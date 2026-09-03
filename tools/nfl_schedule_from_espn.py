#!/usr/bin/env python3
"""Build data/nfl_<season>_schedule.json (32 teams x 17 games) from ESPN's public
scoreboard API, mapped onto ESPN NFL 2K5's 32 franchise slots.

Source: https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
        ?dates=<season>&seasontype=2&week=<n>   (one call per week, 1..18)
Cross-checked against the league's own release
(https://media.nfl.com/.../05%2014%2026%20-%20Schedule%20Release.pdf, May 14 2026):
18 weeks, 272 games, 17 games per team, ONE bye per team (weeks 5-14), kickoff
Wednesday September 9 2026 (NE at SEA), Week 18 = Jan 9-10 2027, Wild Card from
Jan 16, Divisional Jan 23-24, Championship Jan 31, Super Bowl LXI Feb 14 2027.

Team slot = the retail 2K5 team ordinal (alphabetical by nickname, 0 = 49ers ..
31 = Vikings; the same ordinal the ROST schedule template and the franchise
save use).  Franchise continuity maps the 2026 names onto the 2004 slots:
LA Rams -> St. Louis Rams (23), LA Chargers -> San Diego Chargers (8), Las Vegas
Raiders -> Oakland Raiders (22), Washington Commanders -> Washington Redskins
(25).  Names, cities and uniforms are a separate text/art task.

Kickoff times are converted from ESPN's UTC stamps to US Eastern and stored the
way the 2K5 record stores them: 12-hour hour (0 encodes 12) + minute, plus an
explicit "am" flag for the 9:30 AM international kickoffs (the game's display
format is "%d:%02dpm", so those show as 9:30pm in-game; noted, not hidden).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ESPN_URL = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/"
            "scoreboard?dates={season}&seasontype=2&week={week}&limit=100")
# seasontype=1 is the preseason: ESPN week 1 = the Hall of Fame Game (two teams), weeks 2-4 = the
# three league-wide preseason weeks (16 games each) -- 49 games, 3 per team, 4 for the HOF pair.
ESPN_PRE_URL = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/"
                "scoreboard?dates={season}&seasontype=1&week={week}&limit=100")
PRESEASON_ESPN_WEEKS = 4
NFL_RELEASE_PDF = ("https://media.nfl.com/content/dam/communications/"
                   "football-communications/2026/news/"
                   "05%2014%2026%20-%20Schedule%20Release.pdf")
EASTERN = ZoneInfo("America/New_York")

# 2K5 retail team ordinal (tools/nfl2k5_franchise_schedule_probe.py TEAM_NAMES),
# keyed by ESPN abbreviation.  Franchise-continuity mapping for relocated /
# renamed clubs is deliberate (see module docstring).
ESPN_TO_2K5 = {
    "SF": 0, "CHI": 1, "CIN": 2, "BUF": 3, "DEN": 4, "CLE": 5, "TB": 6,
    "ARI": 7, "LAC": 8, "KC": 9, "IND": 10, "DAL": 11, "MIA": 12, "PHI": 13,
    "ATL": 14, "NYG": 15, "JAX": 16, "NYJ": 17, "DET": 18, "GB": 19,
    "CAR": 20, "NE": 21, "LV": 22, "LAR": 23, "BAL": 24, "WSH": 25, "NO": 26,
    "SEA": 27, "PIT": 28, "HOU": 29, "TEN": 30, "MIN": 31,
}
TEAM_2K5 = (
    "49ers", "Bears", "Bengals", "Bills", "Broncos", "Browns", "Buccaneers",
    "Cardinals", "Chargers", "Chiefs", "Colts", "Cowboys", "Dolphins",
    "Eagles", "Falcons", "Giants", "Jaguars", "Jets", "Lions", "Packers",
    "Panthers", "Patriots", "Raiders", "Rams", "Ravens", "Redskins", "Saints",
    "Seahawks", "Steelers", "Texans", "Titans", "Vikings",
)
SLOT_NOTES = {
    8: "2026 Los Angeles Chargers -> 2K5 San Diego Chargers slot",
    22: "2026 Las Vegas Raiders -> 2K5 Oakland Raiders slot",
    23: "2026 Los Angeles Rams -> 2K5 St. Louis Rams slot",
    25: "2026 Washington Commanders -> 2K5 Washington Redskins slot",
}


def fetch_week(season: int, week: int, cache: Path | None, seasontype: int = 2) -> dict:
    name = f"w{week}.json" if seasontype == 2 else f"pre{week}.json"
    if cache is not None:
        cached = cache / name
        if cached.is_file():
            return json.loads(cached.read_text())
    url = (ESPN_URL if seasontype == 2 else ESPN_PRE_URL).format(season=season, week=week)
    with urllib.request.urlopen(url, timeout=60) as resp:
        raw = resp.read()
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / name).write_bytes(raw)
    return json.loads(raw)


def _game_row(event: dict, week: int) -> dict:
    comp = event["competitions"][0]
    sides = {c["homeAway"]: c for c in comp["competitors"]}
    home = ESPN_TO_2K5[sides["home"]["team"]["abbreviation"]]
    away = ESPN_TO_2K5[sides["away"]["team"]["abbreviation"]]
    when = dt.datetime.strptime(event["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    venue = comp.get("venue", {})
    row = {
        "week": week,
        "home": home, "away": away,
        "home_name": TEAM_2K5[home], "away_name": TEAM_2K5[away],
        "espn_home": sides["home"]["team"]["abbreviation"],
        "espn_away": sides["away"]["team"]["abbreviation"],
        "espn_id": event["id"],
        "time_valid": bool(comp.get("timeValid", True)),
        "neutral_site": bool(comp.get("neutralSite", False)),
        "venue": venue.get("fullName"),
        "venue_city": (venue.get("address") or {}).get("city"),
    }
    row.update(kickoff_fields(when))
    if not row["time_valid"]:
        # ESPN stamps unannounced kickoffs (Week 16-18 flex pool, Week 18
        # Saturday/Sunday split) as local midnight; use the 1:00 PM ET
        # Sunday window as the placeholder and say so.
        row.update({"hour_field": 1, "minute_field": 0, "am": False,
                    "time_et": "13:00", "time_tbd": True})
    else:
        row["time_tbd"] = False
    return row


def build_preseason(season: int, cache: Path | None) -> dict:
    """The real preseason: week 0 = Hall of Fame Game, weeks 1-3 = the league-wide slate."""
    games = []
    for espn_week in range(1, PRESEASON_ESPN_WEEKS + 1):
        data = fetch_week(season, espn_week, cache, seasontype=1)
        assert data["season"]["year"] == season and data["season"]["type"] == 1
        assert data["week"]["number"] == espn_week
        for event in data["events"]:
            row = _game_row(event, espn_week - 1)
            row["espn_week"] = espn_week
            row["hall_of_fame"] = espn_week == 1
            games.append(row)
    games.sort(key=lambda g: (g["week"], g["date"], g["hour_field"] + (0 if g["am"] else 12), g["minute_field"], g["home"]))
    per_team = [0] * 32
    weeks_played: dict[int, list[int]] = {t: [] for t in range(32)}
    for g in games:
        for t in (g["home"], g["away"]):
            per_team[t] += 1
            weeks_played[t].append(g["week"])
    hof = [g for g in games if g["hall_of_fame"]]
    assert len(hof) == 1 and len(games) == 49, len(games)
    hof_teams = {hof[0]["home"], hof[0]["away"]}
    assert all(per_team[t] == (4 if t in hof_teams else 3) for t in range(32)), per_team
    assert all(sorted(w for w in weeks_played[t] if w) == [1, 2, 3] for t in range(32)), weeks_played
    return {
        "format": {
            "weeks": 4, "games": 49, "games_per_team": 3,
            "hall_of_fame_game": {"week": 0, "date": hof[0]["date"], "home": hof[0]["home_name"],
                                  "away": hof[0]["away_name"], "venue": hof[0]["venue"]},
            "note": ("Three preseason games per team since 2021 (17-game season); the two Hall of Fame "
                     "Game teams play a fourth.  Week 0 = HOF game, weeks 1-3 = 16 games each."),
        },
        "source": ESPN_PRE_URL,
        "games": games,
    }


def kickoff_fields(when_utc: dt.datetime) -> dict:
    local = when_utc.astimezone(EASTERN)
    hour24 = local.hour
    hour12 = hour24 % 12          # 0 encodes 12 in the 2K5 record
    return {
        "date": local.date().isoformat(),
        "weekday": local.strftime("%a"),
        "time_et": local.strftime("%H:%M"),
        "hour_field": hour12,
        "minute_field": local.minute,
        "am": hour24 < 12,
    }


def build(season: int, weeks: int, cache: Path | None, preseason: bool = True) -> dict:
    games = []
    byes: dict[int, list[int]] = {}
    fetched = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for week in range(1, weeks + 1):
        data = fetch_week(season, week, cache)
        assert data["season"]["year"] == season and data["season"]["type"] == 2
        assert data["week"]["number"] == week
        for team in data["week"].get("teamsOnBye", []):
            byes.setdefault(week, []).append(ESPN_TO_2K5[team["abbreviation"]])
        for event in data["events"]:
            games.append(_game_row(event, week))
    games.sort(key=lambda g: (g["week"], g["date"], g["hour_field"] + (0 if g["am"] else 12), g["minute_field"], g["home"]))
    # invariants
    per_team = [0] * 32
    home_ct = [0] * 32
    weeks_played: dict[int, set[int]] = {t: set() for t in range(32)}
    for g in games:
        per_team[g["home"]] += 1
        per_team[g["away"]] += 1
        home_ct[g["home"]] += 1
        weeks_played[g["home"]].add(g["week"])
        weeks_played[g["away"]].add(g["week"])
    assert len(games) == 272, len(games)
    assert set(per_team) == {17}, per_team
    assert sorted(home_ct) == [8] * 16 + [9] * 16, home_ct
    team_bye = {t: sorted(set(range(1, weeks + 1)) - weeks_played[t]) for t in range(32)}
    assert all(len(v) == 1 for v in team_bye.values()), team_bye
    bye_from_api = {t: [w for w, ts in byes.items() if t in ts] for t in range(32)}
    assert bye_from_api == team_bye, (bye_from_api, team_bye)
    return {
        "schema": "nfl_schedule_for_2k5/v1",
        "season": season,
        "format": {
            "weeks": weeks, "games_per_team": 17, "total_games": 272,
            "byes_per_team": 1, "bye_weeks_span": [min(byes), max(byes)],
            "kickoff": games[0]["date"], "final_regular_season_date": games[-1]["date"],
            "postseason": {
                "wild_card": "2027-01-16/17/18", "divisional": "2027-01-23/24",
                "conference": "2027-01-31", "super_bowl": "2027-02-14 (LXI, SoFi Stadium, Los Angeles)",
            },
            "note": ("The league's 2026 format is 17 games over 18 weeks with ONE bye per team. "
                     "A second bye exists only in the (unadopted) 18-game proposals."),
        },
        "sources": {
            "espn_scoreboard_api": ESPN_URL,
            "nfl_schedule_release_pdf": NFL_RELEASE_PDF,
            "fetched_utc": fetched,
        },
        "team_slots": [{"slot": i, "nickname_2k5": TEAM_2K5[i],
                        "espn": next(k for k, v in ESPN_TO_2K5.items() if v == i),
                        "note": SLOT_NOTES.get(i)} for i in range(32)],
        "byes": {str(t): team_bye[t][0] for t in range(32)},
        "record_layout_2k5": "[type=0x00][home][away][month][day][year%100][hour12 (0=12)][minute]; all times ET",
        "games": games,
        "preseason": build_preseason(season, cache) if preseason else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--weeks", type=int, default=18)
    ap.add_argument("--cache", type=Path, help="directory of cached ESPN week JSON files")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-preseason", action="store_true", help="skip the seasontype=1 (preseason) fetch")
    args = ap.parse_args()
    doc = build(args.season, args.weeks, args.cache, preseason=not args.no_preseason)
    out = args.out or ROOT / "data" / f"nfl_{args.season}_schedule.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    blob = (json.dumps(doc, indent=1, sort_keys=False) + "\n").encode()
    out.write_bytes(blob)
    pre = doc.get("preseason") or {"games": []}
    print(f"wrote {out} games={len(doc['games'])} preseason={len(pre['games'])} sha256={hashlib.sha256(blob).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
