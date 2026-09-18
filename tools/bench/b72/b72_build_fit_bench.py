"""Beta 72: the Build-time equipment fit pass on real retail spans.

Measures what rc97 moved out of project open and into Build: N physical TSET
groups checked by _parallel_equipment_fits. Read-only; no disc is written.

  QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=$PWD \
  python3 -u b72_build_fit_bench.py --index "<extracted>/vc_53450030/0" --groups 32
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(os.environ.get("B72_ROOT", Path.cwd())).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_uniform_equipment_writer as writer  # noqa: E402
from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode  # noqa: E402
from tools import nfl2k5_visual_mod_project as backend  # noqa: E402


def stripes(width, height):
    return b"".join(bytes((20, 60, 140, 255) if (y // 7) % 3 == 0 else
                          (240, 245, 250, 255) if (y // 7) % 3 == 1 else (170, 35, 55, 255))
                    for y in range(height) for x in range(width))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--groups", type=int, default=32)
    parser.add_argument("--workers", default="1,8")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    targets, _ = writer.load_targets()
    socks = sorted((t for t in targets.values() if t.name in ("socks00", "socks00_mud")),
                   key=lambda t: (t.outer_index, t.chunk_index, t.reference_index))
    groups_by_key = {}
    for target in socks:
        groups_by_key.setdefault((target.outer_index, target.chunk_index), []).append(target)
    keys = sorted(groups_by_key)[:args.groups]

    rows = []
    with tempfile.TemporaryDirectory(prefix="b72-build-fit-") as folder:
        root = Path(folder)
        edits, groups = [], {}
        for n, key in enumerate(keys):
            for target in groups_by_key[key]:
                rgba = stripes(target.width, target.height)
                png = root / f"{n}_{target.reference_index}.png"
                png.write_bytes(with_import_mode(
                    writer.encode_rgba_png(target.width, target.height, rgba),
                    target.asset_id, rgba, independent=True, scale=1))
                edit = dict(kind="uniform_equipment_texture", asset_id=target.asset_id, png=str(png))
                edits.append(edit)
                groups.setdefault(key, []).append(edit)
        project_path = root / "project.json"
        project_path.write_bytes(backend.canonical_json(
            dict(schema=backend.SCHEMA, purpose="B72 build fit bench", edits=edits)))
        project = backend.read_project(project_path)
        pins = backend.pin_project_inputs(project)
        for workers in (int(w) for w in args.workers.split(",")):
            cache = writer.EquipmentCompileCache()
            writer._STAGED_CACHE.clear()
            writer._PARSE_CACHE.clear()
            started = time.monotonic()
            backend._parallel_equipment_fits(groups, project, pins, Path(args.index), cache, workers)
            seconds = time.monotonic() - started
            row = dict(workers=workers, groups=len(groups), replacements=len(edits),
                       seconds=seconds, seconds_per_group=seconds / max(1, len(groups)),
                       cached_groups=len(cache.compiled), cache_limit=cache.compiled_limit,
                       output_disc_written=False)
            rows.append(row)
            print("B72 BUILDFIT " + json.dumps(row), flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
