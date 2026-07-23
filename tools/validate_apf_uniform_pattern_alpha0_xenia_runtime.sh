#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
controller_provenance="$root/tools/apf_xenia_controller_capture_provenance.py"
controller_provenance_size=18480
controller_provenance_sha256=23243743b1855a840025a031824b291a8c1f80ed41c87a87fa128137732a9c54

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
  --binding americans_uniform_pattern_alpha0_20260710 >/dev/null

scratch_root=$(mktemp -d /tmp/apf-uniform-pattern-alpha0-xenia-runtime.XXXXXX)
case "$scratch_root" in
  /tmp/apf-uniform-pattern-alpha0-xenia-runtime.*) ;;
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
scratch_entry="$scratch_root/uniform_jersey_06.pattern-alpha0.iff"
scratch_manifest="$scratch_root/writer_manifest.json"
mkdir -m 700 -- "$scratch_game"
find 'extracted/All-Pro Football 2K8 (USA)' \
  -mindepth 1 -maxdepth 1 ! -name 0A \
  -exec cp -a --reflink=auto -t "$scratch_game" {} +
python3 tools/apf_uniform_mip_patch.py \
  --index "$retail_0a" \
  --png reports/cut_content/apf_nfl_lineage/americans_uniform_pattern_alpha0_xenia/americans_outer875_asymmetric_f_alpha0.png \
  --output-entry "$scratch_entry" \
  --output-volume "$scratch_game/0A" \
  --manifest "$scratch_manifest" \
  > "$scratch_root/writer.stdout"
test "$(cat "$scratch_root/writer.stdout")" = \
  'APF_UNIFORM_MIP_PATCH_PASS mode=patched entry=875 file=0 sha256=e6f4824d51a13e9423aa8381ed65b40d292f05a3d45544d64b523ae8b3ce1fe9'

python3 - "$root" "$scratch_game" "$scratch_entry" "$scratch_manifest" <<'PY'
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

root = Path(sys.argv[1])
scratch_game = Path(sys.argv[2])
scratch_entry = Path(sys.argv[3])
scratch_manifest = Path(sys.argv[4])
sys.path.insert(0, str(root / "tools"))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_texture_patch as archive_patch  # noqa: E402
import apf_uniform_mip_patch as uniform_patch  # noqa: E402
import apf_xenos_mip_layout as xenos_mips  # noqa: E402
import apf_xenia_controller_capture_provenance as controller_provenance  # noqa: E402

