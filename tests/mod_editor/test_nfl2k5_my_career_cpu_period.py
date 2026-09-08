"""Native halftime/OT return to CPU choice; presentation inputs are declared."""
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
class PeriodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest("retail XBE exceeds 16 MiB")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.payload = mode.apply(retail)[0]
        cls.roster, cls.resource = retail_roster(), retail_playbook()

    def start(self, m, period):
        m.create(self.roster, preseason=False)
        m.child_services()
        m.cpu_scene(self.resource)
        m.cpu_choice()
        m.period_inputs(period)
        self.assertEqual(m.f32(0xE602B0), 300)
        self.assertEqual(m.call("mode_unit_present"), 0)
        for side, remaining in ((m.offense, 1), (m.defense, 0)):
            m.put(m.get(side + 8) + 4, remaining)

    def assert_choice(self, m, period):
        result = m.next_choice()
        self.assertEqual(result["phase"], 12)
        self.assertTrue(all(flags & 8 for flags in result["chosen_flags"]))
        self.assertEqual(result["unit_present"], 0)
        self.assertEqual(result["offense_human"], 0)
        self.assertEqual(result["defense_human"], 0)
        self.assertEqual(m.get(0xE602C4), period)
        self.assertEqual(m.f32(m.get(0xE6028C) + 16), 300)
        self.assertEqual(m.get(0xE5FF80), 7)  # Native career Franchise match.
        for side in (m.offense, m.defense):
            self.assertEqual(m.get(m.get(side + 8) + 4), 2 if period == 5 else 3)
        self.assertEqual(m.get(m.state + 2564), m.match_player)
        self.assertEqual(m.get(m.state + 2572), 0)
        self.assertEqual(m.get(m.state + 64), 0)

    def test_half_expiry_native_heap_log_timeout_reset_and_next_cpu_choice(self):
        with Machine(self.payload) as m:
            self.start(m, 2)
            first_kicker = m.offense
            m.halftime_pool()
            calls = m.observe((0xA2970, 0xB8A60, 0xDA4D0, 0x48640,
                               0xCD4D0, 0xCD0B0, 0x9F8C0, 0xB88C0, 0x9F940))
            for _ in range(4):
                m.control_frame()
                self.assertEqual(m.get(0xE602B8), 9)
                self.assertEqual(m.get(0xE602C4), 2)
                self.assertEqual(m.call("mode_unit_present"), 0)
            self.assertEqual(calls[:6], [0xA2970, 0xB8A60, 0xDA4D0,
                                         0x48640, 0xCD4D0, 0xCD0B0])
            self.assertGreaterEqual(m.get(0xE53800), 0)
            # Presentation completion is an input, not a mocked return or
            # a Python write of the next quarter, clock or play phase.
            m.put(0xB72C30, 1)
            m.call(0x89260, ecx=3, budget=2000000)
            m.call(0xE9210, args=(0x3C888889,), budget=2000000)
            self.assertEqual(calls[-4:], [0x9F8C0, 0x48640, 0xB88C0, 0x9F940])
            self.assertEqual(m.get(0xE602B8), 11)
            self.assertEqual(m.get(0xE60280), m.get(first_kicker))
            self.assert_choice(m, 3)

    def test_tied_fourth_expiry_native_overtime_toss_return_and_cpu_choice(self):
        with Machine(self.payload) as m:
            self.start(m, 4)
            calls = m.observe((0xA2970, 0xB8A60, 0xB8B30, 0x9F780,
                               0xB8160, 0x9F690, 0xB81C0, 0x9F940))
            m.control_frame()
            self.assertEqual(calls, [0xA2970, 0xB8A60])
            self.assertEqual(m.get(0xE602B8), 21)
            self.assertEqual(m.get(0xE602C4), 4)
            # End-of-period presentation has completed. Native delayed
            # dispatch evaluates the actual tied scores and enters the toss.
            m.put(0xB72C38, 1)
            for _ in range(2):
                m.call(0xAF2C0, args=(0x3C888889,))
                m.call(0xE9210, args=(0x3C888889,), budget=2000000)
            self.assertEqual(calls[-3:], [0xB8B30, 0x9F780, 0xB8160])
            self.assertEqual(m.get(0xE602B8), 7)
            self.assertEqual(m.get(0xE602C4), 4)
            # The toss UI callback input uses the declared side/direction.
            # 9F690/9F940 own quarter, clock, roster and drive-log changes.
            m.call(0x9F690, ecx=m.offense, edx=1, budget=2000000)
            self.assertEqual(calls[-3:], [0x9F690, 0xB81C0, 0x9F940])
            self.assert_choice(m, 5)


if __name__ == "__main__":
    unittest.main()
