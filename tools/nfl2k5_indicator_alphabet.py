"""Author the controlled-player name alphabet for the indicator FONT (nm1 atlas contract v1).

Original letterforms drawn here as geometry, in the manner of the scorebar's own lettering: a bold,
slightly condensed grotesque with squarish rounded bowls and flat terminals. Each glyph sits on an
11 px cap height with 2 px stems and bars on whole pixels, so the native one-texel-per-pixel draw
stays crisp; only curves and diagonals carry coverage. No font file is read. The compiler adds the
one-pixel dark visibility outline, so none is painted here.

python3 tools/nfl2k5_indicator_alphabet.py [--output FOLDER]
"""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOLDER = ROOT/'data/nfl2k5_indicator_names'
CAP, BASELINE, LINE_ADVANCE = 11, 15, 17
TOP = BASELINE-CAP
SPACING, SPACE_ADVANCE = 2, 4
SS = 16
ORDER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\'-. '


class Glyph:
    """Coverage built from filled and cleared shapes in ink coordinates (x right, y down, cap top at 0)."""
    def __init__(self, width, height=CAP, top=0):
        from PIL import Image, ImageDraw
        self.width, self.height, self.top = width, height, top
        self.image = Image.new('L', (width*SS, height*SS), 0)
        self.draw = ImageDraw.Draw(self.image)

    def _xy(self, points):
        return [(x*SS, (y-self.top)*SS) for x, y in points]

    def rect(self, x0, y0, x1, y1, on=True):
        a, b = self._xy([(x0, y0), (x1, y1)])
        self.draw.rectangle((a[0], a[1], b[0]-1, b[1]-1), fill=255 if on else 0)
        return self

    def round(self, x0, y0, x1, y1, r, on=True, corners=None):
        a, b = self._xy([(x0, y0), (x1, y1)])
        self.draw.rounded_rectangle((a[0], a[1], b[0]-1, b[1]-1), radius=r*SS, fill=255 if on else 0, corners=corners)
        return self

    def poly(self, *points, on=True):
        self.draw.polygon(self._xy(points), fill=255 if on else 0)
        return self

    def coverage(self):
        from PIL import Image
        return self.image.resize((self.width, self.height), Image.Resampling.BOX)


def ring(w, r_out=3.0, r_in=1.2, y0=0, y1=CAP, stroke=2, **kw):
    g = Glyph(w, **kw)
    g.round(0, y0, w, y1, r_out).round(stroke, y0+stroke, w-stroke, y1-stroke, r_in, on=False)
    return g


def bowl_right(g, x0, y0, x1, y1, r_out, r_in, stem_to):
    """A D-like bowl: square on the left (joined to the stem), rounded on the right."""
    g.round(x0, y0, x1, y1, r_out, corners=(False, True, True, False))
    g.round(stem_to, y0+2, x1-2, y1-2, r_in, on=False, corners=(False, True, True, False))
    return g


def u_shape(w, depth=CAP):
    g = Glyph(w)
    g.round(0, -6, w, depth, 3.0).round(2, -6, w-2, depth-2, 1.2, on=False)
    return g


