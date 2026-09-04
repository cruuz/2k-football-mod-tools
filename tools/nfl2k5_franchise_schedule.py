#!/usr/bin/env python3
"""Read and rewrite the ESPN NFL 2K5 franchise regular-season schedule template (disc data, copy-only).

Where the schedule lives (retail disc, pack ``vc_53450030/0``):

* The ROST resource is outer entry 5 of pack 0 at pack offset 0x392800: a 0x20-byte wrapper
  (``'ROST'``, stored size 0x90F60) and a 0x90F60-byte body.  The body starts with an inner
  ``'ROST'`` tag at +0x2C and a self-relative pointer at +0x34 to the pool header at +0x60.
* The pool header is a list of (count, offset) u32 pairs.  ``FUN_000c0500`` turns every offset
  field into a pointer with ``ptr = &field + offset - 1`` (constants 4*i-1); the writer
  ``FUN_000c0730`` inverts it.  Pair +0x28/+0x2C is the regular-season schedule: count 0x100,
  offset 0x72749 -> pack 0x404FD4 = 256 records of 8 bytes,
  ``[type=0][home][away][month][day][year-2000][hour12 (0=12)][minute]`` in week order, the real
  2004 season (Colts at Patriots, Thu Sep 9 2004 9:00 PM first).  Teams are the game's 32 ordinals
  (alphabetical by nickname, 0 = 49ers .. 31 = Vikings).
* ``FUN_002bf270`` (regular-season generator) copies the template into the 22x17 runtime grid.
  Season 0 keeps the template's teams, order and dates.  Later seasons keep the template's shape,
  remap teams through the division/finish tables, pick a marquee game per week and re-date the
  whole season from Thanksgiving (``2000 + 4 + season``).
* The week of each record is decided by ``FUN_001c1a90`` on consecutive records: a new week
  starts when the new game is Thu/Fri/Sat/Sun and the previous game was Sun/Mon/Tue/Wed (or when
  they are 7+ days apart).  ``split_weeks`` below is that rule; ``encode_schedule`` orders each
  week Thu, Fri, Sat, Sun, Mon, Tue, Wed so a Wednesday opener (Sep 9 2026) stays in Week 1.
* The loader copies the pool (body from +0x60 to the end of the wrapper) into a fixed 0x91000
  buffer (``FUN_000c2180``), and the franchise save writes that whole buffer back
  (``SAVEGAME.DAT`` holds the same blob with the pool header at +0x40), so the body size must not
  change.  The body ends with 8,026 zero bytes after the last name string (ROST+0x8F026 ..
  ROST+0x90F80); a 272-record template (2,176 bytes) is written there at ROST+0x8F028 and the
  header pair is pointed at it (count 0x110, offset 0x8EF9D).  The retail 256 records stay in
  place, unreferenced, so a copy can always be told from retail.

An 18-week template also needs the executable patch in ``mod_editor.core.nfl2k5_season_length``
(grid row 17 is the Wild Card row in retail code); ``apply --xbe-copy`` applies it, and without it
the tool refuses any template that decodes to more than 17 weeks unless ``--force``.

**Preseason.** Retail generates the preseason at random (``FUN_002bec20``: 4 games per team over
5 weeks, 13/13/13/13/12 pairings, Thanksgiving-minus-119-days dates).  The ``preseason`` group of
``nfl2k5_season_length`` (module ``nfl2k5_preseason``) rewrites that generator to copy a template
instead, which this tool writes straight after the regular-season records in the same tail:
``[u32 'PR'<<16 | count][count x 8-byte records]`` at ``TAIL_PLACEMENT + 8 * regular_count`` (the
rewritten generator finds it through the pool pair: ``records + count * 8``).  ``encode_preseason``
builds it from ``doc["preseason"]`` (real 2026: Hall of Fame Game + three 16-game weeks, 49
records, 3 games per team, the HOF pair 4).  Without the block the rewritten generator leaves the
preseason empty (four idle weeks); without the XBE group the block is inert data.

Read-only unless ``apply`` is given a copy; the retail extraction directory is never written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import struct
import sys
import os
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nfl2k5_franchise_schedule_probe import TEAM_NAMES  # noqa: E402

RETAIL_EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "retail-extraction"))   # never written; developer machines only
PACK_REL = Path("vc_53450030/0")
RETAIL_PACK_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
PACK_ROST_OFFSET = 0x392800
ROST_TAG = b"ROST"
ROST_BODY_SIZE = 0x90F60
ROST_WRAPPER = 0x20
ROST_OUTER_SIZE = ROST_WRAPPER + ROST_BODY_SIZE          # 0x90F80
POOL_LINK_OFFSET = 0x34                                  # self-relative pointer to the pool header
SCHEDULE_COUNT_FIELD = 0x28
SCHEDULE_PTR_FIELD = 0x2C
RECORD_SIZE = 8
RETAIL_TEMPLATE_REL = 0x727D4                            # ROST-relative
RETAIL_TEMPLATE_COUNT = 256
RETAIL_TEMPLATE_SHA256 = "6b15ab091aacac867f6663c10aa907b32508f4377f57ca87ce19db81566e7f59"
RETAIL_HEADER_SHA256 = "5654d8a38e4b5bb1ae3b6aaffbfc47d97871a704ef74ca9227fa167c7c853a2c"
TAIL_FREE_REL = 0x8F026                                  # first byte after the last name string
TAIL_PLACEMENT_REL = 0x8F028                             # 8-aligned
GRID_SLOTS = 17
MAX_WEEKS_RETAIL = 17
PRESEASON_TAG = 0x5052                                   # 'PR' in the high half of the block header
PRESEASON_MAX_GAMES = 4 * GRID_SLOTS                     # four preseason rows in the grid
PRESEASON_WEEKS = 4                                      # HOF week + three league-wide weeks
TEAM_COUNT = 32
DAY_ORDER = {3: 0, 4: 1, 5: 2, 6: 3, 0: 4, 1: 5, 2: 6}   # Mon=0..Sun=6 -> Thu first, Wed last
LATE_DAYS = {3, 4, 5, 6}                                 # Thu Fri Sat Sun
EARLY_DAYS = {6, 0, 1, 2}                                # Sun Mon Tue Wed


class ScheduleError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScheduleError(message)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def u32(payload: bytes, offset: int) -> int:
    return struct.unpack_from("<I", payload, offset)[0]


# -- ROST pool header -----------------------------------------------------------------------------

def pool_header(payload: bytes, rost: int) -> int:
    """Absolute offset of the pool header of the ROST blob whose tag sits at ``rost``."""
    require(payload[rost: rost + 4] == ROST_TAG, f"no ROST tag at 0x{rost:x}")
    require(payload[rost + 0x2C: rost + 0x30] == ROST_TAG, f"no inner ROST tag at 0x{rost + 0x2C:x}")
    link = u32(payload, rost + POOL_LINK_OFFSET)
    require(link != 0, "ROST pool link is zero")
    return rost + POOL_LINK_OFFSET + link - 1


def resolve(payload: bytes, field: int) -> int:
    """``FUN_000c0500``: an offset field resolves to ``&field + value - 1``."""
    return field + u32(payload, field) - 1


def schedule_location(payload: bytes, rost: int) -> tuple[int, int, int]:
    """(count, absolute offset of the records, pool header offset)."""
    hdr = pool_header(payload, rost)
    count = u32(payload, hdr + SCHEDULE_COUNT_FIELD)
    ptr = resolve(payload, hdr + SCHEDULE_PTR_FIELD)
    return count, ptr, hdr


def offset_for(field: int, target: int) -> int:
    return target - field + 1


# -- records --------------------------------------------------------------------------------------

def decode_record(raw: bytes) -> dict[str, Any]:
    require(len(raw) == RECORD_SIZE, "record must be 8 bytes")
    kind, home, away, month, day, yy, hour, minute = raw
    year = 2000 + yy if yy < 99 else 1900 + yy
    return {"type": kind, "home": home, "away": away, "month": month, "day": day, "year": year,
            "hour_field": hour, "minute_field": minute,
            "home_name": TEAM_NAMES[home] if home < TEAM_COUNT else f"team{home}",
            "away_name": TEAM_NAMES[away] if away < TEAM_COUNT else f"team{away}",
            "date": dt.date(year, month, day).isoformat() if 1 <= month <= 12 and 1 <= day <= 31 else None,
            "kickoff": f"{hour if hour else 12}:{minute:02d}"}


def encode_record(home: int, away: int, date: dt.date, hour12: int, minute: int, kind: int = 0) -> bytes:
    require(0 <= home < TEAM_COUNT and 0 <= away < TEAM_COUNT and home != away, "bad team ordinal")
    require(2000 <= date.year <= 2098, "year must be 2000..2098")
    require(0 <= hour12 <= 12 and 0 <= minute <= 59, "bad kickoff")
    return bytes([kind, home, away, date.month, date.day, date.year - 2000, hour12 % 12, minute])


def decode_records(payload: bytes, offset: int, count: int) -> list[dict[str, Any]]:
    out = []
    for i in range(count):
        raw = payload[offset + i * RECORD_SIZE: offset + (i + 1) * RECORD_SIZE]
        require(len(raw) == RECORD_SIZE, "schedule records run past the end of the file")
        rec = decode_record(raw)
        rec["offset"] = offset + i * RECORD_SIZE
        rec["index"] = i
        out.append(rec)
    return out


def record_date(rec: dict[str, Any]) -> dt.date:
    return dt.date(rec["year"], rec["month"], rec["day"])


def new_week(prev: dt.date, cur: dt.date) -> bool:
    """Port of FUN_001c1a90 (weekday encoding Mon=0..Sun=6, Python's)."""
    if prev == cur:
        return False
    if abs((cur - prev).days) >= 7:
        return True
    return cur.weekday() in LATE_DAYS and prev.weekday() in EARLY_DAYS


def split_weeks(records: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    weeks: list[list[dict[str, Any]]] = []
    prev = None
    for rec in records:
        cur = record_date(rec)
        if prev is None or new_week(prev, cur):
            weeks.append([])
        weeks[-1].append(rec)
        prev = cur
    return weeks


def week_summary(weeks: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for index, games in enumerate(weeks):
        playing = {g["home"] for g in games} | {g["away"] for g in games}
        byes = [TEAM_NAMES[t] for t in range(TEAM_COUNT) if t not in playing]
        dates = sorted({g["date"] for g in games})
        rows.append({"week": index + 1, "games": len(games), "first_date": dates[0], "last_date": dates[-1],
                     "byes": byes, "over_capacity": len(games) > GRID_SLOTS})
    return rows


def validate_schedule(records: Sequence[dict[str, Any]], games_per_team: int | None = None) -> dict[str, Any]:
    per_team = [0] * TEAM_COUNT
    home = [0] * TEAM_COUNT
    for rec in records:
        require(rec["home"] < TEAM_COUNT and rec["away"] < TEAM_COUNT, "team ordinal out of range")
        require(rec["home"] != rec["away"], "a team cannot play itself")
        per_team[rec["home"]] += 1
        per_team[rec["away"]] += 1
        home[rec["home"]] += 1
    weeks = split_weeks(records)
    summary = week_summary(weeks)
    require(all(not w["over_capacity"] for w in summary), f"a week has more than {GRID_SLOTS} games")
    if games_per_team is not None:
        require(set(per_team) == {games_per_team}, f"every team must play {games_per_team} games: {per_team}")
    for week in weeks:
        seen: set[int] = set()
        for g in week:
            require(g["home"] not in seen and g["away"] not in seen, "a team plays twice in one week")
            seen.update((g["home"], g["away"]))
    return {"games": len(records), "weeks": len(weeks), "games_per_team": sorted(set(per_team)),
            "home_games": sorted(set(home)), "week_table": summary}


# -- JSON schedule -> template --------------------------------------------------------------------

def encode_schedule(doc: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """The 8-byte template for ``data/nfl_<season>_schedule.json`` (tools/nfl_schedule_from_espn.py)."""
    require(doc.get("schema") == "nfl_schedule_for_2k5/v1", "unexpected schedule JSON schema")
    games = doc["games"]
    ordered = []
    for g in games:
        date = dt.date.fromisoformat(g["date"])
        ordered.append((g["week"], DAY_ORDER[date.weekday()], g.get("time_et", "13:00"), g["home"], g, date))
    ordered.sort(key=lambda t: t[:4])
    blob = bytearray()
    notes = {"am_kickoffs": [], "time_tbd": 0, "neutral_site": []}
    for _week, _day, _time, _home, g, date in ordered:
        blob += encode_record(g["home"], g["away"], date, g["hour_field"], g["minute_field"])
        if g.get("am"):
            notes["am_kickoffs"].append(f"week {g['week']} {g['away_name']} at {g['home_name']} {g['time_et']} ET "
                                        f"(stored as {g['hour_field']}:{g['minute_field']:02d}; the game prints pm)")
        if g.get("time_tbd"):
            notes["time_tbd"] += 1
        if g.get("neutral_site"):
            notes["neutral_site"].append(f"week {g['week']} {g['away_name']} at {g['home_name']} ({g.get('venue_city')})")
    records = decode_records(bytes(blob), 0, len(games))
    check = validate_schedule(records, doc["format"]["games_per_team"])
    require(check["weeks"] == doc["format"]["weeks"],
            f"template splits into {check['weeks']} weeks, the source says {doc['format']['weeks']}")
    for row, expected in zip(check["week_table"], sorted({g["week"] for g in games})):
        require(row["week"] == expected, "week numbering drifted")
    by_week = {}
    for g in games:
        by_week.setdefault(g["week"], set()).update((g["home"], g["away"]))
    for row in check["week_table"]:
        require({TEAM_NAMES[t] for t in range(TEAM_COUNT) if t not in by_week[row["week"]]} == set(row["byes"]),
                f"bye teams differ from the source in week {row['week']}")
    return bytes(blob), {"season": doc["season"], "sources": doc["sources"], "validation": check, "notes": notes,
                         "sha256": sha256(bytes(blob))}


def preseason_weeks(records: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Preseason records carry their week (0..3) in the type byte: the game's date-based week
    detector (``FUN_001c1a90``) would merge preseason weeks 1 and 2 (Saturday -> Thursday is not a
    week break to it), so the rewritten generator reads the week off the record instead."""
    weeks: list[list[dict[str, Any]]] = [[] for _ in range(PRESEASON_WEEKS)]
    for rec in records:
        require(rec["type"] < PRESEASON_WEEKS, f"preseason record week {rec['type']} is out of range")
        weeks[rec["type"]].append(rec)
    return weeks


def validate_preseason(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Shape of a preseason template: 4 weeks (type byte), week 0 = one Hall of Fame game, 3 games
    per team (the HOF pair 4), no team twice in a week, at most 17 games per week, weeks in order."""
    require(0 < len(records) <= PRESEASON_MAX_GAMES, f"preseason must hold 1..{PRESEASON_MAX_GAMES} games")
    per_team = [0] * TEAM_COUNT
    last_week = -1
    for rec in records:
        require(rec["home"] < TEAM_COUNT and rec["away"] < TEAM_COUNT and rec["home"] != rec["away"], "bad teams")
        require(rec["type"] >= last_week, "preseason records must be grouped by week in order")
        last_week = rec["type"]
        per_team[rec["home"]] += 1
        per_team[rec["away"]] += 1
    weeks = preseason_weeks(records)
    require(all(weeks), "every preseason week needs at least one game")
    summary = week_summary(weeks)
    require(all(not w["over_capacity"] for w in summary), f"a preseason week has more than {GRID_SLOTS} games")
    require(len(weeks[0]) == 1, "week 0 must be the single Hall of Fame game")
    hof = {weeks[0][0]["home"], weeks[0][0]["away"]}
    require(all(per_team[t] == (4 if t in hof else 3) for t in range(TEAM_COUNT)),
            f"every team must play 3 preseason games (the Hall of Fame pair 4): {per_team}")
    for week in weeks:
        seen: set[int] = set()
        for g in week:
            require(g["home"] not in seen and g["away"] not in seen, "a team plays twice in a preseason week")
            seen.update((g["home"], g["away"]))
        dates = [record_date(g) for g in week]
        require(max(dates) - min(dates) <= dt.timedelta(days=6), "a preseason week spans more than 7 days")
    return {"games": len(records), "weeks": len(weeks), "hall_of_fame": weeks[0][0], "week_table": summary}


def encode_preseason(doc: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """The preseason block ``[u32 header][records]`` for ``doc["preseason"]`` (None when absent)."""
    pre = doc.get("preseason")
    if not pre:
        return b"", {"games": 0}
    ordered = []
    for g in pre["games"]:
        date = dt.date.fromisoformat(g["date"])
        ordered.append((g["week"], DAY_ORDER[date.weekday()], g.get("time_et", "13:00"), g["home"], g, date))
    ordered.sort(key=lambda t: t[:4])
    blob = bytearray()
    for week, _day, _time, _home, g, date in ordered:
        blob += encode_record(g["home"], g["away"], date, g["hour_field"], g["minute_field"], kind=week)
    records = decode_records(bytes(blob), 0, len(ordered))
    check = validate_preseason(records)
    header = struct.pack("<I", (PRESEASON_TAG << 16) | len(records))
    return header + bytes(blob), {"games": len(records), "weeks": check["weeks"], "validation": check,
                                  "hall_of_fame": f"{records[0]['away_name']} at {records[0]['home_name']} {records[0]['date']}",
                                  "sha256": sha256(header + bytes(blob))}


def decode_preseason_block(payload: bytes, offset: int) -> dict[str, Any] | None:
    """The block the rewritten generator would read at ``offset`` (None when no valid header)."""
    if offset + 4 > len(payload):
        return None
    header = u32(payload, offset)
    if header >> 16 != PRESEASON_TAG:
        return None
    count = header & 0xFFFF
    if not 0 < count <= PRESEASON_MAX_GAMES or offset + 4 + count * RECORD_SIZE > len(payload):
        return None
    records = decode_records(payload, offset + 4, count)
    try:
        check = validate_preseason(records)
    except (ScheduleError, ValueError) as exc:
        return {"offset": f"0x{offset:x}", "games": count, "valid": False, "reason": str(exc)}
    return {"offset": f"0x{offset:x}", "games": count, "valid": True, "weeks": check["weeks"],
            "week_table": check["week_table"], "records": records}


# -- pack status / apply --------------------------------------------------------------------------

def looks_like_pack_rost(payload: bytes, offset: int) -> bool:
    """Is a retail-shaped ROST outer entry at ``offset``? (tag, stored size, pool link)"""
    if offset < 0 or offset + ROST_OUTER_SIZE > len(payload):
        return False
    try:
        return (payload[offset: offset + 4] == ROST_TAG
                and u32(payload, offset + 4) == ROST_BODY_SIZE
                and payload[offset + 0x2C: offset + 0x30] == ROST_TAG
                and pool_header(payload, offset) == offset + 0x60)
    except (ScheduleError, struct.error):
        return False


def locate_pack_rost(payload: bytes, *, expected: int = PACK_ROST_OFFSET) -> int | None:
    """Where the roster resource really is in this pack, or None when it is not there.

    The schedule template is a *resource*, not a byte address. Retail keeps it at outer
    entry 5 (pack offset 0x392800), and reading it there is right for every retail dump
    however the disc image around the pack is laid out. A pack somebody rebuilt can hold
    the same resource somewhere else, though, and answering "ROST stored size is not
    retail" because byte 0x392804 happens to be something else is a claim about an
    offset, not about the pack. So the retail offset is a fast path and the resource is
    searched for when it does not hold.
    """
    if looks_like_pack_rost(payload, expected):
        return expected
    position = 0
    while True:
        hit = payload.find(ROST_TAG, position)
        if hit < 0:
            return None
        if looks_like_pack_rost(payload, hit):
            return hit
        position = hit + 1


def pack_status(payload: bytes, rost: int = PACK_ROST_OFFSET) -> dict[str, Any]:
    located = locate_pack_rost(payload, expected=rost)
    relocated = located is not None and located != rost
    if located is not None:
        rost = located
    try:
        require(len(payload) >= rost + ROST_OUTER_SIZE, "pack is too short for the ROST outer entry")
        require(u32(payload, rost + 4) == ROST_BODY_SIZE, "ROST stored size is not retail")
        count, ptr, hdr = schedule_location(payload, rost)
        require(hdr == rost + 0x60, "pool header is not at ROST+0x60")
    except (ScheduleError, struct.error) as exc:
        return {"state": "foreign", "reason": str(exc)}
    retail_ptr = rost + RETAIL_TEMPLATE_REL
    retail_blob = payload[retail_ptr: retail_ptr + RETAIL_TEMPLATE_COUNT * RECORD_SIZE]
    retail_ok = sha256(retail_blob) == RETAIL_TEMPLATE_SHA256
    tail = payload[rost + TAIL_FREE_REL: rost + ROST_OUTER_SIZE]
    info: dict[str, Any] = {"rost_offset": f"0x{rost:x}", "pool_header": f"0x{hdr:x}", "schedule_count": count,
                            "schedule_offset": f"0x{ptr:x}", "retail_template_intact": retail_ok,
                            "rost_relocated": relocated, "tail_zero": not any(tail)}
    if count == RETAIL_TEMPLATE_COUNT and ptr == retail_ptr and retail_ok and not any(tail):
        info["state"] = "retail"
        info["preseason_games"] = 0
    elif ptr == rost + TAIL_PLACEMENT_REL and retail_ok and 0 < count * RECORD_SIZE <= ROST_OUTER_SIZE - TAIL_PLACEMENT_REL:
        try:
            validate_schedule(decode_records(payload, ptr, count))
            info["state"] = "applied"
            block = decode_preseason_block(payload, ptr + count * RECORD_SIZE)
            info["preseason_games"] = block["games"] if block and block["valid"] else 0
            if block and not block["valid"]:
                info["state"] = "foreign"
                info["reason"] = f"preseason block does not validate: {block['reason']}"
        except (ScheduleError, ValueError) as exc:
            info["state"] = "foreign"
            info["reason"] = f"tail template does not decode: {exc}"
    else:
        info["state"] = "foreign"
        info["reason"] = "schedule pair or template bytes are neither retail nor this tool's layout"
    return info


def apply_pack(payload: bytes, template: bytes, rost: int = PACK_ROST_OFFSET,
               preseason: bytes = b"") -> tuple[bytes, dict[str, Any]]:
    """Write the regular-season ``template`` (and, right after it, the optional ``preseason`` block
    from ``encode_preseason``) into the ROST tail of a retail pack copy; the pool pair counts only
    the regular records."""
    rost = locate_pack_rost(payload, expected=rost) or rost
    state = pack_status(payload, rost)
    require(state["state"] == "retail", f"pack ROST is {state['state']}, not retail: {state.get('reason', '')}")
    require(len(template) % RECORD_SIZE == 0 and template, "template must be whole 8-byte records")
    count = len(template) // RECORD_SIZE
    placement = rost + TAIL_PLACEMENT_REL
    require(placement + len(template) + len(preseason) <= rost + ROST_OUTER_SIZE,
            f"template of {count} records (+{len(preseason)} preseason bytes) does not fit the "
            f"{ROST_OUTER_SIZE - TAIL_PLACEMENT_REL} free tail bytes")
    validate_schedule(decode_records(template, 0, count))
    if preseason:
        block = decode_preseason_block(preseason, 0)
        require(block is not None and block["valid"], "preseason block is not a valid template block")
    hdr = rost + 0x60
    buf = bytearray(payload)
    buf[placement: placement + len(template)] = template
    buf[placement + len(template): placement + len(template) + len(preseason)] = preseason
    struct.pack_into("<I", buf, hdr + SCHEDULE_COUNT_FIELD, count)
    struct.pack_into("<I", buf, hdr + SCHEDULE_PTR_FIELD, offset_for(hdr + SCHEDULE_PTR_FIELD, placement))
    patched = bytes(buf)
    after = pack_status(patched, rost)
    require(after["state"] == "applied", f"post-apply verification failed: {after}")
    changed = [i for i in range(len(payload)) if payload[i] != patched[i]] if len(payload) < 1 << 20 else None
    return patched, {"records": count, "placement": f"0x{placement:x}", "count_field": f"0x{hdr + SCHEDULE_COUNT_FIELD:x}",
                     "preseason_games": after.get("preseason_games", 0),
                     "preseason_placement": f"0x{placement + len(template):x}" if preseason else None,
                     "offset_field": f"0x{hdr + SCHEDULE_PTR_FIELD:x}",
                     "offset_value": f"0x{offset_for(hdr + SCHEDULE_PTR_FIELD, placement):x}",
                     "changed_bytes": (len(changed) if changed is not None
                                       else 8 + sum(1 for a, b in zip(payload[placement: placement + len(template) + len(preseason)],
                                                                      template + preseason) if a != b)),
                     "status_after": after}


# -- inspect --------------------------------------------------------------------------------------

def inspect_blob(payload: bytes, rost: int, source: str) -> dict[str, Any]:
    count, ptr, hdr = schedule_location(payload, rost)
    records = decode_records(payload, ptr, count)
    check = validate_schedule(records)
    pairs = [(u32(payload, hdr + i * 8), u32(payload, hdr + i * 8 + 4)) for i in range(12)]
    block = decode_preseason_block(payload, ptr + count * RECORD_SIZE)
    return {"schema": "nfl2k5_franchise_schedule_inspect/v1", "source": source, "read_only": True,
            "rost_offset": f"0x{rost:x}", "pool_header": f"0x{hdr:x}",
            "pool_pairs_count_offset": [(c, f"0x{o:x}") for c, o in pairs],
            "schedule": {"count": count, "offset": f"0x{ptr:x}", "sha256": sha256(payload[ptr: ptr + count * RECORD_SIZE])},
            "validation": check, "games": records,
            "preseason": block if block is not None else {"games": 0, "note": "no preseason template block (retail: generated at random)"}}


def find_rost(payload: bytes) -> int:
    off = payload.find(ROST_TAG)
    while off >= 0:
        if payload[off + 0x2C: off + 0x30] == ROST_TAG:
            return off
        off = payload.find(ROST_TAG, off + 1)
    raise ScheduleError("no ROST blob with an inner tag found")


def inspect_path(path: Path, kind: str) -> dict[str, Any]:
    if kind == "pack":
        target = path / PACK_REL if path.is_dir() else path
        payload = target.read_bytes()
        report = inspect_blob(payload, PACK_ROST_OFFSET, str(target))
        report["status"] = pack_status(payload)
        report["pack_sha256_matches_retail"] = sha256(payload) == RETAIL_PACK_SHA256
        return report
    if kind == "savegame":
        payload = path.read_bytes()
        return inspect_blob(payload, find_rost(payload), str(path))
    if kind == "image":
        from nfl2k5_franchise_schedule_probe import load_franchise_from_image
        payload = load_franchise_from_image(path)
        return inspect_blob(payload, find_rost(payload), f"{path}:Franchise1/SAVEGAME.DAT")
    raise ScheduleError(f"unknown inspect kind {kind}")


# -- synthetic fixture and self-test --------------------------------------------------------------

def synthetic_pack(rost: int = 0x800, records: bytes | None = None) -> bytes:
    """A pack-shaped blob with a retail-shaped ROST outer entry at ``rost`` (retail header digest not
    reproduced; the retail 2004 template is replaced by ``records`` or a synthetic 16-game season)."""
    if records is None:
        records = synthetic_season(2004, 16, 17)
    body = bytearray(ROST_OUTER_SIZE)
    body[0:4] = ROST_TAG
    struct.pack_into("<III", body, 4, ROST_BODY_SIZE, ROST_BODY_SIZE, 0)
    body[0x2C: 0x30] = ROST_TAG
    struct.pack_into("<II", body, 0x30, 0x11, 0x2D)                     # +0x34 -> +0x60
    hdr = 0x60
    struct.pack_into("<I", body, hdr + SCHEDULE_COUNT_FIELD, len(records) // RECORD_SIZE)
    struct.pack_into("<I", body, hdr + SCHEDULE_PTR_FIELD, offset_for(hdr + SCHEDULE_PTR_FIELD, RETAIL_TEMPLATE_REL))
    body[RETAIL_TEMPLATE_REL: RETAIL_TEMPLATE_REL + len(records)] = records
    body[TAIL_FREE_REL - 0x10: TAIL_FREE_REL] = b"v\0i\0k\0i\0n\0g\0s\0\0\0"
    out = bytearray(rost + ROST_OUTER_SIZE + 0x800)
    out[rost: rost + ROST_OUTER_SIZE] = body
    return bytes(out)


def synthetic_season(year: int, games_per_team: int, weeks: int) -> bytes:
    """A circle-method season: ``weeks`` rounds of 16 pairings; ``weeks - games_per_team`` byes per team
    are made by dropping at most one pairing per week whose two teams still need a bye (Sundays,
    one Monday game per week).  Shape only: home/away counts are not balanced."""
    byes_per_team = weeks - games_per_team
    require(0 <= byes_per_team and weeks <= TEAM_COUNT - 1, "impossible synthetic season")
    teams = list(range(TEAM_COUNT))
    rounds = []
    n = TEAM_COUNT
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = teams[i], teams[n - 1 - i]
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        rounds.append(pairs)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    require(byes_per_team <= 1, "synthetic seasons support at most one bye per team")
    week_games = [list(rounds[w]) for w in range(weeks)]
    if byes_per_team == 1:
        drops = _bye_matching(week_games, 0, set(), {})
        require(drops is not None, "synthetic bye assignment failed")
        for w, pair in drops.items():
            week_games[w].remove(pair)
    sunday = dt.date(year, 9, 12)
    while sunday.weekday() != 6:
        sunday += dt.timedelta(days=1)
    blob = bytearray()
    for w, pairs in enumerate(week_games):
        date = sunday + dt.timedelta(days=7 * w)
        for i, (h, a) in enumerate(pairs):
            monday = i == len(pairs) - 1
            blob += encode_record(h, a, date + dt.timedelta(days=1 if monday else 0), 1 if i < 12 else 4, 0 if i < 12 else 15)
    return bytes(blob)


def _bye_matching(week_games, week, used, chosen):
    """One dropped pairing in each of 16 distinct weeks covering all 32 teams (depth-first search)."""
    if len(used) == TEAM_COUNT:
        return dict(chosen)
    if week >= len(week_games):
        return None
    for pair in week_games[week]:
        if pair[0] not in used and pair[1] not in used:
            chosen[week] = pair
            found = _bye_matching(week_games, week + 1, used | set(pair), chosen)
            if found is not None:
                return found
            del chosen[week]
    return _bye_matching(week_games, week + 1, used, chosen)


def self_test() -> None:
    d = decode_record(bytes([0, 21, 10, 9, 9, 4, 9, 0]))
    require(d["date"] == "2004-09-09" and d["home_name"] == "Patriots" and d["kickoff"] == "9:00", "decode")
    require(encode_record(21, 10, dt.date(2004, 9, 9), 9, 0) == bytes([0, 21, 10, 9, 9, 4, 9, 0]), "encode")
    require(encode_record(0, 1, dt.date(2027, 1, 10), 12, 30)[5:] == bytes([27, 0, 30]), "12 encodes as 0")
    wed, thu, sun, mon = (dt.date(2026, 9, d) for d in (9, 10, 13, 14))
    require(not new_week(thu, sun) and not new_week(sun, mon) and new_week(mon, dt.date(2026, 9, 17)), "detector")
    require(new_week(wed, thu), "Wed->Thu is a week break in the game (hence Wed last)")
    require(not new_week(mon, wed), "Mon->Wed stays in the week")
    require(new_week(mon, dt.date(2026, 11, 26)), "Mon->Thu (Thanksgiving) breaks")
    pack = synthetic_pack()
    require(pack_status(pack, 0x800)["state"] == "foreign", "synthetic retail-shaped pack is not retail (template differs)")
    print("NFL2K5_FRANCHISE_SCHEDULE_SELF_TEST_OK")


# -- CLI ------------------------------------------------------------------------------------------

def _refuse_retail_path(path: Path) -> None:
    resolved = path.resolve()
    require(RETAIL_EXTRACTION.resolve() not in resolved.parents and resolved != RETAIL_EXTRACTION.resolve(),
            "refusing to write inside the retail extraction; pass a copy")


def cmd_inspect(args: argparse.Namespace) -> int:
    kind = "pack" if args.pack else "savegame" if args.savegame else "image"
    path = args.pack or args.savegame or args.image
    report = inspect_path(Path(path), kind)
    if not args.games:
        report["games"] = f"{len(report['games'])} records (use --games to list)"
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    target = Path(args.pack)
    target = target / PACK_REL if target.is_dir() else target
    print(json.dumps(pack_status(target.read_bytes()), indent=1))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    pack_path = Path(args.pack_copy)
    pack_path = pack_path / PACK_REL if pack_path.is_dir() else pack_path
    _refuse_retail_path(pack_path)
    doc = json.loads(Path(args.schedule).read_text(encoding="utf-8"))
    template, info = encode_schedule(doc)
    pre_block, pre_info = (b"", {"games": 0}) if args.no_preseason else encode_preseason(doc)
    weeks = info["validation"]["weeks"]
    receipt: dict[str, Any] = {"schema": "nfl2k5_franchise_schedule_apply/v1", "schedule": str(args.schedule),
                               "template": info, "preseason": pre_info, "runtime_verified": False}
    if weeks > MAX_WEEKS_RETAIL and not args.xbe_copy and not args.force:
        raise ScheduleError(f"{weeks}-week template needs the season-length XBE patch: pass --xbe-copy "
                            "(or --force to write the pack anyway)")
    payload = pack_path.read_bytes()
    if args.dry_run:
        _patched, pack_receipt = apply_pack(payload, template, preseason=pre_block)
        receipt["pack"] = {"path": str(pack_path), "dry_run": True, **pack_receipt}
    else:
        patched, pack_receipt = apply_pack(payload, template, preseason=pre_block)
        pack_path.write_bytes(patched)
        back = pack_path.read_bytes()
        require(back == patched, "read-back after write differs")
        receipt["pack"] = {"path": str(pack_path), "sha256_before": sha256(payload), "sha256_after": sha256(back),
                           **pack_receipt}
    if args.xbe_copy:
        from mod_editor.core import nfl2k5_season_length as season
        xbe_path = Path(args.xbe_copy)
        _refuse_retail_path(xbe_path)
        groups = [g.strip() for g in args.groups.split(",") if g.strip()]
        if weeks > MAX_WEEKS_RETAIL:
            require("season_length" in groups, "an 18-week template needs the season_length group")
        if pre_block and "preseason" not in groups and not args.force:
            raise ScheduleError("a preseason block needs the preseason XBE group (or --no-preseason / --force)")
        xbe = xbe_path.read_bytes()
        patched_xbe, xbe_receipt = season.apply(xbe, groups=groups, year=args.year)
        if not args.dry_run:
            xbe_path.write_bytes(patched_xbe)
            require(xbe_path.read_bytes() == patched_xbe, "XBE read-back differs")
        receipt["xbe"] = {"path": str(xbe_path), "dry_run": bool(args.dry_run), "sha256_before": sha256(xbe),
                          "sha256_after": sha256(patched_xbe), "status_after": season.status(patched_xbe), **xbe_receipt}
    text = json.dumps(receipt, indent=1)
    if args.receipt:
        Path(args.receipt).write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text if not args.receipt else f"wrote {args.receipt}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inspect", help="dump the schedule template of a pack 0 / SAVEGAME.DAT / xemu HDD image as JSON")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pack", help="vc_53450030/0 or the extracted disc directory")
    g.add_argument("--savegame", help="extracted Franchise SAVEGAME.DAT")
    g.add_argument("--image", help="raw 8 GiB Xbox HDD image (read-only)")
    p.add_argument("--games", action="store_true", help="include every record")
    p.add_argument("--out")
    p.set_defaults(func=cmd_inspect)
    p = sub.add_parser("status", help="retail / applied / foreign for a pack 0 copy")
    p.add_argument("--pack", required=True)
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("apply", help="write a schedule JSON into a COPY of pack 0 (and optionally the year/season patch into a COPY of default.xbe)")
    p.add_argument("--pack-copy", required=True, help="copy of vc_53450030/0 (or of the extracted disc directory)")
    p.add_argument("--schedule", default=str(ROOT / "data" / "nfl_2026_schedule.json"))
    p.add_argument("--xbe-copy", help="copy of default.xbe to receive the year / calendar / season-length patch")
    p.add_argument("--year", type=int, default=2026)
    p.add_argument("--groups", default="year,calendar,season_length,playoffs_14,preseason",
                   help="XBE groups to apply (nfl2k5_season_length.GROUPS); playoffs_14 = the 2020+ 14-team bracket, "
                        "preseason = the template-driven 3-game preseason")
    p.add_argument("--no-preseason", action="store_true", help="do not write the preseason block after the template")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="write an 18-week template without the XBE patch")
    p.add_argument("--receipt")
    p.set_defaults(func=cmd_apply)
    p = sub.add_parser("self-test")
    p.set_defaults(func=lambda a: (self_test(), 0)[1])
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ScheduleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
