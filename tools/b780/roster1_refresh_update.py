#!/usr/bin/env python3
"""b780 roster1: bring the pack's dated roster refresh up to a newer nflverse snapshot (Noah 11/03: "update every
team's roster with the latest trades, signings and depth chart moves").

The 10/14 refresh plan (``roster_refresh`` in the pack's roster-edits document, schema nfl2k5.roster_refresh.v1) was
authored outside the repo; only its writer (mod_editor/core/nfl2k5_roster_refresh.py) ships. This tool updates that
plan in place from two nflverse files (CC-BY-4.0): rosters/roster_2026.csv and depth_charts/depth_charts_2026.csv
(the newest chart timestamp of each club).

* Only players who already have a record in the plan move (trades, signings from the free-agent pool, cuts, injured
  reserve, practice squad). No record is created, so the disc keeps its vacant records (the Anniversary moments'
  import floor). A rostered player without a record is listed in ``unrepresented``, as on 10/14.
* Membership by status: ACT and INA on the club's active list, DEV on its reserves (at most 12), RES on no list (the
  writer puts injured players back on their club, b780 D6), everyone else on the free-agent list.
* Every club's depth chart is re-derived from its chart: a player's chain is his record's position; his order is his
  best chart entry for that position (rank, then the chart's slot number; a long snapper after every centre, a
  player the chart does not list after every listed one); the n-th player takes the refresh's native rank/side pair.
* Specialists from the chart's Special Teams group: PK, H, LS, KR (two) and PR, the first listed player who is on
  the club's active list.
* A player who joins a club from the free-agent list with no contract gets the same DESIGN one-year minimum
  placeholder the 10/14 plan used; an initializer for a player who is no longer on a club is dropped.

  python3 tools/b780/roster1_refresh_update.py BASE.json roster_2026.csv depth_charts_2026.csv OUT.json \
      --as-of 2026-11-03 [--body V08_ROST_BODY] [--summary SUMMARY.json]

``--body`` is a disc roster body the writer replays the plan on (validation; contracts read from it).
"""
from __future__ import annotations

import argparse
import collections
import copy
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT)]

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_roster_refresh as refresh  # noqa: E402

TEAM_CODES = {"LA": "LAR"}                     # nflverse -> the pack's club codes
CLUB_STATUSES = ("ACT", "INA")
RESERVE_STATUS, INJURED_STATUS = "DEV", "RES"
SPECIAL = "Special Teams"
SPECIALIST_SLOTS = {"k": ("PK", 0), "h": ("H", 0), "ls": ("LS", 0), "kr1": ("KR", 0), "kr2": ("KR", 1),
                    "pr": ("PR", 0)}
ROSTER_URL = "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2026.csv"
# 2020 CBA article 26 minimum salaries by credited seasons, the 10/14 plan's placeholder scale
MINIMUM_FLOORS = (885000, 1005000, 1075000, 1145000, 1215000, 1215000, 1215000, 1300000)
CBA_URL = ("https://nflpaweb.blob.core.windows.net/website/PDFs/CBA/"
           "March-15-2020-NFL-NFLPA-Collective-Bargaining-Agreement-Final-Executed-Copy.pdf")
QUANTUM = 40000


def club(code):
    return TEAM_CODES.get(code, code)


def latest_roster(path):
    """{gsis_id: row} keeping each player's latest week."""
    out = {}
    for row in csv.DictReader(open(path, encoding="utf-8")):
        g = row["gsis_id"]
        if g and (g not in out or int(row["week"] or 0) >= int(out[g]["week"] or 0)):
            out[g] = row
    return out


def recent_practice_squad(path):
    """{gsis} of players the roster file lists as ``DEV`` (practice squad) in the week before a club's latest week: the
    two practice-squad players a club elevates for a game are listed as active that week, and are not on its 53."""
    status = collections.defaultdict(dict)
    for row in csv.DictReader(open(path, encoding="utf-8")):
        if row["gsis_id"]:
            status[row["gsis_id"]][int(row["week"] or 0)] = row["status"]
    out = set()
    for g, weeks in status.items():
        latest = max(weeks)
        if weeks.get(latest) in CLUB_STATUSES and weeks.get(latest - 1) == RESERVE_STATUS:
            out.add(g)
    return out


