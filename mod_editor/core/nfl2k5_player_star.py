"""The retail controller star under any player the studio tags (executable patch, xemu-only).

Retail already draws the star, and the asset is literally called ``icon_controller_star``
(``.string_`` 0xE6C16C).  ``FUN_000f8e60`` loads it into ``[0xBA28A4]`` (``controller``) and
``[0xBA28A8]`` (``controller100``); ``FUN_000f8880`` puts an instance of that model at a player's
feet as a **world-space decal** (it adds x/z into the instance transform at +0x30/+0x38) and colours
it from the per-user table ``.rdata`` 0x4ED9A0; ``FUN_000f9030`` walks the on-field entity list
``[0xE60268]`` once a frame and appends the players that get one to a list at **0xBA2824** (0xC bytes
an entry, byte count at **0xBA2821**); ``FUN_000f9320`` draws them.  The **only** gate on the append
is ``FUN_00075d40``, an 80-byte leaf at **0x75D40**.  So the whole feature is: make that predicate
say yes for a tagged player.  Nothing is authored, nothing is drawn by us.

**The tag.**  ``FUN_00075d40`` receives the entity in ``ecx``.  ``entity+0x3C`` is the player's
**0x54 roster record**, proved three ways off retail code: ``FUN_000fa270`` stores ``[entity+0x3C]``
into the on-field marker queue (0xFA2CB, the entity is the last ``push`` at 0x761D9 in
``FUN_00075d90``), and the queue's consumers read that object's ``+0x14`` as the name pointer
(``FUN_000f9d00`` at 0xF9D4C), its ``+0x20`` bits 3..9 as the jersey number (0xF9D25, ``shr 3`` /
``and 0x7f``) and its ``+0x35`` as the position code (``FUN_000e5fc0``) -- exactly the studio's own
roster-record fields (``nfl2k5_text_catalog.JERSEY_FIELD`` 0x20 / ``JERSEY_MASK`` 0x3F8 /
``JERSEY_SHIFT`` 3, ``nfl2k5_team_history`` position ``+0x35``, last name ``+0x14``).  The record's
relative pointers are absolute at run time: ``FUN_000c0500`` relocates the ROST body in place.

So the tag is one bit of the roster record and rides into every franchise created from the patched
disc for free (a roster/franchise save carries the whole ROST body).  The byte used is **+0x53**.
Four candidates were checked first and every one of them is live:

* **+0x27 bit 0** (the original plan's choice) is contract length: 981 of the 2,479 retail primary
  records already set it, and the Flying Finn V4 reverse-engineering names +0x0A / +0x24 / +0x26 /
  +0x27 as a contract block (value, years remaining, type and bonus tier, length).  Bit 0 of +0x26
  (386 records) and of +0x08, the Player Type flags (155 records), is taken the same way.
* **+0x23** is not a byte at all: it is bits 24..31 of the **live dword at +0x20**.  ``FUN_000be290``
  / ``FUN_000e4470`` read an 8-bit field out of bits 22..29 (``mov eax,[x+0x20]; shr eax,0x16; and
  eax,0xff``), ``FUN_000be2a0`` / ``FUN_000e4480`` write it back, ``FUN_000be2c0`` / ``FUN_000be2f0``
  read bits 30 and 31, and the game's own record clone copies exactly those masks (0x300000,
  0x3fc00000, 0x40000000 and bit 31) at 0xC18EA..0xC1926.  Zero on the retail disc, read and written
  by the engine: unusable.
* **+0x24 bit 7** is its own one-bit field -- the clone copies it alone (``and ecx,0x80`` at
  0xC1950) -- and unlike +0x23 it is *set* in retail data (the 2,547 records OR to 0xFF at +0x24).

**+0x53** is the second of the two bytes Bad_AL's NFL2K5Tool documents as "padded by 2 zero bytes"
at the end of the record.  It is zero in all 2,547 retail records (2,479 primary + 68 secondary),
and -- the decisive evidence -- the game's own field-by-field player clone (``0xC16CD..0xC1DDB``,
the create/copy path) names **every** field of the record from +0x00 through +0x51, each at its own
displacement, and never names +0x52 or +0x53.  The only other displacements it skips are ones a
wider access already covers (+0x21..+0x23 inside the +0x20 dword, +0x25 inside +0x24, and so on),
+0x29 (inside the +0x28 word), the +0x2C stream pointer a new record must not inherit, and
+0x30..+0x33.  Nine byte-sized reads of ``[reg+0x53]`` exist in the whole executable and every one
of them pairs with +0x52 in an unrelated structure; none is on the roster path.  No studio pass
writes it either (team history rebuilds the pool and the +0x2C words, the reclassifier writes +0x35,
prospect names rewrite the name pool), and the whole record is copied verbatim from the disc into
the runtime buffer.

**The patch** is an in-place rewrite of ``FUN_00075d40``: 80 retail bytes out, 80 new bytes in, no
cave, no hook, no displaced instruction, the entry address unchanged so both call sites (0x7604A in
``FUN_00075d90``, 0xF90AA in ``FUN_000f9030``) still land on byte 0.  The rewrite keeps the retail
predicate exactly and ORs the tag in::

    if (!([0xE5FC50] | [0xE5FC90])) return 0;          // nobody human is playing
    eax = [0xE5FF80];                                  // game mode, hoisted (a pure read)
    if (*(int *)e[3] != -1) return 1;                  // a user-controlled body
    if (*e == 0)              goto tag;
    if (eax == 0)             return 1;                // practice
    if ([0xE602B8] == 0x0E)   return 1;                // live play
    if (*(char *)(e + 0x2C) != 6) return 1;
  tag:
    r = *(void **)(e + 0x3C);                          // the 0x54 roster record
    if (r && (r[0x53] & 1) && *(byte *)0xBA2821 < 9) return 1;
    return FUN_0017ebd0(e);                            // tail call: the retail user-body test

Retail computes ``FUN_0017ebd0(e) != 0 || rest`` in the other order; the rewrite evaluates ``rest``
first and only calls when ``rest`` is 0, which is the same value because ``FUN_0017ebd0`` is pure
(it reads ``[e+0x38]``, calls ``FUN_000f71e0`` -- two loads and a compare -- and compares three
fields; it writes nothing) and returns exactly 0 or 1, so the tail ``jmp`` is the retail result.

**The clamp is not optional.**  The star list is 0xC bytes an entry at 0xBA2824 with a *byte* count
at 0xBA2821, and ``FUN_000f9030`` flushes the block ``[0xBA2820, 0xBA2820 + 4 + count*0xC)`` at
0xF92E3.  With count = 9 that ends exactly at 0xBA2890, the next global (a dword the same routine
writes at 0xF92D6 and reads at 0xF947C).  A tenth entry overruns it, so the tag path refuses once
the count has reached 9.  Retail's own answers are never clamped, only ours.

``mov al,1`` is the return-1 tail: ``eax`` holds the game-mode word there, and that word is a 0..8
enum (the game compares it to 0, 3, 4 and 8 and clamps it to <= 4 at 0x632B0), so its upper 24 bits
are zero and the function returns exactly 1, as retail does.  Both call sites only ``test eax,eax``.

Side effect, by design: ``FUN_00075d40`` is also the gate on the **on-field indicator** in
``FUN_00075d90`` (0x7604A), so a tagged player gets the name / number-and-position text as well as
the star, subject to the user's own "Player Indicator Text" option (``[0xE5FF90]``).

Without tags the patched predicate is byte-for-byte retail behaviour, so it draws nothing; the tags
themselves are written by ``nfl2k5_player_tags``.  Unwitnessed in game.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm

IMAGE_BASE = 0x10000

# --- the predicate that is rewritten in place ----------------------------------------------------
GATE_VA = 0x00075D40
GATE_SIZE = 0x50                       # 0x75D40..0x75D8F; the next routine starts at 0x75D90
RETAIL_GATE = bytes.fromhex(
    "a150fce50085c0568bf17509a190fce50085c074378b460c8338ff75288bcee86c8e100085c0751d833e00741f"
    "a180ffe500 85c0740f833db802e6000e7406807e2c067407b8010000005ec333c05ec3".replace(" ", ""))
assert len(RETAIL_GATE) == GATE_SIZE

# the two call sites: both land on byte 0 of the routine, so neither moves
CALL_SITES = ((0x0007604A, bytes.fromhex("e8f1fcffff")),      # FUN_00075d90: the on-field indicator
              (0x000F90AA, bytes.fromhex("e891ccf7ff85c0")))  # FUN_000f9030: the star list

# --- retail globals and routines the rewrite keeps using -----------------------------------------
HUMAN_A_VA = 0x00E5FC50                # user 1 / user 2 objects: both null = nobody is playing
HUMAN_B_VA = 0x00E5FC90
GAME_MODE_VA = 0x00E5FF80              # 0/1/2 practice, 3 basic training, 4 exhibition, 5/6/7 franchise, 8 other
PLAY_STATE_VA = 0x00E602B8             # 0xE = live play
LIVE_PLAY = 0x0E
IS_USER_BODY_VA = 0x0017EBD0           # FUN_0017ebd0(ecx = entity) -> 0/1, pure
RETAIL_IS_USER_BODY_HEAD = bytes.fromhex("568bf18b4e38e8")
ENTITY_CONTROLLER_OFFSET = 0x0C        # entity+0xC: first dword is -1 on a CPU body
ENTITY_STATE_OFFSET = 0x2C             # entity+0x2C: byte state (6 = the retail "no star" state)
ENTITY_RECORD_OFFSET = 0x3C            # entity+0x3C: the 0x54 roster record (proved, see the docstring)

# --- the tag ------------------------------------------------------------------------------------
TAG_RECORD_OFFSET = 0x53               # the second of the record's two trailing pad bytes
TAG_BIT = 0x01
PLAYER_RECORD_SIZE = 0x54

# --- the star list and its hard bound ------------------------------------------------------------
STAR_COUNT_VA = 0x00BA2821             # byte count, zeroed each frame at 0xF9085
STAR_LIST_VA = 0x00BA2824              # 0xC bytes an entry
STAR_ENTRY_SIZE = 0x0C
STAR_LIST_END_VA = 0x00BA2890          # the next global; (0xBA2890 - 0xBA2824) / 0xC = 9 entries
STAR_LIST_LIMIT = (STAR_LIST_END_VA - STAR_LIST_VA) // STAR_ENTRY_SIZE
assert STAR_LIST_LIMIT == 9
STAR_APPEND_VA = 0x000F912B            # inc cl ; mov [0xBA2821], cl  (the append's count bump)
RETAIL_STAR_APPEND = bytes.fromhex("fec1880d2128ba00")
STAR_FLUSH_VA = 0x000F92E3             # movzx eax,[0xBA2821] ; lea eax,[eax+eax*2] ; lea ecx,[eax*4+4]
RETAIL_STAR_FLUSH = bytes.fromhex("0fb6052128ba008d04408d0c8504000000")

# --- context that must be retail on any image we touch --------------------------------------------
PREV_ROUTINE_VA = 0x00075D30           # the 8-byte routine before the gate plus its 8 alignment nops
RETAIL_PREV_ROUTINE = bytes.fromhex("c7410800000000c39090909090909090")
NEXT_ROUTINE_VA = 0x00075D90
RETAIL_NEXT_ROUTINE_HEAD = bytes.fromhex("558bec83e4f081ec")


class PlayerStarError(ValueError):
    """The player-star patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlayerStarError(message)


