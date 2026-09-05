#!/usr/bin/env python3
"""Prove the star path on a private disc; optionally create an exclusive patched copy.

Only the resolved default.xbe extent changes. The input disc is always read-only.
Every byte outside that extent is compared after the copy, and all XBE section
hashes are verified. No runtime installation or GUI/dispatcher change is needed.
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tools'))
from mod_editor.core import nfl2k5_player_star as ps, nfl2k5_player_tags as pt
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_throw_tuning import image_xbe_extent
from nfl2k5_playbook_position_recode import OuterImage


def disc_xbe(path):
    with path.open('rb') as f:
        extent = image_xbe_extent(f.fileno(), os.fstat(f.fileno()).st_size)
        f.seek(extent[0])
        payload = f.read(extent[1])
    if len(payload) != extent[1]:
        raise ValueError('short executable read')
    return payload, extent


def copy_disc(source, target, expected_source, patched, extent):
    if source.resolve() == target.resolve():
        raise ValueError('target must be a new private disc copy')
    if len(expected_source) != len(patched):
        raise ValueError('executable size changed')
    for s in _sections(patched):
        if patched[s.header_offset+36:s.header_offset+56] != section_digest(patched, s):
            raise ValueError(f'bad section digest {s.index}')
    created = False
    try:
        with source.open('rb') as src, target.open('xb') as dst:
            created = True
            before = os.fstat(src.fileno())
            src.seek(extent[0])
            if src.read(extent[1]) != expected_source:
                raise ValueError('source executable changed since inspection')
            src.seek(0)
            cloned = False
            try:
                import fcntl
                fcntl.ioctl(dst.fileno(), 0x40049409, src.fileno())  # Linux FICLONE
                cloned = True
            except (ImportError, OSError):
                pass
            if not cloned:
                while block := src.read(16*1024*1024):
                    dst.write(block)
            dst.seek(extent[0])
            dst.write(patched)
            dst.flush()
            os.fsync(dst.fileno())
            after = os.fstat(src.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('source changed during copy')
        # Complete comparison, not just an XBE spot-check.
        hsrc, hdst = hashlib.sha256(), hashlib.sha256()
        outside = 0
        with source.open('rb') as a, target.open('rb') as b:
            pos = 0
            while left := a.read(16*1024*1024):
                right = b.read(len(left))
                if len(right) != len(left):
                    raise ValueError('short copied image')
                hsrc.update(left)
                hdst.update(right)
                lo = max(0, min(len(left), extent[0]-pos))
                hi = max(0, min(len(left), extent[0]+extent[1]-pos))
                if left[:lo] != right[:lo] or left[hi:] != right[hi:]:
                    raise ValueError('a byte outside default.xbe changed')
                outside += lo + len(left)-hi
                pos += len(left)
            if b.read(1):
                raise ValueError('copied image grew')
        got, got_extent = disc_xbe(target)
        if got != patched or got_extent != extent or ps.status(got) != 'applied':
            raise ValueError('copied executable verification failed')
        return {'source_disc_sha256': hsrc.hexdigest(), 'output_disc_sha256': hdst.hexdigest(),
                'compared_unchanged_bytes_outside_xbe': outside, 'reflink': cloned,
                'output_image': str(target.resolve())}
    except BaseException:
        if created:
            target.unlink()
        raise


def evidence(source):
    original, extent = disc_xbe(source)
    with OuterImage(source) as archive:
        body = archive.read_entry(pt.ROST_OUTER_INDEX)[pt.RESOURCE_HEADER_SIZE:]
    return evidence_records(original, body, str(source.resolve()), extent)


def evidence_records(original, body, source, extent):
    """Also accept private snapshots captured before a source disc was moved."""
    from tools.player_star.emulate import Machine, HEAP
    fixed, receipt = ps.apply(original)
    players = pt.parse_body(body).tagged
    if not players:
        raise ValueError('disc has no tagged players to exercise')
    selected = players[:ps.ENTITY_LIMIT]
    results = {}
    for label, payload in (('source', original), ('fixed', fixed)):
        vm = Machine(payload)
        entities = vm.entities([1]*len(selected), controlled=(0,))
        arena = HEAP+0x100000
        team = HEAP+0xA0000
        vm.uc.mem_write(arena, body)
        for i, player in enumerate(selected):
            pointer = arena+player.offset
            vm.run(0xE5E70, ecx=pointer)  # actual roster-record pointer relocator
            vm.set32(team+i*4, pointer)
        vm.uc.mem_write(team+0x11C, bytes([len(selected)]))
        vm.run(0xC3C60, ecx=team, edx=0xB30C4C)  # actual in-game whole-record copy
        tag_bytes = [bytes(vm.uc.mem_read(0xB30C4C+i*0x54+0x53, 1))[0] for i in range(len(selected))]
        gate_results = [vm.run(ps.GATE_VA, ecx=e) for e in entities]
        material_before = bytes(vm.uc.mem_read(vm.u32(ps.MATERIAL_VA), 128))
        vm.frame()
        strips = []
        for row in vm.strips:
            strips.append({'primitive': row['primitive'], 'vertex_count': len(row['vertices']),
                           'closed': row['vertices'][:2] == row['vertices'][-2:],
                           'colors': [hex(c) for c in sorted({v[3] for v in row['vertices']})],
                           'diffuse': hex(struct.unpack_from('<I', row['material'], 0x18)[0]),
                           'texture': hex(struct.unpack_from('<I', row['material'], 0x30)[0]),
                           'vertices': row['vertices']})
        results[label] = {'status': ps.status(payload), 'xbe_sha256': hashlib.sha256(payload).hexdigest(),
                          'runtime_tag_bytes': tag_bytes, 'gate_results': gate_results,
                          'controller_count': vm.u32(ps.STAR_COUNT_VA)&255,
                          'retail_models': vm.models, 'star_strips': strips,
                          'shared_material_unchanged': material_before == bytes(vm.uc.mem_read(vm.u32(ps.MATERIAL_VA), 128))}
    if len(results['fixed']['star_strips']) != len(selected):
        raise AssertionError('a tagged runtime record failed to submit a star')
    result = {'schema': 'nfl2k5-star-draw-proof/v1', 'source': source,
              'xbe_extent': [extent[0], extent[1]],
              'tagged_players': [{'pool': p.pool, 'index': p.index, 'name': p.display, 'offset': hex(p.offset)} for p in players],
              'executed_lineup': 'synthetic on-field entities with real relocated/copied disc records; first player controlled',
              'execution': results, 'patch': receipt,
              'proof_boundary': 'Unicorn executes CPU and inline vertex writes. GPU setup/services are stubbed; in-game witness pending.'}
    return result, original, fixed, extent


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--output-image', type=Path)
    args = parser.parse_args()
    reserved = {args.source.resolve()}
    if args.output_image:
        reserved.add(args.output_image.resolve())
    if args.json.resolve() in reserved:
        parser.error('JSON output must differ from both discs')
    for output in (args.json, args.output_image):
        if output is not None and output.exists():
            parser.error(f'output already exists: {output}')
    result, original, fixed, extent = evidence(args.source)
    if args.output_image:
        result['copy'] = copy_disc(args.source, args.output_image, original, fixed, extent)
    with args.json.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps({'source_status': result['execution']['source']['status'],
                      'fixed_status': result['execution']['fixed']['status'],
                      'players': [p['name'] for p in result['tagged_players']],
                      'star_outlines': len(result['execution']['fixed']['star_strips']),
                      'proof': str(args.json), 'copy': result.get('copy')}, indent=2))
