"""Independent beta-69 source-transition regressions; no game payload fixtures."""
import os
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class HandoffPathsTests(unittest.TestCase):
    def test_a2b_report_describes_actual_runtime_pin_block_and_climate_controls(self):
        report = (ROOT / 'ASTRA_B69_A2B_REPORT.md').read_text()
        tree = ast.parse((ROOT / 'packaging/check_2k5_mod_studio_runtime.py').read_text())
        pins = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'B69_GAME_RUNTIME_PINS' for t in n.targets))
        with self.subTest(contract='pin count'):
            self.assertTrue(f'| Additional B69 runtime pin entries | 0 | {len(pins)} |' in report,
                            'A2b pin-block count differs from its implementation')
        with self.subTest(contract='climate controls'):
            self.assertFalse('climate path/choose/editor/clear controls' in report,
                             'A2b describes a separate climate Clear control that does not exist')

    def test_beta69_handoffs_name_the_merged_job_documents(self):
        changelog = (ROOT / 'docs/mod_editor/2k5_mod_studio_changelog.md').read_text()
        beta69 = changelog.split('## v1.0 RC94', 1)[1].split('\n## ', 1)[0]
        self.assertFalse('ASTRA_REPORT.md' in beta69, 'beta-69 notes still point at a generic job report')
        self.assertFalse('`WIRING.md`' in beta69, 'beta-69 notes still point at generic wiring')
        self.assertIn('ASTRA_B69_J3_REPORT.md', beta69)
        weather = (ROOT / 'docs/research/nfl2k5_weather_time_of_day.md').read_text()
        self.assertIn('(../../WIRING_B69_J4.md)', weather)
        self.assertNotIn('(../../WIRING.md)', weather)
        self.assertTrue((ROOT / 'ASTRA_B69_J3_REPORT.md').is_file())
        self.assertTrue((ROOT / 'WIRING_B69_J4.md').is_file())


class SourceTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_new_source_does_not_inherit_modern_scrambles_from_previous_disc(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel
        for panel_class in (BuildPanel, GameplayPatchesPanel):
            for mode in ('retail', 'foreign', 'unknown'):
                with self.subTest(panel=panel_class.__name__, mode=mode):
                    panel = panel_class()
                    self.addCleanup(panel.close)
                    panel.apply_state(dict(path='installed.iso', container='xiso', cpu_scrambles='applied'))
                    self.assertEqual(panel.plan().cpu_scrambles, 'modern')
                    panel.apply_state(dict(path='next.iso', container='xiso', cpu_scrambles=mode))
                    self.assertEqual(panel.plan().cpu_scrambles, 'retail')
                    self.assertEqual(panel.cpu_scrambles_level.isEnabled(), mode == 'retail')

    def test_linked_source_transition_then_saved_project_restore(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel
        from mod_editor.gui.gameplay_project_ui import GameplayBuildLink
        build, gameplay = BuildPanel(), GameplayPatchesPanel()
        self.addCleanup(build.close)
        self.addCleanup(gameplay.close)
        link = GameplayBuildLink(build, gameplay, lambda: None)
        for state in ('applied', 'retail'):
            info = dict(path=state + '.iso', container='xiso', cpu_scrambles=state)
            build.apply_state(info)
            gameplay.apply_state(info)
            link.refresh_from_build()
            for panel in (build, gameplay):
                self.assertEqual(panel.plan().cpu_scrambles, 'modern' if state == 'applied' else 'retail')
        build.restore_project_build_settings({'cpu_scrambles': 'modern'})
        link.refresh_from_build()
        self.assertEqual(build.plan().cpu_scrambles, 'modern')
        self.assertEqual(gameplay.plan().cpu_scrambles, 'modern')


if __name__ == '__main__':
    unittest.main()
