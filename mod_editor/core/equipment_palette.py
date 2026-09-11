"""Equipment palettes keep authored colours instead of averaging them to grey."""
from collections import Counter
from functools import lru_cache
from math import sqrt


def distance(left, right):
    # Compare visible colour and coverage; stored values remain straight RGBA.
    return sum((left[i] * left[3] - right[i] * right[3]) ** 2 for i in range(3)) + (255 * (left[3] - right[3])) ** 2


def representatives(histogram, maximum):
    """Weighted median-cut regions, represented by real input colours (medoids)."""
    if len(histogram) <= maximum:
        return sorted(histogram)
    if maximum == 1:
        return [min(histogram, key=lambda c: (-histogram[c], c))]
    if maximum <= 8:
        # At very small budgets a centroid of black and white is precisely
        # the washed-out grey the importer must avoid. Keep the dominant
        # colour, then frequent colours farthest from those already retained.
        palette = [min(histogram, key=lambda c: (-histogram[c], c))]
        while len(palette) < maximum:
            palette.append(max((c for c in histogram if c not in palette),
                               key=lambda c: (sqrt(histogram[c]) * min(distance(c, p) for p in palette), c)))
        return sorted(palette)
    from nfl_tset_png_import import median_cut_palette
    # Explicitly retain the most common colours. Remaining regions choose an
    # authored colour nearest their centroid, never the desaturated centroid.
    anchors = sorted(histogram, key=lambda c: (-histogram[c], c))[:max(1, maximum // 4)]
    remaining = Counter({c: n for c, n in histogram.items() if c not in anchors})
    palette = list(anchors)
    for centroid in median_cut_palette(remaining, maximum - len(anchors)):
        color = min(remaining, key=lambda c: (distance(c, centroid), -remaining[c], c))
        if color not in palette:
            palette.append(color)
    return sorted(palette)


def quantize(levels, maximum):
    pixels = [[tuple(level.rgba[i:i + 4]) for i in range(0, len(level.rgba), 4)] for level in levels]
    base = Counter(pixels[0])
    hist = Counter(c for row in pixels for c in row)
    if len(base) <= maximum:
        # Newly filtered mip shades must never evict an exact P8 base colour.
        palette = sorted(base)
        extra = Counter({c: n for c, n in hist.items() if c not in base})
        room = maximum - len(palette)
        if room:
            palette.extend(representatives(extra, room))
    else:
        palette = representatives(hist, maximum)
    exact = {c: i for i, c in enumerate(palette)}
    mapping = {c: exact[c] if c in exact else min(range(len(palette)), key=lambda i: (distance(c, palette[i]), i)) for c in hist}
    indices = [bytes(mapping[c] for c in row) for row in pixels]
    actual = b"".join(bytes(palette[i]) for i in indices[0])
    return palette, indices, quality(levels[0].rgba, actual)


@lru_cache(maxsize=8192)
def _lab(color):
    rgb = [v / 255 for v in color[:3]]
    r, g, b = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    xyz = ((.4124564*r + .3575761*g + .1804375*b) / .95047,
           .2126729*r + .7151522*g + .0721750*b,
           (.0193339*r + .1191920*g + .9503041*b) / 1.08883)
    x, y, z = [v ** (1/3) if v > (6/29)**3 else v / (3*(6/29)**2) + 4/29 for v in xyz]
    return 116*y - 16, 500*(x-y), 200*(y-z)


def quality(requested, actual):
    pairs = Counter((tuple(requested[i:i+4]), tuple(actual[i:i+4])) for i in range(0, len(requested), 4))
    merges = [{"from_rgba": list(a), "to_rgba": list(b), "pixels": n} for (a, b), n in sorted(pairs.items()) if a != b]
    total = len(requested) // 4
    deltas = [(sqrt(sum((x-y)**2 for x, y in zip(_lab(a), _lab(b)))), n) for (a, b), n in pairs.items()]
    return {"maximum_channel_error": max((max(abs(x-y) for x,y in zip(a,b)) for a,b in pairs), default=0),
            "mean_delta_e76": sum(d*n for d,n in deltas) / total if total else 0.0,
            "maximum_delta_e76": max((d for d,n in deltas), default=0.0),
            "merged_colours": merges}


def merge_message(quality):
    merges = quality.get("merged_colours", [])
    if not merges:
        return ""
    def colour(values):
        return "#" + "".join(f"{value:02X}" for value in values)
    return (" Colours merged " + quality["merge_reason"] + ": "
            + "; ".join(f'{colour(row["from_rgba"])} -> {colour(row["to_rgba"])} ({row["pixels"]} pixels)' for row in merges) + ".")
