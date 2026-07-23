#!/usr/bin/env python3
"""Build a strict NFL 2K5 team-identity and asset-selector ownership map.

This tool is deliberately read-only.  It joins the already proved ROST,
uniform, Team Select-card, and created-team field-art inventories, then reads
the fixed team-color lookup table directly from the pinned retail XBE.  It
does not infer save-container offsets and does not expose a roster writer.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from xbe_info import Xbe, XbeError


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "nfl2k5_team_identity_audit/v1"
EXPECTED_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
EXPECTED_PACK0_SHA256 = (
    "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
)
EXPECTED_ROSTER_BODY_SHA256 = (
    "b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae"
)

COLOR_TABLE_FIRST = 0x004E7FE0
COLOR_TABLE_AFTER = 0x004E88A0
COLOR_TABLE_STRIDE = 0x1C

DEFAULT_XBE = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
DEFAULT_PACK0 = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
DEFAULT_ROSTER = ROOT / "reports/assets/nfl2k5_roster.json"
DEFAULT_UNIFORMS = ROOT / "reports/assets/nfl2k5_uniform_inventory.json"
DEFAULT_CARDS = ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json"
DEFAULT_FIELD_ART = ROOT / "reports/assets/nfl2k5_create_team_field_art_inventory.json"
DEFAULT_JSON = ROOT / "reports/assets/nfl2k5_team_identity_audit.json"
DEFAULT_TEAMS_TSV = ROOT / "reports/assets/nfl2k5_team_identity_teams.tsv"
DEFAULT_CODES_TSV = ROOT / "reports/assets/nfl2k5_team_identity_asset_codes.tsv"


class AuditError(ValueError):
    """Raised when a frozen input or ownership invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, schema: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(value.get("schema") == schema, f"unsupported schema in {path}")
    return value


def argb(value: int) -> str:
    return f"0x{value:08x}"


def parse_color_table(xbe: Xbe) -> list[dict[str, Any]]:
    require(hashlib.sha256(xbe.data).hexdigest() == EXPECTED_XBE_SHA256,
            "retail XBE SHA-256 changed")
    require((COLOR_TABLE_AFTER - COLOR_TABLE_FIRST) % COLOR_TABLE_STRIDE == 0,
            "color-table range is not stride-aligned")
    records: list[dict[str, Any]] = []
    for index, address in enumerate(
        range(COLOR_TABLE_FIRST, COLOR_TABLE_AFTER, COLOR_TABLE_STRIDE)
    ):
        offset = xbe.va_to_offset(address, COLOR_TABLE_STRIDE)
        words = struct.unpack_from("<7I", xbe.data, offset)
        code = xbe.utf16z_va(words[0])
        require(code is not None and len(code) == 2 and code.isdigit(),
                f"invalid color-table code at 0x{address:08x}")
        records.append({
            "index": index,
            "record_virtual_address": f"0x{address:08X}",
            "record_xbe_file_offset": offset,
            "asset_code": code,
            "asset_code_string_virtual_address": f"0x{words[0]:08X}",
            "scale_float": struct.unpack("<f", struct.pack("<I", words[1]))[0],
            "primary_color_candidate_argb": argb(words[2]),
            "secondary_color_candidate_argb": argb(words[3]),
            "flags_word_10": f"0x{words[4]:08x}",
            "color_candidate_14_argb": argb(words[5]),
            "color_candidate_18_argb": argb(words[6]),
            "primary_value_xbe_file_offset": offset + 0x08,
            "secondary_value_xbe_file_offset": offset + 0x0C,
        })
    require(len(records) == 80, "expected 80 compiled color records")
    require(len({record["asset_code"] for record in records}) == len(records),
            "compiled color codes are not unique")
    return records


def team_classification(index: int) -> str:
    if 0 <= index <= 31:
        return "stock_nfl"
    if 32 <= index <= 33:
        return "empty_user_slot_seed"
    if 34 <= index <= 42:
        return "fictional_or_crib"
    if 43 <= index <= 48:
        return "regional_alumni"
    if 49 <= index <= 50:
        return "conference_aggregate"
    if index == 51:
        return "league_aggregate"
    raise AuditError(f"unexpected main-roster team index {index}")


