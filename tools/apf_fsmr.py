#!/usr/bin/env python3
"""Strictly inventory APF 2K8's sole FSMR/crowdren1 resource.

The resource is structured, big-endian numeric data.  Its first two words are
one-based field-relative pointers, not a count and an offset.  This tool keeps
all unproved record fields mechanically named and emits no writer.

// PORTME: identify every 0x20-byte table-A field and 0x10-byte table-B field
//         from exact rendering consumers or controlled-difference samples.
// PORTME: implement a reversible writer only after table cardinality,
//         allocation, archive recompression, and integrity rules are proved.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Iterable

import apf_inner
import apf_outer


OUTER_TABLE_INDEX = 659
OUTER_NAME_ID = 0x6CB47FC1
INNER_INDEX = 109
INNER_NAME = "crowdren1"
INNER_TYPE = "FSMR"
EXPECTED_LENGTH = 0x700
EXPECTED_SHA256 = "0b6dd34a79201186db707f38e72ceda4033f3bdc3a63b040cfa6b4626a46f4b4"
TABLE_A_STRIDE = 0x20
TABLE_B_STRIDE = 0x10
EXPECTED_TABLE_A_OFFSET = 0x08
EXPECTED_TABLE_B_OFFSET = 0x3C8
EXPECTED_TABLE_A_COUNT = 30
EXPECTED_TABLE_B_NONZERO_COUNT = 47
EXPECTED_TABLE_B_NONZERO_END = 0x6B8


class FsmrError(ValueError):
    """Raised when the supplied FSMR resource violates a proved invariant."""


def _hex(value: int, width: int = 8) -> str:
    return f"0x{value:0{width}x}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _u32be(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise FsmrError(f"{what} at 0x{offset:x} is outside the resource")
    return struct.unpack_from(">I", data, offset)[0]


def _signed32(value: int) -> int:
    return value if value < 0x80000000 else value - 0x1_0000_0000


def resolve_relative(data: bytes, field_offset: int, what: str) -> int:
    stored = _u32be(data, field_offset, what)
    target = field_offset + _signed32(stored) - 1
    if target < 0 or target >= len(data):
        raise FsmrError(
            f"{what} at 0x{field_offset:x} resolves to 0x{target:x}, "
            f"outside 0x0..0x{len(data) - 1:x}"
        )
    return target


def load_fsmr(index_path: Path) -> tuple[bytes, dict[str, object]]:
    archive = apf_outer.parse_archive(index_path)
    matches = [
        entry for entry in archive.entries if entry.table_index == OUTER_TABLE_INDEX
    ]
    if len(matches) != 1:
        raise FsmrError(f"expected one outer table entry {OUTER_TABLE_INDEX}")
    entry = matches[0]
    if entry.name_id != OUTER_NAME_ID:
        raise FsmrError(
            f"outer name ID {_hex(entry.name_id)} != {_hex(OUTER_NAME_ID)}"
        )

    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        if record.warnings:
            raise FsmrError(f"gamedata IFF has warnings: {record.warnings}")
        matches = [item for item in record.files if item.index == INNER_INDEX]
        if len(matches) != 1:
            raise FsmrError(f"expected one inner file {INNER_INDEX}")
        inner = matches[0]
        if inner.name != INNER_NAME or inner.type_name != INNER_TYPE:
            raise FsmrError(
                f"inner file is {inner.name!r}/{inner.type_name!r}, "
                f"expected {INNER_NAME}/{INNER_TYPE}"
            )
        if len(inner.parts) != 1 or inner.parts[0].block_index != 0:
            raise FsmrError("FSMR is not one bounded block-0 DRAM part")
        block = apf_inner.decode_block(
            reader, record, inner.parts[0].block_index, 64 * 1024 * 1024
        )
        part = inner.parts[0]
        data = block[part.offset : part.offset + part.length]
        outer_raw = reader.read(entry, 0, entry.size)

    if len(data) != EXPECTED_LENGTH:
        raise FsmrError(
            f"decoded FSMR length 0x{len(data):x}, expected 0x{EXPECTED_LENGTH:x}"
        )
    if _sha256(data) != EXPECTED_SHA256:
        raise FsmrError("decoded FSMR SHA-256 does not match the supplied US disc")
    return data, {
        "index_path": str(index_path),
        "outer_table_index": entry.table_index,
        "outer_name_id": _hex(entry.name_id),
        "outer_stored_size": entry.size,
        "outer_stored_sha256": _sha256(outer_raw),
        "inner_index": inner.index,
        "inner_name": inner.name,
        "inner_type": inner.type_name,
        "part_block_index": part.block_index,
        "part_offset": part.offset,
        "decoded_length": len(data),
        "decoded_sha256": _sha256(data),
    }


def _float32(word: int) -> float:
    return struct.unpack(">f", struct.pack(">I", word))[0]


def _record(
    data: bytes, index: int, offset: int, stride: int, *, float_words: int
) -> dict[str, object]:
    words = struct.unpack_from(f">{stride // 4}I", data, offset)
    floats = [_float32(word) for word in words[:float_words]]
    if not all(math.isfinite(value) for value in floats):
        raise FsmrError(f"record {index} at 0x{offset:x} has a non-finite float")
    raw = data[offset : offset + stride]
    return {
        "index": index,
        "offset": _hex(offset, 4),
        "be_words": [_hex(word) for word in words],
        "float32_interpretations": floats,
        "raw_sha256": _sha256(raw),
    }


def parse_fsmr(data: bytes) -> dict[str, object]:
    table_a = resolve_relative(data, 0, "root pointer A")
    table_b = resolve_relative(data, 4, "root pointer B")
    if table_a != EXPECTED_TABLE_A_OFFSET or table_b != EXPECTED_TABLE_B_OFFSET:
        raise FsmrError(
            f"root targets are 0x{table_a:x}/0x{table_b:x}, expected "
            f"0x{EXPECTED_TABLE_A_OFFSET:x}/0x{EXPECTED_TABLE_B_OFFSET:x}"
        )
    if (table_b - table_a) % TABLE_A_STRIDE:
        raise FsmrError("table A does not end on a 0x20-byte record boundary")
    table_a_count = (table_b - table_a) // TABLE_A_STRIDE
    if table_a_count != EXPECTED_TABLE_A_COUNT:
        raise FsmrError(f"table A has {table_a_count} records")

    records_a = [
        _record(data, index, table_a + index * TABLE_A_STRIDE, TABLE_A_STRIDE,
                float_words=3)
        for index in range(table_a_count)
    ]
    if any(record["be_words"][7] != "0x00000000" for record in records_a):
        raise FsmrError("table-A word 7 is not uniformly zero")

    cursor = table_b
    while cursor + TABLE_B_STRIDE <= len(data):
        chunk = data[cursor : cursor + TABLE_B_STRIDE]
        if not any(chunk):
            break
        cursor += TABLE_B_STRIDE
    if cursor != EXPECTED_TABLE_B_NONZERO_END:
        raise FsmrError(
            f"table-B nonzero prefix ends at 0x{cursor:x}, expected "
            f"0x{EXPECTED_TABLE_B_NONZERO_END:x}"
        )
    if any(data[cursor:]):
        raise FsmrError("bytes after the table-B nonzero prefix are not all zero")
    table_b_count = (cursor - table_b) // TABLE_B_STRIDE
    if table_b_count != EXPECTED_TABLE_B_NONZERO_COUNT:
        raise FsmrError(f"table B has {table_b_count} nonzero records")
    records_b = [
        _record(data, index, table_b + index * TABLE_B_STRIDE, TABLE_B_STRIDE,
                float_words=3)
        for index in range(table_b_count)
    ]
    if any(record["be_words"][2] != "0x3f800000" for record in records_b):
        raise FsmrError("table-B word 2 is not uniformly float 1.0")

    return {
        "pointer_rule": "target = pointer_field_offset + signed_be32(stored_value) - 1",
        "root": {
            "size": 8,
            "pointers": [
                {
                    "field_offset": "0x0000",
                    "stored_value": _hex(_u32be(data, 0, "root pointer A")),
                    "target": _hex(table_a, 4),
                    "target_label": "table_a",
                },
                {
                    "field_offset": "0x0004",
                    "stored_value": _hex(_u32be(data, 4, "root pointer B")),
                    "target": _hex(table_b, 4),
                    "target_label": "table_b",
                },
            ],
        },
        "table_a": {
            "offset": _hex(table_a, 4),
            "end": _hex(table_b, 4),
            "stride": TABLE_A_STRIDE,
            "record_count": table_a_count,
            "sha256": _sha256(data[table_a:table_b]),
            "proved_fields": {
                "word_00_to_02": (
                    "finite big-endian float32 values consumed by 0x84758dc8; "
                    "words 1-2 form a randomized range"
                ),
                "bytes_0c_to_0f": (
                    "four selector bytes indexed by the evaluator's bounded 0..3 result"
                ),
                "bytes_10_to_13": (
                    "four unsigned weights summed for the evaluator's random choice"
                ),
                "bytes_14_to_1b": (
                    "eight transition bytes; 0xff is skipped, bit 7 and low 7 bits are consumed separately"
                ),
                "word_07": "zero in every supplied record",
                "domain_meanings": "unresolved; structural access is proved but editor labels are not",
            },
            "records": records_a,
        },
        "table_b": {
            "offset": _hex(table_b, 4),
            "nonzero_end": _hex(cursor, 4),
            "stride": TABLE_B_STRIDE,
            "nonzero_record_count": table_b_count,
            "zero_tail_offset": _hex(cursor, 4),
            "zero_tail_length": len(data) - cursor,
            "sha256_nonzero_prefix": _sha256(data[table_b:cursor]),
            "proved_fields": {
                "word_00_to_01": (
                    "finite big-endian float32 values consumed as evaluator state values"
                ),
                "word_02": (
                    "float32 1.0 in every supplied record and consumed as a per-step multiplier"
                ),
                "word_03": "raw packed word; exact domain meaning remains unresolved",
            },
            "records": records_b,
        },
    }


def build_report(data: bytes, source: dict[str, object]) -> dict[str, object]:
    parsed = parse_fsmr(data)
    return {
        "schema": "apf_fsmr_inventory/v1",
        "source": source,
        **parsed,
        "summary": {
            "resource_count": 1,
            "root_pointer_count": 2,
            "table_a_record_count": parsed["table_a"]["record_count"],
            "table_b_nonzero_record_count": parsed["table_b"]["nonzero_record_count"],
            "zero_tail_length": parsed["table_b"]["zero_tail_length"],
        },
        "executable_evidence": {
            "type_crc32": "0x31734984",
            "type_registry_address": "0x820d2b74",
            "root_relocator": "0x84979058",
            "root_unrelocator": "0x84979100",
            "destructor_callback": "0x849791b0",
            "no_op_callback": "0x84b1c718",
            "type_node_constructor": "0x8467d1b8",
            "crowd_resource_true_entry": "0x84975e60",
            "crowd_resource_lookup_name_crc32": "0x4f73c815",
            "crowd_resource_lookup_name": "crowdren1",
            "counted_pointer_pair_initializer": "0x84759478",
            "table_evaluator_true_entry": "0x84758dc8",
            "observed_runtime_contract": (
                "the crowd loader retrieves crowdren1 with the FSMR registry descriptor, "
                "then passes the resource's two relocated root words to 0x84759478"
            ),
        },
        "classification": {
            "result": "finite structured crowd-renderer state/transition configuration, not a script VM",
            "confidence": "high for structured/non-script classification; low for field names",
            "evidence": [
                "one named FSMR resource exists and is named crowdren1",
                "the root is exactly two self-relative pointers into bounded fixed-width tables",
                "the body contains only big-endian numeric/packed records and a zero tail",
                "the XEX looks it up from crowd initialization and feeds both pointers to a runtime table object",
                "the focused evaluator indexes table A at stride 0x20 and table B at stride 0x10, performs weighted bounded choices, and follows packed transition bytes",
                "no bytecode dispatcher, opcode stream, script strings, or general script loader was identified",
            ],
        },
        "worked": [
            "decoded the sole FSMR part through the bounded APF IFF/H7A path",
            "proved both root words are one-based self-relative pointers rather than a count/pointer pair",
            "bounded 30 table-A records and the 47-record nonzero table-B prefix",
            "traced the type registry, crowdren1 lookup, pointer-pair initializer, and evaluator lane",
        ],
        "failed": [
            "record words cannot yet be given editor-facing semantic names without consumer-by-consumer or controlled-difference evidence",
            "no safe writer is emitted because allocation/cardinality and archive integrity behavior remain unproved",
        ],
        "portme": [
            "// PORTME: name FSMR table-A words 0x00-0x1c from exact crowd-renderer consumers",
            "// PORTME: name FSMR table-B words 0x00-0x0c and prove its cardinality source",
            "// PORTME: recover source-equivalent control flow for evaluator 0x84758dc8 beyond focused pseudo-C",
            "// PORTME: implement a reversible FSMR writer and H7A/IFF repacker only after capacity and integrity rules are known",
        ],
    }


def write_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _write_tsv(
    path: Path, header: Iterable[str], rows: Iterable[Iterable[object]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def write_table_a(path: Path, records: list[dict[str, object]]) -> None:
    header = ["index", "offset", *[f"word_{n:02d}" for n in range(8)],
              "float_00", "float_01", "float_02", "raw_sha256"]
    rows = [
        [record["index"], record["offset"], *record["be_words"],
         *record["float32_interpretations"], record["raw_sha256"]]
        for record in records
    ]
    _write_tsv(path, header, rows)


def write_table_b(path: Path, records: list[dict[str, object]]) -> None:
    header = ["index", "offset", *[f"word_{n:02d}" for n in range(4)],
              "float_00", "float_01", "float_02", "raw_sha256"]
    rows = [
        [record["index"], record["offset"], *record["be_words"],
         *record["float32_interpretations"], record["raw_sha256"]]
        for record in records
    ]
    _write_tsv(path, header, rows)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to APF first volume (0A)")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--table-a-tsv", type=Path, required=True)
    parser.add_argument("--table-b-tsv", type=Path, required=True)
    parser.add_argument("--dump", type=Path, help="write the exact decoded 0x700-byte body")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        data, source = load_fsmr(args.index)
        report = build_report(data, source)
        write_json(args.report, report)
        write_table_a(args.table_a_tsv, report["table_a"]["records"])
        write_table_b(args.table_b_tsv, report["table_b"]["records"])
        if args.dump is not None:
            args.dump.parent.mkdir(parents=True, exist_ok=True)
            args.dump.write_bytes(data)
    except (FsmrError, apf_inner.FormatError, apf_outer.FormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "APF_FSMR_INVENTORY_COMPLETE "
        f"table_a={report['summary']['table_a_record_count']} "
        f"table_b={report['summary']['table_b_nonzero_record_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
