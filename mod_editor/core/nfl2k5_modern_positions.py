"""Modern-era depth-chart labels for NFL 2K5's defensive units (xemu-only, local research).

What this patch changes
-----------------------
Only the *labels* of the depth-chart / formation-subs slot records in ``.rdata``.  Nothing about
which players fill a slot changes: every record keeps its position byte (``+0x40``) and its
chain selector (``+0x44``), so the game's roster pools, the play-call personnel fill and the
franchise AI are untouched.  The full design that rewires pools (EDGE = one roster position for
4-3 ends and 3-4 outside backers, one off-ball LB pool) is data on the disc as well, but it is a
separate, larger pass; see ``MODERN_POSITIONS_2026-09-03.md``.

Where the labels live
---------------------
``.rdata 0x5140D8`` holds 44 retail slot records of ``0x48`` bytes. SPECIAL
relocates 46 records to fresh read-only storage at ``0xEE3000``. Every unit
retains stride 11; the final unit may extend through slot 12. Readers and
writers validate the complete stride and base-address instructions.

* ``+0x00`` 5-wchar abbreviation (4 characters plus NUL);
* ``+0x0A`` 27-wchar long name (26 characters plus NUL);
* ``+0x40`` roster position enum the slot draws from (``0xFE``/``0xFD`` = KR/PR specials);
* ``+0x44`` chain selector: ``0`` = the position's *rank* order (player ``+0x28`` bits 10-12),
  ``1`` = the position's *side* order (bits 13-15), which is how one roster position serves two
  starting slots (LDE/RDE, LOLB/ROLB, LCB/RCB ...).

Unit 0 = offense, unit 1 = ``4-3 Defense``, unit 2 = ``3-4 Defense``, unit 3 = special teams
(the tab callbacks ``0x243C30/60/90/C0`` store the unit in ``DAT_00C174B8``; the screen helper
``cb_00243ae0`` returns ``0x5140D8 + 0x48 * (unit * 11 + slot)``; the row lookup ``FUN_00242ae0``
walks the team roster for the record's position and chain).  Both defensive units are *views*
onto the same per-position rank/side fields, so the 4-3 and 3-4 charts show the same players
under different names, which is why the labels can be authored per unit without any code.

The eight records this patch rewrites (retail abbreviation / long name -> new):

=====  ====  ====  ===========================================  ==========================
unit   slot  VA    retail                                       new
=====  ====  ====  ===========================================  ==========================
4-3    4     0x514510  ``ROLB`` / RIGHT OUTSIDE LINE BACKER      ``SAM`` / STRONGSIDE LINEBACKER
4-3    5     0x514558  ``ILB`` / INSIDE LINE BACKER              ``MIKE`` / MIDDLE LINEBACKER
4-3    6     0x5145A0  ``LOLB`` / LEFT OUTSIDE LINE BACKER       ``WILL`` / WEAKSIDE LINEBACKER
3-4    1     0x514750  ``DT`` / DEF TACKLE                       ``NT`` / NOSE TACKLE
3-4    3     0x5147E0  ``RILB`` / RIGHT INSIDE LINE BACKER       ``WILL`` / WEAKSIDE LINEBACKER
3-4    4     0x514828  ``LILB`` / LEFT INSIDE LINE BACKER        ``MIKE`` / MIDDLE LINEBACKER
3-4    5     0x514870  ``ROLB`` / RIGHT OUTSIDE LINE BACKER      ``EDGE`` / RIGHT EDGE RUSHER
3-4    6     0x5148B8  ``LOLB`` / LEFT OUTSIDE LINE BACKER       ``EDGE`` / LEFT EDGE RUSHER
=====  ====  ====  ===========================================  ==========================

WILL/MIKE/SAM follow the chain the record already uses: the 4-3 MIKE is the ILB rank chain,
WILL the OLB rank chain (the #1 OLB) and SAM the OLB side chain (the #2 OLB); the 3-4 MIKE/WILL
are the ILB rank/side chains.  ``NT`` is the DT rank chain, i.e. the #1 DT, which is what the
in-game 3-4 personnel already fields at the nose (category code ``DT0``).

Optional (``three_four_line=True``): the two 3-4 end records (unit 2 slots 0 and 2, VAs
``0x514708`` / ``0x514798``) become ``DE`` / LEFT|RIGHT DEFENSIVE END.  Those two records are
also rewritten by the EDGE rename (``nfl2k5_edge_rename``), so this patch accepts either the
retail bytes (``LDE`` / ``RDE``) or the EDGE-applied bytes there; ``nfl2k5_edge_rename`` accepts
the ``DE`` text on those two records as compatible with either EDGE state. It is off
by default because under the retail pools those slots still draw from the DE (EDGE) roster
position, so the label is only truthful once the 3-4 line is rewired to the interior (DT) pool,
which is what ``nfl2k5_position_pools`` (Phase 2) does: it rewrites the pool fields of six records
and this module accepts either pool profile (``POOL_PROFILES``) as intact.

Everything is pattern-checked (retail or already-applied bytes only), the ``.rdata`` digest is
recomputed, and ``apply`` refuses anything but retail.  Unverified at runtime (Noah tests):
whether the four-character ``MIKE``/``WILL``/``EDGE`` labels clip in the tightest column of the
Depth Chart and Formation Subs screens (``EDGE`` already ships on the 4-3 end slots).
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Mapping, Sequence

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_depth_chart_storage import TABLE_VA as SPECIAL_TABLE_VA

IMAGE_BASE = 0x10000

SLOT_TABLE_VA = 0x005140D8
SLOT_RECORD_STRIDE = 0x48
SLOTS_PER_UNIT = 11
SLOT_TABLE_RECORDS = 44
STRIDE_INSTRUCTION_VA = 0x00243AE5  # cb_00243ae0: imul eax,eax,unit stride
UNIT_COUNT = 4                        # offense, 4-3 defense, 3-4 defense, special teams
SLOT_ABBREV_WCHARS = 5
SLOT_LONG_WCHARS = 27
SLOT_TEXT_BYTES = 2 * (SLOT_ABBREV_WCHARS + SLOT_LONG_WCHARS)    # 0x40: text, then +0x40/+0x44
UNIT_OFFENSE, UNIT_43, UNIT_34, UNIT_SPECIAL = 0, 1, 2, 3
UNIT_NAMES = {UNIT_OFFENSE: "Offense", UNIT_43: "4-3 Defense", UNIT_34: "3-4 Defense",
              UNIT_SPECIAL: "SPECIAL"}


class ModernPositionsError(ValueError):
    """The modern-positions label patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModernPositionsError(message)


