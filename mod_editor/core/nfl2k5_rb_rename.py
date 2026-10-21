"""Rename the Halfback position to Running Back (RB) everywhere NFL 2K5 shows it (display text only).

Noah, 2026-10-20: "also rename halfback to running back (RB) everywhere".

What changes
------------
Only UTF-16 display strings in ``default.xbe``.  Position codes, roster records, ratings, pools,
chains, play data and every pointer stay exactly as they are; nothing is repointed and nothing is
hosted in a cave.  Every string is rewritten in place inside its own retail slot (``.string_``
literals are NUL-terminated and 4-byte aligned, so a string may shrink or keep its length but never
grow), so the abbreviation "HB" becomes "RB" (same length) and a long name becomes "Running Back"
only where the slot has room for it.

The sites (retail VA, slot bytes, consumer; every consumer found by an exhaustive scan of the
executable for the literal's absolute address):

* ``0xE69C18`` "HB" (8): position-enum abbreviation tables ``0x4F26A4`` / ``0x4F26EC`` (accessors
  ``0xE5F90`` / ``0xE5FA0``: menus, rosters, player cards, draft, scouting, franchise screens and the
  MyPlayer HUD label)
* ``0xE6C280`` "HB" (8): in-game HUD position table ``0x4F6920`` (the "%s %u" position + number overlay)
* ``0xE83D5C`` "HB" (8): depth-chart style table ``0xAAB7FC``
* ``0xE87EC0`` "HB" (8): franchise table ``0xAC2690``
* ``0xE7CADC`` "HB" (8): formation label drawn by code at ``0x144881`` (beside WR/TE/FB/DL/LB/DB)
* ``0xE67670`` "|SQUARE| SUB HB" (32): play-call Package menu legend (``0xA89908``)
* ``0xE9836C`` "HB: %d%%" (20): formatted by code at ``0x2B0B8A`` / ``0x2B0C4C``
* ``0xEAC610`` / ``0xEAC628`` / ``0xEAC63C`` "Finesse HB" / "Power HB" / "Balanced HB": the ball
  carrier player-style names (table entries ``0x556B3C`` / ``0x556BB0`` / ``0x556C24``)
* four "Halfback" long names (20-byte slots) and fifteen "Halfbacks" plurals (20-byte slots), each
  reached only through ``.rdata``/``.data`` pointer tables (enum long names ``0x4F2734``, Create
  Player's private table ``0x555AFC``, the Pro Bowl HB tab ``0x549208``, position filters ...)
* the depth-chart / formation-subs offense slot record 1 (``HB`` / ``HALF BACK``) in whichever slot
  table is active (retail ``0x5140D8`` or the relocated SPECIAL table ``0xEE3000``): its 27-wchar
  long-name field has room, so it becomes ``RB`` / ``RUNNING BACK``.  Its pool fields (position 7,
  chain 0) are asserted and never written.

Room decisions (recorded): "Running Back" needs 26 bytes and "Running Backs" 28; the "Halfback" and
"Halfbacks" slots hold 20 bytes (9 characters), so those become "RB" and "RBs".  Full long names
there would need new read-only strings in allocator-owned space (a new ``nfl2k5_xbe_space`` request,
like ``nfl2k5_hback``), which changes the shared allocation layout; that was not done for the
2026-10-20 release.  "FB"/"Fullback" and the H-back companion (``nfl2k5_hback``) are untouched.

The patch is pattern-checked (retail or already-applied bytes only; anything else is refused), the
touched sections' digests are recomputed, and the file never grows.  Unverified at runtime (Noah
tests): nothing should clip, since every replacement is as long as or shorter than retail.
"""
from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from . import nfl2k5_modern_positions as modern

OWNER = "nfl2k5_rb_rename"
BUILD_CAPTION = "Halfback is Running Back (RB)"
HELP_TEXT = ("Every screen that showed the ball carrier as HB or Halfback now says RB (depth chart: RUNNING "
             "BACK). Text only: position codes, ratings and rosters are unchanged. Long names whose retail "
             "space is too small read RB / RBs. Enabled in all SOFTDRINK presets.")

