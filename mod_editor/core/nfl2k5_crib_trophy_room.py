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
* The Crib's 16 calls of the item-ownership test (OWNED_CALLS) answer "not owned", and a gate on SetCribState
  (CUT_STATES) turns every item screen into the plain room: arcade games, bobbleheads, catalogs, Crib Items,
  celebrity phone, movies and the LED ticker can no longer open, whatever a profile bought. Decor placed earlier stays
  as static props (see CUT_STATES). The save is untouched (switching this off shows the items again), and the game's
  own unlockables check outside the Crib keeps every team, stadium, movie, cheat and celebration bought earlier.
Kept: the room, the trophy cabinets and TROPHY VIEWER, User Card, Milestone Info, Exit. Crib Credits still accrue
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
# The Crib's own calls of the profile's item-ownership test 0x13FBA0 (stdcall, one stack argument; per-profile 64-bit
# variant masks at 0xBC7150 + item * 8). Each becomes "add esp, 4 / xor eax, eax": inside the Crib nothing bought is
# owned, so bought furniture, games, jukebox, theater, bobbleheads and phone are neither drawn nor offered as hotspots.
# The game's other caller (0x10E912, the unlockables check for teams, stadiums, movies, cheats, celebrations and
# soundtracks bought earlier) is NOT touched, so nothing unlocked outside the Crib is lost.
OWNED_CALLS = (0x0026FED1, 0x0026FF31, 0x0026FF89, 0x00270424, 0x00270456, 0x002706D0, 0x00271E90, 0x00272171,
               0x002721D0, 0x00272270, 0x00272381, 0x002723E2, 0x00272489, 0x0027352B, 0x00274AE1, 0x00277C3D)
IS_OWNED = 0x0013FBA0
NOT_OWNED = bytes.fromhex("83c40431c0")   # add esp, 4 ; xor eax, eax
# Every Crib screen change goes through SetCribState 0x276810 (state on the stack). A gate in front of it turns every
# item screen into the plain room (state 3): 5 arcade games, 8/9 bobblehead case and viewer, 12..16 catalog popup,
# catalogs, catalog items and Crib Items, 18..20 celebrity phone / challenge / recap, 21/22 movies, 23 LED ticker.
# Kept: 1/2 loading and first visit, 3 room, 4 zoom, 6/7 trophy cabinets and TROPHY VIEWER, 10/11 User Card and its
# milestone pages, 17 MILESTONE INFO, 24/25 exit. Placed decor stays as static room props (the room is built from the
# profile's placement table, which also holds the default furniture, walls and floors; nothing in the save changes).
CUT_STATES = (5, 8, 9, 12, 13, 14, 15, 16, 18, 19, 20, 21, 22, 23)
STATE_MASK = sum(1 << n for n in CUT_STATES)
SET_STATE = ("crib_state_gate", 0x00276810, bytes.fromhex("558bec83e4f0"), None)   # push ebp; mov ebp, esp; and esp, -16
SET_STATE_RESUME = 0x00276816
# The gate lives in the catalog popup's draw routine (state 12, 0x274400..0x274502, 258 bytes), called only from the
# draw table entry for state 12 (0x275DE2). The gate makes state 12 impossible, so that routine is dead code.
GATE_VA, GATE_ROOM = 0x00274400, 0x102
RETAIL_GATE_ROOM = bytes.fromhex(
    "558bec83e4f081ec9002000068cce3e8006a01e818fdffff8d4c2410e8ff24ddffb902000000e825b4e7ff8bd08d4c24"
    "10e87a25ddffbac0c0c0ff8d4c2410e80c27ddffba030000008d4c2410e8ae25ddff8b0d5474ac00e8a328f2ff85c068"
    "0000a041680000b8428d4c2418680000a0430f848a000000e8f325ddff8b0d5474ac00e818e2f1ff8944240c8d44240c"
    "50baf8e3e8008d8c2494000000e85e5fddff8d9424900000008d4c2410e8bed7e7ff680000a041680000f042680000a0"
    "438d4c241ce8a625ddffba40e4e8008d4c2410e898d7e7ff680000a041680000bc43680000a0438d4c241ce88025ddff"
    "baa0e4e8008d4c2410e872d7e7ff8be55dc3")


