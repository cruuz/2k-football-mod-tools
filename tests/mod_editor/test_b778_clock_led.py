"""Modern LED clock digits (nfl2k5_clock_led): the cave, the bulb-mask table, the loader hook, the late owner, and the
real cave run in Unicorn. No game boot.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent).  The palette fixture is
the ten clock-font palettes the retail stadium loader generates (10,240 bytes, SHA-256 pinned below).
"""
import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_clock_led as cl
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

FIXTURE = ROOT / "tests/fixtures/nfl2k5_clock_font_palettes.bin"
FIXTURE_SHA256 = "effe1d90369c368c128fa43298689eee8db359280ee3fd3e7ac707d1b6ed0ed4"
# The retail clock font's ten 6x7 digit patterns (row-major, six bulbs per row).  These are the shapes in the
# generated atlas; the palette index table must select exactly these bulbs for each digit.
PATTERNS = (
    ("111111", "110011", "110011", "110011", "110011", "110011", "111111"),
    ("011100", "011100", "001100", "001100", "001100", "001100", "001100"),
    ("111111", "000011", "000011", "111111", "110000", "110000", "111111"),
    ("111111", "000011", "000011", "111111", "000011", "000011", "111111"),
    ("110011", "110011", "110011", "111111", "000011", "000011", "000011"),
    ("111111", "110000", "110000", "111111", "000011", "000011", "111111"),
    ("111111", "110000", "110000", "111111", "110011", "110011", "111111"),
    ("111111", "000011", "000011", "000011", "000011", "000011", "000011"),
    ("111111", "110011", "110011", "111111", "110011", "110011", "111111"),
    ("111111", "110011", "110011", "111111", "000011", "000011", "111111"),
)


def palettes():
    data = FIXTURE.read_bytes()
    assert len(data) == 10 * 1024
    return [data[i * 1024:(i + 1) * 1024] for i in range(10)]


def visible_mask(pals, index):
    mask = 0
    for digit, pal in enumerate(pals):
        b, g, r, a = pal[index * 4:index * 4 + 4]
        if a and b + g + r > 60:
            mask |= 1 << digit
    return mask


