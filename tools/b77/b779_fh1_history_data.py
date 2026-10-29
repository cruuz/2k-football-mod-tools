#!/usr/bin/env python3
"""b779 fh1: sourced entry years and season history for the real players Studio creates from zero.

Reads pinned nflverse-data release files (CC-BY-4.0) that the caller downloaded into one directory; never the network.
Treat those files as untrusted data: they are only parsed.

  b779_fh1_history_data.py build --nflverse DIR --edits ROSTER_EDITS.json --out-history H.json --out-entry E.json
  b779_fh1_history_data.py league-games --nflverse DIR --edits ROSTER_EDITS.json --out FIXED.json

Entry year = ``entry_year`` of the player's LATEST annual roster row in ``rosters/roster_YYYY.csv`` (the league year he
joined an NFL roster, drafted or not).  It is present for every player the SOFTDRINK recipe writes; ``rookie_year`` (first
season played) is not used because a draftee who spent his first year on injured reserve is still one year older in the
league, which is how the game's own rollover counts.  Years pro = season - entry_year + 1 (rookie = 1).

Season rows follow the policy the franchise history was generated with (every stat and team value reproduced exactly for all
6,203 league player-seasons of the v0.7 plan): regular season, nflverse ``stats_player_reg_YYYY.csv`` 2000..2025; the stat
mapping below; team = the club(s) on the player's latest week of the annual roster, a tie broken by the stat row's
``recent_team`` only when it is one of the candidates (no other inference).

GAMES (b779 fh1, the Andrew Thomas bug): ``stats_player.games`` counts only the weeks with a box-score stat line, which cut
offensive linemen to 1-8 games a year. Games are now the larger of that count and the snap-count games (a snap on offense,
defense or special teams, ``snap_counts_YYYY.csv``, 2013 on); before 2013 no snap data exists and the stat-line count is kept as
a lower bound. A season with snaps but no stat line is added (games and TEAM only). ``league-games`` applies the same rule to
the roster-edits document's ``franchise_history`` (the 1,932 league players).
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_team_history as _teams  # noqa: E402

HISTORY_SCHEMA = "nfl2k5_created_history/v1"
ENTRY_SCHEMA = "nfl2k5_entry_years/v1"
BASE_YEAR = 2026
FIRST_STATS_YEAR = 2000
LAST_STATS_YEAR = 2025
FIRST_SNAP_YEAR = 2013          # nflverse snap_counts_2012.csv is header only; real rows start in 2013
RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"
ATTRIBUTION = "nflverse contributors (https://github.com/nflverse/nflverse-data), CC-BY-4.0"
ENTRY_RULE = ("entry_year of the latest annual roster row (rosters/roster_YYYY.csv, 2000..2026); years pro = "
              f"{BASE_YEAR} - entry_year + 1, rookie = 1, capped at 31")


def _num(row: dict, key: str) -> float:
    value = row.get(key, "")
    return float(value) if value not in ("", None, "NA") else 0.0


def _distances(text: str | None) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", text or "")]


def _bucket(distance: int) -> int:
    return 0 if distance < 30 else 1 if distance < 40 else 2 if distance < 50 else 3


def season_stats(row: dict) -> dict[str, float]:
    """nflverse player-season row -> the Player Card counters (names are ``nfl2k5_career_stats.FIELDS``)."""
    out = {
        "games": _num(row, "games"), "rushing_attempts": _num(row, "carries"), "rushing_yards": _num(row, "rushing_yards"),
        "rushing_touchdowns": _num(row, "rushing_tds"), "passing_attempts": _num(row, "attempts"),
        "passing_completions": _num(row, "completions"), "passing_yards": _num(row, "passing_yards"),
        "passing_touchdowns": _num(row, "passing_tds"), "passing_interceptions": _num(row, "passing_interceptions"),
        "receptions": _num(row, "receptions"), "receiving_yards": _num(row, "receiving_yards"),
        "receiving_touchdowns": _num(row, "receiving_tds"),
        "defensive_tackles": _num(row, "def_tackles_solo") + _num(row, "def_tackles_with_assist") + _num(row, "def_tackle_assists"),
        "defensive_sacks": _num(row, "def_sacks"), "defensive_interceptions": _num(row, "def_interceptions"),
        "forced_fumbles": _num(row, "def_fumbles_forced"), "interception_return_yards": _num(row, "def_interception_yards"),
        "extra_points_made": _num(row, "pat_made"), "extra_points_attempted": _num(row, "pat_att"),
        "punts": _num(row, "pt_att"), "punting_yards": _num(row, "pt_yards"), "punts_inside_20": _num(row, "pt_inside_20"),
        "punt_touchbacks": _num(row, "pt_touchback"),
    }
    made = [_num(row, "fg_made_0_19") + _num(row, "fg_made_20_29"), _num(row, "fg_made_30_39"),
            _num(row, "fg_made_40_49"), _num(row, "fg_made_50_59") + _num(row, "fg_made_60_")]
    missed = [_num(row, "fg_missed_0_19") + _num(row, "fg_missed_20_29"), _num(row, "fg_missed_30_39"),
              _num(row, "fg_missed_40_49"), _num(row, "fg_missed_50_59") + _num(row, "fg_missed_60_")]
    blocked = [0, 0, 0, 0]
    for distance in _distances(row.get("fg_blocked_list")):
        blocked[_bucket(distance)] += 1
    for i, name in enumerate(("1_29", "30_39", "40_49", "50_plus")):
        out[f"field_goals_made_{name}"] = made[i]
        out[f"field_goals_attempted_{name}"] = made[i] + missed[i] + blocked[i]
    return out


def team_index(code: str, season: int) -> int:
    code = "STL" if code == "LA" else code            # nflverse 2016-2019 writes the Rams as LA
    abbreviation, _note = _teams.resolve_team(code, season)
    return _teams.RETAIL_TEAM_INDEX[abbreviation]


class Nflverse:
    """The downloaded release files, indexed lazily by (gsis_id, season)."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self._stats: dict[tuple[str, int], dict] | None = None
        self._roster: dict[tuple[str, int], list[dict]] | None = None
        self._snaps: dict[tuple[str, int], set] | None = None
        self.used: dict[str, str] = {}

    def _path(self, kind: str, year: int) -> Path:
        name = {"rosters": f"roster_{year}.csv", "snaps": f"snap_counts_{year}.csv"}.get(kind, f"stats_player_reg_{year}.csv")
        return self.dir / name

    def _read(self, kind: str, year: int):
        path = self._path(kind, year)
        raw = path.read_bytes()
        self.used[path.name] = hashlib.sha256(raw).hexdigest()
        return csv.DictReader(raw.decode("utf-8").splitlines())

    def stats(self) -> dict[tuple[str, int], dict]:
        if self._stats is None:
            self._stats = {}
            for year in range(FIRST_STATS_YEAR, LAST_STATS_YEAR + 1):
                for row in self._read("stats", year):
                    if row.get("season_type", "REG") == "REG":
                        self._stats[(row["player_id"], year)] = row
        return self._stats

    def snaps(self) -> dict[tuple[str, int], set]:
        """(gsis_id, season) -> the regular-season GAMES the player took a snap in (offense, defense or special teams > 0).

        nflverse ``stats_player.games`` counts only the weeks in which the player has a box-score stat line, so a tackle or guard
        with no penalty, a long snapper, or a defender with no tackle in a week is missing from it (Andrew Thomas 2022-2025: 4,
        1, 3 and 3 games there against 16, 10, 6 and 13 with snaps). ``snap_counts_YYYY.csv`` (2013 on) lists every player with a
        snap; its ``pfr_player_id`` is mapped to the GSIS id through ``players.csv``. Games = distinct game ids."""
        if self._snaps is None:
            raw = (self.dir / "players.csv").read_bytes()
            self.used["players.csv"] = hashlib.sha256(raw).hexdigest()
            pfr = {r["pfr_id"]: r["gsis_id"] for r in csv.DictReader(raw.decode("utf-8").splitlines()) if r["pfr_id"]}
            self._snaps = collections.defaultdict(set)
            for year in range(FIRST_SNAP_YEAR, LAST_STATS_YEAR + 1):
                for row in self._read("snaps", year):
                    if row["game_type"] != "REG":
                        continue
                    if _num(row, "offense_snaps") + _num(row, "defense_snaps") + _num(row, "st_snaps") <= 0:
                        continue
                    gsis = pfr.get(row["pfr_player_id"])
                    if gsis:
                        self._snaps[(gsis, year)].add(row["game_id"])
        return self._snaps

    def games(self, gsis_id: str, year: int, stats_games: float) -> tuple[int, str]:
        """Games played: the larger of the stat-line count and the snap count (2013 on); 2012 and earlier keep the stat-line
        count, which is a LOWER bound (no snap data exists for those seasons)."""
        if year < FIRST_SNAP_YEAR:
            return int(stats_games), "stat_line_games_lower_bound"
        snapped = len(self.snaps().get((gsis_id, year), ()))
        return (max(int(stats_games), snapped), "snap_counts" if snapped >= stats_games else "stat_line_games")

    def roster(self) -> dict[tuple[str, int], list[dict]]:
        if self._roster is None:
            self._roster = collections.defaultdict(list)
            for year in range(FIRST_STATS_YEAR, BASE_YEAR + 1):
                for row in self._read("rosters", year):
                    self._roster[(row["gsis_id"], year)].append(row)
        return self._roster

    def entry_year(self, gsis_id: str) -> int | None:
        for year in range(BASE_YEAR, FIRST_STATS_YEAR - 1, -1):
            rows = self.roster().get((gsis_id, year))
            for row in rows or ():
                if str(row.get("entry_year", "")).strip():
                    return int(float(row["entry_year"]))
        return None

    def team(self, gsis_id: str, year: int, stat_row: dict) -> tuple[str | None, str]:
        rows = self.roster().get((gsis_id, year))
        if not rows:
            return None, "no_roster_row"

        def week(row):
            return int(float(row["week"])) if row.get("week") else 0
        latest = max(week(r) for r in rows)
        candidates = sorted({r["team"] for r in rows if week(r) == latest})
        if len(candidates) == 1:
            return candidates[0], "latest_week"
        if stat_row.get("recent_team") in candidates:
            return stat_row["recent_team"], "tie_stats_recent_team"
        return None, "tie_unresolved"

    def seasons(self, gsis_id: str, entry: int | None = None) -> tuple[list[dict], dict]:
        out, notes = [], collections.Counter()
        for year in range(FIRST_STATS_YEAR, LAST_STATS_YEAR + 1):
            row = self.stats().get((gsis_id, year))
            stat_games = _num(row, "games") if row is not None else 0.0
            games, basis = self.games(gsis_id, year, stat_games)
            if games <= 0:
                continue
            if entry is not None and year < entry:
                notes["before_entry_year"] += 1
                continue
            stats = {k: (int(v) if float(v).is_integer() else v) for k, v in season_stats(row or {}).items() if v}
            stats["games"] = games
            if row is None:
                notes["season_from_snaps_only"] += 1
            if games != int(stat_games):
                notes["games_raised_from_snaps"] += 1
            season = {"year": year, "stats": stats}
            code, how = self.team(gsis_id, year, row or {})
            notes["team_" + how] += 1
            if code is not None:
                season["team"] = code
                season["team_index"] = team_index(code, year)
            out.append(season)
        return out, dict(notes)