IMAGE_BASE = 0x10000
ABBREVIATION = "RB"
LONG_SINGULAR = "RB"        # 20-byte slots cannot hold "Running Back" (26 bytes with its NUL)
LONG_PLURAL = "RBs"         # 20-byte slots cannot hold "Running Backs" (28 bytes)
SLOT_LONG = "RUNNING BACK"  # the depth-chart record's 27-wchar long-name field has room

# (label, VA, slot bytes, retail text, new text)
STRING_SITES: tuple[tuple[str, int, int, str, str], ...] = (
    ("package_legend", 0x00E67670, 32, "|SQUARE| SUB HB", "|SQUARE| SUB RB"),
    ("abbrev_enum_tables", 0x00E69C18, 8, "HB", ABBREVIATION),
    ("abbrev_hud_table", 0x00E6C280, 8, "HB", ABBREVIATION),
    ("abbrev_formation_label", 0x00E7CADC, 8, "HB", ABBREVIATION),
    ("abbrev_depth_table", 0x00E83D5C, 8, "HB", ABBREVIATION),
    ("abbrev_franchise_table", 0x00E87EC0, 8, "HB", ABBREVIATION),
    ("share_format", 0x00E9836C, 20, "HB: %d%%", "RB: %d%%"),
    ("style_finesse", 0x00EAC610, 24, "Finesse HB", "Finesse RB"),
    ("style_power", 0x00EAC628, 20, "Power HB", "Power RB"),
    ("style_balanced", 0x00EAC63C, 24, "Balanced HB", "Balanced RB"),
)
SINGULAR_SITES: tuple[int, ...] = (0x00E69D04, 0x00E83C30, 0x00EABC98, 0x00EAD36C)
PLURAL_SITES: tuple[int, ...] = (
    0x00E69EA8, 0x00E986F4, 0x00EA4018, 0x00EA440C, 0x00EA464C, 0x00EA9AB4, 0x00EAB344, 0x00EAB558,
    0x00EAB8E4, 0x00EAD968, 0x00EAE7D8, 0x00EAF468, 0x00EB39E8, 0x00EB5744, 0x00EBBEE4,
)
LONG_SLOT = 20

# depth-chart / formation-subs slot record: offense unit, slot 1
SLOT_UNIT, SLOT_INDEX = modern.UNIT_OFFENSE, 1
SLOT_RETAIL = ("HB", "HALF BACK")
SLOT_AFTER = (ABBREVIATION, SLOT_LONG)
SLOT_POOL = (7, 0)          # HB enum, rank chain: asserted, never written


