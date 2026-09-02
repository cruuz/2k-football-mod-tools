#!/usr/bin/env python3
"""Exact APF 2K8 per-uniform facemask and Team-turtleneck color writer.

All forty on-disc team uniform configurations are supported. HOME and AWAY
each select one of the first ten colors in their own palette for the facemask
bar and for players whose turtleneck choice is ``Team``. The writer changes
only byte 6 of selector slot 3 and byte 2 of selector slot 0. Palette records,
their final eight opaque metadata bytes, and every nonselected selector byte
remain bit-exact.

The source archive is opened read-only. Returned entry bytes are private
user-owned game data and must never ship in a project or release artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
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


SCHEMA = "apf2k8_uniform_equipment_color_patch/v1"
PAYLOAD_SCHEMA = "apf2k8_uniform_equipment_color_replacement/v1"
EDIT_ID_PREFIX = "apf:uniform-equipment-colors"
MAX_DECOMPRESSED = 16 * 1024 * 1024
TEAM_COUNT = 40
PALETTE_COLOR_COUNT = 10
BUILT_IN_TEAM_NAMES = (
    "Americans", "Assassins", "Beasts", "Cobras", "Cougars", "Cyclones",
    "Federals", "Firebirds", "Gunslingers", "Indians", "Iron Men", "Knights",
    "Legends", "Minutemen", "Red Dogs", "Rhinos", "Rollers", "Rustlers",
    "Sailors", "Scorpions", "Sharks", "Top Guns", "Wasps", "Werewolves",
)

TEAM_TABLE_INDEX = 4
PALETTE_TABLE_INDEX = 16
SELECTOR_TABLE_INDEX = 17
CONFIG_TABLE_INDEX = 19
TEAM_CONFIG_POINTER = 0xBC
CONFIG_HOME_PALETTE_POINTER = 0x70
CONFIG_AWAY_PALETTE_POINTER = 0x74
SELECTORS_PER_BANK = 14
FACEMASK_SELECTOR_SLOT = 3
FACEMASK_SELECTOR_BYTE = 6
TURTLENECK_SELECTOR_SLOT = 0
TURTLENECK_SELECTOR_BYTE = 2
PALETTE_STRIDE = 0x30
SELECTOR_STRIDE = 0x08
CONFIG_STRIDE = 0x98


class UniformEquipmentColorError(ValueError):
    """The source or edit left the exact pointer-derived color contract."""


@dataclass(frozen=True)
class EquipmentColorBank:
    facemask_palette_index: int
    team_turtleneck_palette_index: int


@dataclass(frozen=True)
class UniformEquipmentColors:
    team_index: int
    home: EquipmentColorBank
    away: EquipmentColorBank


@dataclass(frozen=True)
class UniformEquipmentColorTarget:
    asset_id: str
    team_index: int
    config_index: int
    home_palette_index: int
    away_palette_index: int
    home_facemask_selector_index: int
    away_facemask_selector_index: int
    home_turtleneck_selector_index: int
    away_turtleneck_selector_index: int


@dataclass(frozen=True)
class UniformEquipmentColorInspection:
    target: UniformEquipmentColorTarget
    value: UniformEquipmentColors
    home_palette: tuple[int, ...]
    away_palette: tuple[int, ...]


@dataclass(frozen=True)
class UniformEquipmentColorPatchResult:
    outer_index: int
    entry_bytes: bytes
    manifest: Mapping[str, object]


@dataclass(frozen=True)
class _ResolvedTarget:
    public: UniformEquipmentColorTarget
    home_palette_offset: int
    away_palette_offset: int
    home_facemask_offset: int
    away_facemask_offset: int
    home_turtleneck_offset: int
    away_turtleneck_offset: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_team_index(value: object) -> int:
    if type(value) is not int or not 0 <= value < TEAM_COUNT:
        raise UniformEquipmentColorError("APF team index must be an integer from 0 to 39")
    return value


def _validate_palette_index(value: object, label: str) -> int:
    if type(value) is not int or not 0 <= value < PALETTE_COLOR_COUNT:
        raise UniformEquipmentColorError(f"{label} palette index must be an integer from 0 to 9")
    return value


def validate_colors(value: object) -> UniformEquipmentColors:
    if not isinstance(value, UniformEquipmentColors):
        raise UniformEquipmentColorError("Uniform equipment-color value is malformed")
    team_index = _validate_team_index(value.team_index)

    def bank(source: object, label: str) -> EquipmentColorBank:
        if not isinstance(source, EquipmentColorBank):
            raise UniformEquipmentColorError(f"{label} equipment-color bank is malformed")
        return EquipmentColorBank(
            _validate_palette_index(source.facemask_palette_index, f"{label} facemask"),
            _validate_palette_index(
                source.team_turtleneck_palette_index, f"{label} Team-turtleneck"
            ),
        )

    return UniformEquipmentColors(team_index, bank(value.home, "HOME"), bank(value.away, "AWAY"))


def asset_id(team_index: int) -> str:
    return f"{EDIT_ID_PREFIX}:{_validate_team_index(team_index)}"


def team_label(team_index: int) -> str:
    team_index = _validate_team_index(team_index)
    if team_index < len(BUILT_IN_TEAM_NAMES):
        return f"{BUILT_IN_TEAM_NAMES[team_index]} · slot {team_index}"
    return f"Custom / unused team slot {team_index}"


def parse_asset_id(value: str) -> int:
    if not isinstance(value, str):
        raise UniformEquipmentColorError("APF uniform equipment-color asset ID must be text")
    fields = value.split(":")
    if len(fields) != 3 or fields[:2] != ["apf", "uniform-equipment-colors"]:
        raise UniformEquipmentColorError(f"Unknown APF uniform equipment-color asset: {value}")
    try:
        team_index = int(fields[2])
    except ValueError as exc:
        raise UniformEquipmentColorError(
            f"Malformed APF uniform equipment-color asset: {value}"
        ) from exc
    if asset_id(team_index) != value:
        raise UniformEquipmentColorError(
            f"Malformed APF uniform equipment-color asset: {value}"
        )
    return team_index


def encode_replacement_payload(value: UniformEquipmentColors) -> bytes:
    value = validate_colors(value)

    def bank(item: EquipmentColorBank) -> dict[str, int]:
        return {
            "facemask_palette_index": item.facemask_palette_index,
            "team_turtleneck_palette_index": item.team_turtleneck_palette_index,
        }

    return (
        json.dumps(
            {
                "away": bank(value.away),
                "home": bank(value.home),
                "schema": PAYLOAD_SCHEMA,
                "team_index": value.team_index,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def decode_replacement_payload(
    data: bytes, target_id: str = "uniform equipment-color edit"
) -> UniformEquipmentColors:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UniformEquipmentColorError(
            f"Uniform equipment-color replacement is not valid UTF-8 JSON: {target_id}"
        ) from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema", "team_index", "home", "away"}
        or document.get("schema") != PAYLOAD_SCHEMA
    ):
        raise UniformEquipmentColorError(
            f"Uniform equipment-color replacement payload is invalid: {target_id}"
        )

    def bank(source: object, label: str) -> EquipmentColorBank:
        if not isinstance(source, dict) or set(source) != {
            "facemask_palette_index",
            "team_turtleneck_palette_index",
        }:
            raise UniformEquipmentColorError(
                f"{label} uniform equipment-color bank is invalid: {target_id}"
            )
        return EquipmentColorBank(
            source.get("facemask_palette_index"),
            source.get("team_turtleneck_palette_index"),
        )

    value = validate_colors(
        UniformEquipmentColors(
            document.get("team_index"),
            bank(document.get("home"), "HOME"),
            bank(document.get("away"), "AWAY"),
        )
    )
    if encode_replacement_payload(value) != data:
        raise UniformEquipmentColorError(
            f"Uniform equipment-color replacement is not canonical: {target_id}"
        )
    return value


def _table_index(target: int, table: apf_roster.RootTable, label: str) -> int:
    if table.stride is None or target < table.offset:
        raise UniformEquipmentColorError(f"{label} does not resolve inside its table")
    index, remainder = divmod(target - table.offset, table.stride)
    if remainder or not 0 <= index < table.count:
        raise UniformEquipmentColorError(f"{label} is not an aligned in-table record")
    return index


def _resolve_targets(data: bytes) -> dict[int, _ResolvedTarget]:
    try:
        tables, _root = apf_roster.parse_root(data)
    except apf_roster.RosterError as exc:
        raise UniformEquipmentColorError(f"Could not parse the APF ROST root: {exc}") from exc
    team_table = tables[TEAM_TABLE_INDEX]
    palette_table = tables[PALETTE_TABLE_INDEX]
    selector_table = tables[SELECTOR_TABLE_INDEX]
    config_table = tables[CONFIG_TABLE_INDEX]
    if (
        team_table.count != TEAM_COUNT
        or team_table.stride != apf_roster.TEAM_STRIDE
        or palette_table.count != 266
        or palette_table.stride != PALETTE_STRIDE
        or selector_table.count != 3724
        or selector_table.stride != SELECTOR_STRIDE
        or config_table.count != TEAM_COUNT
        or config_table.stride != CONFIG_STRIDE
    ):
        raise UniformEquipmentColorError("APF uniform equipment-color tables changed")

    palette_owners: dict[int, int] = {}
    selector_owners: dict[int, int] = {}
    config_for_team: list[int] = []
    for team_index in range(TEAM_COUNT):
        team_offset = team_table.offset + team_index * team_table.stride
        try:
            config_offset = apf_roster.resolve_relative(
                data, team_offset + TEAM_CONFIG_POINTER, f"team {team_index} config pointer"
            )
        except apf_roster.RosterError as exc:
            raise UniformEquipmentColorError(str(exc)) from exc
        assert config_offset is not None
        config_index = _table_index(config_offset, config_table, f"team {team_index} config")
        config_for_team.append(config_index)
        for relative in (CONFIG_HOME_PALETTE_POINTER, CONFIG_AWAY_PALETTE_POINTER):
            try:
                palette_offset = apf_roster.resolve_relative(
                    data, config_offset + relative, f"team {team_index} palette pointer"
                )
            except apf_roster.RosterError as exc:
                raise UniformEquipmentColorError(str(exc)) from exc
            assert palette_offset is not None
            index = _table_index(palette_offset, palette_table, "uniform palette")
            palette_owners[index] = palette_owners.get(index, 0) + 1
        for selector_number in range(SELECTORS_PER_BANK * 2):
            try:
                selector_offset = apf_roster.resolve_relative(
                    data,
                    config_offset + selector_number * 4,
                    f"team {team_index} selector pointer {selector_number}",
                )
            except apf_roster.RosterError as exc:
                raise UniformEquipmentColorError(str(exc)) from exc
            assert selector_offset is not None
            index = _table_index(selector_offset, selector_table, "uniform selector")
            selector_owners[index] = selector_owners.get(index, 0) + 1

    if config_for_team != list(range(TEAM_COUNT)):
        raise UniformEquipmentColorError("APF teams no longer own their exact uniform config records")

    resolved: dict[int, _ResolvedTarget] = {}
    for team_index, config_index in enumerate(config_for_team):
        config_offset = config_table.offset + config_index * config_table.stride

        def pointer(relative: int, table: apf_roster.RootTable, label: str) -> tuple[int, int]:
            try:
                target = apf_roster.resolve_relative(data, config_offset + relative, label)
            except apf_roster.RosterError as exc:
                raise UniformEquipmentColorError(str(exc)) from exc
            assert target is not None
            return target, _table_index(target, table, label)

        home_palette_offset, home_palette_index = pointer(
            CONFIG_HOME_PALETTE_POINTER, palette_table, "HOME palette"
        )
        away_palette_offset, away_palette_index = pointer(
            CONFIG_AWAY_PALETTE_POINTER, palette_table, "AWAY palette"
        )
        away_base = SELECTORS_PER_BANK * 4
        home_facemask_record, home_facemask_index = pointer(
            FACEMASK_SELECTOR_SLOT * 4, selector_table, "HOME facemask selector"
        )
        away_facemask_record, away_facemask_index = pointer(
            away_base + FACEMASK_SELECTOR_SLOT * 4,
            selector_table,
            "AWAY facemask selector",
        )
        home_turtleneck_record, home_turtleneck_index = pointer(
            TURTLENECK_SELECTOR_SLOT * 4, selector_table, "HOME turtleneck selector"
        )
        away_turtleneck_record, away_turtleneck_index = pointer(
            away_base + TURTLENECK_SELECTOR_SLOT * 4,
            selector_table,
            "AWAY turtleneck selector",
        )
        selector_base = away_turtleneck_index
        if (
            away_palette_index % 2
            or not 0 <= away_palette_index // 2 < TEAM_COUNT
            or home_palette_index != away_palette_index + 1
            or selector_base % (SELECTORS_PER_BANK * 2)
            or not 0 <= selector_base // (SELECTORS_PER_BANK * 2) < TEAM_COUNT
            or home_facemask_index != selector_base + 17
            or away_facemask_index != selector_base + 3
            or home_turtleneck_index != selector_base + 14
        ):
            raise UniformEquipmentColorError(
                f"Team {team_index} uniform equipment-color pointer bank changed"
            )
        for palette_index in (home_palette_index, away_palette_index):
            if palette_owners.get(palette_index) != 1:
                raise UniformEquipmentColorError(
                    f"Team {team_index} palette record is not uniquely owned"
                )
        for selector_index in (
            home_facemask_index,
            away_facemask_index,
            home_turtleneck_index,
            away_turtleneck_index,
        ):
            if selector_owners.get(selector_index) != 1:
                raise UniformEquipmentColorError(
                    f"Team {team_index} selector record is not uniquely owned"
                )
        public = UniformEquipmentColorTarget(
            asset_id(team_index),
            team_index,
            config_index,
            home_palette_index,
            away_palette_index,
            home_facemask_index,
            away_facemask_index,
            home_turtleneck_index,
            away_turtleneck_index,
        )
        resolved[team_index] = _ResolvedTarget(
            public,
            home_palette_offset,
            away_palette_offset,
            home_facemask_record + FACEMASK_SELECTOR_BYTE,
            away_facemask_record + FACEMASK_SELECTOR_BYTE,
            home_turtleneck_record + TURTLENECK_SELECTOR_BYTE,
            away_turtleneck_record + TURTLENECK_SELECTOR_BYTE,
        )
    return resolved


def target_metadata(target: UniformEquipmentColorTarget) -> dict[str, object]:
    return {
        "team_index": target.team_index,
        "config_index": target.config_index,
        "home_palette_index": target.home_palette_index,
        "away_palette_index": target.away_palette_index,
        "home_facemask_selector_index": target.home_facemask_selector_index,
        "away_facemask_selector_index": target.away_facemask_selector_index,
        "home_turtleneck_selector_index": target.home_turtleneck_selector_index,
        "away_turtleneck_selector_index": target.away_turtleneck_selector_index,
        "palette_color_count": PALETTE_COLOR_COUNT,
        "facemask_selector_slot": FACEMASK_SELECTOR_SLOT,
        "facemask_selector_byte": FACEMASK_SELECTOR_BYTE,
        "turtleneck_selector_slot": TURTLENECK_SELECTOR_SLOT,
        "turtleneck_selector_byte": TURTLENECK_SELECTOR_BYTE,
        "visor_scope": "per_player_none_clear_dark_only",
    }


def _palette(data: bytes, offset: int) -> tuple[int, ...]:
    return tuple(
        struct.unpack_from(">I", data, offset + index * 4)[0]
        for index in range(PALETTE_COLOR_COUNT)
    )


def _value_from_body(data: bytes, target: _ResolvedTarget) -> UniformEquipmentColors:
    return validate_colors(
        UniformEquipmentColors(
            target.public.team_index,
            EquipmentColorBank(
                data[target.home_facemask_offset], data[target.home_turtleneck_offset]
            ),
            EquipmentColorBank(
                data[target.away_facemask_offset], data[target.away_turtleneck_offset]
            ),
        )
    )


def inspect_colors(index_path: Path) -> tuple[UniformEquipmentColorInspection, ...]:
    try:
        body, _source = apf_roster.load_roster(index_path)
    except (OSError, apf_inner.FormatError, apf_outer.FormatError, apf_roster.RosterError) as exc:
        raise UniformEquipmentColorError(
            f"Could not read APF uniform equipment colors: {exc}"
        ) from exc
    targets = _resolve_targets(body)
    return tuple(
        UniformEquipmentColorInspection(
            targets[team_index].public,
            _value_from_body(body, targets[team_index]),
            _palette(body, targets[team_index].home_palette_offset),
            _palette(body, targets[team_index].away_palette_offset),
        )
        for team_index in range(TEAM_COUNT)
    )


def read_colors(index_path: Path, team_index: int) -> UniformEquipmentColors:
    team_index = _validate_team_index(team_index)
    return inspect_colors(index_path)[team_index].value


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
        raise UniformEquipmentColorError(
            f"APF roster semantic validation failed: {exc}"
        ) from exc


def _entry_body(entry_bytes: bytes, entry: apf_outer.Entry) -> bytes:
    memory = apf_texture_patch.BytesReader(entry_bytes)
    try:
        record = apf_inner.parse_iff(memory, entry)
        block = apf_inner.decode_block(memory, record, 0, MAX_DECOMPRESSED)
    except apf_inner.FormatError as exc:
        raise UniformEquipmentColorError(f"Could not decode rebuilt APF ROST: {exc}") from exc
    part = record.files[0].parts[0]
    return block[part.offset : part.offset + part.length]


def build_patch(
    index_path: Path,
    replacements: Mapping[int, UniformEquipmentColors],
) -> UniformEquipmentColorPatchResult:
    if not isinstance(replacements, Mapping) or not replacements:
        raise UniformEquipmentColorError("Select at least one APF uniform equipment-color edit")
    normalized: dict[int, UniformEquipmentColors] = {}
    for supplied_team, supplied_value in replacements.items():
        team_index = _validate_team_index(supplied_team)
        value = validate_colors(supplied_value)
        if value.team_index != team_index:
            raise UniformEquipmentColorError("Equipment-color payload team does not match target")
        normalized[team_index] = value

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
        raise UniformEquipmentColorError(
            f"Could not open APF uniform equipment-color target: {exc}"
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
        raise UniformEquipmentColorError("APF uniform equipment-color IFF/outer ownership changed")
    target_file = record.files[0]
    if (
        target_file.name != apf_roster.INNER_NAME
        or target_file.type_name != apf_roster.INNER_TYPE
        or len(target_file.parts) != 1
        or target_file.parts[0].block_index != 0
    ):
        raise UniformEquipmentColorError("APF uniform equipment-color inner-file ownership changed")
    target_part = target_file.parts[0]
    original_body = original_blocks[0][target_part.offset : target_part.offset + target_part.length]
    if len(original_body) != apf_roster.EXPECTED_LENGTH:
        raise UniformEquipmentColorError("APF uniform equipment-color decoded allocation changed")
    targets = _resolve_targets(original_body)
    _semantic_validate(original_body, entry.size, _sha256(original_entry))

    wanted_body = bytearray(original_body)
    selected_offsets: set[int] = set()
    rows: list[dict[str, object]] = []
    for team_index, value in sorted(normalized.items()):
        target = targets[team_index]
        source = _value_from_body(original_body, target)
        writes = (
            (target.home_facemask_offset, value.home.facemask_palette_index),
            (target.home_turtleneck_offset, value.home.team_turtleneck_palette_index),
            (target.away_facemask_offset, value.away.facemask_palette_index),
            (target.away_turtleneck_offset, value.away.team_turtleneck_palette_index),
        )
        for offset, selected_index in writes:
            if offset in selected_offsets:
                raise UniformEquipmentColorError("Two equipment-color targets resolve to one byte")
            selected_offsets.add(offset)
            wanted_body[offset] = selected_index
        rows.append(
            {
                "asset_id": target.public.asset_id,
                **target_metadata(target.public),
                "replacement_value_sha256": _sha256(encode_replacement_payload(value)),
                "effective_change": source != value,
            }
        )

    wanted = bytes(wanted_body)
    changed_offsets = {
        offset
        for offset, pair in enumerate(zip(original_body, wanted, strict=True))
        if pair[0] != pair[1]
    }
    if not changed_offsets.issubset(selected_offsets):
        raise UniformEquipmentColorError(
            "Uniform equipment-color edit changed bytes outside exact selected selectors"
        )

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
            raise UniformEquipmentColorError("APF roster block is no longer H7A-compressed")
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
            roundtrip = apf_inner.decompress_h7a(compressed, len(new_block), descriptor.wrapper.shift)
        except apf_inner.FormatError as exc:
            raise UniformEquipmentColorError(
                f"Could not encode uniform equipment-color H7A: {exc}"
            ) from exc
        if roundtrip != new_block:
            raise UniformEquipmentColorError("Uniform equipment-color H7A round trip changed the edit")
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
            raise UniformEquipmentColorError("APF roster outer allocation has a nonzero tail")
        active = bytes(header) + stored + footer
        if len(active) > entry.size:
            raise UniformEquipmentColorError(
                "Edited equipment colors do not fit the fixed ROST allocation"
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
            rebuilt_blocks = [apf_inner.decode_block(memory, reparsed, 0, MAX_DECOMPRESSED)]
        except apf_inner.FormatError as exc:
            raise UniformEquipmentColorError(
                f"Rebuilt uniform equipment-color IFF is invalid: {exc}"
            ) from exc
        if reparsed.warnings or rebuilt_blocks != [new_block]:
            raise UniformEquipmentColorError("Rebuilt uniform equipment-color IFF changed its block")
        if [
            key
            for key, before in _part_hashes(record, original_blocks).items()
            if before != _part_hashes(reparsed, rebuilt_blocks)[key]
        ] != [(target_file.index, 0)]:
            raise UniformEquipmentColorError("Equipment-color rebuild changed unrelated inner parts")
        verified_body = _entry_body(rebuilt, entry)
        verified_changes = {
            offset
            for offset, pair in enumerate(zip(original_body, verified_body, strict=True))
            if pair[0] != pair[1]
        }
        if verified_body != wanted or verified_changes != changed_offsets:
            raise UniformEquipmentColorError("Rebuilt equipment colors changed unrelated bytes")
        _semantic_validate(verified_body, entry.size, _sha256(rebuilt))
        verified_targets = _resolve_targets(verified_body)
        for team_index, value in normalized.items():
            if _value_from_body(verified_body, verified_targets[team_index]) != value:
                raise UniformEquipmentColorError(
                    f"Rebuilt team {team_index} equipment colors differ from replacement"
                )

    return UniformEquipmentColorPatchResult(
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
                "all_40_team_configs_pointer_derived": True,
                "palette_and_selector_records_uniquely_owned": True,
                "only_selector_slot3_byte6_and_slot0_byte2_selected": True,
                "palette_bytes_preserved": True,
                "palette_metadata_bytes_28_2f_preserved": True,
                "nonselected_selector_bytes_preserved": True,
                "palette_index_domain_0_9": True,
                "visor_remains_per_player_none_clear_dark": True,
                "decoded_changes_subset_of_selected_bytes": True,
                "h7a_round_trip_exact": True,
            },
            "distribution": {
                "entry_bytes_are_private_user_owned_game_data": True,
                "entry_bytes_must_not_ship_in_projects_or_releases": True,
                "manifest_contains_retail_bytes": False,
            },
        },
    )


__all__ = [
    "EquipmentColorBank",
    "UniformEquipmentColorError",
    "UniformEquipmentColorInspection",
    "UniformEquipmentColorPatchResult",
    "UniformEquipmentColorTarget",
    "UniformEquipmentColors",
    "PAYLOAD_SCHEMA",
    "SCHEMA",
    "TEAM_COUNT",
    "asset_id",
    "build_patch",
    "decode_replacement_payload",
    "encode_replacement_payload",
    "inspect_colors",
    "parse_asset_id",
    "read_colors",
    "target_metadata",
    "team_label",
    "validate_colors",
]
