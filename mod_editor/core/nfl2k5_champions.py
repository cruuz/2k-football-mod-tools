"""Super Bowl champion pop-up, champions history and modern award voting (job hn1, beta 79). EXPERIMENTAL.

Noah, 2026-10-28: "at the end of a season, when you click advance to offseason, there should be a pop-up that says, this
team won the Super Bowl, this player was Super Bowl MVP. And I wonder if there's a place to track that in the game over
time, because currently, when I go to a new season, I don't know who won the last Super Bowl." and "retune how the game
calculates player awards to match how they are given out over the last decade ... always leave exceptions where if
someone puts up insane stats at literally any position ... that player could win MVP".

This is a companion of the Player Card honors owner (``nfl2k5_honors``): ``nfl2k5_honors.apply`` installs it and its
status needs both. It is one late allocator owner (code only, no writable memory) with two retail sites.

What the retail game does (static analysis of the USA ``default.xbe``; the stage advance ``FUN_002480B0``)
-------------------------------------------------------------------------------------------------------
* The Super Bowl is week row 0x14 (0x15 with the repaired 18-week season; the immediate at 0x133A41), game 0 of the
  league grid. Retail tells only a user who played it ("Congratulations, you won the Super Bowl!", ``FUN_00247A20``, and
  not in Franchise mode); nobody is told who the champion is.
* "Advance to offseason" is the stage-9 action of ``FUN_002480B0``: ``call 0x2BDB00`` (the retirement pass) at 0x2485FA,
  then the year increment and the stage change. At that moment the Super Bowl cell, the season object's Super Bowl MVP
  (+0x5888) and season MVP (+0x5800) are all still there; the rollover clears them.
* The season's player awards are computed in ``FUN_00116920`` in the final regular week, ending with the call at 0x116E55
  (``FUN_00115FB0``, then the honors owner's rushing-title tail jump).

What this owner adds
--------------------
* ``champions_advance`` at 0x2485FA: one native notice ("<City Team> won Super Bowl <numeral>, 29-13 over the <City
  Team>.", "Super Bowl MVP: <name>, <pos>", "Season MVP: ..."), then the retail retirement pass. Franchise only. It also
  records the season in the history below. One confirm closes the notice; nothing else changes.
* The history: season n (Super Bowl number n, the season's year minus 1965) is kept in team record n % 32, bytes
  +0xE4..+0x103 (32 bytes: number, champion, runner-up, both scores, the Super Bowl MVP and the season MVP as six-bit
  packed names with a position code, the MVP's club, a check byte). Those bytes of the 500-byte team record are zero in
  every club of the disc roster, are never read or written by a retail routine (checked over ten simulated seasons) and
  travel with the roster arena in every franchise save, so the save size, the layout and the player history pool are
  untouched, an old save simply reads as an empty history, and the last 32 seasons are kept.
* The viewer is a third page of the Player Card (the honors page's bumpers now cycle card, honors, champions): the ten
  newest seasons in the rating panel ("2025 SEA" with "29-13 NE") and the newest Super Bowl, its MVP and the season MVP
  in the bio lines.
* ``champions_awards`` at 0x116E55: after the retail award pass, the MVP, offensive and defensive player of the year and
  both rookies of the year are chosen again by production (``tools/nfl2k5_champions/runtime.c``, ``champions_modern_awards``;
  the rule is in ``AWARD_RULE`` below), and the honors owner records the new winners.

Allocation: a late owner (``nfl2k5_xbe_space.LATE_OWNERS``, right after the honors owner it is installed with, so the
owners that Studio appends one by one later keep their places), code only; it does not fit the MyCareer gap.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_champions_code as runtime
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_champions"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = 5632
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)

HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: nobody is told who won the Super Bowl and the game keeps no list of champions. "
    "Patch: advancing to the offseason shows who won the Super Bowl, the score, the Super Bowl MVP and the season MVP, "
    "and keeps the last 32 champions in the team records (no save size change; old saves start empty); the Player Card "
    "gets a third page, champions. MVP, offensive and defensive player of the year and the rookies of the year are "
    "voted by production the way they have gone in the last decade: a quarterback on a winning team almost always, "
    "skill players for offensive player of the year, pass rushers, tackles, linebackers and corners for defensive "
    "player of the year, and any position can win MVP with a season far beyond a record.")

# season awards by position code (QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE); production in hundredths of a point
AWARD_RULE = {
    "offense_points": "1 per 25 passing yards, 4 per passing TD, -2 per interception, 1 per 10 rushing or receiving "
                      "yards, 6 per rushing or receiving TD, 0.5 per catch",
    "defense_points": "3.5 per half sack (7 per sack), 0.25 per tackle, 10 per interception, 3 per forced fumble",
    "mvp_weight_percent": (100, 0, 0, 58, 38, 36, 36, 60, 40, 48, 40, 40, 0, 0, 0, 44, 44),
    "opoy_weight_percent": (72, 0, 0, 100, 0, 0, 0, 100, 55, 88, 0, 0, 0, 0, 0, 0, 0),
    "dpoy_weight_percent": (0, 0, 0, 0, 110, 45, 45, 0, 0, 0, 100, 85, 0, 0, 0, 105, 100),
    "droy_weight_percent": (0, 0, 0, 0, 120, 45, 45, 0, 0, 0, 105, 60, 0, 0, 0, 105, 110),
    "team_factor": "35% at a .400 record or worse rising to 100% at .750 or better (MVP only)",
    "otherworldly": {"sacks": 30, "tackles": 300, "rushing_yards": 2500, "receiving_yards": 2200, "passing_yards": 6000,
                     "passing_touchdowns": 60, "interceptions": 15},
}

POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
_OFFENSE = frozenset((0, 3, 7, 8, 9))
_NO_AWARDS = frozenset((1, 2, 12, 13, 14))        # kickers, punters and the offensive line are not voted on
OTHERWORLDLY_MARKS = (("sacks2", 60), ("tackles", 300), ("rush_yds", 2500), ("rec_yds", 2200), ("pass_yds", 6000),
                      ("pass_td", 60), ("def_int", 15))


def offense_points(s) -> int:
    """Production of an offensive player in hundredths of a point (the native ``offense_points``)."""

    v = (s["pass_yds"] * 4 + s["pass_td"] * 400 - s["pass_int"] * 200 + s["rush_yds"] * 10 + s["rush_td"] * 600
         + s["rec_yds"] * 10 + s["rec"] * 50 + s["rec_td"] * 600)
    return max(v, 0)


def defense_points(s) -> int:
    v = s["sacks2"] * 350 + s["tackles"] * 25 + s["def_int"] * 1000 + s["ff"] * 300
    return max(v, 0)


def otherworldly(s) -> int:
    """The largest percentage of any record-breaking mark reached (100 or more wins MVP)."""

    return max(max(s[key], 0) * 100 // mark for key, mark in OTHERWORLDLY_MARKS)


def team_factor(wins: int, losses: int, ties: int) -> int:
    games = wins + losses + ties
    pct = (2 * wins + ties) * 500 // games if games else 0
    if pct <= 400:
        return 35
    return 100 if pct >= 750 else 35 + (pct - 400) * 65 // 350


def choose_awards(players, record) -> dict:
    """The native ``champions_modern_awards`` on plain data. ``players``: the league in the game's iteration order, each
    a mapping with ``pos`` (position code), ``team``, ``yrs`` (years pro; 1 = rookie) and the stat keys of
    ``OTHERWORLDLY_MARKS``/``offense_points``; ``record(team) -> (wins, losses, ties)``. Returns {award: player or None}.
    Ties go to the player met first; the MVP is excluded from OPOY and DPOY."""

    def best(candidates):
        pick, top = None, 0
        for player, score in candidates:
            if score > top:
                pick, top = player, score
        return pick

    weights = AWARD_RULE
    rows = [p for p in players if p["pos"] not in _NO_AWARDS and p["pos"] <= 16]

    def value(p):
        return offense_points(p) if p["pos"] in _OFFENSE else defense_points(p)

    wonder = best((p, otherworldly(p) if otherworldly(p) >= 100 else 0) for p in rows)
    mvp = wonder or best((p, value(p) * weights["mvp_weight_percent"][p["pos"]] * team_factor(*record(p["team"])))
                         for p in rows)
    rest = [p for p in rows if p is not mvp]
    opoy = best((p, value(p) * weights["opoy_weight_percent"][p["pos"]]) for p in rest if p["pos"] in _OFFENSE)
    dpoy = best((p, value(p) * weights["dpoy_weight_percent"][p["pos"]]) for p in rest if p["pos"] not in _OFFENSE)
    rookies = [p for p in rows if p["yrs"] == 1]
    oroy = best((p, value(p)) for p in rookies if p["pos"] in _OFFENSE)
    droy = best((p, value(p) * weights["droy_weight_percent"][p["pos"]]) for p in rookies if p["pos"] not in _OFFENSE)
    return {"mvp": mvp, "opoy": opoy, "dpoy": dpoy, "oroy": oroy, "droy": droy}


# (label, VA, retail bytes, entry label, opcode, length)
SITE_TABLE = (
    ("stage_advance", 0x002485FA, bytes.fromhex("e801550700"), "champions_advance", 0xE8, 5),
    ("season_awards", 0x00116E55, bytes.fromhex("e856f1ffff"), "champions_awards", 0xE8, 5),
)

# Dependencies this owner calls or reads beyond those the honors owner already pins (text, history writer, league grid
# cells, season object), pinned by SHA-256 of their retail bytes (sites masked).
GUARDS = (
    ('stage 9 action', 0x002485FA, 0x2E, "d14b1e0974db00f382b5b6252c62037bfa56c4a104a79e6aedb49a7aef07775b"),
    ('retirement pass entry', 0x002BDB00, 0x20, "58f9798c97da9fbf47e6cff15d0068a1e1841516a4080c7db57d00dffb05a327"),
    ('award pass tail', 0x00115FB0, 0x20, "578d136fe76c1aba87a6fe9162ea2de29d76f0564f7b6105bd92f9be3805d901"),
    ('information notice', 0x0014E520, 0x19, "3546625976e5bf1c782ad583cbc3f5bf3646469daace6d13f8907e2719a5c18f"),
    ('season stat getter', 0x0014EE40, 0x20, "68c830b0651183324d1470da02aad004f84fb2cb4ca3476efdb0cd48f2e9021e"),
    ('team by index', 0x000C4C50, 0x2E, "f421059ce4ea9ac33e94e9e1541b8fcbbd4c7b28da07038136d5586a526b1dcf"),
    ('team count', 0x000C6430, 0x30, "b954682454bbc2d4da9b59fa5a1212d82a45f0507204723663cf6a5bb4bc8c34"),
    ('team wins', 0x000C7720, 0x30, "83c4b626588be7c7e5da821f5c997519a879a1363edf84c23e2859e5c17a3d90"),
    ('team losses', 0x000C7750, 0x30, "405d309f1add61c7e134c95d1ec455b83848e24c1c882cdb42bfacf43cffc714"),
    ('team ties', 0x000C7780, 0x30, "2481cd7485cb21874604d2e063c8f2897c951ae7efa349ec2cd4dcf181494dab"),
    ('win counter', 0x000C75A0, 0x60, "cbe4cab6a80f68a09980c88ad0abd67a8ec737a01adf3457db9b1dbfe960d094"),
    ('loss counter', 0x000C7620, 0x60, "bc10e4d0f3c0550618ceb2b1d6250e4170e1bf62b9370f59c1bc9acd57f3f68b"),
    ('tie counter', 0x000C76A0, 0x60, "4594d45858da1bc87c39e6acf7fb4ef022f162d1302509242d43b4656bd178b3"),
    ('position names', 0x004F26D0, 0x44, "85b60c8981b4ecac92702695a51ed9249b0cbaa70aef69ec95cdb873c5d43c9b"),
)
# bytes inside guarded spans that other patches change: (VA, size). None; the Super Bowl row immediate is checked.
VARIABLE_BYTES = ()
SUPER_BOWL_ROW_VA = 0x00133A41
SUPER_BOWL_ROWS = (0x14, 0x15)


class ChampionsError(ValueError):
    """Unsupported executable, foreign or mixed installation."""


def _require(condition, message):
    if not condition:
        raise ChampionsError(message)


def _rel32(source_end: int, target: int) -> bytes:
    return struct.pack("<i", target - source_end)


def code_for(code_va: int) -> bytes:
    """The owned RX content with the template's relocations applied, padded to CODE_SIZE with int3."""

    result = bytearray(runtime.CODE)
    for offset, kind, symbol, value in runtime.RELOCATIONS:
        _require(symbol == "code", "unexpected champions relocation")
        target = code_va + value + struct.unpack_from("<i", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    _require(len(result) <= CODE_SIZE, "the champions runtime exceeds its fixed budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def labels(code_va: int) -> dict[str, int]:
    return {name: code_va + offset for name, offset in runtime.LABELS.items()}


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    """Every executable edit as (label, VA, retail bytes, patched bytes)."""

    at = labels(code_va)
    return [(label, va, before, bytes([opcode]) + _rel32(va + 5, at[entry]) + b"\x90" * (length - 5))
            for label, va, before, entry, opcode, length in SITE_TABLE]


def _guard_digest(image: XbeImage, va: int, size: int, checked_sites) -> str:
    content = bytearray(image.read(va, size))
    for _label, address, before, _after in checked_sites:
        if va <= address and address + len(before) <= va + size:
            content[address - va:address - va + len(before)] = before
    for address, length in VARIABLE_BYTES:
        if va <= address and address + length <= va + size:
            content[address - va:address - va + length] = bytes(length)
    return hashlib.sha256(content).hexdigest()


def guard_digests(payload: bytes) -> dict[str, str]:
    """The masked digests of every guarded span (used to pin GUARDS from the retail executable)."""

    image = XbeImage(payload)
    return {name: _guard_digest(image, va, size, sites(0x14DA000)) for name, va, size, _d in GUARDS}


def _check_guards(image: XbeImage, checked_sites) -> None:
    for name, va, size, digest in GUARDS:
        _require(_guard_digest(image, va, size, checked_sites) == digest, f"foreign champions dependency: {name} ({va:#x})")
    _require(image.read(SUPER_BOWL_ROW_VA, 1)[0] in SUPER_BOWL_ROWS, "foreign Super Bowl row predicate")


def allocations(payload: bytes) -> dict[str, dict]:
    """{"code": row} of an installed allocation, {} when the owner is not allocated."""

    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) == "applied" else []
    if not rows:
        return {}
    _require(len(rows) == 1 and rows[0]["kind"] == "code" and (rows[0]["size"], rows[0]["align"]) == (CODE_SIZE, 16),
             "foreign champions allocation")
    return {"code": rows[0]}


def owned_state(payload: bytes):
    """-> ("retail" | "applied", allocations | None); anything else raises."""

    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    found = allocations(payload)
    if not found:
        retail_sites = sites(0x14DA000)  # the retail bytes do not depend on the pages
        _require(rdata.status(payload, retail_sites) == "retail", "champions sites changed without an allocation")
        _check_guards(image, retail_sites)
        return "retail", None
    code_va = found["code"]["va"]
    code = image.read(code_va, CODE_SIZE)
    if code == b"\xcc" * CODE_SIZE:
        edits = sites(code_va)
        _require(rdata.status(payload, edits) == "retail", "champions sites changed with an empty allocation")
        _check_guards(image, edits)
        return "retail", found
    _require(code == code_for(code_va), "foreign champions code")
    edits = sites(code_va)
    _require(rdata.status(payload, edits) == "applied", "mixed champions sites")
    _check_guards(image, edits)
    return "applied", found


def status(payload: bytes) -> str:
    try:
        return owned_state(payload)[0]
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return "foreign"


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    base = allocations(payload)
    edits = sites(base["code"]["va"] if base else 0x14DA000)
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in edits]


def install(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Fill the established allocation and patch the two sites. Idempotent. The allocation must exist."""

    state, found = owned_state(payload)
    common = {"owner": OWNER, "experimental": True, "code_bytes": len(runtime.CODE), "owner_bytes": CODE_SIZE}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    _require(bool(found), "reserve the champions allocation first")
    code_va = found["code"]["va"]
    installed, code_receipt = space.install_code(payload, OWNER, code_for(code_va))
    result, site_receipt = rdata.apply(installed, sites(code_va), OWNER)
    _require(status(result) == "applied", "champions postcondition failed")
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(code_va), "sites": [{"label": label, "va": hex(va), "size": len(before)}
                                                       for label, va, before, _after in sites(code_va)]}


__all__ = ["OWNER", "REQUESTS", "HELP_TEXT", "AWARD_RULE", "ChampionsError", "code_for", "sites", "labels", "allocations",
           "install", "status", "reservations", "guard_digests", "owned_state"]
