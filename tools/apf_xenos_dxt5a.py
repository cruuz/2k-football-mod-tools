#!/usr/bin/env python3
"""Exact Xenos tiled DXT5A transport and a bounded proof encoder.

DXT5A is the alpha half of a BC3 block: two endpoints followed by sixteen
3-bit selectors.  APF's ``digital_font`` presents that scalar through the
fetch swizzle ``1,1,1,A``.  This module deliberately knows nothing about APF
archive targets; target selection and fixed-allocation rebuilding live in
separate tools.
"""

from __future__ import annotations

import hashlib

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_inner


SCHEMA = "apf_xenos_dxt5a/v1"
WIDTH = 128
HEIGHT = 128
PITCH_PIXELS = 128
BLOCK_BYTES = 8
ALLOCATION_BYTES = 8192
ENDIAN_MODE = 1
PRODUCTION_ENCODER_CAVEAT = (
    "The deterministic endpoint encoder is a bounded proof backend, not a "
    "production perceptual alpha compressor; visually inspect replacements "
    "and use a vetted BC4/DXT5A encoder before broad release."
)


class DXT5AError(ValueError):
    """Raised when data leaves the proved 128x128 APF transport class."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def alpha_palette(endpoint_0: int, endpoint_1: int) -> tuple[int, ...]:
    if not (0 <= endpoint_0 <= 255 and 0 <= endpoint_1 <= 255):
        raise DXT5AError("DXT5A endpoint is outside 0..255")
    values = [endpoint_0, endpoint_1]
    if endpoint_0 > endpoint_1:
        values.extend(
            (endpoint_0 * (7 - index) + endpoint_1 * index) // 7
            for index in range(1, 7)
        )
    else:
        values.extend(
            (endpoint_0 * (5 - index) + endpoint_1 * index) // 5
            for index in range(1, 5)
        )
        values.extend((0, 255))
    return tuple(values)


def decode_block(block: bytes) -> tuple[int, ...]:
    if len(block) != BLOCK_BYTES:
        raise DXT5AError("DXT5A block must be exactly 8 bytes")
    palette = alpha_palette(block[0], block[1])
    selectors = int.from_bytes(block[2:8], "little")
    return tuple(palette[(selectors >> (pixel * 3)) & 7] for pixel in range(16))


def encode_block(alphas: tuple[int, ...]) -> tuple[bytes, int]:
    """Encode sixteen alpha samples deterministically, returning squared error."""

    if len(alphas) != 16 or any(type(value) is not int or not 0 <= value <= 255 for value in alphas):
        raise DXT5AError("DXT5A encoder needs sixteen integer alpha samples")
    endpoint_0 = max(alphas)
    endpoint_1 = min(alphas)
    palette = alpha_palette(endpoint_0, endpoint_1)
    selectors = 0
    error = 0
    for pixel, alpha in enumerate(alphas):
        selector = min(
            range(8),
            key=lambda candidate: (abs(alpha - palette[candidate]), candidate),
        )
        difference = alpha - palette[selector]
        error += difference * difference
        selectors |= selector << (pixel * 3)
    return bytes((endpoint_0, endpoint_1)) + selectors.to_bytes(6, "little"), error


def strict_descriptor(metadata: dict[str, object]) -> None:
    required = {
        "vc_file_id": "0x899d899d",
        "vc_width": WIDTH,
        "vc_height": HEIGHT,
        "vc_base_data_length": ALLOCATION_BYTES,
        "vc_mip_data_length": 0,
        "fetch_dwords": [
            "0x810000fe", "0x0000007b", "0x000fe07f",
            "0x00a802da", "0x00000003", "0x00000200",
        ],
        "fetch_type": 2,
        "pitch_pixels": PITCH_PIXELS,
        "tiled": True,
        "format": 59,
        "format_name": "DXT5A",
        "endianness": ENDIAN_MODE,
        "endianness_name": "8in16",
        "stacked": False,
        "width": WIDTH,
        "height": HEIGHT,
        "stack_depth_minus_one": 0,
        "swizzle_components": [5, 5, 5, 0],
        "mip_min_level": 0,
        "mip_max_level": 0,
        "dimension": 1,
        "packed_mips": False,
        "mip_address_pages": 0,
        "warnings": [],
    }
    disagreements = {
        key: (metadata.get(key), expected)
        for key, expected in required.items()
        if metadata.get(key) != expected
    }
    if disagreements:
        raise DXT5AError(f"PORTME: digital_font descriptor changed: {disagreements}")


def extract_linear(tiled: bytes) -> bytes:
    if len(tiled) != ALLOCATION_BYTES:
        raise DXT5AError("digital_font tiled allocation must be exactly 8192 bytes")
    try:
        stored_endian = apf_inner._untile_2d(  # type: ignore[attr-defined]
            tiled, WIDTH, HEIGHT, PITCH_PIXELS, 4, 4, BLOCK_BYTES
        )
        return apf_inner._endian_swap(stored_endian, ENDIAN_MODE)  # type: ignore[attr-defined]
    except apf_inner.FormatError as exc:
        raise DXT5AError(str(exc)) from exc


def insert_linear(linear: bytes) -> bytes:
    if len(linear) != ALLOCATION_BYTES:
        raise DXT5AError("digital_font linear DXT5A must be exactly 8192 bytes")
    stored_endian = apf_inner._endian_swap(linear, ENDIAN_MODE)  # type: ignore[attr-defined]
    result = bytearray(ALLOCATION_BYTES)
    visited: set[int] = set()
    for block_y in range(HEIGHT // 4):
        for block_x in range(WIDTH // 4):
            destination = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                block_x, block_y, PITCH_PIXELS // 4, 3
            )
            if destination in visited or destination + BLOCK_BYTES > len(result):
                raise DXT5AError("Xenos DXT5A tile mapping aliases or leaves bounds")
            visited.add(destination)
            source = (block_y * (WIDTH // 4) + block_x) * BLOCK_BYTES
            result[destination : destination + BLOCK_BYTES] = stored_endian[
                source : source + BLOCK_BYTES
            ]
    if len(visited) * BLOCK_BYTES != ALLOCATION_BYTES:
        raise DXT5AError("Xenos DXT5A tile mapping does not cover the allocation")
    return bytes(result)


def decode_linear_alpha(linear: bytes) -> bytes:
    if len(linear) != ALLOCATION_BYTES:
        raise DXT5AError("linear DXT5A length changed")
    alpha = bytearray(WIDTH * HEIGHT)
    width_blocks = WIDTH // 4
    for block_y in range(HEIGHT // 4):
        for block_x in range(width_blocks):
            block_index = block_y * width_blocks + block_x
            pixels = decode_block(linear[block_index * 8 : block_index * 8 + 8])
            for local_y in range(4):
                for local_x in range(4):
                    destination = (block_y * 4 + local_y) * WIDTH + block_x * 4 + local_x
                    alpha[destination] = pixels[local_y * 4 + local_x]
    return bytes(alpha)


def alpha_to_rgba(alpha: bytes) -> bytes:
    if len(alpha) != WIDTH * HEIGHT:
        raise DXT5AError("digital_font alpha plane length changed")
    return b"".join(bytes((255, 255, 255, value)) for value in alpha)


def rgba_to_alpha(rgba: bytes) -> bytes:
    if len(rgba) != WIDTH * HEIGHT * 4:
        raise DXT5AError("digital_font RGBA length changed")
    if any(rgba[offset : offset + 3] != b"\xff\xff\xff" for offset in range(0, len(rgba), 4)):
        raise DXT5AError(
            "digital_font PNG RGB must be solid white; DXT5A stores alpha only"
        )
    return bytes(rgba[offset + 3] for offset in range(0, len(rgba), 4))


def decode_tiled_rgba(tiled: bytes) -> bytes:
    return alpha_to_rgba(decode_linear_alpha(extract_linear(tiled)))


def replace_changed_blocks(
    original_linear: bytes, wanted_alpha: bytes
) -> tuple[bytes, list[int], int]:
    if len(original_linear) != ALLOCATION_BYTES or len(wanted_alpha) != WIDTH * HEIGHT:
        raise DXT5AError("DXT5A changed-block input length changed")
    original_alpha = decode_linear_alpha(original_linear)
    output = bytearray(original_linear)
    changed: list[int] = []
    total_error = 0
    width_blocks = WIDTH // 4
    for block_y in range(HEIGHT // 4):
        for block_x in range(width_blocks):
            samples = tuple(
                wanted_alpha[(block_y * 4 + local_y) * WIDTH + block_x * 4 + local_x]
                for local_y in range(4)
                for local_x in range(4)
            )
            original = tuple(
                original_alpha[(block_y * 4 + local_y) * WIDTH + block_x * 4 + local_x]
                for local_y in range(4)
                for local_x in range(4)
            )
            if samples == original:
                continue
            encoded, error = encode_block(samples)
            block_index = block_y * width_blocks + block_x
            output[block_index * 8 : block_index * 8 + 8] = encoded
            changed.append(block_index)
            total_error += error
    return bytes(output), changed, total_error

