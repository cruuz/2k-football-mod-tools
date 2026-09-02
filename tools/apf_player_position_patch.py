#!/usr/bin/env python3
"""Bounded APF 2K8 on-disc player-position writer.

Each edit changes the executable-consumed position byte at player ``+0x34``
and its source-required opaque mirror at ``+0x35`` as one indivisible pair.
Only player indices ``0..2253`` and the retail-free semantic codes ``0..16``
are accepted.  The source archive is opened read-only; the returned outer
entry is a private build intermediate and must never ship in a project.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
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
import apf_roster
import apf_texture_patch

from mod_editor.apf_studio.player_positions import (
    PlayerPosition,
    PlayerPositionSchema,
    PlayerPositionsError,
    load_player_position_schema,
)
from mod_editor.apf_studio.project import PLAYER_POSITION_PAYLOAD_SCHEMA


SCHEMA = "apf2k8_player_position_patch/v1"
PAYLOAD_SCHEMA = PLAYER_POSITION_PAYLOAD_SCHEMA
EDIT_ID_PREFIX = "apf:player-position"
MAX_DECOMPRESSED = 16 * 1024 * 1024
EXPECTED_PLAYER_COUNT = 2_254
SEMANTIC_RELATIVE_OFFSET = 0x34
MIRROR_RELATIVE_OFFSET = 0x35
MINIMUM_CODE = 0
MAXIMUM_CODE = 16


class PlayerPositionPatchError(ValueError):
    """A position edit or source left the exact bounded writer contract."""


@dataclass(frozen=True)
class PlayerPositionTarget:
    asset_id: str
    player_index: int
    semantic_relative_offset: int
    mirror_relative_offset: int


@dataclass(frozen=True)
class PlayerPositionPatchResult:
    """Private compiled entry plus a retail-free build receipt."""

    outer_index: int
    entry_bytes: bytes
    manifest: Mapping[str, object]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _schema() -> PlayerPositionSchema:
    try:
        schema = load_player_position_schema()
    except PlayerPositionsError as exc:
        raise PlayerPositionPatchError(
            f"Could not load the APF player-position dictionary: {exc}"
        ) from exc
    if (
        schema.player_count != EXPECTED_PLAYER_COUNT
        or schema.record_stride != apf_roster.PLAYER_STRIDE
        or schema.semantic_relative_offset != SEMANTIC_RELATIVE_OFFSET
        or schema.mirror_relative_offset != MIRROR_RELATIVE_OFFSET
        or schema.code_minimum != MINIMUM_CODE
        or schema.code_maximum != MAXIMUM_CODE
        or len(schema.positions) != 17
    ):
        raise PlayerPositionPatchError("APF player-position target contract changed")
    return schema


def target_for(player_index: int) -> PlayerPositionTarget:
    if type(player_index) is not int or not 0 <= player_index < EXPECTED_PLAYER_COUNT:
        raise PlayerPositionPatchError("APF player index must be an integer from 0 to 2253")
    _schema()
    return PlayerPositionTarget(
        f"{EDIT_ID_PREFIX}:{player_index}",
        player_index,
        SEMANTIC_RELATIVE_OFFSET,
        MIRROR_RELATIVE_OFFSET,
    )


def asset_id(player_index: int) -> str:
    return target_for(player_index).asset_id


def parse_asset_id(value: str) -> PlayerPositionTarget:
    if not isinstance(value, str):
        raise PlayerPositionPatchError("APF player-position asset ID must be text")
    fields = value.split(":")
    if len(fields) != 3 or fields[:2] != ["apf", "player-position"]:
        raise PlayerPositionPatchError(f"Unknown APF player-position asset: {value}")
    try:
        player_index = int(fields[2])
    except ValueError as exc:
        raise PlayerPositionPatchError(
            f"Malformed APF player-position asset: {value}"
        ) from exc
    target = target_for(player_index)
    if target.asset_id != value:
        raise PlayerPositionPatchError(
            f"Malformed APF player-position asset: {value}"
        )
    return target


def target_metadata(target: PlayerPositionTarget) -> dict[str, object]:
    return {
        "player_index": target.player_index,
        "semantic_relative_offset": target.semantic_relative_offset,
        "mirror_relative_offset": target.mirror_relative_offset,
        "minimum_code": MINIMUM_CODE,
        "maximum_code": MAXIMUM_CODE,
        "source_mirror_required": True,
    }


def validate_code(value: object) -> int:
    try:
        position: PlayerPosition = _schema().position_for(value)
    except PlayerPositionsError as exc:
        raise PlayerPositionPatchError(str(exc)) from exc
    return position.code


def encode_replacement_payload(value: object) -> bytes:
    code = validate_code(value)
    return (
        json.dumps(
            {"schema": PAYLOAD_SCHEMA, "value": code},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def decode_replacement_payload(data: bytes, target_id: str = "position edit") -> int:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlayerPositionPatchError(
            f"Player-position replacement is not valid UTF-8 JSON: {target_id}"
        ) from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema", "value"}
        or document.get("schema") != PAYLOAD_SCHEMA
    ):
        raise PlayerPositionPatchError(
            f"Player-position replacement payload is invalid: {target_id}"
        )
    code = validate_code(document.get("value"))
    if encode_replacement_payload(code) != data:
        raise PlayerPositionPatchError(
            f"Player-position replacement payload is not canonical: {target_id}"
        )
    return code


def normalize_replacements(
    replacements: Mapping[int, int],
) -> tuple[tuple[PlayerPositionTarget, int], ...]:
    if not isinstance(replacements, Mapping) or not replacements:
        raise PlayerPositionPatchError("Select at least one APF player position to edit")
    rows: list[tuple[PlayerPositionTarget, int]] = []
    seen: set[str] = set()
    for player_index, supplied in replacements.items():
        target = target_for(player_index)
        if target.asset_id in seen:
            raise PlayerPositionPatchError(
                f"APF player position was selected twice: {target.asset_id}"
            )
        seen.add(target.asset_id)
        rows.append((target, validate_code(supplied)))
    rows.sort(key=lambda item: item[0].player_index)
    return tuple(rows)


def _part_hashes(
    record: apf_inner.IFFRecord, blocks: list[bytes]
) -> Mapping[tuple[int, int], str]:
    return {
        (item.index, part_index): _sha256(
            blocks[part.block_index][part.offset : part.offset + part.length]
        )
        for item in record.files
        for part_index, part in enumerate(item.parts)
    }


def _semantic_validate(data: bytes, entry_size: int, entry_sha256: str) -> None:
    try:
        apf_roster.build_report(
            data,
            {
                "index_path": "user-source",
                "outer_table_index": apf_roster.OUTER_TABLE_INDEX,
                "outer_name_id": f"0x{apf_roster.OUTER_NAME_ID:08x}",
                "outer_stored_size": entry_size,
                "outer_stored_sha256": entry_sha256,
                "inner_index": 0,
                "inner_name": apf_roster.INNER_NAME,
                "inner_type": apf_roster.INNER_TYPE,
                "decoded_length": len(data),
                "decoded_sha256": _sha256(data),
            },
        )
    except apf_roster.RosterError as exc:
        raise PlayerPositionPatchError(
            f"APF roster semantic validation failed: {exc}"
        ) from exc


def build_patch(
    index_path: Path,
    replacements: Mapping[int, int],
) -> PlayerPositionPatchResult:
    """Compile paired position edits into the fixed-size private ROST entry."""

    normalized = normalize_replacements(replacements)
    try:
        archive = apf_outer.parse_archive(index_path)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
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
    except (OSError, IndexError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        raise PlayerPositionPatchError(
            f"Could not open APF player-position writer target: {exc}"
        ) from exc
    if (
        entry.name_id != apf_roster.OUTER_NAME_ID
        or len(entry.segments) != 1
        or entry.segments[0].pack_name != "0A"
        or record.warnings
        or record.footer is None
        or record.block_count != 1
        or record.file_count != 1
        or len(record.files) != 1
    ):
        raise PlayerPositionPatchError("APF player-position IFF/outer ownership changed")
    target_file = record.files[0]
    if (
        target_file.name != apf_roster.INNER_NAME
        or target_file.type_name != apf_roster.INNER_TYPE
        or len(target_file.parts) != 1
        or target_file.parts[0].block_index != 0
    ):
        raise PlayerPositionPatchError("APF player-position inner-file ownership changed")
    target_part = target_file.parts[0]
    original_body = original_blocks[0][
        target_part.offset : target_part.offset + target_part.length
    ]
    if len(original_body) != apf_roster.EXPECTED_LENGTH:
        raise PlayerPositionPatchError("APF player-position decoded allocation changed")
    try:
        tables, _root = apf_roster.parse_root(original_body)
    except apf_roster.RosterError as exc:
        raise PlayerPositionPatchError(f"Could not map APF player records: {exc}") from exc
    player_table = tables[0]
    if (
        player_table.count != EXPECTED_PLAYER_COUNT
        or player_table.stride != apf_roster.PLAYER_STRIDE
        or player_table.offset != apf_roster.ROOT_SIZE
    ):
        raise PlayerPositionPatchError("APF player-position table ownership changed")
    _semantic_validate(original_body, entry.size, _sha256(original_entry))

    wanted_body = bytearray(original_body)
    selected_offsets: set[int] = set()
    expected_changed_offsets: set[int] = set()
    edit_rows: list[dict[str, object]] = []
    position_schema = _schema()
    for target, code in normalized:
        record_start = player_table.offset + target.player_index * player_table.stride
        source_record = original_body[record_start : record_start + player_table.stride]
        try:
            source_position = position_schema.decode_record(source_record)
        except PlayerPositionsError as exc:
            raise PlayerPositionPatchError(
                f"Source {target.asset_id} violates the position mirror contract: {exc}"
            ) from exc
        pair = (
            record_start + target.semantic_relative_offset,
            record_start + target.mirror_relative_offset,
        )
        if pair[0] in selected_offsets or pair[1] in selected_offsets:
            raise PlayerPositionPatchError("Two APF position targets resolve to one byte")
        selected_offsets.update(pair)
        for absolute in pair:
            wanted_body[absolute] = code
            if original_body[absolute] != code:
                expected_changed_offsets.add(absolute)
        edit_rows.append(
            {
                "asset_id": target.asset_id,
                **target_metadata(target),
                "replacement_value_sha256": _sha256(encode_replacement_payload(code)),
                "effective_change": source_position.code != code,
            }
        )

    wanted = bytes(wanted_body)
    actual_changed_offsets = {
        index
        for index, values in enumerate(zip(original_body, wanted, strict=True))
        if values[0] != values[1]
    }
    if actual_changed_offsets != expected_changed_offsets:
        raise PlayerPositionPatchError(
            "APF position edit changed bytes outside the exact selected pairs"
        )
    if len(expected_changed_offsets) % 2:
        raise PlayerPositionPatchError("APF position edit changed only one mirror-pair byte")

    if wanted == original_body:
        rebuilt = original_entry
        mode = "no_op"
        compressed_size_after = record.blocks[0].stored_length
        file_length_after = record.file_length
        token_metrics: Mapping[str, object] = {
            "strategy": "source-entry-verbatim",
            "changed_path_recompressed": False,
            "retail_tokens_split_or_replaced": 0,
        }
    else:
        descriptor = record.blocks[0]
        if not descriptor.is_compressed or descriptor.wrapper is None:
            raise PlayerPositionPatchError("APF roster block is no longer H7A-compressed")
        patched_block = bytearray(original_blocks[0])
        patched_block[target_part.offset : target_part.offset + target_part.length] = wanted
        new_blocks = [bytes(patched_block)]
        try:
            compressed, preservation_metrics = apf_inner.encode_h7a_preserving_tokens(
                original_stored[0][apf_inner.H7A_HEADER_SIZE :],
                original_blocks[0],
                new_blocks[0],
                descriptor.wrapper.shift,
            )
            stored = struct.pack(
                ">5I",
                apf_inner.H7A_MAGIC,
                len(new_blocks[0]),
                apf_inner.H7A_HEADER_SIZE + len(compressed),
                descriptor.unknown_10,
                descriptor.wrapper.shift,
            ) + compressed
            roundtrip = apf_inner.decompress_h7a(
                compressed, len(new_blocks[0]), descriptor.wrapper.shift
            )
        except apf_inner.FormatError as exc:
            raise PlayerPositionPatchError(
                f"Could not encode APF player-position H7A: {exc}"
            ) from exc
        if roundtrip != new_blocks[0]:
            raise PlayerPositionPatchError("APF player-position H7A round trip changed the edit")

        header = bytearray(original_entry[: record.header_size])
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE,
            descriptor.name_hash,
            descriptor.type_hash,
            descriptor.unknown_08,
            descriptor.uncompressed_length,
            descriptor.unknown_10,
            record.header_size,
            len(stored),
            descriptor.indexed,
        )
        file_length_after = record.header_size + len(stored)
        struct.pack_into(">I", header, 0x08, file_length_after)
        footer_size = 8 + record.footer.payload_size
        footer = original_entry[record.file_length : record.file_length + footer_size]
        old_tail = original_entry[record.file_length + footer_size :]
        if any(old_tail):
            raise PlayerPositionPatchError("APF roster outer allocation has a nonzero tail")
        active = bytes(header) + stored + footer
        if len(active) > entry.size:
            raise PlayerPositionPatchError(
                "Edited player positions do not fit the game's fixed compressed allocation"
            )
        rebuilt = active + b"\0" * (entry.size - len(active))
        mode = "patched"
        compressed_size_after = len(stored)
        token_metrics = {
            "strategy": "retail-token-preserving",
            "changed_path_recompressed": True,
            **preservation_metrics,
        }

        memory = apf_texture_patch.BytesReader(rebuilt)
        try:
            reparsed = apf_inner.parse_iff(memory, entry)
            rebuilt_blocks = [
                apf_inner.decode_block(memory, reparsed, 0, MAX_DECOMPRESSED)
            ]
        except apf_inner.FormatError as exc:
            raise PlayerPositionPatchError(
                f"Rebuilt APF player-position IFF is invalid: {exc}"
            ) from exc
        if reparsed.warnings or rebuilt_blocks != new_blocks:
            raise PlayerPositionPatchError("Rebuilt APF player-position IFF changed its block")
        before_parts = _part_hashes(record, original_blocks)
        after_parts = _part_hashes(reparsed, rebuilt_blocks)
        changed_parts = [key for key in before_parts if before_parts[key] != after_parts[key]]
        if changed_parts != [(target_file.index, 0)]:
            raise PlayerPositionPatchError(
                f"Player-position rebuild changed unrelated inner parts: {changed_parts}"
            )
        rebuilt_part = reparsed.files[0].parts[0]
        verified_body = rebuilt_blocks[0][
            rebuilt_part.offset : rebuilt_part.offset + rebuilt_part.length
        ]
        verified_changes = {
            index
            for index, values in enumerate(zip(original_body, verified_body, strict=True))
            if values[0] != values[1]
        }
        if verified_body != wanted or verified_changes != expected_changed_offsets:
            raise PlayerPositionPatchError("Rebuilt APF roster changed unrelated bytes")
        _semantic_validate(verified_body, entry.size, _sha256(rebuilt))
        for target, code in normalized:
            record_start = player_table.offset + target.player_index * player_table.stride
            verified_position = position_schema.decode_record(
                verified_body[record_start : record_start + player_table.stride]
            )
            if verified_position.code != code:
                raise PlayerPositionPatchError(
                    f"Rebuilt {target.asset_id} differs from its replacement"
                )

    return PlayerPositionPatchResult(
        apf_roster.OUTER_TABLE_INDEX,
        rebuilt,
        {
            "schema": SCHEMA,
            "mode": mode,
            "edit_count": len(edit_rows),
            "effective_edit_count": sum(bool(row["effective_change"]) for row in edit_rows),
            "edits": tuple(edit_rows),
            "source": {
                "outer_entry_index": apf_roster.OUTER_TABLE_INDEX,
                "entry_size": entry.size,
                "entry_sha256": _sha256(original_entry),
                "opened_read_only": True,
            },
            "output": {
                "entry_size": len(rebuilt),
                "entry_sha256": _sha256(rebuilt),
                "decoded_changed_byte_count": len(actual_changed_offsets),
                "selected_target_count": len(normalized),
                "selected_byte_count": len(selected_offsets),
                "compressed_block_size": compressed_size_after,
                "file_length": file_length_after,
                "h7a_transport": token_metrics,
            },
            "validation": {
                "all_player_indices_within_0_2253": True,
                "all_codes_within_exact_0_16_dictionary": True,
                "source_semantic_and_mirror_bytes_equal": True,
                "every_effective_edit_changes_both_pair_bytes": True,
                "decoded_changes_equal_selected_position_pairs": True,
                "all_relative_pointers_bit_exact": True,
                "h7a_round_trip_exact": True,
                "h7a_retail_tokens_preserved_where_valid": True,
                "iff_reparsed_without_warnings": True,
                "fixed_outer_allocation_preserved": True,
                "unrelated_inner_parts_preserved": True,
                "semantic_roster_reparse_passed": True,
                "manifest_contains_retail_or_replacement_bytes": False,
                "manifest_contains_physical_offsets": False,
            },
            "runtime": {
                "status": "offline_writer_proved_runtime_spot_check_pending"
            },
            "distribution": {
                "entry_bytes_are_private_user_owned_game_data": True,
                "entry_bytes_must_not_ship_in_projects_or_releases": True,
                "manifest_contains_retail_bytes": False,
            },
        },
    )


__all__ = [
    "EDIT_ID_PREFIX",
    "EXPECTED_PLAYER_COUNT",
    "MAXIMUM_CODE",
    "MINIMUM_CODE",
    "MIRROR_RELATIVE_OFFSET",
    "PAYLOAD_SCHEMA",
    "PlayerPositionPatchError",
    "PlayerPositionPatchResult",
    "PlayerPositionTarget",
    "SCHEMA",
    "SEMANTIC_RELATIVE_OFFSET",
    "asset_id",
    "build_patch",
    "decode_replacement_payload",
    "encode_replacement_payload",
    "normalize_replacements",
    "parse_asset_id",
    "target_for",
    "target_metadata",
    "validate_code",
]
