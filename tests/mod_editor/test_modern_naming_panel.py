"""Offscreen before/after review, selection refresh and refusal presentation."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
except ImportError:
    QApplication = None
from mod_editor.core import nfl2k5_modern_naming as n


@unittest.skipUnless(QApplication is not None, 'PyQt5 is absent; offscreen naming preview needs Qt')
class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_static_preview_lists_every_before_and_after_without_build_claim(self):
        from mod_editor.gui.modern_naming_panel_qt import ModernNamingPanel
        panel=ModernNamingPanel(SimpleNamespace())
        self.addCleanup(panel.close)
        self.assertEqual(panel.model.rowCount(),24)
        self.assertIn('not connected',panel.summary.text())
        for i,row in enumerate(n.preview_rows()):
            self.assertEqual(panel.model.data(panel.model.index(i,1)),row['retail'])
            self.assertEqual(panel.model.data(panel.model.index(i,2)),row['after'])
            self.assertIn(row['after'],panel.model.data(panel.model.index(i,2),Qt.ToolTipRole))
        self.assertIn('MyCareer',panel.career_note.text())

    def test_toggle_off_restores_preview_and_errors_clear_stale_rows(self):
        from mod_editor.gui.modern_naming_panel_qt import ModernNamingPanel
        enabled=True
        def preview():
            return dict(enabled=enabled,rows=[{**r,'source_verified':True} for r in n.preview_rows(enabled=enabled)])
        host=SimpleNamespace(modern_naming_preview=preview)
        panel=ModernNamingPanel(host);self.addCleanup(panel.close)
        self.assertIn('On in Build',panel.summary.text())
        enabled=False;panel.reload()
        self.assertIn('Off in Build',panel.summary.text())
        self.assertTrue(all(r['before']==r['after'] for r in panel.model.rows))
        def conflict():raise ValueError('Manual text conflict')
        host.modern_naming_preview=conflict;panel.reload()
        self.assertEqual(panel.model.rowCount(),0)
        self.assertIn('Manual text conflict',panel.summary.text())


if __name__=='__main__':unittest.main()
