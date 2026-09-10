"""Reproduce the 63.1 page boundaries; the beta-64 action is documented in WIRING."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
from mod_editor.core import nfl2k5_roster_records as rr, nfl2k5_save_rost as codec
from mod_editor.core import nfl2k5_college_check as check
from tests.mod_editor.test_nfl2k5_college_check import corrupt, rel
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body, synthetic_save_v0
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise
from tests.mod_editor.test_roster_editor_panel_franchise import write_container


class PageBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = RosterEditorPanel()

    def tearDown(self):
        self.panel.deleteLater()
        self.app.processEvents()

    def test_roster_save_write_refuses_outside_then_core_repair_unlocks_copy(self):
        for kind in ('null', 'past_table', 'outside'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                bad, field = corrupt(synthetic_save_v0(synthetic_body()), kind)
                source = write_container(Path(td) / 'source', bad)
                self.assertTrue(self.panel.load_save(source))
                self.assertEqual(self.panel.document.players[0].college, '')
                self.panel.document.players[0].record.set('speed', 77)
                if kind == 'outside':
                    with self.assertRaisesRegex(codec.SaveRostError, 'college pointer'):
                        self.panel.write_copy_to(Path(td) / 'blocked')
                else:
                    self.assertTrue(self.panel.write_copy_to(Path(td) / 'allowed')['signed'])
                fixed, receipt = check.repair(self.panel.document.to_body())
                self.panel.document.adopt_body(fixed)
                self.assertTrue(self.panel.write_copy_to(Path(td) / 'fixed')['signed'])
                self.assertEqual(rr.SaveContainer.load(source).savegame, bad)

    def test_franchise_schedule_copy_allowed_but_roster_edit_requires_repair(self):
        with tempfile.TemporaryDirectory() as td:
            bad, field = corrupt(synthetic_franchise(), 'outside')
            self.assertTrue(self.panel.load_save(write_container(Path(td) / 'source', bad)))
            page = self.panel.franchise_panel
            self.assertTrue(page.edit_game(0, 1, hour=8, minute=30))
            self.assertTrue(self.panel.write_copy_to(Path(td) / 'schedule')['signed'])
            self.panel.document.players[0].record.set('speed', 77)
            with self.assertRaisesRegex(ValueError, 'college pointer'):
                self.panel.write_copy_to(Path(td) / 'blocked')
            fixed, receipt = check.repair(self.panel.document.to_body())
            self.panel.document.adopt_body(fixed)
            self.assertTrue(self.panel.write_copy_to(Path(td) / 'fixed')['signed'])
            doc = rr.SaveContainer.load(Path(td) / 'fixed').document()
            self.assertEqual(doc.players[0].record.values['speed'], 77)

    def test_bad_table_name_can_block_load_but_scanner_still_names_affected_players(self):
        data = bytearray(synthetic_franchise())
        doc = codec.decode(data)
        rel(data, doc.tables['colleges'].offset, len(data) + 100)
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / 'source', bytes(data))
            self.assertFalse(self.panel.load_save(source))
            self.assertIn('string offset', self.panel.status_label.text())
        self.assertEqual(len(check.scan(data).findings), 3)
        with self.assertRaisesRegex(check.CollegeCheckError, 'college table'):
            check.repair(data)


if __name__ == '__main__':
    unittest.main()
