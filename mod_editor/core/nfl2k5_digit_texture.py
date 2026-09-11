"""Coverage-preserving digit art for the existing fixed-size P8 writer.

EXPERIMENTAL / UNWITNESSED. These are texture-space operations, not a claim
about the GPU's camera-dependent LOD, lighting, material or alpha-test state.
One BGRA8888 palette serves the complete chain, as in retail digit resources.
"""

from __future__ import annotations

from collections import Counter
from array import array
from typing import Any

from PIL import Image

from .errors import ValidationError


MIP_FILTER = "premultiplied_rgba_area_from_base"
PALETTE_POLICY = "shared_bgra8888_coverage_and_authored_colours"


def resize_cell(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Filter premultiplied colour, then return straight-alpha PNG pixels.

    Pillow's RGBA Lanczos already premultiplies, but through eight-bit RGBa.
    Float channels avoid rounding faint edges to saturated or black RGB before
    filtering. Only the final straight-alpha PNG is rounded to eight bits.
    Never guess whether a user's *stored* RGB has already been premultiplied.
    """
    rgba = image.convert("RGBA")
    if rgba.size == size:
        return rgba
    channels = [channel.tobytes() for channel in rgba.split()]
    filtered = []
    for channel in range(4):
        values = array("f", (float(a) if channel == 3 else float(c * a)
                              for c, a in zip(channels[channel], channels[3])))
        plane = Image.frombytes("F", rgba.size, values.tobytes())
        filtered.append(array("f", plane.resize(size, Image.Resampling.LANCZOS).getdata()))
    output = bytearray(size[0] * size[1] * 4)
    for i, alpha in enumerate(filtered[3]):
        a = max(0, min(255, round(alpha)))
        if a:
            for channel in range(3):
                output[i * 4 + channel] = max(0, min(255, round(filtered[channel][i] / alpha)))
            output[i * 4 + 3] = a
    return Image.frombytes("RGBA", size, bytes(output))


def make_digit_mips(rgba: bytes, width: int, height: int, count: int) -> list[Any]:
    """Average exact base-level footprints, retaining coverage in eight bits.

    Each lower level is derived from the supplied base, never from palette
    indices or a previously rounded/quantized mip. Invisible RGB cannot bleed
    into the average. Stored RGB remains straight alpha for the P8 palette.
    """
    from nfl_tset_png_import import MipLevel

    if (type(width) is not int or type(height) is not int or type(count) is not int
            or not 1 <= width <= 4096 or not 1 <= height <= 4096
            or not 1 <= count <= 13 or len(rgba) != width * height * 4
            or width % (1 << (count - 1)) or height % (1 << (count - 1))):
        raise ValidationError("The digit dimensions do not contain that complete mip chain.")
    base = bytearray(rgba)
    for i in range(0, len(base), 4):
        if base[i + 3] == 0:
            base[i:i + 3] = b"\0\0\0"
    result = [MipLevel(0, width, height, bytes(base))]
    for level in range(1, count):
        stride = 1 << level
        w, h = width // stride, height // stride
        area = stride * stride
        output = bytearray(w * h * 4)
        for y in range(h):
            for x in range(w):
                alpha = red = green = blue = 0
                for dy in range(stride):
                    start = ((y * stride + dy) * width + x * stride) * 4
                    for i in range(start, start + stride * 4, 4):
                        a = base[i + 3]
                        alpha += a
                        red += base[i] * a
                        green += base[i + 1] * a
                        blue += base[i + 2] * a
                a = (alpha + area // 2) // area
                if a:
                    offset = (y * w + x) * 4
                    output[offset:offset + 4] = bytes((
                        (red + alpha // 2) // alpha,
                        (green + alpha // 2) // alpha,
                        (blue + alpha // 2) // alpha, a,
                    ))
        result.append(MipLevel(level, w, h, bytes(output)))
    return result


def _premultiplied(color: tuple[int, ...]) -> tuple[int, int, int, int]:
    r, g, b, a = color
    return ((r * a + 127) // 255, (g * a + 127) // 255,
            (b * a + 127) // 255, a)


def quantize_digit_levels(levels: list[Any], maximum: int = 256, *, preserve_transparent_rgb: bool = False):
    """One deterministic palette, protected solid colours and soft edges.

    Give each mip equal total influence so the base cannot monopolize entries.
    Reserve up to sixteen exact opaque author colours (including rare outlines).
    For resampled/noisy art with more, reserve up to eight distinct solid
    colours, in frequency order, keeping near-identical shades from crowding
    out the outline. Report that approximation. Quantize the rest in premultiplied
    space. Transparent, partial and opaque pixels never map across alpha classes.
    The caller refuses a compression fit below 16 entries, instead of silently
    reducing a detailed sheet to two colours.
    """
    from nfl_tset_png_import import median_cut_palette, rgba_tuples

    if not levels or not (8 if preserve_transparent_rgb else 16) <= maximum <= 256:
        raise ValidationError("Digit quality needs 16 to 256 colours, or 8 to 12 for cleaned two-tone art.")
    colors = [rgba_tuples(level.rgba) for level in levels]
    hist: Counter = Counter()
    for level, pixels in zip(levels, colors):
        weight = (levels[0].width * levels[0].height) // (level.width * level.height)
        for color, amount in Counter(pixels).items():
            hist[color] += amount * weight
    opaque = Counter(c for c in colors[0] if c[3] == 255)
    anchors = sorted(opaque) if len(opaque) <= 16 else []
    if len(opaque) > 16:
        for color in sorted(opaque, key=lambda c: (-opaque[c], c)):
            if all(max(abs(color[ch] - kept[ch]) for ch in range(3)) >= 24 for kept in anchors):
                anchors.append(color)
                if len(anchors) == 8:
                    break
    if preserve_transparent_rgb and len(anchors) > maximum - 7:
        anchors = sorted(anchors, key=lambda c: (-opaque[c], c))[:max(2, maximum - 7)]
    palette = list(anchors)
    if any(c[3] == 0 for c in hist):
        if preserve_transparent_rgb:
            transparent = sorted((c for c in hist if c[3] == 0), key=lambda c: (-hist[c], c))
            palette.append(transparent[0])
            other = next((c for c in transparent if max(abs(c[k]-transparent[0][k]) for k in range(3)) >= 24), None)
            if other is not None:
                palette.append(other)
        else:
            palette.append((0, 0, 0, 0))
    # Reserve one real partial colour per occupied coverage band. These also
    # guarantee an eligible mapping when median-cut rounds an endpoint.
    bands = ((1, 127), (128, 254)) if maximum < 16 else ((1, 63), (64, 127), (128, 191), (192, 254))
    for low, high in bands:
        partial = [c for c in hist if low <= c[3] <= high]
        if partial:
            palette.append(max(partial, key=lambda c: (hist[c], c)))
    if len(palette) >= maximum and len(hist) > maximum:
        raise ValidationError("Too many solid and edge colours for this digit slot; simplify the sheet.")
    if len(hist) <= maximum:
        palette = sorted(hist)
    else:
        reserved = set(palette)
        remaining: Counter = Counter()
        for color, amount in hist.items():
            if color not in reserved:
                remaining[_premultiplied(color)] += amount
        for r, g, b, a in median_cut_palette(remaining, maximum - len(palette)):
            if a:
                palette.append((min(255, (r * 255 + a // 2) // a),
                                min(255, (g * 255 + a // 2) // a),
                                min(255, (b * 255 + a // 2) // a), a))
        palette = sorted(set(palette))
    premult = [_premultiplied(c) for c in palette]
    mapping = {}
    error = maximum_error = differing = 0
    for color in sorted(hist):
        p = _premultiplied(color)
        eligible = [i for i, candidate in enumerate(palette)
                    if (candidate[3] == 0) == (color[3] == 0)
                    and (candidate[3] == 255) == (color[3] == 255)]
        index = min(eligible, key=lambda i: (
            sum((p[ch] - premult[i][ch]) ** 2 for ch in range(4)),
            sum((color[ch] - palette[i][ch]) ** 2 for ch in range(4)), i))
        mapping[color] = index
        mapped = palette[index]
        error += sum((color[ch] - mapped[ch]) ** 2 for ch in range(4)) * hist[color]
        maximum_error = max(maximum_error, *(abs(color[ch] - mapped[ch]) for ch in range(4)))
        differing += hist[color] if color != mapped else 0
    return palette, [bytes(mapping[c] for c in row) for row in colors], {
        "input_unique_rgba_colors": len(hist), "palette_entries": len(palette),
        "weighted_squared_rgba_error": error, "maximum_channel_error": maximum_error,
        "weighted_differing_pixel_count": differing,
        "protected_opaque_colours": len(anchors),
        "unprotected_opaque_colours": len(opaque) - len(anchors),
        "approximated_opaque_colours": sum(color not in palette for color in opaque),
        "alpha_bits": 8,
    }
