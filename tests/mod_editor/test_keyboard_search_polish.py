"""Keyboard/search discoverability on main shells."""

from __future__ import annotations

import inspect
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402


class KeyboardSearchPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_apf_shell_has_escape_clear_and_help_shortcuts(self) -> None:
        from mod_editor.apf_studio import gui as apf_gui

        src = inspect.getsource(apf_gui.ApfStudioMainWindow)
        self.assertIn("clear_search_shortcut", src)
        self.assertIn("Key_Escape", src)
        self.assertIn("Ctrl+/", src)
        self.assertIn("_clear_current_search", src)
        self.assertIn("_show_keyboard_hints", src)

    def test_2k5_shell_has_escape_clear_and_help_shortcuts(self) -> None:
        from mod_editor.gui import studio_qt

        src = inspect.getsource(studio_qt.StudioMainWindow)
        self.assertIn("clear_search_shortcut", src)
        self.assertIn("Key_Escape", src)
        self.assertIn("Ctrl+/", src)
        self.assertIn("_clear_current_search", src)
        self.assertIn("_show_keyboard_hints", src)

    def test_asset_browser_search_marks_studio_search_property(self) -> None:
        from mod_editor.apf_studio.gui import AssetBrowser
        from mod_editor.apf_studio.models import ApfCategory

        class _Facade:
            source_ready = False
            modified_asset_ids = frozenset()

            def browse_assets(self, **kwargs):
                return ()

            def require_catalog(self):
                raise RuntimeError("no catalog")

        page = AssetBrowser(_Facade(), ApfCategory.ALL_ASSETS, lambda *a: True)
        try:
            self.assertTrue(bool(page.search.property("studioSearch")))
            self.assertIn("Ctrl+F", page.search.placeholderText())
            self.assertTrue(page.search.accessibleName().startswith("Search"))
        finally:
            page.deleteLater()
            self.app.processEvents()

    def test_playbooks_search_marks_studio_search_property(self) -> None:
        from mod_editor.gui.playbooks_panel_qt import PlaybooksPanel

        class _Host:
            source_ready = False
            playbook_available = False

            def browse_playbooks(self, *a, **k):
                return ()

            def export_playbook(self, *a, **k):
                raise RuntimeError

            def export_playbook_link_table_copy(self, *a, **k):
                raise RuntimeError

            def export_playbook_package_map_copy(self, *a, **k):
                raise RuntimeError

            def copy_play_assignment_route(self, *a, **k):
                raise RuntimeError

            def revert_play_assignment_route(self, *a, **k):
                raise RuntimeError

            def create_formation(self, *a, **k):
                raise RuntimeError

            def create_play(self, *a, **k):
                raise RuntimeError

            def revert_formation_create(self, *a, **k):
                raise RuntimeError

            def revert_play_create(self, *a, **k):
                raise RuntimeError

        panel = PlaybooksPanel(_Host())
        try:
            self.assertTrue(bool(panel.search.property("studioSearch")))
            self.assertIn("Ctrl+F", panel.search.placeholderText())
        finally:
            panel.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
