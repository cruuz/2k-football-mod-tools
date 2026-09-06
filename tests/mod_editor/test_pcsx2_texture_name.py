"""The PCSX2 replacement-name derivation, on data these tests make.

The real proof -- 2,994 of 3,024 dump-identified textures of the retail Madden
NFL 09 disc reproducing their dumped TEX0 hash from the disc bytes, and the
dumped names pixels could not place placed by hash alone -- needs the disc and
the dumps and is
recorded in ``docs/product/measured/madden09_ps2/``.  What runs here is the
structure that proof stands on: the block layout is a bijection, the two
hashing paths are the ones the emulator takes, a mip chain hashes as one
stream, the name grammar round-trips, and the hash itself is the same XXH3-64
that ``tools/xxh3.py`` and, when it is importable, the ``xxhash`` extension
compute.  No retail byte is in this file.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import random
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from mod_editor.games._formats import pcsx2_texture_name as names  # noqa: E402
from mod_editor.games._formats import xxhash3_64  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402

import xxh3 as tools_xxh3  # noqa: E402  (the dev-time twin, kept in step)


class HashTests(unittest.TestCase):
    """The formats package's XXH3-64 is the one the rest of the repository already trusts."""

    def test_the_secret_is_the_one_pcsx2_vendors(self) -> None:
        self.assertEqual(hashlib.sha256(xxhash3_64.KSECRET).hexdigest(),
                         "2cf2f88bf9b71283059b6df53e5bcde20adbfd9e8d6ce2c1ab106262bb283bed")

    def test_the_published_vectors(self) -> None:
        # xxHash's own sanity vectors for an empty input and a one-byte one.
        self.assertEqual(xxhash3_64.xxh3_64_python(b""), 0x2D06800538D394C2)
        self.assertEqual(xxhash3_64.xxh3_64_python(tools_xxh3._sanity_buffer(1)),
                         0xC44BDFF4074EECDB)

    def test_every_length_class_agrees_with_the_tools_twin(self) -> None:
        rng = random.Random(20260905)
        for length in list(range(0, 260)) + [512, 1023, 1024, 4096, 16384]:
            payload = bytes(rng.randrange(256) for _ in range(length))
            for seed in (0, 7):
                self.assertEqual(xxhash3_64.xxh3_64_python(payload, seed),
                                 tools_xxh3.xxh3_64_python(payload, seed), (length, seed))

    def test_the_accelerator_when_present_agrees_with_the_pure_path(self) -> None:
        if not xxhash3_64.ACCELERATED:
            self.skipTest("xxhash is not importable here; the pure path is the product")
        rng = random.Random(1)
        for length in (0, 3, 16, 17, 128, 129, 240, 241, 1000, 65536):
            payload = bytes(rng.randrange(256) for _ in range(length))
            self.assertEqual(xxhash3_64.xxh3_64(payload), xxhash3_64.xxh3_64_python(payload))

    def test_hex_is_unpadded_lower_case(self) -> None:
        self.assertEqual(xxhash3_64.xxh3_64_hex(b"x"), "%x" % xxhash3_64.xxh3_64(b"x"))
        self.assertNotIn("0x", xxhash3_64.xxh3_64_hex(b"x"))