def latest_charts(path):
    """({club: [entries]}, {club: dt}, {club: {dt: [entries]}}) from each club's newest chart and every snapshot."""
    newest, entries = {}, collections.defaultdict(list)
    history = collections.defaultdict(lambda: collections.defaultdict(list))
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for row in rows:
        team = club(row["team"])
        newest[team] = max(newest.get(team, ""), row["dt"])
        history[team][row["dt"]].append(row)
    for row in rows:
        team = club(row["team"])
        if row["dt"] == newest[team]:
            entries[team].append(row)
    return entries, newest, history


HURT = ("Out", "Doubtful")
RECENT_WEEKS = 4


class Healthy:
    """Noah 11/03 (healthy starters): an active player who is healthy in his club's latest injury report but was Out
    or Doubtful in the last RECENT_WEEKS weeks takes back the rank he held at his slot on the club's last chart
    before that injury streak (the chart of the day of the last game he played healthy), above the backups who
    replaced him; everyone else keeps the newest chart's order. Injured reserve stays off the ranks (the writer)."""

    def __init__(self, injuries_csv, schedule_json, history):
        self.out = collections.defaultdict(set)
        self.latest = collections.defaultdict(int)
        self.reported = collections.defaultdict(set)          # the weeks a club filed a report (not its bye)
        for row in csv.DictReader(open(injuries_csv, encoding="utf-8")):
            week = int(row["week"])
            self.latest[club(row["team"])] = max(self.latest[club(row["team"])], week)
            self.reported[club(row["team"])].add(week)
            if row["report_status"] in HURT:
                self.out[row["gsis_id"]].add(week)
        games = json.loads(Path(schedule_json).read_text(encoding="utf-8"))["games"]
        self.kickoff = {}
        for game in games:
            self.kickoff[game["week"]] = min(self.kickoff.get(game["week"], "9999"), game["date"])
        self.history = history

    def returning(self, gsis, team):
        """(first week of the streak, last week) for a player healthy now after a recent streak, else None."""
        weeks = self.out.get(gsis, set())
        latest = self.latest.get(team, 0)
        if not weeks or latest in weeks or max(weeks) < latest - RECENT_WEEKS:
            return None
        last = max(w for w in weeks if w < latest)
        first = last
        while first - 1 in weeks or (first - 2 in weeks and first - 1 not in self.reported[team]):
            first -= 1
        return first, last

    def chart_before(self, team, week):
        """The club's last chart on or before the day of week ``week - 1``'s first game (week 1: its first chart)."""
        snapshots = sorted(self.history.get(team, {}))
        if not snapshots:
            return []
        if week <= 1:
            return self.history[team][snapshots[0]]
        cutoff = self.kickoff.get(week - 1, "")
        earlier = [dt for dt in snapshots if dt[:10] <= cutoff]
        return self.history[team][earlier[-1]] if earlier else []


def slot_positions(plan_rows):
    """{(pos_grp, pos_abb): {position codes}} as the 10/14 plan mapped chart slots to record positions."""
    out = collections.defaultdict(set)
    for row in plan_rows:
        source = row.get("depth_source")
        if source and "position" in row["fields"]:
            out[(source["pos_grp"], source["pos_abb"])].add(row["fields"]["position"])
    return out


def best_entry(entries, position, mapping):
    """The chart entry that orders a player of ``position``, with its sort key, or (None, None)."""
    def key(e):
        late = e["pos_grp"] == SPECIAL and e["pos_abb"] == "LS"      # the long snapper sorts after every centre
        return (late, int(e["pos_rank"]), int(e["pos_slot"]))
    own = [e for e in entries if position in mapping.get((e["pos_grp"], e["pos_abb"]), ())]
    if not own:
        own = [e for e in entries if e["pos_grp"] != SPECIAL]
    if not own:
        return None, None
    chosen = min(own, key=key)
    return chosen, key(chosen)


