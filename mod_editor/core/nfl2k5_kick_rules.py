"""Modern-era kicking spots for ESPN NFL 2K5 (executable patch, xemu-only).

Retail rules (all proved in the retail ``default.xbe``, see ``KICK_RULES_2026-09-03.md``):

* the field axis is ``z`` in centimetres with midfield at 0 and the goal lines at +/-4572
  (50 yd x 91.44); a team's attacking direction is the +/-1 sign read as
  ``[[[team+8]+0xc]+4] > 0``;
* **kickoff** from the kicking team's 30: every kickoff builder computes ``-sign * 1828.8``
  (the shared 20-yd float at 0x4EDD24; 0x50EB74 holds -1828.8 for one builder) - the opening,
  second-half and overtime kickoffs (``FUN_001584a0`` / ``FUN_00158620`` / ``FUN_001587f0``),
  the kickoff after a FG / PAT / two-point try (``FUN_0022e050``), after a failed try
  (``FUN_0022e250``) and the PAT-phase dead-ball table (``FUN_0022bc70``);
* **touchback** at the 20: the kick dead-ball handler sets ``ctx+0x17c`` to the receiving
  direction (``FUN_000a1a20`` -> ``FUN_000b7780``) and the next-spot routine ``FUN_000b6340``
  spots the ball at ``ctx[0x17c] * 2743.2`` (the shared 30-yd float at 0x4F0F98) for every kind
  of kick - kickoffs, safety kicks and punts alike;
* **point after** from the 2: ``FUN_0022e050`` spots the try at ``sign * 4389.12`` (0x50A53C,
  48 yd from midfield) before the play is called, for both the kick and the two-point play.

The patch (about 190 bytes, everything pattern-checked against retail):

* the seven kickoff ``fmul`` operands are repointed at two private floats (the requested
  ``kickoff_yard`` as a distance from midfield and its negative);
* the touchback ``fmul`` in ``FUN_000b6340`` becomes a call into a cave that multiplies by the
  private touchback float (default the 35, the 2026 rule) when the finished play was a
  **kickoff** (phase 2) and by the retail 20-yd constant otherwise, so punts and safety kicks
  keep their touchback at the 20;
* the PAT split (2 -> ``pat_yard``, two-point tries back at the 2):

  * **the try record itself says the kick spot.** ``FUN_0022e050`` (dead-ball driver, touchdown
    branch) builds the next-play record with ``rec+0x48 = sign * [0x50A53C]`` (4389.12 = the 2);
    ``FUN_0022e4d0`` (record applier) then copies it into the line of scrimmage ``ctx+0x10..0x1c``
    and the ball spot ``ctx+0x30..0x3c`` and sets phase 3.  The ``fmul`` operand at 0x22E1E1 is
    repointed at the private ``pat_kick`` float, so **both teams start every try at the 15** -
    the huddle, the play-call preview, the down marker, the ball, the line-ups.  (The other
    readers of 0x50A53C - 0x1A52CD, 0x2E335C, 0x2F1FC2/D3, 0x22BE34 - are AI "within 2 yd of
    the goal line" tests and are left alone.)
  * **a two-point pick moves everything back to the 2.** One register-preserving routine
    (``fix_pat``) runs on a point-after (phase 3): it reads the offense's chosen formation
    (``[[[0xE60280]+0xc]+8]``, the chain ``FUN_0013a0b0`` walks, guarded against its ``-4`` "no play
    yet" sentinel; flags bits 8-13 == 12 is the Field Goal formation) and maps the spot
    (``ctx+0x18``, ``ctx+0x38`` and the resting ball's z) between the exact retail 2-yd value and
    the exact ``pat_yard`` value - kick formation: 2 -> kick spot (a safety net; the record
    already says so), anything else: kick spot -> 2.  It only ever rewrites those two exact values,
    so penalty re-spots are respected.  Hook sites, all of them **before** the offense's line-up
    targets are computed (the 9/3 z disc proved that the line-up is fixed at pick time inside
    ``FUN_001ceac0`` - its tail ``FUN_0018e4d0`` -> ``FUN_001840b0`` builds every player's target from
    ``ctx+0x10`` right then - and that a fixer placed later, in ``FUN_0009fa80``, moved the defense
    but left the offense at the 2):

    * ``FUN_000a31e0`` @0xA328A, the first call after the formation store (``call FUN_00190730``,
      inside the ``param_2 != 0`` block), and @0xA333C, the handler's join point after the controller
      loop (both formation paths), before ``FUN_0009f4c0`` / ``FUN_0009cbd0`` (down-marker and LOS
      globals), ``FUN_0009f990``, ``FUN_001ceac0`` (offense line-up), ``FUN_0009fa80`` (play plan), the
      defense's pick and line-up: ``call FUN_0009f4c0`` -> ``call stub`` (``push FUN_0009f4c0`` then the
      fixer, whose ``ret`` calls the retail callee, which returns to the handler);
    * ``FUN_000a24b0`` @0xA24E7, the audible / re-pick handler, first call after its formation
      store: ``call FUN_0009f990`` -> the same trick;
    * ``FUN_001ceac0`` @0x1CEAC0, the team line-up routine's entry (all six callers, offense and
      defense, including the ``FUN_00186310`` / ``FUN_0009faf0`` / ``FUN_0009fb80`` paths): the first
      three instructions (``sub esp,0x24; push ebx; push ebp``) become ``call stub``; the stub runs
      the fixer, drops the return address, replays the three instructions and jumps to 0x1CEAC5.

Everything lives in ``FUN_001afcc0`` (0x1AFCC0..0x1AFDEC, 300 bytes), an AI helper with no
reference anywhere in the image (Ghidra reference scan plus an image-wide imm32/rel32 scan);
its retail bytes are recorded and required.  The ``.text`` digest is recomputed.  The record
builder, the record applier, both pick handlers, the line-up entry stub and the fixer were
executed under unicorn on the patched retail image (see ``tests/nfl2k5_kick_rules_test.py``);
the in-game result is Noah's to witness.

**Power-only mode** (``apply(..., spots=False)``): only the field-goal distance part - the two
``.rdata`` curve tables and, for ``cpu_fg_range="retail"``, the four CPU-range operands plus the 80
bytes of retail curve copies in the dead function's tail (its code bytes and every spot site stay
retail).  ``status()`` reports ``"power_only"`` for such an image; ``apply(spots=True)`` upgrades it
to the full patch (the table copies are already in place); a full image cannot be downgraded.

**2026 spots** (NFL Rule 6, 2025 amendments, in force for 2026): kickoff from the 35, touchback on a
kickoff to the **35** (the 2024 dynamic-kickoff value was the 30; ``touchback_yard=30`` reproduces
it), PAT from the 15.  Punts and safety kicks keep the retail 20 (phase-gated cave).

**Field-goal distance** (``max_fg_yards``, retail 60): a place kick's range is not a velocity
cap but two ``.rdata`` curve tables read through the shared interpolator ``FUN_001b0ae0`` by the
human launch routine ``FUN_003147a0`` (calls at 0x3148C2 / 0x3148D7):

* ``0x50B4F0`` **meter -> distance**: ``(0 fill -> 20 yd)(0.6 -> 40)(0.9 -> 55)(1.0 -> 60)``;
* ``0x50B514`` **kicker -> factor**: ``(0 -> 0.2)(0.3 -> 0.4)(0.4 -> 0.8)(0.8 -> 0.9)(1.0 -> 1.0)``,
  looked up at ``KPW_eff - 0.2 * (1 - KAC_eff)`` (attributes 7 and 0x1a of ``FUN_0017b010``);
* distance = meter_curve(fill) * kicker_curve(power') - rand() * 4 yd (0x4F0F58), then the
  launch speed is the 45-degree solve that clears a 10-ft bar (0x509B70) at that distance:
  ``v^2 = g d^2 / (d - h)`` (0x50D9BC = -980.66).  Nothing else clamps it; the Crib cheat
  "Crazy Kick" (flag 0xE601E8) multiplies the horizontal velocity by 1.75 (0x50DA00) inside
  ``FUN_001cbaf0`` instead.

The patch re-spaces both tables as a scale: the meter curve keeps its 0-fill point and
stretches the rest to the new ceiling, and the kicker factor at each knot ``x`` becomes
``f(x) * (60 + (M - 60) * x**4) / M`` so that a perfect meter gives retail yards to mid-power
legs and the full ceiling only to a 99.  The CPU range routine ``FUN_0018b120`` (fourth-down
and end-of-half logic, 14 callers) reads the same two tables; by default its four table
operands (0x18B1AD, 0x18B1B8, 0x18B1CC, 0x18B1D7) are repointed at retail copies kept inside
the cave so CPU decisions stay retail (``cpu_fg_range="retail"``); ``"scaled"`` leaves them on
the live tables.  Kickoff (0x50B980, 85 yd at 1.0) and punt (0x50C0F8, 75 yd) curves are not
touched.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm

IMAGE_BASE = 0x10000
YARD_CM = 91.44
FIELD_HALF_YD = 50.0

RETAIL_KICKOFF_YARD = 30
RETAIL_TOUCHBACK_YARD = 20
RETAIL_PAT_YARD = 2
MODERN_KICKOFF_YARD = 35        # 2024+ dynamic kickoff: kicked from the 35
MODERN_TOUCHBACK_YARD = 35      # 2025+ (in force 2026): kickoff touchback to the 35; 2024's value was the 30
TOUCHBACK_2024_YARD = 30
MODERN_PAT_YARD = 15
RETAIL_MAX_FG_YARDS = 60.0
MIN_MAX_FG_YARDS = 60.0
MAX_MAX_FG_YARDS = 90.0
FG_SCALE_POWER = 4.0            # x**4 weighting: only elite legs collect the raised ceiling
FG_RANDOM_LOSS_YD = 4.0         # 0x4F0F58: rand() * 365.76 cm is taken off every place kick
FG_LOS_TO_POSTS_YD = 17.0       # 0x50A37C: 7-yd hold + 10-yd end zone, subtracted by the CPU range routine
FG_ACCURACY_PENALTY = 0.2       # 0x50F4E0 (-0.2): power' = KPW - 0.2 * (1 - KAC)
CPU_FG_RANGE_MODES = ("retail", "scaled")

CAVE_VA = 0x001AFCC0            # FUN_001afcc0: dead AI helper, 300 bytes to the next function's padding
CAVE_SIZE = 300
FLOAT_COUNT = 4                 # kickoff+, kickoff-, touchback, pat_kick (the 2-yd value is the retail float)
CODE_VA = CAVE_VA + 4 * FLOAT_COUNT

PHASE_GLOBAL = 0x00E602B4       # 0 pregame/OT toss, 1 safety kick, 2 kickoff, 3 point after, 4 scrimmage
CTX_GLOBAL = 0x00E602EC         # game context: +0x10 LOS vec, +0x30 ball-spot vec, +0x17c touchback sign
POSSESSION_GLOBAL = 0x00E60280  # team with the ball
BALL_GLOBAL = 0x00E5FC00        # ball object: [0] holder, [+0x14] transform (x, y, z, 1)
RETAIL_TOUCHBACK_CONST = 0x004F0F98   # 2743.2 (30 yd from midfield = the 20)
RETAIL_KICKOFF_CONST = 0x004EDD24     # 1828.8
RETAIL_KICKOFF_NEG_CONST = 0x0050EB74  # -1828.8
RETAIL_PAT_CONST = 0x0050A53C          # 4389.12 (48 yd from midfield = the 2); FUN_0022e050 spots every try here
FG_FORMATION_TYPE = 12
PLAYCALL_TARGET_VA = 0x0013A0B0        # FUN_0013a0b0: LOS snapshot + formation classifier, first call of FUN_0009fa80

# field-goal distance curves (u32 count; (float x, float y) * count) in .rdata
FG_METER_TABLE_VA = 0x0050B4F0      # meter fill -> distance (cm); FUN_003147a0 @0x3148D7, FUN_0018b120 @0x18B1BD
FG_POWER_TABLE_VA = 0x0050B514      # kicker power' -> factor;    FUN_003147a0 @0x3148C2, FUN_0018b120 @0x18B1E9
RETAIL_FG_METER = ((0.0, 20.0), (0.6, 40.0), (0.9, 55.0), (1.0, 60.0))            # y in yards
RETAIL_FG_POWER = ((0.0, 0.2), (0.3, 0.4), (0.4, 0.8), (0.8, 0.9), (1.0, 1.0))    # y is a factor
# FUN_0018b120 (CPU maximum field-goal range): the table operands it loads
CPU_RANGE_SITES = (
    ("cpu_meter_count", 0x0018B1AD, b"\x8b\x15", FG_METER_TABLE_VA),        # mov edx, [count]
    ("cpu_meter_table", 0x0018B1B8, b"\xb9", FG_METER_TABLE_VA + 4),         # mov ecx, pairs
    ("cpu_power_count", 0x0018B1CC, b"\x8b\x15", FG_POWER_TABLE_VA),
    ("cpu_power_table", 0x0018B1D7, b"\xb9", FG_POWER_TABLE_VA + 4),
)

# kickoff spot: `fmul dword [const]` operands (d8 0d imm32); the sign logic around them is untouched
KICKOFF_SITES = (
    ("kickoff_game_start", 0x0015851C, RETAIL_KICKOFF_CONST, "pos"),
    ("kickoff_half_start", 0x0015869F, RETAIL_KICKOFF_CONST, "pos"),
    ("kickoff_overtime_start", 0x00158854, RETAIL_KICKOFF_CONST, "pos"),
    ("kickoff_after_fg_pat", 0x0022E0E7, RETAIL_KICKOFF_CONST, "pos"),
    ("kickoff_after_two_point", 0x0022E173, RETAIL_KICKOFF_CONST, "pos"),
    ("kickoff_after_failed_try", 0x0022E2B0, RETAIL_KICKOFF_CONST, "pos"),
    ("kickoff_pat_table", 0x0022BCD2, RETAIL_KICKOFF_NEG_CONST, "neg"),
)
TOUCHBACK_SITE_VA = 0x000B63AB      # FUN_000b6340: fmul dword [0x4f0f98] after fld dword [ctx+0x17c]
TRY_RECORD_SITE_VA = 0x0022E1E1     # FUN_0022e050: fmul dword [0x50a53c] -> rec+0x48, the try spot (both teams)
PAT_STORE_SITE_VA = 0x000A328A      # FUN_000a31e0: call FUN_00190730, the first call after `[state+8] = formation`
PAT_PICK_SITE_VA = 0x000A333C       # FUN_000a31e0: call FUN_0009f4c0 (join point, both formation paths)
PAT_AUDIBLE_SITE_VA = 0x000A24E7    # FUN_000a24b0: call FUN_0009f990 (first call after its formation store)
PAT_LINEUP_ENTRY_VA = 0x001CEAC0    # FUN_001ceac0 entry: sub esp,0x24 / push ebx / push ebp (the team line-up)
STORE_TARGET_VA = 0x00190730
PICK_TARGET_VA = 0x0009F4C0
AUDIBLE_TARGET_VA = 0x0009F990
LINEUP_RESUME_VA = PAT_LINEUP_ENTRY_VA + 5
PAT_HOOK_SITES = (TRY_RECORD_SITE_VA, PAT_STORE_SITE_VA, PAT_PICK_SITE_VA, PAT_AUDIBLE_SITE_VA, PAT_LINEUP_ENTRY_VA)

RETAIL_FMUL_KICKOFF = bytes.fromhex("d80d24dd4e00")
RETAIL_FMUL_KICKOFF_NEG = bytes.fromhex("d80d74eb5000")
RETAIL_FMUL_TOUCHBACK = bytes.fromhex("d80d980f4f00")
RETAIL_FMUL_PAT = bytes.fromhex("d80d3ca55000")          # fmul dword [0x50a53c]
RETAIL_CALL_STORE = bytes.fromhex("e8a1d40e00")          # call 0x190730 from 0xa328a
RETAIL_CALL_PICK = bytes.fromhex("e87fc1ffff")           # call 0x9f4c0 from 0xa333c
RETAIL_CALL_AUDIBLE = bytes.fromhex("e8a4d4ffff")        # call 0x9f990 from 0xa24e7
RETAIL_LINEUP_ENTRY = bytes.fromhex("83ec245355")        # sub esp,0x24 ; push ebx ; push ebp

# FUN_001afcc0 as shipped: push ebp ... ret (0x1AFCC0..0x1AFDEB), 300 bytes
RETAIL_CAVE = bytes.fromhex(
    "558bec83e4f083ec2856578bf9e8de4cfaff8b0d00fce50085c9740c8b0185c0740683781c01740233c03bc775"
    "05e83de1f2ff8b4f2033d2e8f39d11008bf0c70690f31a00e83670f8ff8946408b47388b48140f28010f294620"
    "d94620d81d80414e00b9a0fce500dfe0f6c4417519e85c8ee9ffd82d84414e00d80d4c0f4f00d8054c0f4f00eb"
    "17e8438ee9ffd82d84414e00d80d4c0f4f00d82d749b5000d95e20b9a0fce500e8248ee9ffd82d84414e00d80d"
    "4c0f4f00d84628d95e28e8bd6ff8ff85c0745fe8b46ff8ffd946208b50180f2842300f29442410d86424108d44"
    "2420d95c2420d94624d8642414d95c2424d94628d8642418d95c2428d9462cd864241cd95c242ce813c7ffffd8"
    "1d5c0f4f00dfe0f6c4057a0cd94628d80524dd4e00d95e285f5e8be55dc3"
)


class KickRulesError(ValueError):
    """The kicking-rules patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise KickRulesError(message)


