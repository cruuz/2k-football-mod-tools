"""Super Bowl walls (sb2): the mod's own NFL shield by season, the authored event art in slots, and the user's
optional logo folder, proved with synthetic placeholder images (plain shapes and text, not real logos)."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import numpy as np
from PIL import Image, ImageDraw
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core import nfl2k5_super_bowl_walls as walls

DISC = os.environ.get('SB2_DISC')
RETAIL = os.environ.get('SB2_RETAIL')


def placeholder(path, size=(512, 512), colour=(230, 0, 200), alpha=True, text='TEST'):
    """A synthetic placeholder: a coloured disc in a yellow ring with plain text (transparent PNG), or a checker
    square without transparency."""
    if alpha:
        im = Image.new('RGBA', size, (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse([8, 8, size[0] - 8, size[1] - 8], fill=(255, 230, 0, 255))
        d.ellipse([size[0] // 8, size[1] // 8, size[0] * 7 // 8, size[1] * 7 // 8], fill=colour + (255,))
    else:
        im = Image.new('RGB', size, (255, 255, 255))
        d = ImageDraw.Draw(im)
        for y in range(0, size[1], 32):
            for x in range(0, size[0], 32):
                if (x // 32 + y // 32) % 2 == 0:
                    d.rectangle([x, y, x + 31, y + 31], fill=colour)
    d.text((size[0] // 3, size[1] // 2), text, fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def slots_of(row, **match):
    entry = walls.entry(row)
    return [(t, s) for t in entry['textures'] for s in t.get('slots', ())
            if all(s.get(k) == v for k, v in match.items())]


class Shields(unittest.TestCase):
    def test_modern_seasons_use_the_mods_official_shield(self):
        raw = walls.MODERN_SHIELD.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), walls.MODERN_SHIELD_SHA256)
        doc = json.loads((ROOT / 'data/nfl2k5_espn25_fields/manifest.json').read_text())
        pinned = {a['file']: a['sha256'] for a in doc['art']}
        self.assertEqual(pinned['row45/center_logo.png'], walls.MODERN_SHIELD_SHA256)
        rgba, origin = walls.Marks().shield(2008)
        self.assertEqual(origin, 'mod_shield_2008')
        self.assertEqual(rgba.shape, (256, 256, 4))

    def test_earlier_seasons_need_the_period_shield_from_the_disc(self):
        with self.assertRaisesRegex(ValueError, 'period shield'):
            walls.Marks().shield(2007)
        period = np.zeros((256, 256, 4), np.uint8)
        rgba, origin = walls.Marks(period).shield(1988)
        self.assertEqual(origin, 'disc_period_shield')
        self.assertIs(rgba, period)

    def test_every_row_names_its_shield_by_season(self):
        for r in walls.manifest()['rows']:
            with self.subTest(row=r['row']):
                want = 'mod_shield_2008' if r['season'] >= 2008 else 'disc_period_shield'
                self.assertEqual(r['shield'], want)
                self.assertTrue(slots_of(r['row'], kind='shield'), 'every Super Bowl carries the shield')
        before = {r['event'] for r in walls.manifest()['rows'] if r['season'] < 2008}
        self.assertEqual(before, {'XXIII', 'XXV', 'XXXII', 'XXXIV', 'XXXVI', 'XLII'})

    def test_period_shield_keeps_its_cutout_and_loses_its_fringe(self):
        rgba = np.zeros((256, 256, 4), np.uint8)
        rgba[..., :3] = (130, 150, 76)  # the field's green under the cut-out
        rgba[64:192, 64:192] = (0, 60, 160, 255)
        rgba[63, 64:192, 3] = 120  # an anti-aliased edge row still carrying green
        out = walls.defringe(rgba)
        np.testing.assert_array_equal(out[..., 3], rgba[..., 3])
        self.assertLessEqual(np.abs(out[63, 100, :3].astype(int) - (0, 60, 160)).max(), 2)
        self.assertTrue((out[0, 0, :3] == 0).all())

    def test_period_shield_is_read_from_the_retail_field_centre_logo(self):
        fake = np.zeros((256, 256, 4), np.uint8)
        fake[32:224, 32:224] = (200, 0, 20, 255)
        rec = dict(system_bytes=0)
        with patch.object(fields, '_field_chunk', return_value=(None, rec, b'')), \
                patch('mod_editor.core.nfl2k5_modern_venues_2026.p8_rows', return_value={0: {}}), \
                patch('mod_editor.core.nfl2k5_modern_venues_2026.rows_by_material',
                      return_value={'center_logo': 0}), \
                patch('mod_editor.core.nfl2k5_modern_venues_2026.read_texture', return_value=fake):
            rgba, receipt = walls.period_shield(b'bundle')
        self.assertEqual(receipt['source'], 's43dd.iff')
        self.assertEqual(receipt['rgba_sha256'], hashlib.sha256(fake.tobytes()).hexdigest())
        self.assertFalse(receipt['pinned_retail'])
        np.testing.assert_array_equal(rgba[..., 3], fake[..., 3])

    def test_compiler_reads_the_period_shield_once_and_passes_the_folder(self):
        source = (ROOT / 'mod_editor/core/nfl2k5_espn25_fields.py').read_text()
        self.assertIn('super_bowl_walls.period_shield(get_retail(super_bowl_walls.PERIOD_SHIELD_RESOURCE))', source)
        self.assertIn("super_bowl_walls.apply(after, row['row'], marks=marks)", source)
        self.assertIn('def compile_assets(get_built,get_retail,situ,*,progress=None,user_art=None)', source)
        build = (ROOT / 'mod_editor/core/mod_build.py').read_text()
        self.assertIn('user_art=plan.super_bowl_user_art or None, log=lambda line: progress(line, 0, 0)', build)


class ShippedArt(unittest.TestCase):
    def test_slots_are_valid_and_every_event_has_its_marks(self):
        for r in walls.manifest()['rows']:
            with self.subTest(row=r['row']):
                self.assertTrue(slots_of(r['row'], kind='event', key=r['event']))
                self.assertTrue(slots_of(r['row'], kind='brand', key=r['network'].lower()))
                for code in r['teams'].values():
                    self.assertTrue(slots_of(r['row'], kind='team', key=code))
                for t, s in slots_of(r['row']):
                    self.assertIn(s['kind'], walls.SLOT_KINDS)
                    if s['kind'] != 'shield':
                        self.assertTrue(t.get('layer'), f"{t['material']} has authored marks")

    def test_team_logos_come_from_the_mod_except_seasons_it_lacks(self):
        gaps = {(r['row'], c) for r in walls.manifest()['rows'] for c, how in r['team_logos'].items()
                if how == 'authored'}
        self.assertEqual(gaps, {(14, 'CIN'), (15, 'NYG'), (22, 'STL'), (23, 'STL')})
        for row, code in gaps:
            for _, s in slots_of(row, kind='team', key=code):
                self.assertEqual(s['authored'], 'authored_team_roundel')
        for _, s in slots_of(45, kind='team'):
            self.assertEqual(s['authored'], 'mod_team_logo')

    def test_authored_layers_hold_marks_only_inside_slots(self):
        for r in walls.manifest()['rows']:
            for t in r['textures']:
                if not t.get('layer'):
                    continue
                with self.subTest(row=r['row'], material=t['material']):
                    lyr = walls.layer(t)
                    inside = np.zeros(lyr.shape[:2], bool)
                    for s in t['slots']:
                        x0, y0, x1, y1 = s['box']
                        inside[y0:y1, x0:x1] = True
                    self.assertFalse((lyr[~inside, 3] > 0).any())

    def test_no_user_art_ships(self):
        allow = [line.strip() for line in (ROOT / 'packaging/release-allowlist.txt').read_text().splitlines()]
        self.assertFalse([line for line in allow if 'user_art' in line.split('/')[:-1]])
        self.assertFalse(any('user_art' in p.parts for p in (ROOT / 'data').rglob('*')))

    def test_build_plan_and_saved_settings_carry_the_folder(self):
        from mod_editor.core import mod_build, nfl2k5_build_settings as settings
        self.assertEqual(mod_build.BuildPlan('', '').super_bowl_user_art, '')
        self.assertIn('super_bowl_user_art', settings.FEATURE_KEYS)
        for preset in mod_build.PRESETS.values():
            self.assertEqual(preset.get('super_bowl_user_art'), '')


class UserArt(unittest.TestCase):
    """A synthetic user folder on the XLVI walls (Lucas Oil): an event placeholder, a network placeholder, a team
    placeholder without transparency, a broken file and a lower-case name."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = walls.create_user_art_layout(Path(self.temp.name) / 'user_art')
        placeholder(self.folder / 'super_bowl' / 'xlvi.png')
        placeholder(self.folder / 'brands' / 'nbc.png', (512, 256), (0, 220, 230))
        placeholder(self.folder / 'teams' / 'NE.png', (256, 256), (255, 60, 60), alpha=False)
        (self.folder / 'teams' / 'NYG.png').write_bytes(b'not a png at all')
        self.row = walls.entry(29)

    def compose_all(self, marks):
        return {t['material']: walls.compose(t, self.row, marks) for t in self.row['textures']}

    def test_matching_files_fill_their_slots_and_the_rest_fall_back(self):
        plain = self.compose_all(walls.Marks())
        user = self.compose_all(walls.Marks(None, self.folder))
        sources = {(s['kind'], s['key']): set() for _, (_, slots) in user.items() for s in slots}
        for _, (_, slots) in user.items():
            for s in slots:
                sources[(s['kind'], s['key'])].add(s['source'])
        self.assertEqual(sources[('event', 'XLVI')], {'user_art'})
        self.assertEqual(sources[('brand', 'nbc')], {'user_art'})
        self.assertEqual(sources[('team', 'NE')], {'user_art'})
        self.assertEqual(sources[('team', 'NYG')], {'mod_team_logo'})
        self.assertEqual(sources[('brand', 'espn')], {'authored_network_type'})
        self.assertEqual(sources[('shield', 'nfl')], {'mod_shield_2008'})
        for material, (rgba, slots) in user.items():
            base, _ = plain[material]
            outside = np.ones(rgba.shape[:2], bool)
            for s in slots:
                x0, y0, x1, y1 = s['box']
                outside[y0:y1, x0:x1] = False
            np.testing.assert_array_equal(rgba[outside], base[outside], err_msg=material)
            for s in slots:
                if s['kind'] == 'event':
                    x0, y0, x1, y1 = s['box']
                    region = rgba[y0:y1, x0:x1, :3].reshape(-1, 3).astype(int)
                    magenta = (np.abs(region - (230, 0, 200)).sum(1) < 60).sum()
                    self.assertGreater(magenta, 0, f'{material}: the placeholder shows in its slot')
        refused = [s.get('note', '') for _, (_, slots) in user.items() for s in slots if s['key'] == 'NYG']
        self.assertTrue(all('not a PNG' in n for n in refused))

    def test_build_log_lists_filled_and_authored_slots(self):
        receipts = [dict(event='XLVI', slots=[s for t in self.row['textures']
                                              for s in walls.compose(t, self.row,
                                                                     walls.Marks(None, self.folder))[1]])]
        lines = walls.user_art_summary(receipts)
        self.assertTrue(lines[0].startswith('Super Bowl walls: filled from your folder: '))
        for name in ('super_bowl/xlvi.png (XLVI)', 'brands/nbc.png (XLVI)', 'teams/NE.png (XLVI)'):
            self.assertIn(name, lines[0])
        self.assertIn('brands/espn.png', lines[1])
        self.assertIn('teams/NYG.png', lines[1])
        self.assertTrue(any(line.startswith('Super Bowl walls: ignored teams/NYG.png: not a PNG') for line in lines))

    def test_status_line_counts_the_files(self):
        text = walls.user_art_status(self.folder)
        self.assertIn('Found 1 of 16 event logos, 1 of 5 network marks and 1 of', text)
        self.assertIn('teams/NYG.png: not a PNG file', text)

    def test_refusals_fall_back(self):
        target = self.folder / 'super_bowl' / 'LII.png'
        big = Image.new('RGBA', (4100, 8), (255, 0, 0, 255))
        big.save(target)
        image, origin, note = walls.Marks(None, self.folder).user('event', 'LII')
        self.assertIsNone(image)
        self.assertEqual(origin, 'authored')
        self.assertIn('image size', note)
        target.unlink()
        Image.new('RGBA', (64, 64), (0, 0, 0, 0)).save(target)
        self.assertIn('fully transparent', walls.Marks(None, self.folder).user('event', 'LII')[2])
        target.unlink()
        if hasattr(os, 'symlink'):
            try:
                os.symlink(self.folder / 'brands' / 'nbc.png', target)
            except OSError:
                return
            self.assertIn('not a regular file', walls.Marks(None, self.folder).user('event', 'LII')[2])

    def test_fit_keeps_aspect_margin_alpha_and_budget(self):
        mark = np.zeros((100, 400, 4), np.uint8)
        mark[:, :, 3] = 255
        mark[:, :, 0] = np.linspace(0, 255, 400)[None, :].astype(np.uint8)
        mark[:, :, 2] = np.linspace(255, 0, 100)[:, None].astype(np.uint8)
        out = walls.fit_mark(mark, 60, 40, margin=0.1, budget=16)
        ys, xs = np.nonzero(out[..., 3] > 0)
        self.assertGreaterEqual(xs.min(), 4)
        self.assertLessEqual(xs.max(), 55)
        width, height = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
        self.assertAlmostEqual(width / height, 4.0, delta=0.5)
        self.assertEqual(out[0, 0, 3], 0)
        colours = {tuple(c) for c in out[out[..., 3] > 0][:, :3]}
        self.assertLessEqual(len(colours), 16)
        keyed = walls.fit_mark(mark, 60, 40, margin=0.1, budget=16, keyline=(255, 255, 255))
        self.assertGreater((keyed[..., 3] > 0).sum(), (out[..., 3] > 0).sum())

    def test_readme_and_layout(self):
        readme = (self.folder / 'README.md').read_text()
        for r in walls.manifest()['rows']:
            self.assertIn(f"`super_bowl/{r['event']}.png`", readme)
        for brand in walls.BRANDS:
            self.assertIn(f'`brands/{brand}.png`', readme)
        for code in ('CIN', 'NYG', 'STL', 'NE', 'PHI', 'KC', 'LAR'):
            self.assertIn(f'`teams/{code}.png`', readme)
        self.assertIn('transparent PNG', readme)
        self.assertNotIn('—', readme)
        walls.create_user_art_layout(self.folder)
        self.assertTrue((self.folder / 'brands' / 'nbc.png').is_file(), 'existing files are never replaced')
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ['README.md', 'brands', 'super_bowl', 'teams'])


