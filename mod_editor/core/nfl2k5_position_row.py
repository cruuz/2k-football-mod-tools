"""A Position row on the first page of Edit Player, in roster mode and in Franchise (executable patch).

Retail ``default.xbe``: the Create Player screen lists First Name, Last Name, **Position**, Jersey,
College, ... on its first page (row list at .rdata 0x567134; the Position descriptor is 0x562810 with
its own getter ``cb_00345540`` -> the 17 position names at 0x555AE0, next ``0x345560`` and prev
``0x345590`` that cycle 0..16 and set the dirty flag). Edit Player uses two other row lists, one for
players with a created face (0x567394) and one for real-face players (0x5675E4): First, Last, Jersey,
College, Best Hand, then two zero words before the next structure. Position is simply not listed.
Both roster mode (``cb_0035f6c0``) and the Franchise player menu (``cb_002b83f0``) open the same
screens through ``FUN_00346730`` on the live roster record; there is no mode check to defeat, and
edit mode never reloads the ratings template (``FUN_00343460`` returns early), so a position change
keeps the player's ratings and the overall recomputes from the new position's weights at read time.

The patch inserts the Position descriptor pointer after Last Name in both lists (each list keeps its
zero terminator inside the same 28 bytes). Nothing rebuilds the depth chart on exit: use Depth Chart
-> Auto (the pre-game check also repairs it). Unwitnessed in game.
"""

from __future__ import annotations

import struct
from typing import Mapping

from . import nfl2k5_rdata_sites as rdata

LIST_CREATED_FACE_VA = 0x00567394   # Edit Player, created-face players (chain B)
LIST_REAL_FACE_VA = 0x005675E4      # Edit Player, real-face players (chain C)
POSITION_DESCRIPTOR_VA = 0x00562810
LIST_SIZE = 28

RETAIL_LIST = bytes.fromhex("b0265600 60275600 c0285600 202a5600 d02a5600 00000000 00000000".replace(" ", ""))
PATCHED_LIST = bytes.fromhex("b0265600 60275600 10285600 c0285600 202a5600 d02a5600 00000000".replace(" ", ""))
assert len(RETAIL_LIST) == len(PATCHED_LIST) == LIST_SIZE
assert PATCHED_LIST[8:12] == POSITION_DESCRIPTOR_VA.to_bytes(4, "little")

# The descriptor itself must be the retail one: +0x04 = 3, getter 0x345540 at +0x08, next 0x345560 at
# +0x20, prev 0x345590 at +0x38, label 0xEAEE60 "Position" at +0x70.
RETAIL_DESCRIPTOR_HEAD = bytes.fromhex("00000000 03000000 40553400 00000000 00000000 00000000 00000000 00000000 60553400".replace(" ", ""))


class PositionRowError(ValueError):
    """The executable does not carry the retail Edit Player lists."""


def sites() -> list[tuple[str, int, bytes, bytes]]:
    return [("edit_player_created_face_rows", LIST_CREATED_FACE_VA, RETAIL_LIST, PATCHED_LIST),
            ("edit_player_real_face_rows", LIST_REAL_FACE_VA, RETAIL_LIST, PATCHED_LIST)]


def descriptor_is_retail(payload: bytes) -> bool:
    try:
        off = rdata.offset_of(payload, POSITION_DESCRIPTOR_VA)
    except (rdata.RdataSiteError, ValueError, struct.error):
        return False
    return payload[off: off + len(RETAIL_DESCRIPTOR_HEAD)] == RETAIL_DESCRIPTOR_HEAD


def status(payload: bytes) -> str:
    if not descriptor_is_retail(payload):
        return "foreign"
    return rdata.status(payload, sites())


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    if not descriptor_is_retail(payload):
        raise PositionRowError("the Position descriptor at 0x562810 is not retail; refusing")
    try:
        patched, receipt = rdata.apply(payload, sites(), "Position-row")
    except rdata.RdataSiteError as exc:
        raise PositionRowError(str(exc)) from exc
    return patched, {**receipt, "row_inserted_after": "Last Name", "descriptor": f"0x{POSITION_DESCRIPTOR_VA:x}"}


__all__ = ["LIST_CREATED_FACE_VA", "LIST_REAL_FACE_VA", "POSITION_DESCRIPTOR_VA", "PATCHED_LIST", "RETAIL_LIST",
           "PositionRowError", "apply", "descriptor_is_retail", "sites", "status"]
