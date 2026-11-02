"""Franchise extension footer ``2K5XTND1``: one versioned block store after a franchise save (b780 J2). EXPERIMENTAL.

Why (job b780 j23-footer, from the r4-records research)
------------------------------------------------------
Franchise history, records, box scores and the Hall of Fame need data the game never keeps. The Player Progress footer
(``PPGF0001``, v0.8) proved that a franchise save can carry extra bytes that the game's own save transaction writes and
signs. One more footer per feature would multiply the save sizes every admission check must know (native x career x
progress x ...), so this is ONE fixed-size footer with a block directory: a later feature takes a block, not a new size.

File layout (``SAVEGAME.DAT`` of a franchise)
---------------------------------------------
::

    native save            720,044 + arena growth (settings, ROST wrapper, season block, front office)
    MyCareer block         128 bytes, optional (``nfl2k5_my_career_save``)
    extension body         BODY_SIZE = 98,288 bytes, optional (this module)
    Player Progress footer 34,320 bytes, optional (``nfl2k5_player_progression``, byte for byte the v0.8 footer)

The Player Progress footer is always the LAST 34,320 bytes when present, exactly where a v0.8 game and the Player
Progress owner read it. So a beta-80 save loads on a Player Progress build without this footer (its progress intact),
and a v0.8 save loads here (its progress kept, the history starts empty and is written with the next save).

The native size comes from the ROST wrapper the save declares (``0x2E4``: arena + 0x20), never from guessing. The rest
decomposes uniquely into MyCareer (0 or 128) and one of ``FOOTER_SIZES`` = (0, 34,320, 98,288, 132,608): no two
combinations of any arena are equal, and none is a multiple of 4,096, so a footer can never look like a different arena
(arenas grow in 4 KB pages; that is why the body is 0x18000 - 16 bytes, not 96 KiB).

Body (``BODY_SIZE`` bytes, little endian)
-----------------------------------------
::

    +0x0000  header (64 B)
             +0x00 magic "2K5XTND1"      +0x08 u16 envelope version (1)   +0x0A u16 header size (64)
             +0x0C u32 body size         +0x10 u16 directory offset (0x40) +0x12 u16 directory slots (16)
             +0x14 u16 slot size (16)    +0x16 u16 reserved (0)
             +0x18 u32 flags: bit 0 the Player Progress footer follows
             +0x1C u32 save count (the host adds 1 at every save)
             +0x20 u16 franchise year index ([0xE576B8]) at the last save, +0x22 u8 stage, +0x23 u8 week
             +0x24 u32 host build stamp     +0x28..+0x3B reserved (0)
             +0x3C u32 Adler-32 of header bytes 0..0x3B followed by the 256 directory bytes
    +0x0040  directory: 16 slots x 16 B; slot n holds block id n + 1 (ids 1..16, fixed slots)
             +0 u16 block id (0 = slot unused), +2 u8 block version, +3 u8 flags (bit 0 present),
             +4 u32 offset (from the body start), +8 u32 size, +12 u32 Adler-32 of the block bytes
    +0x0140  host info (192 B, not checksummed; diagnostics the host writes at load/save, see INFO_FIELDS)
    +0x0200  blocks (BLOCKS below), each at a fixed offset; 0xF4A0..BODY_SIZE (35,664 B) is free for later blocks

The envelope (header, directory, slot meaning, sizes) never changes; blocks evolve by id and version. Readers keep a
block whose (id, version, offset, size, checksum) all match what they know and rebuild only that block otherwise; a
slot with an id they do not know is kept byte for byte (a newer build's block survives an older build's resave).

Lifecycle (native host ``nfl2k5_franchise_footer``)
---------------------------------------------------
* Fresh body = header + a present entry for every block of ``BLOCKS`` + each block's seed image (real history, when
  the build carries one; zero otherwise), sealed. A new franchise (``0x13EE10``) and a save without a body get one.
* Load: a body that passes the header checks is copied; each block is checked and a bad one rebuilt (the repaired
  blocks are recorded in the host info). A bad header means a fresh body. The Player Progress footer is copied to the
  Player Progress owner, or that owner starts a fresh baseline (its own old-save rule).
* Save: the host seals the body (block checksums, save count, year/stage/week, header checksum) and writes it after the
  native save and the MyCareer block, then the Player Progress footer when that owner is on.
* Memory: on a build with the 128 MB roster heap (K128) the body comes from the extra memory above 64 MB (no cost to the
  64 MB heap the game uses for menus and games); without the extra region (xemu at 64 MB) the history pauses: no body,
  saves are written without one. A build without K128 keeps the body in the executable's own writable memory.

Blocks (version 1; capture code: ``nfl2k5_history``, b780 J3)
------------------------------------------------------------
Every name is a 7-byte *person* (``nfl2k5_champions_history.pack_person``: first initial, up to nine letters of the
last name, 5-bit position code; position 31 = coach / none). Clubs are team-table indices 0..31; "club + 1" fields use
0 for none. Years are display years. See each block's ``*_LAYOUT`` text below for the field map.

======  ==========  =======  ======  =================================================================================
id      name        offset   size    content
======  ==========  =======  ======  =================================================================================
1       seasons     0x0200   18,960  ring of 32 seasons: standings line of every club, playoff result, coach, awards
2       totals      0x4C10   528     franchise-era totals per club (W-L-T, playoffs, titles)
3       records     0x4E20   9,520   club and league single-game and single-season records (franchise era)
4       leaders     0x7350   16,176  all-time club leaders (top 3 x 10) and league career leaders (top 5 x 10)
5       hall        0xB280   4,624   Hall of Fame inductees (192) and pending candidates (64)
6       boxscores   0xC490   12,304  this season's games of the user's club (24 x 512 B)
======  ==========  =======  ======  =================================================================================

Studio API (stable; j4-history, j5-seed, j6-hof, c1-coachdata build on it)
--------------------------------------------------------------------------
``layout(payload)``, ``body_of(payload)``, ``read_body(body)``, ``empty_body()``, ``seal(body)`` (the native
save), ``repair(body)`` (the native load),
``with_block(body, id, content)``, ``with_body(payload, body)``, ``admitted_sizes(arena_size)``,
``franchise_sizes()``, ``native_length(payload)``, the block codecs ``decode_seasons`` .. ``decode_boxscores`` and their
``encode_*`` / ``*_entry`` builders, ``BLOCKS``, ``BLOCK_BY_NAME``, ``BODY_SIZE``, ``PP_SIZE``, ``CAREER_SIZE``.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib
from typing import Iterable, Mapping, Sequence

from . import nfl2k5_roster_arena as _arena

SCHEMA = "nfl2k5_franchise_extension/v1"
MAGIC = b"2K5XTND1"
ENVELOPE_VERSION = 1
HEADER_SIZE = 64
DIRECTORY_OFFSET = 0x40
DIRECTORY_SLOTS = 16
SLOT_SIZE = 16
INFO_OFFSET = 0x140
INFO_SIZE = 0xC0
BLOCK_AREA = 0x200
BODY_SIZE = 0x18000 - 16                 # 98,288: never a multiple of 4,096 (see the module text)
CHECKSUM_AT = 0x3C
FLAG_PP_FOLLOWS = 1
ENTRY_PRESENT = 1

PP_SIZE = 34320                           # nfl2k5_player_progression.FOOTER_SIZE (checked below)
CAREER_SIZE = 128                         # nfl2k5_my_career_save.SIZE
FOOTER_SIZES = (0, PP_SIZE, BODY_SIZE, BODY_SIZE + PP_SIZE)
CAREER_SIZES = (0, CAREER_SIZE)

RETAIL_SAVE_SIZE = _arena.RETAIL_SAVE_SIZE       # 720,044
NATIVE_FROM_DECLARED = RETAIL_SAVE_SIZE - 0x91020  # native size = declared ROST size + 0x1EC8C
SUPPORTED_ARENAS = (_arena.RETAIL_SIZE,) + _arena.ARENA_SIZES
NATIVE_SIZES = tuple(_arena.save_size(size) for size in SUPPORTED_ARENAS)

INFO_FIELDS = (
    # (name, offset in the info area, struct format): written by the host; zero in a Studio-made body
    ("magic", 0x00, "<4s"),             # b"INFO" once the host wrote it
    ("load_result", 0x04, "<I"),       # LOAD_RESULTS
    ("repaired_mask", 0x08, "<I"),     # bit (id - 1) for every block rebuilt at the last load
    ("loads", 0x0C, "<I"),             # loads in this body's life
    ("saves", 0x10, "<I"),             # saves in this body's life (also header +0x1C)
    ("source", 0x14, "<I"),            # MEMORY_SOURCES: where the running body lived
    ("fresh_reason", 0x18, "<I"),      # FRESH_REASONS of the last fresh start
    ("captures", 0x1C, "<I"),          # game captures written by the history engine (nfl2k5_history)
    ("closes", 0x20, "<I"),            # season closes written by the history engine
    ("last_error", 0x24, "<I"),        # the history engine's last skipped-part code (0 = none)
)
LOAD_RESULTS = {0: "none", 1: "no body in the file (fresh)", 2: "loaded", 3: "bad header (fresh)",
                4: "loaded, blocks rebuilt"}
MEMORY_SOURCES = {0: "none", 1: "executable memory", 2: "extra memory (K128)", 3: "main heap"}
FRESH_REASONS = {0: "none", 1: "new franchise", 2: "load without a body", 3: "bad header", 4: "first use"}


class ExtensionError(ValueError):
    """The footer or the save around it cannot be read or written here."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExtensionError(message)