class TableTests(unittest.TestCase):
    def test_fixture_pin(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), FIXTURE_SHA256)

    def test_body_table_selects_the_right_digits(self):
        pals = palettes()
        self.assertEqual(len(cl.BODY), 42)
        for gy in range(7):
            for gx in range(6):
                mask = 0
                for digit, pattern in enumerate(PATTERNS):
                    if pattern[gy][gx] == "1":
                        mask |= 1 << digit
                index = cl.BODY[gy * 6 + gx]
                self.assertNotEqual(index, 0xAA, (gx, gy))
                self.assertEqual(visible_mask(pals, index), mask, (gx, gy, index))

    def test_centres_fit_the_atlas(self):
        for gx, cx in enumerate(cl.CX):
            self.assertLessEqual(abs(cx - (gx + 0.5) * 128 / 6), 1)
        for gy, cy in enumerate(cl.CY):
            self.assertLessEqual(abs(cy - (gy + 0.5) * 128 / 7), 1)
        for cx in cl.CX:
            self.assertTrue(0 <= cx - 7 and cx + 7 < 128)
        for cy in cl.CY:
            self.assertTrue(0 <= cy - 7 and cy + 7 < 128)

    def test_cave_size_and_hook(self):
        code = cl.code_for(0x14DA000)
        self.assertEqual(len(code), cl.CODE_SIZE)
        self.assertEqual(cl.CODE_SIZE, 576)
        self.assertEqual(cl.HOOK, ("clock_led_font", 0x9999A, bytes.fromhex("895c240c8b")))
        self.assertEqual(cl.RESUME, 0x999A0)
        self.assertEqual(cl.GUARD[0], 0x99960)
        self.assertEqual(cl.GUARD[1], 80)
        self.assertEqual(code[cl.TABLE_OFF:cl.TABLE_OFF + 42], cl.BODY)
        self.assertEqual(code[cl.TABLE_OFF + 42:cl.TABLE_OFF + 48], cl.CX)
        self.assertEqual(code[cl.TABLE_OFF + 48:cl.TABLE_OFF + 55], cl.CY)
        self.assertEqual(code[-1], 0xCC)
        # the hook is the five retail bytes; the resume is the instruction after the displaced nop
        site = cl.sites(0x14DA000)
        self.assertEqual(site, [("clock_led_font", 0x9999A, bytes.fromhex("895c240c8b"),
                                 b"\xe9" + struct.pack("<i", 0x14DA000 - 0x9999A - 5))])

    def test_presets_options_and_late_owner_order(self):
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).modern_clock_led, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["modern_clock_led"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        self.assertIn("modern_clock_led", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_clock_led", "Modern clock digits"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        self.assertIn(cl.OWNER, space.LATE_OWNERS)
        self.assertGreater(space.LATE_OWNERS.index(cl.OWNER), space.LATE_OWNERS.index("nfl2k5_force_out"))
        text = (ROOT / "mod_editor/core/nfl2k5_clock_led.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("\u2014", cl.HELP_TEXT + cl.BUILD_CAPTION)


@unittest.skipIf(uc is None, "unicorn is not installed")
class CaveTests(unittest.TestCase):
    CODE, RESUME, ARRAY = 0x2200000, 0x999A0, 0xB66288
    ATLAS, OBJECTS, PALS, STACK = 0x2210000, 0x2218000, 0x2220000, 0x108000

    def run_cave(self):
        code = cl.code_for(self.CODE)
        machine = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        machine.mem_map(0x100000, 0x20000)
        machine.mem_map(0xB66000, 0x3000)
        machine.mem_map(self.CODE, 0x1000)
        machine.mem_map(self.ATLAS, 0x10000)
        machine.mem_map(self.PALS, 0x10000)
        machine.mem_map(0x99000, 0x1000)
        machine.mem_write(self.CODE, code)
        machine.mem_write(self.ATLAS, b"\x5a" * cl.ATLAS_SIZE)   # the cave clears it
        for i, pal in enumerate(palettes()):
            machine.mem_write(self.PALS + i * 0x400, pal)
            obj = self.OBJECTS + i * 0x20
            machine.mem_write(obj, struct.pack("<IIIIIIII", 0, self.ATLAS, self.PALS + i * 0x400,
                                               0x07750B29, 0, 0x80000000, 0x1FFFF, 0))
            machine.mem_write(self.ARRAY + i * 4, struct.pack("<I", obj))
        machine.mem_write(self.RESUME, b"\xf4")
        machine.reg_write(x86.UC_X86_REG_ESP, self.STACK)
        before = {r: 0x10000000 + i for i, r in enumerate((x86.UC_X86_REG_EBX, x86.UC_X86_REG_EBP,
                                                           x86.UC_X86_REG_ESI, x86.UC_X86_REG_EDI))}
        for reg, value in before.items():
            machine.reg_write(reg, value)
        machine.emu_start(self.CODE, self.RESUME, count=4_000_000)
        after = {reg: machine.reg_read(reg) for reg in before}
        return machine, before, after

    def test_cave_rewrites_the_atlas_and_palettes(self):
        machine, before, after = self.run_cave()
        self.assertEqual(before, after)
        atlas = bytes(machine.mem_read(self.ATLAS, cl.ATLAS_SIZE))
        expected = bytearray(b"\xaa" * cl.ATLAS_SIZE)
        for gy in range(7):
            for gx in range(6):
                cx, cy, body = cl.CX[gx], cl.CY[gy], cl.BODY[gy * 6 + gx]
                for dy in range(-7, 8):
                    at = (cy + dy) * 128 + cx - 7
                    expected[at:at + 15] = bytes([body]) * 15
        # four mip levels, each nearest-sampled from the previous level
        levels = ((0, 128), (0x4000, 64), (0x5000, 32), (0x5400, 16), (0x5500, 8))
        for (src_off, src_size), (dst_off, size) in zip(levels, levels[1:]):
            for y in range(size):
                for x in range(size):
                    expected[dst_off + y * size + x] = expected[src_off + (y * 2) * src_size + x * 2]
        self.assertEqual(atlas, bytes(expected))
        for i, pal in enumerate(palettes()):
            got = bytes(machine.mem_read(self.PALS + i * 0x400, 1024))
            want = bytearray(pal)
            for j in range(256):
                b, g, r, a = want[j * 4:j * 4 + 4]
                want[j * 4:j * 4 + 4] = (b"\xe8\xf8\xff\xff" if a and b + g + r > 60
                                         else b"\x00\x00\x00\xff")
            self.assertEqual(got, bytes(want), i)

    def test_each_palette_pass_stays_inside_its_1024_bytes(self):
        """b778 bd3: the palette pass used its loop counter for the brightness sum and wrote far past each palette.
        Palettes here sit 0x1000 apart with a sentinel after each; nothing outside the 1,024 bytes may change."""
        code = cl.code_for(self.CODE)
        machine = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        machine.mem_map(0x100000, 0x20000)
        machine.mem_map(0xB66000, 0x3000)
        machine.mem_map(self.CODE, 0x1000)
        machine.mem_map(self.ATLAS, 0x10000)
        machine.mem_map(self.PALS, 0x10000)
        machine.mem_map(0x99000, 0x1000)
        machine.mem_write(self.CODE, code)
        machine.mem_write(self.PALS, b"\x5c" * 0x10000)
        for i, pal in enumerate(palettes()):
            machine.mem_write(self.PALS + i * 0x1000, pal)
            obj = self.OBJECTS + i * 0x20
            machine.mem_write(obj, struct.pack("<IIIIIIII", 0, self.ATLAS, self.PALS + i * 0x1000,
                                               0x07750B29, 0, 0x80000000, 0x1FFFF, 0))
            machine.mem_write(self.ARRAY + i * 4, struct.pack("<I", obj))
        machine.mem_write(self.RESUME, b"\xf4")
        machine.reg_write(x86.UC_X86_REG_ESP, self.STACK)
        machine.emu_start(self.CODE, self.RESUME, count=4_000_000)
        self.assertEqual(machine.reg_read(x86.UC_X86_REG_EIP), self.RESUME)
        for i in range(10):
            tail = bytes(machine.mem_read(self.PALS + i * 0x1000 + 1024, 0x1000 - 1024))
            self.assertEqual(tail, b"\x5c" * len(tail), f"palette {i} pass wrote past its end")

    def test_zero_first_pointer_is_a_no_op(self):
        machine = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        machine.mem_map(0x100000, 0x20000)
        machine.mem_map(0xB66000, 0x3000)
        machine.mem_map(self.CODE, 0x1000)
        machine.mem_map(0x99000, 0x1000)
        machine.mem_write(self.CODE, cl.code_for(self.CODE))
        machine.mem_write(self.RESUME, b"\xf4")
        machine.reg_write(x86.UC_X86_REG_ESP, self.STACK)
        machine.emu_start(self.CODE, self.RESUME, count=10_000)
        self.assertEqual(machine.reg_read(x86.UC_X86_REG_EIP), self.RESUME)


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = cl.apply(cls.retail)

    def test_site_code_and_receipt(self):
        self.assertEqual(cl.status(self.retail), "retail")
        self.assertEqual(self.retail[0x1000 + 0x9999A - 0x11000:0x1000 + 0x9999A - 0x11000 + 5],
                         bytes.fromhex("895c240c8b"))
        self.assertEqual(cl.status(self.final), "applied")
        image = XbeImage(self.final)
        code_va = cl.allocation(self.final)["va"]
        self.assertEqual(image.read(code_va, cl.CODE_SIZE), cl.code_for(code_va))
        raw = image.read(cl.HOOK[1], 5)
        self.assertEqual(raw[0], 0xE9)
        self.assertEqual(cl.HOOK[1] + 5 + struct.unpack_from("<i", raw, 1)[0], code_va)
        self.assertEqual(image.read(cl.RESUME, 4), bytes.fromhex("8b54240c"))
        self.assertFalse(self.receipt["runtime_witnessed"])
        self.assertEqual(space.status(self.final), "applied")

    def test_only_the_hook_changes_in_retail_sections(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        changed = []
        for section in a.sections:
            if section.raw_size:
                x = a.read(section.start, section.raw_size)
                y = b.read(section.start, section.raw_size)
                changed += [section.start + i for i in range(len(x)) if x[i] != y[i]]
        self.assertEqual(changed, list(range(cl.HOOK[1], cl.HOOK[1] + 5)))

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = cl.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = cl.allocation(self.final)["va"]
        for label, (va, content) in {"hook": (cl.HOOK[1], b"\xe9\x00\x00\x00\x00"),
                                     "code": (code + 3, b"\x90"),
                                     "guard": (0x99960, b"\x90")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(cl.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                cl.apply(bad)
        bad = repin_edit(self.retail, cl.HOOK[1], b"\x90")
        self.assertEqual(cl.status(bad), "foreign")


if __name__ == "__main__":
    unittest.main()
