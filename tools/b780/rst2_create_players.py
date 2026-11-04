#!/usr/bin/env python3
"""b780 rst2 (Q39, Q40, Q41, Q89): give every player on a club's 53-man roster a record in the pack's dated refresh plan.

On 11/03 the plan had no record for 121 players the nflverse roster lists as ACT or INA (A.J. Terrell, Josh Jacobs, the
Saints' long snapper Zach Wood, the Rams' and Dolphins' kickers ...). Noah (11/03): create them in the main 128 MB pack
using capacity records; rate them with the same pipeline that rated the 2026 league; real headshots; nflverse birth
dates, colleges and contracts. This tool adds them to the plan; the plan's own update tool then seats them
(tools/b780/roster1_refresh_update.py) and the writer creates the records (mod_editor/core/nfl2k5_roster_refresh.py).

* A player who already has a record the plan did not list (Charlie Heck, Thomas Morstead: free agents from the dated
  pool) gets a row on that record; nothing about the record changes but his club, jersey and depth rows.
* Every other player gets a ``new`` row on the next vacant create record (the capacity arena grows by the same number:
  ``free_agent_capacity.records``): nflverse name, birth date, college, height, weight and jersey; the position from his
  chart slots (the plan's own slot map), his nflverse position and his weight; ratings from r1 ratings v2.4
  (tools/b780/rst2_rate.py); the body type from height and weight; skin tone and face from his headshot
  (tools/b780/rst2_headshots.py, the tone a person reviewed against the picture); commentary by recorded surname else
  jersey number; the no-photo selector 7100 until the real-portraits step (nfl2k5_real_portraits) matches his picture.
* ``club_new`` marks these rows. The 64 MB fit (tools/nfl2k5_roster_retail_fit.py) keeps as many of them as the retail
  vacancies allow, most important first, and removes the rest from their clubs.

  python3 tools/b780/rst2_create_players.py targets BASE.json roster_2026.csv depth_charts_2026.csv --body V08_ROST --out T.json
  python3 tools/b780/rst2_create_players.py create  BASE.json roster_2026.csv depth_charts_2026.csv OUT.json --body V08_ROST
          --as-of 2026-11-03 [--work HEADSHOTS_WORK] [--tones tones.json] [--report R.json]
  python3 tools/b780/rst2_create_players.py finalize DOC.json roster_2026.csv [--out DOC2.json]
  python3 tools/b780/rst2_create_players.py capacity DOC.json --base BASELINE.body [--out DOC2.json]
"""
from __future__ import annotations

import argparse
import collections
import copy
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT), str(HERE), str(ROOT / "tools")]

import roster1_refresh_update as upd  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

CODES = {name: code for code, name in rr.SCHEME_POSITION_NAMES["one_pool"].items()} \
    if isinstance(rr.SCHEME_POSITION_NAMES["one_pool"], dict) else \
    {name: code for code, name in enumerate(rr.SCHEME_POSITION_NAMES["one_pool"])}
VACANT = "****************"
FIRST_VACANT = 2464
NO_PHOTO_REFRESH = 7100                  # nfl2k5_real_portraits.NO_PHOTO_REFRESH: the dated refresh's no-photo selector
EDGE_WEIGHT, DT_WEIGHT = 247, 277        # nflverse OLB at or over 247 lb and DE under 277 lb are edge rushers (10/14 plan)
# the 10/14 plan's face shapes per build (fa5): sha256(gsis_id)[1] selects among four, or three for an extra-large build
FACES = {0: (1, 3, 4, 6), 1: (1, 3, 4, 6), 2: (1, 2, 5, 6), 3: (2, 5, 6)}


