"""Offscreen product tests for explicit normal-logo palette confirmation."""

from __future__ import annotations

import os
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from mod_editor.apf_studio.helmet_logo_regions import (  # noqa: E402
    TwoRegionPalette,
)
from mod_editor.apf_studio.helmet_logo_regions_qt import (  # noqa: E402
    NormalLogoRegionDialog,
)


def _source_three_colours() -> bytes:
    output = bytearray(512 * 512 * 4)
    colours = ((5, 7, 8, 255), (183, 196, 199, 255), (255, 255, 255, 255))
    for y_value in range(180, 332):
        for x_value in range(80, 432):
            colour = colours[min(2, (x_value - 80) // 118)]
            offset = (y_value * 512 + x_value) * 4
            output[offset : offset + 4] = bytes(colour)
    return bytes(output)


class NormalLogoRegionDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_source_suggestion_requires_confirmation_and_shows_material_preview(self) -> None:
        dialog = NormalLogoRegionDialog(_source_three_colours())
        try:
            self.assertEqual(
                dialog.windowTitle(), "Convert normal logo to APF color regions"
            )
            self.assertIn("does not read", dialog.suggestion_note.text())
            self.assertTrue(dialog.shell.text().startswith("#"))
            self.assertTrue(dialog.red_region.text().startswith("#"))
            self.assertTrue(dialog.green_region.text().startswith("#"))
            self.assertIsNotNone(dialog.conversion)
            self.assertFalse(dialog.material_preview.pixmap().isNull())
            self.assertTrue(
                dialog.buttons.button(QDialogButtonBox.Save).isEnabled()
            )
            self.assertIn("Confirm", dialog.status.text())
            dialog.shell.setText("#001122")
            # Never silent-gray: Save stays enabled; disableReason requires preview.
            save = dialog.buttons.button(QDialogButtonBox.Save)
            self.assertTrue(save.isEnabled())
            self.assertTrue(str(save.property("disableReason") or "").strip())
            self.assertIn("Update", dialog.material_preview.text())
        finally:
            dialog.deleteLater()
            self.application.processEvents()

    def test_one_colour_art_gets_no_invented_palette_and_manual_rams_mapping_works(self) -> None:
        source = bytearray(512 * 512 * 4)
        for y_value in range(210, 302):
            for x_value in range(140, 372):
                offset = (y_value * 512 + x_value) * 4
                source[offset : offset + 4] = bytes((255, 199, 44, 255))
        dialog = NormalLogoRegionDialog(bytes(source))
        try:
            self.assertIn("manually", dialog.suggestion_note.text())
            self.assertEqual(dialog.shell.text(), "")
            save = dialog.buttons.button(QDialogButtonBox.Save)
            self.assertTrue(save.isEnabled())
            self.assertTrue(str(save.property("disableReason") or "").strip())
            dialog.set_palette(
                TwoRegionPalette(
                    shell=(0, 53, 98),
                    red_region=(255, 199, 44),
                    green_region=(255, 255, 255),
                )
            )
            self.assertTrue(dialog.refresh_preview())
            self.assertIsNotNone(dialog.conversion)
            assert dialog.conversion is not None
            offset = (220 * 512 + 150) * 4
            self.assertEqual(
                dialog.conversion.mask_rgba[offset : offset + 4],
                bytes((255, 0, 0, 136)),
            )
            self.assertTrue(
                dialog.buttons.button(QDialogButtonBox.Save).isEnabled()
            )
        finally:
            dialog.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
