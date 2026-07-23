#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

python3 - "$root" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tomllib

from PIL import Image


root = Path(sys.argv[1])
report_path = root / "reports/assets/nfl2k5_uniform_xemu_runtime.json"
report = json.loads(report_path.read_text())


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def check_artifact(record: dict[str, str]) -> Path:
    path = root / record["path"]
    assert path.is_file(), path
    assert digest(path) == record["sha256"], path
    return path


assert report["schema"] == "nfl2k5_uniform_xemu_runtime/v1"
assert report["captured_at"] == "2026-07-10"
scope = report["scope"]
assert scope == {
    "title": "ESPN NFL 2K5",
    "platform": "original Xbox",
    "target_team": "Detroit Lions",
    "target_resource": "09H0.IFF",
    "target_variant": "current HOME",
    "edited_field": "Unif color_word_1",
    "retail_source_modified": False,
    "layout_identical_copy_only_xiso": True,
}

tested = report["artifact_under_test"]
assert tested["size"] == 6_300_499_968
assert tested["sha256"] == "2f0ce4d4ac26c864a274c47f7147c45df1ecbf22d05d169f3940706eb64f3702"
assert tested["retail_source_sha256"] == "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
assert tested["changed_byte_count"] == 3
assert tested["changed_zero_based_offsets"] == [5011470420, 5011470421, 5011470422]
assert tested["source_color_word_1"] == "0xff385aaf"
assert tested["donor_color_word_1"] == "0xff881a1c"
assert tested["donor_resource"] == "27H0.IFF"
assert tested["target_complete_unif_body_equals_pinned_retail_donor"] is True
assert tested["all_other_image_bytes_identical"] is True

writer_path = check_artifact(tested["writer_manifest"])
writer = json.loads(writer_path.read_text())
assert writer["schema"] == "nfl2k5_uniform_home_donor_xiso_direct_patch/v1"
assert writer["output"]["path"] == tested["path_at_run"]
assert writer["output"]["sha256"] == tested["sha256"]
assert writer["output"]["size"] == tested["size"]
patch = writer["patch"]
assert patch["actual_changed_byte_count"] == tested["changed_byte_count"]
assert patch["actual_changed_byte_offsets"] == tested["changed_zero_based_offsets"]
assert patch["allowed_changed_byte_offsets"] == tested["changed_zero_based_offsets"]
assert patch["all_other_image_bytes_identical"] is True
assert patch["target"]["resource"] == "09H0.IFF"
assert patch["target"]["source_color_word_1"] == tested["source_color_word_1"]
assert patch["target"]["patched_color_word_1"] == tested["donor_color_word_1"]
assert patch["donor"]["resource"] == tested["donor_resource"]
assert patch["donor"]["color_word_1"] == tested["donor_color_word_1"]
assert patch["target_complete_body_equals_pinned_donor"] is True
assert writer["xdvdfs"]["tree_identical_after_patch"] is True
assert writer["xdvdfs"]["all_sector_extents_preserved"] is True
assert tested["writer_manifest"]["runtime_fields_superseded"] is True

runtime_image = Path(tested["path_at_run"])
assert runtime_image.is_file()
assert runtime_image.stat().st_size == tested["size"]
assert digest(runtime_image) == tested["sha256"]
with runtime_image.open("rb") as stream:
    stream.seek(tested["changed_zero_based_offsets"][0])
    assert stream.read(3) == bytes.fromhex("1c1a88")

runtime = report["runtime"]
assert runtime["emulator"] == "xemu"
assert runtime["version"] == "0.8.135"
assert runtime["commit"] == "6318bb112091635ef908255019e4d42956bc5fa8"
assert runtime["executable_sha256"] == "360b857b2b0047d338d3530e55dd8995bfee50bbca40d242b5cc2a13df69504a"
assert runtime["gpu"] == "NVIDIA GeForce RTX 2080 Ti"
assert runtime["gpu_driver"] == "580.159.03"
assert runtime["window_size"] == [1280, 720]
assert runtime["surface_scale"] == 2
assert runtime["port1_driver"] == "usb-xbox-gamepad"
assert runtime["port1_binding"] == "keyboard"
assert runtime["isolated_hdd"]["distinct_from_live_hdd_inode"] is True
assert runtime["isolated_hdd"]["inode_at_run"] != report["live_state_guard"]["live_hdd_inode"]
assert runtime["isolated_firmware_and_eeprom_clones"] is True
assert runtime["single_xemu_process_only"] is True
assert runtime["shutdown"] == {
    "method": "WM_DELETE_WINDOW through tools/x11_window.py",
    "forced_kill_used": False,
    "process_remaining_after_close": False,
    "graceful": True,
}

