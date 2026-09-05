"""7-on-7 practice content for the Basic Training playbook ``PRACTICE-pb.iff`` (outer entry 334).

The engine fields eleven per side (eleven formation slots, eleven play chains, the lineup builder
``FUN_0018a5d0`` loops 0..10 and the validator refuses an empty chain), so "seven on seven" is
built the way retail's own Basic Training drills do it: the four linemen of each side stand at the
sideline, in bounds, with the retail inert chain (``Start`` then ``Start``, the two-node chain
every tutorial defence gives its idle players), and the seven who play get real assignments.

What this module writes into a COPY of the practice book (the PLAY resource is uncompressed and
fixed-size, 0x20 wrapper + 0x13390 body, so every edit is in place; the wrapper is byte-identical):

* five personnel groups appended to the category table: ``7-ON-7 PASS 3WR`` (Kings row: TE, three
  WR, HB), ``7-ON-7 PASS 4WR`` (Flush row), ``7-ON-7 PASS 2TE`` (Ace row), ``7-ON-7 COVERAGE 3LB``
  (the 4-3 row), ``7-ON-7 COVERAGE 5DB`` (the Nickel row) -- all eleven-code rows copied from the
  retail team books, so the depth chart fills them exactly as it fills the stock sets;
* five formations (three offence, two defence) whose linemen slots sit at x = +/-25.2 yd (the
  sideline is 26.7) behind the ball / behind the line, and whose first defensive line slot is the
  **timer rusher**: a defender 7.5 yd off the ball whose Rush Lane opcode carries the retail delay
  field set to 4.0 s, so the quarterback has a four-second count before a free rusher arrives;
* nine offensive pass plays (three per set) and six coverages (shared by both defensive sets),
  every one accepted by the ported game validator; the offence keeps a real centre to snap
  (family-0 plays must contain a Snap To) so an offensive set is QB + snapper + five skill players;
* header bit 22 (``0x400000``, the flag retail puts on Take Knee / Spike Ball) on the 27 retail
  plays of the book, which is the flag ``FUN_00204930`` (the CPU play pick) excludes, so with AI
  playcalling on the CPU only calls the 7-on-7 plays; Basic Training looks its drills up by name
  and is unaffected.

Companion of :mod:`nfl2k5_seven_on_seven` (the executable side: the fifth Practice Type that loads
this book for both teams).  Retail geometry, chain shapes and zone/man operand tuples are copied
from the retail practice and team books; what is new is the parking and the 4.0 s delay, both
unverified at runtime.
"""

from __future__ import annotations

import hashlib
import importlib
import struct
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib
from .nfl2k5_formation_play_writer import (
    FormationCreateRequest,
    PlayCreateRequest,
    compile_formation_play_creations,
)
from .nfl2k5_playbook_inspector import (
    BODY_SIZE,
    CATEGORY_BASE,
    CATEGORY_CAPACITY,
    CATEGORY_SIZE,
    FORMATION_AUX_BASE,
    FORMATION_AUX_SIZE,
    FORMATION_PLAY_LINKS,
    PLAY_BASE,
    PLAY_SIZE,
    RESOURCE_HEADER_SIZE,
    STRING_BASE,
    parse_playbook_resource,
)

ROOT = Path(__file__).resolve().parents[2]
ASSET_ID = "PRACTICE"
PRACTICE_OUTER_INDEX = 334
RESOURCE_SIZE = RESOURCE_HEADER_SIZE + BODY_SIZE
RETAIL_RESOURCE_SHA256 = "56de927e6969f010dccf0e1a3d7f216bcb8010393e543769de12a794e9ccdfb9"
#: The same book after the one-pool position recode (``nfl2k5_playbook_position_recode.apply`` with its
#: defaults), which the Build tab runs BEFORE this writer whenever the EDGE/LB/interior pools are on.
#: Only the category table's defensive slot codes differ, so the 7-on-7 sets are written on top of it with
#: their own personnel groups recoded by the same rule; the result is byte-identical to recoding a 7-on-7 book.
RECODED_RESOURCE_SHA256 = "83ac912b3b44505ced3598b76cecc5ea71789e2273cb2bbd331b91d5b8d97cfb"
KNOWN_SOURCE_STATES = {RETAIL_RESOURCE_SHA256: "retail", RECODED_RESOURCE_SHA256: "recoded"}
RETAIL_FORMATIONS = 23
RETAIL_PLAYS = 27
RETAIL_CATEGORIES = 11
POOL_COUNT_WORD = 0x1083C
EMPTY_LINK = 0x1FF
LINK_GROUP = 3                     # the selection group every tutorial link in this book uses
LINK_PRESENT = 0x8000              # set on every real link word in every retail book
EMPTY_LINK = 0x7FF                 # the retail fill for an unused menu slot
AI_EXCLUDED = 0x400000             # play header bit 22: retail Take Knee / Spike Ball; FUN_00204930 skips it
YD = codec.YD_CM

