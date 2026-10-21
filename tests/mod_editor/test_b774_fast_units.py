"""b77.4 fast1: independent texture units compile in workers and a verified cache.

Bounded and synthetic (no retail bytes). The full-league byte-identity proof
lives in the fast1 report; these pin the contracts that proof relies on:
deterministic ordering, the receipt-order substitution, every cache-key
input, the code-version check, corrupt-entry handling, and that the worker
entry point survives the Windows ``spawn`` start method with the backend run
as a script, exactly as the Studio launches it.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).parent)]
from mod_editor.core.nfl2k5_compile_cache import CompileCache  # noqa: E402

TOOL = ROOT / "tools/nfl2k5_visual_mod_project.py"


def backend():
    spec = importlib.util.spec_from_file_location("_b774_fast_build", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Harness:
    """A project of N one-edit units with synthetic pins and a fake compiler."""

    def __init__(self, tool, root: Path, count=6, kind="live_face"):
        self.tool, self.root = tool, root
        (root / "code").mkdir()
        (root / "code/loaded.py").write_text("LOADED = 1\n")
        (root / "code/unrelated.py").write_text("UNRELATED = 1\n")
        self.calls = []
        edits = []
        self.pins = {}
        for number in range(count):
            png = root / f"art{number}.png"
            png.write_bytes(b"PNG-%d" % number)
            resolved = png.resolve()
            self.pins[resolved] = tool.InputPin(resolved, png.read_bytes(), png.stat().st_size,
                                                sha(png.read_bytes()), (0, number))
            if kind == "team_select":
                edits.append(dict(kind=kind, family="unif", asset_code="%02d" % number, side="home",
                                  style=0, resolution=256, png=str(png)))
            else:
                edits.append(dict(kind=kind, face_id="%04d" % number, family="f", png=str(png)))
        self.project = tool.ProjectFile(root / "project.json", b"",
                                        dict(schema="s", purpose="p", edits=edits), (0, 0))
        report = root / "report.json"
        report.write_bytes(b"{}")
        self.report_pins = {kind: tool.InputPin(report, b"{}", 2, sha(b"{}"), (0, 99))}
        self.report_paths = {kind: report}
        self.index = SimpleNamespace(path=root / "0", sha256="1" * 64)
        self.inventory = SimpleNamespace(path=root / "inventory.json", sha256="2" * 64)

    def fake_compile(self, kind, order, edit, project, pins, report_paths, index, inventory,
                     temp_root, temp_files):
        self.calls.append(edit["png"])
        pin = next(iter(pins.values()))
        names = {"span_file": f"{order:05d}_replacement.bin",
                 "manifest_file": f"{order:05d}_import.json",
                 "preview_file": f"{order:05d}_preview.png"}
        report = {"outputs": names, "input_png": {"path": f"{temp_root.path}/{order:05d}_input.png",
                                                    "file_name": f"{order:05d}_input.png"}}
        return "ok", [(b"SPAN" + pin.payload, [(names["preview_file"], b"PREVIEW" + pin.payload)],
                       report, edit.get("face_id", edit.get("asset_code")), {"pin": pin.sha256})]

    def units(self, cache, indices=None):
        return self.tool.IndependentUnits(
            self.project, self.pins, self.report_paths, self.report_pins, self.index,
            self.inventory, self.root, 1, cache,
            list(range(len(self.project.value["edits"]))) if indices is None else indices)

    @contextlib.contextmanager
    def patched(self):
        with patch.object(self.tool, "_unit_compile", side_effect=self.fake_compile), \
             patch.object(self.tool, "ROOT", self.root), \
             patch.object(self.tool, "_UNIT_NATIVE_HELPERS", ()), \
             patch.object(self.tool, "_loaded_code_files", return_value=("code/loaded.py",)):
            yield

    def receipt(self, result, edit):
        # What the serial loop writes: the raw report still names the
        # worker's private input copy until it is normalized.
        if result is None or result[0] != "ok":
            return result
        return result[0], [(span, previews, self.tool.canonical_json(
            self.tool.normalized_import_report(report, edit, edit["kind"])), selector, target)
            for span, previews, report, selector, target in result[1]]

    def run(self, cache, first_order=0):
        results = []
        units = self.units(cache)
        try:
            for index, edit in enumerate(self.project.value["edits"]):
                results.append(self.receipt(units.take(index, first_order + index), edit))
        finally:
            units.close()
        return units, results


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.tool = backend()

    def built(self, report, previews=None):
        name = self.tool._UNIT_PLACEHOLDER_PREFIX
        return [(b"span", previews if previews is not None else [(name + "preview.png", b"png")],
                 report, "selector", {"selector": "selector"})]

    def test_only_derived_names_change_and_the_receipt_is_checked_after_normalizing(self):
        name = self.tool._UNIT_PLACEHOLDER_PREFIX
        edit = {"kind": "live_face", "png": "/project/face.png"}
        report = {"outputs": {"span_file": name + "replacement.bin", "preview_file": name + "preview.png"},
                  "preview": {"file_name": name + "preview.png"},
                  "input_png": {"path": "/tmp/.unit-compile-x/" + name + "input.png",
                                "file_name": name + "input.png"}}
        patched = self.tool.unit_assign_order(self.built(report), 42, edit, "live_face")
        self.assertIsNotNone(patched)
        (_, previews, patched_report, _, _), = patched
        self.assertEqual(previews, [("00042_preview.png", b"png")])
        self.assertEqual(patched_report["outputs"], {"span_file": "00042_replacement.bin",
                                                     "preview_file": "00042_preview.png"})
        normalized = self.tool.normalized_import_report(patched_report, edit, "live_face")
        self.assertEqual(normalized["input_png"], {"path": "/project/face.png", "file_name": "face.png"})

    def test_a_result_that_mentions_the_placeholder_or_worker_folder_elsewhere_is_refused(self):
        edit = {"kind": "live_face", "png": "/project/face.png"}
        for report in ({"note": f"made for {self.tool._UNIT_PLACEHOLDER_ORDER} later"},
                       {"scratch": "/tmp/.unit-compile-x/a.bin"},
                       {self.tool._UNIT_PLACEHOLDER_TEXT + "-key": 1}):
            self.assertIsNone(self.tool.unit_assign_order(self.built(report), 7, edit, "live_face"))
        # An edit-order unit has no placeholder, but its worker folder still may not leak.
        self.assertIsNone(self.tool.unit_assign_order(
            self.built({"scratch": "/tmp/.unit-compile-x"}, previews=[]), None, edit, "torso"))
        self.assertIsNotNone(self.tool.unit_assign_order(
            self.built({"ok": True}, previews=[]), None, edit, "torso"))

    def test_placeholder_is_beyond_any_project_span_order(self):
        # Portraits split in two at most; every other unit is one span.
        self.assertGreater(self.tool._UNIT_PLACEHOLDER_ORDER, 2 * self.tool.MAX_EDITS)
        self.assertEqual(self.tool.UNIT_KINDS & {"uniform_equipment_texture", "unif_color",
                                                 "crib_scene_texture"}, set())

    def test_worker_count_setting(self):
        with patch.dict(os.environ, NFL2K5_BUILD_WORKERS="3"):
            self.assertEqual(self.tool.unit_worker_count(), 3)
        with patch.dict(os.environ, NFL2K5_BUILD_WORKERS="0"):
            self.assertEqual(self.tool.unit_worker_count(), 1)
        with patch.dict(os.environ, NFL2K5_BUILD_WORKERS="many"), \
             patch.object(self.tool, "_available_memory", return_value=None), \
             patch.object(self.tool.os, "cpu_count", return_value=12), \
             patch.object(self.tool.os, "sched_getaffinity", return_value=set(range(12)), create=True):
            self.assertEqual(self.tool.unit_worker_count(), 11)
        with patch.dict(os.environ, {}, clear=False), \
             patch.object(self.tool, "_available_memory", return_value=2 * 640 * 1024 ** 2), \
             patch.object(self.tool.os, "sched_getaffinity", return_value=set(range(32)), create=True):
            os.environ.pop("NFL2K5_BUILD_WORKERS", None)
            self.assertEqual(self.tool.unit_worker_count(), 2)


class PendingOrphanTests(unittest.TestCase):
    def test_an_old_pending_temporary_is_swept_and_a_fresh_one_kept(self):
        """fx1 (review r2-build MINOR 4): a build killed mid-write left .pending-* files nothing ever removed."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "cache"
            cache = CompileCache(root)
            cache.put("warm", {"value": 1})
            old, fresh = root / ".pending-old", root / ".pending-fresh"
            old.write_bytes(b"x" * 64)
            fresh.write_bytes(b"y" * 64)
            stale = 2 * 3600
            os.utime(old, (old.stat().st_atime - stale, old.stat().st_mtime - stale))
            CompileCache(root).put("next", {"value": 2})
            self.assertFalse(old.exists())
            self.assertTrue(fresh.exists())
            self.assertEqual(CompileCache(root).get("warm"), {"value": 1})


