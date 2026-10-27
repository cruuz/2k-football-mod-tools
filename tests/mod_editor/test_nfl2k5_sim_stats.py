"""Franchise simulated-game pace (nfl2k5_sim_stats): bytes, build options and real native games.

The pinned USA retail default.xbe and the signed f0 franchise are read from the private fixtures and the
native tests skip when they are absent.  One native game per Sim. Quarter Length runs the retail simulator
initializer, the real step callbacks and the terminal finalizer in Unicorn; no game boot is claimed.
"""
import hashlib
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
        for offset in changed:
            self.assertTrue(site <= offset < site + ss.SITE_SIZE or offset in digest, hex(offset))
        self.assertEqual(section_digest(patched, section), section.stored_digest)
        again, replay = ss.apply(patched)
        self.assertEqual(again, patched)
        self.assertTrue(replay["already_applied"])
        self.assertEqual(replay["changed_bytes"], 0)

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
