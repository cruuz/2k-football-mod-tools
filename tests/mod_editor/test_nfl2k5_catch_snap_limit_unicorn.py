"""Defender catch snap limit on the game's own catch code (Unicorn). No game boot, no completed interception.

The real catch metadata initializer, the real selector 0x1E78A0, the real plan setup 0x1E57B0 and the real catch update
with its alignment helper run on supplied objects (tools/nfl2k5_catch_snap_replay.py; the ai3-pickwarp grid of 10/11:
a CPU cornerback 1..4 yards in front of, beside and behind the arrival point of a 0.45 s forward pass, and the same
grid for a receiver). The retail executable and the same executable with the owner applied are compared:

- 8 of the 12 defender cases are native catch attempts, 5 remain with the half-yard limit (the three refused ones are
  the ones whose planned slide is over half a yard), every receiver record is byte-for-byte retail;
- a refused plan is retail's own non-catch answer: the setup stores no slide on the clip and the alignment helper moves
  nothing, while every kept plan is byte-for-byte retail and slides exactly as retail does;
- human-controlled defenders, kicked and backward balls, and the AI's probe request are byte-for-byte retail;
- the setup's reach cap alone (the selector hook put back to retail bytes) limits the slide the clip stores to half a yard
  for a CPU defender, whatever plan reaches it, and changes nothing else;
- the catch action's begin callback runs to completion on a refused plan, fresh and from a cached plan.

NFL2K5_V08_XBE may point at a released SOFTDRINK default.xbe (the v0.8 executable); the same checks then run on it.
Skipped without Unicorn or the pinned retail extraction. Slow (each executable initializes ~480 catch records).
"""
from pathlib import Path
import math
import os
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_catch_snap_limit as cs
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    from tools.nfl2k5_catch_snap_replay import CatchSnapReplay, DIRECTIONS, DISTANCES, CM_PER_YARD
    import unicorn  # noqa: F401
except ImportError:  # pragma: no cover
    CatchSnapReplay = None

# ai3-pickwarp's measured planned slides (yards) for the supplied CPU cornerback grid; a native attempt only where listed
EXPECTED_SLIDES = {("front", 2): 0.457322, ("front", 3): 0.491962, ("front", 4): 0.508038,
                   ("beside", 1): 0.599379,
                   ("behind", 1): 0.467469, ("behind", 2): 0.210518, ("behind", 3): 0.108285, ("behind", 4): 0.865640}
REFUSED = {("front", 4), ("beside", 1), ("behind", 4)}


def slide_yards(selection):
    return math.hypot(selection["correction"][0], selection["correction"][2]) / CM_PER_YARD


