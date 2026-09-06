"""Bounded retail facing evidence, not a sustained-facing/bail implementation.

Geometry, quaternion rotation, curves and RNG execute actual XBE instructions.
No callee is stubbed. Route cases below are explicit ball-position snapshots,
not receiver selection, a simulated route/play, or Noah's played witness.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_catch_slider as catch
from mod_editor.core import nfl2k5_coverage_slider as coverage
from mod_editor.core import nfl2k5_qb_spy_runtime as spy
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_zone_drop as drop
from mod_editor.core import nfl2k5_zone_facing as facing
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_zone_drop_unicorn import Machine as DropMachine, XBE, HAVE_UC, YARD


class Machine(DropMachine):
    NODE, QUAT, BALL, TARGET = (DropMachine.HEAP + n for n in (0xA000, 0xA100, 0xB000, 0xB100))
    RNG = 0xE5FCA0

    def _visit(self, uc, address, size, data):
        super()._visit(uc, address, size, data)
        if address == 0x1F433A:
            self.threshold = self.getf(uc.reg_read(self.x.UC_X86_REG_ESP))
        if address == 0x1F433F:
            bits = uc.reg_read(self.x.UC_X86_REG_ECX)
            self.roll = struct.unpack("<f", struct.pack("<I", bits))[0] - 1
        if address == 0x1F42C5:
            value = uc.reg_read(self.x.UC_X86_REG_EAX)
            self.effective_facing = (value + 32768) % 65536 - 32768

    def reaction(self, *, heading=0, rotation=0, ball=(0, 10), seed=0x400000,
                 slider=.5, side=0, context=.8, **actor):
        self.reset(**actor)
        self.put(self.P + 0x14, self.NODE)
        self.put(self.NODE + 0x34, self.QUAT)
        # Explicit unit quaternion around the vertical axis, w/x/y/z layout.
        theta = rotation * math.pi / 65536
        self.uc.mem_write(self.QUAT, struct.pack("<4f", math.cos(theta), 0, math.sin(theta), 0))
        self.put(self.V + 0x50, heading)
        self.put(self.TEAM + 0x30, side)
        self.float(self.M + 0x190, context)
        self.put(0xE5FC00, self.BALL)
        self.put(self.BALL + 0x14, self.TARGET)
        self.float(self.TARGET, self.getf(self.V + 0x30) + ball[0] * YARD)
        self.float(self.TARGET + 8, self.getf(self.V + 0x38) + ball[1] * YARD)
        self.float(0xAAB8C0 + 6 * 4, slider if side == 0 else 1 - slider)
        self.float(0xAAB8C0 + 16 * 4, slider if side else 1 - slider)
        self.uc.mem_write(self.RNG, bytes(8 + 55 * 8))
        self.put(self.RNG, 0)
        self.put(self.RNG + 4, 1)
        self.put(self.RNG + 8, seed)
        self.put(self.SP, self.AUX + 0x80)
        self.setreg("ESP", self.SP)
        self.setreg("ESI", self.P)
        self.threshold = self.roll = self.effective_facing = None
        self.run(0x1F4250, self.AUX + 0x80)
        return dict(threshold=self.threshold, roll=self.roll, facing=self.effective_facing,
                    outcome=self.uc.reg_read(self.x.UC_X86_REG_EAX))

    def latch(self, throttle, reset, active):
        self.reset()
        self.put(self.S + 0x584, 0x40000 if active else 0)
        self.float(self.A + 0x30, 0)
        self.float(self.M + 0x1B8, .8)
        self.float(self.TARGET, self.getf(self.V + 0x30))
        self.float(self.TARGET + 8, self.getf(self.V + 0x38) + 10 * YARD)
        self.uc.mem_write(self.SP, struct.pack("<III f I", self.AUX + 0x80, self.TARGET, 0, throttle, reset))
        self.setreg("ECX", self.P)
        self.setreg("EDX", 0)
        # Stops before the shared navigation call. All preceding callees are
        # native, including heading and throttle smoothing. This is a latch
        # proof only, with no movement/animation rendering claim.
        self.run(0x1A4170, 0x1A4246)
        return bool(self.get(self.S + 0x584) & 0x40000)


@unittest.skipUnless(XBE.is_file() and HAVE_UC, f"pinned USA default.xbe absent at {XBE}, or unicorn missing")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise AssertionError("Unexpected retail executable identity")
        cls.capped = drop.apply(cls.retail)[0]
        base = space.apply(cls.retail, drop.REQUESTS + spy.REQUESTS + coverage.REQUESTS, scaleout=True)[0]
        cls.composed = coverage.apply(spy.apply(drop.apply(base)[0])[0])[0]
        cls.with_catch = catch.apply(cls.composed)[0]
        for payload in (cls.retail, cls.capped, cls.composed, cls.with_catch):
            facing.assess(payload)

    def test_native_effective_facing_includes_animation_rotation(self):
        m = Machine(self.retail)
        for heading in (0, 0x2000, 0x4000, 0x7FFF, 0x8000, 0xC000):
            for rotation in (0, 0x4000, 0x8000, 0xC000):
                with self.subTest(heading=heading, rotation=rotation):
                    result = m.reaction(heading=heading, rotation=rotation)
                    expected = (heading + rotation + 32768) % 65536 - 32768
                    # The native rational bearing approximation rounds units.
                    delta = (result["facing"] - expected + 32768) % 65536 - 32768
                    self.assertLessEqual(abs(delta), 1)
                    for va in (0x217AE0, 0x217AB0, 0x3CA1E0, 0x3CA150, 0x210B0, 0x48B90, 0x48B50):
                        self.assertIn(va, m.visits)
                    self.assertEqual(m.visits.count(0x48B90), 1)
                    self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_ESP), m.SP + 4)
                    self.assertEqual((m.uc.reg_read(m.x.UC_X86_REG_FPSW) >> 11) & 7, 5)

    def test_native_facing_reward_and_rng_threshold(self):
        m = Machine(self.retail)
        for heading, angle_contribution in ((0, .3), (8192, .3), (16384, .1), (20935, .05), (32768, 0)):
            for side in (0, 1):
                threshold = .1125 + .1 + angle_contribution
                for offset in (-.001, .001):
                    seed = int((threshold + offset) * (1 << 23))
                    with self.subTest(heading=heading, side=side, seed=seed):
                        result = m.reaction(heading=heading, side=side, seed=seed)
                        self.assertAlmostEqual(result["threshold"], threshold, places=5)
                        self.assertEqual(result["roll"], seed / (1 << 23))
                        self.assertEqual(result["outcome"], int(offset < 0))
                        self.assertNotIn(catch.CAVE_VA, m.visits)
                        self.assertNotIn(catch.HOOK_VA, m.visits)

    def test_press_off_cover3_route_snapshots_do_not_gain_a_reaction_patch(self):
        before, after = Machine(self.retail), Machine(self.capped)
        # Ball targets relative to the corner at three separately supplied
        # snapshots. No fixture labels are used to invent receiver identity.
        snapshots = {"go": (0, 12), "curl": (0, -4), "comeback": (5, -4)}
        for route, ball in snapshots.items():
            for sign in (-1, 1):
                for depth in (1, 5, 6, 6.999, 7, 10):
                    for heading in (0, 0x4000, 0x8000):
                        kwargs = dict(depth=depth, sign=sign, heading=heading,
                                      ball=(ball[0], sign * ball[1]))
                        with self.subTest(route=route, **kwargs):
                            self.assertEqual(before.reaction(**kwargs), after.reaction(**kwargs))

    def test_cover2_safeties_flat_corners_and_four_deep_controls(self):
        before, after = Machine(self.retail), Machine(self.capped)
        cases = ((16, 11), (17, 11), (18, 5), (18, 6), (16, 8), (17, 8), (18, 9), (18, 10))
        for position, mode in cases:
            for sign in (-1, 1):
                for depth in (1, 7, 10):
                    with self.subTest(position=position, mode=mode, sign=sign, depth=depth):
                        args = dict(position=position, mode=mode, sign=sign, depth=depth)
                        old, new = before.drop(**args), after.drop(**args)
                        if position != 18 or mode in (5, 6) or depth >= 7:
                            self.assertEqual(old["heap"], new["heap"])
                        else:
                            self.assertAlmostEqual(new["q"], .84, places=6)
                        self.assertEqual(before.reaction(**args), after.reaction(**args))

    def test_coverage_and_catch_compose_without_counting_facing_twice(self):
        plain, combined, caught = Machine(self.retail), Machine(self.composed), Machine(self.with_catch)
        for heading in (0, 0x4000, 0x8000):
            for slider in (0, .5, 1):
                for side in (0, 1):
                    args = dict(heading=heading, slider=slider, side=side)
                    baseline = plain.reaction(**args)
                    result = combined.reaction(**args)
                    self.assertEqual(result, caught.reaction(**args))
                    if slider == .5:
                        self.assertEqual(baseline, result)
                    expected_delta = slider * coverage.PATCH_SLOPE - (slider + .25) * coverage.RETAIL_SLOPE
                    self.assertAlmostEqual(result["threshold"] - baseline["threshold"], expected_delta, places=6)
                    for address, size in combined.writes:
                        self.assertTrue(combined.STACK <= address and address + size <= combined.STACK + 0x10000
                                        or combined.RNG <= address and address + size <= combined.RNG + 448,
                                        hex(address))

    def test_later_throttle_does_not_clear_the_inherited_run_latch(self):
        for payload in (self.retail, self.capped, self.composed):
            m = Machine(payload)
            for q in (.5, .84, .9):
                self.assertFalse(m.latch(q, reset=0, active=False))
                self.assertTrue(m.latch(q, reset=0, active=True))
            self.assertTrue(m.latch(.91, reset=0, active=False))
            self.assertTrue(m.latch(1, reset=0, active=False))
            self.assertTrue(m.latch(.35, reset=0, active=True))
            self.assertFalse(m.latch(.35, reset=1, active=True))
            self.assertTrue(m.latch(.36, reset=1, active=True))


if __name__ == "__main__":
    unittest.main()
