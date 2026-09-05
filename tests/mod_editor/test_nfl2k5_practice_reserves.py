"""Pinned staging and bounded CPU witnesses; no game, rendering, or audio boot."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import nfl2k5_franchise_practice as fp
from mod_editor.core import nfl2k5_practice_reserves as pr
from mod_editor.core import nfl2k5_practice_squad as ps

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None


def composed(retail):
    return pr.apply(fp.apply(ps.apply(retail)[0])[0])[0]


@unittest.skipUnless(XBE.is_file(), "private retail XBE absent")
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != ps.RETAIL_SHA256:
            raise unittest.SkipTest("not the pinned USA retail XBE")
        cls.patched = composed(cls.retail)

    def test_pins_extent_idempotence_dependencies_and_digests(self):
        self.assertEqual(len(pr.RETAIL_STAGE), pr.STAGE_SIZE)
        self.assertLessEqual(len(pr.code()), pr.STAGE_SIZE)
        self.assertEqual(pr.status(self.retail), "retail")
        self.assertEqual(pr.status(self.patched), "applied")
        again, receipt = pr.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(len(self.patched), len(self.retail))
        for prerequisite in (self.retail, ps.apply(self.retail)[0], fp.apply(self.retail)[0]):
            with self.assertRaises(pr.PracticeReservesError):
                pr.apply(prerequisite)
        for section in ps._sections(self.patched):
            self.assertEqual(section.stored_digest, ps.section_digest(self.patched, section))
        base = fp.apply(ps.apply(self.retail)[0])[0]
        regions = [(pr.STAGE_VA - 0x10000, pr.STAGE_VA - 0x10000 + pr.STAGE_SIZE)]
        regions += [(s.header_offset + 36, s.header_offset + 56) for s in ps._sections(base)]
        self.assertTrue(all(any(a <= i < b for a, b in regions)
                            for i, (x, y) in enumerate(zip(base, self.patched)) if x != y))

    def test_foreign_partial_and_truncated_input_refused(self):
        for image in (b"", self.patched[:4096]):
            self.assertEqual(pr.status(image), "foreign")
        for image in (fp.apply(ps.apply(self.retail)[0])[0], self.patched):
            for address in (pr.STAGE_VA, pr.STAGE_VA + 100, pr.COPY_PLAYERS_VA):
                data = bytearray(image)
                data[pr.rdata.offset_of(data, address)] ^= 0x55
                self.assertEqual(pr.status(data), "foreign")
                with self.assertRaises(pr.PracticeReservesError):
                    pr.apply(data)
        data = bytearray(fp.apply(ps.apply(self.retail)[0])[0])
        data[pr.STAGE_VA - 0x10000:pr.STAGE_VA - 0x10000 + 5] = pr.code()[:5]
        self.assertEqual(pr.status(data), "foreign")
        data = bytearray(self.patched)
        data[ps.SYMBOLS["reserve_count"] - 0x10000] ^= 1
        self.assertEqual(pr.status(data), "foreign")

    def test_composes_with_the_complete_beta60_xbe_stack(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        from mod_editor.core import nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        flags = {name: True for name in (
            "catch_slider", "accel_ramp", "draft_ai", "edge_rename", "returner_fix",
            "progression", "scheme_labels", "camera", "kick_rules", "widescreen",
            "overtime", "team_column", "seven_on_seven")}
        stack, _ = tt._apply_all(self.retail, None, **flags, arc_table=False, kick_power=False,
                                penalties="nfl", uniform_choice="choice", kick_laces=True,
                                franchise_practice=True, prospect_names="modern", player_star=True,
                                dynamic_kickoff=True, practice_squad=True)
        first = rows.apply(pools.apply(pr.apply(stack)[0])[0])[0]
        last = pr.apply(rows.apply(pools.apply(stack)[0])[0])[0]
        self.assertEqual(first, last)
        self.assertEqual(pr.status(last), "applied")
        self.assertEqual(pr.apply(last)[0], last)
        self.assertEqual(fp.status(last), "applied")
        self.assertEqual(ps.status(last), "applied")


@unittest.skipUnless(XBE.is_file() and HAVE_UNICORN, "private XBE or Unicorn absent")
class ExecutionTests(unittest.TestCase):
    ROOT_BASE = 0x2000000
    STACK = 0x3008000
    STOP = 0x3100000

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != ps.RETAIL_SHA256:
            raise unittest.SkipTest("not the pinned USA retail XBE")
        cls.patched = composed(cls.retail)
        from mod_editor.core import nfl2k5_team_history as th
        with th._outer_image()(XBE.parent) as archive:
            entry = th._entry(archive)
            cls.body = archive.read(entry.virtual_offset, entry.size)[th.RESOURCE_HEADER_SIZE:]

    def setUp(self):
        import unicorn as u
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.uc.mem_map(0x10000, 0xFF0000)
        for section in ps._sections(self.patched):
            self.uc.mem_write(section.virtual_address,
                              self.patched[section.raw_offset:section.raw_offset + section.raw_size])
        self.uc.mem_protect(0x11000, 0x410000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_map(self.ROOT_BASE, 0x200000)
        self.uc.mem_map(0x3000000, 0x10000)
        self.uc.mem_map(self.STOP, 0x1000)
        self.uc.mem_write(self.ROOT_BASE, self.body)
        self.root = self.ROOT_BASE + 0x40
        self.put(0xB72918, self.root)
        self.call(0xC0500, ecx=self.root)
        self.team = self.word(self.root + 0x1C)
        self.other = self.team + 500
        self.put(pr.LEAGUE_VA, 1)
        self.put(0xE576A4, 7)
        self.uc.mem_write(0xE421E0, bytes(160 * 4))

    def word(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value))

    def byte(self, va):
        return self.uc.mem_read(va, 1)[0]

    def call(self, address, *, ecx=0, edx=0, args=(), budget=3000000):
        from unicorn import x86_const as r
        registers = ((r.UC_X86_REG_EBX, 0x11111111), (r.UC_X86_REG_ESI, 0x22222222),
                     (r.UC_X86_REG_EDI, 0x33333333), (r.UC_X86_REG_EBP, 0x44444444))
        self.put(self.STACK, self.STOP)
        for i, value in enumerate(args, 1):
            self.put(self.STACK + 4 * i, value)
        for reg, value in (*registers, (r.UC_X86_REG_ESP, self.STACK),
                           (r.UC_X86_REG_ECX, ecx), (r.UC_X86_REG_EDX, edx)):
            self.uc.reg_write(reg, value)
        self.uc.emu_start(address, self.STOP, count=budget)
        self.assertEqual(self.uc.reg_read(r.UC_X86_REG_EIP), self.STOP, "instruction budget exhausted")
        self.assertEqual(self.uc.reg_read(r.UC_X86_REG_ESP), self.STACK + 4 + 4 * len(args))
        for reg, value in registers:
            self.assertEqual(self.uc.reg_read(reg), value)
        return self.uc.reg_read(r.UC_X86_REG_EAX)

    def demote(self, n=1, fill=False):
        if fill:
            fa_count, fa_table = self.word(self.root + 0x38), self.word(self.root + 0x3C)
            for i in range(12):
                player = self.word(fa_table + 4 * i)
                self.assertEqual(self.call(ps.SYMBOLS["ps_append"], ecx=self.team, edx=player), 1)
            self.uc.mem_write(fa_table, bytes(self.uc.mem_read(fa_table + 48, (fa_count - 12) * 4)) + bytes(48))
            self.put(self.root + 0x38, fa_count - 12)
        for _ in range(n):
            player = self.word(self.team + 4 * (self.byte(self.team + ps.ACTIVE_COUNT) - 1))
            self.assertEqual(self.call(ps.SYMBOLS["ps_demote"], ecx=self.team, edx=player), 1)

    def stage(self, mode, league=1, same_team=False):
        import unicorn as u
        self.put(pr.MODE_VA, mode)
        self.put(pr.LEAGUE_VA, league)
        original = bytes(self.uc.mem_read(self.ROOT_BASE, len(self.body)))
        end = pr.PLAYER_COPIES[1] + 65 * 84
        self.uc.mem_write(pr.TEAM_COPIES[0] - 16, b"L" * 16)
        self.uc.mem_write(end, b"R" * 16)
        unexpected = []
        def write(_uc, _access, address, size, _value, _data):
            if not (pr.TEAM_COPIES[0] <= address and address + size <= end) and not (
                    0x3000000 <= address and address + size <= 0x3010000):
                unexpected.append((hex(address), size))
        hook = self.uc.hook_add(u.UC_HOOK_MEM_WRITE, write)
        try:
            self.call(pr.STAGE_VA, ecx=self.team, edx=self.team if same_team else self.other, budget=100000)
        finally:
            self.uc.hook_del(hook)
        self.assertEqual(unexpected, [])
        self.assertEqual(bytes(self.uc.mem_read(self.ROOT_BASE, len(self.body))), original)
        self.assertEqual(bytes(self.uc.mem_read(pr.TEAM_COPIES[0] - 16, 16)), b"L" * 16)
        self.assertEqual(bytes(self.uc.mem_read(end, 16)), b"R" * 16)

    def assert_copied(self, reserves, same_team=False):
        for side, (team, pool) in enumerate(zip(pr.TEAM_COPIES, pr.PLAYER_COPIES)):
            source = self.team if side == 0 or same_team else self.other
            active = self.byte(source + ps.ACTIVE_COUNT)
            count = active + (self.byte(source + ps.COUNT) if reserves else 0)
            self.assertEqual(self.byte(team + ps.ACTIVE_COUNT), count)
            for i in range(count):
                player = self.word(source + 4 * i)
                expected = bytearray(self.uc.mem_read(player, 84))
                expected[0x34] = side + 1
                self.assertEqual(self.word(team + 4 * i), pool + 84 * i)
                self.assertEqual(bytes(self.uc.mem_read(pool + 84 * i, 84)), expected)

    def test_practice_modes_copy_all_65_with_same_team_and_keep_sources_unchanged(self):
        self.demote(12, fill=True)
        self.assertEqual(self.byte(self.team + ps.ACTIVE_COUNT), 53)
        self.assertEqual(self.byte(self.team + ps.COUNT), 12)
        for mode in (0, 1, 2):
            for same_team in (False, True):
                with self.subTest(mode=mode, same_team=same_team):
                    self.stage(mode, same_team=same_team)
                    self.assert_copied(True, same_team)
                    for team in pr.TEAM_COPIES:
                        self.assertEqual(self.byte(team + ps.COUNT), 0)

    def test_every_game_day_training_and_nonfranchise_gate_is_active_only(self):
        self.demote()
        for league, mode in [(1, x) for x in (3, 4, 5, 6, 7, 8, 0xFFFFFFFF)] + [(x, 1) for x in (0, 2, 3)]:
            with self.subTest(league=league, mode=mode):
                self.stage(mode, league)
                self.assert_copied(False)
                got = bytes(self.uc.mem_read(pr.TEAM_COPIES[0], 2 * 500 + 2 * 65 * 84))
                # Run the complete retail staging routine as the independent control.
                self.uc.mem_write(pr.STAGE_VA, pr.RETAIL_STAGE)
                self.stage(mode, league)
                self.assertEqual(bytes(self.uc.mem_read(pr.TEAM_COPIES[0], len(got))), got)
                self.uc.mem_write(pr.STAGE_VA, pr.sites()[0][3])

    def test_single_reserve_empty_and_invalid_metadata_fall_back_without_source_writes(self):
        self.demote()
        self.stage(1)
        self.assert_copied(True)
        self.uc.mem_write(self.team + ps.MARKER_OFFSET, b"\x00")
        self.stage(1)
        self.assert_copied(False)
        self.uc.mem_write(self.team, bytes(260))
        self.uc.mem_write(self.team + ps.ACTIVE_COUNT, b"\x00")
        for offset in (ps.VERSION_OFFSET, ps.COUNT, ps.MARKER_OFFSET):
            self.uc.mem_write(self.team + offset, b"\x00")
        self.stage(1)
        self.assert_copied(True)

    def test_retail_position_lists_offer_reserve_in_practice_then_exclude_on_game_day(self):
        self.demote()
        for mode, expected_count in ((1, 53), (5, 52), (1, 53)):
            self.stage(mode)
            self.assertEqual(self.byte(pr.TEAM_COPIES[0] + ps.ACTIVE_COUNT), expected_count)
            # ECX=team, EDX=sheet, stack=(availability threshold, override), ret 8.
            sheet = 0xB336F4
            self.call(0xE80D0, ecx=pr.TEAM_COPIES[0], edx=sheet, args=(0, 0), budget=1000000)
            # The final list is sentinel-terminated; +0x10C is not an end pointer.
            indices = set(self.uc.mem_read(sheet + 0xC, 144)) - {0xFF}
            self.assertTrue(all(i < expected_count for i in indices))
            self.assertEqual(52 in indices, mode == 1)

    def test_all_65_position_indices_fit_the_retail_buffer(self):
        self.demote(12, fill=True)
        self.stage(1, same_team=True)
        for team, sheet in zip(pr.TEAM_COPIES, (0xB336F4, 0xB33A28)):
            self.call(0xE80D0, ecx=team, edx=sheet, args=(0, 1), budget=1000000)
            indices = set(self.uc.mem_read(sheet + 0xC, 144)) - {0xFF}
            self.assertEqual(indices, set(range(65)))
            for i in range(28):
                pointer = self.word(sheet + 0x9C + 4 * i)
                self.assertTrue(sheet + 0xC <= pointer <= sheet + 0x9C, hex(pointer))

    def test_phase_schedule_callbacks_leave_practice_second(self):
        for phase, week, expected in ((0, 0, "Off-Season Schedule"), (7, 0, "Schedule"),
                                     (8, 0, "Schedule"), (9, 18, "Playoff Schedule"),
                                     (9, 20, "Super Bowl Schedule")):
            self.put(0xE576A4, phase)
            self.put(0xE576B4, week)
            selectable = []
            for row in fp.read_rows(self.patched)[:5]:
                callback = int(row["visibility"], 16)
                if callback:
                    state = self.ROOT_BASE + 0x1F0000
                    self.call(callback, edx=state, budget=1000)
                    if self.word(state + 8):
                        continue
                selectable.append(row["label"])
            self.assertEqual(selectable, [expected, "Practice"], (phase, week))


if __name__ == "__main__":
    unittest.main()
