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

    def test_people_off_the_clubs_and_free_agency_keep_their_real_birthdays(self):
        # The retail roster also holds ESPN personalities and celebrities with real birthdays
        # (Chris Berman 1955, Mel Kiper 1960). No franchise ever ages them, so the 2026 shift must not
        # make them 22 years younger. A modern roster also keeps stock legends only on the all-star
        # and celebrity squads; those are not clubs either.
        body = retail_roster()
        doc = rr.load_body(body, reference_year=2004)
        outside = [p for p in doc.by_pool("primary")
                   if doc.club_of(p) is None and not doc.is_free_agent(p) and p.first and p.last]
        names = {f"{p.first} {p.last}" for p in outside}
        self.assertTrue({"Chris Berman", "Mel Kiper"} <= names)
        shifted, receipt = ages.preserve_stock_ages(body)
        for p in outside:
            self.assertEqual(shifted[p.offset:p.offset + 84], body[p.offset:p.offset + 84], f"{p.first} {p.last}")
        self.assertEqual(receipt["matched"], receipt["changed"])
        moved = rr.load_body(shifted, reference_year=2004)
        clubs = [p for p in moved.by_pool("primary") if moved.club_of(p) is not None or moved.is_free_agent(p)]
        self.assertGreater(sum(1 for p in clubs if shifted[p.offset:p.offset + 84] != body[p.offset:p.offset + 84]), 1900)

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


STANDARD_SOURCES = Path(os.environ.get("NFL2K5_B81_STANDARD_SOURCES", "") or "missing")
# b81 roster-1125 (Noah: "kirk cousins not on vikings, trade deadline roster not updated?"; the 2026 deadline was 11/10):
# the release sources load the 11/25 refresh, 128 MB and the 64 MB retail-capacity fit of it.
RELEASE_ROSTERS = {128: ("roster-edits-b81-refresh-20261125.json",
                         "c002e7afdfd0b45b79314d85cd467a8675fa7fbec43d5d7ef29edfc22f09e85f"),
                   64: ("roster-edits-b81-refresh-20261125-retail-capacity-64mb.json",
                        "49a255fffadbdec88f5e51a46967af0c02d1f5d88dac4b3f8fe6e82eca47ec98")}


@unittest.skipUnless((STANDARD_SOURCES / "recipe.json").is_file(), "private release sources absent: NFL2K5_B81_STANDARD_SOURCES")
class ReleaseSourcesRosterTests(unittest.TestCase):
    def test_both_editions_load_the_november_25_roster(self):
        import hashlib, json
        for memory, (name, digest) in RELEASE_ROSTERS.items():
            root = STANDARD_SOURCES.parent / f"v10-sources-{memory}"
            if not (root / "recipe.json").is_file():
                continue
            with self.subTest(memory=memory):
                for document in ("recipe.json", "assets/documents/frozen-recipe.json"):
                    overrides = json.loads((root / document).read_text(encoding="utf-8"))["overrides"]
                    self.assertTrue(overrides["roster_edits"].endswith("_" + name), document)
                    self.assertIn("Roster frozen November 25, 2026.", overrides["notes"])
                built = json.loads((root / "SOFTDRINK-build-recipe.json").read_text(encoding="utf-8"))["overrides"]
                path = Path(built["roster_edits"])
                self.assertEqual(path.parent, root / "assets/files")
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
                plan = json.loads(path.read_text(encoding="utf-8"))["roster_refresh"]
                self.assertEqual(plan["as_of"], "2026-11-25")
                cousins = next(r for r in plan["players"] if r.get("gsis_id") == "00-0029604")
                self.assertEqual((cousins["team"], cousins["status"]), ("MIN", "ACT"))
                minnesota = next(t for t in plan["teams"] if t["team"] == "MIN")
                self.assertIn(cousins["index"], minnesota["active"])
                rows = {r["index"]: r for r in plan["players"]}
                # coordinator 11/25: no two men on a club share a number across the 53, the practice squad and IR. The plan
                # lists the 53 and the practice squad; which injured men stay on IR the writer decides (the 65-man list),
                # so IR is checked on the written roster: test_b780_roster1_depth_lint jersey_clashes / lint(lists=True)
                for team in plan["teams"]:
                    numbers = [rows[i]["fields"]["jersey"] for i in set(team["active"]) | set(team["reserves"])]
                    self.assertEqual(len(numbers), len(set(numbers)), team["team"])
                # Noah 11/25 on Joe Mixon ("He should be very likely to reinjure himself when signed"): Durability from
                # his real availability (2025 all season on a reserve list): 85 -> 66
                if memory == 128:   # the 64 MB fit leaves the free agents in capacity records out, Mixon and the named ones too
                    mixon = next(r for r in plan["players"] if r.get("gsis_id") == "00-0033897")
                    self.assertEqual((mixon["status"], mixon["fields"]["durability"]), ("UFA", 66))
                    # Noah 11/25: the free agents he named
                    named = {r["source_name"] for r in plan["players"] if (r.get("evidence") or {}).get("kind")
                             == "owner_named_default_free_agent"}
                    self.assertEqual(named, {"Johnny Manziel", "Robert Griffin III", "Derek Carr", "Teddy Bridgewater",
                                             "Blake Bortles", "Tim Tebow", "Allen Hurns", "PJ Walker", "Hakeem Butler"})
                    self.assertTrue(all(r["index"] in plan["free_agents"] for r in plan["players"]
                                        if r.get("source_name") in named))
                    # coordinator ruling 11/25 (option A): about 600 more real unsigned veterans as free agents
                    tail = [r for r in plan["players"] if (r.get("evidence") or {}).get("kind") == "long_tail_unsigned_veteran"]
                    self.assertEqual(len(tail), 599)
                    self.assertTrue(all(r["status"] == "UFA" and r["index"] in plan["free_agents"] for r in tail))
                # coordinator ruling 11/25: Daniel Carlson is Miami's kicker on the 53; the released Zane Gonzalez is not
                miami = next(t for t in plan["teams"] if t["team"] == "MIA")
                carlson = next(r for r in plan["players"] if r.get("gsis_id") == "00-0034161")
                self.assertIn(carlson["index"], miami["active"])
                self.assertEqual(miami["specialists"]["k"], carlson["index"])
                gonzalez = next((r for r in plan["players"] if r.get("gsis_id") == "00-0033862"), None)
                self.assertTrue(gonzalez is None or gonzalez["index"] not in miami["active"] + miami["reserves"])


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
