#!/usr/bin/env python3
"""Inspect and safely patch custom-team appearance in an APF raw roster save.

The game's accepted user teams are ROST table slots 32 through 39.  A loaded
``Roster.ROS`` carries its own palette and selector graph, so it shadows the
matching records in the disc ``0A``.  This writer resolves that save-local
graph and changes only the same bounded appearance bytes as Mod Studio's disc
writer: ten HOME/AWAY ARGB values and exact eight-byte helmet/crest selectors.

Raw payloads are written to a new file and independently verifiable receipt.
For Xbox 360 STFS packages the verified inner ``Roster.ROS`` can be extracted
or patched into a new raw handoff file.  The signed container is never written:
reinjection, rehashing, and resigning still require an external save manager.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any, Iterable

# The installed Windows runtime uses an embeddable CPython ``._pth`` file,
# which does not automatically add this script's directory to ``sys.path``.
# Restore it before importing sibling tools so direct subprocess launches work
# the same way as a normal Python installation.
_here = str(Path(__file__).resolve().parent)
if _here not in sys.path:
    sys.path.insert(0, _here)

import apf_custom_team_appearance_patch as appearance_writer
import apf_roster
import apf_stfs_roster_extract as stfs_reader


SCHEMA = "apf2k8_save_custom_team_appearance/v1"
MANIFEST_SCHEMA = "apf2k8_save_custom_team_appearance_patch/v1"
VERIFY_SCHEMA = "apf2k8_save_custom_team_appearance_verify/v1"
STFS_EXTRACT_SCHEMA = "apf2k8_stfs_roster_extract/v1"
STFS_EXTRACT_VERIFY_SCHEMA = "apf2k8_stfs_roster_extract_verify/v1"
STFS_HANDOFF_SCHEMA = "apf2k8_stfs_roster_appearance_handoff/v1"
STFS_HANDOFF_VERIFY_SCHEMA = "apf2k8_stfs_roster_appearance_handoff_verify/v1"
RAW_LAYOUT = "raw_roster_payload"
STFS_LAYOUT = "xbox_360_stfs_package"
STFS_MAGICS = stfs_reader.STFS_MAGICS
ROOT_OFFSET = 4
ROOT_PAIR_COUNT = 40
TEAM_TABLE_INDEX = 4
PALETTE_TABLE_INDEX = 16
SELECTOR_TABLE_INDEX = 17
PACKED_TABLE_INDEX = 18
CONFIG_TABLE_INDEX = 19
TEAM_STRIDE = 0x180
PALETTE_STRIDE = 0x30
SELECTOR_STRIDE = 0x08
CONFIG_STRIDE = 0x98
TEAM_CONFIG_POINTER = 0xBC
TEAM_ROSTER_COUNT = 0xC5
TEAM_CATEGORY = 0xD0
TEAM_NAME_POINTER = 0xA8
USER_CATEGORY = 2
CONFIG_HOME_PALETTE_POINTER = 0x70
CONFIG_AWAY_PALETTE_POINTER = 0x74
SELECTORS_PER_BANK = 14
HELMET_SELECTOR_SLOT = 3
LOGO_SELECTOR_SLOT = 5
PACKED_TABLE_PADDING = 2


class SaveAppearanceError(RuntimeError):
    """The save is unsupported, corrupt, stale, or unsafe to write."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SaveAppearanceError(message)


@dataclass(frozen=True)
class SaveAppearanceTarget:
    slot: int
    user_team_id: int
    config_index: int
    home_palette_index: int
    away_palette_index: int
    home_helmet_selector_index: int
    home_logo_selector_index: int
    away_helmet_selector_index: int
    away_logo_selector_index: int
    home_palette_offset: int
    away_palette_offset: int
    home_helmet_offset: int
    home_logo_offset: int
    away_helmet_offset: int
    away_logo_offset: int
    display_name: str
    occupied: bool


@dataclass(frozen=True)
class SaveAppearanceSlot:
    target: SaveAppearanceTarget
    appearance: appearance_writer.CustomTeamAppearance


@dataclass(frozen=True)
class ParsedSave:
    layout: str
    signed_container: bool
    slots: tuple[SaveAppearanceSlot, ...]
    container_kind: str | None = None
    payload_path: str | None = None
    payload_size: int | None = None
    payload_sha256: str | None = None
    container_hash_tree_verified: bool = False
    container_rsa_signature_verified: bool = False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _be32(data: bytes, offset: int, label: str) -> int:
    require(0 <= offset <= len(data) - 4, f"{label} is outside the save")
    return struct.unpack_from(">I", data, offset)[0]


def _signed32(value: int) -> int:
    return value if value < 0x80000000 else value - 0x1_0000_0000


def _relative_target(data: bytes, field: int, label: str) -> int:
    target = field + _signed32(_be32(data, field, label)) - 1
    require(0 <= target < len(data), f"{label} resolves outside the save")
    return target


