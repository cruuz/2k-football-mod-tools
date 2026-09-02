#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
controller_provenance="$root/tools/apf_xenia_controller_capture_provenance.py"
controller_provenance_size=14939
controller_provenance_sha256=29215981cdfa420f0c4d92f8be49a327f86457e71fe8f97e51ef4f9bdc7e40c5

test ! -L "$controller_provenance"
test "$(stat -c %h "$controller_provenance")" = 1
test "$(stat -c %s "$controller_provenance")" = "$controller_provenance_size"
test "$(sha256sum "$controller_provenance" | awk '{print $1}')" = \
  "$controller_provenance_sha256"

retail_xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
retail_0a='extracted/All-Pro Football 2K8 (USA)/0A'
expected_xex='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
expected_0a='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'

test "$(sha256sum "$retail_xex" | awk '{print $1}')" = "$expected_xex"
test "$(sha256sum "$retail_0a" | awk '{print $1}')" = "$expected_0a"

PYTHONDONTWRITEBYTECODE=1 python3 \
  "$controller_provenance" \
  --binding americans_uniform_pattern_alpha64_20260710 >/dev/null

scratch_root=$(mktemp -d /tmp/apf-uniform-pattern-xenia-runtime.XXXXXX)
case "$scratch_root" in
  /tmp/apf-uniform-pattern-xenia-runtime.*) ;;
  *) echo 'unsafe scratch path' >&2; exit 1 ;;
