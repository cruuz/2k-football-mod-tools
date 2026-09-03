"""Make the NFL 2K5 Catching slider actually decide drops (executable patch, xemu-only).

Retail: the nine Human/CPU sliders are copied into a per-side factor table
(`0xAAB8C0`, filled by ``FUN_0017b8a0`` from the menu globals through the getter tables
0xAAB820 (CPU) / 0xAAB848 (Human); accessor ``FUN_0017b8f0(idx, side)``) and the Catching
entry (index 4: ``[0xE60118]`` CPU, ``[0xE600F4]`` Human) has no direct consumer.  It only
reaches play through the attribute accessor's relative nudge, which is capped at a few
rating points, so 100 % catching still drops passes.

The difficulty presets pre-bias the sliders (``FUN_000e3740``: Rookie Human 1.00 / CPU 0.00,
Pro 0.75 / 0.25, All-Pro 0.50 / 0.50, Legend 0.25 / 0.75; a fresh profile starts on Pro,
``FUN_000e3b90``), so "default" is 0.75 for the human side and 0.25 for the CPU side.

The catch decision (``FUN_001c78d0``) computes a catch probability and, at
``0x001C8317`` (``mov ecx, 0xE5FCA0; call FUN_00048B90``), draws a random
number; the pass is caught when ``rand < probability``.  The same roll decides
interceptions: a defender reaching the ball is just another catcher.  This patch
redirects that one call into a 48-byte code cave placed inside the XBE header's
boot-logo bitmap (``0x00010A10``; the kernel reads it once at boot, the game never
does; the thunk tables in .text looked dead statically but ARE called at runtime):

    offense catcher:  rand -> min(rand, rand / (2 * Catching slider of the catcher's side))
    defense catcher:  rand -> rand / (2 * Interception slider)

"Side" is decided the way the game's own attribute accessor does it: the team is
human when its controller record ``[team+0x30]`` is non-zero (``0xE60280`` is the
team with possession, not the human team; the two possession globals swap on every
turnover and kick).  For the offense the slider can only ADD catches: 50 and below is
byte-for-byte the retail odds (so the Pro / Legend / Rookie presets never make a side
worse than retail, and the Rookie CPU value of 0 no longer divides by zero), 75 is
x1.5 catch odds, 100 doubles them, 200 quadruples them.  Interception keeps its full
range: 0 makes picks impossible, 50 is retail, 100 doubles them (the game's own
slider branch keeps a 10 % floor and scales with difficulty, which is why the forums
call it broken).  The Human and CPU Catching menu ceilings (``0x0014AC20`` /
``0x0014B490``) are repointed from the shared 1.0 constant to the shared 2.0 constant
so the slider can show 200.

Everything is pattern-checked: every patched byte must hold its exact retail
value (or the exact already-patched value, which reports as applied), the
``.text`` section digest is recomputed, and the change set is about 70 bytes.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

CAVE_VA = 0x00010A10   # inside the XBE boot-logo bitmap (0x10A10..0x10CC2): kernel-only at boot, never read by the game
CAVE_SIZE = 48         # the slot ends at 0x10A40 (the scorebug X/Y floats live there)
HOOK_VA = 0x001C8317
RAND_FN = 0x00048B90
FACTOR_FN = 0x0017B8F0          # ReadFactor(idx=ecx, side=edx != 0); side 1 = Human table, 0 = CPU
OFFENSE_TEAM_GLOBAL = 0x00E60280   # team with possession (swapped with 0xE60284 on turnovers/kicks)
INT_SLIDER_GLOBAL = 0x00E6020C     # the menu's "Interception" slider, 0.0..1.0
CONST_ONE = 0x004E419C
CONST_TWO = 0x004E6084
CEIL_SITES = (0x0014AC20, 0x0014B490)   # Human / CPU Catching "maximum" callbacks
CATCHING_FACTOR_INDEX = 4
# Difficulty presets (FUN_000e3740 jump table 0xE3B00): Human, CPU slider value for every slider.
DIFFICULTY_PRESETS = {"Rookie": (1.0, 0.0), "Pro": (0.75, 0.25), "All-Pro": (0.5, 0.5), "Legend": (0.25, 0.75)}
FRESH_PROFILE_DIFFICULTY = "Pro"   # FUN_000e3b90 stores 1 into DAT_00e5ff84 before FUN_000e3740

RETAIL_HOOK = b"\xe8" + struct.pack("<i", RAND_FN - (HOOK_VA + 5))
RETAIL_CEIL = b"\xd9\x05" + struct.pack("<I", CONST_ONE)
PATCHED_CEIL = b"\xd9\x05" + struct.pack("<I", CONST_TWO)
# Retail bytes of the boot-logo bitmap where the cave lands (48 bytes at 0x10A10).
RETAIL_CAVE = bytes.fromhex(
    "0733ad030753ad03a903ea000373a7033200b3fd030503fdd343f9ea0003e3f93347"
    "332200ff030573fd7373a773ea00"
)


class CatchSliderError(ValueError):
    """The catch-slider patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CatchSliderError(message)


