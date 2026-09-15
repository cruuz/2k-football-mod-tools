"""Combined sibling staging and artwork-quality regressions, no game witness."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import test_nfl2k5_equipment_consumers as fixture
from mod_editor.core import equipment_staging as staging
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.nfl2k5_equipment_import_intent import import_settings, OWN_TEXTURE
from nfl_txtr import encode_rgba_png
from mod_editor.core.nfl2k5_digit_texture import make_digit_mips


class SiblingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ConsumerFanoutSessionTests()
        old = fixture._MultiPackageArchive
        with patch.object(fixture, '_MultiPackageArchive',
                          side_effect=lambda root: old(root, names=('shoes01', 'shoes01_mud', 'shoes09'))):
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture
        self.asset = self.f.assets['tset:0:8:0:shoes01']
        self.png = self.f.root / 'new.png'
        self.png.write_bytes(encode_rgba_png(32, 32, fixture.artwork(32, 32)))

    def stage(self, asset=None):
        with self.f.archive.context():
            return staging.stage_equipment_import(self.f.session, asset or self.asset, self.png, independent=True)

    def test_normal_and_mud_one_fit_one_undo_and_revert_roundtrip(self):
        result = self.stage()
        self.assertEqual(len(result.changed_asset_ids), 6)
        self.assertEqual(len(self.f.session._undo), 1)
        self.assertTrue(result.receipt['normal_and_mud_staged_together'])
        self.assertIn('fitted at 32 x 32,', result.message)
        self.assertIn('Normal and mud', result.message)
        for asset_id in result.changed_asset_ids:
            a = self.f.assets[asset_id]
            p, rgba = self.f.session.asset_io.validate_replacement(a, self.f.session.current_path(a))
            self.assertEqual(import_settings(p, asset_id, rgba), (OWN_TEXTURE, 1))
        with self.f.archive.context():
            fresh = staging.equipment_fit_rows(self.f.session)
            self.assertEqual({r['asset_id']: r['fit_summary'] for r in fresh},
                             {r['asset_id']: r['fit_summary'] for r in result.receipt['edits']})
            self.assertEqual(len(staging.revert_equipment_import(self.f.session, self.asset)), 6)
        self.assertEqual(self.f.staged(), ())
        self.f.session.undo()
        self.assertEqual(len(self.f.staged()), 6)
        self.f.session.undo()
        self.assertEqual(self.f.staged(), ())

    def test_mud_only_does_not_overwrite_normal(self):
        result = self.stage(self.f.assets['tset:0:8:1:shoes01_mud'])
        self.assertEqual(len(result.changed_asset_ids), 3)
        self.assertTrue(all(a.endswith('_mud') for a in result.changed_asset_ids))

    def test_combined_refusal_is_atomic(self):
        with self.f.archive.context(), patch.object(writer, '_rebuild_fixed_span',
                side_effect=writer.TxtrError('VC-LZ stream is 90000 bytes; exceeds 4000')):
            with self.assertRaises(ValueError):
                staging.stage_equipment_import(self.f.session, self.asset, self.png, independent=True)
        self.assertEqual(self.f.staged(), ())
        self.assertEqual(self.f.session._undo, [])

    def test_repeat_and_restore_original(self):
        self.stage()
        self.assertEqual(self.stage().changed_asset_ids, ())
        original = self.f.session.asset_io.ensure_original(self.asset)
        with self.f.archive.context():
            result = staging.stage_equipment_import(self.f.session, self.asset, original)
        self.assertFalse(result.modified)
        self.assertEqual(self.f.staged(), ())

    def test_retail_style6_and_pad_groups_and_glove_without_mud(self):
        by_id, _ = writer.load_targets()
        for name, count in (('shoes10', 2), ('elbowpad01', 804), ('glove01', 402)):
            target = next(t for t in by_id.values() if t.set_selector == '05H0' and t.name == name)
            rows = staging.staging_targets(target, by_id)
            self.assertEqual(len(rows), count)
            if name == 'shoes10':
                self.assertEqual({t.name for t in rows}, {'shoes10', 'shoes10_mud'})
                self.assertEqual({t.set_selector for t in rows}, {'05H0'})


class PaletteTests(unittest.TestCase):
    def test_actual_stripe_colours_and_no_dither(self):
        colours = ((249, 243, 225, 255), (110, 9, 12, 255), (7, 14, 23, 255))
        rgba = b''.join(bytes(colours[(y // 4) % 3]) for y in range(64) for x in range(64))
        self.assertTrue(writer._striped_art(rgba, 64, 64))
        levels = make_digit_mips(rgba, 64, 64, 4)
        palette, indices, quality = writer._quantize_art(levels, 16)
        self.assertEqual(b''.join(bytes(palette[i]) for i in indices[0]), rgba)
        self.assertEqual(quality['merged_colours'], [])
        for y in range(64):
            self.assertEqual(len(set(indices[0][64*y:64*(y+1)])), 1)

    def test_small_palettes_are_actual_art_median_cut(self):
        rgba = b''.join(bytes((80 + x, 5 + y, 13 + (x + y) // 3, 255))
                        for y in range(32) for x in range(32))
        levels = make_digit_mips(rgba, 32, 32, 3)
        actual = {tuple(rgba[i:i+4]) for i in range(0, len(rgba), 4)}
        for limit in (2, 4, 8, 16):
            palette, indices, _ = writer._quantize_art(levels, limit)
            self.assertLessEqual(len(palette), limit)
            self.assertTrue(set(palette) <= actual)
            self.assertEqual((palette, indices), writer._quantize_art(levels, limit)[:2])
        self.assertFalse(writer._striped_art(rgba, 32, 32))

    def test_striped_fit_never_searches_below_16(self):
        import tempfile
        from test_nfl2k5_equipment_texture_chain import Fixture
        rgba = b''.join(bytes((240,240,230,255) if (y//4)%2 else (10+x,20+x,30+x,255))
                        for y in range(32) for x in range(32))
        with tempfile.TemporaryDirectory() as d:
            f = Fixture(Path(d))
            with patch.object(writer, '_rebuild_fixed_span',
                              side_effect=writer.TxtrError('VC-LZ stream is 90000 bytes; exceeds 4000')):
                with self.assertRaises(writer.EquipmentFitError) as caught:
                    f.build([f.png(rgba=rgba)])
            self.assertTrue(all(r['maximum_palette_entries'] >= 16 for r in caught.exception.attempts))


if __name__ == '__main__':
    unittest.main()
