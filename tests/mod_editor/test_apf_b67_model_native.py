"""Bounded retail-only model comparisons; no redistributable retail fixtures."""
from pathlib import Path
import os
import struct
import time
import unittest
from functools import lru_cache
import tempfile

from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from tools.apf_playcall_research_probe import Machine, MASTER, MANAGER, BOOK
from tests.mod_editor.test_apf_playcall_research_native import heavy_addition, category_candidates, INDEX


def inputs():
    try:
        import unicorn  # noqa: F401
    except ImportError as exc:
        raise unittest.SkipTest(f'Optional native dependency absent: {exc}')
    if not INDEX.is_file():
        raise unittest.SkipTest(f'Owned APF retail index absent: {INDEX}')
    pe = Path(os.environ.get('APF_RETAIL_PE', str(Path(tempfile.gettempdir()) / 'astra-coverage-17votk5s/base_reextracted.pe')))
    if pe.is_file():
        base = pe.read_bytes()
    else:
        from tests.mod_editor.test_apf_playcall_research_native import XEX
        if not XEX.is_file():
            raise unittest.SkipTest('Owned APF executable absent; set APF_RETAIL_PE or APF_RETAIL_XEX')
        from mod_editor.core.apf2k8_xex import decode_xex
        base, _ = decode_xex(XEX.read_bytes())
    master = read_master_play_body(INDEX)
    machine = Machine(base, master)
    machine.call(0x84A8AD38, MASTER, bound=16000000)
    runtime = bytes(machine.cpu.mem_read(MASTER, len(master)))
    return base, master, runtime


class ModelNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.master, cls.runtime = inputs()
        cls.machine = Machine(cls.base, cls.runtime)
        stock = splb.read_book(INDEX, 767)
        donor = splb.read_book(INDEX, 1411)
        added = heavy_addition(stock, donor)
        # P1's insertion preserves cached plays. Publish P2's normalized
        # representation for the edited-book matrix, as the new writers do.
        added = splb.parse_book(splb._compact_normalize(added.body), 767)
        edited = bytearray(added.body)
        for record in added.records:
            if record.populated:
                at = 0x70 + record.record_index * 176 + 168
                word = struct.unpack_from('>I', edited, at)[0]
                ratings = (record.formation_index % 8, 3, 6)
                word = (word & ~0x1FF00) | sum(v << s for v, s in zip(ratings, (14, 11, 8)))
                struct.pack_into('>I', edited, at, word)
        cls.books = (stock, donor, added, splb.parse_book(bytes(edited), 767))

    def test_category_formation_weights_and_uniform_draws(self):
        m = self.machine
        situations = [model.Situation(d, yards, goal, 1, 900, 0, 3)
                      for d in range(1, 5) for yards, goal in
                      ((1, 1), (2, 3), (3, 50), (4, 40), (5, 20),
                       (6, 35), (8, 50), (10, 50), (15, 70), (20, 95))]
        comparisons = 0
        tuples = 0
        def native_vector(address, args, pointer_offset, base, stride):
            captured = []
            def observe(z):
                count = z.reg(4)
                weights = struct.unpack('>' + str(count) + 'f', z.cpu.mem_read(z.reg(3), count * 4))
                for i, weight in enumerate(weights):
                    captured.append(((z.get(z.reg(1) + pointer_offset + i * 4) - MASTER - base) // stride, weight))
            m.observers[0x84863388] = observe
            m.call(address, *args, bound=2000000)
            del m.observers[0x84863388]
            return tuple(captured)
        @lru_cache(maxsize=65536)
        def native_draw(candidates, uniform, power):
            if not candidates:
                return None
            m.random_boundaries(uniform)
            m.cpu.mem_write(0x390000, struct.pack('>' + str(len(candidates)) + 'f', *(w for _, w in candidates)))
            return candidates[m.call(0x84863388, 0x390000, len(candidates), power)][0]
        def same_vector(a, b, context):
            self.assertEqual([p for p, w in a], [p for p, w in b], context)
            for (p, x), (_, y) in zip(a, b):
                self.assertAlmostEqual(x, y, delta=1e-6, msg=str((context, p, x, y)))
        for bi, book in enumerate(self.books):
            m.install(book)
            # In the proved empty-history/null-player B2D0 -> A860 -> 68C70
            # arm, down is not read. Reuse its native candidate vector when
            # the book, formation, category and rounded distance are identical.
            # All forty situations still compare every vector and 64 draws.
            play_cache = {}
            for s in situations:
                m.configure(down=s.down, yards=s.distance_yards, goal_yards=s.yards_to_goal, run_share=.5)
                row = m.call(m.va(0x84867600))
                self.assertEqual(row, model.requested_offense_row(s), (bi, s))
                _, native = category_candidates(m, row)
                expected = model.category_weights(book.body, self.master, row, s)
                self.assertEqual([c for c, _ in native], [c for c, _ in expected], (bi, s))
                for (c, a), (_, b) in zip(native, expected):
                    self.assertAlmostEqual(a, b, delta=1e-6, msg=str((bi, s, c, a, b)))
                formation_cache = {}
                for seed in range(64):
                    uniform = (seed + .5) / 64
                    category = native_draw(tuple(native), uniform, 3)
                    self.assertEqual(category, model.draw(expected, uniform, power=3))
                    comparisons += 1
                    if category not in formation_cache:
                        fv = native_vector(0x848693F8, (MANAGER, 14, MASTER + 0x44 + category * 16, 0, 0), 0xF0, 0x244, 184)
                        fm = model.formation_weights(book.body, self.master, category, s)
                        same_vector(fv, fm, (bi, s, category, 'formation'))
                        formation_cache[category] = fv, fm
                    fv, fm = formation_cache[category]
                    form = native_draw(fv, uniform, 1)
                    self.assertEqual(form, model.draw(fm, uniform))
                    if form is None:
                        continue
                    key = category, form, model._distance(s)
                    if key not in play_cache:
                        pv = native_vector(0x8486B2D0, (MANAGER, 8, MASTER + 0x244 + form * 184, MASTER + 0x44 + category * 16, 0), 0x50, 0x80C4, 100)
                        pm = tuple((p, w) for (p, variant), w in model.play_weights(book.body, self.master, form, s))
                        same_vector(pv, pm, (bi, s, category, form, 'play'))
                        play_cache[key] = pv, pm
                    pv, pm = play_cache[key]
                    self.assertEqual(native_draw(pv, uniform, 3), model.draw(pm, uniform, power=3), (bi, s, category, form))
                    tuples += 1
            print(f'Native tuple matrix book {bi + 1}/4 passed', flush=True)
        print(f'PROVED category vectors: 40 situations x 4 books; native uniform draws: {comparisons}', flush=True)
        print(f'PROVED native category/formation/play tuples from captured native vectors: {tuples}', flush=True)

    def test_preview_performance(self):
        start = time.perf_counter()
        result = model.predict_offense(self.books[2].body, self.master, .5, model.Situation(3, 8, 50, 1, 900, 0, 3))
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, .5)
        self.assertTrue(result.categories)
        print(f'Preview 256 seeds: {elapsed:.4f} seconds', flush=True)

    def test_situation_row_and_run_adjustment_boundaries(self):
        m = self.machine
        m.install(self.books[0])
        for down in range(1, 5):
            for yards in (1, 2, 3, 8, 9, 10, 11, 11.5, 12, 15):
                for score in (-7, 0, 7):
                    s = model.Situation(down, yards, 50, 1, 900, score, 3)
                    m.configure(down=down, yards=yards, goal_yards=50, score=score)
                    m.setfpr(1, .5)
                    m.call(0x8486A1F8)
                    self.assertAlmostEqual(m.fpr(1), model.adjusted_run_share(.5, s), delta=1e-6, msg=str(s))
                    self.assertEqual(m.call(0x84867600), model.requested_offense_row(s), s)

    def test_formation_and_play_vectors(self):
        m = self.machine
        s = model.Situation(3, 8, 50, 1, 900, 0, 3)
        for book in self.books:
            m.install(book)
            m.configure(down=3, yards=8, goal_yards=50, run_share=0)
            for record in book.records:
                if not record.populated:
                    continue
                form = MASTER + 0x244 + 184 * record.formation_index
                for category_mode in (False, True):
                    m.call(0x84869058, MANAGER, form, int(category_mode))
                    self.assertAlmostEqual(m.fpr(1), model.formation_weight(record, self.master, s, category=category_mode, run_share=0), delta=1e-6)
                for entry in record.entries:
                    got = m.call(0x84A87B38, MASTER + 0x80C4 + 100 * entry.play_index)
                    if got == 0xFFFFFFFF:
                        got = -1
                    self.assertEqual(got, model.play_carrier_slot(self.master, entry.play_index), entry.play_index)
            # Capture the actual B2D0 candidate buffer immediately before its
            # power-three lottery, including the native 39-entry overflow.
            record = book.records[0]
            captured = []
            def observe(z):
                count = z.reg(4)
                weights = struct.unpack('>' + str(count) + 'f', z.cpu.mem_read(z.reg(3), count * 4))
                sp = z.reg(1)
                for i, w in enumerate(weights):
                    play = (z.get(sp + 0x50 + i * 4) - MASTER - 0x80C4) // 100
                    captured.append((play, w))
            m.observers[0x84863388] = observe
            m.call(0x8486B2D0, MANAGER, 8, MASTER + 0x244 + 184 * record.formation_index,
                   MASTER + 0x44 + 16 * record.category_index, 0, bound=2000000)
            del m.observers[0x84863388]
            expected = model.play_weights(book.body, self.master, record.formation_index, s, run_share=0)
            self.assertEqual([p for p, w in captured], [p for (p, v), w in expected])
            for (p, a), (_, b) in zip(captured, expected):
                self.assertAlmostEqual(a, b, delta=1e-6, msg=str((book.name, p, a, b)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
