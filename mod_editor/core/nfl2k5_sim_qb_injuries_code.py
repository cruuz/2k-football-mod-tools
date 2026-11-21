"""Relocatable 128 MiB scheduled-franchise QB rules. The native selector and medical writes come from the user's game.

The weekly scheduler and Gamecast enter through the same fixture guard. The completion caller alone uses the
franchise gain curve. The original escape and zero-yard callers keep the standard simulator's converter.
The template and its relocations are generated from the assembly and C in tools/qb_sim_injuries.

Slice 2 (positions.S at bank offset 0x1400) adds one private check per simulated franchise scrimmage play for the
tackles, guards, center, defensive ends and the ball-carrying halfback, through second linked copies of the game's own
diagnosis and duration code and the game's own health write (pos2/DESIGN.md sections 2 and 4.1). Slice 3 extends the
same check to receivers, tight ends, fullbacks, defensive tackles, linebackers, cornerbacks and safeties, with an
exposure rule and weight per walked slot and acceptance stored by week group (pos3/DESIGN.md sections 1 and 2).

Long-franchise stability (stability.S at bank offset 0x1C00; pos3/DESIGN.md addendum "Long-franchise stability")
multiplies each class's threshold, the quarterback's included, by a factor that is exactly 1.0 in a franchise's first
two seasons and from its third follows the league's Durability ratings (mode "adaptive") or the season index (mode
"year", the interim). The factor lives in bank RAM only; no save byte depends on it.
"""
from __future__ import annotations

from hashlib import sha256
import struct
from typing import Callable, NamedTuple

CODE_SIZE = 0x4000
MARK_OFFSET = 0x3FC0
MARK_SIZE = struct.calcsize("<8sIII")
MARK_SIGNATURE = b"QBMEDv4\0"      # Settings record <8sIII> (signature, mode, rate, 0). Slices 1, 2, 3 wrote v1, v2, v3.
DEFAULT_RATE = 310                  # Base probability numerator per 100,000 eligible opportunities.
RATE_DENOMINATOR = 100_000
REFERENCE_DURABILITY = 74.72222222222223
GAIN_TABLE = 0x3B00
GAIN_CONSTANTS = 0x3D80
LENGTH_ACCEPT = ((1, 507082694), (2, 601295421), (3, 1503238554), (4, 196716059),
                 (7, 149245968), (8, 195151244), (14, 348438850), (255, 2050967529))

# Both high-level callers, the Gamecast screen reset, and the three ordinary/sack/escape medical calls.
_FIXED_CALLS = (
    ("weekly_entry", 0x10B95A, 0x10B280, "match_entry"),
    ("gamecast_entry", 0xEC007, 0x10B280, "match_entry"),
    ("gamecast_screen", 0xEBF46, 0x6C780, "gamecast_screen_entry"),
    ("rush", 0x1081E3, 0x1028B0, "medical"),
    ("pass", 0x10904A, 0x1028B0, "medical"),
    ("sack_escape", 0x108A02, 0x1028B0, "medical"),
)
CONTEST_SITE = 0x108B12
COMPLETION_SITE = 0x1094E4
# The running-back owner's weekly roll jumps from the tail of the weekly health tick. While slice 2 covers halfbacks
# per carry, the tail is put back to the game's own bytes (pos2/DESIGN.md section 2, "Halfback weekly roll").
WEEKLY_HALFBACK_SITE = 0x133CC9
WEEKLY_HALFBACK_ORIGINAL = bytes.fromhex("5f5e5bc390")
FIXED_SPANS = tuple((at, 5) for _, at, _, _ in _FIXED_CALLS) + (
    (CONTEST_SITE, 6), (COMPLETION_SITE, 5), (WEEKLY_HALFBACK_SITE, 5))


class PositionClass(NamedTuple):
    name: str
    base_chance: int            # chance per exposed play, per POSITION_SCALE, at reference Durability and slider 0.5
    reference_durability: int
    zero_point: int             # Durability at or above this is immune
    accept: tuple               # (last assigned week of the run, probability the diagnosis is kept), weeks 0 to 31


POSITION_SCALE = 100_000_000
POSITION_WEEKS = 32               # assigned weeks 0 to 31; longer runs use week 31's group
# Acceptance is stored by week group (pos3/DESIGN.md section 2): every class's pairs end exactly at these weeks, and
# pos_week_group in positions.S maps weeks 0 to 31 to the six groups.
ACCEPT_WEEK_BOUNDARIES = (1, 2, 3, 7, 15, 31)
POSITION_WEEK_GROUPS = tuple(next(group for group, last in enumerate(ACCEPT_WEEK_BOUNDARIES) if week <= last)
                             for week in range(POSITION_WEEKS))
# Order is the class index in positions.S (pos_slots). Refit after the independent review (rev-pos2 H1): absences are
# counted by the NFL study's rule (a listed injured player who did not play counts, whatever the status code); frozen
# after refit round R3 on roots 2501-2508 (pos2/refit/r3/constants.json). Calibration changed only base_chance and
# accept; zero_point and reference_durability are the design's.
POSITION_CLASSES = (
    PositionClass("tackle", 637_000, 93, 110,
                  ((1, 0.226), (2, 0.269), (3, 0.6139), (7, 0.0545), (15, 0.1845), (31, 1.0))),
    PositionClass("guard", 287_000, 91, 110,
                  ((1, 0.1177), (2, 0.1401), (3, 1.0), (7, 0.0), (15, 0.0), (31, 0.1151))),
    PositionClass("center", 322_000, 91, 110,
                  ((1, 0.1778), (2, 0.2117), (3, 0.4419), (7, 0.0), (15, 0.0271), (31, 1.0))),
    PositionClass("end", 220_000, 81, 100,
                  ((1, 0.0925), (2, 0.1101), (3, 1.0), (7, 0.0), (15, 0.0), (31, 0.8354))),
    PositionClass("halfback", 1_852_000, 83, 100,
                  ((1, 0.098), (2, 0.1166), (3, 0.8052), (7, 0.023), (15, 0.0414), (31, 1.0))),
    # Slice 3: frozen after its new round 2 on the refit slice 2, absences counted by the NFL study's rule
    # (pos3/calib/nr2/constants.json; pos3/DESIGN_CHANGES.md). Calibration changed only base_chance and accept.
    PositionClass("receiver", 253_000, 78, 100,
                  ((1, 0.2932), (2, 0.349), (3, 1.0), (7, 0.0), (15, 0.0), (31, 0.9481))),
    PositionClass("tight_end", 355_000, 80, 100,
                  ((1, 0.1076), (2, 0.1281), (3, 0.5404), (7, 0.0), (15, 0.0), (31, 1.0))),
    PositionClass("fullback", 148_000, 85, 105,
                  ((1, 0.2179), (2, 0.2594), (3, 1.0), (7, 0.0043), (15, 0.0531), (31, 0.1907))),
    PositionClass("defensive_tackle", 227_000, 80, 100,
                  ((1, 0.1443), (2, 0.1718), (3, 0.582), (7, 0.0), (15, 0.0111), (31, 1.0))),
    PositionClass("linebacker", 315_000, 79, 100,
                  ((1, 0.1493), (2, 0.1778), (3, 0.7243), (7, 0.0), (15, 0.0), (31, 1.0))),
    PositionClass("cornerback", 415_000, 78, 100,
                  ((1, 0.2413), (2, 0.2872), (3, 0.7744), (7, 0.0), (15, 0.097), (31, 1.0))),
    PositionClass("safety", 316_000, 78, 100,
                  ((1, 0.2948), (2, 0.351), (3, 0.9101), (7, 0.0), (15, 0.0), (31, 1.0))),
)
# False is the cut-line fallback of pos2/DESIGN.md section 8: no per-carry halfback chance, weekly roll left as it is.
HALFBACK_SUPPLEMENT = True

