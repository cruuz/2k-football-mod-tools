"""Modern sideline catches (nfl2k5_force_out): exact bytes, replay, refusal, presets, late-owner placement, and the
real retail boundary decision 0x157995..0x1579BE run in Unicorn on the patched executable. No game boot.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent).
"""
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_force_out as fo
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

# The cave as installed at 0x14EC5D0 (where the released v0.6.1 executable places it), then at 0x14DA000 (retail).
CAVE_AT_14EC5D0 = ("8b916801000085d27430833d80ffe500087525833d4c01e60000751c8b155818bf0083fa3373110fa31528c64e01"
                   "73088b9168010000eb0231d2e992b3c6fe")
OLD_RULE_ROWS = list(range(1, 28)) + [32, 33, 34]


class StaticTests(unittest.TestCase):
    def test_cave_bytes(self):
        code = fo.code_for(0x14EC5D0)
        self.assertEqual(len(code), fo.CODE_SIZE)
        self.assertEqual(code[:len(CAVE_AT_14EC5D0) // 2].hex(), CAVE_AT_14EC5D0)
        self.assertEqual(code[len(CAVE_AT_14EC5D0) // 2:fo.MASK_OFFSET], b"\xcc" * (fo.MASK_OFFSET - len(CAVE_AT_14EC5D0) // 2))
        self.assertEqual(struct.unpack("<Q", code[fo.MASK_OFFSET:])[0], 0x387FFFFFF)
        # the resume jump lands on the retail "test edx, edx" right after the six displaced bytes
        at = len(CAVE_AT_14EC5D0) // 2 - 5
        self.assertEqual(0x14EC5D0 + at + 5 + struct.unpack_from("<i", code, at + 1)[0], fo.HOOK[1] + 6)
        self.assertEqual(fo.sites(0x14EC5D0), [("force_out_credit", 0x15799B, bytes.fromhex("8b9168010000"),
                                                bytes.fromhex("e9304c390190"))])

    def test_season_rows_come_from_the_moment_catalog(self):
        self.assertEqual(fo.old_rule_rows(), OLD_RULE_ROWS)
        doc = json.loads((ROOT / "data/nfl2k5_espn25_fields.json").read_text(encoding="utf-8"))
        seasons = {m["row"]: m["season"] for m in doc["moments"]}
        self.assertEqual(seasons[27], 2007)      # the last force-out season keeps the rule
        self.assertEqual(seasons[28], 2008)      # the first season without it
        self.assertTrue(all(seasons[r] < 2008 for r in OLD_RULE_ROWS))
        self.assertTrue(all(seasons[r] >= 2008 for r in set(seasons) - set(OLD_RULE_ROWS)))

    def test_presets_options_and_late_owner_order(self):
        self.assertEqual(space.LATE_OWNERS[-10:], (fo.OWNER, "nfl2k5_practice_injuries", "nfl2k5_ball_carrier_ai", "nfl2k5_star_retention", "nfl2k5_star_career", "nfl2k5_cpu_money_downs_late", "nfl2k5_cpu_money_downs_late_state", "nfl2k5_draft_clock", "nfl2k5_weekly_progression", "nfl2k5_module_loader"))  # b778-xs1: the module loader is last
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).modern_force_out, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["modern_force_out"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        self.assertIn("modern_force_out", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_force_out", "Modern sideline catches"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        text = (ROOT / "mod_editor/core/nfl2k5_force_out.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", fo.HELP_TEXT + fo.BUILD_CAPTION)


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = fo.apply(cls.retail)

    def test_site_code_and_receipt(self):
        self.assertEqual(fo.status(self.retail), "retail")
        self.assertEqual(fo.status(self.final), "applied")
        image = XbeImage(self.final)
        code = fo.allocation(self.final)["va"]
        self.assertEqual(image.read(code, fo.CODE_SIZE), fo.code_for(code))
        raw = image.read(0x15799B, 6)
        self.assertEqual(raw[0], 0xE9)
        self.assertEqual(0x15799B + 5 + struct.unpack_from("<i", raw, 1)[0], code)
        self.assertEqual(raw[5:], b"\x90")
        self.assertEqual(self.receipt["runtime_witnessed"], False)
        self.assertEqual(self.receipt["old_rule_rows"], OLD_RULE_ROWS)
        self.assertEqual(fo.read_settings(self.final), {"status": "applied", "old_rule_rows": OLD_RULE_ROWS})
        self.assertEqual(space.status(self.final), "applied")

    def test_only_the_hook_changes_in_retail_sections(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        changed = []
        for s in a.sections:
            if s.raw_size:
                x, y = a.read(s.start, s.raw_size), b.read(s.start, s.raw_size)
                changed += [s.start + i for i in range(len(x)) if x[i] != y[i]]
        self.assertEqual(changed, list(range(0x15799B, 0x1579A1)))

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = fo.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = fo.allocation(self.final)["va"]
        for label, (va, content) in {"hook": (0x15799B, b"\xe9\x00\x00\x00\x00"),
                                     "nop": (0x1579A0, b"\xcc"),
                                     "code": (code + 3, b"\x90"),
                                     "mask": (code + fo.MASK_OFFSET + 5, b"\xff"),
                                     "contact test": (0x1579AF, b"\x83\xf8\x1d"),
                                     "two-feet test": (0x236720, b"\x90"),
                                     "credit at the catch": (0xB7894, b"\x90"),
                                     "foot counter": (0x158A96, b"\x90")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(fo.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                fo.apply(bad)
        retail_bad = repin_edit(self.retail, 0x1579A0, b"\x90")
        self.assertEqual(fo.status(retail_bad), "foreign")
        with self.assertRaises(ValueError):
            fo.apply(retail_bad)


@unittest.skipIf(uc is None, "unicorn is not installed")
class DecisionTests(unittest.TestCase):
    """The real boundary handler from 0x157995 (credit read) to its two outcomes: 0x157A23 (catch completed, the
    force-out catch) or 0x1579BE (the two-feet test). EDI = 3: a grounded body point of the holder is out of bounds
    while the catch is in progress."""
    HOLDER, ANIM, REC, STATE = 0x3000000, 0x3000100, 0x3000200, 0x3000400
    STACK = 0x3100000
    CATCH, FEET = 0x157A23, 0x1579BE

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, _ = fo.apply(cls.retail)

    def run_decision(self, payload, *, credit=1, category=0x1C, mode=0, situation=0, row=0):
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
        m.mem_map(0x3000000, 0x10000)
        m.mem_map(self.STACK, 0x10000)
        put = lambda va, v: m.mem_write(va, struct.pack("<I", v))
        put(self.HOLDER + 0x10, self.ANIM)
        put(self.ANIM + 4, self.REC)
        m.mem_write(self.REC + 3, bytes([category]))
        put(0xE602EC, self.STATE)
        put(self.STATE + 0x168, credit)
        put(0xE5FF80, mode)
        put(0xE6014C, situation)
        put(0xBF1858, row)
        m.reg_write(x86.UC_X86_REG_ESI, self.HOLDER)
        m.reg_write(x86.UC_X86_REG_EDI, 3)
        m.reg_write(x86.UC_X86_REG_ESP, self.STACK + 0x8000)
        seen = []
        m.hook_add(uc.UC_HOOK_CODE, lambda u, address, size, _: (seen.append(address),
                   u.emu_stop() if address in (self.CATCH, self.FEET) else None))
        m.emu_start(0x157995, 0, count=200)
        self.assertIn(seen[-1], (self.CATCH, self.FEET))
        self.assertEqual(m.reg_read(x86.UC_X86_REG_ESI), self.HOLDER)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EDI), 3)
        return "catch" if seen[-1] == self.CATCH else "two_feet"

    def test_retail_credits_the_force_out_catch(self):
        self.assertEqual(self.run_decision(self.retail), "catch")              # the reported ruling
        self.assertEqual(self.run_decision(self.retail, category=0x05), "two_feet")
        self.assertEqual(self.run_decision(self.retail, credit=0), "two_feet")

    def test_modern_games_drop_the_credit(self):
        for category in (0x1C, 0x1A, 0x0A):
            self.assertEqual(self.run_decision(self.final, category=category), "two_feet")
        self.assertEqual(self.run_decision(self.final, credit=0), "two_feet")

    def test_anniversary_moments_by_season(self):
        for row in range(51):
            want = "catch" if row + 1 in OLD_RULE_ROWS else "two_feet"
            self.assertEqual(self.run_decision(self.final, mode=8, row=row), want, row + 1)
            self.assertEqual(self.run_decision(self.final, mode=8, row=row, category=0x05), "two_feet", row + 1)
            self.assertEqual(self.run_decision(self.final, mode=8, row=row, credit=0), "two_feet", row + 1)
        self.assertEqual(self.run_decision(self.final, mode=8, row=9, situation=1), "two_feet")   # Situation mode
        self.assertEqual(self.run_decision(self.final, mode=8, row=51), "two_feet")
        self.assertEqual(self.run_decision(self.final, mode=8, row=0xFFFFFFFF), "two_feet")
        self.assertEqual(self.run_decision(self.final, mode=7, row=9), "two_feet")


if __name__ == "__main__":
    unittest.main()
