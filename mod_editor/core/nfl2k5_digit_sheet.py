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
import stat
from typing import Iterable, Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import ValidationError


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
    "Use ten equal cells in digit order, with no gaps, labels or outside border. "
    "Choose one row, one column, five columns by two rows, or two columns by five rows. "
    "PNG with transparency is recommended. Keep each digit's padding inside its cell. "
    "Each complete cell is resized to the selected jersey, helmet or arm slot. "
    "See docs/mod_editor/number_sheets.md for examples."
)


@dataclass(frozen=True)
class DigitSheetPng:
    digit: int
    asset_id: str
    width: int
    height: int
    png: bytes


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
) -> tuple[DigitSheetPng, ...]:
    """Return ten exact target-sized PNGs without modifying *source*."""

    targets = _targets(assets)
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
            f"The {image.width}x{image.height} sheet cannot have equal cells: "
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
        if cell.size != (width, height):
            cell = cell.resize((width, height), Image.Resampling.LANCZOS)
        stream = BytesIO()
        cell.save(stream, format="PNG", optimize=False, compress_level=9)
        outputs.append(DigitSheetPng(
            digit=digit,
            asset_id=str(getattr(target, "asset_id")),
            width=width,
            height=height,
            png=stream.getvalue(),
        ))
    return tuple(outputs)


__all__ = ["DigitSheetPng", "MAX_SHEET_BYTES", "SHEET_LAYOUTS", "SHEET_HELP", "split_digit_sheet"]
