#!/usr/bin/env python3
"""Bounded APF 2K8 on-disc roster identity writer.

This module exposes only the identity strings whose pointer meaning is already
proved by :mod:`apf_roster`: player first/last names and team display names and
abbreviations.  Edits address an existing UTF-16BE allocation by a stable pool
index, never by a physical disc offset.  Each replacement must fit that exact
allocation, all relative pointers stay byte-identical, and the rebuilt ROST
IFF/H7A must fit its original outer allocation.

The returned manifest contains coordinates, limits, counts, and hashes only.
It never contains source strings, replacement strings, retail preimages, or
physical offsets.  The caller owns copying the user's game and publishing the
returned fixed-size entry transactionally.

Jersey numbers are deliberately not handled here.  No consumer-backed jersey
number field exists in the current APF ROST parser/evidence set; guessing one
would turn a bounded identity editor into an unsafe packed-record editor.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Iterable, Mapping

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


SCHEMA = "apf2k8_roster_identity_patch/v1"
EDIT_ID_PREFIX = "apf:roster-name"
MAX_DECOMPRESSED = 16 * 1024 * 1024

EXPECTED_ALLOCATION_COUNT = 3_273
EXPECTED_EDITABLE_COUNT = 3_272
EXPECTED_KNOWN_OWNER_COUNT = 4_628

PLAYER_IDENTITY_FIELDS = frozenset({"first_name", "last_name"})
TEAM_IDENTITY_FIELDS = frozenset(
    {"display_name", "abbreviation", "secondary_abbreviation"}
)

# Public product authoring is deliberately narrower than the complete decoded
# identity map.  These stable values are consumed by the session, facade, and
# inspector so every product boundary makes the same fail-closed decision.
TEAM_DISPLAY_NAME_EDIT_SCOPE = "team_display_name"
PLAYER_NAME_EDIT_SCOPE = "player_name"
PRODUCT_EDIT_SCOPES = frozenset(
    {TEAM_DISPLAY_NAME_EDIT_SCOPE, PLAYER_NAME_EDIT_SCOPE}
)

JERSEY_NUMBER_FINDING: Mapping[str, object] = {
    "status": "read_only_unmapped",
    "requested_field": "jersey_number",
    "result": (
        "The decoded APF ROST evidence maps names, positions, biography fields, "
        "teams, stadiums, and membership pointers, but it does not identify a "
        "consumer-backed jersey-number field. No jersey-number writer is exposed."
    ),
    "best_next_experiment": (
        "Create controlled save/profile pairs that change only one player's "
        "jersey number, then correlate the changed packed field with an exact "
        "XEX accessor before adding a bounded writer."
    ),
}


class RosterIdentityError(ValueError):
    """A source or requested identity edit left the proved safe boundary."""


@dataclass(frozen=True)
class RosterIdentityOwner:
    entity_kind: str
    entity_index: int
    field: str

    @property
    def owner_id(self) -> str:
        return f"{self.entity_kind}:{self.entity_index}:{self.field}"


@dataclass(frozen=True)
class RosterIdentityAllocation:
    asset_id: str
    pool_index: int
    text: str
    allocation_bytes: int
    maximum_utf16_units: int
    known_owners: tuple[RosterIdentityOwner, ...]
    owner_fingerprint: str
    editable: bool
    note: str

    @property
    def known_owner_count(self) -> int:
        return len(self.known_owners)


@dataclass(frozen=True)
class RosterIdentityPatchResult:
    outer_index: int
    entry_bytes: bytes
    manifest: Mapping[str, object]


@dataclass(frozen=True)
class _InventoryState:
    allocations: tuple[RosterIdentityAllocation, ...]
    target_by_pool_index: Mapping[int, int]
    data: bytes


def roster_identity_edit_scope(
    allocation: RosterIdentityAllocation,
) -> str | None:
    """Classify one allocation against the runtime-proved product boundary.

    An allocation is writable only when it has positive character capacity and
    every mapped owner belongs to one proved semantic class.  Shared aliases
    are intentionally admitted when they remain wholly inside that class; the
    UI discloses the alias count because all owners change together.

    ``None`` is the fail-closed result for team abbreviations, mixed
    team/player ownership, zero-capacity allocations, ownerless/unknown
    allocations, and any future owner kind or field not explicitly named here.
    """

    if (
        not allocation.editable
        or allocation.maximum_utf16_units <= 0
        or not allocation.known_owners
    ):
        return None
    if all(
        owner.entity_kind == "team" and owner.field == "display_name"
        for owner in allocation.known_owners
    ):
        return TEAM_DISPLAY_NAME_EDIT_SCOPE
    if all(
        owner.entity_kind == "player" and owner.field in PLAYER_IDENTITY_FIELDS
        for owner in allocation.known_owners
    ):
        return PLAYER_NAME_EDIT_SCOPE
    return None


def roster_identity_is_product_editable(
    allocation: RosterIdentityAllocation,
) -> bool:
    """Return whether the allocation is inside a runtime-proved edit scope."""

    return roster_identity_edit_scope(allocation) in PRODUCT_EDIT_SCOPES


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _asset_id(pool_index: int) -> str:
    return f"{EDIT_ID_PREFIX}:{pool_index}"


def parse_asset_id(value: str) -> int:
    fields = value.split(":")
    if len(fields) != 3 or fields[:2] != ["apf", "roster-name"]:
        raise RosterIdentityError(f"Unknown APF roster-name asset: {value}")
    try:
        pool_index = int(fields[2])
    except ValueError as exc:
        raise RosterIdentityError(f"Malformed APF roster-name asset: {value}") from exc
    if pool_index < 0:
        raise RosterIdentityError(f"Malformed APF roster-name asset: {value}")
    return pool_index


def _utf16be(value: str) -> bytes:
    if not isinstance(value, str):
        raise RosterIdentityError("Roster identity replacement must be text")
    if "\0" in value:
        raise RosterIdentityError("Roster identity text cannot contain a NUL character")
    try:
        return value.encode("utf-16be")
    except UnicodeEncodeError as exc:
        raise RosterIdentityError(
            "Roster identity text contains an unsupported Unicode value"
        ) from exc


def validate_replacement(
    allocation: RosterIdentityAllocation, replacement: str
) -> int:
    encoded = _utf16be(replacement)
    units = len(encoded) // 2
    if not allocation.editable and replacement != allocation.text:
        raise RosterIdentityError(
            f"Roster name allocation {allocation.pool_index} is read-only: "
            f"{allocation.note}"
        )
    if units > allocation.maximum_utf16_units:
        raise RosterIdentityError(
            f"Roster name allocation {allocation.pool_index} accepts at most "
            f"{allocation.maximum_utf16_units} UTF-16 characters; this text "
            f"needs {units}. Most ordinary letters count as one character."
        )
    return units


def _owner_fingerprint(owners: Iterable[RosterIdentityOwner]) -> str:
    document = "\n".join(sorted(owner.owner_id for owner in owners)).encode("utf-8")
    return _sha256(document)


def _identity_owners(
    data: bytes, tables: tuple[apf_roster.RootTable, ...]
) -> Mapping[int, tuple[RosterIdentityOwner, ...]]:
    owners: dict[int, list[RosterIdentityOwner]] = defaultdict(list)
    player_table = tables[0]
    for player_index in range(player_table.count):
        record = player_table.offset + player_index * apf_roster.PLAYER_STRIDE
        for relative, field in apf_roster.PLAYER_STRING_FIELDS.items():
            if field not in PLAYER_IDENTITY_FIELDS:
                continue
            target = apf_roster.resolve_relative(
                data,
                record + relative,
                f"player {player_index} {field}",
            )
            assert target is not None
            owners[target].append(
                RosterIdentityOwner("player", player_index, field)
            )

    team_table = tables[4]
    for team_index in range(team_table.count):
        record = team_table.offset + team_index * apf_roster.TEAM_STRIDE
        for relative, field in apf_roster.TEAM_STRING_FIELDS.items():
            if field not in TEAM_IDENTITY_FIELDS:
                continue
            target = apf_roster.resolve_relative(
                data,
                record + relative,
                f"team {team_index} {field}",
            )
            assert target is not None
            owners[target].append(RosterIdentityOwner("team", team_index, field))
    return {
        target: tuple(sorted(rows, key=lambda item: item.owner_id))
        for target, rows in owners.items()
    }


def _inventory_from_decoded(data: bytes) -> _InventoryState:
    try:
        tables_list, root = apf_roster.parse_root(data)
        pool, _empty_count = apf_roster.parse_string_pool(
            data, root["string_pool_offset"]
        )
    except apf_roster.RosterError as exc:
        raise RosterIdentityError(f"Could not map APF roster identity: {exc}") from exc
    tables = tuple(tables_list)
    targets = tuple(sorted(pool))
    pool_index_by_target = {target: index for index, target in enumerate(targets)}
    owners_by_target = _identity_owners(data, tables)
    allocations: list[RosterIdentityAllocation] = []
    target_by_pool_index: dict[int, int] = {}
    for target, owners in sorted(
        owners_by_target.items(), key=lambda item: pool_index_by_target[item[0]]
    ):
        if target not in pool_index_by_target:
            raise RosterIdentityError(
                "A mapped roster identity no longer targets a string-pool boundary"
            )
        pool_index = pool_index_by_target[target]
        end = (
            targets[pool_index + 1]
            if pool_index + 1 < len(targets)
            else len(data)
        )
        allocation_bytes = end - target
        text = pool[target]
        encoded_size = len(_utf16be(text)) + 2
        if allocation_bytes != encoded_size or allocation_bytes < 2:
            raise RosterIdentityError(
                "An APF roster identity allocation is no longer exact UTF-16BE"
            )
        maximum = allocation_bytes // 2 - 1
        editable = maximum > 0
        owner_count = len(owners)
        note = (
            "Empty zero-capacity identity allocation; kept read-only."
            if not editable
            else (
                f"Shared by {owner_count} mapped roster fields; all of those "
                "fields change together."
                if owner_count > 1
                else "One fixed UTF-16BE roster identity allocation."
            )
        )
        allocations.append(
            RosterIdentityAllocation(
                asset_id=_asset_id(pool_index),
                pool_index=pool_index,
                text=text,
                allocation_bytes=allocation_bytes,
                maximum_utf16_units=maximum,
                known_owners=owners,
                owner_fingerprint=_owner_fingerprint(owners),
                editable=editable,
                note=note,
            )
        )
        target_by_pool_index[pool_index] = target

    known_owner_count = sum(item.known_owner_count for item in allocations)
    editable_count = sum(item.editable for item in allocations)
    if (
        len(allocations) != EXPECTED_ALLOCATION_COUNT
        or editable_count != EXPECTED_EDITABLE_COUNT
        or known_owner_count != EXPECTED_KNOWN_OWNER_COUNT
    ):
        raise RosterIdentityError(
            "APF roster identity coverage changed unexpectedly "
            f"(allocations={len(allocations)}, editable={editable_count}, "
            f"owners={known_owner_count})"
        )
    return _InventoryState(
        tuple(allocations), target_by_pool_index, data
    )


def inventory(index_path: Path) -> tuple[RosterIdentityAllocation, ...]:
    try:
        data, _source = apf_roster.load_roster(index_path)
        return _inventory_from_decoded(data).allocations
    except (
        OSError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        apf_roster.RosterError,
    ) as exc:
        raise RosterIdentityError(f"Could not read APF roster identity: {exc}") from exc


def inventory_from_decoded(
    data: bytes,
) -> tuple[RosterIdentityAllocation, ...]:
    """Map identity allocations from a caller's already-validated ROST body."""

    return _inventory_from_decoded(data).allocations