def spot_cm(yard_line: float) -> float:
    """Distance from midfield (cm) of a yard line counted from the nearer goal line."""

    return float(round((FIELD_HALF_YD - float(yard_line)) * YARD_CM, 6))


def yard_line(cm: float) -> float:
    return float(round(FIELD_HALF_YD - abs(float(cm)) / YARD_CM, 3))


def _f32(value: float) -> bytes:
    return struct.pack("<f", value)


def _validate(kickoff_yard: float, touchback_yard: float, pat_yard: float) -> None:
    _require(1 <= kickoff_yard <= 49, "kickoff_yard must be a yard line between 1 and 49")
    _require(1 <= touchback_yard <= 49, "touchback_yard must be a yard line between 1 and 49")
    _require(1 <= pat_yard <= 49, "pat_yard must be a yard line between 1 and 49")


def _validate_fg(max_fg_yards: float, cpu_fg_range: str) -> float:
    max_fg_yards = round(float(max_fg_yards), 3)
    _require(MIN_MAX_FG_YARDS <= max_fg_yards <= MAX_MAX_FG_YARDS,
             f"max_fg_yards {max_fg_yards} outside {MIN_MAX_FG_YARDS:g}..{MAX_MAX_FG_YARDS:g}")
    _require(cpu_fg_range in CPU_FG_RANGE_MODES, f"cpu_fg_range must be one of {CPU_FG_RANGE_MODES}")
    return max_fg_yards


