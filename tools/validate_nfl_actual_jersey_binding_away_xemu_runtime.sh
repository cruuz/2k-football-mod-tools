#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

PYTHONPATH=tools python3 tools/nfl2k5_uniform_jersey_png_workflow_verify.py \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --output-xiso /media/noah/Storage/.codex-tmp/nfl2k5-actual-jersey-binding-away-probe-20260711/ESPN-NFL-2K5-Detroit-AWAY-CODEX-MOD-binding-probe.xiso.iso \
  --manifest /media/noah/Storage/.codex-tmp/nfl2k5-actual-jersey-binding-away-probe-20260711/workflow_manifest.json \
  --target-code 09 \
  --target-side A \
  --target-variant 0 \
  --clean-png reports/assets/nfl2k5_lions_diagnostic_codex_mod.png \
  --previews /media/noah/Storage/.codex-tmp/nfl2k5-actual-jersey-binding-away-probe-20260711/previews \
  >/dev/null

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
report = json.loads(
    (root / "reports/assets/nfl2k5_actual_jersey_binding_away_xemu_runtime.json").read_text()
)


@lru_cache(maxsize=None)
def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def frozen(record: dict[str, object], path_key: str = "path") -> Path:
    path = root / str(record[path_key])
    assert path.is_file(), path
    assert digest(path) == record["sha256"], path
    return path


def frozen_image(record: dict[str, object]) -> Path:
    path = frozen(record)
    with Image.open(path) as image:
        assert image.format == "PNG", path
        assert list(image.size) == record["dimensions"], path
    return path


def saturated_counts(image: Image.Image, crop=None) -> dict[str, int]:
    if crop is not None:
        image = image.crop(tuple(crop))
    pixels = list(image.convert("RGB").getdata())
    return {
        "magenta": sum(r >= 200 and g <= 80 and b >= 200 for r, g, b in pixels),
        "cyan": sum(r <= 80 and g >= 180 and b >= 180 for r, g, b in pixels),
        "yellow": sum(r >= 200 and g >= 200 and b <= 80 for r, g, b in pixels),
        "red": sum(r >= 200 and g <= 80 and b <= 80 for r, g, b in pixels),
        "green": sum(r <= 80 and g >= 160 and b <= 80 for r, g, b in pixels),
    }


