"""Franchise season year, postseason calendar and 18-week season length for ESPN NFL 2K5 (executable patch).

Everything below was read from the retail ``default.xbe`` (sha256 73105b17...) with Ghidra and capstone;
nothing has been witnessed in xemu yet.  Three independent groups, each with ``status``/``apply``:

``year`` -- the franchise calendar year is ``2004 + season index`` at five code sites (the sixth,
  the preseason generator's ``add al,4``, went away with the ``preseason`` group's in-place rewrite of
  that generator: it now takes its year from the template).  The group also carries the two sites
  that make **player ages** follow the year: the rookie generator FUN_002be6f0 seeds every drafted
  player's two-digit birth year as ``(season + 80..82) % 100`` (``add ebx,0x50`` / ``add edi,0x52`` at
  0x2BE815 / 0x2BE806, i.e. born 1980-82 in the first season -- 22 years too old in a 2026
  franchise), so the base moves with the year (2026: 102..104 -> 02..04), and the player card's
  DOB line (FUN_00145d20, "%d/%d/%d" with the raw two-digit year) is rewritten in place to print a
  four-digit year (two-digit years up to ``year + 4 - 2000`` are 2000s).  There is no age
  arithmetic anywhere in the executable: the roster spreadsheet shows HT/WT/YRS PRO/COLLEGE and
  the card shows DOB, so the 2004 roster's players keep their 2004 birth dates until the roster
  changes.  Four ``imm32``
  sites format the year for the UI (FUN_00247ac0 ``add eax,0x7d4`` -> the "%d" year string,
  cb_001c1830 and FUN_0024c480 date lines ``lea edx,[eax+ecx+0x7d4]`` (+1 for months before June),
  FUN_0021b5f0 season history ``add edx,0x7d4``) and two ``imm8`` sites seed the schedule generators'
  two-digit year (``add al,4`` in the regular-season generator FUN_002bf270 at 0x2BF5C0 and in the
  preseason generator FUN_002bec20 at 0x2BEF6A: Thanksgiving of ``2000 + 4 + season`` anchors every
  generated calendar).  ``apply(year=2026)`` writes 2026 / 26 to all six.

``calendar`` -- the twelve postseason kickoff records live in ``.data`` at 0xACD6C8 (8 bytes each:
  ``[0][home][away][month][day][0][hour12][minute]``; the season-start routine FUN_002a7e50 copies them
  into grid rows WC/WC/WC/WC/DIV/DIV/DIV/DIV/CONF/CONF/SB/PB with the teams filled in).  Retail dates
  are the 2004-05 postseason (Jan 8/9, 15/16, 23, 30, Feb 6).  The 2026-27 preset uses the league's
  published dates (Wild Card Jan 16-17, Divisional Jan 23-24, Championship Jan 31, Super Bowl LXI
  Feb 14 2027) with the standard kickoff windows; the exact playoff kickoff times are announced in
  January and can be edited by hand.  The Super Bowl venue selector FUN_001332b0 picks the neutral
  stadium by season index through a five-entry jump table at 0x133354 (s40 Jacksonville, s42 Detroit,
  s43 Miami, s41 Glendale, s44 Los Angeles, then s45); the preset points season 0 at the Los Angeles
  entry (Super Bowl LXI is at SoFi Stadium).

``season_length`` -- the schedule grid is 22 rows x 17 slots (``.data`` 0xE57C40, FUN_000c4f10).  Retail
  uses rows 0-16 for the 17 regular-season weeks and 17-21 for Wild Card, Divisional, Conference,
  Super Bowl and Pro Bowl.  Eighteen regular weeks need row 17, so the postseason moves to rows 18-21
  and the Pro Bowl (a placeholder game between teams 32/33) is dropped: the grid has no row 22.  The
  number of simulated weeks per stage is data (byte +4 of the Season row of the stage table at
  ``.rdata`` 0x515140: 0x11 -> 0x12); the Wild Card row is hard-coded once at the Postseason transition
  (FUN_002480b0 ``mov ecx,0x11`` -> 0x12) and read back from ``DAT_00e576b0`` by the season-start
  routine, so most row arithmetic follows.  What is left are literal comparisons against rows
  16/17/18/19/20/21 in 40 sites (round predicates FUN_00133a30..FUN_00133af0, the weekly tick, the
  schedule screen, standings/momentum, injuries, weekly prep, the two schedule-copy loops that stop at
  the address of row 17, and the generator's own week loops), every one listed in ``WEEK_SITES`` with
  the instruction it lives in.  The Pro Bowl record write in FUN_002a7e50 is jumped over and the row
  bound it leaves in ``DAT_00e576b0`` stays 22.

  2026-09-03 second pass: a capstone walk of every call to the week/row accessors found 94 more row
  literals the first sweep missed (``_MISSED_ROW_SITES``): the seven bracket-advance routines at
  0x2471B0..0x247690 (49 ``mov ecx,row`` immediates -- without them the 18-week postseason would read
  week 18 as the wild-card row and write the divisional round into the wild-card row), the bracket
  membership test FUN_002476c0, the champion lookup FUN_00247a20, the draft order FUN_0031e210, the
  Pro Bowl coaches, the Super Bowl presentation, the owner-goal callbacks at 0x2BA240.., three UI
  callbacks and the Playoff Picture's week thresholds.

``playoffs_14`` -- the 2020+ seven-seed / six-wild-card-game bracket, implemented in
  ``nfl2k5_playoffs14`` and exposed here as a fourth group so one ``apply`` builds the 2026 executable.

Pattern-checked against the retail bytes, touched section digests recomputed.  Unverified at runtime
(the bracket code has been executed under the unicorn emulator, see tests/nfl2k5_playoffs14_test.py).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Mapping, Sequence

from .nfl2k5_bump_strength import _section_for_offset, _sections, section_digest

IMAGE_BASE = 0x10000
RETAIL_YEAR = 2004
DEFAULT_YEAR = 2026
RETAIL_REGULAR_WEEKS = 17
PATCHED_REGULAR_WEEKS = 18
GRID_ROWS = 22
GRID_SLOTS = 17
GRID_VA = 0x00E57C40
GRID_ROW_BYTES = GRID_SLOTS * 8
STAGE_TABLE_VA = 0x00515140
SEASON_WEEKS_VA = STAGE_TABLE_VA + 8 * 16 + 4        # Season row, byte +4 = weeks to simulate
POSTSEASON_WEEKS_VA = STAGE_TABLE_VA + 9 * 16 + 4    # Postseason row, byte +4
POSTSEASON_TABLE_VA = 0x00ACD6C8
POSTSEASON_RECORDS = 12
SB_VENUE_TABLE_VA = 0x00133354
SB_VENUE_CASES = {"s40_jacksonville": 0x001332C5, "s42_detroit": 0x001332CC, "s43_miami": 0x001332D3,
                  "s41_glendale": 0x001332DA, "s44_los_angeles": 0x001332E1}


class SeasonLengthError(ValueError):
    """The season patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SeasonLengthError(message)