def allocation_metadata(
    allocation: RosterIdentityAllocation,
) -> dict[str, object]:
    """Return the replacement-only, offset-free project target contract."""

    return {
        "pool_index": allocation.pool_index,
        "maximum_utf16_units": allocation.maximum_utf16_units,
        "known_owner_count": allocation.known_owner_count,
        "owner_fingerprint": allocation.owner_fingerprint,
    }


def _fixed_allocation_bytes(
    allocation: RosterIdentityAllocation, replacement: str
) -> bytes:
    validate_replacement(allocation, replacement)
    encoded = _utf16be(replacement) + b"\0\0"
    return encoded + b"\0" * (allocation.allocation_bytes - len(encoded))


def _part_hashes(
    record: apf_inner.IFFRecord, blocks: list[bytes]
) -> Mapping[tuple[int, int], str]:
    result: dict[tuple[int, int], str] = {}
    for item in record.files:
        for part_index, part in enumerate(item.parts):
            payload = blocks[part.block_index][
                part.offset : part.offset + part.length
            ]
            result[(item.index, part_index)] = _sha256(payload)
    return result


def build_patch(
    index_path: Path, replacements: Mapping[int, str]
) -> RosterIdentityPatchResult:
    """Compile one or more roster-name allocations into one fixed outer span."""

    if not replacements:
        raise RosterIdentityError("Select at least one roster name to edit")
    if any(type(index) is not int or index < 0 for index in replacements):
        raise RosterIdentityError("Roster-name pool indices must be non-negative integers")
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
        raise RosterIdentityError(f"Could not open APF roster writer target: {exc}") from exc

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
        raise RosterIdentityError("APF roster IFF/outer ownership changed")
    target_file = record.files[0]
    if (
        target_file.name != apf_roster.INNER_NAME
        or target_file.type_name != apf_roster.INNER_TYPE
        or len(target_file.parts) != 1
        or target_file.parts[0].block_index != 0
    ):
        raise RosterIdentityError("APF roster inner-file ownership changed")
    target_part = target_file.parts[0]
    original_body = original_blocks[0][
        target_part.offset : target_part.offset + target_part.length
    ]
    if len(original_body) != apf_roster.EXPECTED_LENGTH:
        raise RosterIdentityError("APF roster decoded allocation changed")
    state = _inventory_from_decoded(original_body)
    allocation_by_index = {item.pool_index: item for item in state.allocations}

    wanted_body = bytearray(original_body)
    authorized_ranges: list[tuple[int, int]] = []
    edit_rows: list[dict[str, object]] = []
    for pool_index, replacement in sorted(replacements.items()):
        allocation = allocation_by_index.get(pool_index)
        if allocation is None:
            raise RosterIdentityError(
                f"Unknown editable APF roster-name allocation: {pool_index}"
            )
        if not isinstance(replacement, str):
            raise RosterIdentityError(
                f"Replacement for {allocation.asset_id} is not text"
            )
        replacement_units = validate_replacement(allocation, replacement)
        target = state.target_by_pool_index[pool_index]
        end = target + allocation.allocation_bytes
        before = original_body[target:end]
        expected_before = _utf16be(allocation.text) + b"\0\0"
        if before != expected_before:
            raise RosterIdentityError(
                f"Roster name allocation {pool_index} source bytes changed"
            )
        wanted_body[target:end] = _fixed_allocation_bytes(allocation, replacement)
        authorized_ranges.append((target, end))
        edit_rows.append(
            {
                "asset_id": allocation.asset_id,
                "pool_index": pool_index,
                "maximum_utf16_units": allocation.maximum_utf16_units,
                "replacement_utf16_units": replacement_units,
                "known_owner_count": allocation.known_owner_count,
                "owner_fingerprint": allocation.owner_fingerprint,
                "source_text_sha256": _sha256(allocation.text.encode("utf-8")),
                "replacement_text_sha256": _sha256(replacement.encode("utf-8")),
            }
        )

    wanted = bytes(wanted_body)
    for position, (before, after) in enumerate(zip(original_body, wanted, strict=True)):
        if before != after and not any(start <= position < end for start, end in authorized_ranges):
            raise RosterIdentityError("Roster edit changed bytes outside selected allocations")

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
            raise RosterIdentityError("APF roster block is no longer H7A-compressed")
        patched_block = bytearray(original_blocks[0])
        patched_block[
            target_part.offset : target_part.offset + target_part.length
        ] = wanted
        new_blocks = [bytes(patched_block)]
        try:
            compressed, preservation_metrics = (
                apf_inner.encode_h7a_preserving_tokens(
                    original_stored[0][apf_inner.H7A_HEADER_SIZE :],
                    original_blocks[0],
                    new_blocks[0],
                    descriptor.wrapper.shift,
                )
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
            raise RosterIdentityError(f"Could not encode APF roster H7A: {exc}") from exc
        if decoded_roundtrip != new_blocks[0]:
            raise RosterIdentityError("APF roster H7A round trip changed the edit")

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
        footer = original_entry[
            record.file_length : record.file_length + footer_size
        ]
        old_tail = original_entry[record.file_length + footer_size :]
        if any(old_tail):
            raise RosterIdentityError("APF roster outer allocation has a nonzero tail")
        active = bytes(header) + stored + footer
        if len(active) > entry.size:
            raise RosterIdentityError(
                "Edited roster names do not fit the game's fixed compressed allocation; "
                "shorten one or more replacements and build again"
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
            raise RosterIdentityError(f"Rebuilt APF roster IFF is invalid: {exc}") from exc
        if reparsed.warnings or rebuilt_blocks != new_blocks:
            raise RosterIdentityError("Rebuilt APF roster IFF changed its decoded block")
        before_parts = _part_hashes(record, original_blocks)
        after_parts = _part_hashes(reparsed, rebuilt_blocks)
        changed_parts = [
            key for key in before_parts if before_parts[key] != after_parts[key]
        ]
        if changed_parts != [(target_file.index, 0)]:
            raise RosterIdentityError(
                f"Roster rebuild changed unrelated inner parts: {changed_parts}"
            )
        rebuilt_part = reparsed.files[0].parts[0]
        verified_body = rebuilt_blocks[0][
            rebuilt_part.offset : rebuilt_part.offset + rebuilt_part.length
        ]
        if verified_body != wanted:
            raise RosterIdentityError("Rebuilt APF roster does not contain the intended body")
        try:
            apf_roster.build_report(
                verified_body,
                {
                    "index_path": "user-source",
                    "outer_table_index": apf_roster.OUTER_TABLE_INDEX,
                    "outer_name_id": f"0x{apf_roster.OUTER_NAME_ID:08x}",
                    "outer_stored_size": entry.size,
                    "outer_stored_sha256": _sha256(rebuilt),
                    "inner_index": target_file.index,
                    "inner_name": target_file.name,
                    "inner_type": target_file.type_name,
                    "decoded_length": len(verified_body),
                    "decoded_sha256": _sha256(verified_body),
                },
            )
        except apf_roster.RosterError as exc:
            raise RosterIdentityError(
                f"Rebuilt APF roster failed semantic parsing: {exc}"
            ) from exc
        for pool_index, replacement in replacements.items():
            target = state.target_by_pool_index[pool_index]
            if apf_roster.decode_utf16be_z(
                verified_body, target, f"roster name {pool_index}"
            ) != replacement:
                raise RosterIdentityError(
                    f"Rebuilt roster name {pool_index} differs from its replacement"
                )

    changed_count = sum(
        before != after for before, after in zip(original_body, wanted, strict=True)
    )
    return RosterIdentityPatchResult(
        outer_index=apf_roster.OUTER_TABLE_INDEX,
        entry_bytes=rebuilt,
        manifest={
            "schema": SCHEMA,
            "mode": mode,
            "edit_count": len(edit_rows),
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
                "decoded_changed_byte_count": changed_count,
                "compressed_block_size": compressed_size_after,
                "file_length": file_length_after,
                "h7a_transport": token_metrics,
            },
            "validation": {
                "all_replacements_fit_original_string_allocations": True,
                "all_relative_pointers_bit_exact": True,
                "h7a_round_trip_exact": True,
                "h7a_retail_tokens_preserved_where_valid": True,
                "iff_reparsed_without_warnings": True,
                "fixed_outer_allocation_preserved": True,
                "unrelated_inner_parts_preserved": True,
                "manifest_contains_retail_or_replacement_bytes": False,
                "manifest_contains_physical_offsets": False,
            },
        },
    )


def _self_test() -> None:
    owner = RosterIdentityOwner("player", 7, "last_name")
    allocation = RosterIdentityAllocation(
        asset_id=_asset_id(3),
        pool_index=3,
        text="Seven",
        allocation_bytes=12,
        maximum_utf16_units=5,
        known_owners=(owner,),
        owner_fingerprint=_owner_fingerprint((owner,)),
        editable=True,
        note="fixture",
    )
    assert parse_asset_id(allocation.asset_id) == 3
    assert _fixed_allocation_bytes(allocation, "VII") == (
        "VII".encode("utf-16be") + b"\0" * 6
    )
    try:
        validate_replacement(allocation, "TOO-LONG")
    except RosterIdentityError:
        pass
    else:
        raise AssertionError("overflow replacement was accepted")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", nargs="?", type=Path, help="user-owned APF 0A")
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="validate and summarize the private source-derived identity catalog",
    )
    parser.add_argument(
        "--check-writer",
        action="store_true",
        help="compile one in-memory no-op through the bounded writer",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the retail-free fixed-allocation contract test",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.self_test:
            _self_test()
            print("APF_ROSTER_IDENTITY_SELF_TEST_PASS retail_bytes=0 offsets=0")
            return 0
        if args.index is None or not (args.inventory or args.check_writer):
            raise RosterIdentityError(
                "Choose --self-test, or supply a user-owned 0A with --inventory/--check-writer"
            )
        rows = inventory(args.index)
        if args.check_writer:
            first = next(item for item in rows if item.editable)
            result = build_patch(args.index, {first.pool_index: first.text})
            if result.manifest["mode"] != "no_op":
                raise RosterIdentityError("Writer identity check was not bit-exact")
        print(
            "APF_ROSTER_IDENTITY_PASS "
            f"allocations={len(rows)} editable={sum(item.editable for item in rows)} "
            f"owners={sum(item.known_owner_count for item in rows)} "
            f"numbers={JERSEY_NUMBER_FINDING['status']}"
        )
        return 0
    except (
        RosterIdentityError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        apf_roster.RosterError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