def _code() -> tuple[bytes, dict[str, int]]:
    """The rewritten ``FUN_00075d40``: 80 bytes, entry at byte 0, no cave, no writes."""

    imm = lambda va: struct.pack("<I", va).hex()  # noqa: E731
    a = _Asm(GATE_VA)
    a.label("gate")
    a.b("a1" + imm(HUMAN_A_VA))                                 # mov eax, [0xE5FC50]
    a.b("0b05" + imm(HUMAN_B_VA))                               # or  eax, [0xE5FC90]
    a.j8("74", "done")                                          # je  done            nobody human -> 0 (eax = 0)
    a.b("a1" + imm(GAME_MODE_VA))                               # mov eax, [0xE5FF80] game mode, hoisted
    a.b("8b51" + f"{ENTITY_CONTROLLER_OFFSET:02x}")             # mov edx, [ecx+0xc]
    a.b("833aff")                                               # cmp dword [edx], -1
    a.j8("75", "one")                                           # jne one             a user-controlled body
    a.b("8339 00")                                              # cmp dword [ecx], 0
    a.j8("74", "tag")                                           # je  tag
    a.b("85c0")                                                 # test eax, eax       game mode 0 = practice
    a.j8("74", "one")                                           # je  one
    a.b("833d" + imm(PLAY_STATE_VA) + f"{LIVE_PLAY:02x}")       # cmp dword [0xE602B8], 0xE
    a.j8("74", "one")                                           # je  one             live play
    a.b("8079" + f"{ENTITY_STATE_OFFSET:02x}" + "06")           # cmp byte [ecx+0x2c], 6
    a.j8("75", "one")                                           # jne one
    a.label("tag")
    a.b("8b51" + f"{ENTITY_RECORD_OFFSET:02x}")                 # mov edx, [ecx+0x3c] the 0x54 roster record
    a.b("85d2")                                                 # test edx, edx
    a.j8("74", "retail")                                        # je  retail          no record: retail answer
    a.b("f642" + f"{TAG_RECORD_OFFSET:02x}" + f"{TAG_BIT:02x}")  # test byte [edx+0x53], 1
    a.j8("74", "retail")                                        # je  retail          not tagged
    a.b("803d" + imm(STAR_COUNT_VA) + f"{STAR_LIST_LIMIT:02x}")  # cmp byte [0xBA2821], 9
    a.j8("72", "one")                                           # jb  one             tagged and the list has room
    a.label("retail")
    a.jmp_abs(IS_USER_BODY_VA)                                  # jmp FUN_0017ebd0    tail call: 0 or 1
    a.label("one")
    a.b("b001")                                                 # mov al, 1           (eax = the 0..8 game mode)
    a.label("done")
    a.b("c3")                                                   # ret
    a.label("end")
    code = a.assemble()
    return code, {name: GATE_VA + off for name, off in a.labels.items()}


