#!/usr/bin/env python3
"""Independently verify the APF helmet crest horizontal guard transform.

The verifier intentionally does not import the guard writer.  It reconstructs
the complete 512x512 output from the semantic pre-guard RGBA bytes and compares
every byte, including both 64-pixel background bands.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import stat
from typing import Any


SCHEMA = "apf2k8_helmet_crest_guard_band_verify/v1"
WRITER_SCHEMA = "apf2k8_helmet_crest_guard_band/v1"
WIDTH = 512
HEIGHT = 512
GUARD_PIXELS = 64
USABLE_WIDTH = WIDTH - 2 * GUARD_PIXELS
U_OFFSET = GUARD_PIXELS / WIDTH
U_SCALE = USABLE_WIDTH / WIDTH
RGBA_LENGTH = WIDTH * HEIGHT * 4
MAX_PNG_BYTES = 64 * 1024 * 1024


class GuardVerifyError(ValueError):
    """The guarded mask is not the exact transform of the source mask."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GuardVerifyError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _pixel(rgba: bytes, x: int, y: int) -> bytes:
    start = (y * WIDTH + x) * 4
    return rgba[start : start + 4]


def _source_x(destination_local_x: int) -> int:
    """Integer nearest-neighbour sample used for one usable output column."""

    return min(
        WIDTH - 1,
        ((2 * destination_local_x + 1) * WIDTH) // (2 * USABLE_WIDTH),
    )


def _active_bbox(rgba: bytes) -> tuple[int, int, int, int]:
    xs: list[int] = []
    ys: list[int] = []
    for y_value in range(HEIGHT):
        for x_value in range(WIDTH):
            pixel = _pixel(rgba, x_value, y_value)
            if pixel[0] or pixel[1] or pixel[2]:
                xs.append(x_value)
                ys.append(y_value)
    _require(bool(xs), "source mask has no active RGB texels")
    return min(xs), min(ys), max(xs), max(ys)


def verify_guard_band(source_rgba: bytes, guarded_rgba: bytes) -> dict[str, Any]:
    """Prove ``guarded_rgba`` is exactly derived from ``source_rgba``.

    Hashes are computed from the supplied bytes.  No particular team logo or
    historical output is pinned by this generic verifier.
    """

    _require(len(source_rgba) == RGBA_LENGTH, "source RGBA length is not 512x512")
    _require(len(guarded_rgba) == RGBA_LENGTH, "guarded RGBA length is not 512x512")
    background = _pixel(source_rgba, 0, 0)
    _require(background[:3] == b"\0\0\0", "source top-left RGB is not background black")
    source_bbox = _active_bbox(source_rgba)

    expected = bytearray(background * (WIDTH * HEIGHT))
    sampled_columns: list[int] = []
    for destination_local_x in range(USABLE_WIDTH):
        source_x = _source_x(destination_local_x)
        sampled_columns.append(source_x)
        destination_x = GUARD_PIXELS + destination_local_x
        for y_value in range(HEIGHT):
            source_start = (y_value * WIDTH + source_x) * 4
            destination_start = (y_value * WIDTH + destination_x) * 4
            expected[destination_start : destination_start + 4] = source_rgba[
                source_start : source_start + 4
            ]
    expected_bytes = bytes(expected)
    if guarded_rgba != expected_bytes:
        first = next(
            index for index, values in enumerate(zip(guarded_rgba, expected_bytes))
            if values[0] != values[1]
        )
        pixel_index = first // 4
        raise GuardVerifyError(
            "guarded RGBA differs from the exact transform at "
            f"x={pixel_index % WIDTH}, y={pixel_index // WIDTH}, channel={first % 4}"
        )

    guarded_bbox = _active_bbox(guarded_rgba)
    _require(
        GUARD_PIXELS <= guarded_bbox[0] <= guarded_bbox[2] < WIDTH - GUARD_PIXELS,
        "active guarded texels escaped the sampler-safe interval",
    )
    left_exact = all(
        guarded_rgba[(y * WIDTH) * 4 : (y * WIDTH + GUARD_PIXELS) * 4]
        == background * GUARD_PIXELS
        for y in range(HEIGHT)
    )
    right_exact = all(
        guarded_rgba[(y * WIDTH + WIDTH - GUARD_PIXELS) * 4 : (y + 1) * WIDTH * 4]
        == background * GUARD_PIXELS
        for y in range(HEIGHT)
    )
    _require(left_exact and right_exact, "one or both guard bands differ from background")

    source_palette = Counter(
        source_rgba[offset : offset + 4]
        for offset in range(0, RGBA_LENGTH, 4)
    )
    guarded_palette = Counter(
        guarded_rgba[offset : offset + 4]
        for offset in range(0, RGBA_LENGTH, 4)
    )
    _require(
        set(guarded_palette) <= set(source_palette),
        "guard transform introduced an RGBA palette value",
    )
    active_source = sum(
        1
        for offset in range(0, RGBA_LENGTH, 4)
        if any(source_rgba[offset : offset + 3])
    )
    active_guarded = sum(
        1
        for offset in range(0, RGBA_LENGTH, 4)
        if any(guarded_rgba[offset : offset + 3])
    )
    sample_counts = Counter(sampled_columns)
    _require(
        min(sampled_columns) == 0 and max(sampled_columns) == WIDTH - 1,
        "nearest-neighbour transform does not sample both source edges",
    )
    _require(
        set(sample_counts.values()) <= {1},
        "guard transform unexpectedly samples a source column more than once",
    )
    return {
        "schema": SCHEMA,
        "verified": True,
        "source": {
            "active_bbox": list(source_bbox),
            "active_texel_count": active_source,
            "rgba_sha256": _sha256(source_rgba),
        },
        "guarded": {
            "active_bbox": list(guarded_bbox),
            "active_texel_count": active_guarded,
            "rgba_sha256": _sha256(guarded_rgba),
        },
        "proof": {
            "background_rgba": list(background),
            "both_guard_bands_exact": True,
            "carrier_u_offset": U_OFFSET,
            "carrier_u_scale": U_SCALE,
            "exact_full_rgba_relation": True,
            "guard_pixels_each_side": GUARD_PIXELS,
            "nearest_source_column_first": min(sampled_columns),
            "nearest_source_column_last": max(sampled_columns),
            "palette_values_preserved": True,
            "sampled_source_column_count": len(sample_counts),
            "usable_width": USABLE_WIDTH,
        },
    }


def load_png_rgba(path: Path, label: str) -> bytes:
    """Read one bounded regular 512x512 PNG as canonical RGBA bytes."""

    try:
        info = path.lstat()
    except OSError as exc:
        raise GuardVerifyError(f"could not inspect {label}: {exc}") from exc
    _require(
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"{label} must be a regular non-symlink file",
    )
    _require(info.st_size <= MAX_PNG_BYTES, f"{label} exceeds 64 MiB")
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = WIDTH * HEIGHT
        with Image.open(path) as image:
            image.load()
            _require(image.size == (WIDTH, HEIGHT), f"{label} is not 512x512")
            return image.convert("RGBA").tobytes()
    except GuardVerifyError:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow has format-specific errors
        raise GuardVerifyError(f"could not decode {label}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--guarded", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = verify_guard_band(
            load_png_rgba(args.source, "source PNG"),
            load_png_rgba(args.guarded, "guarded PNG"),
        )
    except (OSError, GuardVerifyError) as exc:
        parser.exit(2, f"helmet crest guard-band verification failed: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
