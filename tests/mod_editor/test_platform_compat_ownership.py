#!/usr/bin/env python3
"""Real-behaviour tests for cross-platform *ownership* and lazy write-seals.

Two portability defects are covered here, both of which made the released tool
unusable on Windows:

1. ``AttributeError: module 'os' has no attribute 'getuid'``.  Ten private-cache
   guards asserted ``st_uid == os.getuid()``.  The naive port -- dropping the
   comparison, or trusting the ``st_uid`` Windows reports -- would have been a
   silent security regression, because Windows reports ``st_uid == 0`` for every
   file, so the check would have passed for a cache planted by *another*
   account.  The fix routes every site through
   :func:`platform_compat.describe_ownership`, which answers the same question
   with each platform's own ownership model and *names* the model it used.

2. ``ModuleNotFoundError: No module named 'fcntl'``.  The pinned XISO verifier
   imported :mod:`fcntl` at module scope and evaluated the ``F_SEAL_*`` names in
   a module constant, so it could not even be imported on Windows -- taking five
   sibling verifiers that only want its XDVDFS parser down with it.

Windows itself cannot be run here, so the Windows branches are exercised by
simulating exactly what that platform looks like from inside the interpreter:
:mod:`fcntl` hidden behind a meta-path finder, ``os.getuid`` deleted, and
``IS_WINDOWS`` flipped.  Every test that does so also asserts the POSIX branch is
unchanged, because "make Windows pass" must never mean "make POSIX weaker".
"""

from __future__ import annotations

import contextlib
import importlib.abc
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mod_editor.core import platform_compat
from mod_editor.core.nfl2k5_audio_origin_preparation import (
    Nfl2k5AudioOriginPreparation,
)
from mod_editor.core.nfl2k5_audio_source_containment import (
    AudioSourceContainmentError,
    Nfl2k5AudioSourceContainmentStore,
)
from mod_editor.core.platform_compat import (
    OWNERSHIP_POSIX_UID,
    OWNERSHIP_WINDOWS_OWNER_SID,
    OwnershipCheckError,
    describe_ownership,
    is_owned_by_current_user,
    ownership_mechanism,
    supports_posix_uid_ownership,
    write_seal_mask,
)


SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"

# A SID pair standing in for "me" and "some other account on this machine".
MY_SID = "S-1-5-21-1111111111-2222222222-3333333333-1001"
OTHER_SID = "S-1-5-21-1111111111-2222222222-3333333333-1002"


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
def simulated_windows(*, owner_sid: str | None = MY_SID):
    """Make this interpreter look like Windows to :mod:`platform_compat`.

    Deletes ``os.getuid`` (the actual Windows condition, and what
    :func:`platform_compat.supports_posix_uid_ownership` keys off), flips the
    platform constants, and -- unless ``owner_sid`` is ``None`` -- substitutes
    the two ctypes-backed SID lookups, which cannot run on a POSIX host.  Every
    mutation is undone on exit so the rest of the file tests the real platform.
    """

    saved_getuid = os.getuid
    saved_windows = platform_compat.IS_WINDOWS
    saved_linux = platform_compat.IS_LINUX
    saved_owner = platform_compat._windows_owner_sid
    saved_current = platform_compat._windows_current_user_sid
    del os.getuid
    platform_compat.IS_WINDOWS = True
    platform_compat.IS_LINUX = False
    if owner_sid is not None:
        platform_compat._windows_owner_sid = (
            lambda *, fd, path: owner_sid  # noqa: ARG005
        )
        platform_compat._windows_current_user_sid = lambda: MY_SID
    try:
        yield
    finally:
        os.getuid = saved_getuid
        platform_compat.IS_WINDOWS = saved_windows
        platform_compat.IS_LINUX = saved_linux
        platform_compat._windows_owner_sid = saved_owner
        platform_compat._windows_current_user_sid = saved_current


def stat_with_uid(uid: int) -> os.stat_result:
    """A real :class:`os.stat_result` carrying an arbitrary ``st_uid``."""

    return os.stat_result((0o100600, 1, 1, 1, uid, uid, 0, 0, 0, 0))


