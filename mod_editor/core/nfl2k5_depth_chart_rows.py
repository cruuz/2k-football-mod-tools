"""Tier 2 depth-chart rows: X/Z/SLOT and nickel/dime, for the retail Xbox XBE.

The existing 44-record .rdata allocation is retained. Units have a storage
stride of 13 and visible counts of 12/13/13/4; offense slot 12 and record 43
are zero padding. Existing slots keep their within-unit indices. Position
pools (including its third-starter hook and tab initializer) must already be
applied. No new cave, global, position enum or roster data is allocated.

The row getter uses the pools cave's ``chain & 1, row + (chain >> 1)``.
The swap and bench paths must use the same bit, and the bench threshold must
use the shifted row. The duplicate-starter warning still checks the original
eleven slots: the new roles are intentional aliases of those slots' backups.
These details are proved with bounded execution, not an in-game witness.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
from typing import Mapping

from . import nfl2k5_edge_rename as edge
from . import nfl2k5_modern_positions as modern
from . import nfl2k5_position_pools as pools
from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm

STRIDE = modern.EXPANDED_SLOTS_PER_UNIT
ROW_COUNTS = (12, 13, 13, 4)
TABLE_VA = modern.SLOT_TABLE_VA
RECORD_SIZE = modern.SLOT_RECORD_STRIDE
TABLE_SIZE = modern.SLOT_TABLE_RECORDS * RECORD_SIZE
TABLE_END_VA = TABLE_VA + TABLE_SIZE  # 0x514D38, the KR/PR list begins here
RETAIL_TABLE_SHA256 = "f23bcc25e133ed79f497f73b7a22fb8c8c59c911db3452d0beb98faf215759d8"
RETAIL_RETURNER_POSITIONS = struct.pack("<6I", 8, 7, 3, 4, 6, 5)
STRIDE_VAS = (0x242C05, 0x242D1B, 0x242E05, 0x243519, 0x2436E1,
              0x243AE5, 0x243D55, 0x243E1A, 0x24428F, 0x2442F3, 0x244429)
COUNT_VA = 0x243AA0
RETAIL_COUNT = bytes.fromhex("a1b874c10083e800740d83e802740848b8040000007405b80b000000c3")
# Preserve the specials mov eax,4 at 0x243AB0 and the defense mov at 0x243AB7.
# The zero-unit arm returns 12, so no UI callback can select the offense spare.
EXPANDED_COUNT = bytes.fromhex("a1b874c10083f803740685c0b00c740cb8040000007405b80d000000c3")
SWAP_CHAIN_VA = 0x242CA3
BENCH_VA, BENCH_END_VA = 0x244405, 0x244478
RETAIL_BENCH = bytes.fromhex(
    "03c183f8077e6c8b4c2418ba1c8be800e826a1f0ff85c0747ba1b874c1008b0d7874c1006bc00b03c18d14c0"
    "8b04d51c41510085c0741d33c0668b46288bcf25ff1f00000d00a0000066894628e839f3ffffeb4033c9668b4e28"
    "81e1fff7000081c90014000066894e288bcfe81af3ffffeb21"
)
DUPLICATE_COUNT_CALLS = (0x243B6C, 0x243B90, 0x243BCD, 0x243BD7)
# unit, appended slot, abbreviation, long name, position, encoded chain
ROLE_ROWS = ((0, 11, "SLOT", "SLOT RECEIVER", 3, 2),
             (1, 11, "NCB", "NICKEL CORNER", 4, 2),
             (1, 12, "DCB", "DIME CORNER", 4, 3),
             (2, 11, "NCB", "NICKEL CORNER", 4, 2),
             (2, 12, "DCB", "DIME CORNER", 4, 3))
WR_LABELS = ((3, ("LWR", "LEFT WIDE RECEIVER"), ("X", "X RECEIVER")),
             (4, ("RWR", "RIGHT WIDE RECEIVER"), ("Z", "Z RECEIVER")))


class DepthChartRowsError(ValueError):
    """Unknown executable bytes or an unmet position-pools dependency."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DepthChartRowsError(message)


def _span(payload: bytes, va: int, size: int) -> int:
    off = modern._offset(payload, va)
    section = _section_for_offset(_sections(payload), off)
    _require(off + size <= min(len(payload), section.raw_offset + section.raw_size),
             f"truncated section at 0x{va:x}")
    return off


def _read(payload: bytes, va: int, size: int) -> bytes:
    off = _span(payload, va, size)
    return payload[off:off + size]


