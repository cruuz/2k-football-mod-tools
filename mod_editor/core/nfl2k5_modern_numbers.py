"""Modern jersey numbers for players who join a club (beta 81; owner nfl2k5_modern_numbers).

Owner's words (11/25): "i notice rookie rbs and wrs use old numbers... make sure new additions can use modern position
numbers... a top rookie wr prob wants single digit with exceptions, rbs too, edge, db, etc".

What retail does (FUN_002BD260, the jersey routine; ECX = player, EDX = club, [esp+4] = keep, ret 4)
----------------------------------------------------------------------------------------------------
Every join calls it: the draft (FUN_00325B50 at 0x325B67, keep = 0; Rookie faces makes that push 1), the CPU free-agent
signing 0x322DA3, both trade-executor sides 0x2BC740 / 0x2BC790, offseason free agency 0x323BFB / 0x32401E, the user
signing paths 0x2B83AE / 0x319BF6 / 0x36F881 / 0x36FA9F and MyCareer (keep = 1). It starts at the player's own number
(keep) or at the bottom of his position's 2004 range (the tables 0x521B90 / 0x521BD8: QB, K, P 1-19, WR and TE 80-89,
every back and DB 20-49, LB and C 50-59, G, T, DT and DE 60-79), walks up past every number another player on the
club's ACTIVE list wears, wraps inside the range, and with the range full draws a random number from the league RNG
(which can repeat a club-mate's). So no rookie outside QB, K and P wore a single digit (0 of 5,721 rookie slots in 36
openings), and a joiner could take the number of a club-mate on the practice squad or on injured reserve.

What this owner does
--------------------
One fixed page at 0x1530000 (nfl2k5_xbe_space.MODERN_NUMBERS_VA: code, then tables) and one 6-byte site: the routine's
first two instructions (``mov eax,[esp+4]; test eax,eax``) become ``jmp page`` + nop. The page (tools/modern_numbers):
  * legal numbers (today's rule, LEGAL_DECADES): QB 0-19; K, P 0-49, 90-99; WR, TE, HB, FB 0-49, 80-89; CB, FS, SS
    0-49; OLB, ILB 0-59, 90-99; DT 50-79, 90-99; C, G, T 50-79; DE 0-79, 90-99 (the game's DE is the edge player: an
    edge rusher's linebacker numbers and a defensive lineman's; every 2004-range number stays legal);
  * taken = any number worn by another player of the club: active list, practice-squad reserves (and their overflow
    rows), injured reserve (0x246E50 / 0x246EC0: retail or the modern IR owner);
  * a drafted rookie (the call comes from FUN_00325B50 and that routine's caller is one of the three draft paths
    0x325C3B / 0x3265BD / 0x322FB9) and any rookie (years pro 0 or 1) joining before the regular season get a fresh
    draw; anyone else keeps his own number when it is legal and free, else a fresh draw;
  * fresh draw: a single digit with probability SINGLE_DIGIT[group][tier] when one is free, otherwise a decade by the
    real 2026 shares WEIGHTS[group] (single digits left out) over the decades with a free legal number, then a free
    number in it; tier = the draft round (A = 1, B = 2, C = 3, D = 4-7), E for an undrafted rookie, and by rating
    against THRESHOLDS for anyone else; every draw is a hash of (player index, club index, season, stage, k): no game
    RNG, the same number after a reload;
  * nothing legal free: the retail routine with keep = 1 (its walk and its own fallback).
Only the joiner's +0x20 bits 3..9 change (and the retail tail moves his play-by-play cue 9000..9099 with the number).
Nobody already on a club is renumbered; Create Player and the user's own number screen are untouched.

States: "retail" (site retail; page not reserved or 0xCC), "applied" (site enters the page and the page is exactly the
current template for its address), "previous" (site enters the page and the page is an earlier revision's template,
PREVIOUS_TEMPLATES; apply upgrades it in place), anything else "foreign". Retail restores the site and fills the page
with 0xCC; the reservation stays. No save bytes: saves load both ways. EXPERIMENTAL / UNWITNESSED in game.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

OWNER = "nfl2k5_modern_numbers"
BUILD_KEY = "modern_numbers"
LABEL = "EXPERIMENTAL / UNWITNESSED"
BUILD_CAPTION = "Modern jersey numbers"
HELP_TEXT = ("Players who join a club (draft picks, signings, trades) get today's NFL numbers: single digits for many top "
             "receivers, backs and defensive backs, 0 allowed, edge rushers in the 50s and 90s. A new player never takes "
             "a number a teammate already wears, on the practice squad or injured reserve included. Nobody already on a "
             "club changes number.")
MODES = ("retail", "modern")

SITE_VA = 0x2BD260
SITE_RETAIL = bytes.fromhex("8b44240485c0")          # mov eax, [esp+4]; test eax, eax
SITE_SIZE = len(SITE_RETAIL)
CODE_SIZE = 0x1000
PLACEHOLDER_VA = 0x1530000

# ------------------------------------------------------------------------------------------------ the rule's tables
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
GROUPS = ("QB", "RB", "FB", "WR", "TE", "OL", "DL", "EDGE", "LB", "DB", "K", "P")
TIERS = ("A", "B", "C", "D", "E")


def _decades(*spans):
    bits = 0
    for low, high in spans:
        for d in range(low // 10, high // 10 + 1):
            bits |= 1 << d
    return bits


# Legal numbers by position code, whole decades (DESIGN 3.1; DE: the union of the edge-as-LB and the DL rule).
LEGAL_DECADES = (
    _decades((0, 19)),                       # QB
    _decades((0, 49), (90, 99)),             # K
    _decades((0, 49), (90, 99)),             # P
    _decades((0, 49), (80, 89)),             # WR
    _decades((0, 49)),                       # CB
    _decades((0, 49)),                       # FS
    _decades((0, 49)),                       # SS
    _decades((0, 49), (80, 89)),             # HB
    _decades((0, 49), (80, 89)),             # FB
    _decades((0, 49), (80, 89)),             # TE
    _decades((0, 59), (90, 99)),             # OLB
    _decades((0, 59), (90, 99)),             # ILB
    _decades((50, 79)),                      # C
    _decades((50, 79)),                      # G
    _decades((50, 79)),                      # T
    _decades((50, 79), (90, 99)),            # DT
    _decades((0, 79), (90, 99)),             # DE
)
GROUP_OF = tuple(GROUPS.index(g) for g in ("QB", "K", "P", "WR", "DB", "DB", "DB", "RB", "FB", "TE", "LB", "LB", "OL",
                                           "OL", "OL", "DL", "EDGE"))
# Players by decade 0s..90s, nflverse roster_2026 (ACT, RES, DEV; sha256 eaf39f34..., modern-numbers/calc/
# nfl_numbers.txt); FB alone (depth chart FB, 19 players: 30s 7, 40s 12) out of RB. Column 0 is not drawn by weight.
WEIGHTS = (
    (41, 70, 0, 0, 0, 0, 0, 0, 0, 0),        # QB
    (26, 7, 64, 74, 25, 0, 0, 0, 0, 0),      # RB (HB)
    (0, 0, 0, 7, 12, 0, 0, 0, 0, 0),         # FB
    (68, 118, 4, 6, 2, 0, 0, 0, 120, 0),     # WR
    (8, 6, 0, 1, 28, 0, 0, 0, 148, 0),       # TE
    (0, 0, 0, 0, 0, 41, 186, 228, 0, 0),     # OL
    (0, 0, 0, 0, 0, 24, 19, 10, 0, 181),     # DL (DT)
    (27, 16, 6, 14, 51, 113, 5, 3, 0, 105),  # EDGE (DE)
    (14, 7, 3, 9, 73, 81, 0, 0, 0, 0),       # LB
    (79, 18, 205, 145, 35, 0, 0, 0, 0, 0),   # DB
    (11, 13, 2, 11, 1, 0, 0, 0, 0, 0),       # K
    (10, 19, 0, 5, 2, 0, 0, 0, 0, 0),        # P
)
# Single-digit target, percent, by tier A B C D E (DESIGN 3.2 step 3, from nflverse players on rookie deals by round).
SINGLE_DIGIT = (
    (50, 40, 30, 14, 12),                    # QB
    (55, 20, 20, 12, 2),                     # RB
    (0, 0, 0, 0, 0),                         # FB
    (65, 30, 16, 12, 6),                     # WR
    (5, 3, 5, 4, 0),                         # TE
    (0, 0, 0, 0, 0),                         # OL
    (0, 0, 0, 0, 0),                         # DL
    (23, 20, 15, 2, 0),                      # EDGE
    (10, 8, 8, 4, 2),                        # LB
    (54, 40, 23, 8, 3),                      # DB
    (28, 28, 28, 28, 28),                    # K
    (28, 28, 28, 28, 28),                    # P
)
# Overall (0x246D80(player, 1), rounded as the quarterback room rounds it) at or above which a non-draft joiner is tier A,
# B, C: the top 10, 25 and 40 percent of each position on the 32 active lists of the shipped 2026 roster at 2026 week 1
# (kept image sha256 82c00d50..., modern-numbers/calc2/thresholds.json). OLB holds no player there: ILB's values.
THRESHOLDS = (
    (96, 85, 79), (93, 91, 83), (92, 84, 81), (90, 84, 79), (84, 78, 72), (89, 79, 76), (89, 82, 77), (89, 75, 69),
    (100, 92, 81), (85, 75, 69), (86, 80, 75), (86, 80, 75), (96, 81, 74), (93, 85, 79), (91, 83, 77), (81, 74, 69),
    (86, 80, 74),
)
# FUN_00325B50's call of the jersey routine returns to DRAFT_JOIN_RET; FUN_00325B50 itself is called by the three draft
# paths, whose return addresses identify a drafted rookie (and its stack argument is the pick word, round << 5 | slot).
DRAFT_JOIN_RET = 0x325B6C
DRAFT_CALLERS = (0x325C40, 0x3265C2, 0x322FBE)       # after the calls at 0x325C3B, 0x3265BD, 0x322FB9
SALT = 0x4D4E554D                                    # "MNUM"
LEAGUE_GLOBALS = {"root": 0xB72918, "arena_size": 0xB72808, "mode": 0xE576A0, "stage": 0xE576A4, "season": 0xE576B8}

# Retail bytes the page relies on (sha256): the routine body after the site (re-entered at 0x2BD266 on the fallback,
# its tail 0x2BD33F jumped to on the normal path; 0x2BD2F7..0x2BD2FC may hold Rookie faces' dlwrap jump), the draft
# join 0x325B58..0x325B6C (0x325B61 may hold Rookie faces' push 1) and the three draft calls of 0x325B50.
GUARDS = (
    (0x2BD266, 0x2BD370 - 0x2BD266, "ed92476dc2abb1013ee158ed98e180c14288d3bde7b2c971b0ee862b21bae258"),
    (0x325B58, 0x325B6C - 0x325B58, "ac982826af2a7bab282c5cd5e5943b4fa070d9083c1a3b803b5d8fd104eb585d"),
    (0x325C3B, 5, "dc1b18fcf40862ae344c90448a7ffa7dbf9c372df0df6bf204390ea8f49b759c"),   # call 0x325B50
    (0x3265BD, 5, "c5354c530a29fa7257cefe908d8c7832bf297f8517bc980ab5e777f613c4fc70"),   # call 0x325B50
    (0x322FB9, 5, "275ff4163dfe548cb8bbf3c47d10ec903cc57bddc051cdf5dcc55f8f30583eb3"),   # call 0x325B50
)
ROOKIE_FACES_SPANS = ((0x2BD2F7, bytes.fromhex("8bb0901b5200"), bytes.fromhex("e9b19be2ff90")),
                      (0x325B61, bytes.fromhex("6a00"), bytes.fromhex("6a01")))
PREVIOUS_TEMPLATES: tuple[bytes, ...] = ()           # no earlier revision has shipped (beta 81 is the first)

_FAILURES = (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError)


class ModernNumbersError(ValueError):
    """The jersey routine, the page or its site could not be verified."""


def _require(ok, message):
    if not ok:
        raise ModernNumbersError(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _space():
    from . import nfl2k5_xbe_space as space
    return space


def _code():
    from . import nfl2k5_modern_numbers_code as code
    return code


def tables_bytes() -> bytes:
    """The tables exactly as the page holds them (tools/modern_numbers/build.py renders tables.h from these)."""
    out = bytearray()
    out += struct.pack("<17H", *LEGAL_DECADES)
    out += bytes(GROUP_OF)
    for row in WEIGHTS:
        out += struct.pack("<10H", *row)
    for row in SINGLE_DIGIT:
        out += bytes(row)
    for row in THRESHOLDS:
        out += bytes(row)
    out += struct.pack("<3I", *DRAFT_CALLERS)
    return bytes(out)


def code_for(page_va: int) -> bytes:
    """The whole page linked for ``page_va``."""
    return _code().page_bytes(page_va)


def site_bytes(page_va: int) -> bytes:
    return b"\xe9" + struct.pack("<i", page_va + _code().LABELS["number_entry"] - (SITE_VA + 5)) + b"\x90"


def sites(page_va: int) -> list[tuple[str, int, bytes, bytes]]:
    return [("jersey_entry", SITE_VA, SITE_RETAIL, site_bytes(page_va))]


# ------------------------------------------------------------------------------------------------ owner state
def allocation(payload: bytes) -> dict | None:
    """The page's allocator row, or None when this executable has no reservation for it."""
    space = _space()
    if not space.is_scaleout(payload) or space.status(payload) != "applied":
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and tuple(rows[0][k] for k in ("owner", "kind", "size", "align"))
             == space.MODERN_NUMBERS_REQUEST and rows[0]["va"] == space.MODERN_NUMBERS_VA
             and rows[0].get("owner_offset", 0) == 0, "foreign modern numbers allocation")
    return rows[0]


