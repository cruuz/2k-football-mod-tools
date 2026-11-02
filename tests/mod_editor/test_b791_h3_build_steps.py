"""b791-h3: every build failure names its step and resource; a visual step that fails is left out, restored exactly.

Coach Edwards' beta-79 builds ran 4 to 5 hours and ended with one line and no step ("cannot keep the retail scratch
word:"). These tests prove, on synthetic images only (no game data):

* an error leaving a build reads "During <step> (<resource>): <message>", keeps the original as ``__cause__`` and
  ``.original`` and stays in its exception family (callers that catch ValueError or OSError behave as before);
* an optional step that raises in the middle of its writes leaves the copy byte-for-byte as it was (the real
  OuterImage writer under both of its import names, the descriptor writes of a Windows-style seek/write, growth past
  the end, shortening, sidecar receipts), the receipt rolls back and gets one plain note, and the build goes on;
* writes the journal cannot see (a buffered writer, a forked worker) stop the build instead of being "left out";
* a whole ``mod_build.build`` with a failing kit pass finishes with the note and the same disc bytes as a build
  without it; a failing core step still stops, with its step;
* the build log, the errors.log entry and the diagnostic zip say what happened and hold text only (never the
  source disc's bytes or a texture), with Windows-safe names.
"""
from __future__ import annotations

import ast
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import build_report, build_steps, mod_build, platform_compat  # noqa: E402
from mod_editor.core.nfl2k5_project_fit import BuildCancelled  # noqa: E402


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _random(size: int, seed: int) -> bytes:
    import random
    return random.Random(seed).randbytes(size)


