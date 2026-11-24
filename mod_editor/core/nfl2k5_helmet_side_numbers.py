"""Helmet side numbers: kit helmet-number route 5 binds a new number set E, a late executable owner.
EXPERIMENTAL / UNWITNESSED.

How the game binds helmet numbers (PROVED OFFLINE, b81 helmet sides): a kit's Unif payload +0x0C is its helmet-number
route (0 none, 1..4). The player builder's helmet block (0x8F02E..0x8F062) reads it through 0x8E830, maps it to a
number row with ``mov ecx, [ecx*4 + 0x4EF874]`` at 0x8F041 (retail rows 1, 1, 2, 3, 4 for routes 0..4) and calls the
selector 0x8E910 with edx 0xD (helmet digits) and the MODEL ROW [ebp+8] (0 lo_body, 1 hi_body, 2 hi_head). The selector
reads the material index of each cell at 0xA86D6C/D/E + 16 * row + 3 * model row (L, M, R; 0xFF = none) and the binder
0x8E8D0 (or Number kerning's 0x8E8D2) shows that material with the digit texture. The row records 0xA86D68 + 16 * row
(rows 0..13: +0 the UTF-16 name format, "NUMBER_helmet_D_%c" for row 4; +4..+15 the cells of four model rows) are
filled when each model loads, by the registration loop 0x909C7..0x90AB0: per row, per letter L/M/R, sprintf the name
(0x4A410), find the model's material of that name (0x30C40) and store its index or 0xFF; the loop ends with
``cmp eax, 0xA86E38; jle`` at 0x90A9E. Route 5 reads [0x4EF888] = 0, row 0 "NUMBER_%c": the jersey number, so a route-5
kit today binds its helmet digits into the lo_body's far jersey-number cells.

What this owner changes (the selector, the binder and every retail table are untouched):
  * 0x8F044, the 4-byte table address of ``mov ecx, [ecx*4 + 0x4EF874]``, points to the owner's own 6-dword table
    1, 1, 2, 3, 4, k (routes 0..4 map exactly as in retail; route 5 maps to row k, never to row 0).
  * Row k is a 16-byte record R at page + 0x108 of the owner's own fixed page (review 11/22: no separate data
    allocation; the scale-out pool is RWX), so R = 0xA86D68 (mod 16) and k = (R - 0xA86D68) / 16; R lies above every
    retail row, so the selector's ``16 * row + 3 * model row`` addressing reaches exactly R's cells and nothing else.
    The file holds R's name pointer (L"NUMBER_helmet_E_%c") and twelve 0xFF cells; the game writes the cells.
  * A 5-byte hook at 0x90AB1 (``push 0xE65610``, the first instruction after the registration loop) jumps to the
    cave. When the retail rows are done ([esp+0x18] = 0xA86E48) it points the loop at R (should R's name pointer
    ever read otherwise it writes it and sets all twelve cells to 0xFF, as the file holds them), sets the cell pointer
    [esp+0x10] = R + 4 + 3 * model row and jumps back into the retail loop body 0x909F0, so the game's own code names,
    searches and stores E's cells. When the loop falls out again ([esp+0x18] = R + 0x10) the cave puts back the
    loop's retail exit state (eax, ecx, edx, [esp+0x10], [esp+0x14], [esp+0x18]; ebx and edi are the last name
    search's scratch, rewritten before any read), runs the displaced push and returns to 0x90AB6.
  A model without NUMBER_helmet_E_L/M/R (hi_body, a scene without the grown set, a retail scene) stores 0xFF and route
  5 draws nothing. No retail kit uses route 5; the kit rows that use it are written by the side-numbers build step.

Why 0x4EF888 is not edited: that dword is route 5's retail entry AND the first dword of another table (the code at
0x8F8D6 reads it), so the route table is replaced by pointer, never patched in place.

GUARDS (retail bytes pinned; anything else is refused as foreign): the helmet block 0x8F02E..0x8F062, the route getter
0x8E830, the registration loop with its tail 0x909C7..0x90AB6, the retail route rows 0x4EF874, L"LMR" 0x4EEF60, the
name compare 0x30C40 and the sprintf stub 0x4A410; the selector/binder block 0x8E8D0..0x8E9DF must be retail or Number
kerning's rewrite (nfl2k5_number_kerning.status), which keeps the same cell addressing. It commutes with Number
kerning, Jersey number sizes (hook 0x8F580) and Hair styles (0x8F5B9). Guardian's builder guard (0x8EFA0, 194 bytes)
covers 0x8F041, and this owner's helmet-block guard covers Guardian's bind hook 0x8F02E: the two refuse each other,
as Guardian and Hair styles already do.

Install order (review 11/22): one fixed page right after the quarterback trades page (nfl2k5_xbe_space.HELMET_SIDES_VA),
placed like the quarterback pages: at its absolute address, never advancing the pool cursor, and every other pool owner
steps over it whether or not it is requested. So the owner can be added in place after every other owner, and an owner a
disc lacks (the injury bank of a disc built with Simulated injuries Retail) can still be added in place after it: the
FAQ's Build-tab copy keeps working. Removal (``remove``) follows the gadget-play pattern: the two sites back to their
retail bytes and the page back to its int3 fill; the reservation stays, so nothing moves. Applying to an image whose page
is already reserved and then removing returns the same bytes. A clean retail executable comes from rebuilding.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Mapping

OWNER = "nfl2k5_helmet_side_numbers"
LABEL = "EXPERIMENTAL / UNWITNESSED"
BUILD_KEY = "helmet_side_numbers"
BUILD_CAPTION = "Helmet side numbers (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Kits whose helmet-number route is 5 draw their helmet numbers on the new side "
    "number set E (NUMBER_helmet_E_L/M/R) instead of the jersey-number cells. Routes 0-4 stay exactly as the game "
    "draws them. Off = the executable keeps its retail bytes.")
ROUTE = 5
ROW_FORMAT = "NUMBER_helmet_E_%c"
CODE_SIZE = 0x1000                                   # one fixed page (nfl2k5_xbe_space.HELMET_SIDES_VA), the pool is RWX
REQUESTS = ((OWNER, "code", CODE_SIZE, CODE_SIZE),)  # = nfl2k5_xbe_space.HELMET_SIDES_REQUEST
TABLE_OFFSET = 0x80                                  # the 6-dword route -> row table
FORMAT_OFFSET = 0x98                                 # L"NUMBER_helmet_E_%c"
ROW_OFFSET = 0x108                                   # R = page + 0x108 (= 0xA86D68 mod 16), written by the game

ROWS_VA, ROW_SIZE = 0xA86D68, 16                     # row records 0..13: +0 name format, +4 cells [model row][L, M, R]
LOOP_BOUND, LOOP_EXIT = 0xA86E38, 0xA86E48           # cmp eax, 0xA86E38 (signed jle); the row pointer at the fall-out
RETAIL_ROUTE_TABLE = 0x4EF874
RETAIL_ROUTE_ROWS = (1, 1, 2, 3, 4)                  # routes 0..4 (route 5 = [0x4EF888], shared with another table)
ROUTE_SITE, ROUTE_RETAIL = 0x8F041, bytes.fromhex("8b0c8d74f84e00")    # mov ecx, [ecx*4 + 0x4EF874]
HOOK_VA, HOOK_RETAIL = 0x90AB1, bytes.fromhex("681056e600")             # push 0xE65610
RESUME_VA = HOOK_VA + len(HOOK_RETAIL)               # 0x90AB6 mov edx, 'TXTR'
TAIL_PUSH = 0xE65610
LOOP_BODY = 0x909F0                                  # per-row body: name, search, store L, M, R
ROW13_CELL_END = 13 * ROW_SIZE + 3                   # retail ecx / [esp+0x14] at the fall-out, from [esp+0x30]
ROWS_SPAN = 14 * ROW_SIZE                            # retail [esp+0x10] / edx at the fall-out, from [esp+0x30]
PLACEHOLDER_VA = 0x14DA000                           # only the retail half of the sites is read without an allocation
#: (va, size, sha256) of the retail code and data the change relies on
GUARDS = (
    (0x8F02E, 0x34, "31aa3e1670517c3109d68b0084ec0e698cad56e9095f67651cb335722af8205b"),  # helmet-number block
    (0x8E830, 0x0B, "61f6f91fdd0e2d134549d74422112a85d6bf118dedc46d5f4286b67428054816"),  # route getter (Unif +0x0C)
    (0x909C7, 0xEF, "00fa89270cf0ece2ad171ca575024086ad027f31baa2dfd06647945fbd82e5a2"),  # registration loop + tail
    (0x4EF874, 0x18, "80e98d16a76109bae3919446917e7731c7975e4ad3749c6dd46d1652be1cc366"),  # retail route rows
    (0x4EEF60, 0x06, "8b66a77f713d30eaa4a2b2d93f6450192091bd4e1167cb96abbe902bd4128f3c"),  # L"LMR"
    (0x30C40, 0x25, "dd3d52cc45c43dc86d8db7220d777346237b324dd9a00dce35c9de3362bbfdee"),   # name compare
    (0x4A410, 0x05, "fcddef1fc9692988cf1e15e5311e054bb8ce1c13295f924b432d54c022e7c852"),   # sprintf stub
)
_FAILURES = (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError, UnicodeError)


class HelmetSideNumbersError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise HelmetSideNumbersError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _p32(value):
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


# ------------------------------------------------------------------------------------------------ addresses

def row_va(code_va: int) -> int:
    """R, the owner's row record: page + 0x108 (review 11/22: in the owner's own fixed RWX page, no data allocation). It
    must sit on the retail rows' 16-byte grid, above the loop bound and below 2 GiB (the loop's bound check is signed)."""
    _require(type(code_va) is int and code_va % CODE_SIZE == 0, "the helmet side numbers page must be page-aligned")
    row = code_va + ROW_OFFSET
    _require(row % ROW_SIZE == ROWS_VA % ROW_SIZE and LOOP_BOUND < row and row + ROW_SIZE < 0x80000000,
             "the helmet side numbers row is off the row grid")
    return row


def row_index(row: int) -> int:
    """k, the number row of R (what route 5 maps to)."""
    _require((row - ROWS_VA) % ROW_SIZE == 0 and row > LOOP_BOUND, "not a row record address")
    return (row - ROWS_VA) // ROW_SIZE


def table_va(code_va: int) -> int:
    return code_va + TABLE_OFFSET


def format_va(code_va: int) -> int:
    return code_va + FORMAT_OFFSET


# ------------------------------------------------------------------------------------------------ the cave

def code_for(code_va: int) -> bytes:
    """The owned page (CODE_SIZE bytes, int3-padded): the cave, the route table, the name format and the row record R
    (its format pointer, every cell 0xFF until the game registers a model)."""
    from .nfl2k5_draft_ai import _Asm
    row, fmt = row_va(code_va), format_va(code_va)
    a = _Asm(code_va)
    a.b("8b442418")                                  # mov eax, [esp+0x18]       the loop's row pointer
    a.b("3d" + _p32(LOOP_EXIT))                      # cmp eax, 0xA86E48         the retail rows are done
    a.j8("75", "done")                               # jne done                  (back from R: R + 0x10)
    a.b("813d" + _p32(row) + _p32(fmt))              # cmp dword [R], fmt
    a.j8("74", "ready")
    a.b("c705" + _p32(row) + _p32(fmt))              # mov dword [R], fmt        first run: the name format ...
    a.b("830d" + _p32(row + 4) + "ff")               # or dword [R+4], -1        ... and every cell unbound (0xFF)
    a.b("830d" + _p32(row + 8) + "ff")               # or dword [R+8], -1
    a.b("830d" + _p32(row + 12) + "ff")              # or dword [R+12], -1
    a.label("ready")
    a.b("c7442418" + _p32(row))                      # mov dword [esp+0x18], R   the row record
    a.b("8b442420")                                  # mov eax, [esp+0x20]       model row
    a.b("8d8440" + _p32(row + 4))                    # lea eax, [eax+eax*2+R+4]
    a.b("89442410")                                  # mov [esp+0x10], eax       its cells
    a.jmp_abs(LOOP_BODY)                             # the retail body names, searches and stores L, M, R
    a.label("done")
    a.b("8b442430")                                  # mov eax, [esp+0x30]       rows 0..13 cell base (retail)
    a.b("8d88" + _p32(ROW13_CELL_END))               # lea ecx, [eax+0xD3]
    a.b("05" + _p32(ROWS_SPAN))                      # add eax, 0xE0
    a.b("894c2414")                                  # mov [esp+0x14], ecx
    a.b("89442410")                                  # mov [esp+0x10], eax
    a.b("8bd0")                                      # mov edx, eax
    a.b("b8" + _p32(LOOP_EXIT))                      # mov eax, 0xA86E48
    a.b("89442418")                                  # mov [esp+0x18], eax       (the retail exit state)
    a.b("68" + _p32(TAIL_PUSH))                      # push 0xE65610             (the displaced instruction)
    a.jmp_abs(RESUME_VA)
    code = bytearray(a.assemble())
    _require(len(code) <= TABLE_OFFSET, "the helmet side numbers cave outgrew its code budget")
    code += b"\xcc" * (TABLE_OFFSET - len(code))
    code += struct.pack("<6I", *RETAIL_ROUTE_ROWS, row_index(row))
    _require(len(code) == FORMAT_OFFSET, "route table misplaced")
    code += (ROW_FORMAT + "\0").encode("utf-16le")
    _require(len(code) <= ROW_OFFSET, "the helmet side numbers name outgrew its slot")
    code += b"\xcc" * (ROW_OFFSET - len(code))
    code += struct.pack("<I", fmt) + b"\xff" * 12                # R: the format, then 4 model rows x L, M, R unbound
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    jump = b"\xe9" + struct.pack("<i", code_va - RESUME_VA)
    return [("route_table", ROUTE_SITE, ROUTE_RETAIL, ROUTE_RETAIL[:3] + struct.pack("<I", table_va(code_va))),
            ("registration_tail", HOOK_VA, HOOK_RETAIL, jump)]


# ------------------------------------------------------------------------------------------------ owner state

def _space():
    from . import nfl2k5_xbe_space as space
    return space


def allocation(payload: bytes) -> dict | None:
    """{"code": row} of the owner's fixed page, or None."""
    space = _space()
    if space.status(payload) != "applied":
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and rows[0]["kind"] == "code" and rows[0]["size"] == CODE_SIZE
             and rows[0]["va"] == space.HELMET_SIDES_VA, "foreign helmet side numbers allocation")
    row_va(rows[0]["va"])
    return {"code": rows[0]}