def depth_source(entry):
    keys = ("dt", "team", "player_name", "espn_id", "gsis_id", "pos_grp_id", "pos_grp", "pos_id", "pos_name",
            "pos_abb", "pos_slot", "pos_rank")
    out = {k: entry[k] for k in keys}
    out["team"] = club(entry["team"])
    return out


def placeholder(index, name, years_pro, as_of):
    floor = MINIMUM_FLOORS[min(max(years_pro, 1), len(MINIMUM_FLOORS)) - 1]
    value = math.ceil(floor / QUANTUM)
    fields = {"contract_bonus": 0, "contract_length": 1, "contract_remaining": 1, "contract_type": 2,
              "contract_value": value}
    return {"as_of": as_of, "fields": fields,
            "fit": {"charge_quantum_dollars": QUANTUM, "errors_dollars": [value * QUANTUM - floor],
                    "evidence": "DESIGN", "fields": dict(fields),
                    "meaning": "smallest representable one-year charge at or above minimum; years pro proxies "
                               "credited seasons",
                    "minimum_floor_dollars": floor, "represented_cap_dollars": [value * QUANTUM],
                    "source_cap_dollars": [floor]},
            "index": index, "name": name,
            "rule": "DESIGN: one-year minimum accounting placeholder for a newly owned unsigned record, using existing "
                    "franchise-economy scale and experience proxy; not an observed NFL contract",
            "source": CBA_URL}


def reorder_healthy(team, picks, by_index, healthy, mapping, moves):
    """Re-rank ``picks`` ({index: (position, entry, key)}) for players back from a recent injury: each takes his
    pre-injury rank in his pre-injury slot's list; the players at that slot below him move down one."""
    slots = collections.defaultdict(list)            # (position, pos_grp, pos_abb) -> [index] in 11/03 rank order
    slot_no = {}
    for index, (position, entry, key) in sorted(picks.items(), key=lambda kv: (kv[1][2] or (9,), kv[0])):
        if entry is not None:
            slots[(position, entry["pos_grp"], entry["pos_abb"])].append(index)
            slot_no[(position, entry["pos_grp"], entry["pos_abb"])] = int(entry["pos_slot"])
    returned = []
    for index, (position, entry, key) in picks.items():
        row = by_index[index]
        streak = healthy.returning(row["gsis_id"], team)
        if streak is None:
            continue
        before = [e for e in healthy.chart_before(team, streak[0]) if e["gsis_id"] == row["gsis_id"]]
        old_entry, old_key = best_entry(before, position, mapping)
        if old_entry is None or (key is not None and old_key[1] >= key[1]):
            continue                                   # not ranked higher before the injury: the newest chart stands
        returned.append((old_key, index, old_entry, streak))
    changed = set()
    for old_key, index, old_entry, streak in sorted(returned):
        position = picks[index][0]
        for slot, members in slots.items():
            if index in members:
                members.remove(index)
                changed.add(slot)
        target = (position, old_entry["pos_grp"], old_entry["pos_abb"])
        slot_no.setdefault(target, int(old_entry["pos_slot"]))
        members = slots[target]
        members.insert(min(int(old_entry["pos_rank"]) - 1, len(members)), index)
        changed.add(target)
        row = by_index[index]
        moves.append(f"{team} {row['first']} {row['last']}: {old_entry['pos_abb']}{old_entry['pos_rank']} as on "
                     f"{old_entry['dt'][:10]} (Out or Doubtful weeks {streak[0]}-{streak[1]}, healthy in week "
                     f"{healthy.latest.get(team)}'s report)")
    # only the slots a returning player left or joined are renumbered (1..n in their new order), so on a paired
    # position the returner takes his old place and the player who replaced him becomes the top backup again
    for slot in changed:
        position, grp, abb = slot
        for rank, index in enumerate(slots[slot], 1):
            old_position, entry, key = picks[index]
            picks[index] = (old_position, entry, (abb == "LS" and grp == SPECIAL, rank, slot_no[slot]))


