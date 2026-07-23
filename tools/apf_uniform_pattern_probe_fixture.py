#!/usr/bin/env python3
"""Build the non-retail APF outer-875 orientation/alpha probe fixture.

The input is deliberately limited to two RGB565-exact colors and two exact
BC3 alpha endpoints.  Every boundary lies on the 256-pixel grid, so Pillow's
BOX resize preserves the same 4x4 symbolic pattern all the way down to the
stored 4x4 mip.  This makes the fixture suitable for testing rotation,
mirroring, gross UV placement, alpha use, and mip selection without asking
the project's provisional BC3 encoder to preserve arbitrary artwork.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image, __version__ as PILLOW_VERSION

import apf_inner
import apf_texture_patch


SIZE = 1024
CELL = 256
OPAQUE_RED = (255, 0, 0, 255)
OPAQUE_CYAN = (0, 255, 255, 255)
ALPHA64_CYAN = (0, 255, 255, 64)


class FixtureError(ValueError):
    """Raised when fixture construction is not exactly reproducible."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()


def _png_bytes(image: Image.Image) -> bytes:
    encoded = BytesIO()
    image.save(
        encoded,
        format="PNG",
        compress_level=9,
        optimize=False,
        pnginfo=None,
    )
    return encoded.getvalue()


def _fill_rect(
    rgba: bytearray,
    left: int,
    top: int,
    right: int,
    bottom: int,
    color: tuple[int, int, int, int],
) -> None:
    if not (0 <= left <= right <= SIZE and 0 <= top <= bottom <= SIZE):
        raise FixtureError("rectangle leaves the 1024x1024 fixture")
    row = bytes(color) * (right - left)
    for y in range(top, bottom):
        start = (y * SIZE + left) * 4
        rgba[start : start + len(row)] = row


def _fixture_rgba() -> bytes:
    # The 4x4 symbolic image is:
    #   R R R C
    #   R C C C
    #   R R C C
    #   R C C A
    # R/C are opaque red/cyan; A is cyan with alpha 64.  This is a large F
    # with a unique bottom-right alpha sentinel.
    rgba = bytearray(bytes(OPAQUE_CYAN) * (SIZE * SIZE))
    _fill_rect(rgba, 0, 0, CELL, SIZE, OPAQUE_RED)
    _fill_rect(rgba, 0, 0, CELL * 3, CELL, OPAQUE_RED)
    _fill_rect(rgba, 0, CELL * 2, CELL * 2, CELL * 3, OPAQUE_RED)
    _fill_rect(rgba, CELL * 3, CELL * 3, SIZE, SIZE, ALPHA64_CYAN)
    return bytes(rgba)


def _counter(rgba: bytes) -> Counter[tuple[int, int, int, int]]:
    return Counter(
        tuple(rgba[offset : offset + 4])
        for offset in range(0, len(rgba), 4)
    )


def _level_report(base: Image.Image, level: int) -> dict[str, object]:
    dimension = SIZE >> level
    image = base.resize((dimension, dimension), Image.Resampling.BOX)
    rgba = image.tobytes()
    counts = _counter(rgba)
    expected = {
        OPAQUE_RED: dimension * dimension * 7 // 16,
        OPAQUE_CYAN: dimension * dimension * 8 // 16,
        ALPHA64_CYAN: dimension * dimension * 1 // 16,
    }
    if counts != Counter(expected):
        raise FixtureError(
            f"level {level} does not preserve the 7:8:1 symbolic pattern: {counts}"
        )
    return {
        "level": level,
        "width": dimension,
        "height": dimension,
        "rgba_sha256": _sha256(rgba),
        "pixel_counts": {
            "opaque_red": counts[OPAQUE_RED],
            "opaque_cyan": counts[OPAQUE_CYAN],
            "alpha64_cyan": counts[ALPHA64_CYAN],
        },
    }


