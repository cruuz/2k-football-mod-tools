#!/usr/bin/env python3
"""Independently verify the bounded APF Assassins helmet-selector Xenia proof.

This verifier imports the independent all-family selector verifier and the
pose matcher, never the selector writer or allocation planner.  It rechecks
the complete copied 0A, reparses both ROST selector banks, recomputes the
global pose match from every frozen frame, validates runtime provenance, and
keeps the claim limited to team 1's helmet selector changing from 1 to 2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from PIL import Image

import apf_uniform_selector_verify as selector_verify
import apf_uniform_selector_xenia_match as pose_match


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports/assets/apf_uniform_selector_xenia_runtime.json"
RECIPE = ROOT / "reports/asset_samples/apf_roster/uniform_all_families_built_in_capacity.v1.json"
ARTIFACT_ROOT = Path(
    "reports/cut_content/apf_nfl_lineage/assassins_helmet_selector_xenia"
)
SCHEMA = "apf_uniform_selector_xenia_runtime/v1"


class RuntimeVerifyError(ValueError):
    """Frozen runtime evidence does not satisfy the bounded claim."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeVerifyError(message)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _unique_object(label: str):
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeVerifyError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result
    return hook


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object(label),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeVerifyError(f"{label} is invalid JSON") from exc
    require(isinstance(value, dict), f"{label} root is not an object")
    return value


def resolve(root: Path, supplied: str) -> Path:
    path = Path(supplied)
    return path if path.is_absolute() else root / path


def _load_allocation() -> dict[str, Any]:
    with selector_verify.base.BoundFile(
        selector_verify.ALLOCATION_REPORT, "allocation report"
    ) as bound:
        allocation, _raw = selector_verify.load_compact_authority(
            bound,
            selector_verify.ALLOCATION_REPORT_SIZE,
            selector_verify.ALLOCATION_REPORT_SHA256,
            "apf2k8_uniform_selector_allocation/v1",
            "allocation report",
        )
    return allocation


def decoded_selector_layout(
    volume_path: Path, allocation: dict[str, Any], *, retail: bool
) -> tuple[bytes, selector_verify.SelectorLayout]:
    with selector_verify.base.BoundFile(volume_path, "selector runtime volume") as volume:
        outer = selector_verify.base.parse_outer_directory(volume)
        entry = volume.read(outer.pack_offset, outer.size)
    iff = selector_verify.base.parse_iff(entry)
    decoded, _tokens, _consumed = selector_verify.base.decode_h7a(iff.payload)
    layout = selector_verify.derive_selector_layout(
        decoded, allocation, require_retail_vectors=retail
    )
    return decoded, layout


def selector_witness(
    source_path: Path, output_path: Path
) -> dict[str, Any]:
    allocation = _load_allocation()
    source_decoded, source_layout = decoded_selector_layout(
        source_path, allocation, retail=True
    )
    output_decoded, output_layout = decoded_selector_layout(
        output_path, allocation, retail=False
    )
    family_names = [row["family"] for row in allocation["families"]]
    source_assets = {
        name: source_layout.families[name].assets[1] for name in family_names
    }
    output_assets = {
        name: output_layout.families[name].assets[1] for name in family_names
    }
    changed = [
        name for name in family_names if source_assets[name] != output_assets[name]
    ]
    helmet_source = source_layout.families["helmet"]
    helmet_output = output_layout.families["helmet"]
    require(
        helmet_source.offsets[1] == helmet_output.offsets[1]
        and helmet_source.record_indices[1] == helmet_output.record_indices[1],
        "team 1 helmet selector pointer graph differs",
    )
    bank_rows: list[dict[str, Any]] = []
    for bank, (offset, record) in enumerate(
        zip(helmet_source.offsets[1], helmet_source.record_indices[1])
    ):
        source_record = source_decoded[offset:offset + 8]
        output_record = output_decoded[offset:offset + 8]
        require(
            source_record[0] == 1 and output_record[0] == 2
            and source_record[1:] == output_record[1:],
            f"team 1 helmet bank {bank} is not the exact 1-to-2 byte-zero edit",
        )
        bank_rows.append({
            "bank": bank,
            "selector_record_index": record,
            "selector_record_offset": f"0x{offset:x}",
            "source_record_hex": source_record.hex(),
            "output_record_hex": output_record.hex(),
            "opaque_bytes_1_through_7_bit_exact": True,
        })
    for name in family_names:
        if name == "helmet":
            continue
        for source_offset, output_offset in zip(
            source_layout.families[name].offsets[1],
            output_layout.families[name].offsets[1],
        ):
            require(
                source_offset == output_offset
                and source_decoded[source_offset:source_offset + 8]
                == output_decoded[output_offset:output_offset + 8],
                f"team 1 non-helmet family changed: {name}",
            )
    require(changed == ["helmet"], "team 1 changed-family set is not helmet-only")
    return {
        "team_index": 1,
        "team_name": "Assassins",
        "family": "helmet",
        "selector_slot": 3,
        "source_asset_indices": source_assets,
        "output_asset_indices": output_assets,
        "changed_families": changed,
        "helmet_banks": bank_rows,
        "other_ten_family_records_bit_exact": True,
    }


