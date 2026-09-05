"""Throw distance and pass-arc tuning for the NFL 2K5 retail XBE.

What the game does (reverse-engineered 2026-09-02, witnessed in xemu with gdb):

* A human throw is targeted by ``FUN_002da8e0`` and launched by ``FUN_001cbdb0``
  as an exact ballistic solve from the target point and a flight time.  Nothing
  caps the ball's velocity.
* The target is clamped to a maximum distance that is a piecewise-linear
  function of the passer's *effective* arm strength (0..1).  Two curves exist:
  ``bullet`` (button held past half) and ``lob``.  Every throw past 20 yards is
  forced to a lob, and the accuracy pass (``FUN_002d9700``) then re-clamps the
  final target to ``max(bullet_curve, lob_curve / 2)``.  With retail tables that
  makes the **bullet** curve the real deep ceiling: 55 yards at arm 1.0.
* Flight time is distance divided by a speed that is itself a curve of distance
  (``lobspeed`` for lobs, blended toward ``bulletspeed`` by hold).  The lob speed
  is flat at 20 yd/s past 40 yards, so a longer throw is not a taller one.

All five curves are plain ``u32 count; (float x, float y) * count`` tables in
``.rdata`` (x and y in centimetres where they are distances; 1 yd = 91.44 cm)
read through one shared interpolator (``FUN_001b0ae0``: clamp at both ends,
linear between).  This module finds the tables by their exact retail bytes
cross-checked against the section table, rewrites point values on a COPY of the
XBE (or of a disc image, patching ``default.xbe`` in place inside the copy),
recomputes the touched section digest, and verifies by read-back and byte diff.
Tables never grow, move, or change their point count.

Two "sliders" sit on top of the raw curves:

* ``max_deep_yards`` (55 = retail .. 100): the deep-ball ceiling at arm 1.0.  The
  bullet curve is re-spaced as a scale (mid-league arms gain a few yards, only
  elite arms reach the ceiling) and the lob curve is kept at or above it so the
  bullet curve stays the one that decides.
* ``arc`` (0 = retail .. 1): lowers the lob speed at the ceiling distance so
  long balls hang longer and climb higher.  0 leaves the retail speed table
  untouched.

Patched output is xemu-only (the RSA signature stays stale), exactly like the
bump-strength route.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import stat
import struct
from typing import Callable, Iterable, Mapping, Sequence

from . import platform_compat
from . import nfl2k5_catch_slider as catch_slider_patch
from . import nfl2k5_accel_ramp as accel_ramp_patch
from . import nfl2k5_draft_ai as draft_ai_patch
from . import nfl2k5_edge_rename as edge_rename_patch
from . import nfl2k5_returner_fix as returner_fix_patch
from . import nfl2k5_progression as progression_patch
from . import nfl2k5_modern_positions as scheme_labels_patch
from . import nfl2k5_camera as camera_patch
from . import nfl2k5_kick_rules as kick_rules_patch
from . import nfl2k5_dynamic_kickoff as dynamic_kickoff_patch
from . import nfl2k5_depth_chart_rows as depth_chart_rows_patch
from . import nfl2k5_depth_chart_storage as depth_chart_storage
from . import nfl2k5_practice_squad as practice_squad_patch
from . import nfl2k5_practice_reserves as practice_reserves_patch
from . import nfl2k5_depth_locks as depth_locks_patch
from . import nfl2k5_season_cap as season_cap_patch
from . import nfl2k5_xbe_space as xbe_space_patch
from . import nfl2k5_momentum as momentum_patch
from . import nfl2k5_defensive_try as defensive_try_patch
from . import nfl2k5_zone_drop as zone_drop_patch
from . import nfl2k5_dynamic_kickoff_relocated as kickoff_relocated_patch
from . import nfl2k5_scorebug_runtime as scorebug_runtime_patch
from . import nfl2k5_scorebug_ingame as scorebug_reference
from . import nfl2k5_music_policy as music_policy_patch
from . import nfl2k5_music_metadata as music_metadata_patch
from . import nfl2k5_music_storage as music_storage
from . import nfl2k5_playoff_picture as playoff_picture_patch


def _kick_power_status(payload: bytes) -> str:
    """Status of the power-only kicking fix: retail / applied (power-only OR the full patch, which includes it) / foreign."""
    state = kick_rules_patch.status(payload)
    return "applied" if state in ("power_only", "applied") else state
from . import nfl2k5_widescreen as widescreen_patch
from . import nfl2k5_overtime as overtime_patch
from . import nfl2k5_team_column as team_column_patch
from . import nfl2k5_position_row as position_row_patch
from . import nfl2k5_probowl_order as probowl_order_patch
from . import nfl2k5_penalties as penalties_patch
from . import nfl2k5_uniform_choice as uniform_choice_patch
from . import nfl2k5_kick_laces as kick_laces_patch
from . import nfl2k5_franchise_practice as franchise_practice_patch
from . import nfl2k5_prospect_names as prospect_names_patch
from . import nfl2k5_player_star as player_star_patch
from . import nfl2k5_seven_on_seven as seven_on_seven_patch
from . import nfl2k5_boot_logo as boot_logo
from .nfl2k5_bump_strength import (
    RETAIL_XBE_SHA256,
    _Section,
    _sections,
    _section_for_offset,
    section_digest,
)

READ_SCHEMA = "nfl2k5_throw_tuning_read/v1"
WRITE_SCHEMA = "nfl2k5_throw_tuning_write/v1"

YD_CM = 91.44
GRAVITY_YD_S2 = 980.664 / YD_CM  # the game's own constant (cm/s^2) in yards

RETAIL_MAX_DEEP_YARDS = 55.0
MIN_MAX_DEEP_YARDS = 55.0
MAX_MAX_DEEP_YARDS = 100.0
RETAIL_LOB_SPEED_YD_S = 20.0
MIN_ARC_LOB_SPEED_YD_S = 10.0
# Deep balls as elite NFL arms actually throw them: ~60 mph release, 3.2-3.9 s hang for
# 60-80 air yards, apex 13-20 yd. Retail's flat 20 yd/s past 40 yd was already close;
# this keeps the short game retail and slightly lengthens the very deep ball.
REALISTIC_LOBSPEED = ((6.0, 6.0), (10.0, 12.0), (20.0, 16.0), (45.0, 19.0), (80.0, 21.0))
# Arc by distance (Noah, 9/3): 45..60-yard lobs get the high, hanging arc (12 yd/s of ground speed
# ~ 4-5 s hang) while 61..80-yard bombs keep the flat realistic flight (21 yd/s from 63 yd on; the
# interpolator clamps past the last point).  The in-place .rdata table holds five points, so the
# first cut dropped the retail 10-yard point (a 10-yard lob rode the 6->20 line at 8.9 yd/s instead
# of 12, and every 20..45-yard ball slowed too).  Noah 9/3 night: "short accuracy and short throw
# power" must not change.  The table is therefore RELOCATED: an eight-point copy lives in the XBE
# header (certificate AlternateSignatureKeys tail, see ARC_TABLE_VA) and the two operands of the
# only reader (``FUN_002d8970``: ``mov edx,[0x50BCB8]`` count, ``mov ecx,0x50BCBC`` pairs) are
# repointed at it.  Points 1..5 ARE the retail table (6->6, 10->12, 20->16, 35->18, 40->20), so
# every throw up to 40 yards is byte-for-byte retail; 45..60 hang at 12; 63+ fly flat at 21.
HIGH_ARC_BAND_SPEED_YD_S = 12.0
ARC_BY_DISTANCE_LOBSPEED = ((6.0, 6.0), (10.0, 12.0), (20.0, 16.0), (35.0, 18.0), (40.0, 20.0),
                            (45.0, HIGH_ARC_BAND_SPEED_YD_S), (60.0, HIGH_ARC_BAND_SPEED_YD_S), (63.0, 21.0))
# The superseded five-point in-place profile (discs p..y of 9/3); recognised on read, never written.
LEGACY_ARC_BY_DISTANCE_LOBSPEED = ((6.0, 6.0), (20.0, 16.0), (45.0, HIGH_ARC_BAND_SPEED_YD_S),
                                   (60.0, HIGH_ARC_BAND_SPEED_YD_S), (63.0, 21.0))
IMAGE_BASE = 0x10000
# Relocated lob-speed table: 4 + 8 * 8 = 68 bytes at the tail of the certificate's
# AlternateSignatureKeys block (0x10254..0x10354, header page, mapped 1:1 at 0x10000, kernel-only
# at launch).  The widescreen cave owns 0x10254..0x102C4; nothing else in the tree touches the block.
ARC_TABLE_VA = 0x00010310
ARC_TABLE_END_VA = 0x00010354
# FUN_002d8970 (lob speed by distance, the table's ONLY reader; 9 callers, human and CPU alike):
LOBSPEED_COUNT_SITE_VA = 0x002D898B     # 8B 15 B8 BC 50 00   mov edx, dword ptr [0x50BCB8]
LOBSPEED_PAIRS_SITE_VA = 0x002D8992     # B9 BC BC 50 00      mov ecx, 0x50BCBC
# Retail certificate bytes at 0x10310..0x10354 (the pattern that must match before writing).
RETAIL_ARC_TABLE_SLOT = bytes.fromhex(
    "c09cbb6a33852f02452921d764c3eded0c779b160e924109bea4df8c738d157c7f7ee92d71ec2122d72bc761cb35a365b87f6eda0d2028c6db35afce174764ef0cb25c7c"
)
assert len(RETAIL_ARC_TABLE_SLOT) == ARC_TABLE_END_VA - ARC_TABLE_VA
assert RETAIL_ARC_TABLE_SLOT == widescreen_patch.RETAIL_ALT_KEYS[ARC_TABLE_VA - widescreen_patch.CAVE_VA:]
assert ARC_TABLE_VA >= widescreen_patch.CAVE_VA + len(widescreen_patch.cave_bytes())   # never overlap the widescreen cave

EXPECTED_XBE_SIZE = 11_948_032

ProgressSink = Callable[[str, int, int], None]


class ThrowTuningError(ValueError):
    """The requested throw-tuning operation is unsafe or impossible."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ThrowTuningError(message)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------
