#!/usr/bin/env python3
"""Freeze route-specific negative xemu evidence for NFL 2K5 ``digital_font``.

The report joins an independently verified one-span copied XISO to one retained
natural-Demo-Mode frame containing the field HUD and a lower third.  It records
that the solid-magenta replacement was not visibly exercised in that frame. It
does not launch xemu, alter build history, or infer that the resource is unused,
dead, visible elsewhere, globally shared at runtime, or hardware-equivalent.
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
SCHEMA = "nfl2k5_scorebug_font_xemu_runtime/v1"
SOURCE_XISO = ROOT / "ESPN NFL 2K5 (USA).xiso.iso"
WORKFLOW_DIR = ROOT / "build/nfl2k5-scorebug-font-magenta-workflow-20260712"
PATCHED_XISO = WORKFLOW_DIR / "ESPN-NFL-2K5-scorebug-font-magenta.xiso.iso"
PROJECT = WORKFLOW_DIR / "project.json"
BUILD = WORKFLOW_DIR / "build.json"
IMPORT_MANIFEST = WORKFLOW_DIR / "artifacts/digital_font.import.json"
PREVIEW = WORKFLOW_DIR / "artifacts/digital_font.preview.png"
EVIDENCE_DIR = ROOT / "reports/assets/nfl2k5_scorebug_font_xemu_runtime"
FIXTURE = EVIDENCE_DIR / "digital_font_magenta_diagnostic.png"
SCREENSHOT = EVIDENCE_DIR / "digital-font-magenta-not-visible-demo.png"
CONFIG = EVIDENCE_DIR / "isolated-xemu-after.toml"
CONTROL_SCREENSHOT = (
    ROOT
    / "reports/assets/nfl2k5_jersey_tset_xemu_runtime/"
    "automatic-gameplay-packers-patriots.png"
)
CONTROL_REPORT = ROOT / "reports/assets/nfl2k5_jersey_tset_xemu_runtime.json"
RUN_DIR = ROOT / ".codex-tmp/nfl2k5-scorebug-font-magenta-xemu-20260712"
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
        "1163c6fbfcc2059b2cb7c3f6bb29382b19b693db1b1d777a4c7c58dd06b200a1",
    ),
    PROJECT: (
        980,
        "645eaf3d639c5cc5bc46f440ff8ab860d74340ab0436d1f4bd11001866b7d867",
    ),
    BUILD: (
        42_461,
        "c9242caca4dfb63503b3906010eb9c7dfe074793a01e9c8190017d6eca06ed5a",
    ),
    IMPORT_MANIFEST: (
        12_580,
        "f6cb58273c85f753626b6a1cfb4a4368fa426c3b29b6f8f243e805beb21ed8b7",
    ),
    PREVIEW: (
        296,
        "74fa7b294e0be7f4e688c36c7c3524532584d866a2c4cb39dd35a58847d3aa0b",
    ),
    FIXTURE: (
        471,
        "b38fe891f9a18924f5d120b56fcb5ae748d20f24563657d224dc5b5fe9bfd279",
    ),
    SCREENSHOT: (
        484_766,
        "15737fab39c318a80bbecdbd4ea1ea6d768599b90119d39c12edd0fa2758ddf7",
    ),
    CONFIG: (
        883,
        "8974a7749774b6f1532f45bdc5da43f98479b21ef64d1a52aab008edb285c4f0",
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
        10_223_616,
        "356e897e746745f84dfbed5be235be350a729188fb280fa717b2073601fd05be",
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


def magenta_stats(path: Path) -> dict[str, Any]:
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
    return {
        "dimensions": [image.width, image.height],
        "magenta_predicate": "r>=220,g<=60,b>=180",
        "magenta_pixel_count": len(points),
        "magenta_bbox_inclusive": bbox,
        "rgb_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
    }


def crop_rgb_sha256(path: Path, crop: tuple[int, int, int, int]) -> str:
    with Image.open(path) as source:
        source.load()
        require(source.format == "PNG", f"runtime image is not PNG: {path}")
        image = source.convert("RGB")
    return hashlib.sha256(image.crop(crop).tobytes()).hexdigest()


def load_build() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    project = canonical_json(PROJECT)
    build = canonical_json(BUILD)
    import_manifest = canonical_json(IMPORT_MANIFEST)
    edit = build["edits"][0]
    target = import_manifest["target"]
    require(
        project["schema"] == "nfl2k5_scorebug_mod_project/v1"
        and len(project["edits"]) == 1
        and project["edits"][0]["target"] == "digital_font"
        and project["edits"][0]["png_sha256"] == EXPECTED[FIXTURE][1],
        "digital_font project recipe differs",
    )
    require(
        build["schema"] == "nfl2k5_scorebug_mod_build/v1"
        and build["project"]["sha256"] == EXPECTED[PROJECT][1]
        and build["output"]["xiso_sha256"] == EXPECTED[PATCHED_XISO][1]
        and build["source"]["sha256_before"] == EXPECTED[SOURCE_XISO][1]
        and build["source"]["sha256_after"] == EXPECTED[SOURCE_XISO][1]
        and build["source"]["modified"] is False
        and build["patch"]["span_count"] == 1
        and build["patch"]["actual_changed_byte_count"] == 2_465
        and build["patch"]["all_bytes_outside_union_identical"] is True
        and build["xdvdfs"]["tree_identical_after_patch"] is True
        and build["xdvdfs"]["all_sector_extents_preserved"] is True
        and build["xdvdfs"]["default_xbe_sha256"]
        == "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
        "digital_font build proof differs",
    )
    require(
        edit["target"] == "digital_font"
        and edit["import_manifest"] == import_manifest
        and edit["import_manifest_sha256"] == EXPECTED[IMPORT_MANIFEST][1]
        and target["name"] == "digital_font"
        and target["outer_index"] == 3
        and target["chunk_index"] == 46
        and target["width"] == 128
        and target["height"] == 128
        and target["span_size"] == 2_752
        and target["xiso_absolute_span_offset"] == 1_632_281_456
        and edit["patch"]["relative_changed_byte_count"] == 2_465,
        "digital_font target binding differs",
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
    runtime_image = magenta_stats(SCREENSHOT)
    control_image = magenta_stats(CONTROL_SCREENSHOT)
    fixture_image = magenta_stats(FIXTURE)
    preview_image = magenta_stats(PREVIEW)
    require(
        runtime_image
        == {
            "dimensions": [1280, 672],
            "magenta_predicate": "r>=220,g<=60,b>=180",
            "magenta_pixel_count": 0,
            "magenta_bbox_inclusive": None,
            "rgb_sha256":
                "759ffe255c445d209ab2f585a92b14f4cca39373e50995649a34b59602b2fc52",
        },
        "runtime digital_font image metrics differ",
    )
    require(
        control_image["dimensions"] == [1280, 720]
        and control_image["magenta_pixel_count"] == 0
        and control_image["magenta_bbox_inclusive"] is None
        and control_image["rgb_sha256"]
        == "cfe12d1cbd07ee4af41588db3a62661d32574f639f5a7d2db416d169151c262d",
        "retail-art control image metrics differ",
    )
    expected_solid = {
        "dimensions": [128, 128],
        "magenta_predicate": "r>=220,g<=60,b>=180",
        "magenta_pixel_count": 16_384,
        "magenta_bbox_inclusive": [0, 0, 127, 127],
        "rgb_sha256":
            "106984d1dd35a4991415ffed0da80f0359cf171842c4a0f90eab3537443756b2",
    }
    require(fixture_image == expected_solid, "digital_font fixture metrics differ")
    require(preview_image == expected_solid, "digital_font preview metrics differ")
    field_hud_crop = [820, 40, 1080, 205]
    lower_third_crop = [192, 520, 1088, 652]
    require(
        crop_rgb_sha256(SCREENSHOT, tuple(field_hud_crop))
        == "1ed1e40fbc2f54ef6735d299b65bad5c784e76a2d4e17cb434f84700404b5b46",
        "field-HUD crop differs",
    )
    require(
        crop_rgb_sha256(SCREENSHOT, tuple(lower_third_crop))
        == "a88f6f2b4412a82bf119d73bd87a1b4d0ec528bb468d9bbf38707e76f1b1be6d",
        "lower-third crop differs",
    )

    pinned = {display_path(path): pin(path) for path in EXPECTED}
    return {
        "schema": SCHEMA,
        "date": "2026-07-12",
        "scope": (
            "route-specific negative xemu evidence for digital_font only: the "
            "patched copied XISO booted, but its solid-magenta replacement was "
            "not visibly exercised in one no-input natural Demo Mode frame with "
            "a field HUD and lower third; no claim that the resource is unused "
            "or dead, visible elsewhere, globally effective, menu-tested, or "
            "hardware-equivalent"
        ),
        "build_proof": {
            "source_xiso": pinned[display_path(SOURCE_XISO)],
            "patched_xiso": pinned[display_path(PATCHED_XISO)],
            "project": pinned[display_path(PROJECT)],
            "build_manifest": pinned[display_path(BUILD)],
            "import_manifest": pinned[display_path(IMPORT_MANIFEST)],
            "preview": pinned[display_path(PREVIEW)],
            "target": {
                "name": "digital_font",
                "outer_index": 3,
                "chunk_index": 46,
                "dimensions": [128, 128],
                "xiso_absolute_span_offset": 1_632_281_456,
                "span_size": 2_752,
                "changed_byte_count": 2_465,
                "all_other_xiso_bytes_identical": True,
                "xdvdfs_tree_identical": True,
                "default_xbe_unchanged": True,
            },
            "builder_runtime_claim_was_false_at_build_time":
                build["claims"]["runtime_visibility_proved"] is False,
            "build_manifest_global_side_effects_flag":
                build["claims"]["digital_font_has_global_ui_side_effects"],
            "build_manifest_modified_for_runtime_result": False,
        },
        "runtime": {
            "emulator": "xemu",
            "version": "0.8.135",
            "commit": "6318bb112091635ef908255019e4d42956bc5fa8",
            "route": (
                "no-input natural Demo Mode -> Colts at Bills live gameplay; "
                "observed frame contains the full field HUD and an offense lower third"
            ),
            "game_input_sent": False,
            "selected_dvd_sha256": pinned[display_path(PATCHED_XISO)]["sha256"],
            "selected_config": pinned[display_path(CONFIG)],
            "isolated_run_directory": display_path(RUN_DIR),
            "fresh_overlay_after": pinned[display_path(LOCAL_OVERLAY)],
            "overlay_backing_before_and_after": pinned[display_path(BACKING_OVERLAY)],
            "overlay_qemu_check": (
                "no errors; 0.11% allocated, 0.67% fragmented, "
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
        "visual_evidence": {
            "runtime_screenshot": pinned[display_path(SCREENSHOT)] | runtime_image,
            "observed_regions": {
                "field_hud_crop": field_hud_crop,
                "field_hud_crop_rgb_sha256":
                    "1ed1e40fbc2f54ef6735d299b65bad5c784e76a2d4e17cb434f84700404b5b46",
                "offense_lower_third_crop": lower_third_crop,
                "offense_lower_third_crop_rgb_sha256":
                    "a88f6f2b4412a82bf119d73bd87a1b4d0ec528bb468d9bbf38707e76f1b1be6d",
            },
            "fixture": pinned[display_path(FIXTURE)] | fixture_image,
            "retail_art_control":
                pinned[display_path(CONTROL_SCREENSHOT)] | control_image,
            "control_report": pinned[display_path(CONTROL_REPORT)],
            "observation": (
                "The 128x128 diagnostic and rebuilt preview each contain "
                "16,384 threshold-magenta pixels. The retained 1280x672 live "
                "Demo Mode frame visibly contains a complete field HUD and an "
                "offense lower third but contains zero such pixels; the retail "
                "gameplay control also contains zero."
            ),
        },
        "claims": {
            "patched_xiso_booted_in_xemu": True,
            "observed_frame_has_field_hud_and_lower_third": True,
            "digital_font_replacement_not_visibly_exercised_in_observed_frame": True,
            "digital_font_runtime_visibility_proved": False,
            "digital_font_resource_unused_or_dead_proved": False,
            "digital_font_global_ui_side_effects_runtime_proved": False,
            "digital_font_menu_behavior_tested": False,
            "digital_font_other_routes_tested": False,
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
            "PORTME: design routes that visibly exercise digital_font before claiming successful runtime visibility or that the resource is unused/dead.",
            "PORTME: capture menus, overlays, replay/pause screens, and additional presentation states to test the proposed global-font side effects.",
            "PORTME: implement and validate NFL SCNE geometry/UV serialization separately.",
            "PORTME: repeat a successful digital_font visibility route on original Xbox hardware.",
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
        default=ROOT / "reports/assets/nfl2k5_scorebug_font_xemu_runtime.json",
    )
    args = parser.parse_args()
    report = generate()
    write_new(args.output, report)
    print(
        "NFL2K5_SCOREBUG_FONT_XEMU_RUNTIME_REPORT_PASS "
        "target=digital_font changed=2465 runtime_magenta=0 fixture=16384 "
        "route_specific=true xemu=0.8.135 hardware=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, TypeError, json.JSONDecodeError, RuntimeReportError) as exc:
        print(f"error: {exc}")
        raise SystemExit(1)
