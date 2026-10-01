"""SB3: execute shipped native timeout code and read back its actual UV writes.

--report DIR saves native projection rasters, exact pins and lab transition rows.
No emulator, disc build or GPU execution.
"""
from pathlib import Path
import itertools
import json
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(Path(__file__).parent)]
import test_nfl2k5_scorebar_v3 as v3_tests
HAVE_IMAGES = v3_tests.HAVE_IMAGES
from test_nfl2k5_scorebug_runtime import XBE, PACK, HAVE_UC
from mod_editor.core import nfl2k5_scorebar_v3 as bar
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_resources as art
import nfl2k5_scorebug_projection as projection


def uv_bytes(m):
    body = m.get(0xa95528)-256
    return bytes(m.uc.mem_read(body+scene.layout.S1+274*10, 120))


def rows(m):
    data = uv_bytes(m)
    return [list(struct.unpack_from('<6xhh', data, offset)[0] for offset in range(side*60, side*60+60, 10))
            for side in (0,1)]


def expected(count):
    count = count if 0 <= count <= 3 else 0
    return [-25600+count*4096, -25600+count*4096, -28672+count*4096,
            -28672+count*4096, -25600+count*4096, -28672+count*4096]


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC and HAVE_IMAGES,
                     'pinned USA resources, Unicorn, Pillow and numpy required')
class Timeouts(unittest.TestCase):
    setUpClass = classmethod(v3_tests.NativeV3Tests.setUpClass.__func__)
    capture = v3_tests.NativeV3Tests.capture

    def test_all_sixteen_pairs_in_both_modes_and_aspects_use_native_frame_call(self):
        for wide, mode in itertools.product((False,True),(0,1)):
            g, cap = self.capture(widescreen=wide,mode=mode,visibility_state='pre_snap')
            m = cap['machine']
            initial = uv_bytes(m)
            body = m.get(0xa95528)-256
            allowed = {body+scene.layout.S1+v*10+7 for v in range(274,286)}
            for home, away in itertools.product(range(4),repeat=2):
                m.put(m.home+4,home); m.put(m.away+4,away)
                m.run(0xfce70,(0x3c888889,),limit=500000)
                self.assertIn(bar.TIMEOUT_VA,m.visits)
                self.assertEqual(rows(m),[expected(home),expected(away)])
                current = uv_bytes(m)
                self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(initial,current)) if i%10!=7))
                # Direct helper ABI and exact write boundary, independently of the frame driver.
                registers = dict(eax=1,ebx=2,ecx=3,edx=4,esi=5,edi=6,ebp=7)
                m.run(bar.TIMEOUT_VA,**registers)
                for name,value in registers.items():
                    self.assertEqual(m.uc.reg_read(getattr(m.x,'UC_X86_REG_'+name.upper())),value)
                self.assertTrue(all(m.STACK<=at and at+n<=m.STACK+0x10000 or at in allowed and n==1
                                    for at,n,_ in m.writes))
            m.close()

    def test_each_team_decrements_half_reset_null_invalid_and_rebound_objects(self):
        _,cap=self.capture(visibility_state='pre_snap')
        m=cap['machine']
        for home,away,phase in ((3,3,4),(2,3,4),(2,2,4),(1,2,4),(0,1,4),(3,3,0),(3,3,4),
                               (4,2,4),(0xffffffff,1,4),(1,4,4),(2,0xffffffff,4)):
            m.put(m.home+4,home);m.put(m.away+4,away);m.put(0xe602b4,phase)
            m.run(0xfce70,(0,),limit=500000)
            self.assertEqual(rows(m),[expected(home),expected(away)])
        for pointer,other in ((0xe5fc28,1),(0xe5fc68,0)):
            old=m.get(pointer);m.put(pointer,0)
            m.run(bar.TIMEOUT_VA)
            self.assertEqual(rows(m)[1-other],expected(0))
            replacement=m.alloc(8);m.put(replacement+4,3);m.put(pointer,replacement)
            m.run(bar.TIMEOUT_VA)
            self.assertEqual(rows(m)[1-other],expected(3))
            m.put(pointer,old)

    def test_missing_foreign_and_replaced_scenes_never_use_cached_stream_pointers(self):
        _,cap=self.capture(visibility_state='pre_snap')
        m=cap['machine'];instance=m.get(0xa95528);body=instance-256
        for marker,pointer in ((bar.TIMEOUT_MAGIC,0),(0,instance),(0x35525053,instance)):
            m.put(body+0x60,marker);m.put(0xa95528,pointer);m.run(bar.TIMEOUT_VA)
            self.assertTrue(all(m.STACK<=at and at+n<=m.STACK+0x10000 for at,n,_ in m.writes))
        m.put(body+0x60,bar.TIMEOUT_MAGIC);m.put(0xa95528,instance)
        old=bytes(m.uc.mem_read(body,len(self.decoded)))
        replacement=m.alloc(len(old));m.uc.mem_write(replacement,old);m.put(0xa95528,replacement+256)
        m.put(m.home+4,0);m.put(m.away+4,1);m.run(bar.TIMEOUT_VA)
        self.assertEqual(rows(m),[expected(0),expected(1)])
        self.assertEqual(bytes(m.uc.mem_read(body,len(old))),old)

    def test_scores_and_quarters_keep_native_values_after_span_compaction(self):
        _,cap=self.capture(visibility_state='pre_snap')
        m=cap['machine'];dest=m.alloc(128)
        for value in (0,1,9,10,99,100,999):
            m.put(m.home,value);m.put(m.away,999-value)
            for callback,wanted in ((0xfc050,str(value)),(0xfc070,str(999-value))):
                m.run(callback,ecx=dest);self.assertEqual(m.read_string(dest),wanted)
        for period,wanted in ((1,'1ST'),(2,'2ND'),(3,'3RD'),(4,'4TH'),(5,'OT1'),(6,'OT2')):
            m.put(0xe602c4,period);m.run(0xfc090,ecx=dest);self.assertEqual(m.read_string(dest),wanted)

    def test_fixed_spans_native_decompression_replay_and_foreign_refusal(self):
        receipt=projection.static_receipts(self.build.payload,self.build.spans)
        self.assertTrue(receipt['native_refit_verified'])
        for name,data in (('score_bug',self.span),('score_buga',self.atlas)):
            bad=bytearray(data);bad[-30]^=1
            self.assertEqual(scene.status(bytes(bad),name),'foreign')
            with self.assertRaises(ValueError):scene.apply(bytes(bad),name)
            self.assertEqual(len(data),art.RESOURCES[name]['span_size'])


