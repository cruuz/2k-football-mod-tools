#!/usr/bin/env python3
"""Offline, deterministic generator for the classic teams' rosters and depth charts (job ct1, 2026-10-17).

EXPERIMENTAL / UNWITNESSED data. Noah asked for classic teams of the better (and a few memorable worse) teams of
2005-2025 that are not 25th Anniversary moment teams. This tool reuses the Anniversary team generator
(tools/nfl2k5_espn25_more_moments_build.py, job m2) unchanged, so a classic team is built exactly like a moment team:

- the 53-man pool is the nflverse weekly roster (ACT and INA) of the week the spec names;
- that week's nflverse depth chart orders the starters, left/right chains as the m1 contract defines them;
- the jersey numbers come from that game's play-by-play, else the season roster;
- the 28 ratings come from the m2 ratings model (m2-ratings-3) on the season's statistics, anchored to 2K's own 2004
  ratings where the player is in the retail roster.

Inputs, never committed: nflverse-data release files (CC-BY-4.0) in --inputs, the user's retail game (--retail).
Hand-written input: tools/nfl2k5_classic_teams_spec.json (teams, weeks, reasons).
Outputs: data/nfl2k5_classic_teams/ (teams.json, manifest.json, one CSV per team). --check regenerates into temporary
storage and compares every byte.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import nfl2k5_espn25_more_moments_build as m2  # noqa: E402

SPEC = ROOT / "tools/nfl2k5_classic_teams_spec.json"
OUT = ROOT / "data/nfl2k5_classic_teams"
GENERATOR = "tools/nfl2k5_classic_teams_build.py"
EVIDENCE = ("EXPERIMENTAL / UNWITNESSED: sourced nflverse rosters, depth charts and statistics through the m2 ratings "
            "model; no lab run, not played by Noah")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# 2025's nflverse depth chart is a series of dated snapshots (dt, pos_abb, pos_rank) instead of weekly rows.
SNAPSHOT_SKIP = {"H", "PR", "KR", "LS"}
SEASON_SHARE = 0.5      # a season starter is listed first at his slot in at least half of the regular-season weeks


def season_lineup(inputs, season: int, club: str) -> dict[str, tuple[str, str, int, int]]:
    """gsis id -> (depth position, formation, weeks listed first, regular-season weeks) for the season's starters:
    the players nflverse lists first (depth_team 1) at an offense or defense slot in at least half the weeks."""
    rows = [r for r in inputs.rows(f"depth_charts_{season}.csv")
            if r.get("club_code") in m2.club_codes(club) and r.get("game_type") == "REG" and r.get("depth_team") == "1"
            and r.get("formation") in ("Offense", "Defense") and (r.get("depth_position") or "").upper() in m2.DEPTH_SIDES]
    weeks = sorted({int(r["week"]) for r in rows})
    listed: dict[str, set] = {}
    slots: dict[str, collections.Counter] = {}
    for r in rows:
        listed.setdefault(r["gsis_id"], set()).add(int(r["week"]))
        slots.setdefault(r["gsis_id"], collections.Counter())[(r["depth_position"].upper(), r["formation"])] += 1
    out = {}
    for pid, seen in listed.items():
        if len(seen) >= SEASON_SHARE * len(weeks):
            (slot, formation), _ = sorted(slots[pid].items(), key=lambda kv: (-kv[1], kv[0]))[0]
            out[pid] = (slot, formation, len(seen), len(weeks))
    return snap_starters(inputs, season, club, out)


SNAP_GROUPS = ("WR", "TE", "HB", "CB")   # skill groups where team depth charts lag behind who actually played


def snap_starters(inputs, season: int, club: str, lineup: dict) -> dict:
    """From 2012 (nflverse snap counts): inside WR, TE, HB and CB the season starters are the players with the most
    regular-season snaps at that group, as many as the depth charts named; a replaced starter's slot passes on.
    (2019 Titans: the charts list A.J. Brown second all year, the snap counts have him second of all receivers.)"""
    name = f"snap_counts_{season}.csv"
    if not inputs.exists(name):
        return lineup
    roster = [r for r in inputs.rows(f"roster_{season}.csv") if r["team"] in m2.club_codes(club)]
    gsis = {r["pfr_id"]: r["gsis_id"] for r in roster if r.get("pfr_id") and r.get("gsis_id")}
    group_of = {r["gsis_id"]: m2.rm.map_position(r["position"], r.get("depth_chart_position", ""), r.get("weight"))
                for r in roster if r.get("gsis_id")}
    snaps = collections.Counter()
    for r in inputs.rows(name):
        if r["team"] in m2.club_codes(club) and r["game_type"] == "REG" and r["pfr_player_id"] in gsis:
            snaps[gsis[r["pfr_player_id"]]] += int(float(r["offense_snaps"] or 0)) + int(float(r["defense_snaps"] or 0))
    out = dict(lineup)
    for group in SNAP_GROUPS:
        while True:
            # a starter with no snap row (no pfr id in the roster file) is never judged by snaps
            current = [pid for pid, v in out.items() if m2.DEPTH_SIDES[v[0]][0] == group and snaps[pid]]
            others = [pid for pid, g in group_of.items() if g == group and pid not in out and snaps[pid]]
            if not current or not others:
                break
            low = min(current, key=lambda pid: (snaps[pid], pid))
            high = max(others, key=lambda pid: (snaps[pid], pid))
            if snaps[high] <= snaps[low]:
                break
            slot, formation, _n, weeks = out.pop(low)
            out[high] = (slot, formation, -snaps[high], weeks)     # negative: chosen by snaps, not chart weeks
    return out


def snapshot_chart(inputs, season: int, club: str, day: str) -> dict[str, dict]:
    """The dated depth-chart snapshot of the game day (the last one on or before it), in depth_chart_for's shape."""
    rows = [r for r in inputs.rows(f"depth_charts_{season}.csv") if r.get("team") in m2.club_codes(club)]
    stamp = max(r["dt"][:10] for r in rows if r["dt"][:10] <= day)
    out, order = {}, 0
    for r in rows:
        slot = (r.get("pos_abb") or "").upper()
        if r["dt"][:10] != stamp or slot in SNAPSHOT_SKIP or slot not in m2.DEPTH_SIDES:
            continue
        group = r.get("pos_grp", "")
        formation = "Special Teams" if group == "Special Teams" else "Defense" if group.endswith(" D") else "Offense"
        order += 1
        entry = {"depth_position": slot, "rank": int(r["pos_rank"]), "order": order, "formation": formation,
                 "roster_position": "", "snapshot": stamp}
        old = out.get(r["gsis_id"])
        if old is None or (entry["rank"], order) < (old["rank"], old["order"]):
            out[r["gsis_id"]] = entry
    return out


