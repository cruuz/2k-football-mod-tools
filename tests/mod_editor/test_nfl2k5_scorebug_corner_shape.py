"""N27: the scorebar's upper-right corner is rounded like ESPN's; the other three stay nearly square."""
from pathlib import Path
import json
import math
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools/scorebug_sprite')]
import corner_shape as cs
from mod_editor.core import nfl2k5_scorebug_exact as exact
from mod_editor.core import nfl2k5_scorebug_resources as resources

FOLDER = ROOT/'data/nfl2k5_scorebug_sprite'


def load():
    import numpy as np
    from PIL import Image
    spec = json.loads((FOLDER/'layout.json').read_text(encoding='utf-8'))
    with Image.open(FOLDER/'template.png') as image:
        return spec, np.asarray(image.convert('RGBA')).astype(float)/255


def sample(spec, sheet, row, x, y):
    """Bilinear alpha of a static layer at a display point, edge texels clamped like the packed gutter."""
    x0, y0, x1, y1 = row['box']
    if not (x0 <= x < x1 and y0 <= y < y1):
        return 0.0
    cx0, cy0, cx1, cy1 = spec['cells'][row['cell']]['box']
    w, h = cx1-cx0, cy1-cy0
    u = (x-x0)/(x1-x0)*w
    if row.get('flip_x'):
        u = w-u
    v = (y-y0)/(y1-y0)*h
    u, v = u-.5, v-.5
    i, j = math.floor(u), math.floor(v)
    fu, fv = u-i, v-j
    total = 0.0
    for di, dj, k in ((0, 0, (1-fu)*(1-fv)), (1, 0, fu*(1-fv)), (0, 1, (1-fu)*fv), (1, 1, fu*fv)):
        ii, jj = i+di, j+dj
        if 0 <= ii < w and 0 <= jj < h:
            total += sheet[cy0+jj, cx0+ii, 3]*k
    return total


def silhouette(spec, sheet, x, y):
    clear = 1.0
    for row in cs.edge_layers(spec):
        clear *= 1-sample(spec, sheet, row, x, y)
    return 1-clear


class CornerShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.sheet = load()
        cls.box = cs.bar_box(cls.spec)

    def test_shipped_template_is_the_shaped_one(self):
        record = self.spec['provenance'][cs.RECORD]
        self.assertEqual(record['radius'], cs.RADIUS)
        self.assertEqual(record['layers'], ['body', 'body_right', 'home_wing'])
        out = subprocess.run([sys.executable, str(ROOT/'tools/scorebug_sprite/corner_shape.py'), '--check'],
                             capture_output=True, text=True, check=True).stdout
        self.assertTrue(out.startswith('already shaped'), out)

    def test_upper_right_is_round_and_clear_outside(self):
        x0, y0, x1, y1 = self.box
        r = cs.RENDERED_RADIUS
        cx, cy = x1-r, y0+r
        for k in range(1, 9):
            angle = k/9*math.pi/2
            dx, dy = math.sin(angle), -math.cos(angle)
            outside = silhouette(self.spec, self.sheet, cx+dx*(r+4), cy+dy*(r+4))
            inside = silhouette(self.spec, self.sheet, cx+dx*(r-6), cy+dy*(r-6))
            self.assertLess(outside, .06, angle)
            self.assertGreater(inside, .9, angle)
        # The old square corner point is empty now; it was opaque before.
        self.assertLess(silhouette(self.spec, self.sheet, x1-2, y0+2), .03)

    def test_drawn_radius_is_the_broadcast_radius(self):
        x0, y0, x1, y1 = self.box
        def edge(y):
            x = x1
            while x > x1-40 and silhouette(self.spec, self.sheet, x-.5, y) < .5:
                x -= .25
            return x
        top = y0+1.5
        depth_at_top = x1-edge(top)
        r = cs.RENDERED_RADIUS
        expected = r-math.sqrt(r*r-(r-1.5)**2)
        self.assertAlmostEqual(depth_at_top, expected, delta=3.0)
        self.assertLess(x1-edge(y0+r+4), 2.5)

    def test_other_corners_keep_their_small_bevel(self):
        body = self.spec['cells']['body']['box']
        a = self.sheet[body[1]:body[3], body[0]:body[2], 3]
        self.assertEqual([round(v*255) for v in a[:3, 0]], [69, 187, 243])
        self.assertEqual([round(v*255) for v in a[-3:, 0]], [243, 187, 69])
        self.assertEqual([round(v*255) for v in a[-3:, -1]], [243, 187, 69])
        self.assertTrue((a[3:-3, 0] == 1).all())
        x0, y0, x1, y1 = self.box
        self.assertGreater(silhouette(self.spec, self.sheet, x1-4, y1-6), .9)

    def test_rim_follows_the_curve_and_the_right_side(self):
        rim = next(r for r in self.spec['static'] if r['tint'] == 'home rim')
        x0, y0, x1, y1 = self.box
        r = cs.RENDERED_RADIUS
        cx, cy = x1-r, y0+r
        on_curve = sample(self.spec, self.sheet, rim, cx+(r-1.5)*math.sin(math.pi/4), cy-(r-1.5)*math.cos(math.pi/4))
        side = [sample(self.spec, self.sheet, rim, x1-1.5, y) for y in range(round(cy)+4, y1-8, 6)]
        self.assertGreater(on_curve, .35)
        self.assertTrue(all(.3 < v < .7 for v in side), side)
        self.assertLess(sample(self.spec, self.sheet, rim, x1-12, (y0+y1)/2), .05)

    def test_left_layers_are_not_shaped(self):
        self.assertNotIn('away_rim', [r['cell'] for r in cs.edge_layers(self.spec)])
        self.assertNotIn('wing', [r['cell'] for r in cs.edge_layers(self.spec)])

    def test_every_home_mark_stays_inside_the_curve(self):
        import numpy as np
        x0, y0, x1, y1 = next(r['box'] for r in self.spec['static'] if r['name'] == 'home_logo')
        r = cs.RADIUS
        cx, cy = self.box[2]-r, self.box[1]+r
        for team in resources.TEAM_LOGOS:
            with self.subTest(team=team):
                alpha = np.asarray(exact.mnf_panel(team, 'home', fit=resources.logo_fit_for(team, self.spec['logo_fit'])))[..., 3]
                worst = 0.0
                for v, u in zip(*np.nonzero(alpha >= 64)):
                    x, y = x0+(u+.5)*(x1-x0)/64, y0+(v+.5)*(y1-y0)/64
                    if x > cx and y < cy:
                        worst = max(worst, math.hypot(x-cx, y-cy)-r)
                self.assertLessEqual(worst, 0.0)


if __name__ == '__main__':
    unittest.main()
