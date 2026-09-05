"""Bounded native initializer/animation slices. Synthetic inputs, no game boot.

All callees reached by these fixtures execute retail instructions, including
the interpolator, sqrt, speed conversion and animation bank/angle selection.
Each invocation is capped at 1000 instructions with an asserted stop address.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_zone_drop as zone
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None
YARD = 91.44


class Machine:
    HEAP, STACK, AUX = 0x3000000, 0x4000000, 0x5000000
    P, S, A, M, V, C = (0x3000000 + n * 0x1000 for n in range(6))
    TEAM, DIR, SIGN, GAME = (0x3000000 + n * 0x1000 for n in range(6, 10))
    SP = STACK + 0x8000

    def __init__(self, payload):
        import unicorn as u
        from unicorn import x86_const as x
        self.x = x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.image = XbeImage(payload)
        pages = {}
        for s in self.image.sections:
            for page in range(s.start & ~4095, (s.end + 4095) & ~4095, 4096):
                pages[page] = pages.get(page, u.UC_PROT_READ) | (u.UC_PROT_WRITE if s.writable else 0) | (u.UC_PROT_EXEC if s.executable else 0)
        for page in pages:
            self.uc.mem_map(page, 4096)
        for s in self.image.sections:
            self.uc.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        for page, flags in pages.items():
            self.uc.mem_protect(page, 4096, flags)
        self.uc.mem_map(self.HEAP, 0x10000)
        self.uc.mem_map(self.STACK, 0x10000)
        self.uc.mem_map(self.AUX, 4096)
        self.uc.mem_write(self.AUX, bytes.fromhex("dbe3") + b"".join(
            b"\xdd\x05" + struct.pack("<I", self.AUX + 0x100 + i * 8) for i in range(3)))
        self.uc.mem_write(self.AUX + 0x100, struct.pack("<3d", 2.25, -3.75, 6.5))
        self.wrapper = zone.site(payload)["va"] if zone.status(payload) == "applied" else None
        self.writes, self.visits, self.leaf_state = [], [], None
        self.uc.hook_add(u.UC_HOOK_MEM_WRITE, self._write)
        self.uc.hook_add(u.UC_HOOK_CODE, self._visit)

    def _write(self, _uc, _access, address, size, _value, _data):
        self.writes.append((address, size))

    def _visit(self, _uc, address, _size, _data):
        if address == self.stop:
            # Also stop explicitly when a previous invocation cached a larger
            # translation block spanning this invocation's earlier boundary.
            self.uc.emu_stop()
            return
        self.visits.append(address)
        if self.wrapper is not None and address == self.wrapper + 9:
            self.leaf_state = self.registers()
        if self.wrapper is not None and address == self.wrapper + 65:
            sp = self.uc.reg_read(self.x.UC_X86_REG_ESP)
            self.saved_environment = bytes(self.uc.mem_read(sp + 4, 28))

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def float(self, va, value):
        self.uc.mem_write(va, struct.pack("<f", value))

    def getf(self, va):
        return struct.unpack("<f", self.uc.mem_read(va, 4))[0]

    def setreg(self, name, value):
        self.uc.reg_write(getattr(self.x, "UC_X86_REG_" + name), value)

    def registers(self):
        names = ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP", "ESP", "EFLAGS",
                 "FPCW", "FPSW", "FPTAG", "FIP", "FDP", "FOP", "MXCSR")
        names += tuple("FP" + str(i) for i in range(8)) + tuple("XMM" + str(i) for i in range(8))
        return {name: self.uc.reg_read(getattr(self.x, "UC_X86_REG_" + name)) for name in names}

    def run(self, start, stop):
        self.stop = stop
        self.uc.emu_start(start, stop, count=1000)
        reached = self.uc.reg_read(self.x.UC_X86_REG_EIP)
        if reached != stop:
            raise AssertionError(f"instruction budget exhausted at {reached:#x}, expected {stop:#x}")

    def reset(self, position=18, mode=9, depth=3, lateral=0, sign=1, speed=0.8, landmark_depth=18, cw=0x37F):
        self.uc.mem_write(self.HEAP, bytes(0x10000))
        self.uc.mem_write(self.STACK, b"\xa5" * 0x10000)
        for off, ptr in ((0xC, self.C), (0x10, self.M), (0x18, self.V), (0x20, self.S), (0x38, self.TEAM)):
            self.put(self.P + off, ptr)
        self.uc.mem_write(self.P + 0x2C, bytes([position]))
        self.put(self.S + 0x310, self.A)
        self.put(self.S + 0x3E4, 14)
        self.float(self.M + 0x1B4, speed)
        self.put(self.M + 0x28, 2)  # explicit facing reference for native angle helper
        self.put(self.M + 0x10, 0)
        self.float(self.V + 0x38, depth * YARD * sign)
        self.float(self.V + 0x30, 300)
        self.put(0xE60280, self.TEAM)
        self.put(self.TEAM + 8, self.DIR)
        self.put(self.DIR + 12, self.SIGN)
        self.float(self.SIGN + 4, sign)
        self.put(0xE602EC, self.GAME)
        self.float(self.GAME + 0x18, 0)
        self.put(self.A + 0xA4, 5)
        self.float(self.A + 0x60, 0.9)  # established by the earlier initializer
        self.put(self.A + 0xAC, 0xBADC0DE)
        records = b"".join(struct.pack("<IffI", self.P if i == 5 else self.P + 0x100,
                                        300 + lateral * YARD, landmark_depth * YARD * sign,
                                        (0xC0FFEE << 8) | (mode if i == 5 else 15)) for i in range(22))
        self.uc.mem_write(zone.ZONE_RECORDS_VA, records)
        self.zone_before = records
        self.float(self.SP + 0x1C, landmark_depth * YARD * sign)
        self.float(self.SP + 0x20, 300 + lateral * YARD)
        self.run(self.AUX, self.AUX + 20)  # finit and three sentinel x87 values
        self.setreg("FPCW", cw)
        for i, name in enumerate(("EAX", "ECX", "EDX", "EBP")):
            self.setreg(name, 0x12340000 + i * 0x111)
        for i in range(8):
            self.setreg("XMM" + str(i), (0x1122334455667788 << 64) + i)
        self.setreg("EBX", self.P)
        self.setreg("ESI", self.A)
        self.setreg("EDI", mode & 8)
        self.setreg("ESP", self.SP)
        self.setreg("EFLAGS", 0xED7 & ~0x100)  # carry, direction, overflow; no single-step trap
        self.writes, self.visits, self.leaf_state = [], [], None

    def drop(self, **kwargs):
        self.reset(**kwargs)
        self.run(0x1A652A, 0x1A66D5)
        return {"q": self.getf(self.A + 0x34), "travel": self.getf(self.A + 0x60),
                "ac": self.get(self.A + 0xAC), "callback": self.get(self.A),
                "heap": bytes(self.uc.mem_read(self.HEAP, 0x10000)),
                "zones": bytes(self.uc.mem_read(zone.ZONE_RECORDS_VA, 22 * 16)),
                "registers": self.registers(), "visits": tuple(self.visits)}

    def animation(self, throttle, angle):
        self.float(self.C + 0x10, throttle)
        self.put(self.C + 0x14, angle)
        self.put(self.M + 0x14, 0)
        self.setreg("ECX", self.P)
        self.setreg("ESP", self.SP)
        self.put(self.SP, self.AUX + 0x80)
        self.run(0x238660, self.AUX + 0x80)
        group = self.uc.reg_read(self.x.UC_X86_REG_EAX)
        bank = self.get(group)
        self.setreg("ECX", self.P)
        self.setreg("EDX", bank)
        self.setreg("ESP", self.SP)
        self.put(self.SP, self.AUX + 0x80)
        self.run(0x305920, self.AUX + 0x80)
        row = self.get(self.M + 0x1C)
        return group, bank, self.get(row), self.get(row + 4)


@unittest.skipUnless(XBE.is_file() and HAVE_UC, "pinned USA default.xbe or Unicorn absent; bounded native proof requires both")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise AssertionError("retail evidence differs from pinned USA executable")
        cls.retail = Machine(retail)
        cls.patched = Machine(zone.apply(retail)[0])
        cls.custom = Machine(zone.apply(retail, cap=0.6)[0])

    def test_press_drop_and_native_directional_animation_vs_retail_run(self):
        for sign in (-1, 1):
            for depth in (3, 5):
                for lateral in (0, 4, 9):
                    with self.subTest(sign=sign, depth=depth, lateral=lateral):
                        old = self.retail.drop(depth=depth, lateral=lateral, sign=sign)
                        new = self.patched.drop(depth=depth, lateral=lateral, sign=sign)
                        self.assertEqual(old["q"], 1)
                        self.assertAlmostEqual(new["q"], 0.84)
                        self.assertEqual((old["ac"], new["ac"]), (0, 1))
                        self.assertAlmostEqual(new["travel"], 0.9)
                        max_speed = self.retail.image.read(0x4EDD28, 4), self.retail.image.read(0x4F0F70, 4)
                        maximum = struct.unpack("<f", max_speed[0])[0] * 0.8 + struct.unpack("<f", max_speed[1])[0]
                        self.assertAlmostEqual(old["travel"], math.hypot(18 - depth, lateral) * YARD / maximum, places=5)
                        for angle, clip in ((-32768, 0x7A99B0), (-16384, 0x7A85C4), (0, 0x7A9040), (16384, 0x7A85F8), (32767, 0x7A99B0)):
                            self.assertEqual(self.retail.animation(old["q"], angle), (0x511178, 0x511070, 3, 0x7AFAB0))
                            self.assertEqual(self.patched.animation(new["q"], angle), (0x511178, 0x511070, 4, clip))

    def test_off_corner_and_noneligible_actor_memory_remain_retail(self):
        cases = [{"depth": depth, "lateral": lateral} for depth in (7, 10, 15, 20) for lateral in (0, 4, 9)]
        cases += [{"position": position, "mode": mode, "depth": depth}
                  for position in (0, 16, 17, 50, 82, 114, 255) for mode in (8, 9, 10, 11, 15) for depth in (3, 7)]
        cases += [{"mode": mode, "depth": depth} for mode in (*range(8), 12, 13, 14, 15) for depth in (3, 7)]
        for case in cases:
            for sign in (-1, 1):
                with self.subTest(**case, sign=sign):
                    old, new = self.retail.drop(**case, sign=sign), self.patched.drop(**case, sign=sign)
                    self.assertEqual(new["heap"], old["heap"])
                    self.assertEqual(new["zones"], old["zones"])
                    if case.get("mode", 9) & 8 == 0:
                        self.assertNotIn(self.patched.wrapper, new["visits"])

    def test_boundary_modes_zone_records_and_only_expected_actor_writes(self):
        for mode in (8, 9, 10, 11):
            for depth in (1, 5.5, 6, 6.999, 7, 10, 15):
                for speed in (0.5, 1):
                    with self.subTest(mode=mode, depth=depth, speed=speed):
                        old = self.retail.drop(mode=mode, depth=depth, speed=speed)
                        new = self.patched.drop(mode=mode, depth=depth, speed=speed)
                        self.assertAlmostEqual(new["q"], min(old["q"], zone._cap(0.84)))
                        self.assertEqual(new["zones"], self.patched.zone_before)
                        self.assertEqual(new["callback"], 0x1A5790)
                        self.assertEqual(new["ac"], 1)
                        self.assertAlmostEqual(new["travel"], 0.9)
                        for address, size in self.patched.writes:
                            if self.patched.STACK <= address < self.patched.STACK + 0x10000:
                                continue
                            self.assertIn((address, size), ((self.patched.A, 4), (self.patched.A + 0x34, 4), (self.patched.A + 0xAC, 4)))

    def test_configurable_depth_cap_preserves_lateral_maximum_and_retail_floor(self):
        for depth, lateral, expected in ((3, 0, 0.6), (3, 7, 0.84), (10, 0, 0.6), (15, 0, 0.5)):
            with self.subTest(depth=depth, lateral=lateral):
                result = self.custom.drop(depth=depth, lateral=lateral)
                self.assertAlmostEqual(result["q"], expected)
                self.assertEqual(result["ac"], 1)
                self.assertAlmostEqual(result["travel"], 0.9)

    def test_wrapper_preserves_leaf_gprs_flags_x87_control_stack_and_sse(self):
        for position, mode in ((18, 9), (18, 15), (16, 9), (50, 9)):
            for depth in (3, 5.5, 7, 10, 15):
                for rounding in range(4):
                    with self.subTest(position=position, mode=mode, depth=depth, rounding=rounding):
                        m = self.patched
                        m.reset(position=position, mode=mode, depth=depth, cw=0x37F | rounding << 10)
                        m.setreg("ECX", 0x50B30C)
                        m.setreg("EDX", 4)
                        m.float(m.SP, depth * YARD)  # original caller's pushed argument
                        m.run(zone.HOOK_VA, zone.CONTINUE_VA)
                        before, after = m.leaf_state, m.registers()
                        self.assertIsNotNone(before)
                        self.assertEqual(m.visits.count(zone.CURVE_VA), 1)
                        self.assertEqual(after["ESP"], m.SP + 4)
                        top = (before["FPSW"] >> 11) & 7
                        for name in before:
                            # Unicorn 2.1.4 leaves FIP/FDP at the temporary FLD
                            # despite FLDENV. Assert their saved values below;
                            # restoration of these two pointers is an ISA-level
                            # contract, not a claimed Unicorn execution proof.
                            if name not in ("ESP", "FP" + str(top), "FIP", "FDP"):
                                self.assertEqual(after[name], before[name], name)
                        if position != 18 or mode & 12 != 8:
                            self.assertEqual(after["FP" + str(top)], before["FP" + str(top)])
                            self.assertEqual(after["FIP"], before["FIP"])
                            self.assertEqual(after["FDP"], before["FDP"])
                        else:
                            env = m.saved_environment
                            self.assertEqual(struct.unpack_from("<I", env, 12)[0], before["FIP"])
                            self.assertEqual(struct.unpack_from("<I", env, 20)[0], before["FDP"])


if __name__ == "__main__":
    unittest.main()
