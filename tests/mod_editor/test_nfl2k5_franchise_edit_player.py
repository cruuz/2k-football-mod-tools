"""Standalone integrity, instruction census, ownership and CLI proofs."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_edit_player as edit
from mod_editor.core import nfl2k5_position_row as position
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, ReservationManifest, DEFAULT_MANIFEST
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit


class PublicTests(unittest.TestCase):
    def test_budget_and_all_request_unions(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        rows = json.loads((ROOT / 'tests/fixtures/nfl2k5_allocator_beta62_requests.json').read_text())
        self.assertEqual([tuple(row) for row in rows if row[0] == edit.OWNER], list(edit.REQUESTS))
        self.assertTrue(set(edit.REQUESTS) <= set(REQUESTS))
        self.assertTrue(set(edit.REQUESTS) <= set(space.dormant_union()))
        plan = space.plan(rows, scaleout=True)
        self.assertEqual(plan['capacity']['read_only']['available_bytes'], 2968)  # beta 66: Broadcast camera v6 takes 320 RO (v5 took 80); beta 65: the accelerated clock's 8 RO bytes (16-aligned); beta 63 stack: 7400 alone; playbook pair 4096 RO
        self.assertEqual(len(edit.read_only_bytes()), 704)
        self.assertEqual(edit.EDIT_ROW[2:5], (1, 0, 0))
        self.assertEqual(edit.EDIT_ROW[5:], (1,) * 10)

    def test_capability_schema_commands_and_new_evidence_files(self):
        from mod_editor.capabilities import validate_registry as registry
        cap = json.loads((ROOT / 'docs/mod_editor/nfl2k5_franchise_edit_player_capability.json').read_text())
        candidate = json.loads(registry.DEFAULT_REGISTRY.read_text())
        candidate['capabilities'] = sorted([c for c in candidate['capabilities'] if c['id'] != cap['id']] + [cap], key=lambda c: c['id'])
        registry.validate_data(candidate, check_files=False)
        for path in cap['evidence'] + cap['runtime']['evidence'] + [cap['backend']['module']]:
            registry._local_path(path, cap['id'])
        for command in (cap['backend']['command'], cap['validation_command']):
            registry._local_path(registry._command_module(command, cap['id']), cap['id'])
        self.assertEqual(cap['runtime']['status'], 'not-tested')
        self.assertFalse(cap['gui']['default_enabled'])
        self.assertIn('Retail', edit.HELP_TEXT)
        self.assertIn('Patch', edit.HELP_TEXT)


class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.result, cls.receipt = edit.apply(cls.retail)
        cls.owned = edit.allocation(cls.result)

    def assert_refused(self, payload):
        digest = hashlib.sha256(payload).digest()
        self.assertEqual(edit.status(payload), 'foreign')
        with mock.patch.object(space, 'apply', side_effect=AssertionError('allocator before refusal')), \
             mock.patch.object(space, 'install_read_only', side_effect=AssertionError('table write before refusal')), \
             mock.patch.object(position, 'apply', side_effect=AssertionError('dependency before refusal')):
            with self.assertRaises(ValueError):
                edit.apply(payload)
        self.assertEqual(hashlib.sha256(payload).digest(), digest)

    def test_status_replay_receipt_and_permissions(self):
        self.assertEqual(edit.status(self.retail), 'retail')
        self.assertEqual(edit.status(self.result), 'applied')
        same, receipt = edit.apply(self.result)
        self.assertIs(same, self.result)
        self.assertEqual(receipt['changed_bytes'], 0)
        self.assertEqual(position.status(self.result), 'applied')
        self.assertEqual(self.receipt['changed_bytes'], sum(a != b for a, b in zip(self.retail, self.result)) + len(self.result) - len(self.retail))
        self.assertEqual(self.receipt['after_sha256'], hashlib.sha256(self.result).hexdigest())
        self.assertFalse(self.receipt['runtime_witnessed'])
        self.assertEqual((self.receipt['code_bytes'], self.receipt['rw_bytes'], self.receipt['ro_bytes']), (0, 0, 704))
        image = XbeImage(self.result)
        self.assertFalse(image.section(self.owned['va']).writable)
        self.assertFalse(image.section(self.owned['va']).executable)
        for row in self.receipt['edits']:
            self.assertEqual(image.read(int(row['va'], 0), row['size']).hex(), row['after'])
        self.assertTrue(all(s.stored_digest == section_digest(self.result, s) for s in _sections(self.result)))

    def test_original_actions_unchanged_and_appended_action_reuses_retail_arm(self):
        image, result = XbeImage(self.retail), XbeImage(self.result)
        content = edit.read_only_bytes()
        self.assertEqual(content[:600], image.read(edit.ROWS_VA, 600))
        self.assertEqual(content[660:700], image.read(0x2B8D08, 40))
        self.assertEqual(struct.unpack('<I', content[700:])[0], 0x2B8AB6)
        self.assertEqual(result.read(edit.ROWS_VA, 600), image.read(edit.ROWS_VA, 600))
        self.assertEqual(result.read(edit.EDIT_ARM_VA, 13), image.read(edit.EDIT_ARM_VA, 13))
        self.assertEqual(result.read(0x35F6C0, 45), image.read(0x35F6C0, 45))

    def test_instruction_census_covers_every_stack_return_and_row_reference(self):
        try:
            import capstone as c
            from capstone import x86_const as x
        except ImportError:
            self.skipTest('instruction census requires Capstone')
        dis = c.Cs(c.CS_ARCH_X86, c.CS_MODE_32); dis.detail = True
        instructions = list(dis.disasm(XbeImage(self.retail).read(edit.POPUP_VA, 0x95C), edit.POPUP_VA))
        returns = [i.address for i in instructions if i.mnemonic == 'add' and i.op_str == 'esp, 0xa4']
        self.assertEqual(returns, list(edit.EPILOGUES))
        row_references = [i.address for i in instructions for op in i.operands
                          if op.type == x.X86_OP_MEM and edit.ROWS_VA <= op.mem.disp < edit.ROWS_VA + 600]
        self.assertEqual(set(row_references), {va for va, _ in edit.ROW_LOADS} | {0x2B8584})
        by_address = {i.address: i for i in instructions}
        for _, va, before, after in edit.sites(self.owned['va']):
            self.assertEqual(bytes(by_address[va].bytes), before)
            self.assertEqual(len(before), len(after))
            decoded = list(dis.disasm(after, va))
            self.assertEqual(len(decoded), 1)
            self.assertEqual(decoded[0].size, len(after))

    def test_every_site_refuses_corruption_and_partial_installation(self):
        for label, va, before, after in edit.sites(self.owned['va']):
            with self.subTest(label=label):
                self.assert_refused(repin_edit(self.result, va, before))
                self.assert_refused(repin_edit(self.retail, va, bytes([before[0] ^ 1])))
        self.assert_refused(repin_edit(self.result, self.owned['va'], b'\x01'))
        for va in (position.LIST_CREATED_FACE_VA, position.LIST_REAL_FACE_VA):
            self.assert_refused(repin_edit(self.result, va, position.RETAIL_LIST))

    def test_prerequisites_including_back_suppression_and_position_previous_are_pinned(self):
        for va, size, _ in edit.GUARDS:
            with self.subTest(guard=hex(va)):
                at = va + size - 1
                old = XbeImage(self.result).read(at, 1)[0]
                self.assert_refused(repin_edit(self.result, at, bytes([old ^ 1])))
        self.assert_refused(repin_edit(self.result, 0x562810 + 0x38, b'\x00'))
        self.assert_refused(repin_edit(self.result, edit.EDIT_LABEL_VA, b'\x00'))

    def test_preallocation_position_dependency_and_missing_owner(self):
        reserved = space.apply(self.retail, edit.REQUESTS, scaleout=True)[0]
        self.assertEqual(edit.status(reserved), 'retail')
        self.assertEqual(edit.apply(reserved)[0], self.result)
        self.assertEqual(edit.apply(position.apply(self.retail)[0])[0], self.result)
        missing = space.apply(self.retail, (('test_other', 'read_only', 16, 16),), scaleout=True)[0]
        with mock.patch.object(position, 'apply', side_effect=AssertionError('dependency before refusal')):
            with self.assertRaisesRegex(ValueError, 'complete Contracts editor owner union'):
                edit.apply(missing)

    def test_exact_detour_without_complete_mycareer_or_playlist_is_refused(self):
        from mod_editor.core import nfl2k5_my_career_mode as career, nfl2k5_music_playlist as playlist
        seed = space.apply(self.retail, edit.REQUESTS + career.REQUESTS + playlist.REQUESTS, scaleout=True)[0]
        for owner, hook in ((career, 0x6E390), (playlist, 0x6E4E0)):
            installed = owner.apply(seed)[0]
            size = 10 if owner is career else 5
            self.assert_refused(repin_edit(seed, hook, XbeImage(installed).read(hook, size)))
            both = edit.apply(installed)[0]
            self.assertEqual(owner.status(both), 'applied')
            self.assertEqual(edit.status(both), 'applied')

    def test_sealed_foreign_owned_table_is_still_refused(self):
        seed = space.apply(self.retail, edit.REQUESTS, scaleout=True)[0]
        seed = position.apply(seed)[0]
        bad = bytearray(edit.read_only_bytes()); bad[600 + 8] = 0
        wrong = space.install_read_only(seed, edit.OWNER, bytes(bad))[0]
        wrong = edit.rdata.apply(wrong, edit.sites(edit.allocation(wrong)['va']), edit.OWNER)[0]
        self.assertEqual(space.status(wrong), 'applied')
        self.assert_refused(wrong)

    def test_manifest_recorder_owns_all_instructions_and_table(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        recorder.observe(edit, 'apply', self.retail, self.result, self.receipt)
        spans = recorder.finish(self.result)
        for row in self.receipt['edits']:
            va, size = int(row['va'], 0), row['size']
            self.assertTrue(any(s['owner'] == edit.OWNER and int(s['start'], 0) <= va
                                and va + size <= int(s['end'], 0) for s in spans), row['label'])
        self.assertTrue(any(s['owner'] == space.OWNER for s in recorder.spans))

    def test_cli_status_apply_exclusive_output_and_bounded_input(self):
        with tempfile.TemporaryDirectory(prefix='contracts-editor-') as temp:
            folder = Path(temp).resolve()
            source, target = folder/'source.xbe', folder/'patched.xbe'
            source.write_bytes(self.retail)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(edit.main(['status', str(source)]), 0)
            self.assertEqual(json.loads(out.getvalue())['status'], 'retail')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(edit.main(['apply', str(source), str(target)]), 0)
            self.assertEqual(target.read_bytes(), self.result)
            with self.assertRaises(FileExistsError):
                edit.main(['apply', str(source), str(target)])
            self.assertEqual(target.read_bytes(), self.result)
            self.assertEqual(source.read_bytes(), self.retail)
            with source.open('wb') as stream:
                stream.truncate(edit.MAX_XBE_BYTES + 1)
            with self.assertRaisesRegex(ValueError, 'at most 16 MiB'):
                edit.main(['status', str(source)])


if __name__ == '__main__':
    unittest.main()