@dataclass(frozen=True)
class Block:
    id: int
    name: str
    version: int
    offset: int
    size: int
    summary: str


BLOCKS: tuple[Block, ...] = (
    Block(1, "seasons", 1, 0x0200, 18960, "ring of 32 seasons: every club's line, playoffs, coach, awards"),
    Block(2, "totals", 1, 0x4C10, 528, "franchise-era totals per club"),
    Block(3, "records", 1, 0x4E20, 9520, "club and league single-game and single-season records"),
    Block(4, "leaders", 1, 0x7350, 16176, "all-time club leaders and league career leaders"),
    Block(5, "hall", 1, 0xB280, 4624, "Hall of Fame inductees and pending candidates"),
    Block(6, "boxscores", 1, 0xC490, 12304, "this season's games of the user's club"),
)
BLOCK_BY_ID = {block.id: block for block in BLOCKS}
BLOCK_BY_NAME = {block.name: block for block in BLOCKS}
FREE_OFFSET = max(block.offset + block.size for block in BLOCKS)          # 0xF4A0
FREE_BYTES = BODY_SIZE - FREE_OFFSET                                     # 35,664
RESERVED_IDS = {7: "coaching (r2 carousel history, later)"}


def _check_static_layout() -> None:
    at = BLOCK_AREA
    for block in BLOCKS:
        assert block.offset == at and block.offset % 16 == 0 and block.size % 16 == 0, block
        assert 1 <= block.id <= DIRECTORY_SLOTS
        at += block.size
    assert FREE_OFFSET == 0xF4A0 and FREE_BYTES == 35664 and BODY_SIZE == 98288
    for arena_a in NATIVE_SIZES:
        for arena_b in NATIVE_SIZES:
            for career_a in CAREER_SIZES:
                for career_b in CAREER_SIZES:
                    for footer_a in FOOTER_SIZES:
                        for footer_b in FOOTER_SIZES:
                            if (arena_a, career_a, footer_a) != (arena_b, career_b, footer_b):
                                assert arena_a + career_a + footer_a != arena_b + career_b + footer_b
    for footer in FOOTER_SIZES[1:]:
        for career in CAREER_SIZES:
            assert (footer + career) % 4096


_check_static_layout()


# ------------------------------------------------------------------------------------------------ sizes and layout
def franchise_sizes() -> tuple[int, ...]:
    """Every franchise save size the Studio reads: each supported native size x MyCareer x footer."""

    return tuple(sorted(native + career + footer for native in NATIVE_SIZES for career in CAREER_SIZES
                        for footer in FOOTER_SIZES))


def admitted_sizes(arena_size: int) -> tuple[int, ...]:
    """The franchise save sizes the native save list admits on a build whose arena is ``arena_size``.

    The same family every native admission implements (this host's, Player Progress, MyCareer): retail saves
    (720,044), this build's own native size, and on an arena larger than beta-78's also beta-78's 847,020 saves (they
    load and migrate); each with or without the MyCareer block and with any footer of ``FOOTER_SIZES``."""

    natives = {RETAIL_SAVE_SIZE, _arena.save_size(arena_size)}
    if arena_size > _arena.LEGACY_CAPACITY_ARENA_SIZE:
        natives.add(_arena.LEGACY_CAPACITY_SAVE_SIZE)
    return tuple(sorted(native + career + footer for native in natives for career in CAREER_SIZES
                        for footer in FOOTER_SIZES))


@dataclass(frozen=True)
class Layout:
    native_size: int
    career_offset: int | None
    body_offset: int | None
    pp_offset: int | None
    total: int

    @property
    def footer_size(self) -> int:
        return self.total - self.native_size - (CAREER_SIZE if self.career_offset is not None else 0)


