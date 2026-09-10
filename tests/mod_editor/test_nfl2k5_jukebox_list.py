"""Execute the actual collection list builder, including native label hashing."""
from pathlib import Path
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_music_metadata as metadata
from mod_editor.core import nfl2k5_jukebox_list as fix
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

try:
    import unicorn as u
    from unicorn.x86_const import *
except ImportError:
    u = None

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
    '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'


class Machine:
    def __init__(self, payload):
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1800000)
        self.uc.mem_map(0x2000000, 0x20000)
        image = XbeImage(payload)
        for section in image.sections:
            self.uc.mem_write(section.start, payload[section.raw:section.raw+section.raw_size])
        self.steps, self.labels, self.texts = 0, [], []
        self.stub_calls = set()
        self.uc.hook_add(u.UC_HOOK_CODE, self.hook)

    def get(self, at):
        return struct.unpack('<I', self.uc.mem_read(at, 4))[0]

    def put(self, at, *values):
        self.uc.mem_write(at, struct.pack('<'+'I'*len(values), *values))

    def string(self, at):
        out = bytearray()
        for n in range(256):
            word = self.uc.mem_read(at+n*2, 2)
            if word == b'\0\0':
                return out.decode('utf-16le')
            out.extend(word)
        raise AssertionError('unterminated string')

    def ret(self, value=0, pop=0):
        sp = self.uc.reg_read(UC_X86_REG_ESP)
        self.uc.reg_write(UC_X86_REG_EAX, value)
        self.uc.reg_write(UC_X86_REG_EIP, self.get(sp))
        self.uc.reg_write(UC_X86_REG_ESP, sp+4+pop)

    def hook(self, uc, at, size, _):
        self.steps += 1
        if at == 0x38650:
            self.labels.append(uc.reg_read(UC_X86_REG_ECX))
        # Only renderer and number formatter boundaries are replaced. Song
        # identity, title, duration, row count, and label hashing execute retail.
        if at in (0x2ad80, 0x2ac80, 0x151540, 0x1513d0, 0x4a400):
            self.stub_calls.add(at)
            if at == 0x151540:
                self.ret(0x2018000)
            elif at == 0x1513d0:
                self.texts.append(self.string(uc.reg_read(UC_X86_REG_EDX)))
                self.ret()
            elif at == 0x4a400:
                uc.mem_write(uc.reg_read(UC_X86_REG_ECX), b'1\0\0\0')
                self.ret(pop=4)
            else:
                self.ret()

    def run(self, va, ecx=0, edx=0, eax=0, args=()):
        stack, sentinel = 0x200f000, 0x2010000
        self.put(stack, sentinel, *args)
        for reg, value in ((UC_X86_REG_ESP, stack), (UC_X86_REG_EBP, 0),
                           (UC_X86_REG_ECX, ecx), (UC_X86_REG_EDX, edx),
                           (UC_X86_REG_EAX, eax)):
            self.uc.reg_write(reg, value)
        self.steps = 0
        self.uc.emu_start(va, sentinel, timeout=1000000, count=100000)
        assert self.uc.reg_read(UC_X86_REG_EIP) == sentinel, hex(self.uc.reg_read(UC_X86_REG_EIP))
        assert self.steps < 100000
        return self.uc.reg_read(UC_X86_REG_EAX)


