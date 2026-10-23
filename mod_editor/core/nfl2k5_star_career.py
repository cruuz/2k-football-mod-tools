"""Rookie stars, and stars earned and lost over a career (job b778-st2). EXPERIMENTAL / UNWITNESSED.

Noah (10/23 ~01:00): "Someone mentioned that rookies never have star abilities ... we should give some
rookies stars, like some of the top ones ... every draft has one or two gems later ... players should be
able to gain or lose that star ability as they progress".  The right-stick moves stay star-only (Noah:
"Right stick moves cannot be for everyone ... The right stick moves have to be limited to the stars"); this
owner never changes ``nfl2k5_abilities_runtime``'s ``abilities_right_stick_stars_only`` or
``abilities_charge_stars_only``.  Rookies get the moves by being stars.

Star status is the roster record ``+0x53`` bit 0 (written by ``nfl2k5_player_tags``, drawn by
``nfl2k5_player_star``) plus the ability tier at ``+0x53`` bits 6..7 (``Unranked, Star, Superstar,
X-Factor``).  Bits 1..5 (the stored move flags and the Guardian cap) are never touched.

1. Draft class (hooks 0x2BE940 / 0x2BE923 / 0x2BE937).
   ``FUN_002BE940(count)`` sets ``[0xE41CDC]`` and jumps into ``FUN_002BE900``, whose loop allocates each
   prospect (0x2BD390) and calls the generator ``FUN_002BE6F0``.  The owner remembers every generated
   record, then ranks the class with the draft AI's own key without team need or jitter:
   ``(overall - class mean at his position) * positional value``.  The 3..5 best get Star (one class in
   eight makes its best prospect a Superstar).  Then 1..2 "gems": a prospect projected in rounds 2-5
   (rank 33..160) whose hidden development archetype (record +0x24 bits 4..7) has top-decile growth in
   the game's own curve tables (``nfl2k5_progression.PROFILES_VA`` / ``CURVES_VA``; pg1's reshaped
   tables when that option is on).  Gems get Star.

   NFL rate shape: rookies selected to the Pro Bowl, from the Wikipedia Pro Bowl roster tables (rookies
   are printed in italics at the bottom of each page): 2021 season 6 (2022 Pro Bowl), 2022 season 3
   (2023), 2023 season 8 (2024), 2024 season 6 (2025).  That is 3..8 a year; the 3..5 top prospects plus
   1..2 gems reproduce it inside the game's 380-prospect class while keeping the top of the draft the
   place where most stars come from.  Superstars are much rarer in the NFL (about one rookie All-Pro
   every year or two), hence the 1-in-8 coin.

2. Earned and lost stars (hook 0x24857A, before the Preseason aging loop).
   The aging loop 0x24857F..0x2485D6 walks ``[0xB72918]`` {count, base} and calls the game's aging
   routine for every allocated player; the form routine follows it.  The owner runs *before* aging, when
   the season's stats are final, and evaluates every NFL player (record +0x08 bit 2) older than a rookie
   (years pro > 1):
     score = the game's own overall (0x246D80) + a season production bonus (-3..+5 from FUN_0014EF20:
             QB passing yards + 20*TD - 45*INT; RB rushing yards; WR/TE/FB receiving yards; CB
             interceptions; S/LB tackles; DT/DE sacks; nothing for the line or kickers).
     gain   score >= 90 (and raise the tier: 93 Superstar, 97 X-Factor)
     lose   score < 85 after at least 8 games; the star bit clears, the tier stays (so a return is cheap)
     keep   85..89 and every player with a short/injured season: the hysteresis band
     veteran QB (years pro > 4) keeps his star until his score falls under 75, pg1's "no loss after one
            down year unless young" rule; young QBs (years pro <= 4) lose normally.
   The gain/lose band is calibrated against the released v0.6.1 roster: 250 tagged players, 241 of them
   on an NFL club, become about 250-260 after one pass (the 85..89 band keeps most of today's stars and
   the 90+ non-stars join).  The total therefore stays near today's and cannot run away with age.

XBE bytes: code 2,080 (1,456 code + 608 constant-table bytes), data 4,096, read-only 0.  The owner is a late allocator owner
(``nfl2k5_xbe_space.LATE_OWNERS``) and is meant to be placed after pi1's ``nfl2k5_practice_injuries`` at
integration.  The data allocation holds the class pointers/scores, position sums, the 17 positional
values, the production thresholds, the archetype potential table and the constants.  Nothing is saved;
the changes live in the player records the franchise save already carries, so old saves load unchanged.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_star_career_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_star_career"
UI_LABEL = "Rookie stars and stars earned or lost over a career"
BUILD_CAPTION = "Rookie stars and career stars"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. Draft classes give a star ability to their 3-5 best prospects and to "
             "1-2 later-round gems (a top development archetype), and every offseason players earn a star for a "
             "top-tier overall/production season or lose it after a down year, with a hysteresis band and the "
             "veteran-quarterback rule. Right-stick moves stay star-only. The league's star count stays near its "
             "current size. Disc images only; not yet tested in a long franchise.")
EVIDENCE = "EXPERIMENTAL"

IMAGE_BASE = 0x10000
CODE_SIZE = 0x820
DATA_SIZE = 4096
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))

# The retail top prospects the class pass ranks with (QB..DE, the retail position byte order).
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
# nfl2k5_draft_ai.VALUE * 100: the CPU draft's positional value (an NFL first-round share around 1.0).
VALUE = (115, 30, 30, 108, 108, 95, 95, 92, 60, 95, 100, 93, 88, 92, 112, 100, 112)
# Season production field (record history field id, see nfl2k5_career_stats.FIELDS), 0xFF = no bonus.
FIELD = (0xFF, 0xFF, 0xFF, 13, 10, 18, 18, 2, 13, 13, 18, 18, 0xFF, 0xFF, 0xFF, 19, 19)
THI = (0, 0, 0, 1400, 6, 120, 120, 1500, 500, 1100, 140, 140, 0, 0, 0, 12, 14)
TMID = (0, 0, 0, 1000, 4, 90, 90, 1000, 300, 800, 100, 100, 0, 0, 0, 8, 9)
TLO = (0, 0, 0, 500, 1, 50, 50, 500, 100, 400, 60, 60, 0, 0, 0, 3, 4)

GAIN = 90
LOSE = 85
VETERAN_QB_FLOOR = 75
TIER_X = 97
TIER_SUPERSTAR = 93
MIN_GAMES = 8
GEM_MIN_RANK = 33
GEM_MAX_RANK = 160
GEM_POTENTIAL = 70
TIER_LIMITS = (0, 2, 4, 7)

# The retail spans the owner calls or leaves untouched around its hooks (GUARDS below pins these bytes).
RETAIL_CLASS_START = bytes.fromhex("890ddc1ce400e9b5ffffff")
RETAIL_CLASS_TAIL = bytes.fromhex("5f5e5d5b83c408c3")
RETAIL_CLASS_FINISH = bytes.fromhex("59c3909090")
RETAIL_OFFSEASON = bytes.fromhex("a11829b700")
HOOKS = (
    ("class_start", 0x2BE940, RETAIL_CLASS_START, 11),
    # The generator epilogue, not its call: MyCareer replaces the call at 0x2BE923.
    ("class_tail", 0x2BE8DB, RETAIL_CLASS_TAIL, 8),
    ("class_finish", 0x2BE937, RETAIL_CLASS_FINISH, 5),
    ("offseason", 0x24857A, RETAIL_OFFSEASON, 5),
)
SYMBOLS = {
    "retail_generator": 0x2BE6F0,
    "class_loop": 0x2BE900,
    "overall_fn": 0x246D80,
    "stat_fn": 0x14EF20,
    "rand_fn": 0x48B50,
    "allocated_fn": 0x2BD380,
    "class_counter": 0xE41CDC,
    "player_pool": 0xB72918,
}
# SHA-256 of the dependency spans the hooks do not replace.  The generator's interior is deliberately
# not pinned: prospect names hooks 0x2BE7B8 and season length rewrites 0x2BE808/0x2BE817.
GUARDS = (
    (0x2BE6F0, 20, "b14c20e5dea806a99cd94b329df5f05ef40b1577e958418de0fc88fc8d2a826d"),  # placeholder
    (0x2BE900, 35, "29a610dd1e16ad826eec56c5cdea8281a94b67a34f9f60b0ebb36bc0ce5145f1"),   # loop head
    (0x2BE928, 15, "f212eea05ddca177ee824f86430caf8c27751d447629382160aca173913317a3"),   # loop tail
    (0x2BE93C, 4, "e61d6a793b42951d4e466a18683567c9011cd840b03559c0cc9e94c761995098"),    # loop pad
    (0x246D80, 96, "78279642603bb474feae406bb2efc059fb31ef6db31f449963609e63876af4f5"),   # overall
    (0x14EF20, 144, "1739beaa79181bf8f4087e66e1c43a09fea0b1c40f710317b5d42619be0f6a61"),  # stat getter
    (0x48B50, 64, "ba8b0459e82e7fcf22e40ac6db64b32c2ec5f4c6571c574d6298ecf73dce0e90"),    # rand
    (0x2BD380, 64, "2f3cf16029154783ab52d244e43b22b68fde0cd7810be3680286800e94a8f9e7"),   # allocated
    (0x24857F, 87, "0c71817a7917e6a7fe30ef9f4a9972dde0354bc7a4000f49756a5625127ffb5f"),   # aging loop
)

# Mutable data allocation offsets (must match tools/b77/st2_star_career.S).
PTRS, SCORES, SUM, SCOUNT, MEAN = 0x000, 0x640, 0xCC0, 0xD04, 0xD48
C_CLASS_COUNT, C_SCRATCH, C_SCRATCH2, C_SCRATCH3 = 0xD8C, 0xD90, 0xD94, 0xD98
C_BESTIDX, C_BESTPOT, C_BESTSCORE, C_CANDSCORE = 0xD9C, 0xDA0, 0xDA4, 0xDA8
C_REC, C_POS, C_YEARS, C_OV, C_GAMES, C_SCORE = 0xDAC, 0xDB0, 0xDB4, 0xDB8, 0xDBC, 0xDC0
# Constant tables live after the code in the same RX allocation.
K_POT, K_VALUE, K_FIELD, K_THI, K_TMID, K_TLO = 0x600, 0x710, 0x740, 0x760, 0x790, 0x7C0
K_HUNDRED, K_CONST, K_CONST2, K_CONST3, K_LIMITS = 0x7E8, 0x7F0, 0x800, 0x810, 0x814

# nfl2k5_progression's retail tables (a read-only dependency: the potential table is read from the payload).
PROFILES_VA, PROFILES_SIZE = 0x4F27B0, 162 * 16
CURVES_VA, CURVES_SIZE = 0x4F31D0, 0x4F4CB0 - 0x4F31D0
CURVE_LEN = 21
TABLE_OFFSETS = (0x0, 0x378, 0x6D8, 0x880, 0x9A8, 0xAF8, 0xE30, 0x1110, 0x1488, 0x1800)


class StarCareerError(ValueError):
    """A foreign executable, a missing allocation or an incomplete installation."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StarCareerError(message)