def _declared_native(payload: bytes) -> int | None:
    if len(payload) < 0x314 or bytes(payload[0x2E0:0x2E4]) != b"ROST":
        return None
    declared = struct.unpack_from("<I", payload, 0x2E4)[0]
    native = declared + NATIVE_FROM_DECLARED
    return native if native in NATIVE_SIZES else None


def layout(payload: bytes | bytearray) -> Layout | None:
    """Where the native save, the MyCareer block, the body and the Player Progress footer sit, or ``None``.

    ``None`` for anything that is not a franchise save of a supported arena followed by a known combination."""

    native = _declared_native(payload)
    if native is None:
        return None
    rest = len(payload) - native
    for career in CAREER_SIZES:
        footer = rest - career
        if footer in FOOTER_SIZES:
            body_at = native + career if footer in (BODY_SIZE, BODY_SIZE + PP_SIZE) else None
            pp_at = len(payload) - PP_SIZE if footer in (PP_SIZE, BODY_SIZE + PP_SIZE) else None
            return Layout(native, native if career else None, body_at, pp_at, len(payload))
    return None


def native_length(payload: bytes | bytearray) -> int:
    """Length of the native save plus the MyCareer block (every footer stripped); the input length if no footer."""

    found = layout(payload)
    if found is None:
        return len(payload)
    return found.native_size + (CAREER_SIZE if found.career_offset is not None else 0)


def body_of(payload: bytes | bytearray) -> bytes | None:
    found = layout(payload)
    if found is None or found.body_offset is None:
        return None
    return bytes(payload[found.body_offset:found.body_offset + BODY_SIZE])


def pp_footer_of(payload: bytes | bytearray) -> bytes | None:
    found = layout(payload)
    if found is None or found.pp_offset is None:
        return None
    return bytes(payload[found.pp_offset:])


def with_body(payload: bytes | bytearray, body: bytes | None) -> bytes:
    """The save with ``body`` inserted (or replaced, or removed for ``None``); native, MyCareer and Player Progress
    bytes are kept byte for byte."""

    found = layout(payload)
    _require(found is not None, "not a franchise save of a supported size")
    if body is not None:
        _require(len(body) == BODY_SIZE, "wrong body size")
        _require(read_body(body)["header_ok"], "the body does not read back")
    head = bytes(payload[:native_length(payload)])
    tail = bytes(payload[found.pp_offset:]) if found.pp_offset is not None else b""
    result = head + (bytes(body) if body is not None else b"") + tail
    again = layout(result)
    _require(again is not None and (again.body_offset is not None) == (body is not None)
             and (again.pp_offset is not None) == (found.pp_offset is not None), "the new layout does not read back")
    return result


# ------------------------------------------------------------------------------------------------ the body
def adler32(data: bytes, value: int = 1) -> int:
    return zlib.adler32(bytes(data), value) & 0xFFFFFFFF


def _header_sum(body: bytes | bytearray) -> int:
    return adler32(body[DIRECTORY_OFFSET:DIRECTORY_OFFSET + DIRECTORY_SLOTS * SLOT_SIZE], adler32(body[:CHECKSUM_AT]))


def _slot_at(slot: int) -> int:
    return DIRECTORY_OFFSET + slot * SLOT_SIZE


def _write_header(buf: bytearray, *, flags: int, saves: int = 0, year: int = 0, stage: int = 0, week: int = 0,
                  stamp: int = 0) -> None:
    struct.pack_into("<8sHHIHHHHIIHBBI", buf, 0, MAGIC, ENVELOPE_VERSION, HEADER_SIZE, BODY_SIZE, DIRECTORY_OFFSET,
                     DIRECTORY_SLOTS, SLOT_SIZE, 0, flags, saves, year, stage, week, stamp)


def empty_body(*, seeds: Mapping[int, bytes] | None = None, pp_follows: bool = False, stamp: int = 0) -> bytes:
    """A fresh, sealed body: every block present with its seed image (or zero). ``stamp``: the host build stamp the
    native host writes (``nfl2k5_franchise_footer.STAMP``); 0 for a Studio-made body."""

    seeds = dict(seeds or {})
    _require(set(seeds) <= set(BLOCK_BY_ID), "a seed names an unknown block")
    buf = bytearray(BODY_SIZE)
    _write_header(buf, flags=FLAG_PP_FOLLOWS if pp_follows else 0, stamp=stamp)
    for block in BLOCKS:
        content = seeds.get(block.id, bytes(block.size))
        _require(len(content) == block.size, f"the {block.name} seed has the wrong size")
        buf[block.offset:block.offset + block.size] = content
        struct.pack_into("<HBBIII", buf, _slot_at(block.id - 1), block.id, block.version, ENTRY_PRESENT,
                         block.offset, block.size, adler32(content))
    struct.pack_into("<I", buf, CHECKSUM_AT, _header_sum(buf))
    return bytes(buf)


def read_body(body: bytes | bytearray) -> dict:
    """{header_ok, header, entries, blocks (id -> bytes of every valid known block), bad (ids), unknown (ids), info}."""

    result = {"header_ok": False, "header": None, "entries": [], "blocks": {}, "bad": [], "unknown": [], "info": {}}
    if len(body) != BODY_SIZE or bytes(body[:8]) != MAGIC:
        return result
    (magic, version, header_size, body_size, dir_off, slots, slot_size, _r, flags, saves, year, stage, week,
     stamp) = struct.unpack_from("<8sHHIHHHHIIHBBI", body, 0)
    stored = struct.unpack_from("<I", body, CHECKSUM_AT)[0]
    if ((version, header_size, body_size, dir_off, slots, slot_size) !=
            (ENVELOPE_VERSION, HEADER_SIZE, BODY_SIZE, DIRECTORY_OFFSET, DIRECTORY_SLOTS, SLOT_SIZE)
            or stored != _header_sum(body)):
        return result
    result["header_ok"] = True
    result["header"] = {"flags": flags, "saves": saves, "year_index": year, "stage": stage, "week": week,
                        "stamp": stamp, "pp_follows": bool(flags & FLAG_PP_FOLLOWS)}
    for slot in range(DIRECTORY_SLOTS):
        block_id, version, entry_flags, offset, size, checksum = struct.unpack_from("<HBBIII", body, _slot_at(slot))
        if not block_id:
            continue
        entry = {"slot": slot, "id": block_id, "version": version, "flags": entry_flags, "offset": offset,
                 "size": size, "checksum": checksum}
        result["entries"].append(entry)
        known = BLOCK_BY_ID.get(block_id)
        if known is None or slot != block_id - 1:
            result["unknown"].append(block_id)
            continue
        content = bytes(body[offset:offset + size]) if offset + size <= BODY_SIZE else b""
        if ((version, offset, size) == (known.version, known.offset, known.size) and entry_flags & ENTRY_PRESENT
                and adler32(content) == checksum):
            result["blocks"][block_id] = content
        else:
            result["bad"].append(block_id)
    for block in BLOCKS:
        if block.id not in result["blocks"] and block.id not in result["bad"]:
            result["bad"].append(block.id)
    result["bad"].sort()
    for name, at, fmt in INFO_FIELDS:
        result["info"][name] = struct.unpack_from(fmt, body, INFO_OFFSET + at)[0]
    return result


