"""V1D: reject unsupported team arguments, retain FRZ4, replay shipped callers."""
from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).parent)]
import test_b77_frz_stub as base
from mod_editor.core import nfl2k5_moment_gun_weight as gun, nfl2k5_stock_books as stock

INPUT = Path(os.environ.get("B77_V1D_INPUT", "/nonexistent/v1d"))


@unittest.skipUnless(base.HAVE_UNICORN, "Unicorn required")
class GuardTests(unittest.TestCase):
    def setUp(self):
        self.helper = base.LiveTeamContractTests()

    def test_non_live_arguments_fall_back_before_any_argument_memory_read(self):
        m, r = self.helper.fixture()
        reads = []
        import unicorn
        m.hook_add(unicorn.UC_HOOK_MEM_READ, lambda u, kind, addr, size, value, data: reads.append(addr))
        # Roster records, indices, adjacent mapped bytes, and unmapped garbage.
        for team in (0, 1, 2, 31, 0xB30864, 0xB30A58, 0xE5FC24, 0xE5FC5F, 0xE5FC64, 0x31E18C8E, 0xFFFFFFFF):
            with self.subTest(team=hex(team)):
                reads.clear()
                self.assertAlmostEqual(self.helper.run_stub(m, r, team=team), gun.RETAIL_WEIGHT)
                self.assertNotIn((team + 0x1C) & 0xFFFFFFFF, reads)
        # No valid active team when both globals are null. Null is still rejected.
        m.mem_write(gun.OFFENSE_TEAM_POINTER, bytes(8))
        self.assertAlmostEqual(self.helper.run_stub(m, r, team=0), gun.RETAIL_WEIGHT)

    def test_foreign_roster_counterexample_faults_in_frz4_but_is_not_a_native_caller(self):
        m, r = self.helper.fixture()
        va = 0x14E3BD0
        old = stock.code_for(va, legacy_unguarded_live_team=True)
        m.mem_write(va, old)
        # A deliberately wrong argument, NOT an observed game state.
        m.mem_write(0xB30864 + 0x1C, struct.pack("<I", 0x31E18C8E))
        import unicorn
        with self.assertRaises(unicorn.UcError):
            self.helper.run_stub(m, r, team=0xB30864)
        self.assertEqual(m.reg_read(r.UC_X86_REG_EIP), 0x14E3E5A)

    def test_both_active_team_identities_and_moment_bypass(self):
        m, r = self.helper.fixture()
        expected = gun.team_bin_weights(keys=stock.key_order())[stock.key_order().index("BAL")][0]
        for offense, defense in ((0xE5FC20, 0xE5FC60), (0xE5FC60, 0xE5FC20)):
            m.mem_write(gun.OFFENSE_TEAM_POINTER, struct.pack("<II", offense, defense))
            for team in (offense, defense):
                self.assertAlmostEqual(self.helper.run_stub(m, r, team=team), expected)
        m.mem_write(gun.MODE_WORD, struct.pack("<I", 8))
        for row in (0, 38, 50, 51, 0xFFFFFFFF):
            m.mem_write(gun.ROW_WORD, struct.pack("<I", row))
            want = gun.weights()[row] if row < 51 else gun.RETAIL_WEIGHT
            self.assertAlmostEqual(self.helper.run_stub(m, r, team=0xDEADBEEF), want)

    def test_all_keys_downs_bin_boundaries_match_frz4_bit_for_bit(self):
        old, r = self.helper.fixture()
        new, _ = self.helper.fixture()
        va = 0x14E3BD0
        old.mem_write(va, stock.code_for(va, legacy_unguarded_live_team=True))
        # A scalar distance leaf for the portable emitter comparison. The
        # private native rule grid separately executes the real 0x207950.
        for m in (old, new):
            m.mem_write(gun.TOGO_FUNCTION, b"\xd9\x05" + struct.pack("<I", 0x3005000) + b"\xc3")
        for key in stock.key_order():
            for down in (0, 1, 2, 3, 4, 5):
                for yards in (1, 3.49, 3.5, 3.51, 6.49, 6.5, 6.51, 7.49, 7.5, 7.51, 20):
                    for m in (old, new):
                        m.mem_write(0x3003004, struct.pack("<I", down))
                        m.mem_write(0x3005000, struct.pack("<f", yards * gun.YARD))
                        self.helper.run_stub(m, r, key=key)
                    self.assertEqual(old.mem_read(0x3001000, 4), new.mem_read(0x3001000, 4), (key, down, yards))


