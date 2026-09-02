"""Split one user-authored 0–9 sheet into exact NFL 2K5 digit slots.

The game stores every digit as its own fixed-size texture, while font artists
normally work on one horizontal or vertical sheet.  This bridge accepts either
layout at any sensible authoring resolution, resamples each cell independently,
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
MAX_SHEET_PIXELS = 160_000_000
Orientation = Literal["auto", "horizontal", "vertical"]


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
    if orientation not in {"auto", "horizontal", "vertical"}:
        raise ValidationError("Digit sheet orientation must be automatic, horizontal, or vertical.")
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
            opened.seek(0)
            image = ImageOps.exif_transpose(opened).convert("RGBA")
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise ValidationError(f"Could not read that digit-sheet image: {exc}") from exc
    if image.width * image.height > MAX_SHEET_PIXELS:
        raise ValidationError("That digit sheet is too large to process safely.")
    chosen = orientation
    if chosen == "auto":
        chosen = "horizontal" if image.width >= image.height else "vertical"
    primary = image.width if chosen == "horizontal" else image.height
    secondary = image.height if chosen == "horizontal" else image.width
    if primary < 10 or secondary < 1:
        raise ValidationError("The digit sheet is too small to contain ten cells.")

    outputs: list[DigitSheetPng] = []
    for digit, target in enumerate(targets):
        first = round(primary * digit / 10)
        last = round(primary * (digit + 1) / 10)
        box = (
            (first, 0, last, secondary)
            if chosen == "horizontal"
            else (0, first, secondary, last)
        )
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


__all__ = ["DigitSheetPng", "MAX_SHEET_BYTES", "split_digit_sheet"]
