"""Large-build bookkeeping stays linear and quiet stages keep reporting progress."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import nfl2k5_visual_mod_project as backend
from mod_editor.core import nfl2k5_compile_cache as cache_module
from mod_editor.core.nfl2k5_build_service import (
    BuildStage, CommandResult, Nfl2k5BuildService, SubprocessBuildCommandRunner,
)


class CacheBookkeepingTests(unittest.TestCase):
    def test_cold_cache_scans_once_then_accounts_for_each_new_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "cache"
            cache = cache_module.CompileCache(root)
            scans = []
            original = Path.glob
            def glob(path, pattern):
                if path == root:
                    scans.append(pattern)
                return original(path, pattern)
            with mock.patch.object(Path, "glob", glob):
                for index in range(1000):
                    cache.put(f"{index:064x}", (b"compiled bytes", {"index": index}))
            self.assertEqual(scans, ["*.json"])
            self.assertEqual(cache._bytes, sum(path.stat().st_size for path in root.glob("*.json")))
            self.assertEqual(cache.get(f"{999:064x}"), (b"compiled bytes", {"index": 999}))

    def test_external_atomic_write_invalidates_directory_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "cache"
            cache = cache_module.CompileCache(root)
            cache.put("a" * 64, b"first")
            other = cache_module.CompileCache(root)
            other.put("b" * 64, b"other process")
            # A second writer can replace an existing path as well as add one.
            other.put("a" * 64, b"longer replacement from the other process")
            cache.put("c" * 64, b"third")
            self.assertEqual(cache.get("a" * 64), b"longer replacement from the other process")
            self.assertEqual(cache._bytes, sum(path.stat().st_size for path in root.glob("*.json")))
            self.assertEqual(len(cache._entries), 3)

    def test_overwrite_and_lru_eviction_keep_the_byte_budget(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "cache"
            cache = cache_module.CompileCache(root)
            cache.put("a" * 64, b"a" * 100)
            one_entry = cache._bytes
            with mock.patch.object(cache_module, "MAX_CACHE_BYTES", one_entry * 2):
                cache.put("b" * 64, b"b" * 100)
                self.assertIsNotNone(cache.get("a" * 64))
                cache.put("c" * 64, b"c" * 100)
                self.assertIsNone(cache.get("b" * 64))
                self.assertIsNotNone(cache.get("a" * 64))
                cache.put("a" * 64, b"short")
                self.assertLessEqual(cache._bytes, one_entry * 2)
                self.assertEqual(cache._bytes, sum(path.stat().st_size for path in root.glob("*.json")))

    def test_contended_cache_writer_skips_caching_without_blocking_a_build(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "cache"
            cache = cache_module.CompileCache(root)
            with mock.patch.object(cache_module.platform_compat, "exclusive_nonblocking_lock",
                                   side_effect=BlockingIOError("another build owns the cache")):
                cache.put("a" * 64, b"compiled result")
            self.assertFalse((root / ("a" * 64 + ".json")).exists())
            cache.put("a" * 64, b"compiled result")
            self.assertEqual(cache.get("a" * 64), b"compiled result")


class _CountedRows(list):
    iterations = 0
    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


class ProjectIndexTests(unittest.TestCase):
    def test_9500_dependencies_and_receipt_lookups_use_one_shared_index(self):
        edits = _CountedRows(dict(kind="p8_texture", asset_id=f"p8:{i}:0", png="same.png") for i in range(9500))
        groups = backend.compile_dependency_groups(edits)
        dependencies_iterations = edits.iterations
        indices = backend.project_edit_indices(edits)
        indexed_iterations = edits.iterations
        for index, row in enumerate(edits):
            self.assertEqual(backend.compile_dependencies(index, edits, groups), [index])
            self.assertEqual(indices(row), [index])
        self.assertEqual(dependencies_iterations, 2)
        self.assertEqual(indexed_iterations, 3)
        self.assertEqual(edits.iterations, 4)

    def test_shared_stadium_equipment_and_crib_units_preserve_original_order(self):
        edits = [
            dict(kind=backend.UNIFORM_EQUIPMENT_KIND, asset_id="tset:1:8:0:shoe"),
            dict(kind=backend.STADIUM_TEXTURE_KIND, target="nfl2k5.stadium.o3149.c0005.scene01.texture0002"),
            dict(kind=backend.CRIB_SCENE_TEXTURE_KIND, selector="one"),
            dict(kind=backend.CRIB_SCENE_TEXTURE_KIND, selector="two"),
            dict(kind=backend.UNIFORM_EQUIPMENT_KIND, asset_id="tset:1:8:1:glove"),
            dict(kind=backend.STADIUM_GEOMETRY_KIND, target="nfl2k5.stadium.o3149.c0005.scene01"),
            dict(kind=backend.CRIB_SCENE_GEOMETRY_KIND, target="nfl2k5.crib.o0001.c0001.scene01"),
            dict(kind=backend.CRIB_SCENE_TEXTURE_KIND, selector="three"),
            dict(kind=backend.CRIB_SCENE_TEXTURE_KIND, selector="four"),
            dict(kind="team_select"),
        ]
        with mock.patch.object(backend.crib_scene_adapter, "TARGETS", {"one": (0, 1), "two": (0, 2), "three": (0, 1), "four": (0, 3)}):
            indexed = backend.compile_dependency_groups(edits)
        expected = [[0, 4], [1, 5], [2, 6, 7], [3, 8], [0, 4], [1, 5], [2, 6, 7], [2, 6, 7], [3, 8], [9]]
        self.assertEqual([indexed[i] for i in range(len(edits))], expected)
        self.assertIs(indexed[2], indexed[7])
        lookup = backend.project_edit_indices(edits)
        self.assertEqual(lookup(dict(kind="unit", edits=[{"target": edits[4]["asset_id"]}, {"target": edits[0]["asset_id"]}])), [0, 4])
        self.assertEqual(lookup(dict(kind="unit", edits=[{"target": edits[1]["target"]}, {"target": edits[5]["target"]}])), [1, 5])


class QuietProgressTests(unittest.TestCase):
    def test_finished_copy_heartbeat_advances_to_checking_changes(self):
        class ControlledRunner(SubprocessBuildCommandRunner):
            def run(self, command, cwd, poll=None, line_sink=None):
                staged.write_bytes(b"half")
                clock[0] += 2
                poll()
                staged.write_bytes(b"complete")
                clock[0] += 2
                poll()
                return CommandResult(tuple(command), 0, "", "")
        with tempfile.TemporaryDirectory() as td:
            staged = Path(td) / "building.iso"
            clock, events = [100.0], []
            service = Nfl2k5BuildService(runner=ControlledRunner())
            with mock.patch("mod_editor.core.nfl2k5_build_service.time.monotonic", side_effect=lambda: clock[0]):
                service._run_build_command(("python", "backend", "build"), staged, 8, events.append)
            self.assertIn("Copying disc image", events[0].message)
            self.assertEqual((events[0].completed, events[0].total), (4, 8))
            self.assertIn("Checking project changes", events[1].message)
            self.assertEqual(events[1].total, 0)

    def test_real_subprocess_emits_elapsed_heartbeat_without_disc_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = []
            service = Nfl2k5BuildService(runner=SubprocessBuildCommandRunner())
            result = service._run_build_command((sys.executable, "-c", "import time; time.sleep(2.2)"),
                                                root / "absent.iso", 100, events.append)
            self.assertEqual(result.returncode, 0)
            self.assertGreaterEqual(len(events), 2)
            self.assertTrue(all("elapsed" in event.message for event in events))
            self.assertTrue(all(event.stage == BuildStage.BUILDING for event in events))

    def test_heartbeat_preserves_item_counts_during_a_quiet_encode(self):
        class ControlledRunner(SubprocessBuildCommandRunner):
            def run(self, command, cwd, poll=None, line_sink=None):
                line_sink("NFL2K5_BUILD_ITEM " + json.dumps(dict(message="Encoding texture 9500", done=9499, total=9500)))
                clock[0] += 2
                poll()
                return CommandResult(tuple(command), 0, "", "")
        with tempfile.TemporaryDirectory() as td:
            clock = [100.0]
            events = []
            service = Nfl2k5BuildService(runner=ControlledRunner())
            with mock.patch("mod_editor.core.nfl2k5_build_service.time.monotonic", side_effect=lambda: clock[0]):
                service._run_build_command(("python", "backend", "build"), Path(td) / "absent.iso", 100, events.append)
            self.assertEqual((events[-1].completed, events[-1].total), (9499, 9500))
            self.assertIn("Encoding texture 9500 (0:02 elapsed)", events[-1].message)

    def test_verification_heartbeat_reports_verifying_after_full_copy(self):
        class ControlledRunner(SubprocessBuildCommandRunner):
            def run(self, command, cwd, poll=None, line_sink=None):
                clock[0] += 2
                poll()
                return CommandResult(tuple(command), 0, "", "")
        with tempfile.TemporaryDirectory() as td:
            staged = Path(td) / "finished.iso"
            staged.write_bytes(b"done")
            clock = [100.0]
            events = []
            service = Nfl2k5BuildService(runner=ControlledRunner())
            with mock.patch("mod_editor.core.nfl2k5_build_service.time.monotonic", side_effect=lambda: clock[0]):
                service._run_build_command(("python", "backend", "verify"), staged, 4, events.append)
            self.assertEqual(events[-1].stage, BuildStage.VERIFYING)
            self.assertIn("elapsed", events[-1].message)


if __name__ == "__main__":
    unittest.main()
