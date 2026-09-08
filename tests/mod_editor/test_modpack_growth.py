"""Chained named growth, retained allocations, legacy readers and transactions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import modpack as m, modpack_ops as ops
from mod_editor.core import nfl2k5_depth_chart_storage as storage
from nfl2k5_xiso_fixture import dir_node
from test_modpack import build_xdvdfs, windows_file_locks


FILES = {'default.xbe': b'XBEH' + bytes(99), 'vc_53450030/0': b'pack zero',
         'vc_53450030/1': b'pack one', 'keep.bin': b'neighbour', 'short.bin': b'shrink this file'}


def make_image(path, partition=0):
    """Small real nested directory; sparse partition prefix, bounded file writes."""
    layout = {name: 40 + i * 2 for i, name in enumerate(FILES)}
    root = dir_node([(layout[n], len(FILES[n]), 0x80, n) for n in FILES if '/' not in n]
                    + [(34, 40, 0x10, 'vc_53450030')])
    sub = dir_node([(layout[n], len(FILES[n]), 0x80, n.split('/')[-1]) for n in FILES if '/' in n])
    with path.open('wb') as f:
        f.seek(partition + 0x10000); f.write(m._xdvdfs_module().XDVDFS_MAGIC)
        f.write(struct.pack('<II', 33, len(root)))
        f.seek(partition + 0x107ec); f.write(m._xdvdfs_module().XDVDFS_MAGIC)
        f.seek(partition + 33 * 2048); f.write(root)
        f.seek(partition + 34 * 2048); f.write(sub)
        for name, body in FILES.items():
            f.seek(partition + layout[name] * 2048); f.write(body)
        f.truncate(partition + 50 * 2048 + 13)


def write_file(path, name, body, partition=0):
    with path.open('r+b') as f:
        size = os.fstat(f.fileno()).st_size
        node, sector, old_size = storage.image_file_node(
            lambda n, at: m._pread_exact(f.fileno(), n, at, 'fixture'), partition, size, name)
        at = (size + 2047) // 2048 * 2048 if len(body) > old_size else partition + sector * 2048
        m._pwrite_all(f.fileno(), body, at, 'fixture')
        m._pwrite_all(f.fileno(), struct.pack('<II', (at-partition)//2048, len(body)), node, 'fixture')


def assert_same(test, left, right):
    test.assertEqual(left.stat().st_size, right.stat().st_size)
    with left.open('rb') as a, right.open('rb') as b:
        at = 0
        while chunk := a.read(1024 * 1024):
            test.assertTrue(chunk == b.read(len(chunk)), f'image bytes differ at block 0x{at:x}')
            at += len(chunk)
        test.assertEqual(b.read(1), b'')


class ChainedGrowthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.base, self.built, self.pack, self.result = [self.root / p for p in
            ('base.iso', 'built.iso', 'growth.2k5patch', 'result.iso')]
        make_image(self.base)
        shutil.copyfile(self.base, self.built)

    def build(self, retained=False, partition=0):
        if partition:
            make_image(self.base, partition)
            shutil.copyfile(self.base, self.built)
        if retained:
            write_file(self.built, 'default.xbe', b'XBEH' + b'old allocated XBE' * 201, partition)
        write_file(self.built, 'vc_53450030/1', b'first grown pack' * 251, partition)
        write_file(self.built, 'default.xbe', b'XBEH' + b'final grown executable' * 501, partition)
        write_file(self.built, 'vc_53450030/0', b'last grown pack' * 311, partition)
        write_file(self.built, 'short.bin', b'short', partition)
        with self.built.open('r+b') as f:
            f.seek(partition + 150); f.write(b'ordinary edit')
        return self.export()

    def export(self):
        return m.export(self.base, self.built, self.pack, {'name': 'Chained growth'}, recipe=False,
                        file_operations=['VC_53450030/0', 'default.xbe', 'vc_53450030/1',
                                         'vc_53450030/0', 'short.bin'], overwrite=True)

    def roundtrip(self):
        before = m.hash_file(self.base)
        with windows_file_locks() as opened:
            self.assertEqual(m.check(self.pack, self.base)['state'], 'ready')
            self.assertEqual(m.check(self.pack, self.built)['state'], 'applied')
            m.apply(self.pack, self.base, self.result)
            self.assertEqual(opened(), [])
            assert_same(self, self.result, self.built)
            self.assertEqual(m.hash_file(self.base), before)
            m.apply_in_place(self.pack, self.base)
            self.assertEqual(opened(), [])
            with self.assertRaisesRegex(m.ModpackError, 'already present'):
                m.apply_in_place(self.pack, self.base)
        assert_same(self, self.base, self.built)

    def test_three_growths_shrink_and_runs_follow_physical_order(self):
        report = self.build()
        self.assertEqual([o['type'] for o in report['ops']], [0, 5, 3, 3, 3])
        self.assertEqual(report['min_reader_version'], 2)
        current = self.base.stat().st_size
        for op in report['ops']:
            self.assertEqual(op['before_size'], current)
            if op['type'] == 3:
                self.assertEqual(op['version'], 1)
                self.assertEqual(op['append'], {'sector': (current+2047)//2048, 'file_sector_offset': 0})
            current = op['after_size']
        self.assertEqual(current, self.built.stat().st_size)
        self.roundtrip()

    def test_retained_intermediate_allocation_is_hashed_and_reproduced(self):
        report = self.build(retained=True)
        grow = next(o for o in report['ops'] if o['type'] == 3)
        self.assertEqual(grow['version'], 2)
        self.assertGreater(grow['append']['file_sector_offset'], 0)
        self.assertEqual(grow['payload']['length'], grow['after_size'] - grow['append']['sector']*2048)
        self.assertNotEqual(grow['after']['sha256'], grow['payload']['sha256'])
        self.assertEqual(report['min_reader_version'], 2)  # old readers safely refuse op version 2
        self.roundtrip()

    def test_partition_relative_chains(self):
        with patch.object(m._xdvdfs_module(), 'XDVDFS_BASE_OFFSETS', (0, 0x8000)):
            self.build(retained=True, partition=0x8000)
            self.roundtrip()

    def rewrite(self, edit, payload_edit=None):
        with zipfile.ZipFile(self.pack) as z:
            members = {n: z.read(n) for n in z.namelist()}
        doc = json.loads(members[m.MANIFEST_MEMBER]); edit(doc)
        if payload_edit:
            payload_edit(doc, members)
        members[m.MANIFEST_MEMBER] = json.dumps(doc).encode()
        with zipfile.ZipFile(self.pack, 'w') as z:
            for name, data in members.items(): z.writestr(name, data)

    def test_bad_accounting_and_hashes_refuse_before_copy(self):
        for mutation in ('chain', 'sector', 'offset', 'length', 'file_hash', 'before_hash', 'payload'):
            with self.subTest(mutation=mutation):
                self.build(retained=True)
                def edit(doc):
                    op = next(o for o in doc['ops'] if o['version'] == 2)
                    if mutation == 'chain': op['before_size'] += 1
                    elif mutation == 'sector': op['append']['sector'] += 1
                    elif mutation == 'offset': op['append']['file_sector_offset'] += 1
                    elif mutation == 'length': op['payload']['length'] -= 1
                    elif mutation == 'file_hash': op['after']['sha256'] = '0'*64
                    elif mutation == 'before_hash': op['before']['sha256'] = '0'*64
                    else: op['payload']['sha256'] = '0'*64
                self.rewrite(edit)
                with self.assertRaises(m.ModpackError): m.apply(self.pack, self.base, self.result)
                self.assertFalse(self.result.exists())
                self.assertFalse(self.result.with_name('result.iso.part').exists())
                shutil.copyfile(self.base, self.built)

    def test_middle_growth_write_failure_preserves_destination_and_closes_handles(self):
        self.build(retained=True)
        self.result.write_bytes(b'previous result')
        original = m._pwrite_all
        def fail(fd, data, at, what):
            if what == 'file_grow' and data.startswith(b'XBEHfinal'):
                original(fd, data[:3], at, what)
                raise OSError('second growth failed')
            return original(fd, data, at, what)
        with windows_file_locks() as opened, patch.object(m, '_pwrite_all', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'second growth'):
                m.apply(self.pack, self.base, self.result, overwrite=True)
            self.assertEqual(opened(), [])
        self.assertEqual(self.result.read_bytes(), b'previous result')
        self.assertFalse(self.result.with_name('result.iso.part').exists())
        self.assertEqual(m.check(self.pack, self.base)['state'], 'ready')

    def test_corrupt_retained_bytes_and_intermediate_state_are_mismatch(self):
        report = self.build(retained=True)
        grow = next(o for o in report['ops'] if o['version'] == 2)
        with self.built.open('r+b') as f:
            f.seek(grow['append']['sector'] * 2048); f.write(b'BAD!')
        self.assertEqual(m.check(self.pack, self.built)['state'], 'mismatch')
        shutil.copyfile(self.base, self.result)
        write_file(self.result, 'vc_53450030/1', b'first grown pack' * 251)
        self.assertEqual(m.check(self.pack, self.result)['state'], 'mismatch')

    def test_unaccounted_final_tail_and_nonzero_alignment_refuse_export(self):
        self.build()
        with self.built.open('ab') as f: f.write(b'unknown tail')
        with self.assertRaisesRegex(m.ModpackError, 'unrecognised image size change'): self.export()
        shutil.copyfile(self.base, self.built)
        self.build()
        with self.built.open('r+b') as f:
            f.seek(self.base.stat().st_size); f.write(b'bad alignment')
        with self.assertRaisesRegex(m.ModpackError, 'outside the declared operations'): self.export()

    def test_old_reader_version_check_refuses_new_op_before_writing(self):
        self.build(retained=True)
        with patch.object(ops.FileGrow, 'versions', (1,)):
            with self.assertRaisesRegex(m.ModpackError, 'this mod needs a newer Mod Studio: file_grow version 2'):
                m.apply(self.pack, self.base, self.result)
        self.assertFalse(self.result.exists())

    def test_repeated_growth_of_the_same_file_uses_each_intermediate_hash(self):
        operations, payloads = [], {}
        for i in range(3):
            with self.built.open('rb') as f:
                size = os.fstat(f.fileno()).st_size
                node, sector, length = storage.image_file_node(
                    lambda n, at: m._pread_exact(f.fileno(), n, at, 'fixture'), 0, size, 'vc_53450030/0')
                before_sha = ops.digest(lambda n, at: m._pread_exact(f.fileno(), n, sector*2048+at, 'fixture'), length)
            body = bytes([65+i]) * (100 + i*100)
            write_file(self.built, 'vc_53450030/0', body)
            member = f'operations/repeat-{i}.bin'
            payloads[member] = body
            operations.append(dict(type=3, name='file_grow', version=1, path='vc_53450030/0',
                directory_offset=node, before_size=size, after_size=self.built.stat().st_size,
                before=dict(sector=sector, size=length, sha256=before_sha),
                after=dict(sector=(size+2047)//2048, size=len(body), sha256=m._sha256(body)),
                append=dict(sector=(size+2047)//2048, file_sector_offset=0),
                payload=dict(member=member, length=len(body), sha256=m._sha256(body))))
        m.export(self.base, self.built, self.pack, {'name': 'Repeated growth'}, recipe=False,
                 patch_operations=operations, operation_payloads=payloads)
        self.roundtrip()

    def test_retained_prefix_larger_than_a_block_streams_through_bounded_reads(self):
        start = (self.base.stat().st_size+2047)//2048*2048
        end = start + 2*m.BLOCK
        with self.built.open('r+b') as f:
            f.seek(start); f.write(b'retained start')
            f.seek(end-32); f.write(b'retained end')
            f.truncate(end)
        write_file(self.built, 'vc_53450030/0', b'grown pack' * 100)
        original = m._pread_exact
        def bounded(fd, count, at, label):
            self.assertLessEqual(count, m.BLOCK, label)
            return original(fd, count, at, label)
        with patch.object(m, '_pread_exact', new=bounded):
            report = self.export()
            grow = next(o for o in report['ops'] if o['type'] == 3)
            self.assertEqual(grow['append']['file_sector_offset']*2048, 2*m.BLOCK)
            m.apply(self.pack, self.base, self.result)
        assert_same(self, self.result, self.built)


class LegacyPackTests(unittest.TestCase):
    def test_frozen_beta60_and_beta61_basic_and_advanced_packs(self):
        from nfl2k5_depth_chart_rows_test import fixture, prepare
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        fixtures = ROOT / 'tests/fixtures/modpack_legacy'
        receipts = json.loads((fixtures / 'receipts.json').read_text())
        with tempfile.TemporaryDirectory() as temp, patch.object(
                storage, 'RETAIL_CONTENT_SHA256', m._sha256(bytes(storage.RETAIL_SIZE))):
            root = Path(temp).resolve()
            retail = fixture()
            special = bytes(rows.apply(prepare(retail))[0])
            for receipt in receipts:
                with self.subTest(pack=receipt['file']):
                    beta, preset = receipt['file'].removesuffix('.2k5patch').split('-')[1:]
                    base, expected, result = [root / p for p in ('base.iso', 'expected.iso', 'result.iso')]
                    base.write_bytes(build_xdvdfs({'default.xbe': retail if preset == 'advanced' else b'XBEH'+bytes(100),
                                                  'next.bin': b'neighbour'}, tail_pad=19))
                    shutil.copyfile(base, expected)
                    with expected.open('r+b') as f:
                        if preset == 'advanced': storage.write_image_xbe(f.fileno(), special)
                        m._pwrite_all(f.fileno(), f'beta-{beta} {preset}'.encode(), 123, 'fixture marker')
                    pack = fixtures / receipt['file']
                    self.assertEqual(m.hash_file(pack), receipt['pack_sha256'])
                    self.assertEqual(m.hash_file(base), receipt['base_sha256'])
                    self.assertEqual(m.hash_file(expected), receipt['result_sha256'])
                    self.assertEqual(m.check(pack, base)['state'], 'ready')
                    m.apply(pack, base, result, overwrite=True)
                    assert_same(self, expected, result)
                    self.assertEqual(m.check(pack, result)['state'], 'applied')
                    m.apply_in_place(pack, base)
                    assert_same(self, expected, base)
                    self.assertEqual(m.hash_file(pack), receipt['pack_sha256'])


if __name__ == '__main__': unittest.main()