def _record_index(target: int, start: int, count: int, stride: int, label: str) -> int:
    relative = target - start
    index, remainder = divmod(relative, stride)
    require(
        relative >= 0 and remainder == 0 and 0 <= index < count,
        f"{label} is not an aligned record in its table",
    )
    return index


def _decode_utf16be(data: bytes, target: int, label: str) -> str:
    require(target % 2 == 0, f"{label} is not UTF-16 aligned")
    end = target
    while end <= len(data) - 2 and end - target <= 128:
        if data[end : end + 2] == b"\0\0":
            try:
                return data[target:end].decode("utf-16-be", errors="strict")
            except UnicodeDecodeError as exc:
                raise SaveAppearanceError(f"{label} is not valid UTF-16BE") from exc
        end += 2
    raise SaveAppearanceError(f"{label} has no nearby terminator")


def _root_count(data: bytes, index: int) -> int:
    return _be32(data, ROOT_OFFSET + index * 8, f"root table {index} count")


def _root_target(data: bytes, index: int) -> int:
    field = ROOT_OFFSET + index * 8 + 4
    return _relative_target(data, field, f"root table {index} pointer")


def _table_layout(data: bytes) -> dict[int, tuple[int, int, int]]:
    """Resolve the save tables without trusting serialized guest pointers.

    Raw APF saves retain runtime-address values in root pointer fields 15..18.
    Table 19 still has a normal file-relative pointer.  Tables 16 and 17 are
    therefore independently recovered from table 19 and the exact counted,
    contiguous table 18/17 spans, then all config pointers are checked against
    those recovered bounds.
    """

    require(len(data) >= ROOT_OFFSET + ROOT_PAIR_COUNT * 8, "raw save root is truncated")
    for index, expected in enumerate(apf_roster.EXPECTED_COUNTS):
        require(
            _root_count(data, index) == expected,
            f"root table {index} count changed",
        )

    team_start = _root_target(data, TEAM_TABLE_INDEX)
    config_start = _root_target(data, CONFIG_TABLE_INDEX)
    packed_count = _root_count(data, PACKED_TABLE_INDEX)
    selector_count = _root_count(data, SELECTOR_TABLE_INDEX)
    palette_count = _root_count(data, PALETTE_TABLE_INDEX)
    packed_length = packed_count * 5 + PACKED_TABLE_PADDING
    selector_start = config_start - packed_length - selector_count * SELECTOR_STRIDE
    palette_start = selector_start - palette_count * PALETTE_STRIDE

    tables = {
        TEAM_TABLE_INDEX: (team_start, _root_count(data, TEAM_TABLE_INDEX), TEAM_STRIDE),
        PALETTE_TABLE_INDEX: (palette_start, palette_count, PALETTE_STRIDE),
        SELECTOR_TABLE_INDEX: (selector_start, selector_count, SELECTOR_STRIDE),
        CONFIG_TABLE_INDEX: (config_start, _root_count(data, CONFIG_TABLE_INDEX), CONFIG_STRIDE),
    }
    for index, (start, count, stride) in tables.items():
        require(start >= ROOT_OFFSET + ROOT_PAIR_COUNT * 8, f"table {index} overlaps the root")
        require(start + count * stride <= len(data), f"table {index} exceeds the save")
    require(
        palette_start + palette_count * PALETTE_STRIDE == selector_start,
        "palette and selector tables are not contiguous",
    )
    require(
        selector_start + selector_count * SELECTOR_STRIDE + packed_length == config_start,
        "selector, packed, and config tables are not contiguous",
    )
    spans = sorted(
        (
            (
                team_start,
                team_start + _root_count(data, TEAM_TABLE_INDEX) * TEAM_STRIDE,
                "team",
            ),
            (palette_start, selector_start, "palette"),
            (selector_start, selector_start + selector_count * SELECTOR_STRIDE, "selector"),
            (selector_start + selector_count * SELECTOR_STRIDE, config_start, "packed"),
            (
                config_start,
                config_start + _root_count(data, CONFIG_TABLE_INDEX) * CONFIG_STRIDE,
                "config",
            ),
        )
    )
    for previous, following in zip(spans, spans[1:]):
        require(
            previous[1] <= following[0],
            f"{previous[2]} and {following[2]} save tables overlap",
        )
    return tables


def _appearance_from_target(
    data: bytes, target: SaveAppearanceTarget
) -> appearance_writer.CustomTeamAppearance:
    def bank(
        palette_offset: int, helmet_offset: int, logo_offset: int
    ) -> appearance_writer.AppearanceBank:
        require(palette_offset + 40 <= len(data), "appearance palette exceeds the save")
        return appearance_writer.AppearanceBank(
            struct.unpack_from(">10I", data, palette_offset),
            data[helmet_offset : helmet_offset + 8],
            data[logo_offset : logo_offset + 8],
        )

    return appearance_writer.validate_appearance(
        appearance_writer.CustomTeamAppearance(
            target.slot,
            bank(
                target.home_palette_offset,
                target.home_helmet_offset,
                target.home_logo_offset,
            ),
            bank(
                target.away_palette_offset,
                target.away_helmet_offset,
                target.away_logo_offset,
            ),
        )
    )


