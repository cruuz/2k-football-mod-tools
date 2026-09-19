"""Beta 72.1: a Build never stops on a clock, and refits what cannot fit.

Beta 71.1 gave the pure-Python optimal parse a 5-second wall clock. On a slow
or busy Windows laptop that clock, not the art, refused shoes that fit (Coach
Edwards: "Equipment optimal fit reached its 5-second limit"). The interactive
quick check keeps its clock but reports "fit pending"; Build and Refit finish
every search, and Build applies exactly the Refit equipment result to art the
complete measurement proves cannot fit.
"""
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MOD_STUDIO_NO_UPDATE_CHECK", "1")

import b661_build_fixture as build_fixture
import test_nfl2k5_equipment_import as session_fixture
from test_b69_j1_fit import tight_fixture
from test_b68_t1_build import backend
from mod_editor.core import equipment_staging as staging
from mod_editor.core import nfl2k5_equipment_lz as lz
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.equipment_reporting import project_fit_labels, verified_build_refit_lines
from mod_editor.core.nfl2k5_equipment_lz import compress_equipment_optimal
from nfl_txtr import HEADER, decode_chunk, parse_chunks

RETAIL_INDEX = Path(os.environ.get("NFL2K5_RETAIL_INDEX",
                                   ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))


def optimal_only_fixture(root):
    """A 528-byte span this two-colour art fits ONLY through the optimal parse.

    Every palette rung's greedy stream misses (smallest 539 bytes); the
    optimal parse of the best rung needs 526. Chosen by exhaustive search.
    """
    f, _ = tight_fixture(root, family=8)
    encoded = min((compress_equipment_optimal(f.decoded, stream_tag=1, offset_bits=bits,
                                              max_encoded_size=10000) for bits in (10, 11, 12)), key=len)
    stored = 528
    f.span = (HEADER.pack(b"TSET", stored, f.chunk.system_bytes, f.chunk.video_bytes, 0xFEEDBEEF, stored, 0, 0)
              + encoded + bytes(stored - len(encoded)))
    f.chunk = replace(parse_chunks(f.span)[0], index=8)
    f.pack.write_bytes(f.span)
    return f, optimal_only_art()


def optimal_only_art():
    rng = random.Random(24)
    palette = [bytes((rng.randrange(256), rng.randrange(256), rng.randrange(256), 255)) for _ in range(2)]
    return b"".join(palette[rng.randrange(2)] if rng.random() < 0.3 else palette[0] for _ in range(1024))


def tight_art():
    """The unfittable 32x32 art ``tight_fixture`` returns (464-byte span)."""
    rng = random.Random(69)
    return b"".join(bytes((rng.randrange(256), rng.randrange(256), rng.randrange(256), 255))
                    for _ in range(1024))


class quick_check_seconds:
    """Model a slow laptop: the interactive check's clock runs out at once."""

    def __init__(self, seconds):
        self.seconds = seconds

    def __enter__(self):
        self.token = lz._TIME_LIMIT.set(self.seconds)

    def __exit__(self, *exc):
        lz._TIME_LIMIT.reset(self.token)


def fresh_caches():
    writer._PARSE_CACHE.clear()
    writer.staged_equipment_cache().clear()


def run_cli_build(root, edits, *, quick_check=None):
    project = root / "project.json"
    project.write_bytes(backend().canonical_json(dict(
        schema="nfl2k5_visual_mod_project/v1", purpose="beta 72.1 equipment build", edits=edits)))
    command = [sys.executable, str(Path(build_fixture.__file__)), str(root), "build",
               "--project", str(project), "--source-xiso", str(root / "source.iso"),
               "--output-xiso", str(root / "built.iso"), "--manifest", str(root / "receipt.json"),
               "--artifact-dir", str(root / "artifacts"), "--index", str(root / "0"),
               "--inventory", str(root / "inventory.json")]
    environment = dict(os.environ)
    if quick_check is not None:
        environment["B721_QUICK_CHECK_SECONDS"] = str(quick_check)
    return subprocess.run(command, capture_output=True, text=True, timeout=120, cwd=ROOT, env=environment)