def source_url(name: str) -> str:
    tag = ("rosters" if name.startswith("roster_") else "snap_counts" if name.startswith("snap_counts_")
           else "players" if name == "players.csv" else "stats_player")
    return f"{RELEASE}/{tag}/{name}"


def years_pro_for(entry_year: int) -> int:
    return max(1, min(31, BASE_YEAR - entry_year + 1))


def created_identities(edits: dict, free_agents: dict, depth: dict) -> dict[str, dict]:
    """Every real identity Studio writes into a record it creates from zero, by GSIS id, MOST important first.

    The order is the order the history pass folds from the end when the pool is short: players created onto 2026 clubs,
    then the 140 dated free agents, then the depth pool by its own priority, then any other new free agent."""
    found: dict[str, dict] = {}
    refresh = [p for p in edits.get("roster_refresh", {}).get("players", ()) if p.get("new")]

    def add(p, birth, via, full=False):
        found.setdefault(p["gsis_id"], {"first": p["first"], "last": p["last"], "birth_date": birth, "via": via, "full": full})
    for p in refresh:
        if p.get("status") != "UFA":
            add(p, p["birth_date"], "roster_refresh_club")
    for p in free_agents.get("added", ()):
        fields = p["fields"]
        add(p, f"{fields['birth_year']:04d}-{fields['birth_month']:02d}-{fields['birth_day']:02d}", "free_agents_2026")
    for p in sorted(depth.get("players", ()), key=lambda q: q.get("priority", 10**6)):
        # the 26 hand-checked players (Kaepernick is priority 1) keep every season whatever the pool budget says
        add(p, p["birth_date"], "free_agent_depth", full=p.get("priority", 10**6) <= 26)
    for p in refresh:
        add(p, p["birth_date"], "roster_refresh_free_agent")
    return found


