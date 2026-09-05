"""ESPN Scorebug & Ticker tab: state gating and write enablement (no disc access)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.gui.presentation_panel_qt import PresentationPanel  # noqa: E402


class PresentationPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_write_only_for_retail_discs_with_a_target(self) -> None:
        panel = PresentationPanel()
        try:
            panel.apply_state(Path("/nowhere/game.xiso.iso"), "retail")
            # a copy name is suggested beside the disc; clear it to check the no-target gate
            self.assertTrue(panel.target_field.text().endswith(" (ESPN scorebug).xiso.iso"), panel.target_field.text())
            panel.target_field.setText("")
            self.assertFalse(panel.write_button.isEnabled())       # no target
            panel.target_field.setText("/nowhere/copy.xiso.iso")
            panel._refresh()
            self.assertTrue(panel.write_button.isEnabled())
            for state in ("applied", "foreign", "n/a"):
                panel.apply_state(Path("/nowhere/game.xiso.iso"), state)
                self.assertFalse(panel.write_button.isEnabled(), state)
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_studio_offers_the_tab(self) -> None:
        from mod_editor.gui.studio_qt import StudioMainWindow

        window = StudioMainWindow()
        try:
            self.assertEqual(len(window.findChildren(PresentationPanel)), 1)
        finally:
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
