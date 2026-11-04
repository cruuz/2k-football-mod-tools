"""Franchise load: a save with no human-controlled club no longer crashes the Desk (USA retail, xemu-safe).

Report (b780 EMU1 crash_load, triage MC1, 2026-11-04): Options > Load/Save > Load of a Franchise save, "Successfully
loaded", then backing out of the Load screen stopped the game (bugcheck 0x1E, access violation at EIP 0x142BBD
reading 0x10C). The Franchise Desk callback ([0x521DCC], retail 0x142DD0) loads the club's front-office scene in
0x142BB0, which reads ``user_team+0x10C`` from the user-team getter 0x13EC80 (``mov eax,[0xE3C0A0]``) with no null
check; 164 retail callers of that getter assume it is set. The front-office deserializer 0x2D0CE0 sets it at
0x2D0D53..0x2D0D5E to C4D70(), the first club whose human-control word [0xE5775C + i*4] is set, and stores 0 when the
save has no human club. Retail code throughout; a save made by headless franchise tools has no human club, and so
has a MyCareer career saved while MyPlayer has no club (resolve_team keeps only his club's word).

What this owner changes (in place: no allocation, no section, nothing at 64 MB)
-------------------------------------------------------------------------------
The deserializer's ``call 0xC4D70`` at 0x2D0D53 calls a 17-byte routine written into the retail alignment padding
around the user-team accessors (the 10 bytes 0x13EC86..0x13EC8F after the getter's ``ret`` and 7 of the 9 bytes
0x13EC97..0x13EC9F after the setter's ``ret``; nothing falls through or jumps into either run)::

    13EC86  call 0xC4D70        ; the first human club, as before
    13EC8B  test eax, eax
    13EC8D  jz   13EC97
    13EC8F  ret                 ; a human club: its own answer (the setter at 0x13EC90 is untouched)
    13EC97  xor  ecx, ecx
    13EC99  jmp  0xC4C50        ; no human club: club 0 through the game's own team getter

The user-team pointer is then never 0 after a load. The human-control table and every club's CPU control stay as the
save has them; a save with a human club loads exactly as before.
"""
from __future__ import annotations

import struct

from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_load_user_team_guard"
REVISION = 1
FIRST_HUMAN_CLUB = 0x000C4D70   # first club with [0xE5775C + i*4] != 0, else 0
CLUB_BY_INDEX = 0x000C4C50      # the game's own club getter (ECX = league index)
SITE_VA = 0x002D0D53            # call 0xC4D70 (then mov ecx,eax; call 0x13EC90)
HEAD_VA, TAIL_VA = 0x0013EC86, 0x0013EC97
BUILD_CAPTION = "Franchise load: no crash on a save without a human club"
HELP_TEXT = ("Fixes a freeze after loading a Franchise save in which no club is human-controlled (made by save tools, "
             "or a MyCareer career saved while MyPlayer had no club): the front office would read address zero when "
             "you leave the Load screen. Such a load now uses the league's first club as the front office's team; "
             "every club's CPU control stays as saved.")


def _rel(at: int, target: int, size: int = 5) -> bytes:
    return struct.pack("<i", target - (at + size))


def _build_sites():
    head = b"\xe8" + _rel(HEAD_VA, FIRST_HUMAN_CLUB) + bytes.fromhex("85c0") + b"\x74" \
        + bytes([TAIL_VA - (HEAD_VA + 9)]) + b"\xc3"
    tail = bytes.fromhex("31c9") + b"\xe9" + _rel(TAIL_VA + 2, CLUB_BY_INDEX) + b"\x90\x90"
    assert len(head) == 10 and len(tail) == 9
    return (("front-office load: the user-team call goes through the guard", SITE_VA,
             bytes.fromhex("e81840dfff"), b"\xe8" + _rel(SITE_VA, HEAD_VA)),
            ("guard head in the getter's alignment padding", HEAD_VA, b"\x90" * 10, head),
            ("guard tail in the setter's alignment padding", TAIL_VA, b"\x90" * 9, tail))


SITES = _build_sites()
#: the accessors the padding sits between (getter, setter), pinned so a build that moved them is refused
NEIGHBOURS = ((0x13EC80, bytes.fromhex("a1a0c0e300c3")), (0x13EC90, bytes.fromhex("890da0c0e300c3")))


def status(payload: bytes) -> str:
    """``retail`` | ``applied`` | ``foreign``."""
    state = rdata.status(payload, SITES)
    if state == "foreign":
        return state
    if rdata.status(payload, tuple(("accessor", va, raw, raw) for va, raw in NEIGHBOURS)) != "retail":
        return "foreign"
    return state


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, "load_user_team_guard": state == "applied"}


def apply(payload: bytes):
    """(patched payload, receipt). Idempotent; anything neither retail nor applied is refused."""
    state = status(payload)
    if state == "foreign":
        raise ValueError("the Franchise load user-team guard: the site or its padding is not retail")
    patched, receipt = rdata.apply(payload, SITES, "Franchise load user-team guard")
    return patched, {**receipt, "revision": REVISION, "code_bytes": 17}


def verify(payload: bytes) -> dict:
    return {"owner": OWNER, "status": status(payload), "sites": [{"label": s[0], "va": f"0x{s[1]:x}"} for s in SITES],
            "experimental": False, "runtime_witnessed": False}


__all__ = ["OWNER", "REVISION", "SITES", "SITE_VA", "HEAD_VA", "TAIL_VA", "FIRST_HUMAN_CLUB", "CLUB_BY_INDEX",
           "BUILD_CAPTION", "HELP_TEXT", "status", "read_settings", "apply", "verify"]
