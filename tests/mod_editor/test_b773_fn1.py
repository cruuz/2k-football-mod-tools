"""Native decoder allocation checks and block-number handoff through Studio writers."""
from pathlib import Path
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import nfl_txtr as tx
import nfl_vc_lz_fill as fill
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_modern_metlife as ml
from mod_editor.core import nfl2k5_usbank_model as um
from mod_editor.core import nfl2k5_lucas_oil_model as lm


class NativeChecks(unittest.TestCase):
    def test_final_flag_read_fails_even_with_scratch(self):
        expected = b'abc' * 10
        stream = fill.serialize(30, 3, 10, [('L', b) for b in b'abc'] + [('M', 3, 3), ('M', 6, 6), ('M', 6, 6), ('M', 6, 6), ('M', 6, 6)])
        for scratch in (0, 16, 128):
            with self.subTest(scratch=scratch):
                self.assertLessEqual(tx.minimum_vc_lz_overlap_scratch(stream, len(stream), len(expected)), scratch)
                with self.assertRaisesRegex(tx.TxtrError, 'read outside'):
                    tx.check_vc_lz_native(stream, len(stream), scratch, expected)
                padded = stream + b'\0'
                tx.check_vc_lz_native(padded, len(padded), max(scratch, 16), expected)

    def test_last_match_also_fetches_flag(self):
        expected = b'abcdefgabc'
        stream = fill.serialize(10, 3, 10, [('L', b) for b in b'abcdefg'] + [('M', 7, 3)])
        with self.assertRaisesRegex(tx.TxtrError, 'read outside'):
            tx.check_vc_lz_native(stream, len(stream), 16, expected)
        tx.check_vc_lz_native(stream + b'\0', len(stream) + 1, 16, expected)

    def test_exact_output_and_alias_are_checked(self):
        expected = bytes(range(64)) * 16
        stream = tx.compress_vc_lz(expected)[0]
        padded = stream + bytes(17)
        tx.check_vc_lz_native(padded, len(padded), 32, expected)
        with self.assertRaises(tx.TxtrError):
            tx.check_vc_lz_native(padded, len(padded), 32, b'x' * len(expected))

    def test_grown_literal_scene_reserves_the_complete_input_allocation(self):
        from mod_editor.core import nfl2k5_scne_builder as sb
        expected=bytes(range(120))
        span,info=sb.compressed_chunk('SCNE',expected,0,len(expected),stream_tag=3,offset_bits=10,optimal=False)
        chunk=tx.parse_chunks(span)[0]
        tx.check_vc_lz_native(span[32:],chunk.stored_size,chunk.overlap_scratch_bytes,expected)
        self.assertGreaterEqual(chunk.system_bytes+chunk.video_bytes+chunk.overlap_scratch_bytes,chunk.stored_size)

    def test_fitters_reject_an_unsafe_first_candidate(self):
        from unittest.mock import patch
        from mod_editor.core import nfl2k5_modern_color as colour
        expected = bytes(range(64)) * 32
        stream = tx.compress_vc_lz(expected, offset_bits=10)[0]
        stored = (len(stream) + 1023) & ~15
        span = tx.HEADER.pack(b'SCNE', stored, 0, len(expected), tx.COMPRESSED_SENTINEL, 16, 0, 0) + stream + bytes(stored-len(stream))
        real = tx.check_vc_lz_native
        accepted = []
        def reject_once(*args):
            if not accepted:
                accepted.append(False)
                raise tx.TxtrError('native synthetic rejection')
            result = real(*args)
            accepted.append(True)
            return result
        for fitter in (colour.fit_fixed_span, ml.fit_span):
            accepted.clear()
            with patch.object(tx, 'check_vc_lz_native', side_effect=reject_once):
                result, _ = fitter(span, expected)
            self.assertGreater(len(accepted), 1)
            real(result[32:], stored, 16, expected)


