#!/usr/bin/env python3
"""Reproduce the retail rules census and complete representative chain audit.

Read-only, offline and bounded: only individual PLAY resources and the small
XBE are read, never an archive pack or disc image into memory. JSON on stdout
contains private decoded assignments; choose its destination deliberately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_play_rules as rules
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_play_codec as codec
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES


def audit(image: Path, *, xbe: Path | None = None, corpus: Path | None = None) -> dict:
    reference = rules.reference()
    result = dict(schema='nfl2k5_play_rules_audit/v1', evidence=rules.EVIDENCE,
                  books=[], samples=[], unavailable=reference['unavailable'],
                  plays=0, nodes=0, validated_plays=0, exact_nodes=0,
                  gameplay_witnessed=False)
    names = set()
    with OuterImage(image) as archive:
        for team, entry in BOOK_ENTRIES.items():
            raw = archive.read_entry(entry)
            book = insp.parse_playbook_resource(raw, asset_id='book:' + team)
            body = raw[32:]
            for play in book.plays:
                names.add(play.name.casefold())
                flags, chains = lib.play_chains(body, play.index)
                error = codec.validate_play(flags, chains)
                if error:
                    raise ValueError(f'{team} play {play.index}: {error}')
                codec.validate_sync(chains)
                lib.exact_play_chains(body, play.index)
                result['validated_plays'] += 1
            # Count unique declared pool nodes, not repeatedly shared chains.
            for index in range(book.node_count):
                start = insp.NODE_BASE + 8 * index
                node = body[start:start + 8]
                if codec.Node.from_bytes(node).to_bytes() != node:
                    raise ValueError(f'{team} node {index} did not round-trip exactly')
                result['exact_nodes'] += 1
            result['plays'] += len(book.plays)
            result['nodes'] += book.node_count
            result['books'].append(dict(book=team, source_sha256=hashlib.sha256(raw).hexdigest(),
                body_sha256=hashlib.sha256(body).hexdigest(), plays=len(book.plays),
                formations=len(book.formations), nodes=book.node_count,
                resolved_presets=len(rules.catalog(book, body))))
            for sample in reference['samples']:
                if sample['book'] != team:
                    continue
                play, formation = sample['play'], sample['formation']
                bundle = rules.extract_bundle(book, body, formation, play)
                application = rules.apply_bundle(bundle, book, body, formation, play)
                compiled = rules.compile_application(raw, book, application, replace_index=play)
                if compiled.replacement != raw:
                    raise ValueError(f'{team} play {play}: whole-resource round-trip differs')
                row = rules.inspect_play(book, body, play, formation)
                row.update(id=sample['id'], book=team, formation_name=book.formations[formation].name,
                           source_sha256=hashlib.sha256(raw).hexdigest(),
                           roundtrip_sha256=compiled.replacement_sha256,
                           changed_byte_count=compiled.changed_byte_count,
                           position_codes=list(bundle.position_codes),
                           play_flags=f'0x{bundle.play_flags:08x}')
                result['samples'].append(row)
    result['name_checks'] = {name: name.casefold() in names for name in
                            ('Combo Inside Zone', 'Inside Zone Read', 'Slide protection')}
    if xbe is not None:
        from mod_editor.core.nfl2k5_bump_strength import _sections
        with xbe.open('rb') as stream:
            payload = stream.read(16 * 1024 * 1024 + 1)
        if len(payload) > 16 * 1024 * 1024:
            raise ValueError('Expected a small retail XBE, not a pack or image')
        digest = hashlib.sha256(payload).hexdigest()
        if digest != reference['retail_xbe_sha256']:
            raise ValueError('The XBE differs from the pinned retail evidence')
        table_va = int(reference['opcode_table'], 16)
        section = next(s for s in _sections(payload) if
                       s.virtual_address <= table_va and table_va + 580 <= s.virtual_address + s.raw_size)
        offset = section.raw_offset + table_va - section.virtual_address
        table = payload[offset:offset + 580]
        if hashlib.sha256(table).hexdigest() != reference['opcode_table_sha256']:
            raise ValueError('Retail opcode table differs from the reference')
        for row in reference['opcodes']:
            values = struct.unpack_from('<5I', table, row['opcode'] * 20)
            expected = [int(row['table_flags'], 16)] + [int(row['callbacks'][k], 16)
                        for k in ('decode', 'encode', 'draw', 'validate')]
            if list(values) != expected:
                raise ValueError('Opcode callback identity differs from the reference')
        result['xbe'] = dict(sha256=digest, table_sha256=hashlib.sha256(table).hexdigest(),
                             table_entries_verified=29)
    if corpus is not None:
        wanted = set(reference['runtime_consumers'])
        for row in reference['opcodes']:
            wanted.update(row['callbacks'].values())
            if row['runtime_initializer']:
                wanted.add(row['runtime_initializer'])
        wanted = {int(v, 16) for v in wanted if int(v, 16)}
        found = {}
        for path in sorted((corpus / 'pseudo_c').glob('*.c')):
            # A shard is a bounded text file, independent of the disc size.
            text = path.read_text(encoding='utf-8')
            blocks = list(re.finditer(r'/\*\n \* index:.*?\n \* address: (0x[0-9A-Fa-f]+)', text))
            for index, match in enumerate(blocks):
                address = int(match[1], 16)
                if address in wanted:
                    end = blocks[index + 1].start() if index + 1 < len(blocks) else len(text)
                    block = text[match.start():end]
                    found[f'0x{address:08x}'] = dict(path=str(path.relative_to(corpus)),
                        line=text.count('\n', 0, match.start()) + 1,
                        sha256=hashlib.sha256(block.encode()).hexdigest(), lines=len(block.splitlines()))
        result['corpus'] = dict(functions=found, missing=[f'0x{v:08x}' for v in sorted(wanted)
                                if f'0x{v:08x}' not in found],
                               note='Decompiler types and inferred names are not independent gameplay proof.')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--xbe', type=Path)
    parser.add_argument('--corpus', type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(audit(args.image, xbe=args.xbe, corpus=args.corpus), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
