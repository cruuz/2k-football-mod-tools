"""Job j5-seed (b780): the real-history seed data ``data/nfl2k5_history_2026.json`` and its builder.

The franchise History screen starts from real NFL history, so every value in the seed must come from a pinned source and must be
right. These tests need no network, no game files and no emulator (pure Python, run everywhere). Proof level:

* **schema and pins**: the data file's shape, the 32 clubs, 24 seasons x 32 clubs, the pinned source digests, and that the
  pins file, the tool's constants and the data file agree;
* **facts**: spot checks of well-known results against the shipped data (2007 Patriots 16-0, 2008 Lions 0-16, Manning's
  5,477 yards in 2013, Payton's 16,726 career rushing yards for the Bears, the Class of 2026, and so on), and the shipped
  champions history (``data/nfl2k5_champions_2026.json``, a different pinned source) must agree with this one on every Super
  Bowl champion, score, Super Bowl MVP and AP MVP of 2002..2025;
* **builder logic**: the NFL division tie-break engine on hand-made seasons and on the real 2025 NFC South tie, the wikitable
  reader on rowspans, the record-holder parser, the name and club helpers;
* **second sources**: the data file records what Wikipedia's final standings, nflverse statistics and the annual leader lists
  said about it at build time; the tests require that nothing disagreed except the one explained Wikipedia error.

A full rebuild from the pinned inputs (``tools/b780_history_seed.py --check``) needs the network or a filled cache; set
``NFL2K5_HISTORY_SEED_CACHE`` to a cache folder to run it here (otherwise that one test is skipped).
"""
from __future__ import annotations

import collections
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_champions_history as champions  # noqa: E402

TOOL_PATH = ROOT / "tools" / "b780_history_seed.py"
DATA_PATH = ROOT / "data" / "nfl2k5_history_2026.json"
PINS_PATH = ROOT / "tools" / "b780_history_seed_pins.json"
CHAMPIONS_PATH = ROOT / "data" / "nfl2k5_champions_2026.json"


