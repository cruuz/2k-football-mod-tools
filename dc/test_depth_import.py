"""PROVED OFFLINE: specialist replay, matching, refusals and field ownership."""
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests/mod_editor')]
from dc import import_depth as imp
from mod_editor.core import nfl2k5_roster_records as rr
from test_nfl2k5_roster_records import synthetic_body

class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.body=synthetic_body()
        self.doc=rr.RosterDocument(self.body)
        self.player=self.doc.team_players(0)[1]
        self.entry={'team_index':0,'team':'IND','roles':{'kr1':imp.identity(self.player)}}
        self.fragment={'schema':rr.EDITS_SCHEMA,'edits':[],'special_teams':[self.entry]}
    def test_identity_resolution_and_byte_exact_replay(self):
        got,receipt=rr.apply_body(self.body,self.fragment)
        target=self.doc.teams[0].offset+0x195
        self.assertEqual(got[target],1)
        self.assertEqual(got[:target]+got[target+1:],self.body[:target]+self.body[target+1:])
        self.assertEqual(receipt['log'],[])
        self.assertEqual(rr.apply_body(got,self.fragment)[0],got)
        exported=rr.edits_between(self.body,got)
        self.assertEqual(rr.apply_body(self.body,exported)[0],got)
    def test_refuse_bad_role_team_name_membership_index_and_duplicate(self):
        for mutate in [lambda e:e.update(team='ATL'),lambda e:e.update(team_index=-1),
                       lambda e:e.update(roles={'punt':imp.identity(self.player)}),
                       lambda e:e['roles']['kr1'].update(last='stale'),
                       lambda e:e['roles']['kr1'].update(index=999),
                       lambda e:e['roles']['kr1'].update(index=True),
                       lambda e:e['roles'].update(kr1=imp.identity(self.doc.team_players(1)[0]))]:
            entry=copy.deepcopy(self.entry);mutate(entry)
            before=bytes(self.doc.body)
            with self.assertRaises(rr.RosterRecordError):rr.apply_special_teams(self.doc,[self.entry,entry])
            self.assertEqual(bytes(self.doc.body),before)
            with self.assertRaises(rr.RosterRecordError):rr.apply_special_teams(self.doc,[entry])
        with self.assertRaises(rr.RosterRecordError):rr.apply_special_teams(self.doc,[self.entry,self.entry])
    def test_explicit_clear(self):
        self.entry['roles']['kr1']=None
        got,_=rr.apply_body(self.body,self.fragment)
        self.assertEqual(got[self.doc.teams[0].offset+0x195],255)
        self.assertEqual(rr.apply_body(self.body,rr.edits_between(self.body,got))[0],got)
    def test_club_duplicate_returner_claim_still_refuses(self):
        for p in self.doc.team_players(0)[1:]:p.record.values['unknown_52']|=4
        with self.assertRaises(rr.RosterRecordError):self.doc.check_depth_locks()
    def test_matching_prioritizes_id_and_never_crosses_team(self):
        match=imp.matcher(self.doc,[{'pool':self.player.pool,'index':self.player.index,'name':self.player.display,'gsis_id':'id'}])
        self.assertEqual(match({'player_name':'Different Name','gsis_id':'id'},0),(self.player,'gsis_id'))
        self.assertEqual(match({'player_name':self.player.display,'gsis_id':'unknown'},0),(self.player,'normalized_name'))
        self.assertEqual(match({'player_name':self.player.display,'gsis_id':'id'},1),(None,'missing_from_team'))
    def test_latest_is_per_team_without_old_row_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'rows.csv'
            path.write_text('dt,team,player_name\n2026-09-27,A,old\n2026-09-28,A,new\n2026-09-26,B,b\n')
            rows,dates=imp.latest_rows(path)
            self.assertEqual([r['player_name'] for r in rows],['new','b'])
            self.assertEqual(dates,{'A':'2026-09-28','B':'2026-09-26'})
    def test_suffix_and_punctuation_only_name_fallback(self):
        self.assertEqual(imp.norm('Marvin Mims Jr.'),imp.norm('Marvin Mims'))
        self.assertEqual(imp.norm('J.K. Scott'),imp.norm('JK Scott'))
        self.assertNotEqual(imp.norm('Josh Allen'),imp.norm('Joshua Allen'))

class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=(imp.OUT/'candidate_C_before.rost').read_bytes()
        cls.after=(imp.OUT/'candidate_C_dc.rost').read_bytes()
        cls.base=rr.RosterDocument(cls.before);cls.new=rr.RosterDocument(cls.after)
    def test_every_other_field_and_offense_defense_starter_is_unchanged(self):
        for a,b in zip(self.base.players,self.new.players):
            for field in a.record.values:
                if field not in ('depth_rank','unknown_52'):self.assertEqual(a.record.values[field],b.record.values[field],(a.display,field))
            if a.record.values['position'] not in (1,2,12):
                self.assertEqual(a.record.values['depth_rank'],b.record.values['depth_rank'])
            if a.record.values['position']==12 and a.record.values['depth_rank']==0:
                self.assertEqual(b.record.values['depth_rank'],0)
            self.assertEqual(a.record.values['unknown_52']&0xe0,b.record.values['unknown_52']&0xe0)
            self.assertEqual(a.record.values['unknown_52']&3,b.record.values['unknown_52']&3 & a.record.values['unknown_52'])
            self.assertEqual(a.first,b.first);self.assertEqual(a.last,b.last);self.assertEqual(a.teams,b.teams)
    def test_all_clubs_have_unique_claims_and_exhibition_aliases_remain_diagnosed(self):
        for t in self.new.teams[:32]:
            self.assertEqual(self.new.depth_lock_conflicts(t.index),[])
            for bit in (4,8,16):self.assertEqual(sum(bool(p.record.values['unknown_52']&bit) for p in self.new.team_players(t.index)),1)
        self.assertTrue(any(self.new.depth_lock_conflicts(t.index) for t in self.new.teams[34:]))
        self.new.check_depth_locks()
    def test_source_bytes_recover_exactly_from_insertions(self):
        data=(imp.OUT/'league_roster_edits_candC_dc.json').read_bytes()
        receipt=json.loads((ROOT/'dc/proof/import.json').read_text())['proof']['source_byte_preservation']
        for prefix in ['special','edit']:
            start=receipt[prefix+'_insertion_offset'];size=receipt[prefix+'_insertion_bytes']
            data=data[:start]+data[start+size:]
        self.assertEqual(data,imp.SOURCE.read_bytes())
    def test_fragment_is_idempotent_and_zero_log(self):
        fragment=ROOT/'dc/special_depth_fragment.json'
        for b in (self.before,self.after):
            result,receipt=rr.apply_body(b,fragment)
            self.assertEqual(result,self.after);self.assertEqual(receipt['log'],[])

if __name__=='__main__':unittest.main()
