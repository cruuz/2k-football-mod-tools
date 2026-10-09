"""Job u3a (beta 77): the rule kinds, marks and spec path added to the alternate pipeline, the committed recipes of
ARI, ATL, BAL, BUF, CAR, CHI and CIN, and the u3a repair's key discipline.

Model tests use tiny synthetic textures; nothing reads a disc except the optional roster-pair test (skipped when the
retail extraction is not present)."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "tools/b77"), str(REPO / "tools/b765")]

import u3a_repair as ur  # noqa: E402
import u3s_alternates as ua  # noqa: E402
import u3s_repair as base  # noqa: E402

RECIPES = json.loads((REPO / "data/nfl2k5_uniform_alternates_2026.json").read_text())["alternates"]
SLOTS = json.loads((REPO / "data/nfl2k5_uniform_slots_2026.json").read_text())["teams"]
BUILT = ("ARI:6", "ARI:7", "ATL:9", "BAL:2", "BAL:3", "BUF:3", "BUF:8", "BUF:9", "CAR:2", "CHI:4", "CIN:6")


def px(*colours):
    a = np.ones((1, len(colours), 4), np.float32)
    a[0, :, :3] = np.array(colours, np.float32) / 255.0
    return a


def ints(a):
    return (a[0, :, :3] * 255 + 0.5).astype(int)


class RuleKindTests(unittest.TestCase):
    def test_greys_keep_the_texels_own_light_and_leave_marks_alone(self) -> None:
        src = px((255, 255, 255), (128, 128, 140), (0, 0, 0), (200, 16, 46))
        out, _ = ua.recolour(src, {"kind": "greys", "to": "#C8C8C8", "range": [0.5, 1.0], "saturation": 0.3,
                                   "min_luma": 0.25})
        got = ints(out)
        np.testing.assert_allclose(got[0], (200, 200, 200), atol=2)          # white takes the target
        self.assertTrue(100 < got[1][0] < 190 and got[1][0] < got[0][0])     # a fold stays darker
        np.testing.assert_array_equal(got[2], (0, 0, 0))                     # a dark stripe stays (min_luma)
        np.testing.assert_array_equal(got[3], (200, 16, 46))                 # a coloured mark stays

    def test_darks_take_the_shell_colour_and_logos_stay(self) -> None:
        src = px((0, 0, 0), (4, 4, 4), (48, 24, 104), (232, 232, 232))
        got = ints(ua.recolour(src, {"kind": "darks", "to": "#3A2380", "threshold": 0.12})[0])
        np.testing.assert_allclose(got[0], (58, 35, 128), atol=1)
        np.testing.assert_allclose(got[1], (58, 35, 128), atol=3)
        np.testing.assert_array_equal(got[2], (48, 24, 104))
        np.testing.assert_array_equal(got[3], (232, 232, 232))

    def test_hue_families_move_to_the_target_keeping_brightness(self) -> None:
        src = px((48, 24, 104), (24, 12, 52), (255, 255, 255), (200, 16, 46))
        got = ints(ua.recolour(src, {"kind": "hue", "hue": "purple", "to": "#B8962E", "reference": 0.42})[0])
        self.assertGreater(got[0][0], got[1][0])                             # the brighter stripe stays brighter
        self.assertTrue(abs(got[0][0] - 0xB8) < 20 and got[0][2] < got[0][0])
        np.testing.assert_array_equal(got[2], (255, 255, 255))
        np.testing.assert_array_equal(got[3], (200, 16, 46))
        blue = px((0, 16, 114), (255, 255, 255))
        got = ints(ua.recolour(blue, {"kind": "hue", "hue": "blue", "to": "#D4112B", "reference": 0.45})[0])
        self.assertGreater(got[0][0], got[0][2])                             # blue became red
        np.testing.assert_array_equal(got[1], (255, 255, 255))
        with self.assertRaises(SystemExit):
            ua.recolour(blue, {"kind": "hue", "hue": "green", "to": "#FFFFFF"})

    def test_tone_on_tone_flattens_the_background_and_mutes_the_logo(self) -> None:
        src = px((46, 22, 102), (226, 175, 14), (255, 255, 255))
        got = ints(ua.recolour(src, {"kind": "tone", "from_bg": "#2E1666", "to_bg": "#0E0E10", "tint": "#7A5CC8",
                                    "distance": 0.14})[0])
        np.testing.assert_allclose(got[0], (14, 14, 16), atol=1)
        for logo in (got[1], got[2]):
            self.assertTrue(logo[2] > logo[1])                               # monochrome purple, no gold or white left

    def test_speckle_is_deterministic_and_only_marks_the_fabric(self) -> None:
        rule = {"kind": "speckle", "base": "#E9DFC9", "tint": "#A67550", "density": 0.05, "strength": 0.5,
                "distance": 0.12, "seed": "t"}
        fabric = np.ones((32, 32, 4), np.float32)
        fabric[..., :3] = np.array((233, 223, 201), np.float32) / 255.0
        a, _ = ua.recolour(fabric, rule)
        b, _ = ua.recolour(fabric, rule)
        np.testing.assert_array_equal(a, b)
        self.assertGreater(float(np.abs(a - fabric).max()), 0.05)
        red = fabric.copy()
        red[..., :3] = np.array((181, 32, 46), np.float32) / 255.0
        c, _ = ua.recolour(red, rule)
        np.testing.assert_allclose(c[..., :3], red[..., :3], atol=1e-6)      # the red numerals are never speckled

    def test_a_rule_can_name_one_kit_and_a_box(self) -> None:
        src = np.ones((4, 4, 4), np.float32)
        src[..., :3] = np.array((255, 80, 20), np.float32) / 255.0
        out, changed = ua.recolour(src, {"from": ["#FF5014", "#000000"], "to": ["#FFFFFF", "#000000"],
                                         "tolerance": 0.1, "box": [0, 0, 2, 4]})
        self.assertEqual(changed, 8)


class SpecHelpersTests(unittest.TestCase):
    def test_deep_merge_replaces_leaves_and_keeps_siblings(self) -> None:
        a = {"x": {"y": 1, "z": 2}, "list": [1]}
        b = ua.deep_merge(a, {"x": {"y": 9}, "list": [2, 3], "new": None})
        self.assertEqual(b, {"x": {"y": 9, "z": 2}, "list": [2, 3], "new": None})
        self.assertEqual(a["x"]["y"], 1)

    def test_derived_marks_are_made_from_team_masks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mask = Image.new("RGBA", (10, 10), (255, 255, 255, 0))
            mask.paste((255, 255, 255, 255), (3, 3, 7, 7))
            mask.save(root / "m.png")
            ua.make_mark(root / "m.png", root / "o.png", {"fill": "#DCE6F2", "outline": {"colour": "#0B3A9E", "px": 1}})
            out = np.asarray(Image.open(root / "o.png"))
            self.assertEqual(tuple(out[7, 7, :3]), (0xDC, 0xE6, 0xF2))       # the silhouette (offset by the pad)
            self.assertTrue((out[..., 3] > 0).sum() > 16)                    # grown by the border
            border = [tuple(p[:3]) for row in out for p in row if p[3] > 0 and tuple(p[:3]) == (0x0B, 0x3A, 0x9E)]
            self.assertTrue(border)
            Image.new("RGBA", (10, 10), (255, 255, 255, 0)).save(root / "w.png")
            w = Image.open(root / "w.png")
            w.paste((255, 255, 255, 255), (0, 0, 10, 4))
            w.save(root / "w.png")
            ua.make_mark(root / "m.png", root / "l.png", {"layers": [{"from": "w.png", "fill": "#FFFFFF"},
                                                                    {"from": "m.png", "fill": "#0D1A32"}]})
            layered = np.asarray(Image.open(root / "l.png"))
            self.assertEqual(tuple(layered[0, 0, :3]), (255, 255, 255))
            self.assertEqual(tuple(layered[5, 5, :3]), (0x0D, 0x1A, 0x32))


@unittest.skipUnless(ua.UNIFORM_MARKS.is_file(), "the pinned NFL shield and swoosh masters are not present")
class MarksTests(unittest.TestCase):
    """The 'modernize' step on synthetic retail-size textures: marks appear where the 2026 jerseys carry them."""

    @classmethod
    def setUpClass(cls) -> None:
        ua.art.use_uniform_marks(ua.UNIFORM_MARKS)

    def flat(self, w, h, colour):
        a = np.ones((h, w, 4), np.float32)
        a[..., :3] = np.array(colour, np.float32) / 255.0
        return a

    def test_torso_collar_shield_pants_swoosh_and_sleeve_swooshes(self) -> None:
        torso = ua.apply_marks("torso", self.flat(512, 256, (16, 16, 24)), {"collar_shield": True})
        self.assertEqual(torso.shape, (256, 512, 4))
        x, y = int(ua.art.TORSO_V_TIP[0]), int(ua.art.TORSO_V_TIP[1]) + 6
        self.assertGreater(float(np.abs(torso[y - 3:y + 4, x - 3:x + 4, :3] - 16 / 255).max()), 0.3)   # the shield
        self.assertLess(float(np.abs(torso[200:250, 20:60, :3] - np.array((16, 16, 24)) / 255).max()), 0.02)
        pants = ua.apply_marks("pants", self.flat(512, 256, (250, 250, 250)), {"swoosh": "#000000", "hip_shield": True})
        sw = ua.art.PANTS_SWOOSH
        cx, cy = int(sw["centre"][0]), int(sw["centre"][1])
        self.assertLess(float(pants[cy - 3:cy + 4, cx - 9:cx + 10, :3].min()), 0.3)                  # black swoosh
        sleeve = ua.apply_marks("sleeve", self.flat(128, 128, (16, 16, 24)), {"swoosh": "#FFFFFF"})
        self.assertGreater(float(sleeve[..., :3].max()), 0.9)


class RecipeTests(unittest.TestCase):
    def test_every_built_recipe_matches_its_slot_decision(self) -> None:
        for key in BUILT:
            recipe = RECIPES[key]
            team, style = key.split(":")
            self.assertEqual((recipe["team"], recipe["style"]), (team, int(style)))
            row = next(a for a in SLOTS[team]["assignments"] if a["style"] == int(style))
            self.assertEqual(recipe["set"], row["set"], key)
            self.assertIn(recipe["build_type"], ua.BUILD_TYPES)
            self.assertTrue(recipe["sources"], key)
            self.assertEqual(sorted(recipe["kits"]), ["A", "H"], key)
            for side, kit in recipe["kits"].items():
                self.assertTrue(kit["donor"].startswith(recipe["code"]), key)

    def test_the_labels_follow_the_cycle_order(self) -> None:
        for team in ("ARI", "BAL", "BUF", "CHI", "CIN", "ATL", "CAR"):
            built = sorted((RECIPES[k]["style"], RECIPES[k]["label"]) for k in BUILT if k.startswith(team + ":"))
            numbers = [label[1] for _, label in built]
            self.assertEqual(numbers, sorted(numbers), team)

    def test_modernize_recipes_name_their_marks_and_spec_recipes_a_spec(self) -> None:
        for key in BUILT:
            recipe = RECIPES[key]
            if recipe["build_type"] == "modernize":
                self.assertTrue({"torso", "sleeve", "pants"} <= set(recipe["marks"]), key)
            if recipe["build_type"] == "spec":
                self.assertTrue(recipe["spec"]["kits"].keys() == {"H", "A"}, key)

    def test_the_repair_only_takes_this_jobs_alternates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(json.dumps({"schema": base.MANIFEST_SCHEMA, "key": "CIN:5", "resources": {}}))
            with self.assertRaises(ValueError):
                ur.manifest_keys([path])                                     # CIN 5 is u3s's
            path.write_text(json.dumps({"schema": base.MANIFEST_SCHEMA, "key": "CIN:6", "resources": {}}))
            self.assertEqual(ur.manifest_keys([path]), ["CIN:6"])
            with self.assertRaises(ValueError):
                ur.manifest_keys([path, path])                               # twice
        self.assertTrue(set(ur.U3A_KEYS) >= set(BUILT))

    def test_every_manifest_of_a_built_alternate_is_accepted_by_the_u3s_checker(self) -> None:
        recipes = {"alternates": RECIPES}
        with tempfile.TemporaryDirectory() as tmp:
            for key in BUILT:
                r = RECIPES[key]
                names = {f"{r['code']}{side}{r['style']}.IFF": [] for side in r["kits"]}
                names["outer:3102"] = []
                path = Path(tmp) / f"{key.replace(':', '_')}.json"
                path.write_text(json.dumps({"schema": base.MANIFEST_SCHEMA, "key": key, "resources": names}))
                self.assertEqual(len(base.load_manifests([path], recipes, [key])), 1)


RETAIL_PACKS = Path(__import__("os").environ.get("NFL2K5_RETAIL_EXTRACTION",
                                                 "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "vc_53450030"


@unittest.skipUnless((RETAIL_PACKS / "0").is_file(), "the retail extraction is not present")
class RosterPairTests(unittest.TestCase):
    """The year pairs of this job's slots on the retail main roster: found by asset code, checked, idempotent."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core import nfl2k5_historic_styles as hs
        with hs.Source(RETAIL_PACKS) as src:
            cls.roster = src.get(identity=base.ROSTER_ID)

    def test_each_slots_retail_pair_is_what_the_recipe_expects_and_the_orphan_reads_zero(self) -> None:
        for key in BUILT:
            r = RECIPES[key]
            p = base.roster_patch(self.roster, r["code"], r["style"], tuple(r["retail_pair"]), tuple(r["label"]))
            self.assertEqual(struct.unpack_from("<HH", self.roster, p["offset"]), tuple(r["retail_pair"]), key)
        self.assertEqual(RECIPES["CIN:6"]["retail_pair"], [0, 0])            # the orphan kit becomes selectable

    def test_all_pairs_apply_once_and_a_second_pass_is_a_no_op(self) -> None:
        patches = []
        for key in BUILT:
            r = RECIPES[key]
            p = base.roster_patch(self.roster, r["code"], r["style"], tuple(r["retail_pair"]), tuple(r["label"]))
            patches.append(dict(p, resource="ROST", resource_offset=p["offset"]))
        data, receipt = base.apply_patches(self.roster, patches)
        self.assertTrue(receipt["outside_scope_identical"])
        again, second = base.apply_patches(data, patches)
        self.assertEqual(again, data)
        self.assertTrue(all(s["already_applied"] for s in second["spans"]))


if __name__ == "__main__":
    unittest.main()
