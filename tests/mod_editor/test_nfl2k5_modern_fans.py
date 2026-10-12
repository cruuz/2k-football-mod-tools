"""2026 fans (beta 77 fr1): the pins and the shipped art, the Build wiring, and, when a retail USA image is present,
the real compile of crowd textures against their pins.

The always-on tests read only the repository. The retail checks read the user's own disc image and skip without it
(point NFL2K5_RETAIL_XISO at the retail USA .xiso.iso).
"""
from __future__ import annotations

import collections
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
from mod_editor.core import nfl2k5_modern_fans as mf  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))
HAVE_RETAIL = RETAIL.is_file()
TEAMS = {"ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
         "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"}
SIZES = {"tshirt": (256, 128), "sweatshirt": (256, 128), "jersey": (256, 128), "varsity": (256, 128),
         "puffyjacket": (256, 128), "hardhat": (128, 64), "boxlogo": (64, 64), "crowdsign": (128, 128),
         "foamfinger": (128, 64), "fanplate": (128, 128)}
LETTERS = {f"noshirtns{i:02d}" for i in range(1, 9)}
# face paints that carried a retired or outdated mark
FACEPAINT = {("WAS", "head01"), ("WAS", "head03"), ("DET", "head03"), ("MIA", "head03"), ("NYJ", "head03"),
             ("SEA", "head01")}
SCENE_ART = {"crowds13_y_hats29_feathers.png", "crowds13_z_hats29_headdress.png", "crowds29_y_hats29_feathers.png",
             "crowds29_z_hats29_headdress.png", "crowddrink_drinkleft.png"}
# every set a name lives in (one picture per club and name, written into each copy)
COPIES = {"tshirt": {"A", "B", "ns", "tg"}, "hardhat": {"A", "B", "ns", "tg"}, "jersey": {"A", "B"},
          "sweatshirt": {"A", "B"}, "varsity": {"A", "B"}, "puffyjacket": {"B", "ns", "tg"}, "boxlogo": {"ns"},
          "crowdsign": {"ns"}, "foamfinger": {"ns"}, "fanplate": {"tg"}}


