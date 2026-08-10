"""One-click emulator launch says what is actually missing, and can be fixed.

Both editors used to gray the Launch button out and explain it with one
sentence covering two unrelated causes -- no build yet, and no emulator -- so a
modder could not tell which one was theirs. 2K5 went further: its tooltip told
people to "configure xemu" when the app had no way to configure anything, and
it decided once at startup whether xemu existed, so installing it afterwards
did nothing until the editor was restarted. APF relabelled its *disabled*
button "Configure Xenia to Launch", which is an instruction on a dead control.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.studio import facade as studio_facade  # noqa: E402


class _Build:
    def __init__(self, xiso: Path) -> None:
        self.output_xiso = xiso


class XemuLaunchArgumentTests(unittest.TestCase):
    def test_a_direct_xemu_gets_the_plain_dvd_path(self) -> None:
        argv = studio_facade._xemu_launch_argv(
            ("/usr/bin/xemu",), Path("/games/modded.iso")
        )
        self.assertEqual(
            argv, ("/usr/bin/xemu", "-dvd_path", "/games/modded.iso")
        )

    def test_a_flatpak_xemu_is_given_read_access_to_the_iso_directory(self) -> None:
        """Without this the sandbox refuses the file and it reads as a bad build."""

        argv = studio_facade._xemu_launch_argv(
            ("/usr/bin/flatpak", "run", "app.xemu.xemu"),
            Path("/media/drive/builds/modded.iso"),
        )
        self.assertEqual(
            argv,
            (
                "/usr/bin/flatpak",
                "run",
                "--filesystem=/media/drive/builds:ro",
                "app.xemu.xemu",
                "-dvd_path",
                "/media/drive/builds/modded.iso",
            ),
        )
        # Read-only: launching a build never gives the emulator write access.
        self.assertIn(":ro", argv[2])

    def test_a_flatpak_style_command_that_is_not_flatpak_is_left_alone(self) -> None:
        argv = studio_facade._xemu_launch_argv(
            ("/opt/xemu/run", "run", "something"), Path("/games/modded.iso")
        )
        self.assertEqual(argv[:3], ("/opt/xemu/run", "run", "something"))
        self.assertNotIn("--filesystem=/games:ro", argv)


class XemuSettingsTests(unittest.TestCase):
    def test_a_chosen_executable_survives_into_the_next_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "settings.json"
            executable = root / "xemu"
            executable.write_text("#!/bin/sh\n")
            executable.chmod(0o755)
            studio_facade._store_xemu_command(executable, settings)
            self.assertEqual(
                studio_facade._stored_xemu_command(settings), (str(executable),)
            )
            document = json.loads(settings.read_text())
            self.assertEqual(
                document["schema"], studio_facade.XEMU_SETTINGS_SCHEMA
            )

    def test_a_stored_path_that_no_longer_runs_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "settings.json"
            executable = root / "xemu"
            executable.write_text("#!/bin/sh\n")
            executable.chmod(0o755)
            studio_facade._store_xemu_command(executable, settings)
            executable.unlink()
            self.assertEqual(studio_facade._stored_xemu_command(settings), ())

    def test_unreadable_or_foreign_settings_are_not_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "settings.json"
            self.assertEqual(studio_facade._stored_xemu_command(settings), ())
            settings.write_text("{ not json")
            self.assertEqual(studio_facade._stored_xemu_command(settings), ())
            settings.write_text(json.dumps({"schema": "other", "xemu_path": "/bin/sh"}))
            self.assertEqual(studio_facade._stored_xemu_command(settings), ())


class XemuBlockerTests(unittest.TestCase):
    def _facade(self, command):
        return studio_facade.Nfl2k5StudioFacade(xemu_command=command)

    def test_each_cause_is_named_separately(self) -> None:
        missing = self._facade(())
        self.assertIn("xemu was not found", missing.xemu_blocker)
        self.assertFalse(missing.can_launch_xemu)

        no_build = self._facade(("/usr/bin/xemu",))
        self.assertIn("Build a modded XISO first", no_build.xemu_blocker)
        self.assertFalse(no_build.can_launch_xemu)

    def test_a_build_that_vanished_says_so_rather_than_blaming_xemu(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            xiso = Path(directory) / "modded.iso"
            facade = self._facade(("/usr/bin/xemu",))
            facade._last_build = _Build(xiso)
            self.assertIn("no longer at", facade.xemu_blocker)
            xiso.write_bytes(b"x")
            self.assertEqual(facade.xemu_blocker, "")
            self.assertTrue(facade.can_launch_xemu)

    def test_configure_refuses_a_path_that_cannot_be_run(self) -> None:
        facade = self._facade(("/usr/bin/xemu",))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with self.assertRaises(ValidationError):
                facade.configure_xemu(folder)
            not_executable = folder / "notes.txt"
            not_executable.write_text("hello")
            with self.assertRaises(ValidationError) as caught:
                facade.configure_xemu(not_executable)
            self.assertIn("not executable", str(caught.exception))
            with self.assertRaises(ValidationError):
                facade.configure_xemu(folder / "missing")


class XeniaBlockerTests(unittest.TestCase):
    def test_apf_names_the_build_and_the_emulator_causes_apart(self) -> None:
        from mod_editor.apf_studio.facade import ApfStudioFacade

        class _Settings:
            configured = False

        class _Launcher:
            settings = _Settings()

        facade = ApfStudioFacade.__new__(ApfStudioFacade)
        facade.last_build = None
        facade.launcher = _Launcher()  # type: ignore[assignment]
        self.assertIn("Build a modded game folder first", facade.xenia_blocker)
        self.assertFalse(facade.can_launch_xenia)

        with tempfile.TemporaryDirectory() as directory:
            class _Build:
                output_game = Path(directory)

            facade.last_build = _Build()  # type: ignore[assignment]
            self.assertIn("Xenia Canary is not configured", facade.xenia_blocker)
            _Settings.configured = True
            try:
                self.assertEqual(facade.xenia_blocker, "")
                self.assertTrue(facade.can_launch_xenia)
            finally:
                _Settings.configured = False

    def test_a_missing_build_folder_is_reported_as_such(self) -> None:
        from mod_editor.apf_studio.facade import ApfStudioFacade

        class _Settings:
            configured = True

        class _Launcher:
            settings = _Settings()

        class _Build:
            output_game = Path("/nonexistent/apf-build-folder")

        facade = ApfStudioFacade.__new__(ApfStudioFacade)
        facade.last_build = _Build()  # type: ignore[assignment]
        facade.launcher = _Launcher()  # type: ignore[assignment]
        self.assertIn("no longer at", facade.xenia_blocker)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