def _guards(payload: bytes) -> None:
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        for at, retail, patched in ROOKIE_FACES_SPANS:   # Rookie faces' two bytes inside the guarded spans
            if va <= at and at + len(retail) <= va + size and blob[at - va:at - va + len(retail)] == patched:
                blob[at - va:at - va + len(retail)] = retail
        _require(_sha(bytes(blob)) == digest, f"foreign jersey routine or draft join bytes at {va:#x}")


def _state(payload: bytes) -> tuple[str, dict | None]:
    from . import nfl2k5_rdata_sites as rdata
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    _guards(payload)
    found = allocation(payload)
    if found is None:
        _require(rdata.status(payload, sites(PLACEHOLDER_VA)) == "retail",
                 "the jersey routine's entry changed without an allocation")
        return "retail", None
    image = XbeImage(payload)
    section = image.section(found["va"], CODE_SIZE)
    _require(section is not None and section.flags & 1 and section.flags & 4,
             "the modern numbers page is not in a writable executable section")
    page = image.read(found["va"], CODE_SIZE)
    site = rdata.status(payload, sites(found["va"]))
    if page == b"\xcc" * CODE_SIZE:
        _require(site == "retail", "the jersey routine's entry changed with an empty page")
        return "retail", found
    _require(site == "applied", "mixed modern numbers site and page")
    if page == code_for(found["va"]):
        return "applied", found
    _require(page in tuple(_link_previous(t, found["va"]) for t in PREVIOUS_TEMPLATES), "foreign modern numbers page")
    return "previous", found