class RbRenameError(ValueError):
    """The RB rename cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RbRenameError(message)


def _utf16(text: str, slot: int) -> bytes:
    raw = text.encode("utf-16le") + b"\0\0"
    _require(len(raw) <= slot, f"{text!r} does not fit a {slot}-byte slot")
    return raw + b"\0" * (slot - len(raw))


def slot_record_text(retail: bool) -> bytes:
    return modern.slot_text(*(SLOT_RETAIL if retail else SLOT_AFTER))


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + struct.unpack_from("<I", payload, 0x108)[0]:
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise RbRenameError(f"VA 0x{va:x} is in no section")


def string_sites() -> list[tuple[str, int, bytes, bytes]]:
    """(label, VA, retail bytes, applied bytes) for every .string_ literal, padding included."""
    out = [(label, va, _utf16(old, slot), _utf16(new, slot)) for label, va, slot, old, new in STRING_SITES]
    out += [(f"long_singular_{i}", va, _utf16("Halfback", LONG_SLOT), _utf16(LONG_SINGULAR, LONG_SLOT))
            for i, va in enumerate(SINGULAR_SITES)]
    out += [(f"long_plural_{i}", va, _utf16("Halfbacks", LONG_SLOT), _utf16(LONG_PLURAL, LONG_SLOT))
            for i, va in enumerate(PLURAL_SITES)]
    return out


def _sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    """(label, file offset, retail bytes, applied bytes), the slot record last."""
    sites = [(label, _offset(payload, va), before, after) for label, va, before, after in string_sites()]
    va = modern.record_va(SLOT_UNIT, SLOT_INDEX, modern.layout_stride(payload), table_va=modern.layout_table(payload))
    off = _offset(payload, va)
    _require(struct.unpack_from("<II", payload, off + modern.SLOT_TEXT_BYTES) == SLOT_POOL,
             "offense slot 1 does not draw from the HB rank chain")
    sites.append(("depth_slot_offense_1", off, slot_record_text(True), slot_record_text(False)))
    return sites


def site_states(payload: bytes) -> dict[str, str]:
    try:
        return {label: ("retail" if payload[off:off + len(before)] == before
                        else "applied" if payload[off:off + len(after)] == after else "foreign")
                for label, off, before, after in _sites(payload)}
    except (RbRenameError, ValueError, struct.error, IndexError):
        return {"layout": "foreign"}


def status(payload: bytes) -> str:
    """'retail', 'applied', or 'foreign' (mixed or unknown bytes; refuse to touch)."""
    states = set(site_states(payload).values())
    return "retail" if states == {"retail"} else "applied" if states == {"applied"} else "foreign"


def decode(payload: bytes) -> list[dict[str, object]]:
    """Every site as the game would read it (for receipts and proofs)."""
    rows = []
    for label, off, before, _after in _sites(payload):
        raw = payload[off:off + len(before)]
        if label.startswith("depth_slot"):
            text = " / ".join(raw[a:b].decode("utf-16le").split("\0")[0]
                              for a, b in ((0, 2 * modern.SLOT_ABBREV_WCHARS), (2 * modern.SLOT_ABBREV_WCHARS, modern.SLOT_TEXT_BYTES)))
        else:
            text = raw.decode("utf-16le").split("\0")[0]
        rows.append({"label": label, "file_offset": f"0x{off:x}", "slot_bytes": len(before), "text": text})
    return rows


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; idempotent; refuses anything but retail/applied."""
    state = status(payload)
    _require(state in ("retail", "applied"), f"RB-rename sites are {state}, not retail")
    if state == "applied":
        return payload, {"edits": [], "changed_bytes": 0, "sections_repinned": [], "already_applied": True,
                         "owner": OWNER, "abbreviation": ABBREVIATION}
    buf = bytearray(payload)
    sections = _sections(payload)
    touched: set[int] = set()
    edits = []
    for label, off, before, after in _sites(payload):
        _require(len(before) == len(after), f"{label}: replacement length differs")
        buf[off:off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "file_offset": f"0x{off:x}",
                      "before": before.decode("utf-16le").replace("\0", "|").rstrip("|"),
                      "after": after.decode("utf-16le").replace("\0", "|").rstrip("|")})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d:d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(len(patched) == len(payload) and status(patched) == "applied", "post-apply verification failed")
    return patched, {"edits": edits, "changed_bytes": sum(1 for a, b in zip(payload, patched) if a != b),
                     "sections_repinned": sorted(touched), "owner": OWNER, "abbreviation": ABBREVIATION,
                     "long_singular": LONG_SINGULAR, "long_plural": LONG_PLURAL, "slot_long": SLOT_LONG}


# ---------------------------------------------------------------------------------------------
# Disc side: two MRKS screen scenes in the index archive keep their own position labels
# ---------------------------------------------------------------------------------------------
# (label, outer index entry, entry name id, chunk, chunk bytes, offset in the chunk, retail context, applied context)
# Franchise "Roster Breakdown" (Team Needs, scene name team_needs) and the practice "TRAINING RESULTS"
# screen. Same entry/chunk/offset on the retail disc and the 2026-10-20 SOFTDRINK disc. The context
# around "HB" is part of the pattern; position_pools edits other labels of Team Needs (EDGE:/LB:).
_u = lambda text: text.encode("utf-16le")
SCENE_SITES: tuple[tuple[str, int, int, int, int, int, bytes, bytes], ...] = (
    ("team_needs_label", 9, 3649596148, 7, 21024, 0x1752,
     _u("TE:\0FB:\0HB:\0SS:\0"), _u("TE:\0FB:\0RB:\0SS:\0")),
    ("training_results_label", 23, 3315418792, 48, 27424, 0xB62,
     _u("TE\0WR\0FB\0HB\0QB\0IMPROVEMENT\0"), _u("TE\0WR\0FB\0RB\0QB\0IMPROVEMENT\0")),
)