def record_va(unit: int, slot: int, slots_per_unit: int = SLOTS_PER_UNIT,
              *, table_va: int = SLOT_TABLE_VA) -> int:
    """Address in either layout; the default remains retail for existing callers."""

    _require(slots_per_unit == SLOTS_PER_UNIT, "unknown slot stride")
    _require(table_va in (SLOT_TABLE_VA, SPECIAL_TABLE_VA), "unknown slot table")
    count = 13 if unit == UNIT_SPECIAL and table_va == SPECIAL_TABLE_VA else SLOTS_PER_UNIT
    _require(0 <= unit < UNIT_COUNT and 0 <= slot < count, "slot record out of range")
    return table_va + SLOT_RECORD_STRIDE * (unit * slots_per_unit + slot)


def layout_table(payload: bytes) -> int:
    """Validate the whole base-address instruction, accepting only our two tables."""
    off = _offset(payload, 0x243AED)
    for va in (SLOT_TABLE_VA, SPECIAL_TABLE_VA):
        if payload[off:off + 7] == b"\x8d\x04\xc5" + struct.pack("<I", va):
            return va
    raise ModernPositionsError("unrecognised depth-chart table address")


def layout_stride(payload: bytes) -> int:
    """Read the whole record-getter instruction, never infer layout from a label."""

    off = _offset(payload, STRIDE_INSTRUCTION_VA)
    instruction = payload[off:off + 3]
    for stride in (SLOTS_PER_UNIT,):
        if instruction == bytes((0x6B, 0xC0, stride)):
            return stride
    raise ModernPositionsError("unrecognised depth-chart record-getter stride")


@dataclass(frozen=True)
class LabelSite:
    label: str
    unit: int
    slot: int
    before: tuple[tuple[str, str], ...]     # accepted (abbreviation, long name) pairs
    after: tuple[str, str]
    optional: bool = False                  # only with three_four_line=True

    @property
    def va(self) -> int:
        return record_va(self.unit, self.slot)

    def va_for(self, slots_per_unit: int, table_va: int = SLOT_TABLE_VA) -> int:
        return record_va(self.unit, self.slot, slots_per_unit, table_va=table_va)


# The EDGE rename's bytes for the two 3-4 end records (accepted as "before" for the optional part).
_EDGE_LEFT = ("EDGE", "LEFT EDGE RUSHER")
_EDGE_RIGHT = ("EDGE", "RIGHT EDGE RUSHER")

