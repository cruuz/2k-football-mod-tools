"""Include reserves in Franchise Free Practice's disposable game roster.

Replace the complete retail staging function at 0x61730 in place. ECX/EDX
are the two source teams; 0xB30864/0xB30A58 are the two 500-byte game copies.
Each side already has capacity for 65 84-byte player copies. Only the copies
get active+reserve counts, and only for league type 1, game modes 0..2.
Mode 3 (training) and every game-day mode retain the retail active-only view.

No cave, new runtime flag, source-roster mutation, or save-format change.
Requires the practice-squad runtime and Franchise Practice patch first.
This is bounded-function verified; controller/rendering acceptance is manual.
"""
from __future__ import annotations

import struct

from . import nfl2k5_franchise_practice as fp
from . import nfl2k5_practice_squad as ps
from . import nfl2k5_rdata_sites as rdata
from .nfl2k5_draft_ai import _Asm

STAGE_VA = 0x61730
STAGE_SIZE = 0xAB
TEAM_COPIES = (0xB30864, 0xB30A58)
PLAYER_COPIES = (0xB30C4C, 0xB321A0)
COPY_PLAYERS_VA = 0xC3C60
LEAGUE_VA = 0xE576A0
MODE_VA = 0xE5FF80
RETAIL_STAGE = bytes.fromhex(
    "b86408b3002bc8568b3401893083c0043d580ab30072f1b8580ab3008bca2bc88b1401"
    "891083c0043d4c0cb30072f1ba4c0cb300b96408b300e8f22406008a0d8009b30033c0"
    "84c97620b94c0cb300b201890c856408b3008851340fb6358009b3004083c1543bc67ce7"
    "baa021b300b9580ab300e8b72406008a0d740bb30033c084c97624b9a021b300b2028d64"
    "2400890c85580ab3008851340fb635740bb3004083c1543bc67ce75ec3")
RETAIL_COPY_PLAYERS = bytes.fromhex(
    "8a811c0100005333db84c076365556578d7a543bd78b34998bc273128d6424008b2e"
    "892883c00483c6043bc772f20fb6811c01000083c25483c754433bd87cd35f5e5d5bc3")


class PracticeReservesError(ValueError):
    """Unsupported staging bytes or absent prerequisites."""


def code() -> bytes:
    a = _Asm(STAGE_VA)
    a.b("53 56 57 55 52")                    # save nonvolatiles and home source
    a.b("8bf1 bf6408b300 b97d000000 f3a5")    # copy away's 125 dwords
    a.b("5e b97d000000 f3a5")                # copy home to the following team
    a.b("bb6408b300 bf4c0cb300 bd01000000")   # team, players, side tag
    a.label("side")
    a.b("833da076e50001")                    # league == Franchise
    a.j8("75", "copy")
    a.b("833d80ffe50002")                    # unsigned mode <= 2
    a.j8("77", "copy")
    # GCC's private static helper uses EAX=team (observed machine ABI).
    # ps.status pins the entire generated runtime before accepting this call.
    a.b("8bc3")
    a.call(ps.SYMBOLS["reserve_count"])
    a.b("85c0")
    a.j8("7e", "copy")                      # zero or invalid: retain active view
    a.b("00831c010000")                      # expand only the game copy
    a.b("c6839b01000000 66c783f20100000000")  # game copy has no hidden reserve tail
    a.label("copy")
    a.b("8bcb 8bd7")
    a.call(COPY_PLAYERS_VA)
    a.b("0fb68b1c010000 33f6 85c9")
    a.j8("74", "next")
    a.label("player")
    a.b("893cb3 8bc5 884734 83c754 46 3bf1") # repoint copy, set side, next slot
    a.j8("72", "player")
    a.label("next")
    a.b("45 81c3f4010000 bfa021b300 83fd03")
    a.j8("75", "side")
    a.b("5d 5f 5e 5b c3")
    result = a.assemble()
    if len(result) > STAGE_SIZE:
        raise PracticeReservesError("staging replacement exceeds the retail routine")
    return result


def sites() -> list[tuple[str, int, bytes, bytes]]:
    return [("practice_reserve_staging", STAGE_VA, RETAIL_STAGE,
             code().ljust(STAGE_SIZE, b"\x90"))]


def status(payload: bytes) -> str:
    try:
        at = rdata.offset_of(payload, COPY_PLAYERS_VA)
        if payload[at:at + len(RETAIL_COPY_PLAYERS)] != RETAIL_COPY_PLAYERS:
            return "foreign"
        state = rdata.status(payload, sites())
        if state == "applied" and (ps.status(payload) != "applied" or fp.status(payload) != "applied"):
            return "foreign"
        return state
    except (ValueError, struct.error, IndexError):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict[str, object]]:
    if ps.status(payload) != "applied" or fp.status(payload) != "applied":
        raise PracticeReservesError("apply practice squads and Franchise Practice first")
    if status(payload) == "foreign":
        raise PracticeReservesError("foreign practice staging routine or player-copy helper")
    try:
        patched, receipt = rdata.apply(payload, sites(), "Practice reserves")
    except rdata.RdataSiteError as exc:
        raise PracticeReservesError(str(exc)) from exc
    return patched, {**receipt, "runtime_verified": False, "league_type": 1,
                     "practice_modes": [0, 1, 2], "game_day_active_only": True,
                     "source_roster_mutated": False, "new_cave_bytes": 0,
                     "code_bytes": len(code()), "in_game_management": False}
