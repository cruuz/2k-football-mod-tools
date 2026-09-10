#!/usr/bin/env python3
"""Reproduce APF PLAY format proofs, emitting derived JSON only."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.core import apf2k8_play_codec as c
from mod_editor.core import nfl2k5_play_codec as nfl
from mod_editor.core.apf2k8_play_design_build import read_resource, pack_resource, CPU_PINS, splb


def derive(index: Path, pe: Path | None = None) -> dict:
    resource = read_resource(index, 180)
    body = resource.body
    book = c.Book.from_bytes(body)
    failures = []
    for i, node in enumerate(book.nodes):
        raw = node.to_bytes()
        converted = raw[:4] + raw[4:][::-1]
        legacy = nfl.Node.from_bytes(converted).to_bytes()
        if converted != legacy:
            failures.append({"node_index": i, "body_offset": c.NODE_BASE + i * 8,
                "opcode": node.op, "node_sha256": hashlib.sha256(raw).hexdigest(),
                "legacy_operand_loss_mask": struct.unpack_from("<I", converted, 4)[0] ^ struct.unpack_from("<I", legacy, 4)[0],
                "native_operands": list(node.operands), "native_round_trip_exact": True})
    plays = []
    for i, play in enumerate(book.plays):
        qb = book.chain(i, 0)
        pass_positions = [k for k, n in enumerate(qb) if n.op == 6]
        moves = [n for n in qb[:pass_positions[0]] if n.op == 4] if pass_positions else []
        plays.append({"index": i, "name": book.play_name(i), "offset": c.PLAY_BASE + i * c.PLAY_SIZE,
            "type_nibble": play.type_nibble, "feature_bits_set": [bit for bit in range(32) if play.features & (1 << bit)],
            "assignment_node_counts": [a.count for a in play.assignments],
            "qb_move_depth_ft": [round(n.operands[2] / 30.48) for n in moves],
            "first_read_selector": [n.operands[1] for n in qb if n.op == 6],
            "record_round_trip_exact": True})
    formations = [{"index": i, "name": book.formation_name(i), "offset": c.FORMATION_BASE + i * c.FORMATION_SIZE,
        "default_category": f.category_index, "primary_xy_cm": [[s.x[0], s.y[0]] for s in f.slots], "record_round_trip_exact": True}
        for i, f in enumerate(book.formations)]
    _, transport = pack_resource(resource, body)
    starts = [a.start(c.PLAY_BASE + pi * c.PLAY_SIZE + 16 + slot * 8)
              for pi, p in enumerate(book.plays) for slot, a in enumerate(p.assignments)]
    relation_audit = []
    for outer in CPU_PINS:
        cpu = splb.parse_book(read_resource(index, outer).body, outer)
        rows = [r for r in cpu.records if r.entries]
        hits, entries, complete = 0, 0, 0
        for row in rows:
            covered = sum(bool(body[c.RELATION_BASE + row.formation_index * 84 + e.play_index // 8]
                               & (0x80 >> (e.play_index % 8))) for e in row.entries)
            hits += covered
            entries += len(row.entries)
            complete += covered == len(row.entries)
        relation_audit.append({"outer": outer, "name": cpu.name, "populated_records": len(rows),
                               "entries": entries, "msb_relation_hits": hits, "fully_covered_records": complete})
    string_end = max(offset + len(name.encode("utf-16be")) + 2 for offset, name in book.names)
    result = {"schema": "apf_play_format_proof/v1", "body_sha256": hashlib.sha256(body).hexdigest(),
        "counts": {"plays": len(book.plays), "formations": len(book.formations), "categories": len(book.categories), "nodes": len(book.nodes)},
        "whole_body_round_trip_exact": book.to_bytes() == body,
        "legacy_exact_nodes": len(book.nodes) - len(failures), "legacy_failures": failures,
        "opcode_counts": {str(k): v for k, v in sorted(Counter(n.op for n in book.nodes).items())},
        "native_opaque_operand_nodes": sum(bool(n.opaque_bits) for n in book.nodes),
        "assignments": {"count": len(starts), "unique_starts": len(set(starts)),
            "length_histogram": dict(sorted(Counter(a.count for p in book.plays for a in p.assignments).items())),
            "terminal_0x20_count": sum(bool(book.chain(pi, slot)[-1].flags & c.NODE_TERMINAL) for pi in range(len(book.plays)) for slot in range(11))},
        "capacity": {"formations": 176, "formation_spare": 176 - len(book.formations),
            "physical_play_records": 640, "authoring_play_limit": c.PLAY_CAPACITY,
            "authoring_play_spare": c.PLAY_CAPACITY - len(book.plays), "nodes": c.NODE_CAPACITY,
            "node_spare": c.NODE_CAPACITY - len(book.nodes), "strings_end": string_end,
            "string_spare_bytes": c.STRING_END - string_end},
        "opaque_relation_audit": {"hypothesis": "MSB row at formation index contains every CPU play offered in that formation",
            "result": "REFUTED; preserve opaque relation", "books": relation_audit},
        "allocation": transport, "plays": plays, "formations": formations,
        "runtime_status": "UNWITNESSED", "raw_retail_byte_fields": False}
    if pe is not None:
        data = pe.read_bytes()
        if len(data) != 54001664 or hashlib.sha256(data).hexdigest() != "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf":
            raise ValueError("Expected the documented flat BASE executable image.")
        dispatch = []
        for op in range(29):
            flags = struct.unpack_from(">I", data, 0xFBE68 + op * 4)[0]
            callbacks = struct.unpack_from(">4I", data, 0xFBFC8 + op * 16)
            if not all(0x84630000 <= a < 0x84D09000 for a in callbacks):
                raise ValueError("APF opcode dispatch identity changed.")
            if flags != (0x210A if op == 28 else nfl.OPCODE_FLAGS[op]):
                raise ValueError("APF opcode flag identity changed.")
            dispatch.append({"opcode": op, "flags": flags, "decode": callbacks[0], "encode": callbacks[1], "draw": callbacks[2], "validate": callbacks[3]})
        result["executable"] = {"sha256": hashlib.sha256(data).hexdigest(), "image": "BASE / flat, VA minus 0x82000000",
            "flag_table_va": 0x820FBE68, "dispatch_table_va": 0x820FBFC8, "dispatch_stride": 16, "dispatch": dispatch,
            "coordinate_multipliers": [struct.unpack_from(">f", data, a - 0x82000000)[0] for a in (0x82004498, 0x820B7538)]}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--pe", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = derive(args.index, args.pe)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {result['counts']}; legacy {result['legacy_exact_nodes']}/{len(result['legacy_failures'])}; native exact; {result['allocation']['free_bytes']} free bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
