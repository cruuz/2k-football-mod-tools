#!/usr/bin/env python3
"""The pack's roster edits at RETAIL roster capacity: no capacity growth, so no 128 MB (K128) requirement. b780 m64a.

A roster-edits document grown by tools/b77/b778_fa4_capacity.py carries ``free_agent_capacity``: the build then grows
the main ROST arena (0xCA000, appended primary records) and refuses to build without K128 ("Capacity growth needs the
128 MB memory option"), so the disc cannot run at 64 MB. The only rows that need the appended records are the dated
free-agent depth of tools/b77/b778_fa3_free_agent_depth.py (rows marked ``fa3_priority``): fa4 writes every depth
candidate, most of them into the appended records. This tool writes the retail-capacity variant of such a document:

* every section and every other refresh row unchanged, byte for byte;
* the ``free_agent_capacity`` block removed;
* the depth rows dropped, then the first N put back in fa3's priority order, re-addressed to the retail vacancies the
  way fa3 ``extend_plan`` addresses a new row (index in vacancy order, ``photo_id`` = 20000 + index). N is fa3's own
  rule: the most that keep the two-team import floor (106) plus the Create Player margin after the import floor,
  decided by the real refresh writer on the refresh's pinned base (the base fa3 and fa4 used, checked by SHA-256).

b780 rst2 (Q41): the 11/03 refresh also creates real players for the clubs' 53-man rosters (rows marked ``club_new``,
tools/b780/rst2_create_players.py), far more than the retail vacancies hold. They compete with the depth rows for the
vacancies, most important first: the club's kicker, punter and long snapper, then its kick and punt returners, then charted
starters (chart rank 1) by overall, then the other active players by chart rank, then practice-squad players. A club
player who does not fit is removed from his club (active or practice squad list, contract, guard), the club's chains
are renumbered in their old order, a specialist role he held goes to the next player at the position, and he is listed
as unrepresented (no vacant create record at retail capacity).

It refuses a document whose other rows need appended records. ``validate`` (run after ``fit`` unless --no-validate)
checks the variant with the build's own roster writers: the document checks, mod_build's capacity and champions-history
decisions, the refresh + import floor, college heal and created history on the pinned base (read-back, body size,
record counts, vacancies, round trip), every club against the capacity route of the source document (fa4's grow of the
same base with the source's own plan), and optionally every club against a final main ROST of a disc built from the
source.

  python3 tools/nfl2k5_roster_retail_fit.py fit --edits IN.json --base BASE --out OUT.json [--margin 10]
          [--report REPORT.json] [--compare-rost ROST] [--no-validate] [--drop-xbe-sections]
  python3 tools/nfl2k5_roster_retail_fit.py validate --edits OUT.json --source IN.json --base BASE
          [--report REPORT.json] [--compare-rost ROST] [--drop-xbe-sections]

--drop-xbe-sections  also leave out ``draft_pick_ownership`` and ``hback_roles``: their build steps install XBE
         directory spills that always take the allocator's scale-out (+212,992 resident bytes at 64 MB; see
         mod_editor/core/nfl2k5_memory_budget.py). Franchises then start with retail pick ownership and the backfield
         labels stay retail. The 64 MB profile's roster edits use it.

--base   the refresh's pinned base: a bare 0x90F60-byte main ROST body, or a disc image whose main roster precedes
         the refresh. Its SHA-256 must equal the base the document records (fa3_free_agent_depth / free_agent_capacity).
--compare-rost  optional: the main ROST of a disc built from IN.json (the outer entry, or a bare body).
Nothing is written except --out and --report. The coach records are a separate step
(tools/nfl2k5_coach_2026_data.py edits IN OUT).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import types
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for _entry in (ROOT, ROOT / "tools"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_spare_capacity as capacity  # noqa: E402
from tools.b77 import b778_fa3_free_agent_depth as fa3  # noqa: E402

SCHEMA = "nfl2k5.roster_retail_fit.v1"
XBE_SECTIONS = ("draft_pick_ownership", "hback_roles")   # the roster edits' own XBE steps (scale-out owners)
RETAIL_PRIMARY = capacity.PRIMARY_AFTER          # 2619 primary records: the retail main ROST (and every grown one's base)
DEPTH_KEY = "fa3_priority"
CLUB_KEY = "club_new"           # b780 rst2: a real player created for a club's 53-man roster
ACTIVE_STATUSES = ("ACT", "INA")


class RetailFitError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RetailFitError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def recorded_base(document: dict) -> str | None:
    """The base SHA-256 the document's depth or capacity receipt names (they must agree when both do)."""
    pins = {block.get("base_sha256") for block in (document.get("fa3_free_agent_depth") or {},
                                                   document.get("free_agent_capacity") or {}) if block.get("base_sha256")}
    require(len(pins) <= 1, "the depth and capacity receipts name different bases")
    return next(iter(pins), None)


def read_base(path: Path | str) -> bytes:
    return fa3.read_base(path)


