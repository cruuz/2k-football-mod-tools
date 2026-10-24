"""Franchise Player Progress screen: the weekly snapshot record and the screen contract.

Noah, 2026-10-22: "a player progression section where you could click on it. And then it would
show you your roster and just week by week how much a player has progressed." This module defines
the versioned franchise footer that the native week-advance capture
(``nfl2k5_player_progress_screen``) writes and the native Front Office Player Progress screen
reads. The module is pure Python so the record can be built, read and tested without an executable.

Footer (``PPGF0001``) and record (``PPG3`` v1)
----------------------------------------------
The footer follows the complete native franchise container (all four retail blocks) and, when the
MyCareer footer is present, follows that too. It is part of the same signed ``SAVEGAME.DAT``; the
native save transaction writes and signs it. An old save without the footer reads as "no record"
and is never modified. The footer is fixed size (``FOOTER_SIZE``), so the save size only depends
on the native arena geometry and whether the MyCareer block is present:

===============  ============================================================
native container  size with the Player Progress footer
===============  ============================================================
720,044         754,364
720,172 (career) 754,492
724,140         758,460
724,268 (career) 758,588
847,020         881,340
847,148 (career) 881,468
===============  ============================================================

Footer header (32 bytes): magic ``PPGF0001``, u16 version, u16 header size, u32 record size,
then reserved zero bytes. The record follows at +32.

Record header (32 bytes): magic ``PPG3``, version, flags, u16 season year, u8 team index,
u8 last completed week, u8 stored week count, u8 ring head (next write), 20 reserved bytes.

Each of the 65 roster slots (527 bytes, team pointer-list order):

===============  ===========================================================================
``+0x00``        identity: u16 pbp_id, u8 position, u8 jersey (7-bit field)
``+0x04``        flags: 1 identity, 2 baseline
``+0x05``        season-start overall
``+0x06``        28 season-start ratings, player record offsets ``0x36..0x51``
``+0x22``        ``HISTORY_WEEKS`` snapshots, 29 bytes each: 28 ratings then the overall
===============  ===========================================================================

A snapshot is written after the user team's game (the game-end call site 0x1353FC, after the
second club's stat merge) for the week that was just played; the week setter at the end of the week only
establishes the season baseline. Slots are keyed by player identity, so a depth-chart
reorder does not move a player's history. The ring keeps the most recent 17 weeks (a regular
season). The screen's change row can show the season change
(week 0) or the change since any stored week, selected with the toggle; ``Previously`` shows the
same week's ratings and ``Currently`` is the live rating.

The footer is outside every native block: the arena, season and front-office offsets do not move,
so old saves and the capacity arena grow path are untouched.
"""

from __future__ import annotations

import struct
from typing import Iterable, Mapping, Sequence

SCHEMA = "nfl2k5_player_progression/v3"
SCREEN_SCHEMA = "nfl2k5_player_progression/screen-v3"
OWNER = "nfl2k5_player_progression"
TEAM_SLOTS = 65
RATING_OFFSET = 0x36
RATING_COUNT = 28
MAX_OVERALL = 100
HISTORY_WEEKS = 17

RECORD_MAGIC = b"PPG3"
VERSION = 1
RECORD_HEADER = struct.Struct("<4sBBHBBBB20s")   # magic, version, flags, year, team, week, count, head, reserved
RECORD_HEADER_SIZE = RECORD_HEADER.size           # 32
SNAPSHOT_SIZE = RATING_COUNT + 1                  # 28 ratings + overall
SLOT_SIZE = 4 + 1 + 1 + RATING_COUNT + HISTORY_WEEKS * SNAPSHOT_SIZE   # 527
RECORD_SIZE = RECORD_HEADER_SIZE + TEAM_SLOTS * SLOT_SIZE              # 34,287

