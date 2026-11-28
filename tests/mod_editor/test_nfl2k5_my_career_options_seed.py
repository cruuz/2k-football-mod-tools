"""The MyCareer CPU fixture seeds the game options a real save carries (b81 queue, Q79).

The options block at 0xE5FF80 is BSS that the game fills at boot or copies from a save. The bounded fixture does
neither, so before this seed Quarter Length (0xE6000C) and Sim. Quarter Length (0xE60010) read 0 and every headless
season run on it produced wrong simulated stat lines (MC1's 11/04 audit; the halftime time-of-possession split divides
by the quarter length). The first class runs anywhere (no game files); the second runs the native frontend on the
retail executable when it is present.
"""
from pathlib import Path
import hashlib
import inspect
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_save_writer as save_writer
from tests import nfl2k5_my_career_mode_fixture as fixture
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC


class SeedContractTests(unittest.TestCase):
    def test_seed_names_the_two_quarter_lengths_inside_the_game_ranges(self):
        seed = dict(fixture.Machine.OPTION_SEED)
        quarter_va, quarter_low, quarter_high = save_writer.OPTION_FIELDS["quarter_minutes"]
        sim_va, sim_low, sim_high = save_writer.OPTION_FIELDS["sim_minutes"]
        self.assertEqual(set(seed), {quarter_va, sim_va})
        self.assertTrue(quarter_low <= seed[quarter_va] <= quarter_high)
        self.assertTrue(sim_low <= seed[sim_va] <= sim_high)
        self.assertEqual((seed[quarter_va], seed[sim_va]), (15, 15))   # what real-derived saves carry

    def test_seed_writes_every_pair_through_put(self):
        writes = []

        class Recorder:
            OPTION_SEED = fixture.Machine.OPTION_SEED

            def put(self, va, value):
                writes.append((va, value))

        fixture.Machine.seed_game_options(Recorder())
        self.assertEqual(writes, list(fixture.Machine.OPTION_SEED))

    def test_frontend_seeds_before_any_native_call(self):
        source = inspect.getsource(fixture.Machine.frontend)
        self.assertIn("self.seed_game_options()", source)
        self.assertLess(source.index("self.seed_game_options()"), source.index("self.call("))


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "the pinned USA XBE, the retail ROST and Unicorn are required")
class NativeFrontendSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_my_career_mode as mode
        from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.roster = retail_roster()
        cls.payload = mode.apply(retail)[0]

    def test_frontend_leaves_real_quarter_lengths_for_the_game(self):
        with fixture.Machine(self.payload) as m:
            self.assertEqual((m.get(0xE6000C), m.get(0xE60010)), (0, 0))   # BSS before the seed
            m.frontend(self.roster)
            self.assertEqual((m.get(0xE6000C), m.get(0xE60010)), (15, 15))
            # The native menu stack still opens MyCareer on the seeded state.
            m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
            m.select(1)
            self.assertEqual(m.top(), m.labels["entry_menu"])
            self.assertEqual((m.get(0xE6000C), m.get(0xE60010)), (15, 15))


if __name__ == "__main__":
    unittest.main()
