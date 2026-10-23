"""b778-ee1 alien prospect: the in-place code under Unicorn (the roll, once per franchise, the rate over 100 seasons,
the gray lookups, the wrapper), the executable spans, the art pins; with NFL2K5_RETAIL_XBE, the rewritten coin blocks
against retail's own bytes; with NFL2K5_RELEASED_ISO, the image plan on the released disc."""
from __future__ import annotations

import os
import random
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_alien_prospect as ap  # noqa: E402

RETAIL_XBE = os.environ.get("NFL2K5_RETAIL_XBE")
RELEASED_ISO = os.environ.get("NFL2K5_RELEASED_ISO")

# the season driver (tools/b77/ee1_alien_prospect.S's test companion, linked at DRIVER): for each season of ebp
# seasons: [YEAR] = season, [CLASSLEFT] = 380 down to 1, clear the record's photo, call alien, count photo 1947 hits
DRIVER = 0x2600000
DRIVER_CODE = bytes.fromhex("31db891db876e500c705dc1ce4007c01000066c746060000e80000000066817e069b077503ff049fff0ddc1ce40075e2"
                            "4339eb72cdf4")
DRIVER_CALL = 0x18
ROSTER, TEMPLATES, RECORD, COUNTS, STACK = 0x2000000, 0x2010000, 0x2020000, 0x2030000, 0x2080000
# a stand-in for the game's rand() at 0x48B50 (ecx = generator): xorshift32 state at [ecx], eax = next
RAND_STUB = bytes.fromhex("8b0189c2c1e20d31d089c2c1ea1131d089c2c1e20531d08901c3")


def _machine(test=False, seed=1):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(0x0, 0x1000000)
    mu.mem_map(0x2000000, 0x700000)
    mu.mem_write(ap.CODE_VA, ap.code_bytes(test))
    mu.mem_write(0x48B50, RAND_STUB)
    mu.mem_write(0xE5FCA0, struct.pack("<I", 0x9E3779B9 ^ (seed * 2654435761 & 0xFFFFFFFF) or 1))
    mu.mem_write(0xB72918, struct.pack("<I", ROSTER))
    mu.mem_write(ROSTER + 8, struct.pack("<II", 68, TEMPLATES))
    driver = bytearray(DRIVER_CODE)
    struct.pack_into("<i", driver, DRIVER_CALL + 1, ap.SYMBOLS["alien"] - (DRIVER + DRIVER_CALL + 5))
    mu.mem_write(DRIVER, bytes(driver))
    return mu


def run_franchise(mu, seasons=100, flag=0, start=0):
    """Seasons start..seasons-1 (a franchise loaded in its season ``start``); per-season hit counts and the flag."""
    from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_ESP
    mu.mem_write(TEMPLATES + 2 * 0x54 + 0x0F, bytes([flag]))
    mu.mem_write(COUNTS, bytes(4 * seasons))
    mu.reg_write(UC_X86_REG_ESI, RECORD)
    mu.reg_write(UC_X86_REG_EDI, COUNTS)
    mu.reg_write(UC_X86_REG_EBP, seasons)
    mu.reg_write(UC_X86_REG_ESP, STACK)
    mu.reg_write(UC_X86_REG_EBX, start)
    mu.emu_start(DRIVER + 2 if start else DRIVER, DRIVER + len(DRIVER_CODE) - 1)   # +2: past xor ebx,ebx
    return list(struct.unpack(f"<{seasons}I", bytes(mu.mem_read(COUNTS, 4 * seasons)))), \
        bytes(mu.mem_read(TEMPLATES + 2 * 0x54 + 0x0F, 1))[0]


def _unicorn():
    try:
        import unicorn  # noqa: F401
    except ImportError:  # pragma: no cover - unicorn ships with the Studio runtime
        raise unittest.SkipTest("unicorn is not installed")


