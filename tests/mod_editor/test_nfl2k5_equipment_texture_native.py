"""Bounded retail CPU fixtures for TSET allocation, descriptors and GPU commands.

These execute isolated instructions, not the game or a GPU. In particular,
accepting and submitting a one-level format is not a distance-rendering witness.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
XBE = Path(os.environ.get("NFL2K5_RETAIL_XBE", "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe"))
RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"

try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import (
        UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP,
        UC_X86_REG_EIP,
    )
except ImportError:
    Uc = None


@unittest.skipUnless(Uc is not None and XBE.is_file(), "Private retail default.xbe or Unicorn is absent")
class NativeEquipmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not 0 < XBE.stat().st_size <= 16 * 1024 * 1024:
            raise AssertionError("Equipment native proof requires a bounded retail executable")
        cls.retail = XBE.read_bytes()  # 11.4 MiB executable, never a disc/pack
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise AssertionError("Equipment native proof requires the pinned retail executable")

    def setUp(self):
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1600000)
        base = struct.unpack_from("<I", self.retail, 0x104)[0]
        count, table = struct.unpack_from("<II", self.retail, 0x11C)
        for i in range(count):
            _flags, va, _size, raw, rawsize = struct.unpack_from("<5I", self.retail, table - base + i * 0x38)
            if rawsize:
                self.uc.mem_write(va, self.retail[raw:raw + rawsize])
        self.uc.mem_map(0x2000000, 0x400000)
        self.uc.mem_map(0x3000000, 0x20000)
        self.stop = 0x301F000

    def put(self, address, *words):
        self.uc.mem_write(address, struct.pack("<" + "I" * len(words), *words))

    def words(self, address, count=1):
        return struct.unpack("<" + "I" * count, self.uc.mem_read(address, 4 * count))

    def run_native(self, address, *, eax=0, ecx=0, edx=0, args=(), count=20_000):
        stack = 0x3010000
        self.put(stack, self.stop, *args)
        for register, value in ((UC_X86_REG_ESP, stack), (UC_X86_REG_EAX, eax),
                                (UC_X86_REG_ECX, ecx), (UC_X86_REG_EDX, edx)):
            self.uc.reg_write(register, value)
        self.uc.emu_start(address, self.stop, timeout=1_000_000, count=count)
        self.assertEqual(self.uc.reg_read(UC_X86_REG_EIP), self.stop, "Native fixture exhausted its instruction bound")
        return self.uc.reg_read(UC_X86_REG_EAX)

    def test_tset_allocator_uses_grown_wrapper_video_and_scratch(self):
        sizes = []

        def external(uc, address, _size, _data):
            if address not in (0x437D0, 0x48700):
                return
            if address == 0x48700:
                sizes.append(uc.reg_read(UC_X86_REG_EDX))
            uc.reg_write(UC_X86_REG_EAX, 0x2100000)
            esp = uc.reg_read(UC_X86_REG_ESP)
            uc.reg_write(UC_X86_REG_EIP, self.words(esp)[0])
            uc.reg_write(UC_X86_REG_ESP, esp + 4)

        self.uc.hook_add(UC_HOOK_CODE, external)
        for video in (93568, 180992):
            self.put(0x2001000, 0x54455354, 54688, 640, video, 0xFEEDBEEF, 2880, 0, 0)
            self.assertEqual(self.run_native(0x451D0, eax=0x2001000), 1)
            self.assertEqual(sizes[-1], 640 + video + 2880)
            self.assertEqual(self.words(0xB12124)[0], 0x2100000 + 640)

    def test_individual_tset_callbacks_relocate_own_and_sibling_descriptors(self):
        video_base = 0x2100000
        self.put(0xB12124, video_base)
        self.put(0x2000008, 0)
        for number, (pixel, levels) in enumerate(((0, 6), (93568, 6), (180992, 1))):
            record = 0x2000200 + number * 0x24
            descriptor = 0x2001000 + number * 32
            palette = 87360 + number * 1088
            self.put(descriptor, 0, pixel, palette, 0x08800B29 | levels << 16, 0, 0x80000000)
            self.put(record + 0x14, descriptor)
            self.put(record + 0x20, 0x2000000)
            self.assertEqual(self.run_native(0x450B0, ecx=record), 1)
            self.assertEqual(self.words(descriptor, 6),
                             (0, video_base + pixel, video_base + palette,
                              0x08800B29 | levels << 16, 0, 0x80000000))
        self.assertEqual(self.words(0x2000008)[0], 3)
        self.assertEqual(self.words(0x2001004)[0], video_base)  # sibling did not move

    def test_mip_count_one_and_full_count_reach_gpu_format_unchanged(self):
        descriptor, context, material, commands = 0x2001000, 0x2002000, 0x2003000, 0x2200000
        self.put(context + 0xC, commands)
        for count in (1, 3, 4, 5, 6):
            with self.subTest(mip_levels=count):
                packed = 0x08800B29 | count << 16
                self.put(descriptor, 0, 0x2116D80, 0x2115540, packed, 0, 0x80000000)
                self.put(context + 0xC, commands)
                self.run_native(0x31FA0, eax=descriptor, ecx=0, args=(context, material, 0))
                self.assertEqual(self.words(commands, 5),
                                 (0x81B00, 0x2116D80, packed, 0x41B20, 0x2115540))

    def test_misaligned_private_chain_loses_native_direct_use_flag(self):
        descriptor = 0x2001000
        self.put(descriptor, 0, 93569, 87360, 0x08860B29, 0, 0x80000000)
        self.run_native(0x34DF0, ecx=descriptor, edx=0x2100000)
        self.assertEqual(self.words(descriptor + 0x14)[0], 0)

    def test_native_in_place_decoder_accepts_optimal_streams_and_guards(self):
        from mod_editor.core.nfl2k5_equipment_lz import compress_equipment_optimal
        from nfl_txtr import minimum_vc_lz_overlap_scratch

        expected = bytes(range(256)) * 8 + b"aabaaaaabaaaaaababbaaba" * 90
        for bits in (10, 11, 12, 13):
            with self.subTest(offset_bits=bits):
                encoded = compress_equipment_optimal(expected, offset_bits=bits, stream_tag=1,
                                                       max_encoded_size=10000)
                stored = len(encoded) + 256
                scratch = (max(256, minimum_vc_lz_overlap_scratch(encoded, stored, len(expected))) + 15) & ~15
                destination = 0x2100100
                end = destination + len(expected) + scratch
                source = end - stored
                self.uc.mem_write(destination - 32, b"P" * 32)
                self.uc.mem_write(end, b"S" * 32)
                self.uc.mem_write(destination, b"\xA5" * (len(expected) + scratch))
                self.uc.mem_write(source, encoded + bytes(256))
                self.run_native(0x4DC00, ecx=source, edx=destination, count=500_000)
                self.assertEqual(bytes(self.uc.mem_read(destination, len(expected))), expected)
                self.assertEqual(bytes(self.uc.mem_read(destination - 32, 32)), b"P" * 32)
                self.assertEqual(bytes(self.uc.mem_read(end, 32)), b"S" * 32)


if __name__ == "__main__":
    unittest.main()
