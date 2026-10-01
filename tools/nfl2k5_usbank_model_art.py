#!/usr/bin/env python3
"""Draw the U.S. Bank Stadium model's art (job st3, 2026-09-27): deterministic and procedural; plain type for every name
except the venue's own wordmark, which is the official mark (never redrawn).

  python3 tools/nfl2k5_usbank_model_art.py OUT_DIR --logo LOGO_PNG [--masters MASTER_DIR]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model. The venue's wordmark comes from Wikimedia Commons ``US Bank Stadium Minnesota logo.svg``
(public domain text logo), rendered with Inkscape to ``LOGO_PNG`` (author time only; the PNG itself does not ship): the
interior header keeps the red shield and sets the words in white, the exterior signs set it all in white, and the
two-line lockup on the prow is the same pieces stacked ("usbank" over "stadium", the 2016 to 2026 exterior photos). No
team or partner logo is drawn: the Vikings, SKOL and every partner are plain type (Roboto Condensed Bold, Apache 2.0).
Tones are measured from the reference photos (Commons 2016 to 2026 and the Vikings' 2026 week 1 galleries): the purple
seats, the purple field-wall pads, the bright ETFE panels on the white steel grid, the dark steel under the opaque roof,
the dark zinc-coloured panels and the reflective glass outside, the concrete plaza and downtown's towers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nfl2k5_highmark_model_art as base  # noqa: E402

SCALE = base.SCALE
rng, _blur, reduce, _text, _row = base.rng, base._blur, base.reduce, base._text, base._row
#: the Vikings' 2026 colours (NFL Record and Fact Book, via u4's MIN venue spec): purple #4F2683, gold #FFC62F
VIK = dict(purple=(79, 38, 131), gold=(255, 198, 47), white=(255, 255, 255), black=(0, 0, 0))
#: the seats as the photos show them (a darker, greyer purple than the club colour under the stadium's light)
SEAT = (70, 48, 112)
LOGO = None
MARK_3M = None
MARK_LOL = None


# --- the official wordmark ------------------------------------------------------------------------------------------

def _logo():
    im = Image.open(LOGO).convert("RGBA")
    return im.crop(im.getbbox())


def _split(im):
    """(``usbank`` part, ``stadium`` part) of the one-line wordmark: cut at the widest transparent gap between the k
    and the s (searched between 45 and 58 percent of the mark's width, where the bold "bank" meets "stadium")."""
    a = np.asarray(im)[..., 3] > 16
    cols = a.any(axis=0)
    W = im.width
    best, run, start = (0, 0), 0, 0
    for x in range(int(W * 0.45), int(W * 0.58)):
        if not cols[x]:
            if run == 0:
                start = x
            run += 1
            if run > best[0]:
                best = (run, start)
        else:
            run = 0
    cut = best[1] + best[0] // 2
    left, right = im.crop((0, 0, cut, im.height)), im.crop((cut, 0, W, im.height))
    return left.crop(left.getbbox()), right.crop(right.getbbox())


def _recolour(im, keep_red, colour):
    """The wordmark in ``colour``. With ``keep_red`` the shield stays red with its white letters (the interior header);
    without it the shield turns ``colour`` and its letters are cut out of it (the exterior signs: u036, u047). The alpha
    is the mark's own."""
    a = np.asarray(im).astype(np.int16).copy()
    red = (a[..., 0] > 150) & (a[..., 1] < 90) & (a[..., 2] < 110)
    white = (a[..., 0] > 200) & (a[..., 1] > 200) & (a[..., 2] > 200) & (a[..., 3] > 16)
    out = a.copy()
    if keep_red:
        sel = ~red & ~white
    else:
        sel = np.ones(red.shape, bool)
        out[white, 3] = 0
    out[sel, 0], out[sel, 1], out[sel, 2] = colour
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def _fit(im, W, H, fill=0.86):
    s = min(W * fill / im.width, H * fill / im.height)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)


