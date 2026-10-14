#!/usr/bin/env python3
"""uf2 (b772): author the 2026 alternate, throwback and Rivalries kit fixes for ``data/nfl2k5_kit_fixes_2026_alts.json``.

Job uw2 captured the selectable non-primary kits in xemu and compared them with dated 2025/26 club photos; job uf2
checked every finding against the crop, the game frame, the dated photo and the decoded native texture, and authored
the real ones here. The data drives the same Studio pass as uf1 (``mod_editor/core/nfl2k5_kit_fixes_2026.py``,
``apply_alternates``): native-texel vector art drawn at 4x, inner rings and outside halos measured from the art,
stamps of art already in the same kit, palette-only recolours (name plate, digits), cleared shoulder digits and the
Unif facemask colour.

  uf2_author.py preview --export EXPORT_DIR --out DIR [SELECTOR ...]   level 0 painted onto exported kit PNGs
  uf2_author.py data --input DISC.iso [--out data/nfl2k5_kit_fixes_2026_alts.json]

``EXPORT_DIR`` is a ``tools/b765/u1_audit.py`` export (uniforms/<selector>/*.png). Game-derived files stay outside the
repository; only the vector art, the recolour maps and the hashes go into the data file.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
import uf1_author as uf1  # noqa: E402

DATA = fixes.DATA_ALTS
CODES = {"ARI": "00", "ATL": "01", "BAL": "02", "BUF": "03", "CAR": "04", "CHI": "05", "CIN": "06", "DAL": "07",
         "DEN": "08", "DET": "09", "GB": "10", "IND": "11", "JAX": "12", "KC": "13", "MIA": "14", "MIN": "15",
         "NE": "16", "NO": "17", "NYG": "18", "NYJ": "19", "LV": "20", "PHI": "21", "PIT": "22", "LAR": "23",
         "LAC": "24", "SF": "25", "SEA": "26", "TB": "27", "TEN": "28", "WAS": "29", "CLE": "30", "HOU": "37"}
PNG = {1: "torso.png", 2: "pants.png", 3: "sleeve.png", 4: "socks00.png", 12: "helmet_helmet02.png",
       43: "names.png", 49: "logo.png"}
for _d in range(10):
    PNG[13 + _d] = f"digit_jersey_{_d}.png"
    PNG[23 + _d] = f"digit_helmet_{_d}.png"
    PNG[33 + _d] = f"digit_arm_{_d}.png"
NAMES = {1: "jersey00", 2: "pants00", 3: "sleeve00", 4: "socks00", 12: "helmet02", 43: "names", 49: "logo"}
TSET = (1, 2, 3, 4)
JERSEY_DIGITS = tuple(range(13, 23))
ARM_DIGITS = tuple(range(33, 43))
W = "#FFFFFF"

rect, poly, copy, sleeve_bands, stack = uf1.rect, uf1.poly, uf1.copy, uf1.sleeve_bands, uf1.stack
pants_stripe, chevrons, offset_polygon = uf1.pants_stripe, uf1.chevrons, uf1.offset_polygon
LEGS = (142, 369)


def chunk_name(chunk):
    if chunk in NAMES:
        return NAMES[chunk]
    family, prefix = (("jersey", ""), ("helmet", "hn"), ("arm", "an"))[(chunk - 13) // 10]
    return "%s%d" % (prefix, 48 + (chunk - 13) % 10)


# -- shape helpers ---------------------------------------------------------------------------------------------------

def mirror(x):
    """Sleeve island 1 (left arm, rows 64-127) is island 0 mirrored left to right."""
    return 127.0 - x


def on_both_arms(points_fn):
    """``points_fn(top, col)`` -> ops for one island; returns the ops for both (island 1 mirrored)."""
    return points_fn(0, lambda x: x) + points_fn(64, mirror)


def clip(points, x0, y0, x1, y1):
    """Sutherland-Hodgman clip of a polygon to an axis-aligned rectangle."""
    def cut(pts, inside, inter):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            if inside(b):
                if not inside(a):
                    out.append(inter(a, b))
                out.append(b)
            elif inside(a):
                out.append(inter(a, b))
        return out

    def ix(xc):
        return lambda a, b: (xc, a[1] + (b[1] - a[1]) * (xc - a[0]) / (b[0] - a[0]))

    def iy(yc):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yc - a[1]) / (b[1] - a[1]), yc)

    pts = list(points)
    for inside, inter in ((lambda q: q[0] >= x0, ix(x0)), (lambda q: q[0] <= x1, ix(x1)),
                          (lambda q: q[1] >= y0, iy(y0)), (lambda q: q[1] <= y1, iy(y1))):
        pts = cut(pts, inside, inter)
        if not pts:
            break
    return pts


def circle(cx, cy, r, colour, n=24):
    return poly([(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)],
                colour)


def ellipse(cx, cy, rx, ry, colour, n=32):
    return poly([(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
                 for i in range(n)], colour)


def star(cx, cy, r, colour, inner=0.42, rot=-90.0):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * inner
        a = math.radians(rot + 36 * i)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return poly(pts, colour)


def recolor(box, sources, colour, tolerance=24, **extra):
    return dict({"op": "recolor", "box": list(box), "from": list(sources), "color": colour, "tolerance": tolerance},
                **extra)


def clear_box(box, cloth, tolerance=12):
    """Repaint every texel in ``box`` that is not the cloth colour with the cloth colour (removes old art)."""
    return recolor(box, [cloth], cloth, tolerance, invert=True)


def ring(box, inside, frm, to, colour, tolerance=24, **extra):
    return dict({"op": "ring", "box": list(box), "inside": inside, "from": frm, "to": to, "color": colour,
                 "tolerance": tolerance}, **extra)


def halo(box, edge, radius, colour, tolerance=24, **extra):
    return dict({"op": "halo", "box": list(box), "edge": list(edge), "radius": radius, "color": colour,
                 "tolerance": tolerance}, **extra)


def grow(box, sources, colour, radius, into=("*",), tolerance=24, **extra):
    return dict({"op": "grow", "box": list(box), "from": list(sources), "into": list(into), "color": colour,
                 "radius": radius, "tolerance": tolerance}, **extra)


def flood(seed, box, colour, tolerance=24):
    return {"op": "flood", "seed": list(seed), "box": list(box), "color": colour, "tolerance": tolerance}


def enclosed(box, edge, colour, tolerance=24):
    return {"op": "enclosed", "box": list(box), "edge": list(edge), "color": colour, "tolerance": tolerance}


def stamp(src, dst, donor="self", **extra):
    return dict({"op": "stamp", "donor": donor, "src": list(src), "dst": list(dst)}, **extra)


def taper_stripe(c, segments, colour):
    """Pants talon stripe centred on seam column ``c``: ``segments`` are (y_top, half_top, y_bottom, half_bottom)
    quads; a slanted cut is made by giving the top or bottom edge an offset with (y_left, y_right) tuples."""
    ops = []
    for y0, h0, y1, h1 in segments:
        a0, b0 = (y0, y0) if not isinstance(y0, tuple) else y0
        a1, b1 = (y1, y1) if not isinstance(y1, tuple) else y1
        ops.append(poly([(c - h0, a0), (c + h0, b0), (c + h1, b1), (c - h1, a1)], colour))
    return ops


def bolt_path(x0, x1, y0, y1, teeth, depth):
    """Lightning bolt centre-line polygon from (x0, y0) to (x1, y1) with ``teeth`` angular steps: returns a polygon
    whose half width tapers from ``depth`` to a point."""
    pts_l, pts_r = [], []
    for i in range(teeth + 1):
        t = i / teeth
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        half = depth * (1.0 - 0.85 * t)
        pts_l.append((x - half, y))
        pts_r.append((x + half, y))
    return pts_l, pts_r


# -- glyphs (5 x 7 block letters, rectangles) --------------------------------------------------------------------------

LETTERS = {
    "B": [(0, 0, 1.6, 7), (0, 0, 4.2, 1.4), (0, 2.8, 4.2, 4.2), (0, 5.6, 4.2, 7), (3.4, 0.6, 5, 3.0),
          (3.4, 4.0, 5, 6.4)],
    "U": [(0, 0, 1.6, 7), (3.4, 0, 5, 7), (0, 5.6, 5, 7)],
    "F": [(0, 0, 1.6, 7), (0, 0, 5, 1.4), (0, 2.8, 4, 4.2)],
    "A": [(0, 0.8, 1.6, 7), (3.4, 0.8, 5, 7), (0.6, 0, 4.4, 1.4), (0, 3.2, 5, 4.6)],
    "L": [(0, 0, 1.6, 7), (0, 5.6, 5, 7)],
    "O": [(0, 0.6, 1.6, 6.4), (3.4, 0.6, 5, 6.4), (0.6, 0, 4.4, 1.4), (0.6, 5.6, 4.4, 7)],
    "N": [(0, 0, 1.6, 7), (3.4, 0, 5, 7)],
    "E": [(0, 0, 1.6, 7), (0, 0, 5, 1.4), (0, 2.8, 4, 4.2), (0, 5.6, 5, 7)],
    "G": [(0, 0.6, 1.6, 6.4), (0.6, 0, 5, 1.4), (0.6, 5.6, 4.4, 7), (3.4, 3.4, 5, 6.4), (2.6, 3.0, 5, 4.3)],
    "S": [(0.6, 0, 5, 1.4), (0, 0.6, 1.6, 3.6), (0.6, 2.8, 4.4, 4.2), (3.4, 3.4, 5, 6.4), (0, 5.6, 4.4, 7)],
    "H": [(0, 0, 1.6, 7), (3.4, 0, 5, 7), (0, 2.8, 5, 4.2)],
}


def word(text, x, y, height, colour, gap=0.8, serif=0.0):
    unit = height / 7.0
    ops = []
    for ch in text:
        for x0, y0, x1, y1 in LETTERS[ch]:
            ops.append(rect(x + x0 * unit, y + y0 * unit, x + x1 * unit, y + y1 * unit, colour))
        if serif:
            ops.append(rect(x - serif * unit, y, x + 5 * unit + serif * unit, y + 0.9 * unit, colour)) if ch in "" \
                else None
        x += (5 + gap) * unit
    return [op for op in ops if op]


def word_width(text, height, gap=0.8):
    unit = height / 7.0
    return (len(text) * (5 + gap) - gap) * unit


def n_slant(x, y, height, colour):
    """The N's diagonal (the block-letter table holds only its two posts)."""
    unit = height / 7.0
    return [poly([(x + 0.4 * unit, y), (x + 2.0 * unit, y), (x + 4.6 * unit, y + 7 * unit),
                  (x + 3.0 * unit, y + 7 * unit)], colour)]


def bolts_on_torso(cloth, layers, clear_tolerance=10):
    """The four shoulder bolts of the 2026 Chargers torso template (uf1's measured paths), broad with two angular
    steps; ``layers`` are (outward offset, colour) from the outermost border to the bolt itself (offset 0)."""
    ops = []
    for (x0, slope, length, direction), box in zip(uf1.BOLTS, [(60, 0, 104, 100), (220, 0, 266, 100),
                                                              (286, 0, 320, 100), (458, 0, 492, 100)]):
        ops.append(recolor(box, [cloth], cloth, clear_tolerance, invert=True))
        pts = [(x0 + slope * (y * length / 100.0) + direction * x, y * length / 100.0) for x, y in uf1.BOLT]
        for off, colour in layers:
            ops.append(poly(offset_polygon(pts, off) if off else pts, colour))
    return ops