def _resolve_targets(data: bytes) -> dict[int, SaveAppearanceTarget]:
    tables = _table_layout(data)
    team_start, team_count, _team_stride = tables[TEAM_TABLE_INDEX]
    palette_start, palette_count, _palette_stride = tables[PALETTE_TABLE_INDEX]
    selector_start, selector_count, _selector_stride = tables[SELECTOR_TABLE_INDEX]
    config_start, config_count, _config_stride = tables[CONFIG_TABLE_INDEX]
    require(team_count == config_count == 40, "save no longer has 40 team/config records")

    palette_owners: dict[int, int] = {}
    selector_owners: dict[int, int] = {}
    configs: list[tuple[int, tuple[int, ...], tuple[int, int]]] = []
    for team_index in range(team_count):
        team = team_start + team_index * TEAM_STRIDE
        config_offset = _relative_target(
            data, team + TEAM_CONFIG_POINTER, f"team {team_index} config pointer"
        )
        config_index = _record_index(
            config_offset, config_start, config_count, CONFIG_STRIDE,
            f"team {team_index} config",
        )
        selectors: list[int] = []
        for selector_slot in range(SELECTORS_PER_BANK * 2):
            offset = _relative_target(
                data,
                config_offset + selector_slot * 4,
                f"team {team_index} selector {selector_slot}",
            )
            index = _record_index(
                offset, selector_start, selector_count, SELECTOR_STRIDE,
                f"team {team_index} selector {selector_slot}",
            )
            selectors.append(index)
            selector_owners[index] = selector_owners.get(index, 0) + 1
        palettes: list[int] = []
        for field, label in (
            (CONFIG_HOME_PALETTE_POINTER, "HOME palette"),
            (CONFIG_AWAY_PALETTE_POINTER, "AWAY palette"),
        ):
            offset = _relative_target(data, config_offset + field, f"team {team_index} {label}")
            index = _record_index(
                offset, palette_start, palette_count, PALETTE_STRIDE,
                f"team {team_index} {label}",
            )
            palettes.append(index)
            palette_owners[index] = palette_owners.get(index, 0) + 1
        configs.append((config_index, tuple(selectors), (palettes[0], palettes[1])))

    targets: dict[int, SaveAppearanceTarget] = {}
    for slot in appearance_writer.USER_SLOTS:
        team = team_start + slot * TEAM_STRIDE
        config_index, selectors, palettes = configs[slot]
        require(config_index == slot, f"user slot {slot} no longer owns config record {slot}")
        require(
            _be32(data, team + TEAM_CATEGORY, f"user slot {slot} category") == USER_CATEGORY,
            f"team slot {slot} is not a user-team record",
        )
        selected_selector_indices = (
            selectors[HELMET_SELECTOR_SLOT],
            selectors[LOGO_SELECTOR_SLOT],
            selectors[SELECTORS_PER_BANK + HELMET_SELECTOR_SLOT],
            selectors[SELECTORS_PER_BANK + LOGO_SELECTOR_SLOT],
        )
        for index in palettes:
            require(palette_owners.get(index) == 1, f"user slot {slot} palette is shared")
        for index in selected_selector_indices:
            require(selector_owners.get(index) == 1, f"user slot {slot} selector is shared")
        name_target = _relative_target(data, team + TEAM_NAME_POINTER, f"user slot {slot} name")
        target = SaveAppearanceTarget(
            slot=slot,
            user_team_id=slot - 8,
            config_index=config_index,
            home_palette_index=palettes[0],
            away_palette_index=palettes[1],
            home_helmet_selector_index=selected_selector_indices[0],
            home_logo_selector_index=selected_selector_indices[1],
            away_helmet_selector_index=selected_selector_indices[2],
            away_logo_selector_index=selected_selector_indices[3],
            home_palette_offset=palette_start + palettes[0] * PALETTE_STRIDE,
            away_palette_offset=palette_start + palettes[1] * PALETTE_STRIDE,
            home_helmet_offset=selector_start + selected_selector_indices[0] * SELECTOR_STRIDE,
            home_logo_offset=selector_start + selected_selector_indices[1] * SELECTOR_STRIDE,
            away_helmet_offset=selector_start + selected_selector_indices[2] * SELECTOR_STRIDE,
            away_logo_offset=selector_start + selected_selector_indices[3] * SELECTOR_STRIDE,
            display_name=_decode_utf16be(data, name_target, f"user slot {slot} name"),
            occupied=data[team + TEAM_ROSTER_COUNT] != 0,
        )
        targets[slot] = target
    return targets


