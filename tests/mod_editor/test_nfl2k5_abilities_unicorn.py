"""Standalone bounded x86 proofs of actual installed hooks. UNWITNESSED."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as patch
from mod_editor.core import nfl2k5_abilities_runtime_code as code
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
try:
    import unicorn as uc
    from unicorn import x86_const as x86
    from tests.nfl2k5_abilities_machine import Machine
except ImportError:
    uc=None
RETAIL=Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION','/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)/default.xbe'


@unittest.skipUnless(uc is not None and RETAIL.is_file(), 'Unicorn and pinned USA retail XBE required for bounded instruction proofs')
class InstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail=RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest()!=RETAIL_SHA256: raise unittest.SkipTest('USA retail hash mismatch')
        cls.payload=patch.apply(cls.retail,abilities_off_week=7)[0]

    def test_speed_99_127_bit_on_off_through_both_native_clamps(self):
        m=Machine(self.payload)
        for raw in (0,99,100,127,128,255):
            for bit in (0,patch.SPEEDSTER):
                for injury in (1,.5):
                    with self.subTest(raw=raw,bit=bit,injury=injury):
                        m.player(speed=raw,abilities=bit)
                        native=m.seed_native_speed_cache(injury=injury)
                        m.run('speed',ecx=m.R,args=(0x184,))
                        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP),m.STACK+8)
                        actual=m.pop_float()
                        expected=max(0,min(1,native))
                        expected=expected*raw/100 if bit and 100<=raw<=127 else min(.99,expected)
                        self.assertAlmostEqual(actual,expected,places=6)
        m.player(speed=127,abilities=patch.SPEEDSTER)
        self.assertEqual(m.seed_native_speed_cache(),1)
        m.run('speed',ecx=m.R,args=(0x184,))
        self.assertAlmostEqual(m.pop_float(),1.27,places=6)

    def test_week_predicate_exact_tuple_restore_null_and_preserved_roster_bits(self):
        m=Machine(self.payload)
        original=0xFFFF; m.flags(original)
        for mode in (0,1,2,3):
            for stage in (7,8,9):
                for week in range(18):
                    m.u32(0xE576A0,mode);m.u32(0xE576A4,stage);m.u32(0xE576B4,week)
                    expected=0 if (mode,stage,week)==(2,8,7) else patch.ABILITY_MASK
                    self.assertEqual(m.run('effective',ecx=m.R),expected)
        self.assertEqual(bytes(m.uc.mem_read(m.R+0x52,2)),b'\xff\xff')
        for pointer in (0,0xFFFFFFFF): self.assertEqual(m.run('effective',ecx=pointer),0)
        off=Machine(patch.apply(self.retail,abilities_off_week=None)[0])
        off.u32(0xE576A0,2);off.u32(0xE576B4,7)
        self.assertEqual(off.run('effective',ecx=off.R),patch.ABILITY_MASK)

    def test_every_move_each_required_bit_and_cpu_parity(self):
        m=Machine(self.payload)
        for controller in (0,1,2,3,-1):
            for command,required in patch.MOVE_MASKS.items():
                for flags in (0,required,*[required&~(1<<i) for i in range(13) if required&(1<<i)]):
                    with self.subTest(controller=controller,command=command,flags=flags):
                        m.player(controller=controller,command=command,abilities=flags)
                        m.run('filter',regs={'EBX':m.P})
                        self.assertEqual(m.read(m.T+0x1C),command if flags&required==required else 0)
                        self.assertEqual(m.number(m.T+0x10),.625)
                        self.assertEqual(m.read(m.T+0x14),0x3456)

    def test_passing_kicking_qb_evade_contexts_and_noncarriers_commands_untouched(self):
        m=Machine(self.payload)
        for context in (0,1,3,7,9,11,20):
            m.player(abilities=0,command=0x24,context=context)
            m.run('filter',regs={'EBX':m.P})
            self.assertEqual(m.read(m.T+0x1C),0x24)
        for phase,holder in ((13,m.P),(14,0),(15,m.P),(14,m.P+0x8000)):
            m.player(abilities=0,command=0x24);m.u32(0xE602B8,phase);m.u32(m.BALL,holder)
            m.run('filter',regs={'EBX':m.P})
            self.assertEqual(m.read(m.T+0x1C),0x24)

    def test_stock_direction_gesture_selection_then_actual_decode_and_dispatch_hooks(self):
        m=Machine(self.payload)
        # Execute the real 120EFA..120FBD direction/gesture priority selector.
        for base in (0xA99EC0,0xA9A79C,0xA9B078):
            for context in (8,10):
                for i,flag in enumerate((0x40000,0x80000,0x10000,0x20000)):
                    for gesture in (0,0x10000000):
                        table=base+context*108
                        m.u32(m.STACK+0x100-12,gesture)
                        m.run(0x120EFA,ecx=flag,edx=0,stop=0x120FBD,
                              regs={'EBX':table,'EBP':m.STACK+0x100})
                        column=m.uc.reg_read(x86.UC_X86_REG_EDX)
                        self.assertEqual(column,(23 if gesture else 17)+i)
                        command=m.read(table+column*4)
                        # Decoder peripheral ABI fixture retains the selected
                        # native command; the real replaced call and wrapper run.
                        m.uc.mem_write(0x1211E0,b'\xc3')
                        m.player(command=command,abilities=0,context=context)
                        m.run(0x15647D,stop=0x156482,regs={'EBX':m.P,'ESI':m.T})
                        self.assertEqual(m.read(m.T+0x1C),0)
                        m.player(command=command,abilities=patch.JUKE|patch.RIGHT_STICK,context=context)
                        m.run(0x15647D,stop=0x156482,regs={'EBX':m.P,'ESI':m.T})
                        self.assertEqual(m.read(m.T+0x1C),command)
        # Accounting is peripheral; verify both EDX and callback-index EDI.
        m.uc.mem_write(0x1B3340,b'\xc3')
        for controller in (0,-1):
            for flags in (0,patch.SPIN):
                m.player(controller=controller,command=0x1B,abilities=flags)
                m.run(0x18EC6D,stop=0x18EC72)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EDI),0x1B if flags else 0)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EDX),0x1B if flags else 0)

    def test_per_move_consumption_native_meter_and_stale_steering(self):
        m=Machine(self.payload)
        families={0x18:0x2DCF93,0x19:0x2DCF93,0x1A:0x29089B,0x1B:0x2DC803,0x1C:0x2DC803,
                  0x1D:0x2DC803,0x1E:0x2DC803,0x20:0x2DC803,0x21:0x2DC803,0x22:0x2DC803,
                  0x23:0x30D2C2,**{c:0x306DF7 for c in range(0x24,0x2C)},0x5C:0x2DBBCC,0x5D:0x2DBBCC}
        for controller in (0,-1):
            for state,caller in families.items():
                required=patch.MOVE_MASKS[state]
                for flags in (0,required,patch.ABILITY_MASK&~required):
                    for meter in (.5,1):
                        with self.subTest(state=state,flags=flags,meter=meter,controller=controller):
                            m.player(controller=controller,command=state,abilities=flags)
                            m.u32(m.T+0x1C,0x23 if state!=0x23 else 0x1B)  # deliberately misleading!
                            m.f32(m.S+0x44,meter);m.u32(m.S+0x90,0xA5A50003)
                            m.run(0x2D4740,stop=caller+5,return_address=caller+5)
                            self.assertEqual(m.read(m.S+0x90)&3,1 if flags&required==required and meter==1 else 0)
                            self.assertEqual(m.read(m.S+0x90)&~3,0xA5A50000)
                            self.assertEqual(m.number(m.S+0x44),0)
                            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP),m.STACK+4)

    def test_unknown_mismatched_and_unresearched_consumer_cannot_borrow_permission(self):
        m=Machine(self.payload)
        for caller in (0x18D2C6,0x18DF7C,0x1E773E,0x1E7BA2,0x2319CB,0x291D60,0x308512,0x30EDA7,0x31793D,0x123456,0x30D2C2):
            m.player(command=0x1B);m.f32(m.S+0x44,1);m.u32(m.S+0x90,3)
            m.run('consume',stop=caller+5,return_address=caller+5)
            self.assertEqual(m.read(m.S+0x90)&3,0)
            self.assertEqual(m.number(m.S+0x44),0)

    def test_native_generation_ai_ready_cheat_and_disabled_week(self):
        m=Machine(self.payload)
        for controller in (0,-1):
            for flags in (0,patch.SPIN):
                for cheat in (0,1):
                    m.player(controller=controller,abilities=flags)
                    m.u32(m.S+0x28,0)  # native ordinary state permits charging before action lock
                    m.u32(0xE601E0,cheat);m.u32(0xE5FF80,0)
                    m.f32(0xB71D0C,.2)
                    m.run(0x2D43F0)
                    self.assertEqual(m.read(m.S+0x90)&3,(3 if cheat else 2) if flags else 0)
                    self.assertGreater(m.number(m.S+0x44),0) if flags else self.assertEqual(m.number(m.S+0x44),0)
                    m.run(0x2D46D0)
                    self.assertEqual(m.read(m.S+0x90)&3,3 if flags else 0)
                    self.assertEqual(m.number(m.S+0x44),1 if flags else 0)
        m.player(abilities=patch.SPIN);m.run(0x2D46D0)
        m.u32(0xE576A0,2);m.u32(0xE576A4,8);m.u32(0xE576B4,7)
        for entry in (0x2D43F0,0x2D46D0):
            m.f32(m.S+0x44,1);m.u32(m.S+0x90,1)
            m.run(entry)
            self.assertEqual(m.read(m.S+0x90)&3,0)
            self.assertEqual(m.number(m.S+0x44),0)
        m.u32(0xE576B4,8);m.run(0x2D46D0)
        self.assertEqual(m.number(m.S+0x44),1)

    def test_stale_meter_possession_week_and_player_switch_cleanup(self):
        m=Machine(self.payload)
        for transition in ('lost_ball','dead_phase','removed_bit','off_week','denied_active'):
            m.player(command=0x1B,abilities=patch.SPIN);m.u32(m.BALL,m.P);m.u32(0xE602B8,14);m.u32(0xE576A0,0)
            m.run(0x2D46D0)
            if transition=='lost_ball':m.u32(m.BALL,m.P+0x8000)
            if transition=='dead_phase':m.u32(0xE602B8,13)
            if transition=='removed_bit':m.flags(patch.SPEEDSTER)
            if transition=='off_week':m.u32(0xE576A0,2)
            if transition=='denied_active':m.u32(m.S,0x23);m.u32(m.S+0x90,1)
            m.run('filter',regs={'EBX':m.P})
            self.assertEqual(m.number(m.S+0x44),0,transition)
            self.assertEqual(m.read(m.S+0x90)&3,0,transition)
            self.assertEqual(m.number(m.S+0x48),-1)
        # A different entity cannot reuse the original player's native meter.
        m.player(abilities=patch.SPIN);m.u32(0xE576A0,0);m.u32(0xE602B8,14);m.u32(m.BALL,m.P)
        m.run(0x2D46D0)
        other=m.P+0x8000;other_state=m.P+0x9000;other_steer=m.P+0xA000
        for off,value in ((0x10,other_state),(0xC,other_steer),(0x3C,m.R),(0x1C,1)):m.u32(other+off,value)
        m.u32(other_steer,0);m.u32(m.BALL,other)
        m.run('filter',ecx=other,regs={'EBX':other})
        self.assertEqual(m.number(other_state+0x44),0)
        m.run('filter',regs={'EBX':m.P})
        self.assertEqual(m.number(m.S+0x44),0)

    def test_initializer_denies_cpu_and_direct_descriptor_aliases_before_animation(self):
        m=Machine(self.payload)
        # Native cleanup/store/dispatch execute; animation asset entry is a
        # sentinel RET fixture, avoiding any game resource or animation loop.
        m.uc.mem_write(m.read(0x50F4EC+16), b'\xc3')  # old-state exit notification
        for va in (0x2132A0,0x2DC7F0,0x2DCF70,0x290880,0x30D2A0,0x306DE0,0x2DBBC0):
            m.uc.mem_write(va,b'\xc3')
        for controller in (0,-1):
            for command,required in patch.MOVE_MASKS.items():
                for flags in (0,required):
                    m.player(controller=controller,command=command,abilities=flags)
                    descriptor=m.read(0xAD67F0+command*4)
                    m.run(0x1CD550,edx=descriptor)
                    self.assertEqual(m.read(m.S+4),descriptor if flags else 0x50F4EC)
                    if not flags:self.assertEqual(m.read(m.S),0)
                    self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP),m.STACK+4)
        m.player(controller=-1,command=0,abilities=patch.SPIN)
        m.run(0x1CD550,edx=0x5300F8)  # no exact state/steer match; shared family requires both bits
        self.assertEqual(m.read(m.S+4),0x50F4EC)

    def test_flags_registers_x87_depth_and_indirect_write_bounds(self):
        m=Machine(self.payload)
        m.player(command=0x23,abilities=0)
        m.uc.mem_write(0x1211E0,b'\xc3')
        regs={'EBX':m.P,'ESI':m.T,'EDI':0x33333333,'EBP':0x44444444}
        m.run('decode',regs=regs)
        for name,value in regs.items(): self.assertEqual(m.uc.reg_read(getattr(x86,'UC_X86_REG_'+name)),value)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EFLAGS)&0x8D5,0x202&0x8D5)
        for address,size in m.writes:
            self.assertTrue(m.P<=address<address+size<=m.P+0x10000 or 0x3100000<=address<address+size<=0x3110000)
        m.player(speed=127);m.seed_native_speed_cache()
        m.uc.mem_write(m.STOP+0x300,bytes.fromhex('d9e8'))  # keep a live lower x87 value
        m.uc.emu_start(m.STOP+0x300,m.STOP+0x302,count=1)
        m.run('speed',ecx=m.R,args=(0x184,))
        self.assertAlmostEqual(m.pop_float(),1.27,places=6)
        self.assertEqual(m.pop_float(),1)
        self.assertEqual((m.uc.reg_read(x86.UC_X86_REG_FPSW)>>11)&7,0)

    def test_speed_store_with_ramp_and_momentum_native_composition(self):
        from mod_editor.core import nfl2k5_accel_ramp as ramp, nfl2k5_momentum as momentum,nfl2k5_xbe_space as space
        base=space.apply(self.retail,patch.REQUESTS+momentum.REQUESTS,scaleout=True)[0]
        base=momentum.apply(patch.apply(base)[0])[0]
        for with_ramp in (False,True):
            payload=ramp.apply(base)[0] if with_ramp else base
            m=Machine(payload);m.player(speed=127);m.seed_native_speed_cache()
            m.f32(m.S+0x1B4,0)
            # Actual upstream call and six-byte store, including ramp when on.
            m.run(0x75CC5,ecx=m.R,stop=0x75CDB,regs={'EBX':m.P,'ESI':m.S,'EDI':0x184})
            first=m.number(m.S+0x1B4)
            self.assertGreater(first,0)
            self.assertLess(first,1.27) if with_ramp else self.assertAlmostEqual(first,1.27,places=6)
            self.assertEqual(patch.status(payload),'applied')
            self.assertEqual(momentum.status(payload),'applied')


if __name__=='__main__':unittest.main()