class UnitCacheTests(unittest.TestCase):
    def setUp(self):
        self.tool = backend()
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name).resolve()
        self.harness = Harness(self.tool, self.root)
        self.cache = CompileCache(self.root / "cache")

    def tearDown(self):
        self.folder.cleanup()

    def test_cold_warm_and_uncached_results_are_identical_and_in_order(self):
        with self.harness.patched():
            _, uncached = self.harness.run(CompileCache(None), first_order=10)
            cold_units, cold = self.harness.run(self.cache, first_order=10)
            calls = len(self.harness.calls)
            warm_units, warm = self.harness.run(self.cache, first_order=10)
        self.assertEqual(uncached, cold)
        self.assertEqual(cold, warm)
        self.assertEqual((cold_units.hits, cold_units.misses), (0, 6))
        self.assertEqual((warm_units.hits, warm_units.misses), (6, 0))
        self.assertEqual(len(self.harness.calls), calls, "a warm cache must not recompile")
        for number, (outcome, built) in enumerate(warm):
            self.assertEqual(outcome, "ok")
            self.assertEqual(built[0][1][0][0], f"{10 + number:05d}_preview.png")
            self.assertIn(f'"span_file": "{10 + number:05d}_replacement.bin"'.encode(), built[0][2])
            self.assertEqual(built[0][0], b"SPANPNG-%d" % number)

    def test_span_order_is_applied_on_every_hit_not_stored(self):
        with self.harness.patched():
            self.harness.run(self.cache, first_order=0)
            _, shifted = self.harness.run(self.cache, first_order=500)
        self.assertIn(b'"span_file": "00500_replacement.bin"', shifted[0][1][0][2])

    def test_key_covers_every_input_and_nothing_else(self):
        units = self.harness.units(CompileCache(None))
        base = units.key(0)
        self.assertEqual(units.key(0), base)
        changed = []
        edits = self.harness.project.value["edits"]
        original = dict(edits[0])
        edits[0]["face_id"] = "9999"
        changed.append(units.key(0))
        edits[0].clear(); edits[0].update(original)
        png = Path(edits[0]["png"]).resolve()
        pin = self.harness.pins[png]
        self.harness.pins[png] = pin.__class__(pin.path, b"other", 5, sha(b"other"), pin.identity)
        changed.append(units.key(0))
        self.harness.pins[png] = pin
        for field, value in (("index", "3" * 64), ("inventory", "4" * 64)):
            saved = units._context[field]
            units._context[field] = value
            changed.append(units.key(0))
            units._context[field] = saved
        saved = units._context["reports"]
        units._context["reports"] = {"live_face": "5" * 64}
        changed.append(units.key(0))
        units._context["reports"] = saved
        for env in ({"NFL2K5_MARKS_PACK": "/elsewhere"}, {"NFL2K5_DISABLE_NATIVE_LZ": "1"}):
            with patch.dict(os.environ, env):
                changed.append(self.harness.units(CompileCache(None)).key(0))
        with patch.object(self.tool, "_unit_toolchain", return_value={"PIL": "0.0"}):
            changed.append(self.harness.units(CompileCache(None)).key(0))
        self.assertEqual(len(set(changed)), len(changed))
        self.assertNotIn(base, changed)
        self.assertEqual(units.key(0), base)
        # Worker and cache switches select how, never what.
        with patch.dict(os.environ, NFL2K5_BUILD_WORKERS="7", NFL2K5_COMPILE_CACHE_MAX_MB="5",
                        NFL2K5_DISABLE_COMPILE_CACHE="0"):
            self.assertEqual(self.harness.units(CompileCache(None)).key(0), base)

    def test_edit_order_kinds_key_their_edit_index(self):
        harness = Harness(self.tool, self.root / "ts" if (self.root / "ts").mkdir() is None else None,
                          count=2, kind="team_select")
        units = harness.units(CompileCache(None))
        edits = harness.project.value["edits"]
        edits[1].update({key: edits[0][key] for key in ("asset_code", "png")})
        harness.pins = {**harness.pins}
        self.assertNotEqual(units.key(0), units.key(1))
        span_units = self.harness.units(CompileCache(None))
        face = self.harness.project.value["edits"]
        face[1].update(face_id=face[0]["face_id"], png=face[0]["png"])
        self.assertEqual(span_units.key(0), span_units.key(1))

    def test_kit_layers_keep_the_span_order_where_the_old_parallel_path_did_not_run(self):
        folder = self.root / "small"
        folder.mkdir()
        harness = Harness(self.tool, folder, count=2, kind="team_select")
        legacy = harness.units(CompileCache(None))
        span = self.tool.IndependentUnits(
            harness.project, harness.pins, harness.report_paths, harness.report_pins,
            harness.index, harness.inventory, folder, 1, CompileCache(None), [0, 1], ())
        self.assertEqual(legacy._task(1)[1], 1)
        self.assertEqual(span._task(1)[1], self.tool._UNIT_PLACEHOLDER_ORDER)
        self.assertNotEqual(legacy.key(1), span.key(1))
        with harness.patched():
            self.assertEqual(span.take(0, 40)[1][0][1][0][0], "00040_preview.png")
            self.assertEqual(legacy.take(0, 40)[1][0][1][0][0], "00000_preview.png")

    def test_importer_notes_print_in_project_order_and_not_on_a_hit(self):
        def noisy(kind, order, edit, *rest):
            print("NOTE", edit["face_id"])
            return self.harness.fake_compile(kind, order, edit, *rest)
        with self.harness.patched(), patch.object(self.tool, "_unit_compile", side_effect=noisy):
            for expected in (["NOTE %04d" % n for n in range(6)], []):
                printed = io.StringIO()
                with contextlib.redirect_stdout(printed):
                    self.harness.run(self.cache)
                self.assertEqual(printed.getvalue().splitlines(), expected)

    def test_only_a_change_to_loaded_compiler_code_invalidates(self):
        with self.harness.patched():
            self.harness.run(self.cache)
            (self.root / "code/unrelated.py").write_text("UNRELATED = 2\n")
            units, _ = self.harness.run(self.cache)
            self.assertEqual((units.hits, units.misses), (6, 0))
            (self.root / "code/loaded.py").write_text("LOADED = 2\n")
            calls = len(self.harness.calls)
            units, again = self.harness.run(self.cache)
            self.assertEqual((units.hits, units.misses), (0, 6))
            self.assertEqual(len(self.harness.calls), calls + 6)
            units, _ = self.harness.run(self.cache)
            self.assertEqual((units.hits, units.misses), (6, 0))

    def test_a_native_helper_change_invalidates_even_though_it_is_never_imported(self):
        helper = self.root / "tools/nfl2k5_equipment_optimal"
        helper.parent.mkdir()
        helper.write_bytes(b"one")
        with self.harness.patched(), patch.object(self.tool, "_UNIT_NATIVE_HELPERS",
                                                  ("tools/nfl2k5_equipment_optimal",)):
            self.harness.run(self.cache)
            self.assertEqual(self.harness.run(self.cache)[0].hits, 6)
            helper.write_bytes(b"two")
            self.assertEqual(self.harness.run(self.cache)[0].hits, 0)

    def test_corrupt_or_tampered_entries_recompile(self):
        import zlib
        from mod_editor.core.nfl2k5_compile_cache import _decode, _encode
        with self.harness.patched():
            _, expected = self.harness.run(self.cache)
            units = self.harness.units(self.cache)
            keys = [units.key(n) for n in range(6)]
            units.close()
            (self.cache.root / f"{keys[0]}.json").write_bytes(b"not json")
            stored = self.cache.get(keys[1])
            record = _decode(json.loads(zlib.decompress(stored["unit_zlib"])))
            span, previews, report, selector, target = record["value"][0]
            record["value"][0] = (b"TAMPERED", previews, report, selector, target)
            text = json.dumps(_encode(record), separators=(",", ":"))
            self.cache.put(keys[1], {"unit_zlib": zlib.compress(text.encode())})
            self.cache.put(keys[2], {"unit_zlib": zlib.compress(text.encode())[:20]})
            self.cache.put(keys[3], {"unit_zlib": b"\x00" * 9})
            record = _decode(json.loads(zlib.decompress(self.cache.get(keys[4])["unit_zlib"])))
            record["code"] = {"code/loaded.py": "0" * 64}
            text = json.dumps(_encode(record), separators=(",", ":"))
            self.cache.put(keys[4], {"unit_zlib": zlib.compress(text.encode())})
            calls = len(self.harness.calls)
            units, results = self.harness.run(self.cache)
            self.assertEqual(results, expected)
            self.assertEqual((units.hits, units.misses), (1, 5))
            self.assertEqual(len(self.harness.calls), calls + 5)
            units, results = self.harness.run(self.cache)
            self.assertEqual((units.hits, units.misses), (6, 0))
            self.assertEqual(results, expected)

    def test_values_json_cannot_round_trip_are_not_cached(self):
        def odd(*args):
            outcome, built = self.harness.fake_compile(*args)
            built[0][2]["ratio"] = float("nan")  # JSON keeps it, but nan != nan
            return outcome, built
        with self.harness.patched(), patch.object(self.tool, "_unit_compile", side_effect=odd):
            self.harness.run(self.cache)
            units, _ = self.harness.run(self.cache)
        self.assertEqual(units.hits, 0)

    def test_worker_errors_and_unproved_results_fall_back_to_the_serial_loop(self):
        def broken(kind, order, edit, *rest):
            if edit["face_id"] == "0001":
                raise ValueError("bad art")
            if edit["face_id"] == "0002":
                return "ok", [(b"s", [], {"note": f"{order}"}, "x", {})]
            return self.harness.fake_compile(kind, order, edit, *rest)
        with self.harness.patched(), patch.object(self.tool, "_unit_compile", side_effect=broken):
            units, results = self.harness.run(self.cache)
            self.assertIsNone(results[1])
            self.assertIsNone(results[2])
            self.assertEqual(units.fallbacks, 2)
            self.assertIsNotNone(results[0])
            # Neither is remembered: the next build tries the workers again.
            units, _ = self.harness.run(self.cache)
            self.assertEqual((units.hits, units.misses), (4, 2))

    def test_kept_retail_outcome_is_cached(self):
        row = {"kind": "live_number_nameplate", "outcome": "kept_retail", "selector": "s"}
        with self.harness.patched(), patch.object(self.tool, "_unit_compile",
                                                  return_value=("kept", row)):
            _, cold = self.harness.run(self.cache)
            units, warm = self.harness.run(self.cache)
        self.assertEqual(cold, warm)
        self.assertEqual(warm[0], ("kept", row))
        self.assertEqual(units.hits, 6)

    def test_units_are_taken_in_submission_order_only(self):
        with self.harness.patched():
            units = self.harness.units(CompileCache(None))
            try:
                with self.assertRaisesRegex(self.tool.ProjectError, "out of order"):
                    units.take(1, 0)
            finally:
                units.close()

    def test_cache_size_setting(self):
        from mod_editor.core import nfl2k5_compile_cache as cache_module
        with patch.dict(os.environ, NFL2K5_COMPILE_CACHE_MAX_MB="3"):
            self.assertEqual(cache_module.max_cache_bytes(), 3 * 1024 * 1024)
        with patch.dict(os.environ, NFL2K5_COMPILE_CACHE_MAX_MB="x"):
            self.assertEqual(cache_module.max_cache_bytes(), cache_module.MAX_CACHE_BYTES)
        cache = CompileCache(self.root / "small")
        with patch.dict(os.environ, NFL2K5_COMPILE_CACHE_MAX_MB="1"):
            for number in range(6):
                cache.put("%064x" % number, {"blob": os.urandom(400 * 1024)})
        total = sum(path.stat().st_size for path in cache.root.glob("*.json"))
        self.assertLessEqual(total, 1024 * 1024)
        self.assertIsNotNone(cache.get("%064x" % 5))


