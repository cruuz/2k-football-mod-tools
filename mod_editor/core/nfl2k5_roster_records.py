"""The whole NFL 2K5 roster record, decoded and encoded: the data layer behind ★ Rosters.

This is the studio's port of what Flying Finn's *NFL 2K5 GameSave Editor* (Glen Leskinen, 2005-2016)
and Bad_AL's *NFL2K5Tool* know about the 0x54 player record, plus the two things only Finn ever had --
the **contract block** and the **save signature** -- and the two things only the studio has: the
``+0x2C`` history-stream pointer and the ``+0x28`` rank/side depth semantics.  Field credit:
Flying Finn (Glen Leskinen) and Bad_AL; the map was re-verified byte for byte against the retail disc
``ROST`` resource before anything here was written (see ``FIELDS`` and the module tests).

Where the records live
----------------------
The Xbox roster save's ``SAVEGAME.DAT`` **is** the disc's ``ROST`` body: pack ``vc_53450030/0``,
outer entry 5, a 0x20-byte wrapper over a 0x90F60 body.  A franchise save carries the same block at a
constant ``+0x2E0`` prefix, and every pointer in it is field-relative (``target = field + i32 - 1``),
so the block is position independent -- ``RosterDocument`` finds it by its own ``ROST`` preamble and
works the same on a disc, a bare body and either kind of save.

The roster object is the block at ``+0x40``:

===========  ==========================================================================
obj+0x00/04  primary player count (2,479 retail) and the table (stride 0x54)
obj+0x08/0C  secondary player count (68 -- the class generator's templates) and its table
obj+0x18/1C  team count (52) and the team table (stride 0x1F4)
obj+0x20/24  college count (266) and the college table (stride 8: name pointer, index)
obj+0x38/3C  free-agent count (241) and a list of relative pointers to player records
obj+0x40/44  the season-stat pool ``nfl2k5_team_history`` rebuilds (used dwords, base)
obj+0x50/54  the generated draft-name pool ``nfl2k5_prospect_names`` rewrites
===========  ==========================================================================

A team record: 65 relative player pointers at ``+0x000``, nickname ``+0x104``, abbreviation
``+0x108``, label pair ``+0x110``, **player count byte** ``+0x11C``, city ``+0x138``, coach pointer
``+0x14C``, scheme word ``+0x150`` (0 = 4-3, 1 = 3-4, 2 = dual).  The pointer list is the depth
order: slot 0 is the top of the team's list, and moving a player up or down is a list rotation, which
is exactly how Finn's ↑↓ arrows behave.

The 0x54 record
---------------
``FIELDS`` covers **all 84 bytes with no gaps** -- every named field from Finn's grid plus one
explicitly named ``unknown_*`` field for every bit nobody has named yet (his ten hidden ``Unk``
columns and the record's zero padding).  That is what makes ``decode_record`` /``encode_record``
byte-exact on all 2,547 retail records: nothing is dropped, so nothing has to be guessed on the way
back out.  Editing one field rewrites only that field's bits.

The string pools
----------------
Player names are zero-terminated UTF-16LE strings packed **solid** into the body: 5,094 strings in
0x7B970..0x8B7D0, one per pointer, with **zero free bytes** (colleges sit immediately before at
0x79F5C, the generated-name pool immediately after).  So the pool cannot grow, and ``StringPool``
implements the only three honest moves, the same three ``nfl2k5_prospect_names`` uses:

1. **reuse** -- point at a string that already exists (this is Finn's shared-name trick, and it is
   how you beat the rename limit);
2. **rewrite in place** -- when the current string has no other user and the new one is no longer
   (a shorter name frees the tail as a reusable block);
3. **refuse** -- ``RosterPoolFull`` when neither works.  Nothing is ever written outside the span the
   pool was discovered from.

Position schemes
----------------
A position **code** is stable; what it MEANS is decided by the patches the disc carries, so this
module carries three views of the same 17 codes and every reader takes one (``POSITION_SCHEMES``):
``retail``, ``edge`` (``nfl2k5_edge_rename``: 16 prints EDGE, no code moves) and ``one_pool``
(``nfl2k5_position_pools`` + ``tools/nfl2k5_roster_reclassify``: 16 = EDGE, 15 = the interior,
11 = LB, and **10 is retired** -- it keeps its retail name on screen but no player carries it).
``detect_scheme`` reads a disc's own patch states through ``mod_build.inspect`` and falls back to
the records themselves (an empty OLB code in the primary pool is the reclassify signature); the
ratings, the jersey ranges and the depth chains stay keyed by the CODE, because that is what the
game indexes.

Save containers
---------------
``EXTRA`` = HMAC-SHA1(SigKey16, entire ``SAVEGAME.DAT``), 20 bytes.  ``SIG_KEY`` is the literal Finn
carries at file 0x247A88 of ``enf2k5editor.exe``; it is byte-identical to what the studio's own
``nfl2k5_save_writer.derive_sig_key`` computes from the retail XBE certificate (asserted by the
tests when the retail extraction is present), so the two lanes agree and neither needs the other.
``SaveContainer`` reads a zip, a directory or a loose ``SAVEGAME.DAT``, **verifies the stored EXTRA
on load** and refuses a save it cannot re-sign honestly; on write it rewrites ``SAVEGAME.DAT`` and
``EXTRA`` and copies every other member byte for byte.

Nothing here writes to the source.  The image writer edits a disc-image COPY through
``OuterImage`` the way ``nfl2k5_player_tags`` does, and the save writer always writes beside the
original.  Unwitnessed in game.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import hmac
import importlib
import io
import json
import shutil
import struct
import sys
import zipfile
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------------------------- layout
ROST_OUTER_INDEX = 5
RESOURCE_HEADER_SIZE = 0x20
BODY_SIZE = 0x90F60
RESOURCE_SIZE = RESOURCE_HEADER_SIZE + BODY_SIZE
OBJ_OFF = 0x40
PLAYER_SIZE = 0x54
TEAM_SIZE = 0x1F4
TEAM_SLOTS = 65
COLLEGE_SIZE = 8
POOLS = ("primary", "secondary")
POOL_FIELDS = {"primary": (OBJ_OFF + 0x00, OBJ_OFF + 0x04), "secondary": (OBJ_OFF + 0x08, OBJ_OFF + 0x0C)}
TEAM_COUNT_FIELD, TEAM_TABLE_FIELD = OBJ_OFF + 0x18, OBJ_OFF + 0x1C
COLLEGE_COUNT_FIELD, COLLEGE_TABLE_FIELD = OBJ_OFF + 0x20, OBJ_OFF + 0x24
FREE_AGENT_COUNT_FIELD, FREE_AGENT_LIST_FIELD = OBJ_OFF + 0x38, OBJ_OFF + 0x3C

TEAM_NICKNAME = 0x104
TEAM_ABBREVIATION = 0x108
TEAM_LABEL_PAIR = 0x110
TEAM_PLAYER_COUNT = 0x11C
TEAM_CITY = 0x138
TEAM_COACH = 0x14C
TEAM_SCHEME_WORD = 0x150

RETAIL_PRIMARY_COUNT = 2479
RETAIL_SECONDARY_COUNT = 68
RETAIL_TEAM_COUNT = 52
RETAIL_COLLEGE_COUNT = 266
RETAIL_FREE_AGENT_COUNT = 241
# sha256 of the retail ROST body (0x90F60 bytes, disc pack 0 outer entry 5 minus its 0x20 wrapper)
RETAIL_BODY_SHA256 = "b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae"

FRANCHISE_BLOCK_OFFSET = 0x2E0          # where a franchise save keeps the same block

# --------------------------------------------------------------------------------------------- signing
# The 16 bytes Finn's editor carries at file 0x247A88 ("722E...FF80" -- his Delphi string has eight
# more hex digits that Copy(s,1,32) throws away).  Title-static and public by construction: the
# studio's nfl2k5_save_writer derives the identical key from the retail XBE certificate.
SIG_KEY = bytes.fromhex("722E7565FB841B09E938DA756393FF80")
SAVEGAME_NAME = "SAVEGAME.DAT"
EXTRA_NAME = "EXTRA"
EXTRA_SIZE = 20
SAVE_TITLE_ID = "53450030"

EDITS_SCHEMA = "2k5_mod_studio_roster_edits/v1"


class RosterRecordError(ValueError):
    """The roster decoder/encoder cannot proceed."""


class RosterPoolFull(RosterRecordError):
    """A string pool has no room for a longer name and no existing copy to share."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RosterRecordError(message)


# --------------------------------------------------------------------------------------------- enums
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
# Finn calls slot 7 "RB"; the studio's own tools call it "HB".  Both names resolve on import.
POSITION_ALIASES = {"RB": 7, "HB": 7}
POSITION_GROUPS = {
    "QB": ("QB",), "RB": ("HB", "FB"), "WR": ("WR",), "TE": ("TE",), "OL": ("C", "G", "T"),
    "DL": ("DT", "DE"), "LB": ("OLB", "ILB"), "DB": ("CB", "FS", "SS"), "K/P": ("K", "P"),
}
ENUM_OLB, ENUM_ILB, ENUM_DT, ENUM_DE = 10, 11, 15, 16
# The four codes the one-pool pass rearranges; every other code means the same thing in all schemes.
FRONT_CODES = (ENUM_OLB, ENUM_ILB, ENUM_DT, ENUM_DE)
POSITION_LONG_NAMES = ("Quarterback", "Kicker", "Punter", "Wide Receiver", "Cornerback",
                       "Free Safety", "Strong Safety", "Halfback", "Fullback", "Tight End",
                       "Outside Linebacker", "Inside Linebacker", "Center", "Guard", "Tackle",
                       "Defensive Tackle", "Defensive End")

# --------------------------------------------------------------------------------- position schemes
# What a position CODE means depends on which patches the disc carries, so the editor cannot show
# the retail 17 names on every roster:
#
# * ``retail``   -- the shipped table above.
# * ``edge``     -- ``nfl2k5_edge_rename``: every place the game prints "Def End" / "Defensive End"
#                   reads EDGE / Edge Rusher.  **The codes do not move**: 16 is still the same pool.
# * ``one_pool`` -- ``nfl2k5_position_pools`` + ``tools/nfl2k5_roster_reclassify``: 16 = EDGE (4-3
#                   ends and 3-4 outside backers), 15 = the interior (4-3 tackles, the 3-4 nose and
#                   the 3-4 ends), 11 = LB (every off-ball backer) and **10 is retired** -- it keeps
#                   its retail name everywhere the game prints a roster position (see the "One LB
#                   row" note in ``nfl2k5_position_pools``) but no player on a reclassified roster
#                   carries it, and the editor must never write it back.
#
# The 3-4 nose is not a roster position: it is DT #1 on the 3-4 depth-chart tab ("NT", a slot label
# from ``nfl2k5_modern_positions``), so code 15 stays "DT" here and says so in its long name.
POSITION_SCHEMES = ("retail", "edge", "one_pool")
SCHEME_TITLES = {
    "retail": "Retail (17 positions)",
    "edge": "EDGE names (DE renamed, same 17 codes)",
    "one_pool": "One pool (EDGE / LB / interior, OLB retired)",
}
# The Build patch that puts a disc on each scheme -- the state ``detect_scheme_from_states`` reads.
SCHEME_PATCH_NAMES = {"retail": "", "edge": "edge_rename", "one_pool": "position_pools"}


def _relabel(table: Sequence[str], changes: Mapping[int, str]) -> tuple[str, ...]:
    out = list(table)
    for index, text in changes.items():
        out[index] = text
    return tuple(out)


SCHEME_POSITION_NAMES: dict[str, tuple[str, ...]] = {
    "retail": POSITIONS,
    "edge": _relabel(POSITIONS, {ENUM_DE: "EDGE"}),
    "one_pool": _relabel(POSITIONS, {ENUM_DE: "EDGE", ENUM_ILB: "LB"}),
}
SCHEME_POSITION_LONG_NAMES: dict[str, tuple[str, ...]] = {
    "retail": POSITION_LONG_NAMES,
    "edge": _relabel(POSITION_LONG_NAMES, {ENUM_DE: "Edge Rusher"}),
    "one_pool": _relabel(POSITION_LONG_NAMES, {
        ENUM_DE: "Edge Rusher",
        ENUM_ILB: "Linebacker",
        ENUM_DT: "Defensive Tackle (interior; the 3-4 nose is DT #1)",
        ENUM_OLB: "Outside Linebacker (retired -- no player carries it)"}),
}
# Codes the scheme keeps in the data but no longer fills, and where a stray one has to go.
SCHEME_RETIRED_CODES: dict[str, tuple[int, ...]] = {"retail": (), "edge": (), "one_pool": (ENUM_OLB,)}
SCHEME_RETIRED_REPLACEMENT: dict[str, dict[int, int]] = {
    "retail": {}, "edge": {}, "one_pool": {ENUM_OLB: ENUM_ILB},
}

_RETAIL_GROUP_CODES: dict[str, tuple[int, ...]] = {
    "QB": (0,), "RB": (7, 8), "WR": (3,), "TE": (9,), "OL": (12, 13, 14),
    "DL": (ENUM_DT, ENUM_DE), "LB": (ENUM_OLB, ENUM_ILB), "DB": (4, 5, 6), "K/P": (1, 2),
}
SCHEME_GROUP_CODES: dict[str, dict[str, tuple[int, ...]]] = {
    "retail": _RETAIL_GROUP_CODES,
    "edge": _RETAIL_GROUP_CODES,
    # under one pool the edge rushers are their own roster position, so they get their own chip and
    # "DL" means the interior; a stray retired OLB still shows under LB, because that is what the
    # game does with it (enum 10 behaves exactly like an LB, it is only unnamed on the roster).
    "one_pool": {"QB": (0,), "RB": (7, 8), "WR": (3,), "TE": (9,), "OL": (12, 13, 14),
                 "DL": (ENUM_DT,), "EDGE": (ENUM_DE,), "LB": (ENUM_OLB, ENUM_ILB),
                 "DB": (4, 5, 6), "K/P": (1, 2)},
}
SCHEME_CHIP_ORDER: dict[str, tuple[str, ...]] = {
    "retail": ("All", "QB", "RB", "WR", "TE", "OL", "DL", "LB", "DB", "K/P"),
    "edge": ("All", "QB", "RB", "WR", "TE", "OL", "DL", "LB", "DB", "K/P"),
    "one_pool": ("All", "QB", "RB", "WR", "TE", "OL", "DL", "EDGE", "LB", "DB", "K/P"),
}

