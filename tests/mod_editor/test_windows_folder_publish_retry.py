"""A Windows folder publish survives a scanner holding the staged files open.

Coach Edwards (2026-09-10, a work laptop) imported a number sheet and got::

    [WinError 5] Access is denied:
      'C:\\Users\\...\\Temp\\2k5-digit-sheet-m3p9_x6k\\.team-kit-9374wirw'
      -> 'C:\\Users\\...\\Temp\\2k5-digit-sheet-m3p9_x6k\\team-kit'

The digit-sheet import exports a private Team Kit into its own temp folder
and publishes it with ``platform_compat.publish_no_replace(is_directory=True)``,
which on Windows is one ``os.rename``.  Windows refuses to rename a directory
while any file inside it is open by another process, and right after writing
39 fresh PNGs that is exactly when real-time antivirus and the search indexer
hold one.  The refusal is transient (ERROR_ACCESS_DENIED 5 or
ERROR_SHARING_VIOLATION 32), so the publish now retries for a few seconds and,
if the scanner still will not let go, reserves the destination with an
exclusive ``os.mkdir`` and copies the staged tree into it.

These tests run the Windows branch on every platform by flipping the platform
flag and substituting ``os.rename``; the sleeps are recorded, not slept.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.core import platform_compat  # noqa: E402


def _access_denied() -> PermissionError:
    error = PermissionError(13, "Access is denied")
    error.winerror = 5  # type: ignore[attr-defined]
    return error


def _sharing_violation() -> PermissionError:
    error = PermissionError(13, "The process cannot access the file")
    error.winerror = 32  # type: ignore[attr-defined]
    return error


class _Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.stage = self.root / ".team-kit-stage"
        (self.stage / "nested").mkdir(parents=True)
        (self.stage / "a.png").write_bytes(b"png-a")
        (self.stage / "nested" / "b.png").write_bytes(b"png-b")
        self.destination = self.root / "team-kit"
        self.slept: list[float] = []
        patches = [
            mock.patch.object(platform_compat, "IS_WINDOWS", True),
            # Linux would publish through renameat2 before the platform branch
            # is reached; take that primitive away so the Windows branch runs.
            mock.patch.object(platform_compat, "_linux_renameat2", lambda: None),
            mock.patch.object(platform_compat.time, "sleep", self.slept.append),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def _publish(self, **kwargs):
        return platform_compat.publish_no_replace(
            self.stage, self.destination, is_directory=True, **kwargs
        )

    def assertPublishedTree(self) -> None:
        self.assertEqual((self.destination / "a.png").read_bytes(), b"png-a")
        self.assertEqual((self.destination / "nested" / "b.png").read_bytes(), b"png-b")
        self.assertFalse(self.stage.exists(), "the staging folder is consumed")


class TransientRefusalTests(_Fixture):
    def test_rename_is_retried_until_the_scanner_lets_go(self) -> None:
        real_rename = os.rename
        failures = [_access_denied(), _sharing_violation()]

        def rename(src, dst):
            if failures:
                raise failures.pop(0)
            real_rename(src, dst)

        with mock.patch.object(platform_compat.os, "rename", rename):
            result = self._publish(require_atomic=False)
        self.assertEqual(result.mechanism, platform_compat.PUBLISH_WINDOWS_RENAME)
        self.assertTrue(result.atomic_no_clobber)
        self.assertIn("2 refused attempt", result.detail)
        self.assertEqual(self.slept, list(platform_compat.WINDOWS_DIRECTORY_RENAME_DELAYS[:2]))
        self.assertPublishedTree()

    def test_first_attempt_success_is_unchanged(self) -> None:
        result = self._publish(require_atomic=False)
        self.assertEqual(result.mechanism, platform_compat.PUBLISH_WINDOWS_RENAME)
        self.assertEqual(result.detail, "os.rename (Windows: fails if destination exists)")
        self.assertEqual(self.slept, [])
        self.assertPublishedTree()

    def test_persistent_refusal_falls_back_to_reserve_and_copy(self) -> None:
        with mock.patch.object(platform_compat.os, "rename", side_effect=_access_denied()):
            result = self._publish(require_atomic=False)
        self.assertEqual(result.mechanism, platform_compat.PUBLISH_WINDOWS_COPY_RESERVE)
        self.assertFalse(result.atomic_no_clobber)
        self.assertIn("Access is denied", result.detail)
        self.assertEqual(self.slept, list(platform_compat.WINDOWS_DIRECTORY_RENAME_DELAYS))
        self.assertPublishedTree()

    def test_persistent_refusal_with_atomic_required_raises_and_leaves_no_destination(self) -> None:
        with mock.patch.object(platform_compat.os, "rename", side_effect=_access_denied()):
            with self.assertRaises(PermissionError):
                self._publish(require_atomic=True)
        self.assertFalse(self.destination.exists())
        self.assertTrue((self.stage / "a.png").exists(), "the staging folder is kept for the caller")

    def test_the_fallback_never_overwrites_an_existing_destination(self) -> None:
        self.destination.mkdir()
        (self.destination / "keep.txt").write_bytes(b"theirs")
        exists = FileExistsError(17, "Cannot create a file when that file already exists")
        exists.winerror = 183  # type: ignore[attr-defined]
        with mock.patch.object(platform_compat.os, "rename", side_effect=exists):
            with self.assertRaises(FileExistsError):
                self._publish(require_atomic=False)
        self.assertEqual(self.slept, [], "an existing destination is refused at once, never retried")
        self.assertEqual((self.destination / "keep.txt").read_bytes(), b"theirs")
        self.assertTrue((self.stage / "a.png").exists())

    def test_a_destination_that_appears_during_the_retries_is_still_refused(self) -> None:
        def rename(src, dst):
            raise _access_denied()

        self.destination.mkdir()
        with mock.patch.object(platform_compat.os, "rename", rename):
            with self.assertRaises(FileExistsError):
                self._publish(require_atomic=False)
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()), [])
        self.assertTrue((self.stage / "a.png").exists())

    def test_other_errors_are_not_retried(self) -> None:
        with mock.patch.object(platform_compat.os, "rename", side_effect=OSError(22, "Invalid argument")):
            with self.assertRaises(OSError):
                self._publish(require_atomic=False)
        self.assertEqual(self.slept, [])


class RefusalClassificationTests(unittest.TestCase):
    def test_transient_codes(self) -> None:
        self.assertTrue(platform_compat._transient_windows_rename_refusal(_access_denied()))
        self.assertTrue(platform_compat._transient_windows_rename_refusal(_sharing_violation()))
        plain = PermissionError(13, "Permission denied")
        self.assertTrue(platform_compat._transient_windows_rename_refusal(plain))

    def test_non_transient_codes(self) -> None:
        exists = FileExistsError(17, "exists")
        self.assertFalse(platform_compat._transient_windows_rename_refusal(exists))
        other = OSError(22, "Invalid argument")
        self.assertFalse(platform_compat._transient_windows_rename_refusal(other))
        cross = PermissionError(13, "denied")
        cross.winerror = 17  # type: ignore[attr-defined]  # ERROR_NOT_SAME_DEVICE
        self.assertFalse(platform_compat._transient_windows_rename_refusal(cross))

    def test_delays_are_bounded_and_short(self) -> None:
        total = sum(platform_compat.WINDOWS_DIRECTORY_RENAME_DELAYS)
        self.assertGreater(total, 3.0)
        self.assertLess(total, 10.0)


if __name__ == "__main__":
    unittest.main()