class StepContextTests(unittest.TestCase):
    def test_an_error_names_its_step_resource_and_keeps_the_original(self):
        with self.assertRaises(ValueError) as caught:
            with build_steps.track() as session:
                build_steps.begin("modern_surfaces")
                session.progress("Modern surfaces: 117 of 288 bundles", 117, 288)
                with build_steps.resource("s13ad.iff"):
                    raise ValueError("cannot keep the retail scratch word:")
        exc = caught.exception
        self.assertIsInstance(exc, build_steps.StepFailure)
        self.assertEqual(str(exc), "During Modern playing surfaces (s13ad.iff): cannot keep the retail scratch word:")
        self.assertEqual((exc.step, exc.label, exc.resource), ("modern_surfaces", "Modern playing surfaces", "s13ad.iff"))
        self.assertIs(exc.__cause__, exc.original)
        self.assertEqual(str(exc.original), "cannot keep the retail scratch word:")
        self.assertEqual(exc.last_progress, "Modern surfaces: 117 of 288 bundles")
        failure = session.tracker.failure
        self.assertEqual(failure["reason"], "cannot keep the retail scratch word (the step gave no reason)")
        self.assertIn('raise ValueError("cannot keep the retail scratch word:")', failure["traceback"])
        self.assertEqual(session.tracker.result, "failed")

    def test_wrapped_errors_stay_in_their_family(self):
        cases = [OSError(28, "No space left on device", "/out/disc.iso"), FileNotFoundError(2, "gone", "x.iso"),
                 KeyError("s13"), IndexError("chunk 51"), RuntimeError("late owner"), TypeError("bad"),
                 PermissionError(13, "denied", "x")]
        for original in cases:
            with self.subTest(type(original).__name__):
                with self.assertRaises(type(original)) as caught:
                    with build_steps.track():
                        build_steps.begin("copy")
                        raise original
                exc = caught.exception
                self.assertIsInstance(exc, build_steps.StepFailure)
                self.assertTrue(str(exc).startswith("During the copy of your game disc: "), str(exc))
                if isinstance(original, OSError):
                    self.assertEqual((exc.errno, exc.filename), (original.errno, original.filename))
        class Custom(ValueError):
            pass

        class Sentinel(Exception):
            def __init__(self, required, *, also):          # a constructor the wrapper must not call
                super().__init__(required)
                self.selector, self.also = required, also

        with self.assertRaises(Custom) as caught:
            with build_steps.track():
                raise Custom("x")
        self.assertIsInstance(caught.exception, build_steps.StepFailure)
        with self.assertRaises(Sentinel) as caught:
            with build_steps.track():
                build_steps.begin("moment_kits")
                raise Sentinel("14H9", also=1)
        exc = caught.exception
        self.assertEqual(str(exc), "During the Anniversary moment kit pass: 14H9")
        self.assertEqual((exc.selector, exc.also), ("14H9", 1))      # the original's attributes are kept
        from mod_editor.core.errors import ValidationError
        with self.assertRaises(ValidationError):
            with build_steps.track():
                raise ValidationError("The artwork recipe needs attention before building")

    def test_a_cancel_and_a_keyboard_interrupt_are_never_wrapped(self):
        cancel = BuildCancelled("Build cancelled; no output was published.")
        with self.assertRaises(BuildCancelled) as caught:
            with build_steps.track() as session:
                build_steps.begin("project")
                raise cancel
        self.assertIs(caught.exception, cancel)
        self.assertEqual(session.tracker.result, "cancelled")
        with self.assertRaises(KeyboardInterrupt):
            with build_steps.track():
                raise KeyboardInterrupt()

    def test_scoped_helpers_name_their_step_and_quiet_ones_leave_no_noise(self):
        @build_steps.scoped("qb_accuracy")
        def quiet():
            return 7

        @build_steps.scoped("star_career")
        def failing():
            raise ValueError("cave refused")

        with self.assertRaises(ValueError) as caught:
            with build_steps.track() as session:
                build_steps.begin("xbe_space")
                self.assertEqual(quiet(), 7)
                failing()
        self.assertEqual(str(caught.exception), "During Rookie stars and career stars: cave refused")
        ids = [entry["id"] for entry in session.tracker.steps]
        self.assertNotIn("qb_accuracy", ids)          # returned at once: not listed
        self.assertIn("star_career", ids)             # failed: listed
        self.assertEqual(quiet.__wrapped__.__name__, "quiet")

    def test_nested_entry_points_reuse_the_outer_tracker_and_wrap_once(self):
        lines = []
        with self.assertRaises(RuntimeError) as caught:
            with build_steps.track(lambda m, d=0, t=0: lines.append(m)) as outer:
                with build_steps.track(outer.progress) as inner:
                    self.assertIs(inner.tracker, outer.tracker)
                    self.assertFalse(inner.owner)
                    build_steps.begin("hash")
                    inner.progress("Hashing the verified disc", 0, 0)
                    raise RuntimeError("short read")
        self.assertEqual(str(caught.exception), "During the final check of the finished disc: short read")
        self.assertNotIsInstance(caught.exception.original, build_steps.StepFailure)
        self.assertIn("Hashing the verified disc", lines)

    def test_progress_lines_collapse_repeated_counters_and_keep_the_latest(self):
        tracker = build_steps.Tracker()
        progress = tracker.recording(None)
        for index in range(1, 13341):
            progress(f"Preparing Project edit index {index} of 13340", index, 13340)
        progress("Copying the image", 0, 0)
        lines = tracker.lines()
        self.assertEqual(len(lines), 2, lines)
        self.assertIn("Preparing Project edit index 13340 of 13340 [13340/13340] (and 13339 more like it)", lines[0])
        self.assertTrue(lines[1].endswith("Copying the image"))
        self.assertEqual(tracker.calls, 13341)

    def test_every_step_mod_build_marks_has_a_label(self):
        source = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        import re
        ids = set(re.findall(r'_step\("([a-z0-9_]+)"', source)) | set(re.findall(r'@_core_step\("([a-z0-9_]+)"\)', source))
        ids |= set(re.findall(r'_optional\(receipt, target, progress, "([a-z0-9_]+)"', source))
        self.assertGreater(len(ids), 120)
        self.assertEqual(sorted(ids - set(build_steps.STEP_LABELS)), [])
        for step_id in re.findall(r'_optional\(receipt, target, progress, "([a-z0-9_]+)"', source):
            label = build_steps.label_of(step_id)
            self.assertNotIn("—", label)
            self.assertTrue(build_steps.KEPT.get(step_id, build_steps.DEFAULT_KEPT).startswith("Your "), step_id)

    def test_the_build_entry_points_are_tracked(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder, "same.xbe")
            source.write_bytes(b"x" * 64)
            with self.assertRaises(ValueError) as caught:
                mod_build.build(mod_build.BuildPlan(str(source), str(source)))
        self.assertIsInstance(caught.exception, build_steps.StepFailure)
        self.assertEqual(caught.exception.step, "preflight")
        self.assertIn("During the checks before the build: ", str(caught.exception))
        self.assertIn("target must not be the source", str(caught.exception))


