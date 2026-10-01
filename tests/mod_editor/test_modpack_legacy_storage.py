"""A versioned storage operation preserves original release-writer output."""
from pathlib import Path
import copy
import json
import os
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import modpack as m, nfl2k5_depth_chart_storage as storage
from test_modpack import windows_file_locks

FIXTURES = ROOT / 'tests/fixtures/modpack_legacy'


class OriginalReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # The release writers used the existing public, zero-filled synthetic
        # final section. Every other reader/transport check runs unchanged.
        self.enterContext(patch.object(storage, 'RETAIL_CONTENT_SHA256',
                                       m._sha256(bytes(storage.RETAIL_SIZE))))
        self.receipts = json.loads((FIXTURES / 'original-release-receipts.json').read_text())

    def inputs(self, receipt):
        root = self.root / receipt['file']
        root.mkdir()
        base, expected = root / 'base.iso', root / 'expected.iso'
        base.write_bytes(zlib.decompress((FIXTURES / receipt['base_fixture']).read_bytes()))
        expected.write_bytes(zlib.decompress((FIXTURES / receipt['result_fixture']).read_bytes()))
        pack = FIXTURES / receipt['file']
        self.assertEqual(m.hash_file(base), receipt['base_sha256'])
        self.assertEqual(m.hash_file(expected), receipt['result_sha256'])
        self.assertEqual(m.hash_file(pack), receipt['pack_sha256'])
        return root, base, expected, pack

    def test_original_release_packs_and_reexports_reproduce_pinned_results(self):
        for receipt in self.receipts:
            with self.subTest(pack=receipt['file']):
                root, base, expected, pack = self.inputs(receipt)
                result, reexport = root / 'result.iso', root / 'reexport.2k5patch'
                # Exercise the real seek/read/write fallbacks used on Windows,
                # along with its refusal to replace files with open handles.
                with windows_file_locks() as opened, \
                     patch.object(os, 'pread', None, create=True), \
                     patch.object(os, 'pwrite', None, create=True):
                    self.assertEqual(m.check(pack, base)['state'], 'ready')
                    m.apply(pack, base, result)
                    self.assertEqual(m.hash_file(result), receipt['result_sha256'])
                    self.assertEqual(result.read_bytes(), expected.read_bytes())
                    self.assertEqual(m.check(pack, result)['state'], 'applied')
                    m.export(base, expected, reexport, {'name': 'legacy build'}, recipe=False)
                    self.assertEqual(m.check(reexport, base)['state'], 'ready')
                    m.apply_in_place(pack, base)
                    self.assertEqual(base.read_bytes(), expected.read_bytes())
                    self.assertEqual(m.hash_file(pack), receipt['pack_sha256'])
                    self.assertEqual(opened(), [])

    def test_invalid_storage_refuses_even_when_all_transport_hashes_agree(self):
        root, base, expected, pack = self.inputs(self.receipts[0])
        with zipfile.ZipFile(pack) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        manifest = json.loads(members['manifest.json'])
        operation = manifest['ops'][0]
        member = operation['payload']['member']
        original = members[member]
        # This fixture has the standard 22-section XBE directory. Mutations
        # target loader permissions, retained bytes, and unused allocation gaps.
        table = struct.unpack_from('<I', original, 0x120)[0] - 0x10000
        header = table + 21 * 56
        cases = {
            'writable': (header, original[header] | 1),
            'executable': (header, original[header] | 4),
            'retained_content': (storage.RETAIL_RAW, original[storage.RETAIL_RAW] ^ 1),
            'padding_before_table': (storage.RETAIL_RAW + storage.RETAIL_SIZE, 1),
            'padding_after_table': (storage.TABLE_RAW + storage.TABLE_SIZE, 1),
        }
        before = m.hash_file(base)
        for label, (offset, value) in cases.items():
            with self.subTest(storage=label):
                payload = bytearray(original)
                payload[offset] = value
                doc = copy.deepcopy(manifest)
                op = doc['ops'][0]
                op['after']['sha256'] = op['payload']['sha256'] = m._sha256(payload)
                image = bytearray(expected.read_bytes())
                start = op['after']['sector'] * 2048
                image[start:start + len(payload)] = payload
                doc['result']['sha256'] = m._sha256(image)
                invalid = root / (label + '.2k5patch')
                with zipfile.ZipFile(invalid, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, data in members.items():
                        archive.writestr(name, json.dumps(doc).encode() if name == 'manifest.json'
                                         else bytes(payload) if name == member else data)
                output = root / (label + '.iso')
                with windows_file_locks() as opened:
                    check = m.check(invalid, base)
                    self.assertEqual(check['state'], 'mismatch')
                    self.assertIn('SPECIAL storage', check['explanation'])
                    with self.assertRaisesRegex(m.ModpackError, 'SPECIAL storage'):
                        m.apply(invalid, base, output)
                    with self.assertRaisesRegex(m.ModpackError, 'SPECIAL storage'):
                        m.apply_in_place(invalid, base)
                    self.assertFalse(output.exists())
                    self.assertEqual(m.hash_file(base), before)
                    self.assertEqual(opened(), [])
                bad_image = root / (label + '-source.iso')
                bad_image.write_bytes(image)
                with self.assertRaisesRegex(m.ModpackError, 'SPECIAL storage'):
                    m.export(base, bad_image, root / (label + '-export.2k5patch'),
                             {'name': 'invalid storage'}, recipe=False)
                bad_image.unlink()


if __name__ == '__main__':
    unittest.main()