@dataclass(frozen=True)
class Site:
    label: str
    va: int                 # address of the first patched byte
    retail: bytes
    patched: bytes
    note: str

    @property
    def size(self) -> int:
        return len(self.retail)


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


# -- year -----------------------------------------------------------------------------------------

_YEAR_IMM32 = (
    ("ui_year_string", 0x00247AC7, "FUN_00247ac0: add eax,0x7d4 -> the franchise year '%d' string"),
    ("date_line_year", 0x001C1847, "cb_001c1830: lea edx,[eax+ecx+0x7d4] -> '<Month> <day>, <year>'"),
    ("history_year", 0x0021B6FE, "FUN_0021b5f0: add edx,0x7d4 -> season history / records year"),
    ("schedule_row_year", 0x0024C7C1, "FUN_0024c480: lea edx,[eax+ecx+0x7d4] (+1 when month < June)"),
)
_YEAR_IMM8 = (
    ("regular_season_generator_year", 0x002BF5C1, "FUN_002bf270: add al,4 -> Thanksgiving anchor year (2000+)"),
)
# The preseason generator's own ``add al,4`` (0x2BEF6B) is inside the region the ``preseason`` group
# rewrites; the rewritten generator anchors on the template's year byte instead.

# -- player ages: the rookie birth-year seed and the DOB line ------------------------------------
ROOKIE_BIRTH_BASE_VA = 0x002BE817    # FUN_002be6f0: add ebx,0x50 -> low end of the two-digit birth year
ROOKIE_BIRTH_TOP_VA = 0x002BE808     # FUN_002be6f0: add edi,0x52 -> high end (rand % 3 spread)
RETAIL_ROOKIE_BIRTH_BASE = 0x50      # 2004 - 1924: rookies born 1980..1982
DOB_FORMATTER_VA = 0x00145D20        # FUN_00145d20: player card "DOB:" value, "%d/%d/%d" (month, day, yy)
DOB_FORMATTER_SIZE = 0x70            # up to FUN_00145d90 (15 nop bytes of slack in retail)
DOB_FORMAT_STRING_VA = 0x00E7CBEC    # "%d/%d/%d" (kept: the year argument becomes four digits)
DOB_LINE_BUFFER_INDEX_VA = 0x00BD7590
DOB_LINE_BUFFER_VA = 0x00BD7594
DOB_LINE_NEXT_FN = 0x00145840        # advances the rotating 0x200-byte text buffer
DOB_LINE_FORMAT_FN = 0x0004A410      # swprintf-like (ecx = buffer, edx = size, fmt, args)
RETAIL_DOB_FORMATTER = bytes.fromhex(
    "83ec0ce818fbffff8b41188bc88bd0c1e91583e17fc1e80c83e00f894c24088b0d9075bd00c1ea108944240083e21f8d44240050c1e1098954240868eccbe70081c19475bd00ba00010000e8a046f0ffa19075bd00c1e009059475bd0083c40cc3909090909090909090909090909090"
)


def rookie_birth_base(year: int) -> int:
    """Two-digit birth year base of a first-season draft class: ``year - 1924`` (2026 -> 102 -> '02')."""
    base = year - 1924
    _require(0 < base < 0x80, "rookie birth-year base must fit a signed imm8 (year <= 2051)")
    return base


def dob_pivot(year: int) -> int:
    """Two-digit years up to this value print as 2000s on the DOB line (2004 -> 8, 2026 -> 30)."""
    return (year + 4 - 2000) % 100


