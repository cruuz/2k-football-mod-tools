"""Beta 77 job f12: the game's years pro (rookie = 1) against nflverse years_exp (rookie = 0).

Offline tests: the conversion helpers, the 2026 roster generator's write, the validation card, the rookie filter,
the history-slot guard, the data converter and its stamps, and the native repair on synthetic ROST bodies.  Tests that
need the real v0.5 disc (the repair's hashes, the Unicorn rollover and Player Card text) skip when it is absent.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_career_stats as cs  # noqa: E402
from mod_editor.core import nfl2k5_franchise_history as fh  # noqa: E402
from mod_editor.core import nfl2k5_free_agents as fa  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_save_rost as sr  # noqa: E402
from tests.mod_editor.test_nfl2k5_roster_records import ONE_POOL_SAMPLE, PLAYERS_OFF, synthetic_body as roster_body  # noqa: E402
from tests.mod_editor.test_nfl2k5_team_history import D, entry, games, synthetic_body  # noqa: E402
from tools.b77 import f12_anniversary_repair as anniversary  # noqa: E402
from tools.b77 import f12_convert_data as convert  # noqa: E402
from tools.b77 import f12_repair as repair  # noqa: E402
import nfl2k5_team_2026_roster as league  # noqa: E402

V05_ISO = Path(os.environ.get("NFL2K5_V05_ISO", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso"))
PLAYERS_CSV = Path(os.environ.get("NFL2K5_PLAYERS_CSV", "/media/noah/Storage/.b76-research/u1/refs/nflverse/players.csv"))
SPARSE_TEAMS = ("vikings_1998", "falcons_1998", "titans_1999", "bills_1999", "patriots_2001", "raiders_2001")
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None


def v05_files(names=("default.xbe", "vc_53450030/0")):
    """Named files of the v0.5 disc, read-only from the image (None when it is absent)."""
    if not V05_ISO.is_file():
        return None
    from tools import nfl_uniform_color_xiso_direct_patch as xiso
    fd = os.open(V05_ISO, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(fd).st_size
        entries, _ = xiso.parse_xdvdfs(fd, size)
        out = {}
        for name in names:
            found = xiso.file_extent(fd, size, name, entries=entries)
            out[name] = xiso.read_exact(fd, found.byte_offset, found.size)
        return out
    finally:
        os.close(fd)


class ConventionTests(unittest.TestCase):
    def test_the_game_counts_the_season_in_progress(self) -> None:
        self.assertEqual(rr.ROOKIE_YEARS_PRO, 1)
        # nflverse 2026 roster: a 2026 draftee has years_exp 0, a 2025 draftee 1, a 2017 draftee 9
        self.assertEqual([rr.years_pro_from_years_exp(x) for x in ("0", "1", "9", 21)], [1, 2, 10, 22])
        self.assertEqual([rr.years_pro_for_season(2026, y) for y in (2026, 2025, 2017)], [1, 2, 10])
        self.assertEqual(rr.years_pro_for_season(2004, 2004), 1)      # retail: Fitzgerald, Eli Manning, Rivers
        self.assertEqual(rr.years_pro_for_season(2004, 2000), 5)      # retail: Tom Brady
        self.assertEqual(rr.years_pro_for_season(2004, 1991), 14)     # retail: Brett Favre
        self.assertEqual([rr.accrued_seasons(x) for x in (0, 1, 2, 10)], [0, 0, 1, 9])
        self.assertEqual([rr.years_pro_label(x) for x in (0, 1, 2, 13)], ["0", "R", "2", "13"])
        self.assertEqual([rr.is_rookie_years_pro(x) for x in (0, 1, 2)], [True, True, False])

    def test_empty_saturating_and_invalid_experience(self) -> None:
        self.assertEqual(rr.years_pro_from_years_exp(99), rr.YEARS_PRO_MAX)
        for bad in ("", "  ", None, "NA", -1, "abc"):          # unknown is not a rookie (nflverse 1998 to 2001 rosters)
            with self.assertRaises(rr.RosterRecordError):
                rr.years_pro_from_years_exp(bad)
        with self.assertRaises(rr.RosterRecordError):
            rr.years_pro_for_season(2026, 2027)

    def test_the_league_generator_writes_the_game_convention(self) -> None:
        self.assertEqual([league.written_years_pro({"years_exp": x}) for x in ("0", "1", "9", "21")], [1, 2, 10, 22])
        with self.assertRaises(rr.RosterRecordError):
            league.written_years_pro({"years_exp": ""})

    def test_the_field_documents_the_convention(self) -> None:
        note = rr.FIELD_BY_NAME["years_pro"].note
        self.assertIn("1 = rookie", note)
        self.assertIn("R", note)


class RosterEditorRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = rr.RosterDocument(roster_body(), reference_year=2004)

    def test_rookie_filter_follows_the_games_own_predicate(self) -> None:
        for player in self.document.players:
            player.record.values["years_pro"] = {0: 0, 1: 1}.get(player.index, 2 + player.index % 5)
        preview = rr.global_edit_preview(self.document, attribute="speed", mode="add", value=1, rookies_only=True)
        picked = {row["index"] for row in preview}
        self.assertTrue(picked <= {p.index for p in self.document.players if p.record.values["years_pro"] <= 1})
        everyone = rr.global_edit_preview(self.document, attribute="speed", mode="add", value=1)
        self.assertLess(len(picked), len(everyone))
        self.assertIn(1, picked)                      # stored 1 is a rookie (it prints R)
        self.assertNotIn(2, picked)                   # stored 2 is a second-year player

    def test_zero_years_pro_on_a_club_or_free_agent_is_flagged(self) -> None:
        club = next(p for p in self.document.players if p.teams and p.record.values["player_type"] & rr.FLAG_NFL_PLAYER)
        club.record.values["years_pro"] = 0
        flagged = [f for f in rr.validate(self.document, [club]) if f["check"] == "years pro"]
        self.assertEqual(len(flagged), 1)
        self.assertIn("rookie is 1", flagged[0]["detail"])
        club.record.values["years_pro"] = 1
        self.assertFalse([f for f in rr.validate(self.document, [club]) if f["check"] == "years pro"])

    def test_advance_years_pro_is_the_games_rollover_step(self) -> None:
        player = self.document.players[0]
        player.record.values["years_pro"] = 1
        rr.advance_years_pro(self.document, [player])
        self.assertEqual(rr.years_pro_label(player.record.values["years_pro"]), "2")


class HistorySlotTests(unittest.TestCase):
    """A player's k-th pro season is slot k: a roster written in the nflverse convention is refused, not shifted."""

    @staticmethod
    def spec(seasons, birth="1976-03-24"):
        return dict(schema=fh.SCHEMA, base_year=2026,
                    sources={"test": dict(sha256=hashlib.sha256(b"x").hexdigest(), updated_at="2026-10-07", url="synthetic:test")},
                    players=[dict(pool="primary", index=0, first="Test", last="Player", birth_date=birth, gsis_id="t-1",
                                  identity_source="test", seasons=seasons)])

    def body(self, count):
        players = [{"first": "Test", "last": "Player", "birth": D(1976, 3, 24), "position": 0, "count": count,
                    "stream": games([1])}]
        body = bytearray(synthetic_body(players))
        struct.pack_into("<i", body, 0x14, 0x2D)
        return bytes(body)

    def test_rookie_year_is_slot_one_and_the_old_convention_is_refused(self) -> None:
        season = [dict(year=2025, source="test", stats={"games": 12})]
        # game convention: a 2025 draftee in 2026 stores 2; his rookie season (2025) is slot 1
        out, _ = fh.apply_body(self.body(2), self.spec(season))
        self.assertEqual([cs.Word(w).slot for w in sr.decode(out, preamble=0, reference_year=2026).history_words["primary", 0]], [1])
        # nflverse convention: the same player stores 1, so 2025 would be slot 0 -> refused with the reason
        with self.assertRaises(cs.CareerStatsError) as raised:
            fh.apply_body(self.body(1), self.spec(season))
        self.assertIn("years_pro_from_years_exp", str(raised.exception))

    def test_a_veteran_keeps_every_season(self) -> None:
        seasons = [dict(year=y, source="test", stats={"games": 16}) for y in range(2017, 2026)]
        out, _ = fh.apply_body(self.body(10), self.spec(seasons))       # entered 2017: 10th season in 2026
        slots = sorted({cs.Word(w).slot for w in sr.decode(out, preamble=0, reference_year=2026).history_words["primary", 0]})
        self.assertEqual(slots, list(range(1, 10)))


