"""Execute the proposed protected panel in memory; do not edit protected files."""
from pathlib import Path
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from tools.mycareer_mode.b69_wiring import panel_source, build_source


@unittest.skipUnless(importlib.util.find_spec('PyQt5'), 'PyQt5 required for the proposed panel')
class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.module = types.ModuleType('b69_proposed_mycareer_panel')
        exec(compile(panel_source()[1], 'WIRING.md:MyCareerPanel', 'exec'), cls.module.__dict__)

    def test_default_template_tier_and_position_aliases(self):
        panel = self.module.MyCareerPanel()
        self.assertEqual(panel.prospect.currentData(), 0)
        self.assertEqual(panel.template.currentData(), 0)
        self.assertEqual(panel.template.currentText(), 'Pocket QB')
        self.assertEqual(panel.career_playcall.currentText(), 'You call every play')
        panel.prospect.setCurrentIndex(1)
        self.assertFalse(panel.starter.isEnabled())
        panel.prospect.setCurrentIndex(0)
        self.assertTrue(panel.starter.isEnabled())
        self.assertEqual(panel.template.count(), 4)
        panel.position.setCurrentIndex(panel.position.findData(11))
        self.assertEqual(panel.template.count(), 3)
        panel.close()
        compile(build_source()[1], 'WIRING.md:mod_build', 'exec')

    def test_saved_caller_is_loaded_and_real_export_round_trips(self):
        from mod_editor.core import nfl2k5_my_career_save as save
        from mod_editor.core.nfl2k5_roster_records import SaveContainer, sign_save
        from tests.nfl2k5_my_career_fixture import draft_save
        from tests.mod_editor.test_nfl2k5_my_career_inline import block_for
        import zipfile
        source = draft_save()
        payload = save.with_playcall(source + block_for(source), 'By position')
        with tempfile.TemporaryDirectory() as directory:
            original, target = Path(directory) / 'source.zip', Path(directory) / 'export.zip'
            with zipfile.ZipFile(original, 'w') as archive:
                archive.writestr('SAVEGAME.DAT', payload)
                archive.writestr('EXTRA', sign_save(payload))
            panel = self.module.MyCareerPanel()
            panel._run = lambda action, done: done(action())
            with patch.object(self.module.QFileDialog, 'getOpenFileName', return_value=(str(original), '')):
                panel._choose_career_settings()
            self.assertEqual(panel.career_playcall.currentText(), 'By position')
            self.assertTrue(panel.career_playcall.isEnabled())
            panel.career_playcall.setCurrentText('Coach calls the plays')
            panel.career_supersim.setCurrentText('Fast forward')
            with patch.object(self.module.QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
                panel._export_career_settings()
            reopened = SaveContainer.load(target).savegame
            self.assertEqual(save.playcall_choice(reopened), 'Coach calls the plays')
            self.assertEqual(save.supersim_choice(reopened), 'Fast forward')
            self.assertEqual(reopened[:-128], source)
            self.assertEqual(SaveContainer.load(original).savegame, payload)
            panel.close()

    def test_build_dependencies_use_the_already_frozen_setup(self):
        # Stop at recipe capture, before any disc preflight or output. The
        # ordinary option/dependency code executes from the proposed patch.
        name = 'mod_editor.core.b69_proposed_build'
        module = types.ModuleType(name)
        module.__package__ = 'mod_editor.core'
        module.__file__ = str(ROOT / 'mod_editor/core/mod_build.py')
        with patch.dict(sys.modules, {name: module}):
            exec(compile(build_source()[1], module.__file__, 'exec'), module.__dict__)
        class Captured(Exception):
            pass
        for tier, depth, draft in ((None, True, True), (0, False, False), (4, True, False)):
            with self.subTest(tier=tier), tempfile.TemporaryDirectory() as directory:
                state = bytearray(1280)
                state[212:216] = int(tier or 0).to_bytes(4, 'little')
                plan = module.BuildPlan(
                    source=str(Path(directory) / 'source.iso'),
                    target=str(Path(directory) / 'output.iso'), my_career=True,
                    my_career_setup=None if tier is None else 'already-frozen.json')
                observed = []
                def capture(effective):
                    observed.append(effective)
                    raise Captured
                with patch.object(module, 'validate_plan', return_value=[]), \
                     patch.object(module.BuildPlan, 'to_recipe', capture), \
                     patch.object(module.tt.my_career_patch, 'read_setup',
                                  side_effect=AssertionError('setup read twice')):
                    with self.assertRaises(Captured):
                        module._build(plan, r62_options={'my_career_setup': bytes(state)})
                self.assertEqual(len(observed), 1)
                self.assertEqual(observed[0].depth_locks, depth)
                self.assertEqual(observed[0].draft_ai, draft)
                self.assertTrue(observed[0].xbe_space)
                self.assertFalse(Path(plan.target).exists())


if __name__ == '__main__':
    unittest.main()