# --- field-goal curves --------------------------------------------------------------------------

def interpolate(pairs, x: float) -> float:
    """The game's lookup (FUN_001b0ae0): clamp at both ends, linear between points."""

    if x <= pairs[0][0]:
        return float(pairs[0][1])
    if x >= pairs[-1][0]:
        return float(pairs[-1][1])
    for (xa, ya), (xb, yb) in zip(pairs, pairs[1:]):
        if xa <= x <= xb:
            return float(ya) if xb == xa else float(ya + (yb - ya) * (x - xa) / (xb - xa))
    return float(pairs[-1][1])


def fg_tables(max_fg_yards: float = RETAIL_MAX_FG_YARDS) -> dict[str, tuple[tuple[float, float], ...]]:
    """Both curves for a ceiling: identity at 60, a scale above it (x columns never move)."""

    m = _validate_fg(max_fg_yards, "retail")
    retail_top = RETAIL_FG_METER[-1][1]
    base = RETAIL_FG_METER[0][1]
    meter = tuple(
        (x, y if index == 0 else round(base + (y - base) * (m - base) / (retail_top - base), 3))
        for index, (x, y) in enumerate(RETAIL_FG_METER)
    )
    power = tuple(
        (x, round(f * (retail_top + (m - retail_top) * x ** FG_SCALE_POWER) / m, 6))
        for x, f in RETAIL_FG_POWER
    )
    return {"meter": meter, "power": power}


