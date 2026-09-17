"""The all-team clone scope predates the consolidated CPU page."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_book_identity as identity, apf2k8_book_clone as clone
from mod_editor.apf_studio.playcalling_service import assignment_row, validate_request
from tests.mod_editor.test_apf_book_unlock import archive_fixture


class BookScopeTests(unittest.TestCase):
    def check_scope(self, index, retail=False):
        roster = identity.read_disc_roster(index)
        before = identity.parse_roster_identity(roster)
        self.assertEqual(len(before.teams), 40)
        plans = []
        for side, count in (('offense', 36), ('defense', 33)):
            if retail:
                self.assertEqual(sum(l.side == side for l in before.labels), count)
            plan = clone.own_book_plan(index, roster, side)
            self.assertEqual([p.team_index for p in plan], list(range(24)))
            validate_request(dict(kind='clones', side=side, assignments=[assignment_row(p) for p in plan]))
            plans.extend(plan)
        self.assertEqual(len({p.clone_name for p in plans}), 48)
        bound, _ = clone.bind_roster(roster, (p.request() for p in plans))
        after = identity.parse_roster_identity(bound)
        self.assertEqual(before.teams[24:], after.teams[24:])
        for team in after.teams[24:]:
            for field in ('offense', 'defense'):
                label = getattr(team, field)
                self.assertEqual(before.labels[label], after.labels[label])
        for p in plans:
            self.assertEqual(after.labels[p.label_id].kind, p.clone_name)

    def test_48_named_copies_preserve_all_saved_team_readers(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.check_scope(archive_fixture(Path(tmp)/'source'))

    def test_retail_36_and_33_labels_are_not_the_24_team_limit(self):
        from tests.mod_editor.test_apf_playcall_research_native import INDEX
        if not INDEX.is_file():
            self.skipTest('Owned APF index absent; set APF_RETAIL_INDEX for the real label census')
        self.check_scope(INDEX, retail=True)

    def test_retail_manual_allocation_exceeds_24_without_consuming_user_labels(self):
        from tests.mod_editor.test_apf_playcall_research_native import INDEX
        if not INDEX.is_file():
            self.skipTest('Owned APF index absent; set APF_RETAIL_INDEX for archive allocation')
        roster = identity.read_disc_roster(INDEX)
        before = identity.parse_roster_identity(roster)
        # Separate compilations: default label names overlap across sides.
        # This deliberately reassigns saved slots, unlike the automatic plan.
        for side, count in (('offense', 35), ('defense', 32)):
            reserved = {getattr(t, side) for t in before.teams[24:]}
            labels = [l for l in before.labels if l.side == side and l.index not in reserved]
            requests = [clone.CloneRequest(label.index, team.index,
                          before.labels[getattr(team, side)].kind)
                        for team, label in zip(before.teams, labels)]
            compiled = clone.compile_unlock(INDEX, requests)
            self.assertEqual(len(compiled.clones), count)
            after = identity.parse_roster_identity(compiled.roster_body)
            self.assertEqual(len({after.labels[getattr(t, side)].kind for t in after.teams}), count + 1)
            for label in reserved:
                self.assertEqual(after.labels[label], before.labels[label])


if __name__ == '__main__': unittest.main()
