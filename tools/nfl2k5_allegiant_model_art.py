#!/usr/bin/env python3
"""Draw the Allegiant Stadium model's art (job st2, 2026-09-25): deterministic, procedural, plain type only.

  python3 tools/nfl2k5_allegiant_model_art.py OUT_DIR [--masters MASTER_DIR]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model, and no logo is drawn (not the Raiders' shield, not the venue's sunburst): every name is
plain type (Roboto Condensed Bold, Apache 2.0). Tones are measured from the reference photos (Commons: the 2021 Vegas
Kickoff Classic interiors, the 2022 Las Vegas Bowl, "Al Davis Memorial Torch Allegiant Stadium 2022", the exterior
photos 2021 to 2024 day and night): the charcoal and black seats, the black field wall, the ETFE roof's bright panels on
the white grid, the black glass drum with its white light lines, the lanai's tall glass, the silver and black torch,
the Bermuda grass mown in bands and the desert ground and ranges.
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
import nfl2k5_highmark_model_art as base  # noqa: E402

SCALE = base.SCALE
rng, _blur, reduce, font, _text, _row = base.rng, base._blur, base.reduce, base.font, base._text, base._row
RAIDERS = dict(silver=(165, 172, 175), black=(0, 0, 0), white=(255, 255, 255), charcoal=(40, 42, 46))


def seat(p_grey, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0. The seats are
    charcoal and black (the 2021 and 2022 interiors), a few mid-grey seats scattered through them (``p_grey``).
    ALG pass 1 (2026-10-08): neutral black seats on dark risers with a thin grey lip, and the aisle stairs a mid
    concrete grey (the 2021 and 2022 photos: the empty sections read near black with faint row lines; the stairs show
    as soft grey stripes, not white ones)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (40, 40, 42))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.10)], fill=(98, 98, 98))
        d.rectangle([0, y0 + int(rh * 0.10), W, y0 + int(rh * 0.28)], fill=(24, 24, 26))
        for c in range(cols):
            x = c * pitch
            basec = (78, 78, 80) if r.random() < p_grey else (34, 34, 37)
            tone = int(r.integers(-5, 6))
            fill = tuple(int(np.clip(v + tone, 0, 255)) for v in basec)
            d.rectangle([x + SCALE, y0 + int(rh * 0.28), x + pitch - SCALE, y0 + int(rh * 0.94)], fill=fill)
    aisle = int(round(W * 0.14 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(104, 103, 100))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(72, 72, 70), width=SCALE)
    return im


def wall(size=(256, 32)):
    """The field wall: black padding with a thin silver line along its top and plain silver type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (8, 8, 10))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.07)], fill=RAIDERS["silver"])
    items = [_text("RAIDERS", RAIDERS["silver"]), _text("LAS VEGAS", RAIDERS["white"]), _text("RAIDERS", RAIDERS["silver"]),
             _text("ALLEGIANT STADIUM", RAIDERS["white"])]
    band = _row(items, W, int(H * 0.93), SCALE * 12, 0.5)
    im.paste(band, (0, int(H * 0.07)), band)
    return im


