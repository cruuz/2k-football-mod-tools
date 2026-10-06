"""Hash refusal, narrow native bit scope and peer-composed repair; no retail bytes."""
import hashlib
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from test_nfl2k5_free_agents import fixture
from tools.b765 import f1_repair as repair
from mod_editor.core import nfl2k5_free_agents as fa,nfl2k5_roster_records as rr

class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=fa.load_data();cls.before=fixture(cls.plan)
        cls.after,cls.writer=fa.apply_body(cls.before,cls.plan)
    def test_unknown_hash_refuses_and_input_does_not_change(self):
        before=bytes(self.before)
        with self.assertRaisesRegex(ValueError,'Unexpected ROST SHA-256'):repair.repair_body(before)
        self.assertEqual(before,self.before)
    def test_approved_exact_composed_hash_is_logged_and_replay_is_identical(self):
        body=bytearray(self.before);doc=rr.RosterDocument(body,scheme='one_pool',reference_year=2026)
        body[doc.by_pool('primary')[0].offset+4:doc.by_pool('primary')[0].offset+6]=b'\x21\x23'
        body=bytes(body);after,r=repair.repair_body(body,approved_input_sha256=[hashlib.sha256(body).hexdigest()])
        self.assertTrue(r['approved_composed_input']);self.assertTrue(r['scope']['outside_scope_identical'])
        again,replay=repair.repair_body(after,approved_input_sha256=[hashlib.sha256(after).hexdigest()])
        self.assertEqual(after,again);self.assertEqual(replay['scope']['changed_bytes'],0)
        p=doc.by_pool('primary')[0];self.assertEqual(after[p.offset+4:p.offset+6],b'\x21\x23')
    def test_scope_receipt_proves_draft_teams_names_and_adjacent_bits(self):
        receipt=repair.prove_scope(self.before,self.after,self.plan)
        self.assertTrue(receipt['draft_380_records_identical']);self.assertTrue(receipt['team_and_reserve_membership_identical']);self.assertTrue(receipt['unrelated_names_identical'])
        doc=rr.RosterDocument(self.after,scheme='one_pool',reference_year=2026);p=doc.by_pool('primary')[1697]
        corrupted=bytearray(self.after);corrupted[p.offset+0x19]^=0x10  # birth month, adjacent to skin
        with self.assertRaisesRegex(ValueError,'escaped f1 bit scope'):repair.prove_scope(self.before,bytes(corrupted),self.plan)
    def test_new_record_creation_never_touches_existing_commentary(self):
        doc=rr.RosterDocument(self.before,scheme='one_pool',reference_year=2026)
        for row in self.plan['existing']:
            p=doc.by_pool('primary')[row['index']];self.assertEqual(self.before[p.offset+4:p.offset+6],self.after[p.offset+4:p.offset+6])

if __name__=='__main__':unittest.main()