class DataConversionTests(unittest.TestCase):
    def test_frozen_edits_conversion_does_not_rerun_current_free_agent_generator(self) -> None:
        base = roster_body()
        doc = {"schema": rr.EDITS_SCHEMA, "name": "frozen league", "edits": [
            {"pool": "primary", "index": 0, "first": "Peyton", "last": "Manning",
             "names": {"first": "Cam", "last": "Ward"}, "fields": {"years_pro": 0}}],
            "modern_free_agents": "2026-10-05", "restore_historic_spare_capacity": True}
        with patch.object(fa, "apply_body", side_effect=AssertionError("current generator is already converted")):
            converted, report = convert.convert_edits(doc, base)
        self.assertEqual(report["authored_players"], 1)
        self.assertEqual(converted["edits"][0]["fields"]["years_pro"], 1)
        self.assertEqual(converted["modern_free_agents"], "2026-10-05")
        self.assertTrue(converted["restore_historic_spare_capacity"])
        self.assertEqual(doc["edits"][0]["fields"]["years_pro"], 0)

    def test_shipped_free_agent_data_is_stamped_and_exactly_plus_one(self) -> None:
        data = fa.load_data()
        self.assertEqual(data["years_pro_convention"], "game_rookie_1")
        old = copy.deepcopy(data)
        for key in ("years_pro_convention", "years_pro_convention_note"):
            old.pop(key)
        for row in old["added"]:
            row["fields"]["years_pro"] -= 1
        again, report = convert.convert_free_agents(old)
        self.assertEqual(again, data)
        self.assertEqual(report["added_rows_converted"], 140)
        with self.assertRaises(convert.ConversionRefused):
            convert.convert_free_agents(data)

    def test_unstamped_free_agent_data_is_refused_by_the_loader(self) -> None:
        data = json.loads(fa.DEFAULT_DATA.read_text(encoding="utf-8"))
        data.pop("years_pro_convention")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fa.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                fa.load_data(path)
        self.assertIn("rookie = 1", str(raised.exception))

    def test_edits_document_converts_once_and_reaches_players_a_sparse_document_leaves_at_the_base_value(self) -> None:
        base = roster_body()
        base_doc = rr.RosterDocument(base, reference_year=2004)
        years = {p.index: p.record.values["years_pro"] for p in base_doc.players}
        # a sparse league document: player 0 is rewritten as a rookie (an explicit years_pro), player 2 as a veteran whose
        # years_pro equals the base slot's, so the document carries no years_pro for him at all
        doc = {"schema": rr.EDITS_SCHEMA, "name": "synthetic league", "edits": [
            {"pool": "primary", "index": 0, "first": "Peyton", "last": "Manning", "names": {"first": "Cam", "last": "Ward"},
             "fields": {"years_pro": 0}},
            {"pool": "primary", "index": 2, "first": "Edgerrin", "last": "James", "names": {"first": "Jax", "last": "Dart"},
             "fields": {"jersey": 9, "years_pro": years[2]}}]}
        doc["edits"][1]["fields"].pop("years_pro")                              # sparse: equal to the base, so absent
        old_body, _ = rr.apply_body(base, doc)
        old = rr.RosterDocument(old_body, reference_year=2004)
        self.assertEqual((old.players[0].record.values["years_pro"], old.players[2].record.values["years_pro"]), (0, years[2]))
        out, report = convert.convert_edits(doc, base)
        self.assertEqual(report, {"authored_players": 2, "entries_updated": 1, "entries_appended": 1})
        new_body, _ = rr.apply_body(base, out)
        new = rr.RosterDocument(new_body, reference_year=2004)
        self.assertEqual((new.players[0].record.values["years_pro"], new.players[2].record.values["years_pro"]), (1, years[2] + 1))
        for index in (1, 3, 4, 5, 6, 7):
            self.assertEqual(new.players[index].record.values, old.players[index].record.values, "an unauthored player is untouched")
        self.assertEqual(out["edits"][-1]["fields"], {"years_pro": years[2] + 1}, "the appended entry names the final name")
        self.assertEqual((out["edits"][-1]["first"], out["edits"][-1]["last"]), ("Jax", "Dart"))
        self.assertEqual(doc["edits"][0]["fields"]["years_pro"], 0, "the source document is not mutated")
        with self.assertRaises(convert.ConversionRefused):
            convert.convert_edits(out, base)
        rr.read_edits(out)                                   # the stamp does not break the reader

    def test_anniversary_team_data_is_stamped_and_pinned(self) -> None:
        teams = ROOT / "data/nfl2k5_espn25_more_teams"
        manifest = json.loads((teams / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["years_pro_convention"], "game_rookie_1")
        import csv
        for key, entry_ in manifest["teams"].items():
            raw = (teams / f"{key}.csv").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry_["csv_sha256"], key)
            years = [int(r["years_pro"]) for r in csv.DictReader((teams / f"{key}.csv").open(encoding="utf-8", newline=""))]
            self.assertEqual(len(years), 53, key)
            self.assertEqual(sum(1 for y in years if y == 0), 0, f"{key}: nobody prints 0")
            rookies = sum(1 for y in years if y == 1)
            self.assertTrue(1 <= rookies <= 20, f"{key}: a roster has a handful of rookies, not {rookies}")
        # the 2025 Bengals: Flacco entered in 2008, so 2025 is his 18th season; the 2025 rookies store 1
        rows = list(csv.DictReader((teams / "bengals_2025.csv").open(encoding="utf-8", newline="")))
        flacco = next(r for r in rows if (r["first"], r["last"]) == ("Joe", "Flacco"))
        self.assertEqual(int(flacco["years_pro"]), 18)
        self.assertGreater(sum(1 for r in rows if int(r["years_pro"]) == 1), 0)
        unc = json.loads((ROOT / "data/nfl2k5_espn25_unc_bowl.json").read_text(encoding="utf-8"))
        for key in ("bengals_2025", "steelers_2025"):
            self.assertEqual(unc["teams"][key]["csv_sha256"], manifest["teams"][key]["csv_sha256"])

    def test_the_six_sparse_team_seasons_use_entry_years_and_say_so(self) -> None:
        """nflverse's 1998, 1999 and 2001 roster files have no years_exp: those six rosters must not print R for everybody."""
        import csv
        teams = ROOT / "data/nfl2k5_espn25_more_teams"
        manifest = json.loads((teams / "manifest.json").read_text(encoding="utf-8"))
        flagged = {key: sum(1 for p in t["players"] if "years_pro_basis" in p) for key, t in manifest["teams"].items()}
        self.assertEqual({k for k, v in flagged.items() if v}, set(SPARSE_TEAMS))
        self.assertEqual(sum(flagged.values()), 313)
        for key, t in manifest["teams"].items():
            for p in t["players"]:
                if "years_pro_basis" in p:
                    self.assertIn("players.csv", p["years_pro_basis"])
        known = {"vikings_1998": {("Randy", "Moss"): 1, ("Randall", "Cunningham"): 14, ("Cris", "Carter"): 12},
                 "patriots_2001": {("Tom", "Brady"): 2, ("Richard", "Seymour"): 1, ("Drew", "Bledsoe"): 9},
                 "falcons_1998": {("Steve", "DeBerg"): 22, ("Tim", "Dwight"): 1},
                 "raiders_2001": {("Rich", "Gannon"): 15, ("Jerry", "Rice"): 17}}
        for key, want in known.items():
            rows = {(r["first"], r["last"]): int(r["years_pro"])
                    for r in csv.DictReader((teams / f"{key}.csv").open(encoding="utf-8", newline=""))}
            for name, years in want.items():
                self.assertEqual(rows[name], years, f"{key} {name}")

    @unittest.skipUnless(PLAYERS_CSV.is_file(), "nflverse players.csv is not on this machine")
    def test_the_entry_year_fallback_reproduces_the_roster_values_it_stands_in_for(self) -> None:
        import csv
        import nfl2k5_espn25_more_moments_build as build
        teams = ROOT / "data/nfl2k5_espn25_more_teams"
        manifest = json.loads((teams / "manifest.json").read_text(encoding="utf-8"))
        if hashlib.sha256(PLAYERS_CSV.read_bytes()).hexdigest() != manifest["sources"]["nflverse"]["files"]["players.csv"]:
            self.skipTest("players.csv is not the file the data was built from")
        people = list(csv.DictReader(PLAYERS_CSV.open(encoding="utf-8", newline="")))
        by_id = {r["gsis_id"]: r for r in people}
        entry_years = build.players_entry_years(people)
        exact = drafted = misses = undrafted_misses = total = 0
        for key, t in manifest["teams"].items():
            rows = list(csv.DictReader((teams / f"{key}.csv").open(encoding="utf-8", newline="")))
            for index, row in enumerate(rows):
                player = t["players"][index]
                guess, basis = build.years_pro_for({"gsis_id": player["gsis_id"], "years_exp": ""}, t["season"], entry_years)
                self.assertEqual(basis, build.PLAYERS_YEARS_BASIS)
                if key in SPARSE_TEAMS:
                    if "years_pro_basis" in player:         # the shipped value is the fallback
                        self.assertEqual(int(row["years_pro"]), guess, f"{key} {row['first']} {row['last']}")
                    continue                                # (five players there came with their own years_exp)
                total += 1
                is_drafted = bool((by_id[player["gsis_id"]]["draft_year"] or "").strip())
                drafted += is_drafted
                if int(row["years_pro"]) == guess:
                    exact += 1
                else:
                    misses += 1
                    undrafted_misses += not is_drafted
                    self.assertLess(guess, int(row["years_pro"]), "the fallback can only undercount")
        # the figures quoted in years_pro_for's docstring and in reports/f12_REPORT.md
        self.assertEqual((total, drafted, exact, misses), (2332, 1683, 2278, 54))
        self.assertEqual(misses, undrafted_misses, "every miss is an undrafted player")

    def test_the_pins_carry_the_shipped_csv_and_an_old_value_that_differs(self) -> None:
        import csv
        pins = anniversary.load_pins()
        self.assertEqual(len(pins["teams"]), 50)
        for key, team in pins["teams"].items():
            rows = {(r["first"], r["last"]): int(r["years_pro"]) for r in
                    csv.DictReader((ROOT / "data/nfl2k5_espn25_more_teams" / f"{key}.csv").open(encoding="utf-8", newline=""))}
            self.assertEqual({(f, l): new for f, l, _old, new in team["players"]}, rows, key)
            if key not in SPARSE_TEAMS:
                self.assertEqual({new - old for _f, _l, old, new in team["players"]}, {1}, key)
            else:
                self.assertGreaterEqual(sum(1 for _f, _l, old, _new in team["players"] if old == 0), 40, key)