# A driver run the way the Studio runs the backend: as a script, so the pool's
# children re-run it as __mp_main__ under the spawn start method (the only one
# Windows has). It executes the backend's source as its own module, exactly as
# `python tools/nfl2k5_visual_mod_project.py build ...` does.
DRIVER = textwrap.dedent('''
    import os, pickle, sys
    from pathlib import Path
    TOOL = os.environ["B774_TOOL"]
    sys.path[:0] = [os.environ["B774_ROOT"], os.environ["B774_ROOT"] + "/tools",
                    os.environ["B774_ROOT"] + "/tests/mod_editor"]
    DRIVER_FILE, __file__ = __file__, TOOL
    SOURCE = open(TOOL, encoding="utf-8").read()
    SOURCE = SOURCE[:SOURCE.rindex('if __name__ == "__main__":')]
    exec(compile(SOURCE, TOOL, "exec"))
    # The backend's ROOT is resolved; spawn re-runs this driver (with the
    # fixture below) in each child, as it re-runs the backend script.
    __file__ = DRIVER_FILE
    import b661_build_fixture as fixture
    fixture.configure(sys.modules[__name__], Path(os.environ["B774_FIXTURE"]))

    if __name__ == "__main__":
        from nfl_txtr import encode_rgba_png
        from mod_editor.core.nfl2k5_compile_cache import CompileCache
        root = Path(os.environ["B774_FIXTURE"])
        edits, pins = [], {}
        for number in range(9):
            png = root / f"jersey{number}.png"
            png.write_bytes(encode_rgba_png(512, 256, bytes((20 * number, 190, 220 - number, 255)) * (512 * 256)))
            edits.append(dict(kind="torso", asset_code="18", side="H", variant=0,
                              clean_png=str(png), mud_png=None, mud_mode="darken_60"))
            pins[png.resolve()] = InputPin(png.resolve(), png.read_bytes(), png.stat().st_size,
                                           digest(png.read_bytes()), (0, number))
        project = ProjectFile(root / "project.json", b"", dict(schema="s", purpose="p", edits=edits), (0, 0))
        meta = root / "targets.json"
        report_pins = {"torso": InputPin(meta, meta.read_bytes(), meta.stat().st_size,
                                         digest(meta.read_bytes()), (0, 0))}
        index = ownership.pin_large_file(root / "0", "pack", INDEX_SIZE, INDEX_SHA256)
        inventory = ownership.pin_large_file(root / "inventory.json", "inventory",
                                             INVENTORY_SIZE, INVENTORY_SHA256)
        outputs = {}
        for workers in (1, 3):
            units = IndependentUnits(project, pins, {"torso": meta}, report_pins, index, inventory,
                                     root, workers, CompileCache(None), list(range(len(edits))))
            try:
                pooled = units._pool is not None
                outputs[workers] = [units.take(n, 100 + n) for n in range(len(edits))]
            finally:
                units.close()
            assert pooled == (workers > 1), (workers, pooled)
        def receipt(item, edit):
            outcome, built = item
            return [(span, previews, canonical_json(normalized_import_report(report, edit, "torso")),
                     selector, target) for span, previews, report, selector, target in built]
        assert all(item is not None for item in outputs[1] + outputs[3]), outputs[3]
        serial = [receipt(item, edit) for item, edit in zip(outputs[1], edits)]
        pooled = [receipt(item, edit) for item, edit in zip(outputs[3], edits)]
        assert serial == pooled
        assert len({item[0][0] for item in pooled}) == len(edits)
        # A task and its answer cross the process boundary as plain data.
        task = units._task(0)
        assert pickle.loads(pickle.dumps(task))[2] == edits[0]
        print("B774_SPAWN_OK", digest(pickle.dumps(pooled)), flush=True)
''')


