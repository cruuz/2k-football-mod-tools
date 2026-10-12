"""2026 head coaches (beta 77 co1, co2): the pins and the shipped art, the coach bodies, the Build wiring, and, when a
retail USA image is present, the real compile of coach scenes (Reid's derived head included), the body ids and the two
portrait slots against their pins.

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

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
HAVE_RETAIL = RETAIL.is_file()
TEAMS = {"ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
         "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"}
SIZES = {"shirt": (128, 128), "jacket": (128, 128), "logo": (64, 64), "accessories": (128, 64), "head": (256, 128),
         "head_mask": (256, 128), "head_overlay": (256, 128), "sideline_dry": (256, 256), "sideline_rain": (256, 256)}
# co2: the club whose coach wears another retail body, and the body (cNN) he wears
MOVED = {"ARI": "12", "CAR": "09", "CHI": "37", "CLE": "00", "DET": "04", "HOU": "05", "JAX": "30", "KC": "21",
         "NYG": "22", "PHI": "18", "PIT": "26", "SEA": "13"}


class PinsAndArt(unittest.TestCase):
    def test_pins_name_every_club_once_and_the_two_portraits(self):
        pins = mc.pins()
        self.assertEqual({r["team"] for r in pins["teams"]}, TEAMS)
        self.assertEqual(len({r["archive"] for r in pins["teams"]}), 32)
        self.assertEqual({r["archive"] for r in pins["teams"]},
                         {f"c{i:02d}.iff" for i in range(31)} | {"c37.iff"})
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

    def test_the_bodies_are_one_model_per_club(self):
        pins = mc.pins()
        self.assertEqual(sorted(r["body_code"] for r in pins["teams"]),
                         sorted([f"{i:02d}" for i in range(31)] + ["37"]))
        self.assertEqual(set(pins["bodies"]), TEAMS)
        good = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
        bad = json.loads(json.dumps(good))
        bad["teams"][0]["body_code"] = bad["teams"][1]["body_code"]
        bad["teams"][0]["archive"] = bad["teams"][1]["archive"]
        with self.assertRaises(mc.ModernCoachesError):
            mc._check_pins(bad)

    def test_the_shipped_art_matches_its_pins_and_sizes(self):
        self.assertTrue(mc.available())
        from PIL import Image
        for row in mc.pins()["teams"]:
            for name, digest in row["art"].items():
                path = mc.art_path(row["team"], name)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
                with Image.open(path) as image:
                    self.assertEqual(image.size, SIZES[name], f"{row['team']} {name}")
        for row in mc.pins()["portraits"]:
            with Image.open(mc.DATA_DIR / row["png"]) as image:
                self.assertEqual(image.size, (128, 128))

    def test_only_authored_textures_ship(self):
        """No reference photo or anything but the authored PNGs, the pins and the README in the data folder."""
        allowed = {"pins.json", "README.md"}
        for path in mc.DATA_DIR.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(mc.DATA_DIR).as_posix()
            if rel in allowed:
                continue
            self.assertTrue(rel.endswith(".png"), rel)
            team, name = rel.split("/")
            if team == "portraits":
                self.assertIn(name, {"7031.png", "7034.png"})
            elif name[:-4] in mc.HEAD_RECIPE_FILES:
                self.assertEqual(team, "KC")
            else:
                self.assertIn(team, TEAMS)
                self.assertIn(name[:-4], SIZES)

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
            for team in ("KC", "DAL", "PIT"):     # Reid's derived head on c21, an unmoved club, a moved one
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

    def test_glasses_hidden_only_where_the_2026_coach_wears_none(self):
        pins = {r["team"]: r for r in mc.pins()["teams"]}
        self.assertEqual(sorted(t for t, r in pins.items() if r["hide_glasses"]), ["GB", "LAR", "PIT", "SEA", "WAS"])
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
        self.assertEqual(set(parts.values()), {"retail"})
        self.assertTrue(all(row["superseded_sha256"] for row in pins["teams"]))

    def test_portraits_reproduce_their_pins_and_the_roster_names_retail_ids(self):
        with mc._outer_image()(RETAIL) as archive:
            for row in mc.pins()["portraits"]:
                at = archive.entries[row["outer_index"]].virtual_offset + row["chunk_offset"]
                span = archive.read(at, row["span_size"])
                self.assertEqual(mc.sha(span), row["retail_sha256"])
                after = mc.portrait_span(span, mc._rgba(mc.DATA_DIR / row["png"], 128, 128))
                self.assertEqual(mc.sha(after), row["applied_sha256"])
                self.assertEqual(after[:0x20 + 128], span[:0x20 + 128])
                _site, value = mc._coach_photo_site(archive, row["team"])
                self.assertEqual(value, row["retail_photo_id"])


if __name__ == "__main__":
    unittest.main()
