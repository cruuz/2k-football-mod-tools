#!/usr/bin/env python3
"""Draw the Highmark Stadium model's art (job st, 2026-09-25): deterministic, procedural, from sourced marks only.

  python3 tools/nfl2k5_highmark_model_art.py OUT_DIR [--masters MASTER_DIR] [--marks-root DIR] [--highmark-logo PNG]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model. Sources:
* the Highmark Stadium logo: en.wikipedia ``File:HighmarkStadium.svg`` (non-free logo, "Credit: Highmark Stadium"; SHA-256
  8e7d8626...a998 as downloaded 2026-09-25), rendered to PNG with Inkscape; only its wordmark part (HIGHMARK with its
  swoosh, STADIUM) is used, never redrawn, recoloured as the building's signs show it (white letters and a blue swoosh
  inside, per the 2026-09-17 home-opener photos; silver letters outside, per the Commons photo "Bills Stadium May26");
* the Bills' charging buffalo and wordmark: job u1's 2026 team folder (BUF/marks; sources recorded there: NFL.com club
  logo SVG, Commons ``Buffalo_Bills_wordmark.svg``); colours from the 2026 Record and Fact Book (royal #00338D, red
  #C60C30, navy #00274D);
* type: Roboto Condensed Bold (Apache 2.0) for plain-type panels only (sponsor names as type, never their logos);
* tones measured from the reference photos (the video-board test drone set, 2026; the Commons scrimmage photo, 2026-08-08):
  the red and royal seat mosaic, the grey perforated facade panels, the light-grey roof, the black canopy fascia with
  its blue LED line and white floodlights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"
U1 = Path("/media/noah/Storage/.b76-research/u1/teams")
LOGO = Path("/media/noah/Storage/.b76-research/st/refs/logos/highmark_stadium_logo_2048.png")
LOGO_SVG_SHA256 = "8e7d862677c9887379af005079823f4751d168d4a0167592229068d08b9ba998"
BILLS = dict(royal=(0, 51, 141), red=(198, 12, 48), navy=(0, 39, 77), white=(255, 255, 255))
HIGHMARK_BLUE = (0, 94, 184)            # the swoosh on the signs (the 2026 photos: a mid blue)
SCALE = 4


def rng(seed):
    return np.random.default_rng(seed)


def _blur(a, radius):
    a = np.asarray(a, np.float32)
    k = max(1, int(radius))
    for _ in range(3):
        for axis in (0, 1):
            acc = np.zeros_like(a)
            for s in range(-k, k + 1):
                acc += np.roll(a, s, axis=axis)
            a = acc / (2 * k + 1)
    return a


def reduce(master, size):
    return master.resize(size, Image.LANCZOS)


def font(px):
    return ImageFont.truetype(FONT, px)


def mark(path, height, colour=None):
    im = Image.open(path).convert("RGBA")
    im = im.crop(im.getbbox())
    w = max(1, int(im.width * height / im.height))
    im = im.resize((w, height), Image.LANCZOS)
    if colour is not None:
        a = np.asarray(im).copy()
        a[..., :3] = colour
        im = Image.fromarray(a)
    return im


def _text(word, colour, px=200):
    f = font(px)
    w = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(word, font=f))
    im = Image.new("RGBA", (w + 8, int(px * 1.25)), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4, 0), word, font=f, fill=colour + (255,))
    return im.crop(im.getbbox())


def _row(items, W, H, pad, hscale=0.62):
    scaled = []
    for im in items:
        h = int(H * im.info.get("hscale", hscale))
        w = max(1, int(im.width * h / im.height))
        scaled.append(im.resize((w, h), Image.LANCZOS))
    total = sum(im.width for im in scaled)
    gap = max(pad, (W - total) / max(1, len(scaled)))
    if total + gap * len(scaled) > W:
        f = (W - pad * len(scaled)) / total
        scaled = [im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))), Image.LANCZOS) for im in scaled]
        gap = (W - sum(im.width for im in scaled)) / len(scaled)
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = gap / 2
    for im in scaled:
        band.paste(im, (int(x), (H - im.height) // 2), im)
        x += im.width + gap
    return band


# --- the official marks -------------------------------------------------------------------------------------------

def highmark_wordmark(letters, swoosh):
    """The wordmark part of the official Highmark Stadium logo (HIGHMARK with its swoosh, and STADIUM), cut below the
    logo's stadium drawing and recoloured: the swoosh (every pixel left of the H's stem and above the letters' cap line)
    in ``swoosh``, the letters in ``letters``. The logo's own alpha is kept."""
    im = Image.open(LOGO).convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    H, W = a.shape[:2]
    alpha = a[..., 3]
    rows = np.nonzero(alpha.max(axis=1) > 16)[0]
    # the drawing and the wordmark are separated by an empty band: take everything below the first empty band after
    # the drawing
    filled = alpha.max(axis=1) > 16
    top = 0
    for y in range(int(H * 0.2), H):
        if not filled[y]:
            top = y
            break
    while top < H and not filled[top]:
        top += 1
    cut = a[top:].copy()
    ch, cw = cut.shape[:2]
    out = np.zeros_like(cut)
    out[..., 3] = cut[..., 3]
    # the swoosh is the one connected shape that spans the wordmark's width above the letters' cap line
    from scipy import ndimage
    lab, n = ndimage.label(cut[..., 3] > 24)
    sw = np.zeros((ch, cw), bool)
    for k, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is None:
            continue
        ys, xs = sl
        if (xs.stop - xs.start) > cw * 0.35 and ys.start < ch * 0.2:
            sw |= lab == k
    sw = ndimage.binary_dilation(sw, iterations=2) & (cut[..., 3] > 0)
    for k in range(3):
        out[..., k] = np.where(sw, swoosh[k], letters[k])
    img = Image.fromarray(out.astype(np.uint8), "RGBA")
    return img.crop(img.getbbox())


