"""Bounded native proofs for the run-blocking owner. No game boot, no witnessed play.

The real retail engagement start roll 0x230320 and the real per-tick break-up decision 0x233040 run in Unicorn with
their real callees (rating accessor 0x17B010, curve interpolator 0x1B0AE0, angle 0x210B0, shed angle 0x230A00,
sliders 0x17B8F0, run latch 0x2F3AC0, native random 0x48B90, push 0x232750). Player skeletons, positions, wanted
headings, the per-player rating cache and the sliders are supplied inputs; the leverage term 0x2D4250 is a stub that
returns a chosen value. Private data is skipped when absent.
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

from mod_editor.core import nfl2k5_run_blocking as rb, nfl2k5_run_blocking_code as assembly
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

B776_SHA256 = "b00027f9196cd9c32be809e092970a317f4f4ccb758360266a556af48ec604c3"
DT = 1.0 / 60.0
RUN_COVERAGE, RUN_BLOCKING = 19, 15


def b776_xbe():
    path = os.environ.get("NFL2K5_B776_XBE")
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("NFL2K5_B776_XBE (the extracted b776 test-disc default.xbe) is not set")
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != B776_SHA256:
        raise unittest.SkipTest("NFL2K5_B776_XBE does not match the b776 evidence pin")
    return payload


class Machine:
    """One offensive blocker against one defender, both CPU-controlled unless told otherwise."""
    BLK, DEF, CARRIER = 0x3000000, 0x3010000, 0x3020000
    OFF_TEAM, DEF_TEAM, OUT, LEVER = 0x3030000, 0x3031000, 0x3032000, 0x3033000
    STACK, STOP = 0x3100000, 0x3120000

    def __init__(self, payload):
        self.uc = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        pages = {}
        for s in image.sections:
            for va in range(s.start & -4096, (s.start + s.size + 4095) & -4096, 4096):
                pages[va] = uc.UC_PROT_ALL
        pages[0x10000] = uc.UC_PROT_ALL
        ranges = []
        for va in sorted(pages):
            if ranges and ranges[-1][1] == va:
                ranges[-1][1] += 4096
            else:
                ranges.append([va, va + 4096])
        for a, b in ranges:
            self.uc.mem_map(a, b - a)
        self.uc.mem_write(0x10000, payload[:4096])
        for s in image.sections:
            if s.raw_size:
                self.uc.mem_write(s.start, image.read(s.start, s.raw_size))
        self.uc.mem_map(0x3000000, 0x40000)
        self.uc.mem_map(self.STACK, 0x20000)
        self.uc.mem_map(self.STOP, 0x1000)
        self.uc.mem_write(self.STOP, b"\xf4")
        # Leverage 0x2D4250 (ecx, edx; ret): a stub that loads the chosen value.
        self.uc.mem_write(0x2D4250, b"\xd9\x05" + struct.pack("<I", self.LEVER) + b"\xc3")
        self.f32(self.LEVER, 0.0)
        for p, team, slot in ((self.BLK, self.OFF_TEAM, 1), (self.DEF, self.DEF_TEAM, 12),
                              (self.CARRIER, self.OFF_TEAM, 2)):
            self.player(p, team, slot)
        self.u32(0xE60280, self.OFF_TEAM)
        self.u32(0xE60284, self.DEF_TEAM)
        self.u32(0xE602BC, 0)
        self.u32(0xE602B4, 0)
        self.u32(0xE5FF80, 0)
        self.u32(0xC8F294, 0)
        self.u32(0xC8F290, 0)
        self.u32(0xE5FC00, 0)
        self.u32(0xB71D10, 1)
        self.f32(0xB71D0C, DT)
        for side in range(2):                       # all ten runtime sliders, both sides, at 0.5
            for i in range(10):
                self.f32(0xAAB8C0 + side * 0x28 + i * 4, 0.5)
        self.place(self.BLK, 0.0, 0.0)
        self.place(self.DEF, 0.0, 100.0)
        self.seed(1)

    # memory helpers
    def u32(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def f32(self, va, value):
        self.uc.mem_write(va, struct.pack("<f", value))

    def rf32(self, va):
        return struct.unpack("<f", self.uc.mem_read(va, 4))[0]

    def player(self, p, team, slot):
        """Object p: +0xC controller, +0x10 block state, +0x18 transform, +0x38 team, +0x3C rating record."""
        ctl, state, xf, rec, obj, fat = p + 0x100, p + 0x200, p + 0x600, p + 0x800, p + 0x900, p + 0xA00
        for off, value in ((0xC, ctl), (0x10, state), (0x18, xf), (0x38, team), (0x3C, rec), (0x14, p + 0xB00),
                           (0x24, p + 0xC00)):
            self.u32(p + off, value)
        self.u32(ctl, 0xFFFFFFFF)                  # CPU
        self.f32(ctl + 0x10, 0.0)
        self.u32(rec + 0x30, obj)
        self.u32(obj + 0x20, slot)
        self.u32(obj + 4, fat)
        self.f32(fat + 4, 1.0)
        self.uc.mem_write(rec + 0x34, b"\x00")
        self.u32(team + 0x30, 0)                   # no human controller on either team
        self.u32(team + 8, team + 0x100)
        self.u32(team + 0x10C, team + 0x200)
        self.f32(team + 0x204, 1.0)

    def place(self, p, x, z):
        self.f32(p + 0x600 + 0x30, x)
        self.f32(p + 0x600 + 0x38, z)

    def rating(self, p, index, value):
        slot = struct.unpack("<I", self.uc.mem_read(struct.unpack("<I", self.uc.mem_read(p + 0x800 + 0x30, 4))[0] + 0x20, 4))[0]
        self.f32(0xAA43B8 + slot * 0xE4 + index * 8, value)
        self.f32(0xAA43B8 + slot * 0xE4 + index * 8 + 4, 0.0)

    def want(self, p, throttle, heading):
        self.f32(p + 0x100 + 0x10, throttle)
        self.uc.mem_write(p + 0x100 + 0x14, struct.pack("<H", heading & 0xFFFF))

    def seed(self, seed):
        gen = random.Random(seed)
        self.u32(0xE5FCA0, 54)
        self.u32(0xE5FCA4, 23)
        for index in range(110):
            self.u32(0xE5FCA8 + index * 4, gen.getrandbits(32))

    def call(self, entry, *, ecx=0, edx=0, eax=0, esi=0, edi=0, stack=()):
        esp = self.STACK + 0x18000
        for value in reversed(stack):
            esp -= 4
            self.u32(esp, value)
        esp -= 4
        self.u32(esp, self.STOP)
        for reg, value in ((x86.UC_X86_REG_ESP, esp), (x86.UC_X86_REG_EBP, esp + 0x40), (x86.UC_X86_REG_ECX, ecx),
                           (x86.UC_X86_REG_EDX, edx), (x86.UC_X86_REG_EAX, eax), (x86.UC_X86_REG_ESI, esi),
                           (x86.UC_X86_REG_EDI, edi), (x86.UC_X86_REG_EBX, 0)):
            self.uc.reg_write(reg, value)
        self.uc.emu_start(entry, self.STOP, count=2_000_000)
        return self.uc.reg_read(x86.UC_X86_REG_EAX), self.uc.reg_read(x86.UC_X86_REG_ESP)

    def accessor(self, p, index):
        """What the native rating accessor returns for this player (ST0, read through a tiny stub)."""
        stub = 0x3034000
        self.uc.mem_write(stub, b"\x6a\x00\xe8" + struct.pack("<i", 0x17B010 - (stub + 7)) + b"\xd9\x1d"
                          + struct.pack("<I", stub + 0x40) + b"\xf4")
        esp = self.STACK + 0x18000
        self.uc.reg_write(x86.UC_X86_REG_ESP, esp)
        self.uc.reg_write(x86.UC_X86_REG_ECX, p + 0x800)
        self.uc.reg_write(x86.UC_X86_REG_EDX, index)
        self.uc.emu_start(stub, stub + 13, count=200_000)
        return self.rf32(stub + 0x40)

    # the two native routines
    def tick(self):
        """0x233040 as the block tick calls it: ECX = blocker, EAX = defender, [esp+4] = output."""
        result, esp = self.call(0x233040, ecx=self.BLK, eax=self.DEF, stack=(self.OUT,))
        assert esp == self.STACK + 0x18000, "0x233040 must return with ret 4"
        self.u32(0xB71D10, struct.unpack("<I", self.uc.mem_read(0xB71D10, 4))[0] + 1)
        return result

    def ticks_to_shed(self, limit=240):
        self.f32(self.BLK + 0x200 + 0xD8, 0.0)
        for n in range(1, limit + 1):
            if self.tick() == 2:
                return n
        return None

    def start_roll(self, run=True, side=0, flag=0):
        """0x230320 (EAX = run, EDI = defender, ESI = blocker; two stack words, ret 8)."""
        result, esp = self.call(0x230320, eax=1 if run else 0, edi=self.DEF, esi=self.BLK, stack=(side, flag))
        assert esp == self.STACK + 0x18000, "0x230320 must return with ret 8"
        return result


def heading_away(m):
    """A wanted heading for the defender pointing straight away from the blocker (the shed direction)."""
    # 0x233040 compares (heading - angle(def - blk) - 0x8000); the defender sits at +z, so 0x8000 off works.
    for heading in range(0, 0x10000, 0x800):
        m.want(m.DEF, 1.0, heading)
        m.f32(m.BLK + 0x200 + 0xD8, 0.0)
        if m.ticks_to_shed(limit=60) is not None:
            return heading
    raise AssertionError("no wanted heading sheds the block on the retail image")


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class ShedDelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, _ = rb.apply(cls.retail)

    def machine(self, payload, blk_rb, def_rc):
        m = Machine(payload)
        m.rating(m.BLK, RUN_BLOCKING, blk_rb)
        m.rating(m.DEF, RUN_COVERAGE, def_rc)
        m.want(m.DEF, 1.0, self.heading)
        return m

    @classmethod
    def _heading(cls):
        m = Machine(cls.retail)
        return heading_away(m)

    def setUp(self):
        if not hasattr(type(self), "heading"):
            type(self).heading = self._heading()

    def test_retail_delay_is_the_same_for_every_lineman(self):
        seen = {self.machine(self.retail, b, d).ticks_to_shed() for b, d in ((0.95, 0.4), (0.7, 0.7), (0.4, 0.95))}
        self.assertEqual(len(seen), 1, seen)
        self.assertIn(seen.pop(), (3, 4))                  # 0.05 s at 60 ticks a second

    def test_patched_delay_follows_the_ratings(self):
        rows = {}
        for b, d in ((0.95, 0.4), (0.85, 0.6), (0.72, 0.64), (0.6, 0.8), (0.4, 0.95)):
            m = self.machine(self.patched, b, d)
            blk, dfn = m.accessor(m.BLK, RUN_BLOCKING), m.accessor(m.DEF, RUN_COVERAGE)
            want = min(max(rb.DELAY_BASE + rb.DELAY_SLOPE * (blk - dfn), rb.DELAY_MIN), rb.DELAY_MAX)
            n = m.ticks_to_shed()
            rows[(b, d)] = n
            self.assertIsNotNone(n)
            self.assertAlmostEqual(n * DT, want, delta=DT * 1.01, msg=(b, d, blk, dfn))
        ordered = [rows[k] for k in ((0.95, 0.4), (0.85, 0.6), (0.72, 0.64), (0.6, 0.8), (0.4, 0.95))]
        self.assertEqual(ordered, sorted(ordered, reverse=True))
        self.assertGreater(ordered[0], ordered[-1] * 4)

    def test_pass_protection_keeps_the_retail_delay(self):
        for payload in (self.retail, self.patched):
            m = self.machine(payload, 0.95, 0.4)
            m.u32(m.BLK + 0x200 + 0x18C, 1)                 # pass-protection state
            self.assertEqual(m.ticks_to_shed(), 1)          # retail pass delay 0: first tick past zero

    def test_registers_and_stack_preserved_through_the_delay_cave(self):
        m = self.machine(self.patched, 0.8, 0.6)
        code = rb.allocation(self.patched)["va"]
        seen = []

        def at_entry(u, _a, _s, _d):
            seen.append(("in", [u.reg_read(r) for r in (x86.UC_X86_REG_EBX, x86.UC_X86_REG_ESI, x86.UC_X86_REG_EDI,
                                                        x86.UC_X86_REG_EBP, x86.UC_X86_REG_ESP)]))

        def after(u, _a, _s, _d):
            seen.append(("out", [u.reg_read(r) for r in (x86.UC_X86_REG_EBX, x86.UC_X86_REG_ESI, x86.UC_X86_REG_EDI,
                                                         x86.UC_X86_REG_EBP, x86.UC_X86_REG_ESP)]))
        m.uc.hook_add(uc.UC_HOOK_CODE, at_entry, begin=0x23317A, end=0x23317A)
        m.uc.hook_add(uc.UC_HOOK_CODE, after, begin=0x233182, end=0x233182)
        m.tick()
        self.assertEqual(seen[0][0], "in")
        self.assertEqual(seen[0][1], seen[1][1])
        self.assertTrue(code)


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class RunLatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, _ = rb.apply(cls.retail)

    def machine(self, payload, seed):
        m = Machine(payload)
        m.rating(m.BLK, RUN_BLOCKING, 0.7)
        m.rating(m.DEF, RUN_COVERAGE, 0.7)
        m.want(m.DEF, 0.0, 0)                           # not turning away: only the run latch can shed
        carrier = m.CARRIER
        m.u32(m.CARRIER + 0x1C, 1)
        m.u32(m.CARRIER + 0x100, 0)                     # a controlled carrier (controller port 0)
        m.uc.mem_write(m.CARRIER + 0x2C, b"\x00")
        m.u32(0x3035000, carrier)
        m.u32(0xE5FC00, 0x3035000)
        m.u32(0xC8F294, 1)                              # the run has declared
        m.seed(seed)
        return m

    def mean_ticks(self, payload, trials=40):
        out = []
        for seed in range(trials):
            n = self.machine(payload, seed).ticks_to_shed(limit=600)
            self.assertIsNotNone(n)
            out.append(n)
        return sum(out) / len(out)

    def test_retail_sheds_almost_at_once_and_patched_holds(self):
        retail, patched = self.mean_ticks(self.retail), self.mean_ticks(self.patched)
        rc = self.machine(self.retail, 0).accessor(Machine.DEF, RUN_COVERAGE)
        self.assertLess(retail, 2.0)                                  # rand < RunCov on every tick
        self.assertAlmostEqual(patched, rb.SHED_DIVISOR / rc, delta=0.45 * rb.SHED_DIVISOR / rc)
        self.assertGreater(patched, 10 * retail)

    def test_latch_off_never_sheds(self):
        for payload in (self.retail, self.patched):
            m = self.machine(payload, 3)
            m.u32(0xC8F294, 0)
            m.u32(0xE5FC00, 0)
            self.assertIsNone(m.ticks_to_shed(limit=120))


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class StartRollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, _ = rb.apply(cls.retail)

    def defender_wins(self, payload, run, rc, blk, lever=0.0, trials=400):
        wins = 0
        m = Machine(payload)
        m.rating(m.BLK, RUN_BLOCKING if run else 16, blk)
        m.rating(m.DEF, RUN_COVERAGE if run else 18, rc)
        m.f32(m.LEVER, lever)
        for seed in range(trials):
            m.seed(seed)
            wins += m.start_roll(run=run) == 0
        return wins / trials

    def test_run_roll_moves_toward_the_blocker_and_keeps_rating_order(self):
        # Unsaturated pairs (with the native +0.25 side term these inputs take, p stays below 1).
        for rc, blk, lever in ((0.64, 0.72, 0.0), (0.64, 0.72, 0.2), (0.85, 0.6, 0.0), (0.7, 0.7, 0.5)):
            retail = self.defender_wins(self.retail, True, rc, blk, lever=lever)
            patched = self.defender_wins(self.patched, True, rc, blk, lever=lever)
            self.assertLess(patched, retail, (rc, blk, lever))
            self.assertAlmostEqual(retail - patched, 0.9 * (0.25 - rb.ROLL_ADD), delta=0.09)
        strong = self.defender_wins(self.patched, True, 0.9, 0.5, lever=0.2)
        weak = self.defender_wins(self.patched, True, 0.5, 0.9, lever=0.2)
        self.assertGreater(strong, weak + 0.3)

    def test_pass_roll_is_byte_for_byte_retail(self):
        for rc, blk in ((0.64, 0.72), (0.9, 0.5)):
            self.assertEqual(self.defender_wins(self.retail, False, rc, blk, lever=0.2, trials=200),
                             self.defender_wins(self.patched, False, rc, blk, lever=0.2, trials=200))


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class B776Tests(unittest.TestCase):
    def test_b776_installs_and_runs(self):
        base = b776_xbe()
        patched, receipt = rb.apply(base)
        self.assertEqual(rb.status(patched), "applied")
        m = Machine(patched)
        m.rating(m.BLK, RUN_BLOCKING, 0.9)
        m.rating(m.DEF, RUN_COVERAGE, 0.5)
        m.want(m.DEF, 1.0, heading_away(Machine(base)))
        n = m.ticks_to_shed()
        self.assertGreaterEqual(n * DT, 0.5)
        self.assertEqual(receipt["file_growth"], 0)


if __name__ == "__main__":
    unittest.main()