# Long-franchise stability (pos3/DESIGN.md addendum A.2, A.4, A.6). Thirteen classes: POSITION_CLASSES in order, then
# the quarterback (its gate in clinical.S reads the thirteenth factor).
STABILITY_MODES = {"off": 0, "year": 1, "adaptive": 2}
STABILITY_MODE = "adaptive"
STABILITY_CLASS_NAMES = tuple(position.name for position in POSITION_CLASSES) + ("quarterback",)
QUARTERBACK_ZERO_POINT = 100        # the quarterback tables scale with max(0, 100 - Durability)
STABILITY_ZERO_POINTS = tuple(position.zero_point for position in POSITION_CLASSES) + (QUARTERBACK_ZERO_POINT,)
# R per class: the league mean of max(0, K - Durability) over depth-chart starters (stored position in the class,
# stored depth rank below the starter count) at the confirmed calibration. Measured by order S0 on the slice 3
# confirmation candidate seasons, roots 64001 to 64004, 2026 and 2027, Durability from each season's signed save
# (pos3/work/stability/reference.py, reference.json, reference.txt).
STABILITY_REFERENCE = (17.627, 18.847, 18.803, 19.526, 17.703, 22.138, 20.803, 21.261, 20.343, 20.551, 23.144, 21.840,
                       25.807)
STABILITY_YEAR_SLOPE = 0.055        # mode "year": the supplement's measured 24 to 25 percent over four offseasons
STABILITY_SEASONS = 10              # stab_year entries by season index; later seasons use the last
STABILITY_CLASSES_OFF = ()          # class names left at 1.0 by the tracking gate (adaptive mode only)
# stab_class in stability.S, by stored position QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE (0xFF: not counted).
STABILITY_POSITION_CLASS = (12, None, None, 5, 10, 11, 11, 4, 7, 6, 9, 9, 2, 1, 0, 8, 3)
# The references follow the roster on the disc (stability review rev-pos3/REVIEW_STABILITY.md, Medium finding). R above
# is the level of one roster, the base disc's (ROST body sha256 70813bd9). A disc built with another roster (a player's
# edits, a total conversion, a roster update) would otherwise get a step at season 3 that is the roster difference, not
# drift. So the Studio measures each class's static statistic on the disc's own roster with stability.S's starter rule
# (clubs 0-31, listed players, stored position in the class, stored depth rank below the count; mean of
# max(0, K - Durability)) and writes R x static(disc) / static(calibration roster) per class. STABILITY_CALIBRATION is
# that static statistic of roster 70813bd9 as (sum, starters) per class; on that roster every reference is exactly R.
STABILITY_CALIBRATION_ROSTER = "70813bd95d1265b40009fb611569e2e1ffcce02bf17a5f73476e8f55ffa3d157"
STABILITY_CALIBRATION = ((1077, 64), (1253, 64), (576, 32), (1210, 64), (1060, 64), (2168, 96), (654, 32), (385, 19),
                         (1288, 64), (2011, 96), (2147, 96), (1369, 64), (821, 32))
STABILITY_CLUBS = 32                # stability.S CLUBS
STABILITY_MAX_LISTED = 0x41         # stability.S MAX_LISTED: a larger count is not a club record
STABILITY_MIN_STARTERS = 8          # stability.S MIN_STARTERS: fewer starters leave the class at 1.0
# A derived reference outside this factor of the frozen R is a measurement that looks wrong (the Studio then installs the
# frozen R). On the shipped roster an even Durability change from +10 to -15 points stays inside (factors 0.41 to 1.91);
# the factor clamp (0.35 to 1.25) bounds what any reference inside it can do.
STABILITY_REFERENCE_BOUND = (0.4, 2.0)


def stability_starters(clubs) -> tuple[tuple[int, int], ...]:
    """stability.S's walk over a roster at rest: (sum of max(0, K - Durability), starters) for each of the 13 classes.

    ``clubs`` holds the 32 clubs in club-table order, each a sequence of (stored position, stored depth rank, Durability)
    for the players on its list, in list order. Raises ValueError where the walk would leave every factor at 1.0."""
    clubs = list(clubs)
    if len(clubs) != STABILITY_CLUBS:
        raise ValueError(f"The stability walk needs {STABILITY_CLUBS} clubs, not {len(clubs)}")
    at = LABELS["stab_starters"]
    starters = _TEMPLATE[at:at + len(STABILITY_POSITION_CLASS)]
    sums, counts = [0] * len(STABILITY_CLASS_NAMES), [0] * len(STABILITY_CLASS_NAMES)
    for club in clubs:
        club = list(club)
        if len(club) > STABILITY_MAX_LISTED:
            raise ValueError(f"A club lists {len(club)} players; the stability walk stops above {STABILITY_MAX_LISTED}")
        for position, rank, durability in club:
            if not 0 <= position < len(STABILITY_POSITION_CLASS) or STABILITY_POSITION_CLASS[position] is None:
                continue
            if rank >= starters[position]:
                continue
            index = STABILITY_POSITION_CLASS[position]
            sums[index] += max(0, STABILITY_ZERO_POINTS[index] - durability)
            counts[index] += 1
    return tuple(zip(sums, counts))


def stability_reference_for(starters) -> tuple[float, ...]:
    """R x static(roster) / static(calibration roster) per class, from stability_starters() of the disc's roster.

    A class with the calibration roster's exact statistic keeps its frozen R, so that roster builds the executable
    unchanged; so does a class with 1 to 7 starters, which the game leaves at 1.0. Raises ValueError when the measurement
    looks wrong: a class with no starters, a mean of max(0, K - Durability) that is not finite or not in (0, K], or a
    derived reference outside STABILITY_REFERENCE_BOUND x R."""
    from fractions import Fraction
    import math

    starters = tuple(tuple(row) for row in starters)
    if len(starters) != len(STABILITY_CLASS_NAMES):
        raise ValueError("The stability statistic needs thirteen classes")
    low, high = STABILITY_REFERENCE_BOUND
    out = []
    for name, zero, frozen, (total, count), (total0, count0) in zip(
            STABILITY_CLASS_NAMES, STABILITY_ZERO_POINTS, STABILITY_REFERENCE, starters, STABILITY_CALIBRATION):
        if not count > 0:
            raise ValueError(f"The roster has no {name} starters")
        mean = total / count
        if not (math.isfinite(mean) and 0 < mean <= zero):
            raise ValueError(f"The {name} mean of K - Durability ({mean!r}) is out of range")
        if (total, count) == (total0, count0) or count < STABILITY_MIN_STARTERS:
            out.append(frozen)
            continue
        value = float(Fraction(frozen) * Fraction(total) * count0 / (Fraction(count) * total0))
        if not (math.isfinite(value) and low <= value / frozen <= high):
            raise ValueError(f"The {name} reference {value:.3f} is outside {low} to {high} times {frozen}")
        out.append(value)
    return tuple(out)

# These native checks cover the master Injury option, selector stack contract, switch tables and shared constants.
# Four routines are also pinned independently before they are linked into the reserved space.
_NATIVE_ABI = (
    (0x62550, 44, 'injury mode test and four destinations',
     'c6cfcfe1ffe83f092bd149f3edbfc6568925af14e3ab224b91b83d6ab9a74099'),
    (0x625a0, 37, 'master Injury slider predicate',
     '3b81eb41fd08a60f9d233fc9a0ec59842de64c69e80e3b7cba8f3b3f16fbd267'),
    (0x102580, 760, 'primary patient selector, base health writer and stack return',
     'e0228d5cfdb2607aa84e5118683ec7c69369f3ea635ea8d40d20126e41fac702'),
    (0x102878, 49, 'four position handlers and all 33 slot categories',
     '703c1a5985b517f6d9837aab65db8fd4c0becf6c93461b4ba4a7fc88a6bfba1d'),
    (0x1028b0, 82, 'scheduled injury entry with both stack returns',
     '4e5d79a90866054543c2d0684873e1f3579fd065ef2219615087282bbeaae2fb'),
    (0x4e6d10, 4, 'shared default QB entry probability',
     '0b9d79ff0fc4d0a77ef398763bbe45c445501e826219f2b6a1aa709411ab631d'),
    (0x4f6b48, 4, 'stock outer gate multiplier',
     '2bf14e785577603fda60476e5e5cfd313b95b39166647c4fa6b0b00fcd6d46b3'),
)

