"""Exercise the build history stage without constructing or touching a disc."""
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
        plan=SimpleNamespace(roster_edits='g.json',season_2026=season,position_pools=False,career_stats=career,team_history='retail')
        with patch.object(build,'_core_module',side_effect=module):
            build._apply_roster_history(plan,'fake-target',{'steps':[]},lambda *a:None)
        return calls

    def test_order_and_epoch(self):
        calls=self.run_stage()
        self.assertEqual([c[0] for c in calls],['identities','nfl2k5_career_stats','nfl2k5_team_history'])
        self.assertEqual([c[1]['base_year'] for c in calls[1:]],[2026,2026])

    def test_embedded_owner_suppresses_retail_and_conflicts_refuse(self):
        self.assertEqual([c[0] for c in self.run_stage({'base_year':2026},career='')],['identities'])
        with self.assertRaisesRegex(ValueError,'conflicting'):self.run_stage({'base_year':2026})
        with self.assertRaisesRegex(ValueError,'epoch'):self.run_stage({'base_year':2026},career='',season=False)


if __name__ == "__main__":
    unittest.main()