def glyphs():
    out = {}
    g = Glyph(9)
    g.poly((3, 0), (6, 0), (9, 11), (6.75, 11), (4.5, 2.6), (2.25, 11), (0, 11))
    g.rect(2, 7, 7, 9)
    out['A'] = g
    g = Glyph(8).rect(0, 0, 2, 11)
    bowl_right(g, 0, 0, 7, 6, 2.5, 0.8, 2)
    bowl_right(g, 0, 4, 8, 11, 3.0, 1.2, 2)
    out['B'] = g
    g = ring(8).rect(5, 4, 8, 7, on=False)
    out['C'] = g
    g = Glyph(8).rect(0, 0, 2, 11)
    out['D'] = bowl_right(g, 0, 0, 8, 11, 3.5, 1.4, 2)
    out['E'] = Glyph(7).rect(0, 0, 2, 11).rect(0, 0, 7, 2).rect(0, 4, 6, 6).rect(0, 9, 7, 11)
    out['F'] = Glyph(7).rect(0, 0, 2, 11).rect(0, 0, 7, 2).rect(0, 4, 6, 6)
    g = ring(8).rect(5, 3, 8, 5, on=False).rect(4, 5, 8, 7)
    out['G'] = g
    out['H'] = Glyph(8).rect(0, 0, 2, 11).rect(6, 0, 8, 11).rect(0, 4, 8, 6)
    out['I'] = Glyph(2).rect(0, 0, 2, 11)
    g = u_shape(7).rect(0, 0, 2, 7, on=False)
    out['J'] = g
    g = Glyph(8).rect(0, 0, 2, 11)
    g.poly((2, 4.6), (5.6, 0), (8.2, 0), (2, 7.4))
    g.poly((3.4, 4.9), (5.2, 3.9), (8.3, 11), (5.8, 11))
    out['K'] = g
    out['L'] = Glyph(7).rect(0, 0, 2, 11).rect(0, 9, 7, 11)
    g = Glyph(10).rect(0, 0, 2, 11).rect(8, 0, 10, 11)
    g.poly((0, 0), (2.6, 0), (5, 6.0), (7.4, 0), (10, 0), (6.2, 8.6), (3.8, 8.6))
    out['M'] = g
    g = Glyph(8).rect(0, 0, 2, 11).rect(6, 0, 8, 11)
    g.poly((0, 0), (2.5, 0), (8, 11), (5.5, 11))
    out['N'] = g
    out['O'] = ring(8)
    g = Glyph(8).rect(0, 0, 2, 11)
    bowl_right(g, 0, 0, 8, 7, 3.0, 1.0, 2)
    out['P'] = g
    g = Glyph(9, height=12)
    g.round(0, 0, 8, 11, 3.0).round(2, 2, 6, 9, 1.2, on=False)
    g.poly((4.2, 7.4), (6.0, 6.4), (9, 10.6), (9, 12), (7.6, 12))
    out['Q'] = g
    g = Glyph(8).rect(0, 0, 2, 11)
    bowl_right(g, 0, 0, 8, 7, 3.0, 1.0, 2)
    g.poly((3.4, 6), (5.8, 6), (8.2, 11), (5.7, 11))
    out['R'] = g
    g = Glyph(8)
    g.round(0, 0, 8, 6, 2.8).round(2, 2, 10, 4, 1.0, on=False)
    g.round(0, 4, 8, 11, 3.0).round(-2, 6, 6, 9, 1.2, on=False)
    g.rect(6, 2, 8, 3, on=False)
    g.rect(0, 8, 2, 9, on=False)
    out['S'] = g
    out['T'] = Glyph(8).rect(0, 0, 8, 2).rect(3, 0, 5, 11)
    out['U'] = u_shape(8)
    out['V'] = Glyph(9).poly((0, 0), (2.4, 0), (4.5, 8.0), (6.6, 0), (9, 0), (5.8, 11), (3.2, 11))
    out['W'] = Glyph(12).poly((0, 0), (2.2, 0), (3.4, 7.4), (5, 0), (7, 0), (8.6, 7.4), (9.8, 0), (12, 0),
                              (10.1, 11), (7.6, 11), (6, 4.4), (4.4, 11), (1.9, 11))
    g = Glyph(9)
    g.poly((0, 0), (2.6, 0), (9, 11), (6.4, 11)).poly((6.4, 0), (9, 0), (2.6, 11), (0, 11))
    out['X'] = g
    out['Y'] = Glyph(9).poly((0, 0), (2.5, 0), (4.5, 4.2), (6.5, 0), (9, 0), (5.5, 6.6), (5.5, 11),
                             (3.5, 11), (3.5, 6.6))
    g = Glyph(8).rect(0, 0, 8, 2).rect(0, 9, 8, 11)
    g.poly((5.4, 2), (8, 2), (2.6, 9), (0, 9))
    out['Z'] = g

    out['0'] = ring(7)
    g = Glyph(5).rect(3, 0, 5, 11)
    g.poly((3, 0), (4, 0), (4, 2.2), (0.4, 3.6), (0.4, 1.7))
    out['1'] = g
    g = Glyph(7)
    g.round(0, 0, 7, 7, 3.0).round(2, 2, 5, 9, 1.2, on=False).rect(0, 3, 2, 7, on=False)
    g.rect(0, 7, 7, 9, on=False)
    g.poly((4.6, 5.0), (7, 5.4), (2.6, 9.2), (0, 9.2))
    g.rect(0, 9, 7, 11)
    out['2'] = g
    g = Glyph(7)
    g.round(0, 0, 7, 6, 2.5).round(-2, 2, 5, 4, 1.0, on=False)
    g.round(0, 4, 7, 11, 3.0).round(-2, 6, 5, 9, 1.2, on=False)
    g.rect(0, 4, 2, 6, on=False)
    out['3'] = g
    g = Glyph(7).rect(4, 0, 6, 11).rect(0, 7, 7, 9)
    g.poly((4, 0), (6, 0), (2.3, 7), (0, 7))
    out['4'] = g
    g = Glyph(7).rect(0, 0, 7, 2).rect(0, 0, 2, 5)
    g.round(0, 4, 7, 11, 3.0, corners=(False, True, True, True)).round(-2, 6, 5, 9, 1.2, on=False)
    out['5'] = g
    g = ring(7).rect(5, 2, 7, 4, on=False).rect(2, 4, 5, 6)
    out['6'] = g
    g = Glyph(7).rect(0, 0, 7, 2)
    g.poly((4.7, 2), (7, 2), (3.4, 11), (1.1, 11))
    out['7'] = g
    g = Glyph(7)
    g.round(0, 0, 7, 6, 2.5).round(2, 2, 5, 4, 0.8, on=False)
    g.round(0, 4, 7, 11, 3.0).round(2, 6, 5, 9, 1.2, on=False)
    out['8'] = g
    out['9'] = 'rotate:6'
    out["'"] = Glyph(2, height=4).poly((0, 0), (2, 0), (2, 1.5), (1.2, 4), (0, 4))
    out['-'] = Glyph(5, height=2, top=4).rect(0, 4, 5, 6)
    out['.'] = Glyph(2, height=2, top=9).rect(0, 9, 2, 11)
    return out


