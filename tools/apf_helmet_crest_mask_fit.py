#!/usr/bin/env python3
"""Fit a prepared APF helmet palette mask across the full crest U range.

APF helmet crest masks may use zero RGB as the inactive background while every
pixel, including that background, has nonzero alpha.  Alpha bounding boxes are
therefore wrong for this asset.  This writer crops the exact nonblack RGB
region, expands it horizontally to the 512-pixel crest canvas with integer
nearest-neighbour sampling, preserves the mask palette byte-for-byte, and
centres the result vertically on the original background value.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from nfl_txtr import encode_rgba_png  # noqa: E402


SCHEMA = "apf2k8_helmet_crest_visible_mask_fit/v1"
CANVAS_WIDTH = 512
CANVAS_HEIGHT = 512
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_PIXELS = 64 * 1024 * 1024


class MaskFitError(RuntimeError):
    """The source is not a bounded APF palette mask or cannot be fitted."""


@dataclass(frozen=True)
class MaskFit:
    source_bbox: tuple[int, int, int, int]
    source_visible_width: int
    source_visible_height: int
    output_bbox: tuple[int, int, int, int]
    output_visible_width: int
    output_visible_height: int
    output_rgba: bytes
    background_rgba: tuple[int, int, int, int]
    source_horizontal_coverage: float
    output_horizontal_coverage: float
    every_source_x_sampled: bool
    every_source_y_sampled: bool


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MaskFitError(message)


def _pixel(rgba: bytes, width: int, x: int, y: int) -> tuple[int, int, int, int]:
    offset = (y * width + x) * 4
    return tuple(rgba[offset : offset + 4])  # type: ignore[return-value]


def fit_visible_mask_rgba(
    rgba: bytes,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> MaskFit:
    """Return an exact 512x512 nearest-neighbour full-U palette mask."""

    _require((width, height) == (CANVAS_WIDTH, CANVAS_HEIGHT),
             "prepared helmet crest masks must be exactly 512x512")
    _require(len(rgba) == width * height * 4,
             "RGBA byte length does not match the declared mask size")
    background = _pixel(rgba, width, 0, 0)
    _require(background[:3] == (0, 0, 0),
             "the prepared mask's top-left background must have zero RGB")

    active_x: list[int] = []
    active_y: list[int] = []
    for y in range(height):
        row = y * width * 4
        for x in range(width):
            offset = row + x * 4
            if rgba[offset] or rgba[offset + 1] or rgba[offset + 2]:
                active_x.append(x)
                active_y.append(y)
            else:
                _require(
                    tuple(rgba[offset : offset + 4]) == background,
                    "inactive mask pixels must share one exact background RGBA value",
                )
    _require(bool(active_x), "the prepared mask has no nonblack visible pixels")

    left, right = min(active_x), max(active_x)
    top, bottom = min(active_y), max(active_y)
    source_width = right - left + 1
    source_height = bottom - top + 1
    _require(source_width >= source_height,
             "the helmet crest mask must be a horizontal wing-shaped region")

    output_width = CANVAS_WIDTH
    output_height = max(
        1,
        min(
            CANVAS_HEIGHT,
            (source_height * output_width + source_width // 2) // source_width,
        ),
    )
    _require(output_height >= source_height,
             "visible-mask fitting must not discard source rows")
    output_top = (CANVAS_HEIGHT - output_height) // 2
    output = bytearray(bytes(background) * (CANVAS_WIDTH * CANVAS_HEIGHT))

    sampled_x: set[int] = set()
    sampled_y: set[int] = set()
    for destination_y in range(output_height):
        source_y = min(
            source_height - 1,
            ((2 * destination_y + 1) * source_height) // (2 * output_height),
        )
        sampled_y.add(source_y)
        for destination_x in range(output_width):
            source_x = min(
                source_width - 1,
                ((2 * destination_x + 1) * source_width) // (2 * output_width),
            )
            sampled_x.add(source_x)
            source_offset = ((top + source_y) * width + left + source_x) * 4
            destination_offset = (
                (output_top + destination_y) * CANVAS_WIDTH + destination_x
            ) * 4
            output[destination_offset : destination_offset + 4] = rgba[
                source_offset : source_offset + 4
            ]

    every_x = len(sampled_x) == source_width
    every_y = len(sampled_y) == source_height
    _require(every_x and every_y,
             "nearest-neighbour fit did not sample every source row and column")
    return MaskFit(
        source_bbox=(left, top, right, bottom),
        source_visible_width=source_width,
        source_visible_height=source_height,
        output_bbox=(0, output_top, CANVAS_WIDTH - 1,
                     output_top + output_height - 1),
        output_visible_width=output_width,
        output_visible_height=output_height,
        output_rgba=bytes(output),
        background_rgba=background,
        source_horizontal_coverage=source_width / width,
        output_horizontal_coverage=1.0,
        every_source_x_sampled=every_x,
        every_source_y_sampled=every_y,
    )


def _load_rgba(path: Path) -> tuple[bytes, bytes]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow ships with the app
        raise MaskFitError("Pillow is required to read the source PNG") from exc
    try:
        info = path.lstat()
    except OSError as exc:
        raise MaskFitError(f"cannot inspect source mask: {exc}") from exc
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             "source mask must be a regular, non-symlink file")
    _require(info.st_size <= MAX_SOURCE_BYTES,
             "source mask exceeds the 64 MiB input limit")
    source_payload = path.read_bytes()
    Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS
    try:
        with Image.open(path) as image:
            image.load()
            _require(image.size == (CANVAS_WIDTH, CANVAS_HEIGHT),
                     "prepared helmet crest mask must decode as 512x512")
            rgba = image.convert("RGBA").tobytes()
    except MaskFitError:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow raises format-specific errors
        raise MaskFitError(f"could not decode source mask: {exc}") from exc
    return source_payload, rgba


def publish(source: Path, output: Path, receipt: Path) -> dict[str, object]:
    """Create new PNG and hash-only receipt; never overwrite either path."""

    source = Path(source).expanduser()
    output = Path(output).expanduser()
    receipt = Path(receipt).expanduser()
    for destination in (output, receipt):
        _require(not destination.exists() and not destination.is_symlink(),
                 f"destination already exists: {destination}")
    source_payload, rgba = _load_rgba(source)
    fitted = fit_visible_mask_rgba(rgba)
    output_payload = encode_rgba_png(
        CANVAS_WIDTH, CANVAS_HEIGHT, fitted.output_rgba,
    )
    document: dict[str, object] = {
        "schema": SCHEMA,
        "source": {
            "path": str(source),
            "png_sha256": hashlib.sha256(source_payload).hexdigest(),
            "decoded_rgba_sha256": hashlib.sha256(rgba).hexdigest(),
            "width": CANVAS_WIDTH,
            "height": CANVAS_HEIGHT,
        },
        "fit": {
            key: value
            for key, value in asdict(fitted).items()
            if key != "output_rgba"
        },
        "result": {
            "path": str(output),
            "png_sha256": hashlib.sha256(output_payload).hexdigest(),
            "decoded_rgba_sha256": hashlib.sha256(fitted.output_rgba).hexdigest(),
            "width": CANVAS_WIDTH,
            "height": CANVAS_HEIGHT,
            "palette_values_preserved_by_nearest_neighbour": True,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(output_payload)
            stream.flush()
            os.fsync(stream.fileno())
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
        raise
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        document = publish(args.source, args.output, args.receipt)
    except (OSError, MaskFitError) as exc:
        parser.exit(2, f"helmet crest mask fit failed: {exc}\n")
    print(json.dumps(document["result"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
