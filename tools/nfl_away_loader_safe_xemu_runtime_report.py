#!/usr/bin/env python3
"""Freeze the corrected NFL 2K5 AWAY-jersey xemu runtime evidence.

The source run and XISO are treated as read-only.  This tool hashes the exact
artifact and screenshots, verifies the rebuilt TSET wrapper and in-place
decode, measures diagnostic colors, records the fresh cache-overlay state, and
writes one deterministic JSON report.  It never starts xemu or edits an image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tomllib
from typing import Any, Callable

from PIL import Image

from nfl_tset_loader_alias_audit import alias_decode, token_requirements
from nfl_txtr import decompress_vc_lz


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = Path(
    "/media/noah/Storage/.codex-tmp/nfl2k5-away-cacheclear-xemu-20260711"
)
ARTIFACT_DIR = Path(
    "/media/noah/Storage/.codex-tmp/"
    "nfl2k5-actual-jersey-binding-away-loader-safe-20260711"
)
ASSET_DIR = ROOT / (
    "reports/assets/"
    "nfl2k5_actual_jersey_binding_away_loader_safe_xemu_runtime"
)
XISO = ARTIFACT_DIR / "ESPN-NFL-2K5-Detroit-AWAY-CODEX-MOD-loader-safe.xiso.iso"
MANIFEST = ARTIFACT_DIR / "workflow_manifest.json"
RETAIL_XISO = ROOT / "ESPN NFL 2K5 (USA).xiso.iso"
DIAGNOSTIC_PNG = ROOT / "reports/assets/nfl2k5_lions_diagnostic_codex_mod.png"
BACKING_HDD = Path(
    "/media/noah/Storage/.codex-tmp/"
    "nfl2k5-xemu-jersey-tset-controller-20260711/xbox_hdd.qcow2"
)
SCHEMA = "nfl2k5_away_loader_safe_xemu_runtime/v1"

EXPECTED_RETAIL_SHA256 = (
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
EXPECTED_XISO_SHA256 = (
    "5e8cf7c36c511878e5d5073fe96d757c1e21de08a360a5ca15f5ec7584242f2d"
)
EXPECTED_MANIFEST_SHA256 = (
    "8113352fe422132d690f78a8de8ebb08a2947755861a5b0d60de558e7f364c42"
)
EXPECTED_OVERLAY_SHA256 = (
    "43b6cea37aa0c5a02b50a822211842fe761da64cc2aaf75ecaad2fbdfe582ab4"
)
EXPECTED_BACKING_SHA256 = (
    "96bf4b69a2b1b2f71ca9ceb7a989b40c23fde8b979ff686b8155a218bd1846e5"
)
EXPECTED_DIAGNOSTIC_SHA256 = (
    "6ae65b7c4f982fbadb6da20444b21d7a2bb3c13f28a84b22c612967dc8a8f3c8"
)
EXPECTED_SPAN_SHA256 = (
    "12b4ffd5f6926a3c404190262e0a8c19d6c3335cd046b9dfff79797a05016766"
)
EXPECTED_DECODED_SHA256 = (
    "f5ed9101fa5c8bb742168b18fac698f57185c6b6a0190545ecafc1bb1b99c30e"
)

PARTITIONS = {
    "X": 0x00080000,
    "Y": 0x2EE80000,
    "Z": 0x5DC80000,
}
TEAM_CROP = (250, 155, 570, 440)
DETROIT_LIVE_CROP = (810, 90, 1088, 350)
GIANTS_LIVE_CROP = (210, 60, 600, 350)


class ReportError(RuntimeError):
    """Raised when a pinned runtime-evidence invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def pin(path: Path, expected: str | None = None) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    require(resolved.is_file(), f"not a regular file: {resolved}")
    digest = sha256_file(resolved)
    if expected is not None:
        require(digest == expected, f"hash changed: {path}")
    return {
        "path": str(path),
        "size": resolved.stat().st_size,
        "sha256": digest,
        "opened_read_only": True,
    }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def read_span(path: Path, offset: int, size: int) -> bytes:
    with path.open("rb") as stream:
        stream.seek(offset)
        value = stream.read(size)
    require(len(value) == size, f"short span read: {path}")
    return value