def dob_formatter_bytes(year: int) -> bytes:
    """FUN_00145d20 rewritten to print a four-digit birth year (same buffer, format and calls)."""
    pivot = dob_pivot(year)
    code = bytearray()
    code += bytes.fromhex("83ec0c")                                                   # sub esp,0xc
    code += b"\xe8" + struct.pack("<i", DOB_LINE_NEXT_FN - (DOB_FORMATTER_VA + len(code) + 5))
    code += bytes.fromhex("8b4118")                                                   # mov eax,[ecx+0x18]
    code += bytes.fromhex("8bd0")                                                     # mov edx,eax
    code += bytes.fromhex("c1e815")                                                   # shr eax,0x15
    code += bytes.fromhex("83e07f")                                                   # and eax,0x7f
    code += bytes.fromhex("83f8") + bytes([pivot])                                    # cmp eax,pivot
    code += bytes.fromhex("8d88") + struct.pack("<I", 1900)                           # lea ecx,[eax+1900]
    code += bytes.fromhex("7703")                                                     # ja +3 (1900s)
    code += bytes.fromhex("83c164")                                                   # add ecx,100 (2000s)
    code += bytes.fromhex("894c2408")                                                 # mov [esp+8],ecx
    code += bytes.fromhex("8bc2")                                                     # mov eax,edx
    code += bytes.fromhex("c1e80c")                                                   # shr eax,0xc
    code += bytes.fromhex("83e00f")                                                   # and eax,0xf (month)
    code += bytes.fromhex("890424")                                                   # mov [esp],eax
    code += bytes.fromhex("c1ea10")                                                   # shr edx,0x10
    code += bytes.fromhex("83e21f")                                                   # and edx,0x1f (day)
    code += bytes.fromhex("89542404")                                                 # mov [esp+4],edx
    code += bytes.fromhex("8b0d") + struct.pack("<I", DOB_LINE_BUFFER_INDEX_VA)      # mov ecx,[index]
    code += bytes.fromhex("8d0424")                                                   # lea eax,[esp]
    code += bytes.fromhex("50")                                                       # push eax
    code += bytes.fromhex("c1e109")                                                   # shl ecx,9
    code += b"\x68" + struct.pack("<I", DOB_FORMAT_STRING_VA)                        # push fmt
    code += bytes.fromhex("81c1") + struct.pack("<I", DOB_LINE_BUFFER_VA)             # add ecx,buffer
    code += bytes.fromhex("ba00010000")                                               # mov edx,0x100
    code += b"\xe8" + struct.pack("<i", DOB_LINE_FORMAT_FN - (DOB_FORMATTER_VA + len(code) + 5))
    code += b"\xa1" + struct.pack("<I", DOB_LINE_BUFFER_INDEX_VA)                    # mov eax,[index]
    code += bytes.fromhex("c1e009")                                                   # shl eax,9
    code += b"\x05" + struct.pack("<I", DOB_LINE_BUFFER_VA)                          # add eax,buffer
    code += bytes.fromhex("83c40c")                                                   # add esp,0xc
    code += bytes.fromhex("c3")                                                       # ret
    _require(len(code) <= DOB_FORMATTER_SIZE, "DOB formatter rewrite does not fit")
    return bytes(code) + b"\x90" * (DOB_FORMATTER_SIZE - len(code))


def year_sites(year: int) -> tuple[Site, ...]:
    _require(2000 <= year <= 2098, "year must be 2000..2098 (two-digit generator years)")
    sites = [Site(label, va, _u32(RETAIL_YEAR), _u32(year), note) for label, va, note in _YEAR_IMM32]
    sites += [Site(label, va, bytes([RETAIL_YEAR - 2000]), bytes([year - 2000]), note)
              for label, va, note in _YEAR_IMM8]
    base = rookie_birth_base(year)
    sites += [
        Site("rookie_birth_base", ROOKIE_BIRTH_BASE_VA, bytes([RETAIL_ROOKIE_BIRTH_BASE]), bytes([base]),
             "FUN_002be6f0: add ebx,imm8 -> draft-class birth year = (season + base + 0..2) % 100"),
        Site("rookie_birth_top", ROOKIE_BIRTH_TOP_VA, bytes([RETAIL_ROOKIE_BIRTH_BASE + 2]), bytes([base + 2]),
             "FUN_002be6f0: add edi,imm8 -> the top of the same three-year spread"),
        Site("dob_four_digit_year", DOB_FORMATTER_VA, RETAIL_DOB_FORMATTER, dob_formatter_bytes(year),
             f"FUN_00145d20 rewritten: player-card DOB prints a four-digit year (two-digit <= {dob_pivot(year)} -> 2000s)"),
    ]
    return tuple(sites)


# -- calendar -------------------------------------------------------------------------------------

def postseason_record(month: int, day: int, hour12: int, minute: int) -> bytes:
    _require(1 <= month <= 12 and 1 <= day <= 31, "postseason date out of range")
    _require(0 <= hour12 <= 12 and 0 <= minute <= 59, "postseason kickoff out of range")
    return bytes([0, 0, 0, month, day, 0, hour12 % 12, minute])


RETAIL_POSTSEASON = (
    (1, 8, 0, 30), (1, 8, 4, 5), (1, 9, 0, 35), (1, 9, 4, 15),        # wild card (2005)
    (1, 15, 0, 35), (1, 15, 4, 15), (1, 16, 0, 40), (1, 16, 4, 15),  # divisional
    (1, 23, 1, 35), (1, 23, 4, 15),                                  # conference championships
    (1, 30, 4, 0),                                                   # Super Bowl XXXIX
    (2, 6, 4, 0),                                                    # Pro Bowl placeholder
)
# 2026-27 dates: Wild Card Jan 16-18, Divisional Jan 23-24, Championship Jan 31, Super Bowl LXI
# Feb 14 2027 (NFL schedule release, May 14 2026).  2K5 plays four wild-card games (12-team bracket).
CALENDAR_2026 = (
    (1, 16, 4, 30), (1, 16, 8, 15), (1, 17, 1, 0), (1, 17, 4, 30),
    (1, 23, 4, 30), (1, 23, 8, 15), (1, 24, 3, 0), (1, 24, 6, 30),
    (1, 31, 3, 0), (1, 31, 6, 30),
    (2, 14, 6, 30),
    (2, 7, 3, 0),
)
POSTSEASON_LABELS = ("wild_card_1", "wild_card_2", "wild_card_3", "wild_card_4", "divisional_1",
                     "divisional_2", "divisional_3", "divisional_4", "conference_1", "conference_2",
                     "super_bowl", "pro_bowl")


def postseason_table(records: Sequence[tuple[int, int, int, int]]) -> bytes:
    _require(len(records) == POSTSEASON_RECORDS, f"exactly {POSTSEASON_RECORDS} postseason records")
    return b"".join(postseason_record(*r) for r in records)


