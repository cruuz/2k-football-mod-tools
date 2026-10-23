"""Rename "The Crib" to "Trophy Room" everywhere the player still sees it (display text only).

Noah, 2026-10-22: "the crib in my NFL should be renamed to Trophy Room." Job xs1 cut the rest
of the Crib (catalog popup, shop rows, bought items), so after xs1 the player only reaches the
room, User Card, Milestone Info and Exit. This module renames the room references that remain
reachable. It is pure text: no pointer, no menu descriptor, no route, no allocation changes.

What changes
------------
In-place UTF-16 rewrites inside each retail ``.string_`` slot (NUL-terminated, 4-byte aligned, so
a string may shrink or keep its length but never grow). Every replacement is as long as or shorter
than retail:

* ``0xE8B168`` "The Crib|TM|" (28 B) - the main-menu row (row table ``0x515528``).
* ``0xE9A7FC`` "The Crib|TM|" (28 B) - the Coach's Desk row (``0x52208C``).
* ``0xE9C7F0`` "The Crib|TM|" (28 B) - the third entry row (``0x52A77C``).
* ``0xEBCBF0`` "The Crib|TM|" (28 B) - the navigation name table (``0x58D900``).
* ``0xE8EEB4`` "Exit your Crib?" (32 B) - the Exit confirmation dialog (``0x270B20``).
* ``0xE8DDD0`` "CRIB" (10 B) - the room's Crib credits HUD prefix (drawn twice, ``0x272DC0`` and
  ``0x272F71``). It becomes "ROOM"; the longer "Trophy Room" would overwrite the adjacent
  "CREDITS"/"UNLOCKED" literals, so this short label is the safe in-place choice.

All five room-name literals become "Trophy Room" and the exit dialog becomes "Exit the Room?" (its
32-byte slot cannot hold "Exit the Trophy Room?" (40 bytes); "Exit the Room?" is a deliberate
compromise, see below).

One 5-byte code immediate then makes the room header exact: the header formatter at ``0x26E207``
loads the format string ``0xE8DD98`` ("%s's Crib"); it is repointed to the now-renamed
``0xE8B168`` literal. The formatter ignores the extra name argument for a string with no ``%s``,
so the room title is exactly "Trophy Room" (and the old "%s's Crib" slot is left alone because the
bytes after it hold the ``%s`` and ``|M_PRIMARY|%s`` literals used by six other call sites).

Everything else is left alone, deliberately (documented in :func:`crib_references`):

* Internal names and code: ``z_crib_logo``, ``cribdata``, ``crib.iff``, ``crib_*.iff``, the 23
  ``crib_*.mov`` movie names, ``cribmusic``/``crib22``/``crib_darts``, font/label keys "Crib Tally",
  "Crib Only", "Crib/Menus", "CribMax", "Crib Item List", "Modern Crib", "Crib Music".
* Cut by xs1 (unreachable): the catalog popup ("New Catalog Available", "Welcome (back) to The
  Crib|TM|", "You can unlock one of the following catalogs", "Select one to begin purchasing items
  for your Crib"), the celebrity phone ("Head to your Crib"), the playlist prompt, the 100% Crib
  Milestones congrats, and the "Crib Credits" purchase text.
* Brand/feature terms (not the room): "Crib Credits", "Crib Cheats", "Crib Milestones". These name
  a currency/settings/milestone system, not the room; Noah said rename the room, not these systems.
* The unused "%s's Crib" literal at ``0xE8DD98`` (no longer referenced after the header pointer
  moves) is left byte-identical: the bytes after it are the shared ``%s`` and ``|M_PRIMARY|%s``
  literals, so it cannot simply grow in place.

Pattern-checked (retail or already-applied bytes only; anything else is refused), the touched
``.string_`` section digest is recomputed, and the file never grows. Unverified at runtime.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

OWNER = "nfl2k5_trophy_room"
BUILD_CAPTION = "The Crib is now the Trophy Room"
HELP_TEXT = ("The Crib and the Crib entry points now read Trophy Room (the room kept by the Crib "
             "trim), including the room title and the credits HUD prefix. Display text only: "
             "internal Crib names, Crib Credits/Cheats/Milestones and the cut shop text are "
             "unchanged. One header pointer immediate moves to the renamed literal; no allocation "
             "and no file growth. Enabled in all SOFTDRINK presets.")

IMAGE_BASE = 0x10000

# (label, retail VA, slot bytes, retail text, new text)
STRING_SITES: tuple[tuple[str, int, int, str, str], ...] = (
    ("main_menu_row", 0x00E8B168, 28, "The Crib|TM|", "Trophy Room"),
    ("coach_desk_row", 0x00E9A7FC, 28, "The Crib|TM|", "Trophy Room"),
    ("third_menu_row", 0x00E9C7F0, 28, "The Crib|TM|", "Trophy Room"),
    ("nav_name_table", 0x00EBCBF0, 28, "The Crib|TM|", "Trophy Room"),
    ("exit_dialog", 0x00E8EEB4, 32, "Exit your Crib?", "Exit the Room?"),
    ("hud_label", 0x00E8DDD0, 10, "CRIB", "ROOM"),
)

# (label, VA, retail bytes, applied bytes). The room header formatter loads its format string at
# 0x26E207; the renamed main-menu literal at 0xE8B168 is "Trophy Room", so the header is exact
# without a new read-only host. The extra profile-name argument is ignored by a format with no %s.
CODE_SITES: tuple[tuple[str, int, bytes, bytes], ...] = (
    ("room_header_pointer", 0x0026E207,
     bytes.fromhex("ba98dde800"), bytes.fromhex("ba68b1e800")),
)

# Documentation table for the report / Noah: every "Crib"/"crib" string in .string_ that this patch
# does NOT change, classified by why. (label, retail VA, retail text, reason).
UNCHANGED_REFERENCES: tuple[tuple[str, int, str, str], ...] = (
    ("old_room_header", 0x00E8DD98, "%s's Crib", "unreferenced after the header pointer moves; cannot grow in place"),
    ("catalog_popup_title", 0x00E8E3CC, "New Catalog Available", "cut by xs1 (catalog popup)"),
    ("catalog_welcome_back", 0x00E8E3F8, "Welcome back to The Crib|TM|, %s.", "cut by xs1"),
    ("catalog_welcome_to", 0x00E8E4E8, "Welcome to The Crib|TM|, %s.", "cut by xs1"),
    ("catalog_intro_long", 0x00E8DEA4, "Welcome to ESPN NFL 2K5's The Crib, %s. ...", "cut by xs1"),
    ("catalog_purchase", 0x00E8E6F4, "Select one to begin purchasing items for your Crib.", "cut by xs1"),
    ("milestone_options_help", 0x00E71238, "One or more of the options ... prevent some Crib Milestones ...", "brand term; milestone help"),
    ("milestone_in_your_crib", 0x00E712D6, '... "Milestone Info" in your crib ...', "brand term; milestone help"),
    ("phone_call", 0x00E6A8A4, "Hey %s, you've got a phone call. Head to your Crib ...", "cut by xs1 (celebrity phone)"),
    ("crib_credits", 0x00E70D7E, "%s%s has earned %u Crib Credits", "brand term (currency)"),
    ("crib_cheats", 0x00E716A4, "Crib Cheats", "brand term (settings)"),
    ("playlist_prompt", 0x00EA6948, "You've just created your first Playlist for the Crib. ...", "cut by xs1 (music)"),
    ("return_to_crib", 0x00EA7C1A, "Press|CROSS|to return to the Crib", "cut by xs1"),
)


class TrophyRoomError(ValueError):
    """The Trophy Room rename cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TrophyRoomError(message)


