"""Bounded USA native clock/play-call fixture. No game boot or rendered witness.

Timers, completion, ready predicates, and no-huddle dispatch execute native
instructions. Scene/audio/player installation leaves are explicit stubs. Human
input is supplied at its accepted-selection continuation; CPU selection starts
with an already selected play, then runs its native completion dispatcher.
"""
from __future__ import annotations

import struct

from mod_editor.core.nfl2k5_cave_oracle import XbeImage

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:
    uc = x86 = None


class Machine:
    GAME, PLAY, AUX, STATE_CLOCK = 0x2000000, 0x2000100, 0x2000200, 0x2000300
    OFF, DEF, CTX, BALL, POSE = 0x2001000, 0x2002000, 0x2003000, 0x2004000, 0x2004100
    DESC, PREV, OLDER, SELECT, DSELECT, RECORD = 0x2005000, 0x2005200, 0x2005400, 0x2006000, 0x2006200, 0x2006400
    STACK, STOP = 0x300F000, 0x3010000

    def __init__(self, payload):
        self.uc = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1800000 - 0x10000)
        self.uc.mem_map(0x2000000, 0x10000)
        self.uc.mem_map(0x3000000, 0x20000)
        image = XbeImage(payload)
        for section in image.sections:
            self.uc.mem_write(section.start, payload[section.raw:section.raw + section.raw_size])
        # Protect every wholly owned page according to loader permissions.
        for section in image.sections:
            start, end = (section.start + 4095) & -4096, section.end & -4096
            if end > start:
                perms = uc.UC_PROT_READ | (uc.UC_PROT_WRITE if section.writable else 0) | (uc.UC_PROT_EXEC if section.executable else 0)
                self.uc.mem_protect(start, end-start, perms)
        self.stubs = {va: (0, 0) for va in (
            0x11E920, 0xAF260, 0xDDCA0, 0x13A730, 0x206570, 0x1CF2F0,
            0x94A00, 0x1D1A90, 0x89590, 0x7D7A0, 0x1B2E40, 0x875E0,
            0x119470, 0x59370, 0x18EC30, 0xFC340,
            # No-huddle scene/player installation, not clock logic.
            0x188A60, 0x189F00, 0xB1740, 0x17AF00, 0x13A0B0, 0x156640,
            0x1B67C0, 0x1D57A0, 0x1B9E70, 0x1D0430, 0x7B9E0,
            0x2077C0, 0x11E7E0, 0x72160, 0x1B2560,
            # Incompletion presentation; the stop request and timer run natively.
            0xA0FF0, 0x874E0, 0xFEF50, 0x9FC30,
            # Snap presentation manager; descriptor copies and clock stop run.
            0x1B1300,
        )}
        self.stubs.update({0x190730: (0, 4), 0x1CEAC0: (0, 4),
                           0xB5750: (0, 8)})
        # Formation-derived alignment scalar; balanced x87 leaf substitute.
        self.uc.mem_write(0x200F000, bytes.fromhex('d9eec20800'))
        self.hits, self.writes = [], []
        self.stop_at = self.STOP
        self.uc.hook_add(uc.UC_HOOK_CODE, self._code)
        self.uc.hook_add(uc.UC_HOOK_MEM_WRITE, self._write)
        for va, value in ((0xE6028C, self.GAME), (0xE60294, self.PLAY),
                          (0xE602A0, self.AUX), (0xE60290, self.STATE_CLOCK),
                          (0xE6029C, self.AUX+0x40), (0xE60298, self.AUX+0x80),
                          (0xE60280, self.OFF), (0xE60284, self.DEF),
                          (0xE60288, self.OFF), (0xE602EC, self.CTX),
                          (0xE5FC00, self.BALL), (self.BALL+0x14, self.POSE),
                          (0xE602D4, self.DESC), (0xE602D8, self.PREV),
                          (0xE602DC, self.OLDER), (self.OFF, self.DEF),
                          (self.DEF, self.OFF), (self.OFF+0xC, self.SELECT),
                          (self.DEF+0xC, self.DSELECT),
                          (self.SELECT+8, self.RECORD), (self.SELECT+0xC, self.RECORD),
                          (self.DSELECT+8, self.RECORD), (self.DSELECT+0xC, self.RECORD),
                          (self.SELECT+0x24, 8), (self.DSELECT+0x24, 8),
                          (self.OFF+8, self.OFF+0x100), (self.DEF+8, self.DEF+0x100),
                          (self.OFF+0x10C, self.OFF+0x200),
                          (0xE5FC28, self.OFF+0x100), (0xE5FC68, self.DEF+0x100),
                          (0xB71D10, 1), (0xA89B60, 1), (0xE6000C, 15)):
            self.put(va, value)
        self.f32(self.OFF+0x204, 1)
        for timer in (self.GAME, self.PLAY, self.AUX, self.STATE_CLOCK, self.AUX+0x40, self.AUX+0x80):
            self.put(timer+0x18, 3)
            self.f32(timer+0x14, 1)
        self.configure()

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack('<I', value & 0xFFFFFFFF))

    def get(self, va):
        return struct.unpack('<I', self.uc.mem_read(va, 4))[0]

    def f32(self, va, value):
        self.uc.mem_write(va, struct.pack('<f', value))

    def readf(self, va):
        return struct.unpack('<f', self.uc.mem_read(va, 4))[0]

    def configure(self, *, seconds=600, play=40, running=True, period=2, phase=4, cpu=False, play_flags=0x8000):
        self.f32(self.GAME+0x10, seconds)
        self.f32(self.PLAY+0x10, play)
        self.f32(0xE602B0, 900)
        self.f32(0xE602AC, 40)
        self.put(self.GAME+0x18, 1 if running else 3)
        self.put(self.PLAY+0x18, 1)
        self.put(0xE602FC, 0)
        self.put(0xE602B8, 11)
        self.put(0xE602C0, 2)
        self.put(0xE602C4, period)
        self.put(0xE602B4, phase)
        self.put(0xE5FF80, 4)
        self.put(self.OFF+0x30, 0 if cpu else self.OFF+0x300)
        self.put(self.RECORD+4, play_flags)

    def _code(self, _u, va, _size, _data):
        self.hits.append(va)
        if va == self.stop_at:
            self.uc.emu_stop()
        elif va == 0x204F10:
            self.uc.reg_write(x86.UC_X86_REG_EIP, 0x200F000)
        elif va in self.stubs:
            value, pop = self.stubs[va]
            esp = self.uc.reg_read(x86.UC_X86_REG_ESP)
            self.uc.reg_write(x86.UC_X86_REG_EAX, value)
            self.uc.reg_write(x86.UC_X86_REG_EIP, self.get(esp))
            self.uc.reg_write(x86.UC_X86_REG_ESP, esp+4+pop)

    def _write(self, _u, _kind, va, size, value, _data):
        self.writes.append((va, size, value))

    def run(self, va, *, ecx=0, edx=0, ebx=0, eax=0, args=(), stop=None, count=20000):
        self.hits, self.writes = [], []
        self.stop_at = self.STOP if stop is None else stop
        self.put(self.STACK, self.STOP)
        for i, arg in enumerate(args):
            self.put(self.STACK+4+i*4, arg)
        for reg, value in ((x86.UC_X86_REG_ESP, self.STACK), (x86.UC_X86_REG_ECX, ecx),
                           (x86.UC_X86_REG_EDX, edx), (x86.UC_X86_REG_EBX, ebx),
                           (x86.UC_X86_REG_EAX, eax)):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.uc.reg_write(x86.UC_X86_REG_FPTAG, 0xFFFF)
        self.uc.emu_start(va, self.STOP, count=count)
        actual = self.uc.reg_read(x86.UC_X86_REG_EIP)
        if actual != self.stop_at:
            raise AssertionError(f'native instruction budget exhausted at {actual:#x}, wanted {self.stop_at:#x}')
        return self.readf(self.GAME+0x10), self.readf(self.PLAY+0x10)

    def complete(self):
        return self.run(0xB8650, ecx=self.OFF)

    def cpu_complete(self):
        return self.run(0x153170, ecx=self.OFF, stop=0xA2B70)

    def human_complete(self):
        return self.run(0x153B62, ebx=self.OFF, stop=0xA2B70)

    def no_huddle(self):
        return self.run(0xA24B0, edx=1)

    def timer_tick(self, timer, seconds):
        return self.run(0xAF490, ecx=timer, args=(struct.unpack('<I', struct.pack('<f', seconds))[0],))

    def snap(self):
        return self.run(0xB6F30, stop=0xB7015)
