"""Synthetic, redistributable checks for the read-only pants preview helper."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/b77'))
import pt0_pants_preview as preview


class PantsPreviewTests(unittest.TestCase):
    def test_native_cut_and_common_lod_contour(self):
        pos = np.array([[0, 0, 0], [1, 0, 0], [0, -10, 0], [1, -10, 0]])
        uv = np.array([[0, 0], [1, 0], [0, 1], [1, 1]])
        tris = np.array([[0, 1, 2], [1, 3, 2]])
        a = preview.cut_segments(pos, uv, tris, -4)
        b = preview.cut_segments(pos, uv, tris, -6)
        common = preview.common_contour([a, b])
        np.testing.assert_allclose(common[:, 1], .5)
        self.assertEqual((common[0, 0], common[-1, 0]), (0, 1))
        # A cut exactly through vertices must still produce a continuous line.
        diagonal = pos.copy().astype(float)
        diagonal[1, 1] = -4
        self.assertTrue(np.isfinite(preview.cut_segments(diagonal, uv, tris, -4)).all())

    def test_own_sock_shading_scope_alpha_and_input_immutability(self):
        pants = np.full((16, 16, 4), 199, dtype=np.uint8)
        pants[:, :, 3] = np.arange(16)[:, None]
        socks = np.full((64, 16, 4), 240, dtype=np.uint8)
        socks[:8, :, 0] = np.arange(16)[None, :]*8
        socks[:8, :, 1] = np.arange(8)[:, None]*10
        socks[:8, :, 2] = 21
        originals = pants.copy(), socks.copy()
        curve = np.array([[0, .5], [1, .5]])
        registration = np.array([[0, 1, 0], [1, 1, 1]])
        result, mask = preview.recolor(pants, socks, curve, registration)
        np.testing.assert_array_equal(result[~mask], pants[~mask])
        np.testing.assert_array_equal(result[:, :, 3], pants[:, :, 3])
        np.testing.assert_array_equal(pants, originals[0])
        np.testing.assert_array_equal(socks, originals[1])
        self.assertTrue(np.all(result[:, :, 2][mask] == 21))
        # Both circumferential and vertical sock shading survive.
        self.assertGreater(np.ptp(result[8, :, 0]), 100)
        self.assertGreater(np.ptp(result[8:, 3, 1]), 50)
        _, lower_mask = preview.recolor(pants, socks, curve + [0, .2], registration)
        self.assertLess(lower_mask.sum(), mask.sum())

    def test_sock_u_wrap_and_cuff_row_zero(self):
        pants = np.zeros((4, 4, 4), dtype=np.uint8)
        socks = np.zeros((64, 4, 4), dtype=np.uint8)
        socks[0, :, 0] = [20, 40, 60, 80]
        contour = np.array([[0, .25], [1, .25]])
        registration = np.array([[0, .75, 0], [1, .75, 1]])
        result, _ = preview.recolor(pants, socks, contour, registration)
        np.testing.assert_array_equal(result[-1, :, 0], [20, 40, 60, 80])
        registration[:, 2] += 1
        wrapped, _ = preview.recolor(pants, socks, contour, registration)
        np.testing.assert_array_equal(result, wrapped)

    def test_rejects_cut_below_cuff(self):
        with self.assertRaisesRegex(ValueError, 'above the physical cuff'):
            preview.recolor(np.zeros((4, 4, 4)), np.zeros((64, 4, 4)),
                            np.array([[0, .9], [1, .9]]), np.array([[0, .8, 0], [1, .8, 1]]))

    def test_cuff_registration_unwraps_sock_seam(self):
        u = np.linspace(0, 1, 9)
        pos = np.column_stack([u, u*0, u*0])
        uv = np.column_stack([u, u*0+1])
        sock_uv = np.column_stack([(u+.75) % 1, u*0])
        g = dict(pos=np.vstack([pos, pos]), uv=np.vstack([uv, sock_uv]),
                 surfaces={'UNIF_pants': np.arange(9).reshape(3, 3),
                           'SOCKS': np.arange(9, 18).reshape(3, 3)})
        registration = preview.cuff_registration(g)
        np.testing.assert_allclose(registration[:, 2], u+.75)
        np.testing.assert_allclose(registration[:, 1], 1)

    def test_wrong_disc_hash_creates_no_output(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            args = SimpleNamespace(disc=root/'source/base.iso', out=root/'preview',
                                   fraction=.46, sha256='0'*64, blender='blender')
            disc = MagicMock()
            disc.image_size = 3
            disc.read.side_effect = lambda count, offset: b'abc'[offset:offset+count]
            context = MagicMock()
            context.__enter__.return_value = disc
            with patch.object(preview, 'Disc', return_value=context), \
                 patch.object(preview, 'identity', return_value=(1, 2, 3, 4)), \
                 patch.object(preview.shutil, 'which', return_value='blender'):
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    preview.run(args)
            self.assertFalse(args.out.exists())
            context.__exit__.assert_called_once()

    def test_output_guards_and_visible_prototype_banner(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            disc = root/'source/base.iso'
            disc.parent.mkdir()
            disc.write_bytes(b'read-only source sentinel')
            for out in [ROOT/'preview', disc.parent/'preview', root, disc.parent, disc]:
                with self.assertRaises(ValueError):
                    preview.validate_output(out, disc)
            self.assertEqual(preview.validate_output(root/'preview', disc), (root/'preview').resolve())  # macOS /private/var, Windows 8.3 temp
            self.assertEqual(disc.read_bytes(), b'read-only source sentinel')
        image = preview.comparison([preview.Image.new('RGB', (640, 800))]*2, 'test', ['before', 'after'])
        self.assertEqual(image.size, (1280, 900))
        self.assertGreater(np.asarray(image)[:35].std(), 10)


if __name__ == '__main__':
    unittest.main()
