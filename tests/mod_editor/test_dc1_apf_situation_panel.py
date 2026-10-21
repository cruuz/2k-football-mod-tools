"""APF 2K8 Situations panel: sortable formation list and no hitch per edit (Urianus, 10/9 to 10/11).

"Sorting doesn't work for the Situations Patch formation list" and "there is now a short
delay/hitch whenever adjusting weights or multipliers". The table had no sorting at all, and
with a situation patch installed every staged edit re-parsed the 324 KB patch twice (about
0.25 s) just to compare it with the installed file.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio import situation_masks  # noqa: E402
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor  # noqa: E402
from mod_editor.core import apf2k8_playcall_model as model  # noqa: E402
from mod_editor.core import apf2k8_situation_mask as native  # noqa: E402
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture  # noqa: E402
from tests.mod_editor import test_apf_b72_personnel_rows as model_fixture  # noqa: E402


class PanelFixture(FacadeFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        data = model_fixture.ModelFixtureTests()
        data.setUp()
        self.backend.initial.books['O-ManBlock'] = data.book
        self.backend.initial.master = data.master
        self.backend.initial.inventory['formations'] = [
            {'index': 0, 'name': 'Test Queens'}, {'index': 1, 'name': 'Test Spread'}]
        self.backend.model = model

        def run(label, operation, done, blocking):
            done(operation(lambda *_: None))
        self.panel = ApfPlayCallingEditor(self.facade, run)
        self.addCleanup(self.panel.close)
        self.live = self.panel.situation_masks

    def names(self):
        table = self.live.candidates
        return [table.item(r, 0).text() for r in range(table.rowCount())]

    def click_header(self, column):
        self.live.candidates.horizontalHeader().sectionClicked.emit(column)


class SortingTests(PanelFixture):
    def setUp(self):
        super().setUp()
        # many formations with unsorted names; no refresh is triggered, so the list stays
        self.live.context['formations'] = [
            {'id': i, 'name': name} for i, name in enumerate(
                ['Form 10', 'Form 2', 'Ace', 'form 1', 'Zebra', 'Form 20', 'Bunch'])]
        self.live.render()

    def test_unsorted_order_is_the_books_order(self):
        self.assertEqual(self.names(), ['Form 10', 'Form 2', 'Ace', 'form 1', 'Zebra', 'Form 20', 'Bunch'])

    def test_name_column_sorts_naturally_and_reverses_on_second_click(self):
        self.click_header(0)
        self.assertEqual(self.names(), ['Ace', 'Bunch', 'form 1', 'Form 2', 'Form 10', 'Form 20', 'Zebra'])
        self.click_header(0)
        self.assertEqual(self.names(), ['Zebra', 'Form 20', 'Form 10', 'Form 2', 'form 1', 'Bunch', 'Ace'])
        header = self.live.candidates.horizontalHeader()
        self.assertEqual(header.sortIndicatorSection(), 0)
        self.assertEqual(header.sortIndicatorOrder(), Qt.DescendingOrder)

    def test_row_widgets_stay_with_their_formation_after_sorting(self):
        self.click_header(0)
        table = self.live.candidates
        for row in range(table.rowCount()):
            name = table.item(row, 0).text()
            self.assertIn(name, table.cellWidget(row, 3).accessibleName())
            self.assertIn(name, table.cellWidget(row, 4).accessibleName())

    def test_changing_a_multiplier_in_a_sorted_list_stages_that_formation(self):
        self.click_header(0)
        table = self.live.candidates
        row = self.names().index('Zebra')
        sent = []
        self.live.owner.review_request = lambda request: sent.append(request)
        combo = table.cellWidget(row, 4)
        combo.setCurrentIndex(combo.findData(4.))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['kind'], 'situation_weight')
        self.assertEqual(sent[0]['formation'], 4)  # Zebra's id in the fixture list above
        self.assertEqual(sent[0]['value'], 4.)

    def test_multiplier_column_sorts_staged_weights_first_when_descending(self):
        self.live.owner.queue_edits.setChecked(True)
        table = self.live.candidates
        # stage through the real path, which refreshes the list from the book (two formations)
        self.live.context = self.panel._context
        self.panel.submit_requests([
            {'kind': 'situation_masks_enabled', 'enabled': True},
            {'kind': 'situation_weight', 'book': 'O-ManBlock', 'key': self.live.key(), 'formation': 1, 'value': 4.}])
        self.live.sort_column, self.live.sort_ascending = None, True
        self.click_header(4)   # ascending: 1x rows first
        first_asc = table.cellWidget(0, 4).currentData()
        self.click_header(4)   # descending: the 4x row first
        self.assertEqual(table.cellWidget(0, 4).currentData(), 4.)
        self.assertLessEqual(first_asc, 4.)

    def test_weight_column_puts_rows_without_a_candidate_last_both_ways(self):
        for _ in range(2):
            self.click_header(5)
            self.assertTrue(self.live.candidates.item(self.live.candidates.rowCount() - 1, 5).text()
                            .startswith('No candidate'))

    def test_render_leaves_the_table_repainting_after_an_error(self):
        self.live.sort_column = 3
        with mock.patch.object(self.live.candidates, 'resizeColumnsToContents', side_effect=RuntimeError('x')):
            with self.assertRaises(RuntimeError):
                self.live.render()
        self.assertTrue(self.live.candidates.updatesEnabled())


class PatchComparisonTests(PanelFixture):
    def state(self, enabled=True):
        state = self.panel._context['state']
        return state

    def test_expected_payload_equals_the_exported_payload(self):
        state = self.panel._context['state']
        for profile in ('base', 'tu_1_1'):
            for enabled in (False, True):
                state = state.__class__(**{**state.__dict__, 'situation_masks_enabled': enabled}) \
                    if hasattr(state, '__dict__') else state
                self.assertEqual(situation_masks.expected_payload(state, profile),
                                 situation_masks.prepare(state, profile)['payload'])
        with self.assertRaises(Exception):
            situation_masks.expected_payload(state, 'nonsense')

    def test_dependency_check_does_not_reparse_the_patch_after_every_edit(self):
        state = self.panel._context['state']
        profile = self.live.profile.currentData()
        payload = situation_masks.expected_payload(state, profile)
        with tempfile.TemporaryDirectory() as tmp:
            installed = Path(tmp) / 'patch.toml'
            installed.write_bytes(payload)
            result = {'installed': True, 'enabled': True, 'patch_path': str(installed), 'message': 'ok'}
            with mock.patch.object(native, 'canonical_payload', side_effect=AssertionError('slow read-back')):
                self.live.patch_dependency(result)
            self.assertIn('Matching situation patch installed and enabled', self.live.dependency.text())
            installed.write_bytes(payload + b'#')
            self.live.patch_dependency(result)
            self.assertIn('Installed patch differs', self.live.dependency.text())


if __name__ == '__main__':
    unittest.main()
