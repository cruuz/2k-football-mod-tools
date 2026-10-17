#!/usr/bin/env python3
"""sb1: authored Super Bowl field marks (the flank logos on the 25s, 30s and 35s) and the club marks of the three
team-flank Super Bowls, drawn from geometry and type.

Every mark is drawn here from shapes, gradients and system type. The reference logos and field diagrams were only looked
at while choosing the layout, the colours and the proportions; none is read, traced or shipped (they live in the
job's scratch folder). Each mark follows its game's design system:

* XXIII, XXXVIII, XLII, XLIII, XLIV: the period event badges (banner, plate or lozenge with the numerals);
* XLVI, XLVII, XLIX (2011 to 2014): the silver trophy over the host stadium's silhouette, SUPER BOWL and silver
  numerals;
* LI to LVIII (2016 on): chrome slab numerals with the trophy standing among them over a SUPER BOWL bar, the bar and
  the numerals' fill in the game's colours (LVI's sunset and palms, LVIII's violet skyline);
* LXII to LXV, for franchise seasons whose logo is not revealed: the same current system with a neutral fill. These
  are generic marks, not the real logos.

The user's own ``super_bowl/<NUMERALS>.png`` replaces any event mark at build time (nfl2k5_super_bowl_fields).

    python3 tools/nfl2k5_super_bowl_marks_art.py [--out data/nfl2k5_super_bowl_fields] [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import nfl2k5_super_bowl_walls_art as wa  # noqa: E402

OUT = ROOT / "data/nfl2k5_super_bowl_fields"
SCHEMA = "nfl2k5_super_bowl_fields/v1"
#: masters are drawn at this cap height scale, then reduced so the longer side is at most MAX_SIDE
MAX_SIDE = 512
WHITE, BLACK = (255, 255, 255), (0, 0, 0)

# --- the rows ------------------------------------------------------------------------------------------------------
#: Anniversary row -> (numerals, season, flank kind, flank centre yards from midfield, box (along, across) yards,
#: team sides). Yard lines and sizes measured on the reference field diagrams (gridiron-uniforms.com, kept in scratch).
#: A team flank sits on the side of the club's own end zone: the shipped period end-zone art paints the AFC club into
#: the north (-z) end zone of these three rows (DEN, TEN, NE), so that club takes the north 30.
ROWS = {
    14: ("XXIII", 1988, "event", 15, (7.6, 4.0), None),
    15: ("XXV", 1990, "shield", 15, (5.8, 7.0), None),
    21: ("XXXII", 1997, "team", 20, (7.0, 6.0), {"N": "DEN", "S": "GB"}),
    22: ("XXXIV", 1999, "team", 20, (7.0, 6.0), {"N": "TEN", "S": "STL"}),
    23: ("XXXVI", 2001, "team", 20, (7.0, 6.0), {"N": "NE", "S": "STL"}),
    27: ("XLII", 2007, "event", 25, (9.0, 7.0), None),
    28: ("XLIII", 2008, "event", 25, (9.4, 5.0), None),
    29: ("XLVI", 2011, "event", 25, (8.2, 9.2), None),
    30: ("LI", 2016, "event", 25, (8.5, 8.6), None),
    34: ("XXXVIII", 2003, "event", 25, (9.0, 6.6), None),
    35: ("XLIV", 2009, "event", 25, (12.0, 5.2), None),
    40: ("XLVII", 2012, "event", 25, (8.2, 8.8), None),
    42: ("XLIX", 2014, "event", 25, (9.7, 9.4), None),
    45: ("LII", 2017, "event", 25, (9.4, 8.2), None),
    46: ("LIV", 2019, "event", 25, (8.8, 7.2), None),
    48: ("LVI", 2021, "event", 25, (13.0, 10.3), None),
    50: ("LVIII", 2023, "event", 25, (14.0, 10.0), None),
}
#: franchise Super Bowls whose logo is not revealed (2026-10-17): the generic current-system marks
FRANCHISE_GENERIC = ("LXII", "LXIII", "LXIV", "LXV")


# --- small helpers -------------------------------------------------------------------------------------------------

def L(size):
    return Image.new("L", size, 0)


def rgba(size):
    return Image.new("RGBA", size, (0, 0, 0, 0))


def poly(size, pts):
    m = L(size)
    ImageDraw.Draw(m).polygon([(float(x), float(y)) for x, y in pts], fill=255)
    return m


def solid(mask, colour):
    return wa.solid(mask, colour)


def over(dst, src, at=(0, 0)):
    dst.alpha_composite(src, (int(round(at[0])), int(round(at[1]))))


def union(*masks):
    out = masks[0]
    for m in masks[1:]:
        out = ImageChops.lighter(out, m)
    return out


def minus(a, b):
    return ImageChops.subtract(a, b)


def bevel(mask, light, dark, depth):
    """Chiselled edges: the top-left inner band lit, the bottom-right inner band shaded (RGBA over the mask)."""
    a = np.asarray(mask, float) / 255.0
    d = ndi.distance_transform_edt(a > 0.5)
    band = np.clip(1.0 - d / max(1.0, depth), 0, 1) * a
    gy, gx = np.gradient(ndi.gaussian_filter(a, max(1.0, depth / 2)))
    lit = np.clip(-(gx + gy) * depth * 2.2, -1, 1)
    out = np.zeros(a.shape + (4,), float)
    up = (lit > 0) * band * lit
    dn = (lit < 0) * band * -lit
    out[..., :3] = np.where(up[..., None] >= dn[..., None], light, dark)
    out[..., 3] = np.maximum(up, dn) * 255
    return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGBA")


def text(word, px, path=wa.BLACK, tracking=0.0):
    return wa.text_mask(word, px, path, tracking)


def shrink(m, r):
    return wa.shrink(m, r)


def grow(m, r):
    """Dilate within the canvas (the canvas keeps its size)."""
    g = wa.grow(m, r)
    return g.crop((r, r, r + m.width, r + m.height))


def ring(m, r):
    return minus(grow(m, r), m)


def gradient(size, stops, angle=90.0):
    """RGBA linear gradient at ``angle`` degrees (90 = top to bottom)."""
    W, H = size
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    a = math.radians(angle)
    t = (xx * math.cos(a) + yy * math.sin(a))
    t = (t - t.min()) / max(1e-6, t.max() - t.min())
    ts = [s[0] for s in stops]
    cols = np.array([s[1][:3] for s in stops], float)
    rgb = np.stack([np.interp(t, ts, cols[:, i]) for i in range(3)], -1)
    return Image.fromarray(np.dstack([rgb.clip(0, 255).astype(np.uint8), np.full((H, W), 255, np.uint8)]), "RGBA")


def fill(mask, image):
    return wa.fill_mask(mask, image)


CHROME = [(0.0, (250, 252, 255)), (0.30, (214, 220, 228)), (0.47, (150, 158, 172)), (0.52, (96, 104, 120)),
          (0.62, (178, 186, 198)), (1.0, (236, 240, 246))]
SILVER_DARK = [(0.0, (212, 216, 222)), (0.5, (140, 146, 156)), (1.0, (196, 200, 208))]


def chrome(mask, stops=CHROME, angle=90.0):
    return fill(mask, gradient(mask.size, stops, angle))


def chrome_box(mask, stops, angle=90.0):
    """A gradient spanning only the mask's own bounding box."""
    box = mask.getbbox()
    g = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    g.paste(gradient((box[2] - box[0], box[3] - box[1]), stops, angle), box[:2])
    return fill(mask, g)


