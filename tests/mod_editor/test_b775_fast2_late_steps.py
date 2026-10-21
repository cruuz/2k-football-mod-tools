"""b77.5 fast2: the late build steps run in worker processes, with a verified cache, and write the same bytes.

Two groups. The first is synthetic and quick: ordered_map's order and error behaviour, the worker-count and serial
switches, the cache's key and its refusal of damaged, stale or lossy entries, and the spawn start method (the
Windows one) with the module run as a script. The second runs each step on real retail and built-disc bytes (skipped
when those private inputs are absent) and requires the parallel, serial, cold-cache and warm-cache outputs to be
identical, and the declared code/data (nfl2k5_late_steps.STEP_CODE) to cover what a traced run actually uses.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
from mod_editor.core import nfl2k5_late_steps as late  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
BUILT = Path(os.environ.get("B775_FAST2_BUILT_DISC",
                            "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6.1 i4 test (2026-10-17).xiso.iso"))
V06 = Path(os.environ.get("B771_V06_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6 (2026-10-09).xiso.iso"))
MARKS = os.environ.get("NFL2K5_MARKS_PACK", "")


def sha(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def environment(**values):
    """Set (or with None clear) environment variables for a block."""
    before = {name: os.environ.get(name) for name in values}
    try:
        for name, value in values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


_CLOCK = [1_700_000_000]


def rewrite(path, content):
    """Write a file and give it a new modification time (the hash memo is keyed on size and mtime)."""
    path = Path(path)
    path.write_bytes(content if isinstance(content, bytes) else content.encode())
    _CLOCK[0] += 10
    os.utime(path, (_CLOCK[0], _CLOCK[0]))


# Top-level so the process pool (any start method) can pickle them.
def square(task):
    return task * task


def fail_on_three(task):
    if task == 3:
        raise ValueError("three")
    return task


_SEEN = []


def remember_init(value):
    _SEEN.append(value)


def init_plus(task):
    return task + (_SEEN[-1] if _SEEN else 0)


class OrderedMap(unittest.TestCase):
    def test_results_come_back_in_task_order_whatever_the_worker_count(self):
        tasks = list(range(23))
        for workers in (1, 2, 5):
            self.assertEqual(list(late.ordered_map(square, tasks, workers)), [t * t for t in tasks], workers)

    def test_one_worker_or_one_task_runs_in_this_process(self):
        with patch("concurrent.futures.ProcessPoolExecutor", side_effect=AssertionError("no pool")):
            self.assertEqual(list(late.ordered_map(square, [1, 2, 3], 1)), [1, 4, 9])
            self.assertEqual(list(late.ordered_map(square, [4], 8)), [16])

    def test_an_error_surfaces_when_its_turn_comes_after_the_earlier_results(self):
        seen = []
        with self.assertRaisesRegex(ValueError, "three"):
            for value in late.ordered_map(fail_on_three, [1, 2, 3, 4, 5], 3):
                seen.append(value)
        self.assertEqual(seen, [1, 2])

    def test_a_pool_that_cannot_start_finishes_in_this_process(self):
        with patch("concurrent.futures.ProcessPoolExecutor", side_effect=OSError("no fork")):
            self.assertEqual(list(late.ordered_map(square, [1, 2, 3], 4)), [1, 4, 9])

    def test_a_lost_worker_finishes_the_remaining_tasks_in_this_process(self):
        from concurrent.futures.process import BrokenProcessPool

        class Broken:
            def submit(self, *args):
                raise BrokenProcessPool("lost")

            def shutdown(self, **kwargs):
                pass
        with patch("concurrent.futures.ProcessPoolExecutor", return_value=Broken()):
            self.assertEqual(list(late.ordered_map(square, [1, 2, 3], 4)), [1, 4, 9])

    def test_dearest_tasks_start_first_but_results_stay_in_task_order(self):
        tasks = list(range(10))
        self.assertEqual(list(late.ordered_map(square, tasks, 3, cost=lambda t: 1 if t % 4 == 3 else 0)),
                         [t * t for t in tasks])
        with self.assertRaisesRegex(ValueError, "three"):
            list(late.ordered_map(fail_on_three, tasks, 3, cost=lambda t: t))
        self.assertEqual(list(late.ordered_map(square, tasks, 1, cost=lambda t: t)), [t * t for t in tasks])

    def test_the_initializer_runs_once_per_worker_and_in_process(self):
        _SEEN.clear()
        self.assertEqual(list(late.ordered_map(init_plus, [1, 2], 1, initializer=remember_init, initargs=(10,))),
                         [11, 12])
        self.assertEqual(_SEEN, [10])
        self.assertEqual(list(late.ordered_map(init_plus, [1, 2, 3, 4], 2, initializer=remember_init, initargs=(100,))),
                         [101, 102, 103, 104])

    def test_the_marks_pack_travels_with_each_task(self):
        # run_with_pack scopes the recipe's marks pack in the worker; the parent's selection must reach it
        from mod_editor.core import nfl2k5_official_marks as official
        with official.using_pack("/some/pack"):
            self.assertEqual(list(late.ordered_map(selected_pack, [0, 1, 2], 2)), ["/some/pack"] * 3)


def selected_pack(_task):
    from mod_editor.core import nfl2k5_official_marks as official
    return official.selected_root()


class WorkerCount(unittest.TestCase):
    def test_serial_switches_and_small_jobs_use_one_worker(self):
        with environment(NFL2K5_SERIAL_LATE_STEPS="1", NFL2K5_BUILD_WORKERS=None):
            self.assertEqual(late.worker_count(50, "NFL2K5_SERIAL_FAN_ART"), 1)
            self.assertEqual(late.worker_count(50, "NFL2K5_SERIAL_FAN_ART", legacy=4), 4)
        with environment(NFL2K5_SERIAL_LATE_STEPS=None, NFL2K5_SERIAL_ERA_KITS="1", NFL2K5_BUILD_WORKERS=None):
            self.assertEqual(late.worker_count(50, "NFL2K5_SERIAL_ERA_KITS"), 1)
        with environment(NFL2K5_SERIAL_LATE_STEPS=None, NFL2K5_SERIAL_ERA_KITS="1", NFL2K5_BUILD_WORKERS="8"):
            # an explicit worker count wins over a serial switch, and a step without the switch uses it too
            self.assertEqual(late.worker_count(50, "NFL2K5_SERIAL_ERA_KITS"), 8)
            self.assertEqual(late.worker_count(50, "NFL2K5_SERIAL_FAN_ART"), 8)
        with environment(NFL2K5_SERIAL_LATE_STEPS="1", NFL2K5_BUILD_WORKERS="1"):
            self.assertEqual(late.worker_count(50, "NFL2K5_SERIAL_FAN_ART", legacy=4), 1)
        with environment(NFL2K5_SERIAL_LATE_STEPS=None, NFL2K5_BUILD_WORKERS="8"):
            self.assertEqual(late.worker_count(1, "NFL2K5_SERIAL_FAN_ART"), 1)
            self.assertEqual(late.worker_count(3, "NFL2K5_SERIAL_FAN_ART"), 3)

    def test_the_default_is_bounded_by_cores_and_memory_and_by_windows(self):
        with environment(NFL2K5_SERIAL_LATE_STEPS=None, NFL2K5_BUILD_WORKERS=None):
            with patch("os.sched_getaffinity", return_value=set(range(32)), create=True), \
                    patch.object(late, "_available_memory", return_value=1 << 60):
                self.assertEqual(late.worker_count(500), 31)
                self.assertEqual(late.worker_count(10), 10)
            with patch("os.sched_getaffinity", return_value=set(range(32)), create=True), \
                    patch.object(late, "_available_memory", return_value=4 * 700 * 1024 ** 2):
                self.assertEqual(late.worker_count(500, per_worker_mb=700), 4)
            with patch("os.sched_getaffinity", return_value=set(range(128)), create=True), \
                    patch.object(late, "_available_memory", return_value=1 << 60), patch("os.name", "nt"):
                self.assertEqual(late.worker_count(500), 61)

    def test_a_bad_override_falls_back_to_the_default(self):
        with environment(NFL2K5_SERIAL_LATE_STEPS=None, NFL2K5_BUILD_WORKERS="many"):
            with patch("os.sched_getaffinity", return_value=set(range(8)), create=True), \
                    patch.object(late, "_available_memory", return_value=1 << 60):
                self.assertEqual(late.worker_count(100), 7)

    def test_the_two_old_caps_return_with_their_switches(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as venues
        with environment(NFL2K5_SERIAL_LATE_STEPS=None, NFL2K5_SERIAL_VENUE_ART="1", NFL2K5_BUILD_WORKERS=None):
            with patch("os.cpu_count", return_value=64):
                self.assertEqual(venues._workers(), 16)
            self.assertEqual(venues._workers(3), 3)
        with environment(NFL2K5_SERIAL_LATE_STEPS="1", NFL2K5_SERIAL_VENUE_ART=None, NFL2K5_BUILD_WORKERS=None):
            with patch("os.cpu_count", return_value=8):
                self.assertEqual(venues._workers(), 4)
        with environment(NFL2K5_SERIAL_LATE_STEPS=None, NFL2K5_SERIAL_VENUE_ART=None, NFL2K5_BUILD_WORKERS="31"):
            self.assertEqual(venues._workers(), 31)


class Digests(unittest.TestCase):
    def test_arrays_bytes_and_mappings_digest_by_content_not_order_or_identity(self):
        import numpy as np
        a = {"x": np.arange(6, dtype="uint8").reshape(2, 3), "y": b"abc", ("s", 1): [1, 2.5, None]}
        b = {("s", 1): [1, 2.5, None], "y": b"abc", "x": np.arange(6, dtype="uint8").reshape(2, 3).copy()}
        self.assertEqual(late.digest(a), late.digest(b))
        b["x"][0, 0] = 9
        self.assertNotEqual(late.digest(a), late.digest(b))
        self.assertNotEqual(late.digest(np.zeros((2, 3), "uint8")), late.digest(np.zeros((3, 2), "uint8")))
        self.assertNotEqual(late.digest(np.zeros(4, "uint8")), late.digest(np.zeros(4, "int8")))
        with self.assertRaises(TypeError):
            late.digest(object())


class Cache(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "code.py").write_text("A = 1\n")
        self.code = ("mod_editor/core/nfl2k5_late_steps.py",)

    def cache(self, step="demo", code=None, data=()):
        return late.StepCache(step, self.code if code is None else code, data, root=self.root / step)

    def test_a_stored_value_comes_back_exactly_and_is_counted(self):
        cache = self.cache()
        key = cache.key("input")
        self.assertIsNone(cache.get(key))
        value = dict(after=b"\x00\xff" * 1000, rows=[1, (2, 3)], text="t")
        self.assertTrue(cache.put(key, value))
        self.assertEqual(self.cache().get(key), value)
        self.assertEqual((cache.hits, cache.misses, cache.stored), (0, 1, 1))

    def test_every_key_input_changes_the_key(self):
        base = self.cache().key("a", 1)
        self.assertNotEqual(base, self.cache().key("a", 2))
        self.assertNotEqual(base, self.cache("other").key("a", 1))
        with environment(NFL2K5_MARKS_PACK="/elsewhere"):
            self.assertNotEqual(base, self.cache().key("a", 1))
        # switches that only pick workers or caching are not part of the key
        with environment(NFL2K5_BUILD_WORKERS="3", NFL2K5_SERIAL_FAN_ART="1", NFL2K5_DISABLE_COMPILE_CACHE=None):
            self.assertEqual(base, self.cache().key("a", 1))

    def test_a_changed_code_file_or_data_file_never_hits(self):
        (ROOT / "reports").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            relative = Path(folder).relative_to(ROOT)
            (Path(folder) / "step.py").write_text("X = 1\n")
            (Path(folder) / "table.json").write_text("{}\n")
            files = ((relative / "step.py").as_posix(),)
            data = ((relative / "table.json").as_posix(),)
            key = self.cache(code=files, data=data).key("in")
            self.cache(code=files, data=data).put(key, {"v": 1})
            self.assertEqual(self.cache(code=files, data=data).get(key), {"v": 1})
            rewrite(Path(folder) / "step.py", "X = 2\n")
            self.assertNotEqual(self.cache(code=files, data=data).key("in"), key)
            rewrite(Path(folder) / "step.py", "X = 1\n")
            self.assertEqual(self.cache(code=files, data=data).key("in"), key)
            rewrite(Path(folder) / "table.json", '{"a": 1}\n')
            self.assertNotEqual(self.cache(code=files, data=data).key("in"), key)

    def test_damaged_truncated_foreign_and_tampered_entries_are_misses(self):
        cache = self.cache()
        key = cache.key("x")
        cache.put(key, {"v": b"payload" * 100})
        entry = cache.cache.root / (key + ".json")
        good = entry.read_bytes()
        for damaged in (good[:len(good) // 2], b"not json", good.replace(b"payload", b"PAYLOAD", 1), b"", b"[]"):
            entry.write_bytes(damaged)
            self.assertIsNone(self.cache().get(key), damaged[:12])
        # a well-formed entry stored under another key is refused
        other = cache.key("y")
        cache.put(other, {"v": 2})
        (cache.cache.root / (key + ".json")).write_bytes((cache.cache.root / (other + ".json")).read_bytes())
        self.assertIsNone(self.cache().get(key))

    def test_a_value_json_cannot_hold_exactly_is_not_cached(self):
        cache = self.cache()
        key = cache.key("lossy")
        self.assertFalse(cache.put(key, {1: "int key"}))
        self.assertFalse(cache.put(key, {"nan": float("nan")}))
        self.assertFalse(cache.put(key, {"object": object()}))
        self.assertIsNone(cache.get(key))
        self.assertFalse(cache.put(None, {"v": 1}))
        self.assertIsNone(cache.get(None))

    def test_an_undigestable_input_means_no_caching_not_a_failed_build(self):
        self.assertIsNone(self.cache().key(object()))

    def test_the_disable_switch_and_an_unusable_folder_give_no_cache(self):
        with environment(NFL2K5_DISABLE_COMPILE_CACHE="1"):
            self.assertIsNone(late.StepCache.open("demo", self.code))
        blocker = self.root / "blocked"
        blocker.write_text("a file where the folder should be")
        with environment(NFL2K5_DISABLE_COMPILE_CACHE=None, NFL2K5_STEP_CACHE_ROOT=str(blocker)):
            self.assertIsNone(late.StepCache.open("demo", self.code))
        with environment(NFL2K5_DISABLE_COMPILE_CACHE=None, NFL2K5_STEP_CACHE_ROOT=str(self.root / "ok")):
            self.assertIsNotNone(late.StepCache.open("demo", self.code))

    def test_the_cache_obeys_the_size_cap(self):
        cache = self.cache()
        with environment(NFL2K5_COMPILE_CACHE_MAX_MB="1"):
            for number in range(8):
                cache.put(cache.key(number), {"v": os.urandom(400 * 1024)})
        total = sum(p.stat().st_size for p in cache.cache.root.glob("*.json"))
        self.assertLessEqual(total, 1024 * 1024 + 700 * 1024)

    def test_every_step_declares_code_and_data_that_exist(self):
        self.assertEqual(set(late.STEP_CODE), {"fan-art", "anniversary-fields", "play-scoring", "era-kits",
                                               "broadcast-greens", "venue-art"})
        for step, declared in late.STEP_CODE.items():
            self.assertTrue(declared["code"], step)
            for name in (*declared["code"], *declared["data"]):
                self.assertTrue((ROOT / name).exists(), f"{step}: {name}")


class Spawn(unittest.TestCase):
    """Windows starts workers with spawn and re-imports the main script: run the pool that way, as a script."""

    def test_ordered_map_under_spawn_with_the_module_run_as_a_script(self):
        script = textwrap.dedent(f"""
            import multiprocessing, sys
            sys.path[:0] = [{str(ROOT)!r}]
            from mod_editor.core import nfl2k5_late_steps as late
            SEEN = []

            def square(task):
                return task * task

            def remember(value):
                SEEN.append(value)

            def plus(task):
                return task + SEEN[-1]

            def main():
                multiprocessing.set_start_method("spawn")
                got = list(late.ordered_map(square, list(range(12)), 3))
                assert got == [t * t for t in range(12)], got
                got = list(late.ordered_map(plus, [1, 2, 3, 4], 2, initializer=remember, initargs=(7,)))
                assert got == [8, 9, 10, 11], got
                print("SPAWN-OK")

            if __name__ == "__main__":
                multiprocessing.freeze_support()
                main()
        """)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "run_spawn.py"
            path.write_text(script)
            done = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=300,
                                  env=dict(os.environ, PYTHONPATH=str(ROOT)))
        self.assertIn("SPAWN-OK", done.stdout, done.stdout + done.stderr)

    def test_the_worker_entry_points_pickle(self):
        from mod_editor.core import nfl2k5_broadcast_greens as greens
        from mod_editor.core import nfl2k5_era_kits as era
        from mod_editor.core import nfl2k5_espn25_fields as fields
        from mod_editor.core import nfl2k5_model_fan_art as fans
        from mod_editor.core import nfl2k5_modern_venues_2026 as venues
        from mod_editor.core import nfl2k5_play_scoring as scoring
        for function in (late._run_task, fans._paint_task, fields._row_job, era._kit_task, scoring._score_task,
                         scoring._init_worker, greens._greens_task, venues._compile_job):
            self.assertIs(pickle.loads(pickle.dumps(function)), function)


# -- real inputs -----------------------------------------------------------------------------------------------

ART_ROOT = Path(os.environ.get(
    "B775_FAST2_ART_ROOT", "/home/noah/2k-worktrees/.b77-scratch/i4/studio-work/sources/assets/trees/f7bb2bc2e24a8fbb2aeb"))


def traced_uses_only_declared(test, step, traced):
    """The code a traced serial run executed and the files it opened must be inside the step's declaration."""
    declared = late.STEP_CODE[step]
    missing_code = sorted(set(traced["code"]) - set(declared["code"]))
    test.assertEqual(missing_code, [], f"{step}: executed code not declared in STEP_CODE")
    missing_data = sorted(name for name in traced["data"]
                          if not any(name == entry or name.startswith(entry + "/") for entry in declared["data"]))
    test.assertEqual(missing_data, [], f"{step}: opened data not declared in STEP_CODE")


