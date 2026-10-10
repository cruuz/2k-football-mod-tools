"""Type spaces, periods, apostrophes and hyphens in player names with the game's own keyboard.

Create Player, Edit Player (roster mode) and Franchise Edit Player all open the same two handlers:
First Name ``0x346430`` and Last Name ``0x346540``.  Each calls the generic on-screen keyboard
``0x24A220`` with a UTF-16 string of allowed characters.  The keyboard itself is a full QWERTY layout
(56 key slots of 0x28 bytes at ``0xAC4E58``: Esc, digits and shifted symbols, Del, Clear, Caps, Shift,
Enter, ``- = [ ] ; ' , . /`` and the Space bar), and its only filter is that string: ``0x248D20`` looks the
typed character up in it and ``0x248D50`` drops it silently when it is absent (a null string allows every
key, which is what the coach, city and ticker prompts pass).  Retail passes

* ``0xEACAB0``: ``A-Z a-z`` for First Name (52 characters), and
* ``0xEACB20``: ``A-Z a-z - '`` for Last Name (54 characters),

so Space and Period were never typeable, and the First Name field could not take a hyphen or an apostrophe
even though the shipped rosters carry both (``Amon-Ra``, ``Ja'Marr``).  The two literals are referenced
nowhere else (not as code immediates, not through any pointer table).

The patch writes one 56-character literal, ``A-Z a-z - ' space .``, at ``0xEACAB0`` and points the Last Name
keyboard call at it.  The 224-byte window ``0xEACAB0..0xEACB90`` is both retail literals and their padding;
the new string needs 114 bytes, more than either 112-byte slot, so the Last Name immediate moves and the
rest of the window is zeroed.  The Last Name handler also pushes ``0xEACB20`` at ``0x346567`` as the last
stack argument of its "not enough room to edit names" message box.  That argument is never read as a
pointer: ``0x14E070`` hands it to ``0x14DC40``, which only tests it against zero (the First Name handler
passes 0, the Last Name handler passes the old literal's address, so the two boxes differ by one draw call).
It is left exactly as retail, still non-zero.  Edits:

=====================  ==================================  ============================================
site                   retail                              applied
=====================  ==================================  ============================================
``0xEACAB0..0xEACB90`` two letter literals + padding       one 56-character literal, then zero padding
``0x3465BA`` (4 B)     ``0xEACB20``                        ``0xEACAB0``
=====================  ==================================  ============================================

The ``.text`` and ``.string_`` SHA-1 digests are recomputed.  No code is added, no cave and no allocation.

What this does not change, all native paths proved by ``tests/mod_editor/name_keyboard_probe.py``:

* the 12-character cap per name (``push 0xC``; the buffers hold 15 characters plus the terminator),
* the commentary lookup at ``0x346540``: it compares the typed last name with every real player's last name
  (``0x30B90``, ASCII case folded, exact otherwise), takes that player's recorded name cue when it is below
  9000 and the player is neither created nor flagged, and otherwise falls back to 9000 + jersey.  Nothing in
  it treats a space, period, apostrophe or hyphen specially, so "St. Brown" matches "St. Brown" and not
  "St Brown",
* every other keyboard prompt (17 call sites in all, 15 of them not player names).

Menus, the player card and broadcast text draw through ``0x46420``: character 0x20 advances by the font's
space width without a glyph, and all ten FONT resources carry glyphs for U+0021..U+007E.  The jersey
nameplate compositor (``0x1C2140``) draws only ``A-Z a-z ' -`` (case folded); a space is a blank gap as
wide as the hyphen and any other character, including a period, is skipped with no advance.  Nothing
breaks; the period simply does not print on the back of a jersey.

EXPERIMENTAL / UNWITNESSED in a played game.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_name_keyboard"
UI_LABEL = "Type spaces, periods, apostrophes, hyphens in player names"
BUILD_CAPTION = UI_LABEL
HELP_TEXT = (
    "Create Player, Edit Player and Franchise Edit Player: the First Name and Last Name keyboards accept "
    "letters plus space, period, apostrophe and hyphen (Amon-Ra St. Brown, Ja'Marr Chase, D.K. Metcalf, "
    "Van Jefferson). The game's keyboard already has those keys; its filter dropped them. Names are still "
    "limited to 12 characters each. Menus, the player card and broadcast text draw all four; a jersey "
    "nameplate draws letters, apostrophes and hyphens only (a space is a gap, a period is skipped). "
    "Changes data only; no code is added. Do not end a name with a space: it will not match the "
    "commentary surname.")

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
PUNCTUATION = "-' ."
RETAIL_FIRST = LETTERS
RETAIL_LAST = LETTERS + "-'"
NAME_CHARSET = LETTERS + PUNCTUATION

CHARSET_VA = 0xEACAB0                 # retail First Name literal; also the new shared literal
LAST_CHARSET_VA = 0xEACB20            # retail Last Name literal
WINDOW_SIZE = 0xE0                    # 0xEACAB0..0xEACB90: both literals and their padding
FIRST_KEYBOARD_IMMEDIATE = 0x3464C1   # push 0xEACAB0 in the First Name handler (unchanged)
LAST_POPUP_IMMEDIATE = 0x346567       # push 0xEACB20: a zero/non-zero flag of the low-room message box (unchanged)
LAST_KEYBOARD_IMMEDIATE = 0x3465BA    # push 0xEACB20 in the Last Name handler
MAX_NAME_CHARACTERS = 12              # push 0xC at 0x3464CE and 0x3465CC (unchanged)


def _literal(text: str, size: int) -> bytes:
    raw = text.encode("utf-16le") + b"\0\0"
    if len(raw) > size:
        raise ValueError(f"{text!r} needs {len(raw)} bytes, the slot has {size}")
    return raw.ljust(size, b"\0")


RETAIL_WINDOW = _literal(RETAIL_FIRST, 0x70) + _literal(RETAIL_LAST, 0x70)
PATCHED_WINDOW = _literal(NAME_CHARSET, WINDOW_SIZE)
_RETAIL_POINTER = struct.pack("<I", LAST_CHARSET_VA)
_PATCHED_POINTER = struct.pack("<I", CHARSET_VA)

# (label, VA, retail bytes, applied bytes); the shared ``.rdata`` site helper reports retail | applied | foreign.
SITES = (
    ("name_charset_literal", CHARSET_VA, RETAIL_WINDOW, PATCHED_WINDOW),
    ("last_name_keyboard_charset", LAST_KEYBOARD_IMMEDIATE, _RETAIL_POINTER, _PATCHED_POINTER),
)

# Unchanged code and tables the patch relies on: the keyboard driver, its key table and key labels, the filter
# and append routines, and both name handlers (the Last Name handler around its two edited operands).
GUARDS = (
    (0x248D20, 0x2E, "3e5f4053adbdd5091be1a41b27ebe73176c12ca76294b2da91caca6a40b81c91"),
    (0x248D50, 0x41, "d56c2b6e580b9e742610006e9a44276ad1d3966319de1fee926e4aec690b3b2c"),
    (0x248DA0, 0xAC, "bfdd95566ccbe66af23be50a9c4553ec106b9ccf8f869c20e695c25edd034930"),
    (0x248E50, 0x178, "c93bbd20646ed9bdac8b769604ae86bd55a6b2a9513cd76234540f30c66fc87e"),
    (0x24A220, 0x14C, "025104a29ba30050f18c59b554af8dd8541f7b5387522a89ace2f355ca4d9cd1"),
    (0x346430, 0xED, "7d3920c93b826742c83ce4ee7fed73d071a5c25145f7ab3f1d7c03caba3cdb75"),
    (0x346540, 0x7A, "47ea34936587362be1f7ac44134ce07618971eb12402b99fd4f26cd12224b8d5"),
    (0x3465BE, 0x165, "b782c1a6f264673e409a6ebc5d0389a0bdbcde52453191c18d767fd68b288241"),
    (0xAC4E58, 0x8C0, "b1c7b205495c42478353e726d5930218846f7b02781150ac56e735d8d3ff7410"),
    (0xE8991C, 0x20C, "d8b052c8273f00c28119e2299f103fac5f101c9cf737edcd1363c81b186330ba"),
)


def status(payload: bytes) -> str:
    """``retail`` | ``applied`` | ``foreign`` over the three edited sites and the pinned keyboard code."""
    try:
        for va, size, digest in GUARDS:
            off = rdata.offset_of(payload, va)
            if hashlib.sha256(payload[off:off + size]).hexdigest() != digest:
                return "foreign"
        return rdata.status(payload, SITES)
    except (ValueError, TypeError, struct.error):
        return "foreign"


def _utf16z(payload: bytes, va: int, limit: int = 128) -> str:
    off = rdata.offset_of(payload, va)
    out = []
    for i in range(limit):
        unit = struct.unpack_from("<H", payload, off + 2 * i)[0]
        if unit == 0:
            return "".join(out)
        out.append(chr(unit))
    raise rdata.RdataSiteError("unterminated name character list")


def allowed_characters(payload: bytes) -> dict[str, str]:
    """The characters the two name keyboards accept, read back from the executable's own operands."""
    result = {}
    for key, immediate in (("first_name", FIRST_KEYBOARD_IMMEDIATE), ("last_name", LAST_KEYBOARD_IMMEDIATE)):
        pointer = struct.unpack_from("<I", payload, rdata.offset_of(payload, immediate))[0]
        result[key] = _utf16z(payload, pointer)
    return result


def verify(payload: bytes) -> dict:
    state = status(payload)
    if state != "applied":
        raise rdata.RdataSiteError(f"Name keyboard sites are {state}, not applied")
    allowed = allowed_characters(payload)
    if allowed != {"first_name": NAME_CHARSET, "last_name": NAME_CHARSET}:
        raise rdata.RdataSiteError("Name keyboard character lists differ from the pinned set")
    return dict(status=state, first_name_characters=allowed["first_name"], last_name_characters=allowed["last_name"],
                maximum_characters=MAX_NAME_CHARACTERS, runtime_witnessed=False, file_growth=0)


def apply(payload: bytes):
    state = status(payload)
    if state not in ("retail", "applied"):
        raise rdata.RdataSiteError(f"Name keyboard prerequisites are {state}, not retail")
    result, receipt = rdata.apply(payload, SITES, BUILD_CAPTION)
    return result, {**receipt, **verify(result), "owner": OWNER,
                    "reservations": [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                                          basis="pinned in-place edit: " + label)
                                     for label, va, before, _ in SITES]}
