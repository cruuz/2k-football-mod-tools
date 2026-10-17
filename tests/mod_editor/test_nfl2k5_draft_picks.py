"""Complete-table validation and real x86 initialization/rollover proof.
rc1 (2026-10-17): B774_MC2_XBE is the integrated exe WITH the mc2 MyCareer repair (the pre-mc2 B77_RO1_XBE reports MyCareer as foreign
after mc2); provenance in the private fixture folder (.b77-scratch/i4/inputs/sp2_mc2/PROVENANCE.txt).

Set B774_MC2_XBE and B77_RO1_PICKS for the private integrated image/data proof.
No proprietary bytes or live emulator dependencies are bundled here.
"""
import copy
import json
import os
from pathlib import Path
import struct
import sys
import unittest
import tempfile
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_draft_picks as dp, nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
try:
    import unicorn as u
    from unicorn import x86_const as x
except ImportError:
    u = None


def sample():
    return dict(schema=dp.SCHEMA, base_season=2026, as_of='2026-10-14', picks=[
        dict(year=y, round=r, original_team=t, owner=dp.TEAMS[(i+r+y)%32],
             status='confirmed', sources=['https://example.org/fixture'], resolution='Synthetic fixture')
        for y in (2027,2028) for r in range(1,8) for i,t in enumerate(dp.TEAMS)])


class Validation(unittest.TestCase):
    def test_all_identities_and_layout(self):
        p=sample();table=dp.table_for(p)
        self.assertEqual(len(table),448)
        for row in p['picks']:
            at=(row['year']-2027)*224+(row['round']-1)*32+dp.TEAMS.index(row['original_team'])
            self.assertEqual(dp.TEAMS[table[at]],row['owner'])

    def test_incomplete_duplicate_wrong_year_or_owner_refused(self):
        for mutate in (lambda p:p['picks'].pop(),
                       lambda p:p['picks'].__setitem__(0,p['picks'][1]),
                       lambda p:p['picks'][0].update(year=2026),
                       lambda p:p['picks'][0].update(owner='LA'),
                       lambda p:p['picks'][0].update(status='guessed'),
                       lambda p:p['picks'][0].update(resolution=''),
                       lambda p:p['picks'][0].update(sources=[])):
            p=sample();mutate(p)
            with self.assertRaises(ValueError):dp.table_for(p)


@unittest.skipUnless(u, 'Unicorn is an optional test dependency')
class Runtime(unittest.TestCase):
    def machine(self,payload=None):
        uc=u.Uc(u.UC_ARCH_X86,u.UC_MODE_32)
        uc.mem_map(0x10000,0x2000000)
        if payload:
            for s in XbeImage(payload).sections:
                uc.mem_write(s.start,payload[s.raw:s.raw+s.raw_size])
        self.uc=uc
        self.sp=0x1F00000
        uc.reg_write(x.UC_X86_REG_ESP,self.sp)
        return uc

    def call(self,va):
        self.uc.reg_write(x.UC_X86_REG_ESP,self.sp-4)
        self.uc.mem_write(self.sp-4,struct.pack('<I',0x1FF0000))
        self.uc.emu_start(va,0x1FF0000,count=200000)
        self.assertEqual(self.uc.reg_read(x.UC_X86_REG_EIP),0x1FF0000)

    def test_guard_registers_flags_and_write_scope(self):
        table=dp.table_for(sample());va=0x1800000
        for mode in (0,1,2,3):
            uc=self.machine();uc.mem_write(va,dp.code_for(va,table))
            uc.mem_write(0xE576A0,struct.pack('<I',mode))
            uc.mem_write(dp.BANK-8,b'\x55'*464)
            regs=[x.UC_X86_REG_EAX,x.UC_X86_REG_EBX,x.UC_X86_REG_ECX,x.UC_X86_REG_EDX,x.UC_X86_REG_ESI,x.UC_X86_REG_EBP]
            for i,r in enumerate(regs):uc.reg_write(r,0x123400+i)
            # DF intentionally set. Initializer clears it locally, restores it.
            uc.reg_write(x.UC_X86_REG_EFLAGS,0x602)
            writes=[]
            uc.hook_add(u.UC_HOOK_MEM_WRITE,lambda uc,a,addr,size,value,data:writes.append((addr,size)))
            self.call(va)
            self.assertEqual(bytes(uc.mem_read(dp.BANK,448)),table if mode==2 else b'\x55'*448)
            self.assertEqual(bytes(uc.mem_read(dp.BANK-8,8)),b'\x55'*8)
            self.assertEqual(bytes(uc.mem_read(dp.BANK+448,8)),b'\x55'*8)
            for i,r in enumerate(regs):self.assertEqual(uc.reg_read(r),0x123400+i)
            self.assertEqual(uc.reg_read(x.UC_X86_REG_EDI),0xE51F61)
            self.assertEqual(uc.reg_read(x.UC_X86_REG_EFLAGS),0x602)
            self.assertTrue(all(dp.BANK<=a and a+n<=dp.BANK+448 or self.sp-64<=a<self.sp for a,n in writes))


