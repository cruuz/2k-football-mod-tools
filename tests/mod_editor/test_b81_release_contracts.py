"""b81 #48 (coordinator 11/27): the economy contract import keeps OverTheCap's term when the 2026 cap schedule is
missing, and the release roster documents carry the re-fitted contracts (tools/franchise_economy/release_contracts.py)."""
import hashlib
import json
import os
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys  # noqa: E402
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from tools.franchise_economy.contracts import charges  # noqa: E402
from tools.franchise_economy.import_contracts import (  # noqa: E402
    contract_fit, fallback_schedule, in_season_full_2026, term_end)
from tools.franchise_economy import release_contracts  # noqa: E402

DATA = json.loads((ROOT / "data/nfl2k5_franchise_economy.json").read_text())
FLOORS = DATA["minimums"]["dollars"]


def player(years_pro):
    return types.SimpleNamespace(record=types.SimpleNamespace(values={"years_pro": years_pro}),
                                 display="Test Player", first="Test", last="Player")


def row(**kw):
    base = {"player": "Test Player", "is_active": True, "year_signed": 2026, "years": 1, "apy": 1.0, "value": 1.0,
            "draft_year": 2022, "draft_overall": None, "season_history": [], "player_page": "https://overthecap.com/x"}
    return {**base, **kw}


def season(year, cap, base=None, cash=None, team="Texans"):
    return {"year": str(year), "cap_number": cap, "base_salary": cap if base is None else base,
            "cash_paid": cap if cash is None else cash, "team": team}


class FallbackTermTests(unittest.TestCase):
    def test_missing_schedule_keeps_the_term_at_apy(self):
        # a three-year undrafted deal signed in 2026 with no season history yet: three years, not a one-year minimum
        cap, rule = fallback_schedule(player(1), row(years=3, apy=1.2, value=3.6), DATA)
        self.assertEqual(rule["rule"], "OTC term at APY (no 2026 cap schedule)")
        self.assertEqual(cap, [1200000] * 3)
        self.assertEqual(rule["term_end"], 2028)
        fit, modeled, _ = contract_fit(player(1), row(years=3, apy=1.2, value=3.6), DATA)
        self.assertEqual((fit["fields"]["contract_length"], fit["fields"]["contract_remaining"]), (3, 3))

    def test_apy_below_the_minimum_takes_the_minimum_every_year(self):
        cap, _ = fallback_schedule(player(1), row(years=2, apy=0.2475, value=0.495), DATA)
        self.assertEqual(cap, [FLOORS[0]] * 2)

    def test_a_term_that_ended_before_2026_is_a_one_year_minimum(self):
        cap, rule = fallback_schedule(player(5), row(year_signed=2023, years=3), DATA)
        self.assertEqual(rule["rule"], "one-year active-roster CBA minimum")
        self.assertEqual(cap, [FLOORS[4]])
        cap, rule = fallback_schedule(player(5), None, DATA)
        self.assertEqual(rule["rule"], "one-year active-roster CBA minimum")

    def test_a_2026_draftee_on_his_rookie_deal_takes_the_draft_slot_schedule(self):
        cap, rule = fallback_schedule(player(1), row(years=4, draft_year=2026, draft_overall=40), DATA)
        self.assertEqual(rule["rule"], "OTC draft-slot cap schedule interpolation")
        self.assertEqual(len(cap), 4)

    def test_a_2026_draftee_on_a_one_year_deal_keeps_that_deal(self):
        # Carsen Ryan (CLE, pick 248): released, then signed again for one year; not a four-year rookie schedule
        cap, rule = fallback_schedule(player(1), row(years=1, apy=0.2475, draft_year=2026, draft_overall=248), DATA)
        self.assertEqual(rule["rule"], "OTC term at APY (no 2026 cap schedule)")
        self.assertEqual(cap, [FLOORS[0]])
        fit, _, _ = contract_fit(player(1), row(years=1, apy=0.2475, draft_year=2026, draft_overall=248), DATA)
        self.assertEqual(fit["fields"]["contract_length"], 1)
        self.assertGreaterEqual(charges(fit["fields"])[0] * 4000, FLOORS[0])

    def test_term_end(self):
        self.assertEqual(term_end({"year_signed": 2024, "years": 4}), 2027)
        self.assertIsNone(term_end({"year_signed": None, "years": 4}))
        self.assertIsNone(term_end(None))


