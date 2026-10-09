#!/usr/bin/env python3
"""Derive the f12 cohort: every v0.5 ROST record whose years pro was written in the nflverse convention.

Job f12 (beta 77).  The game's years pro counts the season in progress (rookie = 1); the 2026 league build wrote
nflverse ``years_exp`` (completed seasons, rookie = 0).  The cohort is the set of primary records the SOFTDRINK build
authored from 2026 data:

  * a record on one of the 32 NFL clubs or in the free-agent list, or any other NFL-flagged non-vacant record, and
  * whose identity (first name, last name, birth date) differs from the retail record at the same index.

Retail legends that sit on alumni squads (Larry Centers ...), the 140 vacant create-a-player records and the 380
draft-class records are not in it.  Every row is cross-checked against nflverse (name + birth date, then birth date +
club) and carries the evidence; rows nflverse cannot confirm are listed as ``unverified``.

  python3 tools/b77/f12_build_cohort.py --pack0 PACK0_V05 --retail-pack0 RETAIL_PACK0 --nflverse DIR --out cohort.json

Reads only; writes the one JSON.  The repair (f12_repair.py) embeds nothing else about the roster.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

SCHEMA = "nfl2k5_b77_f12_cohort/v1"
ROST_OUTER_INDEX = 5


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def norm(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text).casefold() if c.isalnum())


def rost_body(pack: bytes) -> bytes:
    count, reserved, populated = struct.unpack_from("<3I", pack)
    if not 6 <= count <= 100000 or reserved or not 1 <= populated <= 36:
        raise ValueError("unexpected outer archive header")
    _name, size, blocks = struct.unpack_from("<3I", pack, 0x9C + ROST_OUTER_INDEX * 12)
    offset = blocks * 0x800
    resource = pack[offset:offset + size]
    if resource[:4] != b"ROST":
        raise ValueError("outer entry 5 is not a ROST resource")
    return resource[rr.RESOURCE_HEADER_SIZE:]


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build(pack0: Path, retail_pack0: Path, nflverse: Path) -> dict:
    pack = pack0.read_bytes()
    body = rost_body(pack)
    doc = rr.RosterDocument(body, base=0, scheme="one_pool", reference_year=2026)
    retail = rr.RosterDocument(rost_body(retail_pack0.read_bytes()), base=0, scheme="retail", reference_year=2004)
    retail_by = {(p.pool, p.index): p for p in retail.players}
    free_agents = set(doc.free_agents)
    rows26 = load_rows(nflverse / "roster_2026.csv")
    rows25 = load_rows(nflverse / "roster_2025.csv")
    by_name = {2026: collections.defaultdict(list), 2025: collections.defaultdict(list)}
    by_dob = {2026: collections.defaultdict(list), 2025: collections.defaultdict(list)}
    for season, rows in ((2026, rows26), (2025, rows25)):
        for r in rows:
            by_name[season][(norm(r["first_name"] + r["last_name"]), r.get("birth_date") or "")].append(r)
            by_name[season][(norm(r["full_name"]), r.get("birth_date") or "")].append(r)
            by_dob[season][r.get("birth_date") or ""].append(r)
    older: dict[int, dict[str, list[dict]]] = {}
    for path in sorted(nflverse.glob("roster_20[0-2][0-9].csv")):
        season = int(path.stem[-4:])
        if season >= 2025:
            continue
        table = collections.defaultdict(list)
        for r in load_rows(path):
            table[r.get("birth_date") or ""].append(r)
        older[season] = table
    cohort, basis_counts, club_count, fa_count = [], collections.Counter(), 0, 0
    for p in sorted(doc.players, key=lambda q: (q.pool, q.index)):
        if p.pool != "primary" or p.group == "draft_class":
            continue
        values = p.record.values
        if p.first.startswith("****") or not values["player_type"] & rr.FLAG_NFL_PLAYER:
            continue
        old = retail_by.get((p.pool, p.index))
        if old is not None and (old.first, old.last, old.record.birth_date) == (p.first, p.last, p.record.birth_date):
            continue
        birth = p.record.birth_date.isoformat() if p.record.birth_date else ""
        years_pro = values["years_pro"]
        clubs = [doc.teams[t].abbreviation for t in p.teams if t < 32]
        basis, years_exp = "unverified", None
        for season in (2026, 2025):
            hits = by_name[season].get((norm(p.first + p.last), birth))
            if hits:
                years_exp = int(float(hits[0]["years_exp"]))
                # a 2025 file counts one fewer completed season than the 2026 one
                expected = years_exp + (1 if season == 2025 else 0)
                basis = f"nflverse roster_{season}.csv name+birth" + ("" if expected == years_pro else " MISMATCH")
                years_exp = expected
                break
        if basis == "unverified":
            for season in (2026, 2025):
                hits = [r for r in by_dob[season].get(birth, ())
                        if norm(r["last_name"])[:4] == norm(p.last)[:4] or (clubs and r["team"] == clubs[0])]
                if hits:
                    expected = int(float(hits[0]["years_exp"])) + (1 if season == 2025 else 0)
                    basis = f"nflverse roster_{season}.csv birth+club/surname ({hits[0]['full_name']})" + (
                        "" if expected == years_pro else " MISMATCH")
                    years_exp = expected
                    break
        if basis == "unverified":
            # players nflverse no longer lists for 2025/2026 (unretired veterans, 2024 signings): entry_year in any
            # earlier annual roster gives completed seasons as 2026 - entry_year
            entries = sorted({int(float(r["entry_year"])) for rows in older.values() for r in rows.get(birth, ())
                              if r.get("entry_year") and norm(r["last_name"])[:4] == norm(p.last)[:4]})
            if entries:
                expected = 2026 - entries[0]
                basis = f"nflverse older roster entry_year {entries[0]}" + ("" if expected == years_pro else " MISMATCH")
                years_exp = expected
        basis_counts[basis.split(" (")[0].split(" entry_year")[0].strip()] += 1
        code = ("26n" if basis.startswith("nflverse roster_2026.csv name") else "25n" if basis.startswith("nflverse roster_2025.csv name")
                else "26f" if basis.startswith("nflverse roster_2026.csv birth") else "25f" if basis.startswith("nflverse roster_2025.csv birth")
                else "old" if basis.startswith("nflverse older") else "??")
        require(code != "??" and "MISMATCH" not in basis, f"{p.first} {p.last} ({p.index}): {basis}")
        cohort.append([p.index, p.first, p.last, birth, years_pro, code])
        club_count += 1 if clubs else 0
        fa_count += 1 if p.group == "free_agent" else 0
    return {"schema": SCHEMA,
            "rule": "primary NFL-flagged non-vacant non-draft-class records whose identity differs from the retail record "
                    "at the same index; years pro was written as nflverse years_exp (rookie 0); the game stores rookie = 1",
            "pack0_sha256": sha(pack), "rost_body_sha256": sha(body), "rost_body_size": len(body),
            "retail_pack0_sha256": sha(retail_pack0.read_bytes()),
            "nflverse_roster_sha256": {"roster_2026.csv": sha((nflverse / "roster_2026.csv").read_bytes()),
                                       "roster_2025.csv": sha((nflverse / "roster_2025.csv").read_bytes())},
            "counts": {"records": len(cohort), "basis": dict(sorted(basis_counts.items())),
                       "club": club_count, "free_agent": fa_count},
            "basis_codes": BASIS_CODES,
            "columns": ["index", "first", "last", "birth_date", "old_years_pro", "basis"],
            "records": cohort}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


BASIS_CODES = {"26n": "nflverse roster_2026.csv, name and birth date; years_pro == years_exp",
               "25n": "nflverse roster_2025.csv, name and birth date; years_pro == years_exp(2025) + 1",
               "26f": "nflverse roster_2026.csv, birth date and club or surname (Jr./II name variant); years_pro == years_exp",
               "25f": "nflverse roster_2025.csv, birth date and surname; years_pro == years_exp(2025) + 1",
               "old": "an earlier nflverse annual roster's entry_year; years_pro == 2026 - entry_year"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pack0", type=Path, required=True)
    ap.add_argument("--retail-pack0", type=Path, required=True)
    ap.add_argument("--nflverse", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        ap.error("output exists; choose a fresh path")
    result = build(args.pack0, args.retail_pack0, args.nflverse)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    head = {k: v for k, v in result.items() if k != "records"}
    lines = ",\n".join("  " + json.dumps(r, separators=(",", ":"), ensure_ascii=True) for r in result["records"])
    text = json.dumps(head, indent=1)[:-2] + ',\n "records": [\n' + lines + "\n ]\n}\n"
    json.loads(text)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(result["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
