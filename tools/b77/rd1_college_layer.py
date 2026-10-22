#!/usr/bin/env python3
"""b778 rd1: the latest school of every transfer, as a pinned layer plus a merge into a league roster-edits document.

    python3 tools/b77/rd1_college_layer.py plan DISC NFLVERSE_ROSTER_2026.csv [--out data/nfl2k5_college_latest_school_2026.json]
    python3 tools/b77/rd1_college_layer.py merge LEAGUE_EDITS.json OUT.json [--layer data/nfl2k5_college_latest_school_2026.json]

nflverse lists a player's schools latest first ("Texas; Houston"); the 2026 roster generator walked the list backwards and
wrote the oldest school its table had (v0.6.1: Matthew Golden Houston, Joe Burrow Ohio State, Bo Nix Auburn, 261 in all).
``plan`` lists, for the players of fr/identities.csv, every disc player whose school is not the latest listed school that
the disc's own college table holds (nothing is added to the table). ``merge`` adds them to the league document's
``college_updates``, replacing a same-player entry, and refuses anything else it would change.
"""
from __future__ import annotations

import argparse
import collections
import copy
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fr.colleges import school  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

SCHEMA = "nfl2k5_college_latest_school/v1"
LAYER = ROOT / "data" / "nfl2k5_college_latest_school_2026.json"
IDENTITIES = ROOT / "fr" / "identities.csv"


def plan(document, source_rows: dict, identities: list[dict]) -> list[dict]:
    table: dict[str, list[int]] = collections.defaultdict(list)
    for index, label in enumerate(document.colleges):
        if label:
            table[school(label)].append(index)
    use = collections.Counter(p.college_index for p in document.players)
    players = {p.index: p for p in document.players if p.pool == "primary"}
    rows = []
    for identity in identities:
        player = players.get(int(identity["index"]))
        row = source_rows.get(identity["gsis"])
        if player is None or row is None or player.last.split()[0] != identity["name"].split()[-1].split()[0] \
                and player.last != identity["name"].split()[-1]:
            continue
        schools = [c.strip() for c in (row.get("college") or "").split(";") if c.strip()]
        found = next((c for c in schools if school(c) in table), None)
        if not schools or found is None or school(found) == school(player.college):
            continue
        # a school the table spells twice: the spelling more of the league already uses
        slot = max(table[school(found)], key=lambda i: (use[i], -i))
        rows.append({"pool": "primary", "index": player.index, "first": player.first, "last": player.last,
                     "was": player.college, "college": document.colleges[slot], "source": row["college"]})
    return rows


def merge(league: dict, layer: dict) -> tuple[dict, dict]:
    rr.read_edits(league)
    if layer.get("schema") != SCHEMA:
        raise ValueError("foreign college layer")
    out = copy.deepcopy(league)
    updates = {(u["pool"], u["index"]): u for u in out.get("college_updates", [])}
    added = replaced = 0
    for row in layer["updates"]:
        key = (row["pool"], row["index"])
        if key in updates:
            if (updates[key]["first"], updates[key]["last"]) != (row["first"], row["last"]):
                raise ValueError(f"{key}: the league update names {updates[key]['first']} {updates[key]['last']}")
            replaced += 1
        else:
            added += 1
        updates[key] = {"college": row["college"], "first": row["first"], "index": row["index"],
                        "last": row["last"], "pool": row["pool"]}
    out["college_updates"] = sorted(updates.values(), key=lambda u: (u["pool"] != "primary", u["index"]))
    out["college_latest_school"] = {"source": "data/nfl2k5_college_latest_school_2026.json (b778 rd1)",
                                    "players": len(layer["updates"])}
    return out, {"added": added, "replaced": replaced}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("plan")
    a.add_argument("disc", type=Path)
    a.add_argument("roster", type=Path)
    a.add_argument("--out", type=Path, default=LAYER)
    b = sub.add_parser("merge")
    b.add_argument("league", type=Path)
    b.add_argument("out", type=Path)
    b.add_argument("--layer", type=Path, default=LAYER)
    args = parser.parse_args(argv)
    if args.mode == "plan":
        source = {r["gsis_id"]: r for r in csv.DictReader(args.roster.open(encoding="utf-8"))}
        identities = list(csv.DictReader(IDENTITIES.open(encoding="utf-8")))
        rows = plan(rr.load_image(args.disc), source, identities)
        document = {"schema": SCHEMA,
                    "source": "nflverse-data rosters/roster_2026.csv (CC-BY-4.0), school list latest first; the v0.6.1 college table",
                    "updates": rows}
        text = "{" + ",\n".join(f'"{k}": {json.dumps(v, ensure_ascii=False)}' for k, v in document.items() if k != "updates")
        text += ',\n"updates": [\n' + ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n]}\n"
        json.loads(text)
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"{len(rows)} updates -> {args.out}")
        return 0
    if args.out.resolve() in (args.league.resolve(), args.layer.resolve()):
        raise SystemExit("the output must be a new file")
    merged, receipt = merge(json.loads(args.league.read_text(encoding="utf-8")),
                            json.loads(args.layer.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(merged, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
