"""Bounded native proofs for CPU quarterbacks throw on time and check down. No game boot, rendered play or thrown ball.

Executed from the pinned USA retail default.xbe (skipped when absent), with and without the owner:
* the real target-point scorer 0x19A7E0 (the openness function 0x199F40, the receiving composite curve 0x50C4CC and the
  field terms 0x199CE0 with the owner's hook). Declared input seams: the ball-time helper 0x1995A0 returns 0.65 s and
  the receiver composite getter 0x246A80 returns 0.70 (curve value 0); positions, defenders, down and distance, the
  play clock, the pocket pressure and the first-read-cycle flag are supplied;
* the real QB tick's two pump-fake paths (0x19BF8C and 0x19C187) to their return, the native RNG 0x48B50 supplying the
  draws, and the real throw press 0x19BAE0 up to its holdoff gate;
* the real read advance 0x199100 with Pass Read Coverage supplied (the rating getter 0x17B010 is an input).
Every number is an instruction result for the stated inputs, not a played game.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_cpu_passer_iq as passer
from mod_editor.core import nfl2k5_cpu_qb_reads as reads
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.nfl2k5_cpu_ai_native import OpenMachine, YD, bits, seed_rng, uc, x86

LOS = 1200.0
THRESHOLDS_RETAIL = (1.2, 1.1, 1.0, 0.975)    # 0x50C394 at Pass Read Coverage 0.3 / 0.5 / 0.8 / 1.0
THRESHOLDS_TIERS = (0.62, 0.70, 0.92, 1.00)   # the CPU QB skill tiers (v0.8)


class ScoreMachine(OpenMachine):
    """One receiver row of the CPU QB's read grid, scored by the real 0x19A7E0 (declared seams above)."""
    ROW, POINT = 0, 1
    CLOCK, GCLOCK, BOX, STUBS = 0x3218000, 0x3218100, 0x3218200, 0x3218400

    def __init__(self, payload, *, direction=1):
        super().__init__(payload, direction=direction)
        self.owner = passer.allocations(payload) if passer.status(payload) == "applied" else None
        # seams: ball time (ret 4) and the receiver composite (ret 4)
        self.uc.mem_write(self.STUBS, struct.pack("<ff", 0.65, 0.70))
        self.uc.mem_write(self.STUBS + 0x10, b"\xd9\x05" + struct.pack("<I", self.STUBS) + b"\xc2\x04\x00")
        self.uc.mem_write(self.STUBS + 0x20, b"\xd9\x05" + struct.pack("<I", self.STUBS + 4) + b"\xc2\x04\x00")
        self.uc.hook_add(uc.UC_HOOK_CODE, self._seam, begin=0x1995A0, end=0x1995A0)
        self.uc.hook_add(uc.UC_HOOK_CODE, self._seam, begin=0x246A80, end=0x246A80)
        self.u32(0xE6028C, self.GCLOCK); self.f32(self.GCLOCK + 0x10, 300.0); self.u32(self.GCLOCK + 0x18, 0)
        self.u32(0xE602C4, 1); self.f32(0xE602B0, 420.0)
        self.u32(0xE6029C, self.CLOCK)
        self.u32(0xBE47F8, 0)
        self.u32(self.DEF + 8, self.DEF + 0x200)
        self.u32(self.OFFMETA + 0x10, self.BOX)
        self.uc.mem_write(self.BOX, struct.pack("<4f", 1e7, 1e7, 1e7 + 1, 1e7 + 1))
        self.situation()

    def _seam(self, u, address, _size, _data):
        u.reg_write(x86.UC_X86_REG_EIP, self.STUBS + (0x10 if address == 0x1995A0 else 0x20))

    def situation(self, *, down=1, to_go=10, t=1.0, pressure=0.0, cycled=0, human=False):
        d = self.direction
        self.f32(self.GAME + 0x18, LOS)
        self.f32(self.GAME + 0x28, LOS + to_go * YD * d)
        self.u32(self.GAME + 4, down)
        self.f32(self.CLOCK + 0x10, t)
        self.f32(0xBE47C0, pressure)
        self.u32(0xBE47FC, cycled)
        self.u32(self.QB + 0x100, 0 if human else -1)
        for off, value in ((0x30, 0.0), (0x38, LOS - 5 * YD * d)):
            self.f32(self.QB + 0x400 + off, value)

    def score(self, point, **situation):
        """Stored score of the receiver's point (x yd from the middle, depth yd past the line of scrimmage)."""
        self.situation(**situation)
        d = self.direction
        row = 0xBE4820 + self.ROW * 0xA0
        record = 0xBE4840 + self.ROW * 0xA0 + self.POINT * 0x20
        self.u32(row, self.RB)
        self.u32(row + 0xC, 0)                                   # route kind: no sideline weight
        self.uc.mem_write(record, struct.pack("<5f", point[0] * YD, 0, LOS + point[1] * YD * d, 1, 1.0))
        self.f32(record + 0x14, -99.0)
        self.uc.mem_write(self.BALL + 0x100, struct.pack("<4f", 0, 100, LOS - 5 * YD * d, 1))   # the ball at the QB
        seed_rng(self, 1)
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.run(0x19A7E0, args=(bits(0.75),), eax=self.ROW, edx=self.POINT, ecx=self.QB, count=400000)
        return self.readf(record + 0x14)

    def state(self):
        if self.owner is None:
            return None
        raw = bytes(self.uc.mem_read(self.owner["data"]["va"], 12))
        last, seen, cycle = struct.unpack("<fIf", raw)
        return dict(last=last, seen=seen, cycle=cycle)


