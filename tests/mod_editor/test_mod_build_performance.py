"""One private copy, byte-equivalent composition and refusal before project work."""
from __future__ import annotations
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from mod_editor.core import mod_build, build_io
from mod_editor.core.nfl2k5_build_service import BuildResult
from nfl2k5_edge_rename_test import build_edge_synthetic_xbe
from nfl2k5_commentary_swap_test import _dir_node


def synthetic_disc(path):
    xbe = build_edge_synthetic_xbe()
    size = mod_build.tt.EXPECTED_XBE_SIZE
    assert len(xbe) <= size
    xbe += bytes(size - len(xbe))
    directory = _dir_node([(64, size, 0x80, 'default.xbe')])
    image = bytearray(64 * 2048 + size + 40 * 4096)
    magic = b'MICROSOFT*XBOX*MEDIA'
    image[0x10000:0x10014] = magic
    struct.pack_into('<II', image, 0x10014, 33, len(directory))
    image[0x107ec:0x10800] = magic
    image[33*2048:33*2048+len(directory)] = directory
    image[64*2048:64*2048+size] = xbe
    path.write_bytes(image)


class SyntheticProject:
    """Forty disjoint synthetic texture spans with independent read-back."""
    def __init__(self, source):
        self.source, self.calls = source, 0

    def build(self, cache, session, output, progress=None):
        self.calls += 1
        before = self.source.read_bytes()
        build_io.copy_image(self.source, output)
        with output.open('r+b') as stream:
            for i in range(40):
                stream.seek(len(before) - (40 - i) * 4096)
                stream.write(bytes([i + 1]) * 4096)
        after = output.read_bytes()
        for i in range(40):
            self_start = len(before) - (40 - i) * 4096
            assert after[self_start:self_start+4096] == bytes([i+1])*4096
        return BuildResult(output, len(after), hashlib.sha256(after).hexdigest(), 40, 40*4096,
                           source_sha256=hashlib.sha256(before).hexdigest())


class CombinedBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'retail.iso'
        synthetic_disc(self.source)
        self.original = self.source.read_bytes()
        self.service = SyntheticProject(self.source)

    def test_single_copy_matches_historical_two_copy_composition(self):
        staged = self.root / 'old-stage.iso'
        old_target, new_target = self.root / 'old.iso', self.root / 'source.iso'
        self.service.build(None, None, staged)
        plan = mod_build.BuildPlan(str(staged), str(old_target), throw=True, max_deep_yards=80,
                                   catch_slider=True, accel_ramp=True, draft_ai=True, returner_fix=True)
        mod_build.build(plan)
        with mock.patch.object(build_io, 'copy_descriptors', wraps=build_io.copy_descriptors) as copies:
            receipt = mod_build.build_with_project(replace(plan, source=str(self.source), target=str(new_target)),
                                                   self.service, None, None)
        self.assertEqual(copies.call_count, 1)
        self.assertEqual(old_target.read_bytes(), new_target.read_bytes())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(receipt['outcome']['source']['sha256'], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(receipt['outcome']['output']['sha256'], hashlib.sha256(new_target.read_bytes()).hexdigest())
        self.assertEqual(receipt['steps'][0]['step'], 'shared_project')
        self.assertFalse(list(self.root.glob('.studio-build-*')))

    def test_plain_project_composition_also_consumes_one_copy(self):
        target = self.root / 'project.iso'
        plan = mod_build.BuildPlan(str(self.source), str(target))
        with mock.patch.object(build_io, 'copy_descriptors', wraps=build_io.copy_descriptors) as copies:
            mod_build.build_with_project(plan, self.service, None, None)
        self.assertEqual(copies.call_count, 1)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_conflicting_plan_refuses_before_project_builder(self):
        target = self.root / 'refused.iso'
        plan = mod_build.BuildPlan(str(self.source), str(target), playbook_pair=True, qb_spy=True)
        with self.assertRaisesRegex(ValueError, 'Separate playbooks'):
            mod_build.build_with_project(plan, self.service, None, None)
        self.assertEqual(self.service.calls, 0)
        self.assertFalse(target.exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_configuration_and_document_refusals_precede_project_preparation(self):
        for options, expected in (({'throw': True, 'max_deep_yards': 999}, 'max deep'),
                                  ({'career_stats': str(self.root / 'missing.csv')}, None),
                                  ({'roster_edits': str(self.root / 'missing.json')}, None)):
            with self.subTest(options=options):
                target = self.root / 'refused.iso'
                plan = mod_build.BuildPlan(str(self.source), str(target), **options)
                with self.assertRaises((ValueError, OSError)):
                    mod_build.build_with_project(plan, self.service, None, None)
                self.assertEqual(self.service.calls, 0)
                self.assertFalse(target.exists())

    def test_failed_final_verification_preserves_existing_target(self):
        target = self.root / 'keep.iso'
        target.write_bytes(b'previous output')
        plan = mod_build.BuildPlan(str(self.source), str(target), overwrite=True)
        with mock.patch.object(mod_build, 'inspect', side_effect=ValueError('verification failed')):
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                mod_build.build_with_project(plan, self.service, None, None)
        self.assertEqual(target.read_bytes(), b'previous output')
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(list(self.root.glob('.studio-build-*')))


class CopyTests(unittest.TestCase):
    def test_short_kernel_copies_and_unsupported_fallback(self):
        import errno
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'in', Path(folder)/'out'
            payload = bytes(range(256)) * 8192
            source.write_bytes(payload)
            original = build_io.platform_compat.copy_file_range
            calls = []
            def short(src, dst, count, **kwargs):
                calls.append(count)
                if len(calls) > 1:
                    raise OSError(errno.EXDEV, 'cross device')
                return original(src, dst, 31, **kwargs)
            with mock.patch.object(build_io.platform_compat, 'copy_file_range', short):
                build_io.copy_image(source, target)
            self.assertEqual(target.read_bytes(), payload)
            self.assertGreater(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