def block_of(body: bytes | bytearray, name_or_id) -> bytes | None:
    block = BLOCK_BY_NAME[name_or_id] if isinstance(name_or_id, str) else BLOCK_BY_ID[name_or_id]
    return read_body(body)["blocks"].get(block.id)


def seal(body: bytes | bytearray) -> bytes:
    """What the native host does at a save: every known block's entry (id, version, flags, offset, size) rewritten
    and its checksum recomputed from the block's current bytes, then the header checksum. Unknown slots are kept byte
    for byte. (An in-RAM body's checksums are only current right after a load or a save; seal it before reading.)"""

    _require(len(body) == BODY_SIZE and bytes(body[:8]) == MAGIC, "not a franchise extension body")
    buf = bytearray(body)
    for block in BLOCKS:
        content = bytes(buf[block.offset:block.offset + block.size])
        struct.pack_into("<HBBIII", buf, _slot_at(block.id - 1), block.id, block.version, ENTRY_PRESENT,
                         block.offset, block.size, adler32(content))
    struct.pack_into("<I", buf, CHECKSUM_AT, _header_sum(buf))
    return bytes(buf)


def repair(body: bytes | bytearray, *, seeds: Mapping[int, bytes] | None = None) -> tuple[bytes, list[int]]:
    """What the native host does at a load: a body whose header fails is replaced by a fresh one; a known block whose
    entry fails (id, version, offset, size, present, checksum) is rebuilt from its seed (or zero). Returns the body and
    the rebuilt block ids (every id for a fresh body)."""

    view = read_body(body)
    if not view["header_ok"]:
        return empty_body(seeds=seeds), [block.id for block in BLOCKS]
    buf = bytearray(body)
    seeds = dict(seeds or {})
    for block_id in view["bad"]:
        block = BLOCK_BY_ID[block_id]
        content = seeds.get(block_id, bytes(block.size))
        buf[block.offset:block.offset + block.size] = content
        struct.pack_into("<HBBIII", buf, _slot_at(block_id - 1), block_id, block.version, ENTRY_PRESENT,
                         block.offset, block.size, adler32(content))
    struct.pack_into("<I", buf, CHECKSUM_AT, _header_sum(buf))
    return bytes(buf), list(view["bad"])


def with_block(body: bytes | bytearray, name_or_id, content: bytes) -> bytes:
    """The body with one block's content replaced, its entry and the header resealed (other blocks untouched)."""

    block = BLOCK_BY_NAME[name_or_id] if isinstance(name_or_id, str) else BLOCK_BY_ID[name_or_id]
    _require(len(content) == block.size, f"the {block.name} block is {block.size} bytes")
    _require(read_body(body)["header_ok"], "the body header does not read back; start from empty_body()")
    buf = bytearray(body)
    buf[block.offset:block.offset + block.size] = content
    struct.pack_into("<HBBIII", buf, _slot_at(block.id - 1), block.id, block.version, ENTRY_PRESENT, block.offset,
                     block.size, adler32(content))
    struct.pack_into("<I", buf, CHECKSUM_AT, _header_sum(buf))
    return bytes(buf)


def with_header(body: bytes, *, pp_follows: bool | None = None, saves: int | None = None) -> bytes:
    """The body with header flags/counters changed and the header resealed (Studio: Upgrade, tests)."""

    view = read_body(body)
    _require(view["header_ok"], "the body header does not read back")
    header = view["header"]
    buf = bytearray(body)
    flags = header["flags"]
    if pp_follows is not None:
        flags = (flags | FLAG_PP_FOLLOWS) if pp_follows else (flags & ~FLAG_PP_FOLLOWS)
    _write_header(buf, flags=flags, saves=header["saves"] if saves is None else saves, year=header["year_index"],
                  stage=header["stage"], week=header["week"], stamp=header["stamp"])
    struct.pack_into("<I", buf, CHECKSUM_AT, _header_sum(buf))
    return bytes(buf)


# ------------------------------------------------------------------------------------------------ people
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
COACH_POSITION = 31


def pack_person(first: str, last: str, position: int | str = COACH_POSITION) -> bytes:
    """The 7-byte person (``nfl2k5_champions_history.pack_person``'s packing, any position code 0..31)."""

    from . import nfl2k5_champions_history as champions
    code = POSITIONS.index(position) if isinstance(position, str) else int(position)
    _require(0 <= code <= 31, "position code out of range")
    name = (first + " " + last).strip() if first else last
    head = champions.pack_person(name, "QB")
    out = bytearray(head)
    for b in range(5):                       # replace the position bits (50..54)
        bit = 50 + b
        out[bit >> 3] &= ~(1 << (bit & 7)) & 0xFF
        if code >> b & 1:
            out[bit >> 3] |= 1 << (bit & 7)
    return bytes(out)


def unpack_person(raw: bytes) -> dict | None:
    from . import nfl2k5_champions_history as champions
    alphabet = " ABCDEFGHIJKLMNOPQRSTUVWXYZ-.' ?"
    first, pos = champions._get_bits(raw, 0, 5), champions._get_bits(raw, 50, 5)
    last = ""
    for i in range(9):
        s = champions._get_bits(raw, 5 + 5 * i, 5)
        if not s:
            break
        last += alphabet[s]
    if not last and not first:
        return None
    return {"initial": alphabet[first] if first else "", "last": last,
            "position": POSITIONS[pos] if pos < len(POSITIONS) else ("coach" if pos == COACH_POSITION else "?"),
            "position_code": pos}


# ------------------------------------------------------------------------------------------------ block 1: seasons
SEASON_RING = 32
SEASON_RECORD = 592
SEASON_AWARDS = ("mvp", "opoy", "dpoy", "oroy", "droy", "cpoy", "coy", "sb_mvp")
PLAYOFF_RESULTS = ("missed", "lost wild card", "lost divisional", "lost conference", "lost Super Bowl",
                   "won Super Bowl")
