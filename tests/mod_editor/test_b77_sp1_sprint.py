"""Execute the real decoder, burst initializer and movement calculation."""
from pathlib import Path
import hashlib
import itertools
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_tap_burst as burst
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tools.b77 import sp1_repair as repair
try:
    from tests.nfl2k5_sprint_machine import SprintMachine
except ImportError:
    SprintMachine = None

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XBE", "/nonexistent/retail.xbe"))
BASE = Path(os.environ.get("B772_SP1_BASE_XBE", "/nonexistent/base.xbe"))


@unittest.skipUnless(SprintMachine and RETAIL.is_file(), "Unicorn and pinned retail fixture required")
class SprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        assert hashlib.sha256(cls.retail).hexdigest() == RETAIL_SHA256
        cls.fixed = abilities.apply_rating_rules(cls.retail, charge_stars_only=True, right_stick_stars_only=True)[0]
        cls.old, cls.new = SprintMachine(cls.retail), SprintMachine(cls.fixed)

    def test_low_break_tackle_reproduces_weak_or_zero_burst_and_fix_matches_full_retail_burst(self):
        for scale, speed, context, controller in itertools.product((0, .15, .2, 1), (93, 99, 100),
                                                                 (8, 9, 10, 11, 15, 16), range(4)):
            with self.subTest(scale=scale, speed=speed, context=context, controller=controller):
                values = []
                for m in (self.old, self.new):
                    m.setup(controller=controller, speed=speed)
                    m.context = context
                    m.f32(m.S + 0x190, scale)
                    m.frame(True); m.frame(False)
                    self.assertEqual(m.frame(True)[:2], (0x16, 0x16))
                    values.append((*m.enter_burst(), m.sprint_rate()))
                self.assertAlmostEqual(values[0][0], 1 + .04 * scale, places=6)
                self.assertAlmostEqual(values[1][0], 1.04, places=6)
                self.assertEqual(values[1][1], .25)
                self.assertGreaterEqual(values[1][2], values[0][2])

    def test_charged_burst_exactly_preserves_retail_for_condition_and_role_scales(self):
        for condition, scale in itertools.product((0, .05, .37, .8, .999, 1), (0, .001, .15, .333, .9, 1)):
            values = []
            for m in (self.old, self.new):
                m.setup(abilities=0x4100, speed=93)
                m.f32(m.COND + 4, condition)
                m.f32(m.S + 0x190, scale)
                m.f32(m.S + 0x44, 1)
                m.u32(m.S + 0x90, 3)
                m.u32(m.T + 0x1C, 0x16)
                values.append((*m.enter_burst(), m.sprint_rate()))
            self.assertEqual(values[0], values[1], (condition, scale))
            self.assertEqual(values[1][1], 1.5)

    def test_hold_charge_and_right_stick_stay_star_locked_after_possession_change(self):
        m = self.new
        for carrier, context, star in itertools.product((False, True), (9, 10, 15, 16), (False, True)):
            m.setup(carrier=carrier, abilities=0x4100 if star else 0)
            m.context = context
            decoded = [m.frame(True)[0] for _ in range(90)]
            self.assertEqual(decoded, [0x16] + [0] * 89)
            self.assertEqual(m.number(m.S + 0x44), 1 if star else 0)
            if not star:
                self.assertEqual(m.read(m.S + 0x90) & 3, 0)
            # Interception/fumble switches the same live DB into carrier
            # context. Neither position nor former defending role grants
            # special moves; every right-stick command is still filtered.
            m.u32(m.BALL, m.P)
            m.context = 10
            m.u32(0xA9B960, 10)
            m.u32(m.T + 0x1C, 0x27)
            m.run("filter", regs={"EBX": m.P})
            self.assertEqual(m.read(m.T + 0x1C), 0x27 if star else 0)

    def test_speedster_above_one_still_requires_star_and_stored_permission(self):
        m = self.new
        for word, expected in ((0, 1), (0x20, 1), (0x100, 1), (0x120, 1.27)):
            m.setup(speed=127, abilities=word)
            self.assertAlmostEqual(m.rating, expected, places=6)

    def test_initializer_span_preserves_integer_abi_and_deeper_x87_stack(self):
        from unicorn import x86_const as x86
        # Give this bounded slice its own translation cache. The full
        # initializer tests cache blocks past END in the shared machines.
        for payload, duration in itertools.product((self.retail, self.fixed), (.25, 1.5)):
            m = SprintMachine(payload)
            m.setup()
            for value in (3.5, .8):
                m.f32(m.SCRATCH + 16, value)
                m.uc.mem_write(m.STOP + 0x300, b"\xd9\x05" + struct.pack("<I", m.SCRATCH + 16))
                m.uc.emu_start(m.STOP + 0x300, m.STOP + 0x306, count=1)
            m.f32(m.STACK + 0x10, 1.04 if duration == .25 else 1.075)
            m.f32(m.STACK + 0x1C, duration)
            m.f32(m.S + 0x190, .15)
            registers = dict(ESI=m.S, EDI=m.P, EFLAGS=0x246)
            m.run(burst.START, stop=burst.END, regs=registers)
            for name, value in {**registers, "ESP": m.STACK, "ECX": m.P,
                                "EBX": 0x11111111, "EBP": 0x44444444}.items():
                self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_" + name)), value, name)
            self.assertEqual(m.pop_float(), 3.5)

    def test_source_replay_and_mixed_initializer_refusal(self):
        self.assertEqual(abilities.apply_rating_rules(self.fixed)[0], self.fixed)
        self.assertEqual(burst.status(self.fixed), "applied")
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        bad = bytearray(self.fixed)
        bad[XbeImage(self.fixed).offset(burst.START, 1)] ^= 1
        self.assertEqual(burst.status(bad), "foreign")
        with self.assertRaises(ValueError):
            burst.apply(bad)

    @unittest.skipUnless(BASE.is_file(), "Pinned b772 base fixture required")
    def test_actual_base_source_equality_exact_scope_replay_and_unknown_hash_refusal(self):
        raw = BASE.read_bytes()
        fixed, receipt = repair.repair_xbe(raw)
        self.assertEqual(fixed, abilities.apply_rating_rules(raw)[0])
        self.assertEqual(receipt["changed_bytes"], 69)
        self.assertEqual(receipt["outside_scope_changed_bytes"], 0)
        replay, r = repair.repair_xbe(fixed)
        self.assertEqual(replay, fixed)
        self.assertEqual(r["changed_bytes"], 0)
        # A changed unrelated header byte is not a new approved input,
        # even when both initializer and section digests are recognized.
        bad = bytearray(raw)
        bad[0x120] ^= 1
        with self.assertRaises(ValueError):
            repair.repair_xbe(bytes(bad))


if __name__ == "__main__":
    unittest.main()
