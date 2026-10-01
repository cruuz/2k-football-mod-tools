"""Beta 76 release options: dependencies, source gates and saved choices, no disc build."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PyQt5.QtWidgets import QApplication
from mod_editor.core import mod_build
from mod_editor.gui.build_panel_qt import BuildPanel, ANNIVERSARY_DEPENDENCIES


class ReleaseControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = BuildPanel()
        self.keys = ('espn25_named_previews', 'historic_stock_books', 'espn25_era_rules')
        self.state = dict(path='source.iso', container='xiso',
                          **{k: 'retail' for k in self.panel._boxes()})
        self.panel.apply_state(self.state)
        self.panel.target_field.setText('output.iso')

    def tearDown(self):
        self.panel.deleteLater()
        self.app.processEvents()

    def test_release_options_default_off_with_help_and_roundtrip(self):
        for key in self.keys:
            with self.subTest(key=key):
                box = self.panel._boxes()[key]
                self.assertFalse(box.isChecked())
                self.assertTrue(box.isEnabled())
                self.assertTrue(box.accessibleDescription())
                box.setChecked(True)
                self.assertTrue(getattr(self.panel.plan(), key))
        settings = self.panel.project_build_settings()
        for key in self.keys:
            self.panel._boxes()[key].setChecked(False)
        self.panel.restore_project_build_settings(settings)
        for key in self.keys:
            self.assertTrue(getattr(self.panel.plan(), key))
        self.assertIn('named previews', ' '.join(self.panel.selected_labels()))

    def test_required_parents_turn_on_and_clear_their_child(self):
        for child, parents in ANNIVERSARY_DEPENDENCIES.items():
            for parent in parents:
                with self.subTest(child=child, parent=parent):
                    box = self.panel._boxes()[child]
                    box.setChecked(True)
                    self.assertTrue(all(self.panel._boxes()[p].isChecked() for p in parents))
                    self.panel._boxes()[parent].setChecked(False)
                    self.assertFalse(box.isChecked())

    def test_conflicting_book_options_choose_one(self):
        self.panel.playbook_pair_check.setChecked(True)
        self.panel.historic_stock_books_check.setChecked(True)
        self.assertFalse(self.panel.plan().playbook_pair)
        self.panel.playbook_pair_check.setChecked(True)
        self.assertFalse(self.panel.plan().historic_stock_books)

    def test_missing_parent_and_restored_conflict_block_build(self):
        self.panel.espn25_more_moments_check.setEnabled(False)
        self.panel.espn25_named_previews_check.setChecked(True)
        self.assertIn('requires', self.panel.blocker())
        self.panel.espn25_named_previews_check.setChecked(False)
        for key in ('playbook_pair', 'historic_stock_books'):
            box = self.panel._boxes()[key]
            box.blockSignals(True)
            box.setChecked(True)
            box.blockSignals(False)
        self.assertIn('Choose stock historic books', self.panel.blocker())

    def test_bare_executable_foreign_and_installed_source_gates(self):
        for status, container, enabled, checked in (
            ('retail', 'xbe', False, False), ('foreign', 'xiso', False, False),
            ('applied', 'xiso', False, True), ('retail', 'xiso', True, False),
        ):
            state = dict(self.state, container=container, **{k: status for k in self.keys})
            self.panel.apply_state(state)
            for key in self.keys:
                with self.subTest(status=status, container=container, key=key):
                    box = self.panel._boxes()[key]
                    self.assertEqual(box.isEnabled(), enabled)
                    self.assertEqual(box.isChecked(), checked)

    def test_local_marks_pack_field_rechecks_and_reaches_plan(self):
        with patch.object(mod_build, '_espn_marks_available', return_value=True) as marks, \
             patch.object(mod_build, '_espn_wipes_boards_available', return_value=True):
            self.panel.official_marks_pack_field.setText('/tmp/local-marks')
            marks.assert_called_with('/tmp/local-marks')
            self.assertTrue(self.panel.espn_marks_check.isEnabled())
            self.panel.espn_marks_check.setChecked(True)
            saved = self.panel.project_build_settings()
            self.assertEqual(self.panel.plan().official_marks_pack, '/tmp/local-marks')
            self.panel.official_marks_pack_field.clear()
            self.panel.restore_project_build_settings(saved)
            self.assertEqual(self.panel.official_marks_pack_field.text(), '/tmp/local-marks')
            self.assertTrue(self.panel.plan().espn_marks_2026)
        with patch.object(mod_build, '_espn_marks_available', return_value=False), \
             patch.object(mod_build, '_espn_wipes_boards_available', return_value=False):
            self.panel.official_marks_pack_field.setText('/tmp/missing-marks')
            self.assertFalse(self.panel.espn_marks_check.isEnabled())
            self.assertFalse(self.panel.plan().espn_marks_2026)
            self.assertIn('Official marks pack missing', self.panel._badges['espn_marks_2026'].text())

if __name__ == '__main__':
    unittest.main()
