"""fn1 repair: strict input pins, bounded writes, replay, and complete scope compare."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.b77 import fn1_repair as r


class RepairContract(unittest.TestCase):
    def fixture(self,folder):
        root=Path(folder);before=root/'before.iso';before.write_bytes(bytes(range(128))*8)
        after=bytearray(before.read_bytes());after[80:88]=b'fn1-test'
        span=dict(name='s11dd.iff',file='field.bin',offset=80,size=8,
                  before_sha256=r.sha(before.read_bytes()[80:88]),after_sha256=r.sha(after[80:88]))
        doc=dict(schema=r.SCHEMA,before_sha256=r.file_sha(before),after_sha256=r.sha(after),disc_size=1024,spans=[span])
        (root/'field.bin').write_bytes(after[80:88]);plan=root/'plan.json';r.save(plan,doc)
        return before,after,plan,doc

    def test_write_replay_and_full_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            before,after,plan,doc=self.fixture(folder);disc=Path(folder)/'copy.iso';disc.write_bytes(before.read_bytes())
            receipt=Path(folder)/'receipt.json'
            with patch.object(r,'PINS',plan),patch.object(r,'BASE_SHA',doc['before_sha256']),patch.object(r,'resource_names',return_value=['s11dd.iff']):
                r.apply(disc,plan,receipt);self.assertEqual(disc.read_bytes(),after)
                self.assertEqual(json.loads(receipt.read_text())['bytes_written'],8)
                r.apply(disc,plan,receipt);self.assertEqual(json.loads(receipt.read_text())['bytes_written'],0)
                r.scope(before,disc,plan,receipt)
                proof=json.loads(receipt.read_text())
                self.assertEqual(proof['compared_bytes'],1024)
                self.assertEqual(proof['changed_bytes_outside_spans'],0)

    def test_unknown_input_and_modified_payload_refuse_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            before,_after,plan,doc=self.fixture(folder);disc=Path(folder)/'copy.iso';disc.write_bytes(b'x'*1024)
            with patch.object(r,'PINS',plan),patch.object(r,'BASE_SHA',doc['before_sha256']),patch.object(r,'resource_names',return_value=['s11dd.iff']):
                with self.assertRaisesRegex(ValueError,'unrecognized input hash'):
                    r.apply(disc,plan,Path(folder)/'receipt.json')
                self.assertEqual(disc.read_bytes(),b'x'*1024)
                (Path(folder)/'field.bin').write_bytes(b'y'*8)
                with self.assertRaisesRegex(ValueError,'payload pin mismatch'):r.load_plan(plan)

    def test_payload_path_escape_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            _before,_after,plan,doc=self.fixture(folder);doc['spans'][0]['file']='../escape.bin';r.save(plan,doc)
            with patch.object(r,'PINS',plan),patch.object(r,'BASE_SHA',doc['before_sha256']),patch.object(r,'resource_names',return_value=['s11dd.iff']):
                with self.assertRaisesRegex(ValueError,'payload path escapes'):r.load_plan(plan)


if __name__=='__main__':unittest.main()
