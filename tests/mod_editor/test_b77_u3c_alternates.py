"""Job u3c (beta 77): the Jaguars, Chargers, Raiders and Dolphins 2026 alternates (recipes, painters, repair keys).

Synthetic data only; nothing reads a disc."""

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

import u3c_paint as paint  # noqa: E402
import u3c_repair as cr  # noqa: E402
import u3s_alternates as ua  # noqa: E402
from mod_editor.core import nfl2k5_uniform_slots as us  # noqa: E402

RECIPES = json.loads((REPO / "data/nfl2k5_uniform_alternates_2026.json").read_text(encoding="utf-8"))["alternates"]
DECISIONS = json.loads((REPO / "data/nfl2k5_uniform_slots_2026.json").read_text(encoding="utf-8"))
GOLD, WHITE, POWDER, GREY = (255, 194, 14), (255, 255, 255), (0, 128, 198), (220, 220, 220)

# key: (label number, label text the game prints, retail pair)
EXPECTED = {
    "JAX:5": (1, "2026  Alternate 1", (2003, 3)), "JAX:6": (2, "2026  Alternate 2", (2003, 4)),
    "LAC:9": (1, "2026  Alternate 1", (2003, 1)), "LAC:10": (2, "2026  Alternate 2", (2003, 2)),
    "LAC:11": (3, "2026  Alternate 3", (2004, 1)), "LV:4": (1, "2026  Alternate 1", (2004, 1)),
    "MIA:10": (1, "2026  Alternate 1", (2004, 3)),
}


def px(colours) -> np.ndarray:
    a = np.ones((1, len(colours), 4), np.float32)
    a[0, :, :3] = np.array(colours, np.float32) / 255.0
    return a


def font_available(kind: str) -> bool:
    return any(Path(p).is_file() for p in paint.FONTS[kind])


class RecipeTests(unittest.TestCase):
    def test_the_seven_recipes_are_complete_and_label_in_cycle_order(self) -> None:
        self.assertEqual(sorted(cr.KEYS), sorted(EXPECTED))
        for key, (number, text, retail) in EXPECTED.items():
            recipe = RECIPES[key]
            self.assertEqual(recipe["label"], [us.ALTERNATE_YEAR, number], key)
            self.assertEqual(us.style_label(recipe["style"], *recipe["label"]), text, key)
            self.assertEqual(tuple(recipe["retail_pair"]), retail, key)
            self.assertTrue(recipe["sources"] and all(s["url"].startswith("https://") and s["supports"]
                                                      for s in recipe["sources"]), key)
            self.assertEqual(sorted(recipe["kits"]), ["A", "H"], key)
            if recipe.get("paint"):
                self.assertIn(recipe["paint"], paint.PAINTERS, key)
            if recipe["build_type"] == "new" or recipe.get("confidence"):
                self.assertTrue(recipe.get("estimates") or recipe.get("confidence"), key)   # estimates are marked

    def test_the_plan_marks_them_built_and_the_cycle_numbers_are_consecutive(self) -> None:
        by_team: dict[str, list[tuple[int, int]]] = {}
        for key in EXPECTED:
            team, style = key.split(":")
            planned = {a["style"]: a for a in DECISIONS["teams"][team]["assignments"]}
            self.assertEqual(planned[int(style)]["status"], "built", key)
            by_team.setdefault(team, []).append((int(style), EXPECTED[key][0]))
        for team, rows in by_team.items():
            rows.sort()
            self.assertEqual([n for _s, n in rows], list(range(1, len(rows) + 1)), team)   # no "Alternate 2" alone

    def test_kc_and_the_rams_are_not_this_jobs(self) -> None:
        for key in RECIPES:
            self.assertFalse(key.startswith(("KC:", "LAR:")) and key in cr.KEYS, key)


class ColourRuleTests(unittest.TestCase):
    def test_a_colour_swap_moves_every_blend_and_keeps_listed_identities(self) -> None:
        rule = {"from": ["#0080C6", "#FFC20E", "#FFFFFF", "#DCDCDC"], "to": ["#12295A", "#FFFFFF", "#FFC20E", "#DCDCDC"],
                "moved": None, "tolerance": 0.1}
        src = px([POWDER, GOLD, WHITE, GREY, (10, 200, 10)])
        out, _ = ua.recolour(src, rule)
        got = (out[0, :, :3] * 255 + 0.5).astype(int)
        np.testing.assert_allclose(got[0], (0x12, 0x29, 0x5A), atol=3)    # the base
        np.testing.assert_allclose(got[1], WHITE, atol=3)                   # gold fill -> white
        np.testing.assert_allclose(got[2], GOLD, atol=3)                    # white edge -> gold
        np.testing.assert_array_equal(got[3], GREY)                         # the neck cut-out stays
        np.testing.assert_array_equal(got[4], (10, 200, 10))                # not a blend of the sources
        # without ``moved: null`` only texels holding the first colour move (the original rule)
        out, _ = ua.recolour(src, dict(rule, moved=0))
        np.testing.assert_allclose((out[0, 1, :3] * 255 + 0.5).astype(int), GOLD, atol=2)

    def test_include_boxes_limit_a_rule(self) -> None:
        src = np.ones((4, 8, 4), np.float32)
        src[..., :3] = np.array(WHITE, np.float32) / 255.0
        rule = {"from": ["#FFFFFF", "#000000"], "to": ["#000000", "#000000"], "moved": None, "tolerance": 0.1,
                "include": [[1, 0, 3, 4], [6, 0, 8, 4]]}
        out, changed = ua.recolour(src, rule)
        self.assertEqual(changed, 16)
        self.assertEqual(int(out[0, 0, 0] * 255), 255)
        self.assertEqual(int(out[0, 1, 0] * 255), 0)
        self.assertEqual(int(out[0, 4, 0] * 255), 255)


