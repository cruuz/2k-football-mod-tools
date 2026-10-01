"""College relabeling preserves referenced schools and bounded UTF-16 storage."""
import unittest
from mod_editor.core import nfl2k5_roster_records as rr
from tests.nfl2k5_supersim_draft_fixture import retail_roster

class CollegeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.body=retail_roster()

    def test_unused_table_alias_roundtrip_and_shared_suffix(self):
        doc=rr.RosterDocument(self.body)
        used={p.college_index for p in doc.players}
        slot=next(i for i in range(len(doc.colleges)) if i not in used)
        p=doc.players[0]
        spec=dict(schema=rr.EDITS_SCHEMA,edits=[],college_aliases=[dict(index=slot,expected=doc.colleges[slot],name='Test University')],
            college_updates=[dict(pool=p.pool,index=p.index,first=p.first,last=p.last,college='Test University')])
        out,_=rr.apply_body(self.body,spec);after=rr.RosterDocument(out)
        self.assertEqual(after.players[0].college,'Test University')
        self.assertEqual(len(after.colleges),len(doc.colleges))
        self.assertLessEqual(after.college_pool.end,doc.college_pool.end)
        self.assertEqual([p.college for p in after.players[1:]],[p.college for p in doc.players[1:]])
        self.assertEqual(rr.apply_body(out,spec)[0],out)

    def test_referenced_alias_and_wrong_player_pin_refuse(self):
        doc=rr.RosterDocument(self.body);p=doc.players[0]
        spec=dict(schema=rr.EDITS_SCHEMA,edits=[],college_aliases=[dict(index=p.college_index,expected=p.college,name='Wrong School')])
        with self.assertRaises(rr.RosterRecordError):rr.apply_body(self.body,spec)
        spec=dict(schema=rr.EDITS_SCHEMA,edits=[],college_updates=[dict(pool=p.pool,index=p.index,first='Wrong',last=p.last,college=p.college)])
        with self.assertRaises(rr.RosterRecordError):rr.apply_body(self.body,spec)


if __name__ == "__main__":
    unittest.main()