def norm(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", text.replace(".", " ")))


def split_name(full):
    """(first, last) from a display name, without a generational suffix ('Kenneth Murray, Jr.' -> Kenneth, Murray)."""
    text = re.sub(r"[,\s]+(?:jr|sr|ii|iii|iv|v)\.?$", "", full.strip(), flags=re.IGNORECASE)
    first, _, last = text.partition(" ")
    return first, last


def body_for(height, weight):
    bmi = 703.0 * weight / (height * height)
    return 0 if bmi < 24 else 1 if bmi < 28 else 2 if bmi < 33 else 3


def face_for(gsis, body):
    digest = hashlib.sha256(gsis.encode()).digest()
    options = FACES[body]
    return options[digest[1] % len(options)]


class Slots:
    """The chart slot -> record position map of the plan itself (majority among its own players)."""

    def __init__(self, rows):
        votes = collections.defaultdict(collections.Counter)
        names = rr.SCHEME_POSITION_NAMES["one_pool"]
        for row in rows:
            source = row.get("depth_source")
            if source and "position" in row["fields"]:
                votes[(source["pos_grp"], source["pos_abb"])][names[row["fields"]["position"]]] += 1
        self.slot = {k: v.most_common(1)[0][0] for k, v in votes.items()}

    def position(self, node, entries, weight):
        """The record position name of a player nflverse lists as ``node['depth_chart_position']``."""
        dcp, pos = node["depth_chart_position"], node["position"]
        direct = {"QB": "QB", "K": "K", "P": "P", "LS": "C", "WR": "WR", "TE": "TE", "RB": "HB", "FB": "FB", "C": "C",
                  "G": "G", "T": "T", "CB": "CB", "DT": "DT", "NT": "DT", "MLB": "LB", "ILB": "LB"}
        if pos == "RB" and dcp == "FB":
            return "FB"
        if dcp in direct and dcp not in ("CB",):
            return direct[dcp]
        voted = collections.Counter(self.slot.get((e["pos_grp"], e["pos_abb"])) for e in entries
                                    if e["pos_grp"] != "Special Teams")
        voted.pop(None, None)
        if dcp in ("CB", "FS", "SS"):                  # a defensive back is what his chart slots say, else his listing
            backs = {k: v for k, v in voted.items() if k in ("CB", "FS", "SS")}
            return max(backs, key=backs.get) if backs else {"CB": "CB", "FS": "FS", "SS": "SS"}[dcp]
        if dcp == "DE":
            line = {k: v for k, v in voted.items() if k in ("EDGE", "DT")}
            if len(line) == 1:
                return next(iter(line))
            return "DT" if weight >= DT_WEIGHT else "EDGE"
        if dcp == "OLB":
            backers = {k: v for k, v in voted.items() if k in ("EDGE", "LB")}
            if len(backers) == 1:
                return next(iter(backers))
            return "EDGE" if weight >= EDGE_WEIGHT else "LB"
        raise ValueError(f"no position rule for nflverse {pos}/{dcp}")


def club_code(team):
    return upd.club(team)


def candidates(plan, fresh):
    teams = {t["team"] for t in plan["teams"]}
    have = {r["gsis_id"] for r in plan["players"]}
    return [n for g, n in sorted(fresh.items(), key=lambda kv: (club_code(kv[1]["team"]), kv[1]["full_name"]))
            if n["status"] in upd.CLUB_STATUSES and club_code(n["team"]) in teams and g not in have]


def records_of(body):
    doc = rr.RosterDocument(bytes(body), scheme="one_pool", reference_year=2026)
    return doc, {p.index: p for p in doc.by_pool("primary")}


def find_record(records, node):
    """The pack's own record of this player: same first and last name and birth month and day (suffix ignored)."""
    year, month, day = (int(x) for x in node["birth_date"].split("-"))
    first, last = split_name(node["full_name"])
    hits = [p for p in records.values() if p.first != VACANT and norm(p.last) == norm(last)
            and norm(p.first) == norm(first) and p.record.get("birth_month") == month and p.record.get("birth_day") == day]
    return hits[0] if len(hits) == 1 else None


def vacant_indices(doc, used):
    return [p.index for p in doc.by_pool("primary") if p.index >= FIRST_VACANT and p.group == "pool"
            and p.first == p.last == VACANT and p.record.get("player_type") == 1 and p.index not in used]


def plan_candidates(base, roster_csv, charts_csv, body):
    plan = base["roster_refresh"]
    fresh = upd.latest_roster(roster_csv)
    entries_by, _newest, _hist = upd.latest_charts(charts_csv)
    chart = collections.defaultdict(list)
    for team_entries in entries_by.values():
        for e in team_entries:
            chart[e["gsis_id"]].append(e)
    slots = Slots(plan["players"])
    doc, records = records_of(body)
    used = {r["index"] for r in plan["players"]}
    out = []
    for node in candidates(plan, fresh):
        g = node["gsis_id"]
        found = find_record(records, node)
        if found is not None and found.index in used:
            found = None
        weight = int(float(node["weight"] or 0))
        position = found.record.position_name if found is not None else slots.position(node, chart.get(g, []), weight)
        out.append(dict(node=node, record=found, position=position, entries=chart.get(g, [])))
    return plan, fresh, doc, records, out


# ------------------------------------------------------------------------------------------------ targets
def targets(args):
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    _plan, _fresh, _doc, _records, found = plan_candidates(base, args.roster, args.charts, Path(args.body).read_bytes())
    out = []
    for c in found:
        n = c["node"]
        first, last = split_name(n["full_name"])
        year, month, day = (int(x) for x in n["birth_date"].split("-"))
        out.append(dict(gsis=n["gsis_id"], first=first, last=last, pos=c["position"], college=n["college"], bm=month, bd=day,
                        team=club_code(n["team"]), url=n["headshot_url"], espn=n["espn_id"], existing=c["record"] is not None,
                        method="roster_2026_gsis_id"))
    Path(args.out).write_text(json.dumps(out, indent=0), encoding="utf-8")
    print(len(out), "targets;", sum(t["existing"] for t in out), "on an existing record")


# ------------------------------------------------------------------------------------------------ create
def commentary(last, jersey):
    ids = rr.recorded_surname_ids()
    return ids.get(rr.commentary_surname(last)) or rr.number_commentary_id(jersey)


def handedness():
    path = ROOT / "data" / "HANDEDNESS_FINAL.json"
    out = {}
    if path.exists():
        for p in json.loads(path.read_text(encoding="utf-8")).get("players", ()):
            if p.get("gsis_id") and p.get("hand") in ("Left", "Right"):
                out[p["gsis_id"]] = 0 if p["hand"] == "Left" else 1
    return out


def create(args):
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    as_of = dt.date.fromisoformat(args.as_of)
    body = Path(args.body).read_bytes()
    plan, fresh, doc, records, found = plan_candidates(base, args.roster, args.charts, body)
    work = Path(args.work) if args.work else None
    gate = json.loads((work / "gate.json").read_text(encoding="utf-8")) if work and (work / "gate.json").exists() else {}
    tones = json.loads(Path(args.tones).read_text(encoding="utf-8")) if args.tones else {}
    lefty = handedness()
    out = copy.deepcopy(base)
    oplan = out["roster_refresh"]
    rows, guards = oplan["players"], oplan["identity_guards"]
    # existing records first (they join the comparison population of the ratings)
    added_existing, created = [], []
    for c in found:
        if c["record"] is None:
            continue
        n, p = c["node"], c["record"]
        row = dict(birth_date=str(p.record.birth_date), college=n["college"], depth_source=None,
                   fields={"depth_rank": 7, "depth_side": 7, "jersey": int(n["jersey_number"] or 0),
                           "position": p.record.get("position")},
                   first=p.first, gsis_id=n["gsis_id"], index=p.index, last=p.last, new=False,
                   source=upd.ROSTER_URL, source_as_of=args.as_of, source_name=n["full_name"], source_week=n["week"],
                   status=n["status"], team=club_code(n["team"]))
        rows.append(row)
        if not any(g[0] == p.index for g in guards):             # a free agent of the dated pool is already guarded
            guards.append([p.index, p.first, p.last, str(p.record.birth_date)])
        added_existing.append(f"{n['full_name']} (record {p.index})")
    fresh_new = [c for c in found if c["record"] is None]
    import rst2_rate
    rated, receipt = rst2_rate.rate(args.roster, args.charts, rows, {c["node"]["gsis_id"]: c["position"] for c in fresh_new},
                                    as_of, Path(args.model_inputs), Path(args.nflverse))
    free = vacant_indices(doc, {r["index"] for r in rows})
    if len(free) < len(fresh_new):
        raise SystemExit(f"{len(fresh_new)} players need records, the body has {len(free)} vacant create records")
    problems = []
    for c, index in zip(fresh_new, free):
        n, g = c["node"], c["node"]["gsis_id"]
        first, last = split_name(n["full_name"])
        for text in (first, last):
            try:
                rr.validate_name(text)
            except rr.RosterRecordError as exc:
                problems.append(f"{n['full_name']}: {exc}")
        year, month, day = (int(x) for x in n["birth_date"].split("-"))
        height, weight = int(float(n["height"])), int(float(n["weight"]))
        jersey = int(n["jersey_number"] or 0)
        entry = (int(n["entry_year"]) if str(n.get("entry_year") or "").isdigit() else as_of.year - int(float(n["years_exp"] or 0)))
        info = gate.get(g, {}).get("info", {})
        tone = tones.get(g, {})
        body_type = body_for(height, weight)
        skin = tone.get("skin", info.get("ita_skin", 0))
        fields = dict(rated[g]["ratings"])
        fields.update(position=CODES[c["position"]], jersey=jersey, height=height, weight=weight, birth_month=month,
                      birth_day=day, birth_year=year, years_pro=max(1, as_of.year - entry + 1), depth_rank=7, depth_side=7,
                      hand=lefty.get(g, 1), body=body_type, pbp_id=commentary(last, jersey), photo_id=NO_PHOTO_REFRESH,
                      skin=skin, face=face_for(g, body_type), dreads=tone.get("dreads", 0))
        rows.append(dict(birth_date=n["birth_date"], college=n["college"], depth_source=None, fields=fields, first=first,
                         gsis_id=g, index=index, last=last, new=True, club_new=True, source=upd.ROSTER_URL,
                         source_as_of=args.as_of, source_name=n["full_name"], source_week=n["week"], status=n["status"],
                         team=club_code(n["team"])))
        created.append(dict(name=n["full_name"], club=club_code(n["team"]), index=index, position=c["position"],
                            tier=rated[g]["tier"], skin=skin, tone_source="reviewed" if g in tones else "ita",
                            overall=None))
    cap = out.get("free_agent_capacity")
    if isinstance(cap, dict):
        cap["records"] += len(created)
        cap["final_primary"] = cap["base_primary"] + cap["records"]
    out["rst2_created_players"] = dict(
        schema="nfl2k5.rst2_created_players.v1", as_of=args.as_of, created=len(created), existing_records_added=len(added_existing),
        ratings_model=receipt["model"], comparison_population=receipt["comparison_population"],
        inputs_sha256=receipt["inputs_sha256"],
        roster_csv_sha256=hashlib.sha256(Path(args.roster).read_bytes()).hexdigest(),
        depth_chart_csv_sha256=hashlib.sha256(Path(args.charts).read_bytes()).hexdigest(),
        rule="club_new rows: nflverse identity and measurables, r1-ratings-v2.4 ratings, reviewed headshot tone; contracts by the "
             "update tool's placeholder rule", names=[c["name"] for c in created])
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    report = dict(created=created, existing=added_existing, name_problems=problems, ratings=receipt)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in report.items() if k != "ratings"}))
    if problems:
        print("\n".join(problems))