def built_equipment(root):
    manifest = json.loads((root / "receipt.json").read_bytes())
    row = next(edit for edit in manifest["edits"] if edit["kind"] == "uniform_equipment_texture")
    report = json.loads((root / "artifacts" / row["import_report"]["file_name"]).read_bytes())
    start = row["target"]["absolute_span_offset"]
    span = (root / "built.iso").read_bytes()[start:start + row["replacement"]["span_size"]]
    return report, span


def session_harness(test, factory):
    harness = session_fixture.EquipmentSessionTests()
    with patch("test_nfl2k5_equipment_import.Fixture", factory):
        harness.setUp()
    test.addCleanup(harness.doCleanups)
    return harness


class QuickCheckClockTests(unittest.TestCase):
    def test_clock_limited_quick_check_is_pending_and_never_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            f, rgba = optimal_only_fixture(Path(folder))
            asset_id, png = f.png(rgba=rgba)
            fresh_caches()
            with f.context(), quick_check_seconds(0.0):
                rows = writer.preflight_project_equipment(f.pack, [(None, asset_id, png)])
            self.assertEqual(rows[0]["fit_status"], "fit pending")
            self.assertIn("second limit", rows[0]["fit_error"])
            # Beta 72 stored this timeout in memory AND beside pack 0, so every
            # later Build replayed it without measuring anything.
            self.assertFalse(writer.staged_equipment_cache().failures)
            self.assertFalse(any("optimal_error" in record for record in writer._PARSE_CACHE.values()))
            stage = Path(folder) / ".nfl2k5-equipment-stage-cache"
            self.assertFalse(any(b"fit_failure" in path.read_bytes() for path in stage.glob("*.json")))
            with f.context(), lz.uncapped_optimal_fit():
                rows = writer.preflight_project_equipment(f.pack, [(None, asset_id, png)])
                compiled = writer.build_unified_uniform_equipment_imports(
                    f.pack, [(asset_id, png)], preflight_only=True)
            self.assertEqual(rows[0]["fit_status"], "fits")
            self.assertEqual(compiled.rebuild_info.strategy, "optimal_token_parse")
            self.assertEqual(compiled.rebuild_info.recompressed_bytes, 526)
            # The same disk cache now holds the real, measured fit.
            self.assertTrue(list(stage.glob("*.json")))

    def test_import_stages_art_whose_quick_check_runs_out_of_time(self):
        harness = session_harness(self, lambda root: optimal_only_fixture(root)[0])
        asset_id, png = harness.f.png(rgba=optimal_only_art())
        asset = harness.assets[asset_id]
        fresh_caches()
        with harness.f.context(), quick_check_seconds(0.0):
            result = staging.stage_equipment_import(harness.a, asset, png, independent=True)
        # Beta 72 refused this import outright on a slow PC.
        self.assertEqual(result.changed_asset_ids, (asset_id,))
        self.assertIn("Build finishes its fit", result.message)
        self.assertEqual(project_fit_labels(harness.a)[asset_id], "fit pending; checked when you build")
        with harness.f.context(), lz.uncapped_optimal_fit():
            rows = staging.equipment_fit_rows(harness.a)
        self.assertEqual([row["fit_status"] for row in rows], ["fits"])

    def test_build_fits_art_whose_fit_outlasts_the_quick_check(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "equipment").mkdir()
            f, rgba = optimal_only_fixture(root / "equipment")
            build_fixture.create(root, equipment=f)
            asset_id, png = f.png(rgba=rgba)
            completed = run_cli_build(root, [dict(kind="uniform_equipment_texture", asset_id=asset_id,
                                                  png=str(png))], quick_check=0.0)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            report, span = built_equipment(root)
            self.assertEqual(report["compression"]["strategy"], "optimal_token_parse")
            self.assertNotIn("auto_refit", report)
            chunk = parse_chunks(span)[0]
            decoded, _ = decode_chunk(span, chunk)
            textures, _ = writer._validate_layout(f.decoded, f.chunk, f.rows)
            texture = replace(textures[0], pixel_offset=report["edits"][0]["pixel_offset"])
            self.assertEqual(writer.decode_equipment_levels(decoded, chunk, texture)[0], rgba)

    def test_long_search_reports_progress_and_never_times_out_when_uncapped(self):
        beats = []
        clock = iter(range(0, 10_000_000, 3))
        data = bytes(range(256)) * 64
        slow_clock = SimpleNamespace(monotonic=lambda: next(clock))
        with patch.object(lz, "_optimal_helper", return_value=None), \
                patch.object(lz, "time", slow_clock), \
                lz.uncapped_optimal_fit(lambda: beats.append(1)):
            self.assertFalse(lz.optimal_fit_is_capped())
            lz.compress_equipment_optimal(data, stream_tag=1, offset_bits=12, max_encoded_size=1 << 20)
        self.assertTrue(beats)
        self.assertTrue(lz.optimal_fit_is_capped())

    def test_retail_coach_shoe_is_pending_at_import_and_fits_at_build(self):
        # Coach Edwards' exact span, tset:3660:8:0:shoes01 (06H0), with the
        # mud sibling Studio stages beside it. 64x64 art fits only through the
        # optimal parse (12 bytes spare). Python fallback, as on Windows.
        if not RETAIL_INDEX.is_file():
            self.skipTest("private retail pack 0 unavailable")
        from tools.bench.b72.b72_retail_equipment_bench import photo
        from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
        by_id, _ = writer.load_targets()
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(writer, "_stage_disk_cache", side_effect=OSError("read-only")))
            stack.enter_context(patch.dict(os.environ, {"NFL2K5_DISABLE_NATIVE_LZ": "1"}))
            edits = []
            for name, reference in (("shoes01", 0), ("shoes01_mud", 1)):
                target = by_id[f"tset:3660:8:{reference}:{name}"]
                rgba = photo(target.width, target.height)
                path = Path(folder) / f"{name}.png"
                path.write_bytes(with_import_mode(writer.encode_rgba_png(target.width, target.height, rgba),
                                                  target.asset_id, rgba, independent=True, scale=4))
                edits.append((target.asset_id, path))
            fresh_caches()
            with quick_check_seconds(0.2):
                rows = writer.preflight_project_equipment(RETAIL_INDEX, [(None, a, p) for a, p in edits])
            self.assertEqual({row["fit_status"] for row in rows}, {"fit pending"})
            rows, substitutes, refits = writer.auto_refit_group(RETAIL_INDEX, edits, Path(folder))
        self.assertEqual([row["fit_status"] for row in rows], ["fits", "fits"])
        self.assertEqual((substitutes, refits), ({}, []))
        self.assertLessEqual(max(row["encoded_bytes"] for row in rows), 54_720)


