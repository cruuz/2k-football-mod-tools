"""Generated full-shape package parity and content-cache invalidation gates."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import apf_logo_patch as writer
from apf_ps3_speed_benchmark import fixture, cache_fixture
from mod_editor.apf_studio.ps3_texture_bundle import (read_bundle, destination_slots,
    measure_bundle_logos, build_plan, stage_plan)


class PackageParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.index, cls.zipped = fixture(cls.root, 1)
        # Flat masks fit on the first greedy rung on every OS. The separate
        # benchmark and crest-fit suite exercise full-size shade ladders;
        # this integration gate stays fast without a native optimal helper.
        from test_apf_ps3_texture_bundle import bundle_files
        with zipfile.ZipFile(cls.zipped, 'w') as archive:
            for name, data in bundle_files(hash_value=zlib.crc32(b'UNIFORM_LOGO_00.IFF')).items():
                archive.writestr(name, data)
        cls.pixels = tuple(layer.image.tobytes() for layer in read_bundle(cls.zipped).pairs[0].layers)
        writer._PACKAGE_CACHE.clear()
        cls.result = writer.build_crest_packages(cls.index, ((0, *cls.pixels, True),))[0]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_matches_pre_change_package_and_ladder(self):
        # Measured from the unmodified stack writer on the same generated DDSs,
        # IFF headers, 300,000-byte budget and preserved slack, before this edit.
        self.assertEqual(hashlib.sha256(self.result.entry_bytes).hexdigest(),
                         '588d4a528a4a42fa207ba900d004f45ad5c067d9561d4a8ab423a2fce166eaeb')
        self.assertEqual(self.result.manifest['fit']['shades_per_region'], 16)
        self.assertTrue(self.result.manifest['validation']['rebuilt_iff_reparsed'])

    def test_real_session_staging_and_studio_compile_keep_package_and_cache_coupled(self):
        from unittest.mock import Mock
        from mod_editor.apf_studio.models import ApfSource
        from mod_editor.apf_studio.session import ApfSession
        from mod_editor.apf_studio.build import ApfBuildService
        import apf_logocache_patch as cache
        source = ApfSource(self.root, self.root, self.index, 'a' * 64, self.index.stat().st_size,
                           'b' * 64, 'generated texture-only archive')
        session = ApfSession(source, Mock(), cache_root=self.root / 'session-cache')
        original_sha = hashlib.sha256(self.index.read_bytes()).hexdigest()
        try:
            bundle = read_bundle(self.zipped)
            slots = destination_slots(self.index)
            sizes = measure_bundle_logos(bundle, slots, self.index)
            plan = build_plan(bundle, slots, measurements=sizes)
            stage_plan(session, plan)
            self.assertEqual(len(session.modifications), 1)
            directory, payload = cache_fixture()
            with patch.object(cache, '_read_pair', return_value=(None, None, None, directory, payload)):
                entries, row = ApfBuildService(source)._compile_helmet_crests(session.modifications)
            self.assertEqual(entries[0], self.result.entry_bytes)
            self.assertEqual(set(entries), {0, 171, 213})
            self.assertEqual(row['component_receipts'][0]['fit']['shades_per_region'], 16)
            self.assertTrue(row['cache_receipt']['validation']['directory_reparsed'])
            self.assertEqual(hashlib.sha256(self.index.read_bytes()).hexdigest(), original_sha)
        finally:
            session.close()

    def test_unchanged_package_skips_compilation_and_receipt_mutation_is_isolated(self):
        with patch.object(writer, '_build_crest_job', side_effect=AssertionError('recompiled unchanged')):
            result = writer.build_crest_packages(self.index, ((0, *self.pixels, True),))[0]
            result.manifest['fit']['shades_per_region'] = 99
            again = writer.build_crest_packages(self.index, ((0, *self.pixels, True),))[0]
        self.assertEqual(again.manifest['fit']['shades_per_region'], 16)
        self.assertEqual(again.entry_bytes, self.result.entry_bytes)

    def test_full_size_package_with_forced_python_matches_original_bytes(self):
        import apf_field_art_patch as field
        writer._STREAM_CACHE.clear()
        with patch.object(field, '_optimal_binary', return_value=None):
            portable = writer.build_patch_rgba(self.index, *self.pixels, entry_index=0,
                                               allow_simplification=True)
        self.assertEqual(portable.entry_bytes, self.result.entry_bytes)

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
