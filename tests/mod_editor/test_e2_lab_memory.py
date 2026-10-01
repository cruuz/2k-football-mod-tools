"""Offline tests of E2's local GDB client and retained native book witnesses."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'e2'), str(ROOT / 'tests'), str(ROOT / 'tests/mod_editor'), str(ROOT / 'tools')]
import lab_memory as lab
from lab_verify import verify


class Client(unittest.TestCase):
    def test_eip_unknown_was_not_evidence_of_failed_memory_read(self):
        old = SimpleNamespace(returncode=0, stdout='0x00035988 in ?? ()\n0xe5ff80:\t0x00000008\n', stderr='')
        self.assertIsNone(lab.inspect_gdb(old)['eip'])
        new = SimpleNamespace(returncode=0, stdout='eip  0x35988  0x35988\n0xe5ff80:\t0x00000008\n',
                              stderr='warning: No executable has been specified\n')
        self.assertTrue(lab.inspect_gdb(new)['ok'])
        new.stderr = 'Cannot access memory at address 0x12345678\n'
        self.assertFalse(lab.inspect_gdb(new)['ok'])
        new.stderr, new.returncode = '', 1
        self.assertFalse(lab.inspect_gdb(new)['ok'])

    def test_client_requests_eip_retains_output_and_resumes_after_timeout(self):
        resumed = []
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'peek.log'
            done = SimpleNamespace(returncode=0, stdout='eip 0x1234\n0xe5ff80: 0x00000008\n', stderr='')
            with patch.object(lab.subprocess, 'run', return_value=done) as run:
                result = lab.run_gdb(1234, log, ['x/1wx 0xe5ff80'], resume=lambda: resumed.append(1))
                self.assertIn('info registers eip', run.call_args.args[0])
                self.assertEqual(result['eip'], 0x1234)
                self.assertEqual(log.read_text(), done.stdout)
            with patch.object(lab.subprocess, 'run', side_effect=subprocess.TimeoutExpired('gdb', 40, output=b'partial')):
                with self.assertRaises(RuntimeError):
                    lab.run_gdb(1234, log, resume=lambda: resumed.append(1))
                self.assertIn('partial', log.read_text())
                self.assertFalse(json.loads(log.with_suffix('.json').read_text())['ok'])
            self.assertEqual(resumed, [1, 1])

    def test_failed_capture_keeps_partial_evidence(self):
        def read(at, size):
            if at == 0xE5FF80:
                return struct.pack('<I', 8)
            raise ValueError('unmapped guest page')
        with tempfile.TemporaryDirectory() as directory:
            cat = Path(directory) / 'catalog.json'
            cat.write_text('{}')
            result = lab.capture(read, 0x1234, dict(directory=directory, phase='preview', catalog=str(cat)))
            self.assertFalse(result['ok'])
            self.assertEqual(len(result['ranges']), 1)
            self.assertTrue((Path(directory) / result['ranges'][0]['file']).exists())
            self.assertIn('unmapped', result['error'])


@unittest.skipUnless(Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso').is_file(), 'private source required')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_nfl2k5_stock_books import NativeStockBooks
        NativeStockBooks.setUpClass()
        cls.source = NativeStockBooks

    def test_ice_bowl_and_mixed_bound_payloads_verify_and_corruption_is_rejected(self):
        from test_nfl2k5_stock_books import MomentBooksCPU, BooksCPU
        source = self.source
        catalog = dict(venue_table=0x2700000, venues=['Lambeau Field'] * 50,
                       books={name: dict(body_size=len(raw) - 32,
                                         canonical_sha256=lab.sha(lab.canonical_play(raw[32:])))
                              for name, raw in source.books.items()})
        moments = MomentBooksCPU(source.payload, source.resources, source.context, source.ids, books=source.books,
            situ_chunk=source.collection[:32 + struct.unpack_from('<I', source.collection, 4)[0]], extra_files=source.files)
        moments.select(0)
        moments.stage()
        moments.load_books()
        moments.w(catalog['venue_table'], 0x2700100)
        moments.write(0x2700100, 'Lambeau Field\0'.encode('utf-16le'))
        mixed = BooksCPU(source.payload, source.resources, source.context, source.ids, books=source.books)
        mixed.team_select(mixed.last_resident(), mixed.team(1))
        for _ in range(6):
            mixed.press('home', 1)
        mixed.stage()
        self.assertEqual(mixed.load_books()[0], 'E2R-CHI-pb.iff')
        trace = []
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            cat = directory / 'catalog.json'
            cat.write_text(json.dumps(catalog))
            for case, cpu in (('original', moments), ('mixed', mixed)):
                run = directory / case
                for name in ('loaded', 'later'):
                    out = run / 'witnesses' / name
                    result = lab.capture(cpu.read, 0x35988, dict(directory=str(out), phase='books', catalog=str(cat)))
                    self.assertTrue(result['ok'], result.get('error'))
                if case == 'original':
                    preview = lab.capture(cpu.read, 0x35988, dict(directory=str(run / 'witnesses/preview'),
                                                               phase='preview', catalog=str(cat)))
                    self.assertTrue(preview['ok'], preview.get('error'))
                    (run / 'screens').mkdir()
                    (run / 'screens/named-preview.txt').write_text('THE ICE BOWL LAMBEAU FIELD')
                accepted = verify(run, case)
                self.assertTrue(accepted['memory_verified'])
                trace.append(dict(case=case, sides={side: dict(filename=b['filename'], pointer=b['pointer'],
                                           canonical_sha256=b['canonical_sha256'], matches=b['content_matches'])
                                           for side, b in result['books'].items()}))
                pointer = cpu.r(0xE5FE80)
                before = cpu.read(pointer + 0x50, 1)
                cpu.write(pointer + 0x50, bytes([before[0] ^ 1]))
                rejected = lab.capture(cpu.read, 0x35988, dict(directory=str(run / 'corrupt'), phase='books', catalog=str(cat)))
                self.assertFalse(rejected['ok'])
                self.assertIn('does not match', rejected['error'])
                cpu.write(pointer + 0x50, before)
                retained = next((run / 'witnesses/loaded').glob('*-home-PLAY.bin'))
                retained.unlink()
                with self.assertRaises(FileNotFoundError):
                    verify(run, case)
        if os.environ.get('E2P3_LAB_PROOF'):
            Path(os.environ['E2P3_LAB_PROOF']).write_text(json.dumps(dict(
                classification='PROVED OFFLINE', boundary='Native select, stage, decode and bind; GDB transport mocked. '
                'The ordinary current filename uses the retail fixture body; the stock alias uses the pinned one-pool body. '
                'Candidate E modern recipe contents are checked by the main-only catalog and lab.',
                cases=trace, changed_payload_rejected=True, missing_dump_rejected=True), indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