# Curve tables
@dataclass(frozen=True)
class Curve:
    name: str
    va: int                                     # VA of the count dword
    retail: tuple[tuple[float, float], ...]     # (x, y) in the units below
    x_unit: str                                  # "arm" (raw 0..1) or "yd"
    y_unit: str                                  # "yd" or "yd/s" (both cm-scaled)
    role: str

    @property
    def count(self) -> int:
        return len(self.retail)

    @property
    def size(self) -> int:
        return 4 + 8 * self.count

    @property
    def x_scale(self) -> float:
        return YD_CM if self.x_unit == "yd" else 1.0

    def encode(self, pairs: Sequence[tuple[float, float]]) -> bytes:
        _require(len(pairs) == self.count,
                 f"{self.name}: {len(pairs)} points given, table holds {self.count}")
        out = struct.pack("<I", self.count)
        for x, y in pairs:
            out += struct.pack("<ff", float(x) * self.x_scale, float(y) * YD_CM)
        return out

    def decode(self, blob: bytes) -> tuple[tuple[float, float], ...]:
        _require(len(blob) >= self.size, f"{self.name}: short table")
        count = struct.unpack_from("<I", blob, 0)[0]
        _require(count == self.count,
                 f"{self.name}: count word {count} != {self.count}")
        # float32 holds yards*91.44 to ~1e-4 yd; round to what the game can
        # distinguish so a decode(encode(x)) round trip is the identity.
        x_digits = 6 if self.x_unit == "arm" else 3
        return tuple(
            (
                round(struct.unpack_from("<f", blob, 4 + 8 * i)[0] / self.x_scale, x_digits),
                round(struct.unpack_from("<f", blob, 8 + 8 * i)[0] / YD_CM, 3),
            )
            for i in range(count)
        )

    @property
    def retail_bytes(self) -> bytes:
        return self.encode(self.retail)


CURVES: dict[str, Curve] = {
    "bullet": Curve(
        "bullet", 0x50BDC0,
        ((0.0, 25.0), (0.65, 35.0), (0.85, 45.0), (0.95, 50.0), (1.0, 55.0)),
        "arm", "yd", "max target distance, button held (and the deep re-clamp)",
    ),
    "lob": Curve(
        "lob", 0x50BD8C,
        ((0.0, 20.0), (0.5, 35.0), (0.65, 50.0), (0.85, 60.0), (0.95, 65.0), (1.0, 75.0)),
        "arm", "yd", "max target distance, lob",
    ),
    "anim": Curve(
        "anim", 0x50BD58,
        ((0.0, 20.0), (0.2, 30.0), (0.3, 50.0), (0.5, 60.0), (0.9, 70.0), (1.0, 80.0)),
        "arm", "yd", "throw-animation selector threshold (not edited)",
    ),
    "lobspeed": Curve(
        "lobspeed", 0x50BCB8,
        ((6.0, 6.0), (10.0, 12.0), (20.0, 16.0), (35.0, 18.0), (40.0, 20.0)),
        "yd", "yd/s", "horizontal ball speed by distance, lob",
    ),
    "bulletspeed": Curve(
        "bulletspeed", 0x50BC8C,
        ((4.0, 13.0), (10.0, 18.0), (15.0, 24.0), (25.0, 28.0), (35.0, 30.0)),
        "yd", "yd/s", "horizontal ball speed by distance, full hold (not edited)",
    ),
}
EDITABLE_CURVES = ("bullet", "lob", "lobspeed")


def interpolate(pairs: Sequence[tuple[float, float]], x: float) -> float:
    """The game's lookup: clamp at both ends, linear between points."""

    _require(len(pairs) >= 1, "empty curve")
    if x <= pairs[0][0]:
        return float(pairs[0][1])
    if x >= pairs[-1][0]:
        return float(pairs[-1][1])
    for (xa, ya), (xb, yb) in zip(pairs, pairs[1:]):
        if xa <= x <= xb:
            if xb == xa:
                return float(yb)
            return float(ya) + (float(yb) - float(ya)) * (x - xa) / (xb - xa)
    return float(pairs[-1][1])


def validate_pairs(curve: Curve, pairs: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    _require(len(pairs) == curve.count,
             f"{curve.name}: table holds {curve.count} points, {len(pairs)} given; "
             "tables cannot grow or shrink in place")
    out: list[tuple[float, float]] = []
    for x, y in pairs:
        x = float(x)
        y = float(y)
        _require(x == x and y == y and abs(x) != float("inf") and abs(y) != float("inf"),
                 f"{curve.name}: non-finite point")
        if curve.x_unit == "arm":
            _require(0.0 <= x <= 1.0, f"{curve.name}: x {x} outside 0..1")
        else:
            _require(0.0 < x <= 150.0, f"{curve.name}: x {x} yd is not sane")
        _require(0.0 < y <= 150.0, f"{curve.name}: {y} {curve.y_unit} is not sane")
        out.append((x, y))
    for (xa, _ya), (xb, _yb) in zip(out, out[1:]):
        _require(xa < xb, f"{curve.name}: x must be strictly ascending")
    return tuple(out)


# --------------------------------------------------------------------------
# Slider model
@dataclass(frozen=True)
class TuningSettings:
    max_deep_yards: float = RETAIL_MAX_DEEP_YARDS
    arc: float = 0.0
    realistic_flight: bool = False
    # 45..60-yard lobs hang high, 61+ stay flat (overrides ``arc`` and ``realistic_flight`` for the
    # lob-speed table only; the distance ceiling still comes from ``max_deep_yards``)
    arc_by_distance: bool = False

    def validated(self) -> "TuningSettings":
        _require(MIN_MAX_DEEP_YARDS <= self.max_deep_yards <= MAX_MAX_DEEP_YARDS,
                 f"max deep distance {self.max_deep_yards} outside "
                 f"{MIN_MAX_DEEP_YARDS:g}..{MAX_MAX_DEEP_YARDS:g} yards")
        _require(0.0 <= self.arc <= 1.0, f"arc {self.arc} outside 0..1")
        return self


_BULLET_AT_80 = (25.0, 38.0, 52.0, 66.0, 80.0)
_LOB_AT_80 = (20.0, 35.0, 50.0, 60.0, 72.0, 80.0)


def curves_for(settings: TuningSettings) -> dict[str, tuple[tuple[float, float], ...]]:
    """Map the two sliders onto the three editable curves.

    The shape between retail (55) and the witnessed 80-yard scale is linear in
    the ceiling and extrapolates the same way to 100.  The lob curve is held at
    or above the bullet curve at every shared x so the bullet curve remains the
    deciding deep clamp (``FUN_002d9700`` takes ``max(bullet, lob/2)`` after
    ``FUN_002da8e0`` clamps to lob for forced-lob deep throws).
    """

    settings = settings.validated()
    t = (settings.max_deep_yards - RETAIL_MAX_DEEP_YARDS) / (80.0 - RETAIL_MAX_DEEP_YARDS)
    bullet_retail = CURVES["bullet"].retail
    bullet = tuple(
        (x, round(y + (y80 - y) * t, 3))
        for (x, y), y80 in zip(bullet_retail, _BULLET_AT_80)
    )
    lob_retail = CURVES["lob"].retail
    lob_scaled = [
        (x, round(y + (y80 - y) * t, 3))
        for (x, y), y80 in zip(lob_retail, _LOB_AT_80)
    ]
    lob: list[tuple[float, float]] = []
    for x, y in lob_scaled:
        # Retail already keeps lob >= bullet from arm 0.5 upward (the only
        # region a real passer occupies); hold that invariant there against the
        # interpolated bullet value, and leave the arm-0 point alone so retail
        # settings reproduce retail bytes.
        if x >= 0.5:
            y = max(y, math.ceil(interpolate(bullet, x) * 1000.0) / 1000.0)
        lob.append((x, round(y, 3)))
    # The very top of the lob curve must be the ceiling itself.
    lob[-1] = (lob[-1][0], max(lob[-1][1], settings.max_deep_yards))
    # ``arc_by_distance`` is not an in-place table: it relocates the reader to the eight-point
    # ARC_BY_DISTANCE_LOBSPEED (see apply_arc_table); the .rdata table then keeps whatever the other
    # flags say (unused by the game once relocated, but it round-trips the settings on read-back).
    if settings.realistic_flight:
        lobspeed = REALISTIC_LOBSPEED
    elif settings.arc <= 0.0:
        lobspeed = CURVES["lobspeed"].retail
    else:
        knee = max(40.0, settings.max_deep_yards - 25.0)
        end_speed = RETAIL_LOB_SPEED_YD_S - (RETAIL_LOB_SPEED_YD_S - MIN_ARC_LOB_SPEED_YD_S) * settings.arc
        lobspeed = (
            (6.0, 6.0), (10.0, 12.0), (20.0, 16.0),
            (knee, RETAIL_LOB_SPEED_YD_S),
            (settings.max_deep_yards, round(end_speed, 3)),
        )
    result = {
        "bullet": validate_pairs(CURVES["bullet"], bullet),
        "lob": validate_pairs(CURVES["lob"], tuple(lob)),
        "lobspeed": validate_pairs(CURVES["lobspeed"], lobspeed),
    }
    for x_b, y_b in result["bullet"]:
        if x_b >= 0.5:
            _require(interpolate(result["lob"], x_b) >= y_b - 1e-6,
                     "internal: lob curve fell below the bullet curve")
    return result


def effective_lobspeed(settings: TuningSettings,
                       curves: Mapping[str, Sequence[tuple[float, float]]] | None = None) -> tuple[tuple[float, float], ...]:
    """The lob-speed table the game actually reads for ``settings``: the relocated eight-point
    profile with ``arc_by_distance``, otherwise the in-place table."""

    if settings.arc_by_distance:
        return ARC_BY_DISTANCE_LOBSPEED
    return tuple((curves or curves_for(settings))["lobspeed"])


@dataclass(frozen=True)
class PreviewRow:
    arm: float
    deep_cap_yards: float
    hang_seconds: float
    apex_yards: float


PREVIEW_ARMS = (0.70, 0.80, 0.85, 0.90, 0.95, 0.99, 1.00)


def preview(curves: Mapping[str, Sequence[tuple[float, float]]],
            arms: Iterable[float] = PREVIEW_ARMS) -> tuple[PreviewRow, ...]:
    """Deep-ball ceiling, hang time and apex height per effective arm.

    Deep throws are forced lobs, so the ceiling is ``max(bullet, lob/2)`` with
    ``lob >= bullet`` in every curve set this module writes; the flight time is
    ``distance / lobspeed(distance)`` and the launch is ballistic, so the apex
    is ``g * t^2 / 8``.
    """

    rows = []
    for arm in arms:
        cap = max(interpolate(curves["bullet"], arm), interpolate(curves["lob"], arm) / 2.0)
        cap = min(cap, interpolate(curves["lob"], arm))
        speed = interpolate(curves["lobspeed"], cap)
        hang = cap / speed if speed > 0 else 0.0
        apex = GRAVITY_YD_S2 * hang * hang / 8.0
        rows.append(PreviewRow(arm, round(cap, 2), round(hang, 2), round(apex, 1)))
    return tuple(rows)


# --------------------------------------------------------------------------
# Locating and reading
def _regular_non_link(path: Path) -> os.stat_result:
    info = path.lstat()
    _require(not stat.S_ISLNK(info.st_mode), f"refusing a symlink: {path}")
    _require(stat.S_ISREG(info.st_mode), f"not a regular file: {path}")
    return info


def _resolve_source(path: Path | str) -> Path:
    """Refuse symlinks on the path as given, then resolve it."""

    given = Path(path).expanduser()
    _require(given.exists(), f"source does not exist: {given}")
    _regular_non_link(given)
    return given.resolve(strict=True)


def locate_curve(payload: bytes, curve: Curve) -> int:
    """File offset of ``curve``: its exact retail bytes must sit where the section
    table says the VA lives; an already-edited table is accepted only at that
    same offset and only if the count word still matches."""

    sections = _sections(payload)
    expected: int | None = None
    for section in sections:
        if section.virtual_address <= curve.va < section.virtual_address + section.raw_size:
            expected = section.raw_offset + (curve.va - section.virtual_address)
            break
    _require(expected is not None, f"{curve.name}: VA 0x{curve.va:x} is in no section")
    _require(expected + curve.size <= len(payload), f"{curve.name}: table runs past the file")
    hits: list[int] = []
    start = payload.find(curve.retail_bytes)
    while start >= 0:
        hits.append(start)
        start = payload.find(curve.retail_bytes, start + 1)
    if hits:
        _require(hits == [expected],
                 f"{curve.name}: retail bytes found at {[hex(h) for h in hits]} but the "
                 f"section table places the table at 0x{expected:x}")
    else:
        count = struct.unpack_from("<I", payload, expected)[0]
        _require(count == curve.count,
                 f"{curve.name}: table at 0x{expected:x} is neither retail nor a "
                 "same-count edit; refusing to guess")
    return expected


def read_curves(payload: bytes) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for name, curve in CURVES.items():
        offset = locate_curve(payload, curve)
        blob = payload[offset: offset + curve.size]
        out[name] = {
            "va": f"0x{curve.va:x}",
            "file_offset": f"0x{offset:x}",
            "retail": blob == curve.retail_bytes,
            "points": curve.decode(blob),
            "x_unit": curve.x_unit,
            "y_unit": curve.y_unit,
            "role": curve.role,
            "editable": name in EDITABLE_CURVES,
        }
    return out


def infer_settings(curves: Mapping[str, Mapping[str, object]], arc_table: str | None = None) -> TuningSettings:
    """Best-effort slider positions for a set of read curves (for display).

    ``arc_table`` is :func:`arc_table_status` of the same executable ("applied" = the relocated
    eight-point profile is live); the superseded five-point in-place profile also reads as
    ``arc_by_distance`` so older discs and packs keep their label."""

    bullet = curves["bullet"]["points"]  # type: ignore[index]
    ceiling = float(bullet[-1][1])  # type: ignore[index]
    ceiling = min(max(ceiling, MIN_MAX_DEEP_YARDS), MAX_MAX_DEEP_YARDS)
    speed = curves["lobspeed"]["points"]  # type: ignore[index]
    realistic = tuple(speed) == tuple((x, y) for x, y in REALISTIC_LOBSPEED)
    legacy = tuple(speed) == tuple((x, y) for x, y in LEGACY_ARC_BY_DISTANCE_LOBSPEED)
    by_distance = arc_table == "applied" or legacy
    end_speed = float(speed[-1][1])  # type: ignore[index]
    if realistic or legacy or end_speed >= RETAIL_LOB_SPEED_YD_S - 1e-6:
        arc = 0.0
    else:
        arc = (RETAIL_LOB_SPEED_YD_S - end_speed) / (RETAIL_LOB_SPEED_YD_S - MIN_ARC_LOB_SPEED_YD_S)
        arc = min(max(arc, 0.0), 1.0)
    return TuningSettings(round(ceiling, 2), round(arc, 3), realistic, by_distance)


# --------------------------------------------------------------------------
# Arc by distance: the relocated lob-speed table (header) + the two operand repoints (.text)
ARC_TABLE_CURVE = Curve("lobspeed_relocated", ARC_TABLE_VA, ARC_BY_DISTANCE_LOBSPEED, "yd", "yd/s",
                        "horizontal ball speed by distance, lob (relocated eight-point profile)")
RETAIL_COUNT_OPERAND = b"\x8b\x15" + struct.pack("<I", CURVES["lobspeed"].va)
PATCHED_COUNT_OPERAND = b"\x8b\x15" + struct.pack("<I", ARC_TABLE_VA)
RETAIL_PAIRS_OPERAND = b"\xb9" + struct.pack("<I", CURVES["lobspeed"].va + 4)
PATCHED_PAIRS_OPERAND = b"\xb9" + struct.pack("<I", ARC_TABLE_VA + 4)


def _header_offset(payload: bytes, va: int) -> int:
    header_size = struct.unpack_from("<I", payload, 0x108)[0]
    _require(IMAGE_BASE <= va < IMAGE_BASE + header_size, f"VA 0x{va:x} is not inside the XBE header")
    return va - IMAGE_BASE


def _text_offset(payload: bytes, va: int) -> tuple[int, _Section]:
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address), section
    raise ThrowTuningError(f"VA 0x{va:x} is in no section")


