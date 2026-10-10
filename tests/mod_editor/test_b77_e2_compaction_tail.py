"""E2 (beta 77): the Build tab must never sit on a finished-looking "Compacting disc image" line.

Windows report (Davy, 2026-10-02, Basic preset, D:\\xemu\\...): the status read "Compacting disc image - 90112 of
90112 - about 0 s remaining" and the build never finished. 76.3 removed the quadratic move plan behind one cause. What
still looked like a hang after the last counted unit:

* every fragment was reported as its own "N of N" (one size per file, so each fragment end read as a finished phase
  and the time estimate had nothing to work with);
* the first thing after the last move was truncate + fsync of everything the OS had not yet written, with no label and
  no report for as long as the drive needed (minutes on a slow or external drive), then a full read-back;
* the swap of the rewritten image waited ten silent seconds for a scanner, and the final publish did not wait at all;
* Cancel was not noticed during the flush, the swap or the publish.

These tests run the Windows-only behaviour on every platform by flipping ``os.name`` or by raising the refusals
Windows gives (``winerror`` 5 and 32), and make the drive slow by sleeping inside ``os.fsync``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nfl2k5_xiso_fixture import dir_node  # noqa: E402
from mod_editor.core import image_use  # noqa: E402
from mod_editor.core import xdvdfs_compact as xc  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402


def nfl_image(path, files, physical, gaps=1):
    """The retail tree's shape (three executables, sixteen packs under vc_53450030) with files in `physical` order."""
    at, placed = 40 * xc.SECTOR, {}
    with path.open("wb") as out:
        for name in physical:
            placed[name] = (at // xc.SECTOR, len(files[name]))
            out.seek(at)
            out.write(files[name])
            at += xc.align(len(files[name])) + gaps * xc.SECTOR
        sub = dir_node(sorted(((placed[n][0], placed[n][1], 0x80, n.split("/")[1]) for n in files if "/" in n),
                              key=lambda row: row[3].casefold()))
        root = dir_node(sorted([(placed[n][0], placed[n][1], 0x80, n) for n in files if "/" not in n]
                               + [(34, len(sub), 0x10, "vc_53450030")], key=lambda row: row[3].casefold()))
        header = bytearray(xc.SECTOR)
        header[:20] = header[-20:] = xc.xiso.XDVDFS_MAGIC
        struct.pack_into("<II", header, 20, 33, len(root))
        for sector, data in ((32, header), (33, root), (34, sub)):
            out.seek(sector * xc.SECTOR)
            out.write(data)
        out.truncate(at + 64 * xc.SECTOR)
    return path


def payloads(path):
    with path.open("rb", buffering=0) as stream:
        layout = xc.read_layout(stream)
        return {k: xc.read_at(stream, e.byte_offset, e.size) for k, e in layout.entries.items()
                if not e.attributes & 0x10}


def digests(files):
    """Name -> (size, sha256). Compare these, never the bytes: a failing assertEqual on megabyte strings sends
    unittest's diff off for hours."""
    return {name: (len(data), hashlib.sha256(data).hexdigest()) for name, data in files.items()}


class Cancelled(Exception):
    """Stands in for the Build tab's BuildCancelled."""


class CompactionFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # 0.5 to 1.5 MiB per file: several 1 MiB blocks each, and a dump stored in the opposite order to retail so
        # nearly every file has to move.
        self.files = {name: bytes([i + 1]) * (xc.BLOCK // 2 * (i % 3 + 1) + 7 * i) for i, name in enumerate(xc.NFL_ORDER)}
        self.source = nfl_image(self.root / "source.iso", self.files, list(reversed(xc.NFL_ORDER)))
        self.private = self.root / "private.iso"
        self.private.write_bytes(self.source.read_bytes())
        self.events = []
        # The retail-order permutation of this dump needs thousands of steps and is refused by the 76.3 dry run; the
        # dump's own order (closing the gaps) needs about twenty. Make that refusal a step count, not two seconds.
        steps = mock.patch.object(xc, "IN_PLACE_MAX_STEPS", 300)
        steps.start()
        self.addCleanup(steps.stop)

    def progress(self, label, done=0, total=0):
        self.events.append((label, done, total))

    def groups(self):
        """Consecutive events with the same label, as (label, [(done, total), ...])."""
        out = []
        for label, done, total in self.events:
            if not out or out[-1][0] != label:
                out.append((label, []))
            out[-1][1].append((done, total))
        return out


class OneRunningTotalPerPhase(CompactionFixture):
    def test_every_phase_counts_against_its_whole_size(self):
        receipt = xc.finish_private(self.private, original=self.source, progress=self.progress)
        self.assertEqual(digests(payloads(self.private)), digests(self.files))
        self.assertEqual(receipt["scratch_disk_bytes"], 0)
        seen = [label for label, _ in self.groups()]
        self.assertEqual(seen, [xc.LABEL_PLAN, xc.LABEL_VERIFY, xc.LABEL_MOVE, xc.LABEL_FLUSH, xc.LABEL_VERIFY])
        for label, rows in self.groups():
            if label in (xc.LABEL_PLAN, xc.LABEL_FLUSH):
                self.assertEqual(rows[0], (0, 0), label)
                continue
            totals = {total for _, total in rows}
            self.assertEqual(len(totals), 1, f"{label}: one total for the whole phase, saw {sorted(totals)[:5]}")
            total = totals.pop()
            done = [d for d, _ in rows]
            self.assertEqual(done, sorted(done), f"{label}: the count never goes backwards")
            self.assertEqual(done[-1], total, f"{label}: the phase ends at its total")
            self.assertEqual([d for d in done if d == total], [total],
                             f"{label}: 'N of N' appears once, at the very end of the phase, not at every fragment")
        verify_totals = {rows[0][1] for label, rows in self.groups() if label == xc.LABEL_VERIFY}
        self.assertEqual(verify_totals, {sum(len(v) for v in self.files.values())},
                         "the read-back checks the same bytes the first pass hashed")

    def test_the_old_labels_no_longer_end_at_every_fragment(self):
        """Written with the 76.x label text only, so it runs (and fails) against the code before this change."""
        xc.finish_private(self.private, original=self.source, progress=self.progress)
        groups = [(label, rows) for label, rows in self.groups() if label in ("Verifying disc files", "Compacting disc image")]
        self.assertEqual([label for label, _ in groups], ["Verifying disc files", "Compacting disc image",
                                                          "Verifying disc files"])
        for label, rows in groups:
            self.assertEqual(len({total for _, total in rows}), 1,
                             f"{label} must count against one total, not each file's own size")
            self.assertEqual(sum(1 for done, total in rows if done == total), 1,
                             f"{label} must say 'N of N' once, when the phase is over")

    def test_rewrite_beside_reports_the_same_way_and_gives_the_same_bytes(self):
        reference = self.root / "reference.iso"
        xc.compact_copy(self.source, reference)          # the out-of-place retail-order result
        with mock.patch.object(xc, "_in_place_fits", lambda rows: False):
            receipt = xc.finish_private(self.private, original=self.source, progress=self.progress)
        self.assertEqual(self.private.read_bytes(), reference.read_bytes())
        self.assertEqual(receipt["order"], "nfl2k5-retail")
        self.assertEqual(receipt["scratch_disk_bytes"], receipt["output_bytes"])
        move = [rows for label, rows in self.groups() if label == xc.LABEL_MOVE]
        self.assertEqual(len(move), 1, "one uninterrupted compaction phase")
        self.assertEqual(len({total for _, total in move[0]}), 1)
        self.assertEqual(move[0][-1][0], move[0][-1][1])
        self.assertEqual(sum(1 for d, t in move[0] if d == t), 1)
        self.assertIn(xc.LABEL_FLUSH, [label for label, _ in self.groups()])
        self.assertEqual([label for label, _ in self.groups()][-1], xc.LABEL_VERIFY)


def flat_image(path, files, physical, gaps=3):
    """A flat XISO: the named files in `physical` order, `gaps` free sectors after each."""
    at, rows = 40 * xc.SECTOR, []
    with path.open("wb") as out:
        for name in physical:
            rows.append((at // xc.SECTOR, len(files[name]), 0x80, name))
            out.seek(at)
            out.write(files[name])
            at += xc.align(len(files[name])) + gaps * xc.SECTOR
        root = dir_node(sorted(rows, key=lambda row: row[3].casefold()))
        header = bytearray(xc.SECTOR)
        header[:20] = header[-20:] = xc.xiso.XDVDFS_MAGIC
        struct.pack_into("<II", header, 20, 33, len(root))
        out.seek(32 * xc.SECTOR)
        out.write(header)
        out.seek(33 * xc.SECTOR)
        out.write(root)
        out.truncate(at + 64 * xc.SECTOR)
    return path


class RunningTotalHoldsWhenMovesNeedTheCycleBuffer(unittest.TestCase):
    """A saved prefix is read once and written once, split moves partition the move: each byte is counted once."""

    def check(self, events, expected_total=None):
        move = [(d, t) for label, d, t in events if label == xc.LABEL_MOVE]
        self.assertTrue(move)
        totals = {t for _, t in move}
        self.assertEqual(len(totals), 1)
        total = totals.pop()
        if expected_total is not None:
            self.assertEqual(total, expected_total)
        done = [d for d, _ in move]
        self.assertEqual(done, sorted(done))
        self.assertEqual(done[-1], total)
        self.assertLessEqual(max(done), total)

    def test_two_files_that_swap_places_report_one_total_of_four_mebibytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = {"default.xbe": b"x" * (2 * xc.BLOCK), "a": b"a" * (2 * xc.BLOCK)}
            original = flat_image(root / "original.iso", files, list(files), gaps=0)
            staged = root / "staged.iso"
            xc.compact_copy(original, staged)
            with staged.open("r+b", buffering=0) as stream:       # swap the two adjacent extents in the directory
                layout = xc.read_layout(stream)
                a, b = [layout.entries[name] for name in files]
                for name, sector in (("default.xbe", b.sector), ("a", a.sector)):
                    parent, node = layout.nodes[name]
                    xc.write_at(stream, layout.directories[parent][0] + node, struct.pack("<I", sector))
            expected = digests(payloads(staged))      # after the swap the names carry each other's bytes
            self.assertNotEqual(expected, digests(files))
            events = []
            receipt = xc.finish_private(staged, original=original, progress=lambda *a: events.append(a))
            self.assertEqual(receipt["peak_cycle_buffer_bytes"], xc.BLOCK, "the cycle buffer really was needed")
            self.check(events, expected_total=4 * xc.BLOCK)
            self.assertEqual(digests(payloads(staged)), expected)

    def test_random_permutations_never_overcount_or_stall_the_total(self):
        import random
        rng = random.Random(20261007)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for case in range(25):
                names = ["default.xbe", "a", "b", "c", "d", "e"]
                files = {n: bytes([i + 1]) * (rng.randrange(1, 70) * xc.SECTOR - rng.randrange(0, 100))
                         for i, n in enumerate(names)}
                if case % 5 == 0:
                    files["a"] = bytes(range(256)) * (xc.BLOCK // 256 + 17)   # a file longer than one block
                original = flat_image(root / "original.iso", files, names, gaps=0)
                rng.shuffle(names)
                source = flat_image(root / "source.iso", files, names, gaps=case % 4)
                events = []
                xc.finish_private(source, original=original, progress=lambda *a: events.append(a))
                self.assertEqual(digests(payloads(source)), digests(files), case)
                if any(label == xc.LABEL_MOVE for label, _, _ in events):
                    self.check(events)


class TheTailAfterTheLastMoveIsLabelledAndAlive(CompactionFixture):
    """The drive is "slow" for exactly as long as it takes the progress helper to report PULSES times (never a fixed
    sleep, so a loaded CI machine cannot make these tests flaky; a helper that never reports fails after 20 s)."""

    PULSES = 5

    def slow_drive(self, enough):
        real = os.fsync

        def fsync(fd):
            self.events.append(("fsync", "start", 0))
            self.assertTrue(enough.wait(20), "the progress helper never reported while the flush was running")
            real(fd)
            self.events.append(("fsync", "end", 0))
        return fsync

    def helper_reports(self, enough, needed=PULSES, raise_in_helper=None):
        """A progress sink that records everything and sets `enough` once the helper thread has reported `needed` times
        (a helper that raises stops after its first report, so a cancelling sink needs exactly one)."""
        count = [0]

        def progress(label, done=0, total=0):
            self.events.append((label, done, total))
            if threading.current_thread().name == "compaction-progress":
                count[0] += 1
                if count[0] >= needed:
                    enough.set()
                if raise_in_helper is not None:
                    raise raise_in_helper("Build cancelled")
        return progress

    def test_the_final_flush_is_announced_first_and_pulses_while_the_drive_is_slow(self):
        enough = threading.Event()
        with mock.patch.object(xc, "PULSE_SECONDS", 0.01), mock.patch.object(xc.os, "fsync", self.slow_drive(enough)):
            xc.finish_private(self.private, original=self.source, progress=self.helper_reports(enough))
        starts = [i for i, e in enumerate(self.events) if e[:2] == ("fsync", "start")]
        self.assertEqual(len(starts), 1, "this small image needs only the final flush")
        start = starts[0]
        self.assertEqual(self.events[start - 1][0], xc.LABEL_FLUSH, "the label changes BEFORE the drive is made to wait")
        end = next(i for i in range(start, len(self.events)) if self.events[i][:2] == ("fsync", "end"))
        during = [e for e in self.events[start:end] if e[0] == xc.LABEL_FLUSH]
        self.assertGreaterEqual(len(during), self.PULSES, "the helper keeps reporting for as long as fsync runs")
        self.assertEqual(self.events[end + 1][0], xc.LABEL_VERIFY, "the read-back follows the flush directly")
        self.assertFalse([t for t in threading.enumerate() if t.name == "compaction-progress"],
                         "no helper thread outlives the flush")

    def test_cancel_during_a_slow_flush_is_raised_once_the_flush_returns(self):
        enough = threading.Event()
        progress = self.helper_reports(enough, needed=1, raise_in_helper=Cancelled)
        with mock.patch.object(xc, "PULSE_SECONDS", 0.01), mock.patch.object(xc.os, "fsync", self.slow_drive(enough)):
            with self.assertRaises(Cancelled):
                xc.finish_private(self.private, original=self.source, progress=progress)
        fsyncs = [e for e in self.events if e[0] == "fsync"]
        self.assertEqual(fsyncs[-1], ("fsync", "end", 0),
                         "the flush was allowed to finish, not abandoned mid-call with its file handle open")
        self.assertFalse([t for t in threading.enumerate() if t.name == "compaction-progress"])
        after_flush = [e[0] for e in self.events[[e[0] for e in self.events].index(xc.LABEL_FLUSH):]]
        self.assertNotIn(xc.LABEL_VERIFY, after_flush,
                         "cancelling stops the work; it does not go on to read the whole image back")


class TheSwapWaitsForAScannerAndSaysSo(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.staged, self.target = Path(self.temp.name, "staged"), Path(self.temp.name, "target")
        self.staged.write_bytes(b"new")
        self.target.write_bytes(b"old")
        self.sleeps, self.events = [], []

    def held(self):
        error = PermissionError(13, "The process cannot access the file because it is being used by another process")
        error.winerror = 32
        return error

    def test_a_minute_of_patience_with_a_report_for_every_wait(self):
        real, calls = os.replace, []

        def replace(a, b):
            calls.append(a)
            if len(calls) <= 100:  # 25 s of a real scanner: more than the ten seconds 76.3 allowed
                raise self.held()
            real(a, b)
        with mock.patch.object(xc.os, "replace", replace), mock.patch.object(xc.os, "name", "nt"), \
                mock.patch.object(xc.time, "sleep", self.sleeps.append):
            xc._replace_image(self.staged, self.target, lambda *a: self.events.append(a))
        self.assertEqual(self.target.read_bytes(), b"new")
        self.assertEqual(self.sleeps, [xc.REPLACE_WAIT_SECONDS] * 100)
        self.assertEqual(self.events, [(xc.LABEL_SWAP, 0, 0)] * 100)
        self.assertGreaterEqual(xc.REPLACE_ATTEMPTS * xc.REPLACE_WAIT_SECONDS, 60)

    def test_it_gives_up_with_a_plain_sentence_and_leaves_both_files(self):
        with mock.patch.object(xc.os, "replace", side_effect=self.held()), mock.patch.object(xc.os, "name", "nt"), \
                mock.patch.object(xc.time, "sleep", self.sleeps.append):
            with self.assertRaisesRegex(ValueError, "Windows is still holding the new disc image open.*Nothing was published"):
                xc._replace_image(self.staged, self.target)
        self.assertEqual(len(self.sleeps), xc.REPLACE_ATTEMPTS - 1)
        self.assertEqual((self.staged.read_bytes(), self.target.read_bytes()), (b"new", b"old"))

    def test_other_systems_do_not_wait(self):
        with mock.patch.object(xc.os, "replace", side_effect=PermissionError(13, "read-only")), \
                mock.patch.object(xc.os, "name", "posix"), mock.patch.object(xc.time, "sleep", self.sleeps.append):
            with self.assertRaises(PermissionError):
                xc._replace_image(self.staged, self.target)
        self.assertEqual(self.sleeps, [])


class ThePublishWaitsForAScannerToo(unittest.TestCase):
    """build() publishes the finished 6 GB image by renaming it; Windows refuses while a scanner has it open."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.staging, self.target = self.root / "stage.iso", self.root / "disc.iso"
        self.staging.write_bytes(b"finished disc")
        self.sleeps = []
        patch = mock.patch.object(image_use.time, "sleep", self.sleeps.append)
        patch.start()
        self.addCleanup(patch.stop)

    @staticmethod
    def refusal(code):
        error = PermissionError(13, "refused")
        error.winerror = code
        return error

    def flaky(self, real, failures):
        def call(*args, **kwargs):
            if failures:
                raise failures.pop(0)
            return real(*args, **kwargs)
        return call

    def test_new_output_is_published_once_the_scanner_lets_go(self):
        failures = [self.refusal(32), self.refusal(5), self.refusal(32)]
        with mock.patch.object(image_use, "publish_no_replace", self.flaky(image_use.publish_no_replace, failures)):
            image_use.publish_image(self.staging, self.target, None)
        self.assertEqual(self.target.read_bytes(), b"finished disc")
        self.assertFalse(self.staging.exists())
        self.assertEqual(self.sleeps, [image_use.PUBLISH_HELD_WAIT_SECONDS] * 3)

    def test_overwrite_is_published_once_the_scanner_lets_go(self):
        self.target.write_bytes(b"old disc")
        previous = image_use.check_image_destination(self.target, overwrite=True)
        failures = [self.refusal(32), self.refusal(32)]
        with mock.patch.object(image_use.os, "replace", self.flaky(os.replace, failures)):
            image_use.publish_image(self.staging, self.target, previous)
        self.assertEqual(self.target.read_bytes(), b"finished disc")
        self.assertEqual(self.sleeps, [image_use.PUBLISH_HELD_WAIT_SECONDS] * 2)

    def test_first_try_success_never_sleeps(self):
        image_use.publish_image(self.staging, self.target, None)
        self.assertEqual(self.sleeps, [])
        self.assertEqual(self.target.read_bytes(), b"finished disc")

    def test_refusals_that_waiting_cannot_cure_are_not_retried(self):
        for error in (PermissionError(13, "read-only folder"), FileExistsError(17, "exists"), self.refusal(183)):
            with self.subTest(error=repr(error)):
                with mock.patch.object(image_use, "publish_no_replace", side_effect=error):
                    with self.assertRaises(type(error)):
                        image_use.publish_image(self.staging, self.target, None)
                self.assertEqual(self.sleeps, [])

    def test_it_gives_up_with_a_plain_sentence_and_keeps_the_staged_disc(self):
        with mock.patch.object(image_use, "publish_no_replace", side_effect=self.refusal(32)):
            with self.assertRaisesRegex(ValidationError, "Windows is still holding the finished disc open.*disc.iso.*"
                                                         "Nothing was published"):
                image_use.publish_image(self.staging, self.target, None)
        self.assertEqual(len(self.sleeps), image_use.PUBLISH_HELD_ATTEMPTS - 1)
        self.assertGreaterEqual(image_use.PUBLISH_HELD_ATTEMPTS * image_use.PUBLISH_HELD_WAIT_SECONDS, 60)
        self.assertTrue(self.staging.exists() and not self.target.exists())


class TheBuildTabsTimeEstimateCountsTheCurrentStepOnly(unittest.TestCase):
    """"about N s remaining" was elapsed since the START OF THE BUILD scaled by what is left of this step."""

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_estimate_restarts_with_each_step(self):
        from mod_editor.gui.build_panel_qt import _Task
        clock, shown = [1000.0], []

        def operation(progress):
            for at, step in ((1000, ("Copying disc image", 0, 6000)), (1010, ("Copying disc image", 3000, 6000)),
                             (1600, ("Compacting disc image", 0, 5000)), (1610, ("Compacting disc image", 500, 5000)),
                             (1620, ("Saving the compacted disc to disk", 0, 0)),
                             (1630, ("Verifying disc files", 0, 6000)), (1640, ("Verifying disc files", 1000, 6000))):
                clock[0] = at
                progress(*step)
                shown.append(task.latest_progress)
        with mock.patch("time.monotonic", lambda: clock[0]):
            task = _Task(operation)
            task.run()
        self.assertEqual(shown[1], "Copying disc image • 3000 of 6000 • about 10 s remaining")
        # 10 s for the first tenth of the step: 90 s left. Counted from the start of the build (600 s ago) it said 5400.
        self.assertEqual(shown[3], "Compacting disc image • 500 of 5000 • about 90 s remaining")
        self.assertEqual(shown[4], "Saving the compacted disc to disk")
        self.assertEqual(shown[6], "Verifying disc files • 1000 of 6000 • about 50 s remaining")


class CopyBuildSummaryNamesWhereAStuckBuildIs(unittest.TestCase):
    """The reporter offered "any other details or logs" and sent a screenshot; the summary said only "in progress"."""

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_a_running_build_adds_its_last_progress_line_and_how_long_it_has_been_quiet(self):
        from types import SimpleNamespace
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui.build_panel_qt import BuildPanel
        panel = BuildPanel()
        try:
            panel._last_build_summary = "2K5 Mod Studio RC\nSelected: 11 changes\n\nBuild in progress."
            panel._task = SimpleNamespace(latest_progress="Saving the compacted disc to disk", started=100.0,
                                          last_update=290.0)
            with mock.patch("time.monotonic", lambda: 400.0):
                panel._copy_build_summary()
            copied = QApplication.clipboard().text()
            self.assertTrue(copied.startswith(panel._last_build_summary))
            self.assertTrue(copied.endswith("Still running: Saving the compacted disc to disk • 5:00 elapsed "
                                            "(last progress update 110 s ago)"), copied)
            panel._task = None                  # finished or failed: the summary is exactly what it was
            panel._copy_build_summary()
            self.assertEqual(QApplication.clipboard().text(), panel._last_build_summary)
        finally:
            panel._task = None
            panel.deleteLater()


class TheWholeBuildNeverGoesQuietAfterTheLastMove(unittest.TestCase):
    def test_real_build_reports_the_flush_right_after_the_last_compaction_tick(self):
        from mod_editor.core import mod_build
        from test_mod_build_performance import synthetic_disc
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder, "source.iso"), Path(folder, "out.iso")
            synthetic_disc(source)
            events = []
            with mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True}):
                receipt = mod_build.build(mod_build.BuildPlan(str(source), str(output)),
                                          lambda label, done=0, total=0: events.append((label, done, total)))
        self.assertGreater(receipt["disc_compaction"]["bytes_saved"], 0)
        labels = [e[0] for e in events]
        last_move = len(labels) - 1 - labels[::-1].index(xc.LABEL_MOVE)
        self.assertEqual(events[last_move][1], events[last_move][2])
        self.assertEqual(labels[last_move + 1], xc.LABEL_FLUSH,
                         "after the last counted unit the very next report names what the drive is doing")
        self.assertEqual(labels[last_move + 2], xc.LABEL_VERIFY)


if __name__ == "__main__":
    unittest.main()