class RealStep(unittest.TestCase):
    """Shared: a private cache folder per test, and workers/serial/cache switches set explicitly."""

    def setUp(self):
        import late_step_trace
        self.trace = late_step_trace.trace
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.cache_root = folder.name
        self.addCleanup(self._restore, dict(os.environ))

    @staticmethod
    def _restore(saved):
        os.environ.clear()
        os.environ.update(saved)

    def mode(self, kind, step_switch):
        """The environment of one run: serial (workers 1, no cache), parallel (3 workers, no cache), cold or warm."""
        for name in ("NFL2K5_BUILD_WORKERS", "NFL2K5_DISABLE_COMPILE_CACHE", "NFL2K5_SERIAL_LATE_STEPS", step_switch):
            os.environ.pop(name, None)
        os.environ["NFL2K5_STEP_CACHE_ROOT"] = self.cache_root
        if kind == "serial":
            os.environ[step_switch] = "1"
            os.environ["NFL2K5_DISABLE_COMPILE_CACHE"] = "1"
        elif kind == "parallel":
            os.environ["NFL2K5_BUILD_WORKERS"] = "3"
            os.environ["NFL2K5_DISABLE_COMPILE_CACHE"] = "1"
        else:   # cold and warm cache runs, parallel
            os.environ["NFL2K5_BUILD_WORKERS"] = "3"

    def no_worker_runs(self):
        """Patch that fails the test if any task reaches a worker (a warm cache must not compile)."""
        return patch.object(late, "ordered_map", side_effect=lambda f, tasks, workers, **k: iter(
            [] if not list(tasks) else self.fail("a cache hit still ran a task")))


