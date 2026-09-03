"""Rename the Defensive End position to EDGE everywhere NFL 2K5 shows it (xemu-only, local research).

Where the position text lives
-----------------------------
The executable keeps its UTF-16 string literals in the ``.string_`` section (VA ``0xE60320``
maps to file ``0xAEF000``; the ``.data`` section's raw data ends before it, which is why a
naive ".data continues" address is off by ``0x3669A0``).  Nothing copies that section anywhere:
every consumer holds the absolute ``.string_`` address, either as a code immediate or as an entry
of a pointer table in ``.rdata``/``.data``.  Strings are NUL-terminated and 4-byte aligned, so a
string may shrink in place (zero-fill the slot) but may not grow: a longer replacement has to be
hosted elsewhere and the pointers repointed.

"DE" reaches the screen through five pointer-table entries and one legend string:

* ``.rdata 0x4F2710``  position-enum -> abbreviation table (accessor ``0xE5F90``; menus,
  rosters, player cards, draft, scouting, franchise screens) — entry 16 (DE)
* ``.rdata 0x4F26C8``  16-way variant with OLB/ILB merged into LB (accessor ``0xE5FA0``)
* ``.rdata 0x4F6928``  in-game HUD position table (``0xF9A12``: the "%s %u" position + number
  overlay), entry 12
* ``.data 0xAAB800``   depth-chart style table (QB P K KH KR ... DE DT OLB LB FS SS DB), entry 12
* ``.data 0xAC2698``   franchise table (``0x221F03``), entry 12
* ``.data 0xA89938``   the play-call Package menu legend ``|CIRCLE|SWAP DE``

All six are repointed to a new string hosted in the XBE header's boot-logo bitmap (never read by
the game; the catch/accel/draft caves already live there): ``|CIRCLE|SWAP EDGE`` at
``0x10C88``, whose tail ``EDGE`` at ``0x10CA2`` is the abbreviation.

The long names are shrunk in place: four ``Defensive End`` slots (28 bytes) become
``Edge Rusher`` and fourteen ``Defensive Ends`` slots (32 bytes) become ``Edge Rushers``.

The formation-slot label records in ``.rdata`` (``0x5140D8 + 0x48 * (11 * unit + slot)``:
5-wchar abbreviation at +0, 27-wchar long name at +0x0A, two dwords at +0x40) hold ``LDE`` /
``RDE`` with ``LEFT DEF END`` / ``RIGHT DEF END`` (one retail record says ``RIGHT DEF TACKLE``
for the right end).  The abbreviation field cannot hold ``LEDGE`` (five characters plus NUL is
one wchar too many, and the long name starts right behind it), so both sides become ``EDGE``
and the side moves into the long name: ``LEFT EDGE RUSHER`` / ``RIGHT EDGE RUSHER``.

On the disc, 247 historic-team players are literally named "<Team> Def End" (ROST resources in
pack ``0``, 16-byte last-name allocations, uniquely referenced) and two trivia questions say
"this talented Defensive End" (TRIV bank in pack ``C``).  Those are fixed-span rewrites inside
the copied image: ``Def End`` -> ``Edge`` and ``Defensive End`` -> ``Edge Rusher``.

Everything is pattern-checked (retail or already-applied bytes only), the ``.rdata``/``.data``/
``.string_`` digests are recomputed, the header logo bytes carry no digest.  Unverified at runtime
(Noah tests): the four-character ``EDGE`` may be tight in the narrowest HUD/menu columns.
"""

from __future__ import annotations

import hashlib
import os

from mod_editor.core import platform_compat
import struct
from typing import Mapping, Sequence

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

IMAGE_BASE = 0x10000
LOGO_END_VA = 0x00010CC2

