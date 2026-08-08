"""Noob-language audit: refusals say what happened AND how to fix it.

The fail-closed behaviour never changes -- the same bytes are still refused --
but every user-facing refusal in the GUI layer must carry a plain next step.
These tests pin the fix-hint wording and the converted-instead-of-refused
routes so a future edit cannot quietly bring the dead ends back.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from mod_editor.apf_studio import gui  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APF_GUI = _REPO_ROOT / "mod_editor" / "apf_studio" / "gui.py"
_STUDIO_QT = _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
_CRIB_QT = _REPO_ROOT / "mod_editor" / "gui" / "crib_panel_qt.py"


class FixHintTests(unittest.TestCase):
    """The central error gloss pairs known refusals with plain fixes."""

    REFUSALS = (
        "Expected an exact 128x128 RGBA PNG; received 64x64 RGB.",
        "Pants PNG alpha must be 255 (fully opaque) everywhere",
        "Wordmark PNG alpha must be 255 everywhere; use the importer",
        "digital_font RGB must be solid white; draw only in alpha",
        "Helmet PNG blue must be 0; only the R/G mask channels are stored",
        "That image is 200×300; it must stay 512×512.",
        "DXT1 stadium textures require opaque artwork; flatten transparency first",
        "notes.txt could not be read as an image: cannot identify image file",
        "FFmpeg was not found to convert it.",
    )

    def test_every_known_refusal_gets_a_plain_fix_hint(self) -> None:
        for message in self.REFUSALS:
            with self.subTest(message=message):
                hint = gui.friendly_fix_hint(message)
                self.assertIsNotNone(hint, "refusal has no fix hint")
                assert hint is not None
                self.assertIn("Fix:", hint)

    def test_exact_size_refusals_point_back_to_the_editor(self) -> None:
        hint = gui.friendly_fix_hint(self.REFUSALS[0])
        assert hint is not None
        self.assertIn("resizes it for you", hint)

    def test_unknown_messages_get_no_hint(self) -> None:
        self.assertIsNone(gui.friendly_fix_hint("Something unrelated happened."))

    def test_the_error_dialog_shows_the_hint(self) -> None:
        source = _APF_GUI.read_text(encoding="utf-8")
        start = source.index("    def _show_error(self, message: str")
        block = source[start:start + 800]
        self.assertIn("friendly_fix_hint(message)", block)


class NoDeadEndCopyTests(unittest.TestCase):
    """Stale 'refused / rejects' copy must not survive in the GUI layer."""

    def test_apf_gui_never_claims_wrong_sizes_are_refused(self) -> None:
        source = _APF_GUI.read_text(encoding="utf-8")
        self.assertNotIn("Wrong PNG size", source)
        self.assertNotIn("any other size is refused", source)
        self.assertNotIn("refused before anything is staged", source)

    def test_2k5_uniform_help_no_longer_threatens_rejection(self) -> None:
        source = _STUDIO_QT.read_text(encoding="utf-8")
        self.assertNotIn("rejects the wrong dimensions", source)

    def test_crib_chooser_and_drop_accept_every_ordinary_format(self) -> None:
        source = _CRIB_QT.read_text(encoding="utf-8")
        self.assertIn("CRIB_IMAGE_FILTER", source)
        self.assertIn("resized to the exact", source)
        # The old PNG-only gate is gone from the drop target.
        self.assertNotIn('endswith(".png")', source)

    def test_stadium_chooser_accepts_every_ordinary_format(self) -> None:
        source = _APF_GUI.read_text(encoding="utf-8")
        start = source.index("    def _replace_embedded_texture(self) -> None:")
        # Window must cover never-gray disableReason preamble + getOpenFileName.
        block = source[start:start + 1400]
        self.assertIn("IMAGE_IMPORT_FILTER", block)
        self.assertIn("resized to", block)

    def test_crest_pill_promises_conversion_instead_of_refusal(self) -> None:
        source = _APF_GUI.read_text(encoding="utf-8")
        # The tooltip is split across source string literals, so collapse
        # whitespace and quotes before matching the user-visible phrase.
        collapsed = source.replace('"', "").replace("'", "")
        collapsed = "".join(collapsed.split())
        self.assertIn("resizedandconvertedforyou", collapsed)


class DigitalFontConversionTests(unittest.TestCase):
    """The score-digit slot converts any image instead of refusing it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def test_an_opaque_jpeg_becomes_a_white_alpha_mask(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "digits.jpg"
            image = Image.new("RGB", (300, 100), (0, 0, 0))
            # A bright bar stands in for the digit strokes.
            for x in range(100, 200):
                for y in range(20, 80):
                    image.putpixel((x, y), (255, 255, 255))
            image.save(source, "JPEG")
            destination = Path(directory) / "mask.png"

            with mock.patch.object(
                gui.QMessageBox, "question", return_value=QMessageBox.Yes
            ) as question, mock.patch.object(gui.QMessageBox, "information"):
                prepared = gui._prepare_digital_font_mask(
                    None, source, destination
                )
            self.assertEqual(prepared, destination)
            # The offer explains the mask conversion in plain words.
            body = question.call_args.args[2]
            self.assertIn("alpha channel", body)
            self.assertIn("solid white", body)
            self.assertIn("not modified", body)

            with Image.open(destination) as mask:
                self.assertEqual(mask.size, (128, 128))
                self.assertEqual(mask.mode, "RGBA")
                red = mask.getchannel("R").getextrema()
                green = mask.getchannel("G").getextrema()
                blue = mask.getchannel("B").getextrema()
                alpha_min, alpha_max = mask.getchannel("A").getextrema()
            # The writer contract: RGB solid white, digits drawn in alpha.
            self.assertEqual(red, (255, 255))
            self.assertEqual(green, (255, 255))
            self.assertEqual(blue, (255, 255))
            self.assertEqual(alpha_min, 0)
            self.assertGreater(alpha_max, 200)

    def test_declining_the_conversion_stages_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "digits.png"
            Image.new("RGBA", (200, 200), (10, 10, 10, 255)).save(source)
            destination = Path(directory) / "mask.png"
            with mock.patch.object(
                gui.QMessageBox, "question", return_value=QMessageBox.Cancel
            ), mock.patch.object(gui.QMessageBox, "information"):
                prepared = gui._prepare_digital_font_mask(
                    None, source, destination
                )
            self.assertIsNone(prepared)
            self.assertFalse(destination.exists())

    def test_unreadable_files_are_refused_with_a_fix_not_jargon(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            junk = Path(directory) / "junk.png"
            junk.write_bytes(b"this is not an image")
            with mock.patch.object(
                gui.QMessageBox, "information"
            ) as information:
                prepared = gui._prepare_digital_font_mask(
                    None, junk, Path(directory) / "mask.png"
                )
            self.assertIsNone(prepared)
            title, body = information.call_args.args[1], \
                information.call_args.args[2]
            self.assertIn("could not be read as an image", title.casefold())
            self.assertIn("Fix:", body)
            self.assertIn("resizes it for you", body)


if __name__ == "__main__":
    unittest.main()
