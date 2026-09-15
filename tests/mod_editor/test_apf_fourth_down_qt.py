"""Offscreen editor default, preview and persisted-value checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import unittest

try:
    from PySide6.QtWidgets import QApplication
    from mod_editor.apf_studio.fourth_down_qt import FourthDownDialog
except ImportError:
    QApplication = None

from mod_editor.apf_studio.launcher import XeniaSettings, XeniaLauncher
from mod_editor.core import apf2k8_fourth_down as f


@unittest.skipIf(QApplication is None, 'Optional PySide6 is absent')
class FourthDownQtTests(unittest.TestCase):
    def test_defaults_preview_and_reopen(self):
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            exe=root/'xenia_edge'; exe.write_bytes(b'fake');exe.chmod(0o755)
            settings=XeniaSettings(root/'settings.json');settings.configure(exe)
            launcher=XeniaLauncher(settings,root/'data')
            dialog=FourthDownDialog(launcher)
            self.assertFalse(dialog.enabled.isChecked())
            self.assertFalse(dialog.install_button.isEnabled())
            self.assertEqual(dialog.preview.item(3,2).text(),'Punt')
            dialog.fields['own_half_limit'].setValue(75)
            dialog.fields['short_yards'].setValue(2)
            dialog.fields['fallback_threshold'].setValue(1)
            self.assertEqual(dialog.preview.item(3,2).text(),'Go / scrimmage')
            dialog.enabled.setChecked(True)
            doc=dialog.document()
            output=root/'authored.patch.toml'; f.write_patch(doc,output)
            launcher.install_pass_fetch_patch(output,kind='fourth_down',consent=True)
            reopened=FourthDownDialog(launcher)
            self.assertEqual(reopened.document(),doc)
            reopened.reset_defaults()
            self.assertEqual(reopened.document().thresholds,f.Thresholds())
            self.assertFalse(reopened.enabled.isChecked())
            dialog.close();reopened.close();app.processEvents()


if __name__ == '__main__':
    unittest.main(verbosity=2)