# Every name any scheme uses, plus Finn's RB, resolved to the code it stores.  Import accepts all of
# them whatever the loaded scheme is, so a spreadsheet written against a retail disc still reads on
# a one-pool disc (and the other way round).
POSITION_CODE_BY_TEXT: dict[str, int] = {
    text.upper(): code
    for names in reversed(list(SCHEME_POSITION_NAMES.values()))
    for code, text in enumerate(names)
}
POSITION_CODE_BY_TEXT.update(POSITION_ALIASES)


def normalise_scheme(scheme: str | None) -> str:
    """The scheme name, defaulting to retail; an unknown name is a programming error."""

    name = str(scheme or "retail")
    _require(name in POSITION_SCHEMES, f"unknown position scheme {scheme!r}; use one of {POSITION_SCHEMES}")
    return name


def position_names(scheme: str = "retail") -> tuple[str, ...]:
    return SCHEME_POSITION_NAMES[normalise_scheme(scheme)]


def position_name(code: int, scheme: str = "retail") -> str:
    names = position_names(scheme)
    return names[code] if 0 <= code < len(names) else f"?{code}"


def position_long_name(code: int, scheme: str = "retail") -> str:
    names = SCHEME_POSITION_LONG_NAMES[normalise_scheme(scheme)]
    return names[code] if 0 <= code < len(names) else f"position {code}"


def position_code(text: str | int, scheme: str = "retail") -> int:
    """A position code from a name in any scheme, Finn's ``RB``, or a plain number."""

    normalise_scheme(scheme)
    if isinstance(text, int):
        return int(text)
    value = str(text).strip()
    code = POSITION_CODE_BY_TEXT.get(value.upper())
    if code is not None:
        return code
    _require(value.lstrip("-").isdigit(), f"{value!r} is not a position name or number")
    return int(value)


def retired_position_codes(scheme: str = "retail") -> tuple[int, ...]:
    return SCHEME_RETIRED_CODES[normalise_scheme(scheme)]


def is_retired_position(code: int, scheme: str = "retail") -> bool:
    return int(code) in retired_position_codes(scheme)


def live_position_codes(scheme: str = "retail") -> tuple[int, ...]:
    """The codes a roster on this scheme is allowed to store, in table order."""

    retired = retired_position_codes(scheme)
    return tuple(code for code in range(len(POSITIONS)) if code not in retired)


def replacement_position_code(code: int, scheme: str = "retail") -> int:
    """Where a retired code has to go on this scheme (10 -> 11 under one pool)."""

    return SCHEME_RETIRED_REPLACEMENT[normalise_scheme(scheme)].get(int(code), int(code))


def check_position_code(code: int, scheme: str = "retail") -> None:
    """Refuse a code the scheme retired, naming the code that replaces it."""

    if is_retired_position(code, scheme):
        instead = replacement_position_code(code, scheme)
        raise RosterRecordError(
            f"{position_name(code, 'retail')} (code {code}) is retired on a "
            f"{SCHEME_TITLES[normalise_scheme(scheme)]} roster; use "
            f"{position_name(instead, scheme)} (code {instead}) instead")


def position_groups(scheme: str = "retail") -> dict[str, tuple[int, ...]]:
    return SCHEME_GROUP_CODES[normalise_scheme(scheme)]


def chip_order(scheme: str = "retail") -> tuple[str, ...]:
    return SCHEME_CHIP_ORDER[normalise_scheme(scheme)]

HANDS = ("Left", "Right")
BODIES = ("Skinny", "Normal", "Large", "Extra Large")
HELMETS = ("Standard", "Revolution")
FACE_SHIELDS = ("None", "Clear", "Dark")
YES_NO = ("No", "Yes")
GLOVES = ("None", "Type 1", "Type 2", "Type 3", "Type 4", "Team 1", "Team 2", "Team 3", "Team 4", "Taped")
WRISTS = ("None", "Single White", "Double White", "Single Black", "Double Black", "Neoprene Small",
          "Neoprene Large", "Elastic Small", "Elastic Large", "Single Team", "Double Team",
          "Taped Small", "Taped Large", "Quarterback")
ELBOWS = ("None", "White", "Black", "White/Black Stripe", "Black/White Stripe", "Black/Team Stripe",
          "Team", "White/Team Stripe", "Elastic", "Neoprene", "High White", "High Black", "High Team")
SLEEVES = ("None", "White", "Black", "Team")
TURTLENECKS = SLEEVES
SHOES = ("Style 1", "Style 2", "Style 3", "Style 4", "Style 5", "Style 6", "Taped")
NECK_ROLLS = ("None", "Collar", "Roll", "Washboard", "Bulging")
CONTRACT_TYPES = ("Front Load", "Descending", "Balanced", "Middle", "Edge", "Up Down", "Ascending", "Back Load")
CONTRACT_BONUSES = ("N/A", "10%", "20%", "30%", "40%", "50%", "60%", "70%")
SKINS = tuple(f"Skin {n}" for n in range(1, 23))
FACES = tuple(f"Face {n}" for n in range(1, 16))
FACE_MASKS = tuple(f"Face Mask {n}" for n in range(1, 28))
# Finn's grouping labels for the 22 skin values, in the order his combo shows them.
SKIN_GROUPS = ("Lightest", "Light", "Light Medium", "Dark Medium", "Dark", "Darkest")

# Derived controls that write a rating byte for you: the segmented Power Run Style the game's own
# editor shows, and the throw-style parity bit that moves without disturbing the Scramble magnitude.
VIRTUAL_FIELDS = ("power_run_style_bucket", "throw_style")

ENUMS: dict[str, Sequence[str]] = {
    "position": POSITIONS, "hand": HANDS, "body": BODIES, "helmet": HELMETS,
    "face_shield": FACE_SHIELDS, "dreads": YES_NO, "eye_black": YES_NO, "mouthpiece": YES_NO,
    "left_glove": GLOVES, "right_glove": GLOVES, "left_wrist": WRISTS, "right_wrist": WRISTS,
    "left_elbow": ELBOWS, "right_elbow": ELBOWS, "sleeves": SLEEVES, "turtleneck": TURTLENECKS,
    "left_shoe": SHOES, "right_shoe": SHOES, "neck_roll": NECK_ROLLS,
    "contract_type": CONTRACT_TYPES, "contract_bonus": CONTRACT_BONUSES,
    "skin": SKINS, "face": FACES, "face_mask": FACE_MASKS,
}

# --------------------------------------------------------------------------------------------- ratings
# byte order (+0x36..+0x51).  There are **28** rating bytes, and three of them are style channels
# rather than ordinary scalars (2026-09-04 executable study, BETA59_RESEARCH_RATINGS_ROSTER_LIMITS
# _PLAYBOOKS §1; the game's own label stubs are at 0x000E5CC0, the per-position label/getter lists at
# .rdata 0x004F5258 / 0x004F55B8):
#
# * ``power_run_style`` (+0x4D) -- the game's editor shows it as Finesse / Balanced / Power, decoded
#   at 0x00344E19 / 0x00344E24 as ``< 33`` / ``< 66`` / else, and its cycler writes exactly 50/99/1.
#   Gameplay reads it as ``value x 0.01``, a blend weight, which is why retail quantised it.
# * ``scramble`` (+0x4F) -- a hidden rating with its own editor row ("Scramble", label 0xEAF280) that
#   the Player Card never prints.  **Its low bit is the only parity test on any rating byte anywhere
#   in .text** (``and ecx,ebx`` at 0x002D92B1): it picks between three families of directional
#   animation sets, and the magnitude is read separately (with Agility, threshold 1.5) to choose
#   between the two even families.  The animation is believed -- not proved -- to be the throw /
#   release motion.  Parity and magnitude are independent, so the studio edits them separately.
# * ``kicking_style`` (+0x4B) -- named KICKING STYLE by the game's own getter family (0x0E5780) and
#   held at exactly 99 for every K, 1 for every P and 49 for everyone else.  No consumer is proved
#   and there is no editor row for it, so the studio ships it EXPERIMENTAL.
#
# No other rating byte is bit-tested anywhere in the executable: there is no hidden parity scheme.
RATING_BYTE_ORDER = (
    "speed", "agility", "pass_arm_strength", "stamina", "kick_power", "durability", "strength",
    "jumping", "coverage", "run_route", "tackle", "break_tackle", "pass_accuracy",
    "pass_read_coverage", "catch", "run_blocking", "pass_blocking", "hold_onto_ball", "pass_rush",
    "run_coverage", "kick_accuracy", "kicking_style", "leadership", "power_run_style", "composure",
    "scramble", "consistency", "aggressiveness",
)
STYLE_RATINGS = ("power_run_style", "scramble", "kicking_style")

# Power Run Style: the thresholds and the three values the game's own cycler writes.
POWER_RUN_STYLES = ("Finesse", "Balanced", "Power")
POWER_RUN_STYLE_VALUES = (1, 50, 99)
POWER_RUN_STYLE_THRESHOLDS = (33, 66)          # < 33 Finesse, < 66 Balanced, else Power

# Scramble: the magnitude presets the game's own templates use, and the parity toggle.
SCRAMBLE_PRESETS = (("Pocket", 10), ("Balanced", 50), ("Scrambling", 90))
THROW_STYLES = ("A", "B")          # the parity bit: even = A, odd = B
SCRAMBLE_AGILITY_THRESHOLD = 1.5               # 0.01*Scramble + 0.01*Agility, [0x004E6D0C]

# Kicking Style: retail's three values.  EXPERIMENTAL -- no consumer proved.
KICKING_STYLE_PRESETS = (("Punter", 1), ("Default", 49), ("Kicker", 99))

# Not read yet, kept here so it is not lost: the game's own create-a-player templates ("Pocket QB",
# "Scrambling QB", "Speed WR", "Power HB", ...) live at .rdata 0x005561B8 as 36 records of 0x74 =
# a label pointer plus 28 int32 slots, where -1 means "leave this rating alone".  Slot 7 is Power Run
# Style and slot 21 is Scramble (both proved); the display order of the other 26 slots is unmapped.
# An "apply template" action wants that map finished, or it should write only those two slots.
CREATE_PLAYER_TEMPLATES_RDATA = 0x005561B8
CREATE_PLAYER_TEMPLATE_COUNT = 36
CREATE_PLAYER_TEMPLATE_STRIDE = 0x74
CREATE_PLAYER_TEMPLATE_SLOTS = {7: "power_run_style", 21: "scramble"}

ENUMS["power_run_style_bucket"] = POWER_RUN_STYLES
ENUMS["throw_style"] = THROW_STYLES
RATING_OFFSETS = {name: 0x36 + index for index, name in enumerate(RATING_BYTE_ORDER)}
RATING_LABELS = {
    "speed": "Speed", "agility": "Agility", "strength": "Strength", "jumping": "Jumping",
    "coverage": "Coverage", "pass_rush": "Pass Rush", "run_coverage": "Run Coverage",
    "pass_blocking": "Pass Blocking", "run_blocking": "Run Blocking", "catch": "Catch",
    "run_route": "Run Route", "break_tackle": "Break Tackle", "hold_onto_ball": "Hold On To Ball",
    "power_run_style": "Power Run Style (raw)", "pass_accuracy": "Pass Accuracy",
    "pass_arm_strength": "Pass Arm Strength", "pass_read_coverage": "Pass Read Coverage",
    "tackle": "Tackle", "kick_power": "Kick Power", "kick_accuracy": "Kick Accuracy",
    "stamina": "Stamina", "durability": "Durability", "leadership": "Leadership",
    "scramble": "Scramble (animation style)", "composure": "Composure", "consistency": "Consistency",
    "aggressiveness": "Aggressiveness", "kicking_style": "Kicking Style (+0x4B)",
}
# Finn's ENF2k5Attributes.txt order -- what his Attributes tab shows, top to bottom.
RATING_UI_ORDER = (
    "speed", "agility", "strength", "jumping", "coverage", "pass_rush", "run_coverage",
    "pass_blocking", "run_blocking", "catch", "run_route", "break_tackle", "hold_onto_ball",
    "power_run_style", "pass_accuracy", "pass_arm_strength", "pass_read_coverage", "tackle",
    "kick_power", "kick_accuracy", "stamina", "durability", "leadership", "scramble", "composure",
    "consistency", "aggressiveness",
)
RATING_MAX = 99
RATING_MAX_LARGE = 127          # Finn's Tools > Options > "Large Attribute Values"

# The studio's own headline "OVR" per position -- an estimate, NOT the game's formula (the game's
# weights live in the executable and have not been extracted).  Documented here so the number in the
# grid is explainable and moves when the ratings that matter for the position move.
_SKILL = {
    "QB": {"pass_accuracy": 28, "pass_read_coverage": 22, "pass_arm_strength": 18, "composure": 10,
           "scramble": 6, "speed": 6, "agility": 5, "consistency": 5},
    "HB": {"speed": 20, "agility": 18, "break_tackle": 18, "strength": 10, "catch": 8,
           "hold_onto_ball": 8, "run_blocking": 6, "jumping": 5, "stamina": 5},
    "FB": {"run_blocking": 24, "strength": 18, "break_tackle": 16, "speed": 12, "catch": 10,
           "agility": 10, "hold_onto_ball": 10},
    "WR": {"catch": 28, "run_route": 22, "speed": 20, "agility": 12, "jumping": 10, "hold_onto_ball": 8},
    "TE": {"catch": 24, "run_blocking": 18, "run_route": 16, "speed": 12, "pass_blocking": 10,
           "strength": 10, "agility": 10},
    "C": {"run_blocking": 38, "pass_blocking": 38, "strength": 16, "agility": 8},
    "DT": {"pass_rush": 28, "tackle": 22, "strength": 22, "run_coverage": 16, "agility": 6, "speed": 6},
    "DE": {"pass_rush": 32, "tackle": 20, "strength": 18, "run_coverage": 14, "speed": 10, "agility": 6},
    "ILB": {"tackle": 26, "run_coverage": 20, "coverage": 16, "pass_rush": 14, "speed": 12, "strength": 12},
    "CB": {"coverage": 30, "speed": 22, "agility": 16, "tackle": 14, "jumping": 10, "catch": 8},
    "SS": {"coverage": 22, "tackle": 24, "speed": 20, "agility": 14, "jumping": 10, "strength": 10},
    "K": {"kick_power": 50, "kick_accuracy": 50},
}
OVERALL_WEIGHTS: dict[str, dict[str, int]] = {
    **_SKILL,
    "G": _SKILL["C"], "T": _SKILL["C"], "OLB": _SKILL["ILB"], "FS": _SKILL["CB"], "P": _SKILL["K"],
}
# The rating semantics belong to the CODE, not to the label the disc prints: the game's own
# per-position rating labels and getters are indexed by the position enum (.rdata 0x004F5258 /
# 0x004F55B8), so a one-pool LB (code 11) reads the ILB card set and a one-pool EDGE (code 16) reads
# the DE card set -- only the wording on screen changes.  Renaming a position must never move a
# player onto another position's weights, which is exactly what happened while ``OVERALL_WEIGHTS``
# was keyed by the displayed name: "LB" and "EDGE" are not retail names, so they fell through to the
# flat average.
RATING_PROFILE_BY_CODE: dict[int, str] = {code: name for code, name in enumerate(POSITIONS)}
OVERALL_WEIGHTS_BY_CODE: dict[int, dict[str, int]] = {
    code: OVERALL_WEIGHTS[name] for code, name in RATING_PROFILE_BY_CODE.items() if name in OVERALL_WEIGHTS
}


