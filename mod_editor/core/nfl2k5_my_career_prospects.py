"""Creation tiers and unboosted native overall, derived from USA 246A80..246DE0.

Parameters below are interpreted rating weights and thresholds, not executable
bytes. Native comparison tests cover all 51 templates, tiers and body sizes.
Injury/weekly-preparation boosts are deliberately absent at creation (EDX=0).
In-game outcomes and career-goal completion remain UNWITNESSED.
"""
import math
import struct
from . import nfl2k5_roster_records as roster

# Zero preserves existing creation. Nonzero IDs persist at career footer +83.
TIERS = (
    ("Original creation", None, "Original career goals"),
    ("1st Day", 74, "Highest tier career goals"),
    ("2nd Day", 70, "Middle tier career goals"),
    ("3rd Day", 64, "Low tier career goals"),
    ("Undrafted", 59, "Lowest tier career goals"),
)
# consistency penalty, kick-style modifier, height/weight thresholds, attributes.
_GROUPS = (
    (0.5, 0.0, 1000, 300, ((55, 0.1), (60, 0.4), (69, 0.5))),
    (0.5, 0.0, 1000, 290, ((54, 0.05), (55, 0.15), (60, 0.3), (70, 0.5))),
    (0.6, 0.0, 1000, 230, ((64, 0.3), (54, 0.2), (60, 0.1), (55, 0.1), (73, 0.3))),
    (0.6, 0.0, 1000, 280, ((64, 0.2), (73, 0.4), (60, 0.3), (55, 0.1))),
    (0.6, 0.0, 1000, 260, ((72, 0.4), (54, 0.1), (55, 0.1), (60, 0.2), (64, 0.2))),
    (0.55, 0.0, 70, 1000, ((62, 0.5), (54, 0.2), (60, 0.1), (55, 0.1), (61, 0.05), (68, 0.05))),
    (0.6, 0.0, 75, 1000, ((67, 0.1), (66, 0.4), (56, 0.4), (78, 0.1))),
    (0.7, 0.0, 72, 1000, ((54, 0.2), (68, 0.4), (63, 0.3), (61, 0.05), (60, 0.05))),
    (0.5, 0.0, 1000, 220, ((54, 0.3), (65, 0.4), (55, 0.1), (71, 0.1), (60, 0.1))),
    (0.5, 0.0, 70, 1000, ((62, 0.4), (54, 0.3), (60, 0.1), (55, 0.1), (61, 0.05), (68, 0.05))),
    (0.3, 0.0, 1000, 1000, ((54, 0.4), (55, 0.2), (57, 0.1), (65, 0.2), (71, 0.1))),
    (0.5, 0.0, 1000, 220, ((64, 0.4), (54, 0.2), (60, 0.1), (61, 0.1), (55, 0.1), (73, 0.1))),
    (0.8, 0.5, 1000, 1000, ((74, 0.5), (58, 0.4), (78, 0.1))),
    (0.6, -0.5, 1000, 1000, ((74, 0.8), (58, 0.1), (78, 0.1))),
    (0.55, 0.3, 1000, 1000, ((74, 0.1), (58, 0.9))),
)
# mean, spread, (weight, low, high, group). Native position codes 0..16.
_SCALES = (
    (0.15, 0.9, ((90, 20, 88, 6), (10, 0, 60, 8))),
    (0.25, 0.7, ((70, 0, 100, 12), (30, 0, 100, 14))),
    (0.25, 0.67, ((90, 0, 100, 13), (10, 0, 100, 14))),
    (0.35, 0.7, ((10, 0, 50, 0), (70, 20, 90, 7), (20, 29, 70, 8))),
    (0.55, 0.6, ((70, 10, 77, 9), (20, 10, 75, 5), (10, 0, 65, 2))),
    (0.45, 0.65, ((30, 10, 76, 9), (50, 10, 74, 5), (5, 10, 69, 4), (15, 10, 67, 2))),
    (0.4, 0.7, ((30, 10, 79, 9), (40, 10, 78, 5), (10, 10, 70, 4), (20, 10, 77, 2))),
    (0.37, 0.5, ((10, 5, 75, 0), (10, 5, 85, 1), (20, 0, 80, 7), (60, 35, 84, 8))),
    (0.4, 0.7, ((40, 15, 64, 0), (15, 15, 63, 1), (30, 10, 65, 7), (15, 25, 74, 8))),
    (0.5, 0.6, ((25, 10, 61, 0), (25, 15, 62, 1), (10, 15, 81, 8), (40, 0, 80, 7))),
    (0.4, 0.6, ((20, 10, 84, 4), (10, 10, 81, 3), (10, 10, 78, 9), (20, 10, 78, 5), (40, 10, 89, 2))),
    (0.4, 0.6, ((15, 10, 88, 4), (10, 10, 88, 3), (10, 10, 79, 9), (20, 10, 78, 5), (45, 10, 90, 2))),
    (0.4, 0.7, ((50, 10, 74, 0), (50, 10, 75, 1))),
    (0.4, 0.7, ((60, 10, 75, 0), (40, 10, 76, 1))),
    (0.4, 0.7, ((40, 10, 78, 0), (60, 10, 80, 1))),
    (0.4, 0.7, ((30, 10, 86, 4), (60, 10, 78, 3), (10, 10, 77, 2))),
    (0.4, 0.7, ((60, 10, 81, 4), (30, 10, 70, 3), (10, 10, 80, 2))),
)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def native_overall(record):
    """USA unboosted integer overall; not the roster grid's estimated overall."""
    raw = record.encode()
    def skill(offset):
        return f32(min(raw[offset], 100) * f32(.01))
    def group(index):
        consistency, kick, height, weight, attributes = _GROUPS[index]
        total = denominator = 0.0
        for offset, share in attributes:
            share = f32(share)
            denominator = f32(denominator + share)
            total = f32(total + skill(offset) * share)
        total = f32(total + (1.0 - skill(0x50)) * f32(consistency) * -.5 * .5)
        total = f32(total / denominator)
        modifier = (1.0 - f32(kick) + skill(0x4b) * f32(kick)
                    if kick >= 0 else 1.0 + skill(0x4b) * f32(kick))
        total = f32(total * modifier)
        total = f32(total + max(0, raw[0x2b] - height) * f32(.005))
        return f32(total + max(0, raw[0x2a] + 150 - weight) * f32(.001))
    mean, spread, rows = _SCALES[raw[0x35]]
    total = 0.0
    for share, low, high, index in rows:
        total = f32(total + ((group(index) * 100.0 - low) * share / (high - low)))
    total = f32(total / sum(row[0] for row in rows))
    total = f32((total - f32(mean)) * f32(.7) / f32(spread) + f32(.3))
    return math.floor(f32(max(0.0, min(1.0, total)) * 100) + .5)