SEASONS_LAYOUT = """
seasons block (18,960 B): +0 u8 count (0..32), +1 u8 head (next ring slot), +2 u16 newest year, +4 u16 oldest year,
+6 u8 ring size (32), +7..+15 reserved; +16 + slot*592: season record
season record: +0 u16 year (0 = empty), +2 u8 flags (1 closed, 2 playoffs played, 4 user club known),
  +3 u8 regular-season weeks counted, +4 u8 champion+1, +5 u8 runner-up+1, +6 u8 champion points,
  +7 u8 runner-up points, +8 u8 user club+1, +9 u8 postseason games, +10..+15 reserved,
  +16 awards 8 x 8 B (person 7 + club+1): MVP, OPOY, DPOY, OROY, DROY, comeback, coach of the year, Super Bowl MVP,
  +80 clubs 32 x 16 B: +0 u8 wins, +1 u8 losses, +2 u8 ties (regular season), +3 u8 outcome (bits 0-2 playoff result
  0 missed .. 5 won Super Bowl, bit 3 division champion, bit 4 first-round bye, bits 5-6 division place - 1,
  bit 7 line valid), +4 u16 points for, +6 u16 points against (regular season), +8 person head coach at the close,
  +15 u8 playoff seed (0 none)
"""


def season_club_line(wins: int, losses: int, ties: int, *, playoff: int = 0, division_champion: bool = False,
                     bye: bool = False, place: int = 1, points_for: int = 0, points_against: int = 0,
                     coach: bytes = bytes(7), seed: int = 0) -> bytes:
    _require(0 <= playoff <= 5 and 1 <= place <= 4 and len(coach) == 7, "bad season line")
    outcome = playoff | (8 if division_champion else 0) | (16 if bye else 0) | (place - 1) << 5 | 0x80
    return struct.pack("<BBBBHH7sB", wins, losses, ties, outcome, points_for, points_against, coach, seed)


def season_record(year: int, clubs: Sequence[bytes], *, flags: int = 1, weeks: int = 17, champion: int | None = None,
                  runner_up: int | None = None, champion_points: int = 0, runner_points: int = 0,
                  user_club: int | None = None, postseason_games: int = 0,
                  awards: Mapping[str, tuple[bytes, int | None]] | None = None) -> bytes:
    _require(len(clubs) == 32 and all(len(c) == 16 for c in clubs), "32 club lines of 16 bytes")
    out = bytearray(SEASON_RECORD)
    struct.pack_into("<HBBBBBBBB", out, 0, year, flags, weeks, 0 if champion is None else champion + 1,
                     0 if runner_up is None else runner_up + 1, champion_points, runner_points,
                     0 if user_club is None else user_club + 1, postseason_games)
    for i, key in enumerate(SEASON_AWARDS):
        person, club = (awards or {}).get(key, (bytes(7), None))
        out[16 + 8 * i:16 + 8 * i + 7] = person
        out[16 + 8 * i + 7] = 0 if club is None else club + 1
    for i, line in enumerate(clubs):
        out[80 + 16 * i:96 + 16 * i] = line
    return bytes(out)


def encode_seasons(records: Sequence[bytes]) -> bytes:
    """A seasons block holding ``records`` (oldest first) in ring order, as the native close appends them."""

    _require(len(records) <= SEASON_RING, "at most 32 seasons")
    out = bytearray(BLOCK_BY_NAME["seasons"].size)
    years = []
    for i, record in enumerate(records):
        _require(len(record) == SEASON_RECORD, "season record size")
        out[16 + i * SEASON_RECORD:16 + (i + 1) * SEASON_RECORD] = record
        years.append(struct.unpack_from("<H", record, 0)[0])
    struct.pack_into("<BBHHB", out, 0, len(records), len(records) % SEASON_RING, years[-1] if years else 0,
                     years[0] if years else 0, SEASON_RING)
    return bytes(out)


def decode_seasons(block: bytes) -> list[dict]:
    """Stored seasons, newest first."""

    count, head, _newest, _oldest, ring = struct.unpack_from("<BBHHB", block, 0)
    rows = []
    for k in range(min(count, SEASON_RING)):
        slot = (head - 1 - k) % SEASON_RING
        at = 16 + slot * SEASON_RECORD
        year, flags, weeks, champ, runner, cp, rp, user, games = struct.unpack_from("<HBBBBBBBB", block, at)
        if not year:
            continue
        awards = {}
        for i, key in enumerate(SEASON_AWARDS):
            person = unpack_person(block[at + 16 + 8 * i:at + 23 + 8 * i])
            club = block[at + 23 + 8 * i]
            awards[key] = None if person is None else {**person, "club": club - 1 if club else None}
        clubs = []
        for c in range(32):
            w, l, t, outcome, pf, pa, coach, seed = struct.unpack_from("<BBBBHH7sB", block, at + 80 + 16 * c)
            clubs.append(None if not outcome & 0x80 else {
                "wins": w, "losses": l, "ties": t, "playoff": PLAYOFF_RESULTS[min(outcome & 7, 5)],
                "playoff_code": outcome & 7, "division_champion": bool(outcome & 8), "bye": bool(outcome & 16),
                "place": (outcome >> 5 & 3) + 1, "points_for": pf, "points_against": pa,
                "coach": unpack_person(coach), "seed": seed})
        rows.append({"year": year, "flags": flags, "weeks": weeks, "champion": champ - 1 if champ else None,
                     "runner_up": runner - 1 if runner else None, "champion_points": cp, "runner_up_points": rp,
                     "user_club": user - 1 if user else None, "postseason_games": games, "awards": awards,
                     "clubs": clubs})
    return rows


# ------------------------------------------------------------------------------------------------ block 2: totals
TOTALS_LAYOUT = """
totals block (528 B): +0 u16 first year, +2 u16 seasons closed, +4..+15 reserved; +16 + club*16:
  +0 u16 wins, +2 u16 losses, +4 u16 ties (regular season), +6 u8 playoff appearances, +7 u8 division titles,
  +8 u8 Super Bowl appearances, +9 u8 Super Bowl wins, +10 u8 seasons, +11 u8 winning seasons,
  +12 u16 playoff wins, +14 u16 playoff losses
"""
TOTAL_FIELDS = ("wins", "losses", "ties", "playoffs", "division_titles", "sb_appearances", "sb_wins", "seasons",
                "winning_seasons", "playoff_wins", "playoff_losses")
_TOTAL = struct.Struct("<HHHBBBBBBHH")


