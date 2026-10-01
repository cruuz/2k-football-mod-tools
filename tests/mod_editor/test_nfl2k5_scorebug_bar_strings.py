"""Beta 76 sbfix: every string the retail formatters hand the sprite bar draws, and draws in the bar's own glyphs.

In game (km2 lab 1, frame game-0265s) the down plate read "3rd & 1nCh6s". The retail down formatter FC7D0 prints
"%s & %s" from "1st".."4th" and "%d", "Goal" or "Inches"; the sprite runtime (tools/scorebug_sprite/runtime.c)
matches the text against its glyph tokens longest first and draws nothing unless every character is covered. The
words "Inch" + "es" were covered, but by beta 72 reconstructions (I from the numeral 1, c and e cut from 0). The
quarter formatter FC090 prints "OT%d" in overtime: "OT1" drew "0T" and "OT2" onward had no token (a blank pill).

The 2026 ESPN bar writes its only word distance in capitals (GOAL; 398 s of the full Broncos at Chiefs broadcast, no
Inches plate in the game), so reports/b76_sbfix/author.py draws "Inches" as INCHES and every overtime period as OT,
from the traced broadcast masks in reports/b72_s9. Nothing here is an in-game result.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402
from test_nfl2k5_franchise_records import XBE, _retail  # noqa: E402

ORDINALS = ('1st', '2nd', '3rd', '4th')
# The retail literals the bar's formatters print (UTF-16, USA XBE). FC7D0's other phases ("Pregame", "Overtime",
# "Safety Kick", "Kickoff", "Point After") never reach the glyphs: the runtime shows the ESPN wordmark plate there.
LITERALS = {0xE6C3E4: '1st', 0xE6C3EC: '2nd', 0xE6C3F4: '3rd', 0xE6C3FC: '4th', 0xE6C404: 'Goal', 0xE6C410: '%d',
            0xE6C418: 'Inches', 0xE6C428: '%s & %s', 0xE6C438: ':%02d', 0xE6C4E4: 'OT%d', 0xE6C4F0: '%d:%02d',
            0xE6C380: 'Pregame', 0xE6C390: 'Overtime', 0xE6C3A4: 'Safety Kick', 0xE6C3BC: 'Kickoff', 0xE6C3CC: 'Point After'}
# (va, size, sha256) of the formatter code that picks those literals; no retail bytes live here.
SPANS = {
    'down and distance FC859': (0x0fc859, 0x135, '29931001899b28b040a5da87508424fb5a0e5ed83f6c197ad2eea376b0d42247'),
    'down table FC9A4': (0x0fc9a4, 0x10, '1673dd30d0d2bae3cb358b49ce22669d7374bb248cb528b1b2ec581f6a67110f'),
    'quarter FC090': (0x0fc090, 0x5e, '76bc4e8f835388e4c486784d2faa2d45cb263547be1b31ca8b3ecf801a3f497a'),
}


def strings():
    """Field name -> every text the retail formatters (with the static layer's edits) can hand that field."""
    down = [f'{o} & {d}' for o in ORDINALS for d in [str(n) for n in range(1, 100)] + ['Goal', 'GOAL', 'Inches']]
    down += [f'{o} Down' for o in ORDINALS[1:]] + ['ESPN']          # the interim label and the no-down plate
    clock = [f'{m}:{s:02d}' for m in range(1, 16) for s in range(60)] + [f':{s:02d}' for s in range(60)]
    return {
        'down': down,
        # FC090: "1st".."4th" (the static layer capitalizes them in place) and "OT%d" with the quarter minus four.
        'quarter': list(ORDINALS) + [o.upper() for o in ORDINALS] + [f'OT{n}' for n in range(1, 10)],
        'clock': clock,                                               # FC100/FC150 "%d:%02d"; ":54" under a minute
        'play_clock': [str(n) for n in range(10)] + [str(n) for n in range(10, 41)],   # "%02d", a leading zero stripped
        'away_score': [str(n) for n in range(1000)], 'home_score': [str(n) for n in range(1000)],
        'away_timeouts': ['0', '1', '2', '3'], 'home_timeouts': ['0', '1', '2', '3'],
    }


def tokenize(text, glyphs):
    """runtime.c's field(): the first token in table order ((-len, token), as compiled) that the text starts with."""
    order = [t for t, _ in sorted(glyphs.items(), key=lambda kv: (-len(kv[0]), kv[0]))]
    out, at = [], 0
    while at < len(text):
        match = next((t for t in order if text.startswith(t, at)), None)
        if match is None:
            return None
        out.append(match)
        at += len(match)
    return out


def _author():
    spec = importlib.util.spec_from_file_location('b76_sbfix_author', ROOT / 'reports/b76_sbfix/author.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LayoutTests(unittest.TestCase):
    """Runs everywhere: the committed layout and template."""

    @classmethod
    def setUpClass(cls):
        cls.spec, cls.image = sprite.load_layout()
        cls.fields = {f['name']: f for f in cls.spec['fields']}

    def test_every_retail_string_draws_within_its_slots(self):
        for name, texts in strings().items():
            field = self.fields[name]
            glyphs = self.spec['glyph_sets'][field['glyph_set']]['glyphs']
            for text in texts:
                tokens = tokenize(text, glyphs)
                self.assertIsNotNone(tokens, (name, text))
                self.assertLessEqual(len(tokens), field['slots'], (name, text, tokens))

    def test_inches_draws_as_the_bars_capitals(self):
        label = self.spec['glyph_sets']['label']['glyphs']
        self.assertEqual(tokenize('3rd & Inches', label), ['3', 'rd', ' ', '&', ' ', 'Inch', 'es'])
        # sb2 rebuilt these cells for the smaller field; keep the original sbfix receipt as history.
        receipts = json.loads((ROOT / 'reports/b76_sb2/author_receipt.json').read_text())['strings']
        for token, cell in (('Inch', 'label_Inch'), ('es', 'label_es')):
            row = label[token]
            width = receipts[cell]['glyph_size'][0]
            self.assertEqual((row['cell'], row['size'], row['raise']), (cell, [width, 30], 0), token)
            box = self.spec['cells'][cell]['box']
            self.assertEqual(box, receipts[cell]['cell'])
            pixels = self.image.crop(tuple(box))
            self.assertEqual(pixels.height, 9, token)                       # the 24 px field's nine native texel rows
            self.assertEqual(pixels.width, int(width * .8 / 3 + 0.02), token)     # 1/3 texel per layout px: no minification
            self.assertEqual(hashlib.sha256(pixels.tobytes()).hexdigest(), receipts[cell]['sha256'], token)
            opaque = [p[:3] for p in pixels.getdata() if p[3] > 128]
            self.assertTrue(opaque and all(min(p) >= 250 for p in opaque), token)   # white coverage the field tints
        # 'Inch' ends on H and 'es' starts on E: the word's straight-straight gap (16 px at 4x), condensed with it.
        fit = receipts['fit']
        self.assertAlmostEqual(label['Inch']['advance'] - label['Inch']['size'][0], 16 / 4 * 30 / 23 * fit['condense'], places=2)
        self.assertGreater(fit['condense'], 0.95)                           # a slight auto-fit, not a different face
        # The widest plate the formatter prints fits the down field: no runtime compression, so no label glyph minifies.
        field = self.fields['down']
        widest = max(self._width(f'{o} & Inches', label) for o in ORDINALS)
        self.assertAlmostEqual(widest, fit['widest_plate'], places=2)
        self.assertLessEqual(widest, (field['box'][2] - field['box'][0]) * self.spec['glyph_sets']['label']['cap_height'] / field['size'])
        goal = [self.image.crop(tuple(self.spec['cells'][label[t]['cell']]['box'])).tobytes() for t in ('GOAL', 'Goal')]
        self.assertEqual(goal[0], goal[1])                                  # retail "Goal" draws GOAL, as the broadcast writes it
        self.assertNotEqual(self.spec['cells']['label_Inch']['box'], [587, 47, 613, 59])   # the beta 72 cell is gone
        self.assertIn('sbfix', self.spec['provenance'])

    @staticmethod
    def _width(text, glyphs):
        tokens = tokenize(text, glyphs)
        return sum(glyphs[t]['advance'] for t in tokens[:-1]) + glyphs[tokens[-1]]['size'][0]

    def test_overtime_reads_ot_in_every_period(self):
        quarter = self.spec['glyph_sets']['quarter']['glyphs']
        for n in range(1, 10):
            self.assertEqual(tokenize(f'OT{n}', quarter), [f'OT{n}'])
            self.assertEqual(quarter[f'OT{n}'], {'cell': 'quarter_OT', 'size': [37.278, 22], 'advance': 39.278})
        cell = self.image.crop(tuple(self.spec['cells']['quarter_OT']['box']))
        self.assertEqual(cell.size, (12, 9))                                # the pill numerals' 9 texel rows

    def test_the_committed_art_is_the_authors_output(self):
        author = _author()
        layout = json.loads((ROOT / 'data/nfl2k5_scorebug_sprite/layout.json').read_text(encoding='utf-8'))
        new_layout, new_image, _receipts = author.build(layout, self.image)
        self.assertEqual(new_layout, layout)
        self.assertEqual(new_image.tobytes(), self.image.tobytes())

    def test_the_budget_keeps_the_hud_sectors(self):
        self.assertEqual(sprite.probe_sizes(), (34, 327904, 327680))       # the overtime tokens: +384 B, same sectors


@unittest.skipUnless(XBE.is_file(), 'the pinned USA XBE is required')
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = _retail()
        if cls.data is None:
            raise unittest.SkipTest('retail XBE pin differs')
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        cls.off = lambda self, va: scene.layout.sbpos.va_to_off(self.data, va)

    def test_formatter_spans_match_their_pins(self):
        for name, (va, size, sha) in SPANS.items():
            off = self.off(va)
            self.assertEqual(hashlib.sha256(self.data[off:off + size]).hexdigest(), sha, name)

    def test_the_literals_are_the_enumerated_strings(self):
        for va, text in LITERALS.items():
            off = self.off(va)
            raw = self.data[off:off + 2 * len(text) + 2]
            self.assertEqual(raw, (text + '\0').encode('utf-16le'), hex(va))
        # FC7D0 picks "Inches" when the distance rounds to nothing and "Goal" inside the ten: both are operands.
        for va, operand in ((0xfc937, 0xE6C418), (0xfc8b0, 0xE6C404), (0xfc977, 0xE6C428), (0xfc0e2, 0xE6C4E4)):
            off = self.off(va)
            self.assertEqual(struct.unpack_from('<I', self.data, off + 1)[0], operand, hex(va))


if __name__ == '__main__':
    unittest.main()
