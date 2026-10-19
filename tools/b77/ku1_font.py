"""ku1 (b776): the 2026 Kansas City Chiefs number shapes, measured from dated club photographs.

v2 (Noah 10/18: the first, heavier set was too thick). Every number below was rectified to a front-on plane and
profiled (``.b77-scratch/ku1/tools/measure_numbers.py`` and ``measure2.py``; reference only, nothing of the photos
ships): the chiefs.com 2026 week 1 (DEN), week 2 (IND) and week 4 (LV) galleries and the 2025 week 8 (WSH) Wikimedia
photo, numbers 21, 23, 31, 38, 70, 77 and the single 4, 7, 8, 9. Measured, as fractions of the digit's fill height:
vertical strokes 0.15 to 0.18, horizontal bars 0.15 to 0.17 (photo blur adds about 0.01), widths 0.50 (3) to 0.53
(2), 0.52 (8), about 0.56 (0), 0.34 for the flagged 1 with a 0.17 stem, the gold edge 0.014 to 0.024, an 8 whose
upper counter (0.15 x 0.20) is smaller than its lower (0.19 x 0.30), a closed 4 with a small triangular counter
(0.13 x 0.27), a 7 whose straight stem leans about 20 degrees, small outer corner radii and square counters. The
retail 2004 set measures 0.148 vertical and 0.130 horizontal; the first ku1 set 0.169 and 0.186.

Units: height 100, outer contours are filled in order and may overlap; ``holes`` are cleared after them
(``nfl2k5_team_2026_art.render_polygon_glyph``).
"""
from __future__ import annotations

import math

H = 100.0
SV = 16.0         # vertical stroke
SH = 15.5         # horizontal bar
R = 5.0           # outer corner radius
RI = 1.5          # counter corner radius
SEG = 5           # arc segments per rounded corner
WIDTH = {"0": 55.0, "1": 31.0, "2": 53.0, "3": 51.0, "4": 54.0, "5": 53.0, "6": 52.0, "7": 51.0, "8": 52.0, "9": 52.0}
W = 52.0          # the common width (kept for callers)
W1 = WIDTH["1"]


def _r(v):
    return round(float(v), 2)


def rrect(x0, y0, x1, y1, tl=0.0, tr=0.0, br=0.0, bl=0.0):
    """A rectangle with per-corner radii, clockwise from the top-left (y down)."""
    pts = []

    def arc(cx, cy, r, a0, a1):
        for k in range(SEG + 1):
            a = math.radians(a0 + (a1 - a0) * k / SEG)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    arc(x0 + tl, y0 + tl, tl, 180, 270) if tl else pts.append((x0, y0))
    arc(x1 - tr, y0 + tr, tr, 270, 360) if tr else pts.append((x1, y0))
    arc(x1 - br, y1 - br, br, 0, 90) if br else pts.append((x1, y1))
    arc(x0 + bl, y1 - bl, bl, 90, 180) if bl else pts.append((x0, y1))
    return [[_r(x), _r(y)] for x, y in pts]


def poly(points):
    return [[_r(x), _r(y)] for x, y in points]


def _rot(contours, width):
    """Turn a shape 180 degrees (the 9 from the 6)."""
    return [[[_r(width - x), _r(H - y)] for x, y in reversed(c)] for c in contours]


def shapes():
    sv, sh, r, ri = SV, SH, R, RI
    bot = H - sh
    mid = 42.5                      # top of the middle bar of 3, 5, 6 (9 by symmetry)
    out = {}
    w = WIDTH["0"]
    out["0"] = dict(width=w, contours=[rrect(0, 0, w, H, r + 1, r + 1, r + 1, r + 1)],
                    holes=[rrect(sv, sh, w - sv, bot, ri, ri, ri, ri)])
    w = WIDTH["1"]
    # stem 13..30; the flag: the top slants down to the left, a short vertical edge, then back up into the stem
    out["1"] = dict(width=w, contours=[poly([(0, 9), (13, 0), (w - 2, 0), (w, 2), (w, H - 2), (w - 2, H),
                                             (15, H), (13, H - 2), (13, 33), (0, 25)])], holes=[])
    w = WIDTH["2"]
    out["2"] = dict(width=w, contours=[
        rrect(0, 0, w, sh, r, r, 0, 0),
        rrect(0, 0, sv, 27, r, 0, ri, ri),
        rrect(w - sv, 0, w, 50, 0, r, 0, 0),
        poly([(w - sv, 39), (w, 43), (w, 55), (sv, 71), (0, 71), (0, 58)]),
        rrect(0, 58, sv, H, 0, 0, 0, r),
        rrect(0, bot, w, H, 0, 0, r, r)], holes=[])
    w = WIDTH["3"]
    out["3"] = dict(width=w, contours=[
        rrect(0, 0, w, sh, ri, r, 0, 0),
        rrect(w - sv, 0, w, H, 0, r, r, 0),
        rrect(14, mid + 1, w, mid + 1 + sh, ri, 0, 0, ri),
        rrect(0, bot, w, H, 0, 0, r, ri)], holes=[])
    w = WIDTH["4"]
    s0, s1 = w - 3 - sv, w - 3
    out["4"] = dict(width=w, contours=[
        rrect(s0, 0, s1, H, 0, ri, ri, ri),
        rrect(0, 56, w, 56 + sh, ri, ri, ri, ri),
        poly([(s0 - 3.6, 0), (s0, 0), (s0, 29.4), (s0 - 13, 56), (4, 56), (0, 56), (0, 52)])], holes=[])
    w = WIDTH["5"]
    out["5"] = dict(width=w, contours=[
        rrect(0, 0, w, sh, ri, ri, 0, 0),
        rrect(0, 0, sv, mid + sh, ri, 0, 0, 0),
        rrect(0, mid, w, mid + sh, 0, r, 0, 0),
        rrect(w - sv, mid, w, H, 0, r, r, 0),
        rrect(0, bot, w, H, 0, 0, r, ri)], holes=[])
    w = WIDTH["6"]
    six = [
        rrect(0, 0, sv, H, r, 0, 0, r),
        rrect(0, 0, w, sh, r, r, 0, 0),
        rrect(w - sv, 0, w, 26, 0, r, ri, ri),
        rrect(0, mid, w, mid + sh, 0, r, 0, 0),
        rrect(w - sv, mid, w, H, 0, r, r, 0),
        rrect(0, bot, w, H, 0, 0, r, r)]
    out["6"] = dict(width=w, contours=six, holes=[])
    out["9"] = dict(width=WIDTH["9"], contours=_rot(six, w), holes=[])
    w = WIDTH["7"]
    out["7"] = dict(width=w, contours=[
        rrect(0, 0, w, sh, ri, r, 0, 0),
        rrect(0, 0, 12, 25, ri, 0, ri, ri),
        poly([(w - 17, sh), (w, sh), (w, sh + 2.5), (21, H), (4, H)])], holes=[])
    w = WIDTH["8"]
    out["8"] = dict(width=w, contours=[rrect(0, 0, w, H, r + 1, r + 1, r + 1, r + 1)],
                    holes=[rrect(sv + 1.5, 14, w - sv - 1.5, 34, ri, ri, ri, ri),
                           rrect(sv, 49, w - sv, 82, ri, ri, ri, ri)])
    for shape in out.values():
        shape["height"] = H
    return {k: out[k] for k in sorted(out)}
