#!/usr/bin/env python3
"""b780 roster1: per-club difference between two built main rosters (bare ROST bodies), as the game reads them.

Membership (active, practice squad, free agents), jersey numbers, the six special-teams bytes and every depth-chart
slot row 0 of the game's own slot table (offense, 4-3, 3-4 and the SPECIAL views; chain 0 rank, 1 side, 2/3 the rank
or side row 1, 4 the rank row 2), with an empty slot shown as "(empty)".

  python3 tools/b780/roster1_refresh_diff.py BEFORE.body AFTER.body OUT.json [--markdown OUT.md] [--note TEXT]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT)]

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

POS = rr.SCHEME_POSITION_NAMES["one_pool"]
# (label, position, chain) of the SPECIAL-table build (0xEE3000): unit name + slot abbreviation
SLOTS = [("OFF QB", 0, 0), ("OFF RB", 7, 0), ("OFF FB", 8, 0), ("OFF X", 3, 0), ("OFF Z", 3, 1), ("OFF TE", 9, 0),
         ("OFF LT", 14, 0), ("OFF LG", 13, 0), ("OFF C", 12, 0), ("OFF RG", 13, 1), ("OFF RT", 14, 1),
         ("4-3 LEDGE", 16, 0), ("4-3 LDT", 15, 0), ("4-3 RDT", 15, 1), ("4-3 REDGE", 16, 1), ("4-3 SAM", 11, 3),
         ("4-3 MIKE", 11, 0), ("4-3 WILL", 11, 1), ("4-3 RCB", 4, 1), ("4-3 LCB", 4, 0), ("4-3 SS", 6, 0),
         ("4-3 FS", 5, 0), ("3-4 LDT", 15, 1), ("3-4 NT", 15, 0), ("3-4 RDT", 15, 3), ("3-4 WILL", 11, 1),
         ("3-4 MIKE", 11, 0), ("3-4 REDGE", 16, 1), ("3-4 LEDGE", 16, 0), ("ST K", 1, 0), ("ST P", 2, 0),
         ("ST LS", 12, 2), ("ST LGUN", 3, 3), ("ST RGUN", 4, 3), ("ST NCB", 4, 2), ("ST DCB", 4, 3),
         ("ST SLWR", 3, 2), ("ST GAD", 3, 4), ("ST 3DRB", 7, 0), ("ST PWRB", 7, 1)]
CHAIN = {0: ("depth_rank", 0), 1: ("depth_side", 0), 2: ("depth_rank", 1), 3: ("depth_side", 1), 4: ("depth_rank", 2)}


def snapshot(body):
    doc = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
    clubs = {}
    for team in doc.teams[:32]:
        roster = [doc.by_offset[o] for o in team.slots]
        slots = {}
        for label, position, chain in SLOTS:
            field, row = CHAIN[chain]
            who = [p.display for p in roster if p.record.get("position") == position and p.record.get(field) == row]
            slots[label] = ", ".join(who) if who else "(empty)"
        special = {}
        for key, offset in rr.SPECIAL_TEAM_OFFSETS.items():
            slot = doc.body[team.offset + offset]
            special[key] = roster[slot].display if slot < len(roster) else "(none)"
        clubs[team.abbreviation] = {
            "active": {p.display: (POS[p.record.get("position")], p.record.get("jersey")) for p in roster},
            "reserves": sorted(p.display for p in doc.reserve_players(team.index)),
            "slots": slots, "special": special}
    free = {doc.by_offset[o].display for o in doc.free_agents}
    return clubs, free


def compare(before_body, after_body):
    before, before_free = snapshot(before_body)
    after, after_free = snapshot(after_body)
    where_after = {name: club for club, data in after.items() for name in data["active"]}
    where_before = {name: club for club, data in before.items() for name in data["active"]}
    squad_after = {name: club for club, data in after.items() for name in data["reserves"]}
    squad_before = {name: club for club, data in before.items() for name in data["reserves"]}
    out = {}
    for club in after:
        b, a = before[club], after[club]
        def origin(name):
            if name in where_before:
                return where_before[name]
            if name in squad_before:
                return f"{squad_before[name]} practice squad"
            return "free agents" if name in before_free else "injured reserve (no list)"
        def destination(name):
            if name in where_after:
                return where_after[name]
            if name in squad_after:
                return f"{squad_after[name]} practice squad"
            return "free agents" if name in after_free else "injured reserve (no list)"
        out[club] = {
            "active": [len(b["active"]), len(a["active"])],
            "joined": [f"{n} {a['active'][n][0]} (from {origin(n)})" for n in a["active"] if n not in b["active"]],
            "left": [f"{n} {b['active'][n][0]} (to {destination(n)})" for n in b["active"] if n not in a["active"]],
            "practice_squad_in": [n for n in a["reserves"] if n not in b["reserves"]],
            "practice_squad_out": [n for n in b["reserves"] if n not in a["reserves"]],
            "jersey": [f"{n} #{b['active'][n][1]}->#{a['active'][n][1]}" for n in a["active"]
                       if n in b["active"] and b["active"][n][1] != a["active"][n][1]],
            "special": {k: f"{b['special'][k]} -> {v}" for k, v in a["special"].items() if b["special"][k] != v},
            "slots": {k: f"{b['slots'][k]} -> {v}" for k, v in a["slots"].items() if b["slots"][k] != v},
            "empty_slots_before": [k for k, v in b["slots"].items() if v == "(empty)"],
            "empty_slots_after": [k for k, v in a["slots"].items() if v == "(empty)"],
        }
    return out


def markdown(diff, note):
    lines = ["# SOFTDRINK 2K28 roster refresh 11/03 vs the v0.9 RC roster", "", note, ""]
    for club, d in sorted(diff.items()):
        lines.append(f"## {club} (active {d['active'][0]} -> {d['active'][1]})")
        for key, title in (("joined", "Joined"), ("left", "Left"), ("practice_squad_in", "Practice squad in"),
                           ("practice_squad_out", "Practice squad out"), ("jersey", "Numbers")):
            if d[key]:
                lines.append(f"- {title}: " + "; ".join(d[key]))
        if d["special"]:
            lines.append("- Special teams: " + "; ".join(f"{k} {v}" for k, v in d["special"].items()))
        if d["slots"]:
            lines.append("- Depth chart starters: " + "; ".join(f"{k}: {v}" for k, v in d["slots"].items()))
        if d["empty_slots_after"]:
            lines.append("- Empty slots after: " + ", ".join(d["empty_slots_after"]))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("out")
    ap.add_argument("--markdown")
    ap.add_argument("--note", default="")
    args = ap.parse_args(argv)
    diff = compare(Path(args.before).read_bytes(), Path(args.after).read_bytes())
    Path(args.out).write_text(json.dumps(diff, indent=1, ensure_ascii=False), encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(markdown(diff, args.note), encoding="utf-8")
    moved = sum(len(d["joined"]) for d in diff.values())
    print(json.dumps({"clubs": len(diff), "players_joined": moved,
                      "empty_slots_before": sum(len(d["empty_slots_before"]) for d in diff.values()),
                      "empty_slots_after": sum(len(d["empty_slots_after"]) for d in diff.values())}))


if __name__ == "__main__":
    main()