def report(directory):
    from PIL import Image, ImageDraw
    from nfl2k5_scorebug_exact import Build
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    build=Build(PACK,XBE)
    try:
        span=scene.apply(build.spans['score_bug'],'score_bug')[0];decoded=scene.decode(span)[1]
        atlas=scene.apply(build.spans['score_buga'],'score_buga')[0]
        receipts=projection.static_receipts(build.payload,build.spans)
        states=[]
        sheet=Image.new('RGB',(1280,4*140),(25,27,31));draw=ImageDraw.Draw(sheet)
        # Both independent sides show 3/2/1/0 against a constant opponent.
        for side in ('home','away'):
            for count in (3,2,1,0):
                counts=(count,3) if side=='home' else (3,count)
                cap={};g=projection.native_geometry(build.payload,decoded,fonts=build.fonts,texture_span=atlas,
                    capture=cap,visibility_state='pre_snap',timeouts=counts,identity=dict(away='MIN',home='NYJ'))
                m=cap['machine']
                try:
                    g.update(projection.native_text_draw(cap))
                    name=f'{side}-{count}.png';path=directory/name
                    projection.render_native(cap['live_decoded'],atlas,build.fonts,g,path,texture_spans=cap['texture_spans'])
                    states.append(dict(side=side,remaining=list(counts),used=[3-v for v in counts],
                        uv_rows=rows(m),image=name,sha256=scene.digest(path.read_bytes()),
                        evidence='PROVED OFFLINE: native update and stream read-back, software GPU model'))
                    with Image.open(path) as im:
                        crop=im.crop((0,385,640,480)).convert('RGB')
                        x=0 if side=='home' else 640;y=(3-count)*140
                        sheet.paste(crop,(x,y+35));draw.text((x+16,y+12),f'{side.upper()} remaining {count}, used {3-count}; opponent 3',fill='white')
                finally:m.close()
        sheet.save(directory/'timeouts-contact-sheet.png')
        (directory/'proof.json').write_text(json.dumps(dict(evidence='PROVED OFFLINE',states=states,
            receipts=receipts,limitations=['No played-game witness','GPU rasterization modeled']),indent=2)+'\n')
    finally:build.close()


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--report':report(sys.argv[2])
    else:unittest.main()