class TakeTests(unittest.TestCase):
    def test_a_component_can_come_from_another_kit_by_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = root / "export"
            files = ["pants.png", "digit_helmet_0.png", "digit_helmet_1.png", "glove01.png"]
            doc = {"kits": {}}
            for sel, colour in (("24H0", (255, 194, 14)), ("24A0", (255, 255, 255)), ("24H10", (1, 2, 3)),
                                ("24A10", (4, 5, 6))):
                chunk = {"pants.png": 2, "digit_helmet_0.png": 23, "digit_helmet_1.png": 24, "glove01.png": 6}
                doc["kits"][sel] = {"outer_index": 1, "unif": {"facemask": "FF000000", "turtleneck": "FF000000"},
                                    "assets": [{"file": f, "name": f[:-4], "kind": "TSET" if chunk[f] in (2, 6) else "TXTR",
                                                "chunk": chunk[f], "tset_index": 0, "size": [8, 8]} for f in files]}
                for f in files:
                    p = exp / "uniforms" / sel / f
                    p.parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGBA", (8, 8), colour + (255,)).save(p)
            (exp / "export.json").write_text(json.dumps(doc))
            recipe = {"team": "LAC", "code": "24", "style": 10, "set": "x", "build_type": "derive",
                      "kits": {"H": {"donor": "24H0"}, "A": {"donor": "24A0", "take": {"24H0": ["pants", "digit_helmet_*"]}}}}
            ua.author(recipe, exp, root / "art")
            got = np.asarray(Image.open(root / "art/24A10/pants.png"))[0, 0, :3]
            np.testing.assert_array_equal(got, (255, 194, 14))                       # taken from the home kit
            np.testing.assert_array_equal(np.asarray(Image.open(root / "art/24A10/digit_helmet_1.png"))[0, 0, :3],
                                          (255, 194, 14))
            np.testing.assert_array_equal(np.asarray(Image.open(root / "art/24A10/glove01.png"))[0, 0, :3],
                                          (255, 255, 255))                           # everything else: the road kit


