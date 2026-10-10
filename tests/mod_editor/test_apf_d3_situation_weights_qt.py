"""Draft previews and honest live-bucket aliases with the actual model."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import hashlib
import unittest
from PyQt5.QtWidgets import QApplication

from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core import apf2k8_situation_mask as mask
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture
from tests.mod_editor import test_apf_b72_personnel_rows as model_fixture


class SituationDraftPreviewTests(FacadeFixture):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        data = model_fixture.ModelFixtureTests(); data.setUp()
        self.backend.initial.books['O-ManBlock'] = data.book
        self.backend.initial.master = data.master
        self.backend.initial.inventory['formations'] = [{'index': 0, 'name': 'Test Queens'}, {'index': 1, 'name': 'Test Spread'}]
        self.backend.model = model
        def run(label, operation, done, blocking): done(operation(lambda *_: None))
        self.panel = ApfPlayCallingEditor(self.facade, run)
        self.addCleanup(self.panel.close)

    def test_pending_weights_change_actual_live_preview_without_staging(self):
        snapshot = self.facade.playcalling_snapshot()
        before = self.panel.grid.item(0, 2).text()
        self.panel.queue_edits.setChecked(True)
        self.panel.submit_requests([
            {'kind': 'situation_masks_enabled', 'enabled': True},
            {'kind': 'situation_weight', 'book': 'O-ManBlock', 'key': 2, 'formation': 0, 'value': 4.},
        ])
        self.assertEqual(self.facade.playcalling_snapshot(), snapshot)
        self.assertFalse(self.facade._playcalling.state(self.facade.session).situation_masks_enabled)
        self.assertEqual(self.panel._context['pending_count'], 2)
        self.assertTrue(self.panel._context['state'].situation_masks_enabled)
        self.assertNotEqual(before, self.panel.grid.item(0, 2).text())
        self.assertIn('2 pending edits', self.panel.notice.text())
        self.panel.clear_pending()
        self.assertEqual(before, self.panel.grid.item(0, 2).text())
        self.assertEqual(self.facade.playcalling_snapshot(), snapshot)

    def test_shared_samples_name_the_same_record_and_other_down_stays_independent(self):
        live = self.panel.situation_masks
        aliases = [i for i in range(13, live.bucket.count()) if live.bucket.itemData(i) == 2]
        self.assertGreaterEqual(len(aliases), 3)
        for i in aliases:
            self.assertIn('Shared sample:', live.bucket.itemText(i))
            live.bucket.setCurrentIndex(i)
            self.assertIn('shared Live situations key 2', live.request.text())
        self.panel.queue_edits.setChecked(True)
        self.panel.submit_requests([
            {'kind': 'situation_masks_enabled', 'enabled': True},
            {'kind': 'situation_weight', 'book': 'O-ManBlock', 'key': 2, 'formation': 0, 'value': 4.},
        ])
        for i in aliases:
            live.bucket.setCurrentIndex(i)
            self.assertEqual(live.candidates.cellWidget(0, 4).currentData(), 4.)
        live.bucket.setCurrentIndex(5)
        self.assertEqual(live.candidates.cellWidget(0, 4).currentData(), 1.)


class RevisionCompatibilityTests(unittest.TestCase):
    def test_v1_v2_v3_code_and_canonical_payloads_stay_identical(self):
        expected = {
            'base': ('bb39ee9f752ced58504e8fddb0c2dfed8a7577e1ee799daadb847467a77aec4d',
                     '036b7bd9e6505b8ae24277cb4412c9ee123efda91586ad571879b1a11c9a2529',
                     '8bc1d6ffae725ba80afd0134f8a8f84a7cd6deb6f7ca40dfb364e4596c2a00bf'),
            'tu_1_1': ('edcc2796d01c5f27b82ffe469267e864c1d088d74f2636c255efbb653d6c7cce',
                       '55b9446d84200cf33d851331dd6cb78b65f1e87a1c0ae7c826f75b559f4aabe7',
                       '1393f050c5db7be6b772ba16fc740a805778f111afb4515df18b345e9c78abf4'),
        }
        weights = {'O-ManBlock': [{}, {}, {'14': 4.}] + [{} for _ in range(10)]}
        for profile in mask.PROFILES:
            for version in (1, 2, 3):
                code, _ = mask.assemble(profile, version)
                self.assertEqual(hashlib.sha256(code).hexdigest(), expected[profile.name][version-1])
                data = mask.encode_data({}, {} if version > 1 else None, weights if version == 3 else None, version=version)
                patch = mask.SituationPatch(profile, data)
                self.assertEqual(mask.parse_payload(patch.as_toml().encode()), patch)
            modern = mask.SituationPatch(profile, mask.encode_data({}, {}, weights))
            self.assertEqual(modern.version, 4)
            self.assertEqual(len(mask.assemble(profile, 4)[1]), 4)
            self.assertEqual(mask.parse_payload(modern.as_toml().encode()), modern)


if __name__ == '__main__': unittest.main(verbosity=2)
