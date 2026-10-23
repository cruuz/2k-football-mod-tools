"""b778-ee1/ee2 alien prospect: the in-place code under Unicorn (the roll, once per franchise, the rate over 100
seasons, the five lookups, the wrapper), the executable spans, the art pins, the released disc textures; with
NFL2K5_RETAIL_XBE, the rewritten coin blocks against retail's own bytes; with NFL2K5_RELEASED_ISO, the image plan
on the released disc."""
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

    def test_length_hook_is_not_applied(self):
        """ee2 follow-up: the 0x93850 hook is built but disabled (it hangs the practice loader)."""
        spans = {va for va, _d, _l in ap._spans()}
        self.assertNotIn(ap.SKEL_SITE, spans)
        self.assertIn(ap.GIRTH_SITE, spans)
        self.assertIn(ap.GIRTH_NOP_SITE, spans)

    def test_odds(self):
        self.assertAlmostEqual(ap.per_class_probability(), 1 / 150, delta=2e-5)
        hundred = 1 - (1 - ap.per_class_probability()) ** 99    # the first class never rolls
        self.assertTrue(0.47 < hundred < 0.50, hundred)

    def test_spans_are_relative_calls(self):
        sites = (ap.CALL_SITE, ap.HAND_SITE, ap.ARM_SITE, ap.NECK_SITE, ap.SF_SITE, ap.SIDE_SITE,
                 ap.GIRTH_SITE)
        targets = (ap.WRAP_VA, ap.HAND_VA, ap.ARM_VA, ap.NECK_VA, ap.SF_VA, ap.SIDE_VA,
                   ap.GIRTH_VA)
        for va, data, _label in ap._spans():
            if va in sites:
                self.assertEqual(data[0], 0xE8)
                target = va + 5 + struct.unpack_from("<i", data, 1)[0]
                self.assertIn(target, targets)
                self.assertTrue(all(b == 0x90 for b in data[5:]))
            if va == ap.GIRTH_NOP_SITE:
                self.assertEqual(data, b"\x90\x90")
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
        self.assertEqual(d18 & 0x18, 0, "body type 0 (the thinnest weight profile)")
        self.assertEqual((d1c >> 5) & 0x1FF, 0, "bare hands, no mouthpiece")
        self.assertEqual(d20 & 0xF8000, 0, "no visor, face shape 0")
        self.assertEqual(out[0x0D] & 0x0F, 13, "no hair model")
        self.assertEqual(out[0x0D] >> 4, rec[0x0D] >> 4)
        self.assertEqual(out[0x2B], ap.HEIGHT_INCHES, "7'11\"")
        self.assertEqual(out[0x2B], 95)
        self.assertEqual(out[0x2A], ap.WEIGHT_RAW, "150 lb is weight raw 0 (the record's floor)")
        self.assertEqual(ap.WEIGHT_LB, 150)
        changed = {k for k in range(0x54) if out[k] != rec[k]}
        self.assertLessEqual(changed, {6, 7, 0x0D, 0x18, 0x19, 0x1C, 0x1D, 0x21, 0x22, 0x2A, 0x2B})
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
        mu.mem_write(0xBA8280, struct.pack("<I", 0x87654321) * 0x200)
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
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EDI, UC_X86_REG_ESI

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

        def sf(mu, rec):
            mu.reg_write(UC_X86_REG_EBX, rec)
            mu.reg_write(UC_X86_REG_EAX, 3)
            return (UC_X86_REG_ECX, UC_X86_REG_EBX)

        def side(mu, rec):
            mu.reg_write(UC_X86_REG_EDI, rec)
            mu.reg_write(UC_X86_REG_EAX, 3)
            return (UC_X86_REG_EDI,)

        for photo, want in ((ap.ALIEN_ID, 0x0BADBEEF), (1946, 0x12345678), (0, 0x12345678)):
            eax, regs, esp = self._run(ap.HAND_VA, photo, hand(0))
            self.assertEqual((eax, esp, regs[UC_X86_REG_ECX]), (want, 4, 0x4444))
            eax, _regs, esp = self._run(ap.ARM_VA, photo, arm)
            self.assertEqual((eax, esp), (want, 4))
            eax, regs, esp = self._run(ap.NECK_VA, photo, neck)
            self.assertEqual((eax, esp, regs[UC_X86_REG_ECX]), (want, 4, 0x5555))
            _eax, regs, esp = self._run(ap.SF_VA, photo, sf)
            self.assertEqual((regs[UC_X86_REG_ECX], esp, regs[UC_X86_REG_EBX]), (want, 4, 0x2000100))
            eax, regs, esp = self._run(ap.SIDE_VA, photo, side)
            want_side = 0x0BADBEEF if photo == ap.ALIEN_ID else 0x87654321
            self.assertEqual((eax, esp, regs[UC_X86_REG_EDI]), (want_side, 4, 0x2000100))
        _eax, regs, _esp = self._run(ap.SF_VA, ap.ALIEN_ID, sf)
        self.assertEqual(regs[UC_X86_REG_ECX], 0x0BADBEEF)
        eax, regs, _esp = self._run(ap.SIDE_VA, ap.ALIEN_ID, side)
        self.assertEqual(eax, 0x0BADBEEF)
        eax, _regs, _esp = self._run(ap.HAND_VA, ap.ALIEN_ID, hand(3))
        self.assertEqual(eax, 0x12345678, "a gloved hand keeps its glove")

    def test_missing_texture_keeps_retail(self):
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EDX

        def neck(mu, rec):
            mu.reg_write(UC_X86_REG_EBX, rec)
            mu.reg_write(UC_X86_REG_EDX, 2)
            return ()

        def sf(mu, rec):
            mu.reg_write(UC_X86_REG_EBX, rec)
            mu.reg_write(UC_X86_REG_EAX, 3)
            return (UC_X86_REG_ECX,)

        def side(mu, rec):
            mu.reg_write(UC_X86_REG_EDI, rec)
            mu.reg_write(UC_X86_REG_EAX, 3)
            return ()
        old = Gray.FIND_STUB
        try:
            Gray.FIND_STUB = bytes.fromhex("31c0c20400")    # a disc without the gray textures: nothing found
            eax, _r, _e = self._run(ap.NECK_VA, ap.ALIEN_ID, neck)
            self.assertEqual(eax, 0x12345678)
            _eax, regs, _e = self._run(ap.SF_VA, ap.ALIEN_ID, sf)
            self.assertEqual(regs[UC_X86_REG_ECX], 0x12345678)
            eax, _r, _e = self._run(ap.SIDE_VA, ap.ALIEN_ID, side)
            self.assertEqual(eax, 0x87654321)
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


