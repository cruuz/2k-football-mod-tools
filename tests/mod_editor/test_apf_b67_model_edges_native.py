"""Stored-cache and run/pass edges exposed by the expanded P3 native sweep."""
import struct
import unittest

from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core import apf2k8_splb_writer as splb
from tests.mod_editor.test_apf_b67_model_native import inputs, INDEX
from tests.mod_editor.test_apf_playcall_research_native import heavy_addition
from tools.apf_playcall_research_probe import Machine, MASTER, MANAGER


class ModelEdgeTests(unittest.TestCase):
    def test_inserted_memberships_cache_and_run_pass_gates(self):
        base, master, runtime = inputs()
        m = Machine(base, runtime)
        added = heavy_addition(splb.read_book(INDEX, 767), splb.read_book(INDEX, 1411))
        normalized = splb.parse_book(splb._compact_normalize(added.body), 767)
        s = model.Situation(1, 1, 1, 1, 900, 0, 3)
        counts = []
        for book in (added, normalized):
            for share in (0., .5, 1.):
                m.install(book)
                m.configure(run_share=share)
                native = []
                def capture(z):
                    for i in range(z.reg(4)):
                        play = (z.get(z.reg(1) + 0x50 + i * 4) - MASTER - 0x80C4) // 100
                        weight = struct.unpack('>f', z.cpu.mem_read(z.reg(3) + i * 4, 4))[0]
                        native.append((play, weight))
                m.observers[0x84863388] = capture
                m.call(0x8486B2D0, MANAGER, 8, MASTER + 0x244 + 9 * 184, MASTER + 0x44, 0, bound=2000000)
                del m.observers[0x84863388]
                expected = tuple((p, w) for (p, variant), w in model.play_weights(book.body, master, 9, s, run_share=share))
                self.assertEqual([p for p, _ in native], [p for p, _ in expected])
                for (_, a), (_, b) in zip(native, expected):
                    self.assertAlmostEqual(a, b, delta=1e-6)
                for seed in range(64):
                    uniform = (seed + .5) / 64
                    m.random_boundaries(uniform)
                    m.cpu.mem_write(0x390000, struct.pack('>' + str(len(native)) + 'f', *(w for _, w in native)))
                    chosen = m.call(0x84863388, 0x390000, len(native), 3)
                    self.assertEqual(native[chosen][0], model.draw(expected, uniform, power=3))
                if share == .5:
                    counts.append(len(native))
        self.assertEqual(counts, [8, 28])
        self.assertTrue(any('stored play cache' in n for n in model.predict_offense(added.body, master, .5, s).notes))
        print('PROVED added Jacks: 8 cached candidates before normalization, 28 after; run/pass endpoints and 384 uniform draws agree', flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
