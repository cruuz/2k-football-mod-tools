"""Fake runtime executables only. Every process launch is mocked."""
from pathlib import Path
import json
import os
import sys
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio.launcher import XeniaSettings, XeniaLauncher, LaunchError, _sdl_config


class EdgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def executable(self, name):
        path = self.root / name
        path.write_bytes(b'synthetic executable; never run')
        path.chmod(0o755)
        return path

    def test_config_writer_preserves_settings_and_is_idempotent(self):
        old = b'# keep\n[HID]\nhid = "xinput" # controller\nvibration = false\n[Memory]\napply_patches = false\n[GPU]\ngpu = "vulkan"\n'
        new = _sdl_config(old)
        expected = tomllib.loads(old.decode())
        expected['HID']['hid'] = 'sdl'
        self.assertEqual(tomllib.loads(new.decode()), expected)
        self.assertIn(b'# controller', new)
        self.assertIn(b'# keep', new)
        self.assertEqual(_sdl_config(new), new)
        for source in (b'', b'[HID]', b'[GPU]\ngpu="vulkan"', b'\xef\xbb\xbf# BOM\n'):
            self.assertEqual(tomllib.loads(_sdl_config(source).decode())['HID']['hid'], 'sdl')
        for source in (b'invalid!', b'HID = 3', b'[HID]\nhid="sdl"\nhid="xinput"'):
            with self.assertRaises(LaunchError):
                _sdl_config(source)

    def test_detect_save_reload_and_explicit_renamed_edge(self):
        for name, runtime, config in (
            ('xenia_edge', 'edge', 'xenia-edge.config.toml'),
            ('Xenia-Edge.AppImage', 'edge', 'xenia-edge.config.toml'),
            ('xenia_canary', 'canary', 'xenia-canary.config.toml'),
            ('xenia', 'default', 'xenia.config.toml'),
        ):
            with self.subTest(name=name):
                settings = XeniaSettings(self.root / 'settings.json')
                settings.configure(self.executable(name))
                self.assertEqual(settings.runtime, runtime)
                self.assertEqual(settings.emulator_config.name, config)
                self.assertEqual(tomllib.loads(settings.emulator_config.read_text())['HID']['hid'], 'sdl')
                again = XeniaSettings(settings.config_path)
                self.assertTrue(again.configured)
                self.assertEqual(again.runtime, runtime)
                self.assertEqual(again.emulator_config, settings.emulator_config)
        with patch('mod_editor.apf_studio.launcher.platform_compat.IS_WINDOWS', True):
            settings.configure(self.executable('renamed.exe'), runtime='edge')
            self.assertIsNone(settings.wine_path)
            self.assertEqual(XeniaSettings(settings.config_path).runtime_label, 'Xenia Edge')

    def test_legacy_settings_load_without_mutation(self):
        exe = self.executable('xenia_canary')
        path = self.root / 'settings.json'
        payload = json.dumps({'schema': XeniaSettings.SCHEMA, 'xenia_path': str(exe)}).encode()
        path.write_bytes(payload)
        settings = XeniaSettings(path)
        self.assertEqual(settings.runtime, 'canary')
        self.assertEqual(path.read_bytes(), payload)
        self.assertFalse(settings.emulator_config.exists())

    def test_launch_windows_native_and_wine_use_sdl_and_selected_config(self):
        for runtime, native_windows, suffix in (('edge', True, '.exe'), ('canary', True, '.exe'),
                                                ('edge', False, ''), ('canary', False, ''),
                                                ('edge', False, '.exe'), ('canary', False, '.exe')):
            with self.subTest(runtime=runtime, native_windows=native_windows, suffix=suffix), patch(
                    'mod_editor.apf_studio.launcher.platform_compat.IS_WINDOWS', native_windows):
                exe = self.executable('xenia_' + runtime + suffix)
                wine = self.executable('wine')
                config = self.root / 'chosen config.toml'
                config.write_bytes(b'[HID]\nhid="xinput"\n[Memory]\napply_patches=false\n')
                settings = XeniaSettings(self.root / 'settings.json')
                settings.configure(exe, wine, xenia_config=config)
                game = self.root / 'game folder'
                game.mkdir(exist_ok=True)
                (game / 'default.xex').write_bytes(b'synthetic')
                launcher = XeniaLauncher(settings, self.root / 'data')
                with patch('mod_editor.apf_studio.launcher.subprocess.Popen', return_value=SimpleNamespace(pid=1)) as start, patch.object(
                        launcher, '_winepath', side_effect=lambda w, p, env: 'WIN:' + str(p)):
                    launcher.launch(game)
                args = start.call_args.args[0]
                uses_wine = suffix == '.exe' and not native_windows
                self.assertEqual(args[0], str(wine if uses_wine else exe))
                self.assertIn('--hid=sdl', args)
                self.assertNotIn('--hid=xinput', args)
                self.assertIn('--config=' + ('WIN:' if uses_wine else '') + str(config), args)
                self.assertIn('--apply_patches=false', args)
                self.assertEqual(args[-1], ('WIN:' if uses_wine else '') + str(game / 'default.xex'))
                self.assertEqual(start.call_args.kwargs['cwd'], str(exe.parent))
                self.assertTrue(start.call_args.kwargs['close_fds'])

    def test_invalid_config_never_launches_or_overwrites(self):
        settings = XeniaSettings(self.root / 'settings.json')
        settings.configure(self.executable('xenia_edge'))
        settings.emulator_config.write_bytes(b'invalid!')
        game = self.root / 'game'; game.mkdir(); (game / 'default.xex').write_bytes(b'synthetic')
        with patch('mod_editor.apf_studio.launcher.subprocess.Popen') as start, self.assertRaises(LaunchError):
            XeniaLauncher(settings, self.root / 'data').launch(game)
        start.assert_not_called()
        self.assertEqual(settings.emulator_config.read_bytes(), b'invalid!')


if __name__ == '__main__':
    unittest.main(verbosity=2)
