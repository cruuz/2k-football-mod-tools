"""Franchise Player Progress screen: the weekly snapshot record and the screen contract.

Noah, 2026-10-22: "a player progression section where you could click on it. And then it would
show you your roster and just week by week how much a player has progressed." This module defines
the save-resident record that the native week-advance capture (``nfl2k5_player_progress_screen``)
writes and the native Front Office Player Progress screen reads. The module is pure Python so the
record can be built, read and tested without an executable.

Record (``PPG2`` v1), 5,232 bytes in a fixed, all-zero tail of the roster arena
------------------------------------------------------------------------------
The record is at file offset ``RECORD_FILE_OFFSET`` of ``SAVEGAME.DAT`` (720,044 bytes), which is
the roster object plus ``RECORD_RUNTIME_DELTA`` in memory. It stays inside the existing arena, so
the save size never changes and an old save (all zeros there) reads as "no record" and still
loads. The 5,232-byte record fits the 5,453-byte zero run observed in real franchise saves.

**The host is a HYPOTHESIS that failed its runtime check.** b778-pg2's emulator wrote the record and
the Front Office stopped responding to the Player Progress row; a control run with only the row
visibility patch opens it. The live game uses the tail while those screens are open. Use a versioned
franchise footer or an owned arena reserve (native save/load hooks) before enabling the snapshot.

Header (32 bytes): magic ``PPG2``, version, flags, season year, team index, week, reserved.
Each of the 65 roster slots (80 bytes, in the team's pointer-list order):

===============  ===========================================================================
``+0x00``        identity: u16 pbp_id, u8 position, u8 jersey (7-bit field)
``+0x04``        season-start overall
``+0x05``        previous-week overall (end of the last completed week)
``+0x06``        flags: 1 identity, 2 baseline, 4 previous, 8 last-week
``+0x08``        28 season-start ratings, player record offsets ``0x36..0x51``
``+0x24``        28 previous-week ratings
``+0x40``        14 bytes: 28 four-bit signed last-week rating changes (low nibble first)
``+0x4E``        last-week overall change, signed byte
===============  ===========================================================================

The three snapshots are: **baseline** (regular-season week 0, after the offseason), **previous**
(the end of the week before the last completed week) and the **live** player record. The screen
shows ``Previously`` = baseline, ``Currently`` = live, ``Change`` = live - baseline (season), and a
toggle switches ``Change`` to ``Last Week`` = live - previous (or the stored four-bit changes).
The last-week changes are clamped to ``-7..7`` because the weekly progression owner moves ratings
by at most a few points; larger offseason movement never reaches this field.
"""

from __future__ import annotations

import struct
from typing import Iterable, Mapping, Sequence

SCHEMA = "nfl2k5_player_progression/v2"
SCREEN_SCHEMA = "nfl2k5_player_progression/screen-v2"
OWNER = "nfl2k5_player_progression"
TEAM_SLOTS = 65
RATING_OFFSET = 0x36
RATING_COUNT = 28
MAX_OVERALL = 100

MAGIC = b"PPG2"
VERSION = 1
HEADER = struct.Struct("<4sBBHBBH20s")       # magic, version, flags, year, team, week, reserved, reserved
HEADER_SIZE = HEADER.size                    # 32
SLOT_SIZE = 80
RECORD_SIZE = HEADER_SIZE + TEAM_SLOTS * SLOT_SIZE   # 5,232
assert HEADER_SIZE == 32 and RECORD_SIZE == 5232

# Fixed save host: a real-save zero run starting at file 0x8FCF4; the runtime address is
# [0xB72918] + RECORD_RUNTIME_DELTA (the roster object is at file 0x320).
RECORD_FILE_OFFSET = 0x8FCF4
RECORD_RUNTIME_DELTA = RECORD_FILE_OFFSET - 0x320   # 0x8F9D4
SAVE_SIZE = 720_044

FLAG_IDENTITY = 1
FLAG_BASELINE = 2
FLAG_PREVIOUS = 4
FLAG_LAST = 8
HEADER_BASELINE = 3          # native baseline sets bits 0+1 (baseline present, previous present)
HEADER_LAST = 4              # native week advance adds bit 2 (last-week snapshot present)

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


def _clamp4(value: int) -> int:
    return -8 if value < -8 else 7 if value > 7 else value