def _s8(value: int) -> int:
    return value - 256 if value > 127 else value


def _offset(payload: bytes, va: int, size: int) -> int:
    image = XbeImage(payload)
    return image.offset(va, size)


def _rel(va: int, next_va: int) -> bytes:
    displacement = va - next_va
    _require(-(1 << 31) <= displacement < (1 << 31), "relative branch out of range")
    return struct.pack("<i", displacement)


def sites(labels: Mapping[str, int]) -> list[tuple[str, int, bytes]]:
    """The complete declared replacement spans, including the retail padding they overwrite."""
    after = {
        "class_start": b"\xe9" + _rel(labels["class_start"], HOOKS[0][1] + 5) + b"\x90" * 6,
        "class_tail": b"\xe9" + _rel(labels["class_tail"], HOOKS[1][1] + 5) + b"\x90" * 3,
        "class_finish": b"\xe9" + _rel(labels["class_finish"], HOOKS[2][1] + 5),
        "offseason": b"\xe8" + _rel(labels["offseason"], HOOKS[3][1] + 5),
    }
    return [(name, va, after[name]) for name, va, _before, _size in HOOKS]


def potential_table(payload: bytes) -> bytes:
    """17*16 development potential (0..255) read from the payload's own archetype and curve tables.

    row i of the 162-row table is {position, 0, 0, 0, profile, sub, 10 curve indices}; the ten curve
    tables start at ``TABLE_OFFSETS`` from CURVES_VA.  Potential is the sum over families of
    curve[8] - curve[1] (the growth from rookie year to year eight), clamped to 0..255.
    """
    image = XbeImage(payload)
    profiles = image.read(PROFILES_VA, PROFILES_SIZE)
    curves = image.read(CURVES_VA, CURVES_SIZE)
    out = bytearray(17 * 16)
    for row in range(162):
        base = row * 16
        position, profile, sub = profiles[base], profiles[base + 4], profiles[base + 5]
        if position >= 17 or profile > 1 or sub > 7:
            continue
        total = 0
        for family in range(10):
            index = profiles[base + 6 + family]
            at = TABLE_OFFSETS[family] + index * CURVE_LEN
            if at + CURVE_LEN > len(curves):
                continue
            total += _s8(curves[at + 8]) - _s8(curves[at + 1])
        out[position * 16 + profile * 8 + sub] = max(0, min(255, total))
    return bytes(out)


