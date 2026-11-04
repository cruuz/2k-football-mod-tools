#!/usr/bin/env python3
"""b780 rst2 (Q41): rate real players the pack has no record for, with the r1 ratings v2.4 model the 2026 league was rated with.

The pack's 2026 players were rated by job r1 (tools/ratings_v2, MODEL_VERSION ``r1-ratings-v2.4``): 2024 and 2025
nflverse features, retail 2004 tier scales, percentiles inside a position and tier, rookies by draft slot, then the
b779 reviewed halfback and quarterback steps that live inside ``rate_all``. tools/b765/f1_rate.py already runs that
model for players who have no record (the dated free agents); this module is the same call for players who are on a
club's 53-man roster on a later date:

* the comparison population is the clubs' 53-man rosters (nflverse ``ACT`` and ``INA``), as r1's was (32 x 53 = 1,696
  records); a player is a starter when his club's chart lists him first at his own slot, else a backup;
* a candidate's own ratings never move anybody's: only the candidates' ratings are returned, an existing record is not
  rewritten;
* age is the player's actual age on ``as_of`` and the experience is the completed seasons since his entry year, as
  f1_rate does for a candidate; physical ratings use nflverse combine and cited forty times (data/nfl2k5_ratings_forty_sources.json).

  python3 tools/b780/rst2_rate.py --roster roster_2026.csv --charts depth_charts_2026.csv --plan PLAN.json
          --gsis 00-0030000,00-0031000 --as-of 2026-11-03 --out rated.json
          [--model-inputs /media/noah/Storage/.b76-research/r1/port_work] [--nflverse /media/noah/Storage/.b76-research/r1/data/nflverse]

Evidence: DESIGN / PROVED OFFLINE, a model from real statistics, not 2K's ratings; unwitnessed in play.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools/ratings_v2")]

MODEL_INPUTS = Path("/media/noah/Storage/.b76-research/r1/port_work")
NFLVERSE = Path("/media/noah/Storage/.b76-research/r1/data/nflverse")
FORTY_SOURCES = ROOT / "data/nfl2k5_ratings_forty_sources.json"
CLUB_STATUSES = ("ACT", "INA")
POSITIONS = {0: "QB", 1: "K", 2: "P", 3: "WR", 4: "CB", 5: "FS", 6: "SS", 7: "HB", 8: "FB", 9: "TE", 10: "OLB", 11: "LB",
             12: "C", 13: "G", 14: "T", 15: "DT", 16: "EDGE"}


def latest_roster(path):
    out = {}
    for row in csv.DictReader(open(path, encoding="utf-8")):
        g = row["gsis_id"]
        if g and (g not in out or int(row["week"] or 0) >= int(out[g]["week"] or 0)):
            out[g] = row
    return out


def chart_ranks(path):
    """{gsis: the best (lowest) chart rank he holds on his club's newest chart}, starters have rank 1."""
    newest, rows = {}, list(csv.DictReader(open(path, encoding="utf-8")))
    for row in rows:
        newest[row["team"]] = max(newest.get(row["team"], ""), row["dt"])
    best = {}
    for row in rows:
        if row["dt"] != newest[row["team"]] or row["pos_grp"] == "Special Teams" and row["pos_abb"] not in ("PK", "P", "LS"):
            continue
        best[row["gsis_id"]] = min(best.get(row["gsis_id"], 99), int(row["pos_rank"]))
    return best


def age_on(born, as_of):
    return as_of.year - born.year - ((as_of.month, as_of.day) < (born.month, born.day))


def entry_year(row, as_of):
    for key in ("entry_year", "rookie_year"):
        if str(row.get(key) or "").isdigit():
            return int(row[key])
    return as_of.year - int(float(row.get("years_exp") or 0))


def model_player(row, pos, index, team, tier, as_of):
    born = dt.date.fromisoformat(row["birth_date"])
    return dict(gsis=row["gsis_id"], name=row["full_name"], pos=pos, index=index, pool="primary", team=team,
                depth=0 if tier == "starter" else 7, tier=tier, weight=int(float(row["weight"] or 0)),
                height=int(float(row["height"] or 0)), age=age_on(born, as_of), years=max(0, as_of.year - entry_year(row, as_of)),
                current={})


def rate(roster_csv, charts_csv, plan_rows, candidates, as_of, model_inputs=MODEL_INPUTS, nflverse=NFLVERSE):
    """{gsis: {"ratings": {...28}, "basis": {...}}} for ``candidates`` ({gsis: position name}); ``plan_rows`` are the dated
    plan's rows (the population: every ACT or INA player who already has a record, with his record's position)."""
    import common
    from model import Data, MODEL_VERSION, rate_all
    from mod_editor.core import nfl2k5_roster_records as rr
    common.CFG.update(work=str(model_inputs), nflverse=str(nflverse))
    fresh = latest_roster(roster_csv)
    ranks = chart_ranks(charts_csv)
    players = []
    for n, row in enumerate(plan_rows):
        f = fresh.get(row["gsis_id"])
        if f is None or f["status"] not in CLUB_STATUSES or row["gsis_id"] in candidates:
            continue
        pos = POSITIONS[row["fields"]["position"]]
        tier = "starter" if ranks.get(row["gsis_id"], 99) == 1 else "backup"
        players.append(model_player(f, pos, int(row["index"]), f["team"], tier, as_of))
    population = len(players)
    for n, (gsis, pos) in enumerate(sorted(candidates.items())):
        f = fresh[gsis]
        tier = "starter" if ranks.get(gsis, 99) == 1 else "backup"
        players.append(model_player(f, pos, 100000 + n, f["team"], tier, as_of))
    zero = {k: 0 for k in rr.RATING_BYTE_ORDER}
    for p in players:
        p["current"] = dict(zero)
    data = Data([str(FORTY_SOURCES)])
    with gzip.open(Path(nflverse) / "players.csv.gz", "rt", encoding="utf-8") as stream:
        draft = {r["gsis_id"]: int(float(r["draft_pick"])) if r["draft_pick"] else None
                 for r in csv.DictReader(stream) if r["gsis_id"]}
    rate_all(data, players, draft)
    out = {}
    for p in players:
        if p["gsis"] in candidates and p["index"] >= 100000:
            out[p["gsis"]] = {"ratings": {k: int(v) for k, v in p["ratings"].items()}, "basis": p["basis"],
                              "tier": p["tier"], "age": p["age"], "years": p["years"], "pos": p["pos"]}
    inputs = [Path(model_inputs) / n for n in ("features_2024.json", "features_2025.json", "ratings_v2_reference.json",
                                             "stability.json")] + [Path(nflverse) / "players.csv.gz",
                                                                   Path(nflverse) / "combine.csv.gz", FORTY_SOURCES,
                                                                   ROOT / "tools/ratings_v2/model.py",
                                                                   ROOT / "mod_editor/core/nfl2k5_ratings_model.py"]
    receipt = {"model": MODEL_VERSION, "as_of": as_of.isoformat(), "comparison_population": population + len(candidates),
               "inputs_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs if p.exists()}}
    return out, receipt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--roster", required=True, type=Path)
    ap.add_argument("--charts", required=True, type=Path)
    ap.add_argument("--plan", required=True, type=Path, help="a roster-edits document with a roster_refresh plan")
    ap.add_argument("--gsis", required=True, help="comma-separated gsis ids to rate, optionally id:POS")
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model-inputs", type=Path, default=MODEL_INPUTS)
    ap.add_argument("--nflverse", type=Path, default=NFLVERSE)
    args = ap.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))["roster_refresh"]
    candidates = {}
    for item in args.gsis.split(","):
        gsis, _, pos = item.partition(":")
        candidates[gsis] = pos or "WR"
    out, receipt = rate(args.roster, args.charts, plan["players"], candidates, dt.date.fromisoformat(args.as_of),
                        args.model_inputs, args.nflverse)
    args.out.write_text(json.dumps({"receipt": receipt, "players": out}, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(receipt)[:300], len(out))


if __name__ == "__main__":
    main()
