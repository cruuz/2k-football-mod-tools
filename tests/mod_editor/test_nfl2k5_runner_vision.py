"""CPU ball carrier vision (nfl2k5_runner_vision) and the wide sideline taper of nfl2k5_ball_carrier_ai: exact sites,
replay, refusal, composition with the ball-carrier owner, Studio wiring, and the real retail push routine 0x2E2260,
its relocated owner copy and the real sideline filter 0x2E2780 run in Unicorn on synthetic players. No game boot.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent).
"""
from pathlib import Path
import math
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_ball_carrier_ai as bc
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_runner_vision as rv
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

YARD = 91.44
SIDELINE = 2438.4


def built():
    """retail -> ball carriers (wide taper) -> runner vision, through the real writers (cached per process)."""
    if not hasattr(built, "cache"):
        retail = retail_xbe()
        wide, _ = bc.apply(retail, wide_sideline=True)
        final, receipt = rv.apply(wide)
        built.cache = retail, wide, final, receipt
    return built.cache


class StaticTests(unittest.TestCase):
    def test_request_sites_and_layout(self):
        self.assertEqual(rv.REQUESTS, (("nfl2k5_runner_vision", "code", rv.CODE_SIZE, 16),))
        self.assertEqual(rv.sites(0x14DA0B0), [
            ("push_call", 0x2E3072, bytes.fromhex("e8e9f1ffff"), b"\xe8" + struct.pack("<i", 0x14DA0B0 - 0x2E3077))])
        self.assertEqual(rv.PUSH_SIZE, 0x2E2780 - 0x2E2260)
        for off, before in rv.LOOKAHEAD_SITES:
            self.assertEqual(len(before), len(rv.LOOKAHEAD_EDIT))
        for off, before, after in rv.REFERENCE_SITES:
            self.assertEqual(len(before), len(after))
        self.assertEqual(rv.WEIGHT_SITE, (0x2E2530 - 0x2E2260, 0x2E2572 - 0x2E2260))

    def test_wiring_presets_and_late_owner_order(self):
        # b780-int: several wave owners append after the b779 tail; each must come after every owner v0.8 carries
        self.assertEqual(space.LATE_OWNERS.count(rv.OWNER), 1)
        self.assertGreater(space.LATE_OWNERS.index(rv.OWNER), space.LATE_OWNERS.index("nfl2k5_sim_realism_state"))
        self.assertLess(space.LATE_OWNERS.index(bc.OWNER), space.LATE_OWNERS.index(rv.OWNER))
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).cpu_runner_vision, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["cpu_runner_vision"], False, name)               # off until its emulator gate passes
            self.assertFalse(preset["cpu_runner_vision"] and not preset["cpu_ball_carriers"], name)
        self.assertIn("cpu_runner_vision", settings.FEATURE_KEYS)
        self.assertIn((rv.OWNER, "CPU ball carrier vision"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        text = (ROOT / "mod_editor/core/nfl2k5_runner_vision.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", rv.HELP_TEXT + rv.BUILD_CAPTION)

    def test_vision_needs_ball_carriers(self):
        with self.assertRaisesRegex(ValueError, "needs \"CPU ball carriers stay in bounds\""):
            mod_build.build(mod_build.BuildPlan(Path("missing-source.iso"), Path("target.iso"),
                                                cpu_runner_vision=True, cpu_ball_carriers=False))


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail, cls.wide, cls.final, cls.receipt = built()

    def test_status_code_and_receipt(self):
        self.assertEqual(rv.status(self.retail), "retail")
        self.assertEqual(rv.status(self.wide), "retail")
        self.assertEqual(rv.status(self.final), "applied")
        self.assertEqual(bc.status(self.final), "applied")                       # tolerates the vision hook
        self.assertIs(bc.wide_sideline(self.final), True)
        image = XbeImage(self.final)
        va = rv.allocation(self.final)["va"]
        self.assertEqual(image.read(va, rv.CODE_SIZE), rv.code_for(va, image.read(rv.PUSH_VA, rv.PUSH_SIZE))[0])
        self.assertEqual(self.receipt["status"], "applied")
        self.assertEqual(rv.neighbor_edits(self.final), [(0x2E3072, bytes.fromhex("e8e9f1ffff"))])
        self.assertEqual(rv.neighbor_edits(self.wide), [])

    def test_only_the_call_changes_in_retail_sections(self):
        a, b = XbeImage(self.wide), XbeImage(self.final)
        changed = []
        for s in a.sections:
            if s.raw_size and s.start < 0x1000000:
                x, y = a.read(s.start, s.raw_size), b.read(s.start, s.raw_size)
                changed += [s.start + i for i in range(len(x)) if x[i] != y[i]]
        self.assertEqual(changed, [0x2E3073, 0x2E3074, 0x2E3075, 0x2E3076])
        self.assertEqual(XbeImage(self.final).read(rv.PUSH_VA, rv.PUSH_SIZE), XbeImage(self.retail).read(rv.PUSH_VA, rv.PUSH_SIZE))

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = rv.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        va = rv.allocation(self.final)["va"]
        for label, (at, content) in {"hook": (0x2E3073, b"\x00"),
                                     "code": (va + 0x100, b"\x90"),
                                     "constant": (va, b"\x00\x00\x00\x00"),
                                     "push routine": (0x2E2400, b"\x90"),
                                     "context": (0x2E3090, b"\x90"),
                                     "tables": (0x50C7D0, b"\x00\x00\x00\x00"),
                                     "retail look-ahead": (0x4E41A0, b"\x00\x00\x00\x00")}.items():
            bad = repin_edit(self.final, at, content)
            self.assertEqual(rv.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                rv.apply(bad)
        # a foreign byte in the vision hook makes the ball-carrier owner refuse too (its task guard is not relaxed)
        self.assertEqual(bc.status(repin_edit(self.final, 0x2E3073, b"\x00")), "foreign")
        retail_bad = repin_edit(self.retail, 0x2E3073, b"\x00")
        self.assertEqual(rv.status(retail_bad), "foreign")
        with self.assertRaises(ValueError):
            rv.apply(retail_bad)

    def test_ball_carrier_tapers_are_exclusive(self):
        standard, _ = bc.apply(self.retail)
        self.assertIs(bc.wide_sideline(standard), False)
        self.assertEqual(bc.apply(standard)[1]["status"], "already_applied")
        with self.assertRaises(ValueError):
            bc.apply(standard, wide_sideline=True)
        with self.assertRaises(ValueError):
            bc.apply(self.wide)
        va = bc.allocation(self.wide)["va"]
        code = XbeImage(self.wide).read(va, bc.CODE_SIZE)
        self.assertEqual(code[:bc.WIDE_BAND_OFFSET], bc.code_for(va)[0][:bc.WIDE_BAND_OFFSET].replace(
            struct.pack("<I", bc.C_BAND), struct.pack("<I", va + bc.WIDE_BAND_OFFSET)))
        self.assertAlmostEqual(struct.unpack_from("<f", code, bc.WIDE_BAND_OFFSET)[0], 1 / (8 * YARD))


@unittest.skipIf(uc is None, "unicorn is not installed")
class PushTests(unittest.TestCase):
    """The real push 0x2E2260 vs the owner entry (wrapper -> copy) on synthetic players. 0x76CB0 (blocker engaged
    with that defender) and 0x23ABA0 (a teammate's task test) return 0; everything else executes."""
    HEAP, STACK, RET = 0x3000000, 0x3400000, 0x3500000
    RESULT = RET + 0x100

    @classmethod
    def setUpClass(cls):
        cls.retail, cls.wide, cls.final, _ = built()
        cls.va = rv.allocation(cls.final)["va"]
        cls.entry = cls.va + rv.C_ENTRY
        cls.push_bytes = XbeImage(cls.final).read(rv.PUSH_VA, rv.PUSH_SIZE)
        cls.m = cls.machine(cls.final)

    @classmethod
    def machine(cls, payload):
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
        for base in (cls.HEAP, cls.STACK, cls.RET):
            m.mem_map(base, 0x40000)
        m.mem_write(cls.RET, bytes.fromhex("d91d") + struct.pack("<I", cls.RESULT) + b"\xf4")   # fstp [RESULT]; hlt
        m.reg_write(x86.UC_X86_REG_FPCW, 0x37F)

        def stub(mu, address, size, _):
            sp = mu.reg_read(x86.UC_X86_REG_ESP)
            ret = struct.unpack("<I", mu.mem_read(sp, 4))[0]
            mu.reg_write(x86.UC_X86_REG_EAX, 0)
            mu.reg_write(x86.UC_X86_REG_ESP, sp + 4 + (8 if address == 0x76CB0 else 0))
            mu.reg_write(x86.UC_X86_REG_EIP, ret)
        for address in (0x76CB0, 0x23ABA0):
            m.hook_add(uc.UC_HOOK_CODE, stub, begin=address, end=address)
        return m

    def world(self, carrier, defenders=(), mates=(), *, direction=1.0, cpu=True, urgency=0.0):
        """carrier / defenders / mates: (x, z, vx, vz[, class[, engaged index]]) in yards and yd/s."""
        m = self.m
        m.mem_write(self.HEAP, b"\0" * 0x40000)
        alloc = [self.HEAP]

        def new(size=0x200):
            va = alloc[0]
            alloc[0] += size
            return va
        put = lambda va, v: m.mem_write(va, struct.pack("<I", v & 0xFFFFFFFF))
        flt = lambda va, v: m.mem_write(va, struct.pack("<f", v))

        def team(sign):
            t, t8, t12, tc = new(), new(), new(), new()
            put(t + 8, t8); put(t8 + 0xC, t12); flt(t12 + 4, sign * direction)
            put(t + 0xC, tc); flt(tc + 0xC4, urgency)
            return t
        offense, defense = team(1.0), team(-1.0)

        def player(row, side, control):
            x, z, vx, vz = (v * YARD for v in row[:4])
            cls = row[4] if len(row) > 4 else 1
            p, ctl, L, desc, anim, q, inner, T, A, task = (new() for _ in range(10))
            put(p + 0xC, ctl); put(ctl, control)
            flt(p + 8, 1.0); put(p + 0x10, L); put(p + 0x14, anim); put(p + 0x18, T); put(p + 0x20, A)
            put(p + 0x38, side); put(p + 0x48, 0)
            put(L + 4, desc); put(desc, (cls << 24) | 1)
            put(anim + 0x74, q); put(q, inner); flt(q + 8, 0.4); flt(inner + 0x18, 1.0)
            for off, v in ((0x30, x), (0x38, z), (0x40, vx), (0x48, vz), (0x3C, 1.0)):
                flt(T + off, v)
            put(A + 0x310, task)
            return p, L, row
        P = player(carrier, offense, 0xFFFFFFFF if cpu else 0)
        others = [player(r, defense, 0xFFFFFFFF) for r in defenders] + [player(r, offense, 0xFFFFFFFF) for r in mates]
        everyone = [P] + others
        for (p, L, row) in everyone:                                   # engaged blockers: L+0xD0 -> the man held
            if len(row) > 5:
                put(L + 0xD0, others[row[5]][0])
        for (a, _, _), (b, _, _) in zip(everyone, everyone[1:]):
            put(a + 0x30, b)
        put(everyone[-1][0] + 0x30, 0)
        put(0xE60268, P[0]); put(0xE60280, offense); put(0xE60284, defense)
        return P[0]

    def push(self, entry, p):
        esp = self.STACK + 0x30000
        self.m.mem_write(esp, struct.pack("<II", self.RET, p))
        self.m.reg_write(x86.UC_X86_REG_ESP, esp)
        self.m.emu_start(entry, self.RET + 6, count=500000)
        return struct.unpack("<f", self.m.mem_read(self.RESULT, 4))[0]

    def both(self, *args, **kw):
        p = self.world(*args, **kw)
        retail = self.push(rv.PUSH_VA, p)
        p = self.world(*args, **kw)
        return retail, self.push(self.entry, p)

    def scenes(self, n, seed, *, defenders=True, mates=True):
        rnd = random.Random(seed)
        for _ in range(n):
            car = (rnd.uniform(-24, 24), rnd.uniform(-40, 40), rnd.uniform(-3, 3), rnd.uniform(4, 9))
            near = lambda: (car[0] + rnd.uniform(-9, 9), car[1] + rnd.uniform(-9, 9),
                            rnd.uniform(-9, 9), rnd.uniform(-9, 9))
            ds = [near() + (rnd.choice((1, 1, 2)),) for _ in range(rnd.randint(0, 4) if defenders else 0)]
            ms = []
            for _ in range(rnd.randint(0, 4) if mates else 0):
                cls = rnd.choice((1, 2, 2, 10))
                row = near() + (cls,)
                if cls == 2 and ds:
                    row += (rnd.randrange(len(ds)),)
                ms.append(row)
            yield car, ds, ms, rnd.choice((1.0, -1.0))

    def test_relocated_copy_is_the_retail_routine_bit_for_bit(self):
        # the owner copy with every player on the retail path (a test-only mode): the copy, its nine relocated calls,
        # the player detour and the four operand edits must reproduce 0x2E2260 exactly. A fresh machine, so no
        # translated block of the shipped stub is reused.
        code, _ = rv._code(self.va, self.push_bytes, mode="retail")
        shipped = self.m
        self.m = self.machine(repin_edit(self.final, self.va, code))
        try:
            for car, ds, ms, d in self.scenes(160, 7801):
                retail, copy = self.both(car, ds, ms, direction=d)
                self.assertEqual(struct.pack("<f", retail), struct.pack("<f", copy), (car, ds, ms, d))
        finally:
            self.m = shipped

    def test_humans_urgent_clocks_and_teammates_keep_the_retail_push(self):
        for car, ds, ms, d in self.scenes(120, 7802):
            for kw in (dict(cpu=False), dict(urgency=0.8), dict(cpu=False, urgency=0.8)):
                retail, vision = self.both(car, ds, ms, direction=d, **kw)
                self.assertEqual(struct.pack("<f", retail), struct.pack("<f", vision), (car, ds, ms, d, kw))
        for car, _, ms, d in self.scenes(120, 7803, defenders=False):
            retail, vision = self.both(car, (), ms, direction=d)                  # CPU, calm clock, no defenders
            self.assertEqual(struct.pack("<f", retail), struct.pack("<f", vision), (car, ms, d))
        retail, vision = self.both((10, 0, 0, 8), [(8, 1, 0, 8)], urgency=0.5)  # 0.5 is calm: vision acts
        self.assertNotEqual(retail, vision)

    def test_defenders_are_judged_where_they_are_going(self):
        # Pushes are sideways (+ = toward +x for a team moving toward +z). Every defender here is within 2 yards
        # sideways at his judged spot, so the retail "all pursuit on one side" rule (2..10 yards) stays out of it.
        for d in (1.0, -1.0):
            f = lambda row: tuple(v * d for v in row)
            # a chaser a yard inside and two behind, stride for stride: retail pushes the runner outward; he never
            # gets closer, and behind him counts for nothing in the owner table: no push
            retail, vision = self.both(f((10, 0, 0, 8)), [f((9, -2, 0, 8))], direction=d)
            self.assertGreater(retail * d, 0.1)
            self.assertEqual(vision, 0.0)
            # a man from inside and ahead who runs past the play toward the sideline: retail pushes the runner
            # outward, into his path; at their closest approach (0.25 s) he is outside: cut back inside
            retail, vision = self.both(f((10, 0, 0, 8)), [f((8, 2, 9, 1))], direction=d)
            self.assertGreater(retail * d, 1.0)
            self.assertLess(vision * d, -1.0)
            # a man standing half a yard outside, three yards ahead: they meet on the same side he stands now, and
            # the strength is his bearing now, so the push is the retail sidestep exactly
            retail, vision = self.both(f((10, 0, 0, 8)), [f((10.5, 3, 0, 0))], direction=d)
            self.assertEqual(struct.pack("<f", vision), struct.pack("<f", retail))
            self.assertLess(vision * d, -1.0)
            # one behind and outside who is falling away: retail still pushes a little; vision none
            retail, vision = self.both(f((10, 0, 0, 8)), [f((12, -3, 0, 3))], direction=d)
            self.assertLess(retail * d, -0.05)
            self.assertEqual(vision, 0.0)


@unittest.skipIf(uc is None, "unicorn is not installed")
class SidelineTests(unittest.TestCase):
    """The real sideline filter 0x2E2780 with the ball-carrier cave, standard and wide taper (as in
    test_nfl2k5_ball_carrier_ai). Headings are 16-bit angles, 0 = straight upfield toward +z, positive = toward +x."""
    HEAP, STACK, RET = 0x3000000, 0x3100000, 0x3200000

    @classmethod
    def setUpClass(cls):
        cls.retail, cls.wide, cls.final, _ = built()
        cls.standard, _ = bc.apply(cls.retail)

    def heading(self, payload, x, h, *, cpu=True, urgency=0.0):
        m = PushTests.machine.__func__(type("M", (), dict(HEAP=self.HEAP, STACK=self.STACK, RET=self.RET,
                                                          RESULT=self.RET + 0x100)), payload)
        p, ctl, mat, team, t8, t12, tc, p10, state, clock, opp, o8 = (self.HEAP + 0x200 * i for i in range(12))
        put = lambda va, v: m.mem_write(va, struct.pack("<I", v & 0xFFFFFFFF))
        flt = lambda va, v: m.mem_write(va, struct.pack("<f", v))
        put(p + 0xC, ctl); put(ctl, 0xFFFFFFFF if cpu else 0)
        put(p + 0x18, mat); flt(mat + 0x30, x); flt(mat + 0x38, 0.0)
        put(p + 0x38, team); put(p + 0x10, p10); flt(p10 + 0x1B4, 0.7)
        put(team + 8, t8); put(t8 + 0xC, t12); flt(t12 + 4, 1.0)
        put(team + 0xC, tc); flt(tc + 0xC4, urgency)
        put(team, opp); put(opp + 8, o8)
        put(0xE602EC, state); put(state + 4, 1); flt(state + 0x28, 0.0)
        put(0xE6028C, clock); flt(clock + 0x10, 900.0); put(0xE60280, team)
        esp = self.STACK + 0x8000
        m.mem_write(esp, struct.pack("<III", self.RET, p, h & 0xFFFF))
        m.reg_write(x86.UC_X86_REG_ESP, esp)
        m.emu_start(0x2E2780, self.RET, count=100000)
        out = m.reg_read(x86.UC_X86_REG_EAX) & 0xFFFF
        return round((out - 0x10000 if out >= 0x8000 else out) * 360 / 65536, 1)

    def test_wide_taper_bends_outward_requests_from_nine_yards(self):
        for yd in (12, 9, 7, 5, 3, 2, 1.5, 1, 0.5, 0, -0.5):
            w = max(0.0, min(1.0, (yd - 1) / 8))
            want = round(math.degrees(math.atan(w)), 1)                         # an outward 45 degree request
            self.assertAlmostEqual(self.heading(self.final, SIDELINE - yd * YARD, 0x2000), want, delta=0.25, msg=yd)
            self.assertLessEqual(self.heading(self.final, SIDELINE - yd * YARD, 0x2000),
                                 self.heading(self.standard, SIDELINE - yd * YARD, 0x2000), yd)
        self.assertEqual(self.heading(self.final, -(SIDELINE - 0.5 * YARD), 0xE000), 0.0)   # the other sideline

    def test_wide_taper_keeps_inward_human_and_urgent_requests(self):
        for yd in (8, 5, 2, 1, 0.5):
            x = SIDELINE - yd * YARD
            self.assertEqual(self.heading(self.final, x, 0xE000), self.heading(self.retail, x, 0xE000), yd)
            self.assertEqual(self.heading(self.final, x, 0x2000, cpu=False), self.heading(self.retail, x, 0x2000, cpu=False))
            self.assertEqual(self.heading(self.final, x, 0x2000, urgency=0.8), self.heading(self.retail, x, 0x2000, urgency=0.8))
        self.assertEqual(self.heading(self.final, 0.0, 0x38E3), 80.0)                          # mid-field: untouched


if __name__ == "__main__":
    unittest.main()
