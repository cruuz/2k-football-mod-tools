"""Ratings v2 (job r1): the pure pieces of tools/ratings_v2, with no disc and no network.

The disc-backed steps (the retail tier scale, the game's own OVR under Unicorn, the fragment replay) run in
tools/ratings_v2/build.py and are proved there against the user's own retail image; these tests pin the
arithmetic they rely on."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "ratings_v2"))

import model  # noqa: E402
import honors  # noqa: E402


class ArithmeticTests(unittest.TestCase):
    def test_mid_rank_percentiles_share_ties(self):
        self.assertEqual(model.pct_ranks([3.0, 1.0, 2.0]), [5 / 6, 1 / 6, 0.5])
        q = model.pct_ranks([1.0, 1.0, 2.0, 2.0])
        self.assertEqual(q[0], q[1])
        self.assertEqual(q[2], q[3])
        self.assertLess(q[0], q[2])

    def test_quantile_interpolates_the_retail_table(self):
        table = [10, 20, 30, 40, 50]
        self.assertEqual(model.quantile(table, 0.0), 10)
        self.assertEqual(model.quantile(table, 1.0), 50)
        self.assertEqual(model.quantile(table, 0.5), 30)
        self.assertAlmostEqual(model.quantile(table, 0.625), 35)
        self.assertEqual(model.quantile(table, 2.0), 50)      # clamped
        self.assertIsNone(model.quantile([], 0.5))

    def test_clip_keeps_retail_special_cases_out_of_reach(self):
        self.assertLess(model.Q_CLIP[0], 0.05)
        self.assertGreater(model.Q_CLIP[1], 0.95)
        self.assertEqual(model.clamp(120), 99)
        self.assertEqual(model.clamp(-3), 0)

    def test_passer_rating_matches_the_nfl_formula(self):
        self.assertAlmostEqual(model.passer_rating(20, 30, 300, 3, 0), 132.6389, places=3)   # (1.8333 + 1.75 + 2 + 2.375) / 6 x 100
        self.assertAlmostEqual(model.passer_rating(0, 10, 0, 0, 3), 0.0, places=3)
        self.assertIsNone(model.passer_rating(0, 0, 0, 0, 0))


class HonourTests(unittest.TestCase):
    def test_honour_positions(self):
        self.assertEqual(honors.position_of('[[Quarterback]]'), 'QB')
        self.assertEqual(honors.position_of('style="text-align:center"|[[Defensive end]]'), 'EDGE')
        self.assertEqual(honors.position_of('[[Left tackle]]'), 'T')
        self.assertEqual(honors.position_of('[[Center (gridiron football)|Center]]'), 'C')
        self.assertIsNone(honors.position_of('[[Return specialist|Punt returner]]'))
        self.assertIsNone(honors.position_of('Special teamer'))

    def test_an_honour_lifts_only_a_matching_position(self):
        self.assertIn('EDGE', model.HONOR_POS['LB'])          # the Pro Bowl's outside linebackers rush the passer
        self.assertNotIn('WR', model.HONOR_POS['CB'])
        self.assertGreater(model.HONOR_FLOOR[('AP1', 2025)], model.HONOR_FLOOR[('PB', 2025)])
        self.assertGreater(model.HONOR_FLOOR[('AP1', 2025)], model.HONOR_FLOOR[('AP1', 2024)])


class StabilityTests(unittest.TestCase):
    def setUp(self):
        self.saved = model._STABILITY
        model._STABILITY = {
            ('QB', 'cpoe'): {'r_2024_2025': 0.207, 'k_data': 1541.3},
            ('OL', 'team_pressure_over_expected_inv'): {'r_2024_2025': 0.001, 'k_data': None},
            ('WR', 'ngs_separation_over_expected'): {'r_2024_2025': 1.0, 'k_data': 0.0},
            ('DL', 'pfr_pressures_per_pass_snap'): {'r_2024_2025': 0.654, 'k_data': 50.0},
            ('LB', 'int_share_of_balls_defended'): {'note': 'too few'},
        }

    def tearDown(self):
        model._STABILITY = self.saved

    def test_k_follows_the_data_inside_its_bounds(self):
        self.assertAlmostEqual(model.stable_k('QB', 'cpoe', 150), 1541.3)
        self.assertEqual(model.stable_k('DL', 'pfr_pressures_per_pass_snap', 200), 100.0)       # floor 0.5 x
        self.assertEqual(model.stable_k('OL', 'team_pressure_over_expected_inv', 250), 3000.0)  # no repeat: 12 x

    def test_components_without_a_usable_stability_keep_their_constant(self):
        self.assertEqual(model.stable_k('WR', 'ngs_separation_over_expected', 40), 40)   # pooled over both seasons
        self.assertEqual(model.stable_k('LB', 'int_share_of_balls_defended', 20), 20)     # too few players
        self.assertEqual(model.stable_k('TE', 'unknown', 60), 60)

    def test_catch_floor_inverts_the_engine_curve(self):
        self.assertEqual(model.catch_for_probability(0.80), 50)
        self.assertAlmostEqual(model.catch_for_probability(0.88), 56.0)
        self.assertEqual(model.catch_for_probability(1.0), 65)
        self.assertEqual(model.catch_for_probability(0.05), 0)
        self.assertEqual(model.CATCH_CURVE[3], (65, 1.00))

    def test_era_offsets_are_small_and_per_group(self):
        for pos, offs in model.ERA.items():
            for rating, d in offs.items():
                self.assertIn(rating, model.RATINGS)
                self.assertLessEqual(abs(d), 6)
        self.assertEqual(model.ERA['WR'], model.ERA['TE'])
        self.assertEqual(model.ERA['CB'], model.ERA['SS'])


class _Data:
    """Just enough of model.Data for components(): two seasons of counts for one player."""

    def __init__(self, groups):
        self.F = {2025: {'g': groups}, 2024: {}}
        self.sep_oe = {}
        self.pressure_fit = (0.057, 0.0918, 64)
        self.fg_prob = lambda d: 0.9

    P = model.Data.P
    seasons = model.Data.seasons
    ngs = model.Data.ngs
    ngs_max = model.Data.ngs_max


class MeasureTests(unittest.TestCase):
    def test_receiver_catch_uses_catchable_balls_not_volume(self):
        d = _Data({'ftn_rec': {'catchable': 100.0, 'catchable_caught': 95.0, 'contested': 20.0,
                               'contested_caught': 10.0},
                   'rec': {'targets': 130.0}, 'on': {'off_pass': 500.0}})
        comps = {c[0]: c for c in model.components(d, 'g', 'WR')['catch']}
        self.assertAlmostEqual(comps['ftn_catchable_caught_rate'][1], 0.95)
        self.assertEqual(comps['ftn_catchable_caught_rate'][2], 100.0)     # the volume is the catchable balls
        self.assertAlmostEqual(comps['ftn_contested_caught_rate'][1], 0.5)

    def test_db_catch_is_ints_among_balls_defended(self):
        d = _Data({'def': {'int': 3.0, 'pd': 9.0}, 'on': {'def_pass': 500.0, 'def_run': 300.0}})
        comps = {c[0]: c for c in model.components(d, 'g', 'CB')['catch']}
        self.assertAlmostEqual(comps['int_share_of_balls_defended'][1], 0.25)

    def test_lineman_pass_block_combines_team_and_individual_signals(self):
        d = _Data({'on': {'off_pass_pr_n': 400.0, 'off_pass_pressured': 120.0, 'off_pass_ttt': 1100.0,
                          'off_pass_ttt_n': 400.0, 'off_pass': 400.0, 'off_pass_sacked': 20.0, 'off_run': 300.0,
                          'off_run_success': 130.0, 'off_run_epa': -3.0},
                   'snap': {'off': 1000.0, 'share_sum': 16.0, 'games': 16.0},
                   'pen': {'offensive_holding': 4.0, 'false_start': 2.0}})
        names = {c[0] for c in model.components(d, 'g', 'T')['pass_blocking']}
        self.assertEqual(names, {'team_pressure_over_expected_inv', 'team_sack_rate_on_field_inv',
                                 'holding_false_start_per_snap_inv', 'season_snap_share'})
        weights = sum(c[4] for c in model.components(d, 'g', 'T')['pass_blocking'])
        self.assertAlmostEqual(weights, 1.0)

    def test_qb_accuracy_blends_cpoe_with_epa(self):
        d = _Data({'qb': {'cpoe_sum': 300.0, 'cpoe_n': 500.0, 'epa_sum': 60.0, 'dropbacks': 560.0, 'att': 500.0},
                   'ftn_qb': {'catchable': 380.0, 'aimed': 480.0}})
        comps = {c[0]: c for c in model.components(d, 'g', 'QB')['pass_accuracy']}
        self.assertIn('epa_per_dropback', comps)
        self.assertAlmostEqual(comps['cpoe'][4], comps['epa_per_dropback'][4])
        self.assertAlmostEqual(comps['epa_per_dropback'][1], 60.0 / 560.0)

    def test_every_measured_rating_is_a_real_rating_byte(self):
        for pos, ratings in model.MEASURED.items():
            for r in ratings:
                self.assertIn(r, model.RATINGS, (pos, r))


if __name__ == '__main__':
    unittest.main()