def tables_for(payload: bytes) -> bytes:
    """The constant tables at the tail of the code allocation (potential read from this payload)."""
    buf = bytearray(b"\xcc" * CODE_SIZE)
    buf[K_POT:K_POT + 17 * 16] = potential_table(payload)
    struct.pack_into("<17H", buf, K_VALUE, *VALUE)
    buf[K_FIELD:K_FIELD + 17] = bytes(FIELD)
    struct.pack_into("<17H", buf, K_THI, *THI)
    struct.pack_into("<17H", buf, K_TMID, *TMID)
    struct.pack_into("<17H", buf, K_TLO, *TLO)
    struct.pack_into("<f", buf, K_HUNDRED, 100.0)
    struct.pack_into("<4i", buf, K_CONST, GAIN, LOSE, TIER_X, TIER_SUPERSTAR)
    struct.pack_into("<4i", buf, K_CONST2, MIN_GAMES, GEM_MIN_RANK, GEM_MAX_RANK, GEM_POTENTIAL)
    struct.pack_into("<i", buf, K_CONST3, VETERAN_QB_FLOOR)
    buf[K_LIMITS:K_LIMITS + 4] = bytes(TIER_LIMITS)
    return bytes(buf)


def data_for(payload: bytes) -> bytes:
    """The owner's writable data allocation: zero initialised, written only at runtime."""
    return bytes(DATA_SIZE)


