"""MyCareer apartment hub art: native P8 constraints, layout safety, reproducibility.

The art under docs/mycareer_art is authored by docs/mycareer_art/build.py and
checked by tools/mycareer_art_check.py. These tests pin three things: the
checker's mip and palette code is the repo's own P8 approach (byte-identical
to nfl_tset_png_import), the shipped PNGs pass every native constraint from the
MyCareer asset request, and the renderer reproduces them exactly.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
HAVE_IMAGES = all(importlib.util.find_spec(name) for name in ("PIL", "numpy"))
ART = ROOT / "docs" / "mycareer_art"
CHECK = ROOT / "tools" / "mycareer_art_check.py"
BUILD = ART / "build.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAVE_IMAGES, "Pillow and numpy are required for the art checks")
class QuantizerParityTests(unittest.TestCase):
    """The checker reuses the repo's P8 approach; prove it byte for byte."""

    def setUp(self):
        import numpy as np
        self.np = np
        self.check = _load(CHECK, "mycareer_art_check")
        import nfl_tset_png_import as palettes
        self.palettes = palettes

    def test_box_mips_match_the_pinned_tset_chain(self):
        np = self.np
        rng = np.random.default_rng(7)
        width, height = self.palettes.BASE_WIDTH, self.palettes.BASE_HEIGHT
        arr = rng.integers(0, 256, size=(height, width, 4), dtype=np.uint8)
        reference = self.palettes.generate_mips(arr.tobytes(), width, height)
        ours = self.check.box_mips(arr, len(reference))
        self.assertEqual([(m.width, m.height) for m in ours], list(self.palettes.MIP_DIMENSIONS))
        for mine, theirs in zip(ours, reference):
            self.assertEqual(mine.rgba, theirs.rgba)

    def test_vectorised_mapping_matches_quantize_levels(self):
        np = self.np
        rng = np.random.default_rng(11)
        # A gradient with grain and a few flat colours: more than 256 colours,
        # ties included, so the lowest-index tie rule is actually exercised.
        yy, xx = np.mgrid[0:24, 0:24]
        arr = np.zeros((24, 24, 4), np.uint8)
        arr[..., 0] = np.clip(20 + yy * 9 + rng.integers(0, 3, (24, 24)), 0, 255)
        arr[..., 1] = np.clip(40 + xx * 8 + rng.integers(0, 3, (24, 24)), 0, 255)
        arr[..., 2] = np.clip(120 + (xx + yy) * 2, 0, 255)
        arr[..., 3] = np.where(xx < 4, 0, 255)
        arr[4:8, 4:8] = (255, 0, 0, 255)
        arr[10:12, 10:12] = (0, 255, 0, 128)
        levels = self.check.box_mips(arr, 3)
        palette, indices, stats = self.palettes.quantize_levels(levels, 256)
        fast_palette, fast_indices, fast_stats = self.check.quantize_chain(levels)
        self.assertEqual(fast_palette, palette)
        self.assertEqual(fast_indices, indices)
        for key in stats:
            self.assertEqual(fast_stats[key], stats[key], key)
        reference_palette, reference_indices, reference_stats = self.check.quantize_chain(levels, reference=True)
        self.assertEqual(reference_palette, palette)
        self.assertEqual(reference_indices, indices)
        self.assertEqual(reference_stats, fast_stats)
        self.assertGreater(stats["input_unique_rgba_colors"], 256)
        self.assertEqual(len(self.palettes.palette_bytes(palette)), 1024)


