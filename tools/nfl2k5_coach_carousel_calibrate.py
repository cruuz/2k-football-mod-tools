#!/usr/bin/env python3
"""Build data/nfl2k5_coach_carousel_2026.json, the coaching carousel's change model and fallback hiring pool (job
c6-carousel, beta 80). Development use only; the generated JSON is checked in.

Source: nflverse ``games.csv`` (https://github.com/nflverse/nfldata, ``data/games.csv``; pinned by sha256 in the output),
every regular season 1999-2025. A *change* is a different head coach in the club's first regular-season game of the
next season than in its last game of this one (a coach fired during a season and an interim replaced after it count
once; an interim kept on counts as no change, like an offseason in the game).

Model (what the native code computes, ``nfl2k5_coach_carousel.hazard``):
* a club that made the playoffs: one flat rate (the share of playoff clubs that changed coach);
* any other club: a logistic curve in its regular-season winning share (ties half) with its own level for the
  coach's first, second and later seasons with the club, fitted by maximum likelihood, tabulated at 0, .05, .. 1.0;
* times the club's owner factor: (changes + 3) / (expected + 3) over the 27 seasons (expected = the model above on
  the club's own seasons; 3 = shrinkage toward the league), scaled so the league total is the observed total.

Fallback pool: the 32 sourced 2026 defensive coordinators of ``data/vip/defense_identity_2026.json`` (team-site
sources), minus any who is a 2026 head coach, with their head coaching careers 1999-2025 counted from the same
``games.csv`` (regular season W-L-T, seasons, winning seasons, playoff and Super Bowl games). Ratings are the game's
own created-coach default (every rating 50, the retail coach records 32 and 33). The 2026 head coaches come from
``data/nfl2k5_teams_2026/*.json`` (team-site sources), not from games.csv's 2026 schedule rows. The c5-owners pool replaces it when
``data/nfl2k5_coach_pool_2026.json`` is present (see ``nfl2k5_coach_carousel.load_pool``).

  python3 tools/nfl2k5_coach_carousel_calibrate.py /path/to/games.csv [--out data/nfl2k5_coach_carousel_2026.json]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/nfl2k5_coach_carousel_2026.json"
DCS = ROOT / "data/vip/defense_identity_2026.json"
GAMES_URL = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
ALIAS = {"OAK": "LV", "SD": "LAC", "STL": "LAR", "LA": "LAR"}
# the game's team order (alphabetical by nickname), nflverse abbreviations
CLUBS = ("SF", "CHI", "CIN", "BUF", "DEN", "CLE", "TB", "ARI", "LAC", "KC", "IND", "DAL", "MIA", "PHI", "ATL", "NYG",
         "JAX", "NYJ", "DET", "GB", "CAR", "NE", "LV", "LAR", "BAL", "WAS", "NO", "SEA", "PIT", "HOU", "TEN", "MIN")
DC_TEAM = {"ARZ": "ARI", "OAK": "LV", "SD": "LAC", "STL": "LAR"}
FIRST, LAST = 1999, 2025
SHRINK = 3.0
NAME_FIX = {"Klint Kubliak": "Klint Kubiak"}       # nflverse typo (see data/nfl2k5_teams_2026/LV.json)


def read_games(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def seasons_table(rows: list[dict]) -> list[dict]:
    games = defaultdict(list)
    for r in rows:
        season = int(r["season"])
        if season < FIRST:
            continue
        for team, coach, mine, theirs in ((r["home_team"], r["home_coach"], r["home_score"], r["away_score"]),
                                          (r["away_team"], r["away_coach"], r["away_score"], r["home_score"])):
            result = None
            if mine not in ("", None) and theirs not in ("", None):
                result = "W" if int(mine) > int(theirs) else "L" if int(mine) < int(theirs) else "T"
            games[(ALIAS.get(team, team), season)].append((r["gameday"], r["game_type"], NAME_FIX.get(coach, coach),
                                                           result))
    out = []
    for team in sorted({t for t, _ in games}):
        tenure, previous = 0, None
        for season in sorted(s for t, s in games if t == team):
            if season > LAST:
                continue
            played = sorted(games[(team, season)])
            regular = [g for g in played if g[1] == "REG"]
            coach = regular[-1][2]
            tenure = tenure + 1 if coach == previous else 1
            previous = coach
            following = [g for g in sorted(games.get((team, season + 1), [])) if g[1] == "REG"]
            if not following:
                continue
            w = sum(g[3] == "W" for g in regular)
            l = sum(g[3] == "L" for g in regular)
            t = sum(g[3] == "T" for g in regular)
            post = [g for g in played if g[1] != "REG"]
            out.append(dict(team=team, season=season, coach=coach, w=w, l=l, t=t, pct=(w + t / 2) / max(1, w + l + t),
                            tenure=tenure, playoffs=bool(post), changed=following[0][2] != coach))
    return out


def _features(row: dict) -> list[float]:
    return [1.0, row["pct"], 1.0 if row["tenure"] == 1 else 0.0, 1.0 if row["tenure"] == 2 else 0.0]


def fit_logistic(rows: list[dict], rounds: int = 40) -> list[float]:
    beta = [0.0] * 4
    for _ in range(rounds):
        gradient = [0.0] * 4
        hessian = [[0.0] * 4 for _ in range(4)]
        for row in rows:
            x = _features(row)
            p = 1 / (1 + math.exp(-sum(b * v for b, v in zip(beta, x))))
            y = 1.0 if row["changed"] else 0.0
            for i in range(4):
                gradient[i] += (y - p) * x[i]
                for j in range(4):
                    hessian[i][j] -= p * (1 - p) * x[i] * x[j]
        a = [hessian[i][:] + [-gradient[i]] for i in range(4)]
        for c in range(4):
            pivot = max(range(c, 4), key=lambda r: abs(a[r][c]))
            a[c], a[pivot] = a[pivot], a[c]
            for r in range(4):
                if r != c:
                    f = a[r][c] / a[c][c]
                    a[r] = [x - f * y for x, y in zip(a[r], a[c])]
        beta = [b + a[i][4] / a[i][i] for i, b in enumerate(beta)]
    return beta


def curve(beta: list[float], tenure: int) -> list[float]:
    offset = beta[2] if tenure == 1 else beta[3] if tenure == 2 else 0.0
    return [round(1 / (1 + math.exp(-(beta[0] + beta[1] * k / 20 + offset))), 4) for k in range(21)]


def model(rows: list[dict]) -> dict:
    regular = [r for r in rows if not r["playoffs"]]
    beta = fit_logistic(regular)
    playoff = [r for r in rows if r["playoffs"]]
    playoff_rate = sum(r["changed"] for r in playoff) / len(playoff)
    curves = {"tenure_1": curve(beta, 1), "tenure_2": curve(beta, 2), "tenure_3_plus": curve(beta, 3)}

    def p(row):
        if row["playoffs"]:
            return playoff_rate
        key = "tenure_1" if row["tenure"] == 1 else "tenure_2" if row["tenure"] == 2 else "tenure_3_plus"
        k, f = divmod(round(row["pct"] * 1000), 50)
        values = curves[key]
        return values[k] + (values[min(k + 1, 20)] - values[k]) * f / 50

    expected, observed, seasons = defaultdict(float), defaultdict(int), defaultdict(int)
    for row in rows:
        expected[row["team"]] += p(row)
        observed[row["team"]] += row["changed"]
        seasons[row["team"]] += 1
    factor = {t: (observed[t] + SHRINK) / (expected[t] + SHRINK) for t in expected}
    scale = sum(observed.values()) / sum(p(r) * factor[r["team"]] for r in rows)
    clubs = {}
    for team in CLUBS:
        clubs[team] = dict(seasons=seasons[team], changes=observed[team], expected=round(expected[team], 2),
                           owner_factor=round(factor[team] * scale, 3))
    per_season = defaultdict(int)
    for row in rows:
        per_season[row["season"]] += row["changed"]
    changed = sorted(r["pct"] for r in rows if r["changed"])
    return dict(
        definition="change = a different head coach in the club's first regular-season game of the next season",
        seasons=f"{FIRST}-{LAST} regular seasons", team_seasons=len(rows), changes=sum(r["changed"] for r in rows),
        changes_per_offseason={str(s): n for s, n in sorted(per_season.items())},
        median_changed_share=round(changed[len(changed) // 2], 3),
        logistic=dict(intercept=round(beta[0], 4), share=round(beta[1], 4), first_season=round(beta[2], 4),
                      second_season=round(beta[3], 4)),
        playoff_rate=round(playoff_rate, 4), playoff_clubs=len(playoff),
        playoff_changes=sum(r["changed"] for r in playoff), curves=curves, shrinkage=SHRINK, clubs=clubs)


def careers(rows: list[dict]) -> dict:
    """Head coaching careers 1999-2025 by coach name: regular season, playoffs and Super Bowls."""
    out = defaultdict(lambda: dict(seasons=set(), w=0, l=0, t=0, by_season=defaultdict(lambda: [0, 0]),
                                   pw=0, pl=0, sbw=0, sbl=0, sb=0))
    for r in rows:
        season = int(r["season"])
        if not FIRST <= season <= LAST or r["home_score"] in ("", None) or r["away_score"] in ("", None):
            continue
        for coach, mine, theirs in ((r["home_coach"], int(r["home_score"]), int(r["away_score"])),
                                    (r["away_coach"], int(r["away_score"]), int(r["home_score"]))):
            c = out[NAME_FIX.get(coach, coach)]
            win, loss = mine > theirs, mine < theirs
            if r["game_type"] == "REG":
                c["seasons"].add(season)
                c["w" if win else "l" if loss else "t"] += 1
                c["by_season"][season][0 if win else 1] += 1 if (win or loss) else 0
            elif r["game_type"] == "SB":
                c["sb"] += 1
                c["sbw" if win else "sbl"] += 1
            else:
                c["pw" if win else "pl"] += 1
    result = {}
    for name, c in out.items():
        result[name] = dict(seasons=len(c["seasons"]), wins=c["w"], losses=c["l"], ties=c["t"],
                            winning_seasons=sum(1 for w, l in c["by_season"].values() if w > l),
                            super_bowls=c["sb"], playoff_wins=c["pw"], playoff_losses=c["pl"],
                            super_bowl_wins=c["sbw"], super_bowl_losses=c["sbl"])
    return result


def fallback_pool(rows: list[dict], head_coaches_2026: set[str]) -> list[dict]:
    dcs = json.loads(DCS.read_text(encoding="utf-8"))
    record = careers(rows)
    empty = dict(seasons=0, wins=0, losses=0, ties=0, winning_seasons=0, super_bowls=0, playoff_wins=0,
                 playoff_losses=0, super_bowl_wins=0, super_bowl_losses=0)
    pool = []
    for code, team in sorted(dcs["teams"].items()):
        name = team["dc"]
        if name in head_coaches_2026:
            continue
        first, _, last = name.partition(" ")
        career = record.get(name, empty)
        pool.append(dict(first=first, last=last, kind="defensive coordinator", club_2026=DC_TEAM.get(code, code),
                         source=team["source"], career=career, weight=10 + min(career["seasons"], 10),
                         career_source="nflverse games.csv 1999-2025 head coach games" if career["seasons"] else None))
    return pool


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("games", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    raw = args.games.read_bytes()
    rows = read_games(args.games)
    table = seasons_table(rows)
    head_2026 = {json.loads(path.read_text(encoding="utf-8"))["roster"]["head_coach"]
                 for path in sorted((ROOT / "data/nfl2k5_teams_2026").glob("*.json"))}
    data = dict(
        schema="nfl2k5_coach_carousel/v1",
        generator="tools/nfl2k5_coach_carousel_calibrate.py",
        sources=[dict(file="games.csv", url=GAMES_URL, sha256=hashlib.sha256(raw).hexdigest(), rows=len(rows)),
                 dict(file="data/vip/defense_identity_2026.json", note="2026 defensive coordinators, team-site sources")],
        settings=dict(max_changes=12, rehire_percent=12),
        model=model(table),
        pool_note=("fallback pool: the 2026 defensive coordinators (real people, team-site sources) with their head "
                   "coaching careers from games.csv; ratings are the game's own created-coach default (50)"),
        pool=fallback_pool(rows, head_2026))
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {args.out}: {data['model']['team_seasons']} team-seasons, {data['model']['changes']} changes, "
          f"{len(data['pool'])} pool entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
