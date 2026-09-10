"""Persistent disc paths and permissions, without starting an emulator."""
from pathlib import Path
import sys
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.studio import xemu_settings as x
from mod_editor.studio.facade import _xemu_launch_argv, Nfl2k5StudioFacade, ExternalBuild
from mod_editor.core.errors import ValidationError


class SettingsTests(unittest.TestCase):
    def test_toml_preserves_settings_and_comments_and_roundtrips_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root / 'xemu.toml'
            text = '# keep me\n[sys.files]\nbootrom_path = "bios.bin"\ndvd_path = "old.iso"\n[display]\nscale = 2\n'
            path.write_text(text)
            disc = root / 'folder # one' / 'quoted "disc".xiso.iso'
            x.remember_disc(path, disc)
            data = tomllib.loads(path.read_text())
            self.assertEqual(data['sys']['files'], dict(bootrom_path='bios.bin', dvd_path=str(disc)))
            self.assertEqual(data['display'], dict(scale=2))
            self.assertIn('# keep me', path.read_text())
            before = path.read_bytes()
            x.remember_disc(path, disc)
            self.assertEqual(path.read_bytes(), before)
            empty = root / 'new/xemu.toml'
            x.remember_disc(empty, disc)
            self.assertEqual(tomllib.loads(empty.read_text())['sys']['files']['dvd_path'], str(disc))

    def test_invalid_and_unusual_toml_are_not_corrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'xemu.toml'
            for original in ('[broken', '[sys.files]\ndvd_path = """one\ntwo"""\n',
                             'sys = "bad"\n', '[sys]\nfiles = 42\n'):
                p.write_text(original)
                with self.assertRaises(ValueError): x.remember_disc(p, Path(tmp) / 'disc.iso')
                self.assertEqual(p.read_text(), original)

    def test_sdl_platform_locations_and_windows_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            exe = root / 'portable/xemu.exe'
            exe.parent.mkdir()
            command = [str(exe)]
            kwargs = dict(home=root, environ={})
            self.assertEqual(x.config_path(command, platform='linux', **kwargs), root / '.local/share/xemu/xemu/xemu.toml')
            self.assertEqual(x.config_path(command, platform='darwin', **kwargs), root / 'Library/Application Support/xemu/xemu/xemu.toml')
            self.assertEqual(x.config_path(command, platform='win32', **kwargs), root / 'AppData/Roaming/xemu/xemu/xemu.toml')
            (exe.parent / 'xemu.toml').touch()
            self.assertEqual(x.config_path(command, platform='win32', **kwargs), exe.parent / 'xemu.toml')
            self.assertEqual(x.config_path(['flatpak','run',x.APP_ID], **kwargs), root / '.var/app/app.xemu.xemu/data/xemu/xemu/xemu.toml')
            self.assertEqual(x.config_path(['xemu','-config_path',str(root/'custom.toml')]), root/'custom.toml')

    def test_persistent_readonly_grant_only_once(self):
        folder = Path(tempfile.gettempdir()).resolve() / 'build folder'
        command = ['flatpak', 'run', x.APP_ID]
        runner = Mock(side_effect=[SimpleNamespace(returncode=0, stdout=''), SimpleNamespace(returncode=0)])
        self.assertIn('persistent Flatpak read-only', x.grant_build_folder(command, folder, runner=runner))
        self.assertEqual(runner.call_args.args[0], ('flatpak','override','--user',f'--filesystem={folder}:ro',x.APP_ID))
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout=f'[Context]\nfilesystems={folder}:ro;\n'))
        self.assertEqual(x.grant_build_folder(command, folder, runner=runner), '')
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(_xemu_launch_argv(('xemu',), folder/'disc.iso'), ('xemu','-dvd_path',str(folder/'disc.iso')))

    def test_success_saves_and_footer_names_path_failure_does_not_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); disc = root/'NFL 2K5 Modded.xiso.iso'; disc.write_bytes(b'synthetic')
            launcher = Mock()
            facade = Nfl2k5StudioFacade(uniform_catalog=SimpleNamespace(), xemu_command=('xemu',), process_launcher=launcher)
            facade._last_build = ExternalBuild(disc)
            config = root/'xemu.toml'
            with patch.object(x,'config_path',return_value=config), \
                    patch('mod_editor.studio.facade._validate_xemu_executable'):
                result = facade.launch_xemu(lambda *args: None)
                self.assertIn(f'Your disc: {disc}', result.message)
                self.assertIn('Machine > Load Disc', result.message)
                self.assertEqual(tomllib.loads(config.read_text())['sys']['files']['dvd_path'], str(disc))
                config.unlink(); launcher.side_effect=OSError('failed')
                with self.assertRaises(ValidationError):facade.launch_xemu(lambda *args:None)
                self.assertFalse(config.exists())


if __name__ == '__main__':unittest.main()
