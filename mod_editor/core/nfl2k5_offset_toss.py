"""Keep the carrier and the exchange together when flipping an offset shotgun pitch.

The stock R3 handler passes event 0x12 to the offense at 0x18DCB0. It mirrors the
exchange while leaving the players where they stood. Black sends 0x13, which
also mirrors the formation. A verified three-node QB pitch to a back already
aligned with his outside lane uses that same full-play event for R3. The
original no-route-flip bit also means "reverse" in the CPU's run lottery, so
nothing changes in the PLAY headers or the CPU's calls.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_rdata_sites as sites, nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_offset_toss"
CODE_SIZE = 176
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
SITE = 0x18DCF7
RETAIL = bytes.fromhex("f6c510750d")
DISPATCH = 0x18DCB0
DISPATCH_SHA256 = "05672291302d009d0384f22d059558b8dfea0d8a86b8db900e92026cfc95cc33"
PANEL_SHA256 = "db87ab35b7a8dfe3e0c802bfe93a74a85fac3626926207493aa2f6923ef76ee4"


def code_for(va: int) -> bytes:
    a = _Asm(va)
    a.b("f6c510")                          # Stock reverse or other route-flip lock.
    a.j8("74", "allowed")
    a.jmp_abs(0x18DD09)
    a.label("allowed")
    a.b("f6c580")                          # Offensive run flag. EDX is the current native play.
    a.j32("0f84", "normal")
    a.b("8a4208 240f 3c03")                # Only the three-node QB Start / Snap / Handoff To.
    a.j32("0f85", "normal")
    a.b("8b420c 803801")
    a.j8("75", "normal")
    a.b("80780803")
    a.j8("75", "normal")
    a.b("80781013")
    a.j8("75", "normal")
    a.b("0fb64814 83e911 83f909")          # Pitch type 1 to slot 1..10.
    a.j8("77", "normal")
    a.b("41 8a44ca08 240f 3c02")           # Receiver has a second node.
    a.j8("72", "normal")
    a.b("8b44ca0c 80780816")               # Take Handoff names one of the two outside holes.
    a.j8("75", "normal")
    a.b("0fb6500f 83e2f0 83fa10")
    a.j8("74", "geometry")
    a.b("81fa80000000")
    a.j8("75", "normal")
    a.label("geometry")                    # Native unmirrored formation geometry (signed centimetres).
    a.b("8b4638 8b400c 8b4008 6681782206ff")  # QB depth below -250 cm.
    a.j8("7d", "normal")
    a.b("6bc90e 0fbf4c081c 0fbf401c 29c1")  # Back x minus QB x.
    a.b("83fa10")                          # Hole 1 at +533 cm; hole 8 at -533 cm.
    a.j8("74", "positive")
    a.b("f7d9")
    a.label("positive")
    a.b("83f924")                          # Only when the carrier is already on his own lane's side.
    a.j8("7e", "normal")
    a.b("6a00 8bce 6a13 5a 6a00")          # Same event & arguments as Black; preserve EDI.
    a.jmp_abs(0x18DD04)
    a.label("normal")
    a.jmp_abs(0x18DCFC)                    # Stock Flip Routes.
    code = a.assemble()
    if len(code) > CODE_SIZE:
        raise ValueError("The offset toss control exceeds its reserved executable space")
    return code.ljust(CODE_SIZE, b"\xcc")


def _allocation(payload):
    if space.status(payload) != "applied":
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if rows and (len(rows) != 1 or (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) != ("code", CODE_SIZE, 16)):
        raise ValueError("Incompatible offset toss allocation")
    return rows[0] if rows else None


def _site(va):
    return ("offset_toss_flip", SITE, RETAIL, b"\xe9" + struct.pack("<i", va - SITE - 5))


def status(payload: bytes) -> str:
    try:
        img = XbeImage(payload)
        allocation = _allocation(payload)
        current = img.read(SITE, 5)
        context = bytearray(img.read(DISPATCH, 0x5a))
        context[SITE-DISPATCH:SITE-DISPATCH+5] = RETAIL
        if (hashlib.sha256(context).hexdigest() != DISPATCH_SHA256 or
                hashlib.sha256(img.read(0x18FA20, 0x9f)).hexdigest() != PANEL_SHA256):
            return "foreign"
        if allocation is None:
            return "retail" if current == RETAIL else "foreign"
        va = allocation["va"]
        code = img.read(va, CODE_SIZE)
        if current == RETAIL and code == bytes([0xcc]) * CODE_SIZE:
            return "retail"
        return "applied" if current == _site(va)[3] and code == code_for(va) else "foreign"
    except (ValueError, struct.error, KeyError, IndexError):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict]:
    state = status(payload)
    if state == "applied":
        return payload, {"owner": OWNER, "already_applied": True, "changed_bytes": 0}
    if state != "retail":
        raise ValueError("The current play-flip handler or its offset toss code has unrecognized bytes")
    before = payload
    allocation = _allocation(payload)
    if allocation is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        allocation = _allocation(payload)
    va = allocation["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(va))
    result, receipt = sites.apply(payload, [_site(va)], OWNER)
    if status(result) != "applied":
        raise ValueError("The new offset toss control did not verify")
    return result, {**receipt, "owner": OWNER, "already_applied": False, "code_va": hex(va),
                    "changed_bytes": space.count_differing_bytes(before, result)}