FOOTER_MAGIC = b"PPGF0001"
FOOTER_VERSION = 1
FOOTER_HEADER = struct.Struct("<8sHHI4I")         # magic, version, header size, record size, 4 reserved dwords
FOOTER_HEADER_SIZE = FOOTER_HEADER.size           # 32
FOOTER_SIZE = (FOOTER_HEADER_SIZE + RECORD_SIZE + 15) & ~15   # 34,320
assert FOOTER_HEADER_SIZE == 32 and RECORD_SIZE == 34287 and FOOTER_SIZE == 34320
assert SNAPSHOT_SIZE == 29 and SLOT_SIZE == 527

FLAG_IDENTITY = 1
FLAG_BASELINE = 2
HEADER_BASELINE = 1
HEADER_HISTORY = 2

# Native geometry: the native save size before any footer for each supported arena.
RETAIL_SAVE_SIZE = 720_044
RESERVE_SAVE_SIZE = 724_140
CAPACITY_SAVE_SIZE = 847_020
MYCAREER_FOOTER_SIZE = 128
NATIVE_SAVE_SIZES = (RETAIL_SAVE_SIZE, RESERVE_SAVE_SIZE, CAPACITY_SAVE_SIZE)
SAVE_SIZES = tuple(size + footer for size in NATIVE_SAVE_SIZES
                   for footer in (FOOTER_SIZE, MYCAREER_FOOTER_SIZE + FOOTER_SIZE))
PPG_SAVE_SIZES = tuple(size + FOOTER_SIZE for size in NATIVE_SAVE_SIZES)
PPG_CAREER_SAVE_SIZES = tuple(size + MYCAREER_FOOTER_SIZE + FOOTER_SIZE for size in NATIVE_SAVE_SIZES)

# The screen's attribute columns are the position-page group base ([list record + 0x64]) times 26
# plus the row; these are the player-record offsets each row reads (retail getters 0x365160..).
ROW_MAP = bytes.fromhex(
    "003842434c36373c3d393b4f443f474145464048493e514e503a"   # group 0 (QB)
    "004a3a504c36373c3d393b4238434f443f474145464048493e51"   # group 1
    "003a4a504c36373c3d393b4238434f443f474145464048493e51"   # group 2
    "00443f36373c3d393b4238434f474145464048493e514e504c3a"   # group 3
)
assert len(ROW_MAP) == 4 * 26


