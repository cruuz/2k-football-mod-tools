#!/usr/bin/env python3
"""uf1 (b772): author the 2026 home/away kit fixes as vector art for ``data/nfl2k5_kit_fixes_2026.json``.

The recipes below are the uf1 decisions, each checked against a dated 2025/26 club photo and the decoded native
texture. They produce the shipped data file: native-texel polygons, flood fills, recolours and art moves that the
Studio pass ``mod_editor/core/nfl2k5_kit_fixes_2026.py`` draws at 4x and averages onto the native pixels.

  uf1_author.py preview --export EXPORT_DIR --out DIR [SELECTOR ...]   level 0 painted onto exported kit PNGs
  uf1_author.py data --input DISC.iso [--out data/nfl2k5_kit_fixes_2026.json]
                                                    compile against the pinned input disc and record the pins

``EXPORT_DIR`` is a ``tools/b765/u1_audit.py`` export (uniforms/<selector>/*.png). Game-derived files stay outside
the repository; only the vector art and the hashes go into the data file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402

DATA = ROOT / "data/nfl2k5_kit_fixes_2026.json"
PNG = {1: "torso.png", 2: "pants.png", 3: "sleeve.png", 4: "socks00.png", 11: "helmet_helmet00.png",
       12: "helmet_helmet02.png"}
for _d in range(10):
    PNG[33 + _d] = f"digit_arm_{_d}.png"
SIZES = {1: ("jersey00", "tset", [512, 256, 6]), 2: ("pants00", "tset", [512, 256, 6]),
         3: ("sleeve00", "tset", [128, 128, 5]), 4: ("socks00", "tset", [64, 64, 4]),
         11: ("helmet00", "txtr", [256, 256, 6]), 12: ("helmet02", "txtr", [256, 256, 6])}


# -- shape helpers (native texel coordinates) ----------------------------------------------------------------------

def rect(x0, y0, x1, y1, color):
    return {"op": "poly", "color": color, "points": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def poly(points, color):
    return {"op": "poly", "color": color, "points": [[round(x, 3), round(y, 3)] for x, y in points]}


def sleeve_bands(bands, *, cloth, clear=None, islands=(0, 64)):
    """Full-circumference sleeve bands on both arm islands (rows 0-63 right arm, 64-127 left arm; row 0 is the
    sleeve's top edge where it meets the jersey, row 63 the hem). ``clear`` repaints old art rows with the cloth
    colour first."""
    ops = []
    for top in islands:
        if clear:
            ops.append(rect(0, top + clear[0], 128, top + clear[1], cloth))
        for r0, r1, color in bands:
            ops.append(rect(0, top + r0, 128, top + r1, color))
    return ops


# -- recipes ---------------------------------------------------------------------------------------------------------
# Each entry: selector -> list of (chunk, ops, defect ids, note).

def stack(cloth, layers, start=17.0, clear=(16, 62)):
    """Contiguous sleeve stack: ``layers`` is a list of (height, colour or None for cloth) from the top."""
    bands, y = [], float(start)
    for height, colour in layers:
        if colour is not None:
            bands.append((round(y, 3), round(y + height, 3), colour))
        y += height
    return sleeve_bands(bands, cloth=cloth, clear=clear)


def copy(src, dst, **extra):
    return dict({"op": "copy", "src": list(src), "dst": list(dst)}, **extra)


def recipes():
    """Every uf1 fix, keyed by kit selector: (chunk, ops, defect ids, note).

    Sleeve stacks: uw2's in-game frames and uf1's diag01 run show the game draws the whole sleeve island from its top
    edge (row 0, under the jersey's shoulder) to the hem (row 63), but rows past ~44 crowd into the hem ring. The
    shipped stacks sat in rows 36-60, so in game they read as a thin cuff trim. The dated 2025/26 photos put the
    stack on the upper and middle sleeve under the swoosh (rows 3-15), so each stack moves to start at row 16-20 with
    the photo's band order and proportions; the swoosh, TV numbers and the hem stay."""
    R = {}
    W = "#FFFFFF"
    add = lambda sel, *items: R.setdefault(sel, []).extend(items)
    # -- sleeves -------------------------------------------------------------------------------------------------
    add("18A0", (3, stack(W, [(2.5, "#B81A35"), (3, None), (11.5, "#B81A35"), (3, None), (2.5, "#B81A35")],
                         start=19.5), ["uw2-NYG-away-0-sleeves"], "red thin/broad/thin stack moved up from the hem"))
    add("00A0", (3, stack(W, [(2.5, "#A0233F"), (9, "#A9AEB3"), (2.5, "#A0233F")], start=18) +
                 [copy((45, 42, 82, 47), (45, 23), skip_col=20), copy((45, 106, 82, 111), (45, 87), skip_col=20)],
                 ["uw2-ARI-away-0-sleeves"], "red/silver/red panel and its CARDINALS wordmark moved up"))
    navy, orange = "#0D1A32", "#C83803"
    chi_h = [(1.3, W), (4.8, orange), (1.3, W), (3.8, None)] * 2 + [(1.3, W), (4.8, orange), (1.3, W)]
    add("05H0", (3, stack(navy, chi_h) + [copy((55, 104, 85, 123), (55, 85), skip_col=20)],
                 ["uw2-CHI-home-0-sleeve-bands"], "three white-edged orange bands moved up and widened, GSH moved with them"))
    add("05A0", (3, stack(W, [(6.3, navy), (5.2, None), (6.9, orange), (4.6, None), (6.9, navy)]) +
                 [copy((55, 104, 85, 123), (55, 85), skip_col=20)],
                 ["uw2-CHI-away-0-sleeve-bands"], "navy/orange/navy bands moved up and widened, GSH moved with them"))
    green, gold = "#26413A", "#FFB612"
    add("10H0", (3, stack(green, [(7, gold), (0.75, "#2D4539"), (6, W), (0.75, "#2D4539"), (7, gold)], start=18),
                 ["uw2-GB-home-0-sleeve-bands"], "gold/white/gold stack moved up from the hem"))
    purple, vgold = "#4F2683", "#FFC62F"
    add("15H0", (3, stack(purple, [(7, W), (7, vgold)], start=18), ["uw2-MIN-home-0-sleeve-bands"],
                 "white over gold band moved up and widened"))
    add("15A0", (3, stack(W, [(7, purple), (7, vgold)], start=18), ["uw2-MIN-away-0-sleeve-bands"],
                 "purple over gold band moved up and widened"))
    tblue, tnavy, tred = "#4495D2", "#0C2340", "#D50A0A"
    field = []
    for _ in range(5):
        field += [(2.25, tblue), (0.75, tnavy)]
    field += [(1.5, tblue)]
    add("28H0", (3, stack(tblue, [(2.25, tred), (2, W)] + field + [(2, W), (2.25, tred)], start=16.5),
                 ["uw2-TEN-home-0-sleeve-bands"], "pinstriped field with red/white borders moved up and widened"))
    add("28A0", (3, stack(W, [(2, tred), (1.5, None)] + field + [(1.5, None), (2, tred)], start=17),
                 ["uw2-TEN-away-0-sleeve-bands"], "light blue pinstriped band with red edges moved up and widened"))
    royal, bred = "#0B3A9E", "#C8102E"
    add("03A0", (3, stack(W, [(6, royal), (2, None), (5, bred), (2, None), (6, royal)], start=18),
                 ["uw2-BUF-away-0-sleeve-bands"], "royal/red/royal stack moved up and widened"))
    lblue, silver = "#0076B6", "#B0B7BC"
    add("09H0", (3, stack(lblue, [(1.5, W), (10.5, silver), (1.5, W), (10.5, silver), (1.5, W)], start=18),
                 ["uw2-DET-home-0-sleeve-bands"], "silver panel with white lines moved up and widened"))
    add("09A0", (3, stack(W, [(1, silver), (10, lblue), (1, silver), (1.5, None), (1, silver), (10, lblue),
                              (1, silver)], start=18),
                 ["uw2-DET-away-0-sleeve-layout"], "two broad blue bands with silver trim moved up and widened"))
    add("13A0", (3, stack(W, [(6.5, "#E31837"), (6, "#FFB612"), (6.5, "#E31837")], start=18),
                 ["uw2-KC-away-0-sleeve-bands"], "red/gold/red stack moved up from the hem"))
    sred = "#B0080E"
    add("25H0", (3, stack(sred, [(5.5, W), (4, None), (5.5, W), (4, None), (5.5, W)], start=18),
                 ["uw2-SF-home-0-sleeve-bands"], "three white stripes moved up and widened"))
    add("25A0", (3, stack(W, [(5.5, sred), (4, None), (5.5, sred), (4, None), (5.5, sred)], start=18),
                 ["uw2-SF-away-0-sleeve-bands"], "three red stripes moved up and widened"))
    jgreen = "#145F47"
    add("19H0", (3, stack(jgreen, [(8, W), (4, None), (8, W)], start=18), ["uw2-NYJ-home-0-sleeve-layout"],
                 "two broad white bars moved up and widened (the shoulder-top TV numbers stay: 2026 photos show them)"))
    add("19A0", (3, stack(W, [(8, jgreen), (4, None), (8, jgreen)], start=18),
                 ["uw2-NYJ-away-0-shoulder-sleeve-layout"],
                 "two broad green bars moved up and widened (the shoulder-top TV numbers stay: 2026 photos show them)"))
    add("02A0", (3, sleeve_bands([(51, 58, "#2E1667")], cloth=W), ["uw2-BAL-away-0-sleeve-cuff"],
                 "purple cuff band added at the hem"))
    # DEN: the 2026 mountain panel sits on the sleeve cap (white on orange at home, orange on white away) with a navy
    # band under its slanted edge; the old hem bands go.
    dorange, dnavy = "#FC4C02", "#0A2343"
    add("08H0", (3, den_sleeve(cloth=dorange, panel=W, band=dnavy, swoosh_from=W, swoosh_to=dnavy),
                 ["uw2-DEN-home-0-shoulder-panel"], "white mountain panel with navy band on the sleeve cap; hem bands removed"))
    add("08A0", (3, den_sleeve(cloth=W, panel=dorange, band=dnavy, swoosh_from=dnavy, swoosh_to=W),
                 ["uw2-DEN-away-0-shoulder-panel"], "orange mountain panel with navy band on the sleeve cap; hem bands removed"))
    # -- torsos --------------------------------------------------------------------------------------------------
    add("26H0", (1, sea_chest("#A5ACAF", text_box=(204, 43, 264, 72)), ["uw2-SEA-home-0-chest-bands"],
                 "wolf-gray upper-chest bands widened to the 2026 proportion; SEAHAWKS wordmark kept"))
    add("26A0", (1, sea_chest("#0A2A4E", text_box=(204, 43, 264, 72)), ["uw2-SEA-away-0-chest-bands"],
                 "navy upper-chest bands widened to the 2026 proportion; SEAHAWKS wordmark kept"))
    lar_blue = "#003594"
    horns = [(44, 8, 100, 92), (224, 8, 296, 92), (264, 14, 320, 92), (458, 14, 506, 92)]
    add("23A0", (1, [{"op": "recolor", "box": list(b), "from": ["#FFD100"], "color": lar_blue, "tolerance": 120}
                     for b in horns] +
                 [{"op": "recolor", "box": list(b), "from": ["#FFF4C1", "#FFEFA0"], "color": "#8C9BC9", "tolerance": 40}
                  for b in horns],
                 ["uw2-LAR-away-0-front-yoke"], "the shoulder horns on the white torso are royal blue (2026 unveil and "
                 "week 4 photos); the yellow stays on the sleeves"))
    add("24H0", (1, lac_bolts(), ["uw2-LAC-home-0-shoulder-bolt"],
                 "broad gold shoulder bolt with two angular steps and a white border, on the old bolt's path"))
    add("17A0", (1, [{"op": "grow", "box": [104, 0, 216, 70], "from": ["#060606"], "into": ["*"],
                      "except": ["#DCDCDC"], "color": "#060606", "radius": 4.5, "tolerance": 14},
                     {"op": "enclosed", "box": [104, 0, 216, 70], "edge": ["#060606"], "color": "#060606",
                      "tolerance": 40}],
                 ["uw2-NO-away-0-neckline-panel"], "front black V-neck band widened to the 2026 width"))
    add("37H0", (1, hou_patch(centre=(192, 77)), ["uw2-HOU-home-0-anniversary-chest"],
                 "Texans 25th-season patch on the upper left chest"))
    add("37A0", (1, hou_patch(centre=(192, 77)), ["uw2-HOU-away-0-2026-anniversary-patch"],
                 "Texans 25th-season patch on the upper left chest"))
    add("25H0", (1, sf_patch(centre=(194, 76)), ["uw2-SF-home-0-anniversary-chest"],
                 "49ers 80 YEARS patch on the upper left chest"))
    add("25A0", (1, sf_patch(centre=(194, 76)), ["uw2-SF-away-0-anniversary-chest"],
                 "49ers 80 YEARS patch on the upper left chest"))
    # -- pants ---------------------------------------------------------------------------------------------------
    legs = (142, 369)
    add("28H0", (2, pants_stripe(legs, [(2.5, tred), (2.5, W)] + [(2.4, tblue), (0.9, tnavy)] * 5 + [(1.5, tblue)] +
                                 [(2.5, W), (2.5, tred)], clear=("#FFFFFF", 7)),
                 ["uw2-TEN-home-0-pants-stripe"], "broad light-blue pinstriped side panel with white/red borders"))
    add("27A0", (2, pants_stripe(legs, [(1.5, "#0E0E0E"), (1.5, "#DC4405"), (8, "#B21C35"), (1.5, "#DC4405"),
                                        (1.5, "#0E0E0E")], clear=("#4B4641", 4)),
                 ["uw2-TB-away-0-pants-stripe"], "broad red side stripe with orange and black borders (2026 week 1)"))
    add("08H0", (2, pants_stripe(legs, [(11, dnavy)], clear=None, protect=["#FC4C02"]),
                 ["uw2-DEN-home-0-pants-stripe"], "navy side stripe widened under the orange hip accent"))
    add("08A0", (2, pants_stripe(legs, [(10, W)], clear=("#0A2343", 4), protect=["#FC4C02"]),
                 ["uw2-DEN-away-0-pants-stripe"], "white side stripe on the navy pants under the orange hip accent"))
    add("26H0", (2, pants_stripe(legs, [(12, "#69BE28")], clear=("#0C2A4C", 4)) + chevrons(legs, "#0C2A4C"),
                 ["uw2-SEA-home-0-pants-feather-stripe"], "broad action-green stripe with navy feathers"))
    add("26A0", (2, pants_stripe(legs, [(12, "#002244")], clear=("#FFFFFF", 4)) + chevrons(legs, W),
                 ["uw2-SEA-away-0-pants-pattern"], "broad navy stripe with white feathers"))
    # -- socks ---------------------------------------------------------------------------------------------------
    add("13H0", (4, [rect(0, 41, 64, 43, W), rect(0, 43, 64, 47.5, "#FFB612"), rect(0, 47.5, 64, 64, W)],
                 ["uw2-KC-home-0-sock-bands"], "white/gold band and white foot under the red sock (2026 week 1)"))
    # -- helmets (helmet02 is the shell every 2026 roster player wears) --------------------------------------------
    for sel, defect in (("26H0", "uw2-SEA-home-0-helmet-crown"), ("26A0", "uw2-SEA-away-0-helmet-crown")):
        add(sel, (12, [{"op": "recolor", "box": [138, 18, 192, 182], "from": ["#405361"], "color": "#9AA2A8",
                        "tolerance": 14},
                       {"op": "recolor", "box": [138, 18, 192, 182], "from": ["#203B58"], "color": "#56616C",
                        "tolerance": 10}],
                  [defect], "crown carbon pattern lifted to the 2026 gray"))
    for sel, defect in (("29H0", "uw2-WAS-home-0-helmet-logo-fill"), ("29A0", "uw2-WAS-away-0-helmet-w")):
        add(sel, (12, [{"op": "enclosed", "box": [47, 57, 113, 96], "edge": ["#FFB612"], "color": "#FFB612",
                        "tolerance": 70},
                       {"op": "enclosed", "box": [47, 160, 113, 199], "edge": ["#FFB612"], "color": "#FFB612",
                        "tolerance": 70}],
                  [defect], "the W strokes filled solid gold, both sides"))
    # -- Giants Vintage White / Color Rush: shoulder digits get the chest digits' outlined art ---------------------
    for sel in ("18H7", "18A7"):
        for d in range(10):
            add(sel, ("digit", d, ["ny1-NYG-style7-shoulder-outline"],
                      "shoulder digit takes the chest digit's red-outlined palette and mip chain"))
    return R


def den_sleeve(cloth, panel, band, swoosh_from, swoosh_to):
    ops = sleeve_bands([], cloth=cloth, clear=(45, 64))
    for top, mirror in ((0, False), (64, True)):
        def col(c):
            return 127.0 - c if mirror else c
        back, front = 6.0, 122.0
        b0, b1 = 24.0, 9.0               # the panel's lower edge rises from the back of the arm to the front
        poly_pts = [(col(back), top), (col(front), top), (col(front), top + b1), (col(back), top + b0)]
        band_pts = [(col(back), top + b0), (col(front), top + b1), (col(front), top + b1 + 5.5),
                    (col(back), top + b0 + 5.5)]
        ops.append(poly(poly_pts, panel))
        ops.append(poly(band_pts, band))
        ops.append({"op": "recolor", "box": [40, top, 88, top + 18], "from": [swoosh_from], "color": swoosh_to,
                    "tolerance": 40, "match": "original"})
    return ops


def sea_chest(colour, text_box):
    left = [(46, 57), (64, 54), (92, 51), (112, 46), (120, 44), (122, 50), (104, 62), (80, 70), (64, 74), (48, 72)]
    right = [(320 - x, y) for x, y in left]
    return [poly(left, colour),
            dict(poly(right, colour), protect={"box": list(text_box), "colors": [colour], "tolerance": 30})]


def pants_stripe(legs, layers, clear=None, protect=None, top=10.0, bottom=256.0):
    """A vertical side stripe centred on each leg's seam column; ``layers`` are (width, colour) left to right.
    ``clear`` (colour, half-width) first repaints the old stripe; ``protect`` keeps per column the rows between
    the first and last texel of those colours (an existing hip accent)."""
    ops = []
    total = sum(w for w, _ in layers)
    for c in legs:
        if clear:
            ops.append(rect(c - clear[1] - 0.5, top, c + clear[1] + 0.5, bottom, clear[0]))
        x = c - total / 2.0
        for width, colour in layers:
            if colour is not None:
                op = rect(x, top, x + width, bottom, colour)
                if protect:
                    op["protect"] = {"box": [int(c - 12), 0, int(c + 12), 256], "colors": protect, "tolerance": 30}
                ops.append(op)
            x += width
    return ops


def chevrons(legs, colour, top=20.0, bottom=250.0, period=10.0, half=5.2, depth=3.6, thick=2.2):
    ops = []
    for c in legs:
        y = top
        while y + depth + thick <= bottom:
            ops.append(poly([(c - half, y), (c, y + depth), (c + half, y), (c + half, y + thick),
                             (c, y + depth + thick), (c - half, y + thick)], colour))
            y += period
    return ops


BOLT = [(-14, 0), (12, 0), (2, 38), (13, 36), (-1, 70), (8, 68), (-4, 100), (-8, 64), (-16, 66), (-6, 34), (-17, 36)]
# centre line (x at row 0, x change per row) and length in rows of the four shipped shoulder bolts, measured on 24H0
BOLTS = [(72.5, 0.21, 96, 1), (251.5, -0.21, 96, -1), (299.5, 0.15, 96, -1), (478.5, -0.15, 96, 1)]


def offset_polygon(points, d):
    """Mitred outward offset of a simple polygon by ``d`` texels (either winding)."""
    pts = np.asarray(points, float)
    area = 0.5 * np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1])
    sign = 1.0 if area > 0 else -1.0
    out = []
    n = len(pts)
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        normals = []
        for a, b in ((p0, p1), (p1, p2)):
            e = (b - a) / np.linalg.norm(b - a)
            normals.append(np.array([e[1], -e[0]]) * sign)       # outward for this winding
        m = normals[0] + normals[1]
        m /= np.linalg.norm(m)
        scale = d / max(float(np.dot(m, normals[0])), 0.35)        # mitre, clamped at sharp points
        q = p1 + m * scale
        out.append((round(float(q[0]), 3), round(float(q[1]), 3)))
    return out


