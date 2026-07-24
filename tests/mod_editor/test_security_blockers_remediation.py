"""Remediation tests for the three GPT-5.6 audit BLOCKERS.

These cover the caller-side halves that live in the three cache/provider modules
(``platform_compat`` owns the DACL query, the reparse predicate and the seal
primitives; those are proved by its own suite):

* Finding 1 -- the private NFL 2K5 source-cache root is created through the
  DACL-applying private-directory creator (``create_private_directory``) and its
  real placement/ACL is re-verified, never a bare ``Path.mkdir``.
* Finding 2 -- every private-cache directory guard also refuses a Windows
  JUNCTION / reparse point, not only an ``S_ISLNK`` symlink.  Windows cannot run
  here, so a junction is simulated by injecting the ``st_reparse_tag`` that
  ``os.lstat`` sets on Windows for a reparse point (a real junction reports
  ``S_ISDIR`` true and ``S_ISLNK`` false, which is exactly the gap), under the
  shared ``simulated_windows_filesystem`` Windows branch.
* Finding 3 -- on the non-memfd (macOS/Windows) seal path, where the file is only
  chmod-read-only, the staged closure is re-hashed against its sealed digest
  immediately before the subprocess would open it, so a swap after the seal is
  caught and fails closed.  The Linux memfd path stays a no-op.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from mod_editor.core import platform_compat
from mod_editor.core import nfl2k5_source_cache as source_cache_mod
from mod_editor.core import nfl2k5_stadium_cache as stadium_mod
from mod_editor.core import nfl_audio_provider as audio_mod
from mod_editor.core.errors import ValidationError
from mod_editor.core.model import SourceRecord
from mod_editor.core.nfl2k5_source_cache import (
    Nfl2k5SourceCache,
    SOURCE_SHA256,
    SourceCache,
)
from mod_editor.core.nfl2k5_stadium_cache import (
    Nfl2k5StadiumCacheCoordinator,
    StadiumCacheError,
)
from mod_editor.core.nfl_audio_provider import Nfl2k5MenuBackAudioProvider
from mod_editor.core.platform_compat import supports_sealed_memfd
from mod_editor.core.providers import ProviderError
from tests.mod_editor.test_nfl2k5_stadium_cache import SyntheticSuccessfulRunner
from tests.mod_editor.test_platform_compat import simulated_windows_filesystem


ROOT = Path(__file__).resolve().parents[2]

# A directory-junction (mount-point) reparse tag; any non-zero value proves the
# S_ISLNK-only guard would have missed it.
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003


class _ReparseStat:
    """Wrap a real ``os.stat_result`` and add the Windows ``st_reparse_tag``.

    A real directory junction lstats as ``S_ISDIR`` true, ``S_ISLNK`` false, and
    ``st_reparse_tag`` non-zero.  ``os.stat_result`` cannot carry that attribute
    on POSIX, so this stand-in supplies it while delegating every other field to
    the genuine result -- reproducing exactly what the product's guards see on
    Windows.
    """

    def __init__(self, real: os.stat_result, tag: int = IO_REPARSE_TAG_MOUNT_POINT):
        self._real = real
        self.st_reparse_tag = tag

    def __getattr__(self, name: str):  # delegate st_mode/st_dev/st_ino/...
        return getattr(self._real, name)


def _norm(path) -> str:
    # Filesystem-free canonicalisation (no os.lstat, so no recursion when the
    # fake below is installed): abspath+normpath only touch strings and getcwd.
    return os.path.normcase(os.path.normpath(os.path.abspath(os.fspath(path))))


@contextlib.contextmanager
def _lstat_reports_junction(*targets: Path):
    """Make both ``os.lstat`` and ``Path.lstat`` report the given paths as junctions.

    Product guards use a mix of the module function and the pathlib method; the
    latter does not observe an ``os.lstat`` patch, so both are wrapped.
    """

    wanted = {_norm(p) for p in targets}
    real_os_lstat = os.lstat
    real_path_lstat = Path.lstat

    def _wrap(info: os.stat_result, path) -> os.stat_result:
        try:
            key = _norm(path)
        except TypeError:  # an int fd, never a junction target here
            return info
        return _ReparseStat(info) if key in wanted else info

    def fake_os_lstat(path, *args, **kwargs):
        return _wrap(real_os_lstat(path, *args, **kwargs), path)

    def fake_path_lstat(self, *args, **kwargs):
        return _wrap(real_path_lstat(self, *args, **kwargs), self)

    with mock.patch("os.lstat", fake_os_lstat), mock.patch.object(
        Path, "lstat", fake_path_lstat
    ):
        yield


def _make_source_cache(root: Path) -> SourceCache:
    """A minimal recognized SourceCache pointing at a real private tree."""

    root.mkdir(parents=True, exist_ok=True)
    pack0 = root / "extracted" / "game" / "0"
    pack0.parent.mkdir(parents=True, exist_ok=True)
    pack0.write_bytes(b"synthetic private pack zero")
    inventory = root / "indexes" / "inventory.json"
    inventory.parent.mkdir(parents=True, exist_ok=True)
    inventory.write_text('{"synthetic":true}\n', encoding="utf-8")
    originals = root / "originals"
    originals.mkdir(exist_ok=True)
    source = SourceRecord(
        selected_path="/private/user/NFL2K5.iso",
        inspected_path="/private/user/NFL2K5.iso",
        kind="xiso",
        sha256=SOURCE_SHA256,
        size=6_300_499_968,
        recognized=True,
        fingerprint_id="nfl2k5-usa-retail-xiso",
        detected_game="nfl2k5",
    )
    return SourceCache(
        source=source,
        root=root,
        pack0=pack0,
        inventory=inventory,
        originals=originals,
        resource_count=1,
        outer_entry_count=1,
        kind_counts={"SCNE": 1},
    )


class ReparsePredicateTests(unittest.TestCase):
    """The per-module reparse predicates: non-zero tag => reparse; else not."""

    def test_predicate_is_true_only_for_a_reparse_tag(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / "d"
            directory.mkdir()
            real = os.lstat(directory)
            junction = _ReparseStat(real)
            for module in (source_cache_mod, stadium_mod, audio_mod):
                with self.subTest(module=module.__name__):
                    # A genuine POSIX directory carries no st_reparse_tag.
                    self.assertFalse(module._is_reparse_point(real))
                    # A junction (reparse tag present) is refused.
                    self.assertTrue(module._is_reparse_point(junction))


class Finding1SourceCacheRootTests(unittest.TestCase):
    """The source-cache root is made by the DACL-applying creator, then verified."""

    def test_root_is_created_via_creator_then_placement_verified(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            cache_root = Path(name) / "nested" / "cache"
            cache = Nfl2k5SourceCache(cache_root=cache_root)
            real_create = platform_compat.create_private_directory
            real_verify = platform_compat.verify_private_root_placement
            order: list[tuple[str, Path]] = []

            def spy_create(path, **kwargs):
                order.append(("create", Path(path)))
                return real_create(path, **kwargs)

            def spy_verify(path, label):
                order.append(("verify", Path(path)))
                return real_verify(path, label)

            with mock.patch.object(
                platform_compat, "create_private_directory", spy_create
            ), mock.patch.object(
                platform_compat, "verify_private_root_placement", spy_verify
            ):
                cache._ensure_private_cache_root()

            # The DACL-applying creator ran (not a bare mkdir), and the real
            # placement/ACL was verified AFTERWARDS.
            self.assertEqual([kind for kind, _ in order], ["create", "verify"])
            self.assertEqual(order[0][1], cache_root)
            self.assertEqual(order[1][1], cache_root)
            self.assertTrue(cache_root.is_dir())
            if not platform_compat.IS_WINDOWS:
                # POSIX: the creator's 0o700 replaces the old umask-default root.
                self.assertEqual(stat.S_IMODE(cache_root.stat().st_mode), 0o700)

    def test_ensure_private_cache_root_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            cache = Nfl2k5SourceCache(cache_root=Path(name) / "cache")
            cache._ensure_private_cache_root()
            cache._ensure_private_cache_root()  # exist_ok path, no raise
            self.assertTrue(cache.cache_root.is_dir())


class Finding2JunctionRefusalTests(unittest.TestCase):
    """S_ISLNK-only guards now also refuse a Windows junction / reparse point."""

    def test_source_cache_regular_file_guard_refuses_a_reparse_point(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            target = Path(name) / "pack0"
            target.write_bytes(b"bytes")
            # POSIX view: an ordinary regular file passes unchanged.
            source_cache_mod._regular_non_symlink(target, "cached archive pack")
            with simulated_windows_filesystem(), _lstat_reports_junction(target):
                with self.assertRaisesRegex(ValidationError, "non-link file"):
                    source_cache_mod._regular_non_symlink(target, "cached archive pack")

    def test_source_cache_load_existing_refuses_a_junction_root(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            cache = Nfl2k5SourceCache(cache_root=Path(name))
            final = Path(name) / SOURCE_SHA256
            final.mkdir()
            (final / "cache.json").write_text("{}", encoding="utf-8")
            source = _make_source_cache(Path(name) / "srctree").source
            # Real directory accepted enough to look past the root guard (it then
            # returns None on the marker); a junction root is refused outright.
            with simulated_windows_filesystem(), _lstat_reports_junction(final):
                self.assertIsNone(cache._load_existing(final, source))

    def test_stadium_confined_directory_refuses_a_reparse_point(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            textures = root / "textures"
            textures.mkdir()
            # POSIX view: a real subdirectory is confined and returned.
            self.assertEqual(
                stadium_mod._confined_directory(root, "textures", "texture root"),
                textures,
            )
            with simulated_windows_filesystem(), _lstat_reports_junction(textures):
                with self.assertRaisesRegex(
                    StadiumCacheError, "non-link directory"
                ):
                    stadium_mod._confined_directory(root, "textures", "texture root")

    def test_stadium_ensure_refuses_a_junction_derived_parent(self) -> None:
        # The primary Finding-2 site: the private "derived" parent that holds the
        # whole cache and its single-writer lock must not be a junction.
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve() / "private-source-cache"
            cache = _make_source_cache(root)
            derived_parent = root / "derived"
            coordinator = Nfl2k5StadiumCacheCoordinator(
                runner=SyntheticSuccessfulRunner(), free_space_reserve=0
            )
            with simulated_windows_filesystem(), _lstat_reports_junction(
                derived_parent
            ):
                with self.assertRaisesRegex(
                    StadiumCacheError, "reparse point|junction"
                ):
                    coordinator.ensure(cache)


class Finding3SealReverifyTests(unittest.TestCase):
    """The non-memfd seal is re-hashed immediately before exec; memfd stays a no-op."""

    def setUp(self) -> None:
        self.provider = Nfl2k5MenuBackAudioProvider(workspace=ROOT)
        self.raw = b"PK\x03\x04" + b"synthetic sealed closure payload " * 64

    @contextlib.contextmanager
    def _force_non_memfd(self):
        # Force the chmod-read-only (macOS/Windows) seal path even on Linux, in
        # both the branch selector and seal_readonly itself.
        with mock.patch.object(
            platform_compat, "supports_sealed_memfd", return_value=False
        ), mock.patch.object(
            audio_mod, "supports_sealed_memfd", return_value=False
        ):
            yield

    def test_non_memfd_reverify_passes_when_unchanged(self) -> None:
        with self._force_non_memfd():
            with self.provider._read_only_file_module(self.raw, "writer") as module:
                self.assertFalse(str(module.path).startswith("/proc/"))
                module.reverify_before_exec()  # unchanged snapshot: no raise

    def test_non_memfd_reverify_catches_an_in_place_byte_swap(self) -> None:
        with self._force_non_memfd():
            with self.provider._read_only_file_module(self.raw, "writer") as module:
                # The exact attack Finding 3 describes: a same-user process clears
                # the read-only attribute and rewrites the bytes IN PLACE (same
                # length, same inode) between the seal and the exec.
                os.chmod(module.path, 0o600)
                module.path.write_bytes(b"\x00" * len(self.raw))
                with self.assertRaisesRegex(ProviderError, "bytes changed"):
                    module.reverify_before_exec()

    def test_non_memfd_reverify_catches_a_shortened_swap(self) -> None:
        with self._force_non_memfd():
            with self.provider._read_only_file_module(self.raw, "writer") as module:
                os.chmod(module.path, 0o600)
                module.path.write_bytes(b"short")
                with self.assertRaisesRegex(
                    ProviderError, "swapped before execution"
                ):
                    module.reverify_before_exec()

    def test_memfd_reverify_is_a_noop(self) -> None:
        if not supports_sealed_memfd():
            self.skipTest("kernel memfd write-seals are a Linux primitive")
        with self.provider._sealed_memfd_module(self.raw, "writer") as module:
            self.assertRegex(os.fspath(module.path), r"^/proc/\d+/fd/\d+$")
            module.reverify_before_exec()  # kernel-sealed: deliberate no-op


if __name__ == "__main__":
    unittest.main()
