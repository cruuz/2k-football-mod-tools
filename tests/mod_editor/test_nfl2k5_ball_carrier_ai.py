"""CPU ball carriers stay in bounds / QBs slide past the sticks (nfl2k5_ball_carrier_ai): exact bytes, replay, refusal,
presets, late-owner placement, and the real retail sideline filter 0x2E2780 and slide decision 0x2E340C run in Unicorn
on retail and patched executables. No game boot.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent).
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_ball_carrier_ai as bc
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

# The caves as placed at 0x14EC5D0 (where the released v0.6.1 executable puts the allocation).
CAVE_AT_14EC5D0 = (
    "d9442410d81d9c414e00e91164dffe8b430c8338ff75e9817c24200000003f7fdf8b4b188b41303344241878d3d94130d9e1d82d2804"
    "5100d80d28a55000d95c2410ebbce8c754dafe85c074578b570c833aff754f8b0dec02e6008b5718d94238d86128d84c2420d9eedff1"
    "7630d9e0a104f2c8008b0cc5a0f1c80051e81eb6d4fedec98bcfe815b6d4fe588bcfe8cd57dffedec9dff1ddd8760631c0c3ddd8c36a"
    "0158c3")
YARD = 91.44
SIDELINE = 2438.4


class StaticTests(unittest.TestCase):
    def test_cave_bytes_and_sites(self):
        code, labels = bc.code_for(0x14EC5D0)
        self.assertEqual(len(code), bc.CODE_SIZE)
        self.assertEqual(code.hex(), CAVE_AT_14EC5D0 + "cc" * (bc.CODE_SIZE - len(CAVE_AT_14EC5D0) // 2))
        self.assertEqual((labels["retail"], labels["sideline"], labels["slide"]), (0, 15, 68))
        # the retail stub re-runs the displaced test and resumes on the retail fnstsw
        self.assertEqual(code[:10], bc.SIDELINE_HOOK[2])
        self.assertEqual(0x14EC5D0 + 15 + struct.unpack_from("<i", code, 11)[0], 0x2E29F0)
        self.assertEqual(bc.sites(0x14EC5D0), [
            ("sideline", 0x2E29E6, bytes.fromhex("d9442410d81d9c414e00"), bytes.fromhex("e9f49b20019090909090")),
            ("slide", 0x2E340E, bytes.fromhex("e8cde6faff"), bytes.fromhex("e801922001"))])
        self.assertEqual(bc.REQUESTS, (("nfl2k5_ball_carrier_ai", "code", 176, 16),))

    def test_presets_options_and_late_owner_order(self):
        # b778-int2: fa1's star retention and xs1's module loader follow this owner; the loader stays last.
        self.assertEqual(space.LATE_OWNERS[-8:], (bc.OWNER, "nfl2k5_star_retention", "nfl2k5_star_career", "nfl2k5_cpu_money_downs_late", "nfl2k5_cpu_money_downs_late_state", "nfl2k5_draft_clock", "nfl2k5_weekly_progression", "nfl2k5_module_loader"))
        self.assertEqual(space.LATE_OWNERS[-10], "nfl2k5_force_out")  # b778-int2: pi1, ai5, fa1 and xs1 follow
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).cpu_ball_carriers, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["cpu_ball_carriers"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        self.assertIn("cpu_ball_carriers", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_ball_carrier_ai", "CPU ball carriers"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        text = (ROOT / "mod_editor/core/nfl2k5_ball_carrier_ai.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", bc.HELP_TEXT + bc.BUILD_CAPTION)


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = bc.apply(cls.retail)

    def test_site_code_and_receipt(self):
        self.assertEqual(bc.status(self.retail), "retail")
        self.assertEqual(bc.status(self.final), "applied")
        image = XbeImage(self.final)
        code = bc.allocation(self.final)["va"]
        self.assertEqual(image.read(code, bc.CODE_SIZE), bc.code_for(code)[0])
        for _, va, _, new in bc.sites(code):
            self.assertEqual(image.read(va, len(new)), new)
        self.assertEqual(space.status(self.final), "applied")
        self.assertEqual(self.receipt["status"], "applied")

    def test_only_the_hooks_change_in_retail_sections(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        changed = []
        for s in a.sections:
            if s.raw_size:
                x, y = a.read(s.start, s.raw_size), b.read(s.start, s.raw_size)
                changed += [s.start + i for i in range(len(x)) if x[i] != y[i]]
        self.assertEqual(changed, list(range(0x2E29E6, 0x2E29F0)) + list(range(0x2E340F, 0x2E3413)))

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = bc.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = bc.allocation(self.final)["va"]
        for label, (va, content) in {"sideline hook": (0x2E29E6, b"\xe9\x00\x00\x00\x00"),
                                     "nop": (0x2E29EF, b"\xcc"),
                                     "slide hook": (0x2E340F, b"\x00"),
                                     "code": (code + 20, b"\x90"),
                                     "filter": (0x2E28A0, b"\x90"),
                                     "carrier task": (0x2E33F0, b"\x90"),
                                     "slide check": (0x291B00, b"\x90"),
                                     "speed": (0x237C79, b"\x90"),
                                     "constant": (0x510428, b"\x00\x00\x00\x00")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(bc.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                bc.apply(bad)
        retail_bad = repin_edit(self.retail, 0x2E29EF, b"\x90")
        self.assertEqual(bc.status(retail_bad), "foreign")
        with self.assertRaises(ValueError):
            bc.apply(retail_bad)


@unittest.skipIf(uc is None, "unicorn is not installed")
class DecisionTests(unittest.TestCase):
    """The real filter 0x2E2780(player, heading) and the real slide decision from 0x2E340C (0x291AE0 forced true: its
    defender geometry is not under test) on a synthetic carrier. Headings are 16-bit angles, 0 = straight upfield for
    a team moving toward +z, positive = toward +x."""
    HEAP, STACK, RET = 0x3000000, 0x3100000, 0x3200000

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, _ = bc.apply(cls.retail)
        cls.machines = {}

    def machine(self, payload):
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        pages = sorted({va for s in image.sections for va in range(s.start & -4096, (s.start + s.size + 4095) & -4096, 4096)})
        start = prev = None
        for va in pages + [None]:
            if va is not None and prev is not None and va == prev + 4096:
                prev = va
                continue
            if start is not None:
                m.mem_map(start, prev + 4096 - start)
            start = prev = va
        for s in image.sections:
            if s.raw_size:
                m.mem_write(s.start, image.read(s.start, s.raw_size))
        for base in (self.HEAP, self.STACK, self.RET):
            m.mem_map(base, 0x10000)
        return m

    def world(self, m, x, z, *, cpu=True, direction=1.0, urgency=0.0, line_to_gain=0.0, speed=0.7):
        p, ctl, mat, team, t8, t12, tc, p10, state, clock, opp, o8 = (self.HEAP + 0x200 * i for i in range(12))
        put = lambda va, v: m.mem_write(va, struct.pack("<I", v & 0xFFFFFFFF))
        flt = lambda va, v: m.mem_write(va, struct.pack("<f", v))
        put(p + 0xC, ctl); put(ctl, 0xFFFFFFFF if cpu else 0)
        put(p + 0x18, mat); flt(mat + 0x30, x); flt(mat + 0x38, z)
        put(p + 0x38, team); put(p + 0x10, p10); flt(p10 + 0x1B4, speed)
        put(team + 8, t8); put(t8 + 0xC, t12); flt(t12 + 4, direction)
        put(team + 0xC, tc); flt(tc + 0xC4, urgency)
        put(team, opp); put(opp + 8, o8)                                   # scores (both 0: tied) for 0x205F40
        put(0xE602EC, state); put(state + 4, 1); flt(state + 0x28, line_to_gain)
        put(0xE6028C, clock); flt(clock + 0x10, 900.0); put(0xE60280, team)
        return p, ctl

    def heading(self, payload, x, h, **kw):
        m = self.machine(payload)
        p, _ = self.world(m, x, 0.0, **kw)
        esp = self.STACK + 0x8000
        m.mem_write(esp, struct.pack("<III", self.RET, p, h & 0xFFFF))
        m.reg_write(x86.UC_X86_REG_ESP, esp)
        m.emu_start(0x2E2780, self.RET, count=100000)
        out = m.reg_read(x86.UC_X86_REG_EAX) & 0xFFFF
        return round((out - 0x10000 if out >= 0x8000 else out) * 360 / 65536, 1)

    def slide(self, payload, *, short_yd, threat_yd, cpu=True, direction=1.0, speed=0.7, threat_speed=0.7):
        m = self.machine(payload)
        p, ctl = self.world(m, 0.0, 0.0, cpu=cpu, direction=direction, line_to_gain=direction * short_yd * YARD,
                            speed=speed)
        threat, tmat, t10 = self.HEAP + 0x2000, self.HEAP + 0x2200, self.HEAP + 0x2400
        put = lambda va, v: m.mem_write(va, struct.pack("<I", v & 0xFFFFFFFF))
        put(0xC8F204, 3); put(0xC8F1A0 + 24, threat)
        put(threat + 0x18, tmat); m.mem_write(tmat + 0x30, struct.pack("<ff", 0.0, 0.0))
        m.mem_write(tmat + 0x38, struct.pack("<f", direction * threat_yd * YARD))
        put(threat + 0x10, t10); m.mem_write(t10 + 0x1B4, struct.pack("<f", threat_speed))
        put(ctl + 0x1C, 0)
        esp = self.STACK + 0x8000
        m.mem_write(esp + 0x1C, struct.pack("<f", direction))
        m.reg_write(x86.UC_X86_REG_ESP, esp)
        m.reg_write(x86.UC_X86_REG_EDI, p)

        def hook(mu, address, size, _):
            if address == 0x291AE0:
                sp = mu.reg_read(x86.UC_X86_REG_ESP)
                mu.reg_write(x86.UC_X86_REG_EIP, struct.unpack("<I", mu.mem_read(sp, 4))[0])
                mu.reg_write(x86.UC_X86_REG_ESP, sp + 4)
                mu.reg_write(x86.UC_X86_REG_EAX, 1)
            elif address in (0x2E3421, 0x2E3458):
                mu.emu_stop()
        m.hook_add(uc.UC_HOOK_CODE, hook)
        m.emu_start(0x2E340C, 0, count=100000)
        return struct.unpack("<I", m.mem_read(ctl + 0x1C, 4))[0] == 0x99

    def test_retail_lets_a_carrier_drift_out_in_the_last_half_yard(self):
        # the reported behaviour: the weight grows again past the half-yard line, so an outward heading survives
        for yd, want in ((1.0, 11.3), (0.5, 0.0), (0.0, 11.3), (-0.5, 21.8)):
            self.assertEqual(self.heading(self.retail, SIDELINE - yd * YARD, 0x2000), want, yd)

    def test_patched_cpu_carrier_stays_in_bounds(self):
        for yd, want in ((6, 45.0), (4, 45.0), (3, 33.7), (2, 18.4), (1.5, 9.5), (1, 0.0), (0.5, 0.0), (0, 0.0), (-0.5, 0.0)):
            self.assertEqual(self.heading(self.final, SIDELINE - yd * YARD, 0x2000), want, yd)
        self.assertEqual(self.heading(self.final, -(SIDELINE - 0.5 * YARD), 0xE000), 0.0)   # the other sideline
        for yd in (6, 2, 1, 0.5):                                                               # heading inward: retail
            x = SIDELINE - yd * YARD
            self.assertEqual(self.heading(self.final, x, 0xE000), self.heading(self.retail, x, 0xE000), yd)
        self.assertEqual(self.heading(self.final, 0.0, 0x38E3), 80.0)                          # mid-field: untouched

    def test_humans_and_late_clock_urgency_keep_retail(self):
        for yd in (2, 1, 0, -0.5):
            x = SIDELINE - yd * YARD
            self.assertEqual(self.heading(self.final, x, 0x2000, cpu=False), self.heading(self.retail, x, 0x2000, cpu=False))
            self.assertEqual(self.heading(self.final, x, 0x2000, urgency=0.8), self.heading(self.retail, x, 0x2000, urgency=0.8))
        self.assertEqual(self.heading(self.final, SIDELINE - YARD, 0x2000, urgency=0.5), 0.0)

    def test_slide_short_of_the_sticks_needs_the_hit_first(self):
        cases = {(0.5, 1): False, (1, 2): False, (3, 5): False, (5, 8): False,   # he can reach the sticks first: run
                 (1, 1): True, (3, 2): True, (3, 3): True, (5, 5): True}          # the defender gets there first: slide
        for (short, threat), want in cases.items():
            self.assertTrue(self.slide(self.retail, short_yd=short, threat_yd=threat), (short, threat))
            self.assertIs(self.slide(self.final, short_yd=short, threat_yd=threat), want, (short, threat))
        for direction in (1.0, -1.0):
            self.assertIs(self.slide(self.final, short_yd=-1, threat_yd=6, direction=direction), True)   # past the sticks
            self.assertIs(self.slide(self.final, short_yd=0, threat_yd=6, direction=direction), True)    # at the sticks
            self.assertIs(self.slide(self.final, short_yd=3, threat_yd=6, direction=direction), False)
        self.assertIs(self.slide(self.final, short_yd=3, threat_yd=6, cpu=False), True)               # human: retail
        self.assertIs(self.slide(self.final, short_yd=3, threat_yd=3.5, threat_speed=1.0, speed=0.2), True)


if __name__ == "__main__":
    unittest.main()
