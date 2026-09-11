"""One preparation policy for digit builds, previews and image checks.

Only texture-space geometry is inferred. Retail pixels stay in memory and are
used to measure registration, never as replacement artwork.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import replace
from io import BytesIO
import math

from PIL import Image, ImageFilter

from .errors import ValidationError
from .nfl2k5_digit_texture import resize_cell, make_digit_mips, quantize_digit_levels

REGISTRATION_KEY = "nfl2k5_digit_registration"
REGISTRATION_CHOICES = (("Match retail size", "retail"), ("As authored", "as_authored"))
ALPHA_LOW, ALPHA_HIGH = 16, 240


def registration_mode(payload: bytes) -> str:
    with Image.open(BytesIO(payload)) as image:
        mode = image.info.get(REGISTRATION_KEY, "retail")
    if mode not in {"retail", "as_authored"}:
        raise ValidationError("Unknown number registration. Choose Match retail size or As authored.")
    return mode


def measure(image: Image.Image) -> dict:
    alpha = image.getchannel("A")
    bounds = alpha.point(lambda a: 255 if a >= ALPHA_LOW else 0).getbbox()
    solid = alpha.point(lambda a: 255 if a >= ALPHA_HIGH else 0).getbbox()
    return {"box": list(bounds) if bounds else None,
            "opaque_box": list(solid) if solid else None,
            "margins": [bounds[0], bounds[1], image.width-bounds[2], image.height-bounds[3]] if bounds else None,
            "baseline_exclusive": bounds[3] if bounds else None,
            "aspect": (bounds[2]-bounds[0])/(bounds[3]-bounds[1]) if bounds else None}


def collapse_colours(image: Image.Image) -> tuple[Image.Image, dict]:
    """Collapse only nearby RGB shades (at most 12/255 per channel).

    Frequency-first anchors keep a rare contrasting outline. We do not turn a
    photograph into an invented two-tone glyph, or guess premultiplied input.
    """
    pixels = list(image.getdata())
    hist = Counter(c[:3] for c in pixels if c[3] >= ALPHA_LOW)
    anchors, mapping = [], {}
    for colour in sorted(hist, key=lambda c: (-hist[c], c)):
        near = next((a for a in anchors if max(abs(a[k]-colour[k]) for k in range(3)) <= 12), None)
        if near is None:
            near = colour
            anchors.append(colour)
        mapping[colour] = near
    result = Image.new("RGBA", image.size)
    result.putdata([(*mapping.get(c[:3], c[:3]), c[3]) for c in pixels])
    return result, {"visible_rgb_before": len(hist), "visible_rgb_after": len(anchors),
                    "maximum_rgb_cleanup_delta": 12}


def two_tone_colours(image):
    """Recognise two flat colours plus their resampling blends, not new hues."""
    hist = Counter(c[:3] for c in image.getdata() if c[3] >= ALPHA_HIGH)
    if len(hist) < 2:
        return tuple(hist)
    first = max(hist, key=lambda c: (hist[c], c))
    second = max(hist, key=lambda c: sum((c[k]-first[k])**2 for k in range(3)))
    vector = tuple(second[k]-first[k] for k in range(3))
    length = sum(v*v for v in vector)
    if length < 48**2:
        return ()
    for colour in hist:
        fraction = sum((colour[k]-first[k])*vector[k] for k in range(3))/length
        if max(abs(colour[k]-first[k]-fraction*vector[k]) for k in range(3)) > 12:
            return ()
    return first, second


def flatten_regions(image, colours):
    if not colours:
        return image
    output = image.copy()
    output.putdata([(*min(colours, key=lambda c: sum((c[k]-p[k])**2 for k in range(3))), p[3])
                    for p in image.getdata()])
    return output


def bind_alpha(image: Image.Image) -> Image.Image:
    result = image.copy()
    result.putalpha(image.getchannel("A").point(
        lambda a: 0 if a < ALPHA_LOW else 255 if a >= ALPHA_HIGH else a))
    return result


def one_texel_edge(image: Image.Image) -> Image.Image:
    """Retain partial coverage only immediately next to a solid texel.

    Interior alpha noise becomes opaque. Wide low-alpha fringes are removed,
    without eroding an opaque outline or merging separate colour regions.
    """
    alpha = image.getchannel("A")
    low = alpha.filter(ImageFilter.MinFilter(3)).tobytes()
    high = alpha.filter(ImageFilter.MaxFilter(3)).tobytes()
    values = bytes(255 if a and lo >= 128 else
                   0 if 0 < a < 255 and hi < 255 else a
                   for a, lo, hi in zip(alpha.tobytes(), low, high))
    result = image.copy()
    result.putalpha(Image.frombytes("L", image.size, values))
    return result


def extend_edge_colours(image: Image.Image) -> Image.Image:
    """Nearest visible RGB through transparent texels, leaving alpha intact.

    Deterministic four-connected flood, bounded by the tiny digit canvas. This
    protects straight-alpha GPU bilinear sampling as well as offline previews.
    """
    data = bytearray(image.tobytes())
    width, height = image.size
    seen = bytearray(a != 0 for a in data[3::4])
    queue = deque(i for i, visible in enumerate(seen) if visible)
    while queue:
        i = queue.popleft()
        x, y = i % width, i // width
        for j in (i-1 if x else -1, i+1 if x+1 < width else -1,
                  i-width if y else -1, i+width if y+1 < height else -1):
            if j >= 0 and not seen[j]:
                seen[j] = 1
                data[j*4:j*4+3] = data[i*4:i*4+3]
                queue.append(j)
    return Image.frombytes("RGBA", image.size, bytes(data))


def prepare_digit(image: Image.Image, retail: Image.Image, mode: str = "retail") -> tuple[Image.Image, dict]:
    if image.size != retail.size or mode not in {"retail", "as_authored"}:
        raise ValidationError("Digit preparation needs matching canvases and a supported registration.")
    source = measure(image)
    reference = measure(retail)
    image, cleanup = collapse_colours(bind_alpha(image.convert("RGBA")))
    tones = two_tone_colours(image)
    image = flatten_regions(image, tones)
    bounds = image.getchannel("A").getbbox()
    if not bounds:
        raise ValidationError("The number cell is empty after alpha cleanup. Supply a visible digit.")
    box = reference["box"]
    if not box:
        raise ValidationError("The retail digit has no measurable registration box.")
    box = [max(1, box[0]), max(1, box[1]), min(retail.width-1, box[2]), min(retail.height-1, box[3])]
    scale = 1.0
    destination = list(bounds)
    if mode == "retail":
        width, height = bounds[2]-bounds[0], bounds[3]-bounds[1]
        scale = min((box[2]-box[0])/width, (box[3]-box[1])/height)
        size = (max(1, math.floor(width*scale+1e-8)), max(1, math.floor(height*scale+1e-8)))
        left, top = box[0]+(box[2]-box[0]-size[0])//2, box[1]+(box[3]-box[1]-size[1])//2
        glyph = resize_cell(extend_edge_colours(image.crop(bounds)), size)
        image = Image.new("RGBA", retail.size)
        image.paste(glyph, (left, top))
        destination = [left, top, left+size[0], top+size[1]]
    image = one_texel_edge(bind_alpha(image))
    image = flatten_regions(image, tones)
    image, after = collapse_colours(image)
    image = extend_edge_colours(image)
    return image, {
        "registration": {"mode": mode, "source": source, "retail": reference,
                         "chosen_box": box, "destination_box": destination, "scale": scale,
                         "result": measure(image)},
        "cleanup": {**cleanup, "final_visible_rgb": after["visible_rgb_after"],
                    "alpha_below_to_zero": ALPHA_LOW, "alpha_at_or_above_to_opaque": ALPHA_HIGH,
                    "antialias_band_texels": 1, "resample": "float_premultiplied_lanczos",
                    "transparent_rgb": "nearest_visible_edge", "applied": True},
    }


def prepared_mips(image: Image.Image, count: int) -> list:
    return [replace(m, rgba=extend_edge_colours(Image.frombytes("RGBA", (m.width, m.height), m.rgba)).tobytes())
            for m in make_digit_mips(image.tobytes(), image.width, image.height, count)]


def edge_quantizer(levels, maximum=256):
    return quantize_digit_levels(levels, maximum, preserve_transparent_rgb=True)


def kept_retail_reason(stored_size: int) -> str:
    return (f"kept retail: the authored digit could not fit its {stored_size}-byte texture slot "
            "after cleanup and the recognisable-art fit ladder. Simplify the fill and outline, then preview again.")


def fit_summary(preparation: dict, colours: int) -> str:
    mode = "retail registration" if preparation["registration"]["mode"] == "retail" else "As authored placement"
    factor = preparation["fit"]["registration_factor"]
    extra = f" Additional scale {factor:.0%}." if factor < 1 else ""
    return f"fits after {mode} and cleanup ({colours} colours).{extra}"


def fit_digit(image, retail, mode, mip_count, candidate, *, stream_tag, offset_bits, stored_size):
    """Bounded, shared preparation and encoding, including honest last resorts."""
    from nfl_tset_png_import import quantize_levels_to_vc_lz_bound, QualityBudgetError
    prepared, receipt = prepare_digit(image, retail, mode)
    levels = prepared_mips(prepared, mip_count)
    attempts = []
    # Below 16 entries only a clean two-tone input qualifies. Both opaque
    # colours remain protected; palette capacity is spent on coverage next.
    regions = sorted({c[:3] for c in prepared.getdata() if c[3] >= ALPHA_LOW})
    floor = 8 if 1 <= len(regions) <= 2 else 16
    for factor in (1.0, 0.94, 0.88):
        if factor != 1.0:
            if mode == "as_authored":
                break
            bounds = prepared.getchannel("A").getbbox()
            size = (max(1, round((bounds[2]-bounds[0])*factor)), max(1, round((bounds[3]-bounds[1])*factor)))
            smaller = Image.new("RGBA", image.size)
            left = (bounds[0]+bounds[2]-size[0])//2
            top = (bounds[1]+bounds[3]-size[1])//2
            smaller.paste(resize_cell(prepared.crop(bounds), size), (left, top))
            smaller = one_texel_edge(bind_alpha(smaller))
            if floor == 8:
                smaller = flatten_regions(smaller, regions)
            levels = prepared_mips(smaller, mip_count)
        try:
            fit = quantize_levels_to_vc_lz_bound(
                levels, lambda p, i: candidate(levels, p, i), stream_tag=stream_tag,
                offset_bits=offset_bits, max_encoded_size=stored_size,
                quantizer=edge_quantizer, minimum_palette_limit=floor,
                palette_limits=(256, 128, 64, 32, 16, 12, 8))
        except QualityBudgetError as exc:
            attempts.extend({**a, "registration_factor": factor} for a in getattr(exc, "attempts", ()))
            continue
        attempts.extend({**a, "registration_factor": factor} for a in fit.attempts)
        used = {fit.palette[i] for i in fit.index_levels[0] if fit.palette[i][3] >= ALPHA_LOW}
        if floor == 8 and any(not any(max(abs(c[k]-region[k]) for k in range(3)) <= 24 for c in used)
                              for region in regions):
            # Never accept a tier that lost a contrasting fill or outline.
            # A smaller image cannot restore a missing region either.
            break
        receipt["fit"] = {"registration_factor": factor, "minimum_palette_budget": floor,
                          "two_tone": floor == 8, "attempts": attempts,
                          "written_box": measure(Image.frombytes("RGBA", image.size, levels[0].rgba))["box"]}
        return replace(fit, attempts=tuple(attempts)), levels, receipt
    error = QualityBudgetError(kept_retail_reason(stored_size))
    error.attempts = tuple(attempts)
    error.preparation = receipt
    raise error