def bills_logo(colour=None):
    return mark(U1 / "BUF" / "marks" / "buf_logo_full.png", 400, colour)


def bills_word(colour=None):
    return mark(U1 / "BUF" / "marks" / "bills_wordmark.png", 300, colour)


# --- the bowl -----------------------------------------------------------------------------------------------------

def seat(p_red, seed, size=(64, 128)):
    """One section per u repeat and 21 rows per v repeat (the retail convention), the aisle steps centred on u = 0. The
    new stadium's seats fade by tier from red at the front rows to royal at the back (the 2026 construction and
    video-board photos: every section of every level runs red at the bottom, a scattered mix, then royal at the top), so
    the model lays three of these (``p_red`` 0.85, 0.5 and 0.12) over each tier's front, middle and back rows."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (70, 72, 78))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(160, 160, 156))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(58, 60, 64))
        for c in range(cols):
            x = c * pitch
            base = BILLS["red"] if r.random() < p_red else BILLS["royal"]
            tone = int(r.integers(-8, 9))
            fill = tuple(int(np.clip(v * 0.84 + tone, 0, 255)) for v in base)
            d.rectangle([x + SCALE, y0 + int(rh * 0.30), x + pitch - SCALE, y0 + int(rh * 0.94)], fill=fill)
    aisle = int(round(W * 0.16 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(170, 170, 166))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(120, 120, 116), width=SCALE)
    d.rectangle([0, 0, SCALE // 2, H], fill=(214, 214, 210))
    d.rectangle([W - SCALE // 2, 0, W, H], fill=(214, 214, 210))
    return im


def concrete(size=64):
    S = size * SCALE
    im = Image.new("RGB", (S, S), (172, 172, 168))
    d = ImageDraw.Draw(im)
    d.line([0, S // 2, S, S // 2], fill=(128, 128, 124), width=SCALE)
    return im


def wall(size=(256, 32)):
    """The field wall: the Bills' royal padding with a red top stripe and, every panel, the charging buffalo and
    BUFFALO BILLS in white (the 2026 home-opener and scrimmage photos: royal pads, "BUFFALO", "HOME OF THE BILLS")."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), BILLS["royal"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.12)], fill=BILLS["red"])
    items = [bills_logo(BILLS["white"]), _text("BUFFALO", BILLS["white"]), bills_logo(BILLS["white"]),
             _text("HOME OF THE BILLS", BILLS["white"])]
    band = _row(items, W, int(H * 0.88), SCALE * 12, 0.56)
    im.paste(band, (0, int(H * 0.12)), band)
    return im


