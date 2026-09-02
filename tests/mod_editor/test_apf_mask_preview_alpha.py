"""Display-only alpha handling for APF RGB mask textures."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import apf_inner  # noqa: E402
from mod_editor.apf_studio.asset_io import ApfAssetIO  # noqa: E402


class ApfMaskPreviewAlphaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.asset_io = object.__new__(ApfAssetIO)

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

    def test_visible_export_pixels_round_trip_to_retail_alpha(self) -> None:
        source = bytes((10, 20, 30, 0, 40, 50, 60, 0))

        displayed, note = self.asset_io._display_rgba_and_note(
            source,
            source_label="jersey slot 19",
        )

        self.assertIn("opaque", note or "")
        self.assertEqual(
            apf_inner.restore_unused_mask_alpha_for_encode(displayed, source)[3::4],
            source[3::4],
        )
        self.assertEqual(displayed[3::4], bytes((255, 255)))

    def test_empty_source_is_reported_as_empty_not_alpha_masked(self) -> None:
        source = bytes(8)

        displayed = self.asset_io._force_opaque_for_display(
            source,
            source_label="jersey slot 128",
        )

        self.assertEqual(displayed, source)
        self.assertIn("empty in the retail source", self.asset_io.display_alpha_note or "")
        self.assertNotIn("unused storage", self.asset_io.display_alpha_note or "")

    def test_cached_note_survives_a_second_view(self) -> None:
        source = bytes((10, 20, 30, 0, 40, 50, 60, 0))
        displayed = self.asset_io._force_opaque_for_display(source)
        first_note = self.asset_io.display_alpha_note

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "jersey-19.png"
            ApfAssetIO._write_png_cache(
                path,
                2,
                1,
                displayed,
                display_note=first_note,
            )
            self.asset_io.display_alpha_note = None
            cached_note = ApfAssetIO._read_cached_display_note(path)

        self.assertEqual(cached_note, first_note)


if __name__ == "__main__":
    unittest.main()
