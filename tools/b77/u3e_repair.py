#!/usr/bin/env python3
"""Beta 77 u3e: install the 2026 alternates of PIT, SEA, SF, TB, TEN and WAS on the SOFTDRINK 2K28 v0.5 disc files.

This is ``u3s_repair.py`` (same manifests, same span rules, same receipt) limited to the eight alternates this job
owns, so a run can never write another team's slot:

  PIT:5 (1933 gold throwback)      22H5 / 22A5   was "1959 - 1960 Uniform"
  SEA:3 (Rivalries, wolf grey)     26H3 / 26A3   was "2003  Alternate 1"
  SEA:4 (navy + wolf grey / white) 26H4 / 26A4   was "2003  Alternate 2"
  SF:7  (black Rivalries)          25H7 / 25A7   was "2004  Alternate 1"
  TB:2  (white '76 jersey)         27H2 / 27A2   was "1992 - 1996 Uniform"
  TB:6  (all-pewter Color Rush)    27H6 / 27A6   was "2004  Alternate 1"
  TEN:7 (Music City Rivalries)     28H7 / 28A7   was "2004  Alternate 1"
  WAS:9 (Hail Raiser, all black)   29H9 / 29A9   was "2004  Alternate 1"

Disc files touched (only the spans of the manifests are written; every other byte is proved identical):
  vc_53450030/0 (main roster ROST: eight 4-byte year pairs), /3 and /4 (Team Select cards, outer 3102 and 3105),
  /A (home kit packages) and /B (road kit packages) as the manifests say.

  u3e_repair.py --input "SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso" --output OUT/vc_53450030 \\
      --manifest PIT5/native_manifest.json [--manifest ...] --receipt OUT/receipt.json [--keys PIT:5,...]

A second pass over the output changes nothing (spans already read as their ``after`` bytes).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
import u3s_repair as base  # noqa: E402

OWNED_KEYS = ("PIT:5", "SEA:3", "SEA:4", "SF:7", "TB:2", "TB:6", "TEN:7", "WAS:9")
RECEIPT_SCHEMA = "b77/u3e/repair-receipt/v1"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path, action="append")
    p.add_argument("--recipes", type=Path, default=ROOT / "data/nfl2k5_uniform_alternates_2026.json")
    p.add_argument("--keys", default=",".join(OWNED_KEYS))
    p.add_argument("--receipt", required=True, type=Path)
    a = p.parse_args(argv)
    keys = [k for k in a.keys.split(",") if k]
    base.require(all(k in OWNED_KEYS for k in keys), f"u3e owns only {', '.join(OWNED_KEYS)}")
    b = base._b765()
    receipt_path = b.refuse_links(a.receipt).resolve()
    source_path = b.refuse_links(a.input).resolve()
    base.require(receipt_path != source_path and not (source_path.is_dir() and receipt_path.is_relative_to(source_path)),
                 "receipt must not overwrite any input file")
    recipes = json.loads(a.recipes.read_text())
    for key in keys:
        base.require(key in recipes["alternates"], f"no recipe {key}")
    manifests = base.load_manifests(a.manifest, recipes, keys)
    built = {doc["key"] for doc, _ in manifests}
    keys = [k for k in keys if k in built]       # only the alternates whose manifests were given
    receipt = base.repair(a.input, a.output, manifests, recipes, keys)
    receipt["schema"] = RECEIPT_SCHEMA
    receipt["manifest_sha256"] = {str(path): base.sha(path.read_bytes()) for path in a.manifest}
    receipt["recipes_sha256"] = base.sha(a.recipes.read_bytes())
    b.atomic_write(a.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps({"receipt": str(a.receipt), "scope_verified": True, "keys": keys, "labels": receipt["labels"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
