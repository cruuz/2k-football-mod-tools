#!/usr/bin/env python3
"""Prove APF 2K8 uniform selector bank HOME/AWAY ownership.

This is a read-only evidence reducer.  It joins the complete APF Ghidra
function export with the earlier focused selector trace and refuses to emit a
report unless the selector, all 24 generated resource wrappers, and the two
literal HOME/AWAY anchors agree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


EXPECTED_EXECUTABLE_MD5 = "217eea6084c3d03f0f1143802b1f5636"
PSEUDO_SHARD = "pseudo_c/apf2k8_pseudoc_12544_12799.c"
LEDGER_SHARD = "ledger/apf2k8_functions_12288_12799.jsonl"
SELECTOR_ADDRESS = "0x849D6BD0"
HOME_ANCHOR = "0x849DC2C8"
AWAY_ANCHOR = "0x849DC378"


FAMILIES: dict[int, dict[str, Any]] = {
    0x5A37FC45: {
        "family": "glove", "slot": 2, "template_address": "0x845F1BD8",
        "template": "uniform_glove_{0:D2}.iff",
    },
    0x7D06EB90: {
        "family": "helmet", "slot": 3, "template_address": "0x845F1C74",
        "template": "uniform_helmet_{0:D2}.iff",
    },
    0xE80198F0: {
        "family": "jersey", "slot": 4, "template_address": "0x845F1CDC",
        "template": "uniform_jersey_{0:D2}.iff",
    },
    0x44BC352D: {
        "family": "logo", "slot": 5, "template_address": "0x845F1C44",
        "template": "uniform_logo_{0:D2}.iff",
    },
    0xE31B6285: {
        "family": "textlogo", "slot": 6, "template_address": "0x845F1C0C",
        "template": "uniform_textlogo_{0:D2}.iff",
    },
    0x70A6A7EC: {
        "family": "font", "slot": 7, "template_address": "0x845F1B14",
        "template": "uniform_font_{0:D2}.iff",
    },
    0x913C1A62: {
        "family": "number", "slot": 8, "template_address": "0x845F1B44",
        "template": "uniform_number_{0:D2}.iff",
    },
    0xBDBDD2EE: {
        "family": "pants", "slot": 9, "template_address": "0x845F1CA8",
        "template": "uniform_pants_{0:D2}.iff",
    },
    0x61850777: {
        "family": "shoe", "slot": 10, "template_address": "0x845F1BA8",
        "template": "uniform_shoe_{0:D2}.iff",
    },
    0x56ED5F4B: {
        "family": "shoulder", "slot": 11, "template_address": "0x845F1D10",
        "template": "uniform_shoulder_{0:D2}.iff",
    },
    0xB5D10480: {
        "family": "shoulder_normal", "slot": 11,
        "template_address": "0x845F1D48",
        "template": "uniform_shoulder_normal_{0:D2}.iff",
    },
    0x2FC773F9: {
        "family": "sock", "slot": 12, "template_address": "0x845F1B78",
        "template": "uniform_sock_{0:D2}.iff",
    },
}


class EvidenceError(RuntimeError):
    """Raised when an authority no longer supports the bounded proof."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _function_blocks(source: str) -> dict[str, str]:
    pattern = re.compile(
        r"/\* APF2K8_FUNCTION (0x[0-9A-F]+).*?\*/\s*"
        r"(.*?)"
        r"/\* APF2K8_END_FUNCTION \1 \*/",
        re.DOTALL,
    )
    blocks = {match.group(1): match.group(2).strip() for match in pattern.finditer(source)}
    if len(blocks) != 256:
        raise EvidenceError(f"expected 256 pseudo-C function blocks, found {len(blocks)}")
    return blocks