class BlockLayoutTests(unittest.TestCase):
    """A 256-byte block holds every texel of its tile exactly once."""

    def test_the_8_bit_block_is_a_bijection_onto_256_bytes(self) -> None:
        offsets = sorted(names.block_offset_8(x, y) for y in range(16) for x in range(16))
        self.assertEqual(offsets, list(range(256)))

    def test_the_4_bit_block_is_a_bijection_onto_512_nibbles(self) -> None:
        nibbles = sorted(names.block_nibble_4(x, y) for y in range(16) for x in range(32))
        self.assertEqual(nibbles, list(range(512)))

    def test_each_column_holds_four_whole_rows(self) -> None:
        # The GS reads a block as four 64-byte columns of four texel rows each.
        for column in range(4):
            texels = {(x, y) for y in range(16) for x in range(16)
                      if names.block_offset_8(x, y) // 64 == column}
            self.assertEqual(texels, {(x, y) for y in range(column * 4, column * 4 + 4)
                                      for x in range(16)})

    def test_the_arrangement_alternates_between_row_pairs_and_columns(self) -> None:
        # Rows 0-1 and 2-3 of a column differ by the swap; the swap flips again
        # between an even column and an odd one.  This is the shape the dumps
        # confirmed; a layout without the alternation names every texture wrong.
        def swapped(row: int) -> bool:
            return names.block_offset_8(0, row) // 32 % 2 == 1
        self.assertEqual([swapped(row) for row in (0, 2, 4, 6)], [False, True, True, False])

    def test_block_image_places_a_texel_where_the_table_says(self) -> None:
        width, height = 32, 32
        indices = bytes(range(256)) * 4
        image = names.block_image(indices, width, height, 8)
        self.assertEqual(len(image), width * height)
        # Block (1, 1) covers texels x 16..31, y 16..31 and is the fourth block.
        x, y = 21, 19
        expected_slot = 3 * 256 + names.block_offset_8(x - 16, y - 16)
        self.assertEqual(image[expected_slot], indices[y * width + x])

    def test_a_4_bit_block_image_packs_two_texels_a_byte_low_nibble_first(self) -> None:
        width, height = 32, 16
        indices = bytes((position * 7) & 0x0F for position in range(width * height))
        image = names.block_image(indices, width, height, 4)
        self.assertEqual(len(image), 256)
        x, y = 5, 6
        nibble = names.block_nibble_4(x, y)
        byte = image[nibble >> 1]
        value = (byte >> 4) if nibble & 1 else (byte & 0x0F)
        self.assertEqual(value, indices[y * width + x])

    def test_a_flat_texture_hashes_the_same_either_way(self) -> None:
        # Every texel equal: swizzling is invisible, so the block hash equals
        # the linear hash.  A regression here would mean the permutation drops
        # or duplicates a texel.
        indices = bytes([9]) * (64 * 64)
        self.assertEqual(names.block_image(indices, 64, 64, 8), indices)

    def test_a_partial_block_is_refused_by_name(self) -> None:
        with self.assertRaises(Refusal) as caught:
            names.block_image(bytes(48 * 16), 48, 16, 4)
        self.assertIn("whole number of 32x16 blocks", str(caught.exception))


class HashingPathTests(unittest.TestCase):
    def test_smaller_than_a_block_hashes_the_linear_texels(self) -> None:
        indices = bytes(range(64))
        stream, path = names.hashed_stream(indices, 8, 8, 8)
        self.assertEqual((stream, path), (indices, names.PATH_LINEAR))
        stream4, path4 = names.hashed_stream(bytes(range(16)) * 16, 16, 16, 4)
        # 16 wide is below the 32-texel 4-bit block, so the expansion path:
        # one byte per texel, nibbles NOT packed.
        self.assertEqual(path4, names.PATH_LINEAR)
        self.assertEqual(len(stream4), 256)

    def test_a_whole_block_hashes_the_block_image(self) -> None:
        indices = bytes((position * 3) & 0xFF for position in range(16 * 16))
        stream, path = names.hashed_stream(indices, 16, 16, 8)
        self.assertEqual(path, names.PATH_BLOCKS)
        self.assertEqual(stream, names.block_image(indices, 16, 16, 8))
        self.assertNotEqual(stream, indices)

    def test_a_non_power_of_two_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            names.hashed_stream(bytes(96 * 32), 96, 32, 8)
        self.assertIn("not a power of two", str(caught.exception))

    def test_a_chain_hashes_as_one_stream(self) -> None:
        base = names.TextureLevel(32, 32, 8, bytes((p * 5) & 0xFF for p in range(1024)))
        mip = names.TextureLevel(16, 16, 8, bytes((p * 11) & 0xFF for p in range(256)))
        small = names.TextureLevel(8, 8, 8, bytes(range(64)))
        chains = names.tex0_hash_chains((base, mip, small))
        self.assertEqual(set(chains), {(0, 1), (0, 2), (0, 3), (1, 1), (1, 2), (2, 1)})
        joined = (names.hashed_stream(base.indices, 32, 32, 8)[0]
                  + names.hashed_stream(mip.indices, 16, 16, 8)[0])
        self.assertEqual(chains[(0, 2)], xxhash3_64.xxh3_64(joined))
        self.assertEqual(chains[(2, 1)], xxhash3_64.xxh3_64(small.indices))
        self.assertEqual(names.tex0_hash((base, mip, small)), chains[(0, 3)])

    def test_the_clut_hash_covers_four_bytes_an_entry_in_drawing_order(self) -> None:
        palette = [(index, 255 - index, index // 2, 128) for index in range(256)]
        raw = b"".join(bytes(entry) for entry in palette)
        self.assertEqual(names.clut_hash(palette), xxhash3_64.xxh3_64(raw))
        with self.assertRaises(Refusal):
            names.clut_hash(palette[:20])


class NameGrammarTests(unittest.TestCase):
    def test_bits_pack_psm_tw_th_tcc(self) -> None:
        self.assertEqual(names.texture_bits(names.PSMT8, 7, 7, 1), 0x5DD3)
        self.assertEqual(names.texture_bits(names.PSMT4, 6, 6, 0), 0x1994)

    def test_names_are_unpadded_hashes_and_an_eight_digit_word(self) -> None:
        self.assertEqual(names.replacement_name(0x405AA0413AB4001, 0xF25587A8EB66663E, 0x5DD3),
                         "405aa0413ab4001-f25587a8eb66663e-00005dd3.png")
        self.assertEqual(names.replacement_name(1, None, 0x5DD3), "1-00005dd3.png")
        self.assertEqual(names.replacement_name(1, 2, 0x5DD3, region=(32, 0)),
                         "1-2-r32x0-00005dd3.png")
        self.assertEqual(names.replacement_name(1, 2, 0x5DD3, mip=2), "1-2-00005dd3-mip2.png")

    def test_parse_reads_back_every_field(self) -> None:
        parsed = names.parse_name("405aa0413ab4001-f25587a8eb66663e-r32x0-00005dd3.png")
        self.assertEqual((parsed.tex0, parsed.clut), (0x405AA0413AB4001, 0xF25587A8EB66663E))
        self.assertEqual((parsed.psm, parsed.tw, parsed.th, parsed.tcc), (19, 7, 7, 1))
        self.assertEqual(parsed.region, (32, 0))
        self.assertEqual((parsed.width, parsed.height), (32, 128))
        self.assertIsNone(names.parse_name("1-00001dd3.png").clut)
        with self.assertRaises(Refusal):
            names.parse_name("not-a-texture.png")

    def test_derive_names_lists_every_chain_under_both_conventions(self) -> None:
        base = names.TextureLevel(32, 32, 4, bytes((p * 5) & 0x0F for p in range(1024)))
        mip = names.TextureLevel(16, 16, 4, bytes((p * 11) & 0x0F for p in range(256)))
        palette = [(i * 16, 255 - i * 16, i, 128) for i in range(16)]
        derived = names.derive_names((base, mip), palette)
        modern = [item for item in derived if item.convention == names.CONVENTION_MODERN]
        classic = [item for item in derived if item.convention == names.CONVENTION_CLASSIC]
        # three chains: (0,2) (0,1) (1,1); classic once per TCC value.
        self.assertEqual(len(modern), 3)
        self.assertEqual(len(classic), 6)
        self.assertEqual((modern[0].base_level, modern[0].level_count), (0, 2))
        first = names.parse_name(modern[0].name)
        self.assertEqual((first.psm, first.tw, first.th, first.tcc), (20, 5, 5, 0))
        self.assertEqual(first.clut, names.clut_hash(palette))
        by_convention = names.names_by_convention(derived)
        self.assertEqual(set(by_convention), {"modern", "classic"})
        # A classic TCC-clear name is byte-identical to the modern one.
        self.assertTrue(set(by_convention["modern"]) <= set(by_convention["classic"]))
        tcc_set = [names.parse_name(item.name).tcc for item in classic]
        self.assertEqual(sorted(set(tcc_set)), [0, 1])

    def test_derive_refuses_a_chain_that_does_not_halve(self) -> None:
        base = names.TextureLevel(32, 32, 8, bytes(1024))
        odd = names.TextureLevel(8, 8, 8, bytes(64))
        with self.assertRaises(Refusal) as caught:
            names.derive_names((base, odd), [(0, 0, 0, 0)] * 256)
        self.assertIn("halves each step", str(caught.exception))

    def test_derive_refuses_a_palette_of_the_wrong_size(self) -> None:
        base = names.TextureLevel(16, 16, 8, bytes(256))
        with self.assertRaises(Refusal):
            names.derive_names((base,), [(0, 0, 0, 0)] * 16)


if __name__ == "__main__":
    unittest.main()