def code_for(payload: bytes, code_va: int, data_va: int) -> tuple[bytes, dict[str, int]]:
    """The relocated owner code, its constant tables and its label VAs."""
    blob = bytearray(assembly.CODE)
    symbols = {"code": code_va, "code_base": code_va, "data_base": data_va, **SYMBOLS}
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", blob, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", blob, offset, target & 0xFFFFFFFF)
    _require(len(blob) <= K_POT, "the star-career code outgrew its table offset")
    blob = blob.ljust(CODE_SIZE, b"\xcc")
    tables = tables_for(payload)
    blob[K_POT:CODE_SIZE] = tables[K_POT:CODE_SIZE]
    return bytes(blob), {name: code_va + offset for name, offset in assembly.LABELS.items()}


def _owned(payload: bytes) -> tuple[Mapping[str, object], Mapping[str, object]] | None:
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    if not rows:
        return None
    code = [a for a in rows if a["kind"] == "code"]
    data = [a for a in rows if a["kind"] == "data"]
    _require(len(code) == 1 and len(data) == 1 and len(rows) == 2
             and code[0]["size"] == CODE_SIZE and data[0]["size"] == DATA_SIZE,
             "foreign star-career allocation")
    return code[0], data[0]


def _guard_state(payload: bytes) -> bool:
    image = XbeImage(payload)
    return all(hashlib.sha256(image.read(va, size)).hexdigest() == digest for va, size, digest in GUARDS)


def _site_state(payload: bytes) -> str:
    image = XbeImage(payload)
    states = set()
    for name, va, before, size in HOOKS:
        text = image.read(va, size)
        if text[:len(before)] == before:
            states.add("retail")
        else:
            after = _after_site(payload, name)
            states.add("applied" if after and text[:len(after)] == after else "foreign")
    return states.pop() if len(states) == 1 else "mixed"


def _after_site(payload: bytes, name: str) -> bytes:
    """The installed hook bytes; needs the code allocation when the owner is installed."""
    rows = _owned(payload) if space.status(payload) == "applied" else None
    if rows is None:
        return b""
    labels = code_for(payload, rows[0]["va"], rows[1]["va"])[1]
    return dict((site, after) for site, _va, after in sites(labels))[name]


def status(payload: bytes) -> str:
    """retail | applied | foreign for a USA executable."""
    try:
        if payload[:4] != b"XBEH" or struct.unpack_from("<I", payload, 0x104)[0] != IMAGE_BASE:
            return "foreign"
        allocator = space.status(payload)
        if allocator == "foreign":
            return "foreign"
        site = _site_state(payload)
        if site == "foreign" or site == "mixed":
            return "foreign"
        if allocator == "retail":
            return "retail" if site == "retail" else "foreign"
        rows = _owned(payload) if any(a["owner"] == OWNER for a in space.layout(payload)["allocations"]) else None
        if rows is None:
            return "retail" if site == "retail" else "foreign"
        if not _guard_state(payload):
            return "foreign"
        code_a, data_a = rows
        image = XbeImage(payload)
        code = image.read(code_a["va"], CODE_SIZE)
        data = image.read(data_a["va"], DATA_SIZE)
        if code == b"\xcc" * CODE_SIZE and data == bytes(DATA_SIZE):
            return "retail" if site == "retail" else "foreign"
        expected, labels = code_for(payload, code_a["va"], data_a["va"])
        if code != expected:
            return "foreign"
        if data != data_for(payload):
            return "foreign"
        return "applied" if site == "applied" else "foreign"
    except (StarCareerError, ValueError, KeyError, IndexError, TypeError, struct.error, OverflowError):
        return "foreign"