class Code(unittest.TestCase):
    def test_fits_and_patch_points(self):
        self.assertLessEqual(len(ap.CODE), ap.CODE_END - ap.CODE_VA)
        self.assertEqual(len(ap.code_bytes()), ap.CODE_END - ap.CODE_VA)
        self.assertEqual(ap.code_bytes()[ap.OFF_FIRST_SEASON_JMP], 0xEB)
        self.assertEqual(ap.code_bytes(True)[ap.OFF_FIRST_SEASON_JMP:ap.OFF_FIRST_SEASON_JMP + 2], b"\x90\x90")
        self.assertEqual(struct.unpack_from("<I", ap.code_bytes(True), ap.OFF_THRESH)[0], 0xFFFFFFFF)
        # the coin loop ends by jumping back into retail code right after the 17 blocks
        self.assertIn(b"\xe9" + struct.pack("<i", ap.CODE_END - (ap.SYMBOLS["table"])), ap.CODE)

    def test_odds(self):
        self.assertAlmostEqual(ap.per_class_probability(), 1 / 150, delta=2e-5)
        hundred = 1 - (1 - ap.per_class_probability()) ** 99    # the first class never rolls
        self.assertTrue(0.47 < hundred < 0.50, hundred)

    def test_spans_are_relative_calls(self):
        for va, data, _label in ap._spans():
            if va in (ap.CALL_SITE, ap.HAND_SITE, ap.ARM_SITE, ap.NECK_SITE):
                self.assertEqual(data[0], 0xE8)
                target = va + 5 + struct.unpack_from("<i", data, 1)[0]
                self.assertIn(target, (ap.WRAP_VA, ap.HAND_VA, ap.ARM_VA, ap.NECK_VA))
                self.assertTrue(all(b == 0x90 for b in data[5:]))
        self.assertEqual(len(ap.RECORD_NAME), len(ap.RETAIL_RECORD))


class Roll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _unicorn()

    def test_once_per_franchise_and_rate(self):
        """400 franchises x 100 seasons on the real roll code: never twice, never in the first class, about 48 %."""
        ever, classes, hits = 0, 0, 0
        for seed in range(1, 401):
            counts, flag = run_franchise(_machine(seed=seed))
            self.assertLessEqual(sum(counts), 1, f"franchise {seed} had him twice")
            self.assertEqual(counts[0], 0, "the first class of a franchise never rolls")
            self.assertEqual(flag & 1, int(sum(counts) == 1), "the saved flag is set exactly when he appeared")
            ever += sum(counts)
        self.assertTrue(0.40 < ever / 400 < 0.57, ever)

    def test_per_class_rate(self):
        """Without the once-only flag (cleared before every season) the hit rate per class is 1 in 150."""
        mu = _machine(seed=99)
        hits = 0
        for season in range(1500):
            counts, _ = run_franchise(mu, seasons=2, flag=0, start=1)
            hits += counts[1]
        self.assertTrue(4 <= hits <= 18, hits)   # expected 10 (Poisson, 0.999 bounds)

    def test_old_franchise_flag_blocks(self):
        counts, flag = run_franchise(_machine(seed=5), flag=1, start=3)   # a franchise that already had him
        self.assertEqual(sum(counts), 0)
        self.assertEqual(flag, 1)

    def test_new_franchise_clears_a_reused_roster(self):
        """Year 0, first prospect: the flag a previous franchise left in RAM is cleared (and nothing rolls)."""
        counts, flag = run_franchise(_machine(seed=6), seasons=1, flag=1)
        self.assertEqual((counts, flag), ([0], 0))

    def test_test_build_hits_first_prospect_once(self):
        counts, flag = run_franchise(_machine(test=True, seed=7), seasons=5)
        self.assertEqual(counts, [1, 0, 0, 0, 0])
        self.assertEqual(flag, 1)

    def test_the_alien_record(self):
        from unicorn.x86_const import UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX
        mu = _machine(test=True, seed=8)
        rec = bytearray(random.Random(3).getrandbits(8) for _ in range(0x54))
        mu.mem_write(RECORD, bytes(rec))
        mu.mem_write(0xE576B8, struct.pack("<I", 4))
        mu.mem_write(TEMPLATES + 2 * 0x54 + 0x0F, b"\0")
        mu.mem_write(STACK, struct.pack("<I", 0x2600F00))
        mu.mem_write(0x2600F00, b"\xf4")
        mu.reg_write(UC_X86_REG_ESI, RECORD)
        mu.reg_write(UC_X86_REG_ESP, STACK)
        for reg, value in ((UC_X86_REG_EAX, 0x1111), (UC_X86_REG_ECX, 0x2222), (UC_X86_REG_EDX, 0x3333)):
            mu.reg_write(reg, value)
        mu.emu_start(ap.SYMBOLS["alien"], 0x2600F00)
        out = bytes(mu.mem_read(RECORD, 0x54))
        self.assertEqual(struct.unpack_from("<H", out, 6)[0], ap.ALIEN_ID)
        d18, d1c, d20 = (struct.unpack_from("<I", out, k)[0] for k in (0x18, 0x1C, 0x20))
        self.assertEqual(d18 & 0xF85, 0, "skin 0, arm variant 0, no Dreads, no eye black")
        self.assertEqual((d1c >> 5) & 0x1FF, 0, "bare hands, no mouthpiece")
        self.assertEqual(d20 & 0xF8000, 0, "no visor, face shape 0")
        self.assertEqual(out[0x0D] & 0x0F, 13, "no hair model")
        self.assertEqual(out[0x0D] >> 4, rec[0x0D] >> 4)
        changed = {k for k in range(0x54) if out[k] != rec[k]}
        self.assertLessEqual(changed, {6, 7, 0x0D, 0x18, 0x19, 0x1C, 0x1D, 0x21, 0x22})
        self.assertEqual((mu.reg_read(UC_X86_REG_EAX), mu.reg_read(UC_X86_REG_ECX), mu.reg_read(UC_X86_REG_EDX)),
                         (0x1111, 0x2222, 0x3333), "the roll keeps every register")


