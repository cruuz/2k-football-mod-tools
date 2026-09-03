"""Move the NFL 2K5 kick meter up and/or switch off the pre-snap lineup insert (executable patch, xemu-only).

Both elements collide with the bottom-centre ESPN bar (root at screen (320, 424)).  Retail
``default.xbe`` facts (VAs, image base 0x10000):

Kick meter.  The kick HUD init ``FUN_000ba940`` loads the ``KickArrow`` (outer 346 chunk 75),
``KickMeter`` (chunk 76, one node ``a_kick_meter`` whose mesh is centred on its origin, 124 x 127
units) and ``windmeter`` (chunk 77) scenes.  At 0xBAAD5..0xBABDD it builds a matrix (identity with
y and z flipped), sets its translation to::

    x = 0 + [0x4E6C48]                 (80.0)          0xBAB60  fadd dword [0x4E6C48]
    y = (rect[1] - rect[5]) - [0x4E6C48]  (bottom edge - 80)  0xBAB52  fsub dword [0x4E6C48]
    z = 1 + 100

(rect = the HUD viewport from ``FUN_00066930``) and copies it into the first node matrix of the
KickMeter scene (``FUN_00021960`` = node + 0x20, ``FUN_000ba150`` = 0x40-byte copy), then the same
matrix with z - 14 into the windmeter, and derives the wind text anchor from it
(``DAT_00b727e0`` = x - 39, ``DAT_00b727e4`` = y - 60).  The draw ``FUN_000bb2c0`` never places
the meter again: the gauge sits 80 units above the bottom edge (centre about y 400 of 480, spanning
about y 338..462), so it covers a bar at y 400..440.  The 80.0 constant is shared (24 references),
so the patch repoints the one ``fsub`` operand at another retail float that already holds the wanted
margin (150.0 lives at 0x4E88E4): the gauge then spans about y 268..392, clear of the bar.  The wind
meter and wind text move with it.  The x operand (0xBAB60) is left at 80.

Lineup insert.  The "OFFENSE / DEFENSE" starters strip is the ``start_line_p_ticker`` scene plus a
text object (init ``FUN_000ffe90``, rows filled by ``FUN_000ffba0``).  Its per-frame controller
``FUN_000ffe00`` shows it while the gate ``FUN_000ffa80`` (0xFFA80) returns 1 (pre-snap phases
0xC/0xD, no replay, ball not yet kicked) and hides it (``FUN_000ffda0``) when the gate returns 0.
Making the gate ``xor eax,eax; ret`` removes the insert entirely (3 bytes; the rest of the
function stays as dead retail bytes).

Retail bytes are verified before writing and the .text digest is repinned.  Not verified in game.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

IMAGE_BASE = 0x10000

KICK_MARGIN_SITE_VA = 0x000BAB52          # fsub dword ptr [imm32] inside FUN_000ba940
KICK_X_SITE_VA = 0x000BAB60               # fadd dword ptr [imm32] (x offset, left at retail)
KICK_RETAIL_OPERAND_VA = 0x004E6C48       # 80.0 (shared constant)
KICK_RETAIL_MARGIN = 80.0
# retail floats that can serve as the y margin without a code cave: margin -> .rdata VA
KICK_MARGIN_CONSTANTS: dict[float, int] = {
    80.0: 0x004E6C48, 120.0: 0x004E6D58, 130.0: 0x004E88FC, 140.0: 0x00509BB8,
    150.0: 0x004E88E4, 160.0: 0x004F0F24, 180.0: 0x004E88C8, 200.0: 0x004E6C6C,
}
DEFAULT_KICK_MARGIN = 150.0
FSUB_M32 = bytes.fromhex("d825")

LINEUP_GATE_VA = 0x000FFA80
LINEUP_RETAIL_HEAD = bytes.fromhex("558bec83e4f083ec10a150fce50085c0")
LINEUP_OFF_HEAD = bytes.fromhex("33c0c3") + LINEUP_RETAIL_HEAD[3:]   # xor eax,eax ; ret


class HudLayoutError(ValueError):
    """The HUD layout patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HudLayoutError(message)


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise HudLayoutError(f"VA 0x{va:x} is in no file-backed section")


def _float_at(payload: bytes, va: int) -> float:
    off = _offset(payload, va)
    return struct.unpack_from("<f", payload, off)[0]


