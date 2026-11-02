"""Job j5b-leaders (b780): the franchise leaders data and the builder that makes it.

Offline and quick.  The helper tests run the builder's pure pieces on synthetic input (the two-source rule, the Wikipedia table
reader, the nflverse totals, the evidence-to-data assembly).  The data tests check the shipped
``data/nfl2k5_franchise_leaders_2026.json`` and its evidence file: the data must equal what the evidence says (the builder's
``verify``), every shipped row must carry a second source, ranks and values must be ordered, the printed guide line must contain
the number, and the roster links must resolve.
"""
from __future__ import annotations

import contextlib
import csv
import gzip
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import b780_franchise_leaders_build as B  # noqa: E402

DATA = ROOT / "data" / "nfl2k5_franchise_leaders_2026.json"
EVIDENCE = ROOT / "data" / "nfl2k5_franchise_leaders_evidence_2026.json"
COHORT = ROOT / "tools" / "b77" / "f12_cohort.json"


def table(rows, header):
    def tr(cells, tag="td"):
        return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"
    return "<table>" + "".join(tr(h, "th") for h in header) + "".join(tr(r) for r in rows) + "</table>"


class Helpers(unittest.TestCase):
    def test_years(self):
        self.assertEqual(B.parse_years("1975-87"), set(range(1975, 1988)))
        self.assertEqual(B.parse_years("1940-41; 45-50"), {1940, 1941} | set(range(1945, 1951)))
        self.assertEqual(B.parse_years("2008-16; '25"), set(range(2008, 2017)) | {2025})
        self.assertEqual(B.parse_years("2017, 20-present"), {2017} | set(range(2020, 2026)))
        self.assertEqual(B.parse_years("1998-2001"), {1998, 1999, 2000, 2001})
        self.assertEqual(B.parse_years("2019"), {2019})
        self.assertEqual(B.parse_years("2014-18, 26"), set(range(2014, 2019)))      # a 2026 roster note is no career season

    def test_game_dates_january_games_belong_to_the_previous_season(self):
        self.assertEqual(B.game_date("1/2/2022 vs. Kansas City"), ("2022-01-02", 2021))
        self.assertEqual(B.game_date("12/13/2015"), ("2015-12-13", 2015))
        self.assertEqual(B.game_date("12/3/00 at N.Y."), ("2000-12-03", 2000))
        self.assertEqual(B.game_date("11/20/77")[1], 1977)
        self.assertEqual(B.game_date("1998"), (None, 1998))

    def test_names(self):
        self.assertEqual(B.split_name("Walter Payton"), ("Walter", "Payton", ""))
        self.assertEqual(B.split_name("Odell Beckham Jr."), ("Odell", "Beckham", "Jr."))
        self.assertEqual(B.split_name("Allen Robinson II"), ("Allen", "Robinson", "II"))
        self.assertEqual(B.split_name("Portis"), ("", "Portis", ""))
        self.assertEqual(B.norm("Matt Forté"), B.norm("Matt Forte"))
        self.assertEqual(B.norm("Ja'Marr Chase"), "jamarr chase")

    def test_team_cells_follow_the_franchise_across_eras(self):
        self.assertEqual(B.club_of_cell("BAL", 1970), "IND")           # Baltimore Colts
        self.assertEqual(B.club_of_cell("BAL", 2005), "BAL")           # Ravens
        self.assertEqual(B.club_of_cell("HOU", 1990), "TEN")           # Oilers
        self.assertEqual(B.club_of_cell("HOU", 2010), "HOU")
        self.assertEqual(B.club_of_cell("STL", 1980), "ARI")           # football Cardinals
        self.assertEqual(B.club_of_cell("STL", 2005), "LAR")
        self.assertEqual(B.club_of_cell("OAK", 2001), "LV")
        self.assertEqual(B.club_of_cell("SD", 2010), "LAC")
        self.assertEqual(B.club_of_cell("LA", 1990), "AMBIG")          # Rams or Raiders
        self.assertEqual(B.club_of_cell("2TM", 2012), None)
        self.assertEqual(B.club_of_cell("Chicago Bears", 1990), "CHI")
        self.assertEqual(B.club_of_cell("Tulane", 2005), None)

    def test_positions(self):
        self.assertEqual(B.position_code("Running back"), "HB")
        self.assertEqual(B.position_code("Wide receiver / Kick returner"), "WR")
        self.assertEqual(B.position_code("Tight end"), "TE")
        self.assertEqual(B.position_code("Defensive end"), "DE")
        self.assertEqual(B.position_code("Middle linebacker"), "ILB")
        self.assertEqual(B.position_code("Linebacker"), "OLB")
        self.assertEqual(B.position_code("Placekicker"), "K")
        self.assertIsNone(B.position_code("Head coach"))
        for code in B.POSITION_OVERRIDE.values():
            self.assertIn(code, B.POSITIONS)

    def test_rank_rows_keep_printed_order_and_rerank_columns(self):
        printed = {"kind": "list", "rows": [{"rank": 1, "value": 9}, {"rank": 2, "value": 7}, {"rank": 2, "value": 7}, {"rank": 4, "value": 5}]}
        self.assertEqual([rk for rk, _ in B.rank_rows(printed)], [1, 2, 2, 4])
        column = {"kind": "column", "rows": [{"rank": 1, "value": 5}, {"rank": 2, "value": 9}, {"rank": 3, "value": 9}, {"rank": 4, "value": 1}]}
        self.assertEqual([(rk, r["value"]) for rk, r in B.rank_rows(column)], [(1, 9), (1, 9), (3, 5), (4, 1)])