class Gray(unittest.TestCase):
    """The three lookups: the retail texture for everybody, the gray one (found by name) for photo 1947."""
    FIND_STUB = bytes.fromhex("8b442404"   # mov eax,[esp+4]  (the name pointer)
                              "0fb700"     # movzx eax, word [eax]   ('a' of alien_*)
                              "3d61000000"  # cmp eax, 'a'
                              "7507"       # jne miss
                              "b8efbead0b"  # mov eax, 0x0BADBEEF
                              "eb02"
                              "31c0"       # miss: xor eax,eax
                              "c20400")    # ret 4

    @classmethod
    def setUpClass(cls):
        _unicorn()

    def _run(self, entry, photo, setup):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESP
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0x0, 0x1000000)
        mu.mem_map(0x2000000, 0x100000)
        mu.mem_write(ap.CODE_VA, ap.code_bytes())
        mu.mem_write(0x449E0, self.FIND_STUB)
        mu.mem_write(0xB65428, struct.pack("<I", 0x12345678) * 0x200)
        rec = 0x2000100
        mu.mem_write(rec + 6, struct.pack("<H", photo))
        sp = 0x2080000
        mu.mem_write(sp, struct.pack("<I", 0x2000F00))
        mu.mem_write(0x2000F00, b"\xf4")
        mu.reg_write(UC_X86_REG_ESP, sp)
        regs = setup(mu, rec)
        mu.emu_start(entry, 0x2000F00)
        return mu.reg_read(UC_X86_REG_EAX), {r: mu.reg_read(r) for r in regs}, mu.reg_read(UC_X86_REG_ESP) - sp

    def test_lookups(self):
        from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI

        def hand(glove):
            def setup(mu, rec):
                mu.mem_write(0x2010000 - 8, struct.pack("<I", rec))
                mu.reg_write(UC_X86_REG_EBP, 0x2010000)
                mu.reg_write(UC_X86_REG_EDX, 3)
                mu.reg_write(UC_X86_REG_ECX, 0x4444)
                mu.reg_write(UC_X86_REG_ESI, glove)
                return (UC_X86_REG_ECX, UC_X86_REG_ESI)
            return setup

        def arm(mu, rec):
            mu.mem_write(0x2010000 - 4, struct.pack("<I", rec))
            mu.reg_write(UC_X86_REG_EBP, 0x2010000)
            mu.reg_write(UC_X86_REG_ECX, 5)
            return ()

        def neck(mu, rec):
            mu.reg_write(UC_X86_REG_EBX, rec)
            mu.reg_write(UC_X86_REG_EDX, 7)
            mu.reg_write(UC_X86_REG_ECX, 0x5555)
            return (UC_X86_REG_ECX, UC_X86_REG_EBX)

        for photo, want in ((ap.ALIEN_ID, 0x0BADBEEF), (1946, 0x12345678), (0, 0x12345678)):
            eax, regs, esp = self._run(ap.HAND_VA, photo, hand(0))
            self.assertEqual((eax, esp, regs[UC_X86_REG_ECX]), (want, 4, 0x4444))
            eax, _regs, esp = self._run(ap.ARM_VA, photo, arm)
            self.assertEqual((eax, esp), (want, 4))
            eax, regs, esp = self._run(ap.NECK_VA, photo, neck)
            self.assertEqual((eax, esp, regs[UC_X86_REG_ECX]), (want, 4, 0x5555))
        eax, _regs, _esp = self._run(ap.HAND_VA, ap.ALIEN_ID, hand(3))
        self.assertEqual(eax, 0x12345678, "a gloved hand keeps its glove")

    def test_missing_texture_keeps_retail(self):
        from unicorn.x86_const import UC_X86_REG_EBX, UC_X86_REG_EDX

        def neck(mu, rec):
            mu.reg_write(UC_X86_REG_EBX, rec)
            mu.reg_write(UC_X86_REG_EDX, 2)
            return ()
        old = Gray.FIND_STUB
        try:
            Gray.FIND_STUB = bytes.fromhex("31c0c20400")    # a disc without the gray textures: nothing found
            eax, _r, _e = self._run(ap.NECK_VA, ap.ALIEN_ID, neck)
            self.assertEqual(eax, 0x12345678)
        finally:
            Gray.FIND_STUB = old


