"""Offscreen UI identity, refusal, shared undo and signed-copy witnesses."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QCheckBox
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
from mod_editor.gui.franchise_panel_qt import FranchiseEdit, FranchisePanel
from tests.mod_editor.test_rosters_reserves_abilities import league_save, document
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise


class ControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.panel = RosterEditorPanel()

    def tearDown(self):
        self.panel.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def load(self, payload=None):
        source = self.root/'source'; source.mkdir()
        raw = payload or synthetic_franchise()
        (source/'SAVEGAME.DAT').write_bytes(raw)
        (source/'EXTRA').write_bytes(rr.sign_save(raw))
        self.assertTrue(self.panel.load_save(source))
        return self.panel.document

    def group(self, kind, team=0):
        for row in range(self.panel.team_list.count()):
            item = self.panel.team_list.item(row)
            if tuple(item.data(Qt.UserRole)) == (kind, team):
                self.panel.team_list.setCurrentRow(row)
                return item
        self.fail(f'missing group {kind}/{team}')

    def test_reserve_groups_same_cards_search_and_identity(self):
        doc = document()
        doc.demote_active(0, 1)
        live = self.load(doc.to_body())
        item = self.group('team')
        self.assertEqual(item.text(), 'IND · 2 active + 1 reserve')
        self.assertEqual(self.group('reserve').text().strip(), 'Reserves · 1')
        player = self.panel.selected_player()
        self.assertEqual((player.pool, player.index), ('primary', 1))
        self.assertEqual(self.panel.player_table.item(0, 5).text(), 'IND Reserves')
        self.assertIn('Marvin Harrison', self.panel.header_name.text())
        self.assertTrue(self.panel.promote_button.isEnabled())
        self.assertFalse(self.panel.demote_button.isEnabled())
        for button in (self.panel.release_button, self.panel.team_menu_button, self.panel.swap_button,
                       self.panel.up_button, self.panel.down_button):
            self.assertFalse(button.isEnabled())
        self.panel.search.setText('Harrison')
        self.assertEqual(self.panel.visible_players(), [player])
        self.panel.search.setText('absent name')
        self.assertEqual(self.panel.visible_players(), [])
        self.panel.search.clear()
        self.panel.set_field(player, 'speed', 77)
        self.assertEqual(self.panel.player_table.item(0, 5).text(), 'IND Reserves')
        self.panel.promote_button.click()
        self.assertEqual(live.reserve_owner, {})
        self.assertEqual(live.teams[0].slots[-1], player.offset)
        self.assertEqual(self.panel.player_table.rowCount(), 0)
        self.panel.undo()
        self.assertEqual(self.panel.selected_player(), player)
        self.assertEqual(player.record.get('speed'), 77)
        self.assertEqual(self.group('reserve', 1).text().strip(), 'Reserves · 0')

    def test_locks_independent_transfer_undo_unlock_and_arrows(self):
        self.panel.load_document(rr.load_body(synthetic_body()))
        doc = self.panel.document
        wr, hb = doc.players[1:3]
        doc.set_depth_lock(wr, 'kr1')
        before = doc.to_body()
        self.assertTrue(self.panel.set_lock(hb, 'kr1', True))
        self.assertFalse(wr.record.depth_locks['kr1'])
        self.assertTrue(hb.record.depth_locks['kr1'])
        self.panel.undo()
        self.assertEqual(doc.to_body(), before)
        self.panel.redo()
        self.panel.select_player(hb)
        hb.record.set_ability('speedster', True)
        self.panel.unlock_button.click()
        self.assertFalse(any(hb.record.depth_locks.values()))
        self.panel.undo()
        self.assertTrue(hb.record.depth_locks['kr1'])
        self.assertTrue(hb.record.abilities['speedster'])
        locks = {p.index: p.record.depth_locks for p in doc.players}
        self.panel.move_selected(-1)
        self.assertEqual({p.index: p.record.depth_locks for p in doc.players}, locks)
        controls = self.panel.player_table.cellWidget(0, 6).findChildren(QCheckBox)
        self.assertEqual([c.text() for c in controls], ['Rank', 'Side', 'KR1', 'KR2', 'PR'])
        self.assertIn('Retail auto-depth ignores', self.panel.locks_note.text())

    def test_paired_sides_conflicts_and_save_guard(self):
        doc = self.load()
        p, peer = doc.players[:2]
        for code, left, right in ((14, 'LT', 'RT'), (13, 'LG', 'RG')):
            p.record.set('position', code)
            p.record.set('depth_rank', 0); p.record.set('depth_side', 0)
            self.assertIn(left + ' + ' + right, self.panel._depth_text(p))
            p.record.set('depth_rank', 1)
            self.assertNotIn(left, self.panel._depth_text(p))
        p.record.set('depth_rank', 0)
        peer.record.set('position', 13); peer.record.set('depth_rank', 0)
        self.assertTrue(self.panel.set_lock(p, 'rank', True))
        before, history = doc.to_body(), self.panel.undo_stack.depth
        self.assertFalse(self.panel.set_lock(peer, 'rank', True))
        self.assertEqual(doc.to_body(), before)
        self.assertEqual(self.panel.undo_stack.depth, history)
        peer.record.set_depth_lock('rank', True)  # simulate conflicting raw import
        with self.assertRaisesRegex(rr.RosterRecordError, 'conflicting depth locks'):
            self.panel.write_copy_to(self.root/'blocked.zip')
        self.assertFalse((self.root/'blocked.zip').exists())

    def test_abilities_bulk_undo_masks_and_csv(self):
        self.panel.load_document(rr.load_body(synthetic_body()))
        doc = self.panel.document
        p = doc.players[0]
        p.record.values['unknown_52'] = 0x13
        p.record.set('star_tag', 1)
        self.panel.select_player(p)
        self.panel.ability_checks['speedster'].click()
        self.assertTrue(p.record.abilities['speedster'])
        # Independent later bit edits must survive an ability-only undo.
        p.record.set_depth_lock('side', False)
        self.panel.undo()
        self.assertEqual(p.record.values['unknown_52'], 0x11)
        self.assertEqual(p.record.get('star_tag'), 1)
        self.panel.set_abilities(self.panel.visible_players(), {'spin': True, 'juke': True})
        self.assertTrue(all(x.record.abilities['spin'] for x in self.panel.visible_players()))
        self.assertEqual(p.record.values['unknown_52'] & 0x1f, 0x11)
        self.panel.undo()
        self.assertFalse(any(x.record.abilities['spin'] for x in self.panel.visible_players()))
        text = self.panel.export_csv_text(True)
        self.assertIn('speedster,right_stick_moves,juke,spin,truck,hurdle,stiff_arm', text)
        self.assertEqual(self.panel.import_csv_text(text)['fields'], 0)

    def test_composed_reserve_name_release_sign_ir_undo_redo_and_reopen(self):
        doc = self.load(league_save(44))
        reserve = doc.players[0]
        self.panel.select_player(reserve)
        self.assertTrue(self.panel.reserve_selected(False))
        self.assertEqual(doc.reserve_owner, {('primary', 0): 0})
        self.assertFalse(self.panel.save_edits_button.isEnabled())
        self.group('reserve')
        self.panel.set_field(reserve, 'agility', 88)
        self.panel.first_field.setText('Free')
        self.panel._name_committed('first')
        self.assertEqual(reserve.first, 'Free')
        self.group('team')
        self.panel.select_player(doc.players[1])
        self.assertIsNotNone(self.panel.release_selected())
        self.group('free_agent', -1)
        self.panel.select_player(doc.players[1])
        self.assertIsNotNone(self.panel.send_selected_to(1))
        self.assertTrue(self.panel.franchise_panel.place_on_ir(0, 2))
        self.assertTrue(self.panel.franchise_panel.activate_from_ir(0, 2))
        composed = doc.to_body()
        labels = self.panel.franchise_panel.edit_labels()
        count = self.panel.undo_stack.depth[0]
        for _ in range(count): self.panel.undo()
        self.assertEqual(doc.to_body(), doc.original)
        for _ in range(count): self.panel.redo()
        self.assertEqual(doc.to_body(), composed)
        self.assertEqual(self.panel.franchise_panel.edit_labels(), labels)
        with self.assertRaisesRegex(rr.RosterRecordError, 'Build & Share'):
            self.panel.edits_document()
        receipt = self.panel.write_copy_to(self.root/'copy.zip')
        back = rr.load_save(self.root/'copy.zip')
        self.assertTrue(receipt['signed'])
        self.assertEqual(back.to_body(), composed)
        self.assertEqual(back.reserve_owner, {('primary', 0): 0})
        self.assertEqual(back.players[0].record.get('agility'), 88)
        self.assertEqual(back.players[0].first, 'Free')

    def test_capacity_buttons_refusal_keeps_selection_and_history(self):
        doc = document(league_save(65))
        for index in range(12): doc.demote_active(0, index)
        live = self.load(doc.to_body())
        self.group('reserve')
        self.assertFalse(self.panel.promote_button.isEnabled())
        player = self.panel.selected_player()
        state, history = live.to_body(), self.panel.undo_stack.depth
        self.assertFalse(self.panel.reserve_selected(True))
        self.assertEqual(live.to_body(), state)
        self.assertEqual(self.panel.undo_stack.depth, history)
        self.assertIs(self.panel.selected_player(), player)
        self.group('team')
        self.assertFalse(self.panel.demote_button.isEnabled())

    def test_standalone_journal_replay_refuses_without_dropping_move(self):
        doc = self.load()
        standalone = FranchisePanel()
        try:
            standalone.load(doc.container, doc)
            self.assertTrue(standalone.push(FranchiseEdit('demote_active', 'Demote', {'team': 0, 'player': 0})))
            self.assertEqual(standalone.undo(), 'Demote')
            self.assertEqual(standalone.redo(), 'Demote')
            self.assertFalse(standalone.push(FranchiseEdit('demote_active', 'Duplicate', {'team': 0, 'player': 0})))
            self.assertTrue(standalone.sync_from_roster())
            before = standalone.save.to_bytes()
            doc.swap(doc.players[0], doc.players[3])
            self.assertFalse(standalone.sync_from_roster())
            self.assertEqual(standalone.edit_labels(), ['Demote'])
            self.assertEqual(standalone.save.to_bytes(), before)
            with self.assertRaises(fs.FranchiseSaveError): standalone.write_copy_to(self.root/'bad.zip')
            self.assertFalse((self.root/'bad.zip').exists())
        finally:
            standalone.deleteLater()


if __name__ == '__main__':
    unittest.main()
