#!/usr/bin/env python3
"""Team-unique package plan for the 31 other books (beta 77, job p6s, GOAL P6). Read only; writes the plan JSON.

For each team: identity (staff and scheme from pb/v2/teams/<T>.json, already sourced there), its 2025 tendencies
(pb/research/situational_2025.json), the book's capacity (ordinary formations, play slots, offense node budget from
pb/v2/catalogs/<T>.json), a CPU personnel recommendation, and a short list of team plays chosen by rule from the
team's measured style (targeted-route mix against the league mean, aDOT, play action, screens, RPO). Every rule and
every number is in the output so a Sonnet swarm can apply it mechanically with pb/v2/build.py and pb/v2/fit_cpu.py.

    python3 tools/b77/p6s_team_plan.py --out PLAN.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
NFLVERSE = {"ARZ": "ARI", "STL": "LA", "SD": "LAC", "OAK": "LV"}
# route-mix delta (targeted route share minus league mean, percentage points) -> team plays that lean into it
ROUTE_RULES = {
    "IN/DIG": [("Dagger", "Gun Doubles"), ("Mills", "Singleback Doubles"), ("Levels", "Gun Trips")],
    "QUICK OUT": [("Quick Outs", "Gun Doubles"), ("Bench", "Gun Trey"), ("Smash", "Singleback Doubles")],
    "HITCH/CURL": [("Curl Flat", "Singleback Doubles"), ("Hank", "Gun Doubles"), ("Comebacks", "Gun Doubles Tight")],
    "SCREEN": [("RB Screen", "Gun Doubles"), ("Bubble Screen", "Gun Trips"), ("TE Screen", "Ace Wing")],
    "SWING": [("Mesh Wheel", "Gun Doubles Tight"), ("Texas", "Gun Trey")],
    "SLANT": [("Slant Flat", "Gun Doubles"), ("Double Slants", "Gun Bunch")],
    "CORNER": [("Scissors", "Gun Doubles"), ("Post Corner", "Singleback Doubles")],
    "DEEP OUT": [("Bench", "Gun Trips"), ("Comebacks", "Gun Wing")],
    "GO": [("Four Verticals", "Gun Doubles"), ("Hitch Seam", "Gun Trey")],
    "POST": [("Post Wheel", "Singleback Doubles"), ("Double Post", "Gun Doubles")],
    "SHALLOW CROSS/DRAG": [("Shallow Cross", "Gun Doubles"), ("Drive", "Gun Trey"), ("Mesh", "Gun Bunch")],
    "WHEEL": [("Post Wheel", "Singleback Doubles")],
}
STYLE_RULES = [  # (metric, threshold over league mean, plays)
    ("play_action_pct", 4.0, [("PA Boot", "Singleback Doubles"), ("PA Crossers", "Singleback Ace"), ("Yankee", "I-Form Pro")]),
    ("adot", 0.8, [("PA Shot", "Singleback Ace"), ("Post Wheel", "Pistol Doubles"), ("Stick Nod", "Gun Trips")]),
    ("rpo_pct", 2.5, [("Slant Flat", "Pistol Doubles"), ("Bubble Screen", "Gun Doubles"), ("Stick", "Gun Wing")]),
    ("screen_pct", 2.5, [("WR Slip Screen", "Gun Doubles"), ("RB Screen", "Gun Trey")]),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    research = json.loads((ROOT / "pb/research/situational_2025.json").read_text(encoding="utf-8"))["teams"]
    styles = {t: v["style"] for t, v in research.items()}
    routes = sorted({r for s in styles.values() for r in s["target_routes_pct"]})
    league_route = {r: statistics.mean(s["target_routes_pct"].get(r, 0) for s in styles.values()) for r in routes}
    league_style = {k: statistics.mean(s[k] for s in styles.values() if s[k] is not None)
                    for k in ("adot", "play_action_pct", "screen_pct", "rpo_pct")}
    plan = {}
    for path in sorted((ROOT / "pb/v2/teams").glob("*.json")):
        team = path.stem
        pkg = json.loads(path.read_text(encoding="utf-8"))
        cat = json.loads((ROOT / f"pb/v2/catalogs/{team}.json").read_text(encoding="utf-8"))
        key = NFLVERSE.get(team, team)
        bins, style = research[key]["bins"], styles[key]
        deltas = {r: round(style["target_routes_pct"].get(r, 0) - league_route[r], 1) for r in routes}
        plays, why = [], []
        for r, d in sorted(deltas.items(), key=lambda kv: -kv[1]):
            if d >= 2.0 and r in ROUTE_RULES:
                for concept, form in ROUTE_RULES[r]:
                    plays.append(dict(concept=concept, formation=form, reason=f"targets {r} {style['target_routes_pct'].get(r, 0)}% (league {league_route[r]:.1f})"))
        for metric, gap, rows in STYLE_RULES:
            v = style[metric]
            if v is not None and v - league_style[metric] >= gap:
                for concept, form in rows:
                    plays.append(dict(concept=concept, formation=form, reason=f"{metric} {v} (league {league_style[metric]:.1f})"))
        if len(plays) < 5:      # quiet route profile: lean on the strongest positive deltas, then the package's own picks
            for r, d in sorted(deltas.items(), key=lambda kv: -kv[1]):
                if 0.5 <= d < 2.0 and r in ROUTE_RULES:
                    concept, form = ROUTE_RULES[r][0]
                    plays.append(dict(concept=concept, formation=form, reason=f"targets {r} {style['target_routes_pct'].get(r, 0)}% (league {league_route[r]:.1f}, small lean)"))
            for sig in pkg.get("signature", []):
                plays.append(dict(concept=sig["concept"], formation=sig["formation"], name=sig.get("name"),
                                  reason="existing package signature (DESIGN, p48o): keep and make it the team's own"))
        seen, unique = set(), []
        for p in plays:
            if (p["concept"], p["formation"]) not in seen:
                seen.add((p["concept"], p["formation"]))
                unique.append(p)
        d3l = bins.get("d3_long", {}).get("personnel", {})
        if pkg.get("personnel_groups"):
            twins = [dict(record=rec, **spec, reason="team package (built)") for rec, spec in pkg["personnel_groups"].items()]
        else:
            twins = None
        p12 = d3l.get("12", 0) + d3l.get("12+", 0)
        p10 = d3l.get("10", 0)
        if twins is not None:
            pass
        else:
          twins = [dict(record="Flush (else Queens)", twin_of="11", code=9, name="Kings Long", reason=f"3rd and 7+: 11 personnel {d3l.get('11', 0)}%")]
          if p12 >= 10:
            twins.append(dict(record="Straight (else Queens)", twin_of="12", code=8, name="Ace Long", reason=f"3rd and 7+: 12 personnel {p12}%"))
          if p10 >= 5:
            twins[0]["record"] = "Queens"
            twins[0]["note"] = f"keeps the stock Flush group (10 personnel {p10}% on 3rd and 7+) and the optional Gun Spread / Gun Trips Open sets"
        plan[team] = dict(
            identity=dict(staff=pkg.get("staff"), scheme=pkg.get("identity"), family=pkg.get("family"),
                          key_players=pkg.get("key_players"), sources=pkg.get("sources")),
            capacity=dict(ordinary_formations=len(cat["formations"]), play_slots=len(cat["plays"]),
                          offense_nodes=cat["node_budget"]["after"], offense_node_cap=cat["node_budget"]["cap"],
                          note="team plays replace core plays (play slots are fixed); the offense cap is 2,300 of the "
                               "3,500 nodes with p48d's v2 defense (about 400-570 nodes) and the 78 kickoff-return nodes"),
            tendencies_2025=dict(nflverse_team=key, style=style, route_delta_vs_league=deltas,
                                 bins={b: dict(snaps=v["snaps"], gun_pct=v["gun_pct"], pass_pct=v["pass_pct"],
                                               personnel=v["personnel"]) for b, v in bins.items()}),
            cpu_personnel=dict(twins=twins, fit="python3 pb/v2/fit_cpu.py --image RETAIL --team " + team + " --write"),
            team_plays=unique[:10],
            status="PLAN (DESIGN on sourced 2025 data); TEN is built (job p6s)" if team != "TEN" else "BUILT (job p6s)")
    doc = dict(schema="b77.p6s.team-package-plan.v1", status="PLAN", runtime_witness=False,
               league_route_mean=league_route, league_style_mean=league_style,
               route_rules=ROUTE_RULES, style_rules=[dict(metric=m, over_league=g, plays=r) for m, g, r in STYLE_RULES],
               how_to_build=[
                   "1. Read pb/v2/TEAM_PACKAGES.md and the TEN example (pb/v2/teams/TEN.json).",
                   "2. Add team_plays to the package as named menu entries (menus or menu_adds) with an override that makes each one the team's own (a different read, depth or route on one player), keeping menus at 8-12 and the node cap.",
                   "3. Keep the default Kings Long twin unless the plan names other twins; add them in personnel_groups.",
                   "4. Run pb/v2/fit_cpu.py --write for the team, then pb/v2/build.py --team T --write, pb/defense/build.py --team T, pb/v2/pins.py --write, pb/v2/verify.py --team T (lint 0).",
                   "5. Check the native call mix on 3rd and 8 / 1st and 10 / 3rd and 1 (u-ai harness) and the route execution check (no OOB, COLLIDE or STACK on new plays).",
                   "6. Never invent staff, players or tendencies: every fact needs a source; mark design choices as DESIGN."],
               teams=plan)
    args.out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("wrote", args.out, len(plan), "teams")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
