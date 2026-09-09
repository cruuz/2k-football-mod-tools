"""Small synthetic Franchise and bounded x86 harness. No game boot or I/O."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct

from mod_editor.core import nfl2k5_my_career as career, nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None
TOKEN = "12345678-1234-5678-1234-567812345678"


def draft_save(position=0):
    """The synthetic Franchise at NFL Draft stage; its last player is an unassigned prospect."""
    payload = bytearray(synthetic_franchise())
    payload[fs.SEASON_BLOCK + fs.S_STAGE] = 5
    doc = rr.RosterDocument(payload, base=rr.find_block_base(payload))
    doc.players[-1].record.set("position", rr.position_code(position))
    doc.players[-1].record.set("player_type", 16)
    return doc.to_body()


def prepared(position=0, **options):
    code = rr.position_code(position)
    options.setdefault("template", 0 if career.templates_for(code) else None)
    return career.prepare(draft_save(code), first="My", last="Player", position=code, token=TOKEN, **options)


class Machine:
    SAVE, BODIES, STACK, STOP = 0x2000000, 0x2200000, 0x3008000, 0x3100000

    def __init__(self, payload, save=None, state=None):
        import unicorn as u
        from unicorn import x86_const as x
        self.u, self.x = u, x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        im = XbeImage(payload)
        self.uc.mem_map(0x10000, 0x1510000 - 0x10000)
        # The existing draft-AI owner stores immutable constants and its
        # free-agent routine in the owned header logo span. A section-only
        # mapping silently zeroed the constants and omitted that code.
        headers = struct.unpack_from('<I', payload, 0x108)[0]
        if not 0x178 <= headers <= 4096:
            raise ValueError('bounded XBE header geometry required')
        self.uc.mem_write(0x10000, payload[:headers])
        for section in im.sections:
            if section.raw_size:
                self.uc.mem_write(section.start, im.read(section.start, section.raw_size))
        self.uc.mem_protect(0x11000, 0x410000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        for region in career.space.layout(payload)["regions"]:
            s = im.section(region["va"])
            flags = u.UC_PROT_READ | (u.UC_PROT_WRITE if s.writable else 0) | (u.UC_PROT_EXEC if s.executable else 0)
            self.uc.mem_protect(region["va"], region["size"], flags)
        for va, size in ((self.SAVE, 0x100000), (self.BODIES, 0x20000), (self.STACK & ~65535, 65536), (self.STOP, 4096)):
            self.uc.mem_map(va, size)
        self.code, self.data = career.allocations(payload)
        self.state = self.data["va"]
        self.labels = career.code_for(self.code["va"], self.state)[1]
        self.stubs = []
        self.input_modes = []
        # Port/hardware mapping and animation reset are external services.
        # The native 0x1565F0 assignment helper itself is executed unchanged.
        self.stub(0x120880, lambda: (self.input_modes.append((self.reg("ECX"), self.reg("EDX"))), self.ret()))
        self.stub(0x7D550, lambda: self.ret())
        if save is not None:
            self.uc.mem_write(self.SAVE, save)
            self.root = self.SAVE + 0x320
            self.put(0xB72918, self.root)
            # Execute the retail relative-pointer fixup on the synthetic arena.
            self.call(0xC0500, ecx=self.root, budget=100000)
            self.team = self.get(self.root + 0x1C)
            self.player = self.get(self.root + 4) + 7 * 84
            for i in range(3):
                self.put(0xE5786C + 4 * i, self.team + 500 * i)
        if state is not None:
            self.uc.mem_write(self.state, state)
        self.put(0xE576A0, 2)
        self.put(0xE576A4, 5)
        self.put(0xE576B8, 7)
        self.put(0xE576B4, 0)
        self.put(0xE576BC, 0)

    def get(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def put(self, va, n):
        self.uc.mem_write(va, struct.pack("<I", n & 0xFFFFFFFF))

    def reg(self, name, value=None):
        r = getattr(self.x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(r)
        self.uc.reg_write(r, value & 0xFFFFFFFF)

    def ret(self, value=0, pop=0):
        sp = self.reg("ESP")
        self.reg("EAX", value)
        self.reg("EIP", self.get(sp))
        self.reg("ESP", sp + 4 + pop)

    def stub(self, va, action):
        va = self.labels.get(va, va)
        self.stubs.append(self.uc.hook_add(self.u.UC_HOOK_CODE, lambda *_: action(), begin=va, end=va))

    def call(self, entry, *, ecx=0, edx=0, eax=0, esi=0x22222222, ebx=0x11111111,
             args=(), budget=100000, stop=None, return_to=None):
        target = self.STOP if stop is None else stop
        self.put(self.STACK, self.STOP if return_to is None else return_to)
        for i, n in enumerate(args, 1):
            self.put(self.STACK + 4 * i, n)
        for name, value in (("ESP", self.STACK), ("EAX", eax), ("ECX", ecx), ("EDX", edx),
                            ("EBX", ebx), ("ESI", esi), ("EDI", 0x33333333), ("EBP", 0x44444444), ("EFLAGS", 0x202)):
            self.reg(name, value)
        self.uc.emu_start(self.labels.get(entry, entry), target, count=budget)
        if self.reg("EIP") != target:
            raise AssertionError(f"{entry}: budget exhausted at {self.reg('EIP'):#x}")
        if stop is None and self.reg("ESP") != self.STACK + 4 + 4 * len(args):
            raise AssertionError(f"{entry}: unbalanced stack {self.reg('ESP'):#x}")
        return self.reg("EAX")

    def activate(self):
        self.call("inject")
        self.uc.mem_write(self.player + 8, b"\x04")
        self.put(self.team + 3 * 4, self.player)
        self.uc.mem_write(self.team + 0x11C, b"\x04")
        self.call("resolve_team")
        self.put(0xE576A4, 8)
        self.uc.mem_write(0xE57C40, bytes([0, 0, 1, 9, 12, 4, 1, 0]))

    def bodies(self, count=22, career_slot=3):
        self.call(0xC3C60, ecx=self.team, edx=0xB30C4C)
        self.put(0xE60268, self.BODIES)
        for i in range(count):
            va = self.BODIES + 0x100 * i
            self.put(va + 0x30, va + 0x100 if i + 1 < count else 0)
            self.put(va + 0x3C, 0xB30C4C + 84 * (career_slot if i == 0 else 0))
        self.call(0x1561C0, args=(0,))
        return self.BODIES
