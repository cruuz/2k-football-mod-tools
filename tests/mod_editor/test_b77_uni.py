"""UNI orientation contracts, native palette preservation and repair refusals."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tools/b77')]
import uni_helmet as h
import uni_repair as repair
import u1_cards as cards
import nfl_txtr as t
import nfl2k5_team_2026_art as art
from nfl_vc_lz_fill import fill_stream


def geometry():
    pos, uv = [], []
    for sign in (-1, 1):
        for y in range(38, 52):
            pos.append([sign*10, y, 6])
            uv.append([.3, .2+(y-38)*.015 if sign < 0 else .8-(y-38)*.015])
    return {'HI_HELMET_C': {'pos': pos, 'uv': uv}}


def template(alpha_patch=False):
    sizes = [(256 >> i, 256 >> i) for i in range(6)]
    count = sum(w*h for w, h in sizes)
    system = bytearray(128)
    system[12:16] = b'TXTR'
    struct.pack_into('<II', system, 16, 32-15, 64-19)
    system[32:50] = 'helmet02\0'.encode('utf-16le')
    struct.pack_into('<5I', system, 68, 0, count, (8<<24)|(8<<20)|(6<<16)|(0x0b<<8)|(2<<4), 0, 0)
    palette = bytearray(1024)
    palette[:12] = bytes([100, 20, 10, 255, 0, 180, 10, 255, 255, 255, 255, 255])
    base = np.zeros((256, 256, 4), np.uint8)
    base[:] = [10, 20, 100, 255]
    indices = bytearray(count)
    if alpha_patch:
        palette[12:16] = bytes([100, 20, 10, 254])
        linear = np.zeros((256, 256), np.uint8);linear[70:82, 75:87] = 3
        indices[:256*256] = t.swizzle_2d(linear.tobytes(), 256, 256, 1)
        base[70:82, 75:87, 3] = 254
    decoded = bytes(system)+bytes(indices)+bytes(palette)
    stream, _ = t.compress_vc_lz(decoded, stream_tag=1, offset_bits=12)
    filled, _ = fill_stream(stream, decoded, 32768, slack=16)
    span = t.HEADER.pack(b'TXTR', 32768, 128, count+1024, t.COMPRESSED_SENTINEL, 32, 0, 0)+filled+bytes(32768-len(filled))
    return span, base


class Orientation(unittest.TestCase):
    def test_denver_source_puts_the_mane_below_the_head_in_the_upper_native_island(self):
        spec = art.Spec(ROOT/'data/nfl2k5_teams_2026/DEN.json')
        kit = spec.data['kits']['home']
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp);folder = base/kit['selector'];folder.mkdir()
            atlas = np.full((256,256,4), [8,18,74,255], np.uint8)
            atlas[60:90,55:110,:3] = 245;atlas[165:195,55:110,:3] = 245
            mark = np.full((40,100,4), [245,245,245,255], np.uint8)
            mark[:20,:,:3] = [245,80,20]
            name = spec.data['marks']['team_logo_left'];path = base/name;path.parent.mkdir(parents=True,exist_ok=True)
            Image.fromarray(mark).save(path)
            for family in ('helmet00','helmet02'):
                Image.fromarray(atlas).save(folder/f'helmet_{family}.png')
                result = art.downscale(art.author_helmet(spec, kit, base, family, base))
                for y0,y1,expected in [(50,110,1),(146,205,-1)]:
                    region = result[y0:y1,26:134,:3];yy = np.indices(region.shape[:2])[0]
                    orange = (region[...,0]>.7)&(region[...,1]<.5)&(region[...,2]<.2)
                    white = (region.min(axis=2)>.7)
                    self.assertTrue(orange.any() and white.any())
                    self.assertGreater(expected*(yy[orange].mean()-yy[white].mean()),0)

    def test_pittsburgh_gold_recipe_rotates_only_its_upper_badge(self):
        d = json.loads((ROOT/'data/nfl2k5_uniform_alt_specs_2026/PIT_5.json').read_text())
        for side in ('home', 'away'):
            marks = d['kits'][side]['helmet']['decorations']
            self.assertEqual(len(marks), 1)
            self.assertEqual((marks[0]['center'], marks[0]['rotate']), ([74, 76], 180))

    def test_both_beaks_land_at_the_front_with_opposite_vertical_orientation(self):
        mark = np.zeros((60, 200, 4), np.uint8)
        mark[:] = [240, 30, 20, 255]
        mark[:, 140:] = [20, 30, 240, 255]
        mark[:15, 150:180] = [20, 240, 20, 255]
        for name, place in h.SEA_PLACEMENT.items():
            rgb = h.sample_mark(Image.fromarray(mark), (256, 256), place)
            yy, xx = np.indices(rgb.shape[:2])
            blue = (rgb[..., 2] > .7) & (rgb[..., 0] < .3) & (rgb[..., 3] > .9)
            red = (rgb[..., 0] > .7) & (rgb[..., 2] < .3) & (rgb[..., 3] > .9)
            green = (rgb[..., 1] > .7) & (rgb[..., 3] > .9)
            self.assertLess(xx[blue].mean(), xx[red].mean())
            self.assertGreater(yy[green].mean(), yy[blue].mean()) if name == 'upper' else self.assertLess(yy[green].mean(), yy[blue].mean())

    def test_card_input_rejects_a_second_v_flip_and_swapped_islands(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'g.json'; d = geometry()
            p.write_text(json.dumps(d), newline='\n')
            self.assertEqual(cards.native_shellc(p)['uv_origin'], 'native_top_left')
            for flip in ('v', 'islands'):
                d = geometry()
                for uv in d['HI_HELMET_C']['uv']:
                    uv[1] = 1-uv[1] if flip == 'v' else (uv[1]+.5)%1
                p.write_text(json.dumps(d), newline='\n')
                with self.assertRaisesRegex(ValueError, 'native top-left'):
                    cards.native_shellc(p)

    def test_home_and_away_views_do_not_mirror_the_card_image(self):
        home, away = (cards.view('helm_card', side, Path('card.png')) for side in 'HA')
        self.assertEqual(home['yaw'], -away['yaw'])
        self.assertEqual(home['roll'], -away['roll'])
        self.assertNotIn('mirror', home)
        self.assertNotIn('mirror', away)


class NativePalette(unittest.TestCase):
    def test_old_alpha_split_does_not_turn_new_white_art_into_navy_speckles(self):
        span, base = template(alpha_patch=True)
        scope = np.zeros((256, 256), bool);scope[70:82, 75:87] = True
        native = base.copy();native[scope, :3] = 255
        _fixed, previews, receipt = h.compile_existing_palette(span, native, scope)
        actual = np.array(Image.open(__import__('io').BytesIO(previews[0])))
        self.assertTrue(np.all(actual[scope] == [255, 255, 255, 255]))
        self.assertTrue(np.array_equal(actual[~scope], base[~scope]))
        self.assertEqual(receipt['mips'][0]['maximum_alpha_delta'], 1)

    def test_round_trip_keeps_wrapper_palette_alpha_and_unowned_pixels(self):
        span, base = template()
        scope = np.zeros((256, 256), bool);scope[70:82, 75:87] = True
        native = base.copy();native[scope] = [12, 177, 3, 255]
        fixed, previews, receipt = h.compile_existing_palette(span, native, scope)
        self.assertEqual(len(fixed), len(span))
        self.assertEqual(fixed[:32], span[:32])
        old, _ = t.decode_chunk(span, t.parse_chunks(span)[0])
        new, _ = t.decode_chunk(fixed, t.parse_chunks(fixed)[0])
        self.assertEqual(old[:128], new[:128])
        self.assertEqual(old[-1024:], new[-1024:])
        self.assertEqual(len(previews), 6)
        self.assertTrue(all(r['alpha_identical'] and r['outside_scope_rgba_identical'] for r in receipt['mips']))
        actual = np.array(Image.open(__import__('io').BytesIO(previews[0])))
        self.assertTrue(np.array_equal(actual[~scope], base[~scope]))
        self.assertTrue(np.all(actual[scope] == [10, 180, 0, 255]))

    def test_unowned_pixel_change_is_refused(self):
        span, native = template();scope = np.zeros((256, 256), bool);native[4, 4, 0] += 1
        with self.assertRaisesRegex(ValueError, 'outside its scope'):
            h.compile_existing_palette(span, native, scope)


class Repair(unittest.TestCase):
    def test_denver_repair_owns_shell_a_and_refuses_shell_c(self):
        span, _ = template()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp);(base/'same.span').write_bytes(span)
            raw = span*33
            for index,label,allowed in [(11,'helmet00',True),(12,'helmet02',False)]:
                patch = dict(offset=index*len(span),length=len(span),label=label,
                             before_sha256=repair.sha(span),after_sha256=repair.sha(span),replacement='same.span')
                if allowed:
                    repair.validate_resource('08H0.IFF',raw,[patch],base)
                else:
                    with self.assertRaisesRegex(ValueError,'outside owned'):
                        repair.validate_resource('08H0.IFF',raw,[patch],base)

    def test_manifest_refuses_other_kits_and_changed_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'manifest.json'
            doc = dict(schema=repair.SCHEMA, scope_sha256=repair.sha(repair.SCOPE.read_bytes()),
                       resources={'26H0.IFF': [{'offset': 1}]})
            p.write_text(json.dumps(doc), newline='\n');self.assertEqual(repair.load_manifest(p), doc)
            doc['resources'] = {'28H0.IFF': [{'offset': 1}]}
            p.write_text(json.dumps(doc), newline='\n')
            with self.assertRaisesRegex(ValueError, 'unowned'):
                repair.load_manifest(p)
            doc['scope_sha256'] = '0'*64
            p.write_text(json.dumps(doc), newline='\n')
            with self.assertRaisesRegex(ValueError, 'scope differs'):
                repair.load_manifest(p)

    def test_sealed_span_is_idempotent_preserves_neighbors_and_refuses_tampering(self):
        b = repair.shared._b765()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp);(base/'part.span').write_bytes(b'new')
            p = dict(offset=3, length=3, replacement='part.span', before_sha256=repair.sha(b'old'), after_sha256=repair.sha(b'new'))
            result, receipt = b.apply_spans(b'abcoldXYZ', [p], base)
            self.assertEqual(result, b'abcnewXYZ')
            self.assertTrue(receipt['outside_scope_identical'])
            self.assertEqual(b.apply_spans(result, [p], base)[0], result)
            with self.assertRaisesRegex(ValueError, 'unexpected input'):
                b.apply_spans(b'abcBADXYZ', [p], base)
            (base/'part.span').write_bytes(b'BAD')
            with self.assertRaisesRegex(ValueError, 'replacement size/hash'):
                b.apply_spans(result, [p], base)


if __name__ == '__main__':
    unittest.main()
