"""Any image a modder has must be able to become the size a slot demands.

A texture occupies a fixed byte span, so its replacement has to be exactly the
retail pixel size. That rule is the disc's. Refusing the file instead of
offering to fit it was ours, and it stopped people at the first step -- a team
crest pulled from anywhere is never already 512x512, so "do the Eagles helmet
logo" died on a dialog that said no.

The three fits exist for different content and the choice matters:

* a **crest** pads, because cropping the sides off a logo to fill a square is
  the wrong answer and the texture already has an alpha channel
* a **jersey or field panel** crops, because transparent bars baked into it
  show up in game as holes
* anything already exact is passed through untouched, so a correct file is
  never resampled "just in case"
"""

from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.image_fit import (  # noqa: E402
    FIT_MODES,
    FIT_MODE_CHOICES,
    fit_image,
    fit_mode_from_label,
    fit_mode_labels,
    fit_to_png,
)

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow ships with the app
    Image = None


@unittest.skipIf(Image is None, "Pillow is not installed")
class FitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _image(self, width: int, height: int, name: str = "in.png",
               mode: str = "RGBA") -> Path:
        image = Image.new(mode, (width, height))
        pixels = image.load()
        for y in range(height):
            for x in range(width):
                value = (x * 255 // max(1, width - 1),
                         y * 255 // max(1, height - 1), 128)
                pixels[x, y] = value + ((255,) if mode == "RGBA" else ())
        path = self.root / name
        image.save(path)
        return path

    def test_an_exact_image_is_passed_through_untouched(self) -> None:
        source = self._image(512, 512)
        result = fit_image(source, 512, 512)
        self.assertEqual(result.action, "exact")
        self.assertFalse(result.changed)
        self.assertEqual(result.rgba, Image.open(source).convert("RGBA").tobytes())

    def test_same_aspect_is_scaled_with_nothing_lost(self) -> None:
        result = fit_image(self._image(1024, 512), 512, 256)
        self.assertEqual(result.action, "scaled")
        self.assertEqual((result.width, result.height), (512, 256))
        self.assertEqual(len(result.rgba), 512 * 256 * 4)

    def test_a_crest_keeps_its_whole_shape(self) -> None:
        """contain: the Eagles case. Nothing may be cropped away."""
        result = fit_image(self._image(900, 640), 512, 512, mode="contain")
        self.assertEqual(result.action, "padded")
        self.assertEqual((result.width, result.height), (512, 512))
        self.assertGreater(result.padded_y, 0)
        self.assertEqual(result.padded_x, 0)

    def test_padding_is_transparent_not_black(self) -> None:
        result = fit_image(self._image(900, 640), 512, 512, mode="contain")
        top_left = result.rgba[0:4]
        self.assertEqual(top_left[3], 0, "padding must be fully transparent")

    def test_a_full_bleed_texture_crops_rather_than_padding(self) -> None:
        result = fit_image(self._image(900, 640), 512, 512, mode="cover")
        self.assertEqual(result.action, "cropped")
        self.assertGreater(result.cropped_x, 0)
        for offset in range(0, len(result.rgba), 4):
            self.assertEqual(result.rgba[offset + 3], 255)
            break

    def test_stretch_forces_exact_size_without_preserving_aspect(self) -> None:
        result = fit_image(self._image(200, 50), 100, 100, mode="stretch")
        self.assertEqual(result.action, "stretched")
        self.assertEqual((result.width, result.height), (100, 100))
        self.assertIn("without preserving aspect", result.describe())

    def test_chooser_labels_map_to_contain_cover_stretch(self) -> None:
        labels = fit_mode_labels()
        self.assertEqual(len(labels), 3)
        modes = {fit_mode_from_label(label) for label in labels}
        self.assertEqual(modes, {"contain", "cover", "stretch"})
        self.assertEqual(len(FIT_MODE_CHOICES), 3)
        self.assertEqual(fit_mode_from_label("stretch"), "stretch")
        self.assertEqual(fit_mode_from_label("Contain — keep whole image, pad with transparency"), "contain")

    def test_every_mode_lands_on_the_exact_target(self) -> None:
        for mode in FIT_MODES:
            with self.subTest(mode=mode):
                result = fit_image(self._image(333, 777), 512, 256, mode=mode)
                self.assertEqual((result.width, result.height), (512, 256))
                self.assertEqual(len(result.rgba), 512 * 256 * 4)

    def test_upscaling_a_small_image_still_lands_exactly(self) -> None:
        result = fit_image(self._image(64, 64), 512, 512)
        self.assertEqual((result.width, result.height), (512, 512))
        self.assertEqual(len(result.rgba), 512 * 512 * 4)

    def test_formats_other_than_png_are_accepted(self) -> None:
        """A logo off the web is as likely to be a JPEG."""
        source = self._image(900, 640, "logo.jpg", mode="RGB")
        result = fit_image(source, 512, 512, mode="contain")
        self.assertEqual((result.width, result.height), (512, 512))

    def test_the_written_png_reloads_at_the_target_size(self) -> None:
        destination = self.root / "out.png"
        fit_to_png(self._image(900, 640), 512, 512, destination, mode="contain")
        with Image.open(destination) as written:
            self.assertEqual(written.size, (512, 512))
            self.assertEqual(written.mode, "RGBA")

    def test_a_non_image_is_refused_with_a_reason(self) -> None:
        junk = self.root / "notes.txt"
        junk.write_text("this is not an image", encoding="utf-8")
        with self.assertRaises(ValidationError):
            fit_image(junk, 512, 512)

    def test_an_unknown_mode_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            fit_image(self._image(64, 64), 512, 512, mode="squish")

    def test_a_nonsense_target_is_refused(self) -> None:
        for width, height in ((0, 512), (512, 0), (-1, 8)):
            with self.subTest(size=(width, height)):
                with self.assertRaises(ValidationError):
                    fit_image(self._image(64, 64), width, height)


class WiringTests(unittest.TestCase):
    """The crest panel must offer the fit rather than refuse the file."""

    def test_the_apf_logo_panel_offers_to_resize(self) -> None:
        source = (
            _REPO_ROOT / "mod_editor" / "apf_studio" / "gui.py"
        ).read_text(encoding="utf-8")
        start = source.index("    def _stage_path(self, path: Path) -> None:")
        block = source[start:start + 3000]
        self.assertIn("fit_image", block)
        self.assertIn("fit_to_png", block)
        self.assertIn('mode="contain"', block)
        self.assertNotIn("Wrong PNG size", block)

    def test_the_chooser_accepts_more_than_png(self) -> None:
        source = (
            _REPO_ROOT / "mod_editor" / "apf_studio" / "gui.py"
        ).read_text(encoding="utf-8")
        self.assertIn("*.jpg", source)


    def test_the_apf_uniform_panel_offers_to_resize(self) -> None:
        """Jerseys, pants and colour maps hit the same wall as the crest."""
        source = (
            _REPO_ROOT / "mod_editor" / "apf_studio" / "gui.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Wrong PNG size", source)
        # Shared fit_slot_image plus panel staging paths must call fit_to_png.
        # Match both `fit_to_png(path` and multi-line `fit_to_png(\n    path`.
        import re
        calls = re.findall(r"fit_to_png\s*\(\s*path", source)
        self.assertGreaterEqual(
            len(calls), 3,
            "every APF staging path must offer the fit via fit_to_png(path…)",
        )
        self.assertIn("def fit_slot_image", source)
        self.assertIn("fit_mode_labels", source)
        self.assertIn("getItem", source)

    def test_the_2k5_replace_path_fits_before_replacing(self) -> None:
        source = (
            _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def _fit_for_slot", source)
        start = source.index("    def _replace_visual_asset(")
        block = source[start:start + 900]
        self.assertIn("_fit_for_slot(path, asset.width, asset.height", block)

    def test_the_2k5_chooser_accepts_more_than_png(self) -> None:
        source = (
            _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
        ).read_text(encoding="utf-8")
        start = source.index("    def _choose_visual_replacement(")
        block = source[start:start + 600]
        self.assertIn("*.jpg", block)

    def test_an_already_correct_image_is_never_resampled(self) -> None:
        """The rule that keeps a good file byte-identical through the GUI."""
        source = (
            _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
        ).read_text(encoding="utf-8")
        start = source.index("    def _fit_for_slot(")
        block = source[start:start + 2400]
        self.assertIn("needs_png_conversion", block)
        self.assertIn(
            "if not probe.changed and not needs_png_conversion:", block
        )
        self.assertIn("return path", block)

    def test_the_batch_cli_exists_and_is_executable(self) -> None:
        """For folders of textures a dialog cannot reach."""
        import os
        tool = _REPO_ROOT / "tools" / "nfl_fit_image.py"
        self.assertTrue(tool.is_file())
        self.assertTrue(os.access(tool, os.X_OK), "shipped tools must be 0755")
        source = tool.read_text(encoding="utf-8")
        self.assertIn("--mode", source)
        for mode in FIT_MODES:
            self.assertIn(mode, source)


if __name__ == "__main__":
    unittest.main()