def _table_bytes(pairs, y_scale: float) -> bytes:
    out = struct.pack("<I", len(pairs))
    for x, y in pairs:
        out += struct.pack("<ff", float(x), float(y) * y_scale)
    return out


def fg_table_bytes(max_fg_yards: float = RETAIL_MAX_FG_YARDS) -> dict[str, bytes]:
    tables = fg_tables(max_fg_yards)
    return {"meter": _table_bytes(tables["meter"], YARD_CM), "power": _table_bytes(tables["power"], 1.0)}


RETAIL_FG_METER_BYTES = fg_table_bytes(RETAIL_MAX_FG_YARDS)["meter"]
RETAIL_FG_POWER_BYTES = fg_table_bytes(RETAIL_MAX_FG_YARDS)["power"]


def _decode_table(blob: bytes, count: int, y_scale: float):
    if len(blob) < 4 + 8 * count or struct.unpack_from("<I", blob, 0)[0] != count:
        return None
    return tuple(
        (round(struct.unpack_from("<f", blob, 4 + 8 * i)[0], 6),
         struct.unpack_from("<f", blob, 8 + 8 * i)[0] / y_scale)
        for i in range(count)
    )


def _decode_max_fg(payload: bytes):
    """The ceiling encoded in the meter table, or None when its shape is not the game's."""

    off = _offset(payload, FG_METER_TABLE_VA)
    pairs = _decode_table(payload[off: off + len(RETAIL_FG_METER_BYTES)], len(RETAIL_FG_METER), YARD_CM)
    if pairs is None or tuple(x for x, _y in pairs) != tuple(x for x, _y in RETAIL_FG_METER):
        return None
    top = round(pairs[-1][1], 3)
    if not MIN_MAX_FG_YARDS <= top <= MAX_MAX_FG_YARDS:
        return None
    return top


