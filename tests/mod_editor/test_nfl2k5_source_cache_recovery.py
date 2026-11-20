"""Publication of a concurrently populated cache and repair of missing derived members."""
from concurrent.futures import ThreadPoolExecutor
import errno
import json
from pathlib import Path
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mod_editor.core import nfl2k5_source_cache as cache
from mod_editor.core.errors import ValidationError


class CachePublication(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = SimpleNamespace(size=32, sha256="a" * 64)
        self.final = self.root / self.source.sha256
        self.cache = cache.Nfl2k5SourceCache(self.root)
        self.marker = {"schema": cache.CACHE_SCHEMA, "source": vars(self.source),
                       "packs": [{"name": n, "size": 1} for n in "0123456789ABCDEF"], "summary": {}}
        constants = patch.multiple(cache, PACK0_SIZE=1, INVENTORY_SIZE=2)
        constants.start()
        self.addCleanup(constants.stop)

    def stage(self, name):
        root = self.root / name
        root.mkdir(mode=0o700)
        folder = root / cache.PACK_FOLDER
        folder.mkdir(parents=True)
        for key in "0123456789ABCDEF":
            (folder / key).write_bytes(key.encode())
        inventory = root / cache.INVENTORY_RELATIVE
        inventory.parent.mkdir()
        inventory.write_bytes(b"{}")
        (root / "cache.json").write_text(json.dumps(self.marker))
        (root / "originals").mkdir()
        return root

    def publish(self, stage):
        return self.cache._publish_index(stage, self.final, self.source, self.marker, self.root / "game.iso", None)

    def test_two_healthy_publishers_adopt_one_verified_index(self):
        stages = (self.stage("first"), self.stage("second"))
        together = threading.Barrier(2)
        def worker(stage):
            together.wait(10)
            self.publish(stage)
        with patch.object(self.cache, "_verify_cached_source") as verify, ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [pool.submit(worker, stage) for stage in stages]
            for task in tasks:
                task.result(20)
            verify.assert_called_once()
        self.assertIsNotNone(self.cache._load_existing(self.final, self.source))

    def test_missing_pack_and_missing_directory_restore_without_disturbing_originals(self):
        self.publish(self.stage("initial"))
        original = self.final / "originals" / "my-project"
        original.write_bytes(b"user data")
        folder = self.final / cache.PACK_FOLDER
        retained = folder / "0"
        inode = retained.stat().st_ino
        (folder / "C").unlink()
        self.publish(self.stage("missing-pack"))
        self.assertEqual((folder / "C").read_bytes(), b"C")
        self.assertEqual(retained.stat().st_ino, inode)
        shutil.rmtree(self.final / "extracted")
        self.publish(self.stage("missing-folder"))
        self.assertEqual({p.name for p in folder.iterdir()}, set("0123456789ABCDEF"))
        self.assertEqual(original.read_bytes(), b"user data")
        self.assertIsNotNone(self.cache._load_existing(self.final, self.source))

    def test_foreign_directory_and_divergent_members_survive_the_refusal(self):
        self.final.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValidationError, "unrecognized"):
            self.publish(self.stage("unowned"))
        self.assertEqual(list(self.final.iterdir()), [])
        self.final.rmdir()
        self.publish(self.stage("initial"))
        folder = self.final / cache.PACK_FOLDER
        (folder / "0").unlink()
        (folder / "F").write_bytes(b"x")
        with self.assertRaisesRegex(ValidationError, "different contents"):
            self.publish(self.stage("changed"))
        self.assertEqual((folder / "F").read_bytes(), b"x")
        self.assertFalse((folder / "0").exists())

    def test_volume_without_atomic_directory_publish_and_retry(self):
        publish = cache.platform_compat.publish_no_replace
        def no_directory(staged, destination, *, is_directory=False):
            if is_directory:
                raise cache.platform_compat.NoReplacePublishUnavailable("no directory support")
            if not getattr(no_directory, "interrupted", False) and Path(destination).name == "C":
                no_directory.interrupted = True
                raise InterruptedError("interrupted after publishing earlier packs")
            return publish(staged, destination)
        with patch.object(cache.platform_compat, "publish_no_replace", side_effect=no_directory):
            with self.assertRaises(InterruptedError):
                self.publish(self.stage("interrupted"))
            self.assertIsNone(self.cache._load_existing(self.final, self.source))
            self.publish(self.stage("retry"))
        self.assertIsNotNone(self.cache._load_existing(self.final, self.source))

    def test_non_collision_io_error_is_preserved(self):
        with patch.object(cache.platform_compat, "publish_no_replace", side_effect=OSError(errno.EIO, "drive error")):
            with self.assertRaises(OSError) as result:
                self.publish(self.stage("bad-drive"))
        self.assertEqual(result.exception.errno, errno.EIO)
        self.assertFalse(self.final.exists())


if __name__ == "__main__":
    unittest.main()
