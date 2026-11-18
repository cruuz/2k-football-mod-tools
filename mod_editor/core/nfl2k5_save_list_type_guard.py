"""Validate Xbox save-directory names and types while building the title-screen save list.

The first guard handled null pointers. A renamed, imported save can also return
a nonzero invalid pointer. The native reader checks the title's existing memory
protection API as it crosses each page and bounds the UTF-16 name. The listing
uses an empty name or type for an unreadable entry. This runs once per save
during enumeration and never changes the user's save or the game allocator.
"""
from __future__ import annotations

import struct

from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_save_list_type_guard"
REVISION = 2
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


# The eight aligned RET instructions remain live game entry points. Only their
# following padding is owned here. See tools/nfl2k5_save_list_guard.S.
PAD_BASE = 0x294960
PROTECT_IMPORT = 0x4E3BA0
PAD_BODIES = (
    "515231d2f6c101754785c97e43eb01",
    "515251ff15a03b4e005a59eb039090",
    "f6c401752ba8ee7427eb0590909090",
    "66833900741c80fa807315eb039090",
    "4283c10266f7c1ff0f74c5ebe39090",
    "31d289d05a59c39090909090909090",
    "89f9e899ffffff85c07505c3909090",
    "5631f6e9375cedff90909090909090",
)
BETA80_SITES = _build_sites()
_type_hook, _type_pad, _name_hook, _name_pad = BETA80_SITES


def _reader_jump(site, target):
    label, va, before, _ = site
    after = (b"\xe9" + _rel(va, target)).ljust(len(before), b"\x90")
    return label, va, before, after


SITES = (_type_hook, _reader_jump(_type_pad, PAD_BASE + 0x61),
         _name_hook, _reader_jump(_name_pad, PAD_BASE + 1)) + tuple(
    (f"checked UTF-16 reader, span {index + 1}", PAD_BASE + index * 16 + 1,
     b"\x90" * 15, bytes.fromhex(body)) for index, body in enumerate(PAD_BODIES))
_prior_bytes = {va: after for _label, va, _before, after in BETA80_SITES}
UPGRADE_SITES = tuple(
    (label, va, _prior_bytes.get(va, before), after)
    for label, va, before, after in SITES if _prior_bytes.get(va, before) != after
)
# These fixed dependencies are read-only. The user may supply an already modified executable.
READER_DEPENDENCIES = (("MmQueryAddressProtect import", PROTECT_IMPORT, struct.pack("<I", 0x800000B3)),) + tuple(
    (f"preserved game return {index}", PAD_BASE + index * 16, b"\xc3") for index in range(len(PAD_BODIES))
)


def status(payload: bytes) -> str:
    if rdata.status(payload, [(name, va, expected, expected) for name, va, expected in READER_DEPENDENCIES]) != "retail":
        return "foreign"
    state = rdata.status(payload, SITES)
    if (state == "foreign" and rdata.status(payload, BETA80_SITES) == "applied"
            and rdata.status(payload, SITES[4:]) == "retail"):
        return "previous"
    return state


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, "save_list_type_guard": state == "applied"}


def apply(payload: bytes):
    """(patched payload, receipt). Idempotent; anything neither retail nor applied is refused."""
    state = status(payload)
    if state == "foreign":
        raise ValueError("the boot save-list type guard: the matcher or its padding is not retail")
    patched, receipt = rdata.apply(payload, UPGRADE_SITES if state == "previous" else SITES, "boot save-list type guard")
    return patched, {**receipt, "revision": REVISION, "code_bytes": sum(len(row[3]) for row in SITES)}


def verify(payload: bytes) -> dict:
    return {"owner": OWNER, "status": status(payload),
            "sites": [{"label": s[0], "va": f"0x{s[1]:x}"} for s in SITES],
            "experimental": False, "runtime_witnessed": True}


__all__ = ["OWNER", "REVISION", "SITES", "MATCH_FN", "MATCH_BODY", "CAVE_VA", "NAME_CALL", "NAME_FN", "CAVE2_VA",
           "BUILD_CAPTION", "HELP_TEXT", "status", "read_settings", "apply", "verify"]