# Each relocation names an instruction field in the local fragment, its native addressing mode and exact target.
# pos_descriptor and pos_duration are slice 2's second copies of the first two; their fields resolve to the same
# shared group, weeks and private generator.
_LOCAL_FUNCTIONS = (
    ('descriptor', 0x102580, 139, '72437c36a4e2e8ed98c44491a98ce91ad5f740b745890ec5b0cac7c90c6ef445', (
        (31, True, 'group', 0x0),
        (38, True, 'stock', 0x13e260),
        (79, False, 'private_rng', 0x0),
        (102, True, 'stock', 0x48b90),
    )),
    ('duration', 0x10278b, 93, 'ba50cb26a9df3db43765d2ef631eae897c4da66abe0f07f7d83742244a57060b', (
        (16, True, 'stock', 0x10286e),
        (32, True, 'weeks', 0x0),
        (67, False, 'private_rng', 0x0),
        (74, True, 'stock', 0x48b50),
    )),
    ('group', 0x13e420, 157, '6d3ba41c638463ff7b5f7313ef4c3ac6ba8c7081b47301fc64c26522b00adfc8', (
        (11, False, 'private_rng', 0x0),
        (16, True, 'stock', 0x48b50),
        (38, True, 'stock', 0x13e260),
        (46, False, 'private_rng', 0x0),
        (54, True, 'stock', 0x48b50),
        (107, True, 'stock', 0x13e260),
        (115, False, 'private_rng', 0x0),
        (123, True, 'stock', 0x48b50),
    )),
    ('weeks', 0x13dfe0, 421, '52f80473ec83d1872c8a7c8e7bd346a5ddb5fd8697176ac1f3c66e5900f587f5', (
        (53, False, 'private_rng', 0x0),
        (58, True, 'stock', 0x48b90),
        (223, False, 'private_rng', 0x0),
        (228, True, 'stock', 0x48b90),
        (385, True, 'stock', 0x13dd50),
        (411, True, 'stock', 0x13dd50),
    )),
)
_LOCAL_FUNCTIONS += tuple((copy,) + row[1:] for copy, row in zip(("pos_descriptor", "pos_duration"), _LOCAL_FUNCTIONS))


def _checked(read_game, at, size, label, expected):
    content = read_game(at, size)
    if len(content) != size or sha256(content).hexdigest() != expected:
        raise ValueError(f"Unrecognized native quarterback injury input: {label} at {at:#x}")
    return content


def check_native_sources(read_game: Callable[[int, int], bytes]) -> None:
    """Verify the original selector's indirect tables, slider gate and return ABI on this physical image."""
    for at, size, name, pin in _NATIVE_ABI:
        _checked(read_game, at, size, name, pin)


def _set32(bank, offset, value):
    struct.pack_into("<I", bank, offset, value & 0xFFFFFFFF)


def _rate(rate):
    if type(rate) is not int or not 0 <= rate <= RATE_DENOMINATOR:
        raise ValueError("Quarterback injury chance must be a whole number from 0 to 100,000")
    return rate


def _configure_tables(bank, rate):
    # The health slider scales these 31-bit thresholds again in the native handler. Sacks and escapes carry 4x exposure.
    for label, factor in (("ordinary_thresholds", 1), ("special_thresholds", 4)):
        chance = rate / RATE_DENOMINATOR
        values = (2 * chance * factor * max(0, 100 - d) / (100 - REFERENCE_DURABILITY) * (1 << 31)
                  for d in range(256))
        struct.pack_into("<256f", bank, LABELS[label], *values)
    start = 0
    for end, threshold in LENGTH_ACCEPT:
        count = end + 1 - start
        struct.pack_into(f"<{count}I", bank, LABELS["length_thresholds"] + 4 * start, *([threshold] * count))
        start = end + 1
    for accuracy in range(101):
        position = min(1.0, max(0.0, (accuracy - 92) / 6))
        gain = .982 * (.935 + .130 * position**4)
        struct.pack_into("<f", bank, GAIN_TABLE + 4 * accuracy, gain)
    struct.pack_into("<ff", bank, GAIN_CONSTANTS, .77, .982)
    _configure_positions(bank, rate)
    _configure_stability(bank, rate)


def position_accept_thresholds(position):
    """The six acceptance thresholds by week group on the 31-bit scale; 0x80000000 keeps every diagnosis."""
    if tuple(last for last, _ in position.accept) != ACCEPT_WEEK_BOUNDARIES:
        raise ValueError(f"The {position.name} acceptance table must end its runs at weeks {ACCEPT_WEEK_BOUNDARIES}")
    if not all(0 <= probability <= 1 for _, probability in position.accept):
        raise ValueError(f"Invalid acceptance probability for {position.name}")
    return [round(probability * (1 << 31)) for _, probability in position.accept]


def position_accept_by_week(position):
    """The threshold the native check uses for assigned weeks 0 to 31 (weeks above 31 use week 31's)."""
    groups = position_accept_thresholds(position)
    return [groups[group] for group in POSITION_WEEK_GROUPS]


def _configure_positions(bank, rate):
    # E[class] = pos_scale x Injury slider in the native check; the chance per exposed play is E x (K - Durability).
    for index, position in enumerate(POSITION_CLASSES):
        scale = 2 * position.base_chance / POSITION_SCALE * (rate / DEFAULT_RATE)
        scale = scale / (position.zero_point - position.reference_durability) * (1 << 31)
        if position.name == "halfback" and not HALFBACK_SUPPLEMENT:
            scale = 0.0
        struct.pack_into("<f", bank, LABELS["pos_scale"] + 4 * index, scale)
        struct.pack_into("<I", bank, LABELS["pos_zero"] + 4 * index, position.zero_point)
        groups = len(ACCEPT_WEEK_BOUNDARIES)
        struct.pack_into(f"<{groups}I", bank, LABELS["pos_accept"] + 4 * groups * index,
                         *position_accept_thresholds(position))
    bank[LABELS["pos_enabled"]] = 1 if rate > 0 else 0


def stability_year_factors(slope=STABILITY_YEAR_SLOPE):
    """Mode "year": 1.0 at season index 0 and 1, 1 / (1 + slope x (index - 0.5)) at 2, 3 and 4, index 4's after."""
    values = [1.0, 1.0] + [1 / (1 + slope * (index - 0.5)) for index in (2, 3, 4)]
    return tuple(values + [values[-1]] * (STABILITY_SEASONS - len(values)))


def _configure_stability(bank, rate, *, mode=None, reference=None, classes_off=None, slope=None):
    mode = STABILITY_MODE if mode is None else mode
    reference = STABILITY_REFERENCE if reference is None else tuple(reference)
    classes_off = STABILITY_CLASSES_OFF if classes_off is None else tuple(classes_off)
    slope = STABILITY_YEAR_SLOPE if slope is None else slope
    if mode not in STABILITY_MODES:
        raise ValueError(f"Unknown stability mode {mode!r}")
    if len(reference) != len(STABILITY_CLASS_NAMES) or not all(
            isinstance(value, (int, float)) and 0 < value < 256 for value in reference):
        raise ValueError("The stability reference needs thirteen positive values")
    if not set(classes_off) <= set(STABILITY_CLASS_NAMES):
        raise ValueError(f"Unknown stability classes {sorted(set(classes_off) - set(STABILITY_CLASS_NAMES))}")
    if not 0 <= slope < 1:
        raise ValueError("The stability year slope must be from 0 to 1")
    struct.pack_into(f"<{len(reference)}f", bank, LABELS["stab_reference"], *reference)
    bank[LABELS["stab_zero"]:LABELS["stab_zero"] + len(STABILITY_ZERO_POINTS)] = bytes(STABILITY_ZERO_POINTS)
    struct.pack_into(f"<{STABILITY_SEASONS}f", bank, LABELS["stab_year"], *stability_year_factors(slope))
    off = {STABILITY_CLASS_NAMES.index(name) for name in classes_off}
    for position, index in enumerate(STABILITY_POSITION_CLASS):
        bank[LABELS["stab_class"] + position] = 0xFF if index is None or index in off else index
    bank[LABELS["stab_mode"]] = 0 if rate == 0 else STABILITY_MODES[mode]


