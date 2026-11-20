"""Quarterback trades page for the standard 128 MiB franchise (beta 81 stage 4b; owner nfl2k5_qb_trades; DESIGN_CHANGES
C20). It is part of the quarterback room's option: the room's stage bit 16 installs it, and only through the room owner
(nfl2k5_qb_room.install_stages; the Studio's Realistic set does not include bit 16 until the panels pass).

One fixed page at 0x152C000 (nfl2k5_xbe_space.QB_TRADES_*), right after the room's three pages, holds the native code
(nfl2k5_qb_trades_code) and one link word (the IR owner's store). One whole 5-byte call enters it: 0x247E1E, the weekly
advance's stage-8 `call 0x2BC960` (the native trade pass), reached only while the native trade window is open. The page
reads the room's settings and writes the room's ring and counters at the room's fixed offsets.

States: "retail" (the site holds its retail call and the page is empty or not reserved), "applied" (the site enters the
page and the page is exactly the template linked for this address, the room's address and the IR link), anything else
"foreign". Retail restores the site and fills the page with 0xCC; the reservation stays.
"""
from __future__ import annotations

import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = space.QB_TRADES_OWNER
REQUESTS = (space.QB_TRADES_REQUEST,)
VA = space.QB_TRADES_VA
SIZE = space.QB_TRADES_SIZE
ROOM_VA = space.QB_ROOM_VA
ERRORS = (ValueError, TypeError, IndexError, KeyError, OverflowError, struct.error)


class QbTradesError(ValueError):
    """The trades page or its site could not be verified."""


def _require(condition, message):
    if not condition:
        raise QbTradesError(message)


def _code():
    from . import nfl2k5_qb_trades_code as code
    return code


def allocation(payload):
    """The page's allocator row, or None when this executable has no reservation for it."""
    if not space.is_scaleout(payload):
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and tuple(rows[0][k] for k in ("owner", "kind", "size", "align")) == REQUESTS[0]
             and rows[0]["va"] == VA and rows[0]["owner_offset"] == 0, "Unknown quarterback trades allocation")
    section = XbeImage(payload).section(VA, SIZE)
    _require(section.writable and section.executable, "The quarterback trades page needs a writable executable pool")
    return rows[0]


def page(ir_store_va, shadow=False):
    return _code().page_bytes(VA, ROOM_VA, ir_store_va=ir_store_va, shadow=shadow)


def state(payload):
    """(status, IR link, shadow) after authenticating the site and the whole page: "retail" with link and shadow None,
    "applied" with the page's link word and its shadow flag; raises QbTradesError when foreign."""
    image = XbeImage(payload)
    at, original, patched = _code().site(VA)
    found = image.read(at, len(original))
    row = allocation(payload)
    raw = image.read(VA, SIZE) if row is not None else None
    if found == original:
        _require(raw is None or raw == b"\xcc" * SIZE, "The quarterback trades page holds code but its site is retail")
        return "retail", None, None
    _require(found == patched and raw is not None, f"Foreign quarterback trades bytes at {at:#x}")
    link, flags = struct.unpack_from("<II", raw, _code().LINK_IR_STORE)
    _require(flags in (0, _code().FLAG_SHADOW) and raw == page(link, bool(flags)), "Foreign quarterback trades page")
    return "applied", link, bool(flags)


def status(payload):
    try:
        return state(bytes(payload))[0]
    except ERRORS:
        return "foreign"


def edits(ir_store_va, *, restoring, shadow=False):
    """(address, before, after) for the site and the whole page."""
    at, original, patched = _code().site(VA)
    empty, full = b"\xcc" * SIZE, page(ir_store_va, shadow)
    if restoring:
        return [(at, patched, original), (VA, full, empty)]
    return [(at, original, patched), (VA, empty, full)]
