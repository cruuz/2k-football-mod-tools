#!/usr/bin/env python3
"""2025 offensive tendencies by down and distance for all 32 teams (beta 77 p6s; PROVED OFFLINE from public data).

Inputs (nflverse, the same three files as tendencies_2025.json, sha256 pinned there):
  play_by_play_2025.csv.gz, pbp_participation_2025.csv, ftn_charting_2025.csv
Filter: regular season, run or pass plays, no kneels, spikes or two-point tries.
Per team and situation bin: snaps, personnel shares (RB+FB count then TE count, e.g. '11'; '+' marks six or more
linemen), shotgun share (pbp ``shotgun``, the rule a4 fits on), pass share; per team the passing style
(NGS air yards mean, FTN play action / screen / RPO rates, the targeted receiver's charted route mix).
Bins: d1, d2_short (1-3), d2_mid (4-7), d2_long (8+), d3_short (3rd/4th 1-3), d3_mid (4-6), d3_long (7+),
red10 (inside the 10, any down). Usage: situational_2025.py NFLVERSE_DIR OUT.json
"""
import csv, gzip, json, statistics, sys
from collections import Counter, defaultdict

def bin_of(down, togo, yl):
    if yl <= 10:
        return "red10"
    if down == 1:
        return "d1"
    if down == 2:
        return "d2_short" if togo <= 3 else "d2_mid" if togo <= 7 else "d2_long"
    return "d3_short" if togo <= 3 else "d3_mid" if togo <= 6 else "d3_long"

def personnel(text):
    c = Counter()
    for part in text.split(","):
        part = part.strip()
        if part:
            n, pos = part.split(" ", 1)
            c[pos] += int(n)
    return f"{c['RB'] + c['FB']}{c['TE']}" + ("+" if c["T"] + c["G"] + c["C"] + c["OL"] > 5 else "")

def main(src, out):
    plays = {}
    with gzip.open(f"{src}/play_by_play_2025.csv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["season_type"] != "REG" or r["play_type"] not in ("run", "pass"):
                continue
            if r["qb_kneel"] == "1" or r["qb_spike"] == "1" or r["two_point_attempt"] == "1":
                continue
            try:
                d, t, yl = int(r["down"]), int(r["ydstogo"]), int(r["yardline_100"])
            except ValueError:
                continue
            plays[(r["game_id"], r["play_id"])] = dict(team=r["posteam"], bin=bin_of(d, t, yl), gun=r["shotgun"] == "1",
                                                     pass_=r["pass"] == "1", air=r["air_yards"])
    pers, route = {}, {}
    with open(f"{src}/pbp_participation_2025.csv", newline="") as f:
        for r in csv.DictReader(f):
            k = (r["nflverse_game_id"], r["play_id"])
            if k in plays:
                if r["offense_personnel"]:
                    pers[k] = personnel(r["offense_personnel"])
                if r["route"]:
                    route[k] = r["route"]
    ftn = {}
    with open(f"{src}/ftn_charting_2025.csv", newline="") as f:
        for r in csv.DictReader(f):
            k = (r["nflverse_game_id"], r["nflverse_play_id"])
            if k in plays:
                ftn[k] = (r["is_play_action"] == "TRUE", r["is_screen_pass"] == "TRUE", r["is_rpo"] == "TRUE")
    teams = defaultdict(lambda: defaultdict(lambda: dict(snaps=0, gun=0, pass_=0, pers=Counter())))
    style = defaultdict(lambda: dict(air=[], routes=Counter(), dropbacks=0, pa=0, screen=0, rpo=0))
    for k, p in plays.items():
        b = teams[p["team"]][p["bin"]]
        b["snaps"] += 1; b["gun"] += p["gun"]; b["pass_"] += p["pass_"]
        if k in pers:
            b["pers"][pers[k]] += 1
        if p["pass_"]:
            s = style[p["team"]]
            try:
                s["air"].append(float(p["air"]))
            except ValueError:
                pass
            if k in route:
                s["routes"][route[k]] += 1
            if k in ftn:
                s["dropbacks"] += 1; s["pa"] += ftn[k][0]; s["screen"] += ftn[k][1]; s["rpo"] += ftn[k][2]
    result = {}
    for team, bins in sorted(teams.items()):
        row = {}
        for name, b in bins.items():
            n = sum(b["pers"].values()) or 1
            row[name] = dict(snaps=b["snaps"], gun_pct=round(100 * b["gun"] / b["snaps"], 1),
                             pass_pct=round(100 * b["pass_"] / b["snaps"], 1),
                             personnel={g: round(100 * c / n, 1) for g, c in b["pers"].most_common() if 100 * c / n >= 0.5})
        s = style[team]
        tot = sum(s["routes"].values()) or 1
        result[team] = dict(bins=row, style=dict(
            adot=round(statistics.mean(s["air"]), 2) if s["air"] else None,
            play_action_pct=round(100 * s["pa"] / max(1, s["dropbacks"]), 1),
            screen_pct=round(100 * s["screen"] / max(1, s["dropbacks"]), 1),
            rpo_pct=round(100 * s["rpo"] / max(1, s["dropbacks"]), 1),
            target_routes_pct={r: round(100 * c / tot, 1) for r, c in s["routes"].most_common()}))
    doc = dict(status="PROVED OFFLINE (public nflverse data; aggregation only)", season=2025,
               sources="pb/research/tendencies_2025.json lists the three nflverse files and their sha256",
               generator="pb/research/situational_2025.py", teams=result)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
