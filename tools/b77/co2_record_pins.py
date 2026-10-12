#!/usr/bin/env python3
"""co2: write data/nfl2k5_modern_coaches/pins.json from a retail USA image and the shipped coach art (read only).

b77 co2 moved the 2026 head coaches onto the retail bodies that fit them (BODIES below; the coach record's +0x18 names
the model the game loads, ``c%02d.iff``) and put Kansas City's Andy Reid on the retail 2004 Reid model (c21) with his
own 2004 face, derived at build time (HEAD_RECIPES). The digests the previous pins applied are carried forward as
``superseded_sha256`` so a disc built with them is recognised (and rebuilt only from the user's retail image).
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "b77"))
from mod_editor.core import nfl2k5_modern_coaches as mc
import co1_coach_art as art

PORTRAITS = (("DAL", 7031, 7007, "Brian Schottenheimer"), ("WAS", 7034, 7029, "Dan Quinn"))
# club -> (retail body it now wears, why). Bodies measured from the meshes (tools/b77/co2_measure_coaches.py):
# heavy c21 c26 (belly depth 50-51), heavy-ish c00 c04 c16 (45-46), lean c01 c03 c05 c12 c18 c20 c24 c29 (35-39),
# every other model average (43.9). Builds from one full-length sideline photo per coach (co2 REPORT.md).
BODIES = {
    "ARI": ("12", "lean Mike LaFleur: lean body (c12) instead of the heavy-ish c00"),
    "ATL": ("01", "lean-average Stefanski: his club's lean body"),
    "BAL": ("02", "average Minter: his club's average body"),
    "BUF": ("03", "lean Brady: his club's lean body"),
    "CAR": ("09", "average Canales: average body (c09) instead of the heavy-ish c04"),
    "CHI": ("37", "lean-average Ben Johnson: average body with a light-skinned head (c37); c05 goes to Ryans"),
    "CIN": ("06", "lean-average Taylor: his club's average body"),
    "CLE": ("00", "solid, average-build Monken: the broad heavy-ish c00 (the one body left once the four big men and the lean coaches are placed)"),
    "DAL": ("07", "average Schottenheimer: his club's average body"),
    "DEN": ("08", "average Payton: his club's average body"),
    "DET": ("04", "big, broad Campbell: heavy-ish body (c04)"),
    "GB": ("10", "average Matt LaFleur: his club's average body"),
    "HOU": ("05", "athletic Ryans: lean body with a dark-skinned head (c05)"),
    "IND": ("11", "lean Steichen: his club's average body"),
    "JAX": ("30", "average-build Coen: average body (c30); his club's lean c12 goes to Mike LaFleur"),
    "KC": ("21", "Andy Reid: the retail 2004 Reid model (Philadelphia's c21), the heaviest body"),
    "LAC": ("24", "lean, athletic Jim Harbaugh: his club's lean body, glasses kept"),
    "LAR": ("23", "lean McVay: his club's average body"),
    "LV": ("20", "lean Kubiak: his club's lean body"),
    "MIA": ("14", "lean Hafley: his club's average body"),
    "MIN": ("15", "tall, lean O'Connell: his club's average body"),
    "NE": ("16", "stocky Vrabel: his club's heavy-ish body"),
    "NO": ("17", "lean Kellen Moore: his club's average body"),
    "NYG": ("22", "average John Harbaugh: average capped body (c22) instead of the lean c18"),
    "NYJ": ("19", "lean Glenn: his club's average body with a dark-skinned head"),
    "PHI": ("18", "lean Sirianni: lean capped body (c18) instead of the heaviest c21"),
    "PIT": ("26", "heavy McCarthy: heavy body (c26, glasses hidden) instead of the average c22"),
    "SEA": ("13", "average-build Macdonald: average body (c13, glasses hidden) instead of the heavy c26"),
    "SF": ("25", "lean Shanahan: his club's average body"),
    "TB": ("27", "big Bowles: his club's average capped body"),
    "TEN": ("28", "average, muscular Saleh: his club's average body"),
    "WAS": ("29", "lean, athletic Quinn: his club's lean body (glasses hidden)"),
}
# bodies whose glasses geometry stays visible: only Jim Harbaugh (LAC, c24) wears glasses among the occupants of the
# six glasses models (c10, c13, c23, c24, c26, c29); Reid's are painted on c21's face
GLASSES_MODELS = ("10", "13", "23", "24", "26", "29")
KEEP_GLASSES = ("LAC",)
# Reid 2026 on the 2004 Reid face: hair (class 1) white-grey, brows (2) grey, moustache (3) white with a warm cast;
# target = base + (luma - ref) * gain16 // 16 + tint, weighted by head_mask.png; glasses from head_overlay.png
HEAD_RECIPES = {"KC": {"kind": "retail_recolour", "classes": {"1": [170, 80, 14, [0, 0, 3]], "2": [122, 110, 12, [6, 2, -2]],
                                                              "3": [158, 84, 16, [22, 12, 0]]}}}


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
    superseded: dict[str, list[str]] = {}
    if mc.PINS_PATH.is_file():
        old = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
        for row in old["teams"]:
            superseded.setdefault(row["archive"], []).extend([row["applied_sha256"]] + row.get("superseded_sha256", []))
    teams = {}
    for team, code in art.CODES.items():
        body = BODIES[team][0]
        teams[team] = dict(team_code=code, body_code=body,
                           hide_glasses=body in GLASSES_MODELS and team not in KEEP_GLASSES,
                           head_recipe=HEAD_RECIPES.get(team))
    doc = mc.record_pins(a.retail, teams, portraits, superseded)
    doc["apparel"] = {team: dict(zip(("top", "trim", "cap", "why"), art.APPAREL[team])) for team in art.CODES}
    doc["bodies"] = {team: dict(body=f"c{b}.iff", why=why) for team, (b, why) in BODIES.items()}
    text = json.dumps(doc, indent=1) + "\n"
    if a.write:
        mc.PINS_PATH.write_text(text, encoding="utf-8", newline="\n")
    for row in doc["teams"]:
        print(row["team"], row["archive"], row["palette_max"], row["retail_sha256"][:12], "->", row["applied_sha256"][:12],
              "glasses hidden" if row["hide_glasses"] else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
