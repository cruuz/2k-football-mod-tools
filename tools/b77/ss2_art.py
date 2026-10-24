"""Seamen logo art (job b778 ss2): the Sarasota Seamen anchor, wordmark and card background, drawn from vector data.

The 2006 SOFTDRINKTV Madden 07 episodes show the team logo as a teal anchor with a heavy black outline, curved
arms with arrowhead flukes, inner highlight cuts on the ring and flukes, and an italic SEAMEN wordmark at the
bottom right of a mint honeycomb card. ``ss2_anchor.json`` holds that shape as smoothed polygon outlines on a
1536 unit square (the card as the game draws it), the honeycomb tile measured from the card, the card gradient
and the sampled colours (anchor fill 02A081, outline near black, wordmark 1B1A1C). Everything here is drawn at
4x and box-reduced, so edges are smooth and the output is reproducible without the video.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover - authoring tool only
    cv2 = None

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "ss2_anchor.json").read_text())
G = DATA["size"]                      # 1536
FILL = tuple(DATA["colours"]["fill"])
INK = tuple(DATA["colours"]["ink"])
WORD = tuple(DATA["colours"]["word"])
BAND_TOP = DATA["band_top"]
SS = 4


def _poly_mask(contours, size, scale, ox=0.0, oy=0.0):
    """Even-odd fill of the contour list into a uint8 mask (nested contours cut holes)."""
    mask = np.zeros((size, size), np.uint8)
    for c in contours:
        pts = np.round((np.array(c, np.float64) * scale + [ox, oy]) * 16).astype(np.int32)
        layer = np.zeros_like(mask)
        cv2.fillPoly(layer, [pts], 255, lineType=cv2.LINE_8, shift=4)
        mask ^= layer
    return mask


def _reduce(a, factor):
    h, w = a.shape[:2]
    a = a.reshape(h // factor, factor, w // factor, factor, *a.shape[2:]).astype(np.float32)
    return a.mean(axis=(1, 3))


def layers(size, scale=1.0, ox=0.0, oy=0.0, ss=SS):
    """(ink, fill, word) coverage arrays 0..1 at ``size`` pixels; the anchor drawn at ``scale`` x its card size."""
    big = size * ss
    s = big / G * scale
    ink = _poly_mask(DATA["ink"], big, s, ox * ss, oy * ss)
    fill = _poly_mask(DATA["fill"], big, s, ox * ss, oy * ss)
    word = _poly_mask(DATA["word"], big, s, ox * ss, oy * ss)
    k = max(1, int(round(3 * s)))
    # the outline layer also sits under the fill, so no seam can show between the two
    ink = np.maximum(ink, cv2.dilate(fill, np.ones((k, k), np.uint8)))
    return tuple(_reduce(m, ss) / 255.0 for m in (ink, fill, word))


def _hex_pattern(size, u0=0.0, v0=0.0, span=1.0):
    """Luminance offsets of the card's honeycomb (flattened hexagon cells, measured pitch) over a ``size`` square."""
    hx = DATA["hex"]
    px, ph = hx["pitch"]
    cx0, cy0 = hx["centre"]
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    x = (u0 + (xx + 0.5) / size * span) * G
    y = (v0 + (yy + 0.5) / size * span) * G
    k0 = np.floor((y - cy0) / ph + 0.5).astype(int)
    kfac = px * 0.8660254 / ph
    ds, rows = [], []
    for dk in (-1, 0, 1):
        k = k0 + dk
        off = (k % 2) * (px / 2)
        n0 = np.floor((x - cx0 - off) / px + 0.5)
        for dn in (-1, 0, 1):
            cx = cx0 + off + (n0 + dn) * px
            cy = cy0 + k * ph
            ds.append(np.hypot(x - cx, (y - cy) * kfac))
            rows.append(np.full(x.shape, dk))
    ds, rows = np.stack(ds), np.stack(rows)
    order = np.argsort(ds, axis=0)
    d1 = np.take_along_axis(ds, order[:1], 0)[0]
    d2 = np.take_along_axis(ds, order[1:2], 0)[0]
    r1 = np.take_along_axis(rows, order[:1], 0)[0]
    r2 = np.take_along_axis(rows, order[1:2], 0)[0]
    e = (d2 - d1) / 2 / px
    amp = np.where(r1 == r2, hx["amp_side"], hx["amp_row"])
    line = np.exp(-(e / hx["width"]) ** 2)
    pat = -hx["amp_in"] + (hx["amp_in"] + amp) * line
    return pat - hx["mean"]


