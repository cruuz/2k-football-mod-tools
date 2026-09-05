"""The 2K5 shell after the Build & Share rework: navigation rows, page tabs, header titles.

Gameplay = sliders inspector + Throw Distance & Arc + Gameplay Patches; Presentation = the
scorebug inventory + ESPN Scorebug & Ticker + Commentary; Audio = Audio Cues + Sounds; Text & Team
Identity carries the EDGE rename; ★ Rosters is the first of five special rows and ★ Build & Share the last, with the Build
and Share tabs.
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
        self.assertEqual(len(rows), 1 + len(PRODUCT_CATEGORY_ORDER) + 5)
        self.assertEqual(rows[0], "Getting Started")
        self.assertEqual(rows[-5], "★ Rosters")
        self.assertEqual(rows[-4], "★ Models")
        self.assertEqual(rows[-3], "Animations")
        self.assertFalse(self.window._animations_panel.import_button.isEnabled())
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
        self.assertIn("Game Fixes", titles)
        self.assertIn("Saves & Sliders", titles)
        self.assertEqual(titles[0], "Game Fixes")
        for moved in ("ESPN Scorebug & Ticker", "Commentary", "Share"):
            self.assertNotIn(moved, titles)
        patches = self.window._gameplay_patches_panel
        assert patches is not None
        self.assertEqual(set(patches.checks), {"catch_slider", "accel_ramp", "draft_ai", "returner_fix", "progression", "team_column", "kick_rules", "overtime", "camera", "position_row", "probowl_order", "penalties", "uniform_choice", "kick_laces", "prospect_names", "franchise_practice", "player_star", "depth_roles", "dynamic_kickoff", "depth_chart_rows", "practice_squad", "depth_locks", "season_cap", "xbe_space", "kickoff_relocated", "guardian_cap", "screen_timing", "scorebug", "scorebug_runtime", "music_policy", "music_unlock", "music_userlist"})

    def test_presentation_page_has_inventory_scorebug_and_commentary(self) -> None:
        page = self.window._category_pages[ProductCategory.SCOREBUG_PRESENTATION]
        self.assertIsInstance(page, QTabWidget)
        assert isinstance(page, QTabWidget)
        self.assertEqual(_tab_titles(page), ["Scorebug Images", "ESPN Scorebug & Ticker", "Commentary"])
        self.assertEqual(page.currentIndex(), 0)
        self.assertIs(page.widget(1), self.window._presentation_panel)
        self.assertIs(page.widget(2), self.window._commentary_panel)

    def test_audio_page_has_cues_and_sounds_tabs(self) -> None:
        page = self.window._category_pages[ProductCategory.AUDIO]
        self.assertIsInstance(page, QTabWidget)
        assert isinstance(page, QTabWidget)
        self.assertEqual(page.objectName(), "audioTabs")
        self.assertEqual(_tab_titles(page), ["Audio Cues", "Music", "Replace a Sound"])
        self.assertEqual(page.currentIndex(), 0)
        self.assertIs(page.widget(0), self.window._audio_panel)
        self.assertIs(page.widget(1), self.window._music_panel)
        self.assertIs(page.widget(2), self.window._sounds_panel)
        self.assertTrue(page.isAncestorOf(self.window._audio_panel))

    def test_team_identity_page_hosts_the_edge_rename(self) -> None:
        page = self.window._category_pages[ProductCategory.TEAM_IDENTITY]
        self.assertIsInstance(page, QTabWidget)
        assert isinstance(page, QTabWidget)
        self.assertEqual(_tab_titles(page), ["Game Text", "Position Names (EDGE)"])
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

    def test_build_year_context_reaches_roster_and_franchise_without_byte_edits(self):
        import tempfile
        from pathlib import Path
        from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise
        from mod_editor.core import nfl2k5_roster_records as rr
        panel = self.window._roster_editor_panel
        self.window._build_panel.season_check.setChecked(True)
        original = synthetic_franchise(year_field=27)
        with tempfile.TemporaryDirectory() as folder:
            save = Path(folder) / "SAVEGAME.DAT"
            save.write_bytes(original)
            save.with_name("EXTRA").write_bytes(rr.sign_save(original))
            self.assertTrue(panel.load_save(save), panel.status_label.text())
        self.assertEqual(panel.document.base_year, 2026)
        self.assertEqual(panel.document.reference_year, 2053)
        self.assertEqual(panel.franchise_panel.save.header.display_year, 2053)
        before = bytes(panel.document.body)
        player = panel.document.players[0]
        self.assertEqual(panel._baseline_record(player).reference_year, 2053)
        panel.franchise_panel.base_year_spin.setValue(2004)
        self.assertEqual(panel.document.reference_year, 2031)
        self.assertEqual(panel.franchise_panel.save.header.year_field, 27)
        self.assertEqual(bytes(panel.document.body), before)
        self.assertEqual(panel._baseline_record(player).reference_year, 2031)
        self.assertFalse(panel.franchise_panel.edits)





class BuildShareActionBarTests(StudioShellLayoutTests):
    """Build & Share hides the texture-project controls and feeds Launch Latest Build."""

    def test_build_share_page_hides_the_texture_project_controls(self) -> None:
        nav = self.window.navigation
        project_widgets = (self.window.edit_count, self.window.undo_button, self.window.revert_all_button,
                           self.window.check_images_button, self.window.build_button)
        nav.setCurrentRow(1)
        self.assertTrue(all(not w.isHidden() for w in project_widgets))
        nav.setCurrentRow(nav.count() - 1)          # ★ Build & Share
        self.assertTrue(all(w.isHidden() for w in project_widgets))
        self.assertFalse(self.window.launch_button.isHidden())
        self.assertFalse(self.window.configure_xemu_button.isHidden())
        nav.setCurrentRow(nav.count() - 2)          # ★ Create a Play: controls return
        self.assertTrue(all(not w.isHidden() for w in project_widgets))

    def test_a_finished_build_tab_copy_is_offered_to_launch(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "ESPN NFL 2K5 (modded).xiso.iso"
            image.write_bytes(b"\0" * 64)
            self.window._on_build_tab_built({"target": str(image), "steps": [{"step": "xbe"}]})
            facade = self.window.facade
            if hasattr(facade, "register_external_build") and hasattr(facade, "_last_build"):
                self.assertEqual(getattr(facade._last_build, "output_xiso", None), image)
            # a missing file must not crash the window
            self.window._on_build_tab_built({"target": str(Path(tmp) / "gone.iso")})


if __name__ == "__main__":
    unittest.main()
