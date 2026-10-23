"""Franchise Player Progression screen: the weekly-change record and its adapter (offline contract).

Noah, 2026-10-22: "a player progression section where you could click on it. And then it would show
you your roster and just week by week how much a player has progressed." Job pg1 (progression tuning,
``b778_pg1_REPORT.md``) reshapes *how* ratings move but found that retail NFL 2K5 has **no lasting
weekly in-season progression** (weekly prep 0x2AC4E0/0x2AB840 is a per-game bonus gone by the
Preseason), so nothing exists yet to snapshot. This module is the **adapter** the screen and the
week-advance hook both call: it defines a provisional weekly-change record, the fixed save-resident
bytes that hold it, and the pure-Python codec. The native screen (a Front Office row + descriptor +
draw/input) and the native week-advance capture hook are the **final wiring** (see below).

Record (provisional v1)
-----------------------
For each user-controlled team the record stores the roster's **overall per week**, one byte per
roster slot per week: ``overall[week][slot]``, ``week 0`` = the franchise's opening roster, ``week
w >= 1`` = the roster after the w-th regular-season advance. The screen draws the game's own current
overall from the live roster and the per-week change as ``overall[w] - overall[w-1]`` (and key
ratings the same way, below). Storing absolutes (not deltas) means the display never drifts and the
record is robust to a re-run of the week step.

* ``TEAM_SLOTS`` = 65 (the game's roster-record slot count, ``rr.TEAM_SLOTS``).
* ``WEEK_SLOTS`` = 18 (week 0 baseline + weeks 1..17).
* one record = 65 x 18 bytes of overall (0..100, clamped) = 1,170 bytes, prefixed by a 12-byte
  header (magic ``b"PPRG"``, version, base year, team index, week count), 4-byte aligned: 1,184 B.

Key ratings: the screen also shows "key ratings" week by week. They are *not* stored (the record is
overall only, to stay small and native-friendly); the adapter exposes ``KEY_RATINGS`` -- a fixed,
position-independent three-rating selection (``speed``, ``pass_accuracy``, ``strength``) that the
native hook samples with the same absolute-overall encoding if the coordinator later wants them.
This is a provisional choice flagged for Noah below.

Save-resident placement (provisional)
-------------------------------------
The record lives in a fixed, zero-in-real-saves region so the save **stays 720,044 bytes** (the
retail-sized format) and an old save (all zeros there) is read as "no record". The provisional host
is ``PROGRESSION_REGION`` (see constant), a large all-zero span inside the roster arena's free-agent
tail observed in three real franchise saves; its ownership by the arena allocator is a HYPOTHESIS the
emulator must confirm before this ships (it is not the final wiring; see below). The codec and
old-save behaviour are proved offline regardless of the host address.

Final wiring (deferred, for the coordinator / pg1)
--------------------------------------------------
1. **Native week-advance hook**: where the game advances ``S_WEEK`` (season block +0x05, the
   ``FUN_000c5800`` field) it must also snapshot the user team's 65 overalls into the record. The
   game's overall is the executable's own weighted formula (``nfl2k5_roster_records.overall`` is an
   estimate only), so the hook must be native; it writes ``overall[week][slot]`` for each slot.
2. **Native screen**: a Front Office row + descriptor + draw/input that reads the record and the live
   roster and lists position, name, current overall and the per-week change, in the game's own style
   (the Coach's Desk Practice row in ``nfl2k5_franchise_practice.py`` and the Player Card honors page
   are the closest precedents).
3. **Host confirmation**: prove in the emulator that ``PROGRESSION_REGION`` is never written by the
   arena when free agents join/leave across seasons; if it is, move the record to a late-owner
   read-only allocator region instead.
"""

from __future__ import annotations

import struct
from typing import Mapping

from . import nfl2k5_roster_records as rr

SCHEMA = "nfl2k5_player_progression/v1"
SCREEN_SCHEMA = "nfl2k5_player_progression/screen-v1"
OWNER = "nfl2k5_player_progression"
TEAM_SLOTS = rr.TEAM_SLOTS                    # 65
WEEK_SLOTS = 18                               # week 0 baseline + weeks 1..17
MAGIC = b"PPRG"
HEADER = struct.Struct("<4sBHBH")             # magic, version, base year (u16), team index, week count
HEADER_SIZE = HEADER.size                     # 10
OVERALLS_OFFSET = (HEADER_SIZE + 3) & ~3      # 12: the 65x18 table begins here
RECORD_SIZE = (OVERALLS_OFFSET + TEAM_SLOTS * WEEK_SLOTS + 3) & ~3    # 1,184
assert OVERALLS_OFFSET + TEAM_SLOTS * WEEK_SLOTS <= RECORD_SIZE

