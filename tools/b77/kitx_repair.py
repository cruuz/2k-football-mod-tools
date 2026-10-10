#!/usr/bin/env python3
"""Combined Beta 77 uniform spans, then w1 wet_93 derived from the resulting clean palettes.

Private compile evidence is supplied by --plan (ordered jobs and manifest paths).
--baseline is the shipped v0.5 image. --input may be that image, extracted packs,
or this repair's output. --stack-index optionally preserves the pinned v3 pack 0.
Only packs 0, 3, 4, 9, A, B, C are read/written. No default.xbe changes.
The baseline and final full-pack hashes gate inputs, including unowned bytes.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools/b77'), str(ROOT / 'tools')]
import u3s_repair as uniforms
import u3r_repair as last
import w1_repair as w1
from mod_editor.core import nfl2k5_bump_texture_writer as bump
from nfl_outer import PACK_NAMES
from nfl_txtr import HEADER, parse_chunks, decode_chunk, texture_to_rgba, parse_texture, minimum_vc_lz_overlap_scratch
import u1_audit as audit

ORDER = ('u1', 'u2a', 'u2b', 'u2c', 'u2d', 'u3s', 'u3a', 'u3b', 'u3c', 'u3d', 'u3e', 'u3r')
PACKS = ('0', '3', '4', '9', 'A', 'B', 'C')
U3C_KEYS = ('JAX:6', 'LAC:9', 'LAC:10', 'LAC:11', 'LV:4', 'MIA:10')
BASELINE_SHA256 = {'0': 'b2c48dd3a3e8c7b5e75a596f83b9f6ef64e6c7c00b613611ed5e9e88b790fd72',
 '3': 'f2b012a4ff8f51a761b2dad74cd1135ef826119e8e13f94f9c82a6ed3959dc8f',
 '4': 'b3884ea0cf49022dfbc9fc23140347217564a5d16e2fc761a36acbc962bf36db',
 '9': '358035d5591898fa920e678a0de929e9e1d11b93c4015febf39714d2b6b180fa',
 'A': '7921c0fd0536b76ef9da5d8d3f32d697e9865ead387ff805cc06d6a9098f19ad',
 'B': '743d3e96e6ed1e934246dae6529d3615f562e4bf9a223bac20f9b03a41ae7f59',
 'C': 'a56bfe6825546c4ef2e909c5339b7fce830ed3dccfc7097ab482fe996b5fd490'}
STACK_INDEX_SHA = 'f54fe60d186b72b3e0e48e868bdf091a9ba1f4a554fd935aec7f8c0f7f404fcd'
sha = w1.sha
require = w1.require


def read_binary(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    with os.fdopen(fd, 'rb') as stream:
        return stream.read()


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(doc, stream, indent=2, sort_keys=True)
        stream.write('\n')


def selected_keys(keys):
    return [k for k in keys if k != 'JAX:5']


def u3c_keys(text):
    keys = text.split(',')
    require(len(keys) == len(U3C_KEYS) and set(keys) == set(U3C_KEYS), 'u3c --keys must exclude JAX:5 and retain all six reviewed alternates')
    return keys


def label_for(key, recipe):
    return (2026, 1) if key == 'JAX:6' else tuple(recipe['label'])


def load_plan(path):
    plan = json.loads(path.read_text())
    require(tuple(j['job'] for j in plan['jobs']) == ORDER, 'uniform jobs must run in the declared order; u3r LAST')
    require(plan['baseline_sha256'] == BASELINE_SHA256, 'plan must pin the shipped v0.5 pack hashes')
    return plan


def patches_for(image, plan):
    index = bump._parsed_index(image)
    by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
    roster_entry = next(e for e in index.entries if e.name_id == uniforms.ROSTER_ID)
    roster = w1._read_resource(image, index, roster_entry)
    groups, provenance, labels = [], {}, []
    b = uniforms._b765()
    for job in plan['jobs']:
        name, patches = job['job'], {}
        docs = []
        for filename in job['manifests']:
            path = Path(filename)
            doc = json.loads(path.read_text())
            if name == 'u3c' and doc.get('key') not in job.get('keys', U3C_KEYS):
                continue
            provenance[str(path)] = sha(read_binary(path))
            if name in ORDER[:5]:
                doc = importlib.import_module('tools.b77.' + name + '_repair').load_manifest(path)
            else:
                require(doc.get('schema') == (last.MANIFEST_SCHEMA if name == 'u3r' else uniforms.MANIFEST_SCHEMA),
                        f'{path}: unsupported manifest')
            docs.append((doc, path.parent))
        keys = selected_keys([d['key'] for d, _ in docs if 'key' in d])
        recipes = None
        if name.startswith('u3') and name != 'u3r':
            recipes = json.loads(Path(job['recipes']).read_text())
            provenance[job['recipes']] = sha(read_binary(Path(job['recipes'])))
            uniforms.load_manifests([Path(p) for p in job['manifests'] if json.loads(Path(p).read_text()).get('key') in keys], recipes, keys)

        def place(resource, entry, patch):
            parts = index.sub_extents(entry, patch['offset'], patch['length'])
            require(len(parts) == 1, 'cross-pack patch refused')
            ordinal, at, length = parts[0]
            require(PACK_NAMES[ordinal] in PACKS and length == patch['length'], 'unexpected pack or span size')
            patches.setdefault(ordinal, []).append(dict(patch, offset=at, resource=resource,
                                                       resource_offset=patch['offset']))

        for doc, base in docs:
            for resource, spans in doc['resources'].items():
                card = uniforms.CARDS.fullmatch(resource)
                require(card or uniforms.KIT.fullmatch(resource), 'unexpected resource')
                entry = index.entries[int(card.group(1))] if card else by_name[resource]
                for patch in spans:
                    data = b.replacement_bytes(base, patch['replacement'])
                    place(resource, entry, dict(patch, data=data))
        if recipes:
            for key in keys:
                recipe = recipes['alternates'][key]
                after = label_for(key, recipe)
                patch = uniforms.roster_patch(roster, recipe['code'], recipe['style'], tuple(recipe['retail_pair']), after)
                place('ROST', roster_entry, patch)
                labels.append(dict(key=key, after=list(after)))
        groups.append((name, patches))
    return index, groups, provenance, labels


def merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def outside_hash(data, ranges):
    digest, cursor = hashlib.sha256(), 0
    for start, end in merge_ranges(ranges) + [(len(data), len(data))]:
        require(0 <= cursor <= start <= end <= len(data), 'invalid scope')
        digest.update(data[cursor:start])
        cursor = end
    return digest.hexdigest()


def validate_input(data, baseline, final):
    require(sha(data) in (sha(baseline), sha(final)), 'unexpected input hash; refusing')
    return data == final


def require_output_room(output, needed):
    """Reserve root space and check the actual destination, including tmpfs."""
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    on_root = os.stat(ancestor).st_dev == os.stat('/').st_dev
    root_write = needed if on_root else 0
    require(shutil.disk_usage('/').free - root_write >= 50 * 1024**3,
            'writes would cross the 50 GiB root disk floor')
    require(shutil.disk_usage(ancestor).free >= needed + 64 * 1024**2,
            'insufficient space on output filesystem')


def apply_uniforms(original, ordinal, groups):
    result, ranges, receipts = original, [], []
    for job, by_pack in groups:
        patches = by_pack.get(ordinal, [])
        if not patches:
            continue
        result, receipt = (last.apply_patches if job == 'u3r' else uniforms.apply_patches)(result, patches)
        ranges.extend((p['offset'], p['offset'] + p['length']) for p in patches)
        receipts.append(dict(job=job, **receipt))
    return result, ranges, receipts


def decoded_textures(span):
    chunk = parse_chunks(span)[0]
    decoded, _ = decode_chunk(span, chunk)
    if chunk.kind == 'TSET':
        textures = [audit.tset_texture(decoded, i) for i in range(struct.unpack_from('<I', decoded, 4)[0])]
    elif chunk.kind == 'TXTR':
        textures = [parse_texture(decoded, chunk)]
    else:
        return decoded, chunk, []
    return decoded, chunk, textures


def check_mud(clean_span, wet_span):
    old, chunk, textures = decoded_textures(clean_span)
    new, _, _ = decoded_textures(wet_span)
    count = 0
    allowed = []
    for texture in textures:
        if texture.name.endswith('_mud'):
            continue
        require(texture_to_rgba(old, chunk, texture) == texture_to_rgba(new, chunk, texture), 'clean texture changed')
        mud = next((t for t in textures if t.name == texture.name + '_mud'), None)
        if mud is None:
            continue
        c, m = 256 + texture.palette_offset, 256 + mud.palette_offset
        allowed.append((m, m+1024))
        expected = b''.join(bytes([w1.wet(new[c+i]), w1.wet(new[c+i+1]), w1.wet(new[c+i+2]), new[c+i+3]]) for i in range(0, 1024, 4))
        require(new[m:m+1024] == expected, 'decoded mud palette differs from clean x 0.93')
        count += 1
    require(outside_hash(old, allowed) == outside_hash(new, allowed), 'decoded bytes outside mud palettes changed (including clean mip chains)')
    return count


def studio_wrapper_span(retail_span, wet_span):
    """Match Studio's fixed-span wrapper using the slot's original scratch floor.

    The dark compile may have needed more overlap scratch than the wet stream.
    Its old floor must not carry into a fresh Studio compile. No stream bytes change.
    """
    retail = HEADER.unpack_from(retail_span)
    fields = list(HEADER.unpack_from(wet_span))
    require(tuple(fields[:5] + fields[6:]) == retail[:5] + retail[6:], 'wrapper layout differs')
    chunk = parse_chunks(wet_span)[0]
    decoded, info = decode_chunk(wet_span, chunk)
    require(info is not None, 'compressed chunk required')
    stream = wet_span[HEADER.size:HEADER.size + info.consumed_bytes]
    padding = fields[1] - len(stream)
    minimum = minimum_vc_lz_overlap_scratch(stream, fields[1], len(decoded))
    fields[5] = max(retail[5], (max(padding, minimum) + 15) & ~15)
    fixed = HEADER.pack(*fields) + wet_span[HEADER.size:]
    require(decode_chunk(fixed, parse_chunks(fixed)[0])[0] == decoded, 'wrapper normalization changed decoded bytes')
    return fixed


def repair(baseline, source, output, plan, stack_index=None):
    b = uniforms._b765()
    for path in (baseline, source, output):
        b.refuse_links(path)
    if stack_index:
        b.refuse_links(stack_index)
    require(output.resolve() not in (source.resolve(), baseline.resolve()), 'output must be separate')
    require(not source.is_dir() or not output.resolve().is_relative_to(source.resolve()), 'output inside input refused')
    require(not baseline.is_dir() or not output.resolve().is_relative_to(baseline.resolve()), 'output inside baseline refused')
    rows = json.loads(w1.KIT_MANIFEST.read_text())['spans']
    require(len(rows) == 210, 'expected 210 mud spans')
    receipt = dict(schema='b77/kitx/repair-receipt/v1', order=list(ORDER), excluded_keys=['JAX:5'], disc_files={})
    acceptance = dict(a=True, b=dict(passed=None, pending='run kitx_acceptance.py for exhaustive decode'), e=dict(passed=None, pending='run kitx_acceptance.py'), c=dict(checked=0, passed=True), d=dict(checked=0, passed=True),
                      f=dict(second_run_noop=True, unexpected_hash_refused=True))
    pending = []
    with bump._Image.open(baseline, writable=False) as base, bump._Image.open(source, writable=False) as incoming:
        require_output_room(output, sum(base.pack_size(PACK_NAMES.index(pack)) for pack in PACKS))
        index, groups, provenance, labels = patches_for(base, plan)
        receipt.update(manifest_sha256=provenance, labels=labels, stack_index_used=stack_index is not None)
        for pack in PACKS:
            print(f'kitx pack {pack}', flush=True)
            ordinal = PACK_NAMES.index(pack)
            original = base.read_pack(ordinal, 0, base.pack_size(ordinal))
            require(sha(original) == plan['baseline_sha256'][pack], f'baseline pack {pack}: unexpected hash')
            starting = original
            if pack == '0' and stack_index:
                starting = read_binary(stack_index)
                require(sha(starting) == STACK_INDEX_SHA, 'stack pack 0: unexpected hash')
            uniform, ranges, jobs = apply_uniforms(starting, ordinal, groups)
            fixed = bytearray(uniform)
            mud_receipts = []
            for row in rows:
                if row['pack'] != ordinal:
                    continue
                entry = w1._entry_for(index, bump, row['selector'])
                require(index.sub_extents(entry, row['resource_offset'], row['length']) == ((ordinal, row['pack_offset'], row['length']),), 'mud span moved')
                at, n = row['pack_offset'], row['length']
                collision = any(s < at+n and at < e for s, e in ranges)
                span = uniform[at:at+n]
                wet, derivation = w1.rewrite_chunk(span)
                check_mud(span, wet)
                key = 'd' if collision else 'c'
                acceptance[key]['checked'] += 1
                if not collision:
                    require(sha(wet) == row['after_sha256'], 'noncolliding output differs from w1 pinned bytes')
                require(w1.rewrite_chunk(wet)[0] == wet, 'mud derivation not idempotent')
                fixed[at:at+n] = wet
                mud_receipts.append(dict(row, input_sha256=sha(span), derived_sha256=sha(wet), collision=collision, derivation=derivation))
                ranges.append((at, at+n))
            # Newly compiled alternates use the catalog's wet_93 mode too. These
            # spans are already uniform-owned; historic Basic 2004 kits stay retail.
            primary = {(r['pack_offset'], r['length']) for r in rows if r['pack'] == ordinal}
            extra = {(p['offset'], p['length']) for _, packs in groups for p in packs.get(ordinal, [])
                     if p['resource'] != 'ROST' and not p['resource'].startswith('outer:')
                     and p.get('label') in ('torso', 'pants', 'sleeve')}
            for at, n in sorted(extra - primary):
                span = uniform[at:at+n]
                wet, derivation = w1.rewrite_chunk(span)
                wet = studio_wrapper_span(original[at:at+n], wet)
                check_mud(span, wet)
                fixed[at:at+n] = wet
                mud_receipts.append(dict(pack_offset=at, length=n, extra_uniform_owned=True,
                                         input_sha256=sha(span), derived_sha256=sha(wet), derivation=derivation))
            fixed = bytes(fixed)
            require(outside_hash(starting, ranges) == outside_hash(fixed, ranges), 'outside-scope bytes changed')
            have = original if source.resolve() == baseline.resolve() else incoming.read_pack(ordinal, 0, incoming.pack_size(ordinal))
            already = validate_input(have, original if pack == '0' and stack_index and have == original else starting, fixed)
            require(validate_input(fixed, starting, fixed), 'second pass differs')
            corrupt = bytes([fixed[0] ^ 1]) + fixed[1:]
            try:
                validate_input(corrupt, starting, fixed)
            except ValueError:
                pass
            else:
                raise ValueError('unexpected hash accepted')
            pending.append((output / pack, fixed))
            receipt['disc_files'][f'vc_53450030/{pack}'] = dict(before_sha256=sha(have), baseline_sha256=sha(original),
                after_sha256=sha(fixed), size=len(fixed), already_applied=already, outside_scope_identical=True, readback=True,
                outside_scope_sha256=outside_hash(fixed, ranges), ranges=merge_ranges(ranges), uniform_jobs=jobs, mud_spans=mud_receipts)
    require(acceptance['c']['checked'] == 159 and acceptance['d']['checked'] == 51, 'unexpected collision counts')
    # Every pack and span is validated before the transactional publication.
    b.publish_batch(pending)
    acceptance['a_reference'] = 'stack pack 0; v0.5 for other packs' if stack_index else 'v0.5'
    return receipt, acceptance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'input', 'output', 'plan', 'receipt', 'acceptance'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--stack-index', type=Path)
    parser.add_argument('--keys', default=','.join(U3C_KEYS), help='u3c selection, excludes JAX:5')
    args = parser.parse_args()
    try:
        require(args.receipt.resolve() != args.acceptance.resolve(), 'receipt and acceptance paths must differ')
        for path in (args.receipt, args.acceptance):
            uniforms._b765().refuse_links(path)
            require(path.resolve() not in (args.plan.resolve(), args.baseline.resolve(), args.input.resolve(),
                    *(args.output.resolve()/pack for pack in PACKS)), 'receipt would overwrite input or output pack')
            require(not args.input.is_dir() or not path.resolve().is_relative_to(args.input.resolve()), 'receipt inside input refused')
        plan = load_plan(args.plan)
        keys = u3c_keys(args.keys)
        next(j for j in plan['jobs'] if j['job'] == 'u3c')['keys'] = keys
        receipt, acceptance = repair(args.baseline, args.input, args.output, plan, args.stack_index)
        write_json(args.receipt, receipt)
        write_json(args.acceptance, acceptance)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'kitx refused: {exc}\n')


if __name__ == '__main__':
    main()
