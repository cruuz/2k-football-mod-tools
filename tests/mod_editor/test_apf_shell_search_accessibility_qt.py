"""Headless keyboard-search coverage for the APF product shell."""

from __future__ import annotations

import os
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QShortcut  # noqa: E402

from mod_editor.apf_studio.gui import ApfStudioMainWindow  # noqa: E402
from mod_editor.apf_studio.models import (  # noqa: E402
    APF_CATEGORY_ORDER,
    ApfCategory,
)


class ApfShellSearchAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = ApfStudioMainWindow(offer_recovery=False)
        self.application.processEvents()

    def tearDown(self) -> None:
        self.window.deleteLater()
        self.application.processEvents()

    def _activate(self, category: ApfCategory) -> None:
        self.window.navigation.setCurrentRow(APF_CATEGORY_ORDER.index(category))
        self.application.processEvents()

    def test_shell_owns_the_only_ctrl_f_shortcut(self) -> None:
        matches = tuple(
            shortcut
            for shortcut in self.window.findChildren(QShortcut)
            if shortcut.key().toString() == "Ctrl+F"
        )
        self.assertEqual(matches, (self.window.find_shortcut,))
        self.assertEqual(self.window.find_shortcut.context(), Qt.WindowShortcut)

    def test_ctrl_f_targets_enabled_visible_workspace_searches(self) -> None:
        uniforms = self.window._pages[ApfCategory.UNIFORMS]
        stadiums = self.window._pages[ApfCategory.STADIUMS]
        all_assets = self.window._pages[ApfCategory.ALL_ASSETS]
        gameplay = self.window._pages[ApfCategory.GAMEPLAY]
        expectations = (
            (ApfCategory.UNIFORMS, uniforms.search, "helmet slot"),
            (ApfCategory.STADIUMS, stadiums.scene_search, "scene 43"),
            (ApfCategory.ALL_ASSETS, all_assets.browser.search, "digital font"),
            (ApfCategory.GAMEPLAY, gameplay.inspector.search, "draft"),
        )
        for category, field, query in expectations:
            with self.subTest(workspace=category.title):
                self._activate(category)
                page = self.window.pages.currentWidget()
                self.assertIsNotNone(page)
                assert page is not None
                self.assertTrue(field.isEnabled())
                self.assertTrue(field.isVisibleTo(page))
                self.assertIs(self.window._current_search_field(), field)

                field.setText(query)
                self.window._focus_current_search()

                self.assertEqual(field.selectedText(), query)
                self.assertEqual(
                    self.window.operation_status.text(),
                    "Search ready • type to filter this workspace",
                )

    def test_ctrl_f_reports_when_workspace_has_no_search(self) -> None:
        self._activate(ApfCategory.GETTING_STARTED)

        self.window._focus_current_search()

        self.assertEqual(
            self.window.operation_status.text(),
            "This workspace has no available search box • press Ctrl+1 for categories",
        )


if __name__ == "__main__":
    unittest.main()
