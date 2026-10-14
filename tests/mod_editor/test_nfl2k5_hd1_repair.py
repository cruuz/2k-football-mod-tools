"""Fixed-span transport and refusal checks for the offline N26 repair."""
from pathlib import Path
import hashlib
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.b77 import hd1_repair as repair


class RepairTests(unittest.TestCase):
    def test_diff_plan_contains_only_changed_bytes(self):
        before=b'abcdefghij';after=b'aBCdeFgHIj'
        writes=list(repair.differences(before,after,100))
        self.assertEqual(writes,[(101,b'bc',b'BC'),(105,b'f',b'F'),(107,b'hi',b'HI')])
        self.assertEqual(list(repair.differences(after,after,100)),[])

    def test_scope_rejects_even_one_unowned_byte(self):
        self.assertEqual(repair.scope(b'abc',b'aBc',[(1,1,'x')])['bytes_outside_spans'],0)
        with self.assertRaisesRegex(ValueError,'outside'):
            repair.scope(b'abc',b'aBC',[(1,1,'x')])
        with self.assertRaisesRegex(ValueError,'size'):
            repair.scope(b'abc',b'abcd',[(0,4,'x')])

    def test_full_scan_overlay_and_preimage_cross_block_boundary(self):
        data=b'a'*(4*1024*1024+10)
        off=4*1024*1024-2;new=b'BCDEFG'
        writes=[(off,data[off:off+len(new)],new)]
        with tempfile.TemporaryFile() as stream:
            stream.write(data);stream.flush()
            got,count,_=repair.scan(stream.fileno(),len(data),writes)
            expected=data[:off]+new+data[off+len(new):]
            self.assertEqual(got,hashlib.sha256(expected).hexdigest())
            self.assertEqual(count,6)
            self.assertEqual(repair.io.pread(stream.fileno(),len(data),0),data)
            stream.seek(off);stream.write(new);stream.flush()
            self.assertEqual(repair.scan(stream.fileno(),len(data),writes,normalize=True)[0],hashlib.sha256(data).hexdigest())

    def test_unknown_executable_and_scene_refused(self):
        with self.assertRaisesRegex(ValueError,'unknown executable'):
            repair.repair_xbe(b'unknown',dict(xbe_before='a',xbe_after='b'))

    def test_unknown_disc_refused_before_plan_or_write(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);disc=folder/'disc';pins=folder/'pins';receipt=folder/'receipt'
            disc.write_bytes(b'unknown')
            pins.write_text(json.dumps(dict(disc_size=7,disc_before='a',disc_after='b')),newline='\n')
            with patch.object(repair,'PINS',pins),patch.object(repair,'plan') as planner:
                with self.assertRaisesRegex(ValueError,'unknown disc hash'):
                    repair.run(disc,receipt,apply=True)
                planner.assert_not_called()
            self.assertEqual(disc.read_bytes(),b'unknown')
            self.assertFalse(receipt.exists())

    def test_apply_readback_and_zero_write_replay_on_synthetic_image(self):
        import json
        import contextlib
        import io
        before=b'0123456789abcdef';after=b'012XY56789abZdef'
        writes=list(repair.differences(before,after,0))
        pins=dict(disc_size=len(before),disc_before=repair.sha(before),disc_after=repair.sha(after))
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);disc=folder/'synthetic';pinfile=folder/'pins';receipt=folder/'receipt'
            disc.write_bytes(before);pinfile.write_text(json.dumps(pins),newline='\n')
            with patch.object(repair,'PINS',pinfile),patch.object(repair,'plan',return_value=(writes,dict(replay_changed_bytes=0))) as planner,contextlib.redirect_stdout(io.StringIO()):
                repair.run(disc,receipt,apply=True)
                first=json.loads(receipt.read_text())
                self.assertEqual(first['written_bytes'],3)
                self.assertEqual(first['bytes_outside_spans'],0)
                self.assertEqual(disc.read_bytes(),after)
                repair.run(disc,receipt,apply=True)
                self.assertEqual(json.loads(receipt.read_text())['written_bytes'],0)
                self.assertEqual(planner.call_count,1)


if __name__=='__main__':
    unittest.main()
