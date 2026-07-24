"""Real-behaviour tests for the cross-platform durability primitives.

The shipped editor flushed archives to disk through descriptors it had opened
read-only -- ``open(path, "rb")`` then ``os.fsync(handle.fileno())``, and
``os.open(directory, O_RDONLY | O_DIRECTORY)`` then ``os.fsync``.  POSIX permits
both.  Windows implements ``os.fsync`` as ``FlushFileBuffers``, which the kernel
honours only on a handle carrying ``GENERIC_WRITE``, so every one of those calls
raised ``OSError(EBADF)`` on the Windows CI runner; and Windows cannot open a
directory through the CRT at all.

Windows cannot be run here, so it is *simulated in-process*: ``os.fsync`` is
replaced with one that refuses any descriptor whose ``/proc`` access mode is
``O_RDONLY`` (exactly the Windows rule), ``os.open`` is made to refuse
directories, the Windows-absent ``os`` attributes (``O_DIRECTORY``,
``O_NOFOLLOW``, ``getuid``, ``fchmod``) are deleted, :mod:`fcntl` is hidden, and
``platform_compat.IS_WINDOWS`` is set.  Each test then asserts twice: that the
*old* idiom fails under that simulation, and that the new helper succeeds --
which is what proves the fix takes the Windows branch rather than passing by
accident.

Every POSIX assertion runs unsimulated on the real host, so the Linux and macOS
paths are covered for real and are shown to be unchanged.
"""

from __future__ import annotations

import contextlib
import errno
import importlib.abc
import os
from pathlib import Path
import sys
import tempfile
from typing import Iterator
import unittest

from mod_editor.core import platform_compat
from mod_editor.core.platform_compat import (
    IS_WINDOWS,
    DurabilityError,
    _flush_open_flags,
    fsync_directory,
    fsync_directory_fd,
    fsync_fd,
    fsync_path,
    supports_directory_fsync,
)


_ACCESS_MODE_MASK = getattr(os, "O_ACCMODE", 0o3)

# Windows has no ``O_DIRECTORY``/``O_NOFOLLOW`` and no ``os.getuid``; deleting
# them makes every ``getattr(os, ..., 0)`` in the shipped code take the same
# branch it takes there.  ``O_BINARY`` is the mirror image: absent on POSIX,
# present on Windows, so the simulation adds it.
_WINDOWS_ABSENT_OS_NAMES = ("O_DIRECTORY", "O_NOFOLLOW", "fchmod", "getuid")


class _FcntlBlocker(importlib.abc.MetaPathFinder):
    """A meta-path finder that makes ``import fcntl`` fail, as on Windows."""

    def find_spec(self, name, path, target=None):  # noqa: ANN001, D102
        if name == "fcntl" or name.startswith("fcntl."):
            raise ImportError("fcntl is hidden to simulate Windows")
        return None


def _descriptor_is_read_only(fd: int) -> bool:
    """Whether ``fd`` was opened ``O_RDONLY``, read from the kernel itself.

    Asking ``/proc`` rather than remembering what the test opened means the
    simulation judges *any* descriptor the shipped code produces, including ones
    created deep inside :mod:`zipfile` or :mod:`pathlib`.
    """

    with open(f"/proc/self/fdinfo/{fd}", "r", encoding="ascii") as info:
        for line in info:
            if line.startswith("flags:"):
                flags = int(line.split()[1], 8)
                return flags & _ACCESS_MODE_MASK == os.O_RDONLY
    raise RuntimeError(f"could not read the access mode of descriptor {fd}")


