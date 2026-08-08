"""Boot-time never-silent-gray checks for critical action buttons."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class NeverSilentGrayBootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_apf_text_and_sheet_boot(self) -> None:
        from unittest.mock import MagicMock
        from mod_editor.apf_studio.gui import InspectorBrowser

        facade = MagicMock()
        facade.source_ready = False
        facade.modified_asset_ids = frozenset()
        browser = InspectorBrowser(
            "Universal text",
            facade,
            lambda *_a, **_k: None,
            text_mode=True,
        )
        try:
            self.assertTrue(browser.apply_text_button.isEnabled())
            self.assertTrue(
                str(browser.apply_text_button.property("disableReason") or "").strip()
            )
            self.assertTrue(browser.export_text_sheet_button.isEnabled())
            self.assertTrue(
                str(browser.export_text_sheet_button.property("disableReason") or "").strip()
            )
        finally:
            browser.deleteLater()
            self.app.processEvents()

    def test_2k5_text_rosters_boot(self) -> None:
        from mod_editor.gui.text_rosters_panel import TextRosterPanel
        from tests.mod_editor.test_text_rosters_panel import FakeHost, catalog_fixture

        panel = TextRosterPanel(FakeHost(catalog_fixture()))
        try:
            self.assertTrue(panel.apply_text_button.isEnabled())
            self.assertTrue(
                str(panel.apply_text_button.property("disableReason") or "").strip()
            )
            self.assertTrue(panel.apply_team_button.isEnabled())
            self.assertTrue(
                str(panel.apply_team_button.property("disableReason") or "").strip()
            )
        finally:
            panel.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
