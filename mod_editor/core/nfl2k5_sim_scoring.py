"""Simulated-game kicking: field-goal accuracy by distance and long field-goal attempts (in place, two sites).

Part of the 128 MiB franchise simulator option ``sim_qb_injuries`` (Realistic and Custom install it, Retail restores
the original bytes; see ``nfl2k5_sim_qb_injuries._edits``).  Both sites are inside the native scheduled simulator,
so they act on every game the console simulates instead of playing it (franchise weeks, Gamecast, other season
simulations).  Played-game physics, saves, rosters and allocations are untouched.  The bytes at both sites are
identical in retail, released v0.9 and the beta 81 standard edition.

**Field-goal chance (``0x109B5A..0x109BED``, 148 bytes, same length).**  The scheduled kick handler (dispatch entry 6,
``0x109A00``) keeps kick yards ``y = line-to-goal + 17`` at ``[esp+0x10]`` and the rating-adjusted distance
``adj = y + 50 x (defence composite - kicker rating)`` at ``[esp+0x28]``.  Stock: base 0.95 under 30 yards, 0.90 under
40, 0.85 under 50, 0.75 from 50; ``p = base + 0.375 - 0.015 x adj``, capped at 0.98.  That made 54.9% from 40-49 and
42.2% from 50+ in four signed standard seasons (NFL 2021-25: 79.8% and 68.4%).  The rewrite keeps the credited-distance
write into the kick record, the stock base under 40, base 0.85 from 40 (no ten-point drop at 50), the stock arithmetic
and constants in the stock order (so an extra point's chance is bit-identical), and for a field goal adds
``GAIN_PER_YARD x y``, less ``TAIL_PER_YARD`` per yard past ``TAIL_START``.  Cap, force-make, conditional miss and
the draw are unchanged.  This is the beta 81 E16 trial curve; its native mean chance at the NFL distance mix was
97.9, 92.8, 79.6, 72.0, 64.2, 48.0 and 30.4% under 30, 30s, 40s, 50-54, 55-59, 60-64 and 65+ (NFL 98.0, 93.4, 79.8,
73.4, 62.7, 47.2, 33.3).

**Long attempts (``0x106EC8..0x106F1F``, 88 bytes, 37 used, the rest int3).**  On fourth down in quarters 1 to 3, or
leading in the 4th, the play selector ``0x106A30`` kicked a field goal under 33 yards to goal, punted beyond 37 and in
between kicked only on a 1-in-256 to 1-in-576 draw, so a CPU club practically never tried a kick of 50 yards or more
outside the late-game paths (0.074 a club-game against the NFL's 0.434).  The rewrite draws ``x`` uniformly between
``RAMP_LOW`` and ``RAMP_HIGH`` with the game's own helper ``0x101960`` on the match generator and kicks when ``x`` is
beyond the line to goal: always inside ``RAMP_LOW`` yards to goal, never beyond ``RAMP_HIGH``, linearly in between
(NFL 2021-25, the same situations, field-goal share of kicks: 0.97 at 36, 0.82 at 37, 0.75 at 38, 0.48 at 39, 0.19
at 40, 0.14 at 41, 0.04 at 42).  The fourth-quarter, overtime and end-of-half paths are unchanged.
"""
from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_sim_scoring"

ACCURACY_VA = 0x00109B5A
ACCURACY_SIZE = 0x94
RETAIL_ACCURACY = bytes.fromhex(
    "d94424108b7e0cd81d3c694e00c1e00e33c72500c03f008bcf33c8dfe0894e0cf6c4057a0ac74424143333733feb34d9442410"
    "d81d847f4e00dfe0f6c4057a0ac74424146666663feb19d9442410d81da4724e00dfe0f6c4057a08c74424149a99593fd94424"
    "28d80ddc6b4f00d825b06b4f00d86c2414d95c2414d905ac0f4f00d85c2414dfe0f6c4057a08c744241448e17a3f")