def update(document, roster_csv, charts_csv, as_of, body=None, injuries_csv=None, schedule_json=None):
    doc = copy.deepcopy(document)
    plan = doc["roster_refresh"]
    rows = plan["players"]
    by_gsis = {r["gsis_id"]: r for r in rows}
    by_index = {r["index"]: r for r in rows}
    fresh = latest_roster(roster_csv)
    charts, newest, history = latest_charts(charts_csv)
    healthy = Healthy(injuries_csv, schedule_json, history) if injuries_csv else None
    healthy_moves = []
    mapping = slot_positions(rows)
    records = None
    if body is not None:
        document_ = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
        records = {p.index: p for p in document_.by_pool("primary")}
    teams = {t["team"]: t for t in plan["teams"]}
    before = {t["team"]: (list(t["active"]), list(t["reserves"]), dict(t["specialists"])) for t in plan["teams"]}
    old_rows = {r["index"]: (r["team"], r["status"], dict(r["fields"])) for r in rows}
    week = max(int(r["week"] or 0) for r in fresh.values())
    club_week = collections.defaultdict(int)
    for n in fresh.values():
        if n["status"] in CLUB_STATUSES:
            club_week[club(n["team"])] = max(club_week[club(n["team"])], int(n["week"] or 0))
    stale = []
    # statuses and clubs
    for row in rows:
        n = fresh.get(row["gsis_id"])
        if n is None:
            continue                                   # an unsigned pool player the roster file does not list
        status, team = n["status"], club(n["team"])
        if status in CLUB_STATUSES + (RESERVE_STATUS,) and int(n["week"] or 0) < club_week[team]:
            # off his club's weekly roster since that week (ATL 11/03: Cooper Rush last listed in week 6, his #13
            # now Andy Dalton's): no longer on the club
            stale.append(f"{team} {row['first']} {row['last']} (last listed week {n['week']} {status})")
            status = "CUT"
        if status not in CLUB_STATUSES + (RESERVE_STATUS, INJURED_STATUS):
            team = team if status == "CUT" else row["team"]
        row.update(status=status, team=team, source=ROSTER_URL, source_as_of=as_of, source_week=n["week"])
        if status in CLUB_STATUSES + (RESERVE_STATUS, INJURED_STATUS) and n["jersey_number"].isdigit():
            row["fields"]["jersey"] = int(n["jersey_number"])
    # membership
    legacy_free = [i for i in plan["free_agents"] if i not in by_index]          # retail free agents, no 2026 row
    active = {t: [] for t in teams}
    reserves = {t: [] for t in teams}
    for row in rows:
        if row["status"] in CLUB_STATUSES and row["team"] in teams:
            active[row["team"]].append(row["index"])
        elif row["status"] == RESERVE_STATUS and row["team"] in teams:
            reserves[row["team"]].append(row["index"])
    for t in teams:
        old = before[t][1]
        reserves[t].sort(key=lambda i: (i not in old, old.index(i) if i in old else 0, i))
        reserves[t] = reserves[t][:12]
    # A club the roster file lists with more than 53 active and inactive players (JAX 11/03: 54; most clubs 54 to 56, the
    # two practice-squad players elevated for the game count as active) keeps 53. b780 rst2 (Q41): once every rostered
    # player has a record this fires for most clubs, so it no longer drops an injured starter: the player who goes is
    # never one the chart lists first at his slot (a kicker, punter or long snapper counts) while another can go, then the
    # deepest chart rank (a player the chart does not list is the deepest), a player who was on the club's practice squad
    # (an elevated one is not on the 53) and an inactive player first. He goes to the club's practice squad, else to the
    # free agents.
    over_53 = []
    elevated = recent_practice_squad(roster_csv)
    for t in teams:
        while len(active[t]) > 53:
            listed = collections.defaultdict(lambda: (99, 99))
            for e in charts.get(t, []):
                if e["pos_grp"] != SPECIAL or e["pos_abb"] in ("PK", "P", "LS"):
                    listed[e["gsis_id"]] = min(listed[e["gsis_id"]], (int(e["pos_rank"]), int(e["pos_slot"])))
            # the club's own kicker, punter and long snapper (nflverse position) are never trimmed while another can go,
            # the first of each by chart rank (a club's chart can lack its snapper: LAR 11/03)
            keepers = set()
            for kind in ("K", "P", "LS"):
                kind_players = [i for i in active[t] if fresh.get(by_index[i]["gsis_id"], {}).get("position") == kind]
                if kind_players:
                    keepers.add(min(kind_players, key=lambda i: (listed[by_index[i]["gsis_id"]], i)))
            drop = max(active[t], key=lambda i: (i not in keepers and listed[by_index[i]["gsis_id"]][0] != 1,
                                                 by_index[i]["gsis_id"] in elevated,
                                                 listed[by_index[i]["gsis_id"]][0], by_index[i]["status"] == "INA",
                                                 listed[by_index[i]["gsis_id"]][1], i))
            active[t].remove(drop)
            if len(reserves[t]) < 12:
                reserves[t].append(drop)
            over_53.append(f"{t} {by_index[drop]['first']} {by_index[drop]['last']} "
                           f"({'practice squad' if drop in reserves[t] else 'free agents'})")
    # A club must kick and punt. When its sourced kicker or punter has no record (MIA 11/03: Zane Gonzalez) and no
    # recorded one is on the club, the club's previous kicker or punter stays if he is unsigned now (Riley Patterson).
    kept_specialists = []
    for t, team in teams.items():
        for position in (1, 2):
            if any(by_index[i]["fields"].get("position") == position for i in active[t]):
                continue
            previous = [i for i in before[t][0] if by_index[i]["fields"].get("position") == position
                        and by_index[i]["status"] not in CLUB_STATUSES + (RESERVE_STATUS, INJURED_STATUS)]
            sourced = [e["player_name"] for e in charts.get(t, []) if e["pos_grp"] == SPECIAL
                       and e["pos_abb"] == ("PK" if position == 1 else "P") and e["gsis_id"] not in by_gsis]
            if previous and len(active[t]) < 53:
                index = previous[0]
                active[t].append(index)
                kept_specialists.append(f"{t} {'K' if position == 1 else 'P'}: {by_index[index]['first']} "
                                        f"{by_index[index]['last']} stays (now {by_index[index]['status']}); "
                                        f"the sourced {'/'.join(sourced) or '?'} has no record")
    owned = {i for t in teams for i in active[t] + reserves[t]}
    injured = {r["index"] for r in rows if r["status"] == INJURED_STATUS and r["team"] in teams}
    old_free = [i for i in plan["free_agents"] if i in by_index]
    free = [i for i in old_free if i not in owned and i not in injured]
    free += sorted(r["index"] for r in rows if r["index"] not in owned and r["index"] not in injured
                   and r["index"] not in set(free))
    plan["free_agents"] = legacy_free + free
    # depth charts and specialists
    chart_rows, fallback_roles = {}, []
    for t, team in teams.items():
        entries = collections.defaultdict(list)
        for e in charts.get(t, []):
            entries[e["gsis_id"]].append(e)
        chains = collections.defaultdict(list)
        picks = {}
        for index in active[t]:
            row = by_index[index]
            position = row["fields"].get("position")
            if position is None and records is not None:
                position = records[index].record.get("position")
                row["fields"]["position"] = position
            chosen, key = best_entry(entries.get(row["gsis_id"], []), position, mapping)
            if key is None and fresh.get(row["gsis_id"], {}).get("position") == "LS":
                key = (True, 98, 98)        # b780 rst2 (Q39): a long snapper the chart does not list: after every centre
            row["depth_source"] = depth_source(chosen) if chosen else None
            picks[index] = (position, chosen, key)
        if healthy is not None:
            reorder_healthy(t, picks, by_index, healthy, mapping, healthy_moves)
        for index, (position, chosen, key) in picks.items():
            old = old_rows[index][2]
            unlisted = (2, 9, old.get("depth_rank", 7), old.get("depth_side", 7), index)
            chains[position].append(((int(key[0]),) + key[1:] + (index,) if key else unlisted, index))
        ordered = {}
        for position, members in chains.items():
            members.sort()
            ordered[position] = [index for _key, index in members]
            if position == 12:
                # the long snapper is the second centre (the SPECIAL LS view reads C rank row 1), as on 10/14
                snappers = [index for key, index in members if key[0] == 1]
                rest = [index for key, index in members if key[0] != 1]
                ordered[position] = rest[:1] + snappers + rest[1:]
            for order, index in enumerate(ordered[position]):
                rank, side = refresh.native_depth_pair(order)
                by_index[index]["fields"].update(depth_rank=rank, depth_side=side)
        specialists = {}
        for role, (abb, nth) in SPECIALIST_SLOTS.items():
            listed = sorted((int(e["pos_rank"]), e["gsis_id"]) for e in charts.get(t, [])
                            if e["pos_grp"] == SPECIAL and e["pos_abb"] == abb)
            on_club = [by_gsis[g]["index"] for _r, g in listed if g in by_gsis and by_gsis[g]["index"] in active[t]]
            if role == "kr2":
                # the next kick returner the chart lists, else its punt returners (GB 11/03: KR2 and KR3 have no
                # record, PR2 Matthew Golden does)
                punt = sorted((int(e["pos_rank"]), e["gsis_id"]) for e in charts.get(t, [])
                              if e["pos_grp"] == SPECIAL and e["pos_abb"] == "PR")
                on_club += [by_gsis[g]["index"] for _r, g in punt
                            if g in by_gsis and by_gsis[g]["index"] in active[t]]
                on_club = [i for i in dict.fromkeys(on_club) if i != specialists.get("kr1")]
                nth = 0
            specialists[role] = on_club[nth] if len(on_club) > nth else None
        # The chart's specialist can be a player with no record or on injured reserve (LA 11/03: K1 Brandon
        # McManus has no record, K2 Blake Grupe is on IR, while Joshua Karty is on the active roster). Then the
        # club's own chart decides: its first kicker kicks, its first punter holds, and the long snapper is its last
        # centre after the starter (the SPECIAL LS view), else its last tight end.
        fallbacks = {"k": ordered.get(1, [])[:1], "h": ordered.get(2, [])[:1],
                     "ls": ordered.get(12, [])[1:2] or ordered.get(9, [])[1:][-1:]}
        for role, pick in fallbacks.items():
            if specialists[role] is None and pick:
                specialists[role] = pick[0]
                fallback_roles.append((t, role, pick[0]))
        team["active"], team["reserves"], team["specialists"] = active[t], reserves[t], specialists
        chart_rows[t] = newest.get(t)
    # contracts: a player newly on a club with no contract gets the placeholder; stale initializers go
    inits = [c for c in plan["contract_initializations"] if c["index"] in owned]
    covered = {c["index"] for c in inits}
    added_inits = []
    if records is not None:
        for index in sorted(owned - covered):
            rec = records[index].record
            row = by_index[index]
            new_record = row.get("new") and records[index].first == "****************"
            length = 0 if new_record else rec.get("contract_length")
            if length == 0:
                years = row["fields"].get("years_pro", rec.get("years_pro"))
                inits.append(placeholder(index, f"{row['first']} {row['last']}", years, as_of))
                added_inits.append(index)
    plan["contract_initializations"] = inits
    # players on clubs with no record
    unrepresented = []
    for g, n in sorted(fresh.items()):
        if g in by_gsis or n["status"] not in CLUB_STATUSES + (RESERVE_STATUS, INJURED_STATUS, "EXE"):
            continue
        reason = {"RES": "no native disc IR seed", "DEV": "no available complete squad capacity",
                  "EXE": "no available complete squad capacity"}.get(n["status"],
                                                                     "no record (no vacant record is used)")
        unrepresented.append({"gsis_id": g, "name": n["full_name"], "reason": reason, "source": ROSTER_URL,
                              "status": n["status"], "team": club(n["team"])})
    plan["unrepresented"] = unrepresented
    plan["as_of"] = as_of
    plan["depth_as_of"] = max(chart_rows.values())
    summary = diff(before, old_rows, plan, by_index, chart_rows, added_inits, week)
    summary["healthy_starters"] = healthy_moves
    summary["over_53_in_the_source"] = over_53
    summary["off_the_weekly_roster"] = stale
    summary["kicker_or_punter_kept"] = kept_specialists
    summary["specialists_from_the_club_chart"] = [
        f"{t} {role}: {by_index[i]['first']} {by_index[i]['last']}" for t, role, i in fallback_roles]
    return doc, summary


