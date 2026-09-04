"""Storage tests without game data, plus bounded execution of the retail XBE.

No xemu, GUI, audio, external writes, or proprietary fixtures. All executable
and ROST mutations stay in private Unicorn memory. Optional inputs skip with
specific reasons; tests that run use the actual retail loader and serializer.
"""
from pathlib import Path
import hashlib
import os
import struct
import unittest

from mod_editor.core import nfl2k5_practice_squad as ps

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)' / 'default.xbe'
try:
    import unicorn as uni
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX,
        UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI,
        UC_X86_REG_EBP)
except ImportError:
    uni = None


class StorageTests(unittest.TestCase):
    COORDS = dict(team_offset=0x2000, player_pool_offset=0x1000, player_count=100)

    def test_twelve_relocated_references_preserve_cap_and_statistics(self):
        raw = bytearray(500)
        raw[0x19a:]=bytes(range(90))
        for off in (ps.VERSION_OFFSET,ps.COUNT,ps.MARKER_OFFSET): raw[off]=0
        for n in (0,1,11,12):
            after=ps.set_reserve_list(raw,range(n),**self.COORDS)
            self.assertEqual(ps.reserve_list(after,team_offset=0x2000,player_pool_offset=0x1000),tuple(range(n)))
            self.assertEqual(after[4*n:260],bytes(260-4*n))
            allowed=set(range(260))|{ps.VERSION_OFFSET,ps.COUNT,ps.MARKER_OFFSET}
            self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(raw,after)) if i not in allowed))
        self.assertEqual(ps.reserve_list(bytes(500)),())

    def test_invalid_unknown_storage_and_physical_capacity(self):
        for values in (range(13),range(16),[1,1],[-1],[True],[1.0],['1'],[100]):
            with self.subTest(values=values),self.assertRaises(ps.PracticeSquadError):
                ps.set_reserve_list(bytes(500),values,**self.COORDS)
        for off,value in ((ps.VERSION_OFFSET,2),(ps.COUNT,13),(ps.MARKER_OFFSET,1),(0,1)):
            data=bytearray(ps.set_reserve_list(bytes(500),[]));data[off]=value
            with self.subTest(off=off),self.assertRaises(ps.PracticeSquadError):ps.reserve_list(data)
        for raw in (bytes(499),bytes(501)):
            with self.assertRaises(ps.PracticeSquadError):ps.reserve_list(raw)
        raw=bytearray(500);raw[ps.ACTIVE_COUNT]=54
        for i in range(54):struct.pack_into('<i',raw,4*i,0x1000+84*i-4*i+1)
        with self.assertRaises(ps.PracticeSquadError):
            ps.set_reserve_list(raw,range(60,72),team_offset=0,player_pool_offset=0x1000)

    def test_compaction_requires_complete_explicit_mapping(self):
        raw=ps.set_reserve_list(bytes(500),[0,7,23],**self.COORDS)
        with self.assertRaises(ps.PracticeSquadError):
            ps.remap_reserve_list(raw,{0:0,23:5},**self.COORDS)
        out=ps.remap_reserve_list(raw,{0:0,7:None,23:5},**self.COORDS)
        self.assertEqual(ps.reserve_list(out,team_offset=0x2000,player_pool_offset=0x1000),(0,5))
        with self.assertRaises(ps.PracticeSquadError):
            ps.remap_reserve_list(raw,{0:0,7:0,23:5},**self.COORDS)

    def test_bad_xbe_is_foreign(self):
        for raw in (b'',b'XBEH',bytes(1000)):
            self.assertEqual(ps.status(raw),'foreign')
            with self.assertRaises(ps.PracticeSquadError):ps.apply(raw)


