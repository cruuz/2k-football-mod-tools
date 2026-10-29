"""b779 fh1: years pro = NFL seasons since entering the league, and sourced season history for created real players."""

import copy
import datetime as dt
import json
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "tools" / "b77"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from mod_editor.core import nfl2k5_career_stats as cs
from mod_editor.core import nfl2k5_created_history as ch
from mod_editor.core import nfl2k5_free_agents as free_agents
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_team_history as th
from tests.mod_editor.test_nfl2k5_team_history import synthetic_body

import b779_years_in_league as conv
import b779_fh1_history_data as hd

DATA = _REPO_ROOT / "mod_editor" / "data"


def _json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


ENTRY = _json("nfl2k5_entry_years_2026.v1.json")
HISTORY = _json("nfl2k5_created_history_2026.v1.json")
FREE_AGENTS = _json("nfl2k5_free_agents_2026.v1.json")
DEPTH = _json("nfl2k5_free_agent_depth_2026.v1.json")


def person(name):
    return next(p for p in HISTORY["players"] if f"{p['first']} {p['last']}" == name)


def years_pro(entry_year):
    return rr.years_pro_for_season(2026, entry_year)


def native(rows, **kwargs):
    """A synthetic roster the save decoder accepts (the franchise-history tests patch the same root word)."""
    body = bytearray(synthetic_body(rows, **kwargs))
    struct.pack_into("<i", body, 0x14, 0x2D)
    return bytes(body)


def body_for(players, **kwargs):
    rows = [dict(first=p["first"], last=p["last"], birth=dt.date.fromisoformat(p["birth_date"]), position=0,
                 count=p["years_pro"], stream=None) for p in players]
    return native(rows, **kwargs)


def words_by_year(doc, key, count):
    out = {}
    for w in doc.history_words[key]:
        word = cs.Word(w)
        out.setdefault(2026 - (count - word.slot), {})[word.field] = word
    return out


class YearsInLeagueTests(unittest.TestCase):
    def test_kaepernick_is_sixteen_and_the_convention_is_stamped(self):
        self.assertEqual(ENTRY["entries"]["00-0027974"], 2011)
        self.assertEqual(years_pro(2011), 16)
        row = next(p for p in DEPTH["players"] if p["last"] == "Kaepernick")
        self.assertEqual(row["fields"]["years_pro"], 16)
        for document in (FREE_AGENTS, DEPTH, ENTRY, HISTORY):
            self.assertEqual(document["years_pro_convention"], rr.YEARS_PRO_CONVENTION)

    def test_every_shipped_real_player_row_is_entry_year_based(self):
        rows = [(p["gsis_id"], p["fields"]["years_pro"]) for p in DEPTH["players"]]
        rows += [(p["gsis_id"], p["fields"]["years_pro"]) for p in FREE_AGENTS["added"]]
        self.assertEqual(len(rows), 533 + 140)
        for gsis, value in rows:
            self.assertEqual(value, years_pro(ENTRY["entries"][gsis]), gsis)

    def test_continuous_veteran_is_unchanged_a_gap_player_gets_more_and_a_rookie_is_one(self):
        # Mahomes entered 2017 and played every year: accrued seasons (9) + 1 is the same as years in the league
        self.assertEqual(years_pro(ENTRY["entries"]["00-0033873"]), 10)
        self.assertEqual(rr.years_pro_from_years_exp(9), 10)
        # Kaepernick played 2011-2016 only: accrued + 1 was 7, years in the league is 16
        self.assertEqual(rr.years_pro_from_years_exp(6), 7)
        self.assertEqual(years_pro(2011), 16)
        # a 2026 rookie is 1 (the card prints R) and the field is five bits
        self.assertEqual(years_pro(2026), 1)
        self.assertEqual(rr.years_pro_for_season(2026, 1990), rr.YEARS_PRO_MAX)

    def test_old_convention_data_is_refused_everywhere(self):
        old = copy.deepcopy(FREE_AGENTS)
        old["years_pro_convention"] = "game_rookie_1"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fa.json"
            path.write_text(json.dumps(old), encoding="utf-8", newline="\n")
            with self.assertRaises(ValueError):
                free_agents.load_data(path)
        edits = {"schema": rr.EDITS_SCHEMA, "edits": [], "years_pro_convention": "game_rookie_1"}
        with self.assertRaises(rr.RosterRecordError):
            rr.read_edits(edits)
        edits["years_pro_convention"] = rr.YEARS_PRO_CONVENTION
        rr.read_edits(edits)
        spec = copy.deepcopy(HISTORY)
        spec["years_pro_convention"] = "game_rookie_1"
        with self.assertRaises(cs.CareerStatsError):
            ch.apply_body(body_for([person("Colin Kaepernick")]), spec)

    def test_converter_converts_once_and_refuses_a_second_run(self):
        document = {"added": [{"gsis_id": "00-0027974", "name": "Colin Kaepernick", "fields": {"years_pro": 7}},
                              {"gsis_id": "00-0033873", "name": "Patrick Mahomes", "fields": {"years_pro": 10}}],
                    "years_pro_convention": "game_rookie_1"}
        out, report = conv.convert_rows(document, "added", conv.load_entry_years(), "test data")
        self.assertEqual([r["fields"]["years_pro"] for r in out["added"]], [16, 10])
        self.assertEqual((report["changed"], report["raised"], report["lowered"]), (1, 1, 0))
        self.assertEqual(out["years_pro_convention"], rr.YEARS_PRO_CONVENTION)
        with self.assertRaises(conv.ConversionRefused):
            conv.convert_rows(out, "added", conv.load_entry_years(), "test data")
        unknown = {"added": [{"gsis_id": "00-9999999", "name": "Nobody", "fields": {"years_pro": 1}}]}
        with self.assertRaises(conv.ConversionRefused):
            conv.convert_rows(unknown, "added", conv.load_entry_years(), "test data")

    def test_roster_generators_use_the_entry_year(self):
        sys.path.insert(0, str(_REPO_ROOT / "tools"))
        import nfl2k5_team_2026_roster as league
        self.assertEqual(league.written_years_pro({"entry_year": "2011", "years_exp": "6"}), 16)
        self.assertEqual(league.written_years_pro({"entry_year": "2026", "years_exp": "0"}), 1)
        self.assertEqual(league.written_years_pro({"entry_year": "", "years_exp": "9"}), 10)