# ------------------------------------------------------------------------------------------------ native repair
def cohort_for(players, state_old=True):
    rows = {}
    for index, p in enumerate(players):
        if p.get("cohort"):
            rows[index] = (p["first"], p["last"], p["birth"].isoformat(), p["count"] if state_old else p["count"] - 1, "26n")
    return {"_rows": rows, "_file_sha256": "0" * 64, "counts": {"basis": {"26n": len(rows)}, "club": 0, "free_agent": 0}}


class RepairOnSyntheticRosterTests(unittest.TestCase):
    """The writer on a ROST body built to the v0.5 shape: old-convention years pro and zero-based history slots."""

    def players(self):
        return [
            {"first": "Cam", "last": "Rookie25", "birth": D(2002, 5, 25), "position": 0, "count": 1, "stream": games([0]), "cohort": True},
            {"first": "Jere", "last": "Rookie26", "birth": D(2005, 5, 31), "position": 7, "count": 0, "stream": None, "cohort": True},
            {"first": "Pat", "last": "Veteran", "birth": D(1995, 9, 17), "position": 0, "count": 9,
             "stream": games(list(range(0, 9)), extra=(entry(8, 87, 14),)), "cohort": True},
            {"first": "Old", "last": "Legend", "birth": D(1962, 10, 13), "position": 3, "count": 20, "stream": games(list(range(1, 20)))},
        ]

    def make(self):
        players = self.players()
        return players, bytes(self.fix(synthetic_body(players)))

    @staticmethod
    def fix(body):
        body = bytearray(body)
        struct.pack_into("<i", body, 0x14, 0x2D)
        return body

    def test_years_pro_and_slots_move_together_and_nothing_else_does(self) -> None:
        players, body = self.make()
        out, receipt = repair.repair_body(body, cohort=cohort_for(players), approved_input_sha256=(repair.sha(body),))
        self.assertEqual(receipt["state"], "applied")
        before, after = sr.decode(body, preamble=0, reference_year=2026), sr.decode(out, preamble=0, reference_year=2026)
        for index, (old, new) in enumerate([(1, 2), (0, 1), (9, 10), (20, 20)]):
            self.assertEqual(before.by_key["primary", index].record.values["years_pro"], old)
            self.assertEqual(after.by_key["primary", index].record.values["years_pro"], new)
        self.assertEqual(sorted({cs.Word(w).slot for w in after.history_words["primary", 0]}), [1])
        self.assertEqual(sorted({cs.Word(w).slot for w in after.history_words["primary", 2]}), list(range(1, 10)))
        team = [w for w in after.history_words["primary", 2] if cs.Word(w).field == 87]
        self.assertEqual([(cs.Word(w).slot, w & 0xFFFF) for w in team], [(9, 14)], "the TEAM word moves with its season")
        self.assertEqual(before.history_words["primary", 3], after.history_words["primary", 3], "a non-cohort stream is untouched")
        # a scope proof: only +0x25 bits 0-4 of cohort records and slot bits of cohort words differ
        diff = [i for i, (a, b) in enumerate(zip(body, out)) if a != b]
        starts = {p.offset + 0x25 for p in before.players[:3]}
        words = {before.history_offsets["primary", i] + 4 * k + j for i in (0, 2)
                 for k in range(len(before.history_words["primary", i])) for j in (2, 3)}
        self.assertTrue(set(diff) <= starts | words)
        self.assertTrue(receipt["scope"]["outside_scope_identical"])
        self.assertEqual(receipt["scope"]["changed_bytes"], len(diff))

    def test_replay_is_a_no_op_and_a_half_repaired_cohort_is_refused(self) -> None:
        players, body = self.make()
        out, _ = repair.repair_body(body, cohort=cohort_for(players), approved_input_sha256=(repair.sha(body),))
        again, receipt = repair.repair_body(out, cohort=cohort_for(players), approved_input_sha256=(repair.sha(out),))
        self.assertEqual((again, receipt["state"]), (out, "already_applied"))
        half = bytearray(body)
        half[sr.decode(body, preamble=0, reference_year=2026).by_key["primary", 0].offset + 0x25] += 1
        with self.assertRaises(repair.RepairRefused):
            repair.repair_body(bytes(half), cohort=cohort_for(players), approved_input_sha256=(repair.sha(bytes(half)),))

    def test_pins_hashes_and_shared_streams_are_enforced(self) -> None:
        players, body = self.make()
        with self.assertRaises(repair.RepairRefused):                      # unknown input hash without approval
            repair.repair_body(body, cohort=cohort_for(players))
        wrong = cohort_for(players)
        wrong["_rows"][0] = ("Cam", "Someone", "2002-05-25", 1, "26n")
        with self.assertRaises(repair.RepairRefused):
            repair.repair_body(body, cohort=wrong, approved_input_sha256=(repair.sha(body),))
        stale = cohort_for(players)
        stale["_rows"][2] = ("Pat", "Veteran", "1995-09-17", 5, "26n")     # pinned years pro disagrees with the roster
        with self.assertRaises(repair.RepairRefused):
            repair.repair_body(body, cohort=stale, approved_input_sha256=(repair.sha(body),))
        # a cohort stream that a non-cohort player also points at
        decoded = sr.decode(body, preamble=0, reference_year=2026)
        shared = bytearray(body)
        ptr = decoded.by_key["primary", 3].offset + 0x2C
        target = decoded.history_offsets["primary", 2]
        struct.pack_into("<i", shared, ptr, target - ptr + 1)
        with self.assertRaises(repair.RepairRefused):
            repair.repair_body(bytes(shared), cohort=cohort_for(players), approved_input_sha256=(repair.sha(bytes(shared)),))

    def test_history_at_or_after_the_current_season_is_refused(self) -> None:
        players = self.players()
        players[0]["stream"] = games([0, 1])                                # slot 1 == current season of a rookie (1)
        body = bytes(self.fix(synthetic_body(players)))
        with self.assertRaises(repair.RepairRefused):
            repair.repair_body(body, cohort=cohort_for(players), approved_input_sha256=(repair.sha(body),))


