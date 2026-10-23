"""The Crib keeps only the Trophy Room side: the shop is cut. EXPERIMENTAL (b778 xs1, Noah 10/22).

Noah (10/22 ~17:20): "The only thing I want in the crib is the trophy room that shows your awards. Everything else
can be cut and removed." Job pg2 renames "The Crib" to "Trophy Room"; this owner only removes things.

How the Crib works (static disassembly of the USA executable, xs1 emulator runs cribC2..C4):
* The Crib is one native screen (descriptor 0x524FA0) with a state word at 0xAC7448 (1..25), set only through
  0x276810 (SetCribState, the new state on the stack). Draw and input dispatch on it (tables 0x275EB4, 0x27861C).
  State 1 loads the room; 3 is the free-look room; 6/7 are the trophy cabinets and the TROPHY VIEWER (0x273070);
  12 is the "NEW CATALOG AVAILABLE / unlock one of the following catalogs" shop popup (0x274400 / input 0x278150).
* Entering, state 1 asks 0x275B00 "is a new catalog available?" and goes to 12 (the shop) instead of 3 (the room)
  when one is: 0x277185 ``je 0x277195`` (to ``push 3``) falls through to ``push 0xC``. State 2 (first visit)
  goes to 12 on A at 0x2771FF ``push 0xC``.
* START opens the Crib options list, row table 0x524CA0 (0x34-byte rows, kind 3 ends it): User Card, Catalogs
  (the shop, submenu 0x523A48), Crib Items (the item shop, 0x523F50), Milestone Info, Exit.
* Room furniture, the arcade games, jukebox, home theater, bobbleheads and the celebrity phone are items bought
  with Crib Credits from those catalogs. The trophies are earned, never bought.

What this owner changes (three in-place edits, no allocation):
* 0x277185 ``74 0E`` -> ``EB 0E``: entering always goes to the room (state 3), never to the catalog popup.
* 0x2771FF ``6A 0C`` -> ``6A 03``: the first-visit screen continues to the room, not the catalog popup.
* The options list becomes User Card, Milestone Info, Exit (the two shop rows removed, the table ends after Exit;
  the freed rows are zero). Nothing left on screen leads to a removed screen.
Kept: the room, the trophy cabinets and TROPHY VIEWER, User Card, Milestone Info, Exit. Items a profile already
bought stay where they are (their hotspots still work); a new profile never gets any. Crib Credits still accrue
(harmless). The 23 Crib movies are cut separately by ``nfl2k5_crib_reclaim`` (417 MB of disc).
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_crib_trophy_room"
EVIDENCE = "EXPERIMENTAL"
REQUESTS = ()
BUILD_CAPTION = "The Crib: Trophy Room only (shop cut)"
HELP_TEXT = ("EXPERIMENTAL. The Crib keeps the room, your trophies, User Card and Milestone Info. The catalog popup and the "
             "Catalogs and Crib Items shops are removed. Items a profile already bought stay.")
ROW = 0x34
OPTIONS = 0x00524CA0                 # User Card, Catalogs, Crib Items, Milestone Info, Exit, end
RETAIL_OPTIONS_SHA256 = "84676015b6b79fab7f54ec158c0de81ee2ce73f54d79b2848d2057451f1d05ab"   # 6 rows
ENTRY = ("crib_entry_skips_catalog_popup", 0x00277185, bytes.fromhex("740e"), bytes.fromhex("eb0e"))
INTRO = ("crib_first_visit_skips_catalog_popup", 0x002771FF, bytes.fromhex("6a0c"), bytes.fromhex("6a03"))
GUARDS = (
    (0x002770E0, 0xF0, "1c329d177f236ac354cdcd35376cf5b81ec6b7260cb8a66c89d6f8edf89037eb"),   # state 1 input (entry)
    (0x002771D0, 0x40, "23a092b0d903136ae09434262125f0843e1e990638727ce6da5db19cf5bda4d9"),   # state 2 input (first visit)
    (0x00276810, 0x20, "c765078fa79d8f475d9c0869a37fb43c3183b34ff38d89f3e16e5da92f8fcfbd"),   # SetCribState
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class CribError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise CribError(message)


def options_after(retail_rows):
    """User Card, Milestone Info, Exit, the end row, then zeros (same 6-row span)."""
    rows = [retail_rows[i * ROW:(i + 1) * ROW] for i in range(6)]
    require(struct.unpack_from("<I", rows[5], 0)[0] == 3, "foreign Crib options terminator")
    out = rows[0] + rows[3] + rows[4] + rows[5]
    return out + bytes(6 * ROW - len(out))


def sites(retail_rows):
    return [ENTRY, INTRO, ("crib_options_rows", OPTIONS, bytes(retail_rows), options_after(retail_rows))]


def _recognize(payload):
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    states = set()
    current = image.read(OPTIONS, 6 * ROW)
    retail_rows = current
    if hashlib.sha256(current).hexdigest() != RETAIL_OPTIONS_SHA256:
        retail_rows = None  # not retail: only the exact applied form is accepted below
    edits = []
    for name, va, before, after in (ENTRY, INTRO):
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if raw == after else "foreign")
        edits.append((va, before))
    if retail_rows is not None:
        states.add("retail")
    else:
        states.add("applied" if _applied_rows_ok(current) else "foreign")
    require(states in ({"retail"}, {"applied"}), "foreign or mixed Crib trophy-room state")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for at, before in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"foreign Crib prerequisite at {va:#x}")
    return next(iter(states))


def _applied_rows_ok(current):
    """The applied table: rows User Card, Milestone Info, Exit (retail bytes), the end row, zeros."""
    rows = [current[i * ROW:(i + 1) * ROW] for i in range(6)]
    kinds = [struct.unpack_from("<I", r, 0)[0] for r in rows[:4]]
    labels = [struct.unpack_from("<I", r, 4)[0] for r in rows[:3]]
    return (kinds == [0, 0, 9, 3] and labels == [_USER_CARD, _MILESTONE, _EXIT] and not any(rows[4] + rows[5])
            and hashlib.sha256(b"".join(rows[:4])).hexdigest() == APPLIED_ROWS_SHA256)


# Retail row label pointers (UTF-16 strings in .string_) and the applied rows' digest (from the retail rows).
_USER_CARD, _MILESTONE, _EXIT = 0x00E9AC50, 0x00E9AC90, 0x00E9ACB0
APPLIED_ROWS_SHA256 = "7f13f7d5018988e049de2f95a12f4b0d8f8c44564023806df8934c66a1f6b812"


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def apply(payload):
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    state = status(payload)
    require(state != "foreign", "foreign/mixed Crib input; rebuild from the original")
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    image = XbeImage(payload)
    retail_rows = image.read(OPTIONS, 6 * ROW)
    buf = bytearray(payload)
    edits = sites(retail_rows)
    for _name, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"Crib site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied", "Crib trophy-room postcondition failed")
    return result, dict(common, status="applied", changed_bytes=sum(a != b for a, b in zip(payload, result)),
                        edits=[dict(label=n, va=hex(v), size=len(o)) for n, v, o, _w in edits])


__all__ = ["OWNER", "REQUESTS", "OPTIONS", "ENTRY", "INTRO", "GUARDS", "options_after", "sites", "status", "apply"]
