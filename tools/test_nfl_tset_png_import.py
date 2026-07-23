#!/usr/bin/env python3
"""Unit and bounded-integration tests for the 09H0 PNG importer."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import zlib

from nfl_tset_diagnostic_png import build_rgba
from nfl_tset_png_import import (
    ImportError,
    MipLevel,
    decode_rgba_png,
    derive_mud_palette,
    generate_mips,
    palette_for_shared_mud,
    quantize_levels,
    rgba_from_indices,
)
from nfl_txtr import (
    PNG_SIGNATURE,
    encode_rgba_png,
    png_chunk,
    swizzle_2d,
    unswizzle_2d,
)


ROOT = Path(__file__).resolve().parents[1]


def expect_import_error(callback, label: str) -> None:
    try:
        callback()
    except ImportError:
        return
    raise AssertionError(f"{label} did not fail closed")


def filtered_png(width: int, height: int, rgba: bytes, filter_type: int) -> bytes:
    row_bytes = width * 4
    encoded_rows = []
    previous = bytes(row_bytes)
    for y in range(height):
        row = rgba[y * row_bytes:(y + 1) * row_bytes]
        encoded = bytearray(row_bytes)
        for x, value in enumerate(row):
            left = row[x - 4] if x >= 4 else 0
            up = previous[x]
            upper_left = previous[x - 4] if x >= 4 else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            else:
                estimate = left + up - upper_left
                distances = (
                    (abs(estimate - left), 0, left),
                    (abs(estimate - up), 1, up),
                    (abs(estimate - upper_left), 2, upper_left),
                )
                predictor = min(distances)[2]
            encoded[x] = (value - predictor) & 0xFF
        encoded_rows.append(bytes((filter_type,)) + bytes(encoded))
        previous = row
    return (
        PNG_SIGNATURE
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(b"".join(encoded_rows), level=9))
        + png_chunk(b"IEND", b"")
    )


def main() -> int:
    # Exact inverse for every pinned rectangular mip and multiple texel sizes.
    for width, height in ((512, 256), (256, 128), (128, 64),
                          (64, 32), (32, 16), (16, 8)):
        for bytes_per_pixel in (1, 4):
            linear = bytes(
                (index * 37 + width + height + bytes_per_pixel) & 0xFF
                for index in range(width * height * bytes_per_pixel)
            )
            swizzled = swizzle_2d(linear, width, height, bytes_per_pixel)
            assert unswizzle_2d(swizzled, width, height, bytes_per_pixel) == linear

    # The strict decoder reverses every standard PNG row filter.
    width, height = 7, 5
    small = bytes((index * 29 + 7) & 0xFF for index in range(width * height * 4))
    for filter_type in range(5):
        payload = filtered_png(width, height, small, filter_type)
        assert decode_rgba_png(payload, (width, height)) == (width, height, small)

    diagnostic = build_rgba()
    payload = encode_rgba_png(512, 256, diagnostic)
    assert decode_rgba_png(payload) == (512, 256, diagnostic)
    levels = generate_mips(diagnostic, 512, 256)
    assert [(level.width, level.height) for level in levels] == [
        (512, 256), (256, 128), (128, 64), (64, 32), (32, 16), (16, 8)
    ]
    palette, indices, stats = quantize_levels(levels)
    assert len(palette) == 32
    assert stats == {
        "input_unique_rgba_colors": 32,
        "palette_entries": 32,
        "total_squared_rgba_error": 0,
        "maximum_channel_error": 0,
        "differing_pixel_count": 0,
        "total_pixel_count": 174720,
    }
    assert [rgba_from_indices(index, palette) for index in indices] == \
        [level.rgba for level in levels]
    dark = derive_mud_palette(palette, "darken_60")
    assert all(
        mud == ((clean[0] * 3 + 2) // 5, (clean[1] * 3 + 2) // 5,
                (clean[2] * 3 + 2) // 5, clean[3])
        for clean, mud in zip(palette, dark)
    )

    # Exact second-PNG mode accepts a genuinely shared mapping and rejects a
    # single source image whose colors conflict for an already shared index.
    exact_mud = [
        MipLevel(level.level, level.width, level.height,
                 rgba_from_indices(index, dark))
        for level, index in zip(levels, indices)
    ]
    shared = palette_for_shared_mud(indices, exact_mud)
    assert shared[:len(dark)] == dark
    incompatible = list(exact_mud)
    damaged = bytearray(incompatible[0].rgba)
    damaged[0] ^= 1
    incompatible[0] = MipLevel(0, 512, 256, bytes(damaged))
    expect_import_error(
        lambda: palette_for_shared_mud(indices, incompatible),
        "incompatible second PNG shared indices",
    )

    # A >256-color fixture is deterministic and bounded to 256 entries.
    colors = bytes(
        channel
        for index in range(1024)
        for channel in (index & 0xFF, (index >> 2) & 0xFF,
                        (index * 11) & 0xFF, 255)
    )
    synthetic_level = [MipLevel(0, 32, 32, colors)]
    first_palette, first_indices, first_stats = quantize_levels(synthetic_level)
    second_palette, second_indices, second_stats = quantize_levels(synthetic_level)
    assert first_palette == second_palette and first_indices == second_indices
    assert first_stats == second_stats and len(first_palette) <= 256

    manifest = json.loads(
        (ROOT / "reports/assets/nfl2k5_lions_09H0_diagnostic_png_import.json")
        .read_text(encoding="utf-8")
    )
    assert manifest["compression"]["encoded_bytes"] == 22285
    assert manifest["rebuild"]["zero_padding_bytes"] == 52403
    assert manifest["claims"]["xiso_created"] is False

    print(
        "NFL_TSET_PNG_IMPORT_TESTS_PASS swizzle_pairs=12 png_filters=5 "
        "mips=6 diagnostic_colors=32 quantization_error=0 "
        "second_png_rejection=true median_cut_deterministic=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
