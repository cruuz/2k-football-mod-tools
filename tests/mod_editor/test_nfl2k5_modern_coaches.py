"""2026 head coaches (beta 77 co1, co2, co3, cm1; b778 cm2): the pins and the shipped art, the coach bodies, the authored coach
geometry (cm1: Quinn's bald head, seven lean bodies), the Build wiring, and, when a retail USA image is present, the real
compile of coach scenes (Reid's derived head and the geometry included), the body ids and the two portrait slots
against their pins.

b780 c3-looks: a head coach the Studio moves to another club keeps his own model, face, glasses and geometry and wears
the shirt, jacket and chest logo of the club he leads (the coaching staff, ``staff``); his reserved picture follows him.

The always-on tests read only the repository. The retail checks read the user's own disc image and skip without it
(point NFL2K5_RETAIL_XISO at the retail USA .xiso.iso; NFL2K5_V08_XISO at the released v0.8 disc for the moved looks
compiled from a disc that already has the 2026 coaches).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as build_settings  # noqa: E402
from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))
HAVE_RETAIL = RETAIL.is_file()
# b778 cm2: the SOFTDRINK 2K28 v0.6.1 disc (built with the cm1 coaches), read only, when present
V061 = Path(os.environ.get("NFL2K5_V061_XISO", str(ROOT / "SOFTDRINK 2K28 v0.6.1.xiso.iso")))
HAVE_V061 = V061.is_file()
# b780 c3-looks: the released SOFTDRINK 2K28 v0.8 disc (the current 2026 coaches applied), read only, when present
V08 = Path(os.environ.get("NFL2K5_V08_XISO", str(ROOT / "SOFTDRINK 2K28 v0.8.xiso.iso")))
HAVE_V08 = V08.is_file()
# b780 c3-looks: three moved head coaches the tests dress (coach's 2026 club -> the club he leads): Andy Reid (capped
# c21) to the Raiders, DeMeco Ryans (c05, the jacket model with a few collar triangles fewer) to the 49ers' white top,
# Dan Quinn (bald geometry, glasses hidden, reserved picture 7034) to the Cowboys
MOVES = {"KC": "LV", "HOU": "SF", "WAS": "DAL"}
TEAMS = {"ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
         "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"}
SIZES = {"shirt": (128, 128), "jacket": (128, 128), "logo": (64, 64), "headset": (64, 64), "head": (256, 128),
         "head_mask": (256, 128), "head_overlay": (256, 128), "sideline_dry": (256, 256), "sideline_rain": (256, 256)}
# cm1: the clubs whose coach scene carries authored vertex edits (WAS: the bald head; the others: a lean body)
GEOMETRY = {"WAS", "CIN", "CAR", "GB", "TEN", "LAR", "SF", "MIN", "JAX", "BAL", "CLE", "IND", "PIT"}
# b778 cf1: every scanned coach (tools/b77/cf1_recipes/<club>.json) ships a head shape in geometry.json
GEOMETRY |= {p.stem for p in (ROOT / "tools" / "b77" / "cf1_recipes").glob("*.json")}
# co2: the club whose coach wears another retail body, and the body (cNN) he wears
MOVED = {"ARI": "12", "CAR": "09", "CHI": "37", "CLE": "26", "DET": "04", "HOU": "05", "JAX": "30", "KC": "21",
         "MIN": "28", "NYG": "22", "PHI": "18", "PIT": "27", "SEA": "13", "TEN": "15", "TB": "00", "CIN": "36",
         "IND": "33"}
# b778 cm2: facts the pins must agree with. The 2026 head coaches who are Black men, and the retail coach models that
# are Black men (2004: Dennis Green c00, Lovie Smith c05, Marvin Lewis c06, Tony Dungy c11, Herman Edwards c19; the
# created-team coaches c50, c51). The capped retail models (hatShader1 on the body).
BLACK_COACHES = {"TB", "HOU", "NYJ"}
BLACK_MODELS = {"00", "05", "06", "11", "19", "50", "51"}
CAPPED_MODELS = {"07", "11", "18", "19", "21", "22", "24", "27", "37", "50", "51"}
# b778 cm2: the models no club wears any more (an earlier version of the option dressed them)
RETIRED = {"c06.iff", "c11.iff"}


class PinsAndArt(unittest.TestCase):
    def test_pins_name_every_club_once_and_the_two_portraits(self):
        pins = mc.pins()
        self.assertEqual({r["team"] for r in pins["teams"]}, TEAMS)
        self.assertEqual(len({r["archive"] for r in pins["teams"]}), 32)
        self.assertEqual({r["archive"] for r in pins["teams"]},
                         ({f"c{i:02d}.iff" for i in range(31)} | {"c33.iff", "c36.iff", "c37.iff"}) - RETIRED)
        self.assertEqual([(p["team"], p["portrait_id"], p["retail_photo_id"]) for p in pins["portraits"]],
                         [("DAL", "7031", 7007), ("WAS", "7034", 7029)])
        for row in pins["teams"]:
            self.assertEqual(row["archive"], f"c{row['body_code']}.iff")
            self.assertEqual(row["body_code"] != row["team_code"], row["team"] in MOVED, row["team"])
            self.assertEqual(row["body_code"], MOVED.get(row["team"], row["team_code"]))
            self.assertNotEqual(row["retail_sha256"], row["applied_sha256"])
            self.assertIn(row["palette_max"], mc.PALETTE_LADDER)
            self.assertLessEqual(row["fit"]["scratch_needed"], row["fit"]["scratch_retail"])
            self.assertEqual(row["fit"]["stored_size"] + 0x20, row["span_size"])

    def test_kansas_city_wears_the_2004_reid_model_with_a_scanned_head(self):
        """Noah 2026-10-12: use the existing Andy Reid model for the Chiefs' Andy Reid; 10/22: "All 32 coaches should
        have their face scanned": b778 cf4 scans the 2026 Reid onto that model (head.png; the derived 2004 head retired)."""
        kc = {r["team"]: r for r in mc.pins()["teams"]}["KC"]
        self.assertEqual((kc["archive"], kc["team_code"]), ("c21.iff", "13"))
        self.assertNotIn("head_recipe", kc)
        self.assertIn("head", kc["art"])
        self.assertTrue(mc.art_path("KC", "head").exists())
        self.assertFalse(set(mc.HEAD_RECIPE_FILES) & set(kc["art"]))

    def test_derive_head_is_integer_and_exact(self):
        import numpy as np
        retail = np.zeros((2, 3, 4), np.uint8)
        retail[..., :3] = [[[100, 60, 40], [200, 150, 120], [10, 20, 30]], [[255, 255, 255], [0, 0, 0], [90, 90, 90]]]
        retail[..., 3] = 255
        mask = np.zeros((2, 3, 3), np.uint8)
        mask[0, 0] = (255, 80, 0)        # full weight, class 1
        mask[0, 1] = (128, 160, 0)       # half weight, class 2
        overlay = np.zeros((2, 3, 4), np.uint8)
        overlay[1, 2] = (50, 60, 70, 255)
        out = mc.derive_head(retail, mask, {"1": [170, 80, 14, [0, 0, 3]], "2": [122, 110, 12, [6, 2, -2]]}, overlay)
        luma = (100 * 299 + 60 * 587 + 114 * 40 + 500) // 1000
        grey = 170 + ((luma - 80) * 14) // 16
        self.assertEqual(out[0, 0, :3].tolist(), [grey, grey, grey + 3])
        self.assertEqual(out[0, 2].tolist(), [10, 20, 30, 255])                 # no weight: retail
        self.assertEqual(out[1, 2].tolist(), [50, 60, 70, 255])                 # opaque overlay
        self.assertEqual(out[1, 0].tolist(), [255, 255, 255, 255])

    def test_only_the_headset_half_of_the_accessories_atlas_ships(self):
        """b77 co3: the shoe and clipboard (x >= 64 of the 128x64 atlas) are retail art; they come from the user's disc."""
        from PIL import Image
        self.assertEqual((mc.HEADSET_WIDTH, mc.ACCESSORIES_SIZE), (64, (128, 64)))
        self.assertIn(("headset", "accessoriesShader1"), mc.TEXTURES)
        self.assertNotIn("accessories", mc.ART_NAMES)
        for row in mc.pins()["teams"]:
            self.assertFalse(mc.art_path(row["team"], "accessories").exists(), row["team"])
            self.assertIn("headset", row["art"])
            with Image.open(mc.art_path(row["team"], "headset")) as image:
                self.assertEqual(image.size, (64, 64))
        allowlist = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8")
        self.assertNotIn("accessories.png", allowlist)

    def test_derive_accessories_is_the_authored_round_trip_in_integers(self):
        """The integer bicubic 4x upscale equals Pillow's, and the block mean rounds half to even like the float area
        downscale the art was authored with, so the derived shoe and clipboard equal the earlier shipped pixels."""
        import numpy as np
        from PIL import Image
        rng = np.random.default_rng(2026)
        atlas = rng.integers(0, 256, (64, 128, 4), dtype=np.uint8)
        atlas[..., 3] = 255
        pillow = np.asarray(Image.fromarray(atlas, "RGBA").resize((512, 256), Image.BICUBIC))
        ours = mc.bicubic_upscale(atlas)
        self.assertTrue(np.array_equal(ours, pillow.astype(np.int64)))
        self.assertEqual(mc.block_mean(np.full((4, 4, 1), 2, np.uint8)).item(), 2)
        halves = np.array([[[0], [0], [0], [0]], [[0], [0], [0], [0]], [[1], [1], [1], [1]], [[1], [1], [1], [1]]],
                          np.uint8)                                          # mean 0.5 -> 0 (even)
        self.assertEqual(mc.block_mean(halves).item(), 0)
        self.assertEqual(mc.block_mean(halves + 2).item(), 2)              # mean 2.5 -> 2 (even)
        self.assertEqual(mc.block_mean(halves + 1).item(), 2)              # mean 1.5 -> 2 (even)
        headset = np.zeros((64, 64, 4), np.uint8)
        headset[..., 3] = 255
        out = mc.derive_accessories(atlas, headset)
        self.assertEqual(out.shape, (64, 128, 4))
        self.assertTrue(np.array_equal(out[:, :64], headset))
        reference = pillow.reshape(64, 4, 128, 4, 4).astype(np.float64).mean(axis=(1, 3))
        self.assertTrue(np.array_equal(out[:, 64:], np.uint8(np.rint(reference))[:, 64:]))
        translucent = atlas.copy()
        translucent[0, 0, 3] = 254
        with self.assertRaises(mc.ModernCoachesError):
            mc.derive_accessories(translucent, headset)
        with self.assertRaises(mc.ModernCoachesError):
            mc.derive_accessories(atlas, headset[:32])

    def test_the_bodies_are_one_model_per_club(self):
        pins = mc.pins()
        self.assertEqual(sorted(r["body_code"] for r in pins["teams"]),
                         sorted([f"{i:02d}" for i in range(31) if i not in (6, 11)] + ["33", "36", "37"]))
        self.assertEqual(set(pins["bodies"]), TEAMS)
        good = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
        bad = json.loads(json.dumps(good))
        bad["teams"][0]["body_code"] = bad["teams"][1]["body_code"]
        bad["teams"][0]["archive"] = bad["teams"][1]["archive"]
        with self.assertRaises(mc.ModernCoachesError):
            mc._check_pins(bad)

    def test_every_coach_is_dressed_on_a_model_of_his_own_skin(self):
        """b778 cm2 (Noah 10/21, Todd Bowles on the 2004 Jon Gruden model with a darkened face: "we should use an
        actual black model"): a Black coach stands on a Black coach's model (head, arms, hands) and a white coach on a
        white coach's model, never a model darkened or lightened."""
        pins = mc.pins()
        wrong = sorted(f"{r['team']} c{r['body_code']}" for r in pins["teams"]
                       if (r["team"] in BLACK_COACHES) != (r["body_code"] in BLACK_MODELS))
        self.assertEqual(wrong, [])
        self.assertEqual(set(mc.DARK_SKIN_MODELS), BLACK_MODELS)
        self.assertEqual({t for t, b in pins["bodies"].items() if b["skin"] == "dark"}, BLACK_COACHES)
        self.assertEqual(mc.skin_mismatches(pins), [])
        tb = {r["team"]: r for r in pins["teams"]}["TB"]
        self.assertEqual(tb["archive"], "c00.iff")           # Dennis Green's model: a Black coach, a broad build

    def test_a_coach_on_a_model_of_another_skin_is_refused(self):
        good = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
        bad = json.loads(json.dumps(good))
        bad["bodies"]["TB"]["skin"] = "light"
        with self.assertRaises(mc.ModernCoachesError):
            mc._check_pins(bad)
        bad = json.loads(json.dumps(good))
        del bad["bodies"]["PIT"]["skin"]
        with self.assertRaises(mc.ModernCoachesError):
            mc._check_pins(bad)
        bad = json.loads(json.dumps(good))
        bad["retired"].append(dict(bad["retired"][0], archive="c27.iff"))      # a model a club wears
        with self.assertRaises(mc.ModernCoachesError):
            mc._check_pins(bad)

    def test_mike_mccarthy_wears_a_cap(self):
        """b778 cm2 (Noah 10/21: "you gotta put a hat on"): Pittsburgh's coach stands on a capped model, its cap patch
        black, and keeps his heavy build (authored body geometry on c27)."""
        import numpy as np
        pit = {r["team"]: r for r in mc.pins()["teams"]}["PIT"]
        self.assertIn(pit["body_code"], CAPPED_MODELS)
        self.assertEqual(pit["superseded_body_codes"], ["26"])
        shirt = mc._rgba(mc.art_path("PIT", "shirt"), 128, 128)
        patch = shirt[2:16, 108:126, :3].reshape(-1, 3)        # the cap samples u 0.83-0.99, v 0.00-0.17
        self.assertLess(float(np.median(patch.mean(axis=1))), 60.0)
        self.assertIn("coachBodyGrp1", [s["name"] for s in mc.load_geometry(pit)["shapes"]])

    def test_retired_models_are_pinned_back_to_retail(self):
        pins = mc.pins()
        self.assertEqual({r["archive"] for r in pins["retired"]}, RETIRED)
        for row in pins["retired"]:
            self.assertTrue(row["superseded_sha256"])
            self.assertNotIn(row["retail_sha256"], row["superseded_sha256"])

    def test_the_shipped_art_matches_its_pins_and_sizes(self):
        self.assertTrue(mc.available())
        from PIL import Image
        for row in mc.pins()["teams"]:
            for name, digest in row["art"].items():
                path = mc.art_path(row["team"], name)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
                with Image.open(path) as image:
                    self.assertEqual(image.size, SIZES[name], f"{row['team']} {name}")

    def test_only_authored_textures_ship(self):
        """No reference photo or anything but the authored PNGs, the pins and the README in the data folder."""
        allowed = {"pins.json", "README.md"}
        for path in mc.DATA_DIR.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(mc.DATA_DIR).as_posix()
            if rel in allowed:
                continue
            team, name = rel.split("/")
            if name == mc.GEOMETRY_FILE:                    # cm1: authored vertex edits (integers), not an image
                self.assertIn(team, GEOMETRY)
                continue
            if name[:-4] in mc.HEAD_RECIPE_FILES:
                self.assertEqual(team, "KC")
            else:
                self.assertIn(team, TEAMS)
                self.assertIn(name[:-4], SIZES)

    def test_pictures_are_external_and_no_render_or_photo_ships(self):
        self.assertFalse(list((mc.DATA_DIR / "portraits").glob("*.png")))
        for row in mc.pins()["portraits"]:
            self.assertNotIn("png", row)
            self.assertNotIn("png_sha256", row)
            self.assertTrue(row["rejected_sha256"])

    def test_the_coach_geometry_is_pinned_and_well_formed(self):
        """b77 cm1: each geometry file is pinned, names its own archive, and lists integer lane values for the
        vertices that move (each vertex once, in range, unit normals) on the scene's three shapes only."""
        from mod_editor.core import nfl2k5_models as models
        rows = {r["team"]: r for r in mc.pins()["teams"]}
        self.assertEqual({t for t, r in rows.items() if r.get("geometry")}, GEOMETRY)
        for team in sorted(GEOMETRY):
            row = rows[team]
            doc = mc.load_geometry(row)
            self.assertEqual(doc["archive"], row["archive"])
            names = [item["name"] for item in doc["shapes"]]
            self.assertTrue(set(names) <= set(mc.GEOMETRY_SHAPES) and len(set(names)) == len(names), team)
            self.assertIn("coachBodyGrp1", names)              # the bald head's headset band moves too
            if team == "WAS":
                self.assertIn("coachHeadGrp1", names)
            for item in doc["shapes"]:
                self.assertEqual(len(item["lanes_sha256"]), 64)
                vertices = [v for v, *_q in item["positions"]]
                self.assertEqual(len(vertices), len(set(vertices)))
                self.assertTrue(all(0 <= v < item["vertex_count"] for v in vertices))
                self.assertTrue(all(-32768 <= int(q) <= 32767 for _v, *qs in item["positions"] for q in qs))
                self.assertGreater(len(item["positions"]), 0)
                for _v, word in item["normals"]:
                    n = models.decode_normpacked3(int(word))
                    self.assertAlmostEqual(sum(c * c for c in n) ** 0.5, 1.0, delta=0.01)

    def test_coach_geometry_refusals(self):
        row = dict({r["team"]: r for r in mc.pins()["teams"]}["WAS"])
        with self.assertRaises(mc.ModernCoachesError):
            mc.load_geometry(dict(row, geometry="0" * 64))      # differs from its pin
        with self.assertRaises(mc.ModernCoachesError):
            mc.load_geometry(dict(row, archive="c07.iff"))      # authored for another model
        with self.assertRaises(mc.ModernCoachesError):
            mc.apply_geometry(bytearray(), {"shapes": []}, {"schema": "other", "shapes": []})
        good = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
        bad = json.loads(json.dumps(good))
        bad["teams"][0]["geometry"] = "abc"
        with self.assertRaises(mc.ModernCoachesError):
            mc._check_pins(bad)

    def test_malformed_pins_are_refused(self):
        with self.assertRaises(mc.ModernCoachesError):
            mc._check_pins({"schema": "other"})
        good = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
        bad = dict(good, teams=good["teams"][:31])
        with self.assertRaises(mc.ModernCoachesError):
            mc._check_pins(bad)


