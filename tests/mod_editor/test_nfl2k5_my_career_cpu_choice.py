"""Complete native CPU play choice, not an off-field drive acceptance test."""
from pathlib import Path
import hashlib
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
class CpuChoiceTests(unittest.TestCase):
    def test_native_choice_and_all_assignments_with_career_quarterback_off_field(self):
        if XBE.stat().st_size > 16 * 1024**2:
            self.skipTest("retail XBE exceeds 16 MiB")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            self.skipTest("retail XBE pin differs")
        roster, resource = retail_roster(), retail_playbook()
        payload = mode.apply(retail)[0]
        with Machine(payload) as m:
            m.create(roster, preseason=False)
            m.child_services()
            m.cpu_scene(resource)
            result = m.cpu_choice()
            self.assertEqual(result["unit_present"], 0)
            self.assertEqual((result["offense_human"], result["defense_human"]), (0, 0))
            self.assertGreater(result["visits"].get(0x20B670, 0), 0)
            self.assertGreater(result["visits"].get(0x20B820, 0), 0)
            self.assertEqual(result["visits"][0x18AD10], 4)
            self.assertGreaterEqual(result["visits"][0x1A8E60], 22)
            self.assertTrue(all(flags & 8 for flags in result["chosen_flags"]))
            self.assertEqual(m.get(m.state + 2564), m.match_player)
            self.assertEqual(m.get(m.state + 64), 0)
            self.assertEqual(m.get(m.state + 2572), 0)
            for body in m.actors:
                self.assertNotEqual(m.get(body + 0x3C), m.match_player)


if __name__ == "__main__":
    unittest.main()