# --- the Lombardi trophy -------------------------------------------------------------------------------------------

def trophy(H):
    """The silver trophy (ball tilted on a three-sided tapered stand over a stepped base), height H, RGBA."""
    W = int(H * 0.46)
    cx = W / 2
    s = (W, H)
    # ball: a pointed ellipse, long axis tilted 38 degrees up to the right
    ball = L(s)
    bw, bh = H * 0.155, H * 0.255
    ang = math.radians(38)
    pts = []
    for k in range(120):
        t = 2 * math.pi * k / 120
        # a prolate spheroid outline with sharpened tips
        x = bw * math.sin(t) * (1 - 0.18 * math.cos(t) ** 2)
        y = bh * math.cos(t)
        pts.append((cx + x * math.cos(ang) + y * math.sin(ang) - H * 0.005,
                    H * 0.205 - (-x * math.sin(ang) + y * math.cos(ang)) * 0.82))
    ImageDraw.Draw(ball).polygon(pts, fill=255)
    # stand: concave three-sided column from under the ball to the base
    top_y, neck_y, foot_y = H * 0.36, H * 0.60, H * 0.83
    stand_pts = []
    n = 40
    for k in range(n + 1):
        t = k / n
        y = top_y + (foot_y - top_y) * t
        half = H * (0.021 + 0.022 * (1 - t) ** 3 + 0.062 * t ** 2.6)
        stand_pts.append((cx - half, y))
    for k in range(n, -1, -1):
        t = k / n
        y = top_y + (foot_y - top_y) * t
        half = H * (0.021 + 0.022 * (1 - t) ** 3 + 0.062 * t ** 2.6)
        stand_pts.append((cx + half, y))
    stand = poly(s, stand_pts)
    cup = poly(s, [(cx - H * 0.055, H * 0.335), (cx + H * 0.055, H * 0.335), (cx + H * 0.030, H * 0.38),
                   (cx - H * 0.030, H * 0.38)])
    base = poly(s, [(cx - H * 0.105, foot_y), (cx + H * 0.105, foot_y), (cx + H * 0.125, H * 0.92),
                    (cx + H * 0.125, H * 0.995), (cx - H * 0.125, H * 0.995), (cx - H * 0.125, H * 0.92)])
    body = union(stand, cup, base)
    out = rgba(s)
    over(out, chrome(body, [(0.0, (226, 230, 236)), (0.45, (250, 251, 253)), (0.55, (168, 174, 186)),
                            (1.0, (214, 218, 226))], angle=0.0))
    # the faces of the stand: the left face lit, the right face in shade
    right = poly(s, [(cx + H * 0.004, top_y), (cx + H * 0.2, top_y), (cx + H * 0.2, H), (cx + H * 0.004, H)])
    over(out, fill(ImageChops.multiply(stand, right), gradient(s, [(0, (196, 202, 212)), (1, (122, 128, 142))], 0.0)))
    over(out, solid(ImageChops.multiply(base, poly(s, [(0, H * 0.905), (W, H * 0.905), (W, H * 0.93),
                                                     (0, H * 0.93)])), (110, 116, 130)))
    # ball: chrome with a bright crown and a dark underside, laces and seams
    bfill = chrome_box(ball, [(0.0, (246, 248, 252)), (0.25, (214, 219, 228)), (0.50, (150, 157, 170)),
                          (0.72, (104, 110, 124)), (1.0, (168, 174, 186))], angle=115.0)
    over(out, bfill)
    seam = L(s)
    d = ImageDraw.Draw(seam)
    sx0, sy0 = cx - H * 0.035, H * 0.10
    sx1, sy1 = cx + H * 0.072, H * 0.29
    d.line([(sx0, sy0), (sx1, sy1)], fill=255, width=max(1, int(H * 0.012)))
    for k in range(5):
        t = 0.25 + 0.12 * k
        px, py = sx0 + (sx1 - sx0) * t, sy0 + (sy1 - sy0) * t
        dx, dy = H * 0.022, -H * 0.013
        d.line([(px - dx, py - dy), (px + dx, py + dy)], fill=255, width=max(1, int(H * 0.008)))
    over(out, solid(ImageChops.multiply(seam, ball), (255, 255, 255)))
    over(out, solid(ImageChops.multiply(ring(ball, max(1, int(H * 0.006))), grow(ball, int(H * 0.01))),
                    (96, 102, 114)))
    # the small NFL shield on the stand's front
    sh = int(H * 0.055)
    shield = poly(s, [(cx - sh * 0.5, H * 0.70), (cx + sh * 0.5, H * 0.70), (cx + sh * 0.5, H * 0.70 + sh * 0.7),
                      (cx, H * 0.70 + sh * 1.15), (cx - sh * 0.5, H * 0.70 + sh * 0.7)])
    over(out, solid(shield, (24, 52, 110)))
    over(out, solid(ring(shield, max(1, int(H * 0.004))), (220, 224, 232)))
    return out