def parse_save(data: bytes) -> ParsedSave:
    if data[:4] in STFS_MAGICS:
        extracted = _extract_stfs_payload(data)
        parsed_payload = parse_save(extracted.payload)
        require(
            not parsed_payload.signed_container,
            "nested STFS Roster.ROS payload is invalid",
        )
        return ParsedSave(
            STFS_LAYOUT,
            True,
            parsed_payload.slots,
            container_kind=extracted.package_kind,
            payload_path=extracted.entry.path,
            payload_size=len(extracted.payload),
            payload_sha256=_sha256(extracted.payload),
            container_hash_tree_verified=extracted.hash_tree_verified,
            container_rsa_signature_verified=extracted.rsa_signature_verified,
        )
    targets = _resolve_targets(data)
    slots = tuple(
        SaveAppearanceSlot(targets[slot], _appearance_from_target(data, targets[slot]))
        for slot in appearance_writer.USER_SLOTS
    )
    return ParsedSave(RAW_LAYOUT, False, slots)


def _extract_stfs_payload(data: bytes) -> stfs_reader.StfsRosterPayload:
    try:
        return stfs_reader.extract_roster_payload(data)
    except stfs_reader.StfsRosterError as exc:
        raise SaveAppearanceError(str(exc)) from exc


def read_source(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SaveAppearanceError(f"cannot open source read-only: {path}: {exc}") from exc
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode), f"source is not a regular file: {path}")
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(block), f"short read from source: {path}")
            chunks.append(block)
            remaining -= len(block)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _payload_document(value: appearance_writer.CustomTeamAppearance) -> dict[str, Any]:
    return json.loads(appearance_writer.encode_replacement_payload(value))


def _payload_value(value: object, label: str) -> appearance_writer.CustomTeamAppearance:
    require(isinstance(value, dict), f"{label} appearance payload is invalid")
    data = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        return appearance_writer.decode_replacement_payload(data, label)
    except appearance_writer.CustomTeamAppearanceError as exc:
        raise SaveAppearanceError(str(exc)) from exc


def _target_spans(target: SaveAppearanceTarget) -> tuple[tuple[int, int], ...]:
    return (
        (target.home_palette_offset, 40),
        (target.away_palette_offset, 40),
        (target.home_helmet_offset, 8),
        (target.home_logo_offset, 8),
        (target.away_helmet_offset, 8),
        (target.away_logo_offset, 8),
    )


def _target_metadata(target: SaveAppearanceTarget) -> dict[str, Any]:
    return {
        "slot": target.slot,
        "user_team_id": target.user_team_id,
        "display_name": target.display_name,
        "occupied": target.occupied,
        "config_index": target.config_index,
        "home_palette_index": target.home_palette_index,
        "away_palette_index": target.away_palette_index,
        "home_helmet_selector_index": target.home_helmet_selector_index,
        "home_logo_selector_index": target.home_logo_selector_index,
        "away_helmet_selector_index": target.away_helmet_selector_index,
        "away_logo_selector_index": target.away_logo_selector_index,
    }


def make_patch(
    source_data: bytes,
    replacements: Iterable[appearance_writer.CustomTeamAppearance],
) -> tuple[bytes, dict[str, Any]]:
    parsed = parse_save(source_data)
    require(
        not parsed.signed_container,
        "Xbox 360 STFS packages are inspect-only; extract the raw roster payload, "
        "patch that new file, then reinject/rehash/resign it with your save manager",
    )
    by_slot = {row.target.slot: row for row in parsed.slots}
    normalized: dict[int, appearance_writer.CustomTeamAppearance] = {}
    for supplied in replacements:
        try:
            value = appearance_writer.validate_appearance(supplied)
        except appearance_writer.CustomTeamAppearanceError as exc:
            raise SaveAppearanceError(str(exc)) from exc
        require(value.slot not in normalized, f"user slot {value.slot} is staged twice")
        require(value.slot in by_slot, f"user slot {value.slot} is not writable")
        normalized[value.slot] = value
    require(bool(normalized), "stage at least one custom-team appearance")

    output = bytearray(source_data)
    allowed: set[int] = set()
    rows: list[dict[str, Any]] = []
    for slot, value in sorted(normalized.items()):
        source = by_slot[slot]
        target = source.target
        for start, length in _target_spans(target):
            span = set(range(start, start + length))
            require(not allowed.intersection(span), "two save appearance targets overlap")
            allowed.update(span)

        def write_bank(
            bank: appearance_writer.AppearanceBank,
            palette: int,
            helmet: int,
            logo: int,
        ) -> None:
            struct.pack_into(">10I", output, palette, *bank.palette)
            output[helmet : helmet + 8] = bank.helmet_selector
            output[logo : logo + 8] = bank.logo_selector

        write_bank(
            value.home,
            target.home_palette_offset,
            target.home_helmet_offset,
            target.home_logo_offset,
        )
        write_bank(
            value.away,
            target.away_palette_offset,
            target.away_helmet_offset,
            target.away_logo_offset,
        )
        rows.append(
            {
                **_target_metadata(target),
                "before": _payload_document(source.appearance),
                "after": _payload_document(value),
                "authorized_byte_count": sum(length for _start, length in _target_spans(target)),
            }
        )

    changed = [
        index
        for index, (before, after) in enumerate(zip(source_data, output, strict=True))
        if before != after
    ]
    require(bool(changed), "every requested appearance already matches the source")
    require(set(changed) <= allowed, "save bytes changed outside selected appearance records")
    output_data = bytes(output)
    reparsed = parse_save(output_data)
    output_by_slot = {row.target.slot: row for row in reparsed.slots}
    for slot, value in normalized.items():
        require(output_by_slot[slot].appearance == value, f"user slot {slot} readback differs")

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "layout": RAW_LAYOUT,
        "source_size": len(source_data),
        "output_size": len(output_data),
        "source_sha256": _sha256(source_data),
        "output_sha256": _sha256(output_data),
        "changed_byte_count": len(changed),
        "changed_byte_positions": changed,
        "authorized_byte_count": len(allowed),
        "edits": rows,
        "claims": {
            "source_opened_read_only": True,
            "output_created_new": True,
            "raw_save_root_offset": ROOT_OFFSET,
            "slots_bounded_to_32_39": True,
            "tables_4_16_17_19_resolved_independently": True,
            "palette_and_selector_records_aligned_and_uniquely_owned": True,
            "only_declared_appearance_bytes_changed": True,
            "stfs_package_write_supported": False,
            "runtime_in_game_proved": False,
        },
    }
    return output_data, manifest