def _link_authored(bank_va: int, sim_code_va: int, sim_data_va: int, depth: int) -> bytearray:
    from . import nfl2k5_sim_realism as sim

    origins = {
        "stock": 0, "literal": 0, "bank": bank_va, "sim_data": sim_data_va,
        "depth": depth,
        "pass_converter": sim_code_va + sim.label_offsets()["pass_scale"],
        "red_zone_line": sim_code_va + sim.QB_BONUS_RZ_OFF,
        "mix_slope": sim_code_va + sim.MIX_QB_SLOPE_OFF, "mix_bias": sim_code_va + sim.MIX_BIAS_OFF,
    }
    bank = bytearray(_TEMPLATE)
    for offset, relative, family, addend in _RELOCATIONS:
        target = origins[family] + addend
        _set32(bank, offset, target - (bank_va + offset) if relative else target)
    return bank


def bank_bytes(read_game: Callable[[int, int], bytes], bank_va: int, sim_code_va: int, sim_data_va: int,
               lineup_va: int | None = None, *, rate: int = DEFAULT_RATE, marker: bytes = b"",
               reference=None) -> bytes:
    """Link against the installed simulator, optional lineup owner and four verified local functions."""
    from . import nfl2k5_lineup_roles as roles

    _rate(rate)
    if not isinstance(marker, bytes) or len(marker) not in (0, MARK_SIZE):
        raise ValueError(f"An installed quarterback settings record requires {MARK_SIZE} bytes")
    addresses = (bank_va, sim_code_va, sim_data_va)
    if lineup_va is not None:
        addresses += (lineup_va,)
    for address in addresses:
        if type(address) is not int or not 0 < address <= 0xFFFFFFFF - CODE_SIZE:
            raise ValueError("The quarterback runtime needs valid 32-bit executable addresses")
    check_native_sources(read_game)
    recovery = lineup_va is not None and rate > 0
    depth = lineup_va + 0x455 if recovery else roles.AUTO_DEPTH
    bank = _link_authored(bank_va, sim_code_va, sim_data_va, depth)
    for name, at, size, pin, fields in _LOCAL_FUNCTIONS:
        offset = LABELS[name]
        bank[offset:offset + size] = _checked(read_game, at, size, name, pin)
        for field, relative, symbol, addend in fields:
            target = addend if symbol == "stock" else bank_va + LABELS[symbol] + addend
            where = offset + field
            _set32(bank, where, target - (bank_va + where + 4) if relative else target)
    _configure_tables(bank, rate)
    if reference is not None:       # the disc roster's references (stability_reference_for); None keeps the frozen R
        _configure_stability(bank, rate, reference=reference)
    if not recovery:
        start, end = LABELS["depth_hook"], LABELS["match_hook"]
        bank[start:end] = b"\xc3" + b"\xcc" * (end - start - 1)
    if marker:
        bank[MARK_OFFSET:MARK_OFFSET + len(marker)] = marker
    return bytes(bank)


def _call(at, destination, width=5):
    return (b"\xe8" + struct.pack("<I", (destination - at - 5) & 0xFFFFFFFF)).ljust(width, b"\x90")


def edits(bank_va: int, sim_code_va: int, sim_data_va: int, lineup_va: int | None = None,
          *, rate: int = DEFAULT_RATE, rb_va: int | None = None) -> tuple[tuple[str, int, bytes, bytes], ...]:
    """Return (name, virtual address, expected physical instruction/data, installed bytes) for every external edit.

    rb_va is the running-back owner's installed weekly entry (its cave), when that owner is installed. With a rate
    above zero its jump at the weekly tick is the expected physical bytes and the game's own tail is installed.
    """
    from . import nfl2k5_sim_realism as sim

    _rate(rate)
    if rb_va is not None and (type(rb_va) is not int or not 0 < rb_va <= 0xFFFFFFFF):
        raise ValueError("The running-back weekly entry needs a valid 32-bit executable address")
    result = [(name, at, _call(at, stock), _call(at, bank_va + LABELS[label]))
              for name, at, stock, label in _FIXED_CALLS]
    result.append(("contest", CONTEST_SITE, bytes.fromhex("8b15a071a900"),
                   _call(CONTEST_SITE, bank_va + LABELS["contest"], 6)))
    physical = sim.code_for(sim_code_va, sim_data_va)
    for label, offset in (("slope", 0x38), ("bias", 0x3E), ("flat", 0x62)):
        at = sim_code_va + offset
        result.append((label, at, physical[offset:offset + 6], _call(at, bank_va + LABELS[label], 6)))
    result.append(("completed_pass", COMPLETION_SITE, _call(COMPLETION_SITE, sim_code_va + sim.label_offsets()["pass_scale"]),
                   _call(COMPLETION_SITE, bank_va + LABELS["route_completed_pass"])))
    for label, offset, value in (("MIX_BIAS", sim.MIX_BIAS_OFF, 9.0), ("MIX_QB_SLOPE", sim.MIX_QB_SLOPE_OFF, .16)):
        result.append((label, sim_code_va + offset, physical[offset:offset + 4], struct.pack("<f", value)))
    if lineup_va is not None and rate > 0:
        at = lineup_va + 0x44B
        result.append(("recovery", at, _call(at, lineup_va + 0x455), _call(at, bank_va + LABELS["depth_hook"])))
    if rb_va is not None and rate > 0 and HALFBACK_SUPPLEMENT:
        jump = b"\xe9" + struct.pack("<I", (rb_va - WEEKLY_HALFBACK_SITE - 5) & 0xFFFFFFFF)
        result.append(("weekly_halfback", WEEKLY_HALFBACK_SITE, jump, WEEKLY_HALFBACK_ORIGINAL))
    return tuple(result)


