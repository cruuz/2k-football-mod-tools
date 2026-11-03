"""b780 p2-playcall: the ball spot beside the down and distance on the play-call screen (2026 bar).

nwostar 10/24: "Add down distance and field position to play call screen." The sprite bar showed the down and distance
only. While the play-call screen keeps the bar up, the engine now appends the retail "Ball on" text (FBEB0) to the down
text as "NYJ 35" (own or opposing side), or "50" at midfield. The scene has no spare quad, so the team is one word
cell (U+0001 + abbreviation), the yard line two small digit cells, and the spaces cost no slot.

Art and layout checks need only Pillow; the engine checks run the real owner in Unicorn on the retail XBE (skipped when
the pinned USA XBE/pack or Unicorn is absent).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core import nfl2k5_scorebug_ingame as scene

HAVE_IMAGES = all(importlib.util.find_spec(n) for n in ('PIL', 'numpy'))
RETAIL = ROOT / 'extracted/ESPN NFL 2K5 (USA)/default.xbe'
PACK = RETAIL.parent / 'vc_53450030/0'
NATIVE = RETAIL.is_file() and PACK.is_file() and importlib.util.find_spec('unicorn') is not None and HAVE_IMAGES
AUTHOR = ROOT / 'reports/b780_p2/author_ball_spot.py'
WORD_MARK, DIGIT_BASE, SPACE = chr(1), 16, chr(26)
DT = struct.unpack('<I', struct.pack('<f', 1 / 60))[0]


def author():
    spec = importlib.util.spec_from_file_location('b780_p2_author_ball_spot', AUTHOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def label_tokens(text, glyphs):
    """The engine's match: the first token in table order ((-len, token), as compiled) the text starts with."""
    order = sorted(glyphs, key=lambda t: (-len(t), t))
    out, at = [], 0
    while at < len(text):
        token = next((t for t in order if text.startswith(t, at)), None)
        if token is None:
            return None
        out.append(token)
        at += len(token)
    return out


def spot_text(abbreviation, yards):
    return ' ' + SPACE + WORD_MARK + abbreviation + SPACE + ''.join(chr(DIGIT_BASE + int(c)) for c in str(yards))