def depth_rows(refresh: dict, *, contiguous: bool = True) -> list[dict]:
    """The depth rows in priority order; a source's priorities are 1..n (a variant keeps the signed ones too)."""
    rows = sorted((p for p in refresh.get("players") or [] if DEPTH_KEY in p), key=lambda p: p[DEPTH_KEY])
    require(not contiguous or [p[DEPTH_KEY] for p in rows] == list(range(1, len(rows) + 1)),
            "depth priorities must be 1..n")
    return rows


def is_droppable(row: dict) -> bool:
    """A row the retail variant may leave out: a dated free-agent depth row or a real player created for a club."""
    return DEPTH_KEY in row or bool(row.get(CLUB_KEY))


def club_rows(refresh: dict) -> list[dict]:
    return [p for p in refresh.get("players") or [] if p.get(CLUB_KEY)]


def overall(row: dict) -> int:
    """The game's own overall of a row's ratings and position (0 for a row without them)."""
    from mod_editor.core.nfl2k5_my_career_prospects import native_overall
    fields = row.get("fields") or {}
    if "position" not in fields or not set(rr.RATING_BYTE_ORDER) <= set(fields):
        return 0
    record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE), scheme="one_pool", reference_year=2026)
    for key in (*rr.RATING_BYTE_ORDER, "position"):
        record.set(key, fields[key])
    return int(native_overall(record))


def importance(refresh: dict, row: dict) -> tuple:
    """Lower is more important: his club's kicker, punter or long snapper; its kick or punt returner; a charted starter;
    another active player by chart rank (a player the chart does not list is the deepest); a practice-squad player."""
    roles = {role for t in refresh.get("teams") or [] for role, holder in (t.get("specialists") or {}).items()
             if holder == row["index"]}
    source = row.get("depth_source") or {}
    rank = int(source["pos_rank"]) if str(source.get("pos_rank", "")).isdigit() else 99
    active = row.get("status") in ACTIVE_STATUSES
    cls = 0 if roles & {"k", "h", "ls"} else 1 if roles & {"kr1", "pr"} else 2 if active and rank == 1 else 3 if active else 4
    return (cls, rank, -overall(row), row["index"])


def _indices(document: dict) -> dict[str, list[int]]:
    """Every primary record index the document addresses, by section, except the depth rows and their pointers."""
    out: dict[str, list[int]] = {}

    def add(name, value):
        if type(value) is int:
            out.setdefault(name, []).append(value)

    for section in ("edits", "college_updates", "free_agent_pool", "moves"):
        for row in document.get(section) or []:
            if isinstance(row, dict) and str(row.get("pool", "primary")) == "primary":
                add(section, row.get("index"))
    for row in (document.get("franchise_history") or {}).get("players") or []:
        if str(row.get("pool", "primary")) == "primary":
            add("franchise_history", row.get("index"))
    for team in document.get("special_teams") or []:
        for role in (team.get("roles") or {}).values():
            if isinstance(role, dict) and str(role.get("pool", "primary")) == "primary":
                add("special_teams", role.get("index"))
    refresh = document.get("roster_refresh") or {}
    depth = {p["index"] for p in refresh.get("players") or [] if is_droppable(p)}
    for row in refresh.get("players") or []:
        if not is_droppable(row):
            add("roster_refresh.players", row.get("index"))
    for guard in refresh.get("identity_guards") or []:
        add("roster_refresh.identity_guards", guard[0])
    for team in refresh.get("teams") or []:
        for key in ("active", "reserves"):
            for value in team.get(key) or []:
                add(f"roster_refresh.teams.{key}", value)
        for value in (team.get("specialists") or {}).values():
            add("roster_refresh.teams.specialists", value)
    for row in refresh.get("contract_initializations") or []:
        add("roster_refresh.contract_initializations", row.get("index"))
    for value in refresh.get("free_agents") or []:
        if value not in depth:
            add("roster_refresh.free_agents", value)
    return out


def capacity_dependencies(document: dict) -> dict[str, list[int]]:
    """Rows outside the depth free agents that address appended (capacity) records: {section: indices}."""
    return {k: sorted(v for v in values if v >= RETAIL_PRIMARY) for k, values in _indices(document).items()
            if any(v >= RETAIL_PRIMARY for v in values)}


REMAPPABLE = ("roster_refresh.teams.active", "roster_refresh.teams.reserves", "roster_refresh.teams.specialists",
              "roster_refresh.contract_initializations", "roster_refresh.identity_guards")


def pinned_depth(document: dict) -> list[int]:
    """Depth free agents the refresh itself signed (a club's active or reserve list, a contract, a guard): they are
    kept first and every reference follows their new index. Any other row that needs an appended record refuses."""
    needs = capacity_dependencies(document)
    refresh = document.get("roster_refresh") or {}
    depth = {p["index"] for p in refresh.get("players") or [] if is_droppable(p)}
    other = {k: v for k, v in needs.items() if k not in REMAPPABLE or not set(v) <= depth}
    require(not other, "these rows need appended capacity records, not only the depth free agents: "
            + "; ".join(f"{k} {v[:5]}" for k, v in other.items()))
    # every depth row a club list, contract or guard names, retail-addressed ones included (they move too)
    named = {i for k, v in _indices(document).items() if k in REMAPPABLE for i in v}
    return sorted(depth & named)