# Generated from tools/qb_sim_injuries by build.py.
_TEMPLATE = b''.join((
    bytes.fromhex('50a19c71a90085c074038b4008870424ff742410ff742410ff742410e8ac281000e9fcffffff9090'),
    bytes.fromhex('90909083e4f00fae0424898c2400020000837934000f85e60100008b359c71a90085f60f84d80100'),
    bytes.fromhex('0083bedc000000000f85cb0100008b6e0885ed0f84c00100008b9424000200003b6a240f85b00100'),
    bytes.fromhex('00807d35000f85a6010000f64523800f859c010000f64527700f8592010000e89c25060085c00f84'),
    bytes.fromhex('850100008b3da071a90085ff0f84770100008b0d1829b70085c90f84690100008b491c8b068b1729'),
    bytes.fromhex('c829ca3d8c3c00000f875301000081fa8c3c00000f874701000039d00f843f0100007201928b0db8'),
    bytes.fromhex('76e5008b1db476e5003b05d405000075183b15d805000075103b0dcc05000075083b1dd005000074'),
    bytes.fromhex('5ce8fcffffffa3d40500008915d8050000890dcc050000891dd0050000c1c01031d03531494251e8'),
    bytes.fromhex('fe00000031c8c1c31031d8e8f20000003305a8fce500e8e70000003305b0fce500e8dc000000a3dc'),
    bytes.fromhex('050000c705e005000000000000ff05e0050000a1e005000069c0b979379e0305dc050000e8b10000'),
    bytes.fromhex('0089c33545544147e8a500000025ffffff7fa3e40500000fb64d3bbab8070000ff05e80500008b84'),
    bytes.fromhex('2400020000817828078a10007511ff0de8050000ff05ec050000bab80b0000d9048ad80d0402e600'),
    bytes.fromhex('d80d30000000db05e4050000ded9dfe0f6c4017434ff05f005000089d835314e454ce83b000000d1'),
    bytes.fromhex('e85089d8353154414ee82c00000089c2b9f8050000e8dc8b04006a00e83b000000e8fcffffff0fae'),
    bytes.fromhex('0c248ba42400020000619d8d642404c20c0089c2c1ea1031d069c06bcaeb8589c2c1ea0d31d069c0'),
    bytes.fromhex('35aeb2c289c2c1ea1031d0c3'),
    bytes(139),
    bytes.fromhex('8b7c2410a19c71a90089442414c7442418'),
    bytes(97),
    bytes.fromhex('89d83dff0000000f876a2810008b54243c3b1485b80f00000f836a281000ff05f4050000e9fcffff'),
    bytes.fromhex('ff'),
    bytes(578),
    bytes.fromhex('ffffffffffffffffffffffffffffffff'),
    bytes(3548),
    b'\xcc' * 72,
    bytes.fromhex('803d00070000000f84540200008b9c2404020000837b1c000f8543020000837b34000f8539020000'),
    bytes.fromhex('e89c25060085c00f842c0200008b9c24040200008b359c71a90085f60f84170200008b3da071a900'),
    bytes.fromhex('85ff0f84090200008b0d1829b70085c90f84fb0100008b491c85c90f84f00100008b068b1729c829'),
    bytes.fromhex('ca3d8c3c00000f87dd01000081fa8c3c00000f87d101000039d00f84c90100007201928b0db876e5'),
    bytes.fromhex('008b2db476e5003b053004000075183b153404000075103b0d2804000075083b2d2c040000745ce8'),
    bytes.fromhex('fcffffffa330040000891534040000890d28040000892d2c040000c1c01031d035504f5332e8df01'),
    bytes.fromhex('000031c8c1c51031e8e8d30100003305a8fce500e8c80100003305b0fce500e8bd010000a3380400'),
    bytes.fromhex('00c7053c04000000000000ff053c040000ff0560040000a13c04000069c0b979379e030538040000'),
    bytes.fromhex('e88c010000a3400400003550475432e87d01000025ffffff7fa34404000031c9d9048df4040000d8'),
    bytes.fromhex('0d0402e600d80c8d00000000df3d48040000a1480400008b154c04000085d2740b7807b8ffffffff'),
    bytes.fromhex('eb0231c089048dc40400004183f90c72bf31ed0fb604ad9506000089f185c0740289f983b9dc0000'),
    bytes.fromhex('00000f85970000000fb604ad960600008b54810885d20f8483000000f742200000c0bf757af64227'),
    bytes.fromhex('7075740fb604ad9706000083e0037414817b28e8811000755e4875083b15a471a90075530fb6423b'),
    bytes.fromhex('510fb60cad940600008b148d2405000029c2764689d0f7248dc40400005985d275073d0000008076'),
    bytes.fromhex('05b8000000800fb614ad97060000c1ea047406f7e20facd004390544040000721429054404000045'),
    bytes.fromhex('83fd1b0f8242ffffffc359ebf2890d540400000fb604ad96060000a3580400000fb604ad94060000'),
    bytes.fromhex('a350040000ff0485640400008d0440c1e0030554050000a35c040000a14004000035504c4e32e826'),
    bytes.fromhex('000000d1e850a14004000035504e5432e81400000089c2b900000000e8dc8b04006a00e823000000'),
    bytes.fromhex('c389c2c1ea1031d069c06bcaeb8589c2c1ea0d31d069c035aeb2c289c2c1ea1031d0c3'),
    bytes(139),
    bytes.fromhex('8b7c2410a15404000089442414a15804000089442418'),
    bytes(93),
    bytes.fromhex('89d883f81f7605b81f0000000fb680740600008b54243c8b0d5c0400003b14810f836a281000a150'),
    bytes.fromhex('040000ff048594040000e9e4271000ffffffffffffffffffffffffffffffff'),
    bytes(574),
    bytes.fromhex('01020303030304040404040404040505050505050505050505050505050500000c0000000d000100'),
    bytes.fromhex('0a0001000b000200090003010f000301100004000101040003010500040005000500050006000500'),
    bytes.fromhex('074006000800070002020801110008011200090113000901140009011500090116400a0118000a01'),
    bytes.fromhex('19000a011a000b0117000b011b000b011c4000'),
    b'\xcc' * 255,
    bytes.fromhex('60b90c000000c7048d600100000000803f4979f20fb6058702000085c00f843b0100008b1db876e5'),
    bytes.fromhex('0083fb020f822c01000083f801752583fb097605bb090000008b049d30020000b90c00000089048d'),
    bytes.fromhex('600100004979f6e902010000a11829b70085c00f84f50000008b701c85f60f84ea00000031c0b919'),
    bytes.fromhex('00000089048d940100004979f6bd200000000fb68e1c01000083f9410f87c400000031db39cb7357'),
    bytes.fromhex('8b3c9e4385ff74f40fb6473583f81077eb0fb6905802000081faff00000074dc510fb74f28c1e90a'),
    bytes.fromhex('83e1073a88690200005973c80fb6473b510fb68a7a02000029c1730231c9010c9594010000ff0495'),
    bytes.fromhex('c801000059eba581c6f40100004d758a31c9833c8dc801000008724c833c8d94010000007442db04'),
    bytes.fromhex('8dc8010000d80c8dfc010000da348d94010000d91c8d600100008b048d600100003d3333b33e7305'),
    bytes.fromhex('b83333b33e3d0000a03f7605b80000a03f89048d600100004183f90d72a461c30000803f0000803f'),
    bytes.fromhex('0000803f0000803f0000803f0000803f0000803f0000803f0000803f0000803f0000803f0000803f'),
    bytes.fromhex('0000803f'),
    bytes(158),
    bytes.fromhex('803f0000803f0000803f0000803f0000803f0000803f0000803f0000803f0000803f0000803f0cff'),
    bytes.fromhex('ff050a0b0b040706090902010008030100000303010102010103030102020202'),
    bytes(14),
    b'\xcc' * 376,
    bytes.fromhex('9c605756e8fcffffff83c408619de8fcffffff9c605756e8fcffffff83c408619dc39c608d442424'),
    bytes.fromhex('505251e8fcffffff83c40c619dc7042400000000e97cb210009c60e8fcffffff619de95bb910008b'),
    bytes.fromhex('502081e20000c0bf750f8b4024a9000000700f94c00fb6c0c331c0c38b0d1829b70085c90f84ef01'),
    bytes.fromhex('00005557565383ec1489c68b511c39d00f82d301000029d03d7f3e00000f87c6010000bbf4010000'),
    bytes.fromhex('31d2f7f389d585d20f85b30100006bd8548bbb10000000893c2485ff0f849f010000398b04000000'),
    bytes.fromhex('0f859301000039b3000000000f85870100008b0db876e500398b080000000f85750100008b0db476'),
    bytes.fromhex('e500398b0c0000000f85630100008d90d75d39008b14950000000085d2740e8b154001e60085d20f'),
    bytes.fromhex('84440100000fb68e1c01000080f9410f87340100008d1c8e895c240c6bd85431c089442404895c24'),
    bytes.fromhex('108b44240c39c60f849d0000008b3e85ff0f848b0000008a473584c00f858000000031c939bccb14'),
    bytes.fromhex('0000007408418b042439c172ef390c240f84e3000000b801000000d3e0854424040f85d200000009'),
    bytes.fromhex('44240489f8e8b5feffff85c00f84bf0000008b4424108d94c8100000000fb6420889442408668b47'),
    bytes.fromhex('2866c1e80a83e007394424080f85970000008a42098a575238d00f8589000000394c24087404a801'),
    bytes.fromhex('757f83c604e957ffffffb8010000008a0c24d3e0488b7c240439f87564a10000000031c90fb6b318'),
    bytes.fromhex('00000089f239ee74388b35000000008b8b14000000890cf5000000008d7e01893d000000008814f5'),
    bytes.fromhex('04000000668b512880e6e389eec1e60a09f26689512840b1014583c308392c2475b284c97405a300'),
    bytes.fromhex('000000ff050000000083c4145b5e5f5dc3c35557565383ec0c8b742424837c24201f0f873d010000'),
    bytes.fromhex('6b4424205431d28990100000008b3d1829b70085ff0f84220100008b571c69442420f401000001d0'),
    bytes.fromhex('39f00f850d0100008b44242005d75d39008b04850000000085c0740da14001e60085c00f84ec0000'),
    bytes.fromhex('000fb6961c01000080fa410f87dc0000008d04968944240489342431db31ed6b4424205489442408'),
    bytes.fromhex('8b442404390424743e8b04248b1085d2742f8a4a3584c97528668b4a2866c1e90a83e107b8010000'),
    bytes.fromhex('00d3e085e80f859200000009c5438b4424088994c81400000083042404ebb98d43fe83f8067776b8'),
    bytes.fromhex('0100000088d9d3e04839e875686b6c2420548b85140000008b402085c07956250000c03f3d000040'),
    bytes.fromhex('00754ab9010000008b84cd14000000e8cbfcffff85c074354139cb75eb6b442420548d9000000000'),
    bytes.fromhex('89b00000000089b804000000a1b876e500894208a1b476e50089420c895a10ff050000000083c40c'),
    bytes.fromhex('5b5e5f5dc355575653837c24141f0f87810000006b542414548d82000000008bb21000000085f674'),
    bytes.fromhex('6c8b7c241839ba0000000075608d3cf031db8b6814668b4d2866c1e90a83e1078848188a55528850'),
    bytes.fromhex('190fb7c9ba01000000d3e209d383c00839f875d66b4424145480b81800000000740e89f1ba010000'),
    bytes.fromhex('00d3e24a39da740f6b4424145431d2899010000000eb06ff05000000005b5e5f5dc3538b5424088b'),
    bytes.fromhex('5c240c8b44241031c9890d0000000081781ce0b910007533817834587b0c00752aa180ffe50083f8'),
    bytes.fromhex('047520a1a476e50083e80883f801771339da740f89d0e8c9fbffff89d85be9c1fbffff5bc3a10000'),
    bytes.fromhex('000085c0742748a3000000008b0cc500000000668b51280fb604c504000000c1e00a80e6e309d066'),
    bytes.fromhex('894128ebd0c36690'),
    bytes(2849),
    b'\xcc' * 255,
    bytes.fromhex('9c60817c24245fb910000f8594000000817c2440e0b910000f8586000000817c2458587b0c00757c'),
    bytes.fromhex('833d80ffe500047573a1a476e50083e80783f8027766a1b876e5003b05000000007559a1b476e500'),
    bytes.fromhex('3b0500000000754ca11829b70085c074438b401c29c129c281f98c3c0000773481fa8c3c0000772c'),
    bytes.fromhex('39d17428720287d13b0d00000000751c3b15000000007514c70500000000ffffffffc70500000000'),
    bytes.fromhex('ffffffff619de9fcffffff'),
    b'\xcc' * 85,
    bytes.fromhex('91e30c8d4c24d083c124b901000000919c6089e181ec10020000e9fcffffff'),
    b'\xcc' * 225,
    bytes.fromhex('9c505183ec08833d80ffe500040f8597000000a1a476e50083e80783f8020f8786000000a19c71a9'),
    bytes.fromhex('0085c0747d3b68087578807d35007572f745200000c0bf7569f74524000000707560d914248b0c24'),
    bytes.fromhex('85c978563b0db8000000734ed905b8000000d8e18b0d0072a90081f90000a0417e1581f90000c842'),
    bytes.fromhex('7f0dd80dc4000000a1c8000000eb0bd80dbc000000a1c0000000d95424048b4c240439c1760addd8'),
    bytes.fromhex('89442404d9442404dec18d64240859589d8b15a071a900c385eb513fcdcccc3e0ad7a33d0000403f'),
    bytes.fromhex('295c0f3e'),
    b'\xcc' * 308,
    bytes.fromhex('9c505183ec04833d80ffe500047569a1a476e50083e80783f802775ca19c71a90085c074538b4008'),
    bytes.fromhex('85c0744c807835007546f740200000c0bf753df74024000000707534d91424833c24007e2b0fb648'),
    bytes.fromhex('42b85500000029c87e1e83f8177605b817000000890424db0424d80d8c000000d82d88000000dec9'),
    bytes.fromhex('d80d000000008d64240459589dc3cccc0000803fbc74933c'),
    b'\xcc' * 112,
    bytes.fromhex('9c60c60500000000008b4424243d0000000074273d000000000f85f4000000817c2440000000000f'),
    bytes.fromhex('85e6000000817c2458000000000f85d8000000833d00000000020f85cb000000833d00000000040f'),
    bytes.fromhex('85be000000a10000000083e80783f8020f87ad000000a10000000085c00f84a00000008b581c85db'),
    bytes.fromhex('0f849500000089ce29de81fe8c3c00000f878500000089d729df81ff8c3c0000777939fe7475b9f4'),
    bytes.fromhex('01000089f031d2f7f185d2756689f831d2f7f185d2755cc6050000000001a1000000003b05000000'),
    bytes.fromhex('007537a1000000003b0500000000752a39fe720287fe3b3500000000751c3b3d000000007514c705'),
    bytes.fromhex('00000000ffffffffc70500000000ffffffff817c242400000000740e619de9fcffffff619de9fcff'),
    bytes.fromhex('ffffc7050000000000000000833d000000000872128b442418e8fcffffff8b442414e8fcffffff61'),
    bytes.fromhex('9dc7042400000000e9fcffffff9c60e8fcffffff619de9fcffffff9c803d000000000074069de9fc'),
    bytes.fromhex('ffffff9de9fcffffff9c803d000000000074069de9fcffffff9d8b1500000000c39c803d00000000'),
    bytes.fromhex('0074069de9fcffffff9dd80d08020000c39c803d000000000074069de9fcffffff9dd80d0c020000'),
    bytes.fromhex('c39c803d000000000074089dd80d00000000c39dd80d10020000c39c803d000000000074089dd805'),
    bytes.fromhex('00000000c39dd80514020000c39c803d000000000074089dd81d00000000c39dd81d14020000c3cc'),
    bytes(17),
    bytes.fromhex('ccccccc6050000000000e9fcffffff'),
    b'\xcc' * 24,
    bytes.fromhex('9c803d000000000074069de9fcffffff9de9fcffffff'),
    b'\xcc' * 170,
    bytes.fromhex('9c83fb04723083fb07772b83fb04751081fae57b8d0a721e81fae57b8d0aeb0e81fadb940108720e'),
    bytes.fromhex('81fadb940108bb0300000073014b9de9e4271000'),
    b'\xcc' * 196,
    bytes.fromhex('9c506a00833d80ffe500047550a1a476e50083e80783f8027743a19c71a90085c0743a8b400885c0'),
    bytes.fromhex('743380783500752df740200000c0bf7524f7402400000070751bd91424833c24007e120fb6404283'),
    bytes.fromhex('f8647709d80c8500000000eb06d80d000000008d642404589dc3'),
    b'\xcc' * 662,
    bytes.fromhex('d90500000000d81d00000000dfe0f6c441740ed9442404e8fcffffff90d95c24048b0424a3000000'),
    bytes.fromhex('0058e8fcffffffe8fcffffff908b150000000052c3'),
    b'\xcc' * 707,
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x001d, True, 'stock', 0x1028ac),
    (0x0022, True, 'bank', 0x31fc),
    (0x0098, True, 'stock', 0x6259c),
    (0x00fb, False, 'bank', 0x5d4),
    (0x0103, False, 'bank', 0x5d8),
    (0x010b, False, 'bank', 0x5cc),
    (0x0113, False, 'bank', 0x5d0),
    (0x011a, True, 'bank', 0x1bfc),
    (0x011f, False, 'bank', 0x5d4),
    (0x0125, False, 'bank', 0x5d8),
    (0x012b, False, 'bank', 0x5cc),
    (0x0131, False, 'bank', 0x5d0),
    (0x0167, False, 'bank', 0x5dc),
    (0x016d, False, 'bank', 0x5e0),
    (0x0177, False, 'bank', 0x5e0),
    (0x017c, False, 'bank', 0x5e0),
    (0x0188, False, 'bank', 0x5dc),
    (0x01a3, False, 'bank', 0x5e4),
    (0x01ac, False, 'bank', 0x7b8),
    (0x01b2, False, 'bank', 0x5e8),
    (0x01c8, False, 'bank', 0x5e8),
    (0x01ce, False, 'bank', 0x5ec),
    (0x01d3, False, 'bank', 0xbb8),
    (0x01e2, False, 'bank', 0x1d90),
    (0x01e8, False, 'bank', 0x5e4),
    (0x01f7, False, 'bank', 0x5f0),
    (0x0219, False, 'bank', 0x5f8),
    (0x021e, True, 'stock', 0x48bdc),
    (0x022a, True, 'bank', 0x13fc),
    (0x036a, True, 'stock', 0x10286a),
    (0x0375, False, 'bank', 0xfb8),
    (0x037b, True, 'stock', 0x10286a),
    (0x0381, False, 'bank', 0x5f4),
    (0x0386, True, 'bank', 0x38fc),
    (0x1402, False, 'bank', 0x1b00),
    (0x1429, True, 'stock', 0x6259c),
    (0x14a9, False, 'bank', 0x1830),
    (0x14b1, False, 'bank', 0x1834),
    (0x14b9, False, 'bank', 0x1828),
    (0x14c1, False, 'bank', 0x182c),
    (0x14c8, True, 'bank', 0x1bfc),
    (0x14cd, False, 'bank', 0x1830),
    (0x14d3, False, 'bank', 0x1834),
    (0x14d9, False, 'bank', 0x1828),
    (0x14df, False, 'bank', 0x182c),
    (0x1515, False, 'bank', 0x1838),
    (0x151b, False, 'bank', 0x183c),
    (0x1525, False, 'bank', 0x183c),
    (0x152b, False, 'bank', 0x1860),
    (0x1530, False, 'bank', 0x183c),
    (0x153c, False, 'bank', 0x1838),
    (0x1546, False, 'bank', 0x1840),
    (0x155a, False, 'bank', 0x1844),
    (0x1563, False, 'bank', 0x18f4),
    (0x1570, False, 'bank', 0x1d60),
    (0x1576, False, 'bank', 0x1848),
    (0x157b, False, 'bank', 0x1848),
    (0x1581, False, 'bank', 0x184c),
    (0x1597, False, 'bank', 0x18c4),
    (0x15a7, False, 'bank', 0x1a95),
    (0x15c4, False, 'bank', 0x1a96),
    (0x15e7, False, 'bank', 0x1a97),
    (0x160d, False, 'bank', 0x1a94),
    (0x1614, False, 'bank', 0x1924),
    (0x1621, False, 'bank', 0x18c4),
    (0x163a, False, 'bank', 0x1a97),
    (0x164b, False, 'bank', 0x1844),
    (0x1653, False, 'bank', 0x1844),
    (0x1667, False, 'bank', 0x1854),
    (0x166f, False, 'bank', 0x1a96),
    (0x1674, False, 'bank', 0x1858),
    (0x167c, False, 'bank', 0x1a94),
    (0x1681, False, 'bank', 0x1850),
    (0x1688, False, 'bank', 0x1864),
    (0x1693, False, 'bank', 0x1954),
    (0x1698, False, 'bank', 0x185c),
    (0x169d, False, 'bank', 0x1840),
    (0x16af, False, 'bank', 0x1840),
    (0x16c0, False, 'bank', 0x5f8),
    (0x16c5, True, 'stock', 0x48bdc),
    (0x1783, False, 'bank', 0x1854),
    (0x178c, False, 'bank', 0x1858),
    (0x1800, False, 'bank', 0x1a74),
    (0x180a, False, 'bank', 0x185c),
    (0x1813, True, 'stock', 0x10286a),
    (0x1818, False, 'bank', 0x1850),
    (0x181f, False, 'bank', 0x1894),
    (0x1824, True, 'stock', 0x1027e4),
    (0x1c09, False, 'bank', 0x1d60),
    (0x1c17, False, 'bank', 0x1e87),
    (0x1c44, False, 'bank', 0x1e30),
    (0x1c50, False, 'bank', 0x1d60),
    (0x1c7e, False, 'bank', 0x1d94),
    (0x1cb4, False, 'bank', 0x1e58),
    (0x1ccd, False, 'bank', 0x1e69),
    (0x1cdc, False, 'bank', 0x1e7a),
    (0x1ce9, False, 'bank', 0x1d94),
    (0x1cf0, False, 'bank', 0x1dc8),
    (0x1d05, False, 'bank', 0x1dc8),
    (0x1d0f, False, 'bank', 0x1d94),
    (0x1d19, False, 'bank', 0x1dc8),
    (0x1d20, False, 'bank', 0x1dfc),
    (0x1d27, False, 'bank', 0x1d94),
    (0x1d2e, False, 'bank', 0x1d60),
    (0x1d35, False, 'bank', 0x1d60),
    (0x1d54, False, 'bank', 0x1d60),
    (0x2005, True, 'bank', 0x2266),
    (0x200f, True, 'depth', -0x4),
    (0x2018, True, 'bank', 0x23c1),
    (0x202c, True, 'bank', 0x2456),
    (0x2038, False, 'bank', 0x2041),
    (0x203d, True, 'stock', 0x10b27c),
    (0x2044, True, 'bank', 0x24a9),
    (0x204b, True, 'stock', 0x10b95b),
    (0x20b3, False, 'bank', 0x2590),
    (0x20c4, False, 'bank', 0x2584),
    (0x20d0, False, 'bank', 0x2580),
    (0x20e2, False, 'bank', 0x2588),
    (0x20f4, False, 'bank', 0x258c),
    (0x2167, False, 'bank', 0x2594),
    (0x21a9, False, 'bank', 0x2590),
    (0x21fe, False, 'bank', 0x24e0),
    (0x2207, False, 'bank', 0x2598),
    (0x2213, False, 'bank', 0x24f0),
    (0x2219, False, 'bank', 0x2594),
    (0x2220, False, 'bank', 0x2500),
    (0x2229, False, 'bank', 0x24f0),
    (0x2230, False, 'bank', 0x2504),
    (0x2257, False, 'bank', 0x24e0),
    (0x225d, False, 'bank', 0x24e4),
    (0x2289, False, 'bank', 0x2590),
    (0x2335, False, 'bank', 0x2594),
    (0x235c, False, 'bank', 0x2594),
    (0x237b, False, 'bank', 0x2594),
    (0x2394, False, 'bank', 0x2580),
    (0x239a, False, 'bank', 0x2580),
    (0x23a0, False, 'bank', 0x2584),
    (0x23b9, False, 'bank', 0x24ec),
    (0x23db, False, 'bank', 0x2580),
    (0x23e1, False, 'bank', 0x2590),
    (0x23ef, False, 'bank', 0x2580),
    (0x242b, False, 'bank', 0x2598),
    (0x2449, False, 'bank', 0x2590),
    (0x2451, False, 'bank', 0x24e8),
    (0x246b, False, 'bank', 0x24f0),
    (0x24ae, False, 'bank', 0x24f0),
    (0x24b8, False, 'bank', 0x24f0),
    (0x24bf, False, 'bank', 0x2500),
    (0x24cb, False, 'bank', 0x2504),
    (0x3145, False, 'bank', 0x5cc),
    (0x3152, False, 'bank', 0x5d0),
    (0x3182, False, 'bank', 0x5d4),
    (0x318a, False, 'bank', 0x5d8),
    (0x3192, False, 'bank', 0x5cc),
    (0x319c, False, 'bank', 0x1828),
    (0x31a7, True, 'bank', 0x201e),
    (0x321b, True, 'bank', 0x27),
    (0x3356, False, 'bank', 0x33b8),
    (0x335e, False, 'bank', 0x33b8),
    (0x337c, False, 'bank', 0x33c4),
    (0x3381, False, 'bank', 0x33c8),
    (0x3389, False, 'bank', 0x33bc),
    (0x338e, False, 'bank', 0x33c0),
    (0x356c, False, 'bank', 0x358c),
    (0x3572, False, 'bank', 0x3588),
    (0x357a, False, 'bank', 0x3d80),
    (0x3604, False, 'bank', 0x3818),
    (0x360e, False, 'stock', 0xec00c),
    (0x3615, False, 'stock', 0x10b95f),
    (0x3623, False, 'stock', 0x10b9e0),
    (0x3631, False, 'stock', 0xc7b58),
    (0x363d, False, 'stock', 0xe576a0),
    (0x364a, False, 'stock', 0xe5ff80),
    (0x3656, False, 'stock', 0xe576a4),
    (0x3667, False, 'stock', 0xb72918),
    (0x36b9, False, 'bank', 0x3818),
    (0x36bf, False, 'stock', 0xe576b8),
    (0x36c5, False, 'bank', 0x5cc),
    (0x36cc, False, 'stock', 0xe576b4),
    (0x36d2, False, 'bank', 0x5d0),
    (0x36e0, False, 'bank', 0x5d4),
    (0x36e8, False, 'bank', 0x5d8),
    (0x36f0, False, 'bank', 0x5cc),
    (0x36fa, False, 'bank', 0x1828),
    (0x3706, False, 'stock', 0xec00c),
    (0x370f, True, 'bank', 0x201e),
    (0x3716, True, 'stock', 0x10b27c),
    (0x371c, False, 'bank', 0x24f0),
    (0x3726, False, 'stock', 0xe576a4),
    (0x3732, True, 'bank', 0x2068),
    (0x373b, True, 'bank', 0x2068),
    (0x3744, False, 'bank', 0x374d),
    (0x3749, True, 'stock', 0x10b27c),
    (0x3750, True, 'bank', 0x24a9),
    (0x3757, True, 'stock', 0xec008),
    (0x375e, False, 'bank', 0x3818),
    (0x3767, True, 'bank', -0x4),
    (0x376d, True, 'stock', 0x1028ac),
    (0x3774, False, 'bank', 0x3818),
    (0x377d, True, 'bank', 0x32fc),
    (0x3784, False, 'stock', 0xa971a0),
    (0x378c, False, 'bank', 0x3818),
    (0x3795, True, 'bank', 0x34fc),
    (0x379c, False, 'bank', 0x3808),
    (0x37a4, False, 'bank', 0x3818),
    (0x37ad, True, 'bank', 0x39fc),
    (0x37b4, False, 'bank', 0x380c),
    (0x37bc, False, 'bank', 0x3818),
    (0x37c6, False, 'mix_slope', 0x0),
    (0x37ce, False, 'bank', 0x3810),
    (0x37d6, False, 'bank', 0x3818),
    (0x37e0, False, 'mix_bias', 0x0),
    (0x37e8, False, 'bank', 0x3814),
    (0x37f0, False, 'bank', 0x3818),
    (0x37fa, False, 'mix_bias', 0x0),
    (0x3802, False, 'bank', 0x3814),
    (0x3808, False, 'literal', 0x3f23d70a),
    (0x380c, False, 'literal', 0x3f68f5c3),
    (0x3810, False, 'literal', 0x3ecccccd),
    (0x3814, False, 'literal', 0x41080000),
    (0x381e, False, 'bank', 0x3818),
    (0x3824, True, 'stock', 0x6c77c),
    (0x3843, False, 'bank', 0x3818),
    (0x384c, True, 'bank', 0x3cfc),
    (0x3852, True, 'pass_converter', -0x4),
    (0x3938, True, 'stock', 0x1027e4),
    (0x3a57, False, 'bank', 0x3b00),
    (0x3a5f, False, 'bank', 0x3d84),
    (0x3d02, False, 'stock', 0xa97200),
    (0x3d08, False, 'red_zone_line', 0x0),
    (0x3d18, True, 'bank', 0x34fc),
    (0x3d25, False, 'sim_data', 0xc),
    (0x3d2b, True, 'stock', 0x10647c),
    (0x3d30, True, 'bank', 0x39fc),
    (0x3d37, False, 'sim_data', 0xc),
)