@contextlib.contextmanager
def simulated_windows() -> Iterator[None]:
    """Make this process behave like Windows for the duration of the block."""

    real_fsync = os.fsync
    real_open = os.open
    saved_attributes = {
        name: getattr(os, name) for name in _WINDOWS_ABSENT_OS_NAMES
        if hasattr(os, name)
    }
    saved_binary = getattr(os, "O_BINARY", None)
    saved_windows_flag = platform_compat.IS_WINDOWS
    saved_fcntl = sys.modules.pop("fcntl", None)
    blocker = _FcntlBlocker()

    def windows_fsync(fd: int) -> None:
        """``FlushFileBuffers`` needs ``GENERIC_WRITE``; EBADF otherwise."""

        if _descriptor_is_read_only(fd):
            raise OSError(errno.EBADF, "Bad file descriptor")
        real_fsync(fd)

    def windows_open(path, flags, *args, **kwargs):  # noqa: ANN001, ANN202
        """The CRT cannot open a directory at all on Windows."""

        if os.path.isdir(path):
            raise PermissionError(errno.EACCES, "Permission denied", os.fspath(path))
        return real_open(path, flags, *args, **kwargs)

    sys.meta_path.insert(0, blocker)
    os.fsync = windows_fsync  # type: ignore[assignment]
    os.open = windows_open  # type: ignore[assignment]
    for name in saved_attributes:
        delattr(os, name)
    os.O_BINARY = 0  # type: ignore[attr-defined]
    platform_compat.IS_WINDOWS = True
    try:
        yield
    finally:
        platform_compat.IS_WINDOWS = saved_windows_flag
        if saved_binary is None:
            del os.O_BINARY  # type: ignore[attr-defined]
        else:
            os.O_BINARY = saved_binary  # type: ignore[attr-defined]
        for name, value in saved_attributes.items():
            setattr(os, name, value)
        os.open = real_open  # type: ignore[assignment]
        os.fsync = real_fsync  # type: ignore[assignment]
        with contextlib.suppress(ValueError):
            sys.meta_path.remove(blocker)
        if saved_fcntl is not None:
            sys.modules["fcntl"] = saved_fcntl


class SimulationFidelityTests(unittest.TestCase):
    """The simulation must reproduce the real CI failure before it proves a fix."""

    def test_simulation_reproduces_the_reported_bad_file_descriptor(self) -> None:
        # This is the shipped idiom that produced 14 x "OSError: [Errno 9] Bad
        # file descriptor" on the windows-latest runner.
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "archive.zip"
            path.write_bytes(b"staged bytes")
            with simulated_windows():
                with path.open("rb") as handle:
                    with self.assertRaises(OSError) as caught:
                        os.fsync(handle.fileno())
            self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_simulation_leaves_writable_descriptors_flushable(self) -> None:
        # Windows flushes a writable handle happily; if the simulation refused
        # those too it would prove nothing about the read-only case.
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "writable.bin"
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(descriptor, b"payload")
                with simulated_windows():
                    os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def test_simulation_restores_the_process_afterwards(self) -> None:
        with simulated_windows():
            self.assertTrue(platform_compat.IS_WINDOWS)
            self.assertFalse(hasattr(os, "getuid"))
        self.assertEqual(platform_compat.IS_WINDOWS, IS_WINDOWS)
        self.assertEqual(hasattr(os, "getuid"), os.name == "posix")


class FlushOpenFlagTests(unittest.TestCase):
    def test_posix_keeps_the_read_only_access_mode(self) -> None:
        flags = _flush_open_flags(follow_symlinks=True)
        self.assertEqual(flags & _ACCESS_MODE_MASK, os.O_RDONLY)

    def test_posix_adds_nofollow_only_when_asked(self) -> None:
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        self.assertTrue(nofollow, "this POSIX host should provide O_NOFOLLOW")
        self.assertFalse(_flush_open_flags(follow_symlinks=True) & nofollow)
        self.assertTrue(_flush_open_flags(follow_symlinks=False) & nofollow)

    def test_windows_upgrades_only_the_access_mode(self) -> None:
        # Read-write is the minimum access FlushFileBuffers accepts.  It is the
        # only thing that changes: no create, no truncate, no append.
        with simulated_windows():
            flags = _flush_open_flags(follow_symlinks=False)
        self.assertEqual(flags & _ACCESS_MODE_MASK, os.O_RDWR)
        for forbidden in (os.O_CREAT, os.O_TRUNC, os.O_APPEND, os.O_EXCL):
            self.assertFalse(flags & forbidden)


class FsyncPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.archive = self.root / "bundle.zip"
        self.archive.write_bytes(b"a staged archive" * 64)
        os.chmod(self.archive, 0o600)

    def test_posix_opens_read_only_exactly_as_before(self) -> None:
        observed: list[int] = []
        real_open = os.open

        def recording_open(path, flags, *args, **kwargs):  # noqa: ANN001, ANN202
            fd = real_open(path, flags, *args, **kwargs)
            observed.append(flags)
            return fd

        os.open = recording_open  # type: ignore[assignment]
        try:
            fsync_path(self.archive)
        finally:
            os.open = real_open  # type: ignore[assignment]
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0] & _ACCESS_MODE_MASK, os.O_RDONLY)

    def test_posix_refuses_a_symlink_when_asked(self) -> None:
        link = self.root / "link.zip"
        link.symlink_to(self.archive)
        with self.assertRaises(OSError) as caught:
            fsync_path(link, follow_symlinks=False)
        self.assertEqual(caught.exception.errno, errno.ELOOP)
        # ... and still flushes it when following is permitted, unchanged.
        fsync_path(link)

    def test_posix_propagates_a_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            fsync_path(self.root / "absent.zip")

    def test_windows_flushes_where_the_old_idiom_raised_ebadf(self) -> None:
        with simulated_windows():
            # The idiom this replaced, under the same simulation, fails.
            with self.archive.open("rb") as handle:
                with self.assertRaises(OSError) as caught:
                    os.fsync(handle.fileno())
            self.assertEqual(caught.exception.errno, errno.EBADF)
            # The helper takes the Windows branch and succeeds.
            fsync_path(self.archive)
            fsync_path(self.archive, follow_symlinks=False)
        # The flush must not have altered a single byte or the mode.
        self.assertEqual(self.archive.read_bytes(), b"a staged archive" * 64)
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)

    def test_windows_refuses_read_only_files_loudly(self) -> None:
        # A read-only file genuinely cannot be flushed on Windows, and clearing
        # the attribute behind the caller's back would un-harden a file it
        # deliberately sealed.  Fail closed and say exactly why.
        sealed = self.root / "sealed.zip"
        sealed.write_bytes(b"sealed")
        os.chmod(sealed, 0o400)
        self.addCleanup(os.chmod, sealed, 0o600)
        real_open = os.open

        def read_only_attribute_open(path, flags, *args, **kwargs):  # noqa: ANN001, ANN202
            if os.fspath(path) == os.fspath(sealed) and flags & _ACCESS_MODE_MASK:
                raise PermissionError(errno.EACCES, "Permission denied")
            return real_open(path, flags, *args, **kwargs)

        with simulated_windows():
            os.open = read_only_attribute_open  # type: ignore[assignment]
            try:
                with self.assertRaises(DurabilityError) as caught:
                    fsync_path(sealed)
            finally:
                os.open = real_open  # type: ignore[assignment]
        self.assertIn("read-only", str(caught.exception))

    def test_posix_does_not_convert_permission_errors(self) -> None:
        # The Windows-only translation above must never fire on POSIX; a
        # permission problem here stays a PermissionError, as it always was.
        real_open = os.open

        def refusing_open(path, flags, *args, **kwargs):  # noqa: ANN001, ANN202
            raise PermissionError(errno.EACCES, "Permission denied")

        os.open = refusing_open  # type: ignore[assignment]
        try:
            with self.assertRaises(PermissionError):
                fsync_path(self.archive)
        finally:
            os.open = real_open  # type: ignore[assignment]


class FsyncFdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.staged = self.root / "modded.xiso"
        self.staged.write_bytes(b"verified image")

    @contextlib.contextmanager
    def _read_only_descriptor(self) -> Iterator[int]:
        descriptor = os.open(self.staged, os.O_RDONLY)
        try:
            yield descriptor
        finally:
            os.close(descriptor)

    def test_posix_issues_exactly_one_fsync_on_the_given_descriptor(self) -> None:
        seen: list[int] = []
        real_fsync = os.fsync

        def recording_fsync(fd: int) -> None:
            seen.append(fd)
            real_fsync(fd)

        os.fsync = recording_fsync  # type: ignore[assignment]
        try:
            with self._read_only_descriptor() as descriptor:
                fsync_fd(descriptor, path=self.staged)
                self.assertEqual(seen, [descriptor])
        finally:
            os.fsync = real_fsync  # type: ignore[assignment]

    def test_posix_never_swallows_a_genuinely_bad_descriptor(self) -> None:
        # EBADF is tolerated only on the platform that cannot flush a read-only
        # handle.  Here it still means "this descriptor is closed" and must
        # surface, path or no path.
        descriptor = os.open(self.staged, os.O_RDONLY)
        os.close(descriptor)
        with self.assertRaises(OSError) as caught:
            fsync_fd(descriptor, path=self.staged)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_windows_reopens_the_same_inode_and_flushes_it(self) -> None:
        with self._read_only_descriptor() as descriptor:
            with simulated_windows():
                # Bare os.fsync is what the shipped build service called.
                with self.assertRaises(OSError) as caught:
                    os.fsync(descriptor)
                self.assertEqual(caught.exception.errno, errno.EBADF)
                fsync_fd(descriptor, path=self.staged)
        self.assertEqual(self.staged.read_bytes(), b"verified image")

    def test_windows_still_refuses_a_swapped_file(self) -> None:
        # The build service holds this descriptor open precisely to pin the
        # inode it verified.  Reopening by name must not quietly flush whatever
        # now answers to that name.
        with self._read_only_descriptor() as descriptor:
            self.staged.unlink()
            self.staged.write_bytes(b"an impostor")
            with simulated_windows():
                with self.assertRaises(DurabilityError) as caught:
                    fsync_fd(descriptor, path=self.staged)
        self.assertIn("no longer names", str(caught.exception))

    def test_windows_without_a_path_fails_closed(self) -> None:
        with self._read_only_descriptor() as descriptor:
            with simulated_windows():
                with self.assertRaises(DurabilityError):
                    fsync_fd(descriptor)

    def test_windows_flushes_a_writable_descriptor_directly(self) -> None:
        seen: list[int] = []
        descriptor = os.open(self.root / "writable.bin", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, b"payload")
            with simulated_windows():
                real_open = os.open

                def counting_open(path, flags, *args, **kwargs):  # noqa: ANN001, ANN202
                    seen.append(flags)
                    return real_open(path, flags, *args, **kwargs)

                os.open = counting_open  # type: ignore[assignment]
                try:
                    fsync_fd(descriptor, path=self.root / "writable.bin")
                finally:
                    os.open = real_open  # type: ignore[assignment]
        finally:
            os.close(descriptor)
        self.assertEqual(seen, [], "a writable handle needs no reopen anywhere")


class FsyncDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)

    def test_posix_really_flushes_and_reports_that_it_did(self) -> None:
        (self.root / "published.bin").write_bytes(b"x")
        seen: list[int] = []
        real_fsync = os.fsync

        def recording_fsync(fd: int) -> None:
            seen.append(fd)
            real_fsync(fd)

        os.fsync = recording_fsync  # type: ignore[assignment]
        try:
            self.assertTrue(fsync_directory(self.root))
        finally:
            os.fsync = real_fsync  # type: ignore[assignment]
        self.assertEqual(len(seen), 1)

    def test_posix_advertises_the_capability(self) -> None:
        self.assertTrue(supports_directory_fsync())

    def test_windows_reports_the_gap_instead_of_pretending(self) -> None:
        # Windows exposes no directory-flush primitive at any level the CRT
        # reaches: os.open on a directory fails outright.  Reporting False is
        # what makes the missing guarantee visible instead of silent.
        with simulated_windows():
            self.assertFalse(supports_directory_fsync())
            with self.assertRaises(PermissionError):
                os.open(self.root, os.O_RDONLY)
            self.assertFalse(fsync_directory(self.root))

    def test_windows_never_touches_the_filesystem(self) -> None:
        real_open = os.open
        attempts: list[object] = []

        with simulated_windows():
            def recording_open(path, flags, *args, **kwargs):  # noqa: ANN001, ANN202
                attempts.append(path)
                return real_open(path, flags, *args, **kwargs)

            os.open = recording_open  # type: ignore[assignment]
            try:
                self.assertFalse(fsync_directory(self.root))
            finally:
                os.open = real_open  # type: ignore[assignment]
        self.assertEqual(attempts, [])


class FsyncDirectoryFdTests(unittest.TestCase):
    """The audio-source stores pin one directory fd for a whole transaction."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.descriptor = os.open(
            self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        self.addCleanup(os.close, self.descriptor)

    def test_posix_flushes_the_caller_s_own_descriptor(self) -> None:
        # Re-opening by name would discard the pin those transactions rely on,
        # so the helper must flush this exact descriptor and say it did.
        seen: list[int] = []
        real_fsync = os.fsync

        def recording_fsync(fd: int) -> None:
            seen.append(fd)
            real_fsync(fd)

        os.fsync = recording_fsync  # type: ignore[assignment]
        try:
            self.assertTrue(fsync_directory_fd(self.descriptor))
        finally:
            os.fsync = real_fsync  # type: ignore[assignment]
        self.assertEqual(seen, [self.descriptor])

    def test_posix_propagates_a_real_flush_failure(self) -> None:
        closed = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        os.close(closed)
        with self.assertRaises(OSError) as caught:
            fsync_directory_fd(closed)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_windows_reports_the_gap_without_touching_the_descriptor(self) -> None:
        # Under Windows semantics a bare os.fsync on this read-only directory
        # descriptor is the EBADF the CI log reported; the helper must not make
        # that call at all, and must report that nothing was committed.
        with simulated_windows():
            with self.assertRaises(OSError) as caught:
                os.fsync(self.descriptor)
            self.assertEqual(caught.exception.errno, errno.EBADF)
            self.assertFalse(fsync_directory_fd(self.descriptor))


if __name__ == "__main__":
    unittest.main()
