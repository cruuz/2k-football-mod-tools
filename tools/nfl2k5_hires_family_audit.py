#!/usr/bin/env python3
"""Reproduce retail family pins with bounded, read-only archive access.

Writes metadata only when --catalog / --receipt is supplied. No game data is
exported. The current kits are codes 00..31, H0/A0. Historical kits remain
outside this release. Field scanning covers all 477 field scene resources.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import nfl2k5_hires_texture as texture
from tools import nfl_txtr as txtr
from tools.nfl_uniform_inventory import logical_name_candidates
from tools.nfl_create_team_field_art_inventory import LOGO_CODES, WEATHERS, resource_id


def relative(data, at, system):
    archive.require(0 <= at <= system-4, "Pointer outside system")
    value = struct.unpack_from('<i', data, at)[0]
    if value == 0:
        return None
    target = at-1+value
    archive.require(0 <= target < system, "Pointer target outside system")
    return target


def name(data, at, system):
    archive.require(at is not None and at % 2 == 0, "Invalid name pointer")
    end = next(i for i in range(at, system-1, 2) if data[i:i+2] == b'\0\0')
    return data[at:end].decode('utf-16le')


def describe(raw, outer, chunk, name_id, key, family, kit='', descriptor=None, second=0):
    ch = txtr.parse_chunks(raw)[0]
    archive.require(ch.output_size <= 16*archive.BLOCK, "Resource decode exceeds bound")
    data, comp = txtr.decode_chunk(raw, ch)
    kind, _, system, video, _, _, _, _ = txtr.HEADER.unpack_from(raw)
    if kind == b'TXTR':
        obj = txtr.parse_texture(data, ch)
        descriptor, asset_name = obj.descriptor_offset, obj.name
    else:
        asset_name = 'center_logo' if kind == b'SCNE' else 'jersey00'
    words = struct.unpack_from('<6I', data, descriptor)
    fmt = words[3]
    archive.require(fmt & 0xffff == 0xb29 and words[4:] == (0, 0x80000000), "Nonordinary P8 descriptor")
    native, height, levels = 1 << (fmt >> 20 & 15), 1 << (fmt >> 24 & 15), fmt >> 16 & 15
    asset = texture.Asset(key, outer, chunk, name_id, asset_name, native, levels, descriptor,
                          comp.stream_tag, comp.offset_bits, texture.sha(raw), texture.sha(data[:system]),
                          native_height=height if height != native else 0, family=family, kit=kit,
                          kind=kind.decode(), system_size=system, second_descriptor=second,
                          original_video=video if kind == b'SCNE' else 0,
                          original_pixels=words[1] if kind == b'SCNE' else 0,
                          original_palette=words[2] if kind == b'SCNE' else 0,
                          baseline_sha256=texture.sha(data) if kind == b'SCNE' else '')
    info, _ = texture.inspect_span(raw, asset)
    return asset, info


def audit(image):
    assets, uniforms, fields, errors = [], [], [], []
    pilots = {(a.outer, a.chunk) for a in texture.PILOT_ASSETS}
    with archive.Disc(image, descriptors=()) as disc:
        names = logical_name_candidates()
        fields_by_id = {resource_id(f'CT{code:02d}{weather}.IFF'): f'ct{code:02d}{weather.lower()}'
                        for code in LOGO_CODES for weather, _ in WEATHERS}
        for entry in disc.archive_entries:
            outer = entry.table_index
            logical = names.get(entry.name_id)
            kit = logical.name[:-4].lower() if logical else ''
            current = logical is not None and int(logical.asset_code) < 32 and logical.variant_id == 0
            field = fields_by_id.get(entry.name_id)
            if not (current or field or outer == 346):
                continue
            archive.require(entry.size <= 32*archive.BLOCK, 'Outer exceeds 32 MiB')
            container = disc.read_entry_range(entry, 0, entry.size)
            costs = []
            for chunk, _, raw in archive.chunks(container):
                h = txtr.HEADER.unpack_from(raw)
                if current:
                    costs.append(dict(chunk=chunk, kind=h[0].decode(), system=h[2], video=h[3], scratch=h[5]))
                key = family = ''
                descriptor, second = None, 0
                if current and chunk == 11:
                    key, family = f'helmet_{kit}', 'helmets'
                elif current and 13 <= chunk <= 42:
                    label = ('jersey', 'helmet', 'arm')[(chunk-13)//10]
                    key, family = f'number_{kit}_{label}_{(chunk-13)%10}', 'numbers'
                elif current and chunk == 1:
                    key, family = f'jersey_{kit}', 'jerseys'
                    data, _ = txtr.decode_chunk(raw, txtr.parse_chunks(raw)[0])
                    descriptor = relative(data, 0x20, h[2])
                    second = relative(data, 0x44, h[2])
                    archive.require(struct.unpack_from('<II', data) == (13, 2), 'Foreign jersey TSET')
                    archive.require(name(data, relative(data, 0x1c, h[2]), h[2]) == 'jersey00'
                                    and name(data, relative(data, 0x40, h[2]), h[2]) == 'jersey00_mud', 'Foreign jersey names')
                elif field and chunk == 0:
                    key, family = f'field_{field}', 'field_logos'
                elif outer == 346 and chunk == 26:
                    key, family = 'scorebug_espn', 'scorebug'
                if key and (outer, chunk) not in pilots:
                    try:
                        asset, _ = describe(raw, outer, chunk, entry.name_id, key, family, kit if current else '', descriptor, second)
                        assets.append(asset)
                    except ValueError as exc:
                        errors.append(dict(key=key, outer=outer, chunk=chunk, reason=str(exc)))
            if current:
                uniforms.append(dict(kit=kit, outer=outer, name_id=entry.name_id, resources=costs))
        for outer in range(3136, 3613):
            entry = disc.archive_entries[outer]
            h = disc.read_entry_range(entry, 0, 32)
            size = int.from_bytes(h[4:8], 'little')
            archive.require(h[:4] == b'SCNE' and size < texture.MAX_SCENE_SPAN and size+32 <= entry.size, 'Foreign field scene')
            raw = disc.read_entry_range(entry, 0, size+32)
            ch = txtr.parse_chunks(raw)[0]
            archive.require(ch.output_size <= 16*archive.BLOCK, 'Scene exceeds decode bound')
            data, _ = txtr.decode_chunk(raw, ch)
            system = int.from_bytes(h[8:12], 'little')
            root = relative(data, 20, system)
            count = int.from_bytes(data[root+0x1c:root+0x20], 'little')
            start = relative(data, root+0x20, system)
            archive.require(count < 4096 and start is not None and start+count*128 <= system, 'Foreign material table')
            matches = []
            for i in range(count):
                at = start+i*128
                if name(data, relative(data, at, system), system) == 'center_logo':
                    matches.append(relative(data, at+0x30, system))
            archive.require(len(matches) <= 1, 'Multiple midfield materials')
            row = dict(outer=outer, material_present=bool(matches), embedded=bool(matches and matches[0] is not None),
                       system=system, video=int.from_bytes(h[12:16], 'little'), scratch=int.from_bytes(h[20:24], 'little'))
            fields.append(row)
            if row['embedded']:
                asset, _ = describe(raw, outer, 0, entry.name_id, f'field_o{outer}', 'stock_fields', descriptor=matches[0])
                assets.append(asset)
        xbe = disc.entries['default.xbe']
        archive.require(xbe.size < 16*archive.BLOCK, 'Oversized XBE')
        xbe_sha = texture.sha(disc.read(xbe.size, xbe.byte_offset))
    archive.require(len(uniforms) == 64 and len(fields) == 477, 'Incomplete family census')
    new_counts = Counter(a.family for a in assets)
    counts = new_counts + Counter({'helmets': 1, 'field_logos': 1, 'scorebug': 1})
    return assets, dict(schema='nfl2k5_hires_families/v2', experimental=True, runtime_witnessed=False,
                        xbe_sha256=xbe_sha, asset_count=len(assets)+len(texture.PILOT_ASSETS),
                        counts=dict(counts), added_counts=dict(new_counts),
                        uniforms=uniforms, fields=fields, refused=errors)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args(argv)
    assets, receipt = audit(args.image)
    if args.catalog:
        # Python literal metadata keeps the frozen runtime import self-contained.
        args.catalog.write_text('"""Generated by tools/nfl2k5_hires_family_audit.py; metadata only."""\nROWS = (\n'+
                                ''.join('    '+repr(asdict(a))+',\n' for a in assets)+')\n'+
                                'KIT_COSTS = '+repr({r['kit']: [(c['system'], c['video'], c['scratch']) for c in r['resources']] for r in receipt['uniforms']})+'\n'+
                                'FIELD_COSTS = '+repr({r['outer']: (r['system'], r['video'], r['scratch']) for r in receipt['fields']})+'\n', encoding='utf-8')
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('uniforms', 'fields')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