ABBREVIATION = "EDGE"
LEGEND_TEXT = "|CIRCLE|SWAP " + ABBREVIATION          # play-call Package menu legend
LEGEND_VA = 0x00010C88                                  # header boot-logo bitmap, after the draft cave
EDGE_VA = LEGEND_VA + 2 * len("|CIRCLE|SWAP ")          # 0x10CA2: the legend's tail is the abbreviation
LONG_SINGULAR = "Edge Rusher"
LONG_PLURAL = "Edge Rushers"
SLOT_LEFT_LONG = "LEFT EDGE RUSHER"
SLOT_RIGHT_LONG = "RIGHT EDGE RUSHER"

# retail boot-logo bytes at file 0xC88 (VA 0x10C88), 36 of them: the host site
RETAIL_LOGO_C88 = bytes.fromhex("d3f9330d4b0547130303491373a793070343a3c3a37313051349030b0353d3f3e3731309")

# (label, pointer VA, retail target VA, new target VA)
POINTER_SITES: tuple[tuple[str, int, int, int], ...] = (
    ("abbrev_enum_table", 0x004F2710, 0x00E69C4C, EDGE_VA),
    ("abbrev_group16_table", 0x004F26C8, 0x00E69C4C, EDGE_VA),
    ("abbrev_hud_table", 0x004F6928, 0x00E6C290, EDGE_VA),
    ("abbrev_depth_table", 0x00AAB800, 0x00E83D64, EDGE_VA),
    ("abbrev_franchise_table", 0x00AC2698, 0x00E87ED0, EDGE_VA),
    ("package_legend", 0x00A89938, 0x00E677E0, LEGEND_VA),
)

# "Defensive End" (28-byte slots) and "Defensive Ends" (32-byte slots) in .string_
SINGULAR_SITES: tuple[int, ...] = (0x00E69DDC, 0x00E83C44, 0x00EABD70, 0x00EAD424)
PLURAL_SITES: tuple[int, ...] = (
    0x00E69F8C, 0x00EA40EC, 0x00EA44E0, 0x00EA4720, 0x00EA9B60, 0x00EAB418, 0x00EAB62C,
    0x00EAB9B8, 0x00EADA3C, 0x00EAE8AC, 0x00EAF53C, 0x00EB3ABC, 0x00EB5818, 0x00EBBFB8,
)
SINGULAR_SLOT = 28
PLURAL_SLOT = 32

# formation-slot label records: (record VA, retail abbrev, retail long, new long)
SLOT_RECORD_STRIDE = 0x48
SLOT_ABBREV_WCHARS = 5
SLOT_LONG_WCHARS = 27
SLOT_RECORDS: tuple[tuple[str, int, str, str, str], ...] = (
    ("slot_unit1_lde", 0x005143F0, "LDE", "LEFT DEF END", SLOT_LEFT_LONG),
    ("slot_unit1_rde", 0x005144C8, "RDE", "RIGHT DEF END", SLOT_RIGHT_LONG),
    ("slot_unit2_lde", 0x00514708, "LDE", "LEFT DEF END", SLOT_LEFT_LONG),
    ("slot_unit2_rde", 0x00514798, "RDE", "RIGHT DEF TACKLE", SLOT_RIGHT_LONG),   # retail typo record
)

# The Phase-1/Phase-2 scheme patches (nfl2k5_modern_positions three_four_line, nfl2k5_position_pools)
# relabel the two 3-4 end records "DE" / LEFT|RIGHT DEFENSIVE END once those slots draw from the
# interior pool; that text counts as "applied" here so every module's status stays truthful.
SLOT_RECORD_ALTERNATIVES: Mapping[str, tuple[tuple[str, str], ...]] = {
    "slot_unit2_lde": (("DE", "LEFT DEFENSIVE END"),),
    "slot_unit2_rde": (("DE", "RIGHT DEFENSIVE END"),),
}