config_path = root / runtime["isolated_config"]["path"]
assert digest(config_path) == runtime["isolated_config"]["sha256_after_run"]
config = tomllib.loads(config_path.read_text())
assert config["input"]["bindings"] == {
    "port1_driver": "usb-xbox-gamepad",
    "port1": "keyboard",
}
assert config["display"]["quality"]["surface_scale"] == 2
assert config["display"]["window"]["startup_size"] == "1280x720"
assert config["sys"]["files"]["dvd_path"] == tested["path_at_run"]
assert config["sys"]["files"]["hdd_path"] == runtime["isolated_hdd"]["path_at_run"]

stdout_path = check_artifact(runtime["launch_stdout"])
stderr_path = check_artifact(runtime["launch_stderr"])
stdout = stdout_path.read_text()
assert f"media=cdrom,file={tested['path_at_run']}" in stdout
stderr = stderr_path.read_text()
for required in (
    f"config path: {config['sys']['files']['bootrom_path'].rsplit('/', 1)[0]}/xemu.toml",
    "xemu_version: 0.8.135",
    "xemu_commit: 6318bb112091635ef908255019e4d42956bc5fa8",
    "CPU: AMD Ryzen 9 3950X 16-Core Processor",
    "GL_RENDERER: NVIDIA GeForce RTX 2080 Ti/PCIe/SSE2",
    "GL_VERSION: 4.0.0 NVIDIA 580.159.03",
):
    assert required in stderr
assert "base path: /home/noah/.var/app/app.xemu.xemu/data/xemu/xemu/" in stderr

guard = report["live_state_guard"]
assert guard["live_config_sha256_before"] == guard["live_config_sha256_after"]
assert guard["live_config_unchanged"] is True
assert guard["live_hdd_sha256_before"] == guard["live_hdd_sha256_after"]
assert guard["live_hdd_unchanged"] is True
assert guard["live_state_used_by_run"] is False
live_config = Path(guard["live_config_path"])
live_hdd = Path(guard["live_hdd_path"])
assert digest(live_config) == guard["live_config_sha256_after"]
assert live_hdd.stat().st_ino == guard["live_hdd_inode"]
assert live_hdd.stat().st_size == guard["live_hdd_size"]
assert digest(live_hdd) == guard["live_hdd_sha256_after"]

acceptance = report["acceptance"]
acceptance_path = check_artifact(acceptance["frame"])
with Image.open(acceptance_path) as image:
    assert image.size == tuple(acceptance["frame"]["dimensions"]) == (1280, 720)
    assert image.format == "PNG"
assert acceptance["exact_patched_xiso_named_as_cdrom_in_launch_log"] is True
assert acceptance["title_rendered"] is True
assert acceptance["demo_mode_gameplay_rendered"] is True
assert acceptance["modified_disc_runtime_accepted"] is True
assert acceptance["archive_and_xdvdfs_acceptance_for_this_artifact"] is True

audit = report["input_focus_audit"]
transcript_path = check_artifact(audit["transcript"])
key_helper = check_artifact(audit["key_helper"])
window_helper = check_artifact(audit["window_helper"])
assert key_helper.stat().st_mode & 0o111
assert window_helper.stat().st_mode & 0o111
key_source = key_helper.read_text()
for required in (
    "_NET_ACTIVE_WINDOW",
    "set_input_focus",
    "get_input_focus",
    "focus verification failed",
    "xtest.fake_input",
    "focus_before",
    "focus_after",
):
    assert required in key_source

