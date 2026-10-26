"""2026 head coaches (beta 77 co1, co2, co3, cm1; b778 cm2): the pins and the shipped art, the coach bodies, the authored coach
geometry (cm1: Quinn's bald head, seven lean bodies), the Build wiring, and, when a retail USA image is present, the real
compile of coach scenes (Reid's derived head and the geometry included), the body ids and the two portrait slots
against their pins.

The always-on tests read only the repository. The retail checks read the user's own disc image and skip without it
(point NFL2K5_RETAIL_XISO at the retail USA .xiso.iso).
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

    def test_kansas_city_wears_the_2004_reid_model_with_a_derived_head(self):
        """Noah 2026-10-12: use the existing Andy Reid model for the Chiefs' Andy Reid."""
        kc = {r["team"]: r for r in mc.pins()["teams"]}["KC"]
        self.assertEqual((kc["archive"], kc["team_code"]), ("c21.iff", "13"))
        self.assertEqual(kc["head_recipe"]["kind"], "retail_recolour")
        self.assertNotIn("head", kc["art"])
        self.assertFalse(mc.art_path("KC", "head").exists())
        self.assertEqual(set(mc.HEAD_RECIPE_FILES) & set(kc["art"]), set(mc.HEAD_RECIPE_FILES))

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
        for needle in ("coaches.apply_to_image(target, progress=progress)", '"step": "modern_coaches"',
                       "coaches.image_status(source)"):
            self.assertIn(needle, source)
        # after every roster writer and relocating pass: the coach step follows the goalposts step
        self.assertLess(source.index('"step": "modern_goalposts"'), source.index('"step": "modern_coaches"'))
        panel = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        for needle in ('"modern_coaches": self.modern_coaches_check', "modern_coaches=self._modern_coaches_changed()",
                       "def _modern_coaches_changed(self)"):
            self.assertIn(needle, panel)


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
