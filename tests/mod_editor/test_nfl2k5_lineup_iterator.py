"""PROVED OFFLINE: native iterator exhaustion and exact old-profile upgrade."""
import hashlib
import struct
import unittest
from pathlib import Path

from mod_editor.core import nfl2k5_lineup_iterator as code
from mod_editor.core import nfl2k5_position_pools as pools
from mod_editor.core import nfl2k5_roster_records as rr
from tests import nfl2k5_position_pools_test as fixture


class UpgradeTests(unittest.TestCase):
    def test_old_complete_profile_needs_fix_and_upgrades_only_iterator(self):
        fixed, _ = pools.apply(fixture._prepared())
        off = pools._offset(fixed, code.VA)
        old = bytearray(fixed)
        old[off:off + code.SIZE] = code.RETAIL
        fixture._repin(old)
        old = bytes(old)
        self.assertEqual(pools.status(old), 'needs_fix')
        self.assertEqual(pools.lineup_status(old), 'retail')
        self.assertEqual(rr.detect_scheme_from_states({'position_pools': 'needs_fix'})['scheme'], 'one_pool')
        upgraded, receipt = pools.apply(old)
        self.assertEqual(upgraded, fixed)
        self.assertEqual([e['label'] for e in receipt['edits']], ['lineup_iterator'])
        self.assertTrue(receipt['upgraded_lineup_iterator'])
        self.assertEqual(pools.apply(upgraded)[0], upgraded)
        self.assertEqual(pools.apply(upgraded)[1]['edits'], [])
        old = bytearray(old)
        old[off + 50] ^= 1
        self.assertEqual(pools.status(bytes(old)), 'foreign')
        with self.assertRaises(pools.PositionPoolsError):
            pools.apply(bytes(old))

    def test_existing_span_only_and_no_optional_repair_switch(self):
        for penalty in (False, True):
            for depth in (False, True):
                sites = pools._sites(penalty, depth)
                repair, = [s for s in sites if s.group == 'lineup']
                self.assertEqual((repair.va, repair.size), (0xE8410, 0x380))
                self.assertEqual(repair.after, code.replacement())
        self.assertEqual(len(code.RETAIL), code.SIZE)


@unittest.skipUnless(fixture.RETAIL_XBE.is_file() and fixture.HAVE_UNICORN,
                     'pinned retail XBE and Unicorn required for native helper replay')
class NativeSweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
        cls.retail = fixture.RETAIL_XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('retail XBE pin differs')

    def boot(self):
        from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP
        runner = fixture.EmulationTests()
        uc = runner._boot(self.retail, [])
        team = runner.TEAM_VA
        roster, desc, lists = team + 0x1000, team + 0x2000, team + 0x3000
        pointers = [team + 0x4000 + i * 0x54 for i in range(34)]
        pairs = list(fixture.RETAIL_LIST_PAIRS)
        pairs[15] = pairs[14]
        rows = list(struct.iter_unpack('<19I', uc.mem_read(0x4F5A38, 19 * 76)))
        uc.mem_write(0x4F5930, b''.join(struct.pack('<II', *p) for p in pairs))
        uc.mem_write(code.VA, code.replacement())
        uc.mem_write(team, struct.pack('<34I', *pointers))
        uc.mem_write(roster, struct.pack('<II', team, 0xFFFFFFFF))
        physical = [[] for _ in range(28)]
        for enum, kind in enumerate(pools.RETAIL_ENUM_TO_KIND):
            if enum == 10:
                kind = 14
            for i in range(2):
                n = 2 * enum + i
                uc.mem_write(pointers[n] + 0x35, bytes([enum]))
                for pool in set(pairs[kind]):
                    physical[pool].append(n)
        # Primary-only special lists overlap ordinary lists, as in the game.
        physical[25] = [2, 0, 14]
        physical[26] = [6, 14, 20, 22]
        physical[27] = [22, 20, 14, 6]
        for first, second in pairs:
            if first != second:
                physical[second] = list(reversed(physical[first]))
        def seed(empty=False):
            at = lists
            for p, values in enumerate(physical):
                uc.mem_write(roster + 0x9C + p * 4, struct.pack('<I', at))
                values = [] if empty else values
                uc.mem_write(at, bytes(values) + b'\xff')
                at += len(values)
            uc.mem_write(at, b'\xff')
        def call(va, args):
            ans = runner._call(uc, va, ecx=roster, edx=desc, stack=args, until=runner.SENT_VA)
            self.assertEqual(uc.reg_read(UC_X86_REG_EIP), runner.SENT_VA)
            self.assertEqual(uc.reg_read(UC_X86_REG_ESP), runner.STACK_VA + 0x80004 + 4 * len(args))
            return ans
        return uc, desc, pointers, physical, pairs, rows, seed, call

    def test_every_kind_rank_tier_mask_and_empty_or_legacy_roster(self):
        uc, desc, pointers, physical, pairs, rows, seed, call = self.boot()
        bits = struct.unpack('<19I', uc.mem_read(0x515778, 76))
        cases = 0
        for empty in (False, True):
            seed(empty)
            for kind in range(19):
                for rank in range(8):
                    uc.mem_write(desc, bytes([0, 0, 0, 0, 0, kind | (rank << 5)]))
                    for tier in range(7):
                        for mask in {bits[kind], 0x7FFFF, 0x4000, 0x8000, 0xC000, 0}:
                            uc.mem_write(0xAC26B8, struct.pack('<I', mask))
                            # Independent model: ordered kind masks first, then
                            # other kinds for relaxed tiers; retain primary rank.
                            expected, visited, players = [], set(), set()
                            for phase in range(1 if tier <= 1 else 2):
                                for index, k in enumerate(rows[kind][:1] if tier == 0 else rows[kind]):
                                    if index and k in (3, 4):
                                        continue
                                    if bool(mask & bits[k]) != (phase == 0):
                                        continue
                                    p = pairs[k][rank & 1]
                                    if p in visited:
                                        continue
                                    visited.add(p)
                                    for n in ([] if empty else physical[p]):
                                        if n not in players:
                                            expected.append(pointers[n])
                                            players.add(n)
                            # The first getter retains its existing special-list
                            # quirks. Start from each member of our finite stream
                            # and prove its exact successor, including exhaustion.
                            for i, current in enumerate(expected):
                                nxt = call(code.VA, (0, tier, current))
                                self.assertEqual(nxt, (expected + [0])[i + 1],
                                                 (kind, rank, tier, hex(mask), i))
                            if not expected:
                                self.assertEqual(call(code.VA, (0, tier, pointers[0])), 0)
                            self.assertLessEqual(len(expected), 34)
                            self.assertEqual(len(expected), len(set(expected)))
                            cases += 1
        self.assertGreater(cases, 10000)


if __name__ == '__main__':
    unittest.main()
