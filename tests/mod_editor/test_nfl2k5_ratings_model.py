"""The real-player ratings model (job m2): position mapping, percentiles, the retail scale, styles, CLI.

Synthetic fixtures only, except the last class, which rates real 2007 players when the private nflverse downloads
are present (it skips otherwise).
"""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_ratings_model as rm  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

PRIVATE = Path("/media/noah/Storage/.b76-research/m2/inputs/nflverse")


class FakeRecord:
    def __init__(self, position, ratings):
        self.position_name = position
        self._ratings = ratings

    def ratings(self):
        return dict(self._ratings)

    def overall(self):
        weights = rr.OVERALL_WEIGHTS.get(self.position_name)
        return round(sum(self._ratings[k] * w for k, w in weights.items()) / sum(weights.values()))


class FakePlayer:
    def __init__(self, first, last, position, ratings):
        self.first, self.last = first, last
        self.record = FakeRecord(position, ratings)


class FakeTeam:
    def __init__(self, index):
        self.index = index


class FakeDocument:
    """32 clubs; at every position a ladder of players from weak (20) to strong (95)."""

    def __init__(self):
        self.teams = [FakeTeam(i) for i in range(32)]
        self.players = {i: [] for i in range(32)}
        for position in rr.POSITIONS:
            for n in range(64):
                level = 20 + 75 * n / 63
                ratings = {r: round(level) for r in rr.RATING_BYTE_ORDER}
                ratings["speed"] = round(50 + 45 * n / 63)
                self.players[n % 32].append(FakePlayer(f"P{n}", f"{position}{n}", position, ratings))

    def team_players(self, index):
        return self.players[index]


