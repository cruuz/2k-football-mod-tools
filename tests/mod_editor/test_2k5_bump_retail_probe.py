"""The retail-image probe may hash a 4.7 GB file once per identity, not once per pick.

Every time a source or target is chosen the panel asks whether the file IS the
retail ISO, and the honest answer is a full SHA-256. Re-picking the same file
used to pay that hash again. The probe now memoizes its verdict behind the
file's identity (resolved path, size, mtime), so an unchanged file answers
from the cache and any rewrite re-hashes. The guard itself is unchanged: the
size gate still runs first, and a hash is still the only way to a True.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.gui import bump_panel_qt as bump_panel  # noqa: E402


class _CountingProgress:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, stage: str, completed: int, total: int) -> None:
        self.calls += 1


class RetailProbeCacheTests(unittest.TestCase):
    """Cache behavior, asserted through hash-call counts, never wall clocks."""

    RETAIL_SIZE = 4096

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self._original_size = bump_panel.RETAIL_XISO_SIZE
        self._original_sha = bump_panel.RETAIL_XISO_SHA256
        bump_panel.RETAIL_XISO_SIZE = self.RETAIL_SIZE
        self.retail_bytes = bytes(range(256)) * (self.RETAIL_SIZE // 256)
        bump_panel.RETAIL_XISO_SHA256 = hashlib.sha256(
            self.retail_bytes
        ).hexdigest()
        bump_panel.clear_retail_probe_cache()
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        bump_panel.RETAIL_XISO_SIZE = self._original_size
        bump_panel.RETAIL_XISO_SHA256 = self._original_sha
        bump_panel.clear_retail_probe_cache()

    def _write(self, name: str, payload: bytes) -> Path:
        path = self.work / name
        path.write_bytes(payload)
        return path

    def test_wrong_size_is_refused_without_hashing(self) -> None:
        path = self._write("small.bin", b"not the retail image")
        progress = _CountingProgress()
        self.assertFalse(bump_panel._retail_probe(path, progress))
        self.assertFalse(bump_panel._retail_probe(path, progress))
        self.assertEqual(progress.calls, 0)

    def test_the_retail_image_hashes_once_and_answers_from_cache(self) -> None:
        path = self._write("retail.iso", self.retail_bytes)
        progress = _CountingProgress()
        self.assertTrue(bump_panel._retail_probe(path, progress))
        hashes = progress.calls
        self.assertEqual(hashes, 1)
        self.assertTrue(bump_panel._retail_probe(path, progress))
        self.assertTrue(bump_panel._retail_probe(path, progress))
        self.assertEqual(progress.calls, hashes)

    def test_a_same_size_non_retail_image_caches_its_false(self) -> None:
        other = bytes(reversed(self.retail_bytes))
        path = self._write("copy.iso", other)
        progress = _CountingProgress()
        self.assertFalse(bump_panel._retail_probe(path, progress))
        self.assertEqual(progress.calls, 1)
        self.assertFalse(bump_panel._retail_probe(path, progress))
        self.assertEqual(progress.calls, 1)

    def test_a_rewrite_invalidates_the_cached_verdict(self) -> None:
        path = self._write("image.iso", bytes(self.RETAIL_SIZE))
        progress = _CountingProgress()
        self.assertFalse(bump_panel._retail_probe(path, progress))
        path.write_bytes(self.retail_bytes)
        future = path.stat().st_mtime_ns + 10_000_000_000
        os.utime(path, ns=(future, future))
        self.assertTrue(bump_panel._retail_probe(path, progress))
        self.assertEqual(progress.calls, 2)

    def test_clearing_the_cache_forces_a_rehash(self) -> None:
        path = self._write("retail.iso", self.retail_bytes)
        progress = _CountingProgress()
        self.assertTrue(bump_panel._retail_probe(path, progress))
        bump_panel.clear_retail_probe_cache()
        self.assertTrue(bump_panel._retail_probe(path, progress))
        self.assertEqual(progress.calls, 2)

    def test_the_same_file_probed_through_two_paths_hashes_once(self) -> None:
        path = self._write("retail.iso", self.retail_bytes)
        link = self.work / "alias.iso"
        link.symlink_to(path)
        progress = _CountingProgress()
        self.assertTrue(bump_panel._retail_probe(path, progress))
        self.assertTrue(bump_panel._retail_probe(link, progress))
        self.assertEqual(progress.calls, 1)

    def test_many_images_stay_bounded(self) -> None:
        progress = _CountingProgress()
        paths = []
        for index in range(bump_panel._RETAIL_PROBE_CACHE_LIMIT + 4):
            payload = bytearray(self.retail_bytes)
            payload[0] = index
            paths.append(self._write(f"image_{index}.iso", bytes(payload)))
        for path in paths:
            bump_panel._retail_probe(path, progress)
        self.assertEqual(
            len(bump_panel._RETAIL_PROBE_CACHE),
            bump_panel._RETAIL_PROBE_CACHE_LIMIT,
        )
        # The evicted oldest entry re-hashes; a retained one does not.
        oldest = paths[0]
        before = progress.calls
        bump_panel._retail_probe(oldest, progress)
        self.assertEqual(progress.calls, before + 1)
        newest = paths[-1]
        before = progress.calls
        bump_panel._retail_probe(newest, progress)
        self.assertEqual(progress.calls, before)


if __name__ == "__main__":
    unittest.main()