def calendar_sites(records: Sequence[tuple[int, int, int, int]] = CALENDAR_2026,
                   super_bowl_venue: str = "s44_los_angeles") -> tuple[Site, ...]:
    _require(super_bowl_venue in SB_VENUE_CASES, f"unknown Super Bowl venue key {super_bowl_venue}")
    return (
        Site("postseason_dates", POSTSEASON_TABLE_VA, postseason_table(RETAIL_POSTSEASON),
             postseason_table(records), "12 kickoff records copied into the postseason rows by FUN_002a7e50"),
        Site("super_bowl_venue_season0", SB_VENUE_TABLE_VA, _u32(SB_VENUE_CASES["s40_jacksonville"]),
             _u32(SB_VENUE_CASES[super_bowl_venue]), "FUN_001332b0 jump table entry for season index 0"),
    )


# -- season length (17 -> 18 regular-season weeks, Pro Bowl row dropped) ----------------------------

def _cmp8(label: str, va: int, retail: int, patched: int, note: str) -> Site:
    return Site(label, va, bytes([retail]), bytes([patched]), note)


ROW17_END_VA = GRID_VA + 17 * GRID_ROW_BYTES      # 0xE58548: first byte after the 17 retail regular rows
ROW18_END_VA = GRID_VA + 18 * GRID_ROW_BYTES      # 0xE585D0

WEEK_SITES: tuple[Site, ...] = (
    _cmp8("stage_table_season_weeks", SEASON_WEEKS_VA, 0x11, 0x12,
          ".rdata stage table row 8 (+4): weeks simulated by the Season stage (FUN_00247b20 / FUN_002480b0)"),
    _cmp8("stage_table_postseason_weeks", POSTSEASON_WEEKS_VA, 0x05, 0x04,
          ".rdata stage table row 9 (+4): postseason rows without the Pro Bowl"),
    Site("postseason_first_row", 0x00248665, _u32(0x11), _u32(0x12),
         "FUN_002480b0 stage 9: mov ecx,0x11 -> set_week(wild card row)"),
    _cmp8("is_last_regular_week", 0x00133B01, 0x10, 0x11, "FUN_00133af0: stage 8 and week == 16"),
    _cmp8("is_wild_card_week", 0x00133AC1, 0x11, 0x12, "FUN_00133ab0: stage 9 and week == 17"),
    _cmp8("is_divisional_week", 0x00133AA1, 0x12, 0x13, "FUN_00133a90"),
    _cmp8("is_conference_week", 0x00133A81, 0x13, 0x14, "FUN_00133a70"),
    _cmp8("is_super_bowl_week", 0x00133A41, 0x14, 0x15, "FUN_00133a30 (also the Super Bowl stadium classifier)"),
    _cmp8("is_pro_bowl_week", 0x00133A61, 0x15, 0x16, "FUN_00133a50: never true once the Pro Bowl row is gone"),
    _cmp8("is_pro_bowl_week_param", 0x00133ADF, 0x15, 0x16, "FUN_00133ad0"),
    _cmp8("pro_bowl_ui_cb", 0x000EBA69, 0x15, 0x16, "cb_000eba62: week == 21 Pro Bowl presentation"),
    _cmp8("weekly_tick_conference_guard", 0x00247E8F, 0x13, 0x14, "FUN_00247d40 stage 9: week != conference"),
    _cmp8("weekly_tick_champion", 0x00247E99, 0x14, 0x15, "FUN_00247d40 stage 9: week == Super Bowl -> FUN_00247a20"),
    _cmp8("weekly_tick_eliminated_wc", 0x00247EFD, 0x11, 0x12, "FUN_00247d40: 'eliminated in the Wildcard Round'"),
    _cmp8("weekly_tick_eliminated_div", 0x00247F31, 0x12, 0x13, "FUN_00247d40: 'Division Championships'"),
    _cmp8("weekly_tick_eliminated_conf", 0x00247F65, 0x13, 0x14, "FUN_00247d40: 'Conference Championships'"),
    _cmp8("schedule_round_switch_base", 0x0024C836, 0xEF, 0xEE,
          "FUN_0024c480: add eax,-0x11 -> round-name jump table base (Wild Card row)"),
    _cmp8("super_bowl_week_cb_2c01fd", 0x002C0204, 0x14, 0x15, "cb_002c01fd: week != Super Bowl"),
    _cmp8("late_postseason_cb_2c28dd", 0x002C28E4, 0x14, 0x15, "cb_002c28dd: week > conference"),
    _cmp8("next_round_not_super_bowl", 0x00134652, 0x14, 0x15, "FUN_001345e0"),
    _cmp8("next_round_not_pro_bowl", 0x00134657, 0x15, 0x16, "FUN_001345e0"),
    _cmp8("momentum_regular_a", 0x0027D8D2, 0x11, 0x12, "FUN_0027d7d0: row == 17 / row < 17 (regular-season game)"),
    _cmp8("momentum_regular_b", 0x0027D941, 0x11, 0x12, "FUN_0027d7d0"),
    _cmp8("momentum_regular_c", 0x0027D983, 0x11, 0x12, "FUN_0027d7d0"),
    _cmp8("headline_regular_a", 0x0015E81D, 0x11, 0x12, "cb_0015e060: 6 < week < 17 headlines"),
    _cmp8("headline_regular_b", 0x0015E853, 0x11, 0x12, "cb_0015e060: 11 < week < 17 headlines"),
    _cmp8("headline_last_regular", 0x0015E887, 0x10, 0x11, "cb_0015e060: week == 16"),
    _cmp8("headline_conference", 0x0015E896, 0x13, 0x14, "cb_0015e060: week == 19"),
    _cmp8("injury_beyond_regular_a", 0x0021DAA9, 0x11, 0x12, "FUN_0021da50: injury weeks > 17"),
    _cmp8("injury_beyond_regular_b", 0x0021DAB3, 0x11, 0x12, "FUN_0021da50: displayed week > 17"),
    _cmp8("injury_beyond_regular_c", 0x0021DAB8, 0x11, 0x12, "FUN_0021da50: return row < 17"),
    _cmp8("injury_beyond_regular_d", 0x0021DAD7, 0x11, 0x12, "FUN_0021da50: displayed week <= 17"),
    _cmp8("weekly_prep_window_a", 0x002CEEB8, 0x10, 0x11, "FUN_002ceea0: displayed week < 16"),
    _cmp8("weekly_prep_window_b", 0x002CEE1B, 0x10, 0x11, "FUN_002cee10: displayed week < 16"),
    _cmp8("weekly_prep_stage_bound", 0x002CF6E1, 0x13, 0x14, "cb_002cf680: week < 19"),
    _cmp8("weekly_prep_week16_event", 0x002CF627, 0x10, 0x11, "FUN_002cf620: displayed week == 16 flavour event"),
    _cmp8("theme_by_week", 0x003607F8, 0x12, 0x13, "FUN_00360790: week < 18 presentation theme"),
    _cmp8("pregame_standings_a", 0x00132F4F, 0x10, 0x11, "FUN_00132ed0: week < 16 standings refresh"),
    _cmp8("pregame_regular_rows", 0x00132F92, 0x11, 0x12, "FUN_00132ed0: week < 17 regular-row copy"),
    Site("pregame_row_bound", 0x0013315C, _u32(ROW17_END_VA), _u32(ROW18_END_VA),
         "FUN_00132ed0: cmp eax,0xe58548 -> end of the regular-season rows"),
    _cmp8("pregame_standings_b", 0x001331F4, 0x10, 0x11, "FUN_00132ed0: week < 16"),
    _cmp8("sim_regular_rows", 0x00133D76, 0x11, 0x12, "FUN_00133cf0: week < 17 regular-row copy"),
    Site("sim_row_bound", 0x00133EE4, _u32(ROW17_END_VA), _u32(ROW18_END_VA),
         "FUN_00133cf0: cmp eax,0xe58548"),
    _cmp8("generator_thanksgiving_search", 0x002BF4CA, 0x11, 0x12, "FUN_002bf270: weeks 12..16 searched for the DAL/DET swap"),
    _cmp8("generator_marquee_weeks", 0x002BF5A7, 0x11, 0x12, "FUN_002bf270: prime-time pick per week"),
    _cmp8("generator_date_weeks", 0x002BF744, 0x11, 0x12, "FUN_002bf270: re-dating loop (seasons after the first)"),
    _cmp8("generator_saturday_from", 0x002BF6CB, 0x0F, 0x10, "FUN_002bf270: Saturday games from week index 16"),
    Site("pro_bowl_record_skip", 0x002A82AE, bytes.fromhex("6820d7ac00"), bytes.fromhex("eb22909090"),
         "FUN_002a7e50: jump over the Pro Bowl record/flag writes (row 22 does not exist)"),
    Site("pro_bowl_row_bound", 0x002A82D2, bytes.fromhex("8d4e01"), bytes.fromhex("8bce90"),
         "FUN_002a7e50: DAT_00e576b0 = 22 instead of 23"),
)