def _arc_table_sites(payload: bytes) -> list[tuple[str, int, bytes, bytes, int | None]]:
    table = ARC_TABLE_CURVE.encode(ARC_BY_DISTANCE_LOBSPEED)
    _require(len(table) == len(RETAIL_ARC_TABLE_SLOT), "relocated table does not fill its slot exactly")
    count_off, count_section = _text_offset(payload, LOBSPEED_COUNT_SITE_VA)
    pairs_off, pairs_section = _text_offset(payload, LOBSPEED_PAIRS_SITE_VA)
    return [
        ("arc_table", _header_offset(payload, ARC_TABLE_VA), RETAIL_ARC_TABLE_SLOT, table, None),
        ("lobspeed_count_operand", count_off, RETAIL_COUNT_OPERAND, PATCHED_COUNT_OPERAND, count_section.index),
        ("lobspeed_pairs_operand", pairs_off, RETAIL_PAIRS_OPERAND, PATCHED_PAIRS_OPERAND, pairs_section.index),
    ]


def arc_table_status(payload: bytes) -> str:
    """'retail', 'applied' (reader repointed at the eight-point header table), or 'foreign'."""

    try:
        sites = _arc_table_sites(payload)
    except (ThrowTuningError, ValueError, struct.error, IndexError):
        return "foreign"
    states = set()
    for _label, off, before, after, _section in sites:
        got = payload[off: off + len(before)]
        states.add("retail" if got == before else "applied" if got == after else "foreign")
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def read_arc_table(payload: bytes) -> dict[str, object]:
    state = arc_table_status(payload)
    points = None
    if state == "applied":
        off = _header_offset(payload, ARC_TABLE_VA)
        points = ARC_TABLE_CURVE.decode(payload[off: off + ARC_TABLE_CURVE.size])
    return {"state": state, "va": f"0x{ARC_TABLE_VA:x}", "points": points,
            "reader": {"count_operand": f"0x{LOBSPEED_COUNT_SITE_VA:x}", "pairs_operand": f"0x{LOBSPEED_PAIRS_SITE_VA:x}"}}


def apply_arc_table(payload: bytes) -> tuple[bytes, dict[str, object]]:
    """Write the eight-point table into the header slot and repoint FUN_002d8970's two operands."""

    state = arc_table_status(payload)
    _require(state == "retail", f"arc-by-distance sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched: set[int] = set()
    edits = []
    for label, off, before, after, section_index in _arc_table_sites(payload):
        buf[off: off + len(after)] = after
        if section_index is not None:
            touched.add(section_index)
        edits.append({"label": label, "file_offset": f"0x{off:x}", "before": before.hex(), "after": after.hex()})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(arc_table_status(patched) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
                     "points": list(ARC_BY_DISTANCE_LOBSPEED)}


def _guardian_image_status(path: Path) -> str:
    # Resource compiler stays lazy for standalone executable readers.
    try:
        from . import nfl2k5_guardian_cap as cap
        return cap.image_status(path)
    except Exception:  # noqa: BLE001 - an unreadable resource is never an applied patch
        return "foreign"


def read_xbe(xbe_path: Path | str) -> dict[str, object]:
    path = _resolve_source(xbe_path)
    payload = path.read_bytes()
    curves = read_curves(payload)
    arc_table = read_arc_table(payload)
    return {
        "schema": READ_SCHEMA,
        "container": "xbe",
        "arc_table": arc_table,
        "catch_slider": catch_slider_patch.status(payload),
        "accel_ramp": accel_ramp_patch.status(payload),
        "draft_ai": draft_ai_patch.status(payload),
        "edge_rename": edge_rename_patch.status(payload),
        "returner_fix": returner_fix_patch.status(payload),
        "progression": progression_patch.status(payload),
        "scheme_labels": scheme_labels_patch.status(payload),
        "camera": camera_patch.status(payload),
        "kick_rules": kick_rules_patch.status(payload),
        "dynamic_kickoff": dynamic_kickoff_patch.status(payload),
        "dynamic_kickoff_settings": dynamic_kickoff_patch.read_settings(payload),
        "depth_chart_rows": depth_chart_rows_patch.status(payload),
        "practice_squad": practice_squad_patch.status(payload),
        "practice_reserves": practice_reserves_patch.status(payload),
        "depth_locks": depth_locks_patch.status(payload),
        "screen_timing": "n/a",
        "guardian_cap": "n/a",
        "season_cap": season_cap_patch.status(payload),
        **_allocator_feature_status(payload),
        "xbe_space": xbe_space_patch.status(payload),
        "kickoff_relocated": kickoff_relocated_patch.status(payload),
        "scorebug_runtime": scorebug_runtime_patch.status(payload),
        "scorebug_xbe": scorebug_reference.xbe_status(payload),
        "music_metadata_patch": music_metadata_patch.status(payload),
        **_music_status(payload),
        "kickoff_relocated_settings": kickoff_relocated_patch.read_settings(payload),
        "playoff_picture": playoff_picture_patch.status(payload),
        "kick_power": _kick_power_status(payload),
        "widescreen": widescreen_patch.status(payload),
        "overtime": overtime_patch.status(payload),
        "team_column": team_column_patch.status(payload),
        "seven_on_seven": seven_on_seven_patch.status(payload),
        "position_row": position_row_patch.status(payload),
        "probowl_order": probowl_order_patch.status(payload),
        "penalties": penalties_patch.status(payload),
        "uniform_choice": uniform_choice_patch.status(payload),
        "kick_laces": kick_laces_patch.status(payload),
        "franchise_practice": franchise_practice_patch.status(payload),
        "prospect_names": prospect_names_patch.xbe_status(payload),
        "player_star": player_star_patch.status(payload),
        "boot_logo": boot_logo.status(payload),
        "path": str(path),
        "xbe_sha256": _digest(payload),
        "matches_retail_sha256": _digest(payload) == RETAIL_XBE_SHA256,
        "curves": curves,
        "settings": infer_settings(curves, str(arc_table["state"])),
    }


# --------------------------------------------------------------------------
# Disc images: find default.xbe inside an XDVDFS image
def _xdvdfs_module():
    """The proven XDVDFS reader lives in tools/; import it lazily so the core
    module has no import-time dependency on the tools directory layout."""

    try:
        import nfl_uniform_color_xiso_direct_patch as xc  # type: ignore
        return xc
    except ImportError:
        import sys
        tools = Path(__file__).resolve().parents[2] / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        import nfl_uniform_color_xiso_direct_patch as xc  # type: ignore
        return xc


def _open_binary(path: Path, flags: int) -> int:
    return os.open(
        path,
        flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0),
    )