class ProgressionError(ValueError):
    """The weekly snapshot record cannot be read or written here."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProgressionError(message)


def _identity(player: Mapping[str, object]) -> int:
    pbp = int(player["pbp_id"]) & 0xFFFF
    position = int(player["position"]) & 0xFF
    jersey = int(player["jersey"]) & 0x7F
    return pbp | position << 16 | jersey << 24


def _ratings(player: Mapping[str, object]) -> list[int]:
    values = player.get("ratings")
    _require(isinstance(values, Sequence) and len(values) == RATING_COUNT, "player needs 28 ratings")
    for value in values:
        _require(type(value) is int and 0 <= value <= 100, "rating out of range")
    return list(values)


def footer_start(payload: bytes) -> int | None:
    """Offset of a valid Player Progress footer, or ``None`` for every native save."""
    if len(payload) < FOOTER_SIZE:
        return None
    at = len(payload) - FOOTER_SIZE
    if payload[at:at + 8] != FOOTER_MAGIC:
        return None
    magic, version, header_size, record_size, *_ = FOOTER_HEADER.unpack_from(payload, at)
    if (magic, version, header_size, record_size) != (FOOTER_MAGIC, FOOTER_VERSION,
                                                      FOOTER_HEADER_SIZE, RECORD_SIZE):
        return None
    return at


def read_footer(payload: bytes) -> dict[str, object]:
    """Read a footer; an old native save returns ``present=False``."""
    at = footer_start(payload)
    if at is None:
        return {"present": False, "header": None, "slots": [], "footer_offset": None}
    record = payload[at + FOOTER_HEADER_SIZE:at + FOOTER_HEADER_SIZE + RECORD_SIZE]
    return {**read_record(record), "footer_offset": at}


def empty_footer(*, year: int = 0, team: int = 0) -> bytes:
    _require(0 <= year <= 0xFFFF and 0 <= team <= 0xFF, "header field out of range")
    record = bytearray(RECORD_SIZE)
    RECORD_HEADER.pack_into(record, 0, RECORD_MAGIC, VERSION, 0, year, team, 0, 0, 0, bytes(20))
    return _wrap(bytes(record))


def _wrap(record: bytes) -> bytes:
    _require(len(record) == RECORD_SIZE and record[:4] == RECORD_MAGIC, "wrong record")
    footer = bytearray(FOOTER_HEADER_SIZE + RECORD_SIZE)
    FOOTER_HEADER.pack_into(footer, 0, FOOTER_MAGIC, FOOTER_VERSION, FOOTER_HEADER_SIZE,
                            RECORD_SIZE, 0, 0, 0, 0)
    footer[FOOTER_HEADER_SIZE:] = record
    return bytes(footer).ljust(FOOTER_SIZE, b"\0")


def read_record(record: bytes) -> dict[str, object]:
    _require(len(record) == RECORD_SIZE, "wrong record size")
    magic, version, flags, year, team, week, count, head, _reserved = RECORD_HEADER.unpack_from(record, 0)
    if magic != RECORD_MAGIC or version != VERSION:
        return {"present": False, "header": None, "slots": []}
    _require(count <= HISTORY_WEEKS and head < HISTORY_WEEKS, "history ring is outside its bounds")
    slots = []
    for slot in range(TEAM_SLOTS):
        at = RECORD_HEADER_SIZE + slot * SLOT_SIZE
        identity, slot_flags, base_overall = struct.unpack_from("<IBB", record, at)
        baseline = list(record[at + 6:at + 6 + RATING_COUNT])
        snapshots = []
        for index in range(HISTORY_WEEKS):
            snap = at + 0x22 + index * SNAPSHOT_SIZE
            snapshots.append({"ratings": list(record[snap:snap + RATING_COUNT]),
                              "overall": record[snap + RATING_COUNT]})
        slots.append({"identity": identity, "flags": slot_flags, "baseline_overall": base_overall,
                      "baseline": baseline, "snapshots": snapshots})
    return {"present": True,
            "header": {"magic": magic, "version": version, "flags": flags, "year": year, "team": team,
                       "week": week, "count": count, "head": head},
            "slots": slots}


def encode_record(header: Mapping[str, int], slots: Sequence[Mapping[str, object]]) -> bytes:
    _require(len(slots) == TEAM_SLOTS, "65 roster slots are needed")
    buf = bytearray(RECORD_SIZE)
    RECORD_HEADER.pack_into(buf, 0, RECORD_MAGIC, VERSION, int(header.get("flags", 0)) & 0xFF,
                            int(header.get("year", 0)) & 0xFFFF, int(header.get("team", 0)) & 0xFF,
                            int(header.get("week", 0)) & 0xFF, int(header.get("count", 0)) & 0xFF,
                            int(header.get("head", 0)) & 0xFF, bytes(20))
    for slot, entry in enumerate(slots):
        at = RECORD_HEADER_SIZE + slot * SLOT_SIZE
        struct.pack_into("<IBB", buf, at, int(entry["identity"]) & 0xFFFFFFFF,
                         int(entry.get("flags", 0)) & 0xFF, int(entry.get("baseline_overall", 0)) & 0xFF)
        buf[at + 6:at + 6 + RATING_COUNT] = bytes(int(v) & 0xFF for v in entry["baseline"])
        snapshots = entry.get("snapshots") or [{"ratings": [0] * RATING_COUNT, "overall": 0}] * HISTORY_WEEKS
        _require(len(snapshots) == HISTORY_WEEKS, "17 weekly snapshots are needed")
        for index, snapshot in enumerate(snapshots):
            snap = at + 0x22 + index * SNAPSHOT_SIZE
            buf[snap:snap + RATING_COUNT] = bytes(int(v) & 0xFF for v in snapshot["ratings"])
            buf[snap + RATING_COUNT] = int(snapshot.get("overall", 0)) & 0xFF
    return bytes(buf)


def _slot_for(player: Mapping[str, object], entry: Mapping[str, object] | None) -> dict[str, object]:
    ratings = _ratings(player)
    overall = int(player["overall"]) & 0xFF
    snapshots = [{"ratings": [0] * RATING_COUNT, "overall": 0} for _ in range(HISTORY_WEEKS)]
    return {"identity": _identity(player), "flags": FLAG_IDENTITY | FLAG_BASELINE,
            "baseline_overall": overall, "baseline": ratings, "snapshots": snapshots}


def baseline(players: Sequence[Mapping[str, object]], *, year: int, team: int) -> bytes:
    """A new season-start baseline for the user team's roster (slot order)."""
    _require(len(players) == TEAM_SLOTS, "65 players are needed")
    _require(0 <= year <= 0xFFFF and 0 <= team <= 0xFF, "header field out of range")
    slots = [_slot_for(player, None) for player in players]
    return _wrap(encode_record({"flags": HEADER_BASELINE, "year": year, "team": team, "week": 0,
                                "count": 0, "head": 0}, slots))