# Sites the first sweep missed (found 2026-09-03 by walking every call to the week/row accessors with
# capstone; each is a row literal 0x11..0x15 or a displayed-week literal fed to them).  All +1.
_MISSED_ROW_SITES: tuple[Site, ...] = (
    _cmp8("bracket_row_2471b2", 0x002471B3, 0x13, 0x14, "FUN_002471b0 (Super Bowl from the conference winners)"),
    _cmp8("bracket_row_2471ca", 0x002471CB, 0x13, 0x14, "FUN_002471b0 (Super Bowl from the conference winners)"),
    _cmp8("bracket_row_2471e4", 0x002471E5, 0x14, 0x15, "FUN_002471b0 (Super Bowl from the conference winners)"),
    _cmp8("bracket_row_2471f2", 0x002471F3, 0x14, 0x15, "FUN_002471b0 (Super Bowl from the conference winners)"),
    _cmp8("bracket_row_2471fe", 0x002471FF, 0x14, 0x15, "FUN_002471b0 (Super Bowl from the conference winners)"),
    _cmp8("bracket_row_24720a", 0x0024720B, 0x13, 0x14, "FUN_002471b0 (Super Bowl from the conference winners)"),
    _cmp8("bracket_row_24721b", 0x0024721C, 0x13, 0x14, "FUN_002471b0 (Super Bowl from the conference winners)"),
    _cmp8("bracket_row_247272", 0x00247273, 0x12, 0x13, "FUN_00247270 (AFC conference game from the divisional winners)"),
    _cmp8("bracket_row_24728a", 0x0024728B, 0x12, 0x13, "FUN_00247270 (AFC conference game from the divisional winners)"),
    _cmp8("bracket_row_2472a1", 0x002472A2, 0x13, 0x14, "FUN_00247270 (AFC conference game from the divisional winners)"),
    _cmp8("bracket_row_2472af", 0x002472B0, 0x13, 0x14, "FUN_00247270 (AFC conference game from the divisional winners)"),
    _cmp8("bracket_row_2472bb", 0x002472BC, 0x13, 0x14, "FUN_00247270 (AFC conference game from the divisional winners)"),
    _cmp8("bracket_row_2472c7", 0x002472C8, 0x12, 0x13, "FUN_00247270 (AFC conference game from the divisional winners)"),
    _cmp8("bracket_row_2472d8", 0x002472D9, 0x12, 0x13, "FUN_00247270 (AFC conference game from the divisional winners)"),
    _cmp8("bracket_row_247325", 0x00247326, 0x12, 0x13, "FUN_00247320 (NFC conference game)"),
    _cmp8("bracket_row_24733a", 0x0024733B, 0x12, 0x13, "FUN_00247320 (NFC conference game)"),
    _cmp8("bracket_row_247358", 0x00247359, 0x13, 0x14, "FUN_00247320 (NFC conference game)"),
    _cmp8("bracket_row_247369", 0x0024736A, 0x13, 0x14, "FUN_00247320 (NFC conference game)"),
    _cmp8("bracket_row_247378", 0x00247379, 0x13, 0x14, "FUN_00247320 (NFC conference game)"),
    _cmp8("bracket_row_247387", 0x00247388, 0x12, 0x13, "FUN_00247320 (NFC conference game)"),
    _cmp8("bracket_row_247398", 0x00247399, 0x12, 0x13, "FUN_00247320 (NFC conference game)"),
    _cmp8("bracket_row_2473e2", 0x002473E3, 0x11, 0x12, "FUN_002473e0 (AFC divisional game 0 away = lowest wild-card winner)"),
    _cmp8("bracket_row_2473fa", 0x002473FB, 0x11, 0x12, "FUN_002473e0 (AFC divisional game 0 away = lowest wild-card winner)"),
    _cmp8("bracket_row_247411", 0x00247412, 0x12, 0x13, "FUN_002473e0 (AFC divisional game 0 away = lowest wild-card winner)"),
    _cmp8("bracket_row_24741f", 0x00247420, 0x12, 0x13, "FUN_002473e0 (AFC divisional game 0 away = lowest wild-card winner)"),
    _cmp8("bracket_row_24742b", 0x0024742C, 0x12, 0x13, "FUN_002473e0 (AFC divisional game 0 away = lowest wild-card winner)"),
    _cmp8("bracket_row_247437", 0x00247438, 0x11, 0x12, "FUN_002473e0 (AFC divisional game 0 away = lowest wild-card winner)"),
    _cmp8("bracket_row_247448", 0x00247449, 0x11, 0x12, "FUN_002473e0 (AFC divisional game 0 away = lowest wild-card winner)"),
    _cmp8("bracket_row_247482", 0x00247483, 0x11, 0x12, "FUN_00247480 (AFC divisional game 1 away)"),
    _cmp8("bracket_row_24749a", 0x0024749B, 0x11, 0x12, "FUN_00247480 (AFC divisional game 1 away)"),
    _cmp8("bracket_row_2474b4", 0x002474B5, 0x12, 0x13, "FUN_00247480 (AFC divisional game 1 away)"),
    _cmp8("bracket_row_2474c5", 0x002474C6, 0x12, 0x13, "FUN_00247480 (AFC divisional game 1 away)"),
    _cmp8("bracket_row_2474d4", 0x002474D5, 0x12, 0x13, "FUN_00247480 (AFC divisional game 1 away)"),
    _cmp8("bracket_row_2474e0", 0x002474E1, 0x11, 0x12, "FUN_00247480 (AFC divisional game 1 away)"),
    _cmp8("bracket_row_2474f1", 0x002474F2, 0x11, 0x12, "FUN_00247480 (AFC divisional game 1 away)"),
    _cmp8("bracket_row_247535", 0x00247536, 0x11, 0x12, "FUN_00247530 (NFC divisional game 2 away)"),
    _cmp8("bracket_row_24754a", 0x0024754B, 0x11, 0x12, "FUN_00247530 (NFC divisional game 2 away)"),
    _cmp8("bracket_row_247564", 0x00247565, 0x12, 0x13, "FUN_00247530 (NFC divisional game 2 away)"),
    _cmp8("bracket_row_247575", 0x00247576, 0x12, 0x13, "FUN_00247530 (NFC divisional game 2 away)"),
    _cmp8("bracket_row_247584", 0x00247585, 0x12, 0x13, "FUN_00247530 (NFC divisional game 2 away)"),
    _cmp8("bracket_row_247593", 0x00247594, 0x11, 0x12, "FUN_00247530 (NFC divisional game 2 away)"),
    _cmp8("bracket_row_2475a4", 0x002475A5, 0x11, 0x12, "FUN_00247530 (NFC divisional game 2 away)"),
    _cmp8("bracket_row_2475e5", 0x002475E6, 0x11, 0x12, "FUN_002475e0 (NFC divisional game 3 away)"),
    _cmp8("bracket_row_2475fa", 0x002475FB, 0x11, 0x12, "FUN_002475e0 (NFC divisional game 3 away)"),
    _cmp8("bracket_row_247611", 0x00247612, 0x12, 0x13, "FUN_002475e0 (NFC divisional game 3 away)"),
    _cmp8("bracket_row_247622", 0x00247623, 0x12, 0x13, "FUN_002475e0 (NFC divisional game 3 away)"),
    _cmp8("bracket_row_247631", 0x00247632, 0x12, 0x13, "FUN_002475e0 (NFC divisional game 3 away)"),
    _cmp8("bracket_row_247640", 0x00247641, 0x11, 0x12, "FUN_002475e0 (NFC divisional game 3 away)"),
    _cmp8("bracket_row_247651", 0x00247652, 0x11, 0x12, "FUN_002475e0 (NFC divisional game 3 away)"),
    _cmp8("in_bracket_row_2476c5", 0x002476C6, 0x11, 0x12, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_2476dc", 0x002476DD, 0x11, 0x12, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_2476ef", 0x002476F0, 0x11, 0x12, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_247702", 0x00247703, 0x11, 0x12, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_247715", 0x00247716, 0x11, 0x12, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_247728", 0x00247729, 0x11, 0x12, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_24773b", 0x0024773C, 0x11, 0x12, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_24774e", 0x0024774F, 0x11, 0x12, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_247762", 0x00247763, 0x12, 0x13, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_247779", 0x0024777A, 0x12, 0x13, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_247790", 0x00247791, 0x12, 0x13, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("in_bracket_row_2477a7", 0x002477A8, 0x12, 0x13, "FUN_002476c0: team appears in a wild-card game or hosts a divisional game"),
    _cmp8("champion_row_247a29", 0x00247A2A, 0x14, 0x15, "FUN_00247a20: Super Bowl winner/loser"),
    _cmp8("champion_row_247a35", 0x00247A36, 0x14, 0x15, "FUN_00247a20: Super Bowl winner/loser"),
    _cmp8("draft_order_row_31e241", 0x0031E242, 0x14, 0x15, "FUN_0031e210: draft order from the Super Bowl / conference results"),
    _cmp8("draft_order_row_31e254", 0x0031E255, 0x14, 0x15, "FUN_0031e210: draft order from the Super Bowl / conference results"),
    _cmp8("draft_order_row_31e267", 0x0031E268, 0x13, 0x14, "FUN_0031e210: draft order from the Super Bowl / conference results"),
    _cmp8("draft_order_row_31e276", 0x0031E277, 0x13, 0x14, "FUN_0031e210: draft order from the Super Bowl / conference results"),
    _cmp8("pro_bowl_coach_row_1340bd", 0x001340BE, 0x13, 0x14, "FUN_00134040: Pro Bowl coaches = conference-championship losers (dead once the Pro Bowl row is gone)"),
    _cmp8("pro_bowl_coach_row_1340d7", 0x001340D8, 0x13, 0x14, "FUN_00134040: Pro Bowl coaches = conference-championship losers (dead once the Pro Bowl row is gone)"),
    _cmp8("super_bowl_teams_row_2cda25", 0x002CDA26, 0x14, 0x15, "cb_002cda25: Super Bowl teams for the presentation"),
    _cmp8("super_bowl_teams_row_2cda4a", 0x002CDA4B, 0x14, 0x15, "cb_002cda25: Super Bowl teams for the presentation"),
    _cmp8("super_bowl_teams_row_2cda56", 0x002CDA57, 0x14, 0x15, "cb_002cda25: Super Bowl teams for the presentation"),
    _cmp8("owner_goal_row_2ba240", 0x002BA241, 0x14, 0x15, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("owner_goal_row_2ba258", 0x002BA259, 0x15, 0x16, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("owner_goal_row_2ba264", 0x002BA265, 0x14, 0x15, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("owner_goal_row_2ba272", 0x002BA273, 0x13, 0x14, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("owner_goal_row_2ba280", 0x002BA281, 0x12, 0x13, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("owner_goal_row_2ba28e", 0x002BA28F, 0x11, 0x12, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("owner_goal_row_2ba2c9", 0x002BA2CA, 0x11, 0x12, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("owner_goal_row_2ba2dc", 0x002BA2DD, 0x12, 0x13, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("owner_goal_row_2ba2ef", 0x002BA2F0, 0x13, 0x14, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("owner_goal_row_2ba302", 0x002BA303, 0x15, 0x16, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("owner_goal_row_2ba31c", 0x002BA31D, 0x14, 0x15, "cb_002ba240..: owner/crib goals ('make the playoffs', 'win a playoff game') by postseason row"),
    _cmp8("schedule_helper_sb_row", 0x0024CB9A, 0x14, 0x15, "cb_0024cb90: schedule-screen text for the Super Bowl row"),
    _cmp8("schedule_helper_pb_row", 0x0024CBA8, 0x15, 0x16, "cb_0024cb90: Pro Bowl row"),
    _cmp8("stage9_sb_week_cb", 0x002C0234, 0x14, 0x15, "cb_002c0220: stage 9 and week == Super Bowl"),
    _cmp8("results_text_sb_row", 0x003614F0, 0x14, 0x15, "cb_00361430: 'Week %d Results' vs Super Bowl format"),
    _cmp8("playoff_text_last_week_a", 0x0022038B, 0x10, 0x11, "FUN_00220350: displayed week == last regular week"),
    _cmp8("playoff_text_week15", 0x0022039D, 0x0F, 0x10, "FUN_00220350: week == second-to-last regular week"),
    _cmp8("playoff_text_last_week_row", 0x002203A3, 0x10, 0x11, "FUN_00220350: games of the last regular row"),
    _cmp8("playoff_text_last_week_b", 0x002203FA, 0x10, 0x11, "FUN_00220350: week < last regular week"),
    _cmp8("playoff_picture_final_field", 0x00368489, 0x11, 0x12, "cb_00368395: week > last regular week -> the playoff field only"),
    _cmp8("playoff_picture_hunt_4", 0x0036849A, 0x0D, 0x0E, "cb_00368395: week > 13 -> four teams in the hunt"),
    _cmp8("playoff_picture_hunt_5", 0x003684AD, 0x0B, 0x0C, "cb_00368395: week > 11 -> five teams in the hunt"),
)
WEEK_SITES = WEEK_SITES + _MISSED_ROW_SITES

GROUPS = ("year", "calendar", "season_length", "playoffs_14", "preseason")
XBE_GROUPS = ("year", "calendar", "season_length")   # the groups that live in this module


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int, sections=None) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in sections or _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise SeasonLengthError(f"VA 0x{va:x} is in no section")


def group_sites(group: str, *, year: int = DEFAULT_YEAR,
                calendar: Sequence[tuple[int, int, int, int]] = CALENDAR_2026,
                super_bowl_venue: str = "s44_los_angeles",
                calendar14: Sequence[tuple[int, int, int, int]] | None = None) -> tuple[Site, ...]:
    if calendar14 is None:
        from . import nfl2k5_playoffs14 as p14
        calendar14 = p14.CALENDAR_2026_14
    if group == "year":
        return year_sites(year)
    if group == "calendar":
        return calendar_sites(calendar, super_bowl_venue)
    if group == "season_length":
        return WEEK_SITES
    if group == "playoffs_14":
        from . import nfl2k5_playoffs14 as p14
        return tuple(Site(s.label, s.va, s.retail, s.patched, s.note) for s in p14.sites(calendar14))
    if group == "preseason":
        from . import nfl2k5_preseason as pre
        return tuple(Site(s.label, s.va, s.retail, s.patched, s.note) for s in pre.sites())
    raise SeasonLengthError(f"unknown group {group}")


def _site_state(payload: bytes, site: Site, sections) -> str:
    off = _offset(payload, site.va, sections)
    got = payload[off: off + site.size]
    return "retail" if got == site.retail else "applied" if got == site.patched else "foreign"


def group_status(payload: bytes, group: str, **kwargs) -> str:
    try:
        sections = _sections(payload)
        states = {_site_state(payload, s, sections) for s in group_sites(group, **kwargs)}
    except (SeasonLengthError, ValueError, struct.error):
        return "foreign"
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def read_year(payload: bytes) -> int | None:
    """The year the six sites agree on, or None when they disagree."""
    try:
        sections = _sections(payload)
        years = set()
        for label, va, _note in _YEAR_IMM32:
            years.add(struct.unpack_from("<I", payload, _offset(payload, va, sections))[0])
        for label, va, _note in _YEAR_IMM8:
            years.add(2000 + payload[_offset(payload, va, sections)])
    except (SeasonLengthError, ValueError, struct.error):
        return None
    return years.pop() if len(years) == 1 else None


def status(payload: bytes, **kwargs) -> dict[str, object]:
    year = read_year(payload)
    report: dict[str, object] = {"year": read_year(payload)}
    for group in GROUPS:
        report[group] = group_status(payload, group, **kwargs)
    if report["year"] == "foreign" and year not in (None, RETAIL_YEAR):
        report["year"] = f"applied:{year}"
    report["regular_weeks"] = (PATCHED_REGULAR_WEEKS if report["season_length"] == "applied"
                               else RETAIL_REGULAR_WEEKS if report["season_length"] == "retail" else None)
    report["playoff_teams"] = (14 if report["playoffs_14"] == "applied"
                               else 12 if report["playoffs_14"] == "retail" else None)
    report["preseason_games"] = (3 if report["preseason"] == "applied"
                                 else 4 if report["preseason"] == "retail" else None)
    return report


def apply(payload: bytes, *, groups: Sequence[str] = GROUPS, year: int = DEFAULT_YEAR,
          calendar: Sequence[tuple[int, int, int, int]] = CALENDAR_2026,
          super_bowl_venue: str = "s44_los_angeles",
          calendar14: Sequence[tuple[int, int, int, int]] | None = None) -> tuple[bytes, Mapping[str, object]]:
    """Patch the selected groups into a copy of ``payload`` (refuses anything not retail)."""
    for group in groups:
        _require(group in GROUPS, f"unknown group {group}")
    kwargs = {"year": year, "calendar": calendar, "super_bowl_venue": super_bowl_venue, "calendar14": calendar14}
    sections = _sections(payload)
    buf = bytearray(payload)
    touched: set[int] = set()
    edits: list[dict[str, object]] = []
    for group in groups:
        state = group_status(payload, group, **kwargs)
        _require(state == "retail", f"{group} sites are {state}, not retail")
        for site in group_sites(group, **kwargs):
            off = _offset(payload, site.va, sections)
            buf[off: off + site.size] = site.patched
            touched.add(_section_for_offset(sections, off).index)
            edits.append({"group": group, "label": site.label, "va": f"0x{site.va:08x}", "file_offset": f"0x{off:x}",
                          "before": site.retail.hex() if site.size <= 16 else f"<{site.size} bytes>",
                          "after": site.patched.hex() if site.size <= 16 else f"<{site.size} bytes>"})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    for group in groups:
        _require(group_status(patched, group, **kwargs) == "applied", f"post-apply verification failed for {group}")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"groups": list(groups), "year": year, "edits": edits, "changed_bytes": changed,
                     "sections_repinned": sorted(touched), "regular_weeks":
                     PATCHED_REGULAR_WEEKS if "season_length" in groups else RETAIL_REGULAR_WEEKS,
                     "playoff_teams": 14 if "playoffs_14" in groups else 12,
                     "preseason_games": 3 if "preseason" in groups else 4,
                     "preseason_weeks": 4 if "preseason" in groups else 5,
                     "runtime_verified": False}


def site_table(**kwargs) -> list[dict[str, object]]:
    rows = []
    for group in GROUPS:
        for site in group_sites(group, **kwargs):
            rows.append({"group": group, "label": site.label, "va": f"0x{site.va:08x}", "size": site.size,
                         "retail": site.retail.hex() if site.size <= 16 else f"<{site.size} bytes>",
                         "patched": site.patched.hex() if site.size <= 16 else f"<{site.size} bytes>",
                         "note": site.note})
    return rows


__all__ = ["CALENDAR_2026", "DEFAULT_YEAR", "DOB_FORMATTER_VA", "GROUPS", "XBE_GROUPS", "GRID_ROWS", "GRID_SLOTS", "GRID_VA",
           "POSTSEASON_LABELS", "POSTSEASON_TABLE_VA", "RETAIL_POSTSEASON", "RETAIL_YEAR", "SB_VENUE_CASES",
           "SB_VENUE_TABLE_VA", "SEASON_WEEKS_VA", "STAGE_TABLE_VA", "SeasonLengthError", "Site", "WEEK_SITES",
           "apply", "calendar_sites", "group_sites", "group_status", "postseason_record", "postseason_table",
           "dob_formatter_bytes", "dob_pivot", "read_year", "rookie_birth_base", "site_table", "status", "year_sites"]


def simple_status(payload: bytes) -> str:
    """'retail' when every group is retail, 'applied' when every group is applied, else 'foreign'."""

    report = status(payload)
    states = {str(report[group]) for group in GROUPS}
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"