def verify_patch(
    source_data: bytes, output_data: bytes, manifest: dict[str, Any]
) -> dict[str, Any]:
    require(manifest.get("schema") == MANIFEST_SCHEMA, "manifest schema is unsupported")
    source = parse_save(source_data)
    output = parse_save(output_data)
    require(not source.signed_container and not output.signed_container, "STFS package output is invalid")
    require(len(source_data) == len(output_data), "source/output save sizes differ")
    require(manifest.get("source_size") == len(source_data), "source size differs from manifest")
    require(manifest.get("output_size") == len(output_data), "output size differs from manifest")
    require(manifest.get("source_sha256") == _sha256(source_data), "source SHA-256 differs")
    require(manifest.get("output_sha256") == _sha256(output_data), "output SHA-256 differs")
    changed = [
        index
        for index, pair in enumerate(zip(source_data, output_data, strict=True))
        if pair[0] != pair[1]
    ]
    require(manifest.get("changed_byte_positions") == changed, "changed byte positions differ")
    require(manifest.get("changed_byte_count") == len(changed), "changed byte count differs")
    source_slots = {row.target.slot: row for row in source.slots}
    output_slots = {row.target.slot: row for row in output.slots}
    rows = manifest.get("edits")
    require(isinstance(rows, list) and bool(rows), "manifest contains no appearance edits")
    allowed: set[int] = set()
    seen: set[int] = set()
    for index, row in enumerate(rows):
        require(isinstance(row, dict), f"manifest edit {index} is invalid")
        slot = row.get("slot")
        require(slot in source_slots and slot not in seen, f"manifest edit {index} slot is invalid")
        seen.add(slot)
        source_row = source_slots[slot]
        output_row = output_slots[slot]
        require(
            row.get("before") == _payload_document(source_row.appearance),
            f"manifest edit {index} before appearance differs",
        )
        after = _payload_value(row.get("after"), f"manifest edit {index}")
        require(after.slot == slot, f"manifest edit {index} target slot differs")
        require(output_row.appearance == after, f"manifest edit {index} after appearance differs")
        for key, value in _target_metadata(source_row.target).items():
            require(row.get(key) == value, f"manifest edit {index} {key} differs")
        for start, length in _target_spans(source_row.target):
            allowed.update(range(start, start + length))
        require(
            row.get("authorized_byte_count")
            == sum(length for _start, length in _target_spans(source_row.target)),
            f"manifest edit {index} authorized byte count differs",
        )
    require(set(changed) <= allowed, "output changes bytes outside manifest appearance records")
    require(manifest.get("authorized_byte_count") == len(allowed), "authorized union differs")
    return {
        "schema": VERIFY_SCHEMA,
        "verified": True,
        "edit_count": len(rows),
        "changed_byte_count": len(changed),
        "authorized_byte_count": len(allowed),
        "claims": {
            "source_and_output_reopened": True,
            "pointer_graph_revalidated": True,
            "only_manifest_appearance_bytes_changed": True,
            "runtime_in_game_proved": False,
        },
    }