def kick_margin_operand(margin: float) -> bytes:
    _require(margin in KICK_MARGIN_CONSTANTS, f"no retail constant holds a {margin} margin; choose one of {sorted(KICK_MARGIN_CONSTANTS)}")
    return FSUB_M32 + struct.pack("<I", KICK_MARGIN_CONSTANTS[margin])


def kick_margin_status(payload: bytes) -> str:
    """'retail', the applied margin as a string (e.g. '150.0'), or 'foreign'."""

    try:
        off = _offset(payload, KICK_MARGIN_SITE_VA)
        got = payload[off: off + 6]
        if got[:2] != FSUB_M32:
            return "foreign"
        operand = struct.unpack_from("<I", got, 2)[0]
        for margin, va in KICK_MARGIN_CONSTANTS.items():
            if operand == va and _float_at(payload, va) == margin:
                return "retail" if margin == KICK_RETAIL_MARGIN else str(margin)
    except (HudLayoutError, ValueError, struct.error):
        pass
    return "foreign"


def lineup_status(payload: bytes) -> str:
    try:
        off = _offset(payload, LINEUP_GATE_VA)
    except (HudLayoutError, ValueError, struct.error):
        return "foreign"
    got = payload[off: off + len(LINEUP_RETAIL_HEAD)]
    if got == LINEUP_RETAIL_HEAD:
        return "retail"
    if got == LINEUP_OFF_HEAD:
        return "off"
    return "foreign"


def status(payload: bytes) -> dict[str, str]:
    return {"kick_meter_margin": kick_margin_status(payload), "lineup_insert": lineup_status(payload)}


def apply(payload: bytes, *, kick_margin: float | None = DEFAULT_KICK_MARGIN,
          lineup_insert_off: bool = False) -> tuple[bytes, Mapping[str, object]]:
    """Copy of ``payload`` with the requested HUD changes (each site must still be retail)."""

    _require(kick_margin is not None or lineup_insert_off, "nothing to apply")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    if kick_margin is not None:
        _require(kick_margin_status(payload) == "retail", f"kick meter site is {kick_margin_status(payload)}, not retail")
        target_va = KICK_MARGIN_CONSTANTS.get(kick_margin)
        _require(target_va is not None, f"no retail constant holds a {kick_margin} margin")
        _require(_float_at(payload, target_va) == kick_margin, f"float at 0x{target_va:x} is not {kick_margin}")
        off = _offset(payload, KICK_MARGIN_SITE_VA)
        after = kick_margin_operand(kick_margin)
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": "kick_meter_margin", "va": f"0x{KICK_MARGIN_SITE_VA:x}", "file_offset": f"0x{off:x}",
                      "before": (FSUB_M32 + struct.pack("<I", KICK_RETAIL_OPERAND_VA)).hex(), "after": after.hex(),
                      "margin": kick_margin})
    if lineup_insert_off:
        _require(lineup_status(payload) == "retail", f"lineup gate is {lineup_status(payload)}, not retail")
        off = _offset(payload, LINEUP_GATE_VA)
        buf[off: off + len(LINEUP_OFF_HEAD)] = LINEUP_OFF_HEAD
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": "lineup_insert_off", "va": f"0x{LINEUP_GATE_VA:x}", "file_offset": f"0x{off:x}",
                      "before": LINEUP_RETAIL_HEAD[:3].hex(), "after": LINEUP_OFF_HEAD[:3].hex()})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    after_state = status(patched)
    if kick_margin is not None:
        _require(after_state["kick_meter_margin"] == ("retail" if kick_margin == KICK_RETAIL_MARGIN else str(kick_margin)), "kick meter post-apply verification failed")
    if lineup_insert_off:
        _require(after_state["lineup_insert"] == "off", "lineup post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched), "status": after_state}


__all__ = ["DEFAULT_KICK_MARGIN", "HudLayoutError", "KICK_MARGIN_CONSTANTS", "KICK_MARGIN_SITE_VA", "KICK_X_SITE_VA",
           "LINEUP_GATE_VA", "LINEUP_OFF_HEAD", "LINEUP_RETAIL_HEAD", "apply", "kick_margin_operand",
           "kick_margin_status", "lineup_status", "status"]
