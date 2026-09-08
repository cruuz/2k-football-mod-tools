from pathlib import Path
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
try:
    from PyQt5.QtWidgets import QApplication
    from mod_editor.gui.stadium_blender_panel_qt import StadiumBlenderPanel, WORKFLOW_TEXT, texture_import_summary
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, 'PyQt5 is absent; Stadiums workflow card requires Qt')
class StadiumPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_actions_emit_and_boundary_is_visible(self):
        card = StadiumBlenderPanel()
        self.addCleanup(card.deleteLater)
        calls = []
        card.exportRequested.connect(lambda: calls.append('export'))
        card.importRequested.connect(lambda: calls.append('import'))
        card.export_button.click()
        card.import_button.click()
        self.assertEqual(calls, ['export', 'import'])
        self.assertIn('EXPERIMENTAL / UNWITNESSED', WORKFLOW_TEXT)
        self.assertIn('cannot be written', WORKFLOW_TEXT)

    def test_unchanged_import_does_not_mark_the_workspace_dirty(self):
        text, changed = texture_import_summary([SimpleNamespace(changed=False)] * 3)
        self.assertEqual(changed, 0)
        self.assertEqual(text, '0 texture(s) staged; 3 unchanged.')


if __name__ == '__main__':
    unittest.main()
