#!/usr/bin/env python3
"""Freeze the bounded xemu proof for NFL 2K5's ``shield_espn`` writer.

The report joins an independently verified one-span copied XISO to retained
screenshots from natural demo gameplay.  It does not launch the emulator,
alter the immutable build manifest, or generalize the observation to
``digital_font``, SCNE geometry, behavior, APF, or original Xbox hardware.
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
SCHEMA = "nfl2k5_scorebug_shield_xemu_runtime/v1"
SOURCE_XISO = ROOT / "ESPN NFL 2K5 (USA).xiso.iso"
WORKFLOW_DIR = ROOT / "build/nfl2k5-scorebug-shield-workflow-20260712"
PATCHED_XISO = WORKFLOW_DIR / "ESPN-NFL-2K5-scorebug-shield-cyan.xiso.iso"
PROJECT = WORKFLOW_DIR / "project.json"
BUILD = WORKFLOW_DIR / "build.json"
IMPORT_MANIFEST = WORKFLOW_DIR / "artifacts/shield_espn.import.json"
PREVIEW = WORKFLOW_DIR / "artifacts/shield_espn.preview.png"
FIXTURE = ROOT / "reports/assets/nfl2k5_scorebug_fixtures/shield_espn_diagnostic.png"
EVIDENCE_DIR = ROOT / "reports/assets/nfl2k5_scorebug_shield_xemu_runtime"
SCREENSHOT = EVIDENCE_DIR / "shield-cyan-demo.png"
REPORTER_SCREENSHOT = EVIDENCE_DIR / "shield-cyan-demo-reporter.png"
CONFIG = EVIDENCE_DIR / "isolated-xemu-after.toml"
CONTROL_SCREENSHOT = (
    ROOT
    / "reports/assets/nfl2k5_jersey_tset_xemu_runtime/"
    "automatic-gameplay-packers-patriots.png"
)
CONTROL_REPORT = ROOT / "reports/assets/nfl2k5_jersey_tset_xemu_runtime.json"
RUN_DIR = ROOT / ".codex-tmp/nfl2k5-scorebug-shield-xemu-20260712"
LOCAL_OVERLAY = RUN_DIR / "xbox_hdd.qcow2"
BACKING_OVERLAY = Path(
    "/media/noah/Storage/.codex-tmp/"
    "nfl2k5-away-cacheclear-xemu-20260711/xbox_hdd.qcow2"
)
FIRMWARE = {
    "bootrom": RUN_DIR / "mcpx_1.0.bin",
    "flashrom": RUN_DIR / "Complex_4627.bin",
    "eeprom": RUN_DIR / "eeprom.bin",
}

EXPECTED = {
    SOURCE_XISO: (
        6_300_499_968,
        "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
    ),
    PATCHED_XISO: (
        6_300_499_968,
        "3fc03c76d622fb419b99f31255802d4945ac43f52e84a7ab44d07e6ebe4cd59f",
    ),
    PROJECT: (
        934,
        "cd736d4f90729820ac0cec89b083bf289051ba43608d9b519b78998677266f01",
    ),
    BUILD: (
        93_831,
        "14722e92e3c54cec1a1266e7b62ae47c93335dba6b7f69c91f4dbfb4f297fc05",
    ),
    IMPORT_MANIFEST: (
        24_840,
        "9323e7716396798ccb9e49d0d751130c78826f50d5a8ce61ce28255a4c062831",
    ),
    PREVIEW: (
        190,
        "8e77c89941e8e236caca32a132d64f3106086be71cf91da06f523ab0c2dc4e43",
    ),
    FIXTURE: (
        190,
        "8e77c89941e8e236caca32a132d64f3106086be71cf91da06f523ab0c2dc4e43",
    ),
    SCREENSHOT: (
        617_226,
        "2949d674796f1dcbe493149990de8cc20b50f9dddd0973b184aa0f23e2338909",
    ),
    REPORTER_SCREENSHOT: (
        625_399,
        "214c010d665253c7bb9890bf880a065ac98674d5283e6042ea6db83e4d97f008",
    ),
    CONFIG: (
        853,
        "6a76a340b7055e353b485cb958f8226b0a4b39a71ad16c51b8df823fa3971a38",
    ),
    CONTROL_SCREENSHOT: (
        1_016_970,
        "7eed38a888286c0b64ba55fdbdf1a05637d26aec655e8b2c23da9d2321f766f9",
    ),
    CONTROL_REPORT: (
        9_308,
        "373adb8171cd162139560579e74a80d46a3b29c42c08d820f49a3c78ea93f698",
    ),
    LOCAL_OVERLAY: (
        14_942_208,
        "4f268e63c5cee45b9eef5bde3cf62ab88c56db6f82f2d0b6edb4835c62bdea57",
    ),
    BACKING_OVERLAY: (
        983_040,
        "43b6cea37aa0c5a02b50a822211842fe761da64cc2aaf75ecaad2fbdfe582ab4",
    ),
    FIRMWARE["bootrom"]: (
        512,
        "e99e3a772bf5f5d262786aee895664eb96136196e37732fe66e14ae062f20335",
    ),
    FIRMWARE["flashrom"]: (
        1_048_576,
        "34f1c8ded59116436065783f8ad2ef0939df3cbfc76277ec9e5c41bf9ccb93cd",
    ),
    FIRMWARE["eeprom"]: (
        256,
        "52142e8293aada6343cb07c9aa816b60a6d84bddc230594269ec99f6d188b516",
    ),
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
    require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        f"runtime input is not a regular non-symlink file: {path}",
    )
    expected_size, expected_hash = EXPECTED[path]
    require(supplied.st_size == expected_size, f"runtime input size differs: {path}")
    digest = sha256_file(path)
    require(digest == expected_hash, f"runtime input hash differs: {path}")
    current = path.stat(follow_symlinks=False)
    require(
        (current.st_dev, current.st_ino, current.st_size)
        == (supplied.st_dev, supplied.st_ino, supplied.st_size),
        f"runtime input changed while hashing: {path}",
    )
    return {"path": display_path(path), "size": supplied.st_size, "sha256": digest}


def canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    require(
        raw == (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
        f"JSON evidence is not canonical: {path}",
    )
    return value


def cyan_stats(path: Path, crop: tuple[int, int, int, int]) -> dict[str, Any]:
    with Image.open(path) as source:
        source.load()
        require(source.format == "PNG", f"runtime image is not PNG: {path}")
        image = source.convert("RGB")
    points: list[tuple[int, int]] = []
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = image.getpixel((x, y))
            if red <= 20 and green >= 230 and blue >= 230:
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
        "cyan_predicate": "r<=20,g>=230,b>=230",
        "cyan_pixel_count": len(points),
        "cyan_bbox_inclusive": bbox,
        "field_hud_crop": list(crop),
        "field_hud_crop_rgb_sha256": hashlib.sha256(crop_image.tobytes()).hexdigest(),
    }


def load_build() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    project = canonical_json(PROJECT)
    build = canonical_json(BUILD)
    import_manifest = canonical_json(IMPORT_MANIFEST)
    edit = build["edits"][0]
    target = import_manifest["target"]
    require(
        project["schema"] == "nfl2k5_scorebug_mod_project/v1"
        and len(project["edits"]) == 1
        and project["edits"][0]["target"] == "shield_espn"
        and project["edits"][0]["png_sha256"] == EXPECTED[FIXTURE][1],
        "shield project recipe differs",
    )
    require(
        build["schema"] == "nfl2k5_scorebug_mod_build/v1"
        and build["project"]["sha256"] == EXPECTED[PROJECT][1]
        and build["output"]["xiso_sha256"] == EXPECTED[PATCHED_XISO][1]
        and build["source"]["sha256_before"] == EXPECTED[SOURCE_XISO][1]
        and build["source"]["sha256_after"] == EXPECTED[SOURCE_XISO][1]
        and build["source"]["modified"] is False
        and build["patch"]["span_count"] == 1
        and build["patch"]["actual_changed_byte_count"] == 5_320
        and build["patch"]["all_bytes_outside_union_identical"] is True
        and build["xdvdfs"]["tree_identical_after_patch"] is True
        and build["xdvdfs"]["all_sector_extents_preserved"] is True
        and build["xdvdfs"]["default_xbe_sha256"]
        == "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
        "shield build proof differs",
    )
    require(
        edit["target"] == "shield_espn"
        and edit["import_manifest"] == import_manifest
        and edit["import_manifest_sha256"] == EXPECTED[IMPORT_MANIFEST][1]
        and target["name"] == "shield_espn"
        and target["outer_index"] == 346
        and target["chunk_index"] == 26
        and target["width"] == 128
        and target["height"] == 64
        and target["span_size"] == 5_952
        and target["xiso_absolute_span_offset"] == 1_741_314_128
        and edit["patch"]["relative_changed_byte_count"] == 5_320,
        "shield target binding differs",
    )
    require(
        build["claims"]["runtime_visibility_proved"] is False
        and build["claims"]["title_executed"] is False
        and build["claims"]["xemu_started"] is False
        and import_manifest["claims"]["runtime_visibility_proved"] is False
        and import_manifest["claims"]["title_executed"] is False
        and import_manifest["claims"]["xemu_started"] is False,
        "immutable build-time runtime claims differ",
    )
    return project, build, import_manifest


def generate() -> dict[str, Any]:
    _project, build, _import_manifest = load_build()
    crop = (180, 20, 370, 115)
    runtime_image = cyan_stats(SCREENSHOT, crop)
    reporter_image = cyan_stats(REPORTER_SCREENSHOT, crop)
    control_image = cyan_stats(CONTROL_SCREENSHOT, crop)
    fixture_image = cyan_stats(FIXTURE, (0, 0, 128, 64))
    require(
        runtime_image
        == {
            "dimensions": [1280, 672],
            "cyan_predicate": "r<=20,g>=230,b>=230",
            "cyan_pixel_count": 4_557,
            "cyan_bbox_inclusive": [193, 34, 351, 101],
            "field_hud_crop": [180, 20, 370, 115],
            "field_hud_crop_rgb_sha256":
                "8a0ab0bb7ddabf53ecc5600099598fd083c89885f43bd031faed45cd63470b05",
        },
        "runtime shield image metrics differ",
    )
    require(
        reporter_image["dimensions"] == [1280, 672]
        and reporter_image["cyan_pixel_count"] == 4_558
        and reporter_image["cyan_bbox_inclusive"] == [193, 34, 351, 101]
        and reporter_image["field_hud_crop_rgb_sha256"]
        == "9a6cbf2c87c4f61c059b0f696a9d2a3d5bc48a4df06dcdd12293bdd100be4eb9",
        "reporter-frame shield image metrics differ",
    )
    require(
        control_image["dimensions"] == [1280, 720]
        and control_image["cyan_pixel_count"] == 0
        and control_image["cyan_bbox_inclusive"] is None
        and control_image["field_hud_crop_rgb_sha256"]
        == "dae245f40c419e7f30f02a448997b6e804c9ff21ebaa12afe3706bc887632404",
        "retail-art control image metrics differ",
    )
    require(
        fixture_image["dimensions"] == [128, 64]
        and fixture_image["cyan_pixel_count"] == 8_192
        and fixture_image["cyan_bbox_inclusive"] == [0, 0, 127, 63]
        and fixture_image["field_hud_crop_rgb_sha256"]
        == "43e9e378149717d919efdfdf3afb118028a5fe0a11e9de3d8f73daf336d51f16",
        "shield_espn fixture metrics differ",
    )

    pinned = {display_path(path): pin(path) for path in EXPECTED}
    return {
        "schema": SCHEMA,
        "date": "2026-07-12",
        "scope": (
            "positive xemu runtime visibility and field-HUD ownership for "
            "shield_espn only; no claim for digital_font, SCNE geometry, "
            "behavior, APF, non-field side effects, or hardware"
        ),
        "build_proof": {
            "source_xiso": pinned[display_path(SOURCE_XISO)],
            "patched_xiso": pinned[display_path(PATCHED_XISO)],
            "project": pinned[display_path(PROJECT)],
            "build_manifest": pinned[display_path(BUILD)],
            "import_manifest": pinned[display_path(IMPORT_MANIFEST)],
            "preview": pinned[display_path(PREVIEW)],
            "target": {
                "name": "shield_espn",
                "outer_index": 346,
                "chunk_index": 26,
                "dimensions": [128, 64],
                "xiso_absolute_span_offset": 1_741_314_128,
                "span_size": 5_952,
                "changed_byte_count": 5_320,
                "all_other_xiso_bytes_identical": True,
                "xdvdfs_tree_identical": True,
                "default_xbe_unchanged": True,
            },
            "builder_runtime_claim_was_false_at_build_time":
                build["claims"]["runtime_visibility_proved"] is False,
            "build_manifest_modified_for_runtime_result": False,
        },
        "runtime": {
            "emulator": "xemu",
            "version": "0.8.135",
            "commit": "6318bb112091635ef908255019e4d42956bc5fa8",
            "route": "no-input natural Demo Mode -> Jaguars at Bills live gameplay",
            "game_input_sent": False,
            "selected_dvd_sha256": pinned[display_path(PATCHED_XISO)]["sha256"],
            "selected_config": pinned[display_path(CONFIG)],
            "isolated_run_directory": display_path(RUN_DIR),
            "fresh_overlay_after": pinned[display_path(LOCAL_OVERLAY)],
            "overlay_backing_before_and_after": pinned[display_path(BACKING_OVERLAY)],
            "overlay_qemu_check": (
                "no errors; 0.17% allocated, 0.45% fragmented, "
                "0.00% compressed clusters"
            ),
            "firmware": {
                name: pinned[display_path(path)] for name, path in FIRMWARE.items()
            },
            "shutdown": {
                "wm_delete_sent": True,
                "xemu_exit_code": 0,
                "forced_kill_used": False,
                "nested_display_stopped": True,
            },
        },
        "visual_proof": {
            "runtime_screenshot": pinned[display_path(SCREENSHOT)] | runtime_image,
            "supplementary_reporter_frame":
                pinned[display_path(REPORTER_SCREENSHOT)] | reporter_image,
            "fixture": pinned[display_path(FIXTURE)] | fixture_image,
            "retail_art_control":
                pinned[display_path(CONTROL_SCREENSHOT)] | control_image,
            "control_report": pinned[display_path(CONTROL_REPORT)],
            "observation": (
                "The 4,557 exact-threshold cyan pixels form the upper-left "
                "field-HUD shield/strip in natural Demo Mode. The solid-cyan "
                "128x64 fixture has 8,192 matching pixels, while the unrelated "
                "retail-art gameplay control has zero."
            ),
        },
        "claims": {
            "shield_espn_runtime_visibility_proved": True,
            "shield_espn_field_hud_ownership_proved": True,
            "shield_espn_non_field_side_effects_proved": False,
            "digital_font_runtime_visibility_proved": False,
            "scorebug_scne_geometry_write_proved": False,
            "scorebug_behavior_patch_proved": False,
            "apf_scorebug_write_proved": False,
            "original_xbox_hardware_tested": False,
            "source_xiso_modified": False,
            "patched_xiso_modified_during_runtime": False,
            "build_manifest_modified_for_runtime_result": False,
            "live_user_xemu_config_selected": False,
            "live_user_hdd_selected": False,
        },
        "portme": [
            "PORTME: capture digital_font separately and inspect its global UI side effects.",
            "PORTME: implement and validate NFL SCNE geometry/UV serialization before moving or resizing scorebug elements.",
            "PORTME: trace and patch formatting, data fields, visibility, timing, safe-area transforms, and animation separately.",
            "PORTME: prove or reject any shield_espn reuse outside the field HUD with a separately designed control.",
            "PORTME: implement and validate APF scorebug writing separately.",
            "PORTME: repeat shield_espn visibility on original Xbox hardware.",
        ],
    }


def write_new(path: Path, value: object) -> None:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    require(requested.suffix.lower() == ".json", "runtime report must use .json")
    require(not os.path.lexists(requested), f"runtime report already exists: {requested}")
    parent = requested.parent.lstat()
    require(
        stat.S_ISDIR(parent.st_mode) and not stat.S_ISLNK(parent.st_mode),
        "runtime report parent must be an existing non-symlink directory",
    )
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
        default=ROOT / "reports/assets/nfl2k5_scorebug_shield_xemu_runtime.json",
    )
    args = parser.parse_args()
    report = generate()
    write_new(args.output, report)
    print(
        "NFL2K5_SCOREBUG_SHIELD_XEMU_RUNTIME_REPORT_PASS "
        "target=shield_espn cyan=4557 control=0 xemu=0.8.135 hardware=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, TypeError, json.JSONDecodeError, RuntimeReportError) as exc:
        print(f"error: {exc}")
        raise SystemExit(1)