def _ledger(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceError(f"invalid ledger JSON at line {line_number}") from exc
            address = row.get("address")
            if not isinstance(address, str) or address in rows:
                raise EvidenceError(f"invalid or duplicate ledger address at line {line_number}")
            rows[address] = row
    if len(rows) != 512:
        raise EvidenceError(f"expected 512 ledger rows, found {len(rows)}")
    return rows


def _selector_contract(body: str, trace: str) -> dict[str, Any]:
    mode_zero = re.compile(
        r"if \(param_2 == 0\) \{\s*"
        r"iVar1 = FUN_84682798\(\);\s*"
        r"pcVar4 = \(code \*\)&?(?:UNK_)?847080c8;\s*"
        r"\}\s*else \{\s*"
        r"iVar1 = FUN_84682730\(\);\s*"
        r"pcVar4 = FUN_84687d88;",
        re.DOTALL,
    )
    if not mode_zero.search(body):
        raise EvidenceError("selector mode/accessor branch no longer matches")
    if "*(undefined4 *)(iVar1 + 0xbc)" not in body:
        raise EvidenceError("selector no longer loads the team +0xBC config pointer")
    if "pbVar2 = (byte *)(*pcVar4)(*(undefined4 *)(iVar1 + 0xbc),uVar3);" not in body:
        raise EvidenceError("selector no longer dispatches the selected config slot")

    exact_instructions = [
        "0x84687D88 rlwinm r11,r4,0x2,0x0,0x1d",
        "0x84687D8C lwzx r3,r11,r3",
        "0x84687D90 blr",
        "0x847080C8 addi r11,r4,0xe",
        "0x847080CC rlwinm r11,r11,0x2,0x0,0x1d",
        "0x847080D0 lwzx r3,r11,r3",
        "0x847080D4 blr",
    ]
    missing = [instruction for instruction in exact_instructions if instruction not in trace]
    if missing:
        raise EvidenceError(f"focused accessor trace lost {missing[0]}")

    for selector_hash, family in FAMILIES.items():
        token = f"0x{selector_hash:x}"
        location = body.lower().find(token)
        if location < 0:
            raise EvidenceError(f"selector lost {family['family']} hash {token}")
        window = body[location:location + 420]
        assignment = re.search(
            r"uVar3 = (0x[0-9a-f]+|[0-9]+);\s*"
            r"uVar5 = 0xffffffff([0-9a-f]+);",
            window,
            re.IGNORECASE | re.DOTALL,
        )
        if assignment is None:
            raise EvidenceError(f"cannot recover selector assignment for {family['family']}")
        slot = int(assignment.group(1), 0)
        template_address = f"0x{int(assignment.group(2), 16):08X}"
        if slot != family["slot"] or template_address != family["template_address"]:
            raise EvidenceError(f"selector assignment drift for {family['family']}")
        trace_line = (
            f"{family['template_address']} value={family['template']}"
        )
        if trace_line not in trace:
            raise EvidenceError(f"focused trace lost template text for {family['family']}")

    return {
        "address": SELECTOR_ADDRESS,
        "team_uniform_config_field": "+0xBC",
        "mode_1": {
            "active_team_accessor": "0x84682730",
            "bank_accessor": "0x84687D88",
            "bank_index": 0,
            "accessor_equation": "config[slot]",
        },
        "mode_0": {
            "active_team_accessor": "0x84682798",
            "bank_accessor": "0x847080C8",
            "bank_index": 1,
            "accessor_equation": "config[slot + 14]",
        },
    }


def _wrapper_rows(
    blocks: dict[str, str], ledger: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    call_pattern = re.compile(
        r"Function_849D6BD0\((0x(?:ffffffff)?[0-9a-f]+),(0|1)\)",
        re.IGNORECASE,
    )
    rows: list[dict[str, Any]] = []
    for address, body in blocks.items():
        match = call_pattern.search(body)
        if match is None:
            continue
        selector_hash = int(match.group(1), 16) & 0xFFFFFFFF
        mode = int(match.group(2))
        if selector_hash not in FAMILIES:
            raise EvidenceError(f"unknown selector hash in wrapper {address}")
        if address not in ledger:
            raise EvidenceError(f"wrapper {address} is absent from ledger")
        family = FAMILIES[selector_hash]
        class_matches = re.findall(r"0xffffffff(84e[0-9a-f]+)", body, re.IGNORECASE)
        resource_class = None
        if family["family"] != "font":
            if len(class_matches) != 1:
                raise EvidenceError(f"expected one resource class in {address}")
            resource_class = f"0x{int(class_matches[0], 16):08X}"
        direct_strings = ledger[address].get("direct_string_references")
        if not isinstance(direct_strings, list):
            raise EvidenceError(f"wrapper {address} has invalid string ledger")
        rows.append({
            "address": address,
            "family": family["family"],
            "selector_hash": f"0x{selector_hash:08X}",
            "selector_slot": family["slot"],
            "template": family["template"],
            "mode": mode,
            "bank_index": 0 if mode == 1 else 1,
            "resource_class": resource_class,
            "direct_strings": [
                {"address": value["address"], "value": value["value"]}
                for value in direct_strings
            ],
        })
    if len(rows) != 24:
        raise EvidenceError(f"expected 24 selector wrappers, found {len(rows)}")
    return sorted(rows, key=lambda row: (row["selector_slot"], row["family"], -row["mode"]))


def _family_pairs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_family.setdefault(row["family"], []).append(row)
    if set(by_family) != {family["family"] for family in FAMILIES.values()}:
        raise EvidenceError("wrapper family set does not match selector family set")

    home_refs: list[tuple[str, str]] = []
    away_refs: list[tuple[str, str]] = []
    source_path = "c:/work/maincodeline/vcsports/nfl/code/gamedataresource.items"
    for row in rows:
        values = {value["value"] for value in row["direct_strings"]}
        if source_path not in values:
            raise EvidenceError(f"wrapper {row['address']} lost generated-resource source anchor")
        if "HOME" in values:
            home_refs.append((row["address"], row["family"]))
        if "AWAY" in values:
            away_refs.append((row["address"], row["family"]))
    if home_refs != [(HOME_ANCHOR, "shoulder_normal")]:
        raise EvidenceError(f"HOME anchor mismatch: {home_refs}")
    if away_refs != [(AWAY_ANCHOR, "shoulder_normal")]:
        raise EvidenceError(f"AWAY anchor mismatch: {away_refs}")

    pairs: list[dict[str, Any]] = []
    for family_name, family_rows in by_family.items():
        if len(family_rows) != 2 or {row["mode"] for row in family_rows} != {0, 1}:
            raise EvidenceError(f"family {family_name} does not have one wrapper per mode")
        home = next(row for row in family_rows if row["mode"] == 1)
        away = next(row for row in family_rows if row["mode"] == 0)
        if family_name != "font":
            if home["resource_class"] != "0x84E30180":
                raise EvidenceError(f"HOME resource class drift for {family_name}")
            if away["resource_class"] != "0x84E318C0":
                raise EvidenceError(f"AWAY resource class drift for {family_name}")
        pairs.append({
            "family": family_name,
            "selector_hash": home["selector_hash"],
            "selector_slot": home["selector_slot"],
            "template": home["template"],
            "home": {
                "wrapper": home["address"],
                "selector_mode": 1,
                "bank_index": 0,
                "resource_class": home["resource_class"],
            },
            "away": {
                "wrapper": away["address"],
                "selector_mode": 0,
                "bank_index": 1,
                "resource_class": away["resource_class"],
            },
        })
    return sorted(pairs, key=lambda pair: (pair["selector_slot"], pair["family"]))


def build_report(export_root: Path, focused_trace_path: Path) -> dict[str, Any]:
    manifest_path = export_root / "manifest.json"
    pseudo_path = export_root / PSEUDO_SHARD
    ledger_path = export_root / LEDGER_SHARD
    for path in (manifest_path, pseudo_path, ledger_path, focused_trace_path):
        if not path.is_file():
            raise EvidenceError(f"missing authority: {path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("executable_md5") != EXPECTED_EXECUTABLE_MD5:
        raise EvidenceError("unexpected APF executable MD5")
    if manifest.get("complete") is not True or manifest.get("function_count") != 21347:
        raise EvidenceError("APF function export is not the complete pinned inventory")
    if PSEUDO_SHARD not in manifest.get("pseudo_c_files", []):
        raise EvidenceError("pseudo-C authority is absent from export manifest")
    if LEDGER_SHARD not in manifest.get("ledger_files", []):
        raise EvidenceError("ledger authority is absent from export manifest")

    pseudo = pseudo_path.read_text(encoding="utf-8")
    trace = focused_trace_path.read_text(encoding="utf-8")
    if f"Program MD5: {EXPECTED_EXECUTABLE_MD5}" not in trace:
        raise EvidenceError("focused trace executable identity mismatch")
    blocks = _function_blocks(pseudo)
    ledger = _ledger(ledger_path)
    if SELECTOR_ADDRESS not in blocks or SELECTOR_ADDRESS not in ledger:
        raise EvidenceError("selector is absent from one source authority")
    selector = _selector_contract(blocks[SELECTOR_ADDRESS], trace)
    wrappers = _wrapper_rows(blocks, ledger)
    pairs = _family_pairs(wrappers)

    home_row = next(row for row in wrappers if row["address"] == HOME_ANCHOR)
    away_row = next(row for row in wrappers if row["address"] == AWAY_ANCHOR)
    expected_home_ref = {"address": "0x845F21E8", "value": "HOME"}
    expected_away_ref = {"address": "0x845F21F4", "value": "AWAY"}
    if expected_home_ref not in home_row["direct_strings"]:
        raise EvidenceError("HOME literal address mismatch")
    if expected_away_ref not in away_row["direct_strings"]:
        raise EvidenceError("AWAY literal address mismatch")

    return {
        "schema": "apf2k8_uniform_selector_bank_ownership/v1",
        "status": "static_home_away_bank_orientation_closed",
        "source_authority": {
            "executable_md5": EXPECTED_EXECUTABLE_MD5,
            "export_manifest": {
                "path": str(manifest_path.relative_to(export_root.parent.parent.parent)),
                "sha256": sha256(manifest_path),
            },
            "pseudo_c_shard": {
                "path": str(pseudo_path.relative_to(export_root.parent.parent.parent)),
                "sha256": sha256(pseudo_path),
            },
            "ledger_shard": {
                "path": str(ledger_path.relative_to(export_root.parent.parent.parent)),
                "sha256": sha256(ledger_path),
            },
            "focused_trace": {
                "path": str(focused_trace_path),
                "sha256": sha256(focused_trace_path),
            },
        },
        "selector": selector,
        "orientation_anchors": {
            "home": {
                "literal": expected_home_ref,
                "wrapper": HOME_ANCHOR,
                "family": "shoulder_normal",
                "selector_mode": 1,
                "bank_index": 0,
                "resource_class": "0x84E30180",
            },
            "away": {
                "literal": expected_away_ref,
                "wrapper": AWAY_ANCHOR,
                "family": "shoulder_normal",
                "selector_mode": 0,
                "bank_index": 1,
                "resource_class": "0x84E318C0",
            },
        },
        "family_pair_count": len(pairs),
        "wrapper_count": len(wrappers),
        "family_pairs": pairs,
        "claims": {
            "bank_0_is_home": True,
            "bank_1_is_away": True,
            "all_twelve_filename_templates_have_home_and_away_wrappers": True,
            "all_non_font_pairs_share_the_anchored_resource_class_split": True,
            "selector_bytes_1_through_7_semantics_proved": False,
            "logo_selection_preview_consumption_proved": False,
            "gameplay_runtime_consumption_proved": False,
            "arbitrary_selector_writer_authorized": False,
        },
        "limitations": [
            "This is static executable ownership proof; it does not replace a gameplay runtime witness.",
            "The seven opaque bytes after each filename asset index remain unnamed.",
            "The result orients the two existing 14-pointer banks but does not authorize new selector values.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--export-root", type=Path,
        default=Path("research/functions/apf2k8"),
    )
    parser.add_argument(
        "--focused-trace", type=Path,
        default=Path("reports/assets/apf_uniform_ghidra/uniform_trace.txt"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.export_root, args.focused_trace)
    payload = canonical_json(report)
    if args.output is None:
        print(payload.decode("utf-8"), end="")
    else:
        args.output.write_bytes(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
