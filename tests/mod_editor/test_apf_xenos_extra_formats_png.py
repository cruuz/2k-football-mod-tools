"""PNG decode for additional Xenos formats that block community previews.

Formats 3 (1_5_5_5), 4 (5_6_5), 2 (8), and 10 (8_8) previously raised
PORTME for PNG conversion. Real field-art weather textures and kit assets
use several of these. Tests drive shipped ``decode_txtr_base_rgba``.
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


def _tile_linear(
    linear: bytes,
    width: int,
    height: int,
    pitch_pixels: int,
    bytes_per_block: int,
) -> bytes:
    width_blocks = width
    height_blocks = height
    pitch_blocks_aligned = apf_inner._align_up(pitch_pixels, 32)
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


def _meta(fmt: int, name: str, w: int = 4, h: int = 4, pitch: int = 32) -> dict:
    return {
        "width": w,
        "height": h,
        "pitch_pixels": pitch,
        "format": fmt,
        "format_name": name,
        "endianness": 0,
        "swizzle_components": [0, 1, 2, 3],
        "dimension": 1,
        "stacked": False,
        "tiled": True,
    }


class ExtraFormatPngDecodeTests(unittest.TestCase):
    def test_5_6_5_decodes_opaque_rgb(self) -> None:
        # Pure red in 565: R=31 G=0 B=0 → 0xF800
        linear = bytearray(4 * 4 * 2)
        for i in range(16):
            linear[i * 2 : i * 2 + 2] = struct.pack("<H", 0xF800)
        base = _tile_linear(bytes(linear), 4, 4, 32, 2)
        w, h, rgba = apf_inner.decode_txtr_base_rgba(_meta(4, "5_6_5"), base)
        self.assertEqual((w, h), (4, 4))
        self.assertEqual(rgba[0], 255)  # R expanded
        self.assertEqual(rgba[1], 0)
        self.assertEqual(rgba[2], 0)
        self.assertEqual(rgba[3], 255)

    def test_1_5_5_5_decodes_alpha_bit(self) -> None:
        # Opaque white: A=1 R=G=B=31 → 0xFFFF
        linear = bytearray(4 * 4 * 2)
        for i in range(16):
            linear[i * 2 : i * 2 + 2] = struct.pack("<H", 0xFFFF)
        base = _tile_linear(bytes(linear), 4, 4, 32, 2)
        w, h, rgba = apf_inner.decode_txtr_base_rgba(_meta(3, "1_5_5_5"), base)
        self.assertEqual(rgba[0:4], bytes((255, 255, 255, 255)))

    def test_8_bit_luma_decodes(self) -> None:
        linear = bytes([200] * 16)
        base = _tile_linear(linear, 4, 4, 32, 1)
        w, h, rgba = apf_inner.decode_txtr_base_rgba(_meta(2, "8"), base)
        self.assertEqual(rgba[0:4], bytes((200, 200, 200, 255)))

    def test_8_8_decodes_two_channels(self) -> None:
        linear = bytearray(4 * 4 * 2)
        for i in range(16):
            linear[i * 2] = 10
            linear[i * 2 + 1] = 20
        base = _tile_linear(bytes(linear), 4, 4, 32, 2)
        w, h, rgba = apf_inner.decode_txtr_base_rgba(_meta(10, "8_8"), base)
        self.assertEqual(rgba[0:4], bytes((10, 20, 0, 255)))

    def test_portme_message_names_unsupported_format(self) -> None:
        linear = bytes(4 * 4 * 4)
        base = _tile_linear(linear, 4, 4, 32, 4)
        meta = _meta(7, "2_10_10_10")
        # format 7 still PORTME (4-byte but not 8888 path without packing)
        # Use format that stays blocked: 49 DXN is separate path; use 7
        meta["format"] = 7
        meta["format_name"] = "2_10_10_10"
        # 2_10_10_10 is 4 bytes/texel - not in our implemented set for PNG
        # Force via wrong block size path - actually format 7 not in if chain → PORTME
        with self.assertRaises(apf_inner.FormatError) as ctx:
            # Need enough data for 4-byte if we added it; for PORTME raise before untile
            # format 7 not handled → PORTME before untile... wait, we raise before untile
            apf_inner.decode_txtr_base_rgba(meta, base + bytes(1024))
        msg = str(ctx.exception)
        self.assertIn("PORTME", msg)
        self.assertIn("7", msg)
        self.assertIn("Supported PNG previews", msg)

    def test_png_roundtrip_write_for_565(self) -> None:
        linear = bytearray(8 * 8 * 2)
        for i in range(64):
            linear[i * 2 : i * 2 + 2] = struct.pack("<H", 0x07E0)  # green
        base = _tile_linear(bytes(linear), 8, 8, 32, 2)
        w, h, rgba = apf_inner.decode_txtr_base_rgba(_meta(4, "5_6_5", 8, 8), base)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "g.png"
            apf_inner.write_rgba_png(path, w, h, rgba)
            with Image.open(path) as image:
                image.load()
                self.assertEqual(image.size, (8, 8))
                self.assertEqual(image.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
