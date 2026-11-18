"""Stock ages, season-specific numbering and the final main roster's active membership."""
import importlib.util
import os
import unittest
from pathlib import Path

from mod_editor.core import nfl2k5_roster_ages as ages, nfl2k5_roster_records as rr
from tests.nfl2k5_supersim_draft_fixture import XBE, retail_bytes, retail_roster


class NumberTests(unittest.TestCase):
    def test_season_rules_and_merged_edge_eligibility(self):
        self.assertEqual(rr.jersey_ranges(0, 2004), ((1, 19),))
        self.assertEqual(rr.jersey_ranges(1, 2021), ((1, 19),))
        self.assertEqual(rr.jersey_ranges(0, 2026), ((0, 19),))
        self.assertEqual(rr.jersey_ranges(9, 2026), ((0, 49), (80, 89)))
        self.assertEqual(rr.jersey_ranges(16, 2026, "one_pool"), ((0, 79), (90, 99)))


@unittest.skipUnless(XBE.is_file(), "retail fixtures unavailable")
class StockAgesTests(unittest.TestCase):
    def test_checked_identity_list_and_selective_idempotent_shift(self):
        body = retail_roster()
        self.assertEqual(ages._stock_fingerprints(body), ages._stock_fingerprints(None))
        doc = rr.load_body(body)
        player = doc.team_players(0)[0]
        before = player.record.values["birth_day"]
        player.record.set("birth_day", 1 if before != 1 else 2)
        edited = doc.to_body()
        shifted, receipt = ages.preserve_stock_ages(edited)
        self.assertGreater(receipt["changed"], 1600)
        self.assertEqual(edited[player.offset:player.offset+84], shifted[player.offset:player.offset+84])
        again, receipt = ages.preserve_stock_ages(shifted)
        self.assertEqual((again, receipt["changed"]), (shifted, 0))

    @unittest.skipUnless(importlib.util.find_spec("unicorn"), "unicorn unavailable")
    def test_native_retirement_pass_matches_the_same_2004_players(self):
        from mod_editor.core import nfl2k5_progression as progression
        from tests.mod_editor.test_b780_b4_economy import _franchise
        body = retail_roster()
        shifted, _ = ages.preserve_stock_ages(body)
        payload = progression.apply(retail_bytes())[0]

        def retired(year, roster):
            machine = _franchise(payload, roster)
            machine.put(0x247AC7, year)
            machine.seed(4242)
            players = [machine.get(machine.team_base + i * 500 + 4 * j) for i in range(32)
                       for j in range(machine.uc.mem_read(machine.team_base + i * 500 + 0x11c, 1)[0])]
            machine.call(0x2BDB00, budget=350_000_000)
            base = machine.get(machine.root + 4)
            return {(p - base) // 84 for p in players if machine.uc.mem_read(p + 8, 1)[0] & 8}

        original = retired(2004, body)
        self.assertGreater(len(retired(2026, body)), 3 * len(original))
        self.assertEqual(retired(2026, shifted), original)


MOD = Path(os.environ.get("NFL2K5_V09_XISO", ""))


@unittest.skipUnless(MOD.is_file(), "released v0.9 image unavailable")
class ShippedRosterTests(unittest.TestCase):
    def test_expected_ir_membership_draft_capacity_and_transaction_survive_reopen(self):
        doc = rr.load_image(MOD)
        self.assertTrue(doc.modern_ir)
        self.assertEqual(doc.base_year, 2026)
        self.assertEqual([doc.active_count(i) for i in range(32)], [53] * 32)
        self.assertEqual(sum(doc.projected_ir_count(i) for i in range(32)), 119)
        self.assertEqual({p.offset for p in doc.group_players("free_agent")}, set(doc.free_agents))
        self.assertEqual([doc.summary()[name] for name in ("draft_class", "draft_slots", "draft_capacity")],
                         [0, 380, 746])
        packers = next(t for t in doc.teams if t.abbreviation == "GB")
        player = next(p for p in doc.team_players(packers.index) if not p.record.values["unknown_20_high"] & 0x200)
        slot = packers.slots.index(player.offset)
        doc.release(player, packers.index)
        self.assertEqual(doc.active_count(packers.index), 52)
        doc.sign(player, packers.index, slot=slot)
        saved = rr.RosterDocument(doc.to_body(), base_year=2026, modern_ir=True)
        self.assertEqual((len(saved.teams[packers.index].slots), saved.active_count(packers.index)), (62, 53))
        findings = rr.validate_membership(saved)
        self.assertFalse(any(f["check"] in ("roster size", "duplicate jersey") for f in findings))
        active = [p for p in saved.team_players(packers.index) if p.offset not in saved.projected_ir_players(packers.index)]
        active[0].record.set("jersey", active[1].record.values["jersey"])
        self.assertTrue(any(f["check"] == "duplicate jersey" and f["player"] == packers.display
                            for f in rr.validate_membership(saved)))


if __name__ == "__main__":
    unittest.main()
