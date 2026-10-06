"""Output boundaries of the native stadium resource repair command."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b765 import d2_clock_repair as repair


class ResourceGuardTests(unittest.TestCase):
    def test_composed_reserved_wrapper_words_are_refused_before_decoding(self):
        chunk = SimpleNamespace(offset=16)
        for at in (0x18, 0x1C):
            with self.subTest(word=at):
                data = bytearray(64)
                struct.pack_into('<I', data, chunk.offset + at, 0x12345678)
                with patch.object(repair.ml, 'bundle_scenes', return_value={'stadium': chunk}), \
                        patch.object(repair.ml, '_scene') as decode:
                    with self.assertRaisesRegex(ValueError, 'reserved SCNE wrapper'):
                        repair.repair_resource(bytes(data), 's03dd.iff', allow_composed=True)
                # Reject even a previously fixed scene, before either state
                # could silently accept metadata the encoder would discard.
                decode.assert_not_called()


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.iff'
        self.target = self.root / 'fixed.iff'
        self.receipt = self.root / 'fixed.iff.receipt.json'
        self.source.write_bytes(b'input')

    def invoke(self, *options):
        with patch.object(sys, 'argv', ['repair', str(self.source), str(self.target), '--name', 's03dd.iff', *options]), \
                contextlib.redirect_stderr(io.StringIO()):
            repair.main()

    def test_new_output_and_receipt_keep_source(self):
        with patch.object(repair, 'repair_resource', return_value=(b'fixed', {'status': 'fixed'})):
            self.invoke()
        self.assertEqual(self.source.read_bytes(), b'input')
        self.assertEqual(self.target.read_bytes(), b'fixed')
        self.assertEqual(json.loads(self.receipt.read_text()), {'status': 'fixed'})

    def test_existing_output_or_receipt_is_never_overwritten(self):
        for path in (self.target, self.receipt):
            with self.subTest(path=path.name):
                path.write_bytes(b'existing')
                with self.assertRaises(SystemExit):
                    self.invoke()
                self.assertEqual(path.read_bytes(), b'existing')
                path.unlink()

    def test_dangling_output_or_receipt_symlink_is_refused(self):
        for path in (self.target, self.receipt):
            with self.subTest(path=path.name):
                try:
                    path.symlink_to(self.root / 'absent')
                except (OSError, NotImplementedError):
                    self.skipTest('symlinks unavailable')
                with self.assertRaises(SystemExit):
                    self.invoke()
                self.assertTrue(path.is_symlink())
                self.assertFalse((self.root / 'absent').exists())
                path.unlink()

    def test_symlink_input_is_refused(self):
        real = self.root / 'real.iff'
        self.source.rename(real)
        try:
            self.source.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertEqual(real.read_bytes(), b'input')
        self.assertFalse(self.target.exists())

    def test_composed_input_needs_matching_whole_file_hash(self):
        for options in (('--allow-composed',), ('--allow-composed', '--expected-input-sha256', '0' * 64)):
            with self.subTest(options=options), self.assertRaises(SystemExit):
                self.invoke(*options)
        self.assertFalse(self.target.exists())
        with patch.object(repair, 'repair_resource', return_value=(b'fixed', {})) as patched:
            self.invoke('--allow-composed', '--expected-input-sha256', repair.sha(b'input'))
        patched.assert_called_once_with(b'input', 's03dd.iff', allow_composed=True)

    def test_refused_native_input_creates_no_output(self):
        with patch.object(repair, 'repair_resource', side_effect=ValueError('foreign geometry')):
            with self.assertRaisesRegex(ValueError, 'foreign geometry'):
                self.invoke()
        self.assertFalse(self.target.exists())
        self.assertFalse(self.receipt.exists())


if __name__ == '__main__':
    unittest.main()
