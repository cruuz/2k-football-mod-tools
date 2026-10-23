"""Franchise practice injuries (nfl2k5_practice_injuries): exact bytes, replay, refusal, presets, late-owner placement,
and the real retail keep-or-heal routine 0x61540 run in Unicorn on retail and patched executables. No game boot.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent).
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_practice_injuries as pi
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

# The cave as installed at 0x14EC5D0 (where the released v0.6.1 executable places it).
CAVE_AT_14EC5D0 = "a1a076e50083f803741285c0740c833d80ffe50002770339c0c385e4c3"


class StaticTests(unittest.TestCase):
    def test_cave_and_hook_bytes(self):
        code = pi.code_for(0x14EC5D0)
        self.assertEqual(len(code), pi.CODE_SIZE)
        self.assertEqual(code.hex(), CAVE_AT_14EC5D0 + "cc" * (pi.CODE_SIZE - len(CAVE_AT_14EC5D0) // 2))
        self.assertEqual(pi.sites(0x14EC5D0), [("practice_injury_keep", 0x61550, bytes.fromhex("e82b36060083f803750f"),
                                                bytes.fromhex("e87bb048017512909090"))])
        # the jne keeps retail's heal target 0x61569 and the call lands on the cave
        after = pi.sites(0x14EC5D0)[0][3]
        self.assertEqual(0x61555 + 2 + after[6], 0x61569)
        self.assertEqual(0x61555 + struct.unpack_from("<i", after, 1)[0], 0x14EC5D0)

    def test_presets_options_and_late_owner_order(self):
        # b778-int2: fa1's star retention and xs1's module loader follow this owner; the loader stays last.
        self.assertEqual(space.LATE_OWNERS[-13:], (pi.OWNER, "nfl2k5_ball_carrier_ai", "nfl2k5_star_retention", "nfl2k5_star_career", "nfl2k5_cpu_money_downs_late", "nfl2k5_cpu_money_downs_late_state", "nfl2k5_draft_clock", "nfl2k5_weekly_progression", "nfl2k5_player_progress_screen", "nfl2k5_contract_college_guard", "nfl2k5_sim_cb_tackles", "nfl2k5_clock_led", "nfl2k5_module_loader"))
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).practice_injuries, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["practice_injuries"], preset["franchise_practice"], name)
            self.assertIs(preset["practice_injuries"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        self.assertIn("practice_injuries", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_practice_injuries", "Franchise practice injuries"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        text = (ROOT / "mod_editor/core/nfl2k5_practice_injuries.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", pi.HELP_TEXT + pi.BUILD_CAPTION)


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = pi.apply(cls.retail)

    def test_site_code_and_receipt(self):
        self.assertEqual(pi.status(self.retail), "retail")
        self.assertEqual(pi.status(self.final), "applied")
        image = XbeImage(self.final)
        code = pi.allocation(self.final)["va"]
        self.assertEqual(image.read(code, pi.CODE_SIZE), pi.code_for(code))
        raw = image.read(0x61550, 10)
        self.assertEqual(raw[0], 0xE8)
        self.assertEqual(0x61555 + struct.unpack_from("<i", raw, 1)[0], code)
        self.assertEqual(raw[5:], bytes.fromhex("7512909090"))
        self.assertIs(self.receipt["roster_written"], False)
        self.assertEqual(space.status(self.final), "applied")

    def test_only_the_hook_changes_in_retail_sections(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        changed = []
        for s in a.sections:
            if s.raw_size:
                x, y = a.read(s.start, s.raw_size), b.read(s.start, s.raw_size)
                changed += [s.start + i for i in range(len(x)) if x[i] != y[i]]
        self.assertTrue(changed)
        self.assertTrue(all(0x61551 <= va < 0x6155A for va in changed), [hex(v) for v in changed])

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = pi.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = pi.allocation(self.final)["va"]
        for label, (va, content) in {"hook": (0x61550, b"\xe9\x00\x00\x00\x00"),
                                     "nop": (0x61558, b"\xcc"),
                                     "code": (code + 3, b"\x90"),
                                     "bit 31 test": (0x6155D, b"\x90"),
                                     "heal": (0xE6689, b"\x90"),
                                     "league getter": (0xC4B80, b"\x90"),
                                     "slot eligibility": (0x188468, b"\x90")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(pi.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                pi.apply(bad)
        retail_bad = repin_edit(self.retail, 0x61558, b"\x90")
        self.assertEqual(pi.status(retail_bad), "foreign")
        with self.assertRaises(ValueError):
            pi.apply(retail_bad)


@unittest.skipIf(uc is None, "unicorn is not installed")
class DecisionTests(unittest.TestCase):
    """The real keep-or-heal routine 0x61540 (called for every match copy by 0x61845 / 0x61875, ESI = the copy):
    it either returns at 0x61570 with the copy untouched (injury kept) or tail-jumps into the heal 0xE6680."""
    COPY, STACK, RETURN = 0x3000000, 0x3100000, 0x3200000
    HEAL = 0xE6680
    INJURED = 0xC0C83C71       # Carnell Tate in MyNFL3: injured, 3 weeks out (+0x20)
    STATUS_OUT = 0x44360293    # status 4 = out (+0x24)

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, _ = pi.apply(cls.retail)

    def decide(self, payload, *, mode, league, word20=INJURED):
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        pages = sorted({va for s in image.sections for va in range(s.start & -4096, (s.start + s.size + 4095) & -4096, 4096)})
        start = prev = None
        for va in pages + [None]:
            if va is not None and prev is not None and va == prev + 4096:
                prev = va
                continue
            if start is not None:
                m.mem_map(start, prev + 4096 - start)
            start = prev = va
        for s in image.sections:
            if s.raw_size:
                m.mem_write(s.start, image.read(s.start, s.raw_size))
        for base in (self.COPY, self.STACK, self.RETURN):
            m.mem_map(base, 0x10000)
        put = lambda va, v: m.mem_write(va, struct.pack("<I", v))
        put(self.COPY + 0x20, word20)
        put(self.COPY + 0x24, self.STATUS_OUT)
        put(0xE5FF80, mode)
        put(0xE576A0, league)
        esp = self.STACK + 0x8000
        put(esp, self.RETURN)
        m.reg_write(x86.UC_X86_REG_ESI, self.COPY)
        m.reg_write(x86.UC_X86_REG_ESP, esp)
        m.reg_write(x86.UC_X86_REG_EBX, 0xEFFFFFFF)
        m.reg_write(x86.UC_X86_REG_EDI, 7)
        seen = []
        m.hook_add(uc.UC_HOOK_CODE, lambda u, address, size, _: (seen.append(address),
                   u.emu_stop() if address in (self.HEAL, self.RETURN) else None))
        m.emu_start(0x61540, 0, count=100)
        self.assertIn(seen[-1], (self.HEAL, self.RETURN))
        self.assertEqual(m.reg_read(x86.UC_X86_REG_ESI), self.COPY)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EBX), 0xEFFFFFFF)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EDI), 7)
        if seen[-1] == self.HEAL:
            self.assertEqual(m.reg_read(x86.UC_X86_REG_ECX), self.COPY)
            return "heal"
        return "keep"

    def test_retail_heals_franchise_practice(self):
        # the reported bug: Coach's Desk Practice (mode 1) with a franchise loaded (league type 2) heals the copy
        for mode in (0, 1, 2):
            self.assertEqual(self.decide(self.retail, mode=mode, league=2), "heal", mode)
        for mode in (5, 6, 7):
            self.assertEqual(self.decide(self.retail, mode=mode, league=2), "keep", mode)

    def test_patched_keeps_injuries_in_franchise_practice(self):
        for league in (1, 2, 3):
            for mode in (0, 1, 2):
                self.assertEqual(self.decide(self.final, mode=mode, league=league), "keep", (mode, league))

    def test_patched_is_retail_everywhere_else(self):
        for mode in range(0, 10):
            for league in (0, 1, 2, 3):
                for word in (self.INJURED, 0x40083C71):
                    if mode <= 2 and league and word == self.INJURED:
                        continue
                    self.assertEqual(self.decide(self.final, mode=mode, league=league, word20=word),
                                     self.decide(self.retail, mode=mode, league=league, word20=word), (mode, league, word))
        # main-menu practice with no franchise loaded still heals
        self.assertEqual(self.decide(self.final, mode=1, league=0), "heal")
        # a healthy player is never "kept" by the new case (retail clears his fields, as before)
        self.assertEqual(self.decide(self.final, mode=1, league=2, word20=0x40083C71), "heal")


if __name__ == "__main__":
    unittest.main()
