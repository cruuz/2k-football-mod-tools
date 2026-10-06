"""The 25 more 25th Anniversary moments and their team-seasons (job m2): the data contract with m1's engine.

Everything but the last class reads only committed files. The last class regenerates the data from the private
inputs (nflverse downloads and the user's retail game) when they are present, and skips otherwise.
"""
import collections
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "tools"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from mod_editor.core import nfl2k5_ratings_model as rm  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
import nfl2k5_espn25_more_moments_build as build  # noqa: E402

DATA = ROOT / "data"
MOMENTS = DATA / "nfl2k5_espn25_more_moments.json"
TEAMS = DATA / "nfl2k5_espn25_more_teams"
NOAH_FIVE = ("helmet_catch", "manningham", "fourth_and_18", "toe_tap", "comeback_28_3")
# The retail 25 (title, date), read from the retail situation.iff: no new moment may repeat one.
RETAIL_25 = (
    ("THE ICE BOWL", "December 31, 1967"), ("THE HEIDI BOWL", "November 17, 1968"),
    ("MERRY CHRISTMAS MIAMI", "December 25, 1971"), ("THE IMMACULATE RECEPTION", "December 23, 1972"),
    ("THE SEA OF HANDS", "December 21, 1974"), ("THE FINAL COMEBACK", "December 16, 1979"),
    ("THE AINTS' BIGGEST CHOKE", "December 7, 1980"), ("LONGEST PLAYOFF GAME EVER", "January 2, 1982"),
    ("THE CATCH", "January 10, 1982"), ("GREATEST REDSKIN COMEBACK", "October 2, 1983"),
    ("THE DRIVE", "January 11, 1987"), ("THE 2-SECOND MISCALCULATION", "September 20, 1987"),
    ("SAME OLD BUCS", "November 8, 1987"), ("49ERS DO IT AGAIN", "January 22, 1989"),
    ("WIDE RIGHT", "January 27, 1991"), ("HOUSTON'S HEARTS RIPPED OUT", "January 4, 1992"),
    ("THE TWO TD COMEBACK ON KC", "October 4, 1992"), ("THE BIGGEST COMEBACK EVER", "January 3, 1993"),
    ("THE HEARTBREAKER", "October 17, 1994"), ("THE COLTS' COLLAPSE", "September 21, 1997"),
    ("THE SUPER BOWL DRIVE", "January 25, 1998"), ("A YARD TOO SHORT", "January 30, 2000"),
    ("VINATIERI STRIKES AGAIN", "February 3, 2002"), ("THE BOTCHED SNAP", "January 5, 2003"),
    ("FOURTH AND TWENTY-SIX", "January 11, 2004"),
)
CONTRACT_MINIMUMS = {"QB": 2, "K": 1, "P": 1, "WR": 4, "HB": 2, "FB": 1, "TE": 2, "T": 2, "G": 2, "C": 1,
                     "DE": 2, "DT": 2, "CB": 3, "FS": 1, "SS": 1}
WEATHER = ("clear", "light rain", "heavy rain", "flurries", "heavy snow")
TIMES = ("day", "afternoon", "night")
DASHES = ("\u2014", "\u2013", "\u2012", "\u2015")


def load_moments():
    return json.loads(MOMENTS.read_text(encoding="utf-8"))


def load_teams():
    return json.loads((TEAMS / "teams.json").read_text(encoding="utf-8"))["teams"]