def relative_target(body: bytes, field: int, label: str) -> int | None:
    require(0 <= field <= len(body) - 4, f"{label} pointer field is outside ROST")
    value = struct.unpack_from("<i", body, field)[0]
    if value == 0:
        return None
    target = field + value - 1
    require(0 <= target < len(body), f"{label} pointer target is outside ROST")
    return target


def known_string_pointer_references(
    resource: dict[str, Any], body: bytes
) -> Counter[int]:
    """Count every pointer in the parser's proved UTF-16 field domains.

    The canonical JSON intentionally omits target offsets for team-label and
    generated-name pairs, so merely walking ``*_offset`` keys would miss those
    references.  Re-resolve all proved text-pointer fields from the pinned raw
    body before declaring a replacement target unshared.
    """
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


def build_team_rows(resource: dict[str, Any], body: bytes) -> list[dict[str, Any]]:
    require(resource["outer_index"] == 5 and resource["label"] == "roster",
            "main ROST resource identity changed")
    require(resource["body_sha256"] == EXPECTED_ROSTER_BODY_SHA256,
            "main ROST body hash changed")
    require(len(resource["teams"]) == 52, "main ROST team count changed")
    require(hashlib.sha256(body).hexdigest() == EXPECTED_ROSTER_BODY_SHA256,
            "raw main ROST body hash changed")
    references = known_string_pointer_references(resource, body)
    stadiums = resource["stadiums"]
    rows: list[dict[str, Any]] = []
    for team in resource["teams"]:
        index = int(team["index"])
        stadium_index = team["stadium_index"]
        stadium = stadiums[stadium_index] if stadium_index is not None else None
        field_offsets = {
            "nickname": 0x104,
            "abbreviation": 0x108,
            "asset_code": 0x10C,
            "city": 0x138,
            "city_abbreviation": 0x13C,
        }
        fields: dict[str, Any] = {}
        for name, record_field in field_offsets.items():
            target = int(team[f"{name}_offset"])
            value = str(team[name])
            fields[name] = {
                "value": value,
                "record_pointer_field_offset": record_field,
                "body_string_offset": target,
                "utf16le_size_including_terminator": (len(value) + 1) * 2,
                "known_decoded_pointer_reference_count": references[target],
            }
        rows.append({
            "team_index": index,
            "team_record_body_offset": int(team["offset"]),
            "classification": team_classification(index),
            "team_kind_code": int(team["team_kind_code"]),
            "nickname": team["nickname"],
            "abbreviation": team["abbreviation"],
            "asset_code": team["asset_code"],
            "city": team["city"],
            "city_abbreviation": team["city_abbreviation"],
            "roster_size": int(team["roster_size"]),
            "stadium_index": stadium_index,
            "stadium_name": stadium["name"] if stadium else None,
            "stadium_asset_code": stadium["asset_code"] if stadium else None,
            "stadium_field_art_code": stadium["secondary_label"] if stadium else None,
            "fields": fields,
        })
    require([row["classification"] for row in rows].count("stock_nfl") == 32,
            "stock-team classification changed")
    require([row["classification"] for row in rows].count("empty_user_slot_seed") == 2,
            "user-slot classification changed")
    return rows


def group_cards(cards: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "resource_count": 0, "selector_keys": set(), "styles": set(),
        "side_contexts": set(), "families": set(),
    })
    for target in cards["targets"]:
        item = grouped[str(target["asset_code"])]
        item["resource_count"] += 1
        item["selector_keys"].add(
            (target["asset_code"], target["side_code"], int(target["style"]))
        )
        item["styles"].add(int(target["style"]))
        item["side_contexts"].add(str(target["side_context"]))
        item["families"].add(f"{target['family']}_{target['width']}")
    return {
        code: {
            "resource_count": item["resource_count"],
            "selector_key_count": len(item["selector_keys"]),
            "styles": sorted(item["styles"]),
            "side_contexts": sorted(item["side_contexts"]),
            "families": sorted(item["families"]),
        }
        for code, item in grouped.items()
    }


