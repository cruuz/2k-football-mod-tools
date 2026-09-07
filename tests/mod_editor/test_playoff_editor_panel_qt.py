"""Offscreen postseason list, notices, edits, journal and signed-copy regression."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtCore import Qt
from mod_editor.core import nfl2k5_franchise_save as fs
from tests.mod_editor.test_franchise_panel_qt import _PanelCase
from tests.mod_editor.test_nfl2k5_franchise_save import F0, F1, FRANCHISE1
from tests.mod_editor.test_nfl2k5_playoff_editor import synthetic_postseason, inventory


class PostseasonPanelTests(_PanelCase):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()

    def test_every_synthetic_row_has_editable_dates_or_explicit_played_notice(self):
        data = bytearray(synthetic_postseason())
        data[0x917EA + (18 * 17 + 3) * 8] = 3  # one completed wild-card game
        self.load(bytes(data))
        page = self.page
        page.base_year_spin.setValue(2026)
        page.tabs.setCurrentIndex(1)
        self.assertEqual(page.week_combo.currentText(), 'All postseason')
        self.assertEqual(page.schedule_table.rowCount(), 13)
        self.assertEqual(page.week_combo.itemText(17), 'Week 18')
        self.assertEqual(page.week_combo.itemText(18), 'Wild Card')
        self.assertEqual(page.week_combo.itemText(21), 'Super Bowl')
        self.assertNotIn('Pro Bowl', [page.week_combo.itemText(i) for i in range(page.week_combo.count())])
        identities = [(r, s) for r, s, _ in inventory(page.save)]
        allowed = set()
        for line, identity in enumerate(identities):
            with self.subTest(cell=identity):
                page.allow_played_check.setChecked(False)
                page.schedule_table.selectRow(line)
                game = page._selected_game()
                self.assertEqual((game.row, game.slot), identity)
                self.assertEqual(page.schedule_table.item(line, 7).text(), game.row_name.title())
                for widget in (page.month_spin, page.day_spin, page.hour_spin, page.minute_spin, page.apply_game_button):
                    self.assertTrue(widget.isEnabled())
                for known, column, combo in ((game.away_known, 1, page.away_combo), (game.home_known, 2, page.home_combo)):
                    self.assertEqual(combo.isEnabled(), known)
                    if not known:
                        self.assertEqual(page.schedule_table.item(line, column).text(), 'To be decided')
                        self.assertEqual(combo.currentIndex(), -1)
                        self.assertEqual(combo.placeholderText(), 'To be decided')
                before = page.save.to_bytes()
                page.month_spin.setValue(3)
                page.day_spin.setValue(27)
                page.hour_spin.setValue(9)
                page.minute_spin.setValue(56)
                if game.played:
                    self.assertIn('has been played', page.game_notice.text())
                    self.assertIn('has been played', page.schedule_table.item(line, 3).toolTip())
                    page.apply_game_button.click()
                    self.assertEqual(page.save.to_bytes(), before)
                    self.assertIn('has been played', page.status_label.text())
                    page.allow_played_check.setChecked(True)
                    self.assertIn('Editing is allowed', page.game_notice.text())
                    self.assertEqual(page.day_spin.value(), 27)  # checkbox keeps the pending edit
                page.apply_game_button.click()
                updated = page._selected_game()
                self.assertEqual((updated.row, updated.slot), identity)
                self.assertEqual((updated.month, updated.day, updated.hour, updated.minute), (3, 27, 9, 56))
                self.assertEqual((updated.flags, updated.scores, updated.home, updated.away),
                                 (game.flags, game.scores, game.home, game.away))
                self.assertTrue(page.edit_labels()[-1].startswith(game.row_name.title()))
                allowed.update(game.offset + n for n in (3, 4, 6, 7))
        receipt, written = self.write()
        self.assertEqual(len(receipt['franchise_edits']), 13)
        self.assertEqual({i for i, (a, b) in enumerate(zip(data, written)) if a != b}, allowed)
        self.assertTrue(self.panel.load_save(self.root / 'copy'))
        self.assertEqual(self.page.schedule_table.rowCount(), 13)
        self.assertFalse(self.page.allow_played_check.isChecked())
        self.assertEqual(self.page.save.to_bytes(), written)

    def test_round_filters_identity_sparse_slots_and_undo_redo(self):
        data = bytearray(synthetic_postseason())
        at = 0x917EA + (18 * 17 + 1) * 8
        data[at:at + 8] = bytes([7]) + bytes(7)
        self.load(bytes(data))
        page = self.page
        page.tabs.setCurrentIndex(1)
        for row, count in ((18, 5), (19, 4), (20, 2), (21, 1)):
            page.week_combo.setCurrentIndex(row)
            self.assertEqual(page.schedule_table.rowCount(), count)
            self.assertEqual(page._selected_game().row, row)
            self.assertTrue(page.day_spin.isEnabled())
        page.week_combo.setCurrentIndex(18)
        self.assertEqual([page.schedule_table.item(i, 0).data(Qt.UserRole) for i in range(5)],
                         [(18, s) for s in (0, 2, 3, 4, 5)])
        page.schedule_table.selectRow(4)
        page.minute_spin.setValue(57)
        page.apply_game_button.click()
        self.assertEqual(page.save.game(18, 5).minute, 57)
        changed = page.save.to_bytes()
        page.undo_button.click()
        self.assertEqual(page.save.to_bytes(), data)
        page.redo_button.click()
        self.assertEqual(page.save.to_bytes(), changed)
        self.assertEqual((page._selected_game().row, page._selected_game().slot), (18, 5))
        page.week_combo.setCurrentIndex(16)
        self.assertEqual(page.schedule_table.rowCount(), 0)
        self.assertFalse(page.day_spin.isEnabled())
        self.assertIn('Select a game', page.game_notice.text())

    def test_retail_round_filter_and_all_postseason_include_pro_bowl(self):
        self.load(synthetic_postseason(weeks=17, teams=12))
        page = self.page
        self.assertEqual(page.schedule_table.rowCount(), 12)
        self.assertEqual([page.schedule_table.item(i, 7).text() for i in range(12)],
                         ['Wild Card'] * 4 + ['Divisional'] * 4 + ['Conference'] * 2 + ['Super Bowl', 'Pro Bowl'])
        page.week_combo.setCurrentIndex(21)
        self.assertEqual(page.schedule_table.rowCount(), 1)
        self.assertEqual(page.schedule_table.item(0, 1).text(), 'NFC')
        self.assertEqual(page.schedule_table.item(0, 2).text(), 'AFC')
        page.day_spin.setValue(22)
        page.apply_game_button.click()
        self.assertEqual(page.save.game(21, 0).day, 22)

    def check_real(self, path, expected):
        if not path.is_file():
            self.skipTest(f'private preserved franchise save missing: {path}')
        original = path.read_bytes()
        self.assertTrue(self.panel.load_save(path.parents[3]))
        page = self.page
        page.tabs.setCurrentIndex(1)
        page.week_combo.setCurrentIndex(fs.GRID_ROWS)
        self.assertEqual(page.schedule_table.rowCount(), expected)
        identities = [(r, s) for r, s, _ in inventory(page.save)]
        for line, identity in enumerate(identities):
            page.schedule_table.selectRow(line)
            game = page._selected_game()
            self.assertEqual((game.row, game.slot), identity)
            self.assertEqual(page.schedule_table.item(line, 7).text(), game.row_name.title())
            self.assertIn('has been played', page.game_notice.text())
            self.assertFalse(page.edit_game(*identity, day=27, hour=8))
            self.assertEqual(page.save.to_bytes(), original)
        if identities:
            page.allow_played_check.setChecked(True)
            page.day_spin.setValue(27)
            page.hour_spin.setValue(8)
            page.apply_game_button.click()
            self.assertEqual((page.save.game(21, 0).day, page.save.game(21, 0).hour), (27, 8))
        _receipt, written = self.write()
        self.assertEqual(written, page.save.to_bytes())
        self.assertTrue(self.panel.load_save(self.root / 'copy'))
        self.assertEqual(self.page.save.to_bytes(), written)
        self.assertEqual(path.read_bytes(), original)

    def test_real_finn_before_ir(self):
        self.check_real(F0, 0)

    def test_real_finn_after_ir(self):
        self.check_real(F1, 0)

    def test_real_lions_every_row_has_played_notice(self):
        self.check_real(FRANCHISE1, 12)


if __name__ == '__main__':
    unittest.main()