def rating_profile(code: int) -> str:
    """Which retail position's rating card set the game uses for this code."""

    return RATING_PROFILE_BY_CODE.get(int(code), f"?{code}")


def key_ratings(code: int, limit: int = 4) -> tuple[str, ...]:
    """The ratings that carry this code's profile, heaviest first (the studio's own weighting)."""

    weights = OVERALL_WEIGHTS_BY_CODE.get(int(code))
    if not weights:
        return ()
    ordered = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    return tuple(name for name, _weight in ordered[:limit])

# The attribute cards, grouped the way the ★ Rosters right-hand panel shows them.
ATTRIBUTE_CARDS: dict[str, tuple[str, ...]] = {
    # every rating appears on exactly one card: "scramble" lives on Style, with its parity toggle
    "Athletic": ("speed", "agility", "strength", "jumping", "stamina", "durability", "break_tackle"),
    "Skills": ("catch", "run_route", "hold_onto_ball", "pass_accuracy", "pass_arm_strength",
               "pass_read_coverage", "tackle", "coverage", "pass_rush", "run_coverage",
               "run_blocking", "pass_blocking", "kick_power", "kick_accuracy"),
    "Mental": ("leadership", "composure", "consistency", "aggressiveness"),
    # the three style channels, first-class: two segmented controls over the bytes plus the raw values
    "Style": ("power_run_style_bucket", "power_run_style", "throw_style", "scramble", "kicking_style"),
    "Appearance": ("skin", "face", "body", "dreads", "eye_black", "helmet", "face_mask", "face_shield",
                   "mouthpiece", "turtleneck", "sleeves", "neck_roll", "left_glove", "right_glove",
                   "left_wrist", "right_wrist", "left_elbow", "right_elbow", "left_shoe", "right_shoe",
                   "hand", "photo_id"),
    "Identity": ("position", "jersey", "years_pro", "height", "weight", "birth_month",
                 "birth_day", "birth_year", "pbp_id", "player_type"),
    "Contract": ("contract_value", "contract_type", "contract_bonus", "contract_length", "contract_remaining"),
}
NUMERIC_LIMITS: dict[str, tuple[int, int]] = {
    "jersey": (0, 99), "years_pro": (0, 31), "height": (60, 84), "weight": (150, 405),
    "birth_month": (1, 12), "birth_day": (1, 31), "birth_year": (1900, 2027),
    "pbp_id": (0, 65535), "photo_id": (0, 65535), "player_type": (0, 255),
    "contract_value": (0, 65535), "contract_length": (0, 15), "contract_remaining": (0, 15),
    "depth_rank": (0, 7), "depth_side": (0, 7),
}


# --------------------------------------------------------------------------------------------- fields
@dataclass(frozen=True)
class Field:
    """One stored field: ``width`` bits at ``shift`` inside the ``size``-byte LE word at ``offset``."""

    name: str
    offset: int
    size: int
    shift: int
    width: int
    label: str = ""
    note: str = ""

    @property
    def mask(self) -> int:
        return ((1 << self.width) - 1) << self.shift

    @property
    def maximum(self) -> int:
        return (1 << self.width) - 1


def _f(name: str, offset: int, size: int, shift: int, width: int, label: str = "", note: str = "") -> Field:
    return Field(name, offset, size, shift, width, label or name.replace("_", " ").title(), note)


FIELDS: tuple[Field, ...] = (
    _f("college_pointer", 0x00, 4, 0, 32, "College pointer", "relative pointer to the 8-byte college record"),
    _f("pbp_id", 0x04, 2, 0, 16, "Play-By-Play Name", "index into the recorded name bank"),
    _f("photo_id", 0x06, 2, 0, 16, "Photo", "portrait id (f%04d)"),
    _f("player_type", 0x08, 1, 0, 8, "Player Type", "4 = NFL player, 0 = draft class; bit 2 = announce last name only"),
    _f("unknown_09", 0x09, 1, 0, 8, "Unknown +0x09"),
    _f("contract_value", 0x0A, 2, 0, 16, "Contract Value", "in $10,000 units: 377 = $3.77m"),
    _f("left_shoe", 0x0C, 1, 0, 3, "Left Shoe"),
    _f("right_shoe", 0x0C, 1, 3, 3, "Right Shoe"),
    _f("helmet", 0x0C, 1, 6, 1, "Helmet"),
    _f("headless", 0x0C, 1, 7, 1, "Headless Bit", "Finn's 12Unk1; a set bit renders the model without a head"),
    _f("unknown_0d", 0x0D, 1, 0, 8, "Unknown +0x0D"),
    _f("unknown_0e", 0x0E, 1, 0, 8, "Unknown +0x0E"),
    _f("unknown_0f", 0x0F, 1, 0, 8, "Unknown +0x0F"),
    _f("first_name_pointer", 0x10, 4, 0, 32, "First name pointer"),
    _f("last_name_pointer", 0x14, 4, 0, 32, "Last name pointer"),
    _f("dreads", 0x18, 1, 0, 1, "Dreads"),
    _f("hand", 0x18, 1, 1, 1, "Best Hand", "0 = Left, 1 = Right; the row the game's own editor toggles"),
    _f("eye_black", 0x18, 1, 2, 1, "Eye Black"),
    _f("body", 0x18, 1, 3, 2, "Body Type"),
    _f("turtleneck", 0x18, 1, 5, 2, "Turtleneck"),
    _f("skin_low", 0x18, 1, 7, 1, "Skin bit 0"),
    _f("skin_high", 0x19, 1, 0, 4, "Skin bits 1-4"),
    _f("birth_month", 0x19, 1, 4, 4, "Birth month"),
    _f("birth_day", 0x1A, 1, 0, 5, "Birth day"),
    _f("birth_year_low", 0x1A, 1, 5, 3, "Birth year bits 0-2"),
    _f("birth_year_high", 0x1B, 1, 0, 4, "Birth year bits 3-6"),
    _f("unknown_1b_high", 0x1B, 1, 4, 4, "Unknown +0x1B bits 4-7"),
    _f("sleeves", 0x1C, 1, 0, 2, "Sleeves"),
    _f("neck_roll", 0x1C, 1, 2, 3, "Neck Roll"),
    _f("mouthpiece", 0x1C, 1, 5, 1, "Mouth Piece"),
    _f("left_glove_low", 0x1C, 1, 6, 2, "Left glove bits 0-1"),
    _f("left_glove_high", 0x1D, 1, 0, 2, "Left glove bits 2-3"),
    _f("right_glove", 0x1D, 1, 2, 4, "Right Glove"),
    _f("left_wrist_low", 0x1D, 1, 6, 2, "Left wrist bits 0-1"),
    _f("left_wrist_high", 0x1E, 1, 0, 2, "Left wrist bits 2-3"),
    _f("right_wrist", 0x1E, 1, 2, 4, "Right Wrist"),
    _f("left_elbow_low", 0x1E, 1, 6, 2, "Left elbow bits 0-1"),
    _f("left_elbow_high", 0x1F, 1, 0, 2, "Left elbow bits 2-3"),
    _f("right_elbow", 0x1F, 1, 2, 4, "Right Elbow"),
    _f("unknown_1f_high", 0x1F, 1, 6, 2, "Unknown +0x1F bits 6-7", "Finn's 28Unk1"),
    _f("unknown_20_bit0", 0x20, 4, 0, 1, "Unknown +0x20 bit 0", "Finn's 32Unk1"),
    _f("unknown_20_bits12", 0x20, 4, 1, 2, "Unknown +0x20 bits 1-2"),
    _f("jersey", 0x20, 4, 3, 7, "Jersey Number"),
    _f("face_mask", 0x20, 4, 10, 5, "Face Mask"),
    _f("face_shield", 0x20, 4, 15, 2, "Face Shield"),
    _f("face", 0x20, 4, 17, 4, "Face"),
    _f("unknown_20_bit21", 0x20, 4, 21, 1, "Unknown +0x22 bit 5", "Finn's 32Unk2"),
    _f("unknown_20_high", 0x20, 4, 22, 10, "Unknown +0x22/+0x23 high", "an 8-bit field at bits 22-29 plus two flag bits"),
    _f("contract_remaining", 0x24, 1, 0, 4, "Years Remaining"),
    _f("unknown_24_high", 0x24, 1, 4, 4, "Unknown +0x24 bits 4-7", "Finn's 36Unk"),
    _f("years_pro", 0x25, 1, 0, 5, "Years Pro"),
    _f("unknown_25_high", 0x25, 1, 5, 3, "Unknown +0x25 bits 5-7"),
    _f("contract_type", 0x26, 1, 0, 4, "Contract Type"),
    _f("contract_bonus", 0x26, 1, 4, 4, "Signing Bonus"),
    _f("contract_length", 0x27, 1, 0, 4, "Contract Length"),
    _f("unknown_27_high", 0x27, 1, 4, 4, "Unknown +0x27 bits 4-7", "Finn's 39Unk"),
    _f("injured_reserve", 0x28, 2, 0, 8, "Injured Reserve", "Finn writes 0xEE here when a player goes on IR"),
    _f("unknown_29_low", 0x28, 2, 8, 2, "Unknown +0x29 bits 0-1", "Finn's 41Unk"),
    _f("depth_rank", 0x28, 2, 10, 3, "Depth Rank"),
    _f("depth_side", 0x28, 2, 13, 3, "Depth Side"),
    _f("weight_raw", 0x2A, 1, 0, 8, "Weight", "pounds - 150"),
    _f("height", 0x2B, 1, 0, 8, "Height", "inches"),
    _f("history_pointer", 0x2C, 4, 0, 32, "History Pointer", "the per-season stat stream nfl2k5_team_history rebuilds"),
    _f("unknown_30", 0x30, 4, 0, 32, "Unknown +0x30..+0x33"),
    _f("pool_kind", 0x34, 1, 0, 8, "Pool Kind"),
    _f("position", 0x35, 1, 0, 8, "Position"),
    *(_f(name, 0x36 + index, 1, 0, 8, RATING_LABELS[name]) for index, name in enumerate(RATING_BYTE_ORDER)),
    _f("unknown_52", 0x52, 1, 0, 8, "Unknown +0x52"),
    _f("star_tag", 0x53, 1, 0, 1, "Star Tag", "the studio's own bit; nfl2k5_player_tags writes it"),
    _f("unknown_53_high", 0x53, 1, 1, 7, "Unknown +0x53 bits 1-7"),
)
FIELD_BY_NAME = {f.name: f for f in FIELDS}
COMPOSITE_FIELDS = ("skin", "birth_year", "left_glove", "left_wrist", "left_elbow", "weight")
POINTER_FIELDS = ("college_pointer", "first_name_pointer", "last_name_pointer", "history_pointer")


