"""Bounded native reaction and acceleration helpers, not a console/game witness."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_coverage_slider as coverage
from mod_editor.core import nfl2k5_scramble_tuning as scramble
from mod_editor.core import nfl2k5_xbe_space as space
from tests.nfl2k5_gameplay_levers_fixture import (
    XBE, HAVE_UNICORN, ARENA, STACK, RETURN, OUTPUT, load, finish_float)


@unittest.skipUnless(XBE.is_file() and HAVE_UNICORN, "retail default.xbe extraction or unicorn is absent")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.coverage, _ = coverage.apply(cls.retail)
        cls.scramble, _ = scramble.apply(cls.retail)

    def _accel(self, payload, *, q=.8, speed=60, position=0, phase=14, holder=True,
               agility=.5, multiplier=1., weight=220, ball_kind=1, ball_pointer=None, controller=0):
        from unicorn.x86_const import (UC_X86_REG_EDI, UC_X86_REG_EAX, UC_X86_REG_EBX,
            UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EBP,
            UC_X86_REG_ESP, UC_X86_REG_EFLAGS, UC_X86_REG_FPCW, UC_X86_REG_FPSW)
        from unicorn import UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_CODE
        uc = load(payload)
        player, roster, state, ball = ARENA, ARENA + 0x1000, ARENA + 0x2000, ARENA + 0x3000
        def word(va, value):
            uc.mem_write(va, struct.pack("<I", value))
        word(player + 0x3C, roster)
        word(player + 0x10, state)
        word(player + 0xC, ARENA + 0x5000)
        word(ARENA + 0x5000, controller & 0xFFFFFFFF)
        uc.mem_write(roster + 0x2A, bytes([weight - 150]))
        uc.mem_write(roster + 0x35, bytes([position, speed]))
        uc.mem_write(state + 0x190, struct.pack("<f", multiplier))
        uc.mem_write(state + 0x1B8, struct.pack("<f", agility))
        word(0xE602B8, phase)
        word(0xE5FC00, ball if ball_pointer is None else ball_pointer)
        word(ball, player if holder else player + 0x8000)
        word(ball + 0x1C, ball_kind)
        for section in space.layout(payload)["regions"]:
            if section["kind"] == "code":
                uc.mem_protect(section["va"], section["size"], UC_PROT_READ | UC_PROT_EXEC)
        uc.reg_write(UC_X86_REG_EDI, player)
        registers = (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                     UC_X86_REG_ESI, UC_X86_REG_EBP)
        for i, register in enumerate(registers):
            uc.reg_write(register, 0x12340000 + i * 16)
        uc.reg_write(UC_X86_REG_EFLAGS, 0x246)
        uc.reg_write(UC_X86_REG_FPCW, 0x27F)
        calls = []
        uc.hook_add(UC_HOOK_CODE, lambda _uc, addr, _size, _user: calls.append(addr),
                    begin=scramble.INTERPOLATOR_VA, end=scramble.INTERPOLATOR_VA)
        result = finish_float(uc, 0x1DF190, STACK, q)
        self.assertEqual(calls, [scramble.INTERPOLATOR_VA])
        self.assertEqual(uc.reg_read(UC_X86_REG_ESP), STACK + 8)
        self.assertEqual(uc.reg_read(UC_X86_REG_EDI), player)
        self.assertEqual(uc.reg_read(UC_X86_REG_FPCW), 0x27F)
        self.assertEqual((uc.reg_read(UC_X86_REG_FPSW) >> 11) & 7, 0)
        return result, tuple(uc.reg_read(r) for r in registers), uc.reg_read(UC_X86_REG_EFLAGS)

    def test_native_increment_reduces_only_eligible_slow_carriers(self):
        for q in (0, .5, .7, .8, .875, .9, .95, .99, 1, 1.1):
            with self.subTest(q=q):
                before, regs, flags = self._accel(self.retail, q=q)
                after, new_regs, new_flags = self._accel(self.scramble, q=q)
                self.assertAlmostEqual(after, before * .65, places=7)
                # Native interpolator leaves its table iterator in volatile
                # EAX on interior knots. The parent returns its float in ST0;
                # relocation changes that scratch pointer, not the ABI.
                self.assertEqual(regs[1:], new_regs[1:])
                if 0x50A5B8 <= regs[0] < 0x50A5E0:
                    a = next(a for a in space.layout(self.scramble)["allocations"] if a["owner"] == scramble.OWNER)
                    self.assertEqual(new_regs[0], regs[0] - 0x50A5B8 + a["va"] + scramble.TABLE_OFFSET + 4)
                else:
                    self.assertEqual(regs[0], new_regs[0])
                self.assertEqual(flags, new_flags)

    def test_threshold_uses_inclusive_raw_speed_not_the_cached_envelope(self):
        for speed in (0, 59, 60, 61, 99, 255):
            before = self._accel(self.retail, speed=speed)[0]
            after = self._accel(self.scramble, speed=speed)[0]
            self.assertAlmostEqual(after, before * (.65 if speed <= 60 else 1), places=7)

    def test_non_qbs_dead_ball_loose_ball_and_different_holder_are_retail(self):
        exclusions = ([dict(position=p) for p in range(1, 17)] +
                      [dict(phase=p) for p in (0, 3, 13, 15, 18)] +
                      [dict(holder=False), dict(ball_kind=0), dict(ball_kind=2),
                       dict(ball_pointer=0), dict(ball_pointer=0xFFFFFFFF)])
        for kwargs in exclusions:
            with self.subTest(**kwargs):
                self.assertEqual(self._accel(self.retail, **kwargs), self._accel(self.scramble, **kwargs))

    def test_native_weight_and_agility_still_matter(self):
        values = []
        for agility, weight in ((.3, 180), (.3, 320), (.99, 180), (.99, 320)):
            kwargs = dict(agility=agility, weight=weight)
            before = self._accel(self.retail, **kwargs)[0]
            after = self._accel(self.scramble, **kwargs)[0]
            self.assertAlmostEqual(after, before * .65, places=7)
            values.append(after)
        self.assertGreater(values[0], values[1])
        self.assertGreater(values[2], values[0])

    def test_human_and_valid_cpu_steering_receive_identical_increment(self):
        self.assertEqual(self._accel(self.scramble, controller=0), self._accel(self.scramble, controller=-1))

    def _reaction(self, payload, coverage_value, side, roll, angle=0, context=.8):
        from unicorn.x86_const import UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EIP
        uc = load(payload)
        player, state, team, position, ball, target = [ARENA + i * 0x1000 for i in range(6)]
        def word(va, value):
            uc.mem_write(va, struct.pack("<I", value))
        word(player + 0x10, state)
        word(player + 0x38, team)
        word(team + 0x30, side)
        word(player + 0x18, position)
        word(0xE5FC00, ball)
        word(ball + 0x14, target)
        uc.mem_write(state + 0x190, struct.pack("<f", context))
        # Set the other side to a deliberately different value.
        uc.mem_write(0xAAB8C0 + 6 * 4, struct.pack("<f", coverage_value if side == 0 else 1 - coverage_value))
        uc.mem_write(0xAAB8C0 + 16 * 4, struct.pack("<f", coverage_value if side else 1 - coverage_value))
        # Geometry and RNG are explicit fixture boundaries. Run the real side
        # accessor, both native context curves and all reaction math/branches.
        uc.mem_write(0x210B0, b"\xb8" + struct.pack("<I", angle) + b"\xc2\x08\0")
        uc.mem_write(0x217AE0, b"\x31\xc0\xc3")
        uc.mem_write(OUTPUT, struct.pack("<f", roll))
        uc.mem_write(0x48B90, b"\xd9\x05" + struct.pack("<I", OUTPUT) + b"\xc3")
        uc.mem_write(STACK, struct.pack("<I", RETURN))
        uc.reg_write(UC_X86_REG_ESP, STACK)
        uc.reg_write(UC_X86_REG_ESI, player)
        uc.emu_start(0x1F4250, RETURN, count=10_000)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), RETURN)
        self.assertEqual(uc.reg_read(UC_X86_REG_ESP), STACK + 4)
        return uc.reg_read(UC_X86_REG_EAX)

    def test_real_reaction_uses_each_sides_coverage_and_preserves_neutral(self):
        # Facing zero contributes .30 and context .8 contributes .10, so the
        # three new thresholds are .4000 / .5125 / .6250.
        for side in (0, 1):
            for c, expected in ((0, .4), (.5, .5125), (1, .625)):
                self.assertEqual(self._reaction(self.coverage, c, side, expected - .0001), 1)
                self.assertEqual(self._reaction(self.coverage, c, side, expected + .0001), 0)
            for roll in (.1, .4, .5124, .5126, .8):
                self.assertEqual(self._reaction(self.retail, .5, side, roll), self._reaction(self.coverage, .5, side, roll))

    def test_zero_does_not_disable_every_reaction_and_context_still_matters(self):
        self.assertEqual(self._reaction(self.coverage, 0, 0, .1), 1)
        self.assertEqual(self._reaction(self.coverage, 0, 0, .2, angle=32767, context=0), 0)


if __name__ == "__main__":
    unittest.main()