def ocr_crop(path: Path, crop: tuple[int, int, int, int], psm: int) -> str:
    with Image.open(path) as image:
        sample = image.convert("RGB").crop(crop)
        sample = sample.resize((sample.width * 2, sample.height * 2))
    payload = io.BytesIO()
    sample.save(payload, format="PNG")
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", str(psm)],
        input=payload.getvalue(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return " ".join(result.stdout.decode("utf-8", "replace").upper().split())


def ocr_full(path: Path, psm: int) -> str:
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "--psm", str(psm)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return " ".join(result.stdout.decode("utf-8", "replace").upper().split())


assert report["schema"] == "nfl2k5_actual_jersey_binding_away_xemu_runtime/v1"
assert report["captured_at"] == "2026-07-11"
assert report["scope"] == {
    "title": "ESPN NFL 2K5",
    "platform": "original Xbox",
    "target_team": "Detroit Lions",
    "target_resource": "09A0.IFF",
    "target_variant": "current AWAY",
    "target_chunk_index": 1,
    "target_textures": ["jersey00", "jersey00_mud"],
    "diagnostic_text": "CODEX MOD",
    "retail_source_modified": False,
    "hardware_validation": False,
}

diagnostic = report["diagnostic_input"]
diagnostic_path = root / diagnostic["path"]
assert digest(diagnostic_path) == diagnostic["sha256"] == (
    "6ae65b7c4f982fbadb6da20444b21d7a2bb3c13f28a84b22c612967dc8a8f3c8"
)
with Image.open(diagnostic_path) as image:
    assert list(image.size) == diagnostic["dimensions"] == [512, 256]
    assert saturated_counts(image) == diagnostic["saturated_pixel_counts"] == {
        "magenta": 26624,
        "cyan": 26624,
        "yellow": 23552,
        "red": 4096,
        "green": 7168,
    }

artifact = report["artifact_under_test"]
xiso = Path(artifact["path_at_run"])
assert xiso.is_file()
assert xiso.stat().st_ino == artifact["inode"] == 98980516
assert xiso.stat().st_size == artifact["size"] == 6_300_499_968
assert artifact["sha256_before"] == artifact["sha256_after"] == (
    "ac2a6556b9a6c77724a770c6665d5ea2d4b639e015fea468631a2faa8653b855"
)
assert digest(xiso) == artifact["sha256_after"]
assert artifact["unchanged_by_runtime"] is True

source = artifact["retail_source"]
source_path = Path(source["path"])
assert source_path.stat().st_size == source["size"] == 6_300_499_968
assert digest(source_path) == source["sha256_before_and_after"] == (
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
assert source["opened_by_runtime"] is False
assert source["modified"] is False

writer_record = artifact["writer_manifest"]
writer_path = Path(writer_record["path_at_run"])
assert digest(writer_path) == writer_record["sha256"] == (
    "420977b306b14ec1eb1457dab71c0a9c7bc95414b84aeb86c1ce9df4141b3836"
)
writer = json.loads(writer_path.read_text())
assert writer["schema"] == "nfl2k5_uniform_jersey_png_workflow/v2"
assert writer["target"]["selector"] == "09A0"
assert writer["target"]["outer_index"] == 4002
assert writer["target"]["chunk_index"] == 1
assert writer["target"]["absolute_span_offset"] == 4_718_884_976
assert writer["target"]["span_size"] == 79_120
assert writer["target"]["stored_size"] == 79_088
assert writer["output"]["xiso_sha256"] == artifact["sha256_after"]
assert writer["output"]["xiso_inode"] == artifact["inode"]
assert writer["patch"]["actual_changed_byte_count"] == 74_703
assert writer["patch"]["relative_changed_run_count"] == 3_604
assert writer["patch"]["replacement_span_sha256"] == (
    "390c36805ed9ad7c9fbd0d330873bf93cf728cc270a73375fa3460d3967d2f5b"
)
assert writer["patch"]["all_other_image_bytes_identical"] is True
assert writer["xdvdfs"]["tree_identical_after_patch"] is True
assert writer["xdvdfs"]["all_sector_extents_preserved"] is True
assert writer["claims"]["originals_modified"] is False
assert writer["claims"]["xemu_started"] is False
assert writer_record["creation_time_runtime_flags_superseded"] is True

runtime = report["runtime"]
assert runtime["emulator"] == "xemu"
assert runtime["version"] == "0.8.135"
assert runtime["commit"] == "6318bb112091635ef908255019e4d42956bc5fa8"
assert digest(Path(runtime["executable_path"])) == runtime["executable_sha256"] == (
    "360b857b2b0047d338d3530e55dd8995bfee50bbca40d242b5cc2a13df69504a"
)
assert runtime["video_driver"] == "x11"
assert runtime["audio_driver"] == "dummy"
assert runtime["gl_vendor"] == "Mesa"
assert runtime["nested_display"]["display"] == ":99"
assert runtime["nested_display"]["captured_client_size"] == [1280, 672]
assert runtime["input"]["sdl_guid"] == "030081b85e0400008e02000014010000"
assert runtime["input"]["team_assignment_left_taps"] == 2
assert runtime["input"]["away_team_rt_pulses"] == 18

controller_path = frozen(runtime["input"]["controller_log"])
controller = controller_path.read_text()
assert "vendor=0x045e product=0x028e" in controller
assert controller.count("TAPPED LEFT 0.150") == 2
assert controller.count("TAPPED RT 0.150") == 18
assert controller.count("HOLD START") == 3
assert controller.rstrip().endswith("BYE")
assert runtime["shutdown"] == {
    "method": "WM_DELETE_WINDOW through tools/x11_window.py",
    "forced_kill_used": False,
    "xemu_process_remaining_after_close": False,
    "virtual_gamepad_log_ends_with_bye": True,
    "nested_display_terminated": True,
    "graceful": True,
}

isolation = report["isolation"]
config_record = isolation["config"]
config_path = root / config_record["frozen_after_path"]
assert digest(config_path) == config_record["after_sha256"]
config = tomllib.loads(config_path.read_text())
assert config["input"]["bindings"] == {
    "port1_driver": "usb-xbox-gamepad",
    "port1": "030081b85e0400008e02000014010000",
}
assert config["sys"]["files"]["dvd_path"] == artifact["path_at_run"]

overlay_record = isolation["hdd_overlay"]
overlay = Path(overlay_record["path_at_run"])
assert config["sys"]["files"]["hdd_path"] == str(overlay)
assert overlay.stat().st_ino == overlay_record["inode"]
assert overlay.stat().st_size == overlay_record["size_after"]
assert digest(overlay) == overlay_record["sha256_after"]
backing = Path(overlay_record["backing_path"])
assert backing.stat().st_ino == overlay_record["backing_inode"]
assert backing.stat().st_size == overlay_record["backing_size"]
assert digest(backing) == overlay_record["backing_sha256_before_and_after"]
assert overlay_record["backing_unchanged"] is True
qemu_info = subprocess.run(
    ["qemu-img", "info", "--backing-chain", str(overlay)],
    check=True,
    capture_output=True,
    text=True,
).stdout
assert str(backing) in qemu_info
qemu_check = subprocess.run(
    ["qemu-img", "check", str(overlay)],
    check=True,
    capture_output=True,
    text=True,
).stdout
assert "No errors were found" in qemu_check

run_dir = Path(isolation["run_directory"])
firmware = isolation["firmware"]
assert digest(run_dir / "mcpx_1.0.bin") == firmware["mcpx_sha256"]
assert digest(run_dir / "Complex_4627.bin") == firmware["flashrom_sha256"]
assert digest(run_dir / "eeprom.bin") == firmware["eeprom_sha256"]
assert isolation["live_state_used_by_run"] is False

guard = report["live_state_guard"]
live_config = Path(guard["live_config_path"])
live_hdd = Path(guard["live_hdd_path"])
assert live_config.stat().st_ino == guard["live_config_inode"]
assert live_config.stat().st_size == guard["live_config_size"]
assert live_hdd.stat().st_ino == guard["live_hdd_inode"]
assert live_hdd.stat().st_size == guard["live_hdd_size"]
assert guard["live_config_sha256_before"] == guard["live_config_sha256_after"]
assert guard["live_hdd_sha256_before"] == guard["live_hdd_sha256_after"]
assert digest(live_config) == guard["live_config_sha256_after"]
assert digest(live_hdd) == guard["live_hdd_sha256_after"]
assert guard["live_config_unchanged"] is True
assert guard["live_hdd_unchanged"] is True

images = {
    name: frozen_image(record)
    for name, record in report["observations"].items()
}
assert "PRESS START" in ocr_crop(images["title"], (160, 0, 1120, 180), 11)
team_text = ocr_crop(images["team_select_torso"], (250, 75, 1030, 155), 6)
assert team_text.count("CURRENT UNIFORM") == 2, team_text
assert "GIANTS" in team_text, team_text
coin_text = ocr_crop(images["coin_toss"], (250, 370, 1025, 565), 6)
assert "COIN TOSS" in coin_text, coin_text
full_coin_text = ocr_full(images["coin_toss"], 11)
assert "LIONS CALL IT" in full_coin_text, full_coin_text
live_text = ocr_crop(images["live_presnap"], (200, 25, 1070, 180), 6)
assert "DET" in live_text and "NYG" in live_text, live_text

for key in ("team_select_torso", "coin_toss", "live_presnap"):
    record = report["observations"][key]
    audit = record["saturated_color_audit"]
    with Image.open(images[key]) as image:
        crop = tuple(audit["crop"])
        assert (crop[2] - crop[0]) * (crop[3] - crop[1]) == audit["crop_pixels"]
        counts = saturated_counts(image, crop)
    assert counts == {name: audit[name] for name in (
        "magenta", "cyan", "yellow", "red", "green"
    )}
    assert counts["magenta"] == counts["cyan"] == counts["yellow"] == 0
    assert record["diagnostic_visible"] is False

outcome = report["outcome"]
assert outcome["classification"] == (
    "away_tset_not_visible_in_current_uniform_team_select_coin_toss_or_gameplay"
)
for key in (
    "modified_xiso_runtime_accepted",
    "title_booted",
    "main_menu_reached",
    "deterministic_team_select_reached",
    "lions_at_giants_current_uniform_reached",
    "detroit_away_preview_visible",
    "detroit_away_coin_toss_players_visible",
    "detroit_away_live_players_visible",
):
    assert outcome[key] is True, key
for key in (
    "diagnostic_visible_in_team_select",
    "diagnostic_visible_at_coin_toss",
    "diagnostic_visible_in_gameplay",
    "visible_sampling_of_patched_09A0_span_observed",
    "runtime_static_binding_contradiction_resolved",
    "png_import_corruption_observed",
    "archive_rejection_observed",
    "matched_route_crash_observed",
    "live_state_changed",
    "retail_source_modified",
    "hardware_validation",
):
    assert outcome[key] is False, key
assert all(item.startswith("PORTME(") for item in report["portme"])
PY

echo 'NFL_ACTUAL_JERSEY_BINDING_AWAY_XEMU_RUNTIME_VALIDATION_PASS target=09A0 side=AWAY matchup=Lions-at-Giants current=yes team_select=yes coin_toss=yes gameplay=yes diagnostic_visible=false direct_sampling_observed=false contradiction_resolved=false xemu=0.8.135 live_state=unchanged original=unchanged hardware=false'
