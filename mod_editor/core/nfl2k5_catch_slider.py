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

The catch decision (``FUN_001c78d0``) computes a catch probability P (stack slot
``[esp+0x14]``) and, at ``0x001C8317`` (``mov ecx, 0xE5FCA0; call FUN_00048B90``), draws a
random number; the pass is caught when ``rand < P`` and no veto (``[esp+0x30]``) is set.  The
same roll decides interceptions: a defender reaching the ball is just another catcher.  For
a ball that reaches the hands (contact mask in edi & 0x420000) P is the "hands" curve
(table 0x50AC84) of the catcher's Catching skill (0.1 at skill 0, 0.8 at 0.5, 1.0 at 0.65,
1.5 at 1.0; skill is rating/100 through ``FUN_0017b010``), minus the defender pressure from
``FUN_001c6640`` (at most 0.5), minus 0.4 * (1 - skill) for a diving/one-handed state
(``FUN_001e6250``), minus 0.25 * (1 - skill) * min(failed attempts on this ball, 2)
(``[0xE3C020]``); a defender at the ball sets 0.1.  P at or above 1.0 is a sure catch, so
drops come from low skill, tight coverage and second touches.

This patch redirects that one call into a 48-byte code cave placed inside the XBE header's
boot-logo bitmap (``0x00010A10``; the kernel reads it once at boot, the game never
does; the thunk tables in .text looked dead statically but ARE called at runtime):

    offense or kicked-ball catcher: rand -> rand / (K * (Human Catching + CPU Catching))
    other defense catcher:         rand -> rand / (2 * Interception slider)

so a pass is caught when ``rand < P * m`` with ``m = K * (human + cpu)``.  K = ``ODDS_SCALE`` = 1.25 is
the retail float constant at 0x4EF1CC (b780 b5-sim; b779 gp1 used 2.0 at 0x4E6084) and the two Catching
sliders are read straight from the factor table.  Human and CPU receivers get the SAME odds: the multiplier is the sum of both
sliders, never the receiving side's own.  Every difficulty preset sets the pair to values that
sum to 1.0 (Rookie 1.0/0.0, Pro 0.75/0.25, All-Pro 0.5/0.5, Legend 0.25/0.75), so ``m = 1.25``
(a quarter above the retail catch odds) for every preset and every saved profile; moving either slider
moves both teams.  b780 b5-sim: at m = 2 a receiver rated 70 or better never dropped a ball in his hands (only
P < 0.5 drops) and the v0.8 release measured 0.1 to 0.3 drops a team-game against the NFL's 1.2. With m = 1.25 the
real catch routine (Unicorn, the SOFTDRINK target mix weighted by simulated-season targets) drops 2.8 % of hands
rolls with the assumed coverage and 6.0 % with harsh coverage (gp1's lower-rated synthetic mix: 4.2 % and 8.7 %; NFL
5.2 % of catchable targets, nflverse + FTN 2022-25): Catching 90+ about 0.1-0.8 %, 80s 1.0-3.5 %, 70s 2.2-6 %, 60s
4-10 %. Elite hands stay almost sure.  (The previous revision used the receiving side's own slider: the Pro human
got x1.5 and the CPU stayed at retail odds, which is why the CPU dropped many more passes than
the human.)  Interception keeps its full range: 0 makes picks impossible, 50 is retail, 100
doubles them (the game's own slider branch keeps a 10 % floor and scales with difficulty,
which is why the forums call it broken).  The Human and CPU Catching menu ceilings
(``0x0014AC20`` / ``0x0014B490``) are repointed from the shared 1.0 constant to the shared 2.0
constant so the slider can show 200.

The roll repeats while the ball stays in reach (b779 gp1 read 3 to 5 successive rolls by one
defender at the ball, P = 0.1, from the running game), and the failed-attempt counter
``[0xE3C020]`` (the second-touch penalty above) rises between them, so one pass can carry
several rolls and a drop is the compound of them.

