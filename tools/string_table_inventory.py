#!/usr/bin/env python3
"""Parse and cross-reference the Visual Concepts STRG string-table format.

APF 2K8 stores a compact big-endian body directly in an IFF DRAM part.
NFL 2K5 stores a little-endian body behind the common resource wrapper.  The
formats use different pointer encodings, but their 1,492-record primary banks
contain the same ordered text and therefore provide an exact ID translation.

Only relationships proven by the bounded local corpora are named.  In
particular, the two 32-bit lookup fields remain ``id_a`` and ``id_b`` until
their source-key/hash semantics are recovered from executable consumers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import apf_inner
import apf_outer
from nfl_outer import parse_archive as parse_nfl_archive
from nfl_outer import read_entry_range
from nfl_scene_probe import ProbeError, ResourceRecord, decode_resource, parse_inventory


SCHEMA = "vc_cross_title_string_tables/v1"
APF_VERSION = 5
RECORD_SIZE = 0x0C
MAX_RECORDS = 1_000_000


class StringTableError(ValueError):
    """A declared STRG relationship was malformed or outside its body."""


@dataclass(frozen=True)
class PoolEntry:
    index: int
    offset: int
    end_offset: int
    text: str


@dataclass(frozen=True)
class StringRecord:
    index: int
    offset: int
    id_a: int
    id_b: int
    stored_reference: int
    text_offset: int
    pool_index: int
    text: str


@dataclass
class ParsedTable:
    platform: str
    outer_index: int
    inner_index: int
    name: str
    body: bytes
    count: int
    version: int | None
    encoding: str
    descriptor_offset: int
    record_table_offset: int
    text_pool_offset: int
    text_pool_end: int
    pool: list[PoolEntry]
    records: list[StringRecord]
    trailer: bytes
    outer_id: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_u32(data: bytes, offset: int, endian: str, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise StringTableError(f"{what}: u32 at 0x{offset:x} is out of bounds")
    return struct.unpack_from(endian + "I", data, offset)[0]


def checked_i32(data: bytes, offset: int, endian: str, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise StringTableError(f"{what}: i32 at 0x{offset:x} is out of bounds")
    return struct.unpack_from(endian + "i", data, offset)[0]


def relative_target(data: bytes, field: int, endian: str, what: str) -> int:
    stored = checked_i32(data, field, endian, what)
    target = field - 1 + stored
    if not 0 <= target < len(data):
        raise StringTableError(
            f"{what}: relative {stored:+#x} at 0x{field:x} resolves to "
            f"0x{target:x}, outside 0x{len(data):x} bytes"
        )
    return target


def utf16z(data: bytes, offset: int, encoding: str, what: str) -> tuple[str, int]:
    if offset < 0 or offset + 2 > len(data) or offset & 1:
        raise StringTableError(f"{what}: invalid UTF-16 offset 0x{offset:x}")
    cursor = offset
    while cursor + 2 <= len(data):
        if data[cursor : cursor + 2] == b"\0\0":
            try:
                return data[offset:cursor].decode(encoding), cursor + 2
            except UnicodeDecodeError as exc:
                raise StringTableError(
                    f"{what}: invalid {encoding} at 0x{offset:x}"
                ) from exc
        cursor += 2
    raise StringTableError(f"{what}: unterminated UTF-16 string at 0x{offset:x}")


def parse_pool(
    data: bytes,
    pool_offset: int,
    referenced: dict[int, tuple[str, int]],
    encoding: str,
    what: str,
) -> tuple[list[PoolEntry], int, bytes]:
    if not referenced:
        return [], pool_offset, data[pool_offset:]
    if min(referenced) < pool_offset:
        raise StringTableError(
            f"{what}: a text reference precedes pool offset 0x{pool_offset:x}"
        )
    pool_end = max(end for _text, end in referenced.values())
    if pool_end > len(data):
        raise StringTableError(f"{what}: string pool exceeds body")

    pool: list[PoolEntry] = []
    cursor = pool_offset
    while cursor < pool_end:
        text, end = utf16z(data, cursor, encoding, f"{what} pool entry")
        pool.append(PoolEntry(len(pool), cursor, end, text))
        cursor = end
    if cursor != pool_end:
        raise StringTableError(f"{what}: string pool does not end on a string boundary")
    starts = {item.offset for item in pool}
    if set(referenced) != starts:
        missing = sorted(starts - set(referenced))
        interior = sorted(set(referenced) - starts)
        raise StringTableError(
            f"{what}: pool/reference disagreement; unreferenced starts={missing[:8]}, "
            f"non-start targets={interior[:8]}"
        )
    for item in pool:
        text, end = referenced[item.offset]
        if text != item.text or end != item.end_offset:
            raise StringTableError(f"{what}: inconsistent text at 0x{item.offset:x}")
    return pool, pool_end, data[pool_end:]


def parse_apf_body(
    data: bytes, outer_index: int, inner_index: int, name: str
) -> ParsedTable:
    if len(data) < 8:
        raise StringTableError("APF STRG is shorter than its 8-byte header")
    count, version = struct.unpack_from(">II", data)
    if count > MAX_RECORDS:
        raise StringTableError(f"APF STRG declares excessive count {count}")
    if version != APF_VERSION:
        raise StringTableError(
            f"APF STRG version {version} is not proven version {APF_VERSION}"
        )
    table_offset = 8
    pool_offset = table_offset + count * RECORD_SIZE
    if pool_offset > len(data):
        raise StringTableError("APF STRG record table exceeds body")

    preliminary: list[tuple[int, int, int, int, int, str]] = []
    referenced: dict[int, tuple[str, int]] = {}
    for index in range(count):
        offset = table_offset + index * RECORD_SIZE
        id_a, id_b = struct.unpack_from(">II", data, offset)
        stored = checked_i32(data, offset + 8, ">", "APF text pointer")
        target = offset + 7 + stored
        if target < pool_offset or target >= len(data):
            raise StringTableError(
                f"APF record {index}: text target 0x{target:x} is outside pool/body"
            )
        text, end = utf16z(data, target, "utf-16be", f"APF record {index} text")
        prior = referenced.setdefault(target, (text, end))
        if prior != (text, end):
            raise StringTableError(f"APF record {index}: shared pointer disagrees")
        preliminary.append((offset, id_a, id_b, stored, target, text))

    pool, pool_end, trailer = parse_pool(
        data, pool_offset, referenced, "utf-16be", "APF STRG"
    )
    pool_by_offset = {item.offset: item.index for item in pool}
    records = [
        StringRecord(
            index=index,
            offset=row[0],
            id_a=row[1],
            id_b=row[2],
            stored_reference=row[3] & 0xFFFFFFFF,
            text_offset=row[4],
            pool_index=pool_by_offset[row[4]],
            text=row[5],
        )
        for index, row in enumerate(preliminary)
    ]
    return ParsedTable(
        platform="apf2k8",
        outer_index=outer_index,
        inner_index=inner_index,
        name=name,
        body=data,
        count=count,
        version=version,
        encoding="utf-16be",
        descriptor_offset=0,
        record_table_offset=table_offset,
        text_pool_offset=pool_offset,
        text_pool_end=pool_end,
        pool=pool,
        records=records,
        trailer=trailer,
    )


def parse_nfl_body(data: bytes, record: ResourceRecord) -> ParsedTable:
    if len(data) < 0x34:
        raise StringTableError("NFL STRG is shorter than its inner header")
    if data[0x0C:0x10] != b"STRG":
        raise StringTableError("NFL STRG inner marker is missing at +0x0c")
    name_offset = relative_target(data, 0x10, "<", "NFL STRG name")
    descriptor = relative_target(data, 0x14, "<", "NFL STRG descriptor")
    name, name_end = utf16z(data, name_offset, "utf-16le", "NFL STRG name")
    if name_end > descriptor:
        raise StringTableError("NFL STRG name overlaps descriptor")

    # Both complete on-disc objects have a reserved-zero prefix.  Reconstruct
    # it rather than silently retaining unknown bytes, so byte equality is an
    # independent check of the understood header fields.
    expected_prefix = bytearray(descriptor)
    expected_prefix[0x0C:0x10] = b"STRG"
    struct.pack_into("<i", expected_prefix, 0x10, name_offset - (0x10 - 1))
    struct.pack_into("<i", expected_prefix, 0x14, descriptor - (0x14 - 1))
    encoded_name = name.encode("utf-16le") + b"\0\0"
    expected_prefix[name_offset : name_offset + len(encoded_name)] = encoded_name
    if data[:descriptor] != expected_prefix:
        raise StringTableError(
            "NFL STRG has nonzero/unknown bytes in the proven inner-header prefix"
        )

    count = checked_u32(data, descriptor, "<", "NFL STRG count")
    if count > MAX_RECORDS:
        raise StringTableError(f"NFL STRG declares excessive count {count}")
    table_offset = descriptor + 4
    pool_offset = table_offset + count * RECORD_SIZE
    if pool_offset > len(data):
        raise StringTableError("NFL STRG record table exceeds body")

    preliminary: list[tuple[int, int, int, int, int, str]] = []
    referenced: dict[int, tuple[str, int]] = {}
    for index in range(count):
        offset = table_offset + index * RECORD_SIZE
        id_a, id_b, code_units = struct.unpack_from("<III", data, offset)
        target = pool_offset + code_units * 2
        if target < pool_offset or target >= len(data):
            raise StringTableError(
                f"NFL record {index}: text target 0x{target:x} is outside pool/body"
            )
        text, end = utf16z(data, target, "utf-16le", f"NFL record {index} text")
        prior = referenced.setdefault(target, (text, end))
        if prior != (text, end):
            raise StringTableError(f"NFL record {index}: shared offset disagrees")
        preliminary.append((offset, id_a, id_b, code_units, target, text))

    pool, pool_end, trailer = parse_pool(
        data, pool_offset, referenced, "utf-16le", "NFL STRG"
    )
    pool_by_offset = {item.offset: item.index for item in pool}
    records = [
        StringRecord(
            index=index,
            offset=row[0],
            id_a=row[1],
            id_b=row[2],
            stored_reference=row[3],
            text_offset=row[4],
            pool_index=pool_by_offset[row[4]],
            text=row[5],
        )
        for index, row in enumerate(preliminary)
    ]
    return ParsedTable(
        platform="nfl2k5",
        outer_index=record.outer_index,
        inner_index=record.chunk_index,
        name=name,
        body=data,
        count=count,
        version=None,
        encoding="utf-16le",
        descriptor_offset=descriptor,
        record_table_offset=table_offset,
        text_pool_offset=pool_offset,
        text_pool_end=pool_end,
        pool=pool,
        records=records,
        trailer=trailer,
        outer_id=record.outer_id,
    )


def rebuild_table(table: ParsedTable) -> bytes:
    """Serialize every understood field and preserve only the bounded trailer."""
    pool_offsets: list[int] = []
    encoded_pool: list[bytes] = []
    cursor = table.text_pool_offset
    for item in table.pool:
        encoded = item.text.encode(table.encoding) + b"\0\0"
        pool_offsets.append(cursor)
        encoded_pool.append(encoded)
        cursor += len(encoded)

    if table.platform == "apf2k8":
        output = bytearray(struct.pack(">II", table.count, table.version))
        output.extend(b"\0" * (table.count * RECORD_SIZE))
        for row in table.records:
            offset = table.record_table_offset + row.index * RECORD_SIZE
            target = pool_offsets[row.pool_index]
            relative = target - (offset + 8 - 1)
            struct.pack_into(">IIi", output, offset, row.id_a, row.id_b, relative)
    elif table.platform == "nfl2k5":
        output = bytearray(table.descriptor_offset)
        output[0x0C:0x10] = b"STRG"
        name_offset = 0x20
        encoded_name = table.name.encode("utf-16le") + b"\0\0"
        if name_offset + len(encoded_name) > table.descriptor_offset:
            raise StringTableError("NFL STRG name no longer fits header prefix")
        struct.pack_into("<i", output, 0x10, name_offset - (0x10 - 1))
        struct.pack_into(
            "<i", output, 0x14, table.descriptor_offset - (0x14 - 1)
        )
        output[name_offset : name_offset + len(encoded_name)] = encoded_name
        output.extend(struct.pack("<I", table.count))
        output.extend(b"\0" * (table.count * RECORD_SIZE))
        for row in table.records:
            offset = table.record_table_offset + row.index * RECORD_SIZE
            target = pool_offsets[row.pool_index]
            delta = target - table.text_pool_offset
            if delta & 1:
                raise StringTableError("NFL text offset is not in UTF-16 code units")
            struct.pack_into(
                "<III", output, offset, row.id_a, row.id_b, delta // 2
            )
    else:
        raise StringTableError(f"unsupported platform {table.platform}")

    if len(output) != table.text_pool_offset:
        raise StringTableError(
            f"rebuilder reached 0x{len(output):x}, expected pool 0x{table.text_pool_offset:x}"
        )
    for encoded in encoded_pool:
        output.extend(encoded)
    output.extend(table.trailer)
    return bytes(output)


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
        raise StringTableError("APF STRG part exceeds decoded block")
    return decoded[part.offset:end]


def parse_apf(index: Path, maximum: int) -> list[ParsedTable]:
    archive = apf_outer.parse_archive(index)
    tables: list[ParsedTable] = []
    with apf_inner.ArchiveReader(archive) as reader:
        for entry in archive.entries:
            if entry.head_hex != "ff3bef94":
                continue
            iff = apf_inner.parse_iff(reader, entry)
            cache: dict[int, bytes] = {}
            for item in iff.files:
                if item.type_name != "STRG":
                    continue
                if len(item.parts) != 1:
                    raise StringTableError(
                        f"APF {entry.table_index}:{item.index}: expected one STRG "
                        f"part, found {len(item.parts)}"
                    )
                body = read_apf_part(reader, iff, item.parts[0], cache, maximum)
                tables.append(
                    parse_apf_body(
                        body, entry.table_index, item.index, item.name or ""
                    )
                )
    return tables


def parse_nfl(index: Path, resource_scan: Path) -> list[ParsedTable]:
    inventory, resources = parse_inventory(resource_scan)
    selected = [item for item in resources if item.kind == "STRG"]
    declared = int(inventory["summary"]["resource_kind_counts"]["STRG"])
    if len(selected) != declared:
        raise StringTableError(
            f"NFL inventory selected {len(selected)} STRG, declares {declared}"
        )
    archive = parse_nfl_archive(index)
    tables: list[ParsedTable] = []
    for item in selected:
        entry = archive.entries[item.outer_index]
        span = read_entry_range(
            archive, entry, item.chunk_offset, 0x20 + item.stored_size
        )
        body, _detail = decode_resource(span, item)
        tables.append(parse_nfl_body(body, item))
    return tables


def hex32(value: int) -> str:
    return f"0x{value:08x}"


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def table_json(table: ParsedTable) -> dict[str, object]:
    pool_texts = [item.text for item in table.pool]
    result: dict[str, object] = {
        "platform": table.platform,
        "outer_index": table.outer_index,
        "inner_index": table.inner_index,
        "name": table.name,
        "byte_size": len(table.body),
        "sha256": hashlib.sha256(table.body).hexdigest(),
        "encoding": table.encoding,
        "count": table.count,
        "descriptor_offset": table.descriptor_offset,
        "record_table_offset": table.record_table_offset,
        "record_size": RECORD_SIZE,
        "text_pool_offset": table.text_pool_offset,
        "text_pool_end": table.text_pool_end,
        "pool_entry_count": len(table.pool),
        "distinct_text_count": len(set(pool_texts)),
        "trailer_size": len(table.trailer),
        "trailer_hex": table.trailer.hex(),
        "byte_identical_rebuild": rebuild_table(table) == table.body,
        "pool": [
            {
                "index": item.index,
                "offset": item.offset,
                "end_offset": item.end_offset,
                "sha256_utf8": text_digest(item.text),
                "text": item.text,
            }
            for item in table.pool
        ],
        "records": [
            {
                "index": row.index,
                "offset": row.offset,
                "id_a": hex32(row.id_a),
                "id_b": hex32(row.id_b),
                "stored_text_reference": hex32(row.stored_reference),
                "text_offset": row.text_offset,
                "pool_index": row.pool_index,
                "sha256_utf8": text_digest(row.text),
                "text": row.text,
            }
            for row in table.records
        ],
    }
    if table.version is not None:
        result["version"] = table.version
    if table.outer_id is not None:
        result["outer_id"] = table.outer_id
    return result


def one_to_one_map(
    left: Iterable[int], right: Iterable[int], what: str
) -> list[dict[str, object]]:
    forward: dict[int, set[int]] = defaultdict(set)
    reverse: dict[int, set[int]] = defaultdict(set)
    occurrences: Counter[int] = Counter()
    for source, target in zip(left, right, strict=True):
        forward[source].add(target)
        reverse[target].add(source)
        occurrences[source] += 1
    if any(len(values) != 1 for values in forward.values()) or any(
        len(values) != 1 for values in reverse.values()
    ):
        raise StringTableError(f"{what}: cross-title mapping is not bijective")
    return [
        {
            "apf": hex32(source),
            "nfl": hex32(next(iter(forward[source]))),
            "record_occurrences": occurrences[source],
        }
        for source in sorted(forward)
    ]


def pair_bijection(
    apf_records: list[StringRecord], nfl_records: list[StringRecord]
) -> list[dict[str, object]]:
    forward: dict[tuple[int, int], set[tuple[int, int]]] = defaultdict(set)
    reverse: dict[tuple[int, int], set[tuple[int, int]]] = defaultdict(set)
    occurrences: Counter[tuple[int, int]] = Counter()
    for apf, nfl in zip(apf_records, nfl_records, strict=True):
        source = (apf.id_a, apf.id_b)
        target = (nfl.id_a, nfl.id_b)
        forward[source].add(target)
        reverse[target].add(source)
        occurrences[source] += 1
    if any(len(values) != 1 for values in forward.values()) or any(
        len(values) != 1 for values in reverse.values()
    ):
        raise StringTableError("cross-title ID-pair mapping is not bijective")
    result: list[dict[str, object]] = []
    for source in sorted(forward):
        target = next(iter(forward[source]))
        result.append(
            {
                "apf_id_a": hex32(source[0]),
                "apf_id_b": hex32(source[1]),
                "nfl_id_a": hex32(target[0]),
                "nfl_id_b": hex32(target[1]),
                "record_occurrences": occurrences[source],
            }
        )
    return result


def translation_rows(
    apf: ParsedTable, nfl: ParsedTable
) -> list[dict[str, object]]:
    pair_totals = Counter((row.id_a, row.id_b) for row in apf.records)
    seen: Counter[tuple[int, int]] = Counter()
    rows: list[dict[str, object]] = []
    for apf_row, nfl_row in zip(apf.records, nfl.records, strict=True):
        if apf_row.text != nfl_row.text:
            raise StringTableError(
                f"main string record {apf_row.index} differs across titles"
            )
        pair = (apf_row.id_a, apf_row.id_b)
        variant = seen[pair]
        seen[pair] += 1
        rows.append(
            {
                "record_index": apf_row.index,
                "variant_ordinal": variant,
                "variant_count": pair_totals[pair],
                "apf_id_a": hex32(apf_row.id_a),
                "apf_id_b": hex32(apf_row.id_b),
                "nfl_id_a": hex32(nfl_row.id_a),
                "nfl_id_b": hex32(nfl_row.id_b),
                "apf_text_offset": apf_row.text_offset,
                "nfl_text_offset": nfl_row.text_offset,
                "pool_index": apf_row.pool_index,
                "sha256_utf8": text_digest(apf_row.text),
                "text": apf_row.text,
            }
        )
    return rows


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "record_index",
        "variant_ordinal",
        "variant_count",
        "apf_id_a",
        "apf_id_b",
        "nfl_id_a",
        "nfl_id_b",
        "apf_text_offset",
        "nfl_text_offset",
        "pool_index",
        "sha256_utf8",
        "text",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, dialect="excel-tab", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def select_primary(tables: list[ParsedTable], platform: str) -> ParsedTable:
    candidates = [table for table in tables if table.count == 1492]
    if len(candidates) != 1:
        raise StringTableError(
            f"{platform}: expected one 1,492-record primary STRG, found {len(candidates)}"
        )
    return candidates[0]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--apf-index", type=Path, required=True)
    result.add_argument("--nfl-index", type=Path, required=True)
    result.add_argument(
        "--nfl-resource-scan",
        type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    result.add_argument(
        "--nfl-xbe",
        type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"),
    )
    result.add_argument("--json", type=Path, required=True)
    result.add_argument("--tsv", type=Path, required=True)
    result.add_argument("--max-decompressed", type=int, default=64 * 1024 * 1024)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.max_decompressed <= 0:
        raise StringTableError("--max-decompressed must be positive")
    apf_tables = parse_apf(args.apf_index, args.max_decompressed)
    nfl_tables = parse_nfl(args.nfl_index, args.nfl_resource_scan)
    if len(apf_tables) != 2 or len(nfl_tables) != 2:
        raise StringTableError(
            f"expected two STRG tables per title; APF={len(apf_tables)} NFL={len(nfl_tables)}"
        )
    for table in apf_tables + nfl_tables:
        if rebuild_table(table) != table.body:
            raise StringTableError(
                f"{table.platform} {table.outer_index}:{table.inner_index}: "
                "serialized body is not byte-identical"
            )

    apf_primary = select_primary(apf_tables, "APF")
    nfl_primary = select_primary(nfl_tables, "NFL")
    translations = translation_rows(apf_primary, nfl_primary)
    apf_pool_texts = [item.text for item in apf_primary.pool]
    nfl_pool_texts = [item.text for item in nfl_primary.pool]
    if apf_pool_texts != nfl_pool_texts:
        raise StringTableError("primary deduplicated string pools differ across titles")

    id_a_map = one_to_one_map(
        (row.id_a for row in apf_primary.records),
        (row.id_a for row in nfl_primary.records),
        "id_a",
    )
    id_b_map = one_to_one_map(
        (row.id_b for row in apf_primary.records),
        (row.id_b for row in nfl_primary.records),
        "id_b",
    )
    pair_map = pair_bijection(apf_primary.records, nfl_primary.records)
    apf_id_a = {row.id_a for row in apf_primary.records}
    nfl_id_a = {row.id_a for row in nfl_primary.records}
    apf_id_b = {row.id_b for row in apf_primary.records}
    nfl_id_b = {row.id_b for row in nfl_primary.records}

    summary = {
        "apf_table_count": len(apf_tables),
        "apf_record_count": sum(table.count for table in apf_tables),
        "nfl_table_count": len(nfl_tables),
        "nfl_record_count": sum(table.count for table in nfl_tables),
        "primary_record_count": len(translations),
        "primary_ordered_text_match_count": len(translations),
        "primary_ordered_texts_identical": True,
        "primary_pool_entry_count": len(apf_pool_texts),
        "primary_pools_identical": True,
        "primary_distinct_id_a_count": len(id_a_map),
        "primary_distinct_id_b_count": len(id_b_map),
        "primary_distinct_id_pair_count": len(pair_map),
        "id_a_mapping_bijective": True,
        "id_b_mapping_bijective": True,
        "id_pair_mapping_bijective": True,
        "shared_numeric_id_a_count": len(apf_id_a & nfl_id_a),
        "shared_numeric_id_b_count": len(apf_id_b & nfl_id_b),
        "all_references_bounded": True,
        "all_string_pools_contiguous_and_fully_referenced": True,
        "all_bodies_rebuild_byte_identically": True,
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
            "nfl_xbe": str(args.nfl_xbe),
            "nfl_xbe_sha256": sha256_file(args.nfl_xbe),
        },
        "constants": {
            "record_size": RECORD_SIZE,
            "apf_endianness": "big",
            "apf_encoding": "UTF-16BE",
            "apf_version": APF_VERSION,
            "apf_pointer_rule": "target = pointer_field_offset - 1 + signed_stored_value",
            "nfl_endianness": "little",
            "nfl_encoding": "UTF-16LE",
            "nfl_inner_marker_offset": 0x0C,
            "nfl_text_rule": "target = text_pool_base + stored_code_unit_offset * 2",
        },
        "executable_evidence": {
            "nfl_registration": (
                "default.xbe:0x00169270 registers FourCC STRG with loader "
                "callback 0x00169210 and callbacks 0x00169250/0x00169260"
            ),
            "nfl_lookup": (
                "default.xbe:0x001692D0 finds matching id_a/id_b records, "
                "selects variant modulo match count, and returns "
                "text_pool_base + offset_code_units*2"
            ),
            "nfl_resource_body_callback": (
                "default.xbe:0x00169250 returns input + 0x20, matching the "
                "common outer resource-wrapper size"
            ),
        },
        "summary": summary,
        "id_a_bijection": id_a_map,
        "id_b_bijection": id_b_map,
        "id_pair_bijection": pair_map,
        "primary_translation": translations,
        "portme": [
            "PORTME: recover the source-key/hash semantics of id_a and id_b from producer and consumer code.",
            "PORTME: recover safe ID generation, collision policy, and resource registration before importing edited strings.",
            "PORTME: parse the separate APF 'TXT loc system' resources; they are not STRG objects.",
            "PORTME: implement a round-trip localization writer only after ID ownership and cross-resource references are proven.",
        ],
        "tables": [table_json(table) for table in apf_tables + nfl_tables],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_tsv(args.tsv, translations)
    print(
        "STRING_TABLE_INVENTORY_COMPLETE "
        f"apf={len(apf_tables)}/{sum(table.count for table in apf_tables)} "
        f"nfl={len(nfl_tables)}/{sum(table.count for table in nfl_tables)} "
        f"matched={len(translations)} pool={len(apf_pool_texts)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        StringTableError,
        ProbeError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        struct.error,
    ) as exc:
        raise SystemExit(f"error: {exc}") from exc
