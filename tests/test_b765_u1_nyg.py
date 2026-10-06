"""Bounded opt-in native helmet mip artwork; ordinary imports stay unchanged."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from PIL import Image, PngImagePlugin
import nfl_live_helmet_txtr_png_import as helmet


def sha(data):
    return hashlib.sha256(data).hexdigest()


class AuthoredHelmetMipsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = bytes((11, 34, 101, 255)) * (256 * 256)
        cls.tail = b''.join(bytes((n * 20, 50, 90, 255)) * (w * h)
                            for n, (w, h) in enumerate(helmet.MIP_DIMENSIONS[1:], 1))
        cls.record = {'schema': 'nfl2k5_palette_lock/v1', 'rgba': [[11, 34, 101, 255]],
                      'helmet_mips': {'schema': 'nfl2k5_helmet_mips/v1',
                                      'base_rgba_sha256': sha(cls.base),
                                      'tail_sha256': sha(cls.tail),
                                      'tail_zlib': base64.b64encode(zlib.compress(cls.tail)).decode()}}

    def png(self, record=None, duplicate=False):
        info = PngImagePlugin.PngInfo()
        if record is not None:
            info.add_text('nfl2k5_palette_lock', json.dumps(record))
            if duplicate:
                info.add_text('nfl2k5_palette_lock', json.dumps(record))
        stream = io.BytesIO()
        Image.frombytes('RGBA', (256, 256), self.base).save(stream, format='PNG', pnginfo=info)
        return stream.getvalue()

    def test_ordinary_png_retains_original_filter_and_no_reservations(self):
        levels, locked = helmet.prepared_mips(self.png(), self.base)
        self.assertEqual(levels, helmet.generate_mips(self.base))
        self.assertEqual(locked, [])

    def test_authored_tail_exact_dimensions_pixels_and_colour_lock(self):
        levels, locked = helmet.prepared_mips(self.png(self.record), self.base)
        self.assertEqual(tuple((m.width, m.height) for m in levels), helmet.MIP_DIMENSIONS)
        self.assertEqual(levels[0].rgba, self.base)
        self.assertEqual(b''.join(m.rgba for m in levels[1:]), self.tail)
        self.assertEqual(locked, [(11, 34, 101, 255)])

    def test_visible_base_hash_and_size_are_required(self):
        with self.assertRaises(ValueError):
            helmet.prepared_mips(self.png(self.record), bytes((0,)) * len(self.base))
        with self.assertRaises(ValueError):
            helmet.prepared_mips(self.png(self.record), self.base[:-4])

    def test_tail_hash_must_match(self):
        record = copy.deepcopy(self.record)
        record['helmet_mips']['tail_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            helmet.prepared_mips(self.png(record), self.base)

    def test_truncated_trailing_and_expansion_overflow_refuse(self):
        compressed = zlib.compress(self.tail)
        for data in (compressed[:-1], compressed + b'foreign', zlib.compress(self.tail * 2)):
            with self.subTest(size=len(data)):
                record = copy.deepcopy(self.record)
                record['helmet_mips']['tail_zlib'] = base64.b64encode(data).decode()
                with self.assertRaises(ValueError):
                    helmet.prepared_mips(self.png(record), self.base)

    def test_invalid_compression_and_base64_refuse(self):
        for value in ('not_base64', base64.b64encode(b'not_zlib').decode()):
            record = copy.deepcopy(self.record)
            record['helmet_mips']['tail_zlib'] = value
            with self.assertRaises(ValueError):
                helmet.prepared_mips(self.png(record), self.base)

    def test_duplicate_record_and_wrong_class_refuse(self):
        with self.assertRaises(ValueError):
            helmet.prepared_mips(self.png(self.record, duplicate=True), self.base)
        record = copy.deepcopy(self.record)
        record['preserve_mips'] = {}
        with self.assertRaises(ValueError):
            helmet.prepared_mips(self.png(record), self.base)
        record = copy.deepcopy(self.record)
        record['helmet_mips']['schema'] = 'different_dimensions/v1'
        with self.assertRaises(ValueError):
            helmet.prepared_mips(self.png(record), self.base)
        record['helmet_mips'] = None
        with self.assertRaises(ValueError):
            helmet.prepared_mips(self.png(record), self.base)

    def test_palette_only_reservation_keeps_box_filter(self):
        record = {k: v for k, v in self.record.items() if k != 'helmet_mips'}
        levels, locked = helmet.prepared_mips(self.png(record), self.base)
        self.assertEqual(levels, helmet.generate_mips(self.base))
        self.assertEqual(locked, [(11, 34, 101, 255)])


if __name__ == '__main__':
    unittest.main()