@unittest.skipUnless(HAVE_IMAGES, 'Pillow and numpy required')
class ArtAndLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.author = author()
        cls.spec, cls.template = sprite.load_layout()
        cls.template = cls.template.convert('RGBA')
        cls.receipts = json.loads((ROOT / 'reports/b780_p2/author_receipts.json').read_text(encoding='utf-8'))
        cls.label = cls.spec['glyph_sets']['label']['glyphs']
        cls.field = next(f for f in cls.spec['fields'] if f['name'] == 'down')

    def test_cells_are_the_authored_pixels_eight_rows_tall(self):
        names = self.author.ABBREVIATIONS + tuple(self.author.DIGITS)
        self.assertEqual(set(self.receipts), set(names))
        for item in names:
            box = self.spec['cells']['spot_' + item]['box']
            cell = self.template.crop(tuple(box))
            self.assertEqual(box, self.receipts[item]['cell'], item)
            self.assertEqual(cell.size, tuple(self.receipts[item]['texels']), item)
            self.assertEqual(cell.height, 8, item)
            self.assertEqual(hashlib.sha256(cell.tobytes()).hexdigest(), self.receipts[item]['sha256'], item)
            pixels = list(cell.getdata())
            self.assertTrue(all(p[:3] == (255, 255, 255) for p in pixels), 'white coverage cells: ' + item)
            self.assertGreater(sum(p[3] for p in pixels), 0, item)
            # Letters and digits stand on the baseline and reach the cap: ink in the top and bottom rows.
            self.assertTrue(any(p[3] > 0 for p in list(cell.crop((0, 0, cell.width, 1)).getdata())), item)
            self.assertTrue(any(p[3] > 0 for p in list(cell.crop((0, 7, cell.width, 8)).getdata())), item)

    def test_no_cell_overlaps_another_and_none_is_drawn_outside_a_cell(self):
        import numpy as np
        boxes = [(n, tuple(c['box'])) for n, c in self.spec['cells'].items()]
        spots = [(n, b) for n, b in boxes if n.startswith('spot_')]
        self.assertEqual(len(spots), 46)
        for i, (n, a) in enumerate(boxes):
            for m, b in boxes[i + 1:]:
                if n.startswith('spot_') or m.startswith('spot_'):
                    self.assertFalse(max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3]), (n, m))
        alpha = np.asarray(self.template)[..., 3] > 0
        covered = np.zeros_like(alpha)
        for _n, b in spots:
            covered[b[1]:b[3], b[0]:b[2]] = True
        rows = slice(min(b[1] for _n, b in spots), max(b[3] for _n, b in spots))
        self.assertFalse((alpha[rows] & ~covered[rows]).any(), 'ink outside the spot cells in their rows')

    def test_tokens_metrics_and_no_collision_with_the_down_text(self):
        a = self.author
        self.assertEqual(a.WORD_MARK, WORD_MARK)
        self.assertEqual((a.DIGIT_BASE, a.SPACE_TOKEN), (DIGIT_BASE, SPACE))
        before = [t for t in self.label if not (t.startswith(WORD_MARK) or (len(t) == 1 and ord(t) < 32))]
        # The down text's own tokens are untouched: ordinals, digits, ampersand, words, the label space, ESPN, Down.
        for token in ('1', '0', 'st', 'nd', 'rd', 'th', '&', 'Goal', 'GOAL', 'Inch', 'es', ' ', 'ESPN', 'Down'):
            self.assertIn(token, before)
        self.assertEqual(self.label[' ']['cell'], 'tick')
        self.assertEqual(self.label[' ']['size'], [0, 0])
        for abbreviation in a.ABBREVIATIONS:
            row = self.label[WORD_MARK + abbreviation]
            self.assertEqual(row['cell'], 'spot_' + abbreviation)
            self.assertEqual((row['size'][1], row['raise']), (25.0, -5.0))
            self.assertGreater(row['advance'], row['size'][0])
        for digit in a.DIGITS:
            row = self.label[chr(DIGIT_BASE + int(digit))]
            self.assertEqual((row['cell'], row['size'][1], row['raise']), ('spot_' + digit, 25.0, -5.0))
        self.assertEqual(self.label[SPACE], {'cell': 'tick', 'size': [0, 0], 'advance': 9.0})
        # A spot digit is the plain digit's traced shape at 5/6 the height: same aspect.
        for digit in a.DIGITS:
            plain, small = self.label[digit]['size'], self.label[chr(DIGIT_BASE + int(digit))]['size']
            self.assertAlmostEqual(small[0] / small[1], plain[0] / plain[1], delta=.01)
        # The spot never tokenizes into the down text's cells, and the down text never into the spot's.
        self.assertEqual(label_tokens('1st & 10', self.label), ['1', 'st', ' ', '&', ' ', '1', '0'])
        self.assertEqual(label_tokens(spot_text('STL', 35), self.label),
                         [' ', SPACE, WORD_MARK + 'STL', SPACE, chr(DIGIT_BASE + 3), chr(DIGIT_BASE + 5)])

    def test_every_abbreviation_the_game_prints_has_a_word(self):
        known, found = set(self.author.ABBREVIATIONS), {}
        keys = ('abbreviation', 'city_abbreviation', 'label_abbreviation')

        def walk(node, source):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in keys and isinstance(value, str):
                        found.setdefault(value, source)
                    walk(value, source)
            elif isinstance(node, list):
                for value in node:
                    walk(value, source)
        for path in sorted((ROOT / 'data').rglob('*.json')):
            if path.stat().st_size > 8 * 1024 * 1024:
                continue
            try:
                walk(json.loads(path.read_text(encoding='utf-8')), path.name)
            except ValueError:
                continue
        self.assertGreaterEqual(len(found), 30)
        self.assertEqual({a: s for a, s in found.items() if a not in known}, {},
                         'a team abbreviation in the game data has no ball-spot word: run reports/b780_p2/author_ball_spot.py '
                         'after adding it to ABBREVIATIONS')

    def test_scene_budget_unchanged_the_spot_uses_the_down_fields_own_quads(self):
        for wide in (False, True):
            compiled = sprite.compile_folder(None, wide)
            self.assertEqual(len(compiled.quads), 50, wide)
            self.assertEqual(sum(1 for q in compiled.quads if q['name'].startswith('down:')), 8, wide)
        self.assertEqual(self.field['slots'], 8)
        self.assertEqual(self.field['box'], [845, 955, 1077, 979])
        self.assertEqual((self.field['box'][0] + self.field['box'][2]) / 2, self.field['anchor'][0])
        self.assertLess(sprite.probe_sizes()[1], 400 * 1024)
        self.assertLessEqual(len(self.label), 128)

    def test_every_realistic_line_fits_the_slots_and_the_squeeze_limit(self):
        """Drawn quads (spaces cost none) and width against the field box, for every down, distance, team and yard."""
        label, factor = self.label, self.field['size'] / self.spec['glyph_sets']['label']['cap_height']
        room = self.field['box'][2] - self.field['box'][0]

        def width(tokens):
            advance = sum(label[t]['advance'] for t in tokens)
            last = label[tokens[-1]]
            return (advance - (last['advance'] - last['size'][0])) * factor

        def drawn(tokens):
            return sum(1 for t in tokens if label[t]['size'][0] and label[t]['size'][1])
        worst = 0.0
        for ordinal in ('1st', '2nd', '3rd', '4th'):
            for distance in list(range(1, 100)) + ['GOAL', 'Inches']:
                base = label_tokens(f'{ordinal} & {distance}', label)
                self.assertIsNotNone(base)
                self.assertLessEqual(width(base), room, (ordinal, distance))     # the down text alone never squeezes
                for abbreviation in self.author.ABBREVIATIONS:
                    for yards in (1, 9, 10, 35, 50):
                        tokens = base + label_tokens(spot_text(abbreviation, yards), label)
                        self.assertLessEqual(drawn(tokens), 8, (ordinal, distance, abbreviation, yards))
                        if distance != 'Inches':
                            if not (distance == 'GOAL' and yards > 10):          # goal to go is inside the 10
                                worst = max(worst, width(tokens) / room)
        self.assertLessEqual(worst, 1.30, 'the widest real line needs at most the 23 percent squeeze the engine allows')
        self.assertGreater(worst, 1.2)                   # "2nd & GOAL  WAS 10" is that widest line (about 21 percent)
        # "Inches" is the down text too wide for most spots; the engine then keeps the down text alone.
        wide = label_tokens('3rd & Inches', label) + label_tokens(spot_text('NYJ', 35), label)
        self.assertGreater(width(wide) / room, 1.30)


