"""Single-pool H-back roles: native readers and complete position selectors.

Private integrated XBE/ROST inputs are opt-in. Renderer/heap seams are named
in the reused native fixture; label/pool/count/getter routines execute x86.
"""
import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_hback as hb, nfl2k5_position_pools as pools
from mod_editor.core import nfl2k5_modern_positions as modern
from mod_editor.core.nfl2k5_cave_oracle import XbeImage


def sample():
    return dict(schema=hb.SCHEMA, as_of='2026-10-14', teams=[dict(
        team=t, role='H-B' if t in ('LV','HOU') else 'FB',
        sources=['https://example.org/fixture'], resolution='Synthetic role fixture') for t in hb.TEAMS])


class Validation(unittest.TestCase):
    def test_complete_unique_team_decisions_and_distinct_abbreviation(self):
        mask = hb.mask_for(sample())
        self.assertEqual(len(mask), 38)
        self.assertEqual([i for i,v in enumerate(mask) if v], [20,37])
        self.assertNotEqual('H-B', 'HB')

    def test_missing_duplicate_invalid_unsourced_decisions_refuse(self):
        for mutation in (lambda p:p['teams'].pop(),
                         lambda p:p['teams'].__setitem__(0,p['teams'][1]),
                         lambda p:p['teams'][0].update(role='HB'),
                         lambda p:p['teams'][0].update(team='LA'),
                         lambda p:p['teams'][0].update(sources=[]),
                         lambda p:p['teams'][0].update(resolution='')):
            p=sample();mutation(p)
            with self.assertRaises(ValueError):hb.mask_for(p)

    def test_studio_final_stage_uses_the_same_writer(self):
        from mod_editor.core import mod_build as build
        from types import SimpleNamespace
        plan=SimpleNamespace(roster_edits='roles.json');doc={'hback_roles':sample()}
        records=SimpleNamespace(read_edits=lambda p:doc)
        writer=SimpleNamespace(apply=lambda raw,p:(b'new',dict(native_position=8)))
        with patch.object(build,'_core_module',side_effect=lambda n:records if n=='nfl2k5_roster_records' else writer),patch.object(build,'_xbe_bytes',return_value=b'old'),patch.object(build,'_write_xbe_bytes') as write:
            receipt={'steps':[]};build._apply_hback_roles(plan,'disc',receipt,lambda *_:None)
            write.assert_called_once_with('disc',b'new')
            self.assertEqual(receipt['steps'],[dict(step='hback_roles',native_position=8)])