def _preview(base: Image.Image) -> Image.Image:
    dimension = 512
    checker = Image.new("RGBA", (dimension, dimension))
    pixels = checker.load()
    for y in range(dimension):
        for x in range(dimension):
            value = 72 if ((x // 32) + (y // 32)) % 2 == 0 else 152
            pixels[x, y] = (value, value, value, 255)
    scaled = base.resize((dimension, dimension), Image.Resampling.NEAREST)
    return Image.alpha_composite(checker, scaled).convert("RGB")


def build(png_path: Path, preview_path: Path, manifest_path: Path) -> None:
    outputs = (png_path, preview_path, manifest_path)
    if len({path.resolve(strict=False) for path in outputs}) != len(outputs):
        raise FixtureError("output paths must be distinct")
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FixtureError(f"refusing existing output(s): {existing}")
    if any(not path.parent.is_dir() for path in outputs):
        raise FixtureError("all output parent directories must already exist")

    rgba = _fixture_rgba()
    base = Image.frombytes("RGBA", (SIZE, SIZE), rgba)
    levels = [_level_report(base, level) for level in range(9)]

    # Level 8 is exactly one 4x4 BC3 block.  Requiring an exact encode/decode
    # proves that this specific fixture's two colors and alpha-64 sentinel are
    # lossless through the writer's existing alpha path.
    level8 = base.resize((4, 4), Image.Resampling.BOX).tobytes()
    level8_pixels = [
        tuple(level8[offset : offset + 4]) for offset in range(0, len(level8), 4)
    ]
    bc3 = apf_texture_patch.encode_bc3_block(level8_pixels)  # type: ignore[arg-type]
    decoded = bytes(
        component
        for pixel in apf_inner._decode_bc3(bc3)  # type: ignore[attr-defined]
        for component in pixel
    )
    if decoded != level8:
        raise FixtureError("level-8 BC3 alpha/color encode/decode is not exact")

    png_data = _png_bytes(base)
    preview_data = _png_bytes(_preview(base))
    document = {
        "schema": "apf_uniform_pattern_probe_fixture/v1",
        "claim_boundary": (
            "Non-retail diagnostic fixture only. Offline exactness proves the "
            "writer's RGBA/BC3/H7A transport for this pattern; runtime UV, "
            "material alpha use, mip selection, and hardware fidelity require "
            "a matched emulator or console capture."
        ),
        "geometry": {
            "size": [SIZE, SIZE],
            "cell_size": CELL,
            "symbolic_rows": ["RRRC", "RCCC", "RRCC", "RCCA"],
            "meaning": {
                "R": list(OPAQUE_RED),
                "C": list(OPAQUE_CYAN),
                "A": list(ALPHA64_CYAN),
            },
            "orientation_cue": "large red F",
            "alpha_sentinel": {
                "rectangle_xyxy": [768, 768, 1024, 1024],
                "rgba": list(ALPHA64_CYAN),
                "outside_alpha": 255,
            },
        },
        "mips": {
            "filter": "Pillow BOX directly from the 1024x1024 base",
            "levels": levels,
            "all_boundaries_preserved": True,
            "level_8_single_bc3_block_encode_decode_exact": True,
            "level_8_bc3_sha256": _sha256(bc3),
        },
        "input": {
            "path": str(png_path),
            "mode": "RGBA",
            "size": [SIZE, SIZE],
            "rgba_sha256": _sha256(rgba),
            "png_sha256": _sha256(png_data),
            "png_size": len(png_data),
        },
        "preview": {
            "path": str(preview_path),
            "description": "512x512 nearest-neighbor composite over a checkerboard",
            "png_sha256": _sha256(preview_data),
            "png_size": len(preview_data),
        },
        "backend": {
            "pillow": PILLOW_VERSION,
            "bc3": "project-native deterministic proof encoder",
        },
    }
    manifest_data = (json.dumps(document, indent=2) + "\n").encode("utf-8")

    _write_new(png_path, png_data)
    _write_new(preview_path, preview_data)
    _write_new(manifest_path, manifest_data)
    print(
        "APF_UNIFORM_PATTERN_FIXTURE_PASS "
        f"rgba_sha256={document['input']['rgba_sha256']} "  # type: ignore[index]
        f"png_sha256={document['input']['png_sha256']}"  # type: ignore[index]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--preview", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        build(args.png.expanduser(), args.preview.expanduser(), args.manifest.expanduser())
    except (FixtureError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