def make_stfs_extract(source_data: bytes) -> tuple[bytes, dict[str, Any]]:
    """Extract one hash-verified Roster.ROS without altering its payload."""

    require(source_data[:4] in STFS_MAGICS, "source is not an STFS package")
    extracted = _extract_stfs_payload(source_data)
    parsed = parse_save(extracted.payload)
    require(not parsed.signed_container and len(parsed.slots) == len(appearance_writer.USER_SLOTS),
            "extracted Roster.ROS did not pass the raw-save appearance parser")
    manifest = {
        "schema": STFS_EXTRACT_SCHEMA,
        "source_layout": STFS_LAYOUT,
        "output_layout": RAW_LAYOUT,
        "source_size": len(source_data),
        "source_sha256": _sha256(source_data),
        "container_kind": extracted.package_kind,
        "payload_path": extracted.entry.path,
        "payload_size": len(extracted.payload),
        "payload_sha256": _sha256(extracted.payload),
        "output_size": len(extracted.payload),
        "output_sha256": _sha256(extracted.payload),
        "data_blocks_verified": extracted.data_blocks_verified,
        "claims": {
            "source_container_opened_read_only": True,
            "metadata_hash_verified": extracted.metadata_hash_verified,
            "stfs_hash_tree_verified": extracted.hash_tree_verified,
            "stfs_rsa_signature_verified": extracted.rsa_signature_verified,
            "output_created_new": True,
            "output_is_raw_roster_payload": True,
            "output_is_signed_stfs_container": False,
            "container_reinjected": False,
            "container_rehashed": False,
            "container_resigned": False,
            "external_reinjection_required": True,
        },
    }
    return extracted.payload, manifest


def verify_stfs_extract(
    source_data: bytes, output_data: bytes, manifest: dict[str, Any]
) -> dict[str, Any]:
    require(manifest.get("schema") == STFS_EXTRACT_SCHEMA,
            "STFS extraction manifest schema is unsupported")
    extracted = _extract_stfs_payload(source_data)
    require(manifest.get("source_size") == len(source_data),
            "STFS source size differs from manifest")
    require(manifest.get("source_sha256") == _sha256(source_data),
            "STFS source SHA-256 differs")
    require(manifest.get("container_kind") == extracted.package_kind,
            "STFS container kind differs")
    require(manifest.get("payload_path") == extracted.entry.path,
            "STFS payload path differs")
    require(manifest.get("payload_size") == len(extracted.payload),
            "STFS payload size differs")
    require(manifest.get("payload_sha256") == _sha256(extracted.payload),
            "STFS payload SHA-256 differs")
    require(output_data == extracted.payload,
            "extracted output does not exactly match the verified STFS payload")
    require(manifest.get("output_size") == len(output_data),
            "extracted output size differs")
    require(manifest.get("output_sha256") == _sha256(output_data),
            "extracted output SHA-256 differs")
    parsed = parse_save(output_data)
    require(not parsed.signed_container and len(parsed.slots) == len(appearance_writer.USER_SLOTS),
            "extracted output is not a complete raw Roster.ROS payload")
    return {
        "schema": STFS_EXTRACT_VERIFY_SCHEMA,
        "verified": True,
        "payload_path": extracted.entry.path,
        "output_sha256": _sha256(output_data),
        "claims": {
            "source_container_and_output_reopened": True,
            "metadata_hash_reverified": True,
            "stfs_hash_tree_reverified": True,
            "raw_roster_graph_revalidated": True,
            "output_is_signed_stfs_container": False,
            "external_reinjection_required": True,
        },
    }


def make_stfs_handoff(
    source_data: bytes,
    replacements: Iterable[appearance_writer.CustomTeamAppearance],
) -> tuple[bytes, dict[str, Any]]:
    """Patch the verified inner payload and return a raw external handoff."""

    require(source_data[:4] in STFS_MAGICS, "source is not an STFS package")
    extracted = _extract_stfs_payload(source_data)
    output_data, appearance_manifest = make_patch(extracted.payload, replacements)
    manifest = {
        "schema": STFS_HANDOFF_SCHEMA,
        "source_layout": STFS_LAYOUT,
        "output_layout": RAW_LAYOUT,
        "source_size": len(source_data),
        "source_sha256": _sha256(source_data),
        "container_kind": extracted.package_kind,
        "payload_path": extracted.entry.path,
        "payload_size": len(extracted.payload),
        "payload_sha256": _sha256(extracted.payload),
        "output_size": len(output_data),
        "output_sha256": _sha256(output_data),
        "data_blocks_verified": extracted.data_blocks_verified,
        "appearance_patch": appearance_manifest,
        "claims": {
            "source_container_opened_read_only": True,
            "metadata_hash_verified": extracted.metadata_hash_verified,
            "stfs_hash_tree_verified": extracted.hash_tree_verified,
            "stfs_rsa_signature_verified": extracted.rsa_signature_verified,
            "output_created_new": True,
            "output_is_patched_raw_roster_payload": True,
            "output_is_signed_stfs_container": False,
            "container_reinjected": False,
            "container_rehashed": False,
            "container_resigned": False,
            "live_pirs_retail_resigning_supported": False,
            "con_resigning_supported": False,
            "external_reinjection_required": True,
            "runtime_in_game_proved": False,
        },
    }
    return output_data, manifest


