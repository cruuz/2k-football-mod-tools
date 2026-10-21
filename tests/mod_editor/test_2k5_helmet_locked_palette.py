"""Locked helmet colours remain exact when a fixed VC-LZ span needs fewer colours."""
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import nfl_live_helmet_txtr_png_import as helmet
import nfl_tset_png_import as palette
from nfl_txtr import compress_vc_lz, decompress_vc_lz


class LockedHelmetPaletteTests(unittest.TestCase):
    @staticmethod
    def fixture():
        rng = random.Random(7734)
        colors = [(i & 255, (i >> 8) * 127, (i * 37) & 255, 255) for i in range(320)]
        pixels = colors + rng.choices(colors, k=704)
        levels = [palette.MipLevel(0, 32, 32, bytes(v for c in pixels for v in c))]
        return levels, colors

    @staticmethod
    def decoded(colors, indices):
        return palette.palette_bytes(colors) + b"".join(indices)

    def fit_at(self, levels, locked, maximum):
        colors, indices, _ = palette.quantize_levels(levels, maximum, locked_colors=locked)
        decoded = self.decoded(colors, indices)
        compressed, _ = compress_vc_lz(decoded, stream_tag=1, offset_bits=12)
        return decoded, compressed

    def test_207_reserved_colours_fit_without_crossing_the_floor(self):
        levels, colors = self.fixture()
        locked = colors[:207]
        floor, limits = helmet._locked_palette_budget(locked)
        self.assertEqual(floor, 207)
        _, large = self.fit_at(levels, locked, 256)
        _, small = self.fit_at(levels, locked, 208)
        self.assertGreater(len(large), len(small))
        fit = palette.quantize_levels_to_vc_lz_bound(
            levels, self.decoded, stream_tag=1, offset_bits=12, max_encoded_size=len(small),
            quantizer=lambda source, maximum: palette.quantize_levels(source, maximum, locked_colors=locked),
            minimum_palette_limit=floor, palette_limits=limits)
        self.assertEqual(fit.attempts[0]["result"], "vc_lz_overflow")
        self.assertEqual(fit.attempts[-1]["result"], "fit")
        self.assertTrue(all(row["maximum_palette_entries"] >= 207 for row in fit.attempts))
        self.assertTrue(set(locked) <= set(fit.palette))
        actual, info = decompress_vc_lz(fit.compressed, len(fit.decoded))
        self.assertEqual(actual, fit.decoded)
        self.assertEqual(info.consumed_bytes, len(fit.compressed))
        for source, indices in zip(levels, fit.index_levels):
            for at, index in enumerate(indices):
                pixel = tuple(source.rgba[4 * at:4 * at + 4])
                if pixel in locked:
                    self.assertEqual(fit.palette[index], pixel)

    def test_previously_successful_128_tier_is_byte_identical(self):
        levels, colors = self.fixture()
        locked = colors[:50]
        _, bound = self.fit_at(levels, locked, 128)
        kwargs = dict(stream_tag=1, offset_bits=12, max_encoded_size=len(bound),
                      quantizer=lambda source, maximum: palette.quantize_levels(source, maximum, locked_colors=locked))
        old = palette.quantize_levels_to_vc_lz_bound(levels, self.decoded, **kwargs)
        floor, limits = helmet._locked_palette_budget(locked)
        new = palette.quantize_levels_to_vc_lz_bound(levels, self.decoded, **kwargs,
                                                    minimum_palette_limit=floor, palette_limits=limits)
        self.assertEqual(old.attempts[-1]["maximum_palette_entries"], 128)
        self.assertEqual((new.compressed, new.decoded, new.index_levels, new.palette, new.attempts),
                         (old.compressed, old.decoded, old.index_levels, old.palette, old.attempts))

    def test_unlocked_and_exact_legacy_floors_keep_the_existing_ladder(self):
        self.assertEqual(helmet._locked_palette_budget([]), (2, palette._BOUNDED_PALETTE_LIMITS))
        for count in (2, 4, 8, 16, 32, 64, 128, 256):
            floor, limits = helmet._locked_palette_budget([(i, 0, 0, 255) for i in range(count)])
            self.assertEqual(floor, count)
            self.assertEqual(limits, tuple(n for n in palette._BOUNDED_PALETTE_LIMITS if n >= count))

    def test_duplicate_locks_are_counted_once(self):
        self.assertEqual(helmet._locked_palette_budget([(1, 2, 3, 255)] * 300),
                         (2, palette._BOUNDED_PALETTE_LIMITS))

    def test_invalid_colours_and_more_than_256_unique_locks_refuse(self):
        cases = [[(1, 2, 3)], [(256, 0, 0, 255)], [(-1, 0, 0, 255)], [(True, 0, 0, 255)],
                 [(1.0, 0, 0, 255)], [(i & 255, i >> 8, 0, 255) for i in range(257)]]
        for locked in cases:
            with self.subTest(locked=locked[:2]), self.assertRaisesRegex(ValueError, "locked palette colors"):
                helmet._locked_palette_budget(locked)


if __name__ == "__main__":
    unittest.main()
