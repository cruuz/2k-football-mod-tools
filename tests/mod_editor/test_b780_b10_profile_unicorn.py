"""b780 b10-profile: the game's own code reads what Studio writes (Unicorn replays of the pinned USA retail executable).

* The options loader ``FUN_000E2E20`` (the one routine every Settings and franchise load goes through) copies a
  Studio-edited 0x2E0-byte block over the live options; the live Quarter Length, Sim. Quarter Length and Chop Block then read
  the new values, on the retail executable and on one carrying the new defaults.
* The champions page (the honors owner's third Player Card page, ``tools/nfl2k5_champions/runtime.c``) draws the seasons that
  Franchise > Upgrade merged into a save's history block, and the game's own Super Bowl recorder extends that block.

Boundaries: Unicorn runs the real routines on synthetic RAM (no boot, renderer or save device), so these are not in-game
results.  The tests skip without the private pinned retail ``default.xbe``.  Run them through the machine-wide test slot.
"""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_champions as champions  # noqa: E402
from mod_editor.core import nfl2k5_champions_history as history  # noqa: E402
from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from mod_editor.core import nfl2k5_option_defaults as defaults  # noqa: E402
from mod_editor.core import nfl2k5_profile_defaults as profile  # noqa: E402
from tests.mod_editor import test_b779_hn1_champions as hn1  # noqa: E402
from tests.mod_editor.test_b780_b10_profile_defaults import NEW, settings_save  # noqa: E402
from tests.mod_editor.test_b780_b10_upgrade_gaps import recorded  # noqa: E402
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC  # noqa: E402

BLOCK, BLOCK_SIZE = 0xE5FF80, 0x2E0
QUARTER, SIM, CHOP = 0xE6000C, 0xE60010, 0xE60064
REAL_SETTINGS = Path(os.environ.get("B780_B10_SETTINGS", ""))
REAL_FRANCHISE = Path(os.environ.get("B780_B10_V07", ""))


def retail_bytes():
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes as _retail
    return _retail()