def card_background(size=256):
    """The card's mint gradient with the honeycomb and the lighter band under the wordmark."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    u = (xx + 0.5) / size
    v = (yy + 0.5) / size
    terms = [np.ones_like(u), u, v, u * v, u * u, v * v]
    main = np.stack([sum(c * t for c, t in zip(coefs, terms)) for coefs in DATA["bg_main"]], -1)
    plane = [np.ones_like(u), u, v]
    band = np.stack([sum(c * t for c, t in zip(coefs, plane)) for coefs in DATA["bg_band"]], -1)
    # the band is a translucent lighter strip: blend with a soft edge
    edge = np.clip((v - BAND_TOP) * size + 0.5, 0, 1)[..., None]
    rgb = main * (1 - edge) + band * edge
    # keep the gradient smooth where the quadratic bends: clamp the main fit to the band's range
    rgb = rgb + _hex_pattern(size)[..., None] * 0.9
    return np.clip(rgb, 0, 255)


def _compose(base, cover, rgb):
    c = cover[..., None]
    return base * (1 - c) + np.array(rgb, np.float32) * c


def logo_card(size=256, wordmark=True):
    """The Seamen logo card: honeycomb card, anchor, SEAMEN wordmark (RGBA, opaque)."""
    ss = 2 if size >= 128 else 4
    big = size * ss
    base = card_background(big)
    ink, fill, word = layers(big, ss=1)
    rgb = _compose(base, ink, INK)
    rgb = _compose(rgb, fill, FILL)
    if wordmark:
        rgb = _compose(rgb, word, WORD)
    out = _reduce(rgb, ss)
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8)).convert("RGBA")


def sprite(height, ink_rgb=INK, fill_rgb=FILL, pad=0.04, outline=1.0, ss=SS, word=False):
    """The anchor alone on transparency, cropped to its outline, ``height`` pixels tall (RGBA)."""
    ys, xs = None, None
    ink, fill, _ = layers(512, ss=1)
    m = ink > 0.2
    # anchor only (exclude the wordmark band)
    m[int(0.84 * 512):] = False
    ys, xs = np.where(m)
    y0, y1, x0, x1 = ys.min() / 512 * G, (ys.max() + 1) / 512 * G, xs.min() / 512 * G, (xs.max() + 1) / 512 * G
    h_units = (y1 - y0) * (1 + 2 * pad)
    w_units = (x1 - x0) * (1 + 2 * pad)
    scale = height / h_units
    width = int(np.ceil(w_units * scale))
    big_w, big_h = width * ss, height * ss
    s = big_h / h_units
    ox = -(x0 - (x1 - x0) * pad) * s
    oy = -(y0 - (y1 - y0) * pad) * s
    canvas = max(big_w, big_h)
    inkm = _poly_mask(DATA["ink"], canvas, s, ox, oy)[:big_h, :big_w]
    fillm = _poly_mask(DATA["fill"], canvas, s, ox, oy)[:big_h, :big_w]
    k = max(1, int(round(3 * s / (big / G) if False else 3 * s)))
    inkm = np.maximum(inkm, cv2.dilate(fillm, np.ones((k, k), np.uint8)))
    cov_ink = _reduce(inkm, ss) / 255.0
    cov_fill = _reduce(fillm, ss) / 255.0
    rgb = np.zeros(cov_ink.shape + (3,), np.float32)
    rgb[:] = ink_rgb
    c = cov_fill[..., None]
    rgb = rgb * (1 - c) + np.array(fill_rgb, np.float32) * c
    alpha = np.clip(np.maximum(cov_ink, cov_fill), 0, 1)
    out = np.dstack([np.clip(rgb + 0.5, 0, 255), alpha * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def wordmark_sprite(height, rgb=WORD, ss=SS):
    """SEAMEN alone on transparency, ``height`` pixels tall."""
    pts = np.concatenate([np.array(c) for c in DATA["word"]])
    x0, y0 = pts.min(0)
    x1, y1 = pts.max(0)
    scale = height / (y1 - y0)
    width = int(np.ceil((x1 - x0) * scale))
    big_w, big_h = width * ss, height * ss
    s = big_h / (y1 - y0)
    canvas = max(big_w, big_h)
    m = _poly_mask(DATA["word"], canvas, s, -x0 * s, -y0 * s)[:big_h, :big_w]
    cov = _reduce(m, ss) / 255.0
    out = np.zeros(cov.shape + (4,), np.uint8)
    out[..., :3] = rgb
    out[..., 3] = np.clip(cov * 255 + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _signed_area(points):
    a = np.asarray(points, np.float64)
    return 0.5 * float(np.sum(a[:, 0] * np.roll(a[:, 1], -1) - np.roll(a[:, 0], -1) * a[:, 1]))


def anchor_polys(cx, cy, height, rot180=False):
    """The anchor as nested polygons in texel coordinates, ``height`` texels tall centred on (cx, cy):
    ``ink`` the whole outlined silhouette, ``fill`` the teal body, ``islands`` the ink cut-outs inside the body
    (the ring and the fluke highlights). Paint them in that order (kit painter ``multipoly``)."""
    sil = max(DATA["ink"], key=lambda c: abs(_signed_area(c)))
    pts = np.asarray(sil, np.float64)
    x0, y0 = pts.min(0)
    x1, y1 = pts.max(0)
    s = height / (y1 - y0)
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    sign = -1.0 if rot180 else 1.0

    def place(c):
        a = (np.asarray(c, np.float64) - [mx, my]) * s * sign
        return (a + [cx, cy]).tolist()

    fills = sorted(DATA["fill"], key=lambda c: -abs(_signed_area(c)))
    body, holes = fills[0], fills[1:]
    return {"ink": [place(sil)], "fill": [place(body)], "islands": [place(h) for h in holes]}
