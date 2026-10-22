#!/usr/bin/env python3
"""cf1 (b778): re-pin only the named clubs in data/nfl2k5_modern_coaches/pins.json after their head.png or
geometry.json changed (``cf1_face_scan.py``), leaving every other row, the portraits, bodies and retired models as they
are. Each re-pinned row carries its previous applied digest forward in ``superseded_sha256`` (a disc built with the
earlier face is recognised and rebuilt from the user's retail image), and its palette size is chosen again from the
ladder.

Rows of other clubs are untouched, so jobs that scan different clubs on their own branches change disjoint rows of
the file (the coordinator still re-runs this for every club after merging to prove the whole document).

  python3 tools/b77/cf1_record_pins.py --retail RETAIL.iso --teams JAX,TB [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--retail", required=True)
    p.add_argument("--teams", required=True, help="comma-separated clubs (2026 abbreviations)")
    p.add_argument("--write", action="store_true")
    a = p.parse_args(argv)
    doc = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
    rows = {r["team"]: r for r in doc["teams"]}
    teams = [t for t in a.teams.split(",") if t]
    spec, superseded = {}, {}
    for team in teams:
        row = rows[team]
        spec[team] = dict(team_code=row["team_code"], body_code=row["body_code"], hide_glasses=row["hide_glasses"],
                          head_recipe=row.get("head_recipe"))
        superseded[row["archive"]] = [row["applied_sha256"]] + list(row.get("superseded_sha256", ()))
    check = mc._check_pins
    mc._check_pins = lambda document: document           # a partial document; the whole one is checked below
    try:
        fresh = mc.record_pins(a.retail, spec, [], superseded)
    finally:
        mc._check_pins = check
    for new in fresh["teams"]:
        old = rows[new["team"]]
        for key in ("superseded_body_codes",):          # fields record_pins does not write (cm2)
            if key in old:
                new[key] = old[key]
        changed = old["applied_sha256"] != new["applied_sha256"]
        print(new["team"], new["archive"], "palette", new["palette_max"], "applied", new["applied_sha256"][:12],
              "(changed)" if changed else "(same)", "superseded", len(new["superseded_sha256"]),
              "geometry", (new.get("geometry") or "")[:12])
        rows[new["team"]] = new
    doc["teams"] = [rows[r["team"]] for r in doc["teams"]]
    mc._check_pins(doc)
    if a.write:
        mc.PINS_PATH.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