@unittest.skipUnless(HAVE_UC, "unicorn is not installed")
class OptionsLoaderTests(unittest.TestCase):
    """A saved profile wins over any default; Studio's edit is therefore what the game plays with."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.patched = defaults.apply(cls.retail)[0]

    def load(self, xbe, stored):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = Machine(xbe, trace_writes=False)
        m.call(0x77D20, budget=2_000_000, stop=0x77D45)               # the boot initializer: a fresh profile's defaults
        buffer = m.ARENA + 0x1000
        m.uc.mem_write(buffer, bytes(stored))
        m.call(0xE2E20, ecx=buffer)                                    # FUN_000E2E20: the options loader every save load uses
        return m, bytes(m.uc.mem_read(BLOCK, BLOCK_SIZE))

    def test_a_studio_edited_settings_save_loads_as_7_15_on(self):
        old = settings_save()                                          # 5 / 5 / Off, a profile saved before the new defaults
        new, rows = profile.edit(old, profile.values_from_plan(profile.plan(old, NEW)))
        self.assertEqual(len(rows), 3)
        for label, xbe in (("retail executable", self.retail), ("executable with the new defaults", self.patched)):
            with self.subTest(label):
                m, _live = self.load(xbe, old)
                self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (5, 5, 0))   # the old save still plays 5 / 5 / Off
                m, live = self.load(xbe, new)
                self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (7, 15, 1))
                self.assertEqual(live, new)                            # the loader copied all 0x2E0 bytes of the edited block

    def test_a_player_choice_survives_the_edit_and_the_loader(self):
        old = settings_save(10, 5, 0)
        new, _rows = profile.edit(old, profile.values_from_plan(profile.plan(old, NEW)))
        m, live = self.load(self.patched, new)
        self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (10, 15, 1))
        self.assertEqual(live, new)

    def test_only_the_three_dwords_differ_in_the_live_block(self):
        old = settings_save()
        new, _rows = profile.edit(old, {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})
        _m, before = self.load(self.retail, old)
        _m, after = self.load(self.retail, new)
        changed = {BLOCK + i for i in range(0, BLOCK_SIZE, 4) if before[i:i + 4] != after[i:i + 4]}
        self.assertEqual(changed, {QUARTER, SIM, CHOP})

    @unittest.skipUnless(REAL_SETTINGS.is_file(), "a real game-written Settings1 is not named in B780_B10_SETTINGS")
    def test_a_real_game_written_profile(self):
        old = REAL_SETTINGS.read_bytes()
        new, rows = profile.edit(old, profile.values_from_plan(profile.plan(old, NEW)))
        self.assertEqual(len(rows), 3)
        m, live = self.load(self.retail, new)
        self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (7, 15, 1))
        self.assertEqual(live, new)

    @unittest.skipUnless(REAL_FRANCHISE.is_file(), "a real game-written franchise is not named in B780_B10_V07")
    def test_a_franchise_prefix_loads_through_the_same_routine(self):
        # a franchise save starts with the same 0x2E0-byte block; its loaders call FUN_000E2E20 on that prefix
        franchise = REAL_FRANCHISE.read_bytes()
        new, rows = profile.edit(franchise, profile.values_from_plan(profile.plan(franchise, NEW)))
        self.assertEqual(len(rows), 3)
        m, live = self.load(self.retail, new[:BLOCK_SIZE])
        self.assertEqual((m.get(QUARTER), m.get(SIM), m.get(CHOP)), (7, 15, 1))
        self.assertEqual(live, new[:BLOCK_SIZE])


ABBREVIATIONS = ("SF", "CHI", "CIN", "BUF", "DEN", "CLE", "TB", "ARI", "LAC", "KC", "IND", "DAL", "MIA", "PHI", "ATL", "NYG",
                 "JAX", "NYJ", "DET", "GB", "CAR", "NE", "LV", "LAR", "BAL", "WAS", "NO", "SEA", "PIT", "HOU", "TEN", "MIN")


@unittest.skipUnless(hn1.XBE.is_file() and HAVE_UC, "pinned USA XBE and unicorn required")
class ChampionsPageTests(unittest.TestCase):
    """The seasons Upgrade merges into a save are the seasons the game's Player Card page draws."""

    @classmethod
    def setUpClass(cls):
        hn1.NativeTests.setUpClass()
        cls.helper = hn1.NativeTests("test_a_block_written_by_the_studio_reads_back_and_is_extended")
        cls.seed = history.seeded_block()

    def machine(self):
        m = self.helper.machine()
        m.record(hn1.RETIRE, "retirement pass")
        self.clubs(m)
        return m

    @staticmethod
    def clubs(m, skip=()):
        """The 32 clubs in the arena's own order (the helper's season() builds its own pair; leave those alone)."""
        for index, abbr in enumerate(ABBREVIATIONS):
            if index not in skip:
                m.club(index, f"City{index}", f"Nick{index}", abbr)
        m.wire(None)

    @staticmethod
    def expected(rows):
        """The text the page shows for each season row, newest first (hn1 layout: year club pts-pts club  NAME, POS)."""
        lines = []
        for row in rows:
            text = (f"{row['super_bowl'] + 1965} {ABBREVIATIONS[row['champion']]} {row['champion_points']}-"
                    f"{row['runner_up_points']} {ABBREVIATIONS[row['runner_up']]}")
            mvp = row["super_bowl_mvp"]
            if mvp:
                text += f"  {mvp['last']}, {mvp['position']}"
            lines.append(text)
        return lines

    def test_the_seeded_seasons_are_drawn_newest_first(self):
        m = self.machine()
        merged, _info = history.merge_blocks(None, self.seed, 60)
        m.uc.mem_write(m.GAP, merged)
        rows = m.history()
        self.assertEqual([r["super_bowl"] for r in rows], list(range(60, 38, -1)))     # the game's reader accepts the block
        calls, text = self.helper.draw_card(m, 2)
        self.assertEqual(calls, ["header", "photo", "model"])
        drawn = [t[0] for t in text[:6]]
        self.assertEqual(drawn, self.expected(rows[:6]))
        self.assertEqual(drawn[0], "2025 SEA 29-13 NE  WALKER, HB")                    # Super Bowl LX
        self.assertIn("1-6 OF 22  UP/DOWN", [t[0] for t in text])                       # six at a time, 22 in all

    def test_a_season_the_game_recorded_is_extended_not_replaced(self):
        m = self.machine()
        self.helper.season(m, winner=27, loser=21, high=31, low=24, season_index=0)    # the 2026 season: Super Bowl 61
        self.clubs(m, skip=(27, 21))
        m.call(self.helper.champ["champions_advance"])
        own = bytes(m.uc.mem_read(m.GAP, history.USED))
        self.assertEqual([r["super_bowl"] for r in m.history()], [61])                 # the game wrote one season
        merged, info = history.merge_blocks(own, self.seed, 61)
        self.assertEqual((info["kept"], info["added"][0], info["added"][-1]), ([61], 40, 60))
        m.uc.mem_write(m.GAP, merged)
        rows = m.history()
        self.assertEqual([r["super_bowl"] for r in rows], list(range(61, 39, -1)))
        _calls, text = self.helper.draw_card(m, 2)
        drawn = [t[0] for t in text[:6]]
        self.assertEqual(drawn[1], "2025 SEA 29-13 NE  WALKER, HB")
        self.assertEqual(drawn[0].split()[0], "2026")
        self.assertEqual([r["season_mvp"] and r["season_mvp"]["last"] for r in rows[:2]], ["STAFFORD", None])
        # the next Super Bowl the game plays is written into the merged ring the way it extends its own
        self.helper.season(m, winner=3, loser=9, high=27, low=20, season_index=1)
        self.clubs(m, skip=(3, 9))
        m.call(self.helper.champ["champions_advance"])
        self.assertEqual([r["super_bowl"] for r in m.history()][:3], [62, 61, 60])
        self.assertEqual(len(m.history()), 22)

    def test_an_edited_ring_with_a_foreign_checksum_reads_as_empty_not_as_wrong_champions(self):
        m = self.machine()
        merged, _info = history.merge_blocks(None, self.seed, 60)
        broken = bytearray(merged)
        broken[40] ^= 0x01                                              # one season's byte changed after the checksum
        m.uc.mem_write(m.GAP, bytes(broken))
        self.assertEqual(m.history(), [])                              # the Python model and the game agree it is unreadable
        _calls, text = self.helper.draw_card(m, 2)
        self.assertFalse([t for t in text if t[0].startswith("20")])


if __name__ == "__main__":
    unittest.main()
