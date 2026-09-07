"""Standalone broadcast comparison, native material binding and subset checks."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]
from mod_editor.core import nfl2k5_scorebug_exact as exact
from mod_editor.core import nfl2k5_scorebug_ingame as r, nfl2k5_scorebug_resources as art
from test_nfl2k5_scorebug_runtime import XBE, PACK, HAVE_UC
import nfl2k5_scorebug_projection as projection

HAVE_IMAGES = all(importlib.util.find_spec(name) for name in ("PIL", "numpy"))


class ContractTests(unittest.TestCase):
    def test_all_32_team_wordmarks_and_runtime_default_off(self):
        self.assertEqual(set(exact.NICKNAMES), set(art.TEAM_LOGOS))
        self.assertEqual(art.PROBES, ("transport", "hooks", "resources", "neutral", "pair", "full"))
        from mod_editor.core import mod_build
        self.assertFalse(mod_build.BuildPlan(source="unused", target="unused").scorebug_runtime)
        for name, preset in mod_build.PRESETS.items():
            self.assertFalse(preset.get("scorebug_runtime", False), name)

    @unittest.skipUnless(HAVE_IMAGES, "Pillow and numpy required for authored atlas")
    def test_authored_capitals_and_neutral_timeout_variants_are_portable(self):
        for team, name in exact.NICKNAMES.items():
            mark = exact.wordmark(name)
            self.assertEqual(mark.height, 7)
            self.assertIsNotNone(mark.getbbox(), team)
        for side in ("home", "away"):
            previous = None
            for count in range(4):
                panel = exact.panel(b"", None, side, timeouts=count)
                if previous is not None:
                    from PIL import ImageChops
                    box = ImageChops.difference(previous, panel).convert("RGB").getbbox()
                    self.assertIsNotNone(box)
                    self.assertGreaterEqual(box[1], 27)
                    self.assertLessEqual(box[3], 30)
                previous = panel
        with self.assertRaises(ValueError): exact.panel(b"", None, "home", timeouts=True)

    @unittest.skipUnless(HAVE_IMAGES, "Pillow and numpy required for reference measurement")
    def test_reference_identity_and_active_viewport_transform(self):
        from nfl2k5_scorebug_exact import REFERENCE, reference, reference_text_boxes
        if not REFERENCE.is_file(): self.skipTest("real LV/HOU reference JPEG absent")
        source, normalized = reference()
        self.assertEqual(source.size, (1920, 1080))
        self.assertEqual(normalized.size, (640, 480))
        self.assertLess(exact.RAILS[3], 464)
        self.assertGreater(1054 * 480 / 1080, 464)  # Naive 480 fit would clip.
        text = reference_text_boxes(source)
        self.assertGreater(text["0xfc070"][3] - text["0xfc070"][1], 22)
        self.assertLess(text["0xfbe30"][2] - text["0xfbe30"][0], 11)
        self.assertAlmostEqual(text["0xfc090"][2] - text["0xfc090"][0], 9)
        self.assertAlmostEqual(text["0xfc090"][3] - text["0xfc090"][1], 17*448/1080)

    @unittest.skipUnless(HAVE_IMAGES, "Pillow and numpy required for ink diagnostics")
    def test_rendered_ink_does_not_count_possession_or_clock_rim_as_text(self):
        import numpy as np
        from nfl2k5_scorebug_exact import rendered_text_ink
        pixels = np.zeros((480,640,3),dtype=np.uint8)
        pixels[412:414,385:389] = 255  # Marker fragment touching the score ROI.
        pixels[416:439,380:393] = 255
        self.assertEqual(rendered_text_ink(pixels,'0xfc050'),[380,416,393,439])
        pixels[:] = 255
        pixels[442:446,283:286] = 0  # Capsule edge touching the quarter ROI.
        pixels[435:442,288:296] = 0
        self.assertEqual(rendered_text_ink(pixels,'0xfc090'),[288,435,296,442])
        pixels[:] = 255
        self.assertIsNone(rendered_text_ink(pixels,'0xfc090'))


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC and HAVE_IMAGES,
                     "pinned USA XBE/pack, Unicorn, Pillow and numpy required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_scorebug_exact import Build, reference, reference_text_boxes
        cls.build = Build(PACK, XBE)
        cls.addClassCleanup(cls.build.close)
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.out = Path(cls.temp.name).resolve()
        source, cls.reference = reference()
        cls.text_boxes = reference_text_boxes(source)

    def test_runtime_scene_and_actual_native_materials_match_all_five_boundaries(self):
        from PIL import Image, ImageChops
        from nfl2k5_scorebug_exact import compare
        for wide in (False, True):
            pictures = []
            for mode in (0, 1):
                path = self.out / f"runtime-{wide}-{mode}.png"
                geometry = self.build.render(path, runtime=True, widescreen=wide, mode=mode)
                self.assertTrue(geometry["scorebug_runtime_installed"])
                self.assertEqual(projection.containment_failures(geometry, geometry["frame"], .02), {})
                materials = {m["name"]: m for m in geometry["materials"]}
                for name in ("hscore_buga", "zscore_buga"):
                    self.assertTrue(materials[name]["visible"])
                    self.assertNotEqual(materials[name]["texture"], "0x0")
                    self.assertNotEqual(materials[name]["texture"], materials["cscore_buga"]["texture"])
                self.assertNotEqual(materials["hscore_buga"]["texture"], materials["zscore_buga"]["texture"])
                for name, expected_name in (("hscore_buga", "sb37h3"), ("zscore_buga", "sb20a3")):
                    self.assertEqual(geometry["rendered_materials"][name]["name"], expected_name)
                    self.assertEqual(geometry["rendered_materials"][name]["dimensions"], [128, 32])
                for row in geometry["winding"].values(): self.assertEqual(row["positive"], 0)
                with Image.open(path) as image: pictures.append(image.convert("RGB"))
                if not wide:
                    score = compare(self.reference, pictures[-1], geometry, self.text_boxes, runtime=True)
                    for name, region in score["regions"].items():
                        self.assertLess(region["native_boundary_error_px"], .01, name)
            self.assertIsNone(ImageChops.difference(pictures[0], pictures[1]).getbbox())

    def test_live_timeouts_change_only_the_selected_runtime_panel(self):
        from PIL import Image, ImageChops
        first = self.out / "three.png"
        second = self.out / "one.png"
        before = self.build.render(first, runtime=True, timeouts=(3, 3))
        after = self.build.render(second, runtime=True, timeouts=(3, 1))
        self.assertEqual(before["positions"], after["positions"])
        with Image.open(first) as a, Image.open(second) as b:
            changed = ImageChops.difference(a, b).getbbox()
        self.assertIsNotNone(changed)
        expected = exact.hud_box(exact.SOURCE_REGIONS["left_panel"])
        self.assertGreaterEqual(changed[0], int(expected[0]))
        self.assertLessEqual(changed[2], int(expected[2]) + 1)
        self.assertGreaterEqual(changed[1], 440)

    def test_comparator_reports_pixel_mismatches_even_when_geometry_is_exact(self):
        from PIL import ImageDraw
        from nfl2k5_scorebug_exact import compare
        path = self.out / "static.png"
        geometry = self.build.render(path)
        perfect = compare(self.reference, self.reference, geometry, self.text_boxes)
        for row in perfect["regions"].values(): self.assertEqual(row["rgb_mae"], 0)
        bad = self.reference.copy()
        ImageDraw.Draw(bad).rectangle((280, 430, 359, 448), fill="magenta")
        changed = compare(self.reference, bad, geometry, self.text_boxes)
        self.assertGreater(changed["regions"]["clock_strip"]["rgb_mae"], 70)
        self.assertFalse(changed["exact_match"])
        self.assertLess(changed["regions"]["frame_rim"]["native_boundary_error_px"], .01)
        # Static FONT4 needs a wider row; the comparator must report that
        # real deviation from the photograph, not substitute its new target.
        self.assertGreater(changed["regions"]["clock_strip"]["native_boundary_error_px"], 15)

    def test_current_compiler_and_every_probe_identity_are_reproducible(self):
        from nfl2k5_scorebug_exact import compiler_pins
        pins = compiler_pins(self.build)
        for name, value in pins.items(): self.assertEqual(getattr(art, name), value, name)
        for probe in art.PROBES:
            compiled, receipt = art.compile_runtime_collection(self.build.view, probe=probe)
            self.assertEqual(art.runtime_pack_status(compiled, probe=probe), "applied")
            self.assertEqual(receipt["version"], art.RUNTIME_VERSION)
            self.assertEqual(receipt["texture_count"], art.probe_sizes(probe)[0])


if __name__ == "__main__": unittest.main()
