"""Thirteen SPECIAL role views; offense/defense keep the retail eleven rows.

All indices remain unit * 11 + slot. Relocate 46 records to fresh read-only
storage; preserve the original table and its KR/PR boundary. Pools supplies
the getter cave; swaps and bench promotion honor its encoded chain/row.

The summary sheet uses style 17. Its 28-pixel retail pitch makes SPECIAL
scroll vertically, which narrows the frame and hides the entire third name
column. Reduce its spacing from 4 to 1 (25-pixel pitch). Widen the label
column from 50 to 57 for SLWR/PWRB with normal padding. The font, player
column widths, callbacks and encoded chains remain retail-compatible.

Revision 2 (b780 hunt5; Noah 11/03: "If I make someone a third down back, they
shouldn't be in every single play. The starting halfback should have
priority."). Revision 1 (beta-76.4 to the beta-80 RC) drew 3DRB as chain 0,
the RB rank list itself: moving a back to the top of 3DRB made him RB1, the
back in every formation. 3DRB is now chain 2, RB rank row 1: the top of the
row is RB2 and the starter is not in its list. No offensive formation of the
37 club books asks for RB rank row 1 (their passing sets use the lead back,
heavy sets the power order; kickoff and kick-return units do use RB2), so on
offense the 3DRB back plays when the picker passes over the starter (tired,
hurt or already on the field). A revision-1 table reads "applied" (same layout)
and ``apply`` rewrites only that record's chain dword (0 -> 2) and the section
digest.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
from typing import Mapping

from . import nfl2k5_edge_rename as edge
from . import nfl2k5_modern_positions as modern
from . import nfl2k5_position_pools as pools
from . import nfl2k5_rb_rename as rb
from . import nfl2k5_depth_chart_storage as storage
from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm

STRIDE = modern.SLOTS_PER_UNIT
ROW_COUNTS = (11, 11, 11, 13)
RETAIL_TABLE_VA = modern.SLOT_TABLE_VA
TABLE_VA = storage.TABLE_VA
RECORD_SIZE = modern.SLOT_RECORD_STRIDE
TABLE_SIZE = storage.TABLE_SIZE
RETAIL_TABLE_SIZE = modern.SLOT_TABLE_RECORDS * RECORD_SIZE
TABLE_END_VA = RETAIL_TABLE_VA + RETAIL_TABLE_SIZE  # KR/PR list stays at 0x514D38
RETAIL_TABLE_SHA256 = "f23bcc25e133ed79f497f73b7a22fb8c8c59c911db3452d0beb98faf215759d8"
RETAIL_RETURNER_POSITIONS = struct.pack("<6I", 8, 7, 3, 4, 6, 5)
STRIDE_VAS = (0x242C05, 0x242D1B, 0x242E05, 0x243519, 0x2436E1,
              0x243AE5, 0x243D55, 0x243E1A, 0x24428F, 0x2442F3, 0x244429)
COUNT_VA = 0x243AA0
RETAIL_COUNT = bytes.fromhex("a1b874c10083e800740d83e802740848b8040000007405b80b000000c3")
SPECIAL_COUNT = RETAIL_COUNT[:17] + b"\x0d" + RETAIL_COUNT[18:]
TITLE_VAS = (0xE8894C, 0xEA28D8)
RETAIL_TITLE = "Special Teams\0".encode("utf-16le")
SPECIAL_TITLE = "SPECIAL\0".encode("utf-16le").ljust(len(RETAIL_TITLE), b"\0")
SWAP_CHAIN_VA = 0x242CA3
BENCH_VA, BENCH_END_VA = 0x244405, 0x244478
RETAIL_BENCH = bytes.fromhex(
    "03c183f8077e6c8b4c2418ba1c8be800e826a1f0ff85c0747ba1b874c1008b0d7874c1006bc00b03c18d14c0"
    "8b04d51c41510085c0741d33c0668b46288bcf25ff1f00000d00a0000066894628e839f3ffffeb4033c9668b4e28"
    "81e1fff7000081c90014000066894e288bcfe81af3ffffeb21"
)
DUPLICATE_COUNT_CALLS = (0x243B6C, 0x243B90, 0x243BCD, 0x243BD7)
# unit, slot, <=4-char abbreviation, <=26-char long name, position, encoded chain
ROLE_ROWS = ((3, 4, "LS", "LONG SNAPPER", 12, 2),
             (3, 5, "LGUN", "LEFT GUNNER", 3, 6),
             (3, 6, "RGUN", "RIGHT GUNNER", 4, 6),
             (3, 7, "NCB", "NICKEL CORNER", 4, 2),
             (3, 8, "DCB", "DIME CORNER", 4, 3),
             (3, 9, "SLWR", "SLOT RECEIVER", 3, 2),
             (3, 10, "GAD", "GADGET", 3, 7),
             (3, 11, "3DRB", "THIRD DOWN BACK", 7, 3),
             (3, 12, "PWRB", "POWER BACK", 7, 1))
# Revision 3 (b780 sub1; Noah 11/03: a special-row pick never starts somewhere else). LGUN and RGUN read rank row 3
# of the WR and CB orders (ordinal 6, which no club formation asks for except the punt gunners), 3DRB the RB side
# order from row 1 (ordinal 3: only the third-down rule asks for it), GAD the WR side order from row 3 (ordinal 7:
# only the gadget rule asks for it). Revision 1 (beta-76.4 .. the beta-80 RC: 3DRB = the RB rank list itself, LGUN =
# WR side row 1, the 4th WR in four- and five-WR sets, RGUN = the dime corner, GAD = WR rank row 2) and revision 2
# (the b780 hunt5 3DRB = RB rank row 1) read "previous" and apply() rewrites their role records in place.
REVISION = 3
PREVIOUS_ROLE_ROWS = {
    1: {"LGUN": 3, "RGUN": 3, "GAD": 4, "3DRB": 0},
    2: {"LGUN": 3, "RGUN": 3, "GAD": 4, "3DRB": 2},
}
# What each SPECIAL row does on the field (b780 hunt5, measured on the 37 club playbooks of SOFTDRINK v0.9 and the
# game's own row getter, swap path and lineup picker; tests/mod_editor/test_b780_hunt5_special_rows.py). Both Studio
# pages show this text. Plain words, no dashes between clauses.
ROW_HELP = (
    ("KR / PR", "who returns kickoffs and punts (a new KR1 moves the old one to KR2). No position order moves."),
    ("LS", "your second center. He snaps on every punt, field goal and extra point and is the first center off the "
           "bench."),
    ("LGUN", "the second man in the receiver side order: left gunner on punts, and the fourth receiver in four and five "
             "receiver sets."),
    ("RGUN and DCB", "one list, the second man in the corner side order: right gunner on punts and the fourth corner "
                     "in dime."),
    ("NCB", "the second man in the corner rank order: the third corner in nickel and dime."),
    ("SLWR", "the second man in the receiver rank order: the inside receiver in three receiver sets."),
    ("GAD", "the third man in the receiver rank order: the fifth receiver, and a receiver in the base sets that share "
            "a gadget play's personnel."),
    ("3DRB", "the running backs behind your starter, RB2 first. The starter keeps priority: the 3DRB back comes in "
             "when the starter cannot take the snap. There is no third down switch yet."),
    ("PWRB", "the power back order: the back in goal line, jumbo and heavy I sets, and the second back in two back "
             "sets."),
)
HELP_TEXT = ("Retail: special teams has four depth-chart rows. Patch: SPECIAL shows KR, PR, K, P, LS, LGUN, RGUN, NCB, "
             "DCB, SLWR, GAD, 3DRB and PWRB together, with names beside all available player numbers. Offense and "
             "defense keep eleven rows and show X / Z receiver labels. Row spacing is three pixels tighter on all "
             "depth-chart tabs; the font stays the same. Role labels have more room. Each role row is a view of a "
             "position order, so moving a player there moves him in that order too. "
             + " ".join(f"{label}: {text}" for label, text in ROW_HELP)
             + " The backups in these orders also cover kickoffs and block on kick returns. Requires one-pool "
               "positions and the playbook roles. EXPERIMENTAL/UNWITNESSED.")
WR_LABELS = ((3, ("LWR", "LEFT WIDE RECEIVER"), ("X", "X RECEIVER")),
             (4, ("RWR", "RIGHT WIDE RECEIVER"), ("Z", "Z RECEIVER")))

# File-backed .data style descriptor, not a cave or a runtime allocation.
# dc_overviewsheet is the only style-17 use in all 86 retail LAYT resources.
# All four tab callbacks select the SAME screen 0x533088. Its LAYT node
# overrides the .rdata fallback style with 17 and frame (15, 80, 600, 360).
# 0x16FAD0 computes pitch = style[+0x18] + style[+0x28]. At spacing 2,
# SPECIAL still scrolls; spacing 1 is the largest whole-pixel value that fits.
SUMMARY_STYLE = 17
SUMMARY_STYLE_VA = 0xAA3744
SUMMARY_SPACING_VA = SUMMARY_STYLE_VA + 0x28
RETAIL_SUMMARY_STYLE = bytes.fromhex(
    "0000a041c0c0c0ff01000000dcdcdcff01000000606060ff180000001e000000"
    "020000000100000000008040dc38e800")
SUMMARY_STYLE_BYTES = RETAIL_SUMMARY_STYLE[:40] + struct.pack("<f", 1.0) + RETAIL_SUMMARY_STYLE[44:]
SUMMARY_COLUMNS = (0x532280, 0x532330, 0x532540, 0x5323E0, 0x5325F0, 0x532490, 0x5326A0)
SUMMARY_LABEL_WIDTH_VA = SUMMARY_COLUMNS[0] + 0x50
SUMMARY_LABEL_WIDTH = 57  # widest retail font3 label (51) plus normal padding (6)
SUMMARY_FRAME = (15.0, 80.0, 615.0, 440.0)  # retail LAYT outer 3, chunk 73
# Pin the complete data descriptors used by the bounded draw proof. These
# are read-only assertions; the existing column getters are already correct.
SUMMARY_PINS = ((0x532280, 0x50, "edb74ce4fe66c248b1f8ef66aca90672490bfac5a444c90ed2a957246191d6cd"),
                (0x5322D4, 0x47C, "2b23bca51b666f10e9f7c5a315e267eb98601904d912580922313b6edaa3e509"),
                (0x532800, 0xBC, "ee20e7ff4ed98ba3c5aabf235c6e1ac397cf909c8986b196fb1b38705bb30fdb"),
                (0x532968, 0x100, "9ed52ec7fc5ba9e00b52d6d6c86bd094236cf249e137c190f104e6fcf742e03c"),
                (0x533060, 20, "d0599cc74ffe99c29f128e9f0c2e9247b7ad932c25c7ea1a212887493be88732"))


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
    a.b("6bc90b")                     # imul ecx,ecx,11; preserve displayed row in EAX
    a.b("030d" + struct.pack("<I", pools.DC_SLOT_VA).hex())
    a.b("8d0cc9")                     # lea ecx,[ecx+ecx*8]
    a.b("8b14cd" + struct.pack("<I", TABLE_VA + 0x44).hex())
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
    sites = [CodeSite(f"stride_{va:x}", va, (bytes.fromhex("6bc00b"),), bytes.fromhex("6bc00b"))
             for va in STRIDE_VAS if va not in (0x243D55, 0x244429)]
    # These two old stride sites are inside whole replacement blocks: pin the
    # owner block, not an operand whose neighboring instructions have moved.
    sites += [CodeSite("tab_init", pools.TAB_INIT_VA,
                       (pools.RETAIL_TAB_INIT, pools.tab_init_bytes()), pools.tab_init_bytes(STRIDE, TABLE_VA)),
              CodeSite("unit_counts", COUNT_VA, (RETAIL_COUNT,), SPECIAL_COUNT),
              CodeSite("swap_chain_bit", SWAP_CHAIN_VA, (bytes.fromhex("85c0"),), bytes.fromhex("a801")),
              CodeSite("bench_chain_and_row", BENCH_VA, (RETAIL_BENCH,), bench_bytes())]
    for va in DUPLICATE_COUNT_CALLS:
        before = b"\xe8" + struct.pack("<i", COUNT_VA - va - 5)
        sites.append(CodeSite(f"starter_count_{va:x}", va, (before,), before))
    # Whole retail instructions. The two remaining readers belong to the
    # complete tab-init and bench blocks above; never patch an operand twice.
    for va, raw in POINTER_INSTRUCTIONS:
        old = bytes.fromhex(raw)
        new = old
        for field in (0, 10, 64, 68):
            new = new.replace(struct.pack("<I", RETAIL_TABLE_VA + field), struct.pack("<I", TABLE_VA + field))
        sites.append(CodeSite(f"table_pointer_{va:x}", va, (old,), new))
    return tuple(sites)


POINTER_INSTRUCTIONS = (
    (0x242C10, "6683b8d840510000"), (0x242C20, "8b9018415100"), (0x242C27, "8bb01c415100"),
    (0x242D26, "8b881c415100"), (0x242D2C, "8b8018415100"), (0x242E18, "8b881c415100"),
    (0x242E21, "8b9018415100"), (0x243524, "8b901c415100"), (0x24352A, "8b8018415100"),
    (0x2436EC, "8b901c415100"), (0x2436F2, "8b8018415100"), (0x243AED, "8d04c5d8405100"),
    (0x243E24, "8d14d5e2405100"), (0x2442A6, "8ba818415100"), (0x2442AC, "8b801c415100"),
    (0x2442FB, "8b04d51c415100"),
)


def title_sites() -> tuple[CodeSite, ...]:
    return tuple(CodeSite(f"special_title_{va:x}", va, (RETAIL_TITLE,), SPECIAL_TITLE) for va in TITLE_VAS)


def layout_sites() -> tuple[CodeSite, ...]:
    return (CodeSite("summary_row_spacing", SUMMARY_STYLE_VA,
                     (RETAIL_SUMMARY_STYLE,), SUMMARY_STYLE_BYTES),
            CodeSite("summary_label_width", SUMMARY_LABEL_WIDTH_VA,
                     (struct.pack("<f", 50),), struct.pack("<f", SUMMARY_LABEL_WIDTH)))


def _records(payload: bytes, applied: bool) -> list[bytes]:
    raw = _read(payload, TABLE_VA if applied else RETAIL_TABLE_VA, TABLE_SIZE if applied else RETAIL_TABLE_SIZE)
    records = [raw[i:i + RECORD_SIZE] for i in range(0, TABLE_SIZE, RECORD_SIZE)]
    if applied:
        found = _role_revision(records)
        _require(found is not None, "unknown SPECIAL role records")
        for slot, _before, after in WR_LABELS:
            _require(records[slot][:64] == modern.slot_text(*after), "unknown X/Z labels")
        records = records[:37] + [bytes(RECORD_SIZE)] * 7
        for slot, before, _after in WR_LABELS:
            records[slot] = modern.slot_text(*before) + records[slot][64:]
    return records


def _table_is_known(payload: bytes, applied: bool) -> None:
    """Undo only recognised coordinated edits, then check the entire retail table.

    The digest pins every unused byte, every original record, and every pool
    field. Unknown text is never decoded/re-encoded into an accepted string.
    """

    records = _records(payload, applied)
    for site in modern.SITES:
        i = site.unit * 11 + site.slot
        if records[i][:64] == modern.slot_text(*site.after):
            records[i] = modern.slot_text(*site.before[0]) + records[i][64:]
    for label, va, abbrev, long_name, new_long in edge.SLOT_RECORDS:
        i = (va - RETAIL_TABLE_VA) // RECORD_SIZE
        accepted = (edge._slot_record(edge.ABBREVIATION, new_long),) + tuple(
            edge._slot_record(*text) for text in edge.SLOT_RECORD_ALTERNATIVES.get(label, ()))
        if records[i][:64] in accepted:
            records[i] = modern.slot_text(abbrev, long_name) + records[i][64:]
    # b777-rb2: the RB rename's offense slot 1 text (RB / RUNNING BACK) is a coordinated label edit.
    i = rb.SLOT_UNIT * 11 + rb.SLOT_INDEX
    if records[i][:64] == rb.slot_record_text(False):
        records[i] = rb.slot_record_text(True) + records[i][64:]
    _require(modern.pool_profile(payload) is not None, "mixed position-pool records")
    for _label, unit, slot, before, after in pools.POOL_RECORDS:
        i = unit * 11 + slot
        if records[i][64:] == struct.pack("<II", *after):
            records[i] = records[i][:64] + struct.pack("<II", *before)
    _require(hashlib.sha256(b"".join(records)).hexdigest() == RETAIL_TABLE_SHA256,
             "unknown depth-chart table bytes")


def _special_table(payload: bytes) -> bytes:
    raw = _read(payload, RETAIL_TABLE_VA, RETAIL_TABLE_SIZE)
    result = bytearray(TABLE_SIZE)
    for unit in range(4):
        for slot in range(11 if unit < 3 else 4):
            before, after = (unit * 11 + slot) * RECORD_SIZE, (unit * STRIDE + slot) * RECORD_SIZE
            result[after:after + RECORD_SIZE] = raw[before:before + RECORD_SIZE]
    for slot, _before, after in WR_LABELS:
        result[slot * RECORD_SIZE:slot * RECORD_SIZE + 64] = modern.slot_text(*after)
    for row in ROLE_ROWS:
        off = (row[0] * STRIDE + row[1]) * RECORD_SIZE
        result[off:off + RECORD_SIZE] = _role_record(row)
    return bytes(result)


def _role_record(row) -> bytes:
    unit, slot, abbrev, long_name, position, chain = row
    return modern.slot_text(abbrev, long_name) + struct.pack("<II", position, chain)


def _rows_for(revision: int) -> tuple:
    """ROLE_ROWS as revision ``revision`` wrote them."""

    chains = PREVIOUS_ROLE_ROWS.get(revision, {})
    return tuple(row[:5] + (chains.get(row[2], row[5]),) for row in ROLE_ROWS)


def _role_revision(records: list[bytes]) -> int | None:
    """Which revision wrote these nine SPECIAL role records (3 = current), or None when they are none of them."""

    for revision in (REVISION, *sorted(PREVIOUS_ROLE_ROWS, reverse=True)):
        if all(records[row[0] * STRIDE + row[1]] == _role_record(row) for row in _rows_for(revision)):
            return revision
    return None


def revision(payload: bytes) -> int | None:
    """The SPECIAL role table's revision (1, 2 or 3) on an installed table, None otherwise."""

    if status(payload) not in ("applied", "previous"):
        return None
    raw = _read(payload, TABLE_VA, TABLE_SIZE)
    return _role_revision([raw[i:i + RECORD_SIZE] for i in range(0, TABLE_SIZE, RECORD_SIZE)])