def encode_totals(first_year: int, seasons: int, clubs: Sequence[Mapping[str, int]]) -> bytes:
    _require(len(clubs) == 32, "32 clubs")
    out = bytearray(BLOCK_BY_NAME["totals"].size)
    struct.pack_into("<HH", out, 0, first_year, seasons)
    for i, club in enumerate(clubs):
        _TOTAL.pack_into(out, 16 + 16 * i, *(int(club.get(k, 0)) for k in TOTAL_FIELDS))
    return bytes(out)


def decode_totals(block: bytes) -> dict:
    first, seasons = struct.unpack_from("<HH", block, 0)
    return {"first_year": first, "seasons": seasons,
            "clubs": [dict(zip(TOTAL_FIELDS, _TOTAL.unpack_from(block, 16 + 16 * i))) for i in range(32)]}


# ------------------------------------------------------------------------------------------------ block 3: records
RECORD_CATEGORIES = ("passing_yards", "passing_td", "completions", "rushing_yards", "rushing_td", "receptions",
                     "receiving_yards", "receiving_td", "sacks_half", "interceptions", "tackles", "forced_fumbles")
RECORD_KINDS = ("game", "season")
RECORD_ENTRY = 12
RECORDS_LAYOUT = """
records block (9,520 B): +0 u8 categories (12), +1 u8 clubs (32), +2..+15 reserved;
  +16 club records: entry ((club*12 + category)*2 + kind) of 12 B (kind 0 single game, 1 single season);
  +9232 league records: entry (category*2 + kind);
  entry: person (7), u8 club+1, u16 value, u8 year - 1900 (0 = empty), u8 week row + 1 (game records; 0 season)
  categories: passing yards, passing TD, completions, rushing yards, rushing TD, receptions, receiving yards,
  receiving TD, sacks (half sacks), interceptions, tackles, forced fumbles
"""
LEAGUE_RECORDS_AT = 16 + 32 * len(RECORD_CATEGORIES) * 2 * RECORD_ENTRY      # 9,232


def record_entry(person: bytes, club: int | None, value: int, year: int, week_row: int | None = None) -> bytes:
    _require(len(person) == 7 and 1901 <= year <= 2155 and 0 <= value <= 0xFFFF, "bad record entry")
    return person + struct.pack("<BHBB", 0 if club is None else club + 1, value, year - 1900,
                                0 if week_row is None else week_row + 1)


def _record_view(raw: bytes) -> dict | None:
    club, value, year, week = struct.unpack_from("<BHBB", raw, 7)
    if not year:
        return None
    return {"person": unpack_person(raw[:7]), "club": club - 1 if club else None, "value": value,
            "year": 1900 + year, "week_row": week - 1 if week else None}


def encode_records(club_records: Mapping[tuple[int, str, str], bytes] | None = None,
                   league_records: Mapping[tuple[str, str], bytes] | None = None) -> bytes:
    out = bytearray(BLOCK_BY_NAME["records"].size)
    out[0], out[1] = len(RECORD_CATEGORIES), 32
    for (club, category, kind), entry in (club_records or {}).items():
        index = (club * len(RECORD_CATEGORIES) + RECORD_CATEGORIES.index(category)) * 2 + RECORD_KINDS.index(kind)
        out[16 + index * RECORD_ENTRY:16 + (index + 1) * RECORD_ENTRY] = entry
    for (category, kind), entry in (league_records or {}).items():
        index = RECORD_CATEGORIES.index(category) * 2 + RECORD_KINDS.index(kind)
        at = LEAGUE_RECORDS_AT + index * RECORD_ENTRY
        out[at:at + RECORD_ENTRY] = entry
    return bytes(out)


def decode_records(block: bytes) -> dict:
    clubs = {}
    for club in range(32):
        for c, category in enumerate(RECORD_CATEGORIES):
            for k, kind in enumerate(RECORD_KINDS):
                index = (club * len(RECORD_CATEGORIES) + c) * 2 + k
                view = _record_view(block[16 + index * RECORD_ENTRY:16 + (index + 1) * RECORD_ENTRY])
                if view:
                    clubs[(club, category, kind)] = view
    league = {}
    for c, category in enumerate(RECORD_CATEGORIES):
        for k, kind in enumerate(RECORD_KINDS):
            at = LEAGUE_RECORDS_AT + (c * 2 + k) * RECORD_ENTRY
            view = _record_view(block[at:at + RECORD_ENTRY])
            if view:
                league[(category, kind)] = view
    return {"clubs": clubs, "league": league}


# ------------------------------------------------------------------------------------------------ block 4: leaders
LEADER_CATEGORIES = ("passing_yards", "passing_td", "rushing_yards", "rushing_td", "receptions", "receiving_yards",
                     "receiving_td", "sacks_half", "interceptions", "tackles")
CLUB_DEPTH, LEAGUE_DEPTH = 3, 5
LEADER_ENTRY = 16
LEADER_VALID, LEADER_REAL, LEADER_LINKED, LEADER_NEW = 1, 2, 4, 8
LEAGUE_LEADERS_AT = 16 + 32 * len(LEADER_CATEGORIES) * CLUB_DEPTH * LEADER_ENTRY  # 15,376
NO_PLAYER = 0xFFFF
LEADERS_LAYOUT = """
leaders block (16,176 B): +0 u8 categories (10), +1 u8 club depth (3), +2 u8 league depth (5), +3..+15 reserved;
  +16 club leaders: entry ((club*10 + category)*3 + rank) of 16 B; +15,376 league career leaders: (category*5 + rank)
  entry: person (7), u8 flags (1 valid, 2 real history (seeded), 4 linked to an active player, 8 franchise-era entry),
  u32 value (career total; sacks in half sacks), u16 player record index (0xFFFF none), u16 identity check (record +6)
  categories: passing yards, passing TD, rushing yards, rushing TD, receptions, receiving yards, receiving TD,
  sacks (half sacks), interceptions, tackles
"""


def leader_entry(person: bytes, value: int, *, flags: int = LEADER_VALID, player: int = NO_PLAYER,
                 check: int = 0) -> bytes:
    _require(len(person) == 7 and 0 <= value <= 0xFFFFFFFF, "bad leader entry")
    return person + struct.pack("<BIHH", flags | LEADER_VALID, value, player, check)


def _leader_view(raw: bytes) -> dict | None:
    flags, value, player, check = struct.unpack_from("<BIHH", raw, 7)
    if not flags & LEADER_VALID:
        return None
    return {"person": unpack_person(raw[:7]), "value": value, "real": bool(flags & LEADER_REAL),
            "linked": bool(flags & LEADER_LINKED), "new": bool(flags & LEADER_NEW),
            "player": None if player == NO_PLAYER else player, "check": check}


