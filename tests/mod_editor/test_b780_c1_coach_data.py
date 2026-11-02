"""b780 c1-coachdata: the sourced 2026 coach data (tools/nfl2k5_coach_2026_data.py, data/nfl2k5_coaches_2026.json).

The builder is tested on tiny synthetic play-by-play (no pyarrow, no nflverse files); the committed data file is checked
against the repository (names, ranges, the writer's own rules) and against the retail roster when the private disc is
present."""
from __future__ import annotations

import collections
import copy
import json
import os
import random
import re
import statistics
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import nfl2k5_coach_2026_data as cd  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

_XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))


def coach(club: str, name: str, offense=(), defense=()) -> dict:
    return dict(team=club, coach=name, offense_history=list(offense), defense_history=list(defense))


def hc(team: str, first: int, last: int, **extra) -> dict:
    return dict(team=team, first_season=first, last_season=last, role="HC", **extra)


def play(game: str, play_id: int, pos: str, opp: str, epa: float, **extra) -> dict:
    row = dict(game_id=game, play_id=float(play_id), season=2022, season_type="REG", game_date="2022-09-18", posteam=pos,
               defteam=opp, qtr=1, play_type="pass", epa=epa, success=1.0, qb_dropback=1.0, pass_attempt=1.0, sack=0.0,
               qb_hit=0.0, interception=0.0, rush_attempt=0.0, cpoe=1.0, penalty=0.0)
    row.update(extra)
    return row


class NumbersTests(unittest.TestCase):
    def test_largest_remainder_adds_up_to_the_total_and_keeps_zeros(self) -> None:
        rng = random.Random(7)
        for _ in range(200):
            weights = [rng.choice((0, 0, 1, 2, 7, 33, 100, 4096)) for _ in range(rng.choice((4, 5, 6)))]
            if sum(weights) == 0:
                continue
            shares = cd.largest_remainder(weights)
            self.assertEqual(sum(shares), 100, weights)
            self.assertTrue(all(s == 0 for s, w in zip(shares, weights) if w == 0), (weights, shares))
        self.assertEqual(cd.largest_remainder([1, 1, 1]), [34, 33, 33], "ties go to the lower index")
        with self.assertRaises(cd.CoachDataError):
            cd.largest_remainder([0, 0])

    def test_standardize_is_neutral_without_evidence(self) -> None:
        z = cd.standardize({"a": 1.0, "b": 2.0, "c": 3.0, "d": None})
        self.assertEqual(z["d"], 0.0)
        self.assertAlmostEqual(z["a"], -z["c"])
        self.assertAlmostEqual(cd.standardize({"a": 1.0, "b": 2.0, "c": 3.0}, -1)["a"], -z["a"])
        self.assertEqual(cd.standardize({"a": 1.0, "b": 2.0}), {"a": 0.0, "b": 0.0}, "two coaches are not a distribution")

    def test_shrink_pulls_a_short_sample_toward_the_league(self) -> None:
        self.assertIsNone(cd.shrink(0.3, 0, 100, 0.0))
        self.assertIsNone(cd.shrink(None, 50, 100, 0.0))
        self.assertAlmostEqual(cd.shrink(1.0, 100, 100, 0.0), 0.5)
        self.assertAlmostEqual(cd.shrink(1.0, 1e9, 100, 0.0), 1.0, places=6)

    def test_ratings_stay_on_the_retail_scale(self) -> None:
        self.assertEqual(cd.to_rating(0.0, 78), 78)
        self.assertEqual(cd.to_rating(-9.0, 78), 60)
        self.assertEqual(cd.to_rating(9.0, 83), 99)
        self.assertEqual(cd.to_rating(1.0, 78), 87)

    def test_formation_classes_follow_the_games_five_classes(self) -> None:
        for formation, personnel, expect in (("SHOTGUN", "1 RB, 1 TE, 3 WR", 1), ("PISTOL", "1 RB, 1 TE, 3 WR", 1),
                                              ("EMPTY", "0 RB, 1 TE, 4 WR", 1), ("UNDER CENTER", "2 RB, 1 TE, 2 WR", 3),
                                              ("UNDER CENTER", "1 RB, 1 TE, 3 WR", 4), ("UNDER CENTER", "0 RB, 2 TE, 3 WR", 5),
                                              ("UNDER CENTER", "1 RB, 2 TE, 2 WR, 1 OL", 4), ("I_FORM", None, 3),
                                              ("SINGLEBACK", None, 4), (None, "1 RB", None), ("MYSTERY", None, None)):
            self.assertEqual(cd.formation_class(formation, personnel), expect, (formation, personnel))


