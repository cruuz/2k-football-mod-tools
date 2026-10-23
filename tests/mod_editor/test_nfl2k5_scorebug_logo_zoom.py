"""b778 sb2 (Noah, stream c2-15): team marks zoomed so they fill the wing and are slightly cut at its rails, as ESPN.

Offline only: the Studio's own logo cell (exact.mnf_panel) for every team at the shipped fit. Nothing here is an
in-game result.
"""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools/scorebug_sprite')]
import logo_zoom as lz  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_exact as exact  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_resources as resources  # noqa: E402

FOLDER = ROOT/'data/nfl2k5_scorebug_sprite'


class LogoZoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((FOLDER/'layout.json').read_text(encoding='utf-8'))
        cls.accents = json.loads((FOLDER/'team_accents.json').read_text(encoding='utf-8'))
        cls.record = cls.spec['provenance'][lz.RECORD]

    def fit(self, team):
        return resources.logo_fit_for(team, self.spec['logo_fit'])

    def test_round_and_shield_marks_bleed_past_both_rails(self):
        import numpy as np
        # Noah's stream matchup and the ESPN reference marks: each now runs past the wing's top and bottom.
        for team in ('TEN', 'PIT', 'LV', 'HOU', 'KC', 'DEN', 'DAL'):
            with self.subTest(team=team):
                fit = self.fit(team)
                self.assertAlmostEqual(fit['zoom'], lz.TARGET, places=4)
                alpha = np.asarray(exact.mnf_panel(team, 'home', fit=fit))[..., 3]
                rows = np.nonzero(alpha.max(1) >= 128)[0]
                self.assertEqual((rows[0], rows[-1]), (1, 62))           # cut at both rails inside the clear border

    def test_no_mark_shrinks_and_none_passes_the_target(self):
        for team, (before, after) in self.record['zoom'].items():
            with self.subTest(team=team):
                self.assertGreaterEqual(after, before)
                self.assertLessEqual(after, lz.TARGET)
                self.assertTrue(after == before or after > 1.0)             # raised only past the rails
                self.assertEqual(self.fit(team)['zoom'], after)

    def test_raised_marks_keep_clear_of_the_cell_edges_and_the_round_corner(self):
        for team, (before, after) in self.record['zoom'].items():
            if after == before:
                continue
            with self.subTest(team=team):
                fit = self.fit(team)
                self.assertGreaterEqual(min(lz.side_margins(team, fit)), lz.WIDTH_MARGIN)
                self.assertLessEqual(lz.corner_overreach(self.spec, team, fit), 0.0)

    def test_wide_marks_keep_their_fit(self):
        # The wordmarks and wide heads already fill the cell's width; zooming them would cut them beside a score.
        for team in ('NYJ', 'BAL', 'CAR', 'LAC', 'NE', 'SEA', 'SF', 'WAS'):
            self.assertEqual(self.record['zoom'][team][0], self.record['zoom'][team][1], team)

    def test_layout_and_team_accents_agree(self):
        for team, row in self.spec['logo_fit']['by_team'].items():
            self.assertEqual(self.accents['teams'][team]['logo_fit'], row, team)

    def test_the_tool_is_at_its_fixed_point(self):
        for team, row in lz.plan(self.spec).items():
            self.assertEqual(row['after'], row['before'], team)


if __name__ == '__main__':
    unittest.main()