def encode_leaders(club_leaders: Mapping[tuple[int, str], Sequence[bytes]] | None = None,
                   league_leaders: Mapping[str, Sequence[bytes]] | None = None) -> bytes:
    out = bytearray(BLOCK_BY_NAME["leaders"].size)
    out[0], out[1], out[2] = len(LEADER_CATEGORIES), CLUB_DEPTH, LEAGUE_DEPTH
    for (club, category), entries in (club_leaders or {}).items():
        _require(len(entries) <= CLUB_DEPTH, "three club leaders per category")
        for rank, entry in enumerate(entries):
            index = (club * len(LEADER_CATEGORIES) + LEADER_CATEGORIES.index(category)) * CLUB_DEPTH + rank
            out[16 + index * LEADER_ENTRY:16 + (index + 1) * LEADER_ENTRY] = entry
    for category, entries in (league_leaders or {}).items():
        _require(len(entries) <= LEAGUE_DEPTH, "five league leaders per category")
        for rank, entry in enumerate(entries):
            at = LEAGUE_LEADERS_AT + (LEADER_CATEGORIES.index(category) * LEAGUE_DEPTH + rank) * LEADER_ENTRY
            out[at:at + LEADER_ENTRY] = entry
    return bytes(out)


def decode_leaders(block: bytes) -> dict:
    clubs = {}
    for club in range(32):
        for c, category in enumerate(LEADER_CATEGORIES):
            rows = []
            for rank in range(CLUB_DEPTH):
                index = (club * len(LEADER_CATEGORIES) + c) * CLUB_DEPTH + rank
                view = _leader_view(block[16 + index * LEADER_ENTRY:16 + (index + 1) * LEADER_ENTRY])
                if view:
                    rows.append(view)
            if rows:
                clubs[(club, category)] = rows
    league = {}
    for c, category in enumerate(LEADER_CATEGORIES):
        rows = []
        for rank in range(LEAGUE_DEPTH):
            at = LEAGUE_LEADERS_AT + (c * LEAGUE_DEPTH + rank) * LEADER_ENTRY
            view = _leader_view(block[at:at + LEADER_ENTRY])
            if view:
                rows.append(view)
        if rows:
            league[category] = rows
    return {"clubs": clubs, "league": league}


# ------------------------------------------------------------------------------------------------ block 5: hall
HALL_INDUCTEES, HALL_CANDIDATES = 192, 64
INDUCTEE_ENTRY, CANDIDATE_ENTRY = 16, 24
CANDIDATES_AT = 16 + HALL_INDUCTEES * INDUCTEE_ENTRY            # 3,088
HALL_VALID, HALL_REAL, HALL_NEW = 1, 2, 4
HALL_LAYOUT = """
hall block (4,624 B): +0 u8 inductees (0..192), +1 u8 candidates (0..64), +2 u16 last class year, +4..+15 reserved;
  +16 inductees 192 x 16 B in induction order: person (7), u8 main club+1, u16 induction year, u16 retirement year,
      u8 flags (1 valid, 2 real history, 4 franchise era), u8 seasons, u16 score
  +3,088 candidates 64 x 24 B: person (7), u8 main club+1, u16 retirement year, u16 score, u8 seasons,
      u8 flags (1 valid, 2 real history), u16 x 3 key career numbers (by position, see HALL_KEYS), u8 honors
      (MVP + player of the year + All-Pro + Pro Bowl seasons), u8 Super Bowl wins, u16 reserved
"""
HALL_KEYS = {"QB": ("passing_td", "passing_yards_k", "wins"), "HB": ("rushing_yards", "rushing_td", "receptions"),
             "WR": ("receptions", "receiving_yards", "receiving_td"), "TE": ("receptions", "receiving_yards",
                                                                          "receiving_td"),
             "defense": ("tackles", "sacks_half", "interceptions"), "line": ("seasons_started", "pro_bowls", "all_pro")}


def inductee_entry(person: bytes, club: int | None, inducted: int, retired: int = 0, *, flags: int = HALL_VALID,
                   seasons: int = 0, score: int = 0) -> bytes:
    _require(len(person) == 7, "bad inductee")
    return person + struct.pack("<BHHBBH", 0 if club is None else club + 1, inducted, retired, flags | HALL_VALID,
                                seasons, score)


def candidate_entry(person: bytes, club: int | None, retired: int, *, score: int = 0, seasons: int = 0,
                    flags: int = HALL_VALID, keys: Sequence[int] = (0, 0, 0), honors: int = 0,
                    sb_wins: int = 0) -> bytes:
    _require(len(person) == 7 and len(keys) == 3, "bad candidate")
    return person + struct.pack("<BHHBBHHHBBH", 0 if club is None else club + 1, retired, score, seasons,
                                flags | HALL_VALID, *keys, honors, sb_wins, 0)


def encode_hall(inductees: Sequence[bytes] = (), candidates: Sequence[bytes] = (), last_class: int = 0) -> bytes:
    _require(len(inductees) <= HALL_INDUCTEES and len(candidates) <= HALL_CANDIDATES, "hall capacity")
    out = bytearray(BLOCK_BY_NAME["hall"].size)
    struct.pack_into("<BBH", out, 0, len(inductees), len(candidates), last_class)
    for i, entry in enumerate(inductees):
        out[16 + i * INDUCTEE_ENTRY:16 + (i + 1) * INDUCTEE_ENTRY] = entry
    for i, entry in enumerate(candidates):
        out[CANDIDATES_AT + i * CANDIDATE_ENTRY:CANDIDATES_AT + (i + 1) * CANDIDATE_ENTRY] = entry
    return bytes(out)


def decode_hall(block: bytes) -> dict:
    count, pending, last = struct.unpack_from("<BBH", block, 0)
    inductees, candidates = [], []
    for i in range(min(count, HALL_INDUCTEES)):
        raw = block[16 + i * INDUCTEE_ENTRY:16 + (i + 1) * INDUCTEE_ENTRY]
        club, inducted, retired, flags, seasons, score = struct.unpack_from("<BHHBBH", raw, 7)
        if flags & HALL_VALID:
            inductees.append({"person": unpack_person(raw[:7]), "club": club - 1 if club else None,
                              "inducted": inducted, "retired": retired, "real": bool(flags & HALL_REAL),
                              "new": bool(flags & HALL_NEW), "seasons": seasons, "score": score})
    for i in range(min(pending, HALL_CANDIDATES)):
        raw = block[CANDIDATES_AT + i * CANDIDATE_ENTRY:CANDIDATES_AT + (i + 1) * CANDIDATE_ENTRY]
        club, retired, score, seasons, flags, k1, k2, k3, honors, sb, _r = struct.unpack_from("<BHHBBHHHBBH", raw, 7)
        if flags & HALL_VALID:
            candidates.append({"person": unpack_person(raw[:7]), "club": club - 1 if club else None,
                               "retired": retired, "score": score, "seasons": seasons,
                               "real": bool(flags & HALL_REAL), "keys": (k1, k2, k3), "honors": honors,
                               "sb_wins": sb})
    return {"last_class": last, "inductees": inductees, "candidates": candidates}


