#!/usr/bin/env python3
"""Parse APF 2K8's two ``TXT loc system`` localization resources.

The format is a compact big-endian, sorted ID table followed by a deduplicated
UTF-16BE pool.  This reader is deliberately strict: every ordinary record must
resolve to an exact pool boundary, while the one observed ``0xffffffff``
control record is retained as opaque data instead of being misreported as a
pointer.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import zlib
from pathlib import Path

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_inner
import apf_outer


SCHEMA = "apf2k8_txt_localization/v1"
TYPE_NAME = "TXT loc system"
TYPE_HASH = zlib.crc32(TYPE_NAME.encode("ascii")) & 0xFFFFFFFF
EXPECTED_LANGUAGE_ID = zlib.crc32(b"English") & 0xFFFFFFFF
CONTROL_ID = 0xFFFFFFFF


class TextError(ValueError):
    """A declared localization relationship is malformed or out of bounds."""


def u32(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise TextError(f"{what}: u32 at 0x{offset:x} is out of bounds")
    return struct.unpack_from(">I", data, offset)[0]


def relative(data: bytes, field: int, what: str) -> tuple[int, int]:
    raw = u32(data, field, what)
    if raw == 0:
        raise TextError(f"{what}: null pointer at 0x{field:x}")
    signed = raw if raw < 0x80000000 else raw - 0x100000000
    target = field - 1 + signed
    if not 0 <= target < len(data):
        raise TextError(
            f"{what}: relative 0x{raw:08x} at 0x{field:x} resolves to "
            f"0x{target:x}, outside 0x{len(data):x} bytes"
        )
    return raw, target


def utf16z(data: bytes, offset: int, what: str) -> tuple[str, int]:
    if offset & 1:
        raise TextError(f"{what}: odd UTF-16BE offset 0x{offset:x}")
    cursor = offset
    while cursor + 2 <= len(data):
        if data[cursor : cursor + 2] == b"\0\0":
            try:
                value = data[offset:cursor].decode("utf-16be")
            except UnicodeDecodeError as exc:
                raise TextError(f"{what}: invalid UTF-16BE") from exc
            return value, cursor + 2
        cursor += 2
    raise TextError(f"{what}: unterminated UTF-16BE string at 0x{offset:x}")


def read_part(
    reader: apf_inner.ArchiveReader,
    record: apf_inner.IFFRecord,
    part: apf_inner.FilePart,
    cache: dict[int, bytes],
    maximum: int,
) -> bytes:
    block = record.blocks[part.block_index]
    if not block.is_compressed:
        return reader.read(record.entry, block.start_offset + part.offset, part.length)
    if part.block_index not in cache:
        cache[part.block_index] = apf_inner.decode_block(
            reader, record, part.block_index, maximum
        )
    decoded = cache[part.block_index]
    end = part.offset + part.length
    if end > len(decoded):
        raise TextError("TXT part exceeds its decoded block")
    return decoded[part.offset:end]


def parse_body(
    body: bytes,
    *,
    outer_index: int,
    inner_index: int,
    inner_name: str,
    inner_file_id: int,
) -> dict[str, object]:
    if len(body) < 12 or len(body) & 1:
        raise TextError(f"{inner_name}: invalid even body length {len(body)}")
    language_id = u32(body, 0, "language ID")
    count = u32(body, 4, "record count")
    if language_id != EXPECTED_LANGUAGE_ID:
        raise TextError(
            f"{inner_name}: language ID 0x{language_id:08x} is not CRC32('English')"
        )
    _, records_offset = relative(body, 8, "record-array pointer")
    if records_offset != 12:
        raise TextError(
            f"{inner_name}: record array starts at 0x{records_offset:x}, expected 0xc"
        )
    pool_offset = records_offset + count * 8
    if pool_offset > len(body):
        raise TextError(f"{inner_name}: record array exceeds body")

    pool: list[dict[str, object]] = []
    boundary_to_index: dict[int, int] = {}
    cursor = pool_offset
    while cursor < len(body):
        start = cursor
        text, cursor = utf16z(body, cursor, f"{inner_name} pool entry")
        boundary_to_index[start] = len(pool)
        pool.append(
            {
                "pool_index": len(pool),
                "offset": start,
                "text": text,
                "utf16be_sha256": hashlib.sha256(
                    text.encode("utf-16be") + b"\0\0"
                ).hexdigest(),
            }
        )
    if cursor != len(body) or not pool:
        raise TextError(f"{inner_name}: incomplete or empty string pool")
    if pool[0]["text"] != "INVALID TEXT":
        raise TextError(f"{inner_name}: first pool entry is not the fallback text")

    records: list[dict[str, object]] = []
    previous_id = -1
    referenced: set[int] = set()
    control_count = 0
    for index in range(count):
        offset = records_offset + index * 8
        text_id = u32(body, offset, "text ID")
        raw = u32(body, offset + 4, "text pointer/control word")
        if text_id <= previous_id:
            raise TextError(
                f"{inner_name}: IDs are not strictly sorted at record {index}"
            )
        previous_id = text_id
        row: dict[str, object] = {
            "outer_index": outer_index,
            "inner_index": inner_index,
            "table_name": inner_name,
            "record_index": index,
            "record_offset": offset,
            "text_id": f"0x{text_id:08x}",
            "raw_text_relative_or_control": f"0x{raw:08x}",
            "is_control_record": False,
            "text_offset": None,
            "pool_index": None,
            "text": None,
        }
        try:
            _, target = relative(body, offset + 4, "text pointer")
        except TextError:
            if text_id != CONTROL_ID:
                raise
            row["is_control_record"] = True
            control_count += 1
        else:
            pool_index = boundary_to_index.get(target)
            if pool_index is None:
                raise TextError(
                    f"{inner_name}: record {index} points to non-pool boundary 0x{target:x}"
                )
            row["text_offset"] = target
            row["pool_index"] = pool_index
            row["text"] = pool[pool_index]["text"]
            referenced.add(pool_index)
        records.append(row)

    unreferenced = sorted(set(range(len(pool))) - referenced)
    if unreferenced != [0]:
        raise TextError(
            f"{inner_name}: expected only fallback pool entry to be unreferenced, got {unreferenced}"
        )
    return {
        "outer_index": outer_index,
        "inner_index": inner_index,
        "inner_name": inner_name,
        "inner_file_id": f"0x{inner_file_id:08x}",
        "inner_name_crc32": f"0x{zlib.crc32(inner_name.encode('ascii')) & 0xffffffff:08x}",
        "body_size": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "language_id": f"0x{language_id:08x}",
        "language_name": "English",
        "record_count": count,
        "records_offset": records_offset,
        "pool_offset": pool_offset,
        "pool_entry_count": len(pool),
        "referenced_pool_entry_count": len(referenced),
        "control_record_count": control_count,
        "unreferenced_pool_indices": unreferenced,
        "records": records,
        "pool": pool,
        "_body": body,
    }


def rebuild_table(table: dict[str, object]) -> bytes:
    result = bytearray()
    result.extend(struct.pack(">I", int(str(table["language_id"]), 16)))
    records = table["records"]
    pool = table["pool"]
    assert isinstance(records, list) and isinstance(pool, list)
    result.extend(struct.pack(">I", len(records)))
    records_offset = int(table["records_offset"])
    result.extend(struct.pack(">I", records_offset - 8 + 1))
    pool_offsets = {int(row["pool_index"]): int(row["offset"]) for row in pool}
    for row in records:
        assert isinstance(row, dict)
        result.extend(struct.pack(">I", int(str(row["text_id"]), 16)))
        if bool(row["is_control_record"]):
            raw = int(str(row["raw_text_relative_or_control"]), 16)
        else:
            field = len(result)
            target = pool_offsets[int(row["pool_index"])]
            raw = (target - field + 1) & 0xFFFFFFFF
        result.extend(struct.pack(">I", raw))
    for row in pool:
        assert isinstance(row, dict)
        result.extend(str(row["text"]).encode("utf-16be"))
        result.extend(b"\0\0")
    return bytes(result)


def parse_archive(index: Path, maximum: int) -> list[dict[str, object]]:
    archive = apf_outer.parse_archive(index)
    tables: list[dict[str, object]] = []
    with apf_inner.ArchiveReader(archive) as reader:
        for entry in archive.entries:
            if entry.head_hex != "ff3bef94":
                continue
            record = apf_inner.parse_iff(reader, entry)
            cache: dict[int, bytes] = {}
            for item in record.files:
                if item.type_name != TYPE_NAME:
                    continue
                if item.type_hash != TYPE_HASH or item.name is None:
                    raise TextError("TXT resource has inconsistent name/type metadata")
                if len(item.parts) != 1:
                    raise TextError(
                        f"{item.name}: expected one DRAM part, found {len(item.parts)}"
                    )
                body = read_part(reader, record, item.parts[0], cache, maximum)
                table = parse_body(
                    body,
                    outer_index=entry.table_index,
                    inner_index=item.index,
                    inner_name=item.name,
                    inner_file_id=item.file_id,
                )
                table["byte_identical_rebuild"] = rebuild_table(table) == body
                if not table["byte_identical_rebuild"]:
                    raise TextError(f"{item.name}: serializer did not reproduce body")
                tables.append(table)
    tables.sort(key=lambda row: (int(row["outer_index"]), int(row["inner_index"])))
    if len(tables) != 2:
        raise TextError(f"expected two TXT localization resources, found {len(tables)}")
    return tables


def public_table(table: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in table.items() if key != "_body"}


def write_tsv(path: Path, tables: list[dict[str, object]]) -> None:
    fields = [
        "outer_index", "inner_index", "table_name", "record_index",
        "record_offset", "text_id", "raw_text_relative_or_control",
        "is_control_record", "text_offset", "pool_index", "text",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        for table in tables:
            writer.writerows(table["records"])


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to APF 0A")
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    parser.add_argument(
        "--strg-report",
        type=Path,
        default=Path("reports/assets/cross_title_string_tables.json"),
    )
    parser.add_argument("--max-decompressed", type=int, default=64 * 1024 * 1024)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    tables = parse_archive(args.index, args.max_decompressed)
    strg_texts: set[str] = set()
    if args.strg_report.is_file():
        strg = json.loads(args.strg_report.read_text(encoding="utf-8"))
        strg_texts = {str(row["text"]) for row in strg["primary_translation"]}
    all_records = [row for table in tables for row in table["records"]]
    all_pool = [row for table in tables for row in table["pool"]]
    table_intersections = {
        str(table["inner_name"]): len(
            {str(row["text"]) for row in table["pool"]} & strg_texts
        )
        for table in tables
    }
    report = {
        "schema": SCHEMA,
        "source": {
            "index": str(args.index),
            "index_sha256": hashlib.sha256(args.index.read_bytes()).hexdigest(),
            "strg_report": str(args.strg_report),
        },
        "constants": {
            "endianness": "big",
            "record_stride": 8,
            "relative_pointer": "target = pointer_field_offset - 1 + signed_stored_value",
            "type_name": TYPE_NAME,
            "type_crc32": f"0x{TYPE_HASH:08x}",
            "english_crc32": f"0x{EXPECTED_LANGUAGE_ID:08x}",
        },
        "summary": {
            "table_count": len(tables),
            "record_count": len(all_records),
            "ordinary_record_count": sum(not row["is_control_record"] for row in all_records),
            "control_record_count": sum(bool(row["is_control_record"]) for row in all_records),
            "pool_entry_count": len(all_pool),
            "distinct_text_count": len({str(row["text"]) for row in all_pool}),
            "all_ids_strictly_sorted_and_unique": True,
            "all_ordinary_references_bounded": True,
            "only_fallback_entries_unreferenced": True,
            "all_bodies_rebuild_byte_identically": True,
            "primary_strg_distinct_text_count": len(strg_texts),
            "strg_intersection_by_table": table_intersections,
        },
        "executable_evidence": {
            "language_path_selector": (
                "default.xex:0x84761868 maps CRC32 language IDs to English/French/"
                "German/Italian/Spanish suffix strings"
            ),
            "english_request": (
                "default.xex:0x84691C68 requests resource ID 0xe33e3b9c, "
                "CRC32('English')"
            ),
            "structural_relocator_candidate": (
                "default.xex:0x84761A08 relocates a root +0x08 array pointer and "
                "8-byte records at +0x04; the English 0xffffffff control row "
                "still requires an ownership/special-case trace"
            ),
        },
        "portme": [
            "PORTME: recover the source-key semantics and generation algorithm for each text_id.",
            "PORTME: trace the 0xffffffff English control row and its opaque 0x0c192401 word.",
            "PORTME: prove the exact lookup/collision consumer and fallback selection path.",
            "PORTME: implement size-changing archive import only after IFF ownership and dependent references are proved.",
        ],
        "tables": [public_table(table) for table in tables],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(args.tsv, tables)
    print(
        "APF_TXT_LOCALIZATION_COMPLETE "
        f"tables={len(tables)} records={len(all_records)} pool={len(all_pool)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TextError, apf_inner.FormatError, apf_outer.FormatError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
