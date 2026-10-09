#!/usr/bin/env python3
"""Install five approved era-kit trades AFTER kitx/u3r, a1_uniforms_repair and sh1.

Private compile manifest pins every input/output pack hash, replacement span,
and outside-scope digest. Only the ten named kit packages, their thirty Team
Select cards, five roster year pairs and eight SITU kit words are allowed.
No directory growth, executable edits or runtime dependencies.

  a5k_repair.py --input vc_53450030 --output NEW/vc_53450030
               --manifest native_manifest.json --receipt receipt.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tools/b77')]
import a5k_kits as kits
import a1_uniforms as uni
import u3s_repair as uniform
import kitx_repair as kitx
from mod_editor.core import nfl2k5_bump_texture_writer as bump
from nfl_outer import PACK_NAMES
from nfl_txtr import decode_chunk, parse_chunks, parse_texture

SCHEMA = 'b77/a5k/repair/v1'
sha, require = uniform.sha, uniform.require


def read_binary(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        return stream.read()


def selection_rows():
    return [(d['situ_row'], d['side'], d['a5_kit'], d['v06_kit'])
            for d in uni.load(ROOT, uni.ERAS)['decisions'] if d['a5_kit'] != d['v06_kit']]


def selection_patches(situ):
    require(len(situ) == 151520, 'unexpected situation.iff size')
    actual = uni.read_situ_kits(situ)
    eras = uni.load(ROOT, uni.ERAS)
    old = {(d['situ_row'], d['side']): d['a5_kit'] for d in eras['decisions']}
    new = {(d['situ_row'], d['side']): d['v06_kit'] for d in eras['decisions']}
    require(all(actual[k] == v for k, v in old.items()) or all(actual[k] == v for k, v in new.items()),
            'apply a1_uniforms_repair first; mixed or foreign moment selection refused')
    patches = []
    for row, side, before, after in selection_rows():
        at = 32+uni.SITU_ROW[0]+row*uni.SITU_ROW[1]+uni.KIT_AT[side]
        data = struct.pack('<I', after)
        patches.append(dict(offset=at, length=4, label=f'moment_{row}_{side}',
                            before_sha256=sha(struct.pack('<I', before)), after_sha256=sha(data), data=data))
    require(len(patches) == 8, 'expected eight changed sides in six moments')
    return patches


def validate_kit_span(name, raw, patch):
    recipe = next((r for r in kits.recipes() if name in {r['code']+s+str(r['style'])+'.IFF' for s in 'HA'}), None)
    require(recipe is not None, f'unowned kit: {name}')
    chunks = parse_chunks(raw)
    allowed = {(c.offset, c.end_offset-c.offset) for c in chunks if c.kind in ('TSET', 'TXTR')}
    allowed.add((0x50, 8))
    if recipe.get('repack_prefix'):
        allowed.add((chunks[1].offset, chunks[44].offset-chunks[1].offset))
    if recipe.get('repack_suffix'):
        allowed.add((chunks[49].offset, len(raw)-chunks[49].offset))
    if recipe.get('atlas'):
        allowed.add((chunks[1].offset, len(raw)-chunks[1].offset))
    require((patch['offset'], patch['length']) in allowed, 'kit patch is not an owned native span')


def patches_for(image, manifest, base):
    index = bump._parsed_index(image)
    by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
    groups = {}
    expected_kits = {r['code']+s+str(r['style'])+'.IFF' for r in kits.recipes() for s in 'HA'}
    require(set(manifest['resources']) == expected_kits | {'outer:3102', 'outer:3105', 'ROST', 'SITU'},
            'manifest resource inventory differs from the five trades')
    roster = kitx.w1._read_resource(image, index, index.entries[5])
    situ = kitx.w1._read_resource(image, index, index.entries[22])
    expected_labels = [uniform.roster_patch(roster, r['code'], r['style'], tuple(r['retail_pair']), tuple(r['label']))
                       for r in kits.recipes()]
    expected_situ = selection_patches(situ)
    expected_words = {'ROST': expected_labels, 'SITU': expected_situ}
    seen_cards = set()
    for name, patches in manifest['resources'].items():
        entry = index.entries[int(name.split(':')[1])] if name.startswith('outer:') else (
            index.entries[5] if name == 'ROST' else index.entries[22] if name == 'SITU' else by_name[name])
        raw = kitx.w1._read_resource(image, index, entry)
        if name in expected_words:
            expected = expected_words[name]
            require({(p['offset'], p['length'], p['before_sha256'], p['after_sha256']) for p in patches} ==
                    {(p['offset'], p['length'], p['before_sha256'], p['after_sha256']) for p in expected},
                    f'{name}: unexpected word patches')
        for patch in patches:
            data = uniform._b765().replacement_bytes(base, patch['replacement'])
            require(sha(data) == patch['after_sha256'] and len(data) == patch['length'], 'replacement hash/size differs')
            require(0 <= patch['offset'] <= len(raw)-patch['length'], 'span exceeds resource')
            if name in expected_kits:
                validate_kit_span(name, raw, patch)
            elif name.startswith('outer:'):
                span = raw[patch['offset']:patch['offset']+patch['length']]
                chunk = parse_chunks(span)[0]
                texture = parse_texture(decode_chunk(span, chunk)[0], chunk)
                wanted = {f'{family}_{s.lower()}{r["code"]}_{r["style"]}'
                          for r in kits.recipes() for s in 'HA' for family in ('unif', 'helm')}
                require(texture.name in wanted and texture.width in (128, 256), 'unowned Team Select card')
                updated_chunk = parse_chunks(data)[0]
                updated = parse_texture(decode_chunk(data, updated_chunk)[0], updated_chunk)
                require((updated.name, updated.width, updated.height) == (texture.name, texture.width, texture.height),
                        'card identity changed')
                seen_cards.add((texture.name, texture.width))
            parts = index.sub_extents(entry, patch['offset'], patch['length'])
            require(len(parts) == 1, 'cross-pack patch refused')
            ordinal, at, n = parts[0]
            require(n == len(data), 'extent size differs')
            groups.setdefault(PACK_NAMES[ordinal], []).append(dict(patch, offset=at, resource=name,
                resource_offset=patch['offset'], data=data))
    require(len(seen_cards) == 30, 'expected thirty updated Team Select cards')
    return groups


def validate_pack(raw, spec):
    accepted={spec['before_sha256'],spec['after_sha256']}
    if spec.get('selection_first_sha256'):
        accepted.add(spec['selection_first_sha256'])
    require(len(raw) == spec['size'] and sha(raw) in accepted,
            'unexpected input pack hash; refusing')


def repair(source, output, manifest, base):
    b = uniform._b765()
    b.refuse_links(source); b.refuse_links(output); b.refuse_links(base)
    require(source.resolve() != output.resolve() and not output.resolve().is_relative_to(source.resolve()),
            'output must be separate from input')
    require(manifest.get('schema') == SCHEMA, 'unsupported a5k repair manifest')
    require(manifest['recipes_sha256'] == sha(read_binary(kits.RECIPES)), 'recipes changed after compile')
    total = sum(p['size'] for p in manifest['packs'].values())
    needed = sum(p['size'] for name, p in manifest['packs'].items() if not (output / name).exists())
    kitx.require_output_room(output, needed)
    pending, files = [], {}
    with bump._Image.open(source, writable=False) as image:
        groups = patches_for(image, manifest, base)
        require(set(groups) == set(manifest['packs']), 'pack inventory differs')
        for name, patches in sorted(groups.items()):
            print('a5k pack', name, flush=True)
            spec = manifest['packs'][name]
            require(image.pack_size(PACK_NAMES.index(name)) == spec['size'], 'unexpected input pack size')
            raw = image.read_pack(PACK_NAMES.index(name), 0, spec['size'])
            validate_pack(raw, spec)
            fixed, receipt = uniform.apply_patches(raw, patches)
            require(sha(fixed) == spec['after_sha256'], 'output pack differs from pinned compile')
            ranges = [(p['offset'], p['offset']+p['length']) for p in patches]
            require(kitx.outside_hash(fixed, ranges) == spec['outside_sha256'] == kitx.outside_hash(raw, ranges),
                    'outside-scope pack digest differs')
            require(uniform.apply_patches(fixed, patches)[0] == fixed, 'repair is not idempotent')
            pending.append((output/name, fixed))
            files['vc_53450030/'+name] = dict(receipt, declared_ranges=kitx.merge_ranges(ranges), readback=True)
    b.publish_batch(pending)
    return dict(schema=SCHEMA, disc_files=files, order=['kitx (u3r last)', 'a1_uniforms_repair', 'sh1', 'a5k'],
                idempotent=True, unexpected_input_refused=True, runtime_witnessed=False,
                directory_growth=0, recipe_sha256=manifest['recipes_sha256'], output_bytes=total)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ('input', 'output', 'manifest', 'receipt'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    try:
        b = uniform._b765()
        for path in (args.manifest, args.receipt):
            b.refuse_links(path)
        require(not args.receipt.resolve().is_relative_to(args.input.resolve()) and
                args.receipt.resolve() != args.manifest.resolve() and
                args.receipt.resolve() not in {args.output.resolve()/n for n in PACK_NAMES}, 'unsafe receipt path')
        manifest = json.loads(read_binary(args.manifest))
        receipt = repair(args.input, args.output, manifest, args.manifest.parent)
        receipt['manifest_sha256']=sha(read_binary(args.manifest))
        b.atomic_write(args.receipt,(json.dumps(receipt,indent=2,sort_keys=True)+'\n').encode('utf-8'))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'a5k refused: {exc}\n')


if __name__ == '__main__':
    main()
