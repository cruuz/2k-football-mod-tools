"""b780: the scorebug digit sheet is the same on every machine.

The digit sheet (digital_font) is derived from the user's own disc at build time. Its digits used to be drawn with the
installed DejaVu Sans Bold, so Pillow 11.3.0 (Windows Setup, the Linux .venv, Python 3.13) rendered 179 pixels
differently from the published patch (Pillow 10.2.0) and a machine without DejaVu skipped the atlas. The glyphs now come
from a shipped layer (no retail pixel) and only the bolt cell comes from the user's disc.
"""
from __future__ import annotations

import hashlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import PIL
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import nfl2k5_scorebug_espn_art as gen  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_source_art as art  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
REFERENCE = art.DEVELOPER_ASSETS / art.ART_FILE_NAMES["digital_font"]


def retail_sheet():
    target = art.texture_targets()["digital_font"]
    span = art.retail_texture_span(RETAIL, "digital_font")
    image = Image.open(io.BytesIO(art.decode_texture_png(span, int(target["width"]), int(target["height"]))))
    image.load()
    return image


class GlyphLayer(unittest.TestCase):
    def test_the_layer_is_the_pinned_file_and_holds_no_retail_pixel(self):
        self.assertEqual(hashlib.sha256(gen.DIGIT_GLYPHS.read_bytes()).hexdigest(), gen.DIGIT_GLYPHS_SHA256)
        layer = np.asarray(gen.digit_glyphs())
        self.assertEqual(layer.shape, (128, 128, 4))
        x0, y0, x1, y1 = gen.BOLT_CELL
        self.assertEqual(int(layer[y0:y1, x0:x1, 3].max()), 0)          # the retail bolt cell is clear
        drawn = layer[layer[..., 3] > 0]
        self.assertTrue(len(drawn) > 3000)
        self.assertEqual(np.unique(drawn[:, :3], axis=0).tolist(), [[255, 255, 255]])   # white glyph coverage only

    def test_the_layer_ships(self):
        allowed = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("data/nfl2k5_scorebug_digit_glyphs.png", allowed)

    def test_no_system_font_is_needed(self):
        with mock.patch.object(gen, "FONT_DIRECTORIES", ()):
            self.assertIsNone(gen.font_file(gen.FONT_BOLD))
            self.assertTrue(gen.have_text_font())
            sheet = gen.digits(Image.new("RGBA", (128, 128), (9, 9, 9, 255)))
        got, layer = np.asarray(sheet).copy(), np.asarray(gen.digit_glyphs())
        x0, y0, x1, y1 = gen.BOLT_CELL
        self.assertTrue((got[y0:y1, x0:x1] == [9, 9, 9, 255]).all())      # the disc's own bolt cell
        got[y0:y1, x0:x1] = 0
        self.assertTrue(np.array_equal(got, layer))                        # every glyph from the shipped layer

    @unittest.skipUnless(RETAIL.is_file() and REFERENCE.is_file(), "retail ISO or the developer digit sheet absent")
    def test_the_sheet_equals_the_published_one_on_this_pillow(self):
        sheet = gen.digits(retail_sheet())
        self.assertTrue(np.array_equal(np.asarray(sheet), np.asarray(Image.open(REFERENCE).convert("RGBA"))))
        buffer = io.BytesIO()
        sheet.save(buffer, format="PNG")
        self.assertEqual(hashlib.sha256(buffer.getvalue()).hexdigest(), art.ART_REFERENCE_SHA256["digital_font"])

    @unittest.skipUnless(RETAIL.is_file() and PIL.__version__ == "10.2.0" and gen.font_file(gen.FONT_BOLD) is not None,
                         "the layer is checked against the font only with the published renderer (Pillow 10.2.0)")
    def test_the_layer_is_what_the_published_renderer_draws(self):
        retail = retail_sheet()
        self.assertTrue(np.array_equal(np.asarray(gen.digits_from_font(retail)), np.asarray(gen.digits(retail))))


if __name__ == "__main__":
    unittest.main()
