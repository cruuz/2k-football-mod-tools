"""Native exclusion boundaries beyond the mixed-offense 10,240-tuple sweep."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_apf_b67_model_native import inputs, INDEX
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.apf2k8_formation_calling import membership_masks, set_never_call
from tools.apf_playcall_research_probe import Machine, MANAGER, MASTER, OUTPUT
from tools.apf_defense_native_probe import DefenseMachine, added_book
from tests.mod_editor.test_apf_playcall_research_native import heavy_addition
from mod_editor.core.apf2k8_book_clone import clone_body


class RetirementBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image, cls.master, cls.runtime = inputs()

    def test_complete_offense_driver_at_run_and_pass_boundaries(self):
        book = splb.read_book(INDEX, 767)
        changed = set_never_call(book.body, 68, True, membership_masks(book.body, 68))
        m = Machine(self.image, self.runtime)
        m.install(splb.parse_book(changed, 767)); m.configure(); m.normalize()
        count = 0
        for run in (0., 1.):
            for down, yards, goal in ((1, 1, 1), (2, 5, 50), (3, 8, 50)):
                for quantile in (.01, .25, .5, .9):
                    m.configure(down=down, yards=yards, goal_yards=goal, run_share=run, fraction=quantile)
                    m.call(0x8486CE88, MANAGER, OUTPUT, stop=0x8486D0CC, bound=2000000)
                    form = (m.get(OUTPUT+4)-MASTER-0x244)//184
                    self.assertTrue(0 <= form < 151)
                    self.assertNotEqual(form, 68)
                    self.assertTrue(MASTER+0x80C4 <= m.get(OUTPUT+12) < MASTER+0x80C4+586*100)
                    count += 1
        print('PROVED run/pass boundary complete ordinary drivers:', count, flush=True)

    def test_defense_membership_exclusion_with_remaining_category_coverage(self):
        book = splb.read_book(INDEX, 134)
        # This stock book has only one ordinary record per category. Add
        # replacement supply with the existing writer before retiring stock.
        record = next(r for r in book.records if r.populated and r.formation_index < 151)
        book = added_book(book, record, 144, record.category_index)
        retired = record.formation_index
        changed = set_never_call(book.body, retired, True, membership_masks(book.body, retired))
        d = DefenseMachine(self.image, self.master)
        d.install(splb.parse_book(changed, 134))
        normalized = d.normalize(changed)
        self.assertTrue(all(mask == 0 for mask in membership_masks(normalized, retired)))
        for seed in range(128):
            d.seed(seed+1)
            _, form = d.cpu_formation(offense_category=3, position=0.)
            self.assertTrue(0 <= form < 151)
            self.assertNotEqual(form, retired)
        print('PROVED defensive formation', retired, 'excluded across 128 native matching requests', flush=True)

    def test_added_and_cloned_heavy_sets_return_run_plays_at_goal_line(self):
        import struct
        donor = splb.read_book(INDEX, 1411)
        added = heavy_addition(splb.read_book(INDEX, 767), donor)
        for body in (donor.body, added.body, clone_body(added.body, 'J9 Heavy Run')):
            m = Machine(self.image, self.runtime)
            m.install(splb.parse_book(body, 767)); m.configure(); m.normalize()
            forms = set()
            for fraction in (.01, .5):
                m.configure(run_share=1., fraction=fraction)
                m.call(0x8486CE88, MANAGER, OUTPUT, stop=0x8486D0CC, bound=2000000)
                form = (m.get(OUTPUT+4)-MASTER-0x244)//184
                play = (m.get(OUTPUT+12)-MASTER-0x80C4)//100
                self.assertIn(form, (9, 5))
                self.assertTrue(0 <= play < 586)
                self.assertTrue(struct.unpack_from('>I', self.master, 0x80C4+play*100+8)[0] & 8)
                forms.add(form)
            self.assertEqual(forms, {9, 5})
            print('PROVED native GL run plays from Jacks/Jokers:', splb.parse_book(body, 767).name, flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
