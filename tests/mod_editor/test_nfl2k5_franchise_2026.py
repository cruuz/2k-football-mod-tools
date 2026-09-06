"""Standalone host, ownership, counter codec and dormant-owner proofs. No game witness."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_2026 as f
from mod_editor.core import nfl2k5_franchise_save as fs, nfl2k5_practice_squad as ps
from tests.mod_editor.test_nfl2k5_roster_records import league_body, synthetic_save_v0
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise, F1

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'


def fixture():
    tail = synthetic_franchise(year_field=0)[fs.ARENA_END:]
    save = fs.FranchiseSave(synthetic_save_v0(league_body(65), suffix=tail), base_year=2026)
    candidate = bytearray(save.buffer)
    for team in (0, 1):
        off = save.team_offset(team)
        candidate[off:off + 500] = ps.repack_team(candidate[off:off + 500],
            list(range(team * 65, team * 65 + 53)), list(range(team * 65 + 53, team * 65 + 65)),
            team_offset=off, player_pool_offset=save.player_table[1], player_count=save.player_table[0], mark=True)
    save.buffer = bytearray(ps.recompute_salary(ps.recompute_salary(bytes(candidate), 0), 1))
    save._validate_ownership()
    return save


def candidates(ols=8):
    return [f.Candidate(i, 12 + i % 3 if i < ols else (i - ols) % 12, i % 5, 99 - i) for i in range(53)]


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.s = f.RuleState.new(2026, 2479)

    def refuses(self, call):
        before = bytes(self.s.raw)
        with self.assertRaises(f.Franchise2026Error):
            call()
        self.assertEqual(bytes(self.s.raw), before)

    def games(self, team=0, first=0, day=0, n=4):
        for k in range(first, first + n):
            self.s.complete_game(team, k, day + (k - first + 1) * 7)

    def test_r1_47_or_48_eight_primary_ol_and_no_source_changes(self):
        for ols in (0, 7, 8, 9):
            players = candidates(ols)
            before = tuple(players)
            picked = f.select_game_day(players)
            self.assertEqual(len(picked), 48 if ols >= 8 else 47)
            self.assertEqual(len(set(picked)), len(picked))
            self.assertEqual(tuple(players), before)
            if ols >= 8:
                self.assertGreaterEqual(sum(players[i].position in f.OL for i in picked), 8)
        players = candidates(8)
        players[7] = f.Candidate(7, 14, available=False)
        self.assertEqual(len(f.select_game_day(players)), 47)
        self.assertNotIn(7, f.select_game_day(players))

    def test_selection_covers_positions_special_roles_previous_and_two_elevations(self):
        active = candidates(7)
        reserves = [f.Candidate(53, 12), f.Candidate(54, 3)]
        picked = f.select_game_day(active, reserves, (53, 54), previous=(52, 51), special=(50,))
        self.assertEqual(len(picked), 48)
        self.assertIn(53, picked)
        self.assertIn(50, picked)
        self.assertIn(52, picked)
        self.assertNotIn(53, f.select_game_day(active, reserves))
        for args in ((active, reserves, (53, 54, 55)), (active, reserves, (53, 53)),
                     (active, reserves, (0,)), (active, [active[0]], ())):
            with self.assertRaises(f.Franchise2026Error): f.select_game_day(*args)
        with self.assertRaisesRegex(f.Franchise2026Error, 'eleven'):
            f.select_game_day(active[:10])

    def test_r2_third_allowed_fourth_refused_postseason_and_exact_retry(self):
        for key in range(3):
            self.assertTrue(self.s.commit_game(0, key, key * 7, [53, 54]))
            before = bytes(self.s.raw)
            self.assertFalse(self.s.commit_game(0, key, key * 7, [53, 54]))
            self.assertEqual(bytes(self.s.raw), before)
            self.refuses(lambda: self.s.commit_game(0, key, key * 7, [54, 53]))
            self.s.complete_game(0, key, key * 7)
        self.assertEqual(self.s.history(53), (3, 0))
        self.refuses(lambda: self.s.commit_game(0, 4, 28, [53]))
        self.refuses(lambda: self.s.commit_game(0, 4, 28, [53], postseason=True))
        self.s.qualify(0)
        self.s.commit_game(0, 512, 130, [53], postseason=True)
        self.assertEqual(self.s.history(53), (3, 0))
        self.s.complete_game(0, 512, 130, phase=9)
        self.assertEqual(self.s.team(0)[5:8], [f.EMPTY] * 3)

    def test_r3_bye_preseason_duplicate_and_old_result_do_not_count(self):
        self.s.enter_ir(0, 1, 0)
        self.s.advance_day(0, 14)  # two weeks and a bye are zero games
        self.refuses(lambda: self.s.designate(0, 1, 14))
        self.refuses(lambda: self.s.complete_game(0, 0, 14, phase=7))
        self.s.complete_game(0, 0, 14)
        self.assertFalse(self.s.complete_game(0, 0, 14))
        self.games(first=1, day=14, n=2)
        self.refuses(lambda: self.s.complete_game(0, 0, 14))
        self.refuses(lambda: self.s.designate(0, 1, 28))
        self.s.complete_game(0, 3, 35)
        self.s.designate(0, 1, 35)
        self.assertEqual(self.s.team(0)[1:3], [4, 1])

    def test_r3_r5_medical_room_practice_expiry_and_ir_compaction(self):
        for p in (1, 2, 3, 4, 5): self.s.enter_ir(0, p, 0)
        self.refuses(lambda: self.s.enter_ir(0, 6, 0))
        self.games()
        self.s.designate(0, 3, 28)
        self.assertFalse(self.s.designate(0, 3, 29))
        self.refuses(lambda: self.s.activate(0, 3, 28, medically_clear=False, active_count=52, reserve_count=12))
        self.refuses(lambda: self.s.activate(0, 3, 28, medically_clear=True, active_count=53, reserve_count=12))
        self.s.activate(0, 3, 48, medically_clear=True, active_count=52, reserve_count=12)
        self.assertEqual([e.player for e in self.s.ir(0)], [1, 2, 4, 5, f.EMPTY])
        self.assertEqual(self.s.history(3), (0, 1))
        self.s.designate(0, 1, 48)
        self.refuses(lambda: self.s.activate(0, 1, 69, medically_clear=True, active_count=52, reserve_count=0))
        self.s.advance_day(0, 69)
        self.assertTrue(self.s.ir(0)[0].flags & f.EXPIRED)
        self.refuses(lambda: self.s.designate(0, 1, 70))
        self.assertEqual(self.s.team(0)[2], 2)  # expiry does not refund designation

    def test_r4_two_cutdown_exceptions_charged_at_entry_and_legacy_ineligible(self):
        for p in (1, 2): self.s.enter_ir(0, p, 0, cutdown=True)
        self.refuses(lambda: self.s.enter_ir(0, 3, 0, cutdown=True))
        self.s.enter_ir(0, 3, 0, post_cutdown=False)
        self.s.enter_ir(0, 4, 0, legacy=True)
        self.games()
        self.s.designate(0, 1, 28)
        self.assertEqual(self.s.team(0)[2:4], [2, 2])
        for p in (3, 4): self.refuses(lambda p=p: self.s.designate(0, p, 28))

    def test_r3_eight_designations_plus_two_qualifying_postseason_and_player_twice(self):
        for p in range(1, 9):
            v = self.s.team(0)
            self.s.enter_ir(0, p, v[8])
            # Independent fixtures place at game ordinal 0 to avoid requiring 32 games.
            entry = self.s.ir(0)[0]
            self.s._ir(0, [f.IRRecord(p, 0, entry.flags, 0, entry.entry_day)])
            if p == 1: self.games()
            self.s.designate(0, p, 28)
            self.s.activate(0, p, 28, medically_clear=True, active_count=52, reserve_count=0)
        self.s.enter_ir(0, 9, 28)
        self.games(first=4, day=28)
        self.refuses(lambda: self.s.designate(0, 9, 56))
        self.s.qualify(0)
        self.s.designate(0, 9, 56, postseason=True)
        self.s.activate(0, 9, 56, medically_clear=True, active_count=52, reserve_count=0)
        self.s.enter_ir(0, 1, 56)
        self.games(first=8, day=56)
        self.s.designate(0, 1, 84, postseason=True)
        self.s.activate(0, 1, 84, medically_clear=True, active_count=52, reserve_count=0)
        self.assertEqual(self.s.history(1), (0, 2))
        self.assertEqual(self.s.team(0)[2], 10)
        self.s.enter_ir(0, 1, 84)
        self.games(first=12, day=84)
        self.refuses(lambda: self.s.designate(0, 1, 112, postseason=True))

    def test_rollover_and_pool_remap_are_explicit_and_preserve_identity(self):
        self.s.commit_game(0, 1, 0, [1, 2])
        self.refuses(lambda: self.s.rollover(2027))
        self.s.complete_game(0, 1, 0)
        mapping = list(range(self.s.players))
        mapping[1], mapping[2], mapping[3] = 2, 3, None
        self.s.remap(mapping, self.s.players)
        self.assertEqual(self.s.history(2), (1, 0))
        self.assertEqual(self.s.history(3), (1, 0))
        self.assertEqual(self.s.history(1), (0, 0))
        self.assertTrue(self.s.rollover(2027))
        self.assertFalse(self.s.rollover(2027))
        self.assertEqual(self.s.history(2), (0, 0))
        self.s.enter_ir(0, 2, 0)
        mapping[2] = None
        self.refuses(lambda: self.s.remap(mapping, self.s.players))

    def test_counter_corruption_and_extents_refuse(self):
        for off in (0, 4, 16, f.USED_END, f.TEAM_BASE + 15, f.HISTORY_BASE + 2000):
            raw = bytearray(self.s.raw); raw[off] ^= 0x80
            with self.subTest(off=off), self.assertRaises(f.Franchise2026Error): f.RuleState(raw)
        for raw in (b'', self.s.raw[:-1], self.s.raw + b'\0'):
            with self.assertRaises(f.Franchise2026Error): f.RuleState(raw)

    def test_r4_exact_2026_cutdown_and_deadline_boundary(self):
        self.assertFalse(f.cutdown_due(dt.date(2026, 8, 30), 1079))
        self.assertTrue(f.cutdown_due(dt.date(2026, 8, 30), 1080))
        self.assertTrue(f.trades_open(dt.date(2026, 11, 10), 959))
        self.assertFalse(f.trades_open(dt.date(2026, 11, 10), 960))
        self.assertTrue(f.trades_open(dt.date(2026, 11, 11), deadline_enabled=False))
        with self.assertRaises(f.Franchise2026Error): f.cutdown_due(dt.date(2027, 8, 30))


class HostTests(unittest.TestCase):
    def test_no_native_save_bytes_borrowed_and_companion_bound_to_exact_save(self):
        save = fixture(); before = save.to_bytes(); session = save.franchise_2026_session()
        companion = session.export()
        self.assertEqual(len(companion), f.COMPANION_SIZE)
        self.assertEqual(save.to_bytes(), before)
        self.assertEqual(save.import_franchise_2026_counters(companion).raw, session.state.raw)
        with self.assertRaises(f.Franchise2026Error): save.import_franchise_2026_counters(companion[:-1])
        bad = bytearray(companion); bad[-1] ^= 1
        with self.assertRaises(f.Franchise2026Error): save.import_franchise_2026_counters(bad)
        save.buffer[-1] ^= 1
        with self.assertRaisesRegex(f.Franchise2026Error, 'different save'): save.import_franchise_2026_counters(companion)
        with self.assertRaisesRegex(f.Franchise2026Error, 'outside'): session.export()

    def test_r1_r2_prepare_cancel_accept_reload_and_contract_ownership_unchanged(self):
        save = fixture(); session = save.franchise_2026_session(); before = save.to_bytes()
        proposal = session.prepare(0, 1, 0, elevations=(53, 54))
        self.assertEqual(session.state.history(53), (0, 0))  # Cancel costs nothing
        self.assertEqual(save.to_bytes(), before)
        self.assertTrue(session.accept(proposal))
        self.assertFalse(session.accept(proposal))
        session = save.franchise_2026_session(session.export())
        self.assertFalse(session.accept(proposal))
        self.assertEqual(session.state.history(53), (1, 0))
        self.assertEqual(save.to_bytes(), before)
        self.assertEqual(len(save.team_player_indices(0)), 53)
        self.assertEqual(ps.validate_save(save.to_bytes())[0], tuple(range(53, 65)))
        session.advance(0, 0, game_key=1)
        self.assertEqual(session.state.team(0)[5:8], [f.EMPTY] * 3)

    def test_host_ir_with_reserves_compacts_middle_preserves_injury_cap_and_failure_atomic(self):
        save = fixture(); session = save.franchise_2026_session()
        for p in range(5): session.place_ir(0, p, 0)
        self.assertEqual([e.player_index for e in save.injured_reserve()], list(range(5)))
        reserves = ps.validate_save(save.to_bytes())[0]
        for k in range(4): session.advance(0, 7 * (k + 1), game_key=k)
        session.designate(0, 2, 28)
        # Injecting failure in the existing candidate writer leaves both objects exact.
        before, counters = save.to_bytes(), bytes(session.state.raw)
        with mock.patch.object(fs.FranchiseSave, 'activate_from_injured_reserve', side_effect=ValueError('injected')):
            with self.assertRaisesRegex(ValueError, 'injected'): session.activate_ir(0, 2, 28)
        self.assertEqual(save.to_bytes(), before); self.assertEqual(bytes(session.state.raw), counters)
        off = save.player_offset(2); player_before = bytes(save.buffer[off:off + 84])
        salary = save.team_salary(0)
        session.activate_ir(0, 2, 28)
        self.assertEqual([e.player_index for e in save.injured_reserve()], [0, 1, 3, 4])
        self.assertEqual([e.slot for e in save.injured_reserve()], [0, 1, 2, 3])
        self.assertEqual(bytes(save.buffer[off:off + 84]), player_before)
        self.assertEqual(ps.validate_save(save.to_bytes())[0], reserves)
        self.assertEqual(save.team_salary(0), salary)
        self.assertEqual(session.state.history(2), (0, 1))
        self.assertEqual(save.import_franchise_2026_counters(session.export()).raw, session.state.raw)

    def test_legacy_host_activation_preserves_packed_injury_and_compacts_fifth_slot(self):
        save = fixture()
        for p in range(5): save.place_on_injured_reserve(0, p)
        off = save.player_offset(2)
        save.buffer[off + 0x28] = 0x21
        save.activate_from_injured_reserve(0, 2)
        self.assertEqual(save.buffer[off + 0x28], 0x21)
        self.assertEqual([e.slot for e in save.injured_reserve()], [0, 1, 2, 3])
        save.place_on_injured_reserve(0, 5)
        self.assertEqual([e.slot for e in save.injured_reserve()], [0, 1, 2, 3, 4])

    def test_modern_ir_keeps_medical_state_and_repairs_special_role_indices(self):
        save = fixture()
        player = save.player_offset(2)
        injury = struct.unpack_from('<I', save.buffer, player + 0x24)[0] | 0x10000000
        struct.pack_into('<I', save.buffer, player + 0x24, injury)
        save.buffer[player + 0x28] = 0xee  # Legitimate packed bits are not a modern IR marker.
        roles = save.team_offset(0) + 0x194
        save.buffer[roles:roles + 6] = bytes((0, 2, 3, 52, 0x80, 0xff))
        session = save.franchise_2026_session()
        session.place_ir(0, 2, 0)
        self.assertEqual(save.buffer[roles:roles + 6], bytes((0, 0xff, 2, 51, 0x80, 0xff)))
        self.assertEqual(struct.unpack_from('<I', save.buffer, player + 0x24)[0], injury)
        self.assertEqual(save.buffer[player + 0x28], 0xee)
        for k in range(4): session.advance(0, 7 * (k + 1), game_key=k)
        session.designate(0, 2, 28)
        before, counters = save.to_bytes(), bytes(session.state.raw)
        with self.assertRaises(f.Franchise2026Error): session.activate_ir(0, 2, 28)
        self.assertEqual(save.to_bytes(), before)
        self.assertEqual(bytes(session.state.raw), counters)

    @unittest.skipUnless(F1.is_file(), 'private f1 franchise save absent; legacy migration proof unavailable')
    def test_real_legacy_save_migrates_ir_as_season_ending_without_mutation(self):
        raw = F1.read_bytes(); save = fs.FranchiseSave(raw)
        session = save.franchise_2026_session()
        self.assertEqual(save.to_bytes(), raw)
        for entry in save.injured_reserve():
            ir = next(e for e in session.state.ir(entry.team) if e.player == entry.player_index)
            self.assertEqual(ir.flags, f.LEGACY)
        self.assertEqual(save.import_franchise_2026_counters(session.export()).raw, session.state.raw)


@unittest.skipUnless(XBE.is_file(), 'USA retail default.xbe absent; allocator installation proof unavailable')
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('XBE is not the pinned USA retail executable')
        cls.patched, cls.receipt = f.apply(cls.retail)

    def test_replay_receipt_dormant_feature_and_runtime_refusal(self):
        self.assertEqual(f.status(self.retail), 'retail')
        self.assertEqual(f.status(self.patched), 'applied')
        self.assertEqual(f.apply(self.patched)[0], self.patched)
        self.assertEqual(f.apply(self.patched)[1]['changed_bytes'], 0)
        self.assertFalse(self.receipt['runtime_enforced'])
        self.assertEqual(self.receipt['native_hooks'], [])
        with self.assertRaisesRegex(f.Franchise2026Error, 'unavailable'): f.require_runtime_ready()
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        old, new = XbeImage(self.retail), XbeImage(self.patched)
        for va, size in ((0x61730, 0xab), (0xc5280, 0x79), (0x246ff0, 121), (0x27dbc0, 788), (0x2d09ec, 5)):
            self.assertEqual(old.read(va, size), new.read(va, size))

    def test_foreign_sealed_code_missing_union_and_dirty_data_refuse(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        allocated, _ = space.apply(self.retail, f.REQUESTS)
        foreign, _ = space.install_code(allocated, f.OWNER, b'\x90' * f.CODE_SIZE)
        self.assertEqual(f.status(foreign), 'foreign')
        with self.assertRaises(ValueError): f.apply(foreign)
        other, _ = space.apply(self.retail, [('other_test', 'code', 16, 16)], scaleout=True)
        with self.assertRaisesRegex(ValueError, 'initial allocator union'): f.apply(other)
        bad = bytearray(self.patched)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        data = f._inspect(self.patched)[1]['data']
        bad[XbeImage(self.patched).offset(data['va'])] = 1
        for s in _sections(bad): bad[s.header_offset + 36:s.header_offset + 56] = section_digest(bad, s)
        self.assertEqual(f.status(bad), 'foreign')
        with self.assertRaises(ValueError): f.apply(bad)
        for raw in (b'', b'XBEH', bytes(1024)):
            self.assertEqual(f.status(raw), 'foreign')
            with self.assertRaises(ValueError): f.apply(raw)

    def test_manifest_recorder_and_actual_request_budget(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        from mod_editor.core import nfl2k5_xbe_space as space
        r = Recorder(self.retail)
        r.observe(f, 'apply', self.retail, self.patched, self.receipt)
        self.assertEqual(r.steps[-1]['owner'], f.OWNER)
        own = [s for s in space.reservations(self.patched) if s['owner'] == f.OWNER]
        self.assertEqual(sorted(s['size'] for s in own), sorted([f.CODE_SIZE, f.DATA_SIZE]))
        requests = json.loads((ROOT / 'tests/fixtures/nfl2k5_allocator_beta62_requests.json').read_text())
        self.assertEqual([tuple(row) for row in requests if row[0] == f.OWNER], list(f.REQUESTS))
        space.plan(requests)

    def test_runtime_assessment_pins_real_consumers_and_refuses_drift(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        result = f.runtime_assessment(self.retail)
        self.assertFalse(result['runtime_enforced'])
        self.assertEqual(result['changed_bytes'], 0)
        self.assertEqual(len(result['pins']), len(f.RUNTIME_PINS))
        bad = bytearray(self.retail)
        bad[XbeImage(bad).offset(0xc5280)] ^= 1
        with self.assertRaises(ValueError): f.runtime_assessment(bad)


if __name__ == '__main__':
    unittest.main()