def lac_bolts():
    ops = []
    for (x0, slope, length, direction), box in zip(BOLTS, [(60, 0, 104, 100), (220, 0, 266, 100),
                                                          (286, 0, 320, 100), (458, 0, 492, 100)]):
        ops.append({"op": "recolor", "box": list(box), "from": ["#0080C6"], "color": "#0080C6", "tolerance": 10,
                    "invert": True})
        pts = [(x0 + slope * (y * length / 100.0) + direction * x, y * length / 100.0) for x, y in BOLT]
        ops.append(poly(offset_polygon(pts, 1.7), "#FFFFFF"))
        ops.append(poly(pts, "#FFC210"))
    return ops


GLYPHS = {  # 5 x 7 block digits: rectangles (x0, y0, x1, y1)
    "0": [(0, 0, 5, 1.5), (0, 5.5, 5, 7), (0, 0, 1.6, 7), (3.4, 0, 5, 7)],
    "2": [(0, 0, 5, 1.5), (3.4, 0, 5, 3.6), (0, 2.8, 5, 4.2), (0, 2.8, 1.6, 7), (0, 5.5, 5, 7)],
    "5": [(0, 0, 5, 1.5), (0, 0, 1.6, 3.6), (0, 2.8, 5, 4.2), (3.4, 2.8, 5, 7), (0, 5.5, 5, 7)],
    "8": [(0, 0, 5, 1.5), (0, 2.8, 5, 4.2), (0, 5.5, 5, 7), (0, 0, 1.6, 7), (3.4, 0, 5, 7)],
    "6": [(0, 0, 5, 1.5), (0, 0, 1.6, 7), (0, 2.8, 5, 4.2), (3.4, 2.8, 5, 7), (0, 5.5, 5, 7)],
}


