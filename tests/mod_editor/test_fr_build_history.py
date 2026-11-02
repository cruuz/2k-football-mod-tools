"""Exercise the build history stage without constructing or touching a disc."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from types import SimpleNamespace
from unittest.mock import patch
import unittest
from mod_editor.core import mod_build as build

class BuildHistoryTests(unittest.TestCase):
    def run_stage(self, embedded=None, career='stats.csv', season=True):
        calls=[]
        def module(name):
            if name=='nfl2k5_roster_records':
                return SimpleNamespace(read_edits=lambda p:{'franchise_history':embedded},
                    apply=lambda *a,**kw:calls.append(('identities',kw)) or {'log':[]})
            return SimpleNamespace(apply=lambda *a,**kw:calls.append((name,kw)) or {'log':[]})
        plan=SimpleNamespace(roster_edits='g.json',season_2026=season,position_pools=False,
                             career_stats=career,team_history='retail',honors_history='')
        with patch.object(build,'_core_module',side_effect=module):
            build._apply_roster_history(plan,'fake-target',{'steps':[]},lambda *a:None)
        return calls

    def test_order_and_epoch(self):
        calls=self.run_stage()
        self.assertEqual([c[0] for c in calls],['identities','nfl2k5_career_stats','nfl2k5_team_history'])
        # the counters follow the build's season; the original roster's team history always counts back from the
        # roster's own 2004 (b780 b2: the franchise's 2026 start year made every real row "outside the record")
        self.assertEqual([c[1]['base_year'] for c in calls[1:]],[2026,2004])

    def test_embedded_owner_suppresses_retail_and_conflicts_refuse(self):
        self.assertEqual([c[0] for c in self.run_stage({'base_year':2026},career='')],['identities'])
        with self.assertRaisesRegex(ValueError,'conflicting'):self.run_stage({'base_year':2026})
        with self.assertRaisesRegex(ValueError,'epoch'):self.run_stage({'base_year':2026},career='',season=False)


class ImpliedTeamHistoryTests(unittest.TestCase):
    """b780 b2 (SharkMagick, "Team Card still empty"): the TEAM column on an original roster brings its past seasons."""

    def run_stage(self, *, team_column=True, team_history='', roster_edits='', embedded=None, season=False,
                  status='retail', disc=True, history_present=True, rows_error=None, apply_raises=None, status_after=None):
        calls, notes = [], []
        receipt={'steps':[]}
        state = {'after_apply': False}
        def apply(*a, **kw):
            calls.append((a, kw))
            if apply_raises:
                state['after_apply'] = True
                raise apply_raises
            return {'status': 'applied', 'seasons_with_a_team': 5746, 'log': ['x']}
        def load_rows(source):
            if rows_error:
                raise rows_error
            return [], {}
        def read_status(path):
            if isinstance(status, Exception):
                raise status
            return status_after if (status_after and state['after_apply']) else status
        history = SimpleNamespace(status=read_status, apply=apply, load_rows=load_rows)
        def module(name):
            if name == 'nfl2k5_team_history':
                return history if history_present else None
            if name == 'nfl2k5_roster_records':
                return SimpleNamespace(read_edits=lambda p: {'franchise_history': embedded},
                                       apply=lambda *a, **kw: {'log': []})
            raise AssertionError(name)
        plan = SimpleNamespace(roster_edits=roster_edits, season_2026=season, position_pools=False, career_stats='',
                               team_history=team_history, team_column=team_column, honors_history='')
        with patch.object(build, '_core_module', side_effect=module), \
                patch.object(build.tt, 'is_disc_image', return_value=disc):
            build._apply_roster_history(plan, 'fake-target', receipt, lambda msg, *a: notes.append(msg))
        return calls, receipt['steps'], notes

    def test_the_column_alone_writes_the_built_in_history_for_the_roster_s_own_2004(self):
        calls, steps, _notes = self.run_stage()
        self.assertEqual(len(calls), 1)
        args, kw = calls[0]
        self.assertEqual(args, ('fake-target', 'retail'))
        self.assertEqual(kw['base_year'], 2004)
        self.assertEqual(steps[0]['step'], 'team_history')
        self.assertEqual(steps[0]['implied_by'], 'team_column')
        self.assertEqual(steps[0]['seasons_with_a_team'], 5746)

    def test_the_2026_option_does_not_move_the_original_roster_s_epoch(self):
        self.assertEqual(build.RETAIL_ROSTER_EPOCH, 2004)
        for season in (False, True):
            calls, _steps, _notes = self.run_stage(season=season)
            self.assertEqual(calls[0][1]['base_year'], 2004, season)
        calls, _steps, _notes = self.run_stage(team_history='retail', season=True)      # the explicit option too
        self.assertEqual(calls[0][1]['base_year'], 2004)

    def test_nothing_without_the_column_and_an_explicit_choice_is_untouched(self):
        self.assertEqual(self.run_stage(team_column=False)[0], [])
        calls, steps, _notes = self.run_stage(team_column=False, team_history='mine.csv')
        self.assertEqual(calls[0][0], ('fake-target', 'mine.csv'))
        self.assertNotIn('implied_by', steps[0])
        calls, steps, _notes = self.run_stage(team_history='mine.csv')                    # a CSV wins over the built-in data
        self.assertEqual([c[0][1] for c in calls], ['mine.csv'])

    def test_the_modern_roster_keeps_its_own_history(self):
        calls, steps, _notes = self.run_stage(roster_edits='g.json', embedded={'base_year': 2004})
        self.assertEqual(calls, [])
        self.assertEqual(steps[-1]['status'], 'owned_by_franchise_history')

    def test_a_roster_that_is_not_the_original_is_skipped_with_the_reason_never_fatal(self):
        for state in ('foreign', 'unreadable'):
            calls, steps, notes = self.run_stage(status=state)
            self.assertEqual(calls, [])
            self.assertEqual(steps[0]['status'], 'skipped')
            self.assertIn('not the original 2004 roster', steps[0]['reason'])
            self.assertTrue(any('skipped' in n and 'TEAM column' in n for n in notes), notes)
            # the finished-disc notice carries the same fact in plain words (build_feedback.completion reads user_notes)
            self.assertEqual(len(steps[0]['user_notes']), 1)
            self.assertIn('past seasons were not filled', steps[0]['user_notes'][0])
            self.assertNotIn('\u2014', steps[0]['user_notes'][0])
        for state in ('applied', 'applied-custom'):
            calls, steps, _notes = self.run_stage(status=state)
            self.assertEqual(calls, [])
            self.assertEqual((steps[0]['status'], steps[0]['already_applied']), (state, True))

    def test_a_folder_source_a_missing_module_or_a_broken_csv_is_a_note_not_a_dead_build(self):
        for kw, text in ((dict(disc=False), 'needs a disc image'), (dict(history_present=False), 'not available'),
                         (dict(status=ValueError('bad pack')), 'could not be read (bad pack)'),
                         (dict(rows_error=ValueError('pin mismatch')), 'built-in team history could not be read')):
            calls, steps, notes = self.run_stage(**kw)
            self.assertEqual(calls, [], kw)
            self.assertEqual(steps[0]['status'], 'skipped', kw)
            self.assertIn(text, steps[0]['reason'], kw)
            self.assertTrue(notes, kw)
            self.assertTrue(steps[0]['user_notes'], kw)

    def test_every_preset_that_turns_the_column_on_gets_the_history_with_the_roster_epoch(self):
        for name in ('softdrink_basic', 'softdrink_advanced', 'softdrink_experimental'):
            plan = build.apply_preset(build.BuildPlan('s', 't'), name)
            self.assertTrue(plan.team_column, name)
            calls = []

            def module(mod_name, calls=calls):
                return SimpleNamespace(status=lambda path: 'retail', load_rows=lambda source: ([], {}),
                                       apply=lambda *a, **kw: calls.append((mod_name, a, kw)) or {'log': []})
            with patch.object(build, '_core_module', side_effect=module), \
                    patch.object(build.tt, 'is_disc_image', return_value=True):
                build._apply_roster_history(plan, 'fake-target', {'steps': []}, lambda *a: None)
            history = [c for c in calls if c[0] == 'nfl2k5_team_history']
            self.assertEqual(len(history), 1, name)
            self.assertEqual(history[0][2]['base_year'], 2004, name)

    def test_a_real_write_error_after_the_checks_still_stops_the_build(self):
        with self.assertRaisesRegex(OSError, 'disk'):
            self.run_stage(apply_raises=OSError('disk full'))

    def test_a_refusal_before_anything_was_written_is_a_note_and_one_after_a_write_is_not(self):
        calls, steps, notes = self.run_stage(apply_raises=ValueError('pool would hold 50001 dwords'))
        self.assertEqual(steps[0]['status'], 'skipped')
        self.assertIn('could not be written (pool would hold 50001 dwords)', steps[0]['reason'])
        self.assertTrue(steps[0]['user_notes'] and notes)
        with self.assertRaisesRegex(ValueError, 'read-back'):
            self.run_stage(apply_raises=ValueError('read-back of the roster resource differs'), status_after='applied')


if __name__ == "__main__":
    unittest.main()
