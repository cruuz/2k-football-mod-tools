"""Standalone offscreen animation workspace tests; no display or game execution."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO),str(Path(__file__).resolve().parent)]
try:
    from PyQt5.QtCore import QEvent
    from PyQt5.QtWidgets import QApplication
    from mod_editor.gui.animations_panel_qt import AnimationsPanel,change_report
    HAVE_QT = True
except ImportError:
    HAVE_QT = False
from mod_editor.core import nfl2k5_animation as A
from animation_test_support import make_clip,simple_skeleton


@unittest.skipUnless(HAVE_QT,'PyQt5 is absent; offscreen widget tests require PyQt5')
class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = AnimationsPanel()

    def tearDown(self):
        self.panel.wait_idle()
        self.app.processEvents()
        self.panel.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete)
        self.app.processEvents()

    def settle(self):
        self.assertTrue(self.panel.wait_idle())
        self.app.processEvents()

    def test_gating_and_badge(self):
        self.assertIn('EXPERIMENTAL / UNWITNESSED',self.panel.badge.text())
        for button in (self.panel.export_button,self.panel.check_button,self.panel.import_button,self.panel.reload_button):
            self.assertFalse(button.isEnabled())
        self.panel.reload()
        self.assertIsNone(self.panel._source)

    def test_scrubber_paints_changed_skeleton_offscreen(self):
        self.panel.apply_clip(make_clip(family='referee'),simple_skeleton())
        self.panel.preview.resize(360,280)
        first = self.panel.preview.grab().toImage()
        first_segments = list(self.panel.preview.segments)
        self.panel.scrubber.setValue(2)
        self.app.processEvents()
        self.assertNotEqual(first_segments,self.panel.preview.segments)
        self.assertFalse(first.isNull())
        self.assertEqual(len(first_segments),24)
        self.assertIn('Frame 3 / 4',self.panel.frame_label.text())
        self.assertTrue(self.panel.export_button.isEnabled())
        self.assertFalse(self.panel.import_button.isEnabled())
        self.panel.plane_combo.setCurrentIndex(1)
        self.assertNotEqual(first,self.panel.preview.grab().toImage())

    def test_scopes_and_unknown_family_are_explicit(self):
        clip = make_clip()
        row = A.catalog_entry(clip)
        self.panel.apply_catalog(None,{'archive':[row],'embedded_xbe':[]})
        self.assertEqual(self.panel.clip_list.count(),1)
        self.panel.scope_combo.setCurrentIndex(1)
        self.assertEqual(self.panel.clip_list.count(),0)
        self.panel.apply_clip(clip)
        self.assertIn('unknown',self.panel.preview_note.text())
        self.assertIn('not body bones',self.panel.preview_note.text())
        self.assertEqual(len(self.panel.preview.segments),3)
        self.panel.keys_field.setText('dummy.json')
        self.assertTrue(self.panel.check_button.isEnabled())
        self.panel.apply_clip(make_clip(kind='MMCD'))
        self.assertFalse(self.panel.check_button.isEnabled())
        self.assertFalse(self.panel.import_button.isEnabled())
        self.assertEqual(self.panel.root_combo.count(),2)
        self.panel.root_combo.setCurrentIndex(1)
        self.assertEqual(len(self.panel.preview.segments),3)

    def test_export_then_change_preview_writes_no_game_data(self):
        clip = make_clip(family='referee')
        self.panel.apply_clip(clip,simple_skeleton())
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)/'export'
            self.panel.export_to(destination)
            self.settle()
            self.assertTrue((destination/'animation.native.json').is_file())
            self.panel.keys_field.setText(str(destination/'animation.keys.json'))
            self.panel.check_changes()
            self.settle()
            self.assertIn('0 changed keys',self.panel.details.toPlainText())
            self.assertIn('Nothing was written',self.panel.details.toPlainText())
            self.assertFalse(self.panel.import_button.isEnabled())

    def test_failed_check_does_not_arm_import(self):
        self.panel.apply_clip(make_clip())
        self.panel.keys_field.setText('absent-animation-keys.json')
        self.panel.check_changes()
        self.settle()
        self.assertIn('FileNotFoundError',self.panel.status_label.text())
        self.assertFalse(self.panel.import_button.isEnabled())

    def test_source_change_discards_pending_result_and_clears_selection(self):
        self.panel._run(lambda:make_clip(),lambda clip:self.panel.apply_clip(clip))
        self.panel.set_source_paths(Path('new-disc/0'),Path('new-index.json'))
        self.settle()
        self.assertIsNone(self.panel._clip)
        self.assertFalse(self.panel.export_button.isEnabled())
        self.assertFalse(self.panel.import_button.isEnabled())

    def test_deletion_drops_queued_worker_delivery(self):
        # The worker result may queue before deletion; neither path may touch dead Qt objects.
        other = AnimationsPanel()
        delivered = []
        other._run(lambda:42,lambda result:delivered.append(result))
        self.assertTrue(other.wait_idle())
        other.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(delivered,[])


if __name__ == '__main__':
    unittest.main()
