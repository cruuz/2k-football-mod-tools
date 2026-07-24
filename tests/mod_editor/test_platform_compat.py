"""Real-behaviour tests for the cross-platform hardening primitives.

Every test exercises the primitive on the current platform.  Windows-only code
paths (msvcrt locking) cannot run here, but the *portable* fallbacks -- the
seek/read stand-in for ``os.pread``, the chmod stand-in for kernel seals, and
the reflink-unsupported path -- are all reachable on Linux and are tested for
real, including under a ``fcntl``-hidden simulation of a non-POSIX platform.

The privacy tests go one step further.  Mode-bit privacy is the one guarantee
that genuinely does not exist on Windows, so asserting a single number for every
OS would be a lie whichever number was chosen.  Each test therefore asserts the
value :func:`privacy_guarantee` promises *for the platform it is running on*,
and :class:`SimulatedWindowsModeTests` additionally forces the Windows branch on
this host -- ``os.chmod`` reduced to the read-only attribute, mode-less
directories, read-only files that refuse to be deleted -- so the weaker Windows
contract is exercised and asserted here, not merely described.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.abc
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from mod_editor.core import platform_compat
from mod_editor.core.platform_compat import (
    IS_LINUX,
    IS_MACOS,
    IS_WINDOWS,
    PRIVACY_POSIX_MODE_BITS,
    PRIVACY_WINDOWS_USER_PROFILE_ACL,
    PrivatePathError,
    SealResult,
    _pread_via_seek,
    create_private_directory,
    exclusive_nonblocking_lock,
    fchmod_readonly,
    harden_private_directory,
    harden_private_file,
    is_within_user_private_root,
    pread,
    privacy_guarantee,
    private_directory_mode,
    private_file_mode,
    release_lock,
    remove_private_tree,
    seal_readonly,
    sealed_file_mode,
    supports_reflink,
    supports_sealed_memfd,
    try_reflink,
    user_private_root,
    verify_private_directory,
    verify_private_file,
    verify_private_root_placement,
    verify_sealed_file,
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


@contextlib.contextmanager
def simulated_windows_filesystem():
    """Give this process Windows' permission semantics, for real, temporarily.

    Windows cannot be run from here, so the three stdlib behaviours that break
    every POSIX mode assertion are reproduced exactly:

    * ``os.chmod`` honours one bit.  Clearing owner-write sets the read-only
      attribute (the file then reports ``0o444``); setting it clears the
      attribute (``0o666``).  Directories have no mode and always report
      ``0o777``.
    * ``os.mkdir`` ignores its ``mode`` argument entirely.
    * A read-only file cannot be deleted at all -- ``os.unlink`` raises
      ``PermissionError``.  This is the failure that wedged temporary
      directories holding sealed cache files.

    ``os.fchmod`` is removed too, because Windows does not have it: that is what
    forces :func:`fchmod_readonly` down its by-path branch rather than letting a
    POSIX-only call quietly succeed and hide the difference.

    Because the simulation writes *real* modes on this filesystem, every
    ``stat`` the product performs reports Windows-like values without any of the
    product's own code being patched, and :data:`platform_compat.IS_WINDOWS` is
    flipped so the module takes its genuine Windows branch.
    """

    real_chmod = os.chmod
    real_mkdir = os.mkdir
    real_unlink = os.unlink
    real_flags = (
        platform_compat.IS_WINDOWS,
        platform_compat.IS_LINUX,
        platform_compat.IS_MACOS,
    )
    saved_umask = os.umask(0)
    # Windows has no fd-based rmtree; shutil picks that strategy once at import.
    had_fd_functions = hasattr(shutil, "_use_fd_functions")
    saved_fd_functions = getattr(shutil, "_use_fd_functions", None)
    # Windows-absent os members, removed so the guarded fallbacks really run.
    # ``O_NOFOLLOW`` in particular: without it an open() that means "do not
    # follow a symlink" silently does follow one, which is exactly the gap the
    # private-path verification has to close on that platform.
    absent_on_windows = {
        name: getattr(os, name)
        for name in ("fchmod", "O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC")
        if hasattr(os, name)
    }

    def windows_chmod(path, mode, **kwargs):  # noqa: ANN001, ANN003
        if os.path.isdir(path):
            return real_chmod(path, 0o777, **kwargs)
        return real_chmod(path, 0o666 if mode & 0o200 else 0o444, **kwargs)

    def windows_mkdir(path, mode=0o777, **kwargs):  # noqa: ANN001, ANN003
        return real_mkdir(path, 0o777, **kwargs)

    def windows_unlink(path, **kwargs):  # noqa: ANN001, ANN003
        try:
            info = os.lstat(path)
        except OSError:
            info = None
        if info is not None and stat.S_ISREG(info.st_mode) and not info.st_mode & 0o200:
            raise PermissionError(13, "Permission denied", os.fspath(path))
        return real_unlink(path, **kwargs)

    os.chmod = windows_chmod
    os.mkdir = windows_mkdir
    os.unlink = windows_unlink
    for name in absent_on_windows:
        delattr(os, name)
    if had_fd_functions:
        shutil._use_fd_functions = False
    platform_compat.IS_WINDOWS = True
    platform_compat.IS_LINUX = False
    platform_compat.IS_MACOS = False
    try:
        yield
    finally:
        os.chmod = real_chmod
        os.mkdir = real_mkdir
        os.unlink = real_unlink
        for name, value in absent_on_windows.items():
            setattr(os, name, value)
        if had_fd_functions:
            shutil._use_fd_functions = saved_fd_functions
        (
            platform_compat.IS_WINDOWS,
            platform_compat.IS_LINUX,
            platform_compat.IS_MACOS,
        ) = real_flags
        os.umask(saved_umask)


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
        # 0o400 on POSIX, 0o444 on Windows -- the platform's own sealed mode,
        # not a number relaxed until both platforms fit through it.  The shared,
        # unconditional guarantee (no owner-write bit) is asserted separately.
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "file.bin"
            path.write_bytes(b"payload")
            os.chmod(path, 0o644)
            fd = os.open(path, os.O_RDONLY)
            try:
                fchmod_readonly(fd, os.fspath(path))
            finally:
                os.close(fd)
            self.assertEqual(path.stat().st_mode & 0o777, sealed_file_mode())
            self.assertFalse(path.stat().st_mode & 0o200)
            with self.assertRaises(PermissionError):
                os.open(path, os.O_WRONLY)
            os.chmod(path, 0o644)

    def test_the_posix_sealed_mode_is_still_exactly_0o400_here(self) -> None:
        # Guards the port itself: on this POSIX host the historical constant
        # must be unchanged, so a future edit cannot quietly widen it.
        if IS_WINDOWS:
            self.skipTest("this asserts the POSIX constant on a POSIX host")
        self.assertEqual(sealed_file_mode(), 0o400)
        self.assertEqual(private_file_mode(), 0o600)
        self.assertEqual(private_directory_mode(), 0o700)

    def test_fails_closed_when_the_platform_ignores_the_chmod(self) -> None:
        # A platform that silently dropped the permission change must never be
        # mistaken for one that applied it.
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "ignored.bin"
            path.write_bytes(b"payload")
            fd = os.open(path, os.O_RDONLY)
            real_chmod = os.chmod
            real_fchmod = getattr(os, "fchmod", None)
            os.chmod = lambda *args, **kwargs: None  # noqa: ARG005
            if real_fchmod is not None:
                os.fchmod = lambda *args, **kwargs: None  # noqa: ARG005
            try:
                with self.assertRaises(platform_compat.SealIntegrityError):
                    fchmod_readonly(fd, os.fspath(path))
            finally:
                os.chmod = real_chmod
                if real_fchmod is not None:
                    os.fchmod = real_fchmod
                os.close(fd)


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
            # Per-platform sealed mode: 0o400 here, 0o444 on Windows, where
            # there are no group/other bits to clear.  Both satisfy the one
            # guarantee the seal really makes -- no owner-write bit.
            self.assertEqual(path.stat().st_mode & 0o777, sealed_file_mode())
            self.assertFalse(path.stat().st_mode & 0o200)
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


class PrivatePathTests(unittest.TestCase):
    """The privacy contract as it is enforced on the host running the suite."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def test_the_guarantee_names_this_platforms_mechanism_and_modes(self) -> None:
        guarantee = privacy_guarantee()
        if IS_WINDOWS:
            self.assertEqual(guarantee.mechanism, PRIVACY_WINDOWS_USER_PROFILE_ACL)
            self.assertFalse(guarantee.posix_mode_privacy)
            self.assertTrue(guarantee.profile_root_acl)
            self.assertEqual(
                (guarantee.directory_mode, guarantee.file_mode, guarantee.sealed_file_mode),
                (0o777, 0o666, 0o444),
            )
        else:
            self.assertEqual(guarantee.mechanism, PRIVACY_POSIX_MODE_BITS)
            self.assertTrue(guarantee.posix_mode_privacy)
            self.assertFalse(guarantee.profile_root_acl)
            self.assertEqual(
                (guarantee.directory_mode, guarantee.file_mode, guarantee.sealed_file_mode),
                (0o700, 0o600, 0o400),
            )
        # Immutability of a sealed file is the one promise both platforms keep.
        self.assertTrue(guarantee.sealed_read_only)
        self.assertFalse(guarantee.sealed_file_mode & 0o200)

    def test_created_directory_satisfies_its_own_platforms_verifier(self) -> None:
        private = self.root / "cache"
        create_private_directory(private)
        harden_private_directory(private)
        verify_private_directory(private, "test cache")
        if not IS_WINDOWS:
            self.assertEqual(private.stat().st_mode & 0o777, 0o700)
        self.assertEqual(private.stat().st_mode & 0o777, private_directory_mode())

    def test_a_world_readable_directory_is_refused_on_posix(self) -> None:
        # The POSIX confidentiality assertion, unchanged: 0o755 is not private.
        if IS_WINDOWS:
            self.skipTest("directories carry no mode on Windows; see the sim test")
        private = self.root / "leaky"
        private.mkdir(mode=0o755)
        os.chmod(private, 0o755)
        with self.assertRaisesRegex(PrivatePathError, "mode-0700"):
            verify_private_directory(private, "test cache")

    def test_a_symlinked_directory_is_refused_everywhere(self) -> None:
        real = self.root / "real"
        real.mkdir(mode=0o700)
        link = self.root / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this platform/account cannot create symlinks")
        with self.assertRaisesRegex(PrivatePathError, "non-link directory"):
            verify_private_directory(link, "test cache")

    def test_private_file_is_verified_against_this_platforms_mode(self) -> None:
        path = self.root / "staged.bin"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        harden_private_file(path)
        verify_private_file(path, "staged file")
        self.assertEqual(path.stat().st_mode & 0o777, private_file_mode())
        if not IS_WINDOWS:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_a_group_readable_staging_file_is_refused_on_posix(self) -> None:
        if IS_WINDOWS:
            self.skipTest("0o640 cannot exist on Windows; see the sim test")
        path = self.root / "leaky.bin"
        path.write_bytes(b"x")
        os.chmod(path, 0o640)
        with self.assertRaisesRegex(PrivatePathError, "mode-0600"):
            verify_private_file(path, "staged file")

    def test_sealed_file_verification_requires_no_owner_write_bit(self) -> None:
        path = self.root / "sealed.bin"
        path.write_bytes(b"sealed")
        descriptor = os.open(path, os.O_RDONLY)
        try:
            fchmod_readonly(descriptor, os.fspath(path))
        finally:
            os.close(descriptor)
        verify_sealed_file(path, "sealed file")
        self.assertEqual(path.stat().st_mode & 0o777, sealed_file_mode())
        os.chmod(path, 0o600)
        with self.assertRaisesRegex(PrivatePathError, "still carries owner-write"):
            verify_sealed_file(path, "sealed file")

    def test_the_default_private_root_is_this_users_own_tree(self) -> None:
        root = user_private_root()
        self.assertTrue(root.is_absolute())
        self.assertTrue(is_within_user_private_root(root))
        self.assertTrue(is_within_user_private_root(root / "2k5-mod-studio"))
        # Placement is the Windows guarantee, so it is only asserted there; on
        # POSIX the mode bits travel with the directory wherever it lives, which
        # is why a temporary-directory cache root must stay acceptable.
        verify_private_root_placement(root / "2k5-mod-studio", "test cache root")
        if not IS_WINDOWS:
            verify_private_root_placement(self.root, "test cache root")

    def test_removing_a_tree_containing_a_sealed_file_succeeds(self) -> None:
        tree = self.root / "staging"
        tree.mkdir(mode=0o700)
        nested = tree / "nested"
        nested.mkdir(mode=0o700)
        sealed = nested / "sealed.bin"
        sealed.write_bytes(b"payload")
        os.chmod(sealed, 0o400)
        remove_private_tree(tree)
        self.assertFalse(tree.exists())