esac
cleanup() {
  status=$?
  rm -rf -- "$scratch_root"
  if test -e "$scratch_root"; then
    echo "failed to remove private scratch tree: $scratch_root" >&2
    exit 1
  fi
  return "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
export PYTHONPYCACHEPREFIX="$scratch_root/pycache"
scratch_game="$scratch_root/game"
scratch_entry="$scratch_root/uniform_jersey_06.pattern.iff"
scratch_manifest="$scratch_root/writer_manifest.json"
mkdir -m 700 -- "$scratch_game"
find 'extracted/All-Pro Football 2K8 (USA)' \
  -mindepth 1 -maxdepth 1 ! -name 0A \
  -exec cp -a --reflink=auto -t "$scratch_game" {} +
python3 tools/apf_uniform_mip_patch.py \
  --index "$retail_0a" \
  --png reports/cut_content/apf_nfl_lineage/americans_uniform_pattern_probe/americans_outer875_asymmetric_f_alpha64.png \
  --output-entry "$scratch_entry" \
  --output-volume "$scratch_game/0A" \
  --manifest "$scratch_manifest" \
  > "$scratch_root/writer.stdout"
test "$(cat "$scratch_root/writer.stdout")" = \
  'APF_UNIFORM_MIP_PATCH_PASS mode=patched entry=875 file=0 sha256=d37e9ef9620312ccdb62fa852cfa6ed57a6a40f8fb64be05565ecd4efa789c3d'

python3 - "$root" "$scratch_game" "$scratch_entry" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from PIL import Image


root = Path(sys.argv[1])
scratch_game = Path(sys.argv[2])
scratch_entry = Path(sys.argv[3])
sys.path.insert(0, str(root / "tools"))
import apf_xenia_controller_capture_provenance as controller_provenance  # noqa: E402

report_payload = controller_provenance.read_bound(
    root,
    "reports/assets/apf_uniform_pattern_xenia_runtime.json",
    12309,
    "e060398d397dfe7e6dc8aaf1ce7916922a58cfb0126b2c5d2c94456e6163e1fd",
    "pattern APF Xenia runtime report",
)
report = controller_provenance._strict_json(  # type: ignore[attr-defined]
    report_payload, "pattern APF Xenia runtime report"
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


assert report["schema"] == "apf_uniform_pattern_xenia_runtime/v1"
assert report["captured_at"] == "2026-07-10"
assert report["scope"] == {
    "team": "Americans",
    "screen": "Team Package Editor / Home Jersey Editor",
    "outer_entry_index": 875,
    "outer_name": "uniform_jersey_06.iff",
    "inner_file_index": 0,
    "inner_name": "jersey_color",
    "retail_source_modified": False,
    "copied_volume_only": True,
}

for artifact in report["artifacts"].values():
    assert digest(root / artifact["path"]) == artifact["sha256"]

controlled = report["controlled_input"]
fixture_path = root / controlled["path"]
assert digest(fixture_path) == controlled["png_sha256"]
with Image.open(fixture_path) as image:
    fixture = image.convert("RGBA")
assert fixture.size == tuple(controlled["dimensions"]) == (1024, 1024)
assert hashlib.sha256(fixture.tobytes()).hexdigest() == controlled["rgba_sha256"]
expected_rows = ["RRRC", "RCCC", "RRCC", "RCCA"]
assert controlled["symbolic_rows"] == expected_rows
colors = {key: tuple(value) for key, value in controlled["colors"].items()}
assert colors == {
    "R": (255, 0, 0, 255),
    "C": (0, 255, 255, 255),
    "A": (0, 255, 255, 64),
}
fixture_pixels = list(fixture.getdata())
assert {
    "opaque_red": fixture_pixels.count(colors["R"]),
    "opaque_cyan": fixture_pixels.count(colors["C"]),
    "alpha64_cyan": fixture_pixels.count(colors["A"]),
} == controlled["base_pixel_counts"] == {
    "opaque_red": 458752,
    "opaque_cyan": 524288,
    "alpha64_cyan": 65536,
}
for cell_y, symbolic_row in enumerate(expected_rows):
    for cell_x, symbol in enumerate(symbolic_row):
        assert fixture.getpixel((cell_x * 256 + 128, cell_y * 256 + 128)) == (
            colors[symbol]
        )

offline = report["offline_writer"]
fixture_manifest_path = root / offline["fixture_manifest"]
writer_manifest_path = root / offline["writer_manifest"]
validation_manifest_path = root / offline["offline_validation_manifest"]
assert digest(fixture_manifest_path) == offline["fixture_manifest_sha256"]
assert digest(writer_manifest_path) == offline["writer_manifest_sha256"]
assert digest(validation_manifest_path) == offline[
    "offline_validation_manifest_sha256"
]
assert digest(root / offline["independent_validator"]["path"]) == offline[
    "independent_validator"
]["sha256"]

fixture_manifest = json.loads(fixture_manifest_path.read_text(encoding="utf-8"))
assert fixture_manifest["schema"] == "apf_uniform_pattern_probe_fixture/v1"
assert fixture_manifest["geometry"]["symbolic_rows"] == expected_rows
assert fixture_manifest["input"]["png_sha256"] == controlled["png_sha256"]
assert fixture_manifest["input"]["rgba_sha256"] == controlled["rgba_sha256"]
assert len(fixture_manifest["mips"]["levels"]) == 9
assert fixture_manifest["mips"]["all_boundaries_preserved"] is True
assert fixture_manifest["mips"]["level_8_single_bc3_block_encode_decode_exact"] is True

writer = json.loads(writer_manifest_path.read_text(encoding="utf-8"))
assert writer["schema"] == "apf_uniform_mip_patch/v1"
assert writer["mode"] == "patched"
assert writer["source"]["outer_entry_index"] == 875
assert writer["source"]["outer_name"] == "uniform_jersey_06.iff"
assert writer["source"]["inner_file_index"] == 0
assert writer["source"]["inner_name"] == "jersey_color"
assert writer["source"]["png_rgba_sha256"] == controlled["rgba_sha256"]
assert len(writer["levels"]) == offline["levels_regenerated"] == 9
assert [level["level"] for level in writer["levels"]] == list(range(9))
assert [level["level"] for level in writer["levels"] if level["packed_tail"]] == (
    offline["packed_tail_levels"]
) == [6, 7, 8]
assert all(
    level["decode_back_metrics"]["different_components"] == 0
    and level["decode_back_metrics"]["maximum_absolute_error"] == 0
    for level in writer["levels"]
)
assert writer["validation"]["all_nine_levels_regenerated"] is True
assert writer["validation"]["all_nine_levels_decoded_back"] is True
assert writer["validation"]["all_nine_levels_transport_bit_exact"] is True
assert writer["validation"]["inactive_mip_padding_preserved"] is True
assert writer["validation"]["h7a_decode_encode_decode_exact"] is True
assert writer["validation"]["fixed_outer_allocation"] is True
assert writer["validation"]["source_opened_read_only"] is True
assert writer["iff"]["allocation_size"] == offline["fixed_outer_allocation"] == 32768
assert writer["iff"]["file_length_after"] == offline["rebuilt_iff_length"] == 14040
assert writer["iff"]["allocation_slack_after"] == offline["allocation_slack"] == 18580
assert writer["output_entry"]["sha256"] == offline["replacement_entry_sha256"]
copied_volume = writer["copied_volume"]
assert copied_volume["source_volume_sha256_before"] == offline[
    "source_0a_sha256_before_and_after"
]
assert copied_volume["source_volume_sha256_after"] == offline[
    "source_0a_sha256_before_and_after"
]
assert copied_volume["output_volume_sha256"] == offline["copied_patched_0a_sha256"]
assert copied_volume["replacement_read_back_sha256"] == offline[
    "replacement_entry_sha256"
]
assert copied_volume["outside_replacement"]["source_and_output_match"] is True

offline_validation = json.loads(
    validation_manifest_path.read_text(encoding="utf-8")
)
assert offline_validation["schema"] == "apf_uniform_pattern_probe_validation/v1"
assert offline_validation["status"] == "PASS"
assert offline_validation["fixture"]["png_sha256"] == controlled["png_sha256"]
assert offline_validation["writer"]["all_nine_mips_decode_exact"] is True
assert offline_validation["writer"]["alpha64_survives_every_mip_exactly"] is True
assert offline_validation["writer"]["allocation_slack_after"] == 18580
# This field describes the earlier preparation pass, not the later frozen run.
assert offline_validation["runtime"]["title_executed"] is False

retail_xex = root / "extracted/All-Pro Football 2K8 (USA)/default.xex"
retail_0a = root / "extracted/All-Pro Football 2K8 (USA)/0A"
assert digest(retail_xex) == "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
assert digest(retail_0a) == offline["source_0a_sha256_before_and_after"]

runtime = report["runtime"]
assert runtime["release"] == "6e5b832"
assert runtime["build"] == "canary_experimental@6e5b8324f on Jul  8 2026"
assert runtime["emulator_exe_sha256"] == (
    "ac395b9ab2b6da69d25c1be284fa7ac85b116d32cbbf79db5d69ec444f1cd089"
)
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
assert runtime["actual_americans_home_jersey_screen_reached"] is True
assert runtime["source_tree_unchanged_after_run"] is True
assert runtime["prepared_copy_hashes_verified_after_run"] is True
prepared = runtime["pattern_copy"]
prepared_dir = scratch_game
assert digest(prepared_dir / "default.xex") == prepared["default_xex_sha256"]
assert digest(prepared_dir / "0A") == prepared["volume_0a_sha256"]
prepared_entry = scratch_entry
assert digest(prepared_entry) == prepared["replacement_entry_sha256"]
emulator_exe = Path(
    "/media/noah/Storage/.codex-tmp/apf-americans-pattern-probe-20260710/"
    "emulator-pattern/xenia_canary.exe"
)
assert digest(emulator_exe) == runtime["emulator_exe_sha256"]

log_path = root / report["artifacts"]["runtime_log"]["path"]
runtime_log = log_path.read_text(encoding="utf-8", errors="strict")
for required in (
    "canary_experimental@6e5b8324f on Jul  8 2026",
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
window_title = (
    root / report["artifacts"]["window_title"]["path"]
).read_text(encoding="utf-8")
for required in (
    "0x05c00003",
    "canary_experimental@6e5b8324f on Jul  8 2026",
    "[54540807 v0.0.0.2] All Pro Football 2K8",
    "<Vulkan - FBO - SDL>",
):
    assert required in window_title

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
controller_source = controller_path.read_text(encoding="utf-8")
for required in ("UInput", "ABS_Z", "ABS_RZ", '"LT"', '"RT"', "tap_trigger"):
    assert required in controller_source
transcript_path = root / reproduction["input_transcript"]
assert digest(transcript_path) == reproduction["input_transcript_sha256"]
transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
assert transcript["schema"] == "apf_uniform_pattern_xenia_transcript/v1"
assert transcript["controller"]["tool"] == recorded_controller_path
assert transcript["controller"]["sha256"] == frozen_controller_sha256
expected_commands = [
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
assert [row["command"] for row in transcript["ordered_inputs"]] == expected_commands
assert [row["sequence"] for row in transcript["ordered_inputs"]] == list(
    range(1, 14)
)
assert reproduction["command_count"] == len(expected_commands) == 13
assert transcript["capture_state"] == reproduction["capture_state"] == {
    "screen": "TEAM PACKAGE EDITOR / HOME JERSEY EDITOR",
    "team_package": "Americans",
    "selected_panel": "Home Jersey",
    "frame_help_text": "Press A to Select Option",
}

mask_report = report["retail_source_mask"]
mask_path = root / mask_report["path"]
assert digest(mask_path) == mask_report["png_sha256"]
with Image.open(mask_path) as image:
    retail_mask = image.convert("RGBA")
assert retail_mask.size == tuple(mask_report["dimensions"]) == (1024, 1024)
assert hashlib.sha256(retail_mask.tobytes()).hexdigest() == mask_report[
    "rgba_sha256"
]
retail_rgb = retail_mask.convert("RGB")
assert hashlib.sha256(retail_rgb.tobytes()).hexdigest() == mask_report["rgb_sha256"]
mask_pixels = list(retail_mask.getdata())
assert len(mask_pixels) == mask_report["pixel_count"] == 1048576
assert sum(alpha == 0 for _, _, _, alpha in mask_pixels) == mask_report[
    "alpha_zero_pixels"
] == 1048576
assert sum((red, green, blue) == (0, 0, 0) for red, green, blue, _ in mask_pixels) == (
    mask_report["black_rgb_pixels"]
) == 987136
nonblack = [
    (index % retail_mask.width, index // retail_mask.width)
    for index, (red, green, blue, _) in enumerate(mask_pixels)
    if (red, green, blue) != (0, 0, 0)
]
assert len(nonblack) == mask_report["nonblack_rgb_pixels"] == 61440
assert [
    min(x for x, _ in nonblack),
    min(y for _, y in nonblack),
    max(x for x, _ in nonblack) + 1,
    max(y for _, y in nonblack) + 1,
] == mask_report["nonblack_rgb_bbox_xyxy_half_open"] == [28, 716, 1015, 1020]
assert len({pixel[:3] for pixel in mask_pixels}) == mask_report[
    "unique_rgb_values"
] == 35
assert "channel-weight/material mask" in mask_report["interpretation"]
assert "not literal diffuse RGB" in mask_report["interpretation"]

probe = report["visual_probe"]
matched = probe["matched_screen"]
control_path = root / report["artifacts"]["retail_target_control"]["path"]
pattern_path = root / report["artifacts"]["pattern_target"]["path"]
with Image.open(control_path) as image:
    control = image.convert("RGB")
with Image.open(pattern_path) as image:
    pattern = image.convert("RGB")
assert control.size == tuple(matched["control_dimensions"]) == (1280, 739)
assert pattern.size == tuple(matched["pattern_dimensions"]) == (1280, 739)
assert matched["team_package"] == "Americans"
assert matched["selected_panel"] == "Home Jersey"
assert matched["frame_help_text"] == "Press A to Select Option"
assert matched["same_ui_and_camera_state"] is True
assert matched["separate_processes_not_photometrically_synchronized"] is True

crop = probe["crop"]
box = (crop["x0"], crop["y0"], crop["x1"], crop["y1"])
assert box == (840, 250, 960, 465)
control_crop = control.crop(box)
pattern_crop = pattern.crop(box)
assert control_crop.size == pattern_crop.size == (120, 215)
assert crop["width"] == 120 and crop["height"] == 215
assert crop["pixel_count"] == 120 * 215 == 25800
assert hashlib.sha256(control_crop.tobytes()).hexdigest() == crop[
    "control_rgb_sha256"
]
assert hashlib.sha256(pattern_crop.tobytes()).hexdigest() == crop[
    "pattern_rgb_sha256"
]
with Image.open(root / report["artifacts"]["control_crop"]["path"]) as image:
    frozen_control_crop = image.convert("RGB")
with Image.open(root / report["artifacts"]["pattern_crop"]["path"]) as image:
    frozen_pattern_crop = image.convert("RGB")
assert frozen_control_crop.tobytes() == control_crop.tobytes()
assert frozen_pattern_crop.tobytes() == pattern_crop.tobytes()

control_pixels = list(control_crop.getdata())
pattern_pixels = list(pattern_crop.getdata())


def navy(pixel: tuple[int, int, int]) -> bool:
    red, green, blue = pixel
    return blue >= 45 and blue - red >= 15 and blue - green >= 5 and red < 150


def white(pixel: tuple[int, int, int]) -> bool:
    return min(pixel) >= 145 and max(pixel) - min(pixel) <= 55


def red(pixel: tuple[int, int, int]) -> bool:
    red_value, green, blue = pixel
    return (
        red_value >= 100
        and red_value - green >= 25
        and red_value - blue >= 20
    )


assert crop["thresholds"] == {
    "navy": "B>=45,B-R>=15,B-G>=5,R<150",
    "white": "min(R,G,B)>=145,max(R,G,B)-min(R,G,B)<=55",
    "red": "R>=100,R-G>=25,R-B>=20",
}
assert crop["control_counts"] == {
    "navy": sum(map(navy, control_pixels)),
    "white": sum(map(white, control_pixels)),
    "red": sum(map(red, control_pixels)),
} == {"navy": 15400, "white": 2904, "red": 5860}
assert crop["pattern_counts"] == {
    "navy": sum(map(navy, pattern_pixels)),
    "white": sum(map(white, pattern_pixels)),
    "red": sum(map(red, pattern_pixels)),
} == {"navy": 361, "white": 18936, "red": 5734}
assert crop["transitions"] == {
    "control_navy_to_pattern_white": sum(
        navy(left) and white(right)
        for left, right in zip(control_pixels, pattern_pixels)
    ),
    "control_navy_to_pattern_red": sum(
        navy(left) and red(right)
        for left, right in zip(control_pixels, pattern_pixels)
    ),
    "control_red_to_pattern_red": sum(
        red(left) and red(right)
        for left, right in zip(control_pixels, pattern_pixels)
    ),
} == {
    "control_navy_to_pattern_white": 14314,
    "control_navy_to_pattern_red": 716,
    "control_red_to_pattern_red": 4301,
}
component_differences = [
    abs(left_component - right_component)
    for left, right in zip(control_pixels, pattern_pixels)
    for left_component, right_component in zip(left, right)
]
assert sum(left != right for left, right in zip(control_pixels, pattern_pixels)) == (
    crop["different_pixels"]
) == 20277
assert sum(value != 0 for value in component_differences) == crop[
    "different_components"
] == 60468
assert max(component_differences) == crop[
    "maximum_absolute_component_difference"
] == 197
assert abs(
    sum(component_differences) / len(component_differences)
    - crop["mean_absolute_component_difference"]
) < 1e-12
assert crop["mean_absolute_component_difference"] == 93.54166666666667

with Image.open(root / report["artifacts"]["full_comparison"]["path"]) as image:
    full_comparison = image.convert("RGB")
assert full_comparison.size == (2560, 760)
assert full_comparison.crop((0, 0, 1280, 739)).tobytes() == control.tobytes()
assert full_comparison.crop((1280, 0, 2560, 739)).tobytes() == pattern.tobytes()
with Image.open(root / report["artifacts"]["crop_comparison"]["path"]) as image:
    crop_comparison = image.convert("RGB")
assert crop_comparison.size == (240, 236)
assert crop_comparison.crop((0, 0, 120, 215)).tobytes() == control_crop.tobytes()
assert crop_comparison.crop((120, 0, 240, 215)).tobytes() == pattern_crop.tobytes()

assert "navy jersey base becomes overwhelmingly white" in probe[
    "bounded_observation"
]
assert "does not prove literal red/cyan display" in probe["interpretation"]
outcome = report["outcome"]
assert outcome == {
    "copied_archive_boots": True,
    "actual_target_visible": True,
    "target_binding_proved": True,
    "patterned_material_response_observed": True,
    "navy_base_to_white_observed": True,
    "red_panel_persistence_observed": True,
    "literal_red_cyan_display_proved": False,
    "full_f_uv_orientation_proved": False,
    "alpha_behavior_proved": False,
    "distant_mip_behavior_proved": False,
    "hardware_validation": False,
    "classification": "matched_target_asymmetric_mask_response_visible",
}
assert len(report["portme"]) == 4

artifact_dir = root / (
    "reports/cut_content/apf_nfl_lineage/americans_uniform_pattern_xenia"
)
assert {path.name for path in artifact_dir.iterdir() if path.is_file()} == {
    "control_torso_crop.png",
    "control_vs_asymmetric_mask.png",
    "control_vs_pattern_torso_crop.png",
    "patched_americans_home_asymmetric_mask.png",
    "pattern_input_transcript.json",
    "pattern_torso_crop.png",
    "window_title.txt",
    "xenia_pattern_runtime.log",
}
runtime_doc = (
    root / "docs/research/apf_uniform_pattern_xenia_runtime.md"
).read_text(encoding="utf-8")
assert frozen_controller_path in runtime_doc
assert "apf_xenia_controller_capture_provenance.md" in runtime_doc
assert (root / "docs/research/apf_uniform_pattern_probe.md").is_file()
PY

python3 tools/apf_uniform_pattern_probe_validate.py \
  --source-index "$retail_0a" \
  --fixture reports/cut_content/apf_nfl_lineage/americans_uniform_pattern_probe/americans_outer875_asymmetric_f_alpha64.png \
  --fixture-manifest reports/cut_content/apf_nfl_lineage/americans_uniform_pattern_probe/fixture_manifest.json \
  --writer-manifest "$scratch_manifest" \
  --patched-entry "$scratch_entry" \
  --patched-volume "$scratch_game/0A" \
  --report "$scratch_root/offline-revalidation.json" \
  > "$scratch_root/offline.stdout"

test "$(cat "$scratch_root/offline.stdout")" = \
  'APF_UNIFORM_PATTERN_PROBE_VALIDATION_PASS mips=9 alpha64_base=65536 slack=18580 runtime=false'

test "$(sha256sum "$retail_xex" | awk '{print $1}')" = "$expected_xex"
test "$(sha256sum "$retail_0a" | awk '{print $1}')" = "$expected_0a"
test "$(sha256sum "$controller_provenance" | awk '{print $1}')" = \
  "$controller_provenance_sha256"
PYTHONDONTWRITEBYTECODE=1 python3 \
  "$controller_provenance" \
  --binding americans_uniform_pattern_alpha64_20260710 >/dev/null

echo 'APF_UNIFORM_PATTERN_XENIA_RUNTIME_PASS archive_boot=yes target_visible=yes navy_control=15400 navy_pattern=361 white_control=2904 white_pattern=18936 red_control=5860 red_pattern=5734 source_alpha0=1048576 mask_semantics=channel_weight full_f_uv=unproved alpha=unproved distant_mip=unproved hardware=no originals_unchanged=true emulator_launched_by_validator=false'