def _segments(W, h, segs):
    """One LED ribbon band: (background, [type], width fraction) segments side by side, a thin dark seam between."""
    band = Image.new("RGB", (W, h), (6, 6, 8))
    x = 0
    for bg, items, frac in segs:
        sw = min(int(round(W * frac)), W - x)
        seg = Image.new("RGB", (sw, h), bg)
        if items:
            b = _row(items, sw, h, SCALE * 6, 0.58)
            seg.paste(b, (0, 0), b)
        ImageDraw.Draw(seg).rectangle([sw - SCALE // 2, 0, sw, h], fill=(4, 4, 6))
        band.paste(seg, (x, 0))
        x += sw
    return band


def ribbon_lit(size=(256, 64)):
    """ALG pass 1 (2026-10-08): the LED ribbons as the photos show them lit (2021 north end, 2022 Las Vegas Bowl and
    torch photos: continuous bright red and black segments right round the 100-level and 300-level fascias with white
    type, a black game-information segment among them; pass 2: no white grounds, they read as a white band from the
    game cameras). Plain type only, club words, no partner marks. Top half: the 100-level fascia; bottom half: the
    300-level fascia."""
    W, H = size[0] * SCALE, size[1] * SCALE
    h = H // 2
    red, white, black, silver = (206, 22, 32), (244, 244, 246), (8, 8, 10), RAIDERS["silver"]
    top = _segments(W, h, [(red, [_text("LAS VEGAS", white)], 0.30),
                           (black, [_text("RAIDERS", silver)], 0.22),
                           (red, [_text("RAIDER NATION", white)], 0.28),
                           (black, [_text("1ST & 10", white)], 0.20)])
    bottom = _segments(W, h, [(black, [_text("RAIDERS", white)], 0.24),
                              (red, [_text("JUST WIN BABY", white)], 0.34),
                              (black, [_text("LAS VEGAS", silver)], 0.22),
                              (red, [_text("RAIDERS", white)], 0.20)])
    im = Image.new("RGB", (W, H), (0, 0, 0))
    im.paste(top, (0, 0))
    im.paste(bottom, (0, h))
    return im



def black(size=32):
    """The boards' housings and the lanai's frame: near black with faint panel seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (12, 13, 15))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(24, 25, 28), width=SCALE // 2)
        d.line([0, k, S, k], fill=(24, 25, 28), width=SCALE // 2)
    return im



def roof_grid(size=128):
    """ALG pass 1 (2026-10-08): the ETFE roof from below on a plan grid (u across, v along the field; one repeat 24 m):
    bright cushions between white steel, the main members along the field heavier than the cross members (the 2022 Las
    Vegas Bowl photo looking north: long white trusses run toward the lanai, light cross members every few metres)."""
    S = size * SCALE
    r = rng(31)
    a = np.zeros((S, S, 3), np.float32)
    n = _blur(r.random((S // 8, S // 8)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((8, 8)))
    for k, v in enumerate((222, 225, 230)):
        a[..., k] = v * (0.94 + 0.06 * n)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    cell = S // 4
    # the steel reads mid grey: the game's vertex light lifts the bright cushions to white, so lighter lines vanish
    for k in range(0, S, cell // 2):
        d.rectangle([0, k, S, k + SCALE * 2], fill=(150, 152, 160))
    for k in range(0, S, cell):
        d.rectangle([k, 0, k + SCALE * 3, S], fill=(132, 134, 142))
    for k in range(0, S, S // 2):
        d.rectangle([k, 0, k + SCALE * 4, S], fill=(124, 126, 134))
    return im


def truss(size=(64, 32)):
    """ALG pass 1: one bay of the white roof trusses hanging under the ETFE (alpha): top and bottom chords and the
    diagonal lacing, clear between (the 2022 photos; the chords leave a clear top and bottom texel so wrap filtering
    never draws a line)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    white = (226, 228, 232, 255)
    c = SCALE * 3
    d.rectangle([0, SCALE, W, SCALE + c], fill=white)
    d.rectangle([0, H - SCALE - c, W, H - SCALE], fill=white)
    bay = W // 4
    for k in range(4):
        x0 = k * bay
        d.line([x0, SCALE + c, x0 + bay // 2, H - SCALE - c], fill=white, width=SCALE * 2)
        d.line([x0 + bay // 2, H - SCALE - c, x0 + bay, SCALE + c], fill=white, width=SCALE * 2)
        d.rectangle([x0, SCALE, x0 + SCALE * 2, H - SCALE], fill=white)
    return im


def roof_rim(size=64):
    """The roof's outer ring over the stands (the 2021 north-end photo): dark steel trusses with rows of lamps and
    speaker clusters."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (34, 36, 40))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 6):
        d.rectangle([k, 0, k + SCALE * 2, S], fill=(64, 66, 72))
        d.line([0, k, S, k], fill=(52, 54, 58), width=SCALE)
    for x in range(SCALE * 4, S, SCALE * 16):
        d.rectangle([x, S // 2 - SCALE * 2, x + SCALE * 6, S // 2 + SCALE * 2], fill=(236, 232, 220))
    return im


def roof_top(size=64):
    """The roof from above: silver-white ETFE cushions with seams (the aerials)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (214, 218, 222))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 6):
        d.line([x, 0, x, S], fill=(188, 192, 198), width=SCALE)
    return im


def lamps(size=(64, 32)):
    S_w, S_h = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (S_w, S_h), (30, 32, 36))
    d = ImageDraw.Draw(im)
    for x in range(SCALE * 2, S_w, SCALE * 8):
        d.rectangle([x, int(S_h * 0.25), x + SCALE * 5, int(S_h * 0.75)], fill=(255, 252, 244))
    return im


def lanai(size=(64, 64)):
    """The lanai's tall glass (the torch photo, 2022: about ten heavy black mullions across the glass, a thin one between
    each pair and a few thin transoms, the Strip bright beyond; one repeat is 10 m wide, the glass's full height tall):
    the panes nearly clear with a faint blue tint so the skyline behind reads (alpha; ALG pass 3: 64 texels, the
    lines in fractions of the repeat so their mips fade instead of shimmering)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (170, 190, 214, 22))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, int(W * 0.05), H], fill=(14, 15, 18, 255))
    d.rectangle([W // 2, 0, W // 2 + int(W * 0.016), H], fill=(24, 25, 28, 255))
    for y in range(0, H, H // 5):
        d.rectangle([0, y, W, y + max(1, int(H * 0.008))], fill=(24, 25, 28, 255))
    return im


def skyline(size=(128, 32)):
    """ALG pass 3: the view through the lanai painted once across the whole glass (u west to east, v the glass's height;
    the 2022 torch photo looking north): blue sky, the Strip's cream, white and blue-glass towers filling the lower
    two thirds, the Excalibur's white walls and red, blue and gold turrets toward the east, the freeway's dark band at the
    foot. Architecture only, no signs or marks; drawn large and reduced so the mips stay calm at game distance."""
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(71)
    a = np.zeros((H, W, 3), np.float32)
    t = np.linspace(0.0, 1.0, H)[:, None]
    for k, (top, hor) in enumerate(zip((112, 164, 222), (198, 214, 230))):
        a[..., k] = top + (hor - top) * t
    im = Image.fromarray(a.astype(np.uint8))
    d = ImageDraw.Draw(im)
    Y = lambda f: int(H * (1.0 - f))  # noqa: E731  (f = height fraction of the glass)
    tones = [(226, 218, 200), (204, 198, 186), (146, 170, 198), (238, 232, 216), (184, 176, 160), (120, 146, 178)]

    def tower(x0, x1, top, colour):
        d.rectangle([int(W * x0), Y(top), int(W * x1), H], fill=colour)
        dark = tuple(int(c * 0.78) for c in colour)
        step = max(SCALE * 2, int(H * 0.035))
        for y in range(Y(top) + step, H, step):
            d.rectangle([int(W * x0), y, int(W * x1), y + max(1, step // 3)], fill=dark)
    x = 0.0
    while x < 1.0:
        w = 0.025 + 0.035 * r.random()
        tower(x, x + w, 0.30 + 0.25 * r.random(), tones[int(r.integers(len(tones)))])
        x += w * (0.6 + 0.5 * r.random())
    for x0, x1, top, c in ((0.04, 0.10, 0.72, (236, 230, 214)), (0.15, 0.20, 0.64, (214, 206, 190)),
                           (0.30, 0.36, 0.86, (126, 156, 194)), (0.37, 0.42, 0.78, (150, 178, 210)),
                           (0.45, 0.50, 0.70, (232, 226, 212)), (0.53, 0.58, 0.82, (134, 162, 198)),
                           (0.64, 0.71, 0.62, (232, 224, 204)), (0.80, 0.87, 0.66, (226, 218, 198))):
        tower(x0, x1, top, c)
    # the Excalibur: white walls and round turrets with coloured cone roofs
    d.rectangle([int(W * 0.62), Y(0.30), int(W * 0.92), H], fill=(240, 236, 228))
    for k, (cx, top, roof) in enumerate(((0.635, 0.44, (196, 36, 40)), (0.665, 0.52, (40, 78, 168)),
                                         (0.70, 0.40, (214, 178, 60)), (0.735, 0.56, (196, 36, 40)),
                                         (0.77, 0.46, (40, 78, 168)), (0.805, 0.50, (196, 36, 40)),
                                         (0.84, 0.42, (214, 178, 60)), (0.875, 0.54, (40, 78, 168)),
                                         (0.905, 0.44, (196, 36, 40)))):
        hw = 0.011
        d.rectangle([int(W * (cx - hw)), Y(top), int(W * (cx + hw)), H], fill=(246, 244, 238))
        d.polygon([(int(W * (cx - hw * 1.4)), Y(top)), (int(W * (cx + hw * 1.4)), Y(top)),
                   (int(W * cx), Y(top + 0.13))], fill=roof)
    d.rectangle([0, Y(0.10), W, H], fill=(72, 74, 80))
    d.rectangle([0, Y(0.10), W, Y(0.10) + max(1, int(H * 0.02))], fill=(150, 150, 146))
    return im


def torch(size=(64, 128)):
    """The Al Davis memorial torch's body: black and silver bands spiralling up (the torch photo)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (30, 30, 32))
    d = ImageDraw.Draw(im)
    for k in range(-H, W + H, SCALE * 10):
        d.line([k, H, k + H, 0], fill=(96, 100, 104), width=SCALE)
    return im


def flame(size=(32, 64)):
    """The torch's flame: orange to yellow, soft edges (alpha)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t = yy / H
    width = 0.15 + 0.35 * t
    dx = np.abs(xx / W - 0.5)
    a = np.clip(1.0 - dx / width, 0, 1) * np.clip(t * 3, 0, 1)
    rgb = np.stack([np.full_like(t, 255), 120 + 120 * (1 - t), 30 + 60 * (1 - t)], -1)
    out = np.dstack([rgb, a * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def board_panels(size=(128, 128)):
    """The south board's stat panels either side of the picture, lit edge to edge like the rest of the board (the 2021
    photo: the whole 75 m face bright): a silver-to-graphite field with a white rule, a black window where the game's
    digits sit, the club's name and the down and distance as plain type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (lo, hi) in enumerate(zip((150, 152, 158), (58, 60, 66))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.06)], fill=RAIDERS["white"])
    d.rectangle([int(W * 0.06), int(H * 0.14), int(W * 0.94), int(H * 0.50)], fill=(12, 12, 14))
    word = _row([_text("RAIDERS", RAIDERS["silver"])], W, int(H * 0.16), SCALE * 8, 0.8)
    im.paste(word, (0, int(H * 0.54)), word)
    down = _row([_text("1ST & 10", RAIDERS["white"])], W, int(H * 0.12), SCALE * 8, 0.8)
    im.paste(down, (0, int(H * 0.72)), down)
    return im


def letters(size=(256, 64)):
    """The venue's name as plain lowercase type, white on transparent (the signs read "allegiant stadium" in lowercase;
    the sunburst mark over the first word is never drawn)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    t = _text("allegiant stadium", RAIDERS["white"], px=240)
    h = int(H * 0.62)
    w = int(t.width * h / t.height)
    if w > W * 0.96:
        w = int(W * 0.96)
        h = int(t.height * w / t.width)
    t = t.resize((max(1, w), max(1, h)), Image.LANCZOS)
    im.paste(t, ((W - t.width) // 2, (H - t.height) // 2), t)
    return im


def facade(size=128):
    """The black glass drum (the exterior photos): near-black glass with faint vertical mullions and a slight sheen."""
    S = size * SCALE
    a = np.zeros((S, S, 3), np.float32)
    g = np.linspace(0.0, 1.0, S)[:, None]
    for k, (lo, hi) in enumerate(zip((26, 28, 34), (14, 15, 18))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    # pass 3: faint mullions, the drum reads as one smooth black shell from the flyover (the I-15 photo)
    for x in range(0, S, S // 8):
        d.rectangle([x, 0, x + SCALE // 2, S], fill=(30, 31, 36))
    return im


def glass_out(size=(128, 128)):
    """The lanai's glass seen from outside (the North Entry photos by day: dark blue-grey panes taking the sky's light at
    the top, black mullions and transoms)."""
    S_w, S_h = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((S_h, S_w, 3), np.float32)
    g = np.linspace(0.0, 1.0, S_h)[:, None]
    for k, (lo, hi) in enumerate(zip((78, 94, 118), (32, 38, 50))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for x in range(0, S_w, S_w // 8):
        d.rectangle([x, 0, x + SCALE, S_h], fill=(20, 21, 24))
    for y in range(0, S_h, S_h // 4):
        d.rectangle([0, y, S_w, y + SCALE // 2], fill=(20, 21, 24))
    return im


def lines(size=(64, 8)):
    """The drum's white light lines."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (240, 244, 250))
    return im


def mesh(size=(256, 64)):
    """The LED mesh toward I-15 (27,600 sq ft; the 2024 photo shows it lit edge to edge with bright game-day graphics):
    ALG pass 2, a lit silver and charcoal diamond pattern with red chevrons at the ends and RAIDERS in big white
    plain type (no marks)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    k = H / 4.0
    dia = ((np.abs((xx % (2 * k)) - k) + np.abs((yy % (2 * k)) - k)) < k * 0.8).astype(np.float32)
    a = np.zeros((H, W, 3), np.float32)
    for c, (lo, hi) in enumerate(zip((24, 24, 28), (118, 122, 128))):
        a[..., c] = lo + (hi - lo) * dia
    im = Image.fromarray(a.astype(np.uint8))
    d = ImageDraw.Draw(im)
    for x0 in (0, W - H):
        for j in range(3):
            o = j * H // 3
            d.polygon([(x0 + o, 0), (x0 + o + H // 6, 0), (x0 + o + H // 2, H // 2), (x0 + o + H // 6, H), (x0 + o, H),
                       (x0 + o + H // 3, H // 2)], fill=(214, 26, 38))
    band = _row([_text("RAIDERS", RAIDERS["white"])], W - 2 * H, H, SCALE * 24, 0.62)
    im.paste(band, (H, 0), band)
    # pass 3: the white light line framing the wall above and below (the 2024 I-15 photo)
    d.rectangle([0, 0, W, int(H * 0.05)], fill=(250, 250, 252))
    d.rectangle([0, H - int(H * 0.05), W, H], fill=(250, 250, 252))
    return im


def strip(size=(64, 64)):
    """The Strip's towers (the torch photo by day, 2022: cream and pale gold walls with blue-grey window bands, the
    Excalibur, New York-New York and MGM Grand bright beyond the lanai; by night the LIGHT_ class lights them)."""
    S_w, S_h = size[0] * SCALE, size[1] * SCALE
    r = rng(57)
    im = Image.new("RGB", (S_w, S_h), (172, 162, 142))
    d = ImageDraw.Draw(im)
    for y in range(0, S_h, SCALE * 4):
        d.rectangle([0, y + SCALE, S_w, y + SCALE * 3], fill=(88, 106, 128))
        for x in range(0, S_w, SCALE * 3):
            if r.random() < 0.3:
                d.rectangle([x, y + SCALE, x + SCALE * 2, y + SCALE * 3], fill=(240, 226, 186))
    return im


def pyramid(size=(64, 64)):
    """The Luxor's black glass pyramid."""
    S = size[0] * SCALE
    im = Image.new("RGB", (S, S), (34, 36, 42))
    d = ImageDraw.Draw(im)
    for y in range(0, S, SCALE * 4):
        d.line([0, y, S, y], fill=(52, 56, 64), width=max(1, SCALE // 2))
    return im


def ground(size=128):
    """The desert ground and lots' margins: tan and grey-brown."""
    S = size * SCALE
    r = rng(63)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    a = np.dstack([176 + 24 * n, 160 + 22 * n, 128 + 16 * n])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def hills(size=(128, 64)):
    """The ranges round the valley: dry grey-brown slopes fading into haze at the top."""
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(67)
    n = _blur(r.random((H // 4, W // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))[:H, :W]
    g = np.linspace(0.0, 1.0, H)[:, None]
    haze = np.array([200, 196, 188], np.float32)
    grnd = np.array([140, 118, 96], np.float32)
    a = grnd[None, None, :] * (0.86 + 0.18 * n[..., None])
    t = np.clip(1.0 - g, 0, 1)[..., None] * 0.5
    a = a * (1 - t) + haze * t
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


#: the field: natural Bermuda grass (Wikipedia) mown in 5-yard bands (the 2021 and 2022 photos)
GRASS_LIGHT, GRASS_DARK = (92, 150, 66), (70, 126, 52)


def field_grass(size=(128, 64), bands=20):
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(71)
    n = _blur(r.random((H // 4, W // 4)), 1)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))[:H, :W]
    a = np.zeros((H, W, 3), np.float32)
    for x in range(W):
        band = int(x * bands / W)
        a[:, x] = np.array(GRASS_LIGHT if band % 2 == 0 else GRASS_DARK, np.float32)
    a *= (0.95 + 0.08 * n)[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def field_outside(size=128):
    S = size * SCALE
    return Image.new("RGB", (S, S), (76, 132, 58))


def drawings():
    return {
        "ag_seat_front": (seat(0.06, 11), (64, 128)), "ag_seat_mid": (seat(0.10, 12), (64, 128)),
        "ag_seat_back": (seat(0.16, 13), (64, 128)),
        "ag_concrete": (base.concrete(), (64, 64)), "ag_wall": (wall(), (256, 32)),
        "LIGHT_ag_ribbon": (ribbon_lit(), (256, 64)), "LIGHT_ag_glass": (base.glass(), (128, 64)),
        "LIGHT_ag_concourse": (base.concourse(), (128, 64)), "ag_portal": (base.vomitory(), (32, 32)),
        "ag_dark": (base.dark(), (32, 32)), "ag_black": (black(), (32, 32)),
        "ag_roof_under": (roof_grid(), (128, 128)), "ag_roof_top": (roof_top(), (64, 64)),
        "ag_truss": (truss(), (64, 32)),
        "ag_roof_rim": (roof_rim(), (64, 64)),
        "LIGHT_ag_lights": (lamps(), (64, 32)), "LIGHT_ag_lanai": (lanai(), (64, 64)),
        "LIGHT_ag_skyline": (skyline(), (128, 32)),
        "ag_torch": (torch(), (64, 128)), "LIGHT_ag_flame": (flame(), (32, 64)),
        "LIGHT_ag_board_panel": (board_panels(), (128, 128)), "ag_letters": (letters(), (256, 64)),
        "ag_facade": (facade(), (128, 128)), "ag_glass_out": (glass_out(), (64, 64)),
        "LIGHT_ag_lines": (lines(), (64, 8)), "LIGHT_ag_mesh": (mesh(), (256, 64)),
        "ag_plaza": (base.plaza(), (32, 32)), "ag_ground": (ground(), (32, 32)),
        "ag_asphalt": (base.asphalt(), (32, 32)), "ag_road": (base.road(), (32, 32)),
        "ag_building": (base.building(), (32, 32)), "LIGHT_ag_strip": (strip(), (64, 64)),
        "ag_pyramid": (pyramid(), (64, 64)), "ag_hills": (hills(), (128, 64)),
        "field/ag_grass": (field_grass(), (128, 64)), "field/ag_grass_outside": (field_outside(), (128, 128)),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--masters")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "field").mkdir(exist_ok=True)
    masters = Path(a.masters) if a.masters else None
    if masters:
        (masters / "field").mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, (master, size) in drawings().items():
        native = reduce(master, size)
        path = out / f"{name}.png"
        native.save(path, optimize=True)
        manifest[name] = dict(size=list(size), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if masters:
            master.save(masters / f"{name}.png", optimize=True)
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_allegiant_model_art/v1", art=manifest), indent=1) + "\n")
    print("ALLEGIANT_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