# --- Roman numerals ------------------------------------------------------------------------------------------------

def glyph(ch, H, weight=0.24, serif=0.10, slant=0.0):
    """A geometric slab (serif > 0) or block (serif 0) Roman numeral: (L mask, advance)."""
    s = H * weight          # stem
    t = H * serif           # serif height
    sw = s * 0.55           # serif overhang each side
    if ch == "I":
        W = s + 2 * sw if serif else s
        pts = ([(0, 0), (W, 0), (W, t), (sw + s, t), (sw + s, H - t), (W, H - t), (W, H), (0, H), (0, H - t),
                (sw, H - t), (sw, t), (0, t)] if serif else [(0, 0), (s, 0), (s, H), (0, H)])
        m = poly((int(W) + 2, int(H) + 2), pts)
    elif ch == "L":
        W = H * 0.72
        x0 = sw if serif else 0
        pts = ([(0, 0), (x0 + s + sw, 0), (x0 + s + sw, t), (x0 + s, t), (x0 + s, H - s * 0.92), (W - s * 0.25, H - s * 0.92),
                (W, H - s * 1.45), (W, H), (0, H), (0, H - t), (x0, H - t), (x0, t), (0, t)] if serif else
               [(0, 0), (s, 0), (s, H - s), (W, H - s), (W, H), (0, H)])
        m = poly((int(W) + 2, int(H) + 2), pts)
    elif ch in "VX":
        W = H * (0.86 if ch == "V" else 0.90)
        m = L((int(W) + 2, int(H) + 2))
        d = ImageDraw.Draw(m)
        if ch == "V":
            thick, thin = s * 1.05, s * 0.62
            d.polygon([(0, 0), (thick, 0), (W / 2 + thick * 0.28, H - s * 0.9), (W / 2 + thick * 0.1, H),
                       (W / 2 - thick * 0.45, H)], fill=255)
            d.polygon([(W - thin, 0), (W, 0), (W / 2 + thick * 0.1, H), (W / 2 - thin * 0.4, H - s * 0.5)], fill=255)
            if serif:
                d.rectangle([0 - sw * 0.3, 0, thick + sw, t], fill=255)
                d.rectangle([W - thin - sw, 0, W, t], fill=255)
        else:
            thick, thin = s * 1.05, s * 0.62
            d.polygon([(0, 0), (thick, 0), (W, H), (W - thick, H)], fill=255)
            d.polygon([(W - thin, 0), (W, 0), (thin, H), (0, H)], fill=255)
            if serif:
                d.rectangle([0, 0, thick + sw * 0.8, t], fill=255)
                d.rectangle([W - thin - sw * 0.8, 0, W, t], fill=255)
                d.rectangle([0, H - t, thin + sw * 0.8, H], fill=255)
                d.rectangle([W - thick - sw * 0.8, H - t, W, H], fill=255)
    else:
        raise ValueError(ch)
    if slant:
        m = m.transform((int(m.width + H * slant) + 2, m.height), Image.AFFINE,
                        (1, slant, -H * slant, 0, 1, 0), Image.BICUBIC)
    return m, m.width