def bench_bytes() -> bytes:
    """Rewrite the existing bench arm in place; preserve its two outgoing edges.

    EAX stays the displayed row on the selection edge. ECX is the actual
    list row for the >7 test. Save the encoded chain across the confirmation
    dialog on the stack, then promote in the correct rank/side field.
    """

    a = _Asm(BENCH_VA)
    a.b("03c1")                       # add eax,ecx: displayed row
    a.b("8b0d" + struct.pack("<I", pools.DC_UNIT_VA).hex())
    a.b("6bc90d")                     # imul ecx,ecx,13; preserve displayed row in EAX
    a.b("030d" + struct.pack("<I", pools.DC_SLOT_VA).hex())
    a.b("8d0cc9")                     # lea ecx,[ecx+ecx*8]
    a.b("8b14cd" + struct.pack("<I", pools.RECORD_CHAIN_VA).hex())
    a.b("8bca d1e9 03c8 83f907")       # ecx = displayed row + (chain >> 1)
    a.j8("7e", "select")
    a.b("52 8b4c241c ba1c8be800")     # save chain; original UI argument +4
    a.call(0x14E540)                   # confirmation dialog
    a.b("85c0 58")                    # test result; pop encoded chain (flags preserved)
    a.j8("74", "done")
    a.b("a801")                       # test al,1: chain 2 is RANK, not side
    a.j8("74", "rank")
    a.b("66816628ff1f 66814e2800a0")  # side = 5, preserve rank and other bits
    a.j8("eb", "refresh")
    a.label("rank")
    a.b("66816628fff7 66814e280014")  # rank = 5, preserve side and other bits
    a.label("refresh")
    a.b("8bcf")
    a.call(0x243790)                   # retail order compaction
    a.jmp_abs(0x244499)
    a.labels["select"] = BENCH_END_VA - BENCH_VA
    a.labels["done"] = 0x244499 - BENCH_VA
    code = a.assemble()
    _require(len(code) <= len(RETAIL_BENCH), "bench arm exceeds its retail allocation")
    return code + b"\x90" * (len(RETAIL_BENCH) - len(code))


@dataclass(frozen=True)
class CodeSite:
    label: str
    va: int
    befores: tuple[bytes, ...]
    after: bytes


def code_sites() -> tuple[CodeSite, ...]:
    sites = [CodeSite(f"stride_{va:x}", va, (bytes.fromhex("6bc00b"),), bytes.fromhex("6bc00d"))
             for va in STRIDE_VAS if va not in (0x243D55, 0x244429)]
    # These two old stride sites are inside whole replacement blocks: pin the
    # owner block, not an operand whose neighboring instructions have moved.
    sites += [CodeSite("tab_init", pools.TAB_INIT_VA,
                       (pools.RETAIL_TAB_INIT, pools.tab_init_bytes()), pools.tab_init_bytes(STRIDE)),
              CodeSite("unit_counts", COUNT_VA, (RETAIL_COUNT,), EXPANDED_COUNT),
              CodeSite("swap_chain_bit", SWAP_CHAIN_VA, (bytes.fromhex("85c0"),), bytes.fromhex("a801")),
              CodeSite("bench_chain_and_row", BENCH_VA, (RETAIL_BENCH,), bench_bytes())]
    for va in DUPLICATE_COUNT_CALLS:
        before = b"\xe8" + struct.pack("<i", COUNT_VA - va - 5)
        sites.append(CodeSite(f"starter_count_{va:x}", va, (before,), bytes.fromhex("b80b000000")))
    return tuple(sites)


def _records(payload: bytes, stride: int) -> list[bytes]:
    raw = _read(payload, TABLE_VA, TABLE_SIZE)
    records = [raw[i:i + RECORD_SIZE] for i in range(0, TABLE_SIZE, RECORD_SIZE)]
    if stride == STRIDE:
        for unit, slot, abbrev, long_name, position, chain in ROLE_ROWS:
            expected = modern.slot_text(abbrev, long_name) + struct.pack("<II", position, chain)
            _require(records[unit * STRIDE + slot] == expected, f"unknown {abbrev} record in unit {unit}")
        _require(records[12] == records[43] == bytes(RECORD_SIZE), "nonzero spare record")
        for slot, _before, after in WR_LABELS:
            _require(records[slot][:64] == modern.slot_text(*after), "unknown X/Z labels")
        retail_order = [records[unit * STRIDE + slot]
                        for unit in range(4) for slot in range(11 if unit < 3 else 4)]
        records = retail_order + [bytes(RECORD_SIZE)] * 7
        for slot, before, _after in WR_LABELS:
            records[slot] = modern.slot_text(*before) + records[slot][64:]
    return records


