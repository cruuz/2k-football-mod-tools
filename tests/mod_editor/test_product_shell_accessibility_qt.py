"""Headless keyboard, scaling, and screen-reader checks for both product shells."""

from __future__ import annotations

import os
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QFrame, QTabWidget  # noqa: E402

from mod_editor.apf_studio.gui import ApfStudioMainWindow  # noqa: E402
from mod_editor.core.product_catalog import ProductCategory  # noqa: E402
from mod_editor.gui.studio_qt import (  # noqa: E402
    BrowseOnlyFacade,
    StudioMainWindow,
)


class ProductShellAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.two_k5 = StudioMainWindow(
            facade=BrowseOnlyFacade(), offer_recovery=False
        )
        self.apf = ApfStudioMainWindow(offer_recovery=False)
        self.application.processEvents()

    def tearDown(self) -> None:
        self.two_k5.deleteLater()
        self.apf.deleteLater()
        self.application.processEvents()

    def test_shell_navigation_is_named_and_keyboard_reachable(self) -> None:
        for window in (self.two_k5, self.apf):
            with self.subTest(product=window.windowTitle()):
                self.assertEqual(window.sidebar_shortcut.key().toString(), "Ctrl+1")
                self.assertEqual(window.navigation.accessibleName(), "Modding categories")
                self.assertIn("Ctrl+1", window.navigation.accessibleDescription())
                self.assertIn("Ctrl+1", window.navigation.toolTip())

    def test_2k5_find_shortcut_targets_the_active_page_search(self) -> None:
        self.assertEqual(self.two_k5.find_shortcut.key().toString(), "Ctrl+F")
        self.two_k5.navigation.setCurrentRow(1)
        self.application.processEvents()
        self.assertIs(self.two_k5._current_search_field(), self.two_k5.uniform_search)
        self.two_k5.uniform_search.setText("Giants away")

        self.two_k5._focus_current_search()

        self.assertEqual(self.two_k5.uniform_search.selectedText(), "Giants away")
        self.assertEqual(
            self.two_k5.operation_status.text(),
            "Search ready • type to filter this page",
        )
        self.assertTrue(self.two_k5.uniform_search.property("studioSearch"))
        self.assertIn("Ctrl+F", self.two_k5.uniform_search.accessibleDescription())

    def test_2k5_find_shortcut_reaches_visible_specialist_searches(self) -> None:
        assert self.two_k5._text_roster_panel is not None
        assert self.two_k5._roster_panel is not None
        assert self.two_k5._crib_panel is not None
        assert self.two_k5._playbooks_panel is not None
        expectations = (
            (2, self.two_k5._roster_panel.current_search, "Eli Manning"),
            (3, self.two_k5._text_roster_panel.text_search, "salary cap"),
            (8, self.two_k5._crib_panel.search, "team photos"),
            (11, self.two_k5._playbooks_panel.search, "shotgun routes"),
        )
        for row, field, query in expectations:
            with self.subTest(page=self.two_k5.navigation.item(row).text().strip()):
                self.two_k5.navigation.setCurrentRow(row)
                self.application.processEvents()
                page = self.two_k5.pages.currentWidget()
                self.assertIsNotNone(page)
                assert page is not None
                self.assertTrue(field.isVisibleTo(page))
                self.assertIs(self.two_k5._current_search_field(), field)

                field.setText(query)
                self.two_k5._focus_current_search()

                self.assertEqual(field.selectedText(), query)
                self.assertEqual(
                    self.two_k5.operation_status.text(),
                    "Search ready • type to filter this page",
                )

    def test_2k5_roster_editors_live_with_players_not_team_identity(self) -> None:
        assert self.two_k5._roster_panel is not None
        assert self.two_k5._text_roster_panel is not None
        rosters_page = self.two_k5._category_pages[
            ProductCategory.ROSTERS_PLAYERS
        ]
        self.assertIsInstance(rosters_page, QTabWidget)
        assert isinstance(rosters_page, QTabWidget)
        self.assertEqual(
            [
                rosters_page.tabText(index)
                for index in range(rosters_page.count())
            ],
            # Player Assets joins a player to the face textures and
            # portrait that belong to them, which the app could not
            # answer before.
            ["Players & Numbers", "Portraits & Faces", "Player Assets"],
        )
        self.assertIs(rosters_page.widget(0), self.two_k5._roster_panel)
        self.assertEqual(
            [
                self.two_k5._roster_panel.tabs.tabText(index)
                for index in range(self.two_k5._roster_panel.tabs.count())
            ],
            ["Current Roster Players", "Historical Teams & Players"],
        )
        self.assertEqual(
            [
                self.two_k5._text_roster_panel.tabs.tabText(index)
                for index in range(self.two_k5._text_roster_panel.tabs.count())
            ],
            ["All Text"],
        )

    def test_shell_status_and_build_actions_have_screen_reader_copy(self) -> None:
        expectations = (
            (
                self.two_k5,
                self.two_k5.progress_bar,
                "Build a separate modded XISO",
                "xemu",
            ),
            (
                self.apf,
                self.apf.progress,
                "Build a separate modded game folder",
                "Xenia",
            ),
        )
        for window, progress, build_name, emulator in expectations:
            with self.subTest(product=window.windowTitle()):
                self.assertEqual(
                    window.operation_status.accessibleName(),
                    "Current operation status",
                )
                self.assertEqual(
                    progress.accessibleName(), "Current operation progress"
                )
                self.assertEqual(window.build_button.accessibleName(), build_name)
                self.assertIn(
                    emulator.casefold(),
                    window.launch_button.accessibleName().casefold(),
                )
                self.assertTrue(window.build_button.accessibleDescription())
                self.assertTrue(window.launch_button.accessibleDescription())

        hostile_status = '<img src="file:///tmp/status-probe"> Undo literal'
        self.two_k5._set_status(hostile_status)
        self.assertEqual(self.two_k5.operation_status.textFormat(), Qt.PlainText)
        self.assertEqual(self.two_k5.operation_status.text(), hostile_status)

    def test_shell_chrome_can_expand_for_larger_system_fonts(self) -> None:
        for window in (self.two_k5, self.apf):
            header = window.findChild(QFrame, "header")
            footer = window.findChild(QFrame, "footer")
            with self.subTest(product=window.windowTitle()):
                self.assertIsNotNone(header)
                self.assertIsNotNone(footer)
                assert header is not None and footer is not None
                self.assertGreater(header.maximumHeight(), header.minimumHeight())
                self.assertGreater(footer.maximumHeight(), footer.minimumHeight())
                style = window.styleSheet()
                self.assertIn("QListWidget#navigation:focus", style)
                self.assertIn("border: 2px solid", style)
                self.assertIn("QListWidget#assetList:focus", style)


if __name__ == "__main__":
    unittest.main()
