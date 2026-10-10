#!/usr/bin/env python3
"""Job f12 (beta 77): years pro in the 50 ESPN 25th Anniversary team-season files of SOFTDRINK v0.5 (packs E and F).

Each of the 50 extra team-seasons ("h-<code>-<season>-<name>-<n>.iff": Patriots 2007, Bengals 2025, ...) is a one-team ROST
resource of 53 player records, compiled from ``data/nfl2k5_espn25_more_teams/*.csv`` while that data still carried nflverse
``years_exp`` (rookie 0), and for six team-seasons (Vikings 1998, Falcons 1998, Titans 1999, Bills 1999, Patriots 2001,
Raiders 2001) mostly a missing-data 0, because nflverse's 1998 to 2001 roster files have no ``years_exp``.  The game's years
pro counts the season in progress (rookie 1, printed R).  This writer sets byte +0x25 bits 0-4 of each of the 2,650 records
to the pinned corrected value (the old value plus 1, or for the six sparse team-seasons the entry-year value of the fixed
generator) and changes nothing else.  The team files carry no career-stat history.  Forty-eight files live in pack E
(outer entries 4348..), the two Unc Bowl teams in pack F (4527, 4528).

The files are found by content: a resource is a team-season when its 53 (first, last, years pro) triples are exactly one
pinned team's (first, last, old) triples (``f12_anniversary_cohort.json``), or exactly its (first, last, new) triples (an
idempotent replay).  Anything else refuses.  The outer directory comes from pack 0 (read only); only packs E and F are written.

  python3 tools/b77/f12_anniversary_repair.py --pack0 P0 --pack-e E --pack-f F --output-e OUT_E --output-f OUT_F --receipt R.json
  python3 tools/b77/f12_anniversary_repair.py --build-pins --pack0 P0 --pack-e E --pack-f F --old-teams-dir OLD_CSVS --out PINS.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from nfl_outer import ALIGNMENT, HEADER_SIZE, PACK_SLOT_COUNT  # noqa: E402

TOOL = "tools/b77/f12_anniversary_repair.py"
SCHEMA = "nfl2k5_b77_f12_anniversary_repair/v1"
PINS_SCHEMA = "nfl2k5_b77_f12_anniversary_cohort/v1"
PINS_PATH = Path(__file__).with_name("f12_anniversary_cohort.json")
TEAMS_DIR = ROOT / "data/nfl2k5_espn25_more_teams"
V05_PACK_SHA256 = {14: "88bb34f38971cd43636e1036c9bb4b21fee91979bbbebf4dac036f3887da559b",
                   15: "e295e5f186289ce8ce8ccdab7816cc4ed8944f1379d13871add76fe7b343ed43"}
# filled from the deterministic output (see the receipt)
F12_PACK_SHA256 = {14: "22b0b8c4364223aaf1d8b78603ec8980cc494563926cc958b3df551b27c3ed66",
                   15: "f17a06080711e59179e0f3f78b6c63db3d9ed49baae3bf4a5afc788ec46119c1"}
PACK_NAMES = {14: "E", 15: "F"}
RESOURCE_HEADER_SIZE = 0x20
YEARS_PRO_BYTE = 0x25
YEARS_PRO_MASK = 0x1F
TEAM_SIZE_LIMIT = 40000
ROSTER_SIZE = 53


class RepairRefused(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RepairRefused(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_directory(pack0_head: bytes) -> tuple[list[tuple[int, int, int, int]], list[tuple[int, int]]]:
    """(entries, packs): entries are (index, name_id, virtual_offset, size); packs are (virtual_start, size) by ordinal."""
    require(len(pack0_head) >= HEADER_SIZE, "truncated outer archive header")
    count, reserved, populated = struct.unpack_from("<3I", pack0_head)
    require(6 <= count <= 100000 and not reserved and 1 <= populated <= PACK_SLOT_COUNT, "unexpected outer archive header")
    require(len(pack0_head) >= HEADER_SIZE + 12 * count, "the pack 0 bytes do not cover the outer directory")
    blocks = struct.unpack_from(f"<{PACK_SLOT_COUNT}I", pack0_head, 12)
    packs, virtual = [], 0
    for ordinal in range(populated):
        packs.append((virtual, blocks[ordinal] * ALIGNMENT))
        virtual += blocks[ordinal] * ALIGNMENT
    entries = []
    for index in range(count):
        name_id, size, offset_blocks = struct.unpack_from("<III", pack0_head, HEADER_SIZE + 12 * index)
        entries.append((index, name_id, offset_blocks * ALIGNMENT, size))
    return entries, packs


def check_pins(data: dict) -> None:
    require(data.get("schema") == PINS_SCHEMA, "unknown Anniversary pin schema")
    for key, team in data["teams"].items():
        require(len(team["players"]) == ROSTER_SIZE, f"{key}: {len(team['players'])} pinned players")
        for entry in team["players"]:
            require(len(entry) == 4 and all(isinstance(v, int) for v in entry[2:]), f"{key}: malformed pin {entry!r}")
            _first, _last, old, new = entry
            require(0 <= old <= 30 and 1 <= new <= rr.YEARS_PRO_MAX and old != new, f"{key}: pin {entry!r} must change the value")


def load_pins(path: Path = PINS_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    check_pins(data)
    data["_file_sha256"] = sha(Path(path).read_bytes())
    return data


def team_candidates(packs_data: dict[int, bytes], entries, packs) -> list[dict]:
    """Every small ROST resource wholly inside a given pack, decoded to (first, last, years pro, record offset)."""
    found = []
    for ordinal, data in sorted(packs_data.items()):
        start, size_of_pack = packs[ordinal]
        require(len(data) == size_of_pack, f"pack {PACK_NAMES.get(ordinal, ordinal)} is not the size the outer directory declares")
        for index, name_id, virtual, size in entries:
            if not (start <= virtual and virtual + size <= start + size_of_pack) or not RESOURCE_HEADER_SIZE < size <= TEAM_SIZE_LIMIT:
                continue
            local = virtual - start
            if data[local:local + 4] != b"ROST":
                continue
            document = rr.RosterDocument(data[local + RESOURCE_HEADER_SIZE:local + size], reference_year=2025)
            records = [p for p in document.players if p.pool == "primary"]
            found.append({"entry": index, "pack": ordinal, "local": local, "size": size,
                          "players": [(p.first, p.last, p.record.values["years_pro"], p.offset) for p in records]})
    return found


def match_teams(candidates: list[dict], pins: dict) -> dict[str, tuple[dict, str]]:
    matched: dict[str, tuple[dict, str]] = {}
    used: set[int] = set()
    for key, team in sorted(pins["teams"].items()):
        pinned = [tuple(p) for p in team["players"]]
        hits = []
        for candidate in candidates:
            if len(candidate["players"]) != ROSTER_SIZE:
                continue
            if [(first, last) for first, last, _y, _o in candidate["players"]] != [(first, last) for first, last, _o, _n in pinned]:
                continue
            years = [y for _f, _l, y, _o in candidate["players"]]
            if years == [old for _f, _l, old, _n in pinned]:
                hits.append((candidate, "old"))
            elif years == [new for _f, _l, _o, new in pinned]:
                hits.append((candidate, "new"))
        require(len(hits) == 1, f"{key}: {len(hits)} resources match the pinned roster (expected exactly one)")
        candidate, state = hits[0]
        require(candidate["entry"] not in used, f"{key}: resource {candidate['entry']} matches two team-seasons")
        used.add(candidate["entry"])
        matched[key] = (candidate, state)
    require(len({state for _c, state in matched.values()}) == 1, "the 50 team-seasons are half repaired")
    return matched


def repair_packs(pack0_head: bytes, packs_data: dict[int, bytes], pins: dict | None = None,
                 approved_input_sha256: tuple[str, ...] = ()) -> tuple[dict[int, bytes], dict]:
    pins = pins or load_pins()
    check_pins(pins)
    require(set(packs_data) == {14, 15}, "packs E and F are both required")
    composed = False
    for ordinal, data in packs_data.items():
        digest = sha(data)
        known = {V05_PACK_SHA256[ordinal]} | ({F12_PACK_SHA256[ordinal]} if F12_PACK_SHA256[ordinal] else set())
        if digest not in known:
            require(digest in approved_input_sha256,
                    f"unexpected pack {PACK_NAMES[ordinal]} sha256 {digest}; pass --approved-input-sha256 for an exact composed input")
            composed = True
    entries, packs = read_directory(pack0_head)
    matched = match_teams(team_candidates(packs_data, entries, packs), pins)
    state = next(iter(matched.values()))[1]
    out = {ordinal: bytearray(data) for ordinal, data in packs_data.items()}
    declared: dict[int, list[int]] = {14: [], 15: []}
    teams = {}
    for key, (candidate, _state) in sorted(matched.items()):
        ordinal, local = candidate["pack"], candidate["local"]
        before = bytes(packs_data[ordinal][local:local + candidate["size"]])
        for (first, last, years, offset), (_f, _l, old, new) in zip(candidate["players"], pins["teams"][key]["players"]):
            at = local + RESOURCE_HEADER_SIZE + offset + YEARS_PRO_BYTE
            if state == "old":
                require(years == old and out[ordinal][at] & YEARS_PRO_MASK == old, f"{key} {first} {last}: years pro changed under us")
                out[ordinal][at] = (out[ordinal][at] & ~YEARS_PRO_MASK & 0xFF) | new
            declared[ordinal].append(at)
        after = bytes(out[ordinal][local:local + candidate["size"]])
        teams[key] = {"pack": PACK_NAMES[ordinal], "outer_entry": candidate["entry"], "pack_offset": local,
                      "size": candidate["size"], "before_sha256": sha(before), "after_sha256": sha(after),
                      "changed_bytes": sum(a != b for a, b in zip(before, after))}
    results = {ordinal: bytes(data) for ordinal, data in out.items()}
    # scope proof: only the declared years-pro bytes (bits 0-4) differ, in each pack.  Compare the stretches between
    # the declared bytes with memcmp-speed slices, then the declared bytes under their mask.
    changed = {}
    for ordinal, data in results.items():
        before = packs_data[ordinal]
        require(len(data) == len(before), "a pack changed size")
        cursor, count = 0, 0
        for at in sorted(declared[ordinal]):
            require(data[cursor:at] == before[cursor:at], f"a write escaped the declared scope in pack {PACK_NAMES[ordinal]} before 0x{at:x}")
            require((data[at] ^ before[at]) & ~YEARS_PRO_MASK & 0xFF == 0, f"bits outside the years-pro field changed at 0x{at:x}")
            count += 1 if data[at] != before[at] else 0
            cursor = at + 1
        require(data[cursor:] == before[cursor:], f"a write escaped the declared scope in pack {PACK_NAMES[ordinal]} after 0x{cursor:x}")
        changed[ordinal] = count
    if state == "old":
        again = match_teams(team_candidates(results, entries, packs), pins)
        require(all(s == "new" for _c, s in again.values()), "read-back does not match the repaired pins")
    receipt = {"schema": SCHEMA, "tool": TOOL, "state": "applied" if state == "old" else "already_applied",
               "approved_composed_input": composed, "pins_file_sha256": pins["_file_sha256"],
               "teams": len(teams), "records": sum(len(v) for v in declared.values()),
               "packs": {PACK_NAMES[o]: {"disc_file": f"vc_53450030/{PACK_NAMES[o]}", "before_file_sha256": sha(packs_data[o]),
                                         "after_file_sha256": sha(results[o]), "size": len(results[o]),
                                         "changed_bytes": changed[o],
                                         "declared_years_pro_bytes": {"mask": "0x1f", "count": len(declared[o]),
                                                                      "pack_offsets": sorted(declared[o])}}
                         for o in sorted(results)},
               "outside_scope_identical": True, "per_team": teams}
    return results, receipt


def read_years(path: Path) -> dict[tuple[str, str], int]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    require(len(rows) == ROSTER_SIZE, f"{Path(path).name}: {len(rows)} rows")
    years = {(r["first"], r["last"]): int(r["years_pro"]) for r in rows}
    require(len(years) == ROSTER_SIZE, f"{Path(path).name}: duplicate names")
    return years


def build_pins(pack0_head: bytes, packs_data: dict[int, bytes], old_teams_dir: Path, teams_dir: Path = TEAMS_DIR) -> dict:
    """Pin table: [first, last, old, new] per record.  ``old_teams_dir`` holds the team CSVs the v0.5 packs were compiled from
    (the data before f12); the one resource whose (first, last, years pro) equal a CSV's is that team-season's file (a retail
    team file of the same season can carry the same 53 names with other years pro).  ``new`` is the shipped CSV's years pro."""
    entries, packs = read_directory(pack0_head)
    candidates = team_candidates(packs_data, entries, packs)
    teams = {}
    for path in sorted(Path(teams_dir).glob("*.csv")):
        new = read_years(path)
        old = read_years(Path(old_teams_dir) / path.name)
        require(set(old) == set(new), f"{path.name}: the old and the new CSV list different players")
        hits = [c for c in candidates if {(f, l): y for f, l, y, _o in c["players"]} == old]
        require(len(hits) == 1, f"{path.stem}: {len(hits)} resources equal the old CSV roster and years pro")
        teams[path.stem] = {"players": [[f, l, y, new[(f, l)]] for f, l, y, _o in hits[0]["players"]]}
    return {"schema": PINS_SCHEMA, "pack_sha256": {PACK_NAMES[o]: sha(d) for o, d in sorted(packs_data.items())},
            "rule": "per record of the 50 Anniversary team-season files, in the resource's own order: [first, last, old, new]; "
                    "old = the years pro the v0.5 disc holds, new = years_pro of the shipped data/nfl2k5_espn25_more_teams CSV "
                    "(the game's convention, rookie 1)",
            "teams": teams}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack0", type=Path, required=True, help="vc_53450030/0 (read only: the outer directory)")
    parser.add_argument("--pack-e", type=Path, required=True)
    parser.add_argument("--pack-f", type=Path, required=True)
    parser.add_argument("--output-e", type=Path)
    parser.add_argument("--output-f", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--build-pins", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pins", type=Path, default=PINS_PATH)
    parser.add_argument("--old-teams-dir", type=Path, help="with --build-pins: the pre-f12 team CSVs the v0.5 packs were built from")
    parser.add_argument("--approved-input-sha256", action="append", default=[])
    args = parser.parse_args()
    with args.pack0.open("rb") as handle:
        head = handle.read(HEADER_SIZE)
        head += handle.read(12 * struct.unpack_from("<I", head)[0])
    packs_data = {14: args.pack_e.read_bytes(), 15: args.pack_f.read_bytes()}
    try:
        if args.build_pins:
            require(args.out is not None and not args.out.exists(), "--out must name a fresh file")
            require(args.old_teams_dir is not None, "--build-pins needs --old-teams-dir")
            pins = build_pins(head, packs_data, args.old_teams_dir)
            lines = ",\n".join(f'  {json.dumps(key)}: {{"players": ' + json.dumps(team["players"], separators=(",", ":"), ensure_ascii=True) + "}"
                               for key, team in sorted(pins["teams"].items()))
            text = (json.dumps({k: v for k, v in pins.items() if k != "teams"}, indent=1)[:-2]
                    + ',\n "teams": {\n' + lines + "\n }\n}\n")
            json.loads(text)
            args.out.write_text(text, encoding="utf-8", newline="\n")
            print(json.dumps({"teams": len(pins["teams"]), "pack_sha256": pins["pack_sha256"]}))
            return 0
        require(None not in (args.output_e, args.output_f, args.receipt), "--output-e, --output-f and --receipt are required")
        if any(p.exists() for p in (args.output_e, args.output_f, args.receipt)):
            parser.error("an output or the receipt already exists; choose fresh paths")
        results, receipt = repair_packs(head, packs_data, load_pins(args.pins), tuple(args.approved_input_sha256))
    except RepairRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    for path, ordinal in ((args.output_e, 14), (args.output_f, 15)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(results[ordinal])
    args.receipt.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"state": receipt["state"], "teams": receipt["teams"], "records": receipt["records"],
                      **{f"pack_{k}": [v["before_file_sha256"][:12], v["after_file_sha256"][:12], v["changed_bytes"]]
                         for k, v in receipt["packs"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
