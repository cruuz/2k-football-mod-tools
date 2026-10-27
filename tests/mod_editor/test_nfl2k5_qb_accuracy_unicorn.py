"""QB accuracy owner, native: the game's own target, accuracy, launch and flight code on supplied throws.

Retail and retail + the owner run the same fixtures (tests/nfl2k5_qb_accuracy_native.py). Proves: a throw with no
miss (a set QB) and every throw of 40 yd or more is byte-for-byte retail; on the run the miss shrinks by exactly the
cave's Pass Accuracy factor; better passers miss less; misses are no longer always ahead of the receiver; the cave
preserves the registers, the x87 stack and the routine's other outputs. Skipped without the pinned retail XBE.
"""
from pathlib import Path
import statistics
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_qb_accuracy as accuracy
from mod_editor.core import nfl2k5_qb_accuracy_code as assembly
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    import unicorn  # noqa: F401
except ImportError:  # pragma: no cover
    unicorn = None

ACCURACIES = (.55, .7, .8, .9, .97)
SEEDS = (1, 2, 3, 4, 5, 6)
SHORT = ("drag3", "drag5", "drag5_back", "out5", "out10", "out14", "out10_left", "slant5", "slant8", "dig12", "curl10",
         "flat2", "hitch5")


def without_quick_lead(payload):
    """The installed owner with only the b777 qb4 placement tail put back to retail (test fixture, never shipped)."""
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    offset = XbeImage(payload).offset(accuracy.LEAD[1], len(accuracy.LEAD[2]))
    return payload[:offset] + accuracy.LEAD[2] + payload[offset + len(accuracy.LEAD[2]):]


def k_points():
    values = struct.unpack_from("<12f", assembly.CODE, assembly.LABELS["k_acc_points"])
    return list(zip(values[0::2], values[1::2]))


def interpolate(points, x):
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def expected_scale(accuracy_value, radius_cm):
    weight = min(1., max(0., (3657.6 - radius_cm) * 0.000546806649))
    return 1 + weight * (interpolate(k_points(), accuracy_value) - 1), weight


