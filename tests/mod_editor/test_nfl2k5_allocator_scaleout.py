"""Standalone scale-out capacity, loader geometry, transactional and CPU proofs."""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_music_storage as music
from mod_editor.core import nfl2k5_depth_chart_storage as storage
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_cave_manifest import Recorder
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from tests.mod_editor.test_nfl2k5_xbe_space import synthetic, PublicTests, RETAIL, repin
from tests.nfl2k5_allocator_stack import REQUESTS, compose

LARGE = (("synthetic_scaleout", "code", 90 * 1024, 4096),
         ("synthetic_scaleout", "data", 64 * 1024, 4096),
         ("synthetic_scaleout", "read_only", 1024, 16))


class PlannerTests(unittest.TestCase):
    def test_large_owner_fits_and_legacy_owner_addresses_stay_exact(self):
        before = space._legacy_allocations(REQUESTS)
        report = space.plan(REQUESTS + LARGE)
        self.assertEqual([a for a in report['allocations'] if a['owner'] in space.LEGACY_OWNERS], before)
        self.assertEqual([report['capacity'][k]['capacity_bytes'] for k in ('code', 'data', 'read_only')],
                         [106496, 86016, 20480])
        self.assertEqual([report['capacity'][k]['available_bytes'] for k in ('code', 'data', 'read_only')],
                         [6144, 16384, 15360])
        self.assertEqual(len(report['pages']), 52)
        for a in report['allocations']:
            self.assertEqual(a['va'] % a['align'], 0)
        self.assertEqual(space.plan(reversed(REQUESTS + LARGE)), report)

    def test_documented_beta62_owner_budget_table_fits(self):
        path = ROOT / 'tests/fixtures/nfl2k5_allocator_beta62_requests.json'
        requests = json.loads(path.read_text(encoding='utf-8'))
        for request in REQUESTS:
            self.assertIn(list(request), requests)
        report = space.plan(requests)
        self.assertEqual([report['capacity'][k]['available_bytes'] for k in ('code', 'data', 'read_only')],
                         [51072, 4096, 13312])

    def test_every_kind_exact_capacity_alignment_and_overflow(self):
        for kind, capacity in [('code', 98304), ('data', 81920), ('read_only', 16384)]:
            space.plan([('owner', kind, capacity, 4096)])
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'capacity'):
                space.plan([('owner', kind, capacity + 1, 4096)])
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'capacity'):
                space.plan([('alpha', kind, 1, 1), ('beta', kind, capacity - 1, 4096)])
        for request in [('a', 'code', True, 1), ('a', 'data', 1, 3), ('a', 'read_only', -1, 1),
                        ('a', 'rw', 1, 1), (space.DIRECTORY_OWNER, 'read_only', 1, 1)]:
            with self.assertRaises(ValueError):
                space.plan([request])
        with self.assertRaises(ValueError):
            space.plan([('owner', 'code', 1, 1)] * 2)
        with self.assertRaisesRegex(ValueError, 'count'):
            space.plan([(f'owner_{i}', 'code', 1, 1) for i in range(97)])

    def test_directory_capacity_does_not_depend_on_content_hash_entropy(self):
        requests = [("owner_" + hashlib.sha256(str(i).encode()).hexdigest()[:58], "code", 1, 1)
                    for i in range(95)]
        report = space.plan(requests)
        self.assertEqual(len(report['requests']), 96)
        plain = space._scale_directory(requests, dict(code_sha256='0' * 64, read_only_sha256='0' * 64))
        sealed = space._scale_directory(requests, dict(code_sha256=hashlib.sha256(b'code').hexdigest(),
                                                      read_only_sha256=hashlib.sha256(b'ro').hexdigest()))
        self.assertEqual(plain[:12], sealed[:12])
        self.assertEqual(plain[76:], sealed[76:])

    def test_cli_text_json_and_refusal_without_build_or_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'requests.json'
            path.write_text(json.dumps(REQUESTS + LARGE), encoding='utf-8')
            cmd = [sys.executable, str(ROOT / 'tools/nfl2k5_xbe_space.py'), 'plan', '--requests', str(path)]
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('No build performed', run.stdout)
            self.assertIn('6144 available', run.stdout)
            run = subprocess.run(cmd + ['--json'], capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(len(json.loads(run.stdout)['pages']), 52)
            path.write_text(json.dumps([['owner', 'data', 81921, 1]]), encoding='utf-8')
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 2)
            self.assertIn('capacity', run.stderr)
            self.assertEqual(run.stdout, '')
            self.assertEqual(list(Path(temp).iterdir()), [path])


class SyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = bytearray(synthetic())
        for at, va in space.DEBUG_POINTERS:
            struct.pack_into('<I', cls.retail, at, va)
        struct.pack_into("<II", cls.retail, 0x178, 0x10994, 1)
        cls.retail = bytes(cls.retail)
        pins = ExitStack()
        cls.addClassCleanup(pins.close)
        for module, name, value in (
            (space, 'METADATA_SHA256', space._sha(cls.retail[space.META_START:space.META_END])),
            (space, 'GEOMETRY_SHA256', space._sha(b''.join(cls.retail[space.TABLE + i*56:space.TABLE + i*56 + 36] for i in range(22)))),
            (space, 'LIB_SHA256', space._sha(cls.retail[space.LIB_START:space.LIB_END])),
            (space, 'DEBUG_SHA256', space._sha(cls.retail[space.DEBUG_START:space.DEBUG_END])),
            (storage, 'RETAIL_CONTENT_SHA256', space._sha(bytes(storage.RETAIL_SIZE))),
        ):
            pins.enter_context(patch.object(module, name, value))
        cls.grown, cls.receipt = space.apply(cls.retail, REQUESTS + LARGE)

    def test_legacy_directory_decodes_its_original_request_packing(self):
        # Such a request now selects v3 for a fresh build, but an existing v1
        # image must still decode and replay at its original VAs.
        requests = (("alpha", "code", 16, 16), ("nfl2k5_dynamic_kickoff_relocated", "data", 10, 4))
        with patch.object(space, "_needs_scaleout", return_value=False):
            legacy = space.apply(self.retail, requests)[0]
        self.assertEqual(space.status(legacy), "applied")
        self.assertEqual(space.layout(legacy)["allocations"], space._legacy_allocations(requests))
        self.assertEqual(space.apply(legacy, requests)[0], legacy)
        projected = space.plan(requests)
        fresh = space.apply(self.retail, requests, scaleout=True)[0]
        self.assertEqual(space.layout(fresh)["allocations"], projected["allocations"])

    def test_header_accounting_all_descriptors_and_runtime_permissions(self):
        image = XbeImage(self.grown)
        self.assertEqual(len(image.sections), space.SCALE_COUNT)
        feature = struct.unpack_from('<I', self.grown, 0x178)[0]
        self.assertEqual(image.read(feature, 16), self.retail[0x994:0x9A4])
        self.assertEqual(feature, 0x10FF0)
        self.assertEqual(self.grown[0xA10:space.META_COPY], self.retail[0xA10:space.META_COPY])
        self.assertLessEqual(space.META_START + (space.SCALE_COUNT + 1 - space.COUNT) * 56, 0xA10)
        self.assertLessEqual(space.DEBUG_COPY + space.DEBUG_END - space.DEBUG_START, space.LIB_COPY)
        self.assertEqual(self.grown[space.DEBUG_COPY:space.DEBUG_COPY + space.DEBUG_END-space.DEBUG_START],
                         self.retail[space.DEBUG_START:space.DEBUG_END])
        for old in XbeImage(self.retail).sections:
            new = image.section(old.start)
            self.assertEqual((old.start, old.size, old.raw, old.raw_size, old.flags, old.header),
                             (new.start, new.size, new.raw, new.raw_size, new.flags, new.header))
            for field in (20, 28, 32):
                old_pointer = struct.unpack_from('<I', self.retail, old.header + field)[0]
                new_pointer = struct.unpack_from('<I', self.grown, new.header + field)[0]
                self.assertEqual(new_pointer - old_pointer, space.META_DELTA)
                self.assertEqual(image.read(new_pointer, 2), XbeImage(self.retail).read(old_pointer, 2))
        for region in space.layout(self.grown)['regions']:
            section = image.section(region['va'], region['size'])
            self.assertEqual(section.writable, region['kind'] == 'data')
            self.assertEqual(section.executable, region['kind'] == 'code')
            head, tail = struct.unpack_from('<II', self.grown, section.header + 28)
            self.assertEqual(tail-head, 2 if region['size'] > 4096 else 0)
            self.assertEqual(image.read(head, 2), bytes(2))
            self.assertEqual(image.read(tail, 2), bytes(2))
        for section in _sections(self.grown):
            self.assertEqual(section_digest(self.grown, section), section.stored_digest)

    def test_sealed_code_ro_replay_and_changed_request_refusal(self):
        code = b'\x90' * (90 * 1024)
        grown, _ = space.install_code(self.grown, 'synthetic_scaleout', code)
        grown, _ = space.install_read_only(grown, 'synthetic_scaleout', b'R' * 1024)
        self.assertEqual(space.status(grown), 'applied')
        self.assertEqual(space.install_code(grown, 'synthetic_scaleout', code)[0], grown)
        self.assertEqual(space.install_read_only(grown, 'synthetic_scaleout', b'R' * 1024)[0], grown)
        self.assertEqual(space.apply(grown, reversed(REQUESTS + LARGE))[0], grown)
        self.assertEqual(space.apply(grown)[0], grown)
        with self.assertRaisesRegex(ValueError, 'differ'):
            space.apply(grown, REQUESTS)
        legacy, _ = space.apply(self.retail, REQUESTS)
        with self.assertRaisesRegex(ValueError, 'rebuild'):
            space.apply(legacy, REQUESTS, scaleout=True)
        with self.assertRaisesRegex(ValueError, 'foreign'):
            space.install_read_only(grown, 'synthetic_scaleout', b'Z' * 1024)
        with self.assertRaisesRegex(ValueError, 'exact'):
            space.install_code(grown, 'synthetic_scaleout', code[:-1])

    def test_corruption_and_resealed_unknown_bytes_refuse_before_mutation(self):
        offsets = [0x104, 0x108, 0x10C, 0x11C, 0x120, 0x14C, 0x150, 0x154,
                   0x178, 0x17C, space.META_COPY, space.SCALE_NAMES, space.DEBUG_COPY, space.LIB_COPY,
                   space.DIRECTORY + 12, space.SCALE_DIRECTORY, space.SCALE_DIRECTORY + 4095,
                   space.SCALE_DIRECTORY + 4096, space.SCALE_FILE_SIZE - 1,
                   space.DATA_RAW, space.EXT_FILE_SIZE]
        offsets += [space.META_START + i * 56 + field for i in range(space.SCALE_COUNT - space.COUNT)
                    for field in (0, 4, 8, 12, 16, 20, 24, 28, 32, 36)]
        for offset in offsets:
            bad = bytearray(self.grown)
            bad[offset] ^= 1
            original = bytes(bad)
            with self.subTest(offset=hex(offset)):
                self.assertEqual(space.status(bad), 'foreign')
                with self.assertRaises(ValueError):
                    space.apply(bad, REQUESTS + LARGE)
                self.assertEqual(bytes(bad), original)
        # Repinning the section SHA1 cannot bless a foreign owner byte.
        bad = bytearray(self.grown)
        bad[space.EXT_FILE_SIZE] ^= 1
        for section in XbeImage(bad).sections:
            bad[section.header+36:section.header+56] = space._digest(bad[section.raw:section.raw+section.raw_size])
        self.assertEqual(space.status(bad), 'foreign')
        for payload in (self.grown[:-1], self.grown + b'\0', self.grown[:4096]):
            self.assertEqual(space.status(payload), 'foreign')

    def test_every_page_and_child_is_recorded_in_manifest(self):
        recorder = Recorder(self.retail)
        recorder.observe(space, 'apply', self.retail, self.grown, self.receipt)
        spans = recorder.finish(self.grown)
        for reservation in space.reservations(self.grown):
            self.assertTrue(any(all(s[k] == reservation[k] for k in ('start', 'end', 'owner')) for s in spans), reservation)
        self.assertEqual(len([r for r in space.reservations(self.grown) if r['owner'] == space.OWNER]), 52)

    def test_music_both_orders_and_all_legacy_bytes_stay_identical(self):
        data = b'synthetic music metadata'
        first, _ = music.install(self.grown, data)
        first, _ = space.install_code(first, 'synthetic_scaleout', b'\x90' * 92160)
        second, _ = space.install_code(self.grown, 'synthetic_scaleout', b'\x90' * 92160)
        second, _ = music.install(second, data)
        self.assertEqual(first, second)
        self.assertEqual(music.unwrap(first)[1], data)
        self.assertEqual(space.status(music.unwrap(first)[0]), 'applied')
        self.assertEqual(music.install(first, data)[0], first)
        self.assertEqual(space.layout(first)['regions'][-1]['va'], music.VA)
        bad = bytearray(first); bad[music.RAW] ^= 1
        self.assertEqual(space.status(bad), 'foreign')
        for field in (0, 4, 8, 12, 16, 20, 24, 28, 32, 36):
            bad = bytearray(first)
            bad[space.scale_music_slots()[0] + field] ^= 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                music.install(bad, data)
            with self.subTest(field=field), self.assertRaises(ValueError):
                music.unwrap(bad)

    def test_writer_growth_replay_and_rollback_on_both_write_stages(self):
        helper = PublicTests()
        legacy, _ = space.apply(self.retail, REQUESTS)
        helper._writer(self.retail, self.grown)
        helper._writer(legacy, self.grown)
        helper._writer(self.grown, legacy)
        helper._writer(self.retail, self.grown, 'payload')
        helper._writer(self.retail, self.grown, 'directory')
        helper._writer(self.grown, self.grown, 'payload')

    @unittest.skipUnless(importlib.util.find_spec('unicorn'), 'Unicorn absent: bounded x86 page execution requires unicorn')
    def test_third_and_tenth_rx_pages_execute_and_write_rw(self):
        import unicorn as uc
        from unicorn import x86_const as x86
        layout = space.layout(self.grown)
        pages = [p for p in layout['pages'] if p['kind'] == 'code']
        target = next(a['va'] for a in layout['allocations'] if a['owner'] == 'synthetic_scaleout' and a['kind'] == 'data')
        owner = next(a for a in layout['allocations'] if a['owner'] == 'synthetic_scaleout' and a['kind'] == 'code')
        code = bytearray(b'\xcc' * owner['size'])
        for index, value in [(2, 0x33333333), (9, 0xAAAAAAAA)]:
            at = pages[index]['va'] - owner['va']
            code[at:at+11] = b'\xc7\x05' + struct.pack('<II', target, value) + b'\xc3'
        grown, _ = space.install_code(self.grown, 'synthetic_scaleout', bytes(code))
        for index, value in [(2, 0x33333333), (9, 0xAAAAAAAA)]:
            machine = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
            for p in layout['pages']:
                machine.mem_map(p['va'], 4096)
                machine.mem_write(p['va'], grown[p['raw']:p['raw']+4096])
                flags = XbeImage(grown).section(p['va']).flags
                perms = uc.UC_PROT_READ | (uc.UC_PROT_WRITE if flags & 1 else 0) | (uc.UC_PROT_EXEC if flags & 4 else 0)
                machine.mem_protect(p['va'], 4096, perms)
            stack, stop = 0x3000000, 0x3010000
            machine.mem_map(stack, 4096)
            machine.mem_map(stop, 4096, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
            machine.mem_write(stack, struct.pack('<I', stop))
            machine.reg_write(x86.UC_X86_REG_ESP, stack)
            machine.reg_write(x86.UC_X86_REG_EBX, 0x12345678)
            writes = []
            machine.hook_add(uc.UC_HOOK_MEM_WRITE, lambda _m, _a, va, size, val, _d: writes.append((va, size, val)))
            machine.emu_start(pages[index]['va'], stop, count=4)
            self.assertEqual(machine.reg_read(x86.UC_X86_REG_EIP), stop)
            self.assertEqual(machine.reg_read(x86.UC_X86_REG_ESP), stack + 4)
            self.assertEqual(machine.reg_read(x86.UC_X86_REG_EBX), 0x12345678)
            self.assertEqual(writes, [(target, 4, value)])
            self.assertEqual(bytes(machine.mem_read(target, 4)), struct.pack('<I', value))


@unittest.skipUnless(RETAIL.is_file(), f'private USA retail XBE absent: {RETAIL}')
class RetailTests(unittest.TestCase):
    def test_runtime_scorebug_reader_accepts_scaleout_and_still_validates_xbe(self):
        from types import SimpleNamespace
        from mod_editor.core import nfl2k5_scorebug_ingame as scene, nfl2k5_scorebug_resources as art
        full = compose(RETAIL.read_bytes(), scaleout=True)[0]
        # Isolate the XBE-size boundary from the unrelated 128 MiB art compiler.
        # The real runtime XBE validator and descriptor-backed file reads run.
        blob = b"resource fixture"
        entries = {"default.xbe": SimpleNamespace(size=len(full), byte_offset=0),
                   "vc_53450030/0": SimpleNamespace(size=len(blob), byte_offset=len(full))}
        with tempfile.TemporaryDirectory() as temp:
            path = (Path(temp) / "fixture.iso").resolve()
            path.write_bytes(full + blob)
            with patch.object(scene.layout.xc, "parse_xdvdfs", return_value=(entries, None)), \
                 patch.object(scene, "PACK_SIZE", len(blob)), \
                 patch.object(art, "runtime_pack_status", return_value="applied") as resources:
                self.assertEqual(scene.runtime_image_status(path), "applied")
                resources.assert_called_with(blob)
                bad = bytearray(full); bad[space.EXT_FILE_SIZE] ^= 1
                path.write_bytes(bad + blob)
                self.assertEqual(scene.runtime_image_status(path), "foreign")

    def test_special_before_after_scaleout_and_both_allocator_inputs(self):
        from mod_editor.core import nfl2k5_edge_rename as edge, nfl2k5_modern_positions as modern
        from mod_editor.core import nfl2k5_position_pools as pools, nfl2k5_depth_chart_rows as rows
        retail = RETAIL.read_bytes()
        prepared = retail
        for module in (edge, modern, pools):
            prepared = module.apply(prepared)[0]
        special_only = rows.apply(prepared)[0]
        first = rows.apply(space.apply(prepared, REQUESTS, scaleout=True)[0])[0]
        second = space.apply(special_only, REQUESTS, scaleout=True)[0]
        self.assertEqual(first, second)
        self.assertEqual(rows.status(first), 'applied')
        self.assertEqual(first[storage.RETAIL_RAW:storage.FILE_SIZE],
                         special_only[storage.RETAIL_RAW:storage.FILE_SIZE])

    def test_full_legacy_owner_union_large_owner_both_orders_and_retained_hooks(self):
        retail = RETAIL.read_bytes()
        legacy, _ = compose(retail)
        first, _ = compose(retail, scaleout=True, extra_requests=LARGE)
        second, _ = compose(retail, reverse=True, scaleout=True, extra_requests=LARGE)
        self.assertEqual(first, second)
        old = {(a['owner'], a['kind']): a for a in space.layout(legacy)['allocations']}
        for a in space.layout(first)['allocations']:
            if (a['owner'], a['kind']) in old:
                self.assertEqual(a, old[a['owner'], a['kind']])
                self.assertEqual(first[a['raw']:a['raw']+a['size']], legacy[a['raw']:a['raw']+a['size']])
        self.assertEqual(first[0xA10:space.META_COPY], legacy[0xA10:space.META_COPY])
        from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as kickoff
        self.assertEqual(kickoff.status(first), 'applied')
        self.assertEqual(kickoff.apply(first)[0], first)


if __name__ == '__main__':
    unittest.main()
