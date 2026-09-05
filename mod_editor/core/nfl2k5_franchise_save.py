"""ESPN NFL 2K5 franchise save (``SAVEGAME.DAT``, 720,044 bytes): everything beyond the roster arena.

A franchise save is four blocks laid end to end (offsets are file-relative):

======== ======== ============================================================================
offset   size     block
======== ======== ============================================================================
0x00000  0x2E0    settings prefix: an image of RAM 0xE5FF80..0xE60260 (sliders; ``nfl2k5_save_writer``)
0x002E0  0x91040  the roster arena: ``ROST`` wrapper (declared 0x91020), preamble at 0x300 (version 0),
                  object at 0x320, 0x91000-byte arena (``nfl2k5_roster_records`` / ``nfl2k5_save_rost``)
0x91320  0x83DC   the SEASON block: an image of RAM 0xE57776.. serialised by the routine at 0xC5310 and
                  restored by ``FUN_000c5800`` (pointers replaced by indices), then the league stat
                  tables ``FUN_001349a0`` consumes, then a 0x80-byte tail
0x996FC  0x165B0  the FRONT-OFFICE block restored by ``FUN_002d0ce0`` (mode 2 only): draft/standing
                  orders, the transaction log, trades, free-agent bids, the salary cap, the injured
                  reserve table, per-team blocks; it ends exactly at the end of the file
======== ======== ============================================================================

Provenance.  ``FUN_000c5800`` (retail ``default.xbe`` sha256 73105b17…) copies the season block field
by field into named globals, so every offset it names is PROVED; the serialiser at 0xC5310 (a gap in
the Ghidra ledger, disassembled with capstone) zeroes exactly ``0x83DC`` bytes when the sub-state is
3, which fixes the block length, and ``FUN_002d0ce0`` reads the front-office block at ``[ebp+off]``
with the offsets used below (its last table ends at ``+0x165B0`` = file 0xAFCAC, the file length).
Finn's community offsets (schedule 0x917EA, team control 0x913CC, cap 0x9ACCC, IR 0x9E6CC) all fall on
those fields.  What the game does with a field is PROVED only where a consumer was read: the year
(display = 2004 + field, witnessed in-game), the division table (``FUN_002a7d60`` seeding), the
user-control flags (``FUN_000c4d70``), the salary cap (``DAT_00e3c278``, $1000 units, 80,500 in a
2004 save and 80,500 × 1.013^7 = 88,113 in a year-7 save, matching the game's cap projection), the
injured reserve table (``FUN_002d0540`` index → player, Finn's 17-byte IR diff reproduced byte for
byte), the played grid / flags / quarter scores, the coach record (Finn's map, re-checked on real
career numbers) and the team stat ids (``FUN_00134dd0``).  Everything else is carried verbatim and
exposed with a HYPOTHESIS label; ``REGIONS`` says which is which.

This module never writes a file itself: ``FranchiseSave.write`` hands the bytes to the existing
``SaveContainer`` which re-signs ``EXTRA`` and refuses to overwrite the source.  ``to_bytes()`` of an
untouched save is byte-identical to the input.  Unwitnessed in game except where stated.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from . import nfl2k5_roster_records as rr

# --------------------------------------------------------------------------------------------- layout
FRANCHISE_SAVE_SIZE = 720_044
SETTINGS_PREFIX_SIZE = 0x2E0
ARENA_WRAPPER = 0x2E0
ARENA_PREAMBLE = 0x300
ARENA_ROOT = 0x320
ARENA_DECLARED = 0x91020
ARENA_END = 0x91320

SEASON_BLOCK = 0x91320
SEASON_BLOCK_SIZE = 0x83DC
SEASON_RAM_BASE = 0xE57776                  # RAM address of season block byte 0 (FUN_000c5800)
FRONT_OFFICE_BLOCK = SEASON_BLOCK + SEASON_BLOCK_SIZE          # 0x996FC
FRONT_OFFICE_SIZE = 0x165B0

LEAGUE_SLOTS = 34                           # 32 teams + the two all-star placeholders (ids 32/33)
NFL_TEAMS = 32
GRID_ROWS, GRID_SLOTS = 22, 17
GRID_CELLS = GRID_ROWS * GRID_SLOTS         # 374
GAME_SIZE = 8
SCORE_BYTES = 10                            # five quarter-score bytes per side
AWARD_ROWS, AWARD_SLOTS, AWARD_SIZE = 17, 5, 0x1C

# season block, relative to SEASON_BLOCK ------------------------------------------------------
S_MODE = 0x00            # DAT_00e576a0: 2 = franchise
S_STAGE = 0x01           # DAT_00e576a4: row of the .rdata stage table at 0x515140
S_SUBSTATE = 0x02        # DAT_00e576a8 (3 = "empty" -> the serialiser writes an all-zero block)
S_TEAM_COUNT = 0x03      # DAT_00e576ac (32)
S_STAGE_WEEKS = 0x04     # DAT_00e576b0: the stage's week count (17 in season, 5 pre/post, 1 offseason)
S_WEEK = 0x05            # DAT_00e576b4
S_YEAR = 0x06            # DAT_00e576b8: display year = 2004 + field (witnessed in game)
S_WORD_08 = 0x08         # DAT_00e576bc (u16)
S_FLAG_0A = 0x0A         # DAT_00e576c8 (bool)
S_SEEDS_A = 0x0B         # 12 team indices <- DAT_00e578f4 (playoff seeds, 0xFF = none)
S_SEEDS_B = 0x17         # 12 team indices <- DAT_00e57924
S_DIVISIONS = 0x24       # 34 u32 <- DAT_00e576d4: division 0..7 per team
S_USER_CONTROL = 0xAC    # 34 u32 <- DAT_00e5775c: non-zero = user-controlled team (Finn: 0x913CC)
S_TEAM_WORDS = 0x134     # 34 u32 <- DAT_00e577e4 (unknown per-team word)
S_TEAM_ORDER = 0x1BC     # 34 u8  <- team index of the pointers at DAT_00e5786c (0xFF = null)
S_GRID_FLAGS = 0x1DE     # 374 u16 <- DAT_00e57954: two flag bytes per grid cell
S_GRID = 0x4CA           # 374 x 8 <- DAT_00e57c40: the played/scheduled grid (Finn: 0x917EA)
S_SCORES = 0x107A        # 374 x 10 <- DAT_00e587f0: quarter scores, written only for played cells
S_AWARDS = 0x1F18        # 17 x 5 x 0x1C <- DAT_00e5968c, two player indices per record
S_WORDS_2864 = 0x2864    # 306 u16 <- DAT_00e59fd8
S_BYTES_2AC8 = 0x2AC8    # 4 bytes <- DAT_00e5a23c
S_STATS_HEAD = 0x2ACC    # one dword FUN_001349a0 stores at object +0x2C50
S_STATS = 0x2AD0         # league stat tables consumed by FUN_001349a0: 17 x 0x32C rows, then 0x22A0 bytes
S_STATS_ROWS, S_STATS_ROW_SIZE, S_STATS_TAIL = 17, 0x32C, 0x22A0
S_TAIL = 0x835C          # 0x80 bytes (FUN_00031000(0x80)); zero in the 2004 save
S_TAIL_SIZE = 0x80

# front-office block, relative to FRONT_OFFICE_BLOCK ------------------------------------------
F_ORDERS = 0x0000        # 14 x 32 u32 (byte values) -> DAT_00e3c0b4.. ; table 0 is a permutation of 0..31
F_ORDER_TABLES = 14
F_DWORD_700 = 0x0700     # -> DAT_00e3c0ac
F_BYTES_704 = 0x0704     # 4 bytes -> DAT_00e3c0a4 / e3c0a8 / e3c0b0 / e3c274
F_LOG = 0x0708           # up to 256 x 12: {u32 packed (bits 7-12 = kind), u32, u32} -> DAT_00e40588
F_LOG_CAPACITY, F_LOG_SIZE = 256, 12
F_LOG_COUNT = 0x1308     # u16
F_LOG_FLAG = 0x130A      # u8
F_TEAM_REFS_A = 0x130C   # 32 x {u16 player, u16, u16, u16} -> DAT_00e41898
F_TEAM_REFS_B = 0x140C   # 32 x {u16 player, u16, u16, u16} -> DAT_00e41a18
F_TEAM_BYTES_150C = 0x150C   # 32 u8 -> DAT_00e41b98
F_FLAG_152C = 0x152C     # -> DAT_00e41bd8
F_TEAM_FLOATS = 0x1530   # 32 f32 -> DAT_00e41bdc
F_TEAM_RANK = 0x15B0     # 32 u8 -> DAT_00e41c5c (1..32 in the year-7 save)
F_SALARY_CAP = 0x15D0    # u32 -> DAT_00e3c278, $1000 units (Finn: 0x9ACCC)
F_TRADES = 0x15D4        # 15 x 34 -> DAT_00e3c27c (60-byte records: 2 teams, 2 x 3 players, values)
F_TRADE_COUNT, F_TRADE_SIZE = 15, 34
F_FA_BIDS = 0x17D2       # 100 x 12 -> DAT_00e3c600 (player, team, bid words)
F_FA_BID_COUNT, F_FA_BID_SIZE = 100, 12
F_TEAM_BOARDS = 0x1C82   # 32 x 36 x {u16 player, u8 value, u8} -> DAT_00e3cc40
F_BOARD_SLOTS, F_BOARD_ENTRY = 36, 4
F_BYTE_2E82 = 0x2E82     # -> DAT_00e3f060
F_TEAM_ORDER_2 = 0x2E83  # 32 u8 -> DAT_00e41bb8 (0xFF in the 2004 save, a team permutation in year 7)
F_TEAM_RECORDS = 0x2EA4  # 32 x 36 -> DAT_00e41ce0 (seven f32 0.5 + two u32 in both saves)
F_TEAM_RECORD_SIZE = 36
F_LEDGER_COUNT = 0x332C  # u32 -> DAT_00e3f06c
F_LEDGER = 0x3330        # 600 x 12: {u32 packed, u16 player, u16, u8 team, 3 pad} -> DAT_00e3f070
F_LEDGER_CAPACITY, F_LEDGER_SIZE = 600, 12
F_TEAM_DWORDS_4F50 = 0x4F50  # 32 u32 -> DAT_00e42160
F_INJURED_RESERVE = 0x4FD0   # 32 x 5 x {u16 player index, u16 pad}; 0xFFFF = empty -> DAT_00e421e0
IR_SLOTS, IR_ENTRY = 5, 4
F_TEAM_BLOCKS = 0x5250   # 32 x 2000 bytes -> DAT_00e42460
F_TEAM_BLOCK_SIZE = 2000
F_TEAM_DWORDS_14C50 = 0x14C50   # 32 u32 -> DAT_00e3d210
F_TEAM_DWORDS_14CD0 = 0x14CD0   # 32 u32 -> DAT_00e3d290
F_ROSTER_SLOT_BYTES = 0x14D50   # 32 x 65 x 3 -> DAT_00e51f60
F_ROSTER_SLOT_SIZE = 3
F_END = F_ROSTER_SLOT_BYTES + NFL_TEAMS * rr.TEAM_SLOTS * F_ROSTER_SLOT_SIZE      # 0x165B0

assert F_END == FRONT_OFFICE_SIZE
assert FRONT_OFFICE_BLOCK + FRONT_OFFICE_SIZE == FRANCHISE_SAVE_SIZE
assert S_STATS + S_STATS_ROWS * S_STATS_ROW_SIZE + S_STATS_TAIL == S_TAIL
assert S_TAIL + S_TAIL_SIZE == SEASON_BLOCK_SIZE

# arena-side franchise fields (team record, coach record) --------------------------------------
TEAM_SALARY = 0x124                 # u32, $1000 units; recomputed by FUN_000c3f00 (contracts + IR charge)
TEAM_RECORD_RING = 0x19C            # 7 u16 shifted by FUN_0013ed70 / added by FUN_0013ed30
TEAM_RECORD_RING_COUNT = 7
TEAM_GAMES_PLAYED = 0x1DC           # u16, incremented once per merged game (FUN_00134dd0)
TEAM_STREAK_BYTES = (0x1EE, 0x1EF, 0x1F0, 0x1F1)
# team season stat u16 fields and the stat id FUN_00134dd0 merges into each (retail 0x134DD0..)
TEAM_STAT_FIELDS: dict[int, int] = {
    0x1AA: 0x4C, 0x1AC: 0x50, 0x1AE: 0x46, 0x1B0: 0x45, 0x1B2: 0x25, 0x1B4: 0x26, 0x1B6: 0x0E,
    0x1B8: 0x43, 0x1BA: 0x52, 0x1BC: 0x27, 0x1BE: 0x53, 0x1C0: 0x28, 0x1C2: 0x54, 0x1C4: 0xB3,
    0x1C6: 0xB2, 0x1C8: 0xB1, 0x1CA: 0xB6, 0x1CC: 0xB5, 0x1CE: 0xB4, 0x1D0: 0x24, 0x1D2: 0x62,
    0x1D4: 0x42, 0x1D6: 0x64, 0x1D8: 0x5B, 0x1DA: 0x5C, 0x1DE: 0xB8, 0x1E0: 0x30, 0x1E2: 0x40,
    0x1E4: 0x3F, 0x1E6: 0x16, 0x1E8: 0x17,
}
# the stat ids with a proved label (per-game descriptor table .data 0xAE59C0: "Passing Yards Per Game" =
# 0x4C / games 0x63, "Rushing Yards Per Game" = 0x50, "Yds/Game" = 0x62, "Turnovers Per Game" = 0x42)
TEAM_STAT_NAMES = {0x4C: "passing_yards", 0x50: "rushing_yards", 0x62: "total_yards", 0x42: "turnovers"}

COACH_SIZE = 0xA8
COACH_FIELDS: dict[str, tuple[int, str]] = {           # Finn's map; W/L/SB/playoff numbers re-checked on real coaches
    "body": (0x18, "<I"), "seasons_with_team": (0x1C, "<H"), "total_seasons": (0x1E, "<H"),
    "wins": (0x20, "<H"), "losses": (0x22, "<H"), "ties": (0x24, "<H"),
    "season_wins": (0x26, "<H"), "season_losses": (0x28, "<H"), "season_ties": (0x2A, "<H"),
    "unknown_2c": (0x2C, "<H"), "unknown_2e": (0x2E, "<H"),
    "winning_seasons": (0x30, "<H"), "super_bowls": (0x32, "<H"), "playoff_wins": (0x34, "<H"),
    "playoff_losses": (0x36, "<H"), "super_bowl_wins": (0x38, "<H"), "super_bowl_losses": (0x3A, "<H"),
    "unknown_3c": (0x3C, "<H"), "unknown_3e": (0x3E, "<H"), "photo": (0x40, "<H"),
    "playcalling_run": (0x59, "<B"),
}
COACH_RATINGS = ("overall", "offense", "rush_for", "pass_for", "defense", "pass_rush", "pass_coverage",
                 "qb", "rb", "te", "wr", "ol", "dl", "lb", "db", "special_teams", "professionalism",
                 "preparation", "conditioning", "motivation", "leadership", "discipline", "respect")
COACH_RATINGS_OFFSET = 0x42                                            # 23 bytes 0x42..0x58
COACH_TENDENCIES_OFFSET, COACH_TENDENCY_COUNT = 0x83, 10                # 5 formations x run / pass
COACH_TENDENCIES = ("shotgun_run", "shotgun_pass", "split_back_run", "split_back_pass", "i_form_run",
                    "i_form_pass", "lone_back_run", "lone_back_pass", "empty_run", "empty_pass")

STAGE_WEEKS = (1, 1, 1, 1, 1, 1, 1, 5, 17, 5)                           # .rdata stage table 0x515140, byte +4
STAGE_NAMES = {7: "preseason", 8: "regular season", 9: "postseason"}
DISPLAY_YEAR_BASE = 2004
GAME_SCHEDULED, GAME_PLAYED, GAME_FILLER = 0, 3, 7
ROW_NAMES = {17: "wild card", 18: "divisional", 19: "conference", 20: "super bowl", 21: "pro bowl"}
IR_EMPTY = 0xFFFF
IR_MARK = 0xEE                                                          # player +0x28 while on injured reserve

# fallback names when the arena cannot be read (alphabetical by nickname = the game's team order)
TEAM_NICKNAMES = ("49ers", "Bears", "Bengals", "Bills", "Broncos", "Browns", "Buccaneers", "Cardinals",
                  "Chargers", "Chiefs", "Colts", "Cowboys", "Dolphins", "Eagles", "Falcons", "Giants",
                  "Jaguars", "Jets", "Lions", "Packers", "Panthers", "Patriots", "Raiders", "Rams", "Ravens",
                  "Redskins", "Saints", "Seahawks", "Steelers", "Texans", "Titans", "Vikings", "AFC", "NFC")


class FranchiseSaveError(ValueError):
    """The bytes are not a franchise save, or an edit would leave one inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FranchiseSaveError(message)