SITES: tuple[LabelSite, ...] = (
    LabelSite("43_sam", UNIT_43, 4, (("ROLB", "RIGHT OUTSIDE LINE BACKER"),), ("SAM", "STRONGSIDE LINEBACKER")),
    LabelSite("43_mike", UNIT_43, 5, (("ILB", "INSIDE LINE BACKER"),), ("MIKE", "MIDDLE LINEBACKER")),
    LabelSite("43_will", UNIT_43, 6, (("LOLB", "LEFT OUTSIDE LINE BACKER"),), ("WILL", "WEAKSIDE LINEBACKER")),
    LabelSite("34_nt", UNIT_34, 1, (("DT", "DEF TACKLE"),), ("NT", "NOSE TACKLE")),
    LabelSite("34_will", UNIT_34, 3, (("RILB", "RIGHT INSIDE LINE BACKER"),), ("WILL", "WEAKSIDE LINEBACKER")),
    LabelSite("34_mike", UNIT_34, 4, (("LILB", "LEFT INSIDE LINE BACKER"),), ("MIKE", "MIDDLE LINEBACKER")),
    LabelSite("34_edge_right", UNIT_34, 5, (("ROLB", "RIGHT OUTSIDE LINE BACKER"),), ("EDGE", "RIGHT EDGE RUSHER")),
    LabelSite("34_edge_left", UNIT_34, 6, (("LOLB", "LEFT OUTSIDE LINE BACKER"),), ("EDGE", "LEFT EDGE RUSHER")),
    LabelSite("34_de_left", UNIT_34, 0, (("LDE", "LEFT DEF END"), _EDGE_LEFT), ("DE", "LEFT DEFENSIVE END"), True),
    LabelSite("34_de_right", UNIT_34, 2, (("RDE", "RIGHT DEF TACKLE"), _EDGE_RIGHT), ("DE", "RIGHT DEFENSIVE END"), True),
)

# What the untouched pool fields of every touched record must read (position enum, chain).
# Positions: 0xA = OLB, 0xB = ILB, 0xF = DT, 0x10 = DE.  These are asserted, never written here.
EXPECTED_POOLS: Mapping[str, tuple[int, int]] = {
    "43_sam": (0xA, 1), "43_mike": (0xB, 0), "43_will": (0xA, 0),
    "34_nt": (0xF, 0), "34_will": (0xB, 1), "34_mike": (0xB, 0),
    "34_edge_right": (0xA, 1), "34_edge_left": (0xA, 0),
    "34_de_left": (0x10, 0), "34_de_right": (0x10, 1),
}
# The same fields after the Phase-2 pool rewrite (``nfl2k5_position_pools``): one LB pool (enum 11,
# SAM = side chain row 1 via the depth-chart cave), 3-4 EDGE slots on the DE/EDGE enum, 3-4 ends on
# the interior (DT) enum.  Either profile is accepted as intact, mixed fields are foreign.
ONE_POOL_POOLS: Mapping[str, tuple[int, int]] = {
    "43_sam": (0xB, 3), "43_mike": (0xB, 0), "43_will": (0xB, 1),
    "34_nt": (0xF, 0), "34_will": (0xB, 1), "34_mike": (0xB, 0),
    "34_edge_right": (0x10, 1), "34_edge_left": (0x10, 0),
    "34_de_left": (0xF, 1), "34_de_right": (0xF, 3),
}
POOL_PROFILES: Mapping[str, Mapping[str, tuple[int, int]]] = {"retail": EXPECTED_POOLS, "one_pool": ONE_POOL_POOLS}


def _utf16(text: str, slot: int) -> bytes:
    raw = text.encode("utf-16le") + b"\0\0"
    _require(len(raw) <= slot, f"{text!r} does not fit a {slot}-byte slot")
    return raw + b"\0" * (slot - len(raw))


def slot_text(abbrev: str, long_name: str) -> bytes:
    """The 64 text bytes of a slot record (abbreviation field + long-name field)."""

    return _utf16(abbrev, 2 * SLOT_ABBREV_WCHARS) + _utf16(long_name, 2 * SLOT_LONG_WCHARS)


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise ModernPositionsError(f"VA 0x{va:x} is in no section")


def selected_sites(three_four_line: bool = False) -> tuple[LabelSite, ...]:
    return tuple(site for site in SITES if three_four_line or not site.optional)


