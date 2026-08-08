"""Linear (untiled) uncompressed TXTR PNG decode."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_inner  # noqa: E402


class LinearTxtrUnitTests(unittest.TestCase):
    def test_linear_8888_solid_magenta(self) -> None:
        # 2×2, pitch=2, BGRA little-endian 8_8_8_8 (format 6), no tiling.
        # endianness 0 = none; swizzle identity.
        w = h = 2
        # Little-endian RGBA bytes as stored after swap path with endian 0:
        # store as R,G,B,A per pixel for identity.
        row = bytes([255, 0, 255, 255]) * w  # magenta opaque
        base = row * h
        meta = {
            "width": w,
            "height": h,
            "pitch_pixels": w,
            "format": 6,
            "format_name": "8_8_8_8",
            "endianness": 0,
            "swizzle_components": [0, 1, 2, 3],
            "dimension": 1,
            "stacked": False,
            "tiled": False,
        }
        width, height, rgba = apf_inner.decode_txtr_base_rgba(meta, base)
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(len(rgba), 16)
        # First pixel RGBA
        self.assertEqual(tuple(rgba[0:4]), (255, 0, 255, 255))

    def test_linear_dxt1_solid_white_block(self) -> None:
        """Linear (untiled) DXT1: one 4×4 block, all indices → color0 white."""
        import struct

        # color0 = 0xFFFF (white 5:6:5), color1 = 0x0000, indices all 0
        block = struct.pack("<HHI", 0xFFFF, 0x0000, 0)
        meta = {
            "width": 4,
            "height": 4,
            "pitch_pixels": 4,
            "format": 18,
            "format_name": "DXT1",
            "endianness": 0,
            "swizzle_components": [0, 1, 2, 3],
            "dimension": 1,
            "stacked": False,
            "tiled": False,
        }
        width, height, rgba = apf_inner.decode_txtr_base_rgba(meta, block)
        self.assertEqual((width, height), (4, 4))
        self.assertEqual(len(rgba), 4 * 4 * 4)
        # First pixel ≈ white opaque
        self.assertEqual(tuple(rgba[0:4]), (255, 255, 255, 255))

    def test_linear_dxt1_pitch_padding(self) -> None:
        """Linear DXT1 with pitch wider than width packs only used blocks."""
        import struct

        solid = struct.pack("<HHI", 0xF800, 0x0000, 0)  # red 5:6:5 as color0
        # pitch 8 pixels → 2 blocks per row; height 4 → 1 block row; pad block zeros
        base = solid + (b"\0" * 8)
        meta = {
            "width": 4,
            "height": 4,
            "pitch_pixels": 8,
            "format": 18,
            "format_name": "DXT1",
            "endianness": 0,
            "swizzle_components": [0, 1, 2, 3],
            "dimension": 1,
            "stacked": False,
            "tiled": False,
        }
        width, height, rgba = apf_inner.decode_txtr_base_rgba(meta, base)
        self.assertEqual((width, height), (4, 4))
        # 5:6:5 red (0xF800) expands to (255, 0, 0) via _rgb565 bit expand
        self.assertEqual(tuple(rgba[0:4]), (255, 0, 0, 255))


if __name__ == "__main__":
    unittest.main()
