#!/usr/bin/env python3
"""Add a sampler-safe horizontal guard band to an APF helmet crest mask.

The shell carrier remaps its U coordinates with the same affine transform,
``guard_u + usable_u * source_u``.  Compressing the prepared 512-pixel mask
into that interval therefore leaves the logo's physical helmet placement
unchanged while ensuring every carrier vertex samples inside texture space.

Sampling is explicit integer nearest-neighbour so palette bytes remain exact.
The writer is bounded, fail-closed, and never overwrites its outputs.
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


SCHEMA = "apf2k8_helmet_crest_guard_band/v1"
CANVAS_WIDTH = 512
CANVAS_HEIGHT = 512
GUARD_PIXELS = 64
USABLE_WIDTH = CANVAS_WIDTH - 2 * GUARD_PIXELS
U_OFFSET = GUARD_PIXELS / CANVAS_WIDTH
U_SCALE = USABLE_WIDTH / CANVAS_WIDTH
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_PIXELS = CANVAS_WIDTH * CANVAS_HEIGHT


class GuardBandError(RuntimeError):
    """The input is not a bounded palette mask or cannot be guarded."""


@dataclass(frozen=True)
class GuardBand:
    output_rgba: bytes
    source_active_bbox: tuple[int, int, int, int]
    output_active_bbox: tuple[int, int, int, int]
    background_rgba: tuple[int, int, int, int]
    guard_pixels_each_side: int
    usable_width: int
    carrier_u_offset: float
    carrier_u_scale: float
    palette_values_preserved: bool


@dataclass(frozen=True)
class PreparedGuardBand:
    """Decoded semantic design plus its deterministic build-time transport."""

    design_rgba: bytes
    guarded_png: bytes
    guard: GuardBand


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GuardBandError(message)


def _pixel(
    rgba: bytes, x: int, y: int,
) -> tuple[int, int, int, int]:
    offset = (y * CANVAS_WIDTH + x) * 4
    return tuple(rgba[offset : offset + 4])  # type: ignore[return-value]


def _active_bbox(rgba: bytes) -> tuple[int, int, int, int]:
    xs: list[int] = []
    ys: list[int] = []
    for y in range(CANVAS_HEIGHT):
        row = y * CANVAS_WIDTH * 4
        for x in range(CANVAS_WIDTH):
            offset = row + x * 4
            if rgba[offset] or rgba[offset + 1] or rgba[offset + 2]:
                xs.append(x)
                ys.append(y)
    _require(bool(xs), "the prepared mask has no nonblack visible pixels")
    return min(xs), min(ys), max(xs), max(ys)


def add_horizontal_guard(rgba: bytes) -> GuardBand:
    """Return a 512x512 mask compressed into the sampler-safe U interval."""

    _require(
        len(rgba) == CANVAS_WIDTH * CANVAS_HEIGHT * 4,
        "RGBA byte length does not describe a 512x512 mask",
    )
    background = _pixel(rgba, 0, 0)
    _require(
        background[:3] == (0, 0, 0),
        "the prepared mask's top-left background must have zero RGB",
    )
    source_bbox = _active_bbox(rgba)
    output = bytearray(bytes(background) * (CANVAS_WIDTH * CANVAS_HEIGHT))
    sampled_x: set[int] = set()
    for destination_local_x in range(USABLE_WIDTH):
        source_x = min(
            CANVAS_WIDTH - 1,
            ((2 * destination_local_x + 1) * CANVAS_WIDTH) // (2 * USABLE_WIDTH),
        )
        sampled_x.add(source_x)
        destination_x = GUARD_PIXELS + destination_local_x
        for y in range(CANVAS_HEIGHT):
            source_offset = (y * CANVAS_WIDTH + source_x) * 4
            destination_offset = (y * CANVAS_WIDTH + destination_x) * 4
            output[destination_offset : destination_offset + 4] = rgba[
                source_offset : source_offset + 4
            ]
    output_bytes = bytes(output)
    output_bbox = _active_bbox(output_bytes)
    _require(
        GUARD_PIXELS <= output_bbox[0] <= output_bbox[2] < CANVAS_WIDTH - GUARD_PIXELS,
        "guarded visible pixels escaped the safe U interval",
    )
    source_palette = {
        rgba[offset : offset + 4] for offset in range(0, len(rgba), 4)
    }
    output_palette = {
        output_bytes[offset : offset + 4]
        for offset in range(0, len(output_bytes), 4)
    }
    _require(
        output_palette <= source_palette,
        "nearest-neighbour guard introduced a palette value",
    )
    return GuardBand(
        output_rgba=output_bytes,
        source_active_bbox=source_bbox,
        output_active_bbox=output_bbox,
        background_rgba=background,
        guard_pixels_each_side=GUARD_PIXELS,
        usable_width=USABLE_WIDTH,
        carrier_u_offset=U_OFFSET,
        carrier_u_scale=U_SCALE,
        palette_values_preserved=True,
    )


def _load(path: Path) -> tuple[bytes, bytes]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow ships with the app
        raise GuardBandError("Pillow is required to read the source PNG") from exc
    try:
        info = path.lstat()
    except OSError as exc:
        raise GuardBandError(f"cannot inspect source mask: {exc}") from exc
    _require(
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        "source mask must be a regular, non-symlink file",
    )
    _require(info.st_size <= MAX_SOURCE_BYTES, "source mask exceeds 64 MiB")
    payload = path.read_bytes()
    Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS
    try:
        with Image.open(path) as image:
            image.load()
            _require(
                image.size == (CANVAS_WIDTH, CANVAS_HEIGHT),
                "prepared mask must decode as 512x512",
            )
            rgba = image.convert("RGBA").tobytes()
    except GuardBandError:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow raises format-specific errors
        raise GuardBandError(f"could not decode source mask: {exc}") from exc
    return payload, rgba


def prepare_rgba(design_rgba: bytes) -> PreparedGuardBand:
    """Return the semantic RGBA design and deterministic guarded transport."""

    guard = add_horizontal_guard(design_rgba)
    return PreparedGuardBand(
        design_rgba=bytes(design_rgba),
        guarded_png=encode_rgba_png(
            CANVAS_WIDTH, CANVAS_HEIGHT, guard.output_rgba
        ),
        guard=guard,
    )


def prepare_png(source: Path) -> PreparedGuardBand:
    """Validate one prepared PNG and return its in-memory guarded transport.

    The semantic design remains unguarded so callers can persist it in a
    project without accumulating a second horizontal compression on reload.
    Both texture consumers must receive ``guarded_png`` from this one result.
    """

    _payload, design_rgba = _load(Path(source))
    return prepare_rgba(design_rgba)


def publish(source: Path, output: Path, receipt: Path) -> dict[str, object]:
    """Write one new guarded PNG and hash-only receipt; never overwrite."""

    source, output, receipt = map(
        lambda value: Path(value).expanduser(), (source, output, receipt)
    )
    for destination in (output, receipt):
        _require(
            not destination.exists() and not destination.is_symlink(),
            f"destination already exists: {destination}",
        )
    source_payload, source_rgba = _load(source)
    prepared = prepare_rgba(source_rgba)
    result = prepared.guard
    output_payload = prepared.guarded_png
    document = {
        "schema": SCHEMA,
        "source": {
            "path": str(source),
            "png_sha256": hashlib.sha256(source_payload).hexdigest(),
            "rgba_sha256": hashlib.sha256(source_rgba).hexdigest(),
        },
        "guard": {
            key: value
            for key, value in asdict(result).items()
            if key != "output_rgba"
        },
        "result": {
            "path": str(output),
            "png_sha256": hashlib.sha256(output_payload).hexdigest(),
            "rgba_sha256": hashlib.sha256(result.output_rgba).hexdigest(),
            "width": CANVAS_WIDTH,
            "height": CANVAS_HEIGHT,
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
    except (GuardBandError, OSError) as exc:
        parser.exit(2, f"helmet crest guard-band failed: {exc}\n")
    print(json.dumps(document["result"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
