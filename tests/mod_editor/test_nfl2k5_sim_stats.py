"""Franchise simulated-game pace (nfl2k5_sim_stats): bytes, build options and real native games.

The pinned USA retail default.xbe and the signed f0 franchise are read from the private fixtures and the
native tests skip when they are absent.  One native game per Sim. Quarter Length runs the retail simulator
initializer, the real step callbacks and the terminal finalizer in Unicorn; no game boot is claimed.
"""
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_sim_stats as ss
from mod_editor.core.nfl2k5_bump_strength import _section_for_offset, _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

try:
    import unicorn  # noqa: F401
    HAVE_UNICORN = True
except ImportError:  # pragma: no cover
    HAVE_UNICORN = False


def retail_bytes():
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes as _retail_bytes
    return _retail_bytes()


class BytesTests(unittest.TestCase):
    def test_constant_geometry_and_rate(self):
        self.assertEqual(len(ss.RETAIL_SITE), ss.SITE_SIZE)
        self.assertEqual(len(ss.RETAIL_REGION), ss.REGION_SIZE)
        self.assertEqual(ss.REGION + ss.REGION_SIZE, 0x10B910)
        self.assertEqual(ss.SITE + ss.SITE_SIZE, 0x10B8D2)
        self.assertEqual(ss.REQUESTS, ())
        self.assertEqual(ss.RATE, 0.0315)
        self.assertEqual(ss.APPLIED_SITE[:10],
                         b"\xc7\x05" + struct.pack("<I", 0xA97204) + struct.pack("<f", ss.RATE))
        self.assertEqual(ss.APPLIED_SITE[10:16], bytes.fromhex("8b7424183bf3"))
        self.assertEqual(set(ss.APPLIED_SITE[16:]), {0x90})
        # the displaced instructions and every byte outside the site are still retail
        self.assertEqual(ss.APPLIED_REGION[:ss.SITE - ss.REGION],
                         ss.RETAIL_REGION[:ss.SITE - ss.REGION])
        self.assertEqual(ss.APPLIED_REGION[ss.SITE - ss.REGION + ss.SITE_SIZE:],
                         ss.RETAIL_REGION[ss.SITE - ss.REGION + ss.SITE_SIZE:])
        text = (ROOT / "mod_editor/core/nfl2k5_sim_stats.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("\u2014", ss.HELP_TEXT + ss.BUILD_CAPTION)

    def test_apply_replay_and_digest(self):
        retail = retail_bytes()
        self.assertEqual(ss.status(retail), "retail")
        patched, receipt = ss.apply(retail)
        self.assertEqual(ss.status(patched), "applied")
        self.assertEqual(receipt["code_bytes"], 0)
        self.assertEqual(receipt["writable_bytes"], 0)
        self.assertEqual(receipt["readonly_bytes"], 0)
        self.assertEqual(receipt["site_bytes"], ss.SITE_SIZE)
        changed = [i for i, (a, b) in enumerate(zip(retail, patched)) if a != b]
        site = XbeImage(retail).offset(ss.SITE, ss.SITE_SIZE)
        section = _section_for_offset(_sections(patched), site)
        digest = range(section.header_offset + 36, section.header_offset + 56)
        image = XbeImage(retail)
        opening = image.offset(ss.OPENING_SITE, len(ss.RETAIL_OPENING))
        merge = image.offset(ss.MERGE_SITE, 5)
        for offset in changed:
            self.assertTrue(site <= offset < site + ss.SITE_SIZE or opening <= offset < opening + len(ss.RETAIL_OPENING)
                            or merge <= offset < merge + 5 or offset in digest, hex(offset))
        self.assertEqual(section_digest(patched, section), section.stored_digest)
        again, replay = ss.apply(patched)
        self.assertEqual(again, patched)
        self.assertTrue(replay["already_applied"])
        self.assertEqual(replay["changed_bytes"], 0)

    def test_pace_only_upgrade_rollback_and_mixed_regions(self):
        # Reuse the public 22-section USA-shaped fixture. Its first three four-byte sections have enough raw
        # padding to receive each complete stock recognition region without any commercial game data.
        from tests.mod_editor.test_nfl2k5_xbe_space import synthetic, repin
        fixture = bytearray(synthetic())
        image = XbeImage(fixture)
        for section, address, region in zip(image.sections[:3], (ss.OPENING_SITE, ss.REGION, ss.MERGE_REGION),
                                            (ss.RETAIL_OPENING, ss.RETAIL_REGION, ss.RETAIL_MERGE_REGION)):
            struct.pack_into("<IIII", fixture, section.header + 4, address, len(region), section.raw, len(region))
            fixture[section.raw:section.raw + len(region)] = region
        retail = repin(fixture)
        self.assertEqual(ss.status(retail), "retail")
        image = XbeImage(retail)
        pace_offset = image.offset(ss.SITE, ss.SITE_SIZE)
        old = bytearray(retail)
        old[pace_offset:pace_offset + ss.SITE_SIZE] = ss.APPLIED_SITE
        old = repin(old)
        self.assertEqual(ss.status(old), "previous")
        upgraded, receipt = ss.apply(old)
        self.assertEqual([e["label"] for e in receipt["edits"]],
                         ["simulator_appearance_registration", "games_played_history_add"])
        self.assertEqual(ss.apply(retail)[0], upgraded)
        self.assertEqual(ss.restore_pace_only(upgraded), old)
        self.assertEqual(ss.restore_pace_only(old), old)
        self.assertEqual(ss.apply(upgraded)[0], upgraded)
        for address in (ss.OPENING_SITE, ss.MERGE_SITE, ss.MERGE_REGION):
            with self.subTest(address=address):
                bad = bytearray(upgraded)
                bad[image.offset(address)] ^= 1
                self.assertEqual(ss.status(bad), "foreign")
                with self.assertRaises(ss.SimStatsError):
                    ss.apply(bad)
                with self.assertRaises(ss.SimStatsError):
                    ss.restore_pace_only(bad)
        for address, region in [(ss.MERGE_SITE, ss.RETAIL_MERGE_CALL), (ss.OPENING_SITE, ss.RETAIL_OPENING)]:
            with self.subTest(mixed_region=address):
                bad = bytearray(upgraded)
                at = image.offset(address, len(region))
                bad[at:at + len(region)] = region
                self.assertEqual(ss.status(bad), "foreign")

    def test_released_v061_simulator_region_is_retail(self):
        path = Path(os.environ.get("NFL2K5_V061_XBE", "/nonexistent"))
        if not path.is_file():
            self.skipTest("the released v0.6.1 extraction is not in this scratch")
        data = path.read_bytes()
        self.assertEqual(ss.status(data), "retail")
        patched, _ = ss.apply(data)
        self.assertEqual(ss.status(patched), "applied")

    def test_foreign_region_refuses(self):
        retail = bytearray(retail_bytes())
        offset = XbeImage(bytes(retail)).offset(ss.REGION, ss.REGION_SIZE)
        retail[offset] ^= 0xFF
        self.assertEqual(ss.status(bytes(retail)), "foreign")
        with self.assertRaises(ss.SimStatsError):
            ss.apply(bytes(retail))

    def test_composes_with_the_overtime_sim_hooks(self):
        from mod_editor.core import nfl2k5_overtime as ot
        retail = retail_bytes()
        over, _ = ot.apply(retail)
        self.assertEqual(ss.status(over), "retail")
        both, _ = ss.apply(over)
        self.assertEqual((ss.status(both), ot.status(both)), ("applied", "applied"))
        mine, _ = ss.apply(retail)
        both2, _ = ot.apply(mine)
        self.assertEqual((ss.status(both2), ot.status(both2)), ("applied", "applied"))

    def test_build_options_and_presets(self):
        plan = mod_build.BuildPlan(Path("source.iso"), Path("target.iso"))
        self.assertIs(plan.sim_stats, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["sim_stats"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        self.assertIn("sim_stats", settings.FEATURE_KEYS)
        self.assertIs(mod_build.availability()["sim_stats"], True)


@unittest.skipUnless(HAVE_UNICORN, "unicorn is not installed")
class AppearanceHistoryTests(unittest.TestCase):
    def test_calling_convention_and_appearance_boundaries(self):
        # Run the emitted instructions, then inspect the arguments received by the unmodified history writer.
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn import x86_const as x86
        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        player, bank, career_row, stack = 0x300000, 0x301000, 0x302000, 0x303000

        def write(address, value):
            uc.mem_write(address, struct.pack("<I", value))

        for page in (ss.OPENING_SITE & ~0xfff, ss.MERGE_SITE & ~0xfff, 0x14f000, 0xe5f000, 0xe57000,
                     player, bank, career_row, stack):
            uc.mem_map(page, 0x1000)
        uc.mem_write(ss.OPENING_SITE, ss.APPLIED_OPENING)
        uc.mem_write(ss.MERGE_SITE, ss.APPLIED_MERGE_CALL)

        def decision(categories=(), *, mode=4, stage=8, field=0, original=0, missing=0):
            uc.mem_write(bank, bytes(108))
            for category, weight in categories:
                uc.mem_write(bank + category * 8 + 4, struct.pack("<f", weight))
            write(0xe5ff80, mode)
            write(0xe576a4, stage)
            write(player + 0x30, 0 if missing == 1 else player + 0x200)
            write(player + 0x200, 0 if missing == 2 else bank)
            write(stack + 0x400, original)
            uc.reg_write(x86.UC_X86_REG_ESP, stack + 0x400)
            uc.reg_write(x86.UC_X86_REG_EBP, player)
            uc.reg_write(x86.UC_X86_REG_ECX, career_row)
            uc.reg_write(x86.UC_X86_REG_EDX, field)
            uc.reg_write(x86.UC_X86_REG_EAX, original)
            uc.emu_start(ss.MERGE_SITE, 0x14f450, count=160)
            self.assertEqual(uc.reg_read(x86.UC_X86_REG_EIP), 0x14f450)
            self.assertEqual(uc.reg_read(x86.UC_X86_REG_ECX), career_row)
            self.assertEqual(uc.reg_read(x86.UC_X86_REG_EDX), field)
            self.assertEqual(uc.reg_read(x86.UC_X86_REG_EAX), original)
            self.assertEqual(uc.reg_read(x86.UC_X86_REG_EBP), player)
            self.assertEqual(uc.reg_read(x86.UC_X86_REG_ESP), stack + 0x3fc)
            self.assertEqual(struct.unpack("<I", uc.mem_read(stack + 0x3fc, 4))[0], ss.MERGE_SITE + 5)
            return struct.unpack("<I", uc.mem_read(stack + 0x400, 4))[0]

        self.assertEqual(decision(), 0)
        self.assertEqual(decision([(12, 1.0)]), 0)
        for category in range(12):
            with self.subTest(category=category):
                self.assertEqual(decision([(category, 1.0)]), 1)
        activity = [(1, 59.0), (4, 1.0), (12, 1.0)]
        self.assertEqual(decision(activity), 1)
        for mode in (0, 3, 5, 6, 7):
            self.assertEqual(decision(activity, mode=mode), 0)
        for stage in (0, 6, 7, 9, 10):
            self.assertEqual(decision(activity, stage=stage), 0)
        for field in (1, 6, 12, 18, 50):
            self.assertEqual(decision(activity, field=field), 0)
        for value in (1, 2):
            self.assertEqual(decision(activity, missing=value), 0)
            self.assertEqual(decision(activity, original=value), value)


@unittest.skipUnless(HAVE_UNICORN, "unicorn is not installed")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.patched = ss.apply(cls.retail)[0]
        from tests.nfl2k5_supersim_draft_fixture import signed_save
        try:
            cls.save = signed_save()
        except unittest.SkipTest:
            raise unittest.SkipTest("private signed f0 franchise is absent")

    def one_game(self, payload, sim_minutes, seed=12345):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = Machine(payload, trace_writes=False)
        m.load_franchise(self.save)
        m.seed(seed)
        for address, value in ((0xE5FF80, 4), (0xE576A4, 8), (0xE6000C, 5), (0xE60010, sim_minutes)):
            m.put(address, value)
        m.call(0x77AE0, ecx=m.team_base)
        m.call(0x77B20, ecx=m.team_base + 500)
        m.call(0x10B280, ecx=m.team_base, edx=m.team_base + 500, args=(0, 1, 0, 0, 0, 0),
               budget=3_000_000)
        m.call(0x10B250, budget=1_000_000)
        steps = 0
        while True:
            result = m.call(0x10B250, budget=1_000_000)
            steps += 1
            if result in (5, -1):
                break
            self.assertLess(steps, 5000, "simulator did not finish")
        scores = (m.call(0x250DD0, ecx=0, edx=0), m.call(0x250DD0, ecx=1, edx=0))
        return m, steps, scores

    def test_clock_decrement_is_independent_of_sim_quarter_length(self):
        runs = []
        for minutes in (3, 5, 10, 15):
            m, steps, scores = self.one_game(self.patched, minutes)
            self.assertAlmostEqual(m.f32(0xA97204), ss.RATE, places=6)
            self.assertEqual(m.get(0xE6000C), 5)       # the played-game setting is untouched
            self.assertEqual(m.get(0xE60010), minutes)  # the sim setting is untouched
            self.assertEqual(len(scores), 2)
            self.assertTrue(all(0 <= score <= 100 for score in scores))
            runs.append((steps, scores))
        counts = [steps for steps, _ in runs]
        self.assertLess(max(counts) - min(counts), max(counts) * 0.18,
                        f"sim pace still follows the quarter length: {counts}")

    def test_retail_rate_still_scales_and_the_patch_removes_it(self):
        before = []
        for minutes in (5, 15):
            m, steps, _ = self.one_game(self.retail, minutes)
            before.append((minutes, steps, m.f32(0xA97204)))
        self.assertGreater(before[0][2], before[1][2])       # 5 min: 0.03; 15 min: 0.0173
        self.assertGreater(before[1][1], before[0][1] * 1.4)  # retail 15-min game has far more plays
        after = []
        for minutes in (5, 15):
            m, steps, _ = self.one_game(self.patched, minutes)
            after.append(steps)
        self.assertLess(abs(after[1] - after[0]), before[0][1] * 0.2)


if __name__ == "__main__":
    unittest.main()
