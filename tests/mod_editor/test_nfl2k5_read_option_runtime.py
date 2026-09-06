"""Standalone read-option authoring, byte ownership and refusal proofs."""
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
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / 'tools'):
    sys.path.insert(0, str(entry))
from mod_editor.core import nfl2k5_read_option_runtime as patch
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

EXTRACT = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)'
XBE = EXTRACT / 'default.xbe'


def compiled_reads():
    if not (EXTRACT / 'vc_53450030/0').is_file():
        raise unittest.SkipTest('retail extracted PLAY archive missing')
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    from mod_editor.core import nfl2k5_playbook_pack as pack
    with OuterImage(EXTRACT) as archive:
        raw = archive.read_entry(BOOK_ENTRIES['MIN'])
    compiled = pack.apply_pack_to_resource(raw, pack.load_pack(ROOT / 'data/playbooks/softdrink_option.2k5book'))
    return raw, compiled


def repin(payload):
    out = bytearray(payload)
    for section in _sections(out):
        out[section.header_offset+36:section.header_offset+56] = section_digest(out, section)
    return bytes(out)


class TableTests(unittest.TestCase):
    def test_empty_table_exact_budget_and_complete_budget_plan(self):
        table, receipt = patch.compile_intent_table()
        self.assertEqual(patch.validate_intent_table(table), 0)
        self.assertEqual(receipt['capacity'], 2)
        self.assertEqual(sum(row[2] for row in patch.REQUESTS), 1024)
        self.assertNotIn('data', [row[1] for row in patch.REQUESTS])
        self.assertLessEqual(len(patch.assembly.CODE), patch.CODE_SIZE)
        requests = json.loads((ROOT / 'tests/fixtures/nfl2k5_allocator_beta62_requests.json').read_text())
        self.assertEqual([tuple(row) for row in requests if row[0] == patch.OWNER], list(patch.REQUESTS))
        self.assertTrue(space.plan(requests))

    def test_invalid_table_headers_fields_padding_and_duplicates(self):
        empty = patch.compile_intent_table()[0]
        for offset, value in ((0, 0), (4, 2), (8, 3), (12, 1), (63, 1)):
            bad = bytearray(empty); bad[offset] = value
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                patch.validate_intent_table(bytes(bad))
        for offset, back, read, receiver, flags in ((0, 10, 2, 0, 0), (0x3405, 10, 2, 0, 0),
                (0x3404, 8, 2, 0, 0), (0x3404, 10, 11, 0, 0), (0x3404, 10, 2, 6, 0), (0x3404, 10, 2, 7, 1)):
            row = patch.RECORD.pack(1, offset, 2, 3, 4, back, read, receiver, flags)
            bad = (patch.HEADER.pack(b'RDO1', 1, 1, 0) + row).ljust(64, b'\0')
            with self.assertRaises(ValueError): patch.validate_intent_table(bad)

    def test_real_option_pack_pairing_native_speed_exclusion_and_edge_intent(self):
        raw, compiled = compiled_reads()
        pairs = [(compiled.replacement, compiled.report)]
        table, receipt = patch.compile_intent_table(pairs)
        self.assertEqual(patch.validate_intent_table(table), 2)
        self.assertEqual({row['play_index'] for row in receipt['records']}, {155, 157})
        self.assertEqual({row['authored_read_slot'] for row in receipt['records']}, {1})
        self.assertEqual(patch.compile_intent_table(pairs), (table, receipt))
        with self.assertRaisesRegex(ValueError, 'pairing'): patch.compile_intent_table([(raw, compiled.report)])
        with self.assertRaisesRegex(ValueError, 'Duplicate'): patch.compile_intent_table(pairs * 2)
        wrong = copy.deepcopy(compiled.report); wrong['option_intent']['schema'] = 'v2'
        with self.assertRaisesRegex(ValueError, 'versioned'): patch.compile_intent_table([(compiled.replacement, wrong)])
        wrong = copy.deepcopy(compiled.report); wrong['option_intent']['records'][-1]['play_index'] = 0
        with self.assertRaises(ValueError): patch.compile_intent_table([(compiled.replacement, wrong)])

    def test_reproducible_assembler(self):
        if not shutil.which('as'):
            self.skipTest('GNU ELF32 assembler absent; runtime has no assembler dependency')
        probe = subprocess.run(['as', '--version'], capture_output=True, text=True)
        if probe.returncode or 'GNU assembler' not in probe.stdout:
            self.skipTest('platform assembler is not GNU as')
        from nfl2k5_read_option_runtime_assemble import generate, TARGET
        self.assertEqual(generate(), TARGET.read_text())

    def test_changed_native_argument_cannot_alias_a_committed_decision(self):
        from mod_editor.core import nfl2k5_play_library as library, nfl2k5_play_codec as codec
        _, compiled = compiled_reads()
        out = bytearray(compiled.replacement)
        descriptor = 0x3404+155*96
        nodes = library.play_chains(out[32:], 155)[1][0][1]
        changed = codec.Node.from_bytes(nodes[2])
        changed.operands[6] = 0
        field = descriptor+4
        start = field+struct.unpack_from('<i', out, 32+field)[0]-1
        out[32+start+16:32+start+24] = changed.to_bytes()
        receipt = copy.deepcopy(compiled.report)
        receipt['replacement_sha256'] = hashlib.sha256(out).hexdigest()
        with self.assertRaisesRegex(ValueError, 'argument 13'):
            patch.compile_intent_table([(bytes(out), receipt)])


@unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE extraction missing')
class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()  # approximately 12 MiB, never a disc/pack
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('local XBE does not match the pinned USA evidence')
        cls.patched, cls.receipt = patch.apply(cls.retail)

    def test_replay_exact_receipt_sections_and_hook_span(self):
        self.assertEqual(patch.status(self.retail), 'retail')
        self.assertEqual(patch.status(self.patched), 'applied')
        self.assertIs(patch.apply(self.patched)[0], self.patched)
        self.assertEqual(patch.apply(self.patched)[1]['changed_bytes'], 0)
        expected = sum(a != b for a, b in zip(self.retail, self.patched)) + len(self.patched)-len(self.retail)
        self.assertEqual(self.receipt['changed_bytes'], expected)
        image = XbeImage(self.patched)
        for edit in self.receipt['edits']:
            self.assertEqual(image.read(int(edit['va'], 0), edit['size']), bytes.fromhex(edit['after']))
        for section in _sections(self.patched):
            self.assertEqual(section_digest(self.patched, section), section.stored_digest)

    def test_paired_table_replay_and_changed_table_refusal(self):
        _, compiled = compiled_reads()
        table = patch.compile_intent_table([(compiled.replacement, compiled.report)])[0]
        output, _ = patch.apply(self.retail, intent_table=table)
        self.assertIs(patch.apply(output)[0], output)
        with self.assertRaisesRegex(ValueError, 'rebuild'):
            patch.apply(output, intent_table=patch.compile_intent_table()[0])

    def test_mixed_hooks_dependencies_code_tables_and_partial_union_refuse(self):
        image = XbeImage(self.patched)
        places = patch.allocations(self.patched)
        for va in (0x1AF191, 0x1AF210, 0x120960, 0xA9B4B0, places['code']['va'], places['read_only']['va']):
            bad = bytearray(self.patched); bad[image.offset(va)] ^= 1
            bad = repin(bad)
            with self.subTest(va=hex(va)):
                self.assertEqual(patch.status(bad), 'foreign')
                with self.assertRaises(ValueError): patch.apply(bad)
        partial, _ = space.apply(self.retail, (patch.REQUESTS[0],), scaleout=True)
        with self.assertRaisesRegex(ValueError, 'allocation'): patch.apply(partial)
        for bad in (b'', b'XBEH', None):
            self.assertEqual(patch.status(bad), 'foreign')
            with self.assertRaises((ValueError, TypeError)): patch.apply(bad)

    def test_defense_native_pitch_and_ball_transfer_instructions_are_untouched(self):
        before, after = XbeImage(self.retail), XbeImage(self.patched)
        for va, size in ((0x2FE190, 0x340), (0x2FD700, 0xE90), (0x2FF7C0, 0x230),
                         (0x300B00, 0x200), (0x1ACE40, 0x768), (0x19BAE0, 0x80)):
            self.assertEqual(before.read(va, size), after.read(va, size), hex(va))

    def test_manifest_recorder_owns_complete_rx_ro_and_live_hook(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        recorder.observe(patch, 'apply', self.retail, self.patched, self.receipt)
        spans = recorder.spans
        self.assertTrue(any(int(row['start'], 0) <= 0x1AF191 < int(row['end'], 0)
                            and row['owner'] == patch.OWNER for row in spans))


if __name__ == '__main__':
    unittest.main()
