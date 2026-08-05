#!/usr/bin/env python3
"""Bounded APF 2K8 custom-team palette and helmet/logo selector writer.

Only user-created team slots 32 through 39 are writable.  Each edit owns the
first ten ARGB dwords of the slot's HOME and AWAY palette records plus the
eight-byte helmet and crest selector records in each uniform bank.  Pointer
targets are resolved from the source ROST and must be aligned, in-table, and
uniquely owned before a byte is changed.  Unknown selector bytes remain
explicitly opaque.  The normal editor preserves them.  The Eagles preset is
the one bounded exception: it applies one complete, source-derived crest-routing
tail whose visual effect is proved in Xenia without assigning unsupported names
to its individual bytes.

The source volume is opened read-only.  The returned fixed-allocation ROST
entry is private user-owned game data and must never ship in a project or
release artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
from typing import Mapping

import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_inner
import apf_outer
import apf_roster
import apf_texture_patch


SCHEMA = "apf2k8_custom_team_appearance_patch/v1"
PAYLOAD_SCHEMA = "apf2k8_custom_team_appearance_replacement/v1"
EDIT_ID_PREFIX = "apf:custom-team-appearance"
MAX_DECOMPRESSED = 16 * 1024 * 1024
USER_SLOTS = tuple(range(32, 40))

TEAM_TABLE_INDEX = 4
PALETTE_TABLE_INDEX = 16
SELECTOR_TABLE_INDEX = 17
CONFIG_TABLE_INDEX = 19
TEAM_CONFIG_POINTER = 0xBC
CONFIG_HOME_PALETTE_POINTER = 0x70
CONFIG_AWAY_PALETTE_POINTER = 0x74
CONFIG_SELECTOR_COUNT_PER_BANK = 14
SELECTOR_HELMET_SLOT = 3
SELECTOR_LOGO_SLOT = 5
PALETTE_COLOR_COUNT = 10
PALETTE_STRIDE = 0x30
SELECTOR_STRIDE = 0x08
CONFIG_STRIDE = 0x98

EAGLES_2017_PALETTE = (
    0xFFC0C0C0,
    0xFF101010,
    0xFFFFFFFF,
    0xFF011D42,
    0xFFFFEBB0,
    0xFFC94B14,
    0xFFEDB01D,
    0xFF369F42,
    0xFF004C54,
    0xFFFFFFFF,
)
EAGLES_CREST_CATALOG_INDEX = 30
EAGLES_SHELL_PALETTE_INDEX = 8
EAGLES_2017_LOGO_ROUTING_TAIL = bytes.fromhex("00010009000000")


class CustomTeamAppearanceError(ValueError):
    """The source or requested appearance left the bounded writer contract."""


@dataclass(frozen=True)
class AppearanceBank:
    palette: tuple[int, ...]
    helmet_selector: bytes
    logo_selector: bytes


@dataclass(frozen=True)
class CustomTeamAppearance:
    slot: int
    home: AppearanceBank
    away: AppearanceBank


@dataclass(frozen=True)
class AppearanceTarget:
    asset_id: str
    slot: int
    config_index: int
    home_palette_index: int
    away_palette_index: int
    home_helmet_selector_index: int
    home_logo_selector_index: int
    away_helmet_selector_index: int
    away_logo_selector_index: int


@dataclass(frozen=True)
class CustomTeamAppearancePatchResult:
    outer_index: int
    entry_bytes: bytes
    manifest: Mapping[str, object]


@dataclass(frozen=True)
class _ResolvedTarget:
    public: AppearanceTarget
    home_palette_offset: int
    away_palette_offset: int
    home_helmet_offset: int
    home_logo_offset: int
    away_helmet_offset: int
    away_logo_offset: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_slot(slot: object) -> int:
    if type(slot) is not int or slot not in USER_SLOTS:
        raise CustomTeamAppearanceError(
            "APF custom-team appearance slot must be an integer from 32 to 39"
        )
    return slot


def asset_id(slot: int) -> str:
    return f"{EDIT_ID_PREFIX}:{_validate_slot(slot)}"


def parse_asset_id(value: str) -> int:
    if not isinstance(value, str):
        raise CustomTeamAppearanceError("APF custom-team appearance asset ID must be text")
    fields = value.split(":")
    if len(fields) != 3 or fields[:2] != ["apf", "custom-team-appearance"]:
        raise CustomTeamAppearanceError(f"Unknown APF custom-team appearance asset: {value}")
    try:
        slot = int(fields[2])
    except ValueError as exc:
        raise CustomTeamAppearanceError(
            f"Malformed APF custom-team appearance asset: {value}"
        ) from exc
    if asset_id(slot) != value:
        raise CustomTeamAppearanceError(
            f"Malformed APF custom-team appearance asset: {value}"
        )
    return slot


def _validate_palette(value: object, label: str) -> tuple[int, ...]:
    if not isinstance(value, (tuple, list)) or len(value) != PALETTE_COLOR_COUNT:
        raise CustomTeamAppearanceError(f"{label} must contain exactly 10 ARGB colors")
    colors: list[int] = []
    for index, color in enumerate(value):
        if type(color) is not int or not 0 <= color <= 0xFFFFFFFF:
            raise CustomTeamAppearanceError(
                f"{label} color {index} must be an unsigned 32-bit ARGB value"
            )
        colors.append(color)
    return tuple(colors)


def _validate_selector(
    value: object,
    label: str,
    *,
    maximum_asset: int,
    shell_palette_index: bool = False,
) -> bytes:
    if not isinstance(value, bytes) or len(value) != SELECTOR_STRIDE:
        raise CustomTeamAppearanceError(f"{label} must contain exactly 8 selector bytes")
    if value[0] > maximum_asset:
        raise CustomTeamAppearanceError(
            f"{label} asset byte {value[0]} is outside 0..{maximum_asset}"
        )
    if shell_palette_index and value[1] >= PALETTE_COLOR_COUNT:
        raise CustomTeamAppearanceError(
            f"{label} shell palette byte {value[1]} is outside 0..9"
        )
    return value


def validate_appearance(value: object) -> CustomTeamAppearance:
    if not isinstance(value, CustomTeamAppearance):
        raise CustomTeamAppearanceError("Custom-team appearance value is malformed")
    slot = _validate_slot(value.slot)

    def bank(source: object, label: str) -> AppearanceBank:
        if not isinstance(source, AppearanceBank):
            raise CustomTeamAppearanceError(f"{label} appearance bank is malformed")
        return AppearanceBank(
            _validate_palette(source.palette, f"{label} palette"),
            _validate_selector(
                source.helmet_selector,
                f"{label} helmet selector",
                maximum_asset=23,
                shell_palette_index=True,
            ),
            _validate_selector(
                source.logo_selector, f"{label} crest selector", maximum_asset=117
            ),
        )

    return CustomTeamAppearance(slot, bank(value.home, "HOME"), bank(value.away, "AWAY"))


def eagles_2017_preset(current: CustomTeamAppearance) -> CustomTeamAppearance:
    """Return the accepted-team Xenia-proved Eagles palette/crest preset."""

    current = validate_appearance(current)

    def bank(source: AppearanceBank) -> AppearanceBank:
        helmet = bytearray(source.helmet_selector)
        helmet[1] = EAGLES_SHELL_PALETTE_INDEX
        logo = bytes((EAGLES_CREST_CATALOG_INDEX,)) + EAGLES_2017_LOGO_ROUTING_TAIL
        return AppearanceBank(
            EAGLES_2017_PALETTE,
            bytes(helmet),
            logo,
        )

    return CustomTeamAppearance(current.slot, bank(current.home), bank(current.away))


def _table_index(
    target: int,
    table: apf_roster.RootTable,
    label: str,
) -> int:
    if table.stride is None or target < table.offset:
        raise CustomTeamAppearanceError(f"{label} does not resolve inside its table")
    relative = target - table.offset
    index, remainder = divmod(relative, table.stride)
    if remainder or not 0 <= index < table.count:
        raise CustomTeamAppearanceError(f"{label} is not an aligned in-table record")
    return index


def _resolve_targets(data: bytes) -> dict[int, _ResolvedTarget]:
    try:
        tables, _root = apf_roster.parse_root(data)
    except apf_roster.RosterError as exc:
        raise CustomTeamAppearanceError(f"Could not parse the APF ROST root: {exc}") from exc
    team_table = tables[TEAM_TABLE_INDEX]
    palette_table = tables[PALETTE_TABLE_INDEX]
    selector_table = tables[SELECTOR_TABLE_INDEX]
    config_table = tables[CONFIG_TABLE_INDEX]
    if (
        team_table.count != 40
        or team_table.stride != apf_roster.TEAM_STRIDE
        or palette_table.count != 266
        or palette_table.stride != PALETTE_STRIDE
        or selector_table.count != 3724
        or selector_table.stride != SELECTOR_STRIDE
        or config_table.count != 40
        or config_table.stride != CONFIG_STRIDE
    ):
        raise CustomTeamAppearanceError("APF custom-team appearance tables changed")

    palette_owners: dict[int, int] = {}
    selector_owners: dict[int, int] = {}
    config_for_team: list[int] = []
    for team_index in range(team_table.count):
        team_start = team_table.offset + team_index * team_table.stride
        try:
            config_offset = apf_roster.resolve_relative(
                data, team_start + TEAM_CONFIG_POINTER, f"team {team_index} config pointer"
            )
        except apf_roster.RosterError as exc:
            raise CustomTeamAppearanceError(str(exc)) from exc
        assert config_offset is not None
        config_index = _table_index(config_offset, config_table, f"team {team_index} config")
        config_for_team.append(config_index)
        for field_relative in (
            CONFIG_HOME_PALETTE_POINTER,
            CONFIG_AWAY_PALETTE_POINTER,
        ):
            try:
                target = apf_roster.resolve_relative(
                    data,
                    config_offset + field_relative,
                    f"team {team_index} palette pointer +0x{field_relative:x}",
                )
            except apf_roster.RosterError as exc:
                raise CustomTeamAppearanceError(str(exc)) from exc
            assert target is not None
            palette_index = _table_index(target, palette_table, "uniform palette")
            palette_owners[palette_index] = palette_owners.get(palette_index, 0) + 1
        for selector_number in range(CONFIG_SELECTOR_COUNT_PER_BANK * 2):
            field = config_offset + selector_number * 4
            try:
                target = apf_roster.resolve_relative(
                    data, field, f"team {team_index} selector pointer {selector_number}"
                )
            except apf_roster.RosterError as exc:
                raise CustomTeamAppearanceError(str(exc)) from exc
            assert target is not None
            selector_index = _table_index(target, selector_table, "uniform selector")
            selector_owners[selector_index] = selector_owners.get(selector_index, 0) + 1

    if len(set(config_for_team)) != len(config_for_team):
        raise CustomTeamAppearanceError("Two APF teams alias one uniform config record")

    resolved: dict[int, _ResolvedTarget] = {}
    for slot in USER_SLOTS:
        config_index = config_for_team[slot]
        if config_index != slot:
            raise CustomTeamAppearanceError(
                f"Custom team slot {slot} no longer owns config record {slot}"
            )
        config_offset = config_table.offset + config_index * config_table.stride

        def pointer(relative: int, table: apf_roster.RootTable, label: str) -> tuple[int, int]:
            try:
                target = apf_roster.resolve_relative(data, config_offset + relative, label)
            except apf_roster.RosterError as exc:
                raise CustomTeamAppearanceError(str(exc)) from exc
            assert target is not None
            return target, _table_index(target, table, label)

        home_palette_offset, home_palette_index = pointer(
            CONFIG_HOME_PALETTE_POINTER, palette_table, "HOME palette"
        )
        away_palette_offset, away_palette_index = pointer(
            CONFIG_AWAY_PALETTE_POINTER, palette_table, "AWAY palette"
        )
        home_helmet_offset, home_helmet_index = pointer(
            SELECTOR_HELMET_SLOT * 4, selector_table, "HOME helmet selector"
        )
        home_logo_offset, home_logo_index = pointer(
            SELECTOR_LOGO_SLOT * 4, selector_table, "HOME crest selector"
        )
        away_base = CONFIG_SELECTOR_COUNT_PER_BANK * 4
        away_helmet_offset, away_helmet_index = pointer(
            away_base + SELECTOR_HELMET_SLOT * 4,
            selector_table,
            "AWAY helmet selector",
        )
        away_logo_offset, away_logo_index = pointer(
            away_base + SELECTOR_LOGO_SLOT * 4,
            selector_table,
            "AWAY crest selector",
        )
        for palette_index in (home_palette_index, away_palette_index):
            if palette_owners.get(palette_index) != 1:
                raise CustomTeamAppearanceError(
                    f"Custom team slot {slot} palette record is not uniquely owned"
                )
        for selector_index in (
            home_helmet_index,
            home_logo_index,
            away_helmet_index,
            away_logo_index,
        ):
            if selector_owners.get(selector_index) != 1:
                raise CustomTeamAppearanceError(
                    f"Custom team slot {slot} selector record is not uniquely owned"
                )
        public = AppearanceTarget(
            asset_id(slot),
            slot,
            config_index,
            home_palette_index,
            away_palette_index,
            home_helmet_index,
            home_logo_index,
            away_helmet_index,
            away_logo_index,
        )
        resolved[slot] = _ResolvedTarget(
            public,
            home_palette_offset,
            away_palette_offset,
            home_helmet_offset,
            home_logo_offset,
            away_helmet_offset,
            away_logo_offset,
        )
    return resolved


def target_metadata(target: AppearanceTarget) -> dict[str, object]:
    return {
        "slot": target.slot,
        "config_index": target.config_index,
        "home_palette_index": target.home_palette_index,
        "away_palette_index": target.away_palette_index,
        "home_helmet_selector_index": target.home_helmet_selector_index,
        "home_logo_selector_index": target.home_logo_selector_index,
        "away_helmet_selector_index": target.away_helmet_selector_index,
        "away_logo_selector_index": target.away_logo_selector_index,
        "palette_color_count": PALETTE_COLOR_COUNT,
        "selector_size": SELECTOR_STRIDE,
        "selector_tail_semantics": "opaque",
    }


def _appearance_from_body(data: bytes, target: _ResolvedTarget) -> CustomTeamAppearance:
    def bank(palette_offset: int, helmet_offset: int, logo_offset: int) -> AppearanceBank:
        palette = tuple(
            struct.unpack_from(">I", data, palette_offset + index * 4)[0]
            for index in range(PALETTE_COLOR_COUNT)
        )
        return AppearanceBank(
            palette,
            data[helmet_offset : helmet_offset + SELECTOR_STRIDE],
            data[logo_offset : logo_offset + SELECTOR_STRIDE],
        )

    return validate_appearance(
        CustomTeamAppearance(
            target.public.slot,
            bank(target.home_palette_offset, target.home_helmet_offset, target.home_logo_offset),
            bank(target.away_palette_offset, target.away_helmet_offset, target.away_logo_offset),
        )
    )


def inspect_appearances(
    index_path: Path,
) -> tuple[tuple[AppearanceTarget, CustomTeamAppearance], ...]:
    try:
        body, _source = apf_roster.load_roster(index_path)
    except (
        OSError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        apf_roster.RosterError,
    ) as exc:
        raise CustomTeamAppearanceError(
            f"Could not read APF custom-team appearances: {exc}"
        ) from exc
    targets = _resolve_targets(body)
    return tuple(
        (targets[slot].public, _appearance_from_body(body, targets[slot]))
        for slot in USER_SLOTS
    )


def read_appearances(index_path: Path) -> tuple[CustomTeamAppearance, ...]:
    return tuple(appearance for _target, appearance in inspect_appearances(index_path))


def read_appearance(index_path: Path, slot: int) -> CustomTeamAppearance:
    slot = _validate_slot(slot)
    return read_appearances(index_path)[slot - USER_SLOTS[0]]


def encode_replacement_payload(value: CustomTeamAppearance) -> bytes:
    value = validate_appearance(value)

    def bank(item: AppearanceBank) -> dict[str, object]:
        return {
            "helmet_selector": item.helmet_selector.hex().upper(),
            "logo_selector": item.logo_selector.hex().upper(),
            "palette": [f"{color:08X}" for color in item.palette],
        }

    return (
        json.dumps(
            {
                "away": bank(value.away),
                "home": bank(value.home),
                "schema": PAYLOAD_SCHEMA,
                "slot": value.slot,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def decode_replacement_payload(data: bytes, target_id: str = "appearance edit") -> CustomTeamAppearance:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CustomTeamAppearanceError(
            f"Custom-team appearance replacement is not valid UTF-8 JSON: {target_id}"
        ) from exc
    if not isinstance(document, dict) or set(document) != {"schema", "slot", "home", "away"}:
        raise CustomTeamAppearanceError(
            f"Custom-team appearance replacement payload is invalid: {target_id}"
        )
    if document.get("schema") != PAYLOAD_SCHEMA:
        raise CustomTeamAppearanceError(
            f"Custom-team appearance replacement schema is invalid: {target_id}"
        )

    def bank(value: object, label: str) -> AppearanceBank:
        if not isinstance(value, dict) or set(value) != {
            "palette", "helmet_selector", "logo_selector"
        }:
            raise CustomTeamAppearanceError(f"{label} replacement bank is invalid: {target_id}")
        palette_value = value.get("palette")
        if not isinstance(palette_value, list):
            raise CustomTeamAppearanceError(f"{label} replacement palette is invalid: {target_id}")
        try:
            palette = tuple(int(item, 16) for item in palette_value)
            helmet = bytes.fromhex(str(value.get("helmet_selector")))
            logo = bytes.fromhex(str(value.get("logo_selector")))
        except (TypeError, ValueError) as exc:
            raise CustomTeamAppearanceError(
                f"{label} replacement contains invalid hex: {target_id}"
            ) from exc
        return AppearanceBank(palette, helmet, logo)

    value = validate_appearance(
        CustomTeamAppearance(
            document.get("slot"),
            bank(document.get("home"), "HOME"),
            bank(document.get("away"), "AWAY"),
        )
    )
    if encode_replacement_payload(value) != data:
        raise CustomTeamAppearanceError(
            f"Custom-team appearance replacement is not canonical: {target_id}"
        )
    return value


def _part_hashes(record: apf_inner.IFFRecord, blocks: list[bytes]) -> Mapping[tuple[int, int], str]:
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
        raise CustomTeamAppearanceError(f"APF roster semantic validation failed: {exc}") from exc


def build_patch(
    index_path: Path,
    replacements: Mapping[int, CustomTeamAppearance],
) -> CustomTeamAppearancePatchResult:
    if not isinstance(replacements, Mapping) or not replacements:
        raise CustomTeamAppearanceError("Select at least one APF custom-team appearance")
    normalized: dict[int, CustomTeamAppearance] = {}
    for supplied_slot, value in replacements.items():
        slot = _validate_slot(supplied_slot)
        appearance = validate_appearance(value)
        if appearance.slot != slot:
            raise CustomTeamAppearanceError("Appearance payload slot does not match its target")
        normalized[slot] = appearance

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
        raise CustomTeamAppearanceError(f"Could not open APF appearance target: {exc}") from exc
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
        raise CustomTeamAppearanceError("APF custom-team appearance IFF/outer ownership changed")
    target_file = record.files[0]
    if (
        target_file.name != apf_roster.INNER_NAME
        or target_file.type_name != apf_roster.INNER_TYPE
        or len(target_file.parts) != 1
        or target_file.parts[0].block_index != 0
    ):
        raise CustomTeamAppearanceError("APF custom-team appearance inner-file ownership changed")
    target_part = target_file.parts[0]
    original_body = original_blocks[0][target_part.offset : target_part.offset + target_part.length]
    if len(original_body) != apf_roster.EXPECTED_LENGTH:
        raise CustomTeamAppearanceError("APF custom-team appearance decoded allocation changed")
    targets = _resolve_targets(original_body)
    _semantic_validate(original_body, entry.size, _sha256(original_entry))

    wanted_body = bytearray(original_body)
    selected_offsets: set[int] = set()
    rows: list[dict[str, object]] = []
    for slot, appearance in sorted(normalized.items()):
        target = targets[slot]
        source = _appearance_from_body(original_body, target)

        def write_bank(
            bank: AppearanceBank,
            palette_offset: int,
            helmet_offset: int,
            logo_offset: int,
        ) -> None:
            palette_bytes = b"".join(struct.pack(">I", color) for color in bank.palette)
            for offset, payload in (
                (palette_offset, palette_bytes),
                (helmet_offset, bank.helmet_selector),
                (logo_offset, bank.logo_selector),
            ):
                owned = set(range(offset, offset + len(payload)))
                if selected_offsets.intersection(owned):
                    raise CustomTeamAppearanceError("Two appearance targets resolve to one byte")
                selected_offsets.update(owned)
                wanted_body[offset : offset + len(payload)] = payload

        write_bank(
            appearance.home,
            target.home_palette_offset,
            target.home_helmet_offset,
            target.home_logo_offset,
        )
        write_bank(
            appearance.away,
            target.away_palette_offset,
            target.away_helmet_offset,
            target.away_logo_offset,
        )
        rows.append(
            {
                "asset_id": target.public.asset_id,
                **target_metadata(target.public),
                "replacement_value_sha256": _sha256(encode_replacement_payload(appearance)),
                "effective_change": source != appearance,
            }
        )

    wanted = bytes(wanted_body)
    changed_offsets = {
        index
        for index, pair in enumerate(zip(original_body, wanted, strict=True))
        if pair[0] != pair[1]
    }
    if not changed_offsets.issubset(selected_offsets):
        raise CustomTeamAppearanceError("Appearance edit changed bytes outside selected records")

    if not changed_offsets:
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
            raise CustomTeamAppearanceError("APF roster block is no longer H7A-compressed")
        patched_block = bytearray(original_blocks[0])
        patched_block[target_part.offset : target_part.offset + target_part.length] = wanted
        new_block = bytes(patched_block)
        try:
            compressed, preservation_metrics = apf_inner.encode_h7a_preserving_tokens(
                original_stored[0][apf_inner.H7A_HEADER_SIZE :],
                original_blocks[0],
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
            raise CustomTeamAppearanceError(f"Could not encode appearance H7A: {exc}") from exc
        if roundtrip != new_block:
            raise CustomTeamAppearanceError("Appearance H7A round trip changed the edit")
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
            raise CustomTeamAppearanceError("APF roster outer allocation has a nonzero tail")
        active = bytes(header) + stored + footer
        if len(active) > entry.size:
            raise CustomTeamAppearanceError(
                "Edited appearance does not fit the fixed ROST allocation"
            )
        rebuilt = active + b"\0" * (entry.size - len(active))
        compressed_size_after = len(stored)
        mode = "patched"
        token_metrics = {
            "strategy": "retail-token-preserving",
            "changed_path_recompressed": True,
            **preservation_metrics,
        }
        memory = apf_texture_patch.BytesReader(rebuilt)
        try:
            reparsed = apf_inner.parse_iff(memory, entry)
            rebuilt_blocks = [apf_inner.decode_block(memory, reparsed, 0, MAX_DECOMPRESSED)]
        except apf_inner.FormatError as exc:
            raise CustomTeamAppearanceError(f"Rebuilt appearance IFF is invalid: {exc}") from exc
        if reparsed.warnings or rebuilt_blocks != [new_block]:
            raise CustomTeamAppearanceError("Rebuilt appearance IFF changed its block")
        before_parts = _part_hashes(record, original_blocks)
        after_parts = _part_hashes(reparsed, rebuilt_blocks)
        if [key for key in before_parts if before_parts[key] != after_parts[key]] != [
            (target_file.index, 0)
        ]:
            raise CustomTeamAppearanceError("Appearance rebuild changed unrelated inner parts")
        rebuilt_part = reparsed.files[0].parts[0]
        verified_body = rebuilt_blocks[0][
            rebuilt_part.offset : rebuilt_part.offset + rebuilt_part.length
        ]
        verified_changes = {
            index
            for index, pair in enumerate(zip(original_body, verified_body, strict=True))
            if pair[0] != pair[1]
        }
        if verified_body != wanted or verified_changes != changed_offsets:
            raise CustomTeamAppearanceError("Rebuilt appearance changed unrelated bytes")
        _semantic_validate(verified_body, entry.size, _sha256(rebuilt))
        verified_targets = _resolve_targets(verified_body)
        for slot, appearance in normalized.items():
            if _appearance_from_body(verified_body, verified_targets[slot]) != appearance:
                raise CustomTeamAppearanceError(
                    f"Rebuilt custom-team appearance slot {slot} differs from its replacement"
                )

    return CustomTeamAppearancePatchResult(
        apf_roster.OUTER_TABLE_INDEX,
        rebuilt,
        {
            "schema": SCHEMA,
            "mode": mode,
            "edit_count": len(rows),
            "effective_edit_count": sum(bool(row["effective_change"]) for row in rows),
            "edits": tuple(rows),
            "source": {
                "outer_entry_index": apf_roster.OUTER_TABLE_INDEX,
                "entry_size": entry.size,
                "entry_sha256": _sha256(original_entry),
                "decoded_sha256": _sha256(original_body),
                "opened_read_only": True,
            },
            "output": {
                "entry_size": len(rebuilt),
                "entry_sha256": _sha256(rebuilt),
                "decoded_sha256": _sha256(wanted),
                "decoded_changed_byte_count": len(changed_offsets),
                "selected_target_count": len(normalized),
                "selected_byte_count": len(selected_offsets),
                "compressed_block_size": compressed_size_after,
                "file_length": file_length_after,
                "h7a_transport": token_metrics,
            },
            "validation": {
                "slots_bounded_to_32_39": True,
                "team_config_pointers_aligned_and_exact": True,
                "palette_and_selector_records_uniquely_owned": True,
                "palette_metadata_bytes_preserved": True,
                "selector_records_exactly_eight_bytes": True,
                "decoded_changes_subset_of_selected_records": True,
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


def _entry_body(entry_bytes: bytes, entry: apf_outer.Entry) -> bytes:
    if len(entry_bytes) != entry.size:
        raise CustomTeamAppearanceError("ROST entry read-back changed fixed allocation size")
    memory = apf_texture_patch.BytesReader(entry_bytes)
    try:
        record = apf_inner.parse_iff(memory, entry)
        block = apf_inner.decode_block(memory, record, 0, MAX_DECOMPRESSED)
    except apf_inner.FormatError as exc:
        raise CustomTeamAppearanceError(f"Could not independently decode ROST: {exc}") from exc
    if (
        record.warnings
        or record.footer is None
        or record.block_count != 1
        or record.file_count != 1
        or len(record.files) != 1
    ):
        raise CustomTeamAppearanceError("Independent ROST IFF ownership check failed")
    target_file = record.files[0]
    if (
        target_file.name != apf_roster.INNER_NAME
        or target_file.type_name != apf_roster.INNER_TYPE
        or len(target_file.parts) != 1
        or target_file.parts[0].block_index != 0
    ):
        raise CustomTeamAppearanceError("Independent ROST inner-file ownership check failed")
    part = target_file.parts[0]
    body = block[part.offset : part.offset + part.length]
    if len(body) != apf_roster.EXPECTED_LENGTH:
        raise CustomTeamAppearanceError("Independent ROST decoded allocation changed")
    return body


def verify_copied_volume(
    source_volume: Path,
    output_volume: Path,
    replacements: Mapping[int, CustomTeamAppearance],
) -> dict[str, object]:
    """Independently reopen and verify one copied 0A; fail closed on tamper."""

    normalized = {
        _validate_slot(slot): validate_appearance(value)
        for slot, value in replacements.items()
    }
    if not normalized:
        raise CustomTeamAppearanceError("Select at least one appearance to verify")
    try:
        archive = apf_outer.parse_archive(source_volume)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
    except (OSError, IndexError, apf_outer.FormatError) as exc:
        raise CustomTeamAppearanceError(f"Could not reopen source archive: {exc}") from exc
    if (
        len(entry.segments) != 1
        or entry.segments[0].pack_name != "0A"
        or entry.size <= 0
    ):
        raise CustomTeamAppearanceError("Independent ROST outer ownership changed")
    offset = entry.segments[0].pack_offset
    try:
        source_stat = source_volume.stat()
        output_stat = output_volume.stat()
        if not source_volume.is_file() or not output_volume.is_file():
            raise CustomTeamAppearanceError("Source and output 0A must be regular files")
        if source_stat.st_size != output_stat.st_size:
            raise CustomTeamAppearanceError("Copied 0A size differs from its source")
        with source_volume.open("rb") as stream:
            stream.seek(offset)
            source_entry = stream.read(entry.size)
        with output_volume.open("rb") as stream:
            stream.seek(offset)
            output_entry = stream.read(entry.size)
    except OSError as exc:
        raise CustomTeamAppearanceError(f"Could not independently read copied 0A: {exc}") from exc
    source_body = _entry_body(source_entry, entry)
    output_body = _entry_body(output_entry, entry)
    source_targets = _resolve_targets(source_body)
    output_targets = _resolve_targets(output_body)
    allowed: set[int] = set()
    for slot, wanted in normalized.items():
        source_target = source_targets[slot]
        output_target = output_targets[slot]
        if source_target.public != output_target.public:
            raise CustomTeamAppearanceError(
                f"Copied slot {slot} pointer ownership changed"
            )
        for start, length in (
            (source_target.home_palette_offset, 40),
            (source_target.away_palette_offset, 40),
            (source_target.home_helmet_offset, 8),
            (source_target.home_logo_offset, 8),
            (source_target.away_helmet_offset, 8),
            (source_target.away_logo_offset, 8),
        ):
            allowed.update(range(start, start + length))
        if _appearance_from_body(output_body, output_target) != wanted:
            raise CustomTeamAppearanceError(
                f"Copied slot {slot} differs from its requested appearance"
            )
    changes = {
        index
        for index, pair in enumerate(zip(source_body, output_body, strict=True))
        if pair[0] != pair[1]
    }
    if not changes.issubset(allowed):
        raise CustomTeamAppearanceError("Copied ROST changed decoded bytes outside selected records")
    _semantic_validate(output_body, entry.size, _sha256(output_entry))

    try:
        source_descriptor = source_volume.open("rb")
        output_descriptor = output_volume.open("rb")
        try:
            source_prefix = hashlib.sha256(source_descriptor.read(offset)).hexdigest()
            output_prefix = hashlib.sha256(output_descriptor.read(offset)).hexdigest()
            source_descriptor.seek(offset + entry.size)
            output_descriptor.seek(offset + entry.size)
            source_suffix = hashlib.sha256(source_descriptor.read()).hexdigest()
            output_suffix = hashlib.sha256(output_descriptor.read()).hexdigest()
        finally:
            source_descriptor.close()
            output_descriptor.close()
    except OSError as exc:
        raise CustomTeamAppearanceError(f"Could not verify copied 0A boundaries: {exc}") from exc
    if source_prefix != output_prefix or source_suffix != output_suffix:
        raise CustomTeamAppearanceError("Copied 0A changed bytes outside the ROST allocation")
    return {
        "source_volume_sha256": apf_texture_patch.sha256_file(source_volume),
        "output_volume_sha256": apf_texture_patch.sha256_file(output_volume),
        "source_entry_sha256": _sha256(source_entry),
        "output_entry_sha256": _sha256(output_entry),
        "source_decoded_sha256": _sha256(source_body),
        "output_decoded_sha256": _sha256(output_body),
        "decoded_changed_byte_count": len(changes),
        "changed_bytes_subset_of_selected_records": True,
        "outside_roster_allocation_bit_exact": True,
        "source_reopened_read_only": True,
        "output_reopened_and_redecoded": True,
        "semantic_roster_reparse_passed": True,
        "fixed_volume_and_entry_allocations_preserved": True,
    }


def verify_output_appearances(
    layout_index: Path,
    output_volume: Path,
    replacements: Mapping[int, CustomTeamAppearance],
) -> dict[str, object]:
    """Decode the output ROST by source layout and prove requested appearances."""

    normalized = {
        _validate_slot(slot): validate_appearance(value)
        for slot, value in replacements.items()
    }
    if not normalized:
        raise CustomTeamAppearanceError("Select at least one appearance to verify")
    try:
        archive = apf_outer.parse_archive(layout_index)
        entry = archive.entries[apf_roster.OUTER_TABLE_INDEX]
        if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
            raise CustomTeamAppearanceError("Output appearance ROST ownership changed")
        with output_volume.open("rb") as stream:
            stream.seek(entry.segments[0].pack_offset)
            entry_bytes = stream.read(entry.size)
    except (OSError, IndexError, apf_outer.FormatError) as exc:
        raise CustomTeamAppearanceError(f"Could not reopen output appearance: {exc}") from exc
    body = _entry_body(entry_bytes, entry)
    targets = _resolve_targets(body)
    for slot, appearance in normalized.items():
        if _appearance_from_body(body, targets[slot]) != appearance:
            raise CustomTeamAppearanceError(
                f"Output custom-team appearance slot {slot} differs from its replacement"
            )
    _semantic_validate(body, entry.size, _sha256(entry_bytes))
    return {
        "output_entry_sha256": _sha256(entry_bytes),
        "output_decoded_sha256": _sha256(body),
        "verified_slots": tuple(sorted(normalized)),
        "output_reopened_and_redecoded": True,
        "pointer_ownership_reproved": True,
        "semantic_roster_reparse_passed": True,
    }


def write_verified_copied_volume(
    source_volume: Path,
    output_volume: Path,
    replacements: Mapping[int, CustomTeamAppearance],
) -> dict[str, object]:
    """Build, copy to a new 0A, then independently reopen and verify it."""

    result = build_patch(source_volume, replacements)
    try:
        archive = apf_outer.parse_archive(source_volume)
        entry = archive.entries[result.outer_index]
        copied = apf_texture_patch._write_copied_volume(
            source_volume, output_volume, entry, result.entry_bytes
        )
        verified = verify_copied_volume(source_volume, output_volume, replacements)
    except (
        OSError,
        IndexError,
        apf_outer.FormatError,
        apf_texture_patch.PatchError,
    ) as exc:
        raise CustomTeamAppearanceError(f"Could not stage verified copied 0A: {exc}") from exc
    if (
        copied.get("source_volume_sha256_before")
        != copied.get("source_volume_sha256_after")
        or copied.get("source_volume_sha256_after")
        != verified.get("source_volume_sha256")
        or copied.get("output_volume_sha256")
        != verified.get("output_volume_sha256")
        or copied.get("replacement_read_back_sha256")
        != result.manifest.get("output", {}).get("entry_sha256")
    ):
        raise CustomTeamAppearanceError("Copied 0A provenance receipt changed")
    return {
        "schema": "apf2k8_custom_team_appearance_copied_volume/v1",
        "source": {
            "path": str(source_volume),
            "sha256": verified["source_volume_sha256"],
            "opened_read_only": True,
        },
        "output": {
            "path": str(output_volume),
            "sha256": verified["output_volume_sha256"],
            "created_exclusively": True,
        },
        "writer": result.manifest,
        "copy": copied,
        "independent_verification": verified,
        "distribution": {
            "copied_volume_is_private_user_owned_game_data": True,
            "copied_volume_must_not_ship_in_projects_or_releases": True,
            "receipt_contains_retail_or_replacement_bytes": False,
        },
    }


def patch_private_staged_volume(
    staged_volume: Path,
    replacements: Mapping[int, CustomTeamAppearance],
) -> dict[str, object]:
    """Patch one exclusively-owned temporary 0A inside a larger transaction.

    This route exists so the team-logo package, logo-cache, and appearance
    writers can share two full-volume copies instead of consuming a third
    1.1-GB temporary.  It refuses links and multiply-linked files; callers must
    have just created this private stage and delete it if the transaction fails.
    """

    try:
        metadata = staged_volume.lstat()
    except OSError as exc:
        raise CustomTeamAppearanceError(f"Could not inspect private 0A stage: {exc}") from exc
    if not staged_volume.is_file() or staged_volume.is_symlink() or metadata.st_nlink != 1:
        raise CustomTeamAppearanceError(
            "Appearance staging requires one exclusively-owned temporary 0A copy"
        )
    result = build_patch(staged_volume, replacements)
    try:
        archive = apf_outer.parse_archive(staged_volume)
        entry = archive.entries[result.outer_index]
    except (OSError, IndexError, apf_outer.FormatError) as exc:
        raise CustomTeamAppearanceError(f"Could not map private 0A stage: {exc}") from exc
    if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
        raise CustomTeamAppearanceError("Private appearance stage ROST ownership changed")
    offset = entry.segments[0].pack_offset
    before_volume_sha256 = apf_texture_patch.sha256_file(staged_volume)
    try:
        descriptor = os.open(
            staged_volume,
            os.O_RDWR
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_BINARY", 0),
        )
        try:
            opened = os.fstat(descriptor)
            if (
                opened.st_dev != metadata.st_dev
                or opened.st_ino != metadata.st_ino
                or opened.st_size != metadata.st_size
                or opened.st_nlink != 1
            ):
                raise CustomTeamAppearanceError("Private 0A stage changed before write")
            original_entry = apf_texture_patch._pread_exact(
                descriptor, entry.size, offset
            )
            apf_texture_patch._pwrite_all(
                descriptor, result.entry_bytes, offset
            )
            os.fsync(descriptor)
            read_back = apf_texture_patch._pread_exact(
                descriptor, entry.size, offset
            )
            after = os.fstat(descriptor)
            if after.st_size != opened.st_size or read_back != result.entry_bytes:
                raise CustomTeamAppearanceError("Private appearance stage read-back failed")
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise CustomTeamAppearanceError(f"Could not write private appearance stage: {exc}") from exc
    source_body = _entry_body(original_entry, entry)
    output_body = _entry_body(read_back, entry)
    targets = _resolve_targets(output_body)
    allowed: set[int] = set()
    for slot, appearance in replacements.items():
        slot = _validate_slot(slot)
        appearance = validate_appearance(appearance)
        target = targets[slot]
        if _appearance_from_body(output_body, target) != appearance:
            raise CustomTeamAppearanceError(
                f"Private appearance stage slot {slot} differs from its replacement"
            )
        for start, length in (
            (target.home_palette_offset, 40),
            (target.away_palette_offset, 40),
            (target.home_helmet_offset, 8),
            (target.home_logo_offset, 8),
            (target.away_helmet_offset, 8),
            (target.away_logo_offset, 8),
        ):
            allowed.update(range(start, start + length))
    changes = {
        index
        for index, pair in enumerate(zip(source_body, output_body, strict=True))
        if pair[0] != pair[1]
    }
    if not changes.issubset(allowed):
        raise CustomTeamAppearanceError(
            "Private appearance stage changed decoded bytes outside selected records"
        )
    return {
        "schema": "apf2k8_custom_team_appearance_private_stage/v1",
        "writer": result.manifest,
        "staged_volume": {
            "size": metadata.st_size,
            "sha256_before": before_volume_sha256,
            "sha256_after": apf_texture_patch.sha256_file(staged_volume),
            "exclusively_owned_regular_file": True,
        },
        "verification": {
            "entry_read_back_exact": True,
            "entry_reopened_and_redecoded": True,
            "decoded_changed_byte_count": len(changes),
            "decoded_changes_subset_of_selected_records": True,
            "fixed_volume_and_entry_allocations_preserved": True,
        },
    }


__all__ = [
    "AppearanceBank",
    "AppearanceTarget",
    "CustomTeamAppearance",
    "CustomTeamAppearanceError",
    "CustomTeamAppearancePatchResult",
    "EAGLES_2017_LOGO_ROUTING_TAIL",
    "EAGLES_2017_PALETTE",
    "EAGLES_CREST_CATALOG_INDEX",
    "EAGLES_SHELL_PALETTE_INDEX",
    "EDIT_ID_PREFIX",
    "PAYLOAD_SCHEMA",
    "SCHEMA",
    "USER_SLOTS",
    "asset_id",
    "build_patch",
    "decode_replacement_payload",
    "eagles_2017_preset",
    "encode_replacement_payload",
    "inspect_appearances",
    "parse_asset_id",
    "patch_private_staged_volume",
    "read_appearance",
    "read_appearances",
    "target_metadata",
    "validate_appearance",
    "verify_copied_volume",
    "verify_output_appearances",
    "write_verified_copied_volume",
]


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="source APF 0A")
    parser.add_argument(
        "--recipe",
        required=True,
        type=Path,
        help="canonical replacement-only appearance JSON",
    )
    parser.add_argument(
        "--output-volume", required=True, type=Path, help="new copied 0A"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.manifest.exists() or args.manifest.is_symlink():
            raise CustomTeamAppearanceError(
                f"refusing to overwrite existing manifest: {args.manifest}"
            )
        appearance = decode_replacement_payload(
            args.recipe.read_bytes(), str(args.recipe)
        )
        receipt = write_verified_copied_volume(
            args.index, args.output_volume, {appearance.slot: appearance}
        )
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        with args.manifest.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, CustomTeamAppearanceError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
