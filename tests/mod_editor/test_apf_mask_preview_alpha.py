"""Display-only alpha handling for APF RGB mask textures."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import apf_inner  # noqa: E402


class ApfMaskPreviewAlphaTests(unittest.TestCase):
    def test_uniform_zero_alpha_is_force_opaqued_for_display(self) -> None:
        source = bytes((10, 20, 30, 0, 40, 50, 60, 0))

        displayed, applied = apf_inner.force_opaque_alpha_for_display(source)

        self.assertTrue(applied)
        self.assertEqual(displayed, bytes((10, 20, 30, 255, 40, 50, 60, 255)))

    def test_varying_alpha_is_left_alone(self) -> None:
        source = bytes((10, 20, 30, 0, 40, 50, 60, 128))

        displayed, applied = apf_inner.force_opaque_alpha_for_display(source)

        self.assertFalse(applied)
        self.assertIs(displayed, source)

    def test_encode_restores_zero_alpha_from_original_mask(self) -> None:
        original = bytes((10, 20, 30, 0, 40, 50, 60, 0))
        displayed_edit = bytes((70, 80, 90, 255, 100, 110, 120, 255))

        encoded = apf_inner.restore_unused_mask_alpha_for_encode(
            displayed_edit, original
        )

        self.assertEqual(encoded, bytes((70, 80, 90, 0, 100, 110, 120, 0)))

    def test_encode_preserves_real_alpha(self) -> None:
        original = bytes((10, 20, 30, 0, 40, 50, 60, 128))
        wanted = bytes((70, 80, 90, 255, 100, 110, 120, 64))

        self.assertEqual(
            apf_inner.restore_unused_mask_alpha_for_encode(wanted, original),
            wanted,
        )


if __name__ == "__main__":
    unittest.main()
