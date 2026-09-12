"""Retail shoe relief discovery, fixed-span compilation and every-mip decode proof."""

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import sys
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_bump_texture_writer as writer
from nfl_txtr import (
    HEADER, compress_vc_lz, decode_chunk, encode_rgba_png, parse_chunks, parse_texture,
    rebuild_compressed_chunk_fixed_span, texture_to_rgba,
)

SOURCE = Path(os.environ.get("NFL2K5_RETAIL_INDEX",
    "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")).parent
# Whole compressed spans, including wrappers and retail scratch words.
PINS = (
    "b1dc60ca2b510077709df90512e2eb095a0bd232ff1af4fdafc90f68baaa0957",
    "29f0b674308e3c07fefd76c0ffe3c8e33c2d45fb0f4b609c8de0f7f4be954b02",
    "ab0ef14eb0fc5e08cf41af35018e10a628daf2725244204867bca7fc0e8848c0",
    "691609812fd06bb9a85eee4cad7516847bd878aabeae6c8d340085cd4a9dc825",
    "cca4ea3a205503e2052e171f6aa6098a8e3859999ef3378082fc24644979cd21",
    "0823223783200d77c392c388f9be2479c39ee7f2b77b19f733367a9cc5721284",
    "ff3ba2239249dbbcbe7598765120f2fe5f977c35c9b35d54ed5f4e063caf0058",
)


class ShoeReliefSyntheticTests(unittest.TestCase):
    def test_import_copy_and_verify_rejects_lower_mip_corruption(self):
        # A small synthetic GLOBAL.IFF entry; no retail resources in this fixture.
        system = bytearray(128)
        system[12:16] = b"TXTR"
        struct.pack_into("<II", system, 16, 0x30 - 0x0F, 0x60 - 0x13)
        name = "bump_shoes1\0".encode("utf-16le")
        system[0x30:0x30 + len(name)] = name
        struct.pack_into("<6I", system, 0x60, 0, 0, 21824, 0x7750B29, 0, 0x80000000)
        original = bytes(system) + bytes(21824) + bytes((255, 128, 128, 255)) + bytes(1020)
        encoded, _ = compress_vc_lz(original, offset_bits=12)
        stored = len(encoded) + 1024
        span = HEADER.pack(b"TXTR", stored, 128, 22848, 0xFEEDBEEF, 16, 0, 0) + encoded + bytes(1024)
        head = HEADER.pack(b"FONT", 32, 0, 0, 0, 0, 0, 0) + bytes(32)
        outer = head + span
        start = len(head)
        blocks = (len(outer) + 2047) // 2048
        sizes = [0] * 36
        sizes[11] = blocks
        table = struct.pack("<III36I3I", 1, 0, 16, *sizes, writer.GLOBAL_PACKAGE_NAME_ID, len(outer), 0)
        with tempfile.TemporaryDirectory(prefix="shoe-relief-copy-") as directory:
            root = Path(directory).resolve()
            source, target = root / "source", root / "target"
            for path in (source, target):
                path.mkdir()
                (path / "0").write_bytes(table)
                (path / "B").write_bytes(outer + bytes(blocks * 2048 - len(outer)))
            before = (source / "B").read_bytes()
            rgba = b"".join(bytes((128, 128, 255, 255) if x < 64 else (160, 128, 250, 255))
                            for y in range(128) for x in range(128))
            png = root / "map.png"
            png.write_bytes(encode_rgba_png(128, 128, rgba))
            preview = writer.preview_import(source, 0, "bump_shoes1", png)
            self.assertEqual(preview["scope"], writer.SHOE_BUMP_SCOPE)
            receipt = writer.import_bump(source, target, 0, "bump_shoes1", png)
            self.assertTrue(receipt["post_write_readback_matches"])
            self.assertTrue(writer.verify_write(target, 0, "bump_shoes1", rgba)["ok"])
            built = (target / "B").read_bytes()
            self.assertEqual(built[:start], before[:start])
            self.assertEqual(built[len(outer):], before[len(outer):])
            self.assertEqual(built[start:start + 32], before[start:start + 32])
            chunk = parse_chunks(built[start:start + len(span)])[0]
            decoded, _ = decode_chunk(built[start:start + len(span)], chunk)
            damaged = bytearray(decoded)
            damaged[128 + 16384] ^= 1
            corrupt, _ = rebuild_compressed_chunk_fixed_span(built[start:start + len(span)], bytes(damaged))
            (target / "B").write_bytes(built[:start] + corrupt + built[start + len(span):])
            verification = writer.verify_write(target, 0, "bump_shoes1", rgba)
            self.assertTrue(verification["checks"]["pixels_equal"])
            self.assertFalse(verification["checks"]["distance_images_equal"])
            self.assertFalse(verification["ok"])
            self.assertEqual((source / "B").read_bytes(), before)


