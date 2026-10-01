"""Nameplate atlas mips keep coverage the way retail's do; the region-majority
chain is only a logged fallback for a slot that cannot hold the area chain.

Beta 76 (k2): the Seahawks' nameplate read in play as a dark, noisy patch on the
upper back at a grazing angle. The live-art importer built nameplate mips by
region majority, which turns thin letter strokes into solid blocks at levels
2-5; retail's own atlas mips keep each level's mean coverage.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

_ROOT = Path(__file__).resolve().parents[2]
for _path in (_ROOT, _ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import nfl_live_numbers_nameplate_png_import as live  # noqa: E402
from nfl_tset_png_import import QualityBudgetError  # noqa: E402

_REAL_INDEX = Path(os.environ.get(
    "NFL2K5_TEST_INDEX", str(_ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")))
_REAL_REPORT = _ROOT / "reports/assets/nfl2k5_live_numbers_nameplate_compatibility.json"
_HAVE_REAL_INDEX = _REAL_INDEX.is_file() and _REAL_REPORT.is_file()

NAVY = (10, 42, 78)
WIDTH, HEIGHT, LEVELS = 1024, 32, 6


def letter_strip(width: int = WIDTH, height: int = HEIGHT) -> bytes:
    """A letter-like atlas: two-texel navy strokes (stems, bars and a diagonal)
    in 32-texel cells on a transparent strip, with a one-texel soft edge."""
    out = bytearray(width * height * 4)

    def put(x: int, y: int, alpha: int) -> None:
        if 0 <= x < width and 0 <= y < height:
            i = (y * width + x) * 4
            if alpha > out[i + 3]:
                out[i:i + 4] = bytes((*NAVY, alpha))

    for cell in range(0, width, 32):
        for y in range(4, 28):
            for x in (cell + 6, cell + 7, cell + 20, cell + 21):
                put(x, y, 255)
            put(cell + 5, y, 96)
            put(cell + 22, y, 96)
            d = cell + 6 + (y - 4) // 2
            put(d, y, 255)
            put(d + 1, y, 160)
        for x in range(cell + 6, cell + 22):
            for y in (4, 5, 15, 16):
                put(x, y, 255)
    # a transparent texel carrying a stray colour beside a stroke: it must not tint
    i = (10 * width + 4) * 4
    out[i:i + 4] = bytes((255, 0, 0, 0))
    return bytes(out)


def mean_alpha(level) -> float:
    return sum(level.rgba[3::4]) / float(level.width * level.height)


class AreaMipsKeepCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.rgba = letter_strip()

    def test_every_area_level_keeps_the_base_coverage(self) -> None:
        levels = live.make_mips(self.rgba, WIDTH, HEIGHT, LEVELS, downsample="area")
        self.assertEqual([(lv.width, lv.height) for lv in levels],
                         [(1024, 32), (512, 16), (256, 8), (128, 4), (64, 2), (32, 1)])
        base = mean_alpha(levels[0])
        for lv in levels[1:]:
            with self.subTest(level=lv.level):
                self.assertAlmostEqual(mean_alpha(lv), base, delta=0.5)

    def test_majority_levels_turn_strokes_into_blocks(self) -> None:
        """The defect this change removes: at the small levels the majority
        chain paints far more solid texels than the base coverage."""
        majority = live.make_mips(self.rgba, WIDTH, HEIGHT, LEVELS)
        area = live.make_mips(self.rgba, WIDTH, HEIGHT, LEVELS, downsample="area")
        solid_majority = sum(a == 255 for a in majority[3].rgba[3::4])
        solid_area = sum(a == 255 for a in area[3].rgba[3::4])
        self.assertGreater(solid_majority, solid_area)
        drift = max(abs(mean_alpha(lv) - mean_alpha(majority[0])) for lv in majority[1:])
        self.assertGreater(drift, 1.0)

    def test_area_levels_are_exact_alpha_weighted_footprint_means(self) -> None:
        levels = live.make_mips(self.rgba, WIDTH, HEIGHT, LEVELS, downsample="area")
        base = levels[0].rgba
        for level in (1, 2, 3):
            stride = 1 << level
            lv = levels[level]
            for x, y in ((0, 0), (1, 1), (3, 0), (lv.width - 1, lv.height - 1)):
                alpha = red = 0
                for dy in range(stride):
                    for dx in range(stride):
                        i = ((y * stride + dy) * WIDTH + x * stride + dx) * 4
                        alpha += base[i + 3]
                        red += base[i] * base[i + 3]
                j = (y * lv.width + x) * 4
                with self.subTest(level=level, x=x, y=y):
                    self.assertEqual(lv.rgba[j + 3], (alpha + stride * stride // 2) // (stride * stride))
                    if alpha:
                        self.assertEqual(lv.rgba[j], (red + alpha // 2) // alpha)

    def test_invisible_colour_never_tints_an_edge(self) -> None:
        levels = live.make_mips(self.rgba, WIDTH, HEIGHT, LEVELS, downsample="area")
        for lv in levels:
            reds = [lv.rgba[i] for i in range(0, len(lv.rgba), 4) if lv.rgba[i + 3]]
            self.assertTrue(all(r == NAVY[0] for r in reds), f"level {lv.level} tinted")


class NameplateMajorityFallback(unittest.TestCase):
    def setUp(self) -> None:
        self.rgba = letter_strip()

    def test_the_area_chain_is_used_when_it_fits(self) -> None:
        floors = []

        def fit(levels, floor):
            floors.append(floor)
            return ("fit", levels)

        levels, bounded, mip_filter, fallback = live.fit_nameplate_levels(
            self.rgba, WIDTH, HEIGHT, LEVELS, fit, selector="26A0:nameplate", stored_size=7520)
        self.assertEqual(mip_filter, live.NAMEPLATE_AREA_MIP_FILTER)
        self.assertIsNone(fallback)
        self.assertEqual(floors, [live.NAMEPLATE_AREA_PALETTE_FLOOR])
        self.assertEqual(levels, live.make_mips(self.rgba, WIDTH, HEIGHT, LEVELS, downsample="area"))
        self.assertIs(bounded[1], levels)

    def test_the_majority_fallback_is_taken_and_logged_when_the_slot_cannot_fit(self) -> None:
        floors = []

        def fit(levels, floor):
            floors.append(floor)
            if floor == live.NAMEPLATE_AREA_PALETTE_FLOOR:
                error = QualityBudgetError("area chain overflows")
                error.attempts = ({"maximum_palette_entries": 16, "result": "vc_lz_overflow"},)
                raise error
            return ("fit", levels)

        with self.assertLogs(live.LOG, level="WARNING") as captured:
            levels, bounded, mip_filter, fallback = live.fit_nameplate_levels(
                self.rgba, WIDTH, HEIGHT, LEVELS, fit, selector="26A0:nameplate", stored_size=64)
        self.assertEqual(floors, [live.NAMEPLATE_AREA_PALETTE_FLOOR, 2])
        self.assertEqual(mip_filter, live.MAJORITY_MIP_FILTER)
        self.assertEqual(levels, live.make_mips(self.rgba, WIDTH, HEIGHT, LEVELS))
        self.assertEqual(fallback["used_filter"], live.MAJORITY_MIP_FILTER)
        self.assertEqual(fallback["requested_filter"], live.NAMEPLATE_AREA_MIP_FILTER)
        self.assertEqual(fallback["area_attempts"][0]["result"], "vc_lz_overflow")
        self.assertIn("NAMEPLATE_MIP_FALLBACK selector=26A0:nameplate stored_size=64", captured.output[0])

    def test_a_codec_fault_is_not_turned_into_a_fallback(self) -> None:
        def fit(levels, floor):
            raise ValueError("corrupt layout")

        with self.assertRaises(ValueError):
            live.fit_nameplate_levels(self.rgba, WIDTH, HEIGHT, LEVELS, fit)


@unittest.skipUnless(_HAVE_REAL_INDEX, "private retail index is unavailable")
class RetailNameplateCoverage(unittest.TestCase):
    """Retail's own nameplate atlas (decoded from the user's disc) keeps its
    coverage at every level; the area chain of its level 0 does too."""

    def test_retail_and_area_keep_coverage_majority_does_not(self) -> None:
        _, _, target = live.select_target("nameplate", "26", "A", 0, None, _REAL_REPORT)
        archive = live.parse_archive(_REAL_INDEX)
        entry = archive.entries[target.outer_index]
        span = live.read_entry_range(archive, entry, target.chunk_offset, target.span_size)
        chunk, decoded, texture = live.validate_template(span, target, False)
        retail = live.decode_levels(decoded, chunk, texture)
        base = mean_alpha(retail[0])
        for lv in retail[1:]:
            self.assertAlmostEqual(mean_alpha(lv), base, delta=1.5)
        area = live.make_mips(retail[0].rgba, retail[0].width, retail[0].height, len(retail),
                              downsample="area")
        for lv in area[1:]:
            self.assertAlmostEqual(mean_alpha(lv), base, delta=0.5)

    def test_build_import_takes_the_area_chain(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="nfl-nameplate-area-") as name:
            png = Path(name) / "nameplate.png"
            png.write_bytes(live.encode_rgba_png(WIDTH, HEIGHT, letter_strip()))
            _, _, report = live.build_import(_REAL_INDEX, _REAL_REPORT, "nameplate", "26", "A", 0, None, png)
        self.assertEqual(report["mips"]["filter"], live.NAMEPLATE_AREA_MIP_FILTER)
        self.assertNotIn("fallback", report["mips"])


if __name__ == "__main__":
    unittest.main()