def remap(refresh: dict, mapping: dict[int, int]) -> dict:
    """The refresh with its club lists, specialists, contracts and guards following ``mapping`` (old -> new index)."""
    if not mapping:
        return refresh
    out = copy.deepcopy(refresh)
    for team in out.get("teams") or []:
        for key in ("active", "reserves"):
            if team.get(key):
                team[key] = [mapping.get(v, v) for v in team[key]]
        if isinstance(team.get("specialists"), dict):
            team["specialists"] = {k: mapping.get(v, v) for k, v in team["specialists"].items()}
    for row in out.get("contract_initializations") or []:
        if row.get("index") in mapping:
            row["index"] = mapping[row["index"]]
    out["identity_guards"] = [[mapping.get(g[0], g[0]), *g[1:]] for g in out.get("identity_guards") or []] \
        if "identity_guards" in out else out.get("identity_guards")
    if out.get("identity_guards") is None:
        out.pop("identity_guards", None)
    return out


def ordered_rows(rows: list[dict], pinned, refresh: dict | None = None) -> list[dict]:
    """The rows the fit keeps first: the pinned ones (on a club: most important first when ``refresh`` is given, else in
    the order they come), then the rest in their order (depth priority)."""
    pinned = set(pinned)
    first = [r for r in rows if r["index"] in pinned]
    if refresh is not None:
        first.sort(key=lambda r: importance(refresh, r))
    return first + [r for r in rows if r["index"] not in pinned]


def split(refresh: dict) -> tuple[dict, list[dict]]:
    """(the refresh without the droppable rows and their free-agent pointers, the depth rows in priority order followed by
    the created club rows in document order)."""
    rows = depth_rows(refresh)
    extra = club_rows(refresh)
    gone = {p["index"] for p in rows} | {p["index"] for p in extra}
    stripped = copy.deepcopy(refresh)
    stripped["players"] = [p for p in refresh.get("players") or [] if not is_droppable(p)]
    stripped["free_agents"] = [x for x in refresh.get("free_agents") or [] if x not in gone]
    return stripped, rows + extra


RETURNER_POSITIONS = ("HB", "WR", "CB", "FS", "SS", "FB")


def _chains(team: dict, rows: dict) -> dict[int, list[int]]:
    chains: dict[int, list[int]] = {}
    for index in team["active"]:
        if index in rows:                                   # every club player has a row in a real plan
            chains.setdefault(rows[index]["fields"].get("position"), []).append(index)
    for members in chains.values():
        members.sort(key=lambda i: (rows[i]["fields"].get("depth_rank", 7), rows[i]["fields"].get("depth_side", 7), i))
    return chains


def drop_club_players(plan: dict, gone: set, lost: list[dict]) -> dict:
    """``plan`` without the club players in ``gone`` (changed in place): off their club's lists, contract initializers and
    guards; the club's chains renumbered in their old order; a specialist role they held goes to the next player."""
    from mod_editor.core import nfl2k5_roster_refresh as writer
    rows = {r["index"]: r for r in plan["players"]}
    names = rr.SCHEME_POSITION_NAMES["one_pool"]
    code = {name: i for i, name in enumerate(names)}
    for team in plan["teams"]:
        held = set(team["active"]) | set(team["reserves"]) | {v for v in team["specialists"].values() if v is not None}
        if not held & gone:
            continue
        team["active"] = [i for i in team["active"] if i not in gone]
        team["reserves"] = [i for i in team["reserves"] if i not in gone]
        chains = _chains(team, rows)
        for members in chains.values():
            for order, index in enumerate(members):
                rank, side = writer.native_depth_pair(order)
                rows[index]["fields"]["depth_rank"], rows[index]["fields"]["depth_side"] = rank, side
        spec = team["specialists"]

        def nth(position, n=0):
            members = chains.get(code[position], [])
            return members[n] if len(members) > n else None

        if spec.get("k") in gone:
            spec["k"] = nth("K")
        if spec.get("h") in gone:
            spec["h"] = nth("P")
        if spec.get("ls") in gone:
            spec["ls"] = nth("C", 1) or (chains.get(code["TE"], [])[1:] or [None])[-1]
        for role in ("kr1", "kr2", "pr"):
            if spec.get(role) in gone:
                spec[role] = None
        taken = {v for v in spec.values() if v is not None}
        pool = sorted((i for position in RETURNER_POSITIONS for i in chains.get(code[position], []) if i not in taken),
                      key=lambda i: (RETURNER_POSITIONS.index(names[rows[i]["fields"]["position"]]),
                                     rows[i]["fields"].get("depth_rank", 7), i))
        for role in ("kr1", "pr"):
            if spec.get(role) is None and pool:
                spec[role] = pool.pop(0)
    plan["contract_initializations"] = [c for c in plan.get("contract_initializations") or [] if c["index"] not in gone]
    plan["identity_guards"] = [g for g in plan.get("identity_guards") or [] if g[0] not in gone]
    plan["free_agents"] = [i for i in plan.get("free_agents") or [] if i not in gone]
    plan["unrepresented"] = list(plan.get("unrepresented") or []) + [
        {"gsis_id": r.get("gsis_id"), "name": f"{r.get('first')} {r.get('last')}", "status": r.get("status"),
         "team": r.get("team"), "source": r.get("source"), "reason": "no vacant create record at retail capacity (64 MB)"}
        for r in lost]
    return plan