@unittest.skipUnless((SOURCE / "0").is_file(), "Private retail NFL 2K5 pack index is absent")
class ShoeReliefTests(unittest.TestCase):
    def test_global_discovery_all_seven_maps_and_style_binding_names(self):
        rows = writer.list_packages(SOURCE)
        global_row = next(row for row in rows if row["logical_name"] == "GLOBAL.IFF")
        self.assertEqual(global_row["outer_index"], 3)
        detail = writer.package_bump_slots(SOURCE, 3)
        self.assertEqual([row["name"] for row in detail["chunks"]], list(writer.SHOE_BUMP_NAMES))
        self.assertEqual([row["chunk_index"] for row in detail["chunks"]], list(range(194, 201)))
        self.assertEqual([row["span_sha256"] for row in detail["chunks"]], list(PINS))

    def test_each_shoe_relief_build_preserves_wrapper_and_decodes_all_authored_mips(self):
        # Two exact normal colours on block-aligned halves. No quantization loss.
        rgba = b"".join(bytes((128, 128, 255, 255) if x < 64 else (160, 128, 250, 255))
                        for y in range(128) for x in range(128))
        expected = writer.generate_mips(rgba, 128, 128, 5)
        for name, digest in zip(writer.SHOE_BUMP_NAMES, PINS):
            with self.subTest(name=name), writer._Image.open(SOURCE, writable=False) as image:
                resolved, index, entry = writer._resolve_bump(image, 3, name)
                self.assertEqual(hashlib.sha256(resolved.span).hexdigest(), digest)
                span, decoded, stats = writer._build_replacement_span(resolved, rgba)
                self.assertEqual(len(span), len(resolved.span))
                self.assertEqual(span[:32], resolved.span[:32])
                self.assertEqual(decoded[:resolved.chunk.system_bytes],
                                 resolved.decoded[:resolved.chunk.system_bytes])
                # Close/reopen a bounded saved span before decoding; no pack or XISO copy.
                with tempfile.TemporaryDirectory(prefix="shoe-relief-proof-") as directory:
                    path = Path(directory) / "span.bin"
                    path.write_bytes(b"prefix" + span + b"suffix")
                    reopened = path.read_bytes()
                    self.assertEqual(reopened[:6], b"prefix")
                    self.assertEqual(reopened[-6:], b"suffix")
                    span = reopened[6:-6]
                chunk = parse_chunks(span)[0]
                actual, _ = decode_chunk(span, chunk)
                texture = parse_texture(actual, chunk)
                cursor = texture.pixel_offset
                for level in expected:
                    self.assertEqual(texture_to_rgba(actual, chunk, replace(
                        texture, pixel_offset=cursor, width=level.width, height=level.height, mip_levels=1)),
                        level.rgba)
                    cursor += level.width * level.height
                source_span = image.read_segments(index.sub_extents(
                    entry, resolved.chunk.offset, len(resolved.span)))
                self.assertEqual(source_span, resolved.span)

    def test_unchanged_export_preserves_original_mips_and_palette(self):
        with writer._Image.open(SOURCE, writable=False) as image:
            resolved, _, _ = writer._resolve_bump(image, 3, "bump_shoes1")
            span, decoded, _ = writer._build_replacement_span(resolved, resolved.rgba)
            self.assertEqual(span, resolved.span)
            self.assertEqual(decoded, resolved.decoded)

    def test_more_than_256_colours_refuses_without_a_lossy_normal_map(self):
        rgba = b"".join(bytes((x, y, 255, 255)) for y in range(128) for x in range(128))
        with writer._Image.open(SOURCE, writable=False) as image:
            resolved, _, _ = writer._resolve_bump(image, 3, "bump_shoes1")
            with self.assertRaisesRegex(writer.BumpTextureWriterError, "more than 256 colours"):
                writer._build_replacement_span(resolved, rgba)


if __name__ == "__main__":
    unittest.main()
