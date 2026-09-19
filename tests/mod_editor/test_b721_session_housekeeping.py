"""Beta 72.1: Mod Studio prunes only its own abandoned working-session folders.

Every opened disc or project made a new UUID folder under
``~/.local/share/2k5-mod-studio/sessions`` and none was ever removed (Coach
Edwards found dozens, full of copied textures). Stale folders never feed a new
session; pruning is housekeeping, and it must never touch anything else.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

from test_team_kit_bundle import _PngAssetIO
from mod_editor.studio import session as session_module
from mod_editor.studio.session import SESSION_SCHEMA, StudioSession, prune_stale_sessions

DAY = 24 * 60 * 60


def age(folder, seconds):
    stamp = time.time() - seconds
    for path in (folder / "session.json", folder / "replacements", folder / "undo", folder):
        if path.exists():
            os.utime(path, (stamp, stamp))


def stale_session(parent, *, days=30, manifest=True, session_id=None):
    name = str(uuid4())
    folder = parent / name
    (folder / "replacements").mkdir(parents=True)
    (folder / "undo").mkdir()
    (folder / "replacements" / "old-art.png").write_bytes(b"old texture")
    if manifest:
        (folder / "session.json").write_text(json.dumps(
            dict(schema=SESSION_SCHEMA, session_id=session_id or name, edits=[])))
    age(folder, days * DAY)
    return folder


class SessionHousekeepingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="b721-sessions-")
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name).resolve() / "sessions"
        self.parent.mkdir()

    def test_prunes_only_old_verified_sessions_and_keeps_the_newest(self):
        old = [stale_session(self.parent) for _ in range(3)]
        recent = stale_session(self.parent, days=1)
        kept = stale_session(self.parent)
        unrelated = [self.parent / "notes", self.parent / str(uuid4()),
                     stale_session(self.parent, session_id=str(uuid4()))]
        unrelated[0].mkdir()
        unrelated[1].mkdir()
        (unrelated[1] / "session.json").write_text("not json")
        age(unrelated[0], 90 * DAY)
        age(unrelated[1], 90 * DAY)
        stray = self.parent / "readme.txt"
        stray.write_text("user file")
        leftover = self.parent / ".pruning-interrupted"
        (leftover / "replacements").mkdir(parents=True)
        removed = prune_stale_sessions(self.parent, keep=(kept.name,), keep_newest=1)
        self.assertEqual(sorted(removed), sorted(folder.name for folder in old))
        self.assertTrue(all(not folder.exists() for folder in old))
        self.assertFalse(leftover.exists())
        for folder in (recent, kept, *unrelated, stray):
            self.assertTrue(folder.exists(), folder)
        # The most recently used sessions stay whatever their age.
        self.assertEqual(prune_stale_sessions(self.parent, keep_newest=5), ())

    @unittest.skipIf(os.name == "nt", "creating a directory link needs extra rights on Windows")
    def test_never_follows_a_link_out_of_the_sessions_folder(self):
        outside = stale_session(Path(tempfile.mkdtemp(dir=self.parent.parent)))
        link = self.parent / outside.name
        link.symlink_to(outside, target_is_directory=True)
        self.assertEqual(prune_stale_sessions(self.parent, keep_newest=0), ())
        self.assertTrue((outside / "replacements" / "old-art.png").is_file())

    def test_a_new_session_never_reads_stale_folders(self):
        for _ in range(4):
            folder = stale_session(self.parent)
            (folder / "replacements" / "tampered.png").write_bytes(b"stale")
            age(folder, 30 * DAY)
        cache = SimpleNamespace(source=SimpleNamespace(sha256="a" * 64), root=self.parent.parent / "cache")
        with patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", _PngAssetIO):
            fresh = StudioSession(cache, SimpleNamespace(), root=self.parent)
        self.assertEqual(fresh.modified_count, 0)
        self.assertEqual(sorted(p.name for p in fresh.root.iterdir()), ["replacements", "session.json", "undo"])
        self.assertEqual(list(fresh.replacements.iterdir()), [])
        # A session made in this process is never pruned, even if idle.
        age(fresh.root, 60 * DAY)
        removed = prune_stale_sessions(self.parent, keep_newest=0)
        self.assertEqual(len(removed), 4)
        self.assertTrue(fresh.root.is_dir())

    def test_launcher_housekeeps_the_default_folder_once_in_the_background(self):
        old = stale_session(self.parent)
        recent = [stale_session(self.parent, days=0) for _ in range(5)]
        with patch.object(session_module, "default_session_root", return_value=self.parent), \
                patch.object(session_module, "_PRUNED_PARENTS", set()):
            thread = session_module.start_session_housekeeping()
            thread.join(10)
            self.assertIsNone(session_module.start_session_housekeeping())
        self.assertFalse(old.exists())
        self.assertTrue(all(folder.is_dir() for folder in recent))
        # Only the real Studio launch housekeeps; tools and tests never do.
        import inspect
        from mod_editor.gui.studio_qt import launch_studio
        self.assertIn("start_session_housekeeping()", inspect.getsource(launch_studio))
        self.assertNotIn("housekeeping", inspect.getsource(StudioSession.__init__))

if __name__ == "__main__":
    unittest.main()