RAMP_VA = 0x00106EC8
RAMP_SIZE = 0x58
RETAIL_RAMP = bytes.fromhex(
    "d9050072a90051dcc0d825a4724e00d91c24e821a0ffff8bc883f9017d05b901000000d9050072a900d81d84264f00dfe0f6c4"
    "417b22d9050072a900d81d007f4e00dfe0f6c4057a9c8bd10fafd152e8d4b0ffff85c0748d")

# Native addresses the rewrites use (all checked as retail by the tests).
FN_UNIFORM_BETWEEN = 0x00101960    # stdcall(float lo, float hi) -> st0 = lo + u * (hi - lo), u from 0xE5FCA0
LINE_TO_GOAL = 0x00A97200
PAT_FLAG = 0x00A971C0
PUNT_VA = 0x00106EAD               # returns 9
FIELD_GOAL_VA = 0x00106F20         # returns 6
STOCK_SLOPE = 0x004F6BDC           # 0.015
STOCK_OFFSET = 0x004F6BB0          # 0.375

# Starting parameters (scoring/DESIGN.md section 5).
BASES = (0.95, 0.90, 0.85)         # under 30, 30-39, from 40
GAIN_PER_YARD = 0.00475
TAIL_START = 55.0
TAIL_PER_YARD = 0.0225
CAP = 0.98
RAMP_LOW = 36.0
RAMP_HIGH = 41.5


class SimScoringError(ValueError):
    """The simulated kicking sites hold bytes that are neither retail nor this version's."""


def _require(condition, message):
    if not condition:
        raise SimScoringError(message)


def _f32(value: float) -> bytes:
    return struct.pack("<f", value)


def _rel32(source_next: int, target: int) -> bytes:
    return struct.pack("<i", target - source_next)


def accuracy_bytes(*, gain=GAIN_PER_YARD, tail_start=TAIL_START, tail_per_yard=TAIL_PER_YARD,
                   bases=BASES) -> bytes:
    """The 148 bytes at ``ACCURACY_VA`` (source: ``tools/scoring/sim_fg_chance.S``)."""
    under30, thirties, from40 = bases
    tail_k, tail_b = gain - tail_per_yard, tail_per_yard * tail_start
    va = ACCURACY_VA
    code = bytearray()
    code += bytes.fromhex("8b7e0c" "c1e00e" "31f8" "2500c03f00" "31460c")   # credited yards into [esi+0xC]
    code += bytes.fromhex("8b442410")                                       # mov eax, [esp+0x10] (y bits)
    code += b"\xb9" + _f32(under30)                                          # mov ecx, base under 30
    code += b"\x3d" + _f32(30.0) + b"\x72\x11"                             # cmp eax, 30.0 ; jb .base
    code += b"\xb9" + _f32(thirties)
    code += b"\x3d" + _f32(40.0) + b"\x72\x05"                             # cmp eax, 40.0 ; jb .base
    code += b"\xb9" + _f32(from40)
    code += bytes.fromhex("894c2414")                                       # .base: mov [esp+0x14], ecx
    code += bytes.fromhex("d9442428")                                       # fld adj
    code += b"\xd8\x0d" + struct.pack("<I", STOCK_SLOPE)                    # fmul 0.015
    code += b"\xd8\x25" + struct.pack("<I", STOCK_OFFSET)                   # fsub 0.375
    code += bytes.fromhex("d86c2414")                                       # fsubr base
    code += b"\x83\x3d" + struct.pack("<I", PAT_FLAG) + b"\x00\x75\x2d"     # cmp [PAT], 0 ; jne .cap
    code += bytes.fromhex("d9442410")                                       # fld y
    code += b"\x3d" + _f32(tail_start) + b"\x76\x1a"                       # cmp eax, tail ; jbe .gain
    consts = va + len(code) + 6 + 6 + 2
    code += b"\xd8\x0d" + struct.pack("<I", consts)                         # fmul tail_k
    code += b"\xd8\x05" + struct.pack("<I", consts + 4)                     # fadd tail_b
    code += b"\xeb\x12"                                                     # jmp .add
    code += _f32(tail_k) + _f32(tail_b) + _f32(gain)
    code += b"\xd8\x0d" + struct.pack("<I", consts + 8)                     # .gain: fmul gain
    code += bytes.fromhex("dec1")                                           # .add: faddp st(1), st
    code += bytes.fromhex("d95c2414")                                       # .cap: fstp [esp+0x14]
    code += b"\xb9" + _f32(CAP)                                             # mov ecx, 0.98
    code += bytes.fromhex("394c2414" "7e04" "894c2414")                     # cmp ; jle .done ; mov
    code += b"\x90" * (ACCURACY_SIZE - len(code))                           # .done (falls into 0x109BEE)
    _require(len(code) == ACCURACY_SIZE, "simulated field-goal chance does not fit its site")
    return bytes(code)


