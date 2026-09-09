"""Standalone offscreen Abilities page, transactions and Build option signals."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from mod_editor.core import nfl2k5_roster_records as rr
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body, league_body
try:
    from PyQt5.QtWidgets import QApplication
    from mod_editor.gui.abilities_panel_qt import AbilitiesPanel
except ImportError:
    AbilitiesPanel = None


@unittest.skipUnless(AbilitiesPanel is not None, 'PyQt5 required for offscreen Abilities page')
class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = AbilitiesPanel()
        self.document = rr.load_body(synthetic_body())
        self.panel.set_document(self.document)
        self.panel.set_player(self.document.players[0])
        self.edits = []
        self.panel.edit_committed.connect(self.edits.append)

    def tearDown(self):
        self.panel.deleteLater()
        self.app.processEvents()

    def test_select_load_is_read_only_and_manual_changes_join_shared_undo(self):
        before = self.document.to_body()
        self.panel.set_player(self.document.players[1])
        self.panel.set_player(self.document.players[0])
        self.assertEqual(self.document.to_body(),before)
        self.assertEqual(self.edits,[])
        self.panel.tier_combo.setCurrentIndex(1)
        self.panel.ability_checks['juke'].click()
        self.panel.ability_checks['right_stick_moves'].click()
        self.assertEqual(len(self.edits),3)
        p = self.document.players[0]
        p.record.guardian_cap = True
        self.edits[-1].undo()
        self.assertFalse(p.record.abilities['right_stick_moves'])
        self.assertTrue(p.record.abilities['juke'])
        self.assertTrue(p.record.guardian_cap)
        self.edits[-1].redo()
        self.assertTrue(p.record.abilities['right_stick_moves'])

    def test_capacity_refusal_and_tier_reduction_are_atomic_and_undoable(self):
        self.panel.tier_combo.setCurrentIndex(1)
        self.panel.ability_checks['juke'].click()
        self.panel.ability_checks['spin'].click()
        before, depth = self.document.to_body(),len(self.edits)
        self.panel.ability_checks['truck'].click()
        self.assertEqual(self.document.to_body(),before)
        self.assertEqual(len(self.edits),depth)
        self.assertIn('permits 2',self.panel.status_label.text())
        self.assertFalse(self.panel.ability_checks['truck'].isChecked())
        self.panel.tier_combo.setCurrentIndex(0)
        self.assertEqual(sum(self.document.players[0].record.abilities.values()),0)
        self.edits[-1].undo()
        self.assertEqual(self.document.to_body(),before)

    def test_assignment_preview_apply_export_one_undo_and_redo(self):
        doc = rr.load_body(league_body(53))
        self.panel.set_document(doc)
        self.panel.set_player(doc.players[0])
        before = doc.to_body()
        self.panel.preview_button.click()
        self.assertGreater(self.panel.preview_table.rowCount(),0)
        self.assertEqual(doc.to_body(),before)
        self.panel.apply_button.click()
        after = doc.to_body()
        self.assertNotEqual(after,before)
        self.assertEqual(len(self.edits),1)
        self.assertFalse(self.panel.apply_button.isEnabled())
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp).resolve()/'receipt.json'
            self.panel.save_receipt(target)
            receipt = json.loads(target.read_text())
            self.assertEqual(receipt['result_sha256'],self.edits[0].receipt['result_sha256'])
            with self.assertRaises(FileExistsError): self.panel.save_receipt(target)
        self.edits[0].undo()
        self.assertEqual(doc.to_body(),before)
        self.edits[0].redo()
        self.assertEqual(doc.to_body(),after)

    def test_stale_preview_refuses_after_rating_edit_and_new_document_invalidates_undo(self):
        doc = rr.load_body(league_body(53))
        self.panel.set_document(doc)
        self.panel.preview_assignment()
        doc.players[0].record.set('speed',20)
        before = doc.to_body()
        self.panel.apply_assignment()
        self.assertEqual(doc.to_body(),before)
        self.assertEqual(self.edits,[])
        self.assertIn('preview',self.panel.status_label.text())
        self.panel.preview_assignment()
        self.panel.apply_assignment()
        self.panel.set_document(self.document)
        with self.assertRaisesRegex(ValueError,'different roster'): self.edits[0].undo()

    def test_lock_signals_round_trip_without_changing_roster_or_granting_flags(self):
        before = self.document.to_body()
        emitted = []
        self.panel.lock_settings_changed.connect(emitted.append)
        values = dict(lock_right_stick=False,lock_special_moves=True,lock_speedster=False)
        self.panel.set_lock_settings(values)
        self.assertEqual(self.panel.lock_settings(),values)
        self.assertEqual(emitted,[])
        self.panel.lock_checks['lock_special_moves'].click()
        self.assertEqual(emitted,[dict(values,lock_special_moves=False)])
        self.assertEqual(self.document.to_body(),before)
        self.assertEqual(self.edits,[])


if __name__ == '__main__': unittest.main()
