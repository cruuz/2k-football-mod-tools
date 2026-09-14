"""Bounded native weather fixture. No emulator, rendering, saves or controller UI.

The retail RNG, climate generator, time selector, predicates and fog reader run
unmodified. Only the terminal GPU refresh is stopped before device submission.
"""
from __future__ import annotations

import random
import struct

from mod_editor.core.nfl2k5_cave_oracle import XbeImage

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:
    uc = x86 = None


class Machine:
    STADIUM, OUTPUT, CAMERA = 0x2000000, 0x2001000, 0x2002000
    STACK, STOP = 0x300F000, 0x3010000

    def __init__(self, payload, row):
        self.uc = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1800000-0x10000)
        self.uc.mem_map(0x2000000, 0x10000)
        self.uc.mem_map(0x3000000, 0x20000)
        self.image = XbeImage(payload)
        for section in self.image.sections:
            self.uc.mem_write(section.start, payload[section.raw:section.raw+section.raw_size])
            start, end = (section.start+4095) & -4096, section.end & -4096
            if end > start:
                self.uc.mem_protect(start, end-start, uc.UC_PROT_READ |
                                    (uc.UC_PROT_WRITE if section.writable else 0) |
                                    (uc.UC_PROT_EXEC if section.executable else 0))
        self.uc.mem_write(self.STADIUM, row)
        self.put(0xE5FE64, self.STADIUM)
        self.seed(7)

    def seed(self, seed):
        rng = random.Random(seed)
        self.put(0xE5FCA0, 54)
        self.put(0xE5FCA4, 31)
        for i in range(110):
            self.put(0xE5FCA8+4*i, rng.getrandbits(32))

    def put(self, at, value):
        self.uc.mem_write(at, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, at):
        return struct.unpack("<I", self.uc.mem_read(at, 4))[0]

    def f32(self, at, value):
        self.uc.mem_write(at, struct.pack("<f", value))

    def readf(self, at):
        return struct.unpack("<f", self.uc.mem_read(at, 4))[0]

    def run(self, address, *, args=(), stop=None, count=20000, **registers):
        self.put(self.STACK, self.STOP)
        for index, value in enumerate(args):
            self.put(self.STACK+4+4*index, value)
        self.uc.reg_write(x86.UC_X86_REG_ESP, self.STACK)
        for name in ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP"):
            self.uc.reg_write(getattr(x86, "UC_X86_REG_"+name), registers.get(name.lower(), 0))
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.uc.reg_write(x86.UC_X86_REG_FPTAG, 0xFFFF)
        destination = self.STOP if stop is None else stop
        self.uc.emu_start(address, destination, count=count)
        actual = self.uc.reg_read(x86.UC_X86_REG_EIP)
        if actual != destination:
            raise AssertionError(f"Native budget exhausted at {actual:#x}, expected {destination:#x}")
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def climate(self, month, tod):
        self.run(0xEC870, ecx=self.STADIUM, edx=month, args=(tod, self.OUTPUT))
        return tuple(self.readf(self.OUTPUT+4*i) for i in range(4))

    def schedule(self, month, hour, minute=0, week=0, game=0):
        at = 0xE57C40+8*(17*week+game)
        self.uc.mem_write(at, bytes((0, 0, 1, month, 1, 26, hour, minute)))
        self.run(0x133FC0, ecx=week, edx=game)
        return (self.get(0xE60184), *(self.readf(a) for a in (0xE5FFA4, 0xE5FFAC, 0xE600C0, 0xE600C4)))

    def conditions(self, *, temperature=70, precipitation=0, haze=0, indoor=False, tod=0):
        self.f32(0xE5FFA4, temperature)
        self.f32(0xE5FFAC, precipitation)
        self.f32(0xE600C4, haze)
        self.put(0xE60184, tod)
        self.put(self.STADIUM+0x18, int(indoor))

    def haze(self):
        self.run(0x85EF0)
        return tuple(self.readf(a) for a in (0xA86734, 0xA86738, 0xA8673C))

    def camera_haze(self):
        # 2B9E0 really copies the reader's values to the camera. Stop before the
        # device-state refresh at 2BA04, which is outside this fixture's scope.
        self.run(0x86190, ecx=self.CAMERA, stop=0x2BA04)
        return tuple(self.readf(self.CAMERA+a) for a in (0x2A0, 0x298, 0x29C))

    def suffixes(self):
        # Stop at the formatter boundary; names/CRC inventory are checked separately.
        self.run(0x62BE0, stop=0x62C71)
        return tuple(chr(self.uc.reg_read(reg)) for reg in (x86.UC_X86_REG_EDI, x86.UC_X86_REG_ESI))