# The strings this patch retires.  They stay in .string_ (nothing points at them any more) and
# are listed so a reader can find them: "DE" x4 and "|CIRCLE|SWAP DE".
RETIRED_STRINGS: tuple[tuple[str, int], ...] = (
    ("DE (enum/group tables)", 0x00E69C4C), ("DE (HUD)", 0x00E6C290), ("DE (depth)", 0x00E83D64),
    ("DE (franchise)", 0x00E87ED0), ("|CIRCLE|SWAP DE", 0x00E677E0),
)


class EdgeRenameError(ValueError):
    """The EDGE rename cannot be applied to this executable or image."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EdgeRenameError(message)


def _utf16(text: str, slot: int) -> bytes:
    raw = text.encode("utf-16le") + b"\0\0"
    _require(len(raw) <= slot, f"{text!r} does not fit a {slot}-byte slot")
    return raw + b"\0" * (slot - len(raw))


def legend_bytes() -> bytes:
    raw = _utf16(LEGEND_TEXT, 2 * len(LEGEND_TEXT) + 2)
    _require(raw[EDGE_VA - LEGEND_VA:] == _utf16(ABBREVIATION, 2 * len(ABBREVIATION) + 2),
             "legend tail is not the abbreviation")
    return raw


def _slot_record(abbrev: str, long_name: str) -> bytes:
    return _utf16(abbrev, 2 * SLOT_ABBREV_WCHARS) + _utf16(long_name, 2 * SLOT_LONG_WCHARS)


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise EdgeRenameError(f"VA 0x{va:x} is in no section")


def _sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    legend = legend_bytes()
    _require(LEGEND_VA + len(legend) <= LOGO_END_VA, "host string overruns the boot-logo bitmap")
    _require(len(RETAIL_LOGO_C88) == len(legend), "retail logo record does not cover the host string")
    sites: list[tuple[str, int, bytes, bytes]] = [
        ("host_legend_edge", _offset(payload, LEGEND_VA), RETAIL_LOGO_C88, legend),
    ]
    for label, ptr_va, old, new in POINTER_SITES:
        sites.append((label, _offset(payload, ptr_va), struct.pack("<I", old), struct.pack("<I", new)))
    for index, va in enumerate(SINGULAR_SITES):
        sites.append((f"long_singular_{index}", _offset(payload, va),
                      _utf16("Defensive End", SINGULAR_SLOT), _utf16(LONG_SINGULAR, SINGULAR_SLOT)))
    for index, va in enumerate(PLURAL_SITES):
        sites.append((f"long_plural_{index}", _offset(payload, va),
                      _utf16("Defensive Ends", PLURAL_SLOT), _utf16(LONG_PLURAL, PLURAL_SLOT)))
    for label, va, abbrev, old_long, new_long in SLOT_RECORDS:
        sites.append((label, _offset(payload, va), _slot_record(abbrev, old_long),
                      _slot_record(ABBREVIATION, new_long)))
    return sites


def status(payload: bytes) -> str:
    """'retail', 'applied', or 'foreign' (bytes match neither; refuse to touch)."""

    try:
        sites = _sites(payload)
    except (EdgeRenameError, ValueError, struct.error):
        return "foreign"
    states = set()
    for label, off, before, after in sites:
        got = payload[off: off + len(before)]
        also = tuple(_slot_record(a, l) for a, l in SLOT_RECORD_ALTERNATIVES.get(label, ()))
        states.add("retail" if got == before else "applied" if got == after or got in also else "foreign")
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; refuses anything but retail sites."""

    state = status(payload)
    _require(state == "retail", f"EDGE-rename sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    header = _header_size(payload)
    touched: set[int] = set()
    edits = []
    for label, off, before, after in _sites(payload):
        _require(len(before) == len(after), f"{label}: replacement length differs")
        buf[off: off + len(after)] = after
        if off >= header:
            touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "file_offset": f"0x{off:x}", "before": before.hex(), "after": after.hex()})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
                     "abbreviation": ABBREVIATION, "long_name": LONG_SINGULAR, "legend": LEGEND_TEXT}


