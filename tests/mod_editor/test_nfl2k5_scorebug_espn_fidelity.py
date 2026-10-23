"""b778 sb3: the reference-measured wing glow, plate bevel and rail light, and Buffalo's primary mark.

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

    def test_plate_has_the_measured_top_bevel_and_dark_lower_edge(self):
        box = self.spec['cells']['plate']['box']
        cell = self.sheet.crop(tuple(box))
        rows = [cell.getpixel((cell.width // 2, y))[0] for y in range(cell.height)]
        self.assertGreaterEqual(rows[1], rows[cell.height // 2] + 10)
        self.assertGreaterEqual(rows[cell.height // 2], rows[-2] + 10)
        self.assertLess(rows[-1], 120)
        self.assertGreater(rows[cell.height // 2], 120)
        for pixel in cell.getdata():
            if pixel[3] > 128:
                self.assertLessEqual(max(pixel[:3]) - min(pixel[:3]), 1)

    def test_plate_tint_is_the_possessing_team_and_red_blue_references_exist(self):
        static = next(row for row in self.spec['static'] if row['name'] == 'plate')
        self.assertEqual(static['tint'], 'possessing team')
        accents = json.loads((FOLDER / 'team_accents.json').read_text(encoding='utf-8'))['teams']
        def rgb(name):
            value = accents[name]['plate']
            return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
        kc, den = rgb('KC'), rgb('DEN')
        self.assertGreater(kc[0], kc[2] * 2)       # red possession plate
        self.assertGreater(den[2], den[0] * 2)     # blue possession plate


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


class ProvenanceTests(unittest.TestCase):
    def test_record_names_the_measurements(self):
        spec = json.loads((FOLDER / 'layout.json').read_text(encoding='utf-8'))
        record = spec['provenance'][RECORD]
        self.assertIn('broadcast_away_median', record['reference'])
        self.assertIn('wing', record)
        self.assertIn('plate_rows', record)
        self.assertEqual(record['rim']['cells'], ['away_rim', 'home_rim'])

    def test_template_pin_matches_the_catalog(self):
        catalog = json.loads((ROOT / 'packaging/nfl2k5_scorebug_template_pngs.json').read_text(encoding='utf-8'))
        info = catalog['files']['data/nfl2k5_scorebug_sprite/template.png']
        data = (FOLDER / 'template.png').read_bytes()
        self.assertEqual(info['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(info['size'], len(data))


if __name__ == '__main__':
    unittest.main()
