"""Split one user-authored 0–9 sheet into exact NFL 2K5 digit slots.

The game stores every digit as its own fixed-size texture, while font artists
normally work on a strip or grid. This bridge accepts four explicit layouts
(one row, one column, five columns by two rows with 0-4 above 5-9, and two
columns by five rows), resamples each cell independently, and returns ten exact
RGBA PNGs in digit order. Per-target dimensions come from the live uniform
catalog; no family-wide 64x64 assumption is made.

Real exports rarely have the textbook geometry. A canvas such as 1024x512 cannot
hold five equal columns, a hand-made sheet has gaps or a margin, and digits drawn
tall and narrow have cells that are not square. The splitter therefore tries, in
order: exact equal cells (square cells are detected automatically); equal cells
cut at rounded positions, but only when every cut falls between two digits; and
the digits' own positions, found from the transparent gaps between them. It
never cuts through a digit, and it says in plain words which of these it used.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import math
import stat
from typing import Iterable, Literal

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError, PngImagePlugin

from .errors import ValidationError
from .nfl2k5_digit_texture import resize_cell


MAX_SHEET_BYTES = 128 * 1024 * 1024
MAX_SHEET_PIXELS = 16_000_000
#: Alpha at or above this is a visible digit pixel. It is the encoder's own threshold
#: (nfl2k5_digit_art.ALPHA_LOW): fainter alpha is cleaned to clear.
INK_ALPHA = 16
#: Alpha at or above this is solid enough that two digits touching at a cut line is a real collision,
#: not just two soft glows meeting.
SOLID_ALPHA = 128
Orientation = Literal["auto", "horizontal", "vertical", "grid_5x2", "grid_2x5"]
SHEET_LAYOUTS = (
    ("One row: 0 1 2 3 4 5 6 7 8 9", "horizontal"),
    ("One column: 0 at top, 9 at bottom", "vertical"),
    ("Five columns, two rows: 0-4 above 5-9", "grid_5x2"),
    ("Two columns, five rows: 0 1, then 2 3", "grid_2x5"),
)
SHEET_LAYOUT_CHOICES = (("Detect layout from image (recommended)", "auto"), *SHEET_LAYOUTS)
SHEET_HELP = (
    "Use a PNG with a transparent background and the ten digits in order: one row (0 to 9), one column, "
    "or two rows with 0-4 above 5-9. With 64x64 cells that is 640x64, 64x640, 320x128 or 128x320, "
    "and larger equal cells work too. The Studio finds the layout itself, including sheets with "
    "gaps, margins or tall cells, as long as the digits do not touch each other. "
    "A flat fill with one outline colour fits every slot. Gradients, glows and shadows are "
    "simplified when a slot is too small, and the preview shows what the game will get. "
    "Match retail size fits each glyph into its original game box. As authored keeps your placement. "
    "See docs/mod_editor/number_sheets.md for examples."
)

_GRIDS = {"horizontal": (10, 1), "vertical": (1, 10), "grid_5x2": (5, 2), "grid_2x5": (2, 5)}
_LAYOUT_WORDS = {
    "horizontal": "one row (0 to 9, left to right)",
    "vertical": "one column (0 at the top, 9 at the bottom)",
    "grid_5x2": "five columns and two rows (0-4 above 5-9)",
    "grid_2x5": "two columns and five rows (0 1, then 2 3, down to 8 9)",
}
_PRIORITY = ("horizontal", "vertical", "grid_5x2", "grid_2x5")
_Box = tuple[int, int, int, int]
_INK_LUT = [0] * INK_ALPHA + [255] * (256 - INK_ALPHA)
_SOLID_LUT = [0] * SOLID_ALPHA + [255] * (256 - SOLID_ALPHA)
#: A joined gap may be at most this fraction of a typical digit's size along the same axis.
_MAX_JOIN_ROWS, _MAX_JOIN_COLUMNS = 0.12, 0.25


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
    #: One plain sentence on how the sheet was cut (the same for all ten digits).
    layout_note: str = ""

    @property
    def mapping_note(self) -> str:
        return (f"{self.layout}: {self.cell_size[0]}x{self.cell_size[1]} cell to "
                f"{self.width}x{self.height} slot for digit {self.digit}.")


@dataclass(frozen=True)
class _Plan:
    """Where the ten cells are and how that was decided."""

    layout: str
    boxes: tuple[_Box, ...]
    note: str
    #: Cells found from the digits' own positions are equal-sized windows centred on each digit.
    #: ``sources`` is the region each window may copy pixels from, so a neighbour never leaks in.
    sources: tuple[_Box, ...] = ()
    warnings: tuple[str, ...] = ()


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


# --------------------------------------------------------------------------
# Reading the file
# --------------------------------------------------------------------------

def _mib(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MiB"


def _read_sheet(source: Path) -> Image.Image:
    """Open *source* as straight-alpha RGBA, refusing with a cause and a cure."""

    requested = Path(source).expanduser()
    try:
        info = requested.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"Digit sheet is missing: {requested}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValidationError(
            f"{requested.name} is a folder or a shortcut, not an image file. "
            "Choose the sheet image itself (a PNG with a transparent background is best)."
        )
    if info.st_size == 0:
        raise ValidationError(
            f"{requested.name} is empty (0 bytes). Export the sheet again as a PNG with a transparent background."
        )
    if info.st_size > MAX_SHEET_BYTES:
        raise ValidationError(
            f"{requested.name} is {_mib(info.st_size)}; a digit sheet can be at most 128 MiB. "
            "Export it again with smaller cells. 512x512 cells give a 5120x512 row or a 2560x1024 grid."
        )
    path = requested.resolve(strict=True)
    try:
        with Image.open(path) as opened:
            if opened.width * opened.height > MAX_SHEET_PIXELS:
                raise ValidationError(
                    f"That digit sheet is {opened.width}x{opened.height} "
                    f"({opened.width * opened.height / 1_000_000:.1f} million pixels); the limit is 16 million. "
                    "Export it again with smaller cells. 1024x1024 cells give a 10240x1024 row or a 5120x2048 grid, "
                    "which fit. The game digits are 64x64 or smaller, so larger cells add nothing."
                )
            opened.seek(0)
            image = ImageOps.exif_transpose(opened).convert("RGBA")
    except ValidationError:
        raise
    except UnidentifiedImageError as exc:
        raise ValidationError(
            f"The Studio could not read {requested.name} as an image. "
            "Save the sheet as a PNG (with a transparent background) and choose that file."
        ) from exc
    except Image.DecompressionBombError as exc:
        raise ValidationError(
            f"{requested.name} is far larger than a digit sheet should be. "
            "Export it again with smaller cells (1024x1024 cells or less)."
        ) from exc
    except (OSError, ValueError) as exc:
        raise ValidationError(
            f"{requested.name} could not be read, so it may be damaged or cut off ({exc}). "
            "Export the sheet again as a PNG."
        ) from exc
    return image


# --------------------------------------------------------------------------
# Finding the cells
# --------------------------------------------------------------------------

def _cut_positions(length: int, parts: int) -> list[int]:
    """Edges of *parts* equal pieces of *length*, rounded to whole pixels."""

    return [(index * length + parts // 2) // parts for index in range(parts + 1)]


def _grid_boxes(xs: list[int], ys: list[int], columns: int, rows: int) -> tuple[_Box, ...]:
    return tuple((xs[digit % columns], ys[digit // columns], xs[digit % columns + 1], ys[digit // columns + 1])
                 for digit in range(columns * rows))


def _straddling_cuts(solid: Image.Image, xs: list[int], ys: list[int], columns: int, rows: int) -> list[str]:
    """Plain descriptions of cut lines that would slice through a digit (empty when every cut is clean).

    A cut slices a digit when solid pixels sit on both sides of it at the same height or
    width. Checked per row or column of cells, so a gap in one row is not blamed on a digit
    in another. Soft glows that merely meet at a border do not count.
    """

    problems: list[str] = []
    for row in range(rows):
        y0, y1 = ys[row], ys[row + 1]
        for column in range(1, columns):
            x = xs[column]
            if 0 < x < solid.width:
                left, right = solid.crop((x - 1, y0, x, y1)), solid.crop((x, y0, x + 1, y1))
                if ImageChops.multiply(left, right).getbbox() is not None:
                    a, b = row * columns + column - 1, row * columns + column
                    problems.append(f"the cut between digit {a} and digit {b} (x={x}) would slice through a digit")
    for column in range(columns):
        x0, x1 = xs[column], xs[column + 1]
        for row in range(1, rows):
            y = ys[row]
            if 0 < y < solid.height:
                upper, lower = solid.crop((x0, y - 1, x1, y)), solid.crop((x0, y, x1, y + 1))
                if ImageChops.multiply(upper, lower).getbbox() is not None:
                    a, b = (row - 1) * columns + column, row * columns + column
                    problems.append(f"the cut between digit {a} and digit {b} (y={y}) would slice through a digit")
    return problems


def _empty_cells(ink: Image.Image, boxes: Iterable[_Box]) -> list[int]:
    return [digit for digit, box in enumerate(boxes) if ink.crop(box).getbbox() is None]


def _runs(profile: Iterable[int]) -> list[tuple[int, int]]:
    """[start, stop) intervals of consecutive non-zero entries."""

    runs: list[tuple[int, int]] = []
    start = None
    last = 0
    for index, value in enumerate(profile):
        last = index + 1
        if value:
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, last))
    return runs


def _merge_to(runs: list[tuple[int, int]], target: int, max_join: float) -> list[tuple[int, int]] | None:
    """Join the closest neighbouring runs until *target* remain, or None when that is not convincing.

    A join is convincing only when the gaps that were joined are small next to a typical digit
    (``max_join``) and clearly narrower than the narrowest gap that stays. Otherwise the digits
    cannot be told from parts of a digit, such as a stripe through the middle of every glyph.
    """

    groups = list(runs)
    if len(groups) < target:
        return None
    widest_joined = 0
    while len(groups) > target:
        gaps = [groups[i + 1][0] - groups[i][1] for i in range(len(groups) - 1)]
        smallest = min(range(len(gaps)), key=lambda i: (gaps[i], i))
        widest_joined = max(widest_joined, gaps[smallest])
        groups[smallest:smallest + 2] = [(groups[smallest][0], groups[smallest + 1][1])]
    if widest_joined:
        sizes = sorted(stop - start for start, stop in groups)
        if widest_joined > max_join * sizes[len(sizes) // 2]:
            return None
        if len(groups) > 1 and min(groups[i + 1][0] - groups[i][1] for i in range(len(groups) - 1)) < widest_joined * 2:
            return None
    return groups


def _edges_between(groups: list[tuple[int, int]], low: int, high: int) -> list[int]:
    """Cell edges: halfway through each gap, and the sheet's own edge at either end."""

    edges = [low]
    for left, right in zip(groups, groups[1:]):
        edges.append((left[1] + right[0]) // 2)
    edges.append(high)
    return edges


def _find_groups(mask: Image.Image, columns: int, rows: int):
    """Row bands and the digits in each, from the gaps in one visibility mask.

    Returns ``(row_bands, per_band_groups, None)`` or ``(None, None, why)``.
    """

    _x, y_profile = mask.getprojection()
    row_bands = _merge_to(_runs(y_profile), rows, _MAX_JOIN_ROWS)
    if row_bands is None:
        found = len(_runs(y_profile))
        return None, None, f"I found {found} row{'s' if found != 1 else ''} of shapes and needed {rows}"
    per_band = []
    for band, (top, bottom) in enumerate(row_bands):
        x_profile, _y = mask.crop((0, top, mask.width, bottom)).getprojection()
        groups = _merge_to(_runs(x_profile), columns, _MAX_JOIN_COLUMNS)
        if groups is None:
            found = len(_runs(x_profile))
            where = f" in row {band + 1}" if rows > 1 else ""
            return None, None, f"I found {found} shape{'s' if found != 1 else ''}{where} and needed {columns}"
        per_band.append(groups)
    return row_bands, per_band, None


def _group_plan(masks: tuple[Image.Image, ...], layout: str) -> tuple[_Plan | None, str]:
    """Cells from the digits' own positions for one layout, or (None, why not).

    Tries the visible-pixel mask first, then the solid-pixel mask (which ignores a faint glow
    that bridges neighbouring digits).
    """

    columns, rows = _GRIDS[layout]
    why = ""
    for mask in masks:
        row_bands, per_band, reason = _find_groups(mask, columns, rows)
        if row_bands is None:
            why = reason or why
            continue
        width, height = mask.size
        y_edges = _edges_between(row_bands, 0, height)
        digits: list[tuple[_Box, _Box, int]] = []  # (the digit's own pixels, region it may copy from, row band)
        for band, ((top, bottom), groups) in enumerate(zip(row_bands, per_band)):
            x_edges = _edges_between(groups, 0, width)
            for index, (left, right) in enumerate(groups):
                own = mask.crop((left, top, right, bottom)).getbbox()
                if own is None:  # a group always comes from a non-empty run
                    continue
                digits.append(((left + own[0], top + own[1], left + own[2], top + own[3]),
                               (x_edges[index], y_edges[band], x_edges[index + 1], y_edges[band + 1]), band))
        if len(digits) != 10:
            why = "a digit position was empty"
            continue
        widest = max(box[2] - box[0] for box, _source, _band in digits)
        tallest = max(bottom - top for top, bottom in row_bands)
        pad = max(2, round(max(widest, tallest) * 0.06))
        cell_w, cell_h = widest + 2 * pad, tallest + 2 * pad
        boxes, sources = [], []
        for box, source, band in digits:
            centre_x = (box[0] + box[2]) // 2
            centre_y = (row_bands[band][0] + row_bands[band][1]) // 2
            left, top = centre_x - cell_w // 2, centre_y - cell_h // 2
            boxes.append((left, top, left + cell_w, top + cell_h))
            sources.append(source)
        return _Plan(
            layout, tuple(boxes),
            f"Layout: {_LAYOUT_WORDS[layout]}, found from the gaps between the digits "
            f"(each digit is centred in a {cell_w}x{cell_h} cell).",
            sources=tuple(sources),
        ), ""
    return None, why


def _crop_cell(image: Image.Image, plan: _Plan, digit: int) -> Image.Image:
    box = plan.boxes[digit]
    if not plan.sources:
        return image.crop(box)
    cell = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
    source = plan.sources[digit]
    left, top = max(source[0], box[0]), max(source[1], box[1])
    right, bottom = min(source[2], box[2]), min(source[3], box[3])
    if right > left and bottom > top:
        cell.paste(image.crop((left, top, right, bottom)), (left - box[0], top - box[1]))
    return cell


def _suggest_size(width: int, height: int, columns: int, rows: int) -> tuple[int, int]:
    return max(columns, round(width / columns) * columns), max(rows, round(height / rows) * rows)


def _size_table(cell: int = 64) -> str:
    return (f"With {cell}x{cell} cells: one row {cell * 10}x{cell}, one column {cell}x{cell * 10}, "
            f"five columns by two rows {cell * 5}x{cell * 2}, two columns by five rows {cell * 2}x{cell * 5}.")


def _shape_summary(ink: Image.Image) -> str:
    """How many separate shapes sit in each row, for refusal messages."""

    if ink.getbbox() is None:
        return "The sheet has no visible pixels at all."
    _x, y_profile = ink.getprojection()
    bands = _runs(y_profile)
    counts = []
    for top, bottom in bands[:10]:
        x_profile, _y = ink.crop((0, top, ink.width, bottom)).getprojection()
        counts.append(len(_runs(x_profile)))
    if len(bands) == 1:
        return f"I can see {counts[0]} separate shape{'s' if counts[0] != 1 else ''} in one row."
    more = ", and more" if len(bands) > 10 else ""
    return f"I can see {len(bands)} rows of shapes, with {', '.join(str(c) for c in counts)} shapes{more}."


def _rounded_note(width: int, height: int, layout: str) -> str:
    columns, rows = _GRIDS[layout]
    return (f"Layout: {_LAYOUT_WORDS[layout]}. The {width}x{height} sheet does not divide into equal cells, "
            f"so the cells are about {width / columns:.1f}x{height / rows:.1f}; every cut falls between two digits.")


def _candidates(image: Image.Image, masks: tuple[Image.Image, Image.Image]) -> list[_Plan]:
    """Plans for every layout the digits themselves support, best first.

    Equal cells (exact or rounded) whose every cut falls between digits come first; only when
    there are none are the digits' own positions used.
    """

    ink, solid = masks
    width, height = image.size
    if ink.getbbox() is None:
        return []
    clean: list[_Plan] = []
    for key in _PRIORITY:
        columns, rows = _GRIDS[key]
        if width < columns or height < rows:
            continue
        xs, ys = _cut_positions(width, columns), _cut_positions(height, rows)
        boxes = _grid_boxes(xs, ys, columns, rows)
        if _straddling_cuts(solid, xs, ys, columns, rows) or _empty_cells(ink, boxes):
            continue
        if width % columns == 0 and height % rows == 0:
            note = (f"Layout: {_LAYOUT_WORDS[key]}, {width // columns}x{height // rows} cells; "
                    "every cut falls between two digits.")
        else:
            note = _rounded_note(width, height, key)
        clean.append(_Plan(key, boxes, note))
    if clean:
        return clean
    return [plan for plan in (_group_plan(masks, key)[0] for key in _PRIORITY) if plan is not None]


def _plan_explicit(image: Image.Image, masks: tuple[Image.Image, Image.Image], layout: str, *, auto: bool = False) -> _Plan:
    ink, solid = masks
    columns, rows = _GRIDS[layout]
    width, height = image.size
    has_ink = ink.getbbox() is not None
    if width % columns == 0 and height % rows == 0:
        xs = [width // columns * i for i in range(columns + 1)]
        ys = [height // rows * j for j in range(rows + 1)]
        crossings = _straddling_cuts(solid, xs, ys, columns, rows) if has_ink else []
        total_cuts = (columns - 1) * rows + columns * (rows - 1)
        if crossings and len(crossings) * 2 >= total_cuts:
            # Most cut lines slice through digits: the chosen layout is wrong for this sheet. When the digits
            # clearly sit in another layout, say so instead of importing slivers.
            better = [plan for plan in _candidates(image, masks) if plan.layout != layout]
            if better and auto:
                return better[0]
            if better:
                label = dict((key, text) for text, key in SHEET_LAYOUTS)[better[0].layout]
                raise ValidationError(
                    f"You chose {_LAYOUT_WORDS[layout]}, but the digits in this {width}x{height} sheet sit in "
                    f"{_LAYOUT_WORDS[better[0].layout]}, and the cell borders of the layout you chose would slice "
                    f"through digits ({crossings[0]}). Choose \"{label}\" or \"Detect layout from image\" and try again."
                )
        return _Plan(
            layout, _grid_boxes(xs, ys, columns, rows),
            f"Layout: {_LAYOUT_WORDS[layout]}, {width // columns}x{height // rows} cells.",
            warnings=tuple(f"Check the layout: {c}." for c in crossings[:3]),
        )
    # Not divisible: only go on when the digits themselves show where to cut.
    reasons: list[str] = []
    if has_ink:
        xs, ys = _cut_positions(width, columns), _cut_positions(height, rows)
        boxes = _grid_boxes(xs, ys, columns, rows)
        crossings = _straddling_cuts(solid, xs, ys, columns, rows)
        empty = _empty_cells(ink, boxes)
        if not crossings and not empty:
            return _Plan(layout, boxes, _rounded_note(width, height, layout))
        reasons.append(crossings[0] if crossings else
                       f"the cell{'s' if len(empty) != 1 else ''} for digit{'s' if len(empty) != 1 else ''} "
                       f"{', '.join(str(d) for d in empty)} would be empty")
        plan, why = _group_plan(masks, layout)
        if plan is not None:
            return plan
        if why:
            reasons.append(why)
    new_w, new_h = _suggest_size(width, height, columns, rows)
    message = (
        f"The {width}x{height} sheet in {layout} layout cannot have equal cells "
        f"({width / columns:g}x{height / rows:g} pixels per cell): "
        f"width must be divisible by {columns} and height by {rows}. "
    )
    if reasons:
        message += f"Cutting it anyway would go wrong: {'; '.join(reasons)}. "
    message += (f"Resize the canvas to {new_w}x{new_h} without moving the digits, leave a clear transparent gap "
                "between the digits so they can be cut apart, or choose the layout the digits are really in.")
    raise ValidationError(message)


def _plan_auto(image: Image.Image, masks: tuple[Image.Image, Image.Image]) -> _Plan:
    ink, _solid = masks
    width, height = image.size
    # 1. The documented templates: equal square cells that divide the sheet exactly.
    square = [key for key in _PRIORITY
              if width % _GRIDS[key][0] == 0 and height % _GRIDS[key][1] == 0
              and width // _GRIDS[key][0] == height // _GRIDS[key][1]]
    if square:
        return _plan_explicit(image, masks, square[0], auto=True)
    if ink.getbbox() is not None:
        # 2. Equal cells at rounded cut positions whose every cut falls between digits, else 3. the digits' own positions.
        found = _candidates(image, masks)
        if found:
            first = found[0]
            alternatives = tuple(f"The sheet would also fit {_LAYOUT_WORDS[plan.layout]}; if the digits look wrong in "
                                 "the preview, choose the layout yourself." for plan in found[1:2])
            return _Plan(first.layout, first.boxes, first.note, sources=first.sources,
                         warnings=first.warnings + alternatives)
    elif max(image.size) >= 5 * min(image.size):
        # A blank strip keeps the original rule, so a wrong size is still reported precisely.
        return _plan_explicit(image, masks, "horizontal" if width >= height else "vertical")
    raise ValidationError(
        f"Cannot infer the layout of a {width}x{height} sheet. "
        "Choose its row, column or grid layout explicitly. "
        f"{_shape_summary(ink)} "
        "A digit sheet needs the ten digits in order (0 to 9), with a clear transparent gap between them, as one row, "
        "one column, five columns by two rows (0-4 above 5-9), or two columns by five rows. "
        f"{_size_table()} "
        "Remove labels, guides and borders, and add a transparent gap of a few pixels where digits touch."
    )


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
    image = _read_sheet(source)
    alpha = image.getchannel("A")
    masks = (alpha.point(_INK_LUT), alpha.point(_SOLID_LUT))
    plan = _plan_auto(image, masks) if orientation == "auto" else _plan_explicit(image, masks, orientation)
    chosen = plan.layout
    if any(min(box[2] - box[0], box[3] - box[1]) < 1 for box in plan.boxes):
        raise ValidationError("The digit sheet is too small to contain ten cells.")

    outputs: list[DigitSheetPng] = []
    for digit, target in enumerate(targets):
        cell = _crop_cell(image, plan, digit)
        cell_width, cell_height = cell.size
        width = int(getattr(target, "width"))
        height = int(getattr(target, "height"))
        notes = list(plan.warnings)
        if cell.size != (width, height):
            notes.append(
                f"{chosen} layout: {cell_width}x{cell_height} cell will be resized to "
                f"{width}x{height} for digit {digit}, including its padding."
            )
            if cell_width * height != cell_height * width:
                notes.append("As authored will stretch different cell and slot shapes; Match retail size preserves the glyph's aspect.")
            if cell_width < width or cell_height < height:
                notes.append("Enlarging the cell cannot restore missing edge detail.")
        cell_alpha = cell.getchannel("A")
        visible = cell_alpha.point(_INK_LUT).getbbox()
        if visible is None:
            notes.append(f"Digit {digit} is empty in the sheet (nothing visible in its cell). "
                         "It would be blank in the game. Check the layout and the order of the digits.")
        else:
            if (visible[0] == 0 or visible[1] == 0
                    or visible[2] == cell_width or visible[3] == cell_height):
                notes.append(f"Digit {digit} touches a cell edge; check for clipping, gaps or a background.")
            if cell_alpha.getextrema()[0] == 255:
                notes.append(f"Digit {digit} has no transparent pixels at all, so it would become a solid block. "
                             "Export the sheet as a PNG with a transparent background.")
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
            layout_note=plan.note,
        ))
    return tuple(outputs)


__all__ = ["DigitSheetPng", "INK_ALPHA", "MAX_SHEET_BYTES", "SHEET_LAYOUTS", "SHEET_LAYOUT_CHOICES", "SHEET_HELP", "split_digit_sheet"]