report_payload = controller_provenance.read_bound(
    root,
    "reports/assets/apf_uniform_pattern_alpha0_xenia_runtime.json",
    12916,
    "4ea706acad8e77fcfb0adc65d55991c151823e9ba0287a29531be6188cb256ea",
    "alpha-zero APF Xenia runtime report",
)
report = controller_provenance._strict_json(  # type: ignore[attr-defined]
    report_payload, "alpha-zero APF Xenia runtime report"
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


assert report["schema"] == "apf_uniform_pattern_alpha0_xenia_runtime/v1"
assert report["captured_at"] == "2026-07-10"
assert report["scope"] == {
    "team": "Americans",
    "screen": "Team Package Editor / Home Jersey Editor",
    "outer_entry_index": 875,
    "outer_name": "uniform_jersey_06.iff",
    "inner_file_index": 0,
    "inner_name": "jersey_color",
    "isolated_variable": (
        "replacement alpha: alpha64 sentinel fixture versus alpha zero at "
        "every pixel"
    ),
    "rgb_held_bit_exact": True,
    "retail_source_modified": False,
    "copied_volume_only": True,
}

for artifact in report["artifacts"].values():
    assert digest(root / artifact["path"]) == artifact["sha256"]

pair = report["controlled_alpha_pair"]
alpha0_path = root / pair["alpha0"]["path"]
alpha64_path = root / pair["alpha64_reference"]["path"]
with Image.open(alpha0_path) as image:
    alpha0_fixture = image.convert("RGBA")
with Image.open(alpha64_path) as image:
    alpha64_fixture = image.convert("RGBA")
assert alpha0_fixture.size == alpha64_fixture.size == (1024, 1024)
assert digest(alpha0_path) == pair["alpha0"]["png_sha256"]
assert digest(alpha64_path) == pair["alpha64_reference"]["png_sha256"]
assert hashlib.sha256(alpha0_fixture.tobytes()).hexdigest() == pair["alpha0"][
    "rgba_sha256"
]
assert hashlib.sha256(alpha64_fixture.tobytes()).hexdigest() == pair[
    "alpha64_reference"
]["rgba_sha256"]
alpha0_rgb = alpha0_fixture.convert("RGB")
alpha64_rgb = alpha64_fixture.convert("RGB")
assert hashlib.sha256(alpha0_rgb.tobytes()).hexdigest() == pair["alpha0"][
    "rgb_sha256"
]
assert hashlib.sha256(alpha64_rgb.tobytes()).hexdigest() == pair[
    "alpha64_reference"
]["rgb_sha256"]
assert alpha0_rgb.tobytes() == alpha64_rgb.tobytes()
assert pair["rgb_bytes_identical"] is True
alpha0_pixels = list(alpha0_fixture.getdata())
alpha64_pixels = list(alpha64_fixture.getdata())
assert len(alpha0_pixels) == 1048576
assert sum(pixel[3] == 0 for pixel in alpha0_pixels) == pair["alpha0"][
    "alpha_zero_pixels"
] == 1048576
assert sum(pixel[3] == 255 for pixel in alpha0_pixels) == pair["alpha0"][
    "opaque_pixels"
] == 0
assert Counter(pixel[:3] for pixel in alpha0_pixels) == {
    (255, 0, 0): pair["alpha0"]["rgb_pixel_counts"]["red"],
    (0, 255, 255): pair["alpha0"]["rgb_pixel_counts"]["cyan"],
} == {(255, 0, 0): 458752, (0, 255, 255): 589824}
assert sum(pixel[3] == 255 for pixel in alpha64_pixels) == pair[
    "alpha64_reference"
]["alpha255_pixels"] == 983040
assert sum(pixel[3] == 64 for pixel in alpha64_pixels) == pair[
    "alpha64_reference"
]["alpha64_pixels"] == 65536
different_components = [
    component_index
    for left, right in zip(alpha0_pixels, alpha64_pixels)
    for component_index, (left_component, right_component) in enumerate(
        zip(left, right)
    )
    if left_component != right_component
]
assert len(different_components) == pair["different_rgba_components"] == 1048576
assert set(different_components) == {3}
assert pair["all_differences_are_alpha"] is True
assert pair["symbolic_rgb_rows"] == ["RRRC", "RCCC", "RRCC", "RCCA"]

offline = report["offline_writer"]
manifest_path = root / offline["manifest"]
entry_path = root / offline["standalone_entry"]
assert digest(manifest_path) == offline["manifest_sha256"]
assert digest(entry_path) == offline["standalone_entry_sha256"]
writer = json.loads(manifest_path.read_text(encoding="utf-8"))
rebuilt_writer = json.loads(scratch_manifest.read_text(encoding="utf-8"))
assert writer["schema"] == "apf_uniform_mip_patch/v1"
assert writer["mode"] == "patched"
assert writer["source"]["outer_entry_index"] == 875
assert writer["source"]["outer_name"] == "uniform_jersey_06.iff"
assert writer["source"]["inner_file_index"] == 0
assert writer["source"]["inner_name"] == "jersey_color"
assert writer["source"]["png_rgba_sha256"] == pair["alpha0"]["rgba_sha256"]
assert len(writer["levels"]) == offline["levels_regenerated"] == 9
assert [row["level"] for row in writer["levels"]] == list(range(9))
assert [row["level"] for row in writer["levels"] if row["packed_tail"]] == (
    offline["packed_tail_levels"]
) == [6, 7, 8]
assert all(
    row["decode_back_metrics"]["different_components"] == 0
    and row["decode_back_metrics"]["maximum_absolute_error"] == 0
    for row in writer["levels"]
)
required_flags = (
    "all_nine_levels_regenerated",
    "all_nine_levels_decoded_back",
    "all_nine_levels_transport_bit_exact",
    "inactive_mip_padding_preserved",
    "h7a_decode_encode_decode_exact",
    "rebuilt_iff_reparsed",
    "footer_bit_exact",
    "unrelated_dram_part_preserved",
    "fixed_outer_allocation",
    "source_opened_read_only",
)
assert all(writer["validation"][key] is True for key in required_flags)
assert writer["iff"]["allocation_size"] == offline["fixed_outer_allocation"] == 32768
assert writer["iff"]["file_length_after"] == offline["rebuilt_iff_length"] == 12206
assert writer["iff"]["allocation_slack_after"] == offline["allocation_slack"] == 20414
assert writer["output_entry"]["sha256"] == offline["standalone_entry_sha256"]
copied_manifest = writer["copied_volume"]
assert copied_manifest["output_volume_sha256"] == offline[
    "copied_patched_0a_sha256"
]
assert copied_manifest["source_volume_sha256_before"] == offline[
    "source_0a_sha256_before_and_after"
]
assert copied_manifest["source_volume_sha256_after"] == offline[
    "source_0a_sha256_before_and_after"
]
assert copied_manifest["replacement_read_back_sha256"] == offline[
    "standalone_entry_sha256"
]
assert copied_manifest["outside_replacement"]["source_and_output_match"] is True
assert digest(scratch_entry) == offline["standalone_entry_sha256"]
assert rebuilt_writer["schema"] == writer["schema"]
assert rebuilt_writer["mode"] == writer["mode"]
assert rebuilt_writer["source"]["png_rgba_sha256"] == writer["source"][
    "png_rgba_sha256"
]
assert rebuilt_writer["output_entry"]["sha256"] == writer["output_entry"][
    "sha256"
]
assert rebuilt_writer["copied_volume"]["output_volume_sha256"] == (
    copied_manifest["output_volume_sha256"]
)
assert rebuilt_writer["validation"] == writer["validation"]

# Independently reparse the frozen IFF and decode all nine Xenos/BC3 mips.
retail_0a = root / "extracted/All-Pro Football 2K8 (USA)/0A"
archive = apf_outer.parse_archive(retail_0a)
entry = archive.entries[875]
assert len(entry.segments) == 1
segment = entry.segments[0]
assert segment.pack_name == "0A" and entry.size == 32768
entry_bytes = entry_path.read_bytes()
memory_reader = archive_patch.BytesReader(entry_bytes)
record = apf_inner.parse_iff(memory_reader, entry)
blocks = [
    apf_inner.decode_block(memory_reader, record, index, 1 << 30)
    for index in range(record.block_count)
]
assert record.file_count == 1 and record.block_count == 2
target = record.files[0]
assert target.name == "jersey_color" and target.type_name == "TXTR"
assert len(target.parts) == 2
dram_part, texture_part = target.parts
dram = blocks[dram_part.block_index][
    dram_part.offset : dram_part.offset + dram_part.length
]
texture = blocks[texture_part.block_index][
    texture_part.offset : texture_part.offset + texture_part.length
]
metadata = apf_inner.parse_txtr_metadata(dram)
uniform_patch._strict_descriptor(metadata)  # type: ignore[attr-defined]
locations = xenos_mips.derive_layout(metadata)
assert len(locations) == 9
assert xenos_mips.transport_roundtrip(texture, locations) == texture
for location, writer_level in zip(locations, writer["levels"]):
    wanted = alpha0_fixture.resize(
        (location.width, location.height), Image.Resampling.BOX
    ).tobytes()
    linear = xenos_mips.extract_linear_bc3(texture, location)
    decoded = uniform_patch._decode_linear_bc3(  # type: ignore[attr-defined]
        linear, location
    )
    assert decoded == wanted
    wanted_sha = hashlib.sha256(wanted).hexdigest()
    assert writer_level["wanted_rgba_sha256"] == wanted_sha
    assert writer_level["decoded_rgba_sha256_after"] == wanted_sha
    assert all(decoded[index] == 0 for index in range(3, len(decoded), 4))

# Independently bind the frozen entry into a private rebuilt 0A and compare both sides.
copied_0a = scratch_game / "0A"
assert digest(copied_0a) == offline["copied_patched_0a_sha256"]
assert archive_patch.sha256_range(copied_0a, segment.pack_offset, entry.size) == (
    offline["standalone_entry_sha256"]
)
prefix_size = segment.pack_offset
suffix_offset = segment.pack_offset + entry.size
suffix_size = retail_0a.stat().st_size - suffix_offset
assert archive_patch.sha256_range(retail_0a, 0, prefix_size) == (
    archive_patch.sha256_range(copied_0a, 0, prefix_size)
)
assert archive_patch.sha256_range(retail_0a, suffix_offset, suffix_size) == (
    archive_patch.sha256_range(copied_0a, suffix_offset, suffix_size)
)

retail_xex = root / "extracted/All-Pro Football 2K8 (USA)/default.xex"
assert digest(retail_xex) == "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
assert digest(retail_0a) == offline["source_0a_sha256_before_and_after"]
runtime = report["runtime"]
copy_dir = scratch_game
assert digest(copy_dir / "default.xex") == runtime["alpha0_copy"][
    "default_xex_sha256"
]
assert digest(copy_dir / "0A") == runtime["alpha0_copy"]["volume_0a_sha256"]
source_game = retail_0a.parent
source_files = {
    path.relative_to(source_game).as_posix(): path
    for path in source_game.rglob("*")
    if path.is_file()
}
copied_files = {
    path.relative_to(copy_dir).as_posix(): path
    for path in copy_dir.rglob("*")
    if path.is_file()
}
assert source_files.keys() == copied_files.keys()
for relative, source_path in source_files.items():
    if relative != "0A":
        assert source_path.stat().st_size == copied_files[relative].stat().st_size
        assert digest(source_path) == digest(copied_files[relative])
assert runtime["alpha0_copy"]["replacement_entry_sha256"] == offline[
    "standalone_entry_sha256"
]
assert runtime["source_tree_unchanged_after_run"] is True
assert runtime["prepared_copy_hashes_verified_after_run"] is True
emulator_exe = Path(
    "/media/noah/Storage/.codex-tmp/apf-americans-pattern-alpha0-probe-20260710/"
    "emulator-alpha0/xenia_canary.exe"
)
assert digest(emulator_exe) == runtime["emulator_exe_sha256"] == (
    "ac395b9ab2b6da69d25c1be284fa7ac85b116d32cbbf79db5d69ec444f1cd089"
)

attempts = report["attempt_provenance"]
assert [row["attempt"] for row in attempts] == ["r1", "r2", "r3"]
assert [row["canonical_runtime_evidence"] for row in attempts] == [
    False, False, True
]
for row in attempts:
    assert digest(root / row["log"]) == row["log_sha256"]
assert "closed without a canonical target capture" in attempts[0]["outcome"]
assert "closed without a canonical target capture" in attempts[1]["outcome"]
assert "successful 13-command" in attempts[2]["outcome"]

assert runtime["release"] == "6e5b832"
assert runtime["build"] == "canary_experimental@6e5b8324f on Jul  8 2026"
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
r3_log = (root / attempts[2]["log"]).read_text(encoding="utf-8")
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
    assert required in r3_log
window_title = (
    root / runtime["window_title_capture"]["path"]
).read_text(encoding="utf-8")
for required in (
    "0x05e00003",
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
assert transcript["schema"] == "apf_uniform_pattern_alpha0_xenia_transcript/v1"
assert transcript["attempt"] == reproduction["successful_attempt"] == "r3"
assert transcript["controller"]["tool"] == recorded_controller_path
assert transcript["controller"]["sha256"] == frozen_controller_sha256
commands = [
    "TAP START 5.00",
    "TAP START 5.00",
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
assert [row["command"] for row in transcript["ordered_inputs"]] == commands
assert [row["sequence"] for row in transcript["ordered_inputs"]] == list(
    range(1, 14)
)
assert reproduction["command_count"] == len(commands) == 13
assert reproduction["initial_navigation"] == (
    "The first TAP START 5.00 traversed title readiness; a blank "
    "synchronization wait emitted no input; the second TAP START 5.00 "
    "accepted the welcome flow and reached Team Create."
)
assert transcript["ordered_inputs"][0]["result"].startswith(
    "traversed title readiness"
)
assert transcript["ordered_inputs"][1]["result"] == (
    "accepted the welcome flow and reached Team Create"
)
assert transcript["capture_state"] == reproduction["capture_state"] == {
    "screen": "TEAM PACKAGE EDITOR / HOME JERSEY EDITOR",
    "team_package": "Americans",
    "selected_panel": "Home Jersey",
    "frame_help_text": "Press START to Save Changes and Exit",
}

comparison = report["visual_comparison"]
frame_pair = comparison["frame_pair"]
alpha64_screen_path = root / frame_pair["alpha64_path"]
alpha0_screen_path = root / frame_pair["alpha0_path"]
retail_screen_path = root / report["artifacts"]["retail_screenshot"]["path"]
assert digest(alpha64_screen_path) == frame_pair["alpha64_sha256"]
assert digest(alpha0_screen_path) == frame_pair["alpha0_sha256"]
with Image.open(alpha64_screen_path) as image:
    alpha64_screen = image.convert("RGB")
with Image.open(alpha0_screen_path) as image:
    alpha0_screen = image.convert("RGB")
with Image.open(retail_screen_path) as image:
    retail_screen = image.convert("RGB")
assert alpha64_screen.size == alpha0_screen.size == retail_screen.size == (
    tuple(frame_pair["dimensions"])
) == (1280, 739)
assert frame_pair["same_target_and_torso_camera"] is True
assert frame_pair["same_rgb_fixture"] is True
assert frame_pair["different_help_text_state_outside_crop"] is True
assert frame_pair["separate_processes_not_photometrically_synchronized"] is True

crop = comparison["crop"]
box = (crop["x0"], crop["y0"], crop["x1"], crop["y1"])
assert box == (840, 250, 960, 465)
crops = {
    "retail": retail_screen.crop(box),
    "alpha64": alpha64_screen.crop(box),
    "alpha0": alpha0_screen.crop(box),
}
assert all(image.size == (120, 215) for image in crops.values())
assert crop["width"] == 120 and crop["height"] == 215
assert crop["pixel_count"] == 120 * 215 == 25800
for name, image in crops.items():
    assert hashlib.sha256(image.tobytes()).hexdigest() == crop["rgb_sha256"][name]
pixels = {name: list(image.getdata()) for name, image in crops.items()}


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
counts = {
    name: {
        "navy": sum(map(navy, values)),
        "white": sum(map(white, values)),
        "red": sum(map(red, values)),
    }
    for name, values in pixels.items()
}
assert counts == crop["category_counts"] == {
    "retail": {"navy": 15400, "white": 2904, "red": 5860},
    "alpha64": {"navy": 361, "white": 18936, "red": 5734},
    "alpha0": {"navy": 688, "white": 18240, "red": 5737},
}


def difference(left_name: str, right_name: str) -> dict[str, float | int]:
    left = pixels[left_name]
    right = pixels[right_name]
    components = [
        abs(left_component - right_component)
        for left_pixel, right_pixel in zip(left, right)
        for left_component, right_component in zip(left_pixel, right_pixel)
    ]
    return {
        "different_pixels": sum(a != b for a, b in zip(left, right)),
        "different_components": sum(value != 0 for value in components),
        "maximum_absolute_component_difference": max(components),
        "mean_absolute_component_difference": sum(components) / len(components),
    }


alpha_pair = crop["alpha64_vs_alpha0"]
alpha_pair_metrics = difference("alpha64", "alpha0")
for key in (
    "different_pixels",
    "different_components",
    "maximum_absolute_component_difference",
):
    assert alpha_pair_metrics[key] == alpha_pair[key]
assert abs(
    float(alpha_pair_metrics["mean_absolute_component_difference"])
    - alpha_pair["mean_absolute_component_difference"]
) < 1e-12
assert alpha_pair["different_pixels"] == 4625
assert alpha_pair["different_components"] == 13307
assert alpha_pair["maximum_absolute_component_difference"] == 161
assert alpha_pair["mean_absolute_component_difference"] == 6.451434108527132
alpha64_pixels_crop = pixels["alpha64"]
alpha0_pixels_crop = pixels["alpha0"]
assert alpha_pair["category_mask_disagreement"] == {
    "navy": sum(
        navy(a) != navy(b) for a, b in zip(alpha64_pixels_crop, alpha0_pixels_crop)
    ),
    "white": sum(
        white(a) != white(b) for a, b in zip(alpha64_pixels_crop, alpha0_pixels_crop)
    ),
    "red": sum(
        red(a) != red(b) for a, b in zip(alpha64_pixels_crop, alpha0_pixels_crop)
    ),
} == {"navy": 327, "white": 702, "red": 85}
assert alpha_pair["both_white"] == sum(
    white(a) and white(b) for a, b in zip(alpha64_pixels_crop, alpha0_pixels_crop)
) == 18237
assert alpha_pair["both_red"] == sum(
    red(a) and red(b) for a, b in zip(alpha64_pixels_crop, alpha0_pixels_crop)
) == 5693

retail_pair = crop["retail_vs_alpha0"]
retail_pair_metrics = difference("retail", "alpha0")
for key in (
    "different_pixels",
    "different_components",
    "maximum_absolute_component_difference",
):
    assert retail_pair_metrics[key] == retail_pair[key]
assert abs(
    float(retail_pair_metrics["mean_absolute_component_difference"])
    - retail_pair["mean_absolute_component_difference"]
) < 1e-12
assert retail_pair == {
    "different_pixels": 20217,
    "different_components": 60182,
    "maximum_absolute_component_difference": 197,
    "mean_absolute_component_difference": 88.17904392764858,
}

assert "fully opaque-looking" in comparison["bounded_observation"]
assert "does not prove that the shader never reads alpha" in comparison[
    "interpretation"
]
assert report["outcome"] == {
    "copied_archive_boots": True,
    "actual_target_visible": True,
    "same_rgb_alpha_isolation_proved": True,
    "alpha_zero_target_appears_fully_opaque": True,
    "same_material_mask_appearance_observed": True,
    "conventional_straight_alpha_opacity_at_target": False,
    "shader_never_reads_alpha_proved": False,
    "alpha_irrelevant_everywhere_proved": False,
    "distant_mip_behavior_proved": False,
    "hardware_validation": False,
    "classification": "matched_target_alpha0_same_mask_opaque_visible",
}
assert len(report["portme"]) == 3

evidence_dir = root / (
    "reports/cut_content/apf_nfl_lineage/americans_uniform_pattern_alpha0_xenia"
)
assert {path.name for path in evidence_dir.iterdir() if path.is_file()} == {
    "alpha0_americans_home.png",
    "americans_outer875_asymmetric_f_alpha0.png",
    "r1_xenia.log",
    "r2_xenia.log",
    "r3_input_transcript.json",
    "uniform_jersey_06.pattern-alpha0.iff",
    "window_title.txt",
    "writer_manifest.json",
    "xenia_alpha0_runtime.log",
}
new_doc = (
    root / "docs/research/apf_uniform_pattern_alpha0_xenia_runtime.md"
).read_text(encoding="utf-8")
prior_doc = (
    root / "docs/research/apf_uniform_pattern_xenia_runtime.md"
).read_text(encoding="utf-8")
assert "apf_uniform_pattern_xenia_runtime.md" in new_doc
assert "apf_uniform_pattern_alpha0_xenia_runtime.md" in prior_doc
assert "the shader never reads alpha" in new_doc
assert frozen_controller_path in new_doc
assert "apf_xenia_controller_capture_provenance.md" in new_doc
PY

test "$(sha256sum "$retail_xex" | awk '{print $1}')" = "$expected_xex"
test "$(sha256sum "$retail_0a" | awk '{print $1}')" = "$expected_0a"
test "$(sha256sum "$controller_provenance" | awk '{print $1}')" = \
  "$controller_provenance_sha256"
PYTHONDONTWRITEBYTECODE=1 python3 \
  "$controller_provenance" \
  --binding americans_uniform_pattern_alpha0_20260710 >/dev/null

echo 'APF_UNIFORM_PATTERN_ALPHA0_XENIA_RUNTIME_PASS archive_boot=yes target_visible=yes rgb_same=yes alpha0_pixels=1048576 alpha64_navy=361 alpha0_navy=688 alpha64_white=18936 alpha0_white=18240 alpha64_red=5734 alpha0_red=5737 opaque_appearance=yes conventional_alpha_opacity=no shader_never_reads_alpha=unproved hardware=no originals_unchanged=true emulator_launched_by_validator=false'