def advance_week(footer: bytes, players: Sequence[Mapping[str, object]], *, week: int,
                 team: int | None = None, year: int | None = None) -> bytes:
    """Append the end of ``week`` for the user team; start (or reset) a baseline when needed."""
    _require(len(players) == TEAM_SLOTS, "65 players are needed")
    _require(len(footer) == FOOTER_SIZE, "wrong footer size")
    current = read_footer(footer)
    if not current["present"]:
        return baseline(players, year=int(year or 0), team=int(team or 0))
    header = dict(current["header"])
    if year is not None and header["year"] != year:
        return baseline(players, year=year, team=int(team if team is not None else header["team"]))
    if team is not None and header["team"] != team:
        return baseline(players, year=header["year"], team=team)
    slots = [dict(entry) for entry in current["slots"]]
    head = header["head"]
    count = header["count"]
    for slot, player in enumerate(players):
        entry = slots[slot]
        identity = _identity(player)
        ratings = _ratings(player)
        overall = int(player["overall"]) & 0xFF
        if entry["identity"] != identity or not (entry["flags"] & FLAG_BASELINE):
            slots[slot] = _slot_for(player, None)
            continue
        snapshots = [dict(snap) for snap in entry["snapshots"]]
        snapshots[head] = {"ratings": ratings, "overall": overall}
        entry["snapshots"] = snapshots
        slots[slot] = entry
    header.update({"flags": header["flags"] | HEADER_HISTORY, "week": week & 0xFF,
                   "head": (head + 1) % HISTORY_WEEKS, "count": min(count + 1, HISTORY_WEEKS)})
    return _wrap(encode_record(header, slots))


def snapshot_index(record: Mapping[str, object], weeks_ago: int) -> int | None:
    """Ring index for ``weeks_ago`` weeks before the last completed week (1 = last week)."""
    _require(record.get("present") is True, "no snapshot record")
    header = record["header"]
    if weeks_ago < 1 or weeks_ago > int(header["count"]):
        return None
    return (int(header["head"]) - weeks_ago) % HISTORY_WEEKS


