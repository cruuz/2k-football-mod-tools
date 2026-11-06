#!/usr/bin/env python3
"""c3-looks (b780): add the moved-coach pins to data/nfl2k5_modern_coaches/pins.json without changing anything else.

Per club row, from the user's retail USA image (read only):

* ``scene_sha256``: the SHA-256 of the coach's compiled scene (``compose_scene``: his head, headset, glasses and
  geometry on his model) with the shirt, jacket and chest logo allocations zeroed: his own look at any club;
* ``apparel_sha256``: {palette size: SHA-256 of those three allocations} of the club's own shirt, jacket and chest logo
  art at every palette size of the ladder: the club's colours on any coach.

With them the module dresses a coach the Studio moves to another club in that club's apparel and recognises the look
on a disc by its content. ``bodies[club]["coach"]`` gains the 2026 head coach's name (``data/vip/coach_sources_2026.json``)
for plain messages. ``--check-applied`` also recompiles each row and requires its pinned applied digest (slow: one
compression per club). ``mc.record_pins`` writes the same fields, so the other re-pin tools keep them current.

  python3 tools/b77/c3_record_pins.py --retail RETAIL.iso [--teams KC,LV] [--check-applied] [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402

COACH_SOURCES = ROOT / "data" / "vip" / "coach_sources_2026.json"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--retail", required=True)
    p.add_argument("--teams", help="comma-separated clubs (2026 abbreviations); default every club")
    p.add_argument("--check-applied", action="store_true")
    p.add_argument("--write", action="store_true")
    a = p.parse_args(argv)
    doc = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
    teams = set(a.teams.split(",")) if a.teams else {r["team"] for r in doc["teams"]}
    names = {e["team"]: e["coach"] for e in json.loads(COACH_SOURCES.read_text(encoding="utf-8"))}
    for team, entry in doc["bodies"].items():
        entry["coach"] = names[team]
    with mc._outer_image()(a.retail) as archive:
        entries = {e.name_id: e for e in archive.entries}
        for row in doc["teams"]:
            if row["team"] not in teams:
                continue
            entry = entries[mc.name_id(row["archive"])]
            raw = archive.read(entry.virtual_offset, entry.size)
            span = raw[row["span_offset"]:row["span_offset"] + row["span_size"]]
            if mc.sha(span) != row["retail_sha256"]:
                raise SystemExit(f"{row['archive']} is not retail on {a.retail}")
            row.update(mc.look_pins(raw, row))
            note = ""
            if a.check_applied:
                compiled, _detail = mc.compile_archive(raw, row)
                same = mc.sha(compiled[row["span_offset"]:row["span_offset"] + row["span_size"]]) == row["applied_sha256"]
                if not same:
                    raise SystemExit(f"{row['team']}: the compile no longer reproduces its applied pin")
                note = " applied ok"
            print(row["team"], row["archive"], names[row["team"]], "scene", row["scene_sha256"][:12],
                  "apparel", " ".join(f"{k}:{v[:8]}" for k, v in row["apparel_sha256"].items()) + note, flush=True)
    mc._check_pins(doc)
    if a.write:
        mc.PINS_PATH.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
