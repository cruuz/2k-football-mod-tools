"""Beta 76 sb: the 2026 ESPN bar's remaining states on the sprite scorebug.

Nothing here is an in-game result. The owner's compiled code runs under Unicorn on the mapped retail executable, and
the native preview runs the retail HUD update with the installed owner. Broadcast facts come from read-only frames
(the 2026 MNF Giants at Rams off-air capture and the full Broncos at Chiefs game), measured by reports/b76_sb:

* the black ESPN wordmark plate (22,21,23; white mark in 100 x 24 px at 910..1010 x 956..980) whenever the plate
  carries no down: the kick and point-after phases, pregame, the half and the overtime toss (the retail formatter
  FC7D0 prints "Kickoff", "Point After", "Pregame"... there, which the label set cannot draw), and in place of the
  retail hang-time, ball-on and FUMBLE plates, which ESPN never draws; FLAG keeps its yellow plate (205,198,0);
* "3rd Down" for 7 s after the down steps (ESPN's median of 52 interim labels in the full game);
* ":54" under a minute (the retail FC100 prints "0:54");
* the play-clock cell red (213,0,54) with white digits at 5 and under;
* the TIMEOUT tab over the calling team's wing for 4 s (ESPN's popups ran 2, 4 and 5 s), counted only while the bar
  draws: lab run 2 showed the play-call screen hides the bar ([0xA95524] = 0), and a tab counted there went unseen.
HALFTIME, first traced for the capsule, was removed after lab run 2: the game never draws the bar at the half.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import nfl2k5_scorebug_runtime as owner  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402
from test_nfl2k5_franchise_records import XBE, HAVE_UC, _Season, _retail  # noqa: E402

PACK = ROOT / 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
NATIVE = PACK.is_file() and (PACK.parents[1] / 'default.xbe').is_file() and HAVE_UC
CODE_VA, DATA_VA = 0x5100000, 0x5200000
SCENE_BASE, OBJECTS, FIELD_VA, TEXT_VA = 0x3038000, 0x303c000, 0x303d000, 0x303d100
DOWN, INTERIM, TIMEOUTS, TAB, TAB_SIDE, RED = 96, 100, 104, 108, 112, 116      # State offsets (runtime.c)
PHASE, QUARTER, CLOCK, DOWN_OBJECT = 0xE602B4, 0xE602C4, 0xE6028C, 0xE602EC
HOME_SCORE, AWAY_SCORE = 0xE5FC28, 0xE5FC68
HANG_TIME, FLAG, BALL_ON, FUMBLE = 0xA95AA8, 0xA95B18, 0xA95B88, 0xA95BF8
ESPN_PLATE, PLAY_CLOCK_RED = 0xFF181719, 0xFFDD0038


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def value(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


# Retail spans this pass relies on (SHA-256 only; no retail bytes live here).
PINS = {
    # FC7D0 switches on the phase [0xE602B4] through the five-entry table at FC990: "Pregame"/"Overtime",
    # "Safety Kick", "Kickoff", "Point After", then the down and distance.
    'down formatter phase switch FC7D0': (0x0fc7d0, 0x23, '83abe1356c65d2208fffd9028aedad062424ed78f14789862eb22f517b37ea5d'),
    'phase table FC990': (0x0fc990, 0x14, 'ef4ee701fd5b41947d8bcb7fb86146841a735fc85b1aa5952c32b3eeb0dbf2a7'),
    'play clock formatter FBE30': (0x0fbe30, 0x20, 'dfc76400cd9c596d407b6752c3fada6d3b8127b49835f90b0e4aad679a1cc551'),
    'clock formatter under ten minutes FC100': (0x0fc100, 0x20, '4f8069e0201fc934ff8fe706bd290f78277b4beae1f9501ccfe01f88e0ada31e'),
}


class LayoutTests(unittest.TestCase):
    """Runs everywhere: the traced cells, their tokens and the one new field."""

    @classmethod
    def setUpClass(cls):
        cls.spec, cls.image = sprite.load_layout()
        cls.compiled = sprite.compile_folder()

    def test_budget(self):
        from collections import Counter
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        quads = self.compiled.quads
        self.assertEqual(len(quads), 50)
        used = Counter(q['material'] for q in quads)
        capacity = {k: (w - 4) // 3 for k, (_, w) in enumerate(scene.layout.SUBMESH_COMMANDS)}
        self.assertEqual(sum(used[k] for k in sprite.ATLAS_MATERIALS), 44)
        for k, n in used.items():
            self.assertLessEqual(n, capacity[k], k)
        self.assertEqual(sprite.probe_sizes(), (34, 327904, 327680))    # +128 B (sb), +384 B the OT tokens (sbfix): same HUD sectors
        code, _ = owner.code_for(CODE_VA, DATA_VA)
        self.assertEqual((owner.CODE_SIZE, owner.REVISION), (5376, 13))
        self.assertLess(len(code.rstrip(b'\xcc')), owner.CODE_SIZE - 8)

    def test_tokens_and_metrics(self):
        label = self.spec['glyph_sets']['label']['glyphs']
        # sb2: down labels shrink to 24; compensate the token to preserve the ESPN mark's 100x24 box.
        self.assertEqual(label['ESPN'], {'cell': 'espn_plate_mark', 'size': [125, 30], 'advance': 125, 'raise': -1.25})
        self.assertEqual(label['Down']['cell'], 'label_Down')
        self.assertEqual(label['Down']['raise'], 0)
        self.assertAlmostEqual(label['Down']['size'][1], 22 * 30 / 23, places=2)   # token metrics use the set's 30 px design grid; the field scales them to 24
        self.assertNotIn('HT', self.spec['glyph_sets']['clock']['glyphs'])   # HALFTIME removed after lab run 2
        tab = self.spec['glyph_sets']['timeout_tab']
        self.assertEqual((tab['cap_height'], tab['glyphs']['T']['size']), (21, [172, 21]))
        fields = {f['name']: f for f in self.spec['fields']}
        self.assertEqual(fields['timeout_tab']['source'], 'timeout tab')
        self.assertEqual((fields['timeout_tab']['anchor'], fields['timeout_tab']['alt_anchor'], fields['timeout_tab']['size']),
                         ([630.0, 900], [1291.0, 900], 42))
        self.assertTrue(fields['clock']['strip_minute'])
        self.assertEqual(fields['clock']['box'], [906, 1006, 1014, 1033])
        statics = {r['name']: r for r in self.spec['static']}
        self.assertEqual(statics['red']['tint'], 'play clock cell')
        self.assertEqual(statics['capsule']['box'], [839, 999, 1022, 1039])

    def test_cells_are_traced_masks_at_the_hud_footprint(self):
        for name, size in (('espn_plate_mark', (33, 9)), ('label_Down', (27, 9)), ('timeout_tab', (114, 17))):
            x0, y0, x1, y1 = self.spec['cells'][name]['box']
            cell = self.image.crop((x0, y0, x1, y1))
            self.assertEqual(cell.size, size, name)
            self.assertGreaterEqual(cell.getchannel('A').getextrema()[1], 250, name)     # solid strokes at full coverage
            if name != 'timeout_tab':
                # White masks the field colour tints; nothing but coverage.
                opaque = [p[:3] for p in cell.getdata() if p[3] > 128]
                self.assertTrue(all(min(p) >= 250 for p in opaque), name)
        tab = self.image.crop(tuple(self.spec['cells']['timeout_tab']['box']))
        self.assertLess(max(tab.getpixel((4, tab.height // 2))[:3]), 50)      # the near-black tab (22,18,18) on air
        self.assertIn('sb', self.spec['provenance'])

    def test_flag_yellow_and_no_capsule_dividers(self):
        flag = self.image.crop(tuple(self.spec['cells']['flag']['box']))
        r, g, b, a = flag.getpixel((3, flag.height // 2))
        self.assertTrue(abs(r - 205) <= 6 and abs(g - 198) <= 6 and b < 20, (r, g, b))
        for name in ('capsule', 'red'):
            x0, y0, x1, y1 = self.spec['cells'][name]['box']
            row = [self.image.getpixel((x, (y0 + y1) // 2))[:3] for x in range(x0 + 1 if name == 'red' else x0 + 3, x1 - 3)]
            self.assertGreater(min(min(p) for p in row), 240, name)            # one white run, no dark column

    def test_plate_sits_below_the_bar_rim(self):
        # Noah on the candidate disc: the black ESPN plate "appears above the scorebug barely". On air the plate's top
        # edge is row 948, under the bar's rim glow (944..947), and it ends at 985. The plate and the event plates that
        # cover it start there, at least two HUD rows under the bar's top edge in both aspects.
        statics = {r['name']: r for r in self.spec['static']}
        self.assertEqual(statics['plate']['box'], [822, 948, 1096, 986])
        self.assertTrue(all(e['box'] == [822, 948, 1096, 986] for e in self.spec['events']))
        for wide in (False, True):
            bar, plate = sprite.hud_box(statics['body']['box'], wide), sprite.hud_box(statics['plate']['box'], wide)
            self.assertGreaterEqual(plate[1] - bar[1], 2.4, wide)
            self.assertLessEqual(plate[3], sprite.hud_box(statics['housing']['box'], wide)[1] + 1e-6, wide)

    def test_receipts_name_their_sources(self):
        receipts = json.loads((ROOT / 'reports/b76_sb/author_receipts.json').read_text())
        self.assertEqual(receipts['espn_plate_mark']['ink_box'], [910, 956, 1010, 980])
        self.assertEqual(receipts['flag']['yellow'], [205, 198, 0])
        self.assertGreaterEqual(receipts['espn_plate_mark']['frames'], 200)
        self.assertGreaterEqual(receipts['label_Down']['frames'], 150)


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
class OwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.labels = _machine()

    def setUp(self):
        m = self.m
        m.clear_stubs()
        m.uc.mem_write(DATA_VA, bytes(128))
        m.uc.mem_write(SCENE_BASE, bytes(0x100))
        m.put(SCENE_BASE + 0x60, sprite.MAGIC); m.put(SCENE_BASE + 0x64, sprite.TABLE_OFFSET)
        m.put(0xA95528, SCENE_BASE + 256); m.put(0xA95520, 0)             # bar inactive: the update runs its timers only
        m.put(0xA95524, 1)                                                  # the bar draws (the tab counts only then)
        m.put(DATA_VA, SCENE_BASE + 256); m.put(DATA_VA + 4, 1)
        home, away, clock, down = OBJECTS, OBJECTS + 0x40, OBJECTS + 0x80, OBJECTS + 0xC0
        for obj in (home, away, clock, down):
            m.uc.mem_write(obj, bytes(0x40))
        m.put(HOME_SCORE, home); m.put(AWAY_SCORE, away); m.put(home + 4, 3); m.put(away + 4, 3)
        m.put(CLOCK, clock); m.put(clock + 16, bits(300.0))
        m.put(DOWN_OBJECT, down); m.put(down + 4, 1)
        m.put(PHASE, 4); m.put(QUARTER, 1)
        for record in (HANG_TIME, FLAG, BALL_ON, FUMBLE):
            self.event(record, False)
        self.home, self.away, self.clock, self.down = home, away, clock, down

    def event(self, record, visible):
        self.m.put(record + 0x58, 1)
        self.m.put(record + 0x2c, bits(0.0)); self.m.put(record + 0x3c, bits(30.0 if visible else 0.0))

    def text(self):
        # gcc passes a static, non-address-taken function its three arguments in EAX, EDX and ECX.
        return self.m.call(self.labels['text'], eax=DATA_VA, edx=FIELD_VA, ecx=TEXT_VA)

    def update(self, dt=1 / 60):
        self.m.call(self.labels['sprite_update'], args=(DATA_VA, bits(dt) if isinstance(dt, float) else dt))

    def test_espn_plate_mode(self):
        for phase, espn in ((0, 1), (1, 1), (2, 1), (3, 1), (4, 0)):
            self.m.put(PHASE, phase)
            self.assertEqual(self.m.call(self.labels['espn_mode']), espn, phase)
        self.m.put(PHASE, 4)
        for record, espn in ((HANG_TIME, 1), (BALL_ON, 1), (FUMBLE, 1), (FLAG, 0)):
            self.event(record, True)
            self.assertEqual(self.m.call(self.labels['espn_mode']), espn, hex(record))
            self.event(record, False)
        self.m.put(BALL_ON + 0x58, 0); self.m.put(BALL_ON + 0x3c, bits(30.0))   # an unbound record never shows
        self.assertEqual(self.m.call(self.labels['espn_mode']), 0)

    def test_interim_label_timer(self):
        m = self.m
        self.update()                                                       # first sight of down 1
        self.assertEqual((m.get(DATA_VA + DOWN), m.get(DATA_VA + INTERIM)), (1, 0))
        for down in (2, 3, 4):
            m.put(self.down + 4, down); self.update(0.5)
            self.assertAlmostEqual(value(m.get(DATA_VA + INTERIM)), 6.5, places=4)
            self.update(1.0 - 2 ** -20)
            self.assertAlmostEqual(value(m.get(DATA_VA + INTERIM)), 5.5, places=4)
        for step in range(8):
            self.update(0.99)
        self.assertLess(value(m.get(DATA_VA + INTERIM)), 0)                 # expired
        for down, starts in ((1, False), (3, False), (3, False), (4, True), (2, False)):
            m.put(self.down + 4, down); self.update(0.0)
            self.assertEqual(m.get(DATA_VA + INTERIM) == bits(7.0), starts, down)   # only a step to the next down

    def test_frame_time_guard(self):
        m = self.m
        m.put(self.down + 4, 1); self.update(); m.put(self.down + 4, 2); self.update(0.0)
        for dt in (bits(1.0), bits(2.0), bits(-0.25), 0xFFFFFFFF, 0x7F800000):
            self.update(dt)
            self.assertEqual(m.get(DATA_VA + INTERIM), bits(7.0), hex(dt))

    def test_timeout_tab_marks_the_calling_side(self):
        m = self.m
        m.put(DATA_VA + TIMEOUTS, 0x0303)
        self.update()
        self.assertEqual(m.get(DATA_VA + TAB), 0)
        m.put(self.away + 4, 2); self.update(0.0)
        self.assertEqual((m.get(DATA_VA + TAB), m.get(DATA_VA + TAB_SIDE)), (bits(4.0), 1))
        self.update(0.75)
        self.assertAlmostEqual(value(m.get(DATA_VA + TAB)), 3.25, places=4)
        m.put(self.home + 4, 2); self.update(0.0)
        self.assertEqual((m.get(DATA_VA + TAB), m.get(DATA_VA + TAB_SIDE)), (bits(4.0), 2))
        m.put(0xA95524, 0)                                                  # play calling hides the bar: the tab waits
        for _ in range(5):
            self.update(0.99)
        self.assertEqual(m.get(DATA_VA + TAB), bits(4.0))
        m.put(0xA95524, 1)
        for _ in range(5):
            self.update(0.99)
        self.assertLess(value(m.get(DATA_VA + TAB)), 0)
        m.put(self.home + 4, 3); m.put(self.away + 4, 3); self.update(0.0)   # the half's reset only rises
        self.assertLess(value(m.get(DATA_VA + TAB)), 0)
        self.assertEqual(m.get(DATA_VA + TIMEOUTS), 0x0303)
        # The tab field prints its one token for the side the timers name.
        m.uc.mem_write(FIELD_VA, bytes(64)); m.put(FIELD_VA, 13)
        m.put(self.away + 4, 1); self.update(0.0)
        side = self.text()
        self.assertEqual((side, m.wide(TEXT_VA)), (1, 'T'))

    def test_text_sources(self):
        m = self.m
        m.uc.mem_write(FIELD_VA, bytes(64)); m.put(FIELD_VA, 7)
        m.put(PHASE, 2)
        self.assertEqual((self.text(), m.wide(TEXT_VA)), (1, 'ESPN'))
        for side, key in ((2, 'home'), (3, 'away')):                        # ticks print the timeouts left
            m.put(FIELD_VA, side)
            self.assertEqual((self.text(), m.wide(TEXT_VA)), (1, '3'), key)


@unittest.skipUnless(XBE.is_file(), 'pinned USA XBE required')
class RetailProofTests(unittest.TestCase):
    def test_retail_spans_match_their_pins(self):
        data = _retail()
        if data is None:
            self.skipTest('retail XBE pin differs')
        from test_nfl2k5_franchise_records import XbeImage
        image = XbeImage(data)
        for name, (va, size, digest) in PINS.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(image.read(va, size)).hexdigest(), digest)


@unittest.skipUnless(NATIVE, 'Pinned USA retail XBE/pack and Unicorn required')
class NativePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview = sprite.NativePreview()

    def capture(self, widescreen=False, **state):
        g, c = self.preview.capture(state, widescreen)
        self.addCleanup(c['machine'].close)
        return g, c

    def rows(self, wide, name):
        return sorted((q for q in self.preview.modes[wide]['compiled'].quads if q['name'].split(':')[0] == name),
                      key=lambda q: q['vertex'])

    def colour(self, c, quad):
        return struct.unpack_from('<I', c['live_decoded'], 0x2d20 + quad['vertex'] * 10)[0]

    def visible(self, c, wide, name):
        return [q for q in self.rows(wide, name) if self.colour(c, q)]

    def uv(self, c, quad):
        return tuple(struct.unpack_from('<h', c['live_decoded'], 0x2d20 + (quad['vertex'] + j) * 10 + 4 + k * 2)[0]
                     for j in range(4) for k in range(2))

    def glyph_uv(self, wide, glyph_set, token):
        compiled = self.preview.modes[wide]['compiled']
        cell = compiled.spec['glyph_sets'][glyph_set]['glyphs'][token]['cell']
        return sprite.quantized_uv(compiled.cells[cell], compiled.spec['atlas'])

    def tokens(self, c, wide, name, glyph_set):
        return [self.uv(c, q) for q in self.visible(c, wide, name)], \
            {t: self.glyph_uv(wide, glyph_set, t) for t in self.preview.modes[wide]['compiled'].spec['glyph_sets'][glyph_set]['glyphs']}

    def box(self, g, quads):
        points = [p for q in quads for p in g['positions'][q['vertex']:q['vertex'] + 4]]
        return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]

    def assert_espn_plate(self, g, c, wide, why):
        quads = self.visible(c, wide, 'down')
        self.assertEqual([self.uv(c, q) for q in quads], [self.glyph_uv(wide, 'label', 'ESPN')], why)
        self.assertEqual(self.colour(c, self.rows(wide, 'plate')[0]), ESPN_PLATE, why)
        mark, plate = self.box(g, quads), self.box(g, self.rows(wide, 'plate'))
        self.assertTrue(plate[0] <= mark[0] and mark[2] <= plate[2] and plate[1] <= mark[1] and mark[3] <= plate[3], why)
        self.assertLess(abs((mark[0] + mark[2]) / 2 - (plate[0] + plate[2]) / 2), 1.5, why)   # HUD px

    def event_plate_hidden(self, c, record):
        m = c['machine']
        material = m.get(record + 0x44)
        return bool(m.get(material + 8) & 1)

    def test_espn_plate_in_every_no_down_phase(self):
        for wide in (False, True):
            for phase in (0, 1, 2, 3):
                g, c = self.capture(wide, phase=phase)
                self.assert_espn_plate(g, c, wide, (wide, phase))
            g, c = self.capture(wide, phase=4)
            self.assertNotEqual(self.colour(c, self.rows(wide, 'plate')[0]), ESPN_PLATE)
            self.assertEqual(len(self.visible(c, wide, 'down')), 5)            # "3rd & 10"

    def test_espn_plate_replaces_hang_time_ball_on_and_fumble_and_flag_keeps_its_plate(self):
        for event, record in (('hang time', HANG_TIME), ('ball on', BALL_ON), ('FUMBLE', FUMBLE)):
            g, c = self.capture(False, event=event)
            self.assert_espn_plate(g, c, False, event)
            self.assertTrue(self.event_plate_hidden(c, record), event)
            self.assertFalse(any(row['vertices'] for row in g['draws']), event)   # no retail text either
        g, c = self.capture(False, event='FLAG')
        self.assertEqual(self.visible(c, False, 'down'), [])
        self.assertFalse(self.event_plate_hidden(c, FLAG))

    def test_interim_label(self):
        for wide in (False, True):
            g, c = self.capture(wide, down=3, distance=4, previous_down=2)
            drawn, uv = self.tokens(c, wide, 'down', 'label')
            self.assertEqual(drawn, [uv['3'], uv['rd'], uv['Down']])
            g, c = self.capture(wide, down=3, distance=4)
            drawn, uv = self.tokens(c, wide, 'down', 'label')
            self.assertEqual(drawn, [uv['3'], uv['rd'], uv['&'], uv['4']])

    def test_clock_drops_the_minute_under_one_minute(self):
        for seconds, expected in ((54, [':', '5', '4']), (5, [':', '0', '5']), (0, [':', '0', '0']), (60, ['1', ':', '0', '0']),
                                  (600, ['1', '0', ':', '0', '0'])):
            g, c = self.capture(False, clock=seconds, quarter=3)
            drawn, uv = self.tokens(c, False, 'clock', 'clock')
            self.assertEqual(drawn, [uv[t] for t in expected], seconds)

    def test_play_clock_turns_red_at_five_and_under(self):
        for wide in (False, True):
            for seconds, red in ((4, True), (5, True), (6, False), (40, False)):
                g, c = self.capture(wide, play_clock=seconds)
                cell = self.colour(c, self.rows(wide, 'red')[0])
                digits = {self.colour(c, q) for q in self.visible(c, wide, 'play_clock')}
                self.assertEqual((cell, digits), (PLAY_CLOCK_RED, {0xFFFFFFFF}) if red else (0xFFFFFFFF, {0xFF171717}), seconds)

    def test_end_of_the_half_keeps_quarter_and_clock(self):
        # HALFTIME was removed after lab run 2 (the game hides the bar at the half); the capsule stays retail-driven.
        for wide in (False, True):
            g, c = self.capture(wide, phase=0, quarter=2, clock=0)
            drawn, uv = self.tokens(c, wide, 'clock', 'clock')
            self.assertEqual(drawn, [uv[':'], uv['0'], uv['0']])
            self.assertEqual(len(self.visible(c, wide, 'quarter')), 1)
            self.assert_espn_plate(g, c, wide, 'end of the half')

    def test_timeout_tab_over_the_calling_side(self):
        for wide in (False, True):
            g, c = self.capture(wide)
            self.assertEqual(self.visible(c, wide, 'timeout_tab'), [])
            centres = {}
            for side in ('away', 'home'):
                g, c = self.capture(wide, timeout_called=side, **{side + '_timeouts': 2})
                tab = self.visible(c, wide, 'timeout_tab')
                self.assertEqual(len(tab), 1, side)
                box, bar = self.box(g, tab), g['frame']
                self.assertLess(box[3], bar[1] + 0.5, side)                   # sits on top of the bar
                centres[side] = (box[0] + box[2]) / 2
                wing = self.box(g, self.rows(wide, side + '_wing'))
                self.assertTrue(wing[0] - 1 <= centres[side] <= wing[2] + 1, side)
            self.assertLess(centres['away'], centres['home'])


if __name__ == '__main__':
    unittest.main()


# Beta 76 sb B1 (play calling). Retail spans the B1 edits rely on (SHA-256 only).
PLAYCALL_PINS = {
    'per-frame hide call 0x8BEA0': (0x08bea0, 0x0d, 'b0fed006e681aecf856735c2819ac0d4cfc4e17d7a1aa9179a3d48bb184b7e05'),
    'play-call bar draw 0x8C450 entry and mode gate': (0x08c450, 0x1b, 'f5f706ef53e6496415c530ed5223dd2cd7eeca4de67796bb3fa8214bab3c6394'),
    'play-call bar draw 0x8C450 exit': (0x08c982, 0x06, '1b7b147669549be5375a76a99768a4ee83fb99244ccee93704301fc79d582b1b'),
    'play-call bar draw 0x8CA00 entry and mode gate': (0x08ca00, 0x2a, '8bb622d44438b1a26250f84a38c9e0e925581386d7990e1ea94dd41f7ccde56d'),
    'play-call bar draw 0x8CA00 exit': (0x08cf3f, 0x08, '4af066e9babe398f7a2680a76d6d195edcf6dd4d57fec3c2d0633d81f4339a07'),
}
MODE, MODE_SCENE, DRAW, AUTO = 0xB641B4, 0xB641B0, 0xA95524, 0xA957E0


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE and Unicorn required')
class PlayCallTests(unittest.TestCase):
    """B1: the bar stays up through play calling; the retail play-call bar's two draws take their mode-off exits."""

    @classmethod
    def setUpClass(cls):
        cls.m, cls.labels = _machine()

    def setUp(self):
        m = self.m
        m.uc.mem_write(DATA_VA, bytes(128))
        m.uc.mem_write(SCENE_BASE, bytes(0x100))
        m.put(SCENE_BASE + 0x60, sprite.MAGIC); m.put(SCENE_BASE + 0x64, sprite.TABLE_OFFSET)
        m.put(0xA95528, SCENE_BASE + 256); m.put(0xA95520, 0)
        m.put(DATA_VA, SCENE_BASE + 256); m.put(DATA_VA + 4, 1)
        m.put(DOWN_OBJECT, 0); m.put(HOME_SCORE, 0); m.put(AWAY_SCORE, 0)
        self.retail_gate = bytes(m.uc.mem_read(0x8C465, 6))

    def tearDown(self):
        self.m.uc.mem_write(0x8C465, self.retail_gate)

    def test_hide_keeps_the_bar_only_while_the_play_call_mode_is_on(self):
        m = self.m
        for mode, scene, hidden in ((1, 1, False), (0, 1, True), (1, 0, True), (0, 0, True)):
            m.put(MODE, mode); m.put(MODE_SCENE, scene); m.put(DRAW, 1); m.put(AUTO, 1)
            m.call(self.labels['sprite_playcall_hide'])
            self.assertEqual((m.get(DRAW), m.get(AUTO)), (0, 0) if hidden else (1, 1), (mode, scene))

    def test_update_reshows_the_bar_only_with_the_build_guard(self):
        m = self.m
        m.put(MODE, 1); m.put(MODE_SCENE, 1)
        for gate, shown in ((bytes.fromhex('e91805000090'), 1), (self.retail_gate, 0)):
            m.uc.mem_write(0x8C465, gate); m.put(DRAW, 0)
            m.call(self.labels['sprite_update'], args=(DATA_VA, 0))
            self.assertEqual(m.get(DRAW), shown, gate.hex())
        m.uc.mem_write(0x8C465, bytes.fromhex('e91805000090')); m.put(MODE, 0); m.put(DRAW, 0)
        m.call(self.labels['sprite_update'], args=(DATA_VA, 0))
        self.assertEqual(m.get(DRAW), 0)                                    # outside play calling: retail decides

    def test_retail_spans_match_their_pins(self):
        from test_nfl2k5_franchise_records import XbeImage
        image = XbeImage(_retail())
        for name, (va, size, digest) in PLAYCALL_PINS.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(image.read(va, size)).hexdigest(), digest)

    def test_the_guards_jump_to_the_draws_own_mode_off_exits(self):
        for va, retail, patched, exit_va in ((0x8C465, '0f8417050000', 'e91805000090', 0x8C982),
                                             (0x8CA18, '0f8421050000', 'e92205000090', 0x8CF3F)):
            je = struct.unpack('<i', bytes.fromhex(retail)[2:])[0] + va + 6
            jmp = struct.unpack('<i', bytes.fromhex(patched)[1:5])[0] + va + 5
            self.assertEqual((je, jmp), (exit_va, exit_va), hex(va))
        self.assertEqual([(va, old.hex(), new.hex()) for va, old, new, _ in owner.PLAYCALL_EDITS],
                         [(0x8C465, '0f8417050000', 'e91805000090'), (0x8CA18, '0f8421050000', 'e92205000090')])