def fg_preview(max_fg_yards: float = RETAIL_MAX_FG_YARDS, ratings=(99, 95, 90, 85, 80, 75, 70, 60)) -> list[dict]:
    """Perfect-meter distance by kick power (accuracy assumed equal), retail vs the ceiling."""

    tables = fg_tables(max_fg_yards)
    rows = []
    for rating in ratings:
        power = min(rating / 100.0, 1.0)
        x = power - FG_ACCURACY_PENALTY * (1.0 - power)
        retail = interpolate(RETAIL_FG_METER, 1.0) * interpolate(RETAIL_FG_POWER, x)
        new = interpolate(tables["meter"], 1.0) * interpolate(tables["power"], x)
        rows.append({"rating": rating, "retail_yards": round(retail, 1), "max_yards": round(new, 1),
                     "min_yards": round(new - FG_RANDOM_LOSS_YD, 1),
                     "cpu_range_los_yards": round(retail - FG_LOS_TO_POSTS_YD, 1)})
    return rows


# --- cave layout -------------------------------------------------------------------------------

FLOAT_KICKOFF_POS = CAVE_VA
FLOAT_KICKOFF_NEG = CAVE_VA + 4
FLOAT_TOUCHBACK = CAVE_VA + 8
FLOAT_PAT_KICK = CAVE_VA + 12
FLOAT_PAT_TWO = RETAIL_PAT_CONST        # the two-point spot is the game's own 2-yd constant


def float_bytes(kickoff_yard: float = MODERN_KICKOFF_YARD, touchback_yard: float = MODERN_TOUCHBACK_YARD,
                pat_yard: float = MODERN_PAT_YARD) -> bytes:
    _validate(kickoff_yard, touchback_yard, pat_yard)
    ko = spot_cm(kickoff_yard)
    return _f32(ko) + _f32(-ko) + _f32(spot_cm(touchback_yard)) + _f32(spot_cm(pat_yard))


def _code(base: int) -> tuple[bytes, dict[str, int]]:
    """The cave's code: the PAT spot fixer, three register-preserving stubs and the touchback cave."""

    imm = lambda va: struct.pack("<I", va).hex()  # noqa: E731
    a = _Asm(base)
    # ---- pick / audible stubs: `push <retail callee>` then the fixer; its `ret` calls the callee,
    #      which returns to the hooked handler (fastcall ecx/edx survive pushad/popad)
    a.label("stub_store")
    a.b("68" + imm(STORE_TARGET_VA))            # push FUN_00190730
    a.j8("eb", "fix_pat")
    a.label("stub_pick")
    a.b("68" + imm(PICK_TARGET_VA))             # push FUN_0009f4c0
    a.j8("eb", "fix_pat")
    a.label("stub_audible")
    a.b("68" + imm(AUDIBLE_TARGET_VA))          # push FUN_0009f990
    a.j8("eb", "fix_pat")
    # ---- line-up entry stub: run the fixer, drop the hook's return address, replay the three
    #      replaced instructions of FUN_001ceac0 and resume at its fourth
    a.label("stub_lineup")
    a.j32("e8", "fix_pat")
    a.b("83c404")                               # add esp, 4
    a.b("83ec24")                               # sub esp, 0x24
    a.b("53")                                   # push ebx
    a.b("55")                                   # push ebp
    a.jmp_abs(LINEUP_RESUME_VA)                 # jmp 0x1ceac5
    # ---- fix_pat: preserves every register; acts only on a point-after with the retail/kick spots
    a.label("fix_pat")
    a.b("60")                                   # pushad
    a.b("803d" + imm(PHASE_GLOBAL) + "03")      # cmp byte [phase], 3
    a.j8("75", "done")                          # jne done
    a.b("8b0d" + imm(POSSESSION_GLOBAL))        # mov ecx, [possession team]
    a.b("85c9")                                 # test ecx, ecx
    a.j8("74", "done")
    a.b("8b490c")                               # mov ecx, [ecx+0xc]      play-call state
    a.b("83f9fc")                               # cmp ecx, -4             the game's "no play yet" sentinel (FUN_0013a0b0)
    a.j8("74", "done")
    a.b("85c9")
    a.j8("74", "done")
    a.b("8b4908")                               # mov ecx, [ecx+8]        formation record
    a.b("85c9")
    a.j8("74", "done")
    a.b("8b4904")                               # mov ecx, [ecx+4]        formation flags
    a.b("c1e908")                               # shr ecx, 8
    a.b("83e13f")                               # and ecx, 0x3f           formation type
    a.b("a1" + imm(CTX_GLOBAL))                 # mov eax, [ctx]
    a.b("8b5018")                               # mov edx, [eax+0x18]     spot z
    a.b("83f9" + f"{FG_FORMATION_TYPE:02x}")    # cmp ecx, 12             Field Goal formation?
    a.j8("75", "two_point")
    a.b("8b0d" + imm(FLOAT_PAT_TWO))            # mov ecx, [pat_two]      from: the retail 2-yd spot
    a.b("8b1d" + imm(FLOAT_PAT_KICK))           # mov ebx, [pat_kick]     to: the kick spot
    a.j8("eb", "map")
    a.label("two_point")
    a.b("8b0d" + imm(FLOAT_PAT_KICK))           # from: the kick spot
    a.b("8b1d" + imm(FLOAT_PAT_TWO))            # to: the 2-yd spot
    a.label("map")
    a.b("3bd1")                                 # cmp edx, ecx            +direction?
    a.j8("74", "store")
    a.b("0fbaf91f")                             # btc ecx, 31             flip the sign bit
    a.b("3bd1")                                 # cmp edx, ecx            -direction?
    a.j8("75", "done")                          # anything else (penalty re-spot ...) is left alone
    a.b("0fbafb1f")                             # btc ebx, 31
    a.label("store")
    a.b("895818")                               # mov [eax+0x18], ebx     line of scrimmage
    a.b("895838")                               # mov [eax+0x38], ebx     ball spot
    a.b("8b0d" + imm(BALL_GLOBAL))              # mov ecx, [ball]
    a.b("85c9")
    a.j8("74", "done")
    a.b("833900")                               # cmp dword [ecx], 0      nobody holds it
    a.j8("75", "done")
    a.b("8b4914")                               # mov ecx, [ecx+0x14]     transform
    a.b("85c9")
    a.j8("74", "done")
    a.b("895908")                               # mov [ecx+8], ebx        resting ball z
    a.label("done")
    a.b("61")                                   # popad
    a.b("c3")                                   # ret
    # ---- touchback: st0 = receiving direction; multiply by the kickoff touchback or the retail 20
    a.label("touchback")
    a.b("803d" + imm(PHASE_GLOBAL) + "02")      # cmp byte [phase], 2     the finished play was a kickoff
    a.j8("75", "retail_touchback")
    a.b("d80d" + imm(FLOAT_TOUCHBACK))          # fmul dword [touchback]
    a.b("c3")
    a.label("retail_touchback")
    a.b(RETAIL_FMUL_TOUCHBACK.hex())            # fmul dword [0x4f0f98]
    a.b("c3")
    a.label("end")
    code = a.assemble()
    return code, {name: base + off for name, off in a.labels.items()}


