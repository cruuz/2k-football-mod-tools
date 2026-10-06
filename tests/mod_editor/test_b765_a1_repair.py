"""Strict native file-set repair checks; full private proof requires an existing field cache.

Set B765_A1_FIELD_CACHE to an owned cache produced by the repair CLI to run the
read-only v0.4 integration checks. Synthetic cache checks need no game assets.
"""
from pathlib import Path
import json
import os
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools.b765 import a1_repair as repair


SCRATCH = Path(os.environ.get('B765_A1_SCRATCH', '/nonexistent/b765-a1'))


class StrictInputTests(unittest.TestCase):
    def test_baseline_and_previous_receipt_manifest(self):
        self.assertEqual(repair.accepted_hashes(None), repair.BASELINE)
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / 'accepted.json'
            for doc in (repair.BASELINE, {'files': {name: {'after_sha256': digest}
                                                   for name, digest in repair.BASELINE.items()}}):
                manifest.write_text(json.dumps(doc))
                self.assertEqual(repair.accepted_hashes(manifest), repair.BASELINE)

    def test_missing_incomplete_and_bad_manifest_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / 'accepted.json'
            with self.assertRaises(FileNotFoundError):
                repair.accepted_hashes(manifest)
            for doc in ({'0': repair.BASELINE['0']}, {**repair.BASELINE, 'extra': '0' * 64},
                        {**repair.BASELINE, 'F': 'bad'}, {**repair.BASELINE, 'F': []}, []):
                manifest.write_text(json.dumps(doc))
                with self.assertRaises(ValueError):
                    repair.accepted_hashes(manifest)

    def test_foreign_inputs_without_manifest_fail_before_source_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / 'source', Path(tmp) / 'output'
            source.mkdir()
            for name in repair.BASELINE:
                (source / name).write_bytes(b'foreign fixture')
            with patch.object(repair.archive, 'Disc') as disc:
                with self.assertRaisesRegex(ValueError, 'unexpected input hash: 0'):
                    repair.main(['--input-dir', str(source), '--output-dir', str(output)])
                disc.assert_not_called()
            self.assertFalse(output.exists())
            self.assertTrue(all((source / name).read_bytes() == b'foreign fixture' for name in repair.BASELINE))

    def test_explicit_manifest_authorizes_only_its_exact_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / 'source', Path(tmp) / 'output'
            source.mkdir()
            payloads = {name: ('explicit fixture ' + name).encode() for name in repair.BASELINE}
            for name, raw in payloads.items():
                (source / name).write_bytes(raw)
            manifest = Path(tmp) / 'accepted.json'
            manifest.write_text(json.dumps({name: repair.sha(raw) for name, raw in payloads.items()}))
            args = ['--input-dir', str(source), '--output-dir', str(output), '--accepted-input-hashes', str(manifest)]
            with patch.object(repair.archive, 'Disc', side_effect=RuntimeError('read-only source reached')) as disc:
                with self.assertRaisesRegex(RuntimeError, 'read-only source reached'):
                    repair.main(args)
                disc.assert_called_once()
            (source / 'F').write_bytes(b'changed after authorization')
            with patch.object(repair.archive, 'Disc') as disc:
                with self.assertRaisesRegex(ValueError, 'unexpected input hash: F'):
                    repair.main(args)
                disc.assert_not_called()
            self.assertFalse(output.exists())

    def test_output_refuses_replacement_and_same_input_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            path = source / 'owned'
            repair.write_new(path, b'exact bytes')
            repair.write_new(path, b'exact bytes')
            with self.assertRaisesRegex(ValueError, 'refusing to replace'):
                repair.write_new(path, b'different')
            self.assertEqual(path.read_bytes(), b'exact bytes')
            with self.assertRaisesRegex(ValueError, 'must differ'):
                repair.main(['--input-dir', str(source), '--output-dir', str(source)])


