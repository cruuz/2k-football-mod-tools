"""b780 Q52: a recovery snapshot of a big project never freezes the window.

Every Build-tab change asks for a recovery snapshot, and save_recovery_project / save_project held the facade lock
while the whole .2k5mod was written (STUDIO1: 3,000 tiny edits 1.0 s, 13,000 edits 4.1 s per snapshot), so the GUI
thread's own reads of modified_count and modified_asset_ids waited the whole time. These tests write a real archive
of synthetic 32x32 edits on a worker thread and time the GUI-side calls made meanwhile; the recovery file must still
be complete and loadable. UXFIX_BIG_EDITS sets the edit count (default 3,000; the proof run used 13,000).
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_build_settings as saved  # noqa: E402
from mod_editor.studio import project_archive as archive  # noqa: E402
from mod_editor.studio.facade import Nfl2k5StudioFacade  # noqa: E402

EDITS = int(os.environ.get("UXFIX_BIG_EDITS", "3000"))
_APP = None
SHA = "a" * 64


class _Session:
    """The parts of a StudioSession the GUI reads, writing a real archive of the corpus edits."""

    def __init__(self, corpus) -> None:
        self.corpus = corpus
        self.modified_count = len(corpus.edits)
        self.modified_asset_ids = frozenset(edit.asset_id for edit in corpus.edits)
        self.labeled_audio_asset_ids = frozenset()
        self.project_metadata_count = 1
        self.can_undo = True
        self._build_settings = saved.build_settings({})
        self.writing = threading.Event()
        self.written = threading.Event()
        self.write_seconds = 0.0

    @property
    def build_settings(self):
        return dict(self._build_settings)

    def set_build_settings(self, value):
        self._build_settings = saved.build_settings(value)

    def save_shareable_project(self, destination, *, replace=False, allow_empty=False, expected_target=None):
        started = time.perf_counter()
        self.writing.set()
        path = archive.save_project_archive(catalog=self.corpus.catalog, asset_io=self.corpus.io(),
                                            edits=self.corpus.edits, destination=destination,
                                            replace=replace, allow_empty=allow_empty,
                                            build_settings=self.build_settings)
        time.sleep(0.5)       # a slow disk: the hold always outlasts the reads, even on a fast CI machine
        self.write_seconds = time.perf_counter() - started
        self.written.set()
        return path


class RecoveryWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from b71_t5_project_probe import Corpus
        cls.folder = tempfile.TemporaryDirectory(prefix="uxfix-q52-")
        cls.root = Path(cls.folder.name)
        started = time.perf_counter()
        cls.corpus = Corpus(cls.root, EDITS)
        cls.corpus_seconds = time.perf_counter() - started

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def _facade(self):
        facade = Nfl2k5StudioFacade(uniform_catalog=object(), xemu_command=("xemu",), process_launcher=mock.Mock())
        session = _Session(self.corpus)
        facade._session = session
        facade._cache = SimpleNamespace(source=SimpleNamespace(sha256=SHA, selected_path=self.root / "game.iso"))
        return facade, session

    def test_gui_reads_never_wait_for_a_recovery_snapshot_and_the_snapshot_loads(self):
        facade, session = self._facade()
        target = self.root / "recovery.2k5mod"
        errors = []

        def write():
            try:
                facade.save_recovery_project(target, SHA, lambda *_: None)
            except Exception as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        worker = threading.Thread(target=write)
        worker.start()
        self.assertTrue(session.writing.wait(60))
        slowest, calls = 0.0, 0
        choice = {**saved.build_settings({}), "team_names_2026": True}
        stored_during_write = False
        while worker.is_alive():
            for read in (lambda: facade.modified_count, lambda: set(facade.modified_asset_ids),
                         lambda: facade.project_metadata_count, lambda: facade.can_undo,
                         lambda: facade.labeled_audio_asset_ids, lambda: facade.source_ready,
                         lambda: facade.source_path, lambda: facade.source_sha256,
                         facade.project_build_settings):
                started = time.perf_counter()
                read()
                slowest = max(slowest, time.perf_counter() - started)
                calls += 1
            if not stored_during_write:
                started = time.perf_counter()
                facade.set_project_build_settings(choice)       # a Build-tab change during the write
                slowest = max(slowest, time.perf_counter() - started)
                stored_during_write = worker.is_alive()
                if stored_during_write:
                    self.assertTrue(facade.project_build_settings()["team_names_2026"])   # its own change shows
            time.sleep(0.005)
        worker.join()
        self.assertEqual(errors, [])
        print(f"\nQ52: {EDITS} edits, snapshot written in {session.write_seconds:.2f} s; "
              f"{calls} GUI reads meanwhile, slowest {slowest * 1000:.1f} ms", file=sys.stderr)
        self.assertGreater(session.write_seconds, 0.2)          # the reads really ran beside a long write
        self.assertGreater(calls, 20)
        self.assertLess(slowest, 0.25)                          # was the whole write (1.0 s at 3,000, 4.1 s at 13,000)
        self.assertTrue(stored_during_write)
        self.assertTrue(session.build_settings["team_names_2026"])   # stored when the write ended
        loaded = archive.load_project_archive(source=target, catalog=self.corpus.catalog, asset_io=self.corpus.io(),
                                              private_root=self.root / f"loaded-{time.monotonic_ns()}")
        self.assertEqual(len(loaded.edits), EDITS)              # the recovery file is complete and loadable

    def test_a_change_still_waits_for_the_write_and_a_bad_choice_is_refused_at_once(self):
        facade, session = self._facade()
        target = self.root / "named.2k5mod"
        worker = threading.Thread(target=lambda: facade.save_project(target, lambda *_: None, replace=True))
        worker.start()
        self.assertTrue(session.writing.wait(60))
        if worker.is_alive():
            with self.assertRaises(Exception):
                facade.set_project_build_settings({"not_a_build_option": True})
        locked = []

        def change():                                            # any other change still waits for the writer
            with facade._lock:
                locked.append(session.written.is_set())

        changer = threading.Thread(target=change)
        changer.start()
        worker.join()
        changer.join()
        self.assertEqual(locked, [True])                        # it got the lock only after the archive was written
        self.assertTrue(target.is_file())


class QuietAutosaveTests(unittest.TestCase):
    def test_a_big_project_autosaves_after_a_quiet_period(self):
        from PyQt5.QtCore import QObject
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui import studio_qt
        global _APP
        _APP = QApplication.instance() or QApplication([])      # kept referenced for the timer

        class Host(QObject):
            _recovery_waits_for_quiet = studio_qt.StudioMainWindow._recovery_waits_for_quiet
            _recovery_quiet_elapsed = studio_qt.StudioMainWindow._recovery_quiet_elapsed

            def __init__(self, count):
                super().__init__()
                self.facade = SimpleNamespace(modified_count=count)
                self.saved = 0

            def _save_recovery_snapshot(self):
                if not self._recovery_waits_for_quiet():
                    self.saved += 1

        small = Host(studio_qt.AUTOSAVE_QUIET_EDITS - 1)
        small._save_recovery_snapshot()
        self.assertEqual(small.saved, 1)                         # a normal project autosaves at once, as before
        big = Host(13000)
        for _ in range(5):                                       # five Build-tab changes in a row
            big._save_recovery_snapshot()
        self.assertEqual(big.saved, 0)
        self.assertTrue(big._recovery_quiet_timer.isActive())
        self.assertEqual(big._recovery_quiet_timer.interval(), studio_qt.AUTOSAVE_QUIET_MS)
        big._recovery_quiet_timer.stop()
        big._recovery_quiet_elapsed()                            # 15 quiet seconds later: one snapshot
        self.assertEqual(big.saved, 1)


if __name__ == "__main__":
    unittest.main()