def _cave_tables_offset() -> int:
    code, _labels = _code(CODE_VA)
    return (4 * FLOAT_COUNT + len(code) + 3) & ~3


CAVE_METER_TABLE_VA = CAVE_VA + _cave_tables_offset()                          # retail meter curve copy
CAVE_POWER_TABLE_VA = CAVE_METER_TABLE_VA + len(RETAIL_FG_METER_BYTES)         # retail kicker curve copy


def cave_bytes(kickoff_yard: float = MODERN_KICKOFF_YARD, touchback_yard: float = MODERN_TOUCHBACK_YARD,
               pat_yard: float = MODERN_PAT_YARD) -> bytes:
    """Floats, code, the two retail field-goal curves, int3-padded to the dead function's 300 bytes."""

    code, _labels = _code(CODE_VA)
    body = float_bytes(kickoff_yard, touchback_yard, pat_yard) + code
    body += b"\xcc" * (_cave_tables_offset() - len(body))
    body += RETAIL_FG_METER_BYTES + RETAIL_FG_POWER_BYTES
    _require(len(body) <= CAVE_SIZE, f"kick-rules cave is {len(body)} bytes, over {CAVE_SIZE}")
    return body + b"\xcc" * (CAVE_SIZE - len(body))


def cave_labels() -> dict[str, int]:
    labels = dict(_code(CODE_VA)[1])
    labels["retail_meter_table"] = CAVE_METER_TABLE_VA
    labels["retail_power_table"] = CAVE_POWER_TABLE_VA
    return labels


def _rel32_call(site: int, target: int) -> bytes:
    return b"\xe8" + struct.pack("<i", target - (site + 5))


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise KickRulesError(f"VA 0x{va:x} is in no section")


def _sites(payload: bytes, kickoff_yard: float, touchback_yard: float, pat_yard: float,
           max_fg_yards: float = RETAIL_MAX_FG_YARDS, cpu_fg_range: str = "retail"
           ) -> list[tuple[str, int, bytes, bytes]]:
    """Every site as (label, file offset, retail bytes, patched bytes).

    Groups by label prefix: ``cave`` (floats + code, the spot machinery), ``cave_tables`` (the retail
    curve copies in the dead function's tail), ``fg_*`` (the two live curve tables), ``cpu_*`` (the
    CPU-range operands), everything else = the kickoff / touchback / PAT spot sites.
    """

    labels = cave_labels()
    cave = cave_bytes(kickoff_yard, touchback_yard, pat_yard)
    split = _cave_tables_offset()
    sites: list[tuple[str, int, bytes, bytes]] = [
        ("cave", _offset(payload, CAVE_VA), RETAIL_CAVE[:split], cave[:split]),
        ("cave_tables", _offset(payload, CAVE_VA) + split, RETAIL_CAVE[split:], cave[split:]),
    ]
    tables = fg_table_bytes(max_fg_yards)
    sites.append(("fg_meter_table", _offset(payload, FG_METER_TABLE_VA), RETAIL_FG_METER_BYTES, tables["meter"]))
    sites.append(("fg_power_table", _offset(payload, FG_POWER_TABLE_VA), RETAIL_FG_POWER_BYTES, tables["power"]))
    cave_targets = {FG_METER_TABLE_VA: CAVE_METER_TABLE_VA, FG_METER_TABLE_VA + 4: CAVE_METER_TABLE_VA + 4,
                    FG_POWER_TABLE_VA: CAVE_POWER_TABLE_VA, FG_POWER_TABLE_VA + 4: CAVE_POWER_TABLE_VA + 4}
    for label, va, opcode, retail_va in CPU_RANGE_SITES:
        before = opcode + struct.pack("<I", retail_va)
        after = opcode + struct.pack("<I", cave_targets[retail_va]) if cpu_fg_range == "retail" else before
        sites.append((label, _offset(payload, va), before, after))
    for label, va, retail_const, kind in KICKOFF_SITES:
        before = b"\xd8\x0d" + struct.pack("<I", retail_const)
        after = b"\xd8\x0d" + struct.pack("<I", FLOAT_KICKOFF_POS if kind == "pos" else FLOAT_KICKOFF_NEG)
        sites.append((label, _offset(payload, va), before, after))
    sites.append(("touchback_hook", _offset(payload, TOUCHBACK_SITE_VA), RETAIL_FMUL_TOUCHBACK,
                  _rel32_call(TOUCHBACK_SITE_VA, labels["touchback"]) + b"\x90"))
    sites.append(("pat_try_record", _offset(payload, TRY_RECORD_SITE_VA), RETAIL_FMUL_PAT,
                  b"\xd8\x0d" + struct.pack("<I", FLOAT_PAT_KICK)))
    sites.append(("pat_store_hook", _offset(payload, PAT_STORE_SITE_VA), RETAIL_CALL_STORE,
                  _rel32_call(PAT_STORE_SITE_VA, labels["stub_store"])))
    sites.append(("pat_pick_hook", _offset(payload, PAT_PICK_SITE_VA), RETAIL_CALL_PICK,
                  _rel32_call(PAT_PICK_SITE_VA, labels["stub_pick"])))
    sites.append(("pat_audible_hook", _offset(payload, PAT_AUDIBLE_SITE_VA), RETAIL_CALL_AUDIBLE,
                  _rel32_call(PAT_AUDIBLE_SITE_VA, labels["stub_audible"])))
    sites.append(("pat_lineup_hook", _offset(payload, PAT_LINEUP_ENTRY_VA), RETAIL_LINEUP_ENTRY,
                  _rel32_call(PAT_LINEUP_ENTRY_VA, labels["stub_lineup"])))
    return sites