def read_record(payload: bytes, unit: int, slot: int) -> dict[str, object]:
    """Decode one slot record: abbreviation, long name, position enum, chain."""

    va = record_va(unit, slot, layout_stride(payload), table_va=layout_table(payload))
    off = _offset(payload, va)
    raw = payload[off: off + SLOT_RECORD_STRIDE]
    _require(len(raw) == SLOT_RECORD_STRIDE, "slot record is truncated")
    abbrev = raw[:2 * SLOT_ABBREV_WCHARS].decode("utf-16le", "replace").split("\0")[0]
    long_name = raw[2 * SLOT_ABBREV_WCHARS: SLOT_TEXT_BYTES].decode("utf-16le", "replace").split("\0")[0]
    position, chain = struct.unpack_from("<II", raw, SLOT_TEXT_BYTES)
    return {"unit": unit, "slot": slot, "va": va, "abbreviation": abbrev,
            "long_name": long_name, "position": position, "chain": chain}


def read_units(payload: bytes) -> dict[str, list[dict[str, object]]]:
    """Every defensive slot record of both defensive units, as the screens would show them."""

    return {UNIT_NAMES[unit]: [read_record(payload, unit, slot) for slot in range(layout_stride(payload))]
            for unit in (UNIT_43, UNIT_34)}


def _site_state(payload: bytes, site: LabelSite) -> str:
    off = _offset(payload, site.va_for(layout_stride(payload), layout_table(payload)))
    got = payload[off: off + SLOT_TEXT_BYTES]
    if got == slot_text(*site.after):
        return "applied"
    if any(got == slot_text(abbrev, long_name) for abbrev, long_name in site.before):
        return "retail"
    return "foreign"


def pool_profile(payload: bytes, sites: Sequence[LabelSite] | None = None) -> str | None:
    """Name of the pool profile every record's (position, chain) matches, or None when mixed."""

    sites = SITES if sites is None else sites
    stride = layout_stride(payload)
    for name, profile in POOL_PROFILES.items():
        if all(struct.unpack_from("<II", payload, _offset(payload, site.va_for(stride, layout_table(payload))) + SLOT_TEXT_BYTES) == profile[site.label]
               for site in sites):
            return name
    return None


def _pools_intact(payload: bytes, sites: Sequence[LabelSite]) -> bool:
    return pool_profile(payload, sites) is not None


def site_states(payload: bytes, three_four_line: bool = False) -> dict[str, str]:
    try:
        sites = selected_sites(three_four_line)
        states = {site.label: _site_state(payload, site) for site in sites}
        if not _pools_intact(payload, sites):
            return {label: "foreign" for label in states}
        return states
    except (ModernPositionsError, ValueError, struct.error):
        return {site.label: "foreign" for site in selected_sites(three_four_line)}


def status(payload: bytes, three_four_line: bool = False) -> str:
    """'retail', 'applied', or 'foreign' (bytes match neither; refuse to touch)."""

    states = set(site_states(payload, three_four_line).values())
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def apply(payload: bytes, three_four_line: bool = False) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; refuses anything but retail sites."""

    state = status(payload, three_four_line)
    _require(state == "retail", f"modern-positions sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched: set[int] = set()
    edits = []
    stride = layout_stride(payload)
    for site in selected_sites(three_four_line):
        va = site.va_for(stride, layout_table(payload))
        off = _offset(payload, va)
        before = bytes(buf[off: off + SLOT_TEXT_BYTES])
        after = slot_text(*site.after)
        _require(len(before) == len(after) == SLOT_TEXT_BYTES, f"{site.label}: record length")
        buf[off: off + SLOT_TEXT_BYTES] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": site.label, "unit": UNIT_NAMES[site.unit], "slot": site.slot,
                      "va": f"0x{va:x}", "file_offset": f"0x{off:x}",
                      "before": before.decode("utf-16le", "replace").replace("\0", "|").rstrip("|"),
                      "after": f"{site.after[0]} / {site.after[1]}"})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched, three_four_line) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
                     "three_four_line": three_four_line,
                     "units": read_units(patched)}


__all__ = [
    "EXPECTED_POOLS", "LabelSite", "ModernPositionsError", "ONE_POOL_POOLS", "POOL_PROFILES", "SITES", "SLOT_ABBREV_WCHARS",
    "SLOT_LONG_WCHARS", "SLOT_RECORD_STRIDE", "SLOT_TABLE_VA", "SLOT_TEXT_BYTES", "UNIT_34",
    "UNIT_43", "UNIT_NAMES", "apply", "pool_profile", "read_record", "read_units", "record_va", "selected_sites",
    "site_states", "slot_text", "status", "layout_stride", "layout_table", "SLOTS_PER_UNIT", "SPECIAL_TABLE_VA",
    "SLOT_TABLE_RECORDS", "STRIDE_INSTRUCTION_VA",
]