def open_back(m):
    m.place(m.RB, 3.0, -1.0, 0.0, 0.0)
    m.defender(role=14, x=15, depth=8, man=0)                   # the fixtures' "wide open": no man defender near


def zone_window(m):
    m.place(m.RB, 3.0, -1.0, 0.0, 0.0)
    m.defender(role=13, x=3.0, depth=-1.0, spot=(3.0, -1.0))   # a zone defender standing on the spot


BACK_5YD = (3.0, -1.0)      # 5 yd from the QB (x 3, 4 yd downfield of him), 1 yd behind the line of scrimmage


def factor_at(t, *, start=2.0):
    return max(passer.FLOOR, min(1.0, 1.0 - passer.FADE_RATE * (t - start)))


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class CheckdownScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, _ = passer.apply(cls.retail)
        cls.rows = {}

    def machine(self, payload, setup=open_back, direction=1):
        m = ScoreMachine(payload, direction=direction)
        setup(m)
        return m

    def test_open_back_scores_like_retail_early_and_clears_every_threshold_late_or_pressured(self):
        retail = self.machine(self.retail).score(BACK_5YD, t=1.0)
        # the research's arithmetic: defenders about 1.45, short-throw term about -0.45, depth about -0.18
        self.assertAlmostEqual(retail, 0.82, delta=0.03)
        self.assertTrue(all(retail < th for th in THRESHOLDS_RETAIL))
        self.assertTrue(all(retail < th for th in THRESHOLDS_TIERS[2:]))      # average to elite starters
        for t in (0.2, 1.0, 1.5, 1.99):
            m = self.machine(self.patched)
            self.assertEqual(struct.pack("<f", m.score(BACK_5YD, t=t)), struct.pack("<f", retail), t)
        m = self.machine(self.patched)
        late = m.score(BACK_5YD, t=3.0)
        pressured = self.machine(self.patched).score(BACK_5YD, t=1.0, pressure=0.7)
        self.assertGreater(late, 0.85)
        self.assertGreater(pressured, 0.85)
        self.assertAlmostEqual(late, pressured, places=5)
        self.assertGreater(late, max(THRESHOLDS_RETAIL[2:] + THRESHOLDS_TIERS))   # even an elite reader takes him
        # the retail short-throw term at this point, recovered from the two scores: term x (1 - floor)
        term = (retail - late) / (1 - passer.FLOOR)
        self.assertAlmostEqual(term, -0.45, delta=0.03)
        for t in (2.25, 2.5, 2.75, 3.5, 6.0):
            got = self.machine(self.patched).score(BACK_5YD, t=t)
            self.assertAlmostEqual(got, retail - term * (1 - factor_at(t)), places=4, msg=t)

    def test_targets_15_yards_out_and_human_passers_are_unchanged(self):
        for point in ((0.0, 12.0), (8.0, 10.0), (-6.0, 20.0)):         # 17, 17 and 25.7 yd from the QB
            for situation in (dict(t=1.0), dict(t=3.5), dict(t=1.0, pressure=0.95)):
                a = self.machine(self.retail).score(point, **situation)
                b = self.machine(self.patched).score(point, **situation)
                self.assertEqual(struct.pack("<f", a), struct.pack("<f", b), (point, situation))
        for situation in (dict(t=3.5), dict(t=1.0, pressure=0.95)):
            a = self.machine(self.retail).score(BACK_5YD, human=True, **situation)
            b = self.machine(self.patched).score(BACK_5YD, human=True, **situation)
            self.assertEqual(struct.pack("<f", a), struct.pack("<f", b), situation)

    def test_a_covered_back_stays_below_the_starter_thresholds_with_the_zone_option(self):
        composed, _ = reads.apply(self.retail, zone_windows=True, tiers=True)
        composed, _ = passer.apply(composed)
        for payload in (composed,):
            covered = self.machine(payload, zone_window).score(BACK_5YD, t=4.0)
            self.assertLess(covered, THRESHOLDS_TIERS[2])                # an average or better reader does not force it
            open_late = self.machine(payload).score(BACK_5YD, t=4.0)
            self.assertGreater(open_late, THRESHOLDS_TIERS[3])

    def test_both_field_directions_agree(self):
        for t in (1.0, 2.5, 3.0):
            a = self.machine(self.patched, direction=1).score(BACK_5YD, t=t)
            b = self.machine(self.patched, direction=-1).score(BACK_5YD, t=t)
            self.assertAlmostEqual(a, b, places=4, msg=t)

    def test_first_read_cycle_starts_the_fade_and_a_new_play_resets_it(self):
        m = self.machine(self.patched)
        retail = self.machine(self.retail).score(BACK_5YD, t=1.0)
        term = (retail - self.machine(self.patched).score(BACK_5YD, t=3.0)) / (1 - passer.FLOOR)
        self.assertEqual(m.score(BACK_5YD, t=0.6), retail)
        self.assertEqual(m.state()["seen"], 0)
        self.assertEqual(m.score(BACK_5YD, t=1.3, cycled=1), retail)       # the read wrapped to the first row at 1.3 s
        self.assertEqual((m.state()["seen"], m.state()["cycle"]), (1, struct.unpack("<f", struct.pack("<f", 1.3))[0]))
        later = m.score(BACK_5YD, t=1.8, cycled=0)                         # the native flag is clear again
        self.assertAlmostEqual(later, retail - term * (1 - factor_at(1.8, start=1.3)), places=4)
        self.assertGreater(later, retail)
        self.assertEqual(m.state()["seen"], 1)
        # the next play: the clock went back
        self.assertEqual(m.score(BACK_5YD, t=0.1), retail)
        self.assertEqual(m.state()["seen"], 0)
        self.assertEqual(m.score(BACK_5YD, t=1.8), retail)                # no cycle yet, before 2.0 s
        # a first cycle later than 2.0 s does not delay the fade
        m.score(BACK_5YD, t=2.4, cycled=1)
        self.assertAlmostEqual(m.score(BACK_5YD, t=2.5), retail - term * (1 - factor_at(2.5)), places=4)


