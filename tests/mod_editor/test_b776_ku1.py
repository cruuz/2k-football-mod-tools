"""ku1 (b776): the 2026 Kansas City Chiefs home and road kits redone to the current look."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes
from mod_editor.core import nfl2k5_glyph_fixes_2026 as glyphs
from mod_editor.core import nfl2k5_menu_chiefs_2026 as menu

# the b775 test disc (the pinned input) and the user's retail disc, e.g. NFL2K5_KU1_DISC=... NFL2K5_KU1_RETAIL=...
B775 = Path(os.environ.get("NFL2K5_KU1_DISC", "/nonexistent"))
RETAIL = Path(os.environ.get("NFL2K5_KU1_RETAIL", "/nonexistent"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hx(text):
    return fixes.hex_rgb(text)


class Remap(unittest.TestCase):
    PAIRS = [["#E31837", "#E4282E"], ["#FFB612", "#F7C542"], ["#FFFFFF", "#FFFFFF"], ["#000000", "#000000"]]

    def run_remap(self, colours, tol=8):
        new, hit = fixes.remap_colours(np.array(colours, np.int64), self.PAIRS, tol)
        return new.tolist(), hit.tolist()

    def test_scheme_colours_move_exactly(self):
        new, hit = self.run_remap([hx("#E31837"), hx("#FFB612"), hx("#FFFFFF"), hx("#000000")])
        self.assertEqual(new, [list(hx("#E4282E")), list(hx("#F7C542")), [255, 255, 255], [0, 0, 0]])
        self.assertEqual(hit, [True] * 4)

    def test_shades_and_blends_stay_shades_and_blends(self):
        half_red = [113, 12, 27]                                  # old red x 0.5 (a shade: blend with black)
        edge = [241, 140, 155]                                    # old red half way to white (an anti-aliased edge)
        mix = [241, 103, 37]                                      # old red half way to gold
        new, hit = self.run_remap([half_red, edge, mix])
        self.assertTrue(all(hit))
        self.assertTrue(np.all(np.abs(np.array(new[0]) - [114, 20, 23]) <= 1))
        self.assertTrue(np.all(np.abs(np.array(new[1]) - [242, 148, 151]) <= 1))
        self.assertTrue(np.all(np.abs(np.array(new[2]) - [238, 119, 56]) <= 1))

    def test_other_colours_are_left_alone(self):
        navy, shield_red, green = [1, 51, 105], [213, 10, 10], [0, 200, 0]
        new, hit = self.run_remap([navy, shield_red, green])
        self.assertEqual(new, [navy, shield_red, green])
        self.assertEqual(hit, [False, False, False])

    def test_palette_remap_keeps_clear_entries(self):
        palette = np.array([[227, 24, 55, 255], [227, 24, 55, 0], [9, 9, 9, 255]], np.int64)
        out, moved = fixes.remap_palette(palette, {"palette_remap": {"pairs": self.PAIRS, "tolerance": 8}})
        self.assertEqual(moved, [0])
        self.assertEqual(out[0].tolist(), [228, 40, 46, 255])
        self.assertEqual(out[1].tolist(), [227, 24, 55, 0])

    def test_menu_pull_moves_blue_into_green_on_reds_only(self):
        palette = np.array([[227, 24, 55, 255], [255, 182, 18, 255], [40, 40, 40, 255], [200, 30, 20, 255],
                            [227, 24, 55, 0]], np.int64)
        out, moved = menu.pull_palette(palette, {"red_over_green": 40, "red_over_blue": 20, "pull": [2, 5]})
        self.assertEqual(out[0].tolist(), [227, 36, 43, 255])
        self.assertEqual(out[1:].tolist(), palette[1:].tolist())
        self.assertEqual(moved.tolist(), [True, False, False, False, False])


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = fixes.chiefs()
        cls.glyph_doc = glyphs.spec()
        cls.menu_doc = menu.spec()

    def test_only_the_two_current_chiefs_kits_are_owned(self):
        owned = {(r["selector"], r["chunk"], r["kind"]) for r in self.doc["textures"]}
        expect = {(s, c, k) for s in ("13H0", "13A0")
                  for c, k in ((0, "unif"), (1, "tset"), (2, "tset"), (3, "tset"), (4, "tset"), (11, "txtr"),
                               (12, "txtr"), (51, "txtr"))}
        self.assertEqual(owned, expect)
        for row in self.doc["textures"]:
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
        routes = [r["ints"] for r in self.doc["textures"] if r["kind"] == "unif"]
        self.assertEqual(routes, [{"number_route": 1}] * 2)       # arm numbers on the shoulder tops
        self.assertEqual({t["member"] for t in self.menu_doc["targets"]},
                         {"unif_h13_0", "unif_a13_0", "helm_h13_0", "helm_a13_0", "mini_h13_0", "mini_a13_0"})

    def test_new_colours_land_on_the_club_red_through_the_measured_response(self):
        drawn = lambda c: [max(0, min(255, v * 102 // 100 - 19)) for v in hx(c)]
        old, new = drawn("#E31837"), drawn("#E4282E")
        self.assertGreater(old[2] - old[1], 25)                   # the b775 red drew raspberry: blue far over green
        self.assertLessEqual(abs(new[2] - new[1]), 8)             # the club photos: green and blue about equal
        spec = json.loads((ROOT / "data/nfl2k5_teams_2026/KC.json").read_text())
        self.assertEqual((spec["albedo"]["red"], spec["albedo"]["gold"]), ("#E4282E", "#F7C542"))
        for side in ("home", "away"):
            self.assertEqual(sorted(spec["kits"][side]["digits"]["glyph_shapes"]), list("0123456789"))

    def test_chiefs_digit_and_nameplate_rows(self):
        rows = [r for r in self.glyph_doc["textures"] if r["selector"] in ("13H0", "13A0")]
        digits = [r for r in rows if r["kind"] == "digit_png"]
        self.assertEqual(len(digits), 40)
        for row in digits:
            self.assertEqual(sha((glyphs.ART / row["png"]).read_bytes()), row["png_sha256"])
        names = {r["selector"]: (r["fill"], r["outline"]) for r in rows if r["kind"] == "names_retint"}
        self.assertEqual(names, {"13H0": ("#FFFFFF", "#F7C542"), "13A0": ("#E4282E", "#F7C542")})

    def test_font_shapes_fit_their_boxes(self):
        import ku1_font
        for digit, shape in ku1_font.shapes().items():
            for contour in shape["contours"] + shape["holes"]:
                for x, y in contour:
                    self.assertTrue(0 <= x <= shape["width"] + 1e-6 and 0 <= y <= shape["height"] + 1e-6, digit)

    def test_packaging_and_build_order(self):
        allow = (ROOT / "packaging/release-allowlist.txt").read_text().split("\n")
        for path in ("mod_editor/core/nfl2k5_menu_chiefs_2026.py", "data/nfl2k5_kit_fixes_2026_ku1.json",
                     "data/nfl2k5_menu_chiefs_2026.json",
                     *("data/nfl2k5_glyph_fixes_2026/" + r["png"] for r in self.glyph_doc["textures"]
                       if r.get("png", "").startswith("KC_"))):
            self.assertIn(path, allow)
        text = (ROOT / "mod_editor/core/mod_build.py").read_text()
        hem = text.index('_core_module("nfl2k5_pants_hem_2026")')
        self.assertLess(hem, text.index("kit_fixes.apply_chiefs(target)"))
        self.assertLess(text.index("kit_fixes.apply_chiefs(target)"), text.index('_core_module("nfl2k5_moment_kits")'))
        self.assertLess(text.index('_core_module("nfl2k5_menu_helmet_w2026")'),
                        text.index('_core_module("nfl2k5_menu_chiefs_2026")'))
        self.assertIn('"mod_editor.core.nfl2k5_menu_chiefs_2026"',
                      (ROOT / "packaging/check_2k5_mod_studio_runtime.py").read_text())

    def test_shipped_files_carry_no_private_paths(self):
        for path in ("data/nfl2k5_kit_fixes_2026_ku1.json", "data/nfl2k5_menu_chiefs_2026.json",
                     "mod_editor/core/nfl2k5_menu_chiefs_2026.py", "data/nfl2k5_teams_2026/KC.json"):
            text = (ROOT / path).read_text()
            self.assertNotIn("/home/noah", text)
            self.assertNotIn("/media/noah", text)

    def test_not_an_image_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            junk = Path(tmp) / "junk.iso"
            junk.write_bytes(b"not a disc")
            self.assertEqual(fixes.apply_chiefs(junk)["state"], "other_image")
            self.assertEqual(menu.apply_to_image(junk)["state"], "other_image")
            self.assertEqual(junk.read_bytes(), b"not a disc")


@unittest.skipUnless(B775.exists() and RETAIL.exists(), "the b775 and retail discs are not available")
class RealBytes(unittest.TestCase):
    """Every pinned row reproduces from the b775 disc's own Chiefs packages (read only)."""

    @classmethod
    def setUpClass(cls):
        from test_b776_fn2 import _read_kits
        cls.raws = _read_kits(B775, {"13H0", "13A0"})
        cls.retail = _read_kits(RETAIL, {"13H0", "13A0"})

    def test_kit_rows_compile_to_their_pins_and_replay_to_nothing(self):
        doc = fixes.chiefs()
        for sel in ("13H0", "13A0"):
            raw = bytearray(self.raws[sel])
            replacements, receipt = fixes.compile_resource(sel, bytes(raw), strict=True, document=doc)
            self.assertEqual(len(replacements), 8)
            owned = np.zeros(len(raw), bool)
            for offset, data in replacements:
                raw[offset:offset + len(data)] = data
                owned[offset:offset + len(data)] = True
            diff = np.frombuffer(bytes(raw), np.uint8) != np.frombuffer(self.raws[sel], np.uint8)
            self.assertEqual(int(diff[~owned].sum()), 0)
            again, receipt2 = fixes.compile_resource(sel, bytes(raw), strict=True, document=doc)
            self.assertEqual((again, receipt2["state"]), ([], "applied"))

    def test_glyph_rows_compile_to_their_pins(self):
        doc = glyphs.spec()
        for sel in ("13H0", "13A0"):
            replacements, receipt = glyphs.compile_resource(sel, self.raws[sel], strict=True, document=doc,
                                                            retail_kits=self.retail)
            self.assertEqual(len(replacements), 21)              # 20 digits and the nameplate strip

    def test_the_new_jersey_red_is_the_flat_cloth_colour(self):
        from nfl_txtr import parse_chunks
        doc = fixes.chiefs()
        replacements, _ = fixes.compile_resource("13H0", self.raws["13H0"], strict=True, document=doc)
        span = dict(replacements)[[r for r in doc["textures"] if r["selector"] == "13H0" and r["chunk"] == 1][0]["offset"]]
        chunk, decoded, textures = fixes.native_textures(span, "tset")
        planes = fixes.read_planes(decoded, chunk, textures[0])
        rgba = fixes.read_palette(decoded, chunk, textures[0])[planes[0]]
        colours, counts = np.unique(rgba[..., :3].reshape(-1, 3), axis=0, return_counts=True)
        self.assertEqual(colours[counts.argmax()].tolist(), list(hx("#E4282E")))


if __name__ == "__main__":
    unittest.main()
