"""NV2A packet, palette, combiner and native tint-binding regressions."""
from pathlib import Path
import importlib.util
import json
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_scorebug_teams as teams
from tools.scorebug_sprite import gpu, xemu_model


class ReferenceTests(unittest.TestCase):
    def test_changed_byte_count_includes_block_edges_and_partial_blocks(self):
        from mod_editor.core.nfl2k5_xbe_space import count_differing_bytes
        before=bytes(range(256))*513
        after=bytearray(before)
        for index in (0,65535,65536,131071,len(before)-1):after[index]^=255
        self.assertEqual(count_differing_bytes(before,after),5)
        self.assertEqual(count_differing_bytes(before,after+bytes(300)),5)
        self.assertEqual(count_differing_bytes(before[:-1],after),4)
        self.assertEqual(count_differing_bytes(before,before),0)
        self.assertEqual(count_differing_bytes(b'',after),0)
        inverse=bytes(v^255 for v in before)
        self.assertEqual(count_differing_bytes(before,inverse),len(before))

    def test_packets_preserve_increasing_and_nonincreasing_writes(self):
        got = gpu.methods([0x00081b00, 17, 23, 0x40081800, 4, 9])
        self.assertEqual([(m['method'],m['value']) for m in got],
                         [(0x1b00,17),(0x1b04,23),(0x1800,4),(0x1800,9)])
        for bad in ([0x80081b00,17,23],[0x00081b00,17],[0x20000001]):
            with self.assertRaises(ValueError): gpu.methods(bad)

    def test_combiner_mappings_and_measured_final_constant(self):
        state = {f'0x{k:04x}':v for k,v in {
            0x260:0xd8d41010,0xac0:0xc8c40000,0xaa0:0x100c0,0x1e40:0x100c0,
            0x1e60:0x11101,0x288:0xf030c00,0x28c:0x11331c80,
            0xa60:0,0xa80:0,0x1e20:0,0x1e24:0}.items()}
        self.assertEqual(xemu_model.combiner(state,(1,1,1,1),(.5,)*4),(1,1,1,1))
        # A hypothetical captured fog mix would darken both identical materials.
        state['0x1e20']=0xff000000
        self.assertEqual(xemu_model.combiner(state,(1,1,1,1),(.5,)*4,fog=(.1,.1,.1,0)),(.1,.1,.1,1))
        state['0x1e60']=2
        with self.assertRaises(ValueError):xemu_model.combiner(state,(1,)*4,(.5,)*4)
        self.assertEqual(xemu_model.input_value(0x21,{1:(-.5,.5,1.5,0)}),(1,.5,0))

    def test_official_tints_are_recomputed_from_parent_not_trusted_metadata(self):
        data=json.loads((teams.DATA/'team_accents.json').read_text())
        data['teams']['LV']['wing']='#FF0080'
        data['teams']['LV']['candidates']['forged']={'hex':'#FF0080','parent':'#000000','contrast_white':7}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'accents.json';path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Foreign'):teams.load(path)

    def test_neutral_shapes_cannot_multiply_in_broadcast_hues(self):
        spec,image=sprite.load_layout()
        for row in spec['static']:
            if row['cell']=='logo':continue
            for red,green,blue,alpha in image.crop(spec['cells'][row['cell']]['box']).getdata():
                if alpha:self.assertEqual((red,green),(green,blue),row['cell'])
        compiled=sprite.compile_folder()
        magic,count,offset=teams.FOOTER.unpack(compiled.table[-12:])
        self.assertEqual((magic,count),(teams.MAGIC,52))
        for index,team in enumerate(sorted(teams.load().values(),key=lambda t:t['slot'])):
            values=teams.ENTRY.unpack_from(compiled.table,offset-sprite.TABLE_OFFSET+index*teams.ENTRY.size)
            self.assertEqual(values[2:],tuple(0xff000000|int(team[r][1:],16) for r in ('wing','rim','plate')))


