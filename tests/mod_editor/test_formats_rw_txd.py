"""The RenderWare PS2 texture-dictionary reader, on dictionaries this file builds.

No game data: every dictionary, every palette and every pixel here is built by
``rw_txd``'s own synthetic builder from values this file chooses.  What is
proved:

* a dictionary parses, its declared texture count equals the rasters found, and
  its one section accounts for the whole file;
* the GS un-swizzle is the exact inverse of the layout the builder writes, so
  known indices decode back to themselves, byte for byte;
* the 256-entry CLUT survives its CSM1 interleave both ways;
* a PCSX2 replacement name is derived and is stable for the same bytes;
* a 4-bit raster is refused **by name**, in the sentence that says why, and the
  refusal names the measurement rather than a guess;
* a member that is not a texture dictionary, a raster header of the wrong
  length, and a header whose section sizes disagree are each refused.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import pcsx2_texture_name, rw_txd  # noqa: E402

PALETTE = [(index, (index * 3) & 0xFF, (255 - index) & 0xFF, 0x80) for index in range(256)]


def _indices(width: int, height: int) -> bytes:
    return bytes(((x * 7 + y * 13 + x * y) & 0xFF) for y in range(height) for x in range(width))


class ReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pixels = {(64, 32): _indices(64, 32), (128, 64): _indices(128, 64)}
        self.blob = rw_txd.build_synthetic_dictionary(
            [("fixture_a", 64, 32, self.pixels[(64, 32)], PALETTE),
             ("fixture_b", 128, 64, self.pixels[(128, 64)], PALETTE)])
        self.dictionary = rw_txd.read_dictionary(self.blob, "fixture.rtd")

    def test_the_dictionary_declares_the_rasters_it_holds(self) -> None:
        self.assertEqual(self.dictionary.declared_textures, 2)
        self.assertEqual(len(self.dictionary.rasters), 2)
        self.assertTrue(self.dictionary.section_accounts_for_file)
        self.assertEqual([raster.name for raster in self.dictionary.rasters],
                         ["fixture_a", "fixture_b"])

    def test_each_raster_carries_its_measured_header(self) -> None:
        for raster, (width, height) in zip(self.dictionary.rasters, ((64, 32), (128, 64))):
            self.assertEqual((raster.width, raster.height), (width, height))
            self.assertEqual(raster.depth, 8)
            self.assertEqual(raster.psm, pcsx2_texture_name.PSMT8)
            self.assertEqual(raster.tex0_width, width)
            self.assertEqual(raster.tex0_height, height)
            self.assertEqual(raster.palette_entries, 256)
            self.assertIsNone(rw_txd.undecodable_reason(raster))

    def test_the_unswizzle_returns_the_indices_the_builder_laid_in(self) -> None:
        for raster in self.dictionary.rasters:
            decoded = rw_txd.decode_indices(self.dictionary, raster)
            self.assertEqual(decoded, self.pixels[(raster.width, raster.height)])

    def test_the_clut_survives_its_csm1_interleave(self) -> None:
        raster = self.dictionary.raster(0)
        self.assertEqual(rw_txd.read_palette(self.dictionary, raster), PALETTE)

    def test_rgba_is_the_palette_looked_up_by_the_decoded_indices(self) -> None:
        raster = self.dictionary.raster(0)
        rgba = rw_txd.decode_rgba(self.dictionary, raster)
        self.assertEqual(len(rgba), raster.width * raster.height * 4)
        indices = self.pixels[(64, 32)]
        for position in (0, 1, 137, len(indices) - 1):
            self.assertEqual(tuple(rgba[position * 4:position * 4 + 4]),
                             PALETTE[indices[position]])

    def test_a_replacement_identity_is_derived_and_stable(self) -> None:
        raster = self.dictionary.raster(0)
        name = rw_txd.replacement_identity(self.dictionary, raster)
        self.assertIsNotNone(name)
        assert name is not None
        self.assertTrue(name.endswith(".png"))
        parsed = pcsx2_texture_name.parse_name(name)
        self.assertEqual(parsed.bits & 0x3F, pcsx2_texture_name.PSMT8)
        again = rw_txd.read_dictionary(self.blob, "fixture.rtd")
        self.assertEqual(rw_txd.replacement_identity(again, again.raster(0)), name)

    def test_two_different_pictures_get_two_different_names(self) -> None:
        other = rw_txd.build_synthetic_dictionary(
            [("fixture_a", 64, 32, bytes(64 * 32), PALETTE)])
        other_dictionary = rw_txd.read_dictionary(other, "other.rtd")
        self.assertNotEqual(rw_txd.replacement_identity(self.dictionary, self.dictionary.raster(0)),
                            rw_txd.replacement_identity(other_dictionary,
                                                        other_dictionary.raster(0)))


class RefusalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.blob = rw_txd.build_synthetic_dictionary(
            [("fixture_a", 64, 32, _indices(64, 32), PALETTE)])

    def test_a_member_that_is_not_a_texture_dictionary_is_refused(self) -> None:
        clump = struct.pack("<3I", rw_txd.ID_STRUCT, 4, 0x0401FFFF) + bytes(4)
        with self.assertRaises(rw_txd.RwTxdError) as caught:
            rw_txd.read_dictionary(clump, "not-a-txd.dff")
        self.assertIn("not a .rtd", str(caught.exception))

    def test_a_short_member_is_refused(self) -> None:
        with self.assertRaises(rw_txd.RwTxdError):
            rw_txd.read_dictionary(b"\x16\x00", "short.rtd")

    def test_a_header_whose_section_sizes_disagree_is_refused(self) -> None:
        blob = bytearray(self.blob)
        dictionary = rw_txd.read_dictionary(bytes(blob), "fixture.rtd")
        raster = dictionary.raster(0)
        struct.pack_into("<I", blob, raster.header_offset + 48, raster.texel_bytes + 16)
        with self.assertRaises(rw_txd.RwTxdError) as caught:
            rw_txd.read_dictionary(bytes(blob), "fixture.rtd")
        self.assertIn("the header and the section disagree", str(caught.exception))

    def test_a_four_bit_raster_is_refused_by_name_with_the_measurement(self) -> None:
        raster = rw_txd.Raster(0, "four_bit", "", 64, 32, 4, 0x4504, 0, 0, 0, 0, 0, 0, 0)
        reason = rw_txd.undecodable_reason(raster)
        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("4-bit", reason)
        self.assertIn("232%", reason)
        self.assertIsNone(rw_txd.replacement_identity(
            rw_txd.read_dictionary(self.blob, "fixture.rtd"), raster))

    def test_an_unmeasured_depth_is_refused(self) -> None:
        raster = rw_txd.Raster(0, "odd", "", 64, 32, 16, 0, 0, 0, 0, 0, 0, 0, 0)
        reason = rw_txd.undecodable_reason(raster)
        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("16 bits per texel", reason)

    def test_the_builder_refuses_a_palette_that_is_not_256_entries(self) -> None:
        with self.assertRaises(rw_txd.RwTxdError) as caught:
            rw_txd.build_synthetic_dictionary([("a", 8, 8, bytes(64), PALETTE[:16])])
        self.assertIn("256-entry palette", str(caught.exception))

    def test_the_builder_refuses_indices_that_do_not_fill_the_texture(self) -> None:
        with self.assertRaises(rw_txd.RwTxdError) as caught:
            rw_txd.build_synthetic_dictionary([("a", 64, 32, bytes(16), PALETTE)])
        self.assertIn("which needs 2048", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