# ---------------------------------------------------------------------------------------------
# Disc side: historic-roster player names (pack 0, ROST) and two trivia questions (pack C, TRIV)
# ---------------------------------------------------------------------------------------------

ROST_PACK = "vc_53450030/0"
TRIV_PACK = "vc_53450030/c"
ROST_ALLOCATION = 16
ROST_BEFORE = "Def End".encode("utf-16le") + b"\0\0"                     # exactly the 16-byte allocation
ROST_AFTER = "Edge".encode("utf-16le") + b"\0\0" + b"\0" * (ROST_ALLOCATION - 10)

# pack-0 byte offsets of the 247 "Def End" last-name allocations (historic teams, primary pool,
# reference count 1, verified against the retail pack and the studio's roster parser)
ROST_LAST_NAME_OFFSETS: tuple[int, ...] = (
    0x1870F70, 0x1870F94, 0x1870FB8, 0x1870FDC, 0x1871000, 0x1872F40, 0x1872F60, 0x1872F80,
    0x1874F4C, 0x1874F6C, 0x1874F8C, 0x1874FAC, 0x1876F9E, 0x1876FBC, 0x187701A, 0x1878F3C,
    0x1878F58, 0x1878F74, 0x1878F90, 0x1878FAC, 0x187AF3C, 0x187AF58, 0x187AF74, 0x187AF90,
    0x187CFBC, 0x187CFDE, 0x187D000, 0x187D022, 0x1880F12, 0x1880F2E, 0x1880F4A, 0x1882EF0,
    0x1882F0C, 0x1885010, 0x1885030, 0x1885050, 0x1885070, 0x1886FEA, 0x188700A, 0x188702A,
    0x1888FC8, 0x1888FE8, 0x1889008, 0x1889028, 0x1889048, 0x188AF8C, 0x188AFAC, 0x188AFCC,
    0x188AFEC, 0x188CF84, 0x188CFA4, 0x188CFC4, 0x188CFE4, 0x188EFC6, 0x188EFE6, 0x188F006,
    0x188F026, 0x188F046, 0x1890F82, 0x1890FA2, 0x1890FC2, 0x1892F86, 0x1892FA6, 0x1892FC6,
    0x1892FE6, 0x1893006, 0x1893026, 0x1894F82, 0x1894F9E, 0x1896FBE, 0x1896FDA, 0x1896FF6,
    0x1897012, 0x189903A, 0x189905A, 0x189AFB2, 0x189AFD2, 0x189AFF2, 0x189B030, 0x189EF6C,
    0x189EF88, 0x189EFA4, 0x189EFC0, 0x18A0F2A, 0x18A0F66, 0x18A0F86, 0x18A2F5A, 0x18A2F78,
    0x18A2F96, 0x18A2FB4, 0x18A4FA0, 0x18A4FBE, 0x18A6F80, 0x18A6F9E, 0x18A8FD2, 0x18A8FF4,
    0x18A9016, 0x18A9038, 0x18AAFB2, 0x18AAFD4, 0x18AAFF6, 0x18AB018, 0x18ACFA0, 0x18ACFC0,
    0x18ACFE0, 0x18AD000, 0x18AEFBE, 0x18AEFDE, 0x18AEFFE, 0x18B0F8C, 0x18B0FC8, 0x18B0FE8,
    0x18B2FE0, 0x18B3002, 0x18B3024, 0x18B4F8A, 0x18B4FAC, 0x18B4FCE, 0x18B4FF0, 0x18B5012,
    0x18B8FB4, 0x18B8FD2, 0x18B8FF0, 0x18BB044, 0x18BCEF6, 0x18BCF14, 0x18BCF32, 0x18BCF50,
    0x18BEF3E, 0x18BEF5C, 0x18BEF7A, 0x18C0EFE, 0x18C0F1C, 0x18C0F3A, 0x18C2F46, 0x18C4FB2,
    0x18C4FCC, 0x18C4FE6, 0x18C5000, 0x18C6F60, 0x18C6F7A, 0x18C6F94, 0x18C6FAE, 0x18C6FE0,
    0x18C8EF6, 0x18C8F16, 0x18C8F36, 0x18CAF86, 0x18CAFA6, 0x18CCFB0, 0x18CCFD0, 0x18CCFF0,
    0x18CD010, 0x18CF026, 0x18CF044, 0x18CF062, 0x18CF080, 0x18CF09E, 0x18D0FE6, 0x18D1004,
    0x18D1022, 0x18D1040, 0x18D302C, 0x18D4FDC, 0x18D4FFE, 0x18D5020, 0x18D6FDC, 0x18D6FFE,
    0x18D7020, 0x18D7042, 0x18D8FE6, 0x18D9008, 0x18DB016, 0x18DB030, 0x18DB04A, 0x18DF064,
    0x18DF086, 0x18DF0A8, 0x18DF0CA, 0x18E1064, 0x18E1086, 0x18E10A8, 0x18E10CA, 0x18E3000,
    0x18E3022, 0x18E3044, 0x18E4F9A, 0x18E4FB6, 0x18E4FD2, 0x18E4FEE, 0x18E6F9A, 0x18E6FB6,
    0x18E6FD2, 0x18E6FEE, 0x18E700A, 0x18E8F9A, 0x18E8FB6, 0x18E8FD2, 0x18E8FEE, 0x18E900A,
    0x18E9026, 0x18E9042, 0x18E905E, 0x18ECFEA, 0x18ED00C, 0x18ED02E, 0x18EF03E, 0x18EF060,
    0x18EF082, 0x18F0FC6, 0x18F0FEE, 0x18F1016, 0x18F103E, 0x18F2FA4, 0x18F2FCC, 0x18F2FF4,
    0x18F6FC4, 0x18F6FE2, 0x18F7000, 0x18F701E, 0x18F8FA8, 0x18F8FC6, 0x18F8FE4, 0x18FAF8A,
    0x18FAFDC, 0x18FAFFA, 0x18FCF62, 0x18FCF84, 0x18FCFA6, 0x18FCFC8, 0x18FCFEA, 0x18FEEE2,
    0x18FEF04, 0x18FEF26, 0x1900F82, 0x1900FA4, 0x1900FC6, 0x1900FE8, 0x1902FEC, 0x190300A,
    0x1903028, 0x1903046, 0x1903064, 0x1903082, 0x1904FEC, 0x190500A, 0x1905028,
)