# --------------------------------------------------------------------------------------------- records
@dataclass(frozen=True)
class SeasonHeader:
    mode: int
    stage: int
    substate: int
    team_count: int
    stage_weeks: int
    week: int
    year_field: int
    word_08: int
    flag_0a: int
    seeds_a: tuple[int, ...]
    seeds_b: tuple[int, ...]

    @property
    def display_year(self) -> int:
        return DISPLAY_YEAR_BASE + self.year_field

    @property
    def stage_name(self) -> str:
        return STAGE_NAMES.get(self.stage, f"offseason stage {self.stage}")


@dataclass(frozen=True)
class Game:
    row: int
    slot: int
    offset: int
    kind: int               # 0 scheduled, 3 played, 7 filler
    home: int
    away: int
    month: int
    day: int
    slot_code: int
    hour: int
    minute: int
    flags: int              # the u16 at S_GRID_FLAGS for this cell
    scores: tuple[tuple[int, ...], tuple[int, ...]] | None       # (first five bytes, last five) when played

    @property
    def row_name(self) -> str:
        return ROW_NAMES.get(self.row, f"week {self.row + 1}")

    @property
    def played(self) -> bool:
        return self.kind == GAME_PLAYED

    def kickoff(self) -> str:
        hour = 12 if self.hour == 0 else self.hour
        return f"{hour}:{self.minute:02d}"


