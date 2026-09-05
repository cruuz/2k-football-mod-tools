"""Screen-only wizard tests. Offscreen widgets, no display or facade cache writes."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
try:
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtCore import Qt
except ImportError:
    QApplication = None

from tests.mod_editor.test_nfl2k5_screen_timing import retail_books, spec_for
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_inspector as insp


class RecordingHost:
    def __init__(self, body):
        self.body = body
        self.authored = []

    def playbook_raw_body(self, _asset): return self.body
    def staged_replace_targets(self, _asset): return (), ()
    def create_formation(self, *args, **kwargs): pass
    def stage_formation_selector(self, *args): return 'formation:screen-test'
    def create_authored_play(self, *args, **kwargs): self.authored.append((args, kwargs))


@unittest.skipIf(QApplication is None, 'PyQt5 is absent; screen widget tests require Qt offscreen')
class ScreenPresetWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from mod_editor.gui.create_play_wizard_qt import CreatePlayWizard, DesignedFormation
        self.host = RecordingHost(b'')
        self.wiz = CreatePlayWizard(self.host)
        spec = spec_for()
        self.wiz.current = DesignedFormation('Test formation', 1, 0, spec.positions, spec.kinds,
                                            [str(s) for s in range(11)], list(spec.kinds))
        self.wiz.designed = [self.wiz.current]
        self.page = self.wiz.page_type
        self.page.initializePage()
        self.addCleanup(self.wiz.close)

    def concept(self, name):
        row = next(i for i in range(self.page.concepts.count())
                   if self.page.concepts.item(i).data(Qt.UserRole) == name)
        self.page.concepts.setCurrentRow(row)

    def test_variants_expose_actual_slots_and_default_d(self):
        for variant, slots in [('HB', [10]), ('WR', [7, 8]), ('TE', [6])]:
            self.concept(variant + ' Screen')
            self.assertFalse(self.page.screen_box.isHidden())
            self.assertEqual([self.page.screen_receiver.itemData(i) for i in range(self.page.screen_receiver.count())], slots)
            self.assertEqual(self.page.screen_level.currentData(), 'D')
            self.assertTrue(self.page.isComplete())
            self.page.screen_receiver.setCurrentIndex(len(slots) - 1)
            spec, label = self.page.build_spec()
            self.assertEqual(spec.screen.receiver_slot, slots[-1])
            self.assertEqual((spec.screen.hold_seconds, spec.screen.drop_yards, spec.screen.pass_delay), (.8, 7, .6))
            self.assertIn('EXPERIMENTAL', self.page.concepts.currentItem().text())
            self.assertNotIn('—', self.page.concepts.currentItem().text())
        self.concept('Mesh')
        self.assertTrue(self.page.screen_box.isHidden())
        self.assertIsNone(self.page.build_spec()[0].screen)

    def test_retail_controls_missing_receiver_and_pa(self):
        self.concept('HB Screen')
        self.page.screen_level.setCurrentIndex(0)
        spec, _ = self.page.build_spec()
        self.assertEqual((spec.screen.hold_seconds, spec.screen.drop_yards, spec.screen.pass_delay), (.5, 10, 0))
        self.assertGreaterEqual(self.page.screen_hold.minimum(), .1)
        self.page.radios['pa_pass'].setChecked(True)
        self.assertFalse(self.page.isComplete())
        self.page.radios['pass'].setChecked(True)
        self.wiz.current.kinds[10] = lib.WR
        self.page._screen_options()
        self.assertFalse(self.page.isComplete())

    def test_screen_read_order_preserves_default_and_skip_zeros(self):
        from mod_editor.gui.create_play_wizard_qt import with_read_order, read_order_of, DesignedPlay
        spec = spec_for(); lib.default_assignments(spec, 'HB Screen')
        chain = lib.build_chains(spec)[0]
        self.assertEqual(read_order_of(with_read_order(chain, (0, 5, 0, 0), allow_zero=True)), (0, 5, 0, 0))
        self.assertEqual(read_order_of(chain), (5, 0, 0, 0))
        play = DesignedPlay('Screen', 'pass', 'HB Screen', lib.build_chains(spec), 178)
        final = self.wiz.page_finalize
        final.table.setRowCount(1)
        final._add_read_order(0, play, self.wiz.current)
        spins = final._read_orders[0][1]
        self.assertEqual([s.value() for s in spins], [5, 0, 0, 0])
        self.assertTrue(all(s.minimum() == 0 for s in spins))

    def test_preview_cost_capacity_restore_and_finalize_staging(self):
        books = retail_books()
        raw = books[308]
        self.host.body = raw[32:]
        self.wiz.load_book(insp.parse_playbook_resource(raw, asset_id='private.PLAY'))
        self.wiz.current.donor_formation_index = 13
        self.wiz.current.category_index = lib.formation_category(raw[32:], 13)
        self.concept('WR Screen')
        self.page.screen_receiver.setCurrentIndex(1)
        self.page.screen_side.setCurrentIndex(1)
        self.wiz.page_assign.initializePage()
        assign = self.wiz.page_assign
        self.assertIsNone(assign._error)
        self.assertIn('31 nodes (248 bytes)', assign.status.text())
        self.assertIn('UNWITNESSED', assign.status.text())
        self.assertEqual(assign._default_for(8).kind, 'screen_receiver')
        normal = self.wiz.book
        self.wiz.book = replace(normal, node_count=3499)
        assign._refresh()
        self.assertFalse(assign.isComplete())
        self.assertIn('31 nodes', assign._error)
        self.wiz.book = normal
        assign._refresh()
        self.assertTrue(assign.validatePage())
        final = self.wiz.page_finalize
        final.initializePage()
        self.assertEqual([s.value() for s in final._read_orders[1][1]], [3, 0, 0, 0])
        with patch.object(QMessageBox, 'warning') as warning:
            final._apply()
        warning.assert_not_called()
        self.assertEqual(len(self.host.authored), 1)
        args, kwargs = self.host.authored[0]
        pass_values = next(vals for op, vals in args[3][0] if op == 6)
        self.assertEqual(pass_values[1:5], [3, 0, 0, 0])


if __name__ == '__main__':
    unittest.main()