def _utf16(text: str, slot: int) -> bytes:
    raw = text.encode("utf-16le") + b"\0\0"
    _require(len(raw) <= slot, f"{text!r} does not fit a {slot}-byte slot")
    return raw + b"\0" * (slot - len(raw))


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + struct.unpack_from("<I", payload, 0x108)[0]:
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise TrophyRoomError(f"VA 0x{va:x} is in no section")


def string_sites() -> list[tuple[str, int, bytes, bytes]]:
    """(label, VA, retail bytes, applied bytes) for every .string_ literal, padding included."""
    return [(label, va, _utf16(old, slot), _utf16(new, slot))
            for label, va, slot, old, new in STRING_SITES]


def _sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    return [(label, _offset(payload, va), before, after)
            for label, va, before, after in string_sites()]


def code_sites() -> list[tuple[str, int, bytes, bytes]]:
    """(label, VA, retail bytes, applied bytes) for every code immediate this owner changes."""
    return list(CODE_SITES)


def _code_sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    return [(label, _offset(payload, va), before, after) for label, va, before, after in CODE_SITES]


def site_states(payload: bytes) -> dict[str, str]:
    try:
        sites = _sites(payload) + _code_sites(payload)
        return {label: ("retail" if payload[off:off + len(before)] == before
                        else "applied" if payload[off:off + len(after)] == after else "foreign")
                for label, off, before, after in sites}
    except (TrophyRoomError, ValueError, struct.error, IndexError):
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
        rows.append({"label": label, "file_offset": f"0x{off:x}", "slot_bytes": len(before),
                     "text": raw.decode("utf-16le").split("\0")[0]})
    for label, off, _before, after in _code_sites(payload):
        pointer = struct.unpack_from("<I", payload, off + 1)[0]
        rows.append({"label": label, "file_offset": f"0x{off:x}", "pointer": f"0x{pointer:x}",
                     "text": _read_text(payload, pointer)})
    return rows


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; idempotent; refuses anything but retail/applied."""
    state = status(payload)
    _require(state in ("retail", "applied"), f"Trophy Room sites are {state}, not retail")
    if state == "applied":
        return payload, {"edits": [], "changed_bytes": 0, "sections_repinned": [], "already_applied": True,
                         "owner": OWNER, "new_name": "Trophy Room"}
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
    for label, off, before, after in _code_sites(payload):
        _require(len(before) == len(after), f"{label}: replacement length differs")
        buf[off:off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "file_offset": f"0x{off:x}",
                      "before": before.hex(), "after": after.hex()})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d:d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(len(patched) == len(payload) and status(patched) == "applied", "post-apply verification failed")
    return patched, {"edits": edits, "changed_bytes": sum(1 for a, b in zip(payload, patched) if a != b),
                     "sections_repinned": sorted(touched), "owner": OWNER, "new_name": "Trophy Room"}


def _read_text(payload: bytes, va: int) -> str:
    try:
        off = _offset(payload, va)
    except (TrophyRoomError, ValueError, struct.error):
        return "<unmapped>"
    end = off
    while end + 1 < len(payload) and payload[end:end + 2] != b"\0\0":
        end += 2
    return payload[off:end].decode("utf-16le", errors="replace")


def crib_references(payload: bytes) -> dict[str, list[dict[str, object]]]:
    """Classify every visible ".string_" room reference, for the report and Noah's sign-off.

    Returns ``{"renamed": [...], "unchanged": [...]}``. ``renamed`` rows come from the live site
    table (post-apply text) and include the header pointer's target; ``unchanged`` rows are the
    documented brand/cut strings.
    """
    renamed = [{"label": label, "va": f"0x{va:x}", "text": _read_text(payload, va)}
               for label, va, _slot, _old, _new in STRING_SITES]
    for label, _va, _before, _after in CODE_SITES:
        pointer = struct.unpack_from("<I", payload, _offset(payload, _va) + 1)[0]
        renamed.append({"label": label, "va": f"0x{_va:x}", "text": _read_text(payload, pointer)})
    unchanged = [{"label": label, "va": f"0x{va:x}", "text": _read_text(payload, va), "reason": reason}
                 for label, va, _text, reason in UNCHANGED_REFERENCES]
    return {"renamed": renamed, "unchanged": unchanged}


__all__ = [
    "BUILD_CAPTION", "CODE_SITES", "HELP_TEXT", "OWNER", "STRING_SITES", "TrophyRoomError",
    "UNCHANGED_REFERENCES", "apply", "code_sites", "crib_references", "decode", "site_states",
    "status", "string_sites",
]
