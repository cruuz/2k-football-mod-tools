"""Static scorebar: native state transitions, retail colour reads and witness proof."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(Path(__file__).resolve().parent)]
from test_nfl2k5_scorebug_runtime import XBE,PACK,HAVE_UC
from test_nfl2k5_scorebug_ingame_fix import box,overlap
from mod_editor.core import nfl2k5_scorebug_ingame as scene, nfl2k5_scorebar_v3 as v3
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
import nfl2k5_scorebug_projection as projection
import nfl2k5_scorebug_witness as historical
import nfl2k5_scorebar_v3_witness as witness

HAVE_IMAGES=all(importlib.util.find_spec(n) for n in ('PIL','numpy'))
RETAIL_REQUESTS={'pre_snap':[1,1,0,0,0,0], 'after_play':[1,0,0,0,1,0],
    'live':[0,0,0,0,0,0], 'kickoff':[0,1,1,0,0,0], 'flag':[0,0,0,1,0,0], 'fumble':[0,0,0,0,0,1]}
# Independent observations from the pinned executable, not a production palette.
PAIRS=((('BAL',0xff31145c),('JAX',0xff0c586d)),
       (('MIN',0xff422259),('NYJ',0xff253f36)),
       (('WAS',0xff86364a),('NYG',0xff191c5c)))


def luminance(word):
    rgb=[((word>>shift)&255)/255 for shift in (16,8,0)]
    linear=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
    return sum(c*w for c,w in zip(linear,(.2126,.7152,.0722)))


class ContrastTests(unittest.TestCase):
    def test_readable_white_and_yellow_bound_and_dark_primary_preservation(self):
        for word in (0xff000000,0xffffffff,0xff707070,0xff717171,0xff7f7f7f,0xff808080,
                     0xffff0000,0xff00ff00,0xff0000ff,*[c for p in PAIRS for _,c in p]):
            color=v3.contrast_color(word)
            self.assertLessEqual(max((color>>s)&255 for s in (0,8,16)),112)
            for text in (0xffffffff,0xffffff40):
                self.assertGreaterEqual((luminance(text)+.05)/(luminance(color)+.05),4.5)
            if max((word>>s)&255 for s in (0,8,16))<=112:self.assertEqual(word,color)


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC and HAVE_IMAGES,
                     'pinned USA XBE/pack, Unicorn, Pillow and numpy required')
class NativeV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_scorebug_exact import Build
        cls.build=Build(PACK,XBE);cls.addClassCleanup(cls.build.close)
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.output=Path(cls.temp.name).resolve()
        cls.span=scene.apply(cls.build.spans['score_bug'],'score_bug')[0]
        cls.decoded=scene.decode(cls.span)[1]
        cls.atlas=scene.apply(cls.build.spans['score_buga'],'score_buga')[0]

    def capture(self,**kwargs):
        capture={}
        with mock.patch.object(runtime,'apply',side_effect=AssertionError('runtime owner forbidden')):
            geometry=projection.native_geometry(self.build.payload,self.decoded,fonts=self.build.fonts,
                texture_span=self.atlas,capture=capture,visible_elements=(),**kwargs)
        self.addCleanup(capture['machine'].close)
        return geometry,capture

    def test_all_six_states_keep_middle_geometry_fonts_and_live_values_in_both_aspects_and_modes(self):
        clocks=('0xfc090','0xfc100','0xfbe30')
        for wide in (False,True):
            for mode in (0,1):
                geometry_reference=None
                for state,retail in RETAIL_REQUESTS.items():
                    g,capture=self.capture(widescreen=wide,mode=mode,visibility_state=state,game_seconds=258,
                        play_seconds=30,quarter=1,down=3,distance_yards=2,ball_yards=35,
                        identity=dict(away='MIN',home='NYJ'),possession='away',score_values=(999,999))
                    m=capture['machine']
                    try:
                        self.assertEqual(g['visibility_trace'][-1]['requests'],[1,1,*retail[2:]])
                        if geometry_reference is None:geometry_reference=(g['frame'],g['clock'],g['down'])
                        self.assertEqual((g['frame'],g['clock'],g['down']),geometry_reference)
                        self.assertIn('cscore_buga',g['objects']);self.assertIn('dscore_buga',g['objects'])
                        draws=projection.native_text_draw(capture);rows={d['callback']:d for d in draws['draws']}
                        self.assertEqual(rows['0xfc7d0']['text'],'3rd & 2')
                        self.assertEqual(rows['0xfc090']['text'],'1ST')
                        self.assertEqual(rows['0xfc100']['text'],'4:18')
                        self.assertEqual(rows['0xfbe30']['text'],'--' if state in ('live','after_play','fumble') else '30')
                        self.assertTrue(all(rows[k]['vertices'] for k in clocks))
                        self.assertEqual({d['font'] for d in rows.values()},{'font4','font8'})
                        self.assertEqual(projection.containment_failures({**g,**draws},g['frame'],.02),{})
                        for key in ('0xfbeb0','0xfbe60','0xfbe90','0xfbea0'):
                            if key in rows:
                                for clock in clocks:self.assertFalse(overlap(box(rows[key]),box(rows[clock])))
                                for score in ('0xfc050','0xfc070'):self.assertFalse(overlap(box(rows[key]),box(rows[score])))
                    finally:m.close()

    def test_transitions_do_not_close_center_and_clocks_are_read_again_each_draw(self):
        g,capture=self.capture(visibility_state='pre_snap',down=4,distance_yards=.01)
        m=capture['machine'];original_bindings=[m.get(0xa959c8+i*112+0x58) for i in range(6)]
        for state in ('live','after_play','pre_snap','kickoff','flag','fumble','pre_snap'):
            projection.configure_visibility(m,state)
            for frame in range(20):
                m.float(m.game_clock+16,300-frame)
                m.run(0xfce70,(0x3c888889,),limit=500000)
                self.assertEqual([m.get(0xa959c8+i*112+0x38) for i in (0,1)],[1,1])
                self.assertEqual([m.floats(0xa959c8+i*112+0x3c,1)[0] for i in (0,1)],[30.,30.])
                self.assertEqual([m.get(0xa959c8+i*112+0x58) for i in range(6)],original_bindings)
            rows={d['callback']:d for d in projection.native_text_draw(capture)['draws']}
            self.assertEqual(rows['0xfc100']['text'],'4:41')
            self.assertEqual(rows['0xfc7d0']['text'],'4th & Inches')
        m.put(0xe60294,0)
        dest=m.alloc(128);m.run(0xfbe30,ecx=dest)
        self.assertEqual(m.read_string(dest),'--')

    def test_retail_team_lookup_and_existing_callbacks_write_only_two_bound_materials(self):
        import unicorn
        g,capture=self.capture(visibility_state='pre_snap')
        m=capture['machine'];dest=m.alloc(128);base=m.get(m.get(0xa95528)+0x20)
        for (away,away_color),(home,home_color) in PAIRS:
            m.identity(away=away.lower(),home=home.lower())
            for side,callback,team,wanted,context in (('away',0xfc030,away,away_color,0xb30a58),
                                                      ('home',0xfc010,home,home_color,0xb30864)):
                m.run(0x68d70,ecx=context)
                self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_EAX),wanted)
                reads=[]
                hook=m.uc.hook_add(unicorn.UC_HOOK_MEM_READ,lambda _u,_a,at,n,_v,_d:reads.append((at,n)),
                                  begin=0x4e7fe0,end=0x4e889f)
                registers=dict(ebx=0x12345678,esi=0x23456789,edi=0x34567890,ebp=0x456789ab)
                try:m.run(callback,ecx=dest,**registers)
                finally:m.uc.hook_del(hook)
                self.assertIn(0x68d70,m.visits);self.assertTrue(reads)
                self.assertTrue(any((at-0x4e7fe0)%28==8 for at,n in reads))
                self.assertNotIn(0x449e0,m.visits)
                self.assertEqual(m.read_string(dest),team)
                target=base+128*v3.MATERIAL_INDICES[side]+24
                self.assertEqual(m.get(target),v3.contrast_color(wanted))
                for name,value in registers.items():
                    self.assertEqual(m.uc.reg_read(getattr(m.x,'UC_X86_REG_'+name.upper())),value)
                for at,n,value in m.writes:
                    self.assertTrue(m.STACK<=at and at+n<=m.STACK+0x10000 or
                                    dest<=at and at+n<=dest+128 or
                                    at in (target, base+128*v3.RIM_INDICES[side]+24) and n==4,(hex(at),n))
                # Callback copies/uppercases its output, never the roster string.
                self.assertEqual(m.read_string(m.get(context+0x13c)),team.lower())
                # The mesh precedes callbacks in FC360. Its tint must survive
                # the next native update to reach that following mesh draw.
                m.run(0xfce70,(0x3c888889,),limit=500000)
                self.assertEqual(m.get(target),v3.contrast_color(wanted))
        m.put(0xb30864+0x13c,0);m.run(0xfc010,ecx=dest)
        self.assertEqual(m.read_string(dest),'');self.assertEqual(m.get(base+6*128+24),0xff252625)

    def test_native_contrast_matches_rule_at_every_channel_value_and_boundary(self):
        g,capture=self.capture(visibility_state='pre_snap')
        m=capture['machine'];dest=m.alloc(128);base=m.get(m.get(0xa95528)+0x20)
        m.identity(home='ARI',home_code='00')
        original=m.get(0x4e7fe8)
        try:
            for shift in (0,8,16):
                for channel in range(256):
                    word=0xff000000 | channel<<shift
                    # Synthetic table value exercises the native contrast math;
                    # the independent pair test above uses untouched retail.
                    m.put(0x4e7fe8,word);m.run(0xfc010,ecx=dest)
                    self.assertEqual(m.get(base+6*128+24),v3.contrast_color(word))
            for word in (0xff707070,0xff717171,0xff7f7f7f,0xff808080,0xfffefefe,0xffffffff):
                m.put(0x4e7fe8,word);m.run(0xfc010,ecx=dest)
                self.assertEqual(m.get(base+6*128+24),v3.contrast_color(word))
        finally:m.put(0x4e7fe8,original)

    def test_native_material_draw_reads_callback_tint_and_emits_shader_constant(self):
        g,capture=self.capture(visibility_state='pre_snap',identity=dict(away='WAS',home='NYG'))
        m=capture['machine'];dest=m.alloc(128);base=m.get(m.get(0xa95528)+0x20)
        m.run(0xfc030,ecx=dest)
        material=base+128*v3.MATERIAL_INDICES['away']
        row=witness.material_submission(m,self.build.payload,material)
        color=v3.contrast_color(0xff86364a)
        self.assertEqual(row['argb'],hex(color))
        self.assertEqual(row['header'],['0x41ea4','0x6','0x100b80'])
        for got,shift in zip(row['rgba_half_scale'],(16,8,0,24)):
            self.assertAlmostEqual(got,((color>>shift)&255)/510,places=7)
        self.assertEqual(row['command_bytes'],28)
        self.assertEqual(row['unchanged_color_second_submission_bytes'],0)
        self.assertFalse(row['gpu_executed'])

    def test_v2_negative_control_reproduces_the_witness_and_retains_native_event_requests(self):
        with historical.historical('v2') as old:
            prior=scene.apply_xbe(self.build.payload)[0]
            for state,wanted in RETAIL_REQUESTS.items():
                case={**witness.CASES['min_nyj_pre_snap'],'visibility_state':state}
                g=witness.render(self.build,self.output/(state+'.png'),case,compiler=old,calibrated=False)
                self.assertEqual(g['visibility_trace'][-1]['requests'],wanted)
                self.assertEqual(g['resource_pins']['scene'],'6c3cad4eee9dc3aab4d4cc2ffba60dfdfc579c40fa6d60b18d013deab0529eea')
                if state=='live':self.assertNotIn('dscore_buga',g['objects']);self.assertNotIn('cscore_buga',g['objects'])
        self.assertEqual(scene.xbe_status(prior),'foreign')
        with self.assertRaises(ValueError):scene.apply_xbe(prior)

    def test_new_three_capture_calibration_and_v3_forecasts(self):
        from PIL import Image
        for name,case in witness.CASES.items():
            path=ROOT/'docs/scorebug_ingame/v3/witness'/case['file']
            if not path.is_file():self.skipTest('Noah disc-bf witness PNGs absent')
            self.assertEqual(scene.digest(path.read_bytes()),case['sha256'])
            with historical.historical('v2') as old:
                witness.render(self.build,self.output/'v2.png',case,compiler=old)
            with Image.open(path) as actual,Image.open(self.output/'v2.png') as predicted:
                rows=witness.measure(actual,predicted,case)
            for label,row in rows.items():
                self.assertIsNotNone(row['maximum_edge_error_px'],(name,label))
                self.assertLessEqual(row['maximum_edge_error_px'],1,(name,label,row))
            g=witness.render(self.build,self.output/'v3.png',case)
            self.assertIn('dscore_buga',g['objects']);self.assertIn('cscore_buga',g['objects'])
            self.assertFalse(g['scorebug_runtime_installed'])
            # Both material quads must cover their whole panels, including
            # the second disjoint triangle in the former home-side mark.
            with Image.open(self.output/'v3.png') as im:
                x,y=case['offset']
                for side,points in (('away',[(155,412),(155,449)]),('home',[(489,412),(489,449)])):
                    values=[im.getpixel((round(a*1.5+x),round(b*1.5+y))) for a,b in points]
                    self.assertEqual(values[0],values[1],(name,side,values))

    def test_full_new_spans_and_every_guard_refuse_mixed_bytes_before_mutation(self):
        patched=scene.apply_xbe(self.build.payload)[0]
        self.assertEqual(scene.apply_xbe(patched)[0],patched)
        for va,old,new,_ in v3.xbe_specs():
            offset=scene.layout.sbpos.va_to_off(patched,va)
            self.assertEqual(self.build.payload[offset:offset+len(old)],old)
            for data in (self.build.payload,patched):
                changed=bytearray(data);changed[offset+len(old)//2]^=0x40
                before=bytes(changed)
                self.assertEqual(scene.xbe_status(before),'foreign',hex(va))
                with self.assertRaises(ValueError):scene.apply_xbe(before)
                self.assertEqual(bytes(changed),before)
        for va,n,_sha,_label in v3.GUARDS:
            changed=bytearray(self.build.payload);changed[scene.layout.sbpos.va_to_off(changed,va)+n-1]^=0x40
            with self.assertRaises(ValueError):scene.apply_xbe(bytes(changed))


if __name__=='__main__':
    unittest.main()
