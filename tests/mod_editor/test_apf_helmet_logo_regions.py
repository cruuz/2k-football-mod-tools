"""Headless contracts for ordinary-logo and advanced APF crest imports."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image

from mod_editor.apf_studio.helmet_logo_placement import (
    active_bbox,
    import_mask_nearest,
)
from mod_editor.apf_studio.helmet_logo_regions import (
    FULL_SHELL_OPAQUE_ALPHA,
    PROVED_MASK_ALPHA,
    HelmetLogoRegionError,
    TwoRegionPalette,
    clear_fully_transparent_rgb,
    convert_normal_logo_to_region_mask,
    opaque_shell_body_rgba,
    suggest_two_region_palette,
    validate_full_shell_region_mask_rgba,
    validate_region_mask_rgba,
)


def _canvas(fill: tuple[int, int, int, int] = (0, 0, 0, 136)) -> bytearray:
    return bytearray(bytes(fill) * (512 * 512))


def _put(
    rgba: bytearray, x_value: int, y_value: int, colour: tuple[int, int, int, int]
) -> None:
    offset = (y_value * 512 + x_value) * 4
    rgba[offset : offset + 4] = bytes(colour)


class HiddenRgbCleanupTests(unittest.TestCase):
    def test_cleanup_clears_only_rgb_below_exact_zero_alpha(self) -> None:
        result = clear_fully_transparent_rgb(
            bytes((255, 209, 0, 0, 3, 4, 5, 1, 0, 0, 0, 0))
        )
        self.assertEqual(result.cleared_texels, 1)
        self.assertEqual(
            result.rgba,
            bytes((0, 0, 0, 0, 3, 4, 5, 1, 0, 0, 0, 0)),
        )

    def test_normalized_import_ignores_hidden_png_background_rgb(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "hidden-rgb.png"
            image = Image.new("RGBA", (4, 4), (255, 0, 0, 0))
            for y_value in (1, 2):
                for x_value in (1, 2):
                    image.putpixel((x_value, y_value), (255, 209, 0, 255))
            image.save(source)
            imported = import_mask_nearest(source)
        self.assertEqual(active_bbox(imported.rgba), (128, 128, 383, 383))
        self.assertFalse(
            any(
                imported.rgba[offset + 3] == 0
                and any(imported.rgba[offset : offset + 3])
                for offset in range(0, len(imported.rgba), 4)
            )
        )


class AdvancedRegionMaskTests(unittest.TestCase):
    def test_exact_xenos_simplex_mask_is_accepted(self) -> None:
        rgba = _canvas()
        _put(rgba, 20, 30, (255, 0, 0, 136))
        _put(rgba, 21, 30, (0, 255, 0, 136))
        _put(rgba, 22, 30, (68, 85, 0, 119))
        result = validate_region_mask_rgba(rgba)
        self.assertEqual(result.active_bbox, (20, 30, 22, 30))
        self.assertEqual(result.active_texels, 3)
        self.assertEqual(result.alpha_levels, (119, 136))

    def test_non_lattice_overweight_hidden_and_empty_masks_are_rejected(self) -> None:
        non_lattice = _canvas()
        _put(non_lattice, 0, 0, (1, 0, 0, 136))
        with self.assertRaisesRegex(HelmetLogoRegionError, "4-bit RGBA"):
            validate_region_mask_rgba(non_lattice)

        overweight = _canvas()
        _put(overweight, 0, 0, (136, 136, 0, 136))
        with self.assertRaisesRegex(HelmetLogoRegionError, "coverage unit"):
            validate_region_mask_rgba(overweight)

        blue = _canvas()
        _put(blue, 0, 0, (0, 0, 255, 136))
        with self.assertRaisesRegex(HelmetLogoRegionError, "supports red and green"):
            validate_region_mask_rgba(blue)

        hidden = _canvas()
        _put(hidden, 0, 0, (255, 0, 0, 0))
        with self.assertRaisesRegex(HelmetLogoRegionError, "alpha zero"):
            validate_region_mask_rgba(hidden)

        with self.assertRaisesRegex(HelmetLogoRegionError, "mask is empty"):
            validate_region_mask_rgba(_canvas())


class FullShellOpaqueBodyContractTests(unittest.TestCase):
    def test_opaque_normalization_preserves_rgb_weights_and_lattice(self) -> None:
        rgba = _canvas((0, 0, 0, 0))
        _put(rgba, 40, 40, (255, 0, 0, 136))
        _put(rgba, 41, 40, (119, 0, 0, 85))
        normalized = opaque_shell_body_rgba(rgba)
        self.assertEqual(
            normalized[(40 * 512 + 40) * 4 : (40 * 512 + 40) * 4 + 4],
            bytes((255, 0, 0, 255)),
        )
        self.assertEqual(
            normalized[(40 * 512 + 41) * 4 : (40 * 512 + 41) * 4 + 4],
            bytes((119, 0, 0, 255)),
        )
        self.assertEqual(normalized[0:4], bytes((0, 0, 0, 255)))
        validation = validate_full_shell_region_mask_rgba(normalized)
        self.assertEqual(validation.active_texels, 2)

    def test_transparent_and_sentinel_backgrounds_are_normalized_then_accepted(self) -> None:
        for background_alpha in (0, PROVED_MASK_ALPHA):
            rgba = _canvas((0, 0, 0, background_alpha))
            _put(rgba, 10, 10, (0, 255, 0, background_alpha or 136))
            normalized = opaque_shell_body_rgba(rgba)
            self.assertEqual(normalized[3], FULL_SHELL_OPAQUE_ALPHA)
            validate_full_shell_region_mask_rgba(normalized)

    def test_full_shell_validator_rejects_translucent_shell_body(self) -> None:
        rgba = _canvas((0, 0, 0, PROVED_MASK_ALPHA))
        _put(rgba, 10, 10, (255, 0, 0, 136))
        with self.assertRaisesRegex(HelmetLogoRegionError, "opaque"):
            validate_full_shell_region_mask_rgba(rgba)

    def test_full_shell_validator_keeps_lattice_aa_alpha_fidelity(self) -> None:
        rgba = _canvas((0, 0, 0, 255))
        _put(rgba, 10, 10, (255, 0, 0, 255))
        _put(rgba, 11, 10, (136, 0, 0, 119))
        _put(rgba, 12, 10, (68, 0, 0, 85))
        validation = validate_full_shell_region_mask_rgba(rgba)
        self.assertEqual(validation.alpha_levels, (85, 119, 255))


class NormalLogoConversionTests(unittest.TestCase):
    EAGLES = TwoRegionPalette(
        shell=(5, 7, 8),
        red_region=(183, 196, 199),
        green_region=(255, 255, 255),
    )

    def test_exact_eagles_material_anchors_map_to_proved_channel_order(self) -> None:
        rgba = _canvas((93, 71, 44, 0))
        _put(rgba, 100, 200, (*self.EAGLES.red_region, 255))
        _put(rgba, 101, 200, (*self.EAGLES.green_region, 255))
        _put(rgba, 102, 200, (*self.EAGLES.red_region, 128))
        result = convert_normal_logo_to_region_mask(rgba, self.EAGLES)

        first = (200 * 512 + 100) * 4
        second = first + 4
        third = second + 4
        self.assertEqual(result.mask_rgba[first : first + 4], bytes((255, 0, 0, 136)))
        self.assertEqual(result.mask_rgba[second : second + 4], bytes((0, 255, 0, 136)))
        self.assertEqual(result.mask_rgba[third : third + 4], bytes((136, 0, 0, 136)))
        self.assertEqual(
            result.material_preview_rgba[first : first + 4],
            bytes((*self.EAGLES.red_region, 255)),
        )
        self.assertEqual(
            result.material_preview_rgba[second : second + 4],
            bytes((*self.EAGLES.green_region, 255)),
        )
        self.assertEqual(result.validation.active_bbox, (100, 200, 102, 200))
        self.assertEqual(result.cleared_hidden_rgb_texels, 512 * 512 - 3)
        self.assertTrue(all(value % 17 == 0 for value in result.mask_rgba))
        self.assertIn("unit-simplex", result.mapping)

    def test_rams_blue_shell_yellow_horn_mapping_is_explicit_not_guessed(self) -> None:
        rams = TwoRegionPalette(
            shell=(0, 53, 98),
            red_region=(255, 199, 44),
            green_region=(255, 255, 255),
        )
        rgba = _canvas((0, 0, 0, 0))
        _put(rgba, 10, 10, (255, 199, 44, 255))
        result = convert_normal_logo_to_region_mask(rgba, rams)
        offset = (10 * 512 + 10) * 4
        self.assertEqual(result.mask_rgba[offset : offset + 4], bytes((255, 0, 0, 136)))
        self.assertEqual(
            result.material_preview_rgba[offset : offset + 4],
            bytes((255, 199, 44, 255)),
        )

    def test_converter_is_deterministic_and_refuses_unusable_palette_or_art(self) -> None:
        rgba = _canvas((0, 0, 0, 0))
        _put(rgba, 80, 90, (200, 210, 220, 173))
        first = convert_normal_logo_to_region_mask(rgba, self.EAGLES)
        second = convert_normal_logo_to_region_mask(rgba, self.EAGLES)
        self.assertEqual(first, second)
        self.assertEqual(set(first.validation.channel_levels["blue"]), {0})
        self.assertEqual(first.validation.alpha_levels, (PROVED_MASK_ALPHA,))

        with self.assertRaisesRegex(HelmetLogoRegionError, "non-collinear"):
            TwoRegionPalette(
                shell=(0, 0, 0),
                red_region=(20, 20, 20),
                green_region=(40, 40, 40),
            )
        shell_only = _canvas((*self.EAGLES.shell, 255))
        with self.assertRaisesRegex(HelmetLogoRegionError, "mask is empty"):
            convert_normal_logo_to_region_mask(shell_only, self.EAGLES)

    def test_source_suggestion_is_bounded_and_never_invents_missing_colours(self) -> None:
        rgba = _canvas((0, 0, 0, 0))
        for x_value, colour in enumerate(
            (
                self.EAGLES.shell,
                self.EAGLES.red_region,
                self.EAGLES.green_region,
            )
        ):
            for y_value in range(80):
                _put(rgba, 50 + x_value, 50 + y_value, (*colour, 255))
        suggestion = suggest_two_region_palette(rgba)
        self.assertIsNotNone(suggestion.palette)
        self.assertIn("does not read", suggestion.explanation)

        one_colour = _canvas((0, 0, 0, 0))
        _put(one_colour, 10, 10, (255, 199, 44, 255))
        missing = suggest_two_region_palette(one_colour)
        self.assertIsNone(missing.palette)
        self.assertIn("manually", missing.explanation)


if __name__ == "__main__":
    unittest.main()