class Size(unittest.TestCase):
    def test_height_and_weight_are_the_game_s_own_limits(self):
        self.assertEqual(ap.HEIGHT_INCHES, 95)
        self.assertEqual((ap.HEIGHT_INCHES // 12, ap.HEIGHT_INCHES % 12), (7, 11), "the card prints 7'11\"")
        self.assertEqual(ap.WEIGHT_RAW, 0)
        self.assertEqual(ap.WEIGHT_LB, 150, "weight_raw is pounds - 150 in an unsigned byte: 150 lb is the floor")
        self.assertEqual(ap.BODY_TYPE, 0, "profile 0 is the thinnest weight profile")



SCHEDULE = (0, 1, 2, 3, 4, 1, 2, 1, 1, 1, 1, 1, 1, 5, 6, 7, 8, 5, 6, 5, 5, 5, 5, 5, 5, 0,
            9, 10, 11, 12, 13, 14, 15, 15, 15, 15, 15, 17, 14, 14, 15, 14, 15, 14, 18, 19, 20, 20,
            20, 20, 20, 22, 19, 19, 20, 20, 19, 19, 23, 24, 5, 1)
LOW_CHAIN = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 2, 2, 2, 2, 0, 0)
PIVOTS = (14, 19)
FACTORS = (1.16, 1.16)


class Lanky(unittest.TestCase):
    """ee2 follow-up: the 0x93850 entry hook (arms + shorter torso) and the 0x93859 weight hook, under Unicorn."""

    LOW, HIGH, RECORD, STACK, EXIT = 0x2100000, 0x2100000 + 0x640, 0x2200000, 0x2210000, 0x93856

    @classmethod
    def setUpClass(cls):
        _unicorn()

    def _machine(self):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0, 0x1600000)
        mu.mem_map(0x2000000, 0x300000)
        mu.mem_write(ap.CODE_VA, ap.code_bytes())
        mu.mem_write(ap.SCHED if hasattr(ap, "SCHED") else 0x4EF898, bytes(SCHEDULE))
        mu.mem_write(self.EXIT, b"\xf4")                 # the hook's jmp to retail becomes HLT for the test
        # one 4x4 matrix per bone: translation at +0x30..+0x3c
        for base, count, start in ((self.LOW, 25, 0), (self.HIGH, 62, 1000)):
            for i in range(count):
                at = base + i * 64
                mu.mem_write(at, bytes(64))
                mu.mem_write(at + 0x30, struct.pack("<4f", 100 + start + i, 200 + start + i, 300 + start + i, 1.0))
        for i, (x, y) in ((14, (10, 50)), (15, (20, 50)), (16, (30, 50)), (17, (40, 50)),
                          (19, (10, 60)), (20, (20, 60)), (21, (30, 60)), (22, (40, 60))):
            mu.mem_write(self.LOW + i * 64 + 0x30, struct.pack("<4f", x, y, 0.0, 1.0))
        # high arm bones start at their low joint positions
        for j, low_i in ((32, 15), (37, 17), (46, 20), (51, 22)):
            mu.mem_write(self.HIGH + j * 64 + 0x30, bytes(mu.mem_read(self.LOW + low_i * 64 + 0x30, 16)))
        mu.mem_write(self.RECORD, self._record())
        return mu

    def _record(self, photo=ap.ALIEN_ID, height=ap.HEIGHT_INCHES):
        rec = bytearray(0x54)
        struct.pack_into("<H", rec, 6, photo)
        rec[0x2A], rec[0x2B] = ap.WEIGHT_RAW, height
        return bytes(rec)

    def _run_skel(self, mu):
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP
        mu.mem_write(self.STACK, struct.pack("<II", self.EXIT, self.LOW))
        mu.reg_write(UC_X86_REG_ECX, self.RECORD)
        mu.reg_write(UC_X86_REG_EDX, 0x1FFFFFF)
        mu.reg_write(UC_X86_REG_ESP, self.STACK)
        mu.emu_start(ap.SKEL_VA, self.EXIT, count=200000)
        return mu

    def _translation(self, mu, base, index):
        return struct.unpack("<4f", bytes(mu.mem_read(base + index * 64 + 0x30, 16)))

    def _expected(self):
        low = [[100 + i, 200 + i, 300 + i] for i in range(25)]
        for i, (x, y) in ((14, (10, 50)), (15, (20, 50)), (16, (30, 50)), (17, (40, 50)),
                          (19, (10, 60)), (20, (20, 60)), (21, (30, 60)), (22, (40, 60))):
            low[i] = [x, y, 0.0]
        for i in range(10, 25):
            low[i][1] -= ap.SPINE_DROP
        for i in range(1, 25):
            chain = LOW_CHAIN[i]
            if chain:
                p = low[PIVOTS[chain - 1]]
                f = FACTORS[chain - 1]
                low[i] = [p[k] + f * (low[i][k] - p[k]) for k in range(3)]
        high = [[1100 + j, 1200 + j, 1300 + j] for j in range(62)]
        for j, point in ((32, [20, 50, 0]), (37, [40, 50, 0]), (46, [20, 60, 0]), (51, [40, 60, 0])):
            high[j] = list(point)
        for j in range(27, 60):
            high[j][1] -= ap.SPINE_DROP
        for j in range(62):
            chain = LOW_CHAIN[SCHEDULE[j]]
            if chain:
                p = low[PIVOTS[chain - 1]]
                f = FACTORS[chain - 1]
                high[j] = [p[k] + f * (high[j][k] - p[k]) for k in range(3)]
        return low, high

    def test_arm_chains_and_spine(self):
        mu = self._run_skel(self._machine())
        low, high = self._expected()
        for i in range(25):
            for got, want in zip(self._translation(mu, self.LOW, i)[:3], low[i]):
                self.assertAlmostEqual(got, want, places=3, msg=i)
        for j in range(62):
            for got, want in zip(self._translation(mu, self.HIGH, j)[:3], high[j]):
                self.assertAlmostEqual(got, want, places=3, msg=j)

    def test_other_players_are_untouched(self):
        for photo, height in ((1946, 95), (0, 95), (0, 0)):
            mu = self._machine()
            mu.mem_write(self.RECORD, self._record(photo, height))
            before = {base: [self._translation(mu, base, i) for i in range(count)]
                      for base, count in ((self.LOW, 25), (self.HIGH, 62))}
            self._run_skel(mu)
            for base, count in ((self.LOW, 25), (self.HIGH, 62)):
                for i in range(count):
                    self.assertEqual(self._translation(mu, base, i), before[base][i], (photo, height, base, i))

    def test_weight_hook(self):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP
        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0, 0x1600000)
        mu.mem_map(0x2000000, 0x400000)
        mu.mem_write(ap.CODE_VA, ap.code_bytes())
        mu.mem_write(0x2300000, b"\xf4")
        for photo, height, want in ((ap.ALIEN_ID, 95, ap.VISUAL_WEIGHT), (1946, 95, 150), (ap.ALIEN_ID, 96, ap.VISUAL_WEIGHT)):
            mu.mem_write(0x2200000, self._record(photo, height))
            mu.mem_write(0x2210000, struct.pack("<I", 0x2300000))
            mu.reg_write(UC_X86_REG_ECX, 0x2200000)
            mu.reg_write(UC_X86_REG_ESP, 0x2210000)
            mu.emu_start(ap.GIRTH_VA, 0x2300000)
            self.assertEqual(mu.reg_read(UC_X86_REG_EAX), want, (photo, height))

    def test_constants_are_in_the_code(self):
        self.assertIn(struct.pack("<f", ap.ARM_SCALE) * 2, ap.CODE)
        self.assertIn(struct.pack("<f", ap.SPINE_DROP), ap.CODE)
        self.assertIn(b"\xb8" + struct.pack("<I", ap.VISUAL_WEIGHT), ap.CODE)


