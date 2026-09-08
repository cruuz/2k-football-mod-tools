"""Native injury application, CPU substitution and declared recovery interval.

The injury descriptor/event, post-play reset and elapsed recovery inputs are
supplied. Collision probability and a complete animated drive are not proved.
"""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_my_career_cpu_fixture import retail_playbook
from tests.nfl2k5_my_career_cpu_boundary import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE, ROST, PLAY and Unicorn required")
class InjuryTests(unittest.TestCase):
    def test_native_injury_backup_choice_and_timed_recovery_with_myplayer_absent(self):
        if XBE.stat().st_size > 16 * 1024**2:
            self.skipTest("retail XBE exceeds 16 MiB")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            self.skipTest("retail XBE pin differs")
        roster, resource = retail_roster(), retail_playbook()
        with Machine(mode.apply(retail)[0]) as m:
            m.create(roster, preseason=False)
            m.child_services()
            m.cpu_scene(resource)
            m.cpu_choice()
            qb = next(body for body in m.actors
                      if m.get(body + 0x38) == m.offense
                      and m.uc.mem_read(m.get(body + 0x3C) + 0x35, 1)[0] == 0)
            player = m.get(qb + 0x3C)
            self.assertNotEqual(player, m.match_player)
            injury = m.call(0x13E270, ecx=0, edx=3)
            self.assertEqual(injury, 0x4FD630)
            m.put(0xE602C4, 1)
            m.f32(m.get(0xE6028C) + 16, 300)
            calls = m.observe((0x1369D0, 0xA0370, 0x136D30, 0x189080,
                               0xE7C50, 0x18AD10, 0x1365B0, 0xE6680))
            m.call(0x136B10, eax=0,
                   args=(qb, m.actors[-1], injury, 0, 0, 0), budget=2000000)
            self.assertEqual(m.get(player + 0x24) >> 28, 4)
            self.assertFalse(m.get(player + 0x20) & 0x40000000)
            self.assertEqual(m.get(player + 0x28) & 0x3FF, m.get(injury) & 0x3FF)
            self.assertEqual(m.get(0xBB89A4), qb)
            self.assertEqual(m.get(0xBB89A0), injury)
            # Supply presentation completion/post-play reset through their
            # real native callees. The picker owns replacement roster binding.
            m.call(0xA0320, ecx=0, budget=2000000)
            m.call(0x189080, budget=2000000)
            for depth in (0x61C70, 0x61C80):
                m.call(0xE7C50, ecx=m.call(depth), budget=2000000)
            result = m.next_choice()
            self.assertEqual(result["phase"], 12)
            self.assertTrue(all(flags & 8 for flags in result["chosen_flags"]))
            self.assertEqual((result["unit_present"], result["offense_human"],
                              result["defense_human"]), (0, 0, 0))
            replacement = m.get(qb + 0x3C)
            self.assertNotEqual(replacement, player)
            self.assertEqual(m.uc.mem_read(replacement + 0x35, 1), b"\0")
            self.assertTrue(all(m.get(body + 0x3C) != player for body in m.actors))
            # Five declared rest boundaries re-enable availability. Q3's
            # declared elapsed time then exceeds the seeded six-minute injury.
            for _ in range(5):
                m.call(0x136F80, budget=2000000)
            self.assertTrue(m.get(player + 0x20) & 0x40000000)
            self.assertEqual(m.get(player + 0x24) >> 28, 2)
            m.put(0xE602C4, 3)
            m.f32(m.get(0xE6028C) + 16, 300)
            m.call(0x136F80, budget=2000000)
            self.assertEqual(m.get(player + 0x24) >> 28, 0)
            self.assertEqual(m.get(player + 0x28) & 0x3FF, 0)
            for va in (0x1369D0, 0xA0370, 0x136D30, 0x189080,
                       0xE7C50, 0x18AD10, 0x1365B0, 0xE6680):
                self.assertIn(va, calls)
            self.assertEqual(m.get(m.state + 2564), m.match_player)
            self.assertEqual(m.get(m.state + 2572), 0)
            self.assertEqual(m.get(m.state + 64), 0)


if __name__ == "__main__":
    unittest.main()