def bolts_on_pants(cloth, layers):
    """A broad vertical lightning bolt down each pants seam (the uf1 bolt shape stretched along the leg)."""
    ops = []
    for c in LEGS:
        ops.append(recolor((c - 16, 6, c + 16, 256), [cloth], cloth, 12, invert=True))
        pts = [(c + 0.78 * x, 12.0 + 2.3 * y) for x, y in uf1.BOLT]
        for off, colour in layers:
            ops.append(poly(offset_polygon(pts, off) if off else pts, colour))
    return ops


def braid(cx, y0, y1, half, colour, step=6.0, width=1.3, vertical=True):
    """A simple interlaced knot chain: two zigzag strands crossing every ``step`` texels."""
    ops = []
    y = y0
    k = 0
    while y + step <= y1 + 0.01:
        a, b = (cx - half, cx + half) if k % 2 == 0 else (cx + half, cx - half)
        for xa, xb in ((a, b), (b, a)):
            pts = [(xa, y), (xa + (width if xa < xb else -width), y), (xb, y + step),
                   (xb - (width if xa < xb else -width), y + step)]
            if not vertical:
                pts = [(py, px) for px, py in pts]
            ops.append(poly(pts, colour))
        y += step
        k += 1
    return ops


# -- recipes ---------------------------------------------------------------------------------------------------------

