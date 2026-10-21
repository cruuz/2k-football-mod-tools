"""Variety of the automatic CPU coach's play rings (b776 job pb2).

Synthetic menus cover the rules and determinism with no private data. The real-book checks run when
NFL2K5_COACH_AI_IMAGE names a disc (any disc with the 32 team books; the books' own coach tags are stripped first)."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import random
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_coach_ai as ai  # noqa: E402
from mod_editor.core import nfl2k5_coach_diversity as dv  # noqa: E402
from mod_editor.core import nfl2k5_formation_menu_pages as pages  # noqa: E402
from mod_editor.core import nfl2k5_vip as vip  # noqa: E402

FAMILIES = ("Inside Zone", "Outside Zone", "Counter", "Power", "Draw", "Toss", "Iso", "Duo")
PASSES = ("Mesh", "Flood", "Smash", "Dagger", "Drive", "Spacing", "Bench", "Snag", "Slant Flat", "Double Slants",
          "Y Cross", "Post Wheel")


def menu():
    """A synthetic callable menu: 12 formations; runs in four lanes and two stances, passes in a few classes."""
    out, play = [], 0
    for formation in range(12):
        gun = formation % 2 == 1
        for i, family in enumerate(FAMILIES):
            lane = vip.RUN_LANES[(formation + i) % 5]
            out.append(vip.Choice(formation, play, False, gun, f"F{formation}", family, run_location=lane.split("_")[0],
                                  run_lane=lane, concept=dv.play_family(family), target="HB:C"))
            play += 1
        for i, family in enumerate(PASSES):
            out.append(vip.Choice(formation, play, True, gun, f"F{formation}", family, play_action=i % 4 == 0,
                                  deep_primary=i % 3 == 0, concept=dv.play_family(family),
                                  target=("WR:L", "WR:R", "TE:R", "HB:L")[i % 4]))
            play += 1
        out.append(vip.Choice(formation, play, True, gun, f"F{formation}", "Bubble Screen", screen=True,
                              deep_primary=False, concept="bubble screen", target="WR:L"))
        play += 1
        out.append(vip.Choice(formation, play, True, gun, f"F{formation}", "RB Screen", screen=True,
                              deep_primary=False, concept="rb screen", target="HB:R"))
        play += 1
    return tuple(c for c in out if c.play <= 255)


def staple_rings(choices, pools=20):
    """Every pool holds the same look-alike staples: the failure this job fixes."""
    first = [c for c in choices if not c.passed and not c.shotgun][:2]
    passes = [c for c in choices if c.passed and not c.screen and c.shotgun][:3]
    screens = [c for c in choices if c.screen and c.shotgun][:2]
    same_family = [c for c in choices if c.concept == "counter" and not c.shotgun][:1]
    ring = first + passes + screens + same_family
    return [list(ring) for _ in range(pools)]


class FamilyNames(unittest.TestCase):
    def test_family_ignores_team_numbers_and_direction(self):
        self.assertEqual(dv.play_family("CHI Post Wheel"), "post wheel")
        self.assertEqual(dv.play_family("Strong Counter"), dv.play_family("Weak Counter"))
        self.assertEqual(dv.play_family("90 TE Speed Out"), "te speed out")
        self.assertNotEqual(dv.play_family("PA Boot"), dv.play_family("Boot"))
        self.assertEqual(dv.play_family("Left"), "left")  # a name made only of direction words is kept
        self.assertEqual(dv.play_family(""), "")

    def test_situational_pools_follow_the_projected_pool_formula(self):
        from mod_editor.core import nfl2k5_coach_tendencies as t
        row = dict(down=3, ydstogo=8, yardline_100=50, qtr=4, half_seconds_remaining=60)
        for score, group in ((7, dv.URGENT_LEADING), (-7, dv.URGENT_TRAILING_OR_TIED), (0, dv.URGENT_TRAILING_OR_TIED)):
            pool = t.projected_pool(dict(row, score_differential=score))
            self.assertIn(pool, dv.URGENT_POOLS)
            self.assertIn(pool, group)
        self.assertNotIn(t.projected_pool(dict(row, score_differential=0, half_seconds_remaining=600)),
                         dv.URGENT_POOLS)


class RingSetMath(unittest.TestCase):
    def test_incremental_delta_equals_recomputed_cost(self):
        choices = menu()
        rng = random.Random(7)
        rings = [rng.sample(choices, 8) for _ in range(6)]
        pen = dv.situational_penalty()
        state = dv.RingSet(rings, dv.offense_spec(), pen)
        for _ in range(300):
            i, slot = rng.randrange(6), rng.randrange(8)
            candidate = rng.choice(choices)
            predicted = state.delta(i, rings[i][slot], candidate)
            before = state.total()
            state.replace(i, slot, candidate)
            self.assertAlmostEqual(state.total() - before, predicted, places=6)
        fresh = dv.RingSet(rings, dv.offense_spec(), pen)
        self.assertAlmostEqual(fresh.total(), state.total(), places=6)
        self.assertEqual(fresh.hard_violations(), state.hard_violations())


class ImproveOffense(unittest.TestCase):
    def setUp(self):
        self.choices = menu()
        self.pools = [dict(index=i, choices=[vars(c) for c in ring]) for i, ring in enumerate(staple_rings(self.choices))]

    def run_variety(self):
        pools = copy.deepcopy(self.pools)
        report = vip.diversify_pools(pools, self.choices, None)
        return pools, report

    def test_hard_rules_hold_and_marginals_do_not_move(self):
        before = [[vip.Choice(**c) for c in p["choices"]] for p in self.pools]
        pools, report = self.run_variety()
        after = [[vip.Choice(**c) for c in p["choices"]] for p in pools]
        self.assertEqual(report["hard_violations"], 0)
        for old, new in zip(before, after):
            self.assertEqual(vip.choice_metrics(new), vip.choice_metrics(old))
            self.assertEqual(sorted(c.category for c in new), sorted(c.category for c in old))
            self.assertEqual(len(new), 8)
            self.assertEqual(len({(c.formation, c.play) for c in new}), 8)
            self.assertLessEqual(max(c.play for c in new), 255)
            metrics = dv.ring_metrics(new)
            self.assertEqual(metrics["repeated_formation_family"], 0)
            self.assertLessEqual(metrics["screens"], 2)
            self.assertLessEqual(metrics["screen_families"] if metrics["screens"] == 2 else 1, 2)
            self.assertEqual(metrics["adjacent_screens"], 0)

    def test_screens_are_separate_families_never_adjacent(self):
        pools, _ = self.run_variety()
        for pool in pools:
            ring = [vip.Choice(**c) for c in pool["choices"]]
            screens = [c for c in ring if c.screen]
            self.assertEqual(len({c.concept for c in screens}), len(screens))
            for i, c in enumerate(ring):
                self.assertFalse(c.screen and ring[(i + 1) % 8].screen)

    def test_pools_spread_over_the_menu(self):
        before = dv.pool_metrics([[vip.Choice(**c) for c in p["choices"]] for p in self.pools])
        pools, report = self.run_variety()
        after = dv.pool_metrics([[vip.Choice(**c) for c in p["choices"]] for p in pools])
        self.assertEqual(before["distinct_pairs"], 8)
        self.assertGreater(after["distinct_pairs"], 4 * before["distinct_pairs"])
        self.assertLess(after["most_reused_pair"], before["most_reused_pair"])
        self.assertGreater(after["distinct_formations"], before["distinct_formations"])
        self.assertEqual(report["spread_after"], after)

    def test_rings_spread_across_formations_and_targets(self):
        pools, _ = self.run_variety()
        for pool in pools:
            metrics = dv.ring_metrics([vip.Choice(**c) for c in pool["choices"]])
            self.assertGreaterEqual(metrics["distinct_formations"], 6)
            self.assertGreaterEqual(metrics["distinct_families"], 5)
            self.assertEqual(metrics["longest_family_run"], 1)

    def test_deterministic(self):
        first, report = self.run_variety()
        second, again = self.run_variety()
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(report, sort_keys=True), json.dumps(again, sort_keys=True))

    def test_idempotent(self):
        pools, _ = self.run_variety()
        again = copy.deepcopy(pools)
        vip.diversify_pools(again, self.choices, None)
        self.assertEqual([p["choices"] for p in again], [p["choices"] for p in pools])

    def test_hail_mary_only_in_a_late_trailing_pool(self):
        choices = list(self.choices)
        top = max(c.play for c in choices) + 1
        pray = vip.Choice(40, top, True, True, "Hail Mary", "Chuck And Pray", deep_primary=True,
                          concept="chuck and pray", target="WR:R")
        deep_gun = [c for c in choices if c.passed and c.shotgun and not c.screen and not c.play_action
                    and c.deep_primary]
        self.assertTrue(deep_gun)
        choices.append(pray)
        rings = staple_rings(choices)
        for ring in rings:
            ring[2] = pray  # every pool holds a Hail Mary in a pass_gun slot
        self.assertEqual(vip.fit_class(pray), vip.fit_class(deep_gun[0]))
        pools = [dict(index=i, choices=[vars(c) for c in ring]) for i, ring in enumerate(rings)]
        report = vip.diversify_pools(pools, tuple(choices), None)
        for i, pool in enumerate(pools):
            names = [c["play_name"] for c in pool["choices"]]
            if i in dv.URGENT_TRAILING_OR_TIED:
                continue
            self.assertNotIn("Chuck And Pray", names, f"pool {i}")
        self.assertEqual(report["hard_violations"], 0)

    def test_hail_mary_with_no_class_mate_is_replaced_and_reported(self):
        choices = [c for c in self.choices if not (c.passed and c.shotgun and not c.screen and not c.play_action
                                                   and c.deep_primary)]
        pray = vip.Choice(40, 300 - 60, True, True, "Hail Mary", "Hail Mary", deep_primary=True, concept="hail mary")
        choices.append(pray)
        rings = staple_rings(choices)
        rings[0][2] = pray
        pools = [dict(index=i, choices=[vars(c) for c in ring]) for i, ring in enumerate(rings)]
        report = vip.diversify_pools(pools, tuple(choices), None)
        self.assertIn(0, report["improve"]["escaped_pools"])
        self.assertNotIn("Hail Mary", [c["play_name"] for c in pools[0]["choices"]])
        self.assertEqual(sum(c["passed"] and c["shotgun"] for c in pools[0]["choices"]),
                         sum(c.passed and c.shotgun for c in rings[0]))

    def test_situational_rule_can_be_switched_off(self):
        penalty = dv.situational_penalty(dv.Weights(situational=False))
        pray = vip.Choice(40, 200, True, True, "Hail Mary", "Hail Mary", deep_primary=True)
        self.assertEqual(penalty(0, pray), 0.0)
        self.assertGreater(dv.situational_penalty()(0, pray), 0.0)
        self.assertEqual(dv.situational_penalty()(4, pray), 0.0)
        kneel = vip.Choice(41, 201, False, False, "Victory", "Take Knee")
        self.assertGreater(dv.situational_penalty()(4, kneel), 0.0)
        self.assertEqual(dv.situational_penalty()(3, kneel), 0.0)

    def test_order_ring_separates_look_alikes(self):
        a = [vip.Choice(i, i, False, False, "f", "x", concept=name, screen=name.endswith("screen"))
             for i, name in enumerate(["counter", "counter", "draw", "bubble screen", "rb screen", "mesh", "mesh", "flood"])]
        ordered = dv.order_ring(a, lambda c: c.concept, lambda c: c.screen)
        self.assertEqual(sorted(c.play for c in ordered), sorted(c.play for c in a))
        for i, c in enumerate(ordered):
            n = ordered[(i + 1) % 8]
            self.assertNotEqual(c.concept, n.concept)
            self.assertFalse(c.screen and n.screen)
        self.assertEqual(ordered, dv.order_ring(a, lambda c: c.concept, lambda c: c.screen))
        clean = dv.order_ring(ordered, lambda c: c.concept, lambda c: c.screen)
        self.assertEqual(clean, ordered)  # an already clean ring keeps its order


class ImproveDefense(unittest.TestCase):
    def choices(self):
        out = []
        for formation in range(3):
            for front in range(2):
                for cover in range(8):
                    out.append(vip.DefenseChoice(formation, 10 + front, 20 + cover + 8 * formation,
                                                 cover % 2 == 0, 4 + cover % 3, f"D{formation}", "front", "cover"))
        return tuple(out)

    def test_defensive_rates_unchanged_and_spread_wider(self):
        choices = self.choices()
        target = dict(man=dict(rate=0.4), rush_five_plus=dict(rate=0.3))
        rings = [vip.make_defense_pool(choices, target, i * 7)[1] for i in range(15)]
        metrics = [vip.defense_metrics(r) for r in rings]
        before = len({(c.formation, c.front, c.coverage) for r in rings for c in r})
        report = vip.diversify_defense(rings, choices)
        self.assertEqual([vip.defense_metrics(r) for r in rings], metrics)
        self.assertGreaterEqual(report["spread_after"]["distinct_triples"], before)
        for ring in rings:
            self.assertEqual(len({(c.formation, c.coverage) for c in ring}), 4)
            self.assertLessEqual(max(max(c.front, c.coverage) for c in ring), 255)
        again = [vip.make_defense_pool(choices, target, i * 7)[1] for i in range(15)]
        vip.diversify_defense(again, choices)
        self.assertEqual(again, rings)  # deterministic


class MenuPages(unittest.TestCase):
    def fake_book(self, counts):
        formations = [SimpleNamespace(index=i, name=f"Formation {i} ",
                                      play_links=[SimpleNamespace(play_index=j) for j in range(n)])
                      for i, n in enumerate(counts)]
        plays = [SimpleNamespace(name=f"Play {j} ") for j in range(40)]
        return SimpleNamespace(formations=formations, plays=plays)

    def test_short_last_pages_are_found_with_the_repeated_play(self):
        book = self.fake_book([12, 10, 9, 11, 3])
        with mock.patch.object(pages.ip, "parse_playbook_resource", return_value=book), \
                mock.patch.object(pages, "formation_type", return_value=1):
            rows = pages.padding_report(b"x" * 64)
            self.assertEqual([(r["formation"], r["links"], r["pad"], r["adds"], r["trim"]) for r in rows],
                             [(1, 10, 2, 2, 1), (3, 11, 1, 1, 2)])
            self.assertEqual(rows[0]["repeated_play"], "Play 9")
            total = pages.summary({"A": b"x" * 64})
            self.assertEqual((total["formations"], total["short_formations"], total["repeated_buttons"]), (5, 2, 3))
            self.assertEqual(total["full_page_share"], 0.6)

    def test_defense_formations_are_skipped_by_default(self):
        book = self.fake_book([10])
        with mock.patch.object(pages.ip, "parse_playbook_resource", return_value=book), \
                mock.patch.object(pages, "formation_type", return_value=5):
            self.assertEqual(pages.padding_report(b"x" * 64), [])
            self.assertEqual(len(pages.padding_report(b"x" * 64, offense_only=False)), 1)


class RealBooks(unittest.TestCase):
    """The recorded rings of real books, rebuilt with and without the variety step."""

    @classmethod
    def setUpClass(cls):
        path = os.environ.get("NFL2K5_COACH_AI_IMAGE")
        if not path:
            raise unittest.SkipTest("Set NFL2K5_COACH_AI_IMAGE for real-book variety checks")
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        cls.cases = []
        with OuterImage(path) as archive:
            for team in ("CHI", "BAL", "KC"):
                row = next(r for r in ai.portrait_rows() if r["team"] == team)
                value = json.loads((ROOT / "data/vip/coaches" / (team + ".json")).read_text())
                book = ai.strip_profile(archive.read_entry(BOOK_ENTRIES[value["provenance"]["archive_book"]]))
                cls.cases.append((team, book, value))

    def test_rings_are_varied_valid_and_fit_neutral(self):
        for team, book, value in self.cases:
            with self.subTest(team=team):
                old, old_receipt = ai.build_profile(book, value, varied=False)
                new, receipt = ai.build_profile(book, value)
                self.assertEqual(ai.build_profile(book, value)[0], new)  # deterministic
                self.assertEqual(len(new), len(book))
                ai.inspect_profile(new)  # checksum, book hash and fixed span still valid
                lo = 32 + ai.PROFILE_OFFSET
                self.assertEqual(new[:lo], book[:lo])
                self.assertEqual(new[lo + ai.PROFILE_SIZE:], book[lo + ai.PROFILE_SIZE:])
                variety = receipt["variety"]
                self.assertEqual(variety["hard_violations"], 0, variety["improve"])
                self.assertIsNotNone(variety["fit"])
                self.assertEqual(json.loads(json.dumps(variety)), variety)  # receipts stay plain JSON
                before, after = variety["spread_before"], variety["spread_after"]
                self.assertGreater(after["distinct_pairs"], before["distinct_pairs"])
                self.assertLessEqual(after["most_reused_pair"], before["most_reused_pair"])
                for pool, old_pool in zip(receipt["pools"], old_receipt["pools"]):
                    self.assertEqual(pool["counts"], old_pool["counts"])  # pass/run and stance joint
                    self.assertEqual(pool["quantized_pass"], old_pool["quantized_pass"])
                    self.assertEqual(pool["quantized_shotgun"], old_pool["quantized_shotgun"])
                    for choice in pool["choices"]:
                        self.assertLessEqual(choice["play"], 255)
                        self.assertLess(choice["formation"], 255)
                    ring = [vip.Choice(**c) for c in pool["choices"]]
                    self.assertEqual(dv.ring_metrics(ring)["adjacent_screens"], 0)
                    self.assertLessEqual(dv.ring_metrics(ring)["screens"], 2)
                relaxation = variety["relaxation"]
                if relaxation and relaxation["status"] == "applied":
                    self.assertLessEqual(relaxation["objective_after"] - relaxation["objective_before"],
                                         vip.RELAX_OBJECTIVE_TOLERANCE)
                for pool in receipt["defense_pools"]:
                    for choice in pool["choices"]:
                        self.assertLessEqual(max(choice["front"], choice["coverage"]), 255)
                self.assertEqual([p["quantized"] for p in receipt["defense_pools"]],
                                 [p["quantized"] for p in old_receipt["defense_pools"]])


if __name__ == "__main__":
    unittest.main()