# ------------------------------------------------------------------------------------------------ finalize
BIRTH_CORRECTIONS = ("00-0041539",)         # Logan Jones (CHI C): the guard had 2001-10-29, nflverse lists 2001-10-19 (Q48)


def finalize(args):
    """The document-level fixes of the wave: Q47 (no stale top-level special_teams roles), Q48 (a sourced birth date), the
    Ole Miss -> Mississippi college fold (GEN1 folded the table's double name: row 93 -> row 176)."""
    doc = json.loads(Path(args.doc).read_text(encoding="utf-8"))
    plan = doc["roster_refresh"]
    fresh = upd.latest_roster(args.roster)
    report = {}
    stale = doc.pop("special_teams", None)
    report["special_teams_roles_dropped"] = sum(len(t.get("roles", {})) for t in stale or [])
    moved = []
    for change in doc.get("college_updates", ()):
        if change["college"] == "Ole Miss":
            change["college"] = "Mississippi"
            moved.append(f"{change['first']} {change['last']} (record {change['index']})")
    report["ole_miss_to_mississippi"] = moved
    rows = {r["gsis_id"]: r for r in plan["players"]}
    corrections = {c["index"]: c for c in plan.get("birth_corrections", ())}
    mismatches = []
    for g, row in rows.items():
        node = fresh.get(g)
        if node and node["birth_date"] and node["birth_date"] != row["birth_date"] and not row.get("new"):
            mismatches.append(f"{row['first']} {row['last']} {row['index']}: plan {row['birth_date']}, nflverse {node['birth_date']}")
    for g in BIRTH_CORRECTIONS:
        row, node = rows[g], fresh[g]
        if row["birth_date"] != node["birth_date"]:
            corrections[row["index"]] = dict(
                index=row["index"], first=row["first"], last=row["last"], was=row["birth_date"], birth_date=node["birth_date"],
                source=upd.ROSTER_URL, evidence="nflverse roster_2026 (week 8, fetched 2026-11-03) lists the later date; the "
                "players.csv of 2026-09-24 the plan's identity guard came from listed the earlier one")
            row["birth_date"] = node["birth_date"]
    plan["birth_corrections"] = sorted(corrections.values(), key=lambda c: c["index"])
    report["birth_corrected"] = [f"{c['first']} {c['last']} {c['was']} -> {c['birth_date']}" for c in plan["birth_corrections"]]
    report["other_birth_date_differences_not_changed"] = [m for m in mismatches if not any(
        m.startswith(f"{c['first']} {c['last']} ") for c in plan["birth_corrections"])]
    Path(args.out or args.doc).write_text(json.dumps(doc, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1)[:2500])


