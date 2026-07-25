"""Privacy contract of the private, XISO-derived NFL 2K5 source cache.

The cache holds bytes extracted from the user's own game image, so "only this
user can read it" is a real requirement rather than tidiness.  POSIX expresses
it in mode bits (``0o700`` directories, ``0o600`` files) and re-verifies them;
Windows has no mode bits at all and expresses it as placement under the per-user
profile root, whose ACL is inherited by everything beneath it.

These tests assert both contracts -- the POSIX one on this host unchanged, and
the Windows one under a forced Windows filesystem -- because a single shared
assertion would necessarily be a lie about one of the two platforms.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from mod_editor.core import platform_compat
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_source_cache import Nfl2k5SourceCache, default_cache_root
from tests.mod_editor.test_platform_compat import simulated_windows_filesystem


class DefaultCacheRootTests(unittest.TestCase):
    def test_posix_keeps_the_historical_xdg_style_location(self) -> None:
        if platform_compat.IS_WINDOWS:
            self.skipTest("this asserts the unchanged POSIX location")
        self.assertEqual(default_cache_root(), Path.home() / ".cache" / "2k5-mod-studio")

    def test_the_root_is_inside_this_users_private_tree_on_both_platforms(self) -> None:
        self.assertTrue(platform_compat.is_within_user_private_root(default_cache_root()))
        platform_compat.verify_private_root_placement(
            default_cache_root(), "the private source cache root"
        )
        with simulated_windows_filesystem():
            windows_root = default_cache_root()
            self.assertTrue(platform_compat.is_within_user_private_root(windows_root))
            # On Windows the location *is* the guarantee, so it must resolve to
            # the per-user application-data root rather than to ~/.cache.
            self.assertEqual(windows_root.parent.parent, platform_compat.user_private_root())
            platform_compat.verify_private_root_placement(
                windows_root, "the private source cache root"
            )


class PrivateStagingVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="private-source-cache-")
        self.root = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def test_marker_is_owner_only_on_posix(self) -> None:
        if platform_compat.IS_WINDOWS:
            self.skipTest("POSIX mode privacy does not exist on Windows")
        marker = self.root / "cache.json"
        Nfl2k5SourceCache._atomic_write_json(marker, {"schema": "test"})
        self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)
        self.assertEqual(json.loads(marker.read_text(encoding="utf-8")), {"schema": "test"})

    def test_marker_takes_the_windows_branch_and_is_verified_there_too(self) -> None:
        with simulated_windows_filesystem():
            marker = self.root / "cache.json"
            Nfl2k5SourceCache._atomic_write_json(marker, {"schema": "test"})
            # 0o666 is what a writable file reports on Windows.  It confers no
            # privacy -- the cache root's ACL does -- and the verifier asserts
            # that honest value instead of a POSIX number that cannot hold.
            self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o666)
            self.assertEqual(stat.S_IMODE(marker.stat().st_mode), platform_compat.private_file_mode())
            self.assertFalse(platform_compat.privacy_guarantee().posix_mode_privacy)
            self.assertEqual(
                json.loads(marker.read_text(encoding="utf-8")), {"schema": "test"}
            )

    def test_a_world_readable_staging_directory_is_refused_on_posix(self) -> None:
        if platform_compat.IS_WINDOWS:
            self.skipTest("directories carry no mode on Windows")
        leaky = self.root / "leaky-staging"
        leaky.mkdir(mode=0o755)
        os.chmod(leaky, 0o755)
        with self.assertRaisesRegex(ValidationError, "mode-0700"):
            Nfl2k5SourceCache._require_private_directory(leaky, "staging")

    def test_a_symlinked_staging_directory_is_refused_on_both_platforms(self) -> None:
        real = self.root / "real-staging"
        real.mkdir(mode=0o700)
        link = self.root / "linked-staging"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this platform/account cannot create symlinks")
        with self.assertRaisesRegex(ValidationError, "non-link directory"):
            Nfl2k5SourceCache._require_private_directory(link, "staging")
        with simulated_windows_filesystem():
            with self.assertRaisesRegex(ValidationError, "non-link directory"):
                Nfl2k5SourceCache._require_private_directory(link, "staging")


class PrivateTreeRemovalTests(unittest.TestCase):
    """Failed indexing must always be able to delete its own staging tree."""

    def test_a_sealed_pack_does_not_wedge_cleanup_on_windows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="private-source-cache-") as name:
            staging = Path(name) / "indexing"
            (staging / "packs").mkdir(parents=True)
            pack = staging / "packs" / "0"
            pack.write_bytes(b"private pack bytes")
            with simulated_windows_filesystem():
                os.chmod(pack, 0o400)
                self.assertEqual(stat.S_IMODE(pack.stat().st_mode), 0o444)
                platform_compat.remove_private_tree(staging)
            self.assertFalse(staging.exists())


if __name__ == "__main__":
    unittest.main()