@unittest.skipUnless(RETAIL.is_file(), "retail ISO absent")
class PlayScoring(RealStep):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import mod_build as mb
        packs = mb._core_module("nfl2k5_playbook_pack")
        cls.payload = mb._xbe_bytes(RETAIL)
        with packs._outer_image().OuterImage(RETAIL) as archive:
            cls.books = [(e.index, archive.read_entry(e.index)) for e in archive.entries_with_head(b"PLAY")][:5]

    def test_parallel_serial_cached_and_the_original_loop_agree(self):
        from mod_editor.core import nfl2k5_play_scoring as sc
        reference = [{"entry": index, **sc.require_safe(book, self.payload)} for index, book in self.books]
        sc._sweep_cached.cache_clear()
        self.mode("serial", "NFL2K5_SERIAL_PLAY_SCORING")
        _, traced = self.trace(sc.require_safe_many, self.books, self.payload)
        traced_uses_only_declared(self, "play-scoring", traced)
        sc._sweep_cached.cache_clear()
        self.assertEqual(sc.require_safe_many(self.books, self.payload), reference)
        sc._sweep_cached.cache_clear()
        self.mode("parallel", "NFL2K5_SERIAL_PLAY_SCORING")
        self.assertEqual(sc.require_safe_many(self.books, self.payload), reference)
        self.mode("cold", "NFL2K5_SERIAL_PLAY_SCORING")
        self.assertEqual(sc.require_safe_many(self.books, self.payload), reference)
        with self.no_worker_runs():
            self.assertEqual(sc.require_safe_many(self.books, self.payload), reference)

    def test_progress_runs_in_book_order_and_a_warm_cache_sends_no_book_to_a_worker(self):
        from mod_editor.core import nfl2k5_play_scoring as sc
        self.mode("cold", "NFL2K5_SERIAL_PLAY_SCORING")
        seen = []
        sc.require_safe_many(self.books[:2], self.payload, progress=lambda i, d, t: seen.append((i, d, t)))
        self.assertEqual(seen, [(self.books[0][0], 0, 2), (self.books[1][0], 1, 2)])
        with patch.object(late, "ordered_map", wraps=late.ordered_map) as mapped:
            sc.require_safe_many(self.books[:2], self.payload)
        self.assertEqual(list(mapped.call_args[0][1]), [])

    def test_a_cached_record_with_a_fault_or_foreign_digest_is_not_trusted(self):
        from mod_editor.core import nfl2k5_play_scoring as sc
        book, payload = self.books[0][1], self.payload

        class Store:
            def __init__(self, record):
                self.record = record

            def get(self, key):
                return self.record
        good = sc.sweep(book, payload)
        self.assertIsNotNone(sc._remembered(Store(good), "k", book, payload))
        for bad in (dict(good, faults=[{"play": 1}], fault_count=1), dict(good, resource_sha256="0" * 64),
                    dict(good, xbe_sha256="0" * 64), dict(good, status="unproven"), dict(good, schema="other"), None, []):
            self.assertIsNone(sc._remembered(Store(bad), "k", book, payload))

    def test_the_first_rejected_book_is_the_one_that_raises(self):
        from mod_editor.core import nfl2k5_play_scoring as sc
        self.mode("serial", "NFL2K5_SERIAL_PLAY_SCORING")
        real = sc.require_safe
        calls = []

        def picky(resource, xbe=None):
            calls.append(sha(resource))
            if len(calls) == 2:
                raise sc.ScoringError("book two rejected")
            return real(resource, xbe)
        with patch.object(sc, "require_safe", picky):
            with self.assertRaisesRegex(sc.ScoringError, "book two rejected"):
                sc.require_safe_many(self.books[:4], self.payload)
        self.assertEqual(len(calls), 2)