class TickMachine(OpenMachine):
    """The real QB tick from a pump-fake decision to its return, and the throw press up to its holdoff gate."""
    CLOCK, TASK = 0x3218000, 0x3218400

    def __init__(self, payload):
        super().__init__(payload)
        self.u32(0xE6029C, self.CLOCK)
        self.draws = []
        self.uc.hook_add(uc.UC_HOOK_CODE, self._rng, begin=0x48B50, end=0x48B50)
        self.queue = []

    def _rng(self, u, _address, _size, _data):
        """Input seam: the next native random draw (EAX) when one is queued; otherwise the native generator runs."""
        if not self.queue:
            return
        value = self.queue.pop(0)
        self.draws.append(value)
        esp = u.reg_read(x86.UC_X86_REG_ESP)
        ret = struct.unpack("<I", u.mem_read(esp, 4))[0]
        u.reg_write(x86.UC_X86_REG_EAX, value)
        u.reg_write(x86.UC_X86_REG_ESP, esp + 4)
        u.reg_write(x86.UC_X86_REG_EIP, ret)

    def frame(self, *, timer, button=1):
        """A QB-tick stack frame: locals 0x38 bytes, saved EDI/ESI/EBX, return to STOP."""
        base = self.STACK - 0x48
        self.uc.mem_write(base, bytes(0x48))
        self.u32(base + 0x44, self.STOP)                                    # return address after the 0x38 locals + 3 pushes
        self.f32(base + 0x0C, timer)
        self.u32(base + 0x18, self.RB)                                      # committed target
        self.u32(base + 0x34, button)
        return base

    def pump(self, entry, *, t, timer, draw=None, button=1):
        self.f32(self.CLOCK + 0x10, t)
        self.u32(0xBE47EC, 0)
        self.u32(self.QB + 0x100 + 0x1C, 0)                                 # controller action word
        self.u32(self.QB + 0x200 + 0x28, 0)                                 # [QB+0x10]+0x28 bit 0 clear
        if draw is not None:
            self.queue = [draw]
        base = self.frame(timer=timer, button=button)
        self.stop_at = None
        self.uc.reg_write(x86.UC_X86_REG_ESP, base)
        values = dict(EBX=button, EDI=self.QB, ESI=self.RB, EAX=0, ECX=0, EDX=0, EBP=0x6789)
        for name, value in values.items():
            self.uc.reg_write(getattr(x86, "UC_X86_REG_" + name), value)
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.uc.emu_start(entry, self.STOP, timeout=2_000_000, count=20000)
        action = self.get(self.QB + 0x100 + 0x1C)
        return action, self.readf(0xBE47EC)

    def press_gate(self, *, t, holdoff):
        """The real throw press 0x19BAE0 (ECX = QB): 'open' when it gets past the holdoff and set-feet gates."""
        self.f32(self.CLOCK + 0x10, t)
        self.f32(0xBE47EC, holdoff)
        self.u32(self.QB + 0x600 + 0x310, self.TASK)
        self.u32(self.TASK + 0x40, self.RB)
        self.u32(self.QB + 0x300, 0)                                        # [[QB+0x14]] & 0x38 == 0: feet set
        at = self.run(0x19BAE0, ecx=self.QB, stop_at=0x19BB21, count=2000)
        return "open" if at == 0x19BB21 else "blocked"


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class PumpFakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, _ = passer.apply(cls.retail)

    def test_both_pump_paths_hold_the_throw_for_0_6_seconds(self):
        # path 1 (0x19BF8C): a committed target with 1.0-1.5 s on the release timer; path 2 (0x19C187): the roll
        for payload, hold in ((self.retail, 1.5), (self.patched, 0.6)):
            m = TickMachine(payload)
            action, holdoff = m.pump(0x19BF8C, t=1.25, timer=1.2, button=1)
            self.assertEqual(action, 0x46 + 3)
            self.assertAlmostEqual(holdoff, 1.25 + hold, places=5)
            action, holdoff = m.pump(0x19C187, t=1.75, timer=1.6, draw=0, button=2)
            self.assertEqual(action, 0x46)
            self.assertAlmostEqual(holdoff, 1.75 + hold, places=5)

    def test_pump_roll_is_one_in_sixty(self):
        counts = {}
        for name, payload in (("retail", self.retail), ("patched", self.patched)):
            m = TickMachine(payload)
            pumped = []
            for draw in range(180):
                action, _ = m.pump(0x19C187, t=1.75, timer=1.6, draw=draw, button=1)
                if action:
                    pumped.append(draw)
            counts[name] = pumped
        self.assertEqual(counts["retail"], list(range(0, 180, 20)))
        self.assertEqual(counts["patched"], [0, 60, 120])

    def test_the_throw_press_opens_0_6_seconds_after_a_pump(self):
        for payload, expected in ((self.retail, ("blocked", "blocked", "open")), (self.patched, ("blocked", "open", "open"))):
            m = TickMachine(payload)
            _action, holdoff = m.pump(0x19BF8C, t=2.0, timer=1.2)
            got = tuple(m.press_gate(t=t, holdoff=holdoff) for t in (2.5, 2.65, 3.55))
            self.assertEqual(got, expected)