@unittest.skipUnless(XBE.is_file(), 'pinned USA XBE required')
class PlayCallBuildTests(unittest.TestCase):
    """The runtime writer applies B1 by default and keeps retail play calling with NFL2K5_SCOREBUG_PLAYCALL=retail."""

    def test_both_builds_apply_and_recognize_only_themselves(self):
        import os
        from unittest import mock
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        retail = _retail()
        if retail is None:
            self.skipTest('retail XBE pin differs')
        builds = {}
        for mode in ('sprite', 'retail'):
            with mock.patch.dict(os.environ, {'NFL2K5_SCOREBUG_PLAYCALL': mode}):
                patched, receipt = owner.apply(retail)
                self.assertEqual(owner.status(patched), 'applied', mode)
                builds[mode] = patched
                code, data = owner.sites(patched)
                labels = owner.code_for(code['va'], data['va'])[1]
                at = lambda va, n: patched[scene.layout.sbpos.va_to_off(patched, va):scene.layout.sbpos.va_to_off(patched, va) + n]
                hook = b'\xe8' + struct.pack('<i', labels['sprite_playcall_hide'] - 0x8BEA0 - 5)
                if mode == 'sprite':
                    self.assertEqual((at(0x8BEA0, 5), at(0x8C465, 6), at(0x8CA18, 6)),
                                     (hook, bytes.fromhex('e91805000090'), bytes.fromhex('e92205000090')))
                else:
                    self.assertEqual((at(0x8BEA0, 5), at(0x8C465, 6), at(0x8CA18, 6)),
                                     (bytes.fromhex('e80b080700'), bytes.fromhex('0f8417050000'), bytes.fromhex('0f8421050000')))
        with mock.patch.dict(os.environ, {'NFL2K5_SCOREBUG_PLAYCALL': 'retail'}):
            self.assertEqual(owner.status(builds['sprite']), 'foreign')
        with mock.patch.dict(os.environ, {'NFL2K5_SCOREBUG_PLAYCALL': 'sprite'}):
            self.assertEqual(owner.status(builds['retail']), 'foreign')
