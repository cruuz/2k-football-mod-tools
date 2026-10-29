"""Pre-season roster warning (b779 rc1). EXPERIMENTAL.

Noah, 2026-10-28: tell the user before the regular season that the game will cut his roster to 53. With the franchise
economy (revision 4) the preseason -> regular season gate cuts a user club that is over the in-season limit with the
smart cut-down; this owner warns once beforehand.

When: the Coach's Desk entry (0x142FB0) calls the native automatic advance 0x2486F0 with the screen manager in ECX
(call at 0x143013; the same manager the native gate notices use). That call goes through ``hook``: the automatic
advance runs unchanged first, then, when the franchise is in the preseason (stage 7, 0xE576A4), the current week is
the last preseason week or later (week + 1 >= end, 0xE576B4 / 0xE576B0, so Simulate Preseason in one go is warned too), a user club (0x13EC40 count, 0x13EBE0 club) has
more active players than the in-season limit (the gate's own byte 0x2BF978, 53 with the practice squad), and the
"already warned" byte is clear, the byte is set and the game's notice 0x14E520 shows:
"Cut your roster to 53 before the regular season, or the game will make the cuts for you."
One OK closes it. The byte is cleared every time the desk opens before that week or outside the preseason, so it shows at most once a
preseason. It lives in RAM only (16-byte late RW owner): reloading a save during that week shows it once more.
Nothing shows at the limit or below.

XBE space: code (113 B) and text (178 B) in two retail library functions no byte of the image references
(0x28B330, 0x3BA300; tools/franchise_economy/dead_code.py's scan), pinned by their retail sha256; state: a 16-byte
late RW allocation (``nfl2k5_xbe_space.LATE_OWNERS``, last). One 5-byte call site, 0x143013.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_preseason_warning"
DATA_SIZE = 16
REQUESTS = ((OWNER, "data", DATA_SIZE, 16),)
TEXT = "Cut your roster to 53 before the regular season, or the game will make the cuts for you."
CODE_VA, CODE_SIZE = 0x28B330, 160
TEXT_VA, TEXT_SIZE = 0x3BA300, 208
HOOK_VA = 0x143013
HOOK_RETAIL = bytes.fromhex("e8d8561000")           # call 0x2486F0
PINS = {CODE_VA: "03c516448e230d77ac7d454db379bf22067bb0ad39a8cd9d299de3344d323a11",
        TEXT_VA: "860408fba75941630ffe87ec87020d84c9f5da849294af7df437fe6a723d074b"}
# Assembled from tools/preseason_warning/hook.s (GNU as, origin 0): the flag address 0x11223344, the text address
# 0x55667788 and the four rel32 targets are filled in by code_for().
TEMPLATE = bytes.fromhex(
    "51e8ec86240059833da476e500077559a1b476e500403b05b076e500724b803d44332211007541515356e83cec130089c631db39f373"
    "2e89d9e8dceb13004385c074f08a901c0100003a1578f92b0076e25e5b59c6054433221101ba88776655e91ce514005e5b59c3c605"
    "4433221100c3")
FLAG_AT = (0x20, 0x56, 0x6B)
TEXT_AT = 0x5C
CALLS = ((0x02, 0x2486F0), (0x2B, 0x13EC40), (0x3A, 0x13EBE0), (0x61, 0x14E520))   # rel32 fields


class PreseasonWarningError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise PreseasonWarningError(message)


def text_bytes():
    raw = TEXT.encode("utf-16-le") + b"\0\0"
    require(len(raw) <= TEXT_SIZE, "warning text exceeds its window")
    return raw.ljust(TEXT_SIZE, b"\xcc")


def code_for(flag_va):
    code = bytearray(TEMPLATE)
    for at in FLAG_AT:
        require(struct.unpack_from("<I", code, at)[0] == 0x11223344, "template flag slot")
        struct.pack_into("<I", code, at, flag_va)
    require(struct.unpack_from("<I", code, TEXT_AT)[0] == 0x55667788, "template text slot")
    struct.pack_into("<I", code, TEXT_AT, TEXT_VA)
    for at, target in CALLS:
        struct.pack_into("<i", code, at, target - (CODE_VA + at + 4))
    require(len(code) <= CODE_SIZE, "warning code exceeds its window")
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def hook_bytes():
    return b"\xe8" + struct.pack("<i", CODE_VA - HOOK_VA - 5)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def allocation(payload):
    found = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not found:
        return None
    require(len(found) == 1 and (found[0]["kind"], found[0]["size"]) == ("data", DATA_SIZE),
            "foreign pre-season warning allocation")
    return found[0]


def status(payload):
    try:
        image = XbeImage(payload)
        code, text, hook = image.read(CODE_VA, CODE_SIZE), image.read(TEXT_VA, TEXT_SIZE), image.read(HOOK_VA, 5)
        if sha(code) == PINS[CODE_VA] and sha(text) == PINS[TEXT_VA] and hook == HOOK_RETAIL:
            return "retail"
        owned = allocation(payload)
        require(owned is not None, "pre-season warning code without its state")
        require(code == code_for(owned["va"]) and text == text_bytes() and hook == hook_bytes(),
                "mixed pre-season warning")
        require(image.read(owned["va"], DATA_SIZE) == bytes(DATA_SIZE), "foreign initial pre-season warning state")
        return "applied"
    except (PreseasonWarningError, ValueError, KeyError, struct.error, StopIteration):
        return "foreign"


def seal(out):
    for section in _sections(out):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(out, section)
    return bytes(out)


def apply(payload):
    initial = status(payload)
    require(initial != "foreign", "foreign pre-season warning installation; rebuild from base")
    if initial == "applied":
        return payload, dict(status="already_applied", changed_bytes=0)
    before = payload
    if allocation(payload) is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "the pre-season warning needs the scale-out allocator")
            payload, _ = space.extend_scaleout(payload, REQUESTS)
    allocated, owned = payload, allocation(payload)
    out, image = bytearray(payload), XbeImage(payload)
    for va, raw in ((CODE_VA, code_for(owned["va"])), (TEXT_VA, text_bytes()), (HOOK_VA, hook_bytes())):
        at = image.offset(va, len(raw))
        out[at:at + len(raw)] = raw
    result = seal(out)
    require(status(result) == "applied" and space.status(result) == "applied", "pre-season warning readback")
    require(len(result) == len(allocated), "pre-season warning grew the XBE beyond its allocation")
    return result, dict(status="applied", changed_bytes=space.count_differing_bytes(before, result),
                        state_va=owned["va"], code_va=CODE_VA, text_va=TEXT_VA, hook_va=HOOK_VA,
                        requests=dict(code=0, data=DATA_SIZE, read_only=0))


__all__ = ["OWNER", "REQUESTS", "TEXT", "apply", "status", "code_for", "allocation"]
