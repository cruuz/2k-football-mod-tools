#!/usr/bin/env python3
"""Deterministic opaque DXT1 encoder for proved NFL 2K5 texture layouts.

The retail live-player face/head textures use linear DXT1 blocks.  This module
deliberately implements only opaque four-colour mode: callers must reject PNGs
with transparency instead of silently changing alpha semantics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import struct


class Dxt1Error(ValueError):
    """Raised when an input cannot be represented by the strict encoder."""


@dataclass(frozen=True)
class Dxt1EncodeInfo:
    width: int
    height: int
    block_count: int
    encoded_bytes: int
    endpoint_pair_evaluations: int
    selector_evaluations: int
    total_squared_rgb_error: int
    alpha_policy: str
    endpoint_search: str
    selector_tie_break: str


def rgb_to_565(red: int, green: int, blue: int) -> int:
    """Quantize RGB8 with deterministic round-to-nearest component mapping."""

    return (
        ((red * 31 + 127) // 255) << 11
        | ((green * 63 + 127) // 255) << 5
        | ((blue * 31 + 127) // 255)
    )


def rgb_from_565(value: int) -> tuple[int, int, int]:
    red5 = (value >> 11) & 0x1F
    green6 = (value >> 5) & 0x3F
    blue5 = value & 0x1F
    return (
        (red5 << 3) | (red5 >> 2),
        (green6 << 2) | (green6 >> 4),
        (blue5 << 3) | (blue5 >> 2),
    )


def opaque_palette(color0: int, color1: int) \
        -> tuple[tuple[int, int, int], ...]:
    if not 0 <= color1 < color0 <= 0xFFFF:
        raise Dxt1Error("opaque DXT1 endpoints must satisfy color0 > color1")
    first = rgb_from_565(color0)
    second = rgb_from_565(color1)
    return (
        first,
        second,
        tuple((2 * first[channel] + second[channel]) // 3 for channel in range(3)),
        tuple((first[channel] + 2 * second[channel]) // 3 for channel in range(3)),
    )


def endpoint_pairs(pixels: tuple[tuple[int, int, int], ...]) \
        -> tuple[tuple[int, int], ...]:
    quantized = sorted({rgb_to_565(*pixel) for pixel in pixels})
    candidates = set()
    for first_index, first in enumerate(quantized):
        for second in quantized[:first_index]:
            candidates.add((first, second))

    # Channel-box endpoints add one useful pair when no two source colours lie
    # near the ideal interpolation axis.  The set and final sort make all tie
    # behavior independent of Python hash iteration order.
    maximum = rgb_to_565(
        max(pixel[0] for pixel in pixels),
        max(pixel[1] for pixel in pixels),
        max(pixel[2] for pixel in pixels),
    )
    minimum = rgb_to_565(
        min(pixel[0] for pixel in pixels),
        min(pixel[1] for pixel in pixels),
        min(pixel[2] for pixel in pixels),
    )
    if maximum != minimum:
        candidates.add((max(maximum, minimum), min(maximum, minimum)))

    if not candidates:
        only = quantized[0]
        candidates.add((only + 1, only) if only < 0xFFFF else (only, only - 1))
    return tuple(sorted(candidates))


def encode_block(pixels: tuple[tuple[int, int, int], ...]) \
        -> tuple[bytes, int, int, int]:
    if len(pixels) != 16:
        raise Dxt1Error("a DXT1 block requires exactly sixteen RGB pixels")
    best: tuple[int, int, int, int] | None = None
    pair_count = 0
    selector_count = 0
    for color0, color1 in endpoint_pairs(pixels):
        pair_count += 1
        palette = opaque_palette(color0, color1)
        selectors = 0
        error = 0
        for pixel_index, pixel in enumerate(pixels):
            scored = []
            for selector, color in enumerate(palette):
                selector_count += 1
                scored.append((
                    sum((pixel[channel] - color[channel]) ** 2
                        for channel in range(3)),
                    selector,
                ))
            pixel_error, selector = min(scored)
            error += pixel_error
            selectors |= selector << (2 * pixel_index)
        candidate = (error, color0, color1, selectors)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    error, color0, color1, selectors = best
    return struct.pack("<HHI", color0, color1, selectors), error, pair_count, selector_count


def encode_dxt1_opaque(rgba: bytes, width: int, height: int) \
        -> tuple[bytes, Dxt1EncodeInfo]:
    """Encode exact RGBA8 pixels as linear opaque DXT1 blocks.

    Edge pixels are clamped for non-multiple-of-four dimensions.  Every alpha
    byte must be 255; binary/one-bit alpha is intentionally not inferred.
    """

    if width <= 0 or height <= 0:
        raise Dxt1Error("DXT1 dimensions must be positive")
    if len(rgba) != width * height * 4:
        raise Dxt1Error("RGBA byte count does not match DXT1 dimensions")
    if any(rgba[offset] != 255 for offset in range(3, len(rgba), 4)):
        raise Dxt1Error(
            "live face/head PNG must be fully opaque; transparent DXT1 mode is unsupported"
        )

    encoded = bytearray()
    total_error = 0
    total_pairs = 0
    total_selectors = 0
    block_width = (width + 3) // 4
    block_height = (height + 3) // 4
    for block_y in range(block_height):
        for block_x in range(block_width):
            pixels = []
            for local_y in range(4):
                y = min(block_y * 4 + local_y, height - 1)
                for local_x in range(4):
                    x = min(block_x * 4 + local_x, width - 1)
                    offset = (y * width + x) * 4
                    pixels.append(tuple(rgba[offset:offset + 3]))
            block, error, pairs, selectors = encode_block(tuple(pixels))
            encoded.extend(block)
            total_error += error
            total_pairs += pairs
            total_selectors += selectors

    expected = block_width * block_height * 8
    if len(encoded) != expected:
        raise Dxt1Error("internal DXT1 encoded-size mismatch")
    info = Dxt1EncodeInfo(
        width=width,
        height=height,
        block_count=block_width * block_height,
        encoded_bytes=len(encoded),
        endpoint_pair_evaluations=total_pairs,
        selector_evaluations=total_selectors,
        total_squared_rgb_error=total_error,
        alpha_policy="require_all_255_opaque_four_colour_mode",
        endpoint_search="unique_rgb565_pairs_plus_channel_box",
        selector_tie_break="minimum_squared_rgb_error_then_lowest_selector",
    )
    return bytes(encoded), info


def info_dict(info: Dxt1EncodeInfo) -> dict[str, object]:
    """Small convenience for JSON-producing callers."""

    return asdict(info)