class Grid:
    """Mixin: the checks, run once per executable."""
    label = ""

    @classmethod
    def build(cls, base):
        cls.base_payload = base
        cls.owner_payload, _ = cs.apply(base)
        cls.old = CatchSnapReplay(base)
        cls.new = CatchSnapReplay(cls.owner_payload)
        # the same executable with the selector hook put back to retail bytes: the cap stub alone
        cls.cap_only = CatchSnapReplay(cls.owner_payload, patches=[(cs.HOOK[1], cs.HOOK[2])])
        cls.old_grid, cls.new_grid = cls.old.grid(), cls.new.grid()

    def cell(self, grid, direction, yards, defender=True):
        return next(r for r in grid if (r["direction"], r["distance_yards"], r["defender"]) == (direction, yards, defender))

    def test_catch_metadata_initialized_identically(self):
        self.assertEqual(self.old.initialization, self.new.initialization)
        self.assertEqual(self.old.initialization["records_including_aliases"], 482)

    def test_retail_reproduces_the_ai3_grid(self):
        attempts = {(r["direction"], r["distance_yards"]): r for r in self.old_grid if r["defender"] and r["selection"]["returned"]}
        self.assertEqual(set(attempts), set(EXPECTED_SLIDES), self.label)
        for key, row in attempts.items():
            self.assertAlmostEqual(slide_yards(row["selection"]), EXPECTED_SLIDES[key], places=5, msg=str(key))
            self.assertEqual(row["selection"]["accepted"], 1)
            self.assertAlmostEqual(row["motion"]["correction_yards"], EXPECTED_SLIDES[key], places=5)

    def test_eight_defender_attempts_become_five(self):
        old = {(r["direction"], r["distance_yards"]) for r in self.old_grid if r["defender"] and r["selection"]["returned"]}
        new = {(r["direction"], r["distance_yards"]) for r in self.new_grid if r["defender"] and r["selection"]["returned"]}
        self.assertEqual((len(old), len(new)), (8, 5), self.label)
        self.assertEqual(old - new, REFUSED)
        self.assertEqual(new - old, set())
        for key in new:
            self.assertLessEqual(EXPECTED_SLIDES[key], cs.LIMIT_YARDS)

    def test_kept_plans_and_every_receiver_are_byte_for_byte_retail(self):
        for old, new in zip(self.old_grid, self.new_grid):
            key = (old["direction"], old["distance_yards"])
            if old["defender"] and key in REFUSED:
                continue
            self.assertEqual(new["selection"], old["selection"], (key, old["defender"]))
            if old["motion"] is not None:
                self.assertEqual(new["motion"], old["motion"], (key, old["defender"]))

    def test_refused_plans_are_retails_non_catch_answer_and_slide_nothing(self):
        for key in sorted(REFUSED):
            old, new = self.cell(self.old_grid, *key), self.cell(self.new_grid, *key)
            self.assertTrue(old["selection"]["returned"] and old["selection"]["accepted"], key)
            self.assertFalse(new["selection"]["returned"], key)
            self.assertEqual(new["selection"]["accepted"], 0, key)
            self.assertEqual(new["selection"]["rate"], 1.0, key)
            self.assertEqual(new["selection"]["clip"], old["selection"]["clip"], key)       # a valid unaccepted record
            self.assertIsNone(new["motion"], key)                                           # no accepted plan to run
            # the plan setup on the refused record: nothing stored on the clip, and the alignment helper moves nothing
            self.new.arrange(*key)
            self.new.select()
            self.new.setup()
            self.assertEqual(self.new.plan_effects()["stored_correction"], (0.0, 0.0), key)
            ticks = self.new.run_ticks()
            self.assertEqual(ticks["max_alignment_step_yards"], 0.0, key)
            self.assertGreater(ticks["ticks"], 0, key)
            # the same position without the owner slides him
            self.old.arrange(*key)
            self.old.select()
            self.old.setup()
            self.assertGreater(self.old.run_ticks()["total_alignment_yards"], 0.0, key)

    def test_human_defender_kick_and_probe_are_byte_for_byte_retail(self):
        for kind in (dict(cpu=False), dict(ball_kind=3)):
            for direction in DIRECTIONS:
                for yards in DISTANCES:
                    self.old.arrange(direction, yards, **kind)
                    a = self.old.select()
                    self.new.arrange(direction, yards, **kind)
                    b = self.new.select()
                    self.assertEqual(b, a, (kind, direction, yards))
        for direction in DIRECTIONS:
            for yards in DISTANCES:
                self.old.arrange(direction, yards)
                a = self.old.select(0)
                self.new.arrange(direction, yards)
                b = self.new.select(0)
                self.assertEqual(b, a, ("probe", direction, yards))

    def stored_yards(self, replay, key, *, replan=False, ticks=0, **arrange):
        replay.arrange(*key, **arrange)
        selection = replay.select()
        if not (selection["returned"] and selection["accepted"]):
            return None
        replay.advance_ball(ticks)
        replay.setup(replan=replan)
        return math.hypot(*replay.plan_effects()["stored_correction"]) / CM_PER_YARD

    def test_the_reach_cap_alone_limits_the_stored_slide_of_a_cpu_defender(self):
        for key in sorted(EXPECTED_SLIDES):
            before = self.stored_yards(self.old, key)
            after = self.stored_yards(self.cap_only, key)
            self.assertIsNotNone(before, key)                                   # the retail selector accepts all eight
            self.assertIsNotNone(after, key)                                    # the selector hook is off in this run
            if EXPECTED_SLIDES[key] <= cs.LIMIT_YARDS:
                self.assertEqual(after, before, key)                            # a short slide is untouched
            else:
                self.assertGreater(before, cs.LIMIT_YARDS, key)
                self.assertAlmostEqual(after, cs.LIMIT_YARDS, places=3, msg=str(key))   # scaled down to exactly half a yard

    def test_the_cap_keeps_the_direction_of_the_slide(self):
        for key in sorted(REFUSED):
            self.old.arrange(*key)
            self.old.select()
            self.old.setup()
            x0, z0 = self.old.plan_effects()["stored_correction"]
            self.cap_only.arrange(*key)
            self.cap_only.select()
            self.cap_only.setup()
            x1, z1 = self.cap_only.plan_effects()["stored_correction"]
            self.assertAlmostEqual(x1 / math.hypot(x1, z1), x0 / math.hypot(x0, z0), places=4, msg=str(key))
            self.assertAlmostEqual(z1 / math.hypot(x1, z1), z0 / math.hypot(x0, z0), places=4, msg=str(key))

    def test_the_cap_leaves_receivers_humans_and_kicks_alone(self):
        for key in sorted(EXPECTED_SLIDES):
            self.assertEqual(self.stored_yards(self.cap_only, key, defender=False), self.stored_yards(self.old, key, defender=False), key)
            self.assertEqual(self.stored_yards(self.cap_only, key, cpu=False), self.stored_yards(self.old, key, cpu=False), key)
            self.assertEqual(self.stored_yards(self.cap_only, key, ball_kind=3), self.stored_yards(self.old, key, ball_kind=3), key)

    def test_a_cached_plan_planned_again_a_few_ticks_later_stays_within_the_limit(self):
        for key in sorted(EXPECTED_SLIDES):
            for ticks in range(5):
                after = self.stored_yards(self.new, key, replan=True, ticks=ticks)
                if after is not None:
                    self.assertLessEqual(after, cs.LIMIT_YARDS + 1e-4, (key, ticks))
                before = self.stored_yards(self.cap_only, key, replan=True, ticks=ticks)
                if before is not None:
                    self.assertLessEqual(before, cs.LIMIT_YARDS + 1e-4, (key, ticks))

    def test_random_geometry_follows_the_policy(self):
        """70 seeded states (arrival point, flight time, catch context, a CPU cornerback within 3 yards of the arrival): where
        the retail selector plans an aligned catch longer than half a yard the owner returns the demoted non-catch record,
        everywhere else the record is byte-for-byte retail."""
        rng = random.Random(2026)
        counts = {"attempts": 0, "long": 0, "kept": 0}
        for index in range(70):
            arrival = (rng.uniform(-200, 200), rng.uniform(100, 200), rng.uniform(800, 1400))
            flight, context = rng.choice([0.35, 0.45, 0.6, 0.9]), rng.choice([0.4, 0.6, 0.8, 1.0])
            position = (arrival[0] + rng.uniform(-3, 3) * CM_PER_YARD, arrival[2] + rng.uniform(-3, 3) * CM_PER_YARD)
            self.old.arrange_at(position, arrival, flight=flight, context=context)
            before = self.old.select()
            self.new.arrange_at(position, arrival, flight=flight, context=context)
            after = self.new.select()
            if not (before["returned"] and before["accepted"]):
                self.assertEqual(after, before, index)
                continue
            counts["attempts"] += 1
            self.assertLessEqual(slide_yards(before), 1.0 + 1e-3, index)               # retail's own bound: reach + allowance
            aligned = (before["flags"] >> 8) & 3 == 1
            if aligned and slide_yards(before) > cs.LIMIT_YARDS:
                counts["long"] += 1
                self.assertFalse(after["returned"], index)
                self.assertEqual((after["accepted"], after["rate"], after["clip"]), (0, 1.0, before["clip"]), index)
            else:
                counts["kept"] += 1
                self.assertEqual(after, before, index)
        self.assertGreaterEqual(counts["long"], 5, counts)
        self.assertGreaterEqual(counts["kept"], 5, counts)

    def test_the_begin_callback_runs_on_a_refused_plan_and_a_kept_plan(self):
        for key in (("front", 2), ("behind", 4), ("beside", 1)):
            for replay, name in ((self.old, "retail"), (self.new, "owner")):
                replay.arrange(*key)
                replay.channels()
                replay.m.put(replay.m.P + 0x200, 0x55)                                  # the action id the begin callback asks with
                replay.m.call(0x1E7B80, ecx=replay.m.P)                                 # completes; no exception
                effects = replay.plan_effects()
                self.assertEqual(effects["action_flags"] & 1, 1, (key, name))           # the action is under way
                refused = name == "owner" and key in REFUSED
                if refused:
                    self.assertEqual(effects["stored_correction"], (0.0, 0.0), key)
                elif key in EXPECTED_SLIDES:
                    self.assertAlmostEqual(math.hypot(*effects["stored_correction"]) / CM_PER_YARD, EXPECTED_SLIDES[key], places=3)


class RetailTests(Grid, unittest.TestCase):
    label = "retail"

    @classmethod
    def setUpClass(cls):
        if CatchSnapReplay is None:
            raise unittest.SkipTest("unicorn is not installed")
        cls.build(retail_xbe())


class ReleasedSoftdrinkTests(Grid, unittest.TestCase):
    label = "released SOFTDRINK executable"

    @classmethod
    def setUpClass(cls):
        path = os.environ.get("NFL2K5_V08_XBE")
        if CatchSnapReplay is None or not path or not Path(path).is_file():
            raise unittest.SkipTest("set NFL2K5_V08_XBE to a released SOFTDRINK default.xbe")
        data = Path(path).read_bytes()
        if len(data) > 16 * 1024 ** 2:
            raise AssertionError("expected a default.xbe, not a disc image")
        cls.build(data)


if __name__ == "__main__":
    unittest.main()
