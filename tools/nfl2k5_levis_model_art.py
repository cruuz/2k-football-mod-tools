#!/usr/bin/env python3
"""Draw the Levi's Stadium model's art (job st2, 2026-09-25): deterministic, procedural, plain type only.

  python3 tools/nfl2k5_levis_model_art.py OUT_DIR [--masters MASTER_DIR]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model, and no logo is drawn: every name is plain type (Roboto Condensed Bold, Apache 2.0).
Tones are measured from the reference photos (Commons: "Levi's Stadium interior 1" and "2" (2014-08-12), "Levi's
Stadium panorama" (2014), "Levis stadium panorama" (2019-11-07), "Super Bowl LX first quarter crowd view" (2026-02-08),
"Levi's Stadium 2026 FIFA World Cup Australia v. Paraguay" (2026-06-25), "View of Levi's Stadium from parking lot"
(2014), the 2016 satellite view): the 49ers-red seats on every level, the red field wall, the suite tower's glass and
white slabs, the teal press level, the solar roof, the white steel light trusses and frames, the grey precast west
facade, the natural grass mown in bands, the dry golden ground and the brown hills of the Diablo Range.
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
NINERS = dict(red=(170, 0, 0), gold=(173, 153, 93), white=(255, 255, 255), black=(16, 16, 18))


def seat(p_grey, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0. The seats are
    49ers red on every level (the 2014 and 2019 photos), with a few faded or dark seats scattered through them
    (``p_grey``), a little more toward the back of each tier."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (70, 64, 64))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(168, 166, 162))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(62, 50, 50))
        for c in range(cols):
            x = c * pitch
            basec = (120, 40, 44) if r.random() < p_grey else (178, 22, 30)
            tone = int(r.integers(-10, 11))
            fill = tuple(int(np.clip(v + tone, 0, 255)) for v in basec)
            d.rectangle([x + SCALE, y0 + int(rh * 0.30), x + pitch - SCALE, y0 + int(rh * 0.94)], fill=fill)
    aisle = int(round(W * 0.16 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(176, 174, 170))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(126, 124, 120), width=SCALE)
    return im


def wall(size=(256, 32)):
    """The field wall: 49ers red padding with a thin gold line along its top and plain white type (the 2019 and 2026
    photos: red pads all round the field)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), NINERS["red"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.08)], fill=NINERS["gold"])
    items = [_text("49ERS", NINERS["white"]), _text("FAITHFUL", NINERS["white"]), _text("49ERS", NINERS["white"]),
             _text("LEVI'S STADIUM", NINERS["white"])]
    band = _row(items, W, int(H * 0.92), SCALE * 12, 0.5)
    im.paste(band, (0, int(H * 0.08)), band)
    return im


