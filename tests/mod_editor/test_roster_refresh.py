"""Identity-safe league refresh, using synthetic records and optional private data."""
from pathlib import Path
import copy
import datetime
import json
import os
import sys
import struct
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import tempfile
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests/mod_editor'), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_roster_records as rr, nfl2k5_roster_refresh as refresh
import test_nfl2k5_roster_records as fixture


def sample():
    players = []
    for i in range(1700):
        players.append(('First', 'Last', 3, 10, 3, 200, 72,
                        datetime.date(2000, 1, 1), 0, 80, i//42 if i < 1344 else None))
    with patch.object(fixture, 'TEAM_ABBRS', tuple(f'T{i}' for i in range(32))), \
         patch.object(fixture, 'FREE_AGENTS_OFF', 0x50000), \
         patch.object(fixture, 'COLLEGE_TABLE_OFF', 0x60000), \
         patch.object(fixture, 'COLLEGE_STRINGS_OFF', 0x61000), \
         patch.object(fixture, 'NAME_STRINGS_OFF', 0x70000):
        body = fixture.synthetic_body(players)
    body = bytearray(body)
    struct.pack_into('<I', body, rr.OBJ_OFF, 2619)
    struct.pack_into('<i', body, rr.OBJ_OFF + 12, fixture.PLAYERS_OFF + 2619*84 - (rr.OBJ_OFF+12) + 1)
    source = fixture.PLAYERS_OFF
    for i in range(1700,2619):
        target = source + i*84
        body[target:target+84] = body[source:source+84]
        for off in (0,0x10,0x14):
            v = struct.unpack_from('<i', body, source+off)[0]
            struct.pack_into('<i', body, target+off, v-i*84)
    body = bytes(body)
    doc = rr.RosterDocument(body, scheme='one_pool', reference_year=2026)
    for p in doc.players:
        p.record.set('depth_rank', 7)
        p.record.set('depth_side', 7)
        p.record.set('contract_length', 1)
        p.record.set('contract_remaining', 1)
    body = doc.to_body()
    doc = rr.RosterDocument(body, scheme='one_pool', reference_year=2026)
    rows = [dict(index=p.index, gsis_id=f'id{p.index}', first=p.first, last=p.last,
                 birth_date=str(p.record.birth_date), source='https://example.org/dated.csv',
                 fields={}) for p in doc.players]
    plan = dict(schema=refresh.SCHEMA, as_of='2026-10-14', players=rows,
                identity_guards=[[p.index,p.first,p.last,str(p.record.birth_date)] for p in doc.players],
                teams=[dict(index=t.index,team=t.abbreviation,
                            active=[doc.by_offset[o].index for o in t.slots],reserves=[],
                            specialists={k:None for k in rr.SPECIAL_TEAM_OFFSETS}) for t in doc.teams],
                free_agents=[doc.by_offset[o].index for o in doc.free_agents])
    return body, plan


class RefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body, cls.plan = sample()

    def test_swap_keeps_history_appearance_ratings_and_abilities(self):
        plan = copy.deepcopy(self.plan)
        plan['teams'][0]['active'][0], plan['teams'][1]['active'][0] = 42, 0
        plan['players'][0]['fields'] = {'jersey':18,'depth_rank':0,'depth_side':0}
        out, receipt = refresh.apply_body(self.body, plan)
        old, new = rr.RosterDocument(self.body), rr.RosterDocument(out)
        self.assertEqual(new.club_of(new.players[0]), 1)
        self.assertEqual(new.players[0].record.get('jersey'), 18)
        allowed = {'jersey','depth_rank','depth_side','unknown_52','pbp_id'}
        for p,q in zip(old.players,new.players):
            for k,v in p.record.values.items():
                if k not in allowed:self.assertEqual(v,q.record.values[k],(p.index,k))
            self.assertEqual(p.record.get('unknown_52') & 0xe0,q.record.get('unknown_52') & 0xe0)
        self.assertEqual(refresh.apply_body(out,plan)[0],out)
        self.assertGreater(receipt['changed_bytes'],0)

    def test_no_mutation_on_bad_identity(self):
        plan = copy.deepcopy(self.plan);plan['players'][0]['birth_date']='1999-01-01'
        before = bytes(self.body)
        with self.assertRaisesRegex(ValueError,'identity mismatch'):refresh.apply_body(self.body,plan)
        self.assertEqual(self.body,before)

    def test_historic_namesake_guard(self):
        plan=copy.deepcopy(self.plan);plan['identity_guards'][100][3]='1970-01-01'
        with self.assertRaisesRegex(ValueError,'guard failed'):refresh.apply_body(self.body,plan)

    def test_existing_appearance_and_history_edits_refused(self):
        for field in ['photo_id','speed','history_pointer','unknown_53_high']:
            plan=copy.deepcopy(self.plan);plan['players'][0]['fields'][field]=0
            with self.assertRaises(ValueError):refresh.apply_body(self.body,plan)

    def test_duplicate_source_and_membership_refused(self):
        for kind in ('source','member'):
            plan=copy.deepcopy(self.plan)
            if kind=='source':plan['players'][1]['gsis_id']=plan['players'][0]['gsis_id']
            else:plan['teams'][1]['active'][0]=0
            with self.assertRaises(ValueError):refresh.apply_body(self.body,plan)

    def test_overflow_refused(self):
        plan=copy.deepcopy(self.plan);plan['teams'][0]['active']+=list(range(1344,1356))
        with self.assertRaisesRegex(ValueError,'capacity'):refresh.apply_body(self.body,plan)

    def test_specialist_must_belong_to_team(self):
        plan=copy.deepcopy(self.plan);plan['teams'][0]['specialists']['pr']=42
        with self.assertRaisesRegex(ValueError,'Specialist'):refresh.apply_body(self.body,plan)

    def test_reserve_survives_round_trip(self):
        plan=copy.deepcopy(self.plan);i=plan['free_agents'].pop(0);plan['teams'][0]['reserves']=[i]
        out,_=refresh.apply_body(self.body,plan)
        doc=rr.RosterDocument(out)
        self.assertEqual(doc.reserves[0],(i,));self.assertEqual(doc.club_of(doc.by_pool('primary')[i]),0)
        self.assertEqual(refresh.apply_body(out,plan)[0],out)

    def test_studio_directive_uses_same_writer(self):
        direct,_=refresh.apply_body(self.body,self.plan)
        result,receipt=rr.apply_body(self.body,dict(schema=rr.EDITS_SCHEMA,edits=[],roster_refresh=self.plan))
        self.assertEqual(result,direct);self.assertEqual(receipt['roster_refresh']['teams'],32)

    def test_build_defers_refresh_until_final_roster_stage(self):
        from mod_editor.core import mod_build as build
        document = dict(schema=rr.EDITS_SCHEMA, edits=[], roster_refresh=self.plan)
        plan = build.BuildPlan('source', 'target', roster_edits='refresh.json',
                               season_2026=True, position_pools=True)
        calls = []
        module = SimpleNamespace(EDITS_SCHEMA=rr.EDITS_SCHEMA,
                                 read_edits=lambda p: document,
                                 apply=lambda target, data, **kw: calls.append(data) or {'log': []})
        with patch.object(build, '_core_module', return_value=module):
            build._apply_roster_history(plan, 'target', {'steps': []}, lambda *a: None)
            build._apply_roster_refresh(plan, 'target', {'steps': []}, lambda *a: None)
        self.assertNotIn('roster_refresh', calls[0])
        self.assertEqual(calls[-1], document)
        self.assertIn('roster_refresh', document)

    def test_virtual_spans_cover_block_boundary_and_replay(self):
        from tools.b77 import ro1_repair as repair
        old = bytes(range(30)); new = bytearray(old)
        new[7:11] = b'abcd'; new[-1] = 0
        spans = list(repair.runs(old, bytes(new)))
        with tempfile.TemporaryDirectory() as tmp, patch.object(repair, 'BLOCK', 8):
            path = Path(tmp)/'image.bin'; path.write_bytes(old)
            result = repair.project_hash(path, spans)
            self.assertEqual(result['input_sha256'], repair.sha(old))
            self.assertEqual(result['output_sha256'], repair.sha(new))
            self.assertEqual(result['changed_bytes'], 5)
            self.assertTrue(result['outside_spans_equal'])
            self.assertEqual(path.read_bytes(), old)
            self.assertEqual(list(repair.runs(new, new)), [])
        with self.assertRaisesRegex(ValueError, 'growth'):
            list(repair.runs(old, old+b'x'))

    def test_new_player_uses_vacancy_and_has_no_inherited_history(self):
        raw=bytearray(self.body);offset=fixture.PLAYERS_OFF+2464*84
        for field,target in [(0x10,0x68000),(0x14,0x68022)]:
            raw[target:target+34]='****************'.encode('utf-16le')+b'\0\0'
            struct.pack_into('<i',raw,offset+field,target-offset-field+1)
        raw[offset+8]=1
        plan=copy.deepcopy(self.plan)
        plan['identity_guards']=[g for g in plan['identity_guards'] if g[0]!=2464]
        row=plan['players'][2464]
        row.update(first='New',last='Arrival',birth_date='2000-01-01',new=True)
        row['fields']={k:50 for k in rr.RATING_BYTE_ORDER}
        row['fields'].update(position=3,jersey=18,height=72,weight=200,birth_year=2000,
                             birth_month=1,birth_day=1,years_pro=1,photo_id=7100,
                             contract_length=1,contract_remaining=1,contract_value=23,
                             depth_rank=7,depth_side=7)
        plan['teams'][0]['active'].append(2464)
        out,receipt=refresh.apply_body(bytes(raw),plan)
        p=rr.RosterDocument(out,reference_year=2026).by_pool('primary')[2464]
        self.assertEqual(p.display,'New Arrival');self.assertEqual(p.record.get('history_pointer'),0)
        self.assertEqual(p.record.get('unknown_53_high'),0);self.assertEqual(receipt['added'],1)
        self.assertEqual(refresh.apply_body(out,plan)[0],out)
        with self.assertRaisesRegex(ValueError,'identity mismatch'):
            refresh.apply_body(self.body,plan)

    def test_disjoint_vacant_cap_buffers_become_exclusive_adjacent_and_replay(self):
        raw=bytearray(self.body);offset=fixture.PLAYERS_OFF+2464*84
        for field,target in ((0x10,0x68000),(0x14,0x68080)):
            raw[target:target+34]='****************'.encode('utf-16le')+b'\0\0'
            struct.pack_into('<i',raw,offset+field,target-offset-field+1)
        raw[offset+8]=1
        doc=rr.RosterDocument(bytes(raw))
        self.assertEqual(refresh._repair_create_buffers(doc),1)
        out=doc.to_body(normalise_commentary=False)
        checked=rr.RosterDocument(out);player=checked.by_pool('primary')[2464]
        first=checked._pointer_target(player.offset,'first_name_pointer')
        last=checked._pointer_target(player.offset,'last_name_pointer')
        self.assertEqual(last,first+34)
        self.assertEqual((checked.name_refs[first],checked.name_refs[last]),(1,1))
        self.assertEqual((player.first,player.last),('****************',)*2)
        self.assertEqual(refresh._repair_create_buffers(checked),0)
        self.assertEqual(checked.to_body(normalise_commentary=False),out)
        for p in checked.by_pool('primary'):
            if p.index!=2464:self.assertEqual(p.record.encode(),bytes(raw[p.offset:p.offset+84]))

    def test_newly_owned_unsigned_record_needs_guarded_contract_and_replay_preserves_it(self):
        doc=rr.RosterDocument(self.body);p=doc.by_pool('primary')[0]
        for key in refresh.CONTRACT_FIELDS:p.record.set(key,0)
        raw=doc.to_body();plan=copy.deepcopy(self.plan)
        with self.assertRaisesRegex(ValueError,'contract initializer'):refresh.apply_body(raw,plan)
        fields=dict(contract_value=23,contract_length=1,contract_remaining=1,contract_type=2,contract_bonus=0)
        plan['contract_initializations']=[dict(index=0,fields=fields,source='https://example.org/minimum',rule='Synthetic one-year accounting fixture')]
        out,receipt=refresh.apply_body(raw,plan)
        self.assertEqual(receipt['initialized_contracts'],1)
        checked=rr.RosterDocument(out)
        self.assertEqual({k:checked.players[0].record.get(k) for k in fields},fields)
        self.assertEqual(refresh.apply_body(out,plan)[0],out)
        self.assertEqual(refresh.apply_body(out,plan)[1]['initialized_contracts'],0)
        checked.players[0].record.set('contract_value',99)
        changed=checked.to_body();replayed=refresh.apply_body(changed,plan)[0]
        self.assertEqual(rr.RosterDocument(replayed).players[0].record.get('contract_value'),99)
        for mutation in (lambda q:q['contract_initializations'].append(q['contract_initializations'][0]),
                         lambda q:q['contract_initializations'][0].update(index=1344),
                         lambda q:q['contract_initializations'][0]['fields'].update(contract_length=0),
                         lambda q:q['contract_initializations'][0].update(source='')):
            bad=copy.deepcopy(plan);mutation(bad)
            with self.assertRaises(ValueError):refresh.apply_body(raw,bad)


if __name__=='__main__':unittest.main()