def image_xbe_extent(descriptor: int, size: int) -> tuple[int, int]:
    """(byte offset, size) of default.xbe inside an XDVDFS image.

    Resolved through the image's directory (whatever the game partition's base
    and wherever the file was placed), never assumed from the retail rip."""

    xc = _xdvdfs_module()
    try:
        offset, length = xc.xbe_extent(descriptor, size)
    except xc.PatchError as exc:
        raise ThrowTuningError(f"disc image has no default.xbe: {exc}") from exc
    if length != EXPECTED_XBE_SIZE:
        _require(length in (depth_chart_storage.FILE_SIZE, xbe_space_patch.FILE_SIZE, music_storage.FILE_SIZE, xbe_space_patch.EXT_FILE_SIZE),
                 f"default.xbe inside the image is {length} bytes, not the retail size or a recognised grown size")
        candidate = platform_compat.pread(descriptor, length, offset)
        _require(len(candidate) == length
                 and depth_chart_storage.recognized_grown_xbe(candidate),
                 "larger default.xbe has a foreign or incomplete grown layout")
    return int(offset), int(length)


def _edge_disc_status(descriptor: int, size: int) -> dict[str, object]:
    """Status of the EDGE-rename disc sites (historic-roster names, trivia) in an open image."""

    entries, _directory = _xdvdfs_module().parse_xdvdfs(descriptor, size)
    try:
        return edge_rename_patch.disc_status(descriptor, entries)
    except edge_rename_patch.EdgeRenameError as exc:
        return {"status": "foreign", "reason": str(exc)}


def read_image(image_path: Path | str) -> dict[str, object]:
    path = _resolve_source(image_path)
    descriptor = _open_binary(path, os.O_RDONLY)
    try:
        size = os.fstat(descriptor).st_size
        offset, length = image_xbe_extent(descriptor, size)
        payload = platform_compat.pread(descriptor, length, offset)
        disc_status = _edge_disc_status(descriptor, size)
    finally:
        os.close(descriptor)
    _require(len(payload) == length, "short read of default.xbe from the image")
    curves = read_curves(payload)
    arc_table = read_arc_table(payload)
    return {
        "schema": READ_SCHEMA,
        "container": "xiso",
        "arc_table": arc_table,
        "catch_slider": catch_slider_patch.status(payload),
        "accel_ramp": accel_ramp_patch.status(payload),
        "draft_ai": draft_ai_patch.status(payload),
        "edge_rename": edge_rename_patch.status(payload),
        "edge_rename_disc": disc_status,
        "returner_fix": returner_fix_patch.status(payload),
        "progression": progression_patch.status(payload),
        "scheme_labels": scheme_labels_patch.status(payload),
        "camera": camera_patch.status(payload),
        "kick_rules": kick_rules_patch.status(payload),
        "dynamic_kickoff": dynamic_kickoff_patch.status(payload),
        "dynamic_kickoff_settings": dynamic_kickoff_patch.read_settings(payload),
        "depth_chart_rows": depth_chart_rows_patch.status(payload),
        "practice_squad": practice_squad_patch.status(payload),
        "practice_reserves": practice_reserves_patch.status(payload),
        "depth_locks": depth_locks_patch.status(payload),
        "screen_timing": "unchecked",
        "guardian_cap": _guardian_image_status(path),
        "scorebug_runtime_resources": scorebug_reference.runtime_image_status(path),
        "season_cap": season_cap_patch.status(payload),
        **_allocator_feature_status(payload),
        "xbe_space": xbe_space_patch.status(payload),
        "kickoff_relocated": kickoff_relocated_patch.status(payload),
        "scorebug_runtime": scorebug_runtime_patch.status(payload),
        "scorebug_xbe": scorebug_reference.xbe_status(payload),
        "music_metadata_patch": music_metadata_patch.status(payload),
        **_music_status(payload),
        "kickoff_relocated_settings": kickoff_relocated_patch.read_settings(payload),
        "playoff_picture": playoff_picture_patch.status(payload),
        "kick_power": _kick_power_status(payload),
        "widescreen": widescreen_patch.status(payload),
        "overtime": overtime_patch.status(payload),
        "team_column": team_column_patch.status(payload),
        "seven_on_seven": seven_on_seven_patch.status(payload),
        "position_row": position_row_patch.status(payload),
        "probowl_order": probowl_order_patch.status(payload),
        "penalties": penalties_patch.status(payload),
        "uniform_choice": uniform_choice_patch.status(payload),
        "kick_laces": kick_laces_patch.status(payload),
        "franchise_practice": franchise_practice_patch.status(payload),
        "prospect_names": prospect_names_patch.xbe_status(payload),
        "player_star": player_star_patch.status(payload),
        "boot_logo": boot_logo.status(payload),
        "path": str(path),
        "xbe_byte_offset": offset,
        "xbe_sha256": _digest(payload),
        "matches_retail_sha256": _digest(payload) == RETAIL_XBE_SHA256,
        "curves": curves,
        "settings": infer_settings(curves, str(arc_table["state"])),
    }


def is_disc_image(path: Path | str) -> bool:
    """True when the file looks like an XDVDFS image rather than an XBE.

    The filesystem header is at 0x10000 of the GAME PARTITION, which is byte 0
    of an extracted .xiso but sits 0x18300000 / 0x0FD90000 / 0x02080000 further
    in on a raw disc read.  Checking file offset 0x10000 alone called every raw
    dump "not a disc", so the partition is located the same way every reader
    of the image locates it."""

    path = Path(path)
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except OSError:
        return False
    try:
        if platform_compat.pread(descriptor, 4, 0) == b"XBEH":
            return False
        xc = _xdvdfs_module()
        try:
            xc.locate_xdvdfs_base(descriptor, os.fstat(descriptor).st_size, require_entry=None)
        except xc.PatchError:
            return False
        return True
    except OSError:
        return False
    finally:
        os.close(descriptor)


def read_any(path: Path | str) -> dict[str, object]:
    return read_image(path) if is_disc_image(path) else read_xbe(path)


# --------------------------------------------------------------------------
# Patching
def plan_patch(payload: bytes, wanted: Mapping[str, Sequence[tuple[float, float]]]) -> tuple[bytes, dict[str, object]]:
    """Apply ``wanted`` curves to ``payload`` (an XBE) and return the patched
    bytes plus a receipt.  Curves already equal to the request are skipped; if
    nothing changes the request is refused."""

    _require(bool(wanted), "no curve changes were requested")
    for name in wanted:
        _require(name in EDITABLE_CURVES,
                 f"{name} is not an editable curve ({', '.join(EDITABLE_CURVES)})")
    buf = bytearray(payload)
    sections = _sections(payload)
    changes: list[dict[str, object]] = []
    touched: set[int] = set()
    expected_changed: set[int] = set()
    for name, pairs in wanted.items():
        curve = CURVES[name]
        pairs = validate_pairs(curve, pairs)
        offset = locate_curve(payload, curve)
        before = payload[offset: offset + curve.size]
        after = curve.encode(pairs)
        _require(before[:4] == after[:4], f"{name}: count word would change")
        if before == after:
            continue
        buf[offset: offset + curve.size] = after
        section = _section_for_offset(sections, offset)
        touched.add(section.index)
        expected_changed.update(offset + i for i, (a, b) in enumerate(zip(before, after)) if a != b)
        changes.append({
            "curve": name,
            "va": f"0x{curve.va:x}",
            "file_offset": f"0x{offset:x}",
            "before": curve.decode(before),
            "after": curve.decode(after),
            "before_hex": before.hex(),
            "after_hex": after.hex(),
        })
    _require(bool(changes), "the requested curves already match the file")
    digests: list[dict[str, object]] = []
    for section in sections:
        if section.index not in touched:
            continue
        digest_offset = section.header_offset + 36
        old = bytes(buf[digest_offset: digest_offset + 20])
        new = section_digest(bytes(buf), section)
        buf[digest_offset: digest_offset + 20] = new
        expected_changed.update(digest_offset + i for i, (a, b) in enumerate(zip(old, new)) if a != b)
        digests.append({
            "section_index": section.index,
            "digest_offset": f"0x{digest_offset:x}",
            "before": old.hex(),
            "after": new.hex(),
        })
    patched = bytes(buf)
    actual_changed = {i for i, (a, b) in enumerate(zip(payload, patched)) if a != b}
    _require(len(patched) == len(payload), "patched XBE changed size")
    _require(actual_changed == expected_changed,
             "patched XBE differs outside the requested tables and their section digests")
    receipt = {
        "changes": changes,
        "section_digests": digests,
        "changed_byte_count": len(actual_changed),
    }
    return patched, receipt


