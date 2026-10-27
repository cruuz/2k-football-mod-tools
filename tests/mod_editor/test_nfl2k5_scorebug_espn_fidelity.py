"""b778 sb3/sb4/sb5: the measured wing glow, connected clock pill, ESPN down & distance tab and Buffalo's primary mark.

Offline checks on the shipped template, layout and runtime source. The emulator stills are produced by
tools/scorebug_sprite/espn_fidelity.py and the native preview, not by this module.
"""
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FOLDER = ROOT / 'data/nfl2k5_scorebug_sprite'
RECORD = 'b778_sb3_espn_fidelity'


def load():
    from PIL import Image
    spec = json.loads((FOLDER / 'layout.json').read_text(encoding='utf-8'))
    with Image.open(FOLDER / 'template.png') as image:
        return spec, image.convert('RGBA')


def source_pixel(spec, sheet, name, sx, sy, source):
    box = spec['cells'][name]['box']
    width, height = box[2] - box[0], box[3] - box[1]
    i = min(width - 1, max(0, round(sx * width / source[0])))
    j = min(height - 1, max(0, round(sy * height / source[1])))
    return sheet.getpixel((box[0] + i, box[1] + j))


class WingGlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.sheet = load()

    def test_glow_covers_the_mark_and_clears_before_the_score(self):
        for name in ('wing', 'home_wing'):
            with self.subTest(name=name):
                top = source_pixel(self.spec, self.sheet, name, 20, 10, (340, 110))[3] / 255
                middle = source_pixel(self.spec, self.sheet, name, 20, 50, (340, 110))[3] / 255
                inner = source_pixel(self.spec, self.sheet, name, 300, 30, (340, 110))[3] / 255
                self.assertGreaterEqual(top, .82)          # the reference's 1.0 coverage at the outer top
                self.assertGreaterEqual(middle, .42)
                self.assertLessEqual(inner, .09)           # the score column sits on the dark body
                self.assertGreater(top, middle)

    def test_wing_alpha_is_monotonic_and_zero_at_the_inner_edge(self):
        import numpy as np
        for name in ('wing', 'home_wing'):
            box = self.spec['cells'][name]['box']
            alpha = np.asarray(self.sheet.crop(tuple(box)))[..., 3].astype(int)
            middle = alpha[alpha.shape[0] // 2]
            self.assertTrue((np.diff(middle) <= 0).all(), name)
            if name == 'wing':
                self.assertTrue((np.diff(alpha, axis=1) <= 0).all(), name)
            self.assertGreater(alpha[:, 0].max(), 128)
            self.assertEqual(alpha[:, -1].max(), 0)


class PlateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.sheet = load()

    def test_plate_tint_is_the_possessing_team_and_red_blue_references_exist(self):
        static = next(row for row in self.spec['static'] if row['name'] == 'plate')
        self.assertEqual(static['tint'], 'possessing team')
        accents = json.loads((FOLDER / 'team_accents.json').read_text(encoding='utf-8'))['teams']
        kc, den = tab_tint(accents['KC']), tab_tint(accents['DEN'])
        self.assertGreater(kc[0], kc[2] * 2)       # red possession tab
        self.assertGreater(den[2], den[0] * 2)     # blue possession tab


def tab_tint(team):
    """sb5: the runtime's possession tint, the midpoint of the wing display shade and the plate accent."""
    def rgb(value):
        return [int(value[i:i + 2], 16) for i in (1, 3, 5)]
    return [((w & 0xfe) >> 1) + ((p & 0xfe) >> 1) for w, p in zip(rgb(team['wing']), rgb(team['plate']))]


class RimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.sheet = load()

    def test_rim_cells_are_white_coverage_and_clear_at_the_centre(self):
        import numpy as np
        for name in ('away_rim', 'home_rim'):
            box = self.spec['cells'][name]['box']
            cell = np.asarray(self.sheet.crop(tuple(box)))
            self.assertTrue((cell[..., :3][cell[..., 3] > 128] >= 250).all(), name)
            outer = 0 if name == 'away_rim' else cell.shape[1] - 1
            self.assertGreater(cell[cell.shape[0] // 2, outer, 3], 32)
            self.assertEqual(cell[cell.shape[0] // 2, cell.shape[1] // 2, 3], 0)


class CapsuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.sheet = load()

    def test_capsule_has_a_crisp_rim_instead_of_a_soft_gray_ramp(self):
        box = self.spec['cells']['capsule']['box']
        cell = self.sheet.crop(tuple(box))
        top = cell.getpixel((cell.width // 2, 0))[0]
        middle = cell.getpixel((cell.width // 2, cell.height // 2))[0]
        bottom = cell.getpixel((cell.width // 2, cell.height - 1))[0]
        self.assertLess(top, middle - 8)
        self.assertLess(bottom, middle - 8)
        self.assertGreaterEqual(middle, 244)


class BuffaloTests(unittest.TestCase):
    def test_shipped_buffalo_is_the_charging_primary_not_the_standing_alternate(self):
        import numpy as np
        from PIL import Image
        shipped = Image.open(ROOT / 'data/nfl2k5_scorebug_mnf/logos/buf.png').convert('RGBA')
        primary = Image.open(ROOT / 'data/nfl2k5_scorebug_assets/logos/buf.png').convert('RGBA')
        bounds = primary.getchannel('A').getbbox()
        primary = primary.crop(bounds)
        scale = 62 / max(primary.width, primary.height)
        primary = primary.resize((round(primary.width * scale), round(primary.height * scale)),
                                 Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        canvas.alpha_composite(primary, ((64 - primary.width) // 2, (64 - primary.height) // 2))
        a = np.asarray(shipped)[..., 3] > 32
        b = np.asarray(canvas)[..., 3] > 32
        self.assertGreater((a & b).sum() / (a | b).sum(), .95)
        red = np.asarray(shipped).astype(int)
        stamped = ((red[..., 0] > 150) & (red[..., 1] < 90) & (red[..., 2] < 90) & (red[..., 3] > 128)).sum()
        self.assertGreater(stamped, 20)   # the primary's red streak

    def test_buffalo_zoom_is_the_fit_tool_fixed_point(self):
        spec = json.loads((FOLDER / 'layout.json').read_text(encoding='utf-8'))
        accents = json.loads((FOLDER / 'team_accents.json').read_text(encoding='utf-8'))['teams']
        self.assertEqual(spec['logo_fit']['by_team']['BUF'], accents['BUF']['logo_fit'])
        self.assertGreater(spec['logo_fit']['by_team']['BUF']['zoom'], 1.10)


class ConnectedCapsuleTests(unittest.TestCase):
    """sb4: the still has one 243 px pill, not a pill plus a play-clock box."""

    @classmethod
    def setUpClass(cls):
        cls.spec, cls.sheet = load()
        cls.statics = {row['name']: row for row in cls.spec['static']}
        cls.fields = {row['name']: row for row in cls.spec['fields']}

    def test_one_capsule_holds_quarter_clock_and_play_clock(self):
        self.assertEqual(self.statics['capsule']['box'], [839, 999, 1082, 1039])
        self.assertEqual(self.statics['red']['box'], [1023, 999, 1082, 1039])
        self.assertNotIn('housing', self.statics)
        for name in ('quarter', 'clock', 'play_clock'):
            box = self.fields[name]['box']
            self.assertGreaterEqual(box[0], 839, name)
            self.assertLessEqual(box[2], 1082, name)
        self.assertLess(self.fields['play_clock']['box'][0], 1082)
        x0, y0, x1, y1 = self.spec['cells']['capsule']['box']
        self.assertEqual((x1 - x0, y1 - y0), (81, 16))

    def test_two_measured_dividers_inside_the_white_body(self):
        x0, y0, x1, y1 = self.spec['cells']['capsule']['box']
        width, height = x1 - x0, y1 - y0
        rgb = [self.sheet.getpixel((x0 + x, y0 + height // 2))[0] for x in range(width)]
        self.assertGreaterEqual(max(rgb), 244)
        for divider in (902.5, 1021.5):
            column = round((divider - 839) * width / 243)
            self.assertLess(min(rgb[column - 1:column + 2]), 235)
        self.assertGreater(rgb[width // 2], 240)          # the body returns between dividers

    def test_play_clock_is_smaller_than_the_game_clock(self):
        self.assertEqual((self.fields['clock']['size'], self.fields['quarter']['size'],
                          self.fields['play_clock']['size']), (27, 19, 19))
        self.assertLessEqual(self.fields['play_clock']['box'][3] - self.fields['play_clock']['box'][1], 19)

    def test_red_state_uses_the_pill_itself(self):
        x0, y0, x1, y1 = self.spec['cells']['capsule']['box']
        rx0, ry0, rx1, ry1 = self.spec['cells']['red']['box']
        cap = self.sheet.crop((x1 - (rx1 - rx0), y0, x1, y1))
        red = self.sheet.crop(tuple([rx0, ry0, rx1, ry1]))
        diff = max(abs(a - b) for a, b in zip(cap.getchannel('A').getdata(), red.getchannel('A').getdata()))
        self.assertLessEqual(diff, 2)
        self.assertEqual(self.statics['red']['tint'], 'play clock cell')


class PlateTabTests(unittest.TestCase):
    """sb5: ESPN's down-and-distance tab hangs from the bar's top rail: S-curved shoulders, vertical sides,
    rounded lower corners, lit sides over a darker centre, and a light rim, tinted by the team with the ball."""

    # The read-only Broncos at Chiefs still (sb3/ds/work/ref_full.png): the tab's 50% edge, box-local
    # layout px from the quad's left edge (x 828), averaged over the left and right sides, by box row.
    STILL_INSET = {2: 0.9, 4: 2.4, 6: 4.1, 8: 5.5, 10: 6.7, 12: 8.0, 14: 9.3, 16: 10.5, 18: 11.2,
                   22: 11.5, 26: 11.5, 30: 11.5}

    @classmethod
    def setUpClass(cls):
        import numpy as np
        cls.np = np
        cls.spec, cls.sheet = load()
        cls.statics = {row['name']: row for row in cls.spec['static']}
        x0, y0, x1, y1 = cls.spec['cells']['plate']['box']
        cls.cell = np.asarray(cls.sheet.crop((x0, y0, x1, y1)), dtype=float)
        x0, y0, x1, y1 = cls.spec['cells']['plate_gloss']['box']
        cls.gloss = np.asarray(cls.sheet.crop((x0, y0, x1, y1)), dtype=float)
        x0, y0, x1, y1 = cls.statics['plate']['box']
        cls.sx = (x1 - x0) / cls.cell.shape[1]          # layout px per texel
        cls.sy = (y1 - y0) / cls.cell.shape[0]

    def edge(self, row):
        """50% alpha crossing on the left side of one texel row, in layout px from the quad edge."""
        alpha = [0.0] + list(self.cell[row, :, 3] / 255)     # transparent beyond the quad's edge
        for i in range(1, len(alpha) // 2):
            if alpha[i - 1] < .5 <= alpha[i]:
                return (i - 2 + (.5 - alpha[i - 1]) / (alpha[i] - alpha[i - 1]) + .5) * self.sx
        return None

    def test_tab_shares_the_quad_and_the_gloss(self):
        self.assertEqual(self.statics['plate']['box'], [828, 944, 1098, 990])
        self.assertEqual(self.statics['plate_gloss']['box'], self.statics['plate']['box'])
        self.assertEqual(self.statics['plate']['tint'], 'possessing team')
        self.assertEqual(self.statics['plate_gloss']['tint'], 'none')

    def test_shoulders_follow_the_still(self):
        # Texel row j covers layout rows [j*sy, (j+1)*sy]; compare its edge with the still at its centre.
        checked = 0
        for row in range(self.cell.shape[0]):
            y = (row + .5) * self.sy
            if y > 30:
                break
            keys = sorted(self.STILL_INSET)
            expected = self.np.interp(y, keys, [self.STILL_INSET[k] for k in keys])
            got = self.edge(row)
            self.assertIsNotNone(got, row)
            self.assertLess(abs(got - expected), 1.6, (row, y, got, expected))
            checked += 1
        self.assertGreaterEqual(checked, 12)
        # The shoulder flares out of the rail and is finished by bar y ~964 (sb4's taper ran the whole height).
        side = self.edge(10)
        self.assertGreater(side - self.edge(0), 9.5)
        self.assertLess(abs(self.edge(int(19 / self.sy)) - side), 0.3)

    def test_symmetric_vertical_sides_and_rounded_lower_corners(self):
        alpha = self.cell[..., 3]
        self.assertTrue(self.np.allclose(alpha, alpha[:, ::-1], atol=3))
        body = [self.edge(r) for r in range(8, 13)]
        self.assertLess(max(body) - min(body), 0.8)          # vertical sides
        last = max(r for r in range(alpha.shape[0]) if alpha[r].max() > 128)
        self.assertLessEqual((last + 1) * self.sy, 43)        # flat bottom near bar y 984
        self.assertGreater(self.edge(last), self.edge(10) + 1.5)   # the corner arc pulls the edge in
        self.assertLess(alpha[-1].max(), 40)                  # no sb4 drop-shadow slab under the bar

    def test_lit_sides_over_a_darker_centre(self):
        row = self.cell[self.cell.shape[0] // 2]
        centre = row[row.shape[0] // 2, 0]
        side = max(row[i, 0] for i in range(2, 9))           # ~6..27 layout px in from the edge
        self.assertGreaterEqual(side, 190)
        self.assertLessEqual(centre, 125)
        self.assertGreater(side, centre * 1.6)
        values = [row[i, 0] for i in range(row.shape[0] // 2)]
        values = values[values.index(max(values)):]          # from the lit side inward to the centre
        self.assertTrue(all(b <= a + 2 for a, b in zip(values, values[1:])), values)
        for pixel in self.cell.reshape(-1, 4):
            if pixel[3] > 128:
                self.assertLessEqual(max(pixel[:3]) - min(pixel[:3]), 1)

    def test_gloss_is_an_untinted_rail_glint_and_rim_light(self):
        alpha = self.gloss[..., 3]
        opaque = self.gloss[alpha > 64][:, :3]
        self.assertTrue((opaque >= 250).all())
        middle = alpha.shape[1] // 2
        self.assertGreaterEqual(alpha[0, middle], 80)         # the rail glint across the top
        self.assertLess(alpha[alpha.shape[0] // 2, middle], 8)    # nothing over the label
        side = alpha[alpha.shape[0] // 2, :8]
        self.assertGreaterEqual(side.max(), 20)               # rim light down the side (sub-texel line)

    def test_white_label_stays_legible_for_every_team(self):
        """The label's ink stays inside the tab's darker centre; 4.5:1 against white for every team.

        The widest label, "4th & GOAL", inks 180 layout px (bar x 432..611 on the native preview), centred."""
        from mod_editor.core import nfl2k5_scorebug_teams as teams
        accents = json.loads((FOLDER / 'team_accents.json').read_text(encoding='utf-8'))['teams']
        x0, _y0, x1, _y1 = self.statics['plate']['box']
        half = 180 / 2 / self.sx
        centre = self.cell.shape[1] / 2
        lo, hi = int(centre - half), int(self.np.ceil(centre + half))
        rows = range(int(11 / self.sy), int(35 / self.sy))   # the label's rows, bar y 955..979
        brightest = max(self.cell[r, i, 0] for r in rows for i in range(lo, hi)) / 255
        self.assertLess(brightest, 0.72)
        for name, team in sorted(accents.items()):
            if team.get('kind', 0) != 0:
                continue
            tint = tab_tint(team)
            colour = '#%02X%02X%02X' % tuple(round(c * brightest) for c in tint)
            self.assertGreaterEqual(teams.contrast_white(colour), 4.5, (name, colour))


class RuntimeTintTests(unittest.TestCase):
    def test_runtime_tints_the_tab_with_the_wing_and_plate_midpoint(self):
        source = (ROOT / 'tools/scorebug_sprite/runtime.c').read_text(encoding='utf-8')
        for side in ('home', 'away'):
            self.assertIn('s->%s_plate=0xff000000|(((s->%s_wing&0xfefefe)>>1)+((s->%s_plate&0xfefefe)>>1));'
                          % (side, side, side), source)
        self.assertIn('#define ESPN_PLATE 0xff322f34u', source)
        setup = source[source.index('NOINLINE void sprite_setup'):]
        setup = setup[:setup.index('\n}\n')]
        self.assertLess(setup.index('accents(b,0xb30a58'), setup.index('s->away_plate=0xff000000|'))


class ProvenanceTests(unittest.TestCase):
    def test_record_names_the_measurements(self):
        spec = json.loads((FOLDER / 'layout.json').read_text(encoding='utf-8'))
        record = spec['provenance'][RECORD]
        self.assertIn('broadcast_away_median', record['reference'])
        self.assertIn('wing', record)
        self.assertIn('plate_rows', record)
        self.assertEqual(record['rim']['cells'], ['away_rim', 'home_rim'])
        self.assertEqual(record['plate_source'], [274, 38])       # sb3 history stays sb3
        capsule = spec['provenance']['b778_sb4_connected_clock']
        self.assertEqual(capsule['layout'], [839, 999, 1082, 1039])
        self.assertEqual(capsule['dividers_layout'], [902.5, 1021.5])
        plate = spec['provenance']['b778_sb4_plate_tab']
        self.assertEqual(plate['layout'], [828, 944, 1098, 990])
        self.assertEqual(plate['bottom_inset'], 15)               # sb4 history stays sb4
        tab = spec['provenance']['b778_sb5_tab_shape']
        self.assertEqual(tab['layout'], [828, 944, 1098, 990])
        self.assertEqual(tab['source'], [90, 19])
        self.assertIn('ref_full.png', tab['reference'])
        self.assertIn('ref_full.png', capsule['reference'])

    def test_template_pin_matches_the_catalog(self):
        catalog = json.loads((ROOT / 'packaging/nfl2k5_scorebug_template_pngs.json').read_text(encoding='utf-8'))
        info = catalog['files']['data/nfl2k5_scorebug_sprite/template.png']
        data = (FOLDER / 'template.png').read_bytes()
        self.assertEqual(info['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(info['size'], len(data))


if __name__ == '__main__':
    unittest.main()
