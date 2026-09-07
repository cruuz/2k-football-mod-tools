"""Audit supplied community add-ons in real headless Blender, without a disc copy.

Only metadata leaves TemporaryDirectory. The add-ons are explicit local inputs,
not bundled or installed into the user's Blender preferences by this tool.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
IMPORTER = 'NFL_2K5_Stadium_Importer_v0_11_1.py'
EXPORTER = 'NFL_2K5_Stadium_RoundTrip_Exporter_v0_3_0.py'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def runs(indices):
    """Inclusive integer ranges, lossless even for an empty selection."""
    result = []
    for index in sorted(set(indices)):
        if result and result[-1][1] + 1 == index:
            result[-1][1] = index
        else:
            result.append([index, index])
    return result


def float_rows(doc, binary, index):
    """Independent reader for the Models export's dense FLOAT attributes."""
    acc = doc['accessors'][index]
    view = doc['bufferViews'][acc['bufferView']]
    if acc['componentType'] != 5126 or view.get('buffer', 0) != 0 or acc.get('sparse'):
        raise ValueError('Expected dense FLOAT attribute in buffer 0')
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[acc['type']]
    stride = view.get('byteStride', width * 4)
    offset = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    return [struct.unpack_from('<' + 'f' * width, binary, offset + i * stride)
            for i in range(acc['count'])]


def binary_delta(doc, before, after):
    """Account for EVERY differing byte, with row and absolute offset ranges."""
    if len(before) != len(after):
        raise ValueError('BIN size changed')
    changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
    remaining = set(changed)
    accessors = {}
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            for semantic, index in primitive['attributes'].items():
                accessors.setdefault(index, (mesh['name'], semantic))
    details = []
    by_semantic = Counter()
    for index, (name, semantic) in sorted(accessors.items()):
        acc = doc['accessors'][index]
        view = doc['bufferViews'][acc['bufferView']]
        width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[acc['type']] * 4
        stride = view.get('byteStride', width)
        offset = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
        offsets, rows = [], []
        for row in range(acc['count']):
            hits = [p for p in range(offset + row * stride, offset + row * stride + width) if p in changed]
            if hits:
                rows.append(row)
                offsets.extend(hits)
        if offsets:
            remaining.difference_update(offsets)
            by_semantic[semantic] += len(offsets)
            details.append({'mesh': name, 'semantic': semantic, 'accessor': index,
                            'changed_bytes': len(offsets), 'changed_rows': len(rows),
                            'row_ranges_inclusive': runs(rows),
                            'byte_ranges_inclusive': runs(offsets)})
    return {'bytes': len(before), 'before_sha256': sha(before), 'after_sha256': sha(after),
            'changed_bytes': len(changed), 'by_semantic': dict(by_semantic),
            'unattributed_byte_ranges_inclusive': runs(remaining), 'accessors': details}