# Provisional save host (file-relative byte offset) and its size.  Verified all-zero in three real
# franchise saves (b778/pc2 myNFL3 and sv1 exports) and large enough for one record; ownership is a
# HYPOTHESIS until the emulator confirms the arena never reuses it.  See the final-wiring note.
PROGRESSION_REGION = 0x8FCF3
PROGRESSION_REGION_SIZE = RECORD_SIZE

VERSION = 1
MAX_OVERALL = 100

# Position-independent "key ratings" the screen can also chart (provisional; overall is the shipped
# record).  Picked from ``RATING_BYTE_ORDER`` so the native hook can read them at fixed offsets.
KEY_RATINGS = ("speed", "pass_accuracy", "strength")


class ProgressionError(ValueError):
    """The weekly-change record cannot be read or written here."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProgressionError(message)


def empty_record(base_year: int, team_index: int) -> bytes:
    """A fresh, all-zero record with the header written (0 = "not yet captured" overall)."""
    _require(0 <= base_year <= 0xFFFF, "base year out of range")
    _require(0 <= team_index < 32, "team index out of range")
    buf = bytearray(RECORD_SIZE)
    HEADER.pack_into(buf, 0, MAGIC, VERSION, base_year, team_index, 0)
    return bytes(buf)


def header_of(record: bytes) -> dict[str, int]:
    _require(len(record) == RECORD_SIZE, "wrong record size")
    magic, version, base_year, team_index, week_count = HEADER.unpack_from(record, 0)
    _require(magic == MAGIC, "not a player-progression record")
    _require(version == VERSION, "unknown record version")
    _require(week_count <= WEEK_SLOTS, "week count exceeds the record")
    return {"base_year": base_year, "team_index": team_index, "week_count": week_count}


def is_present(record: bytes) -> bool:
    """True when the record has been written at least once (magic present)."""
    return len(record) == RECORD_SIZE and record[:4] == MAGIC


def decode_weeks(record: bytes) -> list[list[int]]:
    """week -> 65 overalls (0 = never captured)."""
    header = header_of(record)
    weeks = []
    for week in range(WEEK_SLOTS):
        base = OVERALLS_OFFSET + week * TEAM_SLOTS
        weeks.append(list(record[base:base + TEAM_SLOTS]))
    return weeks


def encode_weeks(weeks: list[list[int]], *, base_year: int, team_index: int) -> bytes:
    """Serialize 65-wide, up to 18-week overall columns; 0 = not captured."""
    _require(len(weeks) <= WEEK_SLOTS, "too many weeks")
    buf = bytearray(empty_record(base_year, team_index))
    week_count = 0
    for week, column in enumerate(weeks):
        _require(len(column) == TEAM_SLOTS, f"week {week} is not {TEAM_SLOTS} slots wide")
        base = OVERALLS_OFFSET + week * TEAM_SLOTS
        for slot, overall in enumerate(column):
            _require(type(overall) is int and 0 <= overall <= MAX_OVERALL, "overall out of range")
            buf[base + slot] = overall
        if any(column):
            week_count = week + 1
    HEADER.pack_into(buf, 0, MAGIC, VERSION, base_year, team_index, week_count)
    return bytes(buf)


def _region_offset(payload: bytes, offset: int) -> int:
    _require(0 <= offset and offset + RECORD_SIZE <= len(payload), "record region is outside the save")
    return offset


def read_history(payload: bytes, *, offset: int = PROGRESSION_REGION) -> dict[str, object]:
    """The week-by-week overalls for the record at ``offset``, or an empty history on an old save.

    An old save (all zeros at the region) is *not* an error: it returns ``has_record=False`` with an
    empty ``weeks`` list, so the screen can show the roster with no history and the save still loads.
    """
    at = _region_offset(payload, offset)
    raw = payload[at:at + RECORD_SIZE]
    if not is_present(raw):
        return {"has_record": False, "weeks": [], "header": None}
    return {"has_record": True, "weeks": decode_weeks(raw), "header": header_of(raw)}


def capture_week(payload: bytes, *, team_index: int, base_year: int, week: int,
                 overalls: list[int], offset: int = PROGRESSION_REGION) -> tuple[bytes, dict[str, object]]:
    """Write one week's 65 overalls into the record, keeping prior weeks, and return the new save.

    ``week`` is 0-based (0 = the franchise's opening roster, w >= 1 = after the w-th advance). The save
    stays the same size; only the record region changes. Idempotent: writing the same week twice with
    the same values is a no-op.
    """
    _require(0 <= week < WEEK_SLOTS, "week out of range")
    at = _region_offset(payload, offset)
    current = payload[at:at + RECORD_SIZE]
    if is_present(current):
        weeks = decode_weeks(current)
        _require(header_of(current)["team_index"] == team_index, "record belongs to another team")
    else:
        _require(not any(current), "record region is neither empty nor a progression record")
        weeks = [[0] * TEAM_SLOTS for _ in range(WEEK_SLOTS)]
    weeks[week] = list(overalls)
    record = encode_weeks(weeks, base_year=base_year, team_index=team_index)
    buf = bytearray(payload)
    buf[at:at + RECORD_SIZE] = record
    result = bytes(buf)
    _require(len(result) == len(payload), "save size changed")
    changed = sum(1 for a, b in zip(payload, result) if a != b)
    return result, {"owner": OWNER, "schema": SCHEMA, "week": week, "team_index": team_index,
                    "changed_bytes": changed, "save_growth": 0,
                    "weeks_recorded": header_of(record)["week_count"]}


def plan_rows(weeks: list[list[int]]) -> list[dict[str, object]]:
    """A screen-ready row per roster slot: opening overall and one signed change per week.

    ``weekly_changes[w-1]`` is week ``w`` minus week ``w-1``; it is ``None`` when either week was
    not captured, so the screen can keep the week columns aligned instead of compressing gaps.
    """
    _require(weeks and all(len(w) == TEAM_SLOTS for w in weeks), "weeks are not 65-wide")
    rows = []
    for slot in range(TEAM_SLOTS):
        baseline = weeks[0][slot]
        changes = []
        for week in range(1, len(weeks)):
            previous, current = weeks[week - 1][slot], weeks[week][slot]
            changes.append(current - previous if previous and current else None)
        rows.append({"slot": slot, "opening_overall": baseline, "weekly_changes": changes})
    return rows


def screen_rows(weeks: list[list[int]],
                roster: list[Mapping[str, object]]) -> list[dict[str, object]]:
    """Join the weekly overall table with the live roster for the Progression screen.

    ``roster`` rows come from the live team record and must carry ``slot``, ``position`` and
    ``name``. The result is the screen contract (``SCREEN_SCHEMA``): position, name, opening
    overall, current overall (the latest captured week) and each captured week's signed change.
    Slots without a captured week stay at 0 so the screen can show "no history yet"; an old save
    (``read_history`` returns no weeks) is read as one all-zero week.
    """
    if not weeks:
        weeks = [[0] * TEAM_SLOTS]
    _require(all(len(w) == TEAM_SLOTS for w in weeks), "weeks are not 65-wide")
    plan = {row["slot"]: row for row in plan_rows(weeks)}
    rows: list[dict[str, object]] = []
    seen: set[int] = set()
    for entry in roster:
        _require({"slot", "position", "name"} <= set(entry), "roster entry needs slot, position and name")
        slot = entry["slot"]
        _require(type(slot) is int and 0 <= slot < TEAM_SLOTS, "roster slot out of range")
        _require(slot not in seen, "duplicate roster slot")
        seen.add(slot)
        current = 0
        for column in weeks:
            if column[slot]:
                current = column[slot]
        base = plan[slot]
        rows.append({"slot": slot, "position": str(entry["position"]), "name": str(entry["name"]),
                     "opening_overall": base["opening_overall"], "current_overall": current,
                     "weekly_changes": list(base["weekly_changes"])})
    return rows


__all__ = [
    "HEADER", "HEADER_SIZE", "KEY_RATINGS", "MAGIC", "MAX_OVERALL", "OWNER", "OVERALLS_OFFSET",
    "PROGRESSION_REGION", "PROGRESSION_REGION_SIZE", "ProgressionError", "RECORD_SIZE", "SCHEMA",
    "SCREEN_SCHEMA", "TEAM_SLOTS", "VERSION", "WEEK_SLOTS", "capture_week", "decode_weeks",
    "empty_record", "encode_weeks", "header_of", "is_present", "plan_rows", "read_history",
    "screen_rows",
]
