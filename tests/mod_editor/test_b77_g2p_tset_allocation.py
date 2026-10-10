"""Retail-free loader-allocation preservation for portable authored PNGs."""
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import nfl_tset_png_import as author
import nfl_txtr as txtr


def png_with_allocation(value, *, duplicate=False):
    png = txtr.encode_rgba_png(1, 1, b'\xff\xff\xff\xff')
    text = b'nfl2k5_tset_allocation\0' + json.dumps(dict(
        schema='nfl2k5_tset_allocation/v1', minimum_overlap_scratch_bytes=value)).encode()
    body = b'tEXt' + text
    chunk = struct.pack('>I', len(text)) + body + struct.pack('>I', zlib.crc32(body))
    return png[:-12] + chunk * (2 if duplicate else 1) + png[-12:]


class AllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decoded = bytes(range(256)) * 8
        compressed, _ = txtr.compress_vc_lz(cls.decoded, stream_tag=0, offset_bits=12)
        cls.stored = (len(compressed) + 255) // 16 * 16
        cls.span = txtr.HEADER.pack(b'TSET', cls.stored, 256, len(cls.decoded) - 256,
                                   txtr.COMPRESSED_SENTINEL, 0, 0, 0)
        cls.span += compressed + bytes(cls.stored - len(compressed))

    def test_larger_author_allocation_changes_only_header_and_still_decodes(self):
        original, _ = txtr.rebuild_compressed_chunk_fixed_span(self.span, self.decoded)
        result, info = author.rebuild_authored_tset_span(self.span, self.decoded, png_with_allocation(self.stored))
        self.assertEqual(result[:20], original[:20])
        self.assertEqual(result[24:], original[24:])
        self.assertEqual(struct.unpack_from('<I', result, 20)[0], self.stored)
        chunk = txtr.parse_chunks(result)[0]
        self.assertEqual(txtr.decode_chunk(result, chunk)[0], self.decoded)
        self.assertTrue(info.loader_in_place_alias_guard and info.loader_in_place_end_guard)
        self.assertEqual(info.original_overlap_scratch_bytes, 0)

    def test_missing_metadata_keeps_existing_bytes(self):
        png = txtr.encode_rgba_png(1, 1, b'\0\0\0\xff')
        self.assertEqual(author.rebuild_authored_tset_span(self.span, self.decoded, png),
                         txtr.rebuild_compressed_chunk_fixed_span(self.span, self.decoded))

    def test_smaller_requested_allocation_cannot_weaken_loader_minimum(self):
        result, info = author.rebuild_authored_tset_span(self.span, self.decoded, png_with_allocation(0))
        self.assertGreater(info.required_overlap_scratch_bytes, 0)
        self.assertGreaterEqual(txtr.HEADER.unpack_from(result)[5], info.required_overlap_scratch_bytes)

    def test_invalid_and_duplicate_metadata_refuses(self):
        for value in (True, -16, 1, '16', self.stored + 16):
            with self.subTest(value=value), self.assertRaises(author.ImportError):
                author.rebuild_authored_tset_span(self.span, self.decoded, png_with_allocation(value))
        with self.assertRaises(author.ImportError):
            author.rebuild_authored_tset_span(self.span, self.decoded, png_with_allocation(16, duplicate=True))


if __name__ == '__main__':
    unittest.main()
