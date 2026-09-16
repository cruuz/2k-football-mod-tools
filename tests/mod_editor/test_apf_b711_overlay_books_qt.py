"""Readable Field lists and formation fine-tuning through the shipped workflow."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['MOD_STUDIO_NO_UPDATE_CHECK'] = '1'
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.gui import ApfStudioMainWindow
from mod_editor.apf_studio.models import APF_CATEGORY_ORDER, ApfCategory
from mod_editor.apf_studio.project import WorkspaceStateStore
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture
from tools.apf_ui_snapshots import pump


class FieldLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_rows_scroll_and_grow_in_real_shell_at_both_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facade = ApfStudioFacade(cache_root=root/'cache')
            window = ApfStudioMainWindow(facade, workspace_store=WorkspaceStateStore(root/'state'),
                                         offer_recovery=False)
            try:
                window.navigation.setCurrentRow(APF_CATEGORY_ORDER.index(ApfCategory.FIELD_ART))
                page = window._pages[ApfCategory.FIELD_ART]
                panel = page.field_opacity
                heights = []
                for width, height in ((1280, 720), (1920, 1080)):
                    with self.subTest(size=(width, height)):
                        page.workspace_tabs.setCurrentWidget(panel)
                        window.resize(width, height); window.show(); pump(self.app, window)
                        self.assertEqual((window.width(), window.height()), (width, height))
                        viewport = panel.material_scroll.viewport()
                        self.assertGreaterEqual(viewport.height(), 150)
                        heights.append(viewport.height())
                        previous_bottom = -1
                        for name, (checkbox, value) in panel.controls.items():
                            self.assertGreaterEqual(checkbox.height(), checkbox.fontMetrics().height())
                            self.assertGreaterEqual(value.height(), value.fontMetrics().height() + 4)
                            self.assertGreater(checkbox.y(), previous_bottom, name)
                            previous_bottom = checkbox.geometry().bottom()
                            self.assertIn('%', value.text())
                            self.assertGreater(value.width(), value.fontMetrics().horizontalAdvance('100.00%') + 20)
                        last = list(panel.controls.values())[-1][1]
                        panel.material_scroll.ensureWidgetVisible(last)
                        self.app.processEvents()
                        self.assertTrue(viewport.rect().contains(last.mapTo(viewport, last.rect().center())))
                        self.assertEqual(panel.material_scroll.horizontalScrollBar().maximum(), 0)
                        self.assertTrue(window.rect().contains(panel.stage_button.mapTo(window, QPoint(0, 0))))
                        # Sibling ownership list retains usable rows at the same sizes.
                        page.workspace_tabs.setCurrentIndex(page.workspace_tabs.indexOf(page.group_table.parentWidget()))
                        page.group_table.setRowCount(12)
                        pump(self.app, window)
                        self.assertGreaterEqual(page.group_table.viewport().height(), 100)
                        self.assertGreaterEqual(page.group_table.rowHeight(0), 30)
                        page.group_table.scrollToBottom()
                        page.workspace_tabs.setCurrentWidget(page.browser)
                        pump(self.app, window)
                        self.assertGreaterEqual(page.browser.table.viewport().height(), 100)
                        from types import SimpleNamespace
                        with patch.object(page.editor, 'focus_target', return_value=True):
                            self.assertTrue(page.focus_workspace_route(SimpleNamespace(key=(6, 0)), None))
                        self.assertIs(page.workspace_tabs.currentWidget(), page.field_scroll)
                        self.assertFalse(facade.source_ready)
                self.assertGreater(heights[1], heights[0] + 200)
                books = window._pages[ApfCategory.PLAYBOOKS]
                books.playbook_playcall.manualBookAllocationRequested.emit()
                self.assertIs(books.workspace_tabs.currentWidget(), books.book_identity)
                self.assertTrue(books.book_identity.manual_allocation.isChecked())
                self.assertTrue(books.book_identity.content.isVisibleTo(books.book_identity))
            finally:
                window._allow_close = True; window.close(); self.app.processEvents()
                facade.close()


class FineTuneQtTests(FacadeFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.panel = ApfPlayCallingEditor(self.facade, lambda label, work, done, blocking: done(work(lambda *_: None)))
        self.addCleanup(self.panel.close)
        self.panel.modifiedChanged.connect(self.panel.set_context)

    def test_situation_controls_preview_confirm_and_undo(self):
        p = self.panel
        self.assertTrue(p.situation_group.isAncestorOf(p.ratings_button))
        p.situation_picker.setCurrentIndex(8)
        p.candidate_table.selectRow(1)
        formation = p.formation_picker.currentData()
        self.assertEqual(formation, 63)
        for slider, value in zip(p.ratings, [1, 2, 7]): slider.setValue(value)
        before = self.facade.playcalling_snapshot()
        p.rating_preview_button.click()
        self.assertGreater(p.rating_preview_table.rowCount(), 0, p.notice.text())
        self.assertFalse(p.rating_preview_table.isHidden())
        self.assertEqual(self.facade.playcalling_snapshot(), before)
        self.assertFalse(self.facade.session.can_undo)
        engine = self.facade._playcalling
        with patch.object(engine, 'review', wraps=engine.review) as review:
            p.ratings_button.click()
        self.assertEqual(review.call_count, 1)
        request = engine.events(self.facade.session)[-1]['request']
        self.assertEqual(request, dict(kind='ratings', book='O-ManBlock', formation=63, ratings=[1, 2, 7]))
        self.assertTrue(p.ratings_button.isEnabled())
        self.assertTrue(p.rating_preview_table.isHidden())
        p.undo_button.click()
        self.assertFalse(self.facade.session.modifications)
        p.formation_picker.setCurrentIndex(0)
        self.assertEqual(p.candidate_table.currentRow(), 0)

    def test_bulk_keeps_book_formation_and_ratings_and_checks_once(self):
        p = self.panel; p.queue_edits.setChecked(True)
        p.ratings[0].setValue(7); p.ratings_button.click()
        p.donor_picker.setCurrentText('USER-o')
        p.candidate_table.selectRow(1)
        p.ratings[2].setValue(6); p.ratings_button.click()
        captured = list(p._pending)
        self.assertEqual([r['book'] for r in captured], ['O-ManBlock', 'USER-o'])
        self.assertEqual([r['formation'] for r in captured], [62, 63])
        p.rating_preview_button.click()
        self.assertIn('Includes 2 pending edits', p.rating_preview_note.text())
        self.assertFalse(self.facade.session.modifications)
        engine = self.facade._playcalling
        with patch.object(engine, 'review', wraps=engine.review) as review:
            p.confirm_button.click()
        self.assertEqual(review.call_count, 2)
        self.assertFalse(p._pending, p.notice.text())
        self.assertEqual([e['request'] for e in engine.events(self.facade.session)], captured)
        self.assertEqual(len(self.facade.session._undo), 1)
        project = self.facade.session.save_project(self.root/'weights.apf2k8mod')
        self.facade.undo(); self.facade.session.load_project(project)
        self.assertEqual([e['request'] for e in engine.events(self.facade.session)], captured)

    def test_failed_checks_keep_weight_edit_pending(self):
        p = self.panel; p.queue_edits.setChecked(True)
        p.remove_button.click(); p.ratings[0].setValue(7); p.ratings_button.click()
        p.confirm_button.click()
        self.assertEqual(len(p._pending), 2)
        self.assertFalse(self.facade.session.modifications)
        self.assertIn('Fix:', p.pending_table.item(1, 2).text())

    def test_all_teams_button_keeps_24_assignments_for_each_side(self):
        p = self.panel
        for side in (0, 1):
            p.side_picker.setCurrentIndex(side)
            p.own_all_button.click()
            event = self.facade._playcalling.events(self.facade.session)[-1]
            self.assertEqual(len(event['request']['assignments']), 24)
        self.assertIn('48 independent books', p.capacity_note.text())
        self.assertIn('36 offensive', p.capacity_note.text())

    def test_manual_allocation_handoff_does_not_stage_or_change_source(self):
        calls = []
        self.panel.manualBookAllocationRequested.connect(lambda: calls.append(True))
        self.panel.manual_books_button.click()
        self.assertEqual(calls, [True])
        self.assertFalse(self.facade.session.modifications)


if __name__ == '__main__': unittest.main()
