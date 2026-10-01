"""Beta 76 s15: Franchise records, the possession arrow and used timeouts on the sprite scorebug.

Nothing here is an in-game result. The owner's compiled code runs under Unicorn on the mapped retail executable:

* ``records`` (setup only) on a synthetic season: "1-0" / "0-1", ties as W-L-T, nothing for a side that has not played
  a decided game (ESPN shows no record in week 1), the regular-season record in the playoffs (the retail summers would
  add a played Wild Card game), 18 regular rows once the 2026 season length patches the stage table, and nothing in the
  preseason, a Quick Game with a Franchise loaded, a tournament or Play Now;
* ``possessor``: the team object in [0xE60280] away / home, nobody in phase 0, and the receiving team during a kick,
  kept across the dead-ball swap until the kick phase ends;
* the retail proofs behind both: FUN_000e9460 stages possession, the retail bar highlights [0xE60280], and the retail
  update hides the whole bar at game over (so no post-game record could ever be drawn);
* the native preview: records, tabs and the arrow drawn in both aspects inside their boxes, white digits on the navy tab,
  one quad per timeout state, and the per-frame update never entering the retail counters.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import nfl2k5_scorebug_runtime as owner  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_sprite_code as engine  # noqa: E402
from mod_editor.core import nfl2k5_season_length as season_length  # noqa: E402
from test_nfl2k5_franchise_records import XBE, HAVE_UC, _Season, _retail, record_text, mirror  # noqa: E402

PACK = ROOT / 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
NATIVE = PACK.is_file() and (PACK.parents[1] / 'default.xbe').is_file() and HAVE_UC
CODE_VA, DATA_VA = 0x5100000, 0x5200000
RECORD_OFFSETS = (48, 72)          # State.record[0] home, [1] away
KICK_PHASE, KICKER = 40, 44
HOME_TEAM, AWAY_TEAM = 0xE5FC20, 0xE5FC60
PHASE, POSSESSION, OTHER, GAME_STATE = 0xE602B4, 0xE60280, 0xE60284, 0xE602B8

# Retail spans the arrow and the FINAL decision rest on (SHA-256 pins; no retail bytes live here).
# FUN_000e9460(ecx=team, edx=direction): [0xE60284] = [team] (its opponent), both attack directions, [0xE60280] = team;
# every kickoff builder calls it with the kicking team (the opening kickoff at 0x1584C9 with [0xE602F0]).
# 0xB7E22: the kick dead-ball evaluator swaps [0xE60280] and [0xE60284] on a change of possession.
# 0xFC4E6: the retail bar draw colours the possessing team's text when [0xE60280] is 0xE5FC60 (away) or 0xE5FC20.
# 0xFC9DD: the retail update calls 0xFC6B0 when the game state [0xE602B8] is 10 (game over); 0xFC6B0 zeroes 0xA95524,
# and the bar draw at 0xFC36C returns while 0xA95520 or 0xA95524 is zero: the bar is gone after the final whistle.
PINS = {
    'possession setter FUN_000e9460': (0x0e9460, 0x3e, "5f35cd253f4fe2adaf8e75d8067ffa54daa60889add9aceda4bd1ab40f4358a5"),
    'kick dead-ball possession swap': (0x0b7e22, 0x1c, "86194ab19e32d89a2f55febf30622d67903c8ba731ca87003b778e3b00edddc4"),
    'retail bar highlight tests [0xE60280]': (0x0fc4e6, 0x21, "88e4f12f5d38f13d4387f2e168b7b1fd882e54c1fe6eac822d6343953d1bc2c5"),
    'retail update: game over hides the bar': (0x0fc9dd, 0x1e, "a1d4693baecb7ea3dd06a0600425e58a3e2ee3cf428ee5e3f789e2e4cd87fe54"),
    'hide routine FC6B0': (0x0fc6b0, 0x0d, "743b31b02d89c4d0980271f20354f428e253fe851fc46c018346e608b67c72ef"),
    'bar draw gate': (0x0fc36c, 0x1d, "a60ae17715098f551c2917301bf15af2d75d985f6dedf1a29a5c47c057d94f64"),
    'stage table Season row weeks byte': (0x5151c4, 0x01, "4a64a107f0cb32536e5bce6c98c393db21cca7f4ea187ba8c4dca8b51d4ea80a"),
}


class LayoutTests(unittest.TestCase):
    """Runs everywhere: the compiled layout carries the new fields inside the 44 atlas quads."""

    @classmethod
    def setUpClass(cls):
        cls.compiled = sprite.compile_folder()

    def test_quad_budget_and_materials(self):
        from collections import Counter
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        quads = self.compiled.quads
        self.assertEqual(len(quads), 50)          # b76 sb: + the TIMEOUT tab
        used = Counter(q['material'] for q in quads)
        capacity = {k: (w - 4) // 3 for k, (_, w) in enumerate(scene.layout.SUBMESH_COMMANDS)}
        atlas = sum(used[k] for k in sprite.ATLAS_MATERIALS)
        self.assertEqual(atlas, 44)               # b76 sb: the TIMEOUT tab takes the last atlas quad
        self.assertEqual(sum(capacity[k] for k in sprite.ATLAS_MATERIALS), 44)
        for k, n in used.items():
            self.assertLessEqual(n, capacity[k], k)
        names = {q['name'].split(':')[0] for q in quads}
        self.assertNotIn('pointer', names)
        for name in ('away_record', 'home_record', 'away_record_tab', 'home_record_tab', 'possession'):
            self.assertIn(name, names)
        slots = {f['name']: f['slots'] for f in self.compiled.spec['fields']}
        self.assertEqual((slots['away_timeouts'], slots['home_timeouts'], slots['quarter']), (1, 1, 1))
        self.assertEqual((slots['away_record'], slots['home_record'], slots['possession']), (3, 3, 1))

    def test_record_tokens_cover_every_regular_season_record_in_three_quads(self):
        glyphs = self.compiled.spec['glyph_sets']['record']['glyphs']
        self.assertEqual(set(glyphs), {str(n) for n in range(18)} | {'-' + str(n) for n in range(18)})
        ordered = sorted(glyphs, key=lambda t: (-len(t), t))       # the compiler's (and matcher's) order

        def tokens(text):
            out, at = [], 0
            while at < len(text):
                match = next((t for t in ordered if text.startswith(t, at)), None)
                self.assertIsNotNone(match, text)
                out.append(match)
                at += len(match)
            return out
        for w in range(18):
            for l in range(18 - w):
                for t in range(18 - w - l):
                    text = record_text(w, l, t)
                    self.assertLessEqual(len(tokens(text)), 3, text)
        self.assertEqual(tokens('10-6-1'), ['10', '-6', '-1'])
        self.assertEqual(tokens('1-10'), ['1', '-10'])

    def test_tab_width_follows_text_length_and_holds_the_widest_record(self):
        tab = self.compiled.spec['glyph_sets']['record_tab']['glyphs']
        record = self.compiled.spec['glyph_sets']['record']['glyphs']
        self.assertEqual(set(tab), {str(n) for n in range(3, 9)})
        widths = [tab[str(n)]['size'][0] for n in range(3, 9)]
        self.assertEqual(widths, sorted(widths))
        fields = {f['name']: f for f in self.compiled.spec['fields']}
        box = fields['away_record']['box'][2] - fields['away_record']['box'][0]
        for w, l, t in ((1, 0, 0), (10, 6, 0), (10, 6, 1), (8, 8, 1), (17, 0, 0)):
            text = record_text(w, l, t)
            parts = [text.split('-')[0]] + ['-' + p for p in text.split('-')[1:]]
            width = sum(record[p]['advance'] for p in parts[:-1]) + record[parts[-1]]['size'][0]
            self.assertLessEqual(width, box, text)                  # never compressed
            self.assertAlmostEqual(tab[str(len(text))]['size'][0] >= width + 9 - 1e-6, True, msg=text)

    def test_timeouts_are_four_states_dimming_from_the_right(self):
        ticks = self.compiled.spec['glyph_sets']['ticks']['glyphs']
        self.assertEqual(set(ticks), {'0', '1', '2', '3'})
        image = sprite.load_layout()[1]
        cells = self.compiled.spec['cells']
        for remaining in range(4):
            cell = image.crop(cells[ticks[str(remaining)]['cell']]['box'])
            shades = [cell.getpixel((i * 10 + 3, 0))[0] for i in range(3)]
            self.assertEqual([s == 255 for s in shades], [i < remaining for i in range(3)], remaining)
            for s in shades:
                self.assertIn(s, (255, shades[-1] if remaining < 3 else 255))
        grey = image.crop(cells['timeouts_0']['box']).getpixel((3, 0))[0]
        self.assertTrue(70 <= grey <= 95, grey)                    # measured used/lit 0.33 of the lit pip

    def test_digit_face_is_seven_rows_and_white(self):
        image = sprite.load_layout()[1]
        cells = self.compiled.spec['cells']
        for token in ('0', '17', '-5'):
            name = 'record_' + ('m' + token[1:] if token[0] == '-' else 'd' + token)
            cell = image.crop(cells[name]['box'])
            self.assertEqual(cell.height, 7)
            ink = [p for p in cell.getdata() if p[3]]
            self.assertTrue(ink and all(p[:3] == (255, 255, 255) and p[3] == 255 for p in ink))

    def test_quarter_prints_retail_overtime_as_ot(self):
        quarter = self.compiled.spec['glyph_sets']['quarter']['glyphs']
        self.assertEqual(quarter['OT1'], quarter['OT'])


def _machine():
    data = _retail()
    if data is None:
        raise unittest.SkipTest('retail XBE pin differs')
    m = _Season(data)
    code, labels = owner.code_for(CODE_VA, DATA_VA)
    m.uc.mem_map(CODE_VA, 0x2000)
    m.uc.mem_write(CODE_VA, code)
    m.uc.mem_map(DATA_VA, 0x1000)
    return m, labels


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE and Unicorn required')
class RecordReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.labels = _machine()

    def setUp(self):
        self.m.clear_stubs()
        self.m.uc.mem_write(DATA_VA, bytes(128))

    def records(self, *, mode=2, stage=8, game_mode=7, home=None, away=None):
        m = self.m
        for va, value in ((0xE576A0, mode), (0xE576A4, stage), (0xE5FF80, game_mode),
                          (0xE5FE68, m.team(home) if home is not None else 0),
                          (0xE5FE6C, m.team(away) if away is not None else 0)):
            m.put(va, value)
        m.call(self.labels['records'], ecx=DATA_VA, budget=5_000_000)
        return tuple(m.wide(DATA_VA + off, 12) for off in RECORD_OFFSETS)

    def weeks(self, value):
        self.m.uc.mem_write(season_length.SEASON_WEEKS_VA, bytes((value,)))

    def test_retail_stage_table_is_seventeen_regular_weeks(self):
        self.assertEqual(self.m.uc.mem_read(season_length.SEASON_WEEKS_VA, 1)[0], season_length.RETAIL_REGULAR_WEEKS)

    def test_one_game_each_reads_one_zero_and_zero_one(self):
        m = self.m
        m.season(0)
        m.play(0, 0, 4, 9, 24, 17)                       # week 1: team 4 beat team 9 at home
        self.assertEqual(self.records(home=4, away=9), ('1-0', '0-1'))
        self.assertEqual(self.records(home=9, away=4), ('0-1', '1-0'))

    def test_week_one_before_any_game_shows_nothing(self):
        self.m.season(0)
        self.assertEqual(self.records(home=4, away=9), ('', ''))

    def test_every_team_matches_the_grid_mirror_with_ties(self):
        m = self.m
        fixtures = m.season(12)
        self.assertTrue(any(hs == as_ for _h, _a, hs, as_ in fixtures))
        for team in range(0, 32, 2):
            with self.subTest(team=team):
                home, away = self.records(home=team, away=team + 1)
                self.assertEqual(home, record_text(*mirror(fixtures, team)))
                self.assertEqual(away, record_text(*mirror(fixtures, team + 1)))
        tied = next(t for t in range(32) if mirror(fixtures, t)[2])
        self.assertEqual(self.records(home=tied, away=0)[0].count('-'), 2)

    def test_playoffs_show_the_regular_season_record(self):
        m = self.m
        fixtures = m.season(17)                            # the retail 17-week season is complete
        m.play(17, 0, 4, 9, 24, 17)                       # a played Wild Card game (row 17)
        regular = record_text(*mirror(fixtures, 4))
        with_playoff = record_text(*mirror(fixtures + [(4, 9, 24, 17)], 4))
        self.assertNotEqual(regular, with_playoff)
        self.assertEqual(m.record(m.team(4)), mirror(fixtures + [(4, 9, 24, 17)], 4))   # retail summers count it
        self.assertEqual(self.records(stage=9, game_mode=6, home=4, away=9)[0], regular)

    def test_eighteen_week_season_counts_row_seventeen(self):
        m = self.m
        fixtures = m.season(18)                            # season() plays 16 games in each of rows 0..17
        seventeen = fixtures[:17 * 16]
        try:
            self.weeks(season_length.PATCHED_REGULAR_WEEKS)
            for team in (4, 9, 21):
                self.assertEqual(self.records(home=team, away=0)[0], record_text(*mirror(fixtures, team)))
            self.weeks(season_length.RETAIL_REGULAR_WEEKS)
            for team in (4, 9, 21):
                self.assertEqual(self.records(home=team, away=0)[0], record_text(*mirror(seventeen, team)))
        finally:
            self.weeks(season_length.RETAIL_REGULAR_WEEKS)

    def test_other_modes_show_nothing(self):
        m = self.m
        m.season(6)
        for case in (dict(stage=7), dict(game_mode=4), dict(mode=1, game_mode=5), dict(mode=0)):
            with self.subTest(**case):
                self.assertEqual(self.records(home=4, away=9, **case), ('', ''))
        self.assertEqual(self.records(home=4, away=None)[1], '')

    def test_the_reader_is_setup_only(self):
        # The per-frame update never reaches the counters: no call into C75A0..C77E0 or the formatter.
        update = engine.CODE[engine.LABELS['sprite_update']:]
        for target in (0xC75A0, 0xC7620, 0xC76A0, 0x4A400):
            self.assertNotIn(struct.pack('<I', target), update)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE and Unicorn required')
class PossessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.labels = _machine()

    def side(self, phase, team):
        self.m.put(PHASE, phase)
        self.m.put(POSSESSION, team)
        return self.m.call(self.labels['possessor'], ecx=DATA_VA)

    def test_scrimmage_and_point_after_follow_the_possession_pointer(self):
        self.m.uc.mem_write(DATA_VA, bytes(128))
        for phase in (3, 4):
            self.assertEqual((self.side(phase, AWAY_TEAM), self.side(phase, HOME_TEAM)), (1, 2))
        self.assertEqual(self.side(4, 0), 0)
        self.assertEqual(self.side(4, owner.SCORE_POINTERS[0]), 0)

    def test_nobody_in_phase_zero(self):
        self.m.uc.mem_write(DATA_VA, bytes(128))
        self.assertEqual((self.side(0, AWAY_TEAM), self.side(0, HOME_TEAM)), (0, 0))

    def test_kicks_mark_the_receiving_team_through_the_dead_ball_swap(self):
        m = self.m
        m.uc.mem_write(DATA_VA, bytes(128))
        self.assertEqual(self.side(2, HOME_TEAM), 1)       # home kicks off: the away team receives
        self.assertEqual(m.get(DATA_VA + KICKER), HOME_TEAM)
        self.assertEqual(self.side(2, AWAY_TEAM), 1)       # swapped at the dead ball, still the kick phase
        self.assertEqual(self.side(4, AWAY_TEAM), 1)       # first scrimmage play
        self.assertEqual(m.get(DATA_VA + KICK_PHASE), 0)
        self.assertEqual(self.side(2, AWAY_TEAM), 2)       # the away team kicks off after a score
        self.assertEqual(self.side(1, HOME_TEAM), 1)       # a safety kick re-captures its own kicker
        self.assertEqual(self.side(4, HOME_TEAM), 2)       # onside or not, scrimmage follows the pointer again


@unittest.skipUnless(XBE.is_file(), 'pinned USA XBE required')
class RetailProofTests(unittest.TestCase):
    def test_retail_spans_match_their_pins(self):
        data = _retail()
        if data is None:
            self.skipTest('retail XBE pin differs')
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(data)
        for name, (va, size, digest) in PINS.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(image.read(va, size)).hexdigest(), digest)
        self.assertEqual(PINS['stage table Season row weeks byte'][0], season_length.SEASON_WEEKS_VA)

    @unittest.skipUnless(HAVE_UC, 'Unicorn required')
    def test_possession_setter_and_game_over_hide_execute(self):
        m, _labels = _machine()
        for team, opponent in ((AWAY_TEAM, HOME_TEAM), (HOME_TEAM, AWAY_TEAM)):
            m.put(team, opponent)                           # a team object's +0 names its opponent
            m.put(team + 8, m.HEAP + (0x100 if team == HOME_TEAM else 0x200))   # its direction owner
        m.call(0xE9460, ecx=AWAY_TEAM, edx=1)
        self.assertEqual((m.get(POSSESSION), m.get(OTHER)), (AWAY_TEAM, HOME_TEAM))
        m.call(0xE9460, ecx=HOME_TEAM, edx=-1)
        self.assertEqual((m.get(POSSESSION), m.get(OTHER)), (HOME_TEAM, AWAY_TEAM))
        m.put(0xA95524, 1)
        m.put(0xA957E0, 1)
        m.call(0xFC6B0)
        self.assertEqual((m.get(0xA95524), m.get(0xA957E0)), (0, 0))


@unittest.skipUnless(NATIVE, 'Pinned USA game and Unicorn required')
class NativePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview = sprite.NativePreview()

    def capture(self, widescreen=False, **state):
        g, c = self.preview.capture(state, widescreen)
        self.addCleanup(c['machine'].close)
        return g, c

    def visible(self, c, wide, name):
        rows = [q for q in self.preview.modes[wide]['compiled'].quads if q['name'].split(':')[0] == name]
        return [q for q in rows if struct.unpack_from('<I', c['live_decoded'], 0x2d20 + q['vertex'] * 10)[0]]

    def box(self, g, quads):
        points = [p for q in quads for p in g['positions'][q['vertex']:q['vertex'] + 4]]
        return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]

    def test_records_tabs_and_arrow_in_both_aspects(self):
        for wide in (False, True):
            for possession in ('away', 'home'):
                g, c = self.capture(wide, away='NYG', home='LAR', broadcast='monday_night', possession=possession,
                                    home_record=[0, 1, 0], away_record=[1, 0, 0])
                with self.subTest(wide=wide, possession=possession):
                    bar = g['frame']
                    for side in ('away', 'home'):
                        text, tab = self.visible(c, wide, side + '_record'), self.visible(c, wide, side + '_record_tab')
                        self.assertEqual((len(text), len(tab)), (2, 1))
                        t, b = self.box(g, text), self.box(g, tab)
                        self.assertTrue(b[0] - .01 <= t[0] and t[2] <= b[2] + .01 and b[1] - .01 <= t[1] and t[3] <= b[3] + .01, (t, b))
                        self.assertTrue(bar[0] - .01 <= b[0] and b[2] <= bar[2] + .01 and bar[1] - .01 <= b[1] and b[3] <= bar[3] + .01)
                    arrow = self.visible(c, wide, 'possession')
                    self.assertEqual(len(arrow), 1)
                    a = self.box(g, arrow)
                    score = self.box(g, self.visible(c, wide, possession + '_score'))
                    self.assertLess(abs((a[0] + a[2]) / 2 - (score[0] + score[2]) / 2), 2.0)   # HUD px
                    self.assertLess(a[3], score[1] + .01)                                       # above the digits
                    self.assertTrue(bar[1] - .01 <= a[1])
                    # The frame never enters the per-week counters or the season summers (0xC75A0..0xC77E0); setup
                    # runs the counters and never the summers, which would add played playoff rows. (0x4A400 runs
                    # every frame for the retail clock and down formatters, so it proves nothing either way.)
                    self.assertFalse(any(0xC75A0 <= va < 0xC77E0 for va in c['trace']['frame']))
                    self.assertTrue(any(0xC75A0 <= va < 0xC7720 for va in c['trace']['setup']))
                    self.assertFalse(any(0xC7720 <= va < 0xC77B0 for va in c['trace']['setup']))

    def test_no_record_hides_text_and_tab(self):
        for state in (dict(), dict(broadcast='monday_night', home_record=[0, 0, 0], away_record=[0, 0, 0]),
                      dict(broadcast='play_now', home_record=[3, 1, 0], away_record=[2, 2, 0]),
                      dict(broadcast='monday_night', season='preseason', home_record=[1, 0, 0], away_record=[0, 1, 0])):
            g, c = self.capture(False, **state)
            with self.subTest(state=state):
                for name in ('away_record', 'home_record', 'away_record_tab', 'home_record_tab'):
                    self.assertEqual(self.visible(c, False, name), [], name)

    def test_arrow_hides_in_phase_zero_and_marks_the_receiver_on_a_kickoff(self):
        g, c = self.capture(False, phase=0)
        self.assertEqual(self.visible(c, False, 'possession'), [])
        g, c = self.capture(False, phase=2, possession='home')      # home kicks: the arrow is over the away score
        arrow = self.box(g, self.visible(c, False, 'possession'))
        away = self.box(g, self.visible(c, False, 'away_score'))
        self.assertLess(abs((arrow[0] + arrow[2]) / 2 - (away[0] + away[2]) / 2), 2.0)

    def test_one_timeout_quad_per_side_in_every_state(self):
        compiled = self.preview.modes[False]['compiled']
        glyphs = compiled.spec['glyph_sets']['ticks']['glyphs']
        uv = {t: sprite.quantized_uv(compiled.cells[g['cell']], compiled.spec['atlas']) for t, g in glyphs.items()}
        for home, away in ((3, 0), (2, 1), (1, 2), (0, 3)):
            g, c = self.capture(False, home_timeouts=home, away_timeouts=away)
            for side, remaining in (('home', home), ('away', away)):
                quads = self.visible(c, False, side + '_timeouts')
                self.assertEqual(len(quads), 1)
                self.assertEqual(self.uv(c, quads[0]), uv[str(remaining)], (side, remaining))

    def uv(self, c, quad):
        return tuple(struct.unpack_from('<h', c['live_decoded'], 0x2d20 + (quad['vertex'] + j) * 10 + 4 + k * 2)[0]
                     for j in range(4) for k in range(2))

    def glyph_uv(self, glyph_set, token):
        compiled = self.preview.modes[False]['compiled']
        cell = compiled.spec['glyph_sets'][glyph_set]['glyphs'][token]['cell']
        return sprite.quantized_uv(compiled.cells[cell], compiled.spec['atlas'])

    def test_record_quads_carry_their_tokens(self):
        g, c = self.capture(False, broadcast='monday_night', away_record=[1, 0, 0], home_record=[10, 5, 1])
        away = sorted(self.visible(c, False, 'away_record'), key=lambda q: q['vertex'])
        home = sorted(self.visible(c, False, 'home_record'), key=lambda q: q['vertex'])
        self.assertEqual([self.uv(c, q) for q in away], [self.glyph_uv('record', t) for t in ('1', '-0')])
        self.assertEqual([self.uv(c, q) for q in home], [self.glyph_uv('record', t) for t in ('10', '-5', '-1')])
        self.assertEqual(self.uv(c, self.visible(c, False, 'home_record_tab')[0]), self.glyph_uv('record_tab', '6'))

    def test_overtime_draws_ot(self):
        # The retail quarter formatter prints 'OT%d' (period - 4); the sprite set had no 'OT1', so overtime drew nothing.
        for period, token in ((4, '4TH'), (5, 'OT1')):
            g, c = self.capture(False, quarter=period)
            quads = self.visible(c, False, 'quarter')
            self.assertEqual(len(quads), 1, period)
            self.assertEqual(self.uv(c, quads[0]), self.glyph_uv('quarter', token))

    def test_white_digits_stand_off_the_navy_tab(self):
        compiled = self.preview.modes[False]['compiled']
        from mod_editor.core import nfl2k5_scorebug_assets as assets
        import numpy as np
        palette, indices = assets.quantize_alpha_aware(compiled.atlas)
        atlas = np.asarray(palette, dtype=np.uint8)[np.frombuffer(indices, dtype=np.uint8)].reshape(compiled.atlas.height, compiled.atlas.width, 4)

        def luminance(rgb):
            c = [v / 255 for v in rgb]
            c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
            return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
        x0, y0, x1, y1 = compiled.cells['record_tab']
        navy = atlas[(y0 + y1) // 2, (x0 + x1) // 2, :3]
        x0, y0, x1, y1 = compiled.cells['record_d8']
        ink = atlas[y0:y1, x0:x1][atlas[y0:y1, x0:x1, 3] == 255][:, :3]
        white = ink.max(axis=0)
        ratio = (luminance(white) + 0.05) / (luminance(navy) + 0.05)
        self.assertGreater(ratio, 12.0)


if __name__ == '__main__':
    unittest.main()