class SyntheticImage:
    """A synthetic XDVDFS image with a vc_53450030 outer archive (tests/nfl2k5_xiso_fixture), plus sidecars."""

    def __init__(self, folder: Path):
        from nfl2k5_xiso_fixture import SyntheticXiso
        entries = [(0x1111, _random(0x1800, 1)), (0x2222, _random(0x2300, 2)), (0x3333, _random(0x1000, 3))]
        self.fixture = SyntheticXiso(folder, entries)
        self.path = self.fixture.path
        self.colour = Path(str(self.path) + ".colour.json")
        self.colour.write_text('{"settings": "before"}\n', encoding="utf-8", newline="\n")
        self.before = sha(self.path)
        self.size = self.path.stat().st_size
        self.colour_before = self.colour.read_bytes()


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        self.image = SyntheticImage(self.folder)
        self.receipt = {"steps": [{"step": "copy"}], "result": {"modern_color": "retail"}, "plan": {"x": 1}}
        self.notes = []

    def _progress(self, message, done=0, total=0):
        self.notes.append(message)

    def _assert_restored(self):
        self.assertEqual(sha(self.image.path), self.image.before)
        self.assertEqual(self.image.path.stat().st_size, self.image.size)
        self.assertEqual(self.image.colour.read_bytes(), self.image.colour_before)
        self.assertFalse(build_steps.hooks_installed())
        leftovers = sorted(p.name for p in self.folder.iterdir() if p.name.startswith(".studio-undo-"))
        self.assertEqual(leftovers, [])

    def test_a_step_that_raises_mid_write_is_restored_byte_exact_and_noted(self):
        from tools import nfl2k5_playbook_position_recode as packaged
        import nfl2k5_playbook_position_recode as loose
        self.assertIsNot(packaged.OuterImage, loose.OuterImage)          # two module identities, both journaled
        with build_steps.optional(self.receipt, self.image.path, self._progress, "modern_surfaces"):
            for module, fill in ((packaged, b"\xaa"), (loose, b"\x55")):
                with module.OuterImage(self.image.path, writable=True) as archive:
                    entry = archive.entries[1]
                    archive.write(entry.virtual_offset + 7, fill * 0x900)       # unaligned, inside an entry
            fd = os.open(self.image.path, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                os.lseek(fd, 0x10000 + 3, os.SEEK_SET)                          # the Windows-style seek + write
                os.write(fd, b"\x00" * 5000)
                platform_compat.pwrite(fd, b"\x77" * 9000, self.image.size - 100)  # grows past the end
            finally:
                os.close(fd)
            Path(str(self.image.path) + ".surfaces.json").write_text("{}\n", encoding="utf-8", newline="\n")
            self.image.colour.write_text('{"settings": "after"}\n', encoding="utf-8", newline="\n")
            self.receipt["steps"].append({"step": "modern_surfaces", "state": "applied"})
            self.receipt["result"]["modern_surfaces"] = "applied"
            self.receipt["surfaces_extra"] = True
            raise ValueError("cannot keep the retail scratch word:")
        self._assert_restored()
        self.assertFalse(Path(str(self.image.path) + ".surfaces.json").exists())
        self.assertEqual(self.receipt["result"], {"modern_color": "retail"})
        self.assertNotIn("surfaces_extra", self.receipt)
        row = self.receipt["left_out"][0]
        self.assertEqual((row["step"], row["status"]), ("modern_surfaces", "left_out"))
        self.assertEqual(self.receipt["steps"][-1], row)
        note = ("Modern playing surfaces was left out: cannot keep the retail scratch word (the step gave no reason). "
                "Your disc keeps the playing surfaces as they were.")
        self.assertEqual(row["user_notes"], [note])
        self.assertEqual(self.receipt["user_notes"], [note])
        self.assertIn(note, self.notes)
        self.assertTrue(row["restored"]["changed"])
        self.assertTrue(build_steps.left_out(self.receipt, "modern_surfaces"))

    def test_shortening_the_copy_is_undone_too(self):
        with build_steps.optional(self.receipt, self.image.path, None, "super_bowl_hosts"):
            fd = os.open(self.image.path, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                os.ftruncate(fd, self.image.size - 70000)
            finally:
                os.close(fd)
            raise RuntimeError("Super Bowl host pack read-back")
        self._assert_restored()

    def test_a_descriptor_only_transaction_is_journaled(self):
        namespace = {"__name__": "mod_editor.core.nfl2k5_historic_styles", "Path": Path, "io": platform_compat}
        exec("def rewrite_archive(path, data, at):\n"
             "    with Path(path).open('r+b') as writer:\n"
             "        io.pwrite(writer.fileno(), data, at)\n", namespace)
        with build_steps.optional(self.receipt, self.image.path, None, "moment_kits"):
            namespace["rewrite_archive"](self.image.path, b"\x13" * 4096, 0x9000)
            namespace["rewrite_archive"](self.image.path, b"\x14" * 4096, self.image.size + 2048)
            raise ValueError("the rewritten archive failed its read-back")
        self._assert_restored()
        self.assertEqual(self.receipt["left_out"][0]["step"], "moment_kits")

    def test_a_buffered_writer_cannot_be_undone_so_the_build_stops(self):
        with self.assertRaises(RuntimeError) as caught:
            with build_steps.optional(self.receipt, self.image.path, None, "indicator_names"):
                with open(self.image.path, "r+b") as stream:
                    stream.seek(100)
                    stream.write(b"zz")
                raise RuntimeError("font does not fit")
        self.assertIn("a buffered writer opened the copy", caught.exception._studio_undo)
        self.assertEqual(caught.exception._studio_step[0], "indicator_names")
        self.assertNotIn("left_out", self.receipt)
        self.assertFalse(build_steps.hooks_installed())

    @unittest.skipUnless("fork" in multiprocessing.get_all_start_methods(), "needs fork-start workers")
    def test_a_worker_process_that_writes_the_copy_stops_the_build(self):
        path = str(self.image.path)
        with self.assertRaises(ValueError) as caught:
            with build_steps.optional(self.receipt, self.image.path, None, "modern_venues_2026"):
                process = multiprocessing.get_context("fork").Process(target=_child_writes, args=(path,))
                process.start()
                process.join(60)
                self.assertEqual(process.exitcode, 0)
                raise ValueError("a venue does not fit")
        self.assertIn("a worker process wrote the copy", caught.exception._studio_undo)

    def test_a_cancel_inside_an_optional_step_is_not_left_out(self):
        with self.assertRaises(BuildCancelled):
            with build_steps.optional(self.receipt, self.image.path, None, "modern_fans"):
                raise BuildCancelled("Build cancelled; no output was published.")
        self.assertNotIn("left_out", self.receipt)

    def test_strict_mode_stops_on_an_optional_step(self):
        with mock.patch.dict(os.environ, {build_steps.STRICT_ENV: "1"}):
            with self.assertRaises(ValueError) as caught:
                with build_steps.optional(self.receipt, self.image.path, None, "modern_fans"):
                    raise ValueError("crowd does not fit")
        self.assertIn(build_steps.STRICT_ENV, caught.exception._studio_undo)
        self.assertFalse(build_steps.hooks_installed())

    def test_a_step_left_out_takes_the_steps_that_build_on_it_with_it(self):
        with build_steps.optional(self.receipt, self.image.path, None, "modern_metlife"):
            raise ValueError("Giants field does not fit")
        with build_steps.optional(self.receipt, self.image.path, None, "modern_metlife_model") as step:
            step.require("modern_metlife")
            raise AssertionError("never runs")
        rows = self.receipt["left_out"]
        self.assertEqual([r["step"] for r in rows], ["modern_metlife", "modern_metlife_model"])
        self.assertEqual(rows[1]["user_notes"][0],
                         "The Modern MetLife model was left out: it builds on Modern MetLife Stadium, which was left "
                         "out. Your disc keeps the Giants and Jets stadium model as it was.")

    def test_success_keeps_every_byte_the_step_wrote(self):
        with build_steps.optional(self.receipt, self.image.path, None, "modern_fans"):
            fd = os.open(self.image.path, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                platform_compat.pwrite(fd, b"\x42" * 10, 0x9000)
            finally:
                os.close(fd)
        with open(self.image.path, "rb") as stream:
            stream.seek(0x9000)
            self.assertEqual(stream.read(10), b"\x42" * 10)
        self.assertNotIn("left_out", self.receipt)
        self.assertFalse(build_steps.hooks_installed())

    def test_a_wrapper_kept_by_code_imported_during_a_step_still_writes_afterwards(self):
        # multiprocessing.connection binds os.write when it is first imported; if that happens inside an optional
        # step it keeps the journaled wrapper after the step. That wrapper must still write (it once raised KeyError).
        with build_steps.optional(self.receipt, self.image.path, None, "modern_fans"):
            kept_write, kept_pwrite = os.write, getattr(os, "pwrite", None)
        self.assertFalse(build_steps.hooks_installed())
        self.assertIsNot(os.write, kept_write)
        read, write = os.pipe()
        try:
            self.assertEqual(kept_write(write, b"ok"), 2)
            self.assertEqual(os.read(read, 2), b"ok")
        finally:
            os.close(read)
            os.close(write)
        if kept_pwrite is not None:
            fd = os.open(self.image.path, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                self.assertEqual(kept_pwrite(fd, b"\x01", 0x9000), 1)
            finally:
                os.close(fd)

    def test_a_named_resource_goes_into_the_note(self):
        with build_steps.optional(self.receipt, self.image.path, None, "sideline_2026"):
            with build_steps.resource("14H9.IFF splayer"):
                raise ValueError("cannot keep the retail scratch word: padding 9, needs 12, retail 8")
        self.assertEqual(self.receipt["left_out"][0]["user_notes"][0],
                         "The 2026 sideline uniform repair was left out: 14H9.IFF splayer: cannot keep the retail "
                         "scratch word: padding 9, needs 12, retail 8. Your disc keeps those uniforms as they were.")

    def test_no_room_for_the_undo_copy_means_the_step_stops_instead_of_being_left_out(self):
        from collections import namedtuple
        usage = namedtuple("usage", "total used free")(10 ** 9, 10 ** 9, 4096)
        with mock.patch.object(build_steps, "MEMORY_BUDGET", 0), mock.patch("shutil.disk_usage", return_value=usage):
            with self.assertRaises(ValueError) as caught:
                with build_steps.optional(self.receipt, self.image.path, None, "modern_fans"):
                    fd = os.open(self.image.path, os.O_RDWR | getattr(os, "O_BINARY", 0))
                    try:
                        platform_compat.pwrite(fd, b"\x01" * 50000, 0x1000)
                    finally:
                        os.close(fd)
                    raise ValueError("fans do not fit")
        self.assertIn("no room on the output drive to keep the undo copy", caught.exception._studio_undo)
        self.assertNotIn("left_out", self.receipt)
        self.assertFalse(build_steps.hooks_installed())

    def test_the_memory_budget_spills_to_a_file_beside_the_copy_and_still_restores(self):
        with mock.patch.object(build_steps, "MEMORY_BUDGET", 20000):
            with build_steps.optional(self.receipt, self.image.path, None, "modern_color_bundles"):
                fd = os.open(self.image.path, os.O_RDWR | getattr(os, "O_BINARY", 0))
                try:
                    platform_compat.pwrite(fd, b"\x99" * 90000, 0x1000)
                finally:
                    os.close(fd)
                raise ValueError("grade failed")
        self._assert_restored()


def _fail_for_bundle(task):
    if task[0] == "s13ad.iff":
        raise ValueError("cannot keep the retail scratch word: padding 9, needs 12, retail 8")
    return task[0]


class PoolRunnerResourceTests(unittest.TestCase):
    """The two pool runners name the bundle a failed task was working on (the task's first item)."""

    def test_ordered_map_names_the_failing_task_and_never_the_consumer(self):
        from mod_editor.core import nfl2k5_late_steps as late
        tasks = [("s12ad.iff", 1), ("s13ad.iff", 2), ("s14ad.iff", 3)]
        with self.assertRaises(ValueError) as caught:
            list(late.ordered_map(_fail_for_bundle, tasks, 1))
        self.assertEqual(caught.exception._studio_resource, "s13ad.iff")
        results = late.ordered_map(_fail_for_bundle, [("s12ad.iff", 1)], 1)
        with self.assertRaises(KeyError) as caught:
            for _result in results:
                raise KeyError("the consumer's own error")
        self.assertIsNone(getattr(caught.exception, "_studio_resource", None))
        with self.assertRaises(ZeroDivisionError) as caught:      # an unnamed task carries no resource
            list(late.ordered_map(lambda task: 1 / 0, [(1, 2)], 1))
        self.assertIsNone(getattr(caught.exception, "_studio_resource", None))

    @unittest.skipUnless(multiprocessing.get_start_method(allow_none=True) in (None, "fork")
                         and "fork" in multiprocessing.get_all_start_methods(), "pooled path needs fork-start workers")
    def test_ordered_map_pool_names_the_failing_task(self):
        from mod_editor.core import nfl2k5_late_steps as late
        tasks = [(f"s{index:02d}dd.iff", index) for index in range(8)] + [("s13ad.iff", 99)]
        with self.assertRaises(ValueError) as caught:
            list(late.ordered_map(_fail_for_bundle, tasks, 3))
        self.assertEqual(caught.exception._studio_resource, "s13ad.iff")

    def test_run_jobs_names_the_failing_bundle(self):
        from mod_editor.core import nfl2k5_modern_metlife as metlife
        jobs = [("s12ad.iff", b""), ("s13ad.iff", b"")]
        with self.assertRaises(ValueError) as caught:
            metlife.run_jobs(_fail_for_bundle, jobs, workers=1)
        self.assertEqual(caught.exception._studio_resource, "s13ad.iff")
        with self.assertRaises(ValueError) as caught:
            with build_steps.track():
                build_steps.begin("modern_lambeau")
                metlife.run_jobs(_fail_for_bundle, jobs, workers=1, label="Lambeau Field")
        self.assertTrue(str(caught.exception).startswith("During Lambeau Field (s13ad.iff): cannot keep the retail"))


def _child_writes(path):
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        platform_compat.pwrite(fd, b"\xee" * 64, 0x9000)
    finally:
        os.close(fd)


class DescriptorOnlyWriterTests(unittest.TestCase):
    """Each writer the journal trusts with a buffered open writes only through the descriptor (checked by parsing)."""

    def test_every_listed_writer_uses_its_file_object_only_for_fileno(self):
        for module, function in sorted(build_steps.DESCRIPTOR_ONLY_WRITERS):
            with self.subTest(f"{module}.{function}"):
                tree = ast.parse((ROOT / "mod_editor" / "core" / f"{module}.py").read_text(encoding="utf-8"))
                node = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function), None)
                self.assertIsNotNone(node, f"{module}.{function} is gone: update DESCRIPTOR_ONLY_WRITERS")
                names = set()
                for item in ast.walk(node):
                    if isinstance(item, ast.With):
                        for withitem in item.items:
                            call = withitem.context_expr
                            if (isinstance(call, ast.Call) and getattr(call.func, "attr", getattr(call.func, "id", ""))
                                    == "open" and any(isinstance(a, ast.Constant) and a.value in ("r+b", "rb+")
                                                      for a in call.args)):
                                self.assertIsInstance(withitem.optional_vars, ast.Name)
                                names.add(withitem.optional_vars.id)
                self.assertTrue(names, "no buffered r+b open found")
                parents = {child: parent for parent in ast.walk(node) for child in ast.iter_child_nodes(parent)}
                for item in ast.walk(node):
                    if isinstance(item, ast.Name) and item.id in names and isinstance(item.ctx, ast.Load):
                        parent = parents[item]
                        self.assertTrue(isinstance(parent, ast.Attribute) and parent.attr == "fileno",
                                        f"{module}.{function} uses its file object for more than fileno()")


class BuildIntegrationTests(unittest.TestCase):
    """The whole mod_build.build on the synthetic disc of test_mod_build_performance (no game data)."""

    def setUp(self):
        from test_mod_build_performance import synthetic_disc
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        self.source = self.folder / "retail.iso"
        synthetic_disc(self.source)
        self.enterContext(mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True}))
        self.enterContext(mock.patch("mod_editor.core.nfl2k5_unc_bowl_uniforms.apply_to_image",
                                     return_value={"synthetic": True}))

    def test_a_kit_pass_that_raises_mid_write_is_left_out_and_the_disc_equals_a_build_without_it(self):
        reference = self.folder / "reference.iso"
        clean = {"state": "other_image", "written_spans": 0, "written_bytes": 0, "changed_bytes": 0, "kits": []}
        with mock.patch("mod_editor.core.nfl2k5_kit_fixes_2026.apply_to_image", return_value=clean):
            mod_build.build(mod_build.BuildPlan(str(self.source), str(reference)))
        seen = {"calls": 0}

        def broken(target, *args, **kwargs):
            # apply_alternates, apply_finish ... call apply_to_image too: only the first layer (home and away) breaks
            seen["calls"] += 1
            if seen["calls"] > 1:
                return clean
            seen["target"] = Path(target)
            fd = os.open(target, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                platform_compat.pwrite(fd, b"\xde\xad" * 3000, 64 * 2048 + 4096)       # inside default.xbe
                platform_compat.pwrite(fd, b"\xbe\xef" * 3000, Path(target).stat().st_size - 9000)
            finally:
                os.close(fd)
            raise ValueError("cannot keep the retail scratch word:")

        output, lines = self.folder / "left-out.iso", []
        with mock.patch("mod_editor.core.nfl2k5_kit_fixes_2026.apply_to_image", side_effect=broken):
            receipt = mod_build.build(mod_build.BuildPlan(str(self.source), str(output)),
                                      lambda m, d=0, t=0: lines.append(m))
        self.assertNotEqual(seen["target"], output, "the step ran on the private copy")
        self.assertEqual(sha(output), sha(reference), "the left-out step's writes were undone exactly")
        rows = receipt["left_out"]
        self.assertEqual([r["step"] for r in rows], ["kit_fixes_2026"])
        note = ("The 2026 home and away kit repair was left out: cannot keep the retail scratch word (the step gave no "
                "reason). Your disc keeps those uniforms as they were.")
        self.assertEqual(rows[0]["user_notes"], [note])
        self.assertIn(note, lines)
        from mod_editor.core.build_feedback import completion
        self.assertIn(note, completion(receipt)[1])

    def test_a_core_step_failure_still_stops_and_names_its_step(self):
        output = self.folder / "core.iso"
        with mock.patch.object(mod_build, "inspect", side_effect=RuntimeError("the inspector read a short header")):
            with self.assertRaises(RuntimeError) as caught:
                mod_build.build(mod_build.BuildPlan(str(self.source), str(output)))
        exc = caught.exception
        self.assertEqual(exc.step, "verify_composed")
        self.assertEqual(str(exc), "During the check of the composed disc: the inspector read a short header")
        self.assertIsInstance(exc.__cause__, RuntimeError)
        self.assertFalse(output.exists())

    def test_all_selected_changes_left_out_says_so_instead_of_already_installed(self):
        unchanged = {"status": "unchanged", "message": "The copy is identical to the source."}
        with mock.patch("mod_editor.core.nfl2k5_kit_fixes_2026.apply_to_image", side_effect=ValueError("nope")), \
             mock.patch("mod_editor.core.build_feedback.compare", return_value=unchanged):
            with self.assertRaises(ValueError) as caught:
                mod_build.build(mod_build.BuildPlan(str(self.source), str(self.folder / "x.iso")), require_change=True)
        self.assertIn("was left out", str(caught.exception))
        self.assertNotIn("already installed", str(caught.exception))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        self.canary = b"RETAIL-CANARY-7b4b493b" * 512
        self.source = self.folder / "ESPN NFL 2K5 (USA).xiso.iso"
        self.source.write_bytes(self.canary)
        self.texture = self.folder / "chiefs-field.png"
        self.texture.write_bytes(b"\x89PNG\r\n\x1a\nTEXTURE-CANARY" * 64)
        self.output = self.folder / "out" / "Edwards: disc?.xiso.iso"
        self.output.parent.mkdir()
        from mod_editor.core import nfl2k5_modern_color as colour
        settings = colour.default_settings()
        settings["values"]["turf.value_lift"] = 3.1
        self.plan = mod_build.BuildPlan(str(self.source), str(self.output), modern_color=True,
                                        modern_color_settings=settings, modern_surfaces=True)

    def _failed_tracker(self):
        with self.assertRaises(ValueError) as caught:
            with build_steps.track() as session:
                build_steps.fact("plan", self.plan)
                build_steps.fact("source", str(self.source))
                build_steps.fact("target", str(self.output))
                build_steps.fact("project", mod_build.project_fingerprint(
                    {"edits": [{"kind": "stadium_texture", "target": "nfl2k5.stadium.o3136.field", "png": str(self.texture)},
                               {"kind": "uniform_texture", "target": "nfl2k5.kit.13H0.c3"}]}))
                for index in range(400):
                    session.progress(f"Building your project: edit {index} of 400 ({index}.png)", index, 400)
                build_steps.begin("modern_surfaces")
                with build_steps.resource("s13ad.iff"):
                    raise ValueError("cannot keep the retail scratch word:")
        return session.tracker, caught.exception

    def test_the_failure_record_writes_log_entry_and_text_only_zip(self):
        tracker, exc = self._failed_tracker()
        appended = []
        record = build_report.record_failure(
            tracker, exc, plan=self.plan, labels=["Modern colour and lighting", "Modern playing surfaces"],
            log_directory=self.folder / "logs", append_errors_log=lambda text: appended.append(text) or "errors.log",
            doctor=lambda: ("ok", "Project doctor: 2 findings.\nModern surfaces would keep s13ad.iff's divots.\n",
                            {"findings": 2}))
        self.assertEqual((record.step, record.resource), ("modern_surfaces", "s13ad.iff"))
        self.assertEqual(record.doctor, "ok")
        beside = Path(record.build_log)
        self.assertEqual(beside.parent, self.output.parent)
        self.assertNotIn(":", beside.name)
        log = beside.read_text(encoding="utf-8")
        for needle in ("Result: FAILED during Modern playing surfaces (s13ad.iff)", "Computer: ", "Python ",
                       f"Source disc: {self.source}", "sha256 not measured", "Project: 2 edits (stadium_texture 1, "
                       "uniform_texture 1); recipe sha256 ", "Options: Modern colour and lighting; Modern playing surfaces",
                       "turf.value_lift=3.1", "During Modern playing surfaces (s13ad.iff): cannot keep the retail",
                       "Full error (traceback):", "Building your project: edit 399 of 400", "<- stopped here"):
            self.assertIn(needle, log)
        self.assertNotIn("\r\n", beside.read_bytes().decode("utf-8"))
        self.assertTrue(Path(record.log_copy).is_file())
        entry = appended[0]
        self.assertIn("step: Modern playing surfaces (modern_surfaces)", entry)
        self.assertIn("resource: s13ad.iff", entry)
        self.assertIn("Traceback (most recent call last):", entry)
        self.assertIn(f"last {build_report.ERRORS_LOG_LINES} progress lines:", entry)
        self.assertLessEqual(entry.count("Building your project: edit"), build_report.ERRORS_LOG_LINES)
        archive = Path(record.zip)
        self.assertEqual(archive.parent, self.output.parent)
        self.assertNotIn(":", archive.name)
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            self.assertEqual(sorted(names), sorted(["README.txt", "build-log.txt", "errors-log-entry.txt",
                                                    "build-options.json", "project-doctor.txt", "project-doctor.json"]))
            for name in names:
                data = bundle.read(name)
                text = data.decode("utf-8")           # every member is UTF-8 text
                self.assertNotIn("\x00", text)
                self.assertNotIn(b"RETAIL-CANARY", data)
                self.assertNotIn(b"TEXTURE-CANARY", data)
                self.assertNotIn(b"\x89PNG", data)
                self.assertEqual(name, build_report.safe_name(name))
            options = json.loads(bundle.read("build-options.json"))
            self.assertTrue(options["options"]["modern_surfaces"])
            self.assertIn("SOFTDRINK Discord", bundle.read("README.txt").decode("utf-8"))

    def test_the_doctor_absent_failing_or_skipped_never_stops_the_report(self):
        tracker, exc = self._failed_tracker()
        with mock.patch("mod_editor.core.nfl2k5_project_check.doctor", create=True, side_effect=RuntimeError("bad")):
            status, text, data = build_report.run_doctor(None, self.source, self.plan)
        self.assertEqual(status, "failed")
        self.assertIn("The project doctor stopped: bad", text)
        from mod_editor.core import nfl2k5_project_check as project_check
        if not hasattr(project_check, "doctor"):
            self.assertEqual(build_report.run_doctor(None, self.source, self.plan)[0], "unavailable")
        with mock.patch("mod_editor.core.nfl2k5_project_check.doctor", create=True,
                        side_effect=BuildCancelled("Build cancelled")):
            self.assertEqual(build_report.run_doctor(None, self.source, self.plan)[0], "cancelled")
        record = build_report.record_failure(tracker, exc, plan=self.plan, doctor=lambda: ("failed", "doctor broke", None))
        with zipfile.ZipFile(record.zip) as bundle:
            self.assertIn("project-doctor-not-run.txt", bundle.namelist())
            self.assertIn("doctor broke", bundle.read("project-doctor-not-run.txt").decode("utf-8"))

    def test_a_refusal_before_the_long_work_does_not_run_the_doctor(self):
        with self.assertRaises(ValueError) as caught:
            with build_steps.track() as session:
                raise ValueError("Choose the original retail source.")
        called = []
        record = build_report.record_failure(session.tracker, caught.exception, plan=self.plan,
                                             doctor=lambda: called.append(1) or ("ok", "", None))
        self.assertEqual(called, [])
        self.assertEqual(record.step, "preflight")
        with zipfile.ZipFile(record.zip) as bundle:
            self.assertIn("before any long work", bundle.read("project-doctor-not-run.txt").decode("utf-8"))

    def test_the_zip_writer_refuses_anything_but_plain_text(self):
        target = self.folder / "x.zip"
        with self.assertRaises(TypeError):
            build_report.write_zip(target, {"disc.bin": b"\x00\x01"})
        with self.assertRaises(ValueError):
            build_report.write_zip(target, {"a.txt": "ok\x00binary"})
        with self.assertRaises(ValueError):
            build_report.write_zip(target, {"../escape.txt": "x"})
        with self.assertRaises(ValueError):
            build_report.write_zip(target, {"C:evil.txt": "x"})
        self.assertFalse(target.exists())

    def test_run_logged_gives_a_command_line_build_the_same_files(self):
        def finished(progress):
            build_steps.begin("copy")
            progress("Copying the image", 1, 1)
            self.output.write_bytes(b"built")
            return {"target": str(self.output), "steps": []}

        receipt = build_report.run_logged(finished, self.plan)
        self.assertIn("Result: OK", Path(receipt["build_log"]).read_text(encoding="utf-8"))

        def failing(progress):
            build_steps.begin("modern_coaches")
            raise RuntimeError("coach scene does not fit")

        with self.assertRaises(RuntimeError) as caught:
            build_report.run_logged(failing, self.plan, log_directory=self.folder / "logs")
        record = caught.exception.studio_build_record
        self.assertEqual(record["step"], "modern_coaches")
        self.assertTrue(Path(record["zip"]).is_file())
        self.assertIn("During 2026 head coaches: coach scene does not fit", str(caught.exception))

    def test_a_finished_build_writes_its_log_beside_the_disc(self):
        self.output.write_bytes(b"the published disc")
        with build_steps.track() as session:
            build_steps.fact("plan", self.plan)
            build_steps.fact("target", str(self.output))
            session.progress("Hashing the verified disc", 0, 0)
        record = build_report.record_end(session.tracker, plan=self.plan,
                                         receipt={"target": str(self.output), "user_notes": ["a note"]},
                                         log_directory=self.folder / "logs")
        self.assertEqual(Path(record.build_log).parent, self.output.parent)
        log = Path(record.build_log).read_text(encoding="utf-8")
        self.assertIn("Result: OK (the disc was made)", log)
        self.assertIn("- a note", log)
        self.assertEqual(build_report.safe_name("a:b/c\\d?.txt"), "a_b_c_d_.txt")

    def test_a_relative_or_missing_output_never_puts_a_log_in_the_current_folder(self):
        with build_steps.track() as session:
            session.progress("x", 0, 0)
        here = set(os.listdir("."))
        record = build_report.record_end(session.tracker, receipt={"target": "output.iso"})
        self.assertEqual(record.build_log, "")
        self.assertEqual(set(os.listdir(".")), here)
        missing = self.folder / "out" / "never-published.iso"
        record = build_report.record_end(session.tracker, receipt={"target": str(missing)},
                                         log_directory=self.folder / "logs")
        self.assertEqual(Path(record.build_log).parent, self.folder / "logs" / "builds")


if __name__ == "__main__":
    unittest.main()
