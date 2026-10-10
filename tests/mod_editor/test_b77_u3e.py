"""Job u3e (beta 77): the 2026 alternates of PIT SEA SF TB TEN WAS (author with overlays, painter, marks, repair keys).

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

import u3e_author as ea  # noqa: E402
import u3e_marks as em  # noqa: E402
import u3e_paint as ep  # noqa: E402
import u3e_repair as er  # noqa: E402
import u3s_alternates as ua  # noqa: E402

RECIPES = json.loads((REPO / "data/nfl2k5_uniform_alternates_2026.json").read_text())["alternates"]
SPEC_DIR = REPO / "data/nfl2k5_uniform_alt_specs_2026"
WHITE, BLACK, GOLD, BURGUNDY = (255, 255, 255), (0, 0, 0), (255, 182, 18), (90, 20, 20)


def save(path: Path, colour, size=(8, 8), alpha=255) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, tuple(colour) + (alpha,)).save(path)


class RecipeDataTests(unittest.TestCase):
    keys = er.OWNED_KEYS

    def test_every_owned_alternate_has_a_recipe_a_slot_and_sources(self) -> None:
        self.assertEqual(sorted(self.keys), sorted(["PIT:5", "SEA:3", "SEA:4", "SF:7", "TB:2", "TB:6", "TEN:7", "WAS:9"]))
        for key in self.keys:
            r = RECIPES[key]
            team, style = key.split(":")
            self.assertEqual((r["team"], r["style"]), (team, int(style)), key)
            self.assertIn(r["build_type"], ea.BUILD_TYPES)
            self.assertEqual(r["label"][0], 2026)
            self.assertEqual(sorted(r["kits"]), ["A", "H"])
            self.assertTrue(r["sources"] and all(s["url"].startswith("https://") for s in r["sources"]), key)
            self.assertTrue((REPO / r["spec"]).exists(), key)

    def test_the_labels_follow_the_cycle_order(self) -> None:
        by_team: dict[str, list] = {}
        for key in self.keys:
            by_team.setdefault(key.split(":")[0], []).append((RECIPES[key]["style"], RECIPES[key]["label"][1]))
        for team, rows in by_team.items():
            rows.sort()
            self.assertEqual([n for _, n in rows], list(range(1, len(rows) + 1)), team)

    def test_the_slots_are_the_planned_ones(self) -> None:
        plan = json.loads((REPO / "data/nfl2k5_uniform_slots_2026.json").read_text())["teams"]
        for key in self.keys:
            team, style = key.split(":")
            planned = {int(a["style"]) for a in plan[team]["assignments"]}
            self.assertIn(int(style), planned, key)

    def test_each_spec_names_the_recipes_two_sets(self) -> None:
        for key in self.keys:
            r = RECIPES[key]
            spec = json.loads((REPO / r["spec"]).read_text())
            self.assertEqual(spec["schema"], "nfl2k5_team_2026/v1")
            sels = ([k["selector"] for k in spec["kits"].values()] or [m["selector"] for m in spec.get("modernize", [])])
            self.assertEqual(sorted(sels), sorted(f"{r['code']}{side}{r['style']}" for side in "HA"), key)
            for kit in spec["kits"].values():
                self.assertEqual(kit["selector"][:2], r["code"])
                for d in ("digits", "nameplate"):
                    self.assertEqual(kit[d]["glyph_donor"], kit["selector"])    # the slot's own glyph boxes


class DonorAndRuleTests(unittest.TestCase):
    def test_parts_donors_and_per_kit_rules(self) -> None:
        kit = {"donor": "29H9", "parts": {"digit_*": "29A9", "sleeve": "29A0"}}
        self.assertEqual(ea.kit_donor(kit, "digit_jersey_3"), "29A9")
        self.assertEqual(ea.kit_donor(kit, "sleeve"), "29A0")
        self.assertEqual(ea.kit_donor(kit, "torso"), "29H9")
        rule = {"components": ["digit_*", "torso"], "kits": ["H"]}
        self.assertTrue(ea.rule_applies(rule, "H", "digit_arm_1"))
        self.assertFalse(ea.rule_applies(rule, "A", "torso"))
        self.assertTrue(ea.rule_applies({"components": ["torso"]}, "A", "torso"))

    def test_include_boxes_limit_a_recolour(self) -> None:
        src = np.ones((6, 6, 4), np.float32)
        src[..., :3] = np.array(BURGUNDY, np.float32) / 255.0
        rule = {"from": "#5A1414", "to": "#FFB612", "tolerance": 0.3, "include": [[0, 0, 3, 6]]}
        out, changed = ea.recolour(src, rule)
        self.assertEqual(changed, 18)
        np.testing.assert_allclose(out[:, 3:, :3], src[:, 3:, :3])

    def test_a_logo_body_enclosed_by_its_outline_keeps_its_colour(self) -> None:
        im = np.ones((12, 12, 4), np.float32)
        shell, outline = np.array(BURGUNDY, np.float32) / 255.0, np.array(GOLD, np.float32) / 255.0
        im[..., :3] = shell
        im[3:9, 3:9, :3] = outline            # the outline ring ...
        im[4:8, 4:8, :3] = shell              # ... closes around a burgundy body
        rule = {"from": "#5A1414", "to": "#000000", "tolerance": 0.3, "protect_enclosed": [[0, 0, 12, 12]]}
        out, changed = ea.recolour(im, rule)
        np.testing.assert_allclose(out[6, 6, :3], shell, atol=1e-3)     # the body stays
        np.testing.assert_allclose(out[0, 0, :3], [0, 0, 0], atol=1e-3)  # the shell around the logo moves
        self.assertGreater(changed, 60)

    def test_hard_edges_make_flat_colours_and_a_hard_alpha(self) -> None:
        g = np.zeros((8, 8, 4), np.float32)
        g[2:6, 2:6] = [1, 1, 1, 1]
        g[2:6, 2] = [0.1, 0.1, 0.1, 0.9]
        g[2:6, 6] = [0.4, 0.4, 0.4, 0.3]            # a faint edge below one half drops out
        out = ea.hard_edges(g, 2)
        self.assertEqual(set(np.unique(out[..., 3]).tolist()), {0.0, 1.0})
        self.assertLessEqual(len({tuple(p) for p in out[out[..., 3] > 0][:, :3].round(2).tolist()}), 2)
        self.assertEqual(float(out[2:6, 6, 3].max()), 0.0)


    def test_a_fill_the_colour_of_the_jersey_can_be_left_out(self) -> None:
        g = np.zeros((8, 8, 4), np.float32)
        g[1:7, 1:7] = [15 / 255, 39 / 255, 72 / 255, 1.0]          # the navy fill
        g[1:7, 1] = [0.4, 0.7, 0.9, 1.0]                            # a light outline column
        out = ea.hard_edges(g, 1, "#0F2748")
        self.assertEqual(float(out[3, 3, 3]), 0.0)                  # the fill is transparent
        self.assertEqual(float(out[3, 1, 3]), 1.0)                  # the outline stays, flat


class AuthorOverlayTests(unittest.TestCase):
    def test_overlay_art_replaces_the_donor_and_mud_twins_follow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = root / "export"
            assets = [("torso.png", "TSET", 1, 0), ("socks00.png", "TSET", 4, 0), ("socks00_mud.png", "TSET", 4, 1),
                      ("digit_jersey_1.png", "TXTR", 14, 0), ("sleeve.png", "TSET", 3, 0)]
            doc = {"kits": {}}
            for sel, outer in (("29H9", 3868), ("29A9", 4185), ("29A0", 4176)):
                doc["kits"][sel] = {"outer_index": outer, "unif": {"facemask": "FFF9B402", "turtleneck": "FF822743"},
                                    "assets": [{"file": f, "name": f[:-4], "kind": k, "chunk": c, "tset_index": i,
                                                "size": [8, 8]} for f, k, c, i in assets]}
                for f, *_ in assets:
                    save(exp / "uniforms" / sel / f, WHITE if sel != "29A0" else BURGUNDY)
            (exp / "export.json").write_text(json.dumps(doc))
            overlay = root / "overlay"
            for sel in ("29H9", "29A9"):
                save(overlay / sel / "torso.png", (16, 16, 18))
                save(overlay / sel / "socks00.png", (16, 16, 18))
            recipe = {"team": "WAS", "code": "29", "style": 9, "set": "Hail Raiser", "build_type": "new",
                      "kits": {"H": {"donor": "29H9", "parts": {"sleeve": "29A0"}}, "A": {"donor": "29A9"}},
                      "recolour": [], "unif": {"facemask": "FF111114"}, "unif_by_kit": {"A": {"turtleneck": "FF121215"}}}
            out = ea.author(recipe, exp, root / "art", overlay)
            self.assertEqual(int(np.asarray(Image.open(root / "art/29H9/torso.png"))[0, 0, 0]), 16)
            self.assertEqual(int(np.asarray(Image.open(root / "art/29H9/socks00_mud.png"))[0, 0, 0]), 10)   # 16 x 0.6
            self.assertEqual(int(np.asarray(Image.open(root / "art/29H9/sleeve.png"))[0, 0, 0]), BURGUNDY[0])  # parts donor
            self.assertEqual(int(np.asarray(Image.open(root / "art/29A9/sleeve.png"))[0, 0, 0]), 255)       # own donor
            colours = {e["selector"]: e for e in out["edits"] if e["kind"] == "unif_color"}
            self.assertEqual(colours["29H9"]["facemask"], "FF111114")
            self.assertEqual(colours["29A9"]["turtleneck"], "FF121215")
            self.assertTrue(any(e["kind"] == "torso" for e in out["edits"]))


class PaintLayoutTests(unittest.TestCase):
    def test_the_art_tools_folders_are_laid_out_from_an_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = root / "export"
            doc = {"kits": {"29H9": {"outer_index": 3868, "assets": [
                {"file": "names.png", "name": "names", "kind": "TXTR", "chunk": 43, "tset_index": 0, "size": [8, 8]},
                {"file": "socks00.png", "name": "socks00", "kind": "TSET", "chunk": 4, "tset_index": 0, "size": [8, 8]},
                {"file": "splayer.png", "name": "splayer", "kind": "TXTR", "chunk": 51, "tset_index": 0, "size": [8, 8]}]}},
                "cards": [{"name": "unif_h29_9", "width": 256, "png": "unif_h29_9_256.png"},
                          {"name": "helm_h29_9", "width": 128, "png": "helm_h29_9_128.png"}]}
            (exp / "cards").mkdir(parents=True)
            for f in ("names.png", "socks00.png", "splayer.png"):
                save(exp / "uniforms/29H9" / f, WHITE)
            for f in ("unif_h29_9_256.png", "helm_h29_9_128.png"):
                save(exp / "cards" / f, WHITE)
            (exp / "export.json").write_text(json.dumps(doc))
            retail, equipment, outers = ep.lay_out(exp, root / "work")
            self.assertEqual(outers, {"29H9": 3868})
            self.assertTrue((retail / "29H9/nameplate.png").exists())            # the art tool's name for names
            self.assertTrue((retail / "29H9/team-select_unif_256.png").exists())
            self.assertTrue((retail / "29H9/team-select_helm_128.png").exists())
            self.assertTrue((equipment / "tset_3868_4_0_socks00.png").exists())
            self.assertTrue((equipment / "p8_3868_splayer.png").exists())

    def test_copy_regions_move_only_the_box(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(root / "export/uniforms/29H0/helmet_helmet02.png", (200, 0, 0), (16, 16))
            save(root / "out/29H9/helmet_helmet02.png", (0, 0, 200), (16, 16))
            spec = {"kits": {"home": {"selector": "29H9", "copy_regions": [
                {"from": "29H0", "files": ["helmet_helmet02.png"], "box": [4, 4, 8, 8]}]}}}
            self.assertEqual(ep.copy_regions(spec, root / "export", root / "out"), 1)
            px = np.asarray(Image.open(root / "out/29H9/helmet_helmet02.png"))
            self.assertEqual(px[5, 5, 0], 200)
            self.assertEqual(px[0, 0, 2], 200)


class MarkTests(unittest.TestCase):
    def test_derived_marks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            w = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
            w.paste((255, 182, 18, 255), (20, 20, 380, 180))
            (root / "marks").mkdir()
            w.save(root / "marks/w_full.png")
            path = em.spear_w(root / "marks", root / "out")
            with Image.open(path) as im:
                self.assertGreater(im.width, 400)                      # the spear sits left of the W
            ship = Image.new("RGBA", (10, 10), (0, 0, 0, 255))
            ship.putpixel((5, 5), (255, 255, 255, 255))
            ship.save(root / "ship.png")
            with Image.open(em.dark_to(root / "ship.png", root / "red.png", "#B21C35")) as im:
                red = np.asarray(im).copy()
            self.assertGreater(int(red[0, 0, 0]), 80)
            self.assertLess(int(red[0, 0, 1]), 60)
            self.assertEqual(tuple(red[5, 5, :3]), (255, 255, 255))      # light details stay
            with Image.open(em.gradient_map(root / "ship.png", root / "g.png", ["#102030", "#A0B0C0"])) as im:
                grad = np.asarray(im).copy()
            self.assertEqual(tuple(grad[0, 0, :3]), (16, 32, 48))
            self.assertEqual(tuple(grad[5, 5, :3]), (160, 176, 192))


class RepairKeysTests(unittest.TestCase):
    def test_u3e_refuses_another_teams_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                er.main(["--input", str(Path(tmp) / "in"), "--output", str(Path(tmp) / "out"), "--manifest",
                         str(Path(tmp) / "m.json"), "--receipt", str(Path(tmp) / "r.json"), "--keys", "CIN:5"])


if __name__ == "__main__":
    unittest.main()