def numeral_mask(word, H, gap=0.06, **kw):
    """(mask, [x positions]) of a word of numerals."""
    parts = [glyph(c, H, **kw) for c in word]
    xs, x = [], 0.0
    for m, adv in parts:
        xs.append(x)
        x += adv + H * gap
    out = L((int(x - H * gap) + 4, int(H) + 4))
    for (m, _), px in zip(parts, xs):
        out = ImageChops.lighter(out, _place(m, out.size, px + 2, 2))
    return out, xs


def _place(m, size, x, y):
    c = L(size)
    c.paste(m, (int(round(x)), int(round(y))))
    return c


def bbox_crop(im, pad=4):
    box = im.getchannel("A").getbbox()
    box = (max(0, box[0] - pad), max(0, box[1] - pad), min(im.width, box[2] + pad), min(im.height, box[3] + pad))
    return im.crop(box)


# --- 2016 on: chrome numerals, the trophy and the bar --------------------------------------------------------------

def bar(W, H, stops, text_colour, word="SUPER BOWL", edge=(220, 224, 230)):
    s = (int(W), int(H))
    m = poly(s, [(0, 0), (W, 0), (W, H), (0, H)])
    out = rgba(s)
    over(out, fill(m, gradient(s, stops, 90.0)))
    over(out, solid(ring(shrink(m, 1), max(1, int(H * 0.08))), edge))
    t = solid(text(word, 300, wa.BLACK, 0.16), text_colour)
    t = wa.fit(t, W * 0.82, H * 0.62)
    wa.paste_c(out, t, W / 2, H / 2)
    return out