class RepairOnTheV05DiscTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = v05_files()
        if cls.files is None:
            raise unittest.SkipTest("the v0.5 disc image is not on this machine")
        if hashlib.sha256(cls.files["vc_53450030/0"]).hexdigest() != repair.V05_PACK0_SHA256:
            raise unittest.SkipTest("pack 0 is not the v0.5 pack")
        cls.cohort = repair.load_cohort()
        cls.repaired, cls.receipt = repair.repair_pack0(cls.files["vc_53450030/0"], cohort=cls.cohort)

    def test_hashes_scope_and_idempotence(self) -> None:
        self.assertEqual(hashlib.sha256(self.repaired).hexdigest(), repair.F12_PACK0_SHA256)
        self.assertEqual(self.receipt["after_rost_body_sha256"], repair.F12_ROST_BODY_SHA256)
        self.assertEqual(self.receipt["cohort"]["records"], 2072)
        self.assertEqual((self.receipt["history"]["words"], self.receipt["scope"]["changed_bytes"]), (32989, 49876))
        self.assertTrue(self.receipt["outside_roster_identical"] and self.receipt["scope"]["outside_scope_identical"])
        again, receipt = repair.repair_pack0(self.repaired, cohort=self.cohort)
        self.assertEqual((again == self.repaired, receipt["state"]), (True, "already_applied"))

    def test_the_cohort_is_every_2026_built_record_and_only_those(self) -> None:
        offset, size = repair.locate_rost(self.files["vc_53450030/0"])
        before = rr.RosterDocument(self.files["vc_53450030/0"][offset + 0x20:offset + size], base=0, scheme="one_pool", reference_year=2026)
        pinned = set(self.cohort["_rows"])
        for p in before.players:
            if p.pool != "primary":
                continue
            club = any(t < 32 for t in p.teams)
            if club or p.offset in set(before.free_agents):
                self.assertIn(p.index, pinned, f"{p.display} is on a club or the free-agent list but not pinned")
        self.assertEqual(len(pinned), 2072)
        self.assertEqual(self.cohort["counts"]["club"] + self.cohort["counts"]["free_agent"] + 2, 2072)
        after = rr.RosterDocument(self.repaired[offset + 0x20:offset + size], base=0, scheme="one_pool", reference_year=2026)
        rookies = [p for p in after.players if p.pool == "primary" and p.index in pinned and p.record.values["years_pro"] == 1]
        self.assertEqual(len(rookies), 264)
        self.assertFalse([p for p in after.players if p.index in pinned and p.record.values["years_pro"] == 0])
        # every 2026 draftee in the first round is a rookie, every 2025 one is in his second year
        by = {(p.first, p.last, p.record.birth_date.isoformat()): p.record.values["years_pro"]
              for p in after.players if p.pool == "primary" and p.index in pinned}
        for name in (("Fernando", "Mendoza", "2003-10-01"), ("Jeremiyah", "Love", "2005-05-31"), ("David", "Bailey", "2003-08-28")):
            self.assertEqual(by[name], 1, name)
        for name in (("Cam", "Ward", "2002-05-25"), ("Travis", "Hunter", "2003-05-18"), ("Ashton", "Jeanty", "2003-12-02")):
            self.assertEqual(by[name], 2, name)
        self.assertEqual(by[("Patrick", "Mahomes", "1995-09-17")], 10)