ColorPredicate = Callable[[int, int, int], bool]
COLOR_PREDICATES: dict[str, ColorPredicate] = {
    "magenta": lambda r, g, b: r >= 180 and g <= 100 and b >= 150,
    "cyan": lambda r, g, b: r <= 100 and g >= 140 and b >= 140,
    "green": lambda r, g, b: r <= 100 and g >= 120 and b <= 100,
}


def color_audit(image: Image.Image, crop: tuple[int, int, int, int]) -> dict[str, Any]:
    rgb = image.convert("RGB")
    x0, y0, x1, y1 = crop
    require(0 <= x0 < x1 <= rgb.width and 0 <= y0 < y1 <= rgb.height,
            f"invalid crop {crop} for {rgb.size}")
    points: dict[str, list[tuple[int, int]]] = {
        name: [] for name in COLOR_PREDICATES
    }
    for y in range(y0, y1):
        for x in range(x0, x1):
            pixel = rgb.getpixel((x, y))
            for name, predicate in COLOR_PREDICATES.items():
                if predicate(*pixel):
                    points[name].append((x, y))
    counts = {name: len(value) for name, value in points.items()}
    boxes = {
        name: (None if not value else [
            min(x for x, _y in value),
            min(y for _x, y in value),
            max(x for x, _y in value) + 1,
            max(y for _x, y in value) + 1,
        ])
        for name, value in points.items()
    }
    crop_image = rgb.crop(crop)
    return {
        "crop": list(crop),
        "crop_pixels": (x1 - x0) * (y1 - y0),
        "crop_rgb_sha256": sha256_bytes(crop_image.tobytes()),
        "counts": counts,
        "bounding_boxes": boxes,
    }


def full_color_counts(image: Image.Image) -> dict[str, int]:
    pixels = list(image.convert("RGB").getdata())
    return {
        name: sum(predicate(*pixel) for pixel in pixels)
        for name, predicate in COLOR_PREDICATES.items()
    }


def image_pin(path: Path) -> tuple[dict[str, Any], Image.Image]:
    record = pin(path)
    image = Image.open(path)
    image.load()
    require(image.format == "PNG", f"not PNG: {path}")
    record["dimensions"] = [image.width, image.height]
    return record, image


def normalized_ocr(path: Path) -> str:
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "--psm", "6"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return " ".join(result.stdout.decode("utf-8", "replace").upper().split())


