"""b779 dp1: every club's defense plays like its real 2025/2026 self.

Noah (10/28): "increase variety of defense plays and schemes and blitzes and disguises and shells etc... make teams
play like they do irl with their defensive looks and schemes".

  * CPU calls: with the SOFTDRINK coach profile on, every CPU defensive call comes from fifteen four-call rings
    (native 0xF7450 / 0x17DFC0).  They are now fitted per club and per cell (down-and-distance bin x offense
    personnel) to the 2026 coordinator's 2025 calls, and 3-4 books take part (beta-78 rings were the Bear 46 on every
    snap for BAL, HOU, NE, PIT and SD, and a third each base / nickel / dime for everyone else);
  * books: front families per coordinator (4-3 Over / Under / Wide 9 / Tite, 3-4 Okie / Tite / Eagle), front-call
    styles, per-club coverage script spread and disguised single-high calls ("Rotate").

Pure-data tests run anywhere; the ring tests that compile a retail book need the private XISO and skip without it.
"""
from __future__ import annotations

from collections import Counter
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'pb/v2/defense')]
sys.dont_write_bytecode = True

from mod_editor.core import nfl2k5_defense_lint as dlint  # noqa: E402
from mod_editor.core import nfl2k5_defense_rings as rings  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as pk  # noqa: E402