def load_team_rows(key):
    with (TEAMS / f"{key}.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


class MomentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load_moments()
        cls.moments = cls.doc["moments"]
        cls.teams = load_teams()

    def test_schema_and_count(self):
        self.assertEqual(self.doc["schema"], 1)
        self.assertEqual(len(self.moments), 26)
        self.assertEqual(len({m["id"] for m in self.moments}), len(self.moments))

    def test_noah_five_and_the_miss_lead_the_list(self):
        ids = [m["id"] for m in self.moments]
        for moment in NOAH_FIVE + ("the_miss",):
            self.assertIn(moment, ids)
        # rows 26 to 31 hold the six the engine proves first (no save change up to row 32)
        self.assertEqual(set(ids[:6]), set(NOAH_FIVE) | {"the_miss"})

    def test_no_moment_repeats_the_retail_25(self):
        retail_dates = {date for _, date in RETAIL_25}
        retail_titles = {title for title, _ in RETAIL_25}
        for m in self.moments:
            self.assertNotIn(m["date"], retail_dates, m["id"])
            self.assertNotIn(m["title"], retail_titles, m["id"])

    def test_text_rules(self):
        for m in self.moments:
            for field in ("title", "date", "history", "goal", "stadium", "stadium_note"):
                value = m[field]
                self.assertTrue(value.isascii(), (m["id"], field))
                self.assertFalse(any(d in value for d in DASHES), (m["id"], field))
            self.assertEqual(m["title"], m["title"].upper())
            self.assertLessEqual(len(m["title"]), 27)
            self.assertTrue(320 <= len(m["history"]) <= 445, (m["id"], len(m["history"])))
            self.assertTrue(46 <= len(m["goal"]) <= 86, (m["id"], len(m["goal"])))
            parsed = dt.datetime.strptime(m["date"], "%B %d, %Y")
            self.assertEqual(m["date"], f"{parsed:%B} {parsed.day}, {parsed.year}")
            self.assertTrue(m["sources"])

    def test_situation_fields(self):
        for m in self.moments:
            with self.subTest(m["id"]):
                self.assertIn(m["away"], self.teams)
                self.assertIn(m["home"], self.teams)
                self.assertNotEqual(m["away"], m["home"])
                self.assertIn(m["user_side"], ("away", "home"))
                self.assertIn(m["possession"], ("away", "home"))
                for key in ("score_now", "final_score", "timeouts"):
                    self.assertEqual(set(m[key]), {"away", "home"})
                for side in ("away", "home"):
                    self.assertTrue(0 <= m["score_now"][side] <= 99)
                    self.assertTrue(0 <= m["final_score"][side] <= 99)
                    self.assertTrue(0 <= m["timeouts"][side] <= 3)
                self.assertTrue(1 <= m["quarter"] <= 4, "regulation starts only (overtime is not proved)")
                minutes, seconds = m["clock"].split(":")
                self.assertTrue(0 <= int(minutes) * 60 + int(seconds) <= 900)
                self.assertEqual(m["clock"], f"{int(minutes)}:{int(seconds):02d}")
                self.assertTrue(0 <= m["down"] <= 4)
                if m["down"] == 0:
                    self.assertEqual(m["distance"], 10)
                else:
                    self.assertTrue(1 <= m["distance"] <= 99)
                abbreviations = {self.teams[m["away"]]["abbreviation"], self.teams[m["home"]]["abbreviation"]}
                if m["ball_on"] != "50":
                    team, yard = m["ball_on"].split()
                    self.assertIn(team, abbreviations)
                    self.assertTrue(1 <= int(yard) <= 49)
                self.assertIn(m["weather"], WEATHER)
                self.assertIn(m["time_of_day"], TIMES)
                self.assertIsInstance(m["temperature"], int)
                if "rain" in m["weather"]:
                    self.assertGreaterEqual(m["temperature"], 33)
                if "snow" in m["weather"] or m["weather"] == "flurries":
                    self.assertLessEqual(m["temperature"], 31)
                self.assertTrue(0 <= m["stadium_index"] <= 42)
                for side in ("away", "home"):
                    kit = m["kits"][side]
                    self.assertTrue(isinstance(kit, int) and 0 <= kit <= 14 or isinstance(kit, dict) and "era_year" in kit)

    def test_noah_five_situations(self):
        """The five starting situations, read from nflverse play-by-play (PROVED OFFLINE from the source data).
        Beta 76.3 (Noah 10/2: the Tyree Super Bowl "is off"): a moment named for one play starts AT that play,
        Tyree (2007_21_NYG_NE play 3651) and Holmes (2008_21_PIT_ARI play 3912). Manningham's catch is the drive's
        first play already; New England still had 3 timeouts before it (the row's 2 counts the lost challenge)."""
        expected = {
            "helmet_catch": dict(quarter=4, clock="1:15", down=3, distance=5, ball_on="NYG 44",
                                 score_now={"away": 10, "home": 14}, final_score={"away": 17, "home": 14},
                                 timeouts={"away": 2, "home": 3}),
            "toe_tap": dict(quarter=4, clock="0:42", down=2, distance=6, ball_on="ARZ 6",
                            score_now={"away": 20, "home": 23}, final_score={"away": 27, "home": 23},
                            timeouts={"away": 0, "home": 2}),
            "manningham": dict(quarter=4, clock="3:46", down=1, distance=10, ball_on="NYG 12",
                               score_now={"away": 15, "home": 17}, final_score={"away": 21, "home": 17},
                               timeouts={"away": 1, "home": 3}),
            "comeback_28_3": dict(quarter=3, clock="8:31", down=1, distance=10, ball_on="NE 25",
                                  score_now={"away": 3, "home": 28}, final_score={"away": 34, "home": 28},
                                  timeouts={"away": 3, "home": 2}),
            "fourth_and_18": dict(quarter=4, clock="3:26", down=1, distance=10, ball_on="MIN 24",
                                  score_now={"away": 23, "home": 27}, final_score={"away": 33, "home": 30},
                                  timeouts={"away": 1, "home": 3}),
        }
        by_id = {m["id"]: m for m in self.moments}
        for moment, fields in expected.items():
            for key, value in fields.items():
                self.assertEqual(by_id[moment][key], value, (moment, key))
            self.assertEqual(by_id[moment]["user_side"], by_id[moment]["possession"])


class TeamsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.teams = load_teams()
        cls.manifest = json.loads((TEAMS / "manifest.json").read_text(encoding="utf-8"))
        cls.used = {m[side] for m in load_moments()["moments"] for side in ("away", "home")}

    def test_every_team_is_used_and_every_used_team_exists(self):
        self.assertEqual(set(self.teams), self.used)
        csvs = {p.stem for p in TEAMS.glob("*.csv")}
        self.assertEqual(csvs, set(self.teams))

    def test_team_records(self):
        for key, team in self.teams.items():
            with self.subTest(key):
                self.assertEqual(set(team) >= {"selector", "season", "asset_code", "nickname", "city", "abbreviation",
                                                "template", "retail_same_season"}, True)
                code, abbreviation = build.FRANCHISES[team["selector"]]
                self.assertEqual((team["asset_code"], team["abbreviation"]), (code, abbreviation))
                self.assertTrue(key.startswith(team["selector"]) and key.endswith(str(team["season"])))
                self.assertTrue(team["template"].startswith(f"h-{code}-"))

    def test_csv_contract(self):
        for key in self.teams:
            with self.subTest(key):
                columns, rows = load_team_rows(key)
                self.assertEqual(tuple(columns), build.CSV_COLUMNS)
                self.assertEqual(len(rows), 53)
                self.assertEqual([int(r["index"]) for r in rows], list(range(53)))
                counts = collections.Counter(r["position"] for r in rows)
                for position, need in CONTRACT_MINIMUMS.items():
                    self.assertGreaterEqual(counts[position], need, position)
                self.assertGreaterEqual(counts["OLB"] + counts["ILB"], 3)
                self.assertGreaterEqual(counts["OLB"], 2)
                self.assertGreaterEqual(counts["ILB"], 2)
                jerseys = [int(r["jersey"]) for r in rows]
                self.assertTrue(all(1 <= j <= 99 for j in jerseys))
                self.assertEqual(len(set(jerseys)), 53, "jersey numbers are unique inside a team")
                names = set()
                for r in rows:
                    self.assertEqual(r["pool"], "primary")
                    self.assertIn(r["position"], rr.POSITIONS)
                    self.assertEqual(rr.validate_name(r["first"]), r["first"])
                    self.assertEqual(rr.validate_name(r["last"]), r["last"])
                    names.add((r["first"], r["last"]))
                    self.assertTrue(60 <= int(r["height"]) <= 84)
                    self.assertTrue(150 <= int(r["weight"]) <= 405)
                    self.assertTrue(0 <= int(r["years_pro"]) <= 31)
                    self.assertIn(r["hand"], ("Left", "Right"))
                    self.assertRegex(r["birth_date"], r"^\d{4}-\d{2}-\d{2}$")
                    for rating in rr.RATING_BYTE_ORDER:
                        self.assertTrue(0 <= int(r[rating]) <= 99, (r["last"], rating))
                    self.assertIn(int(r["power_run_style"]), (1, 50, 99))
                    self.assertEqual(int(r["kicking_style"]), 99 if r["position"] == "K" else 1 if r["position"] == "P" else 49)
                    if r["position"] != "QB":
                        # the model writes 5; 2K's own files (THE MISS teams) also use 24 and 0 for non-QBs
                        self.assertIn(int(r["scramble"]), (0, 5, 24))
                self.assertEqual(len(names), 53)
                by_position = collections.defaultdict(list)
                for r in rows:
                    by_position[r["position"]].append(int(r["depth"]))
                for position, depths in by_position.items():
                    self.assertEqual(sorted(depths), list(range(1, len(depths) + 1)), position)

    def test_manifest_pins_every_csv(self):
        for key, entry in self.manifest["teams"].items():
            raw = (TEAMS / f"{key}.csv").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["csv_sha256"])
            self.assertEqual(len(entry["players"]), 53)
        self.assertEqual(self.manifest["sources"]["nflverse"]["licence"], "CC-BY-4.0")

    def test_featured_players_are_on_their_teams(self):
        spec = json.loads(build.SPEC.read_text(encoding="utf-8"))
        for key, team in spec["teams"].items():
            _, rows = load_team_rows(key)
            names = {build.ascii_name(p["source_name"]) for p in self.manifest["teams"][key]["players"]}
            for featured in team.get("featured", []):
                self.assertIn(featured, names, (key, featured))

    def test_stars_play_like_stars(self):
        """The brief's own examples: 2007 Brady and Moss, 2022 Jefferson, 2016 Julio Jones (DESIGN target)."""
        def player(key, first, last):
            _, rows = load_team_rows(key)
            hits = [r for r in rows if (r["first"], r["last"]) == (first, last)]
            self.assertEqual(len(hits), 1, (key, first, last))
            return {k: int(v) for k, v in hits[0].items() if k in rr.RATING_BYTE_ORDER}
        brady = player("patriots_2007", "Tom", "Brady")
        self.assertGreaterEqual(brady["pass_accuracy"], 94)
        self.assertGreaterEqual(brady["pass_read_coverage"], 94)
        for key, first, last in (("patriots_2007", "Randy", "Moss"), ("vikings_2022", "Justin", "Jefferson"),
                                 ("falcons_2016", "Julio", "Jones")):
            wr = player(key, first, last)
            self.assertGreaterEqual(wr["catch"], 95, last)
            self.assertGreaterEqual(wr["run_route"], 95, last)
            self.assertGreaterEqual(wr["speed"], 88, last)

    def test_same_season_retail_teams_carry_2k_ratings(self):
        """THE MISS teams are 2K's own 1998 files: every rating comes from a slot of the same position family."""
        for key in ("falcons_1998", "vikings_1998"):
            self.assertEqual(self.teams[key]["retail_same_season"], self.teams[key]["template"])
            for player in self.manifest["teams"][key]["players"]:
                basis = player["ratings_basis"]
                self.assertIn("slot", basis)
                self.assertEqual(build.FAMILY[basis["slot_position"]] == build.FAMILY[
                    load_team_rows(key)[1][player["index"]]["position"]] or basis["basis"].startswith("retail slot named"), True)