@unittest.skipUnless(XBE.is_file(), 'private retail NFL 2K5 default.xbe absent (NFL2K5_RETAIL_EXTRACTION)')
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail=XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest()!=ps.RETAIL_SHA256:
            raise unittest.SkipTest('private XBE is not the pinned US retail executable')
        cls.patched,cls.receipt=ps.apply(cls.retail)

    def test_pins_idempotence_and_section_digests(self):
        self.assertEqual(ps.status(self.retail),'retail')
        self.assertEqual(ps.status(self.patched),'applied')
        again,receipt=ps.apply(self.patched)
        self.assertEqual(again,self.patched); self.assertEqual(receipt['changed_bytes'],0)
        for section in ps._sections(self.patched):
            self.assertEqual(section.stored_digest, ps.section_digest(self.patched,section))
        self.assertEqual(len(self.retail),len(self.patched))

    def test_partial_or_conflicting_code_is_refused(self):
        for site in ps.sites():
            data=bytearray(self.retail)
            off=ps._offset(data,site.va,ps._sections(data))
            data[off:off+site.size]=site.patched
            self.assertEqual(ps.status(data),'foreign')
            with self.assertRaises(ps.PracticeSquadError): ps.apply(data)
            data=bytearray(self.retail); data[off]^=0x55
            self.assertEqual(ps.status(data),'foreign')


@unittest.skipUnless(XBE.is_file() and uni is not None,
                     'private retail XBE or optional unicorn package absent')
