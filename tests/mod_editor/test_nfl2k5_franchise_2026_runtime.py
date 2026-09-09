"""Current save owners and native franchise boundary counterexamples.

The CPU fixtures execute installed code, not a console boot or played week.
Device/heap services use the existing MyCareer fixture's declared seams.
No save codec, roster projection or result identity resolver is replaced.
"""
from pathlib import Path
import hashlib
import itertools
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_2026 as f
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_roster_arena as arena
from mod_editor.core import nfl2k5_roster_arena_growth as growth
from mod_editor.core import nfl2k5_my_career_save as career_save
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_save_rost as codec
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_practice_reserves as pr
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.mod_editor.test_nfl2k5_franchise_2026 import fixture, XBE
from tests.mod_editor.test_nfl2k5_my_career_inline import block_for
from tests.nfl2k5_my_career_fixture import HAVE_UC
from tests.nfl2k5_my_career_mode_fixture import Machine


def week_save(*, grown=False, reserves=16):
    """Bounded synthetic 32-club save, 53 active and up to 17 reserves.

    Only the first two clubs have players. Relocate the synthetic team's table
    into a known empty fixture span; production migrations use arena.migrate.
    """
    source = fixture().to_bytes()
    doc = codec.decode(source)
    out = bytearray(source)
    table = doc.layout.root + 0x80000
    assert not any(out[table:table + 32 * 500])
    for team in doc.teams:
        dest = table + 500 * team.index
        out[dest:dest + 500] = source[team.offset:team.offset + 500]
        for field in arena.TEAM_POINTERS:
            target = doc.rel(team.offset + field)
            struct.pack_into('<i', out, dest + field, 0 if target is None else target - dest - field + 1)
    for team in range(32):
        struct.pack_into('<H', out, table + team * 500 + 0x118, team)
    struct.pack_into('<Ii', out, doc.layout.root + 24, 32, table - (doc.layout.root + 28) + 1)
    out[fs.SEASON_BLOCK + fs.S_YEAR] = 22  # native 2004 + 22 = 2026
    # Seven/eight OL coverage is varied in the native projection test.
    non_ol = tuple(position for position in range(17) if position not in f.OL)
    for player in doc.players:
        if player.pool == 'primary':
            n = player.index % 65
            out[player.offset + 0x35] = 12 + n % 3 if n < 8 else non_ol[(n - 8) % len(non_ol)]
    if not grown:
        return bytes(out)
    out = bytearray(arena.migrate(bytes(out), eligible_team_mask=int(reserves == 17))[0])
    save = fs.FranchiseSave(out)
    doc = codec.decode(out)
    squads = save._validate_ownership()
    active0, active1 = save.team_player_indices(0), save.team_player_indices(1)
    extra = reserves - len(squads[0])
    arena.repack(out, doc, 1, active1[:-extra], squads[1])
    arena.repack(out, doc, 0, active0, squads[0] + tuple(active1[-extra:]))
    ps.validate_save(out)
    return bytes(out)


