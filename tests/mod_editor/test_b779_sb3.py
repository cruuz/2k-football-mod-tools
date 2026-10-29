"""sb3: the real Super Bowl, network and team-season logos are bundled and used by default.

Noah (2026-10-28): real logos are what the people playing this free mod want. The bundled folder is the build's
default logo folder; a non-empty ``super_bowl_user_art`` folder is used instead and still overrides file by file.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import numpy as np
from PIL import Image, ImageDraw
from mod_editor.core import nfl2k5_super_bowl_walls as walls

SPEC = importlib.util.spec_from_file_location(
    'sb3_release_check', ROOT / 'packaging/check_2k5_mod_studio_release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def placeholder(path, size=(512, 512), colour=(230, 0, 200)):
    """A synthetic transparent PNG: a yellow ring around a magenta disc."""
    im = Image.new('RGBA', size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([8, 8, size[0] - 8, size[1] - 8], fill=(255, 230, 0, 255))
    d.ellipse([size[0] // 8, size[1] // 8, size[0] * 7 // 8, size[1] * 7 // 8], fill=colour + (255,))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


#: a stand-in for the period NFL shield a real build reads from the retail disc
PERIOD = np.zeros((256, 256, 4), np.uint8)
PERIOD[32:224, 32:224] = (10, 40, 120, 255)


def composed(row, marks):
    entry = walls.entry(row)
    return {t['material']: walls.compose(t, entry, marks) for t in entry['textures']}


def slot_source(row, marks, kind, key):
    entry = walls.entry(row)
    found = {s['source'] for t in entry['textures'] for s in walls.compose(t, entry, marks)[1]
             if s['kind'] == kind and s['key'] == key}
    return found


class BundledByDefault(unittest.TestCase):
    def test_the_plan_field_is_empty_and_resolves_to_the_bundled_folder(self):
        from mod_editor.core import mod_build
        plan = mod_build.BuildPlan('', '')
        self.assertEqual(plan.super_bowl_user_art, '')
        self.assertEqual(walls.effective_user_art(plan.super_bowl_user_art), str(walls.BUNDLED_LOGOS))
        softdrink = mod_build.apply_preset(mod_build.BuildPlan('', ''), 'softdrink_experimental')
        self.assertEqual(softdrink.super_bowl_user_art, '')
        self.assertEqual(walls.effective_user_art(softdrink.super_bowl_user_art), str(walls.BUNDLED_LOGOS))
        for name in ('softdrink_basic', 'softdrink_advanced', 'softdrink_experimental'):
            self.assertEqual(mod_build.PRESETS[name].get('super_bowl_user_art'), '', name)

    def test_the_build_resolves_the_bundled_folder_at_both_call_sites(self):
        build = (ROOT / 'mod_editor/core/mod_build.py').read_text()
        self.assertEqual(build.count('effective_user_art(plan.super_bowl_user_art)'), 2)
        self.assertNotIn('user_art=plan.super_bowl_user_art or None', build)

    def test_every_super_bowl_slot_places_the_bundled_logo(self):
        bundled = walls.logo_manifest()['files']
        marks = walls.Marks(PERIOD, walls.effective_user_art(''))
        for row in walls.manifest()['rows']:
            with self.subTest(row=row['row'], event=row['event']):
                for texture in row['textures']:
                    _, slots = walls.compose(texture, row, marks)
                    for slot in slots:
                        if slot['kind'] == 'shield':
                            continue
                        if slot['kind'] in ('event', 'brand'):
                            self.assertEqual(slot['source'], 'bundled_logo', slot['file'])
                        elif slot['file'] in bundled:
                            self.assertEqual(slot['source'], 'bundled_logo', slot['file'])
                        else:
                            self.assertEqual(slot['source'], 'mod_team_logo', slot['file'])

    def test_the_authored_marks_remain_the_fallback_without_a_folder(self):
        authored = walls.Marks(PERIOD)
        for row in (14, 15, 22, 23, 29, 50):
            with self.subTest(row=row):
                entry = walls.entry(row)
                for texture in entry['textures']:
                    _, slots = walls.compose(texture, entry, authored)
                    for slot in slots:
                        if slot['kind'] == 'event':
                            self.assertEqual(slot['source'], 'authored_event_plate')
                        if slot['kind'] == 'brand':
                            self.assertEqual(slot['source'], 'authored_network_type')

    def test_the_bundled_logo_pixels_replace_the_authored_marks(self):
        real = walls.Marks(PERIOD, walls.effective_user_art(''))
        plain = walls.Marks(PERIOD)
        for row in (14, 29, 50):
            with self.subTest(row=row):
                entry = walls.entry(row)
                before, after = composed(row, plain), composed(row, real)
                for texture in entry['textures']:
                    for slot, receipt in zip(texture.get('slots', ()), after[texture['material']][1]):
                        if receipt['source'] != 'bundled_logo':
                            continue
                        x0, y0, x1, y1 = slot['box']
                        left = before[texture['material']][0][y0:y1, x0:x1]
                        right = after[texture['material']][0][y0:y1, x0:x1]
                        self.assertFalse(np.array_equal(left, right),
                                         f"row {row} {texture['material']} {slot['kind']} {slot['key']}")

    def test_team_seasons_use_the_bundled_real_logo(self):
        marks = walls.Marks(PERIOD, walls.effective_user_art(''))
        for row, code in ((14, 'CIN'), (15, 'NYG'), (22, 'STL'), (23, 'STL')):
            with self.subTest(row=row, team=code):
                self.assertEqual(slot_source(row, marks, 'team', code), {'bundled_logo'})

    def test_the_build_log_says_the_logos_are_bundled(self):
        self.assertTrue(walls.is_bundled(str(walls.BUNDLED_LOGOS)))
        self.assertFalse(walls.is_bundled(''))
        self.assertFalse(walls.is_bundled('/tmp/some user folder'))
        receipts = [dict(event='XLVI', slots=[dict(kind='event', key='XLVI', file='super_bowl/XLVI.png',
                                                   note='super_bowl/XLVI.png', source='bundled_logo')])]
        self.assertIn('filled from the bundled real logos: super_bowl/XLVI.png (XLVI)',
                      walls.user_art_summary(receipts)[1])
        source = (ROOT / 'mod_editor/core/nfl2k5_anniversary_pack.py').read_text()
        self.assertIn('bundled real logos', source)
        from mod_editor.core import nfl2k5_super_bowl_fields as fields
        lines = fields.user_art_lines([dict(event='XXIII', slots=[
            dict(kind='event', key='XXIII', note='super_bowl/XXIII.png', source='bundled_logo')])])
        self.assertEqual(lines, ['Super Bowl fields: flank marks filled from the bundled real logos: '
                                 'super_bowl/XXIII.png (XXIII)'])

    def test_a_bundled_file_that_differs_from_its_manifest_falls_back(self):
        broken = {'files': {'super_bowl/XLVI.png': dict(sha256='0' * 64, size=1, width=1, height=1)}}
        with patch.object(walls, 'logo_manifest', return_value=broken):
            rgba, origin, note = walls.Marks(None, walls.BUNDLED_LOGOS).user('event', 'XLVI')
        self.assertIsNone(rgba)
        self.assertEqual(origin, 'authored')
        self.assertIn('differs from its manifest', note)


class UserFolderOverride(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = walls.create_user_art_layout(Path(self.temp.name) / 'user_art')

    def test_the_user_folder_is_used_instead_of_the_bundled_folder(self):
        placeholder(self.folder / 'super_bowl' / 'XLVI.png')
        marks = walls.Marks(None, walls.effective_user_art(self.folder))
        self.assertEqual(slot_source(29, marks, 'event', 'XLVI'), {'user_art'})
        self.assertEqual(slot_source(29, marks, 'brand', 'nbc'), {'authored_network_type'})
        self.assertEqual(slot_source(29, marks, 'team', 'NE'), {'mod_team_logo'})

    def test_each_user_file_wins_its_own_slot(self):
        placeholder(self.folder / 'super_bowl' / 'XLVI.png')
        placeholder(self.folder / 'brands' / 'nbc.png', (512, 256), (0, 220, 230))
        marks = walls.Marks(None, walls.effective_user_art(self.folder))
        self.assertEqual(slot_source(29, marks, 'event', 'XLVI'), {'user_art'})
        self.assertEqual(slot_source(29, marks, 'brand', 'nbc'), {'user_art'})
        self.assertEqual(slot_source(29, marks, 'brand', 'espn'), {'authored_network_type'})


class Packaging(unittest.TestCase):
    def test_the_catalog_is_pinned_and_accepted_by_the_release_gate(self):
        catalog_path = ROOT / release.SUPER_BOWL_LOGO_PNG_CATALOG
        data = catalog_path.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), release.SUPER_BOWL_LOGO_PNG_CATALOG_SHA256)
        document = json.loads(data)
        self.assertEqual(document['schema'], 'nfl2k5_super_bowl_logo_pngs/v1')
        files = sorted(document['files'])
        self.assertEqual(len(files), 25)
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary) / 'stage'
            allowlist = Path(temporary) / 'allowlist.txt'
            entries = [release.SUPER_BOWL_LOGO_PNG_CATALOG, *files]
            for relative in entries:
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            allowlist.write_text('\n'.join(entries) + '\n', encoding='utf-8')
            result = release.audit_release(stage, allowlist)
            self.assertEqual(result['reviewed_super_bowl_logo_png_count'], 25)
            self.assertFalse(result['retail_payloads_included'])
            changed = stage / files[0]
            changed.write_bytes(changed.read_bytes() + b'x')
            with self.assertRaisesRegex(release.ReleaseCheckError,
                                        'bundled Super Bowl logo PNG size changed'):
                release.audit_release(stage, allowlist)

    def test_the_catalog_lists_the_bundled_files_and_manifest(self):
        document = json.loads((ROOT / release.SUPER_BOWL_LOGO_PNG_CATALOG).read_text())
        root = ROOT / 'data/nfl2k5_super_bowl_logos'
        on_disk = {p.relative_to(ROOT).as_posix() for p in root.rglob('*.png')}
        self.assertEqual(set(document['files']), on_disk)
        manifest = walls.logo_manifest()
        self.assertEqual(set(manifest['files']),
                         {p.relative_to(root).as_posix() for p in root.rglob('*.png')})
        self.assertTrue((root / 'SOURCES.txt').is_file())


if __name__ == '__main__':
    unittest.main()
