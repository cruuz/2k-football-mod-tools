"""Standalone tests of all 50 sides, private PFR facts, and fixed retail chains."""
from collections import Counter
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tools', ROOT / 'tests'):
    sys.path.insert(0, str(path))
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_roster_records as rr
import nfl2k5_espn25_rosters_from_nflverse as gen
import nfl2k5_espn25_exact_lineups as exact
from tests.mod_editor.test_nfl2k5_espn25_rosters import RETAIL

# Retail depth table 0x5140D8, independently decoded: left uses chain 0
# (rank), right uses chain 1 (side). A low rank alone cannot certify RT/RCB.
SIDE_ROLES = {
    'LT': ('T', 'retail_depth_rank'), 'RT': ('T', 'retail_depth_side'),
    'LG': ('G', 'retail_depth_rank'), 'RG': ('G', 'retail_depth_side'),
    'LDE': ('DE', 'retail_depth_rank'), 'RDE': ('DE', 'retail_depth_side'),
    'LDT': ('DT', 'retail_depth_rank'), 'RDT': ('DT', 'retail_depth_side'),
    'LLB': ('OLB', 'retail_depth_rank'), 'RLB': ('OLB', 'retail_depth_side'),
    'LOLB': ('OLB', 'retail_depth_rank'), 'ROLB': ('OLB', 'retail_depth_side'),
    'LILB': ('ILB', 'retail_depth_rank'), 'RILB': ('ILB', 'retail_depth_side'),
    'LCB': ('CB', 'retail_depth_rank'), 'RCB': ('CB', 'retail_depth_side'),
    'SE': ('WR', 'retail_depth_rank'), 'FL': ('WR', 'retail_depth_side'),
}


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.sheets = e.dataset()
        cls.targets = {t['outer']: t for t in cls.manifest['resources']}

    def test_all_50_sides_have_complete_facts_and_honest_shared_file_exceptions(self):
        count, chosen_count = 0, 0
        for moment in self.manifest['moments']:
            self.assertEqual(moment['lineup_basis'], exact.LINEUP_BASIS)
            for side in moment['sides'].values():
                target = self.targets[side['outer']]
                sheet = self.sheets[side['outer']]
                people = {gen.norm(r['first'] + ' ' + r['last']): i for i, r in enumerate(sheet)}
                starters = side['starters']
                self.assertEqual(len(starters), 22)
                self.assertEqual(len({s['name'] for s in starters}), 22)
                missing, present = [], 0
                for st in starters:
                    count += 1
                    slot = people.get(gen.norm(st['name']))
                    self.assertEqual(st['slot'], slot)
                    self.assertEqual(st['present'], slot is not None)
                    if slot is None:
                        missing.append(st['name'])
                        continue
                    present += 1
                    self.assertEqual(st['number_matches'], st['jersey'] is not None and int(sheet[slot]['jersey']) == st['jersey'])
                    if side['chosen_moment'] == moment['moment']:
                        self.assertTrue(st['at_starting_depth'], st['name'])
                        self.assertEqual(int(sheet[slot]['jersey']), st['jersey'], st['name'])
                        self.assertTrue(target['players'][slot]['game_starter'])
                        if st['position'] in SIDE_ROLES:
                            position, field = SIDE_ROLES[st['position']]
                            group = [p for p, r in zip(target['players'], sheet) if r['position'] == position]
                            role_count = sum(x['position'] == st['position'] for x in starters)
                            heads = sorted(group, key=lambda p: (p[field], p['slot']))[:role_count]
                            self.assertIn(slot, [p['slot'] for p in heads], st['name'])
                self.assertEqual(side['starters_present'], present)
                self.assertEqual(side['missing_starters'], missing)
                self.assertEqual(side['starters_resolved'], sum(s['present'] and s['at_starting_depth'] for s in starters))
                self.assertEqual(side['numbers_from_game_season'] + side['numbers_still_unknown'], 53)
                self.assertEqual(side['exact_game_lineup_established'], side['starters_resolved'] == 22 and not side['starter_number_mismatches'])
                if side['chosen_moment'] == moment['moment']:
                    chosen_count += 1
                    self.assertEqual(side['starters_resolved'], 22)
                    self.assertTrue(side['exact_game_lineup_established'])
                else:
                    conflict = next(x for x in target['losing_moment_starters'] if x['moment'] == moment['moment'])
                    self.assertEqual(conflict['missing_starters'], missing)
                    self.assertTrue(side['shared_season_conflict'])
                    self.assertFalse(side['exact_game_lineup_established'])
        for target in self.targets.values():
            for position in rr.POSITIONS:
                group = [p for p, r in zip(target['players'], self.sheets[target['outer']]) if r['position'] == position]
                def depth(p):
                    return min(p['retail_depth_rank'], p['retail_depth_side']) if position in {
                        'G', 'T', 'DE', 'DT', 'OLB', 'ILB', 'CB', 'WR'} else p['retail_depth_rank']
                starters = [depth(p) for p in group if p['game_starter']]
                bench = [depth(p) for p in group if not p['game_starter']]
                if starters and bench:
                    self.assertLessEqual(max(starters), min(bench), (target['csv'], position))
        self.assertEqual((count, chosen_count), (1100, 35))
        self.assertEqual(sum(t['unknown_numbers'] for t in self.targets.values()), 123)
        self.assertEqual(sum(t['numbers_from_game_season'] for t in self.targets.values()), 1732)

    def test_only_player_facts_are_distributed_and_base_attribution_survives(self):
        self.assertEqual(self.manifest['source']['licence'], 'CC-BY-4.0')
        self.assertEqual(self.manifest['source']['lineup_source']['name'], 'Pro Football Reference')
        self.assertEqual(self.manifest['source']['lineup_source']['aggregate_rows_excluded'], 50)
        for target in self.targets.values():
            self.assertEqual(sum(p['game_starter'] for p in target['players']), 22)
            self.assertEqual(target['other_season_numbers'], 0)
            for p in target['players']:
                self.assertNotEqual(p['source_full_name'], 'Team Total')
                self.assertFalse({'age', 'drafted', 'gs', 'g', 'av'} & p.keys())
                self.assertEqual(p['jersey_source']['basis'] == 'pfr_game_season', p['pfr_name'] is not None)


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not exact.DEFAULT_PFR.is_file():
            raise unittest.SkipTest('private pfr_pull/v1 evidence absent: ' + str(exact.DEFAULT_PFR))
        cls.raw = json.loads(exact.DEFAULT_PFR.read_text())
        cls.evidence = exact.Evidence()
        cls.manifest, cls.sheets = e.dataset()

    def test_each_box_score_name_position_and_season_number_matches_the_csv_or_recorded_conflict(self):
        for moment in self.manifest['moments']:
            box = self.raw['boxscores'][moment['moment']]
            for side in moment['sides'].values():
                original = box[side['boxscore_source_side']]
                roster = next(r for r in self.raw['rosters'] if r['url'] == side['pfr_roster_url'])
                numbers = {gen.norm(r['player']): r['no'] for r in roster['players'] if r['player'] != 'Team Total'}
                self.assertEqual([s['name'] for s in side['starters']], [s['player'] for s in original])
                for st, src in zip(side['starters'], original):
                    self.assertEqual(st['box_position'], src['pos'])
                    no = numbers[gen.norm(src['player'])]
                    self.assertEqual(st['jersey'], int(no) if no else None)
                    if not side['shared_season_conflict']:
                        self.assertIsNotNone(st['slot'])
                        self.assertEqual(int(self.sheets[side['outer']][st['slot']]['jersey']), int(no))
                verified = sum(bool(numbers.get(gen.norm(r['first'] + ' ' + r['last']))) and
                               int(numbers[gen.norm(r['first'] + ' ' + r['last'])]) == int(r['jersey'])
                               for r in self.sheets[side['outer']])
                self.assertEqual(side['numbers_from_game_season'], verified)

    def test_bench_and_numbers_follow_the_actual_season_page(self):
        pages = {r['url']: r for r in self.raw['rosters']}
        for target in self.manifest['resources']:
            chosen = self.manifest['moments'][target['chosen_moment']]
            side = next(s for s in chosen['sides'].values() if s['outer'] == target['outer'])
            page = pages[side['pfr_roster_url']]
            people = [r for r in page['players'] if r['player'] != 'Team Total']
            order = {r['player']: i for i, r in enumerate(sorted(people, key=lambda r: (
                -gen.number(r['gs']), -gen.number(r['g']), -gen.number(r['av']), gen.norm(r['player']))))}
            selected = {p['pfr_name'] for p in target['players'] if p['pfr_name']}
            excluded = {p['name'] for p in target['excluded_source_names']}
            for p, row in zip(target['players'], self.sheets[target['outer']]):
                if p['pfr_name']:
                    donor = page['players'][p['pfr_roster_line'] - 1]
                    self.assertEqual(donor['player'], p['pfr_name'])
                    self.assertEqual(int(row['jersey']), int(donor['no']))
                    if not p['game_starter']:
                        self.assertEqual(p['bench_selection_rank'], order[donor['player']])
                        for other in people:
                            if other['player'] not in selected | excluded and row['position'] in exact.positions(other['pos']):
                                self.assertLessEqual(order[donor['player']], order[other['player']])
                else:
                    self.assertEqual(p['jersey_source']['reason'], 'player_absent_from_game_season_roster')
                if p['college_source'] == 'Pro Football Reference':
                    self.assertEqual(p['source_college'], page['players'][p['pfr_roster_line'] - 1]['college'])
                if row['college']:
                    self.assertEqual(row['college'], p['source_college'])
                    self.assertEqual(self.manifest['colleges'].count(row['college']), 1)

    def test_source_anomalies_are_explicit_and_ambiguous_names_are_refused(self):
        side = self.manifest['moments'][18]['sides']
        self.assertEqual((side['away']['boxscore_source_side'], side['home']['boxscore_source_side']), ('home', 'away'))
        lance = next(s for s in self.manifest['moments'][12]['sides']['home']['starters'] if s['name'] == 'Lance Smith')
        self.assertEqual((lance['box_position'], lance['position'], lance['season_position']), ('SS', 'RG', 'RG'))
        self.assertIn('HYPOTHESIS', lance['position_note'])
        self.assertEqual(exact.positions('LS', starter=True), ('FS', 'SS'))
        self.assertEqual(exact.positions('LS'), ('C',))
        with self.assertRaisesRegex(e.Espn25RostersError, 'ambiguous'):
            exact.match_name('A Player', [{'player': 'A Player'}, {'player': 'A Player'}])
        bad = copy.deepcopy(self.raw)
        bad['boxscores'][0]['away'].pop()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'bad.json'
            path.write_text(json.dumps(bad))
            with self.assertRaisesRegex(e.Espn25RostersError, '22 distinct'):
                exact.Evidence(path)

    def test_fixed_retail_depth_fields_really_match_the_provenance(self):
        if not (RETAIL / 'vc_53450030/0').is_file():
            self.skipTest('user-owned retail archive evidence absent')
        before = e.read_resources(RETAIL)
        for target in self.manifest['resources']:
            doc = rr.RosterDocument(before[target['outer']][32:])
            for p, provenance in zip(doc.players, target['players']):
                self.assertEqual(p.record.values['depth_rank'], provenance['retail_depth_rank'])
                self.assertEqual(p.record.values['depth_side'], provenance['retail_depth_side'])


if __name__ == '__main__':
    unittest.main()
