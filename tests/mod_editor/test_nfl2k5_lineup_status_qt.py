"""Studio offers the CPU repair on complete old discs and recognizes fixed ones."""
import os
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication
from mod_editor.gui.build_panel_qt import BuildPanel
from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel
from mod_editor.core import mod_build


class StatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_build_and_gameplay_offer_old_disc_upgrade(self):
        state = dict(container='xiso', path='/tmp/sd2-fake.iso', position_pools='needs_fix',
                     position_pool_lineup='retail', scheme_labels='applied',
                     screen_timing_details={'level': 'D'})
        with patch.object(mod_build, 'inspect_screen_timing', return_value={'status': 'retail', 'level': 'D'}):
            for panel in (BuildPanel(available={'position_pools': True}), GameplayPatchesPanel()):
                try:
                    panel.apply_state(state)
                    box = panel.position_pools_check if isinstance(panel, BuildPanel) else panel.checks['position_pools']
                    self.assertTrue(box.isEnabled())
                    self.assertIn('repair is missing', box.toolTip())
                    box.setChecked(True)
                    self.assertTrue(panel.plan().position_pools)
                    panel.apply_state({**state, 'position_pools': 'applied', 'position_pool_lineup': 'applied'})
                    self.assertFalse(box.isEnabled())
                    self.assertIn('Already installed', box.toolTip())
                finally:
                    panel.deleteLater()


if __name__ == '__main__':
    unittest.main()
