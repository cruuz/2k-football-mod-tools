#!/usr/bin/env python3
"""Beta 77 u3b: install the built CLE DAL DEN DET GB HOU IND 2026 alternates on the SOFTDRINK 2K28 v0.5 disc files.

The repair logic is ``tools/b77/u3s_repair.py`` (same manifests, same receipt, same guarantees): only the declared
spans of each alternate's two kit packages and its Team Select cards, plus the 4-byte year pair of its style in the
main roster, are written; every span must read as its shipped ``before`` (or, on a second pass, its ``after``)
SHA-256, every byte outside the spans is proved identical, a second pass over the output is a no-op, and unexpected
input is refused. This wrapper only points it at the u3b recipes (``data/nfl2k5_uniform_alternates_2026_u3b.json``).

  u3b_repair.py --input "SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso" --output OUT/vc_53450030 \\
      --manifest COMPILED/native_manifest.json [--manifest ...] --keys CLE:3,CLE:4 --receipt OUT/receipt.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
import u3s_repair as ur  # noqa: E402

RECIPES = ROOT / "data/nfl2k5_uniform_alternates_2026_u3b.json"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path, action="append")
    p.add_argument("--recipes", type=Path, default=RECIPES)
    p.add_argument("--keys", required=True)
    p.add_argument("--receipt", required=True, type=Path)
    a = p.parse_args(argv)
    return ur.main(["--input", str(a.input), "--output", str(a.output), "--recipes", str(a.recipes),
                    "--keys", a.keys, "--receipt", str(a.receipt)]
                   + [x for m in a.manifest for x in ("--manifest", str(m))])


if __name__ == "__main__":
    raise SystemExit(main())