class PlayByPlayTests(unittest.TestCase):
    COACHES = [coach("AAA", "Ann Alpha", offense=[hc("AAA", 2021, 2026)], defense=[hc("AAA", 2021, 2026)]),
               coach("BBB", "Bob Beta", offense=[hc("BBB", 2022, 2026, first_date="2022-09-15")], defense=[hc("BBB", 2022, 2026)])]
    POSITIONS = {(2022, "WR1"): "WR", (2022, "TE1"): "TE", (2022, "RB1"): "RB", (2022, "QB1"): "QB"}

    def collect(self, rows):
        return cd.collect_pbp(rows, self.COACHES, self.POSITIONS)

    def test_offense_and_defense_totals_follow_the_roles_and_seasons(self) -> None:
        rows = [play("g1", 1, "AAA", "BBB", 0.5, receiver_player_id="WR1"),
                play("g1", 2, "AAA", "BBB", 0.1, play_type="run", qb_dropback=0.0, pass_attempt=0.0, rush_attempt=1.0,
                     rusher_player_id="RB1"),
                play("g1", 3, "AAA", "BBB", -1.0, sack=1.0, pass_attempt=0.0, qb_hit=1.0),
                play("g1", 4, "BBB", "AAA", 0.3, receiver_player_id="TE1"),
                play("g1", 5, "AAA", "BBB", 9.9, season=2019),                       # outside the window
                play("g1", 6, "AAA", "BBB", 9.9, season_type="POST")]                  # playoffs are not evidence
        state = self.collect(rows)
        a, b = state["off"]["AAA"], state["off"]["BBB"]
        self.assertEqual((a["plays"], a["dropbacks"], a["attempts"], a["rushes"], a["sacks"], a["hits"]), (3, 2, 1, 1, 1, 1))
        self.assertAlmostEqual(a["epa"], -0.4)
        self.assertEqual((a["wr_targets"], a["rb_carries"]), (1, 1))
        self.assertEqual((b["plays"], b["te_targets"]), (1, 1))
        d = state["dfn"]["AAA"]
        self.assertEqual((d["plays"], d["attempts"]), (1, 1))
        self.assertEqual(state["league"]["plays"], 4)

    def test_a_date_cut_off_keeps_a_predecessor_out_of_the_coachs_games(self) -> None:
        early = play("g0", 1, "BBB", "AAA", 1.0, game_date="2022-09-11")
        late = play("g2", 1, "BBB", "AAA", 1.0, game_date="2022-09-18")
        state = self.collect([early, late])
        self.assertEqual(state["off"]["BBB"]["plays"], 1, "the game before Bob's first_date is not his")
        self.assertEqual(state["hc_games"]["BBB"], {"g2"})

    def test_penalties_special_teams_the_fourth_quarter_and_the_script(self) -> None:
        rows = [play("g1", 1, "AAA", "BBB", None, play_type="no_play", penalty=1.0, penalty_team="AAA",
                     penalty_type="False Start"),
                play("g1", 2, "AAA", "BBB", None, play_type="no_play", penalty=1.0, penalty_team="AAA",
                     penalty_type="Unnecessary Roughness"),
                play("g1", 3, "AAA", "BBB", None, play_type="no_play", penalty=1.0, penalty_team="BBB",
                     penalty_type="False Start"),
                play("g1", 4, "AAA", "BBB", None, play_type="no_play", penalty=1.0, penalty_team="AAA",
                     penalty_type="Offensive Holding"),                                  # neither procedural nor personal
                # nflverse: on a kickoff posteam is the RECEIVING team and epa is from its side; on a punt it is the punter
                play("g1", 5, "AAA", "BBB", 0.4, play_type="kickoff", qb_dropback=0.0, pass_attempt=0.0),
                play("g1", 6, "BBB", "AAA", -0.2, play_type="punt", qb_dropback=0.0, pass_attempt=0.0),
                play("g1", 7, "AAA", "BBB", 0.5, qtr=4), play("g1", 8, "BBB", "AAA", 0.25, qtr=4)]
        state = self.collect(rows)
        t = state["hc"]["AAA"]
        self.assertEqual((t["pen_procedural"], t["pen_personal"]), (1, 1))
        self.assertAlmostEqual(t["st_epa"], 0.4 + 0.2, msg="receiving the kickoff (+0.4) and covering the punt (-(-0.2))")
        self.assertAlmostEqual(t["q4_epa"], 0.5 - 0.25)
        self.assertEqual(state["hc"]["BBB"]["pen_procedural"], 1)

    def test_the_script_is_the_first_fifteen_plays_by_play_number_whatever_the_row_order(self) -> None:
        rows = [play("g1", n, "AAA", "BBB", float(n)) for n in range(1, 21)]
        random.Random(3).shuffle(rows)
        state = self.collect(rows)
        plays = state["script"]["AAA", "g1"]
        self.assertEqual(len(plays), 20)
        metrics = cd.unit_metrics(state, self.COACHES, {c["team"]: cd.results_block([]) for c in self.COACHES})
        first = sum(range(1, 16)) / 15
        league = state["league"]["epa"] / state["league"]["plays"]
        self.assertAlmostEqual(metrics["AAA"]["script_epa"], league + (first - league) * 15 / (15 + cd.N0["plays"]))


