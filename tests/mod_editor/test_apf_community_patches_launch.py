"""Community patch install/launch flow on fake Xenia folders; no emulator process is started."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio.launcher import COMMUNITY_PATCH_KINDS, LaunchError, XeniaLauncher, XeniaSettings
from mod_editor.core import apf2k8_charge_abilities as charge
from mod_editor.core import apf2k8_community_patches as cp
from mod_editor.core import apf2k8_playcall_patch as pp
from mod_editor.core.errors import ValidationError

UPSTREAM = Path(__file__).resolve().parent / "fixtures" / "apf2k8_community_patches_upstream"


class CommunityLaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        exe = self.root / "xenia-canary"
        exe.write_bytes(b"fake")
        exe.chmod(0o755)
        self.settings = XeniaSettings(self.root / "settings.json")
        self.settings.configure(exe)
        self.launcher = XeniaLauncher(self.settings, self.root / "data")
        self.game = self.root / "game"
        self.game.mkdir()
        (self.game / "default.xex").write_bytes(b"synthetic")

    def export(self, key, enabled=True):
        row = cp.definition(key)
        path = self.root / row.filename
        cp.write_patch(cp.PatchDocument(row, enabled), path)
        return path

    def launch_args(self):
        with patch("mod_editor.apf_studio.launcher.subprocess.Popen", return_value=SimpleNamespace(pid=7)) as popen:
            receipt = self.launcher.launch(self.game)
        return popen.call_args.args[0], receipt

    def storage(self, args):
        return Path(next(a.split("=", 1)[1] for a in args if a.startswith("--storage_root=")))

    def test_default_off_consent_install_launch_sync_and_remove(self):
        for kind, key in COMMUNITY_PATCH_KINDS.items():
            status = self.launcher.pass_fetch_status(kind=kind)
            self.assertFalse(status["installed"])
            self.assertIn("Basileus Maximus", status["message"])
            with self.assertRaisesRegex(LaunchError, "consent"):
                self.launcher.install_pass_fetch_patch(self.export(key), kind=kind)
            with self.assertRaisesRegex(LaunchError, "disabled"):
                self.launcher.install_pass_fetch_patch(self.export(key, False), kind=kind, consent=True)
            self.assertTrue(self.launcher.install_pass_fetch_patch(self.export(key), kind=kind, consent=True)["enabled"])
        args, receipt = self.launch_args()
        folder = self.storage(args) / "patches"
        for kind, key in COMMUNITY_PATCH_KINDS.items():
            row = cp.definition(key)
            self.assertEqual((folder / row.filename).read_bytes(), (self.settings.patches_folder / row.filename).read_bytes())
            self.assertIn(f"Community patch ({row.name.split(':')[0]}) installed", receipt.patch_status)
        self.assertIn("--apply_patches=true", args)
        kind = "community_all_packages_in_substitution"
        self.assertFalse(self.launcher.remove_pass_fetch_patch(kind=kind)["installed"])
        self.launch_args()
        self.assertFalse((folder / cp.definition(COMMUNITY_PATCH_KINDS[kind]).filename).exists())

    def test_wrong_patch_for_kind_refused(self):
        with self.assertRaises(ValidationError):
            self.launcher.install_pass_fetch_patch(self.export("hidden_formations_revealed"),
                                                   kind="community_play_calling_by_package", consent=True)
        upstream = UPSTREAM / "play_calling_by_package.patch.toml"
        with self.assertRaises(ValidationError):
            self.launcher.install_pass_fetch_patch(upstream, kind="community_play_calling_by_package", consent=True)

    def test_upstream_copy_beside_charge_patch_refuses_launch(self):
        source = self.root / charge.FILENAME
        source.write_bytes(charge.PatchDocument(pp.PROFILES[1], True).as_toml().encode())
        self.launcher.install_pass_fetch_patch(source, kind="charge_abilities", consent=True)
        args, _ = self.launch_args()
        folder = self.storage(args) / "patches"
        foreign = folder / "54540807 - play calling by package fixed TU1.1.patch.toml"
        foreign.write_bytes((UPSTREAM / "play_calling_by_package.patch.toml").read_bytes())
        with patch("mod_editor.apf_studio.launcher.subprocess.Popen") as popen, \
                self.assertRaisesRegex(LaunchError, "overwrite the installed charge-abilities patch"):
            self.launcher.launch(self.game)
        popen.assert_not_called()
        self.assertTrue(foreign.is_file())  # foreign files are never removed by the Studio
        foreign.unlink()
        self.launch_args()


class CommunityDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_credits_author_installs_with_consent_and_warns_about_upstream(self):
        from PyQt5.QtWidgets import QLabel, QMessageBox
        from mod_editor.apf_studio.community_patches_qt import CommunityPatchesDialog
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe = root / "xenia-canary"
            exe.write_bytes(b"fake")
            exe.chmod(0o755)
            settings = XeniaSettings(root / "settings.json")
            settings.configure(exe)
            launcher = XeniaLauncher(settings, root / "data")
            settings.patches_folder.mkdir(parents=True, exist_ok=True)
            (settings.patches_folder / "54540807 - all packages.patch.toml").write_bytes(
                (UPSTREAM / "all_packages_in_substitution.patch.toml").read_bytes())
            dialog = CommunityPatchesDialog(launcher)
            texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
            self.assertIn("Basileus Maximus", dialog.windowTitle())
            self.assertIn("Basileus Maximus", texts)
            self.assertIn("Title Update 1.1 only", texts)
            self.assertIn("54540807 - all packages.patch.toml", dialog.warning.text())
            self.assertEqual(set(dialog.status), set(cp.KEYS))
            with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
                dialog.install("play_calling_by_package")
            self.assertFalse(launcher.pass_fetch_status(kind="community_play_calling_by_package")["installed"])
            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                dialog.install("play_calling_by_package")
            self.assertTrue(launcher.pass_fetch_status(kind="community_play_calling_by_package")["enabled"])
            self.assertIn("installed", dialog.status["play_calling_by_package"].text())
            dialog.remove("play_calling_by_package")
            self.assertFalse(launcher.pass_fetch_status(kind="community_play_calling_by_package")["installed"])
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
