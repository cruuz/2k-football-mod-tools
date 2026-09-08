"""Bounded decode reuse must retain strict PNG and external-change checks."""
from pathlib import Path
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core.nfl2k5_asset_io import (
    Nfl2k5AssetIO, _ReplacementDecodeCache, _replacement_decode_cache, png_codec,
)
from mod_editor.core.errors import ValidationError
from nfl_txtr import encode_rgba_png


class VisualDecodeCacheTests(unittest.TestCase):
    def setUp(self):
        _replacement_decode_cache.clear()
        self.addCleanup(_replacement_decode_cache.clear)

    def test_same_bytes_reuse_strict_decode_but_dimensions_and_crc_still_refuse(self):
        cache = _ReplacementDecodeCache()
        png = encode_rgba_png(4, 4, bytes((1, 2, 3, 255)) * 16)
        with patch.object(png_codec, "decode_rgba_png", wraps=png_codec.decode_rgba_png) as decode:
            first = cache.decode(png, (4, 4))
            self.assertIs(cache.decode(png, (4, 4)), first)
            self.assertEqual(decode.call_count, 1)
            with self.assertRaises(ValueError): cache.decode(png, (8, 8))
            broken = bytearray(png)
            broken[-5] ^= 1
            with self.assertRaises(ValueError): cache.decode(bytes(broken), (4, 4))
            self.assertEqual(decode.call_count, 3)

    def test_byte_budget_and_entry_limit_evict_and_oversize_is_not_retained(self):
        cache = _ReplacementDecodeCache(max_bytes=128, max_entries=2)
        for number in range(5):
            cache.decode(encode_rgba_png(4, 4, bytes((number, 0, 0, 255)) * 16), (4, 4))
            self.assertLessEqual(cache._size, 128)
            self.assertLessEqual(len(cache._rows), 2)
        large = encode_rgba_png(8, 8, bytes((0, 0, 0, 255)) * 64)
        cache.decode(large, (8, 8))
        self.assertEqual(cache._size, 128)
        cache.clear()
        self.assertEqual(cache._size, 0)
        self.assertFalse(cache._rows)

    def test_same_path_size_and_mtime_do_not_hide_changed_pixels(self):
        asset = SimpleNamespace(label="Digit 0", width=4, height=4)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "digit.png"
            first = encode_rgba_png(4, 4, bytes((1, 2, 3, 255)) * 16)
            second = encode_rgba_png(4, 4, bytes((3, 2, 1, 255)) * 16)
            self.assertEqual(len(first), len(second))
            path.write_bytes(first)
            timestamp = path.stat()
            before = Nfl2k5AssetIO.validate_replacement(asset, path)
            path.write_bytes(second)
            os.utime(path, ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns))
            after = Nfl2k5AssetIO.validate_replacement(asset, path)
            self.assertNotEqual(before[1], after[1])
            path.write_bytes(b"broken PNG")
            with self.assertRaises(ValidationError): Nfl2k5AssetIO.validate_replacement(asset, path)


if __name__ == "__main__":
    unittest.main()