@dataclass(frozen=True)
class Coach:
    index: int
    offset: int
    first: str
    last: str
    info: tuple[str, str, str]
    fields: dict[str, int]
    ratings: dict[str, int]
    tendencies: dict[str, int]
    teams: tuple[int, ...]         # team indices whose +0x14C points here

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}".strip()


@dataclass(frozen=True)
class TeamSeason:
    index: int
    abbreviation: str
    salary: int                     # $1000 units
    record_ring: tuple[int, ...]    # 7 u16 at +0x19C
    games_played: int
    stats: dict[int, int]           # stat id -> season total (u16)
    streak_bytes: tuple[int, ...]

    def stat(self, name: str) -> int:
        for stat_id, label in TEAM_STAT_NAMES.items():
            if label == name:
                return self.stats.get(stat_id, 0)
        raise KeyError(name)


@dataclass(frozen=True)
class InjuredReserveEntry:
    team: int
    slot: int
    offset: int
    player_index: int
    name: str


@dataclass(frozen=True)
class Region:
    offset: int
    size: int
    label: str
    status: str                     # PROVED / HYPOTHESIS / OPAQUE
    note: str = ""

    @property
    def end(self) -> int:
        return self.offset + self.size


# --------------------------------------------------------------------------------------------- the save
class FranchiseSave:
    """Typed, lossless access to a franchise ``SAVEGAME.DAT``; ``to_bytes()`` is the input when untouched."""

    def __init__(self, payload: bytes | bytearray, *, container: rr.SaveContainer | None = None,
                 source: str = "bytes") -> None:
        data = bytes(payload)
        _require(len(data) == FRANCHISE_SAVE_SIZE,
                 f"a franchise save is {FRANCHISE_SAVE_SIZE:,} bytes; this is {len(data):,}")
        _require(data[ARENA_WRAPPER:ARENA_WRAPPER + 4] == b"ROST"
                 and struct.unpack_from("<I", data, ARENA_WRAPPER + 4)[0] == ARENA_DECLARED,
                 "no runtime ROST arena wrapper at 0x2E0 (declared 0x91020)")
        _require(data[ARENA_PREAMBLE + 0x0C:ARENA_PREAMBLE + 0x10] == b"ROST"
                 and struct.unpack_from("<I", data, ARENA_PREAMBLE + 0x10)[0] == 0,
                 "the ROST preamble at 0x300 is not version 0")
        self.original = data
        self.buffer = bytearray(data)
        self.container = container
        self.source = source
        self._roster: rr.RosterDocument | None = None

    # ------------------------------------------------------------------ construction / output
    @classmethod
    def load(cls, path: Path | str, *, require_signature: bool = True) -> "FranchiseSave":
        container = rr.SaveContainer.load(path, require_signature=require_signature)
        return cls(container.savegame, container=container, source=str(container.path))

    def to_bytes(self) -> bytes:
        return bytes(self.buffer)

    def changed_ranges(self) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        start = None
        for index, (before, after) in enumerate(zip(self.original, self.buffer)):
            if before != after and start is None:
                start = index
            elif before == after and start is not None:
                ranges.append((start, index))
                start = None
        if start is not None:
            ranges.append((start, len(self.buffer)))
        return ranges

    def write(self, target: Path | str, *, overwrite: bool = False) -> dict[str, Any]:
        _require(self.container is not None, "this save was not opened from a container; nothing to re-sign")
        assert self.container is not None
        return self.container.write(target, self.to_bytes(), overwrite=overwrite)

    # ------------------------------------------------------------------ raw helpers
    def u8(self, offset: int) -> int:
        return self.buffer[offset]

    def u16(self, offset: int) -> int:
        return struct.unpack_from("<H", self.buffer, offset)[0]

    def u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.buffer, offset)[0]

    def f32(self, offset: int) -> float:
        return struct.unpack_from("<f", self.buffer, offset)[0]

    def rel(self, field: int) -> int | None:
        value = struct.unpack_from("<i", self.buffer, field)[0]
        if value == 0:
            return None
        target = field + value - 1
        _require(ARENA_ROOT <= target < ARENA_END, f"relative pointer at 0x{field:x} leaves the arena")
        return target

    def wstr(self, field: int) -> str:
        target = self.rel(field)
        if target is None:
            return ""
        end = target
        limit = min(ARENA_END, target + 4096)
        while end + 2 <= limit and self.buffer[end:end + 2] != b"\0\0":
            end += 2
        return self.buffer[target:end].decode("utf-16-le", errors="replace")

    def _set(self, offset: int, fmt: str, value: int, *, label: str, low: int = 0, high: int | None = None) -> None:
        size = struct.calcsize(fmt)
        limit = (1 << (8 * size)) - 1 if high is None else high
        _require(isinstance(value, int) and low <= value <= limit, f"{label}: {value!r} is outside {low}..{limit}")
        struct.pack_into(fmt, self.buffer, offset, value)

    # ------------------------------------------------------------------ the arena (roster side)
    @property
    def roster(self) -> rr.RosterDocument:
        """The ★ Rosters document over the same bytes (parsed lazily, from the ORIGINAL bytes)."""

        if self._roster is None:
            self._roster = rr.RosterDocument(self.original, base=ARENA_PREAMBLE, source=self.source)
        return self._roster

    @property
    def player_table(self) -> tuple[int, int]:
        """``(count, offset)`` of the primary player pool (root +0x00 / +0x04)."""

        count = self.u32(ARENA_ROOT)
        table = self.rel(ARENA_ROOT + 4)
        _require(table is not None and count > 0, "the arena has no primary player table")
        assert table is not None
        return count, table

    def player_offset(self, index: int) -> int:
        count, table = self.player_table
        _require(0 <= index < count, f"player index {index} is outside the primary pool (0..{count - 1})")
        return table + index * rr.PLAYER_SIZE

    def player_index(self, offset: int) -> int:
        count, table = self.player_table
        index, remainder = divmod(offset - table, rr.PLAYER_SIZE)
        _require(remainder == 0 and 0 <= index < count, f"0x{offset:x} is not a primary player record")
        return index

    def player_name(self, index: int) -> str:
        if index == IR_EMPTY:
            return ""
        offset = self.player_offset(index)
        return f"{self.wstr(offset + 0x10)} {self.wstr(offset + 0x14)}".strip()

    @property
    def team_table(self) -> tuple[int, int]:
        count = self.u32(ARENA_ROOT + rr.TEAM_COUNT_FIELD - rr.OBJ_OFF)
        table = self.rel(ARENA_ROOT + rr.TEAM_TABLE_FIELD - rr.OBJ_OFF)
        _require(table is not None and count > 0, "the arena has no team table")
        assert table is not None
        return count, table

    def team_offset(self, index: int) -> int:
        count, table = self.team_table
        _require(0 <= index < count, f"team index {index} is outside the team table (0..{count - 1})")
        return table + index * rr.TEAM_SIZE

    def team_abbreviation(self, index: int) -> str:
        count, _table = self.team_table
        if 0 <= index < count:
            text = self.wstr(self.team_offset(index) + rr.TEAM_ABBREVIATION)
            if text:
                return text
        return TEAM_NICKNAMES[index] if 0 <= index < len(TEAM_NICKNAMES) else f"team {index}"

    @property
    def league_team_count(self) -> int:
        """NFL teams in this arena (32 on retail, fewer on a synthetic fixture)."""

        count, _table = self.team_table
        return min(count, NFL_TEAMS)

    # ------------------------------------------------------------------ season header
    @property
    def header(self) -> SeasonHeader:
        base = SEASON_BLOCK
        return SeasonHeader(
            mode=self.u8(base + S_MODE), stage=self.u8(base + S_STAGE), substate=self.u8(base + S_SUBSTATE),
            team_count=self.u8(base + S_TEAM_COUNT), stage_weeks=self.u8(base + S_STAGE_WEEKS),
            week=self.u8(base + S_WEEK), year_field=self.u8(base + S_YEAR), word_08=self.u16(base + S_WORD_08),
            flag_0a=self.u8(base + S_FLAG_0A),
            seeds_a=tuple(self.buffer[base + S_SEEDS_A:base + S_SEEDS_A + 12]),
            seeds_b=tuple(self.buffer[base + S_SEEDS_B:base + S_SEEDS_B + 12]))

    def set_year_field(self, value: int) -> None:
        self._set(SEASON_BLOCK + S_YEAR, "<B", value, label="year field", high=60)

    def set_display_year(self, year: int) -> None:
        self.set_year_field(year - DISPLAY_YEAR_BASE)

    @property
    def divisions(self) -> tuple[int, ...]:
        base = SEASON_BLOCK + S_DIVISIONS
        return struct.unpack_from(f"<{LEAGUE_SLOTS}I", self.buffer, base)

    @property
    def user_control(self) -> tuple[int, ...]:
        return struct.unpack_from(f"<{LEAGUE_SLOTS}I", self.buffer, SEASON_BLOCK + S_USER_CONTROL)

    def user_teams(self) -> list[int]:
        return [index for index, flag in enumerate(self.user_control[:NFL_TEAMS]) if flag]

    def set_user_control(self, team: int, controlled: bool) -> None:
        _require(0 <= team < NFL_TEAMS, f"team {team} is not an NFL team index")
        struct.pack_into("<I", self.buffer, SEASON_BLOCK + S_USER_CONTROL + 4 * team, 1 if controlled else 0)

    @property
    def team_order(self) -> tuple[int, ...]:
        return tuple(self.buffer[SEASON_BLOCK + S_TEAM_ORDER:SEASON_BLOCK + S_TEAM_ORDER + LEAGUE_SLOTS])

    # ------------------------------------------------------------------ the grid
    @staticmethod
    def cell(row: int, slot: int) -> int:
        _require(0 <= row < GRID_ROWS and 0 <= slot < GRID_SLOTS, f"grid cell ({row}, {slot}) is outside 22 x 17")
        return row * GRID_SLOTS + slot

    def game(self, row: int, slot: int) -> Game:
        index = self.cell(row, slot)
        offset = SEASON_BLOCK + S_GRID + index * GAME_SIZE
        raw = self.buffer[offset:offset + GAME_SIZE]
        flags = self.u16(SEASON_BLOCK + S_GRID_FLAGS + index * 2)
        scores = None
        if raw[0] == GAME_PLAYED:
            score_offset = SEASON_BLOCK + S_SCORES + index * SCORE_BYTES
            block = self.buffer[score_offset:score_offset + SCORE_BYTES]
            scores = (tuple(block[:5]), tuple(block[5:]))
        return Game(row, slot, offset, raw[0], raw[1], raw[2], raw[3], raw[4], raw[5], raw[6], raw[7], flags, scores)

    def games(self, *, rows: Sequence[int] | None = None) -> list[Game]:
        """Every real game in the grid (fillers and empty cells skipped), row by row."""

        out: list[Game] = []
        for row in (rows if rows is not None else range(GRID_ROWS)):
            for slot in range(GRID_SLOTS):
                game = self.game(row, slot)
                if game.kind == GAME_FILLER:
                    break
                if game.kind in (GAME_SCHEDULED, GAME_PLAYED) and (game.home or game.away or game.month):
                    out.append(game)
        return out

    def set_game(self, row: int, slot: int, *, home: int | None = None, away: int | None = None,
                 month: int | None = None, day: int | None = None, hour: int | None = None,
                 minute: int | None = None, slot_code: int | None = None, allow_played: bool = False) -> Game:
        """Edit a scheduled grid cell in place.  Played cells are refused unless ``allow_played``."""

        current = self.game(row, slot)
        _require(current.kind != GAME_FILLER, f"({row}, {slot}) is the row filler, not a game")
        _require(allow_played or current.kind != GAME_PLAYED, f"({row}, {slot}) has been played; pass allow_played")
        values = {"home": home, "away": away, "month": month, "day": day, "hour": hour, "minute": minute,
                  "slot_code": slot_code}
        limits = {"home": (0, LEAGUE_SLOTS - 1), "away": (0, LEAGUE_SLOTS - 1), "month": (1, 12), "day": (1, 31),
                  "hour": (0, 12), "minute": (0, 59), "slot_code": (0, 255)}
        offsets = {"home": 1, "away": 2, "month": 3, "day": 4, "slot_code": 5, "hour": 6, "minute": 7}
        for name, value in values.items():
            if value is None:
                continue
            low, high = limits[name]
            _require(isinstance(value, int) and low <= value <= high, f"{name}: {value!r} is outside {low}..{high}")
            self.buffer[current.offset + offsets[name]] = value
        updated = self.game(row, slot)
        _require(updated.home != updated.away, "a team cannot play itself")
        return updated

    # ------------------------------------------------------------------ the template (arena)
    @property
    def template_table(self) -> tuple[int, int]:
        """``(count, offset)`` of the season template the game copies into row 0.. at season start."""

        count = self.u32(ARENA_ROOT + 0x28)
        table = self.rel(ARENA_ROOT + 0x2C)
        if table is None:
            return 0, 0
        return count, table

    def template_games(self) -> list[Game]:
        count, table = self.template_table
        out = []
        for index in range(count):
            offset = table + index * GAME_SIZE
            raw = self.buffer[offset:offset + GAME_SIZE]
            out.append(Game(-1, index, offset, raw[0], raw[1], raw[2], raw[3], raw[4], raw[5], raw[6], raw[7], 0, None))
        return out

    # ------------------------------------------------------------------ front office
    @property
    def salary_cap(self) -> int:
        """League salary cap in $1000 units (80,500 = the 2004 $80.5M cap)."""

        return self.u32(FRONT_OFFICE_BLOCK + F_SALARY_CAP)

    def set_salary_cap(self, value: int) -> None:
        self._set(FRONT_OFFICE_BLOCK + F_SALARY_CAP, "<I", value, label="salary cap ($1000)", low=1, high=0x7FFFFFFF)

    def team_salary(self, team: int) -> int:
        return self.u32(self.team_offset(team) + TEAM_SALARY)

    def team_salaries(self) -> list[int]:
        return [self.team_salary(team) for team in range(self.league_team_count)]

    def injured_reserve(self, *, include_empty: bool = False) -> list[InjuredReserveEntry]:
        out = []
        for team in range(NFL_TEAMS):
            for slot in range(IR_SLOTS):
                offset = FRONT_OFFICE_BLOCK + F_INJURED_RESERVE + (team * IR_SLOTS + slot) * IR_ENTRY
                index = self.u16(offset)
                if index == IR_EMPTY and not include_empty:
                    continue
                name = self.player_name(index) if index != IR_EMPTY and team < self.league_team_count else ""
                out.append(InjuredReserveEntry(team, slot, offset, index, name))
        return out

    def _team_slots(self, team: int) -> tuple[int, list[int | None]]:
        base = self.team_offset(team)
        count = self.buffer[base + rr.TEAM_PLAYER_COUNT]
        _require(count <= rr.TEAM_SLOTS, f"team {team} declares {count} players")
        return count, [self.rel(base + 4 * slot) for slot in range(rr.TEAM_SLOTS)]

    def team_player_indices(self, team: int) -> list[int]:
        """Primary-pool indices of the players on ``team``'s pointer list, in depth order (the IR picker)."""

        _require(0 <= team < self.league_team_count, f"team {team} is not an NFL team in this arena")
        count, slots = self._team_slots(team)
        return [self.player_index(offset) for offset in slots[:count] if offset is not None]

    def _write_team_slot(self, team: int, slot: int, target: int | None) -> None:
        field = self.team_offset(team) + 4 * slot
        struct.pack_into("<i", self.buffer, field, 0 if target is None else target - field + 1)

    def place_on_injured_reserve(self, team: int, player_index: int) -> InjuredReserveEntry:
        """Finn's IR move: compact the team's pointer list, count -1, player +0x28 = 0xEE, fill an IR slot.

        Reproduces the 17-byte diff between the two 8007Fran fixtures byte for byte (test).  The game
        recomputes the team's salary (IR still counts against the cap) and its active count itself.
        """

        _require(0 <= team < self.league_team_count, f"team {team} is not an NFL team in this arena")
        target = self.player_offset(player_index)
        count, slots = self._team_slots(team)
        _require(target in slots[:count], f"player {player_index} is not on team {team}")
        position = slots.index(target)
        _require(self.buffer[target + 0x28] != IR_MARK, f"player {player_index} is already marked injured reserve")
        free = None
        for slot in range(IR_SLOTS):
            offset = FRONT_OFFICE_BLOCK + F_INJURED_RESERVE + (team * IR_SLOTS + slot) * IR_ENTRY
            if self.u16(offset) == IR_EMPTY:
                free = (slot, offset)
                break
        _require(free is not None, f"team {team} already has {IR_SLOTS} players on injured reserve")
        assert free is not None
        for slot in range(position, count - 1):
            self._write_team_slot(team, slot, slots[slot + 1])
        self._write_team_slot(team, count - 1, None)
        self.buffer[self.team_offset(team) + rr.TEAM_PLAYER_COUNT] = count - 1
        self.buffer[target + 0x28] = IR_MARK
        struct.pack_into("<H", self.buffer, free[1], player_index)
        return InjuredReserveEntry(team, free[0], free[1], player_index, self.player_name(player_index))

    def activate_from_injured_reserve(self, team: int, player_index: int) -> None:
        """The inverse of ``place_on_injured_reserve`` (HYPOTHESIS: unwitnessed in game)."""

        _require(0 <= team < self.league_team_count, f"team {team} is not an NFL team in this arena")
        target = self.player_offset(player_index)
        found = None
        for slot in range(IR_SLOTS):
            offset = FRONT_OFFICE_BLOCK + F_INJURED_RESERVE + (team * IR_SLOTS + slot) * IR_ENTRY
            if self.u16(offset) == player_index:
                found = offset
                break
        _require(found is not None, f"player {player_index} is not on team {team}'s injured reserve")
        count, slots = self._team_slots(team)
        _require(count < rr.TEAM_SLOTS, f"team {team} has no free roster slot")
        assert found is not None
        struct.pack_into("<H", self.buffer, found, IR_EMPTY)
        self.buffer[target + 0x28] = 0
        self._write_team_slot(team, count, target)
        self.buffer[self.team_offset(team) + rr.TEAM_PLAYER_COUNT] = count + 1

    def order_table(self, table: int) -> tuple[int, ...]:
        """One of the 14 per-team byte tables at F+0 (table 0 = a team permutation; HYPOTHESIS: draft order)."""

        _require(0 <= table < F_ORDER_TABLES, f"order table {table} is outside 0..13")
        base = FRONT_OFFICE_BLOCK + F_ORDERS + table * NFL_TEAMS * 4
        return tuple(value & 0xFF for value in struct.unpack_from(f"<{NFL_TEAMS}I", self.buffer, base))

    def team_ranks(self) -> tuple[int, ...]:
        base = FRONT_OFFICE_BLOCK + F_TEAM_RANK
        return tuple(self.buffer[base:base + NFL_TEAMS])

    def team_floats(self) -> tuple[float, ...]:
        return struct.unpack_from(f"<{NFL_TEAMS}f", self.buffer, FRONT_OFFICE_BLOCK + F_TEAM_FLOATS)

    def transactions(self) -> list[dict[str, int]]:
        """The 12-byte log at F+0x708 (HYPOTHESIS: transaction/news log; kind = bits 7-12 of the first word)."""

        count = min(self.u16(FRONT_OFFICE_BLOCK + F_LOG_COUNT), F_LOG_CAPACITY)
        out = []
        for index in range(count):
            offset = FRONT_OFFICE_BLOCK + F_LOG + index * F_LOG_SIZE
            packed, a, b = struct.unpack_from("<III", self.buffer, offset)
            out.append({"index": index, "offset": offset, "packed": packed, "kind": (packed >> 7) & 0x3F,
                        "bit0": packed & 1, "field_1_6": (packed >> 1) & 0x3F, "field_13_19": (packed >> 13) & 0x7F,
                        "field_20_25": (packed >> 20) & 0x3F, "a": a, "b": b})
        return out

    def ledger(self) -> list[dict[str, Any]]:
        """The 600-record table at F+0x3330 (HYPOTHESIS: franchise history ledger; count at F+0x332C)."""

        count = min(self.u32(FRONT_OFFICE_BLOCK + F_LEDGER_COUNT), F_LEDGER_CAPACITY)
        out = []
        for index in range(count):
            offset = FRONT_OFFICE_BLOCK + F_LEDGER + index * F_LEDGER_SIZE
            packed, player, word, team = struct.unpack_from("<IHHB", self.buffer, offset)
            out.append({"index": index, "offset": offset, "packed": packed, "player_index": player,
                        "player": self.player_name(player) if player != IR_EMPTY and player < self.player_table[0] else "",
                        "word": word, "team": team, "team_name": self.team_abbreviation(team) if team != 0xFF else ""})
        return out

    def trades(self) -> list[dict[str, Any]]:
        """The 15 x 34-byte trade records at F+0x15D4 (FUN_002d06d0: kind, two teams, two triples of players)."""

        out = []
        for index in range(F_TRADE_COUNT):
            offset = FRONT_OFFICE_BLOCK + F_TRADES + index * F_TRADE_SIZE
            raw = self.buffer[offset:offset + F_TRADE_SIZE]
            out.append({"index": index, "offset": offset, "kind": raw[0], "raw": bytes(raw)})
        return out

    def fa_bids(self) -> list[dict[str, Any]]:
        """The 100 x 12-byte free-agent bid slots at F+0x17D2 (FUN_002d05b0; player index in the first word)."""

        out = []
        for index in range(F_FA_BID_COUNT):
            offset = FRONT_OFFICE_BLOCK + F_FA_BIDS + index * F_FA_BID_SIZE
            raw = self.buffer[offset:offset + F_FA_BID_SIZE]
            player = struct.unpack_from("<H", raw, 0)[0]
            out.append({"index": index, "offset": offset, "player_index": player, "raw": bytes(raw)})
        return out

    # ------------------------------------------------------------------ coaches (arena)
    @property
    def coach_table(self) -> tuple[int, int]:
        count = self.u32(ARENA_ROOT + 0x30)
        table = self.rel(ARENA_ROOT + 0x34)
        if table is None:
            return 0, 0
        return count, table

    def coaches(self) -> list[Coach]:
        count, table = self.coach_table
        by_offset: dict[int, list[int]] = {}
        for team in range(self.league_team_count):
            pointer = self.rel(self.team_offset(team) + rr.TEAM_COACH)
            if pointer is not None:
                by_offset.setdefault(pointer, []).append(team)
        out = []
        for index in range(count):
            offset = table + index * COACH_SIZE
            fields = {name: struct.unpack_from(fmt, self.buffer, offset + rel)[0] for name, (rel, fmt) in COACH_FIELDS.items()}
            ratings = {name: self.buffer[offset + COACH_RATINGS_OFFSET + k] for k, name in enumerate(COACH_RATINGS)}
            tendencies = {name: self.buffer[offset + COACH_TENDENCIES_OFFSET + k] for k, name in enumerate(COACH_TENDENCIES)}
            out.append(Coach(index, offset, self.wstr(offset), self.wstr(offset + 4),
                             (self.wstr(offset + 8), self.wstr(offset + 0xC), self.wstr(offset + 0x10)),
                             fields, ratings, tendencies, tuple(by_offset.get(offset, ()))))
        return out

    def coach_for_team(self, team: int) -> Coach | None:
        pointer = self.rel(self.team_offset(team) + rr.TEAM_COACH)
        if pointer is None:
            return None
        for coach in self.coaches():
            if coach.offset == pointer:
                return coach
        return None

    def set_coach_field(self, coach_index: int, name: str, value: int) -> None:
        count, table = self.coach_table
        _require(0 <= coach_index < count, f"coach {coach_index} is outside 0..{count - 1}")
        offset = table + coach_index * COACH_SIZE
        if name in COACH_FIELDS:
            rel, fmt = COACH_FIELDS[name]
            self._set(offset + rel, fmt, value, label=f"coach {name}", high=100 if name == "playcalling_run" else None)
        elif name in COACH_RATINGS:
            self._set(offset + COACH_RATINGS_OFFSET + COACH_RATINGS.index(name), "<B", value, label=f"coach {name}", high=99)
        elif name in COACH_TENDENCIES:
            self._set(offset + COACH_TENDENCIES_OFFSET + COACH_TENDENCIES.index(name), "<B", value,
                      label=f"coach {name}", high=100)
        else:
            raise FranchiseSaveError(f"unknown coach field {name!r}")

    # ------------------------------------------------------------------ team season state (arena)
    def team_season(self, team: int) -> TeamSeason:
        base = self.team_offset(team)
        return TeamSeason(
            team, self.team_abbreviation(team), self.u32(base + TEAM_SALARY),
            struct.unpack_from(f"<{TEAM_RECORD_RING_COUNT}H", self.buffer, base + TEAM_RECORD_RING),
            self.u16(base + TEAM_GAMES_PLAYED),
            {stat_id: self.u16(base + rel) for rel, stat_id in TEAM_STAT_FIELDS.items()},
            tuple(self.buffer[base + rel] for rel in TEAM_STREAK_BYTES))

    def team_seasons(self) -> list[TeamSeason]:
        return [self.team_season(team) for team in range(self.league_team_count)]

    def set_team_record_ring(self, team: int, slot: int, value: int) -> None:
        _require(0 <= slot < TEAM_RECORD_RING_COUNT, f"record slot {slot} is outside 0..6")
        self._set(self.team_offset(team) + TEAM_RECORD_RING + 2 * slot, "<H", value, label="team record")

    # ------------------------------------------------------------------ summary
    def summary(self) -> dict[str, Any]:
        header = self.header
        users = self.user_teams()
        injured = self.injured_reserve()
        played = [g for g in self.games() if g.played]
        return {
            "source": self.source, "size": len(self.buffer), "display_year": header.display_year,
            "year_field": header.year_field, "stage": header.stage, "stage_name": header.stage_name,
            "stage_weeks": header.stage_weeks, "week": header.week, "mode": header.mode, "substate": header.substate,
            "user_teams": users, "user_team_names": [self.team_abbreviation(t) for t in users],
            "salary_cap": self.salary_cap, "salary_cap_text": f"${self.salary_cap / 1000:.1f}M",
            "injured_reserve": [{"team": e.team, "team_name": self.team_abbreviation(e.team), "player_index": e.player_index,
                                 "name": e.name} for e in injured],
            "games_in_grid": len(self.games()), "games_played": len(played),
            "coaches": self.coach_table[0], "template_games": self.template_table[0],
            "seeds_a": [s for s in header.seeds_a if s != 0xFF], "seeds_b": [s for s in header.seeds_b if s != 0xFF],
        }

    def one_line(self) -> str:
        s = self.summary()
        users = ", ".join(s["user_team_names"]) or "none"
        return (f"{s['display_year']} (year field {s['year_field']}), {s['stage_name']} week {s['week']}/{s['stage_weeks']}, "
                f"user team(s) {users}, cap {s['salary_cap_text']}, {s['games_played']}/{s['games_in_grid']} grid games "
                f"played, {len(s['injured_reserve'])} on IR")

    # ------------------------------------------------------------------ the map
    def regions(self) -> list[Region]:
        return list(REGIONS)


