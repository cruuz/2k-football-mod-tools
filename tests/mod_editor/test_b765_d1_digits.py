"""Documented sheet templates and a real Rams slot import, without a disc copy."""
from io import BytesIO
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests/fixtures")]
from PIL import Image
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_digit_sheet import split_digit_sheet
from modern_rams_digit_sheet import modern_rams_sheet


def targets():
    return tuple(SimpleNamespace(digit=d, family="jersey", set_selector="23H0", width=64, height=64, asset_id=str(d)) for d in range(10))


class SheetTests(unittest.TestCase):
    def test_auto_all_four_documented_templates_preserve_digit_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sheet.png"
            for layout, columns, rows in (("horizontal", 10, 1), ("vertical", 1, 10), ("grid_5x2", 5, 2), ("grid_2x5", 2, 5)):
                image = Image.new("RGBA", (columns * 64, rows * 64))
                for digit in range(10):
                    image.paste((digit * 20, 11, 22, 255), (digit % columns * 64, digit // columns * 64, (digit % columns + 1) * 64, (digit // columns + 1) * 64))
                image.save(path)
                outputs = split_digit_sheet(path, targets())
                self.assertTrue(all(output.layout == layout for output in outputs))
                for digit, output in enumerate(outputs):
                    with Image.open(BytesIO(output.png)) as cell:
                        self.assertEqual(cell.getpixel((32, 32)), (digit * 20, 11, 22, 255))

    def test_non_square_grid_requires_explicit_layout_and_bad_cells_refuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sheet.png"
            Image.new("RGBA", (400, 128)).save(path)
            with self.assertRaisesRegex(ValidationError, "Choose its row, column or grid"):
                split_digit_sheet(path, targets())
            self.assertEqual(split_digit_sheet(path, targets(), orientation="grid_5x2")[0].cell_size, (80, 64))
            Image.new("RGBA", (321, 128)).save(path)
            with self.assertRaisesRegex(ValidationError, "divisible by 5"):
                split_digit_sheet(path, targets(), orientation="grid_5x2")


class RamsImportTests(unittest.TestCase):
    def test_synthetic_modern_font_imports_to_every_rams_home_jersey_and_arm_slot(self):
        from mod_editor.core.nfl2k5_uniform_catalog import load_nfl2k5_uniform_catalog, DEFAULT_REPORT
        from mod_editor.core.nfl2k5_digit_preview import preview_digit_sheet, decode_digit_texture
        import nfl_live_numbers_nameplate_targets as targets_module
        import nfl_live_numbers_nameplate_png_import as writer
        index = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
        missing = [str(p) for p in (index, DEFAULT_REPORT, targets_module.DEFAULT_REPORT) if not p.is_file()]
        if missing:
            self.skipTest("Private Rams templates absent: " + ", ".join(missing))
        catalog = load_nfl2k5_uniform_catalog()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for family in ("jersey", "arm"):
                assets = tuple(a for a in catalog.assets_for_set("23H0") if a.family == family and a.digit is not None)
                first = None
                for layout in ("horizontal", "grid_5x2"):
                    outputs = split_digit_sheet(modern_rams_sheet(root / "sheet.png", layout), assets)
                    preview = preview_digit_sheet(index, assets, outputs)
                    self.assertEqual(preview.kept_retail_count, 0, preview.details)
                    spans = []
                    for asset, output, receipt in zip(assets, outputs, preview.receipts):
                        replacement = root / f"{output.digit}.png"
                        replacement.write_bytes(output.png)
                        span, _decoded, result = writer.build_import(index, targets_module.DEFAULT_REPORT, family, "23", "H", 0, output.digit, replacement)
                        self.assertEqual(decode_digit_texture(span).span_sha256, receipt["replacement"]["span_sha256"])
                        self.assertLessEqual(result["rebuild"]["recompressed_bytes"], result["target"]["stored_size"])
                        spans.append(span)
                    if first is None:
                        first = spans
                    else:
                        self.assertEqual(spans, first)


if __name__ == "__main__":
    unittest.main()