LABELS = {
    'accept_ptr': 0x185c,
    'active': 0x3818,
    'adjust': 0x3500,
    'before_primary': 0xd,
    'bias': 0x37d3,
    'completed_catch_scale': 0x3d00,
    'contest': 0x3771,
    'continue_capture': 0x2b,
    'depth_hook': 0x2000,
    'descriptor': 0x264,
    'duration': 0x304,
    'finished': 0x229,
    'flat': 0x37ed,
    'gamecast_screen_entry': 0x381c,
    'group': 0x38a,
    'length_thresholds': 0xfb8,
    'match_entry': 0x3600,
    'match_hook': 0x2022,
    'medical': 0x375b,
    'ordinary_thresholds': 0x7b8,
    'passing_scale': 0x3a00,
    'pos_accept': 0x1954,
    'pos_class': 0x1850,
    'pos_club_a': 0x1830,
    'pos_club_b': 0x1834,
    'pos_commits': 0x1894,
    'pos_descriptor': 0x16f3,
    'pos_duration': 0x1794,
    'pos_duration_accept': 0x17f1,
    'pos_effective': 0x18c4,
    'pos_enabled': 0x1b00,
    'pos_hash': 0x1840,
    'pos_hits': 0x1864,
    'pos_key': 0x1838,
    'pos_plays': 0x1860,
    'pos_sample': 0x1844,
    'pos_sampled': 0x155e,
    'pos_scale': 0x18f4,
    'pos_seq': 0x183c,
    'pos_slots': 0x1a94,
    'pos_week': 0x182c,
    'pos_week_group': 0x1a74,
    'pos_wide': 0x1848,
    'pos_year': 0x1828,
    'pos_zero': 0x1924,
    'positions': 0x1400,
    'private_rng': 0x5f8,
    'revise': 0x3900,
    'route_completed_pass': 0x3840,
    'slope': 0x37b9,
    'special_thresholds': 0xbb8,
    'stab_class': 0x1e58,
    'stab_count': 0x1dc8,
    'stab_factor': 0x1d60,
    'stab_mode': 0x1e87,
    'stab_reference': 0x1dfc,
    'stab_starters': 0x1e69,
    'stab_sum': 0x1d94,
    'stab_year': 0x1e30,
    'stab_zero': 0x1e7a,
    'stability': 0x1c00,
    'supplement': 0x0,
    'victim_side': 0x1854,
    'victim_slot': 0x1858,
    'weeks': 0x427,
}
