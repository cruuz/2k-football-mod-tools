"""b791 h7-numbers on the real writer and the retail archive; skipped when the private game files are absent.

A Rams-style sheet (royal outline, gold-to-white gradient) goes through the same path the Studio uses: split,
encode every digit with the pinned writer against the real slot, decode the written texture. Nothing here reads
or writes a disc image; the retail archive is only read for the original slot bytes.
"""
from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).parent)]

from PIL import Image

from mod_editor.core import nfl2k5_digit_art as art
from mod_editor.core.nfl2k5_digit_preview import decode_digit_texture, preview_digit_sheet
from mod_editor.core.nfl2k5_digit_sheet import split_digit_sheet
import nfl_live_numbers_nameplate_png_import as writer
import nfl_live_numbers_nameplate_targets as targets
from test_b791_h7_numbers import grid_sheet, proportional_sheet, rams_digit


def rams_sheet(path, layout="horizontal", *, cell=128, **kwargs):
    """The synthetic Rams-style digits laid out as a sheet (cells are drawn at 64 px and enlarged)."""
    columns, rows = {"horizontal": (10, 1), "grid_5x2": (5, 2)}[layout]
    sheet = Image.new("RGBA", (columns * cell, rows * cell))
    for digit in range(10):
        sheet.alpha_composite(rams_digit(digit, cell), (digit % columns * cell, digit // columns * cell))
    sheet.save(path)
    return Path(path)


class RealSlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = Path(os.environ.get("NFL2K5_TEST_INDEX", ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
        needed = (cls.index, targets.DEFAULT_REPORT, ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json")
        missing = [str(p) for p in needed if not p.is_file()]
        if missing:
            raise unittest.SkipTest("Private retail digit templates absent: " + ", ".join(missing))
        from mod_editor.core.nfl2k5_uniform_catalog import load_nfl2k5_uniform_catalog
        cls.catalog = load_nfl2k5_uniform_catalog()

    def slots(self, selector, family="jersey"):
        return tuple(a for a in self.catalog.assets_for_set(selector) if a.family == family and a.digit is not None)

    def preview(self, sheet, selector, family="jersey", **kwargs):
        assets = self.slots(selector, family)
        outputs = split_digit_sheet(sheet, assets, **kwargs)
        return outputs, preview_digit_sheet(self.index, assets, outputs)

    def test_modern_rams_numerals_import_into_a_roomy_rams_slot_in_every_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            first = None
            for layout in ("horizontal", "grid_5x2"):
                outputs, preview = self.preview(rams_sheet(root / f"{layout}.png", layout), "23H0")
                self.assertEqual(preview.kept_retail_count, 0, preview.details)
                self.assertIn("Layout:", preview.details)
                self.assertIn("Space used in each slot (bytes used of bytes available): 0: ", preview.details)
                spans = [r["replacement"]["span_sha256"] for r in preview.receipts]
                first = first or spans
                self.assertEqual(spans, first, "the same digits give the same textures in either layout")
            # the same digits on a canvas that does not divide into five columns, with gaps and a margin
            gutter = grid_sheet(root / "gutter.png", 5, 2, 100, 140, margin=20, gap=14)
            outputs, preview = self.preview(gutter, "23H0")
            self.assertEqual(outputs[0].layout, "grid_5x2")
            self.assertIn("Layout:", preview.details)

    def test_tight_throwback_slot_never_loses_a_digit_the_old_ladder_fit_and_explains_every_kept_one(self):
        with tempfile.TemporaryDirectory() as temp:
            sheet = rams_sheet(Path(temp) / "rams.png", "grid_5x2")
            outputs, new = self.preview(sheet, "23H2")
            with patch.object(art, "_STEPS", ()):
                _outputs, old = self.preview(sheet, "23H2")
            self.assertLessEqual(new.kept_retail_count, old.kept_retail_count)
            for digit, (before, after) in enumerate(zip(old.receipts, new.receipts)):
                if not before.get("kept_retail"):
                    self.assertEqual(before["replacement"]["span_sha256"], after["replacement"]["span_sha256"],
                                     f"digit {digit} fitted before and must be byte-identical now")
            for digit, receipt in enumerate(new.receipts):
                if receipt.get("kept_retail"):
                    self.assertIn(f"Digit {digit}: kept retail", new.details)
                    self.assertRegex(receipt["reason"], r"needs about [\d,]+ bytes and the slot holds [\d,]+")
                    self.assertIn("one flat colour", receipt["reason"])
                else:
                    self.assertLessEqual(receipt["rebuild"]["recompressed_bytes"], receipt["target"]["stored_size"])

    def test_every_written_digit_decodes_with_its_outline_and_its_fill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            sheet = rams_sheet(root / "rams.png", "grid_5x2")
            outputs, preview = self.preview(sheet, "23H2")
            us = self.catalog.get_uniform_set("23H2")
            for output, receipt in zip(outputs, preview.receipts):
                if receipt.get("kept_retail"):
                    continue
                path = root / f"{output.digit}.png"
                path.write_bytes(output.png)
                span, _preview, result = writer.build_import(self.index, targets.DEFAULT_REPORT, "jersey", us.asset_code,
                                                             us.side_code, us.variant, output.digit, path)
                texture = decode_digit_texture(span)
                self.assertEqual(texture.span_sha256, receipt["replacement"]["span_sha256"])
                base = texture.levels[0]
                solid = Counter(tuple(base.rgba[i:i + 3]) for i in range(0, len(base.rgba), 4) if base.rgba[i + 3] == 255)
                self.assertTrue(any(max(abs(c[0] - 0), abs(c[1] - 53), abs(c[2] - 148)) <= 60 for c in solid),
                                f"digit {output.digit} lost its outline")
                self.assertTrue(any(c[0] > 190 and c[1] > 150 for c in solid), f"digit {output.digit} lost its fill")
                self.assertLessEqual(result["rebuild"]["recompressed_bytes"], result["target"]["stored_size"])

    def test_a_flat_picture_is_refused_before_any_digit_is_encoded(self):
        from mod_editor.core.errors import ValidationError
        with tempfile.TemporaryDirectory() as temp:
            sheet = Image.new("RGB", (640, 64), (10, 30, 90))
            for index in range(10):
                sheet.paste((250, 250, 250), (index * 64 + 20, 12, index * 64 + 44, 52))
            path = Path(temp) / "flat.png"
            sheet.save(path)
            with self.assertRaisesRegex(ValidationError, "no transparent pixels"):
                self.preview(path, "23H0")


if __name__ == "__main__":
    unittest.main()
