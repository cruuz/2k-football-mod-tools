"""Return coverage pursuit angles (nfl2k5_return_coverage): exact bytes, replay, refusal, presets, late-owner
placement, and the real far-chase task 0x2E8F20 plus bearing 0x210B0 run in Unicorn on retail and patched bytes.

No game boot. The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent).
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_return_coverage as rc
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

# The cave as placed at 0x14EC5D0 (the released v0.6.1 executable's free late-owner span).
CAVE_AT_14EC5D0 = (
    "a1bc02e60089c1b8460000000fa3c87205e9ca4ab3fe8b460c8338ff75f38b47188b4e18f30f104030f30f1048380f28d0f30f5c51"
    "300f28d9f30f5c59380f28e2f30f59e40f28ebf30f59edf30f58e5f30f51e48b5610f30f102d28dd4e00f30f59aab4010000f30f582d"
    "700f4f00f30f5ee5f30f5d259c414e00f30f106840f30f59ecf30f107048f30f59f4f30f58e8f30f58f1f30f5d2d28045100f30f5f2d"
    "24045100f30f5c6930f30f5c7138f30f116c2404f30f11742408e9204ab3fe")
YARD = 91.44
SIDELINE_IN = 2346.96


class StaticTests(unittest.TestCase):
    def test_cave_bytes_sites_and_request(self):
        code, labels = rc.code_for(0x14EC5D0)
        self.assertEqual(len(code), rc.CODE_SIZE)
        self.assertEqual(code.hex(), CAVE_AT_14EC5D0 + "cc" * (rc.CODE_SIZE - len(CAVE_AT_14EC5D0) // 2))
        self.assertEqual((labels["entry"], labels["retail"], labels["lead"]), (0, 17, 22))
        self.assertEqual(rc.REQUESTS, (("nfl2k5_return_coverage", "code", 192, 16),))
        self.assertEqual(rc.sites(0x14EC5D0), [
            ("pursuit_aim", 0x2E9148, bytes.fromhex("e8637fd3ff"), bytes.fromhex("e883342001"))])

    def test_presets_options_and_late_owner_order(self):
        self.assertEqual(space.LATE_OWNERS[-2:], ("nfl2k5_return_coverage", "nfl2k5_module_loader"))
        self.assertEqual(space.LATE_OWNERS[-1], "nfl2k5_module_loader")
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).return_coverage, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["return_coverage"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        self.assertIn("return_coverage", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_return_coverage", "Return coverage pursuit angles"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        text = (ROOT / "mod_editor/core/nfl2k5_return_coverage.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("\u2014", rc.HELP_TEXT + rc.BUILD_CAPTION)


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = rc.apply(cls.retail)

    def test_site_code_and_receipt(self):
        self.assertEqual(rc.status(self.retail), "retail")
        self.assertEqual(rc.status(self.final), "applied")
        image = XbeImage(self.final)
        code = rc.allocation(self.final)["va"]
        self.assertEqual(image.read(code, rc.CODE_SIZE), rc.code_for(code)[0])
        for _, va, _, new in rc.sites(code):
            self.assertEqual(image.read(va, len(new)), new)
        self.assertEqual(space.status(self.final), "applied")
        self.assertEqual(self.receipt["status"], "applied")

    def test_only_the_hook_changes_in_retail_sections(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        changed = []
        for s in a.sections:
            if s.raw_size:
                x, y = a.read(s.start, s.raw_size), b.read(s.start, s.raw_size)
                changed += [s.start + i for i in range(len(x)) if x[i] != y[i]]
        self.assertEqual(changed, list(range(rc.HOOK_VA + 1, rc.HOOK_VA + 5)))

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = rc.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = rc.allocation(self.final)["va"]
        for label, (va, content) in {
            "hook": (rc.HOOK_VA, b"\xe9\x00\x00\x00\x00"),
            "cave": (code + 20, b"\x90"),
            "pursuit": (0x2E8F40, b"\x90"),
            "bearing": (0x210C0, b"\x90"),
            "speed": (0x237C79, b"\x90"),
            "band constant": (0x4EDD28, b"\x00\x00\x00\x00"),
            "sideline constant": (0x510428, b"\x00\x00\x00\x00"),
        }.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(rc.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                rc.apply(bad)
        retail_bad = repin_edit(self.retail, 0x2E8F40, b"\x90")
        self.assertEqual(rc.status(retail_bad), "foreign")
        with self.assertRaises(ValueError):
            rc.apply(retail_bad)


@unittest.skipIf(uc is None, "unicorn is not installed")
class PursuitTests(unittest.TestCase):
    """The real 0x2E8F20 far-chase task and the real 0x210B0 bearing on a synthetic carrier.

    The task's own target selection, 23AA40 gate, distance and speed helpers, the patched cave and the bearing all
    execute XBE instructions. Python supplies the carrier path and reads the requested bearing at 0x210B0's entry.
    The hand-off/give-up branches, the close-pursuit task and the turn integrator are outside this fixture.
    """
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, _ = rc.apply(cls.retail)

    def machine(self, payload, *, carrier=(0.0, 20 * YARD), velocity=(0.0, 0.0),
                defender=(0.0, 0.0), rating=0.90, human=False, kind=6):
        from tests.mod_editor.test_nfl2k5_kickoff_v2 import NativeMachine
        m = NativeMachine(payload, direction=1)
        m.put(0xE5FC00, m.BALL)
        m.put(m.BALL, m.RETURNER)
        m.put(m.RETURNER + 0x1C, 1)
        m.put(m.RETURNER + 0x38, m.RECEIVE_TEAM)
        m.put(m.COVERAGE + 0x38, m.KICK_TEAM)
        task = 0x2028000
        m.put(m.COVERAGE + 0x20, m.COVERAGE + 0x200)
        m.put(m.COVERAGE + 0x200 + 0x310, task)
        m.put(task + 0x40, m.RETURNER)
        m.put(task, rc.PURSUIT)
        m.place(m.COVERAGE, defender[0], defender[1])
        m.place(m.RETURNER, carrier[0], carrier[1], velocity[0], velocity[1])
        m.f32(m.COVERAGE + 0x900 + 0x1B4, rating)
        m.f32(m.GAME + 0x10, 600.0)
        m.f32(m.CTX + 0x18, 2000.0)
        m.put(m.KICK_TEAM + 0x204, 8 << 8)
        m.put(m.RECEIVE_TEAM + 0x204, 9 << 8)
        m.put(rc.PLAY_KIND, kind)
        if human:
            m.put(m.COVERAGE + 0xC, m.COVERAGE + 0x100)
            m.put(m.COVERAGE + 0x100, 0)
        m.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.aim = None
        def bearing(uc_, address, size, data):
            sp = uc_.reg_read(x86.UC_X86_REG_ESP)
            self.aim = (struct.unpack("<f", uc_.mem_read(sp + 4, 4))[0],
                        struct.unpack("<f", uc_.mem_read(sp + 8, 4))[0])
            uc_.reg_write(x86.UC_X86_REG_EIP, m.STOP)
        m.uc.hook_add(uc.UC_HOOK_CODE, bearing, begin=rc.BEARING, end=rc.BEARING)
        m.run(rc.PURSUIT, ecx=m.COVERAGE, stop=m.STOP, budget=2_000_000)
        self.assertIsNotNone(self.aim, "the chase task never reached the bearing")
        return m, self.aim

    def aim_at(self, payload, **kwargs):
        # At 0x210B0 entry [esp+4] is the lateral (x) delta and [esp+8] the forward (z) delta.
        m, (lateral, forward) = self.machine(payload, **kwargs)
        return (m.readf(m.get(m.COVERAGE + 0x18) + 0x30) + lateral,
                m.readf(m.get(m.COVERAGE + 0x18) + 0x38) + forward)

    def test_retail_aims_at_the_current_position_and_patched_leads_it(self):
        carrier = (0.0, 20 * YARD)
        velocity = (8 * YARD, 0.0)
        retail = self.aim_at(self.retail, carrier=carrier, velocity=velocity)
        patched = self.aim_at(self.patched, carrier=carrier, velocity=velocity)
        self.assertAlmostEqual(retail[0], carrier[0], places=3)
        self.assertAlmostEqual(retail[1], carrier[1], places=3)
        self.assertGreater(patched[0], carrier[0] + 1 * YARD)
        self.assertAlmostEqual(patched[1], carrier[1], places=3)
        self.assertLessEqual(patched[0], SIDELINE_IN)

    def test_contain_clamps_the_lead_inside_the_sideline(self):
        carrier = (20 * YARD, 20 * YARD)
        velocity = (9 * YARD, 0.0)
        patched = self.aim_at(self.patched, carrier=carrier, velocity=velocity)
        self.assertGreater(patched[0], carrier[0])
        self.assertLessEqual(patched[0], SIDELINE_IN)
        self.assertGreater(patched[1], carrier[1])

    def test_scrimmage_and_field_goal_kinds_keep_the_retail_aim(self):
        carrier = (0.0, 20 * YARD)
        velocity = (8 * YARD, 0.0)
        retail = self.aim_at(self.retail, carrier=carrier, velocity=velocity)
        for kind in (0, 3, 4, 5, 7):
            patched = self.aim_at(self.patched, carrier=carrier, velocity=velocity, kind=kind)
            self.assertEqual(struct.pack("<2f", *patched), struct.pack("<2f", *retail), f"kind {kind}")

    def test_kickoff_safety_kick_and_punt_kinds_take_the_lead(self):
        carrier = (0.0, 20 * YARD)
        velocity = (8 * YARD, 0.0)
        for kind in (1, 2, 6):
            patched = self.aim_at(self.patched, carrier=carrier, velocity=velocity, kind=kind)
            self.assertGreater(patched[0], carrier[0] + 1 * YARD, f"kind {kind}")

    def test_stationary_carrier_and_human_defender_keep_retail(self):
        carrier = (0.0, 20 * YARD)
        retail = self.aim_at(self.retail, carrier=carrier)
        patched = self.aim_at(self.patched, carrier=carrier)
        self.assertAlmostEqual(patched[0], retail[0], places=3)
        self.assertAlmostEqual(patched[1], retail[1], places=3)
        human = self.aim_at(self.patched, carrier=carrier, velocity=(8 * YARD, 0.0), human=True)
        moving_retail = self.aim_at(self.retail, carrier=carrier, velocity=(8 * YARD, 0.0))
        self.assertEqual(struct.pack("<2f", *human), struct.pack("<2f", *moving_retail))

    @staticmethod
    def _heading(m, dx, dz):
        m.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        m.run(rc.BEARING, args=(struct.unpack("<I", struct.pack("<f", dx))[0],
                                struct.unpack("<I", struct.pack("<f", dz))[0]),
              stop=m.STOP, budget=200_000)
        return m.uc.reg_read(x86.UC_X86_REG_EAX)


if __name__ == "__main__":
    unittest.main()