def _validate_frame_sequences(root: Path, report: dict[str, Any]) -> None:
    sequences = report["frame_sequences"]
    for role in ("retail_control", "copied_output"):
        sequence = sequences[role]
        directory = resolve(root, sequence["directory"])
        listed = sequence["frames"]
        require(isinstance(listed, list) and listed, f"{role} frame list is empty")
        expected_names: set[str] = set()
        for item in listed:
            path = resolve(root, item["path"])
            require(path.parent == directory, f"{role} frame escapes its directory")
            require(digest(path) == item["sha256"], f"{role} frame hash differs: {path.name}")
            expected_names.add(path.name)
        actual_names = {
            path.name for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() == ".png"
        }
        require(actual_names == expected_names, f"{role} frame-set membership differs")
        require(
            len(listed) == sequence["frame_count"],
            f"{role} frame count differs",
        )


def _compare_pose_documents(
    stored: dict[str, Any], recomputed: dict[str, Any]
) -> None:
    for key in (
        "schema", "frame_dimensions", "reference_boxes", "evidence_boxes",
        "selection_rule", "control_frame_count", "modified_frame_count",
        "candidate_pair_count", "localization_gate_search",
    ):
        require(stored[key] == recomputed[key], f"pose-match field differs: {key}")
    for rank in ("selected", "runner_up"):
        stored_pair = stored[rank]
        recomputed_pair = recomputed[rank]
        require(
            (stored_pair is None) == (recomputed_pair is None),
            f"pose-match {rank} presence differs",
        )
        if stored_pair is None:
            continue
        for role in ("control", "modified"):
            require(
                Path(stored_pair[role]["path"]).name
                == Path(recomputed_pair[role]["path"]).name,
                f"pose-match {rank} {role} filename differs",
            )
            for key in ("sha256", "reference_rgb_sha256", "evidence_rgb_sha256"):
                require(
                    stored_pair[role][key] == recomputed_pair[role][key],
                    f"pose-match {rank} {role} {key} differs",
                )
        for key in (
            "reference_metrics", "reference_box_metrics",
            "evidence_metrics", "evidence_box_metrics",
        ):
            require(
                stored_pair[key] == recomputed_pair[key],
                f"pose-match {rank} metric differs: {key}",
            )