def build_asset_rows(
    team_rows: list[dict[str, Any]],
    resource: dict[str, Any],
    uniforms: dict[str, Any],
    cards: dict[str, Any],
    field_art: dict[str, Any],
    colors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    card_map = group_cards(cards)
    color_map = {record["asset_code"]: record for record in colors}
    field_codes = {f"{int(value):02d}" for value in field_art["selector_space"]["logo_codes"]}
    package_counts = Counter(
        f"{int(package['logo_code']):02d}" for package in field_art["packages"]
    )
    stadium_refs: dict[str, list[int]] = defaultdict(list)
    for stadium in resource["stadiums"]:
        code = str(stadium["secondary_label"])
        if code:
            stadium_refs[code].append(int(stadium["index"]))
    team_refs: dict[str, list[int]] = defaultdict(list)
    for team in team_rows:
        team_refs[str(team["asset_code"])].append(int(team["team_index"]))

    rows: list[dict[str, Any]] = []
    for uniform in uniforms["asset_codes"]:
        code = str(uniform["asset_code"])
        require(code in card_map, f"asset code {code} lacks Team Select cards")
        color = color_map.get(code)
        rows.append({
            "asset_code": code,
            "main_roster_team_indices": team_refs.get(code, []),
            "main_roster_team_names": [
                f"{team_rows[index]['city']} {team_rows[index]['nickname']}"
                for index in team_refs.get(code, [])
            ],
            "uniform_pair_count": int(uniform["pair_count"]),
            "uniform_variant_ids": [
                int(value) for value in str(uniform["variant_ids"]).split(";") if value
            ],
            "team_select_card_resource_count": card_map[code]["resource_count"],
            "team_select_selector_key_count": card_map[code]["selector_key_count"],
            "team_select_styles": card_map[code]["styles"],
            "created_team_field_art_package_count": int(package_counts[code]),
            "created_team_field_art_weather_variants": (
                ["D", "R", "S"] if code in field_codes else []
            ),
            "retail_stadium_secondary_label_indices": stadium_refs.get(code, []),
            "compiled_color_record_present": color is not None,
            "compiled_primary_color_candidate_argb": (
                color["primary_color_candidate_argb"] if color else None
            ),
            "compiled_secondary_color_candidate_argb": (
                color["secondary_color_candidate_argb"] if color else None
            ),
            "compiled_color_record_virtual_address": (
                color["record_virtual_address"] if color else None
            ),
            "compiled_color_fallback": (
                None if color else {
                    "primary_accessor_0x00068D70": "0xff0065e6",
                    "secondary_accessor_0x00068DC0": "0xff00a0ff",
                }
            ),
        })
    require(len(rows) == 85, "uniform asset-code count changed")
    require(sum(row["compiled_color_record_present"] for row in rows) == 80,
            "compiled-color join count changed")
    require(
        [row["asset_code"] for row in rows if not row["compiled_color_record_present"]]
        == ["95", "96", "97", "98", "99"],
        "compiled-color omissions changed",
    )
    require(sum(row["created_team_field_art_package_count"] for row in rows) == 126,
            "created-team field-art package join changed")
    return rows


def write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    roster = load_json(args.roster, "nfl2k5_roster_inventory/v1")
    uniforms = load_json(args.uniforms, "nfl2k5_uniform_inventory/v1")
    cards = load_json(args.cards, "nfl2k5_team_select_card_inventory/v1")
    field_art = load_json(args.field_art, "nfl2k5_create_team_field_art_inventory/v1")
    pack_hash = sha256_file(args.pack0)
    require(pack_hash == EXPECTED_PACK0_SHA256, "extracted retail pack 0 hash changed")
    xbe = Xbe(args.xbe)
    colors = parse_color_table(xbe)
    main = next(
        (resource for resource in roster["resources"] if resource["outer_index"] == 5),
        None,
    )
    require(main is not None, "main ROST resource is missing")
    with args.pack0.open("rb") as stream:
        stream.seek(0x00392800)
        wrapper = stream.read(0x20)
        require(len(wrapper) == 0x20 and wrapper[:4] == b"ROST",
                "main ROST wrapper changed")
        stored_size = struct.unpack_from("<I", wrapper, 4)[0]
        require(stored_size == 593_760, "main ROST body size changed")
        main_body = stream.read(stored_size)
        require(len(main_body) == stored_size, "short main ROST body read")
    teams = build_team_rows(main, main_body)
    assets = build_asset_rows(teams, main, uniforms, cards, field_art, colors)

    field_codes = {row["asset_code"] for row in assets
                   if row["created_team_field_art_package_count"]}
    stadium_codes = {str(stadium["secondary_label"]) for stadium in main["stadiums"]
                     if stadium["secondary_label"]}
    package_only_codes = sorted(field_codes - stadium_codes)
    require(package_only_codes == ["33", "50", "72"],
            "field-art package-only code set changed")

    return {
        "schema": SCHEMA,
        "sources": {
            "xbe": {"path": str(args.xbe), "sha256": EXPECTED_XBE_SHA256},
            "pack0": {"path": str(args.pack0), "sha256": pack_hash},
            "roster_report": str(args.roster),
            "uniform_report": str(args.uniforms),
            "team_select_card_report": str(args.cards),
            "created_team_field_art_report": str(args.field_art),
        },
        "summary": {
            "main_team_count": len(teams),
            "stock_nfl_team_count": 32,
            "empty_user_slot_seed_count": 2,
            "uniform_and_team_select_asset_code_count": len(assets),
            "compiled_color_record_count": len(colors),
            "created_team_field_art_code_count": len(field_codes),
            "created_team_field_art_package_count": sum(
                row["created_team_field_art_package_count"] for row in assets
            ),
            "retail_stadium_field_art_label_count": len(stadium_codes),
            "field_art_codes_without_retail_stadium_secondary_label": package_only_codes,
        },
        "team_record_layout": {
            "stride": "0x1f4",
            "player_pointer_slots": {"offset": "0x000", "count": 65},
            "nickname_pointer": "0x104",
            "abbreviation_pointer": "0x108",
            "uniform_team_select_asset_code_pointer": "0x10c",
            "team_label_pair_pointer": "0x110",
            "stadium_pointer": "0x114",
            "roster_count_byte": "0x11c",
            "team_kind_word": "0x128",
            "city_pointer": "0x138",
            "city_abbreviation_pointer": "0x13c",
            "related_team_pointers": ["0x140", "0x144", "0x148"],
            "coach_pointer": "0x14c",
            "serialized_pointer_formula": "field_offset + signed_stored_value - 1",
        },
        "runtime_ownership": {
            "team_select_card_formatter": {
                "function": "0x0031F1D0",
                "asset_code_source": "team +0x10c",
                "formats": ["helm_%s%s_%1d", "unif_%s%s_%1d"],
            },
            "uniform_package_formatter": {
                "function": "0x000615A0",
                "asset_code_source": "team +0x10c",
                "format": "%s%c%d.iff",
            },
            "team_colors": {
                "table_range": "0x004E7FE0..0x004E889F",
                "stride": "0x1c",
                "primary_candidate_accessor": "0x00068D70 returns record +0x08",
                "secondary_candidate_accessor": "0x00068DC0 returns record +0x0c",
                "lookup_key": "team +0x10c, case-insensitive UTF-16",
                "storage": "signed retail XBE .rdata, not the ROST body",
            },
            "created_team_field_art": {
                "function": "0x00062BE0",
                "filename_format": "ct%s%c.iff",
                "logo_code_source": "active stadium record +0x14 secondary_label",
                "weather_suffixes": {"d": "dry", "r": "rain", "s": "snow"},
                "note": "This field selector is distinct from team +0x10c; the two empty user-slot seeds already demonstrate that the values need not match.",
            },
            "create_or_edit_team_text": {
                "active_team_global": "0x00C8F7EC",
                "city_editor": {"function": "0x003193F0", "field": "+0x138", "maximum_characters": 12},
                "team_name_editor": {"function": "0x00319480", "field": "+0x104", "maximum_characters": 15},
                "short_name_editor": {"function": "0x00319510", "field": "+0x108", "maximum_characters": 3},
                "state_driver": "0x0031A8A0",
            },
            "roster_serialization": {
                "forward_relocator": "0x000C0500",
                "inverse_relocator": "0x000C0730",
                "import_merge_copy": "0x000C1030",
                "writer_build_path": "0x002D17B0",
            },
        },
        "storage_boundary": [
            {
                "value_family": "retail/historic team text, memberships, stadium and coach links",
                "proved_storage": "disc ROST resources in vc_53450030/0",
                "write_status": "fixed-size same-length string replacement can preserve every pointer and allocation; general writer remains disabled",
            },
            {
                "value_family": "two empty user-team seeds",
                "proved_storage": "disc main ROST teams 32 and 33",
                "write_status": "runtime UI edits the same in-memory team fields; exact dashboard/save-container offsets have not been sampled",
            },
            {
                "value_family": "created-team persisted identity and roster",
                "proved_storage": "ROST serializer/writer path exists and user-team UI mutates ROST-shaped records",
                "write_status": "save/profile ownership is expected but exact save filename, wrapper, checksum, and offsets remain PORTME",
            },
            {
                "value_family": "team primary/secondary color candidates",
                "proved_storage": "80 fixed records in default.xbe .rdata",
                "write_status": "not patched: changing the XBE invalidates its signed section digest chain unless an emulator-specific unsigned workflow is separately proved",
            },
            {
                "value_family": "uniforms and Team Select cards",
                "proved_storage": "85 two-digit asset-code families in disc packs",
                "write_status": "existing fixed-span PNG/package workflows cover the art; this audit does not duplicate them",
            },
            {
                "value_family": "created-team live field branding",
                "proved_storage": "42 ct{code}{D,R,S}.iff disc families",
                "write_status": "existing fixed-span PNG workflow covers the art; code count remains fixed",
            },
        ],
        "safe_fixed_size_proof": {
            "target": "main ROST team 18 / Detroit",
            "changes": {
                "city": {"before": "Detroit", "after": "Codexia"},
                "nickname": {"before": "Lions", "after": "Codex"},
                "abbreviation": {"before": "DET", "after": "CDX"},
                "city_abbreviation": {"before": "DET", "after": "CDX"},
            },
            "unchanged": {
                "asset_code": "09",
                "roster_size": 53,
                "stadium_index": 9,
                "team_record_pointer_fields": True,
            },
            "scope": "copy-only XISO proof; no runtime visibility claim",
        },
        "claims": {
            "team_identity_disc_schema_proved": True,
            "uniform_and_team_select_join_proved": True,
            "compiled_color_table_proved": True,
            "created_team_field_join_proved": True,
            "general_roster_writer_emitted": False,
            "new_team_added": False,
            "save_container_schema_proved": False,
            "runtime_visibility_proved_by_this_audit": False,
            "originals_modified": False,
        },
        "portmes": [
            "PORTME(save): capture one clean Xbox roster/profile save before and after creating a team; identify its wrapper, checksum, and ROST payload instead of projecting disc offsets onto it.",
            "PORTME(colors): identify the exact authoring names of XBE color-table fields +0x08/+0x0c/+0x14/+0x18; primary/secondary are conservative candidates from the accessors and consumers.",
            "PORTME(xbe): prove an emulator-safe unsigned/rehashed XBE workflow before exposing compiled color-table writes.",
            "PORTME(field-art): determine whether package-only field codes 33, 50, and 72 can be materialized dynamically; no retail stadium +0x14 points to them.",
            "PORTME(capacity): adding teams requires relocating the ROST team table, updating root counts/pointers, schedule/playbook/menu consumers, and every fixed team-count loop; no add-team tool is emitted.",
            "PORTME(runtime): capture the copied identity proof in Team Select and gameplay overlays before claiming on-screen visibility.",
        ],
        "teams": teams,
        "asset_codes": assets,
        "compiled_color_records": colors,
    }


def emit_outputs(report: dict[str, Any], args: argparse.Namespace) -> None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    team_rows = []
    for team in report["teams"]:
        team_rows.append({
            "team_index": team["team_index"],
            "classification": team["classification"],
            "team_kind_code": team["team_kind_code"],
            "city": team["city"],
            "nickname": team["nickname"],
            "abbreviation": team["abbreviation"],
            "city_abbreviation": team["city_abbreviation"],
            "asset_code": team["asset_code"],
            "roster_size": team["roster_size"],
            "stadium_index": team["stadium_index"],
            "stadium_name": team["stadium_name"],
            "stadium_asset_code": team["stadium_asset_code"],
            "stadium_field_art_code": team["stadium_field_art_code"],
            "team_record_body_offset": f"0x{team['team_record_body_offset']:x}",
        })
    write_tsv(args.teams_tsv, [
        "team_index", "classification", "team_kind_code", "city", "nickname",
        "abbreviation", "city_abbreviation", "asset_code", "roster_size",
        "stadium_index", "stadium_name", "stadium_asset_code",
        "stadium_field_art_code", "team_record_body_offset",
    ], team_rows)

    asset_rows = []
    for row in report["asset_codes"]:
        asset_rows.append({
            "asset_code": row["asset_code"],
            "main_roster_team_indices": ";".join(map(str, row["main_roster_team_indices"])),
            "main_roster_team_names": ";".join(row["main_roster_team_names"]),
            "uniform_pair_count": row["uniform_pair_count"],
            "uniform_variant_ids": ";".join(map(str, row["uniform_variant_ids"])),
            "team_select_card_resource_count": row["team_select_card_resource_count"],
            "team_select_selector_key_count": row["team_select_selector_key_count"],
            "created_team_field_art_package_count": row["created_team_field_art_package_count"],
            "retail_stadium_secondary_label_indices": ";".join(
                map(str, row["retail_stadium_secondary_label_indices"])
            ),
            "compiled_color_record_present": str(row["compiled_color_record_present"]).lower(),
            "compiled_primary_color_candidate_argb": row["compiled_primary_color_candidate_argb"] or "",
            "compiled_secondary_color_candidate_argb": row["compiled_secondary_color_candidate_argb"] or "",
            "compiled_color_record_virtual_address": row["compiled_color_record_virtual_address"] or "",
        })
    write_tsv(args.codes_tsv, [
        "asset_code", "main_roster_team_indices", "main_roster_team_names",
        "uniform_pair_count", "uniform_variant_ids",
        "team_select_card_resource_count", "team_select_selector_key_count",
        "created_team_field_art_package_count",
        "retail_stadium_secondary_label_indices", "compiled_color_record_present",
        "compiled_primary_color_candidate_argb",
        "compiled_secondary_color_candidate_argb",
        "compiled_color_record_virtual_address",
    ], asset_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, default=DEFAULT_XBE)
    parser.add_argument("--pack0", type=Path, default=DEFAULT_PACK0)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--uniforms", type=Path, default=DEFAULT_UNIFORMS)
    parser.add_argument("--cards", type=Path, default=DEFAULT_CARDS)
    parser.add_argument("--field-art", type=Path, default=DEFAULT_FIELD_ART)
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--teams-tsv", type=Path, default=DEFAULT_TEAMS_TSV)
    parser.add_argument("--codes-tsv", type=Path, default=DEFAULT_CODES_TSV)
    args = parser.parse_args(argv)
    report = build_report(args)
    emit_outputs(report, args)
    print(
        "NFL_TEAM_IDENTITY_AUDIT_OK "
        f"teams={report['summary']['main_team_count']} "
        f"asset_codes={report['summary']['uniform_and_team_select_asset_code_count']} "
        f"colors={report['summary']['compiled_color_record_count']} "
        f"field_codes={report['summary']['created_team_field_art_code_count']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AuditError, XbeError, OSError, json.JSONDecodeError) as exc:
        print(f"nfl_team_identity_audit: {exc}", file=sys.stderr)
        raise SystemExit(1)
