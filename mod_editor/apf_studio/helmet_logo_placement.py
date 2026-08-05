"""Palette-safe placement for APF's semantic 512x512 helmet-crest mask.

The full-shell writer consumes one semantic, pre-guard RGBA canvas.  This
module lets the product position imported region-mask art on that canvas
without inventing colours: every resize and affine transform uses nearest
neighbour, and every output colour must come from the input (apart from the
transparent-black canvas background).

Coordinates deliberately describe the 512x512 texture, not screen pixels.
That keeps the transform deterministic in projects, tests, and the Qt dialog.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import stat

from mod_editor.core.texture_master import AuthoringTransform

from .helmet_logo_regions import clear_fully_transparent_rgb


CANVAS_WIDTH = 512
CANVAS_HEIGHT = 512
RGBA_LENGTH = CANVAS_WIDTH * CANVAS_HEIGHT * 4
TRANSPARENT = b"\0\0\0\0"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_PIXELS = 64 * 1024 * 1024

# This is the proved front/crown-to-rear design envelope.  It spans the full U
# domain while leaving enough vertical background for rotation and an obvious
# helmet-shaped editing guide.
AUTO_TARGET_BOUNDS = (0, 122, 511, 389)


class HelmetLogoPlacementError(ValueError):
    """The imported mask or requested transform is unsafe to stage."""


@dataclass(frozen=True)
class ImportedMask:
    rgba: bytes
    source_width: int
    source_height: int
    action: str


@dataclass(frozen=True)
class Placement:
    center_x: float
    center_y: float
    scale_x: float
    scale_y: float
    rotation_degrees: float = 0.0


@dataclass(frozen=True)
class PlacementResult:
    rgba: bytes
    active_bbox: tuple[int, int, int, int]
    active_texels: int
    transformed_bounds: tuple[float, float, float, float]
    palette_values_preserved: bool


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HelmetLogoPlacementError(message)


def _active_bbox(rgba: bytes) -> tuple[int, int, int, int]:
    _require(len(rgba) == RGBA_LENGTH, "helmet-logo RGBA must be exactly 512x512")
    xs: list[int] = []
    ys: list[int] = []
    for y_value in range(CANVAS_HEIGHT):
        row = y_value * CANVAS_WIDTH * 4
        for x_value in range(CANVAS_WIDTH):
            offset = row + x_value * 4
            if rgba[offset] or rgba[offset + 1] or rgba[offset + 2]:
                xs.append(x_value)
                ys.append(y_value)
    _require(
        bool(xs),
        "The helmet-logo mask is empty. Add a visible red or green region.",
    )
    return min(xs), min(ys), max(xs), max(ys)


def active_bbox(rgba: bytes) -> tuple[int, int, int, int]:
    """Return inclusive bounds of nonblack RGB mask texels."""

    return _active_bbox(bytes(rgba))


def _palette(rgba: bytes) -> set[bytes]:
    return {rgba[offset : offset + 4] for offset in range(0, len(rgba), 4)}


def import_mask_nearest(path: Path) -> ImportedMask:
    """Load any normal image and contain it on 512x512 with nearest sampling."""

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow ships with product
        raise HelmetLogoPlacementError(
            "Pillow is required to place a helmet-logo image."
        ) from exc

    source = Path(path).expanduser()
    try:
        info = source.lstat()
    except OSError as exc:
        raise HelmetLogoPlacementError(
            f"Cannot read {source.name}: {exc.strerror or exc}"
        ) from exc
    _require(
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"{source.name} must be a regular, non-symlink file",
    )
    _require(
        info.st_size <= MAX_SOURCE_BYTES,
        f"{source.name} is larger than {MAX_SOURCE_BYTES // (1024 * 1024)} MiB",
    )
    Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS
    try:
        with Image.open(source) as opened:
            opened.load()
            image = opened.convert("RGBA")
    except Exception as exc:  # noqa: BLE001 - Pillow raises format-specific errors
        raise HelmetLogoPlacementError(
            f"{source.name} could not be read as an image: {exc}"
        ) from exc
    source_width, source_height = image.size
    _require(source_width > 0 and source_height > 0, "The image has no pixels.")

    # PNGs exported by ordinary art tools may retain arbitrary RGB underneath
    # fully transparent pixels.  APF carrier bounds are driven by RGB mask
    # weights, so those invisible colours would otherwise turn a small logo
    # into a full-canvas hull.  Clear them before any contain/placement math.
    cleaned = clear_fully_transparent_rgb(image.tobytes())
    image = Image.frombytes("RGBA", image.size, cleaned.rgba)

    if image.size == (CANVAS_WIDTH, CANVAS_HEIGHT):
        rgba = image.tobytes()
        _active_bbox(rgba)
        return ImportedMask(rgba, source_width, source_height, "exact")

    scale = min(CANVAS_WIDTH / source_width, CANVAS_HEIGHT / source_height)
    inner_width = max(1, min(CANVAS_WIDTH, int(round(source_width * scale))))
    inner_height = max(1, min(CANVAS_HEIGHT, int(round(source_height * scale))))
    nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    resized = image.resize((inner_width, inner_height), nearest)
    canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    canvas.paste(
        resized,
        ((CANVAS_WIDTH - inner_width) // 2, (CANVAS_HEIGHT - inner_height) // 2),
    )
    rgba = canvas.tobytes()
    _active_bbox(rgba)
    _require(
        _palette(rgba) <= _palette(image.tobytes()) | {TRANSPARENT},
        "Nearest-neighbour import introduced a new palette value.",
    )
    return ImportedMask(rgba, source_width, source_height, "nearest-contained")


def reset_placement(rgba: bytes) -> Placement:
    """Return the identity placement for an already-normalized canvas."""

    x_min, y_min, x_max, y_max = _active_bbox(bytes(rgba))
    return Placement(
        center_x=(x_min + x_max + 1) / 2.0,
        center_y=(y_min + y_max + 1) / 2.0,
        scale_x=1.0,
        scale_y=1.0,
        rotation_degrees=0.0,
    )


def auto_fit_placement(
    rgba: bytes,
    *,
    target_bounds: tuple[int, int, int, int] = AUTO_TARGET_BOUNDS,
) -> Placement:
    """Stretch the visible mask to the proved front/crown-to-rear envelope."""

    x_min, y_min, x_max, y_max = _active_bbox(bytes(rgba))
    target_x_min, target_y_min, target_x_max, target_y_max = target_bounds
    _require(
        0 <= target_x_min < target_x_max < CANVAS_WIDTH
        and 0 <= target_y_min < target_y_max < CANVAS_HEIGHT,
        "Auto-fit target bounds must be a nonempty rectangle inside 512x512.",
    )
    source_width = x_max - x_min
    source_height = y_max - y_min
    _require(
        source_width > 0 and source_height > 0,
        "The visible helmet-logo mask must span at least two pixels on each axis.",
    )
    return Placement(
        center_x=(target_x_min + target_x_max + 1) / 2.0,
        center_y=(target_y_min + target_y_max + 1) / 2.0,
        scale_x=(target_x_max - target_x_min + 1) / (source_width + 1),
        scale_y=(target_y_max - target_y_min + 1) / (source_height + 1),
        rotation_degrees=0.0,
    )


def compose_contained_master_transform(
    source_width: int,
    source_height: int,
    normalized_rgba: bytes,
    placement: Placement,
    *,
    resample: str,
) -> AuthoringTransform:
    """Compose original-image contain geometry with semantic-mask placement.

    The placement dialog operates on a contained 512x512 semantic canvas and
    rotates/scales around that mask's *active* bounding-box centre. A raw logo
    may be nonsquare and its active art may be off-centre, so copying the five
    dialog values directly onto the raw image is geometrically wrong. This
    function folds the contain rectangle and active-centre offset into one
    original-image affine transform for the high-resolution master preview.
    """

    _require(
        type(source_width) is int and type(source_height) is int
        and source_width > 0 and source_height > 0,
        "Full-resolution master dimensions must be positive integers.",
    )
    x_min, y_min, x_max, y_max = _active_bbox(bytes(normalized_rgba))
    # Match image_fit(mode="contain") and import_mask_nearest exactly: scale,
    # round each inner dimension, clamp, then centre with integer padding.
    contain_scale = min(
        CANVAS_WIDTH / source_width, CANVAS_HEIGHT / source_height
    )
    inner_width = max(
        1, min(CANVAS_WIDTH, int(round(source_width * contain_scale)))
    )
    inner_height = max(
        1, min(CANVAS_HEIGHT, int(round(source_height * contain_scale)))
    )
    contained_center_x = (CANVAS_WIDTH - inner_width) // 2 + inner_width / 2.0
    contained_center_y = (CANVAS_HEIGHT - inner_height) // 2 + inner_height / 2.0
    active_center_x = (x_min + x_max + 1) / 2.0
    active_center_y = (y_min + y_max + 1) / 2.0
    local_x = (contained_center_x - active_center_x) * placement.scale_x
    local_y = (contained_center_y - active_center_y) * placement.scale_y
    angle = math.radians(placement.rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    result = AuthoringTransform(
        center_x=placement.center_x + cosine * local_x - sine * local_y,
        center_y=placement.center_y + sine * local_x + cosine * local_y,
        width=inner_width * placement.scale_x,
        height=inner_height * placement.scale_y,
        rotation_degrees=placement.rotation_degrees,
        resample=resample,
    )
    result.validate(CANVAS_WIDTH, CANVAS_HEIGHT)
    return result


def transformed_bounds(
    rgba: bytes, placement: Placement
) -> tuple[float, float, float, float]:
    """Return the forward-transformed bounds of the active source rectangle."""

    x_min, y_min, x_max, y_max = _active_bbox(bytes(rgba))
    _require(
        math.isfinite(placement.center_x)
        and math.isfinite(placement.center_y)
        and math.isfinite(placement.scale_x)
        and math.isfinite(placement.scale_y)
        and math.isfinite(placement.rotation_degrees),
        "Placement values must be finite.",
    )
    _require(
        0.01 <= placement.scale_x <= 64.0
        and 0.01 <= placement.scale_y <= 64.0,
        "Width and height scale must each be between 1% and 6400%.",
    )
    source_center_x = (x_min + x_max + 1) / 2.0
    source_center_y = (y_min + y_max + 1) / 2.0
    angle = math.radians(placement.rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    points: list[tuple[float, float]] = []
    for source_x, source_y in (
        (x_min, y_min),
        (x_max + 1, y_min),
        (x_max + 1, y_max + 1),
        (x_min, y_max + 1),
    ):
        local_x = (source_x - source_center_x) * placement.scale_x
        local_y = (source_y - source_center_y) * placement.scale_y
        points.append(
            (
                placement.center_x + cosine * local_x - sine * local_y,
                placement.center_y + sine * local_x + cosine * local_y,
            )
        )
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def validate_placement(rgba: bytes, placement: Placement) -> None:
    """Fail closed when any visible source corner would leave the canvas."""

    left, top, right, bottom = transformed_bounds(bytes(rgba), placement)
    _require(
        left >= 0.0 and top >= 0.0 and right <= CANVAS_WIDTH and bottom <= CANVAS_HEIGHT,
        "The placement clips visible art outside the 512x512 canvas. Move it inward, "
        "reduce width/height, or reduce rotation before staging.",
    )


def render_placement(
    rgba: bytes,
    placement: Placement,
    *,
    allow_clipping: bool = False,
) -> PlacementResult:
    """Render one exact palette-safe 512x512 RGBA placement."""

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow ships with product
        raise HelmetLogoPlacementError(
            "Pillow is required to render a helmet-logo placement."
        ) from exc

    source = bytes(rgba)
    x_min, y_min, x_max, y_max = _active_bbox(source)
    bounds = transformed_bounds(source, placement)
    if not allow_clipping:
        validate_placement(source, placement)

    source_center_x = (x_min + x_max + 1) / 2.0
    source_center_y = (y_min + y_max + 1) / 2.0
    angle = math.radians(placement.rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    a_value = cosine / placement.scale_x
    b_value = sine / placement.scale_x
    d_value = -sine / placement.scale_y
    e_value = cosine / placement.scale_y
    c_value = (
        source_center_x
        - a_value * placement.center_x
        - b_value * placement.center_y
    )
    f_value = (
        source_center_y
        - d_value * placement.center_x
        - e_value * placement.center_y
    )
    source_image = Image.frombytes("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), source)
    affine = getattr(getattr(Image, "Transform", Image), "AFFINE")
    nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    rendered = source_image.transform(
        (CANVAS_WIDTH, CANVAS_HEIGHT),
        affine,
        (a_value, b_value, c_value, d_value, e_value, f_value),
        resample=nearest,
        fillcolor=(0, 0, 0, 0),
    ).tobytes()
    output_bbox = _active_bbox(rendered)
    active_count = sum(
        1
        for offset in range(0, len(rendered), 4)
        if rendered[offset] or rendered[offset + 1] or rendered[offset + 2]
    )
    palette_safe = _palette(rendered) <= _palette(source) | {TRANSPARENT}
    _require(palette_safe, "Nearest-neighbour placement introduced a palette value.")
    return PlacementResult(
        rgba=rendered,
        active_bbox=output_bbox,
        active_texels=active_count,
        transformed_bounds=bounds,
        palette_values_preserved=True,
    )


__all__ = [
    "AUTO_TARGET_BOUNDS",
    "CANVAS_HEIGHT",
    "CANVAS_WIDTH",
    "HelmetLogoPlacementError",
    "ImportedMask",
    "Placement",
    "PlacementResult",
    "active_bbox",
    "auto_fit_placement",
    "compose_contained_master_transform",
    "import_mask_nearest",
    "render_placement",
    "reset_placement",
    "transformed_bounds",
    "validate_placement",
]
