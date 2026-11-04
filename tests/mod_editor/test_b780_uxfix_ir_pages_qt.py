"""b780-uxfix: the ★ Rosters > Franchise injured reserve page shows and edits modern injured reserve (IR1's API).

A save that a modern-IR build wrote shows a club's 20 slots, the games each player has missed, the season-ending flag,
whether he can come back now (or the game's own reason why not) and the club's returns used of 8. Place and Activate go
through nfl2k5_injured_reserve_save, so the game's rules and texts apply. A legacy save keeps its 5 slots and says how
modern IR starts. Offscreen; the modern tests use IR1's real franchise save (2026 week 0, user club BAL), skipped
without it.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_injured_reserve_save as irs  # noqa: E402
from mod_editor.gui.franchise_panel_qt import IR_COLUMNS, IR_LEGACY_NOTE  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402

IR_SAVE = Path(os.environ.get("NFL2K5_B780_IR_SAVE",
                              "/home/noah/2k-worktrees/.b77-scratch/b780/ir1/emu1/UDATA/53450030/495231574954"))
CAMPBELL, CUEVAS = 127, 126            # on IR and healthy with 4 games missed; injured 6 weeks on the roster
_APP: list[QApplication] = []


class _Case(unittest.TestCase):
    def setUp(self):
        if not _APP:
            _APP.append(QApplication.instance() or QApplication([]))
        self.panel = RosterEditorPanel()
        self.addCleanup(self.panel.deleteLater)
        self.folder = Path(tempfile.mkdtemp(prefix="uxfix-ir-"))

    @property
    def page(self):
        return self.panel.franchise_panel

    def _select_team(self, team):
        combo = self.page.ir_team_combo
        combo.setCurrentIndex(combo.findData(team))
        self.page._refresh_injured_reserve()

    def _row_of(self, index):
        table = self.page.ir_table
        for row in range(table.rowCount()):
            item = table.item(row, 2)
            if item is not None and item.text() == str(index):
                return row
        return None

    def _cells(self, row):
        return [self.page.ir_table.item(row, column).text() for column in range(len(IR_COLUMNS))]


@unittest.skipUnless((IR_SAVE / "SAVEGAME.DAT").is_file(), "needs IR1's modern-IR franchise save")
class ModernInjuredReserveTests(_Case):
    def setUp(self):
        super().setUp()
        self.assertTrue(self.panel.load_save(IR_SAVE))
        self.team = next(e.team for e in irs.read_state(fs.FranchiseSave.load(IR_SAVE)).entries
                         if e.player_index == CAMPBELL)
        self._select_team(self.team)

    def test_the_page_shows_twenty_slots_games_missed_and_who_can_return(self):
        self.assertEqual(self.page.ir_table.rowCount(), irs.CAP)
        self.assertEqual(self.page.ir_table.columnCount(), len(IR_COLUMNS))
        row = self._row_of(CAMPBELL)
        self.assertIsNotNone(row)
        self.assertEqual(self._cells(row)[1:], ["Calais Campbell", str(CAMPBELL), "4", "No", "Yes"])
        self.assertIn("0 of 8 used", self.page.ir_returns_label.text())
        self.page.ir_table.selectRow(row)
        self.assertNotIn("Can't", self.page.activate_ir_button.toolTip())

    def test_place_and_activate_follow_the_games_rules_and_reach_the_written_copy(self):
        self.assertTrue(self.page.place_on_ir(self.team, CUEVAS))
        row = self._row_of(CUEVAS)
        self.assertIsNotNone(row)
        cells = self._cells(row)
        self.assertEqual(cells[3], "0")
        self.assertEqual(cells[5], irs.REASONS["too_soon"])              # the game's own words
        self.page.ir_table.selectRow(row)
        self.assertIn(irs.REASONS["too_soon"], self.page.activate_ir_button.toolTip())
        self.assertFalse(self.page.activate_from_ir(self.team, CUEVAS))  # refused before anything changes
        self.assertIn(irs.REASONS["too_soon"], self.page.status_label.text())
        self.assertTrue(self.page.activate_from_ir(self.team, CAMPBELL))
        self.assertIsNone(self._row_of(CAMPBELL))
        self.assertIn("1 of 8 used", self.page.ir_returns_label.text())
        receipt = self.panel.write_copy_to(self.folder / "copy")
        self.assertTrue(receipt["signed"])
        written = irs.read_state(fs.FranchiseSave.load(self.folder / "copy"))
        self.assertTrue(written.extension)
        on_ir = {e.player_index for e in written.club(self.team)}
        self.assertIn(CUEVAS, on_ir)
        self.assertNotIn(CAMPBELL, on_ir)
        self.assertEqual(written.returns_used[self.team], 1)

    def test_undo_puts_the_modern_state_back(self):
        before = irs.read_state(self.page.save)
        self.assertTrue(self.page.activate_from_ir(self.team, CAMPBELL))
        self.panel.undo()
        self.page._refresh_injured_reserve()
        self.assertEqual(irs.read_state(self.page.save), before)
        self.assertIsNotNone(self._row_of(CAMPBELL))


class LegacyInjuredReserveTests(_Case):
    def test_a_legacy_save_keeps_its_five_slots_and_says_how_modern_ir_starts(self):
        from test_franchise_panel_qt import synthetic_franchise_with_coach
        from test_roster_editor_panel_franchise import write_container
        source = write_container(self.folder / "legacy", synthetic_franchise_with_coach(year_field=7, user_team=0))
        self.assertTrue(self.panel.load_save(source))
        self._select_team(0)
        self.assertEqual(self.page.ir_table.rowCount(), fs.IR_SLOTS)
        self.assertEqual(self.page.ir_returns_label.text(), IR_LEGACY_NOTE)
        self.assertNotIn("—", IR_LEGACY_NOTE)


if __name__ == "__main__":
    unittest.main()