@unittest.skipUnless(HAVE_IMAGES, "Pillow and numpy are required for the art checks")
class ShippedArtTests(unittest.TestCase):
    def setUp(self):
        self.check = _load(CHECK, "mycareer_art_check")

    def test_every_asset_meets_its_native_specification(self):
        report = self.check.check_folder(ART)
        failures = [a for a in report["assets"] if not a.get("ok")]
        self.assertEqual(failures, [], json.dumps(failures, indent=2))
        by_name = {a["file"]: a for a in report["assets"]}
        for name, spec in self.check.SPECS.items():
            asset = by_name[name]
            self.assertEqual(asset["size"], list(spec["size"]))
            self.assertEqual(asset["mips"]["count"], spec["mips"])
            self.assertEqual(asset["mips"]["index_bytes"], spec["index_bytes"])
            self.assertLessEqual(asset["palette"]["entries"], 256)
            self.assertEqual(asset["palette"]["palette_bytes"], 1024)
        apartment = by_name["mycareer_apartment.png"]
        self.assertEqual(apartment["mips"]["dimensions"][0], [512, 512])
        self.assertEqual(apartment["mips"]["dimensions"][-1], [8, 8])
        self.assertEqual(apartment["alpha"], {"min": 255, "max": 255, "distinct": 1})
        self.assertIn("menu", apartment["calm_zones"])
        self.assertIn("sky", apartment["banding"])
        self.assertEqual(sorted(by_name["mycareer_calendar.png"]["icons"])[:5],
                         sorted(["played", "upcoming", "bye", "practice", "request", "current", "milestone"])[:5])
        self.assertEqual(by_name["hub_mockup_640x480.png"]["size"], [640, 480])
        self.assertEqual(by_name["hub_mockup_wide.png"]["size"], [854, 480])

    def test_manifest_pins_the_layout_specification(self):
        manifest = json.loads((ART / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["crop_43"], [0, 64, 512, 448])
        self.assertEqual(manifest["crop_wide"], [0, 112, 512, 400])
        ui = manifest["ui"]
        self.assertEqual(ui["menu"], [44, 142, 302, 376])
        self.assertEqual(ui["summary"], [332, 142, 596, 376])
        self.assertEqual(ui["content"], [36, 28, 604, 452])
        self.assertEqual((ui["rows"], ui["row_height"], ui["footer_y"]), (9, 26, 432))
        self.assertEqual(ui["menu"][1] + ui["rows"] * ui["row_height"], ui["menu"][3])
        for name in manifest["core_objects"]:
            x0, y0, x1, y1 = manifest["objects"][name]
            self.assertTrue(0 <= x0 < x1 <= 512 and 112 <= y0 < y1 <= 400, name)

    def test_cli_reports_and_exits_zero(self):
        completed = subprocess.run([sys.executable, str(CHECK), str(ART)], capture_output=True, text=True, timeout=600)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["ok"])

    def test_checker_refuses_a_broken_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "art"
            shutil.copytree(ART, work)
            from PIL import Image
            with Image.open(work / "mycareer_apartment.png") as im:
                arr = im.convert("RGBA")
            arr.putalpha(200)                       # a translucent background is a native error
            arr.save(work / "mycareer_apartment.png")
            with Image.open(work / "mycareer_focus.png") as im:
                focus = im.convert("RGBA").resize((64, 32))
            focus.save(work / "mycareer_focus.png")   # wrong slot size
            report = self.check.check_folder(work)
            self.assertFalse(report["ok"])
            errors = {a["file"]: a.get("error", "") for a in report["assets"]}
            self.assertIn("opaque", errors["mycareer_apartment.png"])
            self.assertIn("128x32", errors["mycareer_focus.png"])
            self.assertTrue(all(a["ok"] for a in report["assets"]
                                if a["file"] in ("mycareer_panels.png", "mycareer_calendar.png")))


@unittest.skipUnless(HAVE_IMAGES, "Pillow and numpy are required for the art checks")
class RenderReproducibilityTests(unittest.TestCase):
    def test_build_reproduces_the_shipped_textures_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "render"
            completed = subprocess.run([sys.executable, str(BUILD), "--out", str(out)],
                                       capture_output=True, text=True, timeout=600)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            for name in ("mycareer_apartment.png", "mycareer_panels.png", "mycareer_calendar.png",
                         "mycareer_focus.png", "manifest.json"):
                self.assertEqual((out / name).read_bytes(), (ART / name).read_bytes(), name)
            for name in ("hub_mockup_640x480.png", "hub_mockup_wide.png"):
                self.assertTrue((out / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
