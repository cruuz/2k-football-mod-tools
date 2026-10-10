#!/usr/bin/env python3
"""Beta 77 u3d: install the u3d alternates (MIN NE NO NYG NYJ PHI) on the SOFTDRINK 2K28 v0.5 disc files.

The same span logic as ``tools/b77/u3s_repair.py`` (its functions are imported, not copied), with the u3d recipes file
as the default. Per alternate the declared bytes are:

* its two kit packages' compiled spans (``<code>H<S>.IFF`` / ``<code>A<S>.IFF``) and its Team Select cards
  (``outer:3102`` / ``outer:3105``), each of which must read as the recorded ``before`` (or, on a second pass, the
  ``after``) SHA-256;
* the style's 4-byte year pair in the main roster (found by the team's asset code), from the recipe's ``retail_pair``
  to its ``label`` ("2026  Alternate n"); an orphan kit (NYJ 7) starts from the zero pair.

Only the index and the packs that hold a change are written; every byte outside the spans is proved identical, a
second pass is a no-op, unexpected input is refused.

  u3d_repair.py --input "SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso" --output OUT/vc_53450030 \\
      --manifest COMPILED/PHI13/native_manifest.json [--manifest ...] --keys PHI:13 --receipt OUT/receipt.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
import u3s_repair as ur  # noqa: E402

RECIPES = ROOT / "data/nfl2k5_uniform_alternates_2026_u3d.json"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path, action="append")
    p.add_argument("--recipes", type=Path, default=RECIPES)
    p.add_argument("--keys", required=True)
    p.add_argument("--receipt", required=True, type=Path)
    a = p.parse_args(argv)
    b = ur._b765()
    receipt_path = b.refuse_links(a.receipt).resolve()
    source_path = b.refuse_links(a.input).resolve()
    ur.require(receipt_path != source_path and not (source_path.is_dir() and receipt_path.is_relative_to(source_path)),
               "receipt must not overwrite any input file")
    recipes = json.loads(a.recipes.read_text())
    keys = [k for k in a.keys.split(",") if k]
    for key in keys:
        ur.require(key in recipes["alternates"], f"no recipe {key}")
    manifests = ur.load_manifests(a.manifest, recipes, keys)
    receipt = ur.repair(a.input, a.output, manifests, recipes, keys)
    receipt["manifest_sha256"] = {str(path): ur.sha(path.read_bytes()) for path in a.manifest}
    receipt["recipes_sha256"] = ur.sha(a.recipes.read_bytes())
    b.atomic_write(a.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps({"receipt": str(a.receipt), "scope_verified": True, "labels": receipt["labels"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
