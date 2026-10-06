"""Full Xenon register and guarded-write proof for the emitted visual latch."""
import struct
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_apf_playcall_patch import SyntheticMachine, MASK64
from mod_editor.core import apf2k8_charge_abilities as p


class LatchMachine(SyntheticMachine):
    def __init__(self, profile):
        super().__init__()
        self.profile = profile
        self.player, self.state, self.roster, self.descriptor = 0x60000, 0x61000, 0x62000, 0x63000
        self.add(self.player, bytes(0x80))
        self.add(self.state, bytes(0x400))
        self.add(self.roster, bytes(0x150))
        self.add(self.descriptor, bytes(4))
        self.add(p.LATCH_START, bytes(p.LATCH_LIMIT - p.LATCH_START))
        self.put(self.player + 0x14, self.state, 4)
        self.put(self.player + 0x44, self.roster, 4)
        self.put(self.state + 4, self.descriptor, 4)
        self.put(self.state + 0xFC, 0x40000000, 4)
        self.put(self.state, 0x1D, 4)
        self.put(self.descriptor, 0x10000000, 4)
        self.put(self.roster + 44, 8, 1)
        self.r[3] = self.player
        self.r[10] = self.state
        self.r[29] = self.player
        self.r[12] = 0xAABBCCDD00000000 | (p.SHARED_MOVE_RETURN + (0xE88 if profile == p.PROFILES[1] else 0))
        self.f = [float(i) / 3 for i in range(32)]
        self.f[18], self.f[28] = 1., 0.
        self.fpscr = 0xABCDEF08

    def get(self, address, size):
        return super().get(address & 0xFFFFFFFF, size)

    def put(self, address, value, size):
        return super().put(address & 0xFFFFFFFF, value, size)

    def run_leaf(self, code, start, stop, *, feedback=False, downgrade=False):
        words = {start + i: int.from_bytes(code[i:i + 4], 'big') for i in range(0, len(code), 4)}
        before, cr, control, fpr, fpscr = self.r.copy(), self.cr, (self.lr, self.ctr), self.f.copy(), self.fpscr
        outside = {a: v for a, v in self.mem.items() if not 0x10000 <= a < 0x11000}
        pc = start
        for step in range(2_000):
            if pc == stop:
                break
            w = words[pc]
            op, rt, ra, rb = w >> 26, w >> 21 & 31, w >> 16 & 31, w >> 11 & 31
            imm, nxt = self.signed(w, 16), pc + 4
            if op in (14, 15):
                self.r[rt] = ((self.r[ra] if ra else 0) + (imm << (16 if op == 15 else 0))) & MASK64
            elif op in (32, 34):
                self.r[rt] = self.get(self.r[ra] + imm, 4 if op == 32 else 1)
            elif op in (36, 37):
                at = (self.r[ra] + imm) & MASK64
                self.put(at, self.r[rt], 4)
                if op == 37:
                    self.r[ra] = at
            elif op in (58, 62):
                at = (self.r[ra] + self.signed(w & 0xFFFC, 16)) & MASK64
                if op == 58:
                    self.r[rt] = self.get(at, 8)
                else:
                    self.put(at, self.r[rt], 8)
            elif op == 10:
                left, right = self.r[ra] & 0xFFFFFFFF, w & 0xFFFF
                shift = 28 - 4 * (rt >> 2)
                self.cr = (self.cr & ~(15 << shift)) | ((8 if left < right else 4 if left > right else 2) << shift)
            elif op == 28:
                self.r[ra] = self.r[rt] & (w & 0xFFFF)
                self.cr = (self.cr & 0x0FFFFFFF) | ((2 if self.r[ra] == 0 else 4) << 28)
            elif op == 18:
                assert not w & 3
                nxt = pc + self.signed(w & 0x3FFFFFC, 26)
            elif op == 16:
                assert rt in (4, 12)
                bit = self.cr >> (31 - ra) & 1
                if (rt == 12 and bit) or (rt == 4 and not bit):
                    nxt = pc + self.signed(w & 0xFFFC, 16)
            elif op == 31:
                xo = w >> 1 & 1023
                if xo == 19:
                    self.r[rt] = self.cr
                elif xo == 144:
                    assert w >> 12 & 255 == 255
                    self.cr = self.r[rt] & 0xFFFFFFFF
                elif xo in (0, 32):
                    left, right = self.r[ra] & 0xFFFFFFFF, self.r[rb] & 0xFFFFFFFF
                    if xo == 0:
                        left, right = self.signed(left, 32), self.signed(right, 32)
                    shift = 28 - 4 * (rt >> 2)
                    self.cr = (self.cr & ~(15 << shift)) | ((8 if left < right else 4 if left > right else 2) << shift)
                else:
                    raise AssertionError(f'Unsupported latch XO {xo}')
            elif op == 63:
                assert w in (0xFFC0E090, 0xFFC09090)
                self.f[30] = self.f[rb]
            else:
                raise AssertionError(f'Unsupported latch instruction {w:08x}')
            pc = nxt
        else:
            raise AssertionError('Latch exceeded bounded instruction budget')
        assert self.r == before, [(i, hex(a), hex(b)) for i, (a, b) in enumerate(zip(self.r, before)) if a != b]
        assert self.cr == cr
        assert (self.lr, self.ctr) == control
        assert self.fpscr == fpscr
        assert all(a == b for i, (a, b) in enumerate(zip(self.f, fpr)) if not (feedback and i == 30))
        if not feedback:
            assert self.f == fpr
        permitted = [(p.LATCH_START, p.LATCH_LIMIT)]
        if downgrade:
            permitted.append((self.state + 0x1A8, self.state + 0x1AC))
        assert all(self.mem[a] == v for a, v in outside.items() if not any(lo <= a < hi for lo, hi in permitted))
        return step

    def consume(self):
        return self.run_leaf(p.latch_consume_trampoline(self.profile), p.LATCH_CONSUME_CAVE, p.address(p.CONSUME_HOOK + 4, self.profile))

    def feedback(self):
        self.run_leaf(p.latched_feedback_trampoline(self.profile), p.LATCH_FEEDBACK_CAVE,
                      p.feedback_address(p.FEEDBACK_HOOK + 4, self.profile), feedback=True)
        return self.f[30]