def ribbon(size=(256, 64)):
    """The LED ribbons, two bands a texture (plain type, no logos): red with WELCOME TO LEVI'S STADIUM (the 2014
    interiors: the ribbon over the 100 level all round); and a lively band of red, gold, black and white segments with
    the club's words and the partners' names as type (the 2026 photos: the upper ribbons in partner colours)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    h = H // 2
    top = Image.new("RGB", (W, h), (196, 16, 26))
    band = _row([_text("WELCOME TO LEVI'S STADIUM", NINERS["white"]), _text("WELCOME TO LEVI'S STADIUM", NINERS["white"])],
                W, h, SCALE * 10, 0.56)
    top.paste(band, (0, 0), band)
    im.paste(top, (0, 0))
    segs = [(NINERS["red"], [_text("SAN FRANCISCO 49ERS", NINERS["white"])]),
            (NINERS["black"], [_text("FAITHFUL", NINERS["gold"])]),
            ((245, 246, 248), [_text("LEVI'S", (196, 16, 26))]),
            (NINERS["gold"], [_text("GO NINERS", NINERS["black"])]),
            ((20, 70, 160), [_text("BUD LIGHT", NINERS["white"])])]
    x = 0
    for (bg, items), w in zip(segs, (0.32, 0.17, 0.15, 0.18, 0.18)):
        sw = int(W * w) if x + int(W * w) <= W else W - x
        seg = Image.new("RGB", (sw, h), bg)
        b = _row(items, sw, h, SCALE * 6, 0.56)
        seg.paste(b, (0, 0), b)
        im.paste(seg, (x, h))
        x += sw
    if x < W:
        im.paste(Image.new("RGB", (W - x, h), NINERS["red"]), (x, h))
    return im


def suites(size=(128, 64)):
    """The suite levels' glass behind the balconies: dark tinted glass with warm lights and people inside, a white slab
    edge along the top (the 2014 tower photo)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (30, 36, 44))
    d = ImageDraw.Draw(im)
    r = rng(51)
    for y in range(int(H * 0.12), H):
        t = (y - H * 0.12) / (H * 0.88)
        c = tuple(int(a + (b - a) * t) for a, b in zip((52, 60, 70), (24, 28, 34)))
        d.line([0, y, W, y], fill=c)
    d.rectangle([0, 0, W, int(H * 0.12)], fill=(222, 222, 218))
    for x in range(SCALE * 2, W, SCALE * 10):
        d.rectangle([x, int(H * 0.16), x + SCALE * 4, int(H * 0.16) + SCALE * 2], fill=(255, 230, 186))
    for x in range(0, W, SCALE * 16):
        d.rectangle([x, int(H * 0.12), x + SCALE, H], fill=(84, 88, 94))
    for _ in range(18):
        x = int(r.integers(0, W - SCALE * 3))
        hh = int(SCALE * r.integers(5, 9))
        c = NINERS["red"] if r.random() < 0.5 else (int(r.integers(50, 90)),) * 3
        d.rectangle([x, H - hh - SCALE * 2, x + SCALE * 2, H - SCALE * 2], fill=c)
    return im


