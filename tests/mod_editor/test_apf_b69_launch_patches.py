"""Prove discovery directory against the actual launch argv, without Xenia."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor import test_apf_b67_xenia_patch as previous
from mod_editor.apf_studio.launcher import PASS_FETCH_FILENAME, LaunchError
from mod_editor.apf_studio import playcalling_patches
from mod_editor.core import apf2k8_playcall_curves_patch as curves


class LaunchPatchTests(previous.PatchTests):
    def launch_args(self, game):
        with patch('mod_editor.apf_studio.launcher.subprocess.Popen', return_value=SimpleNamespace(pid=123)) as popen:
            self.launcher.launch(game)
        return popen.call_args.args[0]

    def test_both_managed_patches_reach_storage_root_and_removal_propagates(self):
        game=self.root/'game';game.mkdir();(game/'default.xex').write_bytes(b'synthetic')
        self.launcher.install_pass_fetch_patch(self.source,consent=True)
        payload=playcalling_patches.prepare('base','offense')
        source=self.root/'curve.patch.toml';source.write_bytes(payload)
        self.launcher.install_pass_fetch_patch(source,kind='curves',consent=True)
        args=self.launch_args(game)
        storage=Path(next(a.split('=',1)[1] for a in args if a.startswith('--storage_root=')))
        self.assertNotEqual(storage,self.settings.xenia_path.parent)
        self.assertEqual((storage/'patches'/PASS_FETCH_FILENAME).read_bytes(),self.source.read_bytes())
        self.assertEqual((storage/'patches'/playcalling_patches.FILENAME).read_bytes(),payload)
        self.assertIn('--apply_patches=true',args)
        other=storage/'patches'/'12345678-unrelated.patch.toml';other.write_bytes(b'keep')
        self.launcher.remove_pass_fetch_patch()
        self.launch_args(game)
        self.assertFalse((storage/'patches'/PASS_FETCH_FILENAME).exists())
        self.assertEqual(other.read_bytes(),b'keep')
        self.assertTrue((storage/'patches'/playcalling_patches.FILENAME).is_file())
        self.settings.emulator_config.write_bytes(b'[Memory]\napply_patches = false\n')
        self.assertIn('--apply_patches=false',self.launch_args(game))

    def test_foreign_managed_destination_refuses_before_process_start(self):
        game=self.root/'game';game.mkdir();(game/'default.xex').write_bytes(b'synthetic')
        self.launcher.install_pass_fetch_patch(self.source,consent=True)
        args=self.launch_args(game)
        storage=Path(next(a.split('=',1)[1] for a in args if a.startswith('--storage_root=')))
        target=storage/'patches'/PASS_FETCH_FILENAME
        target.write_bytes(b'foreign')
        with patch('mod_editor.apf_studio.launcher.subprocess.Popen') as popen, self.assertRaises(ValueError):
            self.launcher.launch(game)
        popen.assert_not_called()
        self.assertEqual(target.read_bytes(),b'foreign')


if __name__=='__main__':unittest.main(verbosity=2)
