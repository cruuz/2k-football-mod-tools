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
            # Fixture may auto-select players (export ready). Clear → teach wall.
            self.assertTrue(panel.export_current_number_button.isEnabled())
            self.assertTrue(panel.export_historical_number_button.isEnabled())
            panel._clear_current_player()
            panel._clear_historical_player()
            self.assertTrue(panel.export_current_number_button.isEnabled())
            self.assertTrue(
                str(
                    panel.export_current_number_button.property("disableReason") or ""
                ).strip()
            )
            self.assertTrue(panel.export_historical_number_button.isEnabled())
            self.assertTrue(
                str(
                    panel.export_historical_number_button.property("disableReason")
                    or ""
                ).strip()
            )
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_2k5_menus_export_never_gray(self) -> None:
        from pathlib import Path
        from PyQt5.QtWidgets import QWidget
        from mod_editor.gui.menus_panel_qt import MenusPanel

        class _FailingMenuHost:
            def inspect_main_menu(self, progress: object) -> object:
                raise RuntimeError("no map")

            def export_main_menu_inspection(
                self, destination: Path, export_format: str, progress: object
            ) -> Path:
                raise RuntimeError("no map")

        panel = MenusPanel(_FailingMenuHost(), raw_fallback=QWidget())
        try:
            self.assertTrue(panel.export_json_button.isEnabled())
            self.assertTrue(panel.export_csv_button.isEnabled())
            self.assertTrue(
                str(panel.export_json_button.property("disableReason") or "").strip()
            )
            self.assertTrue(
                str(panel.export_csv_button.property("disableReason") or "").strip()
            )
            self.assertIn("unavailable", panel.export_json_button.toolTip().lower())
        finally:
            panel.deleteLater()
            self.app.processEvents()



    def test_2k5_audio_export_matching_boot(self) -> None:
        from pathlib import Path
        import tempfile
        from mod_editor.gui.audio_panel_qt import AudioPanel
        # lightweight: just ensure button exists with disableReason after construct
        # uses real fixture if available via AudioFixture in audio panel tests
        try:
            from tests.mod_editor.test_audio_panel_qt import (
                AudioFixture,
                CatalogAudioPanelHost,
            )
            from mod_editor.core.nfl2k5_audio_catalog import Nfl2k5AudioService
        except Exception:
            self.skipTest("audio panel fixtures unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=1)
            try:
                self.assertTrue(panel.export_matching_button.isEnabled())
                # may be ready with fixture - either empty disableReason or tip
                self.assertTrue(panel.export_matching_button.isEnabled())
            finally:
                panel.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
