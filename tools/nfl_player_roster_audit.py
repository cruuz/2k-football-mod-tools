#!/usr/bin/env python3
"""Audit practical NFL 2K5 player fields in the pinned main disc ROST.

This is a read-only evidence tool.  It combines the strict ROST inventory with
small, pinned XBE instruction/data witnesses for player names, membership,
face/head ID, jersey number, position, and a deliberately small ratings subset.
It never applies save-file offsets to the disc resource and never writes game
data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from xbe_info import Xbe, XbeError


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "nfl2k5_player_roster_audit/v1"
ROSTER_SCHEMA = "nfl2k5_roster_inventory/v1"

EXPECTED_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
EXPECTED_PACK0_SHA256 = (
    "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
)
EXPECTED_BODY_SHA256 = (
    "b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae"
)

ROST_OUTER_OFFSET = 0x00392800
ROST_WRAPPER_SIZE = 0x20
ROST_BODY_SIZE = 593_760
PLAYER_STRIDE = 0x54
TEAM_STRIDE = 0x1F4
TEAM_SLOT_COUNT = 65
JERSEY_WORD_OFFSET = 0x20
JERSEY_SHIFT = 3
JERSEY_MASK = 0x7F
FACE_ID_OFFSET = 0x06
POSITION_OFFSET = 0x35
RATING_FIRST = 0x36
RATING_AFTER = 0x52

POSITION_NAME_TABLE_VA = 0x004F2718
POSITION_NAME_LOOKUP_VA = 0x000E5FB0
POSITION_ACCESSOR_VA = 0x00131EE0
JERSEY_RENDERER_VA = 0x00119B10
FACE_FORMATTER_VA = 0x000912E0
RATING_LABEL_TABLE_VA = 0x004F5258
RATING_VALUE_TABLE_VA = 0x004F55B8
RATING_LABEL_STUB_FIRST = 0x000E5CC0
RATING_LABEL_STUB_COUNT = 27
RATING_LABEL_STUB_STRIDE = 0x10

POSITION_ABBREVIATIONS = (
    "QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB",
    "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE",
)
POSITION_FULL_NAMES = (
    "Quarterback", "Kicker", "Punter", "Wide Receiver", "Cornerback",
    "Free Safety", "Strong Safety", "Halfback", "Fullback", "Tight End",
    "Outside Linebacker", "Inside Linebacker", "Center", "Guard", "Tackle",
    "Defensive Tackle", "Defensive End",
)
RATING_LABELS = (
    "SPEED", "AGILITY", "STRENGTH", "JUMPING", "STAMINA", "SECURE BALL",
    "BREAK TACKLE", "DURABILITY", "LEADERSHIP", "PASS ACC", "ARM STRENGTH",
    "READ COVERAGE", "POWER RUN STYLE", "CATCH", "RUN ROUTE", "RUN BLOCKING",
    "PASS BLOCKING", "TACKLE", "PASS RUSH", "RUN COVERAGE", "COVERAGE",
    "KICK POWER", "KICK ACCURACY", "KICKING STYLE", "AGGRESSION",
    "CONSISTENCY", "COMPOSURE",
)

DEFAULT_XBE = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
DEFAULT_PACK0 = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
DEFAULT_ROSTER = ROOT / "reports/assets/nfl2k5_roster.json"
DEFAULT_OUTPUT = ROOT / "reports/assets/nfl2k5_player_roster_audit.json"
DEFAULT_PLAYERS_TSV = ROOT / "reports/assets/nfl2k5_player_roster_players.tsv"
DEFAULT_BINDINGS_TSV = ROOT / "reports/assets/nfl2k5_player_rating_ui_bindings.tsv"


class AuditError(ValueError):
    """Raised when a pinned input or a structural invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_roster(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    require(report.get("schema") == ROSTER_SCHEMA, "unsupported roster report schema")
    resources = [item for item in report["resources"] if item["outer_index"] == 5]
    require(len(resources) == 1, "main ROST resource selection changed")
    resource = resources[0]
    require(resource["label"] == "roster", "outer 5 is not the main roster")
    require(resource["body_sha256"] == EXPECTED_BODY_SHA256,
            "main ROST report body hash changed")
    return report, resource


def load_body(path: Path) -> bytes:
    require(sha256_file(path) == EXPECTED_PACK0_SHA256, "retail pack 0 hash changed")
    with path.open("rb") as stream:
        stream.seek(ROST_OUTER_OFFSET)
        wrapper = stream.read(ROST_WRAPPER_SIZE)
        require(len(wrapper) == ROST_WRAPPER_SIZE, "short main ROST wrapper")
        require(struct.unpack("<4s7I", wrapper) ==
                (b"ROST", ROST_BODY_SIZE, ROST_BODY_SIZE, 0, 0, 0, 0, 0),
                "main ROST wrapper changed")
        body = stream.read(ROST_BODY_SIZE)
    require(len(body) == ROST_BODY_SIZE, "short main ROST body")
    require(hashlib.sha256(body).hexdigest() == EXPECTED_BODY_SHA256,
            "main ROST body hash changed")
    return body


def i32(data: bytes, offset: int) -> int:
    require(0 <= offset <= len(data) - 4, f"i32 outside body at 0x{offset:x}")
    return struct.unpack_from("<i", data, offset)[0]


def relative_target(data: bytes, field: int, label: str) -> int | None:
    value = i32(data, field)
    if value == 0:
        return None
    target = field + value - 1
    require(0 <= target < len(data), f"{label} pointer resolves outside body")
    return target


def utf16z(data: bytes, offset: int, label: str) -> str:
    require(offset % 2 == 0, f"{label} is not aligned UTF-16LE")
    end = offset
    while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
        end += 2
    require(end + 1 < len(data), f"{label} has no UTF-16LE terminator")
    return data[offset:end].decode("utf-16le")


def known_string_pointer_references(
    resource: dict[str, Any], body: bytes
) -> Counter[int]:
    result: Counter[int] = Counter()
    domains = (
        ("teams", (0x104, 0x108, 0x10C, 0x138, 0x13C)),
        ("stadiums", (0x00, 0x08, 0x0C, 0x10, 0x14)),
        ("coaches", (0x00, 0x04, 0x08, 0x0C, 0x10)),
        ("colleges", (0x00,)),
        ("players", (0x10, 0x14)),
        ("team_labels", (0x00, 0x04)),
        ("generated_names", (0x00, 0x04)),
        ("historic_descriptors", (0x0C,)),
    )
    for collection, fields in domains:
        for item in resource.get(collection, []):
            base = int(item["offset"])
            for relative in fields:
                target = relative_target(
                    body, base + relative,
                    f"{collection} {item.get('index')} +0x{relative:x}",
                )
                if target is not None:
                    result[target] += 1
    return result


def xbe_bytes(xbe: Xbe, address: int, size: int) -> bytes:
    offset = xbe.va_to_offset(address, size)
    return xbe.data[offset:offset + size]


def u32_va(xbe: Xbe, address: int) -> int:
    return struct.unpack_from("<I", xbe.data, xbe.va_to_offset(address, 4))[0]


def validate_xbe_witnesses(xbe: Xbe) -> dict[str, Any]:
    require(hashlib.sha256(xbe.data).hexdigest() == EXPECTED_XBE_SHA256,
            "retail XBE hash changed")

    position_lookup = xbe_bytes(xbe, POSITION_NAME_LOOKUP_VA, 8)
    require(position_lookup == bytes.fromhex("8b048d18274f00c3"),
            "position-name lookup machine code changed")
    position_accessor = xbe_bytes(xbe, POSITION_ACCESSOR_VA, 0x3C)
    require(position_accessor.count(bytes.fromhex("0fb64635")) == 2,
            "position accessor no longer reads player +0x35")
    jersey_renderer = xbe_bytes(xbe, JERSEY_RENDERER_VA, 0xDE)
    jersey_pattern = bytes.fromhex("8b4720c1e80383e07f")
    require(jersey_renderer.count(jersey_pattern) == 1,
            "jersey renderer extraction pattern changed")
    face_formatter = xbe_bytes(xbe, FACE_FORMATTER_VA, 0x3B)
    require(face_formatter.count(bytes.fromhex("0fb74106")) == 1,
            "face formatter no longer reads unsigned u16 player +0x06")

    position_rows: list[dict[str, Any]] = []
    pointers = [u32_va(xbe, POSITION_NAME_TABLE_VA + index * 4)
                for index in range(len(POSITION_FULL_NAMES))]
    names = [xbe.utf16z_va(pointer) for pointer in pointers]
    require(tuple(names) == POSITION_FULL_NAMES, "position full-name table changed")
    for code, (abbreviation, full_name, pointer) in enumerate(
        zip(POSITION_ABBREVIATIONS, names, pointers)
    ):
        position_rows.append({
            "code": code,
            "abbreviation": abbreviation,
            "full_name": full_name,
            "name_pointer_virtual_address": f"0x{pointer:08X}",
        })

    label_names: dict[int, str] = {}
    for index, expected in enumerate(RATING_LABELS):
        address = RATING_LABEL_STUB_FIRST + index * RATING_LABEL_STUB_STRIDE
        stub = xbe_bytes(xbe, address, RATING_LABEL_STUB_STRIDE)
        require(stub[:3] == b"\x85\xc9\xb8" and stub[7:10] == b"\x75\x05\xb8" and
                stub[14] == 0xC3, f"rating label stub changed at 0x{address:08x}")
        pointer = struct.unpack_from("<I", stub, 10)[0]
        label = xbe.utf16z_va(pointer)
        require(label == expected, f"rating label changed at index {index}")
        label_names[address] = label

    bindings: list[dict[str, Any]] = []
    label_offset_counts: dict[str, Counter[int]] = {
        label: Counter() for label in RATING_LABELS
    }
    for position_code in range(len(POSITION_FULL_NAMES)):
        for slot in range(12):
            table_index = position_code * 12 + slot
            label_callback = u32_va(xbe, RATING_LABEL_TABLE_VA + table_index * 4)
            value_callback = u32_va(xbe, RATING_VALUE_TABLE_VA + table_index * 4)
            require(label_callback in label_names,
                    f"unknown rating label callback 0x{label_callback:08x}")
            wrapper = xbe_bytes(xbe, value_callback, 0x60)
            matches = list(re.finditer(b"\x0f\xbe\x46(.)", wrapper, re.DOTALL))
            require(matches, f"value callback 0x{value_callback:08x} has no player byte load")
            raw_offset = matches[0].group(1)[0]
            require(RATING_FIRST <= raw_offset < RATING_AFTER,
                    f"value callback selects non-rating +0x{raw_offset:x}")
            label = label_names[label_callback]
            label_offset_counts[label][raw_offset] += 1
            bindings.append({
                "position_code": position_code,
                "position": POSITION_ABBREVIATIONS[position_code],
                "slot": slot,
                "label": label,
                "raw_player_byte_offset": raw_offset,
                "label_callback_virtual_address": f"0x{label_callback:08X}",
                "value_callback_virtual_address": f"0x{value_callback:08X}",
            })
    require(len(bindings) == 17 * 12, "rating UI binding count changed")

    stable = {
        "speed": {
            "label": "SPEED", "offset": 0x36, "occurrences": 16,
            "position_codes": [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
        },
        "consistency": {
            "label": "CONSISTENCY", "offset": 0x50, "occurrences": 16,
            "position_codes": [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
        },
        "aggression": {
            "label": "AGGRESSION", "offset": 0x51, "occurrences": 11,
            "position_codes": [4, 5, 6, 8, 10, 11, 12, 13, 14, 15, 16],
        },
    }
    for name, item in stable.items():
        actual = label_offset_counts[str(item["label"])]
        require(actual == Counter({int(item["offset"]): int(item["occurrences"])}),
                f"stable rating binding changed: {name} -> {dict(actual)}")
        actual_positions = sorted({
            int(binding["position_code"])
            for binding in bindings
            if binding["label"] == item["label"] and
               binding["raw_player_byte_offset"] == item["offset"]
        })
        require(actual_positions == item["position_codes"],
                f"stable rating position coverage changed: {name}")

    return {
        "position_accessor": {
            "virtual_address": f"0x{POSITION_ACCESSOR_VA:08X}",
            "operation": "return/override path reads unsigned player byte +0x35",
            "machine_pattern": "0f b6 46 35",
        },
        "position_name_lookup": {
            "virtual_address": f"0x{POSITION_NAME_LOOKUP_VA:08X}",
            "table_virtual_address": f"0x{POSITION_NAME_TABLE_VA:08X}",
            "operation": "return position_full_name_table[code]",
        },
        "jersey_number_renderer": {
            "virtual_address": f"0x{JERSEY_RENDERER_VA:08X}",
            "operation": "(player_u32_at_0x20 >> 3) & 0x7f, then divide by 10 into digit textures",
            "machine_pattern": "8b 47 20 c1 e8 03 83 e0 7f",
        },
        "face_asset_formatter": {
            "virtual_address": f"0x{FACE_FORMATTER_VA:08X}",
            "operation": "format f%04d from unsigned player_u16_at_0x06",
            "machine_pattern": "0f b7 41 06",
        },
        "rating_ui_dispatch": {
            "label_dispatch_virtual_address": "0x000E65F0",
            "value_dispatch_virtual_address": "0x000E6620",
            "label_table_virtual_address": f"0x{RATING_LABEL_TABLE_VA:08X}",
            "value_table_virtual_address": f"0x{RATING_VALUE_TABLE_VA:08X}",
            "binding_count": len(bindings),
            "scope": "17 retail positions x 12 displayed rating slots",
        },
        "positions": position_rows,
        "rating_ui_bindings": bindings,
        "stable_rating_fields": stable,
    }


def parse_players(
    resource: dict[str, Any], body: bytes, references: Counter[int],
    rating_bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tables = resource["tables"]
    require((tables["primary_players"]["offset"], tables["primary_players"]["count"],
             tables["primary_players"]["stride"]) == (0xAFA8, 2479, PLAYER_STRIDE),
            "primary player table changed")
    require((tables["secondary_players"]["offset"], tables["secondary_players"]["count"],
             tables["secondary_players"]["stride"]) == (0x3DD14, 68, PLAYER_STRIDE),
            "secondary player table changed")
    require((tables["teams"]["offset"], tables["teams"]["count"],
             tables["teams"]["stride"]) == (0x41C8, 52, TEAM_STRIDE),
            "main team table changed")

    direct_ui_fields = {
        (int(binding["position_code"]), str(binding["label"])):
            int(binding["raw_player_byte_offset"])
        for binding in rating_bindings
    }
    result: list[dict[str, Any]] = []
    for source in resource["players"]:
        offset = int(source["offset"])
        raw = body[offset:offset + PLAYER_STRIDE]
        require(len(raw) == PLAYER_STRIDE and raw.hex() == source["raw_hex"],
                f"player raw record changed: {source['pool']}:{source['index']}")
        first_target = relative_target(body, offset + 0x10, "player first name")
        last_target = relative_target(body, offset + 0x14, "player last name")
        require(first_target == source["first_name_offset"] and
                last_target == source["last_name_offset"], "player name pointer changed")
        require(utf16z(body, first_target, "player first name") == source["first_name"] and
                utf16z(body, last_target, "player last name") == source["last_name"],
                "player name text changed")
        position_code = raw[POSITION_OFFSET]
        require(position_code < len(POSITION_FULL_NAMES),
                f"player position code outside 0..16: {position_code}")
        word_20 = struct.unpack_from("<I", raw, JERSEY_WORD_OFFSET)[0]
        jersey_number = (word_20 >> JERSEY_SHIFT) & JERSEY_MASK
        require(jersey_number <= 100, f"player jersey number exceeds UI sentinel: {jersey_number}")
        ratings = list(raw[RATING_FIRST:RATING_AFTER])
        require(len(ratings) == 28 and all(value <= 100 for value in ratings),
                "player 0..100 byte rating region changed")
        def ui_rating(label: str, expected_offset: int) -> int | None:
            selected = direct_ui_fields.get((position_code, label))
            if selected is None:
                return None
            require(selected == expected_offset,
                    f"{label} is not stable for position {position_code}")
            return raw[expected_offset]

        result.append({
            "pool": source["pool"],
            "index": int(source["index"]),
            "record_body_offset": offset,
            "first_name": source["first_name"],
            "last_name": source["last_name"],
            "first_name_body_offset": first_target,
            "last_name_body_offset": last_target,
            "first_name_known_pointer_reference_count": references[first_target],
            "last_name_known_pointer_reference_count": references[last_target],
            "team_indices": [int(value) for value in source["team_refs"]],
            "college_index": source["college_index"],
            "college_name": source["college_name"],
            "face_id": struct.unpack_from("<H", raw, FACE_ID_OFFSET)[0],
            "jersey_number": jersey_number,
            "jersey_word_20": f"0x{word_20:08x}",
            "position_code": position_code,
            "position": POSITION_ABBREVIATIONS[position_code],
            "position_full_name": POSITION_FULL_NAMES[position_code],
            "speed_ui_rating": ui_rating("SPEED", 0x36),
            "consistency_ui_rating": ui_rating("CONSISTENCY", 0x50),
            "aggression_ui_rating": ui_rating("AGGRESSION", 0x51),
            "rating_bytes_36_51": ratings,
        })
    require(len(result) == 2547, "main player total changed")
    return result


def validate_membership(
    resource: dict[str, Any], body: bytes, players: list[dict[str, Any]]
) -> dict[str, Any]:
    offsets = {int(player["record_body_offset"]): player for player in players}
    membership_count = 0
    referenced: Counter[tuple[str, int]] = Counter()
    for team in resource["teams"]:
        base = int(team["offset"])
        count = body[base + 0x11C]
        require(count == team["roster_size"] and count <= TEAM_SLOT_COUNT,
                f"team {team['index']} roster count changed")
        for slot in range(TEAM_SLOT_COUNT):
            target = relative_target(body, base + slot * 4,
                                     f"team {team['index']} roster slot {slot}")
            if slot < count:
                require(target in offsets, "active team slot does not select a player record")
                player = offsets[target]
                referenced[(str(player["pool"]), int(player["index"]))] += 1
                membership_count += 1
            else:
                require(target is None, "unused team roster slot is non-null")
    for player in players:
        expected = len(player["team_indices"])
        actual = referenced[(str(player["pool"]), int(player["index"]))]
        require(actual == expected, "player team-reference count changed")
    return {
        "team_count": 52,
        "slots_per_team": TEAM_SLOT_COUNT,
        "roster_count_byte_offset": 0x11C,
        "active_membership_pointer_count": membership_count,
        "pointer_formula": "target = pointer_field + signed_i32 - 1",
        "all_active_slots_select_exact_0x54_player_boundaries": True,
        "all_unused_slots_null": True,
    }


def build_proof(players: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [player for player in players
               if player["pool"] == "primary_players" and player["index"] == 512]
    require(len(matches) == 1, "proof player selection changed")
    player = matches[0]
    require((player["first_name"], player["last_name"], player["jersey_number"],
             player["position"], player["face_id"], player["team_indices"]) ==
            ("Joey", "Harrington", 3, "QB", 3593, [18]),
            "proof player facts changed")
    require(player["record_body_offset"] == 0x157A8 and
            player["first_name_body_offset"] == 0x7EFDA and
            player["last_name_body_offset"] == 0x7EFE4,
            "proof player offsets changed")
    require(player["first_name_known_pointer_reference_count"] == 1 and
            player["last_name_known_pointer_reference_count"] == 1,
            "proof player name allocation is shared")
    return {
        "target": "main disc ROST primary_players:512 / Detroit slot 35",
        "before": {
            "first_name": "Joey", "last_name": "Harrington", "jersey_number": 3,
            "position": "QB", "face_id": 3593, "team_indices": [18],
        },
        "after": {
            "first_name": "Noah", "last_name": "CodexProof", "jersey_number": 42,
            "position": "QB", "face_id": 3593, "team_indices": [18],
        },
        "record_body_offset": 0x157A8,
        "first_name_body_offset": 0x7EFDA,
        "last_name_body_offset": 0x7EFE4,
        "name_allocations": {
            "first_name_utf16le_bytes_including_terminator": 10,
            "last_name_utf16le_bytes_including_terminator": 22,
            "both_known_pointer_reference_counts": 1,
        },
        "jersey_edit": {
            "word_offset": 0x20,
            "mask_before_shift": "0x000003f8",
            "preservation_formula": "new_word = (old_word & ~0x3f8) | ((42 & 0x7f) << 3)",
        },
        "unchanged_by_workflow_contract": [
            "position byte +0x35", "face ID u16 +0x06", "college/name pointers",
            "all 65 Detroit team membership pointers", "Detroit roster count 53",
            "every unrelated player bit/byte", "ROST wrapper", "default.xbe",
            "XDVDFS tree and extents",
        ],
        "runtime_visibility_proved": False,
    }


def write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def player_tsv_rows(players: list[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for player in players:
        yield {
            "pool": player["pool"],
            "player_index": player["index"],
            "record_body_offset": f"0x{int(player['record_body_offset']):x}",
            "first_name": player["first_name"],
            "last_name": player["last_name"],
            "team_indices": ";".join(str(value) for value in player["team_indices"]),
            "position_code": player["position_code"],
            "position": player["position"],
            "jersey_number": player["jersey_number"],
            "face_id": player["face_id"],
            "speed_ui_rating": (
                "" if player["speed_ui_rating"] is None else player["speed_ui_rating"]
            ),
            "consistency_ui_rating": (
                "" if player["consistency_ui_rating"] is None
                else player["consistency_ui_rating"]
            ),
            "aggression_ui_rating": (
                "" if player["aggression_ui_rating"] is None
                else player["aggression_ui_rating"]
            ),
            "college_name": player["college_name"] or "",
        }


def binding_tsv_rows(bindings: list[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for binding in bindings:
        yield {
            **binding,
            "raw_player_byte_offset": f"0x{int(binding['raw_player_byte_offset']):02x}",
        }


def run(
    xbe_path: Path, pack_path: Path, roster_path: Path,
    output_path: Path, players_tsv: Path, bindings_tsv: Path,
) -> dict[str, Any]:
    _, resource = load_roster(roster_path)
    body = load_body(pack_path)
    references = known_string_pointer_references(resource, body)
    xbe = Xbe(xbe_path)
    executable = validate_xbe_witnesses(xbe)
    players = parse_players(
        resource, body, references, executable["rating_ui_bindings"]
    )
    membership = validate_membership(resource, body, players)
    proof = build_proof(players)

    result = {
        "schema": SCHEMA,
        "sources": {
            "default_xbe": {"path": str(xbe_path), "sha256": EXPECTED_XBE_SHA256},
            "pack0": {"path": str(pack_path), "sha256": EXPECTED_PACK0_SHA256},
            "roster_report": {
                "path": str(roster_path), "sha256": sha256_file(roster_path),
            },
            "main_roster_body": {
                "outer_index": 5, "outer_offset_in_pack0": ROST_OUTER_OFFSET,
                "size": len(body), "sha256": EXPECTED_BODY_SHA256,
            },
        },
        "layout": {
            "primary_players": {"offset": 0xAFA8, "count": 2479, "stride": PLAYER_STRIDE},
            "secondary_players": {"offset": 0x3DD14, "count": 68, "stride": PLAYER_STRIDE},
            "teams": {"offset": 0x41C8, "count": 52, "stride": TEAM_STRIDE},
            "player_fields": {
                "college_pointer": 0x00,
                "face_id_u16": FACE_ID_OFFSET,
                "first_name_pointer": 0x10,
                "last_name_pointer": 0x14,
                "jersey_number": "u32 +0x20 bits 3..9",
                "auxiliary_pointer": 0x2C,
                "position_code_u8": POSITION_OFFSET,
                "rating_like_bytes_clamped_0_100": "+0x36..+0x51 inclusive",
            },
        },
        "executable_evidence": {
            key: value for key, value in executable.items()
            if key not in {"positions", "rating_ui_bindings", "stable_rating_fields"}
        },
        "position_enum": executable["positions"],
        "stable_rating_fields": executable["stable_rating_fields"],
        "rating_ui_bindings": executable["rating_ui_bindings"],
        "membership": membership,
        "players": players,
        "safe_fixed_size_proof": proof,
        "disc_vs_save_boundary": {
            "proved_here": "retail disc seed ROST in vc_53450030/0 outer entry 5",
            "xbe_load_and_serialization_evidence": [
                "0x000C0500 forward relocation", "0x000C0730 inverse serialization",
                "0x000C1030 imported-roster merge/copy", "0x002D17B0 writer/build path",
            ],
            "not_proved_here": [
                "Xbox dashboard save-container header/signature/checksum layout",
                "which existing profile/save takes precedence over the modified disc seed",
                "runtime visibility with an existing saved roster or franchise",
            ],
            "practical_rule": (
                "The proof XISO changes the disc-default roster. A separately loaded saved roster "
                "can override those values; test with no saved roster and then with a controlled save."
            ),
        },
        "summary": {
            "player_count": len(players),
            "primary_player_count": 2479,
            "secondary_player_count": 68,
            "team_count": 52,
            "position_count": 17,
            "rating_ui_binding_count": len(executable["rating_ui_bindings"]),
            "promoted_stable_rating_count": 3,
            "proof_player": "Joey Harrington -> Noah CodexProof",
            "proof_jersey": "3 -> 42",
        },
        "claims": {
            "disc_player_table_proved": True,
            "team_membership_pointer_schema_proved": True,
            "player_name_pointer_schema_proved": True,
            "jersey_number_bits_proved": True,
            "position_byte_and_enum_proved": True,
            "face_id_proved": True,
            "three_stable_rating_fields_proved": True,
            "all_28_rating_semantics_proved": False,
            "save_container_schema_proved": False,
            "runtime_visibility_proved": False,
            "originals_modified": False,
        },
        "portme": [
            "// PORTME: controlled-difference and instruction-trace the position-dependent rating UI bindings before assigning every +0x36..+0x51 byte a global semantic name.",
            "// PORTME: map the Xbox save/profile container, integrity fields, and load precedence; disc ROST offsets are not save-container offsets.",
            "// PORTME: boot the copied proof XISO with no roster save and capture roster UI plus gameplay before claiming runtime visibility.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(
        players_tsv,
        ["pool", "player_index", "record_body_offset", "first_name", "last_name",
         "team_indices", "position_code", "position", "jersey_number", "face_id",
         "speed_ui_rating", "consistency_ui_rating", "aggression_ui_rating",
         "college_name"],
        player_tsv_rows(players),
    )
    write_tsv(
        bindings_tsv,
        ["position_code", "position", "slot", "label", "raw_player_byte_offset",
         "label_callback_virtual_address", "value_callback_virtual_address"],
        binding_tsv_rows(executable["rating_ui_bindings"]),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, default=DEFAULT_XBE)
    parser.add_argument("--pack0", type=Path, default=DEFAULT_PACK0)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--players-tsv", type=Path, default=DEFAULT_PLAYERS_TSV)
    parser.add_argument("--bindings-tsv", type=Path, default=DEFAULT_BINDINGS_TSV)
    args = parser.parse_args(argv)
    try:
        result = run(
            args.xbe, args.pack0, args.roster,
            args.output, args.players_tsv, args.bindings_tsv,
        )
    except (OSError, AuditError, XbeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"nfl_player_roster_audit: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_PLAYER_ROSTER_AUDIT_OK "
        f"players={result['summary']['player_count']} "
        f"positions={result['summary']['position_count']} "
        f"bindings={result['summary']['rating_ui_binding_count']} "
        "runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