def ramp_bytes(*, low=RAMP_LOW, high=RAMP_HIGH) -> bytes:
    """The 88 bytes at ``RAMP_VA`` (source: ``tools/scoring/sim_long_attempts.S``)."""
    _require(0.0 <= low < high <= 99.0, "the long field-goal ramp needs 0 <= low < high <= 99 yards to goal")
    va = RAMP_VA
    code = bytearray()
    code += b"\x68" + _f32(high) + b"\x68" + _f32(low)                      # push hi ; push lo
    code += b"\xe8" + _rel32(va + len(code) + 5, FN_UNIFORM_BETWEEN)        # call uniform_between
    code += b"\xd8\x1d" + struct.pack("<I", LINE_TO_GOAL)                   # fcomp line to goal
    code += bytes.fromhex("dfe0" "f6c441")                                  # fnstsw ax ; test ah, 0x41
    code += b"\x0f\x85" + _rel32(va + len(code) + 6, PUNT_VA)               # draw <= line to goal: punt
    code += b"\xe9" + _rel32(va + len(code) + 5, FIELD_GOAL_VA)             # field goal
    code += b"\xcc" * (RAMP_SIZE - len(code))
    _require(len(code) == RAMP_SIZE, "long field-goal ramp does not fit its site")
    return bytes(code)


def edits(**parameters) -> tuple[tuple[str, int, bytes, bytes], ...]:
    """(name, address, retail bytes, enabled bytes) for the simulator option's edit list."""
    accuracy = {k: parameters[k] for k in ("gain", "tail_start", "tail_per_yard", "bases") if k in parameters}
    ramp = {k: parameters[k] for k in ("low", "high") if k in parameters}
    _require(set(parameters) <= set(accuracy) | set(ramp), "unknown simulated scoring parameter")
    return (("simulated field-goal chance", ACCURACY_VA, RETAIL_ACCURACY, accuracy_bytes(**accuracy)),
            ("simulated long field-goal attempts", RAMP_VA, RETAIL_RAMP, ramp_bytes(**ramp)))


def status(payload: bytes) -> str:
    """``retail`` (both sites retail), ``applied`` (both sites this version), otherwise ``foreign``."""
    try:
        image = XbeImage(payload)
        states = set()
        for _, va, retail, enabled in edits():
            value = image.read(va, len(retail))
            states.add("retail" if value == retail else "applied" if value == enabled else "foreign")
    except Exception:  # noqa: BLE001 - an unreadable image is foreign
        return "foreign"
    return states.pop() if len(states) == 1 else "foreign"


def read_settings(payload: bytes) -> Mapping[str, object]:
    state = status(payload)
    if state != "applied":
        return {"status": state}
    return {"status": state, "gain_per_yard": GAIN_PER_YARD, "tail_start": TAIL_START,
            "tail_per_yard": TAIL_PER_YARD, "bases": list(BASES), "ramp_low": RAMP_LOW, "ramp_high": RAMP_HIGH}


def lab_overlay(**parameters) -> list[dict[str, str]]:
    """The same edits as a guest-memory overlay for the offline season harness (calibration only)."""
    return [{"name": name, "va": f"0x{va:X}", "before": retail.hex(), "after": enabled.hex()}
            for name, va, retail, enabled in edits(**parameters)]


__all__ = ["ACCURACY_SIZE", "ACCURACY_VA", "OWNER", "RAMP_SIZE", "RAMP_VA", "RETAIL_ACCURACY", "RETAIL_RAMP",
           "SimScoringError", "accuracy_bytes", "edits", "lab_overlay", "ramp_bytes", "read_settings", "status"]