PATCHED_GATE, GATE_LABELS = _code()
assert len(PATCHED_GATE) == GATE_SIZE, f"the rewritten predicate is {len(PATCHED_GATE)} bytes, not {GATE_SIZE}"
assert PATCHED_GATE != RETAIL_GATE


def sites() -> list[tuple[str, int, bytes, bytes]]:
    """``(label, va, retail bytes, patched bytes)`` -- one site, the routine itself."""

    return [("star_gate", GATE_VA, RETAIL_GATE, PATCHED_GATE)]


# context pins: the call sites (unmoved), the tail-called routine, the neighbours of the rewrite and
# the star list's own append / flush, which the 9-entry clamp is derived from
PINS = (*CALL_SITES,
        (IS_USER_BODY_VA, RETAIL_IS_USER_BODY_HEAD),
        (PREV_ROUTINE_VA, RETAIL_PREV_ROUTINE),
        (NEXT_ROUTINE_VA, RETAIL_NEXT_ROUTINE_HEAD),
        (STAR_APPEND_VA, RETAIL_STAR_APPEND),
        (STAR_FLUSH_VA, RETAIL_STAR_FLUSH))


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise PlayerStarError(f"VA 0x{va:x} is in no section")


def _pins_are_retail(payload: bytes) -> bool:
    for va, expected in PINS:
        off = _offset(payload, va)
        if payload[off: off + len(expected)] != expected:
            return False
    return True