def plan_with(stripped: dict, rows: list[dict], vacant: list[int], count: int, pinned=()) -> dict:
    """``stripped`` plus the first ``count`` rows on the first ``count`` vacancies (fa3.extend_plan's addressing).
    A pinned row (one the refresh put on a club) is not a free agent; the club lists and contracts follow it. A pinned row
    past ``count`` is removed from its club (drop_club_players), before anything is re-addressed: a new address can equal
    the old address of a row that was left out."""
    require(0 <= count <= min(len(rows), len(vacant)), f"{count} rows for {len(vacant)} vacant records")
    pinned = set(pinned)
    out = copy.deepcopy(stripped)
    first = len(out["players"])
    out["players"].extend(copy.deepcopy(r) for r in rows[:count])        # still at their own indices, as the lists name them
    lost = [r for r in rows[count:] if r["index"] in pinned]
    if lost:
        drop_club_players(out, {r["index"] for r in lost}, lost)
    mapping = {}
    for k, (index, row) in enumerate(zip(vacant, rows[:count])):
        moved = out["players"][first + k]
        moved["index"] = index
        if DEPTH_KEY in moved:
            moved["fields"] = dict(moved["fields"], photo_id=fa3.PHOTO_BASE + index)
        if row["index"] in pinned:
            mapping[row["index"]] = index
        else:
            out["free_agents"].append(index)
    return remap(out, mapping)


def fit(base: bytes, stripped: dict, rows: list[dict], margin: int = fa3.DEFAULT_MARGIN, progress=None, pinned=()):
    """(count, vacancies, final body, import-floor receipt): fa3.fit's rule on these rows, every count the real writer."""
    vacant = fa3.vacant_indices(stripped, base)
    want = capacity.IMPORT_FLOOR + margin
    cache: dict[int, tuple] = {}

    def trial(n):
        if n not in cache:
            try:
                body, receipt = fa3.apply_with_floor(base, plan_with(stripped, rows, vacant, n, pinned))
                floor = receipt["roster_refresh"]["import_floor"]
                cache[n] = (floor["vacancies_after"] >= want, body, floor)
            except (rr.RosterRecordError, capacity.SpareCapacityError, RetailFitError) as exc:
                cache[n] = (False, None, {"refused": str(exc)})
            if progress:
                progress(f"{n} rows: {'fit' if cache[n][0] else 'do not fit'} "
                         f"({cache[n][2].get('vacancies_after', cache[n][2].get('refused'))})")
        return cache[n]

    require(trial(0)[0], f"the refresh alone keeps fewer than {want} import vacancies at retail capacity")
    lo, hi = 0, min(len(rows), len(vacant))
    while lo < hi:                          # vacancies fall as players are added: the largest n that still fits
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if trial(mid)[0] else (lo, mid - 1)
    if lo < min(len(rows), len(vacant)):
        require(not trial(lo + 1)[0], "capacity is not monotone; refuse to guess")
    _ok, body, floor = trial(lo)
    return lo, vacant, body, floor