def _pack4(values: Iterable[int]) -> bytes:
    values = list(values)
    _require(len(values) == RATING_COUNT, "28 four-bit values are needed")
    out = bytearray(14)
    for index, value in enumerate(values):
        _require(type(value) is int and -8 <= value <= 7, "four-bit change out of range")
        out[index // 2] |= (value & 0xF) << (4 * (index & 1))
    return bytes(out)


def _unpack4(raw: bytes) -> list[int]:
    _require(len(raw) == 14, "14 packed bytes are needed")
    out = []
    for index in range(RATING_COUNT):
        value = (raw[index // 2] >> (4 * (index & 1))) & 0xF
        out.append(value - 16 if value >= 8 else value)
    return out


def empty_record(*, year: int = 0, team: int = 0, week: int = 0) -> bytes:
    _require(0 <= year <= 0xFFFF and 0 <= team <= 0xFF and 0 <= week <= 0xFF, "header field out of range")
    buf = bytearray(RECORD_SIZE)
    HEADER.pack_into(buf, 0, MAGIC, VERSION, 0, year, team, week, 0, bytes(20))
    return bytes(buf)


def is_present(record: bytes) -> bool:
    return len(record) == RECORD_SIZE and record[:4] == MAGIC


def decode_header(record: bytes) -> dict[str, int]:
    _require(len(record) == RECORD_SIZE, "wrong record size")
    magic, version, flags, year, team, week, _reserved, _tail = HEADER.unpack_from(record, 0)
    _require(magic == MAGIC, "not a player-progression record")
    _require(version == VERSION, "unknown record version")
    return {"magic": magic, "version": version, "flags": flags, "year": year, "team": team, "week": week}


def read_record(payload: bytes, *, offset: int = RECORD_FILE_OFFSET) -> dict[str, object]:
    """Read the record from a save; an old save (zeros) returns ``present=False``."""
    _require(0 <= offset and offset + RECORD_SIZE <= len(payload), "record region is outside the save")
    raw = payload[offset:offset + RECORD_SIZE]
    if not is_present(raw):
        return {"present": False, "header": None, "slots": []}
    header = decode_header(raw)
    slots = []
    for slot in range(TEAM_SLOTS):
        at = HEADER_SIZE + slot * SLOT_SIZE
        identity, base_overall, prev_overall, flags = struct.unpack_from("<IBBb", raw, at + 0x04)
        # struct B B b: flags is the fourth byte but the layout has identity u32 at +0, then three bytes.
        # Re-read explicitly to avoid an endianness/size mistake.
        identity = struct.unpack_from("<I", raw, at)[0]
        base_overall = raw[at + 4]
        prev_overall = raw[at + 5]
        flags = raw[at + 6]
        baseline = list(raw[at + 0x08:at + 0x08 + RATING_COUNT])
        previous = list(raw[at + 0x24:at + 0x24 + RATING_COUNT])
        last_deltas = _unpack4(raw[at + 0x40:at + 0x40 + 14])
        last_overall = struct.unpack_from("<b", raw, at + 0x4E)[0]
        slots.append({"identity": identity, "baseline_overall": base_overall,
                      "previous_overall": prev_overall, "flags": flags, "baseline": baseline,
                      "previous": previous, "last_deltas": last_deltas, "last_overall": last_overall})
    return {"present": True, "header": header, "slots": slots}


def encode_record(header: Mapping[str, int], slots: Sequence[Mapping[str, object]]) -> bytes:
    _require(len(slots) == TEAM_SLOTS, "65 roster slots are needed")
    buf = bytearray(RECORD_SIZE)
    HEADER.pack_into(buf, 0, MAGIC, VERSION, int(header.get("flags", 0)) & 0xFF,
                     int(header.get("year", 0)) & 0xFFFF, int(header.get("team", 0)) & 0xFF,
                     int(header.get("week", 0)) & 0xFF, 0, bytes(20))
    for slot, entry in enumerate(slots):
        at = HEADER_SIZE + slot * SLOT_SIZE
        struct.pack_into("<IBBb", buf, at, int(entry["identity"]) & 0xFFFFFFFF,
                         int(entry["baseline_overall"]) & 0xFF, int(entry["previous_overall"]) & 0xFF,
                         int(entry["flags"]) & 0xFF)
        buf[at + 0x08:at + 0x08 + RATING_COUNT] = bytes(int(v) & 0xFF for v in entry["baseline"])
        buf[at + 0x24:at + 0x24 + RATING_COUNT] = bytes(int(v) & 0xFF for v in entry["previous"])
        buf[at + 0x40:at + 0x40 + 14] = _pack4(entry["last_deltas"])
        struct.pack_into("<b", buf, at + 0x4E, _clamp4(int(entry.get("last_overall", 0))))
    return bytes(buf)


def write_record(payload: bytes, record: bytes, *, offset: int = RECORD_FILE_OFFSET) -> tuple[bytes, dict[str, object]]:
    _require(len(record) == RECORD_SIZE, "wrong record size")
    _require(0 <= offset and offset + RECORD_SIZE <= len(payload), "record region is outside the save")
    _require(len(payload) == SAVE_SIZE, "not a retail-sized franchise save")
    buf = bytearray(payload)
    buf[offset:offset + RECORD_SIZE] = record
    result = bytes(buf)
    _require(len(result) == len(payload), "save size changed")
    return result, {"owner": OWNER, "schema": SCHEMA, "save_growth": 0,
                    "changed_bytes": sum(1 for a, b in zip(payload, result) if a != b)}


def baseline(payload: bytes, players: Sequence[Mapping[str, object]], *, year: int, team: int,
             offset: int = RECORD_FILE_OFFSET) -> bytes:
    """Write a new season-start baseline for the user team's roster (slot order)."""
    _require(len(players) == TEAM_SLOTS, "65 players are needed")
    slots = []
    for player in players:
        ratings = _ratings(player)
        slots.append({"identity": _identity(player), "baseline_overall": int(player["overall"]) & 0xFF,
                      "previous_overall": int(player["overall"]) & 0xFF, "flags": 7,
                      "baseline": ratings, "previous": ratings, "last_deltas": [0] * RATING_COUNT,
                      "last_overall": 0})
    record = encode_record({"flags": HEADER_BASELINE, "year": year, "team": team, "week": 0}, slots)
    return write_record(payload, record, offset=offset)[0]


def advance_week(payload: bytes, players: Sequence[Mapping[str, object]], *, week: int,
                 offset: int = RECORD_FILE_OFFSET) -> bytes:
    """Capture the end of week ``week`` (the new week counter minus one) for the user team."""
    _require(len(players) == TEAM_SLOTS, "65 players are needed")
    current = read_record(payload, offset=offset)
    if not current["present"] or not (current["header"]["flags"] & HEADER_BASELINE):
        return baseline(payload, players, year=int(current["header"]["year"]) if current["present"] else 0,
                        team=int(current["header"]["team"]) if current["present"] else 0, offset=offset)
    header = dict(current["header"])
    slots = list(current["slots"])
    for slot, player in enumerate(players):
        entry = dict(slots[slot])
        identity = _identity(player)
        ratings = _ratings(player)
        overall = int(player["overall"]) & 0xFF
        if entry["identity"] != identity or not (entry["flags"] & FLAG_BASELINE):
            entry.update({"identity": identity, "baseline_overall": overall, "previous_overall": overall,
                          "flags": FLAG_IDENTITY | FLAG_BASELINE | FLAG_PREVIOUS,
                          "baseline": ratings, "previous": ratings,
                          "last_deltas": [0] * RATING_COUNT, "last_overall": 0})
        else:
            last = [_clamp4(a - b) for a, b in zip(ratings, entry["previous"])]
            entry.update({"last_deltas": last, "last_overall": _clamp4(overall - entry["previous_overall"]),
                          "previous": ratings, "previous_overall": overall,
                          "flags": entry["flags"] | FLAG_IDENTITY | FLAG_PREVIOUS | FLAG_LAST})
        slots[slot] = entry
    header.update({"flags": HEADER_BASELINE | HEADER_LAST, "week": week & 0xFF})
    return write_record(payload, encode_record(header, slots), offset=offset)[0]


def screen_rows(record: Mapping[str, object], roster: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """The screen contract: one row per live roster player with season and last-week changes.

    ``roster`` entries carry ``slot`` and the player fields. The live ``current`` and ``overall``
    values are supplied by the caller; this function joins them with the stored snapshots.
    """
    _require(record.get("present") is True, "no snapshot record")
    slots = record["slots"]
    rows = []
    for entry in roster:
        slot = int(entry["slot"])
        _require(0 <= slot < TEAM_SLOTS, "roster slot out of range")
        stored = slots[slot]
        identity_ok = stored["identity"] == _identity(entry)
        current = _ratings(entry)
        overall = int(entry["overall"]) & 0xFF
        if not identity_ok or not (stored["flags"] & FLAG_BASELINE):
            rows.append({"slot": slot, "identity": identity_ok, "season": [0] * RATING_COUNT,
                         "last_week": [0] * RATING_COUNT, "season_overall": 0, "last_overall": 0,
                         "baseline": [0] * RATING_COUNT, "baseline_overall": 0})
            continue
        season = [a - b for a, b in zip(current, stored["baseline"])]
        last = stored["last_deltas"] if stored["flags"] & FLAG_LAST else [0] * RATING_COUNT
        rows.append({"slot": slot, "identity": True, "season": season, "last_week": last,
                     "season_overall": overall - stored["baseline_overall"],
                     "last_overall": stored["last_overall"] if stored["flags"] & FLAG_LAST else 0,
                     "baseline": list(stored["baseline"]), "baseline_overall": stored["baseline_overall"]})
    return rows


__all__ = ["FLAG_BASELINE", "FLAG_IDENTITY", "FLAG_LAST", "FLAG_PREVIOUS", "HEADER_BASELINE",
           "HEADER_LAST", "MAGIC", "OWNER", "ProgressionError", "RATING_COUNT", "RATING_OFFSET",
           "RECORD_FILE_OFFSET", "RECORD_RUNTIME_DELTA", "RECORD_SIZE", "ROW_MAP", "SAVE_SIZE",
           "SCHEMA", "SCREEN_SCHEMA", "SLOT_SIZE", "TEAM_SLOTS", "VERSION", "advance_week", "baseline",
           "decode_header", "empty_record", "encode_record", "is_present", "read_record", "screen_rows",
           "write_record"]