class CreatedHistoryTests(unittest.TestCase):
    def apply(self, names, spec=None, **kwargs):
        players = [person(n) for n in names]
        body = body_for(players, **kwargs)
        spec = copy.deepcopy(spec or HISTORY)
        spec["players"] = [p for p in spec["players"] if f"{p['first']} {p['last']}" in names]
        out, receipt = ch.apply_body(body, spec)
        return cs.decode_body(out), receipt, players

    def test_data_pin_and_sources(self):
        self.assertEqual(ch.load_data()["schema"], ch.SCHEMA)
        self.assertEqual(len(HISTORY["players"]), 763)
        for pin in HISTORY["sources"].values():
            self.assertRegex(pin["sha256"], "^[0-9a-f]{64}$")
            self.assertTrue(pin["url"].startswith("https://github.com/nflverse/nflverse-data/releases/download/"))
        self.assertTrue(HISTORY["fetched_utc"].startswith("2026-10-28"))

    def test_kaepernick_shows_san_francisco_2011_to_2016_with_his_real_lines(self):
        doc, receipt, (kaep,) = self.apply(["Colin Kaepernick"])
        self.assertEqual(receipt["detail_levels"]["full"], 1)                  # protected: every season, whatever the budget
        key = ("primary", 0)
        rows = words_by_year(doc, key, 16)
        self.assertEqual(sorted(rows), list(range(2011, 2017)))
        club = th.RETAIL_TEAM_INDEX["SF"]
        for year, row in rows.items():
            self.assertEqual(row[87].raw & 0xFFFF, club + 1, year)          # TEAM = SF
            self.assertFalse(row[87].folded)
        lines = {2012: (218, 136, 1814, 10, 3), 2013: (416, 243, 3197, 21, 8), 2014: (478, 289, 3369, 19, 10),
                 2015: (244, 144, 1615, 6, 5), 2016: (331, 196, 2241, 16, 4)}
        for year, expected in lines.items():
            got = tuple(rows[year][f].raw & 0xFFFF for f in (6, 7, 8, 9, 10))
            self.assertEqual(got, expected, year)
        self.assertEqual(rows[2011][0].raw & 0xFFFF, 2)                       # two games as a rookie
        self.assertEqual(cs.Word(rows[2011][2].raw).value(cs.BY_ID[2]), -2)   # signed rushing yards
        # the card's slot for 2011 is slot 1: the rookie year, with years pro 16
        self.assertEqual(min(cs.Word(w).slot for w in doc.history_words[key]), 1)

    def test_five_random_created_free_agents_get_their_sourced_rows(self):
        pool = [p for p in HISTORY["players"] if len(p["seasons"]) >= 2 and p["entry_year"] < 2022]
        chosen = random.Random(779).sample(pool, 5)
        names = ["Colin Kaepernick"] + [f"{p['first']} {p['last']}" for p in chosen]
        doc, receipt, players = self.apply(names)
        self.assertEqual(receipt["players_written"], 6)
        for index, p in enumerate(players):
            rows = words_by_year(doc, ("primary", index), p["years_pro"])
            spec = person(f"{p['first']} {p['last']}")
            self.assertEqual(sorted(rows), [s["year"] for s in spec["seasons"]], p["last"])
            for season in spec["seasons"]:
                row = rows[season["year"]]
                self.assertEqual(row[0].raw & 0xFFFF, season["stats"]["games"])
                self.assertEqual(row[87].raw & 0xFFFF, season["team_index"] + 1)

    def test_a_record_with_the_old_accrued_years_pro_is_refused(self):
        kaep = dict(person("Colin Kaepernick"), years_pro=7)
        body = body_for([kaep])
        spec = copy.deepcopy(HISTORY)
        spec["players"] = [person("Colin Kaepernick")]
        with self.assertRaises(cs.CareerStatsError) as raised:
            ch.apply_body(body, spec)
        self.assertIn("years pro", str(raised.exception))

    def test_unrelated_streams_stay_and_a_second_run_is_idempotent(self):
        kaep = person("Colin Kaepernick")
        bystander = dict(first="By", last="Stander", birth=dt.date(1990, 1, 1), position=0, count=5,
                         stream=[(2 << 23) | (0 << 16) | 9 | 0x80000000])
        body = native([dict(first="Colin", last="Kaepernick", birth=dt.date(1987, 11, 3), position=0, count=16, stream=None),
                       bystander])
        spec = copy.deepcopy(HISTORY)
        spec["players"] = [kaep]
        out, _ = ch.apply_body(body, spec)
        doc = cs.decode_body(out)
        self.assertEqual(doc.history_words["primary", 1], (bystander["stream"][0],))
        again, receipt = ch.apply_body(out, spec)
        self.assertEqual(again, out)
        self.assertEqual(receipt["players_already_with_history"], 1)

    def test_the_local_fold_is_the_franchise_upgrade_fold(self):
        from mod_editor.core import nfl2k5_franchise_upgrade as upgrade
        for p in HISTORY["players"][:200]:
            words = ch.season_words(p, p["years_pro"], 2026)
            if not words:
                continue
            for depth in (12, 10, 8, 6, 4, 3, 2):
                self.assertEqual(ch.fold_words(words, p["years_pro"], depth), upgrade.fold_words(words, p["years_pro"], depth))

    def items(self):
        return [(rank, p["years_pro"], ch.season_words(p, p["years_pro"], 2026), bool(p.get("full")))
                for rank, p in enumerate(HISTORY["players"])]

    def test_the_shipped_budget_leaves_a_native_season_and_a_half_of_headroom_words(self):
        """v0.7 had 15,538 free; the first fill left 72. The pass now spends only what is free beyond HEADROOM."""
        free = 50000 - 34462 - ch.HISTORY_RESERVE
        chosen, levels = ch.allocate(self.items(), max(free - ch.HEADROOM, 0), free)
        total = sum(len(w) for w in chosen)
        self.assertLessEqual(total, free - ch.HEADROOM)
        self.assertGreaterEqual(50000 - 34462 - total, ch.HEADROOM + ch.HISTORY_RESERVE)
        self.assertEqual(levels["none"], 0)
        self.assertEqual(levels["latest"], 0)
        self.assertGreaterEqual(levels["full"], 26)                      # the 26 hand-checked players
        self.assertEqual(sum(levels.values()), 763)
        self.assertEqual(levels["full"] + levels["base"], sum(1 for _, _, w, _ in self.items() if w) + sum(1 for _, _, w, _ in self.items() if not w))

    def test_every_player_keeps_a_clean_latest_season_with_team_and_totals_stay_whole(self):
        for p in HISTORY["players"]:
            words = ch.season_words(p, p["years_pro"], 2026)
            if len(p["seasons"]) < 3:
                continue
            base = ch.detail(words, p["years_pro"], 1)
            newest = max(s["year"] for s in p["seasons"])
            slot = p["years_pro"] - (2026 - newest)
            row = {cs.Word(w).field: cs.Word(w) for w in base if cs.Word(w).slot == slot}
            self.assertFalse(row[0].folded, p["last"])
            self.assertEqual(row[87].raw & 0xFFFF, next(s for s in p["seasons"] if s["year"] == newest)["team_index"] + 1)
            # the folded older row has no TEAM word; career games add up to the sourced total
            self.assertFalse(any(cs.Word(w).field == 87 and cs.Word(w).folded for w in base))
            games = sum(cs.Word(w).raw & 0xFFFF for w in base if cs.Word(w).field == 0)
            self.assertEqual(games, sum(s["stats"]["games"] for s in p["seasons"]), p["last"])

    def test_over_budget_the_least_important_drop_first_and_protected_players_never_do(self):
        items = self.items()
        free = 15538 - ch.HISTORY_RESERVE
        base_total = sum(len(ch.detail(w, yp, 1)) for _, yp, w, full in items if not full) + sum(len(w) for _, _, w, full in items if full)
        chosen, levels = ch.allocate(items, base_total - 400, free)
        self.assertGreater(levels["latest"], 0)
        self.assertLessEqual(sum(len(w) for w in chosen), base_total - 400)
        downgraded = [j for j, (_, yp, w, full) in enumerate(items) if len(chosen[j]) < len(ch.detail(w, yp, 1)) and not full]
        kept = [j for j, (_, yp, w, full) in enumerate(items) if len(chosen[j]) >= len(ch.detail(w, yp, 1)) and w and not full]
        self.assertTrue(downgraded and kept)
        self.assertGreater(min(downgraded), max(j for j in kept if j < min(downgraded)) if any(j < min(downgraded) for j in kept) else -1)
        for j, (_, yp, w, full) in enumerate(items):
            if full:
                self.assertEqual(len(chosen[j]), len(w))
        # a budget below the protected players alone refuses instead of overfilling
        with self.assertRaises(cs.CareerStatsError):
            ch.allocate(items, 0, 100)

    def test_a_synthetic_pool_end_to_end_with_a_tiny_free_space(self):
        names = ["Colin Kaepernick"] + [f"{p['first']} {p['last']}" for p in HISTORY["players"] if len(p["seasons"]) >= 6 and not p.get("full")][:3]
        players = [person(n) for n in names]
        spec = copy.deepcopy(HISTORY)
        spec["players"] = players
        body = body_for(players)
        saved = ch.HEADROOM
        try:
            doc = cs.decode_body(body)
            free = doc.pool_capacity - doc.pool_used - ch.HISTORY_RESERVE
            ch.HEADROOM = free - 40                 # 40 words of budget: the three others cannot all keep a folded career row
            out, receipt = ch.apply_body(body, spec)
        finally:
            ch.HEADROOM = saved
        self.assertLessEqual(receipt["words_written"], free)
        self.assertEqual(receipt["detail_levels"]["full"], 1)
        self.assertGreater(receipt["detail_levels"]["latest"] + receipt["detail_levels"]["none"], 0)
        rows = words_by_year(cs.decode_body(out), ("primary", 0), 16)
        self.assertEqual(sorted(rows), list(range(2011, 2017)))


