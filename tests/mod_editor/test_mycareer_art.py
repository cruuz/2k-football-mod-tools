"""MyCareer apartment hub art: native P8 constraints, layout safety, reproducibility.

The atlases under docs/mycareer_art are authored by docs/mycareer_art/build.py
and committed. The backdrop is a real NFL 2K5 texture (the Crib's skyline)
composed from backdrop_recipe.json out of the user's private source cache at
build time and never committed, so the tests that need it skip on a machine
without that cache. tools/mycareer_art_check.py verifies everything.

These tests pin: the checker's mip and palette code is the repo's own P8
approach (byte-identical to nfl_tset_png_import); the atlases pass their native
constraints without any game data; the manifest pins the layout specification;
and, where the cache exists, the composed backdrop passes every constraint, the
build is byte-for-byte reproducible and the checker refuses broken assets.
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
ATLASES = ("mycareer_panels.png", "mycareer_calendar.png", "mycareer_focus.png")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _have_cache() -> bool:
    if not HAVE_IMAGES:
        return False
    try:
        return _load(BUILD, "mycareer_art_build").find_source_cache_root() is not None
    except Exception:  # noqa: BLE001 - a broken cache is the same as no cache for these tests
        return False


HAVE_CACHE = _have_cache()


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
class CommittedArtTests(unittest.TestCase):
    """Everything that is in the repository must pass without any game data."""

    def setUp(self):
        self.check = _load(CHECK, "mycareer_art_check")
        self.manifest = json.loads((ART / "manifest.json").read_text(encoding="utf-8"))

    def test_atlases_meet_their_native_specification(self):
        for name in ATLASES:
            result = self.check.check_asset(ART, name, self.manifest)
            self.assertTrue(result["ok"], name)
            spec = self.check.SPECS[name]
            self.assertEqual(result["size"], list(spec["size"]))
            self.assertEqual(result["mips"]["count"], spec["mips"])
            self.assertEqual(result["mips"]["index_bytes"], spec["index_bytes"])
            self.assertLessEqual(result["palette"]["entries"], 256)
            self.assertEqual(result["palette"]["palette_bytes"], 1024)
        icons = self.manifest["calendar"]["icons"]
        for name in ("played", "upcoming", "bye", "practice", "request"):
            self.assertIn(name, icons)

    def test_manifest_pins_the_layout_specification(self):
        manifest = self.manifest
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
        self.assertFalse(manifest["backdrop"]["retail_pixels_committed"])

    def test_recipe_names_only_catalogued_crib_textures(self):
        from mod_editor.core.nfl2k5_crib import load_nfl2k5_crib_catalog
        catalog = load_nfl2k5_crib_catalog()
        for path in sorted(ART.glob("backdrop_recipe*.json")):
            recipe = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(recipe["schema"], "mycareer_backdrop_recipe/v1", path.name)
            self.assertEqual(recipe["canvas"], [512, 512], path.name)
            for layer in recipe["layers"]:
                asset = catalog.by_selector(layer["selector"])
                self.assertEqual(asset.asset_id, layer["asset_id"], path.name)
                x0, y0, x1, y1 = layer["rect"]
                self.assertTrue(0 <= x0 < x1 <= 512 and 0 <= y0 < y1 <= 512, path.name)
                if layer.get("fit", "exact") == "exact":
                    self.assertEqual((x1 - x0, y1 - y0), (asset.width, asset.height), path.name)

    def test_committed_pngs_carry_no_backdrop(self):
        tracked = subprocess.run(["git", "ls-files", "docs/mycareer_art"], cwd=ROOT,
                                 capture_output=True, text=True, check=False).stdout.split()
        if not tracked:
            self.skipTest("not a git checkout")
        for path in tracked:
            self.assertNotIn("mycareer_apartment", path)
            self.assertNotIn("hub_mockup", path)


@unittest.skipUnless(HAVE_CACHE, "the composed backdrop needs the user's NFL 2K5 source cache")
class ComposedBackdropTests(unittest.TestCase):
    def setUp(self):
        self.check = _load(CHECK, "mycareer_art_check")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "render"
        completed = subprocess.run([sys.executable, str(BUILD), "--out", str(self.out), "--require-backdrop"],
                                   capture_output=True, text=True, timeout=600)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_build_is_reproducible_and_matches_the_committed_files(self):
        for name in ATLASES + ("manifest.json",):
            self.assertEqual((self.out / name).read_bytes(), (ART / name).read_bytes(), name)
        again = Path(self.tmp.name) / "again"
        completed = subprocess.run([sys.executable, str(BUILD), "--out", str(again), "--require-backdrop"],
                                   capture_output=True, text=True, timeout=600)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        for name in ("mycareer_apartment.png", "hub_mockup_640x480.png", "hub_mockup_wide.png"):
            self.assertEqual((self.out / name).read_bytes(), (again / name).read_bytes(), name)

    def test_composed_backdrop_meets_every_constraint(self):
        report = self.check.check_folder(self.out)
        failures = [a for a in report["assets"] if not a.get("ok")]
        self.assertEqual(failures, [], json.dumps(failures, indent=2))
        by_name = {a["file"]: a for a in report["assets"]}
        apartment = by_name["mycareer_apartment.png"]
        self.assertEqual(apartment["mips"]["dimensions"][0], [512, 512])
        self.assertEqual(apartment["mips"]["dimensions"][-1], [8, 8])
        self.assertEqual(apartment["mips"]["index_bytes"], 349_504)
        self.assertLessEqual(apartment["palette"]["entries"], 256)
        self.assertEqual(apartment["alpha"], {"min": 255, "max": 255, "distinct": 1})
        self.assertIn("menu", apartment["calm_zones"])
        self.assertIn("sky", apartment["banding"])
        self.assertEqual(by_name["hub_mockup_640x480.png"]["size"], [640, 480])
        self.assertEqual(by_name["hub_mockup_wide.png"]["size"], [854, 480])

    def test_cli_reports_and_exits_zero(self):
        completed = subprocess.run([sys.executable, str(CHECK), str(self.out)], capture_output=True, text=True, timeout=600)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["ok"])

    def test_checker_refuses_a_broken_asset(self):
        work = Path(self.tmp.name) / "broken"
        shutil.copytree(self.out, work)
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


if __name__ == "__main__":
    unittest.main()