def text(digits, x, y, height, colour, gap=0.9):
    unit = height / 7.0
    ops = []
    for ch in digits:
        for x0, y0, x1, y1 in GLYPHS[ch]:
            ops.append(rect(x + x0 * unit, y + y0 * unit, x + x1 * unit, y + y1 * unit, colour))
        x += (5 + gap) * unit
    return ops


TEXAS = [(0.30, 0.00), (0.47, 0.00), (0.47, 0.32), (0.62, 0.38), (0.80, 0.40), (1.00, 0.45), (1.00, 0.62),
         (0.93, 0.72), (0.80, 0.80), (0.70, 0.88), (0.66, 1.00), (0.55, 0.97), (0.45, 0.82), (0.35, 0.70),
         (0.22, 0.62), (0.12, 0.68), (0.00, 0.55), (0.00, 0.40), (0.30, 0.40)]


def hou_patch(centre, width=21.0, height=19.0):
    cx, cy = centre
    x0, y0 = cx - width / 2, cy - height / 2
    shape = [(x0 + u * width, y0 + v * height) for u, v in TEXAS]
    ops = [poly(offset_polygon(shape, 1.0), "#A71930"), poly(shape, "#FFFFFF")]
    ops += text("25", cx - 6.0 + 0.7, cy - 3.6 + 0.7, 9.0, "#A71930")       # red drop shadow
    ops += text("25", cx - 6.0, cy - 3.6, 9.0, "#03202F")
    return ops