class Wrapper(unittest.TestCase):
    def test_wrapper_forwards_the_argument_and_rolls_after(self):
        _unicorn()
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EDX
        mu = _machine(test=True, seed=2)
        # a stand-in generator at 0xE6780: [ecx+0x40] = its stack argument, then ret 4
        mu.mem_write(0xE6780, bytes.fromhex("8b44240489414066c741060100c20400"))
        mu.mem_write(0xE576B8, struct.pack("<I", 3))
        sp = STACK
        mu.mem_write(sp, struct.pack("<II", 0x2600F00, 0xA5A5A5A5))
        mu.mem_write(0x2600F00, b"\xf4")
        mu.reg_write(UC_X86_REG_ESP, sp)
        mu.reg_write(UC_X86_REG_ECX, RECORD)
        mu.reg_write(UC_X86_REG_ESI, 0x7777)
        mu.reg_write(UC_X86_REG_EDX, 0x9999)
        mu.emu_start(ap.WRAP_VA, 0x2600F00)
        out = bytes(mu.mem_read(RECORD, 0x54))
        self.assertEqual(struct.unpack_from("<I", out, 0x40)[0], 0xA5A5A5A5)
        self.assertEqual(struct.unpack_from("<H", out, 6)[0], ap.ALIEN_ID, "the roll runs after the generator")
        self.assertEqual(mu.reg_read(UC_X86_REG_ESP), sp + 8, "ret 4, like the generator")
        self.assertEqual(mu.reg_read(UC_X86_REG_ESI), 0x7777)


class Art(unittest.TestCase):
    def test_pins_and_sizes(self):
        self.assertTrue(ap.available())
        for key, size in (("portrait", 128), ("f", 256), ("h", 256), ("n", 256)):
            w, h, rgb = ap.art_rgb(key)
            self.assertEqual((w, h), (size, size))
        pid, rgb = ap.portrait_face()
        self.assertEqual(pid, 1947)
        self.assertLessEqual(len({rgb[i:i + 3] for i in range(0, len(rgb), 3)}), 256)

    def test_gray_palette_is_gray(self):
        import colorsys
        pal = bytes(sum(([b, g, r, 255] for r, g, b in [(230, 180, 150), (200, 150, 120), (160, 110, 90)] * 86), []))[:1024]
        out = ap.gray_palette(pal, bytes([0, 1, 2] * 100))
        for k in range(3):
            b, g, r = out[4 * k:4 * k + 3]
            self.assertLess(colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[1], 0.15, (r, g, b))

    def test_grow_record(self):
        names = [f"f{i:04d}" for i in (2, 7, 9001)]
        hashes = sorted(ap.member_hash(n) for n in names)
        record = bytearray(0x68) + struct.pack(f"<{len(hashes)}I", *hashes) + bytes(20)
        record[:4] = b"CACR"
        struct.pack_into("<II", record, 0x60, len(hashes), 16)
        cdf = b"".join(bytes([k]) * 16 for k in range(3))
        new_rec, new_cdf = ap.grow_record(bytes(record), cdf, {"f1947": b"\xaa" * 16}, ap.CDF_NAME)
        count, slot, new_hashes = ap.parse_record(new_rec)
        self.assertEqual((count, slot), (4, 16))
        i = new_hashes.index(ap.member_hash("f1947"))
        self.assertEqual(new_cdf[i * 16:(i + 1) * 16], b"\xaa" * 16)
        for k, h in enumerate(hashes):
            j = new_hashes.index(h)
            self.assertEqual(new_cdf[j * 16:(j + 1) * 16], bytes([k]) * 16)
        self.assertEqual(new_rec[0x20:0x20 + 22].decode("utf-16-le"), ap.CDF_NAME)


