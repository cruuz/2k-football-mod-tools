"""b778-pg2: the native Player Progress screen + weekly snapshot owner.

The installed cave runs under Unicorn on the retail executable with the game's list/team/overall
routines mocked. It must show the row in every season/playoff stage, return the stored season
baseline and the live rating, switch the change row between season and last week, and write the
PPG2 record at the season start and after each week. Foreign prerequisites, presets and the late
owner order are checked statically.
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as settings  # noqa: E402
from mod_editor.core import nfl2k5_player_progress_screen as screen  # noqa: E402
from mod_editor.core import nfl2k5_player_progression as record  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit  # noqa: E402

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

CODE, DATA = 0x03000000, 0x03010000
ROSTER, TEAM, P0, P1, LIST, ARRAY, ROWPTR = (0x02000000, 0x02010000, 0x02011000, 0x02011100,
                                            0x02020000, 0x02021000, 0x02030000)
STACK, SENTINEL = 0x04000000, 0x04080000
RECORD = ROSTER + record.RECORD_RUNTIME_DELTA


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.retail = retail_xbe()
        except unittest.SkipTest:
            raise
        cls.released = None
        released = Path("/home/noah/2k-worktrees/.b77-scratch/b778/pg2/released_default.xbe")
        if released.is_file():
            cls.released = released.read_bytes()

    def test_retail_and_released_are_retail(self):
        self.assertEqual(screen.status(self.retail), "retail")
        if self.released is not None:
            self.assertEqual(screen.status(self.released), "retail")

    def test_foreign_prerequisite_is_refused(self):
        bad = repin_edit(self.retail, 0xE6660, b"\xcc")
        self.assertEqual(screen.status(bad), "foreign")

    def test_apply_round_trip_when_the_pool_is_available(self):
        if not hasattr(space, "POOL_VA"):
            self.skipTest("the growable pool (b778-xs1) is not merged on this branch")
        applied, receipt = screen.apply(self.retail)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(screen.status(applied), "applied")
        self.assertEqual(space.status(applied), "applied")
        self.assertGreaterEqual(len(applied), len(self.retail))
        again, second = screen.apply(applied)
        self.assertEqual(again, applied)
        self.assertEqual(second["status"], "already_applied")
        code_va = int(receipt["code_va"], 16)
        image = XbeImage(applied)
        for _label, va, _before, after in screen._sites(code_va):
            self.assertEqual(image.read(va, len(after)), after)
        self.assertEqual(image.read(code_va, screen.CODE_SIZE),
                         screen.code_for(code_va, int(receipt["data_va"], 16)))

    def test_code_and_hooks_are_exact(self):
        code = screen.code_for(0x14DA000, 0x14BB000)
        self.assertEqual(len(code), screen.CODE_SIZE)
        self.assertEqual(code, screen.code_for(0x14DA000, 0x14BB000))
        sites = {label: (va, before, after) for label, va, before, after in screen._sites(0x14DA000)}
        self.assertEqual(sites["visibility"][0], 0x2C26A0)
        self.assertEqual(sites["visibility"][1], bytes.fromhex("568bf2c746"))
        self.assertEqual(sites["stage_new_season"][0], 0x13EF03)
        self.assertEqual(sites["stage_next_season"][0], 0x248641)
        self.assertEqual(sites["week_advance"][0], 0xC4E60)
        self.assertEqual(len(sites["week_advance"][2]), 7)
        self.assertEqual(sites["value_getter"][0], 0x365B20)
        self.assertEqual(sites["change_header"][0], 0x365E34)
        self.assertEqual(sites["event_pointer"][0], 0xF4268)
        self.assertEqual(screen.CODE_SIZE, 1408)
        self.assertIn(screen.OWNER, space.LATE_OWNERS)

    def test_options_presets_and_plumbing(self):
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).player_progress, False)
        self.assertIs(mod_build.PRESETS["softdrink_basic"]["player_progress"], False)
        self.assertIs(mod_build.PRESETS["softdrink_advanced"]["player_progress"], False)
        self.assertIs(mod_build.PRESETS["softdrink_experimental"]["player_progress"], False)
        self.assertIn("player_progress", settings.FEATURE_KEYS)
        self.assertIn((screen.OWNER, "Player Progress screen"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        text = (ROOT / "mod_editor/core/nfl2k5_player_progress_screen.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", text)


@unittest.skipIf(uc is None, "unicorn is not installed")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.labels = screen.labels()
        cls.blob = screen.code_for(CODE, DATA)
        cls.overall = 77
        cls.team_pointer = P0

    def machine(self):
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        for base, size in ((ROSTER, 0x100000), (CODE, 0x20000), (0xB72000, 0x1000), (0xE57000, 0x1000),
                           (0xC4000, 0x4000), (0xF3000, 0x2000), (0x170000, 0x2000), (0xE6000, 0x2000),
                           (0x247000, 0x2000), (0x14F000, 0x2000), (0x365000, 0x2000), (STACK, 0x10000)):
            m.mem_map(base, size)
        m.mem_write(CODE, self.blob)
        m.mem_write(DATA, bytes(16))
        m.mem_write(ROSTER + 0x18, struct.pack("<II", 1, TEAM))
        m.mem_write(0xB72918, struct.pack("<I", ROSTER))
        m.mem_write(TEAM, struct.pack("<II", P0, P1))
        m.mem_write(TEAM + 0x11C, bytes([2]))
        for index, player in enumerate((P0, P1)):
            m.mem_write(player, bytes(0x54))
            m.mem_write(player + 4, struct.pack("<H", 10 + index))
            m.mem_write(player + 0x20, struct.pack("<I", (index + 1) << 3))
            m.mem_write(player + 0x35, bytes([0]))
            for field in range(record.RATING_COUNT):
                m.mem_write(player + 0x36 + field, bytes([50 + field]))
        m.mem_write(LIST, bytes(0x108))
        m.mem_write(LIST + 0xA4, struct.pack("<I", 1))
        m.mem_write(LIST + 0x40, struct.pack("<I", ARRAY))
        m.mem_write(LIST + 0x64, struct.pack("<I", 0))
        m.mem_write(ARRAY, struct.pack("<I", P0))
        m.mem_write(ROWPTR, bytes(4))
        m.mem_write(0xE576A4, struct.pack("<I", 8))
        m.mem_write(0xE576B4, struct.pack("<I", 5))
        m.mem_write(0xE576B8, struct.pack("<I", 2027))
        m.mem_write(0xE576A0, struct.pack("<I", 2))

        def ret_imm(va, value):
            m.mem_write(va, b"\xb8" + struct.pack("<I", value) + b"\xc3")
        ret_imm(0xC4D70, TEAM)
        ret_imm(0xF31B0, LIST)
        ret_imm(0x170510, 0)
        ret_imm(0xC4BB0, 8)
        # overall reads a mutable dword so the weekly test can move it
        m.mem_write(0xE6660, b"\xa1\x20\x29\xb7\x00\xc3")
        m.mem_write(0xB72920, struct.pack("<I", self.overall))
        m.mem_write(0x247B20, b"\xc3")
        m.mem_write(0x14FCD0, b"\xf4")
        m.mem_write(0x365B25, b"\xb8\x34\x12\x00\x00\x5b\xc2\x0c\x00")   # retail fallback marker: mov eax,0x1234; pop ebx; ret 0xc
        m.mem_write(0xC5D37, b"\xb8\x78\x56\x00\x00\xc3")    # retail resume marker: mov eax,0x5678; ret
        m.mem_write(0xC5D26, b"\xf4")
        return m

    def call(self, m, label, ecx=0, edx=0, stack=()):
        sp = STACK + 0x8000
        for value in reversed(stack):
            sp -= 4
            m.mem_write(sp, struct.pack("<I", value))
        sp -= 4
        m.mem_write(sp, struct.pack("<I", SENTINEL))
        for reg in (x86.UC_X86_REG_ECX, x86.UC_X86_REG_EDX, x86.UC_X86_REG_EBP,
                    x86.UC_X86_REG_ESI, x86.UC_X86_REG_EDI, x86.UC_X86_REG_EBX):
            m.reg_write(reg, 0)
        m.reg_write(x86.UC_X86_REG_ESP, sp)
        m.reg_write(x86.UC_X86_REG_ECX, ecx)
        m.reg_write(x86.UC_X86_REG_EDX, edx)
        try:
            m.emu_start(CODE + self.labels[label], SENTINEL, count=200000, timeout=5_000_000)
        except uc.UcError as exc:
            self.fail(f"{label} faulted at 0x{m.reg_read(x86.UC_X86_REG_EIP):x}: {exc}")
        return m.reg_read(x86.UC_X86_REG_EAX), m.reg_read(x86.UC_X86_REG_EDX)

    def value(self, m, mode, row):
        return self.call(m, "value", ecx=0, stack=(mode, row, 1))[0]

    def test_visibility_and_toggle(self):
        m = self.machine()
        for stage, hidden in ((0, 1), (1, 0), (2, 0), (3, 0), (4, 1), (5, 1), (6, 1), (7, 0), (8, 0), (9, 0)):
            m.mem_write(0xE576A4, struct.pack("<I", stage))
            m.mem_write(ROWPTR, struct.pack("<I", 1))
            self.call(m, "visibility", edx=ROWPTR)
            self.assertEqual(struct.unpack("<I", m.mem_read(ROWPTR + 8, 4))[0], hidden, stage)
        self.assertEqual(self.call(m, "header")[1], 0xEB92D8)
        self.call(m, "toggle")
        self.assertEqual(m.mem_read(DATA, 1), b"\x01")
        expected = CODE + screen._MAP_OFFSET + len(record.ROW_MAP)
        self.assertEqual(self.call(m, "header")[1], expected)
        self.call(m, "toggle")
        self.assertEqual(m.mem_read(DATA, 1), b"\x00")

    def test_baseline_value_and_weekly_change(self):
        m = self.machine()
        self.call(m, "capture_baseline")
        self.assertEqual(m.mem_read(RECORD, 4), record.MAGIC)
        self.assertEqual(m.mem_read(RECORD + 4, 2), b"\x01\x03")
        self.assertEqual(struct.unpack("<H", m.mem_read(RECORD + 6, 2))[0], 2027)
        self.assertEqual(self.value(m, 0, 0), 77)
        self.assertEqual(self.value(m, 1, 0), 77)
        self.assertEqual(self.value(m, 2, 0), 0)
        self.assertEqual(self.value(m, 0, 5), 50)       # speed
        self.assertEqual(self.value(m, 1, 5), 50)
        # week 0: speed +5, overall +2
        m.mem_write(P0 + 0x36, bytes([55]))
        m.mem_write(0xB72920, struct.pack("<I", 79))
        m.mem_write(0xE576B4, struct.pack("<I", 6))
        self.call(m, "capture_week")
        self.assertEqual(self.value(m, 2, 5), 5)
        self.assertEqual(self.value(m, 2, 0), 2)
        m.mem_write(DATA, b"\x01")
        self.assertEqual(self.value(m, 2, 5), 5)       # same as season at week 1
        # week 1: speed +2, overall +1; last week is now distinct
        m.mem_write(P0 + 0x36, bytes([57]))
        m.mem_write(0xB72920, struct.pack("<I", 80))
        m.mem_write(0xE576B4, struct.pack("<I", 7))
        self.call(m, "capture_week")
        self.assertEqual(self.value(m, 2, 5), 2)
        self.assertEqual(self.value(m, 2, 0), 1)
        m.mem_write(DATA, b"\x00")
        self.assertEqual(self.value(m, 2, 5), 7)
        self.assertEqual(self.value(m, 2, 0), 3)
        self.assertEqual(self.value(m, 0, 5), 50)

    def test_identity_change_and_retail_fallback(self):
        m = self.machine()
        self.call(m, "capture_baseline")
        m.mem_write(P0 + 4, struct.pack("<H", 999))
        self.call(m, "capture_week")
        self.assertEqual(m.mem_read(RECORD + 0x26, 1), b"\x07")
        self.assertEqual(m.mem_read(RECORD + 0x44, 1), m.mem_read(P0 + 0x36, 1))
        # a player not on the user team falls back to the retail getter
        m.mem_write(LIST + 0xA4, struct.pack("<I", 2))
        m.mem_write(ARRAY + 4, struct.pack("<I", 0x02012000))
        m.mem_write(0x02012000, bytes(0x54))
        m.mem_write(0x170510, b"\xb8\x01\x00\x00\x00\xc3")
        self.assertEqual(self.value(m, 0, 0), 0x1234)

    def test_wrappers_capture_once(self):
        m = self.machine()
        # stage wrapper: stage 7 does not capture, stage 8 does
        self.call(m, "stage_wrapper", ecx=7)
        self.assertEqual(m.mem_read(RECORD, 4), bytes(4))
        self.call(m, "stage_wrapper", ecx=8)
        self.assertEqual(m.mem_read(RECORD, 4), record.MAGIC)
        # week setter: new week 5 from week 4 captures and keeps the displaced store (the baseline is present)
        m.mem_write(0xE576B4, struct.pack("<I", 4))
        self.call(m, "week_setter", ecx=5)
        self.assertEqual(struct.unpack("<I", m.mem_read(0xE576B4, 4))[0], 5)
        self.assertEqual(m.mem_read(RECORD, 4), record.MAGIC)
        self.assertEqual(m.mem_read(RECORD + 9, 1), b"\x04")


if __name__ == "__main__":
    unittest.main()
