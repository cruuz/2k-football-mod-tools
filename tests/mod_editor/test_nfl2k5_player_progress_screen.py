"""b778-pg3: the native Player Progress owner, its franchise footer hooks and the safe visibility row.

The installed cave runs under Unicorn on the retail executable with the game's list/team/overall
routines mocked. It must show the row in every season/playoff stage, keep a 17-week rating ring,
return the season and historical weekly views, and append/read the fixed footer through the native
save/load call sites. The visibility-only variant installs only the 0x2C26A0 patch.
"""

from __future__ import annotations

import os
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
FILE, META = 0x05000000, 0x07000000
TARGETS = 0x06000000
RECORD = DATA + screen.RECORD_VA_DELTA


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.released = None
        released = Path(os.environ.get("NFL2K5_RELEASED_XBE", "/nonexistent"))
        if released.is_file():
            cls.released = released.read_bytes()

    def test_retail_and_released_are_retail(self):
        self.assertEqual(screen.status(self.retail), "retail")
        if self.released is not None:
            self.assertEqual(screen.status(self.released), "retail")

    def test_foreign_prerequisite_is_refused(self):
        bad = repin_edit(self.retail, 0xE6660, b"\xcc")
        self.assertEqual(screen.status(bad), "foreign")
        bad = repin_edit(self.retail, 0x16AA10, b"\xcc")
        self.assertEqual(screen.status(bad), "foreign")

    def test_full_apply_round_trip_when_the_pool_is_available(self):
        if not hasattr(space, "POOL_VA"):
            self.skipTest("the growable pool (b778-xs1) is not merged on this branch")
        applied, receipt = screen.apply(self.retail)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(receipt["variant"], "applied")
        self.assertEqual(screen.status(applied), "applied")
        self.assertEqual(space.status(applied), "applied")
        again, second = screen.apply(applied)
        self.assertEqual(again, applied)
        self.assertEqual(second["status"], "already_applied")
        code_va = int(receipt["code_va"], 16)
        image = XbeImage(applied)
        for _label, va, _before, after in screen._sites(code_va) + screen._footer_sites(code_va):
            self.assertEqual(image.read(va, len(after)), after)
        self.assertEqual(image.read(code_va, screen.CODE_SIZE),
                         screen.code_for(code_va, int(receipt["data_va"], 16),
                                         use_native_admission=False))

    def test_visibility_only_round_trip_leaves_the_save_sites_retail(self):
        if not hasattr(space, "POOL_VA"):
            self.skipTest("the growable pool (b778-xs1) is not merged on this branch")
        applied, receipt = screen.apply(self.retail, visible_only=True)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(receipt["save_growth"], 0)
        self.assertEqual(screen.status(applied), "visible")
        self.assertEqual(screen.variant(applied), "visible")
        image = XbeImage(applied)
        for site in screen._footer_sites(int(receipt["code_va"], 16)):
            self.assertEqual(image.read(site[1], len(site[2])), site[2])
        again, second = screen.apply(applied, visible_only=True)
        self.assertEqual(again, applied)
        self.assertEqual(second["status"], "already_applied")

    def test_code_and_hooks_are_exact(self):
        code = screen.code_for(0x14DA000, 0x14BB000)
        self.assertEqual(len(code), screen.CODE_SIZE)
        self.assertEqual(code, screen.code_for(0x14DA000, 0x14BB000))
        sites = {label: (va, before, after) for label, va, before, after in screen._sites(0x14DA000)}
        self.assertEqual(sites["visibility"][0], 0x2C26A0)
        self.assertEqual(sites["visibility"][1], bytes.fromhex("568bf2c746"))
        self.assertEqual(sites["week_advance"][0], 0xC4E60)
        self.assertEqual(len(sites["week_advance"][2]), 7)
        self.assertEqual(sites["game_end"][0], 0x1353FC)
        self.assertEqual(sites["game_end"][1], bytes.fromhex("e8cff9ffff"))
        self.assertEqual(sites["game_end"][2][0], 0xE8)
        self.assertEqual(sites["value_getter"][0], 0x365B20)
        self.assertEqual(sites["event_pointer"][0], 0xF4268)
        footer = {label: (va, before, after)
                  for label, va, before, after in screen._footer_sites(0x14DA000)}
        self.assertEqual(footer["total_size"][0], 0x16AA26)
        self.assertEqual(footer["save_front_office"][0], 0x16E50D)
        self.assertEqual(footer["load_end"][0], 0x16E815)
        self.assertEqual(footer["admission"][0], 0x16ABB5)
        self.assertEqual(screen.CODE_SIZE, 4096)
        self.assertEqual(screen.REQUESTS[1][2], 34336)
        self.assertIn(screen.OWNER, space.LATE_OWNERS)

    def test_options_presets_and_plumbing(self):
        plan = mod_build.BuildPlan(Path("source.iso"), Path("target.iso"))
        self.assertIs(plan.player_progress, False)
        self.assertIs(plan.player_progress_visible, False)
        self.assertIs(mod_build.PRESETS["softdrink_basic"]["player_progress_visible"], False)
        self.assertIs(mod_build.PRESETS["softdrink_advanced"]["player_progress_visible"], True)
        self.assertIs(mod_build.PRESETS["softdrink_experimental"]["player_progress_visible"], True)
        self.assertIs(mod_build.PRESETS["softdrink_experimental"]["player_progress"], False)
        self.assertIn("player_progress_visible", settings.FEATURE_KEYS)
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
        cls.blob = screen.code_for(CODE, DATA, (TARGETS, TARGETS + 0x10, TARGETS + 0x20))
        cls.overall = 77
        cls.team_pointer = P0

    def machine(self):
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        for base, size in ((ROSTER, 0x100000), (CODE, 0x2000), (DATA, 0x10000), (FILE, 0x100000),
                           (META, 0xC00000), (TARGETS, 0x1000), (0xB72000, 0x1000),
                           (0xE57000, 0x1000), (0xC4000, 0x4000), (0xF3000, 0x2000),
                           (0x170000, 0x2000), (0xE6000, 0x2000), (0x247000, 0x2000), (0x133000, 0x2000),
                           (0x14F000, 0x2000), (0x365000, 0x2000), (STACK, 0x10000)):
            m.mem_map(base, size)
        m.mem_write(CODE, self.blob)
        m.mem_write(DATA, bytes(0x10000))
        m.mem_write(ROSTER + 0x1C, struct.pack("<I", TEAM))
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
        m.mem_write(0xB72808, struct.pack("<I", 0xB0000))

        def ret_imm(va, value):
            m.mem_write(va, b"\xb8" + struct.pack("<I", value) + b"\xc3")
        ret_imm(0xC4D70, TEAM)
        ret_imm(0xF31B0, LIST)
        ret_imm(0x170510, 0)
        ret_imm(0xC4BB0, 8)
        ret_imm(0xC4B80, 2)
        m.mem_write(0xE6660, b"\xa1\x20\x29\xb7\x00\xc3")
        m.mem_write(0xB72920, struct.pack("<I", self.overall))
        m.mem_write(0x247B20, b"\xc3")
        m.mem_write(0x14FCD0, b"\xf4")
        m.mem_write(0x365B25, b"\xb8\x34\x12\x00\x00\x5b\xc2\x0c\x00")
        # the retail per-attribute helper: the tests use the speed row (row 5), which reads rating 0
        m.mem_write(0x365B00, b"\x0f\xb6\x41\x36\xc3")
        m.mem_write(0xC5D26, b"\xf4")
        # displaced size/save/load targets: size returns the native front-office term
        ret_imm(TARGETS, 0x165B0)
        m.mem_write(TARGETS + 0x10, b"\xc3")
        m.mem_write(TARGETS + 0x20, b"\xc3")
        return m

    def call(self, m, label, ecx=0, edx=0, esi=0, ebp=0, eax=0, stack=()):
        sp = STACK + 0x8000
        for value in reversed(stack):
            sp -= 4
            m.mem_write(sp, struct.pack("<I", value))
        sp -= 4
        m.mem_write(sp, struct.pack("<I", SENTINEL))
        for reg in (x86.UC_X86_REG_ECX, x86.UC_X86_REG_EDX, x86.UC_X86_REG_EBP,
                    x86.UC_X86_REG_ESI, x86.UC_X86_REG_EDI, x86.UC_X86_REG_EBX, x86.UC_X86_REG_EAX):
            m.reg_write(reg, 0)
        m.reg_write(x86.UC_X86_REG_ESP, sp)
        m.reg_write(x86.UC_X86_REG_ECX, ecx)
        m.reg_write(x86.UC_X86_REG_EDX, edx)
        m.reg_write(x86.UC_X86_REG_ESI, esi)
        m.reg_write(x86.UC_X86_REG_EBP, ebp)
        m.reg_write(x86.UC_X86_REG_EAX, eax)
        try:
            m.emu_start(CODE + self.labels[label], SENTINEL, count=200000, timeout=5_000_000)
        except uc.UcError as exc:
            eip = m.reg_read(x86.UC_X86_REG_EIP)
            self.fail(f"{label} faulted at 0x{eip:x}: {exc}")
        return m.reg_read(x86.UC_X86_REG_EAX), m.reg_read(x86.UC_X86_REG_EDX)

    def value(self, m, mode, row):
        return self.call(m, "value", stack=(mode, row, 1))[0]

    def toggle(self, m, view):
        m.mem_write(DATA, bytes([view]))

    def toggle_event(self, m):
        # The retail event at 0xF4221 is entered with EDI and ESI already on the stack.
        sp = STACK + 0x8000
        m.mem_write(sp, struct.pack("<III", 0x1111, 0x2222, SENTINEL))
        m.reg_write(x86.UC_X86_REG_ESP, sp)
        m.reg_write(x86.UC_X86_REG_EDI, 0)
        m.reg_write(x86.UC_X86_REG_ESI, 0)
        m.emu_start(CODE + self.labels["toggle"], SENTINEL, count=10000, timeout=5_000_000)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EIP), SENTINEL)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EDI), 0x1111)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_ESI), 0x2222)

    def record_bytes(self, m):
        return bytes(m.mem_read(RECORD, record.RECORD_SIZE))

    def test_visibility_toggle_and_header(self):
        m = self.machine()
        for stage, hidden in ((0, 1), (1, 0), (2, 0), (3, 0), (4, 1), (5, 1), (6, 1), (7, 0), (8, 0), (9, 0)):
            m.mem_write(0xE576A4, struct.pack("<I", stage))
            m.mem_write(ROWPTR, struct.pack("<I", 1))
            self.call(m, "visibility", edx=ROWPTR)
            self.assertEqual(struct.unpack("<I", m.mem_read(ROWPTR + 8, 4))[0], hidden, stage)
        self.assertEqual(self.call(m, "header")[1], 0xEB92D8)
        for view in range(1, 9):
            self.toggle_event(m)
            self.assertEqual(m.mem_read(DATA, 1), bytes([view]))
            expected = CODE + screen._TEXT_OFFSET + (view - 1) * 24
            self.assertEqual(self.call(m, "header")[1], expected)
        self.toggle_event(m)
        self.assertEqual(m.mem_read(DATA, 1), b"\x00")
        self.assertEqual(self.call(m, "header")[1], 0xEB92D8)

    def test_baseline_season_and_week_history(self):
        m = self.machine()
        self.call(m, "capture_baseline")
        raw = self.record_bytes(m)
        self.assertEqual(raw[:4], record.RECORD_MAGIC)
        self.assertEqual(m.mem_read(DATA + 16, 8), record.FOOTER_MAGIC)
        self.assertEqual(raw[4], 1)
        self.assertEqual(struct.unpack_from("<H", raw, 6)[0], 2027)
        self.assertEqual(raw[8], 0)                     # team index
        self.assertEqual(self.value(m, 0, 0), 77)
        self.assertEqual(self.value(m, 1, 0), 77)
        self.assertEqual(self.value(m, 2, 0), 0)
        self.assertEqual(self.value(m, 0, 5), 50)
        self.assertEqual(self.value(m, 1, 5), 50)
        # week 0: speed +5, overall +2
        m.mem_write(P0 + 0x36, bytes([55]))
        m.mem_write(0xB72920, struct.pack("<I", 79))
        m.mem_write(0xE576B4, struct.pack("<I", 6))
        self.call(m, "capture_week")
        self.toggle(m, 1)
        self.assertEqual(self.value(m, 0, 5), 50)       # previously = baseline
        self.assertEqual(self.value(m, 1, 5), 55)       # currently = week 0 snapshot
        self.assertEqual(self.value(m, 2, 5), 5)
        self.assertEqual(self.value(m, 2, 0), 2)
        self.toggle(m, 0)
        self.assertEqual(self.value(m, 2, 5), 5)        # season = live - baseline
        self.assertEqual(self.value(m, 2, 0), 2)
        # week 1: speed +2, overall +1
        m.mem_write(P0 + 0x36, bytes([57]))
        m.mem_write(0xB72920, struct.pack("<I", 80))
        m.mem_write(0xE576B4, struct.pack("<I", 7))
        self.call(m, "capture_week")
        self.toggle(m, 1)
        self.assertEqual(self.value(m, 2, 5), 2)        # week 1 delta
        self.assertEqual(self.value(m, 2, 0), 1)
        self.toggle(m, 2)
        self.assertEqual(self.value(m, 2, 5), 5)        # week 0 delta
        self.assertEqual(self.value(m, 0, 5), 50)       # week -1 = baseline
        self.toggle(m, 0)
        self.assertEqual(self.value(m, 2, 5), 7)
        self.assertEqual(self.value(m, 2, 0), 3)

    def test_identity_change_and_retail_fallback(self):
        m = self.machine()
        self.call(m, "capture_baseline")
        m.mem_write(P0 + 4, struct.pack("<H", 999))
        self.call(m, "capture_week")
        raw = self.record_bytes(m)
        slot = raw[record.RECORD_HEADER_SIZE:record.RECORD_HEADER_SIZE + record.SLOT_SIZE]
        self.assertEqual(slot[4], record.FLAG_IDENTITY | record.FLAG_BASELINE)
        self.assertEqual(slot[6], m.mem_read(P0 + 0x36, 1)[0])
        # a player not on the user team falls back to the retail getter
        m.mem_write(LIST + 0xA4, struct.pack("<I", 2))
        m.mem_write(ARRAY + 4, struct.pack("<I", 0x02012000))
        m.mem_write(0x02012000, bytes(0x54))
        m.mem_write(0x170510, b"\xb8\x01\x00\x00\x00\xc3")
        self.assertEqual(self.value(m, 0, 0), 0x1234)

    def test_wrappers_capture_once(self):
        m = self.machine()
        self.call(m, "stage_wrapper", ecx=7)
        self.assertEqual(self.record_bytes(m)[:4], bytes(4))
        self.call(m, "stage_wrapper", ecx=8)
        self.assertEqual(self.record_bytes(m)[:4], record.RECORD_MAGIC)
        # The week setter only guarantees a baseline; the weekly entry is the post-game capture.
        m.mem_write(0xE576B4, struct.pack("<I", 4))
        self.call(m, "week_setter", ecx=5)
        self.assertEqual(struct.unpack("<I", m.mem_read(0xE576B4, 4))[0], 5)
        raw = self.record_bytes(m)
        self.assertEqual(raw[:4], record.RECORD_MAGIC)
        self.assertEqual(raw[9], 0)
        self.assertEqual(raw[10], 0)
        # The stage-enter reset to week 0 never fabricates a week.
        self.call(m, "week_setter", ecx=0)
        self.assertEqual(self.record_bytes(m)[10], 0)
        # The post-game capture writes the completed week at the ring head.
        m.mem_write(0xE576B4, struct.pack("<I", 5))
        self.call(m, "capture_week")
        raw = self.record_bytes(m)
        self.assertEqual(raw[9], 5)
        self.assertEqual(raw[10], 1)
        self.assertEqual(raw[11], 1)

    def game_call(self, m, clubs, week=6):
        game = 0x02040000
        m.mem_write(game, bytes([0, clubs[0], clubs[1]]))
        sp = STACK + 0x8000
        m.mem_write(sp, struct.pack("<I", SENTINEL))       # return address
        m.mem_write(sp + 4, struct.pack("<I", 1))          # call-site arg 2
        m.mem_write(sp + 8, struct.pack("<I", 0))          # call-site arg 1
        m.mem_write(sp + 0x20, struct.pack("<I", game))    # game struct in the caller's frame
        m.mem_write(0xE576B4, struct.pack("<I", week))
        m.reg_write(x86.UC_X86_REG_ESP, sp)
        m.reg_write(x86.UC_X86_REG_EAX, 0)
        m.reg_write(x86.UC_X86_REG_ECX, 0)
        m.reg_write(x86.UC_X86_REG_EDX, 0)
        m.emu_start(CODE + self.labels["game_end"], SENTINEL, count=200000, timeout=5_000_000)

    def test_game_end_captures_only_the_user_game(self):
        m = self.machine()
        m.mem_write(0x134DD0, b"\xc2\x08\x00")            # displaced stat merge: ret 8
        self.call(m, "capture_baseline")
        m.mem_write(P0 + 0x36, bytes([55]))
        self.game_call(m, (0, 1))
        raw = self.record_bytes(m)
        self.assertEqual(raw[9], 6)
        self.assertEqual(raw[10], 1)
        self.assertEqual(raw[32 + 34], 55)                  # week snapshot of P0's slot
        # a game that does not involve the user's club (team index 0) writes nothing
        m.mem_write(P0 + 0x36, bytes([56]))
        self.game_call(m, (2, 3), week=7)
        raw = self.record_bytes(m)
        self.assertEqual(raw[9], 6)
        self.assertEqual(raw[10], 1)

    def test_slots_follow_identity_when_the_roster_reorders(self):
        m = self.machine()
        self.call(m, "capture_baseline")
        m.mem_write(P0 + 0x36, bytes([60]))
        m.mem_write(0xE576B4, struct.pack("<I", 6))
        self.call(m, "capture_week")
        # the depth chart swaps the two players; the history stays on the player's own slot
        m.mem_write(TEAM, struct.pack("<II", P1, P0))
        m.mem_write(P0 + 0x36, bytes([65]))
        m.mem_write(P1 + 0x36, bytes([44]))
        m.mem_write(0xE576B4, struct.pack("<I", 7))
        self.call(m, "capture_week")
        raw = self.record_bytes(m)
        slot0 = raw[record.RECORD_HEADER_SIZE:record.RECORD_HEADER_SIZE + record.SLOT_SIZE]
        slot1 = raw[record.RECORD_HEADER_SIZE + record.SLOT_SIZE:
                   record.RECORD_HEADER_SIZE + 2 * record.SLOT_SIZE]
        self.assertEqual(struct.unpack_from("<H", slot0, 0)[0], 10)   # P0 keeps slot 0
        self.assertEqual(struct.unpack_from("<H", slot1, 0)[0], 11)   # P1 keeps slot 1
        self.assertEqual(slot0[34 + 29], 65)                         # P0 week 7 snapshot speed (rating 0)
        self.assertEqual(slot1[34 + 29], 44)
        # the screen finds P0 by identity, not by the new index
        m.mem_write(LIST + 0xA4, struct.pack("<I", 2))
        m.mem_write(ARRAY, struct.pack("<II", P1, P0))
        m.mem_write(0x170510, b"\xb8\x01\x00\x00\x00\xc3")
        self.toggle(m, 1)
        self.assertEqual(self.value(m, 1, 5), 65)

    def test_size_hook_adds_one_footer(self):
        m = self.machine()
        self.assertEqual(self.call(m, "size_hook")[0], 0x165B0 + record.FOOTER_SIZE)

    def test_save_hook_appends_the_footer(self):
        m = self.machine()
        roster = [{"pbp_id": 10 + i, "position": 0, "jersey": i, "overall": 70,
                   "ratings": [50] * record.RATING_COUNT} for i in range(record.TEAM_SLOTS)]
        footer = record.baseline(roster, year=2027, team=3)
        m.mem_write(DATA + 16, footer)
        m.mem_write(FILE, bytes(0x10000))
        self.call(m, "save_hook", ecx=0x1200, esi=FILE, eax=0x10000)
        # EBX is the total size; set it through the register helper below.
        m.reg_write(x86.UC_X86_REG_EBX, 0x10000)
        # repeat with a real stack frame because the helper zeroes EBX
        sp = STACK + 0x8000
        m.mem_write(sp, struct.pack("<I", SENTINEL))
        m.reg_write(x86.UC_X86_REG_ESP, sp)
        m.reg_write(x86.UC_X86_REG_ECX, 0x1200)
        m.reg_write(x86.UC_X86_REG_ESI, FILE)
        m.reg_write(x86.UC_X86_REG_EBX, 0x10000)
        m.emu_start(CODE + self.labels["save_hook"], SENTINEL, count=200000, timeout=5_000_000)
        self.assertEqual(bytes(m.mem_read(FILE + 0x10000 - record.FOOTER_SIZE, 8)), record.FOOTER_MAGIC)
        self.assertEqual(bytes(m.mem_read(FILE + 0x10000 - record.FOOTER_SIZE, record.FOOTER_SIZE)), footer)
        self.assertEqual(bytes(m.mem_read(FILE, 0x10000 - record.FOOTER_SIZE)), bytes(0x10000 - record.FOOTER_SIZE))

    def test_load_hook_reads_or_clears_the_footer(self):
        m = self.machine()
        roster = [{"pbp_id": 10 + i, "position": 0, "jersey": i, "overall": 70,
                   "ratings": [50] * record.RATING_COUNT} for i in range(record.TEAM_SLOTS)]
        footer = record.baseline(roster, year=2028, team=7)
        size = 0x10000
        m.mem_write(FILE + size - record.FOOTER_SIZE, footer)
        m.mem_write(META + 0xbdc1cc, struct.pack("<I", size))
        self.call(m, "load_hook", esi=FILE, ebp=META)
        self.assertEqual(bytes(m.mem_read(DATA + 16, record.FOOTER_SIZE)), footer)
        # a file without the magic clears the RAM footer and starts a fresh baseline
        m.mem_write(FILE + size - record.FOOTER_SIZE, bytes(record.FOOTER_SIZE))
        self.call(m, "load_hook", esi=FILE, ebp=META)
        fresh = bytes(m.mem_read(DATA + 16, record.FOOTER_SIZE))
        self.assertEqual(fresh[:8], record.FOOTER_MAGIC)
        self.assertEqual(fresh[32:36], record.RECORD_MAGIC)
        self.assertEqual(fresh[32 + 4], 1)
        self.assertEqual(fresh[32 + 5], record.HEADER_BASELINE)
        self.assertEqual(struct.unpack_from("<H", fresh, 32 + 6)[0], 2027)
        # it is a new baseline, not the loaded footer
        self.assertNotEqual(fresh, footer)
        self.assertEqual(fresh[32 + 32:32 + 32 + record.SLOT_SIZE][6:34],
                         m.mem_read(P0 + 0x36, record.RATING_COUNT))

    def test_admission_accepts_every_native_and_footer_size(self):
        m = self.machine()
        m.mem_write(META, bytes(0xC00000))
        for arena, accepted, rejected in (
                (0xB0000, (847020, 847148, 881340, 881468, 720044, 720172, 754364, 754492),
                 (724140, 724268, 881339, 0, 847021)),
                (0x92000, (724140, 724268, 758460, 758588, 720044, 720172, 754364, 754492),
                 (847020, 881340, 758459)),
                (0x91000, (720044, 720172, 754364, 754492), (724140, 847020, 881340, 754363))):
            m.mem_write(0xB72808, struct.pack("<I", arena))
            for size in accepted:
                m.mem_write(META + 0xbdc1cc, struct.pack("<I", size))
                self.assertEqual(self.call(m, "admission", esi=META, stack=(SENTINEL,))[0], 0, (hex(arena), size))
            for size in rejected:
                m.mem_write(META + 0xbdc1cc, struct.pack("<I", size))
                self.assertEqual(self.call(m, "admission", esi=META, stack=(SENTINEL,))[0], 1, (hex(arena), size))

    def test_visibility_only_code(self):
        blob = screen.visible_code_for(CODE)
        m = self.machine()
        m.mem_write(CODE, blob)
        labels = screen._VISIBLE_LABELS
        for stage, hidden in ((0, 1), (1, 0), (4, 1), (7, 0), (9, 0), (10, 1)):
            m.mem_write(0xE576A4, struct.pack("<I", stage))
            m.mem_write(ROWPTR, struct.pack("<I", 1))
            sp = STACK + 0x8000
            m.mem_write(sp, struct.pack("<I", SENTINEL))
            m.reg_write(x86.UC_X86_REG_ESP, sp)
            m.reg_write(x86.UC_X86_REG_EDX, ROWPTR)
            m.emu_start(CODE + labels["visibility"], SENTINEL, count=10000, timeout=5_000_000)
            self.assertEqual(struct.unpack("<I", m.mem_read(ROWPTR + 8, 4))[0], hidden, stage)


if __name__ == "__main__":
    unittest.main()
