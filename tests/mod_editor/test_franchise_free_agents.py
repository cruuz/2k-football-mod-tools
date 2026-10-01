"""Explicit FA list ownership cannot expose historical/all-star aliases."""
import copy
import unittest
from mod_editor.core import nfl2k5_roster_records as rr
from tests.nfl2k5_supersim_draft_fixture import retail_roster

class FreeAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body=retail_roster();cls.doc=rr.RosterDocument(cls.body)
        cls.selected=[dict(pool=p.pool,index=p.index,first=p.first,last=p.last)
                      for p in cls.doc.players if p.group=='free_agent']
        cls.spec=dict(schema=rr.EDITS_SCHEMA,edits=[],free_agent_pool=cls.selected)

    def test_retire_five_aliases_without_changing_historical_records(self):
        out,_=rr.apply_body(self.body,self.spec);doc=rr.RosterDocument(out)
        self.assertEqual(len(doc.free_agents),236)
        self.assertEqual(len(self.doc.free_agents),241)
        for p in self.doc.players:self.assertEqual(self.body[p.offset:p.offset+84],out[p.offset:p.offset+84])
        self.assertEqual(rr.apply_body(out,self.spec)[0],out)

    def test_duplicate_stale_and_other_owner_refuse(self):
        bad=copy.deepcopy(self.spec);bad['free_agent_pool'].append(bad['free_agent_pool'][0])
        with self.assertRaises(rr.RosterRecordError):rr.apply_body(self.body,bad)
        bad=copy.deepcopy(self.spec);bad['free_agent_pool'][0]['first']='Wrong'
        with self.assertRaises(rr.RosterRecordError):rr.apply_body(self.body,bad)
        p=next(self.doc.by_offset[o] for o in self.doc.free_agents if self.doc.by_offset[o].teams)
        bad=copy.deepcopy(self.spec);bad['free_agent_pool'].append(dict(pool=p.pool,index=p.index,first=p.first,last=p.last))
        with self.assertRaises(rr.RosterRecordError):rr.apply_body(self.body,bad)


if __name__ == "__main__":
    unittest.main()