@unittest.skipUnless(u and XBE.is_file(), 'retail USA XBE or Unicorn is absent')
class CollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()

    def library(self, count):
        songs = [dict(title=f'Song {i}', artist=f'Artist {i}', frames=22080) for i in range(count)]
        return metadata.apply(self.retail, songs)[0]

    def test_retail_loop_runs_out_of_widget_labels_at_sixth_disc_song(self):
        payload = bytearray(self.library(61))
        image = XbeImage(payload)
        for va, before, _ in fix.SITES:
            at = image.offset(va, len(before))
            payload[at:at+len(before)] = before
        machine = Machine(bytes(payload))
        machine.put(0xcb69f4, 17)
        with self.assertRaises(u.UcError):
            machine.run(0x32a0f0)
        self.assertEqual(machine.uc.reg_read(UC_X86_REG_EIP), 0x3865d)
        self.assertEqual(machine.labels[-1], 0)
        self.assertEqual(len(machine.labels), 16)

    def test_fixed_native_list_every_window_and_collection_independent(self):
        for count in (59, 60, 61, 193, 200):
            payload, _ = fix.apply(self.library(count))
            machine = Machine(payload)
            # Relocate the same expanded record list into another collection
            # in memory. Collection ownership/naming is D1's independent work.
            count17 = machine.get(metadata.COLLECTIONS+17*32+24)
            root17 = machine.get(metadata.COLLECTIONS+17*32+28)
            machine.put(metadata.COLLECTIONS+14*32+24, count17, root17)
            for collection in (14, 17):
                machine.put(0xcb69f4, collection)
                machine.run(0x329f20, eax=0)
                for first in range(max(1, count17-3)):
                    machine.put(0xcb6d40, first)
                    machine.labels.clear()
                    machine.texts.clear()
                    machine.run(0x32a0f0)
                    rows = min(4, count17-first)
                    self.assertEqual(len(machine.labels), rows*3+1)
                    self.assertTrue(all(machine.labels))
                    expected = [f'Song {55+first+i}' for i in range(rows)]
                    self.assertEqual(machine.texts[1:rows*3:3], expected)

    def test_hdd_label_window_keeps_thirteen_rows(self):
        # Stop before the UI loop calls into the native HDD APIs. Its pointer
        # bound must accept exactly thirteen row starts (22 through 58).
        payload, _ = fix.apply(self.retail)
        machine = Machine(payload)
        sentinel = 0x2010000
        for first, expected in ((22, 13), (49, 4)):
            for row in range(expected+1):
                machine.uc.reg_write(UC_X86_REG_ESI, 0xae6128+(first+row*3)*4)
                machine.uc.reg_write(UC_X86_REG_ESP, 0x200f000)
                machine.uc.emu_start(0x32a159, 0x32a169, count=2)
                self.assertEqual(machine.uc.reg_read(UC_X86_REG_EIP),
                                 0x32a255 if row == expected else 0x32a165)

    def test_native_down_button_scrolls_to_last_added_song(self):
        machine = Machine(self.library(193))
        machine.put(0xcb69f4, 17)
        machine.run(0x329f20, eax=0)
        count = machine.get(metadata.COLLECTIONS+17*32+24)
        # Actual disc down-button arm. Its retail disc/HDD capacity choice
        # already uses four/thirteen; only the list builder was inconsistent.
        for press in range(1, count+3):
            machine.put(0x200f000, 0x2010000)
            for reg, value in ((UC_X86_REG_ESP, 0x200f000),
                               (UC_X86_REG_ESI, 1), (UC_X86_REG_EBX, 0)):
                machine.uc.reg_write(reg, value)
            machine.uc.emu_start(0x32b450, 0x32b504, count=20000)
            self.assertEqual(machine.uc.reg_read(UC_X86_REG_EIP), 0x32b504)
            row, first = machine.get(0xcb6d38), machine.get(0xcb6d40)
            self.assertLess(row, 4)
            self.assertEqual(row+first, min(press, count-1))
        machine.texts.clear()
        machine.run(0x32a0f0)
        self.assertEqual(machine.texts[-3], 'Song 192')

    def test_pins_idempotence_and_foreign_rejection(self):
        self.assertEqual(fix.status(self.retail), 'retail')
        patched, _ = fix.apply(self.retail)
        self.assertEqual(fix.status(patched), 'applied')
        self.assertEqual(fix.apply(patched)[0], patched)
        image = XbeImage(patched)
        for va in (0x32a159, 0x32a24f, 0x32a200):
            bad = bytearray(patched)
            bad[image.offset(va)] ^= 1
            self.assertEqual(fix.status(bytes(bad)), 'foreign')
            with self.assertRaises(ValueError):
                fix.apply(bytes(bad))

    def test_parent_metadata_receipt_keeps_distinct_list_ownership(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        payload, receipt = metadata.apply(self.retail,
            [dict(title='Song', artist='Artist', frames=22080)]*61)
        recorder = Recorder(self.retail)
        recorder.observe(metadata, 'apply', self.retail, payload, receipt)
        for va, before, _ in fix.SITES:
            spans = [r for r in recorder.spans
                     if int(r['start'],0) < va+len(before) and int(r['end'],0) > va]
            self.assertTrue(spans)
            self.assertEqual({r['owner'] for r in spans}, {fix.OWNER})


if __name__ == '__main__':
    unittest.main()
