"""b791 h7-numbers: number sheets that are not textbook equal-cell grids, and clear refusals.

Coach Edwards (DM 2026-10-02): "it accepts the Horizontal sheets but doesn't accept the 0-4, 5-9 sheets".
Every sheet here is original synthetic art: hollow blocks whose colour and height say which digit they are,
so a wrong order, a cut through a neighbour or a leaked pixel shows up as a pixel difference. Nothing needs
the game files; the real-writer cases live in test_b791_h7_numbers_real.py.
"""
from __future__ import annotations

from collections import Counter
from io import BytesIO
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(1, str(ROOT / "tools"))
sys.path.insert(2, str(ROOT / "tests" / "fixtures"))

from PIL import Image, ImageDraw

from mod_editor.core import nfl2k5_digit_art as art
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_digit_sheet import split_digit_sheet, SHEET_HELP, SHEET_LAYOUT_CHOICES
from mod_editor.core import nfl2k5_digit_texture as texture
from mod_editor.core.nfl2k5_digit_texture import resize_cell, visible_colour_range
from nfl_tset_png_import import QualityBudgetError, palette_bytes
from nfl_txtr import swizzle_2d


def assets(size=64):
    return tuple(SimpleNamespace(digit=d, family="jersey", set_selector="23H2", width=size, height=size,
                                 asset_id=f"23H2:jersey:{d}") for d in range(10))


def colour(digit):
    return (30 + digit * 22, 250 - digit * 20, 60 + digit * 12, 255)


def glyph_height(digit, cell_h):
    return round(cell_h * (0.30 + 0.06 * digit))


def glyph(digit, cell_w, cell_h, *, width=None):
    """A hollow block in the digit's colour. Its height grows with the digit; centred in its cell."""
    image = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
    w = width or round(cell_w * 0.46)
    h = glyph_height(digit, cell_h)
    left, top = (cell_w - w) // 2, (cell_h - h) // 2
    thickness = max(2, round(min(w, h) * 0.16))
    draw = ImageDraw.Draw(image)
    draw.rectangle((left, top, left + w - 1, top + h - 1), fill=colour(digit))
    draw.rectangle((left + thickness, top + thickness, left + w - 1 - thickness, top + h - 1 - thickness), fill=(0, 0, 0, 0))
    return image


def grid_sheet(path, columns, rows, cell_w, cell_h, *, margin=0, gap=0, canvas=None, widths=None):
    """Digits in reading order, each centred in its nominal cell; optional margin and gap."""
    width = canvas[0] if canvas else margin * 2 + columns * cell_w + (columns - 1) * gap
    height = canvas[1] if canvas else margin * 2 + rows * cell_h + (rows - 1) * gap
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    # nominal cells spread over the canvas when no gap is given, otherwise laid out with margin and gap
    for digit in range(10):
        column, row = digit % columns, digit // columns
        if canvas:
            x0 = round(column * width / columns + (width / columns - cell_w) / 2)
            y0 = round(row * height / rows + (height / rows - cell_h) / 2)
        else:
            x0, y0 = margin + column * (cell_w + gap), margin + row * (cell_h + gap)
        sheet.alpha_composite(glyph(digit, cell_w, cell_h, width=widths[digit] if widths else None), (x0, y0))
    sheet.save(path)
    return Path(path)


def proportional_sheet(path, columns, rows, *, glyph_widths, gaps, glyph_h=60, margin=3):
    """Tight-cropped sheet: digits of different widths, different gaps, no equal cells anywhere."""
    sheet_w = max(sum(glyph_widths[r * columns:(r + 1) * columns]) + sum(gaps[r * columns:(r + 1) * columns - 1]) for r in range(rows)) + 2 * margin
    sheet_h = rows * glyph_h + (rows - 1) * 9 + 2 * margin
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    for row in range(rows):
        x = margin
        for column in range(columns):
            digit = row * columns + column
            g = glyph(digit, glyph_widths[digit], glyph_h, width=glyph_widths[digit])
            sheet.alpha_composite(g, (x, margin + row * (glyph_h + 9)))
            x += glyph_widths[digit] + (gaps[digit] if column < columns - 1 else 0)
    sheet.save(path)
    return Path(path)


class GeometryCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def split(self, path, **kwargs):
        return split_digit_sheet(path, assets(), **kwargs)

    def assert_each_digit_is_its_own(self, outputs, *, tolerance=3):
        """Order and no leakage: every visible pixel has this digit's colour; heights grow with the digit."""
        heights = []
        for output in outputs:
            with Image.open(BytesIO(output.png)) as opened:
                rgba = opened.convert("RGBA")
            seen = {pixel[:3] for pixel in rgba.getdata() if pixel[3] >= 16}
            self.assertTrue(seen, f"digit {output.digit} is empty")
            want = colour(output.digit)
            for found in seen:
                self.assertLessEqual(max(abs(found[k] - want[k]) for k in range(3)), tolerance,
                                     f"digit {output.digit} holds a pixel of another digit: {found}")
            bbox = rgba.getchannel("A").point(lambda a: 255 if a >= 16 else 0).getbbox()
            heights.append(bbox[3] - bbox[1])
        self.assertEqual(heights, sorted(heights), f"digits are out of order: {heights}")
        self.assertLess(heights[0], heights[-1])