def _three_four(chart: dict) -> None:
    starters_dl = [e for e in chart.values() if e["rank"] == 1 and e["formation"] == "Defense"
                   and (e["depth_position"] in m2.DL_SLOTS or e["depth_position"] == "NT")]
    flag = any(e["depth_position"] == "NT" for e in starters_dl) and len(starters_dl) == 3
    for e in chart.values():
        e["three_four"] = flag


def install_lineups(spec: dict, inputs, games: dict) -> dict:
    """Wrap the m2 depth reader: season starters (or the 2025 snapshot) replace the week's first string. Returns the
    per-team lineup evidence for the manifest."""
    original = m2.depth_chart_for
    plans, evidence = {}, {}
    for key, team in spec["teams"].items():
        mode = team.get("lineup", "season")
        if team["season"] >= 2025:
            plans[(team["season"], team["nflverse"], team["week"])] = ("snapshot", games[team["game_id"]])
            evidence[key] = f"nflverse depth_charts_{team['season']}.csv snapshot on or before {games[team['game_id']]}"
        elif mode == "season":
            lineup = season_lineup(inputs, team["season"], team["nflverse"])
            plans[(team["season"], team["nflverse"], team["week"])] = ("season", lineup)
            evidence[key] = {"source": f"nflverse depth_charts_{team['season']}.csv: listed first in at least half "
                                       f"the regular-season weeks", "starters": {
                                           pid: (f"{slot} {n}/{weeks} weeks" if n >= 0 else f"{slot} by {-n} regular-season snaps") for pid, (slot, _f, n, weeks) in sorted(lineup.items())}}
        else:
            evidence[key] = f"nflverse depth_charts_{team['season']}.csv week {team['week']} (the spec's chosen week)"

    def depth_chart_for(inputs_, season, club, week):
        plan = plans.get((season, club, week))
        if plan is None:
            return original(inputs_, season, club, week)
        if plan[0] == "snapshot":
            chart = snapshot_chart(inputs_, season, club, plan[1])
        else:
            chart = original(inputs_, season, club, week)
            for e in chart.values():
                e["order"] += 10000
                if e["rank"] == 1:
                    e["rank"] = 2
            for i, (pid, (slot, formation, _n, _w)) in enumerate(sorted(plan[1].items(), key=lambda kv: kv[1][0])):
                chart[pid] = {"depth_position": slot, "rank": 1, "order": i + 1, "formation": formation,
                              "roster_position": (chart.get(pid) or {}).get("roster_position", "")}
        _three_four(chart)
        return chart
    m2.depth_chart_for = depth_chart_for
    return evidence


