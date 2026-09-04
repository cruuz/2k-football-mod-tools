#!/usr/bin/env python3
"""Generate ``data/nfl2k5_retail_team_history.csv``: the real team of every past season the retail
NFL 2K5 roster carries stats for, from nflverse-data (CC-BY-4.0).

Sources (https://github.com/nflverse/nflverse-data/releases, all CC-BY-4.0):
  rosters/roster_{1982..2003}.parquet          season, team, names, birth_date, gsis_id
  weekly_rosters/roster_weekly_{2002,2003}.parquet   week-by-week teams (the last regular-season week wins)
  player_stats/player_stats_{1999..2003}.csv   every player who recorded a stat, recent_team per week
  players/players.parquet                      identities: names, birth_date, gsis_id
Pro-Football-Reference is not used.

For each retail player with a history stream (1,325) the tool matches an nflverse identity by
normalised last + first name + birth date, then last name + birth date, then reports "none".  For
each of the player's retail seasons with a games entry it takes the team from, in order, the weekly
roster's last regular-season week, the last stat week's ``recent_team``, or the season roster, and
resolves era codes to the 2004 roster abbreviations (``nfl2k5_team_history.resolve_team``: HOU <= 1996
= Oilers = TEN, RAI = OAK, RAM/SL = STL, STL <= 1987 = Cardinals = ARZ, PHX/ARI = ARZ, BAL <= 1983 = IND,
BLT = BAL, CLV = CLE, HST = HOU).  Rows are written with the retail record's own name and birth date
so the studio's matcher hits them exactly.  A match log is written beside the CSV.

Needs pyarrow (parquet).  Read-only on the retail extraction; downloads go to ``--cache``.

usage: nfl2k5_team_history_from_nflverse.py [--retail PATH] [--cache DIR] [--out CSV] [--offline]
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "tools"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from mod_editor.core import nfl2k5_team_history as th  # noqa: E402

RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"
ROSTER_YEARS = range(1982, 2004)
WEEKLY_YEARS = (2002, 2003)
STATS_YEARS = range(1999, 2004)
DEFAULT_RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)"))
DEFAULT_CACHE = Path(os.environ.get("NFL2K5_NFLVERSE_CACHE", Path.home() / ".cache" / "nfl2k5-team-history"))
DEFAULT_OUT = ROOT / "data" / "nfl2k5_retail_team_history.csv"


def files() -> list[tuple[str, str]]:
    out = [(f"rosters/roster_{y}.parquet", f"roster_{y}.parquet") for y in ROSTER_YEARS]
    out += [(f"weekly_rosters/roster_weekly_{y}.parquet", f"roster_weekly_{y}.parquet") for y in WEEKLY_YEARS]
    out += [(f"player_stats/player_stats_{y}.csv", f"player_stats_{y}.csv") for y in STATS_YEARS]
    out.append(("players/players.parquet", "players.parquet"))
    return out


def fetch(cache: Path, offline: bool) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for remote, local in files():
        path = cache / local
        if path.is_file() and path.stat().st_size > 0:
            continue
        if offline:
            raise SystemExit(f"missing {local} in {cache} and --offline was given")
        print(f"downloading {remote}")
        with urllib.request.urlopen(f"{RELEASE}/{remote}", timeout=60) as response:   # nosec B310 - fixed https host
            data = response.read()
        path.write_bytes(data)


def parquet_rows(path: Path, columns: list[str]) -> list[dict]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pyarrow is needed to read the nflverse parquet files (pip install pyarrow)") from exc
    have = set(pq.read_schema(path).names)
    return pq.read_table(path, columns=[c for c in columns if c in have]).to_pylist()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retail", type=Path, default=DEFAULT_RETAIL, help="retail extraction folder or disc image (read-only)")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="where the nflverse files are kept")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--offline", action="store_true", help="never download; fail on a missing file")
    args = parser.parse_args(argv)

    fetch(args.cache, args.offline)
    cache = args.cache

    # --- nflverse: identities and season -> team per gsis_id
    identity: dict[str, tuple[str, str, dt.date | None]] = {}
    season_team: dict[str, dict[int, tuple[str, int]]] = collections.defaultdict(dict)   # gsis -> season -> (code, priority)
    for r in parquet_rows(cache / "players.parquet", ["gsis_id", "first_name", "last_name", "birth_date"]):
        if r.get("gsis_id"):
            birth = th.parse_birth_date(str(r["birth_date"])[:10]) if r.get("birth_date") else None
            identity[r["gsis_id"]] = (r.get("first_name") or "", r.get("last_name") or "", birth)
    for y in ROSTER_YEARS:
        for r in parquet_rows(cache / f"roster_{y}.parquet", ["season", "team", "first_name", "last_name", "birth_date", "gsis_id"]):
            g = r.get("gsis_id")
            if not g:
                continue
            birth = r.get("birth_date")
            birth = birth if isinstance(birth, dt.date) else (th.parse_birth_date(str(birth)[:10]) if birth else None)
            identity.setdefault(g, (r.get("first_name") or "", r.get("last_name") or "", birth))
            if r.get("team") and 1 > season_team[g].get(int(r["season"]), ("", -1))[1]:
                season_team[g][int(r["season"])] = (r["team"], 1)
    for y in STATS_YEARS:
        last_week: dict[str, tuple[int, str]] = {}
        with open(cache / f"player_stats_{y}.csv", newline="", encoding="utf-8") as handle:
            for r in csv.DictReader(handle):
                if r.get("season_type", "REG") != "REG" or not r.get("player_id") or not r.get("recent_team"):
                    continue
                week = int(r.get("week") or 0)
                if week >= last_week.get(r["player_id"], (-1, ""))[0]:
                    last_week[r["player_id"]] = (week, r["recent_team"])
        for g, (_week, team) in last_week.items():
            if 2 > season_team[g].get(y, ("", -1))[1]:
                season_team[g][y] = (team, 2)
    for y in WEEKLY_YEARS:
        last_week = {}
        for r in parquet_rows(cache / f"roster_weekly_{y}.parquet", ["season", "team", "week", "game_type", "gsis_id"]):
            g = r.get("gsis_id")
            if not g or not r.get("team") or (r.get("game_type") not in (None, "REG")):
                continue
            week = int(r.get("week") or 0)
            if week >= last_week.get(g, (-1, ""))[0]:
                last_week[g] = (week, r["team"])
        for g, (_week, team) in last_week.items():
            season_team[g][y] = (team, 3)

    by_exact: dict[tuple[str, str, dt.date | None], list[str]] = collections.defaultdict(list)
    by_last_dob: dict[tuple[str, dt.date | None], list[str]] = collections.defaultdict(list)
    for g, (first, last, birth) in identity.items():
        by_exact[(th.normalise_name(last), th.normalise_name(first), birth)].append(g)
        by_last_dob[(th.normalise_name(last), birth)].append(g)

    # --- the retail roster
    with th._outer_image()(args.retail) as archive:
        entry = th._entry(archive)
        body = archive.read(entry.virtual_offset, entry.size)[th.RESOURCE_HEADER_SIZE:]
    roster = th.parse_body(body)
    identities = collections.Counter((th.normalise_name(p.last), th.normalise_name(p.first), p.birth, p.position) for p in roster.players)
    rows: list[tuple[str, str, str, int, str, str, str, str]] = []
    log_lines: list[str] = []
    counts = collections.Counter()
    per_year_total: collections.Counter = collections.Counter()
    per_year_hit: collections.Counter = collections.Counter()
    for p in roster.players:
        slots = p.games_slots()
        if not slots:
            continue
        counts["players"] += 1
        key = (th.normalise_name(p.last), th.normalise_name(p.first), p.birth)
        cands = by_exact.get(key, [])
        how = "exact"
        if len(cands) != 1:
            cands = by_last_dob.get((key[0], p.birth), []) if p.birth else []
            how = "fallback_dob" if len(cands) == 1 else ("ambiguous" if len(cands) > 1 else "none")
        seasons = sorted(th.BASE_YEAR - (p.count - s) for s in slots)
        per_year_total.update(seasons)
        if len(cands) != 1:
            counts[how] += 1
            log_lines.append(f"{p.index:4d} {p.first} {p.last} {p.birth}: {how}; seasons {seasons}")
            continue
        counts[how] += 1
        g = cands[0]
        covered, uncovered, unknown = [], [], []
        for season in seasons:
            code, _prio = season_team.get(g, {}).get(season, ("", 0))
            if not code:
                uncovered.append(season)
                continue
            try:
                abbr, _note = th.resolve_team(code, season)
            except th.TeamHistoryError as exc:
                unknown.append(f"{season}:{code} ({exc})")
                continue
            duplicate = identities[(th.normalise_name(p.last), th.normalise_name(p.first), p.birth, p.position)] > 1
            rows.append((p.last, p.first, p.birth.isoformat() if p.birth else "", season, abbr,
                         th.POSITION_CODES[p.position] if p.position < len(th.POSITION_CODES) else "",
                         str(p.index) if duplicate else "", f"nflverse {code}"))
            covered.append(season)
            per_year_hit[season] += 1
        counts["seasons"] += len(seasons)
        counts["covered"] += len(covered)
        log_lines.append(f"{p.index:4d} {p.first} {p.last} {p.birth}: {how} {g}; covered {covered}; missing {uncovered}"
                         + (f"; unmapped {unknown}" if unknown else ""))
    rows.sort(key=lambda r: (r[0].lower(), r[1].lower(), r[3]))

    total_seasons = sum(per_year_total.values())
    header = [
        f"# NFL 2K5 retail roster team history: the real club of every past season the retail roster carries stats for.",
        f"# Source: {th.ATTRIBUTION} - rosters 1982-2003, weekly rosters 2002-2003, player stats 1999-2003, players.",
        f"# Generated {dt.date.today().isoformat()} by tools/nfl2k5_team_history_from_nflverse.py; matched {counts['exact'] + counts['fallback_dob']}"
        f" of {counts['players']} retail players, {counts['covered']} of {total_seasons} season rows.",
        "# Team codes are the 2004 roster abbreviations (relocated franchises resolved by season: Oilers -> TEN, LA Raiders -> OAK, ...).",
        "# Columns: last_name, first_name, birth_date (YYYY-MM-DD), season, team, position, roster_index (only where two retail records share the identity), source.",
        "# Lines starting with # are comments.",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="\n", encoding="utf-8") as handle:
        handle.write("\n".join(header) + "\n")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["last_name", "first_name", "birth_date", "season", "team", "position", "roster_index", "source"])
        writer.writerows(rows)
    log_path = args.out.with_suffix(".match.log")
    per_year = ", ".join(f"{y}: {per_year_hit[y]}/{per_year_total[y]}" for y in sorted(per_year_total))
    with open(log_path, "w", newline="\n", encoding="utf-8") as handle:
        handle.write(f"# match log for {args.out.name} ({th.ATTRIBUTION})\n")
        handle.write(f"# players with game seasons: {counts['players']}; exact: {counts['exact']}; last name + DOB: {counts['fallback_dob']}; "
                     f"ambiguous: {counts['ambiguous']}; none: {counts['none']}\n")
        handle.write(f"# season rows: {counts['covered']} of {total_seasons} have a team; per year: {per_year}\n")
        handle.write("# the studio fills every season this CSV does not cover with the player's own 2004 club\n"
                     "#   (counted as \"inferred\" in the build receipt); a row here always wins over that fill.\n")
        handle.write("\n".join(log_lines) + "\n")
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    print(f"players {counts['players']}: exact {counts['exact']}, last-name+DOB {counts['fallback_dob']}, ambiguous {counts['ambiguous']}, none {counts['none']}")
    print(f"season rows with a team: {counts['covered']} / {total_seasons} ({100 * counts['covered'] / max(1, total_seasons):.1f} %)")
    print(f"per year: {per_year}")
    print(f"wrote {args.out} ({len(rows)} rows, sha256 {digest}) and {log_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