def _site_state(payload: bytes, label: str, off: int, before: bytes, after: bytes) -> str:
    got = payload[off: off + len(before)]
    if got == before:
        return "retail"
    if label == "cave":
        # the floats vary with the settings; the code does not
        return "applied" if got[4 * FLOAT_COUNT:] == after[4 * FLOAT_COUNT:] else "foreign"
    if label.startswith("fg_"):
        # the y columns vary with the ceiling; re-derive it from the meter table and compare exactly
        ceiling = _decode_max_fg(payload)
        if ceiling is None:
            return "foreign"
        expected = fg_table_bytes(ceiling)["meter" if label == "fg_meter_table" else "power"]
        return "applied" if got == expected else "foreign"
    return "applied" if got == after else "foreign"


def _site_states(payload: bytes) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """(spot sites incl. the cave code, field-goal curve sites incl. the cave tables, CPU-range sites)
    -> state; raises on an unreadable image."""

    sites = _sites(payload, MODERN_KICKOFF_YARD, MODERN_TOUCHBACK_YARD, MODERN_PAT_YARD, 70, "retail")
    spots: dict[str, str] = {}
    curves: dict[str, str] = {}
    cpu: dict[str, str] = {}
    for site in sites:
        label = site[0]
        group = cpu if label.startswith("cpu_") else curves if label.startswith("fg_") or label == "cave_tables" else spots
        group[label] = _site_state(payload, *site)
    return spots, curves, cpu


STATUS_POWER_ONLY = "power_only"


def status(payload: bytes) -> str:
    """'retail', 'applied' (the full patch, any settings), 'power_only' (only the field-goal distance
    part: curve tables and the CPU-range pin, every spot site retail), or 'foreign' (bytes match none
    of those; refuse to touch).

    The spot sites decide between retail / applied / power_only.  The curve tables, the cave's table
    copies and the CPU operands may each sit at retail on an applied image (a retail ceiling, or
    ``cpu_fg_range="scaled"``), never half-way.
    """

    try:
        spots, curves, cpu = _site_states(payload)
    except (KickRulesError, ValueError, struct.error):
        return "foreign"
    spot_states, cpu_states = set(spots.values()), set(cpu.values())
    live = {curves["fg_meter_table"], curves["fg_power_table"]}
    copies = curves["cave_tables"]
    # the CPU pin needs the copies; a scaled CPU needs neither
    if cpu_states == {"applied"} and copies != "applied":
        return "foreign"
    if cpu_states == {"retail"} and copies == "applied" and live == {"retail"}:
        return "foreign"        # copies without anything that uses them: not one of our layouts
    if cpu_states not in ({"retail"}, {"applied"}) or live not in ({"retail"}, {"applied"}):
        return "foreign"
    if copies not in ("retail", "applied"):
        return "foreign"
    if spot_states == {"retail"}:
        if live == {"retail"} and cpu_states == {"retail"} and copies == "retail":
            return "retail"
        if live == {"applied"}:
            return STATUS_POWER_ONLY
        return "foreign"
    if spot_states == {"applied"}:
        return "applied"
    return "foreign"


def read_settings(payload: bytes) -> dict[str, object]:
    """The rules currently encoded (retail values when the patch is not applied)."""

    state = status(payload)
    if state == STATUS_POWER_ONLY:
        _spots, _curves, cpu = _site_states(payload)
        return {"status": state, "spots": "retail", "kickoff_yard": float(RETAIL_KICKOFF_YARD),
                "touchback_yard": float(RETAIL_TOUCHBACK_YARD), "pat_yard": float(RETAIL_PAT_YARD),
                "pat_two_yard": float(RETAIL_PAT_YARD), "max_fg_yards": _decode_max_fg(payload),
                "cpu_fg_range": "retail" if set(cpu.values()) == {"applied"} else "scaled"}
    if state != "applied":
        return {"status": state, "spots": "retail", "kickoff_yard": float(RETAIL_KICKOFF_YARD),
                "touchback_yard": float(RETAIL_TOUCHBACK_YARD), "pat_yard": float(RETAIL_PAT_YARD),
                "max_fg_yards": RETAIL_MAX_FG_YARDS, "cpu_fg_range": "retail"}
    off = _offset(payload, CAVE_VA)
    ko, ko_neg, tb, pat = struct.unpack_from("<4f", payload, off)
    pat_two = struct.unpack_from("<f", payload, _offset(payload, RETAIL_PAT_CONST))[0]
    _spots, _curves, cpu = _site_states(payload)
    return {"status": state, "spots": "applied", "kickoff_yard": yard_line(ko), "touchback_yard": yard_line(tb),
            "pat_yard": yard_line(pat), "kickoff_neg_consistent": ko_neg == -ko,
            "pat_two_yard": yard_line(pat_two), "max_fg_yards": _decode_max_fg(payload),
            "cpu_fg_range": "retail" if set(cpu.values()) == {"applied"} else "scaled"}