class Plumbing(unittest.TestCase):
    def test_title_candidates_try_the_plain_name_first_then_what_the_category_suggests(self):
        c = B.title_candidates("Matt Fort\u00e9", {"rushing_yards"})
        self.assertEqual(c[0], "Matt Fort\u00e9")
        self.assertIn("Matt Forte", c)
        self.assertIn("Matt Fort\u00e9 (American football)", c)
        self.assertIn("Matt Fort\u00e9 (running back)", c)
        self.assertLessEqual(len(c), 16)

    def test_years_overlap_identifies_the_right_player(self):
        self.assertTrue(B.years_overlap_ok({2008, 2009, 2010}, {2008, 2009, 2010, 2011}))
        self.assertFalse(B.years_overlap_ok({1990, 1991}, {2008, 2009, 2010}))
        self.assertFalse(B.years_overlap_ok(set(), {2008}))
        self.assertTrue(B.years_overlap_ok({2008}, set()))                         # a season record names no career years

    def test_the_evidence_is_plain_json_with_one_row_per_line(self):
        obj = {"a": 1, "rows": [{"x": 1}, {"x": 2}], "empty": [], "nested": {"k": [1, 2]}}
        text = B.dumps_by_line(obj)
        self.assertEqual(json.loads(text), obj)
        self.assertNotIn("\r", text)
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(text.count("\n"), 9)

    def test_malformed_spans_do_not_break_a_table(self):
        html = '<table class="wikitable"><tr><th rowspan="2"">Year</th><th>Team</th><th>Rushing Yds</th></tr><tr><td>2008</td><td>CHI</td><td>5</td></tr></table>'
        self.assertEqual(B._span('2"'), 2)
        self.assertEqual(B._span(None), 1)
        self.assertEqual(len(B.html_tables(html)), 1)


class WikipediaTables(unittest.TestCase):
    def test_offense_rows_sum_over_the_club_only_and_skip_postseason_and_college(self):
        # a header with a group row, written by hand (table() writes one flat header row)
        html = ("<h2>Regular season</h2><table><tr><th rowspan=2>Year</th><th rowspan=2>Team</th><th colspan=3>Rushing</th></tr>"
                "<tr><th>Att</th><th>Yds</th><th>TD</th></tr>"
                "<tr><td>2008</td><td>CHI</td><td>316</td><td>1,238</td><td>8</td></tr>"
                "<tr><td>2009</td><td>CHI</td><td>258</td><td>929</td><td>4</td></tr>"
                "<tr><td>2010</td><td>2TM</td><td>10</td><td>50</td><td>0</td></tr>"
                "<tr><td>2011</td><td>NYJ</td><td>99</td><td>400</td><td>1</td></tr>"
                "<tr><td>2026</td><td>CHI</td><td>5</td><td>20</td><td>0</td></tr></table>"
                "<h2>Postseason</h2><table><tr><th rowspan=2>Year</th><th rowspan=2>Team</th><th colspan=3>Rushing</th></tr>"
                "<tr><th>Att</th><th>Yds</th><th>TD</th></tr><tr><td>2010</td><td>CHI</td><td>20</td><td>100</td><td>1</td></tr>"
                "<tr><td>2011</td><td>CHI</td><td>1</td><td>2</td><td>0</td></tr></table>")
        r = B.club_sums(html, "CHI")
        self.assertEqual(r["sums"]["rushing_yards"], 1238 + 929)
        self.assertEqual(r["sums"]["rushing_td"], 12)
        self.assertEqual(r["years"], [2008, 2009])          # 2026 is after the cut-off, the playoff table is skipped, 2TM is no club
        self.assertEqual(r["seasons"]["rushing_yards"], {"2008": 1238.0, "2009": 929.0})

    def test_a_quarterbacks_sacks_are_not_defensive_sacks_and_defense_sacks_are_half_sacks(self):
        qb = ("<table><tr><th rowspan=2>Year</th><th rowspan=2>Team</th><th colspan=2>Passing</th><th colspan=2>Sacks</th></tr>"
              "<tr><th>Yds</th><th>TD</th><th>Sck</th><th>Yds</th></tr><tr><td>2010</td><td>CHI</td><td>3,274</td><td>23</td><td>35</td><td>200</td></tr>"
              "<tr><td>2011</td><td>CHI</td><td>1,812</td><td>13</td><td>20</td><td>120</td></tr></table>")
        r = B.club_sums(qb, "CHI")
        self.assertEqual(r["sums"]["passing_yards"], 5086)
        self.assertNotIn("sacks_half", r["sums"])
        d = ("<table><tr><th rowspan=2>Year</th><th rowspan=2>Team</th><th colspan=3>Tackles</th><th colspan=1>Interceptions</th></tr>"
             "<tr><th>Cmb</th><th>Solo</th><th>Sck</th><th>Int</th></tr><tr><td>2000</td><td>CHI</td><td>124</td><td>98</td><td>8.0</td><td>2</td></tr>"
             "<tr><td>2001</td><td>CHI</td><td>100</td><td>80</td><td>5.5</td><td>3</td></tr></table>")
        r = B.club_sums(d, "CHI")
        self.assertEqual(r["sums"]["sacks_half"], 27.0)           # 13.5 sacks = 27 half sacks
        self.assertEqual(r["sums"]["tackles"], 224)
        self.assertEqual(r["sums"]["interceptions"], 5)

    def test_an_ambiguous_team_cell_counts_only_for_the_club_the_player_otherwise_has(self):
        rows = [["1985", "LA", "10", "100"], ["1986", "LA", "12", "120"], ["1990", "RAI", "5", "50"], ["1996", "OAK", "6", "60"]]
        head = [["Year", "Team", "Rushing Att", "Rushing Yds"]]
        html = table(rows, head)
        raiders = B.club_sums(html, "LV")
        self.assertEqual(raiders["sums"]["rushing_yards"], 100 + 120 + 50 + 60)      # every clear row is a Raiders row, so "LA" is the Raiders
        rams = B.club_sums(html, "LAR")
        self.assertNotIn("rushing_yards", rams["sums"])
        mixed = table([["1985", "LA", "1", "10"], ["1996", "STL", "1", "20"], ["1993", "OAK", "1", "30"]], head)
        self.assertEqual(B.club_sums(mixed, "LV")["sums"]["rushing_yards"], 30)       # Rams and Raiders rows both exist: the ambiguous row stays out

    def test_flat_header_without_group_names(self):
        html = table([["1981", "SD", "14", "109", "525", "4.8", "28", "3", "46", "329", "7.2", "29", "3"],
                      ["1982", "SD", "9", "87", "430", "4.9", "48", "6", "13", "66", "5.1", "12", "0"],
                      ["1984", "CIN", "16", "103", "490", "4.8", "40", "4", "28", "300", "10.7", "40", "1"]],
                     [["Year", "Team", "GP", "Att", "Yds", "Avg", "Lng", "TD", "Rec", "Yds", "Avg", "Lng", "TD"]])
        r = B.club_sums(html, "LAC")
        self.assertEqual(r["sums"]["rushing_yards"], 955)
        self.assertEqual(r["sums"]["receiving_yards"], 395)
        self.assertEqual(r["sums"]["receptions"], 59)

    def test_infobox_position(self):
        html = '<table class="infobox"><tr><th colspan=2>Name</th></tr><tr><th>Position:</th><td>Running back</td></tr></table>'
        self.assertEqual(B.infobox_position(html), "Running back")


