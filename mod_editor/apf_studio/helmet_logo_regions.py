"""Deterministic normal-logo to APF helmet region-mask conversion.

APF's crest texture is not literal painted RGBA.  Its RGB components are
palette weights and its Xenos ``4_4_4_4`` transport stores exact four-bit
channel values.  This module keeps that distinction explicit:

* advanced region masks are validated as weight maps; and
* ordinary artwork is projected onto an explicitly supplied shell/detail
  colour triangle before it reaches the placement canvas.

The automatic converter intentionally uses only the proved red and green
detail regions.  The caller supplies their rendered colours, so this code does
not guess a team's palette or claim that arbitrary source RGB can survive the
game's palette shader literally.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from functools import lru_cache
import math
from typing import Iterable


CANVAS_WIDTH = 512
CANVAS_HEIGHT = 512
RGBA_LENGTH = CANVAS_WIDTH * CANVAS_HEIGHT * 4
XENOS_CHANNEL_STEP = 17
XENOS_WEIGHT_SCALE = 15
PROVED_MASK_ALPHA = 8 * XENOS_CHANNEL_STEP
# Retail bounded crests transport the constant 8/15 (0x88) alpha sentinel,
# which is correct for the retail side-decal lane.  The full-shell lane draws
# the whole helmet through the crest material, where a translucent shell body
# renders see-through and flat in game, so full-shell designs must carry an
# opaque shell body instead.
FULL_SHELL_OPAQUE_ALPHA = XENOS_WEIGHT_SCALE * XENOS_CHANNEL_STEP
NORMAL_LOGO_IMPORT_MODE = "normal_logo"
REGION_MASK_IMPORT_MODE = "apf_region_mask"

Rgb = tuple[int, int, int]


class HelmetLogoRegionError(ValueError):
    """Artwork cannot be represented by the proved APF region-mask contract."""


@dataclass(frozen=True)
class HiddenRgbCleanup:
    rgba: bytes
    cleared_texels: int


@dataclass(frozen=True)
class TwoRegionPalette:
    """Rendered colours assigned to shell, red mask, and green mask.

    ``red_region`` and ``green_region`` name texture channels, not the visible
    colours a user must choose.  For example, the proved Eagles mapping uses
    silver for ``red_region`` and white for ``green_region``.
    """

    shell: Rgb
    red_region: Rgb
    green_region: Rgb

    def __post_init__(self) -> None:
        for label, value in (
            ("shell", self.shell),
            ("red region", self.red_region),
            ("green region", self.green_region),
        ):
            _validate_rgb(value, label)
        red_axis = _subtract(self.red_region, self.shell)
        green_axis = _subtract(self.green_region, self.shell)
        determinant = (
            _dot(red_axis, red_axis) * _dot(green_axis, green_axis)
            - _dot(red_axis, green_axis) ** 2
        )
        _require(
            determinant > 1.0e-9,
            "Shell, red-region, and green-region colours must form a non-collinear "
            "colour triangle.",
        )


@dataclass(frozen=True)
class RegionMaskValidation:
    active_bbox: tuple[int, int, int, int]
    active_texels: int
    channel_levels: dict[str, tuple[int, ...]]
    alpha_levels: tuple[int, ...]


@dataclass(frozen=True)
class NormalLogoConversion:
    mask_rgba: bytes
    material_preview_rgba: bytes
    validation: RegionMaskValidation
    cleared_hidden_rgb_texels: int
    maximum_rgb_error: int
    mean_squared_rgb_error: float
    mapping: str
    palette: TwoRegionPalette


@dataclass(frozen=True)
class PaletteSuggestion:
    palette: TwoRegionPalette | None
    explanation: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HelmetLogoRegionError(message)


def _validate_rgb(value: Iterable[int], label: str) -> Rgb:
    values = tuple(value)
    _require(
        len(values) == 3
        and all(type(channel) is int and 0 <= channel <= 255 for channel in values),
        f"{label} must contain three integer RGB values from 0 through 255.",
    )
    return values  # type: ignore[return-value]


def _require_canvas(rgba: bytes | bytearray | memoryview) -> bytes:
    try:
        payload = bytes(rgba)
    except (TypeError, ValueError) as exc:
        raise HelmetLogoRegionError(
            "Helmet-logo pixels must be a bytes-like 512x512 RGBA payload."
        ) from exc
    _require(
        len(payload) == RGBA_LENGTH,
        f"Helmet-logo RGBA has {len(payload)} bytes; expected {RGBA_LENGTH} "
        "for 512x512.",
    )
    return payload


def clear_fully_transparent_rgb(
    rgba: bytes | bytearray | memoryview,
) -> HiddenRgbCleanup:
    """Clear hidden RGB under alpha zero before mask bounds are measured."""

    try:
        payload = bytes(rgba)
    except (TypeError, ValueError) as exc:
        raise HelmetLogoRegionError("RGBA pixels must be bytes-like.") from exc
    _require(
        bool(payload) and len(payload) % 4 == 0,
        "RGBA pixels must contain a nonempty whole number of texels.",
    )
    output = bytearray(payload)
    cleared = 0
    for offset in range(0, len(output), 4):
        if output[offset + 3] == 0 and (
            output[offset] or output[offset + 1] or output[offset + 2]
        ):
            output[offset : offset + 3] = b"\0\0\0"
            cleared += 1
    return HiddenRgbCleanup(bytes(output), cleared)


def validate_region_mask_rgba(
    rgba: bytes | bytearray | memoryview,
) -> RegionMaskValidation:
    """Validate an advanced APF mask without silently treating it as artwork.

    The red/green weights and alpha must already lie on the exact Xenos nibble
    lattice.  The live full-shell carrier proves two detail channels only, so
    blue must be zero and red plus green share one coverage unit.
    """

    payload = _require_canvas(rgba)
    xs: list[int] = []
    ys: list[int] = []
    levels = {"red": set(), "green": set(), "blue": set()}
    alpha_levels: set[int] = set()
    for pixel, offset in enumerate(range(0, len(payload), 4)):
        red, green, blue, alpha = payload[offset : offset + 4]
        if any(value % XENOS_CHANNEL_STEP for value in (red, green, blue, alpha)):
            raise HelmetLogoRegionError(
                f"Region-mask texel {pixel} is not exact Xenos 4-bit RGBA "
                "(every component must be a multiple of 17)."
            )
        if blue:
            raise HelmetLogoRegionError(
                f"Region-mask texel {pixel} uses blue; the proved full-shell "
                "profile supports red and green detail weights only."
            )
        if red + green > 255:
            raise HelmetLogoRegionError(
                f"Region-mask texel {pixel} exceeds one red/green coverage unit."
            )
        if alpha == 0 and (red or green or blue):
            raise HelmetLogoRegionError(
                f"Region-mask texel {pixel} hides nonzero RGB under alpha zero."
            )
        levels["red"].add(red)
        levels["green"].add(green)
        levels["blue"].add(blue)
        alpha_levels.add(alpha)
        if red or green or blue:
            xs.append(pixel % CANVAS_WIDTH)
            ys.append(pixel // CANVAS_WIDTH)
    _require(
        bool(xs),
        "The APF full-shell region mask is empty; add a red or green weighted region.",
    )
    return RegionMaskValidation(
        active_bbox=(min(xs), min(ys), max(xs), max(ys)),
        active_texels=len(xs),
        channel_levels={name: tuple(sorted(values)) for name, values in levels.items()},
        alpha_levels=tuple(sorted(alpha_levels)),
    )


def opaque_shell_body_rgba(
    rgba: bytes | bytearray | memoryview,
    *,
    opaque_active_texels: bool = True,
) -> bytes:
    """Rewrite a full-shell design's alpha to the opaque transport value.

    Zero-RGB texels are the routed shell body and always become alpha 255;
    any translucency there renders the whole helmet see-through in game.
    With ``opaque_active_texels`` (the full-shell default) the weighted ink
    and lattice AA edge texels also become 255 so the crest renders solid;
    the RGB red/green weights are untouched, so the palette shader equation
    and the 17-step lattice contract are preserved exactly.
    """

    payload = bytearray(_require_canvas(rgba))
    for offset in range(0, len(payload), 4):
        if payload[offset] or payload[offset + 1] or payload[offset + 2]:
            if opaque_active_texels:
                payload[offset + 3] = FULL_SHELL_OPAQUE_ALPHA
        else:
            payload[offset + 3] = FULL_SHELL_OPAQUE_ALPHA
    return bytes(payload)


def validate_full_shell_region_mask_rgba(
    rgba: bytes | bytearray | memoryview,
) -> RegionMaskValidation:
    """Validate a full-shell mask plus the opaque shell-body contract.

    Identical Xenos 4-bit lattice/blue/coverage checks to
    :func:`validate_region_mask_rgba`, and additionally every zero-RGB
    shell-body texel must carry alpha 255.  Weighted ink and AA edge texels
    keep full per-texel 4-bit alpha fidelity on the lattice.
    """

    payload = _require_canvas(rgba)
    for pixel, offset in enumerate(range(0, len(payload), 4)):
        red, green, blue, alpha = payload[offset : offset + 4]
        if not (red or green or blue) and alpha != FULL_SHELL_OPAQUE_ALPHA:
            raise HelmetLogoRegionError(
                f"Full-shell texel {pixel} is a shell-body background texel and "
                "must be opaque (alpha 255); the retail bounded-crest 8/15 "
                "transport sentinel renders the routed shell semi-transparent."
            )
    return validate_region_mask_rgba(payload)


def suggest_two_region_palette(
    rgba: bytes | bytearray | memoryview,
) -> PaletteSuggestion:
    """Suggest three source-art colours only when they form a stable triangle.

    This never identifies a game palette.  It looks only at visible pixels in
    the imported artwork, groups nearby colours, and chooses a well-separated
    three-colour triangle from the most populated groups.  Sparse or
    effectively one/two-colour art returns no suggestion so the UI can require
    explicit values instead of inventing a helmet shell colour.
    """

    source = clear_fully_transparent_rgb(_require_canvas(rgba)).rgba
    buckets: dict[tuple[int, int, int], list[int]] = defaultdict(
        lambda: [0, 0, 0, 0]
    )
    for offset in range(0, len(source), 4):
        red, green, blue, alpha = source[offset : offset + 4]
        if alpha == 0:
            continue
        key = (red // 32, green // 32, blue // 32)
        row = buckets[key]
        row[0] += alpha
        row[1] += red * alpha
        row[2] += green * alpha
        row[3] += blue * alpha
    ranked = sorted(
        buckets.values(),
        key=lambda row: (-row[0], row[1], row[2], row[3]),
    )[:18]
    colours: list[tuple[Rgb, int]] = [
        (
            tuple((row[channel] + row[0] // 2) // row[0] for channel in (1, 2, 3)),
            row[0],
        )
        for row in ranked
        if row[0]
    ]  # type: ignore[list-item]
    if len(colours) < 3:
        return PaletteSuggestion(
            None,
            "The artwork does not contain three distinct visible colour groups. "
            "Enter the helmet shell and two rendered detail colours manually.",
        )

    candidates: list[tuple[float, int, int, int]] = []
    for first in range(len(colours) - 2):
        for second in range(first + 1, len(colours) - 1):
            for third in range(second + 1, len(colours)):
                origin = colours[first][0]
                first_axis = _subtract(colours[second][0], origin)
                second_axis = _subtract(colours[third][0], origin)
                determinant = (
                    _dot(first_axis, first_axis) * _dot(second_axis, second_axis)
                    - _dot(first_axis, second_axis) ** 2
                )
                # Population weighting prevents a one-pixel fringe colour from
                # defeating the dominant logo colours solely by being distant.
                population = min(
                    colours[first][1], colours[second][1], colours[third][1]
                )
                candidates.append(
                    (determinant * math.log2(2 + population), first, second, third)
                )
    score, first, second, third = max(candidates)
    if score <= 1.0e6:
        return PaletteSuggestion(
            None,
            "The visible artwork colours are too close to one line for a safe "
            "three-anchor suggestion. Enter the mapping manually.",
        )
    selected = [colours[index][0] for index in (first, second, third)]
    selected.sort(key=lambda colour: (sum(colour), colour))
    try:
        palette = TwoRegionPalette(
            shell=selected[0],
            red_region=selected[1],
            green_region=selected[2],
        )
    except HelmetLogoRegionError:
        return PaletteSuggestion(
            None,
            "No stable source-art colour triangle was found. Enter the shell and "
            "detail mapping manually.",
        )
    return PaletteSuggestion(
        palette,
        "Suggested from three separated colour groups in this artwork only. "
        "Confirm or edit them: this does not read the team's game palette.",
    )


def _dot(left: Rgb | tuple[float, float, float],
         right: Rgb | tuple[float, float, float]) -> float:
    return sum(first * second for first, second in zip(left, right, strict=True))


def _subtract(
    left: Iterable[int | float], right: Iterable[int | float]
) -> tuple[float, float, float]:
    result = tuple(
        float(first) - float(second)
        for first, second in zip(left, right, strict=True)
    )
    _require(len(result) == 3, "RGB vectors must contain exactly three channels.")
    return result  # type: ignore[return-value]


def _closest_triangle_weights(rgb: Rgb, palette: TwoRegionPalette) -> tuple[float, float]:
    """Closest red/green barycentric weights on one rendered colour triangle."""

    pixel = tuple(float(value) for value in rgb)
    shell = tuple(float(value) for value in palette.shell)
    red_colour = tuple(float(value) for value in palette.red_region)
    green_colour = tuple(float(value) for value in palette.green_region)
    red_axis = _subtract(red_colour, shell)
    green_axis = _subtract(green_colour, shell)
    relative = _subtract(pixel, shell)
    rr = _dot(red_axis, red_axis)
    rg = _dot(red_axis, green_axis)
    gg = _dot(green_axis, green_axis)
    pr = _dot(relative, red_axis)
    pg = _dot(relative, green_axis)
    determinant = rr * gg - rg * rg
    _require(determinant > 1.0e-9, "Region palette colour triangle is collinear.")
    red = (gg * pr - rg * pg) / determinant
    green = (rr * pg - rg * pr) / determinant
    if red >= 0.0 and green >= 0.0 and red + green <= 1.0:
        return red, green

    vertices = (
        (shell, (0.0, 0.0)),
        (red_colour, (1.0, 0.0)),
        (green_colour, (0.0, 1.0)),
    )
    candidates: list[tuple[float, int, float, float]] = []
    for edge_index, (first_index, second_index) in enumerate(((0, 1), (0, 2), (1, 2))):
        first_rgb, first_weights = vertices[first_index]
        second_rgb, second_weights = vertices[second_index]
        axis = _subtract(second_rgb, first_rgb)
        axis_length = _dot(axis, axis)
        _require(axis_length > 0.0, "Region palette contains duplicate colours.")
        offset = _subtract(pixel, first_rgb)
        factor = max(0.0, min(1.0, _dot(offset, axis) / axis_length))
        projected = tuple(
            first_rgb[channel] + factor * axis[channel] for channel in range(3)
        )
        error = sum(
            (pixel[channel] - projected[channel]) ** 2 for channel in range(3)
        )
        candidate_red = first_weights[0] + factor * (
            second_weights[0] - first_weights[0]
        )
        candidate_green = first_weights[1] + factor * (
            second_weights[1] - first_weights[1]
        )
        candidates.append((error, edge_index, candidate_red, candidate_green))
    _error, _edge, red, green = min(candidates)
    return red, green


def _quantize_weights(red: float, green: float) -> tuple[int, int]:
    _require(
        math.isfinite(red)
        and math.isfinite(green)
        and red >= -1.0e-9
        and green >= -1.0e-9
        and red + green <= 1.0 + 1.0e-9,
        "Normal-logo palette weights left the unit simplex.",
    )
    wanted_red = max(0.0, min(1.0, red)) * XENOS_WEIGHT_SCALE
    wanted_green = max(0.0, min(1.0, green)) * XENOS_WEIGHT_SCALE
    red_nibble = int(wanted_red + 0.5)
    green_nibble = int(wanted_green + 0.5)
    if red_nibble + green_nibble > XENOS_WEIGHT_SCALE:
        reduce_red_error = (red_nibble - 1 - wanted_red) ** 2 + (
            green_nibble - wanted_green
        ) ** 2
        reduce_green_error = (red_nibble - wanted_red) ** 2 + (
            green_nibble - 1 - wanted_green
        ) ** 2
        if reduce_red_error <= reduce_green_error:
            red_nibble -= 1
        else:
            green_nibble -= 1
    _require(
        0 <= red_nibble <= XENOS_WEIGHT_SCALE
        and 0 <= green_nibble <= XENOS_WEIGHT_SCALE
        and red_nibble + green_nibble <= XENOS_WEIGHT_SCALE,
        "Quantized normal-logo weights left the Xenos unit simplex.",
    )
    return red_nibble, green_nibble


def _material_pixel(
    red_nibble: int, green_nibble: int, palette: TwoRegionPalette
) -> tuple[int, int, int, int]:
    shell_nibble = XENOS_WEIGHT_SCALE - red_nibble - green_nibble
    return tuple(
        (
            palette.shell[channel] * shell_nibble
            + palette.red_region[channel] * red_nibble
            + palette.green_region[channel] * green_nibble
            + XENOS_WEIGHT_SCALE // 2
        )
        // XENOS_WEIGHT_SCALE
        for channel in range(3)
    ) + (255,)  # type: ignore[return-value]


def convert_normal_logo_to_region_mask(
    rgba: bytes | bytearray | memoryview,
    palette: TwoRegionPalette,
) -> NormalLogoConversion:
    """Map ordinary RGBA art to the proved two-detail APF weight contract.

    Source alpha is folded into the red/green weights relative to the supplied
    shell colour.  Output alpha is the proved constant 8/15 transport value,
    so transparent source pixels become inactive black mask texels instead of
    contributing hidden RGB to the carrier hull.
    """

    cleanup = clear_fully_transparent_rgb(_require_canvas(rgba))
    source = cleanup.rgba
    mask = bytearray(RGBA_LENGTH)
    preview = bytearray(RGBA_LENGTH)
    error_total = 0
    error_maximum = 0

    @lru_cache(maxsize=None)
    def convert_pixel(pixel: tuple[int, int, int, int]) -> tuple[bytes, bytes, int, int]:
        source_red, source_green, source_blue, source_alpha = pixel
        if source_alpha == 0:
            red_weight = green_weight = 0.0
        else:
            red_weight, green_weight = _closest_triangle_weights(
                (source_red, source_green, source_blue), palette
            )
            opacity = source_alpha / 255.0
            red_weight *= opacity
            green_weight *= opacity
        red_nibble, green_nibble = _quantize_weights(red_weight, green_weight)
        material = _material_pixel(red_nibble, green_nibble, palette)
        wanted = tuple(
            (
                palette.shell[channel] * (255 - source_alpha)
                + pixel[channel] * source_alpha
                + 127
            )
            // 255
            for channel in range(3)
        )
        errors = tuple(abs(material[channel] - wanted[channel]) for channel in range(3))
        squared = sum(value * value for value in errors)
        return (
            bytes(
                (
                    red_nibble * XENOS_CHANNEL_STEP,
                    green_nibble * XENOS_CHANNEL_STEP,
                    0,
                    PROVED_MASK_ALPHA,
                )
            ),
            bytes(material),
            max(errors),
            squared,
        )

    for offset in range(0, len(source), 4):
        converted, material, maximum, squared = convert_pixel(
            tuple(source[offset : offset + 4])  # type: ignore[arg-type]
        )
        mask[offset : offset + 4] = converted
        preview[offset : offset + 4] = material
        error_maximum = max(error_maximum, maximum)
        error_total += squared

    mask_rgba = bytes(mask)
    validation = validate_region_mask_rgba(mask_rgba)
    return NormalLogoConversion(
        mask_rgba=mask_rgba,
        material_preview_rgba=bytes(preview),
        validation=validation,
        cleared_hidden_rgb_texels=cleanup.cleared_texels,
        maximum_rgb_error=error_maximum,
        mean_squared_rgb_error=error_total / (CANVAS_WIDTH * CANVAS_HEIGHT * 3),
        mapping=(
            "source RGBA -> alpha-weighted closest shell/red-region/green-region "
            "triangle -> joint Xenos 4-bit unit-simplex quantization"
        ),
        palette=palette,
    )


__all__ = [
    "CANVAS_HEIGHT",
    "CANVAS_WIDTH",
    "FULL_SHELL_OPAQUE_ALPHA",
    "HelmetLogoRegionError",
    "HiddenRgbCleanup",
    "NormalLogoConversion",
    "NORMAL_LOGO_IMPORT_MODE",
    "PaletteSuggestion",
    "PROVED_MASK_ALPHA",
    "RegionMaskValidation",
    "REGION_MASK_IMPORT_MODE",
    "TwoRegionPalette",
    "XENOS_CHANNEL_STEP",
    "clear_fully_transparent_rgb",
    "convert_normal_logo_to_region_mask",
    "opaque_shell_body_rgba",
    "suggest_two_region_palette",
    "validate_full_shell_region_mask_rgba",
    "validate_region_mask_rgba",
]