def header(size=(256, 64)):
    """The usbankstadium header over each video board (u014, 2023; the 2026 week 1 frames): the one-line wordmark with
    its red shield and the words in white, on the header's black box."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (8, 8, 10, 255))
    mark = _fit(_recolour(_logo(), True, (238, 238, 240)), W, H, 0.84)
    im.paste(mark, ((W - mark.width) // 2, (H - mark.height) // 2), mark)
    return im


def letters(size=(256, 64)):
    """The one-line wordmark in white on transparent (the exterior signs and the bowl's north fascia, u094)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mark = _fit(_recolour(_logo(), False, (244, 244, 246)), W, H, 0.9)
    im.paste(mark, ((W - mark.width) // 2, (H - mark.height) // 2), mark)
    return im


def _lockup(keep_red, colour, W, H):
    """The two-line lockup on a transparent W x H canvas: "usbank" over "stadium", left-aligned, "stadium" starting under
    the b of "bank" (u036), the pieces of the official wordmark stacked (never redrawn)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    top, bottom = _split(_recolour(_logo(), keep_red, colour))
    h1 = int(H * 0.46)
    top = top.resize((max(1, int(top.width * h1 / top.height)), h1), Image.LANCZOS)
    bottom = bottom.resize((max(1, int(bottom.width * h1 * 0.78 / bottom.height)), int(h1 * 0.78)), Image.LANCZOS)
    offset = int(top.width * 0.40)
    s = min(1.0, (W * 0.94) / max(top.width, offset + bottom.width))
    if s < 1.0:
        top = top.resize((int(top.width * s), int(top.height * s)), Image.LANCZOS)
        bottom = bottom.resize((int(bottom.width * s), int(bottom.height * s)), Image.LANCZOS)
        offset = int(offset * s)
    x0 = int(W * 0.03)
    im.paste(top, (x0, int(H * 0.06)), top)
    im.paste(bottom, (x0 + offset, int(H * 0.06) + top.height + int(H * 0.08)), bottom)
    return im


def prow_letters(size=(128, 64)):
    """The prow's two-line lockup (u036, u047): "usbank" over "stadium", white, left-aligned."""
    return _lockup(False, (244, 244, 246), size[0] * SCALE, size[1] * SCALE)


def letters_back(size=(64, 16)):
    """The dark back of every one-sided sign (u5b: the engine draws alpha signs from both sides)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    return Image.new("RGBA", (W, H), (22, 22, 24, 255))


# --- the bowl --------------------------------------------------------------------------------------------------------

def seat(p_light, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0; purple seats
    (every photo), a few lighter ones where the light catches them (``p_light``)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (58, 44, 86))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(140, 138, 142))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(34, 26, 48))
        for c in range(cols):
            x = c * pitch
            basec = (98, 76, 150) if r.random() < p_light else SEAT
            tone = int(r.integers(-6, 7))
            fill = tuple(int(np.clip(v + tone, 0, 255)) for v in basec)
            d.rectangle([x + SCALE, y0 + int(rh * 0.30), x + pitch - SCALE, y0 + int(rh * 0.94)], fill=fill)
    aisle = int(round(W * 0.16 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(150, 150, 148))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(110, 110, 108), width=SCALE)
    return im


def wall(size=(256, 32)):
    """The field wall (the 2026 week 1 frames 047 and 048): purple pads with a thin gold rule along the top, VIKINGS,
    SKOL and MINNESOTA in white plain type (the club's wordmark and head are never drawn here)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), VIK["purple"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.08)], fill=VIK["gold"])
    items = [_text("VIKINGS", VIK["white"]), _text("SKOL", VIK["white"]), _text("MINNESOTA", VIK["white"]),
             _text("SKOL", VIK["white"])]
    band = _row(items, W, int(H * 0.92), SCALE * 12, 0.56)
    im.paste(band, (0, int(H * 0.08)), band)
    return im


def ribbon(size=(256, 64)):
    """The LED ribbons (the 3.5 ft upper concourse and 2.5 ft club ribbons, Daktronics), two bands a texture: black with
    SKOL VIKINGS and MINNESOTA VIKINGS in white and gold; and the partners as plain type (the 2023 and 2026 photos: the
    TCO ribbons, Hyundai, Lite, Andersen, 3M, CFMOTO; no partner logo is drawn)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    half = H // 2
    bands = [((10, 8, 16), [_text("SKOL", VIK["gold"]), _text("VIKINGS", VIK["white"]), _text("SKOL", VIK["gold"]),
                            _text("MINNESOTA VIKINGS", VIK["white"])]),
             (VIK["purple"], [_text("TCO", VIK["white"]), _text("HYUNDAI", VIK["white"]), _text("3M", VIK["white"]),
                              _text("CFMOTO", VIK["white"]), _text("TCO", VIK["white"])])]
    for k, (bg, items) in enumerate(bands):
        y0 = k * half
        ImageDraw.Draw(im).rectangle([0, y0, W, y0 + half], fill=bg)
        band = _row(items, W, half, SCALE * 10)
        im.paste(band, (0, y0), band)
    return im


def black(size=32):
    S = size * SCALE
    im = Image.new("RGB", (S, S), (12, 12, 14))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(24, 24, 28), width=SCALE // 2)
        d.line([0, k, S, k], fill=(24, 24, 28), width=SCALE // 2)
    return im


# --- the roof ----------------------------------------------------------------------------------------------------------

def etfe_under(size=128):
    """The ETFE from below (u001, u014, the 2026 frames): bright milky cushions in long bays on a white steel grid, the
    rafters and the diagonal bracing in lighter grey."""
    S = size * SCALE
    r = rng(29)
    a = np.zeros((S, S, 3), np.float32)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    for k, v in enumerate((236, 240, 244)):
        a[..., k] = v * (0.92 + 0.08 * n)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.rectangle([k, 0, k + SCALE * 3, S], fill=(176, 180, 186))
    for k in range(0, S, S // 8):
        d.rectangle([0, k, S, k + SCALE], fill=(196, 200, 206))
    for k in range(-S, S, S // 4):
        d.line([k, 0, k + S, S], fill=(206, 210, 214), width=max(1, SCALE // 2))
    return im


def roof_under(size=128):
    """The opaque roof from below (u014: the north half): dark grey deck, the steel trusses in a lighter grey."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (54, 56, 60))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.rectangle([k, 0, k + SCALE * 3, S], fill=(96, 100, 106))
    for k in range(0, S, S // 8):
        d.rectangle([0, k, S, k + SCALE], fill=(78, 80, 86))
    for k in range(-S, S, S // 4):
        d.line([k, 0, k + S, S], fill=(88, 90, 96), width=max(1, SCALE // 2))
    return im


def truss(size=64):
    """The ridge truss and the queen's post trusses (u003, u014, u019: open steel lattices, light grey, the roof showing
    through them): slim top and bottom chords, posts and X bracing on a transparent ground (alpha)."""
    S = size * SCALE
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (178, 182, 188, 255)
    t = SCALE * 2
    d.rectangle([0, 0, S, t], fill=c)
    d.rectangle([0, S - t, S, S], fill=c)
    for x in (0, S // 2, S):
        d.rectangle([x - t // 2, 0, x + t // 2, S], fill=c)
    for k in (0, S // 2):
        d.line([k, 0, k + S // 2, S], fill=c, width=max(1, SCALE * 3 // 2))
        d.line([k + S // 2, 0, k, S], fill=c, width=max(1, SCALE * 3 // 2))
    return im


def etfe_top(size=64):
    """The ETFE from above (u048, u053, u054: pale silver-grey pillows on ribs running down the slope, bright in the
    oblique aerials)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (204, 210, 218))
    d = ImageDraw.Draw(im)
    for x in range(0, S, SCALE * 4):
        d.line([x, 0, x, S], fill=(168, 176, 188), width=SCALE)
    for y in range(0, S, S // 4):
        d.line([0, y, S, y], fill=(150, 156, 166), width=SCALE)
    return im


def zinc_top(size=64):
    """The opaque roof from above: metal panels whose seams run down the slope. Pale where it mirrors the sky straight
    up (the orthophotos) but dark charcoal from every oblique view the flyover takes (u054, u055, u047), which is how
    the model draws it."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (70, 72, 78))
    d = ImageDraw.Draw(im)
    r = rng(33)
    for x in range(0, S, SCALE * 6):
        tone = int(r.integers(-4, 5))
        d.rectangle([x, 0, x + SCALE * 6, S], fill=(70 + tone, 72 + tone, 78 + tone))
        d.line([x, 0, x, S], fill=(56, 58, 62), width=max(1, SCALE // 2))
    return im


def lamps(size=(64, 32)):
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (30, 32, 36))
    d = ImageDraw.Draw(im)
    for x in range(SCALE * 2, W, SCALE * 8):
        d.rectangle([x, int(H * 0.25), x + SCALE * 5, int(H * 0.75)], fill=(255, 252, 246))
    return im


# --- the glass walls and the facade ------------------------------------------------------------------------------------

def glasswall(size=(128, 128), night=False):
    """The Legacy Gate's glass wall from inside (u001, u014): tall panes in a grid of slim dark mullions, a pale sky tint
    and mostly transparent so downtown's towers show through (alpha). By night (u044) the glass is dark and nearly clear
    and the mullions catch the stadium's light."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (18, 22, 30, 16) if night else (176, 200, 222, 56))
    d = ImageDraw.Draw(im)
    mullion = (112, 116, 124, 255) if night else (52, 56, 62, 255)
    for x in range(0, W, W // 8):
        d.rectangle([x, 0, x + SCALE, H], fill=mullion)
    for y in range(0, H, H // 8):
        d.rectangle([0, y, W, y + SCALE - 1], fill=mullion)
    return im


def zinc(size=128):
    """The dark zinc-coloured metal panels (u036, u053 to u055): near-black grey panels in staggered courses."""
    S = size * SCALE
    r = rng(41)
    im = Image.new("RGB", (S, S), (42, 44, 48))
    d = ImageDraw.Draw(im)
    ch = S // 16
    for k in range(16):
        off = int(r.integers(0, S // 4))
        for x in range(-off, S, S // 4):
            tone = int(r.integers(-5, 6))
            d.rectangle([x, k * ch, x + S // 4 - SCALE // 2, (k + 1) * ch - SCALE // 2], fill=(46 + tone, 48 + tone, 52 + tone))
    return im


def facade_glass(size=(128, 64)):
    """The reflective glass curtain walls (u036, u047: sky and downtown mirrored in large panes on a slim grid)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (hi, lo) in enumerate(zip((150, 170, 196), (86, 100, 118))):
        a[..., k] = hi + (lo - hi) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for x in range(0, W, W // 12):
        d.rectangle([x, 0, x + SCALE // 2, H], fill=(60, 66, 74))
    for y in range(0, H, H // 6):
        d.rectangle([0, y, W, y + SCALE // 2], fill=(60, 66, 74))
    return im


def prow_display(size=(128, 128)):
    """The prow's 49 x 76 ft LED display (Daktronics; u036 shows it running game-day graphics): SKOL and VIKINGS on
    purple, plain type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), VIK["purple"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(H * 0.44), W, int(H * 0.56)], fill=VIK["gold"])
    top = _row([_text("SKOL", VIK["white"])], W, int(H * 0.40), SCALE * 8, 0.8)
    im.paste(top, (0, int(H * 0.02)), top)
    bot = _row([_text("VIKINGS", VIK["white"])], W, int(H * 0.40), SCALE * 8, 0.7)
    im.paste(bot, (0, int(H * 0.58)), bot)
    return im


def board_wing(size=(64, 128)):
    """The boards' wing displays (the 2026 frames 047 and 048: the teams' scores, timeouts and the down on black): the
    game's own digits sit over the wing's upper half (``adjust_digits``); plain type below."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (8, 8, 10))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.05)], fill=VIK["purple"])
    d.rectangle([int(W * 0.08), int(H * 0.10), int(W * 0.92), int(H * 0.46)], fill=(26, 24, 34))
    word = _row([_text("SKOL", VIK["gold"])], W, int(H * 0.12), SCALE * 6, 0.8)
    im.paste(word, (0, int(H * 0.54)), word)
    down = _row([_text("1ST & 10", VIK["white"])], W, int(H * 0.10), SCALE * 6, 0.8)
    im.paste(down, (0, int(H * 0.72)), down)
    return im


def signs(size=(256, 128)):
    """Plain-type club bands on the upper decks' fascias (u017, 2021: HOME OF THE MINNESOTA VIKINGS in purple at the
    south-east; the 2023 and 2026 photos): four bands, the club's words only (the partners' marks are on their panels)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(im)
    q = H // 4
    bands = [(VIK["purple"], [_text("HOME OF THE", VIK["gold"]), _text("MINNESOTA VIKINGS", VIK["white"])]),
             (VIK["purple"], [_text("SKOL", VIK["gold"]), _text("VIKINGS", VIK["white"])]),
             (VIK["purple"], [_text("MINNESOTA VIKINGS", VIK["white"])]),
             ((12, 10, 18), [_text("SKOL", VIK["gold"]), _text("VIKINGS", VIK["white"])])]
    for k, (bg, items) in enumerate(bands):
        d.rectangle([0, k * q, W, (k + 1) * q], fill=bg)
        band = _row(items, W, q, SCALE * 8, 0.62)
        im.paste(band, (0, k * q), band)
    return im


def blue_sign(size=(128, 64), aspect=38.0 / 14.0):
    """The east wall's banner (u003, u019): the two-line lockup, "usbank" with its red shield over "stadium", white on
    U.S. Bank blue; drawn at the banner's own 38 x 14 m aspect and squeezed into the texture (it reads true on the
    banner)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    Wd = int(H * aspect)
    im = Image.new("RGBA", (Wd, H), (22, 86, 160, 255))
    lock = _lockup(True, (250, 250, 252), int(Wd * 0.9), int(H * 0.9))
    box = lock.getbbox()
    lock = lock.crop(box)
    im.paste(lock, ((Wd - lock.width) // 2, (H - lock.height) // 2), lock)
    return im.resize((W, H), Image.LANCZOS)


def panels(size=(128, 64), aspects=(25.8 / 8.2, 32.1 / 8.5)):
    """Two partner panels, each drawn at its own aspect and squeezed into a half of the texture, with the partners'
    official marks (Wikimedia Commons, public-domain text logos; never redrawn): top, the 3M panel at the east wall's
    north end (u003, u019: the red wordmark and the two-line tagline in plain type on light grey); bottom, the Land
    O'Lakes panel at the north-west (u014, u017, u044: the wordmark on a pale blue-grey panel)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    q = H // 2
    im = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    # the 3M panel
    Wd = int(q * aspects[0])
    a = Image.new("RGBA", (Wd, q), (226, 228, 230, 255))
    m3 = Image.open(MARK_3M).convert("RGBA")
    m3 = _fit(m3.crop(m3.getbbox()), int(Wd * 0.36), q, 0.66)
    a.paste(m3, (int(Wd * 0.07), (q - m3.height) // 2), m3)
    lines = [_text("Science.", (58, 58, 62)), _text("Applied to Life.", (58, 58, 62))]
    lh = int(q * 0.24)
    lines = [ln.resize((max(1, int(ln.width * lh / ln.height)), lh), Image.LANCZOS) for ln in lines]
    x, y = int(Wd * 0.48), (q - (2 * lh + int(lh * 0.35))) // 2
    for ln in lines:
        a.paste(ln, (x, y), ln)
        y += lh + int(lh * 0.35)
    im.paste(a.resize((W, q), Image.LANCZOS), (0, 0))
    # the Land O'Lakes panel
    Wd = int(q * aspects[1])
    b = Image.new("RGBA", (Wd, q), (212, 222, 232, 255))
    lol = Image.open(MARK_LOL).convert("RGBA")
    lol = _fit(lol.crop(lol.getbbox()), Wd, q, 0.84)
    b.paste(lol, ((Wd - lol.width) // 2, (q - lol.height) // 2), lol)
    im.paste(b.resize((W, H - q), Image.LANCZOS), (0, q))
    return im


def clerestory(size=(64, 64), night=False):
    """The band of windows under the roof along the walls (u003, u017, u019): mullions and a transom, the sky's light
    through the glass by day; the dark sky by night."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (26, 30, 42) if night else (190, 200, 212))
    d = ImageDraw.Draw(im)
    frame = (40, 42, 48) if night else (84, 88, 96)
    d.rectangle([0, 0, W, int(H * 0.12)], fill=(34, 36, 40))           # the roof's edge beam
    d.rectangle([0, int(H * 0.84), W, H], fill=(34, 36, 40))           # the sill
    d.rectangle([0, int(H * 0.47), W, int(H * 0.47) + SCALE * 2], fill=frame)
    for x in range(0, W, W // 4):
        d.rectangle([x, 0, x + SCALE * 2, H], fill=frame)
    return im


def flag(size=(128, 64)):
    """The United States flag (13 stripes, the 50-star union), hung from the roof (u003, u019)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    sh = H / 13.0
    for k in range(13):
        if k % 2 == 0:
            d.rectangle([0, int(k * sh), W, int((k + 1) * sh)], fill=(178, 34, 52))
    uw, uh = int(W * 0.4), int(sh * 7)
    d.rectangle([0, 0, uw, uh], fill=(60, 59, 110))
    for row in range(9):
        cols = 6 if row % 2 == 0 else 5
        for c in range(cols):
            cx = uw * ((c + (0.5 if row % 2 == 0 else 1.0)) / 6.0)
            cy = uh * ((row + 1) / 10.0)
            r_ = max(1, SCALE)
            d.ellipse([cx - r_, cy - r_, cx + r_, cy + r_], fill=(255, 255, 255))
    return im


# --- outside ------------------------------------------------------------------------------------------------------------

def towers(size=(64, 64), night=False):
    """Downtown's towers seen through the west glass wall and from the flyover, about a kilometre off (u014, u036,
    u054): hazy blue-grey glass and stone with faint window rows by day; dark with scattered lit windows by night."""
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(57)
    im = Image.new("RGB", (W, H), (22, 26, 36) if night else (132, 144, 160))
    d = ImageDraw.Draw(im)
    for y in range(0, H, SCALE * 4):
        for x in range(0, W, SCALE * 3):
            v = r.random()
            if night:
                fill = (214, 188, 132) if v < 0.34 else (58, 62, 74) if v < 0.5 else None
            else:
                fill = (158, 168, 180) if v < 0.5 else (116, 128, 144) if v < 0.7 else None
            if fill:
                d.rectangle([x, y + SCALE, x + SCALE * 2, y + SCALE * 3], fill=fill)
    return im


def lawn(size=128):
    """The Commons park's lawns and the plantings round the plaza."""
    S = size * SCALE
    r = rng(51)
    n = _blur(r.random((S, S)), SCALE * 3)
    n = (n - n.min()) / max(1e-6, n.max() - n.min())
    a = np.zeros((S, S, 3), np.float32)
    for k, (lo, hi) in enumerate(zip((70, 104, 52), (98, 132, 66))):
        a[..., k] = lo + (hi - lo) * n
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def sky(tod, size=(256, 128)):
    """The sky backdrop (s15's bundles carry no sky texture): a clear Minnesota sky by day, warmer low toward the
    horizon in the afternoon, dark blue at night; the bottom row meets the horizon."""
    W, H = size[0] * SCALE, size[1] * SCALE
    g = np.linspace(0.0, 1.0, H)[:, None, None]
    top, bot = {"d": ((96, 146, 212), (196, 214, 232)), "a": ((104, 138, 196), (238, 206, 170)),
                "n": ((6, 10, 24), (26, 34, 56))}[tod]
    a = np.array(top, np.float32) * (1 - g) + np.array(bot, np.float32) * g
    a = np.repeat(a, W, axis=1)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


# --- the field ------------------------------------------------------------------------------------------------------------

#: Act Global Xtreme Turf DX (ESPN 2023-12-21), synthetic: two-tone 5-yard bands (the 2026 week 1 frames)
TURF_LIGHT, TURF_DARK = (74, 122, 50), (60, 104, 42)


def field_turf(size=(128, 64), bands=20):
    """The colour map between the goal lines: u along the field (the model remaps the retail turf quad's UVs so u runs
    0 to 1 from the west goal line to the east), v across; 20 bands of 5 yards, flat (the grain is the detail layer's)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    for x in range(W):
        a[:, x] = np.array(TURF_LIGHT if int(x * bands / W) % 2 == 0 else TURF_DARK, np.float32)
    return Image.fromarray(a.astype(np.uint8))


def field_outside(size=128):
    """The turf outside the field of play, to the walls: the same turf, unbanded."""
    S = size * SCALE
    return Image.new("RGB", (S, S), (64, 110, 44))


def drawings():
    return {
        "usb_seat_front": (seat(0.04, 11), (64, 128)), "usb_seat_mid": (seat(0.08, 12), (64, 128)),
        "usb_seat_back": (seat(0.12, 13), (64, 128)),
        "usb_concrete": (base.concrete(), (64, 64)), "usb_wall": (wall(), (256, 32)),
        "LIGHT_usb_ribbon": (ribbon(), (256, 64)), "LIGHT_usb_glass": (base.glass(), (128, 64)),
        "LIGHT_usb_concourse": (base.concourse(), (128, 64)), "usb_portal": (base.vomitory(), (32, 32)),
        "usb_dark": (base.dark(), (32, 32)), "usb_black": (black(), (32, 32)),
        "usb_etfe_under": (etfe_under(), (128, 128)), "usb_roof_under": (roof_under(), (64, 64)),
        "usb_truss": (truss(), (64, 64)), "usb_etfe_top": (etfe_top(), (64, 64)), "usb_zinc_top": (zinc_top(), (64, 64)),
        "LIGHT_usb_lights": (lamps(), (64, 32)), "LIGHT_usb_glasswall": (glasswall(), (128, 128)),
        "LIGHT_usb_glasswall_n": (glasswall(night=True), (128, 128)),
        "usb_zinc": (zinc(), (64, 64)), "LIGHT_usb_facade_glass": (facade_glass(), (128, 64)),
        "LIGHT_usb_prow_display": (prow_display(), (128, 128)), "LIGHT_usb_board_wing": (board_wing(), (64, 128)),
        "usb_header": (header(), (256, 64)), "usb_letters": (letters(), (256, 64)),
        "usb_prow_letters": (prow_letters(), (128, 64)), "usb_letters_back": (letters_back(), (64, 16)),
        "LIGHT_usb_signs": (signs(), (256, 128)), "LIGHT_usb_blue_sign": (blue_sign(), (128, 64)),
        "LIGHT_usb_panels": (panels(), (128, 64)), "LIGHT_usb_clerestory": (clerestory(), (64, 64)),
        "LIGHT_usb_clerestory_n": (clerestory(night=True), (64, 64)),
        "usb_flag": (flag(), (128, 64)),
        "usb_plaza": (base.plaza(), (32, 32)), "usb_lawn": (lawn(), (32, 32)), "usb_asphalt": (base.asphalt(), (32, 32)),
        "usb_road": (base.road(), (32, 32)), "usb_building": (base.building(), (32, 32)),
        "LIGHT_usb_towers": (towers(), (64, 64)), "LIGHT_usb_towers_n": (towers(night=True), (64, 64)),
        "usb_sky_d": (sky("d"), (128, 64)), "usb_sky_a": (sky("a"), (128, 64)), "usb_sky_n": (sky("n"), (128, 64)),
        "field/usb_turf": (field_turf(), (128, 64)), "field/usb_turf_outside": (field_outside(), (128, 128)),
    }


def main(argv=None):
    global LOGO, MARK_3M, MARK_LOL
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--logo", required=True, help="the Commons wordmark rendered to PNG (author time only)")
    ap.add_argument("--mark-3m", required=True, help="the Commons 3M wordmark rendered to PNG (author time only)")
    ap.add_argument("--mark-lol", required=True, help="the Commons Land O'Lakes, Inc. logo PNG (author time only)")
    ap.add_argument("--masters")
    a = ap.parse_args(argv)
    LOGO = a.logo
    MARK_3M, MARK_LOL = a.mark_3m, a.mark_lol
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
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_usbank_model_art/v1", art=manifest), indent=1) + "\n")
    print("USBANK_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
