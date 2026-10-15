"""Fixed-span fa1 transport must reject foreign inputs, preserve scope and replay with zero writes."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.b77 import fa1_repair as repair


class Transport(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.before=bytes(range(128))
        self.payloads=[b'ABCDEF',b'uvwxyz']
        self.spans=[];expected=bytearray(self.before)
        for at,payload in zip((12,98),self.payloads):
            self.spans.append(dict(offset=at,size=len(payload),before_sha256=repair.sha(self.before[at:at+len(payload)])))
            expected[at:at+len(payload)]=payload
        self.expected=bytes(expected)
        self.doc=dict(disc_size=len(self.before),before_sha256=repair.sha(self.before),
                      after_sha256=repair.sha(self.expected),spans=self.spans)
        self.disc=self.root/'synthetic.bin';self.disc.write_bytes(self.before)
        self.plan=self.root/'plan.json';self.receipt=self.root/'receipt.json'

    def test_write_and_zero_write_replay_are_exact(self):
        with patch.object(repair,'load_plan',return_value=(self.doc,self.payloads)):
            repair.apply(self.disc,self.plan,self.receipt)
            self.assertEqual(self.disc.read_bytes(),self.expected)
            self.assertEqual(json.loads(self.receipt.read_text())['bytes_written'],12)
            repair.apply(self.disc,self.plan,self.receipt)
            self.assertEqual(json.loads(self.receipt.read_text())['bytes_written'],0)
            self.assertEqual(self.disc.read_bytes(),self.expected)

    def test_unknown_input_refused_before_any_write(self):
        foreign=b'foreign'+self.before[7:];self.disc.write_bytes(foreign)
        with patch.object(repair,'load_plan',return_value=(self.doc,self.payloads)):
            with self.assertRaisesRegex(ValueError,'unrecognized input hash'):
                repair.apply(self.disc,self.plan,self.receipt)
        self.assertEqual(self.disc.read_bytes(),foreign)
        self.assertFalse(self.receipt.exists())

    def test_whole_stream_scope_detects_unowned_change(self):
        after=self.root/'after.bin';after.write_bytes(self.expected)
        with patch.object(repair,'load_plan',return_value=(self.doc,self.payloads)):
            repair.scope(self.disc,after,self.plan,self.receipt)
        result=json.loads(self.receipt.read_text())
        self.assertEqual(result['compared_bytes'],128)
        self.assertEqual(result['changed_bytes_outside_spans'],0)
        damaged=bytearray(self.expected);damaged[50]^=1;after.write_bytes(damaged)
        forged=dict(self.doc,after_sha256=repair.sha(damaged))
        with patch.object(repair,'load_plan',return_value=(forged,self.payloads)):
            with self.assertRaisesRegex(ValueError,'outside owned spans'):
                repair.scope(self.disc,after,self.plan,self.receipt)

    def test_plan_and_payload_must_match_frozen_pins(self):
        spans=[]
        for index,name in enumerate(repair.resource_names()):
            payload=bytes([index])*4;filename=f'{index}.prefix'
            (self.root/filename).write_bytes(payload)
            spans.append(dict(name=name,file=filename,offset=index*4,size=4,after_sha256=repair.sha(payload)))
        doc=dict(schema=repair.SCHEMA,before_sha256=repair.BASE_SHA,disc_size=4*len(spans),spans=spans)
        repair.save(self.plan,doc);pins=self.root/'pins.json';repair.save(pins,doc)
        with patch.object(repair,'PINS',pins):
            self.assertEqual(len(repair.load_plan(self.plan)[1]),17)
            (self.root/'0.prefix').write_bytes(b'BAD!')
            with self.assertRaisesRegex(ValueError,'payload pin mismatch'):repair.load_plan(self.plan)
            repair.save(self.plan,dict(doc,disc_size=4*len(spans)+1))
            with self.assertRaisesRegex(ValueError,'frozen fa1 pins'):repair.load_plan(self.plan)
            dropped=dict(doc,spans=spans[1:]);repair.save(self.plan,dropped);repair.save(pins,dropped)
            with self.assertRaisesRegex(ValueError,'foreign resource set'):repair.load_plan(self.plan)

    def test_resource_set_is_the_period_rows_and_every_metlife_field(self):
        names=repair.resource_names()
        self.assertEqual(names[:8],['a01ad.iff','a04dd.iff','a06dd.iff','a07dd.iff','a09dd.iff','a12dd.iff',
                                    'a36ad.iff','a48dd.iff'])
        self.assertEqual(sorted(names[8:]),sorted(f's18{t}{w}.iff' for t in 'dan' for w in 'drs'))


class TextureTransplant(unittest.TestCase):
    def test_only_owned_texture_bytes_change_before_fitting(self):
        decoded=bytes(range(256))*4
        rec=dict(system_bytes=16)
        rows={7:dict(pixel_offset=100,palette_offset=200,width=8,height=8,mip_levels=1)}
        with patch.object(repair.mv,'p8_rows',return_value=rows),\
             patch.object(repair.mv,'rows_by_material',return_value={'center_logo':7}):
            got=repair.texture_payloads(rec,decoded,('center_logo',))
        lo,hi,data,size=got['center_logo']
        self.assertEqual((lo,hi),(116,16+200+1024))
        self.assertEqual(data,decoded[116:1240])
        self.assertEqual(size,(8,8,1))


class NativeRefusal(unittest.TestCase):
    def test_candidate_refused_by_native_decoder_falls_to_the_next(self):
        import nfl_vc_lz_fill as fill
        from types import SimpleNamespace
        stored=64;header=bytearray(32);header[8]=10
        original=bytes(32)+bytes(header)+bytes(stored-32)+b'TAIL'
        chunk=SimpleNamespace(offset=0,end_offset=32+stored,stored_size=stored,overlap_scratch_bytes=16,index=0)
        tx=SimpleNamespace(compress_vc_lz=lambda data,stream_tag,offset_bits:(bytes([offset_bits])*8,None),
                           minimum_vc_lz_overlap_scratch=lambda *a:0,
                           parse_chunks=lambda data,allow_trailing:[chunk])
        seen=[]
        def verify(after,new):
            seen.append(after[32])
            if len(seen)==1:raise ValueError('reads one byte past the allocation')
        with patch.object(repair.mm,'_tools',return_value=(tx,)),\
             patch.object(fill,'fill_stream',side_effect=lambda enc,data,size,slack:(enc.ljust(size,b'\0'),)):
            after,scope,fitted,loan=repair.fit(original,chunk,b'edited',verify)
        self.assertEqual(seen,[10,9])
        self.assertEqual((fitted['offset_bits'],fitted['native_rejected'],loan),(9,1,None))
        self.assertEqual((after[32],after[-4:],scope),(9,b'TAIL',32+stored))


if __name__=='__main__':unittest.main()
