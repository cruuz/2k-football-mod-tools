"""Explicit FA list ownership cannot expose historical/all-star aliases."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "tests" / "mod_editor"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import copy
import unittest
from mod_editor.core import nfl2k5_college_check as college_check
from mod_editor.core import nfl2k5_free_agents as fa
from mod_editor.core import nfl2k5_roster_records as rr
from tests.nfl2k5_supersim_draft_fixture import retail_roster
from test_b778_eq1_equipment_fit import GEAR, with_templates

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

    def test_a_new_free_agent_takes_his_positions_gear_not_the_kicker_mask(self):
        # b778-eq1: the 140 dated free agents are created from a zero record; their measured skin/face
        # arrives in the row, their gear must come from the position's own class-generator templates.
        body = with_templates(retail_roster(), rr.POSITIONS.index("WR"))
        doc = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
        player = doc.by_pool("primary")[0]
        position = rr.POSITIONS.index("WR")
        row = dict(first=player.first, last=player.last, jersey=6, commentary_number=6,
                   fields={"position": position},
                   ratings={name: 50 for name in rr.RATING_BYTE_ORDER},
                   appearance={"skin": 0, "face": 5, "body": 1, "dreads": 0, "headless": 0,
                               "photo_id": 7100},
                   college=None)
        fa._create_new_player(doc, player, row, college_check)
        gear = GEAR[0 % len(GEAR)]
        for name, value in gear.items():
            self.assertEqual(player.record.get(name), value, name)
        self.assertEqual(player.record.get("skin"), 0)
        self.assertEqual(player.record.get("face"), 5)
        self.assertEqual(player.record.get("photo_id"), 7100)

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
