#!/usr/bin/env python3
"""Read-only pants census and Models exports from an explicitly supplied disc.

Outputs contain private source-derived geometry/textures. Keep them outside the
repository. No disc writes, resource recompilation, or authored game assets.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_models as models
from mod_editor.core.nfl2k5_music_archive import Disc, chunks, digest, identity
from nfl_scne_gltf import decode_batches, gltf_topology
from nfl_txtr import Chunk, TextureInfo, decode_chunk, texture_to_rgba, encode_rgba_png
from nfl_uniform_inventory import logical_name_candidates, relative_pointer, utf16z


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def extents(disc, entry, start, length):
    result = []
    cursor = 0
    for segment in entry.segments:
        lo, hi = max(start, cursor), min(start + length, cursor + segment.size)
        if hi > lo:
            at = segment.pack_offset + lo - cursor
            result.append(dict(pack=segment.pack_name, pack_offset=at,
                               disc_offset=disc.pack_extents[segment.pack_name].byte_offset + at,
                               size=hi - lo))
        cursor += segment.size
    assert sum(r['size'] for r in result) == length
    return result


def triangles(decoded, submesh):
    result = []
    for mode, batch in decode_batches(decoded, submesh['command_offset'], submesh['primary_command_word_count']):
        mode, ids, _ = gltf_topology(mode, batch)
        if mode == 4:
            ts = [ids[i:i+3] for i in range(0, len(ids), 3)]
        elif mode == 5:
            ts = [ids[i:i+3] for i in range(len(ids)-2)]
        elif mode == 6:
            ts = [[ids[0], ids[i], ids[i+1]] for i in range(1, len(ids)-1)]
        else:
            raise ValueError(f'Unexpected leg primitive {mode}')
        result.extend(t for t in ts if len(set(t)) == 3)
    return result


def census(source, key, folder):
    resource, decoded, scene = source.parse(key)
    result = dict(key=key, scene=scene['name'], decoded_sha256=sha(decoded),
                  decoded_size=len(decoded), shapes=[], materials=scene['materials'])
    for shape in scene['shapes']:
        lanes = models._shape_lanes(scene, shape, decoded)
        pos = models.read_positions(decoded, shape, lanes)
        pairs = models.read_lane_2h(decoded, shape, lanes.texcoord, lanes.vertex_count)
        uv = [models.uv_to_gltf(*p, lanes.uv_scale, lanes.uv_offset) for p in pairs]
        subs = [s for s in scene['submeshes'] if s['shape_index'] == shape['index']]
        skin = models.decode_skin(decoded, shape, lanes, subs)
        row = dict(lanes=asdict(lanes), morphs=models.morph_channels(decoded, lanes),
                   joints=skin.transforms if skin else [], surfaces=[])
        for sub in subs:
            if not any(w in sub['material_name'] for w in ('pants', 'SOCK', 'SHOE', 'SIDELINE')):
                continue
            tris = triangles(decoded, sub)
            ids = sorted({i for t in tris for i in t})
            edges = Counter(tuple(sorted((a, b))) for t in tris for a, b in zip(t, t[1:]+t[:1]))
            surface = dict(submesh=sub, vertices=[dict(id=i, xyz=pos[i], uv=uv[i],
                position_offset=lanes.stream_offsets[lanes.position_stream]+i*lanes.position_stride+lanes.position_offset,
                uv_offset=lanes.stream_offsets[lanes.texcoord[0]]+i*lanes.texcoord[2]+lanes.texcoord[1],
                weights=skin.influences[i] if skin else []) for i in ids],
                triangles=tris, boundary_edges=[list(e) for e,n in edges.items() if n == 1],
                xyz_min=[min(pos[i][a] for i in ids) for a in range(3)],
                xyz_max=[max(pos[i][a] for i in ids) for a in range(3)],
                uv_min=[min(uv[i][a] for i in ids) for a in range(2)],
                uv_max=[max(uv[i][a] for i in ids) for a in range(2)])
            row['surfaces'].append(surface)
        result['shapes'].append(row)
    write_json(folder / f'{key}_census.json', result)
    exported = models.export_model(source, key, folder / f"{scene['name']}_{key}.gltf")
    print(key, scene['name'], exported.summary(), flush=True)
    for row in result['shapes']:
        for s in row['surfaces']:
            print(' ', s['submesh']['submesh_index'], s['submesh']['material_name'],
                  'vertices', len(s['vertices']), 'y', [round(s[k][1], 4) for k in ('xyz_min','xyz_max')],
                  'uv', [[round(x,5) for x in s[k]] for k in ('uv_min','uv_max')], flush=True)
    return result


def texture_records(raw, chunk_index, *, include_pixels=False):
    h = struct.unpack_from('<4s7I', raw)
    chunk = Chunk(chunk_index, 0, h[0].decode(), *h[1:])
    decoded, _ = decode_chunk(raw, chunk)
    result = []
    for i in range(struct.unpack_from('<I', decoded, 4)[0]):
        ref = 0x18 + i*0x24
        name_at = relative_pointer(decoded, ref+4, 'name')
        at = relative_pointer(decoded, ref+8, 'descriptor')
        name = utf16z(decoded, name_at, chunk.system_bytes, 'name')
        _, pixels, palette, fmt, size, flags = struct.unpack_from('<6I', decoded, at)
        width, height = (size & 65535, size >> 16) if size else (1 << ((fmt>>20)&15), 1 << ((fmt>>24)&15))
        tex = TextureInfo(name, name_at, at, pixels, palette, fmt, size, flags,
                          2, (fmt>>8)&255, 'P8', (fmt>>16)&15, width, height, 1)
        rgba = texture_to_rgba(decoded, chunk, tex) if include_pixels and name.startswith(('pants', 'socks')) else None
        result.append((asdict(tex), rgba))
    return chunk, result


def run(args):
    out = args.out.resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError('Private evidence output must be outside the repository')
    out.mkdir(parents=True, exist_ok=True)
    before = identity(args.disc)
    report = dict(schema='pt0_pants_probe/v1', source=str(args.disc), runtime_witnessed=False, models=[], kits=[])
    with Disc(args.disc, descriptors=()) as disc:
        report['source_sha256'] = digest(disc.read, disc.image_size)
        if args.sha256 and args.sha256 != report['source_sha256']:
            raise ValueError('Source disc hash mismatch')
        print('source_sha256', report['source_sha256'], flush=True)
        entry = disc.archive_entries[3]
        data = disc.read_entry_range(entry, 0, entry.size)
        selected = [(i, at, raw) for i,at,raw in chunks(data) if i in (113,114,115)]
        source = models.ModelSpanSource({f'o3c{i}':raw for i,_,raw in selected})
        model_dir = out/'models'; model_dir.mkdir(exist_ok=True)
        for i, at, raw in selected:
            info = dict(key=f'o3c{i}', outer=3, chunk=i, chunk_offset=at, span_size=len(raw),
                        span_sha256=sha(raw), extents=extents(disc,entry,at,len(raw)))
            report['models'].append(info)
            census(source, info['key'], model_dir)
        names = logical_name_candidates()
        for entry in disc.archive_entries:
            logical = names.get(entry.name_id)
            if logical is None:
                continue
            data = disc.read_entry_range(entry, 0, entry.size)
            kit = dict(selector=logical.name, outer=entry.table_index, resources=[])
            for i, at, raw in chunks(data):
                if i not in (2,4,47,48,51):
                    continue
                row = dict(chunk=i, kind=raw[:4].decode(), chunk_offset=at, span_size=len(raw),
                           span_sha256=sha(raw), extents=extents(disc,entry,at,len(raw)))
                if i in (2,4):
                    chunk, textures = texture_records(raw, i, include_pixels=logical.name.removesuffix('.IFF') in args.kits)
                    row.update(system_bytes=chunk.system_bytes, video_bytes=chunk.video_bytes,
                               textures=[t for t,_ in textures])
                    if logical.name.removesuffix('.IFF') in args.kits:
                        folder=out/'kits'/logical.name.removesuffix('.IFF');folder.mkdir(parents=True,exist_ok=True)
                        for tex,rgba in textures:
                            if tex['name'].startswith(('pants','socks')):
                                (folder/(tex['name']+'.png')).write_bytes(encode_rgba_png(tex['width'],tex['height'],rgba))
                kit['resources'].append(row)
            report['kits'].append(kit)
            if len(report['kits']) % 100 == 0:
                print('kits inspected', len(report['kits']), flush=True)
        print('kit_packages',len(report['kits']),flush=True)
        print('pants_dimensions',sorted({(t['width'],t['height'],t['mip_levels']) for k in report['kits'] for r in k['resources'] if r['chunk']==2 for t in r['textures']}),flush=True)
        print('socks_dimensions',sorted({(t['width'],t['height'],t['mip_levels']) for k in report['kits'] for r in k['resources'] if r['chunk']==4 for t in r['textures'] if t['name'].startswith('socks')}),flush=True)
    assert identity(args.disc) == before, 'Source identity changed during inspection'
    report['source_identity_unchanged']=True
    write_json(out/'disc_census.json',report)
    print('source_identity_unchanged True; disc writes 0; disc copies 0',flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--sha256')
    p.add_argument('--kits',nargs='*',default=['18H0','29A0'])
    run(p.parse_args())
