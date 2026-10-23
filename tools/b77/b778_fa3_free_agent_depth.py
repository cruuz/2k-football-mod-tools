#!/usr/bin/env python3
"""b778 fa3: add real unsigned, unretired NFL free agents to the pack's dated roster refresh.

Noah (10/22): "drastically increase the free agent pool with everybody who's technically an NFL free agent and hasn't
officially retired ... even Colin Kaepernick". The main ROST is a fixed-size native resource (0x90F60 bytes; a
franchise save keeps the same 0x91000 arena), so a new player needs a vacant primary record, and vacant records are
also what the game's practice-squad importer needs: an Anniversary moment or a historic Quick Game imports two
53-player team files (nfl2k5_spare_capacity.IMPORT_FLOOR = 106) and in-game Create Player takes one each. This tool
therefore adds no code path and changes no geometry: it appends the players of
``mod_editor/data/nfl2k5_free_agent_depth_2026.v1.json`` as ``new`` rows of the dated refresh (the same writer the refresh's own signings use) and lists them as free agents,
in priority order, only as many as keep ``IMPORT_FLOOR + margin`` vacancies after the import floor has restored
what the name space allows. The count is decided by applying the real refresh and floor to the real pre-refresh
roster, so the result is exactly what the build writes.

  python3 tools/b77/b778_fa3_free_agent_depth.py merge --edits IN.json --base ROSTER --out OUT.json [--margin 10]

``--base`` is the refresh's pinned base: a disc image whose main roster precedes the refresh (the Oct 13 pack disc)
or a bare 0x90F60-byte body. Nothing is written except ``--out``.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_spare_capacity as capacity  # noqa: E402

SCHEMA = "nfl2k5.free_agent_depth.v1"
DATA = ROOT / "mod_editor" / "data" / "nfl2k5_free_agent_depth_2026.v1.json"
FIRST_VACANT = 2464                 # nfl2k5_roster_refresh: a new row may only take a vacant record from here on
PHOTO_BASE = 20000                  # the dated free agents' "no portrait" selector (nfl2k5_free_agents)
DEFAULT_MARGIN = 10                 # Create Player records left above the two-team import floor
STATUS = "UFA"
ROW_FIELDS = frozenset(rr.RATING_BYTE_ORDER) | {
    "position", "jersey", "height", "weight", "birth_month", "birth_day", "birth_year", "years_pro", "depth_rank",
    "depth_side", "hand", "body", "pbp_id", "skin", "face", "dreads", "headless"}


class DepthError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise DepthError(message)


def load(path=DATA):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(data):
    require(data.get("schema") == SCHEMA, "unknown free-agent depth data")
    players = data["players"]
    require([p["priority"] for p in players] == list(range(1, len(players) + 1)), "priorities must be 1..n in order")
    require(len({p["gsis_id"] for p in players}) == len(players), "duplicate player")
    require(len({(p["first"], p["last"]) for p in players}) == len(players), "duplicate name")
    for p in players:
        require(p["status"] == "unsigned_not_retired" and len(p.get("sources", ())) >= 2
                and all(s.get("url", "").startswith("https://") for s in p["sources"]),
                f"{p['name']}: needs dated unsigned and not-retired evidence")
        fields = p["fields"]
        require(set(fields) == ROW_FIELDS, f"{p['name']}: fields must be exactly the documented set")
        require(not set(fields) & set(rr.POINTER_FIELDS), f"{p['name']}: raw pointer")
        require(0 <= fields["jersey"] <= 99, f"{p['name']}: jersey")
        require(rr.validate_name(p["first"]) == p["first"] and rr.validate_name(p["last"]) == p["last"],
                f"{p['name']}: name the game cannot hold")
        require(fields["pbp_id"] == rr.number_commentary_id(fields["jersey"])
                or fields["pbp_id"] in rr.recorded_surname_ids().values(),
                f"{p['name']}: commentary must be a verified surname clip or the jersey number")
        require(fields["face"] == (5 if fields["skin"] == 0 else 0), f"{p['name']}: face outside the neutral rule")
    return data


def vacant_indices(plan, body=None):
    """Vacant create records a new refresh row may take, in index order. With ``body`` (the refresh's base) they
    are read from the records; without it, from the plan alone (the pack's 2464..2618 vacancies)."""
    taken = {row["index"] for row in plan["players"]} | {g[0] for g in plan["identity_guards"]}
    if body is None:
        return [i for i in range(FIRST_VACANT, capacity.PRIMARY_AFTER) if i not in taken]
    doc = rr.RosterDocument(bytes(body), scheme="one_pool", reference_year=2026)
    return [p.index for p in doc.by_pool("primary") if p.index >= FIRST_VACANT and p.group == "pool"
            and p.first == p.last == "****************" and p.record.get("player_type") == 1
            and p.index not in taken]


def extend_plan(plan, data, count, body=None):
    """A copy of the refresh ``plan`` with the first ``count`` players as new unsigned rows and free agents."""
    validate(data)
    players = data["players"][:count]
    require(0 <= count <= len(data["players"]), "count outside the data")
    known = {row["gsis_id"] for row in plan["players"]}
    clash = [p["name"] for p in players if p["gsis_id"] in known]
    require(not clash, f"already in the refresh: {clash}")
    free = vacant_indices(plan, body)
    require(len(free) >= count, f"only {len(free)} vacant records for {count} players")
    out = copy.deepcopy(plan)
    for index, p in zip(free, players):
        out["players"].append({
            "birth_date": p["birth_date"], "college": p["college"], "depth_source": None, "first": p["first"],
            "last": p["last"], "gsis_id": p["gsis_id"], "index": index, "new": True,
            "fields": dict(p["fields"], photo_id=PHOTO_BASE + index),
            "source": p["sources"][0]["url"], "source_as_of": data["as_of"], "source_name": p["name"],
            "status": STATUS, "team": "", "evidence": p["sources"][1], "fa3_priority": p["priority"]})
        out["free_agents"].append(index)
    return out


def apply_with_floor(base, plan):
    directive = {"schema": rr.EDITS_SCHEMA, "edits": [], "roster_refresh": plan, "restore_import_floor": True}
    return rr.apply_body(bytes(base), directive, scheme="one_pool")


def fit(base, plan, data, margin=DEFAULT_MARGIN):
    """The most players (in priority order) that keep IMPORT_FLOOR + margin vacancies after refresh and floor.
    Returns (count, final body, import-floor receipt). Every count tried is the real writer on the real base."""
    want = capacity.IMPORT_FLOOR + margin
    cache = {}

    def trial(n):
        if n not in cache:
            try:
                body, receipt = apply_with_floor(base, extend_plan(plan, data, n, base))
                floor = receipt["roster_refresh"]["import_floor"]
                cache[n] = (floor["vacancies_after"] >= want, body, floor)
            except (rr.RosterRecordError, capacity.SpareCapacityError, DepthError) as exc:
                # DepthError also means "no room": a pool larger than the vacant records must not break the search.
                cache[n] = (False, None, {"refused": str(exc)})
        return cache[n]

    require(trial(0)[0], f"the refresh alone keeps fewer than {want} import vacancies")
    lo, hi = 0, len(data["players"])
    while lo < hi:                          # vacancies fall as players are added: the largest n that still fits
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if trial(mid)[0] else (lo, mid - 1)
    ok, body, floor = trial(lo)
    if lo < len(data["players"]):
        require(not trial(lo + 1)[0], "capacity is not monotone; refuse to guess")
    return lo, body, floor


def read_base(path):
    path = Path(path)
    raw = path.read_bytes() if path.stat().st_size < 0x100000 else None
    if raw is not None:
        require(len(raw) == capacity.BODY_SIZE, "a bare base must be the 0x90F60-byte main ROST body")
        return raw
    return rr.load_image(path).to_body()


def merge(args):
    data = load(args.data)
    edits = json.loads(Path(args.edits).read_text(encoding="utf-8"))
    base = read_base(args.base)
    count, body, floor = fit(base, edits["roster_refresh"], data, args.margin)
    out = dict(edits, roster_refresh=extend_plan(edits["roster_refresh"], data, count, base))
    out["fa3_free_agent_depth"] = {
        "data": DATA.name, "data_sha256": hashlib.sha256(Path(args.data).read_bytes()).hexdigest(),
        "as_of": data["as_of"], "added": count, "candidates": len(data["players"]), "margin": args.margin,
        "import_vacancies_after_floor": floor["vacancies_after"], "floor": capacity.IMPORT_FLOOR,
        "names": [p["name"] for p in data["players"][:count]],
        "left_out": [p["name"] for p in data["players"][count:]],
        "base_sha256": hashlib.sha256(base).hexdigest(),
        "final_body_sha256": hashlib.sha256(body).hexdigest()}
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out["fa3_free_agent_depth"], indent=1))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("merge", help="write a roster-edits document with the free agents that fit")
    m.add_argument("--edits", required=True)
    m.add_argument("--base", required=True, help="the refresh's base roster: a disc image or a bare main ROST body")
    m.add_argument("--out", required=True)
    m.add_argument("--data", default=str(DATA))
    m.add_argument("--margin", type=int, default=DEFAULT_MARGIN,
                   help="Create Player records kept above the two-team import floor (default 10)")
    args = parser.parse_args(argv)
    return merge(args)


if __name__ == "__main__":
    raise SystemExit(main())
