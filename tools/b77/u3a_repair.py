#!/usr/bin/env python3
"""Beta 77 u3a: install the 2026 alternates of ARI, ATL, BAL, BUF, CAR, CHI and CIN in their uniform style slots on the
SOFTDRINK 2K28 v0.5 disc files (or on the output of u3s_repair.py / any stack of the other jobs' repairs).

This is the u3s repair (tools/b77/u3s_repair.py) with this job's alternates: the same two kinds of bytes, both checked
against the shipped bytes before anything is written, and nothing else touched.

* The alternate's spans in its two kit packages (``<code>H<S>.IFF`` / ``<code>A<S>.IFF``) and its Team Select cards
  (``outer:3102`` 256 px cards, ``outer:3105`` 128 px helm cards), from ``tools/b77/u3s_alternates.py compile``
  manifests: each span must read as its ``before`` (or, on a second pass, its ``after``) SHA-256.
* The style's year pair in the main roster (ROST outer 0x4A37581D, team record +0x15A + 4 (S - 1)): 4 bytes that make
  Team Select read "2026  Alternate n". The team record is found by its asset code when the repair runs, so other
  jobs' roster edits elsewhere in the file do not move it; the pair must read the retail pair (or the new one) first.
  Cincinnati style 6 is an orphan kit (retail art and no label): its pair reads 0, 0 and becomes (2026, 2), which makes
  the game offer it.

Only the index and the packs that hold a change are written to ``--output``; every byte outside the declared spans is
proved identical, a second pass over the output is a no-op, and unexpected input is refused.

  u3a_repair.py --input "SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso" --output OUT/vc_53450030 \\
      --manifest COMPILED_ARI6/native_manifest.json [--manifest ...] --keys ARI:6,ARI:7,... --receipt OUT/receipt.json

``--keys`` defaults to the alternates named by the given manifests. Disc files touched (see the report for the byte
ranges): vc_53450030/0 (the year pairs, 4 bytes each), /3 and /4 (Team Select cards), /A and /B (kit packages).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

U3A_KEYS = ("ARI:6", "ARI:7", "ATL:9", "BAL:2", "BAL:3", "BUF:3", "BUF:8", "BUF:9", "CAR:2", "CHI:4", "CHI:6", "CIN:6")
RECEIPT_SCHEMA = "b77/u3a/repair-receipt/v1"


def _u3s():
    name = "b77_u3s_repair"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "tools/b77/u3s_repair.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def manifest_keys(paths: list[Path]) -> list[str]:
    """The alternate each manifest belongs to, in the order given (every key must be one of this job's)."""
    keys = []
    for path in paths:
        key = json.loads(path.read_text()).get("key")
        if key not in U3A_KEYS:
            raise ValueError(f"{path}: alternate {key} is not one of this job's ({', '.join(U3A_KEYS)})")
        if key in keys:
            raise ValueError(f"alternate {key} given twice")
        keys.append(key)
    return keys


def main(argv=None) -> int:
    base = _u3s()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path, action="append")
    p.add_argument("--recipes", type=Path, default=ROOT / "data/nfl2k5_uniform_alternates_2026.json")
    p.add_argument("--keys", default="")
    p.add_argument("--receipt", required=True, type=Path)
    a = p.parse_args(argv)
    b = base._b765()
    receipt_path = b.refuse_links(a.receipt).resolve()
    source_path = b.refuse_links(a.input).resolve()
    base.require(receipt_path != source_path and not (source_path.is_dir() and receipt_path.is_relative_to(source_path)),
                 "receipt must not overwrite any input file")
    recipes = json.loads(a.recipes.read_text())
    given = manifest_keys(a.manifest)
    keys = [k for k in a.keys.split(",") if k] or given
    for key in keys:
        base.require(key in U3A_KEYS and key in recipes["alternates"], f"no recipe {key} for this job")
    base.require(sorted(keys) == sorted(given), "--keys must be exactly the alternates of the given manifests")
    manifests = base.load_manifests(a.manifest, recipes, keys)
    receipt = base.repair(a.input, a.output, manifests, recipes, keys)
    receipt["schema"] = RECEIPT_SCHEMA
    receipt["manifest_sha256"] = {str(path): base.sha(path.read_bytes()) for path in a.manifest}
    receipt["recipes_sha256"] = base.sha(a.recipes.read_bytes())
    b.atomic_write(a.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps({"receipt": str(a.receipt), "scope_verified": True, "labels": receipt["labels"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