def _validate_pose_match(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    visual = report["visual_probe"]
    pose_path = resolve(root, visual["pose_match_report"])
    stored = load_json(pose_path, "pose-match report")
    sequences = report["frame_sequences"]
    control_dir = Path(sequences["retail_control"]["directory"])
    output_dir = Path(sequences["copied_output"]["directory"])
    previous = Path.cwd()
    try:
        os.chdir(root)
        recomputed, control_image, modified_image = pose_match.match_frame_sets(
            pose_match._regular_pngs(control_dir),
            pose_match._regular_pngs(output_dir),
        )
    finally:
        os.chdir(previous)
    _compare_pose_documents(stored, recomputed)
    selected = stored["selected"]

    outputs = stored["outputs"]
    selected_control = resolve(root, outputs["selected_control"]["path"])
    selected_modified = resolve(root, outputs["selected_modified"]["path"])
    panel_path = resolve(root, outputs["comparison_panel"]["path"])
    for path, record in (
        (selected_control, outputs["selected_control"]),
        (selected_modified, outputs["selected_modified"]),
        (panel_path, outputs["comparison_panel"]),
    ):
        require(digest(path) == record["sha256"], f"pose-match output hash differs: {path.name}")
    require(
        digest(selected_control) == selected["control"]["sha256"]
        and digest(selected_modified) == selected["modified"]["sha256"],
        "selected frame copies differ from the global-minimum pair",
    )
    expected_panel = pose_match._comparison_panel(control_image, modified_image)
    with Image.open(panel_path) as image:
        image.load()
        actual_panel = image.convert("RGB")
    require(
        actual_panel.size == expected_panel.size
        and actual_panel.tobytes() == expected_panel.tobytes(),
        "comparison panel does not exactly reproduce the selected pair",
    )

    reference = selected["reference_metrics"]
    evidence = selected["evidence_metrics"]
    gates = visual["localization_gates"]
    require(
        gates == stored["localization_gate_search"]["gates"]
        and visual["localization_gate_search"]
        == stored["localization_gate_search"],
        "declared localization search differs from the complete pose search",
    )
    require(
        gates["maximum_reference_mean_absolute_component_difference"] <= 8.0,
        "declared pose-match tolerance is too permissive",
    )
    reference_pass = (
        reference["mean_absolute_component_difference"]
        <= gates["maximum_reference_mean_absolute_component_difference"]
    )
    ratio = (
        evidence["mean_absolute_component_difference"]
        / max(reference["mean_absolute_component_difference"], 1e-12)
    )
    require(gates["minimum_evidence_to_reference_mad_ratio"] >= 1.5,
            "declared evidence/reference gate is too permissive")
    ratio_pass = ratio >= gates["minimum_evidence_to_reference_mad_ratio"]
    preview_fractions: dict[str, float] = {}
    for row in selected["evidence_box_metrics"]:
        fraction = row["different_pixels"] / row["pixel_count"]
        preview_fractions[row["preview"]] = fraction
    require(
        gates["minimum_changed_pixel_fraction_per_preview"] >= 0.05,
        "declared per-preview pixel gate is too permissive",
    )
    preview_pass = all(
        fraction >= gates["minimum_changed_pixel_fraction_per_preview"]
        for fraction in preview_fractions.values()
    )
    localized = reference_pass and ratio_pass and preview_pass
    search = stored["localization_gate_search"]
    require(
        search["reference_eligible_pair_count"] > 0
        and (search["all_gate_pair_count"] > 0) is localized,
        "global-minimum outcome and exhaustive localization search disagree",
    )
    return {
        "reference_mad": reference["mean_absolute_component_difference"],
        "evidence_mad": evidence["mean_absolute_component_difference"],
        "evidence_to_reference_mad_ratio": ratio,
        "per_preview_changed_pixel_fractions": preview_fractions,
        "localization_gate_passed": localized,
        "reference_eligible_pair_count": search["reference_eligible_pair_count"],
        "all_gate_pair_count": search["all_gate_pair_count"],
    }


def _validate_transcript(root: Path, report: dict[str, Any]) -> None:
    reproduction = report["reproduction"]
    controller = resolve(root, reproduction["controller_tool"])
    transcript_path = resolve(root, reproduction["input_transcript"])
    require(
        digest(controller) == reproduction["controller_tool_sha256"],
        "controller helper hash differs",
    )
    source = controller.read_text(encoding="utf-8")
    for marker in (
        "Hash-stable virtual Xbox controller", "ABS_RZ", '"RT"', "UInput"
    ):
        require(marker in source, f"controller helper lacks {marker}")
    require(
        digest(transcript_path) == reproduction["input_transcript_sha256"],
        "input transcript hash differs",
    )
    transcript = load_json(transcript_path, "input transcript")
    require(
        transcript["schema"] == "apf_uniform_selector_xenia_input_transcript/v1",
        "input transcript schema differs",
    )
    expected_commands = [
        "TAP START 5.00", "TAP A 0.50", "TAP A 0.50", "TAP A 0.50",
        "TAP START 0.50", "TAP A 0.50", "TAP START 0.50",
        "TAP START 0.50", "TAP RT 0.35",
    ]
    ordered = transcript["ordered_inputs"]
    require(
        [row["sequence"] for row in ordered] == list(range(1, 10))
        and [row["command"] for row in ordered] == expected_commands,
        "input replay sequence differs",
    )
    require(
        transcript["same_replay_used_for_both_runs"] is True
        and transcript["capture_state"] == {
            "screen": "LOGO SELECTION",
            "team_label": "ASSASSINS",
            "left_preview_label": "HOME",
            "right_preview_label": "AWAY",
            "no_uniform_package_accepted": True,
        },
        "transcript capture state differs",
    )


def _validate_logs(root: Path, report: dict[str, Any]) -> None:
    runtime = report["runtime"]
    required = (
        "canary_experimental@6e5b8324f",
        'SDL OnControllerDeviceAdded: "Xbox 360 Controller"',
        "VendorID(0x045E), ProductID(0x028E)",
        "PatchDB: Loaded patches for 0 titles",
        "NVIDIA GeForce RTX 2080 Ti",
        "Loading module GAME:\\default.xex",
        "Module Hash: 5447E5428AA2D52A",
        "Title name: All Pro Football 2K8",
        "KernelState: Launching module",
        "New controller connected to slot 0",
    )
    for role in ("retail_control", "copied_output"):
        log_path = resolve(root, runtime[role]["log"])
        require(digest(log_path) == runtime[role]["log_sha256"], f"{role} log hash differs")
        log = log_path.read_text(encoding="utf-8", errors="strict")
        for marker in required:
            require(marker in log, f"{role} runtime log lacks {marker}")
    require(runtime["patch_database_titles_loaded"] == 0, "external patches were loaded")


def verify(root: Path, report_path: Path) -> dict[str, Any]:
    report = load_json(report_path, "runtime report")
    require(report.get("schema") == SCHEMA, "runtime report schema differs")
    require(report["scope"] == {
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
    }, "runtime scope differs")

    files = report["runtime_files"]
    source = resolve(root, files["retail_control_0a"]["path"])
    output = resolve(root, files["copied_output_0a"]["path"])
    source_xex = resolve(root, files["retail_control_xex"]["path"])
    output_xex = resolve(root, files["copied_output_xex"]["path"])
    for record, path in (
        (files["retail_control_0a"], source),
        (files["copied_output_0a"], output),
        (files["retail_control_xex"], source_xex),
        (files["copied_output_xex"], output_xex),
    ):
        require(path.is_file() and not path.is_symlink(), f"runtime file is not regular: {path}")
        require(path.stat().st_size == record["size_bytes"], f"runtime file size differs: {path}")
        require(digest(path) == record["sha256"], f"runtime file hash differs: {path}")
    require(
        files["retail_control_xex"]["sha256"]
        == files["copied_output_xex"]["sha256"]
        == "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
        "runtime executable identity differs",
    )

    artifacts = report["artifacts"]
    for name, record in artifacts.items():
        path = resolve(root, record["path"])
        require(digest(path) == record["sha256"], f"artifact hash differs: {name}")

    manifest = resolve(root, artifacts["writer_manifest"]["path"])
    frozen_verify = resolve(root, artifacts["independent_offline_verify"]["path"])
    independent = selector_verify.verify(source, RECIPE, output, manifest)
    require(
        independent == load_json(frozen_verify, "frozen independent selector verification"),
        "fresh independent selector verification differs from frozen result",
    )
    require(
        independent["output_volume_sha256"] == files["copied_output_0a"]["sha256"]
        and independent["manifest_sha256"] == artifacts["writer_manifest"]["sha256"],
        "runtime copied volume is not the independently verified writer output",
    )

    actual_witness = selector_witness(source, output)
    require(actual_witness == report["selector_witness"], "team 1 selector witness differs")
    _validate_frame_sequences(root, report)
    visual_result = _validate_pose_match(root, report)
    _validate_transcript(root, report)
    _validate_logs(root, report)

    positive_outcome = {
        "copied_archive_boots": True,
        "assassins_logo_selection_reached_in_both_runs": True,
        "pose_matched_helmet_change_observed": True,
        "team_1_helmet_selector_runtime_visibility_proved_in_xenia": True,
        "both_numbered_roster_records_changed_offline": True,
        "both_labeled_preview_cards_show_localized_change": True,
        "all_eleven_families_runtime_proved": False,
        "numbered_bank_to_home_away_mapping_proved": False,
        "save_override_behavior_proved": False,
        "gameplay_visibility_proved": False,
        "original_xbox_360_hardware_proved": False,
        "classification": "pose_matched_assassins_helmet_selector_visible_in_xenia",
        "localization_gate_passed": True,
    }
    negative_outcome = {
        "copied_archive_boots": True,
        "assassins_logo_selection_reached_in_both_runs": True,
        "pose_matched_helmet_change_observed": False,
        "team_1_helmet_selector_runtime_visibility_proved_in_xenia": False,
        "both_numbered_roster_records_changed_offline": True,
        "both_labeled_preview_cards_show_localized_change": False,
        "all_eleven_families_runtime_proved": False,
        "numbered_bank_to_home_away_mapping_proved": False,
        "save_override_behavior_proved": False,
        "gameplay_visibility_proved": False,
        "original_xbox_360_hardware_proved": False,
        "classification": "pose_matched_assassins_helmet_selector_not_visible_in_logo_selection_xenia",
        "localization_gate_passed": False,
    }
    outcome = report["outcome"]
    expected_outcome = (
        positive_outcome
        if visual_result["localization_gate_passed"]
        else negative_outcome
    )
    require(outcome == expected_outcome, "runtime outcome differs")

    capability_path = root / "mod_editor/capabilities/registry.v1.json"
    registry = load_json(capability_path, "capability registry")
    capabilities = {row["id"]: row for row in registry["capabilities"]}
    capability = capabilities["apf2k8.colors.uniform_selector_bytes"]
    require(
        capability["classification"] == "read-only-mapped"
        and capability["gui"]["mode"] == "view"
        and capability["runtime"]["status"]
        == ("partial" if visual_result["localization_gate_passed"] else "negative")
        and "reports/assets/apf_uniform_selector_xenia_runtime.json"
        in capability["runtime"]["evidence"],
        "selector viewer capability overstates or omits the bounded runtime proof",
    )
    require(
        (root / "docs/research/apf_uniform_selector_xenia_runtime.md").is_file(),
        "runtime research note is missing",
    )
    return {
        "classification": outcome["classification"],
        "output_volume_sha256": independent["output_volume_sha256"],
        "reference_mad": visual_result["reference_mad"],
        "evidence_mad": visual_result["evidence_mad"],
        "evidence_to_reference_mad_ratio": visual_result["evidence_to_reference_mad_ratio"],
        "localization_gate_passed": visual_result["localization_gate_passed"],
        "hardware": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    try:
        result = verify(ROOT, args.report)
        print(
            "APF_UNIFORM_SELECTOR_XENIA_RUNTIME_PASS "
            f"classification={result['classification']} "
            f"reference_mad={result['reference_mad']:.6f} "
            f"evidence_mad={result['evidence_mad']:.6f} "
            f"localization_ratio={result['evidence_to_reference_mad_ratio']:.3f} "
            f"localization_pass={str(result['localization_gate_passed']).lower()} "
            "hardware=no"
        )
        return 0
    except (
        RuntimeVerifyError,
        selector_verify.VerifyError,
        selector_verify.base.VerifyError,
        pose_match.MatchError,
        KeyError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