class FieldCacheTests(unittest.TestCase):
    def test_dependency_cache_replays_and_rejects_changed_source_artifact_or_foreign_alias(self):
        catalog = [dict(row=i+1, source_kind='built', source_prefix='s00', endzones=[], center='TEAM', season=2025)
                   for i in range(51)]
        context = dict(catalog_sha256='catalog', art={'art.png': 'art'}, compiler={'compiler.py': 'code'},
                       variants=['dd']*51, python='synthetic', pillow='synthetic', numpy='synthetic')
        aliases = {f'a{i:02d}dd.iff': ('synthetic alias ' + str(i)).encode() for i in range(51)}
        def compiler(get, retail_get, situ, *, progress=None):
            get('s00dd.iff')
            retail_get('s25dd.iff')
            return aliases, {'synthetic_test_only': True}
        with tempfile.TemporaryDirectory() as tmp, patch.object(repair, 'field_context', return_value=context), \
                patch.object(repair.fields, 'catalog', return_value=catalog), \
                patch.object(repair.fields, 'variant', return_value='dd'), \
                patch.object(repair.fields, 'compile_assets', side_effect=compiler) as compile_mock:
            cache = Path(tmp)
            get = lambda name: b'built source'
            retail_get = lambda name: b'retail source'
            first, receipt = repair.compile_fields(get, retail_get, b'synthetic situ', cache, None)
            again, replay = repair.compile_fields(get, retail_get, b'synthetic situ', cache, None)
            self.assertEqual((first, again), (aliases, aliases))
            self.assertEqual((receipt['cache'], replay['cache']), ('compiled', 'verified_hit'))
            self.assertEqual(compile_mock.call_count, 1)
            folder = cache / receipt['cache_key']
            manifest = folder / 'manifest.json'
            original = manifest.read_bytes()
            (folder / 'a00dd.iff').write_bytes(b'changed artifact')
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                repair.compile_fields(get, retail_get, b'synthetic situ', cache, None)
            (folder / 'a00dd.iff').write_bytes(aliases['a00dd.iff'])
            doc = json.loads(original)
            doc['aliases']['foreign.iff'] = repair.sha(b'foreign')
            manifest.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, 'foreign cached alias'):
                repair.compile_fields(get, retail_get, b'synthetic situ', cache, None)
            manifest.write_bytes(original)
            # A different source creates a different dependency key and never reuses these aliases.
            changed, changed_receipt = repair.compile_fields(lambda name: b'new built source', retail_get,
                                                            b'synthetic situ', cache, None)
            self.assertEqual(changed, aliases)
            self.assertNotEqual(changed_receipt['cache_key'], receipt['cache_key'])
            self.assertEqual(compile_mock.call_count, 2)


@unittest.skipUnless((SCRATCH / 'default.xbe').exists(), 'private v0.4 executable fixture absent')
class NativeSealTests(unittest.TestCase):
    def test_changed_helper_without_owner_seal_refused(self):
        before = (SCRATCH / 'default.xbe').read_bytes()
        code, _dat = repair.mm.allocations(before)
        foreign = bytearray(before)
        foreign[code['raw'] + repair.mm.DISPLAY_OFFSET] ^= 1
        self.assertEqual(repair.mm.legacy_status(bytes(foreign), repair.legacy_data()), 'foreign')
        with self.assertRaises(ValueError):
            repair.mm.apply(bytes(foreign), repair.mm.Data.load(), legacy_data=repair.legacy_data())
        self.assertEqual((SCRATCH / 'default.xbe').read_bytes(), before)

    def test_foreign_helper_with_recomputed_seal_still_refused(self):
        before = (SCRATCH / 'default.xbe').read_bytes()
        code, _dat = repair.mm.allocations(before)
        body = bytearray(before[code['raw']:code['raw'] + code['size']])
        body[repair.mm.DISPLAY_OFFSET] ^= 1
        buffer = bytearray(before)
        buffer[code['raw']:code['raw'] + code['size']] = body
        repair.space._seal_scaleout(buffer, repair.space._read_scale_directory(before))
        for section in repair.mm._sections(buffer):
            buffer[section.header_offset + 36:section.header_offset + 56] = repair.mm.section_digest(buffer, section)
        foreign = bytes(buffer)
        self.assertEqual(repair.space.status(foreign), 'applied')
        self.assertEqual(repair.mm.legacy_status(foreign, repair.legacy_data()), 'foreign')
        with self.assertRaisesRegex(ValueError, 'exact legacy profile'):
            repair.mm.apply(foreign, repair.mm.Data.load(), legacy_data=repair.legacy_data())
        self.assertEqual((SCRATCH / 'default.xbe').read_bytes(), before)