def _verify_written(payload: bytes, wanted: Mapping[str, Sequence[tuple[float, float]]]) -> dict[str, object]:
    curves = read_curves(payload)
    for name, pairs in wanted.items():
        got = CURVES[name].decode(CURVES[name].encode(validate_pairs(CURVES[name], pairs)))
        _require(curves[name]["points"] == got, f"post-write read-back disagrees for {name}")
    sections = _sections(payload)
    for section in sections:
        if section.raw_size and any(
            section.raw_offset <= locate_curve(payload, CURVES[n]) < section.raw_offset + section.raw_size
            for n in wanted
        ):
            _require(section_digest(payload, section) == section.stored_digest,
                     f"section {section.index} digest does not match after patching")
    return {name: curves[name]["points"] for name in CURVES}


def _resolve_wanted(settings: TuningSettings | None,
                    curves: Mapping[str, Sequence[tuple[float, float]]] | None) -> dict[str, tuple[tuple[float, float], ...]]:
    _require((settings is None) != (curves is None), "pass exactly one of settings or curves")
    if settings is not None:
        return curves_for(settings)
    assert curves is not None
    return {name: validate_pairs(CURVES[name], pairs) for name, pairs in curves.items()}


def _prepare_target(source: Path, target: Path, overwrite: bool) -> None:
    if target.exists():
        _require(overwrite, f"target already exists; pass overwrite=True to replace it: {target}")
        info = target.lstat()
        _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                 f"target is not a regular file: {target}")
        source_info = source.stat()
        _require((source_info.st_dev, source_info.st_ino) != (info.st_dev, info.st_ino),
                 "source and target are the same file; the target must be a copy")
        target.unlink()
    _require(str(source) != str(target.resolve()), "source and target are the same path")


def _curves_differ(payload: bytes, wanted: Mapping[str, Sequence[tuple[float, float]]]) -> bool:
    for name, pairs in wanted.items():
        curve = CURVES[name]
        offset = locate_curve(payload, curve)
        if payload[offset: offset + curve.size] != curve.encode(validate_pairs(curve, pairs)):
            return True
    return False


class _penalties_adapter:
    """``status``/``apply`` of the penalties patch bound to a profile name (``""`` = off, ``"nfl"`` = the
    estimated NFL-rate profile, or a user .json profile path), so it fits the one-flag-one-module loop."""

    def __init__(self, profile: str) -> None:
        self.profile = profile or penalties_patch.DEFAULT_PROFILE

    def status(self, payload: bytes) -> str:
        return penalties_patch.status(payload, self.profile)

    def apply(self, payload: bytes):
        return penalties_patch.apply(payload, self.profile)


class _prospect_names_adapter:
    """``status``/``apply`` of the prospect-names cave bound to a name source (``""`` = off, ``"modern"`` =
    the shipped CSV, or a user CSV path).  The cave bakes in the boundary of that CSV's pool layout, so an
    executable already carrying the cave with another boundary reads ``foreign`` here (the pool pass
    would refuse it anyway); the boundary is resolved lazily so an idle adapter loads nothing."""

    def __init__(self, source: str) -> None:
        self.source = source
        self._boundary: int | None = None

    def boundary(self) -> int:
        if self._boundary is None:
            self._boundary = prospect_names_patch.layout_for(self.source or "modern").boundary
        return self._boundary

    def status(self, payload: bytes) -> str:
        state = prospect_names_patch.xbe_status(payload)
        if state == "applied" and prospect_names_patch.xbe_boundary(payload) != self.boundary():
            return "foreign"
        return state

    def apply(self, payload: bytes):
        return prospect_names_patch.xbe_apply(payload, self.boundary())


class _dynamic_kickoff_adapter:
    """The dynamic-kickoff module takes four settings; the loop below only knows flag/module pairs.

    Re-applying an already-applied payload validates the requested settings (a mismatch raises rather
    than silently keeping the old ones)."""

    def __init__(self, settings: Mapping[str, object] | None) -> None:
        self.settings = dict(settings or {})

    def status(self, payload: bytes) -> str:
        state = dynamic_kickoff_patch.status(payload)
        if state == "applied":
            dynamic_kickoff_patch.apply(payload, **self.settings)
        return state

    def apply(self, payload: bytes):
        return dynamic_kickoff_patch.apply(payload, **self.settings)


def _selected_space_requests(with_kickoff=False, runtime=False, momentum=0, defensive_try=False, zone_drop_cap=False):
    return ((kickoff_relocated_patch.REQUESTS if with_kickoff else ())
            + (scorebug_runtime_patch.REQUESTS if runtime else ())
            + (momentum_patch.REQUESTS if momentum > 0 else ())
            + (defensive_try_patch.REQUESTS if defensive_try else ())
            + (zone_drop_patch.REQUESTS if zone_drop_cap else ()))


class _xbe_space_adapter:
    def __init__(self, with_kickoff=False, runtime=False, momentum=0, defensive_try=False, zone_drop_cap=False):
        self.requests = _selected_space_requests(with_kickoff, runtime, momentum, defensive_try, zone_drop_cap)

    def status(self, payload):
        state = xbe_space_patch.status(payload)
        if state == "applied":
            xbe_space_patch.apply(payload, self.requests)
        return state

    def apply(self, payload):
        return xbe_space_patch.apply(payload, self.requests)