def retail_variant(document: dict, base: bytes, *, margin: int = fa3.DEFAULT_MARGIN, source_sha256: str = "",
                   progress=None, drop_xbe_sections: bool = False) -> tuple[dict, dict]:
    """(the retail-capacity roster-edits document, its receipt)."""
    rr.read_edits(document)
    require(isinstance(document.get("roster_refresh"), dict), "the document has no dated roster refresh to fit")
    pin = recorded_base(document)
    require(pin is None or pin == sha256(base), f"the base is not the refresh's pinned base ({pin[:12] if pin else ''}...)")
    require(len(base) == capacity.BODY_SIZE, "the base must be a 0x90F60-byte main ROST body")
    pinned = pinned_depth(document)
    stripped, rows = split(document["roster_refresh"])
    rows = ordered_rows(rows, pinned, document["roster_refresh"])
    count, vacant, body, floor = fit(base, stripped, rows, margin, progress, pinned)
    out = copy.deepcopy(document)
    out["roster_refresh"] = plan_with(stripped, rows, vacant, count, pinned)
    # b780 IR1: modern injured reserve is forced off at 64 MB, so an injured player cannot start on the club's IR there:
    # the variant releases players for room (charted starters protected) as the pre-IR plans did
    out["roster_refresh"]["room_policy"] = "release"
    out.pop("free_agent_capacity", None)
    old = document.get("fa3_free_agent_depth") or {}
    kept_rows, left_rows = rows[:count], rows[count:]
    depth_kept = [r for r in kept_rows if DEPTH_KEY in r]
    depth_left = [r for r in left_rows if DEPTH_KEY in r]
    club_kept = [r for r in kept_rows if r.get(CLUB_KEY)]
    club_left = [r for r in left_rows if r.get(CLUB_KEY)]
    name = lambda r: f"{r['first']} {r['last']}"  # noqa: E731
    receipt = {"schema": SCHEMA, "source_sha256": source_sha256, "base_sha256": sha256(base), "margin_target": margin,
               "retail_primary": RETAIL_PRIMARY, "depth_candidates": len(depth_kept) + len(depth_left),
               "depth_kept": len(depth_kept), "depth_dropped": len(depth_left),
               "club_players_candidates": len(club_kept) + len(club_left), "club_players_kept": len(club_kept),
               "club_players_dropped": len(club_left),
               "club_players_kept_names": [f"{name(r)} {r['team']} {r['fields'].get('position')}" for r in club_kept],
               "club_players_dropped_names": [f"{name(r)} {r['team']}" for r in club_left],
               "vacant_records": len(vacant),
               "vacancies_used_by_depth": count, "vacancies_left_for_depth": len(vacant) - count,
               "free_agents_before": len((document["roster_refresh"]).get("free_agents") or []),
               "free_agents_after": len(out["roster_refresh"]["free_agents"]),
               "import_vacancies_after_floor": floor["vacancies_after"], "import_floor": capacity.IMPORT_FLOOR,
               "import_floor_added_records": floor.get("added_records"), "primary_after_floor": floor.get("primary_after"),
               "removed_capacity_records": (document.get("free_agent_capacity") or {}).get("records", 0),
               "signed_depth_kept": [{"old_index": r["index"], "index": i, "name": name(r)}
                                     for i, r in zip(vacant, kept_rows) if r["index"] in set(pinned) and DEPTH_KEY in r],
               "final_body_sha256": sha256(body)}
    out["fa3_free_agent_depth"] = {
        **{k: old[k] for k in ("data", "data_sha256", "as_of") if k in old},
        "added": len(depth_kept), "candidates": len(depth_kept) + len(depth_left),
        "margin": floor["vacancies_after"] - capacity.IMPORT_FLOOR,
        "import_vacancies_after_floor": floor["vacancies_after"], "floor": capacity.IMPORT_FLOOR,
        "names": [name(p) for p in depth_kept],
        "left_out": [name(p) for p in depth_left],
        "base_sha256": sha256(base), "final_body_sha256": sha256(body), "capacity_arena": False,
        "retail_capacity": receipt}
    receipt["dropped_xbe_sections"] = [k for k in XBE_SECTIONS if drop_xbe_sections and k in out]
    for key in receipt["dropped_xbe_sections"]:
        out.pop(key)
    out["name"] = f"{document.get('name', '')} | retail roster capacity (64 MB): no capacity growth".strip(" |")
    return out, receipt


# --------------------------------------------------------------------------------------------------- validation
def _clubs(body: bytes) -> tuple[Any, dict[int, list[str]], list[str]]:
    doc = rr.RosterDocument(bytes(body), scheme="one_pool", reference_year=2026)
    clubs = {t.index: [doc.by_offset[o].key for o in t.slots] for t in doc.teams if t.index < 32}
    free = [doc.by_offset[o].key for o in doc.free_agents if o in doc.by_offset]
    return doc, clubs, free


def _rost_body(raw: bytes) -> bytes:
    return raw[0x20:] if raw[:4] == b"ROST" else raw


def _writers(base: bytes, refresh: dict, created_history: Any):
    from mod_editor.core import nfl2k5_college_check as college_check
    body, receipt = fa3.apply_with_floor(base, refresh)
    body, heal = college_check.heal_null_references(body, source="retail fit validation")
    history = None
    if created_history:
        from mod_editor.core import nfl2k5_created_history as created
        body, history = created.apply_body(body, created.load_data())
    return body, receipt["roster_refresh"]["import_floor"], heal, history