def recipes():
    """selector -> list of items. Items:
    ("tex", chunk, ops, defects, note[, extra])  P8 art (TSET jersey/pants/sleeve/socks, TXTR helmet/digits)
    ("palette", chunk, map, defects, note)       palette-only recolour (name plate, digits)
    ("clear", chunk, defects, note)              shoulder (TV) digit cleared
    ("unif", fields, defects, note)              Unif colour fields
    """
    R = {}

    def add(team, style, sides, item):
        kind = item[0]
        if kind == "tex":
            _, chunk, payload, suffixes, note = item[:5]
            extra = item[5] if len(item) > 5 else {}
        elif kind == "palette":
            _, chunk, payload, suffixes, note = item
            extra = {}
        elif kind == "clear":
            _, chunk, suffixes, note = item
            payload, extra = None, {}
        else:
            _, payload, suffixes, note = item
            chunk, extra = 0, {}
        for side in sides:
            sel = CODES[team] + ("H" if side == "home" else "A") + str(style)
            ids = ["uw2-%s-%s-%d-%s" % (team, side, style, s) for s in suffixes]
            R.setdefault(sel, []).append((kind, chunk, payload, ids, note, json.loads(json.dumps(extra))))

    both = ("home", "away")

    def digits(team, style, sides, mapping, suffixes, note, chunks=JERSEY_DIGITS):
        for c in chunks:
            add(team, style, sides, ("palette", c, mapping, suffixes, note))

    def digit_art(team, style, sides, ops, suffixes, note, chunks=JERSEY_DIGITS):
        for c in chunks:
            add(team, style, sides, ("tex", c, ops, suffixes, note, {"mip": "mode"}))

    def clear_tv(team, style, sides, suffixes, note):
        for c in ARM_DIGITS:
            add(team, style, sides, ("clear", c, suffixes, note))

    def names(team, style, sides, colour, suffixes, note, sources=("#FFFFFF",), tolerance=40):
        add(team, style, sides, ("palette", 43, [{"from": list(sources), "to": colour, "tolerance": tolerance}],
                                 suffixes, note))

    # ARI style 6: 2025 black alternate (dated Oct 5 2025 photos) ---------------------------------------------------
    ari_red, ari_black = "#A0233F", "#17171A"
    digits("ARI", 6, both, [{"from": ["#A9AEB3", "#BEC2C6"], "to": "#F2F2F2", "tolerance": 24},
                            {"from": ["#FFFFFF", "#D9DCDF"], "to": ari_red, "tolerance": 40}],
           ["number-color"], "red numerals with a pale border (were white with a silver edge)")
    add("ARI", 6, both, ("tex", 1, [clear_box((126, 83, 196, 97), ari_black)], ["chest-wordmark"],
                         "the ARIZONA chest wordmark removed: the black alternate is plain above the numbers"))
    add("ARI", 6, both, ("tex", 3, stack(ari_black, [(2, ari_red), (1, None), (9, "#E6E7E8"), (1, None),
                                                     (2, ari_red)], start=18, clear=(34, 54)) +
                         [copy((45, 42, 82, 47), (45, 23), skip_col=20), copy((45, 106, 82, 111), (45, 87), skip_col=20)],
                         ["sleeve-bands"], "red-bordered pale CARDINALS band moved up from the hem and lightened"))

    # ARI style 7: 2025 Rivalries white-sand kit (dated Sept 25 2025 game photos) -----------------------------------
    copper = "#B87333"
    digit_art("ARI", 7, both, [ring((0, 0, 64, 64), "opaque", 0, 1.5, copper)], ["number-bevel"],
              "broad copper edge on the red numerals")
    add("ARI", 7, both, ("tex", 1, [stamp((0, 0, 128, 128), (382.0, 45.0, 402.0, 60.0), donor=49)], ["rear-collar-bird"],
                         "small cardinal head centred under the back collar (the kit's own team logo art)",
                         {"donors": {"49": None}}))
    def az_flag(top, col):
        cx, y0, wd, ht = col(71.0), top + 16.0, 12.0, 9.0
        x0 = cx - wd / 2
        ops = [rect(x0 - 0.7, y0 - 0.7, x0 + wd + 0.7, y0 + ht + 0.7, "#1A1A1A"),
               rect(x0, y0, x0 + wd, y0 + ht / 2, "#C8102E"), rect(x0, y0 + ht / 2, x0 + wd, y0 + ht, "#1A1A1A")]
        ox, oy = x0 + wd / 2, y0 + ht / 2
        for i in range(0, 13, 2):
            a0 = math.pi + math.pi * i / 13
            a1 = math.pi + math.pi * (i + 1) / 13
            wedge = [(ox, oy), (ox + 20 * math.cos(a0), oy + 20 * math.sin(a0)),
                     (ox + 20 * math.cos(a1), oy + 20 * math.sin(a1))]
            ops.append(poly(clip(wedge, x0, y0, x0 + wd, y0 + ht / 2), "#F2A33A"))
        ops.append(star(ox, oy, 2.4, "#D9733A", inner=0.45))
        return ops
    add("ARI", 7, both, ("tex", 3, on_both_arms(az_flag), ["sleeve-flag"],
                         "Arizona flag patch (red and copper rays over black, copper star) below the swoosh"))

    # ATL style 9: 1966 black throwback (dated Oct 10 2025 reveal) ---------------------------------------------------
    neutral = ["#%02X%02X%02X" % (g, g, g) for g in range(0, 256, 8)] + ["#FFFFFF"]
    def falcon(top, col):
        xa, xb = sorted((col(37.0), col(71.0)))
        box = (int(xa), top + 13, int(xb) + 1, top + 58)
        return [{"op": "close", "box": list(box), "colors": neutral, "tolerance": 4, "radius": 2.6,
                 "color": "#050505", "into": ["#11111B"], "into_tolerance": 14},
                recolor(box, ["#A4A4A4", "#888888", "#C0C0C0", "#D8D8D8"], W, 28),
                halo(box, neutral, 1.0, W, 4),
                halo(box, neutral, 2.3, "#A6192E", 4, into=["#11111B"], into_tolerance=14)]
    add("ATL", 9, both, ("tex", 3, on_both_arms(falcon), ["sleeve-crest"],
                         "falcon outlined boldly in white then red, feather lines white"))
    add("ATL", 9, both, ("tex", 4, [rect(0, 0, 64, 64, "#0F0F0F"), rect(0, 41, 64, 45.5, "#A6192E")],
                         ["sock-pattern"], "black socks with red trim just above the shoe"))

    # BAL style 2: 2026 Purple Rising (home) and White Noise (away), April 16 2026 unveil, Sept 20 2026 game ----------
    bpurple, bgold, bdark = "#2E1667", "#C9A23A", "#1C0D40"
    digit_art("BAL", 2, ("home",), [ring((0, 0, 64, 64), "opaque", 1.45, 2.7, bdark),
                                    ring((0, 0, 64, 64), "opaque", 0, 1.45, W)],
              ["number-outline"], "gold numerals with a dark inner edge and a white outer outline")
    def talon(c, colour):
        return taper_stripe(c, [((12, 12), 8.5, (30, 40), 8.5), ((40, 50), 8.5, 140, 6.0), (140, 6.0, 238, 0.6)],
                            colour)
    home_pants = [rect(131, 0, 153, 256, bpurple), rect(358, 0, 380, 256, bpurple)]
    for c in LEGS:
        home_pants += talon(c, "#C9A23A")
    add("BAL", 2, ("home",), ("tex", 2, home_pants, ["pants-talons"],
                              "broad gold segmented talon stripe tapering down the purple pants"))
    away_pants = [rect(131, 0, 153, 256, W), rect(358, 0, 380, 256, W)]
    for c in LEGS:
        away_pants += talon(c, "#2E1667")
    add("BAL", 2, ("away",), ("tex", 2, away_pants, ["pants-talons"],
                              "broad purple talon panel with a gap near the hip and a long taper"))
    def bal_shield(top, col):
        xa, xb = sorted((col(42.0), col(79.0)))
        box = (int(xa), top + 15, int(xb) + 1, top + 52)
        return [recolor(box, ["#C8102E", "#E03040", "#B01020", "#D02838"], "#4B2E83", 40, match="original"),
                recolor(box, ["#FBF9F8", "#FFFFFF", "#E8E8E8"], bgold, 30, match="original"),
                recolor(box, ["#907CB6", "#B8ABD0", "#A090C8"], bgold, 24, match="original"),
                recolor(box, ["#E2AF0E", "#F0C020", "#D0A010"], "#D7B04A", 30, match="original")]
    add("BAL", 2, ("home",), ("tex", 3, on_both_arms(bal_shield), ["sleeve-crest"],
                              "sleeve shield in the Purple Rising purple and metallic gold"))
    add("BAL", 2, ("away",), ("tex", 3, sleeve_bands([(50, 57.5, bpurple)], cloth=W), ["cuff-bands"],
                              "purple band around the sleeve cuff"))

    # BAL style 3: 2026 Darkness (black) -----------------------------------------------------------------------------
    dark_pants = [rect(131, 0, 153, 256, "#0E0E10"), rect(358, 0, 380, 256, "#0E0E10")]
    for c in LEGS:
        dark_pants += talon(c, "#4B2E9A")
    add("BAL", 3, both, ("tex", 2, dark_pants, ["pants-talons"],
                         "broad purple segmented talon panels with a gap at the upper thigh, tapering below"))

    # BUF style 3: red alternate (Dec 28 2025) -------------------------------------------------------------------------
    bred, broyal = "#D4112B", "#0B3A9E"
    add("BUF", 3, both, ("tex", 3, stack(bred, [(1.5, broyal), (5.5, W), (1.5, broyal), (3, None), (1.5, broyal),
                                                (5.5, W), (1.5, broyal)], start=18, clear=(33, 55)),
                         ["sleeve-bands"], "two blue-outlined white bands with a red gap, moved up from the hem"))

    # BUF style 8: 2026 Nickel City (gray) ---------------------------------------------------------------------------
    digit_art("BUF", 8, both, [ring((0, 0, 64, 64), ["#0B3A9E"], 0, 1.6, W, 30)], ["number-border"],
              "blue numerals outlined white inside the red edge")
    add("BUF", 8, both, ("tex", 1, [grow((118, 0, 190, 92), ["#0B3A9E", "#1A48A8", "#2A50A0"], broyal, 6.5,
                                         into=["#8D9096", "#9A9DA2", "#80838A"], tolerance=26)],
                         ["blue-collar"], "broad royal-blue V-neck panel around the NFL shield"))

    # BUF style 9: 2025 Cold Front Rivalries (white) -------------------------------------------------------------------
    bnavy = "#00338D"
    bw = word_width("BUFFALO", 11.0)
    add("BUF", 9, both, ("tex", 1, [clear_box((148, 89, 173, 97), "#F5F8FC", 30)] +
                         word("BUFFALO", 160.0 - bw / 2, 86.0, 11.0, bnavy),
                         ["chest-wordmark"], "blue BUFFALO wordmark above the front number (the small BILLS mark goes)"))
    def cold_buffalo(top, col):
        if top == 0:
            dst, src = (33.0, 9.0, 81.0, 37.0), (128, 14, 0, 114)
        else:
            dst, src = (46.0, 73.0, 94.0, 101.0), (0, 14, 128, 114)
        ice = []
        for k, (ax, ay, bx, by) in enumerate(((0.15, 0.30, 0.55, 0.62), (0.45, 0.15, 0.80, 0.55),
                                              (0.30, 0.70, 0.70, 0.40), (0.60, 0.80, 0.92, 0.45),
                                              (0.20, 0.45, 0.42, 0.20))):
            x0 = dst[0] + ax * (dst[2] - dst[0]); y0 = dst[1] + ay * (dst[3] - dst[1])
            x1 = dst[0] + bx * (dst[2] - dst[0]); y1 = dst[1] + by * (dst[3] - dst[1])
            ice.append(dict(poly([(x0, y0), (x1, y1), (x1 + 0.7, y1 + 0.5), (x0 + 0.7, y0 + 0.5)], "#9DB9DD"),
                            only=["#1F4E9A"], only_tolerance=30))
        return [recolor((int(dst[0]) - 2, int(dst[1]) - 2, int(dst[2]) + 2, int(dst[3]) + 2),
                        ["#DCE6F2", "#D9E3F0", "#E2EAF4"], "#F5F8FC", 10),
                stamp(src, dst, donor=49, skip=["#FFFFFF", "#F4F4F4"], tolerance=40,
                      remap=[{"from": ["#C60C30", "#D50A0A", "#E0203A"], "to": "#1F4E9A", "tolerance": 70},
                             {"from": ["#00338D", "#003A9E"], "to": "#1F4E9A", "tolerance": 60}])] + ice
    add("BUF", 9, both, ("tex", 3, on_both_arms(cold_buffalo), ["shoulder-graphics"],
                         "large blue cracked-ice buffalo on each sleeve (the kit's own buffalo art)",
                         {"donors": {"49": None}}))
    clear_tv("BUF", 9, both, ["shoulder-graphics"], "no shoulder (TV) numbers: the buffalo graphic takes the sleeve")
    cracks = []
    for k in range(9):
        y = 30 + k * 21.5
        xa, xb = (152.5, 171.5) if k % 2 == 0 else (171.5, 152.5)
        cracks.append(poly([(xa, y), (161.5 + (k % 3 - 1) * 2.0, y + 9.0), (xb, y + 17.0), (xb, y + 17.8),
                            (161.5 + (k % 3 - 1) * 2.0 + 0.8, y + 9.6), (xa, y + 0.9)], "#8C9BB2"))
        cracks.append(poly([(161.5 + (k % 3 - 1) * 2.0, y + 9.0), (161.5 + (k % 2) * 6 - 3, y + 15.0),
                            (161.5 + (k % 2) * 6 - 2.3, y + 15.0), (161.5 + (k % 3 - 1) * 2.0 + 0.7, y + 9.0)],
                           "#9EABC0"))
    add("BUF", 9, both, ("tex", 12, [rect(151, 23, 174, 222, "#CDD6E2")] + cracks, ["helmet-center"],
                         "pale metallic cracked-ice centre stripe edged in blue"))

    # CAR style 2: 2025 blue alternate (Sept 21 2025 game) -----------------------------------------------------------
    car_pants = []
    for c in LEGS:
        car_pants += [poly([(c - 9.5, 44), (c + 9.5, 44), (c + 5.0, 236), (c - 5.0, 236)], W),
                      poly([(c - 7.5, 44), (c + 7.5, 44), (c + 3.2, 234), (c - 3.2, 234)], "#0095CD")]
    add("CAR", 2, both, ("tex", 2, car_pants, ["pants-stripe"], "broad blue side panel outlined in white"))

    # CHI style 4: 2026 Rivalries (navy jersey, orange pants and helmet), Aug 25 2026 reveal -------------------------
    cnavy, corange = "#0D1A32", "#C83803"
    def bars(top, col):
        ops = [rect(0, top + 3, 128, top + 63, cnavy)]
        for cx in (33.5, 63.5, 93.5):
            ops += [rect(cx - 7.5, top + 15, cx + 7.5, top + 62, W), rect(cx - 5.5, top + 15, cx + 5.5, top + 62,
                                                                           corange)]
        for a, b, r0, r1 in ((68.0, 85.0, 0, 16), (61.5, 68.0, 0, 7)):
            xa, xb = sorted((col(a), col(b)))
            ops.append(copy((int(round(xa)), top + r0, int(round(xb)), top + r1), (int(round(xa)), top + r0),
                            skip=cnavy, tolerance=30))
        return ops
    add("CHI", 4, both, ("tex", 3, on_both_arms(bars), ["sleeve-bars"],
                         "three broad white-edged orange bars running up the sleeve"))
    clear_tv("CHI", 4, both, ["sleeve-bars"], "no shoulder (TV) numbers in the barred sleeve")
    gw = word_width("GSH", 6.5)
    add("CHI", 4, both, ("tex", 1, [clear_box((186, 66, 224, 92), cnavy, 20), ellipse(204.0, 79.0, 12.2, 8.0, W),
                                    ellipse(204.0, 79.0, 10.6, 6.6, corange)] +
                         word("GSH", 204.0 - gw / 2, 75.75, 6.5, cnavy),
                         ["gsh-chest"], "broad orange football-shaped GSH patch outlined white on the left chest"))
    def bear_c(boxes):
        shell = ["#D14F18", "#C9511F", "#D84E17", "#BA4718", "#AB3F1D"]
        ops = [{"op": "enclosed", "box": [42, 56, 118, 110], "edge": shell, "color": "#0B162A", "tolerance": 34,
                "invert": True},
               {"op": "enclosed", "box": [42, 144, 118, 202], "edge": shell, "color": "#0B162A", "tolerance": 34,
                "invert": True}]
        for box in boxes:
            ops.append(recolor(box, shell, "#0B162A", 40, invert=True))
        for box in boxes:
            ops.append({"op": "close", "box": list(box), "colors": ["#0B162A"], "tolerance": 20, "radius": 1.6,
                        "color": "#0B162A", "into": shell, "into_tolerance": 40})
        for box in boxes:
            ops.append(ring(box, shell, 0, 1.3, W, 40, invert=True))
        return ops
    add("CHI", 4, both, ("tex", 12, bear_c([(47, 62, 100, 103), (100, 62, 107, 95), (47, 150, 100, 194),
                                            (100, 162, 107, 194)]), ["helmet-c"],
                         "solid navy C strokes bordered in white"))
    add("CHI", 4, both, ("tex", 2, pants_stripe(LEGS, [(6.5, cnavy), (3.0, W), (6.5, cnavy)], clear=(corange, 6)),
                         ["pants-panel"], "broad navy side panel with a white centre stripe"))

    # CIN styles 5 and 6: 2025 White Bengal (black tiger stripes) and 2026 white/orange alternate --------------------
    def tiger(colour, cloth, old):
        ops = []
        for c, sign in ((142.0, 1.0), (369.0, -1.0)):
            x0, x1 = (c - 22, c + 24) if sign > 0 else (c - 24, c + 22)
            ops.append(recolor((int(x0), 0, int(x1) + 1, 256), old, cloth, 60))
            y = 14.0
            while y < 236:
                base = c - sign * 16.0
                tip = c + sign * 21.0
                ops.append(poly([(base, y), (c + sign * 2.0, y - 3.5), (tip, y - 10.0), (c + sign * 3.0, y + 3.0),
                                 (base, y + 13.0), (base - sign * 4.0, y + 7.0)], colour))
                y += 22.0
        return ops
    add("CIN", 5, ("away",), ("tex", 2, tiger("#101010", W, ["#000000", "#101010", "#202020", "#808080"]),
                              ["pants-tiger-stripes"], "broad black tiger shapes with narrow white gaps"))
    add("CIN", 6, both, ("tex", 2, tiger("#FA5014", W, ["#FA5014", "#F86A3A", "#FBA080", "#E04010"]),
                         ["pants-tiger-stripes"], "broad orange tiger shapes with narrow white gaps"))

    # DAL style 7: 2026 Arctic (white with navy sleeves) ------------------------------------------------------------
    dnavy = "#002244"
    digit_art("DAL", 7, both, [ring((0, 0, 64, 64), "opaque", 1.4, 2.8, W)], ["number-outlines"],
              "navy numerals with a white inner border and a navy outer outline")
    def arctic_star(top, col):
        xa, xb = sorted((col(42.0), col(102.0)))
        box = (int(xa), top + 4, int(xb), top + 50)
        return [recolor(box, ["#798A9C", "#768799", "#5A6C80", "#9CB0C0", "#B8C8D4"], W, 30),
                halo(box, [W], 0.9, W, 20, into=[dnavy, "#183655"], into_tolerance=30)]
    add("DAL", 7, both, ("tex", 3, on_both_arms(arctic_star), ["shoulder-star"],
                         "navy shoulder star clearly outlined in white"))

    # DAL style 9: 2025 Thanksgiving throwback ---------------------------------------------------------------------
    digits("DAL", 9, both, [{"from": ["#808080"], "to": W, "tolerance": 255}], ["number-fill"],
           "plain solid white numerals (the extra navy and white outlines go)")
    tstars = [(95, 24), (225, 26), (330, 14), (460, 24)]
    star_ops = []
    for x, y in tstars:
        star_ops.append(flood((x, y), (max(x - 40, 0), 0, min(x + 40, 512), 64), "#0B2550", 60))
    add("DAL", 9, both, ("tex", 1, star_ops, ["shoulder-star-fill"], "solid navy stars on the white shoulder caps"))
    add("DAL", 9, both, ("tex", 12, [enclosed((40, 44, 124, 116), [dnavy, "#000E41", "#0B2550", "#1C2F5A"], dnavy, 40),
                                     enclosed((40, 138, 124, 212), [dnavy, "#000E41", "#0B2550", "#1C2F5A"], dnavy, 40)],
                         ["helmet-star"], "one solid navy star (the modern white gap and outer outline filled)"))

    # DEN styles 5 (Summit White helmet set) and 6 (navy alternate) ---------------------------------------------------
    dor, dnv = "#FC4C02", "#0A2343"
    def den_alt(cloth, panel, band):
        ops = sleeve_bands([], cloth=cloth, clear=(30, 64))
        for top, mirrored in ((0, False), (64, True)):
            def col(c):
                return 127.0 - c if mirrored else c
            back, front = 6.0, 122.0
            b0, b1 = 24.0, 9.0
            ops.append(poly([(col(back), top), (col(front), top), (col(front), top + b1), (col(back), top + b0)],
                            panel))
            # pointed mountain peaks along the band's upper edge
            band_pts = [(col(back), top + b0 + 5.5)]
            steps = 6
            for i in range(steps + 1):
                t = i / steps
                x = back + (front - back) * t
                yb = b0 + (b1 - b0) * t
                band_pts.append((col(x), top + yb - (2.2 if i % 2 else 0.0)))
            band_pts.append((col(front), top + b1 + 5.5))
            ops.append(poly(band_pts, band))
            xa, xb = sorted((col(40.0), col(88.0)))
            box = (int(xa), top, int(xb), top + 18)
            ops.append(recolor(box, [cloth], W, 40, invert=True, match="original"))
        return ops
    def den_pants(cloth, stripe, old):
        ops = []
        for c in LEGS:
            ops += [rect(c - 7.5, 0, c + 7.5, 256, cloth),
                    poly([(c - 8.0, 8.0), (c + 8.0, 8.0), (c + 0.8, 62.0), (c - 0.8, 62.0)], dor),
                    rect(c - 5.5, 12.0, c + 5.5, 256, stripe)]
        return ops
    add("DEN", 5, ("home",), ("tex", 3, den_alt(dnv, dor, W), ["shoulder-panels"],
                              "orange shoulder panel above a pointed white mountain band (old hem bands removed)"))
    add("DEN", 5, ("away",), ("tex", 3, den_alt(W, dor, dnv), ["shoulder-panels"],
                              "orange shoulder panel above a pointed navy mountain band (old hem bands removed)"))
    add("DEN", 6, both, ("tex", 3, den_alt(dnv, dor, W), ["shoulder-panels"],
                         "orange shoulder panel above a pointed white mountain band (old hem bands removed)"))
    add("DEN", 5, ("home",), ("tex", 2, den_pants(dnv, W, dor), ["pants-stripe"],
                              "broad white stripe down the thigh with a short orange hip accent"))
    add("DEN", 6, both, ("tex", 2, den_pants(dnv, W, dor), ["pants-stripe"],
                         "broad white stripe down the thigh with a short orange hip accent"))
    add("DEN", 5, ("away",), ("tex", 2, den_pants(W, dnv, dor), ["pants-stripe"],
                              "broader navy stripe down the thigh with a wider short orange hip accent"))
    add("DEN", 5, both, ("tex", 12, [ring((30, 50, 136, 116), [dnv, "#0C2548", "#14294A"], 1.2, None, W, 28),
                                     ring((30, 144, 136, 212), [dnv, "#0C2548", "#14294A"], 1.2, None, W, 28)],
                         ["white-helmet-logo"], "white horse head defined by thin navy contours, orange mane kept"))
    add("DEN", 5, ("away",), ("unif", {"facemask": "#F2F3F6"}, ["white-facemask"],
                              "white facemask on the Summit White helmet"))

    # DET style 2: black alternate (Oct 20 2025) ------------------------------------------------------------------------
    dblue = "#0076B6"
    digits("DET", 2, both, [{"from": ["#005482"], "to": W, "tolerance": 20}], ["number-border"],
           "blue numerals with a white outline")
    add("DET", 2, both, ("tex", 3, stack("#0D0D0F", [(1.2, W), (6.5, dblue), (1.4, W), (6.5, dblue), (1.2, W)],
                                         start=18, clear=(30, 58)),
                         ["shoulder-bands"], "broad blue bands separated and bordered by white, moved up from the hem"))

    # DET style 9: 2026 Rivalries (gray) ----------------------------------------------------------------------------------
    dgray = "#DCDEE1"
    names("DET", 9, both, "#101012", ["name-color"], "black name lettering", sources=(dblue,), tolerance=60)
    add("DET", 9, both, ("tex", 2, [rect(c - 14, 6, c + 14, 256, "#E3E5E7") for c in LEGS], ["pants-stripe"],
                         "plain gray pants side (the black and blue racing stripe removed)"))
    def det_eye(top, col):
        ops = [rect(0, top, 128, top + 64, dgray)]
        pts_top, pts_bot = [], []
        for i in range(9):
            t = i / 8
            x = 4.0 + 120.0 * t
            half = 1.2 + 8.5 * math.sin(math.pi * t) ** 0.8
            yc = top + 12.0 + 4.0 * t
            pts_top.append((col(x), yc - half))
            pts_bot.append((col(x), yc + half))
        ops.append(poly(pts_top + pts_bot[::-1], "#101012"))
        pts_top2, pts_bot2 = [], []
        for i in range(9):
            t = i / 8
            x = 10.0 + 110.0 * t
            half = 1.2 + 8.5 * math.sin(math.pi * t) ** 0.8
            yc = top + 12.0 + 4.0 * t
            pts_top2.append((col(x), yc + half - 1.6))
            pts_bot2.append((col(x), yc + half + 2.0))
        ops.append(poly(pts_top2 + pts_bot2[::-1], dblue))
        xa, xb = sorted((col(52.0), col(90.0)))
        ops.append(copy((int(xa), top, int(xb), top + 16), (int(xa), top), skip="#17191C", tolerance=30))
        return ops
    add("DET", 9, both, ("tex", 3, on_both_arms(det_eye), ["shoulder-graphic"],
                         "gray sleeve with a tapered black and blue eye graphic across the upper shoulder"))
    clear_tv("DET", 9, both, ["shoulder-graphic"], "no shoulder (TV) numbers")

    # GB style 5: 2026 Rivalries (green jersey, cream pants), Aug 25 2026 reveal -------------------------------------
    ggreen, ggold, gcream, gdark = "#203731", "#FFB612", "#EDE6D0", "#101010"
    digit_art("GB", 5, both, [ring((0, 0, 64, 64), "opaque", 0, 1.5, ggold),
                              recolor((0, 0, 64, 64), [W, "#F4F4F4"], "#F1EAD6", 30)],
              ["number-design"], "cream numerals edged in gold (the Rivalries serif typeface itself is not redrawn)")
    names("GB", 5, both, ggold, ["name-color"], "gold name lettering")
    def gb_band(top, col):
        ops = [rect(0, top + 16, 128, top + 56, "#404A36")]
        y = top + 16.0
        layers = [(7.0, gcream), (1.4, gdark), (6.0, ggold), (1.4, gdark), (7.0, gcream)]
        marks = []
        for h, c in layers:
            ops.append(rect(0, y, 128, y + h, c))
            if c == gdark:
                marks.append(y)
            y += h
        # black sawtooth edging pointing into the cream bands, and a diamond lattice on the gold
        for i in range(32):
            x = i * 4.0
            ops.append(poly([(x, marks[0]), (x + 4.0, marks[0]), (x + 2.0, marks[0] - 2.2)], gdark))
            ops.append(poly([(x, marks[1] + 1.4), (x + 4.0, marks[1] + 1.4), (x + 2.0, marks[1] + 3.6)], gdark))
            ops.append(poly([(x, marks[0] + 4.4), (x + 2.0, marks[0] + 2.9), (x + 4.0, marks[0] + 4.4),
                             (x + 2.0, marks[0] + 5.9)], "#E3A20B"))
        return ops
    add("GB", 5, both, ("tex", 3, on_both_arms(gb_band), ["sleeve-bands"],
                        "two broad cream bands around a gold centre stripe with black sawtooth edging, moved up"))
    def gb_crest(cx, cy):
        g = ggold
        x0, y0, x1, y1 = cx - 12.0, cy - 11.0, cx + 12.0, cy + 11.0
        t = 3.2
        ops = [rect(x0, y0, x1, y0 + t, g), rect(x0, y0, x0 + t, y1, g), rect(x0, y1 - t, x1, y1, g),
               rect(x1 - t, cy + 0.5, x1, y1, g), rect(cx + 2.0, cy + 0.5, x1, cy + 0.5 + t, g)]
        bx0, bx1 = cx - 5.5, cx + 5.0
        by0, by1 = cy - 15.0, cy + 15.0
        tb = 2.6
        ops += [rect(bx0 - 1.0, by0, bx0 + tb, by1, gdark), rect(bx0, by0, bx0 + tb - 1.0, by1, g)]
        for (a0, a1) in ((by0, cy), (cy - 0.5, by1)):
            ops += [rect(bx0, a0, bx1, a0 + tb, g), rect(bx1 - tb, a0, bx1, a1, g), rect(bx0, a1 - tb, bx1, a1, g)]
        return ops
    add("GB", 5, both, ("tex", 1, gb_crest(205.0, 80.0), ["chest-monogram"],
                        "gold interlocked GB monogram on the left chest"))
    add("GB", 5, both, ("tex", 2, pants_stripe(LEGS, [(5.5, ggreen), (2.4, ggold), (5.5, ggreen)]),
                        ["pants-stripe"], "broad dark-green side stripe with a gold centre line"))

    # GB style 6: 1923 Classic (navy jersey, mustard pants), 2025 games -----------------------------------------------
    add("GB", 6, both, ("tex", 2, [recolor((0, 0, 512, 256), ["#B79F73"], "#C08A2A", 26)], ["pants-color"],
                        "strong mustard-gold pants (were pale khaki)"))
    names("GB", 6, both, "#D2A23A", ["name-color"], "gold name lettering")
    clear_tv("GB", 6, both, ["extra-shoulder-digits"], "no shoulder (TV) numbers, only the gold sleeve bands")

    # HOU style 2: Battle Red (2025) ----------------------------------------------------------------------------------
    hnavy, hred = "#03202F", "#B5122E"
    add("HOU", 2, both, ("tex", 1, [recolor((128, 0, 196, 76), ["#DCDCDC", "#D8D8D8", "#E0E0E0"], hnavy, 26),
                                    recolor((360, 0, 424, 50), ["#DCDCDC", "#D8D8D8", "#E0E0E0"], hnavy, 26)],
                         ["neck-color"], "dark navy inner neck under the red collar"))
    def horn(top, col):
        ops = [clear_box((min(col(50.0), col(84.0)), top + 12, max(col(50.0), col(84.0)), top + 30), hred, 30)]
        up, lo = [], []
        for i in range(13):
            t = i / 12
            x = 4.0 + 118.0 * t
            yc = top + 13.0 + 10.0 * t * t
            half = 10.5 * (1.0 - t) ** 0.85 + 0.4
            up.append((col(x), yc - half))
            lo.append((col(x), yc + half))
        ops.append(poly(up + lo[::-1], hnavy))
        line = []
        for i in range(11):
            t = i / 12
            x = 4.0 + 118.0 * t
            yc = top + 13.0 + 10.0 * t * t
            half = 10.5 * (1.0 - t) ** 0.85 + 0.4
            line.append((col(x), yc + half * 0.55))
        ops.append(poly(line + [(px, py + 1.1) for px, py in line[::-1]], hred))
        xa, xb = sorted((col(56.0), col(86.0)))
        ops.append(copy((int(xa), top, int(xb), top + 12), (int(xa), top), skip=hred, tolerance=40))
        return ops
    add("HOU", 2, both, ("tex", 3, on_both_arms(horn), ["shoulder-horns"],
                         "large sweeping navy horn across the shoulder and sleeve"))
    clear_tv("HOU", 2, both, ["shoulder-horns"], "no shoulder (TV) numbers under the horn")

    # IND style 3: 2026 Anvil (charcoal), Sept 27 2026 ------------------------------------------------------------------
    icharcoal, iblue = "#46494D", "#1650C8"
    rivets = []
    for c in LEGS:
        for k in range(14):
            rivets.append(circle(c, 22.0 + k * 16.0, 0.9, "#9AA0A6", n=8))
    add("IND", 3, both, ("tex", 2, [recolor((0, 0, 512, 256), ["#8E9195", "#8D9094"], icharcoal, 20)] +
                         pants_stripe(LEGS, [(1.8, "#111214"), (9.0, iblue), (1.8, "#111214")],
                                      clear=(icharcoal, 8)) + rivets,
                         ["pants-color", "pants-panel"],
                         "charcoal pants with one broad blue panel edged black, with rivets"))
    def horseshoe(top, col):
        if top == 0:
            dst = (53.0, 15.0, 83.0, 45.0)
        else:
            dst = (44.0, 79.0, 74.0, 109.0)
        return [stamp((14, 0, 114, 122), dst, donor=49,
                      remap=[{"from": ["#064FA1", "#044DA0"], "to": "#AEB4BA", "tolerance": 60},
                             {"from": ["#F8F8F8", "#FFFFFF"], "to": "#E2E5E8", "tolerance": 30}])]
    add("IND", 3, both, ("tex", 3, on_both_arms(horseshoe), ["sleeve-horseshoe"],
                         "large silver horseshoe on each sleeve (the kit's own horseshoe art)", {"donors": {"49": None}}))
    clear_tv("IND", 3, both, ["sleeve-horseshoe"], "no shoulder (TV) numbers")

    # IND style 4: 2025 Indiana Nights (blue) -----------------------------------------------------------------------
    add("IND", 4, both, ("tex", 2, pants_stripe(LEGS, [(3.6, W), (3.0, None), (3.6, W)], clear=("#1A50B8", 7)),
                         ["pants-stripes"], "two broad white stripes down each leg"))
    ind_blues = ["#0C399C", "#0C247E", "#0A3293", "#091871", "#172E70", "#0B2C8A", "#1A40A8"]
    add("IND", 4, both, ("tex", 12, [halo((30, 44, 112, 112), ind_blues, 1.3, W, 30),
                                     halo((30, 140, 112, 212), ind_blues, 1.3, W, 30)],
                         ["helmet-horseshoe-edge"], "white border around the blue helmet horseshoe"))

    # JAX style 6: 2026 Rivalries (cream), official 2026 reveal ----------------------------------------------------
    jwhite = "#F0EFEC"
    jax_logo = [recolor(b, ["#CDA640", "#D2AA41", "#C09838", "#B89030"], jwhite, 34) for b in
                ((40, 50, 128, 118), (40, 140, 128, 212))] + \
               [recolor(b, ["#5B4631", "#6B614A", "#7A6A50"], "#9C9A96", 26) for b in
                ((40, 50, 128, 118), (40, 140, 128, 212))]
    add("JAX", 6, both, ("tex", 12, jax_logo, ["helmet-head"],
                         "white throwback-style jaguar head with black details and teal tongue"))
    def jag(top, col):
        dst = (45.0, 15.0, 85.0, 44.0) if top == 0 else (42.0, 79.0, 82.0, 108.0)
        src = (0, 18, 128, 112) if top == 0 else (128, 18, 0, 112)
        return [stamp(src, dst, donor=49,
                      remap=[{"from": ["#D2AA41", "#D3AB41", "#D1A941", "#C09838"], "to": jwhite, "tolerance": 40}])]
    add("JAX", 6, both, ("tex", 3, on_both_arms(jag), ["sleeve-emblem"],
                         "large jaguar-head emblem beneath the swoosh (the kit's own logo art in white)",
                         {"donors": {"49": None}}))
    clear_tv("JAX", 6, both, ["sleeve-emblem"], "no shoulder (TV) numbers")

    # LAC styles 9 (Charger Power gold), 10 (white or powder with gold pants), 11 (Super Chargers navy) -----------------
    lgold, lblue, lnavy = "#FFC20E", "#0080C6", "#12295A"
    add("LAC", 9, both, ("tex", 1, bolts_on_torso(lgold, [(1.8, lblue), (0, W)]), ["shoulder-bolt-shape"],
                         "broad angular white shoulder bolt with a blue border and two large points"))
    add("LAC", 9, both, ("tex", 2, bolts_on_pants(W, [(1.6, lblue), (0, lgold)]), ["pants-bolt-width"],
                         "broad gold pants bolt with a blue border and large angular points"))
    names("LAC", 9, both, lblue, ["name-color"], "blue name lettering on the gold jersey")
    add("LAC", 10, ("away",), ("tex", 1, bolts_on_torso(W, [(1.8, lblue), (0, lgold)]), ["shoulder-bolt-shape"],
                               "angular gold shoulder bolt with a broad pointed zigzag and a blue border"))
    add("LAC", 10, ("home",), ("tex", 1, bolts_on_torso(lblue, [(1.8, W), (0, lgold)]), ["shoulder-bolt-shape"],
                               "angular gold shoulder bolt with a broad pointed zigzag and a white border"))
    add("LAC", 10, both, ("tex", 2, bolts_on_pants(lgold, [(1.6, lblue), (0, W)]), ["pants-bolt-width"],
                          "broad white pants bolt with a blue border and large angular points on the gold pants"))
    add("LAC", 11, both, ("tex", 1, bolts_on_torso(lnavy, [(3.0, lgold), (1.7, lnavy), (0, W)]),
                          ["shoulder-bolt-shape"], "broad white shoulder bolt with navy spacing and a gold outer edge"))
    add("LAC", 11, both, ("tex", 2, bolts_on_pants(lnavy, [(2.8, lgold), (1.6, lnavy), (0, W)]),
                          ["pants-bolt-width"], "broad white pants bolt with navy spacing and a gold border"))

    # LAR style 12: 2025 Midnight Rivalries (navy) ------------------------------------------------------------------
    lrnavy, lryellow, lrblue = "#161F36", "#FFD100", "#1F4FAE"
    lr_pants = [rect(124, 0, 163, 256, lrnavy), rect(352, 0, 390, 256, lrnavy),
                rect(127, 0, 133, 256, lryellow), rect(133, 0, 147, 256, lrblue),
                rect(371, 0, 377, 256, lryellow), rect(357, 0, 371, 256, lrblue)]
    for x0 in (133.0, 357.0):
        for row in range(0, 86):
            for col in range(5):
                cx = x0 + 1.4 + col * 2.8 + (1.4 if row % 2 else 0.0)
                if cx < x0 + 13.4:
                    lr_pants.append(circle(cx, 1.5 + row * 3.0, 0.75, "#0E1A3A", n=6))
    add("LAR", 12, both, ("tex", 2, lr_pants, ["pants-panel"],
                          "yellow strip beside a blue halftone panel (the white outer stripe removed)"))
    def lr_horn(top, col):
        pts_u, pts_l = [], []
        for i in range(11):
            t = i / 10
            x = 36.0 + 88.0 * t
            yc = top + 2.0 + 3.5 * t
            half = 5.5 * (1.0 - t) + 1.0
            pts_u.append((col(x), max(yc - half, top)))
            pts_l.append((col(x), yc + half))
        return [poly(pts_u + pts_l[::-1], lryellow),
                poly([(col(30.0), top + 2.0), (col(42.0), top + 0.0), (col(46.0), top + 10.0), (col(36.0), top + 16.0)],
                     lryellow)]
    add("LAR", 12, both, ("tex", 3, on_both_arms(lr_horn), ["shoulder-horn"],
                          "yellow horn sweeps over the top of the blue shoulder from the curl"))

    # MIA style 10: 2025 dark alternate (Sept 29 2025) ------------------------------------------------------------------
    maqua, morange, mblack = "#008E97", "#FC4C02", "#181B24"
    names("MIA", 10, both, morange, ["name-color"], "orange name lettering", sources=("#3F9CC0",), tolerance=30)
    digits("MIA", 10, both, [{"from": ["#86C4DC"], "to": mblack, "tolerance": 20}], ["number-edge"],
           "aqua numerals without the pale outline")
    add("MIA", 10, both, ("tex", 3, stack(mblack, [(5.5, maqua), (2.2, morange), (5.5, maqua)], start=19,
                                          clear=(30, 62)), ["sleeve-bands"],
                          "broad aqua sleeve bands with an orange middle stripe"))
    add("MIA", 10, both, ("tex", 2, pants_stripe(LEGS, [(4.5, maqua), (2.2, morange), (4.5, maqua)],
                                                 clear=(mblack, 6)), ["pants-panel"],
                          "broad aqua side panel divided by an orange stripe"))
    add("MIA", 10, both, ("tex", 12, [rect(148, 26, 178, 225, morange), rect(150.5, 26, 175.5, 225, "#0F1219"),
                                      rect(151.5, 26, 174.5, 225, maqua)], ["helmet-center-stripe"],
                          "broad aqua centre stripe bordered by narrow orange stripes"))

    # MIN style 6: 2026 Rivalries (purple), Aug 25 2026 ----------------------------------------------------------------
    mpurple, mgold, mivory, mdark = "#33236B", "#C9A23A", "#EDE3C8", "#1C1236"
    def min_band(top, col):
        ops = [rect(0, top + 30, 128, top + 56, mpurple)]
        y = top + 17.0
        for h, c in ((1.2, mgold), (2.6, mivory), (1.0, mgold), (7.0, mdark), (1.0, mgold), (2.6, mivory),
                     (1.2, mgold)):
            ops.append(rect(0, y, 128, y + h, c))
            y += h
        ops += braid(top + 17.0 + 4.8 + 3.5, 0.0, 128.0, 2.6, mgold, step=5.0, width=1.1, vertical=False)
        return ops
    add("MIN", 6, both, ("tex", 3, on_both_arms(min_band), ["sleeve-knot-panel"],
                         "broad ivory and gold bands around a dark knot-chain band, moved up from the hem"))
    min_pants = pants_stripe(LEGS, [(1.0, mgold), (2.4, mivory), (1.0, mgold), (7.0, mdark), (1.0, mgold),
                                    (2.4, mivory), (1.0, mgold)], clear=(mpurple, 4))
    for c in LEGS:
        min_pants += braid(c, 12.0, 252.0, 2.6, mgold, step=5.0, width=1.1)
    add("MIN", 6, both, ("tex", 2, min_pants, ["pants-knot-panel"],
                         "broad dark panel with a gold knot chain and ivory and gold edge bands"))
    min_helm = [rect(147, 0, 173, 240, mivory), rect(149.5, 0, 170.5, 240, mgold), rect(150.5, 0, 169.5, 240, mdark)]
    min_helm += braid(160.0, 0.0, 240.0, 4.2, mgold, step=7.0, width=1.5)
    add("MIN", 6, both, ("tex", 12, min_helm, ["helmet-knot-panel"],
                         "broad dark centre panel with a gold knot chain and ivory and gold borders", {"mip": "mode"}))

    # NE style 4: red throwback (Sept 21 2025) ------------------------------------------------------------------------
    nered, nenavy = "#CA102E", "#0C2340"
    ne4 = []
    for box in ((40, 0, 120, 130), (200, 0, 276, 130), (276, 0, 336, 136), (440, 0, 500, 136)):
        ne4 += [grow(box, [W], W, 2.6, into=[nered, "#CC102F"], tolerance=30),
                grow(box, ["#0C2A6E", "#132C6A", nenavy, "#1D2C80"], "#0C2A6E", 1.4, into=[W], tolerance=40)]
    add("NE", 4, both, ("tex", 1, ne4, ["shoulder-band-width"], "broad white, blue, white shoulder bars"))

    # NE style 9: 2025 Nor'easter Rivalries (Nov 11 2025 reveal) ------------------------------------------------------
    nblue, ngray = "#3D5A8C", "#A6A9AB"
    ne9 = []
    for box in ((40, 0, 110, 90), (210, 0, 262, 90), (276, 0, 322, 90), (448, 0, 500, 90)):
        ne9 += [recolor(box, [W, "#F4F4F4"], ngray, 30),
                ring(box, [ngray], 3.2, None, "#14254A", 20)]
        for k in range(-12, 24):
            x = box[0] + k * 4.0
            ne9.append(dict(poly([(x, box[1]), (x + 0.7, box[1]), (x + 0.7 + 30, box[1] + 90), (x + 30, box[1] + 90)],
                                 "#C2C5C7"), only=[ngray], only_tolerance=12))
            ne9.append(dict(poly([(x + 30, box[1]), (x + 30.7, box[1]), (x + 0.7, box[1] + 90), (x, box[1] + 90)],
                                 "#C2C5C7"), only=[ngray], only_tolerance=12))
    for x, y in ((131.0, 14.0), (127.0, 33.0), (134.0, 52.0), (189.0, 14.0), (193.0, 33.0), (186.0, 52.0)):
        ne9.append(star(x, y, 2.9, "#C60C30"))
    add("NE", 9, both, ("tex", 1, ne9, ["shoulder-bars", "collar-stars"],
                        "gray lattice shoulder bars with a dark-blue centre; red stars around the front collar"))
    def ne_crest(top, col):
        cx, y0, h = col(70.0), top + 16.0, 13.0
        wd = word_width("NE", h, gap=0.5)
        x0 = cx - wd / 2
        ops = []
        for d, colour in ((1.0, nenavy), (0.0, W)):
            for x0_, y0_, x1_, y1_ in LETTERS["N"] + []:
                pass
        unit = h / 7.0
        letters = [("N", x0), ("E", x0 + 5.5 * unit)]
        for d, colour in ((0.9, nenavy), (0.0, W)):
            for ch, lx in letters:
                for a, b, c_, e in LETTERS[ch]:
                    ops.append(rect(lx + a * unit - d, y0 + b * unit - d, lx + c_ * unit + d, y0 + e * unit + d,
                                    colour))
                if ch == "N":
                    ops.append(poly([(lx + 0.4 * unit - d, y0 - d), (lx + 2.0 * unit + d, y0 - d),
                                     (lx + 4.6 * unit + d, y0 + 7 * unit + d), (lx + 3.0 * unit - d, y0 + 7 * unit + d)],
                                    colour))
        return ops
    add("NE", 9, both, ("tex", 3, on_both_arms(ne_crest), ["sleeve-crest"],
                        "large white NE monogram outlined blue on each sleeve"))
    add("NE", 9, both, ("tex", 2, pants_stripe(LEGS, [(2.6, ngray), (6.5, "#14254A"), (2.6, ngray)]),
                        ["pants-side-panel"], "dark-blue side panel with gray edges on the white pants"))

    # NO style 1: white/gold Color Rush (Sept 21 2025) -------------------------------------------------------------
    nblack, ngold = "#101010", "#C9A84C"
    add("NO", 1, both, ("tex", 3, stack(W, [(5.0, nblack), (5.0, ngold), (5.0, nblack), (5.0, ngold)], start=20,
                                        clear=(19, 62)), ["sleeve-band-order"],
                        "black, gold, black, gold sleeve stack (black at the top, gold at the cuff)"))
    fleur = []
    for box in ((123, 22, 153, 60), (358, 28, 388, 62)):
        fleur += [recolor(box, [nblack, "#000000", "#0A0A0A"], "#E8E8E8", 30, match="original"),
                  recolor(box, [ngold, "#CBA752", W, "#F4F4F4"], nblack, 40, match="original")]
    add("NO", 1, both, ("tex", 2, fleur, ["pants-fleur-colors"],
                        "pale fleur-de-lis on a black patch at the top of the pants stripe"))

    # NYG style 7: Vintage White (Nov 9 2025) -------------------------------------------------------------------------
    gnavy, gred = "#0B2265", "#A71930"
    add("NYG", 7, both, ("tex", 3, stack(W, [(4.0, gnavy), (2.6, gred), (4.0, gnavy)], start=39.5, clear=(22, 62)),
                         ["sleeve-band-layout"], "one contiguous blue, red, blue band at the sleeve edge"))

    # NYJ style 6: 2025 Gotham Rivalries (black/dark green) ------------------------------------------------------------
    jsilver, jdark = "#A9AEB1", "#1A1D1C"
    nyj6 = []
    for box in ((40, 0, 110, 90), (210, 0, 262, 90), (276, 0, 322, 90), (448, 0, 500, 90)):
        nyj6.append(ring(box, [jsilver, "#B0B5B8", "#9EA3A6"], 0, 2.2, jdark, 24))
    def tread(x0, y0, x1, y1, colour, only, k0=0):
        ops = []
        j = 0
        y = y0
        while y < y1:
            x = x0 + (3.0 if j % 2 else 0.0)
            i = 0
            while x < x1:
                if (i + j + k0) % 2 == 0:
                    pts = [(x, y + 2.6), (x + 0.9, y + 2.6), (x + 3.0, y), (x + 2.1, y)]
                else:
                    pts = [(x, y), (x + 0.9, y), (x + 3.0, y + 2.6), (x + 2.1, y + 2.6)]
                ops.append(dict(poly(pts, colour), only=only, only_tolerance=16))
                x += 6.0
                i += 1
            y += 4.0
            j += 1
        return ops
    oval = [ellipse(198.0, 84.0, 10.5, 8.5, "#C8CCCF"), ellipse(198.0, 84.0, 9.0, 7.0, "#2A2F31")]
    oval += tread(188.0, 76.0, 208.0, 92.0, "#5A6063", ["#2A2F31"])
    oval.append(poly([(190.5, 87.0), (204.5, 80.0), (206.0, 81.0), (196.0, 85.5), (205.0, 86.0), (204.0, 87.4),
                      (193.0, 87.6)], "#F2F3F4"))
    add("NYJ", 6, both, ("tex", 1, nyj6 + oval, ["shoulder-strips", "chest-emblem"],
                         "narrow silver centre stripe between dark border bands; silver-outlined oval jet emblem"))
    add("NYJ", 6, both, ("tex", 3, tread(0.0, 1.0, 128.0, 62.0, "#5A6063", ["#101A16", "#17261F", "#111B17"]) +
                         tread(0.0, 65.0, 128.0, 126.0, "#5A6063", ["#101A16", "#17261F", "#111B17"], 1),
                         ["sleeve-pattern"], "gray manhole-cover tread pattern over the black sleeve"))
    add("NYJ", 6, both, ("tex", 2, pants_stripe(LEGS, [(3.0, jdark), (4.6, jsilver), (3.0, jdark)],
                                                clear=("#17251E", 7)), ["pants-stripe"],
                         "broad silver-gray centre stripe between dark border bands"))

    # NYJ style 7: 2026 Whiteout (Sept 20 2026) -----------------------------------------------------------------------
    jgreen = "#145F47"
    add("NYJ", 7, ("away",), ("tex", 3, stack(W, [(8, jgreen), (4, None), (8, jgreen)], start=18, clear=(30, 62)),
                              ["sleeve-band-width"], "two broad green bands separated by white, moved up from the hem"))
    add("NYJ", 7, ("home",), ("tex", 3, stack(W, [(8, jgreen), (4, None), (8, jgreen)], start=18, clear=(30, 62)),
                              [], "the same Whiteout sleeve as the away kit (identical texture; uw2 passed the home "
                                  "view, the dated Sept 20 2026 photo applies to both)"))

    # PHI style 4: Kelly green (Oct 26 2025) ---------------------------------------------------------------------------
    pgreen = "#008C48"
    def eagle(top, col):
        box = (16, top + 16, 112, top + 52)
        greys = ["#%02X%02X%02X" % (g, g, g) for g in range(64, 256, 6)]
        return [{"op": "lift", "box": list(box), "from": greys, "tolerance": 6, "keep": [2, 5]}]
    add("PHI", 4, both, ("tex", 3, eagle(0, None) + eagle(64, None), ["sleeve-eagle-contrast"],
                         "brighter white and silver sleeve eagle, dark detail kept"))
    add("PHI", 4, both, ("tex", 2, pants_stripe(LEGS, [(3.8, pgreen), (0.8, "#0A0A0A"), (4.4, W), (0.8, "#0A0A0A"),
                                                       (3.8, pgreen)], clear=("#BABDBF", 8)),
                         ["pants-panel-width"], "broad green outer bands around the white centre with thin dark dividers"))

    # PHI styles 12 (white/black) and 13 (all black), 2025 -------------------------------------------------------------
    pteal = "#004C54"
    for style in (12, 13):
        add("PHI", style, both, ("tex", 2, pants_stripe(LEGS, [(2.4, pteal), (6.4, W), (2.4, pteal)]),
                                 ["pants-side-stripe"], "broad white stripe with green outer bands on the black pants"))
    add("PHI", 13, both, ("tex", 3, sleeve_bands([(49.5, 57.5, pteal)], cloth="#111113"), ["sleeve-cuff-trim"],
                          "green cuff trim beneath the sleeve eagle"))

    # PIT style 5: 1933 throwback (2025 shoot) --------------------------------------------------------------------------
    pgold, pblack = "#F4B418", "#101012"
    pit_note = "white numerals with a black outline (front and back share one digit texture)"
    for c in JERSEY_DIGITS:
        if c == 14:
            # the away '1' keeps its indices (its 560-byte allocation cannot hold a new outline ring): opaque
            # entries turn white, the anti-aliased edge stays black as a thin outline
            add("PIT", 5, ("away",), ("palette", c, [{"from": ["#101012"], "to": W, "tolerance": 20,
                                                      "alpha_min": 255}], ["front-numeral-color"], pit_note))
            add("PIT", 5, ("home",), ("tex", c, [ring((0, 0, 64, 64), "opaque", 1.3, None, W)], ["front-numeral-color"],
                                      pit_note, {"mip": "mode"}))
        else:
            add("PIT", 5, both, ("tex", c, [ring((0, 0, 64, 64), "opaque", 1.3, None, W)], ["front-numeral-color"],
                                 pit_note, {"mip": "mode"}))
    pit = [rect(56, 0, 262, 256, pgold)]
    pit += [poly([(92, 0), (122, 0), (172, 96), (160, 104), (148, 96)], pblack),
            poly([(228, 0), (198, 0), (148, 96), (160, 104), (172, 96)], pblack)]
    for k in range(-3, 4):
        cx = 160.0 + k * 27.0
        top = 104.0 - abs(k) * 50.0
        top = max(top, 40.0 + abs(k) * 0.0)
        if abs(k) == 1:
            top = 82.0
        elif abs(k) == 2:
            top = 56.0
        elif abs(k) == 3:
            top = 30.0
        if k == 0:
            continue
        pit.append(poly([(cx - 6.5, top), (cx + 6.5, top), (cx + 6.5, 256), (cx - 6.5, 256)], pblack))
    pit.append(recolor((128, 0, 192, 76), ["#DCDCDC", "#D8D8D8", "#E0E0E0", W], pgold, 26, match="original"))
    pit.append(recolor((360, 0, 424, 48), ["#DCDCDC", "#D8D8D8", "#E0E0E0", W], pgold, 26, match="original"))
    pit.append(copy((150, 68, 171, 84), (150, 68), skip=pgold, tolerance=24))
    def crest(cx, cy):
        ops = [poly([(cx - 9, cy - 6), (cx + 9, cy - 6), (cx + 9, cy + 6), (cx, cy + 13), (cx - 9, cy + 6)], W),
               poly([(cx - 7.6, cy - 4.8), (cx + 7.6, cy - 4.8), (cx + 7.6, cy + 5.4), (cx, cy + 11.2),
                     (cx - 7.6, cy + 5.4)], pblack),
               rect(cx - 8.5, cy - 13, cx + 8.5, cy - 6, W), rect(cx - 7.2, cy - 11.8, cx + 7.2, cy - 6.2, pgold)]
        for i in range(5):
            ops.append(rect(cx - 7.2 + i * 3.0, cy - 14.4, cx - 5.6 + i * 3.0, cy - 11.8, W))
        for i in range(6):
            ops.append(rect(cx - 7.6 + i * 2.6, cy + 0.2, cx - 6.3 + i * 2.6, cy + 1.6, W))
            ops.append(rect(cx - 6.3 + i * 2.6, cy + 1.6, cx - 5.0 + i * 2.6, cy + 3.0, W))
        ops += [circle(cx - 3.6, cy - 2.4, 1.6, pgold, n=10), circle(cx + 3.6, cy - 2.4, 1.6, pgold, n=10),
                circle(cx, cy + 6.6, 1.6, pgold, n=10)]
        return ops
    pit += crest(206.0, 52.0)
    add("PIT", 5, both, ("tex", 1, pit, ["front-stripe-layout", "inner-collar-color", "chest-crest"],
                         "broad black V bands meeting under the collar with fewer broad vertical bars below; yellow "
                         "inner collar; white-bordered Pittsburgh coat of arms on the upper left chest"))

    # SEA style 3: 2025 Rivalries (gray, Dec 18 2025) -----------------------------------------------------------------
    snavy = "#0C2340"
    names("SEA", 3, both, "#002244", ["name-color"], "dark navy name lettering", sources=("#1C6B40",), tolerance=40)
    poster = [{"from": ["#9AA6AB", "#A7B0B4", "#ADB5B8", "#A9B2B5", "#ABB3B7", "#B0B7BA"], "to": "#B1B8BB",
               "tolerance": 10},
              {"from": ["#72878D", "#798C92", "#7C8E94", "#84949A", "#86969C", "#89989D", "#8E9CA1", "#96A3A8"],
               "to": "#7F9197", "tolerance": 8},
              {"from": ["#143C48", "#163D49", "#2A4C56", "#3E5A63", "#56707A", "#647C84"], "to": "#163D49",
               "tolerance": 14}]
    add("SEA", 3, both, ("tex", 3, [stamp((0, 0, 128, 27), (0, 0, 128, 46), remap=poster),
                                    stamp((0, 64, 128, 91), (0, 64, 128, 110), remap=poster)],
                         ["shoulder-pattern-layout"], "the soundwave field stretched down over the shoulder",
                         {"mip": "mode"}))
    sea3_torso = []
    for x0, x1 in ((54, 136), (186, 268), (286, 364), (412, 494)):
        sea3_torso.append(stamp((x0, 0, x1, 36), (x0, 0, x1, 52)))
    add("SEA", 3, both, ("tex", 1, sea3_torso, ["shoulder-pattern-layout"],
                         "the yoke soundwave field broadened down the shoulder"))
    clear_tv("SEA", 3, both, ["shoulder-pattern-layout"], "no green shoulder (TV) numbers in the soundwave panel")
    sea3_pants = pants_stripe(LEGS, [(2.4, snavy)], clear=("#AEB5B8", 5))
    for c in LEGS:
        for k in range(48):
            y = 10.0 + k * 5.0
            ln = 4.0 + 7.0 * abs(math.sin(k * 1.7))
            sea3_pants.append(poly([(c - 1.2, y), (c - 1.2 - ln, y + 1.4), (c - 1.2, y + 2.4)], snavy))
    add("SEA", 3, both, ("tex", 2, sea3_pants, ["pants-pattern-panel"],
                         "broader side panel of dark soundwave marks along a dark border stripe"))

    # SEA style 4: 2026 navy/gray (home) and white (away) alternate ---------------------------------------------------
    sea4_left = [(46, 57), (64, 54), (92, 51), (104, 47.5), (108, 46.5), (110, 52), (98, 63), (80, 70), (64, 74),
                 (48, 72)]
    def sea4_chest(colour):
        return [poly(sea4_left, colour), poly([(320 - x, y) for x, y in sea4_left], colour)]
    add("SEA", 4, ("home",), ("tex", 1, sea4_chest("#A5ACAF"), ["chest-bands"],
                              "broad light-gray bands across the upper chest from the sleeve panels"))
    add("SEA", 4, ("away",), ("tex", 1, sea4_chest("#0A2A4E"), ["chest-bands"],
                              "broad navy bands across the upper chest from the sleeve panels"))
    add("SEA", 4, ("home",), ("tex", 2, pants_stripe(LEGS, [(12, "#0C2A4C")], clear=("#ABB2B5", 4)) +
                              chevrons(LEGS, "#D3D8DA"), ["pants-feather-panel"],
                              "broad navy side panel with pale feathers on the gray pants"))
    add("SEA", 4, ("away",), ("tex", 2, pants_stripe(LEGS, [(12, "#002244")], clear=(W, 4)) + chevrons(LEGS, W),
                              ["pants-feather-panel"], "broad navy side panel with white feathers"))
    add("SEA", 4, both, ("tex", 12, [recolor((138, 18, 192, 182), ["#405361"], "#9AA2A8", 14),
                                     recolor((138, 18, 192, 182), ["#203B58"], "#56616C", 10)],
                         ["helmet-crown-panel"], "broad gray patterned crown panel on the navy helmet"))

    buf8_dots = ["#4B68A7", "#204A99", "#144193", "#2A55A0", "#3A60A8", "#5A78B0", "#6A88B8", "#7890C0"]
    buf8 = []
    for box in ((40, 56, 152, 124), (40, 140, 152, 210)):
        buf8 += [{"op": "close", "box": list(box), "colors": buf8_dots, "tolerance": 14, "radius": 1.5,
                  "color": W, "into": ["#00338D", "#00338B", "#003289"], "into_tolerance": 10},
                 recolor(box, buf8_dots, W, 14),
                 halo(box, ["#C60C30", "#C80E32", "#B80A2C"], 1.0, W, 30, into=["#00338D", "#003289"],
                      into_tolerance=14)]
    add("BUF", 8, both, ("tex", 12, buf8, ["helmet-graphic"],
                         "bold continuous white outline around the blue buffalo and the red streak"))

    # HOU style 2 helmet: large navy horns in place of the bull-head decal (Battle Red, Nov 20 2025) -----------------
    def crescent(cx, cy, R, r, dx, dy, a0, a1, colour, n=28):
        outer = [(cx + R * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                  cy + R * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
        inner = [(cx + dx + r * math.cos(math.radians(a1 - (a1 - a0) * i / n)),
                  cy + dy + r * math.sin(math.radians(a1 - (a1 - a0) * i / n))) for i in range(n + 1)]
        return poly(outer + inner, colour)
    hshell = ["#B01830", "#B21F36", "#B22A40", "#BA3C50", "#A03B51"]
    add("HOU", 2, both, ("tex", 12, [recolor((38, 56, 124, 111), hshell, "#B01830", 30, invert=True),
                                     recolor((38, 145, 124, 200), hshell, "#B01830", 30, invert=True),
                                     crescent(85, 84, 40, 37, 8, 11, 180, 360, hnavy),
                                     crescent(85, 172, 40, 37, 8, -11, 0, 180, hnavy)],
                         ["helmet-horns"], "large dark navy horn sweeping across each side of the red helmet "
                                           "(the bull-head decal removed)"))

    # BAL style 3 helmet: front-facing two-tone dark raven with red eyes (official 2026 Darkness helmet photo) -------
    head = [(-0.85, -0.55), (-0.62, -0.98), (-0.38, -0.68), (0, -1.0), (0.38, -0.68), (0.62, -0.98), (0.85, -0.55),
            (0.92, -0.1), (0.62, 0.32), (0.26, 0.56), (0, 1.0), (-0.26, 0.56), (-0.62, 0.32), (-0.92, -0.1)]
    face = [(-0.6, -0.45), (0, -0.62), (0.6, -0.45), (0.66, -0.05), (0.4, 0.25), (0, 0.42), (-0.4, 0.25),
            (-0.66, -0.05)]
    beak = [(-0.22, 0.12), (0.22, 0.12), (0.0, 0.95)]
    def raven(cx, cy, S, flip):
        def m(u, v):
            return (cx + u * S, cy + (v if flip else -v) * S)
        ops = [poly([m(u * 1.08, v * 1.08) for u, v in head], "#4A4A52"), poly([m(u, v) for u, v in head], "#26262B"),
               poly([m(u, v) for u, v in face], "#34343A"), poly([m(u, v) for u, v in beak], "#55555E")]
        for su in (-0.34, 0.34):
            ops.append(poly([m(su - 0.13, -0.17), m(su + 0.13, -0.21), m(su + 0.1, -0.08), m(su - 0.12, -0.06)],
                            "#D2102E"))
        return ops
    bshell = ["#141416", "#18181B", "#101012", "#1C1C20", "#0E0E10"]
    add("BAL", 3, both, ("tex", 12, [recolor((24, 63, 134, 108), bshell, "#141416", 22, invert=True),
                                     recolor((24, 148, 134, 193), bshell, "#141416", 22, invert=True)] +
                         raven(78, 86, 24, False) + raven(78, 170, 24, True),
                         ["helmet-logo"], "front-facing two-tone dark raven with red eyes (the side-facing raven "
                                          "removed); our own drawing"))

    # Rows uw2 added after the uf2 snapshot (fixed with the same proof) -------------------------------------------------
    # SF style 7: 2026 Rivalries (black) -------------------------------------------------------------------------------
    sblack, sred = "#111113", "#B0080E"
    add("SF", 7, both, ("tex", 3, stack(sblack, [(4.5, sred), (3.0, None), (4.5, sred), (3.0, None), (4.5, sred)],
                                        start=16, clear=(28, 62)),
                        ["sleeve-band-width"], "three broad red bands over more of the sleeve cap, moved up"))
    add("SF", 7, both, ("tex", 2, pants_stripe(LEGS, [(4.6, sred), (2.6, None), (4.6, sred)], clear=(sblack, 7)),
                        ["pants-stripe-width"], "two broad red bands separated by black"))

    # TEN style 7: 2026 MusicCity (navy) -------------------------------------------------------------------------------
    tnv, tpale = "#0F2748", "#C9DDF0"
    def strings(top, col):
        ops = [rect(0, top + 3, 128, top + 5.2, tpale)]
        for k in range(4):
            y = top + 6.6 + k * 2.6
            ops.append(rect(0, y, 128, y + 0.9, "#9DB9D8"))
        ops.append(rect(0, top + 17.4, 128, top + 19.6, tpale))
        return ops
    add("TEN", 7, both, ("tex", 3, on_both_arms(strings) +
                         [recolor((40, 0, 88, 18), [tnv], "#4495D2", 40, invert=True, match="original"),
                          recolor((39, 64, 87, 82), [tnv], "#4495D2", 40, invert=True, match="original")],
                         ["sleeve-string-panel"], "pale string lines between broad pale upper and lower borders on "
                                                  "the sleeve cap"))
    add("TEN", 7, both, ("tex", 2, pants_stripe(LEGS, [(1.6, tpale), (1.4, None), (1.6, tpale), (1.4, None),
                                                       (1.6, tpale), (1.4, None), (1.6, tpale)], clear=("#0C2340", 7)),
                         ["pants-string-panel"], "four broader straight parallel pale lines (the one-texel lines "
                                                 "aliased into diagonal bars in game)"))

    # WAS style 9: black alternate helmet spear -------------------------------------------------------------------
    wgold, wshell = "#FFB712", "#1A1A1F"
    def spear(y, x_back, x_front):
        d = 1.0 if x_front > x_back else -1.0
        return [rect(min(x_back, x_front - d * 2), y - 2.0, max(x_back, x_front - d * 2), y + 2.0, wgold),
                poly([(x_front - d * 2, y - 7.0), (x_front + d * 14.0, y), (x_front - d * 2, y + 7.0)], wgold)]
    was = [recolor((96, 58, 124, 86), [wgold, "#FEB512"], wshell, 40),
           recolor((34, 164, 62, 192), [wgold, "#FEB512"], wshell, 40)]
    was += spear(74.5, 26.0, 108.0) + spear(178.0, 118.0, 44.0)
    add("WAS", 9, both, ("tex", 12, was, ["helmet-spear"],
                         "gold spear through the middle of the W with a large forward arrowhead"))
    return R


# Findings uf2 reviewed and did not fix with a data row, with the reason (the report table repeats these).
_ENGINE_HELMET = ("NOT DONE: the game draws helmet numbers only at the back of the shell (uw2 saw the small rear "
                  "numerals on the Charger Power kit); large side numerals under the bolt would have to be painted "
                  "into the shared helmet texture, one number for every player")
VERDICTS = {
    "uw2-LAR-home-11-sleeve-numbers": "NOT DONE: the kit's TV digits exist; the game places TV numbers on the "
                                      "shoulder top at a fixed size, not on the sleeve side under the horn",
    "uw2-LAR-away-11-sleeve-numbers": "NOT DONE: as LAR home 11",
    "uw2-NE-home-4-sleeve-number-size": "NOT DONE: the TV digit already fills its texture; the size on the arm is "
                                        "set by the game's number geometry",
    "uw2-NE-away-4-sleeve-number-size": "NOT DONE: as NE home 4",
    "uw2-NYG-home-7-shoulder-number-outline": "FIXED by uf1 (already on the input disc): uw2's frame was the ny1 "
                                              "disc; uf1 gave 18H7 an48-an57 the outlined chest digits",
    "uw2-NYG-away-7-shoulder-number-outline": "FIXED by uf1 (already on the input disc), as NYG home 7",
}
for _side in ("home", "away"):
    VERDICTS["uw2-TEN-%s-7-numeral-stroke-design" % _side] = (
        "NOT DONE: the MusicCity digits are hollow outlines whose interior texels are transparent; broad blue strokes "
        "need opaque texels there (an alpha change the fixed-span compiler does not make) and a ring detail the "
        "digits' small allocations cannot hold")
for _team, _style in (("LAC", 9), ("LAC", 10), ("LAC", 11)):
    for _side in ("home", "away"):
        VERDICTS["uw2-%s-%s-%d-helmet-numbers" % (_team, _side, _style)] = _ENGINE_HELMET


# -- entries, preview and data -----------------------------------------------------------------------------------------

def entries():
    rows = []
    for selector, items in sorted(recipes().items()):
        for kind, chunk, payload, defects, note, extra in items:
            if kind == "tex":
                row = {"selector": selector, "chunk": chunk, "texture": chunk_name(chunk),
                       "kind": "tset" if chunk in TSET else "txtr", "defects": defects, "note": note,
                       "ops": payload}
                row.update(extra)
            elif kind == "palette":
                row = {"selector": selector, "chunk": chunk, "texture": chunk_name(chunk), "kind": "palette",
                       "defects": defects, "note": note, "map": payload}
            elif kind == "clear":
                row = {"selector": selector, "chunk": chunk, "texture": chunk_name(chunk), "kind": "clear",
                       "defects": defects, "note": note}
            elif kind == "unif":
                row = {"selector": selector, "chunk": 0, "texture": "Unif", "kind": "unif", "defects": defects,
                       "note": note, "fields": payload}
            else:
                raise ValueError(kind)
            rows.append(row)
    # merge several items on one chunk (ops concatenate, defects and notes join)
    merged = {}
    for row in rows:
        key = (row["selector"], row["chunk"])
        if key in merged:
            m = merged[key]
            if m["kind"] != row["kind"]:
                raise ValueError("mixed kinds on %r" % (key,))
            if "ops" in row:
                m["ops"] = m["ops"] + row["ops"]
                for k in ("donors",):
                    if k in row:
                        m.setdefault(k, {}).update(row[k])
            elif "map" in row:
                m["map"] = m["map"] + row["map"]
            m["defects"] = sorted(set(m["defects"]) | set(row["defects"]))
            m["note"] = m["note"] + "; " + row["note"]
        else:
            merged[key] = dict(row, defects=sorted(set(row["defects"])))
    return [merged[k] for k in sorted(merged)]


def palette_preview(rgba, mapping):
    out = rgba.copy()
    for m in mapping:
        hit = np.zeros(rgba.shape[:2], bool)
        for source in m["from"]:
            hit |= np.abs(rgba[..., :3].astype(int) - np.array(fixes.hex_rgb(source))).max(axis=2) <= m.get(
                "tolerance", 24)
        hit &= rgba[..., 3] > 0
        if "alpha_min" in m:
            hit &= rgba[..., 3] >= m["alpha_min"]
        out[..., :3][hit] = fixes.hex_rgb(m["to"])
    return out


def preview(export: Path, out: Path, only: list[str]) -> None:
    rows = [r for r in entries() if not only or r["selector"] in only]
    for selector in sorted({r["selector"] for r in rows}):
        src = export / "uniforms" / selector
        dst = out / selector
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        originals = {}
        for row in [r for r in rows if r["selector"] == selector]:
            if row["kind"] == "unif":
                continue
            png = dst / PNG[row["chunk"]]
            rgba = np.asarray(Image.open(png).convert("RGBA")).copy()
            originals[row["chunk"]] = rgba
            if row["kind"] == "clear":
                painted = rgba.copy()
                painted[..., 3] = 0
                n = int((rgba[..., 3] > 0).sum())
            elif row["kind"] == "palette":
                painted = palette_preview(rgba, row["map"])
                n = int((painted != rgba).any(axis=2).sum())
            else:
                donors = {int(k): np.asarray(Image.open(src / PNG[int(k)]).convert("RGBA")).copy()
                          for k in (row.get("donors") or {})}
                painted, scope = fixes.paint(rgba, row["ops"], donors)
                n = int(scope.sum())
            Image.fromarray(painted).save(png)
            print(selector, row["chunk"], row["kind"], "texels", n)


def data(disc: Path, out: Path, probe: bool = False, only=()) -> None:
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    rows = [r for r in entries() if not only or r["selector"] in only]
    failures = []
    with bump._Image.open(disc, writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
        for row in rows:
          try:
            entry = by_name[row["selector"] + ".IFF"]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            chunk = fixes._chunk_for(raw, row["chunk"])
            span = raw[chunk.offset:chunk.end_offset]
            if row["kind"] in ("tset", "txtr"):
                kind = row["kind"]
                _, _, textures = fixes.native_textures(span, kind)
                row["size"] = [textures[0]["width"], textures[0]["height"], textures[0]["mips"]]
                donors = {}
                for k in sorted(row.get("donors") or {}):
                    d = fixes._chunk_for(raw, int(k))
                    donor_span = raw[d.offset:d.end_offset]
                    row["donors"][k] = fixes.sha(donor_span)
                    donors[int(k)] = fixes.texture_rgba(donor_span)
                new, detail = fixes.compile_texture(span, row, donors)
                print(row["selector"], row["chunk"], row["texture"], "added", len(detail["palette_slots_added"]),
                      "scope", detail["level0_scope_texels"], flush=True)
            elif row["kind"] == "palette":
                new, detail = fixes.compile_palette(span, row)
                print(row["selector"], row["chunk"], row["texture"], "palette", len(detail["palette_entries"]),
                      flush=True)
            elif row["kind"] == "clear":
                chunk_obj, decoded, texture = fixes._txtr(span)
                row["size"] = [texture.width, texture.height, texture.mip_levels]
                new, detail = fixes.compile_clear(span, row)
                print(row["selector"], row["chunk"], row["texture"], "cleared", flush=True)
            else:
                new, detail = fixes.compile_unif(span, row)
                print(row["selector"], "Unif", row["fields"], flush=True)
            row.update(resource_size=len(raw), offset=chunk.offset, length=len(span),
                       before_sha256=fixes.sha(span), after_sha256=fixes.sha(new))
          except Exception as exc:  # noqa: BLE001 - probe mode lists every row that does not compile
            if not probe:
                raise
            failures.append((row["selector"], row["chunk"], row["kind"], str(exc)[:120]))
            print("FAIL", row["selector"], row["chunk"], str(exc)[:120], flush=True)
    if probe:
        print("failures", len(failures))
        return
    document = {"schema": fixes.SCHEMA,
                "source": "uf2 (b772): uw2's in-game review of the selectable 2026 alternate, throwback and Rivalries "
                          "kits against dated 2025/26 club photos, each finding checked by uf2 against the crop, the "
                          "game frame, the dated photo and the decoded native texture",
                "method": "Vector art in native texel coordinates drawn at 4x (exact integer arithmetic) and averaged "
                          "onto the existing native pixels; inner rings and outside halos measured from the art; "
                          "stamps of art already in the same kit; palette-only recolours; cleared shoulder digits; "
                          "the Unif facemask colour. Existing palette plus spare slots, wet_93 mud twin, fixed spans.",
                "textures": [{k: row[k] for k in ("selector", "chunk", "texture", "kind", "size", "resource_size",
                                                  "offset", "length", "before_sha256", "after_sha256", "defects",
                                                  "note", "mip", "ops", "map", "fields", "donors")
                              if k in row} for row in rows]}
    with out.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=1)
        stream.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview")
    p.add_argument("--export", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("selectors", nargs="*")
    d = sub.add_parser("data")
    d.add_argument("--input", type=Path, required=True)
    d.add_argument("--out", type=Path, default=DATA)
    d.add_argument("--probe", action="store_true", help="compile every row, list failures, write nothing")
    d.add_argument("selectors", nargs="*")
    args = parser.parse_args(argv)
    if args.cmd == "preview":
        preview(args.export, args.out, args.selectors)
    else:
        data(args.input, args.out, args.probe, args.selectors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