def field_coverage() -> list[int]:
    """Bits claimed per record byte -- 8 for all 84 bytes, which is what makes the codec exact."""

    bits = [0] * PLAYER_SIZE
    for f in FIELDS:
        for bit in range(f.shift, f.shift + f.width):
            bits[f.offset + bit // 8] += 1
    return bits


def decode_record(raw: bytes) -> dict[str, int]:
    """Every field of one 0x54 record, named fields and unknown bits alike."""

    _require(len(raw) == PLAYER_SIZE, f"a player record is {PLAYER_SIZE} bytes, got {len(raw)}")
    out: dict[str, int] = {}
    for f in FIELDS:
        word = int.from_bytes(raw[f.offset: f.offset + f.size], "little")
        out[f.name] = (word >> f.shift) & ((1 << f.width) - 1)
    return out


def encode_record(values: Mapping[str, int]) -> bytes:
    """The 0x54 bytes for a full field mapping (the inverse of :func:`decode_record`)."""

    words: dict[tuple[int, int], int] = {}
    for f in FIELDS:
        _require(f.name in values, f"encode_record is missing the field {f.name!r}")
        value = int(values[f.name])
        _require(0 <= value <= f.maximum, f"{f.name} = {value} does not fit in {f.width} bits")
        key = (f.offset, f.size)
        words[key] = words.get(key, 0) | (value << f.shift)
    raw = bytearray(PLAYER_SIZE)
    for (offset, size), word in words.items():
        raw[offset: offset + size] = word.to_bytes(size, "little")
    return bytes(raw)


def _signed(value: int) -> int:
    return value - (1 << 32) if value >= (1 << 31) else value


class PlayerRecord:
    """A decoded 0x54 record with typed access to every field and to the composites."""

    __slots__ = ("values", "scheme")

    def __init__(self, values: Mapping[str, int], scheme: str = "retail") -> None:
        self.values: dict[str, int] = dict(values)
        # which position table this record's code should be READ through; the stored bytes never
        # change with it (see POSITION_SCHEMES)
        self.scheme: str = normalise_scheme(scheme)

    @classmethod
    def decode(cls, raw: bytes, scheme: str = "retail") -> "PlayerRecord":
        return cls(decode_record(raw), scheme)

    def encode(self) -> bytes:
        return encode_record(self.values)

    def copy(self) -> "PlayerRecord":
        return PlayerRecord(self.values, self.scheme)

    # ------------------------------------------------------------------ raw field access
    def get(self, name: str) -> int:
        if name in COMPOSITE_FIELDS or name in VIRTUAL_FIELDS:
            return int(getattr(self, name))
        _require(name in FIELD_BY_NAME, f"no roster field named {name!r}")
        return self.values[name]

    def set(self, name: str, value: int) -> None:
        if name in COMPOSITE_FIELDS or name in VIRTUAL_FIELDS:
            setattr(self, name, int(value))
            return
        f = FIELD_BY_NAME.get(name)
        _require(f is not None, f"no roster field named {name!r}")
        assert f is not None
        _require(0 <= int(value) <= f.maximum, f"{f.label} accepts 0..{f.maximum}, got {value}")
        self.values[name] = int(value)

    # ------------------------------------------------------------------ composites
    @property
    def skin(self) -> int:
        return self.values["skin_low"] | (self.values["skin_high"] << 1)

    @skin.setter
    def skin(self, value: int) -> None:
        _require(0 <= value <= 31, f"skin accepts 0..31, got {value}")
        self.values["skin_low"] = value & 1
        self.values["skin_high"] = (value >> 1) & 0xF

    @property
    def birth_year(self) -> int:
        raw = self.values["birth_year_low"] | (self.values["birth_year_high"] << 3)
        return 1900 + raw if raw > 54 else 2000 + raw

    @birth_year.setter
    def birth_year(self, value: int) -> None:
        raw = value - 1900 if value >= 1955 else value - 2000
        _require(0 <= raw <= 127, f"birth year {value} is outside 1955..2054")
        self.values["birth_year_low"] = raw & 0x7
        self.values["birth_year_high"] = (raw >> 3) & 0xF

    @property
    def birth_date(self) -> dt.date | None:
        month, day = self.values["birth_month"], self.values["birth_day"]
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        try:
            return dt.date(self.birth_year, month, day)
        except ValueError:
            return None

    @birth_date.setter
    def birth_date(self, value: dt.date) -> None:
        self.values["birth_month"] = value.month
        self.values["birth_day"] = value.day
        self.birth_year = value.year

    @property
    def weight(self) -> int:
        return self.values["weight_raw"] + 150

    @weight.setter
    def weight(self, value: int) -> None:
        _require(150 <= value <= 405, f"weight accepts 150..405 lb, got {value}")
        self.values["weight_raw"] = value - 150

    def _split(self, name: str) -> int:
        return self.values[f"{name}_low"] | (self.values[f"{name}_high"] << 2)

    def _set_split(self, name: str, value: int) -> None:
        _require(0 <= value <= 15, f"{name} accepts 0..15, got {value}")
        self.values[f"{name}_low"] = value & 0x3
        self.values[f"{name}_high"] = (value >> 2) & 0x3

    @property
    def left_glove(self) -> int:
        return self._split("left_glove")

    @left_glove.setter
    def left_glove(self, value: int) -> None:
        self._set_split("left_glove", value)

    @property
    def left_wrist(self) -> int:
        return self._split("left_wrist")

    @left_wrist.setter
    def left_wrist(self, value: int) -> None:
        self._set_split("left_wrist", value)

    @property
    def left_elbow(self) -> int:
        return self._split("left_elbow")

    @left_elbow.setter
    def left_elbow(self, value: int) -> None:
        self._set_split("left_elbow", value)

    # ------------------------------------------------------------------ style channels
    @property
    def power_run_style_bucket(self) -> int:
        """0 Finesse / 1 Balanced / 2 Power, decoded the way the game's own editor decodes it."""

        value = self.values["power_run_style"]
        low, high = POWER_RUN_STYLE_THRESHOLDS
        return 0 if value < low else (1 if value < high else 2)

    @power_run_style_bucket.setter
    def power_run_style_bucket(self, index: int) -> None:
        _require(0 <= index < len(POWER_RUN_STYLE_VALUES),
                 f"power run style accepts 0..{len(POWER_RUN_STYLE_VALUES) - 1}, got {index}")
        self.values["power_run_style"] = POWER_RUN_STYLE_VALUES[index]

    @property
    def throw_style(self) -> int:
        """The parity bit of Scramble (+0x4F): the only bit test on any rating byte in the game."""

        return self.values["scramble"] & 1

    @throw_style.setter
    def throw_style(self, style: int) -> None:
        _require(style in (0, 1), f"throw style is 0 or 1, got {style}")
        self.values["scramble"] = (self.values["scramble"] & ~1) | style

    def set_scramble_magnitude(self, value: int) -> None:
        """Move the Scramble rating without disturbing the throw-style bit."""

        _require(0 <= value <= 255, f"scramble accepts 0..255, got {value}")
        self.values["scramble"] = (value & ~1) | (self.values["scramble"] & 1)

    @property
    def mobile_quarterback(self) -> bool:
        """The engine's own second test: 0.01*Scramble + 0.01*Agility > 1.5 picks the high family."""

        return (self.values["scramble"] + self.values["agility"]) / 100.0 > SCRAMBLE_AGILITY_THRESHOLD

    # ------------------------------------------------------------------ conveniences
    @property
    def position_code(self) -> int:
        return self.values["position"]

    @property
    def position_name(self) -> str:
        """The abbreviation this record's scheme prints for its code (retail unless told otherwise)."""

        return position_name(self.values["position"], self.scheme)

    @property
    def position_long_name(self) -> str:
        return position_long_name(self.values["position"], self.scheme)

    @property
    def rating_profile(self) -> str:
        """The retail position whose rating card set the game uses for this record's code."""

        return rating_profile(self.values["position"])

    @property
    def pbp_last_name_only(self) -> bool:
        return bool(self.values["player_type"] & 0x04)

    @property
    def on_injured_reserve(self) -> bool:
        return self.values["injured_reserve"] == 0xEE

    @property
    def contract_millions(self) -> float:
        return self.values["contract_value"] / 100.0

    @property
    def contract_penalty_millions(self) -> float:
        """Finn shows this greyed out: value x bonus%.  Derived, never stored."""

        return self.contract_millions * self.values["contract_bonus"] * 0.10

    @property
    def height_text(self) -> str:
        inches = self.values["height"]
        return f"{inches // 12}'{inches % 12}\""

    def ratings(self) -> dict[str, int]:
        return {name: self.values[name] for name in RATING_BYTE_ORDER}

    def overall(self) -> int:
        """The grid's headline number: this module's own position-weighted rating, 0-99.

        **Not the game's overall.**  The executable computes its own from weights nobody has
        extracted yet; this is a documented, stable estimate (``OVERALL_WEIGHTS``) that sorts a
        depth chart sensibly and moves when you edit the ratings that matter for the position."""

        weights = OVERALL_WEIGHTS_BY_CODE.get(self.values["position"])
        if not weights:
            named = [self.values[name] for name in RATING_BYTE_ORDER if name not in STYLE_RATINGS]
            return round(sum(named) / len(named))
        total = sum(self.values[name] * weight for name, weight in weights.items())
        return max(0, min(99, round(total / sum(weights.values()))))


# --------------------------------------------------------------------------------------------- strings
def encoded_size(text: str) -> int:
    """Bytes a zero-terminated UTF-16LE string needs."""

    return len(text.encode("utf-16-le")) + 2


@dataclass
class Allocation:
    offset: int
    capacity: int               # bytes, including the terminator
    text: str


class StringPool:
    """The player-name (or college-name) strings, as a set of fixed byte allocations.

    The pool is discovered from the pointers that reference it, so it never claims a byte the
    retail data did not already spend on a string of this kind.  Reuse first, rewrite in place
    second, refuse third -- there is nowhere to grow into.
    """

    def __init__(self, body: bytearray, offsets: Iterable[int], label: str) -> None:
        self.body = body
        self.label = label
        self.blocks: dict[int, Allocation] = {}
        self.free: dict[int, int] = {}          # offset -> capacity
        used = sorted(set(offsets))
        _require(bool(used), f"the {label} pool has no strings")
        for offset in used:
            text, size = read_utf16z(body, offset)
            self.blocks[offset] = Allocation(offset, size, text)
        self.start = used[0]
        self.end = max(a.offset + a.capacity for a in self.blocks.values())
        # any byte inside the span that no string claims is free space we may reuse
        cursor = self.start
        for offset in used:
            block = self.blocks[offset]
            if offset > cursor:
                self.free[cursor] = offset - cursor
            cursor = max(cursor, offset + block.capacity)
        if cursor < self.end:
            self.free[cursor] = self.end - cursor
        self._by_text: dict[str, list[int]] = {}
        for block in self.blocks.values():
            self._by_text.setdefault(block.text, []).append(block.offset)

    # ------------------------------------------------------------------ reads
    def text_at(self, offset: int) -> str:
        block = self.blocks.get(offset)
        return block.text if block is not None else read_utf16z(self.body, offset)[0]

    def offsets_for(self, text: str) -> list[int]:
        return list(self._by_text.get(text, ()))

    def release_if_unused(self, offset: int) -> bool:
        """Give a block back once its last pointer has moved away (the reuse path leaves one)."""

        if offset not in self.blocks:
            return False
        self._release(offset)
        return True

    @property
    def capacity_bytes(self) -> int:
        return self.end - self.start

    @property
    def free_bytes(self) -> int:
        return sum(self.free.values())

    def summary(self) -> dict[str, Any]:
        return {"label": self.label, "start": f"0x{self.start:x}", "end": f"0x{self.end:x}",
                "strings": len(self.blocks), "unique": len(self._by_text),
                "capacity_bytes": self.capacity_bytes, "free_bytes": self.free_bytes,
                "free_blocks": len(self.free)}

    # ------------------------------------------------------------------ writes
    def _write(self, offset: int, capacity: int, text: str) -> Allocation:
        raw = text.encode("utf-16-le") + b"\0\0"
        _require(len(raw) <= capacity, f"{self.label}: {text!r} does not fit in {capacity} bytes")
        self.body[offset: offset + len(raw)] = raw
        block = Allocation(offset, capacity, text)
        self.blocks[offset] = block
        self._by_text.setdefault(text, []).append(offset)
        return block

    @staticmethod
    def _merge(free: dict[int, int], offset: int, capacity: int) -> None:
        """Give ``capacity`` bytes at ``offset`` back, joined to any free neighbour."""

        end = offset + capacity
        follower = free.pop(end, None)
        if follower is not None:
            end += follower
        for start, size in list(free.items()):
            if start + size == offset:
                del free[start]
                offset = start
                break
        free[offset] = end - offset

    def _release(self, offset: int) -> None:
        block = self.blocks.pop(offset, None)
        if block is None:
            return
        holders = self._by_text.get(block.text)
        if holders and offset in holders:
            holders.remove(offset)
            if not holders:
                self._by_text.pop(block.text, None)
        self._merge(self.free, offset, block.capacity)

    def _take_free(self, need: int) -> tuple[int, int]:
        """Smallest free block that fits (best fit keeps the big holes for the long names)."""

        size, offset = min((size, offset) for offset, size in self.free.items() if size >= need)
        del self.free[offset]
        spare = size - need
        if spare >= 2:                          # the remainder can still hold an empty string
            self.free[offset + need] = spare
            return offset, need
        return offset, size                     # a remainder under one terminator stays with the block

    def place(self, text: str, *, current: int | None, sole_user: bool) -> int:
        """Offset the pointer should carry for ``text``; writes bytes only when it has to.

        ``current`` is the offset the pointer holds now and ``sole_user`` says whether it is the
        only pointer at that offset (only then may the bytes there be rewritten)."""

        existing = self._by_text.get(text)
        if existing:
            return existing[0]                                  # reuse: Finn's shared name
        need = encoded_size(text)
        releasable = current if (sole_user and current is not None and current in self.blocks) else None
        trial = dict(self.free)
        if releasable is not None:
            self._merge(trial, releasable, self.blocks[releasable].capacity)
        if not any(size >= need for size in trial.values()):
            raise RosterPoolFull(
                f"the {self.label} pool is full: {text!r} needs {need} bytes and the largest free "
                f"block is {max(trial.values(), default=0)}. Point this player at a name that "
                f"already exists, or shorten another player's name first.")
        if releasable is not None:
            self._release(releasable)
        offset, capacity = self._take_free(need)
        return self._write(offset, capacity, text).offset


def read_utf16z(body: bytes | bytearray, offset: int) -> tuple[str, int]:
    """The zero-terminated UTF-16LE string at ``offset`` and the bytes it occupies."""

    _require(0 <= offset < len(body), f"string offset 0x{offset:x} is outside the body")
    end = offset
    while end + 1 < len(body) and body[end: end + 2] != b"\0\0":
        end += 2
    return bytes(body[offset:end]).decode("utf-16-le", "replace"), end + 2 - offset


# --------------------------------------------------------------------------------------------- document
@dataclass
class TeamRecord:
    index: int
    offset: int
    nickname: str
    abbreviation: str
    city: str
    player_count: int
    slots: list[int] = dc_field(default_factory=list)      # body offsets of the players, depth order
    original_slots: tuple[int, ...] = ()                   # what the list held when we parsed it
    coach_offset: int | None = None
    scheme: int = 0

    @property
    def reordered(self) -> bool:
        return tuple(self.slots) != self.original_slots

    @property
    def display(self) -> str:
        return f"{self.city} {self.nickname}".strip() or self.abbreviation or f"Team {self.index}"


@dataclass
class Player:
    pool: str
    index: int
    offset: int
    record: PlayerRecord
    first: str = ""
    last: str = ""
    college: str = ""
    college_index: int | None = None
    teams: list[int] = dc_field(default_factory=list)
    group: str = "pool"                                     # team / free_agent / draft_class / pool

    @property
    def key(self) -> str:
        birth = self.record.birth_date
        return f"{self.last},{self.first},{birth.isoformat() if birth else ''}"

    @property
    def display(self) -> str:
        return f"{self.first} {self.last}".strip() or f"#{self.index}"


class RosterDocument:
    """A whole roster block: players, teams, colleges, free agents and the two string pools.

    Load it from a disc image / loose packs, a bare ROST body or an Xbox save container; edit the
    records and names in memory; write it back to a **copy** of whichever it came from.
    """

    def __init__(self, body: bytes | bytearray, *, base: int = 0, source: str = "body",
                 container: "SaveContainer | None" = None, resource_header: bytes = b"",
                 scheme: str = "retail") -> None:
        self.body = bytearray(body)
        self.base = base
        self.source = source
        self.container = container
        self.resource_header = bytes(resource_header)
        self.original = bytes(body)
        self.scheme = normalise_scheme(scheme)
        # what the data alone says; the panel overwrites it with the disc's patch states or the
        # user's choice (see detect_scheme)
        self.scheme_detection: dict[str, Any] = {}
        self._parse()
        self.set_scheme(self.scheme)

    # ------------------------------------------------------------------ position scheme
    def set_scheme(self, scheme: str) -> str:
        """Read every position code through ``scheme`` (retail | edge | one_pool).

        Nothing in the body changes: this decides which names the editor prints, which chips it
        offers, which codes the Position picker will write and which code a CSV's ``OLB`` maps to.
        """

        self.scheme = normalise_scheme(scheme)
        for player in self.players:
            player.record.scheme = self.scheme
        return self.scheme

    def position_census(self, pool: str | None = "primary") -> dict[int, int]:
        """How many players carry each position code, by default in the primary pool only.

        The 68 secondary records are the class generator's templates: they are keyed one per enum
        and ``tools/nfl2k5_roster_reclassify`` deliberately leaves them alone, so a reclassified
        roster still holds an OLB template.  Counting them would hide the one signal there is.
        """

        counts = {code: 0 for code in range(len(POSITIONS))}
        for player in self.players:
            if pool is not None and player.pool != pool:
                continue
            code = player.record.values["position"]
            counts[code] = counts.get(code, 0) + 1
        return counts

    # ------------------------------------------------------------------ pointers
    def rel(self, field_offset: int) -> int | None:
        value = struct.unpack_from("<i", self.body, field_offset)[0]
        return None if value == 0 else field_offset + value - 1

    def set_rel(self, field_offset: int, target: int | None) -> None:
        struct.pack_into("<i", self.body, field_offset, 0 if target is None else target - field_offset + 1)

    def u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.body, offset)[0]

    # ------------------------------------------------------------------ parse
    def _parse(self) -> None:
        b, base = self.body, self.base
        _require(len(b) >= base + 0x100, "the roster block is truncated")
        _require(bytes(b[base + 0x0C: base + 0x10]) == b"ROST" and self.u32(base + 0x10) == 17,
                 "ROST preamble (magic at +0x0C, version 17 at +0x10)")
        root = self.rel(base + 0x14)
        _require(root == base + OBJ_OFF, f"the roster object should sit at +0x40, found {root}")
        self.players: list[Player] = []
        self.by_offset: dict[int, Player] = {}
        for pool in POOLS:
            count_field, table_field = base + POOL_FIELDS[pool][0], base + POOL_FIELDS[pool][1]
            count = self.u32(count_field)
            table = self.rel(table_field)
            _require(table is not None, f"the {pool} player table pointer is null")
            assert table is not None
            _require(0 <= count <= 8000, f"implausible {pool} player count {count}")
            _require(table + count * PLAYER_SIZE <= len(b), f"the {pool} player table runs past the body")
            for index in range(count):
                offset = table + index * PLAYER_SIZE
                player = Player(pool=pool, index=index, offset=offset,
                                record=PlayerRecord.decode(bytes(b[offset: offset + PLAYER_SIZE]),
                                                           self.scheme))
                self.players.append(player)
                self.by_offset[offset] = player
        self.primary_table = self.rel(base + POOL_FIELDS["primary"][1])
        # colleges
        self.colleges: list[str] = []
        self.college_offsets: list[int] = []
        college_count = self.u32(base + COLLEGE_COUNT_FIELD)
        college_table = self.rel(base + COLLEGE_TABLE_FIELD)
        self.college_table = college_table
        self.college_count = college_count
        college_strings: list[int] = []
        if college_table is not None and 0 < college_count <= 4000:
            for index in range(college_count):
                record = college_table + index * COLLEGE_SIZE
                target = self.rel(record)
                self.college_offsets.append(record)
                if target is None:
                    self.colleges.append("")
                    continue
                college_strings.append(target)
                self.colleges.append(read_utf16z(b, target)[0])
        self.college_record_index = {offset: i for i, offset in enumerate(self.college_offsets)}
        # teams
        self.teams: list[TeamRecord] = []
        team_count = self.u32(base + TEAM_COUNT_FIELD)
        team_table = self.rel(base + TEAM_TABLE_FIELD)
        _require(team_table is not None and 0 < team_count <= 128, "the team table is missing or implausible")
        assert team_table is not None
        self.team_table = team_table
        for index in range(team_count):
            offset = team_table + index * TEAM_SIZE
            count = b[offset + TEAM_PLAYER_COUNT]
            slots: list[int] = []
            for slot in range(min(count, TEAM_SLOTS)):
                target = self.rel(offset + slot * 4)
                if target is None or target not in self.by_offset:
                    break
                slots.append(target)
                self.by_offset[target].teams.append(index)
            coach = self.rel(offset + TEAM_COACH)
            team = TeamRecord(index=index, offset=offset,
                              nickname=self._string_at(offset + TEAM_NICKNAME),
                              abbreviation=self._string_at(offset + TEAM_ABBREVIATION),
                              city=self._string_at(offset + TEAM_CITY),
                              player_count=count, slots=slots, original_slots=tuple(slots),
                              coach_offset=coach,
                              scheme=struct.unpack_from("<H", b, offset + TEAM_SCHEME_WORD)[0])
            self.teams.append(team)
        # free agents
        self.free_agents: list[int] = []
        fa_count = self.u32(base + FREE_AGENT_COUNT_FIELD)
        fa_list = self.rel(base + FREE_AGENT_LIST_FIELD)
        if fa_list is not None and 0 <= fa_count <= 4000:
            for index in range(fa_count):
                target = self.rel(fa_list + index * 4)
                if target is None or target not in self.by_offset:
                    break
                self.free_agents.append(target)
        self.free_agent_list = fa_list
        # names, colleges and groups
        name_offsets: list[int] = []
        self.name_refs: dict[int, int] = {}
        for player in self.players:
            for key in ("first_name_pointer", "last_name_pointer"):
                if player.record.values[key]:
                    target = self._pointer_target(player.offset, key)
                    name_offsets.append(target)
                    self.name_refs[target] = self.name_refs.get(target, 0) + 1
        self.names = StringPool(self.body, name_offsets, "player name")
        self.college_pool = StringPool(self.body, college_strings, "college") if college_strings else None
        free_agent_set = set(self.free_agents)
        for player in self.players:
            player.first = self._player_string(player, "first_name_pointer")
            player.last = self._player_string(player, "last_name_pointer")
            record_offset = self._pointer_target(player.offset, "college_pointer") if player.record.values["college_pointer"] else None
            player.college_index = self.college_record_index.get(record_offset) if record_offset is not None else None
            player.college = self.colleges[player.college_index] if player.college_index is not None else ""
            if player.teams:
                player.group = "team"
            elif player.offset in free_agent_set:
                player.group = "free_agent"
            elif player.pool == "primary" and player.record.values["player_type"] == 0:
                player.group = "draft_class"
            else:
                player.group = "pool"

    def _string_at(self, field_offset: int) -> str:
        target = self.rel(field_offset)
        return "" if target is None else read_utf16z(self.body, target)[0]

    def _pointer_target(self, record_offset: int, key: str) -> int:
        f = FIELD_BY_NAME[key]
        field_offset = record_offset + f.offset
        value = _signed(int.from_bytes(self.body[field_offset: field_offset + 4], "little"))
        return field_offset + value - 1

    def _player_string(self, player: Player, key: str) -> str:
        if not player.record.values[key]:
            return ""
        return self.names.text_at(self._pointer_target(player.offset, key))

    # ------------------------------------------------------------------ queries
    def by_pool(self, pool: str) -> list[Player]:
        return [p for p in self.players if p.pool == pool]

    def team_players(self, index: int) -> list[Player]:
        return [self.by_offset[offset] for offset in self.teams[index].slots]

    def group_players(self, group: str) -> list[Player]:
        return [p for p in self.players if p.group == group]

    def summary(self) -> dict[str, Any]:
        return {"players": len(self.players), "primary": len(self.by_pool("primary")),
                "secondary": len(self.by_pool("secondary")), "teams": len(self.teams),
                "colleges": len(self.colleges), "free_agents": len(self.free_agents),
                "draft_class": len(self.group_players("draft_class")),
                "names": self.names.summary(), "source": self.source,
                "scheme": self.scheme, "base": f"0x{self.base:x}"}

    def depth_chart(self, team_index: int) -> dict[int, list[Player]]:
        """The team's players grouped by position CODE, in the game's own rank order.

        The depth chart is per code, not per label: under one pool the edge rushers (16) and the
        interior (15) are separate chains even though retail called both "DL", and the retired
        OLB code shares the LB chain because the game's kind mapping already sends it there.
        """

        chart: dict[int, list[Player]] = {}
        for player in self.team_players(team_index):
            chart.setdefault(player.record.values["position"], []).append(player)
        for group in chart.values():
            group.sort(key=lambda p: (p.record.values["depth_rank"], p.record.values["depth_side"],
                                      p.index))
        return chart

    def depth_slot(self, team_index: int, player: Player) -> tuple[int, int]:
        """``(nth, of)`` for this player inside his own position code on this team, 1-based."""

        group = self.depth_chart(team_index).get(player.record.values["position"], [])
        for index, candidate in enumerate(group):
            if candidate is player:
                return index + 1, len(group)
        return 0, len(group)

    def set_position(self, player: Player, code: int | str) -> int:
        """Set a position through the loaded scheme, refusing a code the scheme retired."""

        value = position_code(code, self.scheme)
        check_position_code(value, self.scheme)
        player.record.set("position", value)
        return value

    # ------------------------------------------------------------------ edits
    def set_name(self, player: Player, which: str, text: str) -> dict[str, Any]:
        """Set a player's first or last name through the shared pool.  ``which`` is first|last."""

        _require(which in ("first", "last"), "which must be 'first' or 'last'")
        key = "first_name_pointer" if which == "first" else "last_name_pointer"
        text = validate_name(text)
        current = self._pointer_target(player.offset, key) if player.record.values[key] else None
        if current is not None and self.names.text_at(current) == text:
            return {"changed": False, "offset": current, "mode": "unchanged"}
        users = self.name_refs.get(current, 0) if current is not None else 0
        before_free = self.names.free_bytes
        offset = self.names.place(text, current=current, sole_user=users <= 1)
        field_offset = player.offset + FIELD_BY_NAME[key].offset
        self.set_rel(field_offset, offset)
        player.record.values[key] = int.from_bytes(self.body[field_offset: field_offset + 4], "little")
        if current is not None:
            remaining = self.name_refs.get(current, 1) - 1
            if remaining <= 0:
                self.name_refs.pop(current, None)
            else:
                self.name_refs[current] = remaining
        self.name_refs[offset] = self.name_refs.get(offset, 0) + 1
        if current is not None and current != offset and self.name_refs.get(current, 0) == 0:
            self.names.release_if_unused(current)
        setattr(player, which, text)
        mode = "shared" if self.name_refs[offset] > 1 else ("in place" if offset == current else "moved")
        return {"changed": True, "offset": offset, "mode": mode,
                "free_bytes_before": before_free, "free_bytes_after": self.names.free_bytes}

    def set_college(self, player: Player, index: int) -> None:
        _require(0 <= index < len(self.college_offsets), f"college index {index} is outside 0..{len(self.college_offsets) - 1}")
        offset = player.offset + FIELD_BY_NAME["college_pointer"].offset
        self.set_rel(offset, self.college_offsets[index])
        player.record.values["college_pointer"] = int.from_bytes(self.body[offset: offset + 4], "little")
        player.college_index = index
        player.college = self.colleges[index]

    def move_in_depth(self, team_index: int, slot: int, delta: int) -> bool:
        """Move one player up or down his team's pointer list -- Finn's ↑↓ arrows."""

        team = self.teams[team_index]
        target = slot + delta
        if not (0 <= slot < len(team.slots) and 0 <= target < len(team.slots)):
            return False
        team.slots[slot], team.slots[target] = team.slots[target], team.slots[slot]
        return True

    # ------------------------------------------------------------------ serialise
    def to_body(self) -> bytes:
        """The block with every record, team slot list and string edit written back."""

        out = bytearray(self.body)
        for player in self.players:
            out[player.offset: player.offset + PLAYER_SIZE] = player.record.encode()
        for team in self.teams:
            # only a team whose order actually changed is rewritten, and only over the slots we
            # parsed: a pointer we could not resolve stays exactly as the roster shipped it
            if not team.reordered:
                continue
            for slot, target in enumerate(team.slots):
                field_offset = team.offset + slot * 4
                struct.pack_into("<i", out, field_offset, target - field_offset + 1)
        return bytes(out)

    def changed_offsets(self) -> list[int]:
        after = self.to_body()
        return [i for i in range(len(after)) if after[i] != self.original[i]]

    def diff(self) -> list[dict[str, Any]]:
        """Per-player differences against the body this document was loaded from.

        Pointer fields are reported as the **text** they resolve to (first / last / college), not as
        offsets: where a name landed in the pool is an implementation detail, and a name that moved
        without changing is not an edit anybody wants to read."""

        out: list[dict[str, Any]] = []
        original = RosterDocument.__new__(RosterDocument)     # a cheap read-only view of the load state
        original.body = bytearray(self.original)
        original.base = self.base
        for player in self.players:
            before = PlayerRecord.decode(self.original[player.offset: player.offset + PLAYER_SIZE])
            changes = {name: (before.values[name], player.record.values[name])
                       for name in player.record.values
                       if name not in POINTER_FIELDS and before.values[name] != player.record.values[name]}
            texts: dict[str, tuple[str, str]] = {}
            for which, key in (("first", "first_name_pointer"), ("last", "last_name_pointer")):
                was = original._player_string_at(player.offset, key) if before.values[key] else ""
                now = getattr(player, which)
                if was != now:
                    texts[which] = (was, now)
            was_college = original._college_name_at(player.offset, self.colleges, self.college_record_index)
            if was_college != player.college:
                texts["college"] = (was_college, player.college)
            if changes or texts:
                out.append({"pool": player.pool, "index": player.index, "name": player.display,
                            "changes": changes, "texts": texts})
        return out

    def _player_string_at(self, record_offset: int, key: str) -> str:
        return read_utf16z(self.body, self._pointer_target(record_offset, key))[0]

    def _college_name_at(self, record_offset: int, colleges: Sequence[str],
                         index_by_offset: Mapping[int, int]) -> str:
        raw = int.from_bytes(self.body[record_offset: record_offset + 4], "little")
        if not raw:
            return ""
        target = record_offset + _signed(raw) - 1
        position = index_by_offset.get(target)
        return colleges[position] if position is not None and position < len(colleges) else ""


