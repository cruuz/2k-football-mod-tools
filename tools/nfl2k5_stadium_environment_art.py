#!/usr/bin/env python3
"""The shared stadium environment kit's art (st3, 2026-09-28): deterministic drawings at 4x masters reduced to their
native sizes, for every modern stadium's surroundings (nfl2k5_stadium_environment).

Shared tiles: the surface lots with their rows of parked cars, a road lane with its dashed line, grass, tree crowns
(and, pass 3, the round crowns' leaves),
water, building walls (a night drawing with lit windows) and roofs, a white tile the haze takes its colour from by
vertex, and the far ground seen from the air (city blocks, dry suburbs with their pools, green suburbs). Per venue: the
horizon band, drawn from the venue's layout (data/nfl2k5_stadium_environment/VENUE.json: the terrain's elevation angle
round the compass and the tall buildings out to 15 km), by day (white: the haze colour comes by vertex) and at night.

    python3 tools/nfl2k5_stadium_environment_art.py OUT_DIR [--masters DIR] [--venues s00 s15 ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nfl2k5_highmark_model_art as base  # noqa: E402  (landed; its helpers only)

ROOT = Path(__file__).resolve().parents[1]
LAYOUTS = ROOT / "data" / "nfl2k5_stadium_environment"
SCALE = base.SCALE
rng, reduce = base.rng, base.reduce
#: the horizon band's rows: BAND_TOP metres over the street at the top, BAND_FOOT under it at the bottom (the kit's
#: cylinder uses the same numbers), and the haze's own height at the foot
BAND_RADIUS, BAND_TOP, BAND_FOOT, HAZE_H = 1800.0, 240.0, 12.0, 10.0
BAND_PAD = 0.125                 # the clear top eighth (the kit maps the cylinder's top edge to it)
#: a car park's cars (the common colours on US roads: white, black, grey, silver, blue, red, beige, dark green)
CARS = [(236, 236, 234), (26, 26, 28), (112, 114, 118), (178, 180, 184), (40, 58, 110), (150, 28, 30),
        (196, 184, 160), (40, 62, 48), (236, 236, 234), (178, 180, 184), (26, 26, 28), (70, 72, 78)]


def _noise(W, H, seed, radius, lo, hi):
    n = base._blur(rng(seed).random((H, W)), radius)
    n = (n - n.min()) / max(1e-6, float(n.max() - n.min()))
    return lo + (hi - lo) * n


def _grey(W, H, seed, radius, lo, hi, tint=(1.0, 1.0, 1.0)):
    n = _noise(W, H, seed, radius, lo, hi)
    return np.clip(np.stack([n * t for t in tint], axis=-1), 0, 255)


def _img(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _wrap_rect(d, box, fill, W, H):
    """A rectangle drawn on a tile that wraps (its copies one tile over, so the tile repeats seamlessly)."""
    x0, y0, x1, y1 = box
    for ox in (-W, 0, W):
        for oy in (-H, 0, H):
            d.rectangle([x0 + ox, y0 + oy, x1 + ox, y1 + oy], fill=fill)


def lot(size=(64, 64)):
    """One tile of a surface lot: six 2.7 m stalls across (u) and, along v, a row of stalls (5.5 m), the 8 m aisle and
    the facing row (19 m a repeat); about nine in ten stalls hold a car (a game-day lot)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = _grey(W, H, 101, SCALE, 62, 82)
    im = _img(a)
    d = ImageDraw.Draw(im)
    r = rng(103)
    rows = ((0.0, 5.5 / 19.0), (13.5 / 19.0, 1.0))
    for k in range(7):
        x = int(round(k * W / 6)) % W
        for y0, y1 in rows:
            d.rectangle([x - SCALE // 2, int(y0 * H), x + SCALE // 2, int(y1 * H) - 1], fill=(214, 214, 206))
    for y0, y1 in rows:
        for k in range(6):
            if r.random() < 0.1:
                continue
            c = CARS[int(r.integers(len(CARS)))]
            cx0, cx1 = k * W / 6 + W / 6 * 0.17, (k + 1) * W / 6 - W / 6 * 0.17
            depth = (y1 - y0) * H
            front = y1 * H if y0 == 0.0 else y0 * H      # the car's nose at the aisle side
            sgn = 1 if y0 == 0.0 else -1               # the car runs from its nose back into the stall
            cy_a, cy_b = front - sgn * depth * 0.08, front - sgn * depth * 0.90
            ya, yb = sorted((cy_a, cy_b))
            d.rounded_rectangle([cx0, ya, cx1, yb], radius=SCALE * 2, fill=c)
            # the windscreen and the rear window (dark bands) and the roof between them
            L = yb - ya
            ws = (front - sgn * depth * 0.30, front - sgn * depth * 0.38)
            rw = (front - sgn * depth * 0.70, front - sgn * depth * 0.77)
            for w0, w1 in (ws, rw):
                d.rectangle([cx0 + SCALE, min(w0, w1), cx1 - SCALE, max(w0, w1)], fill=(34, 38, 44))
            roof = tuple(int(min(255, v * 1.08 + 8)) for v in c)
            d.rectangle([cx0 + SCALE * 2, min(ws[1], rw[0]), cx1 - SCALE * 2, max(ws[1], rw[0])], fill=roof)
            _ = L
    return im


def road(size=(32, 64)):
    """One lane (u across it, 12 m along v a repeat): worn asphalt, the dashed white line at its left edge (3 m of paint,
    9 m of gap) and the darker wheel tracks."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = _grey(W, H, 111, SCALE, 58, 74)
    for u0 in (0.28, 0.72):
        x0, x1 = int((u0 - 0.08) * W), int((u0 + 0.08) * W)
        a[:, x0:x1] *= 0.9
    im = _img(a)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, max(1, int(W * 0.05)), int(H * 0.25)], fill=(222, 222, 214))
    return im


def green(size=(32, 32)):
    """Grass and leaves in one tile (the lawns and parks, and the tree crowns darker by vertex): clumps in dark and mid
    greens."""
    W, H = size[0] * SCALE, size[1] * SCALE
    n1 = _noise(W, H, 131, SCALE, 0, 1)
    n2 = _noise(W, H, 132, SCALE * 3, 0, 1)
    v = 0.55 * n1 + 0.45 * n2
    return _img(np.stack([56 + 50 * v, 88 + 64 * v, 40 + 32 * v], axis=-1))


def leaf(size=(32, 32)):
    """The round tree crowns' leaves (pass 3): clumps of dark, mid and sunlit greens with shadowed gaps, seamless."""
    W, H = size[0] * SCALE, size[1] * SCALE
    fine = _noise(W, H, 171, SCALE, 0, 1)
    clump = _noise(W, H, 172, SCALE * 2, 0, 1)
    v = 0.65 * fine + 0.35 * clump
    rgb = np.stack([26 + 84 * v, 48 + 110 * v, 20 + 44 * v], axis=-1)
    rgb[(fine > 0.72) & (clump > 0.4)] *= 1.25            # sunlit leaves
    rgb[(fine < 0.3) | (clump < 0.2)] *= 0.55             # the shade between the clumps
    return _img(rgb)


def block(size=(32, 32), night=False):
    """Walls: 3.5 m floors, windows 1.8 m apart (8 m and 3.5 m a repeat along u and v), light concrete and glass by day;
    at night dark walls with about four windows in ten lit."""
    W, H = size[0] * SCALE, size[1] * SCALE
    if night:
        a = _grey(W, H, 151, SCALE, 26, 38, (1.0, 1.0, 1.15))
    else:
        a = _grey(W, H, 151, SCALE, 146, 170, (1.0, 0.96, 0.9))
    im = _img(a)
    d = ImageDraw.Draw(im)
    r = rng(153)
    cols, rows = 4, 1
    for i in range(cols):
        for j in range(rows):
            x0, x1 = int((i + 0.2) * W / cols), int((i + 0.8) * W / cols)
            y0, y1 = int((j + 0.25) * H / rows), int((j + 0.75) * H / rows)
            if night:
                c = (255, 214, 140) if r.random() < 0.4 else (18, 20, 28)
            else:
                c = (60, 70, 84) if r.random() < 0.8 else (96, 106, 118)
            d.rectangle([x0, y0, x1, y1], fill=c)
    return im


def white(size=(8, 8)):
    return Image.new("RGB", (size[0] * SCALE, size[1] * SCALE), (255, 255, 255))


def _houses(d, r, W, H, n, roofs, lot_px, pools=0.0):
    for _ in range(n):
        x, y = int(r.integers(W)), int(r.integers(H))
        w, h = int(lot_px * (0.5 + 0.4 * r.random())), int(lot_px * (0.4 + 0.3 * r.random()))
        _wrap_rect(d, [x, y, x + w, y + h], roofs[int(r.integers(len(roofs)))], W, H)
        if r.random() < pools:
            _wrap_rect(d, [x + w + SCALE, y, x + w + SCALE * 3, y + SCALE * 2], (112, 166, 176), W, H)


def far_dry(size=(64, 64)):
    """The Valley of the Sun from the air, 240 m a repeat: tan ground, curving grey streets, houses with tile roofs and
    their pools, a few trees."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = _grey(W, H, 171, SCALE * 2, 150, 176, (1.0, 0.92, 0.78))
    im = _img(a)
    d = ImageDraw.Draw(im)
    r = rng(173)
    for k in range(4):
        y = int((k + 0.5) * H / 4 + r.integers(-SCALE * 2, SCALE * 2))
        for ox in (-W, 0, W):
            d.line([(ox, y), (ox + W // 3, y + SCALE * 3), (ox + 2 * W // 3, y - SCALE * 2), (ox + W, y)],
                   fill=(120, 118, 114), width=SCALE * 2)
    _houses(d, r, W, H, 90, [(170, 132, 112), (156, 122, 104), (190, 182, 168), (146, 142, 136)], SCALE * 4, pools=0.12)
    for _ in range(40):
        x, y = int(r.integers(W)), int(r.integers(H))
        _wrap_rect(d, [x, y, x + SCALE * 2, y + SCALE * 2], (78, 96, 54), W, H)
    return im


def far_urban(size=(64, 64)):
    """City blocks from the air, 240 m a repeat: a street grid (about 100 m blocks), roofs in greys and browns, lots
    and street trees."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = _grey(W, H, 181, SCALE * 2, 96, 116)
    im = _img(a)
    d = ImageDraw.Draw(im)
    r = rng(183)
    step = W // 2
    for k in range(2):
        for off in (0,):
            x = k * step + off
            d.rectangle([x, 0, x + SCALE * 3, H], fill=(70, 70, 72))
            y = k * (H // 2)
            d.rectangle([0, y, W, y + SCALE * 3], fill=(70, 70, 72))
    for bx in range(2):
        for by in range(2):
            x0, y0 = bx * step + SCALE * 5, by * (H // 2) + SCALE * 5
            x1, y1 = x0 + step - SCALE * 8, y0 + H // 2 - SCALE * 8
            if r.random() < 0.25:
                d.rectangle([x0, y0, x1, y1], fill=(84, 84, 86))
                for cy in range(y0 + SCALE * 2, y1 - SCALE * 2, SCALE * 3):
                    for cx in range(x0 + SCALE, x1 - SCALE, SCALE * 2):
                        if r.random() < 0.7:
                            d.rectangle([cx, cy, cx + SCALE, cy + SCALE * 2 - 1], fill=CARS[int(r.integers(len(CARS)))])
                continue
            n = int(r.integers(2, 5))
            for _ in range(n):
                w = int((x1 - x0) * (0.3 + 0.5 * r.random()))
                h = int((y1 - y0) * (0.3 + 0.5 * r.random()))
                xa, ya = x0 + int(r.integers(max(1, x1 - x0 - w))), y0 + int(r.integers(max(1, y1 - y0 - h)))
                g = int(r.integers(118, 176))
                d.rectangle([xa, ya, xa + w, ya + h], fill=(g, g - int(r.integers(0, 14)), g - int(r.integers(0, 20))))
    for _ in range(30):
        x, y = int(r.integers(W)), int(r.integers(H))
        _wrap_rect(d, [x, y, x + SCALE * 2, y + SCALE * 2], (70, 86, 62), W, H)
    return im


def far_green(size=(64, 64)):
    """Green suburbs from the air, 240 m a repeat: lawns and tree canopy, curving streets, houses."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = _grey(W, H, 191, SCALE * 2, 0, 1)
    g = np.stack([70 + 30 * a[..., 0], 100 + 34 * a[..., 0], 52 + 20 * a[..., 0]], axis=-1)
    im = _img(g)
    d = ImageDraw.Draw(im)
    r = rng(193)
    for k in range(3):
        y = int((k + 0.5) * H / 3)
        for ox in (-W, 0, W):
            d.line([(ox, y), (ox + W // 2, y + SCALE * 4), (ox + W, y)], fill=(118, 118, 116), width=SCALE * 2)
    _houses(d, r, W, H, 50, [(92, 92, 96), (128, 100, 84), (170, 168, 160)], SCALE * 4)
    for _ in range(120):
        x, y = int(r.integers(W)), int(r.integers(H))
        _wrap_rect(d, [x, y, x + SCALE * 3, y + SCALE * 3], (44, 72, 38), W, H)
    return im


FAR = {"dry": far_dry, "urban": far_urban, "green": far_green}


#: the towers a stadium model draws itself (height from, within): U.S. Bank and Lucas Oil keep downtown's towers of
#: 90 m and more as boxes (their footprints' towers, to 2.6 km)
STYLE_SKIP = {"s15": (90.0, 2600.0), "s11": (90.0, 2600.0)}
#: or exactly the ways a model draws itself (its footprint's list): Mercedes-Benz's skyline boxes, Allegiant's Strip
SKIP_WAYS = {"s01": ("data/nfl2k5_mercedes_benz_model/footprint.json", "skyline"),
             "s20": ("data/nfl2k5_allegiant_model/footprint.json", "strip")}


def _skip_ways(venue):
    if venue not in SKIP_WAYS:
        return set()
    path, key = SKIP_WAYS[venue]
    fp = json.loads((ROOT / path).read_text(encoding="utf-8"))
    return {int(e["way"]) for e in fp.get(key, []) if e.get("way") is not None}


def layout(venue):
    return json.loads((LAYOUTS / f"{venue}.json").read_text(encoding="utf-8"))


def band(venue, size=(256, 32), night=False):
    """The horizon band round the compass (u = bearing / 360, v from BAND_TOP over the street at the top down to
    BAND_FOOT under it): the haze at the foot (HAZE_H high), the terrain's ridges at their elevation angle, the tall
    buildings (lit windows at night); clear sky above them (alpha 0)."""
    L = layout(venue)
    W, H = size[0] * SCALE, size[1] * SCALE
    span = BAND_TOP + BAND_FOOT
    pad = int(round(BAND_PAD * H))
    row = lambda h: pad + int(round((BAND_TOP - h) / span * (H - pad)))  # noqa: E731
    rgb = np.zeros((H, W, 3), np.float64)
    alpha = np.zeros((H, W), np.float64)
    if night:
        haze, ridge, tower = np.array([30, 34, 48.0]), np.array([20, 22, 32.0]), np.array([16, 18, 26.0])
    else:
        haze, ridge, tower = np.array([255, 255, 255.0]), np.array([206, 208, 214.0]), np.array([168, 172, 180.0])
    prof = np.array(L["terrain"], float)
    for x in range(W):
        b = (x + 0.5) / W * 360.0
        i0 = int(b) % 360
        f = b - int(b)
        ang = prof[i0] * (1 - f) + prof[(i0 + 1) % 360] * f
        h = BAND_RADIUS * math.tan(math.radians(max(0.0, ang)))
        top = row(max(HAZE_H, h))
        rgb[top:, x] = ridge
        alpha[top:, x] = 1.0
        # aerial perspective: the ridge lightens toward its foot
        foot = row(HAZE_H)
        if foot > top:
            t = np.linspace(0, 1, foot - top)[:, None]
            rgb[top:foot, x] = ridge * (1 - 0.35 * t) + haze * 0.35 * t
    r = rng(211 + int(venue[1:]))
    skip_h, skip_d = STYLE_SKIP.get(venue, (1e9, 0.0))
    ways = _skip_ways(venue)
    for brg, aw, ah, dist, hm, way in L["skyline"]:
        if (hm >= skip_h and dist <= skip_d) or int(way) in ways:
            continue            # a tower the stadium's own model draws as a box
        h = BAND_RADIUS * math.tan(math.radians(ah))
        if h < HAZE_H + 2:
            continue
        x0 = int((brg - aw / 2) / 360.0 * W)
        x1 = max(x0 + 1, int(math.ceil((brg + aw / 2) / 360.0 * W)))
        top = row(h)
        for x in range(x0, x1):
            xx = x % W
            rgb[top:, xx] = tower
            alpha[top:, xx] = 1.0
            if night:
                for y in range(top + 1, row(HAZE_H), max(1, SCALE)):
                    if r.random() < 0.35:
                        rgb[y, xx] = (230, 200, 130)
    foot = row(HAZE_H)
    rgb[foot:] = haze
    alpha[foot:] = 1.0
    a = np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


def drawings(venues, band_sizes):
    out = {
        "env_lot": (lot(), (64, 64)), "env_road": (road(), (32, 64)), "env_green": (green(), (32, 32)),
        "env_block": (block(), (32, 32)), "env_block_n": (block(night=True), (32, 32)), "env_white": (white(), (8, 8)),
        "env_leaf": (leaf(), (32, 32)),
    }
    for k, fn in FAR.items():
        out[f"env_far_{k}"] = (fn(), (64, 64))
    for v in venues:
        size = tuple(band_sizes.get(v, (256, 32)))
        out[f"env_band_{v}"] = (band(v, size), size)
        out[f"env_band_{v}_n"] = (band(v, size, night=True), size)
    return out


def main(argv=None):
    sys.path.insert(0, str(ROOT))
    from mod_editor.core import nfl2k5_stadium_environment as env
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--masters")
    ap.add_argument("--venues", nargs="*", default=None)
    a = ap.parse_args(argv)
    venues = sorted({env.site_of(v) for v in (a.venues if a.venues else env.STYLE)})
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    masters = Path(a.masters) if a.masters else None
    if masters:
        masters.mkdir(parents=True, exist_ok=True)
    manifest = {}
    sizes = {v: env.STYLE[v]["band_size"] for v in venues}
    for name, (master, size) in drawings(venues, sizes).items():
        native = reduce(master, size)
        if name.startswith("env_band_"):
            # crisp silhouettes: the band's alpha is on or off (no half-clear fringe to ghost against the sky)
            a = np.asarray(native.convert("RGBA")).copy()
            a[..., 3] = np.where(a[..., 3] >= 128, 255, 0)
            native = Image.fromarray(a, "RGBA")
        path = out / f"{name}.png"
        native.save(path, optimize=True)
        manifest[name] = dict(size=list(size), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if masters:
            master.save(masters / f"{name}.png", optimize=True)
    old = out / "art.json"
    doc = json.loads(old.read_text()) if old.is_file() else dict(schema="nfl2k5_stadium_environment_art/v1", art={})
    doc["art"].update(manifest)
    old.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print("ENV_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
