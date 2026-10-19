"""mcs: the Career Home Schedule screen (Noah 2026-10-18: "it would be nice if we had a schedule we could look at").

Static: the Schedule row and descriptor, the week rows for both season lengths, every label address independent of
the season length (MyCareer's Apartment words included), the section geometry and MyCareer's spare.
Native (Unicorn, pinned USA XBE, retail ROST/FONT/LAYT/MRKS): Schedule opens from Career Home with the cursor on
this week, the cards follow the native list's scrolling, results and scores come from the league grid (a natively
simulated week and exact written results), bye / no game / TBD rows, A stays, B returns, Play next game still
reaches Team Select. No game boot, display, xemu or controller.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_my_career_home as home
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_supersim_draft_fixture import retail_bytes

TEAM_SELECT = 0x51B908
DOWN, UP, A, B = 0x02000000, 0x01000000, 0x100, 0x200
GRID, SCORES = 0xE57C40, 0xE587F0
PLAYOFFS = ['Wild Card', 'Divisional', 'Conference', 'Super Bowl']
CARDS = (290, 72, 620, 358)   # x0, y0, x1, y1 of the cards and scroll bar (HUD text space)


def weeks(n):
    return [f'Week {i}' for i in range(1, n + 1)] + PLAYOFFS


@unittest.skipUnless(XBE.is_file(), 'pinned USA XBE required')
class ScheduleStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_season_length as season
        cls.career17 = mode.apply(retail_bytes())[0]
        cls.p17 = home.apply(cls.career17)[0]
        cls.p18 = home.apply(mode.apply(season.apply(retail_bytes())[0])[0])[0]

    def test_rows_follow_the_season_length(self):
        for payload, n in ((self.p17, 17), (self.p18, 18)):
            with self.subTest(weeks=n):
                self.assertEqual(home.season_weeks(payload), n)
                self.assertEqual(home.status(payload), 'applied')
                receipt = home.check_static(payload)
                self.assertEqual(receipt['rows']['home_schedule'], weeks(n))
                self.assertEqual(receipt['descriptors']['home_schedule'], 'Season Schedule')
                self.assertEqual(receipt['rows']['apartment'][:2], ['Play next game', 'Schedule'])
                self.assertEqual(len(receipt['rows']['apartment']), home.MAX_VISIBLE_ROWS)
                self.assertGreaterEqual(receipt['mycareer_spare_bytes'], 0)
                self.assertGreater(receipt['spare_bytes'], 1024)
                self.assertEqual(home.apply(payload)[0], payload)

    def test_every_label_address_is_independent_of_the_season_length(self):
        """The week-dependent bytes (row contents and week labels) are the last ones in the section, so the three
        Apartment words MyCareer's template names, and every other label, are the same for 17 and 18 weeks (and for
        MyCareer's own recognizer, which builds the label map without the season length)."""
        career = home.career_labels(self.p17)
        a = home.code_for({**career, 'season_weeks': 17})
        b = home.code_for({**career, 'season_weeks': 18})
        c = home.code_for({k: v for k, v in career.items() if k != 'season_weeks'})
        shared = lambda labels: {k: v for k, v in labels.items() if not k.startswith('home_week_') and k != 'content_end'}
        self.assertEqual(shared(a[1]), shared(b[1]))
        self.assertEqual(shared(a[1]), shared(c[1]))
        self.assertEqual(home.apartment_fields(a[1]), home.apartment_fields(b[1]))
        rows = a[1]['home_schedule_rows'] - home.CONTENT_VA
        self.assertEqual(a[0][:rows], b[0][:rows])
        with self.assertRaises(ValueError):
            home.code_for({**career, 'season_weeks': 19})

    def test_section_geometry_and_mycareer_code(self):
        p = self.p18
        section = XbeImage(p).section(home.VA)
        self.assertEqual((section.start, section.raw, section.raw_size, section.flags, home.SIZE),
                         (home.VA, home.RAW, home.SIZE, home.FLAGS, 0x3000))
        # Still inside the extra section slot's zero file gap and its unmapped VA hole (the music slot's 64 KB).
        self.assertLessEqual(home.RAW + home.SIZE, space.CODE2_RAW)
        self.assertLessEqual(home.VA + home.SIZE, space.DATA_VA + space.PAGE + 0x10000)
        self.assertFalse(any(p[home.RAW + home.SIZE:space.CODE2_RAW]))
        # MyCareer's code is the owner's own build with Career Home's three Apartment words, nothing else.
        code, data = mode.legacy.allocations(p)
        fields = home.apartment_fields(home.code_for(home.career_labels(p))[1])
        self.assertEqual(XbeImage(p).read(code['va'], mode.legacy.CODE_SIZE),
                         mode.code_for(code['va'], data['va'], home=fields)[0])

    def test_schedule_costs_mycareer_no_byte(self):
        """MyCareer's compressed RW template carries the Apartment's three Career Home addresses; with the layout pad
        they cost what ui1's layout cost (13 spare without Career Home, 7 with it, on this retail-length image)."""
        code, data = mode.legacy.allocations(self.career17)
        alone = mode.TAG_OFFSET - (mode.code_for(code['va'], data['va'])[1]['content_end'] - code['va'])
        self.assertEqual((alone, home.check_static(self.p17)['mycareer_spare_bytes']), (13, 7))
        self.assertGreaterEqual(home.check_static(self.p18)['mycareer_spare_bytes'], 0)

    def test_runtime_reads_the_same_season_byte(self):
        """The runtime counts rows from the stage table's Season row byte +4, the byte the builder read."""
        from mod_editor.core import nfl2k5_season_length as season
        self.assertEqual(home.SEASON_WEEKS_VA, season.SEASON_WEEKS_VA)
        source = (ROOT / 'tools/mycareer_home/home.c').read_text()
        self.assertIn('#define WEEKS (*(const u8 *)0x5151C4)', source)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, FONT and Unicorn required')
class ScheduleNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_my_career_navigation_fixture import resources
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        from nfl2k5_scorebug_projection import read_fonts
        cls.payload = home.apply(mode.apply(retail_bytes())[0])[0]
        cls.labels = home.code_for(home.career_labels(cls.payload))[1]
        cls.roster, cls.evidence = retail_roster(), resources()
        try:
            cls.fonts = read_fonts(XBE.parent / 'vc_53450030/0')
        except (OSError, ValueError) as exc:
            raise unittest.SkipTest(f'pinned retail FONT evidence unavailable: {exc}') from exc

    def machine(self, club=15):
        from tests.nfl2k5_my_career_home_fixture import Machine
        m = Machine(self.payload)
        m.create(self.roster, club=club, position=0, preseason=False)
        m.capture(self.fonts, self.evidence)
        m.put(m.manager + 8 * m.depth() + 4, 0)
        return m

    @staticmethod
    def cursor(m):
        return m.get(m.manager + 8 * m.depth() + 4)

    @staticmethod
    def own(m, row):
        """(slot, cell bytes) of the career club's game in a grid row, else None."""
        team = m.get(m.state + 56)
        for slot in range(17):
            cell = bytes(m.uc.mem_read(GRID + 8 * (17 * row + slot), 8))
            if cell[0] == 7:
                return None
            if team in cell[1:3]:
                return slot, cell
        return None

    def result(self, m, row, own_score, other_score):
        """Write a played result for the club's game in this row (state 3, five quarter bytes per side)."""
        slot, cell = self.own(m, row)
        team = m.get(m.state + 56)
        home_score, away_score = (own_score, other_score) if cell[1] == team else (other_score, own_score)
        m.uc.mem_write(GRID + 8 * (17 * row + slot), b'\x03')
        m.uc.mem_write(SCORES + 10 * (17 * row + slot), bytes((home_score, 0, 0, 0, 0, away_score, 0, 0, 0, 0)))

    def open_schedule(self, m):
        m.select(1)
        self.assertEqual(m.top(), self.labels['home_schedule'])
        # The game draws every frame: the native list learns its window size (0xC8E1D0) in the first draw and the
        # next update keeps the cursor in view (0xC8E1CC). The fixture draws only when asked.
        m.frame(0)
        m.event(7, budget=20000000)
        m.frame(0)

    def cards(self, shot):
        return [t['text'] for t in shot['texts']]

    def inside(self, shot):
        x0, y0, x1, y1 = CARDS
        for q in shot['quads']:
            for x, y, *_ in q['verts']:
                self.assertTrue(x0 <= x <= x1 and y0 <= y <= y1, (x, y))
        for g in shot['glyphs']:
            for x, y, *_ in g['verts']:
                self.assertTrue((x0 <= x <= x1 and y0 - 4 <= y <= y1) or 380 <= y <= 440, (x, y))

    def test_preseason_list_cursor_scroll_a_b_and_play_next_game(self):
        m = self.machine()
        with m:
            shot = m.screen()
            self.assertEqual(shot['rows'][:2], ['Play next game', 'Schedule'])
            nick = lambda i: m.string(m.get(m.get(0xE5786C + 4 * i) + 0x104))
            team = m.get(m.state + 56)
            self.open_schedule(m)
            self.assertEqual(self.cursor(m), m.call('mode_next_fixture') // 17)
            shot = m.screen()
            self.assertEqual(shot['rows'], weeks(17)[:7])
            self.assertEqual(shot['selected'], ['Week 1'])
            texts = self.cards(shot)
            # Week 1: the club's game from the grid, with "@" away / "vs" home, date and kickoff, THIS WEEK tag.
            slot, cell = self.own(m, 0)
            other = cell[2] if cell[1] == team else cell[1]
            self.assertEqual(texts[0], ('vs ' if cell[1] == team else '@ ') + nick(other))
            self.assertEqual(texts[1], 'THIS WEEK')
            self.assertEqual(texts[2], f'{cell[3]}/{cell[4]}/{2000 + cell[5]} at {cell[6]}:{cell[7]:02d}')
            # Every visible week has a card; the bye week says so; footer: club and 0-0, the way back.
            for row in range(7):
                if self.own(m, row) is None:
                    self.assertIn('BYE WEEK', texts)
            self.assertEqual(texts[-2:], ['New York Giants  0-0', 'B: back to Career Home'])
            self.inside(shot)
            # The first card (this week) is the club gradient from the retail colour accessors.
            club = m.get(m.state + 2588)
            primary = m.call(0x68D70, ecx=club) & 0xFFFFFF
            self.assertEqual(shot['quads'][0]['verts'][0][4] & 0xFFFFFF, primary)
            # Scroll: the cursor moves through the native list and the cards follow its first visible row.
            for _ in range(20):
                m.frame(DOWN)
            self.assertEqual((self.cursor(m), m.get(0xC8E1CC)), (20, 14))
            shot = m.screen()
            self.assertEqual(shot['rows'], weeks(17)[14:])
            self.assertEqual(shot['selected'], ['Super Bowl'])
            self.assertEqual(self.cards(shot)[-6:-2], ['TBD'] * 4)   # playoff rounds not set yet
            self.inside(shot)
            bar = [q for q in shot['quads'] if q['verts'][0][0] == 613]
            self.assertEqual(len(bar), 2)                              # track and thumb
            self.assertEqual(max(v[1] for v in bar[1]['verts']), 358)  # thumb at the bottom
            for _ in range(20):
                m.frame(UP)
            self.assertEqual((self.cursor(m), m.get(0xC8E1CC)), (0, 0))
            # A does nothing; B returns to Career Home; Play next game still launches Team Select.
            m.frame(A)
            self.assertEqual((m.top(), self.cursor(m)), (self.labels['home_schedule'], 0))
            m.frame(B)
            self.assertEqual(m.top(), m.labels['apartment'])
            self.assertEqual(m.screen()['rows'][1], 'Schedule')
            m.select(0)
            self.assertEqual(m.top(), TEAM_SELECT)

    def test_results_scores_record_and_this_week(self):
        m = self.machine()
        with m:
            # Giants (retail 2004 grid): weeks 1-5 played, week 6 bye, week 7 is next.
            for row, (own, other) in enumerate(((27, 20), (17, 24), (21, 21), (30, 10), (3, 13))):
                self.result(m, row, own, other)
            self.assertIsNone(self.own(m, 5))
            m.put(0xE576B4, 6)
            self.assertEqual(m.call('mode_next_fixture') // 17, 6)
            self.open_schedule(m)
            self.assertEqual((self.cursor(m), m.get(0xC8E1CC)), (6, 0))
            shot = m.screen()
            self.assertEqual(shot['selected'], ['Week 7'])
            texts = self.cards(shot)
            results = [t for t in texts if t[:2] in ('W ', 'L ', 'T ')]
            self.assertEqual(results, ['W 27-20', 'L 17-24', 'T 21-21', 'W 30-10', 'L 3-13'])
            colours = {t['text']: t['tint'] for t in shot['texts']}
            self.assertEqual((colours['W 27-20'], colours['L 17-24'], colours['T 21-21']),
                             (0xFF30C050, 0xFFE03838, 0xFFC8C8C8))
            self.assertEqual(texts.count('BYE WEEK'), 1)
            self.assertEqual(texts.count('THIS WEEK'), 1)
            self.assertEqual(texts[-2], 'New York Giants  2-2-1')
            # Result accents: green, red, grey bars beside the played weeks.
            accents = [q['verts'][0][4] for q in shot['quads'] if q['verts'][1][0] - q['verts'][0][0] == 3]
            self.assertEqual(accents[:5], [0xFF30C050, 0xFFE03838, 0xFFC8C8C8, 0xFF30C050, 0xFFE03838])
            self.inside(shot)

    def test_playoff_rows_no_game_and_scheduled(self):
        m = self.machine()
        with m:
            team = m.get(m.state + 56)
            others = [t for t in range(32) if t != team]
            # Wild Card (row 17 at 17 weeks) has a game without the club; the Divisional round has the club at home.
            for row, cell in ((17, bytes((0, others[0], others[1], 1, 15, 5, 1, 0))),
                              (18, bytes((0, team, others[2], 1, 22, 5, 4, 30)))):
                self.assertEqual(m.uc.mem_read(GRID + 8 * 17 * row, 1), b'\x07')
                m.uc.mem_write(GRID + 8 * 17 * row, cell)
            self.open_schedule(m)
            for _ in range(20):
                m.frame(DOWN)
            texts = self.cards(m.screen())
            nick = m.string(m.get(m.get(0xE5786C + 4 * others[2]) + 0x104))
            self.assertIn('NO GAME', texts)
            self.assertIn(f'vs {nick}', texts)
            self.assertIn('1/22/2005 at 4:30', texts)
            self.assertEqual(texts.count('TBD'), 2)

    def test_a_natively_simulated_week_shows_real_results(self):
        """One real league week (0x247D40, the game's own advance). Declared boundary: while it runs, MyCareer's fixture
        guard (career_fixture, which makes its C7A20 hook refuse to whole-game simulate a MyPlayer-team fixture) says
        "not a career fixture", so the native sim plays the club's game too; in game the user plays it. The card
        shows the native cell scores (C5110 home, C5150 away) from the club's side."""
        m = self.machine()
        with m:
            team = m.get(m.state + 56)
            m.replace_stub(0x177990, lambda: m.ret(pop=4))  # league-advance progress renderer only
            m.replace_stub(m.labels['career_fixture'], lambda: m.ret(0))
            m.call(0x247D40, ecx=m.manager, budget=3_000_000_000)
            m.replace_stub(m.labels['career_fixture'], None)
            slot, cell = self.own(m, 0)
            self.assertEqual(cell[0], 3)
            home_score, away_score = m.call(0xC5110, ecx=0, edx=slot), m.call(0xC5150, ecx=0, edx=slot)
            own, other = (home_score, away_score) if cell[1] == team else (away_score, home_score)
            mark = 'W' if own > other else 'L' if own < other else 'T'
            self.open_schedule(m)
            self.assertEqual(self.cursor(m), m.call('mode_next_fixture') // 17)
            for _ in range(self.cursor(m)):   # the native list wraps, so exactly back to Week 1
                m.frame(UP)
            self.assertEqual((self.cursor(m), m.get(0xC8E1CC)), (0, 0))
            texts = self.cards(m.screen())
            self.assertIn(f'{mark} {own}-{other}', texts)
            record = {'W': '1-0', 'L': '0-1', 'T': '0-0-1'}[mark]
            self.assertEqual(texts[-2], f'New York Giants  {record}')

    def test_missing_font_skips_without_faulting(self):
        m = self.machine()
        with m:
            self.open_schedule(m)
            m.put(0xA90ECC, 0)  # font slot 0 (the quads' material and the card font) absent
            shot = m.screen()
            self.assertEqual(shot['quads'], [])
            self.assertEqual(m.top(), self.labels['home_schedule'])
            m.frame(B)
            self.assertEqual(m.top(), m.labels['apartment'])


if __name__ == '__main__':
    unittest.main()