def sf_patch(centre, width=19.0, height=16.0):
    cx, cy = centre
    x0, y0, x1, y1 = cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2
    c = 2.0                                                            # chamfered corners
    outer = [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c),
             (x0, y0 + c)]
    inner = [(x + (1.3 if x < cx else -1.3), y + (1.3 if y < cy else -1.3)) for x, y in outer]
    ops = [poly(outer, "#B3995D"), poly(inner, "#FFFFFF")]
    ops += text("80", x0 + 2.4, y0 + 2.2, 8.4, "#1A1A1A")
    ops.append(poly([(x1 - 1, cy - 2.6), (x1 + 5.5, cy - 2.6), (x1 + 4.2, cy - 0.6), (x1 + 5.5, cy + 1.4),
                     (x1 - 1, cy + 1.4)], "#AA0000"))                   # YEARS tab
    ops.append(poly([(cx - 3.2, y1 - 3.6), (cx + 3.2, y1 - 3.6), (cx + 3.2, y1 - 1.6), (cx - 3.2, y1 - 1.6)],
                    "#AA0000"))                                         # the SF oval
    return ops


def entries():
    rows = []
    for selector, items in sorted(recipes().items()):
        for item in items:
            if item[0] == "digit":
                _, d, defects, note = item
                rows.append({"selector": selector, "chunk": 33 + d, "texture": "an%d" % (48 + d),
                             "kind": "copy_video", "size": [64, 64, 4], "donor_chunk": 13 + d,
                             "donor_texture": "%d" % (48 + d), "defects": defects, "note": note})
                continue
            chunk, ops, defects, note = item
            name, kind, size = SIZES[chunk]
            rows.append({"selector": selector, "chunk": chunk, "texture": name, "kind": kind, "size": size,
                         "defects": defects, "note": note, "ops": ops})
    return rows


