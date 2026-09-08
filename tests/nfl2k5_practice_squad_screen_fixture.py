"""Bounded native screen harness; no console, graphics, audio or disc-sized reads."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import nfl2k5_practice_squad_screen as screen
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_franchise_practice as fp
from mod_editor.core import nfl2k5_practice_reserves as pr
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None


def composed(retail):
    return pr.apply(fp.apply(ps.apply(retail)[0])[0])[0]


class ScreenMachine(unittest.TestCase):
    ROOT_BASE = 0x2000000
    UI = 0x2400000
    MANAGER = UI + 0x2000
    ROWS = UI + 0x1000
    STACK = 0x3008000
    STOP = 0x3100000
    HEAP = 0x2500000

    @classmethod
    def setUpClass(cls):
        if not XBE.is_file():
            raise unittest.SkipTest("pinned USA retail default.xbe extraction is absent")
        if not HAVE_UNICORN:
            raise unittest.SkipTest("bounded native screen proofs require Unicorn")
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != ps.RETAIL_SHA256:
            raise unittest.SkipTest("extracted XBE is not the pinned USA retail image")
        cls.patched = screen.apply(composed(cls.retail))[0]
        cls.code, cls.data = screen.allocations(cls.patched)
        _, cls.labels = screen.code_for(cls.patched, cls.code["va"], cls.data["va"])
        from mod_editor.core import nfl2k5_team_history as th
        if not (XBE.parent / "vc_53450030" / "0").is_file():
            raise unittest.SkipTest("private extracted ROST archive is absent")
        with th._outer_image()(XBE.parent) as archive:
            entry = th._entry(archive)
            cls.body = archive.read(entry.virtual_offset, entry.size)[th.RESOURCE_HEADER_SIZE:]

    def setUp(self):
        import unicorn as u
        from unicorn import x86_const as r
        self.u, self.r = u, r
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1510000 - 0x10000)
        im = XbeImage(self.patched)
        for section in im.sections:
            if section.raw_size:
                self.uc.mem_write(section.start, im.read(section.start, section.raw_size))
        # Read/execute retail .text and exact permissions for every allocated page.
        self.uc.mem_protect(0x11000, 0x410000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        for page in screen.space.layout(self.patched)["regions"]:
            flags = im.section(page["va"]).flags
            perms = u.UC_PROT_READ | (u.UC_PROT_WRITE if flags & 1 else 0) | (u.UC_PROT_EXEC if flags & 4 else 0)
            self.uc.mem_protect(page["va"], page["size"], perms)
        for address, size in ((self.ROOT_BASE, 0x200000), (self.UI, 0x10000),
                              (self.HEAP, 0x200000), (0x3000000, 0x10000), (self.STOP, 0x1000)):
            self.uc.mem_map(address, size)
        self.uc.mem_write(self.ROOT_BASE, self.body)
        self.root = self.ROOT_BASE + 0x40
        self.put(0xB72918, self.root)
        self.call(0xC0500, ecx=self.root)
        self.team = self.word(self.root + 0x1C)
        self.other = self.team + 500
        self.put(0xE576A0, 1)
        self.put(0xE576A4, 7)
        self.uc.mem_write(0xE421E0, bytes(160 * 4))
        self.uc.mem_write(0xE5775C, bytes(34 * 4))
        for i in range(32):
            self.put(0xE5786C + 4 * i, self.team + 500 * i)
        self.put(0xE5775C, 1)
        self.put(0xE3C0A0, self.team)
        self.put(self.MANAGER, self.labels["descriptor"])
        self.put(self.MANAGER + 0x10C, self.UI + 0x4000)
        self.call(self.labels["enter"], ecx=self.MANAGER)
        self.put(self.UI + 4, self.MANAGER)
        self.put(self.UI + 0x58, self.labels["sheet"])
        self.put(self.UI + 0x5C, self.labels["active_binding"])
        self.put(self.UI + 0x64, 17)
        self.put(self.UI + 0x68, 0)
        self.put(self.UI + 0x40, self.ROWS)
        self.heap_next = self.HEAP
        self.heap_live = set()
        self.dialogs = []
        self.dialog_result = 1
        self.dialog_effect = None
        self.rebuilds = 0
        self.menu_art_stubs = set()
        self.uc.hook_add(u.UC_HOOK_CODE, self._services, begin=0x10000, end=0x420000)

    def word(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def byte(self, va):
        return self.uc.mem_read(va, 1)[0]

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def call(self, address, *, ecx=0, edx=0, eax=0, args=(), extra=(), budget=3000000):
        r = self.r
        saved = {r.UC_X86_REG_EBX: 0x11111111, r.UC_X86_REG_ESI: 0x22222222,
                 r.UC_X86_REG_EDI: 0x33333333, r.UC_X86_REG_EBP: 0x44444444}
        saved.update(extra)
        self.put(self.STACK, self.STOP)
        for i, value in enumerate(args, 1):
            self.put(self.STACK + 4 * i, value)
        for reg, value in {**saved, r.UC_X86_REG_ESP: self.STACK, r.UC_X86_REG_EAX: eax,
                           r.UC_X86_REG_ECX: ecx, r.UC_X86_REG_EDX: edx}.items():
            self.uc.reg_write(reg, value)
        self.uc.emu_start(address, self.STOP, count=budget)
        self.assertEqual(self.uc.reg_read(r.UC_X86_REG_EIP), self.STOP, "instruction budget exhausted")
        self.assertEqual(self.uc.reg_read(r.UC_X86_REG_ESP), self.STACK + 4 + 4 * len(args))
        for reg, value in saved.items():
            self.assertEqual(self.uc.reg_read(reg), value, f"callee-saved register {reg}")
        return self.uc.reg_read(r.UC_X86_REG_EAX)

    def _return(self, value=0, pop=0):
        r = self.r
        sp = self.uc.reg_read(r.UC_X86_REG_ESP)
        self.uc.reg_write(r.UC_X86_REG_EAX, value)
        self.uc.reg_write(r.UC_X86_REG_EIP, self.word(sp))
        self.uc.reg_write(r.UC_X86_REG_ESP, sp + 4 + pop)

    def _services(self, uc, address, _size, _data):
        r = self.r
        if address in self.menu_art_stubs:
            self._return()
        elif address == 0x14E440:
            sp = uc.reg_read(r.UC_X86_REG_ESP)
            table = self.word(sp + 4)
            self.dialogs.append((table, uc.reg_read(r.UC_X86_REG_EDX)))
            if table in (self.labels["promote_menu"], self.labels["demote_menu"]) and self.dialog_effect:
                self.dialog_effect()
            self._return(self.dialog_result if table != 0x5042FC else 0, pop=24)
        elif address == 0x1427A0:
            self._return(pop=8)
        elif address == 0x48700:
            size = uc.reg_read(r.UC_X86_REG_EDX)
            self.assertLess(size, 0x100000)
            at = self.heap_next
            self.heap_next += (max(size, 4) + 15) & -16
            self.assertLess(self.heap_next, self.HEAP + 0x200000)
            self.heap_live.add(at)
            self._return(at)
        elif address == 0x48870:
            self.heap_live.discard(uc.reg_read(r.UC_X86_REG_ECX))
            self._return()
        elif address in (0x172660, 0x1739F0, 0x1701A0):
            # Cell formatting, rendered cell styles and geometry. Row allocation,
            # count/getter dispatch, tab switching, freeing and clamp run native.
            self._return(pop=8 if address == 0x1739F0 else 0)
        elif address == 0x174C70:
            self.rebuilds += 1

    def snapshot(self):
        return bytes(self.uc.mem_read(self.ROOT_BASE, len(self.body)))

    def page(self, reserve=False, row=0):
        self.put(self.UI + 0x5C, self.labels["reserve_binding" if reserve else "active_binding"])
        self.call(0x174C70, ecx=self.UI)
        self.put(self.UI + 0xBC, row)

    def move(self, row=0):
        return self.call(self.labels["activate"], ecx=self.MANAGER, edx=self.UI, args=(row,))

    def demote(self, n=1, fill=False):
        if fill:
            count, table = self.word(self.root + 0x38), self.word(self.root + 0x3C)
            for i in range(12):
                self.assertEqual(self.call(ps.SYMBOLS["ps_append"], ecx=self.team,
                                           edx=self.word(table + 4 * i)), 1)
            self.uc.mem_write(table, bytes(self.uc.mem_read(table + 48, (count - 12) * 4)) + bytes(48))
            self.put(self.root + 0x38, count - 12)
        for _ in range(n):
            player = self.word(self.team + 4 * (self.byte(self.team + ps.ACTIVE_COUNT) - 1))
            self.assertEqual(self.call(ps.SYMBOLS["ps_demote"], ecx=self.team, edx=player), 1)
