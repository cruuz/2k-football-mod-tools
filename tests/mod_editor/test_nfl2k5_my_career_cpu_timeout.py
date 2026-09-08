"""Native CPU timeout/debit and return with a declared presentation-end event."""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_my_career_cpu_fixture import Machine, retail_playbook
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE, ROST, PLAY and Unicorn required")
class TimeoutTests(unittest.TestCase):
    def test_native_late_half_cpu_timeout_once_with_myplayer_absent(self):
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
            # Declared game situation: Q2, two seconds, first down in field
            # goal range, offense trails 7-0. No decision or debit is forced.
            m.put(0xE602C4, 2)
            timer = m.get(0xE6028C)
            m.uc.mem_write(timer + 16, struct.pack('<f', 2))
            m.put(m.get(0xE602EC) + 4, 1)
            m.uc.mem_write(m.get(0xE602EC) + 24, struct.pack('<f', 3000))
            m.put(m.get(m.defense + 8), 7)
            stats = m.get(m.offense + 8)
            self.assertEqual(m.get(stats + 4), 3)
            calls = []
            for va in (0xA00A0, 0x55C70, 0xB8810):
                m.stubs.append(m.uc.hook_add(
                    m.u.UC_HOOK_CODE, lambda _uc, address, *_: calls.append(address),
                    begin=va, end=va))
            for _ in range(30):
                m.call(0xAF2C0, args=(0x3C888889,))
                m.call(0x18C1F0, budget=2000000)
                m.call(0x89BA0, budget=2000000)
                self.assertEqual(m.call("mode_unit_present"), 0)
            self.assertEqual(calls, [0xA00A0, 0x55C70, 0xB8810])
            self.assertEqual(m.get(stats + 4), 2)
            self.assertEqual(m.get(stats + 20), 0)
            self.assertEqual(m.get(m.get(m.defense + 8) + 4), 3)
            self.assertEqual(m.get(0xE602B8), 19)
            self.assertEqual(m.get(0xE602F8), m.offense)
            self.assertTrue(m.get(timer + 24) & 6)
            self.assertAlmostEqual(struct.unpack('<f', m.uc.mem_read(timer + 16, 4))[0],
                                   2 - 1 / 60, places=5)
            # Supply the presentation's return-to-play event. Native
            # 89260 -> A2D40 -> A11F0 performs re-entry and offensive choice;
            # no Python write changes the football phase or chosen flags.
            returns = []
            for va in (0xA2D40, 0xA11F0, 0x20B670, 0x20B820):
                m.stubs.append(m.uc.hook_add(
                    m.u.UC_HOOK_CODE, lambda _uc, address, *_: returns.append(address),
                    begin=va, end=va))
            m.call(0x89260, ecx=5, budget=20000000)
            m.call(0x20B820, ecx=m.defense, edx=0, args=(0,), budget=20000000)
            self.assertEqual(returns, [0xA2D40, 0xA11F0, 0x20B670, 0x20B820, 0xA2D40])
            self.assertEqual(m.get(0xE602B8), 12)
            for side, remaining in ((m.offense, 2), (m.defense, 3)):
                self.assertTrue(m.get(m.get(side + 12) + 36) & 8)
                self.assertEqual(m.call(0x1891B0, ecx=side), 0)
                self.assertEqual(m.get(m.get(side + 8) + 4), remaining)
            self.assertEqual(calls, [0xA00A0, 0x55C70, 0xB8810])
            self.assertEqual(m.call("mode_unit_present"), 0)
            self.assertEqual(m.get(m.state + 2564), m.match_player)
            self.assertEqual(m.get(m.state + 2572), 0)
            self.assertEqual(m.get(m.state + 64), 0)


if __name__ == "__main__":
    unittest.main()