def _regions() -> list[Region]:
    S, F = SEASON_BLOCK, FRONT_OFFICE_BLOCK
    rows: list[tuple[int, int, str, str, str]] = [
        (0, SETTINGS_PREFIX_SIZE, "settings prefix (RAM 0xE5FF80)", "PROVED", "nfl2k5_save_writer"),
        (ARENA_WRAPPER, 0x20, "ROST wrapper (declared 0x91020)", "PROVED", ""),
        (ARENA_PREAMBLE, 0x20, "ROST preamble, version 0, root at +0x20", "PROVED", ""),
        (ARENA_ROOT, ARENA_END - ARENA_ROOT, "roster arena (players, teams, coaches, template schedule, pools)", "PROVED", "nfl2k5_roster_records"),
        (S + S_MODE, 1, "mode (DAT_00e576a0)", "PROVED", "2 = franchise"),
        (S + S_STAGE, 1, "stage (DAT_00e576a4)", "PROVED", "rows 7/8/9 = pre/regular/post season"),
        (S + S_SUBSTATE, 1, "sub-state (DAT_00e576a8)", "PROVED", "3 = empty block"),
        (S + S_TEAM_COUNT, 1, "team count (DAT_00e576ac)", "PROVED", ""),
        (S + S_STAGE_WEEKS, 1, "stage week count (DAT_00e576b0)", "PROVED", ""),
        (S + S_WEEK, 1, "week in stage (DAT_00e576b4)", "HYPOTHESIS", "0 in both saves"),
        (S + S_YEAR, 1, "year field (DAT_00e576b8), display = 2004 + field", "PROVED", "witnessed in game"),
        (S + 7, 1, "unused", "OPAQUE", ""),
        (S + S_WORD_08, 2, "u16 (DAT_00e576bc)", "OPAQUE", ""),
        (S + S_FLAG_0A, 1, "flag (DAT_00e576c8)", "OPAQUE", ""),
        (S + S_SEEDS_A, 12, "playoff seeds A (DAT_00e578f4)", "PROVED", "team index, 0xFF none"),
        (S + S_SEEDS_B, 12, "playoff seeds B (DAT_00e57924)", "PROVED", "team index, 0xFF none"),
        (S + S_SEEDS_B + 12, 1, "pad", "OPAQUE", ""),
        (S + S_DIVISIONS, 4 * LEAGUE_SLOTS, "division per team (DAT_00e576d4)", "PROVED", "seeding reads it"),
        (S + S_USER_CONTROL, 4 * LEAGUE_SLOTS, "user control per team (DAT_00e5775c)", "PROVED", "Finn 0x913CC"),
        (S + S_TEAM_WORDS, 4 * LEAGUE_SLOTS, "per-team word (DAT_00e577e4)", "OPAQUE", ""),
        (S + S_TEAM_ORDER, LEAGUE_SLOTS, "team order (indices of DAT_00e5786c)", "PROVED", ""),
        (S + S_GRID_FLAGS, 2 * GRID_CELLS, "grid flags (DAT_00e57954)", "PROVED", ""),
        (S + S_GRID, GAME_SIZE * GRID_CELLS, "played/scheduled grid 22 x 17 (DAT_00e57c40)", "PROVED", "Finn 0x917EA"),
        (S + S_SCORES, SCORE_BYTES * GRID_CELLS, "quarter scores 5 + 5 per cell (DAT_00e587f0)", "PROVED", "side order HYPOTHESIS"),
        (S + S_SCORES + SCORE_BYTES * GRID_CELLS, 2, "pad", "OPAQUE", ""),
        (S + S_AWARDS, AWARD_ROWS * AWARD_SLOTS * AWARD_SIZE, "17 x 5 award records (DAT_00e5968c)", "HYPOTHESIS", "two player refs each"),
        (S + S_WORDS_2864, 0x264, "306 u16 (DAT_00e59fd8)", "OPAQUE", ""),
        (S + S_BYTES_2AC8, 4, "4 bytes (DAT_00e5a23c)", "OPAQUE", ""),
        (S + S_STATS_HEAD, 4, "league stat head dword (FUN_001349a0)", "OPAQUE", ""),
        (S + S_STATS, S_STATS_ROWS * S_STATS_ROW_SIZE, "league stat tables, 17 rows x 0x32C (FUN_001349a0)", "HYPOTHESIS", ""),
        (S + S_STATS + S_STATS_ROWS * S_STATS_ROW_SIZE, S_STATS_TAIL, "league stat tail (FUN_001349a0)", "HYPOTHESIS", ""),
        (S + S_TAIL, S_TAIL_SIZE, "season block tail", "OPAQUE", ""),
        (F + F_ORDERS, F_ORDER_TABLES * NFL_TEAMS * 4, "14 per-team byte tables (DAT_00e3c0b4..)", "HYPOTHESIS", "table 0 = team permutation"),
        (F + F_DWORD_700, 4, "dword (DAT_00e3c0ac)", "OPAQUE", ""),
        (F + F_BYTES_704, 4, "4 bytes (DAT_00e3c0a4/a8/b0, e3c274)", "OPAQUE", ""),
        (F + F_LOG, F_LOG_CAPACITY * F_LOG_SIZE, "log 256 x 12 (DAT_00e40588)", "HYPOTHESIS", "count at F+0x1308"),
        (F + F_LOG_COUNT, 2, "log count", "PROVED", ""),
        (F + F_LOG_FLAG, 2, "log flag + pad", "OPAQUE", ""),
        (F + F_TEAM_REFS_A, 8 * NFL_TEAMS, "per-team player ref A (DAT_00e41898)", "HYPOTHESIS", ""),
        (F + F_TEAM_REFS_B, 8 * NFL_TEAMS, "per-team player ref B (DAT_00e41a18)", "HYPOTHESIS", ""),
        (F + F_TEAM_BYTES_150C, NFL_TEAMS, "per-team byte (DAT_00e41b98)", "OPAQUE", ""),
        (F + F_FLAG_152C, 4, "flag (DAT_00e41bd8)", "OPAQUE", ""),
        (F + F_TEAM_FLOATS, 4 * NFL_TEAMS, "per-team f32 (DAT_00e41bdc)", "HYPOTHESIS", ""),
        (F + F_TEAM_RANK, NFL_TEAMS, "per-team rank 1..32 (DAT_00e41c5c)", "HYPOTHESIS", ""),
        (F + F_SALARY_CAP, 4, "salary cap $1000 (DAT_00e3c278)", "PROVED", "Finn 0x9ACCC"),
        (F + F_TRADES, F_TRADE_COUNT * F_TRADE_SIZE, "15 trade records (FUN_002d06d0)", "PROVED", "layout; meaning HYPOTHESIS"),
        (F + F_FA_BIDS, F_FA_BID_COUNT * F_FA_BID_SIZE, "100 free-agent bid slots (FUN_002d05b0)", "PROVED", "layout"),
        (F + F_TEAM_BOARDS, NFL_TEAMS * F_BOARD_SLOTS * F_BOARD_ENTRY, "32 x 36 player boards (DAT_00e3cc40)", "HYPOTHESIS", ""),
        (F + F_BYTE_2E82, 1, "byte (DAT_00e3f060)", "OPAQUE", ""),
        (F + F_TEAM_ORDER_2, NFL_TEAMS, "team permutation (DAT_00e41bb8)", "HYPOTHESIS", ""),
        (F + F_TEAM_ORDER_2 + NFL_TEAMS, 1, "pad", "OPAQUE", ""),
        (F + F_TEAM_RECORDS, NFL_TEAMS * F_TEAM_RECORD_SIZE, "32 x 36 team records (DAT_00e41ce0)", "HYPOTHESIS", "seven f32 0.5"),
        (F + F_TEAM_RECORDS + NFL_TEAMS * F_TEAM_RECORD_SIZE, 8, "8 bytes before the ledger count", "OPAQUE", ""),
        (F + F_LEDGER_COUNT, 4, "ledger count (DAT_00e3f06c)", "PROVED", ""),
        (F + F_LEDGER, F_LEDGER_CAPACITY * F_LEDGER_SIZE, "ledger 600 x 12 (DAT_00e3f070)", "HYPOTHESIS", "player + team refs"),
        (F + F_TEAM_DWORDS_4F50, 4 * NFL_TEAMS, "per-team dword (DAT_00e42160)", "OPAQUE", ""),
        (F + F_INJURED_RESERVE, NFL_TEAMS * IR_SLOTS * IR_ENTRY, "injured reserve 32 x 5 (DAT_00e421e0)", "PROVED", "Finn 0x9E6CC"),
        (F + F_TEAM_BLOCKS, NFL_TEAMS * F_TEAM_BLOCK_SIZE, "32 x 2000-byte team blocks (DAT_00e42460)", "OPAQUE", ""),
        (F + F_TEAM_DWORDS_14C50, 4 * NFL_TEAMS, "per-team dword (DAT_00e3d210)", "OPAQUE", ""),
        (F + F_TEAM_DWORDS_14CD0, 4 * NFL_TEAMS, "per-team dword (DAT_00e3d290)", "OPAQUE", ""),
        (F + F_ROSTER_SLOT_BYTES, NFL_TEAMS * rr.TEAM_SLOTS * F_ROSTER_SLOT_SIZE, "32 x 65 x 3 roster-slot bytes (DAT_00e51f60)", "OPAQUE", ""),
    ]
    regions = [Region(*row) for row in rows]
    regions.sort(key=lambda r: r.offset)
    return regions


REGIONS: tuple[Region, ...] = tuple(_regions())


def regions_cover_file() -> bool:
    """True when the region map tiles the whole file without a gap or an overlap."""

    position = 0
    for region in REGIONS:
        if region.offset != position:
            return False
        position = region.end
    return position == FRANCHISE_SAVE_SIZE


def load_franchise(path: Path | str, *, require_signature: bool = True) -> FranchiseSave:
    return FranchiseSave.load(path, require_signature=require_signature)


def is_franchise_save(payload: bytes) -> bool:
    try:
        FranchiseSave(payload)
    except FranchiseSaveError:
        return False
    return True


__all__ = ["FranchiseSave", "FranchiseSaveError", "SeasonHeader", "Game", "Coach", "TeamSeason",
           "InjuredReserveEntry", "Region", "REGIONS", "regions_cover_file", "load_franchise", "is_franchise_save",
           "FRANCHISE_SAVE_SIZE", "SEASON_BLOCK", "FRONT_OFFICE_BLOCK", "TEAM_STAT_FIELDS", "TEAM_STAT_NAMES",
           "COACH_FIELDS", "COACH_RATINGS", "COACH_TENDENCIES", "STAGE_NAMES", "DISPLAY_YEAR_BASE"]
