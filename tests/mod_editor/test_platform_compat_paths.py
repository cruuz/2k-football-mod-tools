"""Standalone, retail-free regressions for the beta-60 Windows path hotfix."""

from __future__ import annotations

import errno
import os
from pathlib import Path, PureWindowsPath
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import persistence, platform_compat
from mod_editor.core.errors import ValidationError
from mod_editor.core.model import GameId, ModProject
from mod_editor.studio import session


REPLACEMENT_NAME = f".team-kit-{'a' * 32}-{'b' * 64}.png"
REPORTED_PARENT = PureWindowsPath(
    r"C:\Users\glenwood.edwards\.local\share\2k5-mod-studio\sessions"
    r"\9c8d849e-762d-475f-ae3f-b67adee4b6ab\replacements"
)
PAYLOAD = b"\x00\r\n\n\r\x1a\xff" * 64  # Detect Windows CRT text translation.


class TemporarySiblingTests(unittest.TestCase):
    def test_short_unique_siblings_and_image_suffix(self) -> None:
        target = Path("sessions") / "replacements" / REPLACEMENT_NAME
        siblings = [platform_compat.temporary_sibling(target) for _ in range(1000)]
        self.assertEqual(len(set(siblings)), len(siblings))
        for sibling in siblings:
            self.assertEqual(sibling.parent, target.parent)
            self.assertNotEqual(sibling, target)
            self.assertRegex(sibling.name, r"^\.[0-9a-f]{12}\.tmp$")
            self.assertLessEqual(len(sibling.name), 20)
        preview = platform_compat.temporary_sibling(target, suffix=".png")
        self.assertEqual(preview.suffix, ".png")
        self.assertEqual(len(preview.name), 17)

    def test_never_returns_the_target_name(self) -> None:
        target = Path("sessions") / ".aaaaaaaaaaaa.tmp"
        with mock.patch.object(platform_compat, "uuid4", side_effect=[
            SimpleNamespace(hex="a" * 32), SimpleNamespace(hex="b" * 32),
        ]):
            self.assertEqual(
                platform_compat.temporary_sibling(target),
                target.with_name(".bbbbbbbbbbbb.tmp"),
            )

    def test_120_character_root_and_longest_team_kit_replacement(self) -> None:
        # Include the session UUID and replacements directory below this root.
        root = Path("r" * 120) / ("s" * 36) / "replacements"
        target = root / REPLACEMENT_NAME
        self.assertGreaterEqual(len(str(target)), 260)
        self.assertLess(len(str(platform_compat.temporary_sibling(target))), 260)
        # Also exercise Windows separator semantics on Linux and macOS.
        windows_root = PureWindowsPath("C:/" + "r" * 117)
        self.assertEqual(len(str(windows_root)), 120)
        target = windows_root / ("s" * 36) / "replacements" / REPLACEMENT_NAME
        self.assertLess(len(str(platform_compat.temporary_sibling(target))), 260)

    def test_reported_path_arithmetic(self) -> None:
        target = REPORTED_PARENT / REPLACEMENT_NAME
        old = target.with_name(f".{target.name}.10032.{'c' * 32}.tmp")
        self.assertEqual(len(target.name), 111)
        self.assertEqual(len(str(target)), 224)
        self.assertEqual(len(str(old)), 268)
        self.assertEqual(len(str(platform_compat.temporary_sibling(target))), 130)


