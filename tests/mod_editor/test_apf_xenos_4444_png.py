"""Regression: Xenos format 15 (4_4_4_4) decodes through shipped apf_inner.

logo_l0 / logo_l1 are format 15. beta-27 fixed PNG conversion that used to
raise PORTME. This test builds a tiny tiled base and drives
``decode_txtr_base_rgba`` + ``write_rgba_png`` — the same path asset_io uses —
without requiring a retail 0A.
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import apf_inner  # noqa: E402


def _pack_4444(a: int, r: int, g: int, b: int) -> int:
    # The writer's retail-proven convention (apf_logo_patch round-trip):
    # red in the LOW nibble, blue at bits 8-11.
    return ((a & 0xF) << 12) | ((b & 0xF) << 8) | ((g & 0xF) << 4) | (r & 0xF)


def _tile_linear(
    linear: bytes,
    width: int,
    height: int,
    pitch_pixels: int,
    bytes_per_block: int,
) -> bytes:
    """Inverse of ``apf_inner._untile_2d`` for 1×1 blocks (raw texels)."""

    width_blocks = width
    height_blocks = height
    pitch_blocks = pitch_pixels
    pitch_blocks_aligned = apf_inner._align_up(pitch_blocks, 32)
    height_blocks_aligned = apf_inner._align_up(height_blocks, 32)
    required = pitch_blocks_aligned * height_blocks_aligned * bytes_per_block
    tiled = bytearray(required)
    log2_size = bytes_per_block.bit_length() - 1
    for y in range(height_blocks):
        for x in range(width_blocks):
            src = (y * width_blocks + x) * bytes_per_block
            dest = apf_inner._tiled_2d_offset(x, y, pitch_blocks_aligned, log2_size)
            tiled[dest : dest + bytes_per_block] = linear[src : src + bytes_per_block]
    return bytes(tiled)


class Format15PngDecodeTests(unittest.TestCase):
    def test_format_15_is_registered_as_4_4_4_4(self) -> None:
        self.assertEqual(apf_inner.XENOS_FORMATS[15], "4_4_4_4")

    def test_decode_txtr_base_rgba_expands_nibbles(self) -> None:
        width = height = 4
        pitch = 32
        # Opaque red: A=F R=F G=0 B=0 → 8-bit 0xFF,0xFF,0x00,0x00 after expand
        value = _pack_4444(0xF, 0xF, 0x0, 0x0)
        linear = bytearray(width * height * 2)
        for i in range(width * height):
            linear[i * 2 : i * 2 + 2] = struct.pack("<H", value)
        base = _tile_linear(bytes(linear), width, height, pitch, 2)
        metadata = {
            "width": width,
            "height": height,
            "pitch_pixels": pitch,
            "format": 15,
            "format_name": "4_4_4_4",
            "endianness": 0,
            "swizzle_components": [0, 1, 2, 3],
            "dimension": 1,
            "stacked": False,
            "tiled": True,
        }
        out_w, out_h, rgba = apf_inner.decode_txtr_base_rgba(metadata, base)
        self.assertEqual((out_w, out_h), (width, height))
        self.assertEqual(len(rgba), width * height * 4)
        # First pixel: expanded nibbles as RGBA (R=F, G=0, B=0, A=F)
        self.assertEqual(tuple(rgba[0:4]), (0xFF, 0x00, 0x00, 0xFF))

    def test_decode_does_not_raise_portme_for_format_15(self) -> None:
        width = height = 8
        pitch = 32
        linear = bytearray(width * height * 2)
        for i in range(width * height):
            linear[i * 2 : i * 2 + 2] = struct.pack("<H", _pack_4444(0xF, 0xA, 0x5, 0x0))
        base = _tile_linear(bytes(linear), width, height, pitch, 2)
        metadata = {
            "width": width,
            "height": height,
            "pitch_pixels": pitch,
            "format": 15,
            "format_name": "4_4_4_4",
            "endianness": 1,  # 8-in-16 common on Xenos
            "swizzle_components": [0, 1, 2, 3],
            "dimension": 1,
            "stacked": False,
            "tiled": True,
        }
        # Endian swap on linear before tile for mode 1
        swapped = apf_inner._endian_swap(bytes(linear), 1)
        # Put endian-swapped samples through tile as the base would store them
        base = _tile_linear(swapped, width, height, pitch, 2)
        try:
            out_w, out_h, rgba = apf_inner.decode_txtr_base_rgba(metadata, base)
        except apf_inner.FormatError as exc:
            self.fail(f"format 15 must not PORTME: {exc}")
        self.assertEqual((out_w, out_h), (width, height))
        self.assertEqual(len(rgba), width * height * 4)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "logo.png"
            apf_inner.write_rgba_png(path, out_w, out_h, rgba)
            with Image.open(path) as image:
                image.load()
                self.assertEqual(image.size, (width, height))
                self.assertEqual(image.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
