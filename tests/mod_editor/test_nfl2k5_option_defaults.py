"""SOFTDRINK default options (nfl2k5_option_defaults): bytes, build wiring and the real native defaults routine.

The pinned USA retail default.xbe is read from the private fixtures; the native tests skip when it is absent.
The native tests run the retail boot initializer 0x77D20 (zero the options block, then FUN_00077C50) and the
restore-defaults path FUN_00127A70 in Unicorn and read the 0x2E0-byte options block at 0xE5FF80.  No game boot,
renderer or save device is claimed.
"""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_option_defaults as od
from mod_editor.core.nfl2k5_bump_strength import _section_for_offset, _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

try:
    import unicorn  # noqa: F401
    HAVE_UNICORN = True
except ImportError:  # pragma: no cover
    HAVE_UNICORN = False

BLOCK, BLOCK_SIZE = 0xE5FF80, 0x2E0
QUARTER, SIM, CHOP = 0xE6000C, 0xE60010, 0xE60064


def retail_bytes():
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes as _retail_bytes
    return _retail_bytes()


class BytesTests(unittest.TestCase):
    def test_geometry_and_encoding(self):
        self.assertEqual(od.REQUESTS, ())
        self.assertEqual(od.SITE_A + od.SITE_A_SIZE, 0x77CBD)
        self.assertEqual(od.RETAIL_SITE_A, bytes.fromhex("b805000000a30c00e600a31000e600"))
        self.assertEqual(od.site_a(7, 15), bytes.fromhex("6a0758a30c00e600" "0408" "a31000e600"))
        self.assertEqual(od.site_a(7, 3), bytes.fromhex("6a0758a30c00e600" "2c04" "a31000e600"))
        self.assertEqual(od.site_a(5, 5), bytes.fromhex("6a0558a30c00e600" "9090" "a31000e600"))
        self.assertEqual(od.site_b(True), bytes.fromhex("c7056400e60001000000"))
        self.assertEqual(od.site_b(False), od.RETAIL_SITE_B)
        for quarter in range(1, 16):
            for sim in range(3, 16):
                self.assertEqual(len(od.site_a(quarter, sim)), od.SITE_A_SIZE)
        self.assertEqual((od.DEFAULT_QUARTER_MINUTES, od.DEFAULT_SIM_MINUTES), (7, 15))
        text = (ROOT / "mod_editor/core/nfl2k5_option_defaults.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", od.HELP_TEXT + od.BUILD_CAPTION)

    def test_ranges_refuse(self):
        retail = retail_bytes()
        for quarter, sim in ((0, 15), (16, 15), (7, 2), (7, 16), (7.0, 15), (True, 15)):
            with self.assertRaises(od.OptionDefaultsError):
                od.apply(retail, quarter_minutes=quarter, sim_minutes=sim)
        with self.assertRaises(od.OptionDefaultsError):
            od.apply(retail, chop_block=1)

    def test_apply_replay_digest_and_scope(self):
        retail = retail_bytes()
        self.assertEqual(od.status(retail), "retail")
        patched, receipt = od.apply(retail)
        self.assertEqual(od.settings(patched), {"state": "applied", "quarter_minutes": 7, "sim_minutes": 15,
                                                "chop_block": True})
        self.assertEqual((receipt["code_bytes"], receipt["writable_bytes"], receipt["readonly_bytes"]), (0, 0, 0))
        image = XbeImage(retail)
        spans = [(image.offset(od.SITE_A, od.SITE_A_SIZE), od.SITE_A_SIZE),
                 (image.offset(od.SITE_B, od.SITE_B_SIZE), od.SITE_B_SIZE)]
        section = _section_for_offset(_sections(patched), spans[0][0])
        digest = range(section.header_offset + 36, section.header_offset + 56)
        for offset, (a, b) in enumerate(zip(retail, patched)):
            if a != b:
                self.assertTrue(any(s <= offset < s + n for s, n in spans) or offset in digest, hex(offset))
        self.assertEqual(section_digest(patched, section), section.stored_digest)
        again, replay = od.apply(patched)
        self.assertEqual(again, patched)
        self.assertTrue(replay["already_applied"])
        self.assertEqual(replay["changed_bytes"], 0)
        # another choice rewrites from an installed image and stays consistent
        other, _ = od.apply(patched, quarter_minutes=6, sim_minutes=12, chop_block=False)
        self.assertEqual(od.settings(other)["quarter_minutes"], 6)
        self.assertEqual(od.settings(other)["sim_minutes"], 12)
        self.assertIs(od.settings(other)["chop_block"], False)
        sec = _section_for_offset(_sections(other), spans[0][0])
        self.assertEqual(section_digest(other, sec), sec.stored_digest)

    def test_foreign_bytes_refuse(self):
        retail = bytearray(retail_bytes())
        image = XbeImage(bytes(retail))
        for va, size in ((od.REGION_A, od.REGION_A_SIZE), (od.REGION_B, od.REGION_B_SIZE)):
            mutated = bytearray(retail)
            mutated[image.offset(va + 1, 1)] ^= 0xFF
            self.assertEqual(od.status(bytes(mutated)), "foreign")
            with self.assertRaises(od.OptionDefaultsError):
                od.apply(bytes(mutated))
        # a site that is neither retail nor this owner's encoding
        mutated = bytearray(retail)
        mutated[image.offset(od.SITE_A, 1)] = 0xB9
        self.assertEqual(od.status(bytes(mutated)), "foreign")

    def test_composes_with_the_sim_pace_fix_in_either_order(self):
        from mod_editor.core import nfl2k5_sim_stats as ss
        retail = retail_bytes()
        a, _ = od.apply(retail)
        both, _ = ss.apply(a)
        b, _ = ss.apply(retail)
        both2, _ = od.apply(b)
        self.assertEqual(both, both2)
        self.assertEqual((ss.status(both), od.status(both)), ("applied", "applied"))

    def test_build_options_and_presets(self):
        plan = mod_build.BuildPlan(Path("source.iso"), Path("target.iso"))
        self.assertIs(plan.option_defaults, False)
        self.assertEqual((plan.default_quarter_minutes, plan.default_sim_quarter_minutes), (7, 15))
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["option_defaults"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        for key in ("option_defaults", "default_quarter_minutes", "default_sim_quarter_minutes"):
            self.assertIn(key, settings.FEATURE_KEYS)
        self.assertIs(mod_build.availability()["option_defaults"], True)
        self.assertTrue(mod_build.BuildPlan(Path("s"), Path("t"), option_defaults=True).wants_xbe_patch())

    def test_values_follow_the_pace_fix_and_the_chop_toggle(self):
        retail_sim = mod_build.BuildPlan(Path("s"), Path("t"), option_defaults=True, sim_stats=False)
        self.assertEqual(mod_build._option_defaults_values(retail_sim),
                         {"quarter_minutes": 7, "sim_minutes": 5, "chop_block": False})
        full = mod_build.BuildPlan(Path("s"), Path("t"), option_defaults=True, sim_stats=True, chop_block_toggle=True)
        self.assertEqual(mod_build._option_defaults_values(full),
                         {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": True})
        custom = mod_build.BuildPlan(Path("s"), Path("t"), option_defaults=True, sim_stats=True,
                                     default_quarter_minutes=6, default_sim_quarter_minutes=12)
        self.assertEqual(mod_build._option_defaults_values(custom)["quarter_minutes"], 6)
        self.assertEqual(mod_build._option_defaults_values(custom)["sim_minutes"], 12)

    def test_recipe_round_trip_and_validation(self):
        plan = mod_build.BuildPlan(Path("s"), Path("t"), option_defaults=True, default_quarter_minutes=6)
        state = settings.from_plan(plan)
        self.assertIs(state["option_defaults"], True)
        self.assertEqual(state["default_quarter_minutes"], 6)
        self.assertEqual(settings.to_plan(state, "s", "t").default_quarter_minutes, 6)
        with self.assertRaises(ValueError):
            settings.build_settings({"default_quarter_minutes": "7"})
        with self.assertRaises(ValueError):
            settings.build_settings({"option_defaults": 1})


@unittest.skipUnless(HAVE_UNICORN, "unicorn is not installed")
class NativeTests(unittest.TestCase):
    """Run the real retail defaults routine and read the whole options block."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.patched = od.apply(cls.retail)[0]

    @staticmethod
    def boot_block(payload):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = Machine(payload, trace_writes=False)
        # 0x77D20 zeroes the block, runs FUN_000E2D80 and FUN_00077C50; stop before it reads the (absent) roster.
        m.call(0x77D20, budget=2_000_000, stop=0x77D45)
        return m, bytes(m.uc.mem_read(BLOCK, BLOCK_SIZE))

    @staticmethod
    def word(block, va):
        return struct.unpack_from("<I", block, va - BLOCK)[0]

    def test_fresh_profile_defaults_fail_on_retail_and_pass_after(self):
        _, base = self.boot_block(self.retail)
        _, new = self.boot_block(self.patched)
        # retail: both options 5, Chop Block off
        self.assertEqual((self.word(base, QUARTER), self.word(base, SIM), self.word(base, CHOP)), (5, 5, 0))
        self.assertEqual((self.word(new, QUARTER), self.word(new, SIM), self.word(new, CHOP)), (7, 15, 1))

    def test_no_other_option_changes(self):
        _, base = self.boot_block(self.retail)
        _, new = self.boot_block(self.patched)
        changed = {BLOCK + i for i in range(0, BLOCK_SIZE, 4)
                   if base[i:i + 4] != new[i:i + 4]}
        self.assertEqual(changed, {QUARTER, SIM, CHOP})
        # difficulty Pro, the nine human / CPU sliders, camera and the other retail defaults stay as retail
        self.assertEqual(self.word(new, 0xE5FF84), 1)
        self.assertEqual(struct.unpack("<f", struct.pack("<I", self.word(new, 0xE600D4)))[0], 0.75)
        self.assertEqual(struct.unpack("<f", struct.pack("<I", self.word(new, 0xE600F8)))[0], 0.25)

    def test_each_pair_lands_exactly(self):
        for quarter, sim, chop in ((6, 12, False), (1, 3, True), (15, 15, True), (12, 4, False), (5, 5, False)):
            payload = od.apply(self.retail, quarter_minutes=quarter, sim_minutes=sim, chop_block=chop)[0]
            _, block = self.boot_block(payload)
            self.assertEqual((self.word(block, QUARTER), self.word(block, SIM), self.word(block, CHOP)),
                             (quarter, sim, int(chop)), (quarter, sim, chop))

    def test_reset_to_defaults_path_uses_the_same_values(self):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        for payload, expected in ((self.retail, (5, 5, 0)), (self.patched, (7, 15, 1))):
            m = Machine(payload, trace_writes=False)
            m.call(0x77D20, budget=2_000_000, stop=0x77D45)
            m.put(QUARTER, 10)
            m.put(SIM, 12)
            m.put(CHOP, 0)
            m.call(0x127A70, budget=3_000_000)   # the restore-defaults routine (online session start / end)
            self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), expected)

    def test_a_loaded_settings_block_keeps_what_it_stored(self):
        """FUN_000E2E20 copies the whole 0x2E0-byte block; the patched defaults are never consulted for a save."""
        from tests.nfl2k5_supersim_draft_fixture import Machine
        _, stored = self.boot_block(self.retail)            # a profile saved on the retail game: Quarter Length 5
        stored = bytearray(stored)
        struct.pack_into("<I", stored, QUARTER - BLOCK, 10)  # the player chose 10 minutes
        struct.pack_into("<I", stored, SIM - BLOCK, 12)      # and 12 for Sim. Quarter Length
        struct.pack_into("<I", stored, CHOP - BLOCK, 0)      # and left Chop Block off
        m = Machine(self.patched, trace_writes=False)
        m.call(0x77D20, budget=2_000_000, stop=0x77D45)
        self.assertEqual((m.get(QUARTER), m.get(SIM)), (7, 15))
        buffer = m.ARENA + 0x1000
        m.uc.mem_write(buffer, bytes(stored))
        m.call(0xE2E20, ecx=buffer)
        self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (10, 12, 0))
        self.assertEqual(bytes(m.uc.mem_read(BLOCK, BLOCK_SIZE)), bytes(stored))

    def test_no_load_path_is_hooked(self):
        """The loader and its callers are byte-identical to retail in a patched image."""
        image_r, image_p = XbeImage(self.retail), XbeImage(self.patched)
        for va, size in ((0xE2E00, 0x30), (0x63B00, 0xC0), (0x84490, 0xD0), (0x84D60, 0x60), (0x16D1D0, 0x20),
                         (0x16E7A8, 0x20), (0x16E860, 0x20), (0x28FA50, 0x30), (0x28FE90, 0x40), (0x127A70, 0xFA)):
            self.assertEqual(image_r.read(va, size), image_p.read(va, size), hex(va))


if __name__ == "__main__":
    unittest.main()
