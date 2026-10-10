"""Small native FRZ fixture tests. Disc fixtures are optional and read only."""
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT),str(ROOT/'tools'),str(ROOT/'tools/b77')]
import frz_bisect as bisect
import frz_transition as transition
from nfl_txtr import HEADER, compress_vc_lz, minimum_vc_lz_overlap_scratch, parse_chunks

FIXTURE = Path(os.environ.get('B77_FRZ_FIXTURES','/home/noah/2k-worktrees/.b77-scratch/frz'))
HAVE_NATIVE = importlib.util.find_spec('unicorn') is not None and (FIXTURE/'v06/default.xbe').is_file()


class DiscRepairTests(unittest.TestCase):
    def test_stream_copy_preserves_offsets_and_surrounding_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            source,target = Path(folder)/'source',Path(folder)/'target'
            payload = b'ab\r\n\x1a\xff'  # Windows text mode must not translate binary disc bytes.
            source.write_bytes(b'HEAD'+payload+b'TAIL')
            target.write_bytes(b'x'*20)
            binary = getattr(os, 'O_BINARY', 0)
            a,b = os.open(source,os.O_RDONLY | binary),os.open(target,os.O_RDWR | binary)
            try:
                digest = bisect.stream_write(a,b,4,7,6)
            finally:
                os.close(a)
                os.close(b)
            self.assertEqual(digest,bisect.sha(payload))
            self.assertEqual(target.read_bytes(),b'x'*7+payload+b'x'*7)
            self.assertEqual(source.read_bytes(),b'HEAD'+payload+b'TAIL')

    def test_short_source_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            source,target = Path(folder)/'source',Path(folder)/'target'
            source.write_bytes(b'abc')
            target.write_bytes(b'x'*20)
            binary = getattr(os, 'O_BINARY', 0)
            a,b = os.open(source,os.O_RDONLY | binary),os.open(target,os.O_RDWR | binary)
            try:
                with self.assertRaisesRegex(ValueError,'short source read'):
                    bisect.stream_write(a,b,0,0,20)
            finally:
                os.close(a)
                os.close(b)


@unittest.skipUnless(HAVE_NATIVE,'optional extracted final executable and Unicorn required')
class NativeTests(unittest.TestCase):
    def test_final_decoder_honors_real_in_place_geometry_and_guards(self):
        machine = transition.TextureMachine((FIXTURE/'v06/default.xbe').read_bytes())
        decoded = bytes(range(256))*8+b'A'*3000
        for bits in (10,11,12):
            with self.subTest(bits=bits):
                stream,_ = compress_vc_lz(decoded,offset_bits=bits)
                stored = len(stream)+64
                scratch = max(64,minimum_vc_lz_overlap_scratch(stream,stored,len(decoded)))
                span = HEADER.pack(b'TSET',stored,256,len(decoded)-256,0xFEEDBEEF,scratch,0,0)+stream+bytes(64)
                machine.check(span,parse_chunks(span)[0],decoded)

    def test_final_decoder_probe_detects_wrong_decoded_output(self):
        machine = transition.TextureMachine((FIXTURE/'v06/default.xbe').read_bytes())
        decoded = bytes(range(256))*8+b'A'*3000
        stream,_ = compress_vc_lz(decoded,offset_bits=12)
        stored = len(stream)+64
        scratch = max(64,minimum_vc_lz_overlap_scratch(stream,stored,len(decoded)))
        span = HEADER.pack(b'TSET',stored,256,len(decoded)-256,0xFEEDBEEF,scratch,0,0)+stream+bytes(64)
        wrong = bytes([decoded[0]^1])+decoded[1:]
        with self.assertRaisesRegex(ValueError,'native in-place output differs'):
            machine.check(span,parse_chunks(span)[0],wrong)

    def test_shipped_commentary_rollback_changes_only_the_c2_byte(self):
        c2 = transition.c2
        tables = []
        for label in ('v05','v06'):
            raw = (FIXTURE/label/'entry3.bin').read_bytes()
            at = c2.find_table(raw)
            tables.append(raw[at:at+c2.SPCI_SIZE])
        before,after = tables
        self.assertEqual(c2.patch_table(before)[0],after)
        self.assertEqual([i for i,(a,b) in enumerate(zip(before,after)) if a != b],[c2.EXPECTED_ID_OFFSET])
        self.assertEqual((before[c2.EXPECTED_ID_OFFSET],after[c2.EXPECTED_ID_OFFSET]),(0x8c,0xef))


if __name__ == '__main__':
    unittest.main()