class SaveOwnershipTests(unittest.TestCase):
    def test_all_four_save_shapes_are_read_only_and_grant_no_ledger(self):
        for grown in (False, True):
            source = week_save(grown=grown)
            for with_career in (False, True):
                raw = source + block_for(source) if with_career else source
                before = hashlib.sha256(raw).digest()
                result = f.save_ownership_assessment(raw)
                self.assertEqual(hashlib.sha256(raw).digest(), before)
                self.assertEqual(result['save_bytes'], 720044 + 4096 * grown + 128 * with_career)
                self.assertEqual(result['arena_version'], int(grown))
                self.assertEqual(result['career_footer_present'], with_career)
                self.assertEqual(result['reserve_counts']['0'], 16 if grown else 12)
                self.assertEqual(result['native_ledger_bytes_owned'], 0)
                self.assertEqual(result['changed_bytes'], 0)
                self.assertFalse(result['runtime_enforced'])
                self.assertFalse(result['signature_verified'])

    def test_guardian_owns_bit_five_and_no_record_bit_is_granted(self):
        flags = f.persistence_contract()['player_flags']
        self.assertEqual(flags['occupied_mask'], 0x3f)
        self.assertEqual(flags['unassigned_mask'], 0xc0)
        self.assertEqual(flags['owned_ledger_mask'], 0)
        self.assertLess(flags['unassigned_mask'].bit_count(), flags['required_history_bits'])

    def test_resealed_reserved_footer_bytes_are_not_spare_storage(self):
        source = week_save()
        block = block_for(source)
        for at in (82, 83, *range(88, 128)):
            bad = bytearray(block)
            bad[at] = 1
            with self.subTest(offset=at), self.assertRaisesRegex(ValueError, 'reserved career bytes'):
                f.save_ownership_assessment(source + career_save.seal(bad))

    def test_corrupt_identity_overflow_auxiliary_and_appended_ledgers_refuse(self):
        source = week_save(grown=True)
        for n in (1, f.DATA_SIZE, f.COMPANION_SIZE):
            with self.subTest(extra=n), self.assertRaises(ValueError):
                f.save_ownership_assessment(source + bytes(n))
        bad = bytearray(source)
        bad[fs.ARENA_ROOT + arena.BLOCK_OFFSET + 32] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            f.save_ownership_assessment(bad)
        bad = bytearray(source)
        struct.pack_into('<I', bad, 0x2e8, 673)
        with self.assertRaisesRegex(ValueError, 'auxiliary'):
            f.save_ownership_assessment(bad)
        block = bytearray(block_for(source))
        block[56] ^= 1
        with self.assertRaisesRegex(ValueError, 'identity'):
            f.save_ownership_assessment(source + career_save.seal(block))

    def test_cli_bounds_input_and_excludes_companion_as_native_transport(self):
        with tempfile.TemporaryDirectory(prefix='f26-inspection-') as directory:
            path = Path(directory).resolve() / 'SAVEGAME.DAT'
            source = week_save(grown=True)
            path.write_bytes(source)
            result = subprocess.run([sys.executable, '-m', 'mod_editor.core.nfl2k5_franchise_2026',
                                     '--assess-save', str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"native_ledger_bytes_owned": 0', result.stdout)
            self.assertEqual(path.read_bytes(), source)
            with path.open('r+b') as stream:
                stream.truncate(8 * 1024**2)
            refused = subprocess.run([sys.executable, '-m', 'mod_editor.core.nfl2k5_franchise_2026',
                                      '--assess-save', str(path)], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn('unsupported franchise container length', refused.stderr)


@unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE required for owner composition')
class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest('expected bounded retail XBE, not a disc or pack')
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('retail XBE differs from USA evidence pin')
        cls.seed = space.apply(cls.retail, f.REQUESTS + mode.REQUESTS + growth.REQUESTS, scaleout=True)[0]

    def test_three_owners_all_six_orders_retain_pins_and_dormancy(self):
        hashes = set()
        for order in itertools.permutations((f, mode, growth)):
            payload = self.seed
            for owner in order:
                payload = owner.apply(payload)[0]
            for owner in order:
                self.assertEqual(owner.status(payload), 'applied')
                replay, receipt = owner.apply(payload)
                self.assertEqual(replay, payload)
                self.assertEqual(receipt['changed_bytes'], 0)
            assessment = f.runtime_assessment(payload)
            self.assertEqual(assessment['kernel_status'], 'applied')
            self.assertFalse(assessment['runtime_enforced'])
            self.assertEqual(f.apply(payload)[1]['native_hooks'], [])
            with self.assertRaisesRegex(f.Franchise2026Error, 'unavailable'):
                f.require_runtime_ready()
            hashes.add(hashlib.sha256(payload).digest())
        self.assertEqual(len(hashes), 1)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA retail XBE and Unicorn required for native boundaries')
class NativeBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CompositionTests.setUpClass()
        payload = CompositionTests.seed
        for owner in (mode, growth, f):
            payload = owner.apply(payload)[0]
        cls.payload = payload
        cls.state = f._inspect(payload)[1]['data']['va']
        cls.grown = week_save(grown=True, reserves=17)

    def test_metadata_admission_rejects_ledger_in_both_native_save_formats(self):
        with Machine(self.payload) as m:
            m.put(0xB72808, arena.ARENA_SIZE)
            for size in career_save.BASE_SIZES + career_save.SIZES:
                self.assertEqual(m.call('inline_admit', ecx=size), 1)
                for extra in (1, f.DATA_SIZE, f.COMPANION_SIZE):
                    # Retail +4096 already names arena v1; that is not a ledger.
                    if size + extra in career_save.BASE_SIZES + career_save.SIZES:
                        continue
                    self.assertEqual(m.call('inline_admit', ecx=size + extra), 0)
            for base in (week_save(), self.grown):
                # Even the length alias fails the complete ROST framing check.
                raw = base + bytes(f.RuleState.new(2026, 134).raw)
                m.uc.mem_write(m.SAVE, raw)
                self.assertEqual(m.call('inline_stage', ecx=m.SAVE, edx=len(raw)), 0)
                m.native_load(raw, requested=False, capacity=arena.ARENA_SIZE)
                self.assertEqual(m.get(m.state + 2660), 0)
                self.assertNotEqual(m.get(m.state + 2580), 2)

    def test_native_footer_validator_and_encoder_own_reserved_bytes(self):
        block = block_for(self.grown)
        with Machine(self.payload) as m:
            for at in (82, 83, *range(88, 128)):
                bad = bytearray(block)
                bad[at] = 1
                m.uc.mem_write(m.SAVE, career_save.seal(bad))
                self.assertEqual(m.call('inline_valid', ecx=m.SAVE, edx=arena.ARENA_SIZE), 0, at)
            m.uc.mem_write(m.state, career_save.to_runtime(block))
            m.uc.mem_write(m.OUT, b'\xa5' * 128)
            m.call('inline_encode', ecx=m.OUT)
            self.assertEqual(bytes(m.uc.mem_read(m.OUT, 128)), block)

    def test_complete_native_save_and_cold_load_do_not_transport_rule_state(self):
        for with_career in (False, True):
            source = self.grown + block_for(self.grown) if with_career else self.grown
            with Machine(self.payload) as m:
                m.native_load(source, requested=with_career, capacity=arena.ARENA_SIZE)
                self.assertEqual(m.get(0xE576A4), 8)
                ledger = f.RuleState.new(2026, 134)
                ledger.commit_game(0, 7, 0, (53, 54))
                m.uc.mem_write(self.state, bytes(ledger.raw))
                before = m.native_save()
                self.assertIsNotNone(before)
                ledger.complete_game(0, 7, 7)
                m.uc.mem_write(self.state, bytes(ledger.raw))
                after = m.native_save()
                self.assertEqual(before, after, 'rule state unexpectedly changed native serialization')
                self.assertEqual(len(after), 724140 + 128 * with_career)
                self.assertEqual(f.save_ownership_assessment(after)['reserve_counts']['0'], 17)
            with Machine(self.payload) as cold:
                cold.native_load(after, requested=with_career, capacity=arena.ARENA_SIZE)
                self.assertEqual(cold.get(0xE576A4), 8)
                self.assertEqual(cold.get(cold.state + 2580), 2 if with_career else 0)
                self.assertEqual(bytes(cold.uc.mem_read(self.state, f.DATA_SIZE)), bytes(f.DATA_SIZE))
                self.assertNotEqual(bytes(cold.uc.mem_read(self.state, f.DATA_SIZE)), bytes(ledger.raw))

    def test_regular_week_projects_53_without_elevations_and_maps_results_by_slot(self):
        for ols in (7, 8):
            source = bytearray(self.grown)
            save = fs.FranchiseSave(source)
            # Replace the eighth OL with a receiver for the 47-player case.
            if ols == 7:
                source[save.player_offset(7) + 0x35] = 3
            session = fs.FranchiseSave(source).franchise_2026_session()
            chosen = session.prepare(0, 7, 0, elevations=(53, 54))
            self.assertEqual(len(chosen.selected), 48 if ols == 8 else 47)
            positions = [source[save.player_offset(p) + 0x35] for p in chosen.selected]
            self.assertEqual(set(positions), set(range(17)))
            self.assertGreaterEqual(positions.count(0), 2)
            self.assertEqual(sum(p in f.OL for p in positions), ols)
            self.assertTrue(session.accept(chosen))
            with Machine(self.payload) as m:
                m.native_load(bytes(source), requested=False, capacity=arena.ARENA_SIZE)
                m.uc.mem_write(self.state, bytes(session.state.raw))
                teams = m.get(m.root + 28)
                original = bytes(m.uc.mem_read(teams, 1000))
                m.call(pr.STAGE_VA, ecx=teams, edx=teams + 500, budget=1000000)
                self.assertEqual(bytes(m.uc.mem_read(teams, 1000)), original)
                self.assertEqual(m.uc.mem_read(pr.TEAM_COPIES[0] + 0x11c, 1), b'\x35')
                pool = m.get(m.root + 4)
                copied_ids = [struct.unpack('<H', m.uc.mem_read(pr.PLAYER_COPIES[0] + 84*i + 4, 2))[0]
                              for i in range(53)]
                self.assertEqual(copied_ids, list(range(1000, 1053)))
                self.assertNotIn(1053, copied_ids)
                self.assertNotIn(1054, copied_ids)
                # The fixture declares a game at row 0/slot 0, away=0/home=1.
                m.put(0xE576B4, 0)
                m.put(0xE576BC, 0)
                m.uc.mem_write(0xE57C40, bytes((0, 0, 1, 0, 0, 0, 0, 0)))
                m.put(0xE5786C, teams)
                m.put(0xE57870, teams + 500)
                for side in (0, 1):
                    count = m.uc.mem_read(pr.TEAM_COPIES[side] + 0x11c, 1)[0]
                    for slot in (0, 1, 47, count - 1):
                        copy = pr.PLAYER_COPIES[side] + slot * 84
                        owner = m.get(teams + side * 500 + slot * 4)
                        self.assertEqual(m.call(0xC5280, ecx=copy), owner)
                    # A counterfactual compacted copy puts an elevated identity
                    # in slot zero. Execute the FULL retail resolver and callees.
                    copy = pr.PLAYER_COPIES[side]
                    elevated = pool + (53 + side * 65) * 84
                    m.uc.mem_write(copy, bytes(m.uc.mem_read(elevated, 84)))
                    self.assertNotEqual(m.call(0xC5280, ecx=copy), elevated)
                    self.assertEqual(m.call(0xC5280, ecx=copy), m.get(teams + side * 500))


if __name__ == '__main__':
    unittest.main()
