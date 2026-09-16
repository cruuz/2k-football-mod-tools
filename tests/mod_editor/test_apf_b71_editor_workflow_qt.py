"""Direct confirmation and a mixed Pending edits queue in the real Qt page."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt5.QtWidgets import QApplication
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture


class QueueQtTests(FacadeFixture):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.tasks = []
        def run(label, work, done, blocking):
            self.tasks.append(label)
            done(work(lambda *_: None))
        self.panel = ApfPlayCallingEditor(self.facade, run)
        self.addCleanup(self.panel.close)

    def test_confirm_personnel_runs_review_without_an_extra_click_or_details(self):
        panel = self.panel
        engine = self.facade._playcalling
        self.assertFalse(panel.details_toggle.isChecked())
        self.assertTrue(panel.review_details.isHidden())
        self.assertIn('Confirm personnel', panel.categories_button.text())
        with patch.object(engine, 'review', wraps=engine.review) as review:
            panel.categories_button.click()
        self.assertEqual(review.call_count, 1)
        event = engine.events(self.facade.session)[0]
        self.assertEqual(event['request'], review.call_args.args[1])
        self.assertEqual(event['request']['kind'], 'categories')
        self.assertEqual(panel.coverage_table.rowCount(), 11)
        panel.details_toggle.click()
        self.assertFalse(panel.review_details.isHidden())
        self.assertIn('EXPERIMENTAL', panel.master_group.title())
        self.assertIn('every book', panel.master_group.title())

    def test_mixed_queue_masks_rows_audibles_and_retirement_one_confirm_one_undo(self):
        p = self.panel; p.queue_edits.click()
        self.assertIn('Add personnel', p.categories_button.text())
        p.categories_button.click()
        p.never_call.setChecked(True); p.never_button.click()
        p.retire_button.click()  # Includes its captured run share.
        p.tendency.setValue(61); p.tendency_button.click()
        p.audibles_button.click()
        p.situation_masks.enabled.click()
        p.situation_masks.bucket.setCurrentIndex(8)
        p.situation_masks.candidates.cellWidget(0, 3).click()
        p.situation_masks.stored_row.setValue(6); p.situation_masks.write_row.click()
        self.assertFalse(self.facade.session.modifications)
        self.assertEqual(len(p._pending), 9)
        self.assertEqual(p.pending_table.rowCount(), 9)
        self.assertTrue(p.confirm_button.isEnabled())
        self.assertTrue(p.situation_masks.candidates.cellWidget(0, 3).isChecked())
        self.assertEqual({r['kind'] for r in p._pending}, {'categories', 'never_call', 'retire', 'tendency', 'audibles', 'situation_masks_enabled', 'situation_mask', 'master_row'})
        # Retiring the selected personnel after Never call is not necessarily
        # compatible; remove those independent draft rows before committing.
        p.pending_table.cellWidget(2, 3).click()
        p.pending_table.cellWidget(1, 3).click()
        captured = list(p._pending)
        p.confirm_button.click()
        self.assertEqual(p._pending, [], p.notice.text())
        self.assertEqual([e['request'] for e in self.facade._playcalling.events(self.facade.session)], captured)
        self.assertEqual(len(self.facade.session._undo), 1)
        p.undo_button.click()
        self.assertFalse(self.facade.session.modifications)

    def test_all_blockers_inline_clean_rows_stage_and_pending_survives_book_refresh(self):
        p = self.panel; p.queue_edits.click()
        p.remove_button.click(); p.ratings_button.click()
        p.tendency.setValue(61); p.tendency_button.click()
        p.confirm_button.click()
        self.assertEqual(len(p._pending), 2)
        self.assertEqual(len(self.facade._playcalling.events(self.facade.session)), 1)
        for row in range(2):
            text = p.pending_table.item(row, 2).text()
            self.assertIn('O-ManBlock', text); self.assertIn('formation 62', text)
            self.assertIn('removes', text); self.assertIn('Fix:', text)
        p.donor_picker.setCurrentText('USER-o')
        self.assertEqual(len(p._pending), 2)
        p.pending_table.cellWidget(1, 3).click()
        self.assertEqual(len(p._pending), 1)
        p.confirm_button.click()
        self.assertEqual(p._pending, [])
        self.assertEqual(self.facade._playcalling.events(self.facade.session)[-1]['request']['book'], 'O-ManBlock')

    def test_clear_is_draft_only_and_failed_write_keeps_pending(self):
        p = self.panel; p.queue_edits.click(); p.ratings_button.click()
        with patch.object(self.facade.session, '_store_payload', side_effect=OSError('disk full')):
            p.confirm_button.click()
        self.assertEqual(len(p._pending), 1)
        self.assertIn('disk full', p.notice.text())
        self.assertFalse(self.facade.session.modifications)
        p.clear_pending_button.click()
        self.assertEqual(p.pending_table.rowCount(), 0)
        self.assertFalse(p.confirm_button.isEnabled())
        self.assertFalse(self.facade.session.can_undo)

    def test_switch_project_clears_drafts_even_with_same_source(self):
        p = self.panel; p.queue_edits.click(); p.ratings_button.click()
        self.facade.session.session_id += '-new-session'
        p.set_context()
        self.assertEqual(p._pending, [])

    def test_owned_book_confirmation_does_not_nest_a_blocking_worker(self):
        active = []; rejected = []
        def run(label, work, done, blocking):
            if blocking and active:
                rejected.append(label); return False
            token = object(); active.append(token)
            try: done(work(lambda *_: None))
            finally: active.remove(token)
            return True
        self.panel.run_task = run
        self.panel.own_team_button.click()
        self.assertFalse(rejected)
        self.assertIn('Team 0 O', self.panel.book_label.text())


if __name__ == '__main__': unittest.main()