PARK_X = 2300                      # 25.2 yd from the centre line; the sideline is 2438 (26.7 yd)
OFFENSE_PARK = ((PARK_X, -900), (-PARK_X, -900), (PARK_X, -1050), (-PARK_X, -1050))   # T0 T1 G0 G1
DEFENSE_PARK = ((-PARK_X, 250), (PARK_X, 250), (-PARK_X, 400))                       # slots 1, 2, 3
RUSHER_POSITION = (0, 686)         # 7.5 yd off the ball, over the centre
RUSH_DELAY_SECONDS = 4.0
RUSH_LANE = 8                      # the interior lane retail's Base rush uses for a tackle

# Personnel rows (eleven position codes, kind | ordinal << 5) copied from the ATL team book.
KINGS_ROW = bytes.fromhex("0005250607270809" "49290a")      # QB T T C G G TE0 WR0 WR2 WR1 HB0
FLUSH_ROW = bytes.fromhex("000525060727" "2969" "4909" "0a")  # QB T T C G G WR1 WR3 WR2 WR0 HB0
ACE_ROW = bytes.fromhex("000525060727" "0829" "0928" "0a")    # QB T T C G G TE0 WR1 WR0 TE1 HB0
BASE43_ROW = bytes.fromhex("2c0c2d0d2f0e0f10113212")        # DE1 DE0 DT1 DT0 OLB1 MLB0 OLB0 SS0 FS0 CB1 CB0
NICKEL_ROW = bytes.fromhex("2c0c2d0d0f0e5210113212")        # DE1 DE0 DT1 DT0 OLB0 MLB0 CB2 SS0 FS0 CB1 CB0

CATEGORIES: tuple[tuple[str, int, bytes], ...] = (
    ("7-ON-7 PASS 3WR", 0x06, KINGS_ROW),
    ("7-ON-7 PASS 4WR", 0x09, FLUSH_ROW),
    ("7-ON-7 PASS 2TE", 0x03, ACE_ROW),
    ("7-ON-7 COVERAGE 3LB", 0x0D, BASE43_ROW),
    ("7-ON-7 COVERAGE 5DB", 0x0E, NICKEL_ROW),
)

QB_UNDER_CENTER = (0, -185)
CENTER = (0, 0)
HB = (0, -632)

# (name, donor formation index in the retail practice book, category ordinal into CATEGORIES,
#  the eleven (x, z) centimetre positions, offense?)
FORMATIONS: tuple[tuple[str, int, int, tuple[tuple[int, int], ...], bool], ...] = (
    ("7-On-7 Trips", 6, 0,
     (QB_UNDER_CENTER, *OFFENSE_PARK[:2], CENTER, *OFFENSE_PARK[2:],
      (457, 0), (1371, 0), (869, -219), (-1371, 0), HB), True),          # TE0 R, WR0 R wide, WR2 R slot, WR1 L, HB
    ("7-On-7 Spread", 4, 1,
     (QB_UNDER_CENTER, *OFFENSE_PARK[:2], CENTER, *OFFENSE_PARK[2:],
      (-869, -219), (869, -219), (1371, 0), (-1371, 0), HB), True),      # WR1 L slot, WR3 R slot, WR2 R, WR0 L, HB
    ("7-On-7 Ace", 8, 2,
     (QB_UNDER_CENTER, *OFFENSE_PARK[:2], CENTER, *OFFENSE_PARK[2:],
      (-457, 0), (-1371, -219), (1371, 0), (457, 0), HB), True),         # TE0 L, WR1 L wide, WR0 R wide, TE1 R, HB
    ("7-On-7 Cover 43", 19, 3,
     (RUSHER_POSITION, *DEFENSE_PARK,
      (457, 411), (0, 457), (-457, 411), (640, 1097), (-640, 1097), (1280, 548), (-1280, 548)), False),
    ("7-On-7 Nickel", 19, 4,
     (RUSHER_POSITION, *DEFENSE_PARK,
      (366, 411), (-366, 411), (-869, 457), (640, 1097), (-640, 1097), (1280, 548), (-1280, 548)), False),
)
OFFENSE_DONOR_PLAY = 7      # "50 All Go": dropback class, family 0
ZONE_DONOR_PLAY = 11        # "Cover 3": family 1
MAN_DONOR_PLAY = 17         # "2 Man": family 1

