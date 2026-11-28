"""Flying Finn's GameSave Editor on the Rosters page, round 2, row M3 (b81, lane finn-r2): select several players
and act on the selection.

Finn: Edit > Select All (Ctrl+A), then Global Edit selected, release, clear stats on the selection. The grid takes
Shift and Ctrl click and Ctrl+A; ``selected_players()`` lists the selection in grid order (also when the grid is
sorted); Release to free agency on the selection is checked as one batch before anything changes, is all or nothing
and is one undo; the Global editor has an "Only the selected players" scope; the one-player commands wait.

Offscreen Qt on synthetic rosters; the real SOFTDRINK roster save (4,096 primary records, reserves) is used when it
is present (``NFL2K5_SOFTDRINK_ROSTER_SAVE``) and skipped, with its path, when it is not.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QItemSelectionModel, Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import GlobalEditDialog, RosterEditorPanel  # noqa: E402
from test_nfl2k5_roster_records import league_body  # noqa: E402

SOFTDRINK_ROSTER_SAVE = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_ROSTER_SAVE",
    "/media/noah/Storage/2K5-project/beta81/isolated-data/FC3-native-roster.zip"))


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def select_rows(panel: RosterEditorPanel, rows: list[int]) -> None:
    """Shift/Ctrl-click's result: exactly these grid rows selected, the last one current."""

    table = panel.player_table
    table.clearSelection()
    model = table.selectionModel()
    for row in rows:
        model.select(table.model().index(row, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
    table.setCurrentCell(rows[-1], 0, QItemSelectionModel.NoUpdate)
    _app().processEvents()


class _Case(unittest.TestCase):
    club_size = 46

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.body = league_body(self.club_size)
        self.panel = RosterEditorPanel()
        self.panel.load_document(rr.load_body(self.body), label="league")
        self.application.processEvents()
        self.panel.team_list.setCurrentRow(self.panel._team_list_row("team", 0))
        self.application.processEvents()

    def tearDown(self) -> None:
        self.panel.close()
        self.panel.deleteLater()
        self.application.processEvents()

    @property
    def document(self) -> rr.RosterDocument:
        assert self.panel.document is not None
        return self.panel.document

    def free_agents(self) -> int:
        return len(self.document.free_agents)


class SelectionTests(_Case):
    def test_ctrl_a_on_the_grid_selects_every_visible_row(self) -> None:
        table = self.panel.player_table
        table.setFocus()
        self.panel.setVisible(True)
        QTest.keyClick(table, Qt.Key_A, Qt.ControlModifier)
        self.application.processEvents()
        shown = self.panel.visible_players()
        self.assertEqual(len(shown), self.club_size)
        self.assertEqual(self.panel.selected_players(), shown)
        self.assertEqual(self.panel._selected_count, self.club_size)
        QTest.keyClick(table, Qt.Key_Escape)            # QTest leaves Ctrl in the modifier state; clear it

    def test_select_all_entry_in_the_right_click_menu(self) -> None:
        menu = self.panel.grid_menu()
        entry = next(a for a in menu.actions() if a.text() == f"Select all {self.club_size} shown")
        self.assertEqual(entry.shortcut().toString(), "Ctrl+A")
        entry.trigger()
        self.assertEqual(len(self.panel.selected_players()), self.club_size)

    def test_selected_players_follow_a_sorted_grid_in_grid_order(self) -> None:
        self.panel.sort_by("speed")
        rows = self.panel._rows
        select_rows(self.panel, [9, 2, 5])
        self.assertEqual(self.panel.selected_players(), [rows[2], rows[5], rows[9]])
        self.assertIs(self.panel.selected_player(), rows[5], "the card keeps the current row")
        self.panel.team_order_button.click()
        select_rows(self.panel, [4, 1])
        self.assertEqual(self.panel.selected_players(), [self.panel._rows[1], self.panel._rows[4]])

    def test_one_row_behaves_as_before(self) -> None:
        panel = self.panel
        player = panel._rows[3]
        panel.select_player(player)
        self.assertEqual(panel.selected_players(), [player])
        self.assertIs(panel.selected_player(), player)
        for widget in (panel.copy_button, panel.swap_button, panel.release_button, panel.team_menu_button):
            self.assertTrue(widget.isEnabled())
        self.assertEqual(panel.release_button.text(), "Release to free agency")
        self.assertIn("pointer list", panel.release_button.toolTip())
        self.assertTrue(panel.copy_player())
        qbs = self.document.depth_order(0, 0)
        panel.select_player(qbs[1])
        self.assertTrue(panel.up_button.isEnabled())
        self.assertTrue(panel.move_selected(-1))
        self.assertIs(self.document.depth_order(0, 0)[0], qbs[1])

    def test_with_several_selected_the_one_player_commands_wait_and_say_why(self) -> None:
        panel = self.panel
        panel.select_player(panel._rows[0])
        self.assertTrue(panel.copy_player())
        tip = "3 players are selected. Choose one player to use this."
        select_rows(panel, [1, 2, 3])
        for widget in (panel.copy_button, panel.paste_button, panel.swap_button, panel.team_menu_button,
                       panel.up_button, panel.down_button, panel.template_button):
            self.assertFalse(widget.isEnabled(), widget.text())
            self.assertEqual(widget.toolTip(), tip)
        self.assertTrue(panel.release_button.isEnabled())
        self.assertEqual(panel.release_button.text(), "Release 3 selected")
        before = self.document.to_body()
        self.assertFalse(panel.copy_player())
        self.assertEqual(panel.paste_player("all"), 0)
        self.assertFalse(panel.move_selected(1))
        self.assertIsNone(panel.send_selected_to(1))
        self.assertIsNone(panel.open_swap_dialog())
        self.assertFalse(panel.place_selected_on_ir())
        self.assertFalse(panel.clear_career_stats()[0])
        self.assertEqual(self.document.to_body(), before)
        self.assertIn(tip, panel.status_label.text())
        menu = {a.text(): a for a in panel.grid_menu().actions() if a.text()}
        for name in ("Copy player", "Paste player", "Place on IR…", "Clear his career stats…"):
            self.assertFalse(menu[name].isEnabled(), name)
        self.assertIn("Release the 3 selected to free agency", menu)
        self.assertIn("Clear career stats of the 3 selected…", menu)
        # back to one row: everything returns, and the tips and text are the original ones
        panel.select_player(panel._rows[5])
        self.assertTrue(panel.copy_button.isEnabled() and panel.swap_button.isEnabled())
        self.assertEqual(panel.release_button.text(), "Release to free agency")
        self.assertNotIn("selected", panel.copy_button.toolTip())

    def test_a_right_click_inside_the_selection_keeps_it(self) -> None:
        from PyQt5.QtCore import QPoint
        panel = self.panel
        select_rows(panel, [1, 2, 3])
        table = panel.player_table
        point = QPoint(5, table.rowViewportPosition(2) + 3)
        shown = {}
        from unittest import mock
        with mock.patch.object(panel.__class__, "grid_menu", lambda self_: shown.setdefault(
                "n", len(self_.selected_players())) and mock.MagicMock()):
            panel._show_grid_menu(point)
        self.assertEqual(shown["n"], 3)


class BatchReleaseTests(_Case):
    def test_three_players_go_to_free_agency_in_one_undo(self) -> None:
        panel = self.panel
        free_before = self.free_agents()
        rows = [2, 5, 9]
        chosen = [panel._rows[r] for r in rows]
        select_rows(panel, rows)
        receipt = panel.release_selected()
        assert receipt is not None
        self.assertEqual(receipt["count"], 3)
        for player in chosen:
            self.assertTrue(self.document.is_free_agent(player), player.display)
            self.assertIsNone(self.document.club_of(player))
        self.assertEqual(self.free_agents(), free_before + 3)
        self.assertEqual(len(self.document.team_players(0)), self.club_size - 3)
        self.assertEqual(panel.undo_stack.depth, (1, 0), "one undo entry")
        self.assertIn(f"Released 3 players to free agency", panel.status_label.text())
        self.assertIn(f"{free_before + 3} free agents now", panel.status_label.text())
        released = self.document.to_body()
        self.assertTrue(panel.undo().endswith("release 3 players") or "release 3 players" in panel.status_label.text())
        self.assertEqual(self.document.to_body(), self.body, "every slot, depth rank and lock is back")
        self.assertEqual([p for p in self.document.team_players(0)][:0], [])
        panel.redo()
        self.assertEqual(self.document.to_body(), released)
        self.assertEqual(self.free_agents(), free_before + 3)

    def test_a_batch_that_would_take_a_club_below_42_changes_nothing_and_names_the_club(self) -> None:
        panel = self.panel
        select_rows(panel, [0, 1, 2, 3, 4])            # 46 - 5 = 41
        before = self.document.to_body()
        self.assertIsNone(panel.release_selected())
        self.assertEqual(self.document.to_body(), before)
        self.assertEqual(panel.undo_stack.depth, (0, 0))
        text = panel.status_label.text()
        club = self.document.teams[0].display
        self.assertIn("Nothing was released", text)
        self.assertIn(f"{club} must maintain at least 42", text)
        self.assertIn("would leave", text)
        select_rows(panel, [0, 1, 2, 3])               # 46 - 4 = 42 is allowed
        self.assertIsNotNone(panel.release_selected())
        self.assertEqual(len(self.document.team_players(0)), 42)

    def test_free_agents_and_the_free_agent_ceiling_refuse_the_whole_batch_by_name(self) -> None:
        panel = self.panel
        panel.team_list.setCurrentRow(panel._team_list_row("free_agent", -1))
        self.application.processEvents()
        select_rows(panel, [0, 1])
        names = [p.display for p in panel.selected_players()]
        before = self.document.to_body()
        self.assertIsNone(panel.release_selected())
        text = panel.status_label.text()
        for name in names:
            self.assertIn(f"{name} is already a free agent", text)
        self.assertEqual(self.document.to_body(), before)
        # the ceiling: fill the list to its capacity, then a batch of two is named and refused
        panel.team_list.setCurrentRow(panel._team_list_row("team", 0))
        document = self.document
        select_rows(panel, [0, 1])
        capacity = document.free_agent_capacity
        original = document.free_agents
        try:
            document.free_agents = list(original) + [0] * (capacity - len(original) - 1)
            plan, problems = panel.release_problems(panel.selected_players())
            self.assertEqual(len(plan), 2)
            self.assertTrue(any("Max free agents reached" in p and "room for 1 more and 2 would" in p
                                for p in problems), problems)
        finally:
            document.free_agents = original

    def test_a_mixed_batch_where_one_player_is_refused_releases_nobody(self) -> None:
        panel = self.panel
        select_rows(panel, [1, 2])
        victim = panel._rows[2]
        victim.record.values["injured_reserve"] = 0xEE                 # on injured reserve
        before = self.document.to_body()
        self.assertIsNone(panel.release_selected())
        self.assertIn(victim.display, panel.status_label.text())
        self.assertEqual(self.document.to_body(), before)
        self.assertEqual(panel.undo_stack.depth, (0, 0))


class GlobalEditSelectedTests(_Case):
    def test_the_selected_scope_changes_only_those_players(self) -> None:
        panel = self.panel
        dialog = GlobalEditDialog(panel, panel)
        self.assertFalse(dialog.selected_only.isEnabled(), "one row or none: the scope is not offered")
        self.assertEqual(dialog.selected_only.text(), "Only the selected players (1)")
        dialog.deleteLater()
        select_rows(panel, [3, 4, 8])
        chosen = panel.selected_players()
        dialog = GlobalEditDialog(panel, panel)
        self.assertTrue(dialog.selected_only.isEnabled())
        self.assertEqual(dialog.selected_only.text(), "Only the selected players (3)")
        dialog.selected_only.setChecked(True)
        self.assertEqual(dialog.scope_label.text(), "Scope: the 3 selected players")
        dialog.attribute.setCurrentIndex(dialog.attribute.findData("speed"))
        dialog.mode.setCurrentIndex(dialog.mode.findData("equal"))
        dialog.value.setValue(11)
        rows = dialog.refresh_preview()
        keys = {(r["pool"], r["index"]) for r in rows}
        self.assertTrue(keys <= {(p.pool, p.index) for p in chosen})
        before = {(p.pool, p.index): p.record.values["speed"] for p in self.document.players}
        dialog._apply()
        after = {(p.pool, p.index): p.record.values["speed"] for p in self.document.players}
        changed = {k for k in before if before[k] != after[k]}
        self.assertEqual(changed, keys)
        self.assertTrue(changed)
        self.assertTrue(all(after[(p.pool, p.index)] == 11 for p in chosen))
        self.assertEqual(panel.undo_stack.depth, (1, 0))
        panel.undo()
        self.assertEqual({(p.pool, p.index): p.record.values["speed"] for p in self.document.players}, before)
        dialog.deleteLater()

    def test_without_the_scope_the_whole_league_is_still_edited(self) -> None:
        select_rows(self.panel, [3, 4, 8])
        rows = self.panel.global_edit_preview(attribute="speed", mode="equal", value=11)
        self.assertGreater(len(rows), 3)
        rows = self.panel.global_edit_preview(attribute="speed", mode="equal", value=11, selected_only=True)
        self.assertLessEqual(len(rows), 3)


class ClearStatsSelectedTests(_Case):
    def test_the_menu_entry_routes_the_selection_through_clear_career_stats(self) -> None:
        from unittest import mock
        panel = self.panel
        select_rows(panel, [1, 2, 3])
        chosen = panel.selected_players()
        entry = next(a for a in panel.grid_menu().actions() if a.text() == "Clear career stats of the 3 selected…")
        # a body is not an Xbox save, so the reason check (the existing one) is what answers here
        self.assertFalse(entry.isEnabled())
        self.assertIn("Xbox save", entry.toolTip())
        with mock.patch.object(RosterEditorPanel, "clear_stats_reason", return_value=""), \
                mock.patch.object(RosterEditorPanel, "clear_career_stats", return_value=(True, "")) as clear:
            entry = next(a for a in panel.grid_menu().actions()
                         if a.text() == "Clear career stats of the 3 selected…")
            self.assertTrue(entry.isEnabled())
            entry.trigger()
        clear.assert_called_once_with(chosen)


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class SoftdrinkSelectionTests(unittest.TestCase):
    """The real 4,096-player roster: speed of Select all, and a batch release through the signed copy."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()
        cls.panel = RosterEditorPanel()
        assert cls.panel.load_save(SOFTDRINK_ROSTER_SAVE)
        cls.application.processEvents()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.panel.deleteLater()
        cls.application.processEvents()

    def test_select_all_and_the_menu_stay_fast_on_the_free_agent_list(self) -> None:
        panel = self.panel
        panel.team_list.setCurrentRow(panel._team_list_row("free_agent", -1))
        self.application.processEvents()
        shown = panel.visible_players()
        self.assertGreater(len(shown), 500)
        started = time.perf_counter()
        panel.select_all_players()
        menu = panel.grid_menu()
        took = time.perf_counter() - started
        self.assertEqual(len(panel.selected_players()), len(shown))
        self.assertLess(took, 1.0, f"Select all and the menu took {took:.2f} s on {len(shown)} rows")
        self.assertTrue(any(a.text() == f"Select all {len(shown)} shown" for a in menu.actions()))
        panel.player_table.clearSelection()

    def test_two_players_of_one_club_are_released_through_a_signed_copy(self) -> None:
        panel = self.panel
        document = panel.document
        assert document is not None
        panel.team_list.setCurrentRow(panel._team_list_row("team", 0))
        self.application.processEvents()
        players = panel.visible_players()
        pair = None
        for first in range(len(players)):
            for second in range(first + 1, len(players)):
                if not panel.release_problems([players[first], players[second]])[1]:
                    pair = (first, second)
                    break
            if pair:
                break
        self.assertIsNotNone(pair, "a releasable pair on the first club")
        assert pair is not None
        club = document.teams[0]
        names = [players[i].display for i in pair]
        slots_before = len(club.slots)
        free_before = len(document.free_agents)
        select_rows(panel, list(pair))
        started = time.perf_counter()
        receipt = panel.release_selected()
        self.assertLess(time.perf_counter() - started, 5.0)
        assert receipt is not None
        self.assertEqual(receipt["count"], 2)
        with tempfile.TemporaryDirectory() as folder:
            written = panel.write_copy_to(Path(folder) / "copy.zip")
            self.assertTrue(written["signed"])
            container = rr.SaveContainer.load(Path(folder) / "copy.zip")
            self.assertTrue(container.verified)
            back = rr.load_save(Path(folder) / "copy.zip", detect=True)
        for name in names:
            player = next(p for p in back.players if p.display == name and p.pool == "primary")
            self.assertTrue(back.is_free_agent(player), name)
        self.assertEqual(len(back.teams[0].slots), slots_before - 2)
        self.assertEqual(len(back.free_agents), free_before + 2)
        panel.undo()
        self.assertEqual(len(document.teams[0].slots), slots_before)
        self.assertEqual(len(document.free_agents), free_before)


if __name__ == "__main__":
    unittest.main()
