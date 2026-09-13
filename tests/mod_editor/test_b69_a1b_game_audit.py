"""Independent beta-69 source-transition regressions; no game payload fixtures."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


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
