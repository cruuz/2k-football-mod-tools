"""Offscreen A3 editing through the same project review/Undo path."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt5.QtWidgets import QApplication
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor


class WeightQtTests(FacadeFixture):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.backend.model.predict_offense = lambda *args, **kwargs: self.backend.offense(*args, seeds=kwargs['seeds'])
        def run(label, operation, done, blocking): done(operation(lambda *_: None))
        self.panel = ApfPlayCallingEditor(self.facade, run)
        self.addCleanup(self.panel.close)

    def test_alias_edit_targets_bucket_and_undo_preserves_global_ratings(self):
        live = self.panel.situation_masks
        self.assertEqual(live.bucket.count(), 36)
        before = self.facade._playcalling.state(self.facade.session)
        live.enabled.click()
        live.bucket.setCurrentIndex(8)
        control = live.candidates.cellWidget(0, 4)
        control.setCurrentIndex(control.findData(4.))
        state = self.facade._playcalling.state(self.facade.session)
        self.assertEqual(state.situation_formation_weights['O-ManBlock'][8], {'62': 4.})
        self.assertEqual(before.books, state.books)
        self.assertEqual(before.master, state.master)
        live.bucket.setCurrentIndex(2)
        self.assertEqual(live.candidates.cellWidget(0, 4).currentData(), 1.)
        # Red zone 25-21 is sample 12 after the thirteen independent keys.
        live.bucket.setCurrentIndex(13+12)
        self.assertEqual(live.key(), 2)
        self.assertIn('Studio sample label', live.request.text())
        live.candidates.cellWidget(0, 3).click()
        state = self.facade._playcalling.state(self.facade.session)
        self.assertEqual(state.situation_masks['O-ManBlock'][2], [62])
        self.assertEqual(state.situation_formation_weights['O-ManBlock'][8], {'62': 4.})
        self.panel.undo_button.click()
        self.assertEqual(self.facade._playcalling.state(self.facade.session).situation_masks, {})
        live.bucket.setCurrentIndex(12)
        live.candidates.cellWidget(0, 3).click()
        self.assertEqual(self.facade._playcalling.state(self.facade.session).situation_masks['O-ManBlock'][12], [62])
        self.assertIn('try phase 3', live.request.text())
        self.assertFalse(self.facade.launcher.pass_fetch_status(kind='situations')['installed'])
