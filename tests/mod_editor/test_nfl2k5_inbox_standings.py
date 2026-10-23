"""Guarded pointer repair, build wiring, and optional real retail execution."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import nfl2k5_inbox_standings as inbox
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_cave_oracle import synthetic, put

XBE = Path(os.environ.get("NFL2K5_INBOX_XBE", str(Path(os.environ.get(
    "NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) /
    "ESPN NFL 2K5 (USA)/default.xbe")))


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.data = synthetic(sections=[(".data", inbox.DESCRIPTOR, 0x200, 0x600, 0x200, 3)])
        data = bytearray(self.data)
        struct.pack_into("<I", data, 0x10C, 0x2000000)
        self.data = bytes(data)
        digest = hashlib.sha256(XbeImage(self.data).read(inbox.DESCRIPTOR, 0x34)).hexdigest()
        self.pins = patch.object(inbox, "PINS", ((inbox.DESCRIPTOR, 0x34, digest),))
        self.callbacks = patch.object(inbox, "CALLBACK_PINS", ())
        self.pins.start()
        self.callbacks.start()
        self.addCleanup(self.pins.stop)
        self.addCleanup(self.callbacks.stop)

    def test_only_pointer_and_section_digest_change_and_second_apply_is_identical(self):
        after, receipt = inbox.apply(self.data)
        image = XbeImage(self.data)
        at = image.offset(inbox.SETUP_SITE, 4)
        allowed = set(range(at, at + 4)) | set(range(0x180 + 36, 0x180 + 56))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(self.data, after))))
        self.assertEqual(len(after), len(self.data))
        self.assertEqual(inbox.status(after), "applied")
        self.assertEqual(inbox.apply(after)[0], after)
        self.assertEqual(receipt["code_bytes"], 0)
        self.assertEqual(inbox.REQUESTS, ())

    def test_foreign_pointer_descriptor_and_callback_refuse(self):
        for address in (inbox.SETUP_SITE, inbox.DESCRIPTOR + 4):
            data = put(self.data, address, b"\x99" * 4)
            with self.subTest(address=address), self.assertRaises(inbox.InboxStandingsError):
                inbox.apply(data)
        with patch.object(inbox, "CALLBACK_PINS", ((inbox.DESCRIPTOR, 4, "a" * 64),)):
            with self.assertRaises(inbox.InboxStandingsError):
                inbox.apply(self.data)
        self.assertEqual(inbox.status(b"invalid"), "foreign")

    def test_reservation_recorder_owns_the_entire_existing_pointer(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        after, receipt = inbox.apply(self.data)
        recorder = Recorder(self.data)
        recorder.observe(inbox, "apply", self.data, after, receipt)
        self.assertTrue(any(int(row["start"], 16) == inbox.SETUP_SITE
                            and row["size"] == 4 and row["owner"] == inbox.OWNER
                            for row in recorder.spans))

    def test_build_presets_and_real_build_helper(self):
        from mod_editor.core import mod_build as build
        self.assertFalse(build.BuildPlan(source="source", target="copy").inbox_standings)
        for name, preset in build.PRESETS.items():
            self.assertEqual(preset["inbox_standings"], name.startswith("softdrink_"))
        receipt = {"steps": [], "result": {}}
        with patch.object(build, "_core_module", return_value=inbox), \
                patch.object(build, "_xbe_bytes", side_effect=[self.data, inbox.apply(self.data)[0]]), \
                patch.object(build, "_write_xbe_bytes") as write:
            build._apply_inbox_standings(build.BuildPlan(source="source", target="copy", inbox_standings=True), Path("copy"), receipt,
                                        lambda *_: None)
        write.assert_called_once()
        self.assertEqual(receipt["result"]["inbox_standings"], "applied")


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn
        except ImportError:
            raise unittest.SkipTest("Unicorn is optional")
        if not XBE.is_file():
            raise unittest.SkipTest("private USA executable is optional")
        cls.payload = XBE.read_bytes()
        if hashlib.sha256(cls.payload).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("requires pinned retail USA executable")
        cls.unicorn = unicorn

    def machine(self, payload):
        uc = self.unicorn
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        m.mem_map(0x10000, 0x2000000)
        for section in XbeImage(payload).sections:
            m.mem_write(section.start, payload[section.raw:section.raw + section.raw_size])
        self.m = m
        self.reg = uc.x86_const
        self.stubs = {}
        m.hook_add(uc.UC_HOOK_CODE, self.hook)
        return m

    def get(self, address):
        return struct.unpack("<I", self.m.mem_read(address, 4))[0]

    def put(self, address, value):
        self.m.mem_write(address, struct.pack("<I", value))

    def hook(self, m, address, size, _):
        if address in self.stubs:
            value = self.stubs[address]()
            m.reg_write(self.reg.UC_X86_REG_EAX, value)
            esp = m.reg_read(self.reg.UC_X86_REG_ESP)
            m.reg_write(self.reg.UC_X86_REG_EIP, self.get(esp))
            m.reg_write(self.reg.UC_X86_REG_ESP, esp + 4)

    def call(self, address, *, stack=(), **regs):
        self.put(0x1F00000, 0x1FF0000)
        for index, value in enumerate(stack):
            self.put(0x1F00004 + index * 4, value)
        self.m.reg_write(self.reg.UC_X86_REG_ESP, 0x1F00000)
        for name, value in regs.items():
            self.m.reg_write(getattr(self.reg, "UC_X86_REG_" + name.upper()), value)
        self.m.emu_start(address, 0x1FF0000, count=100000)
        self.assertEqual(self.m.reg_read(self.reg.UC_X86_REG_EIP), 0x1FF0000)
        self.assertEqual(self.m.reg_read(self.reg.UC_X86_REG_ESP), 0x1F00004 + len(stack) * 4)
        return self.m.reg_read(self.reg.UC_X86_REG_EAX)

    def test_native_event_writer_discards_date_and_wraps_and_clear_discards_kind(self):
        records = []
        for year, week in ((0, 0), (1, 8), (9, 17)):
            self.machine(self.payload)
            self.put(0xE576B8, year)
            self.put(0xE576B4, week)
            self.put(0xE3F06C, 599)
            self.call(0x2BFDF0, ecx=1, edx=0x1800000, stack=(0x1800200, 5, 0, 1))
            self.assertEqual(self.get(0xE3F06C), 0)
            address = 0xE3F070 + 599 * 12
            records.append(bytes(self.m.mem_read(address, 12)))
            self.call(0x2BFDC0, eax=599)
            cleared = bytes(self.m.mem_read(address, 12))
            self.assertEqual(cleared[1:], records[-1][1:])
            self.assertEqual(cleared[0], records[-1][0] & 0xE0)
        self.assertEqual(records, [records[0]] * 3)

    def test_forced_retail_story_is_blank_before_and_has_fallen_club_after(self):
        patched, _ = inbox.apply(self.payload)
        for payload, expected_count in ((self.payload, 0), (patched, 1)):
            with self.subTest(patched=expected_count):
                self.machine(payload)
                # Force the real generator's trigger: every club has a loss,
                # club 9 has its first loss in the latest game. Mock only
                # fixture lookups and news insertion, then run the generator.
                self.stubs = {0xC4BE0: lambda: 32, 0xC4BB0: lambda: 8,
                              0xC4C50: lambda: 0x1800000 + self.m.reg_read(self.reg.UC_X86_REG_ECX) * 0x200,
                              0xC7750: lambda: 1 if self.m.reg_read(self.reg.UC_X86_REG_ECX) == 0x1801200 else 2,
                              0xC7960: lambda: 1}
                inserted = []
                def news():
                    inserted.append((self.m.reg_read(self.reg.UC_X86_REG_ECX),
                                     self.m.reg_read(self.reg.UC_X86_REG_EDX)))
                    self.put(0xE40C90, 23 << 7)
                    return 0
                self.stubs[0x27E3C0] = news
                self.put(0x1F00000, 0x1FF0000)
                self.m.reg_write(self.reg.UC_X86_REG_ESP, 0x1F00000)
                # Stop after the undefeated branch, before the unrelated
                # power-ranking and per-team news generators.
                self.m.emu_start(0x27EB80, 0x27ECB5, count=100000)
                self.assertEqual(self.m.reg_read(self.reg.UC_X86_REG_EIP), 0x27ECB5)
                self.assertEqual(inserted, [(63, 23)])
                self.assertEqual(self.get(0xE40C94), 9)
                descriptor = self.call(0x361830, eax=0)
                self.assertEqual(descriptor, inbox.DESCRIPTOR)
                self.stubs.update({0x13EC80: lambda: 0x1803C00, 0xC7720: lambda: 6,
                                   0xC6480: lambda: 0, 0x360230: lambda: 0})
                for initial in (0, 4):
                    self.put(0xCC1AB8, initial)
                    callback = self.get(descriptor + 0x10)
                    if callback:
                        self.call(callback)
                    self.call(self.get(descriptor + 8), ecx=0, edx=0)
                    self.assertEqual(self.call(0x361E70), 1 if callback else initial)
                    self.assertEqual(self.call(0x361E80, ecx=0), 0x1801200)
                # Every other story descriptor, including Power Rankings, is identical.
                a, b = XbeImage(self.payload), XbeImage(patched)
                for story in range(45):
                    if story != inbox.STORY:
                        address = 0xAECD00 + story * 0x34
                        self.assertEqual(a.read(address, 0x34), b.read(address, 0x34))


if __name__ == "__main__":
    unittest.main()
