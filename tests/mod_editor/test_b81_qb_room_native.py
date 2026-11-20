"""The quarterback room page (beta 81 piece 3): module API, real linked page in Unicorn, retail call sites.

Every Unicorn case runs page_bytes() as the Studio would install it, entered through the installed 5-byte call at
its retail site, and compares with the same fixture entered through the retail call bytes (the old code).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest

from mod_editor.core import nfl2k5_qb_room_code as room
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

VA = 0x1529000
OPENING_SITE, ROOM_SITE = 0x247DCA, 0x24807A
OPENING_TARGET, ROOM_TARGET = 0x2BE020, 0x27EB80


class PageInterface(unittest.TestCase):
    def test_settings_record_layout_and_refusals(self):
        record = room.settings_record(room.STAGE_D1 | room.STAGE_D4, shadow=True, h0_ppm=12345, d2_scale_milli=900)
        self.assertEqual(record, struct.pack("<8sIIIIII", b"QBROOMv1", 1, 5, 1, 12345, 900, 0))
        self.assertEqual(room.settings_record(0), struct.pack("<8sIIIIII", b"QBROOMv1", 1, 0, 0, 15000, 1000, 0))
        self.assertEqual(room.parse_settings(record), {"mode": 1, "stages": 5, "shadow": True, "h0_ppm": 12345,
                                                       "d2_scale_milli": 900})
        for bad in ({"stages": 32}, {"stages": -1}, {"stages": True}, {"stages": 1, "shadow": 1},
                    {"stages": 1, "h0_ppm": 1_000_001}, {"stages": 1, "d2_scale_milli": -1},
                    {"stages": 1, "h0_ppm": 1.5}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                room.settings_record(**bad)
        for bad in (record[:31], b"QBROOMv2" + record[8:], record[:8] + b"\2" + record[9:],
                    record[:28] + b"\1\0\0\0"):
            with self.subTest(record=bad.hex()), self.assertRaises(ValueError):
                room.parse_settings(bad)

    def test_page_layout_relocation_and_sites(self):
        settings = room.settings_record(7)
        page = room.page_bytes(VA, settings, ir_store_va=0x14FD6D0)
        self.assertEqual(len(page), room.PAGE_SIZE)
        self.assertEqual(page[0x2000:0x2020], settings)
        self.assertEqual(page[0x2020:0x2040], struct.pack("<I", 0x14FD6D0) + bytes(28))
        self.assertEqual(page[0x2040:], bytes(0x1000 - 0x40))
        self.assertEqual(page[room.CODE_BYTES:0x2000], b"\xcc" * (0x2000 - room.CODE_BYTES))
        other = room.page_bytes(VA + 0x10000, settings, ir_store_va=0x14FD6D0)
        differ = {n for n in range(room.PAGE_SIZE) if page[n] != other[n]}
        fields = set()
        for offset, relative, family, _ in room._RELOCATIONS:
            if family == "page" and not relative or family == "stock" and relative:
                fields.update(range(offset, offset + 4))
        self.assertTrue(differ <= fields)
        self.assertEqual(room.COUNTERS["opening_passes"], 0x2040)
        self.assertTrue(all(0x2040 <= at < 0x2400 and at % 4 == 0 for at in room.COUNTERS.values()))
        self.assertEqual(room.RING_EVENT.size, 20)
        self.assertEqual(room.RING_OFFSET + room.RING_COUNT * room.RING_EVENT.size, 0x2E00)
        for bad in ((VA + 4, settings), (VA, settings[:31]), (0, settings), (VA, b"\0" * 32)):
            with self.subTest(args=bad), self.assertRaises(ValueError):
                room.page_bytes(*bad)
        listed = list(room.sites(VA, 7))
        self.assertEqual([(name, at, old) for name, at, old, _ in listed],
                         [("opening_entry", OPENING_SITE, bytes.fromhex("e851620700")),
                          ("room_entry", ROOM_SITE, bytes.fromhex("e8016b0300"))])
        for name, at, old, new in listed:
            self.assertEqual(new[0], 0xE8)
            self.assertEqual(at + 5 + struct.unpack("<i", new[1:])[0], VA + room.LABELS[name])
        self.assertEqual(list(room.sites(VA, 0)), listed)
        with self.assertRaises(ValueError):
            list(room.sites(VA, room.STAGE_SIGN))

    def test_authored_template_rebuilds_with_its_development_toolchain(self):
        if not all(shutil.which(tool) for tool in ("gcc", "as", "ld")) or not importlib.util.find_spec("elftools"):
            self.skipTest("development build needs GNU i386 gcc/binutils and pyelftools")
        version = subprocess.run(["gcc", "-dumpfullversion"], capture_output=True, text=True)
        assembler = subprocess.run(["as", "--version"], capture_output=True, text=True)
        if version.stdout.strip() != "13.3.0" or "2.42" not in assembler.stdout.partition("\n")[0]:
            self.skipTest("the checked-in i386 template was generated with GCC 13.3 and GNU binutils 2.42")
        tool = Path(__file__).resolve().parents[2] / "tools/qb_room/build.py"
        subprocess.run([sys.executable, str(tool), "--check"], check=True)


@unittest.skipUnless(HAVE_UC, "Unicorn is required for the native quarterback room cases")
class EntryStubs(unittest.TestCase):
    STACK = 0x3001000

    def setUp(self):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, x86_const

        self.x = x86_const
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        for start, size in ((VA, room.PAGE_SIZE), (0x247000, 0x2000), (self.STACK - 0x1000, 0x2000),
                            (0xE57000, 0x1000)):
            self.uc.mem_map(start, size)
        self.uc.mem_write(VA, room.page_bytes(VA, room.settings_record(0)))
        self.registers = tuple(getattr(self.x, "UC_X86_REG_" + r)
                               for r in ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP", "ESP", "EFLAGS"))

    def enter(self, site, target, installed):
        call = dict((at, new) for _, at, _, new in room.sites(VA, 0))[site] if installed else \
            dict((at, old) for at, old, _, _ in room.HOOKS)[site]
        self.uc.mem_write(site, call)
        self.uc.ctl_flush_tb()                      # the site's old translation must not be reused
        incoming = (0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, self.STACK, 0x8D7)
        for register, value in zip(self.registers, incoming, strict=True):
            self.uc.reg_write(register, value)
        self.uc.emu_start(site, target, count=10_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), target)
        state = tuple(self.uc.reg_read(r) for r in self.registers)
        expected = list(incoming)
        expected[7] -= 4
        self.assertEqual(state, tuple(expected))
        self.assertEqual(struct.unpack("<I", self.uc.mem_read(self.STACK - 4, 4))[0], site + 5)

    def counters(self):
        return room.counters(bytes(self.uc.mem_read(VA, room.PAGE_SIZE)))

    def test_both_entries_keep_every_register_and_reach_their_original_targets(self):
        for site, target, name in ((OPENING_SITE, OPENING_TARGET, "opening_passes"),
                                   (ROOM_SITE, ROOM_TARGET, "room_passes")):
            with self.subTest(site=hex(site)):
                before = self.counters()[name]
                self.enter(site, target, installed=False)          # retail call: the page never runs
                self.assertEqual(self.counters()[name], before)
                self.enter(site, target, installed=True)
                self.assertEqual(self.counters()[name], before + 1)


if __name__ == "__main__":
    unittest.main()
