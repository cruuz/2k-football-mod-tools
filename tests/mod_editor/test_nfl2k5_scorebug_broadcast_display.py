"""The scorebug-only broadcast display class: measured or fitted wing shades, recomputed and bounded."""
from pathlib import Path
import copy
import json
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT)]
from mod_editor.core import nfl2k5_scorebug_teams as teams

DATA = ROOT / 'data/nfl2k5_scorebug_sprite'
MEASURED = {'NYG', 'LAR', 'DEN', 'KC', 'LV', 'HOU', 'PHI', 'CHI'}


class BroadcastDisplayTests(unittest.TestCase):
    def setUp(self):
        self.accents = json.loads((DATA / 'team_accents.json').read_text())
        self.display = teams.load_display()

    def load_with(self, accents=None, display=None):
        """Validate edited copies in a scratch data folder; the shipped files are never touched."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ('team_colors_official_2026.json', 'broadcast_display.json'):
                shutil.copyfile(DATA / name, folder / name)
            if display is not None:
                (folder / 'broadcast_display.json').write_text(json.dumps(display))
            (folder / 'team_accents.json').write_text(json.dumps(accents or self.accents))
            original = teams.DATA
            teams.DATA = folder
            try:
                return teams.load(folder / 'team_accents.json')
            finally:
                teams.DATA = original

    def test_every_nfl_team_wing_is_its_recomputed_display_shade(self):
        loaded = teams.load()
        self.assertEqual(set(self.display['measured']), MEASURED)
        for name, team in loaded.items():
            if team['slot'] >= 32:
                self.assertNotIn('display', team)
                continue
            layer = team['display']
            self.assertEqual(layer['class'], 'broadcast')
            self.assertEqual(layer['source'], 'measured' if name in MEASURED else 'fitted')
            shade = teams.display_shade(name, team, self.display)
            self.assertEqual((team['wing'], team['wash']), (shade, shade), name)
            if name not in MEASURED:
                self.assertEqual(shade, teams.broadcast_shade(layer['parent'], self.display['transfer']))
            # The rim and plate stay sourced accents with the white-label gate.
            for role in ('rim', 'plate'):
                self.assertIn(team[role], teams.variants(team['official']))
                self.assertGreaterEqual(teams.contrast_white(team[role]), 4.5)

    def test_forged_fitted_or_measured_shades_are_rejected(self):
        forged = copy.deepcopy(self.accents)
        forged['teams']['NYJ']['wing'] = forged['teams']['NYJ']['wash'] = '#FF00AA'
        with self.assertRaisesRegex(ValueError, 'Foreign'):
            self.load_with(forged)
        forged = copy.deepcopy(self.accents)
        forged['teams']['NYJ']['display']['source'] = 'measured'
        with self.assertRaisesRegex(ValueError, 'Foreign broadcast display source'):
            self.load_with(forged)
        forged = copy.deepcopy(self.accents)
        forged['teams']['NYJ']['display']['parent'] = '#123456'
        with self.assertRaisesRegex(ValueError, 'Foreign broadcast display parent'):
            self.load_with(forged)
        forged = copy.deepcopy(self.accents)
        forged['teams']['AFC']['display'] = dict(forged['teams']['NYJ']['display'])
        with self.assertRaisesRegex(ValueError, 'Foreign broadcast display record'):
            self.load_with(forged)
        # A measured shade that moves outside the transfer's bound is refused even when both files agree.
        display = copy.deepcopy(self.display)
        display['measured']['KC']['wing'] = '#00FF00'
        forged = copy.deepcopy(self.accents)
        forged['teams']['KC']['wing'] = forged['teams']['KC']['wash'] = '#00FF00'
        with self.assertRaisesRegex(ValueError, 'outside the transfer bound'):
            self.load_with(forged, display)

    def test_display_class_never_reaches_the_plate_or_rim(self):
        forged = copy.deepcopy(self.accents)
        forged['teams']['LV']['plate'] = forged['teams']['LV']['wing']
        with self.assertRaisesRegex(ValueError, 'low-contrast'):
            self.load_with(forged)
        display = copy.deepcopy(self.display)
        display['roles'] = ['wing', 'wash', 'plate']
        with self.assertRaisesRegex(ValueError, 'wing and wash only'):
            self.load_with(None, display)

    def test_the_sourced_accent_stays_recorded_and_valid(self):
        forged = copy.deepcopy(self.accents)
        forged['teams']['DAL']['display']['sourced'] = '#2390FC'
        with self.assertRaisesRegex(ValueError, 'sourced wing'):
            self.load_with(forged)

    def test_measured_shades_sit_within_the_leave_one_out_bound(self):
        transfer = self.display['transfer']
        for name, record in self.display['measured'].items():
            fitted = teams.broadcast_shade(record['parent'], transfer)
            self.assertLessEqual(teams.oklab_distance(record['wing'], fitted), transfer['measured_bound'], name)
            self.assertTrue(record['evidence'])
        self.assertLessEqual(transfer['leave_one_out_de2000']['max'], 6.0)

    def test_chromatic_shades_never_exceed_the_measured_lightness(self):
        transfer = self.display['transfer']
        for team in self.accents['teams'].values():
            if team['slot'] >= 32:
                continue
            shade = teams.broadcast_shade_rgb(team['display']['parent'], transfer)
            _l, a, b = teams.oklab(teams.rgb(team['display']['parent']))
            if (a * a + b * b) ** .5 >= transfer['neutral_chroma']:
                self.assertLessEqual(teams.oklab(shade)[0], transfer['lightness_cap'] + 1e-9)

    def test_no_white_label_sits_on_the_wing(self):
        """Why the wing needs no white-label gate: every light field lies where the wing covers under 10 percent."""
        from PIL import Image
        spec = json.loads((DATA / 'layout.json').read_text())
        sheet = Image.open(DATA / 'template.png').convert('RGBA')
        rows = {r['name']: r for r in spec['static']}
        tabs = {f['source'][:-len(' tab')]: f for f in spec['fields'] if f['source'].endswith('record tab')}
        for field in spec['fields']:
            if min(teams.rgb(field['colour'])) < 0xF0:
                continue
            glyphs = spec['glyph_sets'][field['glyph_set']]['glyphs'].values()
            if field['source'].endswith('record tab'):
                # b76 s15: a tab's white colour multiplies its navy cell; the tab is the dark backing, not a label.
                for g in glyphs:
                    self.assertLess(max(max(p[:3]) for p in sheet.crop(spec['cells'][g['cell']]['box']).getdata()), 0x40)
                continue
            if field['source'] in tabs:
                # b76 s15: a record sits wholly on its own opaque navy tab (white on navy is checked in
                # test_nfl2k5_scorebug_records), so no wing colour is ever under its glyphs.
                tx0, ty0, tx1, ty1 = tabs[field['source']]['box']
                fx0, fy0, fx1, fy1 = field['box']
                self.assertTrue(tx0 <= fx0 and fx1 <= tx1 and ty0 <= fy0 and fy1 <= ty1, field['name'])
                continue
            boxes = [field['box']]
            if 'alt_anchor' in field:
                # The possession arrow is drawn at its anchor (away) or its alternate anchor (home).
                dx = field['alt_anchor'][0] - field['anchor'][0]
                boxes.append([field['box'][0] + dx, field['box'][1], field['box'][2] + dx, field['box'][3]])
            for fx0, fy0, fx1, fy1 in boxes:
                for quad, cell in (('away_wing', 'wing'), ('home_wing', 'home_wing')):
                    qx0, qy0, qx1, qy1 = rows[quad]['box']
                    x0, x1 = max(fx0, qx0), min(fx1, qx1)
                    y0, y1 = max(fy0, qy0), min(fy1, qy1)
                    if x0 >= x1 or y0 >= y1:
                        continue
                    cx0, cy0, cx1, cy1 = spec['cells'][cell]['box']
                    sx, sy = (cx1 - cx0) / (qx1 - qx0), (cy1 - cy0) / (qy1 - qy0)
                    if rows[quad].get('flip_x'):
                        # The home quad samples its cell mirrored: its outer (right) end is the cell's left end.
                        x0, x1 = qx0 + qx1 - x1, qx0 + qx1 - x0
                    crop = sheet.crop((cx0 + int((x0 - qx0) * sx), cy0 + int((y0 - qy0) * sy),
                                       cx0 + int(round((x1 - qx0) * sx)), cy0 + int(round((y1 - qy0) * sy))))
                    coverage = max(crop.getchannel('A').getdata()) / 255
                    if field['source'] == 'possession':
                        # b76 s15: the chevron is a mark, not text, and sits where ESPN draws it: on the rim's glow.
                        # Even the lightest display wing (white) at this coverage over the bar body keeps the
                        # white chevron above 4.5:1.
                        self.assertLess(coverage, 0.25, (field['name'], quad))
                        grey = (coverage * 255 + (1 - coverage) * 37) / 255
                        linear = grey / 12.92 if grey <= 0.03928 else ((grey + 0.055) / 1.055) ** 2.4
                        self.assertGreater(1.05 / (linear + 0.05), 4.5, (field['name'], quad))
                        continue
                    self.assertLess(coverage, 0.10, (field['name'], quad))


if __name__ == '__main__':
    unittest.main()