@unittest.skipUnless(RETAIL_XBE, "set NFL2K5_RETAIL_XBE to the retail default.xbe")
class RetailBytes(unittest.TestCase):
    def setUp(self):
        _unicorn()
        self.retail = Path(RETAIL_XBE).read_bytes()

    def test_status_and_apply(self):
        self.assertEqual(ap.xbe_status(self.retail), "retail")
        out, receipt = ap.apply(self.retail)
        self.assertEqual(ap.xbe_status(out), "applied")
        test, _ = ap.apply(self.retail, test=True)
        self.assertEqual(ap.xbe_status(test), "test")
        diff = [i for i, (a, b) in enumerate(zip(self.retail, out)) if a != b]
        spans = [(ap._offset(self.retail, va, len(d)), len(d)) for va, d, _l in ap._spans()]
        headers = {h + k for _va, _raw, _rs, h in ap._section_map(self.retail) for k in range(36, 56)}
        for i in diff:
            self.assertTrue(any(o <= i < o + n for o, n in spans) or i in headers, hex(i))

    def test_coin_loop_is_retail_bit_for_bit(self):
        """The table loop against retail's 17 blocks: same records, same RNG state, real 0x48B50/0x48B90."""
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn.x86_const import UC_X86_REG_ESI, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ESP, UC_X86_REG_ECX
        def machine(patch):
            mu = Uc(UC_ARCH_X86, UC_MODE_32)
            mu.mem_map(0, 0x1600000)
            for va, raw, rsize, _h in ap._section_map(self.retail):
                if va + rsize <= 0x1600000:
                    mu.mem_write(va, self.retail[raw:raw + rsize])
            if patch:
                mu.mem_write(ap.CODE_VA, ap.code_bytes())
            mu.mem_map(0x2000000, 0x100000)
            return mu
        def run(mu, seed):
            r = random.Random(seed)
            for i in range(3):
                mu.mem_write(0x2000000 + i * 0x100, bytes(r.getrandbits(8) for _ in range(0x54)))
            mu.mem_write(0xE5FCA0, struct.pack("<II", r.randrange(55), r.randrange(55))
                         + bytes(r.getrandbits(8) for _ in range(55 * 8)))
            mu.reg_write(UC_X86_REG_ESI, 0x2000000)
            mu.reg_write(UC_X86_REG_EBP, 0x2000100)
            mu.reg_write(UC_X86_REG_EBX, 0x2000200)
            mu.reg_write(UC_X86_REG_ESP, 0x2080000)
            mu.reg_write(UC_X86_REG_ECX, 0xE5FCA0)
            mu.emu_start(ap.CODE_VA, ap.CODE_END, count=200000)
            return bytes(mu.mem_read(0x2000000, 0x300)), bytes(mu.mem_read(0xE5FCA0, 448)), mu.reg_read(UC_X86_REG_ESP)
        a, b = machine(False), machine(True)
        for seed in range(400):
            self.assertEqual(run(a, seed), run(b, seed), seed)


@unittest.skipUnless(RELEASED_ISO and Path(RELEASED_ISO).is_file(), "set NFL2K5_RELEASED_ISO to the v0.6.1 disc image")
class ReleasedDisc(unittest.TestCase):
    def test_plan(self):
        p = ap.plan(RELEASED_ISO)
        count, slot, hashes = ap.parse_record(p["record"])
        self.assertEqual((count, slot), (p["faces_before"] + 1, 43904))
        self.assertIn(ap.member_hash("f1947"), hashes)
        self.assertEqual(len(p["cdf"]), count * slot)
        self.assertEqual(set(ap.template_flags(RELEASED_ISO)), {0})


if __name__ == "__main__":
    unittest.main()
