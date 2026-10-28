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
        self.assertEqual(receipt["folded_players"], 0)
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
            for depth in ch.FOLD_DEPTHS:
                self.assertEqual(ch.fold_words(words, p["years_pro"], depth), upgrade.fold_words(words, p["years_pro"], depth))

    def test_a_short_pool_folds_the_least_important_players_first_and_keeps_career_totals(self):
        names = ["Colin Kaepernick"] + [f"{p['first']} {p['last']}" for p in HISTORY["players"] if len(p["seasons"]) >= 6][:3]
        players = [person(n) for n in names]
        spec = copy.deepcopy(HISTORY)
        spec["players"] = players
        full = sum(len(ch.season_words(p, p["years_pro"], 2026)) for p in players)
        body = body_for(players)
        saved = ch.HISTORY_RESERVE
        try:
            doc = cs.decode_body(body)
            ch.HISTORY_RESERVE = doc.pool_capacity - doc.pool_used - (full - 12)       # 12 dwords too few
            out, receipt = ch.apply_body(body, spec)
        finally:
            ch.HISTORY_RESERVE = saved
        self.assertGreaterEqual(receipt["folded_players"], 1)
        self.assertLessEqual(receipt["words_written"], full - 12)
        doc = cs.decode_body(out)
        # the most important player (first in the data) keeps every season and its TEAM word
        rows = words_by_year(doc, ("primary", 0), 16)
        self.assertEqual(sorted(rows), list(range(2011, 2017)))
        # the folded player's passing yards still add up to his sourced career
        last = players[-1]
        index = len(players) - 1
        total = sum(s["stats"].get("games", 0) for s in last["seasons"])
        got = sum(cs.Word(w).raw & 0xFFFF for w in doc.history_words["primary", index] if cs.Word(w).field == 0)
        self.assertEqual(got, total)


if __name__ == "__main__":
    unittest.main()
