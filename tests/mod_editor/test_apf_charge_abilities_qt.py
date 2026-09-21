"""Offscreen opt-in Build checkbox, export/install controls and revert."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

try:
    from PyQt5.QtWidgets import QApplication
    from mod_editor.apf_studio.charge_abilities_qt import ChargeAbilitiesDialog
except ImportError:
    QApplication = None
from mod_editor.apf_studio.build import ApfBuildOptions
from mod_editor.apf_studio.launcher import XeniaLauncher, XeniaSettings


@unittest.skipIf(QApplication is None, "Optional PyQt5 absent")
class ChargeQtTests(unittest.TestCase):
    def test_build_default_install_and_remove(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exe = root / "xenia_edge"
            exe.write_bytes(b"authored")
            exe.chmod(0o755)
            settings = XeniaSettings(root / "settings.json")
            settings.configure(exe)
            facade = SimpleNamespace(build_options=ApfBuildOptions(), launcher=XeniaLauncher(settings, root / "data"))
            dialog = ChargeAbilitiesDialog(facade)
            self.assertFalse(dialog.build_enabled.isChecked())
            self.assertFalse(dialog.enabled.isChecked())
            self.assertFalse(dialog.install_button.isEnabled())
            dialog.build_enabled.setChecked(True)
            self.assertTrue(facade.build_options.charge_abilities)
            dialog.enabled.setChecked(True)
            dialog.install()
            self.assertTrue(facade.launcher.pass_fetch_status(kind="charge_abilities")["enabled"])
            reopened = ChargeAbilitiesDialog(facade)
            self.assertTrue(reopened.build_enabled.isChecked())
            reopened.remove()
            self.assertFalse(facade.build_options.charge_abilities)
            self.assertFalse(facade.launcher.pass_fetch_status(kind="charge_abilities")["installed"])
            reopened.close()
            dialog.close()
            app.processEvents()