def validate_name(text: str) -> str:
    """A name the game's fixed 16-wchar buffers and its own data both accept."""

    value = " ".join(str(text).split())
    _require(bool(value), "a name cannot be empty")
    _require(len(value) <= 15, f"{value!r} is longer than the game's 15-character name buffer")
    for character in value:
        _require(character.isalnum() or character in " '-.", f"{value!r} contains {character!r}")
    return value


# --------------------------------------------------------------------------------------------- loaders
def _outer_image():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return importlib.import_module("nfl2k5_playbook_position_recode").OuterImage


def _entry(archive) -> Any:
    entries = archive.entries
    _require(len(entries) > ROST_OUTER_INDEX, f"the archive has no outer entry {ROST_OUTER_INDEX}")
    entry = entries[ROST_OUTER_INDEX]
    _require(entry.size == RESOURCE_SIZE,
             f"outer entry {ROST_OUTER_INDEX} is 0x{entry.size:x} bytes, not the main roster")
    return entry


def find_block_base(payload: bytes) -> int:
    """Where the ROST block starts inside a save arena (0 for a roster save, 0x2E0 for a franchise)."""

    for candidate in (0, FRANCHISE_BLOCK_OFFSET):
        if (len(payload) > candidate + 0x18 and payload[candidate + 0x0C: candidate + 0x10] == b"ROST"
                and struct.unpack_from("<I", payload, candidate + 0x10)[0] == 17):
            return candidate
    index = payload.find(b"ROST", 0, 0x10000)
    while index != -1:
        base = index - 0x0C
        if base >= 0 and struct.unpack_from("<I", payload, base + 0x10)[0] == 17:
            return base
        index = payload.find(b"ROST", index + 1, 0x10000)
    raise RosterRecordError("no ROST block found in this save")


