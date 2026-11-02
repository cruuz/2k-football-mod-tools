"""Job c5-owners (beta 80): owner patience and the coach hiring pool, sourced data for the coaching carousel. UNWITNESSED.

Checks of the two shipped data files and of the reference decision they carry:

* shape: schema, the 32 clubs, the team index of the roster's coach table, integer tables;
* every row has a source: pinned sources carry a SHA-256, every other URL was fetched and its page contained the names it
  is cited for (the ``url_checks`` block), the owners and 2026 coaches agree with the repo's own 2026 team files;
* spot facts against the sources: the r2 research counts (Baltimore and Pittsburgh 1 change, Las Vegas 14, 209 changes,
  8.04 a year) reproduced by the research's own method, the 2026 offseason's ten changes, a few careers, owners and eras;
* the decision: integer formula, monotone tables, the native table round trip;
* the calibration: the stored closed-loop runs are re-run from the stored records (integer math, a fixed generator, so the
  numbers repeat exactly) and must land near the real league: about 7 changes an offseason, median fired record .31,
  and 8 a year at the stored league scale;
* when the pinned nflverse and Wikipedia inputs are on disk (``NFL2K5_COACH_OWNERS_CACHE``), the builder reproduces both
  files byte for byte.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_coach_owners as co  # noqa: E402
from mod_editor.core import nfl2k5_team_history as th  # noqa: E402

OWNERS = json.loads(co.DEFAULT_OWNERS.read_text(encoding="utf-8"))
POOL = json.loads(co.DEFAULT_POOL.read_text(encoding="utf-8"))
CLUB = {c["team"]: c for c in OWNERS["clubs"]}
PERSON = {p["id"]: p for p in POOL["candidates"]}
TEAMS_DIR = ROOT / "data" / "nfl2k5_teams_2026"
CACHE = Path(os.environ.get("NFL2K5_COACH_OWNERS_CACHE", Path.home() / ".cache" / "nfl2k5-coach-owners"))
CHANGED_IN_2026 = {"ARI", "ATL", "BAL", "BUF", "CLE", "LV", "MIA", "NYG", "PIT", "TEN"}      # the ten clubs that opened 2026 with a new coach


def team_file(club):
    return json.loads((TEAMS_DIR / f"{club}.json").read_text(encoding="utf-8"))


class OwnersShapeTests(unittest.TestCase):
    def test_loader_and_validator_accept_the_shipped_files(self):
        co.validate_owners(co.load_owners())
        co.validate_pool(co.load_pool())

    def test_32_clubs_alphabetical_with_the_roster_team_index(self):
        self.assertEqual([c["team"] for c in OWNERS["clubs"]], sorted(co.CLUBS))
        self.assertEqual(sorted(c["team_index"] for c in OWNERS["clubs"]), list(range(32)))
        for club in OWNERS["clubs"]:
            self.assertEqual(club["team_index"], th.RETAIL_TEAM_INDEX[th.TEAM_ALIASES.get(club["team"], club["team"])])
        self.assertEqual({c["team"] for c in OWNERS["clubs"]}, {p.stem for p in TEAMS_DIR.glob("*.json")})
        # the Rams are index 23 and the Raiders 22 in the roster, whatever their 2026 codes are
        self.assertEqual((CLUB["LAR"]["team_index"], CLUB["LV"]["team_index"], CLUB["ARI"]["team_index"]), (23, 22, 7))

    def test_window_and_counts(self):
        self.assertEqual((OWNERS["window"]["first_season"], OWNERS["window"]["last_season"], OWNERS["window"]["offseasons"]), (1999, 2025, 27))
        self.assertEqual(sum(c["history"]["decisions"] for c in OWNERS["clubs"]), 861)       # 32 x 27, Houston from 2002
        self.assertEqual(sum(c["history"]["changes"] for c in OWNERS["clubs"]), 191)
        self.assertEqual((OWNERS["league"]["decisions"], OWNERS["league"]["changes"]), (861, 191))
        self.assertEqual(sum(OWNERS["league"]["by_offseason"].values()), 191)
        self.assertEqual(CLUB["HOU"]["history"]["first_season"], 2002)
        self.assertEqual(CLUB["HOU"]["history"]["decisions"], 24)
        for club in OWNERS["clubs"]:
            self.assertEqual(club["history"]["changes"], len(club["history"]["changes_log"]), club["team"])
            self.assertEqual(len(club["history"]["head_coaches"]), club["history"]["changes"] + 1, club["team"])

    def test_owner_scales_are_q8_integers_around_one(self):
        scales = [c["fire_scale_q8"] for c in OWNERS["clubs"]]
        self.assertTrue(all(type(v) is int and 128 <= v <= 512 for v in scales))
        self.assertAlmostEqual(sum(scales) / 32 / 256, 1.0, delta=0.03)
        self.assertEqual(CLUB["SEA"]["fire_scale_q8"], 256)             # the new owners have decided nothing yet
        self.assertEqual(CLUB["SEA"]["era"]["decisions"], 0)
        self.assertEqual(max(OWNERS["clubs"], key=lambda c: c["fire_scale_q8"])["team"], "LV")
        self.assertEqual(min(OWNERS["clubs"], key=lambda c: c["fire_scale_q8"])["team"], "CIN")
        # recompute every scale from the stored era counts and the stored prior shape
        k = OWNERS["model"]["fit"]["frailty"]["shape"]
        for club in OWNERS["clubs"]:
            era = club["era"]
            self.assertAlmostEqual(club["fire_scale_q8"], 256 * (era["changes"] + k) / (era["expected_changes"] + k), delta=0.6, msg=club["team"])

    def test_pinned_sources_carry_a_sha256_and_a_fixed_revision(self):
        for key in ("nflverse_games", "wikipedia_owners", "wikipedia_2026_season"):
            pin = OWNERS["sources"][key]
            self.assertRegex(pin["sha256"], r"^[0-9a-f]{64}$", key)
            self.assertTrue(pin["url"].startswith("https://"), key)
        self.assertRegex(OWNERS["sources"]["nflverse_games"]["commit"], r"^[0-9a-f]{40}$")
        self.assertIn("oldid=1381227405", OWNERS["sources"]["wikipedia_owners"]["url"])
        self.assertIn("e28cf00d4fdffa262603191a0b339901d4a7efd0", OWNERS["sources"]["nflverse_games"]["url"])
        # the same games.csv the classic-teams build pinned
        manifest = json.loads((ROOT / "data" / "nfl2k5_classic_teams" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["sources"]["nflverse"]["files"]["games.csv"], OWNERS["sources"]["nflverse_games"]["sha256"])


class EverythingHasASourceTests(unittest.TestCase):
    def test_every_club_row_names_listed_sources(self):
        for club in OWNERS["clubs"]:
            self.assertTrue(club["sources"], club["team"])
            for key in club["sources"]:
                self.assertIn(key, OWNERS["sources"], club["team"])
            self.assertIn(club["owner"]["source"], OWNERS["sources"], club["team"])
            self.assertTrue(club["history"]["current"]["source"].startswith("https://"), club["team"])
            self.assertEqual("wikipedia_2026_season" in club["sources"], club["team"] in CHANGED_IN_2026, club["team"])

    def test_every_cited_url_was_fetched_and_the_page_named_its_subject(self):
        for doc in (OWNERS, POOL):
            urls = co.cited_urls(doc)
            self.assertGreater(len(urls), 30)
            self.assertEqual(set(doc["url_checks"]), urls)
            for url, result in doc["url_checks"].items():
                self.assertEqual(result["http"], 200, url)
                self.assertRegex(result["checked"], r"^2026-\d\d-\d\d$", url)
                self.assertTrue(result["page_contains"], url)

    def test_owner_names_come_from_the_pinned_table(self):
        wikitext = CACHE / "owners_1381227405.wikitext"
        if not wikitext.is_file():
            self.skipTest("pinned owners wikitext not on disk")
        import hashlib
        raw = wikitext.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), OWNERS["sources"]["wikipedia_owners"]["sha256"])
        text = raw.decode("utf-8")
        for club in OWNERS["clubs"]:
            self.assertIn(club["owner"]["name"], text, club["team"])


class SpotFactTests(unittest.TestCase):
    def test_current_coaches_are_the_repo_2026_head_coaches(self):
        for club in OWNERS["clubs"]:
            sourced = team_file(club["team"])["roster"]["head_coach"]
            self.assertEqual(club["history"]["current"]["name"], sourced, club["team"])
            self.assertEqual(club["history"]["head_coaches"][-1]["name"], sourced, club["team"])
            self.assertEqual(club["history"]["head_coaches"][-1]["first"], club["history"]["current"]["since"], club["team"])
            self.assertEqual(club["name"], team_file(club["team"])["name"], club["team"])

    def test_r2_research_counts_are_reproduced_by_its_own_method(self):
        per_club = OWNERS["crosscheck_r2"]["changes_per_club"]
        self.assertEqual((per_club["BAL"], per_club["PIT"], per_club["LV"]), (1, 1, 14))
        self.assertEqual((per_club["NE"], per_club["SEA"], per_club["CIN"]), (3, 3, 3))
        self.assertEqual((per_club["PHI"], per_club["GB"], per_club["DET"], per_club["CLE"]), (4, 4, 10, 11))
        self.assertEqual(OWNERS["crosscheck_r2"]["changes"], 209)
        self.assertEqual(OWNERS["crosscheck_r2"]["per_offseason"], 8.04)
        self.assertEqual(OWNERS["crosscheck_r2"]["median_record_before_a_change"], 0.353)

    def test_opening_day_counts_and_the_2026_offseason(self):
        league = OWNERS["league"]
        self.assertEqual(league["by_offseason"]["2025"], 10)                  # the ten clubs that opened 2026 with a new coach
        changed_2026 = {c["team"] for c in OWNERS["clubs"] if any(e["after_season"] == 2025 for e in c["history"]["changes_log"])}
        self.assertEqual(changed_2026, CHANGED_IN_2026)
        self.assertEqual(league["changes_per_offseason"], 7.074)
        self.assertEqual(CLUB["BAL"]["history"]["changes"], 2)                # Billick > Harbaugh (2008), Harbaugh > Minter (2026)
        self.assertEqual([h["name"] for h in CLUB["BAL"]["history"]["head_coaches"]], ["Brian Billick", "John Harbaugh", "Jesse Minter"])
        self.assertEqual([h["name"] for h in CLUB["PIT"]["history"]["head_coaches"]], ["Bill Cowher", "Mike Tomlin", "Mike McCarthy"])
        self.assertEqual(CLUB["LV"]["history"]["changes"], 13)
        self.assertEqual(max(c["history"]["changes"] for c in OWNERS["clubs"]), 13)
        self.assertEqual(CLUB["CLE"]["history"]["changes"], 10)
        belichick = [h for h in CLUB["NE"]["history"]["head_coaches"] if h["name"] == "Bill Belichick"][0]
        self.assertEqual((belichick["first"], belichick["last"], belichick["seasons"]), (2000, 2023, 24))
        reid = CLUB["PHI"]["history"]["head_coaches"][0]
        self.assertEqual((reid["name"], reid["first"], reid["last"]), ("Andy Reid", 1999, 2012))

    def test_the_2026_departures_have_reason_date_and_a_source(self):
        expected = {"ARI": ("fired", "2026-01-05", False), "ATL": ("fired", "2026-01-04", False), "BAL": ("fired", "2026-01-06", False),
                    "BUF": ("fired", "2026-01-19", False), "CLE": ("fired", "2026-01-05", False), "LV": ("fired", "2026-01-05", False),
                    "MIA": ("fired", "2026-01-08", False), "NYG": ("fired", "2025-11-10", True), "PIT": ("resigned", "2026-01-13", False),
                    "TEN": ("fired", "2025-10-13", True)}
        for team, (reason, date, in_season) in expected.items():
            entry = [e for e in CLUB[team]["history"]["changes_log"] if e["after_season"] == 2025][0]
            self.assertEqual((entry["departure"]["reason"], entry["departure"]["date"], entry["departure"]["in_season"]), (reason, date, in_season), team)
            self.assertTrue(entry["departure"]["source"].startswith("https://"), team)
        daboll = [e for e in CLUB["NYG"]["history"]["changes_log"] if e["after_season"] == 2025][0]
        self.assertEqual((daboll["left"], daboll["arrived"], daboll["record"]), ("Brian Daboll", "John Harbaugh", "4-13-0"))
        tomlin = [e for e in CLUB["PIT"]["history"]["changes_log"] if e["after_season"] == 2025][0]
        self.assertEqual((tomlin["left"], tomlin["arrived"], tomlin["record"], tomlin["tenure"]), ("Mike Tomlin", "Mike McCarthy", "10-7-0", 19))

    def test_owners_and_their_eras(self):
        def owner(team):
            return CLUB[team]["owner"]
        self.assertEqual((owner("DAL")["name"], owner("DAL")["since"], owner("DAL")["acquired"]), ("Jerry Jones", 1989, "purchase"))
        self.assertEqual(CLUB["DAL"]["era"]["first_season"], 1999)           # bought before the window: the whole window is his
        self.assertEqual((owner("BAL")["name"], owner("BAL")["since"], CLUB["BAL"]["era"]["first_season"]), ("Steve Bisciotti", 2004, 2004))
        self.assertEqual((owner("DEN")["name"], owner("DEN")["acquired"], CLUB["DEN"]["era"]["first_season"], CLUB["DEN"]["era"]["decisions"]),
                         ("Rob Walton", "purchase", 2022, 4))
        self.assertEqual((owner("PIT")["name"], owner("PIT")["acquired"], CLUB["PIT"]["era"]["first_season"]), ("Art Rooney II", "family", 1999))
        self.assertEqual((owner("LV")["name"], owner("LV")["acquired"]), ("Mark Davis", "family"))
        self.assertEqual((owner("GB")["acquired"], owner("SEA")["name"], owner("SEA")["since"]), ("public", "Neeru Khosla", 2026))
        purchases_after_1999 = sorted(t for t, c in CLUB.items() if c["owner"]["acquired"] == "purchase" and c["owner"]["since"] > 1999)
        self.assertEqual(purchases_after_1999, ["ATL", "BAL", "BUF", "CAR", "CLE", "DEN", "JAX", "LAR", "MIA", "MIN", "NYJ", "SEA", "WAS"])
        for team, c in CLUB.items():
            expect = c["owner"]["since"] if team in purchases_after_1999 else c["history"]["first_season"]
            self.assertEqual(c["era"]["first_season"], expect, team)

    def test_where_the_data_do_not_support_owner_differences_it_says_so(self):
        frailty = OWNERS["model"]["fit"]["frailty"]
        self.assertEqual(frailty["clubs"], 31)
        self.assertLess(frailty["sum_squared_dispersion"], 31)          # fewer surprises than chance alone would give
        self.assertIn("95%", frailty["rule"])
        self.assertEqual(frailty["shape"], 16.0)


class DecisionTests(unittest.TestCase):
    def test_record_index_rounds_half_up_on_a_17_game_scale(self):
        self.assertEqual([co.record_index(*r) for r in ((17, 0, 0), (0, 17, 0), (8, 9, 0), (9, 8, 0), (8, 8, 1), (4, 12, 0), (12, 4, 0), (8, 8, 0))],
                         [17, 0, 8, 9, 9, 4, 13, 9])
        with self.assertRaises(co.CoachOwnersError):
            co.record_index(0, 0, 0)

    def test_tenure_buckets(self):
        self.assertEqual([co.tenure_bucket(n) for n in (1, 2, 3, 9)], [0, 1, 2, 2])

    def test_tables_are_monotone(self):
        base = OWNERS["model"]["base_permille"]
        for row in base:
            self.assertTrue(all(a >= b for a, b in zip(row, row[1:])))
        for idx in range(18):
            self.assertLessEqual(base[0][idx], base[1][idx])
            self.assertLessEqual(base[1][idx], base[2][idx])
        self.assertEqual(base[2][9], 200)                         # a third-year coach at 9-8 or 8-8: one in five
        self.assertLess(base[0][4], 300)                          # a first-year coach at 4-13 is still more likely kept than fired

    def test_the_integer_formula(self):
        model = OWNERS["model"]
        self.assertEqual(co.fire_permille(model, 256, 4, 13, 0, 5), 693)                       # base, owner 1.0
        self.assertEqual(co.fire_permille(model, 331, 4, 13, 0, 5), (693 * 331 * 256 + 32768) >> 16)
        self.assertEqual(co.fire_permille(model, 1024, 2, 15, 0, 5), 1000)                      # clamped
        self.assertEqual(co.fire_permille(model, 256, 12, 5, 0, 1), model["base_permille"][0][12])
        self.assertLess(co.fire_permille(model, CLUB["CIN"]["fire_scale_q8"], 8, 9, 0, 6), co.fire_permille(model, CLUB["LV"]["fire_scale_q8"], 8, 9, 0, 6))
        wider = dict(model, league_q8=288)
        self.assertGreater(co.fire_permille(wider, 256, 8, 9, 0, 6), co.fire_permille(model, 256, 8, 9, 0, 6))
        self.assertTrue(co.decide(693, 692) and not co.decide(693, 693) and co.decide(693, 1692))

    def test_native_table_round_trip(self):
        blob = co.pack_native(OWNERS)
        self.assertEqual(len(blob), co.NATIVE_SIZE)
        self.assertEqual(co.NATIVE_SIZE, 176)
        back = co.unpack_native(blob)
        self.assertEqual(back["model"]["base_permille"], OWNERS["model"]["base_permille"])
        for club in OWNERS["clubs"]:
            self.assertEqual(back["owner_q8_by_team_index"][club["team_index"]], club["fire_scale_q8"])
        # the packed tables give the same answers as the document
        for w in range(0, 18):
            for n in (1, 2, 3):
                self.assertEqual(co.fire_permille(back["model"], back["owner_q8_by_team_index"][24], w, 17 - w, 0, n),
                                 co.fire_permille(OWNERS["model"], CLUB["BAL"]["fire_scale_q8"], w, 17 - w, 0, n))
        with self.assertRaises(co.CoachOwnersError):
            co.unpack_native(blob[:-2])

    def test_the_generator_is_the_same_on_every_platform(self):
        rng = co.Lcg(1)
        self.assertEqual([rng.u32() for _ in range(4)], [4028743203, 1099605407, 1276115407, 660828786])


class CalibrationTests(unittest.TestCase):
    def test_the_stored_default_run_repeats_exactly_and_matches_the_real_league(self):
        stored = OWNERS["calibration"]["simulation"]
        got = co.simulate(OWNERS, stored["seed"], stored["replications"], stored["burn_in_seasons"], stored["measured_seasons"])
        self.assertEqual(got, stored["result"])
        real = OWNERS["calibration"]["real"]
        self.assertAlmostEqual(got["changes_per_offseason"], real["changes_per_offseason"], delta=0.45)       # 7.25 vs 7.07
        self.assertEqual(got["median_fired_win_pct"], real["median_fired_win_pct"])                          # .312, a 5-11 season
        self.assertEqual(got["median_tenure_when_fired"], real["median_tenure_when_fired"])
        for sim, fact in zip(got["fired_rate_by_tenure"], real["fired_rate_by_tenure"]):
            self.assertAlmostEqual(sim, fact, delta=0.02)
        self.assertGreater(got["fewest_in_an_offseason"], -1)
        self.assertLessEqual(got["most_in_an_offseason"], 20)

    def test_the_stored_headline_run_reaches_eight_a_year(self):
        stored = OWNERS["calibration"]["simulation_r2_headline"]
        got = co.simulate(OWNERS, stored["seed"], stored["replications"], stored["burn_in_seasons"], stored["measured_seasons"],
                          league_q8=stored["league_q8"])
        self.assertEqual(got, stored["result"])
        self.assertAlmostEqual(got["changes_per_offseason"], 8.0, delta=0.15)
        self.assertEqual(stored["league_q8"], 288)
        self.assertLess(OWNERS["calibration"]["simulation"]["result"]["changes_per_offseason"], got["changes_per_offseason"])

    def test_the_model_replayed_on_the_real_seasons(self):
        replay = OWNERS["calibration"]["replay_on_real_seasons"]
        self.assertAlmostEqual(replay["expected_changes"], replay["real_changes"], delta=6)               # 188.5 vs 191
        self.assertEqual(replay["real_changes"], 191)
        self.assertEqual(replay["median_win_pct_of_the_fired"], OWNERS["calibration"]["real"]["median_fired_win_pct"])
        self.assertEqual(sorted(OWNERS["calibration"]["records"]), sorted(co.CLUBS))
        for club, line in OWNERS["calibration"]["records"].items():
            seq = co.parse_records(line)
            self.assertEqual(len(seq), 24 if club == "HOU" else 27, club)
            self.assertTrue(all(w + l + t in (16, 17) for w, l, t in seq), club)
        # the stored real records are the same games the club rows count: Baltimore's 2025 was 8-9
        self.assertEqual(co.parse_records(OWNERS["calibration"]["records"]["BAL"])[-1], (8, 9, 0))

    def test_a_quiet_owner_fires_less_than_a_restless_one_on_the_same_records(self):
        quiet = json.loads(json.dumps(OWNERS))
        restless = json.loads(json.dumps(OWNERS))
        for c in quiet["clubs"]:
            c["fire_scale_q8"] = 205
        for c in restless["clubs"]:
            c["fire_scale_q8"] = 330
        a = co.simulate(quiet, 7, 20, 20, 20)["changes_per_offseason"]
        b = co.simulate(restless, 7, 20, 20, 20)["changes_per_offseason"]
        self.assertLess(a, b - 1.0)


class PoolTests(unittest.TestCase):
    def test_shape(self):
        self.assertEqual(POOL["schema"], co.POOL_SCHEMA)
        self.assertGreaterEqual(len(POOL["candidates"]), 38)
        self.assertEqual(len({p["id"] for p in POOL["candidates"]}), len(POOL["candidates"]))
        for person in POOL["candidates"]:
            self.assertRegex(person["first"] + person["last"], r"^[A-Za-z.'\- ]+$", person["id"])
            self.assertTrue(person["sources"], person["id"])
            self.assertIn(person["status"], ("employed", "available"), person["id"])
            self.assertEqual(person["status"] == "available", person["team_2026"] is None, person["id"])
            if person["team_2026"] is not None:
                self.assertIn(person["team_2026"], co.CLUBS, person["id"])

    def test_nobody_in_the_pool_is_a_2026_head_coach(self):
        heads = {team_file(c)["roster"]["head_coach"] for c in co.CLUBS}
        for person in POOL["candidates"]:
            self.assertNotIn(f"{person['first']} {person['last']}", heads, person["id"])

    def test_the_defensive_coordinators_match_the_repo_file(self):
        defense = json.loads((ROOT / "data" / "vip" / "defense_identity_2026.json").read_text(encoding="utf-8"))
        coordinators = [p for p in POOL["candidates"] if p["kind"] == "coordinator"]
        self.assertEqual(len(coordinators), 31)                                  # Tampa Bay's head coach is its own coordinator
        for person in coordinators:
            row = defense["teams"][person["defense_identity_team"]]
            self.assertEqual(f"{person['first']} {person['last']}", row["dc"], person["id"])
        employed = {p["team_2026"] for p in coordinators if p["status"] == "employed"}
        self.assertEqual(employed, set(co.CLUBS) - {"TB", "CAR"})
        self.assertEqual([p["id"] for p in coordinators if p["status"] == "available"], ["ejiro-evero"])

    def test_spot_facts(self):
        fangio = PERSON["vic-fangio"]
        self.assertEqual((fangio["team_2026"], fangio["role_2026"], fangio["side"]), ("PHI", "Defensive coordinator", "defense"))
        self.assertEqual((fangio["head_coach_record"]["wins"], fangio["head_coach_record"]["last_club"]), (19, "DEN"))
        morris = PERSON["raheem-morris"]
        self.assertEqual((morris["team_2026"], morris["head_coach_record"]["last_club"], morris["head_coach_record"]["last_season"]), ("SF", "ATL", 2025))
        evero = PERSON["ejiro-evero"]
        self.assertEqual((evero["status"], evero["team_2026"], evero["head_coach_record"]), ("available", None, None))
        self.assertEqual(PERSON["chris-o-leary"]["last"], "O'Leary")
        tomlin = PERSON["mike-tomlin"]["head_coach_record"]
        self.assertEqual((tomlin["wins"], tomlin["losses"], tomlin["ties"], tomlin["playoff_wins"], tomlin["playoff_losses"]), (193, 114, 2, 8, 12))
        self.assertEqual(PERSON["mike-tomlin"]["status"], "available")

    def test_records_of_coaches_fired_in_season_stop_at_the_firing(self):
        # the pinned Wikipedia / NFL.com figures: Callahan 4-19, Daboll 20-40-1 (one playoff game won, one lost), Eberflus 14-32, Allen 26-53
        def record(pid):
            r = PERSON[pid]["head_coach_record"]
            return r["wins"], r["losses"], r["ties"]
        self.assertEqual(record("brian-callahan"), (4, 19, 0))
        self.assertEqual(record("brian-daboll"), (20, 40, 1))
        self.assertEqual((PERSON["brian-daboll"]["head_coach_record"]["playoff_wins"], PERSON["brian-daboll"]["head_coach_record"]["playoff_losses"]), (1, 1))
        self.assertEqual(record("matt-eberflus"), (14, 32, 0))
        self.assertEqual(record("dennis-allen"), (26, 53, 0))
        self.assertEqual(record("mike-mcdaniel"), (35, 33, 0))
        self.assertEqual(record("jonathan-gannon"), (15, 36, 0))
        self.assertEqual(record("sean-mcdermott"), (98, 50, 0))
        for exit_ in POOL["in_season_exits"]:
            self.assertIn(exit_["source"], POOL["url_checks"])

    def test_left_out_are_listed_with_a_reason(self):
        names = {item["name"] for item in POOL["left_out"]}
        self.assertEqual(names, {"Antonio Pierce", "Jerod Mayo", "Pete Carroll", "Todd Wash"})
        for item in POOL["left_out"]:
            self.assertTrue(item["reason"])
            self.assertTrue(item["source"] is None or item["source"] in POOL["url_checks"])


class BuilderReproducesTheFilesTests(unittest.TestCase):
    """Needs the pinned nflverse games.csv and the two pinned Wikipedia texts (they are not shipped)."""

    def test_rebuild_is_byte_identical(self):
        needed = [CACHE / "games.csv", CACHE / "owners_1381227405.wikitext", CACHE / "season2026_1383458077.wikitext"]
        if not all(p.is_file() for p in needed):
            self.skipTest("pinned inputs not on disk (set NFL2K5_COACH_OWNERS_CACHE)")
        spec = importlib.util.spec_from_file_location("nfl2k5_coach_owners_build", ROOT / "tools" / "nfl2k5_coach_owners_build.py")
        builder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = builder
        spec.loader.exec_module(builder)
        builder.CITED.clear()
        self.assertEqual(builder.main(["--check", "--games", str(needed[0]), "--owners-wikitext", str(needed[1]),
                                       "--season-wikitext", str(needed[2])]), 0)


if __name__ == "__main__":
    unittest.main()