class SpawnTests(unittest.TestCase):
    def test_backend_run_as_a_script_compiles_units_in_spawned_workers_byte_for_byte(self):
        import b661_build_fixture as fixture
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            fixture.create(root)
            driver = root / "driver.py"
            driver.write_text(DRIVER, encoding="utf-8")
            environment = dict(os.environ, B774_TOOL=str(TOOL), B774_ROOT=str(ROOT),
                               B774_FIXTURE=str(root))
            environment.pop("NFL2K5_BUILD_WORKERS", None)
            result = subprocess.run([sys.executable, str(driver)], cwd=root, env=environment,
                                    capture_output=True, text=True, timeout=600)
            self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-3000:])
            self.assertIn("B774_SPAWN_OK", result.stdout)

    def test_worker_entry_points_are_top_level_and_picklable(self):
        tool = backend()
        for function in (tool._unit_worker, tool._unit_compile, tool._loaded_code_files):
            self.assertEqual(function.__qualname__, function.__name__)
            self.assertIs(pickle.loads(pickle.dumps(function)), function)
        self.assertIn("tools/nfl2k5_visual_mod_project.py", Path(TOOL).relative_to(ROOT).as_posix())
        with tempfile.TemporaryDirectory() as folder:
            outcome, text, code = tool._unit_worker(("live_face", 0, {"kind": "live_face", "png": "x.png"},
                                                     None, {}, {}, Path(folder), Path(folder), Path(folder)))
            self.assertEqual((outcome, code), ("error", ()))
            self.assertTrue(text)

    def test_main_calls_freeze_support_before_parsing(self):
        source = TOOL.read_text(encoding="utf-8")
        tail = source[source.rindex('if __name__ == "__main__":'):]
        self.assertLess(tail.index("freeze_support()"), tail.index("main()"))


