"""b777 tp1: formation art icon spacing (late xbe_space owner, hooks 0x18108E and 0x1824EF).

Byte tests use the private USA retail default.xbe; the native test runs the owned code and the game's own
slot getter 0x17FE60 and diagram transform 0x180120 under Unicorn (optional) on formation records.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_formation_art_spacing as fa  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, HAVE_UC  # noqa: E402

# v4 Goal Line Sneak and Goal Line (slot order QB, line x5, then the five skill players), centimetres
GOAL_LINE_SNEAK = [(0, -185), (302, 0), (-302, 0), (0, 0), (155, 0), (-155, 0), (-457, 0), (457, 0),
                   (0, -384), (73, -274), (-73, -274)]
GOAL_LINE = [(0, -185), (302, 0), (-302, 0), (0, 0), (155, 0), (-155, 0), (-457, 0), (457, 0),
             (594, -91), (0, -366), (0, -594)]
I_FORM = [(0, -185), (302, 0), (-302, 0), (0, 0), (155, 0), (-155, 0), (457, 0), (-1554, 0),
          (1463, -137), (0, -502), (0, -731)]   # retail I Pro depths


def record(positions, type_code=0):
    rec = bytearray(0xB4)
    struct.pack_into("<I", rec, 4, type_code << 8)
    for s, (x, z) in enumerate(positions):
        r = 0x1A + s * 14
        rec[r + 1] = (0xB << 4) | 1
        struct.pack_into("<hhh", rec, r + 2, x, x, x)
        struct.pack_into("<hhh", rec, r + 8, z, z, z)
    return bytes(rec)


def overlaps(pos):
    return [(i, j) for i in range(11) for j in range(i + 1, 11)
            if ((pos[i][0] - pos[j][0]) / fa.ICON_ACROSS) ** 2 + ((pos[i][1] - pos[j][1]) / fa.ICON_DEEP) ** 2 < 0.999]


class Wiring(unittest.TestCase):
    def test_last_late_owner_tied_to_play_art(self):
        self.assertEqual(space.LATE_OWNERS[-8:-1], (fa.OWNER, "nfl2k5_force_out", "nfl2k5_practice_injuries", "nfl2k5_ball_carrier_ai", "nfl2k5_star_retention", "nfl2k5_star_career", "nfl2k5_draft_clock"))  # b778-fo1 last
        rows = [r for r in mod_build._LATE_OWNER_OPTIONS if r[0] == fa.OWNER]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0][2](mod_build.BuildPlan("a", "b", play_art_routes=True)))
        self.assertFalse(rows[0][2](mod_build.BuildPlan("a", "b", play_art_routes=False)))
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["play_art_routes"])
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["play_art_routes"])
        allow = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").split()
        self.assertIn("mod_editor/core/nfl2k5_formation_art_spacing.py", allow)
        text = (ROOT / "mod_editor/core/nfl2k5_formation_art_spacing.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/noah", text)
        self.assertNotIn("/media/noah", text)

    def test_owned_code_layout(self):
        code = fa.code_bytes()
        self.assertEqual(len(code), fa.CODE_SIZE)
        self.assertEqual(fa.REQUESTS, ((fa.OWNER, "code", 1024, 16),))
        self.assertEqual(fa.ABSMASK_OFFSET % 16, 0)
        self.assertEqual(code[fa.ABSMASK_OFFSET:fa.ABSMASK_OFFSET + 16], bytes.fromhex("ffffff7f") * 4)
        self.assertEqual(fa.CODE[-8:], struct.pack("<II", 0x17FE60, 0x180120))   # called through their entry points
        self.assertEqual(set(code[len(fa.CODE):]), {0xCC})


class RetailBytes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.after, cls.receipt = fa.apply(cls.retail)

    def test_retail_apply_replay(self):
        self.assertEqual(fa.status(self.retail), "retail")
        self.assertEqual(fa.status(self.after), "applied")
        again, receipt = fa.apply(self.after)
        self.assertEqual(again, self.after)
        self.assertTrue(receipt["already_applied"])
        va = int(self.receipt["code_va"], 16)
        self.assertEqual(va % 16, 0)
        image = XbeImage(self.after)
        self.assertEqual(image.read(va, fa.CODE_SIZE), fa.code_bytes())
        for _label, site, _retail in fa.HOOKS:
            self.assertEqual(image.read(site, 5), fa.hook_bytes(site, va))

    def test_only_the_two_calls_change_in_retail_code(self):
        before, after = XbeImage(self.retail), XbeImage(self.after)
        text = next(s for s in before.sections if s.name == ".text")
        a, b = before.read(text.start, text.raw_size), after.read(text.start, text.raw_size)
        changed = [text.start + i for i in range(len(a)) if a[i] != b[i]]
        allowed = {site + k for _l, site, _r in fa.HOOKS for k in range(1, 5)}
        self.assertTrue(changed)
        self.assertTrue(set(changed) <= allowed, [hex(v) for v in changed if v not in allowed])

    def test_appends_after_an_installed_allocator_without_moving_owners(self):
        grown, _ = space.apply(self.retail, (), scaleout=True)
        rows = space.layout(grown)["allocations"]
        out, _ = fa.apply(grown)
        self.assertEqual(fa.status(out), "applied")
        after = space.layout(out)["allocations"]
        self.assertTrue(all(r in after for r in rows))

    def test_foreign_bytes_are_refused(self):
        buf = bytearray(self.retail)
        off = XbeImage(self.retail).offset(0x181100)
        buf[off] ^= 0xFF
        self.assertEqual(fa.status(bytes(buf)), "foreign")
        with self.assertRaises(ValueError):
            fa.apply(bytes(buf))
        buf = bytearray(self.retail)
        off = XbeImage(self.retail).offset(fa.HOOKS[0][1])
        buf[off + 1] ^= 0x01
        self.assertEqual(fa.status(bytes(buf)), "foreign")


@unittest.skipUnless(HAVE_UC, "Unicorn is an optional test dependency")
class Native(unittest.TestCase):
    CODE_VA, REC_VA, OUT_VA, STACK, STOP = 0x7200000, 0x7300000, 0x7301000, 0x7400000, 0x7500000

    @classmethod
    def setUpClass(cls):
        import unicorn as U
        from unicorn import x86_const as X
        cls.U, cls.X = U, X
        data = fa.apply(retail_bytes())[0]
        image = XbeImage(data)
        cls.code_va = int(fa.apply(retail_bytes())[1]["code_va"], 16)
        uc = U.Uc(U.UC_ARCH_X86, U.UC_MODE_32)
        lo, hi = image.base, max(s.end for s in image.sections)
        uc.mem_map(lo, ((hi - lo) + 0xFFFF) & ~0xFFF)
        uc.mem_write(lo, data[:image.headers_size])
        for s in image.sections:
            if s.raw_size:
                uc.mem_write(s.start, data[s.raw:s.raw + min(s.raw_size, s.size)])
        for va in (cls.REC_VA, cls.STACK, cls.STOP):
            uc.mem_map(va, 0x10000)
        uc.mem_write(cls.STOP, b"\xf4")
        cls.uc = uc

    def _call(self, va, args, regs):
        uc, X = self.uc, self.X
        esp = self.STACK + 0x7FF8
        stack = struct.pack("<I", self.STOP) + b"".join(struct.pack("<I", a) for a in args)
        esp -= len(stack)
        uc.mem_write(esp, stack)
        uc.reg_write(X.UC_X86_REG_ESP, esp)
        for r, v in regs.items():
            uc.reg_write(getattr(X, "UC_X86_REG_" + r.upper()), v)
        uc.emu_start(va, self.STOP, count=3_000_000)
        self.assertEqual(uc.reg_read(X.UC_X86_REG_ESP), esp + len(stack))
        return {r: uc.reg_read(getattr(X, "UC_X86_REG_" + r.upper())) for r in regs}

    def drawn(self, positions, type_code=0, flag=0, spaced=True, esi=0):
        uc = self.uc
        rec = bytearray(record(positions, type_code))
        struct.pack_into("<I", rec, 0, self.REC_VA + 0x800)            # the record's name pointer at run time
        uc.mem_write(self.REC_VA, bytes(rec))
        uc.mem_write(self.REC_VA + 0x800, "X".encode("utf-16-le") + b"\0\0")
        uc.mem_write(0xBDFC20, struct.pack("<I", self.REC_VA))
        uc.mem_write(0xBDFC10, struct.pack("<I", flag))
        uc.mem_write(0xBDFBE4, struct.pack("<I", 1))                    # the formation strip's grid snap
        out = []
        for slot in range(11):
            self._call(0x17FE60, (flag,), dict(ecx=slot, edx=self.REC_VA, esi=0, eax=self.OUT_VA))
            if spaced:
                regs = dict(ebx=0x1111, esi=esi, edi=slot, ebp=0x3333)
                self.assertEqual(self._call(self.code_va, (self.OUT_VA, 1), regs), regs)
            else:
                self._call(0x180120, (self.OUT_VA, 1), dict(ebx=0, esi=0, edi=0))
            x, _y, z, _w = struct.unpack("<4f", bytes(uc.mem_read(self.OUT_VA, 16)))
            out.append((x, z))
        return out

    def test_goal_line_icons_no_longer_overlap(self):
        for positions in (GOAL_LINE_SNEAK, GOAL_LINE):
            for flag in (0, 1):
                before = self.drawn(positions, flag=flag, spaced=False)
                after = self.drawn(positions, flag=flag)
                self.assertTrue(overlaps(before))
                self.assertEqual(overlaps(after), [])
                for (bx, bz), (ax, az) in zip(before[:8], after[:8]):    # QB and the line keep their spots
                    self.assertEqual((bx, bz), (ax, az))

    def test_sneak_backs_side_by_side_in_field_order(self):
        after = self.drawn(GOAL_LINE_SNEAK)
        self.assertGreater(after[9][0], after[10][0])         # the FB (x +73) stays right of the HB (x -73)
        self.assertAlmostEqual(after[9][1], after[10][1])

    def test_spaced_formations_and_other_paths_are_retail(self):
        self.assertEqual(self.drawn(I_FORM), self.drawn(I_FORM, spaced=False))
        self.assertEqual(self.drawn(GOAL_LINE, type_code=9), self.drawn(GOAL_LINE, type_code=9, spaced=False))
        # live player positions (hold-L1 art): esi != 0 runs the retail transform on the vector as given
        self.assertEqual(self.drawn(GOAL_LINE, esi=0x7301100), self.drawn(GOAL_LINE, spaced=False))


if __name__ == "__main__":
    unittest.main()
