"""nl1: MyCareer with Noah's pad in port 2, Team Select side choice, Practice exit and the draft notice.

Noah's 2026-10-17 video (i4 disc 33fcb403, before mc2): in Practice he could not hike, see play art or
"choose a side", could not leave MyCareer, and asked for a "You were drafted by the Cowboys" pop-up.
mc2 (on the RC) gives MyPlayer the port that drives the menus and adds B to quit. These bounded native
fixtures run the RC's MyCareer owner on the pinned USA executable with the native controller-side
widget LIVE (side words 0xE5FE88 + 28 * port, the per-port Team Select mover 0xEE190 and its
initializers 0xED5E0/0xED540), which the older route fixtures stub. Only textures and sounds are
seams. No game boot, display or physical controller; nothing here is a played match.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_supersim_draft_fixture import retail_bytes
from tests.nfl2k5_my_career_played_fixture import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster

PRACTICE_TEAM_SELECT, GAME_TEAM_SELECT, GAME = 0x5275F8, 0x51B908, 0x4E7EC0
PAUSE, QUIT_MENU = 0x4E9078, 0x4E8D70
SIDES = 0xE5FE88  # native controller side per port: 0 centre, 1 home, 2 away
RIGHT, LEFT = 0x8000000, 0x4000000  # Team Select mover bits from 70A10: centre->home, centre->away
PORT2 = 1


def side(m, port):
    return m.get(SIDES + 28 * port)


def text_at(m, pointer, limit=120):
    raw = bytes(m.uc.mem_read(pointer, 2 * limit))
    end = next(i for i in range(0, len(raw), 2) if raw[i:i + 2] == b'\0\0')
    return raw[:end].decode('utf-16le')


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST and Unicorn required')
class Port2SideAndExitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload, cls.roster = mode.apply(retail_bytes())[0], retail_roster()

    def career(self, m, position=0):
        p = m.create(self.roster, position=position, preseason=False)
        m.child_services()
        return p

    def pad(self, m, port):
        """Noah's case: one pad in port 2. Port 1 stays connected but idle (as on his desktop)."""
        # Connected, and (offline, natively always true) eligible for the in-game pause check.
        for va in (0x709B0, 0x128670, 0x131A10):
            m.replace_stub(va, lambda: m.ret(int(m.reg('ECX') in (0, port))))
        for va in (0xF3750, 0xF3780, 0xF3720):
            m.replace_stub(va, lambda: m.ret(m.inputs if m.reg('EDX') == port else 0, pop=4))
        for va in (0x70A10, 0x70A30, 0x709F0):
            m.replace_stub(va, lambda: m.ret(m.inputs if m.reg('ECX') == port else 0))

    def live_sides(self, m):
        """Run the native side widget instead of the route fixtures' stubs; textures and sounds are seams."""
        for va in (0x77200, 0x771F0, 0xED5E0, 0xED540):
            m.replace_stub(va, None)
        m.replace_stub(0x449E0, lambda: m.ret(0, pop=4))  # texture lookup by name
        m.replace_stub(0xED360, lambda: m.ret())  # menu move sound
        # The mover animates over 0.15 s of frame time read from the manager (+0x104).
        m.uc.mem_write(m.manager + 0x104, struct.pack('<f', 1.0))

    def move(self, m, bits):
        m.frame(bits)
        m.frame()  # one frame to finish the 0.15 s slide

    def test_practice_team_select_puts_port2_on_myplayer_side_and_it_can_move(self):
        with Machine(self.payload) as m:
            self.career(m)  # QB: Free Practice starts with his club at home on offense
            self.pad(m, PORT2)
            self.live_sides(m)
            m.select(1)  # Practice row, A from port 2
            self.assertEqual(m.top(), m.labels['practice_menu'])
            self.assertEqual(m.get(m.state + 32), PORT2)  # mc2: MyPlayer belongs to port 2
            self.assertEqual(m.call(0x77B00), m.get(m.state + 2588))  # his club is the home side
            m.frame(0x10)  # START from port 2
            self.assertEqual(m.top(), PRACTICE_TEAM_SELECT)
            # Native Team Select (2C1950) seats the port that pressed START on the home side, his club.
            # Its mover widget starts centred (retail behaviour), so the first push lands on a side.
            self.assertEqual((side(m, 0), side(m, PORT2)), (0, 1))
            self.assertEqual((m.get(0xB9C4A0), m.get(0xB9C4A4), m.get(0xB9C4A8)), (1, 1, 0))  # both sides open
            reached = []
            for bits, expected in ((LEFT, 2), (RIGHT, 0), (RIGHT, 1), (LEFT, 0), (LEFT, 2), (RIGHT, 0), (RIGHT, 1)):
                self.move(m, bits)
                self.assertEqual(side(m, PORT2), expected, hex(bits))
                self.assertEqual(side(m, 0), 0)  # the idle port 1 never moves
                reached.append(expected)
            self.assertEqual(set(reached), {0, 1, 2})  # port 2 can choose either side or neither
            m.frame(0x10)  # START from port 2 launches the practice rep
            self.assertEqual(m.top(), GAME)
            self.assertEqual(m.get(m.state + 32), PORT2)

    def test_practice_pause_quit_from_port2_returns_to_the_apartment(self):
        with Machine(self.payload) as m:
            self.career(m)
            self.pad(m, PORT2)
            self.live_sides(m)
            balance, home = m.get(m.state + 64), m.depth()
            m.select(1)
            m.frame(0x10)
            self.assertEqual(m.top(), PRACTICE_TEAM_SELECT)
            m.frame(0x10)
            self.assertEqual(m.top(), GAME)
            m.frame(0x10)  # START from port 2 pauses
            self.assertEqual(m.top(), PAUSE)
            m.select(12)  # Quit
            self.assertEqual(m.top(), QUIT_MENU)
            m.select(2)  # Quit practice
            m.frame()
            self.assertEqual((m.top(), m.depth()), (m.labels['apartment'], home))
            self.assertEqual(m.get(m.state + 64), balance)
            # And B on the Apartment (mc2) then leaves MyCareer through the native question.
            m.dialog_answer = 2
            m.frame(0x200)
            self.assertEqual((m.depth(), m.top()), (0, 0x515660))
            self.assertEqual(m.get(m.state + 2672), 0)

    def test_play_next_game_team_select_puts_port2_on_his_club_and_keeps_the_cpu_side_closed(self):
        with Machine(self.payload) as m:
            self.career(m)
            self.pad(m, PORT2)
            self.live_sides(m)
            m.dialog_answer = 0
            m.select(0)  # Play next game, A from port 2
            self.assertEqual(m.top(), GAME_TEAM_SELECT)
            self.assertEqual(m.get(m.state + 32), PORT2)
            club = m.get(m.state + 2588)
            mine = 1 if m.call(0x77B00) == club else 2
            self.assertEqual(m.call(0x77B40 if mine == 1 else 0x77B00) != club, True)
            # The native Franchise launch (C73B0) seats MyPlayer's port on his club's side.
            self.assertEqual((side(m, 0), side(m, PORT2)), (0, mine))
            # He can step to the centre and back. The CPU club's side stays closed, as in retail Franchise.
            toward_centre, toward_other = (LEFT, LEFT) if mine == 1 else (RIGHT, RIGHT)
            back = RIGHT if mine == 1 else LEFT
            self.move(m, toward_centre)
            self.assertEqual(side(m, PORT2), 0)
            self.move(m, toward_other)
            self.assertEqual(side(m, PORT2), 0)
            self.move(m, back)
            self.assertEqual(side(m, PORT2), mine)
            m.frame(0x10)
            self.assertEqual(m.top(), GAME)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, signed f0 and Unicorn required')