def featured_starters(spec: dict, inputs) -> dict[str, list[str]]:
    """Season starters missing from the chosen week's pool join it (m2 'featured': taken from the season roster)."""
    out = {}
    for key, team in spec["teams"].items():
        if team["season"] >= 2025 or team.get("lineup", "season") != "season":
            continue
        roster = {r["gsis_id"]: m2.ascii_name(r["full_name"]) for r in inputs.rows(f"roster_{team['season']}.csv")
                  if r["team"] in m2.club_codes(team["nflverse"]) and r.get("gsis_id")}
        counts = collections.Counter(roster.values())
        names = []
        for pid in sorted(season_lineup(inputs, team["season"], team["nflverse"])):
            if pid in roster and counts[roster[pid]] == 1:
                names.append(roster[pid])
        out[key] = sorted(set(names) | set(team.get("featured", [])))
    return out


def generate(spec_path: Path, inputs: Path, retail: Path, out: Path) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    shared = json.loads(m2.SPEC.read_text(encoding="utf-8"))
    reader = m2.Inputs(inputs)
    games = {r["game_id"]: r["gameday"] for r in m2.rm.read_csv(Path(inputs) / "games.csv")}
    featured = featured_starters(spec, reader)
    lineups = install_lineups(spec, reader, games)
    teams = {}
    for key, team in spec["teams"].items():
        m2.require(key == f"{team['selector']}_{team['season']}", f"{key}: key must be selector_season")
        m2.require(team["selector"] in m2.FRANCHISES, f"{key}: unknown selector")
        m2.require(team["game_id"] in games, f"{key}: game {team['game_id']} is not in games.csv")
        teams[key] = {k: v for k, v in team.items() if k not in ("why", "lineup")}
        if featured.get(key):
            teams[key]["featured"] = featured[key]
    merged = {"schema": 1, "about": spec["about"], "left_handed": shared["left_handed"],
              "display_names": shared["display_names"], "handedness": shared["handedness"],
              "teams": teams, "moments": []}
    with tempfile.TemporaryDirectory(prefix="ct1-classic-") as folder:
        work = Path(folder)
        merged_path = work / "spec.json"
        merged_path.write_text(json.dumps(merged, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        m2.generate(merged_path, inputs, retail, work / "out")
        made = work / "out" / m2.TEAMS_DIR
        # The ratings reference is the one the Anniversary teams use; a different one means different inputs.
        reference = (work / "out" / m2.REFERENCE_NAME).read_bytes()
        m2.require(reference == (m2.OUT_DATA / m2.REFERENCE_NAME).read_bytes(),
                   "the ratings reference differs from data/nfl2k5_ratings_reference.json (other retail or combine input)")
        files = {}
        for path in sorted(made.glob("*.csv")):
            files[path.name] = path.read_bytes()
        teams_doc = json.loads((made / "teams.json").read_text(encoding="utf-8"))
        teams_doc["evidence"] = EVIDENCE
        for key, record in teams_doc["teams"].items():
            record["why"] = spec["teams"][key]["why"]
        files["teams.json"] = (json.dumps(teams_doc, indent=2, sort_keys=True) + "\n").encode()
        manifest = json.loads((made / "manifest.json").read_text(encoding="utf-8"))
        manifest.update(generator=GENERATOR, evidence=EVIDENCE, spec_sha256=sha(spec_path.read_bytes()),
                        schema="nfl2k5.classic_teams.manifest.v1")
        manifest["shared_spec_sha256"] = sha(m2.SPEC.read_bytes())
        for key, lineup in lineups.items():
            manifest["teams"][key]["lineup"] = lineup
            manifest["teams"][key]["why"] = spec["teams"][key]["why"]
        manifest["sources"]["nflverse"]["files"]["games.csv"] = sha((Path(inputs) / "games.csv").read_bytes())
        manifest["sources"]["nflverse"]["games_url"] = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
        files["manifest.json"] = (m2.compact_json(manifest) + "\n").encode()
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    return {"teams": len(teams), "files": sorted(files)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument("--inputs", type=Path, default=m2.DEFAULT_INPUTS)
    parser.add_argument("--retail", type=Path, default=m2.DEFAULT_RETAIL)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--check", action="store_true", help="regenerate in temporary storage and compare every byte")
    args = parser.parse_args(argv)
    if not args.check:
        print(json.dumps(generate(args.spec, args.inputs, args.retail, args.out), indent=1))
        return 0
    with tempfile.TemporaryDirectory(prefix="ct1-classic-check-") as folder:
        result = generate(args.spec, args.inputs, args.retail, Path(folder))
        for name in result["files"]:
            shipped = args.out / name
            m2.require(shipped.is_file() and shipped.read_bytes() == (Path(folder) / name).read_bytes(),
                       f"regeneration differs: {name}")
        extra = {p.name for p in args.out.iterdir() if p.suffix in (".csv", ".json")} - set(result["files"])
        extra -= {"appearance.json", "classic.json"}
        m2.require(not extra, f"unexpected files in {args.out}: {sorted(extra)}")
    print(f"all {len(result['files'])} generated files reproduce exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