class NumberContract(unittest.TestCase):
    def test_manifest_pins_existing_authored_atlas_and_four_venues(self):
        doc = json.loads((mv.DATA_DIR/'numbers/manifest.json').read_text())
        self.assertEqual(doc['venues'], dict(s06='CIN', s11='IND', s15='MIN', s28='TEN'))
        self.assertEqual(hashlib.sha256((mv.DATA_DIR/'numbers/block.png').read_bytes()).hexdigest(),
                         '1a6e2517c6f5f745a0a98712c4f19870ae964c8f81563d99351f2a1948d56718')
        for prefix in ('s06','s11','s15','s28'):
            item, = mv.default_numbers(prefix)
            self.assertEqual((item['key'], item['layer'], item['size']), ('numbers','full',[256,256]))
        for prefix in ('s13','s18','s19','a06','a48','s40'):
            self.assertEqual(mv.default_numbers(prefix), [])

    def test_defaults_and_explicit_user_numbers_reach_both_model_loaders(self):
        from PIL import Image
        for prefix, model in (('s11',lm),('s15',um)):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'TEAM/venue';path.mkdir(parents=True)
                art = mv.DATA_DIR/'numbers/block.png'
                (path/'mark.png').write_bytes(art.read_bytes())
                item = dict(scene='field', material='endzone_N_M', layer='full', size=[256,256],
                            file='mark.png',sha256=hashlib.sha256(art.read_bytes()).hexdigest())
                doc = dict(schema=mv.ART_SCHEMA, venue_prefix=prefix, items=[item])
                manifest = path/'manifest.json'
                manifest.write_text(json.dumps(doc),newline='\n')
                first = mv.load_art(directory)['venues'][prefix]
                self.assertIn('numbers', model.team_field_art(directory))
                self.assertEqual(sum(i['key']=='numbers' for i in first['items']),1)
                Image.new('RGBA',(256,256),(10,20,30,40)).save(path/'user.png')
                doc['items'].append(dict(item,material='numbers',file='user.png',sha256=hashlib.sha256((path/'user.png').read_bytes()).hexdigest()))
                manifest.write_text(json.dumps(doc),newline='\n')
                second=mv.load_art(directory)['venues'][prefix]
                self.assertNotEqual(first['digest'],second['digest'])
                self.assertEqual(tuple(model.team_field_art(directory)['numbers'][0,0]),(10,20,30,40))

    def test_numbers_reject_an_overlay_or_resized_atlas(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'TEAM/venue';path.mkdir(parents=True)
            (path/'numbers.png').write_bytes((mv.DATA_DIR/'numbers/block.png').read_bytes())
            item=dict(scene='field',material='numbers',layer='overlay',size=[256,256],file='numbers.png',
                      sha256=hashlib.sha256((path/'numbers.png').read_bytes()).hexdigest())
            for change in ({},dict(layer='full',size=[128,128])):
                doc=dict(schema=mv.ART_SCHEMA,venue_prefix='s28',items=[dict(item,**change)])
                (path/'manifest.json').write_text(json.dumps(doc),newline="\n")
                with self.assertRaisesRegex(mv.ModernVenuesError,'full 256x256'):
                    mv.load_art(directory)

    def test_numbers_keep_alpha_without_weather_or_turf_compositing(self):
        import numpy as np
        item, = mv.default_numbers('s28')
        art=item['rgba'];background=np.full_like(art,100)
        for weather in 'drs':
            result=mv.compose(item,background,background,art,weather)
            np.testing.assert_array_equal(result,art)
            self.assertTrue((result[...,3]==0).any())

    def test_model_painters_preserve_full_number_detail_on_low_rungs(self):
        import numpy as np
        from unittest.mock import patch
        atlas=mv.default_numbers('s11')[0]['rgba'];captured=[]
        rows={lm.GRASS_MATERIAL:dict(width=8,height=8),lm.OUTSIDE_MATERIAL:dict(width=8,height=8),'numbers':dict(width=256,height=256)}
        def read(*args):return np.full((8,8,4),100,dtype=np.uint8),None
        def write(_out,_sys,row,art,*args,**kwargs):
            if row is rows['numbers']:captured.append(art.copy())
        for model in (lm,um):
            captured.clear()
            with patch.object(ml,'texture_rows',return_value=rows),patch.object(ml,'read_p8',side_effect=read),patch.object(ml,'write_p8',side_effect=write):
                if model is um:
                    with patch.object(um,'_rgba',return_value=np.full((8,8,4),100,dtype=np.uint8)),patch.object(um,'remap_grass_uv'):
                        model.paint_field(b'abc',{},0,'s',team={'numbers':atlas},half=True,cap=64)
                else:model.paint_field(b'abc',{},0,'s',team={'numbers':atlas},half=True,cap=64)
            self.assertEqual(len(captured),1)
            np.testing.assert_array_equal(captured[0],atlas)


if __name__ == '__main__':
    unittest.main()
