"""Measure the ESPN Analytics '4th Down Recommendation, Typical situations' chart (Seth Walder, ESPN, 2022-01) per yards to go.

Usage (the image is ESPN's, not redistributed here; see docs/mod_editor/nfl2k5_cpu_decisions_modern2_sources.json for the URL):

    python3 -I digitize_espn4th.py r961387_1295x1617cc.jpg

For each yards-to-go row 1..10 (the horizontal gridline of the chart) prints the colour runs Go (red), FG (blue), Punt (grey) along the x axis,
converted to 'yards to the opponent end zone' with the x ticks (0 at pixel 332, 100 at pixel 1179.5). The chart is a step chart whose boundaries sit on whole
yards, so every boundary is ambiguous by one yard; ``build_tables.py`` keeps the runs below (copied from an earlier pass of this script; this version
agrees with them to within 0.2 yard at every boundary and yields the identical whole-yard go windows, nominal and shipped) and pulls every window edge in by one yard.
Pillow and numpy are needed (analysis only, never a runtime dependency).
"""
import json
import sys

import numpy as np
from PIL import Image

img = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(int)
X0, SCALE = 332.0, (1179.5 - 332.0) / 100.0       # x tick marks of the published image
GRID = {d: 1134.5 - (d - 1) * 71.0 for d in range(1, 11)}   # y of the gridline of each yards-to-go


def classify(px):
    r, g, b = px
    if abs(r - 196) < 40 and g < 80 and b < 90:
        return "G"
    if r < 60 and g > 140 and b > 200:
        return "F"
    if abs(r - g) < 14 and abs(g - b) < 14 and 70 < r < 120:
        return "P"
    return "."


def runs(y, minlen=0.5, label_gap=14.0):
    """Colour runs along row y; runs of one colour split only by the chart's own text labels ('Go', 'FG', 'Punt') are merged."""
    out, cur, start = [], None, 320
    for x in range(320, 1260):
        c = classify(img[y, x])
        if c != cur:
            if cur not in (None, "."):
                out.append([cur, (start - X0) / SCALE, (x - X0) / SCALE])
            cur, start = c, x
    merged = []
    for kind, a, b in out:
        if merged and merged[-1][0] == kind and a - merged[-1][2] <= label_gap:
            merged[-1][2] = b
        else:
            merged.append([kind, a, b])
    return [(k, round(a, 1), round(b, 1)) for k, a, b in merged if b - a >= minlen]


print(json.dumps({str(d): runs(int(round(y))) for d, y in GRID.items()}, indent=1))