def diff(before, old_rows, plan, by_index, chart_rows, added_inits, week):
    name = lambda i: f"{by_index[i]['first']} {by_index[i]['last']}" if i in by_index else f"#{i}"  # noqa: E731
    clubs = {}
    for team in plan["teams"]:
        t = team["team"]
        old_active, old_res, old_spec = before[t]
        new_active = team["active"]
        joined = [i for i in new_active if i not in old_active]
        left = [i for i in old_active if i not in new_active]
        def where(i):
            row = by_index.get(i)
            return f"{row['status']} {row['team'] or 'FA'}" if row else "?"
        def came(i):
            team_was, status_was, _f = old_rows[i]
            return f"{status_was} {team_was or 'FA'}"
        depth = []
        for i in new_active:
            if i in old_active:
                old = old_rows[i][2]
                new = by_index[i]["fields"]
                if (old.get("depth_rank"), old.get("depth_side")) != (new["depth_rank"], new["depth_side"]) \
                        and min(old.get("depth_rank", 7), new["depth_rank"]) <= 2:
                    depth.append(f"{name(i)} {rr.SCHEME_POSITION_NAMES['one_pool'][new['position']]} "
                                 f"#{old.get('depth_rank')+1 if old.get('depth_rank') is not None else '?'}"
                                 f"->#{new['depth_rank']+1}")
        spec = {k: (name(old_spec[k]) if old_spec.get(k) is not None else None,
                    name(v) if v is not None else None) for k, v in team["specialists"].items()
                if old_spec.get(k) != v}
        clubs[t] = {"chart_dt": chart_rows.get(t), "active": len(new_active), "reserves": len(team["reserves"]),
                    "joined": [f"{name(i)} (was {came(i)})" for i in joined],
                    "left": [f"{name(i)} (now {where(i)})" for i in left],
                    "injured_reserve_now": sorted(name(i) for i, (tm, st, _f) in old_rows.items()
                                                  if by_index[i]["team"] == t and by_index[i]["status"] == "RES"
                                                  and st != "RES"),
                    "specialists_changed": spec, "starter_depth_moves": depth}
    return {"roster_week": week, "clubs": clubs, "contract_placeholders_added": len(added_inits),
            "free_agents": len(plan["free_agents"]), "unrepresented": len(plan["unrepresented"]),
            "unrepresented_active": sum(u["status"] in CLUB_STATUSES for u in plan["unrepresented"])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("base")
    ap.add_argument("roster_csv")
    ap.add_argument("charts_csv")
    ap.add_argument("out")
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--body", help="a disc roster body to read contracts from and replay the plan on")
    ap.add_argument("--summary")
    ap.add_argument("--injuries", help="nflverse injuries_2026.csv: healthy starters (Noah 11/03)")
    ap.add_argument("--schedule", default=str(ROOT / "data" / "nfl_2026_schedule.json"))
    args = ap.parse_args(argv)
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    body = Path(args.body).read_bytes() if args.body else None
    doc, summary = update(base, args.roster_csv, args.charts_csv, args.as_of, body, args.injuries, args.schedule)
    text = json.dumps(doc, indent=1, ensure_ascii=True) + "\n"            # the pack document's own format
    Path(args.out).write_text(text, encoding="utf-8")
    summary["out_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if body is not None:
        out_body, receipt = refresh.apply_body(body, doc["roster_refresh"])
        summary["writer"] = {k: v for k, v in receipt.items() if k not in ("appearance",)}
        summary["writer_replays_to_itself"] = refresh.apply_body(out_body, doc["roster_refresh"])[0] == out_body
    if args.summary:
        Path(args.summary).write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "clubs"}, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