def build(nflverse_dir: Path, edits_path: Path):
    data = Nflverse(nflverse_dir)
    edits = json.loads(Path(edits_path).read_text(encoding="utf-8"))
    free_agents = json.loads((ROOT / "mod_editor" / "data" / "nfl2k5_free_agents_2026.v1.json").read_text(encoding="utf-8"))
    depth = json.loads((ROOT / "mod_editor" / "data" / "nfl2k5_free_agent_depth_2026.v1.json").read_text(encoding="utf-8"))
    created = created_identities(edits, free_agents, depth)
    everyone = {x["gsis_id"]: x for x in edits["franchise_history"]["players"]}
    for p in edits["roster_refresh"]["players"]:
        everyone.setdefault(p["gsis_id"], p)
    for gsis, row in created.items():
        everyone.setdefault(gsis, row)
    entries = {}
    for gsis in sorted(everyone):
        year = data.entry_year(gsis)
        if year is not None:
            entries[gsis] = year
    players, summary = [], collections.Counter()
    for gsis in created:
        entry = entries.get(gsis)
        if entry is None:
            summary["no_entry_year"] += 1
            continue
        seasons, notes = data.seasons(gsis, entry)
        for k, v in notes.items():
            summary[k] += v
        row = created[gsis]
        players.append({"gsis_id": gsis, "first": row["first"], "last": row["last"], "birth_date": row["birth_date"],
                        "entry_year": entry, "years_pro": years_pro_for(entry), **({"full": True} if row.get("full") else {}),
                        "seasons": seasons})
        summary["players"] += 1
        summary["seasons"] += len(seasons)
    fetched = (Path(nflverse_dir) / "FETCHED_AT.txt").read_text(encoding="utf-8").strip()
    sources = {name: {"sha256": sha, "url": source_url(name)} for name, sha in sorted(data.used.items())}
    meta = {"attribution": ATTRIBUTION, "fetched_utc": fetched, "base_year": BASE_YEAR, "sources": sources}
    history = {"schema": HISTORY_SCHEMA, **meta,
               "policy": ("Completed regular seasons 2000..2025; games = the larger of the stats_player games (weeks with a stat line) and the "
                          "snap_counts games (a snap on offense, defense or special teams, 2013 on, which fixes linemen, snappers and "
                          "quiet defenders; before 2013 the stat-line count is a lower bound); a season with snaps but no stat line "
                          "carries games and TEAM only; team = the club on the "
                          "latest week of the annual roster (a tie only by the stat row's recent_team when it is a candidate). Seasons "
                          "before 2000 and playoff games are not in the source and are not invented. Sparse counters: zero stays unset."),
               "years_pro_convention": "game_years_in_league",
               "players": players}
    entry = {"schema": ENTRY_SCHEMA, **meta, "rule": ENTRY_RULE, "years_pro_convention": "game_years_in_league",
             "entries": entries}
    return history, entry, dict(summary)


