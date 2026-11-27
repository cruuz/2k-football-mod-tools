"""b81 #48 (coordinator 11/27): the economy contract import keeps OverTheCap's term when the 2026 cap schedule is
missing, and the release roster documents carry the re-fitted contracts (tools/franchise_economy/release_contracts.py)."""
import json
import os
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys  # noqa: E402
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from tools.franchise_economy.contracts import charges  # noqa: E402
from tools.franchise_economy.import_contracts import contract_fit, fallback_schedule, term_end  # noqa: E402

DATA = json.loads((ROOT / "data/nfl2k5_franchise_economy.json").read_text())
FLOORS = DATA["minimums"]["dollars"]


def player(years_pro):
    return types.SimpleNamespace(record=types.SimpleNamespace(values={"years_pro": years_pro}),
                                 display="Test Player", first="Test", last="Player")


def row(**kw):
    base = {"player": "Test Player", "is_active": True, "year_signed": 2026, "years": 1, "apy": 1.0, "value": 1.0,
            "draft_year": 2022, "draft_overall": None, "season_history": [], "player_page": "https://overthecap.com/x"}
    return {**base, **kw}


def season(year, cap, base=None, cash=None):
    return {"year": str(year), "cap_number": cap, "base_salary": cap if base is None else base,
            "cash_paid": cap if cash is None else cash}


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


SOURCES = Path(os.environ.get("NFL2K5_B81_STANDARD_SOURCES", "") or "missing")


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


if __name__ == "__main__":
    unittest.main()
