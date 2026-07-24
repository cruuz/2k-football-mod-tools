#!/usr/bin/env python3
"""Bounded APF 2K8 on-disc player base-rating writer.

APF stores the 28 mapped base ratings as independent unsigned bytes inside
each fixed ``0x14C`` player record.  This writer accepts only player indices
``0..2253``, the exact public field IDs, and public replacement values
``0..99``.  It changes those selected bytes in the decoded ROST body, rebuilds
the existing H7A stream with :func:`apf_inner.encode_h7a_preserving_tokens`,
and reparses and semantically validates the result before returning it.

``entry_bytes`` is a private build intermediate containing bytes from the
user's game.  It must never be put in a project or release.  The accompanying
manifest is retail-free: it carries stable target identities, counts, hashes,
and validation results but no source values, replacement values, preimages,
physical pack offsets, or payload bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
from typing import Mapping

import apf_inner
import apf_outer
import apf_roster
import apf_texture_patch

from mod_editor.core import platform_compat
from mod_editor.apf_studio.player_ratings import (
    PlayerRatingField,
    PlayerRatingsError,
    load_player_rating_schema,
)
from mod_editor.apf_studio.project import PLAYER_RATING_PAYLOAD_SCHEMA


SCHEMA = "apf2k8_player_rating_patch/v1"
PAYLOAD_SCHEMA = PLAYER_RATING_PAYLOAD_SCHEMA
EDIT_ID_PREFIX = "apf:player-rating"
MAX_DECOMPRESSED = 16 * 1024 * 1024
PUBLIC_MINIMUM = 0
PUBLIC_MAXIMUM = 99
EXPECTED_PLAYER_COUNT = 2_254


class PlayerRatingPatchError(ValueError):
    """A rating edit or source left the exact bounded writer contract."""


@dataclass(frozen=True)
class PlayerRatingTarget:
    asset_id: str
    player_index: int
    field_id: str
    label: str
    record_relative_offset: int


@dataclass(frozen=True)
class PlayerRatingPatchResult:
    """Private compiled entry plus a retail-free build receipt."""

    outer_index: int
    entry_bytes: bytes
    manifest: Mapping[str, object]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def _schema_fields() -> tuple[PlayerRatingField, ...]:
    try:
        schema = load_player_rating_schema()
    except PlayerRatingsError as exc:
        raise PlayerRatingPatchError(
            f"Could not load the APF player-rating target dictionary: {exc}"
        ) from exc
    if (
        len(schema.fields) != 28
        or schema.record_stride != apf_roster.PLAYER_STRIDE
        or schema.stock_observed_minimum != PUBLIC_MINIMUM
        or schema.stock_observed_maximum != PUBLIC_MAXIMUM
    ):
        raise PlayerRatingPatchError("APF player-rating target contract changed")
    return schema.fields


def asset_id(player_index: int, field_id: str) -> str:
    """Return one stable, retail-free rating target identity."""

    target = target_for(player_index, field_id)
    return target.asset_id


def target_for(player_index: int, field_id: str) -> PlayerRatingTarget:
    if type(player_index) is not int or not 0 <= player_index < EXPECTED_PLAYER_COUNT:
        raise PlayerRatingPatchError("APF player index must be an integer from 0 to 2253")
    if not isinstance(field_id, str):
        raise PlayerRatingPatchError("APF player-rating field ID must be text")
    by_id = {field.field_id: field for field in _schema_fields()}
    field = by_id.get(field_id)
    if field is None:
        raise PlayerRatingPatchError(f"Unknown APF player-rating field: {field_id!r}")
    return PlayerRatingTarget(
        asset_id=f"{EDIT_ID_PREFIX}:{player_index}:{field.field_id}",
        player_index=player_index,
        field_id=field.field_id,
        label=field.label,
        record_relative_offset=field.relative_offset,
    )


def parse_asset_id(value: str) -> PlayerRatingTarget:
    if not isinstance(value, str):
        raise PlayerRatingPatchError("APF player-rating asset ID must be text")
    fields = value.split(":")
    if len(fields) != 4 or fields[:2] != ["apf", "player-rating"]:
        raise PlayerRatingPatchError(f"Unknown APF player-rating asset: {value}")
    try:
        player_index = int(fields[2])
    except ValueError as exc:
        raise PlayerRatingPatchError(
            f"Malformed APF player-rating asset: {value}"
        ) from exc
    target = target_for(player_index, fields[3])
    if target.asset_id != value:
        raise PlayerRatingPatchError(f"Malformed APF player-rating asset: {value}")
    return target


def target_metadata(target: PlayerRatingTarget) -> dict[str, object]:
    """Small target contract suitable for a future retail-free project."""

    return {
        "player_index": target.player_index,
        "field_id": target.field_id,
        "record_relative_offset": target.record_relative_offset,
        "public_minimum": PUBLIC_MINIMUM,
        "public_maximum": PUBLIC_MAXIMUM,
    }


def validate_value(value: object) -> int:
    if type(value) is not int:
        raise PlayerRatingPatchError("APF player rating must be a whole number from 0 to 99")
    if not PUBLIC_MINIMUM <= value <= PUBLIC_MAXIMUM:
        raise PlayerRatingPatchError("APF player rating must be from 0 to 99")
    return value


def encode_replacement_payload(value: object) -> bytes:
    """Encode a canonical replacement-only payload; never a retail preimage."""

    rating = validate_value(value)
    return (
        json.dumps(
            {"schema": PAYLOAD_SCHEMA, "value": rating},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def decode_replacement_payload(data: bytes, target_id: str = "rating edit") -> int:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlayerRatingPatchError(
            f"Player-rating replacement is not valid UTF-8 JSON: {target_id}"
        ) from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema", "value"}
        or document.get("schema") != PAYLOAD_SCHEMA
    ):
        raise PlayerRatingPatchError(
            f"Player-rating replacement payload is invalid: {target_id}"
        )
    value = validate_value(document.get("value"))
    if encode_replacement_payload(value) != data:
        raise PlayerRatingPatchError(
            f"Player-rating replacement payload is not canonical: {target_id}"
        )
    return value


def normalize_replacements(
    replacements: Mapping[int, Mapping[str, int]],
) -> tuple[tuple[PlayerRatingTarget, int], ...]:
    """Validate and deterministically order a public ratings edit batch."""

    if not isinstance(replacements, Mapping) or not replacements:
        raise PlayerRatingPatchError("Select at least one APF player rating to edit")
    rows: list[tuple[PlayerRatingTarget, int]] = []
    seen: set[str] = set()
    for player_index, fields in replacements.items():
        if type(player_index) is not int or not 0 <= player_index < EXPECTED_PLAYER_COUNT:
            raise PlayerRatingPatchError(
                "APF player indices must be integers from 0 to 2253"
            )
        if not isinstance(fields, Mapping) or not fields:
            raise PlayerRatingPatchError(
                f"Select at least one rating for APF player {player_index}"
            )
        for field_id, supplied in fields.items():
            target = target_for(player_index, field_id)
            if target.asset_id in seen:
                raise PlayerRatingPatchError(
                    f"APF player rating was selected twice: {target.asset_id}"
                )
            seen.add(target.asset_id)
            rows.append((target, validate_value(supplied)))
    order = {
        field.field_id: field.display_order for field in _schema_fields()
    }
    rows.sort(key=lambda item: (item[0].player_index, order[item[0].field_id]))
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
        raise PlayerRatingPatchError(
            f"APF roster semantic validation failed: {exc}"
        ) from exc


def build_patch(
    index_path: Path,
    replacements: Mapping[int, Mapping[str, int]],
) -> PlayerRatingPatchResult:
    """Compile rating edits into the fixed-size private outer ROST entry."""

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
    except (
        OSError,
        IndexError,
        apf_inner.FormatError,
        apf_outer.FormatError,
    ) as exc:
        raise PlayerRatingPatchError(
            f"Could not open APF player-rating writer target: {exc}"
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
        raise PlayerRatingPatchError("APF player-rating IFF/outer ownership changed")
    target_file = record.files[0]
    if (
        target_file.name != apf_roster.INNER_NAME
        or target_file.type_name != apf_roster.INNER_TYPE
        or len(target_file.parts) != 1
        or target_file.parts[0].block_index != 0
    ):
        raise PlayerRatingPatchError("APF player-rating inner-file ownership changed")
    target_part = target_file.parts[0]
    original_body = original_blocks[0][
        target_part.offset : target_part.offset + target_part.length
    ]
    if len(original_body) != apf_roster.EXPECTED_LENGTH:
        raise PlayerRatingPatchError("APF player-rating decoded allocation changed")
    try:
        tables, _root = apf_roster.parse_root(original_body)
    except apf_roster.RosterError as exc:
        raise PlayerRatingPatchError(f"Could not map APF player records: {exc}") from exc
    player_table = tables[0]
    if (
        player_table.count != EXPECTED_PLAYER_COUNT
        or player_table.stride != apf_roster.PLAYER_STRIDE
        or player_table.offset != apf_roster.ROOT_SIZE
    ):
        raise PlayerRatingPatchError("APF player table ownership changed")
    _semantic_validate(original_body, entry.size, _sha256(original_entry))

    wanted_body = bytearray(original_body)
    selected_offsets: set[int] = set()
    expected_changed_offsets: set[int] = set()
    edit_rows: list[dict[str, object]] = []
    for target, value in normalized:
        absolute = (
            player_table.offset
            + target.player_index * apf_roster.PLAYER_STRIDE
            + target.record_relative_offset
        )
        if absolute in selected_offsets:
            raise PlayerRatingPatchError("Two APF rating targets resolve to one byte")
        selected_offsets.add(absolute)
        before = original_body[absolute]
        wanted_body[absolute] = value
        if before != value:
            expected_changed_offsets.add(absolute)
        edit_rows.append(
            {
                "asset_id": target.asset_id,
                **target_metadata(target),
                "replacement_value_sha256": _sha256(
                    encode_replacement_payload(value)
                ),
                "effective_change": before != value,
            }
        )

    wanted = bytes(wanted_body)
    actual_changed_offsets = {
        index
        for index, (before, after) in enumerate(
            zip(original_body, wanted, strict=True)
        )
        if before != after
    }
    if actual_changed_offsets != expected_changed_offsets:
        raise PlayerRatingPatchError(
            "APF rating edit changed bytes outside the exact selected targets"
        )

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
            raise PlayerRatingPatchError("APF roster block is no longer H7A-compressed")
        patched_block = bytearray(original_blocks[0])
        patched_block[
            target_part.offset : target_part.offset + target_part.length
        ] = wanted
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
            decoded_roundtrip = apf_inner.decompress_h7a(
                compressed,
                len(new_blocks[0]),
                descriptor.wrapper.shift,
            )
        except apf_inner.FormatError as exc:
            raise PlayerRatingPatchError(
                f"Could not encode APF player-rating H7A: {exc}"
            ) from exc
        if decoded_roundtrip != new_blocks[0]:
            raise PlayerRatingPatchError("APF player-rating H7A round trip changed the edit")

        header = bytearray(original_entry[: record.header_size])
        block_start = record.header_size
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE,
            descriptor.name_hash,
            descriptor.type_hash,
            descriptor.unknown_08,
            descriptor.uncompressed_length,
            descriptor.unknown_10,
            block_start,
            len(stored),
            descriptor.indexed,
        )
        file_length_after = record.header_size + len(stored)
        struct.pack_into(">I", header, 0x08, file_length_after)
        footer_size = 8 + record.footer.payload_size
        footer = original_entry[record.file_length : record.file_length + footer_size]
        old_tail = original_entry[record.file_length + footer_size :]
        if any(old_tail):
            raise PlayerRatingPatchError("APF roster outer allocation has a nonzero tail")
        active = bytes(header) + stored + footer
        if len(active) > entry.size:
            raise PlayerRatingPatchError(
                "Edited player ratings do not fit the game's fixed compressed allocation"
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
            raise PlayerRatingPatchError(
                f"Rebuilt APF player-rating IFF is invalid: {exc}"
            ) from exc
        if reparsed.warnings or rebuilt_blocks != new_blocks:
            raise PlayerRatingPatchError(
                "Rebuilt APF player-rating IFF changed its decoded block"
            )
        before_parts = _part_hashes(record, original_blocks)
        after_parts = _part_hashes(reparsed, rebuilt_blocks)
        changed_parts = [
            key for key in before_parts if before_parts[key] != after_parts[key]
        ]
        if changed_parts != [(target_file.index, 0)]:
            raise PlayerRatingPatchError(
                f"Player-rating rebuild changed unrelated inner parts: {changed_parts}"
            )
        rebuilt_part = reparsed.files[0].parts[0]
        verified_body = rebuilt_blocks[0][
            rebuilt_part.offset : rebuilt_part.offset + rebuilt_part.length
        ]
        if verified_body != wanted:
            raise PlayerRatingPatchError(
                "Rebuilt APF roster does not contain the intended rating body"
            )
        verified_changes = {
            index
            for index, (before, after) in enumerate(
                zip(original_body, verified_body, strict=True)
            )
            if before != after
        }
        if verified_changes != expected_changed_offsets:
            raise PlayerRatingPatchError(
                "Rebuilt APF roster changed bytes beyond selected rating targets"
            )
        _semantic_validate(verified_body, entry.size, _sha256(rebuilt))
        schema = load_player_rating_schema()
        for target, value in normalized:
            record_start = (
                player_table.offset
                + target.player_index * apf_roster.PLAYER_STRIDE
            )
            decoded = schema.decode_record(
                verified_body[
                    record_start : record_start + apf_roster.PLAYER_STRIDE
                ]
            )
            if decoded[target.field_id] != value:
                raise PlayerRatingPatchError(
                    f"Rebuilt {target.asset_id} differs from its replacement"
                )

    return PlayerRatingPatchResult(
        outer_index=apf_roster.OUTER_TABLE_INDEX,
        entry_bytes=rebuilt,
        manifest={
            "schema": SCHEMA,
            "mode": mode,
            "edit_count": len(edit_rows),
            "effective_edit_count": len(expected_changed_offsets),
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
                "selected_target_count": len(selected_offsets),
                "compressed_block_size": compressed_size_after,
                "file_length": file_length_after,
                "h7a_transport": token_metrics,
            },
            "validation": {
                "all_player_indices_within_0_2253": True,
                "all_fields_in_exact_28_field_dictionary": True,
                "all_public_values_within_0_99": True,
                "decoded_changes_equal_selected_rating_bytes": True,
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
            "distribution": {
                "entry_bytes_are_private_user_owned_game_data": True,
                "entry_bytes_must_not_ship_in_projects_or_releases": True,
                "manifest_contains_retail_bytes": False,
            },
        },
    )


def write_private_outer_entry(
    result: PlayerRatingPatchResult, destination: Path
) -> Path:
    """Atomically publish a private compiled entry without overwriting a file."""

    destination = Path(destination).expanduser().absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            f"Private rating-entry destination already exists: {destination}"
        )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    published = False
    try:
        platform_compat.fchmod(descriptor, 0o600, path=temporary)
        view = memoryview(result.entry_bytes)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("Short write while publishing private APF rating entry")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary, destination)
        published = True
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if destination.read_bytes() != result.entry_bytes:
            raise PlayerRatingPatchError(
                "Published private APF rating entry failed verification"
            )
    except BaseException:
        if published:
            destination.unlink(missing_ok=True)
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    return destination


__all__ = [
    "EDIT_ID_PREFIX",
    "EXPECTED_PLAYER_COUNT",
    "PAYLOAD_SCHEMA",
    "PUBLIC_MAXIMUM",
    "PUBLIC_MINIMUM",
    "PlayerRatingPatchError",
    "PlayerRatingPatchResult",
    "PlayerRatingTarget",
    "SCHEMA",
    "asset_id",
    "build_patch",
    "decode_replacement_payload",
    "encode_replacement_payload",
    "normalize_replacements",
    "parse_asset_id",
    "target_for",
    "target_metadata",
    "validate_value",
    "write_private_outer_entry",
]
