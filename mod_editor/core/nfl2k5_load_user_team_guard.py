"""Restore the front-office club and each human club's saved coaching gameplan on franchise load.

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

Revision 2 also corrects the registration of the saved 36-byte coaching rows. The menu and fresh
franchise index these rows by club. The loader used the ordinal in the human-club list instead.
At 0x2D0DB6 EAX contains the resolved club index and EDI the physical table base. The revised
loop passes base + 36 * club to the same setter. ESI still counts human clubs. The following
code replaces EDI at 0x2D0EA3 before using it. Neither the save format nor the CPU control table changes.
"""
from __future__ import annotations

import struct

from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_load_user_team_guard"
REVISION = 2
FIRST_HUMAN_CLUB = 0x000C4D70   # first club with [0xE5775C + i*4] != 0, else 0
CLUB_BY_INDEX = 0x000C4C50      # the game's own club getter (ECX = league index)
SITE_VA = 0x002D0D53            # call 0xC4D70 (then mov ecx,eax; call 0x13EC90)
HEAD_VA, TAIL_VA = 0x0013EC86, 0x0013EC97
PLAN_SITE_VA = 0x002D0DB6
PLAN_SETTER_VA = 0x000C6D00
BUILD_CAPTION = "Franchise load and saved coaching gameplans"
HELP_TEXT = ("Reload each human club’s own coaching gameplan, including in shared franchises. "
             "A save with no human-controlled club opens the front office using the league’s first club. "
             "Teams keep their saved CPU or human control.")


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


SITES_V1 = _build_sites()
# imul edx,eax,36 / add edx,edi / mov ecx,eax / call setter / inc esi
PLAN_SITE = ("Register the saved coaching gameplan by club", PLAN_SITE_VA,
             bytes.fromhex("8bd78bc8e8415fdfff4683c724"),
             bytes.fromhex("6bd02403d78bc8e8") + _rel(PLAN_SITE_VA + 7, PLAN_SETTER_VA) + b"\x46")
SITES = SITES_V1 + (PLAN_SITE,)
NEIGHBOURS = (
    (0x13EC80, bytes.fromhex("a1a0c0e300c3")),    # user-team getter
    (0x13EC90, bytes.fromhex("890da0c0e300c3")),  # user-team setter
    (0x2D0D98, bytes.fromhex("33f6e8a1dee6ff85c07e29bfe01ce4008bcee831dee6ff8bc8e8ea3edfff")),
    (0x2D0DC3, bytes.fromhex("e878dee6ff3bf07cdc")),  # count, compare and loop back
    (PLAN_SETTER_VA, bytes.fromhex("89148d68a2e500c3")),  # table[ECX] = EDX
)
_GUARDS = tuple(("franchise load context", va, raw, raw) for va, raw in NEIGHBOURS)


def status(payload: bytes) -> str:
    """Recognize the unmodified loader, complete first revision and complete current revision."""
    if rdata.status(payload, _GUARDS) != "retail":
        return "foreign"
    states = rdata.status(payload, SITES_V1), rdata.status(payload, (PLAN_SITE,))
    return {("retail", "retail"): "retail", ("applied", "retail"): "previous",
            ("applied", "applied"): "applied"}.get(states, "foreign")


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, "load_user_team_guard": state in ("previous", "applied")}


def apply(payload: bytes):
    state = status(payload)
    if state == "foreign":
        raise rdata.RdataSiteError("Unrecognized franchise load instructions or coaching gameplan registration.")
    sites = (PLAN_SITE,) if state == "previous" else SITES
    patched, receipt = rdata.apply(payload, sites, "Franchise load and saved coaching gameplans")
    if state == "previous":
        receipt = {**receipt, "upgraded_from": 1}
    return patched, {**receipt, "revision": REVISION, "code_bytes": 17, "gameplan_instruction_bytes": len(PLAN_SITE[3])}


def verify(payload: bytes) -> dict:
    return {"owner": OWNER, "status": status(payload), "sites": [{"label": s[0], "va": f"0x{s[1]:x}"} for s in SITES],
            "experimental": False, "runtime_witnessed": False}


__all__ = ["OWNER", "REVISION", "SITES", "SITES_V1", "PLAN_SITE", "SITE_VA", "HEAD_VA", "TAIL_VA", "FIRST_HUMAN_CLUB", "CLUB_BY_INDEX",
           "BUILD_CAPTION", "HELP_TEXT", "status", "read_settings", "apply", "verify"]