def _table_is_known(payload: bytes, stride: int) -> None:
    """Undo only recognised coordinated edits, then check the entire retail table.

    The digest pins every unused byte, every original record, and every pool
    field. Unknown text is never decoded/re-encoded into an accepted string.
    """

    records = _records(payload, stride)
    for site in modern.SITES:
        i = site.unit * 11 + site.slot
        if records[i][:64] == modern.slot_text(*site.after):
            records[i] = modern.slot_text(*site.before[0]) + records[i][64:]
    for label, va, abbrev, long_name, new_long in edge.SLOT_RECORDS:
        i = (va - TABLE_VA) // RECORD_SIZE
        accepted = (edge._slot_record(edge.ABBREVIATION, new_long),) + tuple(
            edge._slot_record(*text) for text in edge.SLOT_RECORD_ALTERNATIVES.get(label, ()))
        if records[i][:64] in accepted:
            records[i] = modern.slot_text(abbrev, long_name) + records[i][64:]
    _require(modern.pool_profile(payload) is not None, "mixed position-pool records")
    for _label, unit, slot, before, after in pools.POOL_RECORDS:
        i = unit * 11 + slot
        if records[i][64:] == struct.pack("<II", *after):
            records[i] = records[i][:64] + struct.pack("<II", *before)
    _require(hashlib.sha256(b"".join(records)).hexdigest() == RETAIL_TABLE_SHA256,
             "unknown depth-chart table bytes")


def _expanded_table(payload: bytes) -> bytes:
    raw = _read(payload, TABLE_VA, TABLE_SIZE)
    result = bytearray(TABLE_SIZE)
    for unit in range(4):
        for slot in range(11 if unit < 3 else 4):
            before, after = (unit * 11 + slot) * RECORD_SIZE, (unit * STRIDE + slot) * RECORD_SIZE
            result[after:after + RECORD_SIZE] = raw[before:before + RECORD_SIZE]
    for slot, _before, after in WR_LABELS:
        result[slot * RECORD_SIZE:slot * RECORD_SIZE + 64] = modern.slot_text(*after)
    for unit, slot, abbrev, long_name, position, chain in ROLE_ROWS:
        off = (unit * STRIDE + slot) * RECORD_SIZE
        result[off:off + RECORD_SIZE] = modern.slot_text(abbrev, long_name) + struct.pack("<II", position, chain)
    return bytes(result)


def status(payload: bytes) -> str:
    """retail/applied/foreign for this patch, independently of other label toggles.

    A known unexpanded layout is retail even before pools is enabled. Applying
    it still requires pools. An expanded layout requires its live dependency.
    Partial code/table rewrites and unknown bytes are foreign.
    """

    try:
        stride = modern.layout_stride(payload)
        _require(_read(payload, TABLE_END_VA, len(RETAIL_RETURNER_POSITIONS)) == RETAIL_RETURNER_POSITIONS,
                 "unknown KR/PR boundary")
        for site in code_sites():
            got = _read(payload, site.va, len(site.after))
            _require(got == site.after if stride == STRIDE else got in site.befores,
                     f"unknown {site.label} bytes")
        _table_is_known(payload, stride)
        if stride == STRIDE:
            _require(pools.status(payload) == "applied", "position_pools dependency is not applied")
        return "applied" if stride == STRIDE else "retail"
    except (ValueError, struct.error, IndexError):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Pure, idempotent XBE patch; the caller owns writing an output copy."""

    state = status(payload)
    _require(state != "foreign", "depth-chart rows are foreign; refusing")
    _require(pools.status(payload) == "applied",
             "apply nfl2k5_position_pools with depth_chart_third_starter before depth-chart rows")
    if state == "applied":
        return payload, {"status": "applied", "already_applied": True, "changed_bytes": 0,
                         "edits": [], "sections_repinned": [], "stride": STRIDE, "row_counts": list(ROW_COUNTS)}
    sections = _sections(payload)
    buf = bytearray(payload)
    edits, touched = [], set()
    writes = [(site.label, site.va, site.after) for site in code_sites()]
    writes.append(("depth_chart_table", TABLE_VA, _expanded_table(payload)))
    for label, va, after in writes:
        off = _span(payload, va, len(after))
        section = _section_for_offset(sections, off)
        buf[off:off + len(after)] = after
        touched.add(section.index)
        edits.append({"label": label, "va": f"0x{va:x}", "file_offset": f"0x{off:x}", "size": len(after)})
    for section in sections:
        if section.index in touched:
            off = section.header_offset + 36
            buf[off:off + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "depth-chart rows post-apply verification failed")
    _require(modern.status(patched) == modern.status(payload), "scheme-label status changed")
    _require(edge.status(patched) == edge.status(payload), "EDGE status changed")
    return patched, {"status": "applied", "already_applied": False,
                     "changed_bytes": sum(a != b for a, b in zip(payload, patched)),
                     "sections_repinned": sorted(touched), "edits": edits,
                     "dependency": "position_pools", "stride": STRIDE, "row_counts": list(ROW_COUNTS),
                     "runtime_witnessed": False}