def _rel32(src: int, dst: int) -> bytes:
    return struct.pack("<i", dst - (src + 5))


def cave_bytes() -> bytes:
    """rand -> min(rand, rand / (2 * Catching)) for an offense catcher, rand / (2 * Interception)
    for a defender.  Side is decided exactly like the game's own attribute accessor
    (``FUN_0017b010``): a team is "human" when ``[team+0x30]`` (its controller record) is
    non-zero; ``[0xE60280]`` is the team with possession.  ``ReadFactor`` treats any non-zero
    edx as the human side, so the controller pointer itself is passed as the side."""

    code = b""
    code += b"\xe8" + _rel32(CAVE_VA + len(code), RAND_FN)       # call rand              st0 = rand
    code += b"\xa1" + struct.pack("<I", OFFENSE_TEAM_GLOBAL)     # mov eax,[offense team]
    code += b"\x3b\x43\x38"                                     # cmp eax,[ebx+0x38]     catcher's team?
    code += b"\x75\x16"                                         # jne defender (+22)
    code += b"\x8b\x50\x30"                                     # mov edx,[eax+0x30]     controller record (0 = CPU)
    code += b"\x6a\x04"                                         # push 4                 Catching
    code += b"\x59"                                             # pop ecx
    code += b"\xe8" + _rel32(CAVE_VA + len(code), FACTOR_FN)     # call ReadFactor        st0 = slider, st1 = rand
    code += b"\xd8\xc0"                                         # fadd st0,st0           2*slider
    code += b"\xd8\xf9"                                         # fdivr st0,st1          st0 = rand/(2*slider), st1 = rand
    code += b"\xdb\xe9"                                         # fucomi st0,st1         CF = st0 < st1
    code += b"\xdb\xc1"                                         # fcmovnb st0,st1        st0 = min(rand/(2s), rand)
    code += b"\xdd\xd9"                                         # fstp st1               pop the spare rand
    code += b"\xc3"                                             # ret
    code += b"\xd9\x05" + struct.pack("<I", INT_SLIDER_GLOBAL)  # defender: fld [Interception slider]
    code += b"\xd8\xc0"                                         # fadd st0,st0           2*slider
    code += b"\xde\xf9"                                         # fdivp st1,st0          rand/(2*slider)
    code += b"\xc3"                                             # ret
    assert len(code) == CAVE_SIZE, len(code)
    return code


PATCHED_HOOK = b"\xe8" + _rel32(HOOK_VA, CAVE_VA)


IMAGE_BASE = 0x10000


def odds_multiplier(slider: float, defender: bool = False) -> float:
    """Catch-odds multiplier the cave applies for a slider value (0.0 .. 2.0)."""

    if defender:
        return 2.0 * slider
    return max(1.0, 2.0 * slider)


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    """File offset for a VA: the loaded XBE header maps 1:1 from the image base;
    everything else comes from the section table."""

    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise CatchSliderError(f"VA 0x{va:x} is in no section")


def _section_index_for(payload: bytes, off: int) -> int | None:
    if off < _header_size(payload):
        return None  # XBE header: not a section, no digest to recompute
    return _section_for_offset(_sections(payload), off).index


def _sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    cave = cave_bytes()
    return [
        ("cave", _offset(payload, CAVE_VA), RETAIL_CAVE[: len(cave)], cave),
        ("hook", _offset(payload, HOOK_VA), RETAIL_HOOK, PATCHED_HOOK),
        ("ceiling_human", _offset(payload, CEIL_SITES[0]), RETAIL_CEIL, PATCHED_CEIL),
        ("ceiling_cpu", _offset(payload, CEIL_SITES[1]), RETAIL_CEIL, PATCHED_CEIL),
    ]


def status(payload: bytes) -> str:
    """'retail', 'applied', or 'foreign' (bytes match neither; refuse to touch)."""

    states = set()
    try:
        sites = _sites(payload)
    except (CatchSliderError, ValueError):
        return "foreign"
    for _label, off, before, after in sites:
        got = payload[off: off + len(before)]
        states.add("retail" if got == before else "applied" if got == after else "foreign")
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; refuses anything but retail sites."""

    state = status(payload)
    _require(state == "retail", f"catch-slider sites are {state}, not retail")
    buf = bytearray(payload)
    edits = []
    touched = set()
    sections = _sections(payload)
    for label, off, before, after in _sites(payload):
        buf[off: off + len(after)] = after
        index = _section_index_for(payload, off)
        if index is not None:
            touched.add(index)
        edits.append({"label": label, "file_offset": f"0x{off:x}", "before": before.hex(), "after": after.hex()})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched)}


__all__ = ["CatchSliderError", "CAVE_SIZE", "CAVE_VA", "DIFFICULTY_PRESETS", "FRESH_PROFILE_DIFFICULTY", "HOOK_VA",
           "CEIL_SITES", "apply", "cave_bytes", "odds_multiplier", "status"]
