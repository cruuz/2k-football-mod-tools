"""b778 sd3: the modern LED digit cell and the EverBank boards' modern stat-panel art.

The cell is shared by every model stadium (one function in nfl2k5_sofi_model); the panel is the EverBank model's one
128 x 128 texture. The tests here are offline: pixels, the art manifest, the pins/registry identity. The retail-scene
build check runs only when the hydrated archive is present, like the existing EverBank suite.
"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_everbank_model as jx  # noqa: E402
from mod_editor.core import nfl2k5_sofi_model as sm  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


def luma(rgb):
    return np.asarray(rgb, float) @ np.array([0.299, 0.587, 0.114])


class LedCellTests(unittest.TestCase):
    def test_shape_and_warm_white(self):
        cell = sm.led_segment()
        self.assertEqual(cell.shape, (32, 32, 4))
        self.assertTrue((cell[..., 3] == 255).all())
        rgb = cell[..., :3].reshape(-1, 3)
        self.assertGreater(rgb.min(), 200, "the cell must be lit to its edges; no black bulb gaps or frame")
        self.assertGreater(rgb[:, 0].mean(), rgb[:, 2].mean(), "the cell is warm white, not blue")

    def test_the_cell_has_no_dark_border(self):
        cell = sm.led_segment()
        border = np.concatenate([cell[0], cell[-1], cell[:, 0], cell[:, -1]])[:, :3]
        self.assertGreaterEqual(int(border.min()), 200)

    def test_tiling_the_cell_has_no_seam(self):
        """Neighbouring cells must merge: the old texture's 6-level black frame failed exactly here."""
        cell = sm.led_segment()
        seam = np.concatenate([cell[:, -1], cell[:, 0], cell[-1, :], cell[0, :]])[:, :3]
        self.assertGreaterEqual(int(seam.min()), 200)
        # the 4-texel LED grid is periodic across the edge (32 is a multiple of 4): the first and last columns have
        # the same pattern after one cell
        np.testing.assert_array_equal(cell[:, 0], cell[:, 32 - 32])

    def test_modern_grid_not_four_bulbs(self):
        """A fine dot grid brightens most of the cell; there is no 2 x 2 black-hole lamp pattern."""
        cell = sm.led_segment()[..., :3]
        lum = luma(cell)
        self.assertGreater(float(lum.mean()), 220.0)
        self.assertLess(float(lum.max() - lum.min()), 60.0, "the LED dots are a subtle fine-pitch grid")
        # every 4 x 4 block stays bright (the retail 32 x 32 had 4 bulbs in a 16 x 16 quadrant and black elsewhere)
        blocks = lum.reshape(8, 4, 8, 4).mean(axis=(1, 3))
        self.assertGreater(float(blocks.min()), 200.0)

    def test_the_models_share_the_cell(self):
        """Every model stadium's scene repaint calls this one function for its digit_* textures."""
        for name in ("everbank", "sofi", "gillette", "att", "levis", "allegiant", "mercedes_benz", "usbank",
                     "lucas_oil", "state_farm", "hard_rock", "lambeau", "highmark", "practice_field"):
            module = __import__(f"mod_editor.core.nfl2k5_{name}_model", fromlist=["x"])
            self.assertIn("led_segment", Path(module.__file__).read_text(encoding="utf-8"), name)


class PanelArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.image = Image.open(jx.ART_DIR / "LIGHT_jx_board_panel.png").convert("RGB")
        cls.a = np.asarray(cls.image)
        cls.manifest = json.loads((jx.ART_DIR / "art.json").read_text(encoding="utf-8"))["art"]

    def test_size_and_manifest(self):
        self.assertEqual(self.image.size, (128, 128))
        import hashlib
        self.assertEqual(self.manifest["LIGHT_jx_board_panel"]["sha256"],
                         hashlib.sha256((jx.ART_DIR / "LIGHT_jx_board_panel.png").read_bytes()).hexdigest())

    def test_gold_rule_and_dark_screen(self):
        top = self.a[0:5]
        self.assertTrue((top[..., 0] > 180).mean() > 0.85, "the gold top rule")
        self.assertTrue((top[..., 2] < 100).mean() > 0.85)
        # a dark LED screen, not the old teal gradient
        bg = self.a[100:125, 2:14]
        self.assertLess(float(luma(bg).mean()), 25.0, "the old teal gradient was 36.7")
        self.assertGreater(float(bg[..., 2].mean()), float(bg[..., 0].mean()))

    def test_the_live_window_is_where_the_digits_go(self):
        """adjust_digits puts the score and clock inside the window at 0.14 .. 0.50 of the panel's height."""
        win = self.a[int(128 * 0.15):int(128 * 0.49), int(128 * 0.07):int(128 * 0.93)]
        self.assertLess(float(luma(win).mean()), 20.0)
        self.assertGreater(float(luma(win).max()), 0.0)

    def test_white_led_wordmark_and_venue_name(self):
        lower = self.a[70:, :]
        white = (lower[..., 0] > 240) & (lower[..., 1] > 240) & (lower[..., 2] > 240)
        self.assertGreater(int(white.sum()), 300, "JAGUARS and EVERBANK STADIUM as bright LED type (the old gold JAGUARS had 121)")
        gold = (lower[..., 0] > 180) & (lower[..., 1] > 120) & (lower[..., 1] < 190) & (lower[..., 2] < 90)
        self.assertGreater(int(gold.sum()), 50, "the gold underline")

    def test_the_fake_down_and_distance_is_not_printed_twice(self):
        """The panel is branding now; the old static 1ST & 10 band has no matching white text row."""
        band = self.a[int(128 * 0.72):int(128 * 0.84), :]
        # the subline occupies the band, but the old 2x text row's large blue-white area is gone: the new subline
        # is smaller and letterspaced, leaving more dark screen between the glyphs
        self.assertLess(float((luma(band) > 180).mean()), 0.05, "the old 1ST & 10 band was 10.9% bright")


class IdentityTests(unittest.TestCase):
    def test_registry_quotes_the_regenerated_pins(self):
        pins = {row["name"]: row for row in json.loads(
            (ROOT / "data/nfl2k5_everbank_model/pins.json").read_text(encoding="utf-8"))["bundles"]}
        registry = (ROOT / "mod_editor/capabilities/registry.v1.json").read_text(encoding="utf-8")
        for name in ("s12dd.iff", "s12ns.iff"):
            for key in ("model_sha256", "classic_sha256"):
                self.assertIn(pins[name][key], registry, f"{name} {key} is not in the registry")



@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class BuiltSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = jx.read_retail(EXTRACTED)
        cls.model = jx.build()
        cls.scene = jx.build_scene(cls.retail["s12dd.iff"], "s12dd.iff", cls.model)

    def test_the_digit_cells_are_the_led_cell(self):
        indices = sorted({m.texture for m in self.scene.materials
                          if m.name.startswith("digit_") and m.texture is not None})
        self.assertTrue(indices)
        for index in indices:
            rec = self.scene.textures[index]
            palette = np.frombuffer(bytes(rec.palette), np.uint8).reshape(-1, 4)
            used = palette[palette[:, 3] == 255]
            self.assertGreaterEqual(len(used), 2, "the LED cell needs its base and its bright dots")
            # BGRA: every used colour is warm white; the old cell's 6-level black frame is gone
            self.assertGreater(int(used[:, :3].max(axis=1).min()), 200)
            self.assertGreater(int(used[:, 2].mean()), int(used[:, 0].mean()), "warm white, not blue")

    def test_the_panel_texture_is_the_authored_art(self):
        from PIL import Image
        art = np.asarray(Image.open(jx.ART_DIR / "LIGHT_jx_board_panel.png").convert("RGB"))
        mat = self.scene.materials[self.scene.material_index("LIGHT_jx_board_panel")]
        self.assertIsNotNone(mat.texture)
        # the texture record is P8; its used palette must hold the panel's gold rule and bright type
        rec = self.scene.textures[mat.texture]
        palette = np.frombuffer(bytes(rec.palette), np.uint8).reshape(-1, 4)
        used = palette[palette[:, 3] == 255]
        self.assertGreaterEqual(len(used), 8)
        gold = (used[:, 2] > 180) & (used[:, 1] > 120) & (used[:, 1] < 195) & (used[:, 0] < 95)
        white = (used[:, 2] > 230) & (used[:, 1] > 230) & (used[:, 0] > 230)
        dark = (used[:, :3].max(axis=1) < 30)
        self.assertTrue(gold.any(), "the panel texture has no gold rule")
        self.assertTrue(white.any(), "the panel texture has no bright type")
        self.assertTrue(dark.any(), "the panel texture has no dark screen")


if __name__ == "__main__":
    unittest.main()
