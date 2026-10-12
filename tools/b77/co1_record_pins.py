#!/usr/bin/env python3
"""co1: write data/nfl2k5_modern_coaches/pins.json from a retail USA image and the shipped coach art (read only)."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "b77"))
from mod_editor.core import nfl2k5_modern_coaches as mc
import co1_coach_art as art

# Dallas and Washington have no coach portrait on the 2004 disc (7007, 7029 resolve to nophoto); two retail portrait
# slots that no main or historic roster record and no v0.6 league portrait uses (co1 scan of the v0.6.1 disc).
# 2004 models with glasses on the body whose 2026 coach wears none (LaFleur, McVay, Macdonald, Quinn); KC and LAC keep
HIDE_GLASSES = ("GB", "LAR", "SEA", "WAS")
PORTRAITS = (("DAL", 7031, 7007, "Brian Schottenheimer"), ("WAS", 7034, 7029, "Dan Quinn"))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--retail", required=True)
    p.add_argument("--write", action="store_true")
    a = p.parse_args(argv)
    report = json.loads((ROOT / "reports/assets/nfl2k5_player_portrait_compatibility.json").read_text(encoding="utf-8"))
    targets = {int(t["portrait_id"]): t for t in report["targets"]}
    portraits = []
    for team, pid, retail_id, coach in PORTRAITS:
        t = targets[pid]
        portraits.append(dict(team=team, coach=coach, portrait_id=str(pid), retail_photo_id=retail_id,
                              outer_index=t["outer_index"], chunk_offset=t["chunk_offset"], span_size=t["span_size"],
                              retail_sha256=t["span_sha256"], png=f"portraits/{pid}.png"))
    doc = mc.record_pins(a.retail, dict(art.CODES), portraits, HIDE_GLASSES)
    doc["apparel"] = {team: dict(zip(("top", "trim", "cap", "why"), art.APPAREL[team])) for team in art.CODES}
    text = json.dumps(doc, indent=1) + "\n"
    if a.write:
        mc.PINS_PATH.write_text(text, encoding="utf-8", newline="\n")
    for row in doc["teams"]:
        print(row["team"], row["archive"], row["retail_sha256"][:12], "->", row["applied_sha256"][:12])
    for row in doc["portraits"]:
        print(row["team"], row["portrait_id"], row["retail_sha256"][:12], "->", row["applied_sha256"][:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