def modern(word, *, fill_stops=None, fill_img=None, accent=(120, 128, 140), bar_stops=None, bar_text=WHITE,
           trophy_after=1, outline=(236, 238, 242), bar_edge=(226, 230, 236)):
    """The 2016-on system: slab numerals (chrome, or filled with ``fill_img`` and a chrome rim) with the trophy
    standing after the ``trophy_after``-th numeral, over the SUPER BOWL bar."""
    H = 520
    # the current system's numerals are tall and condensed: geometric slabs squeezed to 70 % of their width
    letters = []
    for c in word:
        m, _adv = glyph(c, H, weight=0.30, serif=0.085)
        m = m.resize((max(4, int(m.width * 0.70)), m.height), Image.LANCZOS)
        letters.append((m, m.width))
    gap = H * 0.04
    tro = trophy(int(H * 1.62))
    widths = [m.width for m, _ in letters]
    slot = tro.width * 0.55
    total = sum(widths) + gap * (len(word) - 1) + slot + gap
    W = int(total + 80)
    top = int(H * 0.72)
    canvas_h = top + H + int(H * 0.30) + 40
    out = rgba((W, canvas_h))
    x = 40.0
    xs = []
    for k, (m, adv) in enumerate(letters):
        if k == trophy_after:
            xs.append(("T", x))
            x += slot + gap
        xs.append((k, x))
        x += adv + gap
    num = L((W, canvas_h))
    for item, px in xs:
        if item != "T":
            num = ImageChops.lighter(num, _place(letters[item][0], (W, canvas_h), px, top))
    rim = max(4, int(H * 0.035))
    inner = shrink(num, rim)
    over(out, solid(grow(num, max(2, rim // 2)), (40, 44, 54)))
    over(out, chrome(num, angle=90.0))
    if fill_img is not None:
        over(out, fill(inner, fill_img.resize((W, canvas_h))))
    elif fill_stops is not None:
        over(out, fill(inner, gradient((W, canvas_h), fill_stops, 90.0)))
    else:
        over(out, chrome(inner, [(0.0, (240, 243, 248)), (0.5, (190, 196, 206)), (0.52, (150, 156, 168)),
                                 (1.0, (226, 230, 238))]))
    over(out, bevel(num, (255, 255, 255), accent, rim * 1.2))
    # the trophy
    tx = [px for item, px in xs if item == "T"][0] + slot / 2
    tro_y = top + H - tro.height + int(H * 0.06)
    over(out, wa.shadow(tro, int(H * 0.012), int(H * 0.012), int(H * 0.02), 0.45),
         (tx - tro.width / 2 - (int(H * 0.02) * 2 + int(H * 0.012)), tro_y - (int(H * 0.02) * 2 + int(H * 0.012))))
    # the bar
    bw, bh = x - gap - 40, H * 0.22
    b = bar(bw, bh, bar_stops or [(0, (224, 228, 234)), (0.5, (176, 182, 192)), (1, (214, 218, 226))], bar_text,
            edge=bar_edge)
    over(out, b, (40, top + H + H * 0.02))
    return bbox_crop(out)


def palms(size, colour, seed):
    """Palm silhouettes along the bottom of a canvas (LVI's sunset fill)."""
    W, H = size
    m = L(size)
    d = ImageDraw.Draw(m)
    rng = np.random.default_rng(seed)
    for k in range(9):
        x = W * (0.05 + 0.11 * k + rng.uniform(-0.02, 0.02))
        h = H * rng.uniform(0.30, 0.52)
        lean = rng.uniform(-0.08, 0.08) * H
        d.line([(x, H), (x + lean, H - h)], fill=255, width=max(2, int(W * 0.006)))
        tx, ty = x + lean, H - h
        for a in range(8):
            ang = math.radians(-160 + a * 40 + rng.uniform(-8, 8))
            ln = H * rng.uniform(0.07, 0.11)
            d.line([(tx, ty), (tx + ln * math.cos(ang), ty + ln * math.sin(ang) * 0.6 + ln * 0.25)], fill=255,
                   width=max(2, int(W * 0.004)))
    return solid(m, colour)


def skyline(size, colour, seed):
    """Tower silhouettes along the bottom of a canvas (LVIII's skyline fill)."""
    W, H = size
    m = L(size)
    d = ImageDraw.Draw(m)
    rng = np.random.default_rng(seed)
    x = 0.0
    while x < W:
        w = W * rng.uniform(0.02, 0.05)
        h = H * rng.uniform(0.18, 0.55)
        d.rectangle([x, H - h, x + w, H], fill=255)
        if rng.uniform() < 0.3:
            d.polygon([(x, H - h), (x + w, H - h), (x + w / 2, H - h - H * 0.06)], fill=255)
        x += w + W * rng.uniform(0.0, 0.01)
    return solid(m, colour)


def m_LI():
    return modern("LI", accent=(150, 30, 40), bar_stops=[(0, (196, 30, 40)), (1, (120, 14, 22))],
                  bar_edge=(210, 214, 222))


def m_LII():
    return modern("LII", accent=(40, 110, 170), bar_stops=[(0, (120, 196, 236)), (1, (54, 130, 196))],
                  bar_edge=(220, 226, 232))


def m_LIV():
    return modern("LIV", trophy_after=1, accent=(180, 150, 70),
                  bar_stops=[(0, (46, 168, 170)), (1, (18, 108, 116))], bar_edge=(222, 196, 120))


def m_LVI():
    H = 900
    sunset = gradient((1600, H), [(0.0, (255, 206, 72)), (0.35, (250, 130, 40)), (0.65, (228, 52, 60)),
                                  (1.0, (176, 30, 110))], 90.0)
    sunset.alpha_composite(palms((1600, H), (90, 16, 40), 56))
    return modern("LVI", fill_img=sunset, accent=(150, 30, 40),
                  bar_stops=[(0, (232, 234, 238)), (0.5, (184, 188, 196)), (1, (222, 224, 230))],
                  bar_text=(40, 40, 46))


def m_LVIII():
    H = 900
    violet = gradient((1800, H), [(0.0, (196, 120, 236)), (0.45, (128, 70, 200)), (1.0, (64, 30, 130))], 90.0)
    violet.alpha_composite(skyline((1800, H), (44, 20, 92), 58))
    return modern("LVIII", fill_img=violet, accent=(90, 50, 160),
                  bar_stops=[(0, (232, 234, 238)), (0.5, (184, 188, 196)), (1, (222, 224, 230))],
                  bar_text=(52, 26, 96))


def m_generic(word):
    """A franchise Super Bowl whose logo is not revealed: the current system with a neutral navy fill."""
    return modern(word, fill_stops=[(0.0, (54, 84, 150)), (0.5, (24, 46, 100)), (1.0, (12, 24, 60))],
                  accent=(40, 60, 110), bar_stops=[(0, (232, 234, 238)), (0.5, (184, 188, 196)),
                                                    (1, (222, 224, 230))], bar_text=(16, 32, 76))


# --- 2011 to 2014: trophy over the stadium -------------------------------------------------------------------------

def stadium_shape(kind, W, H):
    m = L((W, H))
    d = ImageDraw.Draw(m)
    if kind == "lucas":       # gabled roof, the big window wall, two towers
        d.polygon([(W * 0.06, H), (W * 0.06, H * 0.42), (W * 0.5, H * 0.18), (W * 0.94, H * 0.42), (W * 0.94, H)],
                  fill=255)
        d.rectangle([W * 0.02, H * 0.36, W * 0.12, H], fill=255)
        d.rectangle([W * 0.88, H * 0.36, W * 0.98, H], fill=255)
    elif kind == "superdome":  # the shallow dome on its drum
        d.rectangle([W * 0.04, H * 0.55, W * 0.96, H], fill=255)
        d.pieslice([W * 0.04, H * 0.20, W * 0.96, H * 0.90], 180, 360, fill=255)
    elif kind == "uop":       # the curved shell over the louvred sides
        d.pieslice([W * 0.0, H * 0.25, W * 1.0, H * 1.35], 180, 360, fill=255)
        d.rectangle([W * 0.03, H * 0.75, W * 0.97, H], fill=255)
    return m


def trophy_stadium(word, kind):
    H = 900
    W = 1000
    out = rgba((W, H))
    st = stadium_shape(kind, int(W * 0.9), int(H * 0.30))
    st_img = rgba(st.size)
    over(st_img, chrome(st, [(0, (196, 202, 210)), (1, (120, 126, 138))]))
    lines = L(st.size)
    d = ImageDraw.Draw(lines)
    for k in range(1, 14):
        x = st.width * k / 14
        d.line([(x, 0), (x, st.height)], fill=255, width=3)
    over(st_img, solid(ImageChops.multiply(lines, shrink(st, 4)), (150, 156, 168)))
    over(out, st_img, ((W - st.width) / 2, H * 0.42))
    tro = trophy(int(H * 0.70))
    over(out, wa.shadow(tro, 6, 6, 10, 0.4), ((W - tro.width) / 2 - 26, H * 0.04 - 26))
    sb = solid(text("SUPER BOWL", 200, wa.BLACK, 0.12), (60, 64, 74))
    sb = wa.fit(sb, W * 0.40, H * 0.05)
    plate = rgba((int(sb.width * 1.25), int(sb.height * 2.0)))
    over(plate, solid(L(plate.size).point(lambda v: 255), (232, 234, 238)))
    wa.paste_c(plate, sb, plate.width / 2, plate.height / 2)
    wa.paste_c(out, plate, W / 2, H * 0.715)
    num, _ = numeral_mask(word, 220, weight=0.24, serif=0.0)
    numi = rgba(num.size)
    over(numi, chrome(num, [(0.0, (250, 251, 253)), (0.45, (206, 210, 218)), (0.5, (120, 126, 138)),
                            (1.0, (222, 226, 232))]))
    over(numi, bevel(num, (255, 255, 255), (40, 44, 54), 12))
    numi = wa.outline(numi, (30, 32, 38), 6)
    numi = wa.fit(numi, W * 0.92, H * 0.24)
    wa.paste_c(out, numi, W / 2, H * 0.87)
    return bbox_crop(out)


# --- the period badges ---------------------------------------------------------------------------------------------

NAVY, RED = (16, 36, 96), (200, 24, 40)


def m_XXIII():
    W, H = 1200, 560
    out = rgba((W, H))
    plate = poly((W, H), [(60, 120), (W - 60, 120), (W - 60, 430), (W / 2 + 60, 430), (W / 2, 520),
                          (W / 2 - 60, 430), (60, 430)])
    over(out, solid(grow(plate, 14), NAVY))
    over(out, solid(plate, WHITE))
    ban = poly((W, H), [(150, 30), (W - 150, 30), (W - 120, 80), (W - 150, 140), (150, 140), (120, 80)])
    over(out, solid(grow(ban, 8), WHITE))
    over(out, solid(ban, NAVY))
    t = solid(text("SUPER BOWL", 200, wa.BLACK, 0.14), WHITE)
    wa.paste_c(out, wa.fit(t, 640, 70), W / 2, 86)
    num, _ = numeral_mask("XXIII", 240, weight=0.25, serif=0.12)
    ni = rgba(num.size)
    over(ni, solid(num, RED))
    over(ni, solid(ring(shrink(num, 14), 6), WHITE))
    ni = wa.outline(ni, NAVY, 8)
    wa.paste_c(out, wa.fit(ni, 920, 250), W / 2, 285)
    return bbox_crop(out)


def m_XXXVIII():
    W, H = 1200, 860
    out = rgba((W, H))
    oval = L((W, H))
    ImageDraw.Draw(oval).ellipse([40, 60, W - 40, H - 60], fill=255)
    over(out, solid(grow(oval, 16), RED))
    over(out, fill(oval, gradient((W, H), [(0, (255, 214, 64)), (1, (236, 160, 20))])))
    inner = L((W, H))
    d = ImageDraw.Draw(inner)
    d.rounded_rectangle([170, 210, W - 170, H - 210], radius=120, fill=255)
    for k in range(5):  # scallops
        x = 250 + k * (W - 500) / 4
        d.ellipse([x - 60, 150, x + 60, 270], fill=255)
        d.ellipse([x - 60, H - 270, x + 60, H - 150], fill=255)
    over(out, solid(grow(inner, 10), RED))
    over(out, solid(inner, NAVY))
    for word, y in (("SUPER", 245), ("BOWL", H - 245)):
        t = solid(text(word, 200, wa.BLACK, 0.12), WHITE)
        wa.paste_c(out, wa.fit(t, 320, 70), W / 2, y)
    num, _ = numeral_mask("XXXVIII", 220, weight=0.23, serif=0.12)
    ni = rgba(num.size)
    over(ni, fill(num, gradient(num.size, [(0, (255, 226, 96)), (1, (230, 150, 20))])))
    ni = wa.outline(ni, RED, 9)
    ni = wa.outline(ni, (255, 236, 150), 5)
    wa.paste_c(out, wa.fit(ni, W * 0.86, 230), W / 2, H / 2)
    return bbox_crop(out)


def m_XLII():
    W, H = 1100, 900
    out = rgba((W, H))
    plate = poly((W, H), [(230, 90), (W - 120, 50), (W - 150, 250), (W - 60, 270), (W - 120, 640),
                          (W / 2 + 120, 780), (W / 2 - 10, 840), (W / 2 - 140, 790), (150, 640), (60, 280),
                          (200, 250)])
    over(out, solid(grow(plate, 16), WHITE))
    over(out, fill(plate, gradient((W, H), [(0, (178, 22, 44)), (1, (120, 10, 34))], 70.0)))
    tag = poly((W, H), [(250, 110), (W - 160, 70), (W - 190, 190), (280, 230)])
    over(out, solid(tag, (220, 40, 60)))
    t = solid(text("SUPER", 200, wa.BLACK_IT, 0.10), WHITE)
    t = t.rotate(5, resample=Image.BICUBIC, expand=True)
    wa.paste_c(out, wa.fit(t, 440, 120), W * 0.52, 150)
    num, _ = numeral_mask("XLII", 360, weight=0.25, serif=0.0, slant=0.18)
    ni = rgba(num.size)
    over(ni, fill(num, gradient(num.size, [(0, (90, 220, 240)), (1, (20, 160, 200))])))
    over(ni, bevel(num, (210, 250, 255), (10, 90, 130), 14))
    ni = wa.outline(ni, NAVY, 14)
    ni = wa.outline(ni, WHITE, 8)
    ni = ni.rotate(5, resample=Image.BICUBIC, expand=True)
    wa.paste_c(out, wa.fit(ni, W * 0.86, 440), W * 0.50, 440)
    b = solid(text("BOWL", 200, wa.BLACK, 0.12), WHITE)
    wa.paste_c(out, wa.fit(b, 300, 90), W * 0.50, 730)
    st = poly((W, H), wa.star_pts(W * 0.78, 740, 30))
    over(out, solid(st, WHITE))
    return bbox_crop(out)


def m_XLIII():
    W, H = 1300, 700
    out = rgba((W, H))
    field = poly((W, H), [(60, 470), (W - 60, 470), (W / 2 + 60, 690), (W / 2 - 60, 690)])
    over(out, solid(grow(field, 10), WHITE))
    over(out, fill(field, gradient((W, H), [(0, (90, 170, 60)), (1, (30, 110, 40))])))
    ln = L((W, H))
    d = ImageDraw.Draw(ln)
    for k in range(-4, 5):
        d.line([(W / 2 + k * 120, 480), (W / 2 + k * 18, 690)], fill=255, width=6)
    over(out, solid(ImageChops.multiply(ln, field), WHITE))
    t = wa.outline(solid(text("SUPER BOWL", 200, wa.BLACK_IT, 0.12), (24, 60, 150)), WHITE, 6)
    wa.paste_c(out, wa.fit(t, 560, 90), W / 2, 120)
    for sx in (W * 0.20, W * 0.80):
        over(out, solid(poly((W, H), wa.star_pts(sx, 205, 34)), (210, 30, 40)))
    num, xs = numeral_mask("XLIII", 260, weight=0.24, serif=0.0)
    ni = rgba(num.size)
    over(ni, fill(num, gradient(num.size, [(0, (40, 90, 190)), (1, (16, 44, 120))])))
    over(ni, bevel(num, (160, 200, 255), (8, 20, 70), 12))
    ni = wa.outline(ni, (220, 226, 236), 10)
    ni = wa.outline(ni, NAVY, 5)
    # an arch: each column of the numerals lifted along a circle
    a = np.asarray(ni)
    hgt = a.shape[0]
    lift = (np.cos(np.linspace(-1.0, 1.0, a.shape[1])) - math.cos(1.0)) * hgt * 0.55
    bent = np.zeros((hgt + int(lift.max()) + 2, a.shape[1], 4), np.uint8)
    for x in range(a.shape[1]):
        o = int(lift.max() - lift[x])
        bent[o:o + hgt, x] = a[:, x]
    ni = Image.fromarray(bent, "RGBA")
    wa.paste_c(out, wa.fit(ni, W * 0.86, 330), W / 2, 330)
    return bbox_crop(out)


def m_XLIV():
    W, H = 1500, 600
    out = rgba((W, H))
    num, xs = numeral_mask("XLIV", 460, weight=0.26, serif=0.0)
    ni = rgba(num.size)
    over(ni, fill(num, gradient(num.size, [(0, (255, 120, 40)), (1, (226, 70, 20))])))
    over(ni, bevel(num, (255, 200, 150), (150, 40, 10), 14))
    ni = wa.outline(ni, NAVY, 16)
    wa.paste_c(out, wa.fit(ni, W * 0.80, 520), W / 2, H / 2)
    band = poly((W, H), [(40, 250), (W - 40, 250), (W - 10, 300), (W - 40, 350), (40, 350), (10, 300)])
    over(out, solid(grow(band, 8), WHITE))
    over(out, solid(band, (232, 64, 24)))
    for word, cx in (("SUPER", W * 0.27), ("BOWL", W * 0.73)):
        t = solid(text(word, 200, wa.BLACK, 0.14), WHITE)
        wa.paste_c(out, wa.fit(t, 360, 70), cx, 300)
    ball = L((W, H))
    ImageDraw.Draw(ball).ellipse([W / 2 - 90, 250, W / 2 + 90, 350], fill=255)
    over(out, solid(grow(ball, 8), WHITE))
    over(out, fill(ball, gradient((W, H), [(0, (150, 80, 40)), (1, (90, 40, 20))])))
    lace = L((W, H))
    d = ImageDraw.Draw(lace)
    d.line([(W / 2 - 40, 300), (W / 2 + 40, 300)], fill=255, width=6)
    for k in range(4):
        x = W / 2 - 30 + k * 20
        d.line([(x, 288), (x, 312)], fill=255, width=5)
    over(out, solid(lace, WHITE))
    return bbox_crop(out)


EVENT_MARKS = {
    "XXIII": m_XXIII, "XXXVIII": m_XXXVIII, "XLII": m_XLII, "XLIII": m_XLIII, "XLIV": m_XLIV,
    "XLVI": lambda: trophy_stadium("XLVI", "lucas"), "XLVII": lambda: trophy_stadium("XLVII", "superdome"),
    "XLIX": lambda: trophy_stadium("XLIX", "uop"), "LI": m_LI, "LII": m_LII, "LIV": m_LIV, "LVI": m_LVI,
    "LVIII": m_LVIII, **{w: (lambda w=w: m_generic(w)) for w in FRANCHISE_GENERIC},
}


def team_mark(row, code, season):
    """The club's mark for a team flank: the mod's own logo where it is the season's, else a club roundel."""
    if (row, code) not in wa.PERIOD_LOGO_GAPS:
        a = wa.logo_mark(code)
        if a is not None:
            return Image.fromarray(a, "RGBA")
    return wa.roundel(dict(row=row), code, 512, 512)


# --- output --------------------------------------------------------------------------------------------------------

def reduce(im):
    im = bbox_crop(im, 2)
    f = min(1.0, MAX_SIDE / max(im.size))
    if f < 1.0:
        im = im.resize((max(1, round(im.width * f)), max(1, round(im.height * f))), Image.LANCZOS)
    return im


def png_bytes(im):
    import io
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def build():
    """{relative file: PNG bytes} and the manifest."""
    files, marks = {}, {}

    def add(key, im):
        im = reduce(im)
        rel = f"marks/{key}.png"
        files[rel] = png_bytes(im)
        marks[key] = dict(file=rel, size=list(im.size), sha256=hashlib.sha256(files[rel]).hexdigest())

    for key, draw in EVENT_MARKS.items():
        add(key, draw())
    rows = []
    for row, (event, season, kind, yard, box, teams) in sorted(ROWS.items()):
        entry = dict(row=row, event=event, season=season,
                     flank=dict(kind=kind, from_mid_yd=yard, box_yd=list(box)))
        if teams:
            entry["flank"]["teams"] = teams
            for code in teams.values():
                add(f"{code}_{season}", team_mark(row, code, season))
        rows.append(entry)
    doc = dict(schema=SCHEMA, note=(
        "sb1: Super Bowl flank marks on the Anniversary fields (yards measured on the reference field diagrams). "
        "Marks are authored from geometry and type (tools/nfl2k5_super_bowl_marks_art.py); LXII to LXV are generic "
        "current-system marks for franchise seasons whose logo is not revealed. The user's super_bowl/<NUMERALS>.png "
        "and teams/<CODE>[_<SEASON>].png replace them at build time."),
        rows=rows, franchise_generic=list(FRANCHISE_GENERIC), marks=dict(sorted(marks.items())))
    return files, doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true", help="fail when the shipped files differ from a fresh render")
    args = ap.parse_args(argv)
    files, doc = build()
    manifest = (json.dumps(doc, indent=1) + "\n").encode()
    if args.check:
        bad = [rel for rel, raw in files.items() if not (args.out / rel).is_file()
               or (args.out / rel).read_bytes() != raw]
        if (args.out / "manifest.json").read_bytes() != manifest:
            bad.append("manifest.json")
        print(json.dumps(dict(check="differs" if bad else "same", files=bad)))
        return 1 if bad else 0
    for rel, raw in files.items():
        p = args.out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    (args.out / "manifest.json").write_bytes(manifest)
    print(json.dumps(dict(written=len(files), out=str(args.out))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
