#!/usr/bin/env python3
"""Verify both retained NFL 2K5 scorebug runtime receipts without Xemu.

The historical patched XISOs were intentionally cleaned.  This verifier
reconstructs each single replacement span and hashes the corresponding
virtual XISO while streaming the pinned retail source once.  It also pins the
retained runtime evidence and its incomplete historical QCOW2 lineage.  It
does not recreate a 6.3 GB file, start an emulator, or re-execute gameplay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from PIL import Image

from nfl_scorebug_png_import import DEFAULT_AUDIT, DEFAULT_INDEX, build_import
import nfl_uniform_color_xiso_direct_patch as xiso


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ESPN NFL 2K5 (USA).xiso.iso"
SCORE_REPORT = ROOT / "reports/assets/nfl2k5_scorebug_xemu_runtime.json"
SHIELD_REPORT = ROOT / "reports/assets/nfl2k5_scorebug_shield_xemu_runtime.json"
SCORE_WORKFLOW = ROOT / "build/nfl2k5-scorebug-workflow-20260712/workflow.json"
SCORE_PREVIEW = ROOT / "build/nfl2k5-scorebug-workflow-20260712/preview.png"
SHIELD_DIR = ROOT / "build/nfl2k5-scorebug-shield-workflow-20260712"
SHIELD_PROJECT = SHIELD_DIR / "project.json"
SHIELD_BUILD = SHIELD_DIR / "build.json"
SHIELD_IMPORT = SHIELD_DIR / "artifacts/shield_espn.import.json"
SHIELD_PREVIEW = SHIELD_DIR / "artifacts/shield_espn.preview.png"
SCORE_FIXTURE = ROOT / "reports/assets/nfl2k5_scorebug_fixtures/score_buga_diagnostic.png"
SHIELD_FIXTURE = ROOT / "reports/assets/nfl2k5_scorebug_fixtures/shield_espn_diagnostic.png"

SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
SCORE_XISO_SHA256 = "852901f79ae3368b1e0663106dffdfd5c3576c1ebd6579022c58277ed2a60a83"
SHIELD_XISO_SHA256 = "3fc03c76d622fb419b99f31255802d4945ac43f52e84a7ab44d07e6ebe4cd59f"
REPORT_PINS = {
    SCORE_REPORT: (6765, "69459139452669ba77b9635d7f90c8fc7d50bf55226e65b424555874e56a752d"),
    SHIELD_REPORT: (8348, "baa95440d1c53f16e7063fbb010cc2066f31d225ba6a462cc6f2d739f005c9bc"),
}


class ReceiptError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReceiptError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(path: Path, expected: tuple[int, str] | None = None) -> dict[str, Any]:
    raw = path.read_bytes()
    if expected is not None:
        require((len(raw), digest(raw)) == expected, f"receipt pin differs: {path}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReceiptError(f"invalid JSON receipt: {path}") from exc
    require(
        raw == (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
        f"receipt is not canonical JSON: {path}",
    )
    require(isinstance(value, dict), f"receipt root is not an object: {path}")
    return value


def resolve_record_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def pin_record(record: dict[str, Any], label: str) -> None:
    path = resolve_record_path(record["path"])
    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
        f"{label} is not a retained regular non-symlink file: {path}",
    )
    require(before.st_size == record["size"], f"{label} size differs: {path}")
    hasher = hashlib.sha256()
    descriptor = os.open(
        path.resolve(strict=True),
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        require(
            (opened.st_dev, opened.st_ino, opened.st_size)
            == (before.st_dev, before.st_ino, before.st_size),
            f"{label} identity changed before read: {path}",
        )
        while True:
            block = os.read(descriptor, 16 * 1024 * 1024)
            if not block:
                break
            hasher.update(block)
    finally:
        os.close(descriptor)
    after = path.stat(follow_symlinks=False)
    require(
        (after.st_dev, after.st_ino, after.st_size)
        == (before.st_dev, before.st_ino, before.st_size),
        f"{label} changed while reading: {path}",
    )
    require(hasher.hexdigest() == record["sha256"], f"{label} hash differs: {path}")


def pin_report_records(report: dict[str, Any], omitted: set[str]) -> None:
    seen: dict[str, tuple[int, str]] = {}

    def walk(value: object, label: str) -> None:
        if isinstance(value, dict):
            if {"path", "size", "sha256"} <= value.keys():
                path = str(value["path"])
                if path not in omitted:
                    identity = (int(value["size"]), str(value["sha256"]))
                    require(
                        path not in seen or seen[path] == identity,
                        f"conflicting receipt records for {path}",
                    )
                    if path not in seen:
                        pin_record(value, label)
                        seen[path] = identity
            for key, child in value.items():
                walk(child, f"{label}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{label}[{index}]")

    walk(report, "report")


def image_stats(record: dict[str, Any], colour: str) -> dict[str, Any]:
    path = resolve_record_path(record["path"])
    with Image.open(path) as source:
        source.load()
        require(source.format == "PNG", f"runtime evidence is not PNG: {path}")
        image = source.convert("RGB")
    if colour == "magenta":
        predicate = lambda r, g, b: r >= 220 and g <= 60 and b >= 180
        count_key, box_key, crop_key, hash_key = (
            "magenta_pixel_count", "magenta_bbox_inclusive", "scorebug_crop",
            "scorebug_crop_rgb_sha256",
        )
    else:
        predicate = lambda r, g, b: r <= 20 and g >= 230 and b >= 230
        count_key, box_key, crop_key, hash_key = (
            "cyan_pixel_count", "cyan_bbox_inclusive", "field_hud_crop",
            "field_hud_crop_rgb_sha256",
        )
    points = [
        (column, row)
        for row in range(image.height)
        for column in range(image.width)
        if predicate(*image.getpixel((column, row)))
    ]
    box = None if not points else [
        min(column for column, _ in points), min(row for _, row in points),
        max(column for column, _ in points), max(row for _, row in points),
    ]
    crop = tuple(record[crop_key])
    return {
        "dimensions": [image.width, image.height],
        count_key: len(points),
        box_key: box,
        crop_key: list(crop),
        hash_key: digest(image.crop(crop).tobytes()),
    }


def validate_visuals(score: dict[str, Any], shield: dict[str, Any]) -> None:
    for key in ("runtime_screenshot", "fixture", "retail_art_control"):
        record = score["visual_proof"][key]
        actual = image_stats(record, "magenta")
        require(all(record[name] == value for name, value in actual.items()),
                f"score_buga {key} metrics differ")
    for key in (
        "runtime_screenshot", "supplementary_reporter_frame", "fixture",
        "retail_art_control",
    ):
        record = shield["visual_proof"][key]
        actual = image_stats(record, "cyan")
        require(all(record[name] == value for name, value in actual.items()),
                f"shield_espn {key} metrics differ")


def reconstruct() -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    score_span, score_preview, score_import = build_import(
        ROOT / DEFAULT_INDEX, ROOT / DEFAULT_AUDIT, "score_buga", SCORE_FIXTURE,
    )
    shield_span, shield_preview, shield_import = build_import(
        ROOT / DEFAULT_INDEX, ROOT / DEFAULT_AUDIT, "shield_espn", SHIELD_FIXTURE,
    )
    score_workflow = canonical_json(SCORE_WORKFLOW)
    shield_project = canonical_json(SHIELD_PROJECT)
    shield_build = canonical_json(SHIELD_BUILD)
    retained_shield_import = canonical_json(SHIELD_IMPORT)

    require(score_workflow["input"]["import_manifest"] == score_import,
            "score_buga import reconstruction differs")
    require(
        score_workflow["input"]["import_manifest_sha256"]
        == digest((json.dumps(score_import, indent=2, sort_keys=True) + "\n").encode()),
        "score_buga import manifest digest differs",
    )
    require(SCORE_PREVIEW.read_bytes() == score_preview,
            "score_buga retained preview differs from reconstruction")
    require(
        score_workflow["output"]["xiso_sha256"] == SCORE_XISO_SHA256
        and score_workflow["claims"]["runtime_visibility_proved"] is False
        and score_workflow["claims"]["xemu_started"] is False
        and score_workflow["claims"]["title_executed"] is False,
        "score_buga immutable build claims differ",
    )

    require(retained_shield_import == shield_import,
            "shield_espn import reconstruction differs")
    require(SHIELD_PREVIEW.read_bytes() == shield_preview,
            "shield_espn retained preview differs from reconstruction")
    require(
        shield_project["edits"] == [{
            "png": str(SHIELD_FIXTURE.resolve()),
            "png_sha256": digest(SHIELD_FIXTURE.read_bytes()),
            "png_size": SHIELD_FIXTURE.stat().st_size,
            "target": "shield_espn",
        }],
        "shield_espn project recipe differs",
    )
    require(
        shield_build["edits"][0]["import_manifest"] == shield_import
        and shield_build["output"]["xiso_sha256"] == SHIELD_XISO_SHA256
        and shield_build["claims"]["runtime_visibility_proved"] is False
        and shield_build["claims"]["xemu_started"] is False
        and shield_build["claims"]["title_executed"] is False,
        "shield_espn immutable build claims differ",
    )
    return score_import, shield_import, score_span, shield_span


def stream_virtual_xisos(
    score_import: dict[str, Any], shield_import: dict[str, Any],
    score_span: bytes, shield_span: bytes,
) -> dict[str, str]:
    before = SOURCE.lstat()
    require(
        stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode)
        and before.st_size == xiso.EXPECTED_XISO_SIZE,
        "retail source XISO identity or size differs",
    )
    descriptor = os.open(
        SOURCE.resolve(strict=True),
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        require(
            (opened.st_dev, opened.st_ino, opened.st_size)
            == (before.st_dev, before.st_ino, before.st_size),
            "retail source XISO changed before read",
        )
        entries, _directory = xiso.parse_xdvdfs(descriptor, opened.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        xbe = entries.get("default.xbe")
        require(
            len(files) == 19 and xbe is not None
            and xiso.sha256_fd(descriptor, xbe.byte_offset, xbe.size)
            == xiso.EXPECTED_XBE_SHA256,
            "retail XDVDFS/default.xbe identity differs",
        )
        patches: list[tuple[str, int, bytes, dict[str, Any]]] = []
        for name, imported, replacement in (
            ("score_buga", score_import, score_span),
            ("shield_espn", shield_import, shield_span),
        ):
            target = imported["target"]
            pack = entries.get(str(target["pack_path"]).casefold())
            require(
                pack is not None and pack.sector == int(target["xiso_pack_sector"])
                and pack.byte_offset == int(target["xiso_pack_byte_offset"])
                and pack.size == int(target["pack_size"]),
                f"{name} XDVDFS pack identity differs",
            )
            absolute = pack.byte_offset + int(target["pack_offset"])
            require(absolute == int(target["xiso_absolute_span_offset"]),
                    f"{name} XISO span arithmetic differs")
            retail = xiso.read_exact(descriptor, absolute, len(replacement))
            require(digest(retail) == target["span_sha256"],
                    f"{name} retail source span differs")
            patches.append((name, absolute, replacement, imported))

        hashers = {"source": hashlib.sha256(), **{
            name: hashlib.sha256() for name, _, _, _ in patches
        }}
        position = 0
        chunk_size = 16 * 1024 * 1024
        while position < opened.st_size:
            block = os.pread(descriptor, min(chunk_size, opened.st_size - position), position)
            require(block, "short retail XISO read")
            hashers["source"].update(block)
            block_end = position + len(block)
            for name, patch_offset, replacement, _imported in patches:
                patch_end = patch_offset + len(replacement)
                overlap_start = max(position, patch_offset)
                overlap_end = min(block_end, patch_end)
                if overlap_start < overlap_end:
                    virtual = bytearray(block)
                    virtual[overlap_start - position:overlap_end - position] = replacement[
                        overlap_start - patch_offset:overlap_end - patch_offset
                    ]
                    hashers[name].update(virtual)
                else:
                    hashers[name].update(block)
            position = block_end
        after = SOURCE.stat(follow_symlinks=False)
        require(
            (after.st_dev, after.st_ino, after.st_size)
            == (opened.st_dev, opened.st_ino, opened.st_size),
            "retail source XISO changed while reading",
        )
    finally:
        os.close(descriptor)
    result = {name: value.hexdigest() for name, value in hashers.items()}
    require(result == {
        "source": SOURCE_SHA256,
        "score_buga": SCORE_XISO_SHA256,
        "shield_espn": SHIELD_XISO_SHA256,
    }, "virtual XISO digest differs from historical receipt")
    return result


def validate_claims(score: dict[str, Any], shield: dict[str, Any]) -> None:
    require(score["schema"] == "nfl2k5_scorebug_xemu_runtime/v1", "score report schema differs")
    require(shield["schema"] == "nfl2k5_scorebug_shield_xemu_runtime/v1", "shield report schema differs")
    require(score["claims"] == {
        "apf_scorebug_write_proved": False,
        "digital_font_runtime_visibility_proved": False,
        "live_user_hdd_selected": False,
        "live_user_xemu_config_selected": False,
        "original_xbox_hardware_tested": False,
        "patched_xiso_modified_during_runtime": False,
        "score_buga_field_hud_ownership_proved": True,
        "score_buga_runtime_visibility_proved": True,
        "scorebug_behavior_patch_proved": False,
        "scorebug_scne_geometry_write_proved": False,
        "shield_espn_runtime_visibility_proved": False,
        "source_xiso_modified": False,
    }, "score_buga causal claim boundary differs")
    require(shield["claims"] == {
        "apf_scorebug_write_proved": False,
        "build_manifest_modified_for_runtime_result": False,
        "digital_font_runtime_visibility_proved": False,
        "live_user_hdd_selected": False,
        "live_user_xemu_config_selected": False,
        "original_xbox_hardware_tested": False,
        "patched_xiso_modified_during_runtime": False,
        "scorebug_behavior_patch_proved": False,
        "scorebug_scne_geometry_write_proved": False,
        "shield_espn_field_hud_ownership_proved": True,
        "shield_espn_non_field_side_effects_proved": False,
        "shield_espn_runtime_visibility_proved": True,
        "source_xiso_modified": False,
    }, "shield_espn causal claim boundary differs")
    require(
        score["runtime"]["selected_dvd_sha256"] == SCORE_XISO_SHA256
        and shield["runtime"]["selected_dvd_sha256"] == SHIELD_XISO_SHA256,
        "runtime selected-DVD receipt differs from virtual output",
    )
    require(score["runtime"]["game_input_sent"] is False
            and score["runtime"]["route"].startswith("no-input attract/demo mode"),
            "score_buga no-input route differs")
    require(shield["runtime"]["game_input_sent"] is False
            and shield["runtime"]["route"].startswith("no-input natural Demo Mode"),
            "shield_espn no-input route differs")
    require(score["build_proof"]["target"]["changed_byte_count"] == 2169
            and shield["build_proof"]["target"]["changed_byte_count"] == 5320,
            "receipt changed-byte count differs")
    for report in (score, shield):
        require(report["build_proof"]["target"]["all_other_xiso_bytes_identical"] is True
                and report["build_proof"]["target"]["xdvdfs_tree_identical"] is True
                and report["build_proof"]["target"]["default_xbe_unchanged"] is True,
                "copy-only build boundary differs")
    score_config = resolve_record_path(score["runtime"]["selected_config"]["path"]).read_text()
    shield_config = resolve_record_path(shield["runtime"]["selected_config"]["path"]).read_text()
    require("nfl2k5-scorebug-xemu-20260712/xbox_hdd.qcow2" in score_config
            and "ESPN-NFL-2K5-scorebug-magenta.xiso.iso" in score_config,
            "score_buga isolated runtime config binding differs")
    require("nfl2k5-scorebug-shield-xemu-20260712/xbox_hdd.qcow2" in shield_config
            and "ESPN-NFL-2K5-scorebug-shield-cyan.xiso.iso" in shield_config,
            "shield_espn isolated runtime config binding differs")


def validate_chain(path: Path, leaf: str) -> None:
    chain = json.loads(path.read_bytes())
    require(chain["schema"] == "nfl2k5_historical_xemu_hdd_chain_verify/v1"
            and chain["leaf"] == leaf, f"{leaf} chain identity differs")
    require(chain["base_status"] == "missing"
            and chain["chain_complete"] is False
            and chain["guest_content_replayable"] is False
            and chain["historical_runtime_reexecuted"] is False
            and chain["missing_base_reconstructed"] is False
            and chain["substitution_allowed"] is False,
            f"{leaf} historical-chain boundary differs")
    expected_first = "scorebug_runtime" if leaf == "scorebug_runtime" else "scorebug_shield_runtime"
    require([row["id"] for row in chain["layers"]] == [
        expected_first, "away_cacheclear", "jersey_tset_controller_base",
    ] and chain["layers"][-1]["pin"] is None,
        f"{leaf} QCOW2 lineage differs")


def validate_docs() -> None:
    score = " ".join((ROOT / "docs/research/nfl_scorebug_xemu_runtime.md").read_text().split())
    shield = " ".join((ROOT / "docs/research/nfl_scorebug_shield_xemu_runtime.md").read_text().split())
    for phrase in (
        "positive runtime visibility for `score_buga` only", "17,233 pixels",
        "No controller input was sent", "Still unproved", "original-Xbox hardware parity",
    ):
        require(phrase in score, f"score_buga documentation boundary missing: {phrase}")
    for phrase in (
        "positive runtime visibility and field-HUD ownership for `shield_espn` only",
        "4,557 exact-threshold cyan pixels", "No controller input was sent",
        "build-time `runtime_visibility_proved=false`", "Still unproved",
        "original-Xbox hardware parity",
    ):
        require(phrase in shield, f"shield_espn documentation boundary missing: {phrase}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorebug-chain", type=Path, required=True)
    parser.add_argument("--shield-chain", type=Path, required=True)
    args = parser.parse_args()

    score = canonical_json(SCORE_REPORT, REPORT_PINS[SCORE_REPORT])
    shield = canonical_json(SHIELD_REPORT, REPORT_PINS[SHIELD_REPORT])
    omitted = {
        score["build_proof"]["source_xiso"]["path"],
        score["build_proof"]["patched_xiso"]["path"],
    }
    pin_report_records(score, omitted)
    omitted = {
        shield["build_proof"]["source_xiso"]["path"],
        shield["build_proof"]["patched_xiso"]["path"],
    }
    pin_report_records(shield, omitted)
    validate_claims(score, shield)
    validate_visuals(score, shield)
    score_import, shield_import, score_span, shield_span = reconstruct()
    require(score_import["rebuild"]["changed_byte_count"] == 2169
            and shield_import["rebuild"]["changed_byte_count"] == 5320,
            "reconstructed replacement changed-byte ledger differs")
    stream_virtual_xisos(score_import, shield_import, score_span, shield_span)
    validate_chain(args.scorebug_chain, "scorebug_runtime")
    validate_chain(args.shield_chain, "scorebug_shield_runtime")
    validate_docs()
    print(
        "NFL2K5_SCOREBUG_RUNTIME_RECEIPTS_PASS targets=score_buga,shield_espn "
        "changed=2169,5320 virtual_output_hashes=true retained_visuals=true "
        "chain_complete=false guest_content_replayable=false "
        "historical_runtime_reexecuted=false emulator_started=false output_xiso_written=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ReceiptError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
