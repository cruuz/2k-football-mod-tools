"""Bounded retail-set acceptance for Stadium glTF and Blender textures.

Reads one SCNE span at a time. Temporary exports are deleted per scene; the
only retained output is JSON metadata/hashes. Never creates an image or pack
copy and never writes the supplied source/cache. No bpy or display required.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT/'tools'):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
from mod_editor.core.nfl2k5_stadium_studio import Nfl2k5StadiumStudio, stadium_gltf_texture_slots
from mod_editor.core.nfl2k5_stadium_texture_writer import (
    _DynamicStadiumResolver, _compile_resolved_scene, _decode_dynamic_p8_mips,
    decode_rgba_png,
)
from nfl_scne_inventory import parse_scene, texture_info
from nfl_txtr import HEADER, decompress_vc_lz, encode_rgba_png, texture_to_rgba
from tools.blender.nfl2k5_stadium import texture_document


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, label):
    if not condition:
        raise ValueError(label)


def verify_uvs(document, binary, decoded, source):
    vertices = 0
    for mesh in document['meshes']:
        shape = source['shapes'][mesh['extras']['source_shape_index']]
        lane = next(row for row in shape['attribute_descriptors'] if row['register'] == 6)
        stream = next(row for row in shape['vertex_streams'] if row['stream_index'] == lane['stream_index'])
        su, sv, ou, ov = struct.unpack_from('<4f', decoded, shape['record_offset'] + 0x30)
        accessor = document['accessors'][mesh['primitives'][0]['attributes']['TEXCOORD_0']]
        view = document['bufferViews'][accessor['bufferView']]
        expected = bytearray()
        for i in range(shape['vertex_count']):
            u, v = struct.unpack_from('<2h', decoded, stream['offset'] + i*stream['stride'] + lane['byte_offset'])
            expected.extend(struct.pack('<2f', u/(32767 if u >= 0 else 32768)*su+ou,
                                        v/(32767 if v >= 0 else 32768)*sv+ov))
        require(binary[view['byteOffset']:view['byteOffset']+view['byteLength']] == expected,
                'source UV formula differs from glTF')
        vertices += shape['vertex_count']
    return vertices


def prove_scene(studio, scene, resolver, changed):
    details = studio.scene_details(scene)
    sources = resolver.resolve_many(tuple(texture.texture_id for texture in details.textures))
    first = sources[0]
    native = parse_scene(scene.scene_index, first.resource, first.decoded, {})[0]
    studio.scene_source = lambda _scene: (first.decoded, native)
    with tempfile.TemporaryDirectory(prefix='nfl2k5-stadium-proof-') as temporary:
        root = Path(temporary).resolve()
        gltf, binary_path = studio.export_scene_gltf(scene, root/'stadium.gltf')
        binary = binary_path.read_bytes()
        require(binary.startswith(scene.bin_path.read_bytes()), 'geometry buffer changed')
        document = json.loads(gltf.read_text())
        vertices = verify_uvs(document, binary, first.decoded, native)
        slots = stadium_gltf_texture_slots(gltf)
        pngs = {slot.texture_id: slot.payload for slot in slots}
        require(set(pngs) == {row.texture_id for row in details.textures}, 'missing texture binding')
        for texture in details.textures:
            require(pngs[texture.texture_id] == texture.png_path.read_bytes(), 'embedded PNG bytes changed')
            require(sha(decode_rgba_png(pngs[texture.texture_id], (texture.width, texture.height))[2])
                    == texture.rgba_sha256, 'PNG pixels differ from source')
        # The Blender helper's actual portable output contract feeds the actual
        # Studio importer. bpy pixel saving is separately mocked, not witnessed.
        bundle = texture_document([(row.texture_id, row.width, row.height, pngs[row.texture_id])
                                   for row in details.textures])
        bundle_path = root/'textures.gltf'
        bundle_path.write_text(json.dumps(bundle), encoding='utf-8', newline='\n')
        receipts = studio.replace_textures_from_gltf(scene, bundle_path)
        require(len(receipts) == len(pngs) and not any(row.changed for row in receipts), 'no-op import staged edits')
        paths = []
        for index, row in enumerate(details.textures):
            path = root/f'{index}.png'
            path.write_bytes(pngs[row.texture_id])
            paths.append(path)
        no_op = _compile_resolved_scene(sources, paths)
        require(no_op.fixed.span == first.span and no_op.decoded_changed_byte_count == 0,
                'unchanged SCNE is not byte-identical')
        result = {'scene_id': scene.scene_id, 'pack': first.contract.pack_name,
                  'textures': len(pngs), 'meshes': len(document['meshes']), 'uv_vertices': vertices,
                  'source_span_sha256': sha(first.span), 'unchanged_span_sha256': sha(no_op.fixed.span),
                  'geometry_prefix_sha256': scene.bin_sha256,
                  'export_binary_sha256': sha(binary),
                  'transform_counts': dict(Counter(str(shape['transform_count']) for shape in native['shapes'])),
                  'node_count': len(native['nodes']), 'status': 'PROVED offline / UNWITNESSED in game'}
        if changed:
            # Two disjoint texture edits exercise the same-scene union. Solid
            # colours are deliberate fixed-palette witnesses, not fidelity tests.
            chosen = sorted(range(len(sources)), key=lambda i: sources[i].contract.width*sources[i].contract.height, reverse=True)[:2]
            replacements, edited_sources, wanted = [], [], []
            for ordinal, index in enumerate(chosen):
                source = sources[index]
                c = source.contract
                rgba = bytes((17 + ordinal, 201, 37, 255)) * (c.width*c.height)
                if sha(rgba) == c.rgba_sha256:
                    rgba = bytes((91, 12, 199, 255)) * (c.width*c.height)
                paths[index].write_bytes(encode_rgba_png(c.width, c.height, rgba))
                replacements.append(paths[index]); edited_sources.append(source); wanted.append(rgba)
            compiled = _compile_resolved_scene(edited_sources, replacements)
            after, info = decompress_vc_lz(compiled.fixed.span[HEADER.size:], len(first.decoded))
            require(len(compiled.fixed.span) == len(first.span), 'changed stored span grew')
            require(info.consumed_bytes <= first.contract.retail_consumed, 'compression exceeds retail cap')
            tail_at = HEADER.size + first.contract.retail_consumed
            require(compiled.fixed.span[tail_at:] == first.span[tail_at:], 'opaque tail changed')
            require(compiled.fixed.span[HEADER.size+info.consumed_bytes:tail_at] ==
                    bytes(tail_at-HEADER.size-info.consumed_bytes), 'nonzero compression gap')
            before_header, after_header = bytearray(first.span[:HEADER.size]), bytearray(compiled.fixed.span[:HEADER.size])
            before_header[20:24] = after_header[20:24]
            require(before_header == after_header, 'wrapper field other than scratch changed')
            ranges = [(row.contract.system_bytes + row.contract.pixel_offset,
                       row.contract.system_bytes + row.contract.palette_offset + 1024) for row in edited_sources]
            cursor = 0
            for start, end in sorted(ranges):
                require(after[cursor:start] == first.decoded[cursor:start], 'unselected SCNE bytes changed')
                cursor = end
            require(after[cursor:] == first.decoded[cursor:], 'unselected SCNE tail changed')
            for source, rgba in zip(edited_sources, wanted):
                c = source.contract
                chunk = SimpleNamespace(index=c.chunk_index, system_bytes=c.system_bytes, video_bytes=c.video_bytes)
                info = texture_info(after, c.descriptor_offset, 'stadium', c.texture_index)
                require(texture_to_rgba(after, chunk, info) == rgba, 'independent edited P8 decode differs')
                require(all(mip == rgba[:4]*(w*h) for mip, (w,h) in
                            zip(_decode_dynamic_p8_mips(after, c), c.mip_dimensions)), 'edited mip chain differs')
            result['changed'] = {'texture_ids': [row.contract.texture_id for row in edited_sources],
                                 'decoded_changed_bytes': compiled.decoded_changed_byte_count,
                                 'span_sha256': sha(compiled.fixed.span),
                                 'encoded_bytes': compiled.fixed.encoded_bytes,
                                 'retail_consumed': first.contract.retail_consumed,
                                 'scratch_bytes': compiled.fixed.scratch_after,
                                 'unselected_bytes_preserved': True}
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True, help='private stadium-studio-v1 directory')
    parser.add_argument('--index', type=Path, required=True, help='retail archive pack 0')
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='metadata-only JSON receipt')
    parser.add_argument('--start', type=int, default=0, help='first scene ordinal for bounded batches')
    parser.add_argument('--limit', type=int, default=0, help='0 means all scenes')
    parser.add_argument('--changed', choices=('all', 'none'), default='all')
    args = parser.parse_args(argv)
    started = time.monotonic()
    resolver = _DynamicStadiumResolver(args.index, args.inventory)
    studio = Nfl2k5StadiumStudio(args.cache/'models/manifest.json', args.cache/'textures/manifest.json', args.cache/'textures')
    rows = []
    if args.start < 0 or args.limit < 0:
        parser.error('start and limit must be nonnegative')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scenes = studio.list_scenes()[args.start:][:args.limit or None]
    for scene in scenes:
        row = prove_scene(studio, scene, resolver, args.changed == 'all')
        rows.append(row)
        args.output.with_suffix('.progress.json').write_text(json.dumps({'scenes': rows}), encoding='utf-8', newline='\n')
        studio._details.clear()
        print(json.dumps({'completed': len(rows), 'total': len(scenes), 'scene': scene.scene_id,
                          'elapsed_seconds': round(time.monotonic()-started, 2)}), flush=True)
    report = {'schema': 'nfl2k5_stadium_editor_proof/v1', 'contains_retail_bytes': False,
              'scene_count': len(rows), 'texture_occurrences': sum(row['textures'] for row in rows),
              'uv_vertices': sum(row['uv_vertices'] for row in rows),
              'mesh_count': sum(row['meshes'] for row in rows),
              'changed_scene_count': sum('changed' in row for row in rows),
              'elapsed_seconds': round(time.monotonic()-started, 2),
              'blender_runtime_witness': False, 'gameplay_witness': False, 'scenes': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    args.output.with_suffix('.progress.json').unlink(missing_ok=True)
    print(json.dumps({k:v for k,v in report.items() if k != 'scenes'}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