def screen_rows(record: Mapping[str, object], roster: Sequence[Mapping[str, object]], *,
                weeks_ago: int = 1) -> list[dict[str, object]]:
    """The screen contract: one row per live roster player with season and selected-week changes.

    ``weeks_ago=0`` is the season baseline; 1 is the last completed week; up to 17 weeks are kept.
    ``roster`` entries carry ``slot`` and the live player fields.
    """
    _require(record.get("present") is True, "no snapshot record")
    header = record["header"]
    _require(0 <= weeks_ago <= HISTORY_WEEKS, "history week out of range")
    if weeks_ago > int(header["count"]):
        weeks_ago = int(header["count"])
    index = (int(header["head"]) - weeks_ago) % HISTORY_WEEKS if weeks_ago else None
    rows = []
    for entry in roster:
        slot = int(entry["slot"])
        _require(0 <= slot < TEAM_SLOTS, "roster slot out of range")
        stored = record["slots"][slot]
        identity_ok = stored["identity"] == _identity(entry)
        current = _ratings(entry)
        overall = int(entry["overall"]) & 0xFF
        empty = {"slot": slot, "identity": identity_ok, "season": [0] * RATING_COUNT,
                 "last_week": [0] * RATING_COUNT, "season_overall": 0, "last_overall": 0,
                 "baseline": [0] * RATING_COUNT, "baseline_overall": 0,
                 "previous": [0] * RATING_COUNT, "previous_overall": 0, "change": [0] * RATING_COUNT,
                 "change_overall": 0, "weeks_ago": weeks_ago}
        if not identity_ok or not (stored["flags"] & FLAG_BASELINE):
            rows.append(empty)
            continue
        baseline = list(stored["baseline"])
        if weeks_ago:
            snapshot = stored["snapshots"][index]
            shown = list(snapshot["ratings"])
            shown_overall = snapshot["overall"]
            if weeks_ago < int(header["count"]):
                before = stored["snapshots"][(index - 1) % HISTORY_WEEKS]
                previous, previous_overall = list(before["ratings"]), before["overall"]
            else:
                previous, previous_overall = baseline, stored["baseline_overall"]
        else:
            shown, shown_overall = current, overall
            previous, previous_overall = baseline, stored["baseline_overall"]
        season = [a - b for a, b in zip(current, baseline)]
        change = [a - b for a, b in zip(shown, previous)]
        rows.append({"slot": slot, "identity": True, "season": season,
                     "last_week": change if weeks_ago == 1 else [0] * RATING_COUNT,
                     "season_overall": overall - stored["baseline_overall"],
                     "last_overall": (shown_overall - previous_overall) if weeks_ago == 1 else 0,
                     "baseline": baseline, "baseline_overall": stored["baseline_overall"],
                     "previous": previous, "previous_overall": previous_overall,
                     "change": change, "change_overall": shown_overall - previous_overall,
                     "shown": shown, "shown_overall": shown_overall, "weeks_ago": weeks_ago})
    return rows


def append_footer(payload: bytes, footer: bytes) -> tuple[bytes, dict[str, object]]:
    """Copy-only external helper: append a footer to a native save (the game writes its own)."""
    _require(footer_start(payload) is None, "the save already has a Player Progress footer")
    _require(len(footer) == FOOTER_SIZE, "wrong footer size")
    native = len(payload)
    team = int(read_footer(footer)["header"]["team"]) if read_footer(footer)["present"] else 0
    result = bytes(payload) + bytes(footer)
    _require(footer_start(result) is not None, "footer does not read back")
    return result, {"owner": OWNER, "schema": SCHEMA, "footer_offset": native, "footer_size": FOOTER_SIZE,
                    "native_bytes_preserved": native, "team": team,
                    "file_growth": len(result) - len(payload)}


def strip_footer(payload: bytes) -> tuple[bytes, bytes | None]:
    at = footer_start(payload)
    if at is None:
        return bytes(payload), None
    return bytes(payload[:at]), bytes(payload[at:])


__all__ = ["FLAG_BASELINE", "FLAG_IDENTITY", "FOOTER_HEADER_SIZE", "FOOTER_MAGIC", "FOOTER_SIZE",
           "FOOTER_VERSION", "HEADER_BASELINE", "HEADER_HISTORY", "HISTORY_WEEKS", "MAX_OVERALL",
           "MYCAREER_FOOTER_SIZE", "NATIVE_SAVE_SIZES", "OWNER", "ProgressionError", "RATING_COUNT",
           "RATING_OFFSET", "RECORD_HEADER_SIZE", "RECORD_MAGIC", "RECORD_SIZE", "ROW_MAP",
           "SAVE_SIZES", "PPG_SAVE_SIZES", "PPG_CAREER_SAVE_SIZES", "SCHEMA", "SCREEN_SCHEMA", "SLOT_SIZE", "SNAPSHOT_SIZE", "TEAM_SLOTS", "VERSION",
           "advance_week", "append_footer", "baseline", "empty_footer", "encode_record", "footer_start",
           "read_footer", "read_record", "screen_rows", "snapshot_index", "strip_footer"]