class BuildWiring(unittest.TestCase):
    def test_plan_presets_availability_and_settings(self):
        plan = mod_build.BuildPlan("s", "t")
        self.assertIs(plan.modern_coaches, False)
        self.assertIn("modern_coaches", plan.to_recipe())
        for name, values in mod_build.PRESETS.items():
            with self.subTest(preset=name):
                self.assertIs(values["modern_coaches"], name == "softdrink_experimental")
        self.assertTrue(mod_build.availability()["modern_coaches"])
        self.assertIn("modern_coaches", build_settings.FEATURE_KEYS)
        saved = build_settings.build_settings({"modern_coaches": True})
        self.assertIs(build_settings.to_plan(saved, "s", "t").modern_coaches, True)
        self.assertEqual((mc.DEFAULT_ENABLED, mc.CAVES, mc.REQUESTS, mc.RUNTIME_GLOBALS, mc.LABEL),
                         (False, (), (), (), "EXPERIMENTAL / UNWITNESSED"))

    def test_refusals_before_any_copy(self):
        import tempfile
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        with tempfile.TemporaryDirectory(prefix="coaches-plan-") as raw:
            root = Path(raw)
            xbe = root / "default.xbe"
            xbe.write_bytes(_build_synthetic_xbe())
            with self.assertRaisesRegex(ValueError, "needs? a disc image"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out.xbe"), modern_coaches=True))
            with self.assertRaisesRegex(ValueError, "must be Off or On"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out2.xbe"), modern_coaches=1))
            self.assertEqual(mod_build.inspect(xbe)["modern_coaches"], "needs_image")
            self.assertFalse((root / "out.xbe").exists())

    def test_the_build_step_and_panel_name_the_option(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        for needle in ("coaches.apply_to_image(target, progress=progress, staff=_coach_staff(plan))",
                       '"step": "modern_coaches"', "coaches.image_status(source)",
                       "coaches.assignment(_coach_staff(plan))"):
            self.assertIn(needle, source)
        # after every roster writer and relocating pass: the coach step follows the goalposts step
        self.assertLess(source.index('"step": "modern_goalposts"'), source.index('"step": "modern_coaches"'))
        panel = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        for needle in ('"modern_coaches": self.modern_coaches_check', "modern_coaches=self._modern_coaches_changed()",
                       "def _modern_coaches_changed(self)"):
            self.assertIn(needle, panel)


class MovedCoaches(unittest.TestCase):
    """b780 c3-looks: the coaching staff, its refusals and the moved-look pins (repository only)."""

    def test_every_club_pins_its_coach_scene_and_its_apparel_at_every_palette_size(self):
        pins = mc.pins()
        self.assertEqual(mc.APPAREL, ("shirt", "jacket", "logo"))
        self.assertTrue(set(mc.APPAREL) <= {name for name, _m in mc.TEXTURES})
        scenes, apparel = set(), set()
        for row in pins["teams"]:
            self.assertEqual(len(row["scene_sha256"]), 64)
            self.assertEqual(set(row["apparel_sha256"]), {str(size) for size in mc.PALETTE_LADDER})
            scenes.add(row["scene_sha256"])
            apparel.update(row["apparel_sha256"].values())
            self.assertTrue(pins["bodies"][row["team"]]["coach"])
        self.assertEqual(len(scenes), 32)                       # every coach's own look is his
        self.assertEqual(len(apparel), 32 * len(mc.PALETTE_LADDER))   # every club's colours are its own
        self.assertEqual(mc.coach_name("KC"), "Andy Reid")
        good = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
        for key in ("scene_sha256", "apparel_sha256"):
            bad = json.loads(json.dumps(good))
            del bad["teams"][3][key]
            with self.assertRaises(mc.ModernCoachesError):
                mc._check_pins(bad)
        bad = json.loads(json.dumps(good))
        del bad["teams"][3]["apparel_sha256"]["96"]
        with self.assertRaises(mc.ModernCoachesError):
            mc._check_pins(bad)

    def test_the_staff_maps_every_club_to_one_coach(self):
        clubs = {r["team"] for r in mc.pins()["teams"]}
        self.assertEqual(mc.assignment(None), {c: c for c in clubs})
        swap = mc.assignment({"KC": "LV", "LV": "KC"})
        self.assertEqual((swap["KC"], swap["LV"], swap["DAL"]), ("LV", "KC", "DAL"))
        aliases = mc.assignment({"oak": "kc", "KC": "OAK", "STL": "SD", "SD": "STL"})   # roster abbreviations
        self.assertEqual((aliases["LV"], aliases["KC"], aliases["LAR"], aliases["LAC"]), ("KC", "LV", "LAC", "LAR"))
        created = mc.assignment({"LV": "KC", "KC": None})       # a coach who is not one of the 32 leads KC
        self.assertEqual((created["LV"], created["KC"]), ("KC", None))

    def test_a_coach_named_for_two_clubs_is_refused_in_plain_words(self):
        with self.assertRaisesRegex(mc.ModernCoachesError, "Andy Reid \\(KC\\) is the head coach of two clubs, KC and LV"):
            mc.assignment({"LV": "KC"})                          # KC keeps Reid too: give one of them another coach
        with self.assertRaisesRegex(mc.ModernCoachesError, "not one of the 32 clubs"):
            mc.assignment({"LONDON": "KC"})
        with self.assertRaises(mc.ModernCoachesError):
            mc.assignment(["KC", "LV"])

    def test_the_staff_comes_from_the_roster_edits(self):
        self.assertIsNone(mc.staff_from_edits({"schema": "x", "edits": []}))
        self.assertIsNone(mc.staff_from_edits({"staff": {"head_coaches": {"KC": "KC", "LV": "OAK"}}}))   # nobody moved
        self.assertEqual(mc.staff_from_edits({"staff": {"head_coaches": {"LV": "KC", "KC": "LV"}}}), {"LV": "KC", "KC": "LV"})
        listed = {"staff": {"head_coaches": [{"team": "LV", "coach": "KC"}, {"team": "KC", "coach": None}]}}
        self.assertEqual(mc.staff_from_edits(listed), {"LV": "KC", "KC": None})
        with self.assertRaises(mc.ModernCoachesError):
            mc.staff_from_edits({"staff": {"head_coaches": [{"team": "LV"}]}})
        self.assertIsNone(mc.staff_from_edits(None))

    def test_the_build_reads_the_staff_from_the_roster_edits(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="coach-staff-") as raw:
            edits = Path(raw) / "edits.json"
            edits.write_text(json.dumps({"schema": "2k5_mod_studio_roster_edits/v1", "edits": [],
                                         "staff": {"head_coaches": {"LV": "KC", "KC": "LV"}}}), encoding="utf-8",
                             newline="\n")
            plan = mod_build.BuildPlan("s", "t", roster_edits=str(edits))
            self.assertEqual(mod_build._coach_staff(plan), {"LV": "KC", "KC": "LV"})
        self.assertIsNone(mod_build._coach_staff(mod_build.BuildPlan("s", "t")))


@unittest.skipUnless(HAVE_RETAIL, "retail USA image not present (NFL2K5_RETAIL_XISO)")
class RetailCompile(unittest.TestCase):
    def test_retail_image_reads_retail(self):
        self.assertEqual(mc.image_status(RETAIL), "retail")

    def test_compile_reproduces_the_applied_pins(self):
        pins = {r["team"]: r for r in mc.pins()["teams"]}
        with mc._outer_image()(RETAIL) as archive:
            entries = {e.name_id: e for e in archive.entries}
            # Reid's derived head on c21, an unmoved club, a moved one, cm1's bald head and two lean bodies
            for team in ("KC", "DAL", "PIT", "WAS", "CIN", "LAR"):
                row = pins[team]
                entry = entries[mc.name_id(row["archive"])]
                raw = archive.read(entry.virtual_offset, entry.size)
                out, detail = mc.compile_archive(raw, row)
                span = out[row["span_offset"]:row["span_offset"] + row["span_size"]]
                self.assertEqual(mc.sha(span), row["applied_sha256"], team)
                self.assertEqual(out[:row["span_offset"]], raw[:row["span_offset"]])
                self.assertEqual(out[row["span_offset"] + row["span_size"]:], raw[row["span_offset"] + row["span_size"]:])
                self.assertEqual(out[row["span_offset"]:row["span_offset"] + 0x20],
                                 raw[row["span_offset"]:row["span_offset"] + 0x20])   # wrapper identical
                self.assertLessEqual(detail["fit"]["scratch_needed"], detail["fit"]["scratch_retail"])

    def test_the_geometry_moves_only_its_own_vertices(self):
        """b77 cm1: the WAS scene compiled with and without its geometry differs only in the position and normal lanes
        of the listed vertices; Quinn's crown is about a centimetre lower (the 2004 hair volume is gone), his face and
        ears do not move, and the skeleton, skin, triangles and textures are the same bytes. Another mesh is refused."""
        from mod_editor.core import nfl2k5_models as models
        import struct
        row = {r["team"]: r for r in mc.pins()["teams"]}["WAS"]
        doc = mc.load_geometry(row)
        with mc._outer_image()(RETAIL) as archive:
            entries = {e.name_id: e for e in archive.entries}
            raw = archive.read(entries[mc.name_id("c29.iff")].virtual_offset, entries[mc.name_id("c29.iff")].size)
            other = archive.read(entries[mc.name_id("c07.iff")].virtual_offset, entries[mc.name_id("c07.iff")].size)
        tx, _fill = mc._tools()
        rec, decoded = mc._mm()._scene(raw, tx.parse_chunks(raw)[0])
        edited = bytearray(decoded)
        detail = mc.apply_geometry(edited, rec, doc)
        allowed = set()
        heads = {}
        for item in doc["shapes"]:
            lanes, position_at, normal_at = mc._geometry_lanes(rec, decoded, item["name"])
            for v, *_q in item["positions"]:
                allowed.update(range(position_at(v), position_at(v) + 6))
            for v, _w in item["normals"]:
                allowed.update(range(normal_at(v), normal_at(v) + 4))
            if item["name"] == "coachHeadGrp1":
                shape = [s for s in rec["shapes"] if s["name"] == "coachHeadGrp1"][0]
                before = models.read_positions(bytes(decoded), shape, lanes)
                after = models.read_positions(bytes(edited), shape, models._shape_lanes(rec, shape, bytes(edited)))
                heads = dict(before=before, after=after)
        changed = {i for i, (a, b) in enumerate(zip(decoded, edited)) if a != b}
        self.assertTrue(changed and changed <= allowed)
        self.assertEqual(detail["coachHeadGrp1"]["positions"], len([1 for item in doc["shapes"]
                                                                      if item["name"] == "coachHeadGrp1"
                                                                      for _p in item["positions"]]))
        top_before = max(p[1] for p in heads["before"]); top_after = max(p[1] for p in heads["after"])
        self.assertGreater(top_before - top_after, 0.8)
        self.assertLess(top_before - top_after, 1.2)
        moved = [i for i, (a, b) in enumerate(zip(heads["before"], heads["after"]))
                 if max(abs(a[k] - b[k]) for k in range(3)) > 1e-3]
        # the bald edit stays off the face (in front of the ears, below the brows): only the scalp and the back of the
        # head move by more than the face scan (b778 cf3 scans Quinn's face: cf1_face_scan, at most 0.8 cm)
        self.assertTrue(moved and all(heads["before"][i][1] > 42.0 or heads["before"][i][2] < 8.0
                                      or max(abs(heads["before"][i][k] - heads["after"][i][k]) for k in range(3)) <= 0.81
                                      for i in moved))
        rec2, decoded2 = mc._mm()._scene(other, tx.parse_chunks(other)[0])
        with self.assertRaises(mc.ModernCoachesError):
            mc.apply_geometry(bytearray(decoded2), rec2, doc)
        self.assertIsNotNone(struct)

    def test_the_shoe_and_clipboard_come_from_the_disc_not_the_repository(self):
        """Every coach body's retail atlas: the compiled DAL atlas carries the authored headset and the disc's own shoe
        and clipboard (through the round trip); the shipped headset shares no pixel with the retail headset half."""
        import numpy as np
        row = {r["team"]: r for r in mc.pins()["teams"]}["DAL"]
        mm = mc._mm()
        tx, _fill = mc._tools()
        with mc._outer_image()(RETAIL) as archive:
            entry = {e.name_id: e for e in archive.entries}[mc.name_id(row["archive"])]
            raw = archive.read(entry.virtual_offset, entry.size)
        rec, decoded = mm._scene(raw, tx.parse_chunks(raw)[0])
        tex = [t for t in rec["embedded_textures"] if "accessoriesShader1" in (t.get("mapped_material_names") or ())][0]
        retail, _ = mm.read_p8(decoded, int(rec["system_bytes"]), tex)
        retail = np.asarray(retail, np.uint8)
        headset = mc._rgba(mc.art_path("DAL", "headset"), 64, 64)
        self.assertEqual(int((np.abs(retail[:, :64, :3].astype(int) - headset[..., :3]).max(axis=2) == 0).sum()), 0)
        derived = mc.derive_accessories(retail, headset)
        self.assertTrue(np.array_equal(derived[:, :64], headset))
        self.assertLessEqual(int(np.abs(derived[:, 64:].astype(int) - retail[:, 64:]).max()), 25)

    def test_glasses_hidden_only_where_the_2026_coach_wears_none(self):
        pins = {r["team"]: r for r in mc.pins()["teams"]}
        self.assertEqual(sorted(t for t, r in pins.items() if r["hide_glasses"]), ["CLE", "GB", "LAR", "SEA", "WAS"])
        import numpy as np
        row = pins["WAS"]
        with mc._outer_image()(RETAIL) as archive:
            entry = {e.name_id: e for e in archive.entries}[mc.name_id(row["archive"])]
            raw = archive.read(entry.virtual_offset, entry.size)
        out, detail = mc.compile_archive(raw, row)
        self.assertTrue(detail["textures"]["glasses"]["hidden"])
        tx, _fill = mc._tools()
        rec, decoded = mc._mm()._scene(out, tx.parse_chunks(out)[0])
        tex = [t for t in rec["embedded_textures"] if mc.GLASSES_MATERIAL in (t.get("mapped_material_names") or ())][0]
        rgba, _ = mc._mm().read_p8(decoded, int(rec["system_bytes"]), tex)
        self.assertEqual(int(np.asarray(rgba)[:, mc.GLASSES_KEEP_COLUMNS:, 3].max()), 0)

    def test_sideline_staff_packages_reproduce_their_pins(self):
        row = {r["team"]: r for r in mc.pins()["teams"]}["KC"]
        self.assertEqual(sorted(p["package"] for p in row["sideline"]), sorted(f"c13{v}.iff".replace("c13", "13")
                                                                               for v in mc.PACKAGES))
        with mc._outer_image()(RETAIL) as archive:
            entries = {e.name_id: e for e in archive.entries}
            for pkg in row["sideline"][:2] + row["sideline"][2:4]:
                _at, span = mc._package_span(archive, entries, pkg["package"], pkg["chunk_index"])
                self.assertEqual(mc.sha(span), pkg["retail_sha256"])
                after, detail = mc.compile_sideline(span, mc._rgba(mc.art_path("KC", pkg["design"]), 256, 256),
                                                    pkg["sideline_palette_max"])
                self.assertEqual(mc.sha(after), pkg["applied_sha256"])
                self.assertEqual(after[:0x20], span[:0x20])
                self.assertLessEqual(detail["fit"]["scratch_needed"], detail["fit"]["scratch_retail"])

    def test_the_retail_roster_names_each_club_model_and_the_old_pins_read_previous(self):
        pins = mc.pins()
        with mc._outer_image()(RETAIL) as archive:
            for row in pins["teams"]:
                if row["team"] in MOVED:
                    _site, value = mc._coach_body_site(archive, row["team"])
                    self.assertEqual(value, int(row["team_code"]), row["team"])
        parts = {k: v for k, v in mc.resource_states(RETAIL).items()}
        self.assertEqual({k for k in parts if k.startswith("body_id:")}, {f"body_id:{t}" for t in MOVED})
        self.assertEqual({v for k, v in parts.items() if not k.startswith("retired:")}, {"retail"})
        self.assertEqual({v for k, v in parts.items() if k.startswith("retired:")}, {"kept"})
        # c33 and c36 were never dressed before cm2 (no earlier art); every other model was
        # (a later face scan of CIN or IND gives those two rows cm2's digest as their superseded entry)
        self.assertLessEqual({row["archive"] for row in pins["teams"] if not row["superseded_sha256"]}, {"c33.iff", "c36.iff"})

    def test_the_dark_skin_models_are_the_retail_models_with_dark_arms(self):
        """DARK_SKIN_MODELS against the user's own disc: the arms texture of every retail coach model."""
        import numpy as np
        mm = mc._mm()
        tx, _fill = mc._tools()
        codes = [f"{i:02d}" for i in range(31)] + ["33", "36", "37", "50", "51"]
        luma = {}
        with mc._outer_image()(RETAIL) as archive:
            entries = {e.name_id: e for e in archive.entries}
            for code in codes:
                entry = entries[mc.name_id(f"c{code}.iff")]
                raw = archive.read(entry.virtual_offset, entry.size)
                rec, decoded = mm._scene(raw, tx.parse_chunks(raw)[0])
                tex = [t for t in rec["embedded_textures"] if "armsShader1" in (t.get("mapped_material_names") or ())][0]
                rgba, _ = mm.read_p8(decoded, int(rec["system_bytes"]), tex)
                rgb = np.asarray(rgba, np.float64)[..., :3].reshape(-1, 3)
                luma[code] = float((rgb @ np.array([0.299, 0.587, 0.114])).mean())
        self.assertEqual({c for c, v in luma.items() if v < 128.0}, set(mc.DARK_SKIN_MODELS), luma)

    def test_pittsburgh_compiles_with_the_cap_and_the_heavy_body(self):
        from mod_editor.core import nfl2k5_models as models
        row = {r["team"]: r for r in mc.pins()["teams"]}["PIT"]
        tx, _fill = mc._tools()
        with mc._outer_image()(RETAIL) as archive:
            entries = {e.name_id: e for e in archive.entries}
            def scene(name):
                e = entries[mc.name_id(name)]
                raw = archive.read(e.virtual_offset, e.size)
                return raw, mc._mm()._scene(raw, tx.parse_chunks(raw)[0])
            raw, _ = scene("c27.iff")
            out, detail = mc.compile_archive(raw, row)
            self.assertEqual(mc.sha(out[row["span_offset"]:row["span_offset"] + row["span_size"]]), row["applied_sha256"])
            rec, decoded = mc._mm()._scene(out, tx.parse_chunks(out)[0])
            _raw26, (rec26, dec26) = scene("c26.iff")
            _raw27, (rec27, dec27) = scene("c27.iff")
        names = {str(m) for t in rec["embedded_textures"] for m in (t.get("mapped_material_names") or ())}
        self.assertIn("hatShader1", names)

        def belly(rec_, dec_):
            shape = [s for s in rec_["shapes"] if s["name"] == "coachBodyGrp1" and int(s["vertex_count"]) > 0][0]
            pts = models.read_positions(bytes(dec_), shape, models._shape_lanes(rec_, shape, bytes(dec_)))
            zs = [p[2] for p in pts if 0.0 < p[1] < 10.0 and abs(p[0]) < 25.0]
            return max(zs) - min(zs)
        # c27's average belly (about 43.9 cm deep) takes c26's heavy one (about 50 cm), within a centimetre
        self.assertGreater(belly(rec, decoded), belly(rec27, dec27) + 4.0)
        self.assertAlmostEqual(belly(rec, decoded), belly(rec26, dec26), delta=1.0)
        self.assertIn("geometry", detail["textures"])


@unittest.skipUnless(HAVE_RETAIL, "retail USA image not present (NFL2K5_RETAIL_XISO)")
class RetailMovedCoaches(unittest.TestCase):
    """b780 c3-looks on the user's retail disc (read only): three moved coaches compile to their own look in the new
    club's apparel, the same bytes from the retail or the 2026 scene, recognised by their content."""

    @classmethod
    def setUpClass(cls):
        cls.pins = mc.pins()
        cls.rows = {r["team"]: r for r in cls.pins["teams"]}
        cls.compiled = {}
        with mc._outer_image()(RETAIL) as archive:
            entries = {e.name_id: e for e in archive.entries}
            for coach, host in MOVES.items():
                row = cls.rows[coach]
                entry = entries[mc.name_id(row["archive"])]
                raw = archive.read(entry.virtual_offset, entry.size)
                span = raw[row["span_offset"]:row["span_offset"] + row["span_size"]]
                rec, base, _detail = mc.compose_scene(raw, row)
                after, detail = mc.compile_moved(span, base, rec, row, cls.rows[host])
                cls.compiled[coach] = dict(raw=raw, span=span, after=after, detail=detail, rec=rec, base=base)

    def test_a_moved_coach_keeps_his_look_and_wears_the_new_club_apparel(self):
        for coach, host in MOVES.items():
            with self.subTest(coach=coach, host=host):
                row, c = self.rows[coach], self.compiled[coach]
                after = c["after"]
                self.assertEqual(len(after), len(c["span"]))
                self.assertEqual(after[:0x20], c["span"][:0x20])                  # wrapper identical
                self.assertNotIn(mc.sha(after), (row["retail_sha256"], row["applied_sha256"]))
                fit = c["detail"]["fit"]
                self.assertLessEqual(fit["scratch_needed"], fit["scratch_retail"])
                self.assertIn(c["detail"]["apparel_palette"], [s for s in mc.PALETTE_LADDER if s <= row["palette_max"]])
                rec, decoded = mc.decode_span(after)
                regions = mc.apparel_regions(rec)
                self.assertEqual(mc.scene_digest(decoded, regions), row["scene_sha256"])     # his own look
                self.assertEqual(mc.apparel_digest(decoded, regions),
                                 self.rows[host]["apparel_sha256"][str(c["detail"]["apparel_palette"])])
                self.assertEqual(mc.dressed_by(after, row, self.pins), host)
                # only the three apparel allocations differ from his own 2026 scene
                home = bytes(c["base"])
                changed = [i for i, (a, b) in enumerate(zip(home, decoded)) if a != b]
                self.assertTrue(changed)
                self.assertTrue(all(any(lo <= i < hi for lo, hi in regions) for i in changed))

    def test_the_states_of_a_moved_look(self):
        coach, host = "KC", "LV"
        row, c = self.rows[coach], self.compiled[coach]
        dress, own = self.rows[host], self.rows[coach]
        self.assertEqual(mc._coach_state(c["after"], row, dress, self.pins), "applied")
        self.assertEqual(mc._coach_state(c["after"], row, self.rows["DAL"], self.pins), "moved")
        self.assertEqual(mc._coach_state(c["after"], row, own, self.pins), "moved")         # back home: rewrite
        self.assertEqual(mc._coach_state(c["span"], row, dress, self.pins), "retail")
        compiled, _detail = mc.compile_archive(c["raw"], row)
        home = compiled[row["span_offset"]:row["span_offset"] + row["span_size"]]
        self.assertEqual(mc._coach_state(home, row, dress, self.pins), "home")
        self.assertEqual(mc._coach_state(home, row, own, self.pins), "applied")
        junk = bytearray(c["after"]); junk[0x40:0x80] = bytes(0x40)
        self.assertEqual(mc._coach_state(bytes(junk), row, dress, self.pins), "foreign")
        self.assertIsNone(mc.dressed_by(c["after"], self.rows["LV"], self.pins))          # not Kubiak's look

    def test_the_moved_look_is_the_same_bytes_from_the_2026_scene_and_goes_home_to_its_pin(self):
        coach, host = "WAS", "DAL"
        row, c = self.rows[coach], self.compiled[coach]
        compiled, _detail = mc.compile_archive(c["raw"], row)
        home = compiled[row["span_offset"]:row["span_offset"] + row["span_size"]]
        self.assertEqual(mc.sha(home), row["applied_sha256"])
        rec, decoded = mc.decode_span(home)
        again, detail = mc.compile_moved(home, decoded, rec, row, self.rows[host])
        self.assertEqual(again, c["after"])
        rec2, decoded2 = mc.decode_span(c["after"])
        back, detail2 = mc.compile_moved(c["after"], decoded2, rec2, row, row)
        self.assertEqual(mc.sha(back), row["applied_sha256"])
        self.assertEqual(detail2["apparel_palette"], row["palette_max"])
        with self.assertRaises(mc.ModernCoachesError):          # another coach's scene is refused
            mc.compile_moved(home, decoded, rec, self.rows["DAL"], self.rows[host])

    def test_the_staff_states_on_the_retail_disc(self):
        staff = {"LV": "KC", "KC": "LV", "SF": "HOU", "HOU": "SF", "DAL": "WAS", "WAS": "DAL"}
        with mc._outer_image()(RETAIL) as archive:
            parts = mc._parts(archive, self.pins, staff)
            base_parts = mc._parts(archive, self.pins)
        coach = {p["team"]: p for p in parts if p["kind"] == "coach"}
        for c_, h in staff.items():
            self.assertEqual((coach[h]["host"], coach[h]["state"]), (c_, "retail"))
        bodies = {p["team"]: (p["coach"], p["value"], p["state"], int(p["row"]["body_code"]))
                  for p in parts if p["kind"] == "body_id"}
        # the retail roster still names each club's own 2004 model: the club leading a moved coach gets his model
        self.assertEqual(bodies["LV"], ("KC", 20, "retail", 21))
        self.assertEqual(bodies["KC"], ("LV", 13, "retail", 20))
        self.assertEqual(bodies["SF"], ("HOU", 25, "retail", 5))
        self.assertEqual(bodies["HOU"], ("SF", 37, "retail", 25))
        self.assertEqual(bodies["DAL"], ("WAS", 7, "retail", 29))
        self.assertEqual(bodies["WAS"], ("DAL", 29, "retail", 7))
        photos = {p["team"]: (p["coach"], p["value"], p["state"]) for p in parts if p["kind"] == "photo_id"}
        # Schottenheimer's reserved picture goes to the club he leads; that record still holds Washington's retail
        # picture on an unmoved roster, so it is left alone (the coaching staff step moves the record first)
        self.assertEqual(photos, {"WAS": ("DAL", 7029, "kept"), "DAL": ("WAS", 7007, "kept")})
        # nobody moved: the parts are those of the 2026 coaches as before (body ids of the 17 clubs on other models)
        self.assertEqual({p["team"] for p in base_parts if p["kind"] == "body_id"}, set(MOVED))
        self.assertEqual({(p["team"], p["coach"]) for p in base_parts if p["kind"] == "photo_id"},
                         {("DAL", "DAL"), ("WAS", "WAS")})
        self.assertEqual({p["state"] for p in base_parts if p["kind"] == "coach"}, {"retail"})


    def test_the_tightest_of_the_992_moves_still_fits(self):
        """b780 c3-looks swept every single move (32 coaches x 31 clubs) on the retail disc: all fit, and Liam Coen's c30
        in the Ravens' purple is the only one that needs the ladder's last step (64 colours for the apparel). A change to
        either art that makes it fail would refuse that move in a build: this test says so first."""
        row, host = self.rows["JAX"], self.rows["BAL"]
        with mc._outer_image()(RETAIL) as archive:
            entry = {e.name_id: e for e in archive.entries}[mc.name_id(row["archive"])]
            raw = archive.read(entry.virtual_offset, entry.size)
        rec, base, _detail = mc.compose_scene(raw, row)
        after, detail = mc.compile_moved(raw[row["span_offset"]:row["span_offset"] + row["span_size"]], base, rec, row, host)
        self.assertIn(detail["apparel_palette"], mc.PALETTE_LADDER)    # 64 today: the last step
        self.assertEqual(mc.dressed_by(after, row, self.pins), "BAL")

    def test_a_created_coach_standing_on_a_2026_model_is_noted_not_written(self):
        """A club led by a coach who is not one of the 32 keeps the model its record names; when that model is a 2026
        coach's (here the retail Kansas City record still names c13, Mike Macdonald's), the receipt says so."""
        with mc._outer_image()(RETAIL) as archive:
            parts = mc._parts(archive, self.pins, {"LV": "KC", "KC": None})
        shared = [(p["team"], p["coach"], p["value"], p["state"]) for p in parts if p["kind"] == "shared_model"]
        self.assertEqual(shared, [("KC", "SEA", 13, "kept")])
        self.assertNotIn("KC", {p["team"] for p in parts if p["kind"] == "body_id"})
        self.assertEqual({p["team"]: p["host"] for p in parts if p["kind"] == "coach"}["KC"], "LV")


@unittest.skipUnless(HAVE_RETAIL and HAVE_V08, "retail and v0.8 images not present (NFL2K5_V08_XISO)")
class ReleasedV08MovedCoaches(unittest.TestCase):
    """b780 c3-looks on the released v0.8 disc (read only): its coaches read applied with no staff; a staff asks the
    moved models to be rebuilt from the 2026 scenes on the disc, without the retail image."""

    def test_v08_reads_applied_and_a_swap_compiles_from_the_disc(self):
        pins = mc.pins()
        rows = {r["team"]: r for r in pins["teams"]}
        states = mc.resource_states(V08)
        self.assertEqual({v for k, v in states.items() if k.startswith("coach:")}, {"applied"})
        self.assertEqual(states["photo_id:DAL"], "applied")
        staff = {"LV": "KC", "KC": "LV"}
        with mc._outer_image()(V08) as archive:
            parts = mc._parts(archive, pins, staff)
            entries = {e.name_id: e for e in archive.entries}
            moved = [p for p in parts if p["kind"] == "coach" and p["host"] != p["team"]]
            self.assertEqual(sorted((p["team"], p["host"], p["state"]) for p in moved),
                             [("KC", "LV", "home"), ("LV", "KC", "home")])
            for part in moved:
                before, after, detail = mc._coach_plan(archive, entries, part, None)
                self.assertEqual(mc.dressed_by(after, part["row"], pins), part["host"])
                self.assertEqual(detail["source"], "home")
        with mc._outer_image()(RETAIL) as archive:
            entries = {e.name_id: e for e in archive.entries}
            row = rows["KC"]
            entry = entries[mc.name_id(row["archive"])]
            raw = archive.read(entry.virtual_offset, entry.size)
            rec, base, _detail = mc.compose_scene(raw, row)
            from_retail, _d = mc.compile_moved(raw[row["span_offset"]:row["span_offset"] + row["span_size"]], base,
                                               rec, row, rows["LV"])
        kc = [p for p in moved if p["team"] == "KC"][0]
        with mc._outer_image()(V08) as archive:
            entries = {e.name_id: e for e in archive.entries}
            _before, from_disc, _detail = mc._coach_plan(archive, entries, kc, None)
        self.assertEqual(from_disc, from_retail)


@unittest.skipUnless(HAVE_RETAIL and HAVE_V061, "retail and v0.6.1 images not present (NFL2K5_V061_XISO)")
class ReleasedDisc(unittest.TestCase):
    def test_the_v061_coaches_read_previous_and_plan_back_to_the_new_models(self):
        """b778 cm2 on the released v0.6.1 disc (read only): the moved clubs' earlier art and body ids read
        ``previous``, c06 and c11 (no club's model now) read ``previous`` and plan back to retail, c33 and c36 are
        still retail; the plan writes nothing but these parts."""
        states = mc.resource_states(V061)
        for team in ("TB", "PIT", "CLE", "JAX"):
            self.assertEqual(states[f"coach:{team}"], "previous", team)
        self.assertEqual((states["coach:CIN"], states["coach:IND"]), ("retail", "retail"))
        self.assertEqual((states["body_id:PIT"], states["body_id:CLE"]), ("previous", "previous"))
        self.assertEqual((states["body_id:TB"], states["body_id:CIN"], states["body_id:IND"]),
                         ("retail", "retail", "retail"))
        self.assertEqual((states["retired:c06.iff"], states["retired:c11.iff"]), ("previous", "previous"))
        with self.assertRaises(mc.ModernCoachesError):
            mc.plan_image(V061)                               # earlier art needs the user's retail image
        plan, rows = mc.plan_image(V061, retail=RETAIL)
        written = sorted(f"{r['kind']}:{r['team']}" for r in rows if r.get("written"))
        scanned = {p.stem for p in (ROOT / "tools" / "b77" / "cf1_recipes").glob("*.json")}   # b778 cf1 and its follow-ups
        coaches = {"TB", "PIT", "CLE", "CIN", "IND", "JAX"} | scanned
        self.assertEqual(written, sorted([f"coach:{t}" for t in coaches]
                                         + ["body_id:TB", "body_id:PIT", "body_id:CLE", "body_id:CIN", "body_id:IND",
                                            "retired:c06.iff", "retired:c11.iff"]))
        bodies = {r["team"]: (r["body_before"], r["body_after"]) for r in rows if r["kind"] == "body_id" and r.get("written")}
        self.assertEqual(bodies, {"TB": (27, 0), "PIT": (26, 27), "CLE": (0, 26), "CIN": (6, 36), "IND": (11, 33)})
        self.assertEqual(len(plan), len(written))

    def test_portraits_reproduce_their_pins_and_the_roster_names_retail_ids(self):
        with mc._outer_image()(RETAIL) as archive:
            for row in mc.pins()["portraits"]:
                at = archive.entries[row["outer_index"]].virtual_offset + row["chunk_offset"]
                span = archive.read(at, row["span_size"])
                self.assertEqual(mc.sha(span), row["retail_sha256"])
                after = mc.fallback_portrait_span(archive, span)
                self.assertEqual(mc.sha(after), row["applied_sha256"])
                self.assertEqual(after[:0x20 + 128], span[:0x20 + 128])
                _site, value = mc._coach_photo_site(archive, row["team"])
                self.assertEqual(value, row["retail_photo_id"])

    def test_external_picture_is_kept_and_rejected_render_is_removed(self):
        import numpy as np
        with mc._outer_image()(RETAIL) as archive:
            for row in mc.pins()["portraits"]:
                at = archive.entries[row["outer_index"]].virtual_offset + row["chunk_offset"]
                span = archive.read(at, row["span_size"])
                self.assertEqual(mc.portrait_state(span, row), "retail")
                fallback = mc.fallback_portrait_span(archive, span)
                self.assertEqual(mc.portrait_state(fallback, row), "applied")
                rgba = np.zeros((128, 128, 4), np.uint8)
                rgba[..., 0], rgba[..., 3] = 200, 255
                external = mc.portrait_span(span, rgba)
                self.assertEqual(mc.portrait_state(external, row), "kept")
                rejected = dict(row, rejected_sha256=[mc.sha(external)])
                self.assertEqual(mc.portrait_state(external, rejected), "previous")
                self.assertEqual(mc.fallback_portrait_span(archive, external), fallback)



if __name__ == "__main__":
    unittest.main()
