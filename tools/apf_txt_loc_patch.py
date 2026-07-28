#!/usr/bin/env python3
"""Bounded APF 2K8 localization and string-bank writer.

The retail game owns two ``TXT loc system`` resources and two ``STRG``
resources.  ``apf_txt_loc`` and ``string_table_inventory`` already prove their
table, pointer, and UTF-16BE pool semantics.  This module adds the deliberately
smaller product contract needed by Mod Studio:

* edits address one existing pool allocation by stable outer/inner/pool ID;
* each replacement must fit that string's original UTF-16 allocation;
* record IDs, control rows, sharing, file names, and every unrelated outer
  entry remain unchanged;
* the complete table is serialized again so relative pointers stay correct;
* the containing H7A/IFF is rebuilt inside its original outer allocation.

It returns replacement entry bytes in memory.  It never opens a retail volume
for writing and it never embeds retail or replacement bytes in its manifest.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import struct
from typing import Mapping

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
import apf_texture_patch
import apf_txt_loc
import string_table_inventory


SCHEMA = "apf2k8_txt_localization_patch/v1"
EDIT_ID_PREFIX = "apf:text-pool"
MAX_DECOMPRESSED = 256 * 1024 * 1024

# Source-derived structural pins, not retail payloads.  They keep this writer
# on the four proved English string banks instead of silently treating
# arbitrary IFF data as localization.
TXT_TARGETS: Mapping[int, tuple[int, str]] = {
    526: (0, "credits_English"),
    1127: (0, "English"),
}
STRG_TARGETS: Mapping[int, tuple[int, str]] = {
    185: (20, "artist_bio_english"),
    810: (87, "strings"),
}
TABLE_TARGETS: Mapping[int, tuple[int, str]] = {
    **STRG_TARGETS,
    **TXT_TARGETS,
}
H7A_STRING_BANK_CANDIDATES = 1536


class TextPatchError(ValueError):
    """A text edit cannot be applied under the bounded product contract."""


@dataclass(frozen=True)
class TextAllocation:
    asset_id: str
    outer_index: int
    inner_index: int
    table_name: str
    pool_index: int
    text: str
    allocation_bytes: int
    maximum_utf16_units: int
    reference_count: int
    editable: bool
    note: str


@dataclass(frozen=True)
class TextPatchResult:
    outer_index: int
    entry_bytes: bytes
    manifest: Mapping[str, object]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _asset_id(outer_index: int, inner_index: int, pool_index: int) -> str:
    return f"{EDIT_ID_PREFIX}:{outer_index}:{inner_index}:{pool_index}"


def parse_asset_id(value: str) -> tuple[int, int, int]:
    fields = value.split(":")
    if len(fields) != 5 or fields[:2] != ["apf", "text-pool"]:
        raise TextPatchError(f"Unknown APF text asset: {value}")
    try:
        outer_index, inner_index, pool_index = map(int, fields[2:])
    except ValueError as exc:
        raise TextPatchError(f"Malformed APF text asset: {value}") from exc
    return outer_index, inner_index, pool_index


def _utf16_units(value: str) -> int:
    if "\0" in value:
        raise TextPatchError("Text cannot contain a NUL character")
    try:
        encoded = value.encode("utf-16be")
    except UnicodeEncodeError as exc:
        raise TextPatchError("Text contains an unsupported Unicode value") from exc
    return len(encoded) // 2


def _allocations_for_table(table: Mapping[str, object]) -> tuple[TextAllocation, ...]:
    pool = table.get("pool")
    records = table.get("records")
    if not isinstance(pool, list) or not isinstance(records, list) or not pool:
        raise TextPatchError("Localization table has no usable string pool")
    outer_index = int(table["outer_index"])
    inner_index = int(table["inner_index"])
    table_name = str(table["inner_name"])
    body_size = int(table["body_size"])
    references: dict[int, int] = {}
    for record in records:
        if not isinstance(record, dict) or record.get("pool_index") is None:
            continue
        index = int(record["pool_index"])
        references[index] = references.get(index, 0) + 1
    result: list[TextAllocation] = []
    for position, row in enumerate(pool):
        if not isinstance(row, dict) or int(row.get("pool_index", -1)) != position:
            raise TextPatchError("Localization pool indices are no longer contiguous")
        start = int(row["offset"])
        end = int(pool[position + 1]["offset"]) if position + 1 < len(pool) else body_size
        allocation = end - start
        text = str(row["text"])
        if allocation != len(text.encode("utf-16be")) + 2 or allocation < 2:
            raise TextPatchError("Localization string allocation changed unexpectedly")
        result.append(
            TextAllocation(
                asset_id=_asset_id(outer_index, inner_index, position),
                outer_index=outer_index,
                inner_index=inner_index,
                table_name=table_name,
                pool_index=position,
                text=text,
                allocation_bytes=allocation,
                maximum_utf16_units=allocation // 2 - 1,
                reference_count=references.get(position, 0),
                editable=position != 0,
                note=(
                    "Special fallback sentinel; kept read-only."
                    if position == 0
                    else (
                        f"Shared by {references.get(position, 0)} localization records."
                        if references.get(position, 0) > 1
                        else "One fixed UTF-16BE pool allocation."
                    )
                ),
            )
        )
    return tuple(result)


def _allocations_for_strg(
    table: string_table_inventory.ParsedTable,
) -> tuple[TextAllocation, ...]:
    if table.platform != "apf2k8" or table.encoding != "utf-16be":
        raise TextPatchError("STRG table is not the proved APF UTF-16BE format")
    if string_table_inventory.rebuild_table(table) != table.body:
        raise TextPatchError("STRG table is not byte-identically serializable")
    references: dict[int, int] = {item.index: 0 for item in table.pool}
    for record in table.records:
        if record.pool_index not in references:
            raise TextPatchError("STRG record points outside its string pool")
        references[record.pool_index] += 1
    result: list[TextAllocation] = []
    for position, row in enumerate(table.pool):
        if row.index != position:
            raise TextPatchError("STRG pool indices are no longer contiguous")
        allocation = row.end_offset - row.offset
        encoded_size = len(row.text.encode("utf-16be")) + 2
        if allocation != encoded_size or allocation < 2:
            raise TextPatchError("STRG string allocation changed unexpectedly")
        maximum = allocation // 2 - 1
        reference_count = references[position]
        editable = maximum > 0
        result.append(
            TextAllocation(
                asset_id=_asset_id(table.outer_index, table.inner_index, position),
                outer_index=table.outer_index,
                inner_index=table.inner_index,
                table_name=table.name,
                pool_index=position,
                text=row.text,
                allocation_bytes=allocation,
                maximum_utf16_units=maximum,
                reference_count=reference_count,
                editable=editable,
                note=(
                    "Zero-capacity empty STRG allocation; kept read-only."
                    if not editable
                    else (
                        f"Shared by {reference_count} STRG records."
                        if reference_count > 1
                        else "One fixed UTF-16BE STRG pool allocation."
                    )
                ),
            )
        )
    return tuple(result)


def inventory(index_path: Path) -> tuple[TextAllocation, ...]:
    """Return every underlying TXT-localization and STRG pool allocation."""

    try:
        txt_tables = apf_txt_loc.parse_archive(index_path, MAX_DECOMPRESSED)
        strg_tables = string_table_inventory.parse_apf(index_path, MAX_DECOMPRESSED)
    except (
        OSError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        apf_txt_loc.TextError,
        string_table_inventory.StringTableError,
    ) as exc:
        raise TextPatchError(f"Could not read APF text banks: {exc}") from exc
    txt_found = {
        int(table["outer_index"]): (int(table["inner_index"]), str(table["inner_name"]))
        for table in txt_tables
    }
    strg_found = {
        table.outer_index: (table.inner_index, table.name) for table in strg_tables
    }
    if txt_found != dict(TXT_TARGETS):
        raise TextPatchError(f"APF TXT-localization targets changed: {txt_found}")
    if strg_found != dict(STRG_TARGETS):
        raise TextPatchError(f"APF STRG targets changed: {strg_found}")
    rows = [
        *(item for table in txt_tables for item in _allocations_for_table(table)),
        *(item for table in strg_tables for item in _allocations_for_strg(table)),
    ]
    return tuple(sorted(rows, key=lambda item: parse_asset_id(item.asset_id)))


def validate_replacement(allocation: TextAllocation, replacement: str) -> int:
    """Validate one replacement and return its UTF-16 code-unit count."""

    if not allocation.editable and replacement != allocation.text:
        raise TextPatchError(
            f"{allocation.table_name} pool {allocation.pool_index} is read-only: "
            f"{allocation.note}"
        )
    units = _utf16_units(replacement)
    if units > allocation.maximum_utf16_units:
        raise TextPatchError(
            f"{allocation.table_name} pool {allocation.pool_index} accepts at most "
            f"{allocation.maximum_utf16_units} UTF-16 characters; this text needs {units}. "
            "Most ordinary letters count as one character."
        )
    return units


def _edited_body(
    table: Mapping[str, object], replacements: Mapping[int, str]
) -> tuple[bytes, tuple[dict[str, object], ...]]:
    allocations = {item.pool_index: item for item in _allocations_for_table(table)}
    edited = deepcopy(dict(table))
    pool = edited.get("pool")
    if not isinstance(pool, list):
        raise TextPatchError("Localization pool changed unexpectedly")
    rows: list[dict[str, object]] = []
    for pool_index, value in sorted(replacements.items()):
        allocation = allocations.get(pool_index)
        if allocation is None:
            raise TextPatchError(
                f"{table['inner_name']} has no pool allocation {pool_index}"
            )
        if not isinstance(value, str):
            raise TextPatchError(f"Replacement for {allocation.asset_id} is not text")
        units = validate_replacement(allocation, value)
        before = str(pool[pool_index]["text"])
        pool[pool_index]["text"] = value
        rows.append(
            {
                "asset_id": allocation.asset_id,
                "pool_index": pool_index,
                "reference_count": allocation.reference_count,
                "allocation_bytes": allocation.allocation_bytes,
                "maximum_utf16_units": allocation.maximum_utf16_units,
                "replacement_utf16_units": units,
                "original_text_sha256": _sha256(before.encode("utf-8")),
                "replacement_text_sha256": _sha256(value.encode("utf-8")),
            }
        )
    records = edited.get("records")
    if not isinstance(records, list):
        raise TextPatchError("Localization records changed unexpectedly")
    cursor = int(edited["records_offset"]) + len(records) * 8
    for pool_row in pool:
        if not isinstance(pool_row, dict):
            raise TextPatchError("Localization pool row changed unexpectedly")
        pool_row["offset"] = cursor
        cursor += len(str(pool_row["text"]).encode("utf-16be")) + 2
    edited["body_size"] = cursor
    body = apf_txt_loc.rebuild_table(edited)
    if len(body) > int(table["body_size"]):
        raise TextPatchError("Edited localization table exceeded its proved allocation")
    try:
        reparsed = apf_txt_loc.parse_body(
            body,
            outer_index=int(table["outer_index"]),
            inner_index=int(table["inner_index"]),
            inner_name=str(table["inner_name"]),
            inner_file_id=int(str(table["inner_file_id"]), 16),
        )
    except apf_txt_loc.TextError as exc:
        raise TextPatchError(f"Edited localization table is invalid: {exc}") from exc
    for pool_index, replacement in replacements.items():
        if str(reparsed["pool"][pool_index]["text"]) != replacement:
            raise TextPatchError("Localization serialize/parse round trip changed an edit")
    return body, tuple(rows)


def _edited_strg_body(
    table: string_table_inventory.ParsedTable,
    replacements: Mapping[int, str],
) -> tuple[bytes, tuple[dict[str, object], ...]]:
    """Rebuild one APF STRG body at its exact original byte length."""

    allocations = {item.pool_index: item for item in _allocations_for_strg(table)}
    edited = deepcopy(table)
    pool = list(edited.pool)
    rows: list[dict[str, object]] = []
    for pool_index, value in sorted(replacements.items()):
        allocation = allocations.get(pool_index)
        if allocation is None:
            raise TextPatchError(f"{table.name} has no pool allocation {pool_index}")
        if not isinstance(value, str):
            raise TextPatchError(f"Replacement for {allocation.asset_id} is not text")
        units = validate_replacement(allocation, value)
        before = pool[pool_index].text
        pool[pool_index] = replace(pool[pool_index], text=value)
        rows.append(
            {
                "asset_id": allocation.asset_id,
                "pool_index": pool_index,
                "reference_count": allocation.reference_count,
                "allocation_bytes": allocation.allocation_bytes,
                "maximum_utf16_units": allocation.maximum_utf16_units,
                "replacement_utf16_units": units,
                "original_text_sha256": _sha256(before.encode("utf-8")),
                "replacement_text_sha256": _sha256(value.encode("utf-8")),
            }
        )
    if any(table.trailer):
        raise TextPatchError("STRG has an opaque nonzero trailer and is read-only")
    edited.pool = pool
    edited.trailer = table.trailer
    draft = string_table_inventory.rebuild_table(edited)
    if len(draft) > len(table.body):
        raise TextPatchError("Edited STRG exceeded its proved fixed allocation")
    edited.trailer = b"\0" * (
        len(table.trailer) + len(table.body) - len(draft)
    )
    body = string_table_inventory.rebuild_table(edited)
    if len(body) != len(table.body):
        raise TextPatchError("Edited STRG did not retain its exact body allocation")
    try:
        reparsed = string_table_inventory.parse_apf_body(
            body,
            table.outer_index,
            table.inner_index,
            table.name,
        )
    except string_table_inventory.StringTableError as exc:
        raise TextPatchError(f"Edited STRG is invalid: {exc}") from exc
    if string_table_inventory.rebuild_table(reparsed) != body:
        raise TextPatchError("Edited STRG is not byte-stable after reparsing")
    for pool_index, replacement in replacements.items():
        if reparsed.pool[pool_index].text != replacement:
            raise TextPatchError("STRG serialize/parse round trip changed an edit")
    return body, tuple(rows)


def _file_part_hashes(
    record: apf_inner.IFFRecord,
    blocks: list[bytes],
) -> dict[tuple[int, int], str]:
    result: dict[tuple[int, int], str] = {}
    for item in record.files:
        for part_index, part in enumerate(item.parts):
            payload = blocks[part.block_index][part.offset : part.offset + part.length]
            result[(item.index, part_index)] = _sha256(payload)
    return result


def _build_strg_patch(
    index_path: Path,
    outer_index: int,
    replacements: Mapping[int, str],
) -> TextPatchResult:
    expected_inner, expected_name = STRG_TARGETS[outer_index]
    try:
        archive = apf_outer.parse_archive(index_path)
        tables = string_table_inventory.parse_apf(index_path, MAX_DECOMPRESSED)
    except (
        OSError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        string_table_inventory.StringTableError,
    ) as exc:
        raise TextPatchError(f"Could not read APF STRG: {exc}") from exc
    table = next(
        (item for item in tables if item.outer_index == outer_index),
        None,
    )
    if table is None:
        raise TextPatchError(f"APF STRG table {outer_index} is missing")
    if table.inner_index != expected_inner or table.name != expected_name:
        raise TextPatchError("APF STRG table identity changed")
    body, edit_rows = _edited_strg_body(table, replacements)

    entry = archive.entries[outer_index]
    if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
        raise TextPatchError("STRG target is no longer one fixed 0A allocation")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        original_blocks = [
            apf_inner.decode_block(reader, record, index, MAX_DECOMPRESSED)
            for index in range(record.block_count)
        ]
        original_stored = [
            reader.read(entry, descriptor.start_offset, descriptor.stored_length)
            for descriptor in record.blocks
        ]
    if record.warnings or record.footer is None:
        raise TextPatchError("STRG container no longer has the proved IFF/footer layout")
    try:
        target = record.files[expected_inner]
    except IndexError as exc:
        raise TextPatchError("STRG inner-file index is missing") from exc
    if (
        target.index != expected_inner
        or target.name != expected_name
        or target.type_name != "STRG"
        or len(target.parts) != 1
    ):
        raise TextPatchError("STRG inner-file ownership changed")
    part = target.parts[0]
    descriptor = record.blocks[part.block_index]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise TextPatchError("STRG owning block is no longer H7A-compressed")
    original_part = original_blocks[part.block_index][
        part.offset : part.offset + part.length
    ]
    if original_part != table.body or len(body) != part.length:
        raise TextPatchError("STRG body no longer matches its owned IFF part")

    if body == original_part:
        return TextPatchResult(
            outer_index,
            original_entry,
            {
                "schema": SCHEMA,
                "mode": "no_op",
                "bank_type": "STRG",
                "outer_index": outer_index,
                "inner_index": expected_inner,
                "table_name": expected_name,
                "edit_count": len(edit_rows),
                "edits": edit_rows,
                "source": {
                    "entry_size": entry.size,
                    "entry_sha256": _sha256(original_entry),
                    "body_size": len(original_part),
                    "body_sha256": _sha256(original_part),
                    "opened_read_only": True,
                },
                "output": {
                    "entry_size": len(original_entry),
                    "entry_sha256": _sha256(original_entry),
                    "body_size": len(body),
                    "body_sha256": _sha256(body),
                    "changed_byte_count": 0,
                    "first_changed_offset": None,
                    "last_changed_offset": None,
                },
                "validation": {
                    "input_matches_source": True,
                    "entry_bit_exact": True,
                    "manifest_contains_retail_or_replacement_bytes": False,
                },
            },
        )

    new_blocks = list(original_blocks)
    changed_block = bytearray(new_blocks[part.block_index])
    changed_block[part.offset : part.offset + part.length] = body
    new_blocks[part.block_index] = bytes(changed_block)
    compressed = apf_texture_patch.compress_h7a(
        new_blocks[part.block_index],
        descriptor.wrapper.shift,
        candidate_limit=H7A_STRING_BANK_CANDIDATES,
    )
    stored = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(new_blocks[part.block_index]),
        apf_inner.H7A_HEADER_SIZE + len(compressed),
        descriptor.unknown_10,
        descriptor.wrapper.shift,
    ) + compressed
    if (
        apf_inner.decompress_h7a(
            compressed,
            len(new_blocks[part.block_index]),
            descriptor.wrapper.shift,
        )
        != new_blocks[part.block_index]
    ):
        raise TextPatchError("STRG H7A round trip failed")
    new_stored = list(original_stored)
    new_stored[part.block_index] = stored

    header = bytearray(original_entry[: record.header_size])
    cursor = record.header_size
    rebuilt_body = bytearray()
    block_rows: list[dict[str, object]] = []
    for block_index, (block_descriptor, block_stored) in enumerate(
        zip(record.blocks, new_stored, strict=True)
    ):
        if (
            not block_descriptor.is_compressed
            and len(block_stored) != block_descriptor.uncompressed_length
        ):
            raise TextPatchError("Uncompressed IFF block allocation changed")
        stored_length = (
            len(block_stored)
            if block_descriptor.is_compressed
            else block_descriptor.uncompressed_length
        )
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE + block_index * apf_inner.IFF_BLOCK_SIZE,
            block_descriptor.name_hash,
            block_descriptor.type_hash,
            block_descriptor.unknown_08,
            block_descriptor.uncompressed_length,
            block_descriptor.unknown_10,
            cursor,
            stored_length,
            block_descriptor.indexed,
        )
        block_rows.append(
            {
                "block_index": block_index,
                "decoded_sha256_before": _sha256(original_blocks[block_index]),
                "decoded_sha256_after": _sha256(new_blocks[block_index]),
                "stored_sha256_before": _sha256(original_stored[block_index]),
                "stored_sha256_after": _sha256(block_stored),
                "stored_length_before": len(original_stored[block_index]),
                "stored_length_after": len(block_stored),
            }
        )
        rebuilt_body.extend(block_stored)
        cursor += len(block_stored)
    new_file_length = record.header_size + len(rebuilt_body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    footer_size = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_size]
    old_tail = original_entry[record.file_length + footer_size :]
    if any(old_tail):
        raise TextPatchError("STRG outer allocation has an opaque nonzero tail")
    active = bytes(header) + bytes(rebuilt_body) + footer
    if len(active) > entry.size:
        raise TextPatchError(
            f"Edited STRG exceeds outer {outer_index} by {len(active) - entry.size} bytes"
        )
    rebuilt = active + b"\0" * (entry.size - len(active))

    memory_reader = apf_texture_patch.BytesReader(rebuilt)
    reparsed_record = apf_inner.parse_iff(memory_reader, entry)
    if reparsed_record.warnings or reparsed_record.footer is None:
        raise TextPatchError("Rebuilt STRG IFF has structural warnings")
    rebuilt_blocks = [
        apf_inner.decode_block(
            memory_reader,
            reparsed_record,
            index,
            MAX_DECOMPRESSED,
        )
        for index in range(reparsed_record.block_count)
    ]
    if rebuilt_blocks != new_blocks:
        raise TextPatchError("Rebuilt STRG IFF changed the intended block corpus")
    before_parts = _file_part_hashes(record, original_blocks)
    after_parts = _file_part_hashes(reparsed_record, rebuilt_blocks)
    changed_parts = [key for key in before_parts if before_parts[key] != after_parts[key]]
    if changed_parts != [(expected_inner, 0)]:
        raise TextPatchError(
            f"STRG rebuild changed unrelated inner parts: {changed_parts}"
        )
    rebuilt_target = reparsed_record.files[expected_inner].parts[0]
    verified_body = rebuilt_blocks[rebuilt_target.block_index][
        rebuilt_target.offset : rebuilt_target.offset + rebuilt_target.length
    ]
    try:
        verified = string_table_inventory.parse_apf_body(
            verified_body,
            outer_index,
            expected_inner,
            expected_name,
        )
    except string_table_inventory.StringTableError as exc:
        raise TextPatchError(f"Rebuilt STRG table is invalid: {exc}") from exc
    if string_table_inventory.rebuild_table(verified) != verified_body:
        raise TextPatchError("Rebuilt STRG table is not byte-stable")
    for pool_index, replacement in replacements.items():
        if verified.pool[pool_index].text != replacement:
            raise TextPatchError("Rebuilt STRG does not contain an intended edit")

    changed = [
        index
        for index, (before, after) in enumerate(zip(original_entry, rebuilt, strict=True))
        if before != after
    ]
    return TextPatchResult(
        outer_index,
        rebuilt,
        {
            "schema": SCHEMA,
            "mode": "patched",
            "bank_type": "STRG",
            "outer_index": outer_index,
            "inner_index": expected_inner,
            "table_name": expected_name,
            "edit_count": len(edit_rows),
            "edits": edit_rows,
            "source": {
                "entry_size": entry.size,
                "entry_sha256": _sha256(original_entry),
                "body_size": len(original_part),
                "body_sha256": _sha256(original_part),
                "opened_read_only": True,
            },
            "output": {
                "entry_size": len(rebuilt),
                "entry_sha256": _sha256(rebuilt),
                "body_size": len(verified_body),
                "body_sha256": _sha256(verified_body),
                "changed_byte_count": len(changed),
                "first_changed_offset": changed[0] if changed else None,
                "last_changed_offset": changed[-1] if changed else None,
            },
            "iff": {
                "allocation_size": entry.size,
                "file_length_before": record.file_length,
                "file_length_after": new_file_length,
                "footer_sha256_before": _sha256(footer),
                "footer_sha256_after": _sha256(
                    rebuilt[new_file_length : new_file_length + footer_size]
                ),
                "blocks": block_rows,
            },
            "validation": {
                "all_replacements_fit_original_string_allocations": True,
                "record_ids_preserved": True,
                "relative_pointers_rebuilt": True,
                "exact_strg_body_allocation_preserved": True,
                "h7a_round_trip_exact": True,
                "iff_reparsed_without_warnings": True,
                "footer_bit_exact": True,
                "fixed_outer_allocation_preserved": True,
                "unrelated_inner_parts_preserved": True,
                "manifest_contains_retail_or_replacement_bytes": False,
            },
        },
    )


def build_table_patch(
    index_path: Path,
    outer_index: int,
    replacements: Mapping[int, str],
) -> TextPatchResult:
    """Compile all selected pool edits for one proved APF text bank."""

    if outer_index not in TABLE_TARGETS:
        raise TextPatchError(f"Outer {outer_index} is not a proved APF text bank")
    if not replacements:
        raise TextPatchError("Select at least one text allocation to edit")
    if any(not isinstance(index, int) or index < 0 for index in replacements):
        raise TextPatchError("Text pool indices must be non-negative integers")
    if outer_index in STRG_TARGETS:
        return _build_strg_patch(index_path, outer_index, replacements)

    try:
        archive = apf_outer.parse_archive(index_path)
        tables = apf_txt_loc.parse_archive(index_path, MAX_DECOMPRESSED)
    except (OSError, apf_inner.FormatError, apf_outer.FormatError, apf_txt_loc.TextError) as exc:
        raise TextPatchError(f"Could not read APF localization: {exc}") from exc
    table = next(
        (row for row in tables if int(row["outer_index"]) == outer_index), None
    )
    if table is None:
        raise TextPatchError(f"APF localization table {outer_index} is missing")
    expected_inner, expected_name = TABLE_TARGETS[outer_index]
    if int(table["inner_index"]) != expected_inner or table["inner_name"] != expected_name:
        raise TextPatchError("APF localization table identity changed")
    body, edit_rows = _edited_body(table, replacements)

    entry = archive.entries[outer_index]
    if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
        raise TextPatchError("Localization target is no longer one fixed 0A allocation")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        original_blocks = [
            apf_inner.decode_block(reader, record, index, MAX_DECOMPRESSED)
            for index in range(record.block_count)
        ]
    if record.warnings or record.block_count != 1 or record.file_count != 1:
        raise TextPatchError("Localization IFF no longer has the proved one-file layout")
    target = record.files[expected_inner]
    if (
        target.name != expected_name
        or target.type_name != apf_txt_loc.TYPE_NAME
        or len(target.parts) != 1
        or target.parts[0].block_index != 0
        or target.parts[0].offset != 0
        or target.parts[0].length != len(original_blocks[0])
    ):
        raise TextPatchError("Localization inner-file ownership changed")
    descriptor = record.blocks[0]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise TextPatchError("Localization block is no longer H7A-compressed")

    if body == original_blocks[0]:
        return TextPatchResult(
            outer_index,
            original_entry,
            {
                "schema": SCHEMA,
                "mode": "no_op",
                "bank_type": "TXT loc system",
                "outer_index": outer_index,
                "inner_index": expected_inner,
                "table_name": expected_name,
                "edit_count": len(edit_rows),
                "edits": edit_rows,
                "source": {
                    "entry_size": entry.size,
                    "entry_sha256": _sha256(original_entry),
                    "body_size": len(body),
                    "body_sha256": _sha256(body),
                    "opened_read_only": True,
                },
                "output": {
                    "entry_size": len(original_entry),
                    "entry_sha256": _sha256(original_entry),
                    "body_size": len(body),
                    "body_sha256": _sha256(body),
                    "changed_byte_count": 0,
                    "first_changed_offset": None,
                    "last_changed_offset": None,
                },
                "validation": {
                    "input_matches_source": True,
                    "entry_bit_exact": True,
                    "manifest_contains_retail_or_replacement_bytes": False,
                },
            },
        )

    compressed = apf_texture_patch.compress_h7a(body, descriptor.wrapper.shift)
    stored = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(body),
        apf_inner.H7A_HEADER_SIZE + len(compressed),
        descriptor.unknown_10,
        descriptor.wrapper.shift,
    ) + compressed
    if len(stored) == len(body):
        raise TextPatchError("Compressed localization block hit an ambiguous IFF length")
    if apf_inner.decompress_h7a(compressed, len(body), descriptor.wrapper.shift) != body:
        raise TextPatchError("Localization H7A round trip failed")

    header = bytearray(original_entry[: record.header_size])
    block_start = record.header_size
    struct.pack_into(
        ">8I",
        header,
        apf_inner.IFF_HEADER_SIZE,
        descriptor.name_hash,
        descriptor.type_hash,
        descriptor.unknown_08,
        len(body),
        descriptor.unknown_10,
        block_start,
        len(stored),
        descriptor.indexed,
    )
    new_file_length = record.header_size + len(stored)
    struct.pack_into(">I", header, 0x08, new_file_length)
    if record.footer is None:
        raise TextPatchError("Localization IFF lost its name footer")
    footer_size = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_size]
    old_tail = original_entry[record.file_length + footer_size :]
    if any(old_tail):
        raise TextPatchError("Localization outer allocation has an opaque nonzero tail")
    active = bytes(header) + stored + footer
    if len(active) > entry.size:
        raise TextPatchError(
            f"Edited localization table exceeds outer {outer_index} by "
            f"{len(active) - entry.size} bytes"
        )
    rebuilt = active + b"\0" * (entry.size - len(active))

    memory_reader = apf_texture_patch.BytesReader(rebuilt)
    reparsed_record = apf_inner.parse_iff(memory_reader, entry)
    if reparsed_record.warnings:
        raise TextPatchError("Rebuilt localization IFF has structural warnings")
    decoded = apf_inner.decode_block(memory_reader, reparsed_record, 0, MAX_DECOMPRESSED)
    if decoded != body:
        raise TextPatchError("Rebuilt localization IFF does not contain the intended table")
    verified = apf_txt_loc.parse_body(
        decoded,
        outer_index=outer_index,
        inner_index=expected_inner,
        inner_name=expected_name,
        inner_file_id=target.file_id,
    )
    if apf_txt_loc.rebuild_table(verified) != decoded:
        raise TextPatchError("Rebuilt localization table is not byte-stable")

    changed = [
        index
        for index, (before, after) in enumerate(zip(original_entry, rebuilt))
        if before != after
    ]
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "mode": "patched",
        "bank_type": "TXT loc system",
        "outer_index": outer_index,
        "inner_index": expected_inner,
        "table_name": expected_name,
        "edit_count": len(edit_rows),
        "edits": edit_rows,
        "source": {
            "entry_size": entry.size,
            "entry_sha256": _sha256(original_entry),
            "body_size": int(table["body_size"]),
            "body_sha256": str(table["body_sha256"]),
            "opened_read_only": True,
        },
        "output": {
            "entry_size": len(rebuilt),
            "entry_sha256": _sha256(rebuilt),
            "body_size": len(body),
            "body_sha256": _sha256(body),
            "changed_byte_count": len(changed),
            "first_changed_offset": changed[0] if changed else None,
            "last_changed_offset": changed[-1] if changed else None,
        },
        "validation": {
            "all_replacements_fit_original_string_allocations": True,
            "record_ids_and_control_rows_preserved": True,
            "relative_pointers_rebuilt": True,
            "h7a_round_trip_exact": True,
            "iff_reparsed_without_warnings": True,
            "footer_bit_exact": True,
            "fixed_outer_allocation_preserved": True,
            "manifest_contains_retail_or_replacement_bytes": False,
        },
    }
    return TextPatchResult(outer_index, rebuilt, manifest)


__all__ = [
    "SCHEMA",
    "STRG_TARGETS",
    "TABLE_TARGETS",
    "TXT_TARGETS",
    "TextAllocation",
    "TextPatchError",
    "TextPatchResult",
    "build_table_patch",
    "inventory",
    "parse_asset_id",
    "validate_replacement",
]
