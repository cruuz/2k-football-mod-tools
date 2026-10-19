#!/usr/bin/env python3
"""Analytic CPU call mix of composed books (b776 pb1): personnel and shotgun/pistol share per situation, read with the
native-equivalent selector ``pb/v2/selection_model.py`` (retail 0.05 shotgun weight outside the 10; job a4's per-team
weights replace it in a built disc, so treat gun shares here as a lower bound).

    python3 pb/v2/callmix.py DIR_A [DIR_B ...] [--teams KC NE]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from pb.v2 import selection_model as sm  # noqa: E402


def mix(raw: bytes) -> dict:
    bk = sm.book_from(raw)
    out = {}
    for name, sit in sm.SITUATIONS[:10]:
        pcat, pform, _ = bk.distribution(sit)
        shares = sm.personnel_shares(bk, sit)
        gun = sum(p for fi, p in pform.items() if bk.forms[fi]["flags"] & 0xC0000 == 0x80000)
        pistol_cat = {ci for ci, c in bk.cats.items() if c["name"] == "Pistol"}
        pistol = sum(p for ci, p in pcat.items() if ci in pistol_cat)
        out[name] = dict(personnel={k: round(v) for k, v in sorted(shares.items(), key=lambda kv: -kv[1]) if v >= 1},
                         gun=round(100 * gun), pistol_group=round(100 * pistol),
                         formations=sum(1 for v in pform.values() if v > 0.01))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("--teams", nargs="*")
    args = ap.parse_args(argv)
    for t in args.teams or sorted(p.stem for p in args.dirs[0].glob("*.play")):
        for d in args.dirs:
            p = d / f"{t}.play"
            if not p.exists():
                continue
            print(f"== {t} {d.name}")
            for sit, row in mix(p.read_bytes()).items():
                print(f"   {sit:14} gun {row['gun']:3}% pistol-group {row['pistol_group']:3}% formations>1% {row['formations']:2} "
                      f"{row['personnel']}")


if __name__ == "__main__":
    main()
