"""mc1 (b780): two MyCareer long-flow faults found by the MC1 long runs (Noah 11/03: "MyCareer also needs some serious
testing for bugs, because most people haven't played through that very far").

A. MyPlayer without a club. When his club releases him (its cut-down 0x2BF9A0) or his contract runs out, start_player's
   resolve_team leaves the club index S(56) at -1 and the career state S(24) at 4. mode_play returned at once, so
   Play next game, Sim to next appearance and Start MyPlayer all did nothing, with no notice, and the league could not
   advance: the career was stuck at Career Home. Only a Save and a reload got the player out, because mode_loaded sends
   such a career to Choose team / Sign. Play next game now opens that same screen.
B. A career saved on a later draft day. mode_loaded sent every career loaded at stage 5 to the MyCareer draft screen,
   which runs the league's draft pick by pick and then says "You were drafted by" MyPlayer's own club again. Only a
   prospect (S(24) = 2) resumes his own draft now; a player already on a club loads into Career Home.

C. Checked, no change: the career club's depth chart. A static reading (HUNT6) was that the weekly auto-depth 0x2BDCF0
   never sorts the MyCareer club, because MyCareer marks it human ([0xE5775C + club*4] = 1) and the sort skips a human
   club unless "CPU manages my depth chart" [0xE60140] is on (the setup defaults 0x148C60 clear it). The sort asks
   0x13EC30, which is MyCareer's own hook of 0xC4D50 and answers CPU for the career club, so the club is sorted every
   week whatever [0xE60140] holds: a clearly better bench player starts, and Play next game still starts MyPlayer.

Unicorn, the pinned USA retail executable with the MyCareer and Career Home owners and the retail ROST: the game's own
Create Player, signing, cut-down, Career Home rows, save (16E3F0) and load (16E540, 16DD30). Negative control (MC1
report): the A and B tests against the pre-fix runtime, installed by the same mode.apply, both fail (Play next game
leaves the released career on Career Home; the stage-5 load opens the draft screen); the MC1 driver shows the same on
the v0.9 RC executable. EXPERIMENTAL / UNWITNESSED in game.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode  # noqa: E402
from mod_editor.core import nfl2k5_my_career_home as home  # noqa: E402
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC  # noqa: E402

STAGE, WEEK, YEAR = 0xE576A4, 0xE576B4, 0xE576B8
TEAM_SELECT = 0x51B908
SRC = (ROOT / 'tools/mycareer_mode/runtime.c').read_text()


class SourceTests(unittest.TestCase):
    def test_play_next_game_opens_the_club_choice_without_a_club(self):
        body = SRC[SRC.index('void FC mode_play(u32 manager) {'):SRC.index('void FC mode_sim_appearance')]
        self.assertIn('if(S(56)>=32) { CALL2(0x6e390,manager,mode_loaded(manager,0)); return; }', body)
        self.assertNotIn('    if(S(56)>=32) return;\n', body)

    def test_only_a_prospect_resumes_the_draft_on_load(self):
        body = SRC[SRC.index('u32 FC mode_loaded(u32 manager,u32 target) {'):SRC.index('void mode_load_error')]
        self.assertIn('if(G(0xE576A4)==5 && S(24)==2) return (u32)m3_draft_menu;', body)
        self.assertNotIn('if(G(0xE576A4)==5) return', body)


def release(m, player, club):
    """Make MyPlayer the weakest at his position, then run the club's own cut-down 0x2BF9A0 until he is released."""
    from mod_editor.core.nfl2k5_my_career_progression import FIELDS
    for field, _, _ in FIELDS:
        m.uc.mem_write(player + field, b'\x01')
    team = m.get(m.get(0xB72918) + 0x1C) + 500 * club
    for _ in range(12):
        count = m.uc.mem_read(team + 0x11C, 1)[0]
        if player not in [m.get(team + 4 * i) for i in range(count)]:
            break
        m.call(0x2BF9A0, ecx=team, edx=count - 1, budget=2000000000)
    m.call('resolve_team', budget=50000000)
    return team


