#!/usr/bin/env python3
"""Read-only structural probe of the supplied decrypted PS3 season payload.

This emits offsets, counts and hashes only. It does not produce a converted
save, fix source bytes, assign meanings to opaque fields, or launch a game.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.apf_studio import ps3_roster_convert as roster

ROSTER_OFFSET = 0x350
TAIL = ROSTER_OFFSET + roster.ROSTER_SIZE
SEASON_SIZE = 2_786_356


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verdict(function, data):
    try:
        function(data)
        return "accepted"
    except (ValueError, RuntimeError) as exc:
        return f"{type(exc).__name__}: {exc}"


def probe(data: bytes) -> dict:
    if len(data) != SEASON_SIZE:
        raise ValueError("This probe describes only the 2,786,356-byte season fixture")
    embedded = data[ROSTER_OFFSET:TAIL]
    structure = roster.inspect_structure(embedded)
    banks = [i for i in range(len(embedded) - 3) if embedded.startswith(roster.BANK_MAGIC, i)]
    readers = {"structure": roster.inspect_structure, "players": roster.players_reader.inspect_bytes,
               "labels": roster.labels_reader.parse_save}
    counts = [roster.save_layout._root_count(embedded, i) for i in range(40)]
    tables = [{"index": i, "absolute_offset": ROSTER_OFFSET + span.start,
               "relative_offset": span.start, "count": span.count, "stride": span.stride}
              for i, span in sorted(structure.tables.items())]
    # The fixture's trailer has a count followed by a fixed table-10-sized
    # index arena. Check every entry before reporting that relationship.
    live_count = struct.unpack_from(">I", data, 0x2A1E90)[0]
    indices = struct.unpack_from(f">{counts[10]}H", data, 0x2A1E94)
    active = indices[:live_count]
    assert len(set(active)) == live_count and all(i < counts[10] for i in active)
    assert all(i == 0xFFFF for i in indices[live_count:])
    assert all(a > b for a, b in zip(active, active[1:]))
    team_ids = struct.unpack_from(">24H", data, 0x297624)
    assert len(set(team_ids)) == 24 and all(i < counts[4] for i in team_ids)
    patterns = []
    for start, count, words in ((0x29E99C, 48, (0xFFFF0000, 0)),
                              (0x29EDB0, 100, (0, 0, 0xFFFFFF00)),
                              (0x29F264, 864, (0x0000FFFF,)),
                              (0x2A0034, 600, (0x0000FFFF, 0x000000FF, 0)),
                              (0x2A1CB0, 120, (0x0000FFFF,))):
        pattern = struct.pack(f">{len(words)}I", *words)
        assert data[start:start + count * len(pattern)] == pattern * count
        patterns.append({"offset": start, "stride": len(pattern), "count": count,
                         "end": start + count * len(pattern), "words": list(words),
                         "meaning": "unknown, repeated sentinel/default records"})
    calendar_count = struct.unpack_from(">I", data, 0x2A7C54)[0]
    calendar = []
    assert calendar_count == 19
    for i in range(calendar_count):
        at = 0x2A7C58 + i * 20
        packed = struct.unpack_from(">H", data, at)[0]
        calendar.append({"offset": at, "packed_date": packed,
                         "day_bits": packed & 31, "month_bits_plus_one": ((packed >> 5) & 15) + 1,
                         "year_bits_epoch_unknown": packed >> 9,
                         "state_word": struct.unpack_from(">I", data, at + 4)[0]})
    prefix_words = struct.unpack_from(">212I", data)
    floats = [struct.unpack(">f", struct.pack(">I", word))[0] for word in prefix_words]
    return {
        "schema": "apf2k8_b72_season_probe/v1", "source_sha256": sha(data), "size": len(data),
        "regions": [
            {"offset": 0, "size": ROSTER_OFFSET, "sha256": sha(data[:ROSTER_OFFSET]),
             "description": "prefix of flags, integers and float-like settings; field meanings unproved",
             "zero_or_one_words": sum(v in (0, 1) for v in prefix_words),
             "words_decoding_as_floats_in_0_1": sum(0.1 <= v <= 1 for v in floats)},
            {"offset": ROSTER_OFFSET, "size": len(embedded), "sha256": sha(embedded),
             "description": "embedded roster graph"},
            {"offset": TAIL, "size": len(data) - TAIL, "sha256": sha(data[TAIL:]),
             "zero_bytes": data[TAIL:].count(0), "ff_bytes": data[TAIL:].count(255),
             "description": "season state, index/sentinel arenas, and packed calendar records"}],
        "strict_readers": {label: {name: verdict(fun, payload) for name, fun in readers.items()}
                           for label, payload in (("whole", data), ("first_roster_size_bytes", data[:roster.ROSTER_SIZE]),
                                                  ("embedded_at_0x350", embedded))},
        "root_counts": counts, "tables": tables,
        "embedded_platform": roster.detect_platform(embedded, structure),
        "string_pool_absolute": ROSTER_OFFSET + structure.pool_start,
        "string_references": len(structure.references), "string_allocations": len(structure.allocations),
        "odd_allocations": sum(a.odd for a in structure.allocations.values()),
        "interior_allocations": len(structure.interior),
        "palette_votes_alpha_first_last": list(roster._palette_votes(embedded, structure.tables[16])),
        "root_runtime_words": [{"table": i, "offset": ROSTER_OFFSET + 8 + i * 8,
                                 "value": struct.unpack_from(">I", embedded, 8 + i * 8)[0]}
                                for i in roster.XBOX_ROOT_RUNTIME_TABLES],
        "runtime_block_offset": ROSTER_OFFSET + roster.RUNTIME_BLOCK_OFFSET,
        "runtime_block_words": list(struct.unpack_from(">8I", embedded, roster.RUNTIME_BLOCK_OFFSET)),
        "banks": [{"absolute_offset": ROSTER_OFFSET + pos, "roster_offset": pos,
                   "runtime_words": [struct.unpack_from(">I", embedded, pos + rel)[0]
                                     for rel in roster.BANK_WORD_OFFSETS],
                   "within_existing_converter_scan": pos >= roster.USER_REGION} for pos in banks],
        "bank_spacing": sorted({b - a for a, b in zip(banks, banks[1:])}),
        "team_id_array": {"offset": 0x297624, "count": len(team_ids), "ids": list(team_ids),
                          "observation": "slots 0..23, except slot 2 replaced by custom slot 32"},
        "repeated_records": patterns,
        "table10_index_arena": {"count_offset": 0x2A1E90, "offset": 0x2A1E94,
            "capacity": len(indices), "entry_size": 2, "active_count": live_count,
            "active_min_max": [min(active), max(active)], "unique_descending": True,
            "sentinel_count": len(indices) - live_count, "end": 0x2A1E94 + len(indices) * 2,
            "meaning": "likely free/available record IDs; semantics unproved"},
        "calendar": {"count_offset": 0x2A7C54, "count": calendar_count, "stride": 20, "rows": calendar,
                     "meaning": "weekly packed calendar inferred from month/day progression; year epoch unknown"},
        "feasibility": "L", "converter_built": False, "runtime_in_game_proved": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    data = roster.read_source(args.source)
    report = probe(data)
    report["source_path"] = str(args.source)
    assert roster.read_source(args.source) == data
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("xb") as stream:
        stream.write((json.dumps(report, indent=2, sort_keys=True) + "\n").encode())
    print(f"SEASON_PROBE_PASS offset=0x350 prefix=848 trailer=69600 banks={len(report['banks'])} converter=no")


if __name__ == "__main__":
    main()