def ribbon(size=(256, 64)):
    """The LED ribbons, two bands a texture: royal with the Bills' marks and BILLS MAFIA; white with HIGHMARK STADIUM
    and the club's partners as plain type (the 2026 photos show white ribbons carrying partner names; no partner logos
    are drawn)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    half = H // 2
    bands = [(BILLS["royal"], [bills_logo(), bills_word(BILLS["white"]), _text("BILLS MAFIA", BILLS["white"]),
                               bills_logo(), _text("GO BILLS", BILLS["white"])]),
             ((236, 238, 240), [highmark_wordmark((20, 24, 32), HIGHMARK_BLUE), _text("M&T BANK", (24, 60, 40)),
                                _text("SENECA", (40, 40, 44)), _text("LABATT BLUE LIGHT", (0, 60, 150)),
                                _text("PEPSI", (0, 70, 160))])]
    for k, (bg, items) in enumerate(bands):
        y0 = k * half
        ImageDraw.Draw(im).rectangle([0, y0, W, y0 + half], fill=bg)
        band = _row(items, W, half, SCALE * 10)
        im.paste(band, (0, y0), band)
    return im


def glass(size=(128, 64)):
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (24, 28, 36))
    d = ImageDraw.Draw(im)
    r = rng(3)
    for y in range(int(H * 0.26), int(H * 0.88)):
        t = (y - H * 0.26) / (H * 0.62)
        c = tuple(int(a + (b - a) * t) for a, b in zip((44, 50, 60), (22, 26, 33)))
        d.line([0, y, W, y], fill=c)
    for x in range(0, W, SCALE * 8):
        if r.random() < 0.55:
            w = int(SCALE * r.integers(2, 6))
            d.rectangle([x + SCALE, int(H * 0.62), x + SCALE + w, int(H * 0.84)], fill=(62, 52, 46))
    d.rectangle([0, 0, W, int(H * 0.14)], fill=(210, 210, 206))
    d.rectangle([0, int(H * 0.14), W, int(H * 0.26)], fill=(30, 32, 38))
    for x in range(SCALE * 2, W, SCALE * 8):
        d.rectangle([x, int(H * 0.19), x + SCALE * 3, int(H * 0.19) + SCALE * 2], fill=(255, 226, 176))
    for x in range(0, W, SCALE * 16):
        d.rectangle([x, int(H * 0.26), x + SCALE - 1, int(H * 0.88)], fill=(66, 70, 78))
    d.rectangle([0, int(H * 0.88), W, H], fill=(16, 18, 22))
    return im


def concourse(size=(128, 64)):
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (26, 28, 32))
    d = ImageDraw.Draw(im)
    r = rng(8)
    d.rectangle([0, 0, W, int(H * 0.10)], fill=(92, 94, 98))
    for x in range(SCALE * 3, W, SCALE * 16):
        d.rectangle([x, int(H * 0.13), x + SCALE * 6, int(H * 0.13) + SCALE * 2], fill=(255, 232, 190))
    for x in (int(W * 0.30), int(W * 0.80)):
        d.rectangle([x, int(H * 0.10), x + SCALE * 3, int(H * 0.74)], fill=(50, 52, 56))
    for _ in range(14):
        x = int(r.integers(0, W - SCALE * 3))
        h = int(SCALE * r.integers(5, 8))
        c = BILLS["royal"] if r.random() < 0.5 else (int(r.integers(40, 80)),) * 3
        d.rectangle([x, int(H * 0.74) - h, x + SCALE * 2, int(H * 0.74)], fill=c)
    d.rectangle([0, int(H * 0.74), W, int(H * 0.76)], fill=(160, 162, 166))
    d.rectangle([0, int(H * 0.76), W, int(H * 0.92)], fill=(48, 54, 62))
    for x in range(0, W, SCALE * 12):
        d.rectangle([x, int(H * 0.76), x + SCALE - 1, int(H * 0.92)], fill=(100, 104, 110))
    d.rectangle([0, int(H * 0.92), W, H], fill=(120, 120, 118))
    return im


def vomitory(size=32):
    S = size * SCALE
    return Image.new("RGB", (S, S), (16, 16, 18))


def dark(size=32):
    S = size * SCALE
    return Image.new("RGB", (S, S), (14, 15, 17))


# --- the canopy ---------------------------------------------------------------------------------------------------

def roof_top(size=128):
    """The canopy's top: light-grey standing-seam metal (the drone photos: a pale, even grey with fine seams running
    from the inner edge to the outside), with a few darker service strips."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (150, 154, 158))
    d = ImageDraw.Draw(im)
    r = rng(21)
    for x in range(0, S, SCALE * 4):
        tone = int(r.integers(-6, 7))
        d.rectangle([x, 0, x + SCALE * 4, S], fill=(150 + tone, 154 + tone, 158 + tone))
        d.line([x, 0, x, S], fill=(126, 130, 134), width=max(1, SCALE // 2))
    for y in (int(S * 0.33), int(S * 0.8)):
        d.rectangle([0, y, S, y + SCALE], fill=(116, 120, 124))
    return im


def roof_under(size=128):
    """The canopy's underside: dark grey steel (the scrimmage photo: a near-black underside with lighter trusses)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (44, 46, 52))
    d = ImageDraw.Draw(im)
    for x in range(0, S, SCALE * 16):
        d.rectangle([x, 0, x + SCALE * 2, S], fill=(84, 86, 92))          # the trusses (radial)
    for y in range(0, S, SCALE * 8):
        d.line([0, y, S, y], fill=(60, 62, 68), width=SCALE)              # the purlins
    return im


def led(size=(64, 16)):
    """The LED line under the canopy's inner edge: blue points on black (lit in Bills blue by day and at night in every
    2026 photo)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (8, 10, 18))
    d = ImageDraw.Draw(im)
    for x in range(SCALE * 2, W, SCALE * 8):
        d.ellipse([x, int(H * 0.3), x + SCALE * 4, int(H * 0.3) + SCALE * 4], fill=(40, 90, 255))
    d.rectangle([0, int(H * 0.72), W, H], fill=(20, 40, 150))
    return im


