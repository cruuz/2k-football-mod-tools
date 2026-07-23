#!/usr/bin/env python3
"""Build a deterministic, evidence-bounded APF franchise-mod feasibility report.

This tool does not patch or execute the game.  It joins previously validated
static-analysis, archive-writer, and external-patch experiment reports so the
public editor can distinguish ordinary asset edits from experimental mode
routing and work that still requires code reconstruction.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_VOLUME_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 << 20):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    ownership = read_json(args.ownership)
    experiment = read_json(args.experiment)
    texture = read_json(args.texture_roundtrip)

    source = ownership["source"]
    require(source["xex_sha256"] == EXPECTED_XEX_SHA256, "ownership XEX hash drift")
    require(
        ownership["scope"]["standalone_franchise_entry_compiled_proved"] is True,
        "standalone franchise entry is no longer proved",
    )
    require(
        ownership["scope"]["standalone_franchise_main_menu_route_proved"] is False,
        "standalone franchise route classification changed",
    )
    require(
        ownership["scope"]["half_finished_franchise_playable_proved"] is False,
        "playable-franchise classification changed",
    )

    entry = ownership["standalone_franchise_entry"]
    season = ownership["retail_season_reuse"]
    require(entry["function"] == "0x849DF2F0", "franchise entry address drift")
    require(entry["incoming_static_audit"]["direct_branches"] == [], "entry gained caller")
    require(entry["incoming_static_audit"]["non_pdata_fullword_sites"] == [], "entry gained pointer")
    require(season["main_row_target_site"] == "0x84E57408", "Season target-site drift")
    require(season["old_gameplan_target_site"] == "0x84E55F10", "Gameplan site drift")

    static_patch = experiment["static_precondition"]
    runtime = experiment["runtime"]
    require(static_patch["guest_word_address"] == "0x84E55F10", "experiment patch-site drift")
    require(static_patch["retail_be32_value"] == "0x820E0B80", "retail descriptor drift")
    require(static_patch["experimental_be32_value"] == "0x820E0BC8", "patched descriptor drift")
    require(runtime["patch_apply_log_seen"] is True, "external patch application no longer proved")
    require(runtime["patch_boot_safe"] is True, "external patch boot classification changed")
    require(experiment["outcome"]["pointer_effect_proved"] is False, "destination classification changed")

    texture_source = texture["source"]
    require(texture_source["volume_sha256"] == EXPECTED_VOLUME_SHA256, "texture source hash drift")
    require(texture["scope"]["outer_entry_index"] == 810, "franchise archive index drift")
    require(texture["scope"]["inner_file_index"] == 117, "draft-logo index drift")
    require(texture["scope"]["inner_name"] == "draft_logo", "draft-logo name drift")

    initializer_calls = [
        {"address": "0x8467D6B8", "role": "query retained franchise handle", "status": "unnamed"},
        {"address": "0x849DEA08", "role": "create retained franchise handle", "status": "unnamed"},
        {"address": "0x84B3E938", "role": "initialize secondary global handle", "status": "unnamed"},
        {"address": "0x8467DB20", "role": "reset subsystem with argument zero", "status": "unnamed"},
        {"address": "0x8467F708", "role": "initialize retained subsystem", "status": "unnamed"},
        {"address": "0x849E8B68", "role": "initialize franchise core component", "status": "unnamed"},
        {"address": "0x849EDC20", "role": "initialize franchise core component", "status": "unnamed"},
        {"address": "0x849DE350", "role": "initialize franchise state with argument zero", "status": "unnamed"},
        {"address": "0x849F9398", "role": "initialize retained subsystem", "status": "unnamed"},
        {"address": "0x8467D658", "role": "conditional 24-slot cleanup", "status": "unnamed"},
        {"address": "0x849DF100", "role": "conditional 24-slot reset", "status": "unnamed"},
        {"address": "0x849ED658", "role": "post-reset franchise initialization", "status": "unnamed"},
        {"address": "0x849E23D0", "role": "final franchise initialization before state push", "status": "unnamed"},
        {"address": "0x846F8A60", "role": "push Coach's Desk state", "status": "exact"},
    ]
    initializer_globals = [
        {"address": "0x851D1910", "role": "retained franchise handle", "precondition": "unknown"},
        {"address": "0x851D1914", "role": "secondary retained handle", "precondition": "unknown"},
        {"address": "0x84F3FB04", "role": "conditional reset flag", "precondition": "unknown"},
        {"address": "0x851D1B3C", "role": "value divided by four during reset", "precondition": "unknown"},
        {"address": "0x84F3FB28", "role": "Coach's Desk versus Simple Coach's Desk selector", "precondition": "unknown"},
    ]

    layers = [
        {
            "id": "retained_asset_retheme",
            "classification": "offline-writer-proved",
            "mod_without_decomp": True,
            "public_gui": "eligible-bounded-targets-only",
            "result": "A copy-only PNG writer is proved for franchise.iff/draft_logo; archive correctness is proved, but the dormant screen is not runtime-reachable yet.",
        },
        {
            "id": "retail_season_reuse",
            "classification": "read-only-mapped",
            "mod_without_decomp": True,
            "public_gui": "viewer-only",
            "result": "Retail Season is a live APF mode and statically routes Coach's Gameplan to an old FranchiseMenu state.",
        },
        {
            "id": "descriptor_redirect_experiment",
            "classification": "unsafe/deferred",
            "mod_without_decomp": "experimental-emulator-patch",
            "public_gui": "disabled",
            "result": "A one-word external Xenia patch applied and booted, but onboarding prevented dispatch; destination, initialization safety, and playability remain unproved.",
        },
        {
            "id": "standalone_franchise_entry",
            "classification": "read-only-mapped",
            "mod_without_decomp": False,
            "public_gui": "viewer-only",
            "result": "The exact initializer and two Coach's Desk targets are compiled, but the entry is statically orphaned and its global/save preconditions are unknown.",
        },
        {
            "id": "full_franchise_loop",
            "classification": "unsafe/deferred",
            "mod_without_decomp": False,
            "public_gui": "disabled",
            "result": "Week progression, simulation, offseason, draft, contracts, roster mutation, and save/load have not been closed into a playable loop.",
        },
        {
            "id": "nfl2k5_franchise_port",
            "classification": "unsafe/deferred",
            "mod_without_decomp": False,
            "public_gui": "disabled",
            "result": "Original-Xbox x86 code cannot be copied into Xenon PowerPC. APF's evolved retained code/assets reduce archaeology work but do not remove ABI, state, database, and save-format reconstruction.",
        },
    ]

    patch_surfaces = [
        {
            "address": "0x84E55F10",
            "retail_be32": "0x820E0B80",
            "experimental_be32": "0x820E0BC8",
            "meaning": "Season Coach's Gameplan target: old CoachGameplan -> old Coach's Desk",
            "delivery": "external Xenia PatchDB word; retail default.xex unchanged",
            "status": "patch-applied-and-boot-safe; destination-not-dispatched",
            "ship_enabled": False,
        },
        {
            "address": "0x84E57408",
            "retail_be32": "0x820F4308",
            "experimental_be32": None,
            "meaning": "Main Menu Season-row target descriptor",
            "delivery": None,
            "status": "mapped-only; direct replacement would bypass unproved franchise initialization",
            "ship_enabled": False,
        },
        {
            "address": "0x849DF2F0",
            "retail_be32": None,
            "experimental_be32": None,
            "meaning": "standalone franchise initializer",
            "delivery": None,
            "status": "compiled/orphaned; no safe call-hook recipe",
            "ship_enabled": False,
        },
    ]

    portme = [
        {"address": "0x84E55F10", "text": "complete identical control/patched navigation and classify Coach's Desk as menu, no-op, or crash"},
        {"address": "0x849DF2F0", "text": "recover a real owner or a calling convention-correct, reversible route that invokes the complete initializer"},
        {"address": "0x84F3FB04/0x84F3FB28/0x851D1910", "text": "name and validate every initializer global and new/load-franchise precondition"},
        {"address": "0x84A1FD00/0x84E44508", "text": "prove franchise.iff load ordering before any old state consumes layouts, markers, scenes, strings, or audio"},
        {"address": "save/profile unknown", "text": "recover APF franchise state serialization, integrity checks, slot ownership, and versioning"},
        {"address": "simulation/offseason unknown", "text": "close a full create/load -> week -> game/sim -> standings -> offseason -> draft -> save loop"},
        {"address": "cross-title database unknown", "text": "map NFL 2K5 schedules, contracts, draft classes, salary cap, and player/team identities to APF structures rather than copying x86 code"},
    ]

    return {
        "schema": "vc_apf_franchise_mod_feasibility/v1",
        "classification": {
            "short_answer": "Asset retheming is already possible for bounded targets; restoring or porting a playable franchise is not yet an ordinary mod and requires executable/state reconstruction.",
            "asset_mod_possible_without_decomp": True,
            "mode_route_experiment_possible_without_native_port": True,
            "standalone_franchise_playable_proved": False,
            "nfl2k5_franchise_direct_copy_possible": False,
            "native_linux_port_required_for_asset_modding": False,
            "decomp_or_equivalent_code_reconstruction_required_for_full_mode_port": True,
        },
        "scope": {
            "launches_game": False,
            "modifies_default_xex": False,
            "modifies_retail_volume": False,
            "produces_enabled_executable_patch": False,
            "uses_existing_validated_runtime_experiment": True,
        },
        "source": {
            "xex_sha256": EXPECTED_XEX_SHA256,
            "volume_0a_sha256": EXPECTED_VOLUME_SHA256,
            "ownership_report": str(args.ownership),
            "ownership_report_sha256": sha256(args.ownership),
            "experiment_report": str(args.experiment),
            "experiment_report_sha256": sha256(args.experiment),
            "texture_roundtrip_report": str(args.texture_roundtrip),
            "texture_roundtrip_report_sha256": sha256(args.texture_roundtrip),
        },
        "proved_inventory": {
            "old_franchise_state_count": len(ownership["old_franchise_states"]),
            "franchise_inner_resource_count": next(
                row["inner_file_count"]
                for row in ownership["archive_inventory"]
                if row["archive"] == "franchise.iff"
            ),
            "franchise_archive_request_call": "0x84A1FD6C",
            "retail_season_main_target_site": "0x84E57408",
            "retail_season_old_gameplan_target_site": "0x84E55F10",
            "standalone_initializer": "0x849DF2F0",
            "mode_selector_global": "0x84F3FB28",
        },
        "initializer_calls": initializer_calls,
        "initializer_globals": initializer_globals,
        "layers": layers,
        "patch_surfaces": patch_surfaces,
        "portme": portme,
    }


def write_tsv(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["kind", "id_or_address", "classification", "public_gui", "result"])
        for row in report["layers"]:
            writer.writerow(["layer", row["id"], row["classification"], row["public_gui"], row["result"]])
        for row in report["patch_surfaces"]:
            writer.writerow(["patch_surface", row["address"], row["status"], "enabled" if row["ship_enabled"] else "disabled", row["meaning"]])
        for row in report["portme"]:
            writer.writerow(["portme", row["address"], "blocking", "disabled", row["text"]])


def write_portme(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "/* Generated APF franchise-mod blockers; no executable patch is emitted. */",
        "#include <stdint.h>",
        "",
    ]
    for index, row in enumerate(report["portme"]):
        lines.extend(
            [
                f"void vc_apf_franchise_mod_portme_{index}(uintptr_t runtime) {{",
                "    (void)runtime;",
                f"    // PORTME: {row['address']}: {row['text']}",
                "}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ownership", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--texture-roundtrip", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--tsv-out", type=Path, required=True)
    parser.add_argument("--portme-c-out", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(args)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(args.tsv_out, report)
    write_portme(args.portme_c_out, report)
    print(
        "APF_FRANCHISE_MOD_FEASIBILITY_GENERATED "
        f"layers={len(report['layers'])} "
        f"patch_surfaces={len(report['patch_surfaces'])} "
        f"portme={len(report['portme'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