class ResultsTests(unittest.TestCase):
    @staticmethod
    def game(season, week, home, away, hs, as_, hc_, ac, spread=None, kind="REG"):
        return dict(season=str(season), week=str(week), game_type=kind, gameday=f"{season}-09-{week:02d}", home_team=home,
                    away_team=away, home_score=str(hs), away_score=str(as_), home_coach=hc_, away_coach=ac,
                    spread_line="" if spread is None else str(spread))

    def test_a_coachs_games_cover_the_spread_from_his_side_and_bounce_back_after_losses(self) -> None:
        rows = [self.game(2024, 1, "HHH", "AAA", 20, 24, "Hal", "Ann", spread=3),      # Ann wins as the away dog: covers
                self.game(2024, 2, "AAA", "HHH", 10, 20, "Ann", "Hal", spread=-3),      # Ann loses at home, a 3 point dog: no cover
                self.game(2024, 3, "AAA", "HHH", 27, 20, "Ann", "Hal", spread=7),       # Ann wins by 7 as a 7 point favourite: push
                self.game(2024, 4, "HHH", "AAA", 17, 21, "Hal", "Ann", spread=None),    # no line
                self.game(2025, 1, "AAA", "HHH", 3, 30, "Ann", "Hal", spread=3, kind="DIV")]
        games = cd.head_coach_games(rows, "Ann")
        self.assertEqual([g["covered"] for g in games], [True, False, None, None, False])
        block = cd.results_block(games)
        self.assertEqual((block["games"], block["seasons"]), (4, 1))
        self.assertEqual(block["win_rate"], 0.75)
        self.assertEqual((block["bounce_games"], block["bounce_win_rate"]), (1, 1.0), "the game after the one loss was won")
        self.assertEqual((block["ats_games"], block["ats_rate"]), (2, 0.5))
        self.assertEqual((block["playoff_games"], block["playoff_wins"]), (1, 0))
        self.assertEqual(cd.head_coach_games(rows + [self.game(2026, 1, "AAA", "HHH", 3, 0, "Ann", "Hal")], "Ann"), games,
                         "the season being played is not part of a career")

    def test_a_misspelled_name_is_found_but_a_stranger_is_not(self) -> None:
        rows = [self.game(2025, 1, "AAA", "HHH", 3, 0, "Klint Kubliak", "Hal")]
        self.assertEqual(cd.resolve_games_name(rows, "Klint Kubiak", "LV"), "Klint Kubliak")
        self.assertEqual(cd.resolve_games_name(rows, "Totally Different", "LV"), "Totally Different")


