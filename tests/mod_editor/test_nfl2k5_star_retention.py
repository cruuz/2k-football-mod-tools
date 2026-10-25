"""CPU clubs keep their stars (nfl2k5_star_retention): exact bytes, replay, refusal, presets, late-owner placement,
and the game's own stage-6 offseason advance (0x247D40 -> 0x2BFAF0) run in Unicorn. No game boot.

The pinned USA retail default.xbe and roster are read from NFL2K5_RETAIL_EXTRACTION (skipped when absent).
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core import nfl2k5_star_retention as sr
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_roster

# The cave as installed at 0x14EC5D0 (the first free late-owner slot of the released v0.6.1 executable).
CAVE_AT_14EC5D0 = ("5152ba01000000e8a4a7d5fe5a5952ba08c64e01807935007505ba0cc64e01d81adfe05af6c4417508b8ffff0000"
                   "c20c00e93a0eddfe")


class StaticTests(unittest.TestCase):
    def test_cave_bytes(self):
        code = sr.code_for(0x14EC5D0)
        self.assertEqual(len(code), sr.CODE_SIZE)
        body = len(CAVE_AT_14EC5D0) // 2
        self.assertEqual(code[:body].hex(), CAVE_AT_14EC5D0)
        self.assertEqual(code[body:sr.DATA_OFFSET], b"\xcc" * (sr.DATA_OFFSET - body))
        self.assertEqual(struct.unpack("<ff", code[sr.DATA_OFFSET:]), (struct.unpack("<f", struct.pack("<f", 0.85))[0],
                                                                     struct.unpack("<f", struct.pack("<f", 0.75))[0]))
        self.assertEqual(0x14EC5D0 + body + struct.unpack_from("<i", code, body - 4)[0], sr.VALUE)  # tail jump
        self.assertEqual(sr.sites(0x14EC5D0), [("veteran_cut_value", 0x2BFB67, bytes.fromhex("e8d4d8ffff"),
                                                bytes.fromhex("e864ca2201"))])

    def test_presets_options_and_late_owner_order(self):
        # b778-int2: fa1's star retention stays before every later b778 owner; the module loader and return coverage are last.
        self.assertEqual(space.LATE_OWNERS[-14], sr.OWNER)
        self.assertEqual(space.LATE_OWNERS[-4:], ("nfl2k5_cpu_third_down", "nfl2k5_return_coverage", "nfl2k5_pass_protection", "nfl2k5_module_loader"))
        self.assertEqual(space.LATE_OWNERS[-2], "nfl2k5_module_loader")
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).star_retention, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["star_retention"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        self.assertIn("star_retention", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_star_retention", "CPU clubs keep their stars"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        text = (ROOT / "mod_editor/core/nfl2k5_star_retention.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", sr.HELP_TEXT + sr.BUILD_CAPTION)


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = sr.apply(cls.retail)
        cls.with_economy = sr.apply(economy.apply(cls.retail)[0])[0]

    def test_site_code_and_receipt(self):
        self.assertEqual(sr.status(self.retail), "retail")
        self.assertEqual(sr.status(self.final), "applied")
        image = XbeImage(self.final)
        code = sr.allocation(self.final)["va"]
        self.assertEqual(image.read(code, sr.CODE_SIZE), sr.code_for(code))
        raw = image.read(0x2BFB67, 5)
        self.assertEqual(raw[0], 0xE8)
        self.assertEqual(0x2BFB67 + 5 + struct.unpack_from("<i", raw, 1)[0], code)
        self.assertEqual(self.receipt["runtime_witnessed"], False)
        self.assertEqual(sr.read_settings(self.final), {"status": "applied", "star_overall": 85, "qb_overall": 75})
        self.assertEqual(space.status(self.final), "applied")

    def test_only_the_hook_changes_in_retail_sections(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        changed = []
        for s in a.sections:
            if s.raw_size:
                x, y = a.read(s.start, s.raw_size), b.read(s.start, s.raw_size)
                changed += [s.start + i for i in range(len(x)) if x[i] != y[i]]
        self.assertEqual(changed, list(range(0x2BFB68, 0x2BFB6C)))

    def test_composes_with_the_franchise_economy_in_either_order(self):
        self.assertEqual(sr.status(self.with_economy), "applied")
        self.assertEqual(economy.status(self.with_economy), "applied")
        self.assertEqual(XbeImage(self.with_economy).read(0x2BFB61, 2), bytes.fromhex("6a00"))

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = sr.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = sr.allocation(self.final)["va"]
        for label, (va, content) in {"hook": (0x2BFB67, b"\xe8\x00\x00\x00\x00"),
                                     "code": (code + 3, b"\x90"),
                                     "threshold": (code + sr.DATA_OFFSET + 3, b"\x00"),
                                     "years-pro rule": (0x2BFB57, b"\x90"),
                                     "stage-6 caller": (0x247FEE, b"\xba\x05")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(sr.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                sr.apply(bad)
        retail_bad = repin_edit(self.retail, 0x2BFB57, b"\x90")
        self.assertEqual(sr.status(retail_bad), "foreign")
        with self.assertRaises(ValueError):
            sr.apply(retail_bad)


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class NativeStageSixTests(unittest.TestCase):
    """Club 0 near the cap in stage 6 with three 12-year veterans each paid far over 2.1 x his market value, first
    on its roster: a star (every rating 99), a quarterback rated about 80 and a depth player (every rating 40)."""

    PLAYERS = (("star", 3, 99), ("qb", 0, 80), ("depth", 3, 40))

    def run_stage_six(self, payload):
        from tools.franchise_economy.probe import start
        m = start(retail_roster(), payload)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        team = m.team_base
        members = [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]
        chosen = {}
        for (label, position, rating), p in zip(self.PLAYERS, members[:3]):
            raw = bytearray(m.uc.mem_read(p, 84))
            struct.pack_into("<H", raw, 10, 40000)          # 4-year balanced deal, 3 left: 100M base a season
            raw[0x24] = (raw[0x24] & 0xF0) | 3
            raw[0x25] = (raw[0x25] & 0xE0) | 12
            raw[0x26] = 2
            raw[0x27] = (raw[0x27] & 0xF0) | 4
            raw[0x35] = position
            raw[0x36:0x52] = bytes([rating]) * 28
            m.uc.mem_write(p, bytes(raw))
            chosen[label] = p
        from tests.franchise_economy_legacy import no_restructure_room
        no_restructure_room(m, team, set(chosen.values()))   # b778 fa2: the retail cut alone, no restructures
        m.call(0xC3F00, ecx=team)
        m.put(0xE3C278, m.get(team + 0x124) + 1000)       # within 6000 of the cap, not over it
        m.put(0xE576A4, 6)
        m.put(0xE576B4, 0)
        m.put(0xE576B8, 1)
        released = []
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: released.append((m.reg("EDX"), m.get(m.reg("ESP")))),
                      begin=0x2BD900, end=0x2BD900)
        m.call(0x247D40, ecx=m.ARENA + 0x1A0000, budget=2_000_000_000)
        self.assertEqual(m.reg("ESP"), m.STACK + 4)
        for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333)):
            self.assertEqual(m.reg(name), value)
        cuts = {p for p, caller in released if caller == 0x2BFBC2}
        return {label: p in cuts for label, p in chosen.items()}

    def test_economy_alone_cuts_the_star_first(self):
        # The cut walks the roster in order and stops once payroll + 6000 < cap: the star (first) clears it.
        self.assertEqual(self.run_stage_six(economy.apply(retail_xbe())[0]), {"star": True, "qb": False, "depth": False})

    def test_star_retention_keeps_the_star_and_the_qb(self):
        payload = sr.apply(economy.apply(retail_xbe())[0])[0]
        self.assertEqual(self.run_stage_six(payload), {"star": False, "qb": False, "depth": True})

    def test_retail_value_with_star_retention(self):
        self.assertEqual(self.run_stage_six(sr.apply(retail_xbe())[0])["star"], False)


if __name__ == "__main__":
    unittest.main()
