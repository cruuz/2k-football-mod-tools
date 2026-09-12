"""Defensive component gates and conditional empty-history X products."""
import struct
import unittest
from functools import lru_cache

from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core import apf2k8_splb_writer as splb
from tools.apf_defense_native_probe import DefenseMachine, added_book
from tools.apf_playcall_research_probe import Machine, MASTER, MANAGER, TEAM
from tests.mod_editor.test_apf_b67_model_native import inputs, INDEX
from tests.mod_editor.test_apf_playcall_research_native import category_candidates


class DefenseModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.master, cls.runtime = inputs()

    def test_native_pair_supply_and_conditional_x_products(self):
        book = splb.read_book(INDEX, 134)
        d = DefenseMachine(self.base, self.master)
        d.install(book)
        d.initialize_plays(self.master, [e.play_index for r in book.records for e in r.entries])
        native = d.play_candidates(11, 141)
        expected = model.defense_pairs(book.body, self.master, 141)
        self.assertEqual([(p['first_play'], tuple(p['compatible_second_plays'])) for p in native], list(expected))
        m = Machine(self.base, self.runtime)
        m.install(book)
        m.configure()
        m.put(TEAM + 8, MASTER + 0x244)
        for first, partners in expected:
            for second in partners:
                m.setfpr(1, 4.)
                m.call(0x84863F58, MANAGER, MASTER + 0x244 + 141 * 184,
                       MASTER + 0x80C4 + first * 100, MASTER + 0x80C4 + second * 100)
                self.assertAlmostEqual(m.fpr(1), model.defense_pair_weight(book.body, self.master, 141, first, second), delta=1e-6)
        self.assertEqual(sum(len(p) for _, p in expected), 192)
        print('PROVED 192 native defensive component pairs and X products conditional on supplied lineup feature 4; feature default remains HYPOTHESIS', flush=True)

    def test_defensive_category_matrix(self):
        stock, donor = splb.read_book(INDEX, 134), splb.read_book(INDEX, 618)
        books = (stock, donor, added_book(stock, donor.records[0], 147, 23), added_book(stock, donor.records[0], 150, 27))
        m = Machine(self.base, self.runtime)
        for book in books:
            m.install(book)
            for situation in range(40):
                offense_row, goal = situation % 11, (1, 5, 20, 50)[situation // 10]
                s = model.Situation(1, 10, goal, 1, 900, 0, 3)
                m.configure(yards=10, goal_yards=goal)
                row = m.call(0x84869B60, offense_row)
                self.assertEqual(row, model.requested_defense_row(offense_row, goal))
                _, native = category_candidates(m, row)
                expected = model.category_weights(book.body, self.master, row, s)
                self.assertEqual([p for p, _ in native], [p for p, _ in expected])
                for (_, a), (_, b) in zip(native, expected):
                    self.assertAlmostEqual(a, b, delta=1e-6)
                for seed in range(64):
                    uniform = (seed + .5) / 64
                    m.random_boundaries(uniform)
                    m.cpu.mem_write(0x390000, struct.pack('>' + str(len(native)) + 'f', *(w for _, w in native)))
                    index = m.call(0x84863388, 0x390000, len(native), 3)
                    self.assertEqual(native[index][0], model.draw(expected, uniform, power=3))
        print('PROVED defensive categories: 40 situations x 4 books x 64 uniform draws', flush=True)

    def test_cold_special_request_rows(self):
        m = Machine(self.base, self.runtime)
        for offense_row in range(11, 28):
            for goal in (1, 50, 95):
                m.configure(yards=10, goal_yards=goal)
                self.assertEqual(m.call(0x84869B60, offense_row), model.requested_defense_row(offense_row, goal))

    def test_conditional_defensive_full_tuple_matrix(self):
        stock, donor = splb.read_book(INDEX, 134), splb.read_book(INDEX, 618)
        added = tuple(splb.parse_book(splb._compact_normalize(added_book(stock, donor.records[0], form, cat).body), 134)
                      for form, cat in ((147, 23), (150, 27)))
        books = (stock, donor, *added)
        m = Machine(self.base, self.runtime)
        # The API does not identify the opponent's selected play or lineup.
        # Bound only that evaluator, explicitly, to the model's hypothesis.
        def supplied_feature(z):
            z.setfpr(1, 4.)
            z.ret(0)
        m.boundaries[0x84865AE0] = supplied_feature
        m.put(TEAM + 8, MASTER + 0x244)
        @lru_cache(maxsize=32768)
        def draw(vector, uniform, power):
            m.random_boundaries(uniform)
            m.cpu.mem_write(0x390000, struct.pack('>' + str(len(vector)) + 'f', *(w for _, w in vector)))
            return vector[m.call(0x84863388, 0x390000, len(vector), power)][0]
        def vector(address, args, base, stride):
            result = []
            def capture(z):
                result.extend(((z.get(z.reg(1) + 0xF0 + i * 4) - MASTER - base) // stride,
                               struct.unpack('>f', z.cpu.mem_read(z.reg(3) + i * 4, 4))[0])
                              for i in range(z.reg(4)))
            m.observers[0x84863388] = capture
            returned = m.call(address, *args, bound=2000000)
            del m.observers[0x84863388]
            if not result and returned:
                result = [((returned - MASTER - base) // stride, 1.)]
            return tuple(result)
        def equal(a, b):
            self.assertEqual([p for p, _ in a], [p for p, _ in b])
            for (_, x), (_, y) in zip(a, b):
                self.assertAlmostEqual(x, y, delta=1e-6)
        count = 0
        for book in books:
            m.install(book)
            formations, firsts, seconds = {}, {}, {}
            for situation in range(40):
                offense_row, goal = situation % 11, (1, 5, 20, 50)[situation // 10]
                s = model.Situation(1, 10, goal, 1, 900, 0, 3)
                m.configure(yards=10, goal_yards=goal)
                row = model.requested_defense_row(offense_row, goal)
                _, native_categories = category_candidates(m, row)
                categories = model.category_weights(book.body, self.master, row, s)
                equal(native_categories, categories)
                for seed in range(64):
                    u = (seed + .5) / 64
                    cat = draw(tuple(native_categories), u, 3)
                    self.assertEqual(cat, model.draw(categories, u, power=3))
                    if cat not in formations:
                        formations[cat] = vector(0x848693F8, (MANAGER, 14, MASTER + 0x44 + cat * 16, 0, 0), 0x244, 184)
                    forms = model.formation_weights(book.body, self.master, cat, s)
                    equal(formations[cat], forms)
                    form = draw(formations[cat], u, 1)
                    self.assertEqual(form, model.draw(forms, u))
                    fp, cp = MASTER + 0x244 + form * 184, MASTER + 0x44 + cat * 16
                    pairs = dict(model.defense_pairs(book.body, self.master, form))
                    expected = model.defense_play_weights(book.body, self.master, form)
                    if form not in firsts:
                        firsts[form] = vector(0x8486C448, (MANAGER, cp, fp), 0x80C4, 100)
                    equal(firsts[form], expected)
                    self.assertTrue(expected, (book.name, situation, cat, form))
                    first = draw(firsts[form], u, 3)
                    self.assertEqual(first, model.draw(expected, u, power=3))
                    key = form, first
                    expected = model.defense_play_weights(book.body, self.master, form, first)
                    if key not in seconds:
                        seconds[key] = vector(0x8486C6C8, (MANAGER, MASTER + 0x80C4 + first * 100, fp, cp), 0x80C4, 100)
                    equal(seconds[key], expected)
                    self.assertEqual(draw(seconds[key], u, 3), model.draw(expected, u, power=3))
                    count += 1
        self.assertEqual(count, 40 * 4 * 64)
        print('PROVED 10240 defensive category/formation/component tuples conditional on supplied feature 4; live evaluator remains outside this proof', flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
