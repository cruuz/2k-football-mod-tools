"""Exercise the compiled preflight, release and zero-contract guards without a private disc."""
import struct
import unittest

from mod_editor.core import nfl2k5_franchise_ownership as owner


class NativeOwnership:
    CODE = 0x1100000
    ROOT = 0x800000
    TEAMS = 0x810000
    PLAYERS = 0x820000
    FREE = 0x830000
    IR = 0x840000
    OFFER = 0x850000
    STACK = 0x860800
    STOP = 0x870000

    def __init__(self):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
        from unicorn import x86_const
        self.regs = x86_const
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(0x10000,0x1200000)
        self.uc.mem_write(self.CODE,owner.code_for(self.CODE,self.IR))
        self.put(0xB72918,self.ROOT)
        self.put(0xE576A0,2)
        self.put(self.ROOT,1024)
        self.put(self.ROOT+4,self.PLAYERS)
        self.put(self.ROOT+0x18,32)
        self.put(self.ROOT+0x1C,self.TEAMS)
        self.put(self.ROOT+0x3C,self.FREE)
        self.put(self.OFFER+8,self.club(7))
        self.put(self.OFFER+32,self.club(19))
        self.uc.mem_write(0xC4C50,b'\x69\xc1'+struct.pack('<I',500)+b'\x05'+struct.pack('<I',self.TEAMS)+b'\xc3')
        for club in range(32):
            self.uc.mem_write(self.club(club)+0x11C,b'\x04')
            for slot in range(4): self.put(self.club(club)+slot*4,self.player(club,slot))
        # The original validation and cut destinations serve as markers for the normal path.
        self.uc.mem_write(0x2BC380,b'\xb8\x2a\x00\x00\x00\xc2\x08\x00')
        self.uc.mem_write(0x2BD906,b'\x5f\x5e\xb8\x2b\x00\x00\x00\xc2\x08\x00')
        self.uc.mem_write(0xE5FF0,b'\x89\xc8\xc3')
        self.uc.mem_write(0x2BCF69,b'\xc3')
        self.visits=[]
        for ip in (0x2BC380,0x2BD906,0xE5FF0,0x2BCF69):
            self.uc.hook_add(UC_HOOK_CODE,lambda _u,at,*_:self.visits.append(at),begin=ip,end=ip)

    def put(self,where,value):self.uc.mem_write(where,struct.pack('<I',value))
    def club(self,i):return self.TEAMS+i*500
    def player(self,club,slot):return self.PLAYERS+(club*4+slot)*84
    def reg(self,name):return getattr(self.regs,'UC_X86_REG_'+name)
    def call(self,entry,ecx=0,edx=0,esi=0,arguments=()):
        self.visits.clear()
        registers={'EDI':0x23456789,'ESI':esi,'EBP':0x3456789A,'EBX':0x456789AB,'EAX':0x126789AB,
                   'ECX':ecx,'EDX':edx,'EFLAGS':0x246,'ESP':self.STACK}
        for key,value in registers.items():self.uc.reg_write(self.reg(key),value)
        self.put(self.STACK,self.STOP)
        for i,value in enumerate(arguments,1):self.put(self.STACK+i*4,value)
        pc=self.CODE+owner.runtime.LABELS[entry]
        self.uc.emu_start(pc,self.STOP,count=4_000_000)
        assert self.uc.reg_read(self.reg('EIP')) == self.STOP
        assert self.uc.reg_read(self.reg('ESP')) == self.STACK+4+4*len(arguments)
        for key in ('ESI','EDI','EBX','EBP'):assert self.uc.reg_read(self.reg(key))==registers[key]
        return self.uc.reg_read(self.reg('EAX'))

    def domain(self):
        return bytes(self.uc.mem_read(self.ROOT,0x51000)),bytes(self.uc.mem_read(0xE421E0,640))

    def set_ir(self,club,slot,player):
        block=self.IR+64+club*164
        self.uc.mem_write(block,bytes([slot+1]))
        for i in range(slot+1):
            self.uc.mem_write(block+4+8*i,struct.pack('<IhBB',self.PLAYERS+(360+i)*84,2+i,0,1))
        self.uc.mem_write(block+4+8*slot,struct.pack('<IhBB',player,9,0,1))
        for i in range(min(slot+1,5)):
            self.uc.mem_write(0xE421E0+club*20+4*i,bytes(self.uc.mem_read(block+4+8*i,4)))
        return block