class NflverseTotals(unittest.TestCase):
    def test_weekly_rows_are_summed_per_club_for_the_regular_season_only(self):
        cols = ["season_type", "team", "player_id", "player_display_name", "position", "week", "passing_yards", "passing_tds", "rushing_yards",
                "rushing_tds", "receptions", "receiving_yards", "receiving_tds", "def_sacks", "def_interceptions", "def_tackles_solo", "def_tackle_assists"]
        rows = [
            ["REG", "LA", "p1", "Pat Passer", "QB", "1", "300", "3", "10", "0", "0", "0", "0", "0", "0", "0", "0"],
            ["REG", "LA", "p1", "Pat Passer", "QB", "2", "250", "1", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
            ["POST", "LA", "p1", "Pat Passer", "QB", "20", "999", "9", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
            ["REG", "CHI", "p2", "Dee Fender", "DE", "1", "0", "0", "0", "0", "0", "0", "0", "1.5", "1", "4", "2"],
        ]
        with tempfile.TemporaryDirectory() as folder:
            for yr in range(B.NV_WINDOW[0], B.NV_WINDOW[1] + 1):
                with gzip.open(Path(folder) / f"stats_player_week_{yr}.csv.gz", "wt", encoding="utf-8", newline="") as f:
                    w = csv.writer(f, lineterminator="\n")
                    w.writerow(cols)
                    if yr == 2010:
                        w.writerows(rows)
            nv = B.NFLverse(folder).load()
        self.assertEqual(nv.career[("LAR", "p1")]["passing_yards"], 550)          # nflverse "LA" is the Rams franchise; the playoff row is skipped
        self.assertEqual(nv.season[("LAR", "p1", 2010)]["passing_td"], 4)
        self.assertEqual(nv.career[("CHI", "p2")]["sacks_half"], 3.0)             # 1.5 sacks in half sacks
        self.assertEqual(nv.career[("CHI", "p2")]["tackles"], 6)
        self.assertEqual(sorted(x[0] for x in nv.game[("LAR", "passing_yards")]), [250, 300])
        self.assertEqual(nv.find("LAR", "Pat Passer", {2010}), "p1")
        self.assertIsNone(nv.find("CHI", "Pat Passer", {2010}))


class TheRule(unittest.TestCase):
    def test_decide(self):
        d = B.decide("rushing_yards", 8602, 8602, 8595, True)         # Forte: Wikipedia agrees, nflverse close
        self.assertEqual((d["decision"], d["confirmed_by"], d["nflverse"]), ("ship", ["wikipedia"], "close"))
        d = B.decide("passing_yards", 23443, None, 23443, True)       # nflverse alone, exact, whole career
        self.assertEqual((d["decision"], d["confirmed_by"]), ("ship", ["nflverse"]))
        d = B.decide("passing_yards", 23443, 23443, 23443, True)
        self.assertEqual(d["confirmed_by"], ["wikipedia", "nflverse"])
        self.assertEqual(B.decide("rushing_td", 46, 47, None, False)["decision"], "conflict")          # sources differ
        self.assertEqual(B.decide("rushing_yards", 8602, 8602, 9500, True)["decision"], "review")       # nflverse far off
        self.assertEqual(B.decide("rushing_yards", 8602, None, None, False)["decision"], "single")
        # nflverse sees only 1999+: its total may not exceed the guide's, and an equal partial total proves nothing
        self.assertEqual(B.decide("rushing_yards", 8000, None, 8000, False)["decision"], "single")
        self.assertEqual(B.decide("rushing_yards", 8000, 8000, 9000, False)["decision"], "review")
        # tackles are never compared with nflverse
        self.assertEqual(B.decide("tackles", 1488, 1488, 900, True)["decision"], "ship")
        self.assertEqual(B.decide("tackles", 1488, None, 1488, True)["decision"], "single")

    def test_tolerances(self):
        self.assertEqual(B.nv_status("rushing_yards", 8602, 8595, True), "close")
        self.assertEqual(B.nv_status("rushing_yards", 8602, 8500, True), "off")
        self.assertEqual(B.nv_status("sacks_half", 249, 245, True), "close")
        self.assertEqual(B.nv_status("receptions", 500, 500, True), "exact")
        self.assertEqual(B.nv_status("passing_td", 100, 130, False), "conflict")

    def test_guard(self):
        self.assertTrue(B.guard_violated("rushing_yards", {"bar": 3000, "other_value": 3500}))
        self.assertFalse(B.guard_violated("rushing_yards", {"bar": 3000, "other_value": 3010}))
        self.assertFalse(B.guard_violated("tackles", {"bar": 100, "other_value": 900}))
        self.assertFalse(B.guard_violated("rushing_yards", {"bar": 3000, "other_value": None}))


def candidate(club, scope, cat, rank, order, name, value, wiki=None, nv=None, covered=False, kind="list", **extra):
    c = {"club": club, "scope": scope, "category": cat, "rank": rank, "order": order, "name": name, "years": "2000-05", "span": [2000, 2005],
         "value": value, "kind": kind, "position": "HB", "guide": {"page": 1, "title": "T", "raw": f"{rank}. {name} {value}"}}
    if wiki is not None:
        c["wikipedia"] = {"title": name, "revid": 1, "retrieved": "2026-11-02", "value": wiki, "years": [2000, 2005]}
    if nv is not None:
        c["nflverse"] = {"value": nv, "covered": covered, "player": name}
    c.update(extra)
    return c


class Assembly(unittest.TestCase):
    def evidence(self, cands, guards=(), missing=()):
        return {"through_season": 2025, "rules": {}, "public_sources": {}, "candidates": list(cands), "guards": list(guards), "missing": list(missing)}

    def test_longest_verified_run_from_rank_one(self):
        cands = [candidate("CHI", "career", "rushing_yards", 1, 0, "A One", 100, wiki=100),
                 candidate("CHI", "career", "rushing_yards", 2, 1, "B Two", 90),                        # single source
                 candidate("CHI", "career", "rushing_yards", 3, 2, "C Three", 80, wiki=80)]            # fine but behind a failed rank
        data, excluded = B.assemble(self.evidence(cands))
        rows = data["clubs"]["CHI"]["career"]["rushing_yards"]
        self.assertEqual([r["name"] for r in rows], ["A One"])
        self.assertEqual(rows[0]["confirmed_by"], ["wikipedia"])
        self.assertEqual({e["name"]: e["reason"] for e in excluded}, {"B Two": "single", "C Three": "after a rank that is single"})

    def test_a_conflict_cuts_the_run_and_is_listed(self):
        cands = [candidate("GB", "career", "passing_td", 1, 0, "A One", 50, wiki=50, nv=50, covered=True),
                 candidate("GB", "career", "passing_td", 2, 1, "B Two", 40, wiki=41)]
        data, excluded = B.assemble(self.evidence(cands))
        self.assertEqual(len(data["clubs"]["GB"]["career"]["passing_td"]), 1)
        self.assertEqual(excluded[0]["reason"], "conflict")
        self.assertEqual((excluded[0]["guide"], excluded[0]["wikipedia"]), (40, 41))
        self.assertEqual(data["counts"]["shipped"]["career"], 1)

    def test_slots_and_ties(self):
        cands = [candidate("DAL", "career", "receptions", i + 1, i, f"P{i}", 100 - i, wiki=100 - i) for i in range(4)]
        data, excluded = B.assemble(self.evidence(cands))
        self.assertEqual(len(data["clubs"]["DAL"]["career"]["receptions"]), 3)       # three leaders; the fourth is simply beyond the slots
        self.assertEqual(excluded, [])
        cands = [candidate("DAL", "season", "rushing_yards", 1, 0, "Tie A", 2000, wiki=2000, season=1995),
                 candidate("DAL", "season", "rushing_yards", 1, 1, "Tie B", 2000, wiki=2000, season=1996)]
        data, _ = B.assemble(self.evidence(cands))
        self.assertEqual(len(data["clubs"]["DAL"]["season"]["rushing_yards"]), 1)      # one record slot

    def test_a_failed_completeness_guard_withholds_the_group(self):
        cands = [candidate("NE", "career", "passing_yards", 1, 0, "A One", 5000, wiki=5000)]
        guard = {"club": "NE", "scope": "career", "category": "passing_yards", "bar": 3000, "other_value": 9000, "other_player": "Someone"}
        data, excluded = B.assemble(self.evidence(cands, guards=[guard]))
        self.assertEqual(data["clubs"]["NE"]["career"], {})
        self.assertEqual(excluded[0]["reason"], "incomplete list")

    def test_rows_carry_person_fields_and_scope_specific_fields(self):
        cands = [candidate("CHI", "game", "rushing_yards", 1, 0, "Walter Payton", 275, nv=275, covered=True, season=1977, date="1977-11-20", week=None),
                 candidate("CHI", "season", "rushing_yards", 1, 0, "Walter Payton Jr.", 1852, wiki=1852, season=1977)]
        data, _ = B.assemble(self.evidence(cands))
        game = data["clubs"]["CHI"]["game"]["rushing_yards"][0]
        self.assertEqual((game["first"], game["last"], game["position"], game["season"], game["date"]), ("Walter", "Payton", "HB", 1977, "1977-11-20"))
        season = data["clubs"]["CHI"]["season"]["rushing_yards"][0]
        self.assertEqual((season["suffix"], "date" in season), ("Jr.", False))

    def test_the_best_verified_list_of_a_stat_ships(self):
        # the guide prints sacks twice: all-time (unofficial sacks included, Wikipedia differs) and since 1982 (verified)
        a = [candidate("CHI", "career", "sacks_half", 1, 0, "Old Timer", 300, wiki=260, variant=0, complete_to=10, list_note="all-time, unofficial included"),
             candidate("CHI", "career", "sacks_half", 2, 1, "Next One", 240, wiki=240, variant=0, complete_to=10, list_note="all-time, unofficial included")]
        b = [candidate("CHI", "career", "sacks_half", 1, 0, "Richard Dent", 249, wiki=249, variant=1, complete_to=11, list_note="official sacks since 1982"),
             candidate("CHI", "career", "sacks_half", 2, 1, "Steve McMichael", 185, wiki=185, variant=1, complete_to=11, list_note="official sacks since 1982")]
        data, excluded = B.assemble(self.evidence(a + b))
        rows = data["clubs"]["CHI"]["career"]["sacks_half"]
        self.assertEqual([r["name"] for r in rows], ["Richard Dent", "Steve McMichael"])
        self.assertEqual(data["clubs"]["CHI"]["notes"]["career.sacks_half"], "official sacks since 1982")
        self.assertEqual(excluded, [])
        # with no verified variant the longer, list-kind one is the one that is reported
        data, excluded = B.assemble(self.evidence(a))
        self.assertEqual(data["clubs"]["CHI"]["career"], {})
        self.assertEqual([e["reason"] for e in excluded], ["conflict", "after a rank that is conflict"])

    def test_ties_and_columns_are_marked(self):
        cands = [candidate("CAR", "career", "rushing_td", 1, 0, "A One", 60, wiki=60, kind="column"),
                 candidate("CAR", "career", "rushing_td", 2, 1, "B Two", 50, wiki=50, kind="column", tie=True)]
        data, _ = B.assemble(self.evidence(cands))
        rows = data["clubs"]["CAR"]["career"]["rushing_td"]
        self.assertEqual([r.get("basis") for r in rows], ["column", "column"])
        self.assertEqual([r.get("tie") for r in rows], [None, True])

    def test_missing_lists_are_listed(self):
        data, excluded = B.assemble(self.evidence([], missing=[{"club": "ATL", "scope": "career", "category": "tackles", "why": "no list"}]))
        self.assertEqual(excluded[0]["reason"], "not printed in the guide")
        self.assertEqual(data["clubs"]["ATL"]["name"], "Atlanta Falcons")
        self.assertEqual(sorted(data["clubs"]), sorted(B.CLUBS))


def full_guide():
    """a transcription file that covers every (scope, category) pair with one trivial row"""
    lists = [{"scope": s, "category": c, "title": "T", "pdf_page": 5, "kind": "list", "ranked_by": "x", "scope_note": "regular season", "complete_to": 1,
              "rows": [{"rank": 1, "tie": False, "name": "A One", "years": "2000", "value": 10, "raw": "1. A One 2000 10"}]}
             for s in B.SCOPES for c in B.GUIDE_CATEGORY]
    return {"team": "CHI", "guide_ident": "x-media-guide", "through_season": 2025, "lists": lists, "missing": [], "notes": []}


class GuideFiles(unittest.TestCase):
    def test_a_complete_file_is_accepted(self):
        self.assertEqual(B.check_guide(full_guide()), ([], []))

    def test_every_pair_needs_a_list_or_a_reason(self):
        d = full_guide()
        gone = d["lists"].pop()
        errs, _ = B.check_guide(d)
        self.assertEqual(len(errs), 1)
        self.assertIn(f"{gone['scope']}/{gone['category']}", errs[0])
        d["missing"].append({"scope": gone["scope"], "category": gone["category"], "why": "the guide prints none"})
        self.assertEqual(B.check_guide(d)[0], [])

    def test_a_number_must_be_on_its_printed_line_and_a_ranked_list_must_not_rise(self):
        d = full_guide()
        d["lists"][0]["rows"][0]["raw"] = "1. A One 2000 11"
        errs, _ = B.check_guide(d)
        self.assertTrue(any("not in the printed line" in e for e in errs))
        d = full_guide()
        d["lists"][0]["rows"] += [{"rank": 2, "tie": False, "name": "B Two", "years": "2001", "value": 12, "raw": "2. B Two 2001 12"}]
        errs, warns = B.check_guide(d)
        self.assertEqual(errs, [])
        self.assertEqual(len(warns), 1)

    def test_sacks_with_halves_and_commas_in_the_printed_line(self):
        d = full_guide()
        row = {"rank": 1, "tie": False, "name": "A One", "years": "1983-93", "value": 124.5, "raw": "1. A One 1983-93 124.5"}
        d["lists"][0]["rows"] = [row, dict(row, rank=2, name="B Two", value=16726, raw="2. B Two 1975-87 3,838 16,726 4.4")]
        d["lists"][0]["kind"] = "column"
        self.assertEqual(B.check_guide(d)[0], [])

    def test_unknown_names_are_refused(self):
        d = full_guide()
        d["team"] = "XXX"
        d["lists"][0]["category"] = "fumbles"
        errs, _ = B.check_guide(d)
        self.assertTrue(any("unknown club" in e for e in errs) and any("bad category" in e for e in errs))

    def test_import_writes_normalised_copies_and_refuses_broken_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "dest"
            src.mkdir()
            good = full_guide()
            good["notes"] = ["a \u2014 b"]
            (src / "CHI.json").write_text(json.dumps(good), encoding="utf-8")
            broken = full_guide()
            broken["team"] = "ATL"
            broken["lists"].pop()
            (src / "ATL.json").write_text(json.dumps(broken), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = B.main(["import-guides", "--src", str(src), "--dest", str(dest)])
            self.assertEqual(rc, 1)
            self.assertEqual(sorted(p.name for p in dest.iterdir()), ["CHI.json"])
            text = (dest / "CHI.json").read_text(encoding="utf-8")
            self.assertNotIn("\u2014", text)
            self.assertEqual(json.loads(text)["notes"], ["a - b"])


class BuildOffline(unittest.TestCase):
    """The whole ``build`` command on synthetic inputs: a guide file, nflverse weekly files, a pre-filled Wikipedia cache."""

    NV_COLS = ["season_type", "team", "player_id", "player_display_name", "position", "week", "passing_yards", "passing_tds", "rushing_yards",
               "rushing_tds", "receptions", "receiving_yards", "receiving_tds", "def_sacks", "def_interceptions", "def_tackles_solo", "def_tackle_assists"]

    def write_nflverse(self, folder):
        def row(team, pid, name, pos, week, rush=0, rec=0):
            r = dict.fromkeys(self.NV_COLS, "0")
            r.update(season_type="REG", team=team, player_id=pid, player_display_name=name, position=pos, week=str(week), rushing_yards=str(rush), receptions=str(rec))
            return [r[c] for c in self.NV_COLS]
        for yr in range(B.NV_WINDOW[0], B.NV_WINDOW[1] + 1):
            rows = []
            if yr >= 2020:                                          # Garrett Williams: 500 rushing yards and 50 catches a season, 2023 as two big games
                for wk in range(1, 11):
                    rush = (200 if wk == 5 else 300 if wk == 6 else 0) if yr == 2023 else 50
                    rows.append(row("CHI", "p-gw", "Garrett Williams", "RB", wk, rush=rush, rec=5))
            if 2010 <= yr <= 2014:                                  # someone the guide's rushing list does not print: 500 a season, no big game
                rows += [row("CHI", "p-ob", "Other Back", "RB", wk, rush=50) for wk in range(1, 11)]
            with gzip.open(Path(folder) / f"stats_player_week_{yr}.csv.gz", "wt", encoding="utf-8", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(self.NV_COLS)
                w.writerows(rows)
        header = ["season", "team", "status", "full_name", "first_name", "last_name", "birth_date", "gsis_id"]
        with open(Path(folder) / "roster_2026.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(header)
            w.writerow(["2026", "CHI", "ACT", "Garrett Williams", "Garrett", "Williams", "2001-06-01", "00-0000001"])

    def write_wikipedia_cache(self, folder):
        wiki = B.Wiki(folder)
        old_timer = [{"heading": "Regular season", "caption": "", "grid": [
            ["Year", "Team", "Receiving", "Receiving"], ["", "", "Rec", "Yds"]] + [[str(y), "CHI", "40" if y < 1970 else "40", "400"] for y in range(1960, 1970)] + [["1970", "CHI", "0", "0"]]}]
        infobox = {"heading": "", "caption": "", "grid": [["Old Timer", "Old Timer"], ["Position", "Wide receiver"]]}
        pages = {"Old Timer": [infobox] + old_timer}
        # every title the build may try is answered from the cache (a missing article is a cache entry too), so the test never touches the network
        for name in ("Old Timer", "Garrett Williams", "Third Guy"):
            for cats in ({"receptions"}, {"rushing_yards"}, {"receptions", "rushing_yards"}):
                for title in B.title_candidates(name, cats):
                    tables = pages.get(title)
                    obj = ({"title": title, "missing": True, "retrieved": "2026-11-02"} if tables is None else
                           {"title": title, "revid": 123, "canonical_title": title, "tables": tables, "retrieved": "2026-11-02"})
                    wiki.path(title).write_text(json.dumps(obj), encoding="utf-8")

    def guide(self):
        def row(rank, name, years, value, raw=None):
            return {"rank": rank, "tie": False, "name": name, "years": years, "value": value, "raw": raw or f"{rank}. {name} {years} {value}"}
        lists = [
            {"scope": "career", "category": "rec", "title": "CAREER RECEPTIONS", "pdf_page": 10, "kind": "list", "ranked_by": "receptions",
             "scope_note": "regular season", "complete_to": 3,
             "rows": [row(1, "Old Timer", "1960-70", 400), row(2, "Garrett Williams", "2020-25", 300), row(3, "Third Guy", "1980-85", 200)]},
            {"scope": "career", "category": "rush_yds", "title": "CAREER RUSHING", "pdf_page": 11, "kind": "list", "ranked_by": "rushing yards",
             "scope_note": "regular season", "complete_to": 2,
             "rows": [row(1, "Garrett Williams", "2020-25", 3000), row(2, "Third Guy", "1980-85", 2000)]},
            {"scope": "season", "category": "rush_yds", "title": "MOST RUSHING YARDS, SEASON", "pdf_page": 12, "kind": "list", "ranked_by": "rushing yards",
             "scope_note": "regular season", "complete_to": 1, "rows": [row(1, "Garrett Williams", "2023", 500)]},
            {"scope": "game", "category": "rush_yds", "title": "MOST RUSHING YARDS, GAME", "pdf_page": 13, "kind": "list", "ranked_by": "rushing yards",
             "scope_note": "regular season", "complete_to": 1, "rows": [row(1, "Garrett Williams", "10/15/2023 vs. Minnesota", 300, "300 Garrett Williams 10/15/2023 vs. Minnesota")]},
        ]
        return {"team": "CHI", "guide_ident": "synthetic-chi-2026-media-guide", "through_season": 2025, "lists": lists,
                "missing": [{"scope": "career", "category": "tackles", "why": "no list"}], "notes": ["synthetic \u2014 test"]}

    def test_build_ships_what_two_sources_agree_on_and_verify_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for sub in ("nv", "wp", "guides"):
                (tmp / sub).mkdir()
            self.write_nflverse(tmp / "nv")
            self.write_wikipedia_cache(tmp / "wp")
            (tmp / "guides" / "CHI.json").write_text(json.dumps(self.guide()), encoding="utf-8")
            out, ev = tmp / "data.json", tmp / "evidence.json"
            with contextlib.redirect_stdout(io.StringIO()):
                rc = B.main(["build", "--guides", str(tmp / "guides"), "--nflverse", str(tmp / "nv"), "--wiki-cache", str(tmp / "wp"),
                             "--clubs", "CHI", "--out", str(out), "--evidence", str(ev)])
            self.assertEqual(rc, 0)
            data, evidence = json.loads(out.read_text(encoding="utf-8")), json.loads(ev.read_text(encoding="utf-8"))
            chi = data["clubs"]["CHI"]
            # receptions: Old Timer by Wikipedia, Garrett Williams by nflverse (whole career 2020-25) and linked to his roster record; the
            # third man has no second source, so the run ends at rank 2
            rows = chi["career"]["receptions"]
            self.assertEqual([(r["name"], r["value"], r["confirmed_by"]) for r in rows], [("Old Timer", 400, ["wikipedia"]), ("Garrett Williams", 300, ["nflverse"])])
            self.assertEqual(rows[0]["position"], "WR")
            self.assertEqual((rows[1]["position"], rows[1]["link"]["index"], rows[1]["link"]["gsis_id"]), ("HB", 0, "00-0000001"))
            self.assertEqual(rows[1]["span"], [2020, 2025])
            # rushing: nflverse knows a Bear with 2,500 yards whom the guide's list does not print, so the list cannot be complete
            self.assertNotIn("rushing_yards", chi["career"])
            reasons = {(e["category"], e["name"]): e["reason"] for e in evidence["excluded"]}
            self.assertEqual(reasons[("rushing_yards", "Garrett Williams")], "incomplete list")
            self.assertEqual(reasons[("receptions", "Third Guy")], "single")
            # season and game records: nflverse equals the guide exactly; the January/October date gives the season and the week is found
            season = chi["season"]["rushing_yards"][0]
            self.assertEqual((season["season"], season["value"], season["confirmed_by"]), (2023, 500, ["nflverse"]))
            game = chi["game"]["rushing_yards"][0]
            self.assertEqual((game["season"], game["date"], game["week"], game["value"]), (2023, "2023-10-15", 6, 300))
            self.assertTrue(any(e["reason"] == "not printed in the guide" for e in evidence["excluded"]))
            self.assertNotIn("\u2014", json.dumps(evidence["sources"]))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.main(["verify", "--out", str(out), "--evidence", str(ev)]), 0)


@unittest.skipUnless(DATA.exists() and EVIDENCE.exists(), "franchise leaders data not built yet")
class ShippedData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA.read_text(encoding="utf-8"))
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_schema_and_clubs(self):
        d = self.data
        self.assertEqual((d["schema"], d["base_year"], d["through_season"]), (B.SCHEMA, 2026, 2025))
        self.assertEqual(sorted(d["clubs"]), sorted(B.CLUBS))
        self.assertEqual(list(d["categories"]), list(B.CATEGORIES))
        self.assertEqual(sorted(c["arena_index"] for c in d["clubs"].values()), list(range(32)))
        for code, c in d["clubs"].items():
            self.assertEqual(c["name"], B.CLUBS[code][0])

    def test_data_is_exactly_what_the_evidence_says(self):
        data, excluded = B.assemble(self.evidence)
        self.assertEqual(data, self.data)
        self.assertEqual(excluded, self.evidence["excluded"])

    def test_every_shipped_row_has_a_second_source_and_ordered_values(self):
        total = 0
        for code, club in self.data["clubs"].items():
            for scope in B.SCOPES:
                for cat, rows in club[scope].items():
                    self.assertIn(cat, B.CATEGORIES)
                    self.assertLessEqual(len(rows), B.SLOTS[scope], (code, scope, cat))
                    prev = None
                    for i, r in enumerate(rows):
                        total += 1
                        self.assertTrue(r["confirmed_by"], (code, scope, cat, r["name"]))
                        self.assertTrue(set(r["confirmed_by"]) <= {"wikipedia", "nflverse"})
                        self.assertTrue(r["last"], (code, r["name"]))
                        self.assertIn(r["position"], B.POSITIONS, (code, scope, cat, r["name"]))
                        self.assertGreater(r["value"], 0)
                        if scope == "career" and prev is not None:
                            self.assertLessEqual(r["value"], prev, (code, cat, r["name"]))
                        prev = r["value"]
                    self.assertEqual(len({r["name"] for r in rows}), len(rows), (code, scope, cat))
        self.assertGreater(total, 0)
        self.assertEqual(total, sum(self.data["counts"]["shipped"].values()))

    def test_the_guide_line_contains_the_number_and_the_other_sources_agree(self):
        by_key = {}
        for c in self.evidence["candidates"]:
            by_key[(c["club"], c["scope"], c["category"], c["name"], c["rank"], c["guide"]["page"])] = c
        checked = 0
        for code, club in self.data["clubs"].items():
            for scope in B.SCOPES:
                for cat, rows in club[scope].items():
                    for r in rows:
                        c = by_key[(code, scope, cat, r["name"], r["rank"], r["guide_page"])]
                        self.assertEqual(c["value"], r["value"])
                        raw = c["guide"]["raw"].replace(",", "")
                        unit = r["value"] / B.SCALE.get(cat, 1)
                        shown = str(int(unit)) if float(unit).is_integer() else f"{unit:.1f}"
                        if c.get("adjusted"):
                            unit = c["adjusted"]["guide_value"] / B.SCALE.get(cat, 1)
                            shown = str(int(unit)) if float(unit).is_integer() else f"{unit:.1f}"
                        self.assertIn(shown, raw, (code, scope, cat, r["name"], c["guide"]["raw"]))
                        if "wikipedia" in r["confirmed_by"]:
                            self.assertEqual(c["wikipedia"]["value"], r["value"])
                            self.assertTrue(c["wikipedia"]["revid"], (code, r["name"]))
                        if "nflverse" in r["confirmed_by"]:
                            self.assertEqual(c["nflverse"]["value"], r["value"])
                            self.assertTrue(c["nflverse"]["covered"])
                        checked += 1
        self.assertEqual(checked, sum(self.data["counts"]["shipped"].values()))

    def test_links_resolve_to_roster_identities(self):
        cohort = {r[0]: r for r in json.loads(COHORT.read_text(encoding="utf-8"))["records"]}
        linked = 0
        for club in self.data["clubs"].values():
            for rows in club["career"].values():
                for r in rows:
                    link = r.get("link")
                    if not link:
                        continue
                    linked += 1
                    rec = cohort[link["index"]]
                    self.assertEqual((rec[1], rec[2], rec[3]), (link["first"], link["last"], link["birth_date"]))
        self.assertGreaterEqual(linked, 0)

    def test_excluded_rows_say_why(self):
        reasons = {"single", "conflict", "review", "incomplete list", "not printed in the guide"}
        for e in self.evidence["excluded"]:
            self.assertTrue(e["reason"] in reasons or e["reason"].startswith("after a rank that is "), e)
        shipped = sum(self.data["counts"]["shipped"].values())
        self.assertEqual(self.data["counts"]["by_decision"].get("ship", 0) >= shipped, True)

    def test_sources_are_pinned_in_the_evidence(self):
        ev = self.evidence
        self.assertEqual(len(ev["sources"]["nflverse_files"]), 27)
        for sha in ev["sources"]["nflverse_files"].values():
            self.assertRegex(sha, r"^[0-9a-f]{64}$")
        self.assertEqual(sorted(ev["sources"]["guides"]), sorted(B.CLUBS))
        for club, g in ev["sources"]["guides"].items():
            self.assertTrue(g["item"], club)
        text = json.dumps(self.data, ensure_ascii=False)
        self.assertNotIn("—", text)                  # no em dashes in public text


if __name__ == "__main__":
    unittest.main()
