"""Played-result statistics, exact next-game routing and inline cold persistence.

These are native completion-boundary proofs, not complete football matches.
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
class PlayedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest("retail XBE exceeds 16 MiB")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.roster = retail_roster()
        cls.payload = mode.apply(retail)[0]
        with Machine(cls.payload) as m:
            m.create(cls.roster, preseason=False)
            cls.source = m.native_save(budget=500000000)

    def test_direct_earliest_career_fixture_no_other_game_card_or_simulation(self):
        with Machine(self.payload) as m:
            m.cold(self.roster, self.source)
            grid = bytes(m.uc.mem_read(0xE57C40, 22 * 17 * 8))
            club = m.get(m.state + 56)
            expected = next(i for i in range(374)
                            if grid[8*i] < 2 and club in grid[8*i+1:8*i+3])
            self.assertGreater(expected % 17, 0)  # tests the old START regression
            self.assertEqual(m.call("mode_next_fixture"), expected)
            def no_sim():
                raise AssertionError("other fixture simulated before MyPlayer's game")
            m.replace_stub(0xC7A20, no_sim)
            m.select(0)
            self.assertEqual(m.top(), 0x51B908)
            self.assertEqual(m.get(0xE576B4), expected // 17)
            self.assertEqual(m.get(0xE576BC), expected % 17)
            self.assertNotIn(0x522828, [m.get(m.manager + 8*i) for i in range(m.depth()+1)])
            self.assertEqual(bytes(m.uc.mem_read(0xE57C40, len(grid))), grid)
            m.frame(0x200)
            m.frame()
            self.assertEqual(m.top(), m.labels["apartment"])

    def test_native_stats_finish_once_award_and_cold_inline_reload(self):
        with Machine(self.payload) as m:
            m.cold(self.roster, self.source)
            live = m.launch()
            m.appearance()
            m.passing_event()
            self.assertEqual([m.value(live, stat, 0) for stat in (35, 4, 76)], [1, 1, 17])
            m.finish()
            self.assertEqual(m.get(m.state + 64), 25)
            watermark = m.get(m.state + 68)
            primary = m.call("primary")
            for bank in (8, 10):
                self.assertEqual([m.value(primary, stat, bank) for stat in (35, 4, 76)], [1, 1, 17])
            for _ in range(3):
                m.call("settle")
                m.frame()
            self.assertEqual(m.get(m.state + 64), 25)
            self.assertEqual(m.get(m.state + 68), watermark)
            m.select(2)
            self.assertEqual(m.top(), 0x535E70)
            m.frame(0x200)
            saved = m.native_save(budget=500000000)
        with Machine(self.payload) as cold:
            cold.cold(self.roster, saved)
            self.assertEqual(cold.get(cold.state + 64), 25)
            self.assertEqual(cold.get(cold.state + 68), watermark)
            for bank in (8, 10):
                self.assertEqual([cold.value(cold.call("primary"), stat, bank) for stat in (35, 4, 76)], [1, 1, 17])
            cold.call("settle")
            self.assertEqual(cold.get(cold.state + 64), 25)

    def test_completed_benched_fixture_has_native_result_and_no_award(self):
        with Machine(self.payload) as m:
            m.cold(self.roster, self.source)
            m.launch()
            m.finish()
            self.assertEqual(m.get(m.state + 64), 0)
            self.assertGreater(m.get(m.state + 68), 0)
            self.assertEqual(m.get(m.state + 196), 0)

    def test_bye_selects_next_own_fixture_and_season_end_dispatches_stage(self):
        # These assertions prove routing at the native operation boundary.
        # The separate long native probe executes the week implementation.
        with Machine(self.payload) as m:
            m.cold(self.roster, self.source)
            grid = bytearray(m.uc.mem_read(0xE57C40, 374 * 8))
            club = m.get(m.state + 56)
            weeks = {i // 17 for i in range(17 * 17) if grid[8*i] < 2 and club in grid[8*i+1:8*i+3]}
            bye = next(w for w in range(17) if w not in weeks)
            for i in range(bye * 17):
                if grid[8*i] < 2:
                    grid[8*i] = 3  # explicit prior-results precondition
            m.uc.mem_write(0xE57C40, bytes(grid))
            m.put(0xE576B4, bye)
            calls = []
            for va in (0x247D40, 0x2480B0):
                m.replace_stub(va, lambda address=va: (calls.append((address, m.reg("ECX"))),
                    m.put(0xE576B4, m.get(0xE576B4) + 1), m.ret()))
            next_slot = m.call('mode_next_fixture')
            m.select(0)
            self.assertEqual(calls, [(0x247D40, m.manager)])
            self.assertEqual(m.top(), 0x51B908)
            self.assertEqual(m.get(0xE576B4) * 17 + m.get(0xE576BC), next_slot)
            self.assertEqual(m.uc.mem_read(0xE57C40, len(grid)), grid)
            m.frame(0x200)
            m.frame()
            self.assertEqual(m.top(), m.labels['apartment'])
            for i in range(374):
                if grid[8*i] < 2:
                    grid[8*i] = 3
            m.uc.mem_write(0xE57C40, bytes(grid))
            m.put(0xE576B4, m.get(0xE576B0))
            m.select(0)
            self.assertEqual(calls[-1], (0x2480B0, m.manager))
            self.assertIn(("notice", "No game pending. Advancing."), m.events)
            self.assertEqual(m.top(), m.labels["apartment"])


if __name__ == "__main__":
    unittest.main()