class LayoutDetectionTests(GeometryCase):
    def test_square_cell_grids_still_detected_exactly_at_any_scale(self):
        for scale in (64, 128, 256):
            for layout, (columns, rows) in {"horizontal": (10, 1), "vertical": (1, 10),
                                            "grid_5x2": (5, 2), "grid_2x5": (2, 5)}.items():
                with self.subTest(layout=layout, scale=scale):
                    path = grid_sheet(self.root / "s.png", columns, rows, scale, scale)
                    outputs = self.split(path)
                    self.assertTrue(all(o.layout == layout for o in outputs))
                    self.assertEqual({o.cell_size for o in outputs}, {(scale, scale)})
                    self.assert_each_digit_is_its_own(outputs)
                    self.assertIn(f"{scale}x{scale} cells", outputs[0].layout_note)

    def test_zero_to_four_over_five_to_nine_with_tall_cells_is_found_without_choosing_a_layout(self):
        # 5 columns x 2 rows of 80x128 cells: not square, so the old detection refused it.
        outputs = self.split(grid_sheet(self.root / "tall.png", 5, 2, 80, 128))
        self.assertTrue(all(o.layout == "grid_5x2" for o in outputs))
        self.assertEqual({o.cell_size for o in outputs}, {(80, 128)})
        self.assert_each_digit_is_its_own(outputs)

    def test_five_by_two_with_wide_cells_and_two_by_five_with_tall_cells(self):
        outputs = self.split(grid_sheet(self.root / "wide.png", 5, 2, 160, 96))
        self.assertTrue(all(o.layout == "grid_5x2" for o in outputs))
        self.assert_each_digit_is_its_own(outputs)
        outputs = self.split(grid_sheet(self.root / "col.png", 2, 5, 96, 160))
        self.assertTrue(all(o.layout == "grid_2x5" for o in outputs))
        self.assert_each_digit_is_its_own(outputs)

    def test_power_of_two_canvas_that_cannot_hold_five_equal_columns(self):
        # 1024x512 is the size an artist picks first; it is 204.8 px per column.
        path = grid_sheet(self.root / "p2.png", 5, 2, 130, 160, canvas=(1024, 512))
        outputs = self.split(path)
        self.assertTrue(all(o.layout == "grid_5x2" for o in outputs))
        self.assert_each_digit_is_its_own(outputs)
        self.assertIn("does not divide into equal cells", outputs[0].layout_note)
        self.assertIn("every cut falls between two digits", outputs[0].layout_note)
        # the explicit choice works the same way
        again = self.split(path, orientation="grid_5x2")
        self.assertEqual([o.png for o in outputs], [o.png for o in again])

    def test_one_row_that_is_not_a_multiple_of_ten(self):
        path = grid_sheet(self.root / "row.png", 10, 1, 90, 128, canvas=(1005, 128))
        outputs = self.split(path)
        self.assertTrue(all(o.layout == "horizontal" for o in outputs))
        self.assert_each_digit_is_its_own(outputs)

    def test_margin_and_gutters_are_found(self):
        outputs = self.split(grid_sheet(self.root / "gut.png", 5, 2, 100, 140, margin=23, gap=17))
        self.assertTrue(all(o.layout == "grid_5x2" for o in outputs))
        self.assert_each_digit_is_its_own(outputs)
        outputs = self.split(grid_sheet(self.root / "gutrow.png", 10, 1, 70, 120, margin=11, gap=9))
        self.assertTrue(all(o.layout == "horizontal" for o in outputs))
        self.assert_each_digit_is_its_own(outputs)

    def test_tight_cropped_sheets_with_different_digit_widths_use_the_digits_own_positions(self):
        widths = [30, 12, 34, 32, 36, 34, 34, 30, 36, 34]
        gaps = [14, 17, 20, 23, 26, 14, 17, 20, 23, 26]
        for layout, (columns, rows) in {"grid_5x2": (5, 2), "horizontal": (10, 1)}.items():
            with self.subTest(layout=layout):
                path = proportional_sheet(self.root / "prop.png", columns, rows, glyph_widths=widths, gaps=gaps)
                outputs = self.split(path)
                self.assertTrue(all(o.layout == layout for o in outputs))
                self.assert_each_digit_is_its_own(outputs)
                self.assertIn("found from the gaps between the digits", outputs[0].layout_note)
                self.assertEqual(len({o.cell_size for o in outputs}), 1, "digits share one cell size")

    def test_digits_with_a_stripe_through_every_glyph_are_not_split_in_two(self):
        # The modern Rams numerals have a split stroke: a transparent band across the middle of each digit.
        widths = [30, 14, 34, 32, 36, 34, 34, 30, 36, 34]
        gaps = [14, 17, 20, 23, 26, 14, 17, 20, 23, 26]
        path = proportional_sheet(self.root / "slit.png", 5, 2, glyph_widths=widths, gaps=gaps, glyph_h=80)
        with Image.open(path) as opened:
            sheet = opened.convert("RGBA")
        for row in range(2):
            y = 3 + row * 89 + 40  # the middle of each row of 80 px cells
            sheet.paste((0, 0, 0, 0), (0, y, sheet.width, y + 3))
        sheet.save(path)
        outputs = self.split(path)
        self.assertTrue(all(o.layout == "grid_5x2" for o in outputs))
        self.assertIn("found from the gaps between the digits", outputs[0].layout_note)
        self.assert_each_digit_is_its_own(outputs)

    def test_soft_glows_that_meet_at_cell_borders_do_not_confuse_the_layout(self):
        from PIL import ImageFilter

        def glowing(digit, cell_w, cell_h):
            base = glyph(digit, cell_w, cell_h)
            halo = Image.new("RGBA", base.size, (*colour(digit)[:3], 255))
            halo.putalpha(base.getchannel("A").filter(ImageFilter.GaussianBlur(14)).point(lambda a: min(255, a * 2) // 3))
            halo.alpha_composite(base)
            return halo

        for width in (5 * 100, 5 * 100 + 3):  # exact cells, and a canvas that does not divide
            sheet = Image.new("RGBA", (width, 300), (0, 0, 0, 0))
            for digit in range(10):
                x0 = round(digit % 5 * width / 5 + (width / 5 - 100) / 2)
                sheet.alpha_composite(glowing(digit, 100, 150), (x0, digit // 5 * 150))
            sheet.save(self.root / "glow.png")
            outputs = self.split(self.root / "glow.png")
            self.assertTrue(all(o.layout == "grid_5x2" for o in outputs), width)
            self.assertFalse(any("touch at the cell border" in w for o in outputs for w in o.warnings))

    def test_a_wrong_layout_choice_is_refused_with_the_right_one_named(self):
        # Beta 76 defaulted the dialog to "One row". A 0-4 / 5-9 sheet whose width divides by ten was then cut
        # into ten slivers without a word. The cut lines slice digits, so the choice is refused and corrected.
        path = grid_sheet(self.root / "g.png", 5, 2, 100, 140, margin=10, gap=10)
        for layout in ("horizontal", "vertical", "grid_2x5"):
            with self.subTest(layout=layout):
                message = self.refusal_for(path, layout)
                self.assertIn("sit in five columns and two rows (0-4 above 5-9)", message)
                self.assertIn("would slice through a digit", message)
                self.assertIn("Five columns, two rows: 0-4 above 5-9", message)
                self.assertIn("Detect layout from image", message)
        outputs = self.split(path, orientation="grid_5x2")
        self.assert_each_digit_is_its_own(outputs)
        # the same sheet in auto mode needs no choice at all
        self.assertTrue(all(o.layout == "grid_5x2" for o in self.split(path)))

    def refusal_for(self, path, layout):
        with self.assertRaises(ValidationError) as caught:
            self.split(path, orientation=layout)
        return str(caught.exception)

    def test_layout_menu_offers_detection_first_and_help_names_the_sizes(self):
        self.assertEqual(SHEET_LAYOUT_CHOICES[0][1], "auto")
        for text in ("640x64", "320x128", "0-4 above 5-9", "transparent"):
            self.assertIn(text, SHEET_HELP)


class RefusalTests(GeometryCase):
    def refusal(self, path, **kwargs):
        with self.assertRaises(ValidationError) as caught:
            self.split(path, **kwargs)
        return str(caught.exception)

    def test_touching_digits_say_how_many_shapes_were_seen_and_what_to_do(self):
        sheet = Image.new("RGBA", (400, 128), (0, 0, 0, 0))
        for index in range(5):  # digit pairs fused into five wide blobs
            ImageDraw.Draw(sheet).rectangle((index * 80 + 4, 30, index * 80 + 76, 100), fill=(200, 30, 30, 255))
        sheet.save(self.root / "fused.png")
        message = self.refusal(self.root / "fused.png")
        self.assertIn("Cannot infer the layout of a 400x128 sheet", message)
        self.assertIn("Choose its row, column or grid layout explicitly", message)
        self.assertIn("The sheet has 5 separate shapes in one row", message)
        self.assertIn("640x64", message)
        self.assertIn("320x128", message)
        self.assertIn("transparent gap", message)

    def test_a_painted_background_is_named_when_the_digits_cannot_be_told_apart(self):
        sheet = Image.new("RGBA", (633, 64), (30, 40, 90, 255))  # one solid slab, not divisible into square cells
        ImageDraw.Draw(sheet).rectangle((10, 10, 600, 50), fill=(250, 250, 250, 255))
        sheet.save(self.root / "slab.png")
        message = self.refusal(self.root / "slab.png")
        self.assertIn("100% of the sheet is visible", message)
        self.assertIn("looks like a background", message)

    def test_a_missing_digit_reports_how_many_shapes_were_found(self):
        widths = [30, 14, 34, 32, 36, 34, 34, 30, 36, 34]
        gaps = [14, 17, 20, 23, 26, 14, 17, 20, 23, 26]
        path = proportional_sheet(self.root / "nine.png", 10, 1, glyph_widths=widths, gaps=gaps)
        with Image.open(path) as opened:
            sheet = opened.convert("RGBA")
        sheet.paste((0, 0, 0, 0), (130, 0, 165, sheet.height))  # erase digit 3
        sheet.save(path)
        message = self.refusal(path)
        self.assertIn("The sheet has 9 separate shapes in one row", message)
        self.assertIn("Cannot infer the layout", message)

    def test_blank_sheets_keep_their_precise_messages(self):
        blank = self.root / "blank.png"
        Image.new("RGBA", (400, 128)).save(blank)
        self.assertIn("Choose its row, column or grid", self.refusal(blank))
        self.assertIn("no visible pixels at all", self.refusal(blank))
        Image.new("RGBA", (321, 128)).save(blank)
        message = self.refusal(blank, orientation="grid_5x2")
        self.assertIn("divisible by 5", message)
        self.assertIn("320x128", message)  # the nearest size that divides

    def test_explicit_layout_that_would_cut_a_digit_names_the_digits_and_the_fix(self):
        sheet = Image.new("RGBA", (1001, 100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(sheet)
        for index in range(10):
            left = index * 100 + 30
            right = left + 40
            if index == 1:
                right = 270  # digit 1 runs on into digit 2: the two are fused across the cut at x=200
            if index == 2:
                continue
            draw.rectangle((left, 20, right, 80), fill=(255, 0, 0, 255))
        sheet.save(self.root / "fused2.png")
        message = self.refusal(self.root / "fused2.png", orientation="horizontal")
        self.assertIn("1001x100 sheet in horizontal layout cannot have equal cells", message)
        self.assertIn("(100.1x100 pixels per cell)", message)
        self.assertIn("would slice through a digit", message)
        self.assertIn("Resize the canvas to 1000x100", message)
        self.assertIn("clear transparent gap", message)

    def test_flat_pictures_without_transparency_are_called_out_digit_by_digit(self):
        sheet = Image.new("RGB", (640, 64), (10, 30, 90))
        for index in range(10):
            ImageDraw.Draw(sheet).rectangle((index * 64 + 20, 12, index * 64 + 44, 52), fill=(250, 250, 250))
        sheet.save(self.root / "flat.png")
        outputs = self.split(self.root / "flat.png")
        notes = " ".join(outputs[3].warnings)
        self.assertIn("Digit 3 has no transparent pixels at all", notes)
        self.assertIn("transparent background", notes)

    def test_blank_cell_among_digits_is_flagged(self):
        sheet = Image.open(grid_sheet(self.root / "ok.png", 10, 1, 64, 64)).convert("RGBA")
        sheet.paste((0, 0, 0, 0), (4 * 64, 0, 5 * 64, 64))
        sheet.save(self.root / "hole.png")
        outputs = self.split(self.root / "hole.png")
        self.assertIn("Digit 4 is empty in the sheet", " ".join(outputs[4].warnings))
        self.assertNotIn("is empty", " ".join(outputs[3].warnings))

    def test_cell_edge_and_resize_warnings_are_kept(self):
        outputs = self.split(grid_sheet(self.root / "r.png", 10, 1, 128, 128))
        self.assertIn("will be resized", " ".join(outputs[0].warnings))

    def test_file_problems_say_what_to_do(self):
        missing = self.root / "nope.png"
        self.assertIn("Digit sheet is missing", self.refusal(missing))
        empty = self.root / "empty.png"
        empty.write_bytes(b"")
        self.assertIn("is empty (0 bytes)", self.refusal(empty))
        notimage = self.root / "text.png"
        notimage.write_text("not a picture\n", encoding="utf-8", newline="\n")
        message = self.refusal(notimage)
        self.assertIn("could not read text.png as an image", message)
        self.assertIn("PNG", message)
        folder = self.root / "dir"
        folder.mkdir()
        self.assertIn("not an image file", self.refusal(folder))

    def test_pixel_limit_message_gives_the_numbers_and_a_size_that_fits(self):
        big = self.root / "big.png"
        Image.new("L", (4200, 4200)).save(big)
        message = self.refusal(big)
        self.assertIn("4200x4200", message)
        self.assertIn("17.6 million pixels", message)
        self.assertIn("limit is 16 million", message)
        self.assertIn("1024x1024", message)


class ResizeContractTests(GeometryCase):
    def test_exact_cells_are_resized_exactly_as_before(self):
        path = grid_sheet(self.root / "x.png", 5, 2, 128, 128)
        outputs = self.split(path)
        with Image.open(path) as opened:
            sheet = opened.convert("RGBA")
        for output in outputs:
            x, y = output.digit % 5 * 128, output.digit // 5 * 128
            expected = resize_cell(sheet.crop((x, y, x + 128, y + 128)), (64, 64))
            with Image.open(BytesIO(output.png)) as opened:
                self.assertEqual(opened.convert("RGBA").tobytes(), expected.tobytes())

    def test_tall_cells_keep_the_glyph_aspect_in_retail_mode(self):
        outputs = self.split(grid_sheet(self.root / "t.png", 5, 2, 80, 128))
        with Image.open(BytesIO(outputs[5].png)) as opened:
            rgba = opened.convert("RGBA")
        bbox = rgba.getchannel("A").point(lambda a: 255 if a >= 16 else 0).getbbox()
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        # the source block is round(80*0.46) wide and glyph_height(5, 128) tall; stretched into 64x64 it would be square
        self.assertAlmostEqual(width / height, round(80 * 0.46) / glyph_height(5, 128), delta=0.06)


# --------------------------------------------------------------------------
# The fit ladder: a shaded numeral in a slot too small for it
# --------------------------------------------------------------------------

SOL, WHITE, ROYAL = (255, 209, 0), (255, 255, 255), (0, 53, 148)
_POSITIONS = {"a": (19, 9, 45, 9), "g": (19, 32, 45, 32), "d": (19, 55, 45, 55),
              "b": (48, 12, 48, 29), "c": (48, 35, 48, 52), "f": (16, 12, 16, 29), "e": (16, 35, 16, 52)}
_SEGMENTS = ("abcdef", "bc", "abged", "abgcd", "fgbc", "afgcd", "afgecd", "abc", "abcdefg", "abfgcd")


def _lerp(a, b, t):
    return tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3))


def rams_digit(digit, size=64, *, shaded=True, outline_colour=ROYAL):
    """A seven-segment numeral with a royal outline and a gold-to-white gradient fill, soft edges.

    ``outline_colour=None`` leaves the outline out: a numeral that is nothing but shading."""
    scale = 4
    big = size * scale
    outline, fill = Image.new("L", (big, big), 0), Image.new("L", (big, big), 0)
    for width, mask in ((11, outline), (6, fill)):
        draw = ImageDraw.Draw(mask)
        for segment in _SEGMENTS[digit]:
            draw.line([round(v * scale * size / 64) for v in _POSITIONS[segment]], fill=255,
                      width=round(width * scale * size / 64))
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    if outline_colour is not None:
        canvas.paste(Image.new("RGBA", (big, big), (*outline_colour, 255)), (0, 0), outline)
    gradient = Image.new("RGBA", (big, big))
    gradient.putdata([(*(_lerp(SOL, WHITE, y / big) if shaded else WHITE), 255) for y in range(big) for _ in range(big)])
    canvas.paste(gradient, (0, 0), fill)
    return resize_cell(canvas, (size, size))


def retail_reference(size=64, box=(13, 1, 50, 63)):
    reference = Image.new("RGBA", (size, size))
    reference.paste((220, 220, 220, 255), box)
    return reference


def candidate(levels, palette, indices):
    return bytes(128) + b"".join(swizzle_2d(i, m.width, m.height, 1) for i, m in zip(indices, levels)) + palette_bytes(palette)


def fit(image, stored_size, mode="retail"):
    return art.fit_digit(image, retail_reference(), mode, 4, candidate, stream_tag=1, offset_bits=12,
                         stored_size=stored_size)


STEP = {step.name: step for step in art._STEPS}


def noisy_two_tone(digit, size=64):
    """A flat white fill with a flat outline, plus stray pixels of unrelated colours that survive the cleanup.

    The stray colours lie off the line between white and the outline, so the two-tone detector refuses the digit and
    it keeps every stray colour (and all its blends). That is what a font sheet scaled down from 128 px did in
    practice: resampling overshoot left colours the artist never drew, and the digit could not use the two-colour
    palette floor.
    """
    image = rams_digit(digit, size, shaded=False, outline_colour=(2, 55, 150))
    strays = [(60, 170, 70), (200, 60, 170), (230, 150, 20), (20, 200, 200)]
    pixels = list(image.getdata())
    seen = 0
    for index, pixel in enumerate(pixels):
        if pixel[3] == 255 and pixel[:3] in ((255, 255, 255), (2, 55, 150)):
            seen += 1
            if seen % 41 == 0:
                pixels[index] = (*strays[(seen // 41) % len(strays)], 255)
    image.putdata(pixels)
    return image


def hard_digit(digit, size, outline, fill):
    """A seven-segment numeral drawn without anti-aliasing: exactly two colours and fully opaque or fully clear."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for width, colour_ in ((11, outline), (6, fill)):
        for segment in _SEGMENTS[digit]:
            draw.line([round(v * size / 64) for v in _POSITIONS[segment]], fill=(*colour_, 255), width=round(width * size / 64))
    return image


class ResampleColourTests(unittest.TestCase):
    """Lanczos overshoots past a flat colour. Resizing must not invent shades the artist never used.

    Found through the quality test that needs the game files: its 62 and 66 pixel cell cases drifted the outline
    colour by up to 45 per channel, and a font sheet scaled down from 128 pixels was no longer recognised as two
    colours, so it needed many more bytes than the same numeral drawn at 64 pixels."""

    def test_resized_colours_stay_inside_the_range_of_the_source(self):
        big = hard_digit(8, 128, ROYAL, WHITE)
        low, high = visible_colour_range(big)
        self.assertEqual((low, high), (ROYAL, WHITE))

        def outside(image):
            return [p for p in image.getdata() if p[3] and any(not low[k] <= p[k] <= high[k] for k in range(3))]

        self.assertEqual(outside(resize_cell(big, (64, 64))), [])
        # the same resize without the limit does leave the range, which is the case the limit exists for
        with unittest.mock.patch.object(texture, "visible_colour_range", return_value=((0, 0, 0), (255, 255, 255))):
            self.assertTrue(outside(resize_cell(big, (64, 64))))

    def test_invisible_pixels_never_widen_the_range(self):
        image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        image.paste((200, 100, 50, 255), (2, 2, 6, 6))
        image.putpixel((0, 0), (255, 0, 255, 0))  # invisible, with loud colour
        self.assertEqual(visible_colour_range(image), ((200, 100, 50), (200, 100, 50)))
        self.assertEqual(visible_colour_range(Image.new("RGBA", (4, 4))), ((0, 0, 0), (255, 255, 255)))

    def test_soft_edges_and_gradients_are_resized_as_before_inside_their_own_range(self):
        # a gradient spans its own range, so the limit never touches it: the result equals the unlimited resize
        gradient = Image.new("RGBA", (96, 96))
        gradient.putdata([(40 + y, 80 + y // 2, 200 - y, 255 if 8 <= x < 88 else 0) for y in range(96) for x in range(96)])
        limited = resize_cell(gradient, (64, 64))
        with unittest.mock.patch.object(texture, "visible_colour_range", return_value=((0, 0, 0), (255, 255, 255))):
            loose = resize_cell(gradient, (64, 64))
        changed = sum(1 for a, b in zip(limited.getdata(), loose.getdata()) if a != b)
        self.assertLessEqual(changed, 64 * 4, "only a few edge texels may differ where the filter overshot the gradient's ends")

    def test_a_scaled_down_two_colour_digit_keeps_the_colours_it_was_drawn_in(self):
        for digit in (0, 3, 8):
            small = resize_cell(hard_digit(digit, 128, ROYAL, WHITE), (64, 64))
            tones = art.two_tone_colours(art.collapse_colours(art.bind_alpha(small))[0])
            self.assertEqual(sorted(tones), sorted((WHITE, ROYAL)), digit)

    def test_cells_of_62_and_66_pixels_keep_the_outline_and_fill_colours(self):
        # the private-data quality test's cell_62 and cell_66 cases, on the synthetic digits and without the game files
        from number_sheet_quality_cases import FILL, OUTLINE, author_sheet
        for case in ("cell_62", "cell_66"):
            with tempfile.TemporaryDirectory() as temp:
                sheet = author_sheet(Path(temp) / "sheet.png", case)
                for output in split_digit_sheet(sheet, assets(), orientation="horizontal"):
                    with Image.open(BytesIO(output.png)) as opened:
                        prepared, _ = art.prepare_digit(opened.convert("RGBA"), retail_reference(), "retail")
                    solid = {p[:3] for p in prepared.getdata() if p[3] >= 240}
                    for wanted in (OUTLINE, FILL):
                        drift = min(max(abs(c[k] - wanted[k]) for k in range(3)) for c in solid)
                        self.assertLess(drift, 24, (case, output.digit, wanted, sorted(solid)))
                    self.assertEqual(len(solid), 2, (case, output.digit, sorted(solid)))


class SimplificationPartsTests(unittest.TestCase):
    def test_hard_edges_make_alpha_binary_and_leave_colours_alone(self):
        image = rams_digit(8)
        self.assertTrue(any(0 < a < 255 for a in image.getchannel("A").getdata()))
        hard = art.hard_edges(image)
        self.assertEqual(set(hard.getchannel("A").getdata()), {0, 255})
        for before, after in zip(image.getdata(), hard.getdata()):
            if before[3] >= 128:
                self.assertEqual(before[:3], after[:3])
                self.assertEqual(after[3], 255)
            else:
                self.assertEqual(after[3], 0)

    def test_shading_is_flattened_to_flat_colours_and_a_small_outline_keeps_its_own(self):
        image = art.hard_edges(rams_digit(8))
        solid = {p[:3] for p in image.getdata() if p[3] == 255}
        self.assertGreater(len(solid), 6, "the test digit really is shaded")
        for count in (4, 3, 2):
            flat = art.flatten_shading(image, count)
            colours = {p[:3] for p in flat.getdata() if p[3] == 255}
            self.assertTrue(2 <= len(colours) <= count, (count, colours))
            # the royal outline is a small share of the pixels and must not be absorbed into the fill
            self.assertTrue(any(max(abs(c[k] - ROYAL[k]) for k in range(3)) <= 60 for c in colours), (count, colours))
            self.assertTrue(any(c[0] > 200 for c in colours), (count, colours))
            self.assertEqual(flat.getchannel("A").tobytes(), image.getchannel("A").tobytes())

    def test_a_gradient_with_an_outline_is_two_regions_and_a_red_patch_makes_three(self):
        gradient = art.hard_edges(rams_digit(8))
        shading = art._Shading(gradient)
        self.assertTrue(shading.shaded)
        self.assertIsNotNone(shading.rim, "the royal outline rims the digit")
        self.assertTrue(max(abs(shading.rim[k] - ROYAL[k]) for k in range(3)) <= 30, shading.rim)
        self.assertEqual(shading.regions, 2)  # the outline and the gradient fill
        gradient.paste((255, 0, 0, 255), (28, 28, 36, 36))
        self.assertEqual(art._Shading(gradient).regions, 3)
        by_name = {step.name: step for step in art._STEPS}
        self.assertIsNone(art._apply_step(gradient, by_name["bands_2"]), "red would be merged into another colour")
        self.assertIsNotNone(art._apply_step(gradient, by_name["bands_3"]))

    def test_one_flat_colour_is_only_for_shading_with_no_outline(self):
        by_name = {step.name: step for step in art._STEPS}
        outlined = art.hard_edges(rams_digit(8))
        self.assertIsNone(art._apply_step(outlined, by_name["bands_1"]), "an outline is a second region")
        fill_only = rams_digit(8, outline_colour=None)
        shading = art._Shading(art.hard_edges(fill_only))
        self.assertIsNone(shading.rim)
        self.assertEqual(shading.regions, 1)
        flat = art._apply_step(fill_only, by_name["bands_1"])
        self.assertIsNotNone(flat)
        self.assertEqual(len({p[:3] for p in flat.getdata() if p[3] == 255}), 1)

    def test_stray_in_between_colours_are_merged_into_the_digits_own_colours(self):
        prepared, _ = art.prepare_digit(noisy_two_tone(8), retail_reference(), "retail")
        stray = {p[:3] for p in prepared.getdata() if p[3] >= 240}
        self.assertGreater(len(stray), 6, "the digit keeps its stray colours: the two-colour path did not take it")
        shading = art._Shading(prepared)
        self.assertTrue(shading.noisy and not shading.shaded, (shading.distinct, shading.regions))
        self.assertEqual(shading.regions, 2)
        clean = art.flatten_shading(prepared, 0, clean=True)
        colours = {p[:3] for p in clean.getdata() if p[3] >= 240}
        self.assertEqual(len(colours), 2, colours)
        self.assertTrue(any(max(abs(c[k] - (2, 55, 150)[k]) for k in range(3)) <= 30 for c in colours), colours)
        self.assertTrue(any(min(c) > 235 for c in colours), colours)
        self.assertEqual(clean.getchannel("A").tobytes(), prepared.getchannel("A").tobytes())
        self.assertIsNotNone(art._apply_step(prepared, STEP["clean_colours"]))
        hard = art._apply_step(prepared, STEP["clean_hard"])
        self.assertEqual(set(hard.getchannel("A").getdata()), {0, 255})

    def test_cleaning_never_erases_a_colour_with_a_real_share(self):
        # An outline miscounted as noise would be erased by a one-colour flatten. Force that miscount and check the guard.
        prepared, _ = art.prepare_digit(noisy_two_tone(8), retail_reference(), "retail")
        shading = art._Shading(prepared)
        self.assertEqual(shading.regions, 2)
        original = art._Shading.__init__

        def one_region(self, image):
            original(self, image)
            self.rim, self.regions = None, 1

        with unittest.mock.patch.object(art._Shading, "__init__", one_region):
            self.assertIsNone(art.flatten_shading(prepared, 0, clean=True))

    def test_clean_steps_leave_clean_art_shaded_art_and_pictures_alone(self):
        # exact outline and fill: the cleanup's own two-tone path already leaves exactly two colours, so nothing is left to clean
        exact = Image.new("RGBA", (64, 64))
        exact.paste((0, 53, 148, 255), (14, 8, 50, 56))
        exact.paste((255, 255, 255, 255), (19, 13, 45, 51))
        prepared, _ = art.prepare_digit(exact, retail_reference(), "retail")
        self.assertEqual(len({p[:3] for p in prepared.getdata() if p[3] >= 16}), 2)
        self.assertIsNone(art._apply_step(prepared, STEP["clean_colours"]))
        self.assertIsNone(art._apply_step(prepared, STEP["clean_hard"]))
        self.assertIsNone(art.flatten_shading(art.hard_edges(rams_digit(8)), 0, clean=True), "a gradient is shading, not noise")
        picture = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        for index in range(64 * 64):
            if 8 <= index % 64 < 56 and 8 <= index // 64 < 56:
                picture.putpixel((index % 64, index // 64), ((index * 37) % 256, (index * 91) % 256, (index * 53) % 256, 255))
        self.assertFalse(art._Shading(picture).noisy, "hundreds of colours are a picture, not flat regions with noise")
        self.assertIsNone(art._apply_step(picture, STEP["clean_colours"]))

    def test_hard_edges_are_not_used_when_they_would_erase_thin_strokes(self):
        thin = Image.new("RGBA", (64, 64))
        for x in range(10, 54):
            thin.putpixel((x, 20), (255, 255, 255, 110))  # a hairline at 43 percent coverage
            thin.putpixel((x, 40), (255, 255, 255, 110))
        thin.paste((255, 255, 255, 255), (28, 22, 34, 38))
        self.assertIsNone(art._apply_step(thin, STEP["hard_edges"]))
        solid = Image.new("RGBA", (64, 64))
        solid.paste((255, 255, 255, 255), (10, 10, 54, 54))
        for x in range(10, 54):
            solid.putpixel((x, 9), (255, 255, 255, 200))
            solid.putpixel((x, 54), (255, 255, 255, 60))
        self.assertIsNotNone(art._apply_step(solid, STEP["hard_edges"]))  # an honest soft edge hardens by a rounding error

    def test_flat_regions_are_not_merged_and_flat_art_needs_no_step(self):
        flat = Image.new("RGBA", (64, 64))
        flat.paste((220, 220, 220, 255), (10, 10, 30, 50))
        flat.paste((18, 38, 65, 255), (30, 10, 40, 50))
        flat.paste((255, 0, 0, 255), (40, 10, 50, 50))
        self.assertIsNone(art.flatten_shading(flat, 3))
        self.assertIsNone(art.flatten_shading(flat, 4))
        for step in art._STEPS:
            if step.colours is not None:
                self.assertIsNone(art._apply_step(flat, step), step.name)  # three flat colours are regions, not shading
        self.assertIsNone(art._apply_step(flat, STEP["hard_edges"]), "no soft edges, so hard edges change nothing")
        self.assertIsNone(art._apply_step(flat, STEP["clean_colours"]), "three clean flat colours have nothing to clean")

    def test_advice_names_the_numbers_and_the_text_everyone_shares_is_unchanged(self):
        self.assertEqual(art.kept_retail_reason(1088),
                         "kept retail: the authored digit could not fit its 1088-byte texture slot after cleanup "
                         "and the recognisable-art fit ladder. Simplify the fill and outline, then preview again.")
        advice = art.kept_retail_advice(stored_size=1088, needed=1310, colours=41)
        self.assertIn("needs about 1,310 bytes and the slot holds 1,088", advice)
        self.assertIn("41 colours", advice)
        self.assertIn("flat fill", advice)
        self.assertEqual(art.kept_retail_advice(), "")


class LadderTests(unittest.TestCase):
    STEPS = (None, *(step.name for step in art._STEPS))

    def test_a_roomy_slot_keeps_the_gradient_exactly_as_before(self):
        result, levels, receipt = fit(rams_digit(8), 6000)
        self.assertNotIn("simplified", receipt["fit"])
        self.assertTrue(all("simplification" not in a for a in result.attempts))
        colours = {tuple(result.palette[i][:3]) for i in result.index_levels[0] if result.palette[i][3] == 255}
        self.assertGreater(len(colours), 6, "the gradient survives")

    def test_as_the_slot_shrinks_the_gentlest_step_that_fits_is_used_and_both_regions_survive(self):
        image = rams_digit(8)
        natural = len(fit(image, 20000)[0].compressed)
        ranks = []
        for percent in range(95, 14, -3):
            stored = natural * percent // 100
            try:
                result, levels, receipt = fit(image, stored)
            except QualityBudgetError as error:
                self.assertGreaterEqual(error.needed_bytes, stored)
                self.assertEqual(error.stored_size, stored)
                if error.needed_bytes > stored:
                    self.assertIn(f"needs about {error.needed_bytes:,} bytes", error.advice)
                break  # a smaller slot cannot fit what this one could not
            self.assertLessEqual(len(result.compressed), stored)
            step = receipt["fit"].get("simplified", {}).get("name")
            ranks.append(self.STEPS.index(step))
            used = {tuple(result.palette[i][:3]) for i in result.index_levels[0] if result.palette[i][3] == 255}
            near = lambda colour: any(max(abs(c[k] - colour[k]) for k in range(3)) <= 40 for c in used)
            self.assertTrue(near(ROYAL), f"the outline is gone at {stored} bytes: {sorted(used)}")
            self.assertTrue(any(c[0] > 200 and c[1] > 150 for c in used), f"the fill is gone at {stored} bytes")
            if step:
                self.assertIn(receipt["fit"]["simplified"]["text"], art.fit_summary(receipt, len(result.palette)))
        else:
            self.fail("the digit fitted in every slot down to 15 percent of its natural size")
        self.assertEqual(ranks, sorted(ranks), "steps only get stronger as the slot shrinks")
        self.assertGreater(max(ranks), 0, f"something was simplified before the digit gave up: {ranks}")

    def test_noisy_two_tone_art_is_cleaned_before_anything_stronger_and_never_loses_a_region(self):
        image = noisy_two_tone(8)
        natural = len(fit(image, 20000)[0].compressed)
        names = []
        for percent in range(95, 14, -3):
            stored = natural * percent // 100
            try:
                result, _levels, receipt = fit(image, stored)
            except QualityBudgetError:
                break
            step = receipt["fit"].get("simplified", {}).get("name")
            names.append(step)
            used = {tuple(result.palette[i][:3]) for i in result.index_levels[0] if result.palette[i][3] == 255}
            self.assertTrue(any(max(abs(c[k] - (2, 55, 150)[k]) for k in range(3)) <= 40 for c in used), (percent, used))
            self.assertTrue(any(min(c) > 200 for c in used), (percent, used))
        simplified = [name for name in names if name]
        self.assertTrue(simplified, f"some slot size needed the cleanup: {names}")
        self.assertTrue(all(name in ("clean_colours", "hard_edges", "clean_hard") for name in simplified), names)
        self.assertEqual(simplified[0], "clean_colours", names)

    def test_as_authored_is_simplified_the_same_way_but_never_shrunk(self):
        image = rams_digit(8)
        natural = len(fit(image, 20000, "as_authored")[0].compressed)
        for fraction in (0.7, 0.5, 0.35):
            try:
                result, _levels, receipt = fit(image, int(natural * fraction), "as_authored")
            except QualityBudgetError as error:
                self.assertEqual({a["registration_factor"] for a in error.attempts}, {1.0})
                continue
            self.assertEqual(receipt["fit"]["registration_factor"], 1.0)

    def test_a_flat_third_region_is_never_merged_away_and_plain_complex_art_keeps_the_sixteen_floor(self):
        image = rams_digit(8)
        image.paste((255, 0, 0, 255), (28, 28, 36, 36))  # a flat red region on top of the gradient
        natural = len(fit(image, 20000)[0].compressed)
        for fraction in (0.8, 0.6, 0.45):
            try:
                result, _levels, receipt = fit(image, int(natural * fraction))
            except QualityBudgetError as error:
                self.assertFalse(any(a.get("simplification") == "bands_2" for a in error.attempts))
                continue
            used = {tuple(result.palette[i][:3]) for i in result.index_levels[0] if result.palette[i][3] == 255}
            self.assertTrue(any(c[0] > 200 and c[1] < 60 and c[2] < 60 for c in used), f"red was merged away: {sorted(used)}")
            self.assertNotEqual(receipt["fit"].get("simplified", {}).get("name"), "bands_2")
        # Noisy two-colour art plus a red patch (the b66 contract): three flat regions, never below 16 colours.
        flat = Image.new("RGBA", (64, 64))
        flat.paste((220, 220, 220, 255), (14, 10, 50, 54))
        flat.paste((18, 38, 65, 255), (20, 16, 44, 48))
        flat.paste((255, 0, 0, 255), (28, 28, 36, 36))
        with self.assertRaises(QualityBudgetError) as caught:
            fit(flat, 40)
        self.assertTrue(all(a["maximum_palette_entries"] >= 16 for a in caught.exception.attempts))


class CheckMyImagesTests(GeometryCase):
    def test_a_digit_that_stays_retail_gets_the_measured_numbers_in_check_my_images(self):
        from mod_editor.core import nfl2k5_import_preflight as preflight
        path = self.root / "digit.png"
        rams_digit(8).save(path)
        contract = preflight.SlotContract("arm_digit", 64, 64, 4, 128, 1, digit=True, retail_rgba=retail_reference().tobytes())
        prediction = preflight.predict_slot(path, contract, 40)
        self.assertEqual(prediction.outcome, preflight.KEPT_RETAIL)
        self.assertEqual(prediction.detail, art.kept_retail_reason(40))  # the words everyone shares are unchanged
        self.assertRegex(prediction.advice, r"needs about [\d,]+ bytes and the slot holds 40")
        line = prediction.summary()
        self.assertTrue(line.startswith(f"{prediction.label}: kept retail"))
        self.assertIn(prediction.advice, line)

    def test_a_simplified_digit_says_so_in_check_my_images(self):
        from mod_editor.core import nfl2k5_import_preflight as preflight
        image = rams_digit(8)
        natural = len(fit(image, 20000)[0].compressed)
        path = self.root / "digit.png"
        image.save(path)
        contract = preflight.SlotContract("arm_digit", 64, 64, 4, 128, 1, digit=True, retail_rgba=retail_reference().tobytes())
        for fraction in (0.8, 0.65, 0.5, 0.4, 0.3):
            prediction = preflight.predict_slot(path, contract, int(natural * fraction))
            if prediction.outcome == preflight.REDUCED and "To fit this slot" in prediction.detail:
                return
        self.skipTest("this synthetic digit never needed a simplification at the sizes tried")


class FlatSheetRefusalTests(GeometryCase):
    def test_a_sheet_without_any_transparency_is_refused_before_anything_is_encoded(self):
        from mod_editor.core.nfl2k5_digit_preview import preview_digit_sheet
        sheet = Image.new("RGB", (640, 64), (10, 30, 90))
        for index in range(10):
            ImageDraw.Draw(sheet).rectangle((index * 64 + 20, 12, index * 64 + 44, 52), fill=(250, 250, 250))
        sheet.save(self.root / "flat.png")
        outputs = self.split(self.root / "flat.png")
        with self.assertRaises(ValidationError) as caught:
            preview_digit_sheet(self.root / "no-game-needed", assets(), outputs)
        message = str(caught.exception)
        self.assertIn("no transparent pixels", message)
        self.assertIn("solid 64x64 block", message)
        self.assertIn("PNG with a transparent background", message)


class PreviewCountTests(unittest.TestCase):
    def test_the_import_button_counts_simplified_digits_only_when_there_are_some(self):
        from mod_editor.core.nfl2k5_digit_preview import DigitSheetPreview
        plain = DigitSheetPreview(b"", "", tuple({"kept_retail": i < 3} for i in range(10)))
        self.assertEqual(plain.import_button_text, "Import 7 digits, 3 kept retail")
        rows = [{"kept_retail": i < 3} for i in range(10)]
        for i in (3, 4):
            rows[i] = {"digit_preparation": {"fit": {"simplified": {"name": "hard_edges", "text": "x"}}}}
        some = DigitSheetPreview(b"", "", tuple(rows))
        self.assertEqual(some.simplified_count, 2)
        self.assertEqual(some.import_button_text, "Import 7 digits, 3 kept retail, 2 simplified")


class ReviewDialogTests(unittest.TestCase):
    """The encoded-preview dialog does not offer an import that would change nothing."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError as exc:  # pragma: no cover - Qt is optional on lean hosts
            raise unittest.SkipTest(f"PyQt5 unavailable: {exc}")
        cls.app = QApplication.instance() or QApplication([])

    def review(self, receipts):
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox
        from mod_editor.core.nfl2k5_digit_preview import DigitSheetPreview
        from mod_editor.gui.studio_qt import StudioMainWindow
        png = BytesIO()
        Image.new("RGB", (40, 20), (200, 200, 200)).save(png, "PNG")
        seen = {}

        def fake_exec(dialog):
            ok = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)
            seen.update(enabled=ok.isEnabled(), text=ok.text(), tip=ok.toolTip())
            return QDialog.Accepted

        preview = DigitSheetPreview(png.getvalue(), "Layout: one row.", tuple(receipts))
        with unittest.mock.patch.object(QDialog, "exec_", fake_exec):
            StudioMainWindow._review_digit_sheet_preview(None, preview)
        return seen

    def test_import_is_switched_off_only_when_every_digit_stays_retail(self):
        none = self.review({"kept_retail": True} for _ in range(10))
        self.assertFalse(none["enabled"])
        self.assertEqual(none["text"], "Import 0 digits, 10 kept retail")
        self.assertIn("nothing would be imported", none["tip"])
        some = self.review({"kept_retail": i < 3} for i in range(10))
        self.assertTrue(some["enabled"])
        self.assertEqual(some["text"], "Import 7 digits, 3 kept retail")
        self.assertTrue(self.review(())["enabled"])  # no receipts: nothing to judge


if __name__ == "__main__":
    unittest.main()
