#!/usr/bin/env python3
"""Verify the redistributable APF all-family selector mod release contract."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import apf_uniform_selector_verify as selector_verify
import apf_uniform_selector_xenia_match as pose_match


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/assets/apf_uniform_selector_mod_release.v1.json"
RETAIL_GAME = ROOT / "extracted/All-Pro Football 2K8 (USA)"
RUNTIME = Path(
    "/media/noah/Storage/.codex-tmp/apf-all-family-selector-runtime-20260716"
)
SCHEMA = "apf_uniform_selector_mod_release/v1"


class ReleaseVerifyError(ValueError):
    """The packaged mod release differs from its fail-closed contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseVerifyError(message)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _unique(label: str):
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result
    return hook


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique(label)
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseVerifyError(f"{label} is invalid JSON") from exc
    require(isinstance(value, dict), f"{label} root is not an object")
    return value


def _validate_hash_record(root: Path, record: dict[str, Any], label: str) -> Path:
    path = root / record["path"]
    require(path.is_file() and not path.is_symlink(), f"{label} is not a regular file")
    require(path.stat().st_size == record["size_bytes"], f"{label} size differs")
    require(digest(path) == record["sha256"], f"{label} hash differs")
    return path


def _validate_builder(builder: Path) -> None:
    source = builder.read_text(encoding="utf-8")
    for required in (
        "set -euo pipefail",
        "--preflight-only",
        "source_game=$(realpath -e",
        "refusing to replace output game directory",
        ".owned-by-apf-uniform-selector-builder",
        "cp --reflink=auto",
        "apf_uniform_selector_patch.py",
        "apf_uniform_selector_verify.py",
        "mv -- \"$stage\" \"$output_game\"",
    ):
        require(required in source, f"builder lacks safety marker: {required}")
    require("cp -l" not in source, "builder must not hard-link retail game files")
    subprocess.run(["bash", "-n", str(builder)], check=True)


def _validate_replay_queue(root: Path, release: dict[str, Any]) -> dict[str, Any]:
    queue_record = release["runtime_queue"]
    queue_path = _validate_hash_record(root, queue_record, "runtime replay queue")
    queue = load_json(queue_path, "runtime replay queue")
    require(
        queue["schema"] == "apf_uniform_selector_xenia_replay_queue/v1"
        and queue["status"] == "queued_not_executed",
        "runtime replay queue state differs",
    )
    gate = queue["exclusive_input_gate"]
    require(
        gate == {
            "required": True,
            "condition": "No other Xenia/xemu process or virtual controller may be live; the APF helper must enumerate as Xenia controller slot 0.",
            "shared_controller_release_event": "event19",
            "release_received": False,
        },
        "exclusive input gate differs",
    )
    toolchain = queue["toolchain"]
    controller = root / toolchain["controller"]
    require(
        toolchain["controller"] == "tools/apf_uniform_selector_xenia_gamepad.py"
        and toolchain["controller_scope"] == "dedicated_hash_stable_apf_replay_only",
        "queued controller scope differs",
    )
    require(controller.is_file() and not controller.is_symlink(),
            "controller helper is not a regular file")
    require(digest(controller) == toolchain["controller_sha256"], "controller helper differs")
    require(toolchain["emulator_sha256"] == "ac395b9ab2b6da69d25c1be284fa7ac85b116d32cbbf79db5d69ec444f1cd089",
            "queued emulator identity differs")
    require([run["role"] for run in queue["runs"]] == ["retail_control", "copied_output"],
            "queued run order differs")
    expected_0a = [
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
        "d2823acba35284dc35f08d3a9706476d08aba95120ccbbd168b987904f643d5a",
    ]
    for run, wanted in zip(queue["runs"], expected_0a):
        for key in ("emulator", "game_xex", "game_0a"):
            require(Path(run[key]).is_file(), f"queued {run['role']} {key} is missing")
        require(digest(Path(run["emulator"])) == toolchain["emulator_sha256"],
                f"queued {run['role']} emulator differs")
        require(digest(Path(run["game_xex"])) == "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
                f"queued {run['role']} executable differs")
        require(digest(Path(run["game_0a"])) == run["game_0a_sha256"] == wanted,
                f"queued {run['role']} 0A differs")
        require(Path(run["capture_directory"]).is_dir(),
                f"queued {run['role']} capture directory is missing")
    commands = [row["command"] for row in queue["ordered_inputs"]]
    require(commands == [
        "TAP START 5.00", "TAP A 0.50", "TAP A 0.50", "TAP A 0.50",
        "TAP START 0.50", "TAP A 0.50", "TAP START 0.50",
        "TAP START 0.50", "TAP RT 0.35",
    ], "queued input sequence differs")
    capture = queue["capture_contract"]
    require(capture["frame_dimensions"] == list(pose_match.FRAME_SIZE),
            "queued frame dimensions differ")
    require(capture["reference_boxes"] == [list(box) for box in pose_match.REFERENCE_BOXES],
            "queued reference boxes differ")
    require(capture["evidence_boxes"] == [list(box) for box in pose_match.EVIDENCE_BOXES],
            "queued evidence boxes differ")
    require(capture["frame_count_per_run"] == 48, "queued frame count differs")
    return queue


