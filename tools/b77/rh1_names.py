#!/usr/bin/env python3
"""b778-rh1: order the shipped prospect first names by how strongly they signal a Black player, add the rare
nickname first names, and write the name odds the rookie-faces tables are built from.

Inputs (not shipped): Rosenman, Olivella & Imai, "Race and ethnicity data for first, middle, and last names"
(Harvard Dataverse, doi:10.7910/DVN/SGKW0K, CC0): ``first_raceNameProbs.tab`` and ``last_raceNameProbs.tab``, the
probability of a name given each of five groups (whi, bla, his, asi, oth), from the voter files of six states.

For a name, ``ln LR = ln P(name | bla) - ln P(name | not Black)`` with "not Black" weighted like the NFL's other
players (white .85, other .11, Hispanic .03, Asian .01; TIDES 2023 shares), clipped to +-3.5 nats.

Outputs:
* ``data/nfl2k5_modern_names.csv``: 445 of the shipped modern first names (the 40 longest of the lower-ranked half
  make room for the nicknames in the pool's fixed byte budget),
  sorted by ln LR ascending, then 40 nickname first names (index 445..484); every surname stays at its index, so every
  recorded surname call-out is kept.  Only first names move (the generator draws first and last independently).
* ``data/nfl2k5_rookie_faces/name_odds.json``: ln LR x 16 per first name and surname of the pool, the nickname list,
  and the four surname code levels.

usage: rh1_names.py --first FIRST.tab --last LAST.tab [--apply]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_prospect_names as pn  # noqa: E402
from mod_editor.core import nfl2k5_rookie_faces as rf  # noqa: E402

NICKNAMES = ("Scooby", "Riff Raff", "Boogie", "Peanut", "Tank", "Bam Bam", "Juice", "Lil Man", "Big Cat", "Biscuit",
             "Choo Choo", "Moose", "Ziggy", "Hambone", "Smokey", "Tater", "Deuce", "Skeeter", "Bubba", "Trey Trey",
             "Turbo", "Cornbread", "Noodle", "Hollywood", "Pookie", "Meatball", "Spud", "Catfish", "Hoss", "Rooster",
             "Gravy", "Boom Boom", "Sugar Bear", "Pistol", "Dozer", "Snacks", "Pork Chop", "Hot Rod", "Bear", "Sweet Pea")
NOT_BLACK = dict(whi=0.85, oth=0.11, his=0.03, asi=0.01)
CAP = 3.5
FLOOR = 2e-7
SURNAME_CUTS = (-16, 10, 29)       # 1/16 nat: < -1.0 | -1.0..0.6 | 0.6..1.8 | >= 1.8


def key(name: str) -> str:
    return "".join(c for c in name.upper() if c.isalpha())


def load(path: Path, wanted: set[str]) -> dict[str, float]:
    out = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        for row in reader:
            name = row[0].strip('"')
            if name in wanted:
                v = dict(zip(header[1:], map(float, row[1:])))
                nb = sum(w * v[k] for k, w in NOT_BLACK.items())
                out[name] = max(-CAP, min(CAP, math.log((v["bla"] + FLOOR) / (nb + FLOOR))))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", required=True, type=Path)
    ap.add_argument("--last", required=True, type=Path)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    text = pn.SHIPPED_CSV.read_text(encoding="utf-8")
    rows = pn.read_csv(text)
    ranked = [r.first for r in rows]
    nick_keys = {key(n) for n in NICKNAMES}
    candidates = [n for n in ranked if key(n) not in nick_keys]
    # drop the 40 longest names from the lower-ranked half (ties: the lower rank goes first) so the nicknames fit
    lower = sorted(range(len(candidates) // 2, len(candidates)), key=lambda i: (-len(candidates[i]), -i))
    dropped = set(lower[:len(candidates) - (pn.POOL_COUNT - len(NICKNAMES))])
    modern = [n for i, n in enumerate(candidates) if i not in dropped]
    first_lr = load(args.first, {key(n) for n in modern})
    last_lr = load(args.last, {key(r.last) for r in rows})
    lr = {n: first_lr.get(key(n), 0.0) for n in modern}
    order = sorted(modern, key=lambda n: (lr[n], ranked.index(n)))
    firsts = order + list(NICKNAMES)
    new_rows = [pn.NameRow(index=r.index, first=firsts[r.index], last=r.last) for r in rows]
    layout = pn.plan_layout(new_rows)
    head = [line for line in text.splitlines() if line.startswith("#")]
    head = [line for line in head if not line.startswith("# Pool bytes") and "rh1" not in line]
    head.append("# b778-rh1 (tools/b77/rh1_names.py): first names 0..444 = 445 modern first names sorted by how "
                "strongly they signal a Black player (Rosenman et al. voter-file name data, CC0); 445..484 = rare "
                "nickname first names (kept one draw in eight). Surnames and call-outs unchanged.")
    head.append(f"# Pool bytes: {layout.bytes_used} of {pn.BUDGET} (UTF-16LE with terminators); boundary body offset "
                f"0x{layout.boundary:x}.")
    out = io.StringIO(newline="")
    out.write("\n".join(head) + "\n")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["index", "first", "last", "audio"])
    for r in new_rows:
        w.writerow([r.index, r.first, r.last, "retail" if r.retained else "number"])
    csv_text = out.getvalue()
    surname = {r.last: round(last_lr.get(key(r.last), 0.0) * rf.UNITS) for r in rows}
    levels = [[], [], [], []]
    for v in surname.values():
        levels[sum(v >= c for c in SURNAME_CUTS)].append(v)
    odds = {
        "schema": rf.SCHEMA_NAMES,
        "units": "1/16 nat: ln P(name | Black) - ln P(name | not Black), clipped to +-3.5 nats",
        "source": "Rosenman, Olivella & Imai, Race and ethnicity data for first, middle, and last names, Harvard "
                  "Dataverse doi:10.7910/DVN/SGKW0K (CC0); not-Black weighted white .85, other .11, Hispanic .03, "
                  "Asian .01 (TIDES 2023 NFL shares)",
        "first": {n: round(lr[n] * rf.UNITS) for n in order} | {n: 0 for n in NICKNAMES},
        "last": surname,
        "nicknames": list(NICKNAMES),
        "surname_code_cuts": list(SURNAME_CUTS),
        "surname_code_logits": [round(sum(l) / len(l)) if l else 0 for l in levels],
    }
    print(f"pool bytes {layout.bytes_used}/{pn.BUDGET}, boundary 0x{layout.boundary:x}, missing first "
          f"{sum(1 for n in modern if key(n) not in first_lr)}, missing last "
          f"{sum(1 for r in rows if key(r.last) not in last_lr)}, surname levels {[len(l) for l in levels]} "
          f"{odds['surname_code_logits']}")
    if args.apply:
        pn.SHIPPED_CSV.write_text(csv_text, encoding="utf-8", newline="\n")
        rf.NAMES_JSON.parent.mkdir(parents=True, exist_ok=True)
        rf.NAMES_JSON.write_text(json.dumps(odds, indent=1, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