def fin_light(size=(16, 16)):
    """A fin's lit edge: a warm white LED line with a pale metal border (the week 2 night photo, 2026-09-17: a lit line
    down each fin between the plinth and the top band; by day the fin's bright metal edge, the Commons west photo)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (218, 220, 222))
    d = ImageDraw.Draw(im)
    d.rectangle([W // 4, 0, W - W // 4 - 1, H], fill=(252, 247, 232))
    return im


def floodlights(size=(64, 32)):
    """The floodlight heads under the inner edge: a pair of bright lamps in a dark frame."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (60, 62, 68))
    d = ImageDraw.Draw(im)
    for x in (int(W * 0.12), int(W * 0.56)):
        for y in range(int(H * 0.1), int(H * 0.9), SCALE * 6):
            d.rectangle([x, y, x + int(W * 0.3), y + SCALE * 4], fill=(255, 254, 246))
    return im


# --- the outside --------------------------------------------------------------------------------------------------

def facade(size=128):
    """One bay of the facade (u repeats every bay): tall silver-grey metal panels, each folded once down its middle so
    its two halves catch the light differently, between light vertical seams (the ribbon-cutting and construction
    photos, 2026: "HighmarkNYOct", the aerials; Dezeen: grey semi-translucent perforated metal panels), with the fine
    perforation as a texture."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (150, 154, 160))
    d = ImageDraw.Draw(im)
    r = rng(31)
    half = S // 2
    for x0, x1, base in ((0, half, (182, 186, 192)), (half, S, (148, 154, 162))):
        d.rectangle([x0, 0, x1, S], fill=base)
        for y in range(0, S, SCALE * 2):
            for x in range(x0 + SCALE, x1 - SCALE, SCALE * 2):
                if r.random() < 0.35:
                    d.point((x, y), fill=tuple(v - 18 for v in base))
    for y in range(0, S, S // 4):
        d.line([0, y, S, y], fill=(118, 122, 128), width=max(1, SCALE // 2))          # the panel joints
    d.rectangle([0, 0, SCALE, S], fill=(214, 216, 220))                              # the seam
    d.rectangle([half - SCALE // 2, 0, half + SCALE // 2, S], fill=(192, 196, 202))  # the fold
    # the sky in the metal: a cool sheen down each panel (the ribbon-cutting photos: the panels read silver)
    a = np.asarray(im).astype(np.float32)
    t = np.linspace(1.0, 0.0, S)[:, None, None]
    a = a * (1 - 0.18 * t) + np.array([214.0, 222.0, 234.0]) * 0.18 * t
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def base_band(size=(128, 64)):
    """The lower band: a dark iron-spot brick plinth under a storey of dark glass with slim mullions and a few warm
    lights inside (the ribbon-cutting photos: the concourse glazing at the foot of the facade)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (34, 38, 44))
    d = ImageDraw.Draw(im)
    r = rng(33)
    d.rectangle([0, int(H * 0.72), W, H], fill=(60, 58, 60))                          # the brick plinth
    for y in range(int(H * 0.72), H, SCALE * 3):
        d.line([0, y, W, y], fill=(44, 42, 44), width=1)
    for y in range(int(H * 0.08), int(H * 0.70)):                                     # the glass
        t = (y - H * 0.08) / (H * 0.62)
        d.line([0, y, W, y], fill=tuple(int(a + (b - a) * t) for a, b in zip((58, 66, 78), (26, 30, 36))))
    for x in range(0, W, SCALE * 10):
        d.rectangle([x, int(H * 0.08), x + SCALE, int(H * 0.70)], fill=(20, 22, 26))
        if r.random() < 0.4:
            d.rectangle([x + SCALE * 3, int(H * 0.46), x + SCALE * 6, int(H * 0.62)], fill=(150, 126, 90))
    d.rectangle([0, 0, W, int(H * 0.08)], fill=(24, 26, 30))                          # the soffit line
    return im


