"""Tests for the EA ``SHPS`` image-bank package.

Synthetic banks only.  Every byte a test looks at is one it built from the
documented layout, so the suite runs for a contributor who owns none of the
games and no pixel from any disc is needed to prove the decoder.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_shps  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402


def block(code: int, width: int, height: int, payload: bytes, *,
          misc=(0, 0, 0, 0), order: str = "<",
          declared: "int | None" = None) -> bytes:
    """One block: code, u24 size, u16 width, u16 height, four u16, payload."""
    size = ea_shps.BLOCK_HEADER_SIZE + len(payload) if declared is None else declared
    endian = "little" if order == "<" else "big"
    return (bytes((code,)) + size.to_bytes(3, endian)
            + struct.pack(order + "HH", width, height)
            + struct.pack(order + "HHHH", *misc) + payload)


def bank(images, *, order: str = "<", magic: bytes = b"SHPS",
         directory_id: bytes = b"G355") -> bytes:
    """A bank from ``[(tag, [block, ...]), ...]``."""
    head = ea_shps.SHPS_HEADER_SIZE + ea_shps.SHPS_ROW_SIZE * len(images)
    bodies = [b"".join(blocks) for _tag, blocks in images]
    offsets = []
    cursor = head
    for body in bodies:
        offsets.append(cursor)
        cursor += len(body)
    directory = b"".join(
        tag.encode("ascii").ljust(4, b" ") + struct.pack(order + "I", offset)
        for (tag, _blocks), offset in zip(images, offsets))
    return (magic + struct.pack(order + "II", cursor, len(images))
            + directory_id + directory + b"".join(bodies))


def palette_block(entries, *, order: str = "<") -> bytes:
    payload = b"".join(bytes(entry) for entry in entries)
    return block(ea_shps.CODE_PALETTE32, len(entries), 1, payload,
                 misc=(len(entries), 0, 0x2000, 0), order=order)


def text_terminator() -> bytes:
    """A final zero-size attachment, the shape every measured chain ends with."""
    return block(0x70, 0, 0, b"", declared=0)


GREY16 = [(index * 16, index * 16, index * 16, 0x80) for index in range(16)]


class ParseTests(unittest.TestCase):

    def simple(self) -> bytes:
        pixels = bytes([0, 1, 2, 3, 4, 5, 6, 7])
        return bank([("icon", [block(ea_shps.CODE_INDEXED8, 4, 2, pixels),
                               palette_block(GREY16), text_terminator()])])

    def test_the_header_and_directory_are_read(self) -> None:
        parsed = ea_shps.parse(self.simple(), name="icon.ssh")
        self.assertEqual(parsed.magic, "SHPS")
        self.assertEqual(parsed.endian, "little")
        self.assertEqual(parsed.directory_id, "G355")
        self.assertEqual(parsed.image_count, 1)
        self.assertEqual(parsed.size_mismatch, 0)
        self.assertEqual([image.tag for image in parsed], ["icon"])

    def test_the_block_chain_is_walked_and_the_zero_block_ends_it(self) -> None:
        parsed = ea_shps.parse(self.simple())
        image = parsed.image(0)
        self.assertEqual([b.code for b in image.blocks],
                         [ea_shps.CODE_INDEXED8, ea_shps.CODE_PALETTE32, 0x70])
        self.assertEqual(image.width, 4)
        self.assertEqual(image.height, 2)
        self.assertTrue(image.blocks[0].is_pixels)
        self.assertTrue(image.blocks[1].is_palette)
        self.assertEqual(image.blocks[2].declared_size, 0)
        # The last block's bytes are what is left, not what it declares.
        self.assertEqual(image.blocks[2].payload_bytes, 0)
        self.assertTrue(image.decodable)

    def test_two_images_do_not_run_into_one_another(self) -> None:
        one = [block(ea_shps.CODE_INDEXED8, 2, 2, bytes([0, 1, 2, 3])),
               palette_block(GREY16), text_terminator()]
        two = [block(ea_shps.CODE_INDEXED8, 2, 1, bytes([4, 5])),
               palette_block(GREY16), text_terminator()]
        parsed = ea_shps.parse(bank([("aaaa", one), ("bbbb", two)]))
        self.assertEqual(len(parsed), 2)
        self.assertEqual(len(parsed.image(0).blocks), 3)
        self.assertEqual(len(parsed.image(1).blocks), 3)
        self.assertEqual(parsed.image(1).width, 2)
        self.assertEqual(parsed.image(1).height, 1)

    def test_a_big_endian_bank_is_read_the_same_way(self) -> None:
        pixels = bytes([0, 1, 2, 3])
        blob = bank([("icon", [block(ea_shps.CODE_INDEXED8, 2, 2, pixels, order=">"),
                               palette_block(GREY16, order=">"),
                               block(0x70, 0, 0, b"", declared=0, order=">")])],
                    order=">")
        parsed = ea_shps.parse(blob)
        self.assertEqual(parsed.endian, "big")
        width, height, rgba = ea_shps.decode_rgba(parsed)
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(rgba[:4], bytes((0, 0, 0, 255)))

    def test_the_histogram_and_summary_count_blocks(self) -> None:
        parsed = ea_shps.parse(self.simple())
        self.assertEqual(parsed.code_histogram(), {"0x02": 1, "0x21": 1, "0x70": 1})
        summary = parsed.summary()
        self.assertEqual(summary["images"], 1)
        self.assertEqual(summary["decodable"], 1)

    def test_something_that_is_not_a_bank_points_at_the_packing(self) -> None:
        with self.assertRaises(Refusal) as caught:
            ea_shps.parse(b"\x10\xfb\x00\x00\x10" + b"\x00" * 32, name="x.ssh")
        self.assertIn("not an SHPS bank", str(caught.exception))
        self.assertIn("RefPack-packed", str(caught.exception))

    def test_a_directory_that_fits_neither_byte_order_is_refused(self) -> None:
        blob = bytearray(self.simple())
        struct.pack_into("<I", blob, 8, 999999)
        with self.assertRaises(Refusal) as caught:
            ea_shps.parse(bytes(blob), name="x.ssh")
        self.assertIn("neither directory fits", str(caught.exception))


class DecodeTests(unittest.TestCase):

    def test_indexed_pixels_come_back_through_the_palette(self) -> None:
        entries = [(10, 20, 30, 0x80), (40, 50, 60, 0x40),
                   (70, 80, 90, 0x00), (1, 2, 3, 0x80)]
        blob = bank([("icon", [block(ea_shps.CODE_INDEXED8, 2, 2,
                                     bytes([0, 1, 2, 3])),
                               palette_block(entries), text_terminator()])])
        width, height, rgba = ea_shps.decode_rgba(ea_shps.parse(blob))
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(list(rgba[0:4]), [10, 20, 30, 255])
        # 0x40 of a 0x80 scale is half: 0x40 * 255 // 0x80 == 127.
        self.assertEqual(list(rgba[4:8]), [40, 50, 60, 127])
        self.assertEqual(list(rgba[8:12]), [70, 80, 90, 0])
        self.assertEqual(list(rgba[12:16]), [1, 2, 3, 255])

    def test_raw_alpha_hands_back_the_stored_value(self) -> None:
        entries = [(9, 9, 9, 0x80)]
        blob = bank([("icon", [block(ea_shps.CODE_INDEXED8, 1, 1, bytes([0])),
                               palette_block(entries), text_terminator()])])
        _w, _h, rgba = ea_shps.decode_rgba(ea_shps.parse(blob), raw_alpha=True)
        self.assertEqual(rgba[3], 0x80)

    def test_a_short_palette_maps_the_rest_to_transparent_black(self) -> None:
        blob = bank([("icon", [block(ea_shps.CODE_INDEXED8, 2, 1, bytes([0, 7])),
                               palette_block([(5, 6, 7, 0x80)]),
                               text_terminator()])])
        _w, _h, rgba = ea_shps.decode_rgba(ea_shps.parse(blob))
        self.assertEqual(list(rgba[0:4]), [5, 6, 7, 255])
        self.assertEqual(list(rgba[4:8]), [0, 0, 0, 0])

    def test_a_256_entry_palette_is_csm1_deinterleaved(self) -> None:
        entries = [(index, 0, 0, 0x80) for index in range(256)]
        blob = bank([("icon", [block(ea_shps.CODE_INDEXED8, 4, 1,
                                     bytes([0, 8, 16, 24])),
                               palette_block(entries), text_terminator()])])
        parsed = ea_shps.parse(blob)
        _w, _h, rgba = ea_shps.decode_rgba(parsed)
        # 0 and 24 sit outside the swapped groups; 8 and 16 trade places.
        self.assertEqual([rgba[0], rgba[4], rgba[8], rgba[12]], [0, 16, 8, 24])

    def test_a_16_entry_palette_is_left_in_order(self) -> None:
        entries = [(index, 0, 0, 0x80) for index in range(16)]
        blob = bank([("icon", [block(ea_shps.CODE_INDEXED8, 4, 1,
                                     bytes([0, 8, 12, 15])),
                               palette_block(entries), text_terminator()])])
        _w, _h, rgba = ea_shps.decode_rgba(ea_shps.parse(blob))
        self.assertEqual([rgba[0], rgba[4], rgba[8], rgba[12]], [0, 8, 12, 15])

    def test_a_padded_palette_uses_its_declared_width_not_its_length(self) -> None:
        # A block that declares 3 entries and carries 4: the fourth is padding
        # and must not join the palette.
        payload = b"".join(bytes(entry) for entry in
                           [(1, 0, 0, 0x80), (2, 0, 0, 0x80),
                            (3, 0, 0, 0x80), (9, 9, 9, 0x80)])
        short = block(ea_shps.CODE_PALETTE32, 3, 1, payload)
        blob = bank([("icon", [block(ea_shps.CODE_INDEXED8, 4, 1,
                                     bytes([0, 1, 2, 3])),
                               short, text_terminator()])])
        parsed = ea_shps.parse(blob)
        self.assertEqual(len(ea_shps.read_palette(parsed,
                                                  parsed.image(0).blocks[1])), 3)
        _w, _h, rgba = ea_shps.decode_rgba(parsed)
        self.assertEqual([rgba[0], rgba[4], rgba[8]], [1, 2, 3])
        # Index 3 is past the declared palette: transparent, not the padding.
        self.assertEqual(list(rgba[12:16]), [0, 0, 0, 0])

    def test_deinterleave_is_its_own_inverse(self) -> None:
        entries = [(index, index, index, 0x80) for index in range(256)]
        once = ea_shps.deinterleave_csm1(entries)
        self.assertNotEqual(once, entries)
        self.assertEqual(ea_shps.deinterleave_csm1(once), entries)


class DirectPixelTests(unittest.TestCase):

    def direct(self, pixels: bytes, width: int, height: int,
               extra=()) -> ea_shps.ShpsBank:
        blocks = [block(ea_shps.CODE_RGBA32, width, height, pixels)]
        blocks.extend(extra)
        blocks.append(text_terminator())
        return ea_shps.parse(bank([("logo", blocks)]), name="logo.ssh")

    def test_direct_rgba_needs_no_palette(self) -> None:
        pixels = bytes((10, 20, 30, 0x80, 40, 50, 60, 0x40))
        parsed = self.direct(pixels, 2, 1)
        self.assertTrue(parsed.image(0).decodable)
        self.assertIsNone(parsed.image(0).palette)
        width, height, rgba = ea_shps.decode_rgba(parsed)
        self.assertEqual((width, height), (2, 1))
        self.assertEqual(list(rgba[0:4]), [10, 20, 30, 255])
        self.assertEqual(list(rgba[4:8]), [40, 50, 60, 127])

    def test_direct_rgba_can_hand_back_the_stored_alpha(self) -> None:
        pixels = bytes((10, 20, 30, 0x80))
        _w, _h, rgba = ea_shps.decode_rgba(self.direct(pixels, 1, 1),
                                           raw_alpha=True)
        self.assertEqual(list(rgba), [10, 20, 30, 0x80])

    def test_direct_rgba_carrying_a_palette_is_refused(self) -> None:
        parsed = self.direct(bytes((1, 2, 3, 0x80)), 1, 1,
                             extra=[palette_block(GREY16)])
        reason = parsed.undecodable_reason(0)
        assert reason is not None
        self.assertIn("carries a palette block as well", reason)

    def test_a_mip_chain_is_counted_and_level_zero_is_decoded(self) -> None:
        # Level 0 plus the whole chain below it: 4x4 + 2x2 + 1x1.
        pixels = bytes([1] * 16 + [2] * 4 + [3])
        blob = bank([("mips", [block(ea_shps.CODE_INDEXED8, 4, 4, pixels),
                               palette_block(GREY16), text_terminator()])])
        parsed = ea_shps.parse(blob)
        self.assertEqual(parsed.image(0).mip_bytes, 5)
        _w, _h, rgba = ea_shps.decode_rgba(parsed)
        self.assertEqual(len(rgba), 4 * 4 * 4)
        self.assertEqual(list(rgba[0:3]), [16, 16, 16])


class RefusalTests(unittest.TestCase):

    def test_an_unknown_pixel_code_is_refused_with_its_arithmetic(self) -> None:
        blob = bank([("crwd", [block(0x0E, 8, 8, b"\x00" * 24),
                               palette_block(GREY16), text_terminator()])])
        parsed = ea_shps.parse(blob, name="crwd.ssh")
        reason = parsed.undecodable_reason(0)
        assert reason is not None
        self.assertIn("0x0e", reason)
        self.assertIn("8x8", reason)
        self.assertIn("0.375", reason)
        # The refusal carries the measurement, not just "unsupported".
        self.assertIn("6 bytes per 4x4 block", reason)
        self.assertIn("fixed-rate compressed codec", reason)
        self.assertFalse(parsed.image(0).decodable)
        with self.assertRaises(ea_shps.UnsupportedBlock) as caught:
            ea_shps.decode_rgba(parsed)
        self.assertIn("crwd.ssh", str(caught.exception))

    def test_indexed_pixels_with_no_palette_say_what_followed(self) -> None:
        blob = bank([("icon", [block(ea_shps.CODE_INDEXED8, 2, 1, b"\x00\x01"),
                               block(0x69, 0, 0, b"\x00" * 16),
                               text_terminator()])])
        parsed = ea_shps.parse(blob, name="icon.ssh")
        reason = parsed.undecodable_reason(0)
        assert reason is not None
        self.assertIn("no palette block", reason)
        self.assertIn("0x69", reason)

    def test_a_pixel_block_short_of_its_own_dimensions_is_refused(self) -> None:
        short = block(ea_shps.CODE_INDEXED8, 16, 16, b"\x00" * 8)
        blob = bank([("icon", [short, palette_block(GREY16), text_terminator()])])
        parsed = ea_shps.parse(blob, name="icon.ssh")
        reason = parsed.undecodable_reason(0)
        assert reason is not None
        self.assertIn("needs 256", reason)

    def test_a_palette_code_this_reader_does_not_know_is_named(self) -> None:
        blob = bank([("icon", [block(ea_shps.CODE_INDEXED8, 1, 1, b"\x00"),
                               block(0x2A, 16, 1, b"\x00" * 32),
                               text_terminator()])])
        parsed = ea_shps.parse(blob)
        with self.assertRaises(ea_shps.UnsupportedBlock) as caught:
            ea_shps.read_palette(parsed, parsed.image(0).blocks[1])
        self.assertIn("0x2a", str(caught.exception))

    def test_an_image_that_is_not_there_says_how_many_are(self) -> None:
        blob = bank([("icon", [block(ea_shps.CODE_INDEXED8, 1, 1, b"\x00"),
                               palette_block(GREY16), text_terminator()])])
        with self.assertRaises(Refusal) as caught:
            ea_shps.parse(blob).image(4)
        self.assertIn("(0..0)", str(caught.exception))


class PngTests(unittest.TestCase):

    def test_the_png_is_readable_without_a_png_library(self) -> None:
        rgba = bytes(range(16)) * 4          # 4x4 RGBA
        png = ea_shps.encode_png(4, 4, rgba)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        length, = struct.unpack_from(">I", png, 8)
        self.assertEqual(png[12:16], b"IHDR")
        width, height, depth, colour = struct.unpack_from(">IIBB", png, 16)
        self.assertEqual((width, height, depth, colour), (4, 4, 8, 6))
        # Walk to IDAT and undo the per-row filter-0 bytes.
        position = 8
        data = b""
        while position < len(png):
            size, tag = struct.unpack_from(">I", png, position)[0], png[position + 4:position + 8]
            if tag == b"IDAT":
                data = zlib.decompress(png[position + 8:position + 8 + size])
            position += 12 + size
        rows = [data[index * 17 + 1:index * 17 + 17] for index in range(4)]
        self.assertEqual(b"".join(rows), rgba)
        del length

    def test_a_size_that_does_not_match_the_pixels_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            ea_shps.encode_png(4, 4, b"\x00" * 8)
        self.assertIn("64 byte(s)", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