The selector uses ball kind [0xE602C0] == 3 (non-forward loose ball, including kicks and
backward passes); forward passes are kind 4. Retail's kick launch FUN_000b73b0 stores 3 at
0xB7410, while FUN_000b6700 stores 4 at 0xB6705.  A kind-3 ball always takes the catching
branch (a returner is on the team WITHOUT possession), and the cave tests that inline.  The
interception branch lives in the 22-byte unused tail of the same boot-logo bitmap
(0x10CAC..0x10CC2, after the EDGE legend; the former kick gate's slot).

Everything is pattern-checked: every patched byte must hold its exact retail
value (or the exact already-patched value, which reports as applied), the
``.text`` section digest is recomputed, and the change set is about 100 bytes.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

CAVE_VA = 0x00010A10   # inside the XBE boot-logo bitmap (0x10A10..0x10CC2): kernel-only at boot, never read by the game
CAVE_SIZE = 48         # the slot ends at 0x10A40 (the scorebug X/Y floats live there)
KICK_GATE_VA = 0x00010CAC  # unused boot-logo tail: EDGE legend ends here; bitmap ends at 0x10CC2
KICK_GATE_SIZE = 22
HOOK_VA = 0x001C8317
RAND_FN = 0x00048B90
FACTOR_FN = 0x0017B8F0          # ReadFactor(idx=ecx, side=edx != 0); side 1 = Human table, 0 = CPU (documentation)
FACTOR_TABLE = 0x00AAB8C0       # nine sliders per side, ten floats apart
OFFENSE_TEAM_GLOBAL = 0x00E60280   # team with possession (swapped with 0xE60284 on turnovers/kicks)
INT_SLIDER_GLOBAL = 0x00E6020C     # the menu's "Interception" slider, 0.0..1.0
BALL_KIND_GLOBAL = 0x00E602C0     # 3 = kicks/backward passes; 4 = forward pass
CONST_ONE = 0x004E419C
CONST_TWO = 0x004E6084
CEIL_SITES = (0x0014AC20, 0x0014B490)   # Human / CPU Catching "maximum" callbacks
CATCHING_FACTOR_INDEX = 4
# Default odds multiplier m = K * (human + cpu) = K at every difficulty preset (the pair always sums to 1.0).
# K is a retail float constant in .rdata, referenced by address.
ODDS_SCALE = 1.25
ODDS_SCALE_VA = {1.25: 0x004EF1CC, 1.5: 0x004E6D0C, 1.75: 0x004E81A4, 2.0: 0x004E6084, 2.5: 0x004E6D44,
                 3.0: 0x004E6D4C, 4.0: 0x004E6D40}[ODDS_SCALE]
CPU_CATCHING_CELL = FACTOR_TABLE + 4 * CATCHING_FACTOR_INDEX           # side 0 (CPU)
HUMAN_CATCHING_CELL = FACTOR_TABLE + 4 * (CATCHING_FACTOR_INDEX + 10)  # side 1 (Human)
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
RETAIL_KICK_GATE = bytes.fromhex("034373a3d3f3e373130b03235347030749130749030d")


class CatchSliderError(ValueError):
    """The catch-slider patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CatchSliderError(message)


def _rel32(src: int, dst: int) -> bytes:
    return struct.pack("<i", dst - (src + 5))


def cave_bytes() -> bytes:
    """rand -> rand / (K * (human + cpu Catching)) for an offense or kicked-ball catcher,
    rand / (2 * Interception) for any other defender; both finish in the tail (``kick_gate_bytes``).
    The sliders are read from the factor table ``0xAAB8C0`` (the same cells ``FUN_0017b8f0`` returns:
    CPU index 4, Human index 14), so the result does not depend on which side the catcher is on."""

    code = b""
    code += b"\xe8" + _rel32(CAVE_VA + len(code), RAND_FN)                      # call rand            st0 = rand
    code += b"\x83\x3d" + struct.pack("<I", BALL_KIND_GLOBAL) + b"\x03"        # cmp [ball kind],3
    code += b"\x74\x0e"                                                        # je offense (+14)     kicked ball: catcher
    code += b"\xa1" + struct.pack("<I", OFFENSE_TEAM_GLOBAL)                    # mov eax,[offense team]
    code += b"\x3b\x43\x38"                                                    # cmp eax,[ebx+0x38]   catcher's team?
    here = CAVE_VA + len(code)
    code += b"\x0f\x85" + struct.pack("<i", KICK_GATE_VA - (here + 6))          # jne defender (tail +0)
    code += b"\xd9\x05" + struct.pack("<I", CPU_CATCHING_CELL)                  # offense: fld [cpu Catching]
    code += b"\xd8\x05" + struct.pack("<I", HUMAN_CATCHING_CELL)                # fadd [human Catching]
    here = CAVE_VA + len(code)
    code += b"\xe9" + _rel32(here, KICK_GATE_VA + DEFENDER_BYTES)                # jmp tail +11 (scale and divide)
    code += b"\x90" * (CAVE_SIZE - len(code))
    assert len(code) == CAVE_SIZE, len(code)
    return code


DEFENDER_BYTES = 11


def kick_gate_bytes(scale_va: int | None = None) -> bytes:
    """The 22-byte tail (the slot of the former kick gate): +0 the interception branch,
    rand / (2 * Interception); +11 the catching branch, rand / (ODDS_SCALE * (human + cpu))."""

    scale_va = ODDS_SCALE_VA if scale_va is None else scale_va
    code = b"\xd9\x05" + struct.pack("<I", INT_SLIDER_GLOBAL)  # fld [Interception slider]
    code += b"\xd8\xc0"                                         # fadd st0,st0           2*slider
    code += b"\xde\xf9"                                         # fdivp st1,st0          rand/(2*slider)
    code += b"\xc3"                                             # ret
    assert len(code) == DEFENDER_BYTES
    code += b"\xd8\x0d" + struct.pack("<I", scale_va)          # fmul [K]               m = K*(h+c)
    code += b"\xd8\xf9"                                         # fdivr st0,st1          st0 = rand/m
    code += b"\xdd\xd9"                                         # fstp st1               pop the spare rand
    code += b"\xc3"                                             # ret
    assert len(code) == KICK_GATE_SIZE, len(code)
    return code


PATCHED_HOOK = b"\xe8" + _rel32(HOOK_VA, CAVE_VA)


IMAGE_BASE = 0x10000


def odds_multiplier(human_slider: float, cpu_slider: float | None = None, defender: bool = False) -> float:
    """Odds multiplier the cave applies: ``ODDS_SCALE * (human + cpu)`` for a catcher (the same for both
    sides; a lone value stands for both sliders), ``2 * interception`` for another defender."""

    if defender:
        return 2.0 * human_slider
    return ODDS_SCALE * (human_slider + (human_slider if cpu_slider is None else cpu_slider))


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
        ("kick_gate", _offset(payload, KICK_GATE_VA), RETAIL_KICK_GATE, kick_gate_bytes()),
        ("hook", _offset(payload, HOOK_VA), RETAIL_HOOK, PATCHED_HOOK),
        ("ceiling_human", _offset(payload, CEIL_SITES[0]), RETAIL_CEIL, PATCHED_CEIL),
        ("ceiling_cpu", _offset(payload, CEIL_SITES[1]), RETAIL_CEIL, PATCHED_CEIL),
    ]


# b780 b5-sim: the b779 gp1 revision (K = 2.0 at 0x4E6084, beta-79 / v0.8) differs only in the tail's constant address.
PREVIOUS_ODDS_SCALE_VA = 0x004E6084


def status(payload: bytes) -> str:
    """'retail', 'applied', 'previous' (the beta-79 revision with K = 2.0; apply() moves it to the current K) or
    'foreign' (bytes match neither; refuse to touch)."""

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
    if _previous(payload, sites):
        return "previous"
    return "foreign"


def _previous(payload: bytes, sites) -> bool:
    old_tail = kick_gate_bytes(PREVIOUS_ODDS_SCALE_VA)
    for label, off, before, after in sites:
        got = payload[off: off + len(before)]
        if got != (old_tail if label == "kick_gate" else after):
            return False
    return True


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Patch retail sites, replay an exact installation, and refuse foreign/mixed bytes."""

    state = status(payload)
    if state == "applied":
        return payload, {"already_applied": True, "edits": [], "changed_bytes": 0, "sections_repinned": []}
    if state == "previous":                      # beta-79 revision: only the tail's scale constant moves (XBE header)
        buf = bytearray(payload)
        off = _offset(payload, KICK_GATE_VA)
        buf[off: off + KICK_GATE_SIZE] = kick_gate_bytes()
        patched = bytes(buf)
        _require(status(patched) == "applied", "post-upgrade verification failed")
        return patched, {"upgraded_from": "previous", "edits": [{"label": "kick_gate", "file_offset": f"0x{off:x}",
                         "before": kick_gate_bytes(PREVIOUS_ODDS_SCALE_VA).hex(), "after": kick_gate_bytes().hex()}],
                         "changed_bytes": sum(1 for a, b in zip(payload, patched) if a != b), "sections_repinned": []}
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
           "CEIL_SITES", "PREVIOUS_ODDS_SCALE_VA", "apply", "cave_bytes", "odds_multiplier", "status"]