class ExecutionTests(PatchTests):
    BASE=0x02000000
    OUT=0x02400000
    STACK=0x03008000
    STOP=0x03100000

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from mod_editor.core import nfl2k5_team_history as th
        try:
            with th._outer_image()(XBE.parent) as archive:
                entry=th._entry(archive)
                cls.body=archive.read(entry.virtual_offset,entry.size)[th.RESOURCE_HEADER_SIZE:]
        except (FileNotFoundError, OSError) as exc:
            raise unittest.SkipTest(f'private retail pack-0 ROST absent: {exc}') from exc

    def setUp(self):
        self.uc=uni.Uc(uni.UC_ARCH_X86,uni.UC_MODE_32)
        self.uc.mem_map(0x10000,0xFF0000)
        for section in ps._sections(self.patched):
            self.uc.mem_write(section.virtual_address,self.patched[section.raw_offset:section.raw_offset+section.raw_size])
        self.uc.mem_protect(0x11000,0x410000,uni.UC_PROT_READ|uni.UC_PROT_EXEC)
        self.uc.mem_map(self.BASE,0x200000)
        self.uc.mem_map(self.OUT,0x200000)
        self.uc.mem_map(0x03000000,0x10000)
        self.uc.mem_map(self.STOP,0x1000)
        self.uc.mem_write(self.BASE,self.body)
        self.root=self.BASE+0x40
        self.put(0xB72918,self.root)
        self.call(0xC0500,ecx=self.root)
        self.teams=self.word(self.root+0x1c)
        self.pool=self.word(self.root+4)
        self.team=self.teams
        for r,v in ((0xE576A0,1),(0xE576A4,7),(0xE576AC,32)):
            self.put(r,v)
        for i in range(32): self.put(0xE5786C+4*i,self.teams+500*i)
        self.uc.mem_write(0xE5775C,bytes(32*4))
        self.uc.mem_write(0xE421E0,bytes(160*4))

    def word(self,a): return struct.unpack('<I',self.uc.mem_read(a,4))[0]
    def put(self,a,v): self.uc.mem_write(a,struct.pack('<I',v))
    def byte(self,a): return self.uc.mem_read(a,1)[0]
    def record(self,t=None): return bytes(self.uc.mem_read(t or self.team,500))
    def reserves(self,t=None):
        t=t or self.team; data=bytearray(self.record(t))
        for i in range(65):
            value=self.word(t+4*i)
            struct.pack_into('<i',data,4*i,value-t-4*i+1 if value else 0)
        return ps.reserve_list(data,team_offset=t,player_pool_offset=self.pool)

    def call(self,address,*,ecx=0,edx=0,eax=0,args=(),budget=3000000):
        if isinstance(address,str): address=ps.SYMBOLS[address]
        self.uc.mem_write(self.STACK,struct.pack('<'+'I'*(1+len(args)),self.STOP,*args))
        for r,v in ((UC_X86_REG_ESP,self.STACK),(UC_X86_REG_ECX,ecx),(UC_X86_REG_EDX,edx),(UC_X86_REG_EAX,eax),
                    (UC_X86_REG_EBX,0x11111111),(UC_X86_REG_ESI,0x22222222),(UC_X86_REG_EDI,0x33333333),(UC_X86_REG_EBP,0x44444444)):
            self.uc.reg_write(r,v)
        try:
            self.uc.emu_start(address,self.STOP,count=budget)
        except uni.UcError as exc:
            raise AssertionError(f'{address:#x} fault at {self.uc.reg_read(UC_X86_REG_EIP):#x}: {exc}') from exc
        self.assertEqual(self.uc.reg_read(UC_X86_REG_EIP),self.STOP,f'{address:#x}: exhausted {budget} instructions')
        for r,v in ((UC_X86_REG_EBX,0x11111111),(UC_X86_REG_ESI,0x22222222),(UC_X86_REG_EDI,0x33333333),(UC_X86_REG_EBP,0x44444444)):
            self.assertEqual(self.uc.reg_read(r),v,f'{address:#x}: clobbered callee-saved register')
        self.assertEqual(self.uc.reg_read(UC_X86_REG_ESP),self.STACK+4+4*len(args),f'{address:#x}: unbalanced stack')
        return self.uc.reg_read(UC_X86_REG_EAX)

    def take_fa(self):
        count=self.word(self.root+0x38); table=self.word(self.root+0x3c)
        p=self.word(table)
        # Fixture setup: complete a FA-to-team ownership transfer, independent
        # of the production reserve transactions under test.
        data=bytes(self.uc.mem_read(table+4,4*(count-1)))
        self.uc.mem_write(table,data+b'\0'*4); self.put(self.root+0x38,count-1)
        self.put(p+0x24,(self.word(p+0x24)&~0x0f00000f)|0x02000002)
        self.uc.mem_write(p+0x0a,struct.pack('<H',100))
        return p

    def fill_twelve(self):
        players=[]
        for i in range(12):
            p=self.word(self.team+4*(self.byte(self.team+0x11c)-1)); players.append(p)
            self.assertEqual(self.call('ps_demote',ecx=self.team,edx=p),1)
        for i in range(12): self.assertEqual(self.call(0xC3EE0,ecx=self.team,edx=self.take_fa()),1)
        return players

    def test_demote_promote_capacity_ownership_and_rollbacks(self):
        players=self.fill_twelve()
        self.assertEqual(self.byte(self.team+0x11c),53)
        self.assertEqual(len(self.reserves()),12)
        before=self.record()
        self.assertEqual(self.call('ps_promote',ecx=self.team,edx=players[0]),0)
        self.assertEqual(self.call('ps_demote',ecx=self.team,edx=self.word(self.team)),0)
        self.assertEqual(self.record(),before)
        self.assertEqual(self.call(0xC3EE0,ecx=self.team+500,edx=players[0]),0)
        self.assertEqual(self.call(0x242560,ecx=self.root+0x38,edx=players[0]),0)
        # A normal active release creates capacity; promotion commits afterward.
        self.assertEqual(self.call(0xC3EB0,ecx=self.team,edx=self.word(self.team)),1)
        self.assertEqual(self.call('ps_promote',ecx=self.team,edx=players[0]),1)
        self.assertEqual(self.byte(self.team+0x11c),53)
        self.assertEqual(len(self.reserves()),11)
        self.assertEqual(self.word(self.team+52*4),players[0])

    def test_real_cpu_gate_captures_twelve_cuts_and_saves_reload(self):
        for i in range(12): self.assertEqual(self.call(0xC3EE0,ecx=self.team,edx=self.take_fa()),1)
        self.assertEqual(self.byte(self.team+0x11c),65)
        self.call(0x2BFAA0,budget=8000000)
        self.assertEqual(self.byte(self.team+0x11c),53)
        self.assertEqual(len(self.reserves()),12)
        before=bytes(self.uc.mem_read(self.BASE,len(self.body)))
        self.call(0xC0730,ecx=self.root)
        saved=bytes(self.uc.mem_read(self.BASE,len(self.body)))
        ps.validate_roster(saved)
        self.call(0xC0500,ecx=self.root)
        self.assertEqual(bytes(self.uc.mem_read(self.BASE,len(self.body))),before)

    def test_combined_patch_cpu_gate_and_save_reload(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        flags={name:True for name in ('catch_slider','accel_ramp','draft_ai','edge_rename',
            'returner_fix','progression','scheme_labels','camera','kick_rules','widescreen',
            'overtime','team_column','seven_on_seven')}
        combined,_=tt._apply_all(self.retail,None,**flags,arc_table=False,kick_power=False,
            penalties='nfl',uniform_choice='choice',kick_laces=True,franchise_practice=True,
            prospect_names='modern',player_star=True)
        combined,_=ps.apply(combined)
        for section in ps._sections(combined):
            self.uc.mem_write(section.virtual_address,combined[section.raw_offset:section.raw_offset+section.raw_size])
        # Loading executable data reset the fixture's runtime globals.
        self.put(0xB72918,self.root)
        for r,v in ((0xE576A0,1),(0xE576A4,7),(0xE576AC,32)): self.put(r,v)
        for i in range(32): self.put(0xE5786C+4*i,self.teams+500*i)
        self.uc.mem_write(0xE5775C,bytes(128)); self.uc.mem_write(0xE421E0,bytes(640))
        self.test_real_cpu_gate_captures_twelve_cuts_and_saves_reload()

    def test_twelve_survive_full_loader_serializer_and_rating(self):
        self.fill_twelve()
        with_squad=self.record()
        self.call(0xC46B0,ecx=self.team)
        from unicorn.x86_const import UC_X86_REG_ST0
        rating=self.uc.reg_read(UC_X86_REG_ST0)
        self.assertNotEqual(rating,0)
        empty=ps.set_reserve_list(self.record(),[])
        self.uc.mem_write(self.team,empty)
        self.call(0xC46B0,ecx=self.team)
        self.assertEqual(self.uc.reg_read(UC_X86_REG_ST0),rating)
        self.uc.mem_write(self.team,with_squad)
        self.call(0xC0730,ecx=self.root)
        saved=bytes(self.uc.mem_read(self.BASE,len(self.body)))
        self.assertEqual(len(ps.validate_roster(saved)[0]),12)
        self.call(0xC0500,ecx=self.root)
        self.assertEqual(self.record(),with_squad)

    def test_record_reuse_purges_reserve_before_draft_reallocation(self):
        p=self.word(self.team+52*4)
        self.assertEqual(self.call('ps_demote',ecx=self.team,edx=p),1)
        self.call(0xE64D0,ecx=p)
        self.assertEqual(self.reserves(),())
        self.assertEqual(self.byte(p+8)&4,0)

    def test_real_draft_allocator_skips_live_reserves(self):
        players=self.fill_twelve()
        # Isolate a single free slot after every reserve in the primary pool.
        n=self.word(self.root)
        for i in range(n):
            p=self.pool+84*i
            self.uc.mem_write(p+8,bytes([self.byte(p+8)|4]))
        free=self.pool+84*(n-1)
        self.uc.mem_write(free+8,bytes([self.byte(free+8)&~4]))
        self.assertEqual(self.call(0x2BD390,ecx=self.OUT),free)
        self.assertEqual(struct.unpack('<H',self.uc.mem_read(self.OUT,2))[0],n-1)
        self.assertEqual(self.reserves(),tuple((p-self.pool)//84 for p in players))

    def test_stats_reset_disproves_sixteen_index_tail_and_preserves_fallback(self):
        self.fill_twelve()
        # The original proposal would put eight of its index bytes here.
        self.uc.mem_write(self.team+0x1aa,bytes.fromhex('7856341201020304'))
        self.uc.mem_write(self.team+0x19c,bytes(range(14)))
        before=self.reserves()
        self.call(0xC3F60,ecx=self.team)
        self.assertEqual(bytes(self.uc.mem_read(self.team+0x1aa,8)),bytes(8))
        self.assertEqual(bytes(self.uc.mem_read(self.team+0x19c,14)),bytes(range(14)))
        self.assertEqual(self.reserves(),before)

    def test_export_includes_twelve_and_remaps_indices(self):
        players=self.fill_twelve()
        self.call(0xC0FA0,ecx=self.OUT,edx=self.team)
        self.assertEqual(self.word(self.OUT),65)
        # C0FA0 returns serialized root with college IDs (retail team-save ABI).
        team=self.OUT+0x1c+self.word(self.OUT+0x1c)-1
        pool=self.OUT+4+self.word(self.OUT+4)-1
        self.assertEqual(ps.reserve_list(bytes(self.uc.mem_read(team,500)),team_offset=team,player_pool_offset=pool),tuple(range(53,65)))
        self.assertEqual(self.byte(team+0x11c),53)
        # Replacing the source pool indices must not affect the source records.
        self.assertEqual(self.reserves(),tuple((p-self.pool)//84 for p in players))

    def test_complete_import_remaps_reserves_and_restores_source(self):
        self.fill_twelve()
        self.call(0xC0FA0,ecx=self.OUT,edx=self.team)
        source=bytes(self.uc.mem_read(self.OUT,20000))
        destination=self.teams+32*500  # Empty retail created-team template.
        self.assertEqual(self.call(0xC1030,ecx=self.OUT,edx=destination,budget=16000000),1)
        self.assertEqual(self.byte(destination+0x11c),53)
        self.assertEqual(self.reserves(destination),tuple(range(2377,2389)))
        self.assertEqual(bytes(self.uc.mem_read(self.OUT,20000)),source)
        imported=self.record(destination)
        self.assertEqual(self.call(0xC1030,ecx=self.OUT,edx=destination),0)
        self.assertEqual(self.record(destination),imported)
        self.assertEqual(bytes(self.uc.mem_read(self.OUT,20000)),source)
        self.call(0xC0730,ecx=self.root)
        self.assertEqual(ps.validate_roster(bytes(self.uc.mem_read(self.BASE,len(self.body))))[32],tuple(range(2377,2389)))

    def test_import_refuses_insufficient_pool_without_mutation(self):
        self.fill_twelve()
        self.call(0xC0FA0,ecx=self.OUT,edx=self.team)
        for i in range(self.word(self.root)):
            p=self.pool+84*i
            self.uc.mem_write(p+8,bytes([self.byte(p+8)|4]))
        source=bytes(self.uc.mem_read(self.OUT,20000))
        arena=bytes(self.uc.mem_read(self.BASE,len(self.body)))
        self.assertEqual(self.call(0xC1030,ecx=self.OUT,edx=self.teams+32*500,budget=16000000),0)
        self.assertEqual(bytes(self.uc.mem_read(self.OUT,20000)),source)
        self.assertEqual(bytes(self.uc.mem_read(self.BASE,len(self.body))),arena)

    def test_complete_two_team_export_includes_reserves(self):
        self.fill_twelve()
        before=self.record(); other=self.record(self.team+500)
        root=self.call(0xC0B90,ecx=self.team,edx=self.team+500,args=(0,self.OUT))
        self.assertEqual(root,self.OUT)
        self.assertEqual(self.word(root),118)
        teams=self.word(root+0x1c)
        self.assertEqual(self.byte(teams+0x11c),53)
        self.assertEqual(self.byte(teams+500+0x11c),53)
        self.assertEqual(self.byte(teams+ps.COUNT),12)
        self.assertEqual(self.record(),before)
        self.assertEqual(self.record(self.team+500),other)

    def test_complete_rollover_retires_and_ages_reserves(self):
        players=self.fill_twelve()
        experience={p:(self.word(p+0x24)>>8)&31 for p in players}
        # Franchise table includes two Pro Bowl placeholders, dropped by retail
        # rollover. The disc fixture has empty templates at these positions.
        self.put(0xE576A4,9); self.put(0xE576AC,34)
        for i in (32,33): self.put(0xE5786C+4*i,self.teams+500*i)
        self.call(0x247B40,budget=16000000)
        survivors={self.pool+84*i for i in self.reserves()}
        self.assertTrue(survivors)
        self.assertTrue(survivors < set(players))
        for p in players:
            if p in survivors:
                self.assertEqual((self.word(p+0x24)>>8)&31,(experience[p]+1)&31)
                self.assertEqual(self.byte(p+8)&0x18,0)
            else: self.assertTrue(self.byte(p+8)&8)
        before=self.record()
        self.call(0xC0730,ecx=self.root)
        ps.validate_roster(bytes(self.uc.mem_read(self.BASE,len(self.body))))
        self.call(0xC0500,ecx=self.root)
        self.assertEqual(self.record(),before)

    def test_ir_return_retains_owner_when_physical_roster_full(self):
        self.fill_twelve()
        p=self.take_fa(); self.put(0xE421E0,p); self.put(0xE576A4,9)
        before=self.record()
        self.call(0x246F90)
        self.assertEqual(self.word(0xE421E0),p)
        # C3F00 legitimately recalculates the cap including the retained IR.
        self.assertEqual(self.record()[:260],before[:260])
        self.assertEqual(self.record()[0x19b:],before[0x19b:])
        self.call(0xC3EB0,ecx=self.team,edx=self.word(self.team))
        self.call(0x246F90)
        self.assertEqual(self.word(0xE421E0),0)
        self.assertEqual(self.byte(self.team+0x11c),53)
        self.assertEqual(self.word(self.team+52*4),p)
        self.assertEqual(len(self.reserves()),12)

    def test_full_roster_signing_and_trade_guards_precede_owner_mutation(self):
        self.fill_twelve()
        player=self.word(self.word(self.root+0x3c))
        self.put(self.OUT,player); self.put(self.OUT+4,self.team)
        arena=bytes(self.uc.mem_read(self.BASE,len(self.body)))
        self.assertEqual(self.call('ps_limit',ecx=self.team),53)
        self.assertEqual(self.call('ps_room',ecx=self.team),0)
        self.assertEqual(self.call(0x322BB0,args=(self.team,0,0xffff,0)),0)
        self.call(0x323B30,eax=self.OUT,ecx=0)
        self.call(0x325B50,ecx=player,edx=self.team,args=(0,))
        # Sequential retail trades can need a temporary spare active slot.
        # Refuse before removing either owner when that spare slot is absent.
        trade=self.OUT+0x100
        self.put(trade+8,self.team+500); self.put(trade+32,self.team)
        self.put(trade+12,self.word(self.team+500))
        self.put(trade+36,self.word(self.team))
        self.assertEqual(self.call('ps_trade_room',ecx=trade),0)
        self.assertEqual(self.call(0x2BC670,ecx=trade,args=(0,)),0)
        self.assertEqual(bytes(self.uc.mem_read(self.BASE,len(self.body))),arena)
        self.call(0xC3EB0,ecx=self.team,edx=self.word(self.team))
        self.assertEqual(self.call('ps_room',ecx=self.team),1)
        self.assertEqual(self.call('ps_trade_room',ecx=trade),1)

    def test_draft_signing_with_capacity_preserves_hidden_tail(self):
        self.fill_twelve()
        before=self.reserves()
        self.call(0xC3EB0,ecx=self.team,edx=self.word(self.team))
        player=self.take_fa()
        self.call(0x325B50,ecx=player,edx=self.team,args=(0,))
        self.assertEqual(self.byte(self.team+0x11c),53)
        self.assertEqual(self.word(self.team+52*4),player)
        self.assertEqual(self.reserves(),before)

    def test_capacity_adapters_return_retail_comparison_flags(self):
        from unicorn.x86_const import UC_X86_REG_EFLAGS
        self.assertEqual(self.call('ps_limit',ecx=self.team),65)
        self.put(0xE576A4,8)
        self.assertEqual(self.call('ps_limit',ecx=self.team),53)
        self.put(0xE576A4,7)
        self.fill_twelve()
        self.call('capacity_flags',eax=self.team)
        self.assertEqual(self.uc.reg_read(UC_X86_REG_EFLAGS)&0x41,0x40)
        # The other two adapters use retail ESI rather than a normal argument.
        # Tiny original test thunks preserve ESI around that custom ABI.
        for index,(name,argument) in enumerate((('draft_limit',self.team),('offer_limit',self.OUT+0x100))):
            self.put(self.OUT+0x104,self.team)
            thunk=self.OUT+index*0x20  # Distinct addresses avoid Unicorn's translated-code cache.
            code=b'\x56\x8b\xf1\xe8'+struct.pack('<i',ps.SYMBOLS[name]-thunk-8)+b'\x5e\xc3'
            self.uc.mem_write(thunk,code)
            self.assertEqual(self.call(thunk,ecx=argument),53,name)
        self.call(0xC3EB0,ecx=self.team,edx=self.word(self.team))
        self.call('capacity_flags',eax=self.team)
        self.assertEqual(self.uc.reg_read(UC_X86_REG_EFLAGS)&0x41,1)

    def test_signed_v0_franchise_save_preserves_reserves_and_envelope(self):
        import tempfile
        from mod_editor.core import nfl2k5_save_rost as codec
        from tests.mod_editor.test_nfl2k5_save_rost import HUB,PINS
        for name,digest in PINS.items():
            path=HUB/name/'UDATA/53450030/0B8506889D40/SAVEGAME.DAT'
            if not path.is_file(): self.skipTest(f'private v0 fixture missing: {path}')
            original=path.read_bytes()
            self.assertEqual(hashlib.sha256(original).hexdigest(),digest)
            document,container=codec.load_save(path)
            self.uc.mem_write(self.BASE,original)
            self.root=self.BASE+document.layout.root
            self.put(0xB72918,self.root)
            self.call(0xC0500,ecx=self.root)
            self.teams=self.word(self.root+0x1c); self.team=self.teams; self.pool=self.word(self.root+4)
            p=self.word(self.team+4*(self.byte(self.team+0x11c)-1))
            self.assertEqual(self.call('ps_demote',ecx=self.team,edx=p),1)
            identity=(p-self.pool)//84
            self.call(0xC0730,ecx=self.root)
            output=bytes(self.uc.mem_read(self.BASE,len(original)))
            self.assertEqual(ps.validate_roster(output)[0],(identity,))
            self.assertEqual(output[:document.layout.root],original[:document.layout.root])
            self.assertEqual(output[document.layout.end:],original[document.layout.end:])
            with tempfile.TemporaryDirectory(prefix='practice-squad-save-') as folder:
                target=Path(folder)/'reserve.zip'
                container.write(target,output)
                saved,signed=codec.load_save(target)
                self.assertTrue(signed.verified)
                self.assertEqual(ps.validate_roster(saved.to_bytes())[0],(identity,))
                self.uc.mem_write(self.BASE,saved.to_bytes())
                self.call(0xC0500,ecx=self.root)
                self.assertEqual(self.reserves(),(identity,))
            self.assertEqual(path.read_bytes(),original)


if __name__=='__main__': unittest.main()
