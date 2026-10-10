"""Jersey number kerning (b76 k2): the rewritten binder/selector, emulated with Unicorn.

The block-only cases need no game files: they emulate the owned routine against synthetic texture and material
tables. The retail cases (skipped without the extracted game) emulate the retail and the applied routine side by
side for every number, family and slot and require identical bindings apart from the jersey 1 offsets.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


import os
import struct
import unittest

from mod_editor.core import nfl2k5_number_kerning as nk

ROOT = Path(__file__).resolve().parents[2]
GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
XBE = GAME / "default.xbe"

try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI,
                                   UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_ESP)
except ImportError:  # pragma: no cover - the suite's emulator is optional on lean hosts
    Uc = None

SCENE, MATS, STACK, RET = 0x200000, 0x210000, 0x300000, 0x0FFFF0
L_IDX, M_IDX, R_IDX, N_MATS = 2, 3, 4, 8


def texture(family, digit, slot):
    return 0x70000000 + family * 100 + digit * 10 + slot


def bind(block, number, family=0xC, slot=0):
    """Run the selector on ``block`` and return {L, M, R: (texture, u scale, v scale, u offset, flags)} and the
    callee-saved registers and stack pointer after the return."""
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(0x8E000, 0x2000)
    mu.mem_write(nk.BLOCK_VA, block)
    mu.mem_map(0xA86000, 0x1000)
    for fam in range(3):
        for digit in range(10):
            for s in range(3):
                mu.mem_write(nk.TEXTURES + 4 * (3 * (fam * 10 + digit) + s), struct.pack("<I", texture(fam, digit, s)))
    for row in range(4):
        for lod in range(4):
            mu.mem_write(nk.MATS_L + row * 3 + lod * 16, bytes([L_IDX, M_IDX, R_IDX]))
    mu.mem_map(SCENE, 0x1000)
    mu.mem_write(SCENE + 0x1C, struct.pack("<II", N_MATS, MATS))
    mu.mem_map(MATS, 0x1000)
    for i in range(N_MATS):   # the model files' values: flags 1, scale 1, 1, offset 0, 0
        mu.mem_write(MATS + i * 0x80 + 8, struct.pack("<I", 1))
        mu.mem_write(MATS + i * 0x80 + 0x20, struct.pack("<4f", 1, 1, 0, 0))
    mu.mem_map(STACK - 0x10000, 0x20000)
    mu.mem_map(0x0FF000, 0x1000)
    sp = STACK - 0x100
    mu.mem_write(sp, struct.pack("<IIIII", RET, SCENE, 0, 0, slot))
    mu.reg_write(UC_X86_REG_ESP, sp)
    mu.reg_write(UC_X86_REG_EAX, number & 0xFFFFFFFF)
    mu.reg_write(UC_X86_REG_ECX, 0)
    mu.reg_write(UC_X86_REG_EDX, family)
    for reg, value in ((UC_X86_REG_EBX, 0x11), (UC_X86_REG_ESI, 0x22), (UC_X86_REG_EDI, 0x33), (UC_X86_REG_EBP, 0x44)):
        mu.reg_write(reg, value)
    mu.emu_start(nk.SELECTOR_VA, RET, count=500)
    cells = {}
    for name, index in (("L", L_IDX), ("M", M_IDX), ("R", R_IDX)):
        raw = bytes(mu.mem_read(MATS + index * 0x80, 0x80))
        su, sv, ou, _ov = struct.unpack_from("<4f", raw, 0x20)
        cells[name] = (struct.unpack_from("<I", raw, 0x30)[0], su, sv, round(ou, 6), struct.unpack_from("<I", raw, 8)[0])
    saved = tuple(mu.reg_read(r) for r in (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP))
    return cells, saved


def retail_block():
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    return XbeImage(XBE.read_bytes()).read(nk.BLOCK_VA, nk.BLOCK_SIZE)


K = round(nk.KERN, 6)


class BlockTests(unittest.TestCase):
    def test_layout(self):
        block = nk.APPLIED_BLOCK
        self.assertEqual(len(block), nk.BLOCK_SIZE)
        self.assertEqual(block[:2], bytes.fromhex("33d2"))                      # retail entry: U offset 0
        at = nk.SELECTOR_VA - nk.BLOCK_VA
        self.assertEqual(block[at:at + 3], bytes.fromhex("83ea0c"))             # selector entry kept
        self.assertEqual(nk.build_block(nk.KERN), block)
        self.assertNotEqual(nk.build_block(0.05), block)


@unittest.skipIf(Uc is None, "unicorn is not installed")
class EmulatedKerningTests(unittest.TestCase):
    def test_tens_one_moves_right_cell_untouched(self):
        cells, _ = bind(nk.APPLIED_BLOCK, 17)
        self.assertEqual(cells["L"], (texture(0, 1, 0), 4.0, 2.0, -K, 0))
        self.assertEqual(cells["R"], (texture(0, 7, 0), 4.0, 2.0, 0.0, 0))

    def test_ones_one(self):
        for number, tens in ((21, 2), (71, 7), (81, 8), (91, 9)):
            cells, _ = bind(nk.APPLIED_BLOCK, number)
            self.assertEqual(cells["L"][0], texture(0, tens, 0))
            self.assertEqual(cells["L"][3], 0.0)
            self.assertEqual(cells["R"][0], texture(0, 1, 0))
            self.assertEqual(cells["R"][3], K)

    def test_eleven_both_cells(self):
        cells, _ = bind(nk.APPLIED_BLOCK, 11, slot=2)
        self.assertEqual(cells["L"], (texture(0, 1, 2), 4.0, 2.0, -K, 0))
        self.assertEqual(cells["R"], (texture(0, 1, 2), 4.0, 2.0, K, 0))

    def test_other_pairs_zero(self):
        for number in (10, 20, 22, 45, 77, 88, 99, 100, 250):
            cells, _ = bind(nk.APPLIED_BLOCK, number)
            tens, ones = divmod(number if number <= 99 else 0, 10)
            self.assertEqual(cells["L"][3], -K if tens == 1 else 0.0, number)
            self.assertEqual(cells["R"][3], 0.0, number)

    def test_single_digit_and_other_families_untouched(self):
        for number in range(10):
            cells, _ = bind(nk.APPLIED_BLOCK, number)
            self.assertEqual(cells["M"], (texture(0, number, 0), 4.0, 2.0, 0.0, 0))
            self.assertEqual(cells["L"][3], 0.0)
        for family, index in ((0xD, 1), (0xE, 2)):
            for number in (1, 11, 17, 21):
                cells, _ = bind(nk.APPLIED_BLOCK, number, family)
                self.assertEqual({cells[c][3] for c in "LMR"}, {0.0}, (family, number))
        cells, _ = bind(nk.APPLIED_BLOCK, 11, 0xF)   # unknown family: nothing bound, as retail
        self.assertEqual({cells[c][0] for c in "LMR"}, {0})

    def test_registers_and_stack(self):
        for number in (1, 17, 71, 88):
            _cells, saved = bind(nk.APPLIED_BLOCK, number)
            self.assertEqual(saved, (0x11, 0x22, 0x33, 0x44, STACK - 0x100 + 4 + 16))


@unittest.skipIf(Uc is None or not XBE.is_file(), "needs unicorn and the extracted retail game")
class RetailEquivalenceTests(unittest.TestCase):
    def test_status_apply_verify(self):
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        retail = XBE.read_bytes()
        self.assertEqual(nk.status(retail), "retail")
        applied, receipt = nk.apply(retail, enabled=True)
        self.assertEqual(nk.status(applied), "applied")
        self.assertEqual(nk.verify(applied)["state"], "applied")
        self.assertEqual(nk.apply(applied, enabled=True)[0], applied)
        self.assertEqual(nk.apply(retail, enabled=False)[0], retail)
        with self.assertRaises(ValueError):
            nk.apply(applied, enabled=False)
        self.assertTrue(all(section_digest(applied, s) == s.stored_digest for s in _sections(applied)))
        self.assertEqual(sum(a != b for a, b in zip(retail, applied)), receipt["changed_bytes"])
        tampered = bytearray(applied)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        tampered[XbeImage(applied).offset(nk.BLOCK_VA + 0x60, 1)] ^= 0xFF
        self.assertEqual(nk.status(bytes(tampered)), "foreign")

    def test_same_bindings_as_retail_apart_from_the_jersey_one(self):
        retail = retail_block()
        for family in (0xC, 0xD, 0xE, 0xF):
            for number in list(range(100)) + [100, 150, -3]:
                for slot in (0, 2):
                    a, saved_a = bind(retail, number, family, slot)
                    b, saved_b = bind(nk.APPLIED_BLOCK, number, family, slot)
                    self.assertEqual(saved_a, saved_b)
                    expect = dict(a)
                    if family == 0xC and 10 <= number <= 99:
                        tens, ones = divmod(number, 10)
                        if tens == 1:
                            expect["L"] = a["L"][:3] + (-K,) + a["L"][4:]
                        if ones == 1:
                            expect["R"] = a["R"][:3] + (K,) + a["R"][4:]
                    self.assertEqual(b, expect, (hex(family), number, slot))


if __name__ == "__main__":
    unittest.main()
