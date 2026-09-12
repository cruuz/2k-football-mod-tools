"""Bounded production build/cache/receipt regressions, with no retail bytes."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).parent)]
import b661_build_fixture as fixture
from nfl_txtr import encode_rgba_png, decompress_vc_lz
from mod_editor.core.nfl2k5_compile_cache import CompileCache
from mod_editor.core import nfl2k5_equipment_lz as lz


def backend():
    spec = importlib.util.spec_from_file_location("_b68_build", ROOT / "tools/nfl2k5_visual_mod_project.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WrittenBuildTests(unittest.TestCase):
    def test_real_encoders_cold_warm_one_change_and_receipt_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            equipment, _ = fixture.create(root)
            tool = backend()
            fixture.configure(tool, root)
            png = root / "jersey.png"
            png.write_bytes(encode_rgba_png(512, 256, bytes((30, 190, 220, 255)) * (512 * 256)))
            asset, equip_png = equipment.png(independent=False,
                rgba=bytes((20, 150, 80, 255)) * (32 * 32))
            project = root / "project.json"
            project.write_bytes(tool.canonical_json(dict(schema="nfl2k5_visual_mod_project/v1", purpose="T1 synthetic proof",
                edits=[dict(kind="torso", asset_code="18", side="H", variant=0,
                            clean_png=str(png), mud_png=None, mud_mode="darken_60"),
                       dict(kind="uniform_equipment_texture", asset_id=asset, png=str(equip_png))])))
            outputs = []
            for name, disabled, expected_hits, expected_misses in (
                    ("uncached", True, 0, 0), ("cold", False, 0, 2),
                    ("warm", False, 2, 0), ("one-change", False, 1, 1)):
                if name == "one-change":
                    png.write_bytes(encode_rgba_png(512, 256, bytes((130, 90, 20, 255)) * (512 * 256)))
                out, manifest, artifacts = root / (name + ".iso"), root / (name + ".json"), root / name
                log = io.StringIO()
                with patch.dict(os.environ, NFL2K5_DISABLE_COMPILE_CACHE="1" if disabled else "0"), \
                     contextlib.redirect_stdout(log):
                    result = tool.build(project, root / "source.iso", out, manifest, artifacts,
                                        root / "0", root / "inventory.json")
                self.assertIn(f"hits={expected_hits} misses={expected_misses}", log.getvalue())
                receipt_hash = tool.file_digest(manifest)
                with patch.object(tool, "prepare_project", side_effect=AssertionError("recompiled")), \
                     patch.object(tool, "verify_union", side_effect=AssertionError("full image scan")), \
                     patch.object(tool, "validate_source", side_effect=AssertionError("full source scan")):
                    verified = tool.verify_written(project, root / "source.iso", out, manifest, artifacts, receipt_hash)
                self.assertTrue(verified["written_spans_verified"])
                self.assertEqual(verified["output_sha256"], tool.file_digest(out))
                outputs.append(tool.file_digest(out))
                # A changed receipt cannot grant itself permission to skip reconstruction.
                with self.assertRaisesRegex(tool.ProjectError, "receipt hash"):
                    tool.verify_written(project, root / "source.iso", out, manifest, artifacts, "0" * 64)
                if name == "one-change":
                    # A gap mutation invalidates the saved full-image proof even
                    # though this verifier only reads spans and the directory.
                    with out.open("r+b") as stream:
                        stream.seek(128); stream.write(b"tamper")
                    with self.assertRaisesRegex(tool.ProjectError, "changed since"):
                        tool.verify_written(project, root / "source.iso", out, manifest, artifacts, receipt_hash)
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0], outputs[2])
            self.assertNotEqual(outputs[0], outputs[3])
            original_union = tool.verify_union
            def mutate_after_scan(source_fd, output_fd, size, edits):
                result = original_union(source_fd, output_fd, size, edits)
                tool.write_all(output_fd, 128, b"late mutation")
                return result
            with patch.object(tool, "verify_union", side_effect=mutate_after_scan), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 self.assertRaisesRegex(tool.ProjectError, "source or output changed"):
                tool.build(project, root / "source.iso", root / "raced.iso", root / "raced.json", root / "raced",
                           root / "0", root / "inventory.json")
            self.assertFalse((root / "raced.iso").exists())

    def test_402_units_one_edit_invalidates_one_and_grouped_inputs_invalidate_together(self):
        tool = backend()
        with tempfile.TemporaryDirectory() as folder:
            cache = CompileCache(Path(folder) / "cache")
            calls = 0
            inputs = [{"kind": "team_select", "target": i, "pixels": str(i)} for i in range(402)]
            def run():
                nonlocal calls
                for item in inputs:
                    key = tool.digest(tool.canonical_json(item))
                    result = cache.get(key)
                    if result is None:
                        calls += 1
                        cache.put(key, (item["pixels"].encode(), [("preview", b"png")], {"receipt": item}))
            run(); self.assertEqual(calls, 402)
            run(); self.assertEqual(calls, 402)
            inputs[201]["pixels"] = "edited"
            run(); self.assertEqual(calls, 403)
            edits = [dict(kind=tool.UNIFORM_EQUIPMENT_KIND, asset_id=f"tset:1:8:{i}:shoe") for i in range(3)]
            edits += [dict(kind=tool.UNIFORM_EQUIPMENT_KIND, asset_id="tset:2:8:0:shoe")]
            self.assertEqual(tool.compile_dependencies(0, edits), [0, 1, 2])
            self.assertEqual(tool.compile_dependencies(3, edits), [3])

    def test_parallel_uniform_path_schedules_only_misses(self):
        from concurrent.futures import Future
        tool = backend()
        calls = []
        class Pool:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def submit(self, function, arguments):
                calls.append(arguments[0])
                future = Future()
                future.set_result((b"span", [], {}, "selector", {}))
                return future
        with tempfile.TemporaryDirectory() as folder:
            cache = CompileCache(Path(folder) / "cache")
            edits = [dict(kind="torso", pixels=str(n)) for n in range(8)]
            def keys(order, dependencies):
                return tool.digest(tool.canonical_json(edits[order]))
            def run():
                with patch("concurrent.futures.ProcessPoolExecutor", Pool):
                    return list(tool._parallel_uniform_imports(edits, None, None, None,
                        None, None, Path(folder), 4, cache, keys))
            first = run()
            self.assertEqual(calls, list(range(8)))
            self.assertEqual(run(), first)
            self.assertEqual(calls, list(range(8)))
            edits[4]["pixels"] = "edited"
            self.assertEqual(run(), first)
            self.assertEqual(calls, [*range(8), 4])

    def test_corrupt_cache_is_disposable_and_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cache = CompileCache(root / "cache")
            key = "a" * 64
            cache.put(key, (b"span", {"a": [1, 2]}))
            self.assertEqual(cache.get(key), (b"span", {"a": [1, 2]}))
            (cache.root / (key + ".json")).write_bytes(b"broken")
            self.assertIsNone(cache.get(key))
            try:
                (root / "link").symlink_to(cache.root, target_is_directory=True)
            except (OSError, NotImplementedError):
                return
            self.assertIsNone(CompileCache(root / "link").get(key))


class NativeLzTests(unittest.TestCase):
    def test_native_and_python_match_bytes_and_roundtrip(self):
        helper = lz._optimal_helper()
        if helper is None:
            self.skipTest("Reviewed Linux x86-64 equipment helper absent or unsupported on this platform")
        rng = random.Random(68)
        corpus = [b"x", b"xx", b"abc", bytes(4096), b"aabaaaaabaaaaaababbaaba" * 80,
                  bytes(rng.randrange(16) for _ in range(8192)), bytes(range(256)) * 64]
        for bits in range(10, 14):
            for source in corpus:
                options = dict(stream_tag=0xFFFFFFFF, offset_bits=bits, max_encoded_size=65536)
                with patch.dict(os.environ, NFL2K5_DISABLE_NATIVE_LZ="1"):
                    expected = lz.compress_equipment_optimal(source, **options)
                with patch.dict(os.environ, NFL2K5_DISABLE_NATIVE_LZ="0"), \
                     patch.object(lz, "array", side_effect=AssertionError("native fell back")):
                    actual = lz.compress_equipment_optimal(source, **options)
                self.assertEqual(actual, expected)
                self.assertEqual(decompress_vc_lz(actual)[0], source)

    def test_bad_or_missing_helper_falls_back_and_bounds_still_apply(self):
        from types import SimpleNamespace
        with patch.object(lz.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b"bad")):
            actual = lz.compress_equipment_optimal(b"abc" * 80, stream_tag=1, offset_bits=12, max_encoded_size=400)
        self.assertEqual(decompress_vc_lz(actual)[0], b"abc" * 80)
        with self.assertRaisesRegex(lz.TxtrError, "search limit"):
            lz.compress_equipment_optimal(b"abc" * 80, stream_tag=1, offset_bits=12,
                                         max_encoded_size=400, max_candidate_comparisons=1)


if __name__ == "__main__":
    unittest.main()
