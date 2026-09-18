"""Beta 72: one real retail equipment compile unit, timed and profiled.

Read-only: it reads the extracted retail pack, compiles one physical TSET in
memory and writes nothing to the source. No disc is produced.

  QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=$PWD \
  python3 -u b72_retail_equipment_bench.py --index "<extracted>/vc_53450030/0"
"""
from __future__ import annotations

import argparse
import cProfile
import io
import json
import os
import pstats
import random
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.environ.get("B72_ROOT", Path.cwd())).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_uniform_equipment_writer as writer  # noqa: E402
from mod_editor.core import nfl2k5_equipment_lz as lz  # noqa: E402
from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode  # noqa: E402


def photo(width, height, seed=72):
    rng = random.Random(seed)
    out = bytearray()
    for y in range(height):
        for x in range(width):
            base = (30 + (x * 200) // max(1, width), 40 + (y * 180) // max(1, height),
                    60 + ((x + y) * 150) // max(2, width + height))
            out += bytes(min(255, max(0, c + rng.randrange(-12, 13))) for c in base) + b"\xff"
    return bytes(out)


def sheet(width, height, seed=73):
    rng = random.Random(seed)
    out = bytearray()
    for y in range(height):
        for x in range(width):
            cell = ((x * 4) // max(1, width)) + 4 * ((y * 4) // max(1, height))
            edge = (x * 4) % max(1, width) < 3 or (y * 4) % max(1, height) < 3
            base = (245, 245, 250) if cell % 2 else (16, 24, 40)
            if edge:
                base = tuple(min(255, max(0, c + rng.randrange(-90, 91))) for c in base)
            out += bytes(base) + b"\xff"
    return bytes(out)


def stripes(width, height):
    return b"".join(bytes((20, 60, 140, 255) if (y // 7) % 3 == 0 else
                          (240, 245, 250, 255) if (y // 7) % 3 == 1 else (170, 35, 55, 255))
                    for y in range(height) for x in range(width))


DESIGNS = {"photo": photo, "sheet": sheet,
           "stripes": lambda w, h: stripes(w, h)}


def compile_once(index, names, design, *, helper, scale=1, profile=None):
    targets, _ = writer.load_targets()
    chosen = [t for t in targets.values() if t.name in names]
    chosen.sort(key=lambda t: (t.outer_index, t.chunk_index, t.reference_index))
    if not chosen:
        raise SystemExit(f"no retail target named {names}")
    first = chosen[0]
    group = [t for t in chosen
             if (t.outer_index, t.chunk_index) == (first.outer_index, first.chunk_index)]
    row = {"design": design, "helper": helper, "scale": scale,
           "set_selector": first.set_selector,
           "targets": [f"{t.name} {t.width}x{t.height}" for t in group]}
    with tempfile.TemporaryDirectory(prefix="b72-retail-") as folder:
        edits = []
        for target in group:
            rgba = DESIGNS[design](target.width, target.height)
            png = Path(folder) / f"{target.name}.png"
            png.write_bytes(with_import_mode(
                writer.encode_rgba_png(target.width, target.height, rgba),
                target.asset_id, rgba, independent=True, scale=scale))
            edits.append((target.asset_id, png))
        writer._STAGED_CACHE.clear()
        writer._PARSE_CACHE.clear()
        guard = patch.object(lz, "_optimal_helper", return_value=None)
        stack = guard if not helper else patch.object(writer, "MAX_DECODED_BYTES",
                                                      writer.MAX_DECODED_BYTES)
        with stack:
            start = time.perf_counter()
            if profile:
                profile.enable()
            try:
                compiled = writer.build_unified_uniform_equipment_imports(
                    Path(index), edits, preflight_only=True)
                row["outcome"] = "fit"
                row["encoded_bytes"] = compiled.rebuild_info.recompressed_bytes
                row["budget_bytes"] = compiled.rebuild_info.stored_size if hasattr(
                    compiled.rebuild_info, "stored_size") else None
            except writer.EquipmentFitError as error:
                row["outcome"] = "refused"
                row["budget_bytes"] = error.budget
                row["required_bytes"] = error.required
            except writer.EquipmentRefitError as error:
                row["outcome"] = "refit_error"
                row["message"] = str(error)[:200]
            finally:
                if profile:
                    profile.disable()
            row["seconds"] = time.perf_counter() - start
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--designs", default="stripes,sheet,photo")
    parser.add_argument("--out", default=None)
    parser.add_argument("--no-disk-cache", action="store_true")
    args = parser.parse_args()
    if args.no_disk_cache:
        def _no_disk(index, key):
            raise OSError("disk stage cache disabled for this benchmark")
        writer._stage_disk_cache = _no_disk
    rows = []
    for names in (("socks00", "socks00_mud"), ("shoes01",)):
        for design in args.designs.split(","):
            for helper in (True, False):
                profile = cProfile.Profile() if args.profile else None
                row = compile_once(args.index, names, design, helper=helper, profile=profile)
                rows.append(row)
                print("B72 RETAIL " + json.dumps(row), flush=True)
                if profile:
                    buffer = io.StringIO()
                    pstats.Stats(profile, stream=buffer).sort_stats("cumulative").print_stats(24)
                    print(f"===== {names} {design} helper={helper} =====", flush=True)
                    print(buffer.getvalue(), flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
