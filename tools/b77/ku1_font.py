"""ku1 (b776): the 2026 Kansas City Chiefs number shapes, drawn from dated club photographs.

The Chiefs' Nike-era numerals are a heavy block face: thick strokes (about a fifth of the height), small rounded outer
corners, square counters, a flat-topped 1 with a slanted flag and no foot, a 7 with a straight diagonal stem, a closed
diagonal 4, and a 6/9 whose bar ends in a short spur. The shapes below are measured from the 2026 week 1 (DEN),
week 2 (IND) and week 4 (LV) chiefs.com galleries and the 2025 week 8 (WSH) Wikimedia photo: numbers 4, 7, 9, 14, 15,
20, 21, 31, 38, 51, 56, 77, 99 (reference only; no photo or font ships). Units: height 100, outer contours are filled
in order and may overlap; ``holes`` are cleared after them (``nfl2k5_team_2026_art.render_polygon_glyph``).
"""
from __future__ import annotations

import math

H = 100.0
W = 56.0          # every digit but the 1
W1 = 34.0         # the 1
SV = 17.5         # vertical stroke
SH = 19.0         # horizontal stroke
R = 8.0           # outer corner radius
SEG = 5           # arc segments per rounded corner


def _r(v):
    return round(float(v), 2)


def rrect(x0, y0, x1, y1, tl=0.0, tr=0.0, br=0.0, bl=0.0):
    """A rectangle with per-corner radii, clockwise from the top-left (y down)."""
    pts = []

    def arc(cx, cy, r, a0, a1):
        if r <= 0:
            pts.append((cx, cy))
            return
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
    w, sv, sh, r = W, SV, SH, R
    mid = 40.5                      # top of the middle bar of 3, 5, 6 (9 by symmetry)
    out = {}
    out["0"] = dict(width=w, contours=[rrect(0, 0, w, H, r, r, r, r)],
                    holes=[rrect(sv, sh, w - sv, H - sh, 2, 2, 2, 2)])
    out["1"] = dict(width=W1, contours=[poly([(0, 2.5), (2.5, 0), (W1 - 3, 0), (W1, 3), (W1, H - 3), (W1 - 3, H),
                                              (13, H), (10, H - 3), (10, 33), (0, 26)])], holes=[])
    out["2"] = dict(width=w, contours=[
        rrect(0, 0, w, sh, r, r, 0, 0),
        rrect(0, 0, sv, 29, r, 0, 2, 2),
        rrect(w - sv, 0, w, 50, 0, r, 0, 0),
        poly([(w - sv, 41), (w, 46), (w, 52), (sv + 2, H - sh + 1), (0, H - sh + 1), (0, H - sh - 7)]),
        rrect(0, H - sh, w, H, 0, 0, 2, 2)], holes=[])
    out["3"] = dict(width=w, contours=[
        rrect(0, 0, w, sh, 2, r, 0, 0),
        rrect(w - sv, 0, w, H, 0, r, r, 0),
        rrect(15, mid, w, mid + sh, 2, 0, 0, 2),
        rrect(0, H - sh, w, H, 0, 0, r, 2)], holes=[])
    stem0 = w - sv - 2
    out["4"] = dict(width=w, contours=[
        rrect(stem0, 0, w - 2, H, 0, 3, 3, 3),
        rrect(0, 60, w, 60 + sh, 2, 2, 2, 2),
        poly([(stem0 - 8, 0), (stem0, 0), (stem0, 22), (sv + 1, 60), (0, 60), (0, 53)])], holes=[])
    out["5"] = dict(width=w, contours=[
        rrect(0, 0, w, sh, 2, 2, 0, 0),
        rrect(0, 0, sv, mid + sh, 2, 0, 0, 0),
        rrect(0, mid, w, mid + sh, 0, r, 0, 0),
        rrect(w - sv, mid, w, H, 0, r, r, 0),
        rrect(0, H - sh, w, H, 0, 0, r, 2)], holes=[])
    six = [
        rrect(0, 0, sv, H, r, 0, 0, r),
        rrect(0, 0, w, sh, r, r, 0, 0),
        rrect(w - sv, 0, w, 28, 0, r, 2, 2),
        rrect(0, mid, w, mid + sh, 0, r, 0, 0),
        rrect(w - sv, mid, w, H, 0, r, r, 0),
        rrect(0, H - sh, w, H, 0, 0, r, r)]
    out["6"] = dict(width=w, contours=six, holes=[])
    out["9"] = dict(width=w, contours=_rot(six, w), holes=[])
    out["7"] = dict(width=w, contours=[
        rrect(0, 0, w, sh + 1, 2, r, 0, 0),
        rrect(0, 0, 12, 29, 2, 0, 2, 2),
        poly([(w - 21, sh), (w, sh), (w, sh + 8), (32, H), (12, H)])], holes=[])
    out["8"] = dict(width=w, contours=[rrect(0, 0, w, H, r, r, r, r)],
                    holes=[rrect(sv + 1.5, sh, w - sv - 1.5, 42, 2, 2, 2, 2),
                           rrect(sv, 42 + 15, w - sv, H - sh, 2, 2, 2, 2)])
    for digit, shape in out.items():
        shape["height"] = H
    return {k: out[k] for k in sorted(out)}
