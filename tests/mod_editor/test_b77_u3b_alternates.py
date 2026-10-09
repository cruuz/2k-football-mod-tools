"""Job u3b (beta 77): the 2026 alternate authoring ops, the recipes for CLE DAL DEN DET GB HOU IND and the repair wrapper.

Model tests build tiny synthetic exports; nothing reads a disc."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "tools/b77"), str(REPO / "tools/b765")]

import u3b_alternates as ub  # noqa: E402
import u3b_repair as ur  # noqa: E402
from mod_editor.core import nfl2k5_uniform_slots as us  # noqa: E402

RECIPES = REPO / "data/nfl2k5_uniform_alternates_2026_u3b.json"
DECISIONS = REPO / "data/nfl2k5_uniform_slots_2026.json"
MINE = {"CLE:3", "CLE:4", "DAL:7", "DAL:9", "DEN:5", "DEN:6", "DET:2", "DET:9", "GB:5", "GB:6", "HOU:2", "IND:3",
        "IND:4"}


# the v0.5 labels of the slots (reports/u3s_SLOT_PLAN.json, label_before) and what the repair writes (label_after)
LABEL_BEFORE = {"CLE:3": "2003  Alternate 1", "CLE:4": "2003  Alternate 2", "DAL:7": "1994  Alternate 1",
                "DAL:9": "2002  Alternate 1", "DEN:5": "2003  Alternate 1", "DEN:6": "2003  Alternate 2",
                "DET:2": "1999 Uniform", "DET:9": "2004  Alternate 2", "GB:5": "2003  Alternate 1",
                "GB:6": "2004  Alternate 1", "HOU:2": "2004  Alternate 1", "IND:3": "1987 Uniform",
                "IND:4": "1982 Uniform"}
LABEL_AFTER = {"CLE:3": "2026  Alternate 1", "CLE:4": "2026  Alternate 2", "DAL:7": "2026  Alternate 1",
               "DAL:9": "2026  Alternate 2", "DEN:5": "2026  Alternate 1", "DEN:6": "2026  Alternate 2",
               "DET:2": "2026  Alternate 1", "DET:9": "2026  Alternate 2", "GB:5": "2026  Alternate 1",
               "GB:6": "2026  Alternate 2", "HOU:2": "2026  Alternate 1", "IND:3": "2026  Alternate 2",
               "IND:4": "2026  Alternate 3"}


def solid(colours: list[tuple[int, int, int]], alpha: int = 255) -> np.ndarray:
    a = np.ones((1, len(colours), 4), np.float32)
    a[0, :, :3] = np.array(colours, np.float32) / 255.0
    a[0, :, 3] = alpha / 255.0
    return a


def ints(a: np.ndarray) -> np.ndarray:
    return (a[..., :3] * 255 + 0.5).astype(int)


class RemixManyTests(unittest.TestCase):
    ORANGE, WHITE, NAVY = (252, 76, 2), (255, 255, 255), (10, 35, 67)

    def test_every_moved_colour_changes_and_the_first_only_rule_is_gone(self) -> None:
        src = solid([self.ORANGE, self.WHITE, self.NAVY, (0, 200, 0)])
        both = {"op": "remix", "components": ["x"], "from": ["#FC4C02", "#FFFFFF", "#0A2343"],
                "to": ["#0A2343", "#0A2343", "#0A2343"], "tolerance": 0.25, "moved": [0, 1]}
        out, changed = ub.apply_op(src, both)
        got = ints(out)[0]
        np.testing.assert_allclose(got[0], self.NAVY, atol=2)
        np.testing.assert_allclose(got[1], self.NAVY, atol=2)
        np.testing.assert_array_equal(got[3], (0, 200, 0))            # green is no blend of the three
        self.assertEqual(changed, 2)
        first_only, changed = ub.apply_op(src, dict(both, moved=[0]))
        np.testing.assert_array_equal(ints(first_only)[0][1], self.WHITE)    # white stays: not a moved colour
        self.assertEqual(changed, 1)

    def test_swapping_two_colours_in_one_pass(self) -> None:
        src = solid([self.ORANGE, self.NAVY])
        op = {"op": "remix", "components": ["x"], "from": ["#FC4C02", "#0A2343"], "to": ["#0A2343", "#FC4C02"],
              "tolerance": 0.25, "moved": [0, 1]}
        got = ints(ub.apply_op(src, op)[0])[0]
        np.testing.assert_allclose(got[0], self.NAVY, atol=2)
        np.testing.assert_allclose(got[1], self.ORANGE, atol=2)


class GlyphAndShapeTests(unittest.TestCase):
    def test_tint_keeps_alpha_and_the_glyphs_own_shading(self) -> None:
        glyph = np.zeros((4, 4, 4), np.float32)
        glyph[1:3, 1:3] = (0.05, 0.2, 0.6, 1.0)                       # a blue glyph on nothing
        out, _ = ub.apply_op(glyph, {"op": "tint", "components": ["d"], "colour": "#002244"})
        np.testing.assert_allclose(out[1, 1, :3], np.array([0, 0x22, 0x44]) / 255.0, atol=0.01)
        self.assertEqual(float(out[0, 0, 3]), 0.0)
        self.assertEqual(float(out[1, 1, 3]), 1.0)

    def test_outline_grows_the_alpha_and_rings_the_glyph(self) -> None:
        glyph = np.zeros((7, 7, 4), np.float32)
        glyph[2:5, 2:5] = (1, 1, 1, 1)
        out, _ = ub.apply_op(glyph, {"op": "outline", "components": ["d"], "fill": "#FF0000", "line": "#0000FF",
                                      "width": 1})
        self.assertEqual(float(out[3, 3, 3]), 1.0)
        np.testing.assert_allclose(out[3, 3, :3], (1, 0, 0), atol=0.01)       # inside: the fill
        self.assertEqual(float(out[1, 3, 3]), 1.0)                            # one texel out: opaque
        np.testing.assert_allclose(out[1, 3, :3], (0, 0, 1), atol=0.01)       # ... and the ring colour
        self.assertEqual(float(out[0, 0, 3]), 0.0)

    def test_halo_rings_only_the_target_shape(self) -> None:
        img = np.ones((9, 9, 4), np.float32)
        img[..., :3] = 1.0
        img[3:6, 3:6, :3] = np.array([0xDC, 0xDC, 0xDC]) / 255.0
        out, changed = ub.apply_op(img, {"op": "halo", "components": ["t"], "target": "#DCDCDC",
                                          "tolerance": 0.05, "width": 1, "colour": "#000000"})
        self.assertEqual(changed, 12)                                          # the 4-connected ring of a 3x3 shape
        self.assertEqual(float(out[3, 3, 0]), float(img[3, 3, 0]))             # the shape itself is untouched
        np.testing.assert_allclose(out[2, 4, :3], 0.0)

    def test_star_is_five_pointed_and_inside_the_texture(self) -> None:
        cov = ub.star_coverage((32, 32), (16, 16), 12, 0.42, 0.0)
        self.assertGreater(float(cov[16, 16]), 0.99)                           # centre
        self.assertGreater(float(cov[5, 16]), 0.5)                             # the top tip region
        self.assertLess(float(cov[28, 6]), 0.01)                               # outside
        self.assertTrue(0.1 < cov.mean() < 0.4)

    def test_paint_rects_respect_the_mask_and_exclusions(self) -> None:
        img = np.ones((8, 8, 4), np.float32)
        op = {"op": "paint", "components": ["p"], "exclude": [[0, 0, 4, 8]],
              "rects": [{"box": [2, 0, 6, 8], "colour": "#000000"}]}
        out, changed = ub.apply_op(img, op)
        self.assertEqual(changed, 16)                                          # columns 4..5 only
        self.assertEqual(float(out[0, 3, 0]), 1.0)

    def test_protect_small_shapes_keeps_a_star_but_not_the_big_field(self) -> None:
        img = np.zeros((40, 40, 4), np.float32)
        img[..., 3] = 1.0
        img[..., :3] = np.array([0x00, 0x22, 0x44]) / 255.0                   # a big navy field
        img[18:21, 18:21, :3] = (1, 1, 1)                                      # a white island
        # near-white islands are the protected "shape" here: colour = white
        mask = ub.protect_mask(img, {"colour": "#FFFFFF", "tolerance": 0.1, "max_area": 50, "min_area": 4, "grow": 1})
        self.assertEqual(float(mask[19, 19]), 0.0)
        self.assertEqual(float(mask[2, 2]), 1.0)

    def test_unknown_ops_are_refused(self) -> None:
        with self.assertRaises(SystemExit):
            ub.apply_op(np.ones((2, 2, 4), np.float32), {"op": "sparkle", "components": ["x"]})


def save(path: Path, colour, size=(8, 8), alpha=255) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, tuple(colour) + (alpha,)).save(path)


class AuthorTests(unittest.TestCase):
    def build_export(self, root: Path) -> Path:
        exp = root / "export"
        assets = [("torso.png", "TSET", 1, 0), ("sleeve.png", "TSET", 3, 0), ("socks00.png", "TSET", 4, 0),
                  ("digit_jersey_3.png", "TXTR", 16, 0), ("digit_helmet_3.png", "TXTR", 26, 0),
                  ("bump_jersey.png", "TXTR", 45, 0)]
        doc = {"kits": {}}
        for sel, outer in (("30H0", 4180), ("30A0", 4186), ("30H3", 4190), ("30A3", 4191)):
            doc["kits"][sel] = {"outer_index": outer, "unif": {"facemask": "FFFFFEFF", "turtleneck": "FFCE4D16"},
                                "assets": [{"file": f, "name": f[:-4], "kind": k, "chunk": c, "tset_index": i,
                                            "size": [8, 8]} for f, k, c, i in assets]}
            for f, *_ in assets:
                colour = (58, 34, 8) if sel == "30H0" else (255, 255, 255) if sel == "30A0" else (90, 90, 90)
                save(exp / "uniforms" / sel / f, colour)
        save(exp / "uniforms/30A0/sleeve.png", (255, 60, 0))
        (exp / "export.json").write_text(json.dumps(doc))
        return exp

    def test_part_donors_per_kit_socks_and_ops_on_a_synthetic_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = self.build_export(root)
            recipe = {"team": "CLE", "code": "30", "style": 3, "set": "Test", "build_type": "derive",
                      "kits": {"H": {"donor": "30H0", "part_donors": {"sleeve": "30A0"},
                                     "socks": {"colour": "#3A2208"}},
                               "A": {"donor": "30A0", "socks": None}},
                      "unif": {"facemask": "FF2F1C0A"},
                      "blank": ["digit_helmet_*"],
                      "ops": [{"op": "tint", "components": ["digit_jersey_*"], "colour": "#FF3C00"},
                              {"op": "remix", "components": ["torso"], "from": ["#3A2208"], "to": ["#101010"],
                               "tolerance": 0.3}]}
            out = ub.author(recipe, exp, root / "art")
            # the home sleeve came from 30A0 (orange), the road sleeve from its own donor 30A0 too
            sleeve = np.asarray(Image.open(root / "art/30H3/sleeve.png"))
            self.assertEqual(tuple(sleeve[0, 0, :3]), (255, 60, 0))
            # the home torso is recoloured by the op, the road torso (white donor) is not
            torso = np.asarray(Image.open(root / "art/30H3/torso.png")).astype(int)
            self.assertTrue((torso[..., :3] < 30).all())
            self.assertTrue((np.asarray(Image.open(root / "art/30A3/torso.png"))[..., :3] == 255).all())
            # the home socks follow the kit's own colour; the road kit's socks rule is off (donor kept)
            socks = np.asarray(Image.open(root / "art/30H3/socks00.png")).astype(int)
            self.assertTrue(abs(socks[..., 0] - 58).max() < 20)
            road_socks = np.asarray(Image.open(root / "art/30A3/socks00.png"))
            self.assertTrue((road_socks[..., :3] == 255).all())
            # digits tinted, helmet digits blank, relief maps never written
            digit = np.asarray(Image.open(root / "art/30H3/digit_jersey_3.png"))
            self.assertEqual(tuple(digit[0, 0, :3]), (255, 60, 0))
            self.assertEqual(int(np.asarray(Image.open(root / "art/30H3/digit_helmet_3.png"))[..., 3].max()), 0)
            self.assertFalse((root / "art/30H3/bump_jersey.png").exists())
            colour = {e["selector"]: e for e in out["edits"] if e["kind"] == "unif_color"}
            self.assertEqual(sorted(colour), ["30A3", "30H3"])
            self.assertEqual(colour["30H3"]["facemask"], "FF2F1C0A")
            self.assertEqual(colour["30H3"]["turtleneck"], "FFCE4D16")


class RecipeFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.recipes = json.loads(RECIPES.read_text(encoding="utf-8"))
        cls.plan = json.loads(DECISIONS.read_text(encoding="utf-8"))

    def test_every_recipe_matches_a_planned_slot_of_this_job(self) -> None:
        self.assertEqual(self.recipes["schema"], "nfl2k5_uniform_alternates_2026/v1")
        self.assertTrue(set(self.recipes["alternates"]) <= MINE)
        for key, recipe in self.recipes["alternates"].items():
            team, style = key.split(":")
            self.assertEqual((recipe["team"], recipe["style"]), (team, int(style)))
            self.assertEqual(us.FRANCHISES[recipe["code"]], team)
            planned = {a["style"]: a for a in self.plan["teams"][team]["assignments"]}
            self.assertIn(recipe["style"], planned, key)
            a = planned[recipe["style"]]
            self.assertEqual(recipe["set"].split(" (")[0], a["set"].split(" (")[0], key)
            self.assertIn(recipe["build_type"], ("derive", "modernize"), key)
            self.assertEqual(recipe["label"][0], us.ALTERNATE_YEAR)
            self.assertTrue(recipe["sources"], key)
            for side in ("H", "A"):
                self.assertIn(side, recipe["kits"], key)
                self.assertRegex(recipe["kits"][side]["donor"], rf"^{recipe['code']}[HA][0-9]+$")

    def test_retail_pairs_are_the_slots_labels_before_the_change(self) -> None:
        for key, recipe in self.recipes["alternates"].items():
            team = recipe["team"]
            before = us.style_label(recipe["style"], *recipe["retail_pair"])
            self.assertEqual(before, LABEL_BEFORE[key], key)
            self.assertEqual(us.style_label(recipe["style"], *recipe["label"]), LABEL_AFTER[key], key)

    def test_every_op_is_a_known_kind_with_components_and_a_reason(self) -> None:
        kinds = {"remix", "tint", "paint", "star", "outline", "halo"}
        for key, recipe in self.recipes["alternates"].items():
            ops = list(recipe.get("ops", []))
            for kit in recipe["kits"].values():
                ops += kit.get("ops", [])
            self.assertTrue(ops or recipe["build_type"] == "modernize", key)
            for op in ops:
                self.assertIn(op["op"], kinds, key)
                self.assertTrue(op["components"], key)
                self.assertTrue(op.get("why"), (key, op["components"]))
                if op["op"] == "remix" and isinstance(op["from"], list):
                    self.assertEqual(len(op["from"]), len(op["to"]), key)
                    self.assertTrue(all(0 <= m < len(op["from"]) for m in op.get("moved", [0])), key)

    def test_every_estimate_or_tier_two_set_says_so(self) -> None:
        for key in ("CLE:4", "DET:2"):
            self.assertIn("TIER 2", self.recipes["alternates"][key]["estimates"])
        for key, recipe in self.recipes["alternates"].items():
            self.assertTrue(recipe.get("estimates") or key in ("CLE:3", "DAL:7", "DEN:5", "DEN:6"), key)


class RepairWrapperTests(unittest.TestCase):
    def test_the_wrapper_points_the_u3s_repair_at_the_u3b_recipes(self) -> None:
        self.assertEqual(ur.RECIPES, RECIPES)
        self.assertTrue(callable(ur.ur.repair))


if __name__ == "__main__":
    unittest.main()