@unittest.skipUnless(RETAIL.is_file() and BUILT.is_file(), "retail ISO or the built disc absent")
class AnniversaryFields(RealStep):
    ROWS = (2, 14, 25, 51)   # authored lettering; Super Bowl walls + the 2004 shield; retail playoff field; stripes

    def compile(self):
        from mod_editor.core import nfl2k5_espn25_fields as fields
        from mod_editor.core import nfl2k5_espn25_more_moments as moments
        from mod_editor.core import nfl2k5_historic_styles as styles
        full = fields.catalog
        progress = []
        with styles.Source(BUILT) as built, styles.Source(RETAIL) as retail, \
                patch.object(fields, "catalog", lambda: [r for r in full() if r["row"] in self.ROWS]):
            situ, _ = fields.repair_situ(built.get(identity=moments.SITU_ID))
            output, receipt = fields.compile_assets(built.get, retail.get, situ,
                                                    progress=lambda *a: progress.append(a))
        return output, json.dumps(receipt, sort_keys=True, default=repr), progress

    def test_serial_parallel_cold_and_warm_runs_write_identical_fields_and_receipts(self):
        self.mode("serial", "NFL2K5_SERIAL_ANNIVERSARY_FIELDS")
        reference, traced = self.trace(self.compile)
        traced_uses_only_declared(self, "anniversary-fields", traced)
        self.assertEqual([name[:3] for name in reference[0]], [f"a{row - 1:02d}" for row in self.ROWS])
        self.assertEqual([p[0] for p in reference[2]], list(self.ROWS))
        self.mode("parallel", "NFL2K5_SERIAL_ANNIVERSARY_FIELDS")
        self.assertEqual(self.compile(), reference)
        self.mode("cold", "NFL2K5_SERIAL_ANNIVERSARY_FIELDS")
        self.assertEqual(self.compile(), reference)
        with self.no_worker_runs():
            self.assertEqual(self.compile(), reference)

    def test_a_changed_user_art_folder_is_part_of_the_key(self):
        from mod_editor.core import nfl2k5_espn25_fields as fields
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "teams").mkdir()
            self.assertIsNone(fields._user_art_digest(None))
            empty = fields._user_art_digest(folder)
            rewrite(Path(folder) / "teams" / "KC.png", b"png one")
            one = fields._user_art_digest(folder)
            rewrite(Path(folder) / "teams" / "KC.png", b"png number two")
            two = fields._user_art_digest(folder)
            self.assertEqual(len({json.dumps(v) for v in (empty, one, two)}), 3)
            self.assertEqual(fields._user_art_digest(folder + "-missing"), ["missing"])

    def test_a_tampered_cache_entry_is_recompiled_not_used(self):
        self.mode("cold", "NFL2K5_SERIAL_ANNIVERSARY_FIELDS")
        reference = self.compile()
        root = Path(self.cache_root) / "anniversary-fields"
        entries = sorted(root.glob("*.json"))
        self.assertEqual(len(entries), len(self.ROWS))
        for entry in entries:
            raw = bytearray(entry.read_bytes())
            raw[len(raw) // 2] ^= 0x01
            entry.write_bytes(bytes(raw))
        self.assertEqual(self.compile(), reference)


def retail_bundle(name):
    """One venue resource from the retail disc, by file name."""
    from mod_editor.core import nfl2k5_modern_metlife as mm
    from mod_editor.core import nfl2k5_modern_venues_2026 as mv
    with mv._outer_image()(RETAIL) as archive:
        wanted = mm.name_id(name)
        entry = next(e for e in archive.entries if e.name_id == wanted)
        return archive.read(entry.virtual_offset, entry.size)


@unittest.skipUnless(RETAIL.is_file() and ART_ROOT.is_dir(), "retail ISO or the club art tree absent")
class FanArt(RealStep):
    NAMES = ("s15dd.iff", "s15nr.iff")      # U.S. Bank Stadium: a dry-day and a rain-night bundle

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_usbank_model as bank
        os.environ.setdefault("NFL2K5_BUILD_WORKERS", "2")
        built = bank.build_all(RETAIL, workers=2, names=list(cls.NAMES))
        cls.results = [(name, model, info) for name, (_retail, model, info) in built.items()]
        cls.retail = bank.read_retail(RETAIL)
        cls.pins = bank.model_pins()

    def paint(self):
        from mod_editor.core import nfl2k5_model_fan_art as fans
        return fans.paint_results(self.results, self.retail, str(ART_ROOT), self.pins)

    def test_serial_parallel_cold_and_warm_runs_paint_identical_bundles_and_receipts(self):
        from mod_editor.core import nfl2k5_model_fan_art as fans
        from mod_editor.core import nfl2k5_stadium_shared_art as shared
        self.mode("serial", "NFL2K5_SERIAL_FAN_ART")

        def serial_and_neutral():
            painted = self.paint()
            # the neutral slot's plan runs through the same painter inputs
            neutral = fans.neutral_plan("s40", {"s40dd.iff": retail_bundle("s40dd.iff")})
            return painted, fans._plan_digest(neutral)
        (reference, neutral_digest), traced = self.trace(serial_and_neutral)
        traced_uses_only_declared(self, "fan-art", traced)
        self.assertEqual([r[0] for r in reference], list(self.NAMES))
        self.assertTrue(all("fan_art" in info for _n, _b, info in reference))
        self.assertNotEqual([b for _n, b, _i in reference], [m for _n, m, _i in self.results])
        for kind in ("parallel", "cold"):
            self.mode(kind, "NFL2K5_SERIAL_FAN_ART")
            self.assertEqual(self.paint(), reference, kind)
        with self.no_worker_runs():
            self.assertEqual(self.paint(), reference)
        self.assertEqual(shared.MODEL_NEUTRAL, frozenset({"s40"}))
        self.assertTrue(neutral_digest)

    def test_a_tampered_entry_is_repainted_and_a_changed_bundle_misses(self):
        self.mode("cold", "NFL2K5_SERIAL_FAN_ART")
        reference = self.paint()
        root = Path(self.cache_root) / "fan-art"
        entries = sorted(root.glob("*.json"))
        self.assertEqual(len(entries), len(self.NAMES))
        for entry in entries:
            raw = bytearray(entry.read_bytes())
            raw[len(raw) // 2] ^= 0x01
            entry.write_bytes(bytes(raw))
        self.assertEqual(self.paint(), reference)
        # a different bundle (one byte of the compiled model) never reuses a painted entry
        changed = list(self.results)
        name, model, info = changed[0]
        model = bytearray(model)
        model[-1] ^= 0x01
        changed[0] = (name, bytes(model), info)
        with patch.object(type(self), "results", changed):
            from mod_editor.core import nfl2k5_model_fan_art as fans
            with patch.object(fans, "paint_bundle", side_effect=fans.paint_bundle) as painter:
                self.paint()
        self.assertGreaterEqual(painter.call_count, 1)


@unittest.skipUnless(RETAIL.is_file() and V06.is_file(), "retail ISO or the v0.6 disc absent")
class EraKits(RealStep):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_bump_texture_writer as bump
        from mod_editor.core import nfl2k5_era_kits as era

        def read(path, names):
            with bump._Image.open(path, writable=False) as image:
                index = bump._parsed_index(image)
                entries = {bump.logical_name_for(e.name_id): e for e in index.entries}
                return {n: image.read_segments(index.sub_extents(entries[n], 0, entries[n].size))
                        for n in names if n in entries}
        copy, retail_names = era.needed_packages()
        targets = {s + ".IFF" for s in era.pins()["kits"]}
        retail = read(RETAIL, sorted(set(copy) | set(retail_names)))
        v06 = read(V06, sorted(set(copy)))
        cls.stage = {n: (retail[n] if n in targets else v06[n]) for n in copy}
        cls.retail_parts = {n: retail[n] for n in retail_names}
        cls.labels = {(r["code"], r["style"]): tuple(r["label"]) for r in era.recipes()}

    def plan(self):
        from mod_editor.core import nfl2k5_era_kits as era
        return era.plan(self.stage, self.labels, self.retail_parts)

    def test_serial_parallel_cold_and_warm_runs_compose_identical_kits_and_rows(self):
        from mod_editor.core import nfl2k5_era_kits as era
        self.mode("serial", "NFL2K5_SERIAL_ERA_KITS")
        reference, traced = self.trace(self.plan)
        traced_uses_only_declared(self, "era-kits", traced)
        self.assertEqual(len(reference), 10)
        self.assertEqual({row["state"] for _s, _d, row in reference}, {"composed"})
        for selector, data, row in reference:   # every composed kit still meets its output pin
            self.assertEqual(sha(data), era.pins()["kits"][selector]["after_sha256"])
        for kind in ("parallel", "cold"):
            self.mode(kind, "NFL2K5_SERIAL_ERA_KITS")
            self.assertEqual(self.plan(), reference, kind)
        with self.no_worker_runs():
            self.assertEqual(self.plan(), reference)

    def test_a_cache_entry_cannot_get_a_kit_past_its_output_pin(self):
        self.mode("cold", "NFL2K5_SERIAL_ERA_KITS")
        self.plan()
        # Hand back, for every cached kit, a same-size and internally consistent but wrong kit: the pin check refuses.
        forged = []
        real_get = late.StepCache.get

        def get_wrong(self_, key):
            value = real_get(self_, key)
            if isinstance(value, dict) and isinstance(value.get("after"), bytes):
                wrong = bytes(len(value["after"]))
                value = dict(value, after=wrong, after_sha256=sha(wrong))
                forged.append(key)
            return value
        with patch.object(late.StepCache, "get", get_wrong):
            with self.assertRaisesRegex(ValueError, "composed kit differs from its output pin"):
                self.plan()
        self.assertTrue(forged)

    def test_the_first_failing_decision_still_comes_after_an_earlier_kit_compile_error(self):
        from mod_editor.core import nfl2k5_era_kits as era
        self.mode("serial", "NFL2K5_SERIAL_ERA_KITS")
        real = era.compile_kit
        calls = []

        def broken(raw, donor, parts, recipe):
            calls.append(recipe["id"])
            raise ValueError("first kit cannot compile")
        # a later recipe asks for the retail source that was not supplied: the earlier compile error wins
        with patch.object(era, "compile_kit", broken):
            with self.assertRaisesRegex(ValueError, "first kit cannot compile"):
                era.plan(self.stage, self.labels, None)
        self.assertEqual(len(calls), 1)
        self.assertIs(era.compile_kit, real)


class FakeEntry:
    def __init__(self, name_id, offset, size):
        self.name_id, self.virtual_offset, self.size = name_id, offset, size


class FakeImage:
    """An in-memory outer archive: named blobs laid end to end, readable and writable."""

    def __init__(self, blobs):
        from mod_editor.core import nfl2k5_modern_metlife as mm
        self.data, self.entries = bytearray(), []
        for name, blob in blobs.items():
            self.entries.append(FakeEntry(mm.name_id(name), len(self.data), len(blob)))
            self.data += blob

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, offset, size):
        return bytes(self.data[offset:offset + size])

    def write(self, offset, blob):
        self.data[offset:offset + len(blob)] = blob
        return len(blob)


@unittest.skipUnless(RETAIL.is_file(), "retail ISO absent")
class BroadcastGreens(RealStep):
    COUNT = 12

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        cls.blobs = {}
        with mv._outer_image()(RETAIL) as archive:
            for prefix in sorted(mv.venues()):
                for pin in mv.venues()[prefix]["bundles"]:
                    if len(cls.blobs) < cls.COUNT:
                        entry = mv._entry(archive, pin)
                        cls.blobs[pin["name"]] = archive.read(entry.virtual_offset, entry.size)
        cls.kinds = {name[:3]: ("grass" if number % 2 else "synthetic") for number, name in enumerate(sorted(cls.blobs))}

    def apply(self, **options):
        from mod_editor.core import nfl2k5_broadcast_greens as greens
        from mod_editor.core import nfl2k5_modern_surfaces as surfaces
        image = FakeImage(self.blobs)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "fake.iso"
            target.write_bytes(b"x")
            progress = []
            with patch.object(greens, "families", lambda archive: self.kinds), \
                    patch.object(surfaces, "_outer_image", lambda: (lambda path, writable=False: image)), \
                    patch.object(surfaces, "HOME_BUNDLES", frozenset(self.blobs)):
                result = greens.apply_to_image(target, progress=lambda *a: progress.append(a), **options)
            sidecar = json.loads(Path(str(target) + ".greens.json").read_text())
        return result, bytes(image.data), json.dumps(sidecar, sort_keys=True), progress

    def test_any_worker_count_the_old_cap_and_the_cache_write_the_same_image_and_receipt(self):
        self.mode("serial", "NFL2K5_SERIAL_BROADCAST_GREENS")
        os.environ["NFL2K5_BUILD_WORKERS"] = "1"
        reference, traced = self.trace(self.apply)
        traced_uses_only_declared(self, "broadcast-greens", traced)
        self.assertEqual(reference[0]["bundles"], self.COUNT)
        self.assertNotEqual(reference[1], b"".join(self.blobs.values()))
        self.assertEqual([p[1] for p in reference[3]], list(range(1, self.COUNT + 1)))
        for workers in (2, 4, 9, 40):    # 40 is above the old limit of four
            self.mode("parallel", "NFL2K5_SERIAL_BROADCAST_GREENS")
            self.assertEqual(self.apply(workers=workers), reference, workers)
        self.mode("parallel", "NFL2K5_SERIAL_BROADCAST_GREENS")
        self.assertEqual(self.apply(), reference)        # the default worker count
        self.mode("serial", "NFL2K5_SERIAL_BROADCAST_GREENS")
        self.assertEqual(self.apply(), reference)        # the old four workers
        self.mode("cold", "NFL2K5_SERIAL_BROADCAST_GREENS")
        self.assertEqual(self.apply(), reference)
        with self.no_worker_runs():
            self.assertEqual(self.apply(), reference)

    def test_workers_must_be_a_positive_whole_number(self):
        for bad in (0, -1, 2.5, "4"):
            with self.assertRaisesRegex(ValueError, "workers must be"):
                self.apply(workers=bad)

    def test_a_tampered_entry_is_recomputed(self):
        self.mode("cold", "NFL2K5_SERIAL_BROADCAST_GREENS")
        reference = self.apply()
        for entry in (Path(self.cache_root) / "broadcast-greens").glob("*.json"):
            raw = bytearray(entry.read_bytes())
            raw[len(raw) // 2] ^= 0x01
            entry.write_bytes(bytes(raw))
        self.assertEqual(self.apply(), reference)


@unittest.skipUnless(RETAIL.is_file() and ART_ROOT.is_dir(), "retail ISO or the club art tree absent")
class VenueArt(RealStep):
    PREFIX = "s03"
    NAMES = ("s03dd.iff", "s03nr.iff")

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = mv.load_art(str(ART_ROOT))
        row = mv.venues()[cls.PREFIX]
        pins = {p["name"]: p for p in row["bundles"]}
        with mv._outer_image()(RETAIL) as archive:
            bundles = {}
            for name, pin in pins.items():
                entry = mv._entry(archive, pin)
                bundles[name] = archive.read(entry.virtual_offset, entry.size)
        plan = mv.plan_venue(cls.PREFIX, art["venues"].get(cls.PREFIX), bundles, art["league"])
        base = plan.pop("base")
        cls.jobs = [(name, bundles[name], None, plan, base, pins[name]["outer"], None) for name in cls.NAMES]

    def stream(self, workers):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        return sorted((name, after, json.dumps(edits, sort_keys=True, default=repr))
                      for name, after, edits in mv._stream(iter(self.jobs), workers))

    def test_serial_parallel_cold_and_warm_streams_agree_and_the_old_cap_returns_with_its_switch(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        self.mode("serial", "NFL2K5_SERIAL_VENUE_ART")
        os.environ["NFL2K5_BUILD_WORKERS"] = "1"
        reference, traced = self.trace(self.stream, None)
        traced_uses_only_declared(self, "venue-art", traced)
        self.assertEqual([r[0] for r in reference], sorted(self.NAMES))
        self.assertTrue(any(after != job[1] for (_n, after, _e), job in zip(reference, sorted(self.jobs))))
        self.mode("parallel", "NFL2K5_SERIAL_VENUE_ART")
        self.assertEqual(self.stream(2), reference)
        self.mode("cold", "NFL2K5_SERIAL_VENUE_ART")
        self.assertEqual(self.stream(3), reference)
        with patch.object(mv, "_compile_job", side_effect=AssertionError("a cache hit still compiled")):
            self.assertEqual(self.stream(3), reference)      # warm: every bundle comes from the cache
            self.assertEqual(self.stream(1), reference)

    def test_a_tampered_entry_is_recompiled(self):
        self.mode("cold", "NFL2K5_SERIAL_VENUE_ART")
        reference = self.stream(3)
        for entry in (Path(self.cache_root) / "venue-art").glob("*.json"):
            raw = bytearray(entry.read_bytes())
            raw[len(raw) // 2] ^= 0x01
            entry.write_bytes(bytes(raw))
        self.assertEqual(self.stream(3), reference)


if __name__ == "__main__":
    unittest.main()
