#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
report="$root/reports/assets/apf_xenia_patch_runtime.json"

python3 - "$root" "$report" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from PIL import Image


root = Path(sys.argv[1])
report_path = Path(sys.argv[2])
report = json.loads(report_path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


assert report["schema"] == "apf_xenia_patch_runtime/v1"
assert report["scope"]["retail_source_modified"] is False
assert report["scope"]["emulator_or_game_binary_redistributed"] is False

emulator = report["emulator"]
assert emulator["release_tag"] == "6e5b832"
assert emulator["windows_archive_size"] == 3565596
assert emulator["windows_archive_sha256"] == (
    "fe43847b26b73140bdf131259f540b12ed7edcb2bf18dd846dc5bc1cf7e293dd"
)
assert emulator["executable_size"] == 16559104
assert emulator["executable_sha256"] == (
    "ac395b9ab2b6da69d25c1be284fa7ac85b116d32cbbf79db5d69ec444f1cd089"
)
assert all(emulator["isolated_runtime"].values())
assert emulator["successful_options"] == {
    "gpu": "vulkan",
    "apu": "sdl",
    "hid": "sdl",
    "fullscreen": False,
    "sdl_audio_driver": "dummy",
}
assert "CreateDriver failed" in emulator["failed_control"]["last_relevant_log"]

patch = report["patch"]
assert patch["outer_entry_index"] == 810
assert patch["inner_file_index"] == 117
assert patch["inner_name"] == "draft_logo"
assert patch["changed_bc3_block_indices"] == [66]
assert patch["decode_back_different_components"] == 0
assert patch["unrelated_inner_parts_preserved"] == 158
assert patch["source_volume_sha256_before"] == patch["source_volume_sha256_after"]
assert patch["source_volume_sha256_before"] == (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)
assert patch["copied_volume_sha256"] == (
    "eb2d9e39763e35cf1221aad3b6cf26f779e00db65baa0a977d91e0a7987ea720"
)
assert patch["bytes_outside_fixed_entry_match_source"] is True

manifest_path = root / patch["manifest"]
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assert manifest["schema"] == "apf_texture_patch/v1"
assert manifest["mode"] == "patched"
assert manifest["source"]["outer_entry_index"] == 810
assert manifest["source"]["inner_file_index"] == 117
assert manifest["target"]["changed_bc3_block_indices"] == [66]
assert manifest["target"]["decode_back_metrics"]["different_components"] == 0
assert manifest["validation"]["unrelated_inner_part_count"] == 158
assert manifest["validation"]["unrelated_inner_parts_preserved"] is True
copied = manifest["copied_volume"]
assert copied["source_volume_sha256_before"] == copied["source_volume_sha256_after"]
assert copied["output_volume_sha256"] == patch["copied_volume_sha256"]
assert copied["outside_replacement"]["source_and_output_match"] is True
assert Path(copied["source_volume"]) != Path(copied["output_volume"])

source = report["source_tree"]
before_path = root / source["before_manifest"]
after_path = root / source["after_manifest"]
before = before_path.read_bytes()
after = after_path.read_bytes()
assert before == after
assert sha256_file(before_path) == (
    "0af931f024275cb8011848c0bb0caffbb32765eedcd23faea0bd1669f585c639"
)
lines = before.decode("utf-8").splitlines()
assert len(lines) == 6
for relative, digest in source["file_sha256"].items():
    assert any(line.startswith(digest + "  ") and line.endswith("/" + relative) for line in lines)

# Recheck the patch source currently present in the canonical workspace. The
# remaining full-tree before/after state is preserved in the matching captures.
source_0a = root / "extracted/All-Pro Football 2K8 (USA)/0A"
assert sha256_file(source_0a) == patch["source_volume_sha256_before"]

evidence = report["runtime_evidence"]
assert evidence["module_hash"] == "5447E5428AA2D52A"
assert evidence["original_pe_name"] == "nfl_clean_opt_submission_ready.xex"
assert evidence["title_name"] == "All Pro Football 2K8"
assert evidence["module_launched"] is True
assert evidence["audio_client_registered"] is True
assert evidence["title_screen_rendered"] is True
assert evidence["attract_mode_stadium_rendered"] is True
assert evidence["copied_game_files_unchanged_after_emulator_run"] is True

artifact_hashes = {
    "reports/cut_content/apf_nfl_lineage/runtime_validation/patched_title_screen.png":
        "0ad1dea09ea644d721bf23e1a766b70f25e81d1e4a73e74830a709b3326631d5",
    "reports/cut_content/apf_nfl_lineage/runtime_validation/patched_attract_stadium.png":
        "ec614fc3561edd3f0a1b69759c6edaa023d7a61bcdd95c12e1cb269e9faccbf9",
    "reports/cut_content/apf_nfl_lineage/runtime_validation/xenia_canary_boot_excerpt.log":
        "9e02f5c084756e13b2a9dafdf3668a4c1ee8e5df59c5f554812340edffce871f",
}
for artifact in evidence["artifacts"]:
    path = root / artifact["path"]
    assert artifact_hashes[artifact["path"]] == artifact["sha256"]
    assert sha256_file(path) == artifact["sha256"]
    if path.suffix == ".png":
        with Image.open(path) as image:
            assert image.size == (artifact["width"], artifact["height"])

excerpt = (
    root
    / "reports/cut_content/apf_nfl_lineage/runtime_validation/xenia_canary_boot_excerpt.log"
).read_text(encoding="utf-8")
for required in (
    "canary_experimental@6e5b8324f",
    "Storage root:",
    "Content root:",
    "Host cache root:",
    "NVIDIA GeForce RTX 2080 Ti",
    "Loading module GAME:\\default.xex",
    "Module Hash: 5447E5428AA2D52A",
    "XEX_HEADER_ORIGINAL_PE_NAME: nfl_clean_opt_submission_ready.xex",
    "Title name: All Pro Football 2K8",
    "KernelState: Launching module",
    "AudioSystem::RegisterClient: client 0 registered successfully",
):
    assert required in excerpt

boundary = report["claim_boundary"]
assert boundary["patched_directory_boot_acceptance"] is True
assert boundary["runtime_title_rendering"] is True
assert boundary["runtime_3d_rendering"] is True
assert boundary["controller_or_keyboard_navigation_proved"] is False
assert boundary["full_retail_frontend_reached"] is False
assert boundary["patched_draft_logo_visible"] is False
assert boundary["franchise_screen_reachable"] is False
assert boundary["hidden_franchise_mode_proved"] is False

artifact_dir = root / "reports/cut_content/apf_nfl_lineage/runtime_validation"
expected_files = {
    "franchise_draft_logo_patch_manifest.json",
    "patched_attract_stadium.png",
    "patched_title_screen.png",
    "source_tree_after.sha256",
    "source_tree_before.sha256",
    "xenia_canary_boot_excerpt.log",
}
assert {path.name for path in artifact_dir.iterdir() if path.is_file()} == expected_files
assert (root / "docs/research/apf_xenia_patch_runtime.md").is_file()

print(
    "APF_XENIA_PATCH_RUNTIME_VALIDATION_PASS "
    "boot_acceptance=yes title=yes attract_3d=yes target_visible=no "
    "source_unchanged=yes"
)
PY
