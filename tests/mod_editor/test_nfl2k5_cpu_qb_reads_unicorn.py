"""Bounded native proofs for CPU QB reads. No game boot, rendered play or witnessed throw.

The real openness function 0x199F40, the real picker 0x1985E0, the real curve interpolator and the owner's caves
execute from the pinned USA retail default.xbe (skipped when absent). Receivers, defenders, target rows, the clock
and the QB's Pass Read Coverage are supplied inputs.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_cpu_qb_reads as reads
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.nfl2k5_cpu_ai_native import OpenMachine, ReadsMachine, uc, x86

SPEED = 8.0  # receiver yd/s, straight downfield from 8 yd; the ball arrives at the 16-yd point at tb = 1.0 s


def zone(m, lateral):
    m.defender(role=13, x=lateral, depth=16, spot=(lateral, 16))


def man(m, trail):
    m.defender(role=14, x=0, depth=8 - trail, vz=SPEED, man=m.RB)


CASES = {
    "zone defender in the window": lambda m: zone(m, 0),
    "zone defender 3 yd off": lambda m: zone(m, 3),
    "zone defender 6 yd off": lambda m: zone(m, 6),
    "zone defender 8 yd off": lambda m: zone(m, 8),
    "zone defender 14 yd off": lambda m: zone(m, 14),
    "man step for step": lambda m: man(m, 0),
    "man 1 yd behind": lambda m: man(m, 1),
    "man 1.5 yd behind": lambda m: man(m, 1.5),
    "man 2 yd behind": lambda m: man(m, 2),
    "man 3 yd behind": lambda m: man(m, 3),
    "man undercutting 1 yd in front": lambda m: man(m, -1),
    "bracket": lambda m: (man(m, 1), m.defender(role=14, x=2, depth=7, vz=SPEED, man2=m.RB)),
    "wide open": lambda m: m.defender(role=14, x=15, depth=8, man=0),
}


def score(payload, name, direction):
    m = OpenMachine(payload, direction=direction)
    m.place(m.RB, 0, 8, 0, SPEED)
    CASES[name](m)
    value = m.openness((0, 16), tb=1.0, tr=0.35)
    return value, list(m.arrivals)


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class CoveredWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.zone, _ = reads.apply(cls.retail, zone_windows=True)
        cls.rows = {}
        for name in CASES:
            for direction in (1, -1):
                cls.rows[(name, direction)] = (score(cls.retail, name, direction), score(cls.zone, name, direction))
        m = OpenMachine(cls.retail)
        # Pass Read Coverage 0.70 / 0.85 / 0.95 through the native threshold curve 0x50C394.
        cls.thresholds = {prc: m.curve(0x50C394, prc) for prc in (0.70, 0.85, 0.95)}

    def test_native_thresholds_are_the_retail_pass_read_coverage_curve(self):
        expected = {0.70: 1.1 - 0.1 * (0.2 / 0.3), 0.85: 1.0 - 0.025 * (0.05 / 0.2), 0.95: 1.0 - 0.025 * (0.15 / 0.2)}
        for prc, value in expected.items():
            self.assertAlmostEqual(self.thresholds[prc], value, places=5, msg=prc)

    def test_both_field_directions_are_identical(self):
        for name in CASES:   # mirrored fields agree to float32 rounding of the mirrored coordinates
            for (a, xa), (b, xb) in zip(self.rows[(name, 1)], self.rows[(name, -1)]):
                self.assertAlmostEqual(a, b, places=5, msg=name)
                for u, v in zip(xa, xb):
                    self.assertAlmostEqual(u, v, places=5, msg=name)

    def test_windows_a_defender_reaches_first_close(self):
        for name in ("zone defender in the window", "zone defender 3 yd off", "zone defender 6 yd off"):
            (old, x), (new, _) = self.rows[(name, 1)]
            self.assertGreaterEqual(old, 1.25, name)
            self.assertLessEqual(new, 0.75, name)
            self.assertTrue(all(v >= 0.35 for v in x), (name, x))
            for prc, threshold in self.thresholds.items():
                self.assertGreater(old, threshold, (name, prc))
                self.assertLess(new, min(0.85, threshold), (name, prc))   # below even the pressured threshold floor
        for name in ("man step for step", "man undercutting 1 yd in front"):
            (old, _), (new, _) = self.rows[(name, 1)]
            self.assertLess(new, 0.75, name)
            self.assertLess(new, old, name)

    def test_receivers_with_separation_score_exactly_as_retail(self):
        for name in ("zone defender 14 yd off", "man 2 yd behind", "man 3 yd behind", "wide open"):
            (old, x), (new, _) = self.rows[(name, 1)]
            self.assertTrue(all(v <= -0.1 for v in x), (name, x))
            self.assertEqual(struct.pack("<f", old), struct.pack("<f", new), name)

    def test_curve_only_changes_arrivals_within_a_tenth_of_a_second(self):
        for (name, direction), ((old, x), (new, _)) in self.rows.items():
            if all(v <= -0.1 for v in x):
                self.assertEqual(old, new, name)
            else:
                self.assertLess(new, old, name)

    def test_native_picker_no_longer_adopts_the_covered_first_read(self):
        (old, _), (new, _) = self.rows[("zone defender in the window", 1)]
        for payload, value, expected in ((self.retail, old, 0), (self.zone, new, None)):
            m = ReadsMachine(payload)
            # first read: the covered receiver; second: not read yet (-inf, as after the snap)
            m.rows([dict(scores=[value, -1e30, -1e30, -1e30], yards=6), dict(scores=[-1e30] * 4, yards=14)])
            self.assertEqual(m.native_pick(self.thresholds[0.85]), expected)
        m = ReadsMachine(self.zone)
        m.rows([dict(scores=[new, -1e30, -1e30, -1e30], yards=6), dict(scores=[1.45, -1e30, -1e30, -1e30], yards=14)])
        self.assertEqual(m.native_pick(self.thresholds[0.85]), 1)


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class RecheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.payload, _ = reads.apply(cls.retail, recheck=True)

    def machine(self, prc=0.85):
        m = ReadsMachine(self.payload)
        m.set_read_coverage(prc)
        # row 0: current read, moderately open; row 1: very open when it was read
        m.rows([dict(scores=[1.10, 1.05, -1e30, -1e30], yards=8), dict(scores=[1.40, 1.30, -1e30, -1e30], yards=12)])
        return m

    def test_stamp_records_the_point_and_enters_the_native_scorer_unchanged(self):
        m = self.machine()
        self.assertEqual(m.stamp(1, 2, 1.25), [1, m.QB, 2])
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EIP), 0x19A7E0)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK)
        self.assertAlmostEqual(m.stamp_value(1, 2), 1.25)
        self.assertEqual(m.get(m.state + m.field("VALID")), 1 << 6)
        m.stamp(7, 0, 1.3)           # rows beyond the grid are ignored
        m.stamp(0, 9, 1.3)
        self.assertEqual(m.get(m.state + m.field("VALID")), 1 << 6)

    def test_stale_reads_are_hidden_from_the_native_picker_and_restored(self):
        m = self.machine()
        for point in (0, 1):
            m.stamp(1, point, 1.0)
            m.stamp(0, point, 1.9)
        before = m.snapshot()
        self.assertEqual(m.native_pick(1.0), 1)           # retail: the 1.0 s old score wins
        self.assertEqual(m.pick(1.0, 2.0), 0)              # re-check: only the fresh read counts
        self.assertEqual(m.snapshot(), before)
        self.assertAlmostEqual(m.readf(m.state + m.field("AGE")), 0.61875, places=5)  # 1.5 x dwell(0.85)
        for point in (0, 1):
            m.stamp(1, point, 1.6)
        self.assertEqual(m.pick(1.0, 2.0), 1)              # read 0.4 s ago: fresh again

    def test_read_window_follows_the_native_dwell_and_is_clamped(self):
        for prc, window in ((0.3, 1.5), (0.5, 0.75), (0.85, 0.61875), (1.0, 0.6)):
            m = self.machine(prc)
            m.stamp(0, 0, 1.9)
            m.pick(1.0, 2.0)
            self.assertAlmostEqual(m.readf(m.state + m.field("AGE")), window, places=5, msg=prc)
            self.assertEqual(m.rating_calls[-1], (m.get(m.QB + 0x3C), 0xD))

    def test_pressure_panic_and_human_passer_keep_retail(self):
        for change in (lambda m: m.f32(0xBE47C0, 0.8), lambda m: m.u32(0xBE47F8, 1),
                       lambda m: m.u32(m.get(m.QB + 0xC), 0)):
            m = self.machine()
            for point in (0, 1):
                m.stamp(1, point, 1.0)
                m.stamp(0, point, 1.9)
            change(m)
            m.commit(1)
            m.u32(0xBE4810, 0)
            self.assertEqual(m.pick(1.0, 2.0), 1)
            self.assertEqual(m.get(0xBE4810), 0)           # no lock-on either
            self.assertEqual(m.hold(2.05), "release")
            self.assertEqual(m.get(m.task + 0x40), m.actors[1])

    def test_lock_on_and_abort_only_after_the_committed_receiver_is_rescored(self):
        m = self.machine()
        for point in (0, 1):
            m.stamp(1, point, 1.7)
            m.stamp(0, point, 1.95)
        m.commit(1, timer=0.3)
        m.pick(1.0, 2.0)
        self.assertEqual(m.get(0xBE4810), 1)
        self.assertEqual(m.get(0xBE4820 + 0xA0 + 4), 0)     # his point cursor restarts
        self.assertAlmostEqual(m.readf(0xBE47C8), 2.1, places=5)
        self.assertEqual(m.hold(2.05), "release")          # not re-scored since the commit
        for point in (0, 1):
            m.f32(0xBE4820 + 0xA0 + 0x34 + point * 0x20, 0.97)
            m.stamp(1, point, 2.07)
        self.assertEqual(m.hold(2.08), "release")          # 0.97 is not below 1.0 - 0.05
        m.f32(0xBE4820 + 0xA0 + 0x34, 0.70)
        m.f32(0xBE4820 + 0xA0 + 0x54, 0.70)
        self.assertEqual(m.hold(2.10), "pick")             # window closed: drop him and re-pick now
        self.assertEqual(m.get(m.task + 0x40), 0)
        self.assertEqual(m.get(m.STACK + 0x18), 0)
        self.assertAlmostEqual(m.readf(m.task + 0x60), 0.05, places=6)
        self.assertEqual(m.get(m.state + m.field("ABORTS")), 1)

    def test_at_most_two_aborts_per_play_and_a_new_play_resets(self):
        m = self.machine()
        t = 2.0
        for expected in ("pick", "pick", "release"):
            m.commit(1, timer=0.3)
            m.pick(1.0, t)
            for point in (0, 1):
                m.f32(0xBE4820 + 0xA0 + 0x34 + point * 0x20, 0.5)
                m.stamp(1, point, t + 0.05)
            self.assertEqual(m.hold(t + 0.06), expected)
            t += 0.2
        self.assertEqual(m.get(m.state + m.field("ABORTS")), 2)
        m.stamp(0, 0, 0.1)                                  # the clock went back: a new play
        self.assertEqual(m.get(m.state + m.field("ABORTS")), 0)
        self.assertEqual(m.get(m.state + m.field("VALID")), 1)

    def test_pick_wrapper_abi_and_x87_balance(self):
        m = self.machine()
        m.stamp(0, 0, 1.9)
        m.pick(1.0, 2.0)
        for reg, value in ((x86.UC_X86_REG_EBX, m.task), (x86.UC_X86_REG_ESI, 0x4567), (x86.UC_X86_REG_EDI, m.QB),
                           (x86.UC_X86_REG_EBP, 0x6789)):
            self.assertEqual(m.uc.reg_read(reg), value)
        self.assertEqual((m.uc.reg_read(x86.UC_X86_REG_FPSW) >> 11) & 7, 0)


if __name__ == "__main__":
    unittest.main()