class OpeningFloorTests(unittest.TestCase):
    def test_a_prorated_2026_number_is_raised_to_the_minimum_and_later_years_stay(self):
        # an in-season trade: OTC lists only the acquiring club's prorated 2026 base, then the full 2027 number
        r = row(year_signed=2024, years=4, season_history=[season(2026, 0.776389, base=1.075), season(2027, 5.618829)])
        fit, modeled, _ = contract_fit(player(3), r, DATA, floor_opening=True)
        self.assertEqual(modeled["opening_floor_dollars"], FLOORS[2])
        self.assertEqual(fit["source_cap_dollars"], [FLOORS[2], 5618829])
        self.assertEqual((fit["fields"]["contract_length"], fit["fields"]["contract_remaining"]), (2, 2))
        plain, modeled, _ = contract_fit(player(3), r, DATA)
        self.assertIsNone(modeled)
        self.assertEqual(plain["source_cap_dollars"], [776389, 5618829])

    def test_a_one_year_prorated_deal_takes_the_smallest_legal_charge_at_the_minimum(self):
        r = row(season_history=[season(2026, 0.15125, base=0.2475)])
        fit, modeled, _ = contract_fit(player(2), r, DATA, floor_opening=True)
        self.assertEqual(fit["fields"]["contract_length"], 1)
        self.assertGreaterEqual(charges(fit["fields"])[0] * 4000, FLOORS[1])
        self.assertLess(charges(fit["fields"])[0] * 4000 - 40000, FLOORS[1])

    def test_an_observed_schedule_above_the_minimum_is_unchanged(self):
        r = row(year_signed=2025, years=4, season_history=[season(y, 10.0) for y in (2026, 2027, 2028)])
        a, _, _ = contract_fit(player(6), r, DATA, floor_opening=True)
        b, _, _ = contract_fit(player(6), r, DATA)
        self.assertEqual(a, b)


class InSeasonMoveTests(unittest.TestCase):
    """coordinator 11/27 (#48 review): a player who moved in season is charged the deal's full-season 2026 figure, the
    original schedule's 2026 cap hit or the APY when that is missing; the floor stays where that figure is at or near
    the minimum."""

    def test_traded_after_the_snapshot_takes_the_original_2026_cap_hit_and_later_years_stay(self):
        # Marvin Harrison Jr.: ARI's 2026 cap hit on 09-24, HOU's prorated base today
        r = row(team="ARI/HOU", year_signed=2024, years=4, apy=8.843686, value=35.374744,
                season_history=[season(2026, 0.776389, base=1.075, cash=0.776389), season(2027, 5.618829)])
        moved = in_season_full_2026(r, season(2026, 9.647657, base=1.075, cash=1.075, team="Cardinals"))
        self.assertEqual((moved["dollars"], moved["from_club"]), (9647657, "Cardinals"))
        fit, modeled, _ = contract_fit(player(3), r, DATA, floor_opening=True, full_2026=moved)
        self.assertEqual(fit["source_cap_dollars"], [9647657, 5618829])
        self.assertNotIn("opening_floor_dollars", modeled)

    def test_traded_with_no_original_schedule_takes_the_apy(self):
        r = row(team="ATL/PHI", year_signed=2025, years=4, apy=1.9, value=7.6,
                season_history=[season(2026, 0.7, base=1.4, cash=0.7)])
        self.assertEqual(in_season_full_2026(r, None)["dollars"], 1900000)
        # an offseason trade is paid the whole base: not a proration
        whole = row(team="PHI/NE", year_signed=2024, years=3, apy=32.0, value=96.0,
                    season_history=[season(2026, 7.04, base=1.3, cash=28.75)])
        self.assertIsNone(in_season_full_2026(whole, None))

    def test_signed_in_season_takes_the_apy_and_an_extension_or_a_held_deal_does_not(self):
        # Kevin Zeitler: a one-year deal signed after week 3, paid all but three weeks of his base
        r = row(team="Packers", apy=4.266667, value=4.266667,
                season_history=[season(2026, 1.676666, base=1.3, cash=4.05, team="Packers")])
        self.assertEqual(in_season_full_2026(r, None)["how"], "signed in season: the deal's APY")
        extension = dict(r, contract_history=[{"contract_type": "Extension", "status": "Active", "year_signed": 2026,
                                               "yrs": 1, "total": 4.266667}])
        self.assertIsNone(in_season_full_2026(extension, None))
        # the same deal at the same club, whole on 09-24 (pay forfeited since, or a restructure): no move
        self.assertIsNone(in_season_full_2026(r, season(2026, 1.893, base=1.3, cash=4.266667, team="Packers")))

    def test_a_full_figure_at_or_near_the_minimum_keeps_the_floor(self):
        r = row(team="NYG/JAX", apy=1.4025, value=1.4025, season_history=[season(2026, 0.6, base=1.215, cash=0.6)])
        moved = in_season_full_2026(r, None)
        self.assertEqual(moved["dollars"], 1402500)
        fit, modeled, _ = contract_fit(player(5), r, DATA, floor_opening=True, full_2026=moved)
        self.assertEqual(modeled["opening_floor_dollars"], FLOORS[4])
        self.assertNotIn("in_season_2026", modeled)


