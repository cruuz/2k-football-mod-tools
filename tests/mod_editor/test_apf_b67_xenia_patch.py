"""Fake Xenia folders only; no emulator process is started."""
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio.launcher import XeniaSettings, XeniaLauncher, LaunchError, PASS_FETCH_FILENAME
from mod_editor.core import apf2k8_playcall_patch as p


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        exe = self.root / 'xenia-canary'; exe.write_bytes(b'fake'); exe.chmod(0o755)
        self.settings = XeniaSettings(self.root / 'settings.json')
        self.settings.configure(exe)
        self.launcher = XeniaLauncher(self.settings, self.root / 'data')
        self.source = self.root / 'export.patch.toml'
        profile = p.PROFILES[0]
        self.source.write_bytes(p.PlaycallPatch(profile, p.assemble_cave(profile.hook), {}).as_toml().encode())

    def test_consent_install_enable_reload_launch_remove(self):
        config = self.root / 'chosen.config.toml'
        original = b'# retain me\n[Memory]\napply_patches = false # explicit\n[GPU]\ngpu = "vulkan"\n'
        config.write_bytes(original)
        self.settings.configure_patch_config(config)
        with self.assertRaisesRegex(LaunchError, 'consent'):
            self.launcher.install_pass_fetch_patch(self.source)
        self.assertEqual(config.read_bytes(), original)
        self.assertFalse(self.settings.patches_folder.exists())
        status = self.launcher.install_pass_fetch_patch(self.source, consent=True)
        destination = self.settings.patches_folder / PASS_FETCH_FILENAME
        self.assertEqual(destination.read_bytes(), self.source.read_bytes())
        self.assertTrue(status['installed'] and status['enabled'])
        self.assertIn('# retain me', config.read_text())
        self.assertEqual(tomllib.loads(config.read_text())['GPU']['gpu'], 'vulkan')
        again = XeniaSettings(self.settings.config_path)
        self.assertEqual(again.emulator_config, config)
        game = self.root / 'game'; game.mkdir(); (game / 'default.xex').write_bytes(b'fake')
        with patch('mod_editor.apf_studio.launcher.subprocess.Popen', return_value=SimpleNamespace(pid=123)) as popen:
            receipt = XeniaLauncher(again, self.root / 'data').launch(game)
        self.assertIn(f'--config={config}', popen.call_args.args[0])
        self.assertEqual(popen.call_args.kwargs['cwd'], str(self.root))
        self.assertIn('enabled', receipt.patch_status)
        other = destination.with_name('unrelated.patch.toml'); other.write_bytes(b'keep')
        self.assertFalse(self.launcher.remove_pass_fetch_patch()['installed'])
        self.assertEqual(other.read_bytes(), b'keep')
        self.assertTrue(tomllib.loads(config.read_text())['Memory']['apply_patches'])
        self.assertFalse(self.launcher.remove_pass_fetch_patch()['installed'])

    def test_disabled_and_invalid_config_report_and_no_partial_install(self):
        self.settings.emulator_config.write_bytes(b'[Memory]\napply_patches = false\n')
        self.launcher.install_pass_fetch_patch(self.source, consent=True)
        self.settings.emulator_config.write_bytes(b'[Memory]\napply_patches = false\n')
        status = self.launcher.pass_fetch_status()
        self.assertTrue(status['installed']); self.assertFalse(status['enabled'])
        self.launcher.remove_pass_fetch_patch()
        self.settings.emulator_config.write_bytes(b'invalid!')
        with self.assertRaises(ValueError):
            self.launcher.install_pass_fetch_patch(self.source, consent=True)
        self.assertFalse((self.settings.patches_folder / PASS_FETCH_FILENAME).exists())
        self.assertEqual(self.settings.emulator_config.read_bytes(), b'invalid!')

    def test_wrong_patch_refused_and_failed_config_write_rolls_back_patch(self):
        original = self.source.read_bytes()
        self.source.write_bytes(original.replace(b'is_enabled = true', b'is_enabled = false'))
        with self.assertRaisesRegex(LaunchError, 'disabled'):
            self.launcher.install_pass_fetch_patch(self.source, consent=True)
        self.source.write_bytes(original)
        from mod_editor.apf_studio import launcher as module
        atomic = module._atomic_bytes
        def fail_config(path, data):
            if path == self.settings.emulator_config:
                raise OSError('fake write failure')
            atomic(path, data)
        with patch.object(module, '_atomic_bytes', side_effect=fail_config), self.assertRaises(OSError):
            self.launcher.install_pass_fetch_patch(self.source, consent=True)
        self.assertFalse((self.settings.patches_folder / PASS_FETCH_FILENAME).exists())


if __name__ == '__main__':
    unittest.main()
