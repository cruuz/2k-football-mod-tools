"""Independent review of beta 81 D07: the CPU fourth-down go limit must not jump or dip along the field.

Beta 81 capped the Modern 2 table for the own 20 through own 49 only, in bands (one yard, two, three) that do not line up
with the table's region boundary at the own 40, where a tied early game subtracts a yard. It left the midfield and
opponent side untouched. In the shipped 128 MiB v0.10 executable a tied first quarter with 7-minute quarters punts on
4th-and-3 at the own 49 but goes for it on 4th-and-6 at the 50, and goes on 4th-and-2 at the own 39 but punts it at the
own 40 to 44. These tests state the shape a fourth-down chart must have: the yards the CPU will go for never shrink as the
offense advances from its own 20 to the opponent 41 in a neutral game, and never jump by more than two yards per yard line.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_cpu_money_downs as patch

NEUTRAL = (
    ("Q1 4:00 tied, 7-minute quarters", dict(quarter=1, seconds=240, score_margin=0, quarter_seconds=420)),
    ("Q1 4:00 tied, 15-minute quarters", dict(quarter=1, seconds=240, score_margin=0, quarter_seconds=900)),
    ("Q2 6:00 tied, 7-minute quarters", dict(quarter=2, seconds=360, score_margin=0, quarter_seconds=420)),
    ("Q3 5:30 tied, 7-minute quarters", dict(quarter=3, seconds=330, score_margin=0, quarter_seconds=420)),
)
YARDS = range(20, 60)   # own 20 .. opponent 41; inside the opponent 40 the field-goal region legitimately lowers it


def go_limit(own_yard, state):
    """Longest distance (yards) the shipped Modern 2 oracle goes for at this spot; 0 = never."""
    best = 0
    for distance in range(1, 26):
        if patch.decision(level="modern2", down=4, own_yard=own_yard, distance=distance, **state) != "go":
            break
        best = distance
    return best


class FourthDownShapeTests(unittest.TestCase):
    def test_go_limit_never_shrinks_as_the_offense_advances_in_a_neutral_game(self):
        for name, state in NEUTRAL:
            limits = [go_limit(y, state) for y in YARDS]
            drops = [(y, limits[i - 1], limits[i]) for i, y in enumerate(YARDS) if i and limits[i] < limits[i - 1]]
            with self.subTest(state=name):
                self.assertEqual(drops, [], f"{name}: limit by own yard {dict(zip(YARDS, limits))}")

    def test_go_limit_has_no_cliff_between_adjacent_yard_lines(self):
        for name, state in NEUTRAL:
            limits = [go_limit(y, state) for y in YARDS]
            jumps = [(y, limits[i - 1], limits[i]) for i, y in enumerate(YARDS) if i and limits[i] - limits[i - 1] > 2]
            with self.subTest(state=name):
                self.assertEqual(jumps, [], f"{name}: limit by own yard {dict(zip(YARDS, limits))}")

    def test_reported_midfield_neighbour_is_consistent_with_the_reported_fix(self):
        """D07 fixed own 48/49 on 4th-and-5 (punt). One yard on, the same tied first quarter must not go on 4th-and-6."""
        state = dict(quarter=1, seconds=240, score_margin=0, quarter_seconds=420)
        self.assertEqual(patch.decision(level="modern2", down=4, own_yard=49, distance=5, **state), "retail")
        self.assertNotEqual(patch.decision(level="modern2", down=4, own_yard=50, distance=6, **state), "go")
        self.assertNotEqual(patch.decision(level="modern2", down=4, own_yard=51, distance=6, **state), "go")


if __name__ == "__main__":
    unittest.main()