Chain = list

# The retail inert chain (every tutorial defence's idle player): Start, then Start with TERM|ACTION.
IDLE: Chain = [lib.start(3), (0x01, [0, 0, 0, 0.1, 0.0, 0.0])]
TIMER_RUSHER: Chain = [(0x1B, [0, 0, 0.0, 0.0, 0, 0]), (0x0B, [1, RUSH_LANE, RUSH_DELAY_SECONDS])]

# Defensive opener / landmark tuples copied from the retail practice book (Cover 3, 2 Man).
DS0 = (0x1B, [0, 0, 0.0, 0.0, 0, 0])
DS_MID = (0x1B, [0, 0, 0.0, 0.0, 8, 0])
DS_CB_R = (0x1B, [0, 0, -640.08, 0.0, 0, 1])
DS_S = (0x1B, [0, 0, 0.0, -274.32, 0, 1])
DS_DEEP = (0x1B, [0, 0, 0.0, 548.64, 0, 1])
DS_MAN_LB = (0x1B, [2, 0, 0.0, 365.76, 0, 0])
DS_MAN_MLB = (0x1B, [2, 0, 0.0, 457.2, 0, 0])
DS_MAN_DB = (0x1B, [2, 0, 0.0, 91.44, 0, 0])
Z_HOOK_MID = (0x0D, [0.0, 914.4, 0, 0, 5, 0, 0])
Z_CURL_L = (0x0D, [-731.52, 731.52, 0, 0, 4, 0, 0])
Z_CURL_R = (0x0D, [731.52, 731.52, 0, 0, 4, 0, 0])
Z_FLAT_L = (0x0D, [-1280.16, 731.52, 6, 7, 6, 0, 0])
Z_FLAT_R = (0x0D, [1280.16, 731.52, 6, 7, 6, 0, 0])
Z_THIRD_R = (0x0D, [1371.6, 1645.92, 10, 9, 9, 0, 0])
Z_THIRD_L = (0x0D, [-1371.6, 1645.92, 6, 7, 10, 0, 0])
Z_THIRD_M = (0x0D, [0.0, 1645.92, 7, 9, 8, 0, 0])
Z_HALF_R = (0x0D, [1097.28, 1645.92, 10, 9, 11, 0, 0])
Z_HALF_L = (0x0D, [-1097.28, 1645.92, 7, 6, 11, 0, 0])
Z_QUARTER_R = (0x0D, [640.08, 1645.92, 10, 9, 11, 0, 0])
Z_QUARTER_L = (0x0D, [-640.08, 1645.92, 7, 6, 11, 0, 0])
MAN_LB = (0x0E, [0, 457.2, 0, 0, 0, 0, 0, 0])
MAN_DB = (0x0E, [0, 182.88, 0, 13, 0, 0, 0, 0])


def _route(name: str, depth: float | None = None) -> Chain:
    return lib.route_chain(name, depth, 0)


def _offense_play(routes: Mapping[int, Chain]) -> tuple[Chain, ...]:
    """Eleven chains: QB dropback, parked linemen idle, the centre snaps and pass-sets, skill routes."""

    chains: list[Chain] = [
        lib.qb_pass_chain(False, 5.0),      # slot 0 QB: take the snap, five-yard drop, throw
        IDLE, IDLE,                          # slots 1, 2: tackles parked at the sideline
        lib.center_chain(0, "pass", False),  # slot 3 C: snap to the QB, pass set
        IDLE, IDLE,                          # slots 4, 5: guards parked
    ]
    for slot in range(6, 11):
        chains.append(routes[slot])
    return tuple(chains)


def _defense_play(cover: Mapping[int, Chain]) -> tuple[Chain, ...]:
    chains: list[Chain] = [TIMER_RUSHER, IDLE, IDLE, IDLE]
    for slot in range(4, 11):
        chains.append(cover[slot])
    return tuple(chains)