class _defensive_try_adapter(_xbe_space_adapter):
    def status(self, payload):
        return defensive_try_patch.status(payload)

    def apply(self, payload):
        grown, allocation = xbe_space_patch.apply(payload, self.requests)
        result, receipt = defensive_try_patch.apply(grown)
        return result, {**receipt, "allocation": allocation,
                        "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload)}


class _momentum_adapter:
    def __init__(self, level, contact):
        self.level, self.contact = level, contact

    def status(self, payload):
        return momentum_patch.status(payload)

    def apply(self, payload):
        return momentum_patch.apply(payload, momentum=self.level, momentum_contact=self.contact)


def _allocator_feature_status(payload):
    state = momentum_patch.status(payload)
    settings = momentum_patch.read_settings(payload)
    contact = ("foreign" if state == "foreign" else "applied"
               if state == "applied" and settings.get("momentum_contact") else "retail")
    return {"momentum": state, "momentum_settings": settings, "momentum_contact": contact,
            "defensive_try": defensive_try_patch.status(payload),
            "zone_drop_cap": zone_drop_patch.status(payload),
            "zone_drop_settings": zone_drop_patch.read_settings(payload)}


class _music_metadata_adapter:
    def __init__(self, records):
        self.records = records

    def status(self, payload):
        state = music_metadata_patch.status(payload)
        if state == "applied":
            music_metadata_patch.apply(payload, self.records)
        return state

    def apply(self, payload):
        return music_metadata_patch.apply(payload, self.records)


def _music_status(payload):
    state = music_policy_patch.read_any(payload)
    return {**{key: state.get(key, "foreign") for key in
               ("music_policy", "music_unlock", "music_userlist")},
            "music_state": state["status"]}


def _apply_all(payload: bytes, wanted: Mapping[str, Sequence[tuple[float, float]]] | None,
               catch_slider: bool, accel_ramp: bool = False, draft_ai: bool = False,
               edge_rename: bool = False, returner_fix: bool = False,
               progression: bool = False, scheme_labels: bool = False,
               camera: bool = False, kick_rules: bool = False,
               widescreen: bool = False, overtime: bool = False,
               arc_table: bool = False, kick_power: bool = False,
               team_column: bool = False,
               seven_on_seven: bool = False, position_row: bool = False,
               probowl_order: bool = False, penalties: str = "", uniform_choice: str = "",
               kick_laces: bool = False, franchise_practice: bool = False,
               prospect_names: str = "", player_star: bool = False,
               dynamic_kickoff: bool = False,
               dynamic_kickoff_settings: Mapping[str, object] | None = None,
               depth_chart_rows: bool = False, practice_squad: bool = False,
               depth_locks: bool = False, season_cap: bool = False,
               xbe_space: bool = False, kickoff_relocated: bool = False,
               momentum: int = 0, momentum_contact: bool = False,
               defensive_try: bool = False, zone_drop_cap: bool = False,
               scorebug_runtime: bool = False, music_policy: str = "retail",
               music_unlock: bool = False, music_userlist: bool = False,
               music_metadata=None) -> tuple[bytes, dict[str, object]]:
    """Curves (if any), the relocated arc-by-distance table (if asked), then the catch-slider,
    acceleration-ramp, draft-AI, EDGE-rename, returner and progression patches (if asked)."""

    momentum_patch._settings(momentum, momentum_contact)
    _require(type(defensive_try) is bool and type(zone_drop_cap) is bool, "experimental switches must be boolean")
    legacy_disabled = momentum > 0 and accel_ramp
    if momentum > 0:
        accel_ramp = False
    if kickoff_relocated:
        dynamic_kickoff, xbe_space = True, True
    if dynamic_kickoff:
        # the hold / landing-zone patch sits on the modern kick spots and never on the power-only variant
        kick_rules, kick_power = True, False
    receipt: dict[str, object] = {"changes": [], "section_digests": [], "changed_byte_count": 0}
    receipt["legacy_accel_ramp_disabled_by_momentum_profile"] = legacy_disabled
    patched = payload
    if wanted and (_curves_differ(payload, wanted) or not arc_table):
        patched, receipt = plan_patch(patched, wanted)
    if arc_table:
        state = arc_table_status(patched)
        if state == "retail":
            patched, arc_receipt = apply_arc_table(patched)
            receipt = {**receipt, "arc_table_patch": arc_receipt,
                       "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(arc_receipt["changed_bytes"])}
        else:
            _require(state == "applied", f"arc-by-distance sites are {state}; refusing to patch")
            receipt = {**receipt, "arc_table_patch": {"already_applied": True}}
    if catch_slider:
        state = catch_slider_patch.status(patched)
        if state == "retail":
            patched, catch_receipt = catch_slider_patch.apply(patched)
            receipt = {**receipt, "catch_slider_patch": catch_receipt,
                       "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(catch_receipt["changed_bytes"])}
        else:
            _require(state == "applied", f"catch-slider sites are {state}; refusing to patch")
            receipt = {**receipt, "catch_slider_patch": {"already_applied": True}}
    if accel_ramp:
        state = accel_ramp_patch.status(patched)
        if state == "retail":
            patched, accel_receipt = accel_ramp_patch.apply(patched)
            receipt = {**receipt, "accel_ramp_patch": accel_receipt,
                       "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(accel_receipt["changed_bytes"])}
        else:
            _require(state == "applied", f"acceleration-ramp sites are {state}; refusing to patch")
            receipt = {**receipt, "accel_ramp_patch": {"already_applied": True}}
    if draft_ai:
        state = draft_ai_patch.status(patched)
        if state == "retail":
            patched, draft_receipt = draft_ai_patch.apply(patched)
            receipt = {**receipt, "draft_ai_patch": draft_receipt,
                       "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(draft_receipt["changed_bytes"])}
        else:
            _require(state == "applied", f"draft-AI sites are {state}; refusing to patch")
            receipt = {**receipt, "draft_ai_patch": {"already_applied": True}}
    if edge_rename:
        state = edge_rename_patch.status(patched)
        if state == "retail":
            patched, edge_receipt = edge_rename_patch.apply(patched)
            receipt = {**receipt, "edge_rename_patch": edge_receipt,
                       "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(edge_receipt["changed_bytes"])}
        else:
            _require(state == "applied", f"EDGE-rename sites are {state}; refusing to patch")
            receipt = {**receipt, "edge_rename_patch": {"already_applied": True}}
    if kick_rules or kick_power:
        _require(not (kick_rules and kick_power), "kick_rules and kick_power are exclusive: modern spots (which include the power fix) or power only")
        state = kick_rules_patch.status(patched)
        if kick_power:
            if state == "retail":
                patched, sub_receipt = kick_rules_patch.apply(patched, spots=False)
                receipt = {**receipt, "kick_rules_patch": sub_receipt,
                           "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(sub_receipt["changed_bytes"])}
            else:
                _require(state == "power_only", f"kick-rules sites are {state}; refusing to patch")
                receipt = {**receipt, "kick_rules_patch": {"already_applied": True, "mode": "power_only"}}
        else:
            if state in ("retail", "power_only"):      # apply() upgrades a power-only image to the full patch
                patched, sub_receipt = kick_rules_patch.apply(patched)
                receipt = {**receipt, "kick_rules_patch": sub_receipt,
                           "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(sub_receipt["changed_bytes"])}
            else:
                _require(state == "applied", f"kick-rules sites are {state}; refusing to patch")
                receipt = {**receipt, "kick_rules_patch": {"already_applied": True}}
    for flag, module, key, label in ((returner_fix, returner_fix_patch, "returner_fix_patch", "returner"),
                                     (progression, progression_patch, "progression_patch", "progression"),
                                     (scheme_labels, scheme_labels_patch, "scheme_labels_patch", "scheme-label"),
                                     (camera, camera_patch, "camera_patch", "camera"),
                                     (widescreen, widescreen_patch, "widescreen_patch", "widescreen"),
                                     (overtime, overtime_patch, "overtime_patch", "overtime"),
                                     (team_column, team_column_patch, "team_column_patch", "TEAM-column"),
                                     (seven_on_seven, seven_on_seven_patch, "seven_on_seven_patch", "7-on-7 practice"),
                                     (position_row, position_row_patch, "position_row_patch", "Position row"),
                                     (probowl_order, probowl_order_patch, "probowl_order_patch", "Pro Bowl order"),
                                     (bool(penalties), _penalties_adapter(penalties), "penalties_patch", "penalties"),
                                     (kick_laces, kick_laces_patch, "kick_laces_patch", "kick-laces"),
                                     (franchise_practice, franchise_practice_patch, "franchise_practice_patch", "Franchise-practice"),
                                     (bool(prospect_names), _prospect_names_adapter(prospect_names), "prospect_names_patch", "prospect-names"),
                                     (player_star, player_star_patch, "player_star_patch", "player-star"),
                                     (dynamic_kickoff, _dynamic_kickoff_adapter(dynamic_kickoff_settings), "dynamic_kickoff_patch", "dynamic-kickoff"),
                                     (depth_chart_rows, depth_chart_rows_patch, "depth_chart_rows_patch", "SPECIAL tab"),
                                     (practice_squad, practice_squad_patch, "practice_squad_patch", "practice squad"),
                                     (depth_locks, depth_locks_patch, "depth_locks_patch", "depth locks"),
                                     (season_cap, season_cap_patch, "season_cap_patch", "season cap"),
                                     (music_policy != "retail" or music_unlock or music_userlist,
                                      music_policy_patch.Selection(music_policy, music_unlock, music_userlist),
                                      "music_policy_patch", "music policy")) :
        if not flag:
            continue
        state = module.status(patched)
        # the star patch knows a "legacy" state (the beta-58..60 gate-only version) and upgrades it in place;
        # every other module still only ever goes retail -> applied
        if state == "retail" or (state == "legacy" and key == "player_star_patch"):
            patched, sub_receipt = module.apply(patched)
            if state == "legacy":
                sub_receipt = {**sub_receipt, "upgraded_from": "legacy"}
            receipt = {**receipt, key: sub_receipt,
                       "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(sub_receipt["changed_bytes"])}
        else:
            _require(state == "applied", f"{label} sites are {state}; refusing to patch")
            receipt = {**receipt, key: {"already_applied": True}}
    if practice_squad and franchise_practice:
        # practice-only reserve staging (beta 61): reserves join the disposable practice roster; needs both patches above
        state = practice_reserves_patch.status(patched)
        if state == "retail":
            patched, sub_receipt = practice_reserves_patch.apply(patched)
            receipt = {**receipt, "practice_reserves_patch": sub_receipt,
                       "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(sub_receipt["changed_bytes"])}
        else:
            _require(state == "applied", f"practice-reserves sites are {state}; refusing to patch")
            receipt = {**receipt, "practice_reserves_patch": {"already_applied": True}}
    if uniform_choice:
        _require(uniform_choice in uniform_choice_patch.MODES, f"uniform_choice must be one of {uniform_choice_patch.MODES}, not {uniform_choice!r}")
        state = uniform_choice_patch.status(patched)
        if state == "retail":
            patched, sub_receipt = uniform_choice_patch.apply(patched, uniform_choice)
            receipt = {**receipt, "uniform_choice_patch": sub_receipt,
                       "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(sub_receipt["changed_bytes"])}
        else:
            have = uniform_choice_patch.applied_mode(patched)
            _require(state == "applied" and have == uniform_choice,
                     f"uniform sites are {state}" + (f" ({have} form)" if have else "") + f"; refusing to patch the {uniform_choice} form")
            receipt = {**receipt, "uniform_choice_patch": {"already_applied": True, "mode": uniform_choice}}
    # Caves in the boot-logo bitmap: keep the kernel's logo decodable by pointing the header at a pristine copy
    if boot_logo.needed(patched):
        patched, logo_receipt = boot_logo.apply(patched)
        receipt["boot_logo"] = logo_receipt
    else:
        receipt["boot_logo"] = {"status": boot_logo.status(patched)}
    # Final owners: choose the complete allocation set before the first growth.
    for flag, module, key, label in (
        (defensive_try, _defensive_try_adapter(kickoff_relocated, scorebug_runtime, momentum, defensive_try, zone_drop_cap),
         "defensive_try_patch", "experimental defensive try"),
        (xbe_space or kickoff_relocated or scorebug_runtime or momentum > 0 or defensive_try or zone_drop_cap,
         _xbe_space_adapter(kickoff_relocated, scorebug_runtime, momentum, defensive_try, zone_drop_cap),
         "xbe_space_patch", "experimental executable space"),
        (kickoff_relocated, kickoff_relocated_patch,
         "kickoff_relocated_patch", "experimental relocated kickoff"),
        (scorebug_runtime, scorebug_runtime_patch, "scorebug_runtime_patch", "experimental scorebug effects"),
        (momentum > 0, _momentum_adapter(momentum, momentum_contact), "momentum_patch", "experimental player momentum"),
        (zone_drop_cap, zone_drop_patch, "zone_drop_patch", "experimental initial corner deep-zone cap"),
        (music_metadata is not None, _music_metadata_adapter(music_metadata),
         "music_metadata_patch", "music library titles"),
    ):
        if not flag:
            continue
        state = module.status(patched)
        _require(state in ("retail", "applied"), f"{label} is {state}; refusing")
        patched, sub_receipt = module.apply(patched)
        receipt[key] = sub_receipt
        receipt["changed_byte_count"] = int(receipt.get("changed_byte_count", 0)) + int(sub_receipt["changed_bytes"])
    receipt["legacy_accel_ramp_disabled_by_momentum_profile"] = bool(legacy_disabled)
    return patched, receipt


def write_xbe_copy(
    source_xbe: Path | str,
    target_xbe: Path | str,
    *,
    settings: TuningSettings | None = None,
    curves: Mapping[str, Sequence[tuple[float, float]]] | None = None,
    overwrite: bool = False,
    catch_slider: bool = False,
    accel_ramp: bool = False,
    draft_ai: bool = False,
    edge_rename: bool = False,
    returner_fix: bool = False,
    progression: bool = False,
    scheme_labels: bool = False,
    camera: bool = False,
    kick_rules: bool = False,
    widescreen: bool = False,
    overtime: bool = False,
    kick_power: bool = False,
    team_column: bool = False,
    seven_on_seven: bool = False,
    position_row: bool = False,
    probowl_order: bool = False,
    penalties: str = "",
    uniform_choice: str = "",
    kick_laces: bool = False,
    franchise_practice: bool = False,
    prospect_names: str = "",
    player_star: bool = False,
    dynamic_kickoff: bool = False,
    dynamic_kickoff_settings: Mapping[str, object] | None = None,
    depth_chart_rows: bool = False,
    practice_squad: bool = False,
    depth_locks: bool = False,
    season_cap: bool = False,
    xbe_space: bool = False,
    kickoff_relocated: bool = False,
    momentum: int = 0, momentum_contact: bool = False,
    defensive_try: bool = False, zone_drop_cap: bool = False,
    scorebug_runtime: bool = False,
    music_policy: str = "retail",
    music_unlock: bool = False,
    music_userlist: bool = False,
    music_metadata=None,
) -> dict[str, object]:
    """Write a patched COPY of ``source_xbe`` to ``target_xbe``."""

    wanted = _resolve_wanted(settings, curves) if (settings is not None or curves is not None) else None
    _require(wanted is not None or catch_slider or accel_ramp or draft_ai or edge_rename or returner_fix or progression or scheme_labels or camera or kick_rules or kick_power or widescreen or overtime or team_column or seven_on_seven or position_row or probowl_order or penalties or uniform_choice or kick_laces or franchise_practice or bool(prospect_names) or player_star or dynamic_kickoff or depth_chart_rows or practice_squad or depth_locks or season_cap or xbe_space or kickoff_relocated or scorebug_runtime or momentum > 0 or momentum_contact or defensive_try or zone_drop_cap or music_policy != "retail" or music_unlock or music_userlist or music_metadata is not None,
             "nothing requested")
    source = _resolve_source(source_xbe)
    target = Path(target_xbe).expanduser()
    _prepare_target(source, target, overwrite)
    original = source.read_bytes()
    arc_table = settings is not None and settings.arc_by_distance
    patched, receipt = _apply_all(original, wanted, catch_slider, accel_ramp, draft_ai, edge_rename, returner_fix, progression, scheme_labels, camera, kick_rules, widescreen, overtime, arc_table=arc_table, kick_power=kick_power, team_column=team_column, seven_on_seven=seven_on_seven, position_row=position_row, probowl_order=probowl_order, penalties=penalties, uniform_choice=uniform_choice, kick_laces=kick_laces, franchise_practice=franchise_practice, prospect_names=prospect_names, player_star=player_star, dynamic_kickoff=dynamic_kickoff, dynamic_kickoff_settings=dynamic_kickoff_settings, depth_chart_rows=depth_chart_rows, practice_squad=practice_squad, depth_locks=depth_locks, season_cap=season_cap, xbe_space=xbe_space, kickoff_relocated=kickoff_relocated, scorebug_runtime=scorebug_runtime, momentum=momentum, momentum_contact=momentum_contact, defensive_try=defensive_try, zone_drop_cap=zone_drop_cap, music_policy=music_policy, music_unlock=music_unlock, music_userlist=music_userlist, music_metadata=music_metadata)
    _require(patched != original, "nothing to write: the requested curves and patches already match the file")
    descriptor = _open_binary(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        view = memoryview(patched)
        written = 0
        while written < len(patched):
            written += os.write(descriptor, view[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    result = target.read_bytes()
    _require(result == patched, "target read-back differs from the patched bytes")
    verified = _verify_written(result, wanted or {})
    arc_state = arc_table_status(result)
    if arc_table:
        _require(arc_state == "applied", "arc-by-distance table did not read back as applied")
    preview_curves = {n: verified[n] for n in EDITABLE_CURVES}
    if arc_state == "applied":
        preview_curves["lobspeed"] = ARC_BY_DISTANCE_LOBSPEED
    return {
        "schema": WRITE_SCHEMA,
        "container": "xbe",
        "arc_table": arc_state,
        "catch_slider": catch_slider_patch.status(result),
        "accel_ramp": accel_ramp_patch.status(result),
        "draft_ai": draft_ai_patch.status(result),
        "edge_rename": edge_rename_patch.status(result),
        "returner_fix": returner_fix_patch.status(result),
        "progression": progression_patch.status(result),
        "scheme_labels": scheme_labels_patch.status(result),
        "camera": camera_patch.status(result),
        "kick_rules": kick_rules_patch.status(result),
        "dynamic_kickoff": dynamic_kickoff_patch.status(result),
        "dynamic_kickoff_settings": dynamic_kickoff_patch.read_settings(result),
        "depth_chart_rows": depth_chart_rows_patch.status(result),
        "practice_squad": practice_squad_patch.status(result),
        "practice_reserves": practice_reserves_patch.status(result),
        "depth_locks": depth_locks_patch.status(result),
        "screen_timing": "n/a",
        "guardian_cap": "n/a",
        "season_cap": season_cap_patch.status(result),
        **_allocator_feature_status(result),
        "xbe_space": xbe_space_patch.status(result),
        "kickoff_relocated": kickoff_relocated_patch.status(result),
        "scorebug_runtime": scorebug_runtime_patch.status(result),
        "scorebug_xbe": scorebug_reference.xbe_status(result),
        "music_metadata_patch": music_metadata_patch.status(result),
        **_music_status(result),
        "kickoff_relocated_settings": kickoff_relocated_patch.read_settings(result),
        "playoff_picture": playoff_picture_patch.status(result),
        "kick_power": _kick_power_status(result),
        "widescreen": widescreen_patch.status(result),
        "overtime": overtime_patch.status(result),
        "team_column": team_column_patch.status(result),
        "seven_on_seven": seven_on_seven_patch.status(result),
        "position_row": position_row_patch.status(result),
        "probowl_order": probowl_order_patch.status(result),
        "penalties": penalties_patch.status(result),
        "uniform_choice": uniform_choice_patch.status(result),
        "kick_laces": kick_laces_patch.status(result),
        "franchise_practice": franchise_practice_patch.status(result),
        "prospect_names": prospect_names_patch.xbe_status(result),
        "player_star": player_star_patch.status(result),
        "boot_logo": boot_logo.status(result),
        "source": {"path": str(source), "sha256": _digest(original),
                   "matches_retail_sha256": _digest(original) == RETAIL_XBE_SHA256},
        "target": {"path": str(target), "sha256": _digest(result)},
        "settings": None if settings is None else {"max_deep_yards": settings.max_deep_yards, "arc": settings.arc, "realistic_flight": settings.realistic_flight, "arc_by_distance": settings.arc_by_distance},
        "curves_requested": {name: list(pairs) for name, pairs in (wanted or {}).items()},
        **receipt,
        "verified_curves": verified,
        "preview": [row.__dict__ for row in preview(preview_curves)],
        "signature_status": (
            "RSA signature left stale; patched XBE is xemu-only (xemu enforces no "
            "XBE integrity). Real hardware needs a resign this tool cannot produce."
        ),
    }


_COPY_CHUNK = 32 * 1024 * 1024


def _transactional_image_writer(writer):
    from functools import wraps
    import tempfile

    @wraps(writer)
    def write(source_image, target_image, **kwargs):
        source = Path(source_image).resolve(strict=True)
        target = Path(target_image).absolute()
        _require(not target.is_symlink(), "target is not a regular file")
        _require(source != target.resolve() and not (target.exists() and os.path.samefile(source, target)),
                 "source and target are the same file")
        _require(not target.exists() or kwargs.get("overwrite", False), "target already exists")
        with tempfile.TemporaryDirectory(prefix=".xbe-disc-", dir=target.parent) as folder:
            stage = Path(folder) / target.name
            receipt = writer(source, stage, **{**kwargs, "overwrite": False})
            os.replace(stage, target)
            receipt["target"]["path"] = str(target)
            return receipt
    return write


@_transactional_image_writer
def write_image_copy(
    source_image: Path | str,
    target_image: Path | str,
    *,
    settings: TuningSettings | None = None,
    curves: Mapping[str, Sequence[tuple[float, float]]] | None = None,
    overwrite: bool = False,
    progress: ProgressSink | None = None,
    catch_slider: bool = False,
    accel_ramp: bool = False,
    draft_ai: bool = False,
    edge_rename: bool = False,
    returner_fix: bool = False,
    progression: bool = False,
    scheme_labels: bool = False,
    camera: bool = False,
    kick_rules: bool = False,
    widescreen: bool = False,
    overtime: bool = False,
    kick_power: bool = False,
    team_column: bool = False,
    seven_on_seven: bool = False,
    position_row: bool = False,
    probowl_order: bool = False,
    penalties: str = "",
    uniform_choice: str = "",
    kick_laces: bool = False,
    franchise_practice: bool = False,
    prospect_names: str = "",
    player_star: bool = False,
    dynamic_kickoff: bool = False,
    dynamic_kickoff_settings: Mapping[str, object] | None = None,
    depth_chart_rows: bool = False,
    practice_squad: bool = False,
    depth_locks: bool = False,
    season_cap: bool = False,
    xbe_space: bool = False,
    kickoff_relocated: bool = False,
    momentum: int = 0, momentum_contact: bool = False,
    defensive_try: bool = False, zone_drop_cap: bool = False,
    scorebug_runtime: bool = False,
    music_policy: str = "retail",
    music_unlock: bool = False,
    music_userlist: bool = False,
    music_metadata=None,
) -> dict[str, object]:
    """Copy a disc image and patch ``default.xbe`` inside the COPY.

    The source is opened read-only and never written.  The copy is byte-exact
    except for the curve tables and the touched section digest of the embedded
    XBE; the receipt lists every changed range.
    """

    momentum_patch._settings(momentum, momentum_contact)
    _require(type(defensive_try) is bool and type(zone_drop_cap) is bool, "experimental switches must be boolean")
    legacy_disabled = momentum > 0 and accel_ramp
    if momentum > 0:
        accel_ramp = False
    wanted = _resolve_wanted(settings, curves) if (settings is not None or curves is not None) else None
    _require(wanted is not None or catch_slider or accel_ramp or draft_ai or edge_rename or returner_fix or progression or scheme_labels or camera or kick_rules or kick_power or widescreen or overtime or team_column or seven_on_seven or position_row or probowl_order or penalties or uniform_choice or kick_laces or franchise_practice or bool(prospect_names) or player_star or dynamic_kickoff or depth_chart_rows or practice_squad or depth_locks or season_cap or xbe_space or kickoff_relocated or scorebug_runtime or momentum > 0 or momentum_contact or defensive_try or zone_drop_cap or music_policy != "retail" or music_unlock or music_userlist or music_metadata is not None,
             "nothing requested")
    source = _resolve_source(source_image)
    target = Path(target_image).expanduser()
    _prepare_target(source, target, overwrite)
    report: ProgressSink = progress or (lambda stage, done, total: None)

    src = _open_binary(source, os.O_RDONLY)
    try:
        size = os.fstat(src).st_size
        offset, length = image_xbe_extent(src, size)
        original = platform_compat.pread(src, length, offset)
        _require(len(original) == length, "short read of default.xbe from the source image")
        arc_table = settings is not None and settings.arc_by_distance
        patched, receipt = _apply_all(original, wanted, catch_slider, accel_ramp, draft_ai, edge_rename, returner_fix, progression, scheme_labels, camera, kick_rules, widescreen, overtime, arc_table=arc_table, kick_power=kick_power, team_column=team_column, seven_on_seven=seven_on_seven, position_row=position_row, probowl_order=probowl_order, penalties=penalties, uniform_choice=uniform_choice, kick_laces=kick_laces, franchise_practice=franchise_practice, prospect_names=prospect_names, player_star=player_star, dynamic_kickoff=dynamic_kickoff, dynamic_kickoff_settings=dynamic_kickoff_settings, depth_chart_rows=depth_chart_rows, practice_squad=practice_squad, depth_locks=depth_locks, season_cap=season_cap, xbe_space=xbe_space and not scorebug_runtime, kickoff_relocated=kickoff_relocated and not scorebug_runtime, scorebug_runtime=False, momentum=0 if scorebug_runtime else momentum, momentum_contact=False if scorebug_runtime else momentum_contact, defensive_try=defensive_try and not scorebug_runtime, zone_drop_cap=zone_drop_cap and not scorebug_runtime, music_policy=music_policy, music_unlock=music_unlock, music_userlist=music_userlist, music_metadata=None if scorebug_runtime else music_metadata)
        entries: dict[str, object] = {}
        disc_before: dict[str, object] = {}
        if edge_rename:
            entries, _directory = _xdvdfs_module().parse_xdvdfs(src, size)
            disc_before = edge_rename_patch.disc_status(src, entries)
        _require(scorebug_runtime or patched != original or disc_before.get("status") == "retail",
                 "nothing to write: the requested curves and patches already match the image")
        dst = _open_binary(target, os.O_RDWR | os.O_CREAT | os.O_EXCL)   # read-write: the disc text pass verifies as it goes
        try:
            copied = 0
            while copied < size:
                chunk = platform_compat.pread(src, min(_COPY_CHUNK, size - copied), copied)
                _require(bool(chunk), "source image shrank during the copy")
                view = memoryview(chunk)
                done = 0
                while done < len(chunk):
                    done += os.write(dst, view[done:])
                copied += len(chunk)
                report("Copying disc image", copied, size)
            ranges: list[tuple[int, int]] = []
            i = 0
            while i < len(original):
                if original[i] != patched[i]:
                    j = i
                    while j < len(original) and original[j] != patched[j]:
                        j += 1
                    ranges.append((i, j))
                    i = j
                else:
                    i += 1
            xbe_relocation: dict[str, object] | None = None
            if len(patched) != EXPECTED_XBE_SIZE:
                # Validate recognized growth and transactional same-size replays.
                xbe_relocation = depth_chart_storage.write_image_xbe(dst, patched)
            else:
                for a, b in ranges:
                    written = platform_compat.pwrite(dst, patched[a:b], offset + a)
                    _require(written == b - a, "short write while patching the copy")
            disc_receipt: dict[str, object] | None = None
            if edge_rename:
                report("Renaming Def End players and trivia text in the copy", 0, 0)
                disc_receipt = edge_rename_patch.apply_disc(dst, entries, platform_compat.pwrite)
            os.fsync(dst)
        finally:
            os.close(dst)
    finally:
        os.close(src)
    report("Verifying the patched copy", 0, 0)
    check = _open_binary(target, os.O_RDONLY)
    try:
        grown = int(xbe_relocation["image_growth"]) if xbe_relocation else 0
        actual_size = os.fstat(check).st_size
        _require(actual_size == size + grown, "copied image has the wrong size")
        after_offset, after_length = image_xbe_extent(check, actual_size)
        after = platform_compat.pread(check, after_length, after_offset)
    finally:
        os.close(check)
    _require(after == patched, "patched default.xbe read-back differs inside the copy")
    if xbe_relocation is not None:
        receipt = {**receipt, "xbe_relocation": xbe_relocation}
    if disc_receipt is not None:
        check = _open_binary(target, os.O_RDONLY)
        try:
            disc_after = edge_rename_patch.disc_status(check, entries)
        finally:
            os.close(check)
        _require(disc_after == disc_receipt["after"], "EDGE disc sites read back differently inside the copy")
        receipt = {**receipt, "edge_rename_disc_patch": disc_receipt,
                   "changed_byte_count": int(receipt.get("changed_byte_count", 0)) + int(disc_receipt["changed_bytes"])}
    if scorebug_runtime:
        runtime_receipt = scorebug_reference.runtime_apply_in_place(target, with_kickoff=kickoff_relocated,
            extra_requests=_selected_space_requests(momentum=momentum, defensive_try=defensive_try, zone_drop_cap=zone_drop_cap))
        receipt["scorebug_runtime_patch"] = runtime_receipt
        with target.open("r+b") as stream:
            fd = stream.fileno()
            off, size = _xdvdfs_module().xbe_extent(fd, os.fstat(fd).st_size)
            from . import platform_compat as io, nfl2k5_depth_chart_storage as storage
            final, extra = _apply_all(io.pread(fd, size, off), None, False,
                xbe_space=True, kickoff_relocated=kickoff_relocated, scorebug_runtime=True,
                momentum=momentum, momentum_contact=momentum_contact, defensive_try=defensive_try,
                zone_drop_cap=zone_drop_cap, music_metadata=music_metadata)
            storage.write_image_xbe(fd, final)
        receipt.update({key: value for key, value in extra.items() if key != "scorebug_runtime_patch"})
        check = _open_binary(target, os.O_RDONLY)
        try:
            actual_size = os.fstat(check).st_size
            after_offset, after_length = image_xbe_extent(check, actual_size)
            after = platform_compat.pread(check, after_length, after_offset)
        finally:
            os.close(check)
    receipt["legacy_accel_ramp_disabled_by_momentum_profile"] = bool(legacy_disabled)
    verified = _verify_written(after, wanted or {})
    arc_state = arc_table_status(after)
    if arc_table:
        _require(arc_state == "applied", "arc-by-distance table did not read back as applied inside the copy")
    preview_curves = {n: verified[n] for n in EDITABLE_CURVES}
    if arc_state == "applied":
        preview_curves["lobspeed"] = ARC_BY_DISTANCE_LOBSPEED
    return {
        "schema": WRITE_SCHEMA,
        "container": "xiso",
        "arc_table": arc_state,
        "catch_slider": catch_slider_patch.status(after),
        "accel_ramp": accel_ramp_patch.status(after),
        "draft_ai": draft_ai_patch.status(after),
        "edge_rename": edge_rename_patch.status(after),
        "edge_rename_disc": disc_receipt["after"] if disc_receipt is not None else disc_before or None,
        "returner_fix": returner_fix_patch.status(after),
        "progression": progression_patch.status(after),
        "scheme_labels": scheme_labels_patch.status(after),
        "camera": camera_patch.status(after),
        "kick_rules": kick_rules_patch.status(after),
        "dynamic_kickoff": dynamic_kickoff_patch.status(after),
        "dynamic_kickoff_settings": dynamic_kickoff_patch.read_settings(after),
        "depth_chart_rows": depth_chart_rows_patch.status(after),
        "practice_squad": practice_squad_patch.status(after),
        "practice_reserves": practice_reserves_patch.status(after),
        "depth_locks": depth_locks_patch.status(after),
        "screen_timing": "unchecked",
        "guardian_cap": _guardian_image_status(target),
        "scorebug_runtime_resources": scorebug_reference.runtime_image_status(target),
        "season_cap": season_cap_patch.status(after),
        **_allocator_feature_status(after),
        "xbe_space": xbe_space_patch.status(after),
        "kickoff_relocated": kickoff_relocated_patch.status(after),
        "scorebug_runtime": scorebug_runtime_patch.status(after),
        "scorebug_xbe": scorebug_reference.xbe_status(after),
        "music_metadata_patch": music_metadata_patch.status(after),
        **_music_status(after),
        "kickoff_relocated_settings": kickoff_relocated_patch.read_settings(after),
        "playoff_picture": playoff_picture_patch.status(after),
        "kick_power": _kick_power_status(after),
        "widescreen": widescreen_patch.status(after),
        "overtime": overtime_patch.status(after),
        "team_column": team_column_patch.status(after),
        "seven_on_seven": seven_on_seven_patch.status(after),
        "position_row": position_row_patch.status(after),
        "probowl_order": probowl_order_patch.status(after),
        "penalties": penalties_patch.status(after),
        "uniform_choice": uniform_choice_patch.status(after),
        "kick_laces": kick_laces_patch.status(after),
        "franchise_practice": franchise_practice_patch.status(after),
        "prospect_names": prospect_names_patch.xbe_status(after),
        "player_star": player_star_patch.status(after),
        "boot_logo": boot_logo.status(after),
        "source": {"path": str(source), "size": size, "xbe_sha256": _digest(original),
                   "xbe_matches_retail_sha256": _digest(original) == RETAIL_XBE_SHA256},
        "target": {"path": str(target), "size": actual_size, "xbe_sha256": _digest(after)},
        "xbe_byte_offset": offset,
        "written_ranges": [{"xbe_offset": f"0x{a:x}", "image_offset": f"0x{offset + a:x}", "length": b - a}
                           for a, b in ranges],
        "settings": None if settings is None else {"max_deep_yards": settings.max_deep_yards, "arc": settings.arc, "realistic_flight": settings.realistic_flight, "arc_by_distance": settings.arc_by_distance},
        "curves_requested": {name: list(pairs) for name, pairs in (wanted or {}).items()},
        **receipt,
        "verified_curves": verified,
        "preview": [row.__dict__ for row in preview(preview_curves)],
        "signature_status": (
            "RSA signature left stale; the patched image is xemu-only (xemu enforces "
            "no XBE integrity). Real hardware needs a resign this tool cannot produce."
        ),
    }


def write_copy(source: Path | str, target: Path | str, **kwargs) -> dict[str, object]:
    """Dispatch on the source container (XBE or disc image)."""

    if is_disc_image(source):
        return write_image_copy(source, target, **kwargs)
    kwargs.pop("progress", None)
    return write_xbe_copy(source, target, **kwargs)


__all__ = [
    "ARC_BY_DISTANCE_LOBSPEED",
    "ARC_TABLE_CURVE",
    "ARC_TABLE_VA",
    "CURVES",
    "Curve",
    "EDITABLE_CURVES",
    "LEGACY_ARC_BY_DISTANCE_LOBSPEED",
    "LOBSPEED_COUNT_SITE_VA",
    "LOBSPEED_PAIRS_SITE_VA",
    "RETAIL_ARC_TABLE_SLOT",
    "apply_arc_table",
    "arc_table_status",
    "effective_lobspeed",
    "read_arc_table",
    "EXPECTED_XBE_SIZE",
    "GRAVITY_YD_S2",
    "MAX_MAX_DEEP_YARDS",
    "MIN_MAX_DEEP_YARDS",
    "PREVIEW_ARMS",
    "PreviewRow",
    "REALISTIC_LOBSPEED",
    "READ_SCHEMA",
    "RETAIL_MAX_DEEP_YARDS",
    "RETAIL_XBE_SHA256",
    "ThrowTuningError",
    "TuningSettings",
    "WRITE_SCHEMA",
    "YD_CM",
    "curves_for",
    "infer_settings",
    "interpolate",
    "is_disc_image",
    "locate_curve",
    "plan_patch",
    "preview",
    "read_any",
    "read_curves",
    "read_image",
    "read_xbe",
    "validate_pairs",
    "write_copy",
    "write_image_copy",
    "write_xbe_copy",
]
