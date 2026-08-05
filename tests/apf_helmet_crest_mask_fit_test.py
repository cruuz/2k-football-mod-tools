from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "apf_helmet_crest_mask_fit", TOOLS / "apf_helmet_crest_mask_fit.py"
)
assert SPEC is not None and SPEC.loader is not None
fit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fit
SPEC.loader.exec_module(fit)


class HelmetCrestMaskFitTest(unittest.TestCase):
    def _mask(self) -> bytes:
        background = bytes((0, 0, 0, 136))
        rgba = bytearray(background * (512 * 512))
        colors = (bytes((0, 255, 0, 136)), bytes((255, 0, 0, 136)))
        for y in range(220, 222):
            for x in range(200, 204):
                offset = (y * 512 + x) * 4
                rgba[offset : offset + 4] = colors[(x - 200) // 2]
        return bytes(rgba)

    def test_fills_entire_u_range_and_preserves_palette(self) -> None:
        source = self._mask()
        result = fit.fit_visible_mask_rgba(source)
        self.assertEqual(result.source_bbox, (200, 220, 203, 221))
        self.assertEqual(result.output_bbox, (0, 128, 511, 383))
        self.assertEqual(result.output_visible_width, 512)
        self.assertEqual(result.output_visible_height, 256)
        self.assertEqual(result.source_horizontal_coverage, 4 / 512)
        self.assertEqual(result.output_horizontal_coverage, 1.0)
        self.assertTrue(result.every_source_x_sampled)
        self.assertTrue(result.every_source_y_sampled)
        source_palette = {
            source[offset : offset + 4] for offset in range(0, len(source), 4)
        }
        output_palette = {
            result.output_rgba[offset : offset + 4]
            for offset in range(0, len(result.output_rgba), 4)
        }
        self.assertEqual(output_palette, source_palette)

    def test_rejects_alpha_only_and_mixed_background(self) -> None:
        alpha_only = bytes((0, 0, 0, 136)) * (512 * 512)
        with self.assertRaisesRegex(fit.MaskFitError, "no nonblack"):
            fit.fit_visible_mask_rgba(alpha_only)
        mixed = bytearray(self._mask())
        mixed[4:8] = bytes((0, 0, 0, 0))
        with self.assertRaisesRegex(fit.MaskFitError, "one exact background"):
            fit.fit_visible_mask_rgba(bytes(mixed))

    def test_publish_is_deterministic_and_no_overwrite(self) -> None:
        from nfl_txtr import encode_rgba_png

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.png"
            output = root / "fitted.png"
            receipt = root / "fitted.json"
            source.write_bytes(encode_rgba_png(512, 512, self._mask()))
            first = fit.publish(source, output, receipt)
            self.assertEqual(first["schema"], fit.SCHEMA)
            self.assertTrue(output.is_file())
            self.assertTrue(receipt.is_file())
            with self.assertRaisesRegex(fit.MaskFitError, "already exists"):
                fit.publish(source, output, receipt)


if __name__ == "__main__":
    unittest.main()
