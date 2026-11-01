"""Bounded native proofs for the pass-protection owner. No game boot, no witnessed play.

The real retail per-tick break-up decision 0x233040 runs in Unicorn with its real callees (rating accessor
0x17B010, curve interpolator 0x1B0AE0, angle 0x210B0, shed angle 0x230A00, sliders 0x17B8F0, run latch
0x2F3AC0, native random 0x48B90, push 0x232750). Player skeletons, positions, wanted headings, the per-player
rating cache and the sliders are supplied inputs; the leverage term 0x2D4250 is a stub that returns 0.
"""
from pathlib import Path
import hashlib
import os
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_pass_protection as pp
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.mod_editor.test_nfl2k5_run_blocking_unicorn import Machine, heading_away, DT

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

PASS_BLOCKING, PASS_RUSH = 16, 18
PLAY_COUNT = 0xE53804


def engagement_factor(blocker, defender, play_count, spread=None):
    """The owner's per-engagement multiplier, re-derived in Python from the same 32-bit hash (b779-pr1)."""
    spread = pp.DELAY_SPREAD if spread is None else spread
    h = ((blocker * 0x9E3779B1) ^ (defender * 0x85EBCA6B) ^ (play_count * 0xC2B2AE35)) & 0xFFFFFFFF
    h ^= h >> 16
    u = h & 0xFFFF
    return struct.unpack("<f", struct.pack("<f", u * struct.unpack("<f", struct.pack("<f", 2 * spread / 65535.0))[0]
                                           + struct.unpack("<f", struct.pack("<f", 1.0 - spread))[0]))[0]


def expected_delay(m, pb, pr, play_count):
    blk, rusher = m.accessor(m.BLK, PASS_BLOCKING), m.accessor(m.DEF, PASS_RUSH)
    mean = min(max(pp.DELAY_BASE + pp.DELAY_SLOPE * (blk - rusher), pp.DELAY_MIN), pp.DELAY_MAX)
    return mean * engagement_factor(m.BLK, m.DEF, play_count)