def _link_previous(template, page_va):
    return template(page_va) if callable(template) else template


def status(payload: bytes) -> str:
    """retail / applied / previous / foreign for default.xbe."""
    try:
        return _state(bytes(payload))[0]
    except _FAILURES:
        return "foreign"


def read_settings(payload: bytes) -> dict:
    try:
        state, found = _state(bytes(payload))
    except _FAILURES:
        return {"status": "foreign", "mode": None}
    out = {"status": state, "mode": "modern" if state in ("applied", "previous") else "retail"}
    if found is not None:
        out.update(page_va=hex(found["va"]), site_va=hex(SITE_VA))
    return out


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in _space().reservations(payload) if r["owner"] == OWNER]
    return rows + [dict(owner=OWNER, start=hex(SITE_VA), end=hex(SITE_VA + SITE_SIZE), size=SITE_SIZE,
                        basis="pinned live jersey routine entry; not a cave")]


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install (or upgrade a previous revision of) the owner: its fixed page (reserved now when the image lacks it, a late
    owner that moves nobody) and the site. Idempotent."""
    from . import nfl2k5_rdata_sites as rdata
    space = _space()
    state, found = _state(bytes(payload))
    common = {"owner": OWNER, "label": LABEL, "experimental": True, "runtime_witnessed": False, "mode": "modern"}
    if state == "applied":
        return payload, {**common, "status": "applied", "already_applied": True, "changed_bytes": 0}
    before = payload
    if found is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, (space.MODERN_NUMBERS_REQUEST,), scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, (space.MODERN_NUMBERS_REQUEST,))
        found = allocation(payload)
    _require(found is not None, "reserve the modern numbers page first")
    page_va = found["va"]
    previous = None
    if state == "previous":
        from .nfl2k5_cave_oracle import XbeImage
        previous = XbeImage(payload).read(page_va, CODE_SIZE)
    payload, code_receipt = space.install_code(payload, OWNER, code_for(page_va), previous=previous)
    if state != "previous":
        payload, _ = rdata.apply(payload, sites(page_va), OWNER)
    _require(status(payload) == "applied", "modern numbers postcondition failed")
    return payload, {**common, "status": "applied", "already_applied": False, "upgraded_from": state,
                     "code_install": code_receipt, "page_va": hex(page_va), "site_va": hex(SITE_VA),
                     "changed_bytes": space.count_differing_bytes(before, payload) + abs(len(payload) - len(before)),
                     "before_sha256": _sha(before), "after_sha256": _sha(payload)}


def remove(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Retail: the site back to its retail bytes and the page back to its int3 fill (the reservation stays; nothing
    moves). The exact inverse of filling an already reserved page."""
    from . import nfl2k5_rdata_sites as rdata
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    state, found = _state(bytes(payload))
    if state == "retail":
        return payload, {"owner": OWNER, "status": "retail", "already_retail": True, "changed_bytes": 0}
    before = payload
    page_va = found["va"]
    installed = XbeImage(payload).read(page_va, CODE_SIZE)
    back = [(label, va, after, retail) for label, va, retail, after in sites(page_va)]
    payload, _ = rdata.apply(payload, back, OWNER + " removal")
    payload, _ = space.install_code(payload, OWNER, b"\xcc" * CODE_SIZE, previous=installed)
    _require(status(payload) == "retail", "the modern numbers did not come off cleanly")
    return payload, {"owner": OWNER, "status": "retail", "already_retail": False,
                     "changed_bytes": space.count_differing_bytes(before, payload)}


