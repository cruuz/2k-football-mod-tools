"""Persistent disc paths and permissions, without starting an emulator."""
import json
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
            data = tomllib.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['sys']['files'], dict(bootrom_path='bios.bin', dvd_path=str(disc)))
            self.assertEqual(data['display'], dict(scale=2))
            self.assertIn('# keep me', path.read_text(encoding='utf-8'))
            before = path.read_bytes()
            x.remember_disc(path, disc)
            self.assertEqual(path.read_bytes(), before)
            empty = root / 'new/xemu.toml'
            x.remember_disc(empty, disc)
            self.assertEqual(tomllib.loads(empty.read_text(encoding='utf-8'))['sys']['files']['dvd_path'], str(disc))

    def test_invalid_and_unusual_toml_are_not_corrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'xemu.toml'
            for original in ('[broken', '[sys.files]\ndvd_path = """one\ntwo"""\n',
                             'sys = "bad"\n', '[sys]\nfiles = 42\n'):
                p.write_text(original)
                with self.assertRaises(ValueError): x.remember_disc(p, Path(tmp) / 'disc.iso')
                self.assertEqual(p.read_text(encoding='utf-8'), original)

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
                # The footer abbreviates a path under the home folder with ~ (Windows temp dirs live there).
                self.assertIn(x.disc_help(disc), result.message)
                self.assertIn('Machine > Load Disc', result.message)
                self.assertEqual(tomllib.loads(config.read_text(encoding='utf-8'))['sys']['files']['dvd_path'], str(disc))
                config.unlink(); launcher.side_effect=OSError('failed')
                with self.assertRaises(ValidationError):facade.launch_xemu(lambda *args:None)
                self.assertFalse(config.exists())


class PlayCheckTests(unittest.TestCase):
    """The pre-play warning for a 128 MB build: reads xemu.toml and the BIOS file, never writes either."""

    HASH = "ab" * 32

    def _config(self, root: Path, *, memory="'128'", bios=None) -> Path:
        text = "[sys]\n"
        if memory is not None:
            text += f"mem_limit = {memory}\n"
        if bios is not None:
            text += "\n[sys.files]\nflashrom_path = " + json.dumps(str(bios)) + "\n"
        path = root / "xemu.toml"
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def _bios(self, root: Path) -> Path:
        bios = root / "Complex 4627.bin"
        bios.write_bytes(b"\0" * 1_048_576)
        return bios

    def test_the_project_bios_pin_is_the_one_megabyte_complex_4627_hash(self):
        self.assertEqual(x.KNOWN_4627_FLASHROM,
                         ((1_048_576, "34f1c8ded59116436065783f8ad2ef0939df3cbfc76277ec9e5c41bf9ccb93cd"),))

    def test_matching_settings_produce_no_warning_and_leave_the_file_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config = self._config(root, bios=self._bios(root))
            before = config.read_bytes()
            with patch.object(x, "KNOWN_4627_FLASHROM", ((1_048_576, self.HASH),)):
                self.assertEqual(x.play_warning(config, hash_file=lambda _path: self.HASH), "")
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual(self._config(root, memory="128", bios=root / "Complex 4627.bin").is_file(), True)
            with patch.object(x, "KNOWN_4627_FLASHROM", ((1_048_576, self.HASH),)):
                self.assertEqual(x.play_warning(root / "xemu.toml", hash_file=lambda _path: self.HASH), "")

    def test_sixty_four_megabytes_is_named_with_the_exact_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.object(x, "KNOWN_4627_FLASHROM", ((1_048_576, self.HASH),)):
                warning = x.play_warning(self._config(root, memory="'64'", bios=self._bios(root)),
                                         hash_file=lambda _path: self.HASH)
            self.assertIn("System Memory", warning)
            self.assertIn("mem_limit = '128'", warning)

    def test_a_missing_memory_value_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.object(x, "KNOWN_4627_FLASHROM", ((1_048_576, self.HASH),)):
                warning = x.play_warning(self._config(root, memory=None, bios=self._bios(root)),
                                         hash_file=lambda _path: self.HASH)
            self.assertIn("System Memory is not set", warning)

    def test_another_bios_image_is_not_confirmed_as_4627_rather_than_called_wrong(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.object(x, "KNOWN_4627_FLASHROM", ((1_048_576, self.HASH),)):
                warning = x.play_warning(self._config(root, bios=self._bios(root)),
                                         hash_file=lambda _path: "00" * 32)
            self.assertIn("could not be confirmed as a 4627 BIOS", warning)
            self.assertIn("you can ignore this note", warning)
            self.assertNotIn("not the tested", warning)
            self.assertIn("Flash ROM (BIOS)", warning)

    def test_a_missing_or_unset_bios_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            missing = root / "gone.bin"
            with patch.object(x, "KNOWN_4627_FLASHROM", ((1_048_576, self.HASH),)):
                self.assertIn("was not found", x.play_warning(self._config(root, bios=missing)))
                self.assertIn("is not set", x.play_warning(self._config(root, bios=None)))

    def test_missing_or_unreadable_settings_ask_for_the_two_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            warning = x.play_warning(root / "never-written.toml")
            self.assertIn("were not found", warning)
            self.assertIn("128 MiB", warning)
            self.assertIn("Complex 4627", warning)
            broken = root / "broken.toml"
            broken.write_text("[broken", encoding="utf-8", newline="\n")
            self.assertIn("could not be read", x.play_warning(broken))

    def test_launch_emits_the_warning_before_starting_xemu(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            disc = root / "modded.xiso.iso"
            disc.write_bytes(b"synthetic")
            config = self._config(root, memory="'64'")
            launched = []
            facade = Nfl2k5StudioFacade(uniform_catalog=SimpleNamespace(), xemu_command=("xemu",),
                                        process_launcher=lambda argv, **kwargs: launched.append(tuple(argv)))
            facade._last_build = ExternalBuild(disc)
            events = []
            with patch.object(x, "config_path", return_value=config), \
                    patch("mod_editor.studio.facade._validate_xemu_executable"):
                result = facade.launch_xemu(lambda message, *_args: events.append(message))
            self.assertTrue(launched)
            self.assertTrue(any("System Memory" in message for message in events))
            self.assertIn("System Memory", result.message)


if __name__ == '__main__':unittest.main()