@unittest.skipUnless(os.environ.get('B765_A1_FIELD_CACHE') and (SCRATCH / 'pack0').exists(),
                     'set B765_A1_FIELD_CACHE for the private native field proof')
class NativeFileSetTests(unittest.TestCase):
    def test_full_repair_replay_foreign_resource_and_preserved_roster_kits(self):
        inputs = {name: (SCRATCH / {'0': 'pack0', 'F': 'packF'}.get(name, name)).read_bytes()
                  for name in repair.BASELINE}
        self.assertEqual({name: repair.sha(raw) for name, raw in inputs.items()}, repair.BASELINE)
        with repair.archive.Disc(repair.V04_DISC, descriptors=()) as original, repair.styles.Source(repair.RETAIL) as retail:
            results, receipt = repair.transform(inputs, original, retail,
                                                field_cache=Path(os.environ['B765_A1_FIELD_CACHE']))
            again, replay = repair.transform(results, original, retail,
                                             field_cache=Path(os.environ['B765_A1_FIELD_CACHE']))
            self.assertEqual(results, again)
            self.assertEqual(replay['packs']['status'], 'already_applied')
            self.assertTrue(receipt['xbe_scope']['outside_scope_identical'])
            self.assertTrue(receipt['xbe_scope']['unrelated_owner_bodies_identical'])
            runs = receipt['xbe_scope']['changed_runs']
            self.assertEqual(sum(row['size'] for row in runs), receipt['xbe_scope']['changed_bytes'])
            self.assertTrue(all(left['raw_end'] < right['raw_start'] for left, right in zip(runs, runs[1:])))
            for row in runs:
                before = inputs['default.xbe'][row['raw_start']:row['raw_end']]
                after = results['default.xbe'][row['raw_start']:row['raw_end']]
                self.assertEqual((repair.sha(before), repair.sha(after)), (row['before_sha256'], row['after_sha256']))
                self.assertTrue(all(a != b for a, b in zip(before, after)))
            self.assertEqual([(r['identity'], r['spare']) for r in receipt['teams']], [(224, 6), (225, 8)])
            get = repair.file_reader(results['0'], results['F'], original)
            for row in receipt['teams']:
                raw = get(row['name'])
                doc = repair.rr.RosterDocument(raw[32:])
                self.assertEqual(len(doc.players), 53)
                self.assertEqual(struct.unpack_from('<H', raw, 32 + doc.teams[0].offset + 0x118)[0], row['identity'])
                self.assertEqual(raw[32 + doc.teams[0].offset + repair.styles.STYLE], row['spare'])
            situ = get(identity=repair.mm.SITU_ID)
            at = 32 + repair.mm.sc.RECORDS + 50 * repair.mm.sc.STRIDE
            self.assertEqual(struct.unpack_from('<II', situ, at + 0x58), (6, 8))
            self.assertEqual(struct.unpack_from('<I', situ, 8)[0], 51)
            # Every pre-existing team remains the source E member, byte for byte.
            old_get = repair.file_reader(inputs['0'], inputs['F'], original)
            old_directory = {row[0]: row for row in repair.packs.entries(inputs['0'])}
            new_directory = {row[0]: row for row in repair.packs.entries(results['0'])}
            growth = (len(results['0']) - len(inputs['0'])) // 2048
            for _key, name, _entry, _selector, _identity in repair.mm.table_entries(repair.legacy_data()):
                self.assertEqual(get(name), old_get(name))
                identity = repair.mm.name_id(name)
                old_row, new_row = old_directory[identity], new_directory[identity]
                self.assertEqual(new_row, (identity, old_row[1], old_row[2] + growth))
            alias = next(row for row in repair.packs.entries(results['0']) if row[0] == repair.mm.name_id('a00ds.iff'))
            start_f = sum(struct.unpack_from('<16I', results['0'], 12)[:15]) * 2048
            broken_f = bytearray(results['F'])
            broken_f[alias[2] * 2048 - start_f] ^= 1
            with self.assertRaisesRegex(ValueError, 'foreign existing'):
                repair.transform(dict(results, F=bytes(broken_f)), original, retail,
                                 field_cache=Path(os.environ['B765_A1_FIELD_CACHE']))


if __name__ == '__main__':
    unittest.main()