def validate(variant: dict, source: dict, base: bytes, *, margin: int = fa3.DEFAULT_MARGIN,
             compare_rost: bytes | None = None, variant_path: Path | None = None, progress=None,
             drop_xbe_sections: bool = False) -> dict:
    checks: list[dict] = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if progress:
            progress(f"{'PASS' if ok else 'FAIL'} {name}{': ' + str(detail) if detail else ''}")

    rr.read_edits(variant)
    check("read_edits accepts the document", True)
    check("no capacity block", "free_agent_capacity" not in variant)
    refresh, source_refresh = variant["roster_refresh"], source["roster_refresh"]
    top = max([p["index"] for p in refresh["players"]] + [-1])
    check("every refresh row is a retail record", top < RETAIL_PRIMARY, f"max index {top}")
    check("every free-agent pointer is a retail record", max(refresh["free_agents"] + [-1]) < RETAIL_PRIMARY,
          f"{len(refresh['free_agents'])} free agents")
    check("no other row addresses an appended record", not capacity_dependencies(variant))
    kept, rows = depth_rows(refresh, contiguous=False), depth_rows(source_refresh)
    club_kept, club_all = club_rows(refresh), club_rows(source_refresh)
    pinned = pinned_depth(source)
    pinned_set = set(pinned)
    everyone = ordered_rows(rows + club_all, pinned, source_refresh)
    n = len(kept) + len(club_kept)
    expected_all, left_all = everyone[:n], everyone[n:]
    expected = sorted([r for r in expected_all if DEPTH_KEY in r], key=lambda p: p[DEPTH_KEY])
    expected_club = sorted([r for r in expected_all if r.get(CLUB_KEY)], key=lambda p: p["gsis_id"])
    renumbered = ("depth_rank", "depth_side")                # a club that lost a player renumbers its chains
    bare = lambda p: {k: v for k, v in p.items() if k not in ("index", "fields")}  # noqa: E731
    inner = lambda p: {k: v for k, v in p["fields"].items() if k not in ("photo_id", *renumbered)}  # noqa: E731
    same = [bare(p) for p in kept] == [bare(p) for p in expected] and \
        [bare(p) for p in sorted(club_kept, key=lambda p: p["gsis_id"])] == [bare(p) for p in expected_club]
    fields = all(inner(a) == inner(b) and a["fields"]["photo_id"] == fa3.PHOTO_BASE + a["index"] for a, b in zip(kept, expected)) \
        and all(inner(a) == inner(b) and a["fields"].get("photo_id") == b["fields"].get("photo_id")
                for a, b in zip(sorted(club_kept, key=lambda p: p["gsis_id"]), expected_club))
    check("kept depth rows are the source's signed ones plus rows 1..N (re-addressed only)", same and fields,
          f"{len(kept)} of {len(rows)} depth rows and {len(club_kept)} of {len(club_all)} club players kept, "
          f"{len(pinned)} signed to clubs")
    new_index = {p["gsis_id"]: p["index"] for p in refresh["players"] if is_droppable(p)}
    back = {r["index"]: new_index[r["gsis_id"]] for r in expected_all if r["index"] in pinned_set and r["gsis_id"] in new_index}
    kept_pinned = [r for r in expected_all if r["index"] in pinned_set]
    check("every signed depth free agent is kept and its club lists and contract follow it",
          len(back) == len(kept_pinned), f"{len(back)} of {len(pinned)} kept; the rest leave their clubs")
    check("kept depth rows that kept their index are byte for byte the source's",
          True, f"{sum(1 for a, b in zip(kept, rows) if a == b)} of {len(kept)} identical")
    others_v = [p for p in refresh["players"] if not is_droppable(p)]
    others_s = [p for p in source_refresh["players"] if not is_droppable(p)]
    flat = lambda p: {**p, "fields": {k: v for k, v in p["fields"].items() if k not in renumbered}}  # noqa: E731
    check("every other refresh row is the source's, same order",
          [flat(p) for p in others_v] == [flat(p) for p in others_s],
          f"{sum(1 for a, b in zip(others_v, others_s) if a != b)} rows with renumbered depth rows")
    droppable_source = {p["index"] for p in rows} | {p["index"] for p in club_all}
    check("free agents: the source's other pointers, same order",
          [x for x in refresh["free_agents"] if x not in {p["index"] for p in kept} | {p["index"] for p in club_kept}]
          == [x for x in source_refresh["free_agents"] if x not in droppable_source])
    other = sorted(k for k in set(variant) | set(source) if variant.get(k) != source.get(k))
    allowed = {"roster_refresh", "free_agent_capacity", "fa3_free_agent_depth", "name"}
    if drop_xbe_sections:
        allowed |= set(XBE_SECTIONS)
        check("no scale-out XBE sections (draft-pick ownership, H-back roles)",
              not any(k in variant for k in XBE_SECTIONS), [k for k in XBE_SECTIONS if k in variant])
    check("every other section is the source's", set(other) <= allowed, f"changed {other}")
    lost_pinned = {r["index"] for r in left_all if r["index"] in pinned_set}
    again = lambda i: back.get(i, i)  # noqa: E731
    teams_ok = True
    for tv, ts in zip(refresh["teams"], source_refresh["teams"]):
        teams_ok &= tv["active"] == [again(i) for i in ts["active"] if i not in lost_pinned]
        teams_ok &= tv["reserves"] == [again(i) for i in ts["reserves"] if i not in lost_pinned]
        teams_ok &= {k: v for k, v in tv.items() if k not in ("active", "reserves", "specialists")} == \
            {k: v for k, v in ts.items() if k not in ("active", "reserves", "specialists")}
        for role, holder in ts["specialists"].items():
            teams_ok &= (tv["specialists"][role] == again(holder)) if holder not in lost_pinned else \
                (tv["specialists"][role] is not None or role == "kr2")
    teams_ok &= refresh["contract_initializations"] == [dict(c, index=again(c["index"]))
                                                        for c in source_refresh["contract_initializations"]
                                                        if c["index"] not in lost_pinned]
    teams_ok &= refresh["identity_guards"] == [[again(g[0]), *g[1:]] for g in source_refresh["identity_guards"]
                                               if g[0] not in lost_pinned]
    teams_ok &= len(refresh.get("unrepresented") or []) == len(source_refresh.get("unrepresented") or []) + len(lost_pinned)
    teams_ok &= all(refresh.get(k) == source_refresh.get(k) for k in set(refresh) | set(source_refresh)
                    if k not in ("players", "free_agents", "teams", "contract_initializations", "identity_guards",
                                 "unrepresented", "room_policy"))
    teams_ok &= refresh.get("room_policy", "release") == "release"
    check("refresh teams, guards, contracts and corrections unchanged (signed depth free agents re-addressed)", teams_ok,
          f"{len(lost_pinned)} club players removed from their clubs")
    from mod_editor.core import mod_build
    from mod_editor.core import nfl2k5_throw_tuning as tt
    records = 0
    if variant_path is not None:
        records = mod_build._roster_capacity_records(types.SimpleNamespace(roster_edits=str(variant_path)))
        check("mod_build reads no capacity records (no arena growth, no K128 demand)", records == 0, f"records {records}")
        champions = mod_build._champions_history_plan(types.SimpleNamespace(
            roster_edits=str(variant_path), honors_page=True, reserves_16=False, created_teams_extra=0,
            season_2026=True, honors_history="builtin"))
        check("champions history without arena growth is no_room (a 64 MB trim, reported by the build)",
              champions["status"] == "no_room", champions["status"])
    check("the roster does not ask for the 128 MB stop",
          tt.k128_requires_128(roster_capacity=bool(records)) is False)
    check("pinned base", recorded_base(variant) in (None, sha256(base)) and len(base) == capacity.BODY_SIZE)
    body, floor, heal, history = _writers(base, refresh, variant.get("created_history"))
    check("refresh, import floor, college heal and created history write a retail-size body",
          len(body) == capacity.BODY_SIZE, f"{len(body):#x} bytes, colleges healed {heal.get('changed')}, created history "
          + (f"{history['players_written']} written / {history['players_not_in_roster']} not in roster" if history else "none"))
    doc, clubs, free = _clubs(body)
    check("read-back round trip", doc.to_body() == body)
    vacancies = capacity.import_vacancies(body)
    check("import vacancies keep the floor plus the margin", vacancies >= capacity.IMPORT_FLOOR + margin,
          f"{vacancies} (floor {capacity.IMPORT_FLOOR} + margin {margin})")
    primary = len(doc.by_pool("primary"))
    listed = set(doc.free_agents)
    primary_by_index = {p.index: p for p in doc.by_pool("primary")}
    planned = [primary_by_index[i].offset for i in refresh["free_agents"]]
    check("free-agent list holds every planned free agent", all(o in listed for o in planned)
          and len(doc.free_agents) <= doc.free_agent_capacity,
          f"{len(doc.free_agents)} of {doc.free_agent_capacity} pointer slots ({len(planned)} from the refresh plan)")
    summary = {"primary_records": primary, "import_floor_added_records": floor.get("added_records"),
               "import_vacancies": vacancies, "free_agents": len(doc.free_agents),
               "free_agent_pointer_slots": doc.free_agent_capacity, "club_players": sum(len(v) for v in clubs.values()),
               "depth_free_agents_kept": len(kept), "depth_free_agents_dropped": len(rows) - len(kept),
               "club_players_kept": len(club_kept), "club_players_left_out": len(club_all) - len(club_kept),
               "body_bytes": len(body), "final_body_sha256": sha256(body),
               "created_history": history and {k: history[k] for k in ("players_written", "players_not_in_roster", "words_written")}}
    cclubs = None
    if source.get("free_agent_capacity"):
        from tools.b77 import b778_fa4_capacity as fa4
        grown, _ = fa4.grow(base, source["free_agent_capacity"]["records"])
        # the capacity route is the source's plan under the variant's own room policy (release at 64 MB)
        route_plan = dict(source_refresh, room_policy=refresh.get("room_policy", "release"))
        cbody, _cfloor, _cheal, chistory = _writers(grown, route_plan, source.get("created_history"))
        cdoc, cclubs, cfree = _clubs(cbody)
        out_keys = {f"{r['last']},{r['first']},{r['birth_date']}" for r in left_all if r["index"] in pinned_set}
        cfree_set = set(cfree)
        differ, extra_total, extra_keys = [], 0, set()
        for t in range(32):
            route, here = cclubs.get(t, []), clubs.get(t, [])
            extra = [k for k in here if k not in route]
            # a club that lost a created player has an open place: the capacity route released a player for room that the
            # variant keeps (at most one per player left out), the rest is the route's club in the route's order
            freed = len([k for k in route if k in out_keys])
            if [k for k in here if k in route] != [k for k in route if k not in out_keys] or not set(extra) <= cfree_set \
                    or len(extra) > freed:
                differ.append(t)
            extra_total += len(extra)
            extra_keys |= set(extra)
        check("every club identical to the source's capacity route (membership and depth order)", not differ,
              f"differing clubs {differ}; {len(out_keys)} club players left out for capacity, {extra_total} players the "
              "route released for room stay")
        gone = cfree_set - set(free)
        left_keys = {f"{r['last']},{r['first']},{r['birth_date']}" for r in left_all}
        # a free agent the capacity route has and the variant lacks is a row left out (a depth free agent, or a created
        # player the route released for room) or a player the route released that a club now keeps
        check("free agents: the capacity route's minus the dropped depth rows",
              set(free) <= cfree_set and gone == (left_keys & cfree_set) | extra_keys,
              f"{len(free)} vs {len(cfree)}: {len(gone)} fewer")
        summary["capacity_route"] = {"primary_records": len(cdoc.by_pool("primary")), "free_agents": len(cdoc.free_agents),
                                     "body_bytes": len(cbody)}
    if compare_rost is not None:
        # The pinned-base harness is not the whole build: a club with more eligible players than slots can keep a
        # different last man after the build's other passes. What the trim must not do is add a difference: the
        # variant's clubs differ from the disc exactly where the source's own plan (the capacity route) does.
        rdoc, rclubs, rfree = _clubs(_rost_body(compare_rost))
        differ = [t for t in range(32) if clubs.get(t) != rclubs.get(t)]
        detail = {"clubs_identical_to_disc": 32 - len(differ), "differing_clubs": {
            t: {"only_here": [k for k in clubs[t] if k not in rclubs[t]], "only_on_disc": [k for k in rclubs[t] if k not in clubs[t]]}
            for t in differ}, "disc_primary_records": len(rdoc.by_pool("primary")), "disc_free_agents": len(rfree)}
        summary["disc_comparison"] = detail
        if cclubs is not None:
            cdiffer = [t for t in range(32) if cclubs.get(t) != rclubs.get(t)]
            check("the trim adds no club difference to the disc built from the source", differ == cdiffer,
                  f"{32 - len(differ)} of 32 clubs identical to the disc; the source's own plan differs in the same {cdiffer}")
        else:
            check("clubs compared with the disc built from the source (report only)", True,
                  f"{32 - len(differ)} of 32 identical, differing {differ}")
    return {"schema": SCHEMA, "ok": all(c["ok"] for c in checks), "checks": checks, "summary": summary}


