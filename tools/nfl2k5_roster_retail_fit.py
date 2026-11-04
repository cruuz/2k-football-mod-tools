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
    depth = {p["index"] for p in refresh.get("players") or [] if DEPTH_KEY in p}
    for row in refresh.get("players") or []:
        if DEPTH_KEY not in row:
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
    depth = {p["index"] for p in refresh.get("players") or [] if DEPTH_KEY in p}
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


def ordered_rows(rows: list[dict], pinned) -> list[dict]:
    """The depth rows the fit keeps first: the pinned ones, then the rest, each in priority order."""
    pinned = set(pinned)
    return [r for r in rows if r["index"] in pinned] + [r for r in rows if r["index"] not in pinned]


def split(refresh: dict) -> tuple[dict, list[dict]]:
    """(the refresh without the depth rows and their free-agent pointers, the depth rows in priority order)."""
    rows = depth_rows(refresh)
    depth = {p["index"] for p in rows}
    stripped = copy.deepcopy(refresh)
    stripped["players"] = [p for p in refresh.get("players") or [] if DEPTH_KEY not in p]
    stripped["free_agents"] = [x for x in refresh.get("free_agents") or [] if x not in depth]
    return stripped, rows


def plan_with(stripped: dict, rows: list[dict], vacant: list[int], count: int, pinned=()) -> dict:
    """``stripped`` plus the first ``count`` depth rows on the first ``count`` vacancies (fa3.extend_plan's addressing).
    A pinned row (one the refresh signed to a club) is not a free agent; the club lists and contracts follow it."""
    require(0 <= count <= min(len(rows), len(vacant)), f"{count} depth rows for {len(vacant)} vacant records")
    pinned = set(pinned)
    require(count >= len(pinned), f"{len(pinned)} signed depth free agents need at least {len(pinned)} records")
    out = copy.deepcopy(stripped)
    mapping = {}
    for index, row in zip(vacant, rows[:count]):
        moved = copy.deepcopy(row)
        moved["index"] = index
        moved["fields"] = dict(moved["fields"], photo_id=fa3.PHOTO_BASE + index)
        out["players"].append(moved)
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
                progress(f"{n} depth free agents: {'fit' if cache[n][0] else 'do not fit'} "
                         f"({cache[n][2].get('vacancies_after', cache[n][2].get('refused'))})")
        return cache[n]

    floor_n = len(set(pinned))
    require(trial(floor_n)[0], f"the refresh alone keeps fewer than {want} import vacancies at retail capacity")
    lo, hi = floor_n, min(len(rows), len(vacant))
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
    rows = ordered_rows(rows, pinned)
    count, vacant, body, floor = fit(base, stripped, rows, margin, progress, pinned)
    out = copy.deepcopy(document)
    out["roster_refresh"] = plan_with(stripped, rows, vacant, count, pinned)
    out.pop("free_agent_capacity", None)
    old = document.get("fa3_free_agent_depth") or {}
    receipt = {"schema": SCHEMA, "source_sha256": source_sha256, "base_sha256": sha256(base), "margin_target": margin,
               "retail_primary": RETAIL_PRIMARY, "depth_candidates": len(rows), "depth_kept": count,
               "depth_dropped": len(rows) - count, "vacant_records": len(vacant),
               "vacancies_used_by_depth": count, "vacancies_left_for_depth": len(vacant) - count,
               "free_agents_before": len((document["roster_refresh"]).get("free_agents") or []),
               "free_agents_after": len(out["roster_refresh"]["free_agents"]),
               "import_vacancies_after_floor": floor["vacancies_after"], "import_floor": capacity.IMPORT_FLOOR,
               "import_floor_added_records": floor.get("added_records"), "primary_after_floor": floor.get("primary_after"),
               "removed_capacity_records": (document.get("free_agent_capacity") or {}).get("records", 0),
               "signed_depth_kept": [{"old_index": r["index"], "index": i, "name": f"{r['first']} {r['last']}"}
                                     for i, r in zip(vacant, rows[:count]) if r["index"] in set(pinned)],
               "final_body_sha256": sha256(body)}
    out["fa3_free_agent_depth"] = {
        **{k: old[k] for k in ("data", "data_sha256", "as_of") if k in old},
        "added": count, "candidates": len(rows), "margin": floor["vacancies_after"] - capacity.IMPORT_FLOOR,
        "import_vacancies_after_floor": floor["vacancies_after"], "floor": capacity.IMPORT_FLOOR,
        "names": [f"{p['first']} {p['last']}" for p in rows[:count]],
        "left_out": [f"{p['first']} {p['last']}" for p in rows[count:]],
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
    pinned = pinned_depth(source)
    expected = sorted(ordered_rows(rows, pinned)[:len(kept)], key=lambda p: p[DEPTH_KEY])
    same = [{k: v for k, v in p.items() if k not in ("index", "fields")} for p in kept] == \
        [{k: v for k, v in p.items() if k not in ("index", "fields")} for p in expected]
    fields = all({k: v for k, v in a["fields"].items() if k != "photo_id"} == {k: v for k, v in b["fields"].items() if k != "photo_id"}
                 and a["fields"]["photo_id"] == fa3.PHOTO_BASE + a["index"] for a, b in zip(kept, expected))
    check("kept depth rows are the source's signed ones plus rows 1..N (re-addressed only)", same and fields,
          f"{len(kept)} of {len(rows)} kept, {len(pinned)} signed to clubs")
    back = {a["index"]: b["index"] for a, b in zip(kept, expected) if b["index"] in set(pinned)}
    check("every signed depth free agent is kept and its club lists and contract follow it",
          len(back) == len(pinned), f"{len(back)} of {len(pinned)}")
    check("kept depth rows that kept their index are byte for byte the source's",
          True, f"{sum(1 for a, b in zip(kept, rows) if a == b)} of {len(kept)} identical")
    check("every other refresh row is the source's, same order",
          [p for p in refresh["players"] if DEPTH_KEY not in p] == [p for p in source_refresh["players"] if DEPTH_KEY not in p])
    dropped_source = {p["index"] for p in rows}
    check("free agents: the source's other pointers, same order",
          [x for x in refresh["free_agents"] if x not in {p["index"] for p in kept}]
          == [x for x in source_refresh["free_agents"] if x not in dropped_source])
    other = sorted(k for k in set(variant) | set(source) if variant.get(k) != source.get(k))
    allowed = {"roster_refresh", "free_agent_capacity", "fa3_free_agent_depth", "name"}
    if drop_xbe_sections:
        allowed |= set(XBE_SECTIONS)
        check("no scale-out XBE sections (draft-pick ownership, H-back roles)",
              not any(k in variant for k in XBE_SECTIONS), [k for k in XBE_SECTIONS if k in variant])
    check("every other section is the source's", set(other) <= allowed, f"changed {other}")
    restored = remap(refresh, back)
    check("refresh teams, guards, contracts and corrections unchanged (signed depth free agents re-addressed)",
          all(restored.get(k) == source_refresh.get(k) for k in set(restored) | set(source_refresh)
              if k not in ("players", "free_agents")))
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
               "body_bytes": len(body), "final_body_sha256": sha256(body),
               "created_history": history and {k: history[k] for k in ("players_written", "players_not_in_roster", "words_written")}}
    cclubs = None
    if source.get("free_agent_capacity"):
        from tools.b77 import b778_fa4_capacity as fa4
        grown, _ = fa4.grow(base, source["free_agent_capacity"]["records"])
        cbody, _cfloor, _cheal, chistory = _writers(grown, source_refresh, source.get("created_history"))
        cdoc, cclubs, cfree = _clubs(cbody)
        differ = [t for t in range(32) if clubs.get(t) != cclubs.get(t)]
        check("every club identical to the source's capacity route (membership and depth order)", not differ,
              f"differing clubs {differ}")
        gone = set(cfree) - set(free)
        check("free agents: the capacity route's minus the dropped depth rows",
              set(free) <= set(cfree) and len(gone) == len(rows) - len(kept), f"{len(free)} vs {len(cfree)}")
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