# (name, donor play, formation ordinal into FORMATIONS or None for "every defensive set", chains)
def plays() -> list[tuple[str, int, int | None, tuple[Chain, ...]]]:
    out: list[tuple[str, int, int | None, tuple[Chain, ...]]] = []
    # --- 7-On-7 Trips: 6 TE0 right tight, 7 WR0 right wide, 8 WR2 right slot, 9 WR1 left wide, 10 HB
    out.append(("7v7 Trips Flood", OFFENSE_DONOR_PLAY, 0, _offense_play(
        {6: _route("Flat", 5), 7: _route("Go", 22), 8: _route("Out", 12), 9: _route("Post", 12), 10: _route("Drag", 8)})))
    out.append(("7v7 Trips Mesh", OFFENSE_DONOR_PLAY, 0, _offense_play(
        {6: _route("Curl", 8), 7: _route("Comeback", 14), 8: _route("Drag", 10), 9: _route("Drag", 8), 10: _route("Wheel", 15)})))
    out.append(("7v7 Trips Verts", OFFENSE_DONOR_PLAY, 0, _offense_play(
        {6: _route("Go", 18), 7: _route("Go", 25), 8: _route("Go", 20), 9: _route("Go", 25), 10: _route("Hitch", 5)})))
    # --- 7-On-7 Spread: 6 WR1 left slot, 7 WR3 right slot, 8 WR2 right wide, 9 WR0 left wide, 10 HB
    out.append(("7v7 Spread Slants", OFFENSE_DONOR_PLAY, 1, _offense_play(
        {6: _route("Slant", 8), 7: _route("Slant", 8), 8: _route("Slant", 8), 9: _route("Slant", 8), 10: _route("Flat", 6)})))
    out.append(("7v7 Spread Curls", OFFENSE_DONOR_PLAY, 1, _offense_play(
        {6: _route("Hitch", 6), 7: _route("Hitch", 6), 8: _route("Curl", 12), 9: _route("Curl", 12), 10: _route("Drag", 8)})))
    out.append(("7v7 Spread Four Verts", OFFENSE_DONOR_PLAY, 1, _offense_play(
        {6: _route("Go", 20), 7: _route("Go", 20), 8: _route("Go", 25), 9: _route("Go", 25), 10: _route("Flat", 6)})))
    # --- 7-On-7 Ace: 6 TE0 left tight, 7 WR1 left wide, 8 WR0 right wide, 9 TE1 right tight, 10 HB
    out.append(("7v7 Ace Smash", OFFENSE_DONOR_PLAY, 2, _offense_play(
        {6: _route("Corner", 12), 7: _route("Hitch", 6), 8: _route("Hitch", 6), 9: _route("Corner", 12), 10: _route("Drag", 8)})))
    out.append(("7v7 Ace Stick", OFFENSE_DONOR_PLAY, 2, _offense_play(
        {6: _route("Drag", 8), 7: _route("Comeback", 14), 8: _route("Go", 20), 9: _route("Stick", 6), 10: _route("Flat", 6)})))
    out.append(("7v7 Ace Double Post", OFFENSE_DONOR_PLAY, 2, _offense_play(
        {6: _route("Out", 8), 7: _route("Post", 12), 8: _route("Post", 12), 9: _route("Curl", 8), 10: _route("Wheel", 15)})))
    # --- coverages (slots: 4 right LB, 5 middle LB, 6 left LB / nickel back, 7 SS, 8 FS, 9 right CB, 10 left CB)
    out.append(("7v7 Cover 2", ZONE_DONOR_PLAY, None, _defense_play(
        {4: [DS0, Z_CURL_R], 5: [DS_MID, Z_HOOK_MID], 6: [DS0, Z_CURL_L], 7: [DS_CB_R, Z_HALF_R], 8: [DS_S, Z_HALF_L],
         9: [DS_S, Z_FLAT_R], 10: [DS_S, Z_FLAT_L]})))
    out.append(("7v7 Cover 3", ZONE_DONOR_PLAY, None, _defense_play(
        {4: [DS0, Z_CURL_R], 5: [DS_MID, Z_HOOK_MID], 6: [DS0, Z_CURL_L], 7: [DS_S, Z_FLAT_R], 8: [DS_CB_R, Z_THIRD_M],
         9: [DS_DEEP, Z_THIRD_R], 10: [DS_DEEP, Z_THIRD_L]})))
    out.append(("7v7 Cover 4", ZONE_DONOR_PLAY, None, _defense_play(
        {4: [DS0, Z_CURL_R], 5: [DS_MID, Z_HOOK_MID], 6: [DS0, Z_CURL_L], 7: [DS_S, Z_QUARTER_R], 8: [DS_S, Z_QUARTER_L],
         9: [DS_DEEP, Z_THIRD_R], 10: [DS_DEEP, Z_THIRD_L]})))
    out.append(("7v7 Man Free", MAN_DONOR_PLAY, None, _defense_play(
        {4: [DS_MAN_LB, MAN_LB], 5: [DS_MID, Z_HOOK_MID], 6: [DS_MAN_LB, MAN_LB], 7: [DS_MAN_DB, MAN_DB],
         8: [DS_CB_R, Z_THIRD_M], 9: [DS_MAN_DB, MAN_DB], 10: [DS_MAN_DB, MAN_DB]})))
    out.append(("7v7 2 Man", MAN_DONOR_PLAY, None, _defense_play(
        {4: [DS_MAN_LB, MAN_LB], 5: [DS_MAN_MLB, MAN_LB], 6: [DS_MAN_LB, MAN_LB], 7: [DS_CB_R, Z_HALF_R],
         8: [DS_S, Z_HALF_L], 9: [DS_MAN_DB, MAN_DB], 10: [DS_MAN_DB, MAN_DB]})))
    out.append(("7v7 Tampa 2", ZONE_DONOR_PLAY, None, _defense_play(
        {4: [DS0, Z_CURL_R], 5: [DS_CB_R, Z_THIRD_M], 6: [DS0, Z_CURL_L], 7: [DS_CB_R, Z_HALF_R], 8: [DS_S, Z_HALF_L],
         9: [DS_S, Z_FLAT_R], 10: [DS_S, Z_FLAT_L]})))
    return out