def load_body(body: bytes, *, scheme: str = "retail") -> RosterDocument:
    """A bare ROST body (0x90F60 bytes on the retail disc)."""

    return RosterDocument(body, base=0, source="body", scheme=scheme)


def load_image(path: Path | str, *, scheme: str = "retail", detect: bool = False) -> RosterDocument:
    """The main roster resource of a disc image or a loose pack folder (read-only).

    With ``detect=True`` the disc's own patch states decide the position scheme (see
    ``detect_scheme``); otherwise the caller says, and ``retail`` is the default.
    """

    with _outer_image()(path) as archive:
        entry = _entry(archive)
        resource = archive.read(entry.virtual_offset, entry.size)
    _require(resource[:4] == b"ROST" and len(resource) == RESOURCE_SIZE, "the roster resource is foreign")
    document = RosterDocument(resource[RESOURCE_HEADER_SIZE:], base=0, source=str(path),
                              resource_header=resource[:RESOURCE_HEADER_SIZE], scheme=scheme)
    if detect:
        document.scheme_detection = detect_scheme(document, source=path)
        document.set_scheme(str(document.scheme_detection["scheme"]))
    return document


def resource_status(resource: bytes) -> str:
    """retail | edited | foreign for an outer-entry-5 payload."""

    if len(resource) != RESOURCE_SIZE or resource[:4] != b"ROST":
        return "foreign"
    body = resource[RESOURCE_HEADER_SIZE:]
    if hashlib.sha256(body).hexdigest() == RETAIL_BODY_SHA256:
        return "retail"
    try:
        RosterDocument(body)
    except (RosterRecordError, struct.error):
        return "foreign"
    return "edited"


def status(path: Path | str) -> str:
    with _outer_image()(path) as archive:
        entry = _entry(archive)
        return resource_status(archive.read(entry.virtual_offset, entry.size))


# ------------------------------------------------------------------------------------ scheme detection
# Retail primary-pool census, measured on the disc: OLB 191, ILB 131, DT 183, DE 204 (2,479 records).
# After ``tools/nfl2k5_roster_reclassify`` the same pool reads OLB 0, LB 305, DT 208, EDGE 196: every
# OLB has become an LB (4-3 teams) or an EDGE (3-4 teams), so **an empty OLB code is the signal**.
# The 68 secondary templates keep one record per enum -- OLB included -- which is why the census
# counts the primary pool only.
RETAIL_PRIMARY_POSITION_CENSUS = {
    0: 147, 1: 70, 2: 69, 3: 242, 4: 248, 5: 86, 6: 108, 7: 138, 8: 101, 9: 141,
    10: 191, 11: 131, 12: 107, 13: 158, 14: 155, 15: 183, 16: 204,
}


def detect_scheme_from_data(document: RosterDocument) -> dict[str, Any]:
    """Infer the position scheme from the roster records alone (a save or a bare ROST body).

    The heuristic, and its limits, stated plainly:

    * **one_pool** when the primary pool has **no** player at code 10 while codes 11 and 16 both
      have players.  Retail ships 191 OLBs, and the reclassify pass is the only thing that empties
      the code, so an empty OLB pool on a roster that still has linebackers and ends is decisive.
    * anything else reads as **retail**, because the EDGE rename is text: it rewrites the
      executable's strings and 247 "Def End" last names in the *historic* ROST resources, and
      touches nothing in the main roster body.  A save or a loose body therefore **cannot** show
      it, and the editor says so rather than guessing.

    Either way the user can override with the panel's "Position scheme" selector.
    """

    census = document.position_census("primary")
    olb, lb, interior, edge = (census.get(code, 0) for code in FRONT_CODES)
    if olb == 0 and lb > 0 and edge > 0:
        return {
            "scheme": "one_pool", "confidence": "high", "census": census, "source": "roster data",
            "why": (f"no primary-pool player carries the retired OLB code (retail has "
                    f"{RETAIL_PRIMARY_POSITION_CENSUS[10]}), and the roster still holds {lb} at LB "
                    f"(11), {edge} at EDGE (16) and {interior} interior (15)"),
        }
    return {
        "scheme": "retail", "confidence": "low", "census": census, "source": "roster data",
        "why": (f"{olb} primary-pool players still carry OLB (10), so this roster has not been "
                "reclassified. Roster data cannot show the EDGE rename -- that patch only rewrites "
                "text in the executable and in the historic ROST name strings -- so pick "
                "\"EDGE names\" yourself if this came from an EDGE disc"),
    }


def detect_scheme_from_states(states: Mapping[str, Any]) -> dict[str, Any]:
    """Read the scheme off a disc's own patch statuses (``mod_build.inspect``).

    ``position_pools`` is the one-pool patch (OLB retired, 11 = LB, 16 = EDGE), ``edge_rename`` is
    the DE -> EDGE text pass (executable) with ``edge_rename_disc`` its pack-side half, and
    ``scheme_labels`` is only the depth-chart slot names, which never move a roster code.
    """

    def text(value: Any) -> str:
        if isinstance(value, Mapping):
            return str(value.get("status", "unknown"))
        return str(value if value is not None else "unknown")

    pools, labels = text(states.get("position_pools")), text(states.get("scheme_labels"))
    xbe, disc = text(states.get("edge_rename")), text(states.get("edge_rename_disc"))
    common = {"confidence": "high", "source": "disc patch states",
              "states": {"position_pools": pools, "edge_rename": xbe, "edge_rename_disc": disc,
                         "scheme_labels": labels}}
    if pools == "applied":
        return {**common, "scheme": "one_pool",
                "why": f"the disc's {SCHEME_PATCH_NAMES['one_pool']} patch reads applied "
                       f"(scheme_labels {labels})"}
    if "applied" in (xbe, disc):
        return {**common, "scheme": "edge",
                "why": (f"the EDGE rename reads applied (executable {xbe}, disc text {disc}) and "
                        f"position_pools reads {pools}")}
    if pools in ("unknown", "n/a", "foreign") and xbe in ("unknown", "n/a", "foreign"):
        return {**common, "scheme": "retail", "confidence": "low",
                "why": f"the disc's patch states are {pools} / {xbe}; falling back to the retail table"}
    return {**common, "scheme": "retail",
            "why": f"position_pools reads {pools} and the EDGE rename reads {xbe}"}


def inspect_states(source: Path | str) -> dict[str, Any] | None:
    """The four patch states ``detect_scheme_from_states`` needs, or ``None`` if we cannot read them."""

    try:
        from . import mod_build                            # local: mod_build imports this module back
        report = mod_build.inspect(Path(source))
    except Exception:                                       # noqa: BLE001 - detection is never fatal
        return None
    return {key: report.get(key) for key in
            ("position_pools", "edge_rename", "edge_rename_disc", "scheme_labels")}


