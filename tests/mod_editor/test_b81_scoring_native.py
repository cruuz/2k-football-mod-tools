"""Beta 81 scoring slice: execute the rewritten kicking instructions and the original ones on synthetic state.

Each test runs the shipped bytes and asserts the new behaviour; each also runs the original (retail) bytes on the
same state and asserts they behave differently, so the tests fail on the old code.  No game files are needed.
"""
from __future__ import annotations

import math
import struct
import unittest

from mod_editor.core import nfl2k5_cpu_kick_aim as aim
from mod_editor.core import nfl2k5_sim_scoring as scoring
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

PAGE = 0x1000
STACK = 0x00200000
# Retail .rdata constants the original and rewritten blocks read (value, address).
CONSTANTS = {0x004E693C: 30.0, 0x004E7F84: 40.0, 0x004E72A4: 50.0, 0x004F6BDC: 0.015, 0x004F6BB0: 0.375,
             0x004F0FAC: 0.98, 0x004F2684: 33.0, 0x004E7F00: 37.0}


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


class _Machine:
    def __init__(self, code_va, code):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn import x86_const as x
        self.x = x
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.mapped = set()
        self.map(code_va, len(code) + PAGE)        # room for the stop addresses past the block
        self.uc.mem_write(code_va, code)
        self.map(STACK - 0x4000, 0x8000)
        for at, value in CONSTANTS.items():
            self.map(at, 4)
            self.uc.mem_write(at, struct.pack("<f", value))
        self.map(0x00A97000, 0x400)
        self.uc.reg_write(x.UC_X86_REG_ESP, STACK)

    def map(self, at, size):
        for page in range(at & ~(PAGE - 1), at + size, PAGE):
            if page not in self.mapped:
                self.uc.mem_map(page, PAGE)
                self.mapped.add(page)

    def put(self, at, raw):
        self.map(at, len(raw))
        self.uc.mem_write(at, raw)

    def u32(self, at, value):
        self.put(at, struct.pack("<I", value & 0xFFFFFFFF))

    def f(self, at, value):
        self.put(at, struct.pack("<f", value))

    def get_f(self, at):
        return struct.unpack("<f", bytes(self.uc.mem_read(at, 4)))[0]

    def get_u32(self, at):
        return struct.unpack("<I", bytes(self.uc.mem_read(at, 4)))[0]

    def reg(self, name, value=None):
        register = getattr(self.x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(register)
        self.uc.reg_write(register, value & 0xFFFFFFFF)

    def run(self, start, stops):
        from unicorn import UC_HOOK_CODE
        landed = []

        def stop(uc, address, size, user):
            landed.append(address)
            uc.emu_stop()
        hooks = [self.uc.hook_add(UC_HOOK_CODE, stop, begin=at, end=at) for at in stops]
        self.uc.emu_start(start, 0xFFFFFFFF, count=2000)
        for hook in hooks:
            self.uc.hook_del(hook)
        assert landed, "the block did not reach any stop address"
        return landed[0]


@unittest.skipUnless(HAVE_UC, "Unicorn is required to execute the kicking blocks")
class SimulatedFieldGoalChance(unittest.TestCase):
    END = scoring.ACCURACY_VA + scoring.ACCURACY_SIZE   # 0x109BEE, unchanged next instruction

    def chance(self, code, yards, adjusted, pat=False, record=0x12345678):
        m = _Machine(scoring.ACCURACY_VA, code)
        esp = STACK - 0x100
        m.reg("ESP", esp)
        m.f(esp + 0x10, yards)
        m.f(esp + 0x18, yards)
        m.f(esp + 0x14, 0.75)                 # the stock default base written at 0x109A5B
        m.f(esp + 0x28, adjusted)
        m.u32(scoring.PAT_FLAG, 1 if pat else 0)
        kick = 0x00300000
        m.u32(kick + 0xC, record)
        m.reg("ESI", kick)
        m.reg("EAX", int(math.floor(yards + 0.5)))   # the credited (rounded) yards from 0x100F00
        self.assertEqual(m.run(scoring.ACCURACY_VA, (self.END,)), self.END)
        return m.get_f(esp + 0x14), m.get_u32(kick + 0xC)

    @staticmethod
    def expected(yards, adjusted, pat):
        base = 0.95 if yards < 30 else 0.90 if yards < 40 else 0.85
        p = base - (adjusted * 0.015 - 0.375)
        if not pat:
            p += 0.00475 * yards if yards <= 55 else 1.2375 - 0.01775 * yards
        return min(p, 0.98)

    def test_field_goal_curve_matches_the_design_and_the_stock_curve_does_not(self):
        new, old = scoring.accuracy_bytes(), scoring.RETAIL_ACCURACY
        for yards in [y + 0.37 for y in range(17, 76)] + [30.0, 40.0, 50.0, 55.0, 55.01]:
            for delta in (-9.0, -4.0, -1.8, 0.0, 3.0, 7.0):
                with self.subTest(yards=yards, delta=delta):
                    p, _ = self.chance(new, yards, yards + delta)
                    self.assertAlmostEqual(p, self.expected(yards, yards + delta, False), delta=2e-6)
        # Anchors at an average matchup (kicker 1.8 yards better than the defence, the sim's mean).
        for yards, low, high in ((25.0, 0.979, 0.981), (35.0, 0.90, 0.96), (45.0, 0.76, 0.82),
                                 (52.0, 0.68, 0.76), (57.0, 0.58, 0.68), (62.0, 0.42, 0.55)):
            p_new, _ = self.chance(new, yards, yards - 1.8)
            p_old, _ = self.chance(old, yards, yards - 1.8)
            with self.subTest(anchor=yards):
                self.assertTrue(low <= p_new <= high, p_new)
                if yards >= 35:
                    self.assertFalse(low <= p_old <= high, p_old)   # the original curve misses every anchor

    def test_chance_never_rises_with_distance_or_falls_with_a_better_matchup(self):
        code = scoring.accuracy_bytes()
        for delta in (-10.0, -2.0, 0.0, 6.0):
            previous = 1.0
            for tenth in range(170, 700, 7):
                yards = tenth / 10
                p, _ = self.chance(code, yards, yards + delta)
                self.assertLessEqual(p, previous + 1e-7, (yards, delta))
                previous = p
        for yards in (28.0, 44.0, 53.0, 61.0):
            values = [self.chance(code, yards, yards + d)[0] for d in (6.0, 2.0, 0.0, -3.0, -9.0)]
            self.assertEqual(values, sorted(values), yards)

    def test_extra_points_and_the_kick_record_are_bit_identical_to_the_original(self):
        new, old = scoring.accuracy_bytes(), scoring.RETAIL_ACCURACY
        for adjusted in (8.0, 15.3, 19.0, 21.7, 26.0, 31.9):
            for record in (0, 0xFFFFFFFF, 0x00C03F00, 0x89ABCDEF):
                with self.subTest(adjusted=adjusted, record=record):
                    self.assertEqual(self.chance(new, 19.0, adjusted, True, record),
                                     self.chance(old, 19.0, adjusted, True, record))
        for yards in (22.4, 37.6, 48.2, 58.9):
            self.assertEqual(self.chance(new, yards, yards, False, 0x5A5A5A5A)[1],
                             self.chance(old, yards, yards, False, 0x5A5A5A5A)[1])


@unittest.skipUnless(HAVE_UC, "Unicorn is required to execute the kicking blocks")
class SimulatedLongAttempts(unittest.TestCase):
    # stdcall uniform_between(lo, hi): st0 = lo + u * (hi - lo), with u read from a test word.
    U = 0x00A97300
    STUB = bytes.fromhex("d905") + struct.pack("<I", 0x00A97300) + bytes.fromhex("d9442408d8642404dec9d8442404c20800")
    FTOL = bytes.fromhex("f30f2c442404c20400")           # retail 0x100F00
    ONE_IN_N = bytes.fromhex("33c0c20400")                # 0x101FF0 stand-in: the 1-in-N draw misses

    def decide(self, code, line_to_goal, u):
        m = _Machine(scoring.RAMP_VA, code)
        m.put(scoring.FN_UNIFORM_BETWEEN, self.STUB)
        m.put(0x00100F00, self.FTOL)
        m.put(0x00101FF0, self.ONE_IN_N)
        m.f(self.U, u)
        m.f(scoring.LINE_TO_GOAL, line_to_goal)
        m.reg("ESP", STACK - 0x100)
        landed = m.run(scoring.RAMP_VA, (scoring.PUNT_VA, scoring.FIELD_GOAL_VA))
        self.assertEqual(m.reg("ESP"), STACK - 0x100)       # both arguments popped
        return "field goal" if landed == scoring.FIELD_GOAL_VA else "punt"

    def test_field_goal_share_falls_linearly_from_36_to_41_5_yards_to_goal(self):
        new = scoring.ramp_bytes()
        draws = [(k + 0.5) / 40 for k in range(40)]
        for line_to_goal in (20.0, 32.9, 35.9, 36.5, 38.0, 39.0, 40.0, 41.0, 41.4, 41.6, 45.0, 60.0):
            share = sum(self.decide(new, line_to_goal, u) == "field goal" for u in draws) / len(draws)
            want = min(1.0, max(0.0, (41.5 - line_to_goal) / 5.5))
            with self.subTest(line_to_goal=line_to_goal):
                self.assertAlmostEqual(share, want, delta=1 / 40 + 1e-9)

    def test_the_original_selector_almost_never_kicks_from_33_yards_or_farther(self):
        old = scoring.RETAIL_RAMP
        self.assertEqual(self.decide(old, 32.0, 0.5), "field goal")
        for line_to_goal in (33.5, 36.0, 38.0, 40.0):
            with self.subTest(line_to_goal=line_to_goal):
                self.assertEqual(self.decide(old, line_to_goal, 0.5), "punt")
                if line_to_goal < 41.5:
                    self.assertEqual(self.decide(scoring.ramp_bytes(), line_to_goal, 0.999), "field goal")


@unittest.skipUnless(HAVE_UC, "Unicorn is required to execute the kicking blocks")
class BreakawayStop(unittest.TestCase):
    """The optional breakaway rule (off by default): same eligibility and draw, long promotions stop at the 1."""
    END = scoring.BREAKAWAY_VA + scoring.BREAKAWAY_SIZE    # 0x10949F, unchanged next instruction
    RATING = bytes.fromhex("d905") + struct.pack("<I", 0x00A97310) + bytes.fromhex("c20400")   # st0 = trait; ret 4
    # stdcall chance(p): eax = (u < p) with u from a test word (the native 0x102030 reads the match RNG).
    CHANCE = (bytes.fromhex("d905") + struct.pack("<I", 0x00A97314)
              + bytes.fromhex("d85c2404dfe0f6c4057a08b801000000c2040033c0c20400"))

    def promote(self, code, gain, line_to_goal, u, positive=1.0, trait=0.75):
        m = _Machine(scoring.BREAKAWAY_VA, code)
        m.put(scoring.FN_RATING, self.RATING)
        m.put(scoring.FN_CHANCE, self.CHANCE)
        m.f(0x00A97310, trait)
        m.f(0x00A97314, u)
        for at, value in ((0x004E6D5C, 0.10), (0x004E419C, 1.0), (0x004E4180, 0.0), (0x004E6D40, 4.0)):
            m.f(at, value)
        m.f(scoring.LINE_TO_GOAL, line_to_goal)
        esp = STACK - 0x100
        m.reg("ESP", esp)
        m.f(esp + 0x10, gain)
        m.f(esp + 0x18, positive)
        m.reg("ESI", 0x00300000)
        self.assertEqual(m.run(scoring.BREAKAWAY_VA, (self.END,)), self.END)
        self.assertEqual(m.reg("ESP"), esp)
        return m.get_f(esp + 0x10)

    def test_long_promotions_stop_at_the_1_and_short_ones_still_score(self):
        new, old = scoring.breakaway_bytes(40.0), scoring.RETAIL_BREAKAWAY
        for line_to_goal in (12.0, 25.5, 39.9, 40.0):
            with self.subTest(line_to_goal=line_to_goal):
                self.assertEqual(self.promote(new, 6.0, line_to_goal, 0.01), f32(line_to_goal + 1.0))
                self.assertEqual(self.promote(old, 6.0, line_to_goal, 0.01), f32(line_to_goal + 1.0))
        for line_to_goal in (40.5, 63.25, 88.0):
            with self.subTest(line_to_goal=line_to_goal):
                self.assertEqual(self.promote(new, 9.67, line_to_goal, 0.01), f32(line_to_goal - 1.0))
                self.assertEqual(self.promote(old, 9.67, line_to_goal, 0.01), f32(line_to_goal + 1.0))

    def test_the_chance_and_eligibility_are_unchanged(self):
        new, old = scoring.breakaway_bytes(40.0), scoring.RETAIL_BREAKAWAY
        for args in ((6.0, 60.0, 0.074), (6.0, 60.0, 0.076), (6.0, 30.0, 0.5), (6.0, 30.0, 0.0749),
                     (6.0, 60.0, 0.01, 0.0), (6.0, 60.0, 0.01, -2.0), (61.0, 60.0, 0.01), (-3.0, 60.0, 0.01)):
            with self.subTest(args=args):
                kept = args[0]
                expected_old = self.promote(old, *args)
                got = self.promote(new, *args)
                if expected_old == f32(kept):
                    self.assertEqual(got, f32(kept))          # no breakaway in either version
                else:
                    self.assertIn(got, (f32(args[1] + 1.0), f32(args[1] - 1.0)))


@unittest.skipUnless(HAVE_UC, "Unicorn is required to execute the kicking blocks")
class CpuKickAim(unittest.TestCase):
    END = aim.RESUME_VA

    def scaled(self, code, error, pressured):
        m = _Machine(aim.SITE_VA, code)
        frame, context, extra = 0x00310000, 0x00320000, 0x00330000
        m.u32(frame + 8, context)
        m.u32(context + 0x38, extra if pressured is not None else 0)
        m.u32(extra + 0x30, 1 if pressured else 0)
        m.reg("EBP", frame)
        m.reg("EDX", error)
        m.reg("ESP", STACK - 0x100)
        self.assertEqual(m.run(aim.SITE_VA, (self.END,)), self.END)
        value = m.reg("EDX")
        return value - (1 << 32) if value & 0x80000000 else value

    def test_cpu_error_is_scaled_to_85_of_128_and_the_1_5x_case_keeps_its_ratio(self):
        new = aim.site_bytes()
        for error in (0, 1, -1, 7, -7, 128, -128, 1000, -1000, 4095, -4096, 12345, -23456):
            for pressured in (None, False, True):
                with self.subTest(error=error, pressured=pressured):
                    value = error * 85
                    if pressured:
                        value = (value * 3) >> 1
                    self.assertEqual(self.scaled(new, error, pressured), value >> 7)

    def test_the_original_bytes_keep_the_full_error(self):
        old = aim.RETAIL_SITE
        self.assertEqual(self.scaled(old, 1000, False), 1000)
        self.assertEqual(self.scaled(old, -1000, True), -1500)
        self.assertNotEqual(self.scaled(aim.site_bytes(), 1000, False), 1000)
        self.assertNotEqual(self.scaled(aim.site_bytes(), -1000, True), -1500)


class Layout(unittest.TestCase):
    def test_sites_are_same_length_rewrites_inside_their_routines(self):
        self.assertEqual(len(aim.site_bytes()), len(aim.RETAIL_SITE))
        for _, va, retail, enabled in scoring.edits():
            self.assertEqual(len(retail), len(enabled))
        self.assertEqual(scoring.ramp_bytes()[37:], b"\xcc" * (scoring.RAMP_SIZE - 37))

    def test_no_overlap_with_the_quarterback_option_or_simulated_season_realism(self):
        from mod_editor.core import nfl2k5_sim_qb_injuries_code as medical, nfl2k5_sim_realism as simulator
        ours = set()
        for _, va, retail, _ in scoring.edits():
            ours.update(range(va, va + len(retail)))
        ours.update(range(aim.SITE_VA, aim.SITE_VA + aim.SITE_SIZE))
        theirs = set()
        for va, width in medical.FIXED_SPANS:
            theirs.update(range(va, va + width))
        for name in ("MIX_SITE", "QB_SITE", "TARGET_SITE", "INTERCEPT_SITE", "TACKLE_ENTRY_SITE",
                     "TACKLE_RETURN_SITE", "RUN_BONUS_SITE"):
            va = getattr(simulator, name)
            theirs.update(range(va, va + 16))
        for va, before in simulator.PASS_SITES:
            theirs.update(range(va, va + len(before)))
        self.assertFalse(ours & theirs)

    def test_parameters_are_checked(self):
        with self.assertRaises(scoring.SimScoringError):
            scoring.ramp_bytes(low=42.0, high=40.0)
        with self.assertRaises(scoring.SimScoringError):
            scoring.edits(spread=3)
        with self.assertRaises(aim.CpuKickAimError):
            aim.site_bytes(128)


if __name__ == "__main__":
    unittest.main()
