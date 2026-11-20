"""Relocatable page of the quarterback room owner (beta 81 piece 3, owner nfl2k5_qb_room).

Three pages: code and read-only tables at 0x0000..0x1FFF (0xCC after the last byte of code), the settings record at
0x2000, link words at 0x2020, counters at 0x2040, the event ring at 0x2400 and its cursor at 0x2E00. The file holds
zeros in the counters, ring and cursor; they change only in RAM. Two whole 5-byte calls of the weekly advance enter
the page (and a third for signings once stage 4a is built). The byte interface is fixed by
.b77-scratch/b81/qb34/INTERFACE.md; the rules are DESIGN.md section 2. The template, relocations, labels and counter
names are generated from tools/qb_room by build.py.
"""
from __future__ import annotations

import struct
from typing import Iterator

PAGE_SIZE = 0x3000
CODE_LIMIT = 0x2000
SETTINGS_OFFSET = 0x2000
SETTINGS = struct.Struct("<8sIIIIII")
MAGIC = b"QBROOMv1"
MODE_REALISTIC = 1
LINK_IR_STORE = 0x2020
COUNTERS_OFFSET = 0x2040
RING_OFFSET = 0x2400
RING_COUNT = 128
# year, week, club, decision (low 4 bits: 1 D1, 2 D2, 3 D3, 4 D4, 5 E1, 6 E2; 0x10 S hot, 0x20 stage 7,
# 0x40 b ends ahead of a), result (0 kept, 1 applied, 2 would fire in shadow, 3 lock only, no draw), a, b,
# d (L - W), g, rating10 of row 0, gap ovr(b) - ovr(a), coach1000 / 10, threshold p100k.
RING_EVENT = struct.Struct("<HBBBBHHbBHbBI")
RING_CURSOR = 0x2E00

STAGE_D1, STAGE_D2D3, STAGE_D4, STAGE_SIGN, STAGE_TRADE = 1, 2, 4, 8, 16
STAGE_MASK = 31
FLAG_SHADOW = 1
H0_PPM = 15000                       # D3 base 0.015 in millionths until shadow panel P0 fixes it (DESIGN 6.3).
D2_SCALE_MILLI = 1000                # D2 table scale in thousandths (1000 = the table as written).
LIMIT_PPM = 1_000_000                # Both are clamped to this in the page (a probability is at most 1).

DECISION_D1, DECISION_D2, DECISION_D3, DECISION_D4 = 1, 2, 3, 4
RESULT_KEPT, RESULT_APPLIED, RESULT_SHADOW, RESULT_LOCK_ONLY = 0, 1, 2, 3

# (site, retail bytes, entry label, stage bit the site needs; 0 = always). Whole 5-byte calls.
HOOKS = (
    (0x247DCA, bytes.fromhex("e851620700"), "opening_entry", 0),
    (0x24807A, bytes.fromhex("e8016b0300"), "room_entry", 0),
    (0x248010, bytes.fromhex("e85bb80d00"), "sign_entry", STAGE_SIGN),
)


def _whole(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"The quarterback room {name} must be a whole number from {low} to {high}")
    return value


def settings_record(stages: int, *, shadow: bool = False, h0_ppm: int = H0_PPM,
                    d2_scale_milli: int = D2_SCALE_MILLI) -> bytes:
    """The 32-byte settings record: magic, mode 1 (realistic), stage bits, flags, H0 and the D2 scale."""
    _whole(stages, 0, STAGE_MASK, "stage set")
    if type(shadow) is not bool:
        raise ValueError("The quarterback room shadow flag must be True or False")
    _whole(h0_ppm, 0, LIMIT_PPM, "H0 (millionths)")
    _whole(d2_scale_milli, 0, LIMIT_PPM, "D2 scale (thousandths)")
    return SETTINGS.pack(MAGIC, MODE_REALISTIC, stages, FLAG_SHADOW if shadow else 0, h0_ppm, d2_scale_milli, 0)


