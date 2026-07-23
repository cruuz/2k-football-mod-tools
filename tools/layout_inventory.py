#!/usr/bin/env python3
"""Inventory the shared Visual Concepts LAYT linked-record format.

APF 2K8 stores big-endian LAYT bodies inside its IFF DRAM blocks.  NFL 2K5
stores little-endian LAYT objects behind the common 0x20-byte resource wrapper.
The record payloads evolved, but both generations use bounded self-relative
linked records and expose template/instance names.  This tool parses only the
relationships proven by the complete local corpora; opaque words remain raw.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Iterable

import apf_inner
import apf_outer
from nfl_outer import parse_archive as parse_nfl_archive
from nfl_outer import read_entry_range
from nfl_scene_probe import decode_resource, parse_inventory


SCHEMA = "vc_cross_title_layout_inventory/v1"
APF_HEADER_TAG = 0x99F822C1
APF_RECORD_SIZES = {0: 0x70, 1: 0x30, 2: 0x30, 3: 0x40}
NFL_RECORD_SIZES = {0: 0x60, 1: 0x30, 2: 0x30}
MAX_RECORDS = 100_000


class LayoutError(ValueError):
    """A declared LAYT relationship was inconsistent or out of bounds."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def u32(data: bytes, offset: int, endian: str, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise LayoutError(f"{what}: u32 at 0x{offset:x} is out of bounds")
    return struct.unpack_from(endian + "I", data, offset)[0]


def relative(
    data: bytes,
    field: int,
    endian: str,
    what: str,
    *,
    allow_null: bool = True,
) -> int | None:
    raw = u32(data, field, endian, what)
    if raw == 0:
        if allow_null:
            return None
        raise LayoutError(f"{what}: null relative pointer at 0x{field:x}")
    signed = raw if raw < 0x80000000 else raw - 0x100000000
    target = field - 1 + signed
    if not 0 <= target < len(data):
        raise LayoutError(
            f"{what}: relative 0x{raw:08x} at 0x{field:x} resolves to "
            f"0x{target:x}, outside 0x{len(data):x} bytes"
        )
    return target


def utf16z(data: bytes, offset: int, encoding: str, what: str) -> str:
    if offset & 1:
        raise LayoutError(f"{what}: UTF-16 string starts at odd offset 0x{offset:x}")
    cursor = offset
    while cursor + 2 <= len(data):
        if data[cursor : cursor + 2] == b"\0\0":
            try:
                value = data[offset:cursor].decode(encoding)
            except UnicodeDecodeError as exc:
                raise LayoutError(f"{what}: invalid {encoding} string") from exc
            if any(ord(character) < 0x20 for character in value):
                raise LayoutError(f"{what}: control character in {value!r}")
            return value
        cursor += 2
    raise LayoutError(f"{what}: unterminated UTF-16 string at 0x{offset:x}")


def optional_name(
    data: bytes,
    field: int,
    endian: str,
    encoding: str,
    what: str,
) -> tuple[int | None, str | None]:
    target = relative(data, field, endian, what)
    if target is None:
        return None, None
    value = utf16z(data, target, encoding, what)
    return target, value or None


def candidate_name(
    data: bytes,
    field: int,
    endian: str,
    encoding: str,
) -> tuple[int | None, str | None]:
    """Return a string only when an otherwise variant field proves one.

    Some record variants reuse the same word for a scalar.  A failed pointer
    or UTF-16 check is therefore a raw-field outcome, not a malformed record.
    """
    try:
        target = relative(data, field, endian, "candidate name")
        if target is None:
            return None, None
        value = utf16z(data, target, encoding, "candidate name")
    except LayoutError:
        return None, None
    return (target, value) if value else (None, None)


def raw_words(data: bytes, offset: int, size: int, endian: str) -> list[str]:
    return [
        f"0x{u32(data, offset + word, endian, 'record raw word'):08x}"
        for word in range(0, size, 4)
    ]