class SevenOnSevenBookError(ValueError):
    """The 7-on-7 content cannot be written into this practice book."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SevenOnSevenBookError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _string_end(body: bytes, field: int) -> int:
    target = field - 1 + struct.unpack_from("<i", body, field)[0]
    _require(STRING_BASE <= target < len(body) and not target & 1, "name pool pointer is invalid")
    cursor = target
    while cursor + 2 <= len(body):
        if body[cursor: cursor + 2] == b"\0\0":
            return cursor + 2
        cursor += 2
    raise SevenOnSevenBookError("name pool string is not terminated")


def _pool_end(body: bytes) -> int:
    book = parse_playbook_resource(_wrap(body), asset_id=ASSET_ID)
    ends = [_string_end(body, 0x30)]
    ends += [_string_end(body, 0x134 + i * 0xB4) for i in range(len(book.formations))]
    ends += [_string_end(body, PLAY_BASE + j * PLAY_SIZE) for j in range(len(book.plays))]
    ends += [_string_end(body, CATEGORY_BASE + k * CATEGORY_SIZE) for k in range(len(book.categories))]
    return max(ends)


def _wrap(body: bytes) -> bytes:
    return b"PLAY" + struct.pack("<7I", BODY_SIZE, BODY_SIZE, 0, 0, 0, 0, 0) + body


def _recode_row(formation_type: int, row: bytes) -> bytes:
    """One personnel group's eleven slot codes after the one-pool position recode (its own rule)."""

    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    recode = importlib.import_module("nfl2k5_playbook_position_recode")
    new, _rule = recode.recode_codes(list(row), formation_type)
    _require(len(new) == len(row), "the position recode changed the slot count")
    return bytes(new)