@unittest.skipUnless(RELEASED_ISO and Path(RELEASED_ISO).is_file(), "set NFL2K5_RELEASED_ISO to the v0.6.1 disc image")
class Textures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_music_archive as archive, nfl2k5_hair_styles as hair
        with archive.Disc(RELEASED_ISO, descriptors=()) as disc:
            cls.outer3 = hair._outer3(disc)[1]

    def _texture(self, data, name):
        from tools import nfl_txtr as tx
        for c in tx.parse_chunks(data, allow_trailing=True):
            if c.kind != "TXTR" or c.compressed:
                continue
            decoded, _ = tx.decode_chunk(data, c)
            t = tx.parse_texture(decoded, c)
            if t.name == name:
                return t
        self.fail(f"no {name}")

    def test_five_gray_textures(self):
        out, receipt = ap.gray_collection(self.outer3)
        want = ["alien_arm", "alien_hand", "alien_neck", ap.SF_TEXTURE, ap.SIDE_TEXTURE]
        self.assertEqual([t["name"] for t in receipt["textures"]], want)
        self.assertEqual(ap.gray_status(out), "applied")
        self.assertEqual(self._texture(out, ap.SF_TEXTURE).width, 32)
        self.assertEqual(self._texture(out, ap.SF_TEXTURE).height, 32)
        self.assertEqual(self._texture(out, ap.SIDE_TEXTURE).width, 128)
        self.assertEqual(self._texture(out, ap.SIDE_TEXTURE).height, 128)
        self.assertEqual(self._texture(out, ap.SIDE_TEXTURE).mip_levels, 5)
        for name in want:
            self.assertEqual(self._texture(out, name).format_name, "P8")

    def test_far_face_is_the_alien_portrait(self):
        from tools import nfl_txtr as tx
        raw = ap.portrait_sf_texture(self.outer3)
        c = tx.parse_chunks(raw)[0]
        decoded, _ = tx.decode_chunk(raw, c)
        t = tx.parse_texture(decoded, c)
        self.assertEqual((t.name, t.width, t.height, t.mip_levels, t.format_name),
                         (ap.SF_TEXTURE, 32, 32, 1, "P8"))
        rgba = tx.texture_to_rgba(decoded, c, t)
        # the portrait's eyes are black holes in a gray face: the darkest texel is much darker than the face
        lum = [0.2126 * rgba[i] + 0.7152 * rgba[i + 1] + 0.0722 * rgba[i + 2]
               for i in range(0, len(rgba), 4) if rgba[i + 3]]
        self.assertLess(min(lum), 40)
        self.assertGreater(sorted(lum)[len(lum) // 2], 70)


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


    def test_lanky_sites_are_retail(self):
        for va, want in ((ap.SKEL_SITE, ap.SKEL_RETAIL), (ap.GIRTH_SITE, ap.GIRTH_RETAIL),
                         (ap.GIRTH_NOP_SITE, ap.GIRTH_NOP_RETAIL)):
            at = ap._offset(self.retail, va, len(want))
            self.assertEqual(self.retail[at:at + len(want)], want, hex(va))

    def test_height_scale_and_weight_profile_do_not_crash(self):
        """Run the real 0x918B0 (height -> model scale) on the retail XBE at 7'11", and check the real 0x93850
        profile table the weight/body fields select: the values are in range and every scale is finite."""
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP

        mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(0, 0x1600000)
        for va, raw, rsize, _h in ap._section_map(self.retail):
            mu.mem_write(va, self.retail[raw:raw + rsize])
        mu.mem_map(0x2000000, 0x2000000)
        mu.mem_write(0x2100000, bytes(0x54))
        mu.mem_write(0x2100000 + 0x2B, bytes([ap.HEIGHT_INCHES]))
        # a tiny fstp stub stores the x87 return (ST0) at 0x2600000; HLT ends the run
        mu.mem_write(0x2500000, bytes.fromhex("d91d00006002f4"))
        mu.mem_write(0x2300000, struct.pack("<I", 0x2500000))
        mu.reg_write(UC_X86_REG_ESP, 0x2300000)
        mu.reg_write(UC_X86_REG_ECX, 0x2100000)
        mu.emu_start(0x918B0, 0x2500000)
        mu.emu_start(0x2500000, 0x2500007)
        value = struct.unpack("<f", bytes(mu.mem_read(0x2600000, 4)))[0]
        self.assertAlmostEqual(value, 95 * 0.012927484698593616, places=4)
        self.assertAlmostEqual(value, 1.228111, places=4)

        # 0x93850 reads these exact tables; 150 lb clamps to 150 and profile 0 is the thinnest of the four
        for body in range(4):
            for weight in (ap.WEIGHT_RAW, 255):
                doc = struct.unpack_from("<52f", self.retail, ap._offset(self.retail, 0x4EF018 + body * 0xD0, 208))
                scalar = min(450.0, max(150.0, weight + 150.0))
                t = (scalar - doc[0]) * doc[1]
                scales = [doc[2 + 2 * i] + (doc[3 + 2 * i] - doc[2 + 2 * i]) * t for i in range(25)]
                self.assertTrue(all(abs(v) < 10 for v in scales), (body, weight))
        doc0 = struct.unpack_from("<52f", self.retail, ap._offset(self.retail, 0x4EF018, 208))
        t0 = (150.0 - doc0[0]) * doc0[1]
        self.assertLess(sum(doc0[2 + 2 * i] + (doc0[3 + 2 * i] - doc0[2 + 2 * i]) * t0 for i in range(25)),
                        sum(doc0[2 + 2 * i] for i in range(25)), "150 lb profile 0 is thinner than its reference")

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
