"""Every club's defensive play call, checked natively against every situation (b780 n4). Private data only.

Smuzz's freeze (11/02) was the human Patriots on defense at the play-call screen (3-4 page, OFFENSE CHOSE Kings, at
Seattle). ``tools/b77/n4_defense_playcall_sweep.py`` runs, under Unicorn on a disc's own executable and books, the
native code that runs on that screen: the menu models, the CPU defense and offense selectors over the focused
situations and every formation context, the human Coach's Pick with its menu placement, and (``--lineup``) the slot
filler over every personnel category with rested, tired, injured and mixed rosters. Any call that does not return
inside its budget is a loop the game would hang in.

Runs on a SOFTDRINK disc image: ``NFL2K5_N4_SWEEP_DISC`` (default: the released v0.8 disc on this machine). By
default the reporter's clubs (NE, SEA); ``NFL2K5_N4_SWEEP_ALL=1`` runs all 32 clubs with the lineup sweep (about an
hour). Skips when the image or Unicorn is absent."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "tools" / "b77")]

DISC = Path(os.environ.get("NFL2K5_N4_SWEEP_DISC",
                           "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.8 (2026-10-31).xiso.iso"))
ALL = os.environ.get("NFL2K5_N4_SWEEP_ALL") == "1"


class DefensePlayCallSweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("the native sweep needs Unicorn")
        if not DISC.is_file():
            raise unittest.SkipTest("no SOFTDRINK disc image (set NFL2K5_N4_SWEEP_DISC)")
        import n4_defense_playcall_sweep as sweep
        cls.sweep = sweep
        cls.tmp = tempfile.TemporaryDirectory()
        cls.directory = sweep.extract(DISC, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_club_hangs_or_breaks_a_menu_on_its_defensive_play_call(self):
        teams = self.sweep.TEAM_KEYS if ALL else ["NE", "SEA"]
        result = self.sweep.sweep(self.directory, teams, samples=1, lineup=ALL, out=None)
        self.assertEqual([t["team"] for t in result["teams"]], teams)
        for row in result["teams"]:
            with self.subTest(team=row["team"]):
                self.assertEqual(row["menu_problems"], [])
                self.assertGreater(row["selectors"]["cases"], 0)
                self.assertEqual(row["selectors"]["faults"], [])
                self.assertGreater(row["coach_pick"]["cases"], 0)
                self.assertEqual(row["coach_pick"]["faults"], [])
                if ALL:
                    self.assertEqual(row["lineup"]["faults"], [])
        self.assertEqual(result["faults"], 0)


if __name__ == "__main__":
    unittest.main()
