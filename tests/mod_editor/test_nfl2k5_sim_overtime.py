"""Simulated (CPU-vs-CPU) overtime follows the modern NFL rule in the patched XBE.

The full-game cases run the retail franchise simulator in Unicorn from a natural
fourth-quarter gun into overtime; the defensive-score cases call the patched
rule's own code with a synthetic overtime state because the retail simulator
almost never produces a defensive score in overtime.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_overtime as ot  # noqa: E402

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None


class SimOvertimeRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not HAVE_UNICORN:
            raise unittest.SkipTest("unicorn is not installed")
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes, signed_save
        try:
            cls.retail = retail_bytes()
            cls.save = signed_save()
        except unittest.SkipTest as exc:
            raise unittest.SkipTest(str(exc))
        cls.patched = ot.apply(cls.retail)[0]

    def machine(self):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = Machine(self.patched, trace_writes=False)
        m.load_franchise(self.save)
        return m

    def overtime_game(self, seed: int):
        m = self.machine()
        m.seed(seed)
        for address, value in ((0xE5FF80, 4), (0xE576A4, 8), (0xE6000C, 5), (0xE60010, 5)):
            m.put(address, value)
        m.call(0x77AE0, ecx=m.team_base, budget=500_000)
        m.call(0x77B20, ecx=m.team_base + 500, budget=500_000)
        m.call(0x10B280, ecx=m.team_base, edx=m.team_base + 500,
               args=(0, 1, 0, 0, 0, 0), budget=3_000_000)
        m.call(0x10B250, budget=1_000_000)
        # End of the fourth quarter, tied: the native evaluator advances to overtime.
        m.put(ot.SIM_PERIOD_INDEX, 3)
        m.f32(ot.SIM_CLOCK_FRACTION, 0.0)
        m.put(ot.SIM_KIND, 0)
        m.put(ot.SIM_STATE, 2)
        m.put(ot.SIM_OT_INIT, 0)
        if m.call(0x10B250, budget=3_000_000) != 4:      # the quarter did not end level
            return None
        rows = []
        for _ in range(200):
            result = m.call(0x10B250, budget=2_000_000)
            rows.append({
                "result": result,
                "state": m.get(ot.SIM_STATE),
                "kind": m.get(ot.SIM_KIND),
                "offense": "home" if m.get(ot.SIM_OFFENSE) == ot.SIM_HOME_TEAM else "away",
                "scores": (m.call(0x250DD0, ecx=0, edx=0, budget=200_000),
                           m.call(0x250DD0, ecx=1, edx=0, budget=200_000)),
            })
            if result in (5, -1):
                break
        return rows

    def test_first_possession_field_goal_and_touchdown_are_answered(self) -> None:
        games = 0
        first_kinds = set()
        for seed in range(1, 17):
            rows = self.overtime_game(seed)
            if rows is None or not rows or rows[-1]["result"] != 5:
                continue
            games += 1
            first_offense = rows[0]["offense"]
            score_index = next(index for index, row in enumerate(rows)
                               if row["scores"] != (0, 0))
            first = rows[score_index]
            home, away = first["scores"]
            scorer = "home" if home > away else "away"
            self.assertEqual(scorer, first_offense, f"seed {seed}: the opening possession scored")
            delta = max(home, away)
            self.assertIn(delta, (3, 6, 7), f"seed {seed}: opening score {first['scores']}")
            first_kinds.add(delta)
            # The modern rule gives the other team a possession even after a touchdown.
            self.assertTrue(any(row["offense"] != first_offense and row["kind"] in (0, 4)
                                for row in rows[score_index + 1:]),
                            f"seed {seed}: the opponent never possessed after {first['scores']}")
            self.assertGreater(len(rows), score_index + 1,
                               f"seed {seed}: the game ended on the first possession")
        self.assertGreaterEqual(games, 10, "too few completed overtime games")
        self.assertIn(3, first_kinds, "no first-possession field goal in the sample")
        self.assertTrue({6, 7} & first_kinds, "no first-possession touchdown in the sample")

    def rule(self, *, offense: str, kind: int, flags: int, last: tuple[int, int],
             scores: tuple[int, int]) -> tuple[int, int]:
        """Call the patched rule with a synthetic overtime state."""

        m = self.machine()
        home, away = scores
        m.put(ot.SIM_PERIOD_INDEX, 4)
        m.put(ot.SIM_OFFENSE, ot.SIM_HOME_TEAM if offense == "home" else 0x00A96E80)
        m.put(ot.SIM_DEFENSE, 0x00A96E80 if offense == "home" else ot.SIM_HOME_TEAM)
        m.put(ot.SIM_KIND, kind)
        m.put(ot.SIM_OT_FLAGS, flags)
        m.put(ot.SIM_OT_INIT, 1)
        m.uc.mem_write(ot.SIM_OT_LAST_HOME, struct.pack("<HH", last[0], last[1]))
        m.put(ot.SIM_STATE, 0)
        offense_score = home if offense == "home" else away
        defense_score = away if offense == "home" else home
        result = m.call(ot.cave_labels()["sim_check"], ecx=0, edx=4,
                        ebx=defense_score, edi=offense_score, budget=100_000)
        return result, m.get(ot.SIM_STATE)

    def test_defensive_score_ends_the_game(self) -> None:
        # A pick-six while the offense leads: the defense's touchdown still ends it.
        result, state = self.rule(offense="home", kind=0, flags=3, last=(3, 0), scores=(3, 9))
        self.assertEqual((result, state), (5, 0x12))
        # A safety while the defense still trails: any defensive score ends it.
        result, state = self.rule(offense="home", kind=0, flags=3, last=(3, 0), scores=(3, 2))
        self.assertEqual((result, state), (5, 0x12))

    def test_turnover_on_the_opening_possession_ends_after_the_second_team_scores(self) -> None:
        rows = self.overtime_game(217)
        self.assertIsNotNone(rows)
        self.assertTrue(any(row["state"] == 11 and row["offense"] == "away" for row in rows))
        self.assertEqual(rows[-1]["scores"], (3, 0))
        self.assertEqual(rows[-1]["result"], 5)

    def test_offensive_scores_follow_both_possessions(self) -> None:
        # Field goal on the opening possession: the opponent still gets the ball.
        result, state = self.rule(offense="home", kind=0, flags=1, last=(0, 0), scores=(3, 0))
        self.assertEqual((result, state), (0, 0))
        # Touchdown on the opening possession: same.
        result, state = self.rule(offense="home", kind=4, flags=1, last=(0, 0), scores=(6, 0))
        self.assertEqual((result, state), (0, 0))
        # Answering touchdown that takes the lead after both possessions: game over.
        result, state = self.rule(offense="away", kind=4, flags=3, last=(3, 0), scores=(3, 6))
        self.assertEqual((result, state), (5, 0x12))
        # Answering field goal that ties after both possessions: sudden death continues.
        result, state = self.rule(offense="away", kind=0, flags=3, last=(3, 0), scores=(3, 3))
        self.assertEqual((result, state), (0, 0))
        # A score that still leaves the offense behind does not end the game.
        result, state = self.rule(offense="away", kind=0, flags=3, last=(10, 3), scores=(10, 6))
        self.assertEqual((result, state), (0, 0))


if __name__ == "__main__":
    unittest.main()