transcript = json.loads(transcript_path.read_text())
assert transcript["schema"] == "nfl2k5_uniform_xemu_input_focus_transcript/v1"
assert transcript["helper"]["path"] == audit["key_helper"]["path"]
assert transcript["helper"]["sha256"] == audit["key_helper"]["sha256"]
assert transcript["focus_invariant"] == {
    "required": "focus_before == target == focus_after",
    "value_for_every_ordered_input": "0x3600013",
    "satisfied": True,
}
ordered = transcript["ordered_inputs"]
assert [entry["sequence"] for entry in ordered] == list(range(1, 8))
assert [entry["command"] for entry in ordered] == [
    "tools/x11_key.py Return --duration 0.20 --window 'xemu |'",
    "tools/x11_key.py Return --duration 0.20 --window 'xemu |'",
    "tools/x11_key.py Return --duration 0.20 --window 'xemu |'",
    "tools/x11_key.py a --duration 0.20 --window 'xemu |'",
    "tools/x11_key.py Return --duration 0.20 --window 'xemu |'",
    "tools/x11_key.py Return --duration 0.35 --window 'xemu |'",
    "tools/x11_key.py b --duration 0.30 --window 'xemu |'",
]
for entry in ordered:
    stdout_line = entry["stdout"]
    assert "focus_before=0x3600013" in stdout_line
    assert "target=0x3600013" in stdout_line
    assert "focus_after=0x3600013" in stdout_line
    for path_key, hash_key in (
        ("starting_frame", "starting_frame_sha256"),
        ("observed_frame", "observed_frame_sha256"),
        ("followup_frame", "followup_frame_sha256"),
    ):
        if path_key in entry:
            frame_path = root / entry[path_key]
            assert digest(frame_path) == entry[hash_key]
            with Image.open(frame_path) as image:
                assert image.size == (1280, 720)
assert transcript["bounded_result"] == {
    "deterministic_demo_to_main_route": True,
    "deterministic_team_select_route": False,
    "team_select_reached_in_this_focus_audited_segment": False,
    "reason_stopped": "The bounded face-button probes did not establish a deterministic Quick Game activation sequence.",
}
assert audit["all_ordered_inputs_focus_verified"] is True
assert audit["deterministic_demo_to_main_route"] is True
assert audit["deterministic_team_select_route"] is False
assert audit["team_select_reached_in_focus_audited_segment"] is False

for artifact in report["artifacts"].values():
    artifact_path = check_artifact(artifact)
    with Image.open(artifact_path) as image:
        assert image.size == (1280, 720)

ownership_path = root / report["visual_semantics"]["static_ownership_report"]
ownership = json.loads(ownership_path.read_text())
assert ownership["existing_runtime_context"]["three_byte_donor_xiso_sha256"] == tested["sha256"]
assert ownership["existing_runtime_context"]["demo_mode_frame_sha256"] == acceptance["frame"]["sha256"]
assert ownership["color_word_1"]["semantic_owner"] == "HI_turtleneck packed tint"
assert ownership["color_word_1"]["selector_mapping"]["3"] == "read color_word_1 and write it"
assert ownership["jersey_diffuse_conclusion"]["color_word_1_reaches_UNIF_jersey"] is False

visual = report["visual_semantics"]
assert visual["observed_lions_jersey_remained_blue"] is True
assert visual["edited_field_is_jersey_diffuse"] is False
assert visual["edited_field_static_owner"] == "conditional HI_turtleneck packed tint"
assert visual["target_current_home_package_proved_on_acceptance_frame"] is False
assert visual["edited_field_visible_on_acceptance_frame"] is False
assert visual["controlled_visual_change_observed"] is False
assert visual["target_binding_proved"] is False
assert visual["runtime_visibility_proved"] is False

assert report["outcome"] == {
    "classification": "modified_disc_gameplay_acceptance_only",
    "copied_xiso_boots_to_rendered_gameplay": True,
    "archive_rejection_observed": False,
    "patch_rejection_observed": False,
    "crash_observed": False,
    "title_or_attract_frames_classified_as_crash": False,
    "visible_material_effect_claimed": False,
    "matched_target_capture_complete": False,
    "hardware_validation": False,
}

artifact_dir = root / "reports/assets/nfl2k5_uniform_xemu_runtime"
assert {path.name for path in artifact_dir.iterdir() if path.is_file()} == {
    "donor-a-probe-title-0p4s.png",
    "donor-b-probe-title-0p5s.png",
    "donor-b-probe-title-2s.png",
    "donor-demo-active-before-route.png",
    "donor-game-45s.png",
    "donor-main-start-probe-3s.png",
    "donor-route-main-menu-1p5s.png",
    "donor-route-title-0p8s.png",
    "donor-title-retry-main-menu-2s.png",
    "input_focus_transcript.json",
    "isolated_xemu.toml",
    "writer_manifest_at_run.json",
    "xemu.stderr.txt",
    "xemu.stdout.txt",
}
assert (root / "docs/research/nfl_uniform_xemu_runtime.md").is_file()

print(
    "NFL_UNIFORM_XEMU_RUNTIME_PASS "
    "modified_disc_gameplay=yes archive_acceptance=yes "
    "focus_demo_to_main=yes team_select_route=no "
    "target_binding=no visible_effect=no live_state=unchanged "
    "xemu_relaunched=no"
)
PY