def verify_stfs_handoff(
    source_data: bytes, output_data: bytes, manifest: dict[str, Any]
) -> dict[str, Any]:
    require(manifest.get("schema") == STFS_HANDOFF_SCHEMA,
            "STFS handoff manifest schema is unsupported")
    extracted = _extract_stfs_payload(source_data)
    require(manifest.get("source_size") == len(source_data),
            "STFS source size differs from handoff manifest")
    require(manifest.get("source_sha256") == _sha256(source_data),
            "STFS source SHA-256 differs from handoff manifest")
    require(manifest.get("container_kind") == extracted.package_kind,
            "STFS container kind differs from handoff manifest")
    require(manifest.get("payload_path") == extracted.entry.path,
            "STFS payload path differs from handoff manifest")
    require(manifest.get("payload_size") == len(extracted.payload),
            "STFS payload size differs from handoff manifest")
    require(manifest.get("payload_sha256") == _sha256(extracted.payload),
            "STFS payload SHA-256 differs from handoff manifest")
    require(manifest.get("output_size") == len(output_data),
            "handoff output size differs")
    require(manifest.get("output_sha256") == _sha256(output_data),
            "handoff output SHA-256 differs")
    appearance_manifest = manifest.get("appearance_patch")
    require(isinstance(appearance_manifest, dict),
            "handoff appearance manifest is missing")
    verification = verify_patch(extracted.payload, output_data, appearance_manifest)
    return {
        "schema": STFS_HANDOFF_VERIFY_SCHEMA,
        "verified": True,
        "edit_count": verification["edit_count"],
        "changed_byte_count": verification["changed_byte_count"],
        "authorized_byte_count": verification["authorized_byte_count"],
        "payload_path": extracted.entry.path,
        "output_sha256": _sha256(output_data),
        "claims": {
            "source_container_and_output_reopened": True,
            "metadata_hash_reverified": True,
            "stfs_hash_tree_reverified": True,
            "raw_roster_patch_reverified": True,
            "output_is_signed_stfs_container": False,
            "external_reinjection_required": True,
            "runtime_in_game_proved": False,
        },
    }


