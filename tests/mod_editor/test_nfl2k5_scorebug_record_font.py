"""b778 sb2 (Noah, stream c2-15, "the font on the records"): the shipped record cells are exactly what
tools/scorebug_sprite/record_font.py draws from the traced broadcast digits, and the layout carries its record.

Offline only. The in-game look is covered by the native preview tests in test_nfl2k5_scorebug_records.
"""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools/scorebug_sprite')]
import record_font as rf  # noqa: E402

FOLDER = ROOT/'data/nfl2k5_scorebug_sprite'


class RecordFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.spec = json.loads((FOLDER/'layout.json').read_text(encoding='utf-8'))
        with Image.open(FOLDER/'template.png') as image:
            cls.sheet = image.convert('RGBA')

    def cell(self, name):
        return self.sheet.crop(tuple(self.spec['cells'][name]['box']))

    def test_every_record_cell_is_the_tool_output(self):
        masks = rf.source_masks()
        glyphs = self.spec['glyph_sets']['record']['glyphs']
        self.assertEqual(set(glyphs), set(rf.TOKENS))
        for token in rf.TOKENS:
            with self.subTest(token=token):
                cov, width = rf.token_cell(token, masks)
                self.assertEqual(self.cell(glyphs[token]['cell']).tobytes(), rf.with_halo(cov).tobytes())
                self.assertEqual(glyphs[token]['size'][0], width + 2*rf.PX_PER_TEXEL)
                self.assertEqual(glyphs[token]['advance'], width + rf.ADVANCE_GAP)

    def test_band_cells_are_the_tool_output(self):
        for side in ('away', 'home'):
            self.assertEqual(self.cell('record_band_'+side).tobytes(), rf.rgba(rf.band_cell(side), rf.BAND['colour']).tobytes())

    def test_old_pixel_font_is_gone_and_the_record_is_kept(self):
        record = self.spec['provenance'][rf.RECORD]
        self.assertIn('espn_glyphs.png', record['digits'])
        self.assertNotIn('record_tab', self.spec['cells'])              # the b76 s15 navy box cell
        names = {n for n in self.spec['cells'] if n.startswith('record_')}
        self.assertEqual(len(names), len(rf.TOKENS) + 2)


if __name__ == '__main__':
    unittest.main()
