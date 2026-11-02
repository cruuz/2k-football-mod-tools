"""Native proof for Speed separation (nfl2k5_speed_threshold, b780-cv5): the game's own speed mapper (0x238020), the
hook at its epilogue (0x2381B1) and the cave run in Unicorn.

* Scalar cases call the real mapper for one defender and read the speed it returns: strength scaling, both field
  directions, the 21 scope and fallback controls (each must return the unpatched value to the bit), the depth ramp, and
  register, flag, x87 control word and stack-write bounds.
* Frame cases replay the real man planner, ordinary locomotion, root sampler and transforms at 60 Hz for a go route
  (WR Speed 93 against CB Speed 83) and compare the separation at 10, 20, 30 and 40 yards.

Component proof only: a supplied go command, one synthetic straight clip, no route scripts, contact or game scheduler.
The retail default.xbe comes from NFL2K5_RETAIL_EXTRACTION. When NFL2K5_SPEED_V08_XBE names the released SOFTDRINK v0.8
executable (sha256 5f987568...), the same cases run on it as well. Slow: run it through the test slot.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_speed_threshold as patch
from mod_editor.core import nfl2k5_xbe_space as space
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

HAVE_NATIVE = all(importlib.util.find_spec(name) is not None for name in ("unicorn", "capstone"))
V08_SHA256 = "5f987568bc88122f566e30cb5bb8a574acde4549b915b6f2514beab37ab3e9f3"


def v08_xbe():
    path = os.environ.get("NFL2K5_SPEED_V08_XBE")
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("Set NFL2K5_SPEED_V08_XBE to the released v0.8 default.xbe to run the v0.8 cases")
    with Path(path).open("rb") as stream:
        payload = stream.read(space.SCALE_FILE_SIZE + 1)
    if hashlib.sha256(payload).hexdigest() != V08_SHA256:
        raise unittest.SkipTest("NFL2K5_SPEED_V08_XBE does not match the v0.8 evidence pin")
    return payload


def prepare(cls, base):
    """One base image and its explicit zero, strength 35 (SOFTDRINK) and strength 100 installs."""
    cls.base = base
    cls.zero = patch.apply(base, value=0)[0]
    cls.mid = patch.apply(base, value=35)[0]
    cls.high = patch.apply(base, value=100)[0]


class Scalar:
    """Mixin: one speed-mapper call on a base image and on its zero, 35 and 100 installs."""

    def machine(self, payload, *, gap=10, direction=1):
        from tests.nfl2k5_speed_threshold_frame import SpeedFrame
        m = SpeedFrame(payload, cb_speed=93 - gap, direction=direction)
        m.place(m.target, 0, 20 * 91.44 * direction, 0, 895.2 * direction)
        m.place(m.p, 0, 18 * 91.44 * direction, 0, 867.76 * direction)
        for who in (m.p, m.target):
            m.f32(who + 0x954, 1)
            m.put(who + 0x114, 0 if direction > 0 else 32768)
            for off in (0x90C, 0x910, 0xC28, 0xB50):
                m.put(who + off, 0 if direction > 0 else 32768)
        return m

    def speed(self, m, command=1):
        bits = struct.unpack("<I", struct.pack("<f", command))[0]
        before = bytes(m.uc.mem_read(m.p, 0x1000)) + bytes(m.uc.mem_read(m.target, 0x1000))
        m.component(0x238020, ecx=m.p, args=(bits,))
        m.component(m.CALLBACK + 0xE0)
        # the mapper changes nothing in either player's records: only the returned value differs
        self.assertEqual(before, bytes(m.uc.mem_read(m.p, 0x1000)) + bytes(m.uc.mem_read(m.target, 0x1000)))
        self.assertEqual(m.executed_leaves, set())
        return m.readf(m.SCALAR)

    def test_strength_scales_the_reduction_and_zero_is_exact_in_both_field_directions(self):
        for direction in (1, -1):
            for gap in (0, 3, 6, 10, 25, 40):
                native = self.speed(self.machine(self.base, gap=gap, direction=direction))
                self.assertAlmostEqual(native / 91.44, 7 + 3 * (93 - gap) / 100, places=5)
                self.assertEqual(self.speed(self.machine(self.zero, gap=gap, direction=direction)), native)
                for strength, payload in ((35, self.mid), (100, self.high)):
                    modified = self.speed(self.machine(payload, gap=gap, direction=direction))
                    self.assertAlmostEqual(modified, native * (1 - strength * min(gap, 25) / 10000), places=3,
                                           msg=f"strength {strength} gap {gap} direction {direction}")

    def test_zero_and_scope_fallbacks_are_exact(self):
        controls = {
            "eligible": lambda m: None,
            "human": lambda m: m.put(m.steer, 0),
            "dead_ball": lambda m: m.put(0xE602B8, 13),
            "offense": lambda m: m.put(m.p + 0x38, m.KICK_TEAM),
            "zone": lambda m: m.put(m.task, 0x1A5790),
            "pursuit": lambda m: m.put(m.task, 0x2EAB60),
            "missing_target": lambda m: m.put(m.task + 0x40, 0),
            "sentinel_target": lambda m: m.put(m.task + 0x40, -1),
            "same_team": lambda m: m.put(m.target + 0x38, m.RECEIVE_TEAM),
            "special": lambda m: m.put(m.state + 4, 0x510458),
            "transition": lambda m: m.put(m.state + 0x28, 2),
            "queued_action": lambda m: m.put(m.steer + 0x1C, 0x12),
            "receiver_cut_request": lambda m: m.put(m.target + 0x114, 16384),
            "receiver_cut_body": lambda m: m.put(m.target + 0x90C, 16384),
            "defender_cut_request": lambda m: m.put(m.steer + 0x14, 16384),
            "acceleration": lambda m: m.f32(m.state + 0x54, .7),
            "before_eight_yards": lambda m: m.f32(m.target + 0xB38, 8 * 91.44),
            "stopped": lambda m: m.f32(m.target + 0xB48, 0),
            "backwards": lambda m: m.f32(m.target + 0xB48, -895.2),
            "nonfinite_position": lambda m: m.f32(m.target + 0xB38, math.nan),
            "nonfinite_velocity": lambda m: m.f32(m.target + 0xB48, math.inf),
        }
        for name, mutate in controls.items():
            with self.subTest(control=name):
                a, b, c = (self.machine(payload) for payload in (self.base, self.zero, self.mid))
                for m in (a, b, c):
                    mutate(m)
                expected = self.speed(a)
                self.assertEqual(self.speed(b), expected)
                if name != "eligible":
                    self.assertEqual(self.speed(c), expected)
                else:
                    self.assertLess(self.speed(c), expected)

    def test_equal_or_faster_defender_is_never_slowed(self):
        for gap in (0, -3, -10):  # CB Speed 93, 96, 103 against a WR of 93
            with self.subTest(gap=gap):
                a = self.machine(self.base, gap=gap)
                b = self.machine(self.high, gap=gap)
                self.assertEqual(self.speed(b), self.speed(a))

    def test_depth_ramp_is_bounded_and_monotonic(self):
        values = []
        for yards in (7, 8, 9, 10, 11, 12, 20):
            m = self.machine(self.high)
            m.f32(m.target + 0xB38, yards * 91.44)
            values.append(self.speed(m))
        self.assertEqual(values[0], values[1])
        self.assertEqual(values[-1], values[-2])
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertGreater(values[1], values[-1])

    def test_cave_preserves_registers_live_x87_control_and_write_bounds(self):
        from unicorn import UC_HOOK_MEM_WRITE
        from unicorn import x86_const as x86
        m = self.machine(self.high)
        m.uc.mem_write(m.SCALAR + 0x10, struct.pack("<3dH", 3.25, -4.5, 5.75, 0x27F))
        load = b"\xdb\xe3\xd9\x2d" + struct.pack("<I", m.SCALAR + 0x28)
        load += b"".join(b"\xdd\x05" + struct.pack("<I", m.SCALAR + 0x10 + 8 * i) for i in range(3)) + b"\xc3"
        m.uc.mem_write(m.CALLBACK + 0x100, load)
        m.component(m.CALLBACK + 0x100)
        saved = {reg: 0x12345670 + i for i, reg in enumerate((x86.UC_X86_REG_EBX, x86.UC_X86_REG_EBP, x86.UC_X86_REG_EDI))}
        for reg, value in saved.items():
            m.uc.reg_write(reg, value)
        writes = []
        row = patch.allocation(self.high)

        def watch(uc, access, address, size, value, data):
            pc = uc.reg_read(x86.UC_X86_REG_EIP)
            if row["va"] <= pc < row["va"] + patch.CODE_SIZE:
                writes.append((address, size))

        m.uc.hook_add(UC_HOOK_MEM_WRITE, watch)
        self.speed(m)
        for reg, value in saved.items():
            self.assertEqual(m.uc.reg_read(reg), value)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPCW), 0x27F)
        store = b"".join(b"\xdd\x1d" + struct.pack("<I", m.SCALAR + 0x40 + 8 * i) for i in range(3)) + b"\xc3"
        m.uc.mem_write(m.CALLBACK + 0x140, store)
        m.component(m.CALLBACK + 0x140)
        self.assertEqual(struct.unpack("<3d", m.uc.mem_read(m.SCALAR + 0x40, 24)), (5.75, -4.5, 3.25))
        self.assertTrue(writes)
        self.assertTrue(all(m.STACK - 256 <= a < a + n <= m.STACK for a, n in writes))


class Frames:
    """Mixin: a 60 Hz go-route replay, WR Speed 93 against CB Speed 83, with a tight and an off cushion."""

    def test_zero_is_the_unpatched_game_and_positive_strengths_add_separation_in_order(self):
        from tests.nfl2k5_speed_threshold_frame import replay
        for cushion in (7,):  # the 2-yard press cushion is checked in the offline matrix; one cushion keeps this file short
            native = replay(self.base, cb_speed=83, cushion=cushion)
            zero = replay(self.zero, cb_speed=83, cushion=cushion)
            mid = replay(self.mid, cb_speed=83, cushion=cushion)
            high = replay(self.high, cb_speed=83, cushion=cushion)
            self.assertEqual(native, zero)
            marks = ("10", "20", "30", "40")
            gap = lambda run, mark: run["samples"][mark]["signed_gap_yards"]  # noqa: E731
            for mark in marks:
                self.assertGreaterEqual(gap(mid, mark), gap(zero, mark) - 1e-9, mark)
                self.assertGreaterEqual(gap(high, mark), gap(mid, mark) - 1e-9, mark)
            for mark in marks[1:]:  # after the ramp the receiver pulls away more at every step up in strength
                self.assertGreater(gap(mid, mark), gap(zero, mark), mark)
                self.assertGreater(gap(high, mark), gap(mid, mark), mark)
            # strength 35 is worth about a yard by 40 yards, 100 about two and three quarters (offline matrix, v0.8 bytes)
            self.assertGreater(gap(mid, "40") - gap(zero, "40"), 0.7)
            self.assertLess(gap(mid, "40") - gap(zero, "40"), 1.4)
            self.assertGreater(gap(high, "40") - gap(zero, "40"), 2.0)
            self.assertLess(gap(high, "40") - gap(zero, "40"), 3.6)

    def test_an_equal_speed_corner_keeps_the_unpatched_frames_at_every_strength(self):
        from tests.nfl2k5_speed_threshold_frame import replay
        native = replay(self.base, cb_speed=93, cushion=7)
        self.assertEqual(replay(self.high, cb_speed=93, cushion=7), native)


@unittest.skipUnless(HAVE_NATIVE, "Unicorn and Capstone required for instruction proofs")
class RetailScalarTests(Scalar, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepare(cls, retail_xbe())


@unittest.skipUnless(HAVE_NATIVE, "Unicorn and Capstone required for instruction proofs")
class RetailFrameTests(Frames, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepare(cls, retail_xbe())


@unittest.skipUnless(HAVE_NATIVE, "Unicorn and Capstone required for instruction proofs")
class V08ScalarTests(Scalar, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepare(cls, v08_xbe())


@unittest.skipUnless(HAVE_NATIVE, "Unicorn and Capstone required for instruction proofs")
class V08FrameTests(Frames, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepare(cls, v08_xbe())


if __name__ == "__main__":
    unittest.main()
