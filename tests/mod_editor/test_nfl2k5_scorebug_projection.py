"""Static v8 witness audit. These tests reject v8 as a literal ESPN v9 bar."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(Path(__file__).resolve().parent)]
from test_nfl2k5_scorebug_runtime import XBE,PACK,HAVE_UC
from mod_editor.core import nfl2k5_scorebug_ingame as r,nfl2k5_scorebug_resources as a
from nfl2k5_scorebug_projection import (native_geometry, v7_baseline, read_fonts, native_text_draw,
                                      native_team_binding_audit, containment_failures, render_native,
                                      static_receipts)


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC and importlib.util.find_spec('PIL'),
                     'pinned USA XBE, pack 0, Pillow and Unicorn required')
class ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xbe=XBE.read_bytes()
        with PACK.open('rb') as f:
            view=a.PackView.from_fd(f.fileno(),0,PACK.stat().st_size)
            cls.spans={n:view[v['pack_offset']:v['pack_offset']+v['span_size']] for n,v in a.RESOURCES.items()}
        cls.after=r.decode(r.apply(cls.spans['score_bug'],'score_bug')[0])[1]
        cls.atlas=r.apply(cls.spans['score_buga'],'score_buga',inputs=cls.spans)[0]
        cls.fonts=read_fonts(PACK)
        cls.capture={}
        # A static proof must never install the runtime to get a usable fixture.
        from mod_editor.core import nfl2k5_scorebug_runtime as runtime
        with mock.patch.object(runtime,'apply',side_effect=AssertionError('runtime is forbidden')):
            cls.normal=native_geometry(cls.xbe,cls.after,texture_span=cls.atlas,fonts=cls.fonts,capture=cls.capture)
        cls.addClassCleanup(cls.capture['machine'].close)
        cls.normal.update(native_text_draw(cls.capture))

    def test_reference_rails_are_measured_but_actual_visible_v8_frame_fails_them(self):
        from PIL import Image
        path=ROOT/'docs/scorebug_ingame/target_NO_MIA.png'
        if not path.is_file():self.skipTest('target_NO_MIA.png reference absent')
        with Image.open(path) as source:
            im=source.convert('RGB')
        self.assertEqual(im.size,(1280,960))
        # Long neutral frame rails distinguish the scorebug from green field
        # lines. ROI excludes the synthetic footer and watermark.
        rails=[]
        for y in range(700,880):
            start=None
            for x in range(im.width):
                color=im.getpixel((x,y));hit=max(color)-min(color)<20
                if hit and start is None:start=x
                if start is not None and (not hit or x==im.width-1):
                    if x-start>900:rails.append((start,y,x,y))
                    start=None
        measured=[min(v[0] for v in rails)/2,min(v[1] for v in rails)/2,
                  max(v[2] for v in rails)/2,max(v[3] for v in rails)/2]
        self.assertEqual(measured,[84,381,560,429])
        # The previous test measured the hidden frame in mode 0. Native FC200
        # selects yscore_buga1, whose left edge misses the rails by four pixels.
        self.assertEqual(self.normal['frame_material'],'yscore_buga1')
        self.assertAlmostEqual(self.normal['frame'][0],79.964,delta=.01)
        self.assertGreater(abs(measured[0]-self.normal['frame'][0]),2)
        self.assertEqual(self.normal['native_root_matrix'][12:14],[320,408])
        self.assertIn('yscore_buga1',containment_failures(self.normal,measured))

    def test_both_modes_and_slide_are_safe_but_score_panels_escape_the_bar(self):
        for mode in (0,1):
            for slide in (0,1):
                geometry=native_geometry(self.xbe,self.after,mode=mode,slide=slide)
                for name in ('frame','clock','down'):
                    x0,y0,x1,y1=geometry[name]
                    self.assertTrue(0<=x0<x1<=640,(name,geometry[name]))
                    self.assertTrue(16<=y0<y1<=464,(name,geometry[name]))
                self.assertLess(geometry['frame_instructions'],16000)
                self.assertIn('zscore_buga',containment_failures(geometry))
                self.assertAlmostEqual(geometry['objects']['zscore_buga'][3],453.19,delta=.02)
                self.assertEqual(geometry['frame_material'],'yscore_buga1' if mode==0 else 'yscore_buga')

    def test_widescreen_activates_real_hook_without_vertical_scale_or_shift(self):
        normal=self.normal
        wide=native_geometry(self.xbe,self.after,widescreen=True)
        for name in ('frame','clock','down'):
            for i in (1,3):self.assertAlmostEqual(normal[name][i],wide[name][i],places=4)
            self.assertAlmostEqual(wide[name][2]-wide[name][0],(normal[name][2]-normal[name][0])*27/32,places=3)
        # Display stretch cancels this contraction and retains 4:3 HUD proportions.
        self.assertAlmostEqual((wide['frame'][2]-wide['frame'][0])*32/27,
                               normal['frame'][2]-normal['frame'][0],places=3)

    def test_shipped_v7_baseline_does_not_prove_a_twofold_mesh_scale(self):
        decoded,_=v7_baseline(self.spans)
        before=native_geometry(self.xbe,decoded,root=(320,424))
        self.assertAlmostEqual(before['frame'][1]-self.normal['frame'][1],16,places=3)
        self.assertAlmostEqual(before['frame'][2]-before['frame'][0],
                               self.normal['frame'][2]-self.normal['frame'][0],delta=.02)
        self.assertAlmostEqual(self.normal['clock'][2]-self.normal['clock'][0],158,delta=.02)

    def test_native_score_transforms_explain_lower_row_omitted_by_old_harness(self):
        disabled=native_geometry(self.xbe,self.after,score_transforms=False)
        self.assertLess(disabled['frame_instructions'],12000)
        self.assertAlmostEqual(disabled['objects']['zscore_buga'][3],427,delta=.02)
        self.assertAlmostEqual(self.normal['objects']['zscore_buga'][3]-disabled['objects']['zscore_buga'][3],
                               26.19,delta=.02)
        for callback in ('0xfc050','0xfc070'):
            row=next(d for d in self.normal['draws'] if d['callback']==callback)
            self.assertEqual(row['text'],'0')
            self.assertAlmostEqual(max(v['screen'][1] for v in row['vertices']),442.201,delta=.01)
            self.assertIn(callback+':0',containment_failures(self.normal))

    def test_native_binding_and_glyph_trace_contains_clocks_and_no_placeholder_text(self):
        bindings=self.normal['bindings']
        self.assertEqual([b['name'] for b in bindings],
                         ['home_city','away_city','Quarter','Gameclock3','Gameclock4'])
        self.assertEqual([b['node_index'] for b in bindings],[3,1,5,7,9])
        self.assertTrue(all(b['enabled'] for b in bindings))
        draws={d['callback']:d for d in self.normal['draws']}
        self.assertEqual(draws['0xfc090']['text'],'1st')
        self.assertEqual(draws['0xfc100']['text'],'')
        self.assertEqual(draws['0xfc150']['text'],'13:10')
        self.assertEqual(draws['0xfbe30']['text'],':12')
        self.assertEqual(draws['0xfc7d0']['text'],'1st & 10')
        self.assertEqual(draws['0xfc030']['text'],'oak')
        self.assertEqual(draws['0xfc010']['text'],'gb')
        self.assertEqual(draws['0xfc010']['color'],'0xffc0c000')
        self.assertFalse(any('---' in d['text'] for d in draws.values()))
        self.assertGreater(self.normal['draw_instructions'],10000)
        self.assertLess(self.normal['draw_instructions'],20000)

    def test_native_clock_callbacks_switch_at_ten_minutes_and_quarter_updates(self):
        m=self.capture['machine']
        try:
            for seconds,quarter,short,long,label in ((600,2,'','10:00','2nd'),(599,3,'9:59','','3rd'),
                                                    (0,4,'0:00','','4th'),(600.1,1,'','10:01','1st')):
                m.float(m.game_clock+16,seconds);m.put(0xe602c4,quarter)
                rows={d['callback']:d for d in native_text_draw(self.capture)['draws']}
                self.assertEqual(rows['0xfc100']['text'],short)
                self.assertEqual(rows['0xfc150']['text'],long)
                self.assertEqual(rows['0xfc090']['text'],label)
        finally:
            m.float(m.game_clock+16,790);m.put(0xe602c4,1)

    def test_two_float_fields_are_shadow_offsets_not_font_scale(self):
        normal=native_text_draw(self.capture)
        altered=native_text_draw(self.capture,shadow_offset=(20,30,5))
        for first,second in zip(normal['draws'],altered['draws']):
            self.assertEqual(first['vertices'],second['vertices'])
            self.assertEqual(second['shadow_offset'],[20,30,5])
        # Restore the shared ordinary text object for subsequent independent draws.
        self.capture['machine'].uc.mem_write(0xa957f0+0x30,struct.pack('<3f',2,2,1))
        self.assertEqual(next(d for d in normal['draws'] if d['callback']=='0xfc7d0')['font'],'font1')

    def test_strip_is_black_vertex_colour_and_quarter_is_bound_black_text(self):
        words={struct.unpack_from('<I',self.after,r.layout.S1+i*10)[0] for i in range(48,64)}
        self.assertEqual(words,{0x99000000})
        quarter=next(d for d in self.normal['draws'] if d['callback']=='0xfc090')
        self.assertEqual(quarter['color'],'0xff000000')
        self.assertTrue(quarter['vertices'])

    def test_all_32_static_team_bindings_ignore_team_identity(self):
        rows=native_team_binding_audit(self.capture)
        self.assertEqual(len(rows),32)
        self.assertEqual({d['asset_code'] for d in rows},{d['asset_code'] for d in a.TEAM_LOGOS.values()})
        for row in rows:
            self.assertEqual(row['context_reads'],[])
            self.assertEqual(row['textures'],rows[0]['textures'])
            self.assertEqual(len(set(row['textures'].values())),1)
            self.assertNotEqual(next(iter(row['textures'].values())),'0x0')
        self.assertFalse(self.normal['scorebug_runtime_installed'])

    def test_native_audit_rejects_foreign_callbacks_and_runtime_hooks(self):
        from nfl2k5_scorebug_projection import validate_native_code
        for va in (0xfc090,0xfc360,0x46920,0xfce56,0xfcfa2):
            changed=bytearray(self.xbe)
            changed[r.layout.sbpos.va_to_off(changed,va)]^=1
            with self.assertRaisesRegex(ValueError,'foreign|runtime'):
                validate_native_code(bytes(changed))

    def test_static_replay_and_native_overlap_keep_retail_wrapper_plus_14(self):
        receipt=static_receipts(self.xbe,self.spans)
        self.assertTrue(receipt['xbe_replay_identical'])
        self.assertFalse(receipt['v9'])
        self.assertFalse(receipt['temporary_disc_created'])
        for resource in receipt['resources']:
            self.assertTrue(resource['wrapper_identical'])
            self.assertEqual(resource['wrapper_plus_14_before'],resource['wrapper_plus_14_after'])
            self.assertEqual(resource['decoded_sha256'],resource['native_decoded_sha256'])

    def test_render_uses_native_glyphs_and_reports_reversed_mark_winding(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp).resolve()/'native.png'
            proof=render_native(self.after,self.atlas,self.fonts,self.normal,target)
            with Image.open(target) as image:
                self.assertEqual(image.size,(640,480))
                # The rewritten strip's source white cannot bypass its native
                # black vertex colour in the software multiplication model.
                self.assertLess(max(image.getpixel((285,414))),90)
            self.assertGreater(proof['winding']['zz_ESPN_bug']['positive'],0)
            self.assertEqual(proof['winding']['zz_ESPN_bug']['negative'],0)
            self.assertGreater(proof['winding']['dscore_buga']['negative'],0)
            self.assertFalse(proof['raster_policy']['gpu_state_proved'])


if __name__=='__main__':unittest.main()
