"""Resolve SportsCenter featured players by identity in the disposable roster.

The canned replay builder (DE100) fills two formation lineups, decodes the
recorded player references, then DE080 swaps whole 84-byte records to put
the featured passer/receiver in their recorded roles. DE010 used to pair
the live franchise and disposable game rosters by array index. That index
ceases to identify the same player after records have been swapped, or
the source list has moved. A subsequent swap can therefore put a TE in
the passer's body and the QB on the line.

Replace only DE010's existing 112-byte allocation. Names are shared string
pointers in the native copies; the portrait and birth fields distinguish
reused names. Ignore mutable game flags, depth order, jersey and ratings.
An ambiguous/absent identity returns NULL, retaining DE080's native direct
copy of the featured record into the requested role. No new storage, save
fields, formation changes or allocator requests.

Bounded native tests prove the mapping and record swaps, not rendered
SportsCenter acceptance or the provenance of an individual old save.
"""
from __future__ import annotations

import hashlib

from . import nfl2k5_rdata_sites as rdata
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_sportscenter_lineup"
REQUESTS = ()
VA, SIZE = 0xDE010, 0x70
BUILD_CAPTION = "SportsCenter highlight lineups"
HELP_TEXT = ("Keep featured players in the correct SportsCenter highlight roles when the game roster has been "
             "reordered. Checked in native routine tests; in-game verification is pending.")
RETAIL = bytes.fromhex(
    "5657e8393cf8ff8bf0e8e29af9ff0fb6be1c01000033d285ff7e188bc82bf090"
    "8b040e3bc374413919743a4283c1043bd77cede8183cf8ff8bf0e8f19af9ff0fb6"
    "be1c01000033d285ff7e178bc82bf08b04313bc374113919740a4283c1043bd77c"
    "ed33c05f5ec35f5e8bc3c3909090")

# The unchanged caller must still consume EBX and use the native NULL-copy
# fallback. Pin both team getters as well as the complete swap/build spans.
GUARDS = (
    (0xDE080, 120, "59021fc71eb0a41b858f616b51902fb50fabfb08407b1688a0f3dc513ce8adff"),
    (0xDE100, 147, "c8af6b750d63a6090197f08ab79dc00d916d7d8e37d1181e58eed43080883ca0"),
    (0x61C50, 16, "d253abcf9f332a747e4e724c67b608ac8b74780d8fa21696bfb12f1e28b3aa03"),
    (0x61C60, 16, "99597a449f1670ce4268d8e6559eed74b552edc2fe3e869d2d2a85c424f64712"),
)


def code() -> bytes:
    """EBX=featured record; EAX=current game copy or NULL. Preserve EBX/ESI/EDI/EBP."""
    a = _Asm(VA)
    a.b("56 57 31ff be6408b300")       # preserve ESI/EDI; unique match; away copy
    a.label("side")
    a.b("0fb6961c010000 83fa41")      # the native team pointer capacity is 65
    a.j8("77", "next_side")
    a.label("player")
    a.b("4a")
    a.j8("78", "next_side")
    a.b("8b0496 85c0")
    a.j8("74", "player")
    a.b("39d8")
    a.j8("74", "done")              # already a game pointer: native semantics
    for offset in (0x10, 0x14):
        a.b(f"8b48{offset:02x} 3b4b{offset:02x}")
        a.j8("75", "player")        # first/last name pointers survive the copy
    a.b("668b4806 663b4b06")          # portrait, independent of commentary cue
    a.j8("75", "player")
    a.b("8b4818 334b18 f7c100f0ff0f") # native immutable birth identity mask
    a.j8("75", "player")
    a.b("85ff")
    a.j8("75", "missing")           # two identities: use native direct-copy fallback
    a.b("89c7")
    a.j8("eb", "player")
    a.label("next_side")
    a.b("81c6f4010000 81fe4c0cb300")  # next 500-byte header, at most two sides
    a.j8("72", "side")
    a.b("89f8")
    a.j8("eb", "done")
    a.label("missing")
    a.b("31c0")
    a.label("done")
    a.b("5f5ec3")
    result = a.assemble()
    if len(result) > SIZE:
        raise ValueError("SportsCenter identity lookup exceeds its native allocation")
    return result.ljust(SIZE, b"\x90")


def sites():
    return [("featured_player_identity", VA, RETAIL, code())]


def status(payload: bytes) -> str:
    try:
        image = XbeImage(payload)
        if any(hashlib.sha256(image.read(va, size)).hexdigest() != digest
               for va, size, digest in GUARDS):
            return "foreign"
        return rdata.status(payload, sites())
    except (ValueError, IndexError):
        return "foreign"


def apply(payload: bytes):
    if status(payload) == "foreign":
        raise ValueError("Foreign SportsCenter lineup lookup or record-swap routines")
    patched, receipt = rdata.apply(payload, sites(), "SportsCenter highlight lineups")
    return patched, {**receipt, "owner": OWNER, "new_cave_bytes": 0,
                     "code_bytes": SIZE, "runtime_witnessed": False,
                     "mapping": "native_copy_identity", "source_roster_mutated": False}