def members(m, player):
    root = m.get(0xB72918)
    out = []
    for club in range(32):
        team = m.get(root + 0x1C) + 500 * club
        out += [club for i in range(m.uc.mem_read(team + 0x11C, 1)[0]) if m.get(team + 4 * i) == player]
    return out


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST and Unicorn required')
class LongFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        cls.payload = home.apply(mode.apply(retail_bytes())[0])[0]
        cls.roster = retail_roster()

    def machine(self, club=15):
        from tests.nfl2k5_my_career_home_fixture import Machine
        m = Machine(self.payload)
        player = m.create(self.roster, club=club, position=0, preseason=False)
        m.child_services()
        return m, player

    def test_a_released_myplayer_signs_again_from_play_next_game(self):
        m, player = self.machine()
        with m:
            release(m, player, 15)
            self.assertEqual(members(m, player), [])
            self.assertEqual((m.get(m.state + 24), m.get(m.state + 56)), (4, 0xFFFFFFFF))
            self.assertEqual(m.top(), m.labels['apartment'])
            before = [m.get(va) for va in (STAGE, WEEK, YEAR)]
            m.select(0, budget=200000000)            # Play next game
            self.assertEqual(m.top(), m.labels['team_menu'], 'the club choice opens instead of nothing')
            self.assertEqual(m.get(m.state + 2680), 2)
            self.assertEqual([m.get(va) for va in (STAGE, WEEK, YEAR)], before, 'no league step without a club')
            m.frame(0x200, budget=100000000)         # B: back to Career Home, MyCareer stays open
            self.assertEqual(m.top(), m.labels['apartment'])
            m.select(0, budget=200000000)            # Play next game again
            self.assertEqual(m.top(), m.labels['team_menu'])
            m.select(0, budget=200000000)            # Choose team
            m.select(3, budget=200000000)            # Buffalo
            self.assertEqual((m.top(), m.get(m.state + 2684)), (m.labels['team_menu'], 3))
            m.select(1, budget=2000000000)           # Sign, the native Yes
            self.assertEqual(m.top(), m.labels['apartment'])
            self.assertEqual((m.get(m.state + 24), m.get(m.state + 56)), (3, 3))
            self.assertEqual(members(m, player), [3])
            self.assertEqual(m.call('primary'), player)
            m.select(0, budget=2000000000)           # the career goes on: his next game
            self.assertEqual(m.top(), TEAM_SELECT)

    def test_a_veteran_saved_on_draft_day_loads_into_career_home(self):
        m, player = self.machine()
        with m:
            # Declared precondition: the league's draft day (stage 5) with MyPlayer on his club, as Play next game
            # leaves a veteran career after the stage-4 advance. The save and the load are the game's own.
            m.put(STAGE, 5)
            self.assertEqual(m.get(m.state + 24), 3)
            saved = m.native_save(budget=500000000)
        from tests.nfl2k5_my_career_played_fixture import Machine
        with Machine(self.payload) as cold:
            cold.cold(self.roster, saved)
            self.assertEqual(cold.get(STAGE), 5)
            self.assertEqual(cold.top(), cold.labels['apartment'], 'not the MyCareer draft screen')
            self.assertEqual(cold.get(cold.state + 24), 3)
            self.assertEqual(cold.get(cold.state + 56), 15)


    def depth(self, m):
        """record -> (club, position, rank, side, lock byte +0x52) for every club. The weekly sort exchanges the
        team's slot pointers, so a player is followed by his record, not by his slot."""
        root = m.get(0xB72918)
        out = {}
        for club in range(32):
            team = m.get(root + 0x1C) + 500 * club
            for i in range(m.uc.mem_read(team + 0x11C, 1)[0]):
                q = m.get(team + 4 * i)
                w = struct.unpack('<H', m.uc.mem_read(q + 0x28, 2))[0]
                out[q] = (club, m.uc.mem_read(q + 0x35, 1)[0], (w >> 10) & 7, (w >> 13) & 7,
                          m.uc.mem_read(q + 0x52, 1)[0])
        return out

    def weekly_depth(self, managed):
        """The game's weekly auto-depth 0x2BDCF0 (the first call of the week 0x247D40) after a Giants receiver on
        the bench is made clearly the best (ratings 99). managed=None keeps [0xE60140] as MyCareer leaves it."""
        from mod_editor.core.nfl2k5_my_career_progression import FIELDS
        m, player = self.machine()
        setting = m.get(0xE60140)
        if managed is not None:
            m.put(0xE60140, int(managed))
        team = m.get(m.get(0xB72918) + 0x1C) + 500 * 15
        cpu = m.call(0x13EC30, ecx=team, budget=2000000)
        before = self.depth(m)
        rank, key = max((v[2], k) for k, v in before.items() if v[0] == 15 and v[1] == 3)
        for field, _, _ in FIELDS:
            m.uc.mem_write(key + field, bytes((99,)))
        m.call(0x2BDCF0, budget=2000000000)
        after = self.depth(m)
        m.call('primary', budget=200000000)
        m.call('start_player', budget=200000000)    # what Play next game does first
        played = self.depth(m)
        m.close()
        return setting, cpu, before, after, played, key, player

    def test_the_weekly_depth_pass_sorts_the_career_club(self):
        setting, cpu, before, after, played, key, mine = self.weekly_depth(None)
        self.assertEqual(setting, 0, 'MyCareer leaves "CPU manages my depth chart" off')
        self.assertEqual(cpu, 0, "MyCareer's 0xC4D50 hook answers CPU for the career club")
        self.assertGreater(before[key][2], 0)
        self.assertEqual(after[key][2], 0, 'the clearly better receiver starts after the weekly pass')
        self.assertEqual(after[mine][4], before[mine][4], "MyPlayer's lock byte is kept")
        self.assertEqual(played[mine][2:4], (0, 0), 'Play next game still starts MyPlayer')
        _, _, _, on_after, _, _, _ = self.weekly_depth(True)
        self.assertEqual(on_after, after, 'the same charts with the setting on: it does not gate the career club')

if __name__ == '__main__':
    unittest.main()