# The two trivia questions: (label, pack-C offset, allocation, sha256 of the retail allocation,
# replacement text).  The retail sentence is identified by its digest only.
TRIV_SITES: tuple[tuple[str, int, int, str, str], ...] = (
    ("triv_question_494", 0x0A9C0238, 190,
     "99feb242263adfd5ae664f162e3d0b94d283b012ea416794a0680ab06cf8ab7b",
     "Carolina Panthers selected this talented Edge Rusher in the 1st round of the 2002 NFL Draft."),
    ("triv_question_576", 0x0A9C6492, 184,
     "775076d1c04af19d32ba3a1a17fcd208e47536a8e13b62716c87888cefb90fba",
     "St. Louis Rams selected this talented Edge Rusher in the 1st round of the 1998 NFL Draft."),
)


def _triv_after(text: str, allocation: int) -> bytes:
    return _utf16(text, allocation)


def disc_site_states(read) -> dict[str, list[tuple[str, int, str]]]:
    """Classify every disc site.  ``read(pack, offset, size)`` returns bytes from the copy."""

    rost: list[tuple[str, int, str]] = []
    for index, off in enumerate(ROST_LAST_NAME_OFFSETS):
        got = read(ROST_PACK, off, ROST_ALLOCATION)
        rost.append((f"rost_last_name_{index}", off,
                     "retail" if got == ROST_BEFORE else "applied" if got == ROST_AFTER else "foreign"))
    triv: list[tuple[str, int, str]] = []
    for label, off, allocation, retail_sha, text in TRIV_SITES:
        got = read(TRIV_PACK, off, allocation)
        digest = hashlib.sha256(got).hexdigest()
        triv.append((label, off, "retail" if digest == retail_sha
                     else "applied" if got == _triv_after(text, allocation) else "foreign"))
    return {"rost": rost, "triv": triv}


