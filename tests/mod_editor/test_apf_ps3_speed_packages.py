"""Generated full-shape package parity and content-cache invalidation gates."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import apf_logo_patch as writer
from apf_ps3_speed_benchmark import fixture
from mod_editor.apf_studio.ps3_texture_bundle import read_bundle


class PackageParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.index, zipped = fixture(cls.root, 1)
        cls.pixels = tuple(layer.image.tobytes() for layer in read_bundle(zipped).pairs[0].layers)
        writer._PACKAGE_CACHE.clear()
        cls.result = writer.build_crest_packages(cls.index, ((0, *cls.pixels, True),))[0]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_matches_pre_change_package_and_ladder(self):
        # Measured from the unmodified stack writer on the same generated DDSs,
        # IFF headers, 300,000-byte budget and preserved slack, before this edit.
        self.assertEqual(hashlib.sha256(self.result.entry_bytes).hexdigest(),
                         'bbc908620a16044bb90a15783ebf2d47183cbcb2591d2b6fccecc729c0287319')
        self.assertEqual(self.result.manifest['fit']['shades_per_region'], 4)
        self.assertTrue(self.result.manifest['validation']['rebuilt_iff_reparsed'])

    def test_unchanged_package_skips_compilation_and_receipt_mutation_is_isolated(self):
        with patch.object(writer, '_build_crest_job', side_effect=AssertionError('recompiled unchanged')):
            result = writer.build_crest_packages(self.index, ((0, *self.pixels, True),))[0]
            result.manifest['fit']['shades_per_region'] = 99
            again = writer.build_crest_packages(self.index, ((0, *self.pixels, True),))[0]
        self.assertEqual(again.manifest['fit']['shades_per_region'], 4)
        self.assertEqual(again.entry_bytes, self.result.entry_bytes)

    def test_source_bytes_are_reread_even_when_mtime_and_length_match(self):
        source, stat = self.index.read_bytes(), self.index.stat()
        try:
            self.index.write_bytes(source[:-1] + bytes([source[-1] ^ 1]))
            import os
            os.utime(self.index, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            with patch.object(writer, '_build_crest_job', side_effect=RuntimeError('source cache miss')):
                with self.assertRaisesRegex(RuntimeError, 'source cache miss'):
                    writer.build_crest_packages(self.index, ((0, *self.pixels, True),))
        finally:
            self.index.write_bytes(source)

    def test_each_mask_and_policy_invalidates_the_package(self):
        for layer in (0, 1):
            pixels = list(self.pixels)
            pixels[layer] = bytes([pixels[layer][0] ^ 17]) + pixels[layer][1:]
            with patch.object(writer, '_build_crest_job', side_effect=RuntimeError('pixel cache miss')):
                with self.assertRaisesRegex(RuntimeError, 'pixel cache miss'):
                    writer.build_crest_packages(self.index, ((0, *pixels, True),))
        with patch.object(writer, '_build_crest_job', side_effect=RuntimeError('policy cache miss')):
            with self.assertRaisesRegex(RuntimeError, 'policy cache miss'):
                writer.build_crest_packages(self.index, ((0, *self.pixels, False),))


if __name__ == '__main__':
    unittest.main()