def gate_code():
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(GATE_VA)
    a.b("50")                                        # push eax (SetCribState's eax input)
    a.b("8b442408")                                  # mov eax, [esp+8]  (the requested state)
    a.b("83f81f")                                    # cmp eax, 31
    a.j8("77", "keep")                               # ja keep
    a.b("51")                                        # push ecx
    a.b("b9" + struct.pack("<I", STATE_MASK).hex())  # mov ecx, mask
    a.b("0fa3c1")                                    # bt ecx, eax
    a.b("59")                                        # pop ecx (flags kept)
    a.j8("73", "keep")                               # jnc keep
    a.b("c744240803000000")                          # mov dword [esp+8], 3  (the room)
    a.label("keep")
    a.b("58")                                        # pop eax
    a.b("558bec83e4f0")                              # the replaced prologue
    a.jmp_abs(SET_STATE_RESUME)
    body = a.assemble()
    require(len(body) <= GATE_ROOM, "Crib state gate exceeds its dead routine")
    return body


def gate_sites(payload=None):
    """The hook at SetCribState and the gate body over the dead state-12 draw routine (its retail bytes pinned)."""
    hook = (b"\xe9" + struct.pack("<i", GATE_VA - SET_STATE[1] - 5)).ljust(len(SET_STATE[2]), b"\x90")
    body = gate_code()
    return [(SET_STATE[0], SET_STATE[1], SET_STATE[2], hook),
            ("crib_state_gate_code", GATE_VA, RETAIL_GATE_ROOM[:len(body)], body)]


INTRO = ("crib_first_visit_skips_catalog_popup", 0x002771FF, bytes.fromhex("6a0c"), bytes.fromhex("6a03"))
GUARDS = (
    (0x002770E0, 0xF0, "1c329d177f236ac354cdcd35376cf5b81ec6b7260cb8a66c89d6f8edf89037eb"),   # state 1 input (entry)
    (0x002771D0, 0x40, "23a092b0d903136ae09434262125f0843e1e990638727ce6da5db19cf5bda4d9"),   # state 2 input (first visit)
    (0x00276810, 0x20, "c765078fa79d8f475d9c0869a37fb43c3183b34ff38d89f3e16e5da92f8fcfbd"),   # SetCribState
    (0x00275DE2, 0x05, "e9697da8dc4e23db1173594afa782a49e2c43df75752c8e45bcb18d664a94868"),   # state 12 draw call
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


def owned_call(va):
    return b"\xe8" + struct.pack("<i", IS_OWNED - va - 5)


def owned_sites():
    return [(f"crib_owns_nothing_{va:x}", va, owned_call(va), NOT_OWNED) for va in OWNED_CALLS]


def sites(retail_rows):
    return [ENTRY, INTRO, *gate_sites(), *owned_sites(), ("crib_options_rows", OPTIONS, bytes(retail_rows), options_after(retail_rows))]


def _recognize(payload):
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    states = set()
    current = image.read(OPTIONS, 6 * ROW)
    retail_rows = current
    if hashlib.sha256(current).hexdigest() != RETAIL_OPTIONS_SHA256:
        retail_rows = None  # not retail: only the exact applied form is accepted below
    edits = []
    for name, va, before, after in (ENTRY, INTRO, *gate_sites(), *owned_sites()):
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


__all__ = ["OWNER", "REQUESTS", "OPTIONS", "ENTRY", "INTRO", "OWNED_CALLS", "CUT_STATES", "owned_sites", "gate_code", "gate_sites", "GUARDS", "options_after", "sites", "status", "apply"]