class PaintTests(unittest.TestCase):
    def donor_digit(self) -> np.ndarray:
        a = np.zeros((64, 64, 4), np.float32)
        a[2:62, 14:50, :3] = 0.016
        a[2:62, 14:50, 3] = 1.0
        a[10:54, 22:42, :3] = np.array((0xCC, 0xC4, 0xC4), np.float32) / 255.0
        return a

    def test_the_raiders_numerals_are_hard_edged_silver_with_a_two_pixel_black_outline(self) -> None:
        out = paint.raiders_throwback("digit_jersey_3", self.donor_digit(), {})
        self.assertEqual(set(np.unique(out[..., 3]).tolist()), {0.0, 1.0})
        self.assertEqual((out[..., 3] > 0).sum(), 60 * 36)
        silver = (np.abs(out[..., 0] - 0xCC / 255) < 0.01) & (out[..., 3] > 0)
        self.assertEqual(int(silver.sum()), 56 * 32)                  # 2 px of black all round
        np.testing.assert_allclose(out[2, 14, :3], np.array((4, 4, 4)) / 255, atol=0.01)
        unchanged = paint.raiders_throwback("torso", self.donor_digit(), {})
        self.assertTrue(np.array_equal(unchanged, self.donor_digit()))

    @unittest.skipUnless(font_available("serif_bold"), "no serif font on this machine")
    def test_a_bold_city_numeral_has_black_fill_a_gold_edge_and_a_teal_shadow(self) -> None:
        donor = np.zeros((64, 64, 4), np.float32)
        donor[1:63, 14:50, 3] = 1.0
        out = paint.bold_city("digit_jersey_6", donor, {})
        self.assertEqual(out.shape, (64, 64, 4))
        again = paint.bold_city("digit_jersey_6", donor, {})
        np.testing.assert_array_equal(out, again)                      # deterministic
        visible = out[..., 3] > 0.9
        rgb = (out[..., :3] * 255).astype(int)
        near = lambda c: int((np.abs(rgb - np.array(c)).max(axis=2) < 40)[visible].sum())     # noqa: E731
        self.assertGreater(near((0x14, 0x14, 0x14)), 100)
        self.assertGreater(near((0xB5, 0x9A, 0x55)), 20)
        self.assertGreater(near((0x03, 0x7C, 0x8C)), 20)
        ys, xs = np.nonzero(out[..., 3] > 0.05)
        self.assertTrue(8 <= xs.min() and xs.max() <= 56 and 1 <= ys.min() and ys.max() <= 62)

    def test_the_bold_city_pants_become_black_with_a_teal_stripe_between_gold_bars(self) -> None:
        donor = np.ones((256, 512, 4), np.float32)
        donor[:16, :, :3] = 0.016                                      # the donor's waistband stays
        out = paint.bold_city("pants", donor, {})
        self.assertLess(out[100, 60, :3].max(), 0.2)                   # the fabric
        np.testing.assert_allclose(out[100, 142, :3], paint.hexf(paint.BC_TEAL), atol=0.02)
        np.testing.assert_allclose(out[100, 131, :3], paint.hexf(paint.BC_GOLD), atol=0.02)
        np.testing.assert_allclose(out[100, 369, :3], paint.hexf(paint.BC_TEAL), atol=0.02)
        self.assertLess(out[5, 300, :3].max(), 0.05)                   # dashes untouched

    def test_the_helmet_shell_turns_teal_and_a_logo_outline_stays_black(self) -> None:
        h = np.zeros((64, 64, 4), np.float32)
        h[..., 3] = 1.0
        h[..., :3] = 0.016
        h[20:30, 20:30, :3] = np.array((0.9, 0.7, 0.2), np.float32)    # a gold logo with a black outline around it
        out = paint.shell_teal(h, np.s_[:, :])
        np.testing.assert_allclose(out[2, 2, :3], paint.hexf(paint.BC_SHELL_TEAL) * 0.9, atol=0.08)
        self.assertLess(out[18, 25, :3].max(), 0.1)                    # within 3 px of the logo: stays black
        np.testing.assert_allclose(out[25, 25, :3], h[25, 25, :3])

    @unittest.skipUnless(font_available("sans_bold"), "no sans font on this machine")
    def test_the_dolphins_torso_gets_an_orange_collar_and_chest_wordmark(self) -> None:
        donor = np.ones((256, 512, 4), np.float32)
        donor[..., :3] = np.array(paint.hexf(paint.MIA_DARK))
        out = paint.rivalries_mia("torso", donor, {})
        orange = (np.abs(out[..., :3] - paint.hexf(paint.MIA_ORANGE)).max(axis=2) < 0.12)
        self.assertGreater(int(orange[:72, 130:200].sum()), 40)        # the V-neck trim
        self.assertGreater(int(orange[88:104, 130:200].sum()), 20)     # MIAMI on the chest
        self.assertEqual(int(orange[150:, :].sum()), 0)

    def test_the_sleeve_keeps_its_swooshes_and_loses_the_logos(self) -> None:
        donor = np.ones((128, 128, 4), np.float32)
        donor[..., :3] = np.array(paint.hexf(paint.MIA_DARK))
        donor[30:40, 50:60, :3] = np.array((0.95, 0.36, 0.11), np.float32)       # an orange logo ring
        donor[8:12, 70:80, :3] = np.array((0.95, 0.36, 0.11), np.float32)        # the swoosh above the logo
        out = paint.rivalries_mia("sleeve", donor, {})
        np.testing.assert_allclose(out[34, 54, :3], paint.hexf(paint.MIA_DARK))
        np.testing.assert_allclose(out[10, 75, :3], donor[10, 75, :3])


class RepairWrapperTests(unittest.TestCase):
    def test_manifest_layout_and_key_set(self) -> None:
        compiled = Path("/x/compiled")
        self.assertEqual(cr.manifest_path(compiled, "MIA:10"), compiled / "mia10/native_manifest.json")
        self.assertEqual(cr.manifest_path(compiled, "LAC:9"), compiled / "lac9/native_manifest.json")
        self.assertEqual(len(cr.KEYS), 7)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                cr.main(["--input", tmp + "/in", "--output", tmp + "/out", "--compiled", tmp, "--receipt", tmp + "/r.json",
                         "--keys", "KC:7"])

    def test_every_label_the_repair_writes_reads_as_planned(self) -> None:
        for key, (number, text, retail) in EXPECTED.items():
            recipe = RECIPES[key]
            self.assertEqual(us.style_label(recipe["style"], *retail).split()[0].isdigit(), True)
            self.assertEqual(us.style_label(recipe["style"], *recipe["label"]), text)


if __name__ == "__main__":
    unittest.main()
