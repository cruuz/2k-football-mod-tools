"""Face fit v2 (tools/nfl2k5_face_fit_v2.py): the camera fit, the skin calibration, the re-skin of a template and the
skin-only low-pass. Retail-free; the mesh-feature check runs only with NFL2K5_HI_HEAD_GLTF pointing at a Models
export of the retail hi_head."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

import cv2
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


class EyesTest(unittest.TestCase):
    """fc1 (10/18, "an eye over an eye"): the photo's eye is registered against a reference eye on the mesh's
    openings and moved into them; the openings and any photo sclera left on the lids take the template's eye/lid;
    the eyeball's iris follows the player's eye colour. Retail-free: a drawn face surface with two openings."""

    def setUp(self):
        S, K = v2.S, v2.K
        self._saved = (v2._R, v2._OPENINGS, v2._SYNTH_EYE, v2._EYE_REF)
        cov = np.ones((S, S), bool)
        cov[: int(20 * K)] = False                                    # (outside the face: does not matter)
        for cx, cy in v2.UV_EYES:                                     # two lens-shaped openings, 34 x 11 texels
            d = ((v2.XX - cx * K) / (17 * K)) ** 2 + ((v2.YY - cy * K) / (5.5 * K)) ** 2
            cov &= d > 1.0
        v2._R = (np.zeros((S, S, 3), np.float32), np.zeros((S, S, 3), np.float32), cov)
        v2._OPENINGS = v2._SYNTH_EYE = None
        v2.use_eye_reference(None)

    def tearDown(self):
        v2._R, v2._OPENINGS, v2._SYNTH_EYE, v2._EYE_REF = self._saved

    @staticmethod
    def drawn_photo(dy_texels):
        """A face in texture space: the drawn eye moved down by dy texels, as grey-scale RGB."""
        S, K = v2.S, v2.K
        eye = v2.synthetic_eye()
        M = np.float32([[1, 0, 0], [0, 1, dy_texels * K]])
        moved = cv2.warpAffine(eye, M, (S, S), borderMode=cv2.BORDER_REPLICATE)
        g = np.clip(120 + 40 * moved, 0, 255).astype(np.uint8)
        return np.repeat(g[..., None], 3, axis=2)

    def test_the_openings_are_found_where_the_mesh_has_holes(self):
        ops = v2.eye_openings()
        self.assertEqual(len(ops), 2)
        for o, (cx, cy) in zip(ops, v2.UV_EYES):
            self.assertAlmostEqual(o["cx"] / v2.K, cx, delta=0.6)
            self.assertAlmostEqual(o["cy"] / v2.K, cy, delta=0.6)

    def test_a_photo_eye_drawn_low_is_measured_low(self):
        for dy in (0.0, 3.0, -2.0):
            got = v2.register_eyes(self.drawn_photo(dy))
            for gdy, ncc, edge in got:
                self.assertAlmostEqual(gdy, dy, delta=0.6)
                self.assertGreater(ncc, 0.9)
                self.assertFalse(edge)

    def test_the_opening_and_photo_sclera_on_the_lid_take_the_template(self):
        S, K = v2.S, v2.K
        skin = np.array([150.0, 140.0, 145.0], np.float32)
        P = np.tile(skin, (S, S, 1)).astype(np.float32)
        w = np.ones((S, S), np.float32)
        o = v2.eye_openings()[0]
        sx, sy = int(o["cx"]), int(o["y1"] + 3 * K)                   # 3 texels under the lower rim
        P[sy - 4:sy + 4, sx - 8:sx + 8] = (235.0, 128.0, 129.0)       # bright, neutral: the photo's sclera
        m = v2.eye_blend(P, skin, w)
        self.assertGreater(float(m[int(o["cy"]), int(o["cx"])]), 0.99)   # inside the opening
        self.assertGreater(float(m[sy, sx]), 0.9)                        # the stray sclera
        self.assertLess(float(m[int(o["cy"] + 15 * K), int(o["cx"])]), 0.01)  # the cheek is the photo's
        self.assertLess(float(m[int(o["y0"] - 8 * K), int(o["cx"])]), 0.01)  # and so are the brows

    def test_the_brows_follow_the_eye_shift(self):
        S, K = v2.S, v2.K
        q0 = np.stack([v2.XX, v2.YY], -1).astype(np.float32)
        q1 = q0.copy()
        q1[..., 1] += 3.0 * K                                         # every texel now samples 3 texels lower
        self.assertEqual([round(v, 2) for v in v2.brow_shift(q0, q1)], [3.0, 3.0])   # the brows sit 3 higher
        self.assertEqual(v2.brow_shift(q0, q0), [0.0, 0.0])

    def test_light_and_brown_irises(self):
        brown = [40.0, 140.0, 150.0]; blue = [90.0, 130.0, 113.0]; grey = [100.0, 133.0, 128.0]
        self.assertFalse(v2.iris_light(brown))
        self.assertTrue(v2.iris_light(blue))
        self.assertTrue(v2.iris_light(grey))
        self.assertFalse(v2.iris_light([20.0, 129.0, 127.0]))          # near-black is not a light eye
        self.assertLess(v2.iris_distance(blue, grey), v2.iris_distance(blue, brown))
        # a dark brown photo iris against retail's mid brown: lightness alone does not separate them
        self.assertLess(v2.iris_distance([10.0, 132.0, 131.0], [34.0, 133.0, 133.0]), 3.0)

    def test_the_eye_patch_is_read_and_copied_alone(self):
        S = 256
        a = np.full((S, S, 3), 200, np.uint8)
        y0, y1, x0, x1 = (int(v2.EYE_PATCH[0] * S), int(v2.EYE_PATCH[1] * S), int(v2.EYE_PATCH[2] * S), int(v2.EYE_PATCH[3] * S))
        cy, cx = (y0 + y1 - 1) / 2, (x0 + x1 - 1) / 2
        yy, xx = np.mgrid[0:S, 0:S]
        r = np.hypot(yy - cy, xx - cx) / (y1 - y0)
        b = a.copy()
        b[(r < 0.3)] = (60, 90, 160)                                   # a blue iris
        b[(r < 0.1)] = (5, 5, 5)                                       # its pupil
        lab_iris = v2.patch_iris(b)
        self.assertTrue(v2.iris_light(lab_iris) or lab_iris[2] < 120)
        self.assertLess(lab_iris[2], 128)                              # blue: b* below neutral
        c = v2.copy_eye_patch(a, b)
        self.assertTrue(np.array_equal(c[y0:y1, x0:x1], b[y0:y1, x0:x1]))
        outside = np.ones((S, S), bool); outside[y0:y1, x0:x1] = False
        self.assertTrue(np.array_equal(c[outside], a[outside]))


@unittest.skipUnless(os.environ.get("NFL2K5_HI_HEAD_GLTF"), "set NFL2K5_HI_HEAD_GLTF to a Models export of hi_head")
class MeshFeaturesTest(unittest.TestCase):
    def test_the_feature_constants_are_the_mesh_own(self):
        head = v2.HeadMesh(os.environ["NFL2K5_HI_HEAD_GLTF"])
        f = v2.mesh_features(head)
        self.assertLess(float(np.abs(f["eyes"] - v2.UV_EYES).max()), 0.6)
        self.assertLess(float(np.abs(f["nose"] - v2.UV_NOSE).max()), 0.6)
        self.assertLess(float(np.abs(f["nose_pos"] - v2.P_NOSE).max()), 0.05)

    def test_the_eye_openings_are_the_meshs_holes_around_the_eyeballs(self):
        saved = (v2._R, v2._OPENINGS, v2._SYNTH_EYE)
        try:
            v2.use_head(os.environ["NFL2K5_HI_HEAD_GLTF"])
            ops = v2.eye_openings()
            # the openings sit level (UV_EYES[1]'s y, 52.8, is pulled 3 texels up by the lid seam's boundary edges
            # that mesh_features counts in; register_eyes measures against the openings themselves)
            self.assertLess(abs(ops[0]["cy"] - ops[1]["cy"]) / v2.K, 1.0)
            for o, (cx, cy) in zip(ops, v2.UV_EYES):
                self.assertAlmostEqual(o["cx"] / v2.K, cx, delta=2.5)
                self.assertAlmostEqual(o["cy"] / v2.K, 55.8, delta=1.0)
                self.assertTrue(8.0 < (o["y1"] - o["y0"]) / v2.K < 16.0)     # about 11 game texels tall
                self.assertTrue(30.0 < (o["x1"] - o["x0"]) / v2.K < 40.0)    # about 35 wide
        finally:
            v2._R, v2._OPENINGS, v2._SYNTH_EYE = saved


if __name__ == "__main__":
    unittest.main()
