"""Bounded fixtures for dormant components, not a game/emulator witness."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import nfl2k5_senior_bowl as bowl
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
SAVE_ROOT = Path(os.environ.get("NFL2K5_SAVE_FIXTURES", str(Path.home() / "Desktop/2K5-8 Editors/save_fixtures")))
SAVE_PATHS = (
    SAVE_ROOT / "f0/UDATA/53450030/0B8506889D40/SAVEGAME.DAT",
    SAVE_ROOT / "f1/UDATA/53450030/0B8506889D40/SAVEGAME.DAT",
    SAVE_ROOT / "256B40374FD6-Franchise1/UDATA/53450030/256B40374FD6/SAVEGAME.DAT",
)


def prospects(scheme="retail", extras=2):
    # Scattered indices intentionally differ from the first-year class window.
    return tuple(bowl.Prospect(80*p+i+1, p, 0x14, False, f"Rookie {p:02}-{i:02}", b"identity")
                 for p, n in enumerate(bowl.quotas(scheme)) if n for i in range(2*n+extras))


def event(**options):
    settings = options.pop("settings", bowl.Settings())
    return bowl.prepare_event(prospects(settings.scheme), year=options.pop("year", 7),
                              franchise_id=options.pop("franchise_id", b"franchise-test-1"),
                              settings=settings, **options)


class Machine(unittest.TestCase):
    INPUT = 0x2000000
    OUTPUT = 0x2010000
    IDENTITY = 0x2020000
    STACK_BASE, STACK, STOP = 0x3000000, 0x3008000, 0x3010000

    @classmethod
    def setUpClass(cls):
        if not XBE.is_file():
            raise unittest.SkipTest("private pinned USA default.xbe extraction is absent")
        if importlib.util.find_spec("unicorn") is None:
            raise unittest.SkipTest("bounded i386 component proofs require Unicorn")
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != bowl.RETAIL_SHA256:
            raise unittest.SkipTest("extraction is not the pinned USA retail XBE")
        cls.patched = bowl.apply(cls.retail)[0]
        cls.allocations = bowl.allocations(cls.patched)
        cls.code_va, cls.state_va = (cls.allocations[k]["va"] for k in ("code", "data"))
        cls.code, cls.labels = bowl.code_for(cls.code_va, cls.state_va)

    def setUp(self):
        import unicorn as u
        from unicorn import x86_const as r
        self.u, self.r = u, r
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        # Only declared feature memory plus bounded input/output/stack buffers.
        self.uc.mem_map(self.code_va & ~4095, 8192, u.UC_PROT_ALL)
        self.uc.mem_write(self.code_va, self.code)
        self.uc.mem_protect(self.code_va & ~4095, 8192, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_map(self.state_va, bowl.DATA_SIZE, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(self.INPUT, 0x30000, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(self.STACK_BASE, 0x10000, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.uc.mem_map(self.STOP, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.writes = []
        self.uc.hook_add(u.UC_HOOK_MEM_WRITE, lambda uc, access, addr, size, val, _: self.writes.append((addr, size)))

    def call(self, name, *args, df=False, limit=2500000):
        r = self.r
        regs = {r.UC_X86_REG_EBX: 0xB0B0B0B0, r.UC_X86_REG_ESI: 0x51515151,
                r.UC_X86_REG_EDI: 0xD1D1D1D1, r.UC_X86_REG_EBP: 0xBEBEBEBE}
        for reg, val in regs.items():
            self.uc.reg_write(reg, val)
        self.uc.reg_write(r.UC_X86_REG_ESP, self.STACK)
        self.uc.reg_write(r.UC_X86_REG_EFLAGS, 0x602 if df else 0x202)
        self.uc.mem_write(self.STACK, struct.pack("<" + "I"*(len(args)+1), self.STOP, *args))
        self.writes.clear()
        self.uc.emu_start(self.labels[name], self.STOP, count=limit)
        self.assertEqual(self.uc.reg_read(r.UC_X86_REG_EIP), self.STOP, "bounded instruction budget exhausted")
        self.assertEqual(self.uc.reg_read(r.UC_X86_REG_ESP), self.STACK+4)
        for reg, val in regs.items():
            self.assertEqual(self.uc.reg_read(reg), val)
        self.assertEqual(bool(self.uc.reg_read(r.UC_X86_REG_EFLAGS) & 0x400), df)
        for addr, size in self.writes:
            self.assertTrue(self.state_va <= addr and addr+size <= self.state_va+bowl.DATA_SIZE
                            or self.INPUT <= addr and addr+size <= self.INPUT+0x30000
                            or self.STACK_BASE <= addr and addr+size <= self.STACK_BASE+0x10000,
                            f"write outside bounded owned/caller memory at {addr:#x}")
        return self.uc.reg_read(r.UC_X86_REG_EAX)

    def put_event(self, record):
        self.uc.mem_write(self.state_va, record.to_bytes())
        self.uc.mem_write(self.IDENTITY, record.franchise_id+record.class_hash)

    def state(self):
        return bytes(self.uc.mem_read(self.state_va, bowl.EVENT_SIZE))

    def select(self, players, *, seed=1, scheme="retail", df=False):
        source = b"".join(struct.pack("<IBBBB", p.index, p.position, p.flags, int(p.owned), 0) for p in players)
        self.uc.mem_write(self.INPUT, source)
        self.uc.mem_protect(self.INPUT, 0x10000, self.u.UC_PROT_READ)
        scratch = self.state_va+bowl.STAGING_OFFSET
        result = self.call("sb_select", self.INPUT, len(players), seed, bowl.SCHEMES.index(scheme), scratch, df=df)
        self.assertEqual(bytes(self.uc.mem_read(self.INPUT, len(source))), source)
        return result, bytes(self.uc.mem_read(scratch, bowl.EVENT_SIZE))
