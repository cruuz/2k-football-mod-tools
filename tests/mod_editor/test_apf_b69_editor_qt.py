"""Offscreen scheme review/CSV and actual 5-2 name, using real core writers."""
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PyQt5.QtWidgets import QApplication
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor
from mod_editor.core import apf2k8_master_writer as master_writer
from mod_editor.core import apf2k8_splb_writer as splb
from tests.mod_editor import test_apf_b69_schemes as previous


class EditorTests(previous.SchemeSessionTests):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.backend.master=master_writer
        def run(label,operation,done,blocking):done(operation(lambda *_:None))
        self.panel=ApfPlayCallingEditor(self.facade,run)
        self.addCleanup(self.panel.close)

    def test_scheme_review_stage_export_undo_and_52_real_name(self):
        self.assertEqual(self.panel.scheme_picker.count(),8)
        self.panel.scheme_button.click()
        self.assertFalse(self.facade.session.modifications)
        self.assertGreater(self.panel.scheme_details.rowCount(),11)
        self.assertIn('Missing preferred personnel',self.panel.review_label.text())
        self.panel.confirm_button.click()
        self.assertTrue(self.facade.session.modifications)
        target=self.root/'calls.csv'
        with patch('mod_editor.apf_studio.playcalling_editor_qt.QFileDialog.getSaveFileName',return_value=(str(target),'CSV')):
            self.panel.scheme_export.click()
        self.assertIn(b'Air Coryell',target.read_bytes())
        with patch('mod_editor.apf_studio.playcalling_editor_qt.QFileDialog.getSaveFileName',return_value=(str(target),'CSV')), patch('mod_editor.apf_studio.launcher._atomic_bytes',side_effect=PermissionError('folder is read-only')):
            self.panel.scheme_export.click()
        self.assertIn('Choose a writable folder and export again',self.panel.notice.text())
        self.assertIn(b'Air Coryell',target.read_bytes())
        self.panel.undo_button.click()
        self.assertFalse(self.facade.session.modifications)
        self.panel.master_group.setChecked(True)
        self.panel.fix_52_button.click()
        self.assertEqual(self.facade.playcalling_context()['categories'][27].row,13)
        self.panel.side_picker.setCurrentIndex(1)
        self.assertFalse(self.panel.scheme_group.isEnabled())

    def test_never_call_restores_original_membership_and_undo(self):
        import struct
        book=bytearray(self.backend.initial.books['O-ManBlock'])
        book[0x120:0x1D0]=book[0x70:0x120]
        word=struct.unpack_from('>I',book,0x1C8)[0]
        struct.pack_into('>I',book,0x1C8,word|(1<<24))
        original=splb._compact_normalize(bytes(book))
        self.backend.initial.books['O-ManBlock']=original
        self.panel.refresh()
        self.panel.never_call.setChecked(True);self.panel.never_button.click();self.panel.confirm_button.click()
        self.assertTrue(self.panel.never_call.isChecked())
        state=self.facade.playcalling_context()['state']
        self.assertEqual(state.books['O-ManBlock'][0x11C:0x120],bytes(4))
        self.panel.never_call.setChecked(False);self.panel.never_button.click();self.panel.confirm_button.click()
        self.assertEqual(self.facade.playcalling_context()['state'].books['O-ManBlock'],original)
        self.panel.undo_button.click()
        self.assertTrue(self.panel.never_call.isChecked())


if __name__=='__main__':unittest.main(verbosity=2)
