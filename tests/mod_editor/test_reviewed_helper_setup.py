"""Permission repair is explicit and pinned; the runtime predicate stays strict."""
import contextlib
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import apf_field_art_patch as art
from tools import setup_reviewed_helpers as setup

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('permission_stage', ROOT / 'packaging/stage_release.py')
stage_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage_release)


@contextlib.contextmanager
def linux_x86_64():
    """Present the reviewed-helper runtime predicate with its one supported platform.

    ``_optimal_binary`` answers ``None`` everywhere but Linux x86_64 before it
    looks at the file at all. The file-based checks under test are the same on
    every POSIX host, so a macOS CI runner exercises them through this shim.
    """
    with patch.object(sys, 'platform', 'linux'), patch('platform.machine', return_value='x86_64'):
        yield


@unittest.skipUnless(os.name == 'posix', 'Unix mode-bit/descriptor tests require POSIX')
class PermissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='reviewed-helper-test-')
        self.addCleanup(self.temporary.cleanup)
        # The tool refuses a symlinked ancestor by design; macOS temp dirs sit
        # under /var -> /private/var, so every test starts from the real path.
        self.root = Path(self.temporary.name).resolve()
        (self.root / 'tools').mkdir()
        self.helper = self.root / 'tools/apf_h7a_optimal'
        shutil.copyfile(ROOT / 'tools/apf_h7a_optimal', self.helper)
        self.helper.chmod(0o775)

    def test_setup_corrects_exact_helper_and_is_idempotent(self):
        before = self.helper.read_bytes()
        with linux_x86_64(), patch.object(art, '_OPTIMAL_BINARY', self.helper):
            self.assertIsNone(art._optimal_binary())
            self.assertEqual(art.optimal_encoder_diagnostic()['code'], 'unsafe_permissions')
            receipt = setup.normalize(self.root)
            self.assertTrue(receipt['changed'])
            self.assertEqual(stat.S_IMODE(self.helper.stat().st_mode), 0o755)
            self.assertEqual(art._optimal_binary(), self.helper)
            self.assertEqual(art.optimal_encoder_diagnostic()['code'], 'available')
            self.assertFalse(setup.normalize(self.root)['changed'])
        self.assertEqual(self.helper.read_bytes(), before)

    def test_wrong_bytes_never_get_chmod(self):
        self.helper.write_bytes(bytes(setup.SIZE))
        with self.assertRaisesRegex(setup.SetupError, 'SHA-256'):
            setup.normalize(self.root)
        self.assertEqual(stat.S_IMODE(self.helper.stat().st_mode), 0o775)

    def test_symlink_and_hardlink_refused(self):
        real = self.root / 'real'
        self.helper.rename(real)
        self.helper.symlink_to(real)
        with self.assertRaisesRegex(setup.SetupError, 'non-symlink'):
            setup.normalize(self.root)
        self.helper.unlink()
        os.link(real, self.helper)
        with self.assertRaisesRegex(setup.SetupError, 'one link'):
            setup.normalize(self.root)
        self.assertEqual(stat.S_IMODE(real.stat().st_mode), 0o775)

    def test_parent_symlink_refused(self):
        actual = self.root / 'real-tools'
        (self.root / 'tools').rename(actual)
        (self.root / 'tools').symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(setup.SetupError, 'symlinked parent'):
            setup.normalize(self.root)

    def test_parent_swapped_after_inspection_is_refused_without_chmod(self):
        actual = self.root / 'real-tools'
        original_open = os.open
        swapped = False

        def swap_then_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped:
                swapped = True
                (self.root / 'tools').rename(actual)
                (self.root / 'tools').symlink_to(actual, target_is_directory=True)
            return original_open(path, flags | getattr(os, 'O_BINARY', 0), *args, **kwargs)

        with patch.object(setup.os, 'open', swap_then_open), self.assertRaises(OSError):
            setup.normalize(self.root)
        self.assertEqual(stat.S_IMODE((actual / 'apf_h7a_optimal').stat().st_mode), 0o775)

    def test_pin_matches_runtime_and_read_error_has_diagnostic(self):
        self.assertEqual(setup.SIZE, art._OPTIMAL_BINARY_SIZE)
        self.assertEqual(setup.SHA256, art._OPTIMAL_BINARY_SHA256)
        with patch.object(art, '_optimal_binary', side_effect=PermissionError('test denied')):
            self.assertEqual(art.optimal_encoder_diagnostic()['code'], 'unreadable')
            with self.assertLogs(art.__name__, level='WARNING') as log:
                self.assertTrue(art.compress_h7a_best(b'headless-test' * 4, 12))
        self.assertIn('test denied', log.output[0])

    def test_precise_fallback_diagnostic(self):
        with linux_x86_64(), patch.object(art, '_OPTIMAL_BINARY', self.helper), \
                self.assertLogs(art.__name__, level='WARNING') as log:
            result = art.compress_h7a_best(b'headless-test' * 4, 12)
        self.assertTrue(result)
        self.assertIn('0775 is group/other writable', log.output[0])
        self.assertIn('setup_reviewed_helpers.py', log.output[0])
        self.assertEqual(stat.S_IMODE(self.helper.stat().st_mode), 0o775)

    def test_other_predicate_reasons(self):
        cases = ((0o644, 'not_executable'), (0o777, 'unsafe_permissions'))
        for mode, reason in cases:
            self.helper.chmod(mode)
            with linux_x86_64(), patch.object(art, '_OPTIMAL_BINARY', self.helper):
                self.assertIsNone(art._optimal_binary())
                self.assertEqual(art.optimal_encoder_diagnostic()['code'], reason)
        self.helper.write_bytes(b'short')
        with linux_x86_64(), patch.object(art, '_OPTIMAL_BINARY', self.helper):
            self.assertEqual(art.optimal_encoder_diagnostic()['code'], 'wrong_size')
        with patch.object(sys, 'platform', 'darwin'), patch.object(art, '_OPTIMAL_BINARY', self.helper):
            self.assertIsNone(art._optimal_binary())
            self.assertEqual(art.optimal_encoder_diagnostic()['code'], 'unsupported_platform')

    def test_stage_strips_umask_write_bits_not_source_permissions(self):
        text = self.root / 'plain.txt'
        text.write_text('unchanged bytes\n')
        text.chmod(0o664)
        allowlist = self.root / 'allowlist.txt'
        allowlist.write_text('tools/apf_h7a_optimal\nplain.txt\n')
        destination = self.root / 'stage'
        stage_release.stage(allowlist, destination, self.root)
        helper = destination / 'tools/apf_h7a_optimal'
        self.assertEqual(stat.S_IMODE(helper.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((destination / 'plain.txt').stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(self.helper.stat().st_mode), 0o775)
        self.assertEqual(stat.S_IMODE(text.stat().st_mode), 0o664)
        self.assertEqual(helper.read_bytes(), self.helper.read_bytes())
        with linux_x86_64(), patch.object(art, '_OPTIMAL_BINARY', helper):
            self.assertEqual(art._optimal_binary(), helper)


if __name__ == '__main__':
    unittest.main()