class StripTests(unittest.TestCase):
    def test_strip_gives_back_the_contracts_the_import_ran_on(self):
        import copy
        import hashlib
        before = {"edits": [{"index": 1, "fields": {"speed": 90}}], "roster_refresh": {
            "contract_initializations": [{"index": 7, "fields": {"contract_value": 9}, "rule": "fr"}],
            "contract_corrections": [{"index": 3, "fields": {"contract_value": 5}, "rule": "DESIGN: rest of base"}]}}
        after = copy.deepcopy(before)
        five = dict.fromkeys(("contract_value", "contract_type", "contract_bonus", "contract_length",
                              "contract_remaining"), 1)
        after["edits"].append({"fields": five, "first": "A", "index": 9, "last": "B", "pool": "primary"})
        plan = after["roster_refresh"]
        plan["contract_initializations"][0].update(fields=five, rule=release_contracts.RULE)
        plan["contract_corrections"][0] = dict(plan["contract_corrections"][0], fields=five,
                                               rule=release_contracts.RULE)
        plan["contract_corrections"].append({"index": 4, "fields": five, "rule": release_contracts.RULE + " [x]"})
        after[release_contracts.RECEIPT] = {
            "rule": release_contracts.RULE, "document_before_sha256": hashlib.sha256(release_contracts.dumps(before).encode()).hexdigest(),
            "contracts_before_sha256": release_contracts.contracts_sha256(before), "layer": {
                "appended_edits": 1, "added_corrections": 1, "had_corrections": True,
                "replaced_corrections": [before["roster_refresh"]["contract_corrections"][0]],
                "replaced_initializers": [before["roster_refresh"]["contract_initializations"][0]]}}
        self.assertEqual(release_contracts.strip(after), before)
        # a 64 MB build drops the base pins: the import still strips
        self.assertEqual(release_contracts.strip(dict(after, other=1)), dict(before, other=1))
        broken = copy.deepcopy(after)
        broken["roster_refresh"]["contract_corrections"][0]["fields"] = {"contract_value": 6}
        with self.assertRaises(ValueError):
            release_contracts.strip(dict(broken, **{release_contracts.RECEIPT: dict(
                after[release_contracts.RECEIPT], layer=dict(after[release_contracts.RECEIPT]["layer"],
                                                               replaced_corrections=[]))}))


SOURCES = Path(os.environ.get("NFL2K5_B81_STANDARD_SOURCES", "") or "missing")
# the OverTheCap snapshot the release import recorded (historical_contracts_active.json, with its parquet beside it)
CONTRACTS = Path(os.environ.get("NFL2K5_B81_CONTRACTS", "") or "missing")
RETAIL_XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", "") or "missing")


ELEVEN_25 = {128: "b5998c412308966f668c0d5f3007e8bbe57c225214a3913d9cf32c196b7fce53",   # the roster lane's 11/25
             64: "285b80bb63fbe795c52b3d0dc58b1c5a2dfd7e1dfcbf399318de46b20d3a7deb"}   # documents (roster-1125)