class Patched:
    """The retail Machine plus the owner's code and hook at the owner's allocation VA."""

    def __init__(self, payload):
        self.payload = payload

    @classmethod
    def build(cls):
        retail = retail_xbe()
        patched, receipt = pp.apply(retail)
        obj = cls(patched)
        obj.retail = retail
        obj.va = pp.allocation(patched)["va"]
        obj.code = pp.code_for(obj.va)
        obj.hook = pp.sites(obj.va)[0][3]
        obj.receipt = receipt
        return obj

    def machine(self, pb, pr, state=1):
        m = Machine(self.payload)
        m.uc.mem_write(self.va, self.code)
        m.uc.mem_write(0x233162, self.hook)
        m.rating(m.BLK, PASS_BLOCKING, pb)
        m.rating(m.DEF, PASS_RUSH, pr)
        m.want(m.DEF, 1.0, self.heading)
        m.u32(m.BLK + 0x200 + 0x18C, state)
        return m


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class ShedDelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched = Patched.build()
        cls.heading = heading_away(Machine(cls.retail))
        cls.patched.heading = cls.heading

    def retail_machine(self, pb, pr, state=1):
        m = Machine(self.retail)
        m.rating(m.BLK, PASS_BLOCKING, pb)
        m.rating(m.DEF, PASS_RUSH, pr)
        m.want(m.DEF, 1.0, self.heading)
        m.u32(m.BLK + 0x200 + 0x18C, state)
        return m

    def test_retail_pass_shed_is_instant_for_every_lineman(self):
        seen = {self.retail_machine(pb, pr).ticks_to_shed() for pb, pr in ((0.95, 0.4), (0.7, 0.7), (0.4, 0.95))}
        self.assertEqual(seen, {1})

    def test_patched_delay_follows_the_pass_ratings(self):
        rows = {}
        for pb, pr in ((0.95, 0.4), (0.85, 0.6), (0.72, 0.64), (0.6, 0.8), (0.4, 0.95)):
            m = self.patched.machine(pb, pr)
            m.u32(PLAY_COUNT, 7)
            want = expected_delay(m, pb, pr, 7)
            n = m.ticks_to_shed(limit=400)
            rows[(pb, pr)] = n
            self.assertIsNotNone(n)
            self.assertAlmostEqual(n * DT, want, delta=DT * 1.01, msg=(pb, pr))
        ordered = [rows[k] for k in ((0.95, 0.4), (0.85, 0.6), (0.72, 0.64), (0.6, 0.8), (0.4, 0.95))]
        self.assertEqual(ordered, sorted(ordered, reverse=True))
        self.assertGreater(ordered[0], ordered[-1] * 4)

    def test_hold_varies_from_play_to_play_but_not_from_tick_to_tick(self):
        """One engagement draws one hold (the play count is constant while it lasts); another play draws again."""
        holds = []
        for play in range(24):
            m = self.patched.machine(0.72, 0.68)
            m.u32(PLAY_COUNT, 100 + play)
            n = m.ticks_to_shed(limit=400)
            self.assertIsNotNone(n)
            self.assertAlmostEqual(n * DT, expected_delay(m, 0.72, 0.68, 100 + play), delta=DT * 1.01, msg=play)
            holds.append(n * DT)
        mean = min(max(pp.DELAY_BASE + pp.DELAY_SLOPE * 0.04, pp.DELAY_MIN), pp.DELAY_MAX)
        self.assertGreaterEqual(min(holds), mean * (1 - pp.DELAY_SPREAD) - DT * 1.5)
        self.assertLessEqual(max(holds), mean * (1 + pp.DELAY_SPREAD) + DT * 1.5)
        self.assertGreater(max(holds) - min(holds), mean * pp.DELAY_SPREAD)     # real spread, not a constant
        self.assertGreater(len(set(round(h / DT) for h in holds)), 6)

    def test_elite_rusher_beats_a_backup_tackle_and_an_elite_tackle_holds_an_average_rusher(self):
        def mean_hold(pb, pr):
            out = []
            for play in range(40):
                m = self.patched.machine(pb, pr)
                m.u32(PLAY_COUNT, 500 + play)
                out.append(m.ticks_to_shed(limit=400) * DT)
            return sum(out) / len(out)
        average = mean_hold(0.80, 0.80)
        elite_rusher = mean_hold(0.58, 0.97)        # backup tackle against an elite edge
        elite_tackle = mean_hold(0.97, 0.80)        # elite tackle against an average edge
        self.assertLess(elite_rusher, 0.35 * average)
        self.assertGreater(elite_tackle, 1.25 * average)
        self.assertLess(elite_rusher, 0.30)

    def test_run_state_keeps_the_retail_constant(self):
        for m in (self.retail_machine(0.95, 0.4, state=0), self.patched.machine(0.95, 0.4, state=0)):
            self.assertIn(m.ticks_to_shed(), (3, 4))     # retail 0.05 s at 60 ticks a second

    def test_registers_stack_and_st0_preserved(self):
        m = self.patched.machine(0.8, 0.6)
        seen = []

        def at_entry(u, _a, _s, _d):
            seen.append(("in", [u.reg_read(r) for r in (x86.UC_X86_REG_EBX, x86.UC_X86_REG_ESI, x86.UC_X86_REG_EDI,
                                                        x86.UC_X86_REG_EBP, x86.UC_X86_REG_ESP)]))

        def after(u, _a, _s, _d):
            seen.append(("out", [u.reg_read(r) for r in (x86.UC_X86_REG_EBX, x86.UC_X86_REG_ESI, x86.UC_X86_REG_EDI,
                                                         x86.UC_X86_REG_EBP, x86.UC_X86_REG_ESP)]))
        m.uc.hook_add(uc.UC_HOOK_CODE, at_entry, begin=0x233162, end=0x233162)
        m.uc.hook_add(uc.UC_HOOK_CODE, after, begin=0x23316A, end=0x23316A)
        self.assertEqual(m.tick(), 0)
        self.assertEqual(seen[0][0], "in")
        self.assertEqual(seen[0][1], seen[1][1])

    def test_pass_start_roll_is_byte_for_byte_retail(self):
        for pb, pr in ((0.64, 0.72), (0.9, 0.5)):
            self.assertEqual(self.patched.machine(pb, pr).start_roll(run=False),
                             self.retail_machine(pb, pr).start_roll(run=False))


if __name__ == "__main__":
    unittest.main()