def decode_quads(mode, capture):
    """Tokens drawn by the down field this frame, in quad order: [(token, x0, x1, y_top, y_bottom, colour)]."""
    m, body = capture['machine'], capture['body']
    compiled = mode['compiled']
    glyphs = compiled.spec['glyph_sets']['label']['glyphs']
    by_uv = {}
    for token, row in glyphs.items():
        uv = tuple(sprite.quantized_uv(compiled.cells[row['cell']], compiled.spec['atlas'])[0:2])
        by_uv.setdefault(uv, []).append(token)
    out = []
    for q in (q for q in compiled.quads if q['name'].startswith('down:')):
        v = q['vertex']
        colour = m.get(body + scene.layout.S1 + v * 10)
        if not colour:
            continue
        pos = [struct.unpack('<3h', bytes(m.uc.mem_read(body + scene.layout.S0 + (v + j) * 6, 6))) for j in range(4)]
        uv = struct.unpack('<2h', bytes(m.uc.mem_read(body + scene.layout.S1 + v * 10 + 4, 4)))
        out.append((by_uv.get(tuple(uv), ['?'])[0], pos[0][0], pos[3][0], pos[0][1], pos[3][1], colour))
    return out


@unittest.skipUnless(NATIVE, 'pinned USA retail XBE/pack, Unicorn and Pillow required')
class EngineTests(unittest.TestCase):
    """The real owner in Unicorn. One retained machine per aspect; each case sets the game state and runs real frames."""

    @classmethod
    def setUpClass(cls):
        import nfl2k5_scorebug_projection as projection
        cls.preview = sprite.NativePreview()
        cls.bars = {}
        for wide in (False, True):
            mode, capture = cls.preview.modes[wide], {}
            projection.native_geometry(cls.preview.payload, mode['scene'], fonts=cls.preview.fonts,
                                       texture_span=mode['atlas'], runtime_textures=mode['textures'], capture=capture,
                                       widescreen=wide, identity=dict(home='KC', away='DAL'), possession='away',
                                       game_seconds=300, playcall=True, ball_yards=35, down=1, distance_yards=10)
            capture['machine'].record = False
            cls.bars[wide] = (mode, capture)
        cls.addClassCleanup(lambda: [c['machine'].close() for _m, c in cls.bars.values()])

    def bar(self, wide, *, home='KC', away='DAL', possession='away', yards=35, down=1, distance=10, goal=False,
            phase=4, playcall=True, previous_down=None, kick=False):
        """Set the game state on the retained machine, run the frames the owner needs, return the down field's tokens."""
        mode, capture = self.bars[wide]
        m = capture['machine']
        m.identity(home=home, away=away)
        m.put(0xe60280, 0xe5fc20 if possession == 'home' else 0xe5fc60)
        m.put(0xe60284, 0xe5fc60 if possession == 'home' else 0xe5fc20)
        m.float(m.play + 0x38, (yards - 50) * 91.44)
        m.float(m.play + 0x28, distance * 91.4)
        code = (b'\xe9' + struct.pack('<i', 0xfbd50 - 0xfc765)) if goal else bytes.fromhex('d9eec3')
        m.uc.mem_write(0xfc760, code)
        m.uc.ctl_remove_cache(0xfc760, 0xfc765)
        m.put(0xe602b4, phase)
        m.put(0xb641b4, int(playcall)); m.put(0xb641b0, int(playcall))
        m.put(0xba2f10, int(kick))
        if previous_down is not None:
            m.put(m.play + 4, previous_down)
            m.run(0xfce70, (DT,), limit=500000)
        m.put(m.play + 4, down)
        for _ in range(2):
            m.run(0xfce70, (DT,), limit=500000)
        return decode_quads(mode, capture)

    def test_own_opposing_and_midfield_spots_both_aspects_and_sides(self):
        word = lambda a: WORD_MARK + a
        digits = lambda n: [chr(DIGIT_BASE + int(c)) for c in str(n)]
        cases = (
            # (possession, ball yards from the offense's own goal, expected team word, yard line)
            ('away', 35, 'DAL', 35), ('away', 65, 'KC', 35), ('away', 1, 'DAL', 1), ('away', 99, 'KC', 1),
            ('home', 20, 'KC', 20), ('home', 80, 'DAL', 20), ('away', 50, None, 50), ('home', 50, None, 50))
        for wide in (False, True):
            for possession, yards, team, line in cases:
                got = [r[0] for r in self.bar(wide, possession=possession, yards=yards)]
                want = ['1', 'st', '&', '1', '0'] + ([word(team)] if team else []) + digits(line)
                self.assertEqual(got, want, (wide, possession, yards))

    def test_spot_follows_other_downs_distances_and_goal_to_go(self):
        got = [r[0] for r in self.bar(False, down=3, distance=12, yards=22, away='WAS')]
        self.assertEqual(got, ['3', 'rd', '&', '1', '2', WORD_MARK + 'WAS', chr(DIGIT_BASE + 2), chr(DIGIT_BASE + 2)])
        got = [r[0] for r in self.bar(True, down=4, distance=3, goal=True, yards=97, possession='home')]
        self.assertEqual(got, ['4', 'th', '&', 'GOAL', WORD_MARK + 'DAL', chr(DIGIT_BASE + 3)])
        self.bar(True)                                    # leave goal to go

    def test_no_spot_off_the_play_call_screen(self):
        for wide in (False, True):
            self.assertEqual([r[0] for r in self.bar(wide, playcall=False)], ['1', 'st', '&', '1', '0'])
            self.assertEqual(len(self.bar(wide, playcall=True)), 8)

    def test_other_phases_and_kick_attempts_show_no_spot(self):
        for phase in (0, 1, 2, 3):
            self.assertEqual([r[0] for r in self.bar(False, phase=phase)], ['ESPN'], phase)
        self.assertEqual(len(self.bar(False)), 8)
        # The kick attempt label ("35 yd FG") replaces "Ball on" in the retail formatter: not a spot.
        self.assertEqual([r[0] for r in self.bar(False, kick=True)], ['1', 'st', '&', '1', '0'])
        self.assertEqual(len(self.bar(False)), 8)

    def test_a_team_without_a_word_keeps_the_down_text_alone(self):
        self.assertEqual([r[0] for r in self.bar(False, away='ZZZ')], ['1', 'st', '&', '1', '0'])
        self.assertEqual([r[0] for r in self.bar(False, away='D4L')], ['1', 'st', '&', '1', '0'])
        self.assertEqual(len(self.bar(False)), 8)

    def test_a_line_too_wide_for_the_plate_drops_the_spot_not_the_down_text(self):
        # distance 0 prints "Inches": 3rd & INCHES plus a team and yard line needs more than the 23 percent squeeze.
        self.assertEqual([r[0] for r in self.bar(False, down=3, distance=0)], ['3', 'rd', '&', 'Inch', 'es'])
        self.assertEqual(len(self.bar(False)), 8)

    def test_play_call_shows_the_distance_not_the_interim_down_label(self):
        # The step to 2nd down starts the 7 s "2nd Down" label; the play-call screen is where the distance is read.
        self.assertEqual([r[0] for r in self.bar(False, down=2, previous_down=1, distance=7, playcall=False)],
                         ['2', 'nd', 'Down'])
        self.assertEqual([r[0] for r in self.bar(False, down=2, previous_down=1, distance=7, playcall=True)][:4],
                         ['2', 'nd', '&', '7'])
        self.bar(False)

    def test_geometry_baseline_order_colour_and_the_plate(self):
        for wide in (False, True):
            rows = self.bar(wide, yards=35)
            mode, capture = self.bars[wide]
            self.assertEqual(len(rows), 8)
            base, spot = rows[:5], rows[5:]
            self.assertTrue(all(r[5] == 0xffffffff for r in rows))
            bottoms = [r[4] for r in rows]
            self.assertLessEqual(max(bottoms) - min(bottoms), 2, 'one baseline for the down text and the spot (two units of rounding)')
            self.assertTrue(all(s[3] < base[0][3] for s in spot), 'the spot is the smaller text (scene y grows upward)')
            self.assertEqual([r[1] for r in rows], sorted(r[1] for r in rows), 'left to right')
            self.assertGreater(spot[0][1], base[-1][2], 'a gap separates the spot from the down text')
            # Everything lies inside the plate quad and the line is centred on it.
            plate = next(q for q in mode['compiled'].quads if q['name'] == 'plate')
            m, body = capture['machine'], capture['body']
            xs = [struct.unpack('<3h', bytes(m.uc.mem_read(body + scene.layout.S0 + (plate['vertex'] + j) * 6, 6)))[0] for j in range(4)]
            self.assertGreater(min(r[1] for r in rows), min(xs))
            self.assertLess(max(r[2] for r in rows), max(xs))
            centre = (min(r[1] for r in rows) + max(r[2] for r in rows)) / 2
            self.assertAlmostEqual(centre, (min(xs) + max(xs)) / 2, delta=abs(max(xs) - min(xs)) * .04)

    def test_a_down_change_rewrites_only_the_down_fields_quads(self):
        # The spot lives in the down field's own eight quads; no other quad's position, colour or texture moves.
        mode, capture = self.bars[False]
        m, body = capture['machine'], capture['body']
        down = [q for q in mode['compiled'].quads if q['name'].startswith('down:')]
        first, last = down[0]['vertex'], down[-1]['vertex'] + 4
        count = scene.layout.VCOUNT

        def snapshot():
            positions = bytes(m.uc.mem_read(body + scene.layout.S0, count * 6))
            colours = bytes(m.uc.mem_read(body + scene.layout.S1, count * 10))
            return [(positions[v * 6:(v + 1) * 6], colours[v * 10:(v + 1) * 10]) for v in range(count)]
        self.bar(False, down=1)
        before = snapshot()
        self.bar(False, down=3, distance=4)
        after = snapshot()
        self.assertNotEqual([before[v] for v in range(first, last)], [after[v] for v in range(first, last)])
        self.assertEqual([before[v] for v in range(count) if not first <= v < last],
                         [after[v] for v in range(count) if not first <= v < last])
    def test_the_engine_leaves_the_strip_flag_word_of_its_data_page_alone(self):
        # The page strip fit keeps FUN_000AAFD0's second argument in the owner's data page at +124 (nfl2k5_playcall_layout.
        # STRIP_FLAG_OFFSET); the engine's State is 120 bytes, so setup, update and every spot case must not touch it.
        from mod_editor.core import nfl2k5_playcall_layout as pc
        patched = owner.apply(self.preview.payload)[0]
        _code, data = owner.sites(patched)
        self.assertGreaterEqual(owner.DATA_SIZE, pc.STRIP_FLAG_OFFSET + 4)
        mode, capture = self.bars[False]
        m = capture['machine']
        at = data['va'] + pc.STRIP_FLAG_OFFSET
        m.put(at, 0xdeadbeef)
        for kwargs in (dict(), dict(possession='home', yards=65), dict(playcall=False), dict(phase=2), dict(down=3, distance=0)):
            self.bar(False, **kwargs)
        self.assertEqual(m.get(at), 0xdeadbeef)
        m.put(at, 0)
        self.bar(False)


if __name__ == '__main__':
    unittest.main()