def parse_chain(
    data: bytes,
    head: int | None,
    endian: str,
    encoding: str,
    sizes: dict[int, int],
    platform: str,
    identity: dict[str, object],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[int] = set()
    offset = head
    while offset is not None:
        if len(records) >= MAX_RECORDS:
            raise LayoutError(f"{platform}: record chain exceeds {MAX_RECORDS}")
        if offset in seen:
            raise LayoutError(f"{platform}: linked-record cycle at 0x{offset:x}")
        seen.add(offset)
        record_type = u32(data, offset + 4, endian, "record type")
        size = sizes.get(record_type)
        if size is None:
            raise LayoutError(
                f"{platform}: PORTME unknown record type {record_type} at 0x{offset:x}"
            )
        if offset + size > len(data):
            raise LayoutError(
                f"{platform}: type {record_type} record 0x{offset:x}+0x{size:x} "
                f"exceeds 0x{len(data):x} bytes"
            )
        next_offset = relative(data, offset, endian, "record next")
        if next_offset is not None and next_offset != offset + size:
            raise LayoutError(
                f"{platform}: type {record_type} next 0x{next_offset:x} != "
                f"adjacent expected 0x{offset + size:x}"
            )

        names: dict[str, object] = {}
        if platform == "apf2k8":
            if record_type in (0, 2):
                target, value = optional_name(
                    data, offset + 0x20, endian, encoding, "record primary name"
                )
                names["primary_name_offset"] = target
                names["primary_name"] = value
            if record_type == 0:
                target, value = candidate_name(
                    data, offset + 0x4C, endian, encoding
                )
                names["owner_name_offset"] = target
                names["owner_name"] = value
        else:
            target, value = optional_name(
                data, offset + 0x08, endian, encoding, "record source name"
            )
            names["source_name_offset"] = target
            names["source_name"] = value
            # XBE relocator 0x001690B0 fixes +0x20 for type 0 and the
            # default/type-2 path, but deliberately skips it for type 1.
            target, value = (
                optional_name(
                    data, offset + 0x20, endian, encoding,
                    "record instance name",
                )
                if record_type != 1
                else (None, None)
            )
            names["instance_name_offset"] = target
            names["instance_name"] = value

        record = {
            **identity,
            "record_index": len(records),
            "record_offset": offset,
            "record_type": record_type,
            "record_size": size,
            "next_offset": next_offset,
            "id_or_hash_08": f"0x{u32(data, offset + 8, endian, 'record id/hash'):08x}",
            **names,
            "raw_words": raw_words(data, offset, size, endian),
        }
        records.append(record)
        offset = next_offset
    return records


def read_apf_part(
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
        raise LayoutError("APF LAYT part exceeds decoded block")
    return decoded[part.offset:end]


def parse_apf(index: Path, maximum: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    archive = apf_outer.parse_archive(index)
    layouts: list[dict[str, object]] = []
    all_records: list[dict[str, object]] = []
    with apf_inner.ArchiveReader(archive) as reader:
        for entry in archive.entries:
            if entry.head_hex != "ff3bef94":
                continue
            iff = apf_inner.parse_iff(reader, entry)
            cache: dict[int, bytes] = {}
            for item in iff.files:
                if item.type_name != "LAYT":
                    continue
                if len(item.parts) != 1:
                    raise LayoutError(
                        f"APF {entry.table_index}:{item.index}: expected one LAYT part, "
                        f"found {len(item.parts)}"
                    )
                data = read_apf_part(reader, iff, item.parts[0], cache, maximum)
                if len(data) < 0x40:
                    raise LayoutError("APF LAYT is shorter than its 0x40-byte header")
                if u32(data, 0, ">", "APF header tag") != APF_HEADER_TAG:
                    raise LayoutError("APF LAYT header tag is not 0x99f822c1")
                if any(data[offset : offset + 4] != b"\0\0\0\0" for offset in range(4, 0x40, 4) if offset != 8):
                    raise LayoutError("APF LAYT reserved header word is nonzero")
                head = relative(data, 8, ">", "APF record head", allow_null=False)
                identity = {
                    "platform": "apf2k8",
                    "outer_index": entry.table_index,
                    "inner_index": item.index,
                    "layout_name": item.name,
                }
                records = parse_chain(
                    data, head, ">", "utf-16be", APF_RECORD_SIZES,
                    "apf2k8", identity,
                )
                layouts.append(
                    {
                        **identity,
                        "byte_size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "header_offset": 0,
                        "record_head_offset": head,
                        "record_count": len(records),
                        "record_type_counts": dict(
                            sorted(Counter(str(row["record_type"]) for row in records).items())
                        ),
                    }
                )
                all_records.extend(records)
    return layouts, all_records


def parse_nfl(
    index: Path, resource_scan: Path
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    inventory, resources = parse_inventory(resource_scan)
    selected = [item for item in resources if item.kind == "LAYT"]
    declared = int(inventory["summary"]["resource_kind_counts"]["LAYT"])
    if len(selected) != declared:
        raise LayoutError(f"NFL inventory selected {len(selected)} LAYT, declares {declared}")
    archive = parse_nfl_archive(index)
    layouts: list[dict[str, object]] = []
    all_records: list[dict[str, object]] = []
    for item in selected:
        entry = archive.entries[item.outer_index]
        span = read_entry_range(
            archive, entry, item.chunk_offset, 0x20 + item.stored_size
        )
        data, detail = decode_resource(span, item)
        if len(data) < 0x18 or data[0x0C:0x10] != b"LAYT":
            raise LayoutError(
                f"NFL {item.outer_index}:{item.chunk_index}: missing inner LAYT marker"
            )
        name_offset = relative(data, 0x10, "<", "NFL layout name", allow_null=False)
        assert name_offset is not None
        name = utf16z(data, name_offset, "utf-16le", "NFL layout name")
        descriptor = relative(data, 0x14, "<", "NFL descriptor", allow_null=False)
        assert descriptor is not None
        if descriptor + 8 > len(data):
            raise LayoutError("NFL LAYT descriptor is truncated")
        if u32(data, descriptor, "<", "NFL descriptor reserved") != 0:
            raise LayoutError("NFL LAYT descriptor +0 is nonzero")
        head = relative(data, descriptor + 4, "<", "NFL record head")
        identity = {
            "platform": "nfl2k5",
            "outer_index": item.outer_index,
            "inner_index": item.chunk_index,
            "layout_name": name,
        }
        records = parse_chain(
            data, head, "<", "utf-16le", NFL_RECORD_SIZES,
            "nfl2k5", identity,
        )
        layouts.append(
            {
                **identity,
                "byte_size": len(data),
                "sha256": detail["decoded_sha256"],
                "header_offset": 0,
                "name_offset": name_offset,
                "descriptor_offset": descriptor,
                "record_head_offset": head,
                "record_count": len(records),
                "record_type_counts": dict(
                    sorted(Counter(str(row["record_type"]) for row in records).items())
                ),
            }
        )
        all_records.extend(records)
    return layouts, all_records


def record_names(records: Iterable[dict[str, object]]) -> set[str]:
    result: set[str] = set()
    for record in records:
        for key in ("primary_name", "owner_name", "source_name", "instance_name"):
            value = record.get(key)
            if isinstance(value, str) and value:
                result.add(value.casefold())
    return result


def write_tsv(path: Path, records: list[dict[str, object]]) -> None:
    fields = [
        "platform", "outer_index", "inner_index", "layout_name", "record_index",
        "record_offset", "record_type", "record_size", "next_offset", "id_or_hash_08",
        "primary_name", "owner_name", "source_name", "instance_name", "raw_words",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    **record,
                    "raw_words": ",".join(record["raw_words"]),
                }
            )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--apf-index", type=Path, required=True)
    result.add_argument("--nfl-index", type=Path, required=True)
    result.add_argument(
        "--nfl-resource-scan", type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    result.add_argument("--json", type=Path, required=True)
    result.add_argument("--tsv", type=Path, required=True)
    result.add_argument("--max-decompressed", type=int, default=64 * 1024 * 1024)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.max_decompressed <= 0:
        raise LayoutError("--max-decompressed must be positive")
    apf_layouts, apf_records = parse_apf(args.apf_index, args.max_decompressed)
    nfl_layouts, nfl_records = parse_nfl(args.nfl_index, args.nfl_resource_scan)
    apf_names = record_names(apf_records)
    nfl_names = record_names(nfl_records)
    shared = sorted(apf_names & nfl_names)
    all_records = apf_records + nfl_records
    summary = {
        "apf_layout_count": len(apf_layouts),
        "apf_record_count": len(apf_records),
        "apf_record_type_counts": dict(
            sorted(Counter(str(row["record_type"]) for row in apf_records).items())
        ),
        "nfl_layout_count": len(nfl_layouts),
        "nfl_record_count": len(nfl_records),
        "nfl_record_type_counts": dict(
            sorted(Counter(str(row["record_type"]) for row in nfl_records).items())
        ),
        "apf_distinct_record_name_count": len(apf_names),
        "nfl_distinct_record_name_count": len(nfl_names),
        "shared_casefolded_record_name_count": len(shared),
        "all_links_adjacent_and_bounded": True,
        "all_known_record_types_sized": True,
    }
    report = {
        "schema": SCHEMA,
        "sources": {
            "apf_index": str(args.apf_index),
            "apf_index_sha256": sha256_file(args.apf_index),
            "nfl_index": str(args.nfl_index),
            "nfl_index_sha256": sha256_file(args.nfl_index),
            "nfl_resource_scan": str(args.nfl_resource_scan),
            "nfl_resource_scan_sha256": sha256_file(args.nfl_resource_scan),
        },
        "constants": {
            "relative_pointer": "target = pointer_field_offset - 1 + signed_stored_value",
            "apf_endianness": "big",
            "apf_header_size": 0x40,
            "apf_header_tag": "0x99f822c1",
            "apf_record_sizes": {str(key): value for key, value in APF_RECORD_SIZES.items()},
            "nfl_endianness": "little",
            "nfl_inner_marker_offset": 0x0C,
            "nfl_record_sizes": {str(key): value for key, value in NFL_RECORD_SIZES.items()},
        },
        "executable_evidence": {
            "nfl_type_registration": "default.xbe:0x001691A0 registers scalar LAYT with loader 0x00169160",
            "nfl_relocator": "default.xbe:0x001690B0 fixes descriptor +0x04, every record +0x00/+0x08, and +0x20 except type 1",
            "nfl_consumer_example": "default.xbe:0x0006A880 requests espn_background and team_background as LAYT",
            "apf_type_hash": "CRC32('LAYT') = 0x86a1ac9e",
            "apf_asset_lookup": "default.xex:0x84B16398 is called with DRAM hash 0xbb05a9c1, logical-name hash, and LAYT hash 0x86a1ac9e",
        },
        "summary": summary,
        "shared_casefolded_record_names": shared,
        "portme": [
            "PORTME: name record types and remaining words from executable consumers.",
            "PORTME: prove parent/ownership and coordinate semantics before constructing editable menu scenes.",
            "PORTME: recover event bindings, localization IDs, visibility conditions, and round-trip serialization.",
        ],
        "layouts": apf_layouts + nfl_layouts,
        "records": all_records,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(args.tsv, all_records)
    print(
        "LAYOUT_INVENTORY_COMPLETE "
        f"apf={len(apf_layouts)}/{len(apf_records)} "
        f"nfl={len(nfl_layouts)}/{len(nfl_records)} shared_names={len(shared)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, LayoutError, apf_inner.FormatError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
