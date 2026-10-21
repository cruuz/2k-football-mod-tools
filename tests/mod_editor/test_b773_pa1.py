"""pa1 (b773, N32): the 2026 pants hem above the knee. The hem shape and its exact-integer blend, the joint clean and
wet palette choice, the twin folds, the shipped data (kits, exclusions, pins chained after uf1, uf2 and uf3), the
build order, refusals and the in-place native repair."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
from mod_editor.core import nfl2k5_pants_hem_2026 as hem  # noqa: E402
from tools.b77 import pa1_repair as repair  # noqa: E402
import pa1_author as author  # noqa: E402

FLAT_HEM = dict(points=[[0.0, 10.25], [32.0, 10.25]], shadow=[[0, 1, 80]])


class Shape(unittest.TestCase):
    def test_cover_is_zero_above_full_below_and_partial_on_the_edge(self):
        cover, weight = hem.hem_shape(FLAT_HEM, 32, 16)
        self.assertTrue((cover[:10] == 0).all())
        self.assertTrue((cover[10] == 12).all())          # a quarter of the 4x4 samples lie above y=10.25
        self.assertTrue((cover[11:] == hem.FULL).all())
        self.assertTrue((weight <= cover * 100).all())

    def test_shadow_band_darkens_only_the_first_texel_under_the_hem(self):
        _cover, weight = hem.hem_shape(FLAT_HEM, 32, 16)
        self.assertTrue((weight[12:] == hem.FULL * 100).all())
        self.assertTrue((weight[11] < hem.FULL * 100).all())

    def test_box_masks_the_other_atlas_islands(self):
        shape = dict(FLAT_HEM, box=[0, 0, 16, 14])
        cover, weight = hem.hem_shape(shape, 32, 16)
        self.assertTrue((cover[:, 16:] == 0).all() and (cover[14:] == 0).all())
        self.assertTrue((weight[:, 16:] == 0).all())

    def test_coverage_is_cached_read_only_and_equal_to_the_kit_compiler(self):
        poly = hem.below(FLAT_HEM["points"], 0.0, 16, 0, 32)
        got = hem.coverage(poly, 32, 16)
        self.assertTrue(np.array_equal(got, fixes.polygon_coverage(poly, 32, 16)))
        self.assertIs(got, hem.coverage(poly, 32, 16))
        with self.assertRaises(ValueError):
            got[0, 0] = 1

    def test_blend_is_exact_at_the_ends(self):
        base = np.full((2, 2, 3), 200, np.int64)
        cover = np.array([[0, hem.FULL], [8, hem.FULL]])
        weight = np.array([[0, hem.FULL * 100], [800, hem.FULL * 80]])
        out = hem.blend(base, (10, 20, 30), cover, weight)
        self.assertEqual(out[0, 0].tolist(), [200, 200, 200])
        self.assertEqual(out[0, 1].tolist(), [10, 20, 30])
        self.assertEqual(out[1, 0].tolist(), [105, 110, 115])
        self.assertEqual(out[1, 1].tolist(), [8, 16, 24])


class Palette(unittest.TestCase):
    def test_nearest_pairs_equals_brute_force(self):
        rng = np.random.default_rng(7)
        palette = rng.integers(0, 256, (256, 4))
        mud = rng.integers(0, 256, (256, 4))
        clean = rng.integers(0, 256, (400, 3))
        wet = rng.integers(0, 256, (400, 3))
        clean[200:], wet[200:] = clean[:200], wet[:200]
        cand = list(range(0, 256, 3))
        got = hem.nearest_pairs(clean, wet, palette, mud, cand)
        for i in range(len(clean)):
            d = [((clean[i] - palette[c, :3]) ** 2).sum() * hem.WET_WEIGHT + ((wet[i] - mud[c, :3]) ** 2).sum()
                 for c in cand]
            self.assertEqual(got[i], cand[int(np.argmin(d))])

    def test_legging_and_shadow_come_first_then_edges(self):
        palette = np.zeros((256, 4), np.int64)
        palette[:, 3] = 255
        palette[1, :3] = (250, 250, 250)
        clean = np.array([[250, 250, 250]] * 5 + [[120, 120, 120]] * 50 + [[10, 10, 200]] * 50)
        out = hem.choose_entries(palette, None, [0, 1], clean, np.zeros_like(clean), (10, 10, 200), None, [80], 10)
        self.assertEqual([r for _c, _m, r in out[:2]], ["legging", "shadow"])
        self.assertEqual(out[0][0], (10, 10, 200))
        self.assertEqual(out[1][0], (8, 8, 160))
        self.assertIn((120, 120, 120), [c for c, _m, _r in out])

    def test_an_exact_legging_entry_is_reused(self):
        palette = np.zeros((256, 4), np.int64)
        palette[:, 3] = 255
        palette[5, :3] = (10, 10, 200)
        clean = np.array([[10, 10, 200]] * 9)
        out = hem.choose_entries(palette, None, [5], clean, np.zeros_like(clean), (10, 10, 200), None, [], 10)
        self.assertEqual(out, [])

    def test_twin_folds_skip_excluded_slots_and_move_each_texel_once(self):
        palette = np.zeros((256, 4), np.int64)
        palette[:, 3] = 255
        for i in range(256):
            palette[i, :3] = (i * 7 % 256, i * 13 % 256, i * 29 % 256)
        palette[10, :3], palette[11, :3], palette[12, :3] = (100, 100, 100), (101, 100, 100), (102, 100, 100)
        palette[20, :3], palette[21, :3] = (50, 50, 50), (50, 51, 50)
        plane = np.array([[10, 11, 12, 20], [21, 21, 11, 3]], np.uint8)
        planes = [plane.copy()]
        freed, moved = hem.merge_twins(palette, None, planes, 5, 1, {20})
        self.assertNotIn(20, freed)
        self.assertTrue(set(freed).isdisjoint(set(planes[0].ravel().tolist())))
        before = palette[plane]
        after = palette[planes[0]]
        self.assertLessEqual(np.abs(before - after).max(), 1)
        self.assertEqual(moved, int(sum((plane == f).sum() for f in freed)))


DATA = hem.spec()


class ShippedData(unittest.TestCase):
    def test_every_current_kit_has_its_three_textures(self):
        current, skipped = author.kits()
        self.assertEqual(hem.selectors(DATA), sorted(k["selector"] for k in current))
        self.assertEqual(DATA["excluded"], skipped)
        kept = {k["selector"] for k in DATA["sideline_kept"]}
        self.assertLessEqual(len(kept), 8)
        for selector in hem.selectors(DATA):
            rows = sorted((r["chunk"], r["kind"], r["texture"]) for r in DATA["textures"] if r["selector"] == selector)
            want = [(2, "pants", "pants00"), (47, "bump", "bump_pants"), (51, "splayer", "splayer")]
            self.assertEqual(rows, want[:2] if selector in kept else want)

    def test_kept_sideline_atlases_had_no_room_in_retail(self):
        for kept in DATA["sideline_kept"]:
            self.assertIn("keeps its retail hem", kept["why"])
            self.assertLessEqual(kept["retail_need"], kept["retail_scratch"])

    def test_primaries_and_alternates_in_throwbacks_out(self):
        selectors = set(hem.selectors(DATA))
        for code in author.FRANCHISES:
            self.assertIn(f"{code}H0", selectors)
            self.assertIn(f"{code}A0", selectors)
        out = {k["selector"] for k in DATA["excluded"]}
        for team, style in author.EXCLUDED:
            code = {v: k for k, v in author.FRANCHISES.items()}[team]
            for side in "HA":
                self.assertIn(f"{code}{side}{style}", out)
                self.assertNotIn(f"{code}{side}{style}", selectors)
        self.assertEqual(len(selectors), 164)

    def test_hem_sits_above_the_knee_inside_the_spec_range(self):
        self.assertEqual(DATA["fraction"], author.FRACTION)
        self.assertTrue(0.42 <= DATA["fraction"] <= 0.49 and DATA["fraction"] < 0.507)
        rows = [y for _x, y in DATA["hem"]["pants"]["points"]]
        self.assertTrue(195 < min(rows) and max(rows) < 216)
        side = [y for _x, y in DATA["hem"]["splayer"]["points"]]
        self.assertEqual(DATA["hem"]["splayer"]["box"], author.SPLAYER_BOX)
        self.assertTrue(75 < min(side) and max(side) < DATA["hem"]["splayer"]["box"][3])

    def test_pins_are_complete_and_unique(self):
        for row in DATA["textures"]:
            self.assertEqual(len(row["before_sha256"]), 64)
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            if row["kind"] == "pants":
                self.assertRegex(row["legging"], "^#[0-9A-F]{6}$")
                self.assertRegex(row["legging_wet"], "^#[0-9A-F]{6}$")
                self.assertEqual(row["socks_chunk"], 4)
        self.assertEqual(len({(r["selector"], r["chunk"]) for r in DATA["textures"]}), len(DATA["textures"]))

    def test_input_pins_are_the_output_of_the_earlier_kit_passes(self):
        mine = {(r["selector"], r["chunk"]): r for r in DATA["textures"]}
        socks = {r["selector"]: r["socks_sha256"] for r in DATA["textures"] if r["kind"] == "pants"}
        checked = 0
        for document in (fixes.spec(), fixes.alternates(), fixes.finish()):
            for row in document["textures"]:
                key = (row["selector"], row["chunk"])
                if key in mine:
                    self.assertEqual(mine[key]["before_sha256"], row["after_sha256"], key)
                    checked += 1
                if row["chunk"] == 4 and row["selector"] in socks:
                    self.assertEqual(socks[row["selector"]], row["after_sha256"], key)
                    checked += 1
        self.assertGreater(checked, 30)

    def test_no_private_paths_in_shipped_files(self):
        for path in (hem.DATA, Path(hem.__file__), ROOT / "tools/b77/pa1_author.py", ROOT / "tools/b77/pa1_repair.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("/home/", text)
            self.assertNotIn("/media/", text)


class Build(unittest.TestCase):
    def test_build_runs_it_after_the_uf3_finish(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertLess(source.index("kit_fixes.apply_finish(target)"), source.index('_core_module("nfl2k5_pants_hem_2026")'))
        self.assertLess(source.index('_core_module("nfl2k5_menu_icon_uf3")'),
                        source.index('_core_module("nfl2k5_pants_hem_2026")'))

    def test_unrelated_image_is_skipped_by_studio_but_refused_by_native_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.iso"
            path.write_bytes(b"\0" * 4096)
            self.assertEqual(hem.apply_to_image(path)["state"], "other_image")
            with self.assertRaises((ValueError, OSError)):
                hem.apply_to_image(path, strict=True)
            self.assertEqual(path.read_bytes(), b"\0" * 4096)

    def test_native_tool_refuses_a_wrong_disc_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            disc = Path(tmp) / "small.iso"
            disc.write_bytes(b"\0" * 1024)
            with self.assertRaises(SystemExit):
                repair.main(["--disc", str(disc), "--receipts", str(Path(tmp) / "r")])
            self.assertFalse((Path(tmp) / "r").exists())
            self.assertEqual(disc.read_bytes(), b"\0" * 1024)
        self.assertEqual(repair.BASE_SHA256, "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4")


DISC = os.environ.get("NFL2K5_PA1_DISC")


@unittest.skipUnless(DISC, "set NFL2K5_PA1_DISC (the v0.6.1 base disc, read only) for native integration")
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raws, cls.ranges, cls.extents = repair.read_resources(Path(DISC), DATA)

    def test_compile_matches_pins_and_only_owned_bytes_change(self):
        cache = {}
        owned = {}
        for row in DATA["textures"]:
            owned.setdefault(row["selector"], []).append((row["offset"], row["offset"] + row["length"]))
        for selector, raw in sorted(self.raws.items()):
            replacements, receipt = hem.compile_resource(selector, raw, strict=True, document=DATA, cache=cache)
            self.assertEqual(receipt["state"], "applied")
            self.assertEqual(len(replacements), len(owned[selector]))
            new = bytearray(raw)
            for at, data in replacements:
                new[at:at + len(data)] = data
                self.assertTrue(any(lo <= at and at + len(data) <= hi for lo, hi in owned[selector]))
            again, receipt = hem.compile_resource(selector, bytes(new), strict=True, document=DATA)
            self.assertEqual((again, receipt["changed_bytes"]), ([], 0))

    def test_leggings_are_the_kits_own_upper_sock_colours(self):
        from nfl_txtr import parse_chunks
        for selector in ("01H0", "18H0", "29A0"):
            raw = self.raws[selector]
            chunks = {c.index: c for c in parse_chunks(raw, allow_trailing=True)}
            clean, wet = author.sock_colours(raw[chunks[4].offset:chunks[4].end_offset])
            row = [r for r in DATA["textures"] if r["selector"] == selector and r["kind"] == "pants"][0]
            self.assertEqual((author.hexc(clean), author.hexc(wet)), (row["legging"], row["legging_wet"]))

    def test_no_other_archive_entry_shares_an_owned_byte(self):
        self.assertEqual(repair.alias_check(self.ranges, self.extents), [])

    def test_no_owned_span_in_pack_0_none_overlaps_st1_or_uf3(self):
        self.assertFalse({r["file"] for r in self.ranges} & {"vc_53450030/0"})
        self.assertEqual(repair.st1_disjointness(self.ranges)["overlapping_bytes"], 0)
        self.assertEqual(repair.uf3_disjointness(Path(DISC), self.ranges)["overlapping_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
