"""Native broadcast acceptance with hash-pinned historical negative controls."""
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
from nfl2k5_scorebug_projection import (native_geometry, v7_baseline, v8_baseline, read_fonts, native_text_draw,
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
        cls.before,cls.old_atlas=v8_baseline(cls.spans)
        cls.fonts=read_fonts(PACK)
        cls.capture={}
        # A static proof must never install the runtime to get a usable fixture.
        from mod_editor.core import nfl2k5_scorebug_runtime as runtime
        with mock.patch.object(runtime,'apply',side_effect=AssertionError('runtime is forbidden')):
            cls.normal=native_geometry(cls.xbe,cls.after,texture_span=cls.atlas,fonts=cls.fonts,capture=cls.capture)
        cls.addClassCleanup(cls.capture['machine'].close)
        cls.normal.update(native_text_draw(cls.capture))

    def test_real_reference_rails_and_actual_frame_contain_current_scene(self):
        from PIL import Image
        path=ROOT/'docs/scorebug_ingame/reference_LV_HOU_broadcast.jpeg'
        if not path.is_file():self.skipTest('real LV/HOU broadcast JPEG absent')
        self.assertEqual(r.digest(path.read_bytes()),r.exact.REFERENCE_SHA256)
        with Image.open(path) as image:self.assertEqual(image.size,(1920,1080))
        self.assertEqual(r.exact.SOURCE_RAILS,(434,942,1488,1054))
        measured=[434/3,16+942*448/1080,1488/3,16+1054*448/1080]
        self.assertEqual(self.normal['frame_material'],'yscore_buga1')
        for actual,expected in zip(self.normal['frame'],measured):
            self.assertAlmostEqual(actual,expected,delta=.01)
        self.assertEqual(self.normal['native_root_matrix'][12:14],[320,408])
        self.assertEqual(containment_failures(self.normal,measured),{})
        self.assertEqual(containment_failures(self.normal,self.normal['frame'],.02),{})

    def test_modes_aspects_score_rotation_and_visibility_endpoints_stay_inside(self):
        for mode in (0,1):
            for widescreen in (False,True):
                for phase,slide in ((0,0),(0,1),(.25,1),(.5,1),(.75,1),(.999,1)):
                    with self.subTest(mode=mode,wide=widescreen,phase=phase,slide=slide):
                        capture={}
                        geometry=native_geometry(self.xbe,self.after,mode=mode,widescreen=widescreen,
                                                 score_phase=phase,slide=slide,fonts=self.fonts,capture=capture,
                                                 score_values=(100,999),previous_scores=(99,111))
                        try:
                            geometry.update(native_text_draw(capture))
                            self.assertEqual(containment_failures(geometry),{})
                            self.assertEqual(containment_failures(geometry,geometry['frame'],.02),{})
                            self.assertLess(geometry['frame_instructions'],16000)
                            self.assertEqual(geometry['frame_material'],'yscore_buga1' if mode==0 else 'yscore_buga')
                        finally:capture['machine'].close()

    def test_alternate_native_event_glyphs_fit_in_the_frame(self):
        for element,expected in ((2,'Hangtime: 0.0'),(3,'FLAG'),(4,'Ball at Midfield'),(5,'FUMBLE')):
            capture={}
            geometry=native_geometry(self.xbe,self.after,fonts=self.fonts,capture=capture,
                                     visible_elements=(element,))
            try:
                geometry.update(native_text_draw(capture))
                self.assertEqual(geometry['draws'][0]['text'],expected)
                self.assertEqual(geometry['draws'][0]['color'],'0xffffffff')
                self.assertEqual(containment_failures(geometry,geometry['frame'],.02),{})
            finally:capture['machine'].close()

    def test_widescreen_activates_real_hook_without_vertical_scale_or_shift(self):
        normal=self.normal
        wide=native_geometry(self.xbe,self.after,widescreen=True)
        for name in ('frame','clock','down'):
            for i in (1,3):self.assertAlmostEqual(normal[name][i],wide[name][i],places=4)
            self.assertAlmostEqual(wide[name][2]-wide[name][0],(normal[name][2]-normal[name][0])*27/32,places=3)
        # Display stretch cancels this contraction and retains 4:3 HUD proportions.
        self.assertAlmostEqual((wide['frame'][2]-wide['frame'][0])*32/27,
                               normal['frame'][2]-normal['frame'][0],places=3)

    def test_v8_negative_control_proves_the_static_defects(self):
        capture={}
        before=native_geometry(self.xbe,self.before,texture_span=self.old_atlas,fonts=self.fonts,
                               capture=capture,baseline_v8=True)
        try:
            before.update(native_text_draw(capture))
            # The historical failure is against its own v8 target rails.
            failures=containment_failures(before,[84,381,560,429])
            self.assertIn('yscore_buga1',failures)
            self.assertIn('zscore_buga',failures)
            self.assertAlmostEqual(before['frame'][0],79.964,delta=.01)
            self.assertAlmostEqual(before['objects']['zscore_buga'][3],453.19,delta=.02)
            for callback in ('0xfc050','0xfc070'):
                self.assertIn(callback+':0',failures)
            self.assertEqual(next(d for d in before['draws'] if d['callback']=='0xfc090')['color'],'0xff000000')
            self.assertEqual({struct.unpack_from('<I',self.before,r.layout.S1+i*10)[0] for i in range(48,64)},
                             {0x99000000})
        finally:capture['machine'].close()
        disabled=native_geometry(self.xbe,self.before,score_transforms=False,baseline_v8=True)
        self.assertAlmostEqual(disabled['objects']['zscore_buga'][3],427,delta=.02)
        self.assertEqual(self.normal['widescreen'],False)
        # Old executable/resource inputs remain historical, not an accepted v9 replay.
        self.assertEqual(r.status(self.old_atlas,'score_buga'),'foreign')
        scene,_=r.layout.refit(self.spans['score_bug'],self.before)
        self.assertEqual(r.status(scene,'score_bug'),'foreign')

    def test_native_binding_and_glyph_trace_contains_clocks_and_no_placeholder_text(self):
        bindings=self.normal['bindings']
        self.assertEqual([b['name'] for b in bindings],
                         ['home_city','away_city','Quarter','Gameclock3','Gameclock4'])
        self.assertEqual([b['node_index'] for b in bindings],[3,1,5,7,9])
        self.assertTrue(all(b['enabled'] for b in bindings))
        draws={d['callback']:d for d in self.normal['draws']}
        self.assertEqual(draws['0xfc090']['text'],'1ST')
        self.assertEqual(draws['0xfc100']['text'],'')
        self.assertEqual(draws['0xfc150']['text'],'13:10')
        self.assertEqual(draws['0xfbe30']['text'],'12')
        self.assertEqual(draws['0xfc7d0']['text'],'1st & 10')
        self.assertEqual(draws['0xfc030']['text'],'OAK')
        self.assertEqual(draws['0xfc010']['text'],'GB')
        self.assertEqual(draws['0xfc010']['color'],'0xffffff40')
        self.assertFalse(any('---' in d['text'] for d in draws.values()))
        self.assertGreater(self.normal['draw_instructions'],10000)
        self.assertLess(self.normal['draw_instructions'],20000)

    def test_native_clock_callbacks_switch_at_ten_minutes_and_quarter_updates(self):
        m=self.capture['machine']
        try:
            for seconds,quarter,short,long,label in ((600,2,'','10:00','2ND'),(599,3,'9:59','','3RD'),
                                                    (0,4,'0:00','','4TH'),(600.1,1,'','10:01','1ST')):
                m.float(m.game_clock+16,seconds);m.put(0xe602c4,quarter)
                rows={d['callback']:d for d in native_text_draw(self.capture)['draws']}
                self.assertEqual(rows['0xfc100']['text'],short)
                self.assertEqual(rows['0xfc150']['text'],long)
                self.assertEqual(rows['0xfc090']['text'],label)
        finally:
            m.float(m.game_clock+16,790);m.put(0xe602c4,1)

    def test_three_digit_scores_inches_overtime_and_possession_use_native_data(self):
        m=self.capture['machine']
        try:
            m.put(m.home,100);m.put(m.away,999)
            m.put(m.play+4,4);m.float(m.play+0x28,1)
            m.identity(home='BAL',away='WSH');m.put(0xe602c4,5)
            m.float(m.game_clock+16,59);m.float(m.clock+16,4)
            for possession,yellow in ((0xe5fc20,'0xfc010'),(0xe5fc60,'0xfc030')):
                m.put(0xe60280,possession)
                drawn=native_text_draw(self.capture)
                rows={row['callback']:row for row in drawn['draws']}
                for callback,value in (('0xfc050','100'),('0xfc070','999'),('0xfc7d0','4th & Inches'),
                                       ('0xfc090','OT1'),('0xfc100','0:59'),('0xfbe30','04')):
                    self.assertEqual(rows[callback]['text'],value)
                self.assertEqual(rows[yellow]['color'],'0xffffff40')
                self.assertEqual(containment_failures({**self.normal,**drawn},self.normal['frame'],.02),{})
                # Three-digit score containment is proved; centre-cell crowding is a documented font residual.
                for callback,left,right in (('0xfc070',self.normal['frame'][0],self.normal['frame'][2]),('0xfc050',self.normal['frame'][0],self.normal['frame'][2])):
                    xs=[v['screen'][0] for v in rows[callback]['vertices']]
                    self.assertGreaterEqual(min(xs),left)
                    self.assertLessEqual(max(xs),right)
        finally:
            m.put(m.home,0);m.put(m.away,0);m.put(m.play+4,1);m.float(m.play+0x28,914)
            m.identity();m.put(0xe602c4,1);m.float(m.game_clock+16,790);m.float(m.clock+16,12)
            m.put(0xe60280,0xe5fc20)

    def test_two_float_fields_are_shadow_offsets_not_font_scale(self):
        normal=native_text_draw(self.capture)
        altered=native_text_draw(self.capture,shadow_offset=(20,30,5))
        for first,second in zip(normal['draws'],altered['draws']):
            self.assertEqual(first['vertices'],second['vertices'])
            self.assertEqual(second['shadow_offset'],[20,30,5])
        # Restore the shared ordinary text object for subsequent independent draws.
        self.capture['machine'].uc.mem_write(0xa957f0+0x30,struct.pack('<3f',2,2,1))
        self.assertEqual(next(d for d in normal['draws'] if d['callback']=='0xfc7d0')['font'],'font4')

    def test_text_contrast_font_selection_and_neutral_subset(self):
        words={struct.unpack_from('<I',self.after,r.layout.S1+i*10)[0] for i in range(48,64)}
        self.assertEqual(words,{0xffffffff})
        for row in self.normal['draws']:
            callback=row['callback']
            expected=('0xffffff40' if callback == '0xfc010' else
                      '0xff242622' if callback in ('0xfc090','0xfc100','0xfc150') else '0xffffffff')
            self.assertEqual(row['color'],expected)
            self.assertTrue(all(v['color']==expected for v in row['vertices']))
            if callback in ('0xfc050','0xfc070'):self.assertEqual(row['font'],'font8')
        self.assertEqual(self.normal['objects']['zz_ESPN_bug'][0],self.normal['objects']['zz_ESPN_bug'][2])
        self.assertGreater(self.normal['objects']['dscore_buga'][2]-self.normal['objects']['dscore_buga'][0],80)

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
        self.assertTrue(receipt['native_refit_verified'])
        self.assertFalse(receipt['pixel_match_claimed'])
        self.assertEqual(receipt['version'],r.VERSION)
        self.assertFalse(receipt['temporary_disc_created'])
        for resource in receipt['resources']:
            self.assertTrue(resource['wrapper_identical'])
            self.assertEqual(resource['wrapper_plus_14_before'],resource['wrapper_plus_14_after'])
            self.assertEqual(resource['decoded_sha256'],resource['native_decoded_sha256'])

    def test_render_has_no_network_mark_and_consistent_visible_winding(self):
        from PIL import Image, ImageChops
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp).resolve()/'native.png'
            proof=render_native(self.after,self.atlas,self.fonts,self.normal,target)
            self.assertEqual(proof['winding']['zz_ESPN_bug'],dict(positive=0,negative=0))
            self.assertEqual(proof['winding']['yscore_buga1'],dict(positive=0,negative=30))
            self.assertEqual(proof['winding']['dscore_buga'],dict(positive=0,negative=2))
            self.assertEqual(proof['winding']['cscore_buga'],dict(positive=0,negative=2))
            self.assertFalse(proof['raster_policy']['gpu_state_proved'])
            culled=Path(tmp).resolve()/'culled.png'
            render_native(self.after,self.atlas,self.fonts,self.normal,culled,cull_positive=True)
            with Image.open(target) as first,Image.open(culled) as second:
                box=(140,400,500,458)
                self.assertIsNone(ImageChops.difference(first.crop(box),second.crop(box)).getbbox())


if __name__=='__main__':unittest.main()
