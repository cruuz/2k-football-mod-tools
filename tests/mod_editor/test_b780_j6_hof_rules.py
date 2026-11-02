"""Job j6-hof (b780): the Hall of Fame rule, its calibration on real careers, the yearly process, the records and the pop-up.

Pure Python, no network, no game files; runs on every OS. The calibration tests read the checked-in dataset
``data/nfl2k5_hof_calibration_2026.json`` (retired players 1999-2025 from nflverse and pinned Wikipedia pages) and pin the
numbers the report quotes, so a change to the rule, the data or the process shows up here first. Two tests need files that
are not in the repo and skip without them: the hn1 simulated seasons (``B780_HN1_RUNS``) and the pinned source cache
(``B780_HOF_CACHE``, from ``tools/b780_hof_calibrate.py fetch``).
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_champions_history as champions  # noqa: E402
from mod_editor.core import nfl2k5_hof_rules as rules  # noqa: E402


def _load_tool():
    spec = importlib.util.spec_from_file_location("b780_hof_calibrate", ROOT / "tools" / "b780_hof_calibrate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()
ROWS = TOOL.load_rows()
BY_NAME = {}
for _row in ROWS:
    BY_NAME.setdefault(_row["name"], []).append(_row)


def career(name: str, last: int | None = None):
    rows = [r for r in BY_NAME[name] if last is None or r["last"] == last]
    assert len(rows) == 1, (name, len(rows))
    return TOOL.rows_career(rows[0])


def Q(**kw):
    return rules.Career.from_position("QB", **kw)


# --------------------------------------------------------------------------------------------------------------------
class ScoreTests(unittest.TestCase):
    def test_position_groups(self):
        self.assertEqual(len(rules.POSITIONS), 17)
        self.assertEqual(len(rules.GROUP_OF_POSITION), 17)
        names = {rules.POSITIONS[i]: rules.GROUPS[g] for i, g in enumerate(rules.GROUP_OF_POSITION)}
        self.assertEqual(names, {"QB": "QB", "K": "K", "P": "P", "WR": "WR", "CB": "DB", "FS": "DB", "SS": "DB", "HB": "RB", "FB": "RB",
                                 "TE": "TE", "OLB": "LB", "ILB": "LB", "C": "OL", "G": "OL", "T": "OL", "DT": "DL", "DE": "DL"})
        self.assertEqual(rules.Career.from_position("HB").group, rules.GROUPS.index("RB"))
        with self.assertRaises(ValueError):
            rules.Career.from_position(17)

    def test_every_honor_term(self):
        one = {"all_pro": 25, "mvp": 25, "opoy": 15, "dpoy": 15, "super_bowl_mvp": 15, "oroy": 10, "droy": 10, "rushing_title": 15,
               "super_bowl": 3}
        for name, points in one.items():
            self.assertEqual(rules.score(Q(**{name: 1})), points, name)
        self.assertEqual(rules.score(Q(all_pro=4)), 100)

    def test_caps_and_floors(self):
        self.assertEqual(rules.score(Q(rushing_title=9)), 4 * 15)             # at most four rushing titles count
        self.assertEqual(rules.score(Q(super_bowl=9)), 4 * 3)                 # and four rings
        self.assertEqual([rules.games_points(Q(games=g)) for g in (0, 80, 83, 84, 160, 161, 400)], [0, 0, 0, 1, 20, 20, 20])
        line = rules.Career.from_position("T", games=400)
        self.assertEqual(rules.games_points(line), 35)                        # linemen only
        self.assertEqual(rules.games_points(rules.Career.from_position("P", games=400)), 20)
        self.assertEqual(rules.production_points(line), 0)
        self.assertEqual(rules.production_points(rules.Career.from_position("P", games=400)), 0)

    def test_production_is_a_share_of_par(self):
        rb = lambda yards: rules.Career.from_position("HB", rushing_yards=yards)           # noqa: E731
        self.assertEqual(rules.production_points(rb(21000)), 25)              # exactly par
        self.assertEqual(rules.production_points(rb(20999)), 24)              # one tenth below
        self.assertEqual(rules.production_points(rb(10500)), 12)
        self.assertEqual(rules.production_points(rb(90000)), 25)              # saturates
        self.assertEqual(rules.production_points(rules.Career.from_position("K", field_goals_made=400)), 25)
        self.assertEqual(rules.production_points(rules.Career.from_position("ILB", sacks_half=100, interceptions=0)), 25 * 1500 // 1500)

    def test_composite_by_group(self):
        self.assertEqual(rules.composite(Q(passing_touchdowns=10, rushing_touchdowns=1)), 100 + 20)
        self.assertEqual(rules.composite(rules.Career.from_position("HB", rushing_yards=100, rushing_touchdowns=1, receiving_yards=50,
                                                                   receiving_touchdowns=2)), 100 + 60 + 50 + 120)
        self.assertEqual(rules.composite(rules.Career.from_position("WR", receiving_yards=100, receiving_touchdowns=1, rushing_yards=999)), 160)
        self.assertEqual(rules.composite(rules.Career.from_position("DE", sacks_half=2, interceptions=1)), 30 + 40)
        self.assertEqual(rules.composite(rules.Career.from_position("ILB", sacks_half=2, interceptions=1)), 30 + 50)
        self.assertEqual(rules.composite(rules.Career.from_position("CB", sacks_half=2, interceptions=1)), 50 + 30)
        self.assertEqual(rules.composite(rules.Career.from_position("K", field_goals_made=3)), 30)
        self.assertEqual(rules.composite(rules.Career.from_position("G", games=300, all_pro=3)), 0)

    def test_negative_sums_count_as_zero(self):
        c = rules.Career.from_position("HB", rushing_yards=-500, receiving_yards=-1, rushing_touchdowns=-2, games=-5, all_pro=-1)
        self.assertEqual(rules.score(c), 0)

    def test_pro_bowls_are_not_read(self):
        a = rules.Career.from_position("WR", games=200, all_pro=3, receiving_yards=12000, pro_bowl=0)
        b = rules.Career.from_position("WR", games=200, all_pro=3, receiving_yards=12000, pro_bowl=14)
        self.assertEqual(rules.score(a), rules.score(b))
        self.assertEqual(rules.honors_count(b), 17)                           # but the footer's honors byte counts them

    def test_score_never_falls_when_a_count_rises(self):
        rng = random.Random(8)
        names = [f for f in rules.Career.__dataclass_fields__ if f != "group"]
        for _ in range(400):
            base = {n: rng.randrange(0, 12) for n in names}
            base["games"] = rng.randrange(0, 400)
            group = rng.randrange(10)
            before = rules.score(rules.Career(group=group, **base))
            more = dict(base)
            more[rng.choice(names)] += rng.randrange(1, 9)
            self.assertGreaterEqual(rules.score(rules.Career(group=group, **more)), before)

    def test_the_score_saturates_at_a_word_and_32_bit_sums_are_enough(self):
        top = {n: 32767 for n in rules.Career.__dataclass_fields__ if n != "group"}
        for g in range(10):
            c = rules.Career(group=g, **top)
            self.assertEqual(rules.score(c), 0xFFFF)
            self.assertLess(rules.honors_points(c) + rules.games_points(c) + rules.production_points(c), 2 ** 22)
        self.assertEqual(rules.SCORE_MAX, 0xFFFF)

    def test_spot_values_on_real_careers(self):
        spots = {"Peyton Manning": (351, 20, 25, 396), "Brett Favre": (165, 20, 25, 210), "Kurt Warner": (115, 10, 25, 150),
                 "Tom Brady": (267, 20, 25, 312), "J.J. Watt": (170, 17, 25, 212), "Joe Thomas": (150, 21, 0, 171),
                 "Calvin Johnson": (75, 13, 22, 110), "Isaac Bruce": (0, 20, 25, 45), "Shane Lechler": (150, 20, 0, 170),
                 "Adam Vinatieri": (87, 20, 25, 132)}
        for name, (honors, games, production, total) in spots.items():
            parts = rules.score_parts(career(name))
            self.assertEqual((parts["honors"], parts["games"], parts["production"], parts["score"]), (honors, games, production, total), name)


class NativeParityTests(unittest.TestCase):
    def test_golden_vectors_are_stable_and_cover_every_branch(self):
        a, b = rules.golden_vectors(), rules.golden_vectors()
        self.assertEqual(a, b)
        self.assertGreaterEqual(len(a), 50)
        self.assertEqual({v["group"] for v in a}, set(range(10)))
        scores = {v["score"] for v in a}
        self.assertIn(0, scores)
        self.assertTrue(any(s >= rules.BAR for s in scores) and any(rules.FLOOR <= s < rules.BAR for s in scores))
        for v in a:
            c = rules.Career.from_position(v["position"], **v["fields"])
            self.assertEqual(rules.score(c), v["score"])
            self.assertEqual(sum(v["parts"][k] for k in ("honors", "games", "production")), v["score"])

    def test_history_words_sum_back_to_the_career(self):
        for v in rules.golden_vectors():
            c = rules.Career.from_position(v["position"], **v["fields"])
            words = rules.history_words(c)
            self.assertTrue(words[-1] & 0x80000000)
            self.assertFalse(any(w & 0x80000000 for w in words[:-1]))
            back = rules.career_from_words(c.group, words)
            clamp = lambda x: max(x, 0)                                                     # noqa: E731
            self.assertEqual(rules.score(back), v["score"], v["fields"])
            self.assertEqual(back.games, clamp(c.games) if c.games >= 0 else back.games)

    def test_deleted_and_postseason_words_are_ignored(self):
        live = 0x40000000 | (1 << 23) | (rules.FIELD_PASSING_TOUCHDOWNS << 16) | 100
        deleted = live | 0x10000000
        post = live | 0x20000000
        c = rules.career_from_words(0, [live, deleted, post, 0x80000000 | live])
        self.assertEqual(c.passing_touchdowns, 200)

    def test_signed_fields_sum_as_signed_words(self):
        w1 = 0x40000000 | (1 << 23) | (rules.FIELD_RUSHING_YARDS << 16) | (0x10000 - 300)
        w2 = 0x40000000 | (2 << 23) | (rules.FIELD_RUSHING_YARDS << 16) | 1000
        self.assertEqual(rules.career_from_words(7, [w1, w2]).rushing_yards, 700)
        self.assertEqual(rules.career_from_words(7, [w1]).rushing_yards, -300)

    def test_history_words_refuse_what_a_word_cannot_hold(self):
        with self.assertRaises(rules.HofError):
            rules.history_words(Q(passing_touchdowns=40000))

    def test_studio_texts_follow_the_house_rules(self):
        self.assertLessEqual(len(rules.UI_LABEL), 60)
        for text in (rules.UI_LABEL, rules.RULE_HELP, rules.POPUP_TITLE):
            self.assertTrue(text.isascii(), text)
            self.assertNotIn("\u2014", text)
        for number in (str(rules.BAR), str(rules.FLOOR), str(rules.MAX_CLASS), str(rules.MIN_CLASS)):
            self.assertIn(number, rules.RULE_HELP)
        self.assertIn("Pro Bowls", rules.RULE_HELP)

    def test_c_header_carries_the_constants(self):
        text = rules.c_header()
        self.assertIn("HOF_GROUP[17] = {" + ", ".join(map(str, rules.GROUP_OF_POSITION)) + "}", text)
        par = [int(x) for x in re.search(r"HOF_PAR\[10\] = \{([^}]*)\}", text).group(1).split(",")]
        self.assertEqual(par, [rules.PAR.get(g, 0) for g in rules.GROUPS])
        defined = {m.group(1): int(m.group(2)) for m in re.finditer(r"#define HOF_(\w+) (\d+)", text)}
        self.assertEqual(defined["BAR"], rules.BAR)
        self.assertEqual(defined["FLOOR"], rules.FLOOR)
        self.assertEqual(defined["PTS_ALL_PRO"], rules.POINTS["all_pro"])
        self.assertEqual(defined["CANDIDATE_SLOTS"], 64)
        self.assertEqual(defined["GAMES_CAP_LINEMEN"], 35)


# --------------------------------------------------------------------------------------------------------------------
def person(name, pos):
    return champions.pack_person(name, pos)


def cand(name, pos, retired, score, **kw):
    return rules.Candidate(person(name, pos), kw.pop("club", 3), retired, score, kw.pop("seasons", 10), **kw)


class ProcessTests(unittest.TestCase):
    def test_eligibility_window(self):
        c = cand("Tom Brady", "QB", 2022, 312)
        self.assertEqual((rules.first_eligible_season(2022), rules.last_eligible_season(2022)), (2027, 2042))
        self.assertFalse(rules.is_eligible(c, 2026))
        self.assertTrue(rules.is_eligible(c, 2027))
        self.assertTrue(rules.is_eligible(c, 2042))
        self.assertFalse(rules.is_eligible(c, 2043))
        self.assertEqual(rules.class_year(2027), 2028)                         # retired 2022 -> Class of 2028, like the real one

    def test_class_takes_at_most_five_over_the_bar_best_first(self):
        table = rules.empty_table()
        for i in range(8):
            table[i] = cand(f"Player{i}", "WR", 2000, 200 - 10 * i)
        self.assertEqual(rules.select_class(table, 2010), [0, 1, 2, 3, 4])

    def test_class_fills_to_two_from_the_floor(self):
        floor = rules.FLOOR
        table = rules.empty_table()
        table[0] = cand("Aaa One", "QB", 2000, 140)
        table[1] = cand("Bbb Two", "QB", 2000, rules.BAR - 1)
        table[2] = cand("Ccc Three", "QB", 2000, floor)
        table[3] = cand("Ddd Four", "QB", 2000, floor - 1)
        self.assertEqual(rules.select_class(table, 2010), [0, 1])               # one over the bar, one filled from BAR - 1
        table[0] = None
        self.assertEqual(rules.select_class(table, 2010), [1, 2])
        table[1] = None
        self.assertEqual(rules.select_class(table, 2010), [2])                  # only one at the floor or more: a class of one
        table[2] = None
        self.assertEqual(rules.select_class(table, 2010), [])                   # nobody: no class, no pop-up

    def test_ties_break_by_honors_then_seasons_then_earlier_retirement_then_slot(self):
        table = rules.empty_table()
        table[0] = cand("Aaa One", "QB", 2001, 120, honors=5, seasons=10)
        table[1] = cand("Bbb Two", "QB", 2001, 120, honors=6, seasons=10)
        table[2] = cand("Ccc Three", "QB", 2001, 120, honors=6, seasons=12)
        table[3] = cand("Ddd Four", "QB", 2000, 120, honors=6, seasons=12)
        table[4] = cand("Eee Five", "QB", 2000, 120, honors=6, seasons=12)
        table[5] = cand("Fff Six", "QB", 2000, 130, honors=0, seasons=1)
        self.assertEqual(rules.select_class(table, 2012), [5, 3, 4, 2, 1])      # the sixth candidate (slot 0) waits

    def test_not_yet_eligible_and_over_age_candidates_are_skipped(self):
        table = rules.empty_table()
        table[0] = cand("Aaa One", "QB", 2008, 300)                               # retired 2008: eligible 2013..2028
        self.assertEqual(rules.select_class(table, 2012), [])
        self.assertEqual(rules.select_class(table, 2013), [0])
        self.assertEqual(rules.select_class(table, 2028), [0])
        self.assertEqual(rules.select_class(table, 2029), [])

    def test_admit_rules(self):
        table = rules.empty_table()
        self.assertEqual(rules.admit(table, cand("Low Man", "WR", 2020, rules.FLOOR - 1)), "refused")
        x = cand("Aaa One", "WR", 2020, 90)
        self.assertEqual(rules.admit(table, x), "added")
        self.assertEqual(rules.admit(table, x), "refused")                        # the retirement pass ran twice
        self.assertEqual(rules.admit(table, cand("Aaa One", "WR", 2020, 91)), "added")   # a different man, same packing
        self.assertEqual(sum(c is not None for c in table), 2)

    def test_full_table_replaces_only_the_weakest_and_never_grows(self):
        floor = rules.FLOOR
        table = rules.empty_table()
        for i in range(rules.CANDIDATE_SLOTS):
            self.assertEqual(rules.admit(table, cand(f"Pl{i:03d}", "TE", 2020, floor + 1 + i)), "added")
        weak = cand("Weak Man", "TE", 2021, floor)                                 # at the floor, but weaker than everyone
        self.assertEqual(rules.admit(table, weak), "refused")
        strong = cand("Strong Man", "TE", 2021, 500)
        outcome, dropped = rules.admit_detail(table, strong)
        self.assertEqual(outcome, "replaced")
        self.assertEqual(dropped, cand("Pl000", "TE", 2020, floor + 1))           # the weakest is the one dropped
        self.assertEqual(len(table), 64)
        self.assertIn(strong, table)
        self.assertNotIn(dropped, table)
        equal = cand("Equal Man", "TE", 2021, floor + 2)                           # ties: an earlier retirement ranks higher, so a later one loses
        self.assertEqual(rules.admit(table, equal), "refused")

    def test_close_season_order_and_bookkeeping(self):
        table = rules.empty_table()
        old = cand("Old Timer", "OLB", 2006, 150, flags=rules.FLAG_VALID | rules.FLAG_REAL)    # retired 2006: last chance is the 2026 close
        new = cand("Newer Man", "OLB", 2020, 130)
        table[0], table[1] = old, new
        fresh = [cand("Fresh One", "WR", 2025, 110), cand("Too Low", "WR", 2025, 10)]
        result = rules.close_season(table, 2026, fresh)
        self.assertEqual((result.season, result.class_year), (2026, 2027))
        self.assertEqual([i.person for i in result.inductees], [old.person, new.person])
        self.assertEqual(result.sources, [old, new])
        self.assertEqual([i.flags for i in result.inductees], [rules.FLAG_FRANCHISE | rules.FLAG_REAL, rules.FLAG_FRANCHISE])
        self.assertEqual([a for _, a in result.admitted], ["added", "refused"])
        self.assertEqual(result.evicted, [])
        self.assertEqual([c for c in table if c is not None], [fresh[0]])

    def test_over_age_candidate_is_dropped_after_his_last_chance(self):
        def build():
            table = rules.empty_table()
            table[0] = cand("Waiting Man", "OLB", 2006, 90)              # eligible 2011..2026; five stronger candidates keep him out
            for i in range(1, 6):
                table[i] = cand(f"Strong{i}", "QB", 2010, 200 + i)
            return table
        table = build()
        r1 = rules.close_season(table, 2025)
        self.assertEqual((len(r1.inductees), len(r1.expired)), (5, 0))
        self.assertIsNotNone(table[0])                                    # still waiting: 2025 is not his last close
        table = build()
        r2 = rules.close_season(table, 2026)                              # 2006 + 20 is his last close
        self.assertEqual(len(r2.inductees), 5)
        self.assertEqual([c.person for c in r2.expired], [person("Waiting Man", "OLB")])
        self.assertIsNone(table[0])

    def test_one_candidate_at_the_floor_is_still_inducted_alone(self):
        table = rules.empty_table()
        table[0] = cand("Waiting Man", "OLB", 2006, 90)
        result = rules.close_season(table, 2025)
        self.assertEqual([i.score for i in result.inductees], [90])
        self.assertEqual(len(rules.close_season(table, 2026).inductees), 0)

    def test_a_long_run_never_breaks_a_limit(self):
        rng = random.Random(3)
        table = rules.empty_table()
        for season in range(2026, 2126):
            retirees = [cand(f"X{season}{i}", rng.choice(["QB", "WR", "T", "DE"]), season, rng.randrange(0, 200), seasons=rng.randrange(1, 20))
                        for i in range(rng.randrange(0, 12))]
            result = rules.close_season(table, season, retirees)
            self.assertLessEqual(len(result.inductees), rules.MAX_CLASS)
            self.assertEqual(len(table), rules.CANDIDATE_SLOTS)
            self.assertTrue(all(c is None or (c.score >= rules.FLOOR and not season >= rules.last_eligible_season(c.retired))
                                for c in table))
            self.assertTrue(all(i.score >= rules.FLOOR for i in result.inductees))
            over_bar = sum(1 for i in result.inductees if i.score >= rules.BAR)
            self.assertTrue(over_bar == len(result.inductees) or len(result.inductees) <= rules.MIN_CLASS)
            self.assertTrue(all(i.class_year == season + 1 for i in result.inductees))



C_HARNESS = r"""
#include <stdio.h>
int main(void) {
    int cmd;
    while (scanf("%d", &cmd) == 1) {
        if (cmd == 4) {
            unsigned position;
            if (scanf("%u", &position) != 1) return 2;
            printf("%u\n", hof_group_of(position));
        } else if (cmd == 1) {
            HofCareer c; int v[19]; int k;
            for (k = 0; k < 19; k++) if (scanf("%d", &v[k]) != 1) return 2;
            c.group = (unsigned)v[0]; c.games = v[1]; c.mvp = v[2]; c.opoy = v[3]; c.dpoy = v[4]; c.oroy = v[5]; c.droy = v[6];
            c.super_bowl = v[7]; c.super_bowl_mvp = v[8]; c.all_pro = v[9]; c.rushing_title = v[10]; c.passing_touchdowns = v[11];
            c.rushing_touchdowns = v[12]; c.rushing_yards = v[13]; c.receiving_yards = v[14]; c.receiving_touchdowns = v[15];
            c.sacks_half = v[16]; c.interceptions = v[17]; c.field_goals_made = v[18];
            printf("%u\n", hof_score(&c));
        } else {
            HofSlot t[HOF_CANDIDATE_SLOTS], c; int i, n, out[HOF_CANDIDATE_SLOTS]; unsigned season;
            if (scanf("%u", &season) != 1) return 2;
            for (i = 0; i < HOF_CANDIDATE_SLOTS; i++)
                if (scanf("%d %u %u %u %u", &t[i].valid, &t[i].score, &t[i].honors, &t[i].seasons, &t[i].retired) != 5) return 2;
            if (cmd == 2) {
                n = hof_select(t, season, out);
                printf("%d", n); for (i = 0; i < n; i++) printf(" %d", out[i]); printf("\n");
            } else {
                if (scanf("%d %u %u %u %u", &c.valid, &c.score, &c.honors, &c.seasons, &c.retired) != 5) return 2;
                n = hof_admit(t, &c);
                printf("%d", n);
                for (i = 0; i < HOF_CANDIDATE_SLOTS; i++) printf(" %d:%u:%u:%u:%u", t[i].valid, t[i].score, t[i].honors, t[i].seasons, t[i].retired);
                printf("\n");
            }
        }
    }
    return 0;
}
"""


def _c_compiler():
    return shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")


@unittest.skipUnless(_c_compiler(), "no C compiler on this machine")
class CReferenceTests(unittest.TestCase):
    """The generated C (``rules.c_reference``) agrees with this module on fuzzed careers, class selections and admissions."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        base = Path(cls.folder.name)
        (base / "ref.c").write_text(rules.c_reference() + C_HARNESS, encoding="utf-8", newline="\n")
        exe = str(base / ("ref.exe" if os.name == "nt" else "ref"))
        done = subprocess.run([_c_compiler(), "-std=c99", "-O1", "-Wall", "-Wno-unused-const-variable", "-o", exe, str(base / "ref.c")],
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        cls.exe = exe

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def run_c(self, text: str) -> list[str]:
        done = subprocess.run([self.exe], input=text, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip().split("\n")

    FIELDS = ("games", "mvp", "opoy", "dpoy", "oroy", "droy", "super_bowl", "super_bowl_mvp", "all_pro", "rushing_title",
              "passing_touchdowns", "rushing_touchdowns", "rushing_yards", "receiving_yards", "receiving_touchdowns", "sacks_half",
              "interceptions", "field_goals_made")

    def test_score_agrees_on_golden_vectors_and_fuzzed_careers(self):
        cases = []
        for v in rules.golden_vectors():
            cases.append(rules.Career.from_position(v["position"], **v["fields"]))
        rng = random.Random(11)
        for _ in range(3000):
            scale = rng.choice([3, 12, 400, 5000, 32767])
            kw = {f: rng.randrange(-2, scale) if rng.random() < 0.6 else 0 for f in self.FIELDS}
            cases.append(rules.Career(group=rng.randrange(10), **kw))
        lines = [" ".join(["1", str(c.group)] + [str(getattr(c, f)) for f in self.FIELDS]) for c in cases]
        out = self.run_c("\n".join(lines) + "\n")
        self.assertEqual(len(out), len(cases))
        for c, got in zip(cases, out):
            self.assertEqual(int(got), rules.score(c), c)

    def test_builds_under_the_repos_freestanding_32_bit_flags(self):
        gcc = shutil.which("gcc")
        if not gcc:
            self.skipTest("no gcc")
        flags = ["-m32", "-Os", "-ffreestanding", "-fno-builtin", "-fno-strict-aliasing", "-fno-pic", "-fno-pie", "-fno-stack-protector",
                 "-fno-asynchronous-unwind-tables", "-fno-unwind-tables", "-fomit-frame-pointer", "-fno-jump-tables",
                 "-mpreferred-stack-boundary=2", "-mno-sse", "-mno-mmx", "-Wall", "-Wextra", "-Werror"]       # tools/nfl2k5_honors_build.py
        base = Path(self.folder.name)
        (base / "probe.c").write_text("int probe(void) { return 1; }\n", encoding="utf-8", newline="\n")
        if subprocess.run([gcc, "-m32", "-c", str(base / "probe.c"), "-o", str(base / "probe.o")], capture_output=True).returncode != 0:
            self.skipTest("this gcc cannot target 32-bit x86")
        (base / "only.c").write_text(rules.c_reference(), encoding="utf-8", newline="\n")            # no harness, no library header
        done = subprocess.run([gcc, *flags, "-c", str(base / "only.c"), "-o", str(base / "only.o")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertLess((base / "only.o").stat().st_size, 8000)

    def test_group_table_agrees(self):
        out = self.run_c("\n".join(f"4 {p}" for p in range(0, 20)) + "\n")
        self.assertEqual([int(x) for x in out[:17]], list(rules.GROUP_OF_POSITION))
        self.assertEqual([int(x) for x in out[17:]], [255, 255, 255])

    @staticmethod
    def slot_text(c):
        return "0 0 0 0 0" if c is None else f"1 {c.score} {c.honors} {c.seasons} {c.retired}"

    @staticmethod
    def table_from(rng, fill):
        table = rules.empty_table()
        for i in range(rules.CANDIDATE_SLOTS):
            if rng.random() < fill:
                table[i] = rules.Candidate(bytes(7), None, rng.randrange(1996, 2036), rng.randrange(rules.FLOOR - 15, rules.BAR + 60),
                                           rng.randrange(1, 18), honors=rng.randrange(0, 14))
        return table

    def test_class_selection_agrees(self):
        rng = random.Random(21)
        tables, lines = [], []
        for _ in range(1500):
            table = self.table_from(rng, rng.choice([0.05, 0.3, 0.7, 1.0]))
            season = rng.randrange(2002, 2050)
            tables.append((table, season))
            lines.append("2 %d " % season + " ".join(self.slot_text(c) for c in table))
        out = self.run_c("\n".join(lines) + "\n")
        for (table, season), got in zip(tables, out):
            self.assertEqual([int(x) for x in got.split()[1:]], rules.select_class(table, season))
            self.assertEqual(int(got.split()[0]), len(rules.select_class(table, season)))

    def test_admission_agrees_including_full_tables_and_ties(self):
        rng = random.Random(31)
        cases, lines = [], []
        for _ in range(2000):
            table = self.table_from(rng, rng.choice([0.2, 0.9, 1.0, 1.0]))
            if rng.random() < 0.3:                                                # a candidate who ties somebody on three numbers
                taken = [c for c in table if c is not None]
                base = rng.choice(taken) if taken else None
            else:
                base = None
            if base is not None:
                new = rules.Candidate(bytes(7), None, base.retired + rng.choice([-1, 0, 1]), base.score, base.seasons, honors=base.honors)
            else:
                new = rules.Candidate(bytes(7), None, rng.randrange(1996, 2036), rng.randrange(rules.FLOOR - 15, rules.BAR + 60),
                                      rng.randrange(1, 18), honors=rng.randrange(0, 14))
            cases.append((table, new))
            lines.append("3 2030 " + " ".join(self.slot_text(c) for c in table) + " " + self.slot_text(new))
        out = self.run_c("\n".join(lines) + "\n")
        codes = {"added": 1, "replaced": 2, "refused": 0}
        for (table, new), got in zip(cases, out):
            outcome = rules.admit(table, new)
            parts = got.split()
            self.assertEqual(int(parts[0]), codes[outcome])
            self.assertEqual(parts[1:], [self.slot_text(c).replace(" ", ":") if c else "0:0:0:0:0" for c in table])

    def test_a_c_year_by_year_run_matches(self):
        """Thirty years of random retirements: the class close_season picks each year equals the C selection on the same table."""

        rng = random.Random(41)
        table, ctable, lines = rules.empty_table(), [], []
        classes = []
        # Python side only needs to be checked against C one close at a time with the table state copied across
        for season in range(2026, 2056):
            before = list(table)
            lines.append("2 %d " % season + " ".join(self.slot_text(c) for c in before))
            result = rules.close_season(table, season, [
                rules.Candidate(bytes(7), None, season, rng.randrange(rules.FLOOR - 10, 260), rng.randrange(1, 18), honors=rng.randrange(0, 14))
                for _ in range(rng.randrange(0, 9))])
            classes.append([before.index(c) for c in result.sources])
        out = self.run_c("\n".join(lines) + "\n")
        for want, got in zip(classes, out):
            self.assertEqual([int(x) for x in got.split()[1:]], want)


# --------------------------------------------------------------------------------------------------------------------
class RecordTests(unittest.TestCase):
    def test_sizes_and_round_trips(self):
        self.assertEqual((rules.CANDIDATE_ENTRY.size, rules.INDUCTEE_ENTRY.size), (24, 16))
        c = rules.Candidate(person("Tom Brady", "QB"), 21, 2022, 312, 23, rules.FLAG_VALID | rules.FLAG_REAL, (649, 89, 0), 20, 7)
        raw = rules.candidate_to_bytes(c)
        self.assertEqual(len(raw), 24)
        self.assertEqual(rules.candidate_from_bytes(raw), c)
        i = rules.Inductee(c.person, None, 2028, 2022, rules.FLAG_FRANCHISE | rules.FLAG_REAL, 23, 312)
        raw = rules.inductee_to_bytes(i)
        self.assertEqual(len(raw), 16)
        back = rules.inductee_from_bytes(raw)
        self.assertEqual((back.club, back.class_year, back.score, back.flags & 7), (None, 2028, 312, 7))
        self.assertIsNone(rules.candidate_from_bytes(bytes(24)))
        self.assertIsNone(rules.inductee_from_bytes(bytes(16)))

    def test_bad_values_are_refused(self):
        p = person("Tom Brady", "QB")
        for bad in (dict(person=p[:6]), dict(score=70000), dict(club=32), dict(keys=(1, 2)), dict(seasons=300), dict(retired=-1)):
            kw = dict(person=p, club=1, retired=2020, score=100)
            kw.update(bad)
            with self.assertRaises(rules.HofError):
                rules.Candidate(**kw)
        with self.assertRaises(rules.HofError):
            rules.candidate_from_bytes(b"\0" * 23)

    def test_byte_compatible_with_the_footer_hall_block_when_it_is_present(self):
        try:
            from mod_editor.core import nfl2k5_franchise_extension as ext
        except ImportError:
            self.skipTest("nfl2k5_franchise_extension (job j23) is not in this branch")
        rng = random.Random(5)
        for _ in range(200):
            who = ext.pack_person(rng.choice(["Tom", "J.J.", "Odell"]), rng.choice(["Brady", "Watt", "Beckham"]), rng.randrange(17))
            club = rng.choice([None] + list(range(32)))
            keys = tuple(rng.randrange(65536) for _ in range(3))
            args = dict(retired=rng.randrange(1999, 2090), score=rng.randrange(0, 600), seasons=rng.randrange(1, 40))
            flags = rng.choice([1, 3, 5, 7])
            honors, rings = rng.randrange(256), rng.randrange(8)
            theirs = ext.candidate_entry(who, club, args["retired"], score=args["score"], seasons=args["seasons"], flags=flags, keys=keys,
                                         honors=honors, sb_wins=rings)
            mine = rules.candidate_to_bytes(rules.Candidate(who, club, args["retired"], args["score"], args["seasons"], flags, keys, honors, rings))
            self.assertEqual(theirs, mine)
            self.assertEqual(ext.inductee_entry(who, club, 2031, args["retired"], flags=flags, seasons=args["seasons"], score=args["score"]),
                             rules.inductee_to_bytes(rules.Inductee(who, club, 2031, args["retired"], flags, args["seasons"], args["score"])))
        self.assertEqual((ext.HALL_INDUCTEES, ext.HALL_CANDIDATES, ext.INDUCTEE_ENTRY, ext.CANDIDATE_ENTRY),
                         (rules.INDUCTEE_SLOTS, rules.CANDIDATE_SLOTS, 16, 24))


class PopupTests(unittest.TestCase):
    def inductees(self, names):
        return [rules.Inductee(person(n, p), c, 2031, 2025, rules.FLAG_FRANCHISE, 12, 150) for n, p, c in names]

    def test_one_notice_for_up_to_three_names(self):
        ins = self.inductees([("Tom Brady", "QB", 6), ("J.J. Watt", "DE", 28), ("Zack Martin", "G", 11)])
        texts = rules.popup_texts(2031, ins)
        self.assertEqual(texts, ["Hall of Fame Class of 2031\nT. BRADY, QB, Buccaneers\nJ. WATT, DE, Steelers\nZ. MARTIN, G, Cowboys"])

    def test_five_names_make_two_notices(self):
        ins = self.inductees([("Tom Brady", "QB", 6), ("J.J. Watt", "DE", 28), ("Zack Martin", "G", 11), ("Jason Kelce", "C", 13),
                              ("Justin Tucker", "K", 24)])
        texts = rules.popup_texts(2031, ins)
        self.assertEqual(len(texts), 2)
        self.assertTrue(texts[0].startswith("Hall of Fame Class of 2031 (1 of 2)\n"))
        self.assertTrue(texts[1].startswith("Hall of Fame Class of 2031 (2 of 2)\n"))
        self.assertEqual([t.count("\n") for t in texts], [3, 2])

    def test_empty_class_has_no_notice(self):
        self.assertEqual(rules.popup_texts(2031, []), [])

    def test_lines_fit_the_dialog_and_are_plain_ascii(self):
        longest = [("Christopher Hubbardwilliams", "OLB", 21), ("Q. Ng", "DE", 0), ("Odell Beckham Jr.", "WR", 15)]
        for texts in (rules.popup_texts(2031, self.inductees(longest)), rules.popup_texts(2031, self.inductees(longest), per_notice=1)):
            for text in texts:
                lines = text.split("\n")
                self.assertLessEqual(len(lines), 4)
                for line in lines:
                    self.assertLessEqual(len(line), rules.POPUP_LINE_MAX, line)
                    self.assertTrue(line.isascii(), line)
                    self.assertNotIn("\u2014", line)
                    self.assertNotIn("\u2013", line)

    def test_position_labels_can_follow_the_builds_rename(self):
        labels = tuple("RB" if p == "HB" else p for p in rules.POSITIONS)
        ins = self.inductees([("Adrian Peterson", "HB", 27)])
        self.assertIn("A. PETERSON, RB, Seahawks", rules.popup_texts(2027, ins, position_labels=labels)[0])
        self.assertIn("A. PETERSON, HB, Seahawks", rules.popup_texts(2027, ins)[0])

    def test_unknown_club_is_left_out(self):
        ins = self.inductees([("Tom Brady", "QB", None)])
        self.assertEqual(rules.popup_texts(2031, ins)[0].split("\n")[1], "T. BRADY, QB")


# --------------------------------------------------------------------------------------------------------------------
class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "data" / "nfl2k5_hof_calibration_2026.json").read_text(encoding="utf-8"))

    def test_schema_columns_and_sources(self):
        d = self.data
        self.assertEqual(d["schema"], "nfl2k5_hof_calibration/v1")
        self.assertEqual(d["columns"], list(TOOL.COLUMNS))
        self.assertTrue(all(len(r) == len(d["columns"]) for r in d["rows"]))
        self.assertEqual(d["counts"]["rows"], len(d["rows"]))
        for key, pin in d["sources"].items():
            self.assertRegex(pin["sha256"], r"^[0-9a-f]{64}$", key)
        self.assertEqual(set(d["sources"]), {f"wiki:{k}" for k in TOOL.PINS_WIKI} | {f"nflverse:{k}" for k in TOOL.PINS_NFLVERSE})
        self.assertIn("CC-BY-4.0", d["attribution"])
        for key in ("hof_list", "mvp", "opoy", "dpoy", "roy", "rushing", "sbmvp", "sbchamps"):
            self.assertIn(f"wiki:{key}", d["sources"])
        self.assertEqual(sum(1 for k in d["sources"] if k.startswith("wiki:allpro_")), 27)
        self.assertEqual(sum(1 for k in d["sources"] if k.startswith("nflverse:stats_player_reg_")), 27)

    def test_pins_in_the_dataset_equal_the_tools_pins(self):
        for key, pin in TOOL.PINS_WIKI.items():
            self.assertEqual(self.data["sources"][f"wiki:{key}"]["sha256"], pin["sha256"])
            self.assertIn(str(pin["revision"]), self.data["sources"][f"wiki:{key}"]["url"])
        for key, pin in TOOL.PINS_NFLVERSE.items():
            self.assertEqual(self.data["sources"][f"nflverse:{key}"]["sha256"], pin["sha256"])

    def test_the_honors_pins_are_the_same_pages_the_game_seeds_use(self):
        honors = json.loads((ROOT / "data" / "nfl2k5_honors_2026.json").read_text(encoding="utf-8"))["sources"]
        for key, name in (("wiki_mvp", "mvp"), ("wiki_opoy", "opoy"), ("wiki_dpoy", "dpoy"), ("wiki_roy", "roy"),
                          ("wiki_rushing", "rushing"), ("wiki_sbmvp", "sbmvp"), ("wiki_sbchamps", "sbchamps")):
            self.assertEqual(honors[key]["sha256"], TOOL.PINS_WIKI[name]["sha256"], name)
            self.assertEqual(honors[key]["revision"], TOOL.PINS_WIKI[name]["revision"], name)
        for season in range(2005, 2026):
            for kind in ("allpro", "probowl"):
                self.assertEqual(honors[f"wiki_{kind}_{season}"]["sha256"], TOOL.PINS_WIKI[f"{kind}_{season}"]["sha256"], (kind, season))

    def test_rows_are_sane(self):
        seen = set()
        for r in ROWS:
            self.assertIn(r["group"], rules.GROUPS)
            self.assertTrue(1999 <= r["last"] <= 2025, r)
            self.assertTrue(r["hof"] == 0 or 1963 <= r["hof"] <= 2026)
            self.assertEqual(r["active"], 0)
            self.assertEqual(rules.score(TOOL.rows_career(r)) >= TOOL.KEEP_SCORE or TOOL.is_notable(r) or bool(r["hof"]), True, r["name"])
            key = (r["name"], r["last"], r["gsis"] or r["first"])
            self.assertNotIn(key, seen)
            seen.add(key)

    def test_excluded_retirees_cannot_reach_the_floor(self):
        counts = self.data["counts"]
        self.assertEqual(counts["excluded_max_score"], 39)
        self.assertLess(counts["excluded_max_score"], rules.FLOOR)
        self.assertEqual(counts["retired_2005_2019_excluded"], 5057)
        in_range = [r for r in ROWS if 2005 <= r["last"] <= 2019]
        self.assertEqual(len(in_range) + counts["retired_2005_2019_excluded"], 5399)


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.report = TOOL.evaluate(ROWS)

    def test_real_inductees_in_range_come_from_two_agreeing_sources(self):
        members = [r for r in ROWS if r["hof"] and 2005 <= r["last"] <= 2019]
        self.assertEqual(len(members), 55)
        self.assertEqual(sorted(r["hof"] for r in members)[:3], [2011, 2011, 2012])
        self.assertEqual(sorted(r["hof"] for r in members)[-3:], [2025, 2026, 2026])
        self.assertEqual(len([r for r in members if r["src"] == "stats_player"]), 3)       # Warner, Gates, Vinatieri (never drafted)
        self.assertEqual({r["name"] for r in members if r["src"] == "stats_player"}, {"Kurt Warner", "Antonio Gates", "Adam Vinatieri"})

    def test_acceptance_at_least_80_percent_of_inductees_and_at_most_10_percent_of_peers(self):
        e = self.report
        for key in ("recall", "recall_train", "recall_test"):
            passed, total = e[key]
            self.assertGreaterEqual(passed / total, TOOL.TARGET_RECALL, key)
        for key in ("false_positives", "false_positives_train", "false_positives_test"):
            passed, total = e[key]
            self.assertLessEqual(passed / total, TOOL.TARGET_FPR, key)

    def test_the_numbers_the_report_quotes(self):
        e = self.report
        self.assertEqual((e["bar"], e["inductees"], e["notable_non_inductees"]), (100, 55, 239))
        self.assertEqual((e["recall"], e["recall_train"], e["recall_test"]), ((47, 55), (30, 36), (17, 19)))
        self.assertEqual((e["false_positives"], e["false_positives_train"], e["false_positives_test"]), ((12, 239), (5, 126), (7, 113)))
        self.assertEqual([m[0] for m in e["misses"]], ["Orlando Pace", "Curtis Martin", "John Lynch", "Andre Johnson", "Devin Hester",
                                                       "Will Shields", "Bryant Young", "Isaac Bruce"])
        self.assertEqual({m[0] for m in e["false_positive_names"]},
                         {"Shane Lechler", "Kevin Williams", "Jahri Evans", "Priest Holmes", "James Harrison", "NaVorro Bowman",
                          "Earl Thomas", "Shaun Alexander", "Mike Alstott", "Willie Anderson", "Rodney Harrison", "Terrell Suggs"})
        self.assertEqual(e["by_group"], {"QB": (3, 3), "RB": (4, 5), "WR": (4, 6), "TE": (2, 2), "OL": (8, 10), "DL": (7, 8), "LB": (8, 8),
                                         "DB": (9, 11), "K": (2, 2)})

    def test_no_other_retiree_passes(self):
        others = [r for r in ROWS if 2005 <= r["last"] <= 2019 and not r["hof"] and not TOOL.is_notable(r)]
        self.assertEqual(len(others), 48)
        self.assertEqual(sum(rules.score(TOOL.rows_career(r)) >= rules.BAR for r in others), 0)

    def test_the_search_code_scores_exactly_like_the_rule(self):
        for r in ROWS:
            c = TOOL.rows_career(r)
            self.assertEqual(TOOL.score_with(c, TOOL.DEFAULT_PARAMS), rules.score(c), r["name"])

    def test_sensitivity_plateau(self):
        table = TOOL.sensitivity(ROWS)
        base = table[0]
        self.assertEqual((base["recall"], base["fp"]), ((47, 55), (12, 239)))
        for row in table[1:]:
            if row["parameter"] in ("ap", "pcap"):
                continue
            self.assertLessEqual(abs(row["delta_recall"]), 1, row)
            self.assertLessEqual(abs(row["delta_fp"]), 2, row)
        ap = [r for r in table if r["parameter"] == "ap"]
        self.assertTrue(any(abs(r["delta_recall"]) >= 5 for r in ap))

    def test_the_shipped_set_is_in_the_feasible_region_of_the_search(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy is not installed")
        out = TOOL.search(ROWS, samples=1500)
        self.assertTrue(out["shipped_feasible"])
        self.assertGreater(out["feasible"], 50)
        self.assertEqual(tuple(out["shipped"]["recall"]), (47, 55))
        again = TOOL.search(ROWS, samples=1500)
        self.assertEqual(out["feasible"], again["feasible"])                            # reproducible


class ReplayTests(unittest.TestCase):
    def test_real_classes_are_two_to_five_every_year(self):
        out = TOOL.real_replay(ROWS, 2010, 2026)
        self.assertEqual(sorted(out["classes"]), list(range(2010, 2027)))
        self.assertTrue(all(2 <= len(v) <= 5 for v in out["classes"].values()), out["sizes"])
        self.assertEqual(out["sizes"], {2: 3, 3: 1, 4: 6, 5: 7})
        self.assertEqual((out["inductees"], out["real_members"]), (68, 52))

    def test_a_class_is_the_same_whatever_year_the_caller_starts_at(self):
        a = TOOL.real_replay(ROWS, 2010, 2026)["classes"]
        b = TOOL.real_replay(ROWS, 2020, 2026)["classes"]
        for y in range(2020, 2027):
            self.assertEqual([r["name"] for r in a[y]], [r["name"] for r in b[y]])

    def test_a_few_real_classes(self):
        classes = TOOL.real_replay(ROWS, 2010, 2026)["classes"]
        names = lambda y: [r["name"] for r in classes[y]]                      # noqa: E731
        self.assertEqual(names(2018), ["Ray Lewis", "Brian Urlacher", "Randy Moss", "Steve Hutchinson", "Ronde Barber"])
        self.assertEqual(names(2021)[0], "Peyton Manning")
        self.assertEqual(names(2025)[:2], ["Luke Kuechly", "Adam Vinatieri"])
        self.assertEqual(names(2026)[0], "Drew Brees")

    def test_franchise_classes_from_the_real_retirees_nobody_has_judged(self):
        out = TOOL.franchise_replay(ROWS, 2036)
        names = lambda y: [r["name"] for r in out["classes"][y]]               # noqa: E731
        self.assertEqual(names(2027), ["Adrian Peterson", "Rob Gronkowski", "Antonio Brown", "Richard Sherman", "Cam Newton"])
        self.assertEqual(names(2028), ["Tom Brady", "J.J. Watt", "Ndamukong Suh", "Matt Ryan"])
        for y in range(2027, 2032):
            self.assertTrue(2 <= len(names(y)) <= 5, y)
        all_names = {n for y in out["classes"] for n in names(y)}
        self.assertNotIn("Aaron Donald", all_names)                           # he has a 2026 roster row (ACT): not retired
        self.assertTrue(all(not r["hof"] and r["last"] >= TOOL.SEED_FIRST_RETIRED for v in out["classes"].values() for r in v))
        self.assertEqual(out["left"], [])

    def test_seed_candidates(self):
        doc = TOOL.seed_document(ROWS)
        self.assertEqual(doc["schema"], "nfl2k5_hof_candidates/v1")
        self.assertEqual(doc["count"], len(doc["candidates"]))
        self.assertEqual(doc["count"], 27)
        self.assertLessEqual(doc["count"], rules.CANDIDATE_SLOTS)
        names = [c["name"] for c in doc["candidates"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names[:3], ["Tom Brady", "Adrian Peterson", "J.J. Watt"])
        for c in doc["candidates"]:
            self.assertGreaterEqual(c["score"], rules.FLOOR)
            self.assertEqual(c["eligible_class"], c["retired"] + 6)
            self.assertGreaterEqual(c["retired"], 2021)
            self.assertRegex(c["birth_date"], r"^\d{4}-\d{2}-\d{2}$")
            entry = rules.candidate_from_bytes(bytes.fromhex(c["candidate_hex"]))
            self.assertEqual((entry.score, entry.retired, entry.flags & 3), (c["score"], c["retired"], 3))
            self.assertEqual(entry.club, c["club_index"])
        brady = next(c for c in doc["candidates"] if c["name"] == "Tom Brady")
        self.assertEqual((brady["eligible_class"], brady["score"], brady["club"]), (2028, 312, "Buccaneers"))

    def test_checked_in_candidates_file_matches_the_tool(self):
        path = ROOT / "data" / "nfl2k5_hof_candidates_2026.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), json.loads(json.dumps(TOOL.seed_document(ROWS))))

    def test_seeds_fit_the_table_with_room_for_the_next_retirees(self):
        table = rules.empty_table()
        for c in TOOL.seed_document(ROWS)["candidates"]:
            self.assertEqual(rules.admit(table, rules.candidate_from_bytes(bytes.fromhex(c["candidate_hex"]))), "added")
        self.assertLessEqual(sum(x is not None for x in table), rules.CANDIDATE_SLOTS - 30)         # room for 30 more


# --------------------------------------------------------------------------------------------------------------------
HOF_LIST = """== Inductees ==
{| class="wikitable" style="font-size:smaller"
|-
! Key
|}
{| class="wikitable sortable" style="text-align:left; font-size:100%; line-height:17px; width:100%;"
|+ Biographies
! Inductee
! Class
! Position
! Team(s)
! Years
|-style="border-top: 2px solid gray"
| rowspan=2|{{sortname|Herb|Adderley}} ||rowspan=2| 1980 || rowspan=2 data-sort-value="Cornerback 1980"|Cornerback|| [[Green Bay Packers]]|| 1961&ndash;1969
|-style="border-bottom: 2px solid gray"
| [[Dallas Cowboys]] || 1970&ndash;1972
|-style="border-top: 2px solid gray"
| style="background:#D4EDFF"|{{sortname|Troy|Aikman}}'''**''' || 2006 || data-sort-value="Quarterback 2006"| Quarterback || [[Dallas Cowboys]] || 1989&ndash;2000
|-style="border-top: 2px solid gray"
|{{sortname|Adam|Vinatieri}} || 2026 || data-sort-value="Placekicker 2026"| Placekicker || [[New England Patriots]] || 1996&ndash;2005
|-
| [[Indianapolis Colts]] || 2006&ndash;2019
|}
== Inductees who have played for non-NFL teams ==
{| class="wikitable sortable"
|-style="border-top: 2px solid gray"
| {{sortname|Not|Counted}} || 1999 || data-sort-value="Guard 1999"|Guard || X || 1920&ndash;1925
|}
"""

ALLPRO = """==Teams==
{| border=0
|- valign="top"
|
{| class="wikitable"
! colspan=3 | Offense
|-
!Position
!First team
!Second team
|-
|align=center|[[Quarterback]]
|[[Peyton Manning]], [[Indianapolis Colts]] (AP, PFWA, TSN)
| [[Tom Brady]], [[New England Patriots]] (AP-2)
|-
|align=center|[[Running back]]
| [[Tiki Barber]], [[New York Giants]] (AP, PFWA) <BR> [[Shaun Alexander]], [[Seattle Seahawks]] (AP, PFWA, TSN) <BR> [[LaDainian Tomlinson]], [[San Diego Chargers]] (TSN)
|[[Larry Johnson (American football)|Larry Johnson]], [[Kansas City Chiefs]] (AP-2) <BR> LaDainian Tomlinson, San Diego Chargers (AP-2)
|-
|align=center|[[Guard (American football)|Guard]]
| [[Alan Faneca]], [[Pittsburgh Steelers]] (AP, PFWA, TSN) <BR> [[Brian Waters]], Kansas City Chiefs (AP-t) <BR> [[Steve Hutchinson (American football)|Steve Hutchinson]], Seattle Seahawks (AP-t, PFWA, TSN)
| <BR> [[Will Shields]], Kansas City Chiefs (AP-2)
|-
|align=center|[[Offensive backfield|Flex]]
|[[Shaun Alexander]], Seattle Seahawks (AP)
|none
|-
|}
"""

OPOY = """|-
|[[2013 NFL season|2013]]
!scope="row"|{{sortname|Peyton|Manning}} {{small|(2)}}
|[[Quarterback]]||[[Denver Broncos]]||<ref>cite</ref>
|-
|[[2014 NFL season|2014]]
!scope="row"|{{sortname|DeMarco|Murray}}
|[[Running back]]||[[Dallas Cowboys]]||<ref>cite</ref>
|-
|[[1985 NFL season|1985]]
!scope="row"|{{sortname|Marcus|Allen}}
"""

DPOY = """{| class="wikitable"
|-
| {{center|[[2012 NFL season|2012]]}} ||style="background:#ffb;"| [[J. J. Watt]] ||align="center"|[[Defensive end|DE]] || [[2012 Houston Texans season|Houston]]
|-
| {{center|[[1990 NFL season|1990]]}} ||style="background:#ffb;"| [[Bruce Smith (defensive end)|Bruce Smith]] ||align="center"|[[Defensive end|DE]] || x
|}
"""

ROY = """==Winners==
===Offensive===
{| class="wikitable"
|-
| [[2015 NFL season|2015]]
!scope="row"|{{sortname|Todd|Gurley}}
|[[Running back]] || x
|-
===Defensive===
{| class="wikitable"
|-
| [[2015 NFL season|2015]]
!scope="row"|{{sortname|Marcus|Peters}}
|[[Cornerback]] || x
|-
"""

PROBOWL_FILLER = "\n".join("* {{NFLplayer|%d| Filler%03d Player | ([[Some Team]])}}" % (i, i) for i in range(80))
PROBOWL = """==Game format==
text
==Rosters==
===Team Rice===
'''[[Quarterbacks]]'''
* {{NFLplayer|&nbsp;4| Derek Carr |d=American football | ([[Oakland Raiders]])}}{{ref label|replacement|a|a}}
* {{NFLplayer|10| Eli Manning | ([[New York Giants]])}}
'''[[Running back|Running Backs]]'''
* {{Small|28}} [[Adrian Peterson]], [[Minnesota Vikings|Minnesota]]
* [[Joe Thomas (offensive tackle)|Joe Thomas]] ([[Cleveland Browns]])
""" + PROBOWL_FILLER + """
==Number of selections per team==
* Nobody Here
"""


class ParserTests(unittest.TestCase):
    def test_name_normalisation(self):
        n = TOOL.norm_name
        self.assertEqual(n("T. J. Watt"), n("T.J. Watt"))
        self.assertEqual(n("Odell Beckham Jr."), n("Odell Beckham"))
        self.assertEqual(n("Kenneth Walker III"), "kennethwalker")
        self.assertEqual(n("Jos\u00e9 Alvarez"), "josealvarez")

    def test_hall_of_fame_table(self):
        rows = TOOL.parse_hof_list(HOF_LIST)
        self.assertEqual([(r["first"], r["last"], r["class"], r["position"], r["first_season"], r["last_season"]) for r in rows],
                         [("Herb", "Adderley", 1980, "Cornerback", 1961, 1972), ("Troy", "Aikman", 2006, "Quarterback", 1989, 2000),
                          ("Adam", "Vinatieri", 2026, "Placekicker", 1996, 2019)])

    def test_award_tables(self):
        self.assertEqual(TOOL.parse_award_seasons(OPOY), {2013: ["Peyton Manning"], 2014: ["DeMarco Murray"]})       # 1985 is before 1990
        self.assertEqual(TOOL.parse_award_seasons(OPOY, lo=1980)[1985], ["Marcus Allen"])
        self.assertEqual(TOOL.parse_dpoy(DPOY), {2012: ["J. J. Watt"], 1990: ["Bruce Smith"]})
        off, dfn = TOOL.parse_roy(ROY)
        self.assertEqual((off, dfn), ({2015: ["Todd Gurley"]}, {2015: ["Marcus Peters"]}))

    def test_all_pro_first_team_counts_ap_and_ap_t_only(self):
        names = TOOL.parse_allpro_first_team(ALLPRO)
        self.assertEqual(names, ["Alan Faneca", "Brian Waters", "Peyton Manning", "Shaun Alexander", "Steve Hutchinson", "Tiki Barber"])
        self.assertNotIn("LaDainian Tomlinson", names)                          # a Sporting News-only pick
        self.assertNotIn("Tom Brady", names)                                     # second team

    def test_pro_bowl_roster_presence(self):
        blob = TOOL.pro_bowl_blob(PROBOWL)
        for name in ("Derek Carr", "Eli Manning", "Adrian Peterson", "Joe Thomas"):
            self.assertIn(TOOL.norm_name(name), blob, name)
        self.assertNotIn(TOOL.norm_name("Nobody Here"), blob)

    def test_pinned_pages_are_named_by_revision(self):
        pin = TOOL.PINS_WIKI["hof_list"]
        self.assertIn(f"oldid={pin['revision']}", TOOL.wiki_url(pin))
        self.assertTrue(TOOL.wiki_url(pin).endswith("&action=raw"))
        self.assertEqual(len(TOOL.source_files()), len(TOOL.PINS_WIKI) + len(TOOL.PINS_NFLVERSE))


class ToolTests(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = TOOL.main(list(argv))
        return code, out.getvalue()

    def test_evaluate_and_replay_commands(self):
        code, text = self.run_cli("evaluate")
        self.assertEqual(code, 0)
        self.assertIn("inductees that pass: 47/55 = 85.5%", text)
        self.assertIn("notable non-inductees that pass: 12/239 = 5.0%", text)
        code, text = self.run_cli("replay", "--from", "2024", "--to", "2026")
        self.assertEqual(code, 0)
        self.assertIn("2026 [3] Drew Brees", text)
        code, text = self.run_cli("franchise", "--to", "2029")
        self.assertIn("2028 [4] Tom Brady", text)

    def test_candidates_command_is_deterministic(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.json", Path(folder) / "b.json"
            self.assertEqual(self.run_cli("candidates", "--out", str(a))[0], 0)
            self.assertEqual(self.run_cli("candidates", "--out", str(b))[0], 0)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(a.read_bytes(), (ROOT / "data" / "nfl2k5_hof_candidates_2026.json").read_bytes())
            self.assertNotIn(b"\r\n", a.read_bytes())

    def test_check_cache_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            code, text = self.run_cli("check-cache", "--cache", folder)
            self.assertEqual(code, 1)
            state = json.loads(text)
            self.assertEqual(state["ok"], 0)
            self.assertEqual(len(state["missing"]), len(TOOL.source_files()))

    def test_a_text_that_does_not_match_its_pin_stops_the_build(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            for name in TOOL.source_files():
                (cache / name).write_bytes(b"not the pinned text")
            state = TOOL.check_cache(cache)
            self.assertEqual(len(state["bad"]), len(TOOL.source_files()))
            with self.assertRaises(TOOL.CalibrationError):
                TOOL.build_dataset(cache)


@unittest.skipUnless(os.environ.get("B780_HN1_RUNS"), "set B780_HN1_RUNS to the hn1 runs folder (rel301.json .. rel310.json)")
class SimProxyTests(unittest.TestCase):
    def test_franchise_career_regime(self):
        out = TOOL.sim_proxy(Path(os.environ["B780_HN1_RUNS"]))
        self.assertEqual({n: (v["at_bar"], v["at_floor"]) for n, v in out.items()}, {5: (4, 11), 8: (13, 22), 10: (17, 31)})
        self.assertEqual(set(out[10]["production_scale"].values()) - {16, 17}, set())
        self.assertEqual(out[10]["production_scale"]["rushing x1.3"], 17)


@unittest.skipUnless(os.environ.get("B780_HOF_CACHE"), "set B780_HOF_CACHE to a folder filled by `b780_hof_calibrate.py fetch`")
class RebuildTests(unittest.TestCase):
    def test_the_dataset_rebuilds_byte_for_byte_from_the_pinned_sources(self):
        cache = Path(os.environ["B780_HOF_CACHE"])
        self.assertEqual(TOOL.check_cache(cache)["bad"], [])
        data = TOOL.build_dataset(cache)
        text = json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n"
        self.assertEqual(text.encode("utf-8"), (ROOT / "data" / "nfl2k5_hof_calibration_2026.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
