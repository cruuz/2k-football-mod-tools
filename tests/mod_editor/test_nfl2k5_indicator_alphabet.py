"""hu1: the authored player-name alphabet meets the nm1 atlas contract and reproduces from its generator."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
import nfl2k5_indicator_alphabet as alphabet

FOLDER = ROOT/'data/nfl2k5_indicator_names'
CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\'-. '
NAMES = ('ST. BROWN', "O'CONNELL", 'SMITH-NJIGBA', 'GAINWELL')


def load():
    from PIL import Image
    spec = json.loads((FOLDER/'metrics.json').read_text(encoding='utf-8'))
    with Image.open(FOLDER/'atlas.png') as image:
        return spec, image.convert('RGBA')


class AlphabetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.image = load()

    def test_header(self):
        spec = self.spec
        self.assertEqual(spec['schema'], 'nfl2k5_indicator_names/v1')
        self.assertEqual(spec['atlas'], [256, 128])
        self.assertEqual(self.image.size, (256, 128))
        self.assertFalse(spec['placeholder'])
        self.assertEqual((spec['cap_height'], spec['line_advance'], spec['baseline'], spec['outline']), (11, 17, 15, 1))
        self.assertEqual(set(spec['glyphs']), set(CHARS))

    def test_rects_quads_and_margins(self):
        alpha = self.image.getchannel('A')
        claimed = set()
        for char, glyph in self.spec['glyphs'].items():
            rect, quad, advance = glyph['rect'], glyph['quad'], glyph['advance']
            self.assertTrue(all(isinstance(v, int) for v in rect + [advance]), char)
            self.assertTrue(1 <= advance <= 32, char)
            if char == ' ':
                self.assertEqual(rect, [0, 0, 0, 0])
                self.assertEqual(quad, [0, 0, 0, 0])
                continue
            x0, y0, x1, y1 = rect
            self.assertTrue(0 <= x0 < x1 <= 256 and 0 <= y0 < y1 <= 128, char)
            self.assertLessEqual((x1-x0, y1-y0), (32, 24), char)
            self.assertEqual((quad[2]-quad[0], quad[3]-quad[1]), (x1-x0, y1-y0), char)
            cells = {(x, y) for x in range(x0, x1) for y in range(y0, y1)}
            self.assertFalse(cells & claimed, char)
            claimed |= cells
            for x in range(x0, x1):
                self.assertEqual(alpha.getpixel((x, y0)), 0, char)
                self.assertEqual(alpha.getpixel((x, y1-1)), 0, char)
            for y in range(y0, y1):
                self.assertEqual(alpha.getpixel((x0, y)), 0, char)
                self.assertEqual(alpha.getpixel((x1-1, y)), 0, char)

    def test_ink_is_white_and_sits_on_the_cap_band(self):
        top = self.spec['baseline'] - self.spec['cap_height']
        for char, glyph in self.spec['glyphs'].items():
            if char == ' ':
                continue
            crop = self.image.crop(glyph['rect'])
            rows = []
            for (r, g, b, a), i in zip(crop.getdata(), range(crop.width*crop.height)):
                if a:
                    self.assertEqual((r, g, b), (255, 255, 255), char)
                    rows.append(i//crop.width + glyph['quad'][1])
            self.assertTrue(rows, char)
            self.assertGreaterEqual(min(rows), top, char)
            self.assertLessEqual(max(rows), self.spec['baseline'], char)
            if char.isalnum() and char != 'Q':
                self.assertEqual((min(rows), max(rows)), (top, self.spec['baseline']-1), char)

    def test_brief_names_fit_one_label(self):
        for name in NAMES:
            width = sum(self.spec['glyphs'][c]['advance'] for c in name)
            self.assertLessEqual(width, 120, name)

    def test_generator_reproduces_the_shipped_files(self):
        with tempfile.TemporaryDirectory() as folder:
            alphabet.author(Path(folder))
            for name in ('atlas.png', 'metrics.json'):
                self.assertEqual((Path(folder)/name).read_bytes(), (FOLDER/name).read_bytes(), name)

    def test_nm1_compiler_accepts_the_atlas(self):
        try:
            from mod_editor.core import nfl2k5_indicator_names as names
        except ImportError:
            self.skipTest('nm1 indicator compiler not merged in this tree')
        spec, image, receipt = names.load_atlas(FOLDER)
        self.assertFalse(receipt['placeholder'])
        font, info = names.compile_font(FOLDER)
        self.assertEqual(info['cap_height'], 11)


if __name__ == '__main__':
    unittest.main()
