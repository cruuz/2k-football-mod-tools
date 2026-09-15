"""Integrated jersey forms and real completion consumers retain honest state."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from mod_editor.core import build_feedback, mod_build, nfl2k5_uniform_choice as uniform
from mod_editor.core.nfl2k5_build_service import BuildResult
from mod_editor.gui import beta62_options as captions, gameplay_project_ui, studio_qt
from mod_editor.gui.build_panel_qt import BuildPanel
from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel
from nfl2k5_throw_tuning_test import _build_synthetic_xbe


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'default.xbe'
            source.write_bytes(_build_synthetic_xbe())
            cls.state = mod_build.inspect(source)

    def test_readers_take_installed_form_from_executable_bytes(self):
        payload = bytearray(_build_synthetic_xbe())
        for _label, va, before, _after in uniform.sites('choice'):
            offset = uniform._offset(payload, va)
            payload[offset:offset + len(before)] = before
        panel = BuildPanel()
        self.addCleanup(panel.deleteLater)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'default.xbe'
            for mode in ('rule', 'choice'):
                installed, _receipt = uniform.apply(bytes(payload), mode)
                source.write_bytes(installed)
                state = mod_build.inspect(source)
                self.assertEqual(state['uniform_choice'], 'applied')
                self.assertEqual(state['uniform_choice_mode'], mode)
                panel.apply_state(state)
                self.assertEqual(panel.uniform_choice_mode.currentData(), mode)
                self.assertEqual(panel.uniform_choice_check.text(), captions.uniform_choice_caption(mode))
                # Exercise the image reader's real descriptor/readback and
                # dictionary with only the synthetic archive extent supplied.
                with patch.object(mod_build.tt, 'image_xbe_extent', return_value=(0, len(installed))), \
                     patch.object(mod_build.tt, '_edge_disc_status', return_value='retail'):
                    image_state = mod_build.tt.read_image(source)
                self.assertEqual(image_state['uniform_choice'], 'applied')
                self.assertEqual(image_state['uniform_choice_mode'], mode)

    def test_build_form_survives_source_and_saved_project_transitions(self):
        panel = BuildPanel()
        self.addCleanup(panel.deleteLater)
        retail = dict(self.state, uniform_choice='retail', uniform_choice_mode=None)
        panel.apply_state(retail)
        self.assertEqual(panel.uniform_choice_check.text(), captions.uniform_choice_caption(''))
        for mode in ('choice', 'rule'):
            panel.uniform_choice_check.setChecked(True)
            panel.uniform_choice_mode.setCurrentIndex(panel.uniform_choice_mode.findData(mode))
            self.assertEqual(panel.plan().uniform_choice, mode)
            self.assertEqual(panel.uniform_choice_check.text(), captions.uniform_choice_caption(mode))
        installed = dict(retail, uniform_choice='applied', uniform_choice_mode='rule')
        panel.apply_state(installed)
        self.assertFalse(panel.uniform_choice_mode.isEnabled())
        self.assertEqual(panel.uniform_choice_mode.currentData(), 'rule')
        gameplay_project_ui.restore(panel, {'uniform_choice': 'choice'})
        self.assertEqual(panel.uniform_choice_check.text(), captions.uniform_choice_caption('rule'))
        self.assertEqual(panel.uniform_choice_mode.currentData(), 'rule')
        self.assertFalse(panel.uniform_choice_mode.isEnabled())
        panel.apply_state(retail)
        self.assertEqual(panel.uniform_choice_mode.currentData(), 'choice')
        self.assertEqual(panel.plan().uniform_choice, '')
        gameplay_project_ui.restore(panel, {'uniform_choice': 'rule'})
        self.assertEqual(panel.plan().uniform_choice, 'rule')
        self.assertEqual(panel.uniform_choice_check.text(), captions.uniform_choice_caption('rule'))
        self.assertTrue(panel.uniform_choice_mode.isEnabled())
        panel.apply_state(dict(retail, uniform_choice='foreign'))
        self.assertFalse(panel.uniform_choice_check.isEnabled())
        self.assertFalse(panel.uniform_choice_mode.isEnabled())
        self.assertIn('neither retail nor this patch', panel.uniform_choice_check.toolTip())
        for name in mod_build.PRESETS:
            self.assertEqual(mod_build.PRESETS[name]['uniform_choice'], '', name)

    def test_gameplay_names_installed_rule_and_restores_foreign_refusal(self):
        panel = GameplayPatchesPanel()
        self.addCleanup(panel.deleteLater)
        retail = dict(self.state, uniform_choice='retail', uniform_choice_mode=None)
        panel.apply_state(retail)
        check = panel.checks['uniform_choice']
        check.setChecked(True)
        self.assertEqual(panel.plan().uniform_choice, 'choice')
        self.assertEqual(check.text(), captions.uniform_choice_caption('choice'))
        for mode in ('rule', 'choice', None):
            panel.apply_state(dict(retail, uniform_choice='applied', uniform_choice_mode=mode))
            self.assertFalse(check.isEnabled())
            self.assertEqual(check.text(), captions.uniform_choice_caption(mode))
            self.assertIn('Installed '+str(mode or 'unknown form'), panel.badges['uniform_choice'].text())
        panel.apply_state(dict(retail, uniform_choice='foreign'))
        self.assertIn('neither retail nor this patch', check.toolTip())
        panel.apply_state(retail)
        self.assertEqual(check.text(), captions.uniform_choice_caption(''))
        self.assertNotIn('Installed', panel.badges['uniform_choice'].text())

    def test_actual_completion_paths_share_summary_and_preserve_receipts(self):
        rows = [dict(kind='live_number_nameplate', selector='arm:1', family='arm', digit=1,
                     asset_code='26', side='A', variant=0, shortfall_bytes=42,
                     suggestion=dict(width=32, height=32, colours=16), message='old wall '*20)]
        receipt = dict(outcome=dict(status='changed', message='Measured changed bytes.'),
                       steps=[dict(kept_retail=rows*2+[dict(message='Legacy warning')])])
        original = deepcopy(receipt)
        title, body = build_feedback.completion(receipt)
        self.assertEqual(title, 'Disc ready')
        self.assertEqual(body.count('42 bytes over; 32 x 32 at 16 colours fits'), 1)
        self.assertIn('Legacy warning', body)
        self.assertNotIn('old wall', body)
        self.assertEqual(receipt, original)
        self.assertEqual(build_feedback.completion({})[0], 'Copy ready; changes not measured')
        result = BuildResult(Path('out.iso'), 100, 'a'*64, 1, 20, kept_retail=tuple(rows))
        fake = SimpleNamespace(_build_panel=None, _refuse_while_audio_busy=lambda *args: False,
                               _set_status=lambda *args: None, _refresh_edit_state=lambda: None)
        fake._start_task = lambda operation, success, **kwargs: success(result)
        with patch.object(studio_qt.QFileDialog, 'getSaveFileName', return_value=('out.iso', '')), \
             patch.object(studio_qt.QMessageBox, 'information') as dialog:
            studio_qt.StudioMainWindow._choose_build_output(fake)
        body = dialog.call_args.args[2]
        self.assertIn('42 bytes over; 32 x 32 at 16 colours fits', body)
        self.assertNotIn('old wall', body)


if __name__ == '__main__':
    unittest.main()
