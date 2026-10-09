"""Aggregate named regular-season targets and join the shipped build's depth chart.

Python standard library only. Inputs are public nflverse CSVs and a read-only
pack-0 main ROST extraction. No ratings, player bytes or disc payload are emitted.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core.nfl2k5_roster_records import RosterDocument

ALIASES = {"ARI": "ARZ", "LAC": "SD", "LV": "OAK", "LA": "STL", "LAR": "STL"}
POSITIONS = {3: "WR", 7: "RB", 8: "FB", 9: "TE", 0: "QB"}


def norm(name):
    name = re.sub(r",?\s+(jr|sr|ii|iii|iv|v)\.?$", "", name, flags=re.IGNORECASE)
    return "".join(c for c in unicodedata.normalize("NFKD", name).casefold() if c.isalnum())


def aggregate(rows):
    counts = defaultdict(Counter)
    names, weeks, dates, games = {}, set(), set(), set()
    seen = set()
    for row in rows:
        if row["season"] != "2026" or row["season_type"] != "REG" or int(row["week"]) < 1:
            continue
        key = (row["game_id"], row["play_id"])
        if key in seen:
            raise ValueError(f"duplicate play {key}")
        seen.add(key)
        weeks.add(int(row["week"]))
        dates.add(row["game_date"])
        games.add(row["game_id"])
        if (row["play_type"] != "pass" or row["pass_attempt"] != "1"
                or row["two_point_attempt"] == "1" or not row["receiver_player_id"]):
            continue
        team = ALIASES.get(row["posteam"], row["posteam"])
        gid = row["receiver_player_id"]
        counts[team][gid] += 1
        names[gid] = row["receiver_player_name"]
    return counts, names, dict(weeks=sorted(weeks), first_game=min(dates), last_game=max(dates), games=len(games))


def build(pbp, roster_csv, main_roster, sources):
    with gzip.open(pbp, "rt", encoding="utf-8", newline="") as stream:
        counts, names, coverage = aggregate(csv.DictReader(stream))
    public = {}
    with roster_csv.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["gsis_id"]:
                public[row["gsis_id"]] = row
    raw = main_roster.read_bytes()
    doc = RosterDocument(raw[32:], scheme="one_pool", reference_year=2026)
    teams = {}
    for team in doc.teams[:32]:
        code = ALIASES.get(team.abbreviation, team.abbreviation)
        chart, matching = {}, {}
        for pos, players in doc.depth_chart(team.index).items():
            if pos not in POSITIONS:
                continue
            for rank, player in enumerate(players, 1):
                role = f"{POSITIONS[pos]}{rank}"
                chart[role] = dict(name=player.display, rank=player.record.get("depth_rank"),
                                   side=player.record.get("depth_side"))
                matching[norm(player.display)] = role
        targets = counts[code]
        total = sum(targets.values())
        if total <= 0:
            raise ValueError(f"no 2026 targets for {code}")
        players, roles = [], Counter()
        for gid, count in targets.most_common():
            if gid not in public:
                raise ValueError(f"targeted player absent from public roster: {gid}")
            row = public[gid]
            role = matching.get(norm(row["full_name"]))
            if role:
                roles[role] += count
            players.append(dict(gsis_id=gid, name=row["full_name"], pbp_name=names[gid],
                                position=row["position"], targets=count, share=count / total, role=role))
        teams[code] = dict(nflverse_team=team.abbreviation, targets=total, players=players,
                           depth_chart=chart, role_targets=dict(roles),
                           role_shares={r: n / total for r, n in sorted(roles.items())},
                           unmapped_targets=sum(p["targets"] for p in players if p["role"] is None))
    return dict(schema="b77.targets-2026.v1", season=2026, sources=sources, coverage=coverage,
                target_definition="Named receiver on a counted pass attempt (play_type pass), REG, week >= 1; excludes no-play penalties and two-point attempts. Share denominator is all named team targets, including players absent from the build.",
                build_depth_source=dict(disc="SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso", pack="0", entry=5,
                    resource_sha256=hashlib.sha256(raw).hexdigest(),
                    method="RosterDocument.depth_chart: position pool, depth_rank, depth_side, player index. WR1 is X, WR2 Z, WR3 slot. Exact rank/side fields retained for personnel-chain verification."),
                teams=dict(sorted(teams.items())))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("pbp", "roster-csv", "main-roster", "sources", "out"):
        ap.add_argument("--" + name, type=Path, required=True)
    args = ap.parse_args()
    result = build(args.pbp, args.roster_csv, args.main_roster, json.loads(args.sources.read_text()))
    with args.out.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=1, allow_nan=False)
        stream.write("\n")
    print(result["coverage"], "teams", len(result["teams"]))


if __name__ == "__main__":
    main()
