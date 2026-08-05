"""Focused gates for the clean-source Eagles APF region-mask conversion."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_eagles_crest_region_mask as converter  # noqa: E402
import apf_logo_patch as logo_patch  # noqa: E402


SOURCE = Path(
    "/media/noah/Storage/.codex-tmp/"
    "philadelphia-eagles-wing-source-1022x256.png"
)
SHADER_TRACE = Path("/home/noah/.codex-tmp/shader_12A5859DBBD7C3FE.ucode.ps")


class EaglesRegionMaskUnitTest(unittest.TestCase):
    def test_source_anchors_map_to_exact_semantic_weights(self) -> None:
        self.assertEqual(
            converter._source_paint_weights((*converter.SOURCE_DARK, 255)),
            (0, 0),
        )
        self.assertEqual(
            converter._source_paint_weights((*converter.SOURCE_SILVER, 255)),
            (converter.WEIGHT_SCALE, 0),
        )
        self.assertEqual(
            converter._source_paint_weights((*converter.SOURCE_WHITE, 255)),
            (0, converter.WEIGHT_SCALE),
        )
        self.assertEqual(
            converter._source_paint_weights((*converter.SOURCE_WHITE, 0)),
            (0, 0),
        )

    def test_fixed_weight_sampler_is_endpoint_aligned(self) -> None:
        weights = [(converter.WEIGHT_SCALE, 0), (0, converter.WEIGHT_SCALE)] * 2
        first = converter._bilinear_weight_sample(weights, 2, 2, 0, 0, 3, 2)
        middle = converter._bilinear_weight_sample(weights, 2, 2, 1, 0, 3, 2)
        last = converter._bilinear_weight_sample(weights, 2, 2, 2, 0, 3, 2)
        self.assertEqual(first, (converter.WEIGHT_SCALE, 0))
        self.assertEqual(middle, (32768 - 1, 32768))
        self.assertEqual(last, (0, converter.WEIGHT_SCALE))

    def test_joint_xenos_quantization_preserves_simplex_and_antialiasing(self) -> None:
        red, green = converter._xenos_quantize_weights(32768, 32767)
        self.assertEqual((red, green), (136, 119))
        self.assertEqual(red + green, 255)
        for value in (red, green):
            self.assertEqual(value % 17, 0)
            self.assertNotIn(value, (0, 255))

    def test_material_preview_uses_shader_weight_equation(self) -> None:
        self.assertEqual(converter._material_pixel(0, 0), converter.MATERIAL_SHELL)
        self.assertEqual(converter._material_pixel(255, 0), converter.MATERIAL_SILVER)
        self.assertEqual(converter._material_pixel(0, 255), converter.MATERIAL_WHITE)
        red, green = 68, 85
        shell = 255 - red - green
        expected = tuple(
            (
                converter.MATERIAL_SHELL[channel] * shell
                + converter.MATERIAL_SILVER[channel] * red
                + converter.MATERIAL_WHITE[channel] * green
                + 127
            ) // 255
            for channel in range(3)
        ) + (255,)
        self.assertEqual(converter._material_pixel(red, green), expected)

    def test_writer_is_fail_closed_and_non_overwriting(self) -> None:
        source = inspect.getsource(converter)
        self.assertIn("O_NOFOLLOW", source)
        self.assertIn("O_EXCL", source)
        self.assertTrue(converter.SOURCE_PNG_SHA256)
        self.assertTrue(converter.SOURCE_RGBA_SHA256)
        self.assertTrue(converter.EXPECTED_MASK_RGBA_SHA256)
        self.assertTrue(converter.EXPECTED_MATERIAL_RGBA_SHA256)
        self.assertTrue(converter.EXPECTED_MASK_PNG_SHA256)
        self.assertTrue(converter.EXPECTED_MATERIAL_PNG_SHA256)
        self.assertEqual(converter.SCHEMA, "apf2k8_eagles_crest_region_mask/v3")
        self.assertEqual((converter.SOURCE_PAINT_WIDTH, converter.SOURCE_PAINT_HEIGHT),
                         (490, 256))
        self.assertEqual((converter.PAINT_WIDTH, converter.PAINT_HEIGHT), (512, 268))
        self.assertEqual(converter.EXPECTED_ACTIVE_BBOX, (0, 122, 511, 389))
        self.assertEqual(converter.XENOS_CHANNEL_STEP, 17)
        self.assertTrue(converter.SHADER_WEIGHT_TRACE_SHA256)


@unittest.skipUnless(SOURCE.is_file(), "private clean Eagles source is absent")
class EaglesRegionMaskPrivateWitnessTest(unittest.TestCase):
    def test_exact_source_produces_pinned_clean_mask(self) -> None:
        result, receipt = converter.build(SOURCE)
        self.assertEqual(result.output_active_bbox, (0, 122, 511, 389))
        self.assertEqual(
            hashlib.sha256(result.mask_rgba).hexdigest(),
            converter.EXPECTED_MASK_RGBA_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(result.material_rgba).hexdigest(),
            converter.EXPECTED_MATERIAL_RGBA_SHA256,
        )
        self.assertEqual(set(result.mask_pixel_counts), {
            "black_unpainted",
            "red_weighted_texels",
            "green_weighted_texels",
            "mixed_weight_texels",
            "antialiased_weight_texels",
        })
        self.assertGreater(result.mask_pixel_counts["red_weighted_texels"], 10_000)
        self.assertGreater(result.mask_pixel_counts["green_weighted_texels"], 25_000)
        self.assertGreater(result.mask_pixel_counts["antialiased_weight_texels"], 1_000)
        self.assertGreater(len(result.channel_levels["red"]), 3)
        self.assertGreater(len(result.channel_levels["green"]), 3)
        self.assertEqual(receipt["contract"]["no_redraw"], True)
        self.assertEqual(
            receipt["contract"]["aspect_fit"]["source_painted_size"],
            [490, 256],
        )
        self.assertEqual(
            receipt["contract"]["aspect_fit"]["output_painted_size"],
            [512, 268],
        )
        self.assertTrue(
            receipt["contract"]["aspect_fit"]["source_shape_preserved_without_crop"]
        )
        self.assertEqual(
            receipt["contract"]["selected_source_side"],
            "right_outward_front_to_rear",
        )

    def test_publish_pngs_decode_to_the_pinned_pixels_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mask = root / "mask.png"
            material = root / "material.png"
            receipt_path = root / "receipt.json"
            receipt = converter.publish(SOURCE, mask, material, receipt_path)
            self.assertEqual(json.loads(receipt_path.read_text()), receipt)
            with Image.open(mask) as image:
                self.assertEqual(image.size, (512, 512))
                self.assertEqual(
                    hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest(),
                    converter.EXPECTED_MASK_RGBA_SHA256,
                )
            with Image.open(material) as image:
                self.assertEqual(image.size, (512, 512))
                self.assertEqual(
                    hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest(),
                    converter.EXPECTED_MATERIAL_RGBA_SHA256,
                )
            with self.assertRaisesRegex(converter.RegionMaskError, "overwrite"):
                converter.publish(SOURCE, mask, root / "next.png", root / "next.json")

    def test_actual_xenos_4444_transport_round_trips_every_weight(self) -> None:
        result, _receipt = converter.build(SOURCE)
        metadata = {
            "endianness": logo_patch.ENDIAN,
            "height": logo_patch.HEIGHT,
            "pitch_pixels": logo_patch.PITCH,
            "swizzle_components": logo_patch.SWIZZLE,
            "width": logo_patch.WIDTH,
        }
        encoded = logo_patch.encode_4444_base(metadata, result.mask_rgba)
        decoded = logo_patch.decode_4444_base(metadata, encoded)
        self.assertEqual(decoded, result.mask_rgba)

    def test_one_byte_source_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tampered = Path(temporary) / "tampered.png"
            payload = bytearray(SOURCE.read_bytes())
            payload[-1] ^= 1
            tampered.write_bytes(payload)
            with self.assertRaisesRegex(converter.RegionMaskError, "source PNG hash"):
                converter.build(tampered)


@unittest.skipUnless(SHADER_TRACE.is_file(), "private recovered shader trace is absent")
class EaglesRegionMaskShaderWitnessTest(unittest.TestCase):
    def test_recovered_crest_shader_uses_continuous_sampled_channel_weights(self) -> None:
        payload = SHADER_TRACE.read_bytes()
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(),
            converter.SHADER_WEIGHT_TRACE_SHA256,
        )
        source = payload.decode("ascii")
        self.assertIn("cndgt r7, r2.wwww, c251.xxyy, c29.xywz", source)
        self.assertIn("mul r0._yzw, r12.zzzz, c14.xxyz", source)
        self.assertIn("mad r0._yzw, r12.yyyy, c13.xxyz, r0.yyzw", source)
        self.assertIn("mad r0._yzw, r12.xxxx, c12.xxyz, r0.yyzw", source)


if __name__ == "__main__":
    unittest.main()