class Gui(unittest.TestCase):
    """The Build panel shows the folder, counts its files, creates the layout and saves the folder in the plan."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_folder_row_status_create_and_plan(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        with tempfile.TemporaryDirectory() as temp:
            panel = BuildPanel()
            try:
                self.assertIn('authored event marks', panel.super_bowl_user_art_status.text())
                with patch('mod_editor.gui.build_panel_qt.QFileDialog.getExistingDirectory', return_value=temp):
                    panel.super_bowl_user_art_create.click()
                folder = Path(temp) / 'user_art'
                self.assertTrue((folder / 'README.md').is_file())
                self.assertEqual(panel.super_bowl_user_art_field.text(), str(folder))
                placeholder(folder / 'super_bowl' / 'LII.png')
                panel._super_bowl_user_art_changed()
                self.assertIn('Found 1 of 16 event logos', panel.super_bowl_user_art_status.text())
                self.assertEqual(panel.plan().super_bowl_user_art, str(folder))
                saved = panel.project_build_settings()
                self.assertEqual(saved['super_bowl_user_art'], str(folder))
                panel.super_bowl_user_art_field.setText('')
                panel.restore_project_build_settings(saved)
                self.assertEqual(panel.super_bowl_user_art_field.text(), str(folder))
            finally:
                panel.deleteLater()


@unittest.skipUnless(DISC and RETAIL, 'set SB2_DISC (base disc) and SB2_RETAIL (retail disc), both read only')
class Disc(unittest.TestCase):
    """Real aliases: XXIII at Joe Robbie (retail venue, period shield) and LII at U.S. Bank (built venue)."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_historic_styles as historic
        with historic.Source(Path(RETAIL)) as retail:
            cls.shield, cls.shield_receipt = walls.period_shield(retail.get(walls.PERIOD_SHIELD_RESOURCE))
        cls.bundles = {}
        with historic.Source(Path(DISC)) as source:
            situ = source.get(identity=historic.SITU_OUTER_ID)
            for row in (14, 45):
                cls.bundles[row] = source.get(f'a{row - 1:02d}{fields.variant(situ, row - 1)}.iff')

    def test_retail_period_shield_is_the_pinned_one(self):
        self.assertTrue(self.shield_receipt['pinned_retail'])

    def test_walls_fit_and_replay_with_and_without_user_art(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = walls.create_user_art_layout(Path(temp) / 'user_art')
            placeholder(folder / 'super_bowl' / 'XXIII.png')
            placeholder(folder / 'super_bowl' / 'LII.png', colour=(0, 200, 90))
            for row, bundle in self.bundles.items():
                for user in (None, folder):
                    with self.subTest(row=row, user=bool(user)):
                        marks = walls.Marks(self.shield, user)
                        new, receipt = walls.apply(bundle, row, marks=marks)
                        self.assertTrue(receipt['written'])
                        self.assertEqual(len(new), len(bundle))
                        again, second = walls.apply(new, row, marks=marks)
                        self.assertEqual(again, new)
                        self.assertTrue(second['already_applied'])
                        sources = {s['source'] for s in receipt['slots'] if s['kind'] == 'event'}
                        self.assertEqual(sources, {'user_art'} if user else {'authored_event_plate'})


if __name__ == '__main__':
    unittest.main()