class LongPathTests(unittest.TestCase):
    def test_windows_absolute_unc_device_and_relative_paths(self) -> None:
        cases = [
            (r"C:\sessions\file.png", r"\\?\C:\sessions\file.png"),
            ("C:/sessions/../replacements/./file.png", r"\\?\C:\replacements\file.png"),
            (r"\\server\share\folder\file.png", r"\\?\UNC\server\share\folder\file.png"),
            ("//server/share/folder/file.png", r"\\?\UNC\server\share\folder\file.png"),
            (r"\\server\share", "\\\\?\\UNC\\server\\share"),
            (r"\\?\C:\sessions\file.png", r"\\?\C:\sessions\file.png"),
            (r"\\?\UNC\server\share\file.png", r"\\?\UNC\server\share\file.png"),
            (r"\\.\C:\file.png", r"\\.\C:\file.png"),
            ("//?/C:/file.png", "//?/C:/file.png"),
            (r"sessions\file.png", r"sessions\file.png"),
            ("./sessions/file.png", "./sessions/file.png"),
            (r"C:sessions\file.png", r"C:sessions\file.png"),
            (r"\sessions\file.png", r"\sessions\file.png"),
            ("/sessions/file.png", "/sessions/file.png"),
            ("", ""),
        ]
        with mock.patch.object(platform_compat, "IS_WINDOWS", True):
            for supplied, expected in cases:
                with self.subTest(path=supplied):
                    self.assertEqual(platform_compat.long_path(supplied), expected)
                    self.assertEqual(platform_compat.long_path(expected), expected)
            self.assertEqual(
                platform_compat.long_path(PureWindowsPath(r"C:\file.png")),
                r"\\?\C:\file.png",
            )

    def test_posix_paths_are_verbatim(self) -> None:
        with mock.patch.object(platform_compat, "IS_WINDOWS", False):
            for path in ["/tmp/a/../b", "relative/name", r"C:\file.png", r"\\server\share"]:
                self.assertEqual(platform_compat.long_path(path), path)
            self.assertEqual(platform_compat.long_path(Path("relative")), "relative")


class AtomicPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp()).resolve()
        # Use extended syntax for cleanup too, even on Windows without opt-in.
        self.addCleanup(shutil.rmtree, platform_compat.long_path(self.root))

    def _roundtrip(self, root: Path) -> None:
        destination = root / REPLACEMENT_NAME
        self.assertEqual(session._write_new_atomic(destination, PAYLOAD), destination)
        io_path = Path(platform_compat.long_path(destination))
        self.assertEqual(io_path.read_bytes(), PAYLOAD)
        with self.assertRaisesRegex(ValidationError, "already exists"):
            session._write_new_atomic(destination, b"must not overwrite")
        self.assertEqual(io_path.read_bytes(), PAYLOAD)
        session._replace_atomic(destination, PAYLOAD[::-1])
        self.assertEqual(io_path.read_bytes(), PAYLOAD[::-1])
        self.assertEqual([p.name for p in io_path.parent.iterdir()], [destination.name])

    def test_session_roundtrip_on_synthetic_long_root(self) -> None:
        root = self.root / ("r" * max(1, 120 - len(str(self.root)) - 1))
        self._roundtrip(root)

    def test_ten_digit_batch_under_simulated_max_path(self) -> None:
        original = self.root / "original.png"
        original.write_bytes(b"original pixels")
        supplied = self.root / "digit.png"
        supplied.write_bytes(PAYLOAD)
        assets = {
            f"digit-{digit}": SimpleNamespace(asset_id=f"digit-{digit}", label=f"Digit {digit}")
            for digit in range(10)
        }
        asset_io = SimpleNamespace(
            ensure_original=lambda asset: original,
            validate_replacement=lambda asset, path: (path.read_bytes(), path.read_bytes()),
        )
        cache = SimpleNamespace(
            source=SimpleNamespace(sha256="a" * 64), root=self.root,
            pack0=self.root / "pack0", inventory=self.root / "inventory.json",
        )
        # The replacements parent is at least as long as the reported 112 chars.
        root = self.root / ("s" * max(1, 62 - len(str(self.root)) - 1))
        with mock.patch.object(session, "Nfl2k5ProductVisualIO", return_value=asset_io):
            store = session.StudioSession(
                cache, SimpleNamespace(get_asset=assets.__getitem__),
                root=root, session_id="s" * 36,
            )
        old_temp = store.replacements / f".{REPLACEMENT_NAME}.10032.{'c' * 32}.tmp"
        self.assertGreaterEqual(len(str(old_temp)), 260)
        real_open = os.open
        opened = []

        def bounded_open(path, flags, *args, **kwargs):
            name = os.fspath(path)
            if len(name) >= 260 and not name.startswith("\\\\?\\"):
                raise FileNotFoundError(errno.ENOENT, "simulated MAX_PATH", name)
            opened.append(Path(path))
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(session.os, "open", side_effect=bounded_open):
            result = store.replace_batch(
                ((asset, supplied) for asset in assets.values()), label="Import digits 0-9"
            )
        self.assertEqual(len(result.changed_asset_ids), 10)
        self.assertEqual(store.modified_count, 10)
        for path in store.replacements.iterdir():
            self.assertEqual(path.read_bytes(), PAYLOAD)
        self.assertTrue(opened)
        self.assertTrue(all(len(path.name) == 17 for path in opened))
        self.assertEqual(store.undo(), "Import digits 0-9")
        self.assertEqual(store.modified_count, 0)
        self.assertEqual(list(store.replacements.iterdir()), [])
        self.assertEqual(original.read_bytes(), b"original pixels")

    @unittest.skipUnless(platform_compat.IS_WINDOWS, "MAX_PATH is a Windows limit")
    def test_session_roundtrip_with_parent_and_final_over_260(self) -> None:
        root = self.root
        while len(str(root)) <= 280:
            root /= "r" * 60
        self.assertGreater(len(str(root)), 260)
        self._roundtrip(root)

    def test_failed_fsync_or_replace_preserves_destination_and_cleans_stage(self) -> None:
        destination = self.root / REPLACEMENT_NAME
        destination.write_bytes(PAYLOAD)
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                with mock.patch.object(session.os, operation, side_effect=OSError("write failed")):
                    with self.assertRaisesRegex(OSError, "write failed"):
                        session._replace_atomic(destination, b"new payload")
                self.assertEqual(destination.read_bytes(), PAYLOAD)
                self.assertEqual(list(self.root.iterdir()), [destination])

    def test_persistence_roundtrip(self) -> None:
        self._project_roundtrip(self.root / "project.json")

    def _project_roundtrip(self, destination: Path) -> None:
        project = ModProject(name="Path regression", game=GameId.NFL2K5)
        self.assertEqual(persistence.save_project(project, destination), destination)
        loaded = persistence.load_project(destination)
        self.assertEqual(loaded.project_id, project.project_id)
        self.assertEqual(loaded.name, project.name)
        self.assertFalse(project.dirty)
        parent = Path(platform_compat.long_path(destination.parent))
        self.assertEqual([p.name for p in parent.iterdir()], [destination.name])

    @unittest.skipUnless(platform_compat.IS_WINDOWS, "MAX_PATH is a Windows limit")
    def test_persistence_roundtrip_over_260(self) -> None:
        root = self.root
        while len(str(root)) <= 280:
            root /= "p" * 60
        self._project_roundtrip(root / "project.json")

    def test_windows_write_failure_has_length_and_recovery_instructions(self) -> None:
        target = self.root / ("a" * 100) / ("b" * 100) / REPLACEMENT_NAME
        for writer in (session._write_new_atomic, session._replace_atomic):
            with self.subTest(writer=writer.__name__):
                failure = FileNotFoundError(errno.ENOENT, "No such file or directory")
                with mock.patch.object(platform_compat, "IS_WINDOWS", True):
                    with mock.patch.object(session.os, "open", side_effect=failure):
                        with self.assertRaises(ValidationError) as caught:
                            writer(target, PAYLOAD)
                message = str(caught.exception)
                self.assertIn(f"this one is {len(str(target))}.", message)
                self.assertIn("Windows limits file paths to 260 characters", message)
                self.assertIn(r"HKLM\SYSTEM\CurrentControlSet\Control\FileSystem", message)
                self.assertIn("LongPathsEnabled=1, then restart", message)
                self.assertIn("move your sessions folder", message)
                self.assertIs(caught.exception.__cause__, failure)

    def test_error_counts_unprefixed_os_paths_at_260_boundary(self) -> None:
        for length in (259, 260, 268):
            filename = "C:\\" + "a" * (length - 3)
            failure = FileNotFoundError(errno.ENOENT, "missing", "\\\\?\\" + filename)
            with self.subTest(length=length):
                with mock.patch.object(platform_compat, "IS_WINDOWS", True):
                    expected = ValidationError if length >= 260 else FileNotFoundError
                    with self.assertRaises(expected) as caught:
                        with session._explain_write_failure(Path("short.png")):
                            raise failure
                if length >= 260:
                    self.assertIn(f"this one is {length}.", str(caught.exception))
                else:
                    self.assertIs(caught.exception, failure)

    def test_posix_long_path_failure_is_unchanged(self) -> None:
        failure = FileNotFoundError(errno.ENOENT, "missing")
        with mock.patch.object(platform_compat, "IS_WINDOWS", False):
            with self.assertRaises(FileNotFoundError) as caught:
                with session._explain_write_failure(Path("a" * 270)):
                    raise failure
        self.assertIs(caught.exception, failure)


if __name__ == "__main__":
    unittest.main()