def _guards(payload: bytes, hooked: bool) -> None:
    from . import nfl2k5_number_kerning as kerning
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        if hooked:
            for _label, site, before, _after in sites(PLACEHOLDER_VA):
                if va <= site and site + len(before) <= va + size:
                    blob[site - va:site - va + len(before)] = before
        _require(_sha(bytes(blob)) == digest, f"foreign helmet side numbers prerequisite at {va:#x}")
    _require(kerning.status(payload) in ("retail", "applied"), "foreign number selector or binder")


def _state(payload: bytes) -> tuple[str, dict | None]:
    from . import nfl2k5_rdata_sites as rdata
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    found = allocation(payload)
    if found is None:
        _require(rdata.status(payload, sites(PLACEHOLDER_VA)) == "retail",
                 "the helmet number sites changed without an allocation")
        _guards(payload, False)
        return "retail", None
    image = XbeImage(payload)
    code_va = found["code"]["va"]
    section = image.section(row_va(code_va), ROW_SIZE)
    _require(section is not None and section.flags & 1, "the helmet side numbers row is not in a writable section")
    code = image.read(code_va, CODE_SIZE)
    if code == b"\xcc" * CODE_SIZE:
        _require(rdata.status(payload, sites(code_va)) == "retail",
                 "the helmet number sites changed with an empty owner")
        _guards(payload, False)
        return "retail", found
    _require(code == code_for(code_va), "foreign helmet side numbers code")
    _require(rdata.status(payload, sites(code_va)) == "applied", "mixed helmet side numbers sites")
    _guards(payload, True)
    return "applied", found