class PinsAndArt(unittest.TestCase):
    def test_pins_name_every_club_and_every_set_copy(self):
        pins = mf.pins()
        by = collections.defaultdict(set)
        for p in pins["parts"]:
            by[(p["team"], p["name"])].add(p["set"])
            self.assertNotEqual(p["retail_sha256"], p["applied_sha256"])
            self.assertIn(p["palette_max"], mf.PALETTE_LADDER)
            self.assertLessEqual(p["fit"]["scratch_needed"], p["fit"]["scratch_retail"])
            self.assertEqual(p["fit"]["stored_size"] + 0x20, p["span_size"])
            self.assertEqual(int(p["outer_index"]) - mf.SETS[p["set"]], pins_order().index(p["code"]))
        self.assertEqual({t for t, _n in by}, TEAMS)
        for team in TEAMS:
            for name, sets in COPIES.items():
                self.assertEqual(by[(team, name)], sets, f"{team} {name}")
        letters = {t for t, n in by if n in LETTERS}
        self.assertEqual(letters, {"WAS", "LAR", "SEA", "LAC"})
        self.assertEqual({(t, n) for t, n in by if n.startswith("head")}, FACEPAINT)
        for key in FACEPAINT:
            self.assertEqual(by[key], {"A", "B", "ns", "tg"})

    def test_the_shipped_art_matches_its_pins_and_sizes(self):
        self.assertTrue(mf.available())
        from PIL import Image
        for p in mf.pins()["parts"]:
            path = mf.art_path(p)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), p["art_sha256"])
            with Image.open(path) as image:
                self.assertEqual(image.size, (p["width"], p["height"]))
                expected = (128, 128) if p["name"].startswith("head") else SIZES.get(p["name"], (64, 64))
                self.assertEqual(image.size, expected, f"{p['team']} {p['name']}")

    def test_only_authored_textures_ship(self):
        allowed = {"pins.json", "README.md"}
        for path in mf.DATA_DIR.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(mf.DATA_DIR).as_posix()
            if rel in allowed:
                continue
            self.assertTrue(rel.endswith(".png"), rel)
            team, name = rel.split("/")
            if team == "scenes":
                self.assertIn(name, SCENE_ART)
                continue
            self.assertIn(team, TEAMS)
            self.assertTrue(name[:-4] in set(SIZES) | LETTERS or (team, name[:-4]) in FACEPAINT, rel)

    def test_retail_details_ship_as_flat_grey_and_paint_as_a_layer(self):
        """No retail pixel ships: the kept details are flat grey in the PNG (the Build takes them from the disc) and
        the face paints are a paint layer with clear hair, ears, eyes and mouth."""
        import numpy as np
        from PIL import Image
        for p in mf.pins()["parts"]:
            if p["set"] != "A":
                continue
            with Image.open(mf.art_path(p)) as image:
                rgba = np.asarray(image.convert("RGBA"))
            for x0, y0, x1, y1 in mf.KEEP_RECTS.get(p["name"], ()):
                self.assertTrue((rgba[y0:y1, x0:x1] == (128, 128, 128, 255)).all(), f"{p['team']} {p['name']}")
            if p["name"].startswith(mf.OVERLAY_PREFIX):
                self.assertEqual(int(rgba[:20, :, 3].max()), 0)          # hair and the top of the head are the disc's
                self.assertGreater(int(rgba[70, 64, 3]), 200)             # the painted face
                self.assertEqual(int(rgba[64, 52, 3]), 0)                 # an eye stays bare
        retail = np.full((4, 4, 4), 7, np.uint8)
        art = np.zeros((4, 4, 4), np.uint8)
        art[..., 3] = 255
        self.assertTrue((mf.compose("jersey", art, lambda: retail) == art).all())
        half = art.copy()
        half[..., :3] = 207
        half[..., 3] = 128
        mixed = mf.compose("head01", half, lambda: retail)
        self.assertEqual(int(mixed[0, 0, 0]), round(207 * 128 / 255 + 7 * (1 - 128 / 255)))
        self.assertEqual(int(mixed[0, 0, 3]), 7)

    def test_ns_and_tg_sets_are_the_named_archives(self):
        mm = mf._mm()
        for p in mf.pins()["parts"]:
            if p["set"] in ("ns", "tg"):
                self.assertEqual(int(p["outer_id"], 16), mm.name_id(f"{p['set']}{p['code']:02d}.iff"))

    def test_malformed_pins_are_refused(self):
        with self.assertRaises(mf.ModernFansError):
            mf._check_pins({"schema": "other"})
        good = json.loads(mf.PINS_PATH.read_text(encoding="utf-8"))
        bad = dict(good, parts=[p for p in good["parts"] if p["team"] != "GB"])
        with self.assertRaises(mf.ModernFansError):
            mf._check_pins(bad)
        twice = dict(good, parts=good["parts"] + good["parts"][:1])
        with self.assertRaises(mf.ModernFansError):
            mf._check_pins(twice)


def pins_order():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fr1_record_pins", ROOT / "tools/b77/fr1_record_pins.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ORDER