def apply(payload: bytes, kickoff_yard: float = MODERN_KICKOFF_YARD, touchback_yard: float = MODERN_TOUCHBACK_YARD,
          pat_yard: float = MODERN_PAT_YARD, max_fg_yards: float = 70, cpu_fg_range: str = "retail",
          spots: bool = True) -> tuple[bytes, Mapping[str, object]]:
    """Return the patched XBE bytes plus a receipt; refuses anything but retail sites.

    ``spots=False`` is the power-only mode: only the field-goal distance tables (and the CPU-range pin
    with its retail copies) are written; kickoff / touchback / PAT stay retail (2004 rules).  A
    power-only image can be upgraded to the full patch by calling ``apply`` again with ``spots=True``
    and the **same** ``max_fg_yards`` / ``cpu_fg_range``; nothing can be downgraded.
    """

    _validate(kickoff_yard, touchback_yard, pat_yard)
    max_fg_yards = _validate_fg(max_fg_yards, cpu_fg_range)
    state = status(payload)
    if spots:
        _require(state in ("retail", STATUS_POWER_ONLY), f"kick-rules sites are {state}, not retail")
        if state == STATUS_POWER_ONLY:
            have = read_settings(payload)
            _require(have["max_fg_yards"] == max_fg_yards and have["cpu_fg_range"] == cpu_fg_range,
                     f"power-only image carries ceiling {have['max_fg_yards']} / CPU {have['cpu_fg_range']}; "
                     f"upgrade with the same field-goal settings")
    else:
        _require(state == "retail", f"kick-rules sites are {state}, not retail")
        _require(max_fg_yards != RETAIL_MAX_FG_YARDS, "power-only mode with the retail ceiling changes nothing")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched: set[int] = set()
    edits = []
    for label, off, before, after in _sites(payload, kickoff_yard, touchback_yard, pat_yard,
                                            max_fg_yards, cpu_fg_range):
        if not spots and not (label.startswith("fg_") or label.startswith("cpu_") or label == "cave_tables"):
            continue
        if label == "cave_tables" and cpu_fg_range != "retail":
            continue                # nothing reads the copies when the CPU uses the live tables
        if after == before or payload[off: off + len(after)] == after:
            continue
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "file_offset": f"0x{off:x}", "bytes": len(after),
                      "before": before.hex() if label != "cave" else f"<{len(before)} retail bytes>",
                      "after": after.hex() if label != "cave" else f"<{len(after)} bytes>"})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    expected_state = "applied" if spots else STATUS_POWER_ONLY
    _require(status(patched) == expected_state, "post-apply verification failed")
    back = read_settings(patched)
    _require(back["max_fg_yards"] == max_fg_yards and back["cpu_fg_range"] == cpu_fg_range,
             "post-apply read-back of the field-goal ceiling failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    code, labels = _code(CODE_VA)
    tables = fg_tables(max_fg_yards)
    spot_receipt = ({"kickoff_yard": float(kickoff_yard), "touchback_yard": float(touchback_yard),
                     "pat_yard": float(pat_yard), "kickoff_spot_cm": spot_cm(kickoff_yard),
                     "touchback_spot_cm": spot_cm(touchback_yard), "pat_kick_spot_cm": spot_cm(pat_yard)}
                    if spots else
                    {"kickoff_yard": float(RETAIL_KICKOFF_YARD), "touchback_yard": float(RETAIL_TOUCHBACK_YARD),
                     "pat_yard": float(RETAIL_PAT_YARD)})
    return patched, {
        "edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
        "status": expected_state, "spots": spots, **spot_receipt,
        "max_fg_yards": max_fg_yards, "cpu_fg_range": cpu_fg_range,
        "fg_meter_curve": {"retail": RETAIL_FG_METER, "applied": tables["meter"]},
        "fg_power_curve": {"retail": RETAIL_FG_POWER, "applied": tables["power"]},
        "fg_preview": fg_preview(max_fg_yards),
        "cave_va": f"0x{CAVE_VA:x}", "cave_code_bytes": len(code),
        "cave_labels": {name: f"0x{va:x}" for name, va in cave_labels().items()},
    }


__all__ = ["KickRulesError", "STATUS_POWER_ONLY", "CAVE_VA", "CAVE_SIZE", "RETAIL_CAVE", "KICKOFF_SITES", "TOUCHBACK_SITE_VA",
           "TRY_RECORD_SITE_VA", "PAT_STORE_SITE_VA", "PAT_PICK_SITE_VA", "PAT_AUDIBLE_SITE_VA", "PAT_LINEUP_ENTRY_VA", "PAT_HOOK_SITES",
           "RETAIL_KICKOFF_YARD",
           "MODERN_KICKOFF_YARD", "MODERN_TOUCHBACK_YARD", "TOUCHBACK_2024_YARD", "MODERN_PAT_YARD",
           "RETAIL_TOUCHBACK_YARD", "RETAIL_PAT_YARD", "RETAIL_MAX_FG_YARDS", "MIN_MAX_FG_YARDS",
           "MAX_MAX_FG_YARDS", "FG_METER_TABLE_VA", "FG_POWER_TABLE_VA", "RETAIL_FG_METER", "RETAIL_FG_POWER",
           "CPU_RANGE_SITES", "CPU_FG_RANGE_MODES", "CAVE_METER_TABLE_VA", "CAVE_POWER_TABLE_VA", "apply",
           "cave_bytes", "cave_labels", "fg_preview", "fg_table_bytes", "fg_tables", "float_bytes",
           "interpolate", "read_settings", "spot_cm", "status", "yard_line"]