class DraftedNoticeTests(unittest.TestCase):
    """Noah: "It would be nice if there was a little pop-up, like 'You were drafted by the Cowboys.'"."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import signed_save
        from mod_editor.core import nfl2k5_draft_ai as ai
        signed_save()  # precise private-evidence skip comes from the fixture
        cls.payload = mode.apply(ai.apply(retail_bytes())[0])[0]
        cls.roster = retail_roster()

    def notices(self, m):
        seen = []

        def notice():
            seen.append((text_at(m, m.reg('EDX')), m.top()))
            m.ret()
        m.replace_stub(0x14E520, notice)
        return seen

    def test_drafted_player_is_told_his_club_by_full_name_once_on_the_apartment(self):
        from tests.nfl2k5_my_career_draft_fixture import Machine as DraftMachine
        with DraftMachine(self.payload) as m:
            m.prepare_draft(self.roster, ratings=99)
            seen = self.notices(m)
            club = m.draft()
            self.assertLess(club, 32)
            self.assertEqual(m.get(m.state + 24), 3)
            team = m.get(m.state + 2588)
            self.assertEqual(team, m.get(m.root + 0x1C) + 500 * club)
            city, nickname = text_at(m, m.get(team + 0x138)), text_at(m, m.get(team + 0x104))
            self.assertTrue(city and nickname)
            drafted = [s for s in seen if s[0].startswith('You were drafted by the ')]
            self.assertEqual(drafted, [(f'You were drafted by the {city} {nickname}.', m.labels['apartment'])])
            self.assertEqual(m.top(), m.labels['apartment'])

    def test_undrafted_player_gets_only_the_existing_sign_notice(self):
        from tests.nfl2k5_my_career_draft_fixture import Machine as DraftMachine
        with DraftMachine(self.payload) as m:
            m.prepare_draft(self.roster, ratings=0, position=1, preseason=False)
            seen = self.notices(m)
            self.assertEqual(m.draft(), 0xFFFFFFFF)
            self.assertEqual([s[0] for s in seen], ['Undrafted. Choose a club and sign.'])
            self.assertEqual(m.top(), m.labels['team_menu'])

    def test_no_club_names_means_no_notice(self):
        with Machine(self.payload) as m:
            m.frontend(self.roster)
            seen = self.notices(m)
            for city, nickname in ((0, 1), (1, 0), (0, 0)):
                team = 0x2A10000
                m.uc.mem_write(team, bytes(500))
                m.put(team + 0x138, 0x2A10200 if city else 0)
                m.put(team + 0x104, 0x2A10240 if nickname else 0)
                m.put(m.state + 2588, team)
                m.call('drafted', ecx=m.manager, eax=m.manager)
            m.put(m.state + 2588, 0)
            m.call('drafted', ecx=m.manager, eax=m.manager)
            self.assertEqual(seen, [])

    def test_the_format_lives_in_the_m3_ascii_pool(self):
        _, labels = mode.code_for(0x400000, 0x500000)
        self.assertIn('m3_drafted_format', mode.POOLED2)
        self.assertGreaterEqual(labels['m3_drafted_format'], mode.EXTRA_VA + 2160)
        self.assertLess(labels['m3_drafted_format'], mode.EXTRA_VA + 2700)
        for grades in (False, True):
            _, labels = mode.code_for(0x400000, 0x500000, letter_grades=grades)
            self.assertLessEqual(labels['content_end'] - 0x400000, mode.TAG_OFFSET)


if __name__ == '__main__':
    unittest.main()
