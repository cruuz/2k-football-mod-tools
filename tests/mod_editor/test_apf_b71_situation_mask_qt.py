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

    def test_v2_local_row_preview_decomposition_dependency_and_reset(self):
        from unittest.mock import patch
        from mod_editor.apf_studio.situation_masks import prepare
        panel=self.panel;live=panel.situation_masks
        original=self.backend.offense
        seen=[]
        def predict(book,master,tendency,situation,*,seeds,exclusions=(),personnel_rows=None):
            seen.append((situation.down,situation.distance_yards,personnel_rows))
            return original(book,master,tendency,situation,seeds=seeds)
        self.backend.model.predict_offense=predict
        original_candidates=self.backend.model.situation_candidates
        def candidates(book,master,situation,**kwargs):
            result=original_candidates(book,master,situation)
            for c in result:
                c.update(curve_term=.5,ratings_term=.1,category_weight=.05,
                         rank=2,retail_weight=.005,stored_row=3,effective_row=9,active=True)
            return result
        self.backend.model.situation_candidates=candidates
        live.enabled.click();live.bucket.setCurrentIndex(8)
        live.personnel.setCurrentIndex(live.personnel.findData(3));live.local_row.setValue(9)
        live.write_local.click()
        state=self.facade._playcalling.state(self.facade.session)
        self.assertEqual(state.situation_personnel_rows['O-ManBlock'][8],{'3':9})
        self.assertIn((3,8,{'3':9}),seen)
        self.assertIn('Requires the matching v2',live.dependency.text())
        self.assertFalse(self.facade.launcher.pass_fetch_status(kind='situations')['installed'])
        live.check.click();self.assertIn('Requires the matching v2',live.dependency.text())
        self.assertEqual(panel.candidate_table.item(0,5).text(),'0.5')
        self.assertEqual(panel.candidate_table.item(0,6).text(),'0.1')
        self.assertEqual(panel.candidate_table.item(0,7).text(),'2')
        self.assertEqual(panel.candidate_table.item(0,8).text(),'0.005')
        self.assertEqual(panel.candidate_table.item(0,9).text(),'3 / 9')
        path=self.root/'installed.patch.toml';path.write_bytes(prepare(state,'base')['payload'])
        result={'installed':True,'enabled':True,'patch_path':str(path),'message':'Installed'}
        live.patch_result(result);self.assertIn('Matching v2 situation patch installed and enabled',live.dependency.text())
        live.bucket.setCurrentIndex(7);self.assertEqual(live.local_row.value(),-1)
        live.bucket.setCurrentIndex(8);self.assertEqual(live.local_row.value(),9)
        live.local_row.setValue(-1);live.write_local.click()
        self.assertEqual(self.facade._playcalling.state(self.facade.session).situation_personnel_rows,{})
        live.patch_result(result);self.assertIn('differs from these choices',live.dependency.text())
        panel.undo_button.click()
        self.assertEqual(self.facade._playcalling.state(self.facade.session).situation_personnel_rows['O-ManBlock'][8],{'3':9})

if __name__=='__main__':unittest.main()