def portal(size=(64, 64)):
    """The black cladding of the main entrance portal at the north end (the ribbon-cutting photos, 2026-06-23)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (22, 23, 26))
    d = ImageDraw.Draw(im)
    for x in range(0, W, SCALE * 8):
        d.line([x, 0, x, H], fill=(34, 35, 40), width=SCALE)
    return im


def brick(size=64):
    """The base: dark grey iron-spot brick (Wikipedia; Dezeen)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (62, 60, 62))
    d = ImageDraw.Draw(im)
    r = rng(41)
    bh, bw = SCALE * 4, SCALE * 12
    for row, y in enumerate(range(0, S, bh)):
        off = (row % 2) * bw // 2
        for x in range(-bw, S, bw):
            t = int(r.integers(-8, 9))
            d.rectangle([x + off + 1, y + 1, x + off + bw - 2, y + bh - 2], fill=(70 + t, 67 + t, 68 + t))
            if r.random() < 0.25:
                d.point((x + off + int(r.integers(2, bw - 2)), y + bh // 2), fill=(40, 36, 34))
    return im


def entry(size=(64, 64)):
    """Glass entrances (the north end and the corners): lit glass with mullions."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (40, 52, 66))
    d = ImageDraw.Draw(im)
    for y in range(0, H, SCALE * 16):
        d.rectangle([0, y + SCALE * 10, W, y + SCALE * 13], fill=(200, 176, 130))
    for x in range(0, W, SCALE * 8):
        d.rectangle([x, 0, x + SCALE, H], fill=(70, 74, 80))
    return im


def letters(inside=True, size=(256, 64)):
    """The Highmark Stadium sign: the official wordmark (white letters and a blue swoosh inside; silver outside) on a
    clear background."""
    W, H = size[0] * SCALE, size[1] * SCALE
    mark_ = highmark_wordmark((250, 250, 250) if inside else (52, 56, 62), HIGHMARK_BLUE)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    h = int(H * 0.92)
    w = int(mark_.width * h / mark_.height)
    if w > W:
        w = W
        h = int(mark_.height * w / mark_.width)
    m = mark_.resize((w, h), Image.LANCZOS)
    im.paste(m, ((W - w) // 2, (H - h) // 2), m)
    return im


def bills_logo_sign(size=(128, 64)):
    """The charging buffalo on the west facade under the wordmark (Commons "Bills Stadium May26"; u1's club mark)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lg = bills_logo()
    h = int(H * 0.92); w = int(lg.width * h / lg.height)
    if w > W:
        w = W; h = int(lg.height * w / lg.width)
    lg = lg.resize((w, h), Image.LANCZOS)
    im.paste(lg, ((W - w) // 2, (H - h) // 2), lg)
    return im


def letters_back(size=(64, 16)):
    S = (size[0] * SCALE, size[1] * SCALE)
    return Image.new("RGB", S, (30, 30, 32))


def board_panels(size=(256, 64)):
    """The sponsor panels either side of the video boards (the home-opener photos: M&T Bank, Toyota, Labatt Blue Light,
    Seneca, Pepsi, Verizon): plain type on dark panels, two rows, no logos."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (10, 12, 16))
    half = H // 2
    rows = [[_text("M&T BANK", (255, 255, 255)), _text("TOYOTA", (235, 10, 30))],
            [_text("BLUE LIGHT", (70, 140, 255)), _text("SENECA", (255, 255, 255))]]
    for k, items in enumerate(rows):
        band = _row(items, W, half, SCALE * 16, 0.5)
        im.paste(band, (0, k * half), band)
    d = ImageDraw.Draw(im)
    d.line([0, half, W, half], fill=(40, 42, 48), width=SCALE)
    return im


def plaza(size=128):
    S = size * SCALE
    im = Image.new("RGB", (S, S), (176, 174, 168))
    d = ImageDraw.Draw(im)
    for k in range(0, S, SCALE * 16):
        d.line([k, 0, k, S], fill=(150, 148, 142), width=SCALE)
        d.line([0, k, S, k], fill=(150, 148, 142), width=SCALE)
    return im


def ground(size=128):
    """Grass and young trees round the site (the 2026 aerials: mown lawns, new plantings, woods beyond)."""
    S = size * SCALE
    r = rng(51)
    base = np.zeros((S, S, 3), np.float32)
    n = _blur(r.random((S, S)), SCALE * 3)
    n = (n - n.min()) / max(1e-6, n.max() - n.min())
    for k, (a, b) in enumerate(zip((70, 96, 50), (104, 128, 66))):
        base[..., k] = a + (b - a) * n
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def asphalt(size=128):
    """Parking: asphalt with white bay lines (u runs along the aisles)."""
    S = size * SCALE
    r = rng(61)
    a = (86 + 10 * _blur(r.random((S, S)), 2)).astype(np.uint8)
    im = Image.fromarray(np.dstack([a, a, a + 2]))
    d = ImageDraw.Draw(im)
    for x in range(0, S, SCALE * 3):
        d.line([x, int(S * 0.05), x, int(S * 0.45)], fill=(214, 214, 210), width=max(1, SCALE // 2))
        d.line([x, int(S * 0.55), x, int(S * 0.95)], fill=(214, 214, 210), width=max(1, SCALE // 2))
    return im


def dirt(size=64):
    """The old stadium's site across Abbott Road, structurally demolished by 2026-08-05 and being cleared: graded earth
    and crushed concrete (Wikipedia, "Ralph Wilson Stadium", Demolition)."""
    S = size * SCALE
    r = rng(71)
    n = _blur(r.random((S, S)), SCALE)
    n = (n - n.min()) / max(1e-6, n.max() - n.min())
    base = np.zeros((S, S, 3), np.float32)
    for k, (a, b) in enumerate(zip((120, 108, 92), (168, 160, 148))):
        base[..., k] = a + (b - a) * n
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def road(size=(64, 64)):
    """A road: asphalt with a yellow centre line and white edge lines (u across the road, v along it)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (70, 70, 72))
    d = ImageDraw.Draw(im)
    d.rectangle([int(W * 0.49), 0, int(W * 0.51), H], fill=(214, 180, 40))
    for x in (int(W * 0.04), int(W * 0.95)):
        d.rectangle([x, 0, x + SCALE, H], fill=(220, 220, 216))
    for y in range(0, H, SCALE * 16):
        for x in (int(W * 0.27), int(W * 0.73)):
            d.rectangle([x, y, x + SCALE, y + SCALE * 8], fill=(220, 220, 216))
    return im


def building(size=(64, 64)):
    """Low college and commercial buildings round the site (ECC South Campus, the Bills' fieldhouse): pale walls with
    window bands."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (178, 168, 150))
    d = ImageDraw.Draw(im)
    for y in range(int(H * 0.2), H, int(H * 0.35)):
        d.rectangle([0, y, W, y + int(H * 0.12)], fill=(60, 70, 82))
    return im


def trees(size=(64, 64)):
    """A band of woods (alpha): the tree line round Orchard Park in every 2026 aerial."""
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(81)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for _ in range(90):
        x = int(r.integers(0, W)); rr = int(SCALE * r.integers(4, 9))
        top = int(r.integers(int(H * 0.05), int(H * 0.45)))
        g = int(r.integers(60, 100))
        d.ellipse([x - rr, top, x + rr, top + rr * 2], fill=(g // 2, g, g // 3, 255))
        d.rectangle([x - rr, top + rr, x + rr, H], fill=(g // 2 - 6, g - 10, g // 3, 255))
    return im


# --- the field ------------------------------------------------------------------------------------------------

#: the natural grass (Kentucky bluegrass; Wikipedia "Highmark Stadium") mown in 5-yard bands across the field, a darker
#: green than the retail turf (the 2026 preseason and home-opener photos: light and dark bands every 5 yards)
GRASS_LIGHT, GRASS_DARK = (78, 118, 54), (54, 90, 40)


def field_grass(size=(128, 64), bands=20):
    """The field colour map between the goal lines: u along the field (the model remaps the retail turf quad's UVs so u
    runs 0 to 1 from the north goal line to the south), v across it; 20 mown bands of 5 yards, with a fine grain."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    for x in range(W):
        band = int(x * bands / W)
        a[:, x] = np.array(GRASS_LIGHT if band % 2 == 0 else GRASS_DARK, np.float32)
    # flat bands (the field span is the retail turf's: the grain lives in the detail layer, not in the colour map)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def field_outside(size=128):
    """The grass outside the field of play (to the walls): the same bluegrass, unstriped, a little darker and worn."""
    S = size * SCALE
    r = rng(92)
    n = _blur(r.random((S // 8, S // 8)), 2)
    n = (n - n.min()) / max(1e-6, n.max() - n.min())
    n = np.round(n * 3) / 3.0                                     # four soft tones: wear patches, not pixel noise
    n = np.kron(n, np.ones((8, 8)))
    base = np.zeros((S, S, 3), np.float32)
    for k, (lo, hi) in enumerate(zip((50, 82, 38), (62, 98, 46))):
        base[..., k] = lo + (hi - lo) * n
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


# --- driver -------------------------------------------------------------------------------------------------------

def drawings():
    return {
        "hm_seat_front": (seat(0.85, 11), (64, 128)), "hm_seat_mid": (seat(0.5, 12), (64, 128)),
        "hm_seat_back": (seat(0.12, 13), (64, 128)), "hm_concrete": (concrete(), (64, 64)),
        "hm_wall": (wall(), (256, 32)), "LIGHT_hm_ribbon": (ribbon(), (256, 64)),
        "LIGHT_hm_glass": (glass(), (128, 64)), "LIGHT_hm_concourse": (concourse(), (128, 64)),
        "hm_portal": (vomitory(), (32, 32)), "hm_dark": (dark(), (32, 32)), "hm_black": (portal(), (64, 64)),
        "LIGHT_hm_base": (base_band(), (128, 64)),
        "hm_roof_top": (roof_top(), (64, 64)), "hm_roof_under": (roof_under(), (64, 64)),
        "LIGHT_hm_led": (led(), (64, 16)), "LIGHT_hm_lights": (floodlights(), (64, 32)),
        "LIGHT_hm_finline": (fin_light(), (16, 16)),
        "hm_facade": (facade(), (128, 128)), "hm_brick": (brick(), (64, 64)), "LIGHT_hm_entry": (entry(), (64, 64)),
        "hm_letters": (letters(True), (256, 64)), "hm_letters_out": (letters(False), (256, 64)),
        "hm_letters_back": (letters_back(), (64, 16)), "hm_logo": (bills_logo_sign(), (128, 64)), "LIGHT_hm_board_panel": (board_panels(), (256, 64)),
        "hm_plaza": (plaza(), (64, 64)), "hm_ground": (ground(), (64, 64)), "hm_asphalt": (asphalt(), (64, 64)),
        "hm_dirt": (dirt(), (64, 64)), "hm_road": (road(), (64, 64)), "hm_building": (building(), (64, 64)),
        "hm_trees": (trees(), (64, 64)),
        "field/hm_grass": (field_grass(), (128, 64)), "field/hm_grass_outside": (field_outside(), (128, 128)),
    }


def main(argv=None):
    global U1, LOGO
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--masters")
    ap.add_argument("--marks-root", default=str(U1), help="the 2026 team folders (<root>/BUF/marks)")
    ap.add_argument("--highmark-logo", default=str(LOGO), help="the Highmark Stadium logo rendered from the official SVG")
    a = ap.parse_args(argv)
    U1, LOGO = Path(a.marks_root), Path(a.highmark_logo)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    masters = Path(a.masters) if a.masters else None
    if masters:
        masters.mkdir(parents=True, exist_ok=True)
    manifest = {}
    (out / "field").mkdir(exist_ok=True)
    for name, (master, size) in drawings().items():
        native = reduce(master, size)
        path = out / f"{name}.png"
        native.save(path, optimize=True)
        manifest[name] = dict(size=list(size), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if masters:
            (masters / "field").mkdir(exist_ok=True)
            master.save(masters / f"{name}.png", optimize=True)
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_highmark_model_art/v1", art=manifest), indent=1) + "\n")
    print("HIGHMARK_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