def scene_state(label: str, segment: bytes) -> str:
    """'retail' | 'applied' | 'foreign' for one scene chunk (MRKS wrapper included)."""
    _label, _entry, _name, _chunk, size, at, before, after = next(s for s in SCENE_SITES if s[0] == label)
    if len(segment) != size or segment[:4] != b"MRKS" or struct.unpack_from("<2I", segment, 4) != (size - 32, size - 32):
        return "foreign"
    got = segment[at:at + len(before)]
    return "retail" if got == before else "applied" if got == after else "foreign"


def apply_scene(label: str, segment: bytes) -> tuple[bytes, dict]:
    state = scene_state(label, segment)
    _require(state in ("retail", "applied"), f"{label}: scene bytes are {state}")
    site = next(s for s in SCENE_SITES if s[0] == label)
    at, after = site[5], site[7]
    out = segment[:at] + after + segment[at + len(after):]
    _require(scene_state(label, out) == "applied" and len(out) == len(segment), f"{label}: postcondition failed")
    return out, {"label": label, "already_applied": state == "applied", "chunk_offset": hex(at),
                 "changed_bytes": sum(1 for a, b in zip(segment, out) if a != b)}


def _scene_segments(image, index):
    from nfl_txtr import parse_chunks
    for label, entry_index, name_id, chunk_index, _size, _at, _before, _after in SCENE_SITES:
        entry = index.entries[entry_index]
        _require(entry.name_id == name_id, f"{label}: outer resource identity drift")
        raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
        chunk = parse_chunks(raw)[chunk_index]
        yield label, entry, chunk, raw[chunk.offset:chunk.end_offset]


def image_status(path) -> str:
    """Disc-side status of an image: 'retail', 'applied', or 'foreign'/'partial'."""
    from pathlib import Path
    from . import nfl2k5_bump_texture_writer as bump
    try:
        with bump._Image.open(Path(path), writable=False) as image:
            index = bump._parsed_index(image)
            states = {scene_state(label, seg) for label, _e, _c, seg in _scene_segments(image, index)}
    except Exception:  # noqa: BLE001 - any unreadable layout is foreign
        return "foreign"
    return states.pop() if len(states) == 1 else "foreign" if "foreign" in states else "partial"


def apply_image(path) -> dict:
    """Rewrite both scene labels in the image COPY in place (same length, no relocation)."""
    from pathlib import Path
    from . import nfl2k5_bump_texture_writer as bump
    rows = []
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        for label, entry, chunk, segment in list(_scene_segments(image, index)):
            fixed, receipt = apply_scene(label, segment)
            if not receipt["already_applied"]:
                image.write_segments(index.sub_extents(entry, chunk.offset, len(fixed)), fixed)
                _require(image.read_segments(index.sub_extents(entry, chunk.offset, len(fixed))) == fixed,
                         f"{label}: read-back differs")
            rows.append(dict(receipt, resource_offset=chunk.offset))
    return {"owner": OWNER, "scenes": rows, "changed_bytes": sum(r["changed_bytes"] for r in rows),
            "runtime_witnessed": False}


__all__ = [
    "ABBREVIATION", "BUILD_CAPTION", "HELP_TEXT", "LONG_PLURAL", "LONG_SINGULAR", "OWNER", "PLURAL_SITES",
    "RbRenameError", "SCENE_SITES", "SINGULAR_SITES", "SLOT_AFTER", "SLOT_LONG", "SLOT_RETAIL", "STRING_SITES",
    "apply", "apply_image", "apply_scene", "decode", "image_status", "scene_state", "site_states",
    "slot_record_text", "status", "string_sites",
]
