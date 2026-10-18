#!/usr/bin/env python3
"""b775 / hs1: merge the 2026 hair style assignments into a league roster-edits document (collects no data).

    python3 tools/b77/hs1_roster_hair.py LEAGUE_EDITS.json OUT.json [--hair data/nfl2k5_hair_styles_2026_roster_edits.json]

Each hair edit sets only ``hair_style`` (record +0x0D bits 0-3). An existing edit of the same (pool, index) gains the
field (its last name must agree); a player the league document does not edit gets a new entry. Nothing else in the
league document changes. The output is refused if it would change any other field.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

HAIR = ROOT / "data" / "nfl2k5_hair_styles_2026_roster_edits.json"


def merge(league: dict, hair: dict) -> tuple[dict, dict]:
    rr.read_edits(league)
    rr.read_edits(hair)
    out = copy.deepcopy(league)
    index = {(str(e.get("pool", "primary")), int(e["index"])): e for e in out["edits"]}
    # a dated roster refresh creates new players in vacant pool slots AFTER the edits (from a zero record), so their
    # hair style has to travel in the refresh row itself
    created = {int(r["index"]): r for r in (out.get("roster_refresh") or {}).get("players", []) if r.get("new")}
    added = updated = refreshed = 0
    for edit in hair["edits"]:
        key = (edit["pool"], int(edit["index"]))
        style = int(edit["fields"]["hair_style"])
        if not 0 <= style <= 15:
            raise ValueError(f"{key}: hair style {style} out of range")
        row = created.get(key[1]) if key[0] == "primary" else None
        if row is not None:
            if row["last"].split()[0] != edit["last"].split()[0]:
                raise ValueError(f"{key}: the refresh creates {row['last']}, the hair edit names {edit['last']}")
            row["fields"]["hair_style"] = style
            refreshed += 1
            continue
        current = index.get(key)
        if current is None:
            out["edits"].append({"pool": edit["pool"], "index": edit["index"], "first": edit["first"],
                                 "last": edit["last"], "fields": {"hair_style": style}})
            added += 1
            continue
        named = (current.get("names") or {}).get("last") or current.get("last")
        if named and set(named) != {"*"} and named != edit["last"]:   # "****" = a slot the roster refresh fills
            raise ValueError(f"{key}: the league edit names {named}, the hair edit {edit['last']}")
        current.setdefault("fields", {})["hair_style"] = style
        updated += 1
    out["hair_styles"] = {"source": "data/nfl2k5_hair_styles_2026_roster_edits.json (b775 hs1)",
                          "players": len(hair["edits"])}
    return out, {"updated": updated, "added": added, "refresh_rows": refreshed}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("league", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--hair", type=Path, default=HAIR)
    a = p.parse_args(argv)
    if a.out.resolve() in (a.league.resolve(), a.hair.resolve()):
        raise SystemExit("the output must be a new file")
    league = json.loads(a.league.read_text(encoding="utf-8"))
    merged, receipt = merge(league, json.loads(a.hair.read_text(encoding="utf-8")))
    a.out.write_text(json.dumps(merged, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