class TendencyTests(unittest.TestCase):
    @staticmethod
    def rate(runs, calls):
        return dict(numerator=runs, denominator=calls, rate=runs / calls if calls else None)

    def vip(self, pass_rate=0.6, no_huddle=0.1):
        lanes = {"left_outside": 0.1, "left_inside": 0.3, "middle": 0.3, "right_inside": 0.2, "right_outside": 0.1}
        return dict(overall=dict(calls=1000, pass_rate=dict(rate=pass_rate),
                                 run_lane={k: dict(rate=v, denominator=100) for k, v in lanes.items()}),
                    native_statistics=dict(score=[self.rate(10, 100)] * 6, redzone=self.rate(0, 0),
                                           down_distance=[self.rate(1, 2)] * 16),
                    native_decision_projections=dict(no_huddle=dict(rate=no_huddle)))

    def test_groups_are_percentages_the_writer_accepts(self) -> None:
        out, basis = cd.tendencies_for(self.vip(), None)
        self.assertEqual(out["run_share"], 40)
        self.assertEqual(out["run_by_score"], [round(100 * (10 + 20 * 0.4) / 120)] * 6, "cells lean on his own run share")
        self.assertEqual(out["run_redzone"], 40, "no red zone calls: exactly his own run share")
        self.assertEqual(out["run_by_down_distance"], [round(100 * (1 + 20 * 0.4) / 22)] * 16)
        self.assertEqual(out["run_lane"], [round(x) for x in out["run_lane"]])
        self.assertEqual(sum(out["run_lane"]), 100)
        self.assertEqual(out["no_huddle"], round(100 * 0.1 / (4 - 0.3)))
        rr.plan_coach_record({"tendencies": out})
        self.assertEqual(basis["calls"], 1000)

    def test_formation_shares_come_from_the_coach_or_else_the_league(self) -> None:
        coach_counts = dict(run=collections.Counter({1: 100, 4: 100, 3: 10}), pass_=collections.Counter({1: 250}))
        league = dict(run=collections.Counter({1: 40, 4: 160, 3: 10}), pass_=collections.Counter({1: 180, 4: 30}))
        out, basis = cd.tendencies_for(self.vip(), coach_counts, league)
        self.assertEqual(out["formation_run"], cd.largest_remainder([100, 0, 10, 100, 0]), "his own 210 classified runs")
        self.assertEqual(basis["formation_run"]["source"], "coach")
        self.assertEqual(out["formation_pass"], [100, 0, 0, 0, 0])
        thin = dict(run=collections.Counter({1: 5}), pass_=collections.Counter({1: 5}))
        out, basis = cd.tendencies_for(self.vip(), thin, league)
        self.assertEqual(out["formation_run"], cd.largest_remainder([40, 0, 10, 160, 0]))
        self.assertEqual(basis["formation_run"]["source"], "league")
        self.assertEqual(basis["formation_pass"]["classes"], {"1": 180, "2": 0, "3": 0, "4": 30, "5": 0})

    def test_participation_rows_join_the_plays_the_pass_remembered(self) -> None:
        coaches = PlayByPlayTests.COACHES
        state = cd.collect_pbp([play("g1", 1, "AAA", "BBB", 0.2), play("g1", 2, "AAA", "BBB", 0.1, play_type="run", qb_dropback=0.0,
                                                                    pass_attempt=0.0, rush_attempt=1.0),
                                play("g1", 3, "CCC", "DDD", 0.1)], coaches, {})
        rows = [dict(nflverse_game_id="g1", play_id=1.0, offense_formation="SHOTGUN", offense_personnel="1 RB, 1 TE, 3 WR"),
                dict(nflverse_game_id="g1", play_id=2.0, offense_formation="UNDER CENTER", offense_personnel="2 RB, 1 TE, 2 WR"),
                dict(nflverse_game_id="g1", play_id=3.0, offense_formation="SHOTGUN", offense_personnel="1 RB, 1 TE, 3 WR"),
                dict(nflverse_game_id="g1", play_id=9.0, offense_formation="SHOTGUN", offense_personnel="1 RB")]
        mine = cd.collect_formations(rows, state)
        self.assertEqual(dict(mine["AAA"]["pass_"]), {1: 1})
        self.assertEqual(dict(mine["AAA"]["run"]), {3: 1})
        league = cd.collect_league_formations(rows, state)
        self.assertEqual((dict(league["pass_"]), dict(league["run"])), ({1: 2}, {3: 1}))


