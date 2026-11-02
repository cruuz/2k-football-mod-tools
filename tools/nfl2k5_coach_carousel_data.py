#!/usr/bin/env python3
"""Build data/nfl2k5_coach_carousel_2026.json, the coaching carousel's own settings and the hiring pool's Super Bowl and
winning-season counts (job c6-carousel, beta 80). Development use only; the generated JSON is checked in.

The decision model, the owner table and the hiring pool itself are c5-owners' (``data/nfl2k5_owners_2026.json``,
``data/nfl2k5_coach_pool_2026.json``, ``mod_editor/core/nfl2k5_coach_owners.py``). The pool's head coaching records
there carry seasons, wins, losses, ties and playoff games; the Coach's Card also shows winning seasons and the Super Bowl
record, so this adds those three numbers for every pool coach who was a head coach, counted from the same pinned
nflverse ``games.csv`` (https://github.com/nflverse/nfldata, ``data/games.csv``) the c5 table uses: a winning season is
a regular season in which the coach's own games are more wins than losses; Super Bowl games are game_type SB. (games.csv
credits the opening-day coach with every 2024 and 2025 game; every coach cut short in those seasons had a losing season
either way, and no Super Bowl is affected.)

  python3 tools/nfl2k5_coach_carousel_data.py /path/to/games.csv [--out data/nfl2k5_coach_carousel_2026.json]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/nfl2k5_coach_carousel_2026.json"
POOL = ROOT / "data/nfl2k5_coach_pool_2026.json"
GAMES_URL = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
FIRST, LAST = 1999, 2025
SETTINGS = {"max_changes": 12, "rehire_percent": 12}


def careers(path: Path) -> dict:
    """name -> {winning_seasons, super_bowls, super_bowl_wins, super_bowl_losses} over 1999-2025."""
    by_season = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    bowls = defaultdict(lambda: [0, 0])
    with path.open(newline="", encoding="utf-8") as stream:
        for r in csv.DictReader(stream):
            season = int(r["season"])
            if not FIRST <= season <= LAST or r["home_score"] in ("", None) or r["away_score"] in ("", None):
                continue
            home, away = int(r["home_score"]), int(r["away_score"])
            for coach, mine, theirs in ((r["home_coach"], home, away), (r["away_coach"], away, home)):
                if r["game_type"] == "REG":
                    if mine != theirs:
                        by_season[coach][season][0 if mine > theirs else 1] += 1
                elif r["game_type"] == "SB":
                    bowls[coach][0 if mine > theirs else 1] += 1
    out = {}
    for coach in set(by_season) | set(bowls):
        out[coach] = dict(winning_seasons=sum(1 for w, l in by_season[coach].values() if w > l),
                          super_bowls=sum(bowls[coach]), super_bowl_wins=bowls[coach][0],
                          super_bowl_losses=bowls[coach][1])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("games", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    raw = args.games.read_bytes()
    pool_raw = POOL.read_bytes()
    pool = json.loads(pool_raw)
    record = careers(args.games)
    extras = {}
    for c in pool["candidates"]:
        if not c.get("head_coach_record"):
            continue
        name = f"{c['first']} {c['last']}"
        extras[c["id"]] = dict(name=name, **record.get(name, dict(winning_seasons=0, super_bowls=0,
                                                                     super_bowl_wins=0, super_bowl_losses=0)))
    data = dict(
        schema="nfl2k5_coach_carousel/v2",
        generator="tools/nfl2k5_coach_carousel_data.py",
        sources=[dict(file="games.csv", url=GAMES_URL, sha256=hashlib.sha256(raw).hexdigest(), rows=raw.count(b"\n") - 1),
                 dict(file="data/nfl2k5_coach_pool_2026.json", sha256=hashlib.sha256(pool_raw).hexdigest(),
                      note="c5-owners hiring pool: names, kinds and head coaching records")],
        settings=dict(SETTINGS, note="max_changes: the game's fixed table holds 12 changes an offseason (the real "
                                     "league's most since 1999 is 11); rehire_percent: share of vacancies that "
                                     "take a coach another club parted ways with that offseason, when one is free"),
        pool_extras=extras)
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {args.out}: {len(extras)} pool coaches with a head coaching record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