class SimulatedWindowsModeTests(unittest.TestCase):
    """Force the Windows privacy branch on this host and assert what it promises.

    Windows is not merely "POSIX with different numbers": mode bits confer no
    privacy there at all.  These tests exercise that branch for real -- with
    ``os.chmod`` reduced to the read-only attribute and read-only files
    refusing to be deleted -- so the weaker guarantee is verified rather than
    described, and so the POSIX branch above can stay exactly as strict as it
    has always been.
    """

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def test_the_windows_branch_reports_the_acl_mechanism_and_its_modes(self) -> None:
        with simulated_windows_filesystem():
            guarantee = privacy_guarantee()
            self.assertEqual(guarantee.mechanism, PRIVACY_WINDOWS_USER_PROFILE_ACL)
            self.assertFalse(guarantee.posix_mode_privacy)
            self.assertTrue(guarantee.profile_root_acl)
            self.assertEqual(private_directory_mode(), 0o777)
            self.assertEqual(private_file_mode(), 0o666)
            self.assertEqual(sealed_file_mode(), 0o444)
            self.assertIn("no POSIX mode bits", guarantee.summary)
        # The POSIX branch is restored untouched.
        self.assertEqual(privacy_guarantee().mechanism, PRIVACY_POSIX_MODE_BITS)

    def test_a_private_directory_reports_0o777_and_is_still_accepted(self) -> None:
        # This is the 511-vs-448 failure. The directory really is mode-less on
        # Windows, so the verifier asserts what Windows can promise instead.
        with simulated_windows_filesystem():
            private = self.root / "derived"
            create_private_directory(private)
            harden_private_directory(private)
            self.assertEqual(private.stat().st_mode & 0o777, 0o777)
            self.assertEqual(private.stat().st_mode & 0o777, private_directory_mode())
            verify_private_directory(private, "test cache")

    def test_a_private_file_reports_0o666_and_is_still_accepted(self) -> None:
        # This is the 438-vs-384 failure, asserted honestly for Windows.
        with simulated_windows_filesystem():
            path = self.root / "staged.bin"
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
            harden_private_file(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o666)
            self.assertEqual(path.stat().st_mode & 0o777, private_file_mode())
            verify_private_file(path, "staged file")

    def test_a_sealed_file_reports_0o444_and_keeps_the_real_guarantee(self) -> None:
        # This is the 292-vs-256 failure.  The read-only attribute genuinely is
        # set: the owner-write bit is gone, which is the guarantee that matters.
        with simulated_windows_filesystem():
            path = self.root / "sealed.bin"
            path.write_bytes(b"payload")
            descriptor = os.open(path, os.O_RDONLY)
            try:
                fchmod_readonly(descriptor, os.fspath(path))
            finally:
                os.close(descriptor)
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)
            self.assertEqual(path.stat().st_mode & 0o777, sealed_file_mode())
            self.assertFalse(path.stat().st_mode & 0o200)
            verify_sealed_file(path, "sealed file")
            # And the POSIX number is genuinely NOT what Windows produces --
            # proof the branch ran rather than the POSIX path silently passing.
            self.assertNotEqual(path.stat().st_mode & 0o777, 0o400)
        os.chmod(self.root / "sealed.bin", 0o600)

    def test_a_writable_staging_file_still_fails_closed_if_left_read_only(self) -> None:
        with simulated_windows_filesystem():
            path = self.root / "accidentally-sealed.bin"
            path.write_bytes(b"payload")
            os.chmod(path, 0o400)
            with self.assertRaisesRegex(PrivatePathError, "mode-0666"):
                verify_private_file(path, "staged file")
        os.chmod(self.root / "accidentally-sealed.bin", 0o600)

    def test_a_cache_root_outside_the_user_profile_is_refused(self) -> None:
        # Placement is the whole Windows guarantee, so it is enforced there.
        with simulated_windows_filesystem():
            with self.assertRaisesRegex(PrivatePathError, "private profile root"):
                verify_private_root_placement(self.root, "test cache root")

    def test_a_sealed_file_no_longer_wedges_tree_removal(self) -> None:
        # The PermissionError [Errno 13] that took out every temporary directory
        # holding a sealed cache file: a read-only file cannot be deleted at all
        # on Windows, so remove_private_tree clears the attribute first.
        with simulated_windows_filesystem():
            tree = self.root / "private-staging"
            tree.mkdir()
            nested = tree / "nested"
            nested.mkdir()
            sealed = nested / "sealed.bin"
            sealed.write_bytes(b"payload")
            os.chmod(sealed, 0o400)
            self.assertEqual(sealed.stat().st_mode & 0o777, 0o444)
            with self.assertRaises(PermissionError):
                shutil.rmtree(tree)
            self.assertTrue(sealed.exists())
            remove_private_tree(tree)
            self.assertFalse(tree.exists())


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
