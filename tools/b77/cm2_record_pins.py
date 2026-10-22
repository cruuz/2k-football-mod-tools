#!/usr/bin/env python3
"""cm2 (b778): rewrite data/nfl2k5_modern_coaches/pins.json for the coach moves of ``cm2_coach_models.py``.

Runs co2's recorder (``co2_record_pins.py``, the one ``cm1_record_pins.py`` runs; it also pins each club's
geometry.json) with the cm2 bodies, then adds:

* ``bodies[club]["skin"]``: the 2026 coach's skin, which the module checks against the model he wears
  (``DARK_SKIN_MODELS``): a coach is never dressed on a model of another skin again;
* ``superseded_body_codes`` per club: the coach model an earlier version of this option wrote into the club's coach
  record (+0x18), so a disc built with it is rewritten to the new model (``previous``) instead of being left alone;
* ``retired``: the models no club wears any more (c06, c11), with the digests of the art earlier versions left there,
  so a disc built with them gets the retail bytes back.

  python3 tools/b77/cm2_record_pins.py --retail RETAIL.iso [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "b77"))
from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402
import co2_record_pins  # noqa: E402

# the cm2 bodies (cm2_coach_models.MOVES) and why
BODIES = {
    "TB": ("00", "Todd Bowles, a Black coach: the 2004 Dennis Green model (c00), a Black coach's head, arms and hands "
                 "and a broad build, in place of the 2004 Jon Gruden model (c27) with a darkened face (b778 cm2)"),
    "PIT": ("27", "Mike McCarthy in a cap (Noah 10/21): the capped c27, his heavy build carried over from c26 by "
                  "position (b778 cm2)"),
    "CLE": ("26", "Todd Monken, a white coach: c26 (glasses hidden) with c13's average body, in place of the Black "
                  "Dennis Green model c00 (b778 cm2)"),
    "CIN": ("36", "Zac Taylor, a white coach: c36 (a model no coach record uses) with c20's lean body, in place of "
                  "the Black Marvin Lewis model c06 (b778 cm2)"),
    "IND": ("33", "Shane Steichen, a white coach: c33 (a model no coach record uses) with c20's lean body, in place "
                  "of the Black Tony Dungy model c11 (b778 cm2)"),
}
# the 2026 head coaches' skin (dark: Todd Bowles, DeMeco Ryans, Aaron Glenn)
DARK = ("TB", "HOU", "NYJ")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--retail", required=True)
    p.add_argument("--write", action="store_true")
    a = p.parse_args(argv)
    before = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
    old_rows = {r["team"]: r for r in before["teams"]}
    co2_record_pins.BODIES.update(BODIES)
    co2_record_pins.main(["--retail", a.retail, "--write"])
    doc = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
    for team, entry in doc["bodies"].items():
        entry["skin"] = "dark" if team in DARK else "light"
    for row in doc["teams"]:
        old = old_rows[row["team"]]
        codes = [c for c in [old["body_code"]] + old.get("superseded_body_codes", [])
                 if c not in (row["body_code"], row["team_code"])]
        if codes:
            row["superseded_body_codes"] = sorted(set(codes))
    worn = {r["archive"] for r in doc["teams"]}
    retired = {r["archive"]: r for r in before.get("retired", []) if r["archive"] not in worn}
    for old in before["teams"]:
        if old["archive"] in worn:
            continue
        row = retired.setdefault(old["archive"], dict(archive=old["archive"], span_offset=old["span_offset"],
                                                      span_size=old["span_size"], retail_sha256=old["retail_sha256"],
                                                      superseded_sha256=[]))
        row["superseded_sha256"] = sorted(set(row["superseded_sha256"]) | {old["applied_sha256"]}
                                          | set(old.get("superseded_sha256", ())))
    doc["retired"] = [retired[k] for k in sorted(retired)]
    mc._check_pins(doc)
    text = json.dumps(doc, indent=1) + "\n"
    mc.PINS_PATH.write_text(text if a.write else json.dumps(before, indent=1) + "\n", encoding="utf-8", newline="\n")
    for row in doc["teams"]:
        if row["team"] in BODIES:
            print(row["team"], row["archive"], "palette", row["palette_max"], "applied", row["applied_sha256"][:12],
                  "earlier bodies", row.get("superseded_body_codes"), "superseded", len(row["superseded_sha256"]))
    for row in doc["retired"]:
        print("retired", row["archive"], "earlier art", len(row["superseded_sha256"]))
    print("skin mismatches", mc.skin_mismatches(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
