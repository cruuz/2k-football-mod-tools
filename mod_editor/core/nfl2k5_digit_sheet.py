"""Split one user-authored 0–9 sheet into exact NFL 2K5 digit slots.

The game stores every digit as its own fixed-size texture, while font artists
normally work on a strip or grid. This bridge accepts four explicit layouts,
resamples each equal cell independently,
and returns ten exact RGBA PNGs in digit order.  Per-target dimensions come from
the live uniform catalog; no family-wide 64x64 assumption is made.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import math
import stat
from typing import Iterable, Literal

from PIL import Image, ImageOps, UnidentifiedImageError, PngImagePlugin

from .errors import ValidationError
from .nfl2k5_digit_texture import resize_cell


MAX_SHEET_BYTES = 128 * 1024 * 1024
MAX_SHEET_PIXELS = 16_000_000
Orientation = Literal["auto", "horizontal", "vertical", "grid_5x2", "grid_2x5"]
SHEET_LAYOUTS = (
    ("One row: 0 1 2 3 4 5 6 7 8 9", "horizontal"),
    ("One column: 0 at top, 9 at bottom", "vertical"),
    ("Five columns, two rows: 0-4 above 5-9", "grid_5x2"),
    ("Two columns, five rows: 0 1, then 2 3", "grid_2x5"),
)
SHEET_HELP = (
    "Use a 640x64 transparent PNG with ten 64x64 cells in digit order. "
    "A 64x640 column, 320x128 grid or 128x320 grid also works. "
    "Use one flat fill colour and one outline colour. Keep a margin inside each cell. "
    "Leave out noise, gradients, labels and guides. AI output needs the cleanup the tool applies. "
    "Match retail size fits each glyph into its original game box. As authored keeps your placement. "
    "See docs/mod_editor/number_sheets.md for examples."
)


@dataclass(frozen=True)
class DigitSheetPng:
    digit: int
    asset_id: str
    width: int
    height: int
    png: bytes
    layout: str = ""
    cell_size: tuple[int, int] = (0, 0)
    warnings: tuple[str, ...] = ()

    @property
    def mapping_note(self) -> str:
        return (f"{self.layout}: {self.cell_size[0]}x{self.cell_size[1]} cell to "
                f"{self.width}x{self.height} slot for digit {self.digit}.")


def _targets(assets: Iterable[object]) -> tuple[object, ...]:
    rows = tuple(assets)
    if len(rows) != 10:
        raise ValidationError("A digit sheet needs exactly the ten targets 0 through 9.")
    by_digit: dict[int, object] = {}
    family: str | None = None
    selector: str | None = None
    for row in rows:
        digit = getattr(row, "digit", None)
        row_family = getattr(row, "family", None)
        row_selector = getattr(row, "set_selector", None)
        width = getattr(row, "width", None)
        height = getattr(row, "height", None)
        asset_id = getattr(row, "asset_id", None)
        if (
            type(digit) is not int
            or not 0 <= digit <= 9
            or row_family not in {"jersey", "helmet", "arm"}
            or not isinstance(row_selector, str)
            or type(width) is not int
            or type(height) is not int
            or not 1 <= width <= 4096
            or not 1 <= height <= 4096
            or not isinstance(asset_id, str)
            or not asset_id
            or digit in by_digit
        ):
            raise ValidationError("The selected digit family has an invalid target catalog.")
        family = row_family if family is None else family
        selector = row_selector if selector is None else selector
        if row_family != family or row_selector != selector:
            raise ValidationError("One digit sheet may target only one family in one uniform set.")
        by_digit[digit] = row
    if set(by_digit) != set(range(10)):
        raise ValidationError("The selected digit family does not contain every digit 0 through 9.")
    return tuple(by_digit[digit] for digit in range(10))


def split_digit_sheet(
    source: Path,
    assets: Iterable[object],
    *,
    orientation: Orientation = "auto",
    registration: str = "retail",
) -> tuple[DigitSheetPng, ...]:
    """Return ten exact target-sized PNGs without modifying *source*."""

    targets = _targets(assets)
    from .nfl2k5_digit_art import REGISTRATION_KEY, REGISTRATION_CHOICES
    if registration not in dict(REGISTRATION_CHOICES).values():
        raise ValidationError("Choose Match retail size or As authored.")
    if orientation not in {"auto", *(key for _label, key in SHEET_LAYOUTS)}:
        raise ValidationError("Choose a supported digit sheet layout. " + SHEET_HELP)
    requested = Path(source).expanduser()
    try:
        info = requested.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"Digit sheet is missing: {requested}") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or not 0 < info.st_size <= MAX_SHEET_BYTES
    ):
        raise ValidationError("Choose a regular digit-sheet image smaller than 128 MiB.")
    path = requested.resolve(strict=True)
    try:
        with Image.open(path) as opened:
            if opened.width * opened.height > MAX_SHEET_PIXELS:
                raise ValidationError("That digit sheet exceeds the 16 million pixel limit.")
            opened.seek(0)
            image = ImageOps.exif_transpose(opened).convert("RGBA")
    except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationError(f"Could not read that digit-sheet image: {exc}") from exc
    chosen = orientation
    if chosen == "auto":
        if max(image.size) < 5 * min(image.size):
            raise ValidationError(
                f"Cannot infer the layout of a {image.width}x{image.height} sheet. "
                "Choose its row, column or grid layout explicitly. " + SHEET_HELP
            )
        chosen = "horizontal" if image.width >= image.height else "vertical"
    columns, rows = {"horizontal": (10, 1), "vertical": (1, 10),
                     "grid_5x2": (5, 2), "grid_2x5": (2, 5)}[chosen]
    if image.width % columns or image.height % rows:
        raise ValidationError(
            f"The {image.width}x{image.height} sheet in {chosen} layout cannot have equal cells "
            f"({image.width / columns:g}x{image.height / rows:g} pixels per cell): "
            f"width must be divisible by {columns} and height by {rows}. "
            "Remove outside borders and gaps, or select the correct layout."
        )
    cell_width, cell_height = image.width // columns, image.height // rows
    if min(cell_width, cell_height) < 1:
        raise ValidationError("The digit sheet is too small to contain ten cells.")

    outputs: list[DigitSheetPng] = []
    for digit, target in enumerate(targets):
        x, y = digit % columns * cell_width, digit // columns * cell_height
        box = (x, y, x + cell_width, y + cell_height)
        cell = image.crop(box)
        width = int(getattr(target, "width"))
        height = int(getattr(target, "height"))
        notes = []
        if cell.size != (width, height):
            notes.append(
                f"{chosen} layout: {cell_width}x{cell_height} cell will be resized to "
                f"{width}x{height} for digit {digit}, including its padding."
            )
            if cell_width * height != cell_height * width:
                notes.append("As authored will stretch different cell and slot shapes; Match retail size preserves the glyph's aspect.")
            if cell_width < width or cell_height < height:
                notes.append("Enlarging the cell cannot restore missing edge detail.")
        alpha = cell.getchannel("A")
        bounds = alpha.getbbox()
        if bounds and (bounds[0] == 0 or bounds[1] == 0
                       or bounds[2] == cell_width or bounds[3] == cell_height):
            notes.append(f"Digit {digit} touches a cell edge; check for clipping, gaps or a background.")
        if registration == "retail" and cell_width * height != cell_height * width:
            scale = min(width / cell_width, height / cell_height)
            size = (max(1, math.floor(cell_width*scale)), max(1, math.floor(cell_height*scale)))
            glyph = resize_cell(cell, size)
            cell = Image.new("RGBA", (width, height))
            cell.paste(glyph, ((width-size[0])//2, (height-size[1])//2))
        else:
            cell = resize_cell(cell, (width, height))
        stream = BytesIO()
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text(REGISTRATION_KEY, registration)
        cell.save(stream, format="PNG", optimize=False, compress_level=9, pnginfo=metadata)
        outputs.append(DigitSheetPng(
            digit=digit,
            asset_id=str(getattr(target, "asset_id")),
            width=width,
            height=height,
            png=stream.getvalue(),
            layout=chosen,
            cell_size=(cell_width, cell_height),
            warnings=tuple(notes),
        ))
    return tuple(outputs)


__all__ = ["DigitSheetPng", "MAX_SHEET_BYTES", "SHEET_LAYOUTS", "SHEET_HELP", "split_digit_sheet"]