def summarize_disc(states: Mapping[str, Sequence[tuple[str, int, str]]]) -> dict[str, object]:
    out: dict[str, object] = {}
    overall = set()
    for kind, rows in states.items():
        counts = {"retail": 0, "applied": 0, "foreign": 0}
        for _label, _off, state in rows:
            counts[state] += 1
        out[kind] = counts
        overall.update(s for s, n in counts.items() if n)
    out["status"] = ("retail" if overall == {"retail"} else "applied" if overall == {"applied"}
                     else "foreign" if overall == {"foreign"} else "partial")
    return out


def disc_status(descriptor: int, entries: Mapping[str, object]) -> dict[str, object]:
    """Status of the disc-side sites in an open image (``entries`` from ``parse_xdvdfs``)."""

    def read(pack: str, offset: int, size: int) -> bytes:
        entry = entries.get(pack)
        _require(entry is not None, f"disc image has no {pack}")
        _require(offset + size <= int(entry.size), f"{pack} is too small for offset 0x{offset:x}")
        return platform_compat.pread(descriptor, size, int(entry.byte_offset) + offset)

    return summarize_disc(disc_site_states(read))


def apply_disc(descriptor: int, entries: Mapping[str, object], pwrite) -> dict[str, object]:
    """Rewrite every retail disc site in the open COPY; already-applied and foreign sites are
    left alone and counted.  ``pwrite(fd, data, offset)`` must return the byte count."""

    def read(pack: str, offset: int, size: int) -> bytes:
        entry = entries.get(pack)
        _require(entry is not None, f"disc image has no {pack}")
        _require(offset + size <= int(entry.size), f"{pack} is too small for offset 0x{offset:x}")
        return platform_compat.pread(descriptor, size, int(entry.byte_offset) + offset)

    before = disc_site_states(read)
    written: list[dict[str, object]] = []
    for kind, rows in before.items():
        for label, off, state in rows:
            if state != "retail":
                continue
            if kind == "rost":
                pack, data = ROST_PACK, ROST_AFTER
            else:
                allocation, text = next((a, t) for l, o, a, _p, t in TRIV_SITES if l == label)
                pack, data = TRIV_PACK, _triv_after(text, allocation)
            absolute = int(entries[pack].byte_offset) + off
            count = pwrite(descriptor, data, absolute)
            _require(count == len(data), f"short write at {label}")
            written.append({"label": label, "pack": pack, "pack_offset": f"0x{off:x}",
                            "image_offset": f"0x{absolute:x}", "length": len(data)})
    after = summarize_disc(disc_site_states(read))
    return {"before": summarize_disc(before), "after": after, "written": written,
            "changed_bytes": sum(int(row["length"]) for row in written)}


__all__ = [
    "ABBREVIATION", "EDGE_VA", "EdgeRenameError", "LEGEND_TEXT", "LEGEND_VA", "LONG_PLURAL",
    "LONG_SINGULAR", "PLURAL_SITES", "POINTER_SITES", "RETAIL_LOGO_C88", "RETIRED_STRINGS", "SLOT_RECORD_ALTERNATIVES",
    "ROST_LAST_NAME_OFFSETS", "SINGULAR_SITES", "SLOT_RECORDS", "TRIV_SITES", "apply",
    "apply_disc", "disc_site_states", "disc_status", "legend_bytes", "status", "summarize_disc",
]
