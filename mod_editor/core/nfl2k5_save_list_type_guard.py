"""Boot save list: a saved game whose stored name or type string is absent no longer stops the game at the title.

Report (b780 EMU1 crash_boot, triage MC1, corrected 2026-11-04): on the v0.9 final candidate, and identically on the
released v0.8, the title screen stopped while the boot save browser built its list (bugcheck 0x1E). The trigger is a
saved game whose stored name does not match its save folder id (the folder id is derived from the name). The save-list
entry builder 0x16AC40 copies the enumerated record's fields and dereferences two of them:

* its type string, at 0x16A600 via the wide-string compare 0x30C40 (``mov ecx,edi`` at 0x16A617; faults with ECX = 0);
* its name string, at the wide-string length 0x30A60 called from 0x16AD0D (``cmp word ptr [ecx], 0`` with ECX = 0).

When the name and folder id disagree the resolve leaves one of those pointers NULL, and whichever the builder reaches
first faults. All callers assume non-NULL strings.

Reachability: the game derives the folder id from the save name, so a save the game writes always matches, including a
cut free-agent MyCareer save, which does NOT crash. The mismatch comes from saves copied or renamed outside the game,
or produced by save tools (the IR1 witness and GEN1 show saves are named out of step with their folders).

What this owner changes (in place: no allocation, no section, nothing at 64 MB)
-------------------------------------------------------------------------------
Two call sites in the one builder are made NULL-safe, each through a routine in retail .text alignment padding
(0x90 runs before the next function; nothing falls through or jumps into them):

* 0x16A600's five-byte prologue (``push esi; xor esi,esi; jmp 0x16A610``) jumps to a 15-byte routine at 0x160771 that
  returns 0 (no type match, the builder's own default) when the type string (EDI) is NULL, else runs the displaced
  prologue and continues into 0x16A610.
* 0x16AD0D's ``call 0x30A60`` (the name length) goes to a 12-byte routine at 0x160354 that returns 0 (empty name) when
  the name string (ECX) is NULL, else tail-calls 0x30A60.

Every save whose name and type resolve lists exactly as before (both routines run the same bytes and reach the same
code); a save with a NULL name or type is listed untyped or unnamed instead of stopping the game.
"""
from __future__ import annotations

import struct

from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_save_list_type_guard"
REVISION = 1
MATCH_FN = 0x0016A600            # the save-type matcher whose prologue is redirected
MATCH_BODY = 0x0016A610          # where the matcher's loop continues after the prologue
CAVE_VA = 0x00160771            # 15 bytes of retail .text alignment padding (type guard)
RETAIL_PROLOGUE = bytes.fromhex("5633f6eb0b")   # push esi; xor esi,esi; jmp 0x16A610
RETAIL_CAVE = b"\x90" * 15
NAME_CALL = 0x0016AD0D           # the builder's `call 0x30A60` (name length) that is redirected
NAME_FN = 0x00030A60             # the wide-string length helper (reads [ecx])
CAVE2_VA = 0x00160354           # 12 bytes of retail .text alignment padding (name guard)
RETAIL_NAME_CALL = bytes.fromhex("e84e5decff")  # call 0x30A60
RETAIL_CAVE2 = b"\x90" * 12
BUILD_CAPTION = "Boot save list: no freeze on a save with a bad name"
HELP_TEXT = ("Fixes a freeze at the title screen while the game lists saved games, when a save's stored name or type "
             "does not match its save folder (a save copied in or renamed outside the game, or made by save tools). "
             "Such a save is now listed with an empty name or untyped instead of stopping the game; every other save "
             "lists as before.")


def _rel(at: int, target: int, size: int = 5) -> bytes:
    return struct.pack("<i", target - (at + size))


def _build_sites():
    cave = bytearray()
    cave += bytes.fromhex("85ff")                      # test edi,edi
    cave += bytes.fromhex("7408")                      # jz null (+8)
    cave += bytes.fromhex("56")                        # push esi
    cave += bytes.fromhex("33f6")                      # xor esi,esi
    cave += b"\xe9" + _rel(CAVE_VA + len(cave), MATCH_BODY)   # jmp 0x16A610
    cave += bytes.fromhex("31c0")                      # null: xor eax,eax
    cave += b"\xc3"                                     # ret
    assert len(cave) == 15, len(cave)
    hook = b"\xe9" + _rel(MATCH_FN, CAVE_VA)           # jmp cave (5 bytes, over the retail prologue)
    assert len(hook) == len(RETAIL_PROLOGUE)
    cave2 = bytearray()
    cave2 += bytes.fromhex("85c9")                     # test ecx,ecx
    cave2 += bytes.fromhex("7405")                     # jz null (+5)
    cave2 += b"\xe9" + _rel(CAVE2_VA + len(cave2), NAME_FN)   # jmp 0x30A60
    cave2 += bytes.fromhex("31c0")                     # null: xor eax,eax
    cave2 += b"\xc3"                                    # ret
    assert len(cave2) == 12, len(cave2)
    name_hook = b"\xe8" + _rel(NAME_CALL, CAVE2_VA)    # call cave2 (5 bytes, over the retail call)
    assert len(name_hook) == len(RETAIL_NAME_CALL)
    return (("save matcher prologue goes through the type NULL guard", MATCH_FN, RETAIL_PROLOGUE, bytes(hook)),
            ("NULL save-type guard in the matcher's alignment padding", CAVE_VA, RETAIL_CAVE, bytes(cave)),
            ("save name-length call goes through the name NULL guard", NAME_CALL, RETAIL_NAME_CALL, bytes(name_hook)),
            ("NULL save-name guard in .text alignment padding", CAVE2_VA, RETAIL_CAVE2, bytes(cave2)))


SITES = _build_sites()


def status(payload: bytes) -> str:
    """``retail`` | ``applied`` | ``foreign``."""
    return rdata.status(payload, SITES)


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, "save_list_type_guard": state == "applied"}


def apply(payload: bytes):
    """(patched payload, receipt). Idempotent; anything neither retail nor applied is refused."""
    state = status(payload)
    if state == "foreign":
        raise ValueError("the boot save-list type guard: the matcher or its padding is not retail")
    patched, receipt = rdata.apply(payload, SITES, "boot save-list type guard")
    return patched, {**receipt, "revision": REVISION, "code_bytes": 15}


def verify(payload: bytes) -> dict:
    return {"owner": OWNER, "status": status(payload),
            "sites": [{"label": s[0], "va": f"0x{s[1]:x}"} for s in SITES],
            "experimental": False, "runtime_witnessed": False}


__all__ = ["OWNER", "REVISION", "SITES", "MATCH_FN", "MATCH_BODY", "CAVE_VA", "NAME_CALL", "NAME_FN", "CAVE2_VA",
           "BUILD_CAPTION", "HELP_TEXT", "status", "read_settings", "apply", "verify"]
