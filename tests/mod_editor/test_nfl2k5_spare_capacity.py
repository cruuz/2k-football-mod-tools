"""Synthetic native-shaped full tables; no game bytes, emulator or image copies."""
from pathlib import Path
import copy
import struct
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'tests/mod_editor')]
from mod_editor.core import nfl2k5_roster_records as rr,nfl2k5_free_agents as fa,nfl2k5_spare_capacity as capacity,nfl2k5_prospect_names as names,mod_build
from test_nfl2k5_free_agents import fixture as fa_fixture

def fixture():
    data=fa.load_data()
    body=bytearray(fa_fixture(data))
    def relative(field,target):struct.pack_into('<i',body,field,target-field+1)
    root=rr.OBJ_OFF
    count_fields={'primary':0,'secondary':8,'stadiums':0x10,'teams':0x18,'colleges':0x20,'coaches':0x30,'free_agents':0x38,'team_labels':0x48,'generated_names':0x50,'historic_descriptors':0x58}
    pointer_fields={key:offset+4 for key,offset in count_fields.items()}
    for name,(count,offset) in capacity.NATIVE_TABLES.items():
        if name=='free_agents':count=239
        struct.pack_into('<I',body,root+count_fields[name],count)
        relative(root+pointer_fields[name],offset)
    # Existing named synthetic clubs retain their pointers. Extra blank clubs
    # and all synthetic model/coach/label tables carry no selected pointers.
    body[0xB0:0x29B0]=bytes(82*128)
    body[0x29B0:0x41C8]=bytes(0x41C8-0x29B0)
    for index in range(52):
        at=0x41C8+index*500
        if index>=3:body[at:at+500]=bytes(500)
        struct.pack_into('<H',body,at+0x118,index)
    body[0xA758+5*8:0xAFA8]=bytes((266-5)*8)
    rows,_=names.load_rows('modern');layout=names.plan_layout(rows)
    body[names.ARRAY_OFF:names.ARRAY_OFF+names.ARRAY_SIZE]=layout.array
    body[names.STRINGS_START:names.STRINGS_END]=layout.strings
    body[0x73EDC:0x73EDC+75*16]=bytes(75*16)
    # A selected secondary-template label seals the full synthetic name span;
    # the intervening bytes are empty reusable storage, never retail literals.
    last_buffer=capacity.PLAYER_NAME_END-34
    body[last_buffer:last_buffer+14]='Player'.encode('utf-16le')+b'\0\0'
    relative(0x3DD14+67*84+0x14,last_buffer)
    after,_=fa.apply_body(bytes(body),data)
    return after

class SpareCapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=fixture();cls.after,cls.receipt=capacity.apply_body(cls.before)
    def test_exact_size_real_spares_and_every_existing_identity_preserved(self):
        before=rr.load_body(self.before,scheme='one_pool');after=rr.load_body(self.after,scheme='one_pool')
        self.assertEqual(len(self.before),len(self.after));self.assertEqual(len(after.by_pool('primary')),2619)
        self.assertEqual(len(after.by_pool('secondary')),68)
        self.assertEqual(sum(bool(p.record.get('player_type')&1) for p in after.by_pool('primary')),155)
        self.assertEqual(len(after.free_agents),377)
        self.assertEqual([p.index for p in after.group_players('draft_class')],list(range(1944,2324)))
        self.assertTrue(self.receipt['all_original_record_nonpointer_bytes_names_history_equal'])
        self.assertTrue(self.receipt['all_bytes_outside_explicit_reclaimed_and_new_name_scopes_recover_exactly_by_inverse'])
        for p in before.players:
            q=next(v for v in after.by_pool(p.pool) if v.index==p.index)
            self.assertEqual((p.first,p.last,p.college_index,p.teams),(q.first,q.last,q.college_index,q.teams))
            a=bytearray(p.record.encode());b=bytearray(q.record.encode())
            for offset in (0,0x10,0x14,0x2C):a[offset:offset+4]=b[offset:offset+4]=bytes(4)
            self.assertEqual(a,b)
    def test_private_blank_names_have_no_alias_or_overlap(self):
        doc=rr.load_body(self.after);targets=[]
        old_targets={doc.rel(p.offset+field) for p in doc.players if p.pool!='primary' or p.index<2479 for field in (0x10,0x14)}
        for player in doc.by_pool('primary')[2479:]:
            for field in (0x10,0x14):
                at=doc.rel(player.offset+field);targets.append(at)
                self.assertEqual(self.after[at:at+34],'****************'.encode('utf-16le')+b'\0\0')
        self.assertEqual(len(set(targets)),280);self.assertFalse(set(targets)&old_targets)
        ordered=sorted(targets);self.assertTrue(all(a+34<=b for a,b in zip(ordered,ordered[1:])))
        self.assertEqual(self.receipt['new_blank_name_bytes'],9520)
    def test_native_layout_and_hash_refusals_leave_source_untouched(self):
        for field,value in ((rr.TEAM_COUNT_FIELD,51),(names.HEADER_ARRAY_OFF,0),(rr.POOL_FIELDS['primary'][0],2618)):
            bad=bytearray(self.after);struct.pack_into('<I',bad,field,value);before=bytes(bad)
            self.assertEqual(capacity.status(bad),'foreign')
            with self.assertRaises(ValueError):capacity.apply_body(bad)
            self.assertEqual(bytes(bad),before)
        raw=capacity._wrapped(self.before)
        with self.assertRaisesRegex(ValueError,'SHA-256'):capacity.repair_resource(raw)
        output,receipt=capacity.repair_resource(raw,approved_input_sha256=(capacity.sha(raw),))
        self.assertEqual(output[32:],self.after);self.assertTrue(receipt['approved_composed_input'])
    def test_replay_refuses_shared_or_occupied_new_names(self):
        doc=rr.load_body(self.after);first,second=doc.by_pool('primary')[2479:2481]
        bad=bytearray(self.after);target=doc.rel(first.offset+0x10);struct.pack_into('<i',bad,second.offset+0x10,target-second.offset-0x10+1)
        with self.assertRaisesRegex(ValueError,'alias'):capacity.apply_body(bad)
        bad=bytearray(self.after);bad[first.offset+8]=4
        with self.assertRaisesRegex(ValueError,'occupied|foreign type'):capacity.apply_body(bad)
        self.assertEqual(capacity.apply_body(self.after)[0],self.after)
    def test_private_buffer_inside_existing_name_suffix_is_refused(self):
        doc=rr.load_body(self.after);old=doc.by_pool('primary')[2464];new=doc.by_pool('primary')[2479]
        at=doc.rel(old.offset+0x10)
        bad=bytearray(self.after)
        bad[at:at+66]=('*'*32).encode('utf-16le')+b'\0\0'
        target=at+32
        self.assertEqual(bad[target:target+34],'****************'.encode('utf-16le')+b'\0\0')
        struct.pack_into('<i',bad,new.offset+0x10,target-new.offset-0x10+1)
        with self.assertRaisesRegex(ValueError,'overlaps an existing selected-name'):
            capacity.apply_body(bad)

    def test_prospect_pool_canonical_read_write_and_native_boundary_survive(self):
        self.assertEqual(names.parse_pool(self.before),names.parse_pool(self.after))
        self.assertEqual(names.pool_digest(self.before),names.pool_digest(self.after))
        self.assertEqual(names.body_status(self.after),'applied')
        self.assertEqual(names.boundary_range(self.before),names.boundary_range(self.after))
        rows,_=names.load_rows('modern');self.assertEqual(names.apply_body(self.after,rows)[0],self.after)
        bad=bytearray(self.after);struct.pack_into('<I',bad,rr.TEAM_COUNT_FIELD,51)
        self.assertFalse(names.header_ok(bad))
    def test_dated_fa_replay_and_typed_cap_edit_keep_layout_recognition(self):
        self.assertEqual(fa.apply_body(self.after)[0],self.after)
        doc=rr.load_body(self.after);player=doc.by_pool('primary')[2479]
        doc.set_name(player,'first','NewName');player.record.set('player_type',5)
        edited=doc.to_body(normalise_commentary=False)
        capacity.extended_layout(edited)
        self.assertTrue(names.header_ok(edited));self.assertEqual(names.body_status(edited),'applied')
        with self.assertRaises(ValueError):capacity.apply_body(edited)
    def test_studio_restores_capacity_for_dated_fa_including_retail_anniversary(self):
        source={'fr_free_agents':{'date':'2026-09-29','selected':236,'source':'roster_2026.csv'},'free_agent_pool':[{}]*239}
        for historic,anniversary,selected in ((False,False,True),(True,False,True),(False,True,True),(True,True,True)):
            plan=mod_build.BuildPlan('source','target',roster_edits='edits.json',season_2026=True,position_pools=True,historic_teams_quick_game=historic,espn25_more_moments=anniversary)
            with mock.patch.object(rr,'read_edits',return_value=source),mock.patch.object(rr,'apply',return_value={'log':[]}) as apply:
                mod_build._apply_roster_history(plan,'target',{'steps':[]},lambda *args:None)
            self.assertEqual(apply.call_args.args[1].get('restore_historic_spare_capacity') is True,selected)
        self.assertNotIn('restore_historic_spare_capacity',source)
        undated={'free_agent_pool':[{}]*239}
        plan=mod_build.BuildPlan('source','target',roster_edits='edits.json',season_2026=True,position_pools=True,espn25_more_moments=True)
        with mock.patch.object(rr,'read_edits',return_value=undated),mock.patch.object(rr,'apply',return_value={'log':[]}) as apply:
            mod_build._apply_roster_history(plan,'target',{'steps':[]},lambda *args:None)
        self.assertNotIn('restore_historic_spare_capacity',apply.call_args.args[1])

if __name__=='__main__':unittest.main()