class AnniversaryRepairSyntheticTests(unittest.TestCase):
    """The pack E/F writer on two synthetic one-team resources in the real outer-archive layout."""

    BLOCK = 0x800

    @staticmethod
    def team(prefix: str, years):
        rows = [(f"{prefix}F{i:02d}", f"{prefix}L{i:02d}", i % 17, 1 + i, years[i], 200, 72, D(1990, 1, 1), 0, 70, 0)
                for i in range(53)]
        body = roster_body(rows)
        return b"ROST" + struct.pack("<II", len(body), len(body)) + bytes(0x14) + body, rows

    def build(self, years_a, years_b, new_a=None, new_b=None):
        res_a, rows_a = self.team("A", years_a)
        res_b, rows_b = self.team("B", years_b)
        new_a = new_a or [y + 1 for y in years_a]
        new_b = new_b or [y + 1 for y in years_b]
        blocks_e = 1 + -(-len(res_a) // self.BLOCK)
        blocks_f = -(-len(res_b) // self.BLOCK)
        pack_e = bytearray(blocks_e * self.BLOCK)
        pack_e[self.BLOCK:self.BLOCK + len(res_a)] = res_a
        pack_f = bytearray(blocks_f * self.BLOCK)
        pack_f[:len(res_b)] = res_b
        head = bytearray(anniversary.HEADER_SIZE + 12 * 6)          # six directory rows, four of them empty
        struct.pack_into("<3I", head, 0, 6, 0, 16)
        blocks = [1] * 14 + [blocks_e, blocks_f]
        struct.pack_into("<16I", head, 12, *blocks)
        struct.pack_into("<3I", head, anniversary.HEADER_SIZE, 1, len(res_a), 15)
        struct.pack_into("<3I", head, anniversary.HEADER_SIZE + 12, 2, len(res_b), 14 + blocks_e)
        pins = {"_file_sha256": "0" * 64, "schema": anniversary.PINS_SCHEMA, "teams": {
            "a": {"players": [[r[0], r[1], r[4], new_a[i]] for i, r in enumerate(rows_a)]},
            "b": {"players": [[r[0], r[1], r[4], new_b[i]] for i, r in enumerate(rows_b)]}}}
        return bytes(head), {14: bytes(pack_e), 15: bytes(pack_f)}, pins

    def run_repair(self, head, packs, pins):
        approved = tuple(hashlib.sha256(p).hexdigest() for p in packs.values())
        from unittest import mock
        with mock.patch.object(anniversary, "TEAM_SIZE_LIMIT", 10**6):
            return anniversary.repair_packs(head, packs, pins, approved)

    def test_every_record_gains_one_year_and_nothing_else_changes(self) -> None:
        years_a = [0, 1, 2, 3] + [5] * 49
        years_b = [1] + [0] * 3 + [7] * 49
        head, packs, pins = self.build(years_a, years_b)
        out, receipt = self.run_repair(head, packs, pins)
        self.assertEqual((receipt["state"], receipt["teams"], receipt["records"]), ("applied", 2, 106))
        self.assertEqual([receipt["packs"][k]["changed_bytes"] for k in "EF"], [53, 53])
        for ordinal, base, years in ((14, self.BLOCK, years_a), (15, 0, years_b)):
            before, after = packs[ordinal], out[ordinal]
            self.assertEqual(len(before), len(after))
            expected = {base + anniversary.RESOURCE_HEADER_SIZE + PLAYERS_OFF + i * rr.PLAYER_SIZE + 0x25 for i in range(53)}
            self.assertEqual({i for i, (a, b) in enumerate(zip(before, after)) if a != b}, expected)
            for i, at in enumerate(sorted(expected)):
                self.assertEqual((before[at], after[at]), (years[i], years[i] + 1))
        again, receipt2 = self.run_repair(head, out, pins)
        self.assertEqual((receipt2["state"], again), ("already_applied", out))

    def test_each_record_gets_its_own_pinned_value(self) -> None:
        """The six sparse team-seasons were all missing-data zeros: the pinned new value is the entry-year one, not old + 1."""
        years_a = [0] * 53
        new_a = [1 + (i * 7) % 22 for i in range(53)]
        head, packs, pins = self.build(years_a, [4] * 53, new_a=new_a)
        out, receipt = self.run_repair(head, packs, pins)
        base = self.BLOCK + anniversary.RESOURCE_HEADER_SIZE + PLAYERS_OFF
        self.assertEqual([out[14][base + i * rr.PLAYER_SIZE + 0x25] & 0x1F for i in range(53)], new_a)
        self.assertEqual(receipt["packs"]["E"]["changed_bytes"], sum(1 for v in new_a if v != 0))
        again, receipt2 = self.run_repair(head, out, pins)
        self.assertEqual((receipt2["state"], again), ("already_applied", out))
        stuck = copy.deepcopy(pins)
        stuck["teams"]["a"]["players"][3][3] = stuck["teams"]["a"]["players"][3][2]     # a pin that changes nothing
        with self.assertRaises(anniversary.RepairRefused):
            self.run_repair(head, packs, stuck)

    def test_half_repaired_unknown_and_unapproved_input_is_refused(self) -> None:
        head, packs, pins = self.build([2] * 53, [3] * 53)
        out, _ = self.run_repair(head, packs, pins)
        mixed = {14: out[14], 15: packs[15]}                    # one team repaired, the other not
        with self.assertRaises(anniversary.RepairRefused):
            self.run_repair(head, mixed, pins)
        wrong = copy.deepcopy(pins)
        wrong["teams"]["a"]["players"][0][2] += 5
        with self.assertRaises(anniversary.RepairRefused):
            self.run_repair(head, packs, wrong)
        from unittest import mock
        with mock.patch.object(anniversary, "TEAM_SIZE_LIMIT", 10**6), self.assertRaises(anniversary.RepairRefused):
            anniversary.repair_packs(head, packs, pins)         # unknown hashes, no approval
        with self.assertRaises(anniversary.RepairRefused):
            self.run_repair(head, {14: packs[14]}, pins)        # both packs are required


class AnniversaryOnTheV05DiscTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        files = v05_files(("vc_53450030/0", "vc_53450030/e", "vc_53450030/f"))
        if files is None:
            raise unittest.SkipTest("the v0.5 disc image is not on this machine")
        if hashlib.sha256(files["vc_53450030/e"]).hexdigest() != anniversary.V05_PACK_SHA256[14]:
            raise unittest.SkipTest("pack E is not the v0.5 pack")
        from nfl_outer import HEADER_SIZE
        head = files["vc_53450030/0"][:HEADER_SIZE]
        head += files["vc_53450030/0"][HEADER_SIZE:HEADER_SIZE + 12 * struct.unpack_from("<I", head)[0]]
        cls.head, cls.packs = head, {14: files["vc_53450030/e"], 15: files["vc_53450030/f"]}
        cls.out, cls.receipt = anniversary.repair_packs(head, cls.packs)

    def test_hashes_scope_and_idempotence(self) -> None:
        self.assertEqual({k: hashlib.sha256(v).hexdigest() for k, v in self.out.items()}, anniversary.F12_PACK_SHA256)
        self.assertEqual((self.receipt["teams"], self.receipt["records"]), (50, 2650))
        self.assertEqual({k: v["changed_bytes"] for k, v in self.receipt["packs"].items()}, {"E": 2544, "F": 106})
        again, receipt = anniversary.repair_packs(self.head, self.out)
        self.assertEqual((again, receipt["state"]), (self.out, "already_applied"))

    @unittest.skipUnless(HAVE_UNICORN and HAVE_CAPSTONE, "unicorn and capstone are required for the native proof")
    def test_the_card_text_of_the_2025_bengals_before_and_after(self) -> None:
        import csv
        from tools.b77 import f12_rollover_proof as proof
        files = v05_files(("default.xbe", "vc_53450030/0"))
        game = proof.Game(files["default.xbe"], proof.rost_body(files["vc_53450030/0"]))
        entries, packs = anniversary.read_directory(self.head)
        team = [c for c in anniversary.team_candidates(self.packs, entries, packs)
                if {(f, l) for f, l, _y, _o in c["players"]} >= {("Joe", "Flacco"), ("Ja'Marr", "Chase")}]
        self.assertEqual(len(team), 1)
        resource = team[0]
        rows = list(csv.DictReader((ROOT / "data/nfl2k5_espn25_more_teams/bengals_2025.csv").open(encoding="utf-8", newline="")))
        rookies = {(r["first"], r["last"]) for r in rows if int(r["years_pro"]) == 1}
        self.assertTrue(rookies, "the 2025 Bengals have rookies")
        seen = {}
        for first, last, _years, offset in resource["players"]:
            if (first, last) in rookies or (first, last) == ("Joe", "Flacco"):
                at = resource["local"] + anniversary.RESOURCE_HEADER_SIZE + offset
                before = game.card_of_record(self.packs[resource["pack"]][at:at + 84])
                after = game.card_of_record(self.out[resource["pack"]][at:at + 84])
                seen[(first, last)] = (before, after)
        self.assertEqual(seen[("Joe", "Flacco")], ("17", "18"))
        for name in rookies:
            self.assertEqual(seen[name], ("0", "R"), name)

    @unittest.skipUnless(HAVE_UNICORN and HAVE_CAPSTONE, "unicorn and capstone are required for the native proof")
    def test_the_card_text_of_the_sparse_team_seasons_before_and_after(self) -> None:
        """Before the fix a missing-data 0 sat on nearly every record of six teams; after it each card shows the career year."""
        from tools.b77 import f12_rollover_proof as proof
        files = v05_files(("default.xbe", "vc_53450030/0"))
        game = proof.Game(files["default.xbe"], proof.rost_body(files["vc_53450030/0"]))
        entries, packs = anniversary.read_directory(self.head)
        candidates = anniversary.team_candidates(self.packs, entries, packs)
        wanted = {"vikings_1998": {("Randy", "Moss"): "R", ("Randall", "Cunningham"): "14", ("Cris", "Carter"): "12"},
                  "patriots_2001": {("Tom", "Brady"): "2", ("Richard", "Seymour"): "R", ("Drew", "Bledsoe"): "9"},
                  "falcons_1998": {("Steve", "DeBerg"): "22", ("Tim", "Dwight"): "R"},
                  "raiders_2001": {("Rich", "Gannon"): "15", ("Jerry", "Rice"): "17"}}
        pins = anniversary.load_pins()
        for key, names in wanted.items():
            roster = [(f, l, o) for f, l, o, _n in pins["teams"][key]["players"]]
            found = [c for c in candidates if [(f, l, y) for f, l, y, _o in c["players"]] == roster]
            self.assertEqual(len(found), 1, key)
            resource = found[0]
            seen = {}
            for first, last, _years, offset in resource["players"]:
                if (first, last) in names:
                    at = resource["local"] + anniversary.RESOURCE_HEADER_SIZE + offset
                    seen[(first, last)] = (game.card_of_record(self.packs[resource["pack"]][at:at + 84]),
                                           game.card_of_record(self.out[resource["pack"]][at:at + 84]))
            self.assertEqual({k: v[1] for k, v in seen.items()}, names, key)
            # v0.5 printed 0 for the missing-data players and R for the few whose roster row carried years_exp (Brady's 2001
            # row had 1, stored as 1: R); every one of these cards changes
            self.assertTrue(all(before in ("0", "R") and before != after for before, after in seen.values()), f"{key}: {seen}")


@unittest.skipUnless(HAVE_UNICORN and HAVE_CAPSTONE, "unicorn and capstone are required for the native proof")
class NativeRolloverTests(unittest.TestCase):
    """The shipped x86 on the real v0.5 default.xbe: card text, rollover step, class generator."""

    @classmethod
    def setUpClass(cls) -> None:
        files = v05_files()
        if files is None or hashlib.sha256(files["vc_53450030/0"]).hexdigest() != repair.V05_PACK0_SHA256:
            raise unittest.SkipTest("the v0.5 disc image is not on this machine")
        from tools.b77 import f12_rollover_proof as proof
        cls.proof = proof
        cls.xbe = files["default.xbe"]
        cls.before = proof.rost_body(files["vc_53450030/0"])
        repaired, _ = repair.repair_pack0(files["vc_53450030/0"])
        cls.after = proof.rost_body(repaired)

    def test_player_card_text_before_and_after(self) -> None:
        indices = {name: self.proof.find(self.before, *name.split(" ", 1), birth)
                   for name, birth in (("Cam Ward", "2002-05-25"), ("Fernando Mendoza", "2003-10-01"),
                                       ("Patrick Mahomes", "1995-09-17"))}
        old, new = self.proof.Game(self.xbe, self.before), self.proof.Game(self.xbe, self.after)
        self.assertEqual({n: old.card(i) for n, i in indices.items()}, {"Cam Ward": "R", "Fernando Mendoza": "0", "Patrick Mahomes": "9"})
        self.assertEqual({n: new.card(i) for n, i in indices.items()}, {"Cam Ward": "2", "Fernando Mendoza": "R", "Patrick Mahomes": "10"})

    def test_the_career_table_reads_the_same_before_and_after_for_the_games_own_getters(self) -> None:
        old, new = self.proof.Game(self.xbe, self.before), self.proof.Game(self.xbe, self.after)
        mahomes = self.proof.find(self.before, "Patrick", "Mahomes", "1995-09-17")
        kelce = self.proof.find(self.before, "Travis", "Kelce", "1989-10-05")
        ward = self.proof.find(self.before, "Cam", "Ward", "2002-05-25")
        for index, first_label, rows in ((mahomes, "2025", 9), (kelce, "2025", 12), (ward, "2025", 1)):
            before, after = old.career_rows(index), new.career_rows(index)
            self.assertEqual(before, after, index)
            self.assertEqual((before[0][0], len(before)), (first_label, rows))
        # slot 1 is the rookie year: Mahomes's 2017 season is the last row, one game, with the same TEAM
        self.assertEqual(new.career_rows(mahomes)[-1][:2], ("2017", 1))

    def test_rollover_adds_one_to_every_allocated_non_prospect_and_a_rookie_keeps_r_only_one_season(self) -> None:
        game = self.proof.Game(self.xbe, self.after)
        before = [(game.years_pro(i), game.flags(i)) for i in range(game.count)]
        game.rollover()
        for i, (years, flags) in enumerate(before):
            expected = (years + 1) & 31 if flags & 0x04 and not flags & 0x10 else years
            self.assertEqual(game.years_pro(i), expected, i)
        mendoza = self.proof.find(self.after, "Fernando", "Mendoza", "2003-10-01")
        self.assertEqual(game.card(mendoza), "2")

    def test_the_class_generator_starts_every_rookie_as_one(self) -> None:
        rows = self.proof.Game(self.xbe, self.after).generate_rookies()
        self.assertEqual(len(rows), 17)
        self.assertTrue(all(r["years_pro"] == 1 and r["card"] == "R" for r in rows), rows)


if __name__ == "__main__":
    unittest.main()
