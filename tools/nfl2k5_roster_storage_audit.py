#!/usr/bin/env python3
"""Read-only roster-layout census. Emits addresses/lines/hashes, no game bodies.

Matches are conservative candidates, NOT a claim of complete data-flow proof.
Ghidra has gaps; optional retail instruction and byte-reference scans complement
the corpus. Only the small XBE is read in full, never an archive pack or disc.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

QUERIES = {
    'team_stride': r'\b(?:0x1f4|0x7d|500|125)\b',
    'baked_team_ordinals': r'\b(?:0x2710|0x2904|0x5208)\b',
    'team_active_count': r'\b0x11c\b',
    'team_reserve_metadata': r'\b(?:0x19b|0x1f2|0x1f3)\b',
    'roster_root': r'\b(?:DAT_00b72918|DAT_00b72808)\b',
    'arena_size': r'\b(?:0x91000|0x91020|0x91040|0x90f60|0x91320)\b',
    'created_team_ids': r'\b(?:0x5a|0x5b)\b',
    'stadium_list_cursor': r'\b(?:DAT_00531b70|DAT_00c8f7f0|DAT_00c8f7ec)\b',
    'fixed_slot_bound': r'\b(?:0x41|65)\b',
    'match_team_or_player_buffers': r'\b(?:DAT_00b30864|DAT_00b30a58|DAT_00b30c4c|DAT_00b321a0)\b',
    'front_office_slot_table': r'\b(?:DAT_00e51f60|0x165b0|0x14d50)\b',
}
HOST_QUERY = re.compile(
    r'\b(?:TEAM_SIZE|TEAM_SLOTS|RESERVE_LIMIT|CLUB_TEAM_COUNT|LEAGUE_SLOTS|NFL_TEAMS|'
    r'ARENA_END|ARENA_DECLARED|FRONT_OFFICE_SIZE|F_ROSTER_SLOT_BYTES|'
    r'TEAM_COUNT_FIELD|TEAM_TABLE_FIELD|RETAIL_TEAM_COUNT|team_count|team_table|'
    r'0x1[fF]4|0x91000|0x91020|0x90[Ff]60|65|500)\b')


def corpus_census(corpus: Path) -> dict:
    patterns = {key: re.compile(value, re.I) for key, value in QUERIES.items()}
    matches = {key: [] for key in patterns}
    hashes = {}
    function_count = 0
    for path in sorted((corpus / 'pseudo_c').glob('*.c')):
        digest = hashlib.sha256()
        address = None
        with path.open('rb') as reader:
            for number, raw in enumerate(reader, 1):
                digest.update(raw)
                line = raw.decode('utf-8')
                if found := re.match(r' \* address: (0x[0-9A-Fa-f]+)', line):
                    address = found[1].lower()
                    function_count += 1
                if line.startswith(' *') or line.lstrip().startswith(('/*', '//')):
                    continue
                for key, pattern in patterns.items():
                    if pattern.search(line):
                        matches[key].append([address, path.name, number])
        hashes[path.name] = digest.hexdigest()
    if not hashes:
        raise ValueError('Ghidra pseudo_c shards absent')
    return dict(function_count=function_count, shard_sha256=hashes, queries=QUERIES,
                counts={k: dict(lines=len(v), functions=len({r[0] for r in v})) for k, v in matches.items()},
                candidates=matches)


def host_census(root: Path) -> dict:
    paths = sorted(set((root / 'mod_editor/core').glob('nfl2k5_*.py')) |
                   set((root / 'tools').glob('nfl2k5_*.py')) |
                   set((root / 'tools/practice_squad').glob('*.[cS]')) |
                   {root / 'mod_editor/gui/roster_editor_panel_qt.py',
                    root / 'mod_editor/gui/franchise_panel_qt.py'})
    out = {}
    for path in paths:
        if path.name == Path(__file__).name:
            continue
        data = path.read_bytes()
        lines = [number for number, line in enumerate(data.decode('utf-8').splitlines(), 1)
                 if HOST_QUERY.search(line)]
        if lines:
            out[path.relative_to(root).as_posix()] = dict(sha256=hashlib.sha256(data).hexdigest(), lines=lines)
    return dict(query=HOST_QUERY.pattern, candidates=out)


def xbe_census(path: Path, corpus: Path) -> dict:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('expected small retail default.xbe, not an archive or image')
    image = XbeImage(path.read_bytes())
    if image.sha256 != RETAIL_SHA256:
        raise ValueError('retail XBE SHA-256 mismatch')
    with (corpus / 'functions.tsv').open(encoding='utf-8', newline='') as reader:
        ranges = sorted((int(row['address'], 16), int(row['end'], 16))
                        for row in csv.DictReader(reader, delimiter='\t') if row['section'] == '.text')
    starts = [lo for lo, _ in ranges]
    def function(va):
        at = bisect.bisect_right(starts, va) - 1
        return hex(ranges[at][0]) if at >= 0 and va <= ranges[at][1] else 'GHIDRA_GAP'
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    md.skipdata = True
    text = next(s for s in image.sections if s.name == '.text')
    matches = collections.defaultdict(list)
    # Stream the decoder iterator; do not retain the 1.6M instruction objects.
    for ins in md.disasm(image.read(text.start, text.raw_size), text.start):
        if not ins.id:
            continue
        for operand in ins.operands:
            kind = None
            if operand.type == X86_OP_IMM:
                value = operand.imm & 0xFFFFFFFF
                if value in (500, 125):
                    kind = 'team_stride_immediate'
                elif value in (0x91000, 0x91020, 0x91040, 0x90F60):
                    kind = 'arena_size_immediate'
            elif operand.type == X86_OP_MEM:
                value = operand.mem.disp & 0xFFFFFFFF
                if value == 0x11C:
                    kind = 'active_count_displacement'
                elif value in (0x531B70, 0xC8F7F0):
                    kind = 'stadium_list_cursor_operand'
            if kind:
                matches[kind].append([hex(ins.address), function(ins.address), ins.mnemonic, ins.op_str])
    # Byte-granular reference scan complements instruction alignment/Ghidra gaps.
    import struct
    references = {}
    for target in (0x531B70, 0xC8F7F0):
        found = []
        needle = struct.pack('<I', target)
        for section in image.sections:
            data = image.read(section.start, section.raw_size)
            start = 0
            while (at := data.find(needle, start)) >= 0:
                found.append([hex(section.start + at), section.name])
                start = at + 1
        references[hex(target)] = found
    return dict(retail_sha256=image.sha256, candidates=dict(matches), references=references,
                counts={key: len(rows) for key, rows in matches.items()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--xbe', type=Path)
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args(argv)
    result = dict(schema='nfl2k5_roster_storage_census/v1',
                  proof_boundary='PROVED lexical/decoded matches only. Candidates require data-flow review; computed aliases and Ghidra gaps are not closed.',
                  corpus=corpus_census(args.corpus), studio=host_census(ROOT))
    if args.xbe:
        result['xbe'] = xbe_census(args.xbe, args.corpus)
    args.json.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(corpus=result['corpus']['counts'],
                         studio_files=len(result['studio']['candidates']),
                         xbe=result.get('xbe', {}).get('counts')), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