def detect_scheme(document: RosterDocument, *, source: Path | str | None = None,
                  states: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Decide the position scheme for a loaded roster.

    A disc can say for itself (its patch states); a save or a bare body can only be inferred from
    the records.  When both are available they are combined, and a disagreement is reported rather
    than silently resolved -- a disc whose executable carries the pools but whose ROST was never
    reclassified is a real, broken state somebody could hand us.
    """

    data = detect_scheme_from_data(document)
    if states is None and source is not None:
        states = inspect_states(source)
    if not states:
        return {**data, "data": data, "disc": None, "note": ""}
    disc = detect_scheme_from_states(states)
    note = ""
    scheme = disc["scheme"]
    if disc["scheme"] == "one_pool" and data["scheme"] != "one_pool":
        note = ("the executable carries the one-pool patch but the roster still has "
                f"{data['census'].get(10, 0)} players at the retired OLB code: run the reclassify "
                "pass (Build & Share -> Advanced) or the depth chart will not fill")
    elif data["scheme"] == "one_pool" and disc["scheme"] != "one_pool":
        scheme = "one_pool"
        note = ("the roster is reclassified (no OLB) but the executable's position_pools patch "
                f"reads {disc.get('states', {}).get('position_pools', 'unknown')}: the names below "
                "follow the roster")
    why = disc["why"] + ("; " + data["why"] if data["scheme"] == "one_pool" else "")
    return {"scheme": scheme, "confidence": disc["confidence"], "source": "disc patch states",
            "why": why, "census": data["census"], "note": note, "data": data, "disc": disc}


# --------------------------------------------------------------------------------------------- saves
@dataclass
class SaveMember:
    name: str
    data: bytes


class SaveContainer:
    """An Xbox NFL 2K5 save: SAVEGAME.DAT + EXTRA plus whatever else the container carries.

    Reads an Action Replay ``.zip``, an extracted save directory or a loose ``SAVEGAME.DAT`` with
    its ``EXTRA`` beside it.  The stored EXTRA is verified on load; writing re-signs and copies
    every other member byte for byte, because renaming or dropping ``SaveMeta.xbx`` is what makes
    the game call a save corrupt.
    """

    def __init__(self, kind: str, path: Path, members: dict[str, bytes], savegame_name: str,
                 extra_name: str, verified: bool) -> None:
        self.kind = kind
        self.path = path
        self.members = members
        self.savegame_name = savegame_name
        self.extra_name = extra_name
        self.verified = verified

    # ------------------------------------------------------------------ construction
    @classmethod
    def load(cls, path: Path | str, *, require_signature: bool = True) -> "SaveContainer":
        source = Path(path).expanduser()
        _require(source.exists(), f"{source} does not exist")
        if source.is_dir():
            members = {}
            for item in sorted(source.rglob("*")):
                if item.is_file():
                    members[item.relative_to(source).as_posix()] = item.read_bytes()
            kind = "directory"
        elif zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as archive:
                members = {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}
            kind = "zip"
        else:
            members = {source.name: source.read_bytes()}
            extra = source.with_name(EXTRA_NAME)
            if extra.is_file():
                members[EXTRA_NAME] = extra.read_bytes()
            kind = "loose"
        savegame_name = _member_named(members, SAVEGAME_NAME)
        _require(savegame_name is not None, f"no {SAVEGAME_NAME} in {source}")
        assert savegame_name is not None
        extra_name = _member_named(members, EXTRA_NAME) or _sibling_extra(savegame_name)
        stored = members.get(extra_name)
        verified = stored is not None and verify_extra(members[savegame_name], stored)
        if require_signature:
            _require(stored is not None, f"no {EXTRA_NAME} beside {savegame_name}; refusing to edit a save "
                                         "whose signature we cannot check")
            _require(verified, "the stored EXTRA does not match SAVEGAME.DAT; this save is already "
                               "damaged and re-signing it would hide that")
        return cls(kind, source, members, savegame_name, extra_name, verified)

    # ------------------------------------------------------------------ content
    @property
    def savegame(self) -> bytes:
        return self.members[self.savegame_name]

    def document(self, *, scheme: str = "retail") -> RosterDocument:
        payload = self.savegame
        base = find_block_base(payload)
        return RosterDocument(payload, base=base, source=str(self.path), container=self, scheme=scheme)

    def with_savegame(self, payload: bytes) -> dict[str, bytes]:
        members = dict(self.members)
        members[self.savegame_name] = payload
        members[self.extra_name] = sign_save(payload)
        return members

    def write(self, target: Path | str, payload: bytes, *, overwrite: bool = False) -> dict[str, Any]:
        """Write a re-signed copy of this container.  Never writes over the source."""

        destination = Path(target).expanduser()
        _require(destination.resolve() != self.path.resolve(), "the target must not be the source save")
        members = self.with_savegame(payload)
        if self.kind == "zip" or destination.suffix.lower() == ".zip":
            _require(overwrite or not destination.exists(), f"{destination} exists")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
                for name in self.members:
                    archive.writestr(name, members[name])
            written = str(destination)
        else:
            destination.mkdir(parents=True, exist_ok=True)
            for name, data in members.items():
                item = destination / name
                item.parent.mkdir(parents=True, exist_ok=True)
                _require(overwrite or not item.exists(), f"{item} exists")
                item.write_bytes(data)
            written = str(destination)
        untouched = [name for name in self.members if name not in (self.savegame_name, self.extra_name)]
        return {"target": written, "kind": self.kind, "savegame": self.savegame_name,
                "extra": self.extra_name, "extra_sha1": members[self.extra_name].hex(),
                "members_copied_byte_for_byte": untouched, "signed": True}


def _member_named(members: Mapping[str, bytes], leaf: str) -> str | None:
    for name in members:
        if name.rsplit("/", 1)[-1].upper() == leaf.upper():
            return name
    return None


def _sibling_extra(savegame_name: str) -> str:
    head = savegame_name.rsplit("/", 1)
    return f"{head[0]}/{EXTRA_NAME}" if len(head) == 2 else EXTRA_NAME


def sign_save(savegame: bytes) -> bytes:
    """``EXTRA`` for a SAVEGAME.DAT: HMAC-SHA1(SigKey16, the whole file)."""

    return hmac.new(SIG_KEY, savegame, hashlib.sha1).digest()


def verify_extra(savegame: bytes, extra: bytes) -> bool:
    return len(extra) == EXTRA_SIZE and hmac.compare_digest(sign_save(savegame), bytes(extra))


def load_save(path: Path | str, *, require_signature: bool = True, scheme: str = "retail",
              detect: bool = False) -> RosterDocument:
    document = SaveContainer.load(path, require_signature=require_signature).document(scheme=scheme)
    if detect:
        document.scheme_detection = detect_scheme(document)
        document.set_scheme(str(document.scheme_detection["scheme"]))
    return document


def save_document(document: RosterDocument, target: Path | str, *, overwrite: bool = False) -> dict[str, Any]:
    """Write an edited save-loaded document to a re-signed copy beside the original."""

    _require(document.container is not None, "this document did not come from a save container")
    assert document.container is not None
    payload = document.to_body()        # for a save-loaded document this is the whole arena
    _require(len(payload) == len(document.container.savegame), "the arena changed size; refusing to write")
    return document.container.write(target, payload, overwrite=overwrite)


# --------------------------------------------------------------------------------------------- edits doc
def edits_document(document: RosterDocument, *, name: str = "", author: str = "") -> dict[str, Any]:
    """A sparse, shareable record of everything changed since load (the Build & Share asset)."""

    edits = []
    for entry in document.diff():
        player = next(p for p in document.players if p.pool == entry["pool"] and p.index == entry["index"])
        # the identity is the name the SOURCE roster carried, so a target disc can be cross-checked
        was_first = entry["texts"]["first"][0] if "first" in entry["texts"] else player.first
        was_last = entry["texts"]["last"][0] if "last" in entry["texts"] else player.last
        item: dict[str, Any] = {"pool": entry["pool"], "index": entry["index"], "last": was_last,
                                "first": was_first,
                                "fields": {key: after for key, (_before, after) in entry["changes"].items()}}
        if entry["texts"]:
            item["names"] = {key: after for key, (_before, after) in entry["texts"].items()}
        edits.append(item)
    return {"schema": EDITS_SCHEMA, "name": name, "author": author,
            "source_body_sha256": hashlib.sha256(document.original).hexdigest(),
            "players": len(document.players), "edits": edits}


def edits_between(base_body: bytes, patched_body: bytes, *, name: str = "") -> dict[str, Any]:
    """The roster-edits document that turns ``base_body`` into ``patched_body``.

    Share uses this to recover the edit from a patched copy when the creator no longer has the
    JSON: the document is rebuilt from the two rosters themselves."""

    document = RosterDocument(patched_body)
    document.original = bytes(base_body)
    return edits_document(document, name=name)


def read_edits(source: Path | str | Mapping[str, Any]) -> dict[str, Any]:
    document = source if isinstance(source, Mapping) else json.loads(Path(source).read_text(encoding="utf-8"))
    _require(isinstance(document, Mapping), "a roster-edits file must be a JSON object")
    _require(str(document.get("schema")) == EDITS_SCHEMA,
             f"unknown roster-edits schema {document.get('schema')!r}; expected {EDITS_SCHEMA}")
    edits = document.get("edits")
    _require(isinstance(edits, list), "the roster-edits document has no edits list")
    return dict(document)


def apply_body(body: bytes, source: Path | str | Mapping[str, Any], *,
               scheme: str | None = None) -> tuple[bytes, dict[str, Any]]:
    """Apply a roster-edits document to a ROST body; returns the new body and a receipt.

    ``scheme`` is the TARGET roster's position scheme.  It defaults to what the target's own
    records say (``detect_scheme_from_data``), and it is what stops an edit authored on a retail
    disc from writing the retired OLB code into a reclassified one: the code is mapped to the pool
    that absorbed it and the receipt's log says so, for every record it moved.
    """

    doc = read_edits(source)
    roster = RosterDocument(body)
    target_scheme = normalise_scheme(scheme) if scheme else str(detect_scheme_from_data(roster)["scheme"])
    roster.set_scheme(target_scheme)
    index: dict[tuple[str, int], Player] = {(p.pool, p.index): p for p in roster.players}
    log: list[str] = []
    applied = 0
    fields_written = 0
    for entry in doc["edits"]:
        key = (str(entry.get("pool", "primary")), int(entry.get("index", -1)))
        player = index.get(key)
        if player is None:
            log.append(f"{key}: no such roster record")
            continue
        expected_last = str(entry.get("last", "") or "")
        if expected_last and expected_last != player.last:
            log.append(f"{key}: the record now holds {player.display!r}, the edit was made for "
                       f"{entry.get('first', '')} {expected_last}".strip())
        changed = False
        for name, value in dict(entry.get("fields") or {}).items():
            if name not in FIELD_BY_NAME:
                log.append(f"{key}: unknown field {name!r}")
                continue
            if name in POINTER_FIELDS:
                log.append(f"{key}: {name} is a pointer and cannot travel between roster copies")
                continue
            if name == "position" and is_retired_position(int(value), target_scheme):
                instead = replacement_position_code(int(value), target_scheme)
                log.append(f"{key}: the edit sets "
                           f"{position_name(int(value), 'retail')} (code {value}), retired on this "
                           f"{SCHEME_TITLES[target_scheme]} roster; wrote "
                           f"{position_name(instead, target_scheme)} (code {instead}) instead")
                value = instead
            try:
                player.record.set(name, int(value))
            except RosterRecordError as exc:
                log.append(f"{key}: {exc}")
                continue
            fields_written += 1
            changed = True
        for which, text in dict(entry.get("names") or {}).items():
            try:
                if which == "college":
                    _require(text in roster.colleges, f"{text!r} is not one of this roster's colleges")
                    roster.set_college(player, roster.colleges.index(str(text)))
                else:
                    roster.set_name(player, which, str(text))
            except RosterRecordError as exc:
                log.append(f"{key} {which}: {exc}")
                continue
            fields_written += 1
            changed = True
        applied += 1 if changed else 0
    out = roster.to_body()
    return out, {"edits": len(doc["edits"]), "players_changed": applied,
                 "fields_written": fields_written, "log": log}


def apply(path: Path | str, source: Path | str | Mapping[str, Any], *,
          progress: Callable[[str], None] | None = None,
          scheme: str | None = None) -> dict[str, Any]:
    """Write a roster-edits document into the main roster of the disc image at ``path`` (a COPY).

    ``scheme`` is the target disc's position scheme; ``None`` reads it off the target's records.
    """

    say = progress or (lambda _m: None)
    with _outer_image()(path, writable=True) as archive:
        entry = _entry(archive)
        before = archive.read(entry.virtual_offset, entry.size)
        state = resource_status(before)
        _require(state in ("retail", "edited"), f"the roster resource is {state}; refusing")
        say("Applying the roster edits")
        body, receipt = apply_body(before[RESOURCE_HEADER_SIZE:], source, scheme=scheme)
        replacement = before[:RESOURCE_HEADER_SIZE] + body
        if replacement == before:
            return {"status": state, "already_applied": True, "outer_index": ROST_OUTER_INDEX, **receipt}
        say("Writing the edited roster")
        count = archive.write(entry.virtual_offset, replacement)
        _require(count == len(replacement), "short write of the roster resource")
        _require(archive.read(entry.virtual_offset, entry.size) == replacement,
                 "read-back of the roster resource differs")
    return {"status": resource_status(replacement), "outer_index": ROST_OUTER_INDEX,
            "virtual_offset": f"0x{entry.virtual_offset:x}", **receipt}


# --------------------------------------------------------------------------------------------- CSV twin
CSV_IDENTITY = ("pool", "index", "team", "first", "last", "position", "jersey", "years_pro",
                "height", "weight", "hand", "college", "birth_date", "pbp_id", "photo_id",
                "contract_value", "contract_type", "contract_bonus", "contract_length",
                "contract_remaining", "skin", "face", "body", "dreads", "eye_black", "helmet",
                "face_mask", "face_shield", "mouthpiece", "turtleneck", "sleeves", "neck_roll",
                "left_glove", "right_glove", "left_wrist", "right_wrist", "left_elbow",
                "right_elbow", "left_shoe", "right_shoe", "depth_rank", "depth_side", "player_type")
CSV_COLUMNS = CSV_IDENTITY + RATING_BYTE_ORDER
CSV_READ_ONLY = frozenset({"pool", "index", "team"})


def _csv_row(document: RosterDocument, player: Player) -> dict[str, Any]:
    record = player.record
    birth = record.birth_date
    row: dict[str, Any] = {
        "pool": player.pool, "index": player.index,
        "team": document.teams[player.teams[0]].abbreviation if player.teams else player.group,
        "first": player.first, "last": player.last, "position": record.position_name,
        "jersey": record.values["jersey"], "years_pro": record.values["years_pro"],
        "height": record.values["height"], "weight": record.weight,
        "hand": HANDS[record.values["hand"]], "college": player.college,
        "birth_date": birth.isoformat() if birth else "",
        "pbp_id": record.values["pbp_id"], "photo_id": record.values["photo_id"],
        "contract_value": record.values["contract_value"],
        "contract_type": CONTRACT_TYPES[record.values["contract_type"]] if record.values["contract_type"] < len(CONTRACT_TYPES) else record.values["contract_type"],
        "contract_bonus": CONTRACT_BONUSES[record.values["contract_bonus"]] if record.values["contract_bonus"] < len(CONTRACT_BONUSES) else record.values["contract_bonus"],
        "contract_length": record.values["contract_length"],
        "contract_remaining": record.values["contract_remaining"],
        "skin": record.skin, "face": record.values["face"],
        "body": BODIES[record.values["body"]], "dreads": YES_NO[record.values["dreads"]],
        "eye_black": YES_NO[record.values["eye_black"]], "helmet": HELMETS[record.values["helmet"]],
        "face_mask": record.values["face_mask"],
        "face_shield": FACE_SHIELDS[record.values["face_shield"]] if record.values["face_shield"] < len(FACE_SHIELDS) else record.values["face_shield"],
        "mouthpiece": YES_NO[record.values["mouthpiece"]],
        "turtleneck": TURTLENECKS[record.values["turtleneck"]], "sleeves": SLEEVES[record.values["sleeves"]],
        "neck_roll": NECK_ROLLS[record.values["neck_roll"]] if record.values["neck_roll"] < len(NECK_ROLLS) else record.values["neck_roll"],
        "left_glove": record.left_glove, "right_glove": record.values["right_glove"],
        "left_wrist": record.left_wrist, "right_wrist": record.values["right_wrist"],
        "left_elbow": record.left_elbow, "right_elbow": record.values["right_elbow"],
        "left_shoe": record.values["left_shoe"], "right_shoe": record.values["right_shoe"],
        "depth_rank": record.values["depth_rank"], "depth_side": record.values["depth_side"],
        "player_type": record.values["player_type"],
    }
    row.update(record.ratings())
    return row


def export_csv(document: RosterDocument, players: Sequence[Player] | None = None, *,
               delimiter: str = ",") -> str:
    """Finn's "Export as Text", as a spreadsheet-friendly CSV (his own separator was ';').

    The ``position`` column is written in the document's own scheme (``EDGE`` and ``LB`` on a
    one-pool roster), and ``import_csv`` accepts **every** scheme's names whichever roster it is
    reading into, so a sheet exported from a retail disc still loads onto a one-pool disc.
    """

    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(CSV_COLUMNS), delimiter=delimiter,
                            lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for player in (players if players is not None else document.players):
        writer.writerow(_csv_row(document, player))
    return stream.getvalue()


def _enum_value(name: str, text: str) -> int:
    table = ENUMS.get(name)
    value = str(text).strip()
    if table is not None:
        folded = value.casefold()
        for index, label in enumerate(table):
            if label.casefold() == folded:
                return index
        if name == "position" and value.upper() in POSITION_CODE_BY_TEXT:
            # every scheme's names resolve, so "OLB", "ILB", "LB", "DE", "EDGE" and "RB" all read
            return POSITION_CODE_BY_TEXT[value.upper()]
    _require(value.lstrip("-").isdigit(), f"{name}: {text!r} is not one of {table or 'the accepted values'}")
    return int(value)


def import_csv(document: RosterDocument, text: str, *, delimiter: str | None = None) -> dict[str, Any]:
    """Read back a CSV this module wrote (or Finn's semicolon export) and apply it.

    Rows are matched by ``pool`` + ``index`` when present, otherwise by last+first name.  Only
    columns present in the file are touched, so a spreadsheet with three columns is a legal edit.
    The receipt reports ``rows`` matched, ``changed`` players and ``fields`` written."""

    sample = text.splitlines()[0] if text.strip() else ""
    if delimiter is None:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    by_key = {(p.pool, p.index): p for p in document.players}
    by_name: dict[tuple[str, str], list[Player]] = {}
    for player in document.players:
        by_name.setdefault((player.last.casefold(), player.first.casefold()), []).append(player)
    log: list[str] = []
    matched = 0
    changed_players = 0
    changed_fields = 0
    for number, row in enumerate(reader, start=2):
        clean = {(key or "").strip().lower(): (value or "") for key, value in row.items() if key}
        player = None
        if clean.get("pool") and str(clean.get("index", "")).strip().isdigit():
            player = by_key.get((clean["pool"].strip(), int(clean["index"])))
        if player is None:
            hits = by_name.get((clean.get("last", "").strip().casefold(), clean.get("first", "").strip().casefold()), [])
            if len(hits) == 1:
                player = hits[0]
            elif len(hits) > 1:
                log.append(f"row {number}: {clean.get('first', '')} {clean.get('last', '')} matches {len(hits)} records")
                continue
        if player is None:
            log.append(f"row {number}: no roster record matches")
            continue
        matched += 1
        touched = 0
        for column, value in clean.items():
            if column in CSV_READ_ONLY or column not in CSV_COLUMNS or value == "":
                continue
            try:
                changed_here, note = _apply_csv_cell(document, player, column, value)
                touched += changed_here
                if note:
                    log.append(f"row {number} {column}: {note}")
            except (RosterRecordError, ValueError) as exc:
                log.append(f"row {number} {column}: {exc}")
        changed_fields += touched
        changed_players += 1 if touched else 0
    return {"rows": matched, "changed": changed_players, "fields": changed_fields, "log": log}


def _apply_csv_cell(document: RosterDocument, player: Player, column: str,
                    value: str) -> tuple[int, str]:
    """Apply one cell.  Returns ``(fields written, note)``; the note goes in the receipt's log."""

    record = player.record
    if column in ("first", "last"):
        if value == getattr(player, column):
            return 0, ""
        document.set_name(player, column, value)
        return 1, ""
    if column == "college":
        if value == player.college:
            return 0, ""
        _require(value in document.colleges, f"{value!r} is not one of the roster's {len(document.colleges)} colleges")
        document.set_college(player, document.colleges.index(value))
        return 1, ""
    if column == "birth_date":
        date = dt.date.fromisoformat(value.strip())
        if record.birth_date == date:
            return 0, ""
        record.birth_date = date
        return 1, ""
    if column == "weight":
        new = int(value)
        if record.weight == new:
            return 0, ""
        record.weight = new
        return 1, ""
    if column == "skin":
        new = int(value)
        if record.skin == new:
            return 0, ""
        record.skin = new
        return 1, ""
    if column in ("left_glove", "left_wrist", "left_elbow"):
        new = int(value)
        if getattr(record, column) == new:
            return 0, ""
        setattr(record, column, new)
        return 1, ""
    note = ""
    if column == "position":
        # a sheet written against a retail roster carries OLB rows; on a one-pool roster that code
        # is retired, so map it to the pool that absorbed it and SAY SO rather than writing a code
        # no screen in the game fills
        new = position_code(value, document.scheme)
        if is_retired_position(new, document.scheme):
            instead = replacement_position_code(new, document.scheme)
            note = (f"{value!r} is {position_name(new, 'retail')} (code {new}), retired on this "
                    f"{SCHEME_TITLES[document.scheme]} roster; wrote "
                    f"{position_name(instead, document.scheme)} (code {instead}) instead")
            new = instead
    else:
        new = _enum_value(column, value) if column in ENUMS else int(value)
    if record.values.get(column) == new:
        return 0, note
    record.set(column, new)
    return 1, note


# --------------------------------------------------------------------------------------------- global
WHERE_OPERATORS = {
    ">=": lambda a, b: a >= b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
}


def global_edit_preview(document: RosterDocument, *, attribute: str, mode: str, value: float,
                        positions: Sequence[str] = (), teams: Sequence[int] = (),
                        rookies_only: bool = False, minimum: int = 0, maximum: int = RATING_MAX,
                        where: tuple[str, str, int] | None = None,
                        players: Sequence[Player] | None = None) -> list[dict[str, Any]]:
    """Finn's Global Attribute Editor: what "Set Attribute" would do, before it does it.

    ``mode`` is ``equal`` (set to value), ``add`` (+/- value) or ``percent`` (scale by value %).
    ``where`` is an optional ``(attribute, operator, value)`` condition, which is what turns this into
    "every QB with Speed >= 80 -> throw style B" or "every HB with Break Tackle >= 75 -> Power".

    ``positions`` are matched by the **code** they resolve to, in any scheme's names, so ``["DE"]``
    and ``["EDGE"]`` select the same players and a condition written on a retail disc still runs on
    a one-pool one."""

    _require(attribute in FIELD_BY_NAME or attribute in COMPOSITE_FIELDS or attribute in VIRTUAL_FIELDS,
             f"no roster field named {attribute!r}")
    _require(mode in ("equal", "add", "percent"), "mode must be equal, add or percent")
    if attribute == "position":
        # a sweep that moves people between positions has to land on a code the scheme still fills
        _require(mode == "equal", "a global position change must be 'set equal to' a position code")
        check_position_code(int(round(value)), document.scheme)
    condition = None
    if where is not None:
        key, operator, threshold = where
        _require(key in FIELD_BY_NAME or key in COMPOSITE_FIELDS or key in VIRTUAL_FIELDS,
                 f"no roster field named {key!r}")
        _require(operator in WHERE_OPERATORS,
                 f"unknown comparison {operator!r}; use one of {sorted(WHERE_OPERATORS)}")
        condition = (key, WHERE_OPERATORS[operator], int(threshold))
    wanted_positions = {position_code(p, document.scheme) for p in positions}
    wanted_teams = set(teams)
    out: list[dict[str, Any]] = []
    for player in (players if players is not None else document.players):
        if wanted_positions and player.record.values["position"] not in wanted_positions:
            continue
        if wanted_teams and not wanted_teams.intersection(player.teams):
            continue
        if rookies_only and player.record.values["years_pro"] != 0:
            continue
        if condition is not None and not condition[1](player.record.get(condition[0]), condition[2]):
            continue
        before = player.record.get(attribute)
        if mode == "equal":
            after = int(round(value))
        elif mode == "add":
            after = before + int(round(value))
        else:
            after = int(round(before * (1.0 + value / 100.0)))
        ceiling = len(ENUMS[attribute]) - 1 if attribute in VIRTUAL_FIELDS else maximum
        after = max(minimum, min(ceiling, after))
        if after != before:
            out.append({"pool": player.pool, "index": player.index, "name": player.display,
                        "position": player.record.position_name, "before": before, "after": after})
    return out


def global_edit_apply(document: RosterDocument, preview: Sequence[Mapping[str, Any]], attribute: str) -> int:
    by_key = {(p.pool, p.index): p for p in document.players}
    count = 0
    for row in preview:
        player = by_key.get((str(row["pool"]), int(row["index"])))
        if player is None:
            continue
        player.record.set(attribute, int(row["after"]))
        count += 1
    return count


# --------------------------------------------------------------------------------------------- passes
def advance_years_pro(document: RosterDocument, players: Sequence[Player] | None = None) -> int:
    """Finn's Tools > Auto-update > Advance year."""

    field = FIELD_BY_NAME["years_pro"]
    count = 0
    for player in (players if players is not None else document.players):
        current = player.record.values["years_pro"]
        if current < field.maximum:
            player.record.values["years_pro"] = current + 1
            count += 1
    return count


def restore_measurements(document: RosterDocument, retail: RosterDocument,
                         players: Sequence[Player] | None = None) -> int:
    """Finn's Restore Weight/Height (+DOB): put the shipped values back from a retail document."""

    index = {(p.pool, p.index): p for p in retail.players}
    keys = ("weight_raw", "height", "birth_month", "birth_day", "birth_year_low", "birth_year_high")
    count = 0
    for player in (players if players is not None else document.players):
        original = index.get((player.pool, player.index))
        if original is None:
            continue
        if any(player.record.values[key] != original.record.values[key] for key in keys):
            for key in keys:
                player.record.values[key] = original.record.values[key]
            count += 1
    return count


COPY_EXCLUDED = frozenset({"college_pointer", "first_name_pointer", "last_name_pointer",
                           "history_pointer", "pbp_id", "photo_id"})


def copy_player(source: PlayerRecord, target: PlayerRecord, *, mode: str = "all") -> int:
    """Finn's Paste / Paste-Attributes-Only / Paste-Photo.

    ``all`` copies everything except college, names, PBP and photo (his own rule); ``attributes``
    copies the 28 rating bytes only; ``photo`` copies the portrait id only."""

    _require(mode in ("all", "attributes", "photo"), "mode must be all, attributes or photo")
    if mode == "photo":
        keys: Sequence[str] = ("photo_id",)
    elif mode == "attributes":
        keys = RATING_BYTE_ORDER
    else:
        keys = tuple(name for name in (f.name for f in FIELDS) if name not in COPY_EXCLUDED)
    count = 0
    for key in keys:
        if target.values[key] != source.values[key]:
            target.values[key] = source.values[key]
            count += 1
    return count


# --------------------------------------------------------------------------------------------- checks
# Keyed by the CODE, not the label: the number a position is allowed to wear follows the pool the
# record is in, so a one-pool EDGE (16) keeps the defensive-end range and a one-pool LB (11) keeps
# the linebacker range whatever the disc prints.  The name-keyed table is the retail view of the
# same numbers and stays for callers that already import it.
JERSEY_RANGES_BY_CODE: dict[int, tuple[int, int]] = {
    0: (1, 19), 1: (1, 19), 2: (1, 19), 3: (10, 89), 9: (40, 89),
    7: (20, 49), 8: (20, 49), 4: (20, 49), 5: (20, 49), 6: (20, 49),
    12: (50, 79), 13: (50, 79), 14: (50, 79), 15: (50, 99), 16: (50, 99),
    10: (40, 59), 11: (40, 59),
}
JERSEY_RANGES: dict[str, tuple[int, int]] = {
    POSITIONS[code]: span for code, span in sorted(JERSEY_RANGES_BY_CODE.items())
}


def jersey_range(code: int) -> tuple[int, int]:
    return JERSEY_RANGES_BY_CODE.get(int(code), (0, 99))


def validate(document: RosterDocument, players: Sequence[Player] | None = None) -> list[dict[str, Any]]:
    """The validation cards: jersey ranges per position, rating bounds, pool budget, measurements."""

    findings: list[dict[str, Any]] = []
    for player in (players if players is not None else document.players):
        record = player.record
        position = record.position_name
        low, high = jersey_range(record.values["position"])
        number = record.values["jersey"]
        if not low <= number <= high:
            findings.append({"level": "warning", "player": player.display, "check": "jersey",
                             "detail": f"#{number} is outside the NFL range {low}-{high} for a {position}"})
        if is_retired_position(record.values["position"], document.scheme):
            instead = replacement_position_code(record.values["position"], document.scheme)
            findings.append({"level": "warning", "player": player.display, "check": "position",
                             "detail": f"carries {position_name(record.values['position'], 'retail')} "
                                       f"(code {record.values['position']}), which this roster's "
                                       f"{SCHEME_TITLES[document.scheme]} scheme retired; the game "
                                       f"lists him under a filter row no team fills. Move him to "
                                       f"{position_name(instead, document.scheme)}"})
        for name in RATING_BYTE_ORDER:
            if record.values[name] > RATING_MAX:
                findings.append({"level": "warning", "player": player.display, "check": "rating",
                                 "detail": f"{RATING_LABELS[name]} = {record.values[name]} is above 99 "
                                           "(the game clamps on import; Finn's Large Attributes allows it)"})
        if record.values["height"] and not 60 <= record.values["height"] <= 84:
            findings.append({"level": "error", "player": player.display, "check": "height",
                             "detail": f"{record.values['height']} inches is outside 5'0\"-7'0\""})
        if record.birth_date is None and record.values["birth_month"]:
            findings.append({"level": "warning", "player": player.display, "check": "birth date",
                             "detail": "the stored month/day/year is not a real date"})
        if record.values["headless"]:
            findings.append({"level": "error", "player": player.display, "check": "headless",
                             "detail": "+0x0C bit 7 is set; this model renders without a head "
                                       "(Finn's editor clears it on load)"})
    free = document.names.free_bytes
    findings.append({"level": "info", "player": "", "check": "name pool",
                     "detail": f"{document.names.capacity_bytes} bytes hold {len(document.names.blocks)} "
                               f"strings; {free} bytes free"})
    return findings


__all__ = [
    "ATTRIBUTE_CARDS", "BODIES", "CONTRACT_BONUSES", "CONTRACT_TYPES", "CSV_COLUMNS", "EDITS_SCHEMA",
    "ELBOWS", "ENUMS", "FACE_SHIELDS", "FIELDS", "FIELD_BY_NAME", "GLOVES", "HANDS", "HELMETS",
    "JERSEY_RANGES", "JERSEY_RANGES_BY_CODE", "KICKING_STYLE_PRESETS", "NECK_ROLLS", "POSITIONS",
    "POSITION_ALIASES", "POSITION_CODE_BY_TEXT", "POSITION_GROUPS", "POSITION_LONG_NAMES",
    "POSITION_SCHEMES", "OVERALL_WEIGHTS", "OVERALL_WEIGHTS_BY_CODE", "RATING_PROFILE_BY_CODE",
    "FRONT_CODES", "RETAIL_PRIMARY_POSITION_CENSUS", "SCHEME_CHIP_ORDER", "SCHEME_GROUP_CODES",
    "SCHEME_PATCH_NAMES",
    "SCHEME_POSITION_LONG_NAMES", "SCHEME_POSITION_NAMES", "SCHEME_RETIRED_CODES",
    "SCHEME_RETIRED_REPLACEMENT", "SCHEME_TITLES", "ENUM_OLB", "ENUM_ILB", "ENUM_DT", "ENUM_DE",
    "check_position_code", "chip_order", "detect_scheme", "detect_scheme_from_data",
    "detect_scheme_from_states", "inspect_states", "is_retired_position", "jersey_range",
    "key_ratings", "live_position_codes", "normalise_scheme", "position_code", "position_groups",
    "position_long_name", "position_name", "position_names", "rating_profile",
    "replacement_position_code", "retired_position_codes",
    "POWER_RUN_STYLES", "POWER_RUN_STYLE_THRESHOLDS", "POWER_RUN_STYLE_VALUES",
    "RATING_BYTE_ORDER", "RATING_LABELS", "RATING_MAX", "RATING_MAX_LARGE", "RATING_UI_ORDER",
    "RETAIL_BODY_SHA256", "SCRAMBLE_AGILITY_THRESHOLD", "SCRAMBLE_PRESETS", "STYLE_RATINGS",
    "THROW_STYLES", "VIRTUAL_FIELDS", "WHERE_OPERATORS",
    "SHOES", "SIG_KEY", "SLEEVES", "TURTLENECKS", "WRISTS", "YES_NO", "Allocation", "Field",
    "Player", "PlayerRecord", "RosterDocument", "RosterPoolFull", "RosterRecordError",
    "SaveContainer", "StringPool", "TeamRecord", "advance_years_pro", "apply", "apply_body",
    "copy_player", "decode_record", "edits_document", "encode_record", "encoded_size",
    "export_csv", "field_coverage", "find_block_base", "global_edit_apply", "global_edit_preview",
    "import_csv", "load_body", "load_image", "load_save", "read_edits", "read_utf16z",
    "resource_status", "restore_measurements", "save_document", "sign_save", "status",
    "validate", "validate_name", "verify_extra",
]
