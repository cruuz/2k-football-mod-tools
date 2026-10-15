"""Fixed-span transport, refusal and Studio-equality checks for the offline N27 scorebar repair."""
from pathlib import Path
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b77 import hu1_repair as repair

PACK = ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'


class RepairTests(unittest.TestCase):
    def test_diff_plan_contains_only_changed_bytes(self):
        writes = list(repair.differences(b'abcdefghij', b'aBCdeFgHIj', 100))
        self.assertEqual(writes, [(101, b'bc', b'BC'), (105, b'f', b'F'), (107, b'hi', b'HI')])
        self.assertEqual(list(repair.differences(b'abc', b'abc', 0)), [])

    def test_overlay_scan_counts_scope_across_block_boundary(self):
        data = b'a'*(repair.BLOCK+10)
        off = repair.BLOCK-2
        new = b'BCDEFG'
        writes = [(off, data[off:off+6], new)]
        with tempfile.TemporaryFile() as stream:
            stream.write(data)
            stream.flush()
            image = repair.Image(stream.fileno(), len(data), writes)
            digest, changed, outside = repair.scan(image, [(off, 6, 'span')])
            self.assertEqual(digest, hashlib.sha256(data[:off]+new+data[off+6:]).hexdigest())
            self.assertEqual((changed, outside), (6, 0))
            self.assertEqual(repair.scan(image, [(off, 3, 'short span')])[2], 3)
            self.assertEqual(repair.io.pread(stream.fileno(), len(data), 0), data)

    def test_unknown_disc_refused_before_plan_or_write(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            disc, pins, receipt = folder/'disc', folder/'pins', folder/'receipt'
            disc.write_bytes(b'unknown')
            pins.write_text(json.dumps(dict(disc_size=7, inputs={'a': dict(label='x', after='b')})), newline='\n')
            with patch.object(repair, 'PINS', pins), patch.object(repair, 'plan') as planner:
                with self.assertRaisesRegex(ValueError, 'unknown disc hash'):
                    repair.run(disc, receipt, apply=True)
                planner.assert_not_called()
            self.assertEqual(disc.read_bytes(), b'unknown')
            self.assertFalse(receipt.exists())

    def test_apply_readback_and_zero_write_replay_on_synthetic_image(self):
        before, after = b'0123456789abcdef', b'012XY56789abZdef'
        writes = list(repair.differences(before, after, 0))
        spans = [(3, 2, 'TXTR a'), (12, 1, 'TXTR b')]
        pins = dict(disc_size=len(before), inputs={repair.sha(before): dict(label='synthetic', after=repair.sha(after))})
        planned = lambda image, _pins: ([] if image.read(len(after), 0) == after else writes, spans, 0, after, {'x': (0, len(after))})
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            disc, pinfile, receipt = folder/'synthetic', folder/'pins', folder/'receipt'
            disc.write_bytes(before)
            pinfile.write_text(json.dumps(pins), newline='\n')
            with patch.object(repair, 'PINS', pinfile), patch.object(repair, 'plan', side_effect=planned), \
                    contextlib.redirect_stdout(io.StringIO()):
                repair.run(disc, receipt, apply=True)
                first = json.loads(receipt.read_text())
                self.assertEqual((first['written_bytes'], first['bytes_outside_spans']), (3, 0))
                self.assertEqual(disc.read_bytes(), after)
                repair.run(disc, receipt, apply=True)
                self.assertEqual(json.loads(receipt.read_text())['written_bytes'], 0)
                self.assertEqual(disc.read_bytes(), after)

    def test_write_outside_declared_spans_is_refused(self):
        before, after = b'0123456789', b'01X3456789'
        pins = dict(disc_size=len(before), inputs={repair.sha(before): dict(label='synthetic', after=repair.sha(after))})
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            disc, pinfile, receipt = folder/'synthetic', folder/'pins', folder/'receipt'
            disc.write_bytes(before)
            pinfile.write_text(json.dumps(pins), newline='\n')
            planned = (list(repair.differences(before, after, 0)), [(5, 1, 'elsewhere')], 0, b'', {})
            with patch.object(repair, 'PINS', pinfile), patch.object(repair, 'plan', return_value=planned):
                with self.assertRaisesRegex(ValueError, 'outside declared spans'):
                    repair.run(disc, receipt, apply=True)
            self.assertEqual(disc.read_bytes(), before)

    def test_pins_cover_exactly_the_two_scorebar_textures(self):
        pins = json.loads(repair.PINS.read_text(encoding='utf-8'))
        self.assertEqual([r['name'] for r in pins['spans']], ['sb29h0', 'score_buga'])
        self.assertEqual(len(pins['inputs']), 2)
        self.assertTrue(all(r['before_sha256'] != r['after_sha256'] for r in pins['spans']))

    @unittest.skipUnless(PACK.is_file(), 'Pinned USA retail pack 0 required')
    def test_studio_compiler_reproduces_the_pinned_textures(self):
        from mod_editor.core import nfl2k5_scorebug_resources as art
        pins = json.loads(repair.PINS.read_text(encoding='utf-8'))
        fd = os.open(PACK, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
        try:
            data, offsets = repair.studio(art.PackView.from_fd(fd, 0, os.fstat(fd).st_size))
        finally:
            os.close(fd)
        self.assertEqual(len(data), pins['appendix_size'])
        for row in pins['spans']:
            off, size = offsets[row['name']]
            self.assertEqual((off, size), (row['appendix_offset'], row['size']))
            self.assertEqual(repair.sha(data[off:off+size]), row['after_sha256'], row['name'])


if __name__ == '__main__':
    unittest.main()