def _upgrade(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Revision 1 or 2 -> 3 in place: only the changed role records' chain dwords and their section digest."""

    old_revision = revision(payload)
    _require(old_revision in PREVIOUS_ROLE_ROWS, "not a previous SPECIAL role table")
    buf = bytearray(payload)
    sections = _sections(buf)
    edits, touched = [], set()
    for old, new in zip(_rows_for(old_revision), ROLE_ROWS):
        if old == new:
            continue
        va = modern.record_va(new[0], new[1], table_va=TABLE_VA)
        off = _span(buf, va, RECORD_SIZE)
        _require(bytes(buf[off:off + RECORD_SIZE]) == _role_record(old), f"unknown {old[2]} record")
        buf[off:off + RECORD_SIZE] = _role_record(new)
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": f"special_{new[2]}_chain", "va": f"0x{va + 0x44:x}", "file_offset": f"0x{off + 0x44:x}",
                      "size": 4, "before": old[5], "after": new[5]})
    for section in sections:
        if section.index in touched:
            at = section.header_offset + 36
            buf[at:at + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied" and revision(patched) == REVISION, "SPECIAL rows upgrade verification failed")
    return patched, {"status": "applied", "already_applied": False, "upgraded_from": f"revision {old_revision}",
                     "changed_bytes": sum(a != b for a, b in zip(payload, patched)), "edits": edits,
                     "sections_repinned": sorted(touched), "stride": STRIDE, "row_counts": list(ROW_COUNTS),
                     "revision": REVISION, "runtime_witnessed": False}


def status(payload: bytes) -> str:
    """Reject partial relocation and obsolete stride-13 builds; rebuild from retail."""

    try:
        _require(modern.layout_stride(payload) == STRIDE, "unknown unit stride")
        applied = modern.layout_table(payload) == TABLE_VA
        _require(storage.state(payload) == ("applied" if applied else "retail"), "unknown storage")
        _require(_read(payload, TABLE_END_VA, len(RETAIL_RETURNER_POSITIONS)) == RETAIL_RETURNER_POSITIONS,
                 "unknown KR/PR boundary")
        for site in (*code_sites(), *title_sites(), *layout_sites()):
            got = _read(payload, site.va, len(site.after))
            _require(got == site.after if applied else got in site.befores,
                     f"unknown {site.label} bytes")
        for va, size, digest in SUMMARY_PINS:
            _require(hashlib.sha256(_read(payload, va, size)).hexdigest() == digest,
                     f"unknown summary descriptor at 0x{va:x}")
        _table_is_known(payload, applied)
        if applied:
            _table_is_known(payload, False)  # retired allocation and its padding are retained intact
            _require(pools.status(payload) in ("applied", "needs_fix"), "position_pools dependency is not applied")
            raw = _read(payload, TABLE_VA, TABLE_SIZE)
            current = _role_revision([raw[i:i + RECORD_SIZE] for i in range(0, TABLE_SIZE, RECORD_SIZE)]) == REVISION
            return "applied" if current else "previous"
        return "retail"
    except (ValueError, struct.error, IndexError):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Pure, idempotent XBE patch; the caller owns writing an output copy."""

    state = status(payload)
    _require(state != "foreign", "depth-chart rows are foreign; refusing")
    _require(pools.status(payload) == "applied",
             "apply nfl2k5_position_pools with depth_chart_third_starter before depth-chart rows")
    if state == "previous":
        return _upgrade(payload)
    if state == "applied":
        return payload, {"status": "applied", "already_applied": True, "changed_bytes": 0,
                         "edits": [], "sections_repinned": [], "stride": STRIDE, "row_counts": list(ROW_COUNTS),
                         "revision": REVISION}
    buf, edits = storage.extend(payload)
    sections = _sections(buf)
    touched = {storage._section(buf).index}
    writes = [(site.label, site.va, site.after) for site in (*code_sites(), *title_sites(), *layout_sites())]
    writes.append(("depth_chart_table", TABLE_VA, _special_table(payload)))
    for label, va, after in writes:
        off = _span(buf, va, len(after))
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
                     "changed_bytes": sum(a != b for a, b in zip(payload, patched)) + len(patched) - len(payload),
                     "file_growth": len(patched) - len(payload), "table_va": hex(TABLE_VA),
                     "sections_repinned": sorted(touched), "edits": edits,
                     "dependency": "position_pools", "stride": STRIDE, "row_counts": list(ROW_COUNTS),
                     "summary_row_pitch": 25, "summary_spacing": 1, "summary_font_unchanged": True,
                     "summary_label_width": SUMMARY_LABEL_WIDTH,
                     "layout_scope": "shared depth-chart summary style 17",
                     "revision": REVISION, "runtime_witnessed": False}
