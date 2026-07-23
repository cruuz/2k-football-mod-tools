#!/usr/bin/env python3
"""Freeze the bounded xemu proof for NFL 2K5's ``score_buga`` writer.

The report joins an independently verified one-span copied XISO to a clean
window capture from xemu demo gameplay. It does not launch the emulator, alter
the build manifest, or generalize the observation to ``shield_espn``,
``digital_font``, scorebug geometry, or behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "nfl2k5_scorebug_xemu_runtime/v1"
SOURCE_XISO = ROOT / "ESPN NFL 2K5 (USA).xiso.iso"
PATCHED_XISO = (
    ROOT
    / "build/nfl2k5-scorebug-workflow-20260712/"
    "ESPN-NFL-2K5-scorebug-magenta.xiso.iso"
)
WORKFLOW = ROOT / "build/nfl2k5-scorebug-workflow-20260712/workflow.json"
FIXTURE = ROOT / "reports/assets/nfl2k5_scorebug_fixtures/score_buga_diagnostic.png"
SCREENSHOT = (
    ROOT
    / "reports/assets/nfl2k5_scorebug_xemu_runtime/score_buga-magenta-demo.png"
)
CONFIG = (
    ROOT
    / "reports/assets/nfl2k5_scorebug_xemu_runtime/isolated-xemu-after.toml"
)
CONTROL_SCREENSHOT = (
    ROOT
    / "reports/assets/nfl2k5_jersey_tset_xemu_runtime/"
    "automatic-gameplay-packers-patriots.png"
)
CONTROL_REPORT = ROOT / "reports/assets/nfl2k5_jersey_tset_xemu_runtime.json"
LOCAL_OVERLAY = (
    ROOT / ".codex-tmp/nfl2k5-scorebug-xemu-20260712/xbox_hdd.qcow2"
)
BACKING_OVERLAY = Path(
    "/media/noah/Storage/.codex-tmp/"
    "nfl2k5-away-cacheclear-xemu-20260711/xbox_hdd.qcow2"
)
FIRMWARE = {
    "bootrom": ROOT / ".codex-tmp/nfl2k5-scorebug-xemu-20260712/mcpx_1.0.bin",
    "flashrom": ROOT / ".codex-tmp/nfl2k5-scorebug-xemu-20260712/Complex_4627.bin",
    "eeprom": ROOT / ".codex-tmp/nfl2k5-scorebug-xemu-20260712/eeprom.bin",
}

EXPECTED = {
    SOURCE_XISO: (6_300_499_968, "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"),
    PATCHED_XISO: (6_300_499_968, "852901f79ae3368b1e0663106dffdfd5c3576c1ebd6579022c58277ed2a60a83"),
    WORKFLOW: (None, "2eaf73aa660d5f8ae785cd9214e52e76ee4adb0a493a0bbf45431b2aebc2eac4"),
    FIXTURE: (155, "c53c8b7a88cfc8f7bceab66eedca1bf4d6efc34f6d2414d413d24cdb7f4d9a00"),
    SCREENSHOT: (None, "0329e564429e44873fab70ceee5470673e8e92539533869b17498960039ca9e2"),
    CONFIG: (None, "4838a63bd0c6082d13e185cb9cd81488bbb892bf59b988629a79db79270b360b"),
    CONTROL_SCREENSHOT: (None, "7eed38a888286c0b64ba55fdbdf1a05637d26aec655e8b2c23da9d2321f766f9"),
    CONTROL_REPORT: (None, "373adb8171cd162139560579e74a80d46a3b29c42c08d820f49a3c78ea93f698"),
    LOCAL_OVERLAY: (79_495_168, "329d8a0bce5947b0e58dd2a4066180851fb9d53172e1567662c5aee73dbbcb9d"),
    BACKING_OVERLAY: (983_040, "43b6cea37aa0c5a02b50a822211842fe761da64cc2aaf75ecaad2fbdfe582ab4"),
    FIRMWARE["bootrom"]: (512, "e99e3a772bf5f5d262786aee895664eb96136196e37732fe66e14ae062f20335"),
    FIRMWARE["flashrom"]: (1_048_576, "34f1c8ded59116436065783f8ad2ef0939df3cbfc76277ec9e5c41bf9ccb93cd"),
    FIRMWARE["eeprom"]: (256, "52142e8293aada6343cb07c9aa816b60a6d84bddc230594269ec99f6d188b516"),
}


class RuntimeReportError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeReportError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return os.fspath(path)


def pin(path: Path) -> dict[str, Any]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"runtime input is not a regular non-symlink file: {path}")
    expected_size, expected_hash = EXPECTED[path]
    require(expected_size is None or supplied.st_size == expected_size,
            f"runtime input size differs: {path}")
    digest = sha256_file(path)
    require(digest == expected_hash, f"runtime input hash differs: {path}")
    current = path.stat(follow_symlinks=False)
    require((current.st_dev, current.st_ino, current.st_size) ==
            (supplied.st_dev, supplied.st_ino, supplied.st_size),
            f"runtime input changed while hashing: {path}")
    return {"path": display_path(path), "size": supplied.st_size, "sha256": digest}


def magenta_stats(path: Path, crop: tuple[int, int, int, int]) -> dict[str, Any]:
    with Image.open(path) as source:
        source.load()
        require(source.format == "PNG", f"runtime image is not PNG: {path}")
        image = source.convert("RGB")
    points: list[tuple[int, int]] = []
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = image.getpixel((x, y))
            if red >= 220 and green <= 60 and blue >= 180:
                points.append((x, y))
    bbox = None
    if points:
        bbox = [
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        ]
    crop_image = image.crop(crop)
    return {
        "dimensions": [image.width, image.height],
        "magenta_predicate": "r>=220,g<=60,b>=180",
        "magenta_pixel_count": len(points),
        "magenta_bbox_inclusive": bbox,
        "scorebug_crop": list(crop),
        "scorebug_crop_rgb_sha256": hashlib.sha256(crop_image.tobytes()).hexdigest(),
    }


def load_workflow() -> dict[str, Any]:
    raw = WORKFLOW.read_bytes()
    value = json.loads(raw)
    require(raw == (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
            "scorebug workflow manifest is not canonical JSON")
    target = value["input"]["import_manifest"]["target"]
    require(
        value["schema"] == "nfl2k5_scorebug_xiso_workflow/v1"
        and target["name"] == "score_buga"
        and target["outer_index"] == 346
        and target["chunk_index"] == 53
        and target["xiso_absolute_span_offset"] == 1_741_540_432
        and value["patch"]["actual_changed_byte_count"] == 2_169
        and value["patch"]["all_other_xiso_bytes_identical"] is True
        and value["xdvdfs"]["tree_identical_after_patch"] is True
        and value["xdvdfs"]["default_xbe_sha256"] ==
            "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
        "scorebug workflow target or independent proof differs",
    )
    return value


def generate() -> dict[str, Any]:
    workflow = load_workflow()
    runtime_image = magenta_stats(SCREENSHOT, (200, 50, 460, 205))
    control_image = magenta_stats(CONTROL_SCREENSHOT, (160, 40, 450, 215))
    fixture_image = magenta_stats(FIXTURE, (0, 0, 64, 64))
    require(runtime_image == {
        "dimensions": [1280, 672],
        "magenta_predicate": "r>=220,g<=60,b>=180",
        "magenta_pixel_count": 17_233,
        "magenta_bbox_inclusive": [211, 70, 441, 188],
        "scorebug_crop": [200, 50, 460, 205],
        "scorebug_crop_rgb_sha256":
            "f2b23c1702d7a8f17505170fe883b373e68e67095d7e3579bf8302e9052ee9ef",
    }, "runtime scorebug image metrics differ")
    require(control_image["dimensions"] == [1280, 720] and
            control_image["magenta_pixel_count"] == 0 and
            control_image["magenta_bbox_inclusive"] is None and
            control_image["scorebug_crop_rgb_sha256"] ==
                "998d0a3ca0e52fd395d18e557e712f617dd39005715b7b73791fb408ed436317",
            "retail-art control image metrics differ")
    require(fixture_image["dimensions"] == [64, 64] and
            fixture_image["magenta_pixel_count"] == 4_096 and
            fixture_image["magenta_bbox_inclusive"] == [0, 0, 63, 63],
            "score_buga fixture metrics differ")

    pinned = {display_path(path): pin(path) for path in EXPECTED}
    return {
        "schema": SCHEMA,
        "date": "2026-07-12",
        "scope": (
            "positive xemu runtime visibility for score_buga only; no claim for "
            "shield_espn, digital_font, SCNE geometry, behavior, or hardware"
        ),
        "build_proof": {
            "source_xiso": pinned[display_path(SOURCE_XISO)],
            "patched_xiso": pinned[display_path(PATCHED_XISO)],
            "workflow_manifest": pinned[display_path(WORKFLOW)],
            "target": {
                "name": "score_buga",
                "outer_index": 346,
                "chunk_index": 53,
                "xiso_absolute_span_offset": 1_741_540_432,
                "changed_byte_count": 2_169,
                "all_other_xiso_bytes_identical": True,
                "xdvdfs_tree_identical": True,
                "default_xbe_unchanged": True,
            },
            "builder_runtime_claim_was_false_at_build_time":
                workflow["claims"]["runtime_visibility_proved"] is False,
        },
        "runtime": {
            "emulator": "xemu",
            "version": "0.8.135",
            "commit": "6318bb112091635ef908255019e4d42956bc5fa8",
            "graphics": "Mesa llvmpipe (LLVM 21.1.8, 256 bits)",
            "audio_driver": "SDL dummy",
            "nested_display": "Xephyr :99 at 1280x720 with Metacity",
            "route": "no-input attract/demo mode -> Raiders at Giants live gameplay",
            "game_input_sent": False,
            "selected_dvd_sha256": pinned[display_path(PATCHED_XISO)]["sha256"],
            "selected_config": pinned[display_path(CONFIG)],
            "fresh_overlay_after": pinned[display_path(LOCAL_OVERLAY)],
            "overlay_backing_before_and_after": pinned[display_path(BACKING_OVERLAY)],
            "overlay_qemu_check": "no errors; 0.92% allocated",
            "firmware": {name: pinned[display_path(path)] for name, path in FIRMWARE.items()},
            "flatpak_filesystem": (
                "host read-only plus one-run read/write grant limited to the isolated run directory"
            ),
            "shutdown": {
                "wm_delete_sent": True,
                "xemu_exit_code": 0,
                "forced_kill_used": False,
                "virtual_gamepad_log_ended_with_bye": True,
                "nested_display_stopped": True,
            },
        },
        "visual_proof": {
            "runtime_screenshot": pinned[display_path(SCREENSHOT)] | runtime_image,
            "fixture": pinned[display_path(FIXTURE)] | fixture_image,
            "retail_art_control": pinned[display_path(CONTROL_SCREENSHOT)] | control_image,
            "control_report": pinned[display_path(CONTROL_REPORT)],
            "observation": (
                "The 17,233 threshold-magenta pixels form one bounded field-HUD box "
                "containing team, score, quarter, clock, down/distance, and play clock; "
                "the separately owned ESPN shield remains retail-colored."
            ),
        },
        "claims": {
            "score_buga_runtime_visibility_proved": True,
            "score_buga_field_hud_ownership_proved": True,
            "shield_espn_runtime_visibility_proved": False,
            "digital_font_runtime_visibility_proved": False,
            "scorebug_scne_geometry_write_proved": False,
            "scorebug_behavior_patch_proved": False,
            "apf_scorebug_write_proved": False,
            "original_xbox_hardware_tested": False,
            "source_xiso_modified": False,
            "patched_xiso_modified_during_runtime": False,
            "live_user_xemu_config_selected": False,
            "live_user_hdd_selected": False,
        },
        "portme": [
            "PORTME: capture shield_espn and digital_font replacements separately and inspect global digital_font side effects.",
            "PORTME: implement and validate NFL SCNE geometry/UV serialization before moving or resizing scorebug elements.",
            "PORTME: trace and patch formatting, data fields, visibility, timing, safe-area transforms, and animation separately.",
            "PORTME: repeat score_buga visibility on original Xbox hardware.",
        ],
    }


def write_new(path: Path, value: object) -> None:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    require(requested.suffix.lower() == ".json", "runtime report must use .json")
    require(not os.path.lexists(requested), f"runtime report already exists: {requested}")
    parent = requested.parent.lstat()
    require(stat.S_ISDIR(parent.st_mode) and not stat.S_ISLNK(parent.st_mode),
            "runtime report parent must be an existing non-symlink directory")
    destination = requested.resolve(strict=False)
    protected = {path.resolve(strict=True) for path in EXPECTED}
    require(destination not in protected, "runtime report cannot replace an evidence input")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    with destination.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports/assets/nfl2k5_scorebug_xemu_runtime.json",
    )
    args = parser.parse_args()
    report = generate()
    write_new(args.output, report)
    print(
        "NFL2K5_SCOREBUG_XEMU_RUNTIME_REPORT_PASS "
        "target=score_buga magenta=17233 control=0 xemu=0.8.135 hardware=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, TypeError, json.JSONDecodeError, RuntimeReportError) as exc:
        print(f"error: {exc}")
        raise SystemExit(1)