def status(payload: bytes) -> str:
    """'retail', 'applied' or 'foreign' (bytes match neither; refuse to touch)."""

    try:
        if not _pins_are_retail(payload):
            return "foreign"
        gate = payload[_offset(payload, GATE_VA):][:GATE_SIZE]
    except (PlayerStarError, ValueError, struct.error):
        return "foreign"
    if gate == RETAIL_GATE:
        return "retail"
    if gate == PATCHED_GATE:
        return "applied"
    return "foreign"


def read_settings(payload: bytes) -> dict[str, object]:
    """What the image's predicate does today."""

    state = status(payload)
    return {"status": state,
            "tag": f"roster record +0x{TAG_RECORD_OFFSET:02x} bit {TAG_BIT:#04x}" if state == "applied" else "none",
            "star_list_limit": STAR_LIST_LIMIT if state == "applied" else 0}


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; refuses anything but retail sites."""

    state = status(payload)
    if state == "applied":
        return payload, {"already_applied": True, "edits": [], "changed_bytes": 0, **read_settings(payload)}
    _require(state == "retail", f"player-star sites are {state}, not retail; refusing")
    buf = bytearray(payload)
    sections_ = _sections(payload)
    touched: set[int] = set()
    edits = []
    for label, va, before, after in sites():
        off = _offset(payload, va)
        _require(payload[off: off + len(before)] == before, f"{label}: retail bytes missing")
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections_, off).index)
        edits.append({"label": label, "va": f"0x{va:x}", "file_offset": f"0x{off:x}", "bytes": len(after),
                      "before": before.hex(), "after": after.hex()})
    for section in sections_:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {
        "edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched), "status": "applied",
        "gate_va": f"0x{GATE_VA:x}", "gate_bytes": GATE_SIZE, "in_place": True, "cave": None,
        "gate_labels": {name: f"0x{va:x}" for name, va in GATE_LABELS.items()},
        "tag": {"record_offset": f"0x{TAG_RECORD_OFFSET:02x}", "bit": TAG_BIT,
                "entity_field": f"entity+0x{ENTITY_RECORD_OFFSET:02x}"},
        "clamp": {"count_va": f"0x{STAR_COUNT_VA:x}", "list_va": f"0x{STAR_LIST_VA:x}",
                  "entry_bytes": STAR_ENTRY_SIZE, "limit": STAR_LIST_LIMIT,
                  "collides_with": f"0x{STAR_LIST_END_VA:x}"},
        "tail_call": f"FUN_0017ebd0 (0x{IS_USER_BODY_VA:x}, pure, returns 0 or 1)",
        "call_sites": [f"0x{va:x}" for va, _b in CALL_SITES],
        "side_effect": "the same predicate gates the on-field indicator text in FUN_00075d90",
    }


__all__ = ["CALL_SITES", "ENTITY_RECORD_OFFSET", "GAME_MODE_VA", "GATE_LABELS", "GATE_SIZE", "GATE_VA",
           "HUMAN_A_VA", "HUMAN_B_VA", "IS_USER_BODY_VA", "LIVE_PLAY", "NEXT_ROUTINE_VA", "PATCHED_GATE",
           "PINS", "PLAYER_RECORD_SIZE", "PLAY_STATE_VA", "PREV_ROUTINE_VA", "PlayerStarError", "RETAIL_GATE",
           "STAR_APPEND_VA", "STAR_COUNT_VA", "STAR_ENTRY_SIZE", "STAR_FLUSH_VA", "STAR_LIST_END_VA",
           "STAR_LIST_LIMIT", "STAR_LIST_VA", "TAG_BIT", "TAG_RECORD_OFFSET", "apply", "read_settings",
           "sites", "status"]