class SnapGamesTests(unittest.TestCase):
    """Games played come from snap counts, not from weeks with a box-score line (Andrew Thomas 2025 read 3 games, he played 13)."""

    def make_dir(self, tmp, snaps, stats, roster_rows):
        d = Path(tmp)
        (d / "FETCHED_AT.txt").write_text("2026-10-28T17:18:58Z\n", encoding="utf-8")
        (d / "players.csv").write_text("gsis_id,pfr_id\n00-1,ThomAn02\n00-2,SnapLo00\n", encoding="utf-8")
        for year in range(2000, 2027):
            rows = [r for r in roster_rows if r[0] == year]
            (d / f"roster_{year}.csv").write_text("season,team,gsis_id,week,entry_year\n" + "".join(
                f"{y},{t},{g},{w},{e}\n" for y, t, g, w, e in rows), encoding="utf-8")
        for year in range(2000, 2026):
            rows = [r for r in stats if r[0] == year]
            (d / f"stats_player_reg_{year}.csv").write_text("player_id,season_type,games,recent_team,completions\n" + "".join(
                f"{g},REG,{n},{t},0\n" for _y, g, n, t in rows), encoding="utf-8")
        for year in range(2012, 2026):
            rows = [r for r in snaps if r[0] == year]
            (d / f"snap_counts_{year}.csv").write_text("game_id,game_type,pfr_player_id,offense_snaps,defense_snaps,st_snaps\n" + "".join(
                f"{gid},{gt},{pfr},{o},{dd},{st}\n" for _y, gid, gt, pfr, o, dd, st in rows), encoding="utf-8")
        return hd.Nflverse(d)

    def test_games_use_snaps_and_the_larger_count_wins(self):
        snaps = [(2025, f"2025_{w:02d}_A_B", "REG", "ThomAn02", 60, 0, 0) for w in range(1, 14)]        # 13 games
        snaps += [(2025, "2025_01_A_B", "REG", "ThomAn02", 60, 0, 0)]                                     # duplicate row, same game
        snaps += [(2025, "2025_18_A_B", "POST", "ThomAn02", 60, 0, 0), (2025, "2025_19_A_B", "REG", "ThomAn02", 0, 0, 0)]  # not counted
        snaps += [(2025, f"2025_{w:02d}_A_B", "REG", "SnapLo00", 0, 0, 12) for w in range(1, 9)]          # a long snapper: special teams only
        with tempfile.TemporaryDirectory() as tmp:
            data = self.make_dir(tmp, snaps, [(2025, "00-1", 3, "NYG")], [(2025, "NYG", "00-1", 18, 2020), (2025, "NYG", "00-2", 18, 2020)])
            self.assertEqual(data.games("00-1", 2025, 3), (13, "snap_counts"))
            self.assertEqual(data.games("00-2", 2025, 0), (8, "snap_counts"))
            self.assertEqual(data.games("00-1", 2025, 17), (17, "stat_line_games"))          # the stat line count is never lowered
            self.assertEqual(data.games("00-1", 2012, 4), (4, "stat_line_games_lower_bound"))  # no snap data before 2013
            seasons, notes = data.seasons("00-2", 2020)
            self.assertEqual([(s["year"], s["stats"]["games"], s["team"]) for s in seasons], [(2025, 8, "NYG")])
            self.assertEqual(notes["season_from_snaps_only"], 1)

    def test_league_history_games_are_raised_and_snap_only_seasons_added(self):
        snaps = [(2025, f"g{w}", "REG", "ThomAn02", 60, 0, 0) for w in range(1, 14)]
        snaps += [(2024, f"h{w}", "REG", "ThomAn02", 60, 0, 0) for w in range(1, 7)]
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self.make_dir(tmp, snaps, [(2025, "00-1", 3, "NYG")], [(2025, "NYG", "00-1", 18, 2020), (2024, "NYG", "00-1", 18, 2020)])
            edits = {"franchise_history": {"sources": {"roster_2025.csv": {"sha256": "0" * 64}}, "players": [
                {"gsis_id": "00-1", "first": "Andrew", "last": "Thomas", "seasons": [
                    {"year": 2025, "source": "stats_player_reg_2025.csv", "stats": {"games": 3}, "team_index": 15}]}]}}
            out, report = hd.patch_league(data_dir, edits)
        seasons = out["franchise_history"]["players"][0]["seasons"]
        self.assertEqual([(s["year"], s["stats"]["games"]) for s in seasons], [(2024, 6), (2025, 13)])
        self.assertEqual(seasons[0]["source"], "snap_counts_2024.csv")
        self.assertEqual(seasons[0]["team_index"], 15)                                       # NYG, from the annual roster
        self.assertEqual((report["games_raised"], report["seasons_added"]), (1, 1))
        self.assertIn("snap_counts_2025.csv", out["franchise_history"]["sources"])
        self.assertIn("players.csv", out["franchise_history"]["sources"])
        self.assertEqual(edits["franchise_history"]["players"][0]["seasons"][0]["stats"]["games"], 3)  # input not mutated

    def test_shipped_created_history_uses_snap_games(self):
        kaep = person("Colin Kaepernick")
        games = {s["year"]: s["stats"]["games"] for s in kaep["seasons"]}
        self.assertEqual(games[2016], 12)         # 11 weeks with a stat line, 12 games played
        self.assertEqual(games[2012], 13)         # before 2013 the stat-line count is kept (a lower bound)
        self.assertIn("games = the larger", HISTORY["policy"])


if __name__ == "__main__":
    unittest.main()
