#!/usr/bin/env python3
"""Seed pb/v2/teams/<TEAM>.json team packages (beta 77, job p48o).

Inputs (sourced): pb/research/team_profiles.json (staff, scheme family, emphasis, feature
role, checked 2026-09-24 against club sites) and pb/research/tendencies_2025.json
(nflverse / FTN 2025 regular season: personnel, shotgun, pistol, play action).
Everything this script adds on top (concept boosts, signature plays) is DESIGN.
Re-running overwrites the packages: hand edits belong in the JSON files, so run it only
to reset a team (``--team KC``) or to seed a new league.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "pb" / "research"
TEAMS = ROOT / "pb" / "v2" / "teams"
ALIASES = {"ARZ": "ARI", "STL": "LA", "SD": "LAC", "OAK": "LV"}

FAMILY_BOOST = {
    "wide_zone": {"Outside Zone": 3, "PA Boot": 3, "PA Boot Leak": 2, "Yankee": 2, "Drive": 2, "Sail": 1,
                  "Counter": 1, "Y Cross": 1, "Dagger": 1},
    "mcvay": {"Outside Zone": 2, "Duo": 2, "PA Boot": 2, "Dagger": 2, "Drive": 2, "Yankee": 2, "Mills": 1, "Levels": 1},
    "west_coast": {"Mesh": 3, "Stick": 2, "Snag": 2, "Spacing": 2, "Drive": 2, "Slant Flat": 2, "RB Screen": 2,
                   "Texas": 1, "Bubble Screen": 1},
    "vertical": {"Four Verticals": 2, "Mills": 2, "Double Post": 2, "Dagger": 2, "Y Cross": 2, "PA Shot": 2,
                 "Post Corner": 1, "Out and Up": 1},
    "power": {"Power": 3, "Counter": 2, "Duo": 2, "Iso": 2, "Trap": 1, "PA Dagger": 2, "Yankee": 1, "QB Sneak": 1},
    "spread": {"Stick": 2, "Snag": 2, "Bubble Screen": 2, "Spacing": 2, "Draw": 2, "QB Draw": 2, "Mesh": 1,
               "Four Verticals": 1, "Quick Outs": 1},
}
EMPHASIS_MAP = {"Mesh": "Mesh", "Stick": "Stick", "RB Slip": "RB Screen", "Outside Zone": "Outside Zone",
                "PA Boot": "PA Boot", "TE Seam": "Dagger", "TE Drag": "Drive", "Downhill": "Duo",
                "Counter": "Counter", "Inside Zone": "Inside Zone", "End Around": "End Around", "Levels": "Levels",
                "Dagger": "Dagger", "Y Cross": "Y Cross", "Flood": "Flood", "Drive": "Drive"}
FEATURE_BOOST = {"TE1": {"Y Cross": 1, "Stick": 1, "TE Screen": 1, "PA Boot Leak": 1},
                 "WR1": {"Dagger": 1, "Mills": 1, "Smash": 1, "Double Post": 1},
                 "HB1": {"Texas": 1, "RB Screen": 1, "Draw": 1, "Outside Zone": 1}}

#: DESIGN: two or three signature plays per team: (formation, concept, display name, overrides).
#: Each one changes at least one assignment against the core design, so it is a play of its own.
SIGNATURES = {
    "ARZ": [("Ace Wing", "PA Boot Leak", "Y Leak Boot", {}),
            ("Singleback Ace", "Y Cross", "Y Cross Over", {"routes": {"Y": ["route", "Deep Cross", 12]}}),
            ("Gun Y Trips", "Stick", "Y Stick Seam", {"routes": {"S2": ["route", "Seam", 15]}})],
    "ATL": [("Pistol Strong", "Counter", "Pistol Counter Weak", {"direction": "weak"}),
            ("Gun Doubles", "Mesh", "Mesh Wheel", {"routes": {"B": ["route", "Back Wheel"]}}),
            ("I-Form Pro", "Outside Zone", "Wide Zone Weak", {"direction": "weak"})],
    "BAL": [("I-Form Tight", "Power", "Power Weak", {"direction": "weak"}),
            ("Pistol Strong", "Yankee", "Pistol Yankee", {"routes": {"S1": ["route", "Over", 10]}}),
            ("Gun Doubles", "QB Draw", "QB Power Draw", {})],
    "BUF": [("Gun Doubles", "Slant Flat", "Slant Wheel", {"routes": {"S2": ["route", "Wheel", 2]}}),
            ("Ace Jumbo", "QB Sneak", "Jumbo Sneak", {}),
            ("Gun Trips", "Levels", "Levels Seam", {"routes": {"S3": ["route", "Seam", 16]}})],
    "CAR": [("Gun Trey", "Y Cross", "X Dig Cross", {"routes": {"W1": ["route", "Dig", 12]}}),
            ("Singleback Doubles", "PA Boot", "Boot Corner", {"routes": {"W1": ["route", "Corner", 14]}})],
    "CHI": [("Ace Jumbo", "PA Boot Leak", "Jumbo Leak", {}),
            ("Singleback Ace", "PA Shot", "PA Post Wheel", {"routes": {"S2": ["route", "Wheel", 2]}}),
            ("Gun Y Trips", "Y Cross", "Y Cross Sluggo", {"routes": {"W1": ["route", "Slant and Go", 1]}})],
    "CIN": [("Gun Doubles", "Mills", "X Mills", {"routes": {"W1": ["route", "Dig", 13], "W2": ["route", "Post", 12]}}),
            ("Gun Trips", "Bubble Screen", "Trips Bubble", {}),
            ("Gun Spread", "Four Verticals", "Verts Bender", {"routes": {"S2": ["route", "Skinny Post", 12]}})],
    "CLE": [("Singleback Ace", "Y Cross", "Y Cross Post", {"routes": {"S1": ["route", "Skinny Post", 12]}}),
            ("Heavy Wing", "Counter", "Wing Counter", {"direction": "weak"})],
    "DAL": [("Gun Doubles", "Four Verticals", "Verts Choice", {"routes": {"S2": ["route", "Hook", 9]}}),
            ("Gun Trey", "Out and Up", "X Out and Up", {}),
            ("I-Form Pro", "PA Dagger", "PA X Dagger", {"routes": {"W1": ["route", "Dig", 15]}})],
    "DEN": [("Gun Bunch", "Mesh", "Bunch Mesh", {"routes": {"S1": ["route", "Corner", 12]}}),
            ("Singleback Doubles", "Drive", "Drive Swing", {"routes": {"B": ["check", "Swing"]}})],
    "DET": [("I-Form Pro", "Flea Flicker", "Flea Flicker Post", {}),
            ("Gun Split Backs", "Texas", "Texas Wheel", {"routes": {"B2": ["route", "Back Wheel"]}}),
            ("I-Form Tight", "Power", "Power Weak", {"direction": "weak"})],
    "GB": [("Ace Wing", "Drive", "Wing Drive", {"routes": {"S3": ["route", "Shallow", 5]}}),
           ("Singleback Ace", "PA Boot", "Boot Over", {"routes": {"S1": ["route", "Deep Cross", 13]}})],
    "HOU": [("Singleback Doubles", "Dagger", "X Dagger", {"routes": {"W1": ["route", "Dig", 15], "W2": ["route", "Seam", 15]}}),
            ("Gun Trey", "Levels", "Levels Over", {"routes": {"S3": ["route", "Over", 9]}})],
    "IND": [("Singleback Ace", "Y Cross", "Y Cross Seam", {"routes": {"W2": ["route", "Seam", 16]}}),
            ("Ace Jumbo", "Inside Zone", "Jumbo Zone Weak", {"direction": "weak"})],
    "JAX": [("Gun Trey", "Mills", "Trey Mills", {}),
            ("Singleback Doubles", "End Around", "Slot Reverse", {})],
    "KC": [("Gun Bunch", "Mesh", "Bunch Mesh Wheel", {"routes": {"B": ["route", "Back Wheel"]}}),
           ("Gun Trey", "Stick", "Y Stick Nod", {"routes": {"S3": ["route", "Stop and Go", 6]}}),
           ("Gun Doubles", "RB Screen", "Swing Screen", {})],
    "MIA": [("Pistol Doubles", "Outside Zone", "Pistol Wide Zone", {}),
            ("Gun Doubles", "Four Verticals", "Verts Swing", {"routes": {"B": ["route", "Swing"]}}),
            ("Singleback Doubles", "End Around", "Speed Reverse", {})],
    "MIN": [("Singleback Trey", "Y Cross", "Y Cross Dig", {"routes": {"W1": ["route", "Dig", 14]}}),
            ("Gun Doubles", "Double Post", "Yankee Posts", {"routes": {"W1": ["route", "Post", 14]}})],
    "NE": [("I-Form Pro", "Iso", "Iso Weak", {"direction": "weak"}),
           ("Singleback Trey", "Drive", "Y Drive", {"routes": {"S3": ["route", "Drag", 2]}})],
    "NO": [("Gun Doubles", "Mesh", "Mesh Sit", {"routes": {"S1": ["route", "Hook", 9]}}),
           ("Gun Spread", "Dagger", "Spread Dagger", {"routes": {"W1": ["route", "Curl", 12]}})],
    "NYG": [("Singleback Ace", "Y Cross", "Y Over Cross", {"routes": {"W2": ["route", "Over", 9]}}),
            ("Gun Trey", "Stick", "Trey Stick Seam", {"routes": {"S2": ["route", "Seam", 15]}})],
    "NYJ": [("Gun Doubles", "Smash", "Smash Wheel", {"routes": {"B": ["route", "Back Wheel"]}}),
            ("Gun Trips", "Flood", "Trips Sail", {"routes": {"S2": ["route", "Sail", 12]}})],
    "OAK": [("Singleback Ace", "Y Cross", "Y Cross Bender", {"routes": {"S2": ["route", "Seam", 16]}}),
            ("I-Form Pro", "Outside Zone", "Stretch Weak", {"direction": "weak"})],
    "PHI": [("Ace Jumbo", "QB Sneak", "Tush Push", {}),
            ("Gun Doubles", "RB Screen", "Slip Screen", {}),
            ("Singleback Doubles", "Smash", "Smash Post", {"routes": {"S2": ["route", "Post", 11]}})],
    "PIT": [("Ace Jumbo", "PA Boot", "Jumbo Boot", {}),
            ("Gun Doubles", "Shallow Cross", "Shallow Go", {"routes": {"W1": ["route", "Go", 15]}})],
    "SD": [("Gun Doubles", "Mesh", "Mesh Rail", {"routes": {"B": ["route", "Back Wheel"]}}),
           ("Weak I", "Inside Zone Weak", "Weak Zone Lead", {})],
    "SEA": [("I-Form Pro", "PA Boot", "Boot Over Deep", {"routes": {"S1": ["route", "Deep Cross", 13]}}),
            ("Gun Doubles", "Dagger", "Dagger Seam", {"routes": {"S2": ["route", "Seam", 16]}})],
    "SF": [("I-Form Pro", "Outside Zone", "Wide Zone Weak", {"direction": "weak"}),
           ("Strong I", "PA Boot", "Boot Leak FB", {"routes": {"B2": ["leak", "Shallow", 1.2, 2]}}),
           ("Singleback Doubles", "End Around", "Jet Reverse", {})],
    "STL": [("Ace Jumbo", "PA Boot", "Jumbo Boot Over", {"routes": {"S1": ["route", "Over", 10]}}),
            ("Singleback Doubles", "Dagger", "Dagger Dig", {"routes": {"W1": ["route", "Dig", 14]}}),
            ("Singleback Trey", "Drive", "Trey Drive", {})],
    "TB": [("Gun Trey", "Y Cross", "Trey Cross", {"routes": {"S2": ["route", "Out", 12]}}),
           ("Singleback Doubles", "PA Boot", "Boot Flood", {"routes": {"W2": ["route", "Sail", 10]}})],
    "TEN": [("Gun Doubles", "Slant Flat", "Slant Seam", {"routes": {"S2": ["route", "Seam", 15]}}),
            ("Gun Empty", "Spacing", "Empty Spacing", {"routes": {"S3": ["route", "Snag", 4]}})],
    "WAS": [("Pistol Doubles", "QB Draw", "Pistol QB Draw", {}),
            ("Gun Trips", "Bubble Screen", "Trips Bubble", {}),
            ("Gun Doubles", "Four Verticals", "Verts Post", {"routes": {"W2": ["route", "Post", 14]}})],
}


def seed(team: str, profiles: dict, tendencies: dict) -> dict:
    p = profiles[team]
    t = tendencies[ALIASES.get(team, team)]
    boost: dict[str, int] = {}
    for src in (FAMILY_BOOST.get(p["family"], {}), FEATURE_BOOST.get(p["feature_role"], {})):
        for k, v in src.items():
            boost[k] = boost.get(k, 0) + v
    for e in p.get("emphasis", []):
        k = EMPHASIS_MAP.get(e)
        if k:
            boost[k] = boost.get(k, 0) + 2
    pa = t.get("play_action_pct", 22.0)
    shift = {}
    if pa >= 27:
        shift = {"PA Boot": -1, "PA Boot Leak": -1, "Yankee": -1, "PA Dagger": -1, "PA Crossers": -1}
    elif pa <= 18:
        shift = {"PA Boot": 1, "PA Crossers": 1, "PA Dagger": 1}
    prefer = []
    if t.get("pistol_pct", 0) >= 10:
        prefer += ["Pistol Doubles", "Pistol Ace", "Pistol Strong"]
    pers = t.get("personnel", {})
    total = sum(pers.values()) or 1
    if 100.0 * pers.get("13", 0) / total >= 8:
        prefer.append("Ace Jumbo")
    if 100.0 * pers.get("21", 0) / total >= 14:
        prefer += ["Weak I", "Split Backs"]
    for formation, _concept, _name, _ov in SIGNATURES.get(team, []):
        if formation not in prefer and formation in ("Ace Jumbo", "Pistol Doubles", "Pistol Strong", "Pistol Ace",
                                                     "Weak I", "Split Backs", "I-Form Twins", "Gun Wing"):
            prefer.append(formation)
    return {
        "team": team,
        "status": "DESIGN",
        "identity": p["scheme"],
        "staff": p["staff"],
        "family": p["family"],
        "feature": p["feature_role"],
        "key_players": p["key_players"],
        "depth_step": int(p.get("route_depth_step", 0)) // 2,
        "tendencies": {k: t[k] for k in ("shotgun_pct", "pistol_pct", "play_action_pct", "motion_pct") if k in t}
                      | {"personnel": t.get("personnel", {})},
        "formations": {"prefer": prefer, "avoid": []},
        "boost": dict(sorted(boost.items())),
        "preference_shift": shift,
        "signature": [{"formation": f, "concept": c, "name": n, "overrides": o}
                      for f, c, n, o in SIGNATURES.get(team, [])],
        "menu_adds": {},
        "sources": {"profile": "pb/research/team_profiles.json (" + p.get("staff_source", "") + ")",
                    "tendencies": "pb/research/tendencies_2025.json (nflverse / FTN 2025)",
                    "design": "boosts, preferences and signature plays are DESIGN (beta 77 p48o)"},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--team", action="append")
    args = ap.parse_args(argv)
    profiles = json.loads((RESEARCH / "team_profiles.json").read_text())["teams"]
    tendencies = {r["team"]: r for r in json.loads((RESEARCH / "tendencies_2025.json").read_text())["teams"]}
    TEAMS.mkdir(parents=True, exist_ok=True)
    for team in args.team or sorted(profiles):
        pkg = seed(team, profiles, tendencies)
        (TEAMS / f"{team}.json").write_text(json.dumps(pkg, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(team, len(pkg["signature"]), "signature plays,", len(pkg["boost"]), "boosts")


if __name__ == "__main__":
    main()
