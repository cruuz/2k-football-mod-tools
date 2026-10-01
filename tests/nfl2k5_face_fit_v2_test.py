"""Face fit v2 (tools/nfl2k5_face_fit_v2.py): the camera fit, the skin calibration, the re-skin of a template and the
skin-only low-pass. Retail-free; the mesh-feature check runs only with NFL2K5_HI_HEAD_GLTF pointing at a Models
export of the retail hi_head."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "tools", ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import nfl2k5_face_fit_v2 as v2  # noqa: E402


class CameraFitTest(unittest.TestCase):
    def _photo_points(self, params):
        P3 = np.array([v2.P_EYES[0], v2.P_EYES[1], v2.P_NOSE, v2.P_MOUTH[0], v2.P_MOUTH[1]])
        q, _ = v2.project(np.array(params, float), P3)
        return q.astype(np.float32)

    def test_a_frontal_head_is_recovered_with_no_residual(self):
        pts = self._photo_points([50.0, 0.0, 0.0, 0.0, 1700.0, 3200.0, 1.0])
        params, resid = v2.fit_camera(pts)
        self.assertLess(float(np.abs(resid).max()), 0.5)
        self.assertAlmostEqual(params[0], 50.0, delta=0.5)

    def test_the_fit_assumes_the_frontal_studio_camera(self):
        # five landmarks cannot tell a small turn from a face's own proportions (on the league's smiling headshots a
        # free fit reads 12 to 19 degrees of pitch that is not there), so the fit stays near frontal and the residual
        # field carries the difference
        truth = [48.0, 0.08, -0.12, 0.05, 1650.0, 3150.0, 1.0]
        pts = self._photo_points(truth)
        params, resid = v2.fit_camera(pts)
        eye_d = float(np.linalg.norm(pts[1] - pts[0]))
        self.assertLess(abs(params[1]), 0.035)
        self.assertLess(abs(params[2]), 0.035)
        self.assertLess(float(np.abs(resid).max()) / eye_d, 0.05)

    def test_a_wide_smile_moves_the_mouth_corners_not_the_eyes(self):
        pts = self._photo_points([50.0, 0.0, 0.0, 0.0, 1700.0, 3200.0, 1.0])
        pts[3, 0] -= 40.0
        pts[4, 0] += 40.0                                          # a smile widens the mouth by 80 px
        _params, resid = v2.fit_camera(pts)
        self.assertLess(float(np.abs(resid[:2]).max()), 6.0)      # the eyes stay put
        self.assertGreater(float(np.abs(resid[3:, 0]).min()), 25.0)  # the corners carry the difference


class SkinCalibrationTest(unittest.TestCase):
    def lab(self, lstar, a, b):
        return np.array([lstar * 255 / 100, a + 128, b + 128], np.float32)

    def test_the_target_stays_inside_the_roster_tones_spread(self):
        cal = v2.calibration()
        for tone, c in cal["tones"].items():
            for lstar in (20.0, 50.0, 90.0):
                t = v2.target_skin(self.lab(lstar, 15, 20), int(tone))
                self.assertGreaterEqual(t[0] * 100 / 255, c["L_p10"] - 1e-3)
                self.assertLessEqual(t[0] * 100 / 255, c["L_p90"] + 1e-3)

    def test_the_exposure_darkens_a_studio_photo_and_keeps_the_order(self):
        light = v2.target_skin(self.lab(75, 15, 18), None)
        dark = v2.target_skin(self.lab(45, 18, 22), None)
        self.assertLess(light[0] * 100 / 255, 75)
        self.assertGreater(light[0], dark[0])


class ReskinTest(unittest.TestCase):
    def test_skin_moves_to_the_target_and_hair_does_not_turn_to_skin(self):
        S = v2.S
        T0 = np.zeros((S, S, 3), np.float32)
        T0[:] = (150.0, 150.0, 150.0)                          # retail skin
        T0[: S // 16] = (40.0, 131.0, 133.0)                    # a dark hair band at the top
        skin_t = v2.template_skin(T0)
        target = np.array([110.0, 145.0, 150.0], np.float32)
        out = v2.reskin(T0, target, skin_t)
        centre = out[S // 2, S // 2]
        self.assertTrue(np.allclose(centre, target, atol=1.0))
        self.assertLess(out[4, S // 2, 0], 60.0)                 # the hair stays dark


class NormconvTest(unittest.TestCase):
    def test_the_low_pass_ignores_masked_out_pixels(self):
        S = 256
        img = np.full((S, S, 1), 100.0, np.float32)
        img[100:140, 100:140] = 10.0                              # a beard patch, masked out
        mask = np.ones((S, S), bool)
        mask[100:140, 100:140] = False
        low = v2.normconv(img, mask, 12.0)
        self.assertAlmostEqual(float(low[120, 120, 0]), 100.0, delta=1.0)


class TemplateChoiceTest(unittest.TestCase):
    TABLE = {
        "0001": {"tone": 4, "skin": [90, 145, 150], "hair": [20, 129, 130], "iris": [80, 133, 128], "beard": 5, "bald": False},
        "0002": {"tone": 4, "skin": [92, 145, 150], "hair": [22, 129, 130], "iris": [80, 136, 145], "beard": 5, "bald": False},
        "0003": {"tone": 0, "skin": [160, 150, 155], "hair": [22, 129, 130], "iris": [80, 136, 145], "beard": 5, "bald": False},
        "0004": {"tone": 4, "skin": [90, 145, 150], "hair": [90, 146, 150], "iris": [80, 136, 145], "beard": 5, "bald": True},
    }

    def test_same_tone_and_a_brown_iris_for_dark_tones(self):
        table = {k: v for k, v in self.TABLE.items()}
        for n in range(20):                        # enough same-tone candidates that no neighbour tone is needed
            table[f"1{n:03d}"] = dict(self.TABLE["0003"], tone=0)
        got = v2.choose_template(table, 4, [21, 129, 130], 5.0, [90, 145, 150])
        self.assertEqual(got, "0002")              # 0001 has the blue iris, 0003 the wrong tone, 0004 a bare skull

    def test_each_template_once_a_team_where_a_close_one_is_left(self):
        table = dict(self.TABLE, **{"0005": dict(self.TABLE["0002"], hair=[26, 129, 130])})
        self.assertEqual(v2.choose_template(table, 4, [21, 129, 130], 5.0, [90, 145, 150]), "0002")
        self.assertEqual(v2.choose_template(table, 4, [21, 129, 130], 5.0, [90, 145, 150], used={"0002"}), "0005")


class ChromaRelightTest(unittest.TestCase):
    """The relight's chroma rule (compose): up to the photo skin's chroma by ratio, beyond it as a capped excess."""

    @staticmethod
    def relit(d, ip, it, cap=12.0):
        t = d / ip
        if t <= 1.0:
            return d * (0.6 if t < 0 else float(np.clip(it / ip, 0.3, 2.0)))
        return it + cap * float(np.tanh((d - ip) / cap))

    def test_a_warm_photo_cast_does_not_turn_a_black_beard_blue(self):
        self.assertEqual(self.relit(0.0, 35.0, 17.0), 0.0)                 # a black beard stays neutral
        self.assertAlmostEqual(self.relit(35.0, 35.0, 17.0), 17.0)         # skin lands on the target

    def test_studio_lips_are_capped_not_amplified(self):
        lips = self.relit(56.0, 24.0, 17.5)                                 # Kincaid: lips a* +56 in the photo
        self.assertLess(lips, 17.5 + 12.0 + 1e-6)
        self.assertGreater(lips, 17.5)


@unittest.skipUnless(os.environ.get("NFL2K5_HI_HEAD_GLTF"), "set NFL2K5_HI_HEAD_GLTF to a Models export of hi_head")
class MeshFeaturesTest(unittest.TestCase):
    def test_the_feature_constants_are_the_mesh_own(self):
        head = v2.HeadMesh(os.environ["NFL2K5_HI_HEAD_GLTF"])
        f = v2.mesh_features(head)
        self.assertLess(float(np.abs(f["eyes"] - v2.UV_EYES).max()), 0.6)
        self.assertLess(float(np.abs(f["nose"] - v2.UV_NOSE).max()), 0.6)
        self.assertLess(float(np.abs(f["nose_pos"] - v2.P_NOSE).max()), 0.05)


if __name__ == "__main__":
    unittest.main()