class SpeedSourceTests(unittest.TestCase):
    """Main's speed rule (2026-09-23): retail 2K speed, else the combine 40, else a cited 40, else the flagged profile."""
    SPEED_ROLES = ("WR", "CB", "FS", "SS", "HB", "DE", "OLB")

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((TEAMS / "manifest.json").read_text(encoding="utf-8"))
        cls.forty = json.loads(rm.DEFAULT_FORTY_SOURCES.read_text(encoding="utf-8"))
        cls.cited = rm.load_forty_sources(rm.DEFAULT_FORTY_SOURCES)

    def model_players(self):
        for key, team in self.manifest["teams"].items():
            _, rows = load_team_rows(key)
            for player in team["players"]:
                basis = player["ratings_basis"]
                if "model" in basis:
                    yield key, player, basis, rows[player["index"]]

    def test_every_model_player_records_where_his_speed_came_from(self):
        seen = collections.Counter()
        for key, player, basis, row in self.model_players():
            source = basis["speed_source"]
            seen[source] += 1
            self.assertIn(source, rm.SPEED_SOURCES, (key, row["last"]))
            if source in ("combine", "cited_combine", "pro_day", "other_40"):
                self.assertEqual(int(row["speed"]), rm.clamp(rm.Reference.load().speed_from_forty(basis["forty"]), 30, 99))
            if source in ("cited_combine", "pro_day", "other_40"):
                entry = self.cited[player["gsis_id"]]
                self.assertEqual((entry["forty"], entry["source_url"]), (basis["forty"], basis["forty_source"]))
            if source == "profile":
                self.assertIn("speed_flag", basis)
                self.assertNotIn(player["gsis_id"], self.cited, (key, row["last"]))
        self.assertGreater(seen["pro_day"], 100)

    def test_speed_roles_fall_back_to_the_profile_only_after_a_search(self):
        """Every WR, CB, S, RB and edge rusher on the profile was searched: the sources file lists him with no time."""
        for key, player, basis, row in self.model_players():
            if row["position"] in self.SPEED_ROLES and basis["speed_source"] == "profile":
                entry = self.forty["players"].get(player["gsis_id"])
                self.assertIsNotNone(entry, (key, row["first"], row["last"]))
                self.assertIsNone(entry["forty"], (key, row["last"]))

    def test_cited_forty_entries_carry_their_evidence(self):
        for pid, entry in self.forty["players"].items():
            with self.subTest(pid):
                if entry["forty"] is None:
                    self.assertTrue(entry["note"])
                    continue
                self.assertIn(entry["kind"], rm.FORTY_KINDS)
                self.assertTrue(entry["source_url"].startswith("http") and entry["quote"])
                self.assertIs(entry["found_on_page"], True)
                self.assertFalse(any(d in json.dumps(entry, ensure_ascii=False) for d in DASHES))

    def test_retail_identities_under_other_names(self):
        """2K lists Ed Reed as Edward Reed and Ike Taylor under his playing name: both keep 2K's own physicals."""
        reed = [p for p in self.manifest["teams"]["ravens_2012"]["players"] if p["source_name"] == "Ed Reed"][0]
        self.assertEqual(reed["retail_identity"], "alias of retail Edward Reed")
        self.assertEqual(reed["ratings_basis"]["speed_source"], "retail_anchor")
        _, rows = load_team_rows("steelers_2008")
        taylor = [r for r in rows if (r["first"], r["last"]) == ("Ike", "Taylor")]
        self.assertEqual(len(taylor), 1)
        entry = [p for p in self.manifest["teams"]["steelers_2008"]["players"] if p["index"] == int(taylor[0]["index"])][0]
        self.assertEqual(entry["retail_identity"], "exact")


class RegenerationTests(unittest.TestCase):
    def test_generator_reproduces_the_data(self):
        inputs = Path(os.environ.get("NFL2K5_ESPN25_INPUTS", str(build.DEFAULT_INPUTS)))
        needed = (inputs / "play_by_play_2007.csv.gz", inputs / "play_by_play_2025.csv.gz",
                  inputs / "roster_weekly_2025.csv", build.DEFAULT_RETAIL / "vc_53450030" / "0")
        if not all(p.exists() for p in needed):
            raise unittest.SkipTest("private inputs (nflverse downloads, retail game) are not on this machine")
        result = subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_espn25_more_moments_build.py"),
                                 "--inputs", str(inputs), "--check"],
                                capture_output=True, text=True, timeout=900)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("reproduce exactly", result.stdout)


if __name__ == "__main__":
    unittest.main()