def press(size=(128, 32)):
    """The press level at the tower's top: a band of teal-tinted glass (the 2014 photos), mullions every few metres."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (lo, hi) in enumerate(zip((70, 118, 124), (40, 84, 92))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for x in range(0, W, SCALE * 6):
        d.rectangle([x, 0, x + SCALE // 2, H], fill=(150, 170, 172))
    d.rectangle([0, 0, W, SCALE * 2], fill=(200, 204, 206))
    return im


def balcony(size=(64, 16)):
    """A suite balcony's railing: glass (alpha) with a white top rail and posts."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (170, 184, 196, 96))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.18)], fill=(236, 236, 234, 255))
    for x in range(0, W, W // 4):
        d.rectangle([x, 0, x + SCALE, H], fill=(210, 212, 214, 255))
    return im


def white(size=32):
    """White painted steel and slab edges (the tower's floors, the frames)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (226, 226, 222))
    d = ImageDraw.Draw(im)
    d.line([0, S - SCALE, S, S - SCALE], fill=(190, 190, 186), width=SCALE)
    return im


def solar(size=64):
    """The tower roof's photovoltaic panels from above: dark blue cells in rows with light seams (the 2016 satellite
    view: a long dark striped roof on the west side)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (34, 44, 70))
    d = ImageDraw.Draw(im)
    for y in range(0, S, SCALE * 8):
        d.rectangle([0, y, S, y + SCALE], fill=(150, 156, 166))
    for x in range(0, S, SCALE * 4):
        d.line([x, 0, x, S], fill=(46, 58, 88), width=max(1, SCALE // 2))
    return im


def green(size=64):
    """The green roof beside the solar panels (27,000 sq ft; the Faithful Farm since 2016)."""
    S = size * SCALE
    r = rng(61)
    n = _blur(r.random((S, S)), 3)
    n = (n - n.min()) / max(1e-6, n.max() - n.min())
    a = np.dstack([96 + 40 * n, 124 + 40 * n, 64 + 20 * n])
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for y in range(0, S, S // 6):
        d.line([0, y, S, y], fill=(150, 140, 110), width=SCALE)
    return im


def roof_under(size=64):
    """The tower roof's underside over the press level: white panels with dark joints."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (206, 208, 210))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(150, 152, 156), width=SCALE)
    return im


def truss(size=(64, 32)):
    """The light trusses on the east rim and the tower roof: white steel lattice (chords and X bracing) with the sky
    through it (alpha; the 2014 interior photos)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (232, 232, 230, 255)
    t = SCALE * 3
    d.rectangle([0, 0, W, t], fill=c); d.rectangle([0, H - t, W, H], fill=c)
    for x in range(0, W + 1, W // 2):
        d.rectangle([x - t // 2, 0, x + t // 2, H], fill=c)
    for x0 in range(0, W, W // 2):
        d.line([x0, 0, x0 + W // 2, H], fill=c, width=t // 2)
        d.line([x0, H, x0 + W // 2, 0], fill=c, width=t // 2)
    return im


def frame(size=(64, 64)):
    """The open steel frame round the east and end stands, seen from outside: white columns, beams and diagonal braces
    with the stands' backs showing through (alpha; the 2014 exterior photos)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (230, 230, 228, 255)
    t = SCALE * 3
    for x in (0, W // 2, W):
        d.rectangle([x - t, 0, x + t, H], fill=c)
    for y in (0, H // 2, H):
        d.rectangle([0, y - t // 2, W, y + t // 2], fill=c)
    d.line([0, H // 2, W // 2, 0], fill=c, width=t)
    d.line([W // 2, H, W, H // 2], fill=c, width=t)
    return im


def lamps(size=(64, 32)):
    """The LED floodlights on the trusses: bright lamps in a dark frame."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (30, 32, 36))
    d = ImageDraw.Draw(im)
    for x in range(SCALE * 2, W, SCALE * 8):
        d.rectangle([x, int(H * 0.25), x + SCALE * 5, int(H * 0.75)], fill=(255, 252, 244))
    return im


def black(size=32):
    """The boards' housings: near black with faint panel seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (14, 15, 17))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(26, 27, 30), width=SCALE // 2)
        d.line([0, k, S, k], fill=(26, 27, 30), width=SCALE // 2)
    return im


def steel(size=32):
    S = size * SCALE
    return Image.new("RGB", (S, S), (200, 202, 204))


def board_panels(size=(128, 128)):
    """The boards' side panels either side of the live picture: the game presentation's stat panels (the 2026 World Cup
    photo: red panels with the score beside the picture), plain type: the club's name, the down and distance and the
    time-out bars. The game's own digits sit over the panel's upper half."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (150, 8, 18))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.08)], fill=NINERS["gold"])
    d.rectangle([int(W * 0.06), int(H * 0.14), int(W * 0.94), int(H * 0.50)], fill=(24, 8, 10))
    word = _row([_text("49ERS", NINERS["white"])], W, int(H * 0.16), SCALE * 8, 0.8)
    im.paste(word, (0, int(H * 0.54)), word)
    down = _row([_text("1ST & 10", NINERS["gold"])], W, int(H * 0.12), SCALE * 8, 0.8)
    im.paste(down, (0, int(H * 0.72)), down)
    for k in range(3):
        x0 = int(W * (0.18 + 0.23 * k))
        d.rectangle([x0, int(H * 0.88), x0 + int(W * 0.16), int(H * 0.92)], fill=NINERS["gold"])
    return im


def letters(size=(256, 64)):
    """LEVI'S STADIUM as plain type (never the Levi's mark): white letters on a transparent ground, a red panel behind
    LEVI'S (the signs over the boards and on the west facade read that way from the field and the lots)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lev = _text("LEVI'S", NINERS["white"], px=240)
    sta = _text("STADIUM", NINERS["white"], px=240)
    h = int(H * 0.62)
    pad = int(H * 0.16)
    # the letters' height fits the whole sign inside the texture (a 4:1 panel; STADIUM is the long word)
    width_at = lambda hh: (lev.width + sta.width) * hh / lev.height + 2 * pad + SCALE * 10  # noqa: E731
    while width_at(h) > W * 0.96:
        h -= SCALE
    lev = lev.resize((max(1, int(lev.width * h / lev.height)), h), Image.LANCZOS)
    sta = sta.resize((max(1, int(sta.width * h / sta.height)), h), Image.LANCZOS)
    total = lev.width + 2 * pad + SCALE * 10 + sta.width
    x0 = (W - total) // 2
    d.rectangle([x0, 0, x0 + lev.width + 2 * pad, H], fill=(196, 16, 26, 255))
    im.paste(lev, (x0 + pad, (H - h) // 2), lev)
    im.paste(sta, (x0 + lev.width + 2 * pad + SCALE * 10, (H - h) // 2), sta)
    return im


def facade(size=128):
    """The suite tower's west facade: light grey precast panels in a regular grid, deep-set dark windows on each floor
    and vertical fins (the 2014 and 2017 exterior photos from the west lots)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (204, 204, 200))
    d = ImageDraw.Draw(im)
    r = rng(71)
    fl = S // 4
    for y in range(0, S, fl):
        d.rectangle([0, y, S, y + SCALE * 2], fill=(170, 170, 166))
        for x in range(0, S, S // 8):
            tone = int(r.integers(-8, 9))
            d.rectangle([x + SCALE * 3, y + int(fl * 0.30), x + S // 8 - SCALE * 3, y + int(fl * 0.78)],
                        fill=(58 + tone, 64 + tone, 72 + tone))
    for x in range(0, S, S // 8):
        d.rectangle([x, 0, x + SCALE * 2, S], fill=(226, 226, 222))
    return im


def curtain(size=128):
    """The glass curtain in the middle of the tower's west face (the 2014 and 2017 photos from the west lots): dark
    grey-blue glass on a grid of light mullions, a floor line every storey, the concourse's lights faint behind it."""
    S = size * SCALE
    r = rng(73)
    a = np.zeros((S, S, 3), np.float32)
    g = np.linspace(0.0, 1.0, S)[:, None]
    for k, (lo, hi) in enumerate(zip((96, 106, 116), (70, 80, 92))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for y in range(0, S, S // 6):
        d.rectangle([0, y, S, y + SCALE * 2], fill=(176, 180, 184))
        for x in range(SCALE * 4, S, SCALE * 14):
            if r.random() < 0.4:
                d.rectangle([x, y + SCALE * 6, x + SCALE * 5, y + SCALE * 8], fill=(214, 200, 170))
    for x in range(0, S, S // 10):
        d.rectangle([x, 0, x + SCALE, S], fill=(160, 164, 170))
    return im


def banner(size=(64, 128)):
    """A tall club banner on the west face (plain type, no marks or players: FAITHFUL over 49ERS on red, a gold
    rule)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), NINERS["red"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(H * 0.05), W, int(H * 0.06)], fill=NINERS["gold"])
    d.rectangle([0, int(H * 0.94), W, int(H * 0.95)], fill=NINERS["gold"])
    top = _row([_text("FAITHFUL", NINERS["white"])], W, int(H * 0.12), SCALE * 6, 0.9)
    im.paste(top, (0, int(H * 0.12)), top)
    big = _row([_text("49ERS", NINERS["gold"])], W, int(H * 0.2), SCALE * 4, 0.95)
    im.paste(big, (0, int(H * 0.62)), big)
    return im


def base_band(size=(128, 64)):
    """The concourse level outside: grey concrete with gates and the lit concourse behind open grilles."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (150, 150, 146))
    d = ImageDraw.Draw(im)
    for x in range(SCALE * 4, W, SCALE * 24):
        d.rectangle([x, int(H * 0.35), x + SCALE * 14, H], fill=(40, 40, 44))
        d.rectangle([x + SCALE * 2, int(H * 0.40), x + SCALE * 12, int(H * 0.52)], fill=(250, 226, 180))
    d.rectangle([0, 0, W, int(H * 0.12)], fill=(196, 196, 192))
    return im


def water(size=32):
    S = size * SCALE
    r = rng(81)
    n = _blur(r.random((S, S)), 2)
    a = np.dstack([74 + 20 * n, 96 + 20 * n, 88 + 16 * n])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def hills(size=(128, 64)):
    """The Diablo Range's dry foothills east of Santa Clara (every photo from the lots and Great America: brown and
    golden grass slopes under a pale sky), drawn as a band: the ridge at the top fades into haze."""
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(91)
    n = _blur(r.random((H // 4, W // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))[:H, :W]
    g = np.linspace(0.0, 1.0, H)[:, None]
    haze = np.array([196, 190, 176], np.float32)
    ground = np.array([150, 120, 82], np.float32)
    a = ground[None, None, :] * (0.86 + 0.18 * n[..., None])
    t = np.clip(1.0 - g, 0, 1)[..., None] * 0.45
    a = a * (1 - t) + haze * t
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def ground(size=128):
    """The site's dry ground and lawns: golden-brown with green patches (the 2016 satellite view and the aerials)."""
    S = size * SCALE
    r = rng(93)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    a = np.dstack([150 + 30 * n, 140 + 26 * n, 96 + 14 * n])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


#: the field: natural grass (Bermuda and rye, Wikipedia; OSM: West Coast Turf "Ready Play Grass") mown in 5-yard bands
#: (the 2019 and 2026 photos)
GRASS_LIGHT, GRASS_DARK = (86, 140, 62), (64, 116, 48)


def field_grass(size=(128, 64), bands=20):
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(97)
    n = _blur(r.random((H // 4, W // 4)), 1)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))[:H, :W]
    a = np.zeros((H, W, 3), np.float32)
    for x in range(W):
        band = int(x * bands / W)
        a[:, x] = np.array(GRASS_LIGHT if band % 2 == 0 else GRASS_DARK, np.float32)
    a *= (0.95 + 0.08 * n)[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def field_outside(size=128):
    """The grass outside the field of play (to the walls): the same green, unstriped."""
    S = size * SCALE
    return Image.new("RGB", (S, S), (72, 124, 54))


def drawings():
    return {
        "lv_seat_front": (seat(0.03, 11), (64, 128)), "lv_seat_mid": (seat(0.08, 12), (64, 128)),
        "lv_seat_back": (seat(0.14, 13), (64, 128)),
        "lv_concrete": (base.concrete(), (64, 64)), "lv_wall": (wall(), (256, 32)),
        "LIGHT_lv_ribbon": (ribbon(), (256, 64)), "LIGHT_lv_glass": (base.glass(), (128, 64)),
        "LIGHT_lv_concourse": (base.concourse(), (128, 64)), "lv_portal": (base.vomitory(), (32, 32)),
        "lv_dark": (base.dark(), (32, 32)), "lv_black": (black(), (32, 32)),
        "LIGHT_lv_suites": (suites(), (128, 64)), "LIGHT_lv_press": (press(), (128, 32)),
        "lv_balcony": (balcony(), (64, 16)), "lv_white": (white(), (32, 32)),
        "lv_solar": (solar(), (64, 64)), "lv_green": (green(), (64, 64)), "lv_roof_under": (roof_under(), (64, 64)),
        "lv_truss": (truss(), (64, 32)), "lv_frame": (frame(), (64, 64)), "lv_steel": (steel(), (32, 32)),
        "LIGHT_lv_lights": (lamps(), (64, 32)), "LIGHT_lv_board_panel": (board_panels(), (128, 128)),
        "lv_letters": (letters(), (256, 64)), "lv_facade": (facade(), (128, 128)),
        "LIGHT_lv_curtain": (curtain(), (128, 128)), "lv_banner": (banner(), (64, 128)),
        "LIGHT_lv_base": (base_band(), (128, 64)),
        "lv_plaza": (base.plaza(), (32, 32)), "lv_ground": (ground(), (32, 32)),
        "lv_asphalt": (base.asphalt(), (32, 32)), "lv_road": (base.road(), (32, 32)),
        "lv_building": (base.building(), (32, 32)), "lv_water": (water(), (32, 32)), "lv_hills": (hills(), (128, 64)),
        "field/lv_grass": (field_grass(), (128, 64)), "field/lv_grass_outside": (field_outside(), (128, 128)),
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
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_levis_model_art/v1", art=manifest), indent=1) + "\n")
    print("LEVIS_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
