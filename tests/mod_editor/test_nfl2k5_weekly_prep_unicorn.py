"""Bounded retail instructions and real signed Franchise copies, no game boot."""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_save as fs, nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_weekly_prep as patch, nfl2k5_weekly_prep_save as prep
from tests.nfl2k5_weekly_prep_fixture import Machine, HAVE_UC, retail_bytes, signed_save


@unittest.skipUnless(HAVE_UC, "Unicorn is absent; bounded native instruction evidence requires it")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail, cls.save = retail_bytes(), signed_save()
        cls.patched, _ = patch.apply(cls.retail)

    def machine(self, *, cpu=True, remember=True, retail=False):
        payload = self.retail if retail else self.patched if cpu and remember else patch.apply(self.retail, cpu=cpu, remember=remember)[0]
        return Machine(payload, self.save)

    def route_counter(self, m):
        calls = []
        m.leaf(0x2AC4E0, lambda: (calls.append(m.reg("ECX")), m.ret()),
               reason="Count dispatch only; separate tests execute the full native forward/inverse kernels")
        return calls

    def test_db_filter_includes_both_safeties_and_no_unrelated_position(self):
        for retail in (True, False):
            m = self.machine(retail=retail)
            player = m.players(0)[0]
            for position in range(17):
                m.uc.mem_write(player + 0x35, bytes([position]))
                for activity in range(75, 82):
                    self.assertEqual(bool(m.eligible(player, activity)), position in ((4,) if retail else (4, 5, 6)),
                                     (retail, prep.POSITIONS[position], activity))

    def test_all_position_drills_have_a_complete_position_mapping(self):
        m = self.machine()
        player = m.players(0)[0]
        groups = {35: (0,), 82: (1,), 86: (2,), 59: (3,), 75: (4, 5, 6),
                  39: (7,), 44: (8,), 54: (9,), 69: (10, 11), 49: (12, 13, 14), 64: (15, 16)}
        for position in range(17):
            m.uc.mem_write(player + 0x35, bytes([position]))
            for activity, members in groups.items():
                self.assertEqual(bool(m.eligible(player, activity)), position in members, (position, activity))

    def test_default_plan_fits_the_native_weighted_daily_budget(self):
        m = self.machine()
        m.plan(0, prep.default_plan())
        for day in range(7):
            spent = m.call(0x2AAA10, ecx=0, edx=day)
            allowed = m.call(0x2AA850, ecx=0, edx=day)
            self.assertEqual((spent, allowed), (36, 40) if day < 5 else (0, 0))

    def test_starter_and_backup_full_drills_partition_every_position(self):
        m = self.machine()
        player = m.players(0)[0]
        for position in range(17):
            m.uc.mem_write(player + 0x35, bytes([position]))
            for rank in range(8):
                for side in (0, 1, 2, 7):
                    m.uc.mem_write(player + 0x28, struct.pack("<H", rank << 10 | side << 13))
                    selected = [m.eligible(player, a) for a in (93, 96, 99)]
                    paired = m.call(0xC40F0, ecx=m.team(0), edx=position) == 0
                    effective = min(rank, side) if paired else rank
                    self.assertEqual(selected, [int(effective == 0), int(effective == 1), int(effective > 1)],
                                     (prep.POSITIONS[position], rank, side))

    def test_native_te_and_back_progression_match_on_identical_inputs(self):
        outcomes = []
        for position, base in ((7, 39), (8, 44), (9, 54)):
            m = self.machine()
            team, player = m.team(0), m.players(0)[0]
            m.uc.mem_write(team + 0x11C, b"\x01")
            m.uc.mem_write(player + 0x35, bytes([position]) + bytes([60]) * 28)
            m.uc.mem_write(player + 0x28, bytes(2))
            rows = [prep.encode(activity=base+i, hours=2, day=i) for i in range(5)]
            m.plan(0, rows + [prep.EMPTY] * (500-len(rows)))
            m.snapshot(0)
            m.call(0x2AC4E0, ecx=0, budget=3000000)
            outcomes.append(m.ratings(0))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0], outcomes[2])
        self.assertNotEqual(outcomes[0][0], bytes([60]) * 28)

    def test_cpu_runs_the_same_full_roster_routine_as_human_and_cleanup(self):
        outcomes = []
        for cpu in (False, True):
            m = self.machine()
            # The f0 evidence has all 32 human flags. Author only this flag in
            # RAM to compare native human and CPU treatment of the same club.
            m.put(0xE5775C, int(not cpu))
            m.put(0xE3C0A0, m.team(0))
            m.plan(0, prep.default_plan())
            m.snapshot(0)
            m.put(prep.STATE_VA, 2)
            before = m.ratings(0)
            m.call(0x2AC4E0, ecx=0, budget=50000000)
            forward = m.ratings(0)
            self.assertNotEqual(forward, before)
            m.call(0x2AC520, ecx=0, budget=50000000)
            self.assertEqual(m.get(prep.STATE_VA), 0)
            self.assertEqual(m.plan(0), prep.default_plan())
            outcomes.append((forward, m.ratings(0)))
        # Includes the native clamp behavior of this fixture's >100 ratings.
        self.assertEqual(outcomes[0], outcomes[1])

    def test_retail_cpu_is_skipped_and_off_preserves_that_policy(self):
        for retail, enabled in ((True, True), (False, False)):
            m = self.machine(retail=retail, cpu=enabled)
            m.put(0xE5775C, 0)
            m.plan(0, prep.default_plan())
            m.snapshot(0)
            before = m.ratings(0)
            m.call(0x2AC4E0, ecx=0, budget=1000000)
            self.assertEqual(m.ratings(0), before)

    def test_every_cpu_club_prepares_once_each_game_week_including_next_week(self):
        m = self.machine()
        calls = self.route_counter(m)
        m.uc.mem_write(0xE5775C, bytes(32*4))
        for week in (0, 1):
            for team in range(0, 32, 2):
                m.game(team, team+1, week=week, slot=team//2)
                m.call("before_sim")
                m.call("before_sim")
                self.assertEqual(m.plan(team), prep.default_plan())
                self.assertEqual(m.plan(team+1), prep.default_plan())
            self.assertEqual(calls, list(range(32)) * (week+1))
            for team in range(32):
                m.call("remember_clear", ecx=team, edx=0, budget=100000)

    def test_real_played_and_simulated_callers_prepare_before_game_setup(self):
        for entry in (0xC73B0, 0xC7A20):
            m = self.machine()
            m.game(0, 1, week=3, slot=1)
            m.put(0xE5775C, 0)
            m.put(0xE57760, 0)
            calls = self.route_counter(m)
            if entry == 0xC73B0:
                m.leaf(0x64B80, lambda: m.ret(), reason="Controller setup outside weekly prep")
            else:
                m.leaf(0x177990, lambda: m.ret(pop=4), reason="Simulation progress display outside weekly prep")
                m.leaf(0x14EC60, lambda: m.ret(), reason="Simulation progress display outside weekly prep")
            m.call(entry, ecx=3, edx=1, args=(0,),
                   stop=0x134045 if entry == 0xC73B0 else 0x10B9C0, budget=3000000)
            self.assertEqual(calls, [0, 1])
            self.assertEqual((m.get(0xE576B4), m.get(0xE576BC)), (3, 1))

    def test_seed_uses_actual_team_in_forward_and_inverse(self):
        m = self.machine()
        team = m.team(1)
        player = m.players(1)[0]
        m.uc.mem_write(team + 0x11C, b"\x01")
        m.plan(1, prep.default_plan())
        m.snapshot(1)
        m.put(0xE3C0A0, m.team(0))
        m.put(prep.SEED_VA, 10)
        m.put(prep.SEED_VA + 4, 900)
        jersey = (m.get(player + 0x20) >> 3) & 127
        seeds = []
        for callsite in (0x2AB9B5, 0x2ABF25):
            m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: seeds.append(m.reg("EDX")),
                          begin=callsite, end=callsite)
        for entry in (0x2AB8F0, 0x2ABE60):
            seeds.clear()
            m.call(entry, ecx=player, edx=team, args=(0,), budget=4000000)
            self.assertEqual(seeds, [900 + jersey])

    def test_human_remember_waits_for_nonempty_plan_and_respects_off(self):
        for enabled in (False, True):
            m = self.machine(remember=enabled)
            calls = self.route_counter(m)
            m.game()
            m.call("before_sim")
            self.assertEqual(calls, [])
            m.plan(0, prep.default_plan())
            m.call("before_sim")
            self.assertEqual(calls, [0] if enabled else [])
            m.call("before_sim")
            self.assertEqual(calls, [0] if enabled else [])

    def test_master_mode_completed_invalid_and_unknown_state_guards(self):
        for va, value in ((0xE6011C, 0), (0xE576A0, 1), (0xE576AC, 33),
                          (0xE576A4, 5), (0xE576B4, 22), (0xE576BC, 17)):
            m = self.machine()
            calls = self.route_counter(m)
            m.game()
            m.plan(0, prep.default_plan())
            m.put(va, value)
            m.call("before_sim")
            self.assertEqual(calls, [], hex(va))
        m = self.machine()
        calls = self.route_counter(m)
        for kind in ("complete", "bad team", "self", "state", "bad row", "bad roster"):
            m.game()
            m.plan(0, prep.default_plan())
            m.put(prep.STATE_VA, 0)
            if kind == "complete": m.uc.mem_write(0xE57C40, b"\x03")
            if kind == "bad team": m.uc.mem_write(0xE57C41, b"\x20")
            if kind == "self": m.uc.mem_write(0xE57C42, b"\x00")
            if kind == "state": m.put(prep.STATE_VA, 0xFFFFFFFF)
            if kind == "bad row": m.put(prep.PLAN_VA, 0x010001FF)
            if kind == "bad roster": m.uc.mem_write(m.team(0) + 0x11C, b"\x42")
            m.call("before_sim")
            self.assertEqual(calls, [], kind)

    def test_season_cleanup_keeps_valid_plan_but_fresh_franchise_still_wipes(self):
        m = self.machine()
        rows = [prep.encode(activity=54, hours=2, day=3)] + [prep.EMPTY] * 499
        m.plan(0, rows)
        m.call("remember_clear", ecx=0, edx=1, budget=100000)
        self.assertEqual(m.plan(0)[0], rows[0] | 0x80000000)
        self.assertEqual(m.get(prep.STATE_VA), 0)
        m.call(0x2AB840, ecx=0, edx=1, budget=100000)
        self.assertFalse(prep.validate_plan(m.plan(0)))
        # This call remains retail and is the actual fresh-franchise path.
        image = patch.XbeImage(self.patched)
        self.assertEqual(image.read(0x13EE47, 5), patch.XbeImage(self.retail).read(0x13EE47, 5))

    def test_native_cleaner_drops_departed_player_targets_and_off_wipes_new_season(self):
        for enabled in (False, True):
            m = self.machine(remember=enabled)
            primary = (m.players(1)[0] - m.get(m.root + 4)) // 84
            rows = [prep.encode(activity=1, target=primary+18), prep.encode(activity=54)] + [prep.EMPTY]*498
            m.plan(0, rows)
            m.call("remember_clear", ecx=0, edx=1, budget=100000)
            active = prep.validate_plan(m.plan(0))
            self.assertEqual([r["activity"] for r in active], [54] if enabled else [])

    def test_disabled_cpu_can_still_remove_an_already_applied_plan(self):
        m = self.machine(cpu=False)
        m.put(0xE5775C, 0)
        calls = []
        m.leaf(0x2ABE60, lambda: (calls.append(m.reg("ECX")), m.ret(pop=4)),
               reason="Count inverse admission with CPU option off; full inverse tested separately")
        m.put(prep.STATE_VA, 2)
        m.call(0x2AC520, ecx=0, budget=1000000)
        self.assertEqual(calls, m.players(0))

    def test_both_entry_wrappers_preserve_registers_and_float_state(self):
        for entry in ("before_sim", "before_play"):
            m = self.machine()
            m.game()
            m.plan(0, prep.default_plan())
            def disturb():
                m.uc.reg_write(m.x.UC_X86_REG_XMM0, 123)
                m.uc.reg_write(m.x.UC_X86_REG_FPCW, 0x27F)
                m.reg("ECX", 123)
                m.reg("EDX", 456)
                m.ret()
            m.leaf(0x2AC4E0, disturb, reason="Deliberately clobber caller scratch and FP state to test wrapper preservation")
            xmm = 0x123456789ABCDEF00123456789ABCDEF
            m.uc.reg_write(m.x.UC_X86_REG_XMM0, xmm)
            m.put(0xE60184, 77)
            m.put(0xE576C8, 88)
            value = m.call(entry, ecx=101, edx=202, stop=0x134045 if entry == "before_play" else None)
            self.assertEqual(value, 77 if entry == "before_play" else 88)
            self.assertEqual(m.reg("ECX"), 101)
            self.assertEqual(m.reg("EDX"), 202)
            self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_XMM0), xmm)
            self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_FPCW), 0x37F)
            for reg, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333), ("EBP", 0x44444444)):
                self.assertEqual(m.reg(reg), value)

    def test_native_serializers_and_cold_signed_reload_keep_plan_state_seed(self):
        m = self.machine()
        m.plan(0, prep.default_plan())
        m.put(prep.STATE_VA, 2)
        m.put(prep.SEED_VA, 0x12345678)
        output = m.ARENA + 0x100000
        m.uc.mem_write(output, self.save)
        m.put(0xB72808, 0x91000)
        m.put(0xB7280C, 0x91000)
        for native, offset in ((0xE2E10, 0), (0xC1F90, fs.ARENA_WRAPPER),
                               (0xC5310, fs.SEASON_BLOCK), (0x2D0790, fs.FRONT_OFFICE_BLOCK)):
            m.call(native, ecx=output+offset, budget=100000000)
        saved = bytes(m.uc.mem_read(output, len(self.save)))
        self.assertTrue(rr.verify_extra(saved, rr.sign_save(saved)))
        self.assertEqual(prep.read_plan(saved, 0)["seed"], 0x12345678)
        cold = Machine(self.patched, saved)
        self.assertEqual(cold.plan(0), prep.default_plan())
        self.assertEqual(cold.get(prep.STATE_VA), 2)
        self.assertEqual(cold.get(prep.SEED_VA), 0x12345678)
        self.assertEqual(cold.uc.mem_read(prep.SNAPSHOT_VA, 195), m.uc.mem_read(prep.SNAPSHOT_VA, 195))
        calls = self.route_counter(cold)
        cold.game()
        cold.call("before_sim")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