def write_csv(path, rows):
    fields = sorted({k for row in rows for k in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def synthetic_league(folder: Path):
    """40 QBs with rising EPA, 40 WRs with rising yards, 30 kickers; ids Q00.., W00.., K00.."""
    stats, roster = [], []
    for i in range(40):
        stats.append({"player_id": f"Q{i:02d}", "position": "QB", "season_type": "REG", "games": 16,
                      "attempts": 20 + 15 * i, "completions": round((20 + 15 * i) * (0.5 + 0.004 * i)),
                      "passing_epa": -20 + 4 * i, "passing_yards": (20 + 15 * i) * 7, "passing_air_yards": (20 + 15 * i) * (6 + 0.05 * i),
                      "sacks_suffered": 10, "carries": 20, "rushing_yards": 3 * i, "rushing_epa": 0})
        roster.append({"gsis_id": f"Q{i:02d}", "position": "QB", "status": "ACT", "weight": 220})
        stats.append({"player_id": f"W{i:02d}", "position": "WR", "season_type": "REG", "games": 16,
                      "targets": 10 + 3 * i, "receptions": 6 + 2 * i, "receiving_yards": 60 + 40 * i, "receiving_tds": i // 4})
        roster.append({"gsis_id": f"W{i:02d}", "position": "WR", "status": "ACT", "weight": 200})
    for i in range(30):
        stats.append({"player_id": f"K{i:02d}", "position": "K", "season_type": "REG", "games": 16,
                      "fg_att": 30, "fg_made": 18 + i // 3, "fg_missed": 12 - i // 3, "fg_long": 40 + i // 2,
                      "fg_made_50_59": i // 10, "pat_made": 30})
        roster.append({"gsis_id": f"K{i:02d}", "position": "K", "status": "ACT", "weight": 190})
    for i in range(10):   # never-played backups on the roster population
        roster.append({"gsis_id": f"B{i:02d}", "position": "QB", "status": "ACT", "weight": 215})
    return write_csv(folder / "stats.csv", stats), write_csv(folder / "roster.csv", roster)


class PositionMappingTests(unittest.TestCase):
    def test_map_position(self):
        cases = [(("RB", ""), "HB"), (("FB", ""), "FB"), (("OL", "T"), "T"), (("OL", "", 330), "T"), (("OL", "", 305), "G"),
                 (("DL", "NT"), "DT"), (("DL", "", 300), "DT"), (("DL", "", 265), "DE"), (("LB", "MLB"), "ILB"),
                 (("LB", ""), "OLB"), (("DB", "", 190), "CB"), (("DB", "", 205), "FS"), (("DB", "", 215), "SS"),
                 (("SAF", "", 200), "FS"), (("S", "", 212), "SS"), (("LS", ""), "C"), (("K", ""), "K"), (("PK", ""), "K")]
        for args, expected in cases:
            self.assertEqual(rm.map_position(*args), expected, args)


class ReferenceTests(unittest.TestCase):
    def test_committed_reference(self):
        ref = rm.Reference.load()
        self.assertEqual(len(ref.grid), rm.GRID_POINTS)
        self.assertEqual(set(ref.positions), set(rr.POSITIONS))
        for position, table in ref.positions.items():
            self.assertGreater(table["n"], 25, position)
            for rating in rr.RATING_BYTE_ORDER:
                q = table["quantiles"][rating]
                self.assertEqual(len(q), rm.GRID_POINTS)
                self.assertEqual(q, sorted(q), (position, rating))
                self.assertEqual(len(table["profile"][rating]), rm.GRID_POINTS)
        self.assertLess(ref.speed["r"], -0.9)
        self.assertGreater(ref.speed["n"], 500)
        self.assertEqual(ref.data["population"].startswith("retail 2004"), True)

    def test_build_reference_from_a_document(self):
        data = rm.build_reference(FakeDocument())
        ref = rm.Reference(data)
        self.assertAlmostEqual(ref.quantile("QB", "pass_accuracy", 1.0), 95, delta=0.5)
        self.assertAlmostEqual(ref.quantile("QB", "pass_accuracy", 0.0), 20, delta=0.5)
        self.assertGreater(ref.profile("WR", "catch", 0.9), ref.profile("WR", "catch", 0.1))
        self.assertIsNone(data["speed_from_forty"]["r"])   # no combine names given: the documented default line


class RatingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        folder = Path(cls.tmp.name)
        stats, roster = synthetic_league(folder)
        cls.stats = rm.SeasonStats.from_files(2030, stats, roster)
        cls.ref = rm.Reference(rm.build_reference(FakeDocument()))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rate(self, **row):
        row.setdefault("weight", 210)
        row.setdefault("years_pro", 5)
        return rm.rate_player(row, self.stats, self.ref)

    def test_better_quarterbacks_rate_higher(self):
        previous = None
        for i in range(0, 40, 5):
            ratings, basis = self.rate(position="QB", gsis_id=f"Q{i:02d}")
            if previous:
                for key in ("pass_accuracy", "pass_read_coverage", "composure"):
                    self.assertGreaterEqual(ratings[key], previous[key], (i, key))
            previous = ratings
        best, basis = self.rate(position="QB", gsis_id="Q39")
        self.assertGreaterEqual(basis["q_value"], 0.97)
        self.assertGreaterEqual(best["pass_accuracy"], 90)

    def test_a_backup_who_never_played_rates_low_and_a_rookie_gets_a_draft_prior(self):
        backup, basis = self.rate(position="QB", gsis_id="B01")
        self.assertLess(basis["q_value"], 0.2)
        rookie, basis = self.rate(position="QB", gsis_id="", years_pro=0, draft_number=5)
        self.assertEqual(basis["rookie_prior"], 0.55)
        self.assertGreater(rookie["pass_accuracy"], backup["pass_accuracy"])

    def test_style_bytes(self):
        self.assertEqual(self.rate(position="K", gsis_id="K29")[0]["kicking_style"], 99)
        self.assertEqual(self.rate(position="P", gsis_id="")[0]["kicking_style"], 1)
        wr = self.rate(position="WR", gsis_id="W10")[0]
        self.assertEqual((wr["kicking_style"], wr["scramble"]), (49, 5))
        self.assertEqual(self.rate(position="HB", gsis_id="", weight=235)[0]["power_run_style"], 99)
        self.assertEqual(self.rate(position="HB", gsis_id="", weight=200)[0]["power_run_style"], 1)
        self.assertEqual(self.rate(position="HB", gsis_id="", weight=218)[0]["power_run_style"], 50)
        self.assertEqual(self.rate(position="CB", gsis_id="")[0]["power_run_style"], 1)
        self.assertEqual(self.rate(position="T", gsis_id="")[0]["power_run_style"], 99)
        qb = self.rate(position="QB", gsis_id="Q20")[0]
        self.assertEqual(qb["scramble"] % 2, 0)

    def test_anchor_keeps_retail_physicals_and_style(self):
        anchor = {r: 70 for r in rr.RATING_BYTE_ORDER}
        anchor.update(speed=80, agility=78, scramble=97, pass_arm_strength=99)
        row = {"position": "QB", "gsis_id": "Q30", "birth_date": "1998-02-01", "weight": 215}
        plain, _ = rm.rate_player(row, self.stats, self.ref)
        ratings, basis = rm.rate_player(row, self.stats, self.ref, anchor=anchor)
        self.assertEqual(ratings["speed"], 80 - (2030 - 1998 - 30))
        self.assertEqual(ratings["pass_arm_strength"], rm.clamp(0.5 * 99 + 0.5 * plain["pass_arm_strength"]))
        self.assertEqual(ratings["scramble"], 97)
        self.assertIn("anchor", basis)

    def test_forty_sets_speed(self):
        self.stats.forty["W05"] = 4.40
        try:
            ratings, basis = self.rate(position="WR", gsis_id="W05")
        finally:
            del self.stats.forty["W05"]
        self.assertEqual(ratings["speed"], rm.clamp(self.ref.speed_from_forty(4.40), 30, 99))
        self.assertEqual(basis["forty"], 4.40)
        self.assertEqual(basis["speed_source"], "combine")

    def test_speed_source_order(self):
        """Retail anchor, then the combine 40, then a cited 40 (combine, pro day, other), then the flagged profile."""
        cited = {"forty": 4.30, "kind": "pro_day", "source_url": "https://example.org/p", "quote": "ran a 4.30"}
        anchor = {r: 70 for r in rr.RATING_BYTE_ORDER}
        anchor["speed"] = 91
        row = {"position": "WR", "gsis_id": "W06", "weight": 200, "birth_date": "2005-01-01"}
        self.stats.forty_cited["W06"] = cited
        try:
            profile_speed = rm.rate_player({**row, "gsis_id": "W07"}, self.stats, self.ref)
            self.assertEqual(profile_speed[1]["speed_source"], "profile")
            self.assertIn("speed_flag", profile_speed[1])
            ratings, basis = rm.rate_player(row, self.stats, self.ref)
            self.assertEqual((basis["speed_source"], basis["forty"], basis["forty_source"]), ("pro_day", 4.30, "https://example.org/p"))
            self.assertEqual(ratings["speed"], rm.clamp(self.ref.speed_from_forty(4.30), 30, 99))
            for kind, source in (("combine", "cited_combine"), ("other", "other_40")):
                self.stats.forty_cited["W06"] = {**cited, "kind": kind}
                self.assertEqual(rm.rate_player(row, self.stats, self.ref)[1]["speed_source"], source)
            self.stats.forty["W06"] = 4.60          # the nflverse combine time wins over any cited time
            ratings, basis = rm.rate_player(row, self.stats, self.ref)
            self.assertEqual((basis["speed_source"], basis["forty"]), ("combine", 4.60))
            ratings, basis = rm.rate_player(row, self.stats, self.ref, anchor=anchor)   # 2K's own speed wins over all
            self.assertEqual((basis["speed_source"], ratings["speed"]), ("retail_anchor", 91))
        finally:
            self.stats.forty_cited.pop("W06", None)
            self.stats.forty.pop("W06", None)

    def test_starter_floor(self):
        """A starter with little production rates at least like the league's weakest regular starter."""
        bench, _ = rm.rate_player({"position": "QB", "gsis_id": "B03", "weight": 215}, self.stats, self.ref)
        started, basis = rm.rate_player({"position": "QB", "gsis_id": "B03", "weight": 215, "depth": 1}, self.stats, self.ref)
        self.assertIn("starter_floor", basis)
        self.assertEqual(basis["q_value"], round(self.stats.starter_floor("QB"), 4))
        self.assertGreater(started["pass_accuracy"], bench["pass_accuracy"])
        second, basis = rm.rate_player({"position": "QB", "gsis_id": "B03", "weight": 215, "depth": 2}, self.stats, self.ref)
        self.assertNotIn("starter_floor", basis)

    def test_honor_floor(self):
        ratings, basis = rm.rate_player({"position": "WR", "gsis_id": "W02", "weight": 200}, self.stats, self.ref,
                                        honors={"W02": "AP1"})
        self.assertGreaterEqual(basis["q_value"], 0.97)
        self.assertEqual(basis["honor"], "AP1")

    def test_kicker_aspects(self):
        good, _ = self.rate(position="K", gsis_id="K29")
        poor, _ = self.rate(position="K", gsis_id="K00")
        self.assertGreater(good["kick_accuracy"], poor["kick_accuracy"])
        self.assertGreater(good["kick_power"], poor["kick_power"])

    def test_cli_round_trip(self):
        folder = Path(self.tmp.name)
        roster = write_csv(folder / "team.csv", [{"first": "Test", "last": "Passer", "position": "QB", "gsis_id": "Q39",
                                                  "weight": 220, "years_pro": 6}])
        stats, population = folder / "stats.csv", folder / "roster.csv"
        reference = folder / "ref.json"
        reference.write_text(json.dumps(rm.build_reference(FakeDocument())))
        out = folder / "rated.csv"
        self.assertEqual(rm.main(["rate", "--roster", str(roster), "--season", "2030", "--stats", str(stats),
                                  "--population", str(population), "--reference", str(reference), "--out", str(out)]), 0)
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        self.assertEqual(len(rows), 1)
        self.assertGreaterEqual(int(rows[0]["pass_accuracy"]), 90)
        self.assertIn("q_value", json.loads(rows[0]["rating_basis"]))


class FortySourceTests(unittest.TestCase):
    ENTRY = {"forty": 4.41, "kind": "pro_day", "source_url": "https://example.org/a", "quote": "a 4.41 at his pro day"}

    def test_load_forty_sources(self):
        loaded = rm.load_forty_sources({"A": self.ENTRY, "B": {"forty": None, "note": "searched, none found"}})
        self.assertEqual(list(loaded), ["A"])
        self.assertEqual(loaded["A"]["forty"], 4.41)
        document = {"schema": rm.FORTY_SOURCES_SCHEMA, "players": {"A": self.ENTRY}}
        self.assertEqual(list(rm.load_forty_sources(document)), ["A"])
        self.assertEqual(rm.load_forty_sources(None), {})
        for bad in ({**self.ENTRY, "forty": 3.2}, {**self.ENTRY, "kind": "hand"}, {**self.ENTRY, "quote": ""},
                    {**self.ENTRY, "source_url": None}):
            with self.assertRaises(ValueError):
                rm.load_forty_sources({"A": bad})
        with self.assertRaises(ValueError):
            rm.load_forty_sources({"schema": "other", "players": {}})

    def test_committed_forty_sources_file(self):
        data = json.loads(rm.DEFAULT_FORTY_SOURCES.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], rm.FORTY_SOURCES_SCHEMA)
        loaded = rm.load_forty_sources(rm.DEFAULT_FORTY_SOURCES)
        self.assertGreater(len(loaded), 100)
        for pid, entry in loaded.items():
            self.assertTrue(entry["source_url"].startswith("http"), pid)
            self.assertIn(entry["kind"], rm.FORTY_KINDS)

    def test_name_key(self):
        self.assertEqual(rm.name_key("Odell Beckham Jr."), "odellbeckham")
        self.assertEqual(rm.name_key("T.J. Hockenson"), rm.name_key("TJ Hockenson"))
        self.assertEqual(rm.name_key("Le Kevin Smith"), rm.name_key("LeKevin Smith"))
        self.assertEqual(rm.name_key("Ha Ha Clinton-Dix"), "hahaclintondix")

    def test_combine_joins_by_pfr_id_then_name_and_draft_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            stats = write_csv(folder / "stats.csv", [{"player_id": pid, "position": "WR", "season_type": "REG"}
                                                     for pid in ("G1", "G2", "G3", "G4", "G5")])
            players = write_csv(folder / "players.csv", [
                {"gsis_id": "G1", "pfr_id": "AaaA00", "display_name": "Al Able", "draft_year": "2010"},
                {"gsis_id": "G2", "pfr_id": "", "display_name": "Bo Baker Jr.", "draft_year": "2011"},
                {"gsis_id": "G3", "pfr_id": "", "display_name": "Cy Cole", "draft_year": "2012"},
                {"gsis_id": "G4", "pfr_id": "", "display_name": "Cy Cole", "draft_year": "2012"},
                {"gsis_id": "G5", "pfr_id": "", "display_name": "Di Dunn", "draft_year": "", "rookie_season": "2013"}])
            combine = write_csv(folder / "combine.csv", [
                {"season": "2010", "draft_year": "2010", "pfr_id": "AaaA00", "player_name": "Al Able", "forty": "4.50"},
                {"season": "2011", "draft_year": "2011", "pfr_id": "", "player_name": "Bo Baker", "forty": "4.40"},
                {"season": "2012", "draft_year": "2012", "pfr_id": "", "player_name": "Cy Cole", "forty": "4.45"},
                {"season": "2013", "draft_year": "", "pfr_id": "", "player_name": "Di Dunn", "forty": "4.55"}])
            cited = {"G1": {**self.ENTRY, "forty": 4.30}, "G3": self.ENTRY}
            season = rm.SeasonStats.from_files(2014, stats, combine=combine, players=players, forty_sources=cited)
        self.assertEqual(season.forty, {"G1": 4.50, "G2": 4.40, "G5": 4.55})   # two Cy Coles: no join
        self.assertEqual(list(season.forty_cited), ["G3"])                      # the combine time wins for G1


class DepthChartTests(unittest.TestCase):
    def test_weekly_schema(self):
        rows = [{"game_type": "REG", "depth_team": "1", "formation": "Offense", "gsis_id": "A", "week": "1"},
                {"game_type": "REG", "depth_team": "1", "formation": "Offense", "gsis_id": "A", "week": "2"},
                {"game_type": "REG", "depth_team": "2", "formation": "Offense", "gsis_id": "B", "week": "2"},
                {"game_type": "POST", "depth_team": "1", "formation": "Offense", "gsis_id": "B", "week": "19"},
                {"game_type": "REG", "depth_team": "1", "formation": "Special Teams", "gsis_id": "C", "week": "1"}]
        self.assertEqual(rm.starts_from_depth_charts(rows), {"A": 2.0})

    def test_snapshot_schema(self):
        rows = [{"dt": "d1", "team": "T", "gsis_id": "A", "pos_rank": "1"},
                {"dt": "d2", "team": "T", "gsis_id": "A", "pos_rank": "1"},
                {"dt": "d2", "team": "T", "gsis_id": "B", "pos_rank": "1"},
                {"dt": "d1", "team": "T", "gsis_id": "B", "pos_rank": "2"}]
        self.assertEqual(rm.starts_from_depth_charts(rows), {"A": 17.0, "B": 8.5})


class RealSeasonTests(unittest.TestCase):
    """2007 from the private nflverse downloads (skips without them)."""

    def test_2007_stars(self):
        stats_file = PRIVATE / "stats_player_reg_2007.csv.gz"
        if not stats_file.exists():
            raise unittest.SkipTest("private nflverse downloads are not on this machine")
        stats = rm.SeasonStats.from_files(2007, stats_file, PRIVATE / "roster_2007.csv",
                                          depth_charts=PRIVATE / "depth_charts_2007.csv")
        ref = rm.Reference.load()
        roster = {r["full_name"]: r for r in rm.read_csv(PRIVATE / "roster_2007.csv")}

        def rate(name, position):
            r = roster[name]
            return rm.rate_player({"position": position, "gsis_id": r["gsis_id"], "weight": r["weight"],
                                   "birth_date": r["birth_date"], "years_pro": r["years_exp"]}, stats, ref)[0]
        self.assertGreaterEqual(rate("Tom Brady", "QB")["pass_accuracy"], 94)
        self.assertGreaterEqual(rate("Randy Moss", "WR")["catch"], 95)
        self.assertLess(rate("Matt Cassel", "QB")["pass_accuracy"], 70)


if __name__ == "__main__":
    unittest.main()