def load_tool():
    spec = importlib.util.spec_from_file_location("b780_history_seed", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["b780_history_seed"] = module
    spec.loader.exec_module(module)
    return module


tool = load_tool()
DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
CHAMPIONS = json.loads(CHAMPIONS_PATH.read_text(encoding="utf-8"))
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def team(season: int, club: str) -> dict:
    block = next(s for s in DATA["seasons"] if s["season"] == season)
    return next(t for t in block["teams"] if t["club"] == club)


def season_block(season: int) -> dict:
    return next(s for s in DATA["seasons"] if s["season"] == season)


def record(identifier: str) -> dict:
    return next(r for r in DATA["nfl_records"] if r["id"] == identifier)


def winners(season: int, award: str) -> list[dict]:
    return next(w for w in DATA["awards"]["winners"] if w["season"] == season and w["award"] == award)["winners"]


def hof(name: str) -> dict:
    return next(m for m in DATA["hall_of_fame"]["members"] if m["name"] == name)


class SchemaTests(unittest.TestCase):
    def test_header_and_top_level_keys(self):
        self.assertEqual(DATA["schema"], "nfl2k5_history_seed/v1")
        self.assertEqual((DATA["base_year"], DATA["first_season"], DATA["last_season"]), (2026, 2002, 2025))
        self.assertEqual(set(DATA), {"schema", "base_year", "first_season", "last_season", "rules", "sources", "clubs",
                                     "playoff_codes", "seasons", "awards", "nfl_records", "nfl_career_leaders", "hall_of_fame",
                                     "pending_candidates", "checks"})
        self.assertEqual(DATA["playoff_codes"], ["missed", "lost_wild_card", "lost_divisional", "lost_conference",
                                                 "lost_super_bowl", "champion"])

    def test_the_file_is_the_writers_output_byte_for_byte(self):
        text = DATA_PATH.read_text(encoding="utf-8")
        self.assertEqual(text, tool.dumps(DATA) + "\n")
        self.assertNotIn("\r", text)

    def test_thirty_two_clubs_in_arena_order(self):
        clubs = DATA["clubs"]
        self.assertEqual(len(clubs), 32)
        self.assertEqual(len({c["id"] for c in clubs}), 32)
        self.assertEqual([c["nickname_2004"] for c in clubs], list(champions.CLUBS))
        self.assertEqual([c["arena_index"] for c in clubs], list(range(32)))
        divisions = collections.Counter(c["division"] for c in clubs)
        self.assertEqual(sorted(divisions.values()), [4] * 8)
        for club in clubs:
            names = club["names"]
            self.assertEqual(names[0]["first"], 2002)
            self.assertEqual(names[-1]["last"], 2025)
            for a, b in zip(names, names[1:]):
                self.assertEqual(a["last"] + 1, b["first"])
        by_id = {c["id"]: c for c in clubs}
        self.assertEqual([n["name"] for n in by_id["LAR"]["names"]], ["St. Louis Rams", "Los Angeles Rams"])
        self.assertEqual([n["name"] for n in by_id["WAS"]["names"]],
                         ["Washington Redskins", "Washington Football Team", "Washington Commanders"])
        self.assertEqual(by_id["LV"]["names"][0]["name"], "Oakland Raiders")
        self.assertEqual(by_id["LAC"]["names"][0]["name"], "San Diego Chargers")

    def test_every_club_appears_once_in_every_season(self):
        ids = {c["id"] for c in DATA["clubs"]}
        self.assertEqual([s["season"] for s in DATA["seasons"]], list(range(2002, 2026)))
        for block in DATA["seasons"]:
            self.assertEqual([t["club"] for t in block["teams"]], [c["id"] for c in DATA["clubs"]], block["season"])
            self.assertEqual({t["club"] for t in block["teams"]}, ids)

    def test_no_duplicate_rows_anywhere(self):
        keys = [(w["season"], w["award"]) for w in DATA["awards"]["winners"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), 24 * 8)
        ids = [r["id"] for r in DATA["nfl_records"]]
        self.assertEqual(len(ids), len(set(ids)))
        members = [(m["name"], m["class"]) for m in DATA["hall_of_fame"]["members"]]
        self.assertEqual(len(members), len(set(members)))
        gsis = [p["gsis_id"] for p in DATA["pending_candidates"]["players"]]
        self.assertEqual(len(gsis), len(set(gsis)))
        for category, rows in DATA["nfl_career_leaders"].items():
            self.assertEqual(len({r["name"] for r in rows}), len(rows), category)


class SeasonTests(unittest.TestCase):
    def test_every_season_is_internally_consistent(self):
        for block in DATA["seasons"]:
            season = block["season"]
            teams = block["teams"]
            games = 17 if season >= 2021 else 16
            self.assertEqual(block["regular_season_games"], games)
            self.assertEqual(block["playoff_teams"], 14 if season >= 2020 else 12)
            self.assertEqual(sum(t["w"] for t in teams), sum(t["l"] for t in teams), season)
            self.assertEqual(sum(t["t"] for t in teams) % 2, 0, season)
            self.assertEqual(sum(t["pf"] for t in teams), sum(t["pa"] for t in teams), season)
            for t in teams:
                played = t["w"] + t["l"] + t["t"]
                if (season, t["club"]) in ((2022, "BUF"), (2022, "CIN")):     # the Bills-Bengals game was never finished
                    self.assertEqual(played, 16)
                else:
                    self.assertEqual(played, games, (season, t["club"]))
                self.assertEqual(sum(t["div"]), 6, (season, t["club"]))
                self.assertLessEqual(sum(t["conf"]), 12 + 1)
                self.assertIn(t["playoffs"], DATA["playoff_codes"])
            by_division = collections.defaultdict(list)
            clubs = {c["id"]: c for c in DATA["clubs"]}
            for t in teams:
                by_division[clubs[t["club"]]["division"]].append(t["place"])
            self.assertEqual(len(by_division), 8)
            for places in by_division.values():
                self.assertEqual(sorted(places), [1, 2, 3, 4])
            # the playoff field
            counts = collections.Counter(t["playoffs"] for t in teams)
            self.assertEqual(counts["champion"], 1)
            self.assertEqual(counts["lost_super_bowl"], 1)
            self.assertEqual(counts["lost_conference"], 2)
            self.assertEqual(counts["lost_divisional"], 4)
            self.assertEqual(counts["lost_wild_card"], 4 if season < 2020 else 6)
            self.assertEqual(sum(1 for t in teams if t["playoffs"] != "missed"), block["playoff_teams"])
            self.assertEqual(sum(1 for t in teams if t.get("bye")), 4 if season < 2020 else 2)
            self.assertEqual(sum(1 for t in teams if t["place"] == 1), 8)
            champion = next(t["club"] for t in teams if t["playoffs"] == "champion")
            runner_up = next(t["club"] for t in teams if t["playoffs"] == "lost_super_bowl")
            self.assertEqual((block["champion"], block["runner_up"]), (champion, runner_up))
            self.assertGreater(block["champion_points"], block["runner_up_points"])
            self.assertEqual(block["super_bowl_number"], season - 1965)

    def test_well_known_seasons(self):
        patriots = team(2007, "NE")
        self.assertEqual((patriots["w"], patriots["l"], patriots["t"], patriots["pf"], patriots["pa"]), (16, 0, 0, 589, 274))
        self.assertEqual((patriots["playoffs"], patriots["place"], patriots["coach"]), ("lost_super_bowl", 1, "Bill Belichick"))
        self.assertTrue(patriots["bye"])
        giants = team(2007, "NYG")
        self.assertEqual((giants["w"], giants["l"], giants["playoffs"], giants["place"]), (10, 6, "champion", 2))
        block = season_block(2007)
        self.assertEqual((block["super_bowl"], block["champion"], block["champion_points"], block["runner_up_points"]),
                         ("XLII", "NYG", 17, 14))
        lions = team(2008, "DET")
        self.assertEqual((lions["w"], lions["l"], lions["place"], lions["label"]), (0, 16, 4, "DET"))
        self.assertEqual(team(2016, "CLE")["w"], 1)
        self.assertEqual((team(2017, "CLE")["w"], team(2017, "CLE")["l"]), (0, 16))
        self.assertEqual(sorted(t["club"] for t in season_block(2016)["teams"] if t["t"]), ["ARI", "CIN", "SEA", "WAS"])
        texans = team(2002, "HOU")
        self.assertEqual((texans["w"], texans["l"], texans["coach"]), (4, 12, "Dom Capers"))
        self.assertEqual((team(2022, "BUF")["w"], team(2022, "BUF")["l"], team(2022, "CIN")["w"], team(2022, "CIN")["l"]),
                         (13, 3, 12, 4))
        self.assertEqual((season_block(2025)["champion"], season_block(2025)["runner_up"],
                          season_block(2025)["champion_points"], season_block(2025)["runner_up_points"]), ("SEA", "NE", 29, 13))
        self.assertEqual((season_block(2002)["champion"], season_block(2002)["champion_points"]), ("TB", 48))
        # the Giants' page, as the History screen will list it
        g11 = team(2011, "NYG")
        self.assertEqual((g11["w"], g11["l"], g11["place"], g11["playoffs"], g11["coach"]), (9, 7, 1, "champion", "Tom Coughlin"))
        g22 = team(2022, "NYG")
        self.assertEqual((g22["w"], g22["l"], g22["t"], g22["place"], g22["playoffs"]), (9, 7, 1, 3, "lost_divisional"))
        self.assertEqual(g22["coach"], "Brian Daboll")

    def test_relocated_clubs_carry_the_label_and_name_of_their_year(self):
        self.assertEqual((team(2015, "LAR")["label"], team(2015, "LAR")["name"]), ("STL", "St. Louis Rams"))
        self.assertEqual((team(2016, "LAR")["label"], team(2016, "LAR")["name"]), ("LAR", "Los Angeles Rams"))
        self.assertEqual((team(2016, "LAC")["label"], team(2017, "LAC")["label"]), ("SD", "LAC"))
        self.assertEqual((team(2019, "LV")["label"], team(2020, "LV")["label"]), ("OAK", "LV"))
        self.assertEqual([team(y, "WAS")["name"] for y in (2019, 2020, 2021, 2022)],
                         ["Washington Redskins", "Washington Football Team", "Washington Football Team", "Washington Commanders"])

    def test_interim_coaches_and_the_tie_rule(self):
        # the coach with the most games; a tie goes to the coach whose game came first
        cowboys = team(2010, "DAL")
        self.assertEqual((cowboys["coach"], cowboys["coach_games"]), ("Wade Phillips", 8))
        self.assertEqual(cowboys["other_coaches"], [["Jason Garrett", 8]])
        giants17 = team(2017, "NYG")
        self.assertEqual((giants17["coach"], giants17["coach_games"], giants17["other_coaches"]),
                         ("Ben McAdoo", 12, [["Steve Spagnuolo", 4]]))
        browns = team(2018, "CLE")
        self.assertEqual((browns["coach"], browns["other_coaches"]), ("Hue Jackson", [["Gregg Williams", 8]]))
        for block in DATA["seasons"]:
            for t in block["teams"]:
                if "other_coaches" in t:
                    total = t["coach_games"] + sum(n for _c, n in t["other_coaches"])
                    self.assertEqual(total, t["w"] + t["l"] + t["t"])
                    self.assertGreaterEqual(t["coach_games"], max(n for _c, n in t["other_coaches"]))

    def test_tiebreak_notes_and_no_unbroken_ties(self):
        steps = collections.Counter(t["tiebreak"] for b in DATA["seasons"] for t in b["teams"] if "tiebreak" in t)
        self.assertNotIn("unresolved", steps)
        self.assertGreater(sum(steps.values()), 50)
        carolina, tampa = team(2025, "CAR"), team(2025, "TB")
        self.assertEqual((carolina["place"], tampa["place"]), (1, 2))              # the three-way tie of 2025 (CAR, TB, ATL)
        self.assertEqual(carolina["tiebreak"], "head_to_head")
        self.assertEqual(team(2025, "ATL")["place"], 3)

    def test_playoff_seeds_follow_the_field_the_byes_and_the_division_winners(self):
        divisions = {c["id"]: c["division"] for c in DATA["clubs"]}
        for block in DATA["seasons"]:
            seeded = [t for t in block["teams"] if "seed" in t]
            self.assertEqual({t["club"] for t in seeded}, {t["club"] for t in block["teams"] if t["playoffs"] != "missed"},
                             block["season"])
            for conference in ("AFC", "NFC"):
                seeds = sorted(t["seed"] for t in seeded if divisions[t["club"]].startswith(conference))
                self.assertEqual(seeds, list(range(1, 8 if block["season"] >= 2020 else 7)), (block["season"], conference))
            for t in seeded:
                self.assertEqual(t["seed"] <= 4, t["place"] == 1, (block["season"], t["club"]))
                self.assertEqual(bool(t.get("bye")), t["seed"] <= (1 if block["season"] >= 2020 else 2), (block["season"], t["club"]))
            self.assertTrue(all("seed" not in t for t in block["teams"] if t["playoffs"] == "missed"))
        self.assertEqual((team(2007, "NE")["seed"], team(2007, "NYG")["seed"]), (1, 5))          # the Giants won it all as a 5 seed
        self.assertEqual(team(2002, "TB")["seed"], 2)
        self.assertEqual(team(2010, "SEA")["seed"], 4)                                           # 7-9 division champion

    def test_the_coach_of_the_year_coached_that_club_that_year(self):
        for entry in DATA["awards"]["winners"]:
            if entry["award"] != "coy":
                continue
            winner = entry["winners"][0]
            row = team(entry["season"], winner["club"])
            if (entry["season"], winner["club"]) == (2012, "IND"):
                # Bruce Arians led the Colts for 12 games while Chuck Pagano was treated for leukemia; the league's record
                # credits the season to Pagano, so the games file does too (the Coach of the Year went to Arians)
                self.assertEqual((row["coach"], winner["name"]), ("Chuck Pagano", "Bruce Arians"))
                self.assertNotIn("other_coaches", row)
            else:
                self.assertEqual(row["coach"], winner["name"], (entry["season"], winner))

    def test_club_totals_are_the_sums_of_the_season_rows(self):
        for club in DATA["clubs"]:
            rows = [team(s["season"], club["id"]) for s in DATA["seasons"]]
            totals = club["totals_2002_2025"]
            self.assertEqual(totals["w"], sum(r["w"] for r in rows))
            self.assertEqual(totals["l"], sum(r["l"] for r in rows))
            self.assertEqual(totals["pf"], sum(r["pf"] for r in rows))
            self.assertEqual(totals["division_titles"], sum(r["place"] == 1 for r in rows))
            self.assertEqual(totals["playoff_trips"], sum(r["playoffs"] != "missed" for r in rows))
            self.assertEqual(totals["super_bowl_wins"], sum(r["playoffs"] == "champion" for r in rows))
            self.assertEqual(totals["conference_titles"], totals["super_bowl_wins"] + totals["super_bowl_losses"])
        self.assertEqual(sum(c["totals_2002_2025"]["super_bowl_wins"] for c in DATA["clubs"]), 24)
        # every playoff game has a winner and a loser: 11 games a year in the 12-team format (to 2019), 13 after
        playoff_games = 11 * 18 + 13 * 6
        self.assertEqual(sum(c["totals_2002_2025"]["playoff_w"] for c in DATA["clubs"]), playoff_games)
        self.assertEqual(sum(c["totals_2002_2025"]["playoff_l"] for c in DATA["clubs"]), playoff_games)
        for club in DATA["clubs"]:
            totals = club["totals_2002_2025"]
            self.assertEqual(totals["seasons"], 24)
            self.assertEqual(totals["winning_seasons"], sum(team(s["season"], club["id"])["w"] > team(s["season"], club["id"])["l"]
                                                            for s in DATA["seasons"]))
        by_id = {c["id"]: c["totals_2002_2025"] for c in DATA["clubs"]}
        # NE won Super Bowls XXXVIII, XXXIX, XLIX, LI and LIII (seasons 2003, 2004, 2014, 2016, 2018); NYG XLII and XLVI;
        # PIT XL and XLIII
        self.assertEqual((by_id["NE"]["super_bowl_wins"], by_id["NYG"]["super_bowl_wins"], by_id["PIT"]["super_bowl_wins"]),
                         (5, 2, 2))

    def test_every_super_bowl_matches_the_shipped_champions_history(self):
        """A second pinned source (three Wikipedia pages read for the champions page) must say the same."""

        by_game = {row["super_bowl"]: row for row in CHAMPIONS["seasons"]}
        names = {club["id"]: {n["name"] for n in club["names"]} for club in DATA["clubs"]}
        for block in DATA["seasons"]:
            row = by_game[block["super_bowl_number"]]
            self.assertEqual(row["season"], block["season"])
            for key, club, points in (("champion", block["champion"], block["champion_points"]),
                                      ("runner_up", block["runner_up"], block["runner_up_points"])):
                self.assertIn(row[key], names[club], (block["season"], key, row[key]))
                self.assertEqual(row[key + "_points"], points, (block["season"], key))


class AwardTests(unittest.TestCase):
    def test_eight_award_kinds(self):
        self.assertEqual([k["id"] for k in DATA["awards"]["kinds"]],
                         ["mvp", "opoy", "dpoy", "oroy", "droy", "cpoy", "coy", "sb_mvp"])

    def test_every_winner_has_a_known_club_and_position(self):
        clubs = {c["id"] for c in DATA["clubs"]}
        for entry in DATA["awards"]["winners"]:
            self.assertTrue(entry["winners"])
            for w in entry["winners"]:
                self.assertIn(w["club"], clubs)
                if entry["award"] == "coy":
                    self.assertEqual(w["position"], "HC")
                else:
                    self.assertIn(w["position"], tool.POSITIONS, w)
                self.assertTrue(w["name"].strip() and w["name"] == w["name"].strip())
                self.assertNotRegex(w["name"], r"[\d()*~^]")

    def test_shared_awards_list_everyone(self):
        shared = [(e["season"], e["award"]) for e in DATA["awards"]["winners"] if len(e["winners"]) > 1]
        self.assertEqual(shared, [(2003, "mvp"), (2005, "cpoy")])
        self.assertEqual([w["name"] for w in winners(2003, "mvp")], ["Peyton Manning", "Steve McNair"])
        self.assertEqual([w["club"] for w in winners(2003, "mvp")], ["IND", "TEN"])
        self.assertEqual([w["name"] for w in winners(2005, "cpoy")], ["Tedy Bruschi", "Steve Smith Sr."])

    def test_spot_checks(self):
        expected = {
            (2002, "mvp"): ("Rich Gannon", "LV"), (2013, "mvp"): ("Peyton Manning", "DEN"),
            (2012, "mvp"): ("Adrian Peterson", "MIN"), (2002, "opoy"): ("Priest Holmes", "KC"),
            (2008, "dpoy"): ("James Harrison", "PIT"), (2012, "oroy"): ("Robert Griffin III", "WAS"),
            (2011, "droy"): ("Von Miller", "DEN"), (2016, "coy"): ("Jason Garrett", "DAL"),
            (2007, "sb_mvp"): ("Eli Manning", "NYG"), (2002, "sb_mvp"): ("Dexter Jackson", "TB"),
            (2025, "sb_mvp"): ("Kenneth Walker III", "SEA"), (2022, "cpoy"): ("Geno Smith", "SEA"),
            (2002, "cpoy"): ("Tommy Maddox", "PIT"), (2011, "coy"): ("Jim Harbaugh", "SF"),
        }
        for (season, award), (name, club) in expected.items():
            first = winners(season, award)[0]
            self.assertEqual((first["name"], first["club"]), (name, club), (season, award))

    def test_mvp_and_super_bowl_mvp_agree_with_the_champions_history(self):
        """data/nfl2k5_champions_2026.json reads the same three pages through another parser."""

        by_game = {row["super_bowl"]: row for row in CHAMPIONS["seasons"]}
        for season in range(2002, 2026):
            row = by_game[season - 1965]
            self.assertEqual(winners(season, "mvp")[0]["name"], row["season_mvp"]["name"], season)
            self.assertEqual(winners(season, "sb_mvp")[0]["name"], row["super_bowl_mvp"]["name"], season)
            self.assertEqual(winners(season, "sb_mvp")[0]["position"], row["super_bowl_mvp"]["position"], season)
            self.assertEqual(winners(season, "mvp")[0]["position"], row["season_mvp"]["position"], season)

    def test_the_sourced_player_honors_agree_with_the_award_winners(self):
        """data/nfl2k5_honors_2026.json was read from the same pages by a different parser (job F5) and lists the 2026
        roster's players only; every award it gives for 2002..2025 must be one of the winners here."""

        honors = json.loads((ROOT / "data" / "nfl2k5_honors_2026.json").read_text(encoding="utf-8"))
        kind_of = {"mvp": "mvp", "opoy": "opoy", "dpoy": "dpoy", "oroy": "oroy", "droy": "droy", "super_bowl_mvp": "sb_mvp"}
        seen = 0
        for player in honors["players"]:
            for honor in player["honors"]:
                if honor["honor"] in kind_of and 2002 <= honor["season"] <= 2025:
                    names = [w["name"] for w in winners(honor["season"], kind_of[honor["honor"]])]
                    full = f"{player['first']} {player['last']}"
                    self.assertTrue(any(tool.same_person(full, n) for n in names), (honor, full, names))
                    seen += 1
        self.assertGreaterEqual(seen, 30)

    def test_the_champion_is_the_super_bowl_mvps_club_when_he_won(self):
        for season in range(2002, 2026):
            club = winners(season, "sb_mvp")[0]["club"]
            self.assertEqual(club, season_block(season)["champion"], season)


class RecordTests(unittest.TestCase):
    def test_the_footers_twelve_categories_by_three_scopes_plus_two_extras(self):
        categories = {r["category"] for r in DATA["nfl_records"]}
        self.assertEqual(categories, set(tool.RECORD_SPECS))
        self.assertEqual(len(categories), 14)
        self.assertEqual(len(DATA["nfl_records"]), 42)
        # the ids of the extension footer (b780 j23-footer, nfl2k5_franchise_extension.RECORD_CATEGORIES / LEADER_CATEGORIES)
        self.assertEqual(tool.FOOTER_RECORD_CATEGORIES, ("passing_yards", "passing_td", "completions", "rushing_yards", "rushing_td",
                                                         "receptions", "receiving_yards", "receiving_td", "sacks_half",
                                                         "interceptions", "tackles", "forced_fumbles"))
        self.assertEqual(tool.FOOTER_LEADER_CATEGORIES, ("passing_yards", "passing_td", "rushing_yards", "rushing_td", "receptions",
                                                         "receiving_yards", "receiving_td", "sacks_half", "interceptions", "tackles"))
        self.assertEqual(categories - set(tool.FOOTER_RECORD_CATEGORIES), {"points", "field_goals"})
        for category in categories:
            self.assertEqual({r["scope"] for r in DATA["nfl_records"] if r["category"] == category}, {"career", "season", "game"})
        self.assertEqual(set(DATA["nfl_career_leaders"]), set(tool.LEADER_SPECS))
        self.assertTrue(set(tool.FOOTER_LEADER_CATEGORIES) <= set(DATA["nfl_career_leaders"]))

    def test_headline_records(self):
        expected = {
            "passing_yards.season": (5477, "Peyton Manning", 2013), "passing_td.season": (55, "Peyton Manning", 2013),
            "passing_yards.career": (89214, "Tom Brady", None), "passing_td.career": (649, "Tom Brady", None),
            "passing_yards.game": (554, "Norm Van Brocklin", 1951), "rushing_yards.season": (2105, "Eric Dickerson", 1984),
            "rushing_yards.game": (296, "Adrian Peterson", 2007), "rushing_yards.career": (18355, "Emmitt Smith", None),
            "rushing_td.season": (28, "LaDainian Tomlinson", 2006), "receptions.season": (149, "Michael Thomas", 2019),
            "receptions.game": (21, "Brandon Marshall", 2009), "receiving_yards.season": (1964, "Calvin Johnson", 2012),
            "receiving_yards.game": (336, "Flipper Anderson", 1989), "receiving_td.season": (23, "Randy Moss", 2007),
            "receiving_yards.career": (22895, "Jerry Rice", None), "sacks_half.season": (46, "Myles Garrett", 2025),
            "sacks_half.career": (400, "Bruce Smith", None), "sacks_half.game": (14, "Derrick Thomas", 1990),
            "completions.career": (7753, "Tom Brady", None), "completions.season": (490, "Tom Brady", 2022),
            "forced_fumbles.career": (54, "Robert Mathis", None), "interceptions.career": (81, "Paul Krause", None),
            "points.season": (186, "LaDainian Tomlinson", 2006), "points.game": (40, "Ernie Nevers", 1929),
            "field_goals.game": (8, "Rob Bironas", 2007), "tackles.career": (2059, "Ray Lewis", None),
        }
        for identifier, (value, holder, season) in expected.items():
            rec = record(identifier)
            self.assertEqual(rec["value"], value, identifier)
            self.assertEqual(rec["holders"][0]["name"], holder, identifier)
            if season is not None:
                self.assertEqual(rec["holders"][0]["season"], season, identifier)
        self.assertEqual(record("passing_yards.season")["holders"][0]["club"], "DEN")
        self.assertEqual(record("rushing_yards.season")["holders"][0]["club"], "LAR")

    def test_ties_list_every_holder(self):
        self.assertEqual([h["name"] for h in record("passing_td.game")["holders"]],
                         ["Sid Luckman", "Adrian Burk", "George Blanda", "Y. A. Tittle", "Joe Kapp", "Peyton Manning",
                          "Nick Foles", "Drew Brees"])
        self.assertEqual([h["name"] for h in record("field_goals.season")["holders"]], ["David Akers", "Kaʻimi Fairbairn"])
        self.assertEqual(record("interceptions.game")["tied_players"], 19)
        self.assertEqual([h["date"] for h in record("rushing_td.game")["holders"]], ["1929-11-28", "2020-12-25"])

    def test_every_record_has_a_check_and_none_disagrees(self):
        checks = {c["id"]: c for c in DATA["checks"]["records"]}
        self.assertEqual(set(checks), {r["id"] for r in DATA["nfl_records"]})
        allowed = set(DATA["rules"]["check_status"])
        for identifier, check in checks.items():
            self.assertIn(check["status"], allowed, identifier)
            self.assertNotEqual(check["status"], "mismatch")
        self.assertEqual(checks["passing_yards.season"]["status"], "official_differs")      # nflverse sums Brees 2011 to 5,535
        self.assertEqual(checks["passing_td.career"]["status"], "exact")
        self.assertEqual(checks["rushing_td.season"]["status"], "exact")
        self.assertEqual(checks["rushing_yards.game"]["status"], "exact")
        self.assertEqual(checks["tackles.career"]["status"], "single_source")
        self.assertEqual(checks["forced_fumbles.season"]["status"], "single_source")

    def test_career_top_five(self):
        for category, rows in DATA["nfl_career_leaders"].items():
            self.assertEqual([r["rank"] for r in rows], [1, 2, 3, 4, 5], category)
            values = [r["value"] for r in rows]
            self.assertEqual(values, sorted(values, reverse=True), category)
            self.assertEqual(rows[0]["value"], record(f"{category}.career")["value"], category)
        rushing = DATA["nfl_career_leaders"]["rushing_yards"]
        self.assertEqual((rushing[1]["name"], rushing[1]["value"], rushing[1]["clubs"]), ("Walter Payton", 16726, ["CHI"]))
        passing = DATA["nfl_career_leaders"]["passing_yards"]
        self.assertEqual([(r["name"], r["value"]) for r in passing[:2]], [("Tom Brady", 89214), ("Drew Brees", 80358)])
        self.assertEqual(passing[0]["clubs"], ["NE", "TB"])
        self.assertEqual(DATA["nfl_career_leaders"]["receptions"][0]["name"], "Jerry Rice")
        self.assertEqual((DATA["nfl_career_leaders"]["sacks_half"][0]["name"], DATA["nfl_career_leaders"]["sacks_half"][0]["value"]),
                         ("Bruce Smith", 400))                                     # 200 sacks, kept in half sacks
        self.assertEqual(DATA["nfl_career_leaders"]["points"][0], {"rank": 1, "name": "Adam Vinatieri", "value": 2673,
                                                                    "position": "K", "clubs": []})

    def test_leaders_who_played_since_1999_carry_their_nflverse_identity(self):
        passing = DATA["nfl_career_leaders"]["passing_yards"]
        self.assertEqual((passing[0]["name"], passing[0]["gsis_id"], passing[0]["birth_date"]), ("Tom Brady", "00-0019596", "1977-08-03"))
        self.assertNotIn("active", passing[0])
        self.assertIn("gsis_id", passing[1])
        for category, rows in DATA["nfl_career_leaders"].items():
            for row in rows:
                if "gsis_id" in row:
                    self.assertRegex(row["gsis_id"], r"^00-\d{7}$")
                    self.assertRegex(row["birth_date"], r"^\d{4}-\d{2}-\d{2}$")
        payton = DATA["nfl_career_leaders"]["rushing_yards"][1]
        self.assertNotIn("gsis_id", payton)                                  # retired before 1999

    def test_leader_checks_never_disagree(self):
        checks = DATA["checks"]["career_leaders"]
        self.assertEqual(len(checks), 60)
        self.assertEqual([c for c in checks if c["status"] == "mismatch"], [])
        self.assertEqual(sum(c["status"] in ("exact", "within_stat_correction") for c in checks) >= 10, True)


class HallOfFameTests(unittest.TestCase):
    def test_classes(self):
        members = DATA["hall_of_fame"]["members"]
        self.assertEqual(DATA["hall_of_fame"]["through_class"], 2026)
        by_class = collections.Counter(m["class"] for m in members)
        self.assertEqual(sorted(by_class), list(range(1963, 2027)))
        self.assertEqual(by_class[1963], 17)
        self.assertEqual(by_class[2020], 20)
        self.assertEqual(len(members), 387)
        for year, count in by_class.items():
            self.assertTrue(3 <= count <= 20, (year, count))
        self.assertEqual(sorted(m["name"] for m in members if m["class"] == 2026),
                         ["Adam Vinatieri", "Drew Brees", "Larry Fitzgerald", "Luke Kuechly", "Roger Craig"])
        flags = collections.Counter(f for m in members for f in m.get("flags", []))
        self.assertEqual(flags["charter_member"], 17)
        self.assertEqual(flags["centennial_slate"], 15)
        self.assertEqual(sorted(members, key=lambda m: (m["class"], m["name"])), members)

    def test_member_rows(self):
        clubs = {c["id"] for c in DATA["clubs"]}
        for m in DATA["hall_of_fame"]["members"]:
            self.assertIn(m["category"], ("player", "coach", "contributor"))
            self.assertTrue(m["stints"], m["name"])
            if m["club"] is not None:
                self.assertIn(m["club"], clubs)
            if m["category"] == "player":
                self.assertTrue(m["position"] in tool.POSITIONS or m["position"] is None, m)
            else:
                self.assertIsNone(m["position"])
            for stint in m["stints"]:
                self.assertTrue(stint["club"] is None or stint["club"] in clubs)
        self.assertEqual(hof("Troy Aikman")["club"], "DAL")
        self.assertEqual((hof("Troy Aikman")["position"], hof("Troy Aikman")["class"]), ("QB", 2006))
        self.assertEqual(hof("Peyton Manning")["club"], "IND")
        self.assertEqual(hof("Peyton Manning")["class"], 2021)
        self.assertEqual(hof("Orlando Pace")["class"], 2016)
        self.assertEqual(hof("Bruce Matthews")["position"], "G")
        self.assertIn("first_year_of_eligibility", hof("Drew Brees")["flags"])
        self.assertEqual([s["club"] for s in hof("Drew Brees")["stints"]], ["LAC", "NO"])
        self.assertEqual(sum(1 for m in DATA["hall_of_fame"]["members"] if m["name"] == "Jimmy Johnson"), 2)

    def test_modern_stars_of_the_awards_are_inducted_or_pending(self):
        names = {m["name"] for m in DATA["hall_of_fame"]["members"]}
        pending = {p["name"] for p in DATA["pending_candidates"]["players"]}
        for name in ("Peyton Manning", "Calvin Johnson", "Joe Thomas", "Devin Hester", "Julius Peppers"):
            self.assertIn(name, names)
            self.assertNotIn(name, pending)


class CandidateTests(unittest.TestCase):
    def test_rule_and_window(self):
        block = DATA["pending_candidates"]
        self.assertEqual(block["window"], [2011, 2025])
        self.assertEqual(block["bar"], tool.CANDIDATE_BAR)
        self.assertEqual(block["honors_ambiguous"], 0)
        self.assertLessEqual(block["honors_unmatched"], 6)
        inducted = {m["name"] for m in DATA["hall_of_fame"]["members"] if m["category"] == "player"}
        for p in block["players"]:
            self.assertTrue(2011 <= p["last_season"] <= 2025, p["name"])
            self.assertEqual(p["first_eligible_class"], p["last_season"] + 6)
            self.assertTrue(p["why"], p["name"])
            self.assertLessEqual(p["first_season"], p["last_season"])
            self.assertRegex(p["gsis_id"], r"^00-\d{7}$")
            self.assertRegex(p["birth_date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(p["position"] in tool.POSITIONS)
            self.assertTrue(set(p["honors"]) <= set(tool.HONOR_IDS))
            self.assertTrue(p["club"] is None or p["club"] in {c["id"] for c in DATA["clubs"]})
            self.assertNotIn(p["name"], inducted - {"Jimmy Johnson"}, p["name"])
        order = [(-p["honors"].get("all_pro", 0), -p["honors"].get("pro_bowl", 0), p["name"]) for p in block["players"]]
        self.assertEqual(order, sorted(order))
        self.assertTrue(40 <= len(block["players"]) <= 120, len(block["players"]))

    def test_known_candidates(self):
        by_name = {p["name"]: p for p in DATA["pending_candidates"]["players"]}
        brady = by_name["Tom Brady"]
        self.assertEqual((brady["last_season"], brady["first_eligible_class"], brady["position"]), (2022, 2028, "QB"))
        self.assertEqual(brady["honors"]["mvp"], 3)
        self.assertEqual(brady["honors"]["super_bowl_mvp"], 4)
        self.assertEqual(brady["honors"]["pro_bowl"], 14)                  # seasons 2002..2025: his 2001 selection is outside
        self.assertEqual(brady["honors"]["super_bowl"], 6)                 # 2003, 2004, 2014, 2016, 2018, 2020 (2001 is outside)
        self.assertEqual(by_name["Eli Manning"]["honors"]["super_bowl"], 2)
        # the rule is the Super Bowl-week 53-man roster (active or inactive): Gronkowski's 2016 ring came on injured reserve
        self.assertEqual(by_name["Rob Gronkowski"]["honors"]["super_bowl"], 3)
        self.assertEqual(by_name["Ben Roethlisberger"]["honors"]["super_bowl"], 2)
        self.assertEqual(brady["clubs"], ["NE", "TB"])
        self.assertEqual(brady["production_1999_2025"]["passing_td"], 649)
        watt = by_name["J.J. Watt"]
        self.assertEqual((watt["last_season"], watt["first_eligible_class"], watt["honors"]["dpoy"]), (2022, 2028, 3))
        for name in ("Ben Roethlisberger", "Rob Gronkowski", "Adrian Peterson", "Frank Gore"):
            self.assertIn(name, by_name)
        self.assertNotIn("Aaron Rodgers", by_name)                     # still playing in 2026 (last season 2026)

    def test_footer_keys_and_quarterback_wins(self):
        players = {p["name"]: p for p in DATA["pending_candidates"]["players"]}
        groups = DATA["pending_candidates"]["key_groups"]
        self.assertEqual(groups["QB"], ["passing_td", "passing_yards_k", "wins"])
        for p in players.values():
            expected = tool.KEY_GROUP.get(p["position"])
            self.assertEqual(p["key_group"], expected, p["name"])
            self.assertEqual(p["keys"] is None, expected is None, p["name"])
            if expected:
                self.assertEqual(list(p["keys"]), groups[expected], p["name"])
        brady = players["Tom Brady"]
        self.assertEqual((brady["keys"]["passing_td"], brady["keys"]["passing_yards_k"]), (649, 89))
        self.assertTrue(245 <= brady["keys"]["wins"] <= 255, brady["keys"])                  # 251 regular-season wins as the starter
        self.assertEqual(players["Jason Kelce"]["keys"], {"seasons_started": None, "pro_bowls": 7, "all_pro": 6})
        self.assertEqual(players["J.J. Watt"]["keys"]["sacks_half"], 229)                       # 114.5 sacks
        self.assertGreater(players["Ben Roethlisberger"]["keys"]["wins"], 150)

    def test_sources_of_the_candidate_list_are_pinned(self):
        manifest = DATA["sources"]["wiki_honor_pages"]
        self.assertEqual(manifest["pages"], 48)
        keys = sorted(k for k in PINS["wikipedia"] if k.startswith(("wiki_allpro_", "wiki_probowl_")))
        self.assertEqual(len(keys), 48)
        self.assertEqual(manifest, tool.pages_manifest(PINS, ("wiki_allpro_", "wiki_probowl_"),
                                                       "wiki_allpro_<season>, wiki_probowl_<season>",
                                                       "<season> All-Pro Team and the Pro Bowl played after the season, 2002..2025")
                         | {"publisher": "Wikipedia"})


class SourceTests(unittest.TestCase):
    def test_every_source_is_pinned(self):
        sources = DATA["sources"]
        for key, pin in sources.items():
            if key in ("nflverse_stats", "nflverse_rosters"):
                self.assertEqual(len(pin["files"]), 28 if key == "nflverse_stats" else 24)
                for name, f in pin["files"].items():
                    self.assertRegex(f["sha256"], HEX64, name)
                    self.assertTrue(f["url"].startswith("https://github.com/nflverse/nflverse-data/releases/download/"), name)
                continue
            if key == "wiki_honor_pages":
                self.assertRegex(pin["manifest_sha256"], HEX64)
                continue
            if key == "nflverse_games":
                self.assertRegex(pin["sha256"], HEX64)
                self.assertRegex(pin["used_rows_sha256"], HEX64)
                self.assertRegex(pin["commit"], r"^[0-9a-f]{40}$")
                self.assertIn(pin["commit"], pin["url"])
                self.assertTrue(pin["url"].startswith("https://raw.githubusercontent.com/nflverse/nfldata/"))
                continue
            self.assertRegex(pin["sha256"], HEX64, key)
            self.assertIsInstance(pin["revision"], int, key)
            self.assertTrue(pin["url"].startswith("https://en.wikipedia.org/w/index.php?title="), key)
            self.assertIn(f"oldid={pin['revision']}", pin["url"], key)
            self.assertEqual(pin["publisher"], "Wikipedia")

    def test_the_games_pin_is_the_tools_constant(self):
        pin = DATA["sources"]["nflverse_games"]
        for key, value in tool.NFLVERSE_GAMES.items():
            self.assertEqual(pin[key], value, key)
        self.assertEqual(pin["sha256"], "a5181ec4974309828d1d58e6f881eb1d106ee85c15c038a51b6bdca7b7ee6cf5")

    def test_the_pins_file_and_the_data_file_agree(self):
        wiki = PINS["wikipedia"]
        for key, pin in DATA["sources"].items():
            if key in ("nflverse_games", "nflverse_stats", "nflverse_rosters", "wiki_honor_pages"):
                continue
            self.assertIn(key, wiki, key)
            self.assertEqual((pin["title"], pin["revision"], pin["sha256"]),
                             (wiki[key]["title"], wiki[key]["revision"], wiki[key]["sha256"]), key)
        self.assertEqual(DATA["sources"]["nflverse_stats"]["files"], PINS["nflverse"]["files"])
        self.assertEqual(DATA["sources"]["nflverse_rosters"]["files"], PINS["nflverse"]["rosters"])
        for pin in wiki.values():
            self.assertRegex(pin["sha256"], HEX64)
            self.assertIsInstance(pin["revision"], int)

    def test_pages_shared_with_the_honors_and_champions_histories_are_the_same_revisions(self):
        honors = json.loads((ROOT / "data" / "nfl2k5_honors_2026.json").read_text(encoding="utf-8"))["sources"]
        for key in ("wiki_mvp", "wiki_opoy", "wiki_dpoy", "wiki_roy", "wiki_sbmvp"):
            self.assertEqual((DATA["sources"][key]["revision"], DATA["sources"][key]["sha256"]),
                             (honors[key]["revision"], honors[key]["sha256"]), key)
        for season in range(2005, 2026):
            for kind in ("allpro", "probowl"):
                key = f"wiki_{kind}_{season}"
                self.assertEqual((PINS["wikipedia"][key]["revision"], PINS["wikipedia"][key]["sha256"]),
                                 (honors[key]["revision"], honors[key]["sha256"]), key)
        for season in range(2005, 2026):
            self.assertEqual(PINS["nflverse"]["rosters"][f"roster_{season}.csv"]["sha256"],
                             honors[f"nflverse_roster_{season}"]["sha256"], season)
        self.assertEqual(CHAMPIONS["sources"]["wiki_mvp"]["revision"], DATA["sources"]["wiki_mvp"]["revision"])
        self.assertEqual(CHAMPIONS["sources"]["wiki_sbmvp"]["revision"], DATA["sources"]["wiki_sbmvp"]["revision"])

    def test_the_standings_manifest_recomputes_from_the_pins(self):
        manifest = DATA["checks"]["standings"]
        self.assertEqual(manifest["pages"], 192)
        recomputed = tool.standings_manifest(PINS)
        for key in ("pages", "manifest_sha256", "seasons"):
            self.assertEqual(manifest[key], recomputed[key], key)
        self.assertEqual(manifest["compared_club_seasons"], 768)
        for season in range(2002, 2026):
            for division in tool.DIVISIONS:
                self.assertIn(tool.template_key(season, division), PINS["wikipedia"])

    def test_wikipedia_standings_agree_with_the_computed_seasons_except_one_explained_error(self):
        differences = DATA["checks"]["standings"]["differences"]
        self.assertEqual(len(differences), 1)
        only = differences[0]
        self.assertEqual((only["season"], only["club"], only["field"]), (2010, "Houston Texans", "conf"))
        self.assertEqual(only["ours"], list(team(2010, "HOU")["conf"]))
        self.assertEqual(only["ours"], [5, 7, 0])
        self.assertEqual(only["wikipedia"], [4, 8, 0])
        self.assertEqual([{k: v for k, v in d.items() if k != "why"} for d in differences],
                         [{k: v for k, v in e.items() if k != "why"} for e in tool.KNOWN_WIKIPEDIA_ERRORS])
        # the explanation is arithmetic: the Texans' wins, their division record and their one NFC win
        texans = team(2010, "HOU")
        self.assertEqual((texans["w"], texans["div"][0]), (6, 3))
        self.assertEqual(texans["conf"][0], 5)


class EngineTests(unittest.TestCase):
    """The tie-break engine on small seasons made by hand, with the tool's own Game rows."""

    @staticmethod
    def game(week, away, home, away_score, home_score, season=2030):
        return tool.Game({"season": str(season), "game_type": "REG", "week": str(week), "game_id": f"{season}_{week:02d}_{away}_{home}",
                          "away_team": away, "home_team": home, "away_score": str(away_score), "home_score": str(home_score),
                          "away_coach": "A", "home_coach": "H", "gameday": f"{season}-09-{week:02d}", "overtime": "0"})

    def test_two_clubs_level_head_to_head_decides(self):
        # every pair of the division meets twice (once at each ground); the number is the first club's wins in the pair
        wins = {("NYG", "DAL"): 2, ("NYG", "PHI"): 1, ("NYG", "WAS"): 1, ("DAL", "PHI"): 2, ("DAL", "WAS"): 2, ("PHI", "WAS"): 1}
        games, week = [], 0
        for (a, b), wins_a in wins.items():
            for k in range(2):
                week += 1
                home, away = (a, b) if k == 0 else (b, a)
                winner = a if k < wins_a else b
                games.append(self.game(week, away, home, 10 if winner == home else 17, 17 if winner == home else 10))
        table = tool.SeasonTable(2030, games)
        self.assertEqual(table.record["NYG"], (4, 2, 0))
        self.assertEqual(table.record["DAL"], (4, 2, 0))
        stands = table.standings()
        self.assertEqual((stands["NYG"]["place"], stands["DAL"]["place"]), (1, 2))
        self.assertEqual((stands["NYG"]["tiebreak"], stands["DAL"]["tiebreak"]), ("head_to_head", "head_to_head"))
        self.assertEqual({stands["PHI"]["place"], stands["WAS"]["place"]}, {3, 4})

    def test_the_real_three_way_tie_of_the_2025_nfc_south(self):
        # CAR, TB and ATL all 8-9 and 3-3 in the division; CAR beat ATL twice and split with TB, so it leads the games
        # among the three (3-1); TB and ATL then split, and the procedure restarts for the two
        scores = [(1, "TB", "ATL", 23, 20), (3, "ATL", "CAR", 0, 30), (8, "TB", "NO", 23, 3), (10, "NO", "CAR", 17, 7),
                  (11, "CAR", "ATL", 30, 27), (12, "ATL", "NO", 24, 10), (14, "NO", "TB", 24, 20), (15, "ATL", "TB", 29, 28),
                  (15, "CAR", "NO", 17, 20), (16, "TB", "CAR", 20, 23), (18, "CAR", "TB", 14, 16), (18, "NO", "ATL", 17, 19)]
        table = tool.SeasonTable(2025, [self.game(w, a, h, asc, hsc, 2025) for w, a, h, asc, hsc in scores])
        for club in ("CAR", "TB", "ATL"):
            self.assertEqual(table.tally(table.division_games(club)), (3, 3, 0))
        top, step = table.best_of(["CAR", "TB", "ATL"])
        self.assertEqual((top, step), (["CAR"], "head_to_head"))
        order = table.order(["CAR", "TB", "ATL"])
        self.assertEqual(order[0], ("CAR", "head_to_head"))
        self.assertEqual({c for c, _s in order}, {"CAR", "TB", "ATL"})

    def test_win_percentage_counts_a_tie_as_half_and_orders_first(self):
        games = [self.game(1, "DAL", "NYG", 10, 10), self.game(2, "PHI", "WAS", 20, 3), self.game(3, "WAS", "PHI", 3, 20)]
        table = tool.SeasonTable(2030, games)
        stands = table.standings()
        self.assertEqual(stands["PHI"]["place"], 1)
        self.assertEqual(tool.pct(1, 1, 2), 0.5)
        self.assertIsNone(tool.pct(0, 0, 0))

    def test_standings_template_reader(self):
        text = ("{| class=\"wikitable\"\n! colspan=\"10\" | [[AFC East]]\n|-\n! Team !! W !! L !! T !! PCT !! DIV !! CONF !! PF !! PA !! STK\n"
                "|- style=\"background-color:#ccffcc\"\n| {{nowrap|<sup>(1)</sup> [[2007 New England Patriots season|New England Patriots]]}}\n"
                "| 16\n| 0\n| 0\n| 1.000\n| 6–0\n| 12–0\n| 589\n| 274\n| W16\n|-\n| [[2007 Buffalo Bills season|Buffalo Bills]]"
                "{{efn|a note}}\n| 7\n| 9\n| 0\n| .438\n| 4–2\n| 6–6\n| 252\n| 354\n| L3\n|}<noinclude>\nx\n</noinclude>")
        rows = tool.parse_standings_template(text)
        self.assertEqual(rows[0], {"name": "New England Patriots", "seed": 1, "w": 16, "l": 0, "t": 0, "div": (6, 0, 0),
                                   "conf": (12, 0, 0), "pf": 589, "pa": 274})
        self.assertEqual((rows[1]["name"], rows[1]["seed"], rows[1]["conf"]), ("Buffalo Bills", None, (6, 6, 0)))


class ReaderTests(unittest.TestCase):
    def test_strip_markup(self):
        self.assertEqual(tool.strip_markup("{{sortname|Peyton|Manning|dab=x}}{{dagger}} (3)"), "Peyton Manning† (3)")
        self.assertEqual(tool.strip_markup("[[2016 Oakland Raiders season|Oakland]]<ref>cite</ref>"), "Oakland")
        self.assertEqual(tool.strip_markup("{{nowrap|[[2014 New Orleans Saints season|New Orleans Saints]]}}"), "New Orleans Saints")
        self.assertEqual(tool.strip_markup("{{nowrap|(1) New England Patriots"), "(1) New England Patriots")      # never closed
        self.assertEqual(tool.strip_markup("{{unbulleted list| Guard | Center |Tackle }}"), "Guard/Center/Tackle")
        self.assertEqual(tool.strip_markup("{{NFL year|2000|2019}}"), "2000–2019")
        self.assertEqual(tool.strip_markup("Washington&nbsp;Redskins{{efn|name=x|a note {{sfn|b}}}}"), "Washington Redskins")
        self.assertEqual(tool.strip_markup("A<br />B"), "A / B")

    def test_wikitable_rowspans_and_odd_attributes(self):
        text = ("{|class=\"wikitable\"\n! Name !! Class !! Team\n|-\n| rowspan=2 style=|Orlando Pace || rowspan=2 | 2016 || Rams\n|-\n"
                "| Bears\n|-\n| Troy Aikman || 2006 || Cowboys\n|}")
        table = tool.parse_tables(text)[0]
        self.assertEqual([[c.text for c in row] for row in table],
                         [["Name", "Class", "Team"], ["Orlando Pace", "2016", "Rams"], ["Orlando Pace", "2016", "Bears"],
                          ["Troy Aikman", "2006", "Cowboys"]])
        self.assertIs(table[1][0], table[2][0])
        self.assertEqual(table[1][1].attrs["rowspan"], "2")

    def test_record_holders(self):
        value, holders, many = tool.parse_record_holders(
            " 44, [[David Akers]], [[2011 San Francisco 49ers season|2011]], [[Kaʻimi Fairbairn]], [[2025 Houston Texans season|2025]]")
        self.assertEqual(value, 44)
        self.assertEqual([(h["name"], h["season"], h["team"]) for h in holders],
                         [("David Akers", 2011, "San Francisco 49ers"), ("Kaʻimi Fairbairn", 2025, "Houston Texans")])
        value, holders, many = tool.parse_record_holders(
            " 6, [[Ernie Nevers]], November 28, 1929; [[Alvin Kamara]], Dec 25, 2020")
        self.assertEqual([(h["name"], h["date"]) for h in holders], [("Ernie Nevers", "1929-11-28"), ("Alvin Kamara", "2020-12-25")])
        value, holders, many = tool.parse_record_holders(" 4, by 19 players, most recently [[DeAngelo Hall]], October 24, 2010")
        self.assertEqual((value, many, holders[0]["name"], holders[0]["season"]), (4, 19, "DeAngelo Hall", 2010))
        value, holders, many = tool.parse_record_holders(" 7.0, [[Derrick Thomas]] on [[1990 Kansas City Chiefs season|November 11, 1990]]")
        self.assertEqual((value, holders[0]["date"], holders[0]["team"]), (7.0, "1990-11-11", "Kansas City Chiefs"))
        value, holders, many = tool.parse_record_holders(" 18,355, [[Emmitt Smith]], 1990–2004")
        self.assertEqual((value, holders[0]["seasons"]), (18355, "1990-2004"))

    def test_names_positions_and_clubs(self):
        self.assertEqual(tool.clean_name("Joe Burrow (2)"), "Joe Burrow")
        self.assertEqual(tool.clean_name("Mike Vrabel~ (2)"), "Mike Vrabel")
        self.assertEqual(tool.clean_name("Kenneth Walker III"), "Kenneth Walker III")
        self.assertEqual(tool.position_code("Quarterback (19)", "Tom Brady"), "QB")
        self.assertEqual(tool.position_code("Linebacker", "Ray Lewis"), "ILB")
        self.assertEqual(tool.position_code("Linebacker", "Von Miller"), "OLB")
        self.assertEqual(tool.position_code("Safety", "Troy Polamalu"), "SS")
        self.assertIsNone(tool.position_code("Coach", "x"))
        self.assertEqual(tool.club_of("[[2017 Los Angeles Rams season|LA Rams]]"), "LAR")
        self.assertEqual(tool.club_of("[[2016 Oakland Raiders season|Oakland]]"), "LV")
        self.assertEqual(tool.club_of("[[2005 New England Patriots season|New England]]"), "NE")
        self.assertEqual(tool.club_of("[[Indianapolis Colts]]<br />[[Tennessee Titans]]"), "IND")
        self.assertEqual(tool.clubs_in("Philadelphia Eagles / Green Bay Packers")[0], ["PHI", "GB"])
        self.assertEqual(tool.clubs_in("[[Los Angeles Rams|Los Angeles]] / [[St. Louis Rams|St. Louis]]")[0], ["LAR"])
        self.assertTrue(tool.same_person('Dick "Night Train" Lane', "Night Train Lane"))
        self.assertTrue(tool.same_person("T. J. Watt", "T.J. Watt"))
        self.assertFalse(tool.same_person("Adrian Peterson", "Adrian Burk"))
        self.assertEqual(tool.norm_name("Odell Beckham Jr."), "odell beckham")

    def test_seed_years_and_quarterback_helpers(self):
        row = {"club": "NE", "playoffs": "champion", "bye": True, "coach": "x"}
        self.assertEqual(list(tool.with_seed(row, 1)), ["club", "playoffs", "bye", "seed", "coach"])
        self.assertEqual(list(tool.with_seed({"club": "NE", "playoffs": "lost_wild_card", "coach": "x"}, 6)),
                         ["club", "playoffs", "seed", "coach"])
        self.assertIs(tool.with_seed(row, None), row)
        self.assertEqual(tool.normalize_years("1930\u20131937, 1943"), "1930-1937, 1943")
        self.assertEqual(tool.normalize_years("1915\u201317, 1919"), "1915-1917, 1919")
        self.assertEqual(tool.normalize_years("1929\u20131933,/1935\u20131936"), "1929-1933, 1935-1936")
        self.assertEqual(tool.normalize_years("2004\u2013present"), "2004-present")
        rows = [{"game_type": "REG", "season": "2005", "home_score": "20", "away_score": "10", "home_qb_id": "A", "away_qb_id": "B"},
                {"game_type": "REG", "season": "2006", "home_score": "7", "away_score": "9", "home_qb_id": "A", "away_qb_id": "B"},
                {"game_type": "REG", "season": "2006", "home_score": "7", "away_score": "7", "home_qb_id": "A", "away_qb_id": "B"},
                {"game_type": "WC", "season": "2006", "home_score": "7", "away_score": "9", "home_qb_id": "A", "away_qb_id": "B"},
                {"game_type": "REG", "season": "1998", "home_score": "7", "away_score": "9", "home_qb_id": "A", "away_qb_id": "B"}]
        self.assertEqual(tool.quarterback_wins(rows), {"A": 1, "B": 1})
        import collections as _c
        c = _c.Counter(passing_td=649, passing_yards=89214, rushing_yards=100, tackles=539, sacks_half=229)
        self.assertEqual(tool.career_keys("QB", {}, c, 251), {"passing_td": 649, "passing_yards_k": 89, "wins": 251})
        self.assertEqual(tool.career_keys("defense", {}, c, 0), {"tackles": 539, "sacks_half": 229, "interceptions": 0})
        self.assertEqual(tool.career_keys("line", {"pro_bowl": 7, "all_pro": 6}, c, 0),
                         {"seasons_started": None, "pro_bowls": 7, "all_pro": 6})
        self.assertIsNone(tool.career_keys(None, {}, c, 0))

    def test_writer_inlines_short_rows_and_round_trips(self):
        value = {"a": [1, 2, 3], "rows": [{"x": i, "y": "z" * 40} for i in range(12)], "long": {"k": "v" * 400}, "empty": []}
        text = tool.dumps(value)
        self.assertEqual(json.loads(text), value)
        self.assertIn('{"x": 0, "y": "' + "z" * 40 + '"}', text)
        self.assertEqual(text.count("\n") > 10, True)

    def test_known_errors_are_well_formed(self):
        kept, rest = tool.split_known([{"season": 2010, "club": "Houston Texans", "field": "conf", "ours": [5, 7, 0],
                                        "wikipedia": [4, 8, 0]},
                                       {"season": 2011, "club": "Houston Texans", "field": "conf", "ours": [5, 7, 0],
                                        "wikipedia": [4, 8, 0]}])
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(rest), 1)
        self.assertIn("why", kept[0])


class PackagingTests(unittest.TestCase):
    def test_the_data_file_ships(self):
        entries = (ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("data/nfl2k5_history_2026.json", entries)

    def test_the_tool_writes_text_with_an_explicit_newline(self):
        source = TOOL_PATH.read_text(encoding="utf-8")
        self.assertIn('write_text(text, encoding="utf-8", newline="\\n")', source)
        self.assertNotIn("open(", source.replace("urlopen(", ""))


@unittest.skipUnless(os.environ.get("NFL2K5_HISTORY_SEED_CACHE"), "set NFL2K5_HISTORY_SEED_CACHE to a filled cache to rebuild")
class RebuildTests(unittest.TestCase):
    def test_a_fresh_build_equals_the_committed_file(self):
        cache = Path(os.environ["NFL2K5_HISTORY_SEED_CACHE"])
        games = tool.ensure_games(cache, None)
        document = tool.build(games, cache / "nflverse", cache / "wikipedia", tool.load_pins())
        self.assertEqual(document, DATA)


if __name__ == "__main__":
    unittest.main()