class RatingModelTests(unittest.TestCase):
    def metrics(self, count=8):
        out = {}
        for i in range(count):
            out[f"C{i}"] = dict(off_epa=0.01 * i, pass_epa=0.01 * i, rush_epa=0.0, rush_success=0.4, qb_epa=0.01 * i, qb_cpoe=0.0,
                                off_sack_rate=0.05, off_hit_rate=0.1, rb_epa=0.0, te_epa=0.0, wr_epa=0.0, def_epa=-0.01 * i,
                                def_attempt_epa=0.0, def_rush_epa=0.0, def_sack_rate=0.06, def_hit_rate=0.1, def_stuff_rate=0.1,
                                def_int_rate=0.02, st_per_game=None, proc_per_game=None, personal_per_game=None,
                                script_epa=None, q4_per_game=None, win_rate=0.4 + 0.02 * i, recent_margin=float(i),
                                playoff_win_rate=None, close_win_rate=None, bounce_win_rate=None, ats_rate=None,
                                playoff_wins_per_season=None, tenure=None)
        return out

    def test_better_numbers_never_rate_lower_and_missing_evidence_is_the_baseline(self) -> None:
        ratings, zs = cd.ratings_from_metrics(self.metrics())
        order = [ratings[f"C{i}"] for i in range(8)]
        for name in ("overall", "offense", "pass_for", "defense", "qb"):
            values = [r[name] for r in order]
            self.assertEqual(values, sorted(values), name)
            self.assertGreater(values[-1], values[0], name)
        for name in ("special_teams", "preparation", "professionalism", "discipline", "conditioning"):
            expected = cd.BASE_FOOTBALL if name == "special_teams" else cd.BASE_CHARACTER
            self.assertEqual({r[name] for r in order}, {expected}, f"{name}: nobody has evidence")
        self.assertTrue(all(cd.RATING_MIN <= r[name] <= cd.RATING_MAX for r in order for name in cd.RATING_ORDER))
        self.assertEqual(set(order[0]), set(rr.COACH_RATING_NAMES))


class CommittedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = cd.load_data()

    def test_the_file_is_sound_by_the_writers_own_rules(self) -> None:
        self.assertEqual(cd.validate(self.data), [])
        self.assertEqual(len(self.data["coaches"]), 32)

    def test_every_club_has_its_head_coach_and_the_generic_announcer(self) -> None:
        sources = {r["team"]: r["coach"] for r in json.loads((ROOT / "data/vip/coach_sources_2026.json").read_text(encoding="utf-8"))}
        self.assertEqual({k: v["coach"] for k, v in self.data["coaches"].items()}, sources)
        self.assertEqual({v["announcer"] for v in self.data["coaches"].values()}, {"generic"})

    def test_every_distribution_adds_up_and_every_rating_is_on_the_scale(self) -> None:
        for club, entry in self.data["coaches"].items():
            for name, (_at, _count, kind) in rr.COACH_TENDENCY_GROUPS.items():
                if kind == "share" and name in entry["tendencies"]:
                    self.assertEqual(sum(entry["tendencies"][name]), 100, (club, name))
            self.assertEqual(set(entry["ratings"]), set(rr.COACH_RATING_NAMES), club)
            self.assertTrue(all(60 <= v <= 99 for v in entry["ratings"].values()), club)
            self.assertIn("formation_run", entry["tendencies"], club)
            self.assertIn("formation_pass", entry["tendencies"], club)

    def test_the_ratings_spread_like_the_retail_scale(self) -> None:
        for name in rr.COACH_RATING_NAMES:
            values = [e["ratings"][name] for e in self.data["coaches"].values()]
            self.assertTrue(74 <= statistics.fmean(values) <= 86, (name, statistics.fmean(values)))
            self.assertTrue(5 <= statistics.pstdev(values) <= 12, (name, statistics.pstdev(values)))

    def test_no_evidence_means_the_baseline_not_a_guess(self) -> None:
        none_seen = 0
        for club, entry in self.data["coaches"].items():
            metrics = entry["basis"]["metrics"]
            if metrics["games"] == 0:                      # a first-time head coach: no head-coach games before 2026
                none_seen += 1
                for name in ("special_teams",):
                    self.assertEqual(entry["ratings"][name], cd.BASE_FOOTBALL, (club, name))
                for name in ("professionalism", "preparation", "conditioning", "discipline"):
                    self.assertEqual(entry["ratings"][name], cd.BASE_CHARACTER, (club, name))
            if metrics["off_epa_n"] == 0:
                self.assertEqual(entry["ratings"]["offense"], cd.BASE_FOOTBALL, club)
            if metrics["def_epa_n"] == 0:
                self.assertEqual(entry["ratings"]["defense"], cd.BASE_FOOTBALL, club)
        self.assertGreater(none_seen, 0)

    def test_the_inputs_are_pinned(self) -> None:
        inputs = self.data["inputs"]
        hashes = [inputs["games_csv"]["sha256"], inputs["coach_sources"]["sha256"]] + [x["sha256"] for k in ("rosters", "play_by_play", "participation") for x in inputs[k]]
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes))
        self.assertEqual(inputs["coach_sources"]["sha256"], cd.sha256_file(cd.SOURCES_PATH),
                         "the club/role sources changed since the data was built: rebuild it")
        for name, digest in inputs["vip_tendencies"].items():
            self.assertEqual(cd.sha256_file(cd.VIP_DIR / name), digest, f"{name} changed since the data was built: rebuild it")

    def test_record_entry_refuses_another_coach_and_hands_out_copies(self) -> None:
        self.assertIsNone(cd.record_entry(self.data, "KC", "Someone Else"))
        self.assertIsNone(cd.record_entry(self.data, "XXX"))
        first = cd.record_entry(self.data, "KC", "Andy Reid")
        first["ratings"]["overall"] = 1
        first["tendencies"]["run_lane"][0] = 99
        again = cd.record_entry(self.data, "KC", "Andy Reid")
        self.assertNotEqual(again["ratings"]["overall"], 1)
        self.assertNotEqual(again["tendencies"]["run_lane"][0], 99)