def _add_categories(raw: bytes) -> tuple[bytes, list[int]]:
    """Append the five 7-on-7 personnel groups (name in the pool tail, id byte, eleven codes)."""

    body = bytearray(raw[RESOURCE_HEADER_SIZE:])
    count = struct.unpack_from("<I", body, 0x3C)[0]
    _require(count + len(CATEGORIES) <= CATEGORY_CAPACITY, "the practice book has no room for the 7-on-7 personnel groups")
    pool_end = _pool_end(bytes(body))
    _require(not any(body[pool_end:]), "the practice book's name pool tail is not zero padding")
    _require(struct.unpack_from("<I", body, POOL_COUNT_WORD)[0] == (pool_end - STRING_BASE) // 2,
             "the practice book's pool count word does not match its name pool")
    cursor = pool_end
    indices = []
    for k, (name, id_byte, row) in enumerate(CATEGORIES):
        index = count + k
        record = CATEGORY_BASE + index * CATEGORY_SIZE
        _require(not any(body[record: record + CATEGORY_SIZE]), f"category slot {index} is not free")
        encoded = name.encode("utf-16le") + b"\0\0"
        _require(cursor + len(encoded) <= BODY_SIZE, "the name pool is full")
        body[cursor: cursor + len(encoded)] = encoded
        struct.pack_into("<i", body, record, cursor - record + 1)
        body[record + 4] = id_byte
        body[record + 5: record + 16] = row
        cursor += len(encoded)
        indices.append(index)
    struct.pack_into("<I", body, 0x3C, count + len(CATEGORIES))
    struct.pack_into("<I", body, POOL_COUNT_WORD, (cursor - STRING_BASE) // 2)
    out = raw[:RESOURCE_HEADER_SIZE] + bytes(body)
    parsed = parse_playbook_resource(out, asset_id=ASSET_ID)
    _require([c.name for c in parsed.categories[count:]] == [name for name, _i, _r in CATEGORIES], "category names did not survive reparse")
    return out, indices


def _requests(category_indices: Sequence[int], donor_flags: Mapping[int, int]) -> tuple[list[FormationCreateRequest], list[PlayCreateRequest]]:
    formations = [
        FormationCreateRequest(ASSET_ID, donor, custom_name=name, slot_positions=tuple(positions),
                               category_index=category_indices[cat], category_positions=tuple(CATEGORIES[cat][2]))
        for name, donor, cat, positions, _offense in FORMATIONS
    ]
    play_requests = [
        PlayCreateRequest(ASSET_ID, donor, custom_name=name,
                          assignments=tuple(tuple((op, tuple(vals)) for op, vals in chain) for chain in chains),
                          play_flags=donor_flags[donor])
        for name, donor, _formation, chains in plays()
    ]
    return formations, play_requests


def _write_links(body: bytearray, formation_index: int, play_indices: Sequence[int]) -> None:
    aux = FORMATION_AUX_BASE + formation_index * FORMATION_AUX_SIZE
    _require(len(play_indices) <= FORMATION_PLAY_LINKS, "too many plays for one formation menu")
    # Retail encoding, checked across all 16,065 links of the 37 shipped books: bit 15 set on every real
    # link, the selection group in bits 9-10, the play index in bits 0-8, 0x7FF for an empty slot. A word
    # without bit 15 is not a play link to the game: the defensive play-call then walked a personnel-group
    # record as if it were a play and faulted (witnessed 2026-09-03, EIP 0x1A8E3A, address 0x12321110).
    words = [LINK_PRESENT | (LINK_GROUP << 9) | p for p in play_indices] + [EMPTY_LINK] * (FORMATION_PLAY_LINKS - len(play_indices))
    struct.pack_into(f"<{FORMATION_PLAY_LINKS}H", body, aux, *words)


def build_replacement(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    """The 7-on-7 practice book built from the retail resource; returns (resource, report)."""

    _require(len(raw) == RESOURCE_SIZE and raw[:4] == b"PLAY", "not a fixed NFL 2K5 PLAY resource")
    source_state = KNOWN_SOURCE_STATES.get(_sha256(raw))
    _require(source_state is not None, "this practice book is neither the retail PRACTICE-pb.iff nor its one-pool recode")
    with_categories, category_indices = _add_categories(raw)
    source = parse_playbook_resource(with_categories, asset_id=ASSET_ID)
    donor_flags = {p.index: p.flags_or_id for p in source.plays}
    formation_requests, play_requests = _requests(category_indices, donor_flags)
    compiled = compile_formation_play_creations(
        with_categories, formation_requests, play_requests, _seven_on_seven_source=raw)
    body = bytearray(compiled.replacement[RESOURCE_HEADER_SIZE:])
    new_formations = list(compiled.new_formation_indices)
    new_plays = list(compiled.new_play_indices)
    # Menu links: each offensive set lists its own three plays; both defensive sets list all six.
    defensive = [new_plays[k] for k, (_n, _d, f, _c) in enumerate(plays()) if f is None]
    for ordinal, (_name, _donor, _cat, _positions, offense) in enumerate(FORMATIONS):
        listed = [new_plays[k] for k, (_n, _d, f, _c) in enumerate(plays()) if f == ordinal] if offense else defensive
        _write_links(body, new_formations[ordinal], listed)
    # The CPU never calls the retail (eleven-man) practice plays once they carry bit 22.
    for play_index in range(RETAIL_PLAYS):
        field = PLAY_BASE + play_index * PLAY_SIZE + 4
        struct.pack_into("<I", body, field, struct.unpack_from("<I", body, field)[0] | AI_EXCLUDED)
    if source_state == "recoded":
        for k, (_name, id_byte, row) in enumerate(CATEGORIES):
            record = CATEGORY_BASE + category_indices[k] * CATEGORY_SIZE
            _require(body[record + 4] == id_byte and bytes(body[record + 5: record + 16]) == row,
                     "the personnel group rows moved during compilation")
            body[record + 5: record + 16] = _recode_row(id_byte, row)
    result = raw[:RESOURCE_HEADER_SIZE] + bytes(body)
    report = verify(result)
    report.update({"source_state": source_state, "source_sha256": _sha256(raw), "replacement_sha256": _sha256(result),
                   "new_formation_indices": new_formations, "new_play_indices": new_plays,
                   "category_indices": list(category_indices), "new_node_count": compiled.report["new_node_count"],
                   "changed_byte_count": sum(1 for a, b in zip(raw, result) if a != b)})
    return result, report


def verify(resource: bytes) -> dict[str, Any]:
    """Prove the 7-on-7 book: capacity, eleven slots with four parked idle linemen, every play valid."""

    _require(len(resource) == RESOURCE_SIZE, "resource size changed")
    body = resource[RESOURCE_HEADER_SIZE:]
    book = parse_playbook_resource(resource, asset_id=ASSET_ID)
    names = {f.name: f.index for f in book.formations}
    play_names = {p.name: p.index for p in book.plays}
    for name, _d, _c, _p, _o in FORMATIONS:
        _require(name in names, f"formation {name!r} missing")
    for name, _d, _f, _c in plays():
        _require(name in play_names, f"play {name!r} missing")
    for name, _i, _r in CATEGORIES:
        _require(name in {c.name for c in book.categories}, f"personnel group {name!r} missing")
    invalid = []
    for play in book.plays:
        flags, chains = lib.play_chains(body, play.index)
        error = codec.validate_play(flags, chains)
        if error:
            invalid.append((play.name, error))
    _require(not invalid, "plays the game would reject: " + "; ".join(f"{n}: {e}" for n, e in invalid))
    ai_excluded = sum(1 for play in book.plays[:RETAIL_PLAYS] if play.flags_or_id & AI_EXCLUDED)
    _require(ai_excluded == RETAIL_PLAYS, "not every retail practice play carries the AI-excluded flag")
    _require(not any(play.flags_or_id & AI_EXCLUDED for play in book.plays[RETAIL_PLAYS:]), "a 7-on-7 play is AI-excluded")
    formations_report = []
    for name, _donor, cat, positions, offense in FORMATIONS:
        index = names[name]
        record = lib.formation_record(body, index)
        parked = [s for s, slot in enumerate(record.slots) if abs(slot.x[0]) == PARK_X]
        expected = [1, 2, 4, 5] if offense else [1, 2, 3]
        _require(parked == expected, f"{name}: parked slots {parked}, expected {expected}")
        _require(all(abs(slot.x[0]) < 2438 for slot in record.slots), f"{name}: a slot is out of bounds")
        _require([(slot.x[0], slot.z[0]) for slot in record.slots] == [tuple(p) for p in positions], f"{name}: positions differ")
        _require(lib.formation_category(body, index) == book.categories[RETAIL_CATEGORIES + cat].index, f"{name}: personnel group differs")
        links = [link.play_index for link in book.formations[index].play_links]
        _require(links, f"{name}: no plays listed")
        aux = FORMATION_AUX_BASE + index * FORMATION_AUX_SIZE
        for word in struct.unpack_from(f"<{FORMATION_PLAY_LINKS}H", body, aux):
            _require(word == EMPTY_LINK or (word & LINK_PRESENT and (word & 0x1FF) < len(book.plays)),
                     f"{name}: menu link {word:#06x} is not a retail-shaped play link")
        for play_index in links:
            _flags, chains = lib.play_chains(body, play_index)
            for slot in expected:
                ops = [n[0] for n in chains[slot][1]]
                _require(ops == [0x01, 0x01], f"{name}: slot {slot} of play {play_index} is not the idle chain")
            if not offense:
                ops = [n[0] for n in chains[0][1]]
                _require(ops == [0x1B, 0x0B], f"{name}: slot 0 of play {play_index} is not the timer rusher")
                delay = codec.decode_operands(0x0B, struct.unpack_from("<I", chains[0][1][1], 4)[0])[2]
                _require(abs(delay - RUSH_DELAY_SECONDS) < 0.05, f"{name}: rusher delay is {delay}")
        formations_report.append({"name": name, "index": index, "plays": links, "parked_slots": parked,
                                  "category": book.categories[RETAIL_CATEGORIES + cat].name})
    node_count = struct.unpack_from("<I", body, 0x40)[0]
    return {"formations": formations_report, "formation_count": len(book.formations), "play_count": len(book.plays),
            "category_count": len(book.categories), "node_count": node_count,
            "capacity": {"formations": 50, "plays": 270, "categories": CATEGORY_CAPACITY, "nodes": (STRING_BASE - 0x9ADC) // 8},
            "wrapper": resource[:RESOURCE_HEADER_SIZE].hex(), "ai_excluded_retail_plays": ai_excluded}


def resource_status(resource: bytes) -> str:
    """retail | recoded | applied | foreign for one PRACTICE-pb.iff resource (``recoded`` = the retail
    book after the one-pool position recode, a source this writer builds on just like retail)."""

    if len(resource) != RESOURCE_SIZE or resource[:4] != b"PLAY":
        return "foreign"
    known = KNOWN_SOURCE_STATES.get(_sha256(resource))
    if known is not None:
        return known
    try:
        verify(resource)
    except Exception:  # noqa: BLE001
        return "foreign"
    return "applied"


# ---------------------------------------------------------------------------------------------
# Disc images / loose pack folders (the outer archive reader/writer the position recode uses)

def _outer_image():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return importlib.import_module("nfl2k5_playbook_position_recode").OuterImage


def _entry(archive) -> Any:
    entries = archive.entries
    _require(len(entries) > PRACTICE_OUTER_INDEX, "the archive has no outer entry 334")
    entry = entries[PRACTICE_OUTER_INDEX]
    _require(entry.size == RESOURCE_SIZE, f"outer entry 334 is 0x{entry.size:x} bytes, not the practice book")
    return entry


def status(path: Path | str) -> str:
    with _outer_image()(path) as archive:
        entry = _entry(archive)
        return resource_status(archive.read(entry.virtual_offset, entry.size))


def apply(path: Path | str, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Write the 7-on-7 book into the practice book of the disc image at ``path`` (a COPY)."""

    say = progress or (lambda _m: None)
    with _outer_image()(path, writable=True) as archive:
        entry = _entry(archive)
        before = archive.read(entry.virtual_offset, entry.size)
        state = resource_status(before)
        if state == "applied":
            return {"status": "applied", "already_applied": True, "outer_index": PRACTICE_OUTER_INDEX}
        _require(state in ("retail", "recoded"), f"the practice book is {state}, not retail; refusing")
        say("Building the 7-on-7 practice book")
        replacement, report = build_replacement(before)
        _require(replacement[:RESOURCE_HEADER_SIZE] == before[:RESOURCE_HEADER_SIZE], "the resource wrapper changed")
        say("Writing PRACTICE-pb.iff")
        count = archive.write(entry.virtual_offset, replacement)
        _require(count == len(replacement), "short write of the practice book")
        check = archive.read(entry.virtual_offset, entry.size)
        _require(check == replacement, "read-back of the practice book differs")
    return {"status": "applied", "outer_index": PRACTICE_OUTER_INDEX, "virtual_offset": f"0x{entry.virtual_offset:x}",
            **{k: v for k, v in report.items() if k != "wrapper"}}


__all__ = ["ASSET_ID", "CATEGORIES", "FORMATIONS", "PRACTICE_OUTER_INDEX", "RECODED_RESOURCE_SHA256", "RETAIL_RESOURCE_SHA256", "RESOURCE_SIZE",
           "RUSH_DELAY_SECONDS", "SevenOnSevenBookError", "apply", "build_replacement", "plays", "resource_status",
           "status", "verify"]
