"""Bounded native proofs for CPU QB skill tiers (b779 gp1). No game boot, rendered play or witnessed throw.

The real openness function 0x199F40, the real picker 0x1985E0 and the real curve interpolator execute from the
pinned USA retail default.xbe (skipped when absent) with the tier owner applied. Receivers and defenders are the
same supplied window cases as the zone-window proofs; the QB's Pass Read Coverage is the supplied input, run through
the native threshold curve 0x50C394 as patched.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_cpu_qb_reads as reads
from tests.mod_editor.test_nfl2k5_cpu_qb_reads_unicorn import CASES, score
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.nfl2k5_cpu_ai_native import OpenMachine, ReadsMachine, uc

# Pass Read Coverage of the QB classes in the SOFTDRINK roster (rt1 report, v0.6.1 ratings): rookie / low reader,
# average starter, strong starter, elite.
TIERS = {"rookie / low reader": 0.45, "average starter": 0.72, "strong starter": 0.85, "elite": 0.97}
THROWN_AT = {   # which window cases a QB class adopts (score >= threshold), proved below through the native picker
    "rookie / low reader": {"zone defender 6 yd off", "zone defender 8 yd off", "man 1 yd behind", "man 1.5 yd behind",
                            "man 2 yd behind", "man 3 yd behind", "zone defender 14 yd off", "wide open"},
}


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class SkillTierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.zone, _ = reads.apply(cls.retail, zone_windows=True)
        cls.tiers, _ = reads.apply(cls.retail, zone_windows=True, tiers=True)
        cls.scores = {name: score(cls.tiers, name, 1)[0] for name in CASES}
        cls.retail_scores = {name: score(cls.retail, name, 1)[0] for name in CASES}
        cls.threshold = {}
        cls.retail_threshold = {}
        for payload, store in ((cls.tiers, cls.threshold), (cls.retail, cls.retail_threshold)):
            m = OpenMachine(payload)
            for label, prc in TIERS.items():
                store[label] = m.curve(0x50C394, prc)

    def adopts(self, payload, value, threshold):
        m = ReadsMachine(payload)
        m.rows([dict(scores=[value, -1e30, -1e30, -1e30], yards=8), dict(scores=[-1e30] * 4, yards=14)])
        return m.native_pick(threshold) == 0

    def accepted(self, payload, scores, thresholds, label):
        return {name for name, value in scores.items() if self.adopts(payload, value, thresholds[label])}

    def test_native_threshold_curve_is_the_tier_curve(self):
        for label, prc in TIERS.items():
            lo = max(i for i, x in enumerate(reads.THRESHOLD_X) if x <= prc) if prc > reads.THRESHOLD_X[0] else 0
            hi = min(lo + 1, len(reads.THRESHOLD_X) - 1)
            x0, x1 = reads.THRESHOLD_X[lo], reads.THRESHOLD_X[hi]
            y0, y1 = reads.TIER_THRESHOLD_Y[lo], reads.TIER_THRESHOLD_Y[hi]
            expected = y0 if x1 == x0 else y0 + (prc - x0) * (y1 - y0) / (x1 - x0)
            self.assertAlmostEqual(self.threshold[label], expected, places=5, msg=label)
        ordered = [self.threshold[label] for label in TIERS]
        self.assertEqual(ordered, sorted(ordered), "a stronger reader demands more openness")

    def test_retail_every_class_throws_into_zones_and_a_weak_reader_is_the_most_patient(self):
        for label in TIERS:
            accepted = self.accepted(self.retail, self.retail_scores, self.retail_threshold, label)
            self.assertIn("zone defender in the window", accepted, label)
            self.assertIn("zone defender 3 yd off", accepted, label)
        weak = self.accepted(self.retail, self.retail_scores, self.retail_threshold, "rookie / low reader")
        elite = self.accepted(self.retail, self.retail_scores, self.retail_threshold, "elite")
        self.assertLess(len(weak & {"man step for step", "man 1 yd behind", "man 1.5 yd behind"}),
                        len(elite & {"man step for step", "man 1 yd behind", "man 1.5 yd behind"}))

    def test_tiers_nobody_throws_into_the_window_but_weak_readers_force_covered_throws(self):
        rows = {label: self.accepted(self.tiers, self.scores, self.threshold, label) for label in TIERS}
        for label, accepted in rows.items():
            print(f"{label:22s} thr {self.threshold[label]:.3f} throws at: {sorted(accepted)}", flush=True)
            self.assertNotIn("zone defender in the window", accepted, label)
            self.assertNotIn("man step for step", accepted, label)
            self.assertNotIn("man undercutting 1 yd in front", accepted, label)
            self.assertIn("wide open", accepted, label)
            self.assertIn("zone defender 14 yd off", accepted, label)
        weak, avg, strong, elite = (rows[label] for label in TIERS)
        covered = {"zone defender 6 yd off", "man 1 yd behind"}
        self.assertTrue(covered <= weak)                 # the rookie still forces a throw at a covered receiver
        self.assertFalse(covered & avg)                  # an average starter wants a step of separation
        self.assertFalse(covered & elite)
        self.assertGreater(len(weak), len(avg))
        self.assertGreaterEqual(len(avg), len(elite))    # the elite reader is the most selective
        self.assertIn("man 2 yd behind", elite)          # ... but a clear window (two yards of separation) is taken
        self.assertTrue(elite <= strong <= avg <= weak)

    def test_the_threshold_curve_is_the_only_new_difference_from_zone_windows(self):
        for name in CASES:
            self.assertEqual(score(self.zone, name, 1)[0], self.scores[name], name)


if __name__ == "__main__":
    unittest.main()
