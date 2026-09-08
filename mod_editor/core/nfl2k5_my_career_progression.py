"""M3 purchase policy. EXPERIMENTAL / UNWITNESSED balance choices.

Caps limit purchases, never lower a template or native progression rating.
Physical/general skills cap at 90, role skills at 99, unrelated specialist
skills at 75. Style bytes, position, identity and contracts are never sold.
"""
from . import nfl2k5_roster_records as roster

FIELDS = tuple((roster.RATING_OFFSETS[key], key, roster.RATING_LABELS[key])
               for key in roster.RATING_BYTE_ORDER if key not in roster.STYLE_RATINGS)
SPECIALISTS = {
    "pass_arm_strength": (0,), "pass_accuracy": (0,), "pass_read_coverage": (0,),
    "kick_power": (1, 2), "kick_accuracy": (1, 2),
    "coverage": (4, 5, 6, 10, 11), "run_route": (3, 7, 8, 9),
    "tackle": (4, 5, 6, 10, 11, 15, 16), "break_tackle": (0, 3, 7, 8, 9),
    "catch": (3, 7, 8, 9), "run_blocking": (8, 9, 12, 13, 14),
    "pass_blocking": (7, 8, 9, 12, 13, 14),
    "pass_rush": (10, 11, 15, 16), "run_coverage": (4, 5, 6, 10, 11, 15, 16),
}
CAPS = tuple(
    tuple((99 if position in SPECIALISTS[key] else 75) if key in SPECIALISTS else 90
          for _, key, _ in FIELDS) for position in range(17))


def cost(value):
    if type(value) is not int or not 0 <= value < 99:
        return 0
    return 10 if value < 70 else 15 if value < 80 else 25 if value < 90 else 40 if value < 95 else 60
