"""Real-behaviour tests for the cross-platform hardening primitives.

Every test exercises the primitive on the current platform.  Windows-only code
paths (msvcrt locking) cannot run here, but the *portable* fallbacks -- the
seek/read stand-in for ``os.pread``, the chmod stand-in for kernel seals, and
the reflink-unsupported path -- are all reachable on Linux and are tested for
real, including under a ``fcntl``-hidden simulation of a non-POSIX platform.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.abc
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mod_editor.core.platform_compat import (
    IS_LINUX,
    IS_MACOS,
    IS_WINDOWS,
    SealResult,
    _pread_via_seek,
    exclusive_nonblocking_lock,
    fchmod_readonly,
    pread,
    release_lock,
    seal_readonly,
    supports_reflink,
    supports_sealed_memfd,
    try_reflink,
)


class _FcntlBlocker(importlib.abc.MetaPathFinder):
    """A meta-path finder that makes ``import fcntl`` fail, as on Windows."""

    def find_spec(self, name, path, target=None):  # noqa: ANN001, D102
        if name == "fcntl" or name.startswith("fcntl."):
            raise ImportError("fcntl is hidden to simulate a non-POSIX platform")
        return None


@contextlib.contextmanager
def hidden_fcntl():
    """Temporarily make :mod:`fcntl` unimportable in this process."""

    saved = sys.modules.pop("fcntl", None)
    finder = _FcntlBlocker()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass
        if saved is not None:
            sys.modules["fcntl"] = saved


class PlatformConstantTests(unittest.TestCase):
    def test_exactly_one_family_constant_matches_this_interpreter(self) -> None:
        self.assertEqual(IS_WINDOWS, sys.platform.startswith("win"))
        self.assertEqual(IS_MACOS, sys.platform == "darwin")
        self.assertEqual(IS_LINUX, sys.platform.startswith("linux"))

    def test_sealed_memfd_only_advertised_on_linux(self) -> None:
        if supports_sealed_memfd():
            self.assertTrue(IS_LINUX)
        if supports_reflink():
            self.assertTrue(IS_LINUX)


class PreadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "payload.bin"
        self.data = bytes((index * 7) & 0xFF for index in range(5000))
        self.path.write_bytes(self.data)
        self.addCleanup(self._dir.cleanup)

    def test_fallback_matches_os_pread_across_offsets(self) -> None:
        cases = [
            (0, 0),
            (0, 100),
            (10, 0),
            (100, 250),
            (2500, 1000),
            (4990, 100),  # runs past EOF -> short result
            (5000, 10),  # entirely past EOF -> empty
            (0, 5000),  # the whole file
        ]
        fd = os.open(self.path, os.O_RDONLY)
        try:
            for offset, count in cases:
                expected = os.pread(fd, count, offset)
                self.assertEqual(_pread_via_seek(fd, count, offset), expected)
                self.assertEqual(pread(fd, count, offset), expected)
        finally:
            os.close(fd)

    def test_fallback_preserves_the_descriptor_offset(self) -> None:
        fd = os.open(self.path, os.O_RDONLY)
        try:
            os.lseek(fd, 123, os.SEEK_SET)
            _pread_via_seek(fd, 200, 40)
            self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 123)
        finally:
            os.close(fd)


class FchmodReadonlyTests(unittest.TestCase):
    def test_makes_the_backing_file_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "file.bin"
            path.write_bytes(b"payload")
            os.chmod(path, 0o644)
            fd = os.open(path, os.O_RDONLY)
            try:
                fchmod_readonly(fd, os.fspath(path))
            finally:
                os.close(fd)
            self.assertEqual(path.stat().st_mode & 0o777, 0o400)
            with self.assertRaises(PermissionError):
                os.open(path, os.O_WRONLY)
            os.chmod(path, 0o644)


class ReflinkTests(unittest.TestCase):
    def _pair(self, directory: str) -> tuple[int, int, bytes]:
        payload = b"reflink-source-bytes" * 64
        source = Path(directory) / "source.bin"
        destination = Path(directory) / "destination.bin"
        source.write_bytes(payload)
        destination.write_bytes(b"")
        source_fd = os.open(source, os.O_RDONLY)
        destination_fd = os.open(destination, os.O_RDWR)
        return source_fd, destination_fd, payload

    def test_returns_bool_and_clones_content_when_it_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            source_fd, destination_fd, payload = self._pair(name)
            try:
                cloned = try_reflink(destination_fd, source_fd)
                self.assertIsInstance(cloned, bool)
                if cloned:
                    self.assertEqual(
                        os.pread(destination_fd, len(payload), 0), payload
                    )
            finally:
                os.close(source_fd)
                os.close(destination_fd)

    def test_reports_false_and_leaves_destination_untouched_without_fcntl(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as name:
            source_fd, destination_fd, _payload = self._pair(name)
            try:
                with hidden_fcntl():
                    self.assertFalse(try_reflink(destination_fd, source_fd))
                self.assertEqual(os.fstat(destination_fd).st_size, 0)
            finally:
                os.close(source_fd)
                os.close(destination_fd)


class ExclusiveLockTests(unittest.TestCase):
    def test_lock_excludes_a_second_holder_then_releases(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            lock_path = Path(name) / "single-instance.lock"
            first = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            second = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                exclusive_nonblocking_lock(first)
                with self.assertRaises(BlockingIOError):
                    exclusive_nonblocking_lock(second)
                # The lock is advisory but must be strictly non-blocking: the
                # failing call above returned immediately, it did not hang.
                release_lock(first)
                exclusive_nonblocking_lock(second)
                release_lock(second)
            finally:
                os.close(first)
                os.close(second)


class SealReadonlyTests(unittest.TestCase):
    @unittest.skipUnless(supports_sealed_memfd(), "kernel memfd seals required")
    def test_memfd_path_seals_and_reports_the_true_digest(self) -> None:
        import fcntl  # local: this branch only runs where fcntl exists

        payload = b"sealed-closure-bytes" * 32
        descriptor = os.memfd_create("seal-test", os.MFD_ALLOW_SEALING)
        try:
            os.write(descriptor, payload)
            result = seal_readonly(descriptor, None)
            self.assertIsInstance(result, SealResult)
            self.assertTrue(result.sealed)
            self.assertTrue(result.read_only)
            self.assertEqual(result.sha256, hashlib.sha256(payload).hexdigest())
            wanted = (
                fcntl.F_SEAL_GROW
                | fcntl.F_SEAL_SEAL
                | fcntl.F_SEAL_SHRINK
                | fcntl.F_SEAL_WRITE
            )
            self.assertEqual(
                fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & wanted, wanted
            )
            # A sealed descriptor genuinely cannot be written any more.
            with self.assertRaises(OSError):
                os.write(descriptor, b"x")
        finally:
            os.close(descriptor)

    def test_fallback_makes_file_read_only_and_hashes_current_bytes(self) -> None:
        payload = b"portable-closure" * 40
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "closure.bin"
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(descriptor, payload)
                with hidden_fcntl():
                    self.assertFalse(supports_sealed_memfd())
                    result = seal_readonly(descriptor, os.fspath(path))
            finally:
                os.close(descriptor)
            self.assertFalse(result.sealed)
            self.assertTrue(result.read_only)
            self.assertEqual(result.sha256, hashlib.sha256(payload).hexdigest())
            self.assertEqual(path.stat().st_mode & 0o777, 0o400)
            os.chmod(path, 0o600)

    def test_fallback_detects_post_write_tampering(self) -> None:
        pristine = b"the-exact-staged-bytes" * 30
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "closure.bin"
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(descriptor, pristine)
                # Something corrupts one byte after it was staged but before the
                # seal is taken; the returned digest must no longer match.
                os.pwrite(descriptor, b"\x00", 5)
                with hidden_fcntl():
                    result = seal_readonly(descriptor, os.fspath(path))
            finally:
                os.close(descriptor)
            self.assertNotEqual(
                result.sha256, hashlib.sha256(pristine).hexdigest()
            )
            os.chmod(path, 0o600)


class WindowsSimulationTests(unittest.TestCase):
    """Prove the three shipped modules import and function without fcntl."""

    _IMPORT_PROOF = (
        "import sys, importlib.abc\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path, target=None):\n"
        "        if name == 'fcntl' or name.startswith('fcntl.'):\n"
        "            raise ImportError('fcntl hidden')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "try:\n"
        "    import fcntl\n"
        "    raise SystemExit('fcntl unexpectedly importable')\n"
        "except ImportError:\n"
        "    pass\n"
        "import mod_editor.core.platform_compat as pc\n"
        "import mod_editor.core.nfl_audio_provider\n"
        "import mod_editor.core.nfl2k5_stadium_cache\n"
        "import mod_editor.apf_studio.build\n"
        "assert pc.try_reflink(0, 0) is False\n"
        "print('three shipped modules imported and functioned with fcntl hidden')\n"
    )

    def test_modules_import_and_function_without_fcntl(self) -> None:
        environment = dict(os.environ)
        root = Path(__file__).resolve().parents[2]
        environment["PYTHONPATH"] = os.fspath(root)
        completed = subprocess.run(
            [sys.executable, "-c", self._IMPORT_PROOF],
            capture_output=True,
            text=True,
            env=environment,
            cwd=os.fspath(root),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("imported and functioned with fcntl hidden", completed.stdout)

    def test_advisory_lock_fails_closed_when_no_primitive_exists(self) -> None:
        # With fcntl hidden on a non-Windows host there is no lock primitive at
        # all; the guard must refuse rather than run without a single-instance
        # lock.  It is fail-closed, never a silent skip.
        if IS_WINDOWS:
            self.skipTest("Windows has msvcrt and does not exercise this path")
        with tempfile.TemporaryDirectory() as name:
            lock_path = Path(name) / "x.lock"
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                with hidden_fcntl():
                    with self.assertRaises(RuntimeError):
                        exclusive_nonblocking_lock(fd)
            finally:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
