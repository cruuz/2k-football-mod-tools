"""Standalone ownership, retail pins and explicit opt-in contract."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_playbook_pair as pair
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"


class ContractTests(unittest.TestCase):
    def test_budget_and_union_are_explicit(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        rows = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([tuple(r) for r in rows if r[0]==pair.OWNER], list(pair.REQUESTS))
        self.assertTrue(set(pair.REQUESTS) <= set(REQUESTS))
        pair.space.plan(REQUESTS)
        self.assertLessEqual(len(pair.assembly.CODE), pair.CODE_SIZE)
        self.assertIn("Retail", pair.HELP_TEXT)
        self.assertIn("Patch", pair.HELP_TEXT)
        self.assertNotIn("\u2014", pair.HELP_TEXT)

    def test_capability_handoff_schema_and_each_new_evidence_path(self):
        from mod_editor.capabilities import validate_registry as registry
        cap=json.loads((ROOT/'docs/mod_editor/nfl2k5_playbook_pair_capability.json').read_text())
        candidate=json.loads(registry.DEFAULT_REGISTRY.read_text())
        candidate['capabilities']=sorted([c for c in candidate['capabilities'] if c['id']!=cap['id']]+[cap],
                                         key=lambda c:c['id'])
        registry.validate_data(candidate,check_files=False)
        for path in cap['evidence']+cap['runtime']['evidence']+[cap['backend']['module']]:
            registry._local_path(path,cap['id'])
        self.assertEqual(registry._command_module(cap['backend']['command'],cap['id']),cap['backend']['module'])
        registry._local_path(registry._command_module(cap['validation_command'],cap['id']),cap['id'])
        self.assertFalse(cap['gui']['default_enabled'])
        self.assertEqual(cap['runtime']['status'],'not-tested')

    def test_both_native_options_descriptors_share_two_adjacent_new_rows(self):
        code, ro = 0x2000000, 0x2200000
        b = pair.read_only_bytes(code,ro)
        at = struct.unpack_from("<I",b,71*4)[0]-ro
        rows = [struct.unpack_from("<13I",b,at+i*52) for i in range(10)]
        self.assertEqual([r[0] for r in rows], [7]*9+[3])
        for index, side in ((2,"away"),(4,"home")):
            self.assertEqual(rows[index][5],code+pair.assembly.LABELS['get_'+side])
            self.assertEqual(rows[index-1][5], pair.ROWS[1 if side=='away' else 2][5])
        self.assertEqual(len(b),pair.RO_SIZE)


@unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe is absent")
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest()!=RETAIL_SHA256:
            raise unittest.SkipTest("USA retail XBE SHA-256 differs")
        cls.result, cls.receipt = pair.apply(cls.retail)

    def corrupt(self, va, source=None, value=None):
        b = bytearray(self.result if source is None else source)
        at = XbeImage(b).offset(va,1)
        if value is None:
            b[at] ^= 1
        else:
            b[at:at+len(value)] = value
        for s in _sections(b):
            b[s.header_offset+36:s.header_offset+56] = section_digest(b,s)
        return bytes(b)

    def test_idempotence_receipt_and_section_seals(self):
        self.assertEqual(pair.status(self.retail),'retail')
        self.assertEqual(pair.status(self.result),'applied')
        self.assertEqual(pair.apply(self.result)[0],self.result)
        self.assertEqual(pair.apply(self.result)[1]['changed_bytes'],0)
        self.assertFalse(self.receipt['franchise_persistence'])
        self.assertFalse(self.receipt['runtime_witnessed'])
        self.assertEqual(self.receipt['in_game_default'],'Same as offense')
        self.assertEqual(self.receipt['changed_bytes'],sum(a!=b for a,b in zip(self.retail,self.result))+len(self.result)-len(self.retail))
        self.assertTrue(all(section_digest(self.result,s)==s.stored_digest for s in _sections(self.result)))

    def test_every_site_and_owned_span_refuses_foreign_or_partial_before_mutation(self):
        owned = pair.allocations(self.result)
        addresses = [va for _,va,_,_ in pair.sites()]+[r['va'] for r in owned.values()]
        addresses += [pair.TABLES[0]+60, 0x16665a, 0xf71ed]
        for va in addresses:
            with self.subTest(address=hex(va)):
                b = self.corrupt(va)
                self.assertEqual(pair.status(b),'foreign')
                with patch.object(pair.space,'apply',side_effect=AssertionError('allocated before refusal')):
                    with self.assertRaises(ValueError):
                        pair.apply(b)
        # A valid retail instruction in an otherwise applied owner is mixed.
        name, va, pin, _ = pair.HOOKS[0]
        mixed = self.corrupt(va,value=bytes.fromhex(pin))
        self.assertEqual(pair.status(mixed),'foreign',name)
        with self.assertRaises(ValueError):
            pair.apply(mixed)

    def test_reserved_empty_union_and_missing_owner(self):
        reserved,_ = pair.space.apply(self.retail,pair.REQUESTS,scaleout=True)
        self.assertEqual(pair.status(reserved),'retail')
        self.assertEqual(pair.apply(reserved)[0],self.result)
        other,_ = pair.space.apply(self.retail,(("other", "code",16,16),),scaleout=True)
        with self.assertRaisesRegex(ValueError,'complete owner union'):
            pair.apply(other)

    def test_recorder_includes_full_hooks_and_owned_rw_ro(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        recorder.observe(pair,'apply',self.retail,self.result,self.receipt)
        for _,va,before,_ in pair.sites():
            self.assertTrue(any(int(s['start'],0)<=va and va+len(before)<=int(s['end'],0)
                                for s in recorder.spans),hex(va))
        image = XbeImage(self.result)
        owned = pair.allocations(self.result)
        for kind in ('code','read_only'):
            self.assertFalse(image.runtime_writable(owned[kind]['va'],owned[kind]['size']))
        self.assertTrue(image.runtime_writable(owned['data']['va'],pair.DATA_SIZE))
        self.assertEqual(image.read(owned['data']['va'],pair.DATA_SIZE),bytes(pair.DATA_SIZE))


if __name__ == '__main__':
    unittest.main()
