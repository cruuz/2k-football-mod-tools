"""Job u3d (beta 77): the 2026 alternates of MIN NE NO NYG NYJ PHI, their recipes, authoring ops and native repair.

Model tests on synthetic inputs and on the committed recipes and plan; nothing reads a disc or the research tree
(the art tool's pinned marks and the 3D body are not needed here)."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "tools/b77"), str(REPO / "tools/b765")]

import u3d_alternates as ud  # noqa: E402
import u3d_repair  # noqa: E402
import u3s_repair as ur  # noqa: E402

RECIPES = json.loads((REPO / "data/nfl2k5_uniform_alternates_2026_u3d.json").read_text())
PLAN = json.loads((REPO / "data/nfl2k5_uniform_slots_2026.json").read_text())
# the slot plan (reports/u3s_SLOT_PLAN.json) for these fifteen: (retail pair before, label pair after)
EXPECTED = {
    "MIN:5": ([2004, 1], [2026, 1]), "MIN:6": ([2004, 2], [2026, 2]), "NE:4": ([1990, 1992], [2026, 1]),
    "NE:9": ([2003, 1], [2026, 2]), "NO:1": ([2001, 2002], [2026, 1]), "NO:3": ([1993, 1994], [2026, 2]),
    "NO:8": ([2003, 1], [2026, 3]), "NYG:7": ([2004, 1], [2026, 1]), "NYJ:2": ([1990, 1993], [2026, 1]),
    "NYJ:6": ([2003, 1], [2026, 2]), "NYJ:7": ([0, 0], [2026, 3]), "PHI:4": ([1989, 1999], [2026, 1]),
    "PHI:10": ([2000, 2], [2026, 2]), "PHI:12": ([2003, 2], [2026, 3]), "PHI:13": ([2004, 1], [2026, 4]),
}
KEYS = ["MIN:5", "MIN:6", "NE:4", "NE:9", "NO:1", "NO:3", "NO:8", "NYG:7", "NYJ:2", "NYJ:6", "NYJ:7",
        "PHI:4", "PHI:10", "PHI:12", "PHI:13"]


def save(path: Path, colour, size=(8, 8), alpha=255) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, tuple(colour) + (alpha,)).save(path)


class CommittedRecipeTests(unittest.TestCase):
    def test_the_fifteen_alternates_are_the_plans_built_assignments(self) -> None:
        self.assertEqual(sorted(RECIPES["alternates"]), sorted(KEYS))
        for key, recipe in RECIPES["alternates"].items():
            team, style = key.split(":")
            plan = next(a for a in PLAN["teams"][team]["assignments"] if a["style"] == int(style))
            self.assertEqual(plan["status"], "built", key)
            self.assertEqual((recipe["team"], recipe["style"]), (team, int(style)), key)
            self.assertEqual(recipe["retail_pair"], EXPECTED[key][0], key)
            self.assertEqual(recipe["label"], EXPECTED[key][1], key)
            self.assertEqual(sorted(recipe["kits"]), ["A", "H"], key)

    def test_every_recipe_carries_sources_a_confidence_and_its_estimates(self) -> None:
        for key, recipe in RECIPES["alternates"].items():
            self.assertTrue(recipe["sources"] and all(s["url"].startswith("http") and s["supports"]
                                                       for s in recipe["sources"]), key)
            self.assertTrue(recipe["confidence"] and isinstance(recipe["estimates"], list), key)
        # the sets without a photo of the exact look say so
        self.assertIn("TEXT-ONLY", RECIPES["alternates"]["NO:3"]["confidence"])
        self.assertIn("TEXT-ONLY", RECIPES["alternates"]["PHI:12"]["confidence"])

    def test_the_labels_a_team_offers_count_up_in_cycle_order(self) -> None:
        by_team: dict[str, list] = {}
        for key, recipe in RECIPES["alternates"].items():
            by_team.setdefault(recipe["team"], []).append((recipe["style"], recipe["label"][1]))
        for team, rows in by_team.items():
            numbers = [n for _, n in sorted(rows)]
            self.assertEqual(numbers, sorted(numbers), team)
        # (MIN 8 Purple-on-Purple and the other appended indexes are not part of this job)
        self.assertNotIn("MIN:8", RECIPES["alternates"])

    def test_socks_are_never_written_banded(self) -> None:
        # the equipment writer scrambles banded textures (u3b): a set that keeps striped retail socks lists them
        for key in ("PHI:4", "NE:4"):
            self.assertIn("socks00", RECIPES["alternates"][key]["keep_slot"], key)

    def test_the_spec_patches_name_both_kits_on_the_slots_selectors(self) -> None:
        for key, recipe in RECIPES["alternates"].items():
            if key in ("NE:4", "PHI:4"):
                self.assertIn("modernize", recipe)          # the two sets made from the slot's own retail art
            else:
                self.assertEqual(sorted(recipe["spec"]["kits"]), ["A", "H"], key)


class MergeTests(unittest.TestCase):
    def test_dicts_merge_lists_replace_and_none_deletes(self) -> None:
        base = {"a": {"x": 1, "y": [1, 2]}, "b": 2, "c": {"z": 1}}
        out = ud.merge(base, {"a": {"y": [3]}, "b": None, "c": {"w": 5}})
        self.assertEqual(out, {"a": {"x": 1, "y": [3]}, "c": {"z": 1, "w": 5}})
        self.assertEqual(base["a"]["y"], [1, 2])                       # the input is not changed


class SpecTests(unittest.TestCase):
    def test_a_patched_team_kit_on_the_slots_selector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exp = Path(tmp)
            doc = {"kits": {sel: {"outer_index": n, "unif": {}, "assets": []} for sel, n in
                            (("21H13", 3788), ("21A13", 4105), ("21H0", 3783), ("21A0", 4100))}}
            (exp / "export.json").write_text(json.dumps(doc))
            spec = ud.build_spec(RECIPES["alternates"]["PHI:13"], exp)
            self.assertEqual({k["selector"] for k in spec["kits"].values()}, {"21H13", "21A13"})
            home = spec["kits"]["H"]
            self.assertEqual((home["outer_index"], home["torso"]["base_colour"]), (3788, "jet_black"))
            self.assertEqual(home["torso"]["neck_donor"], "21H13")
            self.assertEqual(home["splayer"]["torso_donor_outer"], 3788)       # read from the export
            self.assertEqual(spec["albedo"]["jet_black"], "#111113")
            self.assertEqual(home["torso"]["collar_shield"], True)               # kept from the team's own kit


class MarkAndHelmetOpTests(unittest.TestCase):
    def test_derived_marks_union_masks_and_put_a_ring_under_the_fill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marks = root / "marks"
            for name, box in (("a.png", (10, 10, 20, 20)), ("b.png", (30, 10, 40, 20))):
                m = np.zeros((40, 60, 4), np.uint8)
                m[box[1]:box[3], box[0]:box[2]] = 255
                Image.fromarray(m, "RGBA").save(marks / name) if marks.mkdir(exist_ok=True) is None else None
            recipe = {"derived_marks": {"m": {"fill": ["a.png", "b.png"], "fill_colour": "#C9A646",
                                              "ring": ["a.png", "b.png"], "ring_colour": "#000000", "ring_frac": 0.1}},
                      "marks_extra": {"x.png": str(marks / "a.png")}}
            folder = ud.derive_marks(recipe, marks, root / "out")
            made = np.asarray(Image.open(folder / "m.png"))
            self.assertEqual(tuple(made[15, 15, :3]), (201, 166, 70))          # the fill
            self.assertEqual(tuple(made[15, 8, :3]), (0, 0, 0))                # the ring outside it
            self.assertGreater(int(made[15, 35, 3]), 250)                      # the second mask joined the union
            self.assertTrue((folder / "x.png").exists() and (folder / "a.png").exists())

    def test_the_helmet_stripe_is_cleared_and_redrawn_as_a_tapering_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mark = np.zeros((20, 20, 4), np.uint8)
            mark[2:18, 2:18] = 255
            marks = root / "marks"
            marks.mkdir()
            Image.fromarray(mark, "RGBA").save(marks / "dot.png")
            helmet = np.zeros((256, 256, 4), np.uint8)
            helmet[..., :3] = (240, 240, 240)
            helmet[..., 3] = 255
            helmet[:, 150:154, :3] = (255, 255, 255)
            helmet[10:20, 0:5, 3] = 0                                          # a cut-out the stripe must not fill
            png = root / "helmet.png"
            Image.fromarray(helmet, "RGBA").save(png)
            cfg = {"mark": "dot.png", "colour": "#C9A646", "base": "#0E0E10", "x": 162, "y0": 6, "y1": 226,
                   "w0": 26, "w1": 12, "size": 5.0, "pitch": 5.0, "clear": [146, 178]}
            ud.helmet_fleur_stripe(cfg, marks, png)
            out = np.asarray(Image.open(png))
            self.assertLess(int(out[100, 148, :3].max()), 30)                  # cleared to the shell colour
            gold = ((np.abs(out[..., 0].astype(int) - 201) < 40) & (np.abs(out[..., 2].astype(int) - 70) < 50))
            self.assertGreater(int(gold[:, 140:185].sum()), 50)               # the mark field is gold
            self.assertGreater(int(gold[20:60].sum()), int(gold[180:220].sum()))  # wide end first, tapering
            self.assertEqual(int(out[15, 2, 3]), 0)                            # the retail alpha is kept
            self.assertTrue((out[100, 20, :3] == 240).all())                   # nothing outside the stripe moved

    def test_a_sleeve_is_shifted_down_its_islands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "sleeve.png"
            sleeve = np.zeros((128, 128, 4), np.uint8)
            sleeve[..., :3] = (170, 10, 30)
            sleeve[..., 3] = 255
            sleeve[10:20, 30:60, :3] = (255, 255, 255)
            Image.fromarray(sleeve, "RGBA").save(png)
            ud.modernize_part("sleeve", {"shift_rows": 8}, png)
            out = np.asarray(Image.open(png))
            self.assertTrue((out[22:26, 40, :3] > 200).all())                  # the art moved 8 rows down
            self.assertTrue((out[10:14, 40, :3] < 200).any())


class RetailOverrideTests(unittest.TestCase):
    def test_a_slot_texture_can_start_from_another_kit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exp = Path(tmp)
            save(exp / "uniforms/19H6/helmet_helmet02.png", (255, 255, 255))
            save(exp / "uniforms/19H6/torso.png", (10, 10, 10))
            save(exp / "uniforms/19H0/helmet_helmet02.png", (17, 87, 64))
            recipe = {"code": "19", "style": 6, "retail_override": {"H": {"helmet_helmet02": "19H0"}}}
            folder = ud.retail_dir(recipe, exp, exp / "work")
            self.assertEqual(tuple(np.asarray(Image.open(folder / "19H6/helmet_helmet02.png"))[0, 0, :3]), (17, 87, 64))
            self.assertEqual(tuple(np.asarray(Image.open(folder / "19H6/torso.png"))[0, 0, :3]), (10, 10, 10))
            self.assertTrue((folder / "19H0").is_symlink())


class AuthorOpsTests(unittest.TestCase):
    def test_donor_all_recolour_and_keep_slot_on_a_synthetic_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = root / "export"
            assets = [("torso.png", "TSET", 1, 0), ("socks00.png", "TSET", 4, 0), ("socks00_mud.png", "TSET", 4, 1)]
            doc = {"kits": {}}
            for sel, n in (("21H4", 3792), ("21A4", 4109)):
                doc["kits"][sel] = {"outer_index": n, "unif": {"facemask": "FF9598A2", "turtleneck": "FF007342"},
                                    "assets": [{"file": f, "name": f[:-4], "kind": k, "chunk": c, "tset_index": i,
                                                "size": [8, 8]} for f, k, c, i in assets]}
            for f, *_ in assets:
                save(exp / "uniforms/21H4" / f, (0, 107, 57))
                save(exp / "uniforms/21A4" / f, (250, 250, 250))
            (exp / "export.json").write_text(json.dumps(doc))
            recipe = {"team": "PHI", "code": "21", "style": 4, "set": "Kelly Green", "build_type": "modernize",
                      "kits": {"H": {}, "A": {}}, "donor_all": {"A": "21H4"},
                      "recolour": [{"from": "#006B39", "to": "#008C48", "tolerance": 0.3,
                                    "components": ["torso", "socks00", "socks00_mud"]}],
                      "keep_slot": ["socks00", "socks00_mud"]}
            out = ud.author(recipe, exp, root / "art")
            png_kinds = sorted((Path(e.get("png") or e.get("clean_png")).parent.name,
                                e["kind"]) for e in out["edits"])
            # the torso changes on both kits; the socks are reset to the slot's own, so neither is written
            self.assertEqual(png_kinds, [("21A4", "torso"), ("21H4", "torso")])
            torso = np.asarray(Image.open(root / "art/21A4/torso.png"))
            self.assertGreater(int(torso[0, 0, 1]), 125)                      # the donor's green, lifted
            socks = np.asarray(Image.open(root / "art/21A4/socks00.png"))
            self.assertEqual(tuple(socks[0, 0, :3]), (250, 250, 250))         # the slot's own road socks


class RepairTests(unittest.TestCase):
    def test_the_repair_defaults_to_the_u3d_recipes_and_names_only_its_slots(self) -> None:
        self.assertEqual(u3d_repair.RECIPES.name, "nfl2k5_uniform_alternates_2026_u3d.json")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(json.dumps({"schema": ur.MANIFEST_SCHEMA, "key": "NYJ:7",
                                        "resources": {"19H7.IFF": [], "19A7.IFF": [], "outer:3102": [], "outer:3105": []}}))
            self.assertEqual(len(ur.load_manifests([path], RECIPES, ["NYJ:7"])), 1)
            path.write_text(json.dumps({"schema": ur.MANIFEST_SCHEMA, "key": "NYJ:7", "resources": {"19H6.IFF": []}}))
            with self.assertRaises(ValueError):
                ur.load_manifests([path], RECIPES, ["NYJ:7"])

    def test_an_orphan_kit_starts_from_the_zero_pair(self) -> None:
        import struct
        from mod_editor.core import nfl2k5_historic_styles as hs
        from mod_editor.core import nfl2k5_uniform_slots as us
        recipe = RECIPES["alternates"]["NYJ:7"]
        self.assertEqual(recipe["retail_pair"], [0, 0])
        # a synthetic main roster with one team record (asset code 19) whose style-7 pair is zero
        original = hs.team_records
        record_at = 40
        roster = bytearray(32 + 4096)
        try:
            hs.team_records = lambda data: [(record_at, "19")] + [(record_at + 1000 * (i + 1), f"x{i:02d}") for i in range(31)]
            at = 32 + record_at + us.TABLE + 4 * (recipe["style"] - 1)
            patch = ur.roster_patch(bytes(roster), "19", recipe["style"], tuple(recipe["retail_pair"]), tuple(recipe["label"]))
            self.assertEqual((patch["offset"], patch["length"]), (at, 4))
            self.assertEqual(patch["data"], struct.pack("<HH", 2026, 3))
            roster[at:at + 4] = struct.pack("<HH", 1999, 1)
            with self.assertRaises(ValueError):
                ur.roster_patch(bytes(roster), "19", recipe["style"], tuple(recipe["retail_pair"]), tuple(recipe["label"]))
        finally:
            hs.team_records = original


if __name__ == "__main__":
    unittest.main()
