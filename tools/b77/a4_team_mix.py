#!/usr/bin/env python3
"""b77 / a4 + a4pd: native check of the per-franchise shotgun weights. For each team the game's real offensive commit (0x20B670) runs on
the team's composed PLAY book with the franchise key stored the way the game stores it, before (another executable: v0.5, or the one
with a single weight per franchise) and after (the repaired executable), in the seven down and distance cells of
``a4_eras.TEAM_BINS`` (cells at the selector's representative distances); the result is compared with the real nflverse shotgun
rates in the era data file.

    python3 tools/b77/a4_team_mix.py --before default_v05.xbe --after default_a4.xbe --books DIR_OF_KEY.play --teams TEN KC --out mix.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from tools.b77 import a4_callmix as cm  # noqa: E402
from tools.b77.a4_eras import BIN_ORDER as TEAM_BINS  # noqa: E402

CELLS = {"d1": "1st&10 mid", "d2_short": "2nd&2 mid", "d2_mid": "2nd&6 mid", "d2_long": "2nd&11 mid",
         "d3_short": "3rd&2 mid", "d3_mid": "3rd&5 mid", "d3_long": "3rd&10 mid"}


def run_team(xbe: bytes, book: bytes, key: str, samples: int, category: int = 0) -> dict:
    result = cm.run(xbe, book, {cell: cm.SITUATIONS[cell] for cell in CELLS.values()}, samples, None, team=key, category=category)
    return {name: result[cell]["gun_pct"] for name, cell in CELLS.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--before", type=Path, required=True)
    ap.add_argument("--after", type=Path, required=True)
    ap.add_argument("--books", type=Path, required=True)
    ap.add_argument("--teams", nargs="+", required=True)
    ap.add_argument("--eras", type=Path, default=ROOT / "data/nfl2k5_moment_playbook_eras.json")
    ap.add_argument("--samples", type=int, default=100)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    eras = json.loads(args.eras.read_text())
    before_xbe, after_xbe = args.before.read_bytes(), args.after.read_bytes()
    out = {}
    for key in args.teams:
        book = (args.books / f"{key}.play").read_bytes()
        real = eras["teams"][key]["bins"]
        before, after = run_team(before_xbe, book, key, args.samples), run_team(after_xbe, book, key, args.samples)
        snaps = {n: real[n]["snaps"] for n in TEAM_BINS}
        total = sum(snaps.values())
        mean = lambda row: round(sum(snaps[n] * row[n] for n in TEAM_BINS) / total, 1)       # noqa: E731
        out[key] = dict(bin_weights=eras["teams"][key]["gun_weights"], real={n: real[n]["gun_pct"] for n in TEAM_BINS}, before=before, after=after,
                        overall=dict(real=mean({n: real[n]["gun_pct"] for n in TEAM_BINS}), before=mean(before), after=mean(after)))
        print(key, "bin weights", list(out[key]["bin_weights"].values()), "overall real/before/after", out[key]["overall"], flush=True)
        for n in TEAM_BINS:
            print(f"   {n:9s} real {real[n]['gun_pct']:5}  before {before[n]:5}  after {after[n]:5}")
    if args.out:
        args.out.write_text(json.dumps(out, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