class BuildWiring(unittest.TestCase):
    def test_plan_presets_availability_and_settings(self):
        plan = mod_build.BuildPlan("s", "t")
        self.assertIs(plan.modern_fans, False)
        self.assertIn("modern_fans", plan.to_recipe())
        for name, values in mod_build.PRESETS.items():
            with self.subTest(preset=name):
                self.assertIs(values["modern_fans"], name == "softdrink_experimental")
        self.assertTrue(mod_build.availability()["modern_fans"])
        self.assertIn("modern_fans", build_settings.FEATURE_KEYS)
        saved = build_settings.build_settings({"modern_fans": True})
        self.assertIs(build_settings.to_plan(saved, "s", "t").modern_fans, True)
        self.assertEqual((mf.DEFAULT_ENABLED, mf.CAVES, mf.REQUESTS, mf.RUNTIME_GLOBALS, mf.LABEL),
                         (False, (), (), (), "EXPERIMENTAL / UNWITNESSED"))

    def test_refusals_before_any_copy(self):
        import tempfile
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        with tempfile.TemporaryDirectory(prefix="fans-plan-") as raw:
            root = Path(raw)
            xbe = root / "default.xbe"
            xbe.write_bytes(_build_synthetic_xbe())
            with self.assertRaisesRegex(ValueError, "needs? a disc image"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out.xbe"), modern_fans=True))
            with self.assertRaisesRegex(ValueError, "must be Off or On"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out2.xbe"), modern_fans=1))
            self.assertEqual(mod_build.inspect(xbe)["modern_fans"], "needs_image")
            self.assertFalse((root / "out.xbe").exists())

    def test_the_build_step_and_panel_name_the_option(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        for needle in ("fans.apply_to_image(target, progress=progress)", '"step": "modern_fans"',
                       "fans.image_status(source)"):
            self.assertIn(needle, source)
        self.assertLess(source.index('"step": "modern_coaches"'), source.index('"step": "modern_fans"'))
        panel = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        for needle in ('"modern_fans": self.modern_fans_check', "modern_fans=self._modern_fans_changed()",
                       "def _modern_fans_changed(self)"):
            self.assertIn(needle, panel)


@unittest.skipUnless(HAVE_RETAIL, "retail USA image not present (NFL2K5_RETAIL_XISO)")
class RetailCompile(unittest.TestCase):
    def test_retail_image_reads_retail(self):
        self.assertEqual(mf.image_status(RETAIL), "retail")

    def test_compile_reproduces_the_applied_pins(self):
        """One club's whole set (every name, every copy), plus the parts on the deepest palette rungs."""
        parts = mf.pins()["parts"]
        chosen = [p for p in parts if p["team"] == "WAS"]
        deepest = sorted(parts, key=lambda p: p["palette_max"])[:3]
        chosen += [p for p in deepest if p not in chosen]
        with mf._outer_image()(RETAIL) as archive:
            entries = {e.name_id: e for e in archive.entries}
            cache: dict = {}
            for p in chosen:
                at, span = mf._locate(archive, entries, p, cache)
                self.assertEqual(mf.sha(span), p["retail_sha256"])
                after, detail = mf.compile_part(span, p)
                self.assertEqual(mf.sha(after), p["applied_sha256"], f"{p['team']} {p['set']} {p['name']}")
                self.assertEqual(len(after), len(span))
                self.assertEqual(after[:0x20], span[:0x20])              # wrapper identical
                self.assertLessEqual(detail["fit"]["scratch_needed"], detail["fit"]["scratch_retail"])
                tx, _fill = mf._tools()
                chunk_a = tx.parse_chunks(after, allow_trailing=True)[0]
                chunk_r = tx.parse_chunks(span, allow_trailing=True)[0]
                dec_a, _ = tx.decode_chunk(after, chunk_a)
                dec_r, _ = tx.decode_chunk(span, chunk_r)
                self.assertEqual(dec_a[:chunk_a.system_bytes], dec_r[:chunk_r.system_bytes])  # header and name kept
                self.assertEqual(tx.parse_texture(dec_a, chunk_a).name, p["name"])

    def test_scene_pins_cover_every_copy_and_reproduce(self):
        scenes = mf.pins()["scenes"]
        self.assertEqual(sorted((s["scene"], s["outer_index"]) for s in scenes),
                         [("crowddrink", 2568), ("crowddrink", 2569), ("crowddrink", 2863), ("crowddrink", 2864),
                          ("crowds13", 2545), ("crowds13", 2840), ("crowds29", 2561), ("crowds29", 2856)])
        import numpy as np
        with mf._outer_image()(RETAIL) as archive:
            entries = {e.name_id: e for e in archive.entries}
            for pin in (scenes[0], [s for s in scenes if s["scene"] == "crowds29"][0]):
                _at, span = mf._locate_scene(archive, entries, pin, {})
                self.assertEqual(mf.sha(span), pin["retail_sha256"])
                after, detail = mf.compile_scene(span, pin)
                self.assertEqual(mf.sha(after), pin["applied_sha256"])
                self.assertEqual(after[:0x20], span[:0x20])
                self.assertLessEqual(detail["fit"]["scratch_needed"], detail["fit"]["scratch_retail"])
                if pin["scene"] == "crowds29":   # the headdress feathers are clear
                    tx, _fill = mf._tools()
                    rec, dec = mf._mm()._scene(after, tx.parse_chunks(after, allow_trailing=True)[0])
                    tex = [t for t in rec["embedded_textures"] if "y_hats29_feathers" in (t.get("mapped_material_names") or ())][0]
                    rgba, _ = mf._mm().read_p8(dec, int(rec["system_bytes"]), tex)
                    self.assertEqual(int(np.asarray(rgba)[..., 3].max()), 0)

    def test_the_other_textures_and_codes_are_not_owned(self):
        owned = {(p["outer_id"], p["chunk_index"]) for p in mf.pins()["parts"]}
        names = {p["name"] for p in mf.pins()["parts"]}
        self.assertFalse(names & {"head02", "head04", "head05", "head08", "48", "cementcolor", "chair"})
        self.assertEqual(len({p["outer_index"] for p in mf.pins()["parts"]}), 32 * 4)
        self.assertEqual(len(owned), len(mf.pins()["parts"]))


if __name__ == "__main__":
    unittest.main()