# -- commands --------------------------------------------------------------------------------------------------------

def preview(export: Path, out: Path, only: list[str]) -> None:
    rows = [r for r in entries() if not only or r["selector"] in only]
    for selector in sorted({r["selector"] for r in rows}):
        src = export / "uniforms" / selector
        dst = out / selector
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        for row in [r for r in rows if r["selector"] == selector]:
            if row["kind"] == "copy_video":
                d = row["chunk"] - 33
                shutil.copyfile(dst / f"digit_jersey_{d}.png", dst / f"digit_arm_{d}.png")
                continue
            png = dst / PNG[row["chunk"]]
            rgba = np.asarray(Image.open(png).convert("RGBA")).copy()
            painted, scope = fixes.paint(rgba, row["ops"])
            Image.fromarray(painted).save(png)
            print(selector, row["chunk"], "scope texels", int(scope.sum()))


def data(disc: Path, out: Path) -> None:
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    rows = entries()
    with bump._Image.open(disc, writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
        for row in rows:
            entry = by_name[row["selector"] + ".IFF"]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            chunk = fixes._chunk_for(raw, row["chunk"])
            span = raw[chunk.offset:chunk.end_offset]
            if row["kind"] == "copy_video":
                donor = fixes._chunk_for(raw, row["donor_chunk"])
                donor_span = raw[donor.offset:donor.end_offset]
                row["donor_sha256"] = fixes.sha(donor_span)
                new, detail = fixes.copy_video(span, donor_span, row)
                print(row["selector"], row["chunk"], row["texture"], "fit", detail["fit"].get("encoder"), flush=True)
            else:
                new, detail = fixes.compile_texture(span, row)
                print(row["selector"], row["chunk"], row["texture"], "added", len(detail["palette_slots_added"]),
                      "scope", detail["level0_scope_texels"], flush=True)
            row.update(resource_size=len(raw), offset=chunk.offset, length=len(span),
                       before_sha256=fixes.sha(span), after_sha256=fixes.sha(new))
    document = {"schema": fixes.SCHEMA,
                "source": "uf1 (b772): uw2's in-game review of the 64 current kits against dated 2025/26 club "
                          "photos, each finding checked by uf1 against the decoded native textures",
                "method": "Vector art in native texel coordinates, drawn at 4x (4x4 samples per texel, exact "
                          "integer arithmetic) and averaged onto the existing native pixels; existing palette plus "
                          "spare slots, wet_93 mud twin, fixed spans.",
                "textures": [{k: row[k] for k in ("selector", "chunk", "texture", "kind", "size", "resource_size",
                                                  "offset", "length", "before_sha256", "after_sha256", "defects",
                                                  "note", "ops", "donor_chunk", "donor_texture", "donor_sha256")
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
    args = parser.parse_args(argv)
    if args.cmd == "preview":
        preview(args.export, args.out, args.selectors)
    else:
        data(args.input, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