@unittest.skipUnless(u and os.environ.get('B774_MC2_XBE') and os.environ.get('B77_RO1_PICKS'), 'private integrated XBE and complete ownership map required')
class Native(Runtime):
    @classmethod
    def setUpClass(cls):
        cls.before=Path(os.environ['B774_MC2_XBE']).read_bytes()
        cls.plan=json.loads(Path(os.environ['B77_RO1_PICKS']).read_text())
        cls.after,cls.receipt=dp.apply(cls.before,cls.plan)
        cls.table=dp.table_for(cls.plan)

    def test_append_keeps_allocations_and_replay(self):
        self.assertEqual(dp.status(self.after),'applied')
        old=space.layout(self.before)['allocations'];new=space.layout(self.after)['allocations']
        self.assertTrue(all(row in new for row in old if row['owner'] != space.DIRECTORY_OWNER))
        self.assertEqual(sum(r['size'] for r in old if r['owner'] == space.DIRECTORY_OWNER)
                         - sum(r['size'] for r in new if r['owner'] == space.DIRECTORY_OWNER), dp.CODE_SIZE)
        for row in old:
            if row['owner']=='nfl2k5_xbe_space_directory':
                continue  # allocator-owned directory must describe the appended owner
            a=row['raw'];n=row['size']
            self.assertEqual(self.before[a:a+n],self.after[a:a+n],row['owner'])
        self.assertEqual(dp.apply(self.after,self.plan)[0],self.after)
        self.assertEqual(dp.apply(self.after,self.plan)[1]['changed_bytes'],0)
        self.assertEqual(len(self.before),len(self.after))

    def test_foreign_context_code_table_and_wrong_calendar_refused(self):
        for va in (dp.SITE,0x13EF75,0x31E440,dp.allocation(self.after)['va']):
            bad=bytearray(self.after);bad[XbeImage(self.after).offset(va)]^=1
            self.assertEqual(dp.status(bytes(bad)),'foreign')
            with self.assertRaises(ValueError):dp.apply(bytes(bad),self.plan)
        p=copy.deepcopy(self.plan);p['base_season']=2027
        for row in p['picks']:row['year']+=1
        with self.assertRaisesRegex(ValueError,'starting season'):dp.apply(self.before,p)
        p=copy.deepcopy(self.plan);p['picks'][0]['owner']=dp.TEAMS[(dp.TEAMS.index(p['picks'][0]['owner'])+1)%32]
        with self.assertRaisesRegex(ValueError,'different ownership'):dp.apply(self.after,p)

    def test_studio_final_stage_matches_native_writer(self):
        from mod_editor.core import mod_build as build, nfl2k5_roster_records as rr
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'default.xbe';target.write_bytes(self.before)
            document=root/'roster-edits.json'
            document.write_text(json.dumps(dict(schema=rr.EDITS_SCHEMA,edits=[],draft_pick_ownership=self.plan)),newline='\n')
            plan=build.BuildPlan('source',str(target),roster_edits=str(document))
            receipt={'steps':[]}
            with patch.object(build,'_core_module',side_effect=lambda name:{'nfl2k5_roster_records':rr,'nfl2k5_draft_picks':dp}[name]):
                build._apply_draft_pick_ownership(plan,target,receipt,lambda *a:None)
            self.assertEqual(target.read_bytes(),self.after)
            self.assertEqual(receipt['steps'][0]['step'],'draft_pick_ownership')

    def test_byte_scope_is_only_initializer_hook_and_allocator_seals(self):
        image=XbeImage(self.after);row=dp.allocation(self.after)
        allowed=[(row['raw'],row['raw']+row['size']),
                 (image.offset(dp.SITE),image.offset(dp.SITE)+5),
                 (space.SCALE_DIRECTORY,space.SCALE_DIRECTORY+space.PAGE),
                 (space.DIRECTORY,space.LIB_COPY),
                 (space.META_START,space.META_START+56*len(space._scale_regions()))]
        allowed += [(s.header+36,s.header+56) for s in image.sections]
        outside=[i for i,(a,b) in enumerate(zip(self.before,self.after)) if a!=b and not any(lo<=i<hi for lo,hi in allowed)]
        self.assertEqual(outside,[])

    def seed_native(self):
        uc=self.machine(self.after)
        uc.mem_write(0xE576A0,struct.pack('<I',2))
        uc.mem_write(dp.BANK-8,b'\xa5'*464)
        # Execute the actual 32-club x seven-round native reset, then our call,
        # stopping at the first following native instruction.
        uc.emu_start(0x13EF60,dp.SITE+5,count=20000)
        self.assertEqual(uc.reg_read(x.UC_X86_REG_EIP),dp.SITE+5)
        self.assertEqual(bytes(uc.mem_read(dp.BANK,448)),self.table)
        return uc

    def test_real_init_all_448_and_native_rollover_twice(self):
        uc=self.seed_native();self.assertEqual(bytes(uc.mem_read(dp.BANK-8,8)),b'\xa5'*8)
        self.assertEqual(bytes(uc.mem_read(dp.BANK+448,8)),b'\xa5'*8)
        # No draft-player fixtures needed: empty drafted-player list. Execute
        # the entire native annual function, including both owner loops.
        uc.mem_write(0x31DD50,b'\x31\xc0\xc3')
        self.call(0x31E430)
        retail=bytes(range(32))*7
        self.assertEqual(bytes(uc.mem_read(dp.BANK,448)),self.table[224:]+retail)
        self.call(0x31E430)
        self.assertEqual(bytes(uc.mem_read(dp.BANK,448)),retail*2)

    def test_native_trade_screen_enumerates_both_banks_for_all_teams(self):
        uc=self.seed_native()
        # Screen context setup and stage getter are outside the owner traversal.
        uc.mem_write(0x2B8D70,b'\xc3');uc.mem_write(0xC4BB0,b'\x31\xc0\xc3')
        for i,t in enumerate(dp.TEAMS):
            uc.mem_write(0xCB8C60,bytes([i]));self.call(0x3482E0)
            count=self.table.count(i);self.assertEqual(uc.reg_read(x.UC_X86_REG_EAX),count,t)
            actual=[]
            for n in range(count):
                uc.reg_write(x.UC_X86_REG_ECX,n);self.call(0x348360)
                ident=uc.reg_read(x.UC_X86_REG_EAX);bank=ident//500;cell=ident%500
                actual.append((bank,cell//32,cell%32))
            expected=[(a//224,(a%224)//32,a%32) for a,v in enumerate(self.table) if v==i]
            self.assertEqual(actual,expected,t)

    def test_native_upcoming_draft_consumes_first_bank(self):
        uc=self.seed_native()
        # Return the requested club index instead of a roster pointer; preserve
        # the actual bank/round/slot lookup and its tail call to the team getter.
        uc.mem_write(0xC4C50,b'\x8b\xc1\xc3')
        for cell in range(224):
            uc.mem_write(0xE3C0A8,struct.pack('<I',cell//32))
            uc.mem_write(0xE3C0A4,struct.pack('<I',cell%32))
            self.call(0x3254D0)
            self.assertEqual(uc.reg_read(x.UC_X86_REG_EAX),self.table[cell])

    def test_mycareer_context_accepts_only_validated_pick_owner(self):
        from mod_editor.core import nfl2k5_my_career_mode as career
        self.assertEqual(career.status(self.before),'applied')
        self.assertEqual(career.status(self.after),'applied')
        bad=bytearray(self.after);bad[XbeImage(self.after).offset(dp.SITE)+1]^=1
        self.assertEqual(career.status(bytes(bad)),'foreign')


if __name__=='__main__':unittest.main()