# ------------------------------------------------------------------------------------------------ block 6: box scores
BOX_GAMES, BOX_ENTRY, BOX_LINES = 24, 512, 23
TEAM_STATS = ("points", "first_downs", "total_yards", "passing_yards", "rushing_yards", "pass_attempts",
              "completions", "rush_attempts", "turnovers", "interceptions_thrown", "fumbles_lost", "sacks_allowed",
              "penalties", "penalty_yards", "third_down_made", "third_down_attempts")
LINE_KINDS = {1: ("passing", ("completions", "attempts", "yards", "td", "int", "rush_yards")),
              2: ("rushing", ("attempts", "yards", "td", "receptions", "rec_yards", "rec_td")),
              3: ("receiving", ("receptions", "yards", "td", "rush_attempts", "rush_yards", "rush_td")),
              4: ("defense", ("tackles", "sacks_half", "interceptions", "forced_fumbles", "fumble_recoveries",
                              "def_td")),
              5: ("kicking", ("fg_made", "fg_attempts", "xp_made", "xp_attempts", "long", "punts"))}
LEADER_KINDS = {1: "passing", 2: "rushing", 3: "receiving", 4: "defense"}
BOX_PLAYED, BOX_SIMULATED = 2, 4
BOXSCORES_LAYOUT = """
boxscores block (12,304 B): +0 u16 year, +2 u8 games (0..24), +3 u8 user club+1, +4..+15 reserved;
  +16 + game*512: +0 u8 week row, +1 u8 slot, +2 u8 home club, +3 u8 away club, +4 u8 home points, +5 u8 away
  points, +6 u8 user side (0 home, 1 away), +7 u8 flags (1 valid, 2 played by the user, 4 simulated),
  +8 u8 user lines, +9..+15 reserved,
  +16 team stats: home then away, 16 x u16 each (TEAM_STATS),
  +80 opponent leaders 4 x 16 B: person (7), u8 kind (1 passing, 2 rushing, 3 receiving, 4 defense), 4 x i16,
  +144 user club lines 23 x 16 B: u16 player record index, u8 position code, u8 kind (LINE_KINDS), 6 x i16
"""


def decode_boxscores(block: bytes) -> dict:
    year, games, user = struct.unpack_from("<HBB", block, 0)
    rows = []
    for g in range(min(games, BOX_GAMES)):
        at = 16 + g * BOX_ENTRY
        row, slot, home, away, hp, ap, side, flags, lines = struct.unpack_from("<BBBBBBBBB", block, at)
        if not flags & 1:
            continue
        stats = [dict(zip(TEAM_STATS, struct.unpack_from("<16H", block, at + 16 + 32 * side_index)))
                 for side_index in range(2)]
        leaders = []
        for k in range(4):
            raw = block[at + 80 + 16 * k:at + 96 + 16 * k]
            kind = raw[7]
            if kind:
                leaders.append({"person": unpack_person(raw[:7]), "kind": LEADER_KINDS.get(kind, "?"),
                                "values": struct.unpack_from("<4h", raw, 8)})
        user_lines = []
        for k in range(min(lines, BOX_LINES)):
            player, position, kind, *values = struct.unpack_from("<HBB6h", block, at + 144 + 16 * k)
            name, fields = LINE_KINDS.get(kind, ("?", ("v1", "v2", "v3", "v4", "v5", "v6")))
            user_lines.append({"player": player, "position": position, "kind": name,
                               "values": dict(zip(fields, values))})
        rows.append({"week_row": row, "slot": slot, "home": home, "away": away, "home_points": hp,
                     "away_points": ap, "user_side": side, "played": bool(flags & BOX_PLAYED),
                     "simulated": bool(flags & BOX_SIMULATED), "team_stats": stats, "opponent_leaders": leaders,
                     "lines": user_lines})
    return {"year": year, "user_club": user - 1 if user else None, "games": rows}


# ------------------------------------------------------------------------------------------------ a whole save
def describe(payload: bytes | bytearray) -> dict:
    """Plain summary of the footers of a franchise save (Studio, project doctor, reports)."""

    found = layout(payload)
    if found is None:
        return {"franchise_save": False, "size": len(payload)}
    out = {"franchise_save": True, "size": len(payload), "native_size": found.native_size,
           "mycareer": found.career_offset is not None, "player_progress": found.pp_offset is not None,
           "extension": found.body_offset is not None}
    body = body_of(payload)
    if body is not None:
        view = read_body(body)
        out.update(header_ok=view["header_ok"], header=view["header"], bad_blocks=view["bad"],
                   unknown_blocks=view["unknown"], info=view["info"])
        if view["header_ok"] and 1 in view["blocks"]:
            seasons = decode_seasons(view["blocks"][1])
            out["seasons_stored"] = len(seasons)
            out["newest_season"] = seasons[0]["year"] if seasons else None
    return out


assert PP_SIZE == __import__("mod_editor.core.nfl2k5_player_progression", fromlist=["FOOTER_SIZE"]).FOOTER_SIZE \
    if __package__ == "mod_editor.core" else True

__all__ = ["BLOCKS", "BLOCK_BY_ID", "BLOCK_BY_NAME", "BODY_SIZE", "Block", "CAREER_SIZE", "CAREER_SIZES",
           "ExtensionError", "FOOTER_SIZES", "FREE_BYTES", "FREE_OFFSET", "Layout", "MAGIC", "PP_SIZE", "SCHEMA",
           "admitted_sizes", "block_of", "body_of", "candidate_entry", "decode_boxscores", "decode_hall",
           "decode_leaders", "decode_records", "decode_seasons", "decode_totals", "describe", "empty_body",
           "encode_hall", "encode_leaders", "encode_records", "encode_seasons", "encode_totals", "franchise_sizes",
           "inductee_entry", "layout", "leader_entry", "native_length", "pack_person", "pp_footer_of", "read_body",
           "record_entry", "repair", "season_club_line", "season_record", "seal", "unpack_person", "with_block",
           "with_body",
           "with_header"]
