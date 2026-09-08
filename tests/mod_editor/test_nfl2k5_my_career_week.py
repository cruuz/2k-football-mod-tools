"""Complete native week after MyPlayer's game, including every other result.

The career game's engine-end signal is supplied at the completion boundary.
All other fixture simulation, result/history commits and weekly work are native.
The bytewise retail history writer makes this a deliberately long CPU fixture.
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
from tests.nfl2k5_my_career_played_fixture import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE, ROST and Unicorn required")
class WeekTests(unittest.TestCase):
    def test_native_other_fixtures_follow_completed_career_game_then_next_own_game(self):
        if XBE.stat().st_size > 16 * 1024**2:
            self.skipTest("retail XBE exceeds 16 MiB")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            self.skipTest("retail XBE pin differs")
        roster, payload = retail_roster(), mode.apply(retail)[0]
        with Machine(payload) as created:
            created.create(roster, preseason=False)
            source = created.native_save(budget=500000000)
        with Machine(payload) as m:
            m.cold(roster, source)
            own = m.call("mode_next_fixture")
            m.launch()
            m.finish()
            self.assertEqual(m.get(0xE576B4), 0)
            grid = bytes(m.uc.mem_read(0xE57C40, 17 * 8))
            pending = [i for i in range(17) if grid[i * 8] < 2]
            self.assertNotIn(own, pending)
            self.assertEqual(len(pending), 15)
            simulated, committed = [], []
            m.stubs.append(m.uc.hook_add(
                m.u.UC_HOOK_CODE,
                lambda *_: simulated.append((m.reg("ECX"), m.reg("EDX"))),
                begin=0xC7A20, end=0xC7A20))
            m.stubs.append(m.uc.hook_add(
                m.u.UC_HOOK_CODE,
                lambda *_: committed.append((m.get(0xE576B4), m.get(0xE576BC))),
                begin=0x1356D0, end=0x1356D0))
            m.select(0, budget=3000000000)
            self.assertEqual(simulated, [(0, slot) for slot in pending])
            self.assertEqual(committed, simulated)
            self.assertEqual(m.get(0xE576B4), 1)
            self.assertEqual(m.top(), 0x51B908)
            self.assertEqual(m.get(m.state + 64), 0)
            self.assertTrue(all(m.uc.mem_read(0xE57C40 + slot * 8, 1)[0] >= 2
                                for slot in pending))
            next_own = m.call("mode_next_fixture")
            self.assertEqual(next_own // 17, 1)
            self.assertEqual((m.get(0xE576B4), m.get(0xE576BC)),
                             (next_own // 17, next_own % 17))
            self.assertEqual(len(simulated), 15)


if __name__ == "__main__":
    unittest.main()
