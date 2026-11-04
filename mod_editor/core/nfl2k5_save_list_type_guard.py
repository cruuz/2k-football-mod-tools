"""Boot save list: a saved game whose stored type string is absent no longer stops the game at the title (USA retail).

Report (b780 EMU1 crash_boot, triage MC1, 2026-11-04): on the v0.9 final candidate, and identically on the released
v0.8, the title screen stopped (bugcheck 0x1E, access violation at 0x30C40 with ECX = 0) while the boot save browser
built its list. The save-type matcher 0x16A600 walks the 14 type names at 0xAA3398 and for each calls the wide-string
compare 0x30C40 with ECX = the enumerated save's type string (``mov ecx,edi`` at 0x16A617). When that string pointer
is 0 the compare dereferences address 0. The entry builder 0x16AC40 passes it as EDI from the enumerated slot; all six
callers of 0x16A600 assume a non-NULL string.

A real save reaches it. The crash needs a save with no human-controlled club ([0xE5775C + i*4] all 0) that also
carries the modern injured-reserve extension (b780 IR1). resolve_team clears the whole 34-word human table and, for a
free agent (career club S(56) = -1), skips the set, so a released MyPlayer's autosave has no human club; if he played
any week under the pack's modern injured reserve the save already carries the IR extension. A MyPlayer cut mid-season,
then autosaved on returning to Career Home, is exactly that save. Headless franchise tools produce the same state.

What this owner changes (in place: no allocation, no section, nothing at 64 MB)
-------------------------------------------------------------------------------
0x16A600's first five bytes (``push esi; xor esi,esi; jmp 0x16A610``) jump to a 15-byte routine written into the
retail alignment padding at 0x160771 (fifteen 0x90 bytes before the next function; nothing falls through or jumps into
it). The routine returns 0 (no type match, the safe default the builder already handles) when the string is NULL, and
otherwise runs the exact displaced instructions and continues into 0x16A610::

    160771  test edi, edi
    160773  jz   160780
    160775  push esi            ; the displaced retail prologue
    160776  xor  esi, esi
    160778  jmp  0x16A610       ; the matcher's own loop, unchanged
    160780  xor  eax, eax       ; NULL type string: no match
    160782  ret

Every save with a type string lists exactly as before (the routine runs the same bytes and reaches the same loop); a
save whose type string is absent is listed untyped instead of stopping the game. This protects all six callers.
"""
from __future__ import annotations

import struct

from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_save_list_type_guard"
REVISION = 1
MATCH_FN = 0x0016A600            # the save-type matcher whose prologue is redirected
MATCH_BODY = 0x0016A610          # where the matcher's loop continues after the prologue
CAVE_VA = 0x00160771            # 15 bytes of retail .text alignment padding
RETAIL_PROLOGUE = bytes.fromhex("5633f6eb0b")   # push esi; xor esi,esi; jmp 0x16A610
RETAIL_CAVE = b"\x90" * 15
BUILD_CAPTION = "Boot save list: no freeze on a save with no type"
HELP_TEXT = ("Fixes a freeze at the title screen while the game lists saved games, when a save has no stored type "
             "(a franchise or MyCareer save made with no human-controlled club, from save tools or a MyPlayer who was "
             "released). Such a save is now listed untyped instead of stopping the game; every other save lists as "
             "before.")


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
    return (("save matcher prologue goes through the NULL guard", MATCH_FN, RETAIL_PROLOGUE, bytes(hook)),
            ("NULL save-type guard in the matcher's alignment padding", CAVE_VA, RETAIL_CAVE, bytes(cave)))


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


__all__ = ["OWNER", "REVISION", "SITES", "MATCH_FN", "MATCH_BODY", "CAVE_VA",
           "BUILD_CAPTION", "HELP_TEXT", "status", "read_settings", "apply", "verify"]
