"""One preparation policy for digit builds, previews and image checks.

Only texture-space geometry is inferred. Retail pixels stay in memory and are
used to measure registration, never as replacement artwork.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, replace
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
    if not image.convert("RGBA").getchannel("A").getbbox():
        # A deliberately blank cell: every texel of the supplied art is fully transparent (a kit without sleeve or
        # helmet numbers, such as the 2020+ Chargers' sleeves). Art whose faint alpha the cleanup removes is still
        # refused below.
        blank = Image.new("RGBA", retail.size, (0, 0, 0, 0))
        return blank, {
            "registration": {"mode": mode, "source": source, "retail": reference, "chosen_box": None,
                             "destination_box": None, "scale": 1.0, "result": measure(blank), "blank": True},
            "cleanup": {"applied": False, "blank": True},
        }
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
                    "transparent_rgb": "nearest_visible_edge", "mip_border_alpha_zero": True,
                    "applied": True},
    }


def prepared_mips(image: Image.Image, count: int) -> list:
    result = []
    for mip in make_digit_mips(image.tobytes(), image.width, image.height, count):
        level = Image.frombytes("RGBA", (mip.width, mip.height), mip.rgba)
        if mip.level and min(level.size) >= 3:
            # Retail number mips retain a clear one-texel border. Area reduction
            # alone averages a one-pixel base margin into nonzero border alpha
            # (223/255 at 8px), which clamp sampling stretches outside the quad.
            # Keep the base placement, including an expert's As authored choice.
            alpha = level.getchannel("A")
            alpha.paste(0, (0, 0, level.width, 1))
            alpha.paste(0, (0, level.height-1, level.width, level.height))
            alpha.paste(0, (0, 0, 1, level.height))
            alpha.paste(0, (level.width-1, 0, level.width, level.height))
            level.putalpha(alpha)
        result.append(replace(mip, rgba=extend_edge_colours(level).tobytes()))
    return result


def edge_quantizer(levels, maximum=256):
    return quantize_digit_levels(levels, maximum, preserve_transparent_rgb=True)


def kept_retail_reason(stored_size: int) -> str:
    return (f"kept retail: the authored digit could not fit its {stored_size}-byte texture slot "
            "after cleanup and the recognisable-art fit ladder. Simplify the fill and outline, then preview again.")


def kept_retail_advice(*, stored_size: int | None = None, needed: int | None = None, colours: int | None = None) -> str:
    """What was measured and what to change, for a digit that stayed retail (empty when nothing is known)."""
    parts = []
    if needed and stored_size and needed > stored_size:
        parts.append(f"Even the simplest version tried needs about {needed:,} bytes and the slot holds {stored_size:,}.")
    if colours and colours > 4:
        parts.append(f"It uses {colours} colours after cleanup; gradients and soft shading cost the most space.")
    if parts:
        parts.append("Use one flat fill and one flat outline, no glow or shadow, and fewer curves and corners.")
    return " ".join(parts)


def fit_summary(preparation: dict, colours: int) -> str:
    mode = "retail registration" if preparation["registration"]["mode"] == "retail" else "As authored placement"
    factor = preparation["fit"]["registration_factor"]
    extra = f" Additional scale {factor:.0%}." if factor < 1 else ""
    simplified = preparation["fit"].get("simplified")
    if simplified:
        extra += f" To fit this slot, {simplified['text']}."
    return f"fits after {mode} and cleanup ({colours} colours).{extra}"


@dataclass(frozen=True)
class _Step:
    """One deliberate, reported simplification, tried only after the faithful fit has failed."""

    name: str
    text: str
    colours: int | None = None
    hard: bool = False


# From least to most visible. None of them drops the outline or the fill, and none is silent:
# the receipt, the preview note and Check my images all say which one was used.
_STEPS = (
    _Step("hard_edges", "its edges were made hard at the largest size (the smaller views keep soft edges)", hard=True),
    _Step("bands_4", "its shading was reduced to 4 flat colours, with hard edges", colours=4, hard=True),
    _Step("bands_3", "its shading was reduced to 3 flat colours, with hard edges", colours=3, hard=True),
    _Step("bands_2", "its shading was reduced to 2 flat colours, with hard edges", colours=2, hard=True),
    # Only for a digit that is nothing but shading (no outline, one region), where one flat colour loses no region.
    _Step("bands_1", "its shading was flattened to one colour, with hard edges", colours=1, hard=True),
)
_HARD_LUT = [0] * 128 + [255] * 128
#: A fill with at least this many different solid colours is shading (a gradient), not separate flat regions.
_SHADED = 6


def hard_edges(image: Image.Image) -> Image.Image:
    """Binary alpha at the largest size. Smaller levels are still averaged from it, so they stay soft."""
    result = image.copy()
    result.putalpha(image.getchannel("A").point(_HARD_LUT))
    return extend_edge_colours(result)


def _seed_colours(counts: Counter, count: int) -> list[tuple[int, int, int]]:
    """Weighted k-means over a handful of colours, seeded from the most common colour, then the farthest."""
    colours = sorted(counts)
    centres = [max(colours, key=lambda c: (counts[c], c))]
    while len(centres) < min(count, len(colours)):
        centres.append(max(colours, key=lambda c: (min(sum((c[k]-m[k])**2 for k in range(3)) for m in centres), c)))
    for _ in range(12):
        members: list[list[tuple[int, int, int]]] = [[] for _ in centres]
        for colour in colours:
            index = min(range(len(centres)), key=lambda i: (sum((colour[k]-centres[i][k])**2 for k in range(3)), i))
            members[index].append(colour)
        moved = []
        for index, group in enumerate(members):
            total = sum(counts[c] for c in group)
            moved.append(tuple(round(sum(c[k]*counts[c] for c in group)/total) for k in range(3)) if total else centres[index])
        if moved == centres:
            break
        centres = moved
    return centres


def _smooth_colours(image: Image.Image) -> Counter:
    """Colours of pixels inside flat or gently shaded areas.

    A pixel counts when it and its four neighbours are solid and no neighbour differs from it by more than
    16 in any channel. Edges, anti-aliasing blends and the seam between an outline and its fill do not count,
    so they cannot be mistaken for shading or for an extra region.
    """
    width, height = image.size
    pixels = list(image.getdata())
    smooth: Counter = Counter()
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            here = pixels[y * width + x]
            if here[3] < ALPHA_HIGH:
                continue
            for there in (pixels[y * width + x - 1], pixels[y * width + x + 1],
                          pixels[(y - 1) * width + x], pixels[(y + 1) * width + x]):
                if there[3] < ALPHA_HIGH or max(abs(here[k] - there[k]) for k in range(3)) > 16:
                    break
            else:
                smooth[here[:3]] += 1
    return smooth


def _rim_colour(image: Image.Image) -> tuple[int, int, int] | None:
    """The one colour that rims the digit (an outline), or None. Half the pixels touching transparency share it."""
    width, height = image.size
    pixels = list(image.getdata())
    rim: Counter = Counter()
    for y in range(height):
        for x in range(width):
            here = pixels[y * width + x]
            if here[3] < ALPHA_HIGH:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height) or pixels[ny * width + nx][3] < ALPHA_LOW:
                    rim[here[:3]] += 1
                    break
    total = sum(rim.values())
    if not total:
        return None
    best = max(rim, key=lambda c: (rim[c], c))
    near = sum(n for c, n in rim.items() if max(abs(c[k] - best[k]) for k in range(3)) <= 24)
    return best if near * 2 >= total else None


class _Shading:
    """What a digit is made of: an outline colour (or none), the fill shades, and how many separate regions."""

    def __init__(self, image: Image.Image) -> None:
        smooth = _smooth_colours(image)
        self.rim = _rim_colour(image)
        total = sum(smooth.values())
        fill = Counter({c: n for c, n in smooth.items()
                        if self.rim is None or max(abs(c[k] - self.rim[k]) for k in range(3)) > 40})
        self.fill = Counter({c: n for c, n in fill.items() if n >= max(2, total * 0.005)})
        # colours within one gradient step of each other are one region; a flat patch of another colour is its own
        colours = sorted(self.fill)
        parent = list(range(len(colours)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        for i, first in enumerate(colours):
            for j in range(i + 1, len(colours)):
                if sum((first[k] - colours[j][k]) ** 2 for k in range(3)) <= 48 * 48:
                    parent[find(i)] = find(j)
        self.regions = len({find(i) for i in range(len(colours))}) + (1 if self.rim is not None else 0)
        #: Many different fill shades are shading (a gradient). A few are flat regions.
        self.shaded = len(self.fill) >= _SHADED


def flatten_shading(image: Image.Image, count: int) -> Image.Image | None:
    """Merge a gradient or shaded fill into *count* flat colours in all; None when that would change nothing or lose a region.

    An outline keeps its own colour (one of the *count*), and the fill shades are grouped around the commonest
    shade and the shades farthest from it, so a flat patch of another colour keeps its own colour too. Edge blends are
    simply given to the nearest of the final colours.
    """
    shading = _Shading(image)
    if not shading.shaded or count < shading.regions:
        return None
    fixed = [shading.rim] if shading.rim is not None else []
    centres = fixed + _seed_colours(shading.fill, count - len(fixed))
    nearest: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    out = []
    for p in image.getdata():
        if p[3] < ALPHA_LOW:
            out.append(p)
            continue
        key = p[:3]
        if key not in nearest:
            nearest[key] = min(centres, key=lambda c: (sum((c[k]-key[k])**2 for k in range(3)), c))
        out.append((*nearest[key], p[3]))
    result = Image.new("RGBA", image.size)
    result.putdata(out)
    return extend_edge_colours(result)


def _apply_step(art: Image.Image, step: _Step) -> Image.Image | None:
    """The art after *step*, or None when the step would change nothing for this digit."""
    result = art
    if step.hard and any(0 < a < 255 for a in art.getchannel("A").getdata()):
        result = hard_edges(art)
        before, after = sum(art.getchannel("A").getdata()) / 255, sum(result.getchannel("A").getdata()) / 255
        if abs(after - before) > 0.10 * before:
            # Hard edges would lose a tenth of the digit's area: strokes thinner than a texel would vanish.
            return None
    if step.colours is not None:
        # Only shaded art (many fill shades, as a gradient has) is flattened, and never to fewer colours than it
        # has separate regions: an outline and flat patches are design, and merging them would change it.
        return flatten_shading(result, step.colours)
    return None if result is art else result


def _palette_floor(regions: int, banded: int | None) -> int:
    """Fewest palette entries worth trying. Below 16 only clean few-colour art qualifies.

    Two flat colours may go down to 8. Three or four are allowed 12 only after their shading was
    deliberately flattened by a reported step. Any other art keeps the 16-colour quality floor.
    """
    if 1 <= regions <= 2:
        return 8
    if banded is not None and 3 <= regions <= 4:
        return 12
    return 16


def _ladder(art, size, mode, mip_count, candidate, *, stream_tag, offset_bits, stored_size, attempts, step):
    """The registration-scale and palette ladder for one version of the art.

    Returns ``(fit, levels, factor, floor)``. ``fit`` is the first stream that fits, or None when none does;
    ``levels`` and ``floor`` then describe the smallest version that was tried. The faithful version
    (``step`` None) behaves exactly as it always has, so no digit that fitted before changes.
    """
    from nfl_tset_png_import import quantize_levels_to_vc_lz_bound, QualityBudgetError
    levels = prepared_mips(art, mip_count)
    # Below 16 entries only a clean few-colour input qualifies. Every opaque colour
    # remains protected; palette capacity is spent on coverage next.
    regions = sorted({c[:3] for c in art.getdata() if c[3] >= ALPHA_LOW})
    floor = _palette_floor(len(regions), step.colours if step is not None else None)
    flatten_smaller = floor < 16 if step is not None else floor == 8
    tag = {"simplification": step.name} if step is not None else {}
    factor = 1.0
    for factor in (1.0, 0.94, 0.88):
        if factor != 1.0:
            if mode == "as_authored":
                break
            bounds = art.getchannel("A").getbbox()
            shrunk = (max(1, round((bounds[2]-bounds[0])*factor)), max(1, round((bounds[3]-bounds[1])*factor)))
            smaller = Image.new("RGBA", size)
            left = (bounds[0]+bounds[2]-shrunk[0])//2
            top = (bounds[1]+bounds[3]-shrunk[1])//2
            smaller.paste(resize_cell(art.crop(bounds), shrunk), (left, top))
            smaller = one_texel_edge(bind_alpha(smaller))
            if step is not None and step.hard:
                smaller = hard_edges(smaller)
            if flatten_smaller:
                smaller = flatten_regions(smaller, regions)
            levels = prepared_mips(smaller, mip_count)
        try:
            fit = quantize_levels_to_vc_lz_bound(
                levels, lambda p, i: candidate(levels, p, i), stream_tag=stream_tag,
                offset_bits=offset_bits, max_encoded_size=stored_size,
                quantizer=edge_quantizer, minimum_palette_limit=floor,
                palette_limits=(256, 128, 64, 32, 16, 12, 8))
        except QualityBudgetError as exc:
            attempts.extend({**a, **tag, "registration_factor": factor} for a in getattr(exc, "attempts", ()))
            continue
        except ValidationError:
            # The quantizer cannot protect this many solid colours in the palette tier it reached (a gradient with
            # nine to sixteen shades is the usual case). That is "does not fit at this quality", not a bad sheet:
            # record it and let the next simplification try, instead of refusing the whole sheet or build.
            attempts.append({"maximum_palette_entries": floor, "palette_entries": None, "result": "too_many_colours",
                             **tag, "registration_factor": factor})
            return None, levels, factor, floor
        attempts.extend({**a, **tag, "registration_factor": factor} for a in fit.attempts)
        used = {fit.palette[i] for i in fit.index_levels[0] if fit.palette[i][3] >= ALPHA_LOW}
        if flatten_smaller and any(not any(max(abs(c[k]-region[k]) for k in range(3)) <= 24 for c in used)
                                   for region in regions):
            # Never accept a tier that lost a contrasting fill or outline.
            # A smaller image cannot restore a missing region either.
            return None, levels, factor, floor
        return fit, levels, factor, floor
    return None, levels, factor, floor


def _needed_bytes(levels, floor, candidate, *, stream_tag, offset_bits) -> int | None:
    """Encoded size of the smallest version the ladder tried, measured without a bound (None if it cannot be)."""
    try:
        from nfl_txtr import compress_vc_lz
        palette, indices, _ = edge_quantizer(levels, floor)
        stream, _info = compress_vc_lz(candidate(levels, palette, indices), stream_tag=stream_tag, offset_bits=offset_bits)
        return len(stream)
    except Exception:  # an unmeasured shortfall is reported as unmeasured, never invented
        return None


def fit_digit(image, retail, mode, mip_count, candidate, *, stream_tag, offset_bits, stored_size):
    """Bounded, shared preparation and encoding, including honest last resorts.

    The authored digit is fitted exactly as before. Only when that fails does the encoder try, in order,
    the reported simplifications in ``_STEPS``; each keeps both the fill and the outline. A digit that still
    cannot fit raises QualityBudgetError, carrying how many bytes its simplest version needs.
    """
    from nfl_tset_png_import import QualityBudgetError
    prepared, receipt = prepare_digit(image, retail, mode)
    attempts: list[dict] = []
    smallest = None  # (levels, floor) of the smallest version tried, for the measured shortfall
    for step in (None, *_STEPS):
        art = prepared if step is None else _apply_step(prepared, step)
        if art is None:
            continue
        fit, levels, factor, floor = _ladder(art, image.size, mode, mip_count, candidate, stream_tag=stream_tag,
                                             offset_bits=offset_bits, stored_size=stored_size, attempts=attempts, step=step)
        if fit is None:
            smallest = (levels, floor)
            continue
        receipt["fit"] = {"registration_factor": factor, "minimum_palette_budget": floor,
                          "two_tone": floor == 8, "attempts": attempts,
                          "written_box": measure(Image.frombytes("RGBA", image.size, levels[0].rgba))["box"]}
        if step is not None:
            receipt["fit"]["simplified"] = {"name": step.name, "text": step.text}
        return replace(fit, attempts=tuple(attempts)), levels, receipt
    error = QualityBudgetError(kept_retail_reason(stored_size))
    error.attempts = tuple(attempts)
    error.preparation = receipt
    error.stored_size = stored_size
    error.needed_bytes = (_needed_bytes(*smallest, candidate, stream_tag=stream_tag, offset_bits=offset_bits)
                          if smallest else None)
    error.advice = kept_retail_advice(stored_size=stored_size, needed=error.needed_bytes,
                                      colours=receipt.get("cleanup", {}).get("final_visible_rgb"))
    raise error
