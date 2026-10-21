"""Fixed-span transport must reject foreign inputs, preserve scope and replay."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.b77 import fd1_repair as repair


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

    def test_virtual_output_equals_materialized_synthetic_output(self):
        result=repair.overlay_hash(self.disc,self.spans,self.payloads)
        self.assertEqual(result['after_sha256'],repair.sha(self.expected))
        self.assertEqual(result['changed_bytes'],sum(a!=b for a,b in zip(self.before,self.expected)))
        self.assertEqual(result['changed_bytes_outside_spans'],0)
        bad=[dict(self.spans[0],before_sha256='0'*64),self.spans[1]]
        with self.assertRaisesRegex(ValueError,'unrecognized input span'):
            repair.overlay_hash(self.disc,bad,self.payloads)

    def test_plan_and_payload_must_match_frozen_pins(self):
        spans=[]
        for index,number in enumerate(repair.ROWS):
            payload=bytes([index])*4;filename=f'{index}.prefix'
            (self.root/filename).write_bytes(payload)
            name=f"a{number-1:02d}{repair.fields.catalog()[number-1]['variant']}.iff"
            spans.append(dict(name=name,file=filename,offset=index*4,size=4,
                              after_sha256=repair.sha(payload)))
        doc=dict(schema=repair.SCHEMA,before_sha256=repair.BASE_SHA,disc_size=24,spans=spans)
        repair.save(self.plan,doc);pins=self.root/'pins.json';repair.save(pins,doc)
        with patch.object(repair,'PINS',pins):
            self.assertEqual(len(repair.load_plan(self.plan)[1]),6)
            (self.root/'0.prefix').write_bytes(b'BAD!')
            with self.assertRaisesRegex(ValueError,'payload pin mismatch'):repair.load_plan(self.plan)
            repair.save(self.plan,dict(doc,disc_size=25))
            with self.assertRaisesRegex(ValueError,'frozen fd1 pins'):repair.load_plan(self.plan)


if __name__=='__main__':unittest.main()