@unittest.skipUnless(os.environ.get('B77_RO1_XBE') and os.environ.get('B77_RO1_HBACK'), 'private integrated image and role plan required')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=Path(os.environ['B77_RO1_XBE']).read_bytes()
        cls.plan=json.loads(Path(os.environ['B77_RO1_HBACK']).read_text())
        cls.payload,cls.receipt=hb.apply(cls.base,cls.plan)
        cls.image=XbeImage(cls.payload)

    def machine(self):
        from tests.mod_editor.test_nfl2k5_draft_picks import Runtime
        runner=Runtime();runner.machine(self.payload)
        runner.uc.mem_write(0x10000,self.payload[:struct.unpack_from('<I',self.payload,0x108)[0]])
        return runner

    def test_real_studio_helper_matches_direct_writer(self):
        from mod_editor.core import mod_build as build, nfl2k5_roster_records as rr
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);xbe=root/'default.xbe';document=root/'edits.json'
            xbe.write_bytes(self.base)
            document.write_text(json.dumps(dict(schema=rr.EDITS_SCHEMA,edits=[],hback_roles=self.plan)),newline='\n')
            plan=SimpleNamespace(roster_edits=str(document));receipt={'steps':[]}
            with patch.object(build,'_core_module',side_effect=lambda name:{'nfl2k5_roster_records':rr,'nfl2k5_hback':hb}[name]):
                build._apply_hback_roles(plan,xbe,receipt,lambda *_:None)
            self.assertEqual(xbe.read_bytes(),self.payload)
            self.assertEqual(receipt['steps'][0]['owner'],hb.OWNER)

    def test_all_32_teams_all_slots_and_header_no_shared_mutation(self):
        from unicorn import x86_const as x, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_CODE
        m=self.machine();uc=m.uc;team=0x1700000;table=modern.layout_table(self.payload)
        def put(va,n):uc.mem_write(va,struct.pack('<I',n))
        put(0xC1749C,team);put(team+0x128,0)
        uc.mem_protect(table&~4095,4096,UC_PROT_READ)
        row=hb.allocation(self.payload)
        uc.mem_protect(row['va']&~4095,4096,UC_PROT_READ|UC_PROT_EXEC)
        mask=hb.mask_for(self.plan)
        for index,(club,asset) in enumerate(zip(hb.TEAMS,hb.TEAM_IDS)):
            put(team+0x118,asset|(index<<16))
            for unit in range(4):
                put(0xC174B8,unit)
                for slot in range(13 if unit==3 else 11):
                    uc.reg_write(x.UC_X86_REG_ECX,slot)
                    m.call(0x243AE0);at=uc.reg_read(x.UC_X86_REG_EAX)
                    expected=row['va']+hb.RECORD_OFFSET if unit==0 and slot==2 and mask[asset] else table+(unit*11+slot)*72
                    self.assertEqual(at,expected,(club,unit,slot))
                    self.assertEqual(uc.reg_read(x.UC_X86_REG_ECX),slot)
        # Null, non-NFL and out-of-range teams keep the native record.
        put(0xC174B8,0)
        for pointer,kind,asset in ((0,0,37),(team,1,37),(team,0,38),(team,0,0xffffffff)):
            put(0xC1749C,pointer);put(team+0x128,kind);put(team+0x118,asset)
            uc.reg_write(x.UC_X86_REG_ECX,2);m.call(0x243AE0)
            self.assertEqual(uc.reg_read(x.UC_X86_REG_EAX),table+144)
        put(0xC1749C,team);put(team+0x128,0)
        # Native header tail computes its own pointer, then calls the renderer.
        captured=[]
        def renderer(uc,pc,size,data):
            captured.append(uc.reg_read(x.UC_X86_REG_EDX))
            sp=uc.reg_read(x.UC_X86_REG_ESP);uc.reg_write(x.UC_X86_REG_EIP,int.from_bytes(uc.mem_read(sp,4),'little'));uc.reg_write(x.UC_X86_REG_ESP,sp+4)
        uc.hook_add(UC_HOOK_CODE,renderer,begin=0xF3670,end=0xF3670)
        for asset in hb.TEAM_IDS:
            put(team+0x118,asset);uc.reg_write(x.UC_X86_REG_EDX,table+144+10)
            m.call(0x243E2C)
            self.assertEqual(captured[-1],(row['va']+hb.RECORD_OFFSET if mask[asset] else table+144)+10)
        self.assertEqual(bytes(uc.mem_read(table,46*72)),self.image.read(table,46*72))
        print('NATIVE_DEPTH 32 teams, 1472 slot reads, 32 header reads; shared table unchanged')

    def test_foreign_sites_masks_readers_and_replay(self):
        from mod_editor.core import nfl2k5_my_career_mode as career
        self.assertEqual(hb.apply(self.payload,self.plan)[0],self.payload)
        self.assertEqual(career.status(self.payload),'applied')
        self.assertEqual(career.apply(self.payload)[0],self.payload)
        for at in (0x243AF4,0x243E2C,0x243AE0,0x4F26F0,hb.allocation(self.payload)['va']+hb.MASK_OFFSET):
            b=bytearray(self.payload);b[self.image.offset(at)]^=0x40
            with self.assertRaises(ValueError):hb.apply(bytes(b),self.plan)
            self.assertEqual(career.status(bytes(b)),'foreign')
        other=copy.deepcopy(self.plan)
        other['teams'][0]['role']='H-B' if other['teams'][0]['role']!='H-B' else 'FB'
        with self.assertRaises(ValueError):hb.apply(self.payload,other)
        self.assertEqual(pools.status(self.payload),'applied')
        self.assertEqual(modern.status(self.payload),'applied')

    @unittest.skipUnless(os.environ.get('B77_RO1_BODY'), 'private roster body required')
    def test_native_sixteen_selectors_fa_trade_contracts_draft_cache(self):
        from tools import nfl2k5_roster_reclassify as rr
        from tests.nfl2k5_olb_row_fixture import Machine
        body=Path(os.environ['B77_RO1_BODY']).read_bytes()
        raw=struct.pack('<4s7I',b'ROST',len(body),len(body),0,0,0,0,0)+body
        resource=rr.parse_resource(5,0,raw)
        m=Machine(self.payload,resource,body)
        # Controlled membership using distinct real identities. This changes
        # fixture inputs only; every list's count/getter remains native.
        for p in m.team_players+m.fa_players:
            pos=m.byte(p+0x35)
            if pos in (11,16):m.uc.mem_write(p+0x35,bytes([8 if pos==11 else 9]))
        m.roster_before=bytes(m.uc.mem_read(m.BASE,m.body_size))
        checked=[]
        for name,table,_olb,_stride,pages in pools.FILTER_TABLES:
            m.open(table)
            if name=='team_rosters':m.put(m.UI+0x68,0);m.call(0x174140,eax=m.UI)
            count=m.call(0x170910,ecx=m.UI);results=[]
            for i in range(count):
                result=m.result();results.append(result)
                if result['enum']==8:
                    self.assertEqual(result['title'],'FB / H-backs',name)
                    self.assertEqual(len(result['players']),2 if name=='choose_players' else 1,name)
                    self.assertEqual(len(result['players']),len(set(result['players'])),name)
                    self.assertTrue(all(m.byte(p+0x35)==8 for p in result['players']))
                if result['enum']==9:
                    self.assertTrue(all(m.byte(p+0x35)==9 for p in result['players']),name)
                m.call(0x174CB0,ecx=m.UI)
            self.assertEqual(sum(r['enum']==8 for r in results),1,name)
            self.assertEqual(sum(r['title']=='FB / H-backs' for r in results),1,name)
            for i in reversed(range(count)):
                m.call(0x174D30,ecx=m.UI,edx=i);self.assertEqual(m.result(),results[i])
            checked.append(name)
        m.close()
        print('NATIVE_SELECTORS',','.join(checked),'one enum-8 page each; unique identities; forward/indexed reverse passed')

    def test_native_player_card_and_cap_labels_templates_and_cycles(self):
        from unicorn import x86_const as x
        m=self.machine();uc=m.uc;player=0x1700000
        uc.mem_write(0xCB8B14,struct.pack('<I',player));uc.mem_write(player+0x35,b'\x08')
        def text(va):return bytes(uc.mem_read(va,80)).decode('utf-16le').split('\0')[0]
        for va in (0xE5F90,0xE5FB0):
            uc.reg_write(x.UC_X86_REG_ECX,8);m.call(va)
            self.assertEqual(text(uc.reg_read(x.UC_X86_REG_EAX)),'F/H' if va==0xE5F90 else 'FB / H-back')
        uc.reg_write(x.UC_X86_REG_ECX,player);m.call(0xE5FC0)
        self.assertEqual(text(uc.reg_read(x.UC_X86_REG_EAX)),'F/H')
        m.call(0x345540);self.assertEqual(text(uc.reg_read(x.UC_X86_REG_EAX)),'FB / H-back')
        for va in (0x345560,0x345590):
            seen=[]
            for _ in range(16):
                m.call(va);seen.append(uc.mem_read(player+0x35,1)[0])
            self.assertEqual(len(seen),len(set(seen)));self.assertEqual(seen.count(8),1);self.assertNotIn(10,seen)
        uc.mem_write(player+0x35,b'\x08')
        for i,name in enumerate(('Blocking F/H','Catching F/H','Balanced F/H')):
            uc.mem_write(0xCB8830,struct.pack('<I',i));m.call(0x343460);m.call(0x343FA0)
            self.assertEqual(text(uc.reg_read(x.UC_X86_REG_EAX)),name)
        print('NATIVE_CARD_CAP player abbreviation, common long name, CAP/MyCareer long name, 3 templates, both 16-position cycles passed')

if __name__=='__main__':unittest.main()
