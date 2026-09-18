"""Unmodified rc97 quantizer, retained only as a byte identity oracle."""
from collections import Counter
from mod_editor.core.nfl2k5_uniform_equipment_writer import palette_tools

def quantize_art(levels, maximum):
    """Median cut of actual base artwork; nearest-colour mapping, no dither.

    Keep an already representable base exact. Filtered distance colours use
    remaining entries, and cannot replace a base colour. Under pressure, use
    weighted median-cut regions of the base (never a fixed colour ramp).
    """
    from mod_editor.core.equipment_palette import distance, quality
    pixels = [[tuple(level.rgba[i:i + 4]) for i in range(0, len(level.rgba), 4)]
              for level in levels]
    base = Counter(pixels[0])
    histogram = Counter(c for row in pixels for c in row)
    def medoids(hist, limit):
        if len(hist) <= limit:
            return sorted(hist)
        return sorted(set(min(hist, key=lambda c: (distance(c, centre), -hist[c], c))
                          for centre in palette_tools.median_cut_palette(hist, limit)))
    if len(base) <= maximum:
        palette = sorted(base)
        room = maximum - len(palette)
        if room:
            palette += medoids(Counter({c: n for c, n in histogram.items() if c not in base}), room)
    else:
        palette = medoids(base, maximum)
    exact = {c: i for i, c in enumerate(palette)}
    mapping = {c: exact[c] if c in exact else min(range(len(palette)),
               key=lambda i: (distance(c, palette[i]), i)) for c in histogram}
    indices = [bytes(mapping[c] for c in row) for row in pixels]
    actual = b"".join(bytes(palette[i]) for i in indices[0])
    return palette, indices, quality(levels[0].rgba, actual)

