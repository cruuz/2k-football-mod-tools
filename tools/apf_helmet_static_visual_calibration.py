#!/usr/bin/env python3
"""Private non-package-bound crest-aspect calibration for the exact v17 helmet.

The exact package mask is 512x512 but its active RGB region is 512x226.  This
calibration crops that nonblack region and expands it to 512x512 with exact
nearest-neighbour sampling.  It changes only a generated review material; the
game volume, extracted SCNE geometry, UVs, package/cache evidence, and public
editor behavior remain untouched.  Every output is labelled non-proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from PIL import Image  # noqa: E402

import apf_helmet_static_visual_proof as proof  # noqa: E402
from nfl_txtr import encode_rgba_png  # noqa: E402


SCHEMA = "apf2k8_helmet_static_visual_calibration/v1"
CLAIM = "calibration_not_package_bound"
EXPECTED_ACTIVE_BBOX = (0, 143, 511, 368)


class CalibrationError(ValueError):
    """The exact private calibration left its deliberately narrow contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibrationError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def active_rgb_bbox(rgba: bytes) -> tuple[int, int, int, int]:
    _require(len(rgba) == 512 * 512 * 4, "calibration source is not 512x512 RGBA")
    active = [
        (index % 512, index // 512)
        for index in range(512 * 512)
        if any(rgba[index * 4 + channel] for channel in range(3))
    ]
    _require(bool(active), "calibration source has no active RGB region")
    return (
        min(point[0] for point in active), min(point[1] for point in active),
        max(point[0] for point in active), max(point[1] for point in active),
    )


def fit_active_xy_nearest(rgba: bytes) -> tuple[bytes, dict[str, object]]:
    bbox = active_rgb_bbox(rgba)
    _require(bbox == EXPECTED_ACTIVE_BBOX,
             f"exact v17 active bbox differs: {bbox}")
    left, top, right, bottom = bbox
    width = right - left + 1
    height = bottom - top + 1
    output = bytearray(512 * 512 * 4)
    sampled_x: set[int] = set()
    sampled_y: set[int] = set()
    for y in range(512):
        source_y = top + y * height // 512
        sampled_y.add(source_y)
        for x in range(512):
            source_x = left + x * width // 512
            sampled_x.add(source_x)
            source = (source_y * 512 + source_x) * 4
            target = (y * 512 + x) * 4
            output[target : target + 4] = rgba[source : source + 4]
    _require(sampled_x == set(range(left, right + 1)),
             "nearest calibration skipped a source column")
    _require(sampled_y == set(range(top, bottom + 1)),
             "nearest calibration skipped a source row")
    return bytes(output), {
        "algorithm": "crop_nonblack_rgb_bbox_then_xy_nearest_v1",
        "input_canvas": [512, 512],
        "input_active_bbox_inclusive": list(bbox),
        "input_active_size": [width, height],
        "output_canvas": [512, 512],
        "x_scale": 512 / width,
        "y_scale": 512 / height,
        "all_source_columns_sampled": True,
        "all_source_rows_sampled": True,
        "palette_and_alpha_copied_without_interpolation": True,
    }


def prepare(input_0a: Path, output_dir: Path) -> dict[str, object]:
    destination, staging = proof._atomic_destination(output_dir)
    try:
        proof.prepare_exact(input_0a, staging)
        receipt_path = staging / "helmet-v17-proof.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        raw_path = staging / receipt["crest"]["raw_region_mask"]["file"]
        with Image.open(raw_path) as image:
            image.load()
            _require(image.size == (512, 512), "exact region-mask PNG dimensions differ")
            raw = image.convert("RGBA").tobytes()
        _require(_sha256(raw) == receipt["crest"]["raw_region_mask"]["decoded_rgba_sha256"],
                 "exact region-mask PNG no longer matches package-decoded RGBA")
        fitted, transform = fit_active_xy_nearest(raw)
        palette = [int(value, 16) for value in receipt["appearance"]["palette_argb"]]
        material = proof.colorize_region_mask(fitted, palette[0], palette[2])

        fitted_path = staging / "helmet-v17-calibration-region-mask.png"
        material_path = staging / "helmet-v17-calibration-crest-material.png"
        fitted_path.write_bytes(encode_rgba_png(512, 512, fitted))
        material_path.write_bytes(encode_rgba_png(512, 512, material))
        exact_review = receipt["crest"]["review_material"]
        receipt["schema"] = SCHEMA
        receipt["claim"] = CLAIM
        receipt["proof_eligible"] = False
        receipt["package_bound"] = False
        receipt["calibration"] = {
            "label": CLAIM,
            "source": {
                "package_decoded_rgba_sha256": receipt["crest"]["raw_region_mask"]["decoded_rgba_sha256"],
                "exact_review_material": exact_review,
            },
            "transform": transform,
            "fitted_region_mask": {
                "file": fitted_path.name,
                "png_sha256": proof._sha256_file(fitted_path),
                "rgba_sha256": _sha256(fitted),
            },
            "fitted_review_material": {
                "file": material_path.name,
                "png_sha256": proof._sha256_file(material_path),
                "rgba_sha256": _sha256(material),
            },
            "game_bytes_changed": False,
            "editor_behavior_changed": False,
        }
        receipt["crest"]["review_material"] = {
            "file": material_path.name,
            "png_sha256": proof._sha256_file(material_path),
            "rgba_sha256": _sha256(material),
            "mapping": exact_review["mapping"],
            "no_redraw": True,
            "nearest_neighbor_calibration": True,
            "package_bound": False,
        }
        receipt["limitations"].insert(
            0,
            "CALIBRATION ONLY: the vertically fitted review mask is not stored in the v17 package/cache and cannot prove runtime or editor output.",
        )
        receipt["render_contract"]["label"] = CLAIM
        receipt["render_contract"]["package_bound"] = False
        proof._write_json(receipt_path, receipt)
        staging.rename(destination)
        return receipt
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def finalize(directory: Path) -> dict[str, object]:
    return proof._finalize_render(
        directory,
        expected_schema=SCHEMA,
        expected_claim=CLAIM,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("input_0a", type=Path)
    prepare_parser.add_argument("output_dir", type=Path)
    finalize_parser = commands.add_parser("finalize")
    finalize_parser.add_argument("prepared_dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            receipt = prepare(args.input_0a, args.output_dir)
            output = args.output_dir
        else:
            receipt = finalize(args.prepared_dir)
            output = args.prepared_dir
        print(
            "APF_HELMET_STATIC_CALIBRATION_READY "
            f"claim={receipt['claim']} output={output}"
        )
        return 0
    except (CalibrationError, proof.ProofError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
