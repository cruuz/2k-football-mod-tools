"""Native repair scope, refused foreign bytes and reserve compatibility.

Small synthetic XBE fixtures exercise the scope writer without retail data.
The optional actual v0.4 check uses a private extraction, never bundled bytes.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import hashlib
import os
import struct
import unittest

from tools.b765 import p1_repair as repair
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest


def fixture():
    # Two separate file-backed sections around the two real patch addresses.
    out = bytearray(0x4000)
    out[:4] = b'XBEH'
    struct.pack_into('<I', out, 0x104, 0x10000)
    struct.pack_into('<I', out, 0x108, 0x1000)
    struct.pack_into('<I', out, 0x10C, 0x530000)
    struct.pack_into('<I', out, 0x11C, 22)
    struct.pack_into('<I', out, 0x120, 0x10300)
    for n in range(22):
        struct.pack_into('<9I', out, 0x300 + 56 * n, 0, 0x60000 + n * 0x1000,
                         0x1000, 0, 0, 0x10820, 0, 0, 0)
    for n, va in enumerate((0x2BF000, 0x522000)):
        header = 0x300 + 56 * n
        raw = 0x1000 + 0x1000 * n
        struct.pack_into('<9I', out, header, 4, va, 0x1000, raw, 0x1000,
                         0x10800 + n * 8, 0, 0, 0)
        out[0x800 + n * 8:0x808 + n * 8] = (b'.text\0\0\0', b'.rdata\0\0')[n]
        out[raw:raw + 0x1000] = bytes([0x90 + n]) * 0x1000
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    image = XbeImage(out)
    for _, va, before, _ in repair.SITES:
        at = image.offset(va, len(before)); out[at:at + len(before)] = before
    for s in _sections(out):
        out[s.header_offset + 36:s.header_offset + 56] = section_digest(out, s)
    return bytes(out)


class ScopeTests(unittest.TestCase):
    def test_scope_composed_input_and_idempotence(self):
        before = fixture()
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            repair.repair(before)
        fixed, receipt = repair.repair(before, expected_input_sha256=repair.digest(before))
        self.assertEqual(receipt['disc_files'], ['default.xbe'])
        self.assertEqual(len(receipt['ranges']), 4)
        self.assertTrue(receipt['outside_scope_identical'])
        self.assertEqual(receipt['outside_before_sha256'], receipt['outside_after_sha256'])
        self.assertEqual(receipt['new_code_caves'], [])
        self.assertFalse(receipt['save_changes'])
        self.assertEqual(repair.repair(fixed, expected_input_sha256=repair.digest(fixed))[0], fixed)
        self.assertNotEqual(before, fixed)

    def test_expected_hash_does_not_bypass_instruction_guard(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        before = bytearray(fixture())
        at = XbeImage(before).offset(repair.SITES[0][1], 5)
        before[at] ^= 1
        for s in _sections(before):
            before[s.header_offset + 36:s.header_offset + 56] = section_digest(before, s)
        original = bytes(before)
        with self.assertRaisesRegex(ValueError, 'unexpected bytes'):
            repair.repair(original, expected_input_sha256=repair.digest(original))
        self.assertEqual(bytes(before), original)

    def test_expected_hash_does_not_bypass_section_digest(self):
        before = bytearray(fixture()); before[0x1000] ^= 1
        with self.assertRaisesRegex(ValueError, 'section digest'):
            repair.repair(bytes(before), expected_input_sha256=repair.digest(before))

    def test_copy_writer_preserves_existing_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'copy.xbe'
            repair.write_copy(target, b'our file')
            repair.write_copy(target, b'our file')
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                repair.write_copy(target, b'foreign file')
            self.assertEqual(target.read_bytes(), b'our file')

    def test_actual_v04_native_and_studio_writers_agree(self):
        source = os.environ.get('B765_P1_V04_XBE')
        if not source:
            self.skipTest('private v0.4 extraction not configured')
        from mod_editor.core import nfl2k5_practice_squad_screen as screen
        before = Path(source).read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(), repair.V04_SHA256)
        native, receipt = repair.repair(before)
        studio, _ = screen.apply(before)
        self.assertEqual(native, studio)
        self.assertEqual(receipt['after_sha256'], repair.FIXED_SHA256)
        self.assertEqual(receipt['changed_bytes'], 48)
        self.assertEqual(repair.repair(native)[0], native)


if __name__ == '__main__':
    unittest.main()