# ------------------------------------------------------------------------------------------------ capacity
def capacity_block(args):
    """Refresh the capacity receipts of a document whose plan changed: grow the pinned base by ``records`` and replay."""
    from mod_editor.core import nfl2k5_college_check as college_check
    from mod_editor.core import nfl2k5_roster_arena as arena
    from mod_editor.core import nfl2k5_roster_refresh as refresh
    from mod_editor.core import nfl2k5_spare_capacity as capacity
    document = json.loads(Path(args.doc).read_text(encoding="utf-8"))
    base = Path(args.base).read_bytes()
    block = document["free_agent_capacity"]
    assert hashlib.sha256(base).hexdigest() == block["base_sha256"], "not the pinned base"
    plan = document["roster_refresh"]
    records = args.records or block["records"]
    grown, receipt = arena.migrate(base, reserves_16=False, capacity_records=records)
    result, _r = refresh.apply_body(grown, plan)
    result, heal = college_check.heal_null_references(result, source="capacity roster")
    vacancies = capacity.import_vacancies(result)
    doc = rr.RosterDocument(result, scheme="one_pool", reference_year=2026)
    assert vacancies >= capacity.IMPORT_FLOOR + 10, f"only {vacancies} import vacancies"
    # final_primary stays base + create vacancies, as fa4 recorded it (the grown arena also holds free draft-class records)
    block.update(records=records, final_primary=block["base_primary"] + records, free_agents=len(doc.free_agents),
                 import_vacancies=vacancies, margin=vacancies - capacity.IMPORT_FLOOR,
                 grown_body_sha256=hashlib.sha256(grown).hexdigest(), final_body_sha256=hashlib.sha256(result).hexdigest(),
                 college_null_repair=heal["changed"])
    depth = document.get("fa3_free_agent_depth")
    if isinstance(depth, dict):
        depth.update(margin=vacancies - capacity.IMPORT_FLOOR, import_vacancies_after_floor=vacancies)
    Path(args.out or args.doc).write_text(json.dumps(document, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(block))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="step", required=True)
    for name in ("targets", "create"):
        p = sub.add_parser(name)
        p.add_argument("base")
        p.add_argument("roster")
        p.add_argument("charts")
        if name == "create":
            p.add_argument("out")
            p.add_argument("--as-of", required=True)
            p.add_argument("--work")
            p.add_argument("--tones")
            p.add_argument("--report")
            p.add_argument("--model-inputs", default="/media/noah/Storage/.b76-research/r1/port_work")
            p.add_argument("--nflverse", default="/media/noah/Storage/.b76-research/r1/data/nflverse")
        else:
            p.add_argument("--out", required=True)
        p.add_argument("--body", required=True, help="the released v0.8 main roster body (827,456 bytes)")
    p = sub.add_parser("finalize")
    p.add_argument("doc")
    p.add_argument("roster")
    p.add_argument("--out")
    p = sub.add_parser("capacity")
    p.add_argument("doc")
    p.add_argument("--base", required=True)
    p.add_argument("--records", type=int, default=0)
    p.add_argument("--out")
    args = ap.parse_args(argv)
    {"targets": targets, "create": create, "finalize": finalize, "capacity": capacity_block}[args.step](args)


if __name__ == "__main__":
    main()