class Book:
    def __init__(self, team):
        self.team = team

    def resolved_targets(self):
        return (self.team,)


class PlaybookStepMemoTests(unittest.TestCase):
    def test_identical_install_steps_compile_once_and_return_independent_copies(self):
        from mod_editor.core import nfl2k5_playbook_pack as packs
        calls = []

        class Compiled:
            def __init__(self, payload):
                self.replacement, self.report = payload, {"steps": []}

            def __eq__(self, other):
                return (self.replacement, self.report) == (other.replacement, other.report)

        def fake(before, pack, asset_id, xbe):
            calls.append((before, asset_id, xbe))
            return Compiled(before[::-1])
        pack = SimpleNamespace(name="p")
        packs._COMPILED_INSTALL_STEPS.clear()
        with patch.object(packs, "apply_pack_to_resource",
                          side_effect=lambda before, pack, asset_id, xbe: fake(before, pack, asset_id, xbe)):
            first = packs._compile_install_step(b"abc", pack, "ARZ", b"xbe")
            first.report["steps"].append("mutated by a caller")
            second = packs._compile_install_step(b"abc", pack, "ARZ", b"xbe")
            self.assertEqual(len(calls), 1)
            self.assertEqual(second.report, {"steps": []})
            for before, team, xbe in ((b"abd", "ARZ", b"xbe"), (b"abc", "ATL", b"xbe"),
                                      (b"abc", "ARZ", b"other"), (b"abc", "ARZ", None)):
                packs._compile_install_step(before, pack, team, xbe)
            self.assertEqual(len(calls), 5)
            packs._compile_install_step(b"abc", SimpleNamespace(name="q"), "ARZ", b"xbe")
            self.assertEqual(len(calls), 6)
            with patch.dict(os.environ, NFL2K5_DISABLE_COMPILE_CACHE="1"):
                packs._compile_install_step(b"abc", pack, "ARZ", b"xbe")
            self.assertEqual(len(calls), 7)
        packs._COMPILED_INSTALL_STEPS.clear()

    def test_parallel_warm_helper_runs_as_a_script_and_never_invents_steps(self):
        # Synthetic books cannot compile: the helper (spawn pool, three
        # workers) must hand back nothing, so the installer compiles serially.
        request = pickle.dumps({"chains": [(b"not a book %d" % n, [(SimpleNamespace(), "ARZ")])
                                           for n in range(3)], "xbe": b"xbe", "workers": 3})
        result = subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_playbook_warm.py")],
                                input=request, capture_output=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(pickle.loads(result.stdout), [[], [], []])

    def test_warm_pool_workers_end_when_the_helper_is_killed(self):
        """fx1 (review pr69 #1): a cancelled build kills the helper; its spawn pool workers must not live on."""
        import signal
        import tempfile
        import time
        script = (
            "import os, sys, time, multiprocessing\n"
            f"sys.path.insert(0, {str(ROOT / 'tools')!r})\n"
            "import nfl2k5_playbook_warm as warm\n"
            "from concurrent.futures import ProcessPoolExecutor\n"
            "if __name__ == '__main__':\n"
            "    pool = ProcessPoolExecutor(1, mp_context=multiprocessing.get_context('spawn'),\n"
            "                               initializer=warm._exit_with_parent)\n"
            "    print(pool.submit(os.getpid).result(), flush=True)\n"
            "    pool.submit(time.sleep, 120)\n"
            "    time.sleep(120)\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "helper_standin.py"
            path.write_text(script, encoding="utf-8", newline="\n")
            helper = subprocess.Popen([sys.executable, str(path)], stdout=subprocess.PIPE, text=True)
            try:
                worker = int(helper.stdout.readline())
            finally:
                helper.kill()
                helper.wait()
            deadline = time.monotonic() + 20
            alive = True
            while alive and time.monotonic() < deadline:
                try:
                    if os.name == "nt":
                        import ctypes
                        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, worker)
                        code = ctypes.c_ulong()
                        alive = bool(handle) and ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) \
                            and code.value == 259
                        if handle:
                            ctypes.windll.kernel32.CloseHandle(handle)
                    else:
                        os.kill(worker, 0)
                        if os.path.exists("/proc/self/stat"):   # Linux: an unreaped zombie counts as ended
                            with open(f"/proc/{worker}/stat", encoding="ascii") as stat:
                                alive = stat.read().rsplit(")", 1)[1].split()[0] != "Z"
                except (OSError, ProcessLookupError):
                    alive = False
                if alive:
                    time.sleep(0.1)
            if alive and os.name != "nt":
                os.kill(worker, signal.SIGKILL)
            self.assertFalse(alive, "the pool worker outlived the killed helper")

    def test_prewarm_seeds_only_the_memo_and_skips_what_is_already_compiled(self):
        from mod_editor.core import nfl2k5_playbook_pack as packs
        entries = [SimpleNamespace(size=packs.RESOURCE_SIZE) for _ in range(3)]
        books = {0: b"A" * 8, 1: b"B" * 8, 2: b"C" * 8}

        class Archive:
            def __init__(self):
                self.entries = entries

            def read_entry(self, index):
                return books[index]
        loaded = [("a", SimpleNamespace(book=Book("ARZ"))), ("b", SimpleNamespace(book=Book("ATL")))]
        compiled = SimpleNamespace(replacement=b"done")
        seen = []

        class Popen:
            returncode = 0

            def __init__(self, argv, **kwargs):
                seen.append(argv)

            def communicate(self, payload, timeout=None):
                request = pickle.loads(payload)
                return pickle.dumps([[(packs.install_step_key(before, None, steps[0][1], request["xbe"]),
                                       compiled)] for before, steps in request["chains"]]), b""
        packs._COMPILED_INSTALL_STEPS.clear()
        try:
            with patch("subprocess.Popen", Popen), patch.dict(os.environ, NFL2K5_BUILD_WORKERS="4"), \
                 patch.object(packs, "install_step_key",
                              side_effect=lambda before, p, team, xbe: (team, before, xbe)):
                self.assertEqual(packs.prewarm_install_steps(
                    Archive(), loaded, {"ARZ": 0, "ATL": 1}, b"xbe"), 2)
                self.assertEqual(packs.prewarm_install_steps(
                    Archive(), loaded, {"ARZ": 0, "ATL": 1}, b"xbe"), 0)
                self.assertEqual(len(seen), 1, "a warm memo must not start the helper again")
                self.assertEqual(packs.prewarm_install_steps(
                    Archive(), loaded, {"ARZ": 0, "ATL": 9}, b"xbe"), 0)
                with patch.dict(os.environ, NFL2K5_DISABLE_COMPILE_CACHE="1"):
                    packs._COMPILED_INSTALL_STEPS.clear()
                    self.assertEqual(packs.prewarm_install_steps(
                        Archive(), loaded, {"ARZ": 0, "ATL": 1}, b"xbe"), 0)
            self.assertEqual(len(seen), 1)
        finally:
            packs._COMPILED_INSTALL_STEPS.clear()


if __name__ == "__main__":
    unittest.main()