@unittest.skipIf(unicorn is None, "unicorn is required for the native probe")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_qb_accuracy_native import AccuracyMachine
        retail = retail_xbe()
        cls.before = AccuracyMachine(retail)
        # b777 qb4's quick-throw placement (LEAD) moves some short targets on purpose; it has its own native test
        # (test_nfl2k5_qb_accuracy_quick_lead.py). These accuracy assertions run the owner with that tail retail.
        applied = accuracy.apply(retail)[0]
        cls.after = AccuracyMachine(without_quick_lead(applied))
        cls.full = AccuracyMachine(applied)                        # b778 qa1: screens are checked on the whole owner
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        cls.after_image = XbeImage(applied)
        cls.rows = {}
        for state in ("set", "roll_human", "roll_cpu"):
            for route in SHORT + ("seam20", "go30", "post25"):
                for value in ACCURACIES:
                    for seed in SEEDS:
                        key = (state, route, value, seed)
                        cls.rows[key] = (cls.before.throw(route, state=state, accuracy=value, seed=seed),
                                         cls.after.throw(route, state=state, accuracy=value, seed=seed))

    def test_no_miss_and_deep_throws_are_retail(self):
        unchanged = 0
        for (state, route, _v, _s), (old, new) in self.rows.items():
            # no capture: the routine returned before the miss (a target within 1 yd of the line, e.g. a flat)
            miss = old["capture"]["exit"]["miss_cm"] if "exit" in old["capture"] else 0.
            self.assertEqual("exit" in old["capture"], "exit" in new["capture"])
            if miss <= 0 or old["radius_yd"] * 91.44 >= 3657.6:
                self.assertEqual(old["raw"], new["raw"], (state, route))
                self.assertEqual(old["launch"], new["launch"], (state, route))
                unchanged += 1
        self.assertGreater(unchanged, 300)
        for (state, route, _v, _s), (old, new) in self.rows.items():
            if state == "set" and route in SHORT:
                self.assertEqual(old["raw"], new["raw"], route)

    def test_miss_scaled_by_pass_accuracy_and_heading_flip(self):
        scaled = flipped = 0
        for (state, route, value, seed), (old, new) in self.rows.items():
            if "exit" not in old["capture"]:
                continue
            entry, exit_old, exit_new = old["capture"]["entry"], old["capture"]["exit"], new["capture"]["exit"]
            if exit_old["miss_cm"] <= 0:
                continue
            factor, weight = expected_scale(entry["pass_accuracy"], old["radius_yd"] * 91.44)
            self.assertAlmostEqual(exit_new["miss_cm"], exit_old["miss_cm"] * factor, delta=1e-3 * exit_old["miss_cm"] + 1e-3)
            self.assertAlmostEqual(exit_new["height_error"], exit_old["height_error"] * factor,
                                   delta=1e-3 * abs(exit_old["height_error"]) + 1e-3)
            turn = (exit_new["heading"] - exit_old["heading"]) & 0xFFFF
            self.assertIn(turn, (0, 0x8000) if weight > 0 else (0,))
            scaled += weight > 0
            flipped += turn == 0x8000
        self.assertGreater(scaled, 200)
        self.assertGreater(flipped, scaled // 4)
        self.assertLess(flipped, 3 * scaled // 4)

    def test_registers_x87_and_other_outputs_preserved(self):
        for (_state, _route, _v, _s), (old, new) in self.rows.items():
            if "exit" not in new["capture"]:
                continue
            a, b = old["capture"]["exit"], new["capture"]["exit"]
            self.assertEqual(a["top"], b["top"])
            for name in ("EAX", "ECX", "EDX", "EBX", "ESP", "EBP", "EDI"):
                self.assertEqual(a["regs"][name], b["regs"][name], name)
            self.assertIn((b["regs"]["ESI"] - a["regs"]["ESI"]) & 0xFFFFFFFF, (0, 0x8000))

    def test_on_the_run_rating_spread_and_bias(self):
        def run_rows(which, value=None):
            return [pair[which] for (state, route, v, _s), pair in self.rows.items()
                    if state == "roll_human" and route in SHORT and (value is None or v == value)]
        before = {v: statistics.mean(r["miss_yd"] for r in run_rows(0, v)) for v in ACCURACIES}
        after = {v: statistics.mean(r["miss_yd"] for r in run_rows(1, v)) for v in ACCURACIES}
        self.assertEqual(len(set(round(m, 6) for m in before.values())), 1)   # retail: the rating does not matter
        self.assertEqual(list(after.values()), sorted(after.values(), reverse=True))
        self.assertLess(after[.9], 0.7 * before[.9])
        self.assertLess(after[.97], after[.55] - 0.4)
        self.assertLessEqual(after[.55], before[.55] + 1e-6)
        ahead_before = statistics.mean(r["ahead_yd"] for r in run_rows(0))
        ahead_after = statistics.mean(r["ahead_yd"] for r in run_rows(1))
        self.assertLess(ahead_after, ahead_before / 2 + 0.05)

    def test_screen_passes_are_retail_and_lead_a_moving_back(self):
        """b778 qa1: the owner leaves screen routes (kind 9) to retail. Retail leads a MOVING screen receiver by his
        velocity (the fallback 0x2F4350); b777's screen operand aimed at his route spot instead, which is behind a back
        who runs on through it (the v0.6.1 bug). A receiver standing at his spot is aimed at his spot either way."""
        from nfl2k5_qb_accuracy_native import screen_target
        cases = (((4., -4.5), (7., 2.), (11., -1.5), 1.0),       # running out to his spot
                 ((11., -1.5), (7., .5), (11., -1.5), 0.),       # at his spot, still running
                 ((13., -1.3), (7., .5), (11., -1.5), -.3),      # past his spot, still running
                 ((11., -1.5), (0., 0.), (11., -1.5), 0.))       # standing at his spot
        for position, velocity, spot, due in cases:
            old = screen_target(self.before, position, velocity, spot=spot, due=due)
            new = screen_target(self.full, position, velocity, spot=spot, due=due)
            self.assertEqual(old, new)
            if any(velocity):
                self.assertGreater(new["velocity_fallback"], 0)
                self.assertAlmostEqual(new["aim"][0], new["receiver"][0], delta=.6)    # on him at arrival
                self.assertGreater(new["aim"][1], new["receiver"][1])                  # behind the line: +1 yd up
                self.assertLess(new["aim"][1] - new["receiver"][1], 1.25)
            else:
                self.assertAlmostEqual(new["aim"][0], spot[0], places=3)
        self.assertEqual(self.after_image.read(0x226832, 3), bytes.fromhex("83fa09"))   # cmp edx, 9: retail

    def test_cpu_on_the_run_throws_arrive_higher(self):
        low = [sum(pair[i]["ball_height_cm"] < 100 for (state, route, v, _s), pair in self.rows.items()
                   if state == "roll_cpu" and route in SHORT and v >= .8) for i in (0, 1)]
        self.assertLess(low[1], low[0] / 2)


if __name__ == "__main__":
    unittest.main()
