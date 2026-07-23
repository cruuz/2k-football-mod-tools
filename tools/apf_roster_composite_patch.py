#!/usr/bin/env python3
"""Compose validated APF ROST edit classes into one collision-free entry.

Roster identity text, player ratings, and player positions all own outer entry
1126.  This compositor reconstructs each component's authorized decoded-byte
set from retail-free target metadata, rejects overlap or cross-source results,
then performs one token-preserving H7A rebuild.  The returned entry contains
private user-owned game data; its manifest contains only metadata and hashes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Mapping

import apf_inner
import apf_outer
import apf_player_position_patch
import apf_player_rating_patch
import apf_roster
import apf_roster_identity_patch
import apf_texture_patch


SCHEMA = "apf2k8_roster_composite_patch/v1"
MAX_DECOMPRESSED = 16 * 1024 * 1024


class RosterCompositeError(ValueError):
    """A component result or merged ROST body left the safe contract."""


@dataclass(frozen=True)
class RosterCompositePatchResult:
    outer_index: int
    entry_bytes: bytes
    manifest: Mapping[str, object]


@dataclass(frozen=True)
class _Component:
    kind: str
    schema: str
    result: object
    body: bytes
    changes: frozenset[int]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _target_body(
    entry_bytes: bytes,
    entry: apf_outer.Entry,
) -> tuple[apf_inner.IFFRecord, bytes, bytes]:
    if len(entry_bytes) != entry.size:
        raise RosterCompositeError("A component ROST entry changed fixed allocation size")
    memory = apf_texture_patch.BytesReader(entry_bytes)
    try:
        record = apf_inner.parse_iff(memory, entry)
        if record.block_count != 1:
            raise RosterCompositeError("The APF ROST block count changed")
        block = apf_inner.decode_block(memory, record, 0, MAX_DECOMPRESSED)
    except apf_inner.FormatError as exc:
        raise RosterCompositeError(f"Could not decode a component ROST entry: {exc}") from exc
    if (
        record.warnings
        or record.footer is None
        or record.file_count != 1
        or len(record.files) != 1
    ):
        raise RosterCompositeError("A component ROST IFF ownership contract changed")
    target_file = record.files[0]
    if (
        target_file.name != apf_roster.INNER_NAME
        or target_file.type_name != apf_roster.INNER_TYPE
        or len(target_file.parts) != 1
        or target_file.parts[0].block_index != 0
    ):
        raise RosterCompositeError("A component no longer owns the exact ROST inner file")
    part = target_file.parts[0]
    body = block[part.offset : part.offset + part.length]
    if len(body) != apf_roster.EXPECTED_LENGTH:
        raise RosterCompositeError("A component changed the decoded ROST allocation")
    return record, block, body


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
        raise RosterCompositeError(
            f"Composed APF roster failed semantic validation: {exc}"
        ) from exc


def _result_fields(result: object) -> tuple[int, bytes, Mapping[str, object]]:
    outer_index = getattr(result, "outer_index", None)
    entry_bytes = getattr(result, "entry_bytes", None)
    manifest = getattr(result, "manifest", None)
    if (
        type(outer_index) is not int
        or not isinstance(entry_bytes, bytes)
        or not isinstance(manifest, Mapping)
    ):
        raise RosterCompositeError("A ROST component result is malformed")
    return outer_index, entry_bytes, manifest


def _identity_allowed_offsets(
    original_body: bytes, manifest: Mapping[str, object]
) -> set[int]:
    try:
        _tables, root = apf_roster.parse_root(original_body)
        pool, _empty = apf_roster.parse_string_pool(
            original_body, root["string_pool_offset"]
        )
    except apf_roster.RosterError as exc:
        raise RosterCompositeError(
            f"Could not reconstruct ROST identity targets: {exc}"
        ) from exc
    pool_targets = tuple(sorted(pool))
    rows = manifest.get("edits")
    if not isinstance(rows, (tuple, list)) or not rows:
        raise RosterCompositeError("Roster identity component has no bounded edit rows")
    allowed: set[int] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise RosterCompositeError("Roster identity component edit row is malformed")
        pool_index = row.get("pool_index")
        if type(pool_index) is not int or not 0 <= pool_index < len(pool_targets):
            raise RosterCompositeError("Roster identity component pool target changed")
        if row.get("asset_id") != f"apf:roster-name:{pool_index}":
            raise RosterCompositeError("Roster identity component asset target changed")
        start = pool_targets[pool_index]
        end = (
            pool_targets[pool_index + 1]
            if pool_index + 1 < len(pool_targets)
            else len(original_body)
        )
        allowed.update(range(start, end))
    return allowed


def _rating_allowed_offsets(manifest: Mapping[str, object]) -> set[int]:
    rows = manifest.get("edits")
    if not isinstance(rows, (tuple, list)) or not rows:
        raise RosterCompositeError("Player-rating component has no bounded edit rows")
    allowed: set[int] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise RosterCompositeError("Player-rating component edit row is malformed")
        try:
            target = apf_player_rating_patch.parse_asset_id(str(row.get("asset_id")))
        except apf_player_rating_patch.PlayerRatingPatchError as exc:
            raise RosterCompositeError(
                f"Player-rating component target changed: {exc}"
            ) from exc
        if any(
            row.get(key) != expected
            for key, expected in apf_player_rating_patch.target_metadata(target).items()
        ):
            raise RosterCompositeError("Player-rating component metadata changed")
        allowed.add(
            apf_roster.ROOT_SIZE
            + target.player_index * apf_roster.PLAYER_STRIDE
            + target.record_relative_offset
        )
    return allowed


def _position_allowed_offsets(
    manifest: Mapping[str, object], changes: frozenset[int]
) -> set[int]:
    rows = manifest.get("edits")
    if not isinstance(rows, (tuple, list)) or not rows:
        raise RosterCompositeError("Player-position component has no bounded edit rows")
    allowed: set[int] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise RosterCompositeError("Player-position component edit row is malformed")
        try:
            target = apf_player_position_patch.parse_asset_id(str(row.get("asset_id")))
        except apf_player_position_patch.PlayerPositionPatchError as exc:
            raise RosterCompositeError(
                f"Player-position component target changed: {exc}"
            ) from exc
        if any(
            row.get(key) != expected
            for key, expected in apf_player_position_patch.target_metadata(target).items()
        ):
            raise RosterCompositeError("Player-position component metadata changed")
        start = apf_roster.ROOT_SIZE + target.player_index * apf_roster.PLAYER_STRIDE
        pair = {
            start + target.semantic_relative_offset,
            start + target.mirror_relative_offset,
        }
        changed_pair = changes.intersection(pair)
        if changed_pair and changed_pair != pair:
            raise RosterCompositeError(
                "Player-position component changed only one byte of its mirror pair"
            )
        allowed.update(pair)
    return allowed


def _component(
    kind: str,
    expected_schema: str,
    result: object,
    entry: apf_outer.Entry,
    original_entry_sha256: str,
    original_body: bytes,
) -> _Component:
    outer_index, entry_bytes, manifest = _result_fields(result)
    if outer_index != apf_roster.OUTER_TABLE_INDEX:
        raise RosterCompositeError("ROST component writers resolved to different entries")
    if manifest.get("schema") != expected_schema:
        raise RosterCompositeError(f"{kind.replace('_', ' ').title()} component schema changed")
    source = manifest.get("source")
    if (
        not isinstance(source, Mapping)
        or source.get("outer_entry_index") != apf_roster.OUTER_TABLE_INDEX
        or source.get("entry_size") != entry.size
        or source.get("entry_sha256") != original_entry_sha256
        or source.get("opened_read_only") is not True
    ):
        raise RosterCompositeError(
            f"The {kind.replace('_', ' ')} component was not compiled from this exact source ROST entry"
        )
    _record, _block, body = _target_body(entry_bytes, entry)
    changes = frozenset(
        offset
        for offset, values in enumerate(zip(original_body, body, strict=True))
        if values[0] != values[1]
    )
    output = manifest.get("output")
    if (
        not isinstance(output, Mapping)
        or output.get("decoded_changed_byte_count") != len(changes)
    ):
        raise RosterCompositeError(f"The {kind.replace('_', ' ')} decoded-change receipt changed")
    if kind == "identity":
        allowed = _identity_allowed_offsets(original_body, manifest)
    elif kind == "player_rating":
        allowed = _rating_allowed_offsets(manifest)
    elif kind == "player_position":
        allowed = _position_allowed_offsets(manifest, changes)
    else:
        raise RosterCompositeError(f"Unknown ROST component kind: {kind}")
    if not changes.issubset(allowed):
        raise RosterCompositeError(
            f"The {kind.replace('_', ' ')} component changed bytes outside its selected targets"
        )
    return _Component(kind, expected_schema, result, body, changes)


def compose_components(
    index_path: Path,
    *,
    identity: apf_roster_identity_patch.RosterIdentityPatchResult | None = None,
    ratings: apf_player_rating_patch.PlayerRatingPatchResult | None = None,
    positions: apf_player_position_patch.PlayerPositionPatchResult | None = None,
) -> RosterCompositePatchResult:
    """Merge any two or three validated, disjoint ROST-owned edit classes."""

    supplied = tuple(
        item
        for item in (
            ("identity", apf_roster_identity_patch.SCHEMA, identity),
            ("player_rating", apf_player_rating_patch.SCHEMA, ratings),
            ("player_position", apf_player_position_patch.SCHEMA, positions),
        )
        if item[2] is not None
    )
    if len(supplied) < 2:
        raise RosterCompositeError("ROST composition needs at least two edit classes")

    try:
        archive = apf_outer.parse_archive(index_path)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        with apf_inner.ArchiveReader(archive) as reader:
            original_record = apf_inner.parse_iff(reader, entry)
            original_entry = reader.read(entry, 0, entry.size)
            original_block = apf_inner.decode_block(
                reader, original_record, 0, MAX_DECOMPRESSED
            )
            descriptor = original_record.blocks[0]
            original_stored = reader.read(
                entry, descriptor.start_offset, descriptor.stored_length
            )
    except (OSError, IndexError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        raise RosterCompositeError(f"Could not open the source ROST entry: {exc}") from exc
    if (
        entry.name_id != apf_roster.OUTER_NAME_ID
        or len(entry.segments) != 1
        or entry.segments[0].pack_name != "0A"
        or original_record.warnings
        or original_record.footer is None
        or original_record.block_count != 1
        or original_record.file_count != 1
        or len(original_record.files) != 1
    ):
        raise RosterCompositeError("Source ROST IFF/outer ownership changed")
    source_file = original_record.files[0]
    if (
        source_file.name != apf_roster.INNER_NAME
        or source_file.type_name != apf_roster.INNER_TYPE
        or len(source_file.parts) != 1
        or source_file.parts[0].block_index != 0
    ):
        raise RosterCompositeError("Source ROST inner-file ownership changed")
    source_part = source_file.parts[0]
    original_body = original_block[
        source_part.offset : source_part.offset + source_part.length
    ]
    if len(original_body) != apf_roster.EXPECTED_LENGTH:
        raise RosterCompositeError("Source decoded ROST allocation changed")
    _semantic_validate(original_body, entry.size, _sha256(original_entry))

    original_entry_sha256 = _sha256(original_entry)
    components = tuple(
        _component(
            kind,
            schema,
            result,
            entry,
            original_entry_sha256,
            original_body,
        )
        for kind, schema, result in supplied
    )
    occupied: set[int] = set()
    for component in components:
        overlap = occupied.intersection(component.changes)
        if overlap:
            raise RosterCompositeError("ROST component decoded deltas overlap")
        occupied.update(component.changes)

    wanted_body = bytearray(original_body)
    for component in components:
        for offset in component.changes:
            wanted_body[offset] = component.body[offset]
    wanted = bytes(wanted_body)

    if not occupied:
        rebuilt = original_entry
        mode = "no_op"
        compressed_size_after = descriptor.stored_length
        file_length_after = original_record.file_length
        token_metrics: Mapping[str, object] = {
            "strategy": "source-entry-verbatim",
            "changed_path_recompressed": False,
            "retail_tokens_split_or_replaced": 0,
        }
    else:
        if not descriptor.is_compressed or descriptor.wrapper is None:
            raise RosterCompositeError("Source ROST block is no longer H7A-compressed")
        patched_block = bytearray(original_block)
        patched_block[source_part.offset : source_part.offset + source_part.length] = wanted
        new_block = bytes(patched_block)
        try:
            compressed, preservation_metrics = apf_inner.encode_h7a_preserving_tokens(
                original_stored[apf_inner.H7A_HEADER_SIZE :],
                original_block,
                new_block,
                descriptor.wrapper.shift,
            )
            stored = struct.pack(
                ">5I",
                apf_inner.H7A_MAGIC,
                len(new_block),
                apf_inner.H7A_HEADER_SIZE + len(compressed),
                descriptor.unknown_10,
                descriptor.wrapper.shift,
            ) + compressed
            roundtrip = apf_inner.decompress_h7a(
                compressed, len(new_block), descriptor.wrapper.shift
            )
        except apf_inner.FormatError as exc:
            raise RosterCompositeError(f"Could not encode composed ROST H7A: {exc}") from exc
        if roundtrip != new_block:
            raise RosterCompositeError("Composed ROST H7A round trip changed the edit")

        header = bytearray(original_entry[: original_record.header_size])
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE,
            descriptor.name_hash,
            descriptor.type_hash,
            descriptor.unknown_08,
            descriptor.uncompressed_length,
            descriptor.unknown_10,
            original_record.header_size,
            len(stored),
            descriptor.indexed,
        )
        file_length_after = original_record.header_size + len(stored)
        struct.pack_into(">I", header, 0x08, file_length_after)
        footer_size = 8 + original_record.footer.payload_size
        footer = original_entry[
            original_record.file_length : original_record.file_length + footer_size
        ]
        old_tail = original_entry[original_record.file_length + footer_size :]
        if any(old_tail):
            raise RosterCompositeError("Source ROST allocation has a nonzero tail")
        active = bytes(header) + stored + footer
        if len(active) > entry.size:
            raise RosterCompositeError(
                "Combined roster edits do not fit the fixed ROST allocation"
            )
        rebuilt = active + b"\0" * (entry.size - len(active))
        mode = "patched"
        compressed_size_after = len(stored)
        token_metrics = {
            "strategy": "retail-token-preserving",
            "changed_path_recompressed": True,
            **preservation_metrics,
        }
        _rebuilt_record, _rebuilt_block, verified_body = _target_body(rebuilt, entry)
        verified_changes = {
            offset
            for offset, values in enumerate(zip(original_body, verified_body, strict=True))
            if values[0] != values[1]
        }
        if verified_body != wanted or verified_changes != occupied:
            raise RosterCompositeError("Rebuilt composite ROST changed unrelated bytes")
        _semantic_validate(verified_body, entry.size, _sha256(rebuilt))

    changes_by_kind = {component.kind: component.changes for component in components}
    manifests = {
        component.kind: _result_fields(component.result)[2]
        for component in components
    }
    return RosterCompositePatchResult(
        apf_roster.OUTER_TABLE_INDEX,
        rebuilt,
        {
            "schema": SCHEMA,
            "mode": mode,
            "component_schemas": tuple(component.schema for component in components),
            "identity_edit_count": int(manifests.get("identity", {}).get("edit_count", 0)),
            "player_rating_edit_count": int(
                manifests.get("player_rating", {}).get("edit_count", 0)
            ),
            "player_position_edit_count": int(
                manifests.get("player_position", {}).get("edit_count", 0)
            ),
            "output": {
                "entry_size": len(rebuilt),
                "entry_sha256": _sha256(rebuilt),
                "identity_changed_byte_count": len(changes_by_kind.get("identity", ())),
                "player_rating_changed_byte_count": len(
                    changes_by_kind.get("player_rating", ())
                ),
                "player_position_changed_byte_count": len(
                    changes_by_kind.get("player_position", ())
                ),
                "decoded_changed_byte_count": len(occupied),
                "compressed_block_size": compressed_size_after,
                "file_length": file_length_after,
                "h7a_transport": token_metrics,
            },
            "validation": {
                "components_target_same_source_entry": True,
                "component_decoded_deltas_disjoint": True,
                "position_semantic_mirror_pair_indivisible": True,
                "decoded_changes_equal_component_union": True,
                "h7a_round_trip_exact": True,
                "fixed_outer_allocation_preserved": True,
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


def compose_results(
    index_path: Path,
    identity: apf_roster_identity_patch.RosterIdentityPatchResult,
    ratings: apf_player_rating_patch.PlayerRatingPatchResult,
) -> RosterCompositePatchResult:
    """Backwards-compatible identity-plus-ratings composition route."""

    return compose_components(index_path, identity=identity, ratings=ratings)


__all__ = [
    "RosterCompositeError",
    "RosterCompositePatchResult",
    "SCHEMA",
    "compose_components",
    "compose_results",
]