TEAMS = pk.TEAM_BOOKS
IMAGE = Path(os.environ.get('NFL2K5_RETAIL_IMAGE', '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))
OUT = ROOT / 'pb/v2/defense/out'


def catalog(team: str) -> dict:
    return json.loads((OUT / f'{team}.json').read_text())


class Identity(unittest.TestCase):
    def test_every_club_has_a_coordinator_row_with_its_situational_counts(self):
        doc = rings.load_identity()
        self.assertEqual(sorted(doc['teams']), sorted(TEAMS))
        for team, row in doc['teams'].items():
            with self.subTest(team=team):
                self.assertTrue(row['dc'] and row['baseline_2025'] and row['source'].startswith('https://'))
                cells = row['cells']
                self.assertGreater(sum(c.get('snaps', 0) for c in cells.values()), 800)
                for key, c in cells.items():
                    self.assertRegex(key, r'^[012][1-4]$')
                    self.assertLessEqual(c.get('base', 0) + c.get('nickel', 0) + c.get('dime', 0), c.get('pers_known', 0))
                    self.assertLessEqual(c.get('blitz', 0), c.get('rush_known', 0))
                self.assertTrue(0.1 <= row['disguise'] <= 0.6)

    def test_targets_follow_the_offense_personnel(self):
        """A ring against four wide receivers wants more sub-package DBs than a ring against two backs."""
        doc = rings.load_identity()
        for team in TEAMS:
            targets, weights = rings.ring_targets(doc['teams'][team], doc['league_cells'])
            with self.subTest(team=team):
                self.assertEqual(len(targets), 15)
                self.assertAlmostEqual(sum(targets[1]['pers'].values()), 1.0, places=6)
                heavy, spread = targets[1]['pers'], targets[4]['pers']
                self.assertGreater(heavy['base'], spread['base'])
                self.assertGreater(spread['nickel'] + spread['dime'], heavy['nickel'] + heavy['dime'])


class FrontFamilies(unittest.TestCase):
    """Every front family authored for a coordinator passes the alignment linter on the retail slot layouts."""

    def check(self, name, positions, codes):
        stances = [3 if (c & 31) in (12, 13) else 1 for c in codes]
        f = dlint.DefenseFormation(name, positions, codes, stances, type_code=5)
        return [x.message for x in dlint.formation_findings(f)]

    def test_four_down_families_are_lint_clean(self):
        import design as D
        retail = [(365, 0), (-365, 0), (150, 0), (-150, 0), (402, 365), (0, 457), (-402, 365),
                  (640, 1188), (-640, 1097), (1371, 365), (-1371, 365)]
        base_codes = [12, 12, 13, 13, 15, 14, 15, 16, 17, 18, 18]
        nickel_codes = [12, 12, 13, 13, 15, 14, 18, 16, 17, 18, 18]
        dime_codes = [12, 12, 13, 13, 18, 15, 18, 16, 17, 18, 18]
        for fam in (D.OVER, D.WIDE, D.UNDER, D.WIDE9, D.TITE4):
            for codes, builder in ((base_codes, D.base_43), (nickel_codes, D.nickel_even), (dime_codes, D.dime_even)):
                pos = list(retail)
                for s, p in builder(fam, [c & 31 for c in codes]).items():
                    pos[s] = p
                with self.subTest(family=fam.name, builder=builder.__name__):
                    self.assertEqual(self.check(f'4-3 {fam.name}', pos, codes), [])

    def test_three_down_families_are_lint_clean(self):
        import design as D
        retail = [(520, 91), (255, 0), (-365, 0), (0, 0), (183, 457), (-183, 457), (-580, 91),
                  (640, 1188), (-640, 1097), (1371, 365), (-1371, 365)]
        codes = [15, 12, 12, 13, 14, 14, 15, 16, 17, 18, 18]
        for fam in (D.ODD, D.TITE3, D.EAGLE):
            pos = list(retail)
            for s, p in D.odd_front([c & 31 for c in codes], base=True, family=fam).items():
                pos[s] = p
            with self.subTest(family=fam.name):
                f = dlint.DefenseFormation(f'3-4 {fam.name}', pos, codes, [1, 3, 3, 3, 1, 1, 1, 1, 1, 1, 1], type_code=4)
                self.assertEqual([x.message for x in dlint.formation_findings(f)], [])

    def test_clubs_line_up_in_their_coordinators_fronts(self):
        names = {t: [r['name'] for r in catalog(t)['roles'].values()] for t in TEAMS}
        self.assertIn('4-3 Wide 9', names['TEN'])          # Bradley: Seattle / Saleh four-down
        self.assertIn('Nickel Tite', names['PHI'])         # Fangio
        self.assertIn('3-4 Eagle', names['MIN'])           # Flores
        self.assertIn('4-3 Under', names['KC'])            # Spagnuolo
        self.assertIn('3-4 Tite', names['DAL'])            # Parker (Fangio tree)
        alignments = Counter()
        for t in TEAMS:
            for r in catalog(t)['roles'].values():
                alignments[r['family']] += 1
        self.assertGreaterEqual(len([f for f in alignments if f not in ('Bear', 'Mug', 'retail')]), 7, alignments)

    def test_front_call_menus_differ_by_style(self):
        menus = {}
        for t in TEAMS:
            fronts = tuple((p['name'], p['band']) for p in catalog(t)['plays'] if p['component'] == 'front')[:8]
            menus[t] = fronts
        self.assertNotEqual(menus['TEN'], menus['PHI'])
        self.assertNotEqual(menus['TB'], menus['PHI'])
        self.assertEqual(menus['TEN'][0][0], 'Wide Rush')     # speed off the edge first
        self.assertEqual(menus['PHI'][0][0], 'Base')          # read the run on the way
        self.assertEqual(menus['TB'][0][0], 'Attack')         # line games and penetration
        self.assertGreaterEqual(len(set(menus.values())), 3)


class Books(unittest.TestCase):
    def test_disguised_calls_exist_for_the_disguise_coordinators(self):
        for team in ('SEA', 'MIN', 'WAS', 'PIT', 'IND', 'BAL'):
            with self.subTest(team=team):
                plays = catalog(team)['plays']
                rot = [p for p in plays if p.get('disguise')]
                self.assertTrue(all('Rotate' in p['name'] for p in rot))
                for p in rot:
                    self.assertEqual(p['disguise']['presnap'], 'two')
                    self.assertIn(p['disguise']['postsnap'], ('C0', 'C1', 'C3', 'ZONE1'))
                    self.assertNotIn('bear', p['roles'])

    def test_coverage_scripts_spread_over_the_retail_library(self):
        """b779 dp1 ``build.spread``: clubs no longer all take the most popular retail script for a concept."""
        sources = Counter()
        for t in TEAMS:
            for p in catalog(t)['plays']:
                src = p.get('source') or {}
                if p['component'] == 'coverage' and 'book' in src:
                    sources[(src['book'], src['play'])] += 1
        self.assertGreaterEqual(len(sources), 600, len(sources))


@unittest.skipUnless(IMAGE.is_file(), f'private retail XISO absent: {IMAGE}')
class Rings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        from mod_editor.core import nfl2k5_playbook_inspector as ip
        from mod_editor.core import nfl2k5_play_library as lib
        from mod_editor.core import nfl2k5_vip as vip
        cls.built = {}
        with OuterImage(IMAGE) as img:
            for team in ('PIT', 'PHI', 'TB'):
                raw = img.read_entry(BOOK_ENTRIES[team])
                book = ip.parse_playbook_resource(raw)
                body = raw[32:]
                cls.built[team] = rings.build(book, body, vip.vip_defense_formations(book, body), lib.defense_pairs, team)

    def test_three_four_books_call_their_three_four(self):
        rs, receipt = self.built['PIT']
        forms = Counter(c.type_code for r in rs for c in r)
        self.assertGreater(forms[4], 20, forms)                       # 3-4 / Nickel / Dime (three-down) calls
        for p, r in enumerate(rs):
            for c in r:
                if c.bear:
                    self.assertEqual(p // 5, 0, receipt['rings'][p])  # the Bear only on short yardage
                    self.assertIn(p % 5, (0, 1, 2))

    def test_rings_are_distinct_and_fit_the_season(self):
        for team, (rs, receipt) in self.built.items():
            with self.subTest(team=team):
                for r in rs:
                    self.assertEqual(len({(c.formation, c.coverage) for c in r}), 4)
                    self.assertTrue(all(c.front <= 255 and c.coverage <= 255 for c in r))
                m, t = receipt['season_model'], receipt['season_target']
                for k in ('base', 'nickel', 'dime'):
                    self.assertLess(abs(m.get('p_' + k, 0) - t['pers'][k]), 0.08, (k, m, t))
                self.assertLess(abs(m.get('blitz', 0) - t['blitz']), 0.08)
                self.assertLess(abs(m.get('man', 0) - t['man']), 0.10)
                self.assertGreaterEqual(receipt['distinct_calls'], 40)

    def test_the_situation_changes_the_call(self):
        """Against two backs the CPU stays in base; against four wide receivers it is in sub packages."""
        for team, (rs, _) in self.built.items():
            with self.subTest(team=team):
                heavy = Counter(c.personnel for c in rs[1] + rs[6])
                spread = Counter(c.personnel for c in rs[9] + rs[14])
                self.assertGreater(heavy['base'], spread['base'])
                self.assertGreater(spread['nickel'] + spread['dime'], heavy['nickel'] + heavy['dime'])


if __name__ == '__main__':
    unittest.main()