class AdvanceMachine(OpenMachine):
    """The real read advance 0x199100 (ECX = QB); Pass Read Coverage is an input (0x17B010 stubbed, ret 4)."""
    CLOCK, RATING = 0x3218000, 0x3218800

    def __init__(self, payload):
        super().__init__(payload)
        self.u32(0xE6029C, self.CLOCK)
        self.uc.mem_write(self.RATING, b"\xd9\x05" + struct.pack("<I", self.RATING + 0x10) + b"\xc2\x04\x00")
        self.uc.hook_add(uc.UC_HOOK_CODE, lambda u, a, s, d: u.reg_write(x86.UC_X86_REG_EIP, self.RATING),
                         begin=0x17B010, end=0x17B010)

    def dwell(self, prc, rows=4):
        self.f32(self.RATING + 0x10, prc)
        self.u32(0xBE480C, rows)
        for row in range(5):
            self.u32(0xBE4820 + row * 0xA0 + 0x10, 1 if row < rows else 0)
        self.u32(0xBE4810, 0)
        self.f32(0xBE47C8, 0.5)
        self.f32(self.CLOCK + 0x10, 0.5)
        self.run(0x199100, ecx=self.QB, count=4000)
        return self.readf(0xBE47C8) - 0.5, self.get(0xBE4810)

    def cycle(self, prc, rows):
        """Advance at each switch time until the read wraps; the clock when 0xBE47FC goes up."""
        self.f32(self.RATING + 0x10, prc)
        self.u32(0xBE480C, rows)
        for row in range(5):
            self.u32(0xBE4820 + row * 0xA0 + 0x10, 1 if row < rows else 0)
        self.u32(0xBE4810, 0); self.u32(0xBE47FC, 0); self.f32(0xBE47C8, 0.5)
        for _ in range(12):
            t = self.readf(0xBE47C8)
            self.f32(self.CLOCK + 0x10, t)
            self.run(0x199100, ecx=self.QB, count=4000)
            if self.get(0xBE47FC):
                return t
        return None


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class ReadDwellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, _ = passer.apply(cls.retail)

    def test_native_read_advance_uses_the_faster_dwell(self):
        expected = {0.0: (2.0, 1.0), 0.3: (1.0, 0.8), 0.5: (0.5, 0.6), 0.7: (0.45, 0.475), 0.9: (0.4, 0.35), 1.0: (0.2, 0.25)}
        old, new = AdvanceMachine(self.retail), AdvanceMachine(self.patched)
        for prc, (a, b) in expected.items():
            got_a, row_a = old.dwell(prc)
            got_b, row_b = new.dwell(prc)
            self.assertAlmostEqual(got_a, a, places=4, msg=prc)
            self.assertAlmostEqual(got_b, b, places=4, msg=prc)
            self.assertEqual((row_a, row_b), (1, 1))
        # a weak reader (0.4) cycles four reads in 0.5 + 3 x 0.7 = 2.6 s instead of 0.5 + 3 x 0.75 = 2.75 s; an
        # average one (0.75) in 0.5 + 3 x 0.444 = 1.83 s (retail 0.5 + 3 x 0.4375 = 1.81 s)
        self.assertAlmostEqual(new.cycle(0.4, 4), 0.5 + 3 * 0.7, places=3)
        self.assertAlmostEqual(old.cycle(0.4, 4), 0.5 + 3 * 0.75, places=3)
        self.assertAlmostEqual(new.cycle(0.0, 3), 0.5 + 2 * 1.0, places=3)
        self.assertAlmostEqual(old.cycle(0.0, 3), 0.5 + 2 * 2.0, places=3)


if __name__ == "__main__":
    unittest.main()
