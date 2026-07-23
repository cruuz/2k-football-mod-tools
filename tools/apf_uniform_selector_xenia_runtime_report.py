#!/usr/bin/env python3
"""Build the hashes-only APF selector Xenia runtime evidence report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import apf_uniform_selector_xenia_runtime_verify as verifier


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "reports/cut_content/apf_nfl_lineage/assassins_helmet_selector_xenia"
RUNTIME = Path("/media/noah/Storage/.codex-tmp/apf-all-family-selector-runtime-20260716")
QUEUE = ROOT / "reports/assets/apf_uniform_selector_xenia_replay_queue.v1.json"
OUTPUT = ROOT / "reports/assets/apf_uniform_selector_xenia_runtime.json"


class ReportError(ValueError):
    """The frozen evidence is incomplete or internally inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportError(message)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def file_record(path: Path, *, repo_relative: bool = True) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"not a regular file: {path}")
    return {
        "path": relative(path) if repo_relative else str(path),
        "size_bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def frame_sequence(role: str) -> dict[str, Any]:
    directory = ARTIFACT / "final_v1_frames" / role
    frames = sorted(directory.glob("*.png"))
    require(len(frames) == 48, f"{role} does not contain exactly 48 frames")
    return {
        "directory": relative(directory),
        "frame_count": len(frames),
        "frames": [
            {"path": relative(path), "sha256": digest(path)} for path in frames
        ],
    }


def build_report() -> dict[str, Any]:
    queue = load_json(QUEUE)
    require(queue["status"] == "queued_not_executed", "frozen v1 queue drift")
    pose_path = ARTIFACT / "final_v1_pose_match.json"
    pose = load_json(pose_path)
    search = pose["localization_gate_search"]
    gates = search["gates"]
    selected = pose["selected"]
    reference_mad = selected["reference_metrics"][
        "mean_absolute_component_difference"
    ]
    evidence_mad = selected["evidence_metrics"][
        "mean_absolute_component_difference"
    ]
    ratio = evidence_mad / max(reference_mad, 1e-12)
    fractions = {
        row["preview"]: row["different_pixels"] / row["pixel_count"]
        for row in selected["evidence_box_metrics"]
    }
    localized = (
        reference_mad
        <= gates["maximum_reference_mean_absolute_component_difference"]
        and ratio >= gates["minimum_evidence_to_reference_mad_ratio"]
        and min(fractions.values())
        >= gates["minimum_changed_pixel_fraction_per_preview"]
    )
    require(
        (search["all_gate_pair_count"] > 0) is localized,
        "selected outcome and exhaustive gate search disagree",
    )

    source = RUNTIME / "game-retail/0A"
    output = RUNTIME / "game-all-family/0A"
    source_xex = RUNTIME / "game-retail/default.xex"
    output_xex = RUNTIME / "game-all-family/default.xex"
    require(
        digest(source) == "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
        and digest(output) == "d2823acba35284dc35f08d3a9706476d08aba95120ccbbd168b987904f643d5a"
        and digest(source_xex) == digest(output_xex)
        == "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
        "post-runtime game identity differs",
    )
    witness = verifier.selector_witness(source, output)

    writer_manifest = ARTIFACT / "all_family_writer_manifest.json"
    offline_verify = ARTIFACT / "all_family_independent_verify.json"
    selected_control = ARTIFACT / "final_v1_selected_control.png"
    selected_modified = ARTIFACT / "final_v1_selected_modified.png"
    panel = ARTIFACT / "final_v1_comparison_panel.png"
    transcript = ARTIFACT / "final_v1_input_transcript.json"
    controller = ROOT / queue["toolchain"]["controller"]
    control_log = ARTIFACT / "final_v1_control_xenia.log"
    modified_log = ARTIFACT / "final_v1_modified_xenia.log"

    outcome = {
        "copied_archive_boots": True,
        "assassins_logo_selection_reached_in_both_runs": True,
        "pose_matched_helmet_change_observed": localized,
        "team_1_helmet_selector_runtime_visibility_proved_in_xenia": localized,
        "both_numbered_roster_records_changed_offline": True,
        "both_labeled_preview_cards_show_localized_change": localized,
        "all_eleven_families_runtime_proved": False,
        "numbered_bank_to_home_away_mapping_proved": False,
        "save_override_behavior_proved": False,
        "gameplay_visibility_proved": False,
        "original_xbox_360_hardware_proved": False,
        "classification": (
            "pose_matched_assassins_helmet_selector_visible_in_xenia"
            if localized
            else "pose_matched_assassins_helmet_selector_not_visible_in_logo_selection_xenia"
        ),
        "localization_gate_passed": localized,
    }
    report = {
        "schema": verifier.SCHEMA,
        "created_at": "2026-07-16",
        "scope": {
            "team_index": 1,
            "team_name": "Assassins",
            "family": "helmet",
            "selector_slot": 3,
            "retail_asset_index": 1,
            "copied_output_asset_index": 2,
            "both_numbered_selector_records_changed": True,
            "numbered_bank_home_away_mapping_claimed": False,
            "all_family_runtime_visibility_claimed": False,
            "original_xbox_360_hardware_claimed": False,
            "retail_source_modified": False,
            "copied_volume_only": True,
        },
        "runtime_files": {
            "retail_control_0a": file_record(source, repo_relative=False),
            "copied_output_0a": file_record(output, repo_relative=False),
            "retail_control_xex": file_record(source_xex, repo_relative=False),
            "copied_output_xex": file_record(output_xex, repo_relative=False),
        },
        "artifacts": {
            "writer_manifest": file_record(writer_manifest),
            "independent_offline_verify": file_record(offline_verify),
            "pose_match_report": file_record(pose_path),
            "selected_control": file_record(selected_control),
            "selected_modified": file_record(selected_modified),
            "comparison_panel": file_record(panel),
            "input_transcript": file_record(transcript),
        },
        "selector_witness": witness,
        "frame_sequences": {
            "retail_control": frame_sequence("control"),
            "copied_output": frame_sequence("modified"),
        },
        "visual_probe": {
            "pose_match_report": relative(pose_path),
            "localization_gates": gates,
            "localization_gate_search": search,
            "observed": {
                "selected_control_frame": Path(
                    selected["control"]["path"]
                ).name,
                "selected_modified_frame": Path(
                    selected["modified"]["path"]
                ).name,
                "reference_mad": reference_mad,
                "evidence_mad": evidence_mad,
                "evidence_to_reference_mad_ratio": ratio,
                "per_preview_changed_pixel_fractions": fractions,
                "localization_gate_passed": localized,
            },
            "interpretation": (
                "The helmet crowns localize above pose drift."
                if localized
                else "No reference-eligible frame pair localizes a helmet-crown change; the selected crowns differ less than the face/facemask reference regions."
            ),
        },
        "reproduction": {
            "queue": relative(QUEUE),
            "queue_sha256": digest(QUEUE),
            "controller_tool": relative(controller),
            "controller_tool_sha256": digest(controller),
            "input_transcript": relative(transcript),
            "input_transcript_sha256": digest(transcript),
            "same_nine_inputs_used_for_both_runs": True,
            "frame_count_per_run": 48,
            "minimum_capture_pause_ms": 150,
        },
        "runtime": {
            "emulator_build": queue["toolchain"]["emulator_build"],
            "emulator_sha256": queue["toolchain"]["emulator_sha256"],
            "patch_database_titles_loaded": 0,
            "retail_control": {
                "log": relative(control_log),
                "log_sha256": digest(control_log),
            },
            "copied_output": {
                "log": relative(modified_log),
                "log_sha256": digest(modified_log),
            },
            "controller_slot": 0,
            "window_dimensions": [1280, 739],
            "controller_and_xenia_released_after_capture": True,
        },
        "outcome": outcome,
        "limitations": [
            "This negative result is limited to the unaccepted Assassins Logo Selection previews under the exact queued Xenia build and readback mode.",
            "It does not prove that helmet selector slot 3 is unused in gameplay, another UI, a save-resolved team, or original Xbox 360 hardware.",
            "It does not map either numbered selector record to Home or Away.",
            "It does not prove runtime behavior for the other ten selector families or the other built-in teams.",
        ],
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    try:
        report = build_report()
        require(not args.output.exists() and not args.output.is_symlink(),
                f"refusing to replace output: {args.output}")
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print(
            "APF_UNIFORM_SELECTOR_XENIA_RUNTIME_REPORT_PASS "
            f"classification={report['outcome']['classification']} "
            f"localization_pass={str(report['outcome']['localization_gate_passed']).lower()}"
        )
        return 0
    except (ReportError, verifier.RuntimeVerifyError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