class LatchAbiTests(unittest.TestCase):
    def test_full_width_registers_cr_fprs_control_and_private_write_scope(self):
        for profile in p.PROFILES:
            m = LatchMachine(profile)
            m.consume()
            self.assertEqual(m.get(p.LATCH_START + 8, 4), 1)
            self.assertEqual(m.feedback(), 1.)
            m.r[11] = 1 << 22
            m.run_leaf(p.latch_downgrade_trampoline(profile), p.LATCH_DOWNGRADE_CAVE,
                       p.address(p.DOWNGRADE_HOOK + 4, profile), downgrade=True)
            self.assertEqual(m.get(m.state + 0x1A8, 4), 1 << 22)
            self.assertEqual(m.feedback(), 0.)

    def test_finite_charge_category_null_and_action_qualifications(self):
        for profile in p.PROFILES:
            m = LatchMachine(profile)
            for bits, expected in ((0, 0), (0x3F800000, 0), (0x3FFFF000, 0), (0x40000000, 1),
                                   (0x40400000, 1), (0x7F800000, 0), (0x7FC00000, 0), (0xC0000000, 0)):
                m.put(m.state + 0xFC, bits, 4)
                m.consume()
                self.assertEqual(m.feedback(), expected)
            m.put(m.state + 0xFC, 0x40000000, 4)
            m.r[12] = 0x1122334488888888  # ordinary unclassified native caller
            m.put(m.state + 4, 0, 4)
            m.consume()
            self.assertEqual(m.feedback(), 1.)  # no new null-descriptor read
            m.put(m.state + 4, m.descriptor, 4)
            for category, union, own in ((0x17, 6, 4), (0x19, 6, 2), (0x1B, 0, 0x80)):
                m.put(m.descriptor, category << 24, 4)
                for packed, expected in ((0, 0), (8, 0), (2, int(bool(union))), (4, int(bool(union)))):
                    m.put(m.roster + 44, packed, 1)
                    m.put(m.roster + 36, 0, 1)
                    m.put(m.roster + 37, 0, 1)
                    m.consume()
                    self.assertEqual(m.feedback(), expected)
                m.put(m.roster + (37 if category == 0x1B else 36), own, 1)
                m.consume()
                self.assertEqual(m.feedback(), 1.)

    def test_bounded_saturation_and_state_key_roster_reuse(self):
        for profile in p.PROFILES:
            m = LatchMachine(profile)
            for i in range(p.LATCH_COUNT):
                m.put(p.LATCH_START + i * p.LATCH_ENTRY_SIZE, 0x100000 + i * 0x400, 4)
                m.put(p.LATCH_START + i * p.LATCH_ENTRY_SIZE + 4, m.roster, 4)
                m.put(p.LATCH_START + i * p.LATCH_ENTRY_SIZE + 8, 1, 4)
            table = bytes(m.get(p.LATCH_START + i, 1) for i in range(p.LATCH_LIMIT - p.LATCH_START))
            self.assertLess(m.consume(), 2_000)
            self.assertEqual(m.feedback(), 0.)
            self.assertEqual(bytes(m.get(p.LATCH_START + i, 1) for i in range(len(table))), table)
            m.put(p.LATCH_START, m.state, 4)
            m.put(p.LATCH_START + 4, m.roster + 4, 4)
            self.assertEqual(m.feedback(), 0.)
            m.consume()
            self.assertEqual(m.feedback(), 1.)
            self.assertEqual(m.get(p.LATCH_START + 4, 4), m.roster)


if __name__ == '__main__':
    unittest.main(verbosity=2)
