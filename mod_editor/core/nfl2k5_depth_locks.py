"""Persistent, independent depth-chain and returner locks (experimental XBE patch).

Byte +0x52 bits 0..4 of a 0x54 player record own rank/side/KR1/KR2/PR.
The native weekly ratings sort is retained. Its rank stage and the shared
compactor allocate unlocked rows around reserved locked rows, capped at 7.
The existing screen swap and confirmed KR/PR arms set the relevant locks;
bench promotions are recognized by pinned return addresses in the compactor.

All six rewrites stay inside their original function/block allocations.
There are NO code caves or absolute runtime variables. Scratch is on the
stack; persistent bits are in writable roster records, separate from stars.
The annotated GNU assembler source is docs/mod_editor/nfl2k5_depth_locks.S;
embedded code makes application independent of an assembler on Windows.

Conflicting imported locks are preserved (and reported by the roster API),
not silently reassigned. Valid records have unique locked rows 0..6 per
position/chain and at most one owner of each returner role per team. Row 7
is the shared overflow row. Locks are preferences, not an injury or personnel
eligibility override. Full game/UI/save lifecycles remain unwitnessed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_cave_oracle import XbeImage
from . import nfl2k5_modern_positions as modern
from . import nfl2k5_returner_fix as returners

LOCK_OFFSET = 0x52
LOCK_BITS = {"rank": 1, "side": 2, "kr1": 4, "kr2": 8, "pr": 16}
LOCK_MASK = 0x1F
PLAYER_SIZE = 0x54
TEAM_CAPACITY = 65
PAIRED_POSITIONS = (3, 4, 10, 11, 13, 14, 15, 16)
CAVES = ()
RUNTIME_GLOBALS = ()
COMPACT_VA = 0x243790
WEEKLY_ENTRY_VA = COMPACT_VA + 4
SWAP_VA = 0x242CA0
KR_SET_VA = 0x244360
PR_SET_VA = 0x2443D4
REMOVE_VA = 0xC3A9E
RANK_STAGE_VA = 0x2BDDE0
RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"


class DepthLockError(ValueError):
    """Unrecognized executable or invalid lock selection."""


def lock_bit(role: str) -> int:
    try:
        return LOCK_BITS[role]
    except (KeyError, TypeError) as exc:
        raise DepthLockError(f"unknown depth lock {role!r}; choose {tuple(LOCK_BITS)}") from exc


def read_locks(record: bytes) -> dict[str, bool]:
    if len(record) != PLAYER_SIZE:
        raise DepthLockError("expected one complete 0x54 player record")
    return {role: bool(record[LOCK_OFFSET] & bit) for role, bit in LOCK_BITS.items()}


def set_lock(record: bytes, role: str, enabled: bool = True) -> bytes:
    """Pure record API; preserves all other bits, including +0x52 high bits/star.

    Use RosterDocument.set_depth_lock for team-level uniqueness validation.
    """
    read_locks(record)
    bit = lock_bit(role)
    if not isinstance(enabled, bool):
        raise DepthLockError("enabled must be a boolean")
    out = bytearray(record)
    out[LOCK_OFFSET] = out[LOCK_OFFSET] | bit if enabled else out[LOCK_OFFSET] & ~bit
    return bytes(out)

RETAIL_COMPACT = bytes.fromhex(
    "558bec83e4f881ec2002000053555633f657894c2414897424188d9b00000000b863000000b9410000008d7c2420f3ab"
    "8b4c24148bd6e8e504e8ff8bd833ed85db895c241c7e738b4c2414568bd5e84d05e8ff33d2668b5028c1ea0a83e20733"
    "ff3b54bc207c084783ff417cf4eb4683ff407d36bb4000000033c92bdf8d49008bb40c1c01000089b40c200100008bb4"
    "0c2402000089b40c2802000083e9044b75de8b7424188b5c241c8954bc208984bc28010000453beb7c8d33d285db7e28"
    "83fa078bc27c05b8070000008b8c9428010000c1e00a6633412825001c000066314128423bd37cd84683fe1189742418"
    "0f8c2affffff33f6897424188d642400b863000000b9410000008d7c2420f3ab8b4c24148bd6e80504e8ff8bf833ed85"
    "ff897c241c7e738b4c2414568bd5e86d04e8ff0fb75828c1eb0d33d28d6424003b5c94207c084283fa417cf4eb4783fa"
    "407d37bf4000000033c92bfa8d6424008bb40c1c01000089b40c200100008bb40c2402000089b40c2802000083e9044f"
    "75de8b7c241c8b742418895c942089849428010000453bef7c8d33c085ff7e2d83f8078bc87c05b9070000008b948428"
    "01000033db668b5a28c1e10d81e3ff1f00000bd9403bc766895a287cd34683fe11897424180f8c25ffffff8b74241433"
    "c0b9fe000000e835f2ffff888695010000b801000000b9fe000000e820f2ffff88869601000033c0b9fd000000e80ef2"
    "ffff5f8886990100005e5d5b8be55dc3"
)

PATCHED_COMPACT = bytes.fromhex(
    "31d2eb036a015a6083ec6c89cdc7442468000000008b84248c0000006a025a3d57442400741a4a3d7644240074123d64"
    "44240075188b94248800000083e20142895424688b742470f7d22056528b942480000000895424440fb6851c01000083"
    "f8410f87a10100008944245431ffc744244c0a000000c744245001000000c744245800000000c74424640000000031db"
    "3b5c24547373c6041cff8b749d0089f838463575618b4c244c0fb74628d3e883e0078b54245084565274070fab442458"
    "eb40837c24440074368b44246483f90d7525ba18ec01000fa3fa720b0fb74628d3e883e007eb1883f803730b83c00283"
    "f803720383e80383f80776036a075888041cff44246443eb87c744246000000000c744245c0000000031db3b5c245473"
    "478b44246038041c753b8b44245c83f80772056a0758eb0a0fa3442458730340ebec8944245cff44245c8b749d008b4c"
    "244cd3e0ba07000000d3e26633462821d06631462843ebb3ff442460837c24600872a6837c244c0d7415c744244c0d00"
    "0000c744245002000000e9effeffff4783ff110f82d5feffff837c244400756989ee31c0b9fe000000e872f2ffff8886"
    "95010000b801000000b9fe000000e85df2ffff88869601000031c0b9fd000000e84bf2ffff8886990100008b5c24544b"
    "78278b749d008a4652a8047406889d95010000a8087406889d96010000a81074de889d99010000ebd68b44246885c074"
    "078b74247008465283c46c61c3"
)

RETAIL_RANK_STAGE = bytes.fromhex(
    "33db8bd38bcf33f6e8c35ee0ff4885c07e748d6bfd538bd68bcfe8315fe0ff8bcec1e10a6633482881e1001c00006631"
    "482883fd0d668b4828773c0fb695f8df2b00ff2495f0df2b008bd681e1ff1f000083ea0074174a741a4a74098bd6c1e2"
    "0d0bcaeb0e81c900200000eb0681c900400000668948288bd38bcf46e84f5ee0ff483bf07c8f4383fb110f8c72ffffff"
)

PATCHED_RANK_STAGE = bytes.fromhex(
    "89f9e8ad59f8ffe984000000"
)

RETAIL_SWAP = bytes.fromhex(
    "5733ff85c0668b79287434668b56286633fa0fb7c233d2c1e80dc1e00d81e7ff1f00006633792866897e28668b51285f"
    "81e2ff1f00000bd066895128c2040033d2668b56286633fa8bc2c1e80a83e00781e7001c000033fa66897e28c1e00a66"
    "3341285f25001c000066314128c20400"
)

PATCHED_SWAP = bytes.fromhex(
    "5731ffa801ba001c0000b801000000740aba00e00000b8020000000841520846520fb7792866337e2821d766317e2866"
    "3179285fc20400"
)

RETAIL_KR_SET = bytes.fromhex(
    "8a8f95010000888f960100008a8f1c01000033c084c90f861d0100008d64240039348774110fb6971c010000403bc27c"
    "efe903010000888795010000e9f8000000"
)

PATCHED_KR_SET = bytes.fromhex(
    "600fb6979501000088979601000031c03a871c01000073208b1c87806352f339d07504804b520839f3750a8887950100"
    "00804b520440ebd861e9fb000000"
)

RETAIL_PR_SET = bytes.fromhex(
    "8a8f1c01000033c084c90f86b500000039348774110fb6971c010000403bc27cefe99f000000888799010000e9940000"
    "00"
)

PATCHED_PR_SET = bytes.fromhex(
    "6031c03a871c01000073188b1487806252ef39f2750a888799010000804a521040ebe061e99c000000"
)

RETAIL_REMOVE = bytes.fromhex(
    "8b148856816224ff1fffff8a901c010000feca88901c0100000fb6d2"
)

PATCHED_REMOVE = bytes.fromhex(
    "8b1488568062251f806252e0fe881c0100000fb6901c010000"
)

# Context gates cover the native pointer-sort frame and returner/UI call ABI.
# The whole bench block is pinned by the retail/SPECIAL layout owner.
SORT_PREFIX_SHA256 = "55a6689d6bccfea9d6aadbf39c3261ae7af8614e8adf309ebff78fca3427a40e"
FALLBACK_SHA256 = "ab0cf0d699372e7996efaaf7edf988dec7ced0cfd211fcacdf7438e3923934d5"


@dataclass(frozen=True)
class Site:
    label: str
    va: int
    before: bytes
    after: bytes


def sites(layout: str = "retail") -> tuple[Site, ...]:
    """Both layouts use stride 11; SPECIAL alone uses encoded swap chains."""
    if layout not in ("retail", "special"):
        raise DepthLockError("unknown depth-chart layout")
    swap_before, swap_after = bytearray(RETAIL_SWAP), bytearray(PATCHED_SWAP)
    swap_before[3:5] = swap_after[3:5] = bytes.fromhex("85c0" if layout == "retail" else "a801")
    values = (
        ("compactor", COMPACT_VA, RETAIL_COMPACT, PATCHED_COMPACT),
        ("weekly_rank_stage", RANK_STAGE_VA, RETAIL_RANK_STAGE, PATCHED_RANK_STAGE),
        ("screen_swap", SWAP_VA, bytes(swap_before), bytes(swap_after)),
        ("screen_kr", KR_SET_VA, RETAIL_KR_SET, PATCHED_KR_SET),
        ("screen_pr", PR_SET_VA, RETAIL_PR_SET, PATCHED_PR_SET),
        ("membership_remove", REMOVE_VA, RETAIL_REMOVE, PATCHED_REMOVE),
    )
    return tuple(Site(label, va, before, after + b"\x90" * (len(before) - len(after)))
                 for label, va, before, after in values)


def _context(payload: bytes) -> tuple[XbeImage, str]:
    from . import nfl2k5_depth_chart_rows as rows
    image = XbeImage(payload)
    # Check the complete coordinated layout, including stride, table/storage,
    # reader pointers, counts, swap test and bench arm. Accepting either bench
    # arm in isolation would silently accept a partial SPECIAL install.
    rows_state = rows.status(payload)
    if rows_state == "foreign":
        raise DepthLockError("unknown or mixed retail/SPECIAL depth-chart layout")
    layout = "special" if rows_state == "applied" else "retail"
    if hashlib.sha256(image.read(0x2BDCF0, 0xF0)).hexdigest() != SORT_PREFIX_SHA256:
        raise DepthLockError("unknown native weekly pointer-sort frame")
    if hashlib.sha256(image.read(0x242BB0, 0x4A)).hexdigest() != FALLBACK_SHA256:
        raise DepthLockError("unknown returner fallback ABI")
    if image.read(returners.SITE_VA, returners.SITE_SIZE) not in (
            returners.RETAIL_SITE, returners.site_bytes()):
        raise DepthLockError("unknown returner selection loop")
    for site in sites(layout):
        section = image.section(site.va, len(site.before))
        if section is None or section.name != ".text" or section.flags != 0x16:
            raise DepthLockError("expected retail read-only text mapping")
    return image, layout


def read_any(payload: bytes) -> dict[str, object]:
    """Describe complete retail/applied/foreign states; partial installs refuse."""
    try:
        image, layout = _context(payload)
        states = {}
        for site in sites(layout):
            got = image.read(site.va, len(site.before))
            states[site.label] = ("retail" if got == site.before else
                                  "applied" if got == site.after else "foreign")
        unique = set(states.values())
        state = next(iter(unique)) if len(unique) == 1 else "foreign"
        return {"status": state, "sites": states, "stride": modern.SLOTS_PER_UNIT,
                "layout": layout}
    except (ValueError, struct.error, IndexError) as exc:
        return {"status": "foreign", "reason": str(exc)}


def status(payload: bytes) -> str:
    return str(read_any(payload)["status"])


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Pure and idempotent; caller writes an output copy using binary I/O."""
    state = read_any(payload)
    if state["status"] == "foreign":
        raise DepthLockError(f"depth locks are foreign; refusing: {state}")
    if state["status"] == "applied":
        return payload, {"status": "applied", "already_applied": True,
                         "changed_bytes": 0, "edits": [], "sections_repinned": []}
    image, layout = _context(payload)
    buf = bytearray(payload)
    sections = _sections(payload)
    touched, edits = set(), []
    for site in sites(layout):
        off = image.offset(site.va, len(site.before))
        buf[off:off + len(site.after)] = site.after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": site.label, "va": hex(site.va),
                      "file_offset": hex(off), "size": len(site.after)})
    for section in sections:
        if section.index in touched:
            off = section.header_offset + 36
            buf[off:off + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    if status(patched) != "applied":
        raise DepthLockError("depth locks post-apply verification failed")
    return patched, {"status": "applied", "already_applied": False, "edits": edits,
                     "changed_bytes": sum(a != b for a, b in zip(payload, patched)),
                     "sections_repinned": sorted(touched), "stride": modern.SLOTS_PER_UNIT,
                     "layout": layout,
                     "lock_offset": hex(LOCK_OFFSET), "lock_bits": dict(LOCK_BITS),
                     "new_caves": [], "runtime_globals": [], "runtime_witnessed": False}