def tier_id(tier):
    if type(tier) is int and 0 <= tier < len(TIERS):
        return tier
    for index, row in enumerate(TIERS):
        if tier == row[0]:
            return index
    raise ValueError('Choose Original creation, 1st Day, 2nd Day, 3rd Day or Undrafted.')


def starting_rank(tier, position, count=8):
    """Zero-based rank; Undrafted goes last among this club's position group."""
    tier = tier_id(tier)
    if tier == 4:
        return min(7, max(0, count - 1))
    if not tier:
        return 0
    return ((2, 3, 4) if position in (3, 4) else (1, 2, 2))[tier - 1]


def apply_tier(record, tier):
    """Move template skills toward the requested native OVR, retaining styles.

    A bounded sweep adjusts one point at a time and refuses to overshoot.
    Non-rating fields, style/parity bytes and prototype differences survive.
    """
    tier = tier_id(tier)
    if not tier:
        return
    goal = TIERS[tier][1]
    from .nfl2k5_my_career_progression import FIELDS
    for _ in range(100):
        moved = False
        for _, field, _ in FIELDS:
            score = native_overall(record)
            if score == goal:
                return
            old = record.get(field)
            value = old + (1 if score < goal else -1)
            if not 0 <= value <= 100:
                continue
            record.set(field, value)
            after = native_overall(record)
            if (score < goal < after) or (after < goal < score):
                record.set(field, old)
            else:
                moved = True
        if not moved:
            break
    if native_overall(record) != goal:
        raise ValueError('This player cannot reach the prospect overall. Choose another template or Original creation.')



class HostTemplate:
    """An authored fourth QB row, only for preparing a save in Studio.

    Gunslinger uses a stronger arm (95), lower accuracy (78) and lower reads
    (72) than Pocket, with all other Pocket values retained. This is a distinct
    rating vector, not a label alias or a change to the native 51-row table.
    """
    position_code = 0
    variant = 3
    index = None
    label = 'Gunslinger QB'

    def ratings(self):
        ratings = roster.templates_for_position(0)[0].ratings()
        ratings.update(pass_arm_strength=95, pass_accuracy=78, pass_read_coverage=72)
        return ratings


def templates_for(position, *, scheme='retail'):
    choices = roster.templates_for_position(position, scheme=scheme)
    return choices + (HostTemplate(),) if position == 0 else choices


def prototypes(position, *, scheme='retail'):
    """One label per real rating template; only QB has an authored fourth row."""
    choices = templates_for(position, scheme=scheme)
    order = (1, 3, 2, 0) if position == 0 else range(len(choices))
    return tuple((choices[i].label, choices[i].variant) for i in order)