def author(folder=DEFAULT_FOLDER):
    from PIL import Image
    shapes = glyphs()
    atlas = Image.new('RGBA', (256, 128), (255, 255, 255, 0))
    metrics = {}
    for i, char in enumerate(ORDER):
        if char == ' ':
            metrics[char] = dict(rect=[0, 0, 0, 0], quad=[0, 0, 0, 0], advance=SPACE_ADVANCE)
            continue
        shape = shapes[char]
        if shape == 'rotate:6':
            source = shapes['6']
            alpha, width, height, top = source.coverage().rotate(180), source.width, source.height, source.top
        else:
            alpha, width, height, top = shape.coverage(), shape.width, shape.height, shape.top
        cx, cy = 32*(i % 8), 24*(i//8)
        rect = [cx, cy, cx+width+2, cy+height+2]
        cell = Image.new('RGBA', (width, height), (255, 255, 255, 0))
        cell.putalpha(alpha)
        atlas.paste(cell, (cx+1, cy+1))
        y = TOP+top-1
        metrics[char] = dict(rect=rect, quad=[-1, y, width+1, y+height+2], advance=width+SPACING)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    pixels = atlas.load()
    for y in range(atlas.height):
        for x in range(atlas.width):
            if pixels[x, y][3] == 0:
                pixels[x, y] = (255, 255, 255, 0)
    atlas.save(folder/'atlas.png', optimize=True)
    spec = dict(schema='nfl2k5_indicator_names/v1', atlas=[256, 128], texture='atlas.png', placeholder=False,
                provenance='Opus authored scorebug-style alphabet (hu1 2026-10-14): original geometric letterforms '
                           'drawn by tools/nfl2k5_indicator_alphabet.py; no font file or retail glyph',
                cap_height=CAP, line_advance=LINE_ADVANCE, baseline=BASELINE, outline=1, glyphs=metrics)
    (folder/'metrics.json').write_text(json.dumps(spec, indent=2)+'\n', encoding='utf-8', newline='\n')
    return spec


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_FOLDER)
    author(parser.parse_args().output)