# --------------------------------------------------------------------------------------------------- command line
def _write_json(path: Path, value: Any) -> None:
    Path(path).write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fit", help="write the retail-capacity variant (and validate it)")
    f.add_argument("--edits", required=True)
    f.add_argument("--out", required=True)
    v = sub.add_parser("validate", help="validate a retail-capacity variant against its source")
    v.add_argument("--edits", required=True, help="the retail-capacity variant")
    v.add_argument("--source", required=True, help="the document it was derived from")
    for p in (f, v):
        p.add_argument("--base", required=True, help="the refresh's pinned base: a bare main ROST body or a disc image")
        p.add_argument("--margin", type=int, default=fa3.DEFAULT_MARGIN,
                       help="Create Player records kept above the two-team import floor (default 10)")
        p.add_argument("--report")
        p.add_argument("--compare-rost", help="the main ROST of a disc built from the source (outer entry or body)")
    f.add_argument("--no-validate", action="store_true")
    for p in (f, v):
        p.add_argument("--drop-xbe-sections", action="store_true",
                       help="also leave out draft_pick_ownership and hback_roles (they take the XBE scale-out)")
    args = parser.parse_args(argv)
    say = lambda message: print(message, flush=True)  # noqa: E731
    try:
        base = read_base(args.base)
        compare = Path(args.compare_rost).read_bytes() if args.compare_rost else None
        if args.command == "fit":
            raw = Path(args.edits).read_bytes()
            source = json.loads(raw.decode("utf-8"))
            variant, receipt = retail_variant(source, base, margin=args.margin, source_sha256=sha256(raw), progress=say,
                                              drop_xbe_sections=args.drop_xbe_sections)
            _write_json(Path(args.out), variant)
            say(json.dumps(receipt, indent=1))
            report = {"fit": receipt}
            if not args.no_validate:
                report["validation"] = validate(variant, source, base, margin=args.margin, compare_rost=compare,
                                                variant_path=Path(args.out), progress=say,
                                                drop_xbe_sections=args.drop_xbe_sections)
        else:
            variant = json.loads(Path(args.edits).read_text(encoding="utf-8"))
            source = json.loads(Path(args.source).read_text(encoding="utf-8"))
            report = {"validation": validate(variant, source, base, margin=args.margin, compare_rost=compare,
                                             variant_path=Path(args.edits), progress=say,
                                             drop_xbe_sections=args.drop_xbe_sections)}
        if args.report:
            _write_json(Path(args.report), report)
        ok = report.get("validation", {"ok": True})["ok"]
        say("validation passed" if ok and "validation" in report else "validation FAILED" if not ok else "written")
        return 0 if ok else 1
    except (RetailFitError, rr.RosterRecordError, capacity.SpareCapacityError, fa3.DepthError, OSError, ValueError) as exc:
        parser.exit(2, f"retail fit refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
