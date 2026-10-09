#!/usr/bin/env python3
"""Beta 77 u3c: install the seven 2026 alternates of the Jaguars, Chargers, Raiders and Dolphins on the SOFTDRINK 2K28
v0.5 disc files (the u3s repair, with this job's key set and manifest layout).

Built alternates (recipes in ``data/nfl2k5_uniform_alternates_2026.json``, built by ``tools/b77/u3s_alternates.py``,
painted ones through ``tools/b77/u3c_paint.py``):

  JAX:5  Black alternate (style 5, "2026  Alternate 1")      JAX:6  Bold City (style 6, "2026  Alternate 2")
  LAC:9  Charger Power (style 9, "2026  Alternate 1")        LAC:10 Gold pants combos (style 10, "Alternate 2")
  LAC:11 Super Chargers (style 11, "2026  Alternate 3")      LV:4   White throwback (style 4, "Alternate 1")
  MIA:10 Rivalries (style 10, "2026  Alternate 1")

Owned bytes (each checked against the shipped bytes before anything is written, exactly as ``u3s_repair.py``): the
kit packages ``<code>H<S>.IFF`` / ``<code>A<S>.IFF`` of those styles (fixed spans, compile manifests), their Team Select
cards (outer 3102 and 3105), and the style's 4-byte year pair in the main roster team record (found by asset code).
Everything else on the disc is proved identical, a second pass over the output is a no-op, and unexpected input is
refused. KC 7 (a new style index) and LAR 10 to 12 (shipped in beta 76) are not part of this job.

  u3c_repair.py --input "SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso" --output OUT/vc_53450030 \\
      --compiled SCRATCH/compiled --receipt OUT/receipt.json [--keys JAX:5,JAX:6,...]

``--compiled`` is the folder with one ``<team><style>/native_manifest.json`` per alternate (jax5, jax6, lac9, lac10,
lac11, lv4, mia10), as ``u3s_alternates.py compile --out`` writes them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
import u3s_repair as base  # noqa: E402

KEYS = ("JAX:5", "JAX:6", "LAC:9", "LAC:10", "LAC:11", "LV:4", "MIA:10")
RECEIPT_SCHEMA = "b77/u3c/repair-receipt/v1"


def manifest_path(compiled: Path, key: str) -> Path:
    team, style = key.split(":")
    return compiled / f"{team.lower()}{style}" / "native_manifest.json"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--compiled", required=True, type=Path)
    p.add_argument("--recipes", type=Path, default=ROOT / "data/nfl2k5_uniform_alternates_2026.json")
    p.add_argument("--keys", default=",".join(KEYS))
    p.add_argument("--receipt", required=True, type=Path)
    a = p.parse_args(argv)
    keys = [k for k in a.keys.split(",") if k]
    for key in keys:
        base.require(key in KEYS, f"{key} is not one of this job's alternates {KEYS}")
    b = base._b765()
    receipt_path = b.refuse_links(a.receipt).resolve()
    source_path = b.refuse_links(a.input).resolve()
    base.require(receipt_path != source_path and not (source_path.is_dir() and receipt_path.is_relative_to(source_path)),
                 "receipt must not overwrite any input file")
    recipes = json.loads(a.recipes.read_text())
    for key in keys:
        base.require(key in recipes["alternates"], f"no recipe {key}")
    paths = [manifest_path(a.compiled, key) for key in keys]
    for path in paths:
        base.require(path.is_file(), f"missing compile manifest {path}")
    manifests = base.load_manifests(paths, recipes, keys)
    receipt = base.repair(a.input, a.output, manifests, recipes, keys)
    receipt["schema"] = RECEIPT_SCHEMA
    receipt["manifest_sha256"] = {str(path): base.sha(path.read_bytes()) for path in paths}
    receipt["recipes_sha256"] = base.sha(a.recipes.read_bytes())
    b.atomic_write(a.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps({"receipt": str(a.receipt), "scope_verified": True, "labels": receipt["labels"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
