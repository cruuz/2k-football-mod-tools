#!/usr/bin/env python3
"""Build a read-only feasibility matrix for NFL 2K5 franchise fixes.

This joins already recovered Xbox executable, roster, and draft evidence.  It
does not infer PS2 offsets, decode a franchise save, or emit a game patch.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "nfl2k5_franchise_limit_feasibility/v1"

SOURCES = {
    "xbox_xbe": (
        ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe",
        11_948_032,
        "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
    ),
    "function_ledger": (
        ROOT / "research/functions/nfl2k5/functions.tsv",
        9_431_836,
        "902eb0e5f504bcc24ee55aa895d8fa65e4cb3db05409eb8daaf147e3d74f28f7",
    ),
    "gameplay_draft_audit": (
        ROOT / "reports/gameplay_tuning/gameplay_tuning_ai_draft_audit.json",
        54_545,
        "0c1c47c7f025f9fbb303b9a7d78e7aaf8e9d3c4d603a47bc7819d5ded43557ec",
    ),
    "draft_integrity_probe": (
        ROOT / "reports/gameplay_tuning/nfl_draft_weight_xbe_integrity_probe.json",
        5_720,
        "4e96733fce37f07ec53ad9ab7f74b6ee6c7c693dfa153256c2899c3f7a4c270c",
    ),
    "disc_roster_audit": (
        ROOT / "reports/assets/nfl2k5_player_roster_audit.json",
        2_842_500,
        "795336ad0092e6ba6c806e314bb7515ecc0e11103bd889557229f4f1a92451c2",
    ),
    "roster_inventory": (
        ROOT / "reports/assets/nfl2k5_roster.json",
        5_742_274,
        "de5676af8e996be1ff1ce62ac50e507af89f6ad111e2708c286553c65e7d1f79",
    ),
    "pseudo_super_bowl": (
        ROOT / "research/functions/nfl2k5/pseudo_c/shard_005632_006143.c",
        573_061,
        "49cdfffd281b809d460bbc25e13b93b26f21febbfab4c8ec7eba1f677ef6488b",
    ),
    "pseudo_cap_value": (
        ROOT / "research/functions/nfl2k5/pseudo_c/shard_006144_006655.c",
        483_072,
        "970edf65b824a52b9d55de97ddb220e725de331d0ea8a96e2ceab3330567cca3",
    ),
    "pseudo_season_gate": (
        ROOT / "research/functions/nfl2k5/pseudo_c/shard_009728_010239.c",
        682_015,
        "3f835439c51715804acbf91b4556027235bc86222eee4a806e38f41de1fc3bdd",
    ),
    "pseudo_cap_validator": (
        ROOT / "research/functions/nfl2k5/pseudo_c/shard_011776_012287.c",
        577_357,
        "a61121bbc422d79ff15649b7e3137ac22f7cef3598fb722740a620f9d24de6df",
    ),
}


class FeasibilityError(ValueError):
    """A pinned source or recovered invariant differs."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FeasibilityError(message)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_pinned(path: Path, size: int, digest: str, label: str) -> bytes:
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
            f"{label} must be a non-symlink regular file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode) and opened.st_size == size,
                f"{label} size differs")
        require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                f"{label} identity changed before read")
        data = bytearray()
        while len(data) < size:
            chunk = os.read(descriptor, min(16 * 1024 * 1024, size - len(data)))
            require(bool(chunk), f"{label} shortened during read")
            data.extend(chunk)
        require(not os.read(descriptor, 1), f"{label} grew during read")
        payload = bytes(data)
        require(sha256(payload) == digest, f"{label} SHA-256 differs")
        after = path.stat(follow_symlinks=False)
        require((after.st_dev, after.st_ino, after.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                f"{label} pathname changed during read")
        return payload
    finally:
        os.close(descriptor)


def load_sources() -> dict[str, bytes]:
    return {
        label: read_pinned(path, size, digest, label)
        for label, (path, size, digest) in SOURCES.items()
    }


def parse_ledger(payload: bytes) -> dict[str, dict[str, str]]:
    text = payload.decode("utf-8")
    rows = list(csv.DictReader(text.splitlines(), delimiter="\t"))
    require(len(rows) == 20_131, "NFL function ledger row count differs")
    by_address = {row["address"].upper(): row for row in rows}
    require(len(by_address) == len(rows), "NFL function ledger has duplicate addresses")
    return by_address


def extract_function(payload: bytes, symbol: str) -> str:
    text = payload.decode("utf-8")
    marker = f" * symbol: {symbol}\n"
    marker_at = text.find(marker)
    require(marker_at >= 0, f"missing pseudo-C function {symbol}")
    start = text.rfind("/*\n * index:", 0, marker_at)
    require(start >= 0, f"missing pseudo-C header for {symbol}")
    end = text.find("\n\n/*\n * index:", marker_at)
    if end < 0:
        end = len(text)
    function = text[start:end].rstrip() + "\n"
    require(function.count(marker) == 1, f"ambiguous pseudo-C function {symbol}")
    return function


def validate_function_rows(rows: dict[str, dict[str, str]]) -> None:
    expected = {
        "0X00077470": ("FUN_00077470", "0x00077470-0x00077476"),
        "0X000C4EB0": ("FUN_000c4eb0", "0x000C4EB0-0x000C4EB5"),
        "0X001332B0": (
            "FUN_001332b0", "0x001332B0-0x001332FC,0x00133300-0x00133350"
        ),
        "0X00133A30": ("FUN_00133a30", "0x00133A30-0x00133A4C"),
        "0X00134040": (
            "FUN_00134040", "0x00133FC0-0x0013403B,0x00134040-0x00134132"
        ),
        "0X0013ECA0": ("FUN_0013eca0", "0x0013ECA0-0x0013ECF8"),
        "0X00247B40": ("FUN_00247b40", "0x00247B40-0x00247D01"),
        "0X002480B0": (
            "FUN_002480b0", "0x002480B0-0x002483EC,0x002483F0-0x0024869A"
        ),
        "0X002BAD00": ("FUN_002bad00", "0x002BAD00-0x002BAE36"),
        "0X002BAE90": ("FUN_002bae90", "0x002BAE90-0x002BB1B2"),
        "0X002BB760": ("FUN_002bb760", "0x002BB760-0x002BB7ED"),
        "0X002BC090": (
            "FUN_002bc090", "0x002BC090-0x002BC114,0x002BC120-0x002BC375"
        ),
        "0X002BC380": ("FUN_002bc380", "0x002BC380-0x002BC66F"),
        "0X002BC670": (
            "FUN_002bc670", "0x002BC670-0x002BC85C,0x002BC860-0x002BC8FF"
        ),
        "0X002BD440": ("FUN_002bd440", "0x002BD440-0x002BD879"),
        "0X002BF950": ("FUN_002bf950", "0x002BF950-0x002BF980"),
        "0X0036EE70": ("FUN_0036ee70", "0x0036EE70-0x0036EE7C"),
        "0X0036F0A0": ("FUN_0036f0a0", "0x0036F0A0-0x0036F145"),
        "0X0036F830": ("FUN_0036f830", "0x0036F830-0x0036F938"),
    }
    for address, (name, ranges) in expected.items():
        row = rows.get(address)
        require(row is not None, f"function ledger missing {address}")
        require((row["name"], row["body_ranges"]) == (name, ranges),
                f"function ledger row differs for {address}")
    require("0x0013ECA0:FUN_0013eca0" in rows["0X002BF950"]["callees"],
            "salary-cap validator no longer calls the cap-value path")
    require("0x002480B0:FUN_002480b0" in rows["0X002BF950"]["callers"],
            "salary-cap validator no longer belongs to season advance")
    require("salary cap" in rows["0X002480B0"]["direct_strings"].lower(),
            "season-advance salary-cap message differs")


def u32(payload: bytes, offset: int) -> int:
    require(0 <= offset <= len(payload) - 4, "XBE u32 is outside input")
    return struct.unpack_from("<I", payload, offset)[0]


def xbe_sections(payload: bytes) -> list[dict[str, int | str]]:
    require(payload[:4] == b"XBEH", "pinned Xbox input is not an XBE")
    image_base = u32(payload, 0x104)
    count = u32(payload, 0x11C)
    table_offset = u32(payload, 0x120) - image_base
    require(image_base == 0x10000 and count == 22 and table_offset == 0x370,
            "XBE section-table boundary differs")
    result: list[dict[str, int | str]] = []
    for index in range(count):
        fields = struct.unpack_from("<9I20s", payload, table_offset + index * 56)
        name_at = fields[5] - image_base
        name_end = payload.find(b"\0", name_at, name_at + 64)
        require(name_end >= 0, "XBE section name is unterminated")
        result.append({
            "name": payload[name_at:name_end].decode("ascii"),
            "virtual_address": fields[1],
            "virtual_size": fields[2],
            "raw_address": fields[3],
            "raw_size": fields[4],
        })
    return result


def va_to_offset(payload: bytes, virtual_address: int, size: int) -> int:
    for section in xbe_sections(payload):
        start = int(section["virtual_address"])
        raw_size = int(section["raw_size"])
        if start <= virtual_address and virtual_address + size <= start + raw_size:
            return int(section["raw_address"]) + virtual_address - start
    raise FeasibilityError(
        f"XBE VA 0x{virtual_address:08X}+0x{size:X} is not in raw section data"
    )


def va_bytes(payload: bytes, virtual_address: int, size: int) -> bytes:
    offset = va_to_offset(payload, virtual_address, size)
    return payload[offset:offset + size]


def utf16_at_va(payload: bytes, virtual_address: int, maximum: int = 64) -> str:
    raw = va_bytes(payload, virtual_address, maximum * 2)
    end = 0
    while end + 1 < len(raw) and raw[end:end + 2] != b"\0\0":
        end += 2
    require(end + 1 < len(raw), f"UTF-16 string at 0x{virtual_address:08X} is unterminated")
    return raw[:end].decode("utf-16le")


def validate_super_bowl_venue_selector(
    xbe: bytes, stadium_metadata: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    selector = va_bytes(xbe, 0x001332B0, 0xA1)
    pregame = va_bytes(xbe, 0x00134096, 0x7B)
    season_increment = va_bytes(xbe, 0x00247B40, 0x11)
    require(sha256(selector) ==
            "1b17980494fd9dc22ac2117d48a8773ee54542a5bc5bef0ee9ab2a5ad246e762",
            "Super Bowl stadium selector body differs")
    require(sha256(pregame) ==
            "5cb5bb32bdc79e652c80c23bea8cd94dfcda1a0662ada0c725977040860053de",
            "pregame Super Bowl stadium route differs")
    require(sha256(season_increment) ==
            "8012e68a77208a45c965afc8b7bd758451ea4ee543bfcef7b54d25a1ac44d440",
            "franchise season-index increment differs")
    require(selector[4:9] == bytes.fromhex("e8f71bf9ff") and
            selector[9:16] == bytes.fromhex("83f804772aff24"),
            "Super Bowl selector season-index switch differs")
    # Immediate operands of six `mov ebp, stadium_name_pointer` instructions.
    pointer_offsets = (0x16, 0x1D, 0x24, 0x2B, 0x32, 0x39)
    expected_pointers = (0x00E79528, 0x00E79530, 0x00E79538,
                         0x00E79540, 0x00E79548, 0x00E79550)
    pointers = tuple(struct.unpack_from("<I", selector, offset)[0]
                     for offset in pointer_offsets)
    require(pointers == expected_pointers, "Super Bowl stadium-name pointer table differs")
    stadium_keys = tuple(utf16_at_va(xbe, pointer) for pointer in pointers)
    require(stadium_keys == ("s40", "s42", "s43", "s41", "s44", "s45"),
            "Super Bowl stadium-key mapping differs")
    mapping = [
        {
            "season_index": index,
            "stadium_key": stadium_keys[index],
            **stadium_metadata[stadium_keys[index]],
        }
        for index in range(5)
    ]
    default = {
        "condition": "season_index >= 5",
        "stadium_key": stadium_keys[5],
        **stadium_metadata[stadium_keys[5]],
    }
    return {
        "season_index_getter": "0x000C4EB0 returns franchise state global 0x00E576B8",
        "season_index_increment": "0x00247B40 calls getter, increments ECX, calls 0x000C4EA0",
        "selector": "0x001332B0..0x00133350",
        "selector_sha256": sha256(selector),
        "stadium_record_source": (
            "ROST root +0x10 count / +0x14 table, 0x80-byte stadium records; "
            "selector compares record +0x0C name and returns the matching record"
        ),
        "pregame_route": (
            "0x00134040 calls the selector only after 0x00133A30 reports Super Bowl, "
            "then passes its stadium record to setter 0x00077470"
        ),
        "season_index_mapping": mapping,
        "default_mapping": default,
        "root_cause": "all franchise seasons at index 5 or later collapse to stadium key s45",
        "runtime_reproduced": False,
        "writer_emitted": False,
    }


def validate_trade_logic(xbe: bytes, pseudo_payload: bytes) -> dict[str, Any]:
    bodies = {
        "salary_and_roster_legality": (0x002BAD00, 0x137,
            "ea86f188ffa66201bd8eebff018cfa64a454c48c6e3799c99f1ba4fb9979bef6"),
        "trade_value_and_slot_validator": (0x002BAE90, 0x323,
            "23c786a715f668a51323a1b980a0478e2d2fa0635a3bc90d9f17b20280287409"),
        "normalized_balance_score": (0x002BB760, 0x8E,
            "e0ec784cbfe5fe808ab32788e77df1d36a207864cc52748511d19df4e7a5d7d3"),
        "counteroffer_search": (0x002BC090, 0x2E6,
            "53bfb4ea839ba9fa0fd7616d31607a2814499c3e5585087d21c1db6f2ac139ce"),
        "accept_decline_gate": (0x002BC380, 0x2F0,
            "400c75e30cd3043257746063738f255f0cb831800e05be6ca3db52a64d74c679"),
        "player_valuation": (0x002BD440, 0x43A,
            "04c68607c55cfd54db5a8a94f522bc2f61b6914914dba84b05c511d8d8a4d39c"),
    }
    body_report: dict[str, Any] = {}
    for label, (address, size, expected_hash) in bodies.items():
        body = va_bytes(xbe, address, size)
        require(sha256(body) == expected_hash, f"trade body differs: {label}")
        body_report[label] = {
            "virtual_address": f"0x{address:08X}",
            "byte_size": size,
            "sha256": expected_hash,
        }

    legality = extract_function(pseudo_payload, "FUN_002bad00")
    validator = extract_function(pseudo_payload, "FUN_002bae90")
    balance = extract_function(pseudo_payload, "FUN_002bb760")
    gate = extract_function(pseudo_payload, "FUN_002bc380")
    valuation = extract_function(pseudo_payload, "FUN_002bd440")
    for function, needles in (
        (legality, ("FUN_0013eca0(0)", "FUN_0013ede0()")),
        (validator, ("iVar6 < 3", "local_34", "local_30", "param_3 == 0")),
        (balance, ("FUN_002bae40", "local_8 < _DAT_004e4180", "local_8 = 1.0")),
        (gate, ("FUN_002bb760()", "_DAT_005156a4", "FUN_002bc090")),
        (valuation, ("FUN_00246d80()", "FUN_000c4eb0()", "FUN_002bc9c0")),
    ):
        for needle in needles:
            require(needle in function, f"trade pseudo-C no longer contains {needle!r}")

    threshold_raw = va_bytes(xbe, 0x005156A4, 4)
    threshold = struct.unpack("<f", threshold_raw)[0]
    require(threshold_raw == bytes.fromhex("85eb513f") and
            struct.pack("<f", threshold) == struct.pack("<f", 0.82),
            "trade acceptance threshold differs")
    gate_body = va_bytes(xbe, 0x002BC380, 0x2F0)
    require(struct.pack("<I", 0x005156A4) in gate_body,
            "accept/decline gate no longer references the 0.82 threshold")
    trade_strings = {
        "offer_prompt": (0x00E9A13C, "Offer this trade to the %s?"),
        "declined": (0x00E9A290, "The %s have declined your trade. %s"),
        "accepted": (0x00E9A3B8, "The trade has been accepted."),
    }
    for label, (address, expected) in trade_strings.items():
        require(utf16_at_va(xbe, address) == expected, f"trade string differs: {label}")
    require(struct.pack("<I", 0x00E9A13C) in gate_body and
            struct.pack("<I", 0x00E9A290) in gate_body,
            "accept/decline owner no longer contains prompt/decline strings")
    execution_body = va_bytes(xbe, 0x002BC670, 0x290)
    require(struct.pack("<I", 0x00E9A3B8) in execution_body,
            "trade execution owner no longer contains accepted string")
    return {
        "functions": body_report,
        "acceptance_threshold": {
            "virtual_address": "0x005156A4",
            "float_le_hex": threshold_raw.hex(),
            "value": threshold,
            "consumer": "0x002BC380 accept/decline gate",
        },
        "proved_path": (
            "0x002BAD00 salary/cap legality -> 0x002BAE90 value/slot validation -> "
            "0x002BB760 normalized balance -> 0x002BC380 accept/counteroffer gate -> "
            "0x002BC090 counteroffer search or 0x002BC670 execution"
        ),
        "bounded_interpretation": (
            "The fixed 0.82 constant is an exact acceptance/counteroffer threshold. "
            "It is not proof that lowering it alone improves every CPU trade outcome."
        ),
        "cpu_generated_offer_builder_proved": False,
        "runtime_effect_proved": False,
        "writer_emitted": False,
    }


def validate_pseudo(sources: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    selected = {
        "super_bowl_classifier": (
            "pseudo_super_bowl", "FUN_00133a30",
            ("iVar1 == 9", "iVar1 == 0x14", "return 1;"),
        ),
        "cap_value_path": (
            "pseudo_cap_value", "FUN_0013eca0",
            ("param_3 = DAT_00e3c278 - uVar2;", "FUN_0013e9a0"),
        ),
        "season_advance_gate": (
            "pseudo_season_gate", "FUN_002480b0",
            ("case 7:", "FUN_002bf950();", "under the salary cap", "maximum of 54 players"),
        ),
        "cap_and_roster_validator": (
            "pseudo_cap_validator", "FUN_002bf950",
            ("param_1 + 0x124", "FUN_0013eca0(0)",
             "return *(byte *)(param_1 + 0x11c) < 0x37;"),
        ),
    }
    result: dict[str, dict[str, Any]] = {}
    for label, (source, symbol, needles) in selected.items():
        function = extract_function(sources[source], symbol)
        for needle in needles:
            require(needle in function, f"{symbol} no longer contains {needle!r}")
        result[label] = {
            "symbol": symbol,
            "source": SOURCES[source][0].relative_to(ROOT).as_posix(),
            "function_text_sha256": sha256(function.encode("utf-8")),
            "checked_semantics": list(needles),
        }
    return result


def load_json_source(payload: bytes, schema: str, label: str) -> dict[str, Any]:
    value = json.loads(payload)
    require(payload == canonical_json(value), f"{label} is not canonical JSON")
    require(value.get("schema") == schema, f"{label} schema differs")
    return value


def validate_joined_reports(sources: dict[str, bytes]) -> dict[str, Any]:
    gameplay = load_json_source(
        sources["gameplay_draft_audit"],
        "vc_gameplay_tuning_ai_draft_audit/v1",
        "gameplay/draft audit",
    )
    probe = load_json_source(
        sources["draft_integrity_probe"],
        "nfl2k5_draft_weight_xbe_integrity_probe/v1",
        "draft integrity probe",
    )
    roster = load_json_source(
        sources["disc_roster_audit"],
        "nfl2k5_player_roster_audit/v1",
        "disc roster audit",
    )
    roster_inventory = load_json_source(
        sources["roster_inventory"],
        "nfl2k5_roster_inventory/v1",
        "roster inventory",
    )
    draft = gameplay["nfl2k5"]["cpu_fantasy_draft"]
    table = draft["priority_table"]
    require(table["virtual_address"] == "0x00589588" and len(table["rows"]) == 17,
            "draft priority-table boundary differs")
    require(draft["corrected_priority_builder_boundary"]["range"] ==
            "0x0036EE70-0x0036F095", "draft priority owner differs")
    require(probe["conclusion"]["current_public_writer_safe"] is False,
            "draft integrity probe unexpectedly promotes a writer")
    require(probe["integrity_branches"]["payload_only_stale_section_digest"]
            ["section_digest_matches"] is False,
            "draft stale-digest branch differs")
    require(probe["integrity_branches"]["payload_plus_updated_section_digest"]
            ["signed_header_changed"] is True,
            "draft repaired-digest signed-header branch differs")
    save_boundary = roster["disc_vs_save_boundary"]
    unproved = " ".join(save_boundary["not_proved_here"])
    require("save-container" in unproved and "takes precedence" in unproved and
            save_boundary["proved_here"] ==
            "retail disc seed ROST in vc_53450030/0 outer entry 5",
            "roster audit unexpectedly promotes franchise-save offsets")
    stadium_rows = {
        stadium["asset_code"]: stadium
        for resource in roster_inventory["resources"]
        for stadium in resource["stadiums"]
        if stadium["asset_code"] in {"s40", "s41", "s42", "s43", "s44", "s45"}
    }
    expected_stadiums = {
        "s40": (35, "Super Bowl 2005 Stadium", "Jacksonville, FL"),
        "s42": (36, "Super Bowl 2006 Stadium", "Detroit, MI"),
        "s43": (37, "Super Bowl 2007 Stadium", "Miami, FL"),
        "s41": (38, "Super Bowl 2008 Stadium", "Tempe, AZ"),
        "s44": (39, "Super Bowl Future Stadium", "Los Angeles, CA"),
        "s45": (40, "Ulterior Super Bowl Stadium", "San Jose, CA"),
    }
    require({key: (row["index"], row["display_name"], row["location"])
             for key, row in stadium_rows.items()} == expected_stadiums,
            "Super Bowl stadium metadata differs")
    stadium_metadata = {
        key: {
            "roster_stadium_index": row["index"],
            "display_name": row["display_name"],
            "location": row["location"],
        }
        for key, row in stadium_rows.items()
    }
    return {
        "gameplay": gameplay,
        "probe": probe,
        "roster": roster,
        "stadium_metadata": stadium_metadata,
    }


def make_matrix(
    joined: dict[str, Any], venue: dict[str, Any], trade: dict[str, Any]
) -> list[dict[str, Any]]:
    table = joined["gameplay"]["nfl2k5"]["cpu_fantasy_draft"]["priority_table"]
    return [
        {
            "id": "cpu_fantasy_draft_priority",
            "user_limitation": "draft and trade logic",
            "current_proof": "exact static algorithm and constant table",
            "proof": {
                "weight_count": 17,
                "table_virtual_address": table["virtual_address"],
                "table_file_offset": table["file_offset"],
                "priority_builder": "0x0036EE70..0x0036F095",
                "pick_path": "0x0036F0A0..0x0036F145 -> 0x0036F830..0x0036F938",
            },
            "likely_mutation_layer": ["Xbox default.xbe or emulator memory patch"],
            "archive_only_fix": False,
            "current_writer_safe": False,
            "feasibility": "near-term experiment, not a released fix",
            "blockers": [
                "changing .rdata invalidates its stored SHA-1",
                "repairing the section digest changes the RSA-signed XBE header",
                "no before/after deterministic fantasy-draft runtime trial exists",
                "Xbox proof does not identify PS2 ELF addresses",
            ],
            "smallest_safe_next": (
                "Apply one weight change only in an authorized copied-XBE/emulator lane, "
                "independently verify changed bytes, boot it, and compare seeded CPU drafts."
            ),
        },
        {
            "id": "cpu_trade_evaluation",
            "user_limitation": "draft and trade logic",
            "current_proof": "exact legality, valuation, balance, and accept/counteroffer path",
            "proof": {
                "trade_feature_present": True,
                "proved_path": trade["proved_path"],
                "acceptance_threshold": trade["acceptance_threshold"],
                "cpu_acceptance_or_offer_scoring_function_proved": True,
                "cpu_generated_offer_builder_proved": False,
                "trade_save_records_mapped": False,
            },
            "likely_mutation_layer": [
                "Xbox default.xbe decision code", "franchise runtime/save state"
            ],
            "archive_only_fix": False,
            "current_writer_safe": False,
            "feasibility": "near-term threshold/valuation experiment; generator remains open",
            "blockers": [
                "the CPU-generated offer builder is not yet completely owned",
                "several valuation inputs and constants still lack stable semantic names",
                "no deterministic identical-offer before/after runtime trial exists",
                "XBE integrity handling is still required for a persistent executable patch",
                "Xbox proof does not identify PS2 ELF addresses",
            ],
            "smallest_safe_next": (
                "Change only the 0.82 threshold in an authorized copied-XBE/emulator lane "
                "and replay an identical controlled offer to prove the decision boundary."
            ),
        },
        {
            "id": "salary_cap_enforcement",
            "user_limitation": "salary cap and contracts",
            "current_proof": "exact season-entry gate, not an accurate cap model",
            "proof": {
                "season_advance_owner": "0x002480B0..0x0024869A",
                "validator": "0x002BF950..0x002BF980",
                "team_total_field": "+0x124 in the runtime team object",
                "cap_value_path": "0x0013ECA0..0x0013ECF8",
                "roster_count_field": "+0x11C; gate requires count < 0x37",
                "annual_cap_growth_formula_proved": False,
            },
            "likely_mutation_layer": [
                "Xbox default.xbe financial code", "franchise runtime/save state"
            ],
            "archive_only_fix": False,
            "current_writer_safe": False,
            "feasibility": "good static foothold; model and serialization still open",
            "blockers": [
                "runtime team +0x124 storage/units are not yet serialized to a save field",
                "cap baseline, annual growth, penalties, and exceptions are not mapped",
                "no controlled franchise save fixture",
                "Xbox proof does not identify PS2 ELF addresses",
            ],
            "smallest_safe_next": (
                "Capture two saves differing by one contract and one season boundary; map "
                "the signed/container delta, then watch +0x124 and the 0x0013ECA0 result."
            ),
        },
        {
            "id": "contract_model_and_serialization",
            "user_limitation": "salary cap and contracts",
            "current_proof": "contract screens exist; dynamic contract schema is unproved",
            "proof": {
                "disc_player_stride": "0x54",
                "disc_roster_contract_fields_promoted": False,
                "dashboard_save_container_mapped": False,
                "disc_offsets_are_franchise_save_offsets": False,
            },
            "likely_mutation_layer": [
                "franchise save/runtime objects", "Xbox default.xbe negotiation/progression code"
            ],
            "archive_only_fix": False,
            "current_writer_safe": False,
            "feasibility": "requires save-schema recovery before tuning",
            "blockers": [
                "salary, years, bonus/penalty, expiration, and cap-hit fields are not proved",
                "save integrity and load precedence are unmapped",
                "CPU negotiation and re-signing consumers are not owned",
                "Xbox proof does not identify PS2 ELF addresses",
            ],
            "smallest_safe_next": (
                "Obtain same-season before/after saves for a single known contract edit and "
                "a next-season save, then prove field encoding and integrity without writing."
            ),
        },
        {
            "id": "future_super_bowl_stadium_assignment",
            "user_limitation": "Super Bowl stadium assignment five years in the future",
            "current_proof": "exact year-indexed stadium selector and five-year root cause",
            "proof": {
                "super_bowl_classifier": "0x00133A30..0x00133A4C",
                "classifier_condition": "franchise phase/mode 9 and week 0x14",
                "venue_selector": venue["selector"],
                "season_index_mapping": venue["season_index_mapping"],
                "default_mapping": venue["default_mapping"],
                "venue_rotation_table_proved": True,
                "year_to_venue_mapping_proved": True,
                "all_season_indices_at_or_above_5_collapse_to_s45": True,
                "five_year_failure_reproduced_in_this_workspace": False,
            },
            "likely_mutation_layer": [
                "Xbox default.xbe schedule/venue selection", "franchise save schedule state"
            ],
            "archive_only_fix": False,
            "current_writer_safe": False,
            "feasibility": "exact executable fix target; runtime patch not performed",
            "blockers": [
                "the desired future venue sequence or rotation policy is not specified",
                "no year 5/6 controlled runtime reproduction validates the static root cause",
                "an XBE code/data change still crosses section-digest and signed-header integrity",
                "Xbox proof does not identify PS2 ELF addresses",
            ],
            "smallest_safe_next": (
                "Choose the intended post-index-4 venue policy, patch only an authorized "
                "copied-XBE/emulator lane, and verify year 5/6 venue selection plus changed bytes."
            ),
        },
    ]


def generate() -> dict[str, Any]:
    sources = load_sources()
    rows = parse_ledger(sources["function_ledger"])
    validate_function_rows(rows)
    pseudo = validate_pseudo(sources)
    joined = validate_joined_reports(sources)
    xbe = sources["xbox_xbe"]
    venue = validate_super_bowl_venue_selector(xbe, joined["stadium_metadata"])
    trade = validate_trade_logic(xbe, sources["pseudo_cap_validator"])
    matrix = make_matrix(joined, venue, trade)
    return {
        "schema": SCHEMA,
        "scope": {
            "operation": "read-only evidence join and feasibility classification",
            "game_binary_modified": False,
            "save_modified": False,
            "patch_recipe_emitted": False,
            "emulator_launched": False,
            "arbitrary_offsets_used": False,
        },
        "platform_boundary": {
            "canonical_binary": "retail original-Xbox default.xbe",
            "canonical_binary_sha256": sha256(xbe),
            "pcsx2_ps2_executable_is_a_canonical_input": False,
            "xbox_virtual_addresses_transfer_to_ps2": False,
            "conclusion": (
                "The Xbox results prove subsystem ownership and likely mutation layers, "
                "not reusable PCSX2/PS2 patch offsets. A PS2 ELF and controlled PS2 saves "
                "are required for a PCSX2-targeted implementation."
            ),
        },
        "inputs": {
            label: {
                "path": path.relative_to(ROOT).as_posix(),
                "size": size,
                "sha256": digest,
            }
            for label, (path, size, digest) in SOURCES.items()
        },
        "static_proof_anchors": {
            **pseudo,
            "cpu_trade_evaluation": trade,
            "super_bowl_venue_selector": venue,
        },
        "matrix": matrix,
        "summary": {
            "row_count": len(matrix),
            "archive_only_fix_count": sum(bool(row["archive_only_fix"]) for row in matrix),
            "current_safe_writer_count": sum(bool(row["current_writer_safe"]) for row in matrix),
            "exact_static_footholds": [
                "CPU fantasy-draft priority", "CPU trade acceptance/valuation path",
                "salary-cap season-entry gate",
                "Super Bowl year-to-stadium selector and five-year root cause",
            ],
            "unowned_targets": [
                "CPU-generated trade offer builder",
                "dynamic contract save schema and financial progression model",
            ],
            "answer": (
                "All five subproblems are plausible executable/save-system fixes, but none "
                "is currently a safe public writer. Draft priority, trade acceptance, and "
                "the Super Bowl five-year collapse now have exact XBE owners; salary-cap "
                "enforcement has a strong code foothold; contract serialization and the "
                "CPU offer generator still need controlled save/runtime ownership."
            ),
        },
    }


def matrix_tsv(report: dict[str, Any]) -> str:
    fields = (
        "id", "user_limitation", "current_proof", "likely_mutation_layer",
        "archive_only_fix", "current_writer_safe", "feasibility", "blockers",
        "smallest_safe_next",
    )
    lines = ["\t".join(fields)]
    for row in report["matrix"]:
        values: list[str] = []
        for field in fields:
            value = row[field]
            if isinstance(value, list):
                value = " | ".join(str(item) for item in value)
            elif isinstance(value, bool):
                value = str(value).lower()
            values.append(str(value).replace("\t", " ").replace("\n", " "))
        lines.append("\t".join(values))
    return "\n".join(lines) + "\n"


def write_output(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    require(path.parent.resolve() == path.parent.absolute(),
            f"output parent must not traverse symlinks: {path.parent}")
    if path.exists() or path.is_symlink():
        supplied = path.lstat()
        require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
                f"output must be a non-symlink regular file: {path}")
        for source_path, _, _ in SOURCES.values():
            require(not os.path.samefile(path, source_path),
                    f"output aliases a pinned input: {path}")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0),
        0o644,
    )
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode), f"output is not regular: {path}")
        view = memoryview(payload)
        while view:
            count = os.write(descriptor, view)
            require(count > 0, f"short write to {path}")
            view = view[count:]
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json-out", type=Path,
        default=ROOT / "reports/gameplay_tuning/nfl_franchise_limit_feasibility.json",
    )
    parser.add_argument(
        "--tsv-out", type=Path,
        default=ROOT / "reports/gameplay_tuning/nfl_franchise_limit_feasibility.tsv",
    )
    args = parser.parse_args()
    try:
        report = generate()
        write_output(args.json_out, canonical_json(report))
        write_output(args.tsv_out, matrix_tsv(report).encode("utf-8"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(f"NFL_FRANCHISE_LIMIT_FEASIBILITY_FAIL: {exc}") from exc
    print(
        "NFL_FRANCHISE_LIMIT_FEASIBILITY_PASS "
        f"rows={len(report['matrix'])} archive_writers=0 safe_writers=0 "
        "platform=xbox pcsx2_offsets=false originals_unchanged=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
