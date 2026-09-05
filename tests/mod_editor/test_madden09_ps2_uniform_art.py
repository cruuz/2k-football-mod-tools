"""The Madden 09 (PS2) MMAP decoder and uniform-art lane, on synthetic data only.

Every texture here is built by ``containers.synthetic_mmap`` out of the
format's own rules -- a computed palette and a counting ramp of indices -- so
the tests prove the layout without a game.  The evidence that the same layout
reads *real* art is in ``docs/product/MADDEN09_PS2_MODULE.md``; what these
tests hold is that the rules are implemented as written and that every refusal
names its fix.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.games.contract import EncodedArt, Refusal, Target  # noqa: E402
from mod_editor.games.madden09_ps2 import containers, mmap_art, uniform_art  # noqa: E402


class MmapLayoutTests(unittest.TestCase):
    """The table-of-tables, and the two rules that are easy to get wrong."""

    def test_a_member_parses_to_its_declared_tables(self) -> None:
        payload = containers.synthetic_mmap(16, 8, mips=2, palette_only_extra=True)
        texture = mmap_art.parse(payload)
        self.assertEqual(texture.version, 2)
        self.assertEqual(len(texture.images), 2)
        self.assertEqual(len(texture.surfaces), 2, "one surface row per mip level")
        self.assertEqual(len(texture.palettes), 2)
        self.assertEqual(texture.images[0].name, "SYNTH")
        base = texture.base_surface(texture.images[0])
        self.assertIsNotNone(base)
        self.assertEqual((base.width, base.height), (16, 8), "level 0 is the largest")
        self.assertEqual(texture.surfaces[1].width, 8, "level 1 halves both axes")

    def test_a_palette_only_image_is_named_not_treated_as_broken(self) -> None:
        payload = containers.synthetic_mmap(8, 8, palette_only_extra=True)
        texture = mmap_art.parse(payload)
        extra = texture.images[1]
        self.assertFalse(extra.decodable)
        reason = texture.undecodable_reason(extra)
        self.assertIn("palette-only", reason)
        self.assertIn("no pixels of its own", reason)
        self.assertIsNone(texture.undecodable_reason(texture.images[0]))
        self.assertEqual(len(texture.decodable_images), 1)

    def test_a_256_entry_clut_is_de_interleaved_and_a_16_entry_one_is_not(self) -> None:
        wanted = containers.synthetic_palette(256)
        stored = mmap_art.deinterleave_csm1(wanted)
        self.assertNotEqual(stored, wanted, "the interleave must actually move entries")
        self.assertEqual(mmap_art.deinterleave_csm1(stored), wanted,
                         "the CSM1 swap is its own inverse")
        payload = containers.synthetic_mmap(8, 8, bits=4)
        texture = mmap_art.parse(payload)
        small = mmap_art.read_palette(payload, texture.palettes[0])
        self.assertEqual(len(small), 16)
        raw = payload[texture.palettes[0].offset:
                      texture.palettes[0].offset + texture.palettes[0].byte_size]
        self.assertEqual(small[0], tuple(raw[0:4]),
                         "a 16-entry CLUT is stored in order and must not be swapped")

    def test_eight_bit_pixels_decode_to_the_palette_they_index(self) -> None:
        payload = containers.synthetic_mmap(8, 4, seed=3)
        width, height, rgba = mmap_art.decode_rgba(payload)
        self.assertEqual((width, height), (8, 4))
        self.assertEqual(len(rgba), 8 * 4 * 4)
        palette = containers.synthetic_palette(256)
        indices = containers.synthetic_indices(8, 4, seed=3)
        for position, index in enumerate(indices):
            red, green, blue, alpha = palette[index]
            expected = (red, green, blue, 255 if alpha >= 0x80 else alpha * 255 // 0x80)
            self.assertEqual(tuple(rgba[position * 4:position * 4 + 4]), expected,
                             f"pixel {position} took the wrong palette entry")

    def test_four_bit_pixels_take_the_low_nibble_first(self) -> None:
        payload = containers.synthetic_mmap(8, 4, bits=4, seed=1)
        width, height, rgba = mmap_art.decode_rgba(payload)
        self.assertEqual((width, height), (8, 4))
        palette = containers.synthetic_palette(16)
        packed = containers.synthetic_indices(8, 4, bits=4, seed=1)
        first_low = packed[0] & 0x0F
        red, green, blue, alpha = palette[first_low]
        self.assertEqual(tuple(rgba[0:4]),
                         (red, green, blue, 255 if alpha >= 0x80 else alpha * 255 // 0x80))

    def test_alpha_is_scaled_off_the_ps2_zero_to_128_range(self) -> None:
        payload = containers.synthetic_mmap(8, 4)
        _width, _height, rgba = mmap_art.decode_rgba(payload)
        alphas = {rgba[position] for position in range(3, len(rgba), 4)}
        self.assertTrue(alphas <= {255, 0x40 * 255 // 0x80},
                        f"unexpected alpha values {sorted(alphas)}")

    def test_a_pure_palette_bank_is_read_rather_than_refused(self) -> None:
        """Six retail members declare no surfaces and no surface table."""

        payload = bytearray(containers.synthetic_mmap(8, 8))
        struct.pack_into("<H", payload, 0x0E, 0)       # surfaceCount = 0
        struct.pack_into("<I", payload, 0x18, 0)       # surfaceTableOffset = 0
        struct.pack_into("<H", payload, 0x0C, 0)       # imageCount = 0
        struct.pack_into("<I", payload, 0x14, 0)
        struct.pack_into("<I", payload, 0x20, 0)
        texture = mmap_art.parse(bytes(payload))
        self.assertEqual(texture.surfaces, ())
        self.assertEqual(texture.images, ())
        self.assertEqual(len(texture.palettes), 1)

    def test_a_surface_table_somewhere_else_is_refused_when_there_are_surfaces(self) -> None:
        payload = bytearray(containers.synthetic_mmap(8, 8))
        struct.pack_into("<I", payload, 0x18, 0x30)
        with self.assertRaises(mmap_art.MmapError) as caught:
            mmap_art.parse(bytes(payload))
        self.assertIn("Re-derive the header", str(caught.exception))

    def test_a_member_that_is_not_mmap_is_refused_by_name(self) -> None:
        with self.assertRaises(mmap_art.MmapError) as caught:
            mmap_art.parse(b"SMF\x00" + bytes(64))
        self.assertIn("Decompress the container member first", str(caught.exception))

    def test_a_truncated_member_is_refused_not_half_read(self) -> None:
        payload = containers.synthetic_mmap(16, 16)
        with self.assertRaises(mmap_art.MmapError) as caught:
            mmap_art.parse(payload[:64])
        self.assertIn("truncated", str(caught.exception))

    def test_an_unimplemented_surface_codec_is_refused_by_name(self) -> None:
        payload = bytearray(containers.synthetic_mmap(8, 8))
        surface_format = mmap_art.PIXELS_INDEXED_8 | (mmap_art.SURFACE_IPU1 << 16)
        struct.pack_into("<I", payload, 0x28 + 4, surface_format)
        texture = mmap_art.parse(bytes(payload))
        self.assertIn("IPU1", texture.undecodable_reason(texture.images[0]))
        with self.assertRaises(mmap_art.MmapError) as caught:
            mmap_art.decode_rgba(bytes(payload))
        self.assertIn("IPU1", str(caught.exception))

    def test_an_unimplemented_pixel_layout_is_refused_by_name(self) -> None:
        payload = bytearray(containers.synthetic_mmap(8, 8))
        struct.pack_into("<I", payload, 0x28 + 4, 7)
        with self.assertRaises(mmap_art.MmapError) as caught:
            mmap_art.decode_rgba(bytes(payload))
        self.assertIn("layout 7", str(caught.exception))

    def test_lzm1_round_trips_a_stream_this_test_builds(self) -> None:
        """A literal run, a match, and the terminator, encoded by hand."""

        stream = bytes([0x00, 0x80 | 4]) + b"ABCD" + bytes([4, 0x04, 0x00]) + bytes([0x00])
        self.assertEqual(mmap_art.lzm1_decompress(stream), b"ABCDABCD")

    def test_lzm1_refuses_a_match_that_reaches_before_the_start(self) -> None:
        stream = bytes([0x00, 4, 0x10, 0x00, 0x00])
        with self.assertRaises(mmap_art.MmapError) as caught:
            mmap_art.lzm1_decompress(stream)
        self.assertIn("not LZM1", str(caught.exception))

    def test_indexing_an_image_back_against_its_own_palette_is_exact(self) -> None:
        payload = containers.synthetic_mmap(8, 4, seed=5)
        texture = mmap_art.parse(payload)
        width, height, rgba = mmap_art.decode_rgba(payload, texture=texture)
        entries = mmap_art.read_palette(payload, texture.palettes[0])
        surface = texture.surfaces[0]
        self.assertEqual(mmap_art.encode_indexed(rgba, width, height, surface, entries),
                         containers.synthetic_indices(8, 4, seed=5),
                         "a decode followed by an encode must return the original indices")


class UniformArtLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="madden09-art-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.lane = uniform_art.UniformArtLane()
        self.source = self.lane.synthetic_source(self.work)
        self.catalogue = self.lane.build_catalogue(self.source)
        self.target = self.catalogue.targets[0]

    def test_the_lane_is_extract_only_and_lands_on_the_uniforms_page(self) -> None:
        self.assertEqual(self.lane.classification, "extract-only")
        self.assertEqual(self.lane.page, "uniforms")
        self.assertFalse(self.lane.fixed_allocation, "it publishes files, not byte ranges")
        self.assertFalse(getattr(self.lane, "read_only", False))

    def test_the_catalogue_carries_shape_and_no_pixels(self) -> None:
        from mod_editor.games.conformance import contains_payload

        document = self.catalogue.document
        self.assertEqual(document["images_decodable"], len(self.catalogue.targets))
        self.assertFalse(contains_payload(json.loads(json.dumps(document, default=dict))))
        self.assertIn("width", self.target.raw)
        self.assertNotIn("rgba", self.target.raw)

    def test_a_target_says_what_the_file_does_not_tell_us(self) -> None:
        structure = self.target.raw["structure"]
        self.assertIn("not established here", structure,
                      "the uniform container names nothing and the page must say so")

    def test_decode_gives_a_png_of_the_texture_s_own_size(self) -> None:
        png = self.lane.decode_png(self.source, self.target)
        width, height, rgba = uniform_art.read_rgba_png(png)
        self.assertEqual((width, height), (self.target.raw["width"], self.target.raw["height"]))
        self.assertEqual(len(rgba), width * height * 4)

    def test_decode_by_key_needs_no_catalogue(self) -> None:
        self.assertEqual(self.lane.decode_png_by_key(self.source, self.target.key),
                         self.lane.decode_png(self.source, self.target))

    def test_a_malformed_key_is_refused_with_the_shape_it_wanted(self) -> None:
        with self.assertRaises(Refusal) as caught:
            self.lane.parse_key("not-a-key")
        self.assertIn("<container>:<member>:<image>", str(caught.exception))

    def test_replacement_identity_is_none_and_says_why(self) -> None:
        self.assertIsNone(self.lane.replacement_identity(self.target))
        self.assertIn("GS dump", self.lane.NO_IDENTITY)

    def test_a_same_size_png_is_accepted_and_reported_against_the_palette(self) -> None:
        png = self.lane.decode_png(self.source, self.target)
        art = self.lane.encode(self.source, self.target, png)
        self.assertIsInstance(art, EncodedArt)
        self.assertEqual((art.width, art.height),
                         (self.target.raw["width"], self.target.raw["height"]))
        self.assertIn("land on an exact entry", art.note)
        self.assertIn("nowhere to write them yet", art.note)

    def test_an_integer_multiple_is_accepted_and_kept_at_that_size(self) -> None:
        width, height = self.target.raw["width"], self.target.raw["height"]
        doubled = uniform_art.write_rgba_png(bytes(width * 2 * height * 2 * 4),
                                             width * 2, height * 2)
        art = self.lane.encode(self.source, self.target, doubled)
        self.assertEqual((art.width, art.height), (width * 2, height * 2))
        self.assertIn("2x the texture's own", art.note)

    def test_a_wrong_size_png_is_refused_naming_the_size_it_wanted(self) -> None:
        width, height = self.target.raw["width"], self.target.raw["height"]
        odd = uniform_art.write_rgba_png(bytes((width + 3) * height * 4), width + 3, height)
        with self.assertRaises(Refusal) as caught:
            self.lane.encode(self.source, self.target, odd)
        self.assertIn(f"{width}x{height}", str(caught.exception))
        self.assertIn("whole-number multiple", str(caught.exception))
        self.assertIsNotNone(self.lane.check_edit(self.target, {"png": "unused"}))

    def test_a_file_that_is_not_a_png_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            uniform_art.read_rgba_png(b"not a png at all")
        self.assertIn("export a texture first", str(caught.exception))

    def test_check_edit_names_a_key_it_does_not_take(self) -> None:
        problem = self.lane.check_edit(self.target, {"colour": "red"})
        self.assertIn("colour", problem)

    def test_check_edit_accepts_an_export_with_no_png(self) -> None:
        self.assertIsNone(self.lane.check_edit(self.target, {}))

    def test_build_writes_the_pngs_it_receipts_and_verify_passes(self) -> None:
        recipe = self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue))
        out = self.work / "export.json"
        receipt = self.lane.build(self.source, out, recipe, self.catalogue)
        folder = self.lane.export_root_for(out)
        self.assertTrue(out.is_file(), "the destination is the manifest, a file")
        self.assertTrue((folder / "HOW-TO.txt").is_file(),
                        "the export explains its own limits")
        self.assertEqual(len(receipt.artifacts), 3, "manifest, one PNG, and the HOW-TO")
        verdict = self.lane.verify(self.source, out, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertIn("re-decoded from the source", verdict.summary)

    def test_verify_fails_on_a_tampered_export(self) -> None:
        recipe = self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue))
        out = self.work / "export.json"
        receipt = self.lane.build(self.source, out, recipe, self.catalogue)
        png = next(path for path in self.lane.export_root_for(out).iterdir()
                   if path.suffix == ".png")
        png.write_bytes(png.read_bytes()[:-8] + b"\x00" * 8)
        self.assertFalse(self.lane.verify(self.source, out, receipt).passed)

    def test_verify_fails_when_an_undeclared_file_appears(self) -> None:
        recipe = self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue))
        out = self.work / "export.json"
        receipt = self.lane.build(self.source, out, recipe, self.catalogue)
        (self.lane.export_root_for(out) / "sneaked-in.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        verdict = self.lane.verify(self.source, out, receipt)
        self.assertFalse(verdict.passed)
        self.assertIn("undeclared", verdict.summary)

    def test_build_refuses_an_existing_destination_and_the_source(self) -> None:
        recipe = self.lane.compose_recipe(self.lane.conformance_edits(self.catalogue))
        out = self.work / "export.json"
        self.lane.build(self.source, out, recipe, self.catalogue)
        with self.assertRaises(Refusal) as caught:
            self.lane.build(self.source, out, recipe, self.catalogue)
        self.assertIn("refusing to overwrite", str(caught.exception))
        with self.assertRaises(Refusal) as caught:
            self.lane.build(self.source, self.source, recipe, self.catalogue)
        self.assertIn("never the disc", str(caught.exception))

    def test_a_recipe_naming_a_texture_the_catalogue_does_not_have_is_refused(self) -> None:
        recipe = {"schema": uniform_art.RECIPE_SCHEMA,
                  "textures": [{"texture": "NOSUCH.DAT:0:0"}]}
        with self.assertRaises(Refusal):
            self.lane.plan(self.source, recipe, self.catalogue)

    def test_an_empty_recipe_is_refused_with_what_to_do(self) -> None:
        with self.assertRaises(Refusal) as caught:
            self.lane.plan(self.source, {"schema": uniform_art.RECIPE_SCHEMA, "textures": []},
                           self.catalogue)
        self.assertIn("choose at least one texture", str(caught.exception))


class MmapEncoderTests(unittest.TestCase):
    """Writing a member back: the tables, the CLUT, the packing, the layout."""

    SHAPES = (
        {},
        {"bits": 4},
        {"mips": 4},
        {"palette_only_extra": True},
        {"mips": 3, "bits": 4, "palette_only_extra": True},
    )

    @staticmethod
    def whole_member(payload: bytes) -> tuple:
        """Every decodable level and every palette of *payload*."""
        texture = mmap_art.parse(payload)
        levels = {}
        for image in texture.images:
            if texture.undecodable_reason(image) is not None:
                continue
            for level in range(image.mip_count):
                _width, _height, rgba = mmap_art.decode_rgba(
                    payload, image=image.index, level=level, texture=texture)
                levels[(image.index, level)] = rgba
        palettes = {palette.index: mmap_art.read_palette(payload, palette)
                    for palette in texture.palettes}
        return texture, levels, palettes

    def test_decode_then_encode_returns_the_same_bytes(self) -> None:
        """Every table, every offset, every CLUT and every pixel, byte for byte."""
        for shape in self.SHAPES:
            with self.subTest(**shape):
                member = containers.synthetic_mmap(32, 32, seed=2, retail_layout=True,
                                                   **shape)
                texture, levels, palettes = self.whole_member(member)
                self.assertEqual(
                    mmap_art.encode(member, levels=levels, palettes=palettes,
                                    texture=texture),
                    member)

    def test_indexing_from_pixels_alone_also_returns_the_same_bytes(self) -> None:
        """With ``prefer_original_indices=False`` nothing is carried over.

        The synthetic palette has no duplicate colour, so pixels alone are
        enough here.  On the disc they often are not -- 23 of one uniform
        member's 34 CLUTs carry a duplicate -- which is why the writer keeps
        the original index for an unchanged pixel rather than guessing.
        """
        for shape in self.SHAPES:
            with self.subTest(**shape):
                member = containers.synthetic_mmap(32, 32, seed=5, retail_layout=True,
                                                   **shape)
                texture, levels, palettes = self.whole_member(member)
                self.assertEqual(
                    mmap_art.encode(member, levels=levels, palettes=palettes,
                                    texture=texture, prefer_original_indices=False),
                    member)

    def test_a_duplicate_colour_keeps_the_index_the_file_used(self) -> None:
        member = containers.synthetic_mmap(16, 16, retail_layout=True)
        texture = mmap_art.parse(member)
        entries = mmap_art.read_palette(member, texture.palettes[0])
        entries[7] = entries[3]            # two indices, one colour
        member = mmap_art.encode(member, palettes={0: entries}, texture=texture)
        texture, levels, palettes = self.whole_member(member)
        self.assertEqual(
            mmap_art.encode(member, levels=levels, palettes=palettes, texture=texture),
            member)
        loose = mmap_art.encode(member, levels=levels, palettes=palettes,
                                texture=texture, prefer_original_indices=False)
        self.assertEqual(len(loose), len(member))
        self.assertNotEqual(loose, member,
                            "indexing by colour cannot tell the two apart, which is "
                            "the whole reason the original index is kept")

    def test_encode_with_nothing_replaced_normalises_the_layout(self) -> None:
        """The reader tolerates other arrangements; the disc uses exactly one."""
        loose = containers.synthetic_mmap(32, 32)
        retail = mmap_art.encode(loose)
        self.assertNotEqual(loose, retail)
        self.assertEqual(mmap_art.encode(retail), retail, "the layout is a fixed point")
        before = mmap_art.decode_rgba(loose)
        self.assertEqual(mmap_art.decode_rgba(retail), before)
        texture = mmap_art.parse(retail)
        self.assertEqual(texture.surfaces[0].offset % mmap_art.REGION_ALIGNMENT, 0)
        self.assertGreater(texture.palettes[0].offset, texture.surfaces[0].offset)

    def test_the_csm1_interleave_is_an_involution(self) -> None:
        entries = [((index * 5) & 0xFF, (index * 9) & 0xFF, (index * 17) & 0xFF,
                    index % 129) for index in range(mmap_art.CSM1_ENTRIES)]
        self.assertEqual(mmap_art.interleave_csm1(mmap_art.deinterleave_csm1(entries)),
                         entries)
        self.assertEqual(mmap_art.deinterleave_csm1(mmap_art.interleave_csm1(entries)),
                         entries)
        self.assertNotEqual(mmap_art.interleave_csm1(entries), entries)

    def test_write_palette_is_read_palettes_exact_inverse(self) -> None:
        for size in (16, mmap_art.CSM1_ENTRIES):
            with self.subTest(size):
                member = containers.synthetic_mmap(16, 16, retail_layout=True,
                                                   bits=8 if size == 256 else 4)
                texture = mmap_art.parse(member)
                palette = texture.palettes[0]
                self.assertEqual(palette.entries, size)
                raw = member[palette.offset:palette.offset + palette.byte_size]
                self.assertEqual(
                    mmap_art.write_palette(mmap_art.read_palette(member, palette)), raw)

    def test_the_alpha_scale_round_trips_over_the_ps2_range(self) -> None:
        for value in range(mmap_art.PS2_ALPHA_OPAQUE + 1):
            self.assertEqual(mmap_art._unscale_alpha(mmap_art._scale_alpha(value)), value)

    def test_index_packing_round_trips_at_both_depths(self) -> None:
        for bits in (4, 8):
            with self.subTest(bits):
                member = containers.synthetic_mmap(32, 16, retail_layout=True, bits=bits)
                texture = mmap_art.parse(member)
                surface = texture.surfaces[0]
                run = mmap_art.surface_pixels(member, surface)
                indices = mmap_art.unpack_indices(run, surface)
                self.assertEqual(len(indices), surface.width * surface.height)
                self.assertEqual(mmap_art.pack_indices(indices, surface), run)

    def test_lzm1_round_trips_including_its_edge_cases(self) -> None:
        state = 0x9E3779B9
        noise = bytearray()
        while len(noise) < 6000:
            state ^= (state << 13) & 0xFFFFFFFF
            state ^= state >> 17
            state ^= (state << 5) & 0xFFFFFFFF
            noise += state.to_bytes(4, "little")
        for name, data in (("empty", b""), ("one byte", b"A"),
                           ("a long run", bytes(9000)),
                           ("a two-byte cycle", b"ab" * 5000),
                           ("incompressible", bytes(noise))):
            with self.subTest(name):
                stream = mmap_art.lzm1_compress(data)
                self.assertEqual(stream[0], mmap_art.LZM1_HEADER_BYTE)
                self.assertEqual(mmap_art.lzm1_decompress(stream), data)

    def test_a_replacement_of_the_wrong_size_is_refused_naming_the_size(self) -> None:
        member = containers.synthetic_mmap(32, 32, retail_layout=True)
        with self.assertRaises(mmap_art.MmapError) as caught:
            mmap_art.encode_image(member, 0, b"\x00" * (16 * 16 * 4))
        self.assertIn("32x32", str(caught.exception))
        self.assertIn("4096", str(caught.exception))

    def test_a_clut_replacement_of_the_wrong_length_is_refused(self) -> None:
        member = containers.synthetic_mmap(32, 32, retail_layout=True)
        with self.assertRaises(mmap_art.MmapError) as caught:
            mmap_art.encode(member, palettes={0: [(1, 2, 3, 4)] * 8})
        self.assertIn("256 entries", str(caught.exception))

    def test_an_edit_only_moves_the_pixels_that_changed(self) -> None:
        member = containers.synthetic_mmap(32, 32, seed=9, retail_layout=True)
        width, height, rgba = mmap_art.decode_rgba(member)
        edited = bytearray(rgba)
        texture = mmap_art.parse(member)
        entries = mmap_art.read_palette(member, texture.palettes[0])
        target = tuple(entries[200][:3]) + (mmap_art._scale_alpha(entries[200][3]),)
        edited[0:4] = bytes(target)
        out = mmap_art.encode_image(member, 0, bytes(edited))
        self.assertEqual(len(out), len(member))
        differing = [index for index, pair in enumerate(zip(member, out)) if pair[0] != pair[1]]
        self.assertEqual(len(differing), 1, "one pixel changed, so one byte should")
        self.assertEqual(mmap_art.decode_rgba(out)[2], bytes(edited))

    def test_quantise_is_lossless_when_the_image_already_fits(self) -> None:
        pixels = [(value * 16, 255 - value * 16, value * 8, 255) for value in range(16)]
        rgba = b"".join(bytes(pixels[(x * 3 + y) % 16])
                        for y in range(8) for x in range(8))
        result = mmap_art.quantise(rgba, 8, 8, 16)
        self.assertTrue(result.lossless)
        self.assertEqual(result.colours_in_image, 16)
        self.assertIn("no loss", result.note())

    def test_quantise_states_the_loss_when_it_has_to_reduce(self) -> None:
        rgba = b"".join(bytes(((value * 7) & 0xFF, (value * 13) & 0xFF,
                               (value * 29) & 0xFF, 255)) for value in range(256))
        result = mmap_art.quantise(rgba, 16, 16, 16)
        self.assertFalse(result.lossless)
        self.assertEqual(result.colours_wanted, 16)
        self.assertLessEqual(max(result.indices), 15)
        self.assertGreater(result.max_channel_error, 0)
        self.assertIn("mean squared error", result.note())

    def test_a_quantised_clut_can_be_written_and_read_back(self) -> None:
        member = containers.synthetic_mmap(16, 16, retail_layout=True, bits=4)
        rgba = b"".join(bytes((value * 3 % 256, value * 5 % 256, value * 11 % 256, 255))
                        for value in range(256))
        result = mmap_art.quantise(rgba, 16, 16, 16)
        texture = mmap_art.parse(member)
        out = mmap_art.encode(member, levels={(0, 0): rgba},
                              palettes={0: list(result.entries)}, texture=texture)
        width, height, drawn = mmap_art.decode_rgba(out)
        self.assertEqual((width, height), (16, 16))
        self.assertEqual(len(set(drawn[i:i + 4] for i in range(0, len(drawn), 4))), 16)


if __name__ == "__main__":
    unittest.main()
