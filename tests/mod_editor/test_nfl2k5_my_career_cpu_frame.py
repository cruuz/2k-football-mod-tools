"""Full native frame and clock proof; synthetic clips are not drive acceptance."""
from pathlib import Path
import hashlib
import math
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_my_career_cpu_fixture import retail_playbook
from tests.nfl2k5_my_career_cpu_frame import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE, ROST, PLAY and Unicorn required")
class FrameTests(unittest.TestCase):
    def test_full_cpu_frames_advance_clock_without_claiming_snap_or_drive(self):
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
            m.scene_assets()
            timer = m.get(0xE6028C) + 16
            self.assertEqual(m.f32(timer), 300)
            for frame in range(60):
                m.engine_frame()
                for body in m.actors:
                    # +50 onward includes integer heading/state, not floats.
                    transform = struct.unpack('<8f', m.uc.mem_read(m.get(body + 0x18) + 0x30, 32))
                    self.assertTrue(all(math.isfinite(value) for value in transform),
                                    (frame, hex(body), transform))
                    for address, count in (
                            (m.get(body + 0x18) + 0x60, 2),
                            (m.get(m.get(body + 0x14) + 0x34), 25 * 4),
                            (m.get(body + 4), (25 + 62) * 16)):
                        values = struct.unpack('<' + str(count) + 'f', m.uc.mem_read(address, count * 4))
                        self.assertTrue(all(math.isfinite(value) for value in values),
                                        (frame, hex(body), hex(address)))
                self.assertEqual(m.call("mode_unit_present"), 0)
            self.assertAlmostEqual(m.f32(timer), 299, delta=0.01)
            self.assertEqual(m.get(m.state + 2564), m.match_player)
            self.assertEqual(m.get(m.state + 2572), 0)
            self.assertEqual(m.get(m.state + 64), 0)
            # The supplied looping clips have not proved lineup completion.
            self.assertEqual(m.get(0xE602B8), 12)


if __name__ == "__main__":
    unittest.main()
