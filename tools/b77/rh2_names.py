#!/usr/bin/env python3
"""b778-rh2: put the rare-group names into the shipped prospect pool.

Noah (2026-10-22): rare East Asian prospects ("every now and then") and very rare South Asian ones ("maybe one or two
appear every few years"), each with a fitting first name and surname.

* Surnames: three adjacent replacement rows (announced by number, so no recorded call-out is lost) take the three
  most common US surnames with the highest Asian share (US Census Bureau, 2010 surname file, Names_2010Census.csv:
  NGUYEN rank 38, 96.45 % Asian/Pacific Islander; CHEN rank 150, 96.12 %; PATEL rank 95, 94.78 %; KIM, rank 77,
  is already a retail surname with a recorded call-out at row 222 and stays an ordinary surname).  The generator draws
  each surname 1 time in 485, so a class of 224 prospects carries about 0.92 East Asian and 0.46 South Asian
  prospects.  The surnames they replace (rows 347..349) are three of the 52 modern surnames rd1 added (no audio).
* First names: four per surname at the pool tail (rows 473..484), in place of the last twelve nickname first names
  rh1 added: names with a high Asian share that the pool does not already hold (first names stay unique), from
  Rosenman, Olivella & Imai, Harvard Dataverse doi:10.7910/DVN/SGKW0K (CC0), P(name | Asian) and P(Asian | name)
  printed by this tool.  The native code never keeps these from an ordinary draw (they are redrawn), and a rare
  surname always takes one of its own four.

usage: rh2_names.py --first FIRST.tab --census Names_2010Census.csv [--apply]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_prospect_names as pn  # noqa: E402
from mod_editor.core import nfl2k5_rookie_faces as rf  # noqa: E402

RARE_ROW = 347            # rows 347..349 (Hairston, Heath, Herron): adjacent replacement surnames
PRIOR = dict(whi=0.60, bla=0.13, his=0.18, asi=0.06, oth=0.03)   # US male population shares, for P(Asian | name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", required=True, type=Path)
    ap.add_argument("--census", required=True, type=Path)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    text = pn.SHIPPED_CSV.read_text(encoding="utf-8")
    rows = pn.read_csv(text)
    names = rf.load_names()
    tail = rf.POOL_COUNT - len(rf.RARE_FIRSTS)
    for k in range(len(rf.RARE_SURNAMES)):
        assert not rows[RARE_ROW + k].retained, "rare surnames go on replacement rows only"
    stats = {}
    with open(a.first, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        for row in reader:
            n = row[0].strip('"')
            if n in {x.upper() for x in rf.RARE_FIRSTS}:
                v = dict(zip(header[1:], map(float, row[1:])))
                post = {k: v[k] * PRIOR[k] for k in PRIOR}
                stats[n] = dict(p_name_given_asian=round(v["asi"], 6), p_asian_given_name=round(post["asi"] / sum(post.values()), 3))
    census = {}
    with open(a.census, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["name"] in {x.upper() for x in rf.RARE_SURNAMES}:
                census[row["name"]] = dict(rank=int(row["rank"]), count=int(row["count"]), pct_api=float(row["pctapi"]))
    new = []
    for r in rows:
        first, last = r.first, r.last
        if RARE_ROW <= r.index < RARE_ROW + len(rf.RARE_SURNAMES):
            last = rf.RARE_SURNAMES[r.index - RARE_ROW]
        if r.index >= tail:
            first = rf.RARE_FIRSTS[r.index - tail]
        new.append(pn.NameRow(index=r.index, first=first, last=last))
    layout = pn.plan_layout(new)
    nick = [n for n in names["nicknames"]][: tail - 445]
    head = [line for line in text.splitlines() if line.startswith("#") and not line.startswith("# Pool bytes")]
    head.append("# b778-rh2 (tools/b77/rh2_names.py): surnames 347..349 = Nguyen, Chen, Patel (rare East / South Asian "
                "prospects, US Census 2010 surname shares); first names 473..484 = four fitting first names per rare "
                "surname (Rosenman et al., CC0), only ever given with that surname; nicknames 445..472.")
    head.append(f"# Pool bytes: {layout.bytes_used} of {pn.BUDGET} (UTF-16LE with terminators); boundary body offset "
                f"0x{layout.boundary:x}.")
    out = io.StringIO(newline="")
    out.write("\n".join(head) + "\n")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["index", "first", "last", "audio"])
    for r in new:
        w.writerow([r.index, r.first, r.last, "retail" if r.retained else "number"])
    odds = dict(names)
    odds["nicknames"] = nick
    odds["first"] = {k: v for k, v in names["first"].items() if k in {r.first for r in new[:tail]}}
    odds["last"] = {r.last: names["last"].get(r.last, 0) for r in new}
    odds["rare"] = {
        "surnames": list(rf.RARE_SURNAMES), "groups": ["east", "east", "south"], "first_names": list(rf.RARE_FIRSTS),
        "surname_source": "US Census Bureau, Frequently Occurring Surnames from the 2010 Census (Names_2010Census.csv)",
        "first_source": "Rosenman, Olivella & Imai, Harvard Dataverse doi:10.7910/DVN/SGKW0K (CC0); P(Asian | name) "
                        "with US male shares white .60, Black .13, Hispanic .18, Asian .06, other .03",
        "census": census, "first_stats": stats,
    }
    print(f"pool bytes {layout.bytes_used}/{pn.BUDGET}, boundary 0x{layout.boundary:x} (was 0x{pn.SHIPPED_BOUNDARY:x})")
    print(json.dumps(odds["rare"], indent=1))
    if a.apply:
        pn.SHIPPED_CSV.write_text(out.getvalue(), encoding="utf-8", newline="\n")
        rf.NAMES_JSON.write_text(json.dumps(odds, indent=1, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
