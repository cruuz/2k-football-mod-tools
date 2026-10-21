"""b77 cr1: crowd people keep the retail proportion on every modern venue billboard (no squashed or stretched fans)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np

from mod_editor.core import nfl2k5_metlife_model as mm

TOL = 0.15


def crowd_rows(model):
    """(texel aspect, person strip height m, shown fraction, area) for every visible crowd triangle of a built model."""
    rows = []
    for mesh in model.meshes.values():
        P, UV = np.asarray(mesh.P), np.asarray(mesh.UV)
        for strip in mesh.groups.get("crowd", ()):
            for k in range(len(strip) - 2):
                tri = list(strip[k:k + 3])
                p, t = P[tri], UV[tri]
                e = np.stack([p[1] - p[0], p[2] - p[0]], 1)
                area = 0.5 * np.linalg.norm(np.cross(e[:, 0], e[:, 1]))
                if area < 1e-6:
                    continue
                T = np.stack([t[1] - t[0], t[2] - t[0]], 1)
                det = np.linalg.det(T)
                assert abs(det) > 1e-12, "a visible crowd triangle has a degenerate UV map"
                J = e @ np.linalg.inv(T)
                mu, mv = np.linalg.norm(J[:, 0]), np.linalg.norm(J[:, 1])
                rows.append((mv / mu, mm.CROWD_STRIP * mu, np.ptp(t[:, 0]) / mm.CROWD_STRIP, area))
    return np.asarray(rows)


class HelperTests(unittest.TestCase):
    def test_a_typical_billboard_shows_one_whole_person(self):
        bottom, top = (0.0, 0.0, 0.0), (0.0, 2.2, 0.0)
        ub, ut = mm.crowd_u(0.25, bottom, top)
        self.assertAlmostEqual(ut, 0.25 + mm.CROWD_MARGIN)
        self.assertAlmostEqual(ub, 0.5 - mm.CROWD_MARGIN)

    def test_a_short_billboard_crops_never_squeezes(self):
        for h in (0.0, 0.06, 0.5, 1.2, 1.9):
            ub, ut = mm.crowd_u(0.0, (0, 0, 0), (0, h, 0))
            self.assertAlmostEqual(ut, mm.CROWD_MARGIN)                 # heads at the top
            if h:
                metres_per_u = h / (ub - ut)
                self.assertAlmostEqual(metres_per_u * mm.CROWD_STRIP, mm.CROWD_PERSON_M[0], places=9)

    def test_a_tall_billboard_draws_a_taller_person_up_to_the_retail_maximum(self):
        ub, ut = mm.crowd_u(0.0, (0, 0, 0), (0, 2.8, 0))
        self.assertAlmostEqual(ub - ut, mm.CROWD_STRIP - 2 * mm.CROWD_MARGIN)
        self.assertAlmostEqual(mm.crowd_person_m(2.8), 2.8 / 0.94)
        self.assertEqual(mm.crowd_person_m(5.0), mm.CROWD_PERSON_M[1])

    def test_v_follows_the_column_person_size(self):
        bot = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (20.0, 0.0, 0.0)]
        top = [(0.0, 2.2, 0.0), (10.0, 2.2, 0.0), (20.0, 2.2, 0.0)]
        vs = mm.crowd_band_v(bot, top, 1.5)
        dens = mm.CROWD_ASPECT * mm.crowd_person_m(2.2) / mm.CROWD_STRIP
        self.assertAlmostEqual(vs[0], 1.5)
        self.assertAlmostEqual(vs[2] - vs[0], 20.0 / dens)


class ModelTests(unittest.TestCase):
    def check(self, rows, *, tall_allowance=0):
        aspect, person = rows[:, 0], rows[:, 1]
        off = np.abs(aspect / mm.CROWD_ASPECT - 1.0) > TOL
        self.assertEqual(int(off.sum()), 0, f"aspect outside 15%: {np.sort(aspect[off])[:5]} .. {np.sort(aspect[off])[-5:]}")
        self.assertGreaterEqual(person.min(), mm.CROWD_PERSON_M[0] - 1e-6, "a person is drawn smaller than retail")
        self.assertLessEqual(int((person > mm.CROWD_PERSON_M[1] + 1e-6).sum()), tall_allowance)

    def test_metlife_fans_are_not_stretched_along_the_upper_rows(self):
        self.check(crowd_rows(mm.build("s18")))

    def test_sofi_fans_keep_the_retail_proportion(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        self.check(crowd_rows(sm.build("s23")))

    def test_att_fans_keep_the_retail_proportion(self):
        from mod_editor.core import nfl2k5_att_model as am
        rows = crowd_rows(am.build("s07"))
        # AT&T's corner billboards up to 3.52 m slant exceed the tallest retail person strip (3.404 m * 0.94): those
        # 38 triangles show a whole person stretched at most 10 percent tall; the aspect still holds within 15%.
        self.assertLessEqual(rows[:, 1].max(), 3.75)
        aspect = rows[:, 0]
        self.assertLessEqual(int((np.abs(aspect / mm.CROWD_ASPECT - 1.0) > TOL).sum()), 2)
        self.assertGreaterEqual(rows[:, 1].min(), mm.CROWD_PERSON_M[0] - 1e-6)


if __name__ == "__main__":
    unittest.main()
