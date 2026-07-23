#!/usr/bin/env python3
"""Parse the APF 2K8 on-disc ROST resource without guessing unknown fields.

The supplied US disc stores one ``ROST/roster`` file in outer table entry
1126.  This tool reads that file through the existing bounds-checked APF IFF
and H7A implementation, validates every root array, resolves the game's
one-based field-local relative pointers, and exports only relationships backed
by both the bytes and traced XEX consumers.

Known exports are player names/positions/biographical strings, the exact
executable-backed base-rating bytes, stadium names, team names,
team-to-stadium links, and the counted team roster pointer arrays.  All other
root tables and record bytes remain inventoried but deliberately unnamed.
They are not silently reinterpreted as editor folklore.

// PORTME: identify the schemas and XEX consumers of root tables 1-2 and 5-39.
// PORTME: name the remaining player/team appearance, equipment, ability, tier,
//         and behavior bitfields only after exact consumer traces exist.
// PORTME: implement a reversible writer only after pointer/string ownership,
//         capacity rules, archive recompression, and integrity checks are known.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import Iterable

import apf_inner
import apf_outer

# ``apf_roster.py`` remains directly runnable from ``tools/`` while consuming
# the same retail-free, fail-closed dictionary as the desktop product.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from mod_editor.apf_studio.player_ratings import (  # noqa: E402
    PlayerRatingsError,
    load_player_rating_schema,
)
from mod_editor.apf_studio.player_positions import (  # noqa: E402
    PlayerPositionsError,
    load_player_position_schema,
)


OUTER_TABLE_INDEX = 1126
OUTER_NAME_ID = 0xBCEFFD46
INNER_NAME = "roster"
INNER_TYPE = "ROST"
EXPECTED_LENGTH = 2_294_304
ROOT_PAIR_COUNT = 40
ROOT_SIZE = 0x14C

# The first 23 nonempty arrays occupy the resource contiguously.  Every stride
# except table 18 is independently present in an XEX accessor or is the exact
# quotient between adjacent validated root targets.  Table 18 is 266 packed
# five-byte records followed by two zero alignment bytes.
EXPECTED_COUNTS = (
    2254, 0, 1, 31, 40, 295, 199, 199, 199, 42, 5957, 69,
    650, 1050, 3200, 266, 266, 3724, 266, 40, 93, 204, 212,
) + (0,) * 17
EXPECTED_STRIDES: tuple[int | None, ...] = (
    0x14C, None, 0xFA4, 0x24, 0x180, 0x08, 0x18, 0x18,
    0x18, 0xB4, 0xBC, 0x0C, 0x08, 0x08, 0x08, 0x02,
    0x30, 0x08, 0x05, 0x98, 0x98, 0x20, 0x78,
) + (None,) * 17
TABLE_LABELS = {
    0: "players",
    2: "unknown_02_player_reference_slots",
    3: "stadiums",
    4: "teams",
}

PLAYER_STRING_FIELDS = {
    0x000: "last_name",
    0x004: "first_name",
    0x118: "nickname",
    0x11C: "career_history",
    0x120: "league_mvp_years",
    0x124: "all_pro_mvp_years",
    0x128: "championship_mvp_years",
    0x12C: "unknown_accolade_text_1",
    0x130: "unknown_accolade_text_2",
    0x134: "unknown_accolade_text_3",
    0x138: "unknown_accolade_text_4",
    0x13C: "championship_years",
    0x140: "championship_game_appearance_years",
    0x144: "unknown_biography_text_1",
    0x148: "unknown_biography_text_2",
}

# Named team string-pointer fields used by both the read-only inventory and
# the bounded identity writer.  Keeping this mapping here prevents the product
# layer from carrying a second, potentially divergent record layout.
TEAM_STRING_FIELDS = {
    0x0A8: "display_name",
    0x0AC: "abbreviation",
    0x0B0: "numeric_string_code",
    0x0E8: "secondary_abbreviation",
}

PLAYER_STRIDE = 0x14C
STADIUM_STRIDE = 0x24
TEAM_STRIDE = 0x180
TEAM_ROSTER_CAPACITY = 42
TEAM_AUX_PLAYER_OFFSETS = tuple(range(0x108, 0x120, 4))
PLAYER_RATING_SCHEMA = load_player_rating_schema()
PLAYER_POSITION_SCHEMA = load_player_position_schema()
POSITION_LABELS = tuple(
    (position.abbreviation, position.name)
    for position in PLAYER_POSITION_SCHEMA.positions
)


class RosterError(ValueError):
    """Raised when the supplied ROST resource violates a proved invariant."""


@dataclass(frozen=True)
class RootTable:
    index: int
    count: int
    pointer_field_offset: int
    stored_pointer: int
    offset: int
    stride: int | None
    storage_length: int
    alignment_padding: int


def _hex(value: int, width: int = 8) -> str:
    return f"0x{value:0{width}x}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _u16be(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise RosterError(f"{what} at 0x{offset:x} is outside the resource")
    return struct.unpack_from(">H", data, offset)[0]


def _u32be(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise RosterError(f"{what} at 0x{offset:x} is outside the resource")
    return struct.unpack_from(">I", data, offset)[0]


def _signed32(value: int) -> int:
    return value if value < 0x80000000 else value - 0x1_0000_0000


def resolve_relative(
    data: bytes, field_offset: int, what: str, *, allow_null: bool = False
) -> int | None:
    """Resolve ``field + signed(stored) - 1`` with strict resource bounds."""
    stored = _u32be(data, field_offset, what)
    if stored == 0 and allow_null:
        return None
    target = field_offset + _signed32(stored) - 1
    if not 0 <= target < len(data):
        raise RosterError(
            f"{what} at 0x{field_offset:x} resolves to 0x{target:x}, "
            f"outside 0x0..0x{len(data) - 1:x}"
        )
    return target


def decode_utf16be_z(data: bytes, offset: int, what: str) -> str:
    if offset < 0 or offset >= len(data) or offset & 1:
        raise RosterError(f"{what} target 0x{offset:x} is not an aligned in-file string")
    end = offset
    while end + 1 < len(data) and data[end : end + 2] != b"\0\0":
        end += 2
    if end + 1 >= len(data):
        raise RosterError(f"unterminated UTF-16BE {what} at 0x{offset:x}")
    try:
        return data[offset:end].decode("utf-16be")
    except UnicodeDecodeError as exc:
        raise RosterError(f"invalid UTF-16BE {what} at 0x{offset:x}") from exc


def parse_string_pool(data: bytes, start: int) -> tuple[dict[int, str], int]:
    strings: dict[int, str] = {}
    cursor = start
    empty_count = 0
    while cursor < len(data):
        text = decode_utf16be_z(data, cursor, "string-pool entry")
        strings[cursor] = text
        empty_count += not bool(text)
        cursor += len(text.encode("utf-16be")) + 2
    if cursor != len(data):
        raise RosterError("string pool does not end exactly at the resource boundary")
    return strings, empty_count


def parse_root(data: bytes) -> tuple[list[RootTable], dict[str, int]]:
    if len(data) != EXPECTED_LENGTH:
        raise RosterError(
            f"ROST decoded length is {len(data)}, expected {EXPECTED_LENGTH}"
        )
    tables: list[RootTable] = []
    targets: list[int] = []
    for index in range(ROOT_PAIR_COUNT):
        pair = index * 8
        count = _u32be(data, pair, f"root table {index} count")
        if count != EXPECTED_COUNTS[index]:
            raise RosterError(
                f"root table {index} count {count}, expected {EXPECTED_COUNTS[index]}"
            )
        pointer_field = pair + 4
        target = resolve_relative(data, pointer_field, f"root table {index} pointer")
        assert target is not None
        targets.append(target)

    pointer_140 = resolve_relative(data, 0x140, "root pointer 0x140")
    pointer_144 = resolve_relative(data, 0x144, "root pointer 0x144")
    string_pool = resolve_relative(data, 0x148, "root string-pool pointer")
    assert pointer_140 is not None and pointer_144 is not None and string_pool is not None

    for index in range(ROOT_PAIR_COUNT):
        count = EXPECTED_COUNTS[index]
        stride = EXPECTED_STRIDES[index]
        start = targets[index]
        if index + 1 < ROOT_PAIR_COUNT:
            end = targets[index + 1]
        else:
            end = pointer_140
        if end < start:
            raise RosterError(f"root table {index} has descending bounds")
        span = end - start
        padding = 2 if index == 18 else 0
        expected = 0 if stride is None else count * stride
        if span != expected + padding:
            raise RosterError(
                f"root table {index} span 0x{span:x}, expected "
                f"0x{expected + padding:x}"
            )
        if padding and data[end - padding : end] != b"\0" * padding:
            raise RosterError(f"root table {index} alignment padding is not zero")
        tables.append(
            RootTable(
                index=index,
                count=count,
                pointer_field_offset=index * 8 + 4,
                stored_pointer=_u32be(data, index * 8 + 4, "root pointer"),
                offset=start,
                stride=stride,
                storage_length=expected,
                alignment_padding=padding,
            )
        )

    if targets[0] != ROOT_SIZE:
        raise RosterError(
            f"player table begins at 0x{targets[0]:x}, expected root size 0x{ROOT_SIZE:x}"
        )
    if pointer_140 != pointer_144 or pointer_140 != targets[23]:
        raise RosterError("root pointers 0x140/0x144 do not share the end-of-array target")
    if string_pool < pointer_144:
        raise RosterError("string pool begins before the reserved UTF-16 workspace")
    workspace = data[pointer_144:string_pool]
    if any(workspace):
        raise RosterError("reserved UTF-16 workspace contains nonzero bytes")
    return tables, {
        "array_end": pointer_140,
        "workspace_begin": pointer_144,
        "workspace_length": len(workspace),
        "workspace_utf16_code_unit_capacity": len(workspace) // 2,
        "string_pool_offset": string_pool,
        "string_pool_length": len(data) - string_pool,
    }


def _record_sha(data: bytes, offset: int, stride: int) -> str:
    return _sha256(data[offset : offset + stride])


def _pointer_index(
    data: bytes,
    field: int,
    base: int,
    stride: int,
    count: int,
    what: str,
    *,
    allow_null: bool = False,
) -> int | None:
    target = resolve_relative(data, field, what, allow_null=allow_null)
    if target is None:
        return None
    delta = target - base
    if delta < 0 or delta % stride or delta // stride >= count:
        raise RosterError(
            f"{what} at 0x{field:x} targets 0x{target:x}, not a 0x{stride:x}-byte record"
        )
    return delta // stride


def _string_field(
    data: bytes, field: int, pool: dict[int, str], what: str
) -> tuple[int, str]:
    target = resolve_relative(data, field, what)
    assert target is not None
    if target not in pool:
        raise RosterError(f"{what} targets 0x{target:x}, not a string-pool boundary")
    return target, pool[target]


def parse_stadiums(
    data: bytes, table: RootTable, pool: dict[int, str]
) -> list[dict[str, object]]:
    stadiums: list[dict[str, object]] = []
    capacity_pattern = re.compile(r"Capacity:\s*(\d+)\s*$")
    for index in range(table.count):
        offset = table.offset + index * STADIUM_STRIDE
        _, display_name = _string_field(data, offset, pool, f"stadium {index} name")
        _, asset_key = _string_field(data, offset + 4, pool, f"stadium {index} asset key")
        _, description = _string_field(
            data, offset + 8, pool, f"stadium {index} description"
        )
        capacity = _u32be(data, offset + 0x0C, f"stadium {index} capacity")
        match = capacity_pattern.search(description)
        if match is None or int(match.group(1)) != capacity:
            raise RosterError(
                f"stadium {index} capacity {capacity} disagrees with its description"
            )
        stadiums.append(
            {
                "stadium_index": index,
                "record_offset": _hex(offset, 6),
                "display_name": display_name,
                "asset_key": asset_key,
                "description": description,
                "capacity": capacity,
                "raw_record_sha256": _record_sha(data, offset, STADIUM_STRIDE),
            }
        )
    return stadiums


def parse_teams(
    data: bytes,
    table: RootTable,
    player_table: RootTable,
    stadium_table: RootTable,
    pool: dict[int, str],
    stadiums: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, int]]]:
    teams: list[dict[str, object]] = []
    memberships: list[dict[str, int]] = []
    seen_roster_players: set[int] = set()
    for index in range(table.count):
        offset = table.offset + index * TEAM_STRIDE
        team_strings = {
            label: _string_field(
                data,
                offset + relative,
                pool,
                f"team {index} {label.replace('_', ' ')}",
            )[1]
            for relative, label in TEAM_STRING_FIELDS.items()
        }
        display_name = team_strings["display_name"]
        abbreviation = team_strings["abbreviation"]
        numeric_code = team_strings["numeric_string_code"]
        secondary_abbreviation = team_strings["secondary_abbreviation"]
        roster_count = data[offset + 0xC5]
        if roster_count > TEAM_ROSTER_CAPACITY:
            raise RosterError(
                f"team {index} roster count {roster_count} exceeds {TEAM_ROSTER_CAPACITY}"
            )
        roster: list[int] = []
        for slot in range(roster_count):
            player = _pointer_index(
                data,
                offset + slot * 4,
                player_table.offset,
                PLAYER_STRIDE,
                player_table.count,
                f"team {index} roster slot {slot}",
            )
            assert player is not None
            if player in roster:
                raise RosterError(f"team {index} repeats player {player} in its counted roster")
            if player in seen_roster_players:
                raise RosterError(f"player {player} occurs in more than one counted team roster")
            seen_roster_players.add(player)
            roster.append(player)
            memberships.append(
                {"team_index": index, "roster_slot": slot, "player_index": player}
            )
        # Unused counted-roster slots are zero in all eight empty user teams.
        if roster_count == 0:
            for slot in range(TEAM_ROSTER_CAPACITY):
                if _u32be(data, offset + slot * 4, "empty team roster slot") != 0:
                    raise RosterError(f"empty team {index} has a nonzero roster slot {slot}")

        stadium_index = _pointer_index(
            data,
            offset + 0xB8,
            stadium_table.offset,
            STADIUM_STRIDE,
            stadium_table.count,
            f"team {index} stadium pointer",
        )
        assert stadium_index is not None
        aux_players = [
            _pointer_index(
                data,
                offset + relative,
                player_table.offset,
                PLAYER_STRIDE,
                player_table.count,
                f"team {index} auxiliary player reference 0x{relative:x}",
                allow_null=True,
            )
            for relative in TEAM_AUX_PLAYER_OFFSETS
        ]
        if abbreviation.startswith("ONLN"):
            slot_kind = "online_slot"
        elif abbreviation.startswith("USER"):
            slot_kind = "user_slot"
        else:
            slot_kind = "built_in_team"
        teams.append(
            {
                "team_index": index,
                "record_offset": _hex(offset, 6),
                "display_name": display_name,
                "abbreviation": abbreviation,
                "numeric_string_code": numeric_code,
                "secondary_abbreviation": secondary_abbreviation,
                "derived_slot_kind": slot_kind,
                "roster_count": roster_count,
                "roster_player_indices": roster,
                "stadium_index": stadium_index,
                "stadium_name": stadiums[stadium_index]["display_name"],
                "category_code_at_0xd0": _u32be(
                    data, offset + 0xD0, f"team {index} category code"
                ),
                "auxiliary_player_references_0x108_0x11c": aux_players,
                "raw_record_sha256": _record_sha(data, offset, TEAM_STRIDE),
            }
        )
    return teams, memberships


def parse_players(
    data: bytes,
    table: RootTable,
    pool: dict[int, str],
    teams: list[dict[str, object]],
    memberships: list[dict[str, int]],
) -> list[dict[str, object]]:
    by_player: dict[int, list[dict[str, int]]] = {}
    for membership in memberships:
        by_player.setdefault(membership["player_index"], []).append(membership)

    players: list[dict[str, object]] = []
    for index in range(table.count):
        offset = table.offset + index * PLAYER_STRIDE
        strings: dict[str, str] = {}
        string_targets: dict[str, str] = {}
        for relative, label in PLAYER_STRING_FIELDS.items():
            target, text = _string_field(
                data, offset + relative, pool, f"player {index} {label}"
            )
            strings[label] = text
            string_targets[label] = _hex(target, 6)
        try:
            position = PLAYER_POSITION_SCHEMA.decode_record(
                data[offset : offset + PLAYER_STRIDE]
            )
        except PlayerPositionsError as exc:
            raise RosterError(f"player {index} position is invalid: {exc}") from exc
        position_code = position.code
        abbreviation, position_name = position.abbreviation, position.name
        try:
            base_ratings = PLAYER_RATING_SCHEMA.decode_record(
                data[offset : offset + PLAYER_STRIDE]
            )
        except PlayerRatingsError as exc:
            raise RosterError(f"player {index} base ratings are invalid: {exc}") from exc
        member_rows = by_player.get(index, [])
        membership_documents = [
            {
                "team_index": row["team_index"],
                "team_name": teams[row["team_index"]]["display_name"],
                "roster_slot": row["roster_slot"],
            }
            for row in member_rows
        ]
        players.append(
            {
                "player_index": index,
                "record_offset": _hex(offset, 6),
                "first_name": strings.pop("first_name"),
                "last_name": strings.pop("last_name"),
                "position_code": position_code,
                "position_abbreviation": abbreviation,
                "position_name": position_name,
                "base_ratings": base_ratings,
                "hall_of_fame_induction_year_at_0x112": _u16be(
                    data, offset + 0x112, f"player {index} Hall of Fame year"
                ),
                "championship_count_at_0x114": data[offset + 0x114],
                "championship_game_appearance_count_at_0x115": data[offset + 0x115],
                "all_pro_game_count_at_0x116": data[offset + 0x116],
                "strings": strings,
                "raw_string_targets": string_targets,
                "team_memberships": membership_documents,
                "raw_record_sha256": _record_sha(data, offset, PLAYER_STRIDE),
            }
        )
    return players


def validate_table_02_player_references(
    data: bytes, table: RootTable, player_table: RootTable
) -> dict[str, object]:
    if table.count != 1 or table.stride != 0xFA4:
        raise RosterError("root table 2 no longer has its proved single-record layout")
    slot_count = table.stride // 4
    nonnull: list[dict[str, int]] = []
    for slot in range(slot_count):
        field = table.offset + slot * 4
        player = _pointer_index(
            data,
            field,
            player_table.offset,
            PLAYER_STRIDE,
            player_table.count,
            f"root table 2 slot {slot}",
            allow_null=True,
        )
        if player is not None:
            nonnull.append({"slot": slot, "player_index": player})
    return {
        "slot_count": slot_count,
        "null_slot_count": slot_count - len(nonnull),
        "nonnull_player_reference_count": len(nonnull),
        "nonnull_player_references": nonnull,
        "semantic_status": "unknown; pointer type only is proved",
    }


def load_roster(index_path: Path) -> tuple[bytes, dict[str, object]]:
    archive = apf_outer.parse_archive(index_path)
    matches = [
        entry for entry in archive.entries if entry.table_index == OUTER_TABLE_INDEX
    ]
    if len(matches) != 1:
        raise RosterError(f"expected one outer table entry {OUTER_TABLE_INDEX}")
    entry = matches[0]
    if entry.name_id != OUTER_NAME_ID:
        raise RosterError(
            f"outer entry name ID {_hex(entry.name_id)} != expected {_hex(OUTER_NAME_ID)}"
        )
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        if record.warnings:
            raise RosterError(f"ROST IFF has structural warnings: {record.warnings}")
        if len(record.files) != 1:
            raise RosterError(f"ROST IFF contains {len(record.files)} inner files")
        inner = record.files[0]
        if inner.name != INNER_NAME or inner.type_name != INNER_TYPE:
            raise RosterError(
                f"inner file is {inner.name!r}/{inner.type_name!r}, expected roster/ROST"
            )
        if len(inner.parts) != 1 or inner.parts[0].block_index != 0:
            raise RosterError("ROST inner file is not one bounded DRAM part")
        block = apf_inner.decode_block(
            reader, record, inner.parts[0].block_index, 16 * 1024 * 1024
        )
        part = inner.parts[0]
        data = block[part.offset : part.offset + part.length]
        outer_raw = reader.read(entry, 0, entry.size)
    source = {
        "index_path": str(index_path),
        "outer_table_index": entry.table_index,
        "outer_name_id": _hex(entry.name_id),
        "outer_stored_size": entry.size,
        "outer_stored_sha256": _sha256(outer_raw),
        "inner_index": inner.index,
        "inner_name": inner.name,
        "inner_type": inner.type_name,
        "decoded_length": len(data),
        "decoded_sha256": _sha256(data),
    }
    return data, source


def build_report(data: bytes, source: dict[str, object]) -> dict[str, object]:
    tables, root = parse_root(data)
    string_pool, empty_string_count = parse_string_pool(data, root["string_pool_offset"])
    stadiums = parse_stadiums(data, tables[3], string_pool)
    teams, memberships = parse_teams(
        data, tables[4], tables[0], tables[3], string_pool, stadiums
    )
    players = parse_players(data, tables[0], string_pool, teams, memberships)
    table_02 = validate_table_02_player_references(data, tables[2], tables[0])

    active_teams = sum(int(team["roster_count"]) > 0 for team in teams)
    populated_player_names = sum(
        bool(player["first_name"] or player["last_name"]) for player in players
    )
    return {
        "schema": "apf_roster_inventory/v1",
        "source": source,
        "pointer_rule": "target = pointer_field_offset + signed_be32(stored_value) - 1",
        "root": {
            "size": ROOT_SIZE,
            **root,
            "tables": [
                {
                    "index": table.index,
                    "label": TABLE_LABELS.get(table.index, f"unknown_{table.index:02d}"),
                    "count": table.count,
                    "pointer_field_offset": _hex(table.pointer_field_offset, 3),
                    "stored_pointer": _hex(table.stored_pointer),
                    "offset": _hex(table.offset, 6),
                    "stride": None if table.stride is None else _hex(table.stride),
                    "storage_length": table.storage_length,
                    "alignment_padding": table.alignment_padding,
                }
                for table in tables
            ],
        },
        "summary": {
            "player_count": len(players),
            "players_with_nonempty_name": populated_player_names,
            "stadium_count": len(stadiums),
            "team_record_count": len(teams),
            "teams_with_counted_rosters": active_teams,
            "counted_team_roster_reference_count": len(memberships),
            "unique_counted_team_roster_player_count": len(
                {membership["player_index"] for membership in memberships}
            ),
            "unassigned_player_count": len(players) - len(memberships),
            "utf16be_string_count": len(string_pool),
            "empty_utf16be_string_count": empty_string_count,
        },
        "position_labels": [
            {"code": code, "abbreviation": pair[0], "name": pair[1]}
            for code, pair in enumerate(POSITION_LABELS)
        ],
        "player_base_rating_contract": {
            "schema": "apf2k8_player_ratings/v1",
            "field_count": len(PLAYER_RATING_SCHEMA.fields),
            "native_range": [
                PLAYER_RATING_SCHEMA.native_minimum,
                PLAYER_RATING_SCHEMA.native_maximum,
            ],
            "stock_observed_range": [
                PLAYER_RATING_SCHEMA.stock_observed_minimum,
                PLAYER_RATING_SCHEMA.stock_observed_maximum,
            ],
            "runtime_status": PLAYER_RATING_SCHEMA.runtime_status,
            "fields": [
                {
                    "id": field.field_id,
                    "label": field.label,
                    "relative_offset": field.relative_offset,
                    "relative_offset_hex": field.relative_offset_hex,
                    "label_status": field.label_status,
                }
                for field in PLAYER_RATING_SCHEMA.fields
            ],
        },
        "root_table_02_pointer_inventory": table_02,
        "stadiums": stadiums,
        "teams": teams,
        "players": players,
        "team_roster_memberships": memberships,
        "worked": [
            "decoded the sole roster/ROST file through the bounded APF IFF/H7A path",
            "bounded all 40 root count/pointer pairs and all nonempty array spans",
            "resolved the complete UTF-16BE string pool to the exact resource end",
            "exported executable-backed player positions and biography/accolade strings",
            "exported 27 named and one neutrally labeled executable-backed base ratings per player",
            "exported team counted-roster pointers and team-to-stadium relationships",
        ],
        "failed": [
            "no reversible roster writer is emitted because ownership/capacity/integrity rules are incomplete",
            "unknown root-table, ability, tier, appearance, equipment, and behavior semantics are intentionally not guessed",
        ],
        "portme": [
            "// PORTME: root tables 1-2 and 5-39 require exact consumer traces before semantic export",
            "// PORTME: player/team appearance, face, equipment, ability, tier, and behavior fields remain unnamed",
            "// PORTME: fix the runtime-falsified rebuilt-ROST transport before exposing any base-rating writer",
            "// PORTME: implement safe import only after string allocation, pointer rebuilding, H7A recompression, and archive integrity behavior are proved",
            "// PORTME: trace the resource registry structure around XEX data 0x82017D78 and all nested relocation callbacks",
        ],
    }


def write_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _tsv(path: Path, header: Iterable[str], rows: Iterable[Iterable[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def write_players_tsv(path: Path, players: list[dict[str, object]]) -> None:
    extra = [label for _, label in PLAYER_STRING_FIELDS.items() if label not in ("first_name", "last_name")]
    header = [
        "player_index", "record_offset", "first_name", "last_name",
        "position_code", "position_abbreviation", "position_name",
        *[f"rating_{field.field_id}" for field in PLAYER_RATING_SCHEMA.fields],
        "hall_of_fame_induction_year", "championship_count",
        "championship_game_appearance_count", "all_pro_game_count",
        *extra, "team_indices", "team_names", "raw_record_sha256",
    ]
    rows = []
    for player in players:
        strings = player["strings"]
        memberships = player["team_memberships"]
        rows.append(
            [
                player["player_index"], player["record_offset"],
                player["first_name"], player["last_name"],
                player["position_code"], player["position_abbreviation"],
                player["position_name"],
                *[
                    player["base_ratings"][field.field_id]
                    for field in PLAYER_RATING_SCHEMA.fields
                ],
                player["hall_of_fame_induction_year_at_0x112"],
                player["championship_count_at_0x114"],
                player["championship_game_appearance_count_at_0x115"],
                player["all_pro_game_count_at_0x116"],
                *[strings[label] for label in extra],
                ";".join(str(row["team_index"]) for row in memberships),
                ";".join(str(row["team_name"]) for row in memberships),
                player["raw_record_sha256"],
            ]
        )
    _tsv(path, header, rows)


def write_teams_tsv(path: Path, teams: list[dict[str, object]]) -> None:
    header = [
        "team_index", "record_offset", "display_name", "abbreviation",
        "numeric_string_code", "derived_slot_kind", "roster_count",
        "stadium_index", "stadium_name", "category_code_at_0xd0",
        "roster_player_indices", "auxiliary_player_references_0x108_0x11c",
        "raw_record_sha256",
    ]
    rows = [
        [
            team["team_index"], team["record_offset"], team["display_name"],
            team["abbreviation"], team["numeric_string_code"],
            team["derived_slot_kind"], team["roster_count"], team["stadium_index"],
            team["stadium_name"], team["category_code_at_0xd0"],
            ";".join(str(value) for value in team["roster_player_indices"]),
            ";".join("" if value is None else str(value) for value in team["auxiliary_player_references_0x108_0x11c"]),
            team["raw_record_sha256"],
        ]
        for team in teams
    ]
    _tsv(path, header, rows)


def write_stadiums_tsv(path: Path, stadiums: list[dict[str, object]]) -> None:
    header = [
        "stadium_index", "record_offset", "display_name", "asset_key",
        "capacity", "description", "raw_record_sha256",
    ]
    rows = [
        [
            item["stadium_index"], item["record_offset"], item["display_name"],
            item["asset_key"], item["capacity"], item["description"],
            item["raw_record_sha256"],
        ]
        for item in stadiums
    ]
    _tsv(path, header, rows)


def write_memberships_tsv(
    path: Path,
    memberships: list[dict[str, int]],
    teams: list[dict[str, object]],
    players: list[dict[str, object]],
) -> None:
    header = [
        "team_index", "team_name", "roster_slot", "player_index",
        "first_name", "last_name", "position_abbreviation",
    ]
    rows = []
    for item in memberships:
        team = teams[item["team_index"]]
        player = players[item["player_index"]]
        rows.append(
            [
                item["team_index"], team["display_name"], item["roster_slot"],
                item["player_index"], player["first_name"], player["last_name"],
                player["position_abbreviation"],
            ]
        )
    _tsv(path, header, rows)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to the extracted APF 0A volume")
    parser.add_argument("--report", type=Path, help="write full deterministic JSON")
    parser.add_argument("--players-tsv", type=Path, help="write proved player fields")
    parser.add_argument("--teams-tsv", type=Path, help="write proved team fields")
    parser.add_argument("--stadiums-tsv", type=Path, help="write proved stadium fields")
    parser.add_argument(
        "--memberships-tsv", type=Path, help="write one row per counted team roster slot"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        data, source = load_roster(args.index)
        report = build_report(data, source)
        if args.report is not None:
            write_json(args.report, report)
        if args.players_tsv is not None:
            write_players_tsv(args.players_tsv, report["players"])
        if args.teams_tsv is not None:
            write_teams_tsv(args.teams_tsv, report["teams"])
        if args.stadiums_tsv is not None:
            write_stadiums_tsv(args.stadiums_tsv, report["stadiums"])
        if args.memberships_tsv is not None:
            write_memberships_tsv(
                args.memberships_tsv,
                report["team_roster_memberships"],
                report["teams"],
                report["players"],
            )
        summary = report["summary"]
        print(
            "APF_ROSTER_PARSE_PASS "
            f"players={summary['player_count']} teams={summary['team_record_count']} "
            f"stadiums={summary['stadium_count']} memberships="
            f"{summary['counted_team_roster_reference_count']} strings="
            f"{summary['utf16be_string_count']} sha256={source['decoded_sha256']}"
        )
        return 0
    except (RosterError, apf_inner.FormatError, apf_outer.FormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
