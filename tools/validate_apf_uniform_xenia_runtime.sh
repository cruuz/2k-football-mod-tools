#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
controller_provenance="$root/tools/apf_xenia_controller_capture_provenance.py"
controller_provenance_size=14939
controller_provenance_sha256=29215981cdfa420f0c4d92f8be49a327f86457e71fe8f97e51ef4f9bdc7e40c5

test ! -L "$controller_provenance"
test "$(stat -c %h "$controller_provenance")" = 1
test "$(stat -c %s "$controller_provenance")" = "$controller_provenance_size"
test "$(sha256sum "$controller_provenance" | awk '{print $1}')" = \
  "$controller_provenance_sha256"

PYTHONDONTWRITEBYTECODE=1 python3 \
  "$controller_provenance" \
  --binding americans_uniform_solid_20260710 >/dev/null

python3 - "$root" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from PIL import Image


root = Path(sys.argv[1])
sys.path.insert(0, str(root / "tools"))
import apf_xenia_controller_capture_provenance as controller_provenance  # noqa: E402

report_payload = controller_provenance.read_bound(
    root,
    "reports/assets/apf_uniform_xenia_runtime.json",
    9287,
    "0eabe929101c08d7e83b36ed6ef12e61e18703d3d7bbdb6808650a1181d021bf",
    "solid APF Xenia runtime report",
)
report = controller_provenance._strict_json(  # type: ignore[attr-defined]
    report_payload, "solid APF Xenia runtime report"
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


assert report["schema"] == "apf_uniform_xenia_runtime/v1"
scope = report["scope"]
assert scope == {
    "team": "Americans",
    "outer_entry_index": 875,
    "outer_name": "uniform_jersey_06.iff",
    "inner_file_index": 0,
    "inner_name": "jersey_color",
    "retail_source_modified": False,
    "copied_volume_only": True,
}

controlled = report["controlled_input"]
input_path = root / controlled["path"]
assert digest(input_path) == controlled["png_file_sha256"]
with Image.open(input_path) as image:
    rgba = image.convert("RGBA")
    assert rgba.size == tuple(controlled["dimensions"]) == (1024, 1024)
    assert set(rgba.getdata()) == {(255, 0, 255, 255)}
    assert hashlib.sha256(rgba.tobytes()).hexdigest() == controlled["rgba_sha256"]

writer = report["writer_result"]
manifest_path = root / writer["manifest"]
assert digest(manifest_path) == writer["manifest_sha256"]
manifest = json.loads(manifest_path.read_text())
assert manifest["schema"] == "apf_uniform_mip_patch/v1"
assert manifest["mode"] == "patched"
assert manifest["source"]["outer_entry_index"] == 875
assert manifest["source"]["inner_file_index"] == 0
assert manifest["source"]["inner_name"] == "jersey_color"
assert manifest["source"]["png_rgba_sha256"] == controlled["rgba_sha256"]
assert len(manifest["levels"]) == writer["levels_regenerated"] == 9
assert [level["level"] for level in manifest["levels"]] == list(range(9))
assert [level["level"] for level in manifest["levels"] if level["packed_tail"]] == [6, 7, 8]
assert all(level["decode_back_metrics"]["different_components"] == 0 for level in manifest["levels"])
assert all(level["decode_back_metrics"]["maximum_absolute_error"] == 0 for level in manifest["levels"])
assert manifest["levels"][0]["changed_bc3_blocks"]["count"] == 65536
validation = manifest["validation"]
assert validation["all_nine_levels_regenerated"] is True
assert validation["all_nine_levels_decoded_back"] is True
assert validation["all_nine_levels_transport_bit_exact"] is True
assert validation["fixed_outer_allocation"] is True
assert validation["source_opened_read_only"] is True
assert manifest["iff"]["allocation_size"] == writer["fixed_outer_allocation"] == 32768
copied = manifest["copied_volume"]
assert copied["source_volume_sha256_before"] == writer["source_0a_sha256_before"]
assert copied["source_volume_sha256_after"] == writer["source_0a_sha256_after"]
assert copied["output_volume_sha256"] == writer["copied_patched_0a_sha256"]
assert copied["replacement_read_back_sha256"] == writer["replacement_entry_sha256"]
assert copied["outside_replacement"]["source_and_output_match"] is True

retail_xex = root / "extracted/All-Pro Football 2K8 (USA)/default.xex"
retail_0a = root / "extracted/All-Pro Football 2K8 (USA)/0A"
assert digest(retail_xex) == "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
assert digest(retail_0a) == writer["source_0a_sha256_after"]

runtime = report["runtime"]
assert runtime["release"] == "6e5b832"
assert runtime["build"] == "canary_experimental@6e5b8324f on Jul 8 2026"
assert runtime["emulator_exe_sha256"] == "ac395b9ab2b6da69d25c1be284fa7ac85b116d32cbbf79db5d69ec444f1cd089"
assert runtime["options"] == {
    "gpu": "vulkan",
    "apu": "sdl",
    "hid": "sdl",
    "license_mask": 1,
    "profile_slot_0_xuid": "E03000007E9F1BEC",
    "profile_gamertag": "codex",
}
assert runtime["patch_database_titles_loaded"] == 0
assert runtime["module_launched"] is True
assert runtime["title_screen_rendered"] is True
assert runtime["copied_archive_boot_acceptance"] is True
assert runtime["patched_copy"]["default_xex_sha256"] == digest(retail_xex)
assert runtime["patched_copy"]["volume_0a_sha256"] == writer["copied_patched_0a_sha256"]
assert runtime["patched_copy"]["actual_americans_home_jersey_screen_reached"] is True
control_copy = runtime["retail_control_copy"]
assert control_copy["physically_independent_game_tree"] is True
assert control_copy["default_xex_sha256"] == digest(retail_xex)
assert control_copy["volume_0a_sha256"] == digest(retail_0a)
assert control_copy["profile_runtime_cloned_from_patched_run"] is True
assert control_copy["apf_save_container_present_before_replay"] is False
assert control_copy["actual_americans_home_jersey_screen_reached"] is True
assert runtime["copied_game_trees_unchanged_after_run"] is True
assert runtime["source_tree_unchanged_after_run"] is True

for artifact in report["artifacts"].values():
    assert digest(root / artifact["path"]) == artifact["sha256"]

reproduction = report["reproduction"]
recorded_controller_path = "tools/xenia_virtual_gamepad.py"
frozen_controller_path = (
    "reports/cut_content/apf_nfl_lineage/runtime_provenance/"
    "xenia_virtual_gamepad."
    "fe63265a8e19a873adb794be132f84a44b7a40cd488d753505751470fdaf48dc.py"
)
frozen_controller_sha256 = (
    "fe63265a8e19a873adb794be132f84a44b7a40cd488d753505751470fdaf48dc"
)
assert reproduction["controller_tool"] == recorded_controller_path
assert reproduction["controller_tool_sha256"] == frozen_controller_sha256
controller_path = root / frozen_controller_path
assert controller_path.stat().st_size == 3051
assert controller_path.stat().st_nlink == 1
assert not controller_path.is_symlink()
assert digest(controller_path) == frozen_controller_sha256
controller_source = controller_path.read_text()
for required in ("ABS_Z", "ABS_RZ", '"LT"', '"RT"', "tap_trigger", "UInput"):
    assert required in controller_source
transcript_path = root / reproduction["control_input_transcript"]
assert digest(transcript_path) == reproduction["control_input_transcript_sha256"]
transcript = json.loads(transcript_path.read_text())
assert transcript["schema"] == "apf_uniform_xenia_control_transcript/v1"
assert transcript["controller"]["tool"] == recorded_controller_path
assert transcript["controller"]["sha256"] == frozen_controller_sha256
commands = [entry["command"] for entry in transcript["ordered_inputs"]]
assert commands == [
    "TAP START 5.00",
    "TAP A 0.50",
    "TAP A 0.50",
    "TAP A 0.50",
    "TAP START 0.50",
    "TAP A 0.50",
    "TAP START 0.50",
    "TAP START 0.50",
    "TAP START 0.50",
    "TAP DOWN 0.35",
    "TAP DOWN 0.35",
    "TAP DOWN 0.35",
    "TAP A 0.50",
]
assert [entry["sequence"] for entry in transcript["ordered_inputs"]] == list(range(1, 14))
assert transcript["capture_state"] == {
    "screen": "TEAM PACKAGE EDITOR / HOME JERSEY EDITOR",
    "team_package": "Americans",
    "selected_panel": "Home Jersey",
    "frame_help_text": "Press A to Select Option",
}

probe = report["visual_probe"]
assert probe["screen_proved_to_bind_americans_uniform_jersey_06"] is True
assert probe["actual_americans_team_screen_reached"] is True
matched = probe["matched_screen"]
assert matched["team_package"] == "Americans"
assert matched["selected_panel"] == "Home Jersey"
assert matched["frame_help_text"] == "Press A to Select Option"
assert matched["same_ui_and_camera_state"] is True
assert matched["separate_processes_not_photometrically_synchronized"] is True

control_path = root / report["artifacts"]["retail_target_control"]["path"]
patched_path = root / report["artifacts"]["patched_target"]["path"]
with Image.open(control_path) as image:
    control = image.convert("RGB")
with Image.open(patched_path) as image:
    patched = image.convert("RGB")
assert control.size == tuple(matched["control_dimensions"]) == (1280, 739)
assert patched.size == tuple(matched["patched_dimensions"]) == (1280, 739)

crop_report = probe["crop"]
box = (
    crop_report["x0"],
    crop_report["y0"],
    crop_report["x1"],
    crop_report["y1"],
)
assert box == (840, 250, 960, 465)
control_crop = control.crop(box)
patched_crop = patched.crop(box)
assert control_crop.size == patched_crop.size == (120, 215)
assert crop_report["pixel_count"] == 120 * 215 == 25800
assert hashlib.sha256(control_crop.tobytes()).hexdigest() == crop_report["control_rgb_sha256"]
assert hashlib.sha256(patched_crop.tobytes()).hexdigest() == crop_report["patched_rgb_sha256"]
control_pixels = list(control_crop.getdata())
patched_pixels = list(patched_crop.getdata())


def pink_count(pixels: list[tuple[int, int, int]]) -> int:
    return sum(
        red >= 180 and blue >= 140 and red - green >= 25 and blue - green >= 5
        for red, green, blue in pixels
    )


def navy_count(pixels: list[tuple[int, int, int]]) -> int:
    return sum(
        blue >= 45 and blue - red >= 15 and blue - green >= 5 and red < 150
        for red, green, blue in pixels
    )


assert crop_report["pink_threshold"] == "R>=180,B>=140,R-G>=25,B-G>=5"
assert crop_report["navy_threshold"] == "B>=45,B-R>=15,B-G>=5,R<150"
assert pink_count(control_pixels) == crop_report["control_pink_pixels"] == 98
assert pink_count(patched_pixels) == crop_report["patched_pink_pixels"] == 8969
assert navy_count(control_pixels) == crop_report["control_navy_pixels"] == 15400
assert navy_count(patched_pixels) == crop_report["patched_navy_pixels"] == 341
assert crop_report["patched_pink_pixels"] > 80 * crop_report["control_pink_pixels"]
assert crop_report["control_navy_pixels"] > 40 * crop_report["patched_navy_pixels"]

different_pixels = sum(left != right for left, right in zip(control_pixels, patched_pixels))
component_differences = [
    abs(left_component - right_component)
    for left, right in zip(control_pixels, patched_pixels)
    for left_component, right_component in zip(left, right)
]
assert different_pixels == crop_report["different_pixels"] == 20226
assert sum(value != 0 for value in component_differences) == crop_report["different_components"] == 60194
assert max(component_differences) == crop_report["maximum_absolute_component_difference"] == 149
assert abs(
    sum(component_differences) / len(component_differences)
    - crop_report["mean_absolute_component_difference"]
) < 1e-12

comparison_path = root / report["artifacts"]["target_comparison"]["path"]
with Image.open(comparison_path) as image:
    comparison = image.convert("RGB")
assert comparison.size == (2560, 793)
assert comparison.crop((0, 54, 1280, 793)).tobytes() == control.tobytes()
assert comparison.crop((1280, 54, 2560, 793)).tobytes() == patched.tobytes()

legacy = probe["legacy_non_target_probe"]
assert legacy["control_magenta_pixels"] == legacy["patched_magenta_pixels"] == 0

runtime_log = (root / report["artifacts"]["retail_target_runtime_log"]["path"]).read_text()
for required in (
    "canary_experimental@6e5b8324f",
    'SDL OnControllerDeviceAdded: "Xbox 360 Controller"',
    "VendorID(0x045E), ProductID(0x028E)",
    "PatchDB: Loaded patches for 0 titles",
    "Loaded codex (GUID: E03000007E9F1BEC) to slot 0",
    "NVIDIA GeForce RTX 2080 Ti",
    "Loading module GAME:\\default.xex",
    "Module Hash: 5447E5428AA2D52A",
    "Title name: All Pro Football 2K8",
    "KernelState: Launching module",
    "New controller connected to slot 0",
):
    assert required in runtime_log

boot_excerpt = (root / report["artifacts"]["patched_boot_log_excerpt"]["path"]).read_text()
for required in (
    "canary_experimental@6e5b8324f",
    "PatchDB: Loaded patches for 0 titles",
    "Loading module GAME:\\default.xex",
    "Title name: All Pro Football 2K8",
):
    assert required in boot_excerpt

outcome = report["outcome"]
assert outcome == {
    "copied_archive_boots": True,
    "actual_target_visible": True,
    "controlled_visual_change_observed": True,
    "target_binding_proved": True,
    "solid_color_runtime_visibility_proved": True,
    "runtime_visual_correctness_proved": False,
    "classification": "matched_target_screen_solid_color_visible",
    "hardware_validation": False,
}

artifact_dir = root / "reports/cut_content/apf_nfl_lineage/americans_uniform_xenia"
assert {path.name for path in artifact_dir.iterdir() if path.is_file()} == {
    "americans_uniform_patch_manifest.json",
    "control_input_transcript.json",
    "control_vs_patched_americans_home_jersey.png",
    "control_vs_patched_non_target.png",
    "controlled_input_solid_magenta.png",
    "patched_americans_home_jersey_magenta.png",
    "patched_player_select_non_target.png",
    "patched_title_screen.png",
    "unpatched_americans_home_jersey_control.png",
    "unpatched_player_select_control.png",
    "xenia_uniform_boot_excerpt.log",
    "xenia_uniform_target_visibility.log",
}
runtime_doc = (root / "docs/research/apf_uniform_xenia_runtime.md").read_text()
assert frozen_controller_path in runtime_doc
assert "apf_xenia_controller_capture_provenance.md" in runtime_doc

PY

test "$(sha256sum "$controller_provenance" | awk '{print $1}')" = \
  "$controller_provenance_sha256"
PYTHONDONTWRITEBYTECODE=1 python3 \
  "$controller_provenance" \
  --binding americans_uniform_solid_20260710 >/dev/null

echo 'APF_UNIFORM_XENIA_RUNTIME_PASS archive_boot=yes target_visible=yes solid_color_change=yes pink_control=98 pink_patched=8969 navy_control=15400 navy_patched=341 uv_detail_fidelity=unproved hardware=no'
