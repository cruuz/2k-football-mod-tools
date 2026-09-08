"""Bounded native-instruction fixture; no disc, game loop, graphics or audio."""
from __future__ import annotations
import struct
import unicorn as uc
from unicorn import x86_const as x86
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core import nfl2k5_abilities_runtime as patch


class Machine:
    P, S, T, R = 0x3000000, 0x3001000, 0x3002000, 0x3003000
    TEAM, COND, BALL = 0x3004000, 0x3005000, 0x3006000
    STACK, STOP, SCRATCH = 0x3108000, 0x3200000, 0x3200800

    def __init__(self, payload):
        self.uc = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        self.image = XbeImage(payload)
        end = max(s.end for s in self.image.sections)
        self.uc.mem_map(0x10000, ((end+4095)&-4096)-0x10000)
        self.uc.mem_write(0x10000, payload[:self.image.headers_size])
        for section in self.image.sections:
            self.uc.mem_write(section.start,payload[section.raw:section.raw+section.raw_size])
        for start,size in ((self.P,0x10000),(0x3100000,0x10000),(self.STOP,0x1000)):
            self.uc.mem_map(start,size)
        self.labels = patch.code_for(patch.allocation(payload)['va'])[1]
        self.writes = []
        self.uc.hook_add(uc.UC_HOOK_MEM_WRITE, lambda u,a,address,size,value,data: self.writes.append((address,size)))
        # Only peripheral notifications and global-slider lookup are fixtures.
        # Both native attribute clamps, charge arithmetic/consumption and
        # initializer cleanup/store instructions remain actual retail bytes.
        for va in (0xA20F0,0xA2850,0x231EE0): self.uc.mem_write(va,b'\xc3')
        self.uc.mem_write(0x17B940,bytes.fromhex('d9eec20400'))  # neutral slider ret4
        self.uc.mem_write(0x17B8F0,bytes.fromhex('d9eec3'))
        self.uc.mem_write(0x13E2B0,b'\xd9\x05'+struct.pack('<I',self.SCRATCH)+b'\xc3')
        for section in self.image.sections:
            if not section.writable:
                start=(section.start+4095)&-4096; end=section.end&-4096
                if end>start: self.uc.mem_protect(start,end-start,uc.UC_PROT_READ|uc.UC_PROT_EXEC)
        self.player()
        self.u32(0xE602B8,14)
        self.u32(0xE5FC00,self.BALL)
        self.u32(self.BALL,self.P)
        self.u32(0xE576A0,0); self.u32(0xE576A4,8); self.u32(0xE576B4,7)
        self.f32(0xB71D0C,1/60)
        self.f32(self.SCRATCH,1)
        self.uc.reg_write(x86.UC_X86_REG_FPCW,0x37F)
        self.uc.reg_write(x86.UC_X86_REG_FPTAG,0xFFFF)

    def player(self, *, controller=0, context=10, abilities=0x1EE0, command=0, speed=127):
        self.u32(self.P+0x10,self.S); self.u32(self.P+0x0C,self.T)
        self.u32(self.P+0x3C,self.R); self.u32(self.P+0x1C,1)
        self.u32(self.R+0x30,self.TEAM); self.u32(self.TEAM+4,self.COND)
        self.f32(self.COND+4,1); self.u32(self.TEAM+0x20,0)
        self.uc.mem_write(self.R+0x34,bytes([1,0,speed]))
        self.uc.mem_write(self.R+0x52,struct.pack('<H',abilities))
        self.u32(self.S,command); self.u32(self.S+4,0x50F4EC)
        self.u32(self.S+0x28,1); self.u32(self.S+0x90,0xA5A50000)
        self.f32(self.S+0x44,0); self.f32(self.S+0x48,-1)
        self.f32(self.S+0x54,1); self.f32(self.S+0x1B8,.99)
        self.u32(self.T,controller); self.u32(self.T+0x1C,command)
        self.f32(self.T+0x10,.625); self.u32(self.T+0x14,0x3456)
        self.u32(self.T+0x18,0x20004)
        if 0<=controller<=3: self.u32(0xA9B960+controller*44,context)

    def u32(self,va,value): self.uc.mem_write(va,struct.pack('<I',value&0xFFFFFFFF))
    def f32(self,va,value): self.uc.mem_write(va,struct.pack('<f',value))
    def read(self,va): return struct.unpack('<I',self.uc.mem_read(va,4))[0]
    def number(self,va): return struct.unpack('<f',self.uc.mem_read(va,4))[0]
    def flags(self,value): self.uc.mem_write(self.R+0x52,struct.pack('<H',value))

    def run(self,entry,*,ecx=None,edx=0,args=(),stop=None,regs=None,count=5000,return_address=None):
        stop=self.STOP if stop is None else stop
        self.u32(self.STACK,self.STOP if return_address is None else return_address)
        for i,value in enumerate(args): self.u32(self.STACK+4+i*4,value)
        self.uc.reg_write(x86.UC_X86_REG_ESP,self.STACK)
        for name,value in dict(EBX=0x11111111,ESI=0x22222222,EDI=0x33333333,EBP=0x44444444,
                               ECX=self.P if ecx is None else ecx,EDX=edx,EFLAGS=0x202).items():
            self.uc.reg_write(getattr(x86,'UC_X86_REG_'+name),value)
        for name,value in (regs or {}).items(): self.uc.reg_write(getattr(x86,'UC_X86_REG_'+name),value)
        self.writes.clear()
        self.uc.emu_start(self.labels.get(entry,entry),stop,count=count)
        if self.uc.reg_read(x86.UC_X86_REG_EIP)!=stop:
            raise AssertionError(f'instruction budget {count} exhausted at {self.uc.reg_read(x86.UC_X86_REG_EIP):#x}')
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def pop_float(self):
        self.uc.mem_write(self.STOP+0x200,b'\xd9\x1d'+struct.pack('<I',self.SCRATCH+4))
        self.uc.emu_start(self.STOP+0x200,self.STOP+0x206,count=1)
        return self.number(self.SCRATCH+4)

    def seed_native_speed_cache(self,*,injury=1):
        self.f32(self.SCRATCH,injury)
        self.uc.mem_write(self.R+0x28,struct.pack('<H',0x20 if injury!=1 else 0))
        self.run(0x179840,ecx=self.R,edx=1)
        value=self.pop_float()
        self.f32(0xAA43B8,value); self.f32(0xAA43BC,0)
        return value