def status(payload: bytes) -> str:
    """retail / applied / foreign for default.xbe."""
    try:
        return _state(payload)[0]
    except _FAILURES:
        return "foreign"


def read_settings(payload: bytes) -> dict:
    try:
        state, found = _state(payload)
    except _FAILURES:
        return {"status": "foreign", "route": ROUTE}
    if state != "applied":
        return {"status": state, "route": ROUTE}
    code_va = found["code"]["va"]
    row = row_va(code_va)
    return {"status": state, "route": ROUTE, "row": row_index(row), "row_va": hex(row), "code_va": hex(code_va),
            "table_va": hex(table_va(code_va)), "format_va": hex(format_va(code_va))}


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in _space().reservations(payload) if r["owner"] == OWNER]
    found = allocation(payload)
    edits = sites(found["code"]["va"] if found else PLACEHOLDER_VA)
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in edits]


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the owner (a late allocator owner, after every other) and its two sites. Idempotent."""
    from . import nfl2k5_rdata_sites as rdata
    space = _space()
    state, found = _state(payload)
    common = {"owner": OWNER, "label": LABEL, "experimental": True, "runtime_witnessed": False, "route": ROUTE,
              "row_format": ROW_FORMAT}
    if state == "applied":
        return payload, {**common, "status": "applied", "already_applied": True, "changed_bytes": 0, "edits": []}
    before = payload
    if found is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        found = allocation(payload)
    _require(found is not None, "reserve the helmet side numbers allocation first")
    code_va = found["code"]["va"]
    row = row_va(code_va)
    with_code, code_receipt = space.install_code(payload, OWNER, code_for(code_va))
    result, site_receipt = rdata.apply(with_code, sites(code_va), OWNER)
    _require(status(result) == "applied", "helmet side numbers postcondition failed")
    return result, {**common, **site_receipt, "status": "applied", "already_applied": False,
                    "code_install": code_receipt, "code_va": hex(code_va), "code_end": hex(code_va + CODE_SIZE),
                    "row_va": hex(row), "row": row_index(row),
                    "table_va": hex(table_va(code_va)), "format_va": hex(format_va(code_va)),
                    "hook_va": hex(HOOK_VA), "route_site_va": hex(ROUTE_SITE),
                    "changed_bytes": space.count_differing_bytes(before, result) + abs(len(result) - len(before)),
                    "before_sha256": _sha(before), "after_sha256": _sha(result)}


def remove(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """The sites back to their retail bytes and the code back to its int3 fill (the reservation stays; nothing
    moves). The exact inverse of filling an already reserved allocation."""
    from . import nfl2k5_rdata_sites as rdata
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    state, found = _state(payload)
    if state == "retail":
        return payload, {"owner": OWNER, "status": "retail", "already_retail": True, "changed_bytes": 0}
    before = payload
    code_va = found["code"]["va"]
    installed = XbeImage(payload).read(code_va, CODE_SIZE)
    back = [(label, va, after, retail) for label, va, retail, after in sites(code_va)]
    payload, _ = rdata.apply(payload, back, OWNER + " removal")
    payload, _ = space.install_code(payload, OWNER, b"\xcc" * CODE_SIZE, previous=installed)
    _require(status(payload) == "retail", "the helmet side numbers did not come off cleanly")
    return payload, {"owner": OWNER, "status": "retail", "already_retail": False,
                     "changed_bytes": space.count_differing_bytes(before, payload)}


__all__ = ["OWNER", "LABEL", "BUILD_KEY", "BUILD_CAPTION", "HELP_TEXT", "ROUTE", "ROW_FORMAT", "CODE_SIZE",
           "REQUESTS", "GUARDS", "HelmetSideNumbersError", "row_va", "row_index", "table_va",
           "format_va", "code_for", "sites", "allocation", "status", "read_settings", "reservations", "apply",
           "remove"]


# ------------------------------------------------------------------------------------------------ kits and disc image
# b81 helmet-sides (lane lead): the Chargers' 2026 home and road kits take route 5. The SOFTDRINK build (and retail)
# gives them route 2 (set B, large at the back); only these two kits change, only the Unif route word changes, and only
# this step writes route 5, so a disc never carries route 5 without the owner above.
KITS = ("24H0", "24A0")
ROUTE_BEFORE = 2
UNIF_CHUNK_HEADER = 0x20
UNIF_ROUTE_OFFSET = 0x3C        # Unif chunk body +0x3C = payload +0x0C, read by the accessor 0x8E830
def _kit_unif(image, index, entry):
    """(segments of the route word, the route) of one kit package, after checking its raw Unif chunk."""
    head = image.read_segments(index.sub_extents(entry, 0, UNIF_CHUNK_HEADER + 0x50))
    kind, stored = head[:4], struct.unpack_from("<I", head, 4)[0]
    _require(kind == b"Unif" and stored == 80, "the kit's first chunk is not the raw 80-byte Unif")
    at = UNIF_CHUNK_HEADER + UNIF_ROUTE_OFFSET
    return index.sub_extents(entry, at, 4), struct.unpack_from("<I", head, at)[0]


def kit_routes(path) -> dict[str, int]:
    """The helmet-number route of each Chargers kit on a disc image."""
    from . import nfl2k5_bump_texture_writer as bump
    out = {}
    with bump._Image.open(Path(path), writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        for selector in KITS:
            entries = by_name.get(selector + ".IFF", [])
            _require(len(entries) == 1, f"{selector}: kit package absent or duplicated")
            out[selector] = _kit_unif(image, index, entries[0])[1]
    return out


def kit_status(path) -> str:
    try:
        routes = set(kit_routes(path).values())
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"
    return {frozenset({ROUTE_BEFORE}): "retail", frozenset({ROUTE}): "applied"}.get(frozenset(routes), "foreign")


def _write_kits(path, value: int, expect: int) -> list[dict]:
    from . import nfl2k5_bump_texture_writer as bump
    rows = []
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        plans = []
        for selector in KITS:                       # preflight both kits before the first write
            entries = by_name.get(selector + ".IFF", [])
            _require(len(entries) == 1, f"{selector}: kit package absent or duplicated")
            segments, route = _kit_unif(image, index, entries[0])
            _require(route in (expect, value), f"{selector}: helmet-number route {route}, expected {expect}")
            plans.append((selector, segments, route))
        for selector, segments, route in plans:
            if route != value:
                image.write_segments(segments, struct.pack("<I", value))
                _require(image.read_segments(segments) == struct.pack("<I", value), f"{selector}: route read-back")
            rows.append({"selector": selector, "before": route, "after": value})
    return rows


def image_status(path) -> str:
    """retail / applied / partial / foreign for the disc: the owner in default.xbe, set E in the player models (the
    hair styles growth) and the Chargers' two kits."""
    from . import nfl2k5_hair_styles as hair
    from . import nfl2k5_music_archive as archive
    try:
        with archive.Disc(Path(path), descriptors=()) as disc:
            x = disc.entries["default.xbe"]
            xbe = status(disc.read(x.size, x.byte_offset))
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"
    kits = kit_status(path)
    if xbe == "retail" and kits == "retail":
        return "retail"
    if xbe == "applied" and kits == "applied":
        return "applied" if hair.resource_status(path) == "applied" else "partial"
    return "partial" if {xbe, kits} <= {"retail", "applied"} else "foreign"


def apply_to_image(path, read_xbe, write_xbe) -> dict:
    """Build step: the owner (the last late allocator owner), then the two kits. Needs the hair styles growth with set
    E on the same image (otherwise route 5 would bind nothing)."""
    from . import nfl2k5_hair_styles as hair
    _require(hair.resource_status(path) == "applied", "helmet side numbers need the player models with set E "
                                                    "(Hair styles)")
    before = read_xbe(path)
    patched, xbe_receipt = apply(before)
    if patched != before:
        write_xbe(path, patched)
    _require(read_xbe(path) == patched and status(patched) == "applied", "the route-5 owner does not read back")
    kits = _write_kits(path, ROUTE, ROUTE_BEFORE)
    _require(kit_status(path) == "applied", "the Chargers' kits do not read back on route 5")
    return {"label": BUILD_CAPTION, "evidence": LABEL, "runtime_witnessed": False,
            "xbe": {k: v for k, v in xbe_receipt.items() if k not in ("edits", "code_install")}, "kits": kits}


__all__ += ["KITS", "ROUTE_BEFORE", "kit_routes", "kit_status", "image_status", "apply_to_image"]
