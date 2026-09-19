"""Beta 72: one real retail equipment fit, replayed on each shipped writer.

Loads mod_editor/core/nfl2k5_uniform_equipment_writer.py and
mod_editor/core/nfl2k5_equipment_lz.py out of each release commit and runs the
same compile against the same read-only retail span and the same artwork.

Caveat (same as the beta 71.1 T5 probe): shared support modules
(equipment_palette, nfl_txtr, nfl2k5_digit_texture) come from the CURRENT tree,
so this isolates the writer/LZ owners, not three complete shipped applications.

  QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONPATH=$PWD \
  python3 -u b72_version_bench.py --index "<extracted>/vc_53450030/0"
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType

ROOT = Path(os.environ.get("B72_ROOT", Path.cwd())).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_equipment_lz as current_lz
from mod_editor.core import nfl2k5_uniform_equipment_writer as current  # noqa: E402
from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode  # noqa: E402

REVISIONS = [("beta-68 / rc93", "b48a07b9"), ("beta-69 / rc94", "42a0e609"),
             ("beta-70 / rc95", "b7eccf8e"), ("beta-71 / rc96", "02bbadd1"),
             ("beta-71.1 / rc97", "088e3f41"), ("beta-72 / rc98 candidate", None)]


def historical(revision, path, name):
    source = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=ROOT,
                            check=True, capture_output=True).stdout
    module = ModuleType(name)
    module.__file__ = str(ROOT / path)
    sys.modules[name] = module
    exec(compile(source, f"{revision}:{path}", "exec"), module.__dict__)
    return module


def photo(width, height, seed=72):
    rng = random.Random(seed)
    out = bytearray()
    for y in range(height):
        for x in range(width):
            base = (30 + (x * 200) // width, 40 + (y * 180) // height,
                    60 + ((x + y) * 150) // (width + height))
            out += bytes(min(255, max(0, c + rng.randrange(-12, 13))) for c in base) + b"\xff"
    return bytes(out)


def sheet(width, height, seed=73):
    rng = random.Random(seed)
    out = bytearray()
    for y in range(height):
        for x in range(width):
            cell = ((x * 4) // width) + 4 * ((y * 4) // height)
            edge = (x * 4) % width < 3 or (y * 4) % height < 3
            base = (245, 245, 250) if cell % 2 else (16, 24, 40)
            if edge:
                base = tuple(min(255, max(0, c + rng.randrange(-90, 91))) for c in base)
            out += bytes(base) + b"\xff"
    return bytes(out)


DESIGNS = {"photo": photo, "sheet": sheet}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--names", default="socks00,socks00_mud")
    parser.add_argument("--design", default="photo")
    parser.add_argument("--out", default=None)
    parser.add_argument("--revision", default=None, help="optional commit or current for a focused replay")
    args = parser.parse_args()

    names = set(args.names.split(","))
    targets, _ = current.load_targets()
    chosen = sorted((t for t in targets.values() if t.name in names),
                    key=lambda t: (t.outer_index, t.chunk_index, t.reference_index))
    first = chosen[0]
    group = [t for t in chosen if (t.outer_index, t.chunk_index) == (first.outer_index, first.chunk_index)]
    rows = []
    with tempfile.TemporaryDirectory(prefix="b72-version-") as folder:
        pngs = []
        for target in group:
            rgba = DESIGNS[args.design](target.width, target.height)
            png = Path(folder) / f"{target.name}.png"
            png.write_bytes(with_import_mode(
                current.encode_rgba_png(target.width, target.height, rgba),
                target.asset_id, rgba, independent=True, scale=1))
            pngs.append((target.asset_id, png))
        for label, revision in REVISIONS:
            if args.revision is not None and args.revision != (revision or 'current'):
                continue
            # Shared support owners remain current, as in the supplied probe.
            if revision is None:
                lz, writer = current_lz, current
                sys.modules['mod_editor.core.nfl2k5_equipment_lz'] = lz
            else:
                try:
                    lz = historical(revision, 'mod_editor/core/nfl2k5_equipment_lz.py', f'b72_lz_{revision}')
                    sys.modules['mod_editor.core.nfl2k5_equipment_lz'] = lz
                except subprocess.CalledProcessError:
                    sys.modules.pop('mod_editor.core.nfl2k5_equipment_lz', None)
                writer = historical(revision, 'mod_editor/core/nfl2k5_uniform_equipment_writer.py', f'b72_writer_{revision}')
            if hasattr(writer, '_STAGED_CACHE'):
                writer._STAGED_CACHE.clear()
            if hasattr(writer, '_PARSE_CACHE'):
                writer._PARSE_CACHE.clear()
            def no_disk(index, key):
                raise OSError("disk stage cache disabled for this benchmark")
            writer._stage_disk_cache = no_disk
            row = {"version": label, "revision": revision, "design": args.design,
                   "targets": [f"{t.name} {t.width}x{t.height}" for t in group],
                   "helper_enabled": os.environ.get("NFL2K5_DISABLE_NATIVE_LZ") != "1"}
            started = time.perf_counter()
            try:
                try:
                    compiled = writer.build_unified_uniform_equipment_imports(
                        Path(args.index), pngs, preflight_only=True)
                    encoded = compiled.rebuild_info.recompressed_bytes
                except TypeError:
                    # Beta 68 has no preflight_only; it returns the built tuple.
                    started = time.perf_counter()
                    built = writer.build_unified_uniform_equipment_imports(Path(args.index), pngs)
                    encoded = built[2]["compression"]["recompressed_bytes"] if isinstance(built, tuple) else None
                row["outcome"] = "fit"
                row["encoded_bytes"] = encoded
            except Exception as error:  # noqa: BLE001
                row["outcome"] = type(error).__name__
                row["message"] = str(error)[:140]
            row["seconds"] = time.perf_counter() - started
            rows.append(row)
            print("B72 VERSION " + json.dumps(row), flush=True)
    from mod_editor.core import nfl2k5_equipment_lz as restored
    sys.modules["mod_editor.core.nfl2k5_equipment_lz"] = restored
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