PACK=ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
@unittest.skipUnless(PACK.is_file() and importlib.util.find_spec('unicorn'), 'retail resources and Unicorn required')
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.preview=sprite.NativePreview()

    def test_texture_cache_tracks_pixel_options_and_template_changes(self):
        from PIL import Image
        from mod_editor.core.nfl2k5_scorebug_assets import texture_chunk
        pixels=Image.new('RGBA',(32,32),(255,255,255,255))
        first,receipt=texture_chunk('cacheproof',pixels,self.preview.atlas,alpha_aware=True)
        receipt['sha256']='mutated caller receipt'
        again,fresh=texture_chunk('cacheproof',pixels,self.preview.atlas,alpha_aware=True)
        self.assertEqual(first,again)
        self.assertNotEqual(fresh['sha256'],receipt['sha256'])
        pixels.putpixel((16,16),(0,0,0,255))
        changed,_=texture_chunk('cacheproof',pixels,self.preview.atlas,alpha_aware=True)
        reserved,_=texture_chunk('cacheproof',pixels,self.preview.atlas,alpha_aware=True,
                                  reserved_colours=((255,0,0,255),))
        self.assertNotEqual(first,changed)
        self.assertNotEqual(changed,reserved)
        with self.assertRaises(ValueError):
            texture_chunk('cacheproof',pixels,b'foreign',alpha_aware=True)

    def test_decoded_logo_cache_retains_pin_checks_and_image_isolation(self):
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        record=scene.TEAM_LOGOS['LV']
        with PACK.open('rb') as stream:
            stream.seek(record['pack_offset']);span=stream.read(record['span_size'])
        first=scene.texture_image(span,record);expected=first.tobytes()
        first.putpixel((0,0),(255,0,128,255))
        self.assertEqual(scene.texture_image(span,record).tobytes(),expected)
        with self.assertRaises(ValueError):
            scene.texture_image(span,dict(record,decoded_sha256='0'*64))

    def test_actual_native_tints_every_slot_possession_and_aspect(self):
        from mod_editor.core import nfl2k5_scorebug_runtime as owner
        palette=teams.load();payload=owner.apply(self.preview.payload)[0]
        code,data=owner.sites(payload);labels=owner.code_for(code['va'],data['va'])[1]
        for wide in (False,True):
            _,capture=self.preview.capture(dict(home='LV',away='DET'),wide)
            m=capture['machine'];compiled=self.preview.modes[wide]['compiled']
            try:
                for name,t in palette.items():
                    m.identity(home=name,away=name,home_code=t['asset_code'],away_code=t['asset_code'],home_kind=t['kind'],away_kind=t['kind'])
                    m.run(labels['setup'],limit=100000)
                    for possession in (0xe5fc20,0xe5fc60):
                        m.put(0xe60280,possession)
                        m.run(labels['update'],(0x3c888889,),limit=100000)
                        for q in compiled.quads:
                            tint=q.get('tint','none')
                            if tint=='none':continue
                            role='rim' if 'rim' in tint else 'plate' if tint=='possessing team' else 'wing'
                            word=m.get(capture['body']+0x2d20+q['vertex']*10)
                            self.assertEqual(word,0xff000000|int(t[role][1:],16),(name,wide,possession,q['name']))
            finally:m.close()

    def test_native_state_equal_and_independent_xemu_texture_decode(self):
        import nfl2k5_scorebug_projection as projection
        g,c=self.preview.capture(dict(home='LV',away='DET'),True)
        try:
            trace=gpu.capture_state(c);rows={r['name']:r for r in trace['rows']}
            label,score=rows['yscore_buga1'],rows['yscore_buga']
            for key in ('0x1b04','0x1b08','0x1b14','0x1b20','0x0260','0x0ac0','0x0288','0x028c','0x0344','0x0348','0x0350','0x0340'):
                self.assertEqual(label['state'][key],score['state'][key],key)
            for span in c['texture_spans'].values():
                got,_=xemu_model.texture(bytes(span));expected,_=projection._raster_texture(bytes(span))
                self.assertEqual(got.tobytes(),expected.tobytes())
            pipeline=xemu_model.Pipeline(trace);pipeline.select('yscore_buga1')
            self.assertEqual(pipeline.vertex_uv((-32768,32767)),(0,1))
            self.assertEqual(pipeline.fragment((255,)*4,(255,)*4,(19,)*4),(255,)*4)
            self.assertIsNone(pipeline.fragment((255,255,255,1),(255,)*4,(19,)*4))
            self.assertFalse(pipeline.receipt()['calibration_passed'])
        finally:c['machine'].close()


if __name__=='__main__':unittest.main()
