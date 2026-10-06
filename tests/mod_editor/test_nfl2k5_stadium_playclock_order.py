"""The native tens material must appear left of ones at both end walls."""
import importlib
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_scne_builder as sb


MODELS = ('sofi', 'att', 'highmark', 'levis', 'allegiant', 'mercedes_benz',
          'usbank', 'lucas_oil', 'state_farm', 'hard_rock', 'gillette', 'lambeau', 'everbank')


def fixture(pairs=2):
    record = bytearray(0x100)
    struct.pack_into('<4f', record, 0x30, 1., 1., 0., 0.)
    struct.pack_into('<I', record, 0x44, 2)
    struct.pack_into('<H', record, 0x4c, pairs * 8)
    struct.pack_into('<HH', record, 0xc4, 12, 10)
    for index, value in ((0, 0x32), (1, 0x80115), (3, 0x140), (6, 0x40121)):
        struct.pack_into('<I', record, 0x84 + index * 4, value)
    subs = []
    for material in range(2):
        sub = bytearray(0x80)
        struct.pack_into('<H', sub, 0, material)
        subs.append(sb.Submesh(sub, sb.encode_words(sb.QUADS, range(material * pairs * 4, (material + 1) * pairs * 4))))
    uv = b''.join(struct.pack('<4B3h', 255, 255, 255, 255, u, v, 0)
                  for _ in range(pairs * 2) for u, v in ((0, 256), (0, 0), (256, 256), (256, 0)))
    shape = sb.Shape(record, 'digits', [], subs, [bytes(pairs * 8 * 12), uv] + [None] * 6)
    materials = [SimpleNamespace(name='digit_playclock_' + side) for side in ('L', 'R')]
    sc = SimpleNamespace(materials=materials, shapes=[shape], shape=lambda name: shape)
    zero = np.zeros(3)
    frame = dict(centre=zero, right=np.array([1., 0., 0.]), face=np.array([0., 0., 1.]),
                 width=20., height=10., panels=[zero, zero], wing=(10., 8.), feed=False, angle=0.,
                 panel_top_left=zero, t=np.array([1., 0., 0.]), n=np.array([0., 0., 1.]))
    model = SimpleNamespace(p=dict(loop=dict(L=70., zn=70., zs=70., ze=70., zw=70.),
                                   screen=dict(outer=10.), board=dict(bottom=10., end_h=10., side_w=20.),
                                   boards=dict(panel_w=4.), halo=dict(h=10.)),
                            board_frames=[frame, frame], halo_frames=[frame, frame],
                            screen_point=lambda *args: (zero, frame['face'], frame['right']))
    return shape, sc, model


class PlayClockOrderTests(unittest.TestCase):
    def check_walls(self, shape, sc):
        positions = np.frombuffer(shape.streams[0], dtype='<f4').reshape(-1, 3)
        centres = {}
        for sub in shape.submeshes:
            name = sc.materials[sub.material].name
            ids = sorted({i for _, indices in sb.decode_words(sub.words) for i in indices})
            for start in range(0, len(ids), 4):
                points = positions[ids[start:start + 4]]
                centre = points.mean(axis=0)
                if abs(centre[2]) < 5000:
                    continue
                zs = 1 if centre[2] > 0 else -1
                centres[name, zs] = float(centre @ np.array([-zs, 0., 0.]))
                self.assertAlmostEqual(float(np.ptp(points[:, 0])), 150., places=3)
                self.assertAlmostEqual(float(np.ptp(points[:, 1])), 220., places=3)
                u = np.array([struct.unpack_from('<h', shape.streams[1], i * 10 + 4)[0]
                              for i in ids[start:start + 4]])
                glyph_right = points[u > u.mean()].mean(0) - points[u < u.mean()].mean(0)
                self.assertGreater(float(glyph_right @ np.array([-zs, 0., 0.])), 0.,
                                   'each glyph must remain unmirrored')
        for zs in (1, -1):
            self.assertAlmostEqual(centres['digit_playclock_L', zs], -90., places=3)
            self.assertAlmostEqual(centres['digit_playclock_R', zs], 90., places=3)

    def test_every_stadium_compiler_uses_tens_then_ones(self):
        for name in MODELS:
            with self.subTest(model=name):
                module = importlib.import_module('mod_editor.core.nfl2k5_' + name + '_model')
                shape, scene, model = fixture()
                before_uv = shape.streams[1]
                module.adjust_digits(shape, scene, model)
                self.check_walls(shape, scene)
                self.assertEqual(shape.streams[1], before_uv)

    def test_metlife_board_clocks_and_endwall_clocks(self):
        from mod_editor.core import nfl2k5_metlife_model as module
        _, scene, model = fixture()
        module.adjust_kept(scene, model, {})
        self.check_walls(scene.shapes[0], scene)

    def test_donors_with_three_or_four_pairs_keep_every_clock_in_order(self):
        for name, pairs in (('lucas_oil', 3), ('everbank', 3), ('hard_rock', 4)):
            with self.subTest(model=name):
                module = importlib.import_module('mod_editor.core.nfl2k5_' + name + '_model')
                shape, scene, model = fixture(pairs)
                module.adjust_digits(shape, scene, model)
                self.check_walls(shape, scene)
                self.assertEqual(shape.vertex_count, pairs * 8)


if __name__ == '__main__':
    unittest.main()
