"""b776 ns1: per-kit jersey number size (nfl2k5_team_number_scale), emulated with Unicorn on the real executable.

The table cases need no game files. The executable cases (skipped without the extracted retail default.xbe) run the
player builder's own jersey-number block, 0x8F556..0x8F587 (the selector call, the binder, the hook and the route
call), on the retail executable and on the same executable with the owner installed (with and without the number
kerning owner), and compare the bound number materials: every kit that is not in the table, every non-jersey row and
an empty texture slot must bind exactly the retail bytes; the listed kit gets the scaled transform.
"""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import nfl2k5_team_number_scale as ns  # noqa: E402
from mod_editor.core import nfl2k5_number_kerning as nk  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(_REPO_ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
XBE = GAME / "default.xbe"

try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_WRITE
    from unicorn.x86_const import (UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_ESP)
except ImportError:  # pragma: no cover - the suite's emulator is optional on lean hosts
    Uc = None

KC = {"13H0": 1.1, "13A0": 1.1}
START, STOP = 0x8F556, 0x8F587
WORK, STACK, FRAME = 0x2000000, 0x3000000, 0x2FF0000
RECORD, MODEL, MATS = WORK, WORK + 0x100, WORK + 0x1000
ROUTES = WORK + 0x200
N_MATS = 0xD2
CELLS = {0: (28, 29, 30), 11: (60, 61, 62), 7: (37, 38, 39)}     # NUMBER_, NECKROLL4_NUMBER_, NUMBER_sleeve_A_
STYLE_FOR_ROW = {0: 0, 11: 4, 7: 6}                               # jersey style -> row (0x4EF7F8)


def run(payload, number, *, kit="13h0.iff", slot=0, row=0, lod=0, materials=None, other_kit="08a0.iff"):
    """Emulate the builder's jersey-number block; return (material bytes after, list of writes outside the work
    area and the stack)."""
    image = XbeImage(payload)
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    end = (image.base + image.image_size + 0xFFFF) & ~0xFFFF
    mu.mem_map(0x10000, end - 0x10000)
    for s in image.sections:
        if s.raw_size:
            mu.mem_write(s.start, payload[s.raw:s.raw + min(s.raw_size, s.size)])
    mu.mem_map(WORK, 0x200000)
    # textures: a distinct handle per (family, digit, slot)
    for fam in range(3):
        for digit in range(10):
            for sl in range(2):
                mu.mem_write(0xA86C04 + 4 * (3 * (fam * 10 + digit) + sl),
                             struct.pack("<I", 0x70000000 + fam * 100 + digit * 10 + sl))
    for r, (cl, cm, cr) in CELLS.items():
        for lv in range(4):
            mu.mem_write(0xA86D6C + r * 16 + lv * 3, bytes([cl, cm, cr]))
    names = [kit, other_kit] if slot == 0 else [other_kit, kit]
    for i, name in enumerate(names):
        mu.mem_write(0xB30710 + 0x20 * i, (name + "\0").encode("utf-16le"))
    mu.mem_write(0xB652B0, struct.pack("<II", ROUTES, ROUTES))
    mu.mem_write(ROUTES + 8, struct.pack("<I", 1))
    mu.mem_write(RECORD + 0x20, struct.pack("<I", number << 3))
    mu.mem_write(RECORD + 0x1C, struct.pack("<I", STYLE_FOR_ROW[row] << 2))
    mu.mem_write(MODEL + 0x1C, struct.pack("<II", N_MATS, MATS))
    if materials is None:
        materials = b"".join(struct.pack("<8xI20x4f", 0x80000001, 1.0, 1.0, 0.0, 0.0).ljust(0x80, b"\0")
                             for _ in range(N_MATS))
    mu.mem_write(MATS, materials)
    mu.mem_map(STACK - 0x20000, 0x20000)
    ebp = FRAME
    mu.mem_write(ebp + 8, struct.pack("<I", lod))
    mu.mem_write(ebp + 0x10, struct.pack("<I", 0))
    mu.mem_write(ebp - 0x14, struct.pack("<I", slot))
    mu.mem_write(ebp - 0x10, struct.pack("<I", STYLE_FOR_ROW[row]))
    mu.reg_write(UC_X86_REG_EBP, ebp)
    mu.reg_write(UC_X86_REG_ESP, FRAME - 0x400)
    mu.reg_write(UC_X86_REG_EBX, RECORD)
    mu.reg_write(UC_X86_REG_EDI, MODEL)
    stray = []

    def on_write(_uc, _access, address, size, _value, _data):
        if not (WORK <= address < WORK + 0x200000 or STACK - 0x20000 <= address < STACK):
            stray.append((address, size))
    mu.hook_add(UC_HOOK_MEM_WRITE, on_write)
    mu.emu_start(START, STOP, count=4000)
    regs = tuple(mu.reg_read(r) for r in (UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP))
    return bytes(mu.mem_read(MATS, N_MATS * 0x80)), stray, regs


def cell(materials, index):
    return struct.unpack_from("<4fI", materials, index * 0x80 + 0x20)


class TableTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(ns.normalize({}), {})
        self.assertEqual(ns.normalize({"13a0": 1.1, "13H0": 1.1}), {"13A0": 1.1, "13H0": 1.1})
        for bad in ({"KC": 1.1}, {"13H0": 2.0}, {"13H0": float("nan")}, {"13H10": 1.1}, {"13H0": "1.1"},
                    {"13H0": 1.1, "13h0": 1.2}, []):
            with self.assertRaises(ValueError):
                ns.normalize(bad)

    def test_transform_is_an_enlargement_about_the_anchors(self):
        for s in (1.06, 1.1, 1.25):
            for c in range(3):
                su, sv, ou, ov = ns.transform(s, c)
                self.assertAlmostEqual(su, 4 / s, places=6)
                self.assertAlmostEqual(sv, 2 / s, places=6)
                # the anchor maps to itself: u' = su * (A / 4) + ou == A
                self.assertAlmostEqual(su * ns.ANCHOR_U[c] / 4 + ou, ns.ANCHOR_U[c], places=5)
                av = ns.anchor_v(s)
                self.assertAlmostEqual(sv * av / 2 + ov, av, places=5)
                # the glyph's top row never rises above the back decal's top
                top = ns.GLYPH_TOP
                self.assertGreaterEqual(av + (top - av) * s, ns.DECAL_TOP - 1e-6)

    def test_table_round_trip(self):
        code = ns.code_for(0x14EB500, KC)
        self.assertEqual(len(code), ns.CODE_SIZE)
        self.assertEqual(ns.read_table(code), ns.normalize(KC))
        with self.assertRaises(ValueError):
            ns.code_for(0x14EB500, {})


@unittest.skipUnless(Uc is not None and XBE.is_file(), "needs unicorn and the extracted retail default.xbe")
class ExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.kerned, _ = nk.apply(cls.retail)
        cls.scaled, cls.receipt = ns.apply(cls.retail, KC)
        cls.both, _ = ns.apply(cls.kerned, KC)

    def test_status_and_idempotence(self):
        self.assertEqual(ns.status(self.retail), "retail")
        self.assertEqual(ns.status(self.scaled), "applied")
        self.assertEqual(ns.read_settings(self.both), {"status": "applied", "scales": ns.normalize(KC)})
        self.assertEqual(nk.status(self.both), "applied")
        self.assertEqual(space.status(self.both), "applied")
        again, receipt = ns.apply(self.scaled, KC)
        self.assertEqual(again, self.scaled)
        self.assertEqual(receipt["changed_bytes"], 0)
        with self.assertRaises(ValueError):
            ns.apply(self.scaled, {"13H0": 1.05})
        same, receipt = ns.apply(self.retail, {})
        self.assertEqual(same, self.retail)
        self.assertEqual(receipt["changed_bytes"], 0)
        image = XbeImage(self.scaled)
        self.assertEqual(image.read(ns.HOOK_VA, 7)[:1], b"\xe9")
        retail_text = XbeImage(self.retail)
        for va, size, _digest in ns.GUARDS:
            if not va <= ns.HOOK_VA < va + size:
                self.assertEqual(image.read(va, size), retail_text.read(va, size))

    def test_other_kits_bind_the_retail_bytes(self):
        for base, patched in ((self.retail, self.scaled), (self.kerned, self.both)):
            for number in (0, 1, 4, 9, 10, 11, 15, 31, 56, 77, 99, 120):
                for kit, slot, row, lod in (("08a0.iff", 1, 0, 0), ("20h0.iff", 0, 0, 2), ("13h1.iff", 0, 0, 0),
                                            ("13a5.iff", 1, 11, 1), ("13h0.iff", 0, 7, 0), ("08h0.iff", 0, 11, 3)):
                    want, stray_a, regs_a = run(base, number, kit=kit, slot=slot, row=row, lod=lod)
                    got, stray_b, regs_b = run(patched, number, kit=kit, slot=slot, row=row, lod=lod)
                    self.assertEqual(got, want, (number, kit, row))
                    self.assertEqual(regs_a, regs_b)
                    self.assertEqual(stray_b, stray_a)

    def test_the_listed_kit_scales(self):
        for base, patched, kerning in ((self.retail, self.scaled, False), (self.kerned, self.both, True)):
            for kit, slot in (("13h0.iff", 0), ("13a0.iff", 1), ("13h0.iff", 1)):
                for row in (0, 11):
                    for number in (4, 15, 31, 77):
                        want, _s, _r = run(base, number, kit=kit, slot=slot, row=row)
                        got, stray, regs = run(patched, number, kit=kit, slot=slot, row=row)
                        _sa, _sb, regs_a = run(base, number, kit=kit, slot=slot, row=row)
                        self.assertEqual(regs, regs_a)
                        self.assertEqual(stray, [])
                        cl, cm, cr = CELLS[row]
                        cells = ((1, cm),) if number < 10 else ((0, cl), (2, cr))
                        for c, index in cells:
                            su, sv, ou, ov, flags = cell(got, index)
                            rsu, rsv, rou, rov, rflags = cell(want, index)
                            esu, esv, eou, eov = ns.transform(1.1, c, kern=rou if kerning else 0.0)
                            self.assertEqual((su, sv, ov, flags), (esu, esv, eov, rflags))
                            self.assertAlmostEqual(ou, eou, places=6)
                            self.assertEqual(struct.unpack_from("<I", got, index * 0x80 + 0x30),
                                             struct.unpack_from("<I", want, index * 0x80 + 0x30))
                        # everything but the bound cells' transform is the retail result
                        mask = bytearray(got)
                        for _c, index in cells:
                            mask[index * 0x80 + 0x20:index * 0x80 + 0x30] = want[index * 0x80 + 0x20:index * 0x80 + 0x30]
                        self.assertEqual(bytes(mask), want)

    def test_a_shared_material_returns_to_retail_for_the_next_kit(self):
        for base, patched in ((self.retail, self.scaled), (self.kerned, self.both)):
            for number in (4, 77, 31):
                after_kc, _s, _r = run(patched, number, kit="13h0.iff", slot=0)
                want, _s, _r = run(base, number, kit="08a0.iff", slot=1)
                got, _s, _r = run(patched, number, kit="08a0.iff", slot=1, materials=after_kc)
                self.assertEqual(got, want)


if __name__ == "__main__":
    unittest.main()