def parse_settings(record: bytes) -> dict:
    """Decode a settings record; refuses anything that settings_record could not have written."""
    if not isinstance(record, (bytes, bytearray)) or len(record) != SETTINGS.size:
        raise ValueError("A quarterback room settings record is 32 bytes")
    magic, mode, stages, flags, h0, scale, reserved = SETTINGS.unpack(record)
    if magic != MAGIC or mode != MODE_REALISTIC or stages & ~STAGE_MASK or flags & ~FLAG_SHADOW or reserved \
            or h0 > LIMIT_PPM or scale > LIMIT_PPM:
        raise ValueError("Unrecognized quarterback room settings record")
    return {"mode": mode, "stages": stages, "shadow": bool(flags & FLAG_SHADOW), "h0_ppm": h0,
            "d2_scale_milli": scale}


def _set32(page, offset, value):
    struct.pack_into("<I", page, offset, value & 0xFFFFFFFF)


def page_bytes(va: int, settings: bytes, *, ir_store_va: int = 0) -> bytes:
    """The whole 0x3000-byte page linked for `va`, with the settings record and link words in place."""
    _whole(va, 0x1000, 0xFFFFFFFF - PAGE_SIZE + 1, "page address")
    if va % 0x1000:
        raise ValueError("The quarterback room page must start on a page boundary")
    parse_settings(settings)
    _whole(ir_store_va, 0, 0xFFFFFFFF, "IR store address")
    page = bytearray(_TEMPLATE)
    for offset, relative, family, addend in _RELOCATIONS:
        target = (va if family == "page" else 0) + addend
        _set32(page, offset, target - (va + offset) if relative else target)
    page[SETTINGS_OFFSET:SETTINGS_OFFSET + SETTINGS.size] = settings
    _set32(page, LINK_IR_STORE, ir_store_va)
    return bytes(page)


def _call(at: int, destination: int) -> bytes:
    return b"\xe8" + struct.pack("<I", (destination - at - 5) & 0xFFFFFFFF)


def sites(va: int, stages: int) -> Iterator[tuple[str, int, bytes, bytes]]:
    """(entry label, site, retail call, installed call) for every site the stage set needs."""
    _whole(stages, 0, STAGE_MASK, "stage set")
    for at, original, label, need in HOOKS:
        if need and not stages & need:
            continue
        if label not in LABELS:
            raise ValueError(f"The quarterback room template has no {label} (stage {need} is not built)")
        yield label, at, original, _call(at, va + LABELS[label])


def counters(page: bytes) -> dict:
    """Counter values from a page image (RAM or file)."""
    return {name: struct.unpack_from("<I", page, offset)[0] for name, offset in COUNTERS.items()}


def events(page: bytes) -> list[tuple]:
    """Ring events in the order written (at most the last RING_COUNT)."""
    total = struct.unpack_from("<I", page, RING_CURSOR)[0]
    first = max(0, total - RING_COUNT)
    return [RING_EVENT.unpack_from(page, RING_OFFSET + RING_EVENT.size * (n % RING_COUNT)) for n in range(first, total)]


# Generated from tools/qb_room by build.py.
CODE_BYTES = 0x36

_TEMPLATE = b''.join((
    bytes.fromhex('9c60fce8fcffffff619de91ce02b009c60fce8fcffffff619de97ceb2700a10000000040a3000000'),
    bytes.fromhex('00c3a10400000040a304000000c3'),
    b'\xcc' * 8138,
    bytes(4096),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0004, True, 'page', 0x1a),
    (0x000b, True, 'stock', 0x2be01c),
    (0x0013, True, 'page', 0x26),
    (0x001a, True, 'stock', 0x27eb7c),
    (0x001f, False, 'page', 0x2040),
    (0x0025, False, 'page', 0x2040),
    (0x002b, False, 'page', 0x2044),
    (0x0031, False, 'page', 0x2044),
)

LABELS = {
    'opening_entry': 0x0,
    'opening_pass': 0x1e,
    'room_entry': 0xf,
    'room_pass': 0x2a,
}

# Counter name -> page offset, in the order of struct counters in tools/qb_room/room.c.
COUNTERS = {
    'opening_passes': 0x2040,
    'room_passes': 0x2044,
}