def set_mode(payload: bytes, mode: str) -> tuple[bytes, Mapping[str, object]]:
    """The Studio's one entry: "modern" installs (or upgrades), "retail" restores."""
    _require(mode in MODES, f"modern numbers mode must be one of {MODES}")
    return apply(payload) if mode == "modern" else remove(payload)


# ------------------------------------------------------------------------------------------------ the rule in Python
def legal(position: int, number: int) -> bool:
    return 0 <= number <= 99 and bool(LEGAL_DECADES[position] >> (number // 10) & 1)


def fmix32(h: int) -> int:
    h ^= h >> 16
    h = h * 0x85EBCA6B & 0xFFFFFFFF
    h ^= h >> 13
    h = h * 0xC2B2AE35 & 0xFFFFFFFF
    return h ^ h >> 16


def draw(key, k: int) -> int:
    h = SALT
    for word in (*key, k):
        h = fmix32(h ^ (word & 0xFFFFFFFF))
    return h


def pick(position: int, own: int, taken, key, *, draft_round: int | None = None, rookie_preseason: bool = False,
         overall: int = 0) -> int:
    """The page's rule in Python (tests compare the two): ``taken`` = numbers worn by the club's other players, ``key`` =
    (player index, club index, season, stage). -1 = the retail routine."""
    free = lambda n: legal(position, n) and n not in taken  # noqa: E731
    if draft_round is None and not rookie_preseason and 0 <= own <= 99 and free(own):
        return own
    group = GROUP_OF[position]
    if draft_round is not None:
        tier = min(draft_round, 3)
    elif rookie_preseason:
        tier = 4
    else:
        a, b, c = THRESHOLDS[position]
        tier = 0 if overall >= a else 1 if overall >= b else 2 if overall >= c else 3
    in_decade = lambda d: [n for n in range(10 * d, 10 * d + 10) if free(n)]  # noqa: E731
    if draw(key, 1) % 100 < SINGLE_DIGIT[group][tier] and in_decade(0):
        singles = in_decade(0)
        return singles[draw(key, 2) % len(singles)]
    weights = [WEIGHTS[group][d] if in_decade(d) else 0 for d in range(10)]
    total = sum(weights[1:])
    if total:
        r = draw(key, 3) % total
        for d in range(1, 10):
            if r < weights[d]:
                numbers = in_decade(d)
                return numbers[draw(key, 4) % len(numbers)]
            r -= weights[d]
    numbers = [n for n in range(100) if free(n)]
    if not numbers:
        return -1
    return numbers[draw(key, 5) % len(numbers)]


__all__ = ["OWNER", "BUILD_KEY", "LABEL", "BUILD_CAPTION", "HELP_TEXT", "MODES", "SITE_VA", "SITE_RETAIL", "CODE_SIZE",
           "POSITIONS", "GROUPS", "TIERS", "LEGAL_DECADES", "GROUP_OF", "WEIGHTS", "SINGLE_DIGIT", "THRESHOLDS",
           "DRAFT_JOIN_RET", "DRAFT_CALLERS", "GUARDS", "ModernNumbersError", "tables_bytes", "code_for", "site_bytes",
           "sites", "allocation", "status", "read_settings", "reservations", "apply", "remove", "set_mode", "legal",
           "draw", "pick"]