def read_settings(payload: bytes) -> dict[str, object]:
    state = status(payload)
    return {"status": state, "owner": OWNER, "experimental": True, "runtime_witnessed": False,
            "code_bytes": CODE_SIZE, "data_bytes": DATA_SIZE, "read_only_bytes": 0,
            "class_stars": "3..5 top prospects + 1..2 gems", "gain": GAIN, "lose": LOSE,
            "superstar_coin": "1 in 8", "veteran_qb_floor": VETERAN_QB_FLOOR}


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the star-career owner on a COPY of the executable."""
    state = status(payload)
    if state == "applied":
        return payload, {"status": "already_applied", "changed_bytes": 0, "edits": [], **read_settings(payload)}
    _require(state == "retail", f"the star-career sites are {state}; rebuild from a supported base")
    _require(_guard_state(payload), "a star-career dependency (class generator/aging/overall/stat) is not retail")
    allocator = space.status(payload)
    if allocator == "retail":
        allocated, _ = space.apply(payload, REQUESTS, scaleout=True)
    else:
        _require(allocator == "applied", "the executable's extra-space layout is foreign")
        rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
        allocated = payload if rows else space.extend_scaleout(payload, REQUESTS)[0]
    code_a, data_a = _owned(allocated)
    body, labels = code_for(allocated, code_a["va"], data_a["va"])
    installed, code_receipt = space.install_code(allocated, OWNER, body)
    image = XbeImage(installed)
    _require(image.read(data_a["va"], DATA_SIZE) == bytes(DATA_SIZE),
             "the star-career data allocation is not zero initialised")
    buf = bytearray(installed)
    sections = _sections(buf)
    touched = set()
    edits = []
    for name, va, after in sites(labels):
        off = _offset(bytes(buf), va, len(after))
        before = bytes(buf[off:off + len(after)])
        buf[off:off + len(after)] = after
        touched.add(next(s.index for s in sections if s.raw_offset <= off < s.raw_offset + s.raw_size))
        edits.append({"label": name, "va": hex(va), "file_offset": hex(off), "size": len(after),
                      "before_sha256": hashlib.sha256(before).hexdigest(),
                      "after_sha256": hashlib.sha256(after).hexdigest()})
    for section in sections:
        if section.index in touched:
            buf[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(buf), section)
    result = bytes(buf)
    _require(status(result) == "applied", "star-career installation postcondition failed")
    return result, {"status": "applied", "changed_bytes": sum(a != b for a, b in zip(payload, result)),
                    "edits": edits, "sections_repinned": sorted(touched),
                    "code_va": hex(code_a["va"]), "data_va": hex(data_a["va"]),
                    "code_install": code_receipt, "source_sha256": hashlib.sha256(payload).hexdigest(),
                    "result_sha256": hashlib.sha256(result).hexdigest(), **read_settings(result)}


def reservations(payload: bytes) -> list[dict[str, object]]:
    out = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    for name, va, _before, size in HOOKS:
        out.append({"owner": OWNER, "start": hex(va), "end": hex(va + size), "size": size,
                    "basis": "pinned live " + name + "; not a cave"})
    return out


__all__ = ["OWNER", "UI_LABEL", "BUILD_CAPTION", "HELP_TEXT", "CODE_SIZE", "DATA_SIZE", "REQUESTS",
           "POSITIONS", "VALUE", "FIELD", "THI", "TMID", "TLO", "GAIN", "LOSE", "VETERAN_QB_FLOOR",
           "TIER_X", "TIER_SUPERSTAR", "MIN_GAMES", "GEM_MIN_RANK", "GEM_MAX_RANK", "GEM_POTENTIAL",
           "TIER_LIMITS", "HOOKS", "GUARDS", "SYMBOLS", "StarCareerError", "apply", "code_for", "data_for",
           "potential_table", "read_settings", "reservations", "sites", "status"]
