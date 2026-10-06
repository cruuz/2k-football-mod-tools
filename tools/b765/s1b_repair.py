#!/usr/bin/env python3
"""Prepare/replay a pinned UV-only crowd repair using s1's native writer.

prepare --input-dir V04_FILES --pins stadium_extraction_manifest.json --out PLAN_DIR
apply --input-dir FILES --output-dir FIXED --plan PLAN_DIR/plan.json --receipt JSON

Only crowd NORMSHORT2 lanes and their UV decode constants may change. Positions
are checked byte for byte in native vertex order against the Studio compiler.
The plan pins the original stadium span, accepts its exact idempotent output,
and composes with field-only edits outside that span. No disc is opened.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import importlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from mod_editor.core import nfl2k5_models as models, nfl2k5_scne_builder as sb
from tools.b765 import s1_geometry as g, s1_repair

MODULES = dict(zip(
    ['s00','s01','s03','s07','s10','s11','s12','s14','s15','s16','s20','s23','s24','s25','s40'],
    ['state_farm','mercedes_benz','highmark','att','lambeau','lucas_oil','everbank',
     'hard_rock','usbank','gillette','allegiant','sofi','sofi','levis','sofi']))


def studio_targets(scene, model, *, compiled_meshes=None):
    """Use the same static_shape compiler/full mesh inputs as venue build_scene."""
    result = {}
    compiled_meshes = {} if compiled_meshes is None else compiled_meshes
    meshes = {m.name: m for m in model.meshes.values() if m.groups.get('crowd')}
    crowd_shapes = {i: s for i, s in enumerate(scene.shapes)
                    if any(scene.materials[sm.material].name == 'crowd' for sm in s.submeshes)}
    g.require(all(s.name.endswith('_crowd_fix') for s in crowd_shapes.values()),
              'expected v0.4 crowd-only shapes')
    g.require({s.name.removesuffix('_crowd_fix') for s in crowd_shapes.values()} == set(meshes),
              'native crowd shape set differs from Studio model')
    for shape_id, native in crowd_shapes.items():
        g.require(all(scene.materials[sm.material].name == 'crowd' for sm in native.submeshes),
                  'UV scope includes a non-crowd draw')
        mesh = meshes[native.name.removesuffix('_crowd_fix')]
        ids = sorted({i for strip in mesh.groups['crowd'] for i in strip})
        # A cache belongs to an immutable build() result; do not share entries
        # between different venue model objects, even when mesh names agree.
        key = (id(model), mesh.name, bytes(native.record[0x84:0xC8]))
        if key not in compiled_meshes:
            P = np.asarray(mesh.P) * 100
            compiled_meshes[key] = sb.static_shape(native, mesh.name, P, [(0,0,0,255)] * len(P), mesh.UV, [])
        target = compiled_meshes[key]
        points = np.frombuffer(target.streams[0], '<f4').reshape(-1,3)[ids].tobytes()
        g.require(points == native.streams[0], f'{native.name}: native vertex order/positions differ')
        raw = np.frombuffer(target.streams[1], np.dtype([('c','u1',4),('uv','<i2',2),('s','<i2')]))['uv'][ids]
        constant = struct.unpack_from('<4f', target.record, 0x30)
        uv = [models.uv_to_gltf(int(u),int(v),constant[:2],constant[2:]) for u,v in raw]
        result[shape_id] = dict(name=native.name, ids=ids, raw=raw, uv=uv, constant=constant,
                                positions_sha256=g.sha(points))
    return result


def edit_uvs(folder, targets):
    path = folder / 'stadium.gltf'
    doc = json.loads(path.read_text())
    payload = bytearray((folder / 'stadium.bin').read_bytes())
    for mesh in doc['meshes']:
        shape = mesh['extras']['source_shape_index']
        if shape not in targets:
            continue
        wanted = targets[shape]['uv']
        for primitive in mesh['primitives']:
            attrs = primitive['attributes']
            accessor = doc['accessors'][attrs['TEXCOORD_0']]
            view = doc['bufferViews'][accessor['bufferView']]
            g.require(accessor['componentType'] == 5126 and accessor['type'] == 'VEC2', 'UV accessor format differs')
            ids_accessor = doc['accessors'][attrs[models.VERTEX_INDEX_ATTRIBUTE]]
            ids_view = doc['bufferViews'][ids_accessor['bufferView']]
            id_base = ids_view.get('byteOffset',0) + ids_accessor.get('byteOffset',0)
            id_stride = ids_view.get('byteStride',4)
            g.require(ids_accessor['componentType'] in (5125,5126), 'native ID accessor format differs')
            id_format = '<I' if ids_accessor['componentType'] == 5125 else '<f'
            base = view.get('byteOffset',0) + accessor.get('byteOffset',0)
            stride = view.get('byteStride',8)
            for row in range(accessor['count']):
                value = struct.unpack_from(id_format,payload,id_base+row*id_stride)[0]
                g.require(value == int(value),'native ID must be an integer')
                vertex = int(value)
                struct.pack_into('<2f',payload,base+row*stride,*wanted[vertex])
    (folder / 'stadium.bin').write_bytes(payload)


def prepare_venue(job):
    code, input_dir, out, pins = job
    model = importlib.import_module('mod_editor.core.nfl2k5_'+MODULES[code]+'_model').build(code)
    entries = [];compiled_meshes = {}
    for tod in 'dan':
        for weather in 'drs':
            name = code+tod+weather+'.iff'
            data = (input_dir/name).read_bytes()
            g.require(g.sha(data) == pins[name]['sha256'], f'{name}: unexpected v0.4 input hash')
            folder = out/name.removesuffix('.iff')
            g.export_bundle(data,name,folder,outer_index=pins[name]['outer_index'])
            chunk,_,decoded = g.stadium(data)
            targets = studio_targets(sb.parse(decoded,chunk.system_bytes), model,compiled_meshes=compiled_meshes)
            edit_uvs(folder,targets)
            entry = dict(name=name,manifest=str(folder.relative_to(out)/'manifest.json'),
                         edited=str(folder.relative_to(out)/'stadium.gltf'),uvs=sorted(targets),
                         rescale_uvs=sorted(targets),
                         uv_constants={str(i):list(t['constant']) for i,t in targets.items()})
            entries.append(entry)
    return entries


def verify(data, code, model, *, compiled_meshes=None):
    chunk,_,decoded = g.stadium(data)
    scene = sb.parse(decoded,chunk.system_bytes)
    targets = studio_targets(scene, model,compiled_meshes=compiled_meshes)
    receipts = []
    for shape_id,t in targets.items():
        shape = scene.shapes[shape_id]
        raw = np.frombuffer(shape.streams[1],np.dtype([('c','u1',4),('uv','<i2',2),('s','<i2')]))['uv']
        g.require(np.array_equal(raw,t['raw']),f'{shape.name}: packed crowd UV differs from Studio')
        g.require(shape.record[0x30:0x40] == struct.pack('<4f',*t['constant']),
                  f'{shape.name}: crowd UV constant differs from Studio')
        receipts.append(dict(shape_id=shape_id,name=shape.name,vertices=len(raw),
                             positions_sha256=t['positions_sha256'],
                             packed_uv_sha256=g.sha(raw.tobytes()),
                             uv_constant_sha256=g.sha(shape.record[0x30:0x40]),
                             same_native_order_positions=True,packed_uv_and_constants_equal_studio=True))
    return receipts


def apply(input_dir, output_dir, plan_path, receipt_path, *, workers=1):
    g.require(input_dir.resolve() != output_dir.resolve(), 'input/output folders must differ')
    document = json.loads(plan_path.read_text())
    cache = {};compiled_meshes = {}
    for item in document['entries']:
        g.require(not item.get('positions') and not item.get('bounds') and 'textures' not in item,
                  's1b accepts UV-only crowd repair plans')
        name = item['name']
        g.require(Path(name).name == name and name.endswith('.iff'), 'unsafe resource name')
        code = name[:3]
        g.require(code in MODULES, 'unknown crowd venue')
        if code not in cache:
            cache[code] = importlib.import_module('mod_editor.core.nfl2k5_'+MODULES[code]+'_model').build(code)
            compiled_meshes[code] = {}
        chunk,_,decoded = g.stadium((input_dir/name).read_bytes())
        targets = studio_targets(sb.parse(decoded,chunk.system_bytes),cache[code],compiled_meshes=compiled_meshes[code])
        scopes = set(item.get('uvs',[])) | set(item.get('rescale_uvs',[])) | {int(i) for i in item.get('uv_constants',{})}
        g.require(scopes <= set(targets), 'UV scope includes a non-crowd shape')

    def verify_output(name, data, entry):
        entry['studio_crowd_equality'] = verify(data,name[:3],cache[name[:3]],compiled_meshes=compiled_meshes[name[:3]])
        g.require(not entry['position_shapes'] and not entry['bounds_shapes'], 'non-UV repair scope')
        g.require({e['lane'] for e in entry['edits']} <= {'uv','uv_constant'}, 'non-UV decoded lane changed')

    # Reuse s1's batch collision guards and whole-batch preflight.
    s1_repair.main(['--input-dir',str(input_dir),'--output-dir',str(output_dir),
                   '--plan',str(plan_path),'--receipt',str(receipt_path),
                   '--workers',str(workers)],verify_output=verify_output)
    receipt = json.loads(receipt_path.read_text())
    receipt['scope'] = 'crowd-only packed NORMSHORT2 UVs and shape UV decode constants; all other decoded and outer bytes identical'
    receipt['studio_equality_method'] = 'same full-mesh static_shape compiler as Studio build_scene; sorted crowd IDs; exact FLOAT3 positions, packed UV and constants'
    g.write_atomic(receipt_path,g.json_bytes(receipt))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action',required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--input-dir',required=True,type=Path)
    prepare.add_argument('--pins',required=True,type=Path)
    prepare.add_argument('--out',required=True,type=Path)
    prepare.add_argument('--codes',nargs='+',choices=MODULES,default=list(MODULES))
    prepare.add_argument('--workers',type=int,default=2)
    replay = sub.add_parser('apply')
    replay.add_argument('--input-dir',required=True,type=Path)
    replay.add_argument('--output-dir',required=True,type=Path)
    replay.add_argument('--plan',required=True,type=Path)
    replay.add_argument('--receipt',required=True,type=Path)
    replay.add_argument('--workers',type=int,default=2)
    a=p.parse_args(argv)
    if a.action == 'prepare':
        g.require(not a.out.exists(),'prepare needs a new plan folder')
        g.require(a.workers>0,'workers must be positive')
        pins={e['name']:e for e in json.loads(a.pins.read_text())['entries']}
        a.out.mkdir(parents=True)
        jobs=[(code,a.input_dir,a.out,pins) for code in a.codes]
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            entries=[e for group in pool.map(prepare_venue,jobs) for e in group]
        g.write_atomic(a.out/'plan.json',g.json_bytes(dict(schema='b765_s1_repair_plan/v1',entries=entries)))
        print(json.dumps(dict(plan=str(a.out/'plan.json'),resources=len(entries))))
    else:
        apply(a.input_dir,a.output_dir,a.plan,a.receipt,workers=a.workers)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