def _reserve(path: Path) -> int:
    require(path.parent.is_dir(), f"output directory does not exist: {path.parent}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags, 0o600)
    except OSError as exc:
        raise SaveAppearanceError(f"refusing to overwrite output: {path}: {exc}") from exc


def _write_all(descriptor: int, data: bytes) -> None:
    position = 0
    while position < len(data):
        written = os.write(descriptor, data[position : position + 1024 * 1024])
        require(written > 0, "short write while creating output")
        position += written


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def default_manifest_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.appearance.json")


def write_patch(
    source: Path,
    output: Path,
    replacements: Iterable[appearance_writer.CustomTeamAppearance],
    manifest_path: Path,
    *,
    expected_source_sha256: str | None = None,
) -> dict[str, Any]:
    require(output != source, "output must not be the source path")
    require(manifest_path not in (source, output), "manifest path must be separate")
    output_fd = _reserve(output)
    try:
        try:
            manifest_fd = _reserve(manifest_path)
        except Exception:
            os.close(output_fd)
            output_fd = -1
            output.unlink(missing_ok=True)
            raise
        try:
            source_data = read_source(source)
            if expected_source_sha256 is not None:
                require(
                    _sha256(source_data) == expected_source_sha256,
                    "source save changed after inspection; reload it before writing",
                )
            if source_data[:4] in STFS_MAGICS:
                output_data, manifest = make_stfs_handoff(source_data, replacements)
                verifier = verify_stfs_handoff
            else:
                output_data, manifest = make_patch(source_data, replacements)
                verifier = verify_patch
            _write_all(output_fd, output_data)
            os.fsync(output_fd)
            verification = verifier(read_source(source), read_source(output), manifest)
            manifest["verification"] = verification
            _write_all(manifest_fd, _json_bytes(manifest))
            os.fsync(manifest_fd)
            return manifest
        except Exception:
            os.close(manifest_fd)
            manifest_fd = -1
            os.close(output_fd)
            output_fd = -1
            manifest_path.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            raise
        finally:
            if manifest_fd >= 0:
                os.close(manifest_fd)
    finally:
        if output_fd >= 0:
            os.close(output_fd)


def write_stfs_extract(
    source: Path,
    output: Path,
    manifest_path: Path,
    *,
    expected_source_sha256: str | None = None,
) -> dict[str, Any]:
    require(output != source, "output must not be the source path")
    require(manifest_path not in (source, output), "manifest path must be separate")
    output_fd = _reserve(output)
    try:
        try:
            manifest_fd = _reserve(manifest_path)
        except Exception:
            os.close(output_fd)
            output_fd = -1
            output.unlink(missing_ok=True)
            raise
        try:
            source_data = read_source(source)
            if expected_source_sha256 is not None:
                require(
                    _sha256(source_data) == expected_source_sha256,
                    "source save changed after inspection; reload it before extracting",
                )
            output_data, manifest = make_stfs_extract(source_data)
            _write_all(output_fd, output_data)
            os.fsync(output_fd)
            verification = verify_stfs_extract(
                read_source(source), read_source(output), manifest
            )
            manifest["verification"] = verification
            _write_all(manifest_fd, _json_bytes(manifest))
            os.fsync(manifest_fd)
            return manifest
        except Exception:
            os.close(manifest_fd)
            manifest_fd = -1
            os.close(output_fd)
            output_fd = -1
            manifest_path.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            raise
        finally:
            if manifest_fd >= 0:
                os.close(manifest_fd)
    finally:
        if output_fd >= 0:
            os.close(output_fd)


def inspection(data: bytes) -> dict[str, Any]:
    parsed = parse_save(data)
    return {
        "schema": SCHEMA,
        "layout": parsed.layout,
        "signed_container": parsed.signed_container,
        "container_kind": parsed.container_kind,
        "payload_path": parsed.payload_path,
        "payload_size": parsed.payload_size,
        "payload_sha256": parsed.payload_sha256,
        "file_size": len(data),
        "sha256": _sha256(data),
        "slots": [
            {
                **_target_metadata(row.target),
                "appearance": _payload_document(row.appearance),
            }
            for row in parsed.slots
        ],
        "claims": {
            "source_opened_read_only": True,
            "signed_container_writable": False,
            "raw_save_appearance_writable": not parsed.signed_container,
            "signed_container_payload_extractable": parsed.signed_container,
            "signed_container_patched_raw_handoff_writable": parsed.signed_container,
            "container_hash_tree_verified": parsed.container_hash_tree_verified,
            "container_rsa_signature_verified": parsed.container_rsa_signature_verified,
            "container_reinjection_supported": False,
            "container_resigning_supported": False,
            "runtime_in_game_proved": False,
        },
    }


def _load_recipe(path: Path) -> list[appearance_writer.CustomTeamAppearance]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveAppearanceError(f"appearance recipe is not readable JSON: {path}") from exc
    rows = document.get("edits") if isinstance(document, dict) else document
    require(isinstance(rows, list), "appearance recipe must contain an edits list")
    return [_payload_value(row, f"recipe edit {index}") for index, row in enumerate(rows)]


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveAppearanceError(f"manifest is not readable JSON: {path}") from exc
    require(isinstance(value, dict), "manifest must be a JSON object")
    return value


def _emit_json(value: dict[str, Any], path: Path | None) -> None:
    payload = _json_bytes(value)
    if path is None:
        sys.stdout.buffer.write(payload)
        return
    descriptor = _reserve(path)
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("source", type=Path)
    inspect_parser.add_argument("--json", type=Path, dest="json_path")
    extract_parser = commands.add_parser("extract")
    extract_parser.add_argument("source", type=Path)
    extract_parser.add_argument("output", type=Path)
    extract_parser.add_argument("--manifest", type=Path, required=True)
    patch_parser = commands.add_parser("patch")
    patch_parser.add_argument("source", type=Path)
    patch_parser.add_argument("output", type=Path)
    patch_parser.add_argument("--recipe", type=Path, required=True)
    patch_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("source", type=Path)
    verify_parser.add_argument("output", type=Path)
    verify_parser.add_argument("manifest", type=Path)
    verify_parser.add_argument("--json", type=Path, dest="json_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            _emit_json(inspection(read_source(args.source)), args.json_path)
        elif args.command == "extract":
            manifest = write_stfs_extract(
                args.source,
                args.output,
                args.manifest,
            )
            print(
                "APF_STFS_ROSTER_EXTRACT_PASS "
                f"path={manifest['payload_path']} bytes={manifest['output_size']}"
            )
        elif args.command == "patch":
            manifest = write_patch(
                args.source,
                args.output,
                _load_recipe(args.recipe),
                args.manifest,
            )
            if manifest["schema"] == STFS_HANDOFF_SCHEMA:
                patch = manifest["appearance_patch"]
                print(
                    "APF_STFS_ROSTER_HANDOFF_PASS "
                    f"edits={len(patch['edits'])} bytes={patch['changed_byte_count']}"
                )
            else:
                print(
                    "APF_SAVE_APPEARANCE_PATCH_PASS "
                    f"edits={len(manifest['edits'])} bytes={manifest['changed_byte_count']}"
                )
        else:
            source_data = read_source(args.source)
            output_data = read_source(args.output)
            manifest = _load_manifest(args.manifest)
            if manifest.get("schema") == STFS_EXTRACT_SCHEMA:
                verification = verify_stfs_extract(source_data, output_data, manifest)
            elif manifest.get("schema") == STFS_HANDOFF_SCHEMA:
                verification = verify_stfs_handoff(source_data, output_data, manifest)
            else:
                verification = verify_patch(source_data, output_data, manifest)
            _emit_json(
                verification,
                args.json_path,
            )
        return 0
    except (OSError, SaveAppearanceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