class BuildRefitTests(unittest.TestCase):
    def test_unfittable_shoe_build_refits_like_the_refit_button_and_lists_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "equipment").mkdir()
            f, rgba = tight_fixture(root / "equipment", family=8)
            build_fixture.create(root, equipment=f)
            asset_id, png = f.png(rgba=rgba)
            completed = run_cli_build(root, [dict(kind="uniform_equipment_texture", asset_id=asset_id,
                                                  png=str(png))])
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("NFL2K5_VISUAL_MOD_BUILD_PASS edits=1", completed.stdout)
            report, built_span = built_equipment(root)
            refit = report["auto_refit"][0]
            self.assertEqual((refit["asset_id"], refit["fit_summary"]), (asset_id, "fitted at 16 x 16, 2 colours"))
            self.assertEqual((refit["budget"], refit["required"]), (464, 664))
            lines = verified_build_refit_lines(root / "receipt.json")
            self.assertEqual(len(lines), 1)
            self.assertIn("Build refitted equipment SYNTHETIC / shoes01: fitted at 16 x 16, 2 colours", lines[0])
            self.assertIn("Your project still has your original art", lines[0])
            receipts = [json.loads(line.split(" ", 1)[1]) for line in completed.stdout.splitlines()
                        if line.startswith("NFL2K5_FIT_RECEIPT ")]
            # The project's own art is recorded truthfully: it still needs refit.
            self.assertTrue(receipts and all(row["fit_status"] == "needs refit"
                                             for rows in receipts for row in rows))

        # The Refit button on the same art in a Studio session.
        harness = session_harness(self, lambda root: tight_fixture(root, family=8)[0])
        asset = harness.assets[asset_id]
        _, session_png = harness.f.png(rgba=rgba)
        harness.a.replace_batch(((asset, session_png),))
        fresh_caches()
        with harness.f.context():
            refitted = staging.refit_equipment(harness.a, asset_id)
            staged = harness.a.current_path(asset).read_bytes()
            span = harness.f.build([(asset_id, harness.a.current_path(asset))])[0]
        self.assertEqual(refitted.changed_asset_ids, (asset_id,))
        self.assertEqual(hashlib.sha256(staged).hexdigest(), refit["refit_png_sha256"])
        self.assertEqual(span, built_span)

    def test_build_refits_in_studio_order_beside_a_fitting_sibling(self):
        def factory(root):
            return tight_fixture(root, family=4, names=("socks00", "socks00_mud", "untouched"))[0]
        harness = session_harness(self, factory)
        f = harness.f
        normal, mud = f.rows[:2]
        _, normal_png = f.png(rgba=tight_art())
        _, mud_png = f.png(1, independent=False, rgba=bytes((90, 20, 10, 255)) * 1024)
        edits = [(normal.asset_id, normal_png), (mud.asset_id, mud_png)]
        fresh_caches()
        with f.context(), tempfile.TemporaryDirectory() as folder:
            rows, substitutes, refits = writer.auto_refit_group(f.pack, edits, Path(folder))
        self.assertEqual(sorted(substitutes), [normal.asset_id])
        self.assertEqual([row["asset_id"] for row in refits], [normal.asset_id])
        self.assertEqual({row["fit_status"] for row in rows}, {"fits"})
        harness.a.replace_batch(tuple((harness.assets[key], path) for key, path in edits))
        fresh_caches()
        with f.context():
            staging.refit_equipment(harness.a, normal.asset_id)
        self.assertEqual(harness.a.current_path(harness.assets[normal.asset_id]).read_bytes(),
                         substitutes[normal.asset_id])
        self.assertEqual(harness.a.current_path(harness.assets[mud.asset_id]).read_bytes(), mud_png.read_bytes())

    def test_parallel_worker_returns_refit_bytes_and_truthful_receipts(self):
        tool = backend()
        with tempfile.TemporaryDirectory() as folder:
            f, rgba = tight_fixture(Path(folder), family=8)
            asset_id, png = f.png(rgba=rgba)
            fresh_caches()
            with f.context(), patch.object(tool, "uniform_equipment_adapter", writer), \
                    patch.object(tool, "_EQUIPMENT_WORKER_CACHE", None):
                rows, records, substitutes, refits = tool._equipment_fit_worker(
                    (f.pack, [(asset_id, str(png))], folder, 0, 1))
            self.assertEqual([row["fit_status"] for row in rows], ["fits"])
            self.assertTrue(records)
            self.assertEqual(list(substitutes), [asset_id])
            receipt = tool._equipment_receipt_rows(rows, refits)
            self.assertEqual(receipt[0]["fit_status"], "needs refit")
            self.assertIn("Build refits it on the disc", receipt[0]["fit_error"])
            self.assertEqual(sorted(Path(folder).glob(".equipment-refit-*")), [])


if __name__ == "__main__":
    unittest.main()
