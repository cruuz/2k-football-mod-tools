#!/usr/bin/env python3
"""Read-only reference/ownership audit; exports addresses and hashes, no retail bytes."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_player_star as ps
from mod_editor.core.nfl2k5_cave_oracle import (
    XbeImage, ReservationManifest, DEFAULT_MANIFEST, legacy_references)

RETAIL_SHA256 = '73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
RETAIL = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
    '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'


def audit(payload):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    image = XbeImage(payload)
    if image.sha256 != RETAIL_SHA256:
        raise ValueError('requires the pinned USA retail XBE')
    # Ownership remains useful when writer fingerprints have drifted. Report that
    # drift explicitly, then test actual composed-stack bytes independently.
    manifest = ReservationManifest.load(DEFAULT_MANIFEST, image)
    drift = [p for p, digest in manifest.document['source_sha256'].items()
             if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != digest]
    spans = [(va, va+size) for va, size, _ in ps.CAVES]
    hits = set()

    def ref(source, target, kind):
        for start, end in spans:
            if start <= target < end and (source is None or not start <= source < end):
                hits.add((source, target, kind))

    for target, references in legacy_references(image).items():
        for r in references:
            ref(r.source, target, r.kind)
    # Every unaligned dword in every file-backed section, plus the whole header.
    # Includes C7 callbacks regardless of addressing mode and unaligned tables.
    regions = [(image.base, payload[:struct.unpack_from('<I', payload, 0x108)[0]])]
    regions += [(s.start, image.read(s.start, s.raw_size)) for s in image.sections]
    for start, raw in regions:
        for off in range(len(raw)-3):
            ref(start+off, struct.unpack_from('<I', raw, off)[0], 'possible-absolute-pointer')
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.skipdata = True
    text = next(s for s in image.sections if s.name == '.text')
    count = 0
    for address, size, op, args in md.disasm_lite(image.read(text.start, text.raw_size), text.start):
        count += 1
        if op.startswith(('j', 'loop', 'call')) and args.startswith('0x'):
            ref(address, int(args, 16), 'decoded-transfer-including-rel8')
        # Width-overlap reads into a cave could precede its entry by a few bytes.
        # The individual declared boundaries are reviewed in AUDIT.md as well.
    ownership = [{'va': hex(a), 'end': hex(b),
                  'overlaps': manifest.overlaps(a, b, exclude_owner='nfl2k5_player_star'),
                  'retail_sha256': hashlib.sha256(image.read(a, b-a)).hexdigest()}
                 for a, b in spans]
    return {'retail_sha256': image.sha256, 'decoded_instructions': count,
            'manifest_sha256': hashlib.sha256(DEFAULT_MANIFEST.read_bytes()).hexdigest(),
            'manifest_source_drift': drift, 'source_root_checked': False,
            'spans': ownership,
            'external_references': [[hex(a) if a is not None else None, hex(b), k] for a, b, k in sorted(hits)],
            'limit': 'Negative explicit-reference scan; unresolved indirect/computed accesses are not a proof of freedom.'}


def oracle_audit(payload):
    from mod_editor.core.nfl2k5_cave_oracle import CaveOracle
    manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(payload))
    oracle = CaveOracle(payload, manifest=manifest, reference_budget=6_000_000).analyze()
    queries = []
    for va, size, _ in ps.CAVES:
        row = oracle.assess(va, size)
        row['external_witnesses'] = [e.report() for e in oracle.witnesses(va, va+size)
                                     if e.source is not None and not va <= e.source < va+size]
        queries.append(row)
    return {'queries': queries, 'instruction_count': oracle.instruction_count,
            'reference_count': oracle.reference_count, 'unresolved_count': len(oracle.unknowns),
            'unresolved_kinds': sorted(oracle._unknown_kinds),
            'budget_exhausted': {'instructions': oracle._instruction_limit, 'references': oracle._reference_limit}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xbe', type=Path, default=RETAIL)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--oracle', action='store_true')
    args = parser.parse_args()
    payload = args.xbe.read_bytes()
    result = audit(payload)
    if args.oracle:
        result['oracle'] = oracle_audit(payload)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'oracle'}, indent=2))
    if result['external_references'] or any(s['overlaps'] for s in result['spans']):
        raise SystemExit('reference or ownership conflict')
    if args.oracle:
        print('Oracle:', [(q['start'], q['verdict']) for q in result['oracle']['queries']])
        if any(q['verdict'] in ('reserved', 'reachable') for q in result['oracle']['queries']):
            raise SystemExit('oracle found reserved/reachable code; review evidence')