class EditsDocumentTests(unittest.TestCase):
    def test_entries_gain_the_record_fields_and_keep_their_names(self) -> None:
        document = {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": [
            {"team": "KC", "first": "Andy", "last": "Reid", "full_name": "Andy Reid", "fields": {"wins": 1}, "bio": ["x"]},
            {"team": "OAK", "first": "Klint", "last": "Kubiak"},                         # retail code for Las Vegas
            {"team": "NYG", "first": "Tom", "last": "Coughlin"},                         # not the 2026 coach
        ]}
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "in.json", Path(folder) / "out.json"
            source.write_text(json.dumps(document), encoding="utf-8")
            result = cd.add_to_edits(source, target)
            out = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(result["written"], 2)
        self.assertEqual(len(result["mismatched"]), 1)
        self.assertIn("NYG", result["mismatched"][0])
        self.assertIn("DEN", result["missing"])
        kc, oak, nyg = out["coaches"]
        self.assertEqual((kc["first"], kc["last"], kc["fields"], kc["bio"]), ("Andy", "Reid", {"wins": 1}, ["x"]))
        self.assertEqual(set(kc) - {"team", "first", "last", "full_name", "fields", "bio"}, {"ratings", "tendencies", "announcer"})
        self.assertEqual(oak["ratings"], self.expected("LV")["ratings"])
        self.assertNotIn("ratings", nyg)

    @staticmethod
    def expected(club: str) -> dict:
        return cd.record_entry(cd.load_data(), club)


@unittest.skipUnless(_XISO.is_file(), "private retail NFL 2K5 disc absent (set NFL2K5_RETAIL_XISO)")
class RetailRosterTests(unittest.TestCase):
    def test_all_thirty_two_entries_land_on_the_retail_roster_and_only_record_bytes_move(self) -> None:
        base = rr.load_image(_XISO).to_body()
        document = rr.RosterDocument(base)
        clubs = [t for t in document.teams if t.index < 32]
        data = cd.load_data()
        entries = [dict(cd.record_entry(data, ct_code), team=team.abbreviation)
                   for team in clubs for ct_code in [cd.ct.team(team.abbreviation)]]
        new, receipt = rr.apply_body(base, {"schema": rr.EDITS_SCHEMA, "edits": [], "coaches": entries})
        self.assertEqual(receipt["log"], [])
        self.assertEqual(receipt["coach_records_written"], 32)
        self.assertEqual(receipt["coach_names_written"], 0)
        records = {t.coach_offset: t for t in clubs}
        self.assertEqual(len(records), 32)
        for index, (a, b) in enumerate(zip(base, new)):
            if a != b:
                owner = next((r for r in records if r <= index < r + rr.COACH_RECORD_SIZE), None)
                self.assertIsNotNone(owner, f"byte 0x{index:X} outside the coach records changed")
                rel = index - owner
                self.assertTrue(rel in (0x14, 0x15, 0x16, 0x17, 0x1A) or 0x42 <= rel < 0xA8, f"+0x{rel:X}")
        # every club's record reads back its own entry
        after = rr.RosterDocument(new)
        for team in after.teams[:32]:
            entry = data["coaches"][cd.ct.team(team.abbreviation)]
            record = team.coach_offset
            self.assertEqual(list(new[record + 0x42: record + 0x59]), [entry["ratings"][n] for n in rr.COACH_RATING_NAMES])
            self.assertEqual(new[record + 0x59], entry["tendencies"]["run_share"])
            self.assertTrue(new[record + 0x1A] & 2)
            self.assertFalse(new[record + 0x1A] & 1)


if __name__ == "__main__":
    unittest.main()
