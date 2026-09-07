"""Standalone QB spy writer, pairing, ownership and manifest proofs."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / 'tools'):
    sys.path.insert(0, str(entry))
from mod_editor.core import nfl2k5_qb_spy_runtime as spy
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
EXTRACT = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)'
XBE = EXTRACT / 'default.xbe'


def compiled_spy():
    if not (EXTRACT / 'vc_53450030/0').is_file():
        raise unittest.SkipTest('retail extracted PLAY archive missing')
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    from mod_editor.core import nfl2k5_playbook_inspector as inspector
    from mod_editor.core import nfl2k5_play_library as library
    from mod_editor.core import nfl2k5_formation_play_writer as writer
    with OuterImage(EXTRACT) as archive:
        raw = archive.read_entry(BOOK_ENTRIES['ATL'])
    book = inspector.parse_playbook_resource(raw, asset_id='book:ATL')
    donor, fallback = library.spy_fallback(book, raw[32:], 23, 5, 4)
    request = writer.PlayCreateRequest('book:ATL', donor, 'SD QB Spy',
        tuple(tuple((op, tuple(v)) for op, v in fallback) if s == 5 else None for s in range(11)), spy_slots=(5,))
    link = writer.FormationLinkRequest('book:ATL', 23, len(book.plays), 3)
    compiled = writer.compile_formation_play_creations(raw, play_requests=[request], link_requests=[link])
    return raw, compiled


class TableTests(unittest.TestCase):
    def test_empty_versioned_table_and_exact_budget(self):
        table, receipt = spy.compile_intent_table()
        self.assertEqual(spy.validate_intent_table(table), 0)
        self.assertEqual(receipt['capacity'], 31)
        self.assertEqual(spy.CODE_SIZE, 0x800)
        self.assertEqual(spy.TABLE_SIZE, 0x200)
        self.assertEqual(spy.DATA_SIZE, 0x300)
        self.assertLessEqual(len(spy.assembly.CODE), spy.CODE_SIZE)
        budgets = json.loads((ROOT / 'tests/fixtures/nfl2k5_allocator_beta62_requests.json').read_text())
        self.assertEqual(sorted(tuple(r) for r in budgets if r[0] == spy.OWNER), sorted(spy.REQUESTS))
        plan = space.plan(budgets)
        self.assertTrue(plan)

    def test_foreign_header_padding_version_rows_and_capacity(self):
        empty = spy.compile_intent_table()[0]
        for offset, value in ((0, 0), (4, 2), (8, 32), (12, 1), (511, 1)):
            bad = bytearray(empty); bad[offset] = value
            with self.assertRaises(spy.QbSpyError): spy.validate_intent_table(bytes(bad))
        for pi, slot, version in ((270, 5, 1), (1, 11, 1), (1, 5, 2)):
            bad = spy.HEADER.pack(b'QBS1', 1, 1, 0) + spy.RECORD.pack(1, pi, slot, version, 2, 3)
            with self.assertRaises(spy.QbSpyError): spy.validate_intent_table(bad.ljust(512, b'\0'))

    def test_assembler_reproduces_shipped_bytes(self):
        from _gnu_elf32_as import gnu_elf32_as
        if not gnu_elf32_as():
            self.skipTest('GNU ELF32 as is absent; runtime application does not require it')
        from nfl2k5_qb_spy_runtime_assemble import generate, TARGET
        self.assertEqual(generate(), TARGET.read_text())

    def test_native_authoring_receipt_compiles_and_refuses_stale_pair(self):
        raw, compiled = compiled_spy()
        table, receipt = spy.compile_intent_table([(compiled.replacement, compiled.report)])
        self.assertEqual(spy.validate_intent_table(table), 1)
        self.assertEqual(receipt['records'][0]['play_index'], 254)
        self.assertEqual(receipt['records'][0]['slot'], 5)
        self.assertEqual(spy.compile_intent_table([(compiled.replacement, compiled.report)])[0], table)
        with self.assertRaisesRegex(spy.QbSpyError, 'pairing'):
            spy.compile_intent_table([(raw, compiled.report)])
        with self.assertRaisesRegex(spy.QbSpyError, 'Duplicate'):
            spy.compile_intent_table([(compiled.replacement, compiled.report)] * 2)
        bad = copy.deepcopy(compiled.report); bad['spy_intent']['schema'] = 'v2'
        with self.assertRaisesRegex(spy.QbSpyError, 'versioned'):
            spy.compile_intent_table([(compiled.replacement, bad)])
        bad = copy.deepcopy(compiled.report); bad['spy_intent']['records'][0]['slot'] = 11
        with self.assertRaisesRegex(spy.QbSpyError, 'play/slot'):
            spy.compile_intent_table([(compiled.replacement, bad)])
        self.assertFalse(compiled.report['spy_intent']['records'][0]['runtime_available'])


@unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE extraction missing')
class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('local XBE is not the pinned USA retail evidence')
        cls.patched, cls.receipt = spy.apply(cls.retail)

    def test_install_replay_digests_and_exact_receipt(self):
        self.assertEqual(spy.status(self.retail), 'retail')
        self.assertEqual(spy.status(self.patched), 'applied')
        replay, receipt = spy.apply(self.patched)
        self.assertEqual(replay, self.patched)
        self.assertEqual(receipt['status'], 'already_applied')
        self.assertEqual(receipt['changed_bytes'], 0)
        self.assertEqual(self.receipt['changed_bytes'], sum(a != b for a, b in zip(self.retail, self.patched)) + len(self.patched)-len(self.retail))
        for s in _sections(self.patched): self.assertEqual(section_digest(self.patched, s), s.stored_digest)

    def test_module_copy_recipe_refuses_existing_output_and_oversized_input(self):
        with tempfile.TemporaryDirectory(prefix='spy-copy-') as directory:
            root = Path(directory).resolve()
            output = root / 'spy.xbe'
            command = [sys.executable, '-m', 'mod_editor.core.nfl2k5_qb_spy_runtime', str(XBE), str(output)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), self.patched)
            self.assertEqual(json.loads(result.stdout)['tier'], 'zone-man-rush')
            original = hashlib.sha256(output.read_bytes()).hexdigest()
            replay = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(replay.returncode, 0)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), original)
            oversized = root / 'disc-by-mistake.iso'
            with oversized.open('wb') as source: source.truncate(12_300_289)
            refused = root / 'refused.xbe'
            result = subprocess.run(command[:2]+['mod_editor.core.nfl2k5_qb_spy_runtime', str(oversized), str(refused)],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('bounded XBE', result.stderr)
            self.assertFalse(refused.exists())

    def test_authored_table_replay_preserves_omitted_and_refuses_reconfiguration(self):
        _, compiled = compiled_spy()
        table, _ = spy.compile_intent_table([(compiled.replacement, compiled.report)])
        installed, receipt = spy.apply(self.retail, intent_table=table)
        self.assertEqual(receipt['authored_spies'], 1)
        self.assertEqual(spy.apply(installed)[0], installed)
        self.assertEqual(spy.apply(installed, intent_table=table)[0], installed)
        with self.assertRaisesRegex(spy.QbSpyError, 'Different'):
            spy.apply(installed, intent_table=spy.compile_intent_table()[0])

    def test_mixed_hook_code_ro_state_and_dependencies_refuse_before_mutation(self):
        locations = spy.allocations(self.patched)
        image = XbeImage(self.patched)
        spans = [image.offset(va+i) for _name, va, old, _new in spy.sites(locations['code']['va'])
                 for i in range(len(old))]
        spans += [a['raw'] for a in locations.values()]
        spans += [image.offset(0x1A4170)]
        for offset in spans:
            bad = bytearray(self.patched); bad[offset] ^= 1
            for section in _sections(bad):
                bad[section.header_offset+36:section.header_offset+56] = section_digest(bad, section)
            original = bytes(bad)
            self.assertEqual(spy.status(original), 'foreign', hex(offset))
            with self.assertRaises(ValueError): spy.apply(original)
            self.assertEqual(bytes(bad), original)
        # Allocator-sealed isolated RO and code installs still are mixed owners.
        base, _ = space.apply(self.retail, spy.REQUESTS, scaleout=True)
        partial, _ = space.install_read_only(base, spy.OWNER, spy.compile_intent_table()[0])
        self.assertEqual(spy.status(partial), 'foreign')
        with self.assertRaises(ValueError): spy.apply(partial)

    def test_incomplete_union_requires_rebuild(self):
        base, _ = space.apply(self.retail, (("other_spy_probe", 'code', 16, 16),), scaleout=True)
        with self.assertRaisesRegex(spy.QbSpyError, 'allocation missing'): spy.apply(base)

    def test_older_immutable_request_requires_base_rebuild(self):
        old_requests = tuple((owner, kind, 1536 if kind == 'code' else size, align)
                             for owner, kind, size, align in spy.REQUESTS)
        old, _ = space.apply(self.retail, old_requests, scaleout=True)
        self.assertEqual(spy.status(old), 'foreign')
        with self.assertRaisesRegex(spy.QbSpyError, 'rebuild from base'):
            spy.apply(old)

    def test_existing_qb_spy_flag_drives_all_four_status_dictionaries(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt, mod_build
        from tests.mod_editor.test_nfl2k5_xbe_space import image_with_xbe
        with tempfile.TemporaryDirectory(prefix='spy-status-') as directory:
            root = Path(directory).resolve()
            for image in (False, True):
                source = root / ('source.iso' if image else 'source.xbe')
                target = root / ('output.iso' if image else 'output.xbe')
                source.write_bytes(image_with_xbe(self.retail) if image else self.retail)
                source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                self.assertEqual(tt.read_any(source)['qb_spy'], 'retail')
                result = (tt.write_image_copy if image else tt.write_xbe_copy)(
                    source, target, catch_slider=False, qb_spy=True)
                self.assertEqual(result['qb_spy'], 'applied')
                self.assertEqual(tt.read_any(target)['qb_spy'], 'applied')
                payload = mod_build._xbe_bytes(target)
                self.assertEqual(spy.allocations(payload)['code']['size'], 2048)
                self.assertEqual(spy.apply(payload)[1]['tier'], 'zone-man-rush')
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash)

    def test_complete_union_both_orders_equal_and_replay(self):
        from tests.nfl2k5_allocator_stack import compose
        forward, _ = compose(self.retail)
        reverse, _ = compose(self.retail, reverse=True)
        self.assertEqual(forward, reverse)
        self.assertEqual(spy.status(forward), 'applied')

    def test_manifest_records_hooks_all_three_allocations_and_zero_state(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        base, receipt = space.apply(self.retail, spy.REQUESTS, scaleout=True)
        recorder.observe(space, 'apply', self.retail, base, receipt)
        installed, receipt = spy.apply(base)
        recorder.observe(spy, 'apply', base, installed, receipt)
        spans = recorder.finish(installed)
        for reservation in spy.reservations(installed):
            self.assertTrue(any(row['owner'] == spy.OWNER and int(row['start'], 0) <= int(reservation['start'], 0)
                                and int(row['end'], 0) >= int(reservation['end'], 0) for row in spans), reservation)
        for kind, a in spy.allocations(installed).items():
            image = XbeImage(installed)
            self.assertEqual(image.runtime_writable(a['va'], a['size']), kind == 'data')
            self.assertNotEqual(image.section(a['va']).name, '.text')
            self.assertEqual(bool(image.section(a['va']).flags & 4), kind == 'code')


if __name__ == '__main__': unittest.main()
