"""The 2K5 shell after the Build & Share rework: navigation rows, page tabs, header titles.

Gameplay = sliders inspector + Throw Distance & Arc + Gameplay Patches; Presentation = the
scorebug inventory + ESPN Scorebug & Ticker + Commentary; Audio = Audio Cues + Sounds; Text & Team
Identity carries the EDGE rename; ★ Build & Share is the second special row with the Build and
Share tabs.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QTabWidget  # noqa: E402

from mod_editor.core.product_catalog import PRODUCT_CATEGORY_ORDER, ProductCategory  # noqa: E402
from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow  # noqa: E402


def _tab_titles(widget: QTabWidget) -> list[str]:
    return [widget.tabText(i).replace("&&", "&") for i in range(widget.count())]


class StudioShellLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = StudioMainWindow(facade=BrowseOnlyFacade(), offer_recovery=False)
        self.application.processEvents()

    def tearDown(self) -> None:
        self.window.deleteLater()
        self.application.processEvents()

    def _row_texts(self) -> list[str]:
        nav = self.window.navigation
        return [nav.item(i).text().strip() for i in range(nav.count())]

    def test_navigation_rows_and_pages_line_up(self) -> None:
        rows = self._row_texts()
        self.assertEqual(len(rows), 1 + len(PRODUCT_CATEGORY_ORDER) + 3)
        self.assertEqual(rows[0], "Getting Started")
        self.assertEqual(rows[-3], "★ Models")
        self.assertEqual(rows[-2], "★ Create a Play")
        self.assertEqual(rows[-1], "★ Build & Share")
        self.assertIn("Gameplay", rows)
        self.assertIn("Presentation", rows)
        self.assertNotIn("Sliders & Gameplay", rows)
        self.assertNotIn("Scorebug & Presentation", rows)
        self.assertEqual(self.window.pages.count(), self.window.navigation.count())

    def test_header_title_follows_every_row(self) -> None:
        nav = self.window.navigation
        for row in range(nav.count()):
            nav.setCurrentRow(row)
            self.application.processEvents()
            expected = nav.item(row).text().strip().lstrip("★ ").strip()
            self.assertEqual(self.window.page_title.text(), expected, msg=f"row {row}")

    def test_gameplay_page_carries_throw_and_gameplay_patches_only(self) -> None:
        gameplay = self.window._category_pages[ProductCategory.SLIDERS_GAMEPLAY]
        titles = _tab_titles(gameplay.tabs)
        self.assertIn("Throw Distance & Arc", titles)
        self.assertIn("Gameplay Patches", titles)
        for moved in ("ESPN Scorebug & Ticker", "Commentary", "Share"):
            self.assertNotIn(moved, titles)
        patches = self.window._gameplay_patches_panel
        assert patches is not None
        self.assertEqual(set(patches.checks), {"catch_slider", "accel_ramp", "draft_ai", "returner_fix", "progression", "team_column", "kick_rules", "overtime", "camera", "seven_on_seven"})

    def test_presentation_page_has_inventory_scorebug_and_commentary(self) -> None:
        page = self.window._category_pages[ProductCategory.SCOREBUG_PRESENTATION]
        self.assertIsInstance(page, QTabWidget)
        assert isinstance(page, QTabWidget)
        self.assertEqual(_tab_titles(page), ["Inventory", "ESPN Scorebug & Ticker", "Commentary"])
        self.assertEqual(page.currentIndex(), 0)
        self.assertIs(page.widget(1), self.window._presentation_panel)
        self.assertIs(page.widget(2), self.window._commentary_panel)

    def test_audio_page_has_cues_and_sounds_tabs(self) -> None:
        page = self.window._category_pages[ProductCategory.AUDIO]
        self.assertIsInstance(page, QTabWidget)
        assert isinstance(page, QTabWidget)
        self.assertEqual(page.objectName(), "audioTabs")
        self.assertEqual(_tab_titles(page), ["Audio Cues", "Sounds"])
        self.assertEqual(page.currentIndex(), 0)
        self.assertIs(page.widget(0), self.window._audio_panel)
        self.assertIs(page.widget(1), self.window._sounds_panel)
        self.assertTrue(page.isAncestorOf(self.window._audio_panel))

    def test_team_identity_page_hosts_the_edge_rename(self) -> None:
        page = self.window._category_pages[ProductCategory.TEAM_IDENTITY]
        self.assertIsInstance(page, QTabWidget)
        assert isinstance(page, QTabWidget)
        self.assertEqual(_tab_titles(page), ["Text & Team Identity", "EDGE Rename"])
        self.assertIs(page.widget(0), self.window._text_roster_panel)
        edge = self.window._edge_panel
        assert edge is not None
        self.assertEqual(set(edge.checks), {"edge_rename", "scheme_labels"})

    def test_build_and_share_page_has_both_tabs(self) -> None:
        nav = self.window.navigation
        nav.setCurrentRow(nav.count() - 1)
        self.application.processEvents()
        page = self.window._build_share_page
        self.assertIsInstance(page, QTabWidget)
        assert isinstance(page, QTabWidget)
        self.assertEqual(_tab_titles(page), ["Build", "Share"])
        self.assertIs(page.widget(0), self.window._build_panel)
        self.assertIs(page.widget(1), self.window._share_panel)
        self.assertEqual(self.window.page_title.text(), "Build & Share")


if __name__ == "__main__":
    unittest.main()
