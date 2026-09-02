#!/usr/bin/env python3
"""Convert the pinned clean Eagles wing into APF's weighted crest-region mask.

The supplied 1022x256 artwork contains outward-facing mirrored wings.  APF's
helmet carrier consumes one front-to-rear wing, so this tool selects the
right-hand source wing without reflecting or redrawing it.  Source white maps
to APF green (the game's white/main palette region), source silver maps to APF
red (the silver/detail region), and the source dark outline plus transparency
map to black (unpainted helmet shell).

The recovered crest pixel shader uses each sampled RGB channel as a linear
palette weight.  APF's Xenos ``4_4_4_4`` transport preserves sixteen exact
levels per channel.  This converter therefore projects each antialiased source
pixel onto the source dark/silver/white colour triangle, filters the resulting
silver and white coverage fields with endpoint-aligned integer bilinear
weights, then jointly quantizes them to the exact Xenos nibble lattice.  Red
plus green never exceeds one coverage unit; the remainder is unpainted shell.

No resizing or quantization is delegated to Pillow.  The writer is fail-closed
on the source and decoded-result hashes and refuses to overwrite destinations.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from nfl_txtr import encode_rgba_png  # noqa: E402


SCHEMA = "apf2k8_eagles_crest_region_mask/v3"
SOURCE_PNG_SHA256 = (
    "f7f038a52a77bb5e0e5a95ed6442a13d6fb4b1223a52c69d6c187ecfd1974e1f"
)
SOURCE_RGBA_SHA256 = (
    "bc5bac8a0c5e4d4b2069c097edba2494e6faf6f310fed70616d7d29704a2cd57"
)

SOURCE_WIDTH = 1022
SOURCE_HEIGHT = 256
SOURCE_RIGHT_PAINT_BBOX = (531, 0, 1020, 255)
SOURCE_PAINT_WIDTH = SOURCE_RIGHT_PAINT_BBOX[2] - SOURCE_RIGHT_PAINT_BBOX[0] + 1
SOURCE_PAINT_HEIGHT = SOURCE_RIGHT_PAINT_BBOX[3] - SOURCE_RIGHT_PAINT_BBOX[1] + 1

CANVAS_WIDTH = 512
CANVAS_HEIGHT = 512
PAINT_WIDTH = 512
# Preserve the selected source wing's 490x256 geometry at the pinned 512x268
# proof target.  The one-pixel conservative vertical choice avoids clipping an
# antialiased endpoint and centers with equal 122-row margins.
PAINT_HEIGHT = 268
PAINT_TOP = (CANVAS_HEIGHT - PAINT_HEIGHT) // 2
EXPECTED_ACTIVE_BBOX = (
    0, PAINT_TOP, PAINT_WIDTH - 1, PAINT_TOP + PAINT_HEIGHT - 1,
)

MASK_ALPHA = 136
MASK_BLACK = (0, 0, 0, MASK_ALPHA)
MASK_RED = (255, 0, 0, MASK_ALPHA)
MASK_GREEN = (0, 255, 0, MASK_ALPHA)
XENOS_CHANNEL_STEP = 17
WEIGHT_SCALE = 65535

SOURCE_DARK = (5, 7, 8)
SOURCE_SILVER = (183, 196, 199)
SOURCE_WHITE = (255, 255, 255)
SOURCE_ANCHORS = (SOURCE_DARK, SOURCE_SILVER, SOURCE_WHITE)

MATERIAL_SHELL = (0x00, 0x4C, 0x54, 255)
MATERIAL_SILVER = (0xC0, 0xC0, 0xC0, 255)
MATERIAL_WHITE = (255, 255, 255, 255)

MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_PIXELS = SOURCE_WIDTH * SOURCE_HEIGHT

# Exact private disassembly containing ReverseLogoScaleAndOffset c29 and the
# sampled-channel palette multiply/add chain.  The converter never reads or
# distributes this trace; its hash and the non-copyrightable instruction
# equations bind the recovered interface used by this mask contract.
SHADER_WEIGHT_TRACE_SHA256 = (
    "254042c11d6534ff04c7fce3670fd1384c396d0b52e0c547fce03422bc905dd9"
)
SHADER_WEIGHT_EQUATIONS = (
    "sample.z * palette_c14",
    "sample.y * palette_c13 + previous",
    "sample.x * palette_c12 + previous",
)

# Pinned decoded results from the fixed-point conversion above.  These bind the
# complete 512x512 palette mask and its exact review material, not screenshots.
EXPECTED_MASK_RGBA_SHA256 = (
    "c9a915df7f66dae85a5f620ad4907aadc2cf3f4941fcfc86a074c68a34362d6c"
)
EXPECTED_MATERIAL_RGBA_SHA256 = (
    "cdebb62ac31e3f6569aad372ad74dc575c3d07d60646cf140c43804fcd37f84a"
)
EXPECTED_MASK_PNG_SHA256 = (
    "3d7e10828af458c9ad13663f8031311b364fa56be5c852f6aa8f38574d9c3597"
)
EXPECTED_MATERIAL_PNG_SHA256 = (
    "b53b78b5b5a20d7e5321644f582648ba76e26abd4f7eafdb17241e1a6245754d"
)


class RegionMaskError(RuntimeError):
    """The source or generated APF region mask violates the pinned contract."""


@dataclass(frozen=True)
class RegionMaskResult:
    mask_rgba: bytes
    material_rgba: bytes
    source_painted_bbox: tuple[int, int, int, int]
    output_active_bbox: tuple[int, int, int, int]
    mask_pixel_counts: dict[str, int]
    channel_levels: dict[str, tuple[int, ...]]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegionMaskError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _pixel(
    rgba: bytes, width: int, x: int, y: int,
) -> tuple[int, int, int, int]:
    start = (y * width + x) * 4
    return tuple(rgba[start : start + 4])  # type: ignore[return-value]


def _dot(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return sum(first * second for first, second in zip(left, right, strict=True))


def _subtract(
    left: Iterable[int | float], right: Iterable[int | float],
) -> tuple[float, float, float]:
    values = tuple(
        float(first) - float(second)
        for first, second in zip(left, right, strict=True)
    )
    _require(len(values) == 3, "RGB vectors must contain three channels")
    return values  # type: ignore[return-value]


def _closest_semantic_weights(rgb: Iterable[int]) -> tuple[float, float]:
    """Closest silver/white barycentric weights on the source colour triangle."""

    pixel_values = tuple(rgb)
    _require(len(pixel_values) == 3, "source RGB sample must contain three channels")
    pixel = tuple(float(value) for value in pixel_values)
    dark = tuple(float(value) for value in SOURCE_DARK)
    silver = tuple(float(value) for value in SOURCE_SILVER)
    white = tuple(float(value) for value in SOURCE_WHITE)
    silver_axis = _subtract(silver, dark)
    white_axis = _subtract(white, dark)
    relative = _subtract(pixel, dark)
    ss = _dot(silver_axis, silver_axis)
    sw = _dot(silver_axis, white_axis)
    ww = _dot(white_axis, white_axis)
    ps = _dot(relative, silver_axis)
    pw = _dot(relative, white_axis)
    determinant = ss * ww - sw * sw
    _require(determinant > 0.0, "source semantic anchors are collinear")
    red = (ww * ps - sw * pw) / determinant
    green = (ss * pw - sw * ps) / determinant
    if red >= 0.0 and green >= 0.0 and red + green <= 1.0:
        return red, green

    # Outside the triangle, choose the exact closest point on its three edges.
    vertices = (
        (dark, (0.0, 0.0)),
        (silver, (1.0, 0.0)),
        (white, (0.0, 1.0)),
    )
    candidates: list[tuple[float, int, float, float]] = []
    for edge_index, (first_index, second_index) in enumerate(((0, 1), (0, 2), (1, 2))):
        first_rgb, first_weights = vertices[first_index]
        second_rgb, second_weights = vertices[second_index]
        axis = _subtract(second_rgb, first_rgb)
        axis_length = _dot(axis, axis)
        offset = _subtract(pixel, first_rgb)
        factor = max(0.0, min(1.0, _dot(offset, axis) / axis_length))
        projected = tuple(
            first_rgb[channel] + factor * axis[channel] for channel in range(3)
        )
        error = sum(
            (pixel[channel] - projected[channel]) ** 2 for channel in range(3)
        )
        candidate_red = (
            first_weights[0] + factor * (second_weights[0] - first_weights[0])
        )
        candidate_green = (
            first_weights[1] + factor * (second_weights[1] - first_weights[1])
        )
        candidates.append((error, edge_index, candidate_red, candidate_green))
    _error, _edge_index, red, green = min(candidates)
    return red, green


def _joint_round_weights(red: float, green: float, scale: int) -> tuple[int, int]:
    _require(scale > 0, "weight scale must be positive")
    _require(red >= -1.0e-9 and green >= -1.0e-9 and red + green <= 1.0 + 1.0e-9,
             "semantic weights are outside the unit simplex")
    wanted_red = max(0.0, min(1.0, red)) * scale
    wanted_green = max(0.0, min(1.0, green)) * scale
    result_red = int(wanted_red + 0.5)
    result_green = int(wanted_green + 0.5)
    if result_red + result_green > scale:
        red_cost = (result_red - 1 - wanted_red) ** 2 + (
            result_green - wanted_green
        ) ** 2
        green_cost = (result_red - wanted_red) ** 2 + (
            result_green - 1 - wanted_green
        ) ** 2
        if red_cost <= green_cost:
            result_red -= 1
        else:
            result_green -= 1
    _require(result_red >= 0 and result_green >= 0,
             "rounded semantic weight became negative")
    _require(result_red + result_green <= scale,
             "rounded semantic weights exceed one coverage unit")
    return result_red, result_green


@lru_cache(maxsize=None)
def _source_paint_weights(pixel: tuple[int, int, int, int]) -> tuple[int, int]:
    red, green, blue, alpha = pixel
    if alpha == 0:
        return 0, 0
    silver_weight, white_weight = _closest_semantic_weights((red, green, blue))
    silver_weight *= alpha / 255.0
    white_weight *= alpha / 255.0
    return _joint_round_weights(silver_weight, white_weight, WEIGHT_SCALE)


def _bilinear_weight_sample(
    weights: list[tuple[int, int]],
    source_width: int,
    source_height: int,
    destination_x: int,
    destination_y: int,
    destination_width: int,
    destination_height: int,
) -> tuple[int, int]:
    """Endpoint-aligned fixed-point bilinear sampling of two mask fields."""

    _require(source_width > 0 and source_height > 0, "source dimensions are empty")
    _require(source_width > 1 and source_height > 1, "source crop is too small")
    _require(destination_width > 1 and destination_height > 1,
             "destination is too small")
    _require(0 <= destination_x < destination_width, "destination X is outside output")
    _require(0 <= destination_y < destination_height, "destination Y is outside output")
    _require(len(weights) == source_width * source_height,
             "source weight count differs from its dimensions")

    denominator_x = destination_width - 1
    denominator_y = destination_height - 1
    numerator_x = destination_x * (source_width - 1)
    numerator_y = destination_y * (source_height - 1)
    x0_local, remainder_x = divmod(numerator_x, denominator_x)
    y0_local, remainder_y = divmod(numerator_y, denominator_y)
    x1_local = min(x0_local + 1, source_width - 1)
    y1_local = min(y0_local + 1, source_height - 1)
    weights_x = (denominator_x - remainder_x, remainder_x)
    weights_y = (denominator_y - remainder_y, remainder_y)
    weight_total = denominator_x * denominator_y

    totals = [0, 0]
    for local_y, weight_y in ((y0_local, weights_y[0]), (y1_local, weights_y[1])):
        for local_x, weight_x in ((x0_local, weights_x[0]), (x1_local, weights_x[1])):
            weight = weight_x * weight_y
            if not weight:
                continue
            source = weights[local_y * source_width + local_x]
            totals[0] += source[0] * weight
            totals[1] += source[1] * weight
    result = [
        (value + weight_total // 2) // weight_total for value in totals
    ]
    if result[0] + result[1] > WEIGHT_SCALE:
        red_down_cost = (
            ((result[0] - 1) * weight_total - totals[0]) ** 2
            + (result[1] * weight_total - totals[1]) ** 2
        )
        green_down_cost = (
            (result[0] * weight_total - totals[0]) ** 2
            + ((result[1] - 1) * weight_total - totals[1]) ** 2
        )
        if red_down_cost <= green_down_cost:
            result[0] -= 1
        else:
            result[1] -= 1
    _require(result[0] + result[1] <= WEIGHT_SCALE,
             "filtered paint weights exceed one coverage unit")
    return result[0], result[1]


def _xenos_quantize_weights(red: int, green: int) -> tuple[int, int]:
    """Joint nearest quantization to two 4-bit channels with sum <= 15."""

    _require(red >= 0 and green >= 0 and red + green <= WEIGHT_SCALE,
             "unquantized paint weights are outside the unit simplex")
    wanted_red = red * 15
    wanted_green = green * 15
    red_nibble = (wanted_red + WEIGHT_SCALE // 2) // WEIGHT_SCALE
    green_nibble = (wanted_green + WEIGHT_SCALE // 2) // WEIGHT_SCALE
    if red_nibble + green_nibble > 15:
        red_down_cost = (
            ((red_nibble - 1) * WEIGHT_SCALE - wanted_red) ** 2
            + (green_nibble * WEIGHT_SCALE - wanted_green) ** 2
        )
        green_down_cost = (
            (red_nibble * WEIGHT_SCALE - wanted_red) ** 2
            + ((green_nibble - 1) * WEIGHT_SCALE - wanted_green) ** 2
        )
        if red_down_cost <= green_down_cost:
            red_nibble -= 1
        else:
            green_nibble -= 1
    _require(0 <= red_nibble <= 15 and 0 <= green_nibble <= 15,
             "quantized Xenos mask channel is outside four bits")
    _require(red_nibble + green_nibble <= 15,
             "quantized Xenos paint weights exceed one coverage unit")
    return red_nibble * XENOS_CHANNEL_STEP, green_nibble * XENOS_CHANNEL_STEP


def _material_pixel(red: int, green: int) -> tuple[int, int, int, int]:
    _require(red >= 0 and green >= 0 and red + green <= 255,
             "material weights exceed one coverage unit")
    shell = 255 - red - green
    return tuple(
        (
            MATERIAL_SHELL[channel] * shell
            + MATERIAL_SILVER[channel] * red
            + MATERIAL_WHITE[channel] * green
            + 127
        ) // 255
        for channel in range(3)
    ) + (255,)  # type: ignore[return-value]


def _active_bbox(rgba: bytes) -> tuple[int, int, int, int] | None:
    _require(len(rgba) == CANVAS_WIDTH * CANVAS_HEIGHT * 4,
             "mask RGBA byte length differs from 512x512")
    xs: list[int] = []
    ys: list[int] = []
    for y in range(CANVAS_HEIGHT):
        for x in range(CANVAS_WIDTH):
            red, green, blue, _alpha = _pixel(rgba, CANVAS_WIDTH, x, y)
            if red or green or blue:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def convert_source_rgba(rgba: bytes) -> RegionMaskResult:
    """Convert decoded pinned source pixels to weighted Xenos mask channels."""

    _require(len(rgba) == SOURCE_WIDTH * SOURCE_HEIGHT * 4,
             "source RGBA byte length differs from 1022x256")
    _require(_sha256(rgba) == SOURCE_RGBA_SHA256,
             "decoded source RGBA hash differs from the pinned clean wing")

    left, top, right, bottom = SOURCE_RIGHT_PAINT_BBOX
    crop_width = right - left + 1
    crop_height = bottom - top + 1
    source_weights = [
        _source_paint_weights(_pixel(rgba, SOURCE_WIDTH, x, y))
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
    ]
    _require(any(red for red, _green in source_weights),
             "source wing has no silver/detail coverage")
    _require(any(green for _red, green in source_weights),
             "source wing has no white/main coverage")

    output = bytearray(bytes(MASK_BLACK) * (CANVAS_WIDTH * CANVAS_HEIGHT))
    for destination_y in range(PAINT_HEIGHT):
        for destination_x in range(PAINT_WIDTH):
            weighted_red, weighted_green = _bilinear_weight_sample(
                source_weights,
                crop_width,
                crop_height,
                destination_x,
                destination_y,
                PAINT_WIDTH,
                PAINT_HEIGHT,
            )
            red, green = _xenos_quantize_weights(weighted_red, weighted_green)
            mask = (red, green, 0, MASK_ALPHA)
            target = (
                ((PAINT_TOP + destination_y) * CANVAS_WIDTH + destination_x) * 4
            )
            output[target : target + 4] = bytes(mask)

    mask_rgba = bytes(output)
    levels: dict[str, set[int]] = {"red": set(), "green": set()}
    for offset in range(0, len(mask_rgba), 4):
        red, green, blue, alpha = mask_rgba[offset : offset + 4]
        _require(blue == 0, "generated weighted mask contains blue coverage")
        _require(alpha == MASK_ALPHA, "generated weighted mask alpha differs")
        _require(red % XENOS_CHANNEL_STEP == 0,
                 "generated red weight is not Xenos 4-bit exact")
        _require(green % XENOS_CHANNEL_STEP == 0,
                 "generated green weight is not Xenos 4-bit exact")
        _require(red + green <= 255,
                 "generated paint weights exceed one coverage unit")
        levels["red"].add(red)
        levels["green"].add(green)
    _require({0, 255} <= levels["red"],
             "generated mask is missing empty or full silver coverage")
    _require({0, 255} <= levels["green"],
             "generated mask is missing empty or full white coverage")
    _require(any(value not in (0, 255) for value in levels["red"]),
             "generated mask lost antialiased silver coverage")
    _require(any(value not in (0, 255) for value in levels["green"]),
             "generated mask lost antialiased white coverage")
    active_bbox = _active_bbox(mask_rgba)
    _require(active_bbox == EXPECTED_ACTIVE_BBOX,
             f"generated active bbox differs: {active_bbox}")

    material = bytearray(CANVAS_WIDTH * CANVAS_HEIGHT * 4)
    mask_counts: Counter[str] = Counter()
    for offset in range(0, len(mask_rgba), 4):
        red, green, _blue, _alpha = mask_rgba[offset : offset + 4]
        material[offset : offset + 4] = bytes(_material_pixel(red, green))
        if red == 0 and green == 0:
            mask_counts["black_unpainted"] += 1
        if red:
            mask_counts["red_weighted_texels"] += 1
        if green:
            mask_counts["green_weighted_texels"] += 1
        if red and green:
            mask_counts["mixed_weight_texels"] += 1
        if red not in (0, 255) or green not in (0, 255):
            mask_counts["antialiased_weight_texels"] += 1
    material_rgba = bytes(material)

    mask_hash = _sha256(mask_rgba)
    material_hash = _sha256(material_rgba)
    if EXPECTED_MASK_RGBA_SHA256:
        _require(mask_hash == EXPECTED_MASK_RGBA_SHA256,
                 "generated mask RGBA hash differs from the pinned result")
    if EXPECTED_MATERIAL_RGBA_SHA256:
        _require(material_hash == EXPECTED_MATERIAL_RGBA_SHA256,
                 "generated material RGBA hash differs from the pinned result")

    return RegionMaskResult(
        mask_rgba=mask_rgba,
        material_rgba=material_rgba,
        source_painted_bbox=SOURCE_RIGHT_PAINT_BBOX,
        output_active_bbox=EXPECTED_ACTIVE_BBOX,
        mask_pixel_counts={
            name: mask_counts[name]
            for name in (
                "black_unpainted",
                "red_weighted_texels",
                "green_weighted_texels",
                "mixed_weight_texels",
                "antialiased_weight_texels",
            )
        },
        channel_levels={
            name: tuple(sorted(values)) for name, values in levels.items()
        },
    )


def _read_pinned_source(path: Path) -> tuple[bytes, bytes]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RegionMaskError(f"cannot open source wing: {exc}") from exc
    try:
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode), "source wing must be a regular file")
        _require(0 < info.st_size <= MAX_SOURCE_BYTES,
                 "source wing exceeds the bounded input size")
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            _require(bool(chunk), "source wing ended before its declared size")
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
    finally:
        os.close(descriptor)
    _require(_sha256(payload) == SOURCE_PNG_SHA256,
             "source PNG hash differs from the pinned clean mirrored Eagles wings")

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow ships with the app
        raise RegionMaskError("Pillow is required to decode the pinned PNG") from exc
    previous_pixel_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            _require(image.size == (SOURCE_WIDTH, SOURCE_HEIGHT),
                     "source wing dimensions differ from 1022x256")
            rgba = image.convert("RGBA").tobytes()
    except RegionMaskError:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow uses format-specific errors
        raise RegionMaskError(f"could not decode source wing PNG: {exc}") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_pixel_limit
    _require(_sha256(rgba) == SOURCE_RGBA_SHA256,
             "decoded source RGBA hash differs from the pinned clean wing")
    return payload, rgba


def build(source: Path) -> tuple[RegionMaskResult, dict[str, object]]:
    source_payload, rgba = _read_pinned_source(Path(source))
    result = convert_source_rgba(rgba)
    mask_png = encode_rgba_png(CANVAS_WIDTH, CANVAS_HEIGHT, result.mask_rgba)
    material_png = encode_rgba_png(
        CANVAS_WIDTH, CANVAS_HEIGHT, result.material_rgba,
    )
    _require(_sha256(mask_png) == EXPECTED_MASK_PNG_SHA256,
             "generated mask PNG hash differs from the pinned result")
    _require(_sha256(material_png) == EXPECTED_MATERIAL_PNG_SHA256,
             "generated material PNG hash differs from the pinned result")
    receipt: dict[str, object] = {
        "contract": {
            "anti_alias_handling": (
                "source_rgb_triangle_projection_times_alpha_then_integer_"
                "endpoint_aligned_bilinear_then_joint_xenos_4bit_quantization"
            ),
            "aspect_fit": {
                "horizontal_scale_numerator": PAINT_WIDTH,
                "horizontal_scale_denominator": SOURCE_PAINT_WIDTH,
                "pinned_integer_height": PAINT_HEIGHT,
                "output_painted_size": [PAINT_WIDTH, PAINT_HEIGHT],
                "source_painted_size": [SOURCE_PAINT_WIDTH, SOURCE_PAINT_HEIGHT],
                "source_shape_preserved_without_crop": True,
                "vertical_center_offset": PAINT_TOP,
            },
            "mask_channels": {
                "black": "zero_weight_unpainted_shell",
                "green_0_to_255": "linear_white_main_weight",
                "red_0_to_255": "linear_silver_detail_weight",
            },
            "mask_weight_sum_maximum": 255,
            "no_reflection": True,
            "no_redraw": True,
            "preview_equation": (
                "shell*(255-red-green)/255 + silver*red/255 + white*green/255"
            ),
            "selected_source_side": "right_outward_front_to_rear",
            "shader_weight_proof": {
                "equations": list(SHADER_WEIGHT_EQUATIONS),
                "private_disassembly_sha256": SHADER_WEIGHT_TRACE_SHA256,
                "sample_channels_are_linear_palette_weights": True,
            },
            "xenos_4_4_4_4": {
                "channel_step": XENOS_CHANNEL_STEP,
                "levels_per_channel": 16,
                "output_is_decode_roundtrip_exact": True,
            },
        },
        "result": {
            "active_bbox": list(result.output_active_bbox),
            "channel_levels": {
                name: list(values) for name, values in result.channel_levels.items()
            },
            "height": CANVAS_HEIGHT,
            "mask_decoded_rgba_sha256": _sha256(result.mask_rgba),
            "mask_pixel_counts": result.mask_pixel_counts,
            "mask_png_sha256": _sha256(mask_png),
            "material_decoded_rgba_sha256": _sha256(result.material_rgba),
            "material_png_sha256": _sha256(material_png),
            "width": CANVAS_WIDTH,
        },
        "schema": SCHEMA,
        "source": {
            "decoded_rgba_sha256": _sha256(rgba),
            "height": SOURCE_HEIGHT,
            "painted_bbox": list(result.source_painted_bbox),
            "png_sha256": _sha256(source_payload),
            "width": SOURCE_WIDTH,
        },
    }
    return result, receipt


def publish(
    source: Path, mask_output: Path, material_output: Path, receipt_output: Path,
) -> dict[str, object]:
    """Write new deterministic artifacts, cleaning only files created here."""

    destinations = tuple(
        Path(path) for path in (mask_output, material_output, receipt_output)
    )
    _require(len(set(destinations)) == len(destinations),
             "mask, material, and receipt destinations must be different")
    for destination in destinations:
        _require(not destination.exists() and not destination.is_symlink(),
                 f"refusing to overwrite destination: {destination}")
        _require(destination.parent.is_dir(),
                 f"destination parent does not exist: {destination.parent}")

    result, receipt = build(source)
    payloads = (
        encode_rgba_png(CANVAS_WIDTH, CANVAS_HEIGHT, result.mask_rgba),
        encode_rgba_png(CANVAS_WIDTH, CANVAS_HEIGHT, result.material_rgba),
        (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    created: list[Path] = []
    try:
        for destination, payload in zip(destinations, payloads, strict=True):
            descriptor = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
            )
            created.append(destination)
            try:
                cursor = 0
                while cursor < len(payload):
                    cursor += os.write(descriptor, payload[cursor:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except BaseException:
        for created_path in created:
            created_path.unlink(missing_ok=True)
        raise
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--mask-output", required=True, type=Path)
    parser.add_argument("--material-output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = publish(
            args.source, args.mask_output, args.material_output, args.receipt,
        )
    except (OSError, RegionMaskError) as exc:
        parser.exit(2, f"Eagles crest region-mask conversion failed: {exc}\n")
    print(json.dumps(receipt["result"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
