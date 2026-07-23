#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

python3 - "$root" <<'PY'
from __future__ import annotations

import hashlib
import io
import json
from functools import lru_cache
from pathlib import Path
import subprocess
import sys
import tomllib

from PIL import Image


root = Path(sys.argv[1])


@lru_cache(maxsize=None)
def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def frozen(record: dict[str, object]) -> Path:
    path = root / str(record["path"])
    assert path.is_file(), path
    assert digest(path) == record["sha256"], path
    return path


def frozen_image(record: dict[str, object]) -> Path:
    path = frozen(record)
    with Image.open(path) as image:
        assert image.format == "PNG", path
        assert list(image.size) == record["dimensions"], path
    return path


def ocr(image: Image.Image, psm: int = 11) -> str:
    payload = io.BytesIO()
    image.save(payload, format="PNG")
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", str(psm)],
        input=payload.getvalue(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return result.stdout.decode("utf-8", "replace")


def full_ocr(path: Path, psm: int = 11) -> str:
    with Image.open(path) as image:
        return ocr(image.convert("RGB"), psm)


def top_ocr(path: Path) -> str:
    with Image.open(path) as image:
        crop = image.convert("RGB").crop((220, 55, 1070, 155))
        crop = crop.resize((crop.width * 2, crop.height * 2))
        return ocr(crop, 6)


donor = json.loads(
    (root / "reports/assets/nfl2k5_jersey_tset_xemu_runtime.json").read_text()
)
assert donor["schema"] == "nfl2k5_jersey_tset_xemu_runtime/v2"
assert donor["captured_at"] == "2026-07-11"
assert donor["scope"] == {
    "title": "ESPN NFL 2K5",
    "platform": "original Xbox",
    "target_team": "Detroit Lions",
    "target_resource": "09H0.IFF",
    "target_variant": "current HOME",
    "target_chunk": "TSET chunk 1",
    "target_textures": ["jersey00", "jersey00_mud"],
    "donor_team": "Atlanta Falcons",
    "donor_resource": "01A0.IFF",
    "donor_variant": "AWAY",
    "retail_source_modified": False,
    "layout_identical_copy_only_xiso": True,
}

tested = donor["artifact_under_test"]
tested_path = Path(tested["path_at_run"])
assert tested_path.is_file()
assert tested_path.stat().st_size == tested["size"] == 6_300_499_968
assert tested["sha256_before"] == tested["sha256_after"] == (
    "502b41d2d7813549342861c92e17b9ff1bc83a8f0cb5995401e9abaeb2b288f5"
)
assert digest(tested_path) == tested["sha256_after"]
assert tested["unchanged_by_runtime"] is True

writer_path = frozen(tested["writer_manifest"])
writer = json.loads(writer_path.read_text())
assert writer["schema"] == "nfl2k5_jersey_tset_donor_xiso_direct_patch/v1"
assert writer["output"]["path"] == tested["path_at_run"]
assert writer["output"]["sha256"] == tested["sha256_after"]
patch = tested["patch"]
writer_patch = writer["patch"]
assert writer_patch["absolute_patch_start"] == patch["absolute_span_start"] == 5_011_470_448
assert writer_patch["absolute_patch_end_exclusive"] == patch["absolute_span_end_exclusive"] == 5_011_545_168
assert writer_patch["target_complete_span_size"] == patch["complete_span_size"] == 74_720
assert writer_patch["actual_changed_byte_count"] == patch["actual_changed_byte_count"] == 73_304
assert writer_patch["target"]["resource"] == "09H0.IFF"
assert writer_patch["donor"]["resource"] == "01A0.IFF"
assert writer_patch["target"]["patched_decoded_sha256"] == writer_patch["donor"]["decoded_sha256"]
assert writer["xdvdfs"]["tree_identical_after_patch"] is True
assert writer["xdvdfs"]["all_sector_extents_preserved"] is True

runtime = donor["runtime"]
assert runtime["emulator"] == "xemu"
assert runtime["version"] == "0.8.135"
assert runtime["commit"] == "6318bb112091635ef908255019e4d42956bc5fa8"
assert runtime["executable_sha256"] == (
    "360b857b2b0047d338d3530e55dd8995bfee50bbca40d242b5cc2a13df69504a"
)
assert runtime["input"]["game_input_sent"] is True
assert runtime["input"]["sdl_guid"] == "030081b85e0400008e02000014010000"
controller_path = frozen(runtime["input"]["controller_log"])
controller = controller_path.read_text()
assert "vendor=0x045e product=0x028e" in controller
assert "HOLD START" in controller
assert controller.rstrip().endswith("BYE")
guid_path = frozen(runtime["input"]["sdl_guid_record"])
assert "guid=030081b85e0400008e02000014010000" in guid_path.read_text()

isolation = donor["isolation"]
config_path = root / isolation["config"]["after_path"]
assert digest(config_path) == isolation["config"]["after_sha256"]
config = tomllib.loads(config_path.read_text())
assert config["input"]["bindings"] == {
    "port1_driver": "usb-xbox-gamepad",
    "port1": "030081b85e0400008e02000014010000",
}
assert config["display"]["quality"]["surface_scale"] == 2
assert config["sys"]["files"]["dvd_path"] == tested["path_at_run"]
assert config["sys"]["files"]["hdd_path"] == isolation["hdd"]["path_at_run"]
donor_hdd = Path(isolation["hdd"]["path_at_run"])
assert donor_hdd.stat().st_ino == isolation["hdd"]["inode"]
assert donor_hdd.stat().st_size == isolation["hdd"]["size"]
assert digest(donor_hdd) == isolation["hdd"]["after_sha256"]

guard = donor["live_state_guard"]
live_config = Path(guard["live_config_path"])
live_hdd = Path(guard["live_hdd_path"])
assert live_config.stat().st_ino == guard["live_config_inode"]
assert live_hdd.stat().st_ino == guard["live_hdd_inode"]
assert live_hdd.stat().st_size == guard["live_hdd_size"]
assert guard["live_config_sha256_before"] == guard["live_config_sha256_after"]
assert guard["live_hdd_sha256_before"] == guard["live_hdd_sha256_after"]
assert digest(live_config) == guard["live_config_sha256_after"]
assert digest(live_hdd) == guard["live_hdd_sha256_after"]
assert guard["live_config_unchanged"] is True
assert guard["live_hdd_unchanged"] is True

donor_images = {
    name: frozen_image(record)
    for name, record in donor["observations"].items()
}
exact_donor_ocr = full_ocr(donor_images["exact_matchup"])
for fragment in ("JAGUARS", "LIONS", "CURRENT UNIFORM"):
    assert fragment in exact_donor_ocr.upper(), (fragment, exact_donor_ocr)
assert donor["observations"]["lions_preview_contact"]["sample_count"] == 10
assert donor["observations"]["lions_torso"]["falcons_away_donor_pattern_visible"] is False
assert donor["outcome"]["classification"] == "donor_tset_not_visible_in_current_uniform_team_select"
assert donor["outcome"]["jersey00_binding_falsified_for_team_select_preview"] is True
assert donor["outcome"]["on_field_binding_tested"] is False


custom = json.loads(
    (root / "reports/assets/nfl2k5_lions_png_import_xemu_runtime.json").read_text()
)
assert custom["schema"] == "nfl2k5_lions_png_import_xemu_runtime/v1"
assert custom["captured_at"] == "2026-07-11"
assert custom["scope"]["target_resource"] == "09H0.IFF"
assert custom["scope"]["target_chunk_index"] == 1
assert custom["scope"]["target_textures"] == ["jersey00", "jersey00_mud"]
assert custom["scope"]["diagnostic_text"] == "CODEX MOD"

diagnostic = custom["diagnostic_input"]
diagnostic_path = root / diagnostic["path"]
assert digest(diagnostic_path) == diagnostic["sha256"]
with Image.open(diagnostic_path) as image:
    assert list(image.size) == diagnostic["dimensions"] == [512, 256]
assert digest(root / diagnostic["tset_path"]) == diagnostic["tset_sha256"]
frozen(diagnostic["import_manifest"])

custom_tested = custom["artifact_under_test"]
custom_xiso = Path(custom_tested["path_at_run"])
assert custom_xiso.stat().st_ino == custom_tested["inode"]
assert custom_xiso.stat().st_size == custom_tested["size"] == 6_300_499_968
assert custom_tested["sha256_before"] == custom_tested["sha256_after"] == (
    "b9f47fcec3e284a12ea30f390035dd29f97fa62507330ba3ff30391cf4e10ae6"
)
assert digest(custom_xiso) == custom_tested["sha256_after"]
custom_writer_path = frozen(custom_tested["writer_manifest"])
custom_writer = json.loads(custom_writer_path.read_text())
assert custom_writer["schema"] == "nfl2k5_tset_png_import_xiso_direct_patch/v1"
assert custom_writer["output"]["path"] == custom_tested["path_at_run"]
assert custom_writer["output"]["sha256"] == custom_tested["sha256_after"]
assert custom_writer["patch"]["absolute_span_offset"] == custom_tested["patch"]["absolute_span_offset"]
assert custom_writer["patch"]["span_size"] == custom_tested["patch"]["span_size"] == 74_720
assert custom_writer["patch"]["actual_changed_byte_count"] == 70_333
assert custom_writer["patch"]["replacement_span_sha256"] == diagnostic["tset_sha256"]
assert custom_writer["patch"]["all_other_image_bytes_identical"] is True
assert custom_writer["xdvdfs"]["tree_identical_after_patch"] is True
assert custom_writer["xdvdfs"]["all_sector_extents_preserved"] is True

custom_runtime = custom["runtime"]
assert custom_runtime["version"] == "0.8.135"
assert custom_runtime["commit"] == "6318bb112091635ef908255019e4d42956bc5fa8"
assert digest(Path(custom_runtime["executable_path"])) == custom_runtime["executable_sha256"]
assert custom_runtime["video_driver"] == "x11"
assert custom_runtime["audio_driver"] == "dummy"
assert custom_runtime["gl_vendor"] == "Mesa"
assert custom_runtime["nested_display"]["display"] == ":99"
assert custom_runtime["nested_display"]["captured_client_size"] == [1280, 672]
assert custom_runtime["input"]["sdl_guid"] == "030081b85e0400008e02000014010000"
assert custom_runtime["input"]["title_prompt_detected_by_ocr_at_seconds"] == 146.8
assert custom_runtime["input"]["mapped_uniform_buttons"] == {
    "previous": "LB",
    "next": "RB",
}
assert custom_runtime["shutdown"] == {
    "method": "WM_DELETE_WINDOW through tools/x11_window.py",
    "forced_kill_used": False,
    "xemu_process_remaining_after_close": False,
    "virtual_gamepad_quit": True,
    "nested_display_terminated": True,
    "graceful": True,
}

custom_isolation = custom["isolation"]
custom_config_path = root / custom_isolation["config"]["frozen_after_path"]
assert digest(custom_config_path) == custom_isolation["config"]["after_sha256"]
custom_config = tomllib.loads(custom_config_path.read_text())
assert custom_config["input"]["bindings"] == {
    "port1_driver": "usb-xbox-gamepad",
    "port1": "030081b85e0400008e02000014010000",
}
assert custom_config["sys"]["files"]["dvd_path"] == custom_tested["path_at_run"]
overlay_record = custom_isolation["hdd_overlay"]
overlay = Path(overlay_record["path_at_run"])
assert overlay.stat().st_ino == overlay_record["inode"]
assert overlay.stat().st_size == overlay_record["size_after"]
assert digest(overlay) == overlay_record["sha256_after"]
assert digest(Path(overlay_record["backing_path"])) == overlay_record["backing_sha256_before_and_after"]
qemu_info = subprocess.run(
    ["qemu-img", "info", "--backing-chain", str(overlay)],
    check=True,
    capture_output=True,
    text=True,
).stdout
assert overlay_record["backing_path"] in qemu_info
qemu_check = subprocess.run(
    ["qemu-img", "check", str(overlay)],
    check=True,
    capture_output=True,
    text=True,
).stdout
assert "No errors were found" in qemu_check

firmware = custom_isolation["firmware"]
run_dir = Path(custom_isolation["run_directory"])
assert digest(run_dir / "mcpx_1.0.bin") == firmware["mcpx_sha256"]
assert digest(run_dir / "Complex_4627.bin") == firmware["flashrom_sha256"]
assert digest(run_dir / "eeprom.bin") == firmware["eeprom_sha256"]

custom_guard = custom["live_state_guard"]
assert custom_guard["live_config_path"] == guard["live_config_path"]
assert custom_guard["live_hdd_path"] == guard["live_hdd_path"]
assert custom_guard["live_config_sha256_before"] == custom_guard["live_config_sha256_after"]
assert custom_guard["live_hdd_sha256_before"] == custom_guard["live_hdd_sha256_after"]
assert digest(Path(custom_guard["live_config_path"])) == custom_guard["live_config_sha256_after"]
assert digest(Path(custom_guard["live_hdd_path"])) == custom_guard["live_hdd_sha256_after"]

custom_images = {
    name: frozen_image(record)
    for name, record in custom["observations"].items()
}
title_text = full_ocr(custom_images["title"])
settings_text = full_ocr(custom_images["settings"])
assert "PRESS START" in title_text.upper()
assert "SUCCESSFULLY LOADED SETTINGS SETTINGS1" in " ".join(settings_text.upper().split())
historical_text = top_ocr(custom_images["historical_uniform_cycle"])
assert "2000-2003 UNIFORM" in historical_text.upper(), historical_text
exact_custom_text = top_ocr(custom_images["exact_matchup"])
assert "JAGUARS" in exact_custom_text.upper()
assert custom["observations"]["lions_current_preview_contact"]["sample_count"] == 10
for name in (
    "lions_current_preview_contact",
    "historical_uniform_cycle",
    "exact_matchup",
    "coin_toss",
    "live_formation",
):
    assert custom["observations"][name]["codex_mod_visible"] is False
assert custom["observations"]["live_formation"]["visible_scoreboard"] == ["JAX", "DET"]

outcome = custom["outcome"]
assert outcome["classification"] == "target_tset_not_bound_to_observed_current_uniform_render_paths"
assert outcome["modified_xiso_runtime_accepted"] is True
assert outcome["jaguars_at_lions_current_uniform_reached"] is True
assert outcome["detroit_current_preview_visible"] is True
assert outcome["detroit_ingame_players_visible"] is True
assert outcome["codex_mod_visible_in_team_select"] is False
assert outcome["codex_mod_visible_in_gameplay"] is False
assert outcome["assumed_09H0_chunk1_jersey00_binding_falsified_for_observed_paths"] is True
assert outcome["archive_rejection_observed"] is False
assert outcome["matched_route_crash_observed"] is False
assert outcome["live_state_changed"] is False

for doc in (
    "docs/research/nfl_jersey_tset_xemu_runtime.md",
    "docs/research/nfl_lions_png_import_xemu_runtime.md",
):
    assert (root / doc).is_file()

print(
    "NFL_JERSEY_TSET_XEMU_RUNTIME_PASS "
    "donor_sha=502b41d2d7813549342861c92e17b9ff1bc83a8f0cb5995401e9abaeb2b288f5 "
    "png_xiso_sha=b9f47fcec3e284a12ea30f390035dd29f97fa62507330ba3ff30391cf4e10ae6 "
    "route=JAGUARS_at_LIONS current_uniform=yes preview_samples=10 "
    "coin_toss=yes live_formation=yes donor_pattern_visible=no codex_mod_visible=no "
    "binding=not_observed live_state=unchanged"
)
PY