@unittest.skipUnless((SOURCES / "recipe.json").is_file(), "private release sources absent: NFL2K5_B81_STANDARD_SOURCES")
class ReleaseDocumentTests(unittest.TestCase):
    """The staged 11/25 roster documents carry #48's re-fit: every correction and initializer is well formed and the
    receipt names the pinned OverTheCap snapshot."""

    def test_both_editions_carry_the_contract_refresh(self):
        from tests.mod_editor.test_b81_roster_consistency import RELEASE_ROSTERS
        for memory, (name, _digest) in RELEASE_ROSTERS.items():
            root = SOURCES.parent / f"v10-sources-{memory}" / "assets/files"
            paths = list(root.glob("*_" + name))
            if not paths:
                continue
            with self.subTest(memory=memory):
                document = json.loads(paths[0].read_text(encoding="utf-8"))
                receipt = document["b81_contract_refresh"]
                self.assertEqual(receipt["parquet_sha256"],
                                 "f507960eb66788608de7de1f333c53d0659a24f3bad380a7c9af5aaa5cc490c4")
                self.assertEqual(receipt["asset_updated_at"], "2026-11-26T17:40:56Z")
                plan = document["roster_refresh"]
                fields = {"contract_value", "contract_type", "contract_bonus", "contract_length", "contract_remaining"}
                owned = {i for t in plan["teams"] for i in t["active"] + t["reserves"]}
                for c in plan["contract_corrections"]:
                    self.assertIn(c["index"], owned)
                    self.assertEqual(set(c["fields"]), fields)
                    self.assertEqual(set(c["was"]), fields)
                    self.assertTrue(c["source"].startswith("https://"))
                for c in plan["contract_initializations"]:
                    self.assertEqual(set(c["fields"]), fields)
                    self.assertTrue(1 <= c["fields"]["contract_remaining"] <= c["fields"]["contract_length"] <= 15)
                # Micah Parsons (GB) is under contract through 2029, not on a one-year placeholder
                parsons = next(r for r in plan["players"] if r.get("gsis_id") == "00-0036932")
                entry = [c for c in plan["contract_corrections"] + plan["contract_initializations"]
                         if c["index"] == parsons["index"]]
                self.assertEqual(entry[0]["fields"]["contract_remaining"], 4)
                # coordinator 11/27: Quenton Nelson (traded IND -> SEA after week 8) is charged IND's full 2026 cap hit
                nelson = next(c for c in plan["contract_corrections"]
                              if (c["first"], c["last"]) == ("Quenton", "Nelson"))
                self.assertEqual(nelson["fit"]["source_cap_dollars"], [24200000])
                self.assertEqual((nelson["from_club"], nelson["to_club"]), ("IND", "SEA"))
                # the documents are the 11/25 roster documents plus the import, entry for entry
                before = release_contracts.strip(document)
                self.assertEqual(hashlib.sha256(release_contracts.dumps(before).encode()).hexdigest(),
                                 receipt["document_before_sha256"])
                self.assertEqual(receipt["document_before_sha256"], ELEVEN_25[memory])

    @unittest.skipUnless(CONTRACTS.is_file() and RETAIL_XISO.is_file(),
                         "the recorded contract snapshot (NFL2K5_B81_CONTRACTS) or the retail XISO absent")
    def test_the_64_mb_edition_is_the_retail_fit_with_the_import_run_on_it(self):
        """#48 review: the retail-fit validator passes on the release pair, its contract check (release_contracts
        check_after_fit) re-running the import on the fitted document (a user's-dump base in place of the deleted
        authoring base)."""
        from tests.mod_editor.test_b81_roster_consistency import RELEASE_ROSTERS
        from tools import nfl2k5_roster_retail_fit as fit
        docs = {}
        for memory, (name, _digest) in RELEASE_ROSTERS.items():
            path = next((SOURCES.parent / f"v10-sources-{memory}" / "assets/files").glob("*_" + name))
            docs[memory] = json.loads(path.read_text(encoding="utf-8"))
        base = release_contracts.users_dump_base(release_contracts.strip(docs[128]))
        for document in docs.values():
            for key in ("fa3_free_agent_depth", "free_agent_capacity"):
                if isinstance(document.get(key), dict):
                    document[key] = {k: v for k, v in document[key].items() if k != "base_sha256"}
        report = fit.validate(docs[64], docs[128], base, drop_xbe_sections=True,
                              after_fit=release_contracts.check_after_fit(CONTRACTS))
        failed = [c for c in report["checks"] if not c["ok"]]
        self.assertEqual(failed, [])
        self.assertIn(fit.CONTRACT_CHECK, [c["check"] for c in report["checks"]])
        # the shipped Studio's validate (no import, no snapshot) cannot vouch for the contracts and says so
        bare = fit.validate(docs[64], docs[128], base, drop_xbe_sections=True)
        self.assertEqual([c["check"] for c in bare["checks"] if not c["ok"]], [fit.CONTRACT_CHECK])


if __name__ == "__main__":
    unittest.main()
