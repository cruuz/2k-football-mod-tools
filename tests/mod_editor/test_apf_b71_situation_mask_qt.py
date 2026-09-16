"""Offscreen UI transactions; model arithmetic is covered by native tests."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PyQt5.QtWidgets import QApplication
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor

class MaskQtTests(FacadeFixture):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        super().setUp();self.exclusions=[]
        original=self.backend.model.predict_offense
        def predict(book,master,tendency,situation,*,seeds,exclusions=()):
            self.exclusions.append((situation.down,situation.distance_yards,tuple(exclusions)))
            return original(book,master,tendency,situation,seeds=seeds)
        self.backend.model.predict_offense=predict
        def run(label,operation,done,blocking):done(operation(lambda *_:None))
        self.panel=ApfPlayCallingEditor(self.facade,run);self.addCleanup(self.panel.close)

    def test_live_checkbox_preview_undo_and_requested_row_edit(self):
        panel=self.panel;live=panel.situation_masks
        self.assertEqual(live.bucket.count(),12)
        self.assertFalse(live.enabled.isChecked());self.assertFalse(self.facade.session.modifications)
        self.assertFalse(live.candidates.cellWidget(0,3).isEnabled())
        live.enabled.click();self.assertTrue(live.candidates.cellWidget(0,3).isEnabled())
        live.bucket.setCurrentIndex(8);live.candidates.cellWidget(0,3).click()
        self.assertIn((3,8,(62,)),self.exclusions)
        self.assertTrue(live.candidates.cellWidget(0,3).isChecked())
        live.bucket.setCurrentIndex(7);self.assertFalse(live.candidates.cellWidget(0,3).isChecked())
        self.assertIn('read-only',next(w.text() for w in live.findChildren(__import__('PyQt5.QtWidgets',fromlist=['QLabel']).QLabel) if 'read-only' in w.text()))
        live.preview.click();self.assertEqual(panel.custom['down'].value(),3);self.assertEqual(panel.custom['distance_yards'].value(),5)
        panel.undo_button.click();self.assertEqual(self.facade._playcalling.state(self.facade.session).situation_masks,{})
        live.stored_row.setValue(6);live.write_row.click()
        self.assertEqual(self.facade._playcalling.events(self.facade.session)[-1]['request']['kind'],'master_row')
        self.assertIn('FB fallback',live.roles.text())

    def test_named_books_keep_independent_masks_and_no_implicit_install(self):
        live=self.panel.situation_masks
        live.enabled.click();live.bucket.setCurrentIndex(8);live.candidates.cellWidget(0,3).click()
        self.panel.donor_picker.setCurrentText('USER-o')
        self.assertFalse(live.candidates.cellWidget(0,3).isChecked())
        self.assertFalse(self.facade.launcher.pass_fetch_status(kind='situations')['installed'])
        self.panel.donor_picker.setCurrentText('O-ManBlock')
        self.assertTrue(live.candidates.cellWidget(0,3).isChecked())

if __name__=='__main__':unittest.main()