def patch_league(nflverse_dir: Path, edits: dict) -> tuple[dict, dict]:
    """The roster-edits document's ``franchise_history`` (the 1,932 league players) with games played from snap counts.

    The league history was generated from ``stats_player`` only, so its ``games`` (and which seasons exist at all) follow the weeks
    with a box-score line. This raises every season's games to the snap-count games (2013 on) and adds the seasons a player has
    snaps in but no stat line (games and TEAM words only). Values change for 55 percent of the league seasons; the new seasons add
    two words each. Sources: nflverse snap_counts and players.csv, pinned like the existing ones."""
    out = json.loads(json.dumps(edits))
    data = Nflverse(nflverse_dir)
    history = out["franchise_history"]
    report = collections.Counter()
    fetched = (Path(nflverse_dir) / "FETCHED_AT.txt").read_text(encoding="utf-8").strip()
    for player in history["players"]:
        gsis = player["gsis_id"]
        entry = data.entry_year(gsis) or 0
        have = {s["year"]: s for s in player["seasons"]}
        for season in player["seasons"]:
            old = int(season["stats"]["games"])
            new, basis = data.games(gsis, season["year"], old)
            report["seasons"] += 1
            if new > old:
                season["stats"]["games"] = new
                report["games_raised"] += 1
            if basis == "stat_line_games_lower_bound":
                report["seasons_before_2013_stat_line_lower_bound"] += 1
        for year in range(FIRST_SNAP_YEAR, LAST_STATS_YEAR + 1):
            snapped = len(data.snaps().get((gsis, year), ()))
            if year in have or snapped <= 0 or year < entry:
                continue
            season = {"source": f"snap_counts_{year}.csv", "stats": {"games": snapped}, "year": year}
            code, how = data.team(gsis, year, {})
            report["new_season_team_" + how] += 1
            if code is not None:
                rows = data.roster()[(gsis, year)]
                latest = max(int(float(r["week"])) if r.get("week") else 0 for r in rows)
                season.update(team_index=team_index(code, year), team_source=f"roster_{year}.csv",
                              team_selection={"candidates": [code], "selected": code, "tie_break": None, "week": latest})
            player["seasons"].append(season)
            report["seasons_added"] += 1
        player["seasons"].sort(key=lambda s: s["year"])
    pins = history["sources"]
    for name, sha in sorted(data.used.items()):
        if name.startswith(("snap_counts_", "players")) and name not in pins:
            raw = (Path(nflverse_dir) / name).read_bytes()
            pins[name] = {"bytes": len(raw), "file": f"data/{name}", "sha256": sha,
                          "tag": "snap_counts" if name.startswith("snap_counts_") else "players",
                          "updated_at": fetched, "url": source_url(name)}
    history["games_policy"] = ("games = max(stats_player games, snap_counts games with a snap on offense, defense or special teams) "
                               "from 2013; 2012 and earlier keep the stat-line count (a lower bound). Added by b779 fh1.")
    return out, dict(report)


def _dump(path: Path, document: dict) -> None:
    Path(path).write_text(json.dumps(document, indent=None, separators=(",", ":"), sort_keys=False) + "\n",
                          encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--nflverse", type=Path, required=True)
    b.add_argument("--edits", type=Path, required=True)
    b.add_argument("--out-history", type=Path, required=True)
    b.add_argument("--out-entry", type=Path, required=True)
    lg = sub.add_parser("league-games")
    lg.add_argument("--nflverse", type=Path, required=True)
    lg.add_argument("--edits", type=Path, required=True)
    lg.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "league-games":
        if args.out.exists():
            parser.error("output exists; choose a fresh path")
        document, summary = patch_league(args.nflverse, json.loads(args.edits.read_text(encoding="utf-8")))
        args.out.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(summary, sort_keys=True))
        return 0
    history, entry, summary = build(args.nflverse, args.edits)
    _dump(args.out_history, history)
    _dump(args.out_entry, entry)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