class PosixOwnershipTests(unittest.TestCase):
    """The POSIX branch must be byte-identical to the historical check."""

    def test_mechanism_is_the_uid_comparison_on_this_host(self) -> None:
        self.assertTrue(supports_posix_uid_ownership())
        self.assertEqual(ownership_mechanism(), OWNERSHIP_POSIX_UID)

    def test_a_file_this_process_created_is_owned(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "mine"
            path.write_bytes(b"x")
            check = describe_ownership(path.stat(), path=path)
            self.assertTrue(check.owned)
            self.assertEqual(check.mechanism, OWNERSHIP_POSIX_UID)
            self.assertIn(str(os.getuid()), check.detail)

    def test_another_uid_is_refused(self) -> None:
        check = describe_ownership(stat_with_uid(os.getuid() + 1))
        self.assertFalse(check.owned)
        self.assertEqual(check.mechanism, OWNERSHIP_POSIX_UID)

    def test_fd_and_path_never_influence_the_posix_answer(self) -> None:
        # The Windows-only locators must not change POSIX behaviour, even when
        # they are nonsense: the uid comparison alone decides.
        foreign = stat_with_uid(os.getuid() + 1)
        self.assertFalse(
            is_owned_by_current_user(foreign, fd=-1, path="/nonexistent")
        )
        self.assertTrue(
            is_owned_by_current_user(
                stat_with_uid(os.getuid()), fd=-1, path="/nonexistent"
            )
        )

    def test_ownership_survives_fcntl_being_unavailable(self) -> None:
        # Ownership has nothing to do with fcntl; hiding it must not disturb it.
        with hidden_fcntl():
            self.assertEqual(ownership_mechanism(), OWNERSHIP_POSIX_UID)
            self.assertTrue(is_owned_by_current_user(stat_with_uid(os.getuid())))


class SimulatedWindowsOwnershipTests(unittest.TestCase):
    """The Windows branch: owner SID, and never a vacuous pass."""

    def test_mechanism_switches_to_the_owner_sid_model(self) -> None:
        with simulated_windows():
            self.assertFalse(supports_posix_uid_ownership())
            self.assertEqual(ownership_mechanism(), OWNERSHIP_WINDOWS_OWNER_SID)
        # ...and switches straight back; nothing leaks into the POSIX branch.
        self.assertEqual(ownership_mechanism(), OWNERSHIP_POSIX_UID)

    def test_windows_st_uid_zero_is_never_trusted(self) -> None:
        # This is the whole point.  Windows reports st_uid == 0 for every file,
        # including one planted by another account.  A port that kept comparing
        # st_uid would accept it; the owner-SID model must decide instead.
        windows_shaped = stat_with_uid(0)
        with simulated_windows(owner_sid=OTHER_SID):
            check = describe_ownership(windows_shaped, path=__file__)
            self.assertFalse(check.owned)
            self.assertEqual(check.mechanism, OWNERSHIP_WINDOWS_OWNER_SID)
            self.assertIn(OTHER_SID, check.detail)

    def test_matching_owner_sid_is_owned(self) -> None:
        with simulated_windows(owner_sid=MY_SID):
            check = describe_ownership(stat_with_uid(0), path=__file__)
            self.assertTrue(check.owned)
            self.assertEqual(check.mechanism, OWNERSHIP_WINDOWS_OWNER_SID)

    def test_refuses_to_answer_with_nothing_to_interrogate(self) -> None:
        # No fd and no path means there is no object to ask about.  Guessing
        # would be the vacuous pass; the caller bug is surfaced instead.
        with simulated_windows():
            with self.assertRaises(OwnershipCheckError):
                describe_ownership(stat_with_uid(0))

    def test_a_failed_win32_lookup_fails_closed(self) -> None:
        # owner_sid=None leaves the real ctypes path in place, which cannot
        # resolve on a POSIX host (no ctypes.windll).  An unanswerable ownership
        # question must be reported as NOT owned, with the reason attached.
        with simulated_windows(owner_sid=None):
            check = describe_ownership(stat_with_uid(0), path=__file__)
            self.assertFalse(check.owned)
            self.assertEqual(check.mechanism, OWNERSHIP_WINDOWS_OWNER_SID)
            self.assertIn("unavailable", check.detail)

    def test_the_descriptor_form_is_preferred_over_the_path(self) -> None:
        # The open descriptor is the object the caller already validated, so
        # interrogating the *handle* -- GetSecurityInfo -- rather than the name
        # -- GetNamedSecurityInfoW -- is what closes the stat/open race.  The
        # real dispatch runs here; only the Win32 edge is stubbed.
        with tempfile.TemporaryDirectory() as name:
            target = Path(name) / "mine"
            target.write_bytes(b"x")
            fd = os.open(target, os.O_RDONLY)
            try:
                with_fd = self._record_win32_calls(fd=fd, path=target)
                without_fd = self._record_win32_calls(fd=None, path=target)
            finally:
                os.close(fd)
        self.assertEqual(with_fd, ["GetSecurityInfo", "LocalFree"])
        self.assertEqual(without_fd, ["GetNamedSecurityInfoW", "LocalFree"])

    def _record_win32_calls(
        self, *, fd: int | None, path: Path
    ) -> list[str]:
        """Run the real ``_windows_owner_sid`` against a recording fake API."""

        called: list[str] = []

        class _Recorder:
            def __init__(self, name: str) -> None:
                self._name = name

            def __call__(self, *args: object) -> int:
                called.append(self._name)
                return 0

        class _Library:
            def __getattr__(self, name: str) -> _Recorder:
                return _Recorder(name)

        fake_msvcrt = type(sys)("msvcrt")
        fake_msvcrt.get_osfhandle = lambda descriptor: 4242  # noqa: ARG005
        saved_msvcrt = sys.modules.get("msvcrt")
        saved_api = platform_compat._windows_security_api
        saved_string_sid = platform_compat._windows_string_sid
        sys.modules["msvcrt"] = fake_msvcrt
        try:
            platform_compat._windows_security_api = (
                lambda: platform_compat._WindowsSecurityApi(
                    advapi32=_Library(), kernel32=_Library()
                )
            )
            platform_compat._windows_string_sid = (
                lambda api, sid: MY_SID  # noqa: ARG005
            )
            with simulated_windows(owner_sid=None):
                self.assertEqual(
                    platform_compat._windows_owner_sid(fd=fd, path=path), MY_SID
                )
        finally:
            platform_compat._windows_security_api = saved_api
            platform_compat._windows_string_sid = saved_string_sid
            if saved_msvcrt is None:
                del sys.modules["msvcrt"]
            else:
                sys.modules["msvcrt"] = saved_msvcrt
        return called


class OwnershipCallSiteTests(unittest.TestCase):
    """The guards must really consult the helper, not merely import it."""

    def test_private_file_readiness_asks_the_ownership_helper(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "inventory.json"
            path.write_bytes(b"{}")
            path.chmod(0o600)
            ready = Nfl2k5AudioOriginPreparation._private_file_ready
            self.assertTrue(ready(path, 1 << 20))

            # If ownership is denied, the preflight must refuse -- proving the
            # answer is load-bearing rather than decorative.
            saved = platform_compat.is_owned_by_current_user
            try:
                platform_compat.is_owned_by_current_user = (
                    lambda info, **kwargs: False  # noqa: ARG005
                )
                self.assertFalse(ready(path, 1 << 20))
            finally:
                platform_compat.is_owned_by_current_user = saved

    def test_containment_cache_open_asks_the_ownership_helper(self) -> None:
        store = Nfl2k5AudioSourceContainmentStore(
            expected_source_sha256=SOURCE_SHA256
        )
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            root.chmod(0o700)
            root_fd, parent_fd = store._open_private_parent(root, create=True)
            os.close(parent_fd)
            os.close(root_fd)

            saved = platform_compat.is_owned_by_current_user
            try:
                platform_compat.is_owned_by_current_user = (
                    lambda info, **kwargs: False  # noqa: ARG005
                )
                with self.assertRaises(AudioSourceContainmentError):
                    store._open_private_parent(root, create=False)
            finally:
                platform_compat.is_owned_by_current_user = saved

    def test_no_guarded_module_calls_os_getuid_directly_any_more(self) -> None:
        # A single missed site would raise AttributeError on Windows, which is
        # exactly how this defect was reported, so assert on the source.
        root = Path(__file__).resolve().parents[2]
        guarded = (
            "mod_editor/core/nfl2k5_build_service.py",
            "mod_editor/core/nfl2k5_audio_origin_preparation.py",
            "mod_editor/core/nfl2k5_audio_source_containment.py",
        )
        for relative in guarded:
            with self.subTest(module=relative):
                source = (root / relative).read_text(encoding="utf-8")
                self.assertNotIn("os.getuid()", source)
                self.assertIn("is_owned_by_current_user", source)


class WriteSealTests(unittest.TestCase):
    """Seals stay a fail-closed POSIX primitive, resolved lazily."""

    def test_mask_matches_the_historical_literal(self) -> None:
        if not platform_compat.supports_sealed_memfd():
            self.skipTest("kernel memfd seals are unavailable on this host")
        import fcntl

        self.assertEqual(
            write_seal_mask(),
            fcntl.F_SEAL_WRITE
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_SEAL,
        )

    def test_seals_round_trip_on_a_real_memfd(self) -> None:
        if not platform_compat.supports_sealed_memfd():
            self.skipTest("kernel memfd seals are unavailable on this host")
        fd = os.memfd_create("ownership-test", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        try:
            os.write(fd, b"payload")
            mask = write_seal_mask()
            platform_compat.add_seals(fd, mask)
            self.assertEqual(platform_compat.read_seals(fd) & mask, mask)
            with self.assertRaises(OSError):
                os.pwrite(fd, b"X", 0)
        finally:
            os.close(fd)

    def test_seal_helpers_fail_closed_without_fcntl(self) -> None:
        # Not an ImportError at module scope -- a typed refusal at the moment a
        # POSIX-only primitive is actually requested.
        with hidden_fcntl():
            self.assertFalse(platform_compat.supports_sealed_memfd())
            with self.assertRaises(RuntimeError):
                write_seal_mask()
            with self.assertRaises(RuntimeError):
                platform_compat.read_seals(0)


class PinnedVerifierImportTests(unittest.TestCase):
    """The pinned XISO verifier must import where :mod:`fcntl` does not exist."""

    _IMPORT_PROOF = """
import importlib.abc
import os
import sys


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name == "fcntl" or name.startswith("fcntl."):
            raise ImportError("fcntl hidden")
        return None


sys.meta_path.insert(0, Blocker())
sys.modules.pop("fcntl", None)
del os.getuid
sys.path.insert(0, os.path.join(os.getcwd(), "tools"))

import nfl_uniform_color_xiso_direct_verify as verifier

# The parser five sibling verifiers depend on must be usable...
assert verifier.SECTOR == 2048
assert callable(verifier.parse_xdvdfs)
# ...and the seal contract must refuse rather than silently skip.
try:
    verifier.required_executable_seals()
except RuntimeError:
    print("verifier imported and refused seals with fcntl hidden")
else:
    raise SystemExit("seals resolved without fcntl")
"""

    def test_imports_and_refuses_seals_with_fcntl_hidden(self) -> None:
        root = Path(__file__).resolve().parents[2]
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.fspath(root)
        completed = subprocess.run(
            [sys.executable, "-c", self._IMPORT_PROOF],
            capture_output=True,
            text=True,
            env=environment,
            cwd=os.fspath(root),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            "verifier imported and refused seals with fcntl hidden",
            completed.stdout,
        )

    def test_module_scope_no_longer_imports_fcntl(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = (
            root / "tools/nfl_uniform_color_xiso_direct_verify.py"
        ).read_text(encoding="utf-8")
        for line in source.splitlines():
            self.assertNotEqual(line.strip(), "import fcntl")


if __name__ == "__main__":
    unittest.main()