class FranchiseOwnershipTests(unittest.TestCase):
    def test_relocations_and_hooks_fit_the_named_allocations(self):
        for base in (0x14DA000,0x1523130,0x1524000):
            data=owner.code_for(base,0x14F3000)
            self.assertEqual(len(data),owner.CODE_SIZE)
            self.assertEqual(struct.unpack_from('<I',data,owner.runtime.LABELS['ownership_store'])[0],0x14F3000)
            for (at,old,symbol,opcode),(_,original,patched) in zip(owner.HOOKS,owner.sites(base),strict=True):
                self.assertEqual(old,original)
                self.assertEqual(len(patched),len(old))
                self.assertEqual(patched[0],opcode)
                self.assertEqual(at+5+struct.unpack_from('<i',patched,1)[0],base+owner.runtime.LABELS[symbol])

    def setUp(self):
        if self._testMethodName!='test_relocations_and_hooks_fit_the_named_allocations':
            try: self.m=NativeOwnership()
            except ImportError as exc: self.skipTest(str(exc))

    def test_every_trade_slot_and_both_sides_recheck_the_current_owner_before_payment(self):
        m=self.m
        for side,club in enumerate((7,19)):
            for slot in range(3):
                field=m.OFFER+(3+6*side+slot)*4
                rightful=m.player(club,slot)
                for who,expected in ((rightful,42),(m.player(5,2),0),(m.PLAYERS+340*84,0)):
                    with self.subTest(side=side,slot=slot,player=who):
                        m.put(field,who);before=m.domain()
                        self.assertEqual(m.call('ownership_trade_stub',ecx=m.OFFER,arguments=(0,0)),expected)
                        self.assertEqual(m.visits,[0x2BC380] if expected else [])
                        self.assertEqual(m.domain(),before)
                m.put(field,0)
        self.assertEqual(m.call('ownership_trade_stub',ecx=m.OFFER,arguments=(0,0)),42) # pick-only proposal

    def test_a_healthy_or_injured_active_player_passes_to_the_native_physical_and_caps(self):
        m=self.m;p=m.player(7,0);m.put(m.OFFER+12,p)
        for status in range(8):
            with self.subTest(status=status):
                m.put(p+0x20,0x80400000);m.put(p+0x24,status<<28)
                self.assertEqual(m.call('ownership_trade_stub',ecx=m.OFFER,arguments=(0,0)),42)
                self.assertEqual(m.visits,[0x2BC380])

    def test_duplicate_offer_and_each_competing_ownership_are_rejected_atomically(self):
        m=self.m;p=m.player(7,1);m.put(m.OFFER+12,p);m.put(m.OFFER+16,p)
        self.assertEqual(m.call('ownership_trade_stub',ecx=m.OFFER,arguments=(0,0)),0);m.put(m.OFFER+16,0)
        for bank in (0,4,5,19):
            block=m.set_ir(26,bank,p);before=m.domain()
            self.assertEqual(m.call('ownership_trade_stub',ecx=m.OFFER,arguments=(0,0)),0);self.assertEqual(m.domain(),before)
            m.uc.mem_write(block,bytes(164));m.uc.mem_write(0xE421E0+26*20,bytes(20))
        m.put(m.ROOT+0x38,1);m.put(m.FREE,p)
        self.assertEqual(m.call('ownership_trade_stub',ecx=m.OFFER,arguments=(0,0)),0)
        m.put(m.ROOT+0x38,0);m.put(m.FREE,0);club=m.club(21)
        m.uc.mem_write(club+0x19B,b'\x01');m.uc.mem_write(club+0x1F2,b'\x01\xa5');m.put(club+16,p)
        self.assertEqual(m.call('ownership_trade_stub',ecx=m.OFFER,arguments=(0,0)),0)

    def test_release_of_an_ir_player_clears_only_its_slot_and_repeated_release_stays_out_of_native_finance(self):
        m=self.m;p=m.PLAYERS+299*84
        for slot in (0,4,5,19):
            with self.subTest(slot=slot):
                block=m.set_ir(26,slot,p);before=bytes(m.uc.mem_read(block+4,slot*8)) if slot else b''
                self.assertEqual(m.call('ownership_release_stub',ecx=m.club(26),edx=p,arguments=(1,1)),43)
                self.assertEqual(m.uc.mem_read(block,1)[0],slot)
                if slot:self.assertEqual(bytes(m.uc.mem_read(block+4,slot*8)),before)
                self.assertEqual(bytes(m.uc.mem_read(block+4+slot*8,8)),bytes(8))
                self.assertEqual(m.call('ownership_release_stub',ecx=m.club(26),edx=p,arguments=(1,1)),0)
                self.assertEqual(m.visits,[])

    def test_ir_placement_and_ordinary_active_removal_keep_the_new_ir_membership(self):
        m=self.m;p=m.player(7,0);m.set_ir(7,0,p);prior=m.domain()
        self.assertEqual(m.call('ownership_release_stub',ecx=m.club(7),edx=p,arguments=(0,0)),43)
        self.assertEqual(m.domain(),prior)

    def test_explicit_practice_roster_release_removes_only_the_requested_reserve(self):
        m = self.m
        club = m.club(7)
        target = m.PLAYERS + 299 * 84
        neighbour = m.PLAYERS + 298 * 84
        m.uc.mem_write(club + 0x19B, bytes([1]))
        m.uc.mem_write(club + 0x1F2, bytes([2, 0xA5]))
        m.put(club + 16, target)
        m.put(club + 20, neighbour)
        self.assertEqual(m.call('ownership_release_stub', ecx=club, edx=target, arguments=(1, 1)), 43)
        self.assertEqual(bytes(m.uc.mem_read(club + 16, 8)), struct.pack('<2I', neighbour, 0))
        self.assertEqual(bytes(m.uc.mem_read(club + 0x1F2, 2)), bytes([1, 0xA5]))
        self.assertEqual(m.call('ownership_release_stub', ecx=club, edx=target, arguments=(1, 1)), 0)

    def test_invalid_squad_metadata_leaves_the_source_ir_and_contract_together(self):
        m = self.m
        player = m.PLAYERS + 299 * 84
        m.set_ir(26, 0, player)
        other = m.club(13)
        m.uc.mem_write(other + 0x19B, bytes([2]))
        m.uc.mem_write(other + 0x1F2, bytes([1, 0xA5]))
        before = m.domain()
        self.assertEqual(m.call('ownership_release_stub', ecx=m.club(26), edx=player, arguments=(1, 1)), 0)
        self.assertEqual(m.domain(), before)
        self.assertEqual(m.visits, [])

    def test_existing_free_agent_aliases_are_removed_before_the_single_native_release(self):
        m = self.m
        player = m.player(7, 2)
        neighbours = [m.PLAYERS + i * 84 for i in (299, 345)]
        m.put(m.ROOT + 0x38, 4)
        m.uc.mem_write(m.FREE, struct.pack('<4I', player, neighbours[0], player, neighbours[1]))
        self.assertEqual(m.call('ownership_release_stub', ecx=m.club(7), edx=player, arguments=(1, 1)), 43)
        self.assertEqual(bytes(m.uc.mem_read(m.FREE, 16)), struct.pack('<4I', *neighbours, 0, 0))
        self.assertEqual(bytes(m.uc.mem_read(m.ROOT + 0x38, 4)), struct.pack('<I', 2))
        self.assertEqual(m.visits, [0x2BD906])

    def test_zero_years_preserves_player_fields_and_all_positive_terms_reach_stock_proration(self):
        m=self.m;p=m.player(19,1)
        for years in range(16):
            with self.subTest(years=years):
                m.uc.mem_write(p+0x27,bytes([0xB0|years]));before=m.domain()
                m.call('ownership_contract_stub',esi=p)
                self.assertEqual(m.visits,[0xE5FF0,0x2BCF69] if years else [])
                self.assertEqual(m.domain(),before)


if __name__=='__main__':unittest.main()
