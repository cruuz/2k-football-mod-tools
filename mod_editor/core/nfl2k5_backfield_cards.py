"""Use the current QB, halfback and fullback depth lists for the pregame Backfield cards."""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_rdata_sites as sites
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = space.BACKFIELD_REQUEST[0]
CODE_SIZE = space.BACKFIELD_REQUEST[2]
BUILD_CAPTION = "Starting backfield cards"
HELP_TEXT = ("Show the current quarterback, running back and fullback in Coach Matchup’s "
             "Player Lineup. The cards show the players the game selects for those positions.")
REQUESTS = space.GADGET_REQUESTS + (space.BACKFIELD_REQUEST,)
SITE = 0x34C6B0
ORIGINAL_HANDLER = 0x34C273
RETURN = 0x34C6A4
RETAIL = struct.pack("<I", ORIGINAL_HANDLER)
ROSTER_CONTEXT_SIZE = 0x334

# Pin the stock dispatch, including the continuation shared with other tabs, and
# the native entry points this code calls. Other owners can extend the rank builder.
DISPATCH = 0x34C250
DISPATCH_BYTES = 0x34C6C8 - DISPATCH
DISPATCH_SHA256 = "02735e58f109ece07bada1c0ae3fd5db91db307a99f13052c5761b22a0bf9a5a"
GUARDS = (
    (0x34B7C0, 73, "00975e850a0e1e00eb871d32f84a265a1dbb69bab3b9312d19ccaf6d8c231259"),
    (0xE80D0, 31, "aeaaf12b4bdd9e0ec898171b565a800a7531e859ebc03deae3e43c20a3003e18"),
    (0xE75A0, 20, "5eb2036e65b118b4005edf0235b9d02bb8c496017c91013446f36f898073689b"),
    (0xE7810, 16, "26242a2c407cfea24d68652353f7513c3b8a64d4b22fe2ee3a4fe7c2747ddf48"),
)


def code_for(va: int) -> bytes:
    a = _Asm(va)
    a.b("9c 833d587cae0000")            # Preserve flags across the special-mode dispatch.
    a.j8("74", "lineup")
    a.b("9d")
    a.jmp_abs(ORIGINAL_HANDLER)
    a.label("lineup")
    a.b("51 52 57")                    # Native caller already saved ESI and EBP.
    a.b("81ec" + struct.pack("<I", ROSTER_CONTEXT_SIZE).hex())
    a.b("89e7 6a00 6a00 89fa 89d9")    # EDI = temporary rank context, EBX = copied club.
    a.call(0xE80D0)
    a.b("31f6")                        # ESI is the number of cards already accepted by the emitter.
    for position, ordinal in ((0, 0), (1, 0), (2, 0), (1, 1), (2, 1)):
        if ordinal:
            a.b("83fe03")
            a.j8("74", "done")
        a.b(f"6a{position:02x} 59 6a{ordinal:02x} 58")
        a.j32("e8", "add_rank")
    a.label("done")
    a.b("89f0 81c4" + struct.pack("<I", ROSTER_CONTEXT_SIZE).hex())
    a.b("5f 5a 59 9d")                 # Return the count in EAX, restore other caller registers.
    a.jmp_abs(RETURN)

    # ECX = list index, EAX = ordinal. Validate the ordinal before E7810 reads
    # the packed rank array. E7810's ECX=0 path reads this club's ranked player.
    a.label("add_rank")
    a.b("50 51 89fa")
    a.call(0xE75A0)
    a.b("8b4c2404 39c8")               # Has the list at least ordinal + one entries?
    a.j8("7e", "skip")
    a.b("51 57 8b442408 31c9")         # E7810(list in EAX, 0, context, ordinal), callee pops 8.
    a.call(0xE7810)
    a.b("53 89c2 89e9 89f0")           # 34B7C0(count, side, player, copied club), callee pops 4.
    a.call(0x34B7C0)
    a.b("89c6")
    a.label("skip")
    a.b("83c408 c3")
    code = a.assemble()
    if len(code) > CODE_SIZE:
        raise ValueError("Backfield card code exceeds its allocation")
    return code.ljust(CODE_SIZE, b"\xcc")


def _allocation(payload: bytes):
    state = space.status(payload)
    if state == "retail":
        return None
    if state != "applied":
        raise ValueError("Unrecognized executable allocation layout")
    entries = [row for row in space.layout(payload)["allocations"] if row["owner"] == OWNER]
    if not entries:
        return None
    if len(entries) != 1 or (entries[0]["kind"], entries[0]["size"], entries[0]["align"], entries[0]["va"]) != (
            "code", CODE_SIZE, 16, space.BACKFIELD_VA):
        raise ValueError("Incompatible Backfield card allocation")
    return entries[0]


def status(payload: bytes) -> str:
    try:
        image = XbeImage(payload)
        dispatch = bytearray(image.read(DISPATCH, DISPATCH_BYTES))
        current = bytes(dispatch[SITE - DISPATCH:SITE - DISPATCH + 4])
        dispatch[SITE - DISPATCH:SITE - DISPATCH + 4] = RETAIL
        if hashlib.sha256(dispatch).hexdigest() != DISPATCH_SHA256:
            return "foreign"
        if any(hashlib.sha256(image.read(va, size)).hexdigest() != pin for va, size, pin in GUARDS):
            return "foreign"
        allocation = _allocation(payload)
        if allocation is None:
            return "retail" if current == RETAIL else "foreign"
        va = allocation["va"]
        installed = image.read(va, CODE_SIZE)
        if current == RETAIL and installed == b"\xcc" * CODE_SIZE:
            return "retail"
        return "applied" if current == struct.pack("<I", va) and installed == code_for(va) else "foreign"
    except (KeyError, ValueError, IndexError, struct.error):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict]:
    state = status(payload)
    if state == "applied":
        return payload, {"owner": OWNER, "already_applied": True, "changed_bytes": 0}
    if state != "retail":
        raise ValueError("The Player Lineup dispatch or Backfield card code has unrecognized bytes")
    before = payload
    allocation = _allocation(payload)
    if allocation is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            existing = {(r["owner"], r["kind"]) for r in space.layout(payload)["allocations"]}
            missing = [r for r in REQUESTS if r[:2] not in existing]
            payload, _ = space.extend_scaleout(payload, missing)
        allocation = _allocation(payload)
    va = allocation["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(va))
    result, receipt = sites.apply(payload, [("backfield_cards", SITE, RETAIL, struct.pack("<I", va))], OWNER)
    if status(result) != "applied":
        raise ValueError("Starting backfield cards did not verify")
    return result, {**receipt, "owner": OWNER, "code_va": hex(va), "already_applied": False,
                    "changed_bytes": space.count_differing_bytes(before, result)}