def verify(root: Path, report_path: Path, *, full_volume: bool) -> dict[str, Any]:
    release = load_json(report_path, "mod release report")
    require(release["schema"] == SCHEMA, "mod release schema differs")
    require(release["version"] == "1.0.0", "mod release version differs")
    require(release["status"] == "offline_release_ready_logo_selection_runtime_negative",
            "mod release status differs")
    require(release["distribution"] == {
        "classification": "metadata_and_source_only",
        "retail_game_bytes_included": False,
        "copied_output_volume_included": False,
        "user_must_supply_legally_obtained_retail_game": True,
        "redistributable_inputs": [
            "source code", "schemas", "hashes-only reports",
            "deterministic assignment recipe",
        ],
    }, "distribution boundary differs")

    source_rows = release["source_game"]["required_files"]
    require([row["path"] for row in source_rows] == [
        "0A", "0B", "1A", "1B", "default.xex",
        "$SystemUpdate/su20076000_00000000",
    ], "source-game membership differs")
    for row in source_rows:
        path = RETAIL_GAME / row["path"]
        require(path.is_file() and not path.is_symlink(), f"retail source is missing {row['path']}")
        require(path.stat().st_size == row["size_bytes"], f"retail source size differs: {row['path']}")
        require(digest(path) == row["sha256"], f"retail source hash differs: {row['path']}")

    recipe = release["recipe"]
    recipe_path = _validate_hash_record(root, recipe, "release recipe")
    recipe_document = load_json(recipe_path, "release recipe")
    require(recipe_document["schema"] == recipe["schema"], "release recipe schema differs")
    require(len(recipe_document["families"]) == recipe["family_count"] == 11,
            "release recipe family count differs")
    assignments = sum(len(row["assignments"]) for row in recipe_document["families"])
    changed = sum(
        row["expected_retail_asset_index"] != row["replacement_asset_index"]
        for family in recipe_document["families"] for row in family["assignments"]
    )
    require(assignments == recipe["assignment_count"] == 264,
            "release recipe assignment count differs")
    require(changed == recipe["changed_team_family_assignment_count"] == 95,
            "release recipe changed-assignment count differs")

    tooling_paths: dict[str, Path] = {}
    for label, record in release["tooling"].items():
        tooling_paths[label] = _validate_hash_record(root, record, f"tooling {label}")
    _validate_builder(tooling_paths["builder"])
    verifier_tree = ast.parse(tooling_paths["independent_verifier"].read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(verifier_tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    require("apf_uniform_selector_patch" not in imported,
            "independent verifier imports the selector writer")
    require("apf_uniform_selector_allocation" not in imported,
            "independent verifier imports the allocation planner")

    proof = release["offline_proof"]
    for label in (
        "allocation_authority", "capacity_authority", "roundtrip_closure",
        "frozen_writer_manifest", "frozen_independent_verification",
    ):
        _validate_hash_record(root, proof[label], f"offline proof {label}")
    manifest_path = root / proof["frozen_writer_manifest"]["path"]
    manifest = load_json(manifest_path, "frozen writer manifest")
    frozen_verify_path = root / proof["frozen_independent_verification"]["path"]
    frozen_verify = load_json(frozen_verify_path, "frozen independent verification")
    result = proof["result"]
    require(manifest["result"]["copied_volume"]["sha256"] == result["copied_0a_sha256"],
            "release output-volume hash differs from manifest")
    require(manifest["preservation"]["decoded_changed_byte_count"] == result["decoded_changed_byte_count"],
            "release changed-byte count differs from manifest")
    require(manifest["preservation"]["changed_decoded_offsets_sha256"]
            == result["changed_decoded_offsets_sha256"],
            "release changed-offset digest differs from manifest")
    require(frozen_verify["output_volume_sha256"] == result["copied_0a_sha256"],
            "release output-volume hash differs from independent verification")

    install = release["install"]
    require(
        install["source_opened_read_only"] is True
        and install["output_directory_must_not_exist"] is True
        and install["transaction_uses_owned_sibling_staging_directory"] is True
        and install["failure_removes_only_owned_staging_directory"] is True
        and install["complete_game_tree_created"] is True
        and install["only_0a_changes_from_retail"] is True,
        "install transaction boundary differs",
    )
    integration = release["production_integration"]
    require(integration == {
        "capability_id": "apf2k8.colors.uniform_selector_all_family_capacity",
        "classification": "offline-writer-proved",
        "backend": "tools/build_apf_uniform_selector_mod.sh",
        "validation_command": "bash tools/validate_apf_uniform_selector_mod_release.sh",
        "gui_exposed": False,
        "reason_hidden": "The v1 plan is deterministic rather than user-authored, and its exact Xenia Logo Selection witness executed negative.",
    }, "production integration record differs")
    registry = load_json(
        root / "mod_editor/capabilities/registry.v1.json", "capability registry"
    )
    rows = [
        row for row in registry["capabilities"]
        if row.get("id") == integration["capability_id"]
    ]
    require(len(rows) == 1, "all-family capability registry row differs")
    capability = rows[0]
    require(
        capability["classification"] == integration["classification"]
        and capability["backend"]["module"] == integration["backend"]
        and capability["backend"]["operation"] == "write"
        and capability["validation_command"] == integration["validation_command"]
        and capability["gui"]["expose"] is integration["gui_exposed"]
        and capability["gui"]["default_enabled"] is False,
        "all-family capability integration differs",
    )
    queue = _validate_replay_queue(root, release)
    queue_record = release["runtime_queue"]
    require(
        queue_record["status"] == "executed_from_frozen_queue_negative"
        and queue_record["frozen_queue_document_status"] == queue["status"]
        == "queued_not_executed"
        and queue_record["exclusive_controller_release_received"] is True
        and queue_record["classification"]
        == "pose_matched_assassins_helmet_selector_not_visible_in_logo_selection_xenia",
        "runtime execution state differs",
    )
    runtime_path = _validate_hash_record(
        root, queue_record["execution_report"], "runtime execution report"
    )
    runtime_report = load_json(runtime_path, "runtime execution report")
    require(
        runtime_report["outcome"]["classification"]
        == queue_record["classification"]
        and runtime_report["outcome"]["localization_gate_passed"] is False,
        "runtime negative outcome differs",
    )
    boundary = release["claim_boundary"]
    require(boundary == {
        "offline_installable_mod_proved": True,
        "complete_copied_volume_independently_verified": True,
        "assassins_logo_selection_negative_proved": True,
        "all_eleven_family_plans_runtime_proved": False,
        "assassins_helmet_runtime_proved": False,
        "numbered_bank_home_away_mapping_proved": False,
        "save_override_behavior_proved": False,
        "gameplay_visibility_proved": False,
        "original_xbox_360_hardware_proved": False,
        "arbitrary_user_assignment_editor_exposed": False,
    }, "release claim boundary differs")

    if full_volume:
        fresh = selector_verify.verify(
            RUNTIME / "game-retail/0A",
            recipe_path,
            RUNTIME / "game-all-family/0A",
            manifest_path,
        )
        require(fresh == frozen_verify, "fresh complete-volume verification differs")

    require((root / "docs/research/apf_uniform_selector_mod_release.md").is_file(),
            "release install documentation is missing")
    return {
        "version": release["version"],
        "changed_assignments": changed,
        "decoded_changed_bytes": result["decoded_changed_byte_count"],
        "output_sha256": result["copied_0a_sha256"],
        "runtime_status": queue_record["status"],
        "full_volume_verified": full_volume,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = verify(ROOT, args.report, full_volume=not args.metadata_only)
        print(
            "APF_UNIFORM_SELECTOR_MOD_RELEASE_PASS "
            f"version={result['version']} changed_assignments={result['changed_assignments']} "
            f"decoded_changed_bytes={result['decoded_changed_bytes']} "
            f"runtime={result['runtime_status']} full_volume={str(result['full_volume_verified']).lower()}"
        )
        return 0
    except (
        ReleaseVerifyError,
        selector_verify.VerifyError,
        selector_verify.base.VerifyError,
        KeyError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
