"""b77 e5: the modern/classic book swap in Build and Playbooks & Plays, and three newcomer fixes.

Offscreen Qt over the real facade methods (the c2x fixture: a real session setter, no disc).
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt5.QtWidgets import QApplication, QMessageBox

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_playbook_pack as packs
from mod_editor.gui import build_panel_qt
from mod_editor.gui.build_panel_qt import BuildPanel
from mod_editor.gui.playbook_pack_dialog_qt import (
    BookSetTeamsDialog, book_set_status_text, BOOK_SET_TEAM_NAMES)
from mod_editor.gui.playbooks_panel_qt import PlaybooksPanel
from test_playbooks_link_table_export_ui import _Host
from test_playbooks_panel_qt import _book
from test_softdrink_book_set import host as real_facade

APP = QApplication.instance() or QApplication([])
GENERIC = str(ROOT / "data/playbooks/softdrink_match_coverage.2k5book")


class _FacadeHost(_Host):
    """The panel host surface plus the two book-set methods, delegating to the real facade code."""

    def __init__(self, facade):
        self.facade = facade

    def project_softdrink_book_set(self):
        return self.facade.project_softdrink_book_set()

    def set_softdrink_book_set(self, teams=None):
        return self.facade.set_softdrink_book_set(teams)

    def project_build_settings(self):
        return self.facade.project_build_settings()


class _SourceReadyFacade:
    """A facade wrapper: source_ready and the build-settings pair the Build panel uses."""

    source_ready = True

    def __init__(self, facade):
        self._facade = facade

    def __getattr__(self, name):
        return getattr(self._facade, name)


def build_panel(facade=None):
    panel = BuildPanel(facade)
    return panel


class BookSetDialogHelpersTests(unittest.TestCase):
    def test_status_text(self):
        self.assertIn("Open your game disc", book_set_status_text(None))
        self.assertEqual(book_set_status_text({"modern_count": 32, "classic_count": 0, "incomplete_teams": ()}),
                         "Modern 32, Classic 0")
        text = book_set_status_text({"modern_count": 1, "classic_count": 30, "incomplete_teams": ("KC",)})
        self.assertEqual(text, "Modern 1, Classic 30, half-set 1 (KC)")

    def test_every_team_has_a_name(self):
        self.assertEqual(set(BOOK_SET_TEAM_NAMES), set(packs.TEAM_BOOKS))

    def test_teams_dialog_reads_and_returns_the_selection(self):
        dialog = BookSetTeamsDialog({"modern_teams": ("KC", "NYG"), "incomplete_teams": ("ARZ",)})
        try:
            self.assertEqual(dialog.selected_teams(), ("KC", "NYG"))
            self.assertEqual(dialog.count_label.text(), "Modern 2, Classic 30")
            self.assertIn("half set", dialog.checks["ARZ"].text())
            dialog.all_button.click()
            self.assertEqual(dialog.selected_teams(), packs.TEAM_BOOKS)
            dialog.none_button.click()
            self.assertEqual(dialog.selected_teams(), ())
            self.assertEqual(dialog.count_label.text(), "Modern 0, Classic 32")
        finally:
            dialog.deleteLater()


class BuildPanelBookSetTests(unittest.TestCase):
    def setUp(self):
        self.facade = _SourceReadyFacade(real_facade())
        self.panel = build_panel(self.facade)
        self.addCleanup(self.panel.deleteLater)
        self.signals = []
        self.panel.book_set_changed.connect(lambda: self.signals.append(1))

    def test_without_a_disc_the_buttons_explain_instead_of_acting(self):
        panel = build_panel(None)
        try:
            self.assertFalse(panel.book_all_button.isEnabled())
            self.assertIn("Open your game disc", panel.book_set_status.text())
            self.assertIn("Open your game disc", panel.book_all_button.toolTip())
            panel._apply_book_set(None)          # a click that cannot happen is still harmless
            self.assertEqual(panel.playbook_packs, [])
        finally:
            panel.deleteLater()

    def test_status_and_all_none_choose(self):
        self.assertEqual(self.panel.book_set_status.text(), "Modern 0, Classic 32")
        self.assertTrue(self.panel.book_all_button.isEnabled())
        self.panel.book_all_button.click()
        self.assertEqual(self.panel.book_set_status.text(), "Modern 32, Classic 0")
        self.assertEqual(len(self.panel.playbook_packs), 64)
        self.assertEqual(self.panel.packs_list.count(), 64)
        # the panel and the project hold the same list, so a later capture cannot restore stale packs
        self.assertEqual(self.panel.playbook_packs, self.facade.project_build_settings()["playbook_packs"])
        self.assertIn("playbooks (Modern 32, Classic 0)", self.panel.selected_labels())
        self.assertNotIn("playbook packs (64)", self.panel.selected_labels())
        self.panel.book_none_button.click()
        self.assertEqual(self.panel.book_set_status.text(), "Modern 0, Classic 32")
        self.assertEqual(self.panel.playbook_packs, [])
        self.assertEqual(self.facade.project_build_settings()["playbook_packs"], [])
        self.assertEqual(len(self.signals), 2)

    def test_choose_teams_uses_the_dialog_selection(self):
        class Dialog:
            Accepted = 1
            seen = None

            def __init__(self, info, parent=None):
                Dialog.seen = info

            def exec_(self):
                return 1

            def selected_teams(self):
                return ("NYG", "KC")

            def deleteLater(self):
                pass

        with mock.patch.object(build_panel_qt, "BookSetTeamsDialog", Dialog):
            self.panel.book_choose_button.click()
        self.assertEqual(Dialog.seen["modern_count"], 0)
        self.assertEqual(self.panel.book_set_status.text(), "Modern 2, Classic 30")
        self.assertEqual({Path(p).name for p in self.panel.playbook_packs},
                         {"softdrink_kc_modern.2k5book", "softdrink_giants_modern.2k5book",
                          "softdrink_kc_defense.2k5book", "softdrink_nyg_defense.2k5book"})

    def test_a_cancelled_dialog_changes_nothing(self):
        class Dialog:
            Accepted = 1

            def __init__(self, info, parent=None):
                pass

            def exec_(self):
                return 0

            def deleteLater(self):
                pass

        with mock.patch.object(build_panel_qt, "BookSetTeamsDialog", Dialog):
            self.panel.book_choose_button.click()
        self.assertEqual(self.panel.playbook_packs, [])
        self.assertEqual(self.signals, [])

    def test_other_packs_survive_and_pack_edits_reach_the_project(self):
        self.panel._add_match_coverage_pack()
        self.assertEqual(self.facade.project_build_settings()["playbook_packs"], [GENERIC])
        self.assertEqual(self.panel.selected_labels()[-1], "playbook packs (1)")   # no books chosen: plain count
        self.panel.book_all_button.click()
        self.assertEqual(self.panel.playbook_packs[0], GENERIC)
        self.assertEqual(len(self.panel.playbook_packs), 65)
        self.assertEqual(self.panel.selected_labels()[-1], "playbooks (Modern 32, Classic 0; 1 other pack)")
        self.panel.book_none_button.click()
        self.assertEqual(self.panel.playbook_packs, [GENERIC])

    def test_pending_panel_packs_are_flushed_before_the_swap(self):
        # a pack the page holds but the project has not seen yet (restore, programmatic edit)
        self.panel.set_playbook_packs(["user/mine.2k5book"])
        self.assertEqual(self.facade.project_build_settings().get("playbook_packs", []), [])
        self.panel.book_all_button.click()
        self.assertIn("user/mine.2k5book", self.facade.project_build_settings()["playbook_packs"])
        self.assertEqual(self.panel.playbook_packs, self.facade.project_build_settings()["playbook_packs"])

    def test_a_refused_change_shows_the_reason_and_keeps_the_list(self):
        with mock.patch.object(self.facade._facade, "set_softdrink_book_set", side_effect=ValueError("no good")), \
                mock.patch.object(build_panel_qt, "show_operation_error") as shown:
            self.panel.book_all_button.click()
        shown.assert_called_once()
        self.assertEqual(self.panel.playbook_packs, [])
        self.assertEqual(self.signals, [])

    def test_confirmation_says_modern_and_classic_not_64_packs(self):
        self.panel.book_all_button.click()
        plan = self.panel.plan()
        self.assertEqual(len(plan.playbook_packs), 64)
        text = self.panel.confirmation_text(plan)
        self.assertIn("playbooks: Modern 32, Classic 0", text)
        self.assertNotIn("playbook packs: 64", text)

    def test_preset_note_names_the_books(self):
        with mock.patch.object(build_panel_qt.mod_build, "PRESETS", mod_build.PRESETS):
            self.panel.apply_preset("softdrink_basic")
        note = self.panel.preset_note.text()
        self.assertIn("Playbooks: Modern 0, Classic 32", note)
        self.assertIn("More inputs", note)
        self.assertIn("modern or classic playbooks", self.panel.advanced_details.button.text())

    def test_shell_style_restore_refreshes_the_status(self):
        self.facade.set_softdrink_book_set(["KC"])
        self.panel.set_playbook_packs(self.facade.project_build_settings()["playbook_packs"])
        self.assertEqual(self.panel.book_set_status.text(), "Modern 1, Classic 31")


class PlaybooksPanelBookSetTests(unittest.TestCase):
    def setUp(self):
        self.facade = real_facade()
        self.host = _FacadeHost(self.facade)
        self.panel = PlaybooksPanel(self.host)
        self.addCleanup(self.panel.deleteLater)
        self.flushed = []
        self.panel.flush_build_choices = lambda: self.flushed.append(1)
        self.signals = []
        self.panel.book_set_changed.connect(lambda: self.signals.append(1))
        self.book = _book(asset_id="private.play.kc", name="KC", formation_name="I Pro",
                          play_name="Quick Test", family_id=0, outer_index=10)
        self.util = _book(asset_id="private.play.gen", name="GEN", formation_name="I Pro",
                          play_name="Quick Test", family_id=0, outer_index=11)
        self.panel._all_books = (self.book, self.util)

    def select(self, book):
        self.panel.selected_asset_id = book.asset_id
        self.panel.refresh_book_set()

    def test_all_modern_all_classic_and_status(self):
        self.assertEqual(self.panel.book_set_status.text(), "Modern 0, Classic 32")
        self.panel.book_all_modern_button.click()
        self.assertEqual(self.panel.book_set_status.text(), "Modern 32, Classic 0")
        self.assertEqual(len(self.facade.project_build_settings()["playbook_packs"]), 64)
        self.panel.book_all_classic_button.click()
        self.assertEqual(self.panel.book_set_status.text(), "Modern 0, Classic 32")
        self.assertEqual(self.facade.project_build_settings()["playbook_packs"], [])
        self.assertEqual(len(self.signals), 2)
        self.assertEqual(len(self.flushed), 2)

    def test_selected_team_toggles_only_that_team(self):
        self.facade.set_softdrink_book_set(["NYG"])
        self.select(self.book)
        self.assertFalse(self.panel.book_modern_button.isChecked())
        self.assertTrue(self.panel.book_classic_button.isChecked())
        self.assertIn("KC", self.panel.book_set_team_label.text())
        self.panel.book_modern_button.click()
        info = self.facade.project_softdrink_book_set()
        self.assertEqual(info["modern_teams"], ("KC", "NYG"))
        self.assertTrue(self.panel.book_modern_button.isChecked())
        self.assertFalse(self.panel.book_classic_button.isChecked())
        self.assertEqual(self.panel.book_set_status.text(), "Modern 2, Classic 30")
        self.panel.book_classic_button.click()
        self.assertEqual(self.facade.project_softdrink_book_set()["modern_teams"], ("NYG",))
        self.assertEqual(self.panel.book_set_status.text(), "Modern 1, Classic 31")
        self.assertTrue(self.panel.book_classic_button.isChecked())

    def test_generic_packs_are_not_touched(self):
        self.facade.set_project_build_settings({"playbook_packs": [GENERIC]})
        self.select(self.book)
        self.panel.book_modern_button.click()
        packs_now = self.facade.project_build_settings()["playbook_packs"]
        self.assertIn(GENERIC, packs_now)
        self.assertEqual(len(packs_now), 3)

    def test_a_utility_book_cannot_be_set_and_says_why(self):
        self.select(self.util)
        self.assertIn("Select", self.panel.book_set_team_label.text())
        reason = str(self.panel.book_modern_button.property("disableReason"))
        self.assertIn("32 team books", reason)
        with mock.patch.object(QMessageBox, "information") as info:
            self.panel.book_modern_button.click()
        info.assert_called_once()
        self.assertEqual(self.facade.project_softdrink_book_set()["modern_count"], 0)
        self.assertEqual(self.signals, [])
        self.assertFalse(self.panel.book_modern_button.isChecked())

    def test_a_half_set_team_shows_neither_button_checked(self):
        self.facade.set_project_build_settings({"playbook_packs": [
            str(mod_build.softdrink_book_paths(["KC"])[0])]})
        self.select(self.book)
        self.assertFalse(self.panel.book_modern_button.isChecked())
        self.assertFalse(self.panel.book_classic_button.isChecked())
        self.assertIn("half set", self.panel.book_set_team_label.text())
        self.assertIn("half-set 1 (KC)", self.panel.book_set_status.text())
        self.panel.book_classic_button.click()       # normalised to classic
        self.assertEqual(self.facade.project_softdrink_book_set()["incomplete_teams"], ())

    def test_host_without_the_methods_or_a_disc_explains(self):
        panel = PlaybooksPanel(_Host())
        try:
            self.assertIn("Open your game disc", panel.book_set_status.text())
            self.assertIn("Open your game disc", str(panel.book_all_modern_button.property("disableReason")))
            with mock.patch.object(QMessageBox, "information") as info:
                panel.book_all_modern_button.click()
            info.assert_called_once()
        finally:
            panel.deleteLater()


class ShellWiringTests(unittest.TestCase):
    """studio_qt._connect_book_set keeps Build and Playbooks on one list, whichever page exists first."""

    def make_shell(self, facade):
        from mod_editor.gui import studio_qt

        # The real wiring methods on a plain object: they only touch these attributes.
        class Shell:
            _connect_book_set = studio_qt.StudioMainWindow._connect_book_set
            _flush_build_for_book_set = studio_qt.StudioMainWindow._flush_build_for_book_set
            _playbooks_book_set_changed = studio_qt.StudioMainWindow._playbooks_book_set_changed
            _build_book_set_changed = studio_qt.StudioMainWindow._build_book_set_changed

        shell = Shell()
        shell.facade = facade
        shell._book_set_wired = set()
        shell._build_panel = None
        shell._playbooks_panel = None
        shell._mark_workspace_changed = mock.Mock()
        shell._capture_music_build_settings = mock.Mock()
        return shell

    def test_either_order_wires_once_and_changes_sync_both_ways(self):
        facade = _SourceReadyFacade(real_facade())
        shell = self.make_shell(facade)
        build = build_panel(facade)
        playbooks = PlaybooksPanel(_FacadeHost(facade))
        try:
            shell._playbooks_panel = playbooks
            shell._connect_book_set()                  # playbooks first
            shell._build_panel = build
            shell._connect_book_set()                  # then build
            shell._connect_book_set()                  # idempotent
            self.assertEqual(shell._book_set_wired, {"playbooks", "build"})
            playbooks.book_all_modern_button.click()
            self.assertEqual(build.playbook_packs, facade.project_build_settings()["playbook_packs"])
            self.assertEqual(build.book_set_status.text(), "Modern 32, Classic 0")
            shell._capture_music_build_settings.assert_called()      # the flush
            self.assertEqual(shell._mark_workspace_changed.call_count, 1)
            build.book_none_button.click()
            self.assertEqual(playbooks.book_set_status.text(), "Modern 0, Classic 32")
            self.assertEqual(shell._mark_workspace_changed.call_count, 2)
        finally:
            build.deleteLater()
            playbooks.deleteLater()

    def test_an_unfinished_unrelated_choice_does_not_block_the_swap(self):
        facade = _SourceReadyFacade(real_facade())
        shell = self.make_shell(facade)
        shell._build_panel = object()
        shell._capture_music_build_settings = mock.Mock(side_effect=ValueError("Choose a music project"))
        shell._flush_build_for_book_set()          # swallowed on purpose


class RealShellTests(unittest.TestCase):
    """The real StudioMainWindow, with the c2x facade methods attached to its browse-only facade."""

    def test_the_two_pages_share_one_list_end_to_end(self):
        import tempfile
        from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow

        with tempfile.TemporaryDirectory() as tmp:
            xbe = Path(tmp) / "default.xbe"
            # Lazy pages: build only the two this feature joins (the eager window also needs the
            # 940 MB private uniform inventories, which a light worktree does not carry).
            window = StudioMainWindow(eager_pages=False, facade=BrowseOnlyFacade(), offer_recovery=False)
            try:
                APP.processEvents()
                from mod_editor.core.product_catalog import ProductCategory
                window._build_category_page(ProductCategory.PLAYBOOKS_PLAYS)
                window._build_build_share_page()
                self.assertEqual(window._book_set_wired, {"playbooks", "build"})
                real = real_facade()
                facade = window.facade
                facade.source_ready, facade.source_path, facade.source_display_name = True, xbe, xbe.name
                for name in ("project_softdrink_book_set", "set_softdrink_book_set",
                             "project_build_settings", "set_project_build_settings"):
                    setattr(facade, name, getattr(real, name))
                build, playbooks = window._build_panel, window._playbooks_panel
                playbooks.refresh_book_set()
                build.refresh_book_set()
                self.assertEqual(build.book_set_status.text(), "Modern 0, Classic 32")
                dirty_before = window._workspace_revision
                playbooks.book_all_modern_button.click()
                self.assertEqual(len(build.playbook_packs), 64)
                self.assertEqual(build.book_set_status.text(), "Modern 32, Classic 0")
                self.assertGreater(window._workspace_revision, dirty_before)
                self.assertEqual(len(real.project_build_settings()["playbook_packs"]), 64)
                build.book_none_button.click()
                self.assertEqual(playbooks.book_set_status.text(), "Modern 0, Classic 32")
                self.assertEqual(real.project_build_settings().get("playbook_packs", []), [])
            finally:
                window.deleteLater()
                APP.processEvents()


class HiresBudgetIdentityTests(unittest.TestCase):
    """Found while ticking every option for the confirmation test: the artwork budget preview unpacked a
    5-item identity from the 6-item tuple _hires_identity returns, so it raised in the timer slot."""

    def test_preview_unpacks_the_identity_the_page_builds(self):
        panel = build_panel(None)
        try:
            panel.hires_pack_check.setEnabled(True)
            panel.hires_pack_check.setChecked(True)
            panel._hires_budget_identity = panel._hires_identity()
            with mock.patch.object(panel._pool, "start") as start:
                panel._preview_hires_budget()
            start.assert_called_once()
        finally:
            panel.deleteLater()


class NewcomerPolishTests(unittest.TestCase):
    def test_long_confirmation_keeps_ok_reachable(self):
        panel = build_panel(None)
        try:
            boxes = [(k, b) for k, b in panel._boxes().items() if not k.startswith("music")]
            for key, box in boxes[:40]:
                box.setEnabled(True)
                box.setChecked(True)
            plan = panel.plan()
            full = panel.confirmation_text(plan)
            brief = panel.confirmation_text(plan, brief=True)
            self.assertGreater(len(panel.selected_labels()), 20)
            self.assertLess(len(brief), len(full) // 2)
            self.assertLessEqual(brief.count("\n"), 8)
            self.assertIn("more; the full list is under Show Details", brief)
            shown = {}

            def fake_exec(box):
                shown["text"] = box.text()
                shown["details"] = box.detailedText()
                shown["buttons"] = box.standardButtons()
                shown["default"] = box.defaultButton().text()
                return QMessageBox.Ok

            with mock.patch.object(QMessageBox, "exec_", fake_exec):
                self.assertTrue(panel._confirm_make_disc(plan))
            self.assertEqual(shown["text"], brief)
            self.assertEqual(shown["details"], full)
            self.assertIn("Cancel", shown["default"])
            with mock.patch.object(QMessageBox, "exec_", return_value=QMessageBox.Cancel):
                self.assertFalse(panel._confirm_make_disc(plan))
        finally:
            panel.deleteLater()

    def test_short_confirmation_is_unchanged_and_has_no_details(self):
        panel = build_panel(None)
        try:
            plan = panel.plan()
            self.assertEqual(panel.confirmation_text(plan), panel.confirmation_text(plan, brief=True))
            shown = {}

            def fake_exec(box):
                shown["details"] = box.detailedText()
                return QMessageBox.Ok

            with mock.patch.object(QMessageBox, "exec_", fake_exec):
                panel._confirm_make_disc(plan)
            self.assertEqual(shown["details"], "")
        finally:
            panel.deleteLater()

    def test_onedrive_note_appears_for_a_synced_output_and_not_otherwise(self):
        from mod_editor.core import nfl2k5_build_service as service
        panel = build_panel(None)
        try:
            panel.target_field.setText("C:/Users/Tee/OneDrive/Desktop/SOFTDRINK 2K28.xiso.iso")
            self.assertTrue(panel.synced_note.isHidden())
            synced = (Path("C:/Users/Tee/OneDrive"), "the OneDrive folder")
            with mock.patch.object(service, "_cloud_synced_root", return_value=synced):
                panel.target_field.setText("C:/Users/Tee/OneDrive/Desktop/other.xiso.iso")
                panel.source_field.setText("C:/Users/Tee/OneDrive/Games/ESPN NFL 2K5.iso")
                panel._refresh()
                self.assertFalse(panel.synced_note.isHidden())
                text = panel.synced_note.text()
                self.assertIn("OneDrive warning", text)
                self.assertIn("the disc copy", text)
                self.assertIn("the source disc", text)
                self.assertIn("C:\\2K5", text)
            panel.target_field.setText("D:/xemu/plain.xiso.iso")
            self.assertTrue(panel.synced_note.isHidden())
            with mock.patch.object(service, "_cloud_synced_root", side_effect=OSError("denied")):
                self.assertEqual(panel.synced_folder_advice(), "")      # advice never breaks the page
        finally:
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
