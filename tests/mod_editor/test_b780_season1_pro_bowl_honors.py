"""b780-season1 (Q73): franchise seasons award Pro Bowl honors from the game's own Pro Bowl selection.

When the postseason starts the game fills its AFC and NFC all-star clubs (roster abbreviations "AFC" and "NFC", 40
players each; HUNT1's simulated 2026 season on the v0.9 RC: 3 QB, 6 WR, 2 TE, 3 T, 3 G, 2 C, 2 HB, 2 FB, 3 DE, 3 DT,
3 ILB, 3 CB, 2 FS, 1 SS, 1 K, 1 P per conference). At Advance to offseason the champions owner now gives every one of
them the season's Pro Bowl honor (honors field 103, the Player Card's Pro Bowl count), once. The real champions code runs
under Unicorn (the champions harness of test_b779_hn1_champions); the game's history writer is recorded.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_champions as champions  # noqa: E402
from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from tests.mod_editor.test_b779_hn1_champions import AWARDS, CLASS, HAVE_UC, LeagueMachine, RETIRE, XBE, _retail  # noqa: E402

HIST_SET = 0x14F430
PRO_BOWL_FIELD = 96 + 7                     # honors FIELD0 + H_PB


@unittest.skipUnless(XBE.is_file() and HAVE_UC, "pinned USA XBE and unicorn required")
class ProBowlHonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = _retail()
        if retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.patched, _ = honors.apply(retail)
        cls.champ = champions.labels(champions.allocations(cls.patched)["code"]["va"])

    def season(self, *, mode=2, pro_bowl=True):
        m = LeagueMachine(self.patched)
        m.reserve_block()
        m.record(RETIRE, "retirement pass")
        writes = []

        def hist_set(machine):
            writes.append((machine.reg("ECX"), machine.reg("EDX"), machine.get(machine.reg("ESP") + 4),
                           machine.get(CLASS)))
            return 0
        m.hook(HIST_SET, hist_set, pop=4)
        m.hook(0x14EDB0, lambda machine: machine.put(CLASS, machine.reg("ECX")))    # the class setter
        players = m.roster([(5, []) for _ in range(9)])
        m.club(4, "Seattle", "Seahawks", "SEA", players[:2])
        m.club(9, "New England", "Patriots", "NE", players[2:3])
        if pro_bowl:
            m.club(49, "AFC", "AFC", "AFC", [players[2], players[3], players[4]])
            m.club(50, "NFC", "NFC", "NFC", [players[0], players[5]])
        m.club(51, "NFL", "NFL", "NFL", players[6:9])                     # an all-time club is not a Pro Bowl
        m.club(43, "FW", "FW Alumni", "AFW", players[7:9])
        for i, p in enumerate(players):
            m.person(p, "First", f"Player{i}", "QB")
        m.wire(players)
        m.put(0xE576A0, mode)
        m.set_year(0)
        m.super_bowl(4, 9, 31, 24)
        m.put(AWARDS + 0x5888, players[0])
        m.put(AWARDS + 0x5800, players[1])
        m.put(AWARDS + 0x5804, m.team_ptr(4))
        m.put(CLASS, 1)                                                     # the postseason class at the advance
        m.call(self.champ["champions_advance"])
        return m, players, writes

    def test_every_selected_player_gets_one_pro_bowl_in_the_regular_season_class(self):
        m, players, writes = self.season()
        selected = [players[2], players[3], players[4], players[0], players[5]]
        self.assertEqual([w[0] for w in writes], selected)
        self.assertEqual({(w[1], w[2], w[3]) for w in writes}, {(PRO_BOWL_FIELD, 1, 0)})
        self.assertEqual(m.get(CLASS), 1)                                   # the class is restored
        self.assertEqual(m.calls[-2:], ["notice", "retirement pass"])       # the notice and the retail pass still run
        self.assertIn("won Super Bowl LXI", m.notices[0][1])

    def test_nothing_outside_a_franchise_or_without_selected_clubs(self):
        _m, _players, writes = self.season(mode=1)
        self.assertEqual(writes, [])
        _m, _players, writes = self.season(pro_bowl=False)
        self.assertEqual(writes, [])

    def test_the_champions_code_still_fits_its_owner(self):
        self.assertLessEqual(len(champions.runtime.CODE), champions.CODE_SIZE)


if __name__ == "__main__":
    unittest.main()
