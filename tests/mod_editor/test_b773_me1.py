"""Super Bowl moments carry their own event walls (N06); everything else in the venue keeps its bytes."""
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
from PIL import Image
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core import nfl2k5_super_bowl_walls as walls
from mod_editor.core import nfl2k5_modern_venues_2026 as mv

DISC = os.environ.get('ME1_DISC')
SIZE = 16


def fake_scene(textures=2):
    """A decoded scene holding `textures` 16 x 16 P8 textures, each with a gradient and a half-clear cutout."""
    rows, blob = [], bytearray(b'\x00' * 64)
    for k in range(textures):
        pixel = len(blob)
        rows.append(dict(index=k, format_name='P8', conversion_status='base_level_supported', width=SIZE,
                         height=SIZE, mip_levels=1, pixel_offset=pixel, palette_offset=pixel + SIZE * SIZE,
                         mapped_material_names=[f'mat{k}']))
        blob += bytes((i * 7 + k) % 256 for i in range(SIZE * SIZE))
        palette = bytearray()
        for i in range(256):
            palette += bytes((i, 255 - i, (i * 3) % 256, 255 if i % 2 else 0))
        blob += palette
    blob += b'\xee' * 32
    return dict(system_bytes=0, embedded_textures=rows), bytes(blob)


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.art = Path(self.temp.name)
        patch.object(walls, 'ART', self.art).start()
        patch.object(walls, '_MANIFEST', None).start()
        self.addCleanup(patch.stopall)
        self.rec, self.decoded = fake_scene()

    def texture(self, material, alpha, colour=(200, 20, 40, 255), areas=None, name=None):
        rgba = np.zeros((SIZE, SIZE, 4), np.uint8)
        rgba[...] = colour
        rgba[:, :4, 3] = 0
        name = name or f'{material}.png'
        Image.fromarray(rgba).save(self.art / name)
        entry = dict(material=material, file=name, size=[SIZE, SIZE], alpha=alpha,
                     sha256=hashlib.sha256((self.art / name).read_bytes()).hexdigest())
        if areas:
            entry['areas'] = areas
        return entry

    def write_manifest(self, textures, row=45):
        doc = dict(schema=walls.SCHEMA, held_rows=[34], rows=[dict(row=row, event='LII', textures=textures)])
        (self.art / 'manifest.json').write_text(json.dumps(doc), newline='\n')
        walls._MANIFEST = None
        return walls.entry(row)

    def row(self, k):
        return mv.p8_rows(self.rec)[k]

    def test_alpha_modes(self):
        current = mv.read_texture(self.decoded, self.rec, self.row(0))
        for alpha, expect in (('opaque', np.full((SIZE, SIZE), 255)),
                              ('source', np.where(current[..., 3] >= 128, 255, 0)),
                              ('art', np.where(np.arange(SIZE)[None, :].repeat(SIZE, 0) < 4, 0, 255))):
            rgba, resized = walls.target(self.decoded, self.rec, self.row(0), self.texture('mat0', alpha))
            self.assertFalse(resized)
            np.testing.assert_array_equal(rgba[..., 3], expect, err_msg=alpha)
            self.assertEqual(tuple(rgba[8, 8, :3]), (200, 20, 40))

    def test_areas_keep_disc_texels_outside(self):
        current = mv.read_texture(self.decoded, self.rec, self.row(0))
        texture = self.texture('mat0', 'opaque', areas=[[0, 8, 16, 16]])
        rgba, _ = walls.target(self.decoded, self.rec, self.row(0), texture)
        np.testing.assert_array_equal(rgba[:8], current[:8])
        self.assertTrue((rgba[8:, :, :3] == (200, 20, 40)).all())

    def test_only_listed_texture_bytes_change_and_scope_is_checked(self):
        entry = self.write_manifest([self.texture('mat0', 'opaque')])
        edited, receipts = walls.painted(self.decoded, self.rec, entry)
        r0 = self.row(0)
        start, end = r0['pixel_offset'], r0['palette_offset'] + 1024
        self.assertNotEqual(bytes(edited[start:end]), self.decoded[start:end])
        self.assertEqual(bytes(edited[:start]), self.decoded[:start])
        self.assertEqual(bytes(edited[end:]), self.decoded[end:])
        walls._check_scope(self.decoded, bytes(edited), self.rec, receipts)
        edited[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'outside their textures'):
            walls._check_scope(self.decoded, bytes(edited), self.rec, receipts)

    def test_painted_surface_is_recognised_on_replay(self):
        entry = self.write_manifest([self.texture('mat0', 'opaque', areas=[[0, 8, 16, 16]]),
                                     self.texture('mat1', 'source', colour=(10, 60, 200, 255))])
        self.assertFalse(walls.already_painted(self.decoded, self.rec, entry))
        edited, _ = walls.painted(self.decoded, self.rec, entry)
        self.assertTrue(walls.already_painted(bytes(edited), self.rec, entry))

    def test_refusals(self):
        entry = self.write_manifest([self.texture('mat0', 'opaque'), self.texture('mat0x', 'opaque')])
        with self.assertRaisesRegex(ValueError, 'lacks mat0x'):
            walls.painted(self.decoded, self.rec, entry)
        self.rec['embedded_textures'][1]['mapped_material_names'] = ['mat1', 'mat0b']
        entry = self.write_manifest([self.texture('mat1', 'opaque'), self.texture('mat0b', 'opaque', name='b.png')])
        with self.assertRaisesRegex(ValueError, 'shares a texture'):
            walls.painted(self.decoded, self.rec, entry)
        tampered = self.texture('mat0', 'opaque')
        tampered['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            walls.art(tampered)
        escape = dict(tampered, file='../outside.png')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            walls.art(escape)
        bad = self.texture('mat0', 'opaque', areas=[[0, 0, 17, 4]])
        with self.assertRaisesRegex(ValueError, 'area'):
            self.write_manifest([bad])

    def test_held_row_and_foreign_schema_refused(self):
        doc = dict(schema=walls.SCHEMA, held_rows=[34], rows=[dict(row=34, event='XXXVIII', textures=[])])
        (self.art / 'manifest.json').write_text(json.dumps(doc), newline='\n')
        with self.assertRaisesRegex(ValueError, 'held row'):
            walls.manifest()
        walls._MANIFEST = None
        (self.art / 'manifest.json').write_text(json.dumps(dict(doc, schema='other')), newline='\n')
        with self.assertRaisesRegex(ValueError, 'foreign'):
            walls.manifest()

    def test_rows_without_event_walls_are_untouched(self):
        self.write_manifest([self.texture('mat0', 'opaque')], row=45)
        bundle = b'not a bundle'
        self.assertEqual(walls.apply(bundle, 44), (bundle, None))


class ShippedArt(unittest.TestCase):
    def test_every_super_bowl_moment_but_the_held_one_has_event_walls(self):
        doc = walls.manifest()
        catalog = {m['row']: m for m in json.loads((ROOT / 'data/nfl2k5_espn25_fields.json').read_text())['moments']}
        super_bowls = {row for row, m in catalog.items() if m.get('super_bowl')}
        self.assertEqual(len(super_bowls), 17)
        self.assertEqual(doc['held_rows'], [34])
        self.assertEqual({r['row'] for r in doc['rows']}, super_bowls - {34})
        for r in doc['rows']:
            self.assertEqual(r['event'], catalog[r['row']]['super_bowl'])
            names = {t['material'] for t in r['textures']}
            self.assertTrue({'banner_corp', 'banner_home_team', 'banner_away_team', 'banner_home_player'} <= names)
            self.assertGreater(len(names), 4, f"row {r['row']} has no venue surface")
            for t in r['textures']:
                self.assertEqual(walls.art(t).shape[:2], tuple(t['size'][::-1]))

    def test_art_folder_holds_only_manifest_files(self):
        doc = walls.manifest()
        listed = {t['file'] for r in doc['rows'] for t in r['textures']} | {'manifest.json'}
        present = {p.relative_to(walls.ART).as_posix() for p in walls.ART.rglob('*') if p.is_file()}
        self.assertEqual(present, listed)

    def test_compiler_wires_the_pass_after_period_protection(self):
        source = (ROOT / 'mod_editor/core/nfl2k5_espn25_fields.py').read_text()
        self.assertLess(source.index('protect_period_field(after)'), source.index("super_bowl_walls.apply(after, row['row'])"))


@unittest.skipUnless(DISC, 'set ME1_DISC to the read-only base disc')
class Disc(unittest.TestCase):
    """Real aliases: a built venue (LII, U.S. Bank) and a retail venue with kept areas (LI, NRG)."""
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_historic_styles as historic
        cls.bundles = {}
        with historic.Source(Path(DISC)) as source:
            situ = source.get(identity=historic.SITU_OUTER_ID)
            for row in (45, 30):
                cls.bundles[row] = source.get(f'a{row - 1:02d}{fields.variant(situ, row - 1)}.iff')

    def test_only_the_stadium_span_changes_and_replay_is_a_no_op(self):
        for row, bundle in self.bundles.items():
            with self.subTest(row=row):
                new, receipt = walls.apply(bundle, row)
                self.assertTrue(receipt['written'])
                self.assertEqual(len(new), len(bundle))
                at, size = receipt['stadium_offset'], receipt['stadium_size']
                self.assertEqual(new[:at], bundle[:at])
                self.assertEqual(new[at + size:], bundle[at + size:])
                again, second = walls.apply(new, row)
                self.assertEqual(again, new)
                self.assertTrue(second['already_applied'])
                _, rec, before = walls._stadium_chunk(bundle)
                _, _, after = walls._stadium_chunk(new)
                listed = {t['texture'] for t in receipt['textures']}
                every = set(mv.p8_rows(rec))
                old, now = walls.texture_bytes(before, rec, every), walls.texture_bytes(after, rec, every)
                self.assertEqual({int(k) for k in old if old[k] != now[k]}, listed)


if __name__ == '__main__':
    unittest.main()
