"""Franchise load: a save with no human-controlled club no longer crashes the Desk (USA retail, xemu-safe).

Report (b780 EMU1 crash_load, triage MC1, 2026-11-04): Options > Load/Save > Load of a Franchise save, "Successfully
loaded", then backing out of the Load screen stopped the game (bugcheck 0x1E, access violation at EIP 0x142BBD
reading 0x10C). The Franchise Desk callback ([0x521DCC], retail 0x142DD0) loads the club's front-office scene in
0x142BB0, which reads ``user_team+0x10C`` from the user-team getter 0x13EC80 (``mov eax,[0xE3C0A0]``) with no null
check; 164 retail callers of that getter assume it is set. The front-office deserializer 0x2D0CE0 sets it at
0x2D0D53..0x2D0D5A to C4D70(), the first club whose human-control word [0xE5775C + i*4] is set, and stores 0 when the
save has no human club. Retail code throughout; a save made by headless franchise tools has no human club, and so
has a MyCareer career saved while MyPlayer has no club (resolve_team keeps only his club's word).

What this owner adds
--------------------
One five-byte hook at 0x2D0D53 (the deserializer's ``call 0xC4D70``) and a 17-byte code cave: the same call, and
when it finds no human club, the league's club 0 through the game's own team getter 0xC4C50. The user-team pointer is
then never 0 after a load. The human-control table and every club's CPU control stay as the save has them; a save
with a human club loads exactly as before (the cave returns C4D70's own answer).

Allocation: a late owner (appended at the end of ``nfl2k5_xbe_space.LATE_OWNERS``), 32 bytes of code (16-aligned).
It is applied by ``mod_build`` after the other late owners; the full build regenerates the cave reservations.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_load_user_team_guard"
CODE_SIZE = 32
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
FIRST_HUMAN_CLUB = 0x000C4D70   # first club with [0xE5775C + i*4] != 0, else 0
CLUB_BY_INDEX = 0x000C4C50      # the game's own club getter (ECX = league index)
HOOK = ("load_user_team", 0x002D0D53, bytes.fromhex("e81840dfff"))  # call 0xC4D70 (then mov ecx,eax; call 0x13EC90)
BUILD_CAPTION = "Franchise load: no crash on a save without a human club"
HELP_TEXT = ("Fixes a freeze after loading a Franchise save in which no club is human-controlled (made by save tools, "
             "or a MyCareer career saved while MyPlayer had no club): the front office would read address zero when "
             "you leave the Load screen. Such a load now uses the league's first club as the front office's team; "
             "every club's CPU control stays as saved.")
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError)


class LoadUserTeamGuardError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise LoadUserTeamGuardError(message)


def _rel(at: int, target: int) -> bytes:
    rel = target - (at + 5)
    require(-(1 << 31) <= rel < (1 << 31), "call target out of rel32 range")
    return struct.pack("<i", rel)


def code_for(code_va: int) -> bytes:
    """The 17-byte cave, padded with int3 to the 32-byte allocation."""
    body = bytearray()
    body += b"\xe8" + _rel(code_va + len(body), FIRST_HUMAN_CLUB)   # call 0xC4D70
    body += bytes.fromhex("85c0")                                     # test eax,eax
    body += bytes.fromhex("7507")                                     # jnz done
    body += bytes.fromhex("31c9")                                     # xor ecx,ecx
    body += b"\xe8" + _rel(code_va + len(body), CLUB_BY_INDEX)       # call 0xC4C50 (club 0)
    body += b"\xc3"                                                   # done: ret
    require(len(body) == 17, "cave size")
    return bytes(body).ljust(CODE_SIZE, b"\xcc")


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    name, va, before = HOOK
    after = b"\xe8" + _rel(va, code_va)
    require(len(after) == len(before), "hook size")
    return [(name, va, before, after)]


def allocation(payload: bytes) -> dict:
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "missing or foreign load user-team allocation")
    return rows[0]


def _recognize(payload: bytes):
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    edits = sites(owned["va"] if owned else 0)
    state = rdata.status(payload, edits)
    if owned is None:
        require(state == "retail", "the load user-team site changed without an allocation")
        return "retail", None
    code = image.read(owned["va"], CODE_SIZE)
    require(code in (b"\xcc" * CODE_SIZE, code_for(owned["va"])), "foreign load user-team code")
    require(state == ("retail" if code == b"\xcc" * CODE_SIZE else "applied"),
            "mixed load user-team installation")
    return ("retail" if code == b"\xcc" * CODE_SIZE else "applied"), owned


def status(payload: bytes) -> str:
    try:
        return _recognize(payload)[0]
    except _ERRORS:
        return "foreign"


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, "load_user_team_guard": state == "applied"}


def reservations(payload: bytes | None = None) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER] if payload is not None else []
    return rows + [dict(owner=OWNER, start=hex(HOOK[1]), end=hex(HOOK[1] + len(HOOK[2])), size=len(HOOK[2]),
                        basis="pinned live front-office deserializer user-team call; not a cave")]


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the guard and its one site. Idempotent."""
    state, owned = _recognize(payload)
    common = {"owner": OWNER, "code_bytes": 17, "owner_bytes": CODE_SIZE, "experimental": False}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    before = payload
    if owned is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        owned = allocation(payload)
    installed, code_receipt = space.install_code(payload, OWNER, code_for(owned["va"]))
    result, site_receipt = rdata.apply(installed, sites(owned["va"]), OWNER)
    require(status(result) == "applied", "load user-team postcondition failed")
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(owned["va"]), "changed_bytes": sum(a != b for a, b in zip(before, result)),
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "FIRST_HUMAN_CLUB", "CLUB_BY_INDEX", "HOOK", "BUILD_CAPTION", "HELP_TEXT",
           "LoadUserTeamGuardError", "code_for", "sites", "allocation", "status", "read_settings", "reservations",
           "apply"]