def load_addon(path, name):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def blender_worker(addons, folder):
    import bpy
    from mathutils import Vector

    importer = load_addon(addons / IMPORTER, 'community_importer')
    exporter = load_addon(addons / EXPORTER, 'community_exporter')
    template = folder / 'template.gltf'
    result = bpy.ops.nfl2k5.import_stadium(filepath=str(template))
    if result != {'FINISHED'}:
        raise RuntimeError(f'Import failed: {result}')
    bpy.context.view_layer.update()
    roots = exporter.find_roots()
    if len(roots) != 1:
        raise RuntimeError(f'Expected one root, got {len(roots)}')
    root = roots[0]
    parts = [o for o in exporter.descendants(root) if o.type == 'MESH']
    settings = bpy.context.scene.nfl2k5_export_settings
    receipt = {'blender_version': bpy.app.version_string, 'import_result': sorted(result),
               'root': root.name, 'root_scale_ok': exporter.root_scale_ok(root),
               'parts': len(parts), 'handles': sum(exporter.is_handle(o) for o in exporter.descendants(root)),
               'missing_vertex_ids': sum(exporter.read_vertex_index_values(p.data) is None for p in parts),
               'attribute_types': dict(Counter((a.name + ':' + a.domain + ':' + a.data_type)
                                               for p in parts for a in p.data.attributes)),
               'scene_diagnostics': {k: v for k, v in bpy.context.scene.items()
                                     if k.startswith(('nfl2k5_last_', 'nfl2k5_time_'))},
               'export_defaults': {k: getattr(settings, k) for k in
                                   ('fast_template_export', 'patch_positions', 'patch_uvs',
                                    'patch_vertex_colors', 'patch_normals', 'flip_v_for_gltf', 'strict_validation')}}
    def export(name):
        outcome = bpy.ops.nfl2k5.export_roundtrip(filepath=str(folder / (name + '.gltf')))
        if outcome != {'FINISHED'}:
            raise RuntimeError(f'{name} failed: {outcome}')
        return sorted(outcome)

    receipt['unchanged_export'] = export('unchanged')
    # Select a small, uniquely owned source-ID island so the one-piece oracle
    # is independent of object order and does not conflate duplicated IDs.
    ownership = Counter((exporter.source_group_name(p), i) for p in parts
                        for i in (exporter.read_vertex_index_values(p.data) or []))
    candidates = [p for p in parts if p.parent and exporter.is_handle(p.parent)
                  and len(p.data.polygons) and exporter.read_vertex_index_values(p.data)
                  and all(ownership[(exporter.source_group_name(p), i)] == 1
                          for i in exporter.read_vertex_index_values(p.data))]
    if not candidates:
        raise RuntimeError('No uniquely owned handle island found')
    part = min(candidates, key=lambda p: (len(p.data.vertices), p.name))
    handle = part.parent
    old_world = handle.matrix_world.copy()
    delta = Vector((1.0, 2.0, 3.0))  # metres in Blender WORLD axes
    moved = old_world.copy()
    moved.translation += delta
    handle.matrix_world = moved
    bpy.context.view_layer.update()
    receipt['movement'] = {'part': part.name, 'group': exporter.source_group_name(part),
                           'source_ids': sorted(exporter.read_vertex_index_values(part.data)),
                           'requested_world_metres': list(delta),
                           'actual_world_metres': list(handle.matrix_world.translation - old_world.translation),
                           'expected_gltf_centimetres': [100.0, 300.0, -200.0]}
    receipt['moved_export'] = export('moved')
    (folder / 'blender.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    exporter.unregister()
    importer.unregister()


def movement_check(doc, before, after, movement):
    group = movement['group']
    mesh = next(m for m in doc['meshes'] if m['name'] == group)
    attrs = mesh['primitives'][0]['attributes']
    ids = float_rows(doc, before, attrs['_NFL_VERTEX_INDEX'])
    old = float_rows(doc, before, attrs['POSITION'])
    new = float_rows(doc, after, attrs['POSITION'])
    selected = set(movement['source_ids'])
    errors = []
    deltas = []
    for i, (a, b) in enumerate(zip(old, new)):
        if int(ids[i][0]) in selected:
            delta = [y - x for x, y in zip(a, b)]
            deltas.append(delta)
            errors.append(max(abs(x-y) for x, y in zip(delta, movement['expected_gltf_centimetres'])))
    return {'selected_rows': len(deltas), 'max_offset_error_cm': max(errors, default=None),
            'actual_offset_min_cm': [min(d[i] for d in deltas) for i in range(3)],
            'actual_offset_max_cm': [max(d[i] for d in deltas) for i in range(3)]}


def contract_details(doc, original, outputs):
    """Check untouched structure, bounds and the residual after fixing axes alone."""
    result = {'mesh_count': len(doc['meshes']),
              'primitive_count': sum(len(m['primitives']) for m in doc['meshes']),
              'semantic_mesh_counts': dict(Counter(s for m in doc['meshes']
                                                  for s in m['primitives'][0]['attributes'])),
              'buffer_count': len(doc['buffers']), 'samplers': doc.get('samplers'),
              'skins': len(doc.get('skins', [])), 'images': len(doc.get('images', [])),
              'one_attribute_map_per_mesh': all(len({json.dumps(p['attributes'], sort_keys=True)
                                                     for p in m['primitives']}) == 1 for m in doc['meshes'])}
    changed_rows = Counter()
    residual, rewritten, max_error = 0, 0, 0.0
    unchanged = outputs['unchanged'][1]
    for mesh in doc['meshes']:
        for semantic, index in mesh['primitives'][0]['attributes'].items():
            old = float_rows(doc, original, index)
            new = float_rows(doc, unchanged, index)
            for a, b in zip(old, new):
                fmt = '<' + 'f' * len(a)
                if struct.pack(fmt, *a) == struct.pack(fmt, *b):
                    continue
                changed_rows[semantic] += 1
                if semantic == 'POSITION':
                    corrected = (b[0], b[2], -b[1])
                    rewritten += 1
                    residual += struct.pack('<3f', *a) != struct.pack('<3f', *corrected)
                    max_error = max(max_error, max(abs(x-y) for x, y in zip(a, corrected)))
    result['changed_rows_by_semantic'] = dict(changed_rows)
    result['axis_correction_only'] = {'rewritten_position_rows': rewritten,
                                      'still_different_position_rows': residual,
                                      'maximum_absolute_error_cm': max_error}
    for name, (document, binary) in outputs.items():
        compared = copy.deepcopy(document)
        bounds_ok = True
        for i, accessor in enumerate(document['accessors']):
            if accessor['componentType'] != 5126 or 'min' not in accessor and 'max' not in accessor:
                continue
            rows = float_rows(document, binary, i)
            for label, reducer in (('min', min), ('max', max)):
                if label in accessor:
                    bounds_ok &= accessor[label] == [reducer(row[k] for row in rows) for k in range(len(rows[0]))]
        compared['buffers'] = doc['buffers']
        for actual, expected in zip(compared['accessors'], doc['accessors']):
            for key in ('min', 'max'):
                if key in expected:
                    actual[key] = expected[key]
        result[name + '_bounds_correct'] = bounds_ok
        result[name + '_document_matches_except_buffer_and_bounds'] = compared == doc
    return result


def compile_result(models, source, key, path, write_uvs):
    try:
        compiled = models.compile_import(source, key, path, write_uvs=write_uvs)
        return {'accepted': True, **compiled.report()}
    except models.UnchangedModelError as exc:
        return {'accepted': True, 'unchanged': True, 'changed_bytes': 0, 'message': str(exc)}
    except models.ModelsError as exc:
        return {'accepted': False, 'changed_bytes': None, 'message': str(exc)}


def prove(args):
    from mod_editor.core import nfl2k5_models as models

    available = shutil.disk_usage(ROOT).free
    if available < 100_000_000_000 + 200_000_000:
        raise ValueError('Need 100 GB free plus 200 MB temporary headroom')
    if args.output.exists():
        raise ValueError('Choose a new metadata output filename')
    source = models.ModelSource(args.index, args.inventory)
    receipt = {'schema': 'nfl2k5_community_blender_proof/v1', 'model_key': args.key,
               'evidence': 'PROVED offline / UNWITNESSED in game', 'free_bytes_before': available,
               'input_index': str(args.index), 'input_inventory': str(args.inventory),
               'addon_sha256': {name: sha((args.addons / name).read_bytes()) for name in (IMPORTER, EXPORTER)}}
    with tempfile.TemporaryDirectory(prefix='nfl2k5-community-') as temporary:
        folder = Path(temporary).resolve()
        started = time.monotonic()
        exported = models.export_model(source, args.key, folder / 'template.gltf')
        receipt['export_summary'] = exported.summary()
        receipt['source_span_sha256'] = sha(source.span(source.resource(args.key)))
        receipt['original_models_import'] = {str(uvs): compile_result(models, source, args.key,
                                                                     exported.gltf_path, uvs) for uvs in (False, True)}
        print(exported.summary(), flush=True)
        command = [args.blender, '-b', '-noaudio', '--factory-startup', '-t', '2', '--python-exit-code', '1',
                   '--python', str(Path(__file__).resolve()), '--', '--worker',
                   '--addons', str(args.addons), '--folder', str(folder)]
        receipt['blender_command'] = command
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, timeout=600, check=False)
        receipt['blender_exit_code'] = completed.returncode
        receipt['blender_log'] = completed.stdout
        if completed.returncode:
            raise RuntimeError(completed.stdout)
        receipt['blender'] = json.loads((folder / 'blender.json').read_text())
        doc = json.loads(exported.gltf_path.read_text())
        original = exported.bin_path.read_bytes()
        outputs = {}
        for name in ('unchanged', 'moved'):
            payload = (folder / (name + '.bin')).read_bytes()
            outputs[name] = (json.loads((folder / (name + '.gltf')).read_text()), payload)
            receipt[name] = binary_delta(doc, original, payload)
            for write_uvs in (False, True):
                label = 'models_import_uvs_on' if write_uvs else 'models_import_defaults'
                print(f'Checking {name}, write_uvs={write_uvs}', flush=True)
                receipt[name][label] = compile_result(models, source, args.key, folder / (name + '.gltf'), write_uvs)
        unchanged = (folder / 'unchanged.bin').read_bytes()
        moved = (folder / 'moved.bin').read_bytes()
        receipt['movement_delta'] = binary_delta(doc, unchanged, moved)
        receipt['movement_offset'] = movement_check(doc, unchanged, moved, receipt['blender']['movement'])
        receipt['contract'] = contract_details(doc, original, outputs)
        receipt['elapsed_seconds'] = time.monotonic() - started
    receipt['temporary_exports_removed'] = not folder.exists()
    receipt['free_bytes_after'] = shutil.disk_usage(ROOT).free
    # Compact ranges avoid megabytes of whitespace; there are no native bytes,
    # images, model coordinates or reconstructed spans in this evidence file.
    args.output.write_text(json.dumps(receipt, separators=(',', ':')) + '\n', encoding='utf-8')
    print(json.dumps({k: receipt[k] for k in ('export_summary', 'elapsed_seconds', 'temporary_exports_removed')}, indent=2))
    for name in ('unchanged', 'moved', 'movement_delta'):
        print(name, receipt[name]['changed_bytes'], receipt[name]['by_semantic'])


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--addons', required=True, type=Path)
    parser.add_argument('--folder', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--index', type=Path)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--key', default='o3136c6')
    parser.add_argument('--blender', default='blender')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    args.addons = args.addons.resolve()
    if args.worker:
        blender_worker(args.addons, args.folder)
    else:
        if not all((args.index, args.inventory, args.output)):
            parser.error('--index, --inventory and --output are required')
        prove(args)


if __name__ == '__main__':
    main()