@unittest.skipUnless((INPUT / "default.xbe").is_file(), "set B77_V1D_INPUT to the shipped v0.6 bounded extraction")
class NativeCallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.b77.a4_repair import repair_xbe
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        cls.before = (INPUT / "default.xbe").read_bytes()
        cls.home = (INPUT / "BAL.play").read_bytes()
        cls.away = (INPUT / "PHI.play").read_bytes()
        cls.owned = stock.allocation(cls.before)
        kind, weights = stock._installed_kind(XbeImage(cls.before), cls.owned["va"])
        if kind != "unguarded_bins":
            raise ValueError("requires the shipped FRZ4 body")
        cls.after, cls.receipt = repair_xbe(cls.before, *weights)

    def test_exact_upgrade_scope_idempotence_and_foreign_refusal(self):
        from tools.b77.frz_xbe_bisect import digests_ok
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        self.assertEqual(stock.status(self.before), "needs_fix")
        self.assertEqual(stock.status(self.after), "applied")
        _, weights = stock._installed_kind(XbeImage(self.after), self.owned["va"])
        self.assertEqual(stock.apply(self.after, weights=weights[0], team_weights=weights[1])[0], self.after)
        start = self.owned["raw"]
        self.assertEqual(self.before[start:start+stock.STUB_OFFSET], self.after[start:start+stock.STUB_OFFSET])
        self.assertEqual(self.before[start+stock.WEIGHT_OFFSET:start+stock.CODE_SIZE],
                         self.after[start+stock.WEIGHT_OFFSET:start+stock.CODE_SIZE])
        self.assertTrue(digests_ok(self.after))
        self.assertTrue(self.receipt["outside_scope_identical"])
        body = bytearray(self.before[start:start+stock.CODE_SIZE])
        body[stock.STUB_OFFSET+7] ^= 1
        foreign = stock._write_body(self.before, self.owned, body)
        self.assertEqual(stock.status(foreign), "foreign")
        with self.assertRaises(ValueError):
            stock.apply(foreign)

    def test_static_inventory_has_every_known_direct_caller_and_no_extra_entry_reference(self):
        from tools.b77.v1d_caller_audit import inventory
        for payload in (self.before, self.after):
            self.assertEqual(inventory(payload)["inventory_failures"], [])

    def test_each_native_call_edge_returns_with_correct_contract(self):
        from tools.b77.v1d_caller_audit import replay_edges, CALLS
        for payload in (self.before, self.after):
            result = replay_edges(payload, self.home, self.away)
            self.assertFalse(result["failed"], result["rows"][-1])
            self.assertEqual(result["inventory"]["inventory_failures"], [])
            self.assertEqual(result["rule_balance_errors"], [])
            self.assertEqual(result["bad_weights"], [])
            self.assertEqual(result["bad_bin_reads"], 0)
            self.assertEqual(set(result["rule_team_arguments"]), {"0xe5fc20", "0xe5fc60"})
            sites = {r["site"] for r in result["rows"]}
            self.assertTrue({hex(s) for v in CALLS.values() for s in v} <= sites)

    def test_all_selector_caller_blocks_return_identical_choices(self):
        from tools.b77.v1d_caller_audit import replay_selector_callers
        old = replay_selector_callers(self.before, self.home, self.away)
        new = replay_selector_callers(self.after, self.home, self.away)
        for result in (old, new):
            self.assertFalse(result["failed"], result["rows"][-1])
            self.assertEqual(result["rule_balance_errors"], [])
            self.assertEqual(result["bad_weights"], [])
            self.assertEqual(result["bad_bin_reads"], 0)
        self.assertEqual(old, new)


if __name__ == "__main__":
    unittest.main()
