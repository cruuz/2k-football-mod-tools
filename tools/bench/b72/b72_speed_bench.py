"""Beta 72 speed benchmark: equipment texture import, refit and project open.

Run from the repo root (a worktree is fine):

  QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 \
  PYTHONPATH=$PWD python3 -u beta72_evidence/speed/b72_speed_bench.py --mode import

Artwork profiles model what testers actually import: striped socks (few
colours), AI-generated sheets and photographic cleats (thousands of colours),
against tight and generous retail spans. "windows" runs force the reviewed
Linux helper off, which is what every Windows and macOS user gets.
"""
from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import random
import sys
import time
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.environ.get("B72_ROOT", Path.cwd())).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests/mod_editor")]

from b70_equipment_fixture import SizedFixture  # noqa: E402
import test_nfl2k5_equipment_import as session_tests  # noqa: E402
from test_nfl2k5_equipment_import import EquipmentSessionTests  # noqa: E402
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer  # noqa: E402
from mod_editor.core import nfl2k5_equipment_lz as lz  # noqa: E402
from mod_editor.core.equipment_staging import stage_equipment_import, refit_equipment  # noqa: E402


def stripes(width):
    return b"".join(bytes((20, 60, 140, 255) if (y // 7) % 3 == 0 else
                          (240, 245, 250, 255) if (y // 7) % 3 == 1 else (170, 35, 55, 255))
                    for y in range(width) for x in range(width))


def photo(width, seed=72):
    """Smooth lighting plus fine grain: thousands of distinct colours."""
    rng = random.Random(seed)
    out = bytearray()
    for y in range(width):
        for x in range(width):
            base = (30 + (x * 200) // width, 40 + (y * 180) // width,
                    60 + ((x + y) * 150) // (2 * width))
            out += bytes((min(255, max(0, c + rng.randrange(-12, 13))) for c in base)) + b"\xff"
    return bytes(out)


def sheet(width, seed=73):
    """AI-generated number sheet: flat blocks with anti-aliased edges."""
    rng = random.Random(seed)
    out = bytearray()
    for y in range(width):
        for x in range(width):
            cell = ((x * 4) // width) + 4 * ((y * 4) // width)
            edge = (x * 4) % width < 3 or (y * 4) % width < 3
            base = (245, 245, 250) if cell % 2 else (16, 24, 40)
            if edge:
                base = tuple(min(255, max(0, c + rng.randrange(-90, 91))) for c in base)
            out += bytes(base) + b"\xff"
    return bytes(out)


DESIGNS = {"stripes": stripes, "photo": photo, "sheet": sheet}

# name, width, family, margin, design
CASES = [
    ("sock256_stripes", 256, 4, 1000, "stripes"),
    ("sock256_sheet", 256, 4, 1000, "sheet"),
    ("sock256_photo", 256, 4, 1000, "photo"),
    ("shoe64_stripes", 64, 8, 128, "stripes"),
    ("shoe64_sheet", 64, 8, 128, "sheet"),
    ("shoe64_photo", 64, 8, 128, "photo"),
    ("shoe128_photo", 128, 8, 512, "photo"),
]


def clear():
    writer._STAGED_CACHE.clear()
    writer._PARSE_CACHE.clear()


def one_import(case, *, helper, profile=None, refit=False):
    name, width, family, margin, design = case
    harness = EquipmentSessionTests()
    factory = lambda root: SizedFixture(root, width=width, family=family, margin=margin,
                                        names=("socks00", "socks00_mud", "untouched") if family == 4 else None)
    with patch.object(session_tests, "Fixture", factory):
        harness.setUp()
    row = {"case": name, "helper": helper, "width": width}
    try:
        f = harness.f
        rgba = DESIGNS[design](width)
        row["distinct_colours"] = len({rgba[i:i + 4] for i in range(0, len(rgba), 4)})
        row["span_budget_bytes"] = f.chunk.stored_size
        asset, path = f.png(rgba=rgba)
        guard = patch.object(lz, "_optimal_helper", return_value=None) if not helper else None
        with f.context():
            ctx = guard if guard is not None else patch.object(lz, "ping", create=True)
            with ctx:
                clear()
                start = time.perf_counter()
                if profile:
                    profile.enable()
                try:
                    stage_equipment_import(harness.a, harness.asset, path, independent=True, scale=1)
                    row["outcome"] = "fit"
                except writer.EquipmentFitError as error:
                    row["outcome"] = "refused"
                    row["required"] = error.required
                    row["budget"] = error.budget
                except writer.EquipmentRefitError as error:
                    row["outcome"] = "refit_error"
                    row["message"] = str(error)[:160]
                finally:
                    if profile:
                        profile.disable()
                row["seconds"] = time.perf_counter() - start
                start = time.perf_counter()
                try:
                    stage_equipment_import(harness.a, harness.asset, path, independent=True, scale=1)
                except writer.EquipmentRefitError:
                    pass
                row["repeat_seconds"] = time.perf_counter() - start
                if refit and row["outcome"] != "fit":
                    start = time.perf_counter()
                    try:
                        refit_equipment(harness.a, harness.asset.asset_id)
                        row["refit_outcome"] = "fit"
                    except Exception as error:  # noqa: BLE001
                        row["refit_outcome"] = type(error).__name__
                    row["refit_seconds"] = time.perf_counter() - start
    finally:
        harness.doCleanups()
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="import", choices=["import", "profile"])
    parser.add_argument("--case", default=None)
    parser.add_argument("--helper", default="both", choices=["both", "on", "off"])
    parser.add_argument("--refit", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    cases = [c for c in CASES if args.case in (None, c[0])]
    helpers = {"both": [True, False], "on": [True], "off": [False]}[args.helper]
    rows = []
    for case in cases:
        for helper in helpers:
            if args.mode == "profile":
                profile = cProfile.Profile()
                row = one_import(case, helper=helper, profile=profile, refit=args.refit)
                buffer = StringIO()
                pstats.Stats(profile, stream=buffer).sort_stats("cumulative").print_stats(28)
                row["profile"] = buffer.getvalue()
                print(f"===== {case[0]} helper={helper} =====", flush=True)
                print(row["profile"], flush=True)
            else:
                row = one_import(case, helper=helper, refit=args.refit)
            rows.append({k: v for k, v in row.items() if k != "profile"})
            print("B72 IMPORT " + json.dumps({k: v for k, v in row.items() if k != "profile"}), flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
