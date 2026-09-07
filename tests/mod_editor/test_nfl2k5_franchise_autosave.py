"""Standalone patch integrity and owner proofs, without a disc build."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_autosave as a
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from tests.nfl2k5_franchise_autosave_fixture import XBE


class PublicTests(unittest.TestCase):
    def test_budget_registry_and_reproducible_template(self):
        rows = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([tuple(r) for r in rows if r[0] == a.OWNER], list(a.REQUESTS))
        self.assertLessEqual(len(a.assembly.CODE), a.CODE_SIZE)
        self.assertEqual(len(a.read_only_bytes()), a.RO_SIZE)
        self.assertGreaterEqual(len(a.GUARDS), 20)
        from tests.nfl2k5_allocator_stack import REQUESTS
        self.assertTrue(set(a.REQUESTS) <= set(REQUESTS))

    def test_capability_handoff_schema_commands_and_own_file_checks(self):
        from mod_editor.capabilities import validate_registry as registry
        cap = json.loads((ROOT / 'docs/mod_editor/nfl2k5_franchise_autosave_capability.json').read_text())
        # This checkout lacks unrelated baseline evidence (apf_audio.md, etc.).
        # Validate the whole merged schema, then strictly resolve EVERY new
        # reference. Do not claim the baseline's missing files passed checks.
        candidate = json.loads(registry.DEFAULT_REGISTRY.read_text())
        candidate['capabilities'] = sorted(
            [c for c in candidate['capabilities'] if c['id'] != cap['id']] + [cap], key=lambda c: c['id'])
        registry.validate_data(candidate, check_files=False)
        for path in cap['evidence'] + cap['runtime']['evidence'] + [cap['backend']['module']]:
            registry._local_path(path, cap['id'])
        self.assertEqual(registry._command_module(cap['backend']['command'], cap['id']), cap['backend']['module'])
        command = registry._command_module(cap['validation_command'], cap['id'])
        self.assertIsNotNone(command)
        registry._local_path(command, cap['id'])
        self.assertEqual(cap['runtime']['status'], 'not-tested')
        self.assertIn('Retail', a.HELP_TEXT)
        self.assertIn('Patch', a.HELP_TEXT)


@unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe is absent")
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail USA XBE evidence pin differs")
        cls.result, cls.receipt = a.apply(cls.retail)

    def corrupt(self, va, payload=None):
        buf = bytearray(self.result if payload is None else payload)
        buf[XbeImage(buf).offset(va, 1)] ^= 1
        for s in _sections(buf):
            buf[s.header_offset+36:s.header_offset+56] = section_digest(buf, s)
        return bytes(buf)

    def test_replay_full_receipts_and_permissions(self):
        self.assertEqual(a.status(self.retail), "retail")
        self.assertEqual(a.status(self.result), "applied")
        same, receipt = a.apply(self.result)
        self.assertEqual(same, self.result)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(self.receipt["changed_bytes"], sum(x != y for x, y in zip(self.retail, self.result)) + len(self.result)-len(self.retail))
        im = XbeImage(self.result)
        rows = a.allocations(self.result)
        self.assertFalse(im.section(rows["code"]["va"]).writable)
        self.assertTrue(im.section(rows["code"]["va"]).executable)
        self.assertTrue(im.section(rows["data"]["va"]).writable)
        self.assertFalse(im.section(rows["read_only"]["va"]).writable)
        self.assertEqual(im.read(rows["data"]["va"], a.DATA_SIZE), bytes(a.DATA_SIZE))

    def test_foreign_and_mixed_sites_refuse_before_allocator(self):
        rows = a.allocations(self.result)
        addresses = [va for _, va, _, _ in a.sites()] + [rows[k]["va"] for k in rows]
        addresses += [a.GUARDS[5][0]+20, a.DESK_VA+4]
        for va in addresses:
            with self.subTest(va=hex(va)):
                bad = self.corrupt(va)
                self.assertEqual(a.status(bad), "foreign")
                with patch.object(a.space, "apply", side_effect=AssertionError("mutated before refusal")):
                    with self.assertRaises(ValueError):
                        a.apply(bad)

    def test_empty_reserved_union_and_missing_owner(self):
        reserved, _ = a.space.apply(self.retail, a.REQUESTS, scaleout=True)
        self.assertEqual(a.status(reserved), "retail")
        self.assertEqual(a.apply(reserved)[0], self.result)
        other, _ = a.space.apply(self.retail, (("test_other", "code", 16, 16),), scaleout=True)
        with self.assertRaisesRegex(ValueError, "complete owner union"):
            a.apply(other)

    def test_both_real_rows_share_toggle_and_native_fpf_code_stays_pinned(self):
        im = XbeImage(self.result)
        for off in (20, 24, 28, 32):
            self.assertEqual(im.read(a.ROW_VAS[0]+off, 4), im.read(a.ROW_VAS[1]+off, 4))
        for va in (0x147E60, 0x147E80, 0x627E0, 0x64530, 0x64560):
            self.assertEqual(im.read(va, 24), XbeImage(self.retail).read(va, 24))

    def test_manifest_recorder_covers_new_retail_hooks_and_allocated_state(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        recorder.observe(a, "apply", self.retail, self.result, self.receipt)
        spans = recorder.spans
        for _, va, before, _ in a.sites():
            self.assertTrue(any(int(s["start"], 0) <= va and va+len(before) <= int(s["end"], 0)
                                for s in spans), hex(va))
        self.assertTrue(any(s["owner"] == a.space.OWNER for s in spans))


if __name__ == "__main__":
    unittest.main()