def qemu_read(path: Path, offset: int, size: int = 64) -> bytes:
    result = subprocess.run(
        ["qemu-io", "-r", "-f", "qcow2", "-c", f"read -v {offset} {size}",
         str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    output = bytearray()
    for line in result.stdout.splitlines():
        if not re.match(r"^[0-9a-fA-F]{8,}:", line):
            continue
        hex_and_ascii = line.split(":", 1)[1].strip()
        hex_part = re.split(r"\s{2,}", hex_and_ascii, maxsplit=1)[0]
        output.extend(bytes.fromhex(hex_part))
    require(len(output) == size,
            f"qemu-io returned {len(output)} bytes, expected {size}")
    return bytes(output)


def qemu_info(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["qemu-img", "info", "--backing-chain", "--output=json", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    value = json.loads(result.stdout)
    require(isinstance(value, list) and len(value) >= 2,
            "qemu-img did not expose the backing chain")
    top = value[0]
    return {
        "format": top["format"],
        "virtual_size": top["virtual-size"],
        "cluster_size": top["cluster-size"],
        "dirty": top["dirty-flag"],
        "backing_path": top["full-backing-filename"],
        "snapshot_count": len(top.get("snapshots", [])),
    }


def flatpak_xemu_version() -> str:
    result = subprocess.run(
        ["flatpak", "list", "--app", "--columns=application,version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if fields and fields[0] == "app.xemu.xemu":
            require(len(fields) == 2, "xemu Flatpak version row is malformed")
            return fields[1]
    raise ReportError("xemu Flatpak is absent")


def build(args: argparse.Namespace) -> dict[str, Any]:
    manifest_pin = pin(args.manifest, EXPECTED_MANIFEST_SHA256)
    manifest = load_json(args.manifest)
    require(manifest["schema"] == "nfl2k5_uniform_jersey_png_workflow/v3",
            "wrong workflow schema")
    target = manifest["target"]
    require(target["selector"] == "09A0" and target["outer_index"] == 4002 and
            target["chunk_index"] == 1 and target["side"] == "A" and
            target["variant"] == 0, "wrong workflow target")
    require(target["template_overlap_scratch_bytes"] == 16 and
            target["rebuilt_overlap_scratch_bytes"] == 56_816,
            "corrected scratch values changed")
    require(manifest["output"]["xiso_sha256"] == EXPECTED_XISO_SHA256 and
            manifest["output"]["xiso_size"] == 6_300_499_968,
            "workflow XISO identity changed")
    require(manifest["patch"]["replacement_span_sha256"] == EXPECTED_SPAN_SHA256 and
            manifest["patch"]["all_other_image_bytes_identical"],
            "workflow target-span evidence changed")

    retail_pin = pin(args.retail_xiso, EXPECTED_RETAIL_SHA256)
    xiso_pin = pin(args.xiso, EXPECTED_XISO_SHA256)
    diagnostic_pin, diagnostic = image_pin(args.diagnostic_png)
    require(diagnostic_pin["sha256"] == EXPECTED_DIAGNOSTIC_SHA256 and
            diagnostic_pin["dimensions"] == [512, 256],
            "diagnostic source changed")

    span = read_span(args.xiso, target["absolute_span_offset"], target["span_size"])
    require(sha256_bytes(span) == EXPECTED_SPAN_SHA256, "runtime span hash changed")
    header = struct.unpack_from("<4s7I", span)
    require(header == (b"TSET", 79_088, 256, 176_768, 0xFEEDBEEF,
                       56_816, 0, 0), "runtime TSET wrapper changed")
    body = span[32:]
    decoded, decode_info = decompress_vc_lz(body, 177_024)
    require(sha256_bytes(decoded) == EXPECTED_DECODED_SHA256 and
            decode_info.consumed_bytes == 22_285,
            "runtime span separate decode changed")
    requirements = token_requirements(body, 177_024, 79_088)
    require(requirements["exact_minimum_scratch_bytes"] == 56_792,
            "runtime span alias minimum changed")
    alias = alias_decode(body, 177_024, 79_088, 56_816,
                         decode_info.consumed_bytes)
    require(alias["output_sha256"] == EXPECTED_DECODED_SHA256 and
            alias["first_unread_source_collision"] is None and
            alias["first_invalid_match"] is None,
            "runtime span is not loader-alias safe")

    config_pin = pin(args.run_dir / "xemu.toml",
                     "506e3eedef37530d069dd93c1149519e9b6ffe6c8a3d1528fdcaa91bdf9b8251")
    config = tomllib.loads((args.run_dir / "xemu.toml").read_text(encoding="utf-8"))
    require(config["sys"]["files"]["dvd_path"] == str(args.xiso) and
            config["sys"]["files"]["hdd_path"] == str(args.run_dir / "xbox_hdd.qcow2"),
            "run config does not select the evidence XISO/HDD")

    overlay = args.run_dir / "xbox_hdd.qcow2"
    overlay_pin = pin(overlay, EXPECTED_OVERLAY_SHA256)
    backing_pin = pin(args.backing_hdd, EXPECTED_BACKING_SHA256)
    info = qemu_info(overlay)
    require(info == {
        "format": "qcow2",
        "virtual_size": 8_589_934_592,
        "cluster_size": 65_536,
        "dirty": False,
        "backing_path": str(args.backing_hdd),
        "snapshot_count": 0,
    }, "fresh-overlay backing metadata changed")

    cache_rows = []
    for name, offset in PARTITIONS.items():
        backing_header = qemu_read(args.backing_hdd, offset)
        postrun_header = qemu_read(overlay, offset)
        require(backing_header[:4] == b"FATX", f"backing {name} lacks FATX")
        if name in {"X", "Y"}:
            require(postrun_header == b"\0" * 64,
                    f"postrun {name} superblock prefix is not cleared")
            post_state = "still_zero_after_run"
        else:
            require(postrun_header[:4] == b"FATX" and
                    postrun_header[4:8] != backing_header[4:8],
                    "postrun Z was not reinitialized with a new serial")
            post_state = "reinitialized_during_run_with_new_serial"
        cache_rows.append({
            "partition": name,
            "offset": offset,
            "offset_hex": f"0x{offset:08x}",
            "prelaunch_action": "zeroed_first_4096_bytes_in_fresh_overlay",
            "backing_header_64_sha256": sha256_bytes(backing_header),
            "backing_header_16_hex": backing_header[:16].hex(),
            "postrun_header_64_sha256": sha256_bytes(postrun_header),
            "postrun_header_16_hex": postrun_header[:16].hex(),
            "postrun_state": post_state,
        })

    firmware = {
        "mcpx": pin(args.run_dir / "mcpx_1.0.bin",
                    "e99e3a772bf5f5d262786aee895664eb96136196e37732fe66e14ae062f20335"),
        "flashrom": pin(args.run_dir / "Complex_4627.bin",
                        "34f1c8ded59116436065783f8ad2ef0939df3cbfc76277ec9e5c41bf9ccb93cd"),
        "eeprom": pin(args.run_dir / "eeprom.bin",
                      "52142e8293aada6343cb07c9aa816b60a6d84bddc230594269ec99f6d188b516"),
    }

    source_map = {
        "coin-toss-live-diagnostic.png": "game-load-35s.png",
        "stadium-load-20s.png": "game-load-20s.png",
        "team-select-contact.png": "lions-away-loader-safe-team-select-contact.png",
    }
    for index in range(13):
        name = f"lions-away-loader-safe-team-select-{index:02d}.png"
        source_map[name] = name

    asset_pins: dict[str, dict[str, Any]] = {}
    loaded_images: dict[str, Image.Image] = {}
    for canonical_name, source_name in source_map.items():
        canonical = args.asset_dir / canonical_name
        source = args.run_dir / "logs" / source_name
        record, image = image_pin(canonical)
        expected_dimensions = (
            [1720, 912] if canonical_name == "team-select-contact.png"
            else [1280, 672]
        )
        require(record["dimensions"] == expected_dimensions,
                f"unexpected screenshot dimensions: {canonical_name}")
        require(record["sha256"] == sha256_file(source),
                f"canonical screenshot differs from run source: {canonical_name}")
        record["source_run_path"] = str(source)
        asset_pins[canonical_name] = record
        loaded_images[canonical_name] = image

    team_rows = []
    for index in range(13):
        name = f"lions-away-loader-safe-team-select-{index:02d}.png"
        image = loaded_images[name]
        crop = color_audit(image, TEAM_CROP)
        require(crop["counts"]["magenta"] == 0 and
                crop["counts"]["green"] == 0 and
                crop["counts"]["cyan"] <= 20,
                f"diagnostic colors unexpectedly appear in {name}")
        team_rows.append({
            "index": index,
            "asset": asset_pins[name],
            "lions_preview_crop": crop,
            "human_observation": "retail-looking Lions Current Uniform preview",
            "diagnostic_visible": False,
        })

    coin_name = "coin-toss-live-diagnostic.png"
    coin = loaded_images[coin_name]
    detroit_colors = color_audit(coin, DETROIT_LIVE_CROP)
    giants_colors = color_audit(coin, GIANTS_LIVE_CROP)
    require(detroit_colors["counts"] == {
        "magenta": 630, "cyan": 564, "green": 26,
    }, "Detroit live diagnostic color counts changed")
    require(giants_colors["counts"] == {
        "magenta": 0, "cyan": 0, "green": 13,
    }, "Giants control color counts changed")
    require(detroit_colors["bounding_boxes"] == {
        "magenta": [855, 105, 1088, 315],
        "cyan": [841, 105, 1088, 309],
        "green": [906, 146, 988, 317],
    }, "Detroit diagnostic bounding boxes changed")

    coin_ocr = normalized_ocr(args.asset_dir / coin_name)
    team_ocr = normalized_ocr(
        args.asset_dir / "lions-away-loader-safe-team-select-00.png"
    )
    require("COIN TOSS" in coin_ocr and "LIONS CALL IT" in coin_ocr,
            "coin-toss OCR anchors disappeared")
    require("TEAMSELECT" in team_ocr and "LIONS" in team_ocr and
            "GIANTS" in team_ocr,
            "Team Select OCR anchors disappeared")

    diagnostic_counts = full_color_counts(diagnostic)
    require(diagnostic_counts == {
        "magenta": 26_624, "cyan": 26_624, "green": 7_168,
    }, "diagnostic input color counts changed")

    version = flatpak_xemu_version()
    require(version == "0.8.135", f"unexpected xemu version {version}")

    return {
        "schema": SCHEMA,
        "captured_at": "2026-07-11",
        "scope": {
            "title": "ESPN NFL 2K5",
            "platform": "original Xbox",
            "emulator": "xemu",
            "emulator_version": version,
            "target": "09A0.IFF chunk 1 jersey00/jersey00_mud",
            "target_team": "Detroit Lions",
            "target_side": "AWAY",
            "uniform_selector": "Current Uniform",
            "hardware_validation": False,
            "legacy_negative_reports_modified": False,
        },
        "diagnostic_input": {
            **diagnostic_pin,
            "thresholds": {
                "magenta": "r>=180 and g<=100 and b>=150",
                "cyan": "r<=100 and g>=140 and b>=140",
                "green": "r<=100 and g>=120 and b<=100",
            },
            "full_image_counts": diagnostic_counts,
        },
        "artifact_under_test": {
            "xiso": xiso_pin,
            "retail_source": retail_pin,
            "workflow_manifest": manifest_pin,
            "workflow_schema": manifest["schema"],
            "target": {
                "logical_name": target["logical_name"],
                "outer_index": target["outer_index"],
                "chunk_index": target["chunk_index"],
                "absolute_span_offset": target["absolute_span_offset"],
                "span_size": target["span_size"],
                "stored_size": target["stored_size"],
                "template_overlap_scratch_bytes":
                    target["template_overlap_scratch_bytes"],
                "rebuilt_overlap_scratch_bytes":
                    target["rebuilt_overlap_scratch_bytes"],
                "replacement_span_sha256": EXPECTED_SPAN_SHA256,
            },
            "patch": {
                "changed_bytes": manifest["patch"]["actual_changed_byte_count"],
                "changed_runs": manifest["patch"]["relative_changed_run_count"],
                "all_other_xiso_bytes_identical": True,
                "xdvdfs_tree_and_extents_preserved":
                    manifest["xdvdfs"]["tree_identical_after_patch"] and
                    manifest["xdvdfs"]["all_sector_extents_preserved"],
            },
            "loader_alias_revalidation": {
                "decoded_sha256": EXPECTED_DECODED_SHA256,
                "encoded_bytes": decode_info.consumed_bytes,
                "exact_minimum_scratch_bytes":
                    requirements["exact_minimum_scratch_bytes"],
                "wrapper_scratch_bytes": header[5],
                "scratch_margin_bytes":
                    header[5] - requirements["exact_minimum_scratch_bytes"],
                "source_start": alias["source_start"],
                "matches_reference_decode": True,
                "first_unread_source_collision": None,
                "first_invalid_match": None,
            },
            "unchanged_since_manifest_hash": True,
        },
        "isolation": {
            "run_directory": str(args.run_dir),
            "xemu_config": config_pin,
            "selected_dvd_path": config["sys"]["files"]["dvd_path"],
            "selected_hdd_path": config["sys"]["files"]["hdd_path"],
            "hdd_overlay": {
                **overlay_pin,
                **info,
                "fresh_for_this_run": True,
                "backing": backing_pin,
            },
            "cache_partition_preparation": {
                "procedure": (
                    "Before launch, clear the first 4096 bytes containing each "
                    "FATX superblock for cache partitions X, Y, and Z in the "
                    "fresh overlay only."
                ),
                "backing_image_modified": False,
                "partitions": cache_rows,
                "postrun_note": (
                    "X and Y remain zero at evidence freeze; Z was reinitialized "
                    "during the run with a new FATX serial."
                ),
            },
            "firmware": firmware,
            "preexisting_live_xemu_state_used": False,
        },
        "canonical_assets": asset_pins,
        "observations": {
            "route": {
                "matchup": "Lions at Giants",
                "detroit_side": "AWAY",
                "away_uniform": "Current Uniform",
                "home_uniform": "Current Uniform",
            },
            "team_select": {
                "frame_count": len(team_rows),
                "frames": team_rows,
                "ocr_anchors": ["TEAMSELECT", "LIONS", "GIANTS"],
                "all_frames_retail_looking": True,
                "diagnostic_visible": False,
                "interpretation": "separate or baked preview path",
            },
            "coin_toss": {
                "asset": asset_pins[coin_name],
                "ocr_anchors": ["COIN TOSS", "LIONS CALL IT"],
                "visible_state": (
                    "Coin Toss with Giants players on the left and Detroit "
                    "players on the right"
                ),
                "detroit_player_crop": detroit_colors,
                "giants_player_control_crop": giants_colors,
                "diagnostic_visible_on_detroit_players": True,
                "live_player_rendering_visibility_proved": True,
            },
            "stadium_load_20s": {
                "asset": asset_pins["stadium-load-20s.png"],
                "visible_state": "stadium presentation before coin toss",
            },
            "team_select_contact": {
                "asset": asset_pins["team-select-contact.png"],
                "source_frame_count": 13,
            },
        },
        "outcome": {
            "classification":
                "positive_live_player_jersey_visibility_team_select_preview_separate",
            "modified_xiso_runtime_accepted": True,
            "title_booted": True,
            "lions_at_giants_current_uniform_reached": True,
            "diagnostic_visible_in_team_select": False,
            "diagnostic_visible_on_live_coin_toss_players": True,
            "patched_09A0_chunk1_controls_live_detroit_away_jersey": True,
            "team_select_uses_separate_or_baked_preview_path": True,
            "gameplay_after_coin_toss_captured": False,
            "gameplay_visibility_claimed": False,
            "runtime_static_binding_contradiction_resolved_for_live_players": True,
            "retail_source_modified": False,
            "backing_hdd_modified": False,
            "hardware_validation": False,
        },
        "boundary": (
            "The nested display/session ended after the positive coin-toss "
            "capture. No gameplay frame after coin toss was captured, so this "
            "report makes no gameplay-visibility claim."
        ),
        "interpretation": [
            "The corrected +0x14 value removes the loader-alias failure while preserving the fixed 09A0 span.",
            "The injected diagnostic appears on Detroit's live coin-toss player models, proving 09A0 chunk-1 jersey00 visibility for live player rendering.",
            "All 13 Team Select frames remain retail-looking, so that menu uses a separate or baked preview path rather than the live player-material path proved at coin toss.",
            "The prior HOME/AWAY negative artifacts remain preserved historical controls; this positive report does not rewrite them.",
            "Gameplay after coin toss and original-Xbox hardware behavior remain untested here.",
        ],
        "portme": [
            "PORTME(gameplay): capture a scratch-corrected Detroit-away gameplay frame before claiming gameplay visibility.",
            "PORTME(team-select): recover the separate/baked Team Select preview asset path if menu preview modding is desired.",
            "PORTME(hardware): repeat the positive live-player result on an original Xbox.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=RUN_DIR)
    parser.add_argument("--artifact-dir", type=Path, default=ARTIFACT_DIR)
    parser.add_argument("--asset-dir", type=Path, default=ASSET_DIR)
    parser.add_argument("--xiso", type=Path, default=XISO)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--retail-xiso", type=Path, default=RETAIL_XISO)
    parser.add_argument("--diagnostic-png", type=Path, default=DIAGNOSTIC_PNG)
    parser.add_argument("--backing-hdd", type=Path, default=BACKING_HDD)
    parser.add_argument("--output", type=Path, default=ROOT /
                        "reports/assets/"
                        "nfl2k5_actual_jersey_binding_away_loader_safe_xemu_runtime.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    counts = report["observations"]["coin_toss"]["detroit_player_crop"]["counts"]
    print(
        "NFL_AWAY_LOADER_SAFE_XEMU_RUNTIME_REPORT_OK "
        f"team_frames={report['observations']['team_select']['frame_count']} "
        f"magenta={counts['magenta']} cyan={counts['cyan']} green={counts['green']} "
        "coin_toss=yes gameplay=no"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
