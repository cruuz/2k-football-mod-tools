#!/usr/bin/env python3
"""Draw the Mercedes-Benz Stadium model's art (job st2, 2026-09-27): deterministic, procedural, from sourced marks only.

  python3 tools/nfl2k5_mercedes_benz_model_art.py OUT_DIR [--masters MASTER_DIR] [--star PNG]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model. Sources:
* the Mercedes-Benz star, where the building shows it (the facade's petals and the window to the city's end): Wikimedia
  Commons ``Mercedes-Benz_Star_2022.svg`` (source: the Mercedes-Benz Group website; PD-textlogo, trademarked; SHA-1
  6f1958c4982fca91582b4b52d479c4b23e2595e1, SHA-256 1c35cb516ffff6dc694730726a19241b0af8ad5c5d4a5e8e449954601b9d46c9 as
  downloaded 2026-09-27), rendered to PNG with Inkscape, never redrawn;
* the venue's sign on the facade's petals: the wordmark part of the venue's own logo (en.wikipedia
  ``File:Mercedes-Benz_Stadium_logo.svg``, non-free logo, source mercedesbenzstadium.com; SHA-256 6cb09179...64cf as
  downloaded 2026-09-27), rendered with Inkscape, cropped and recoloured as the building shows it, never redrawn;
* the venue's name as plain type: Liberation Serif Regular (SIL OFL) for the one-line "Mercedes-Benz Stadium" sign the
  bridge at the west end carries (Commons "NFL 2021 - Washington at Falcons 322": white serif type on black), Roboto
  Condensed Bold (Apache 2.0) for the Falcons' plain-type panels (no club logo is drawn);
* tones measured from the reference photos (Commons: the 2018 and 2019 Peach Bowls, the 2025 CFP final from the press box,
  the 2024 interiors, the Halo with the roof closed and open, the Super Bowl LIII aerials, the 2019 exteriors; the
  Falcons' 2025 "Bird's Eye View" galleries): the red seats, the black fascias with their white and teal LED lines, the
  Halo's red and black graphics, the roof's dark steel web over the translucent panels, the silver-grey metal petals and
  the blue-grey glass of the facade, the turf and the green of the city round it; the sky backdrop's blues and greys
  (pass 3) from the same exteriors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nfl2k5_highmark_model_art as base  # noqa: E402

SCALE = base.SCALE
rng, _blur, reduce, font, _text, _row = base.rng, base._blur, base.reduce, base.font, base._text, base._row
STAR = Path("/media/noah/Storage/.b76-research/st/refs/logos/mercedes_star_2048.png")
STAR_SVG_SHA256 = "1c35cb516ffff6dc694730726a19241b0af8ad5c5d4a5e8e449954601b9d46c9"
LOGO = Path("/media/noah/Storage/.b76-research/st/refs/logos/mercedes_benz_stadium_logo_2048.png")
LOGO_SVG_SHA256 = "6cb0917978004e76d7a39bcc5a4d0057e1fa4e782e13f0b2cc2432faa6fc64cf"
SERIF = "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
#: the Falcons' colours (the club's 2026 style: red #A71930, black, silver #A5ACAF, white)
FALCONS = dict(red=(167, 25, 48), black=(0, 0, 0), silver=(165, 172, 175), white=(255, 255, 255))
#: the stadium's LED lines (the 2024 interiors: a teal line along the upper fascias)
TEAL = (40, 214, 212)
#: FieldTurf in 5-yard bands (the 2025 bird's-eye photos: a mid green, the bands faint)
TURF_LIGHT, TURF_DARK = (74, 128, 60), (64, 116, 52)


def seat(p_dark, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0. The seats are red
    (every photo: the whole bowl red), a few darker seats scattered through them (``p_dark``)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (96, 30, 34))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(150, 148, 146))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(58, 24, 26))
        for c in range(cols):
            x = c * pitch
            basec = (120, 26, 34) if r.random() < p_dark else (178, 34, 42)
            tone = int(r.integers(-8, 9))
            fill = tuple(int(np.clip(v + tone, 0, 255)) for v in basec)
            d.rectangle([x + SCALE, y0 + int(rh * 0.30), x + pitch - SCALE, y0 + int(rh * 0.94)], fill=fill)
    aisle = int(round(W * 0.16 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(150, 148, 146))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(110, 108, 106), width=SCALE)
    return im


def wall(size=(256, 32)):
    """The field wall: black padding with a thin red line along its top and plain type (no club logo)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (8, 8, 10))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.07)], fill=FALCONS["red"])
    items = [_text("FALCONS", FALCONS["white"]), _text("RISE UP", FALCONS["red"]), _text("ATLANTA", FALCONS["white"]),
             _text("MERCEDES-BENZ STADIUM", FALCONS["silver"])]
    band = _row(items, W, int(H * 0.93), SCALE * 12, 0.5)
    im.paste(band, (0, int(H * 0.07)), band)
    return im


def ribbon(size=(256, 64)):
    """The LED ribbons on the fascias (plain type, no logos): a black band with a teal line and FALCONS and RISE UP in
    white; and a band of red, black and white segments with the partners' names as type (the photos: red and white
    ribbons with partner names)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    h = H // 2
    top = Image.new("RGB", (W, h), (6, 6, 8))
    ImageDraw.Draw(top).rectangle([0, h - SCALE * 2, W, h], fill=TEAL)
    band = _row([_text("FALCONS", FALCONS["white"]), _text("RISE UP", FALCONS["red"]), _text("ATLANTA", FALCONS["white"]),
                 _text("RISE UP", FALCONS["red"])], W, h - SCALE * 2, SCALE * 10, 0.56)
    top.paste(band, (0, 0), band)
    im.paste(top, (0, 0))
    segs = [(FALCONS["red"], [_text("GEORGIA POWER", FALCONS["white"])]),
            ((10, 10, 12), [_text("MERCEDES-BENZ STADIUM", FALCONS["white"])]),
            ((240, 240, 242), [_text("DELTA", FALCONS["red"])]),
            (FALCONS["black"], [_text("ATL", FALCONS["red"])])]
    x = 0
    for (bg, items), w in zip(segs, (0.28, 0.32, 0.20, 0.20)):
        sw = int(W * w) if x + int(W * w) <= W else W - x
        seg = Image.new("RGB", (sw, h), bg)
        b = _row(items, sw, h, SCALE * 6, 0.56)
        seg.paste(b, (0, 0), b)
        im.paste(seg, (x, h))
        x += sw
    if x < W:
        im.paste(Image.new("RGB", (W - x, h), (6, 6, 8)), (x, h))
    return im


def black(size=32):
    """The Halo's housing, the column board's frame, the bridge: near black with faint panel seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (12, 13, 15))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(24, 25, 28), width=SCALE // 2)
        d.line([0, k, S, k], fill=(24, 25, 28), width=SCALE // 2)
    return im


def roof_under(size=128):
    """The pinwheel's eight panels from below, closed (the 2019 Peach Bowl and 2018 photos): light translucent ETFE seen
    through a dense web of dark steel (radial trusses, rings and cross bracing)."""
    S = size * SCALE
    r = rng(29)
    a = np.zeros((S, S, 3), np.float32)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    for k, v in enumerate((206, 210, 214)):
        a[..., k] = v * (0.90 + 0.10 * n)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    step = S // 6
    for k in range(0, S, step):
        d.rectangle([k, 0, k + SCALE * 3, S], fill=(40, 42, 46))
        d.rectangle([0, k, S, k + SCALE * 2], fill=(52, 54, 58))
    for k in range(-S, S, step):
        d.line([k, 0, k + S, S], fill=(64, 66, 70), width=max(1, SCALE))
        d.line([k + S, 0, k, S], fill=(64, 66, 70), width=max(1, SCALE))
    return im


def ring(size=64):
    """The fixed roof round the oculus, from below (the photos: dark steel trusses and catwalks with rows of lamps and
    speaker clusters over the upper deck)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (30, 32, 36))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 6):
        d.rectangle([k, 0, k + SCALE * 2, S], fill=(58, 60, 66))
        d.line([0, k, S, k], fill=(48, 50, 54), width=SCALE)
    for k in range(-S, S, S // 3):
        d.line([k, 0, k + S, S], fill=(46, 48, 52), width=SCALE)
    for x in range(SCALE * 4, S, SCALE * 16):
        d.rectangle([x, S // 2 - SCALE * 2, x + SCALE * 6, S // 2 + SCALE * 2], fill=(236, 232, 220))
    return im


def roof_top(size=64):
    """The roof from above (the Super Bowl LIII aerials): the flat ring's silver-grey panels and the pale membrane, with
    their seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (198, 202, 208))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 6):
        d.line([x, 0, x, S], fill=(192, 196, 202), width=SCALE)
    for y in range(0, S, S // 3):
        d.line([0, y, S, y], fill=(204, 208, 212), width=max(1, SCALE // 2))
    return im


def pinwheel(size=128):
    """The pinwheel's eight panels from above (the Super Bowl LIII aerials and the Falcons' rooftop photos): dark
    translucent ETFE over the bowl, the white steel of the panels' frames across it."""
    S = size * SCALE
    r = rng(31)
    a = np.zeros((S, S, 3), np.float32)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    for k, v in enumerate((92, 98, 106)):
        a[..., k] = v * (0.90 + 0.12 * n)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    step = S // 4
    for k in range(0, S, step):
        d.rectangle([k, 0, k + SCALE * 2, S], fill=(206, 210, 216))
        d.rectangle([0, k, S, k + SCALE * 2], fill=(206, 210, 216))
    for k in range(-S, S, step):
        d.line([k, 0, k + S, S], fill=(170, 174, 180), width=max(1, SCALE))
    return im


def lamps(size=(64, 32)):
    S_w, S_h = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (S_w, S_h), (30, 32, 36))
    d = ImageDraw.Draw(im)
    for x in range(SCALE * 2, S_w, SCALE * 8):
        d.rectangle([x, int(S_h * 0.25), x + SCALE * 5, int(S_h * 0.75)], fill=(255, 252, 244))
    return im


def _halo_layout(W, H, window):
    """One Halo graphics layout (W x H): the red panel with its white rules; ``window``: "ATL" and "RISE UP" either side
    of the digits' dark window (the game's digits sit in it), else the club layout without a window: "RISE UP" large in
    its place with "ATL" either side; "FALCONS" under them."""
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, W)[None, :]
    red = np.array(FALCONS["red"], np.float32)
    dark = np.array((40, 6, 12), np.float32)
    a[:] = red * (1 - 0.55 * np.abs(g - 0.5) * 2)[..., None] + dark * (0.55 * np.abs(g - 0.5) * 2)[..., None]
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.05)], fill=FALCONS["white"])
    d.rectangle([0, int(H * 0.95), W, H], fill=FALCONS["white"])
    if window:
        # the digits' window in the middle of the panel's upper half
        d.rectangle([int(W * 0.30), int(H * 0.16), int(W * 0.70), int(H * 0.58)], fill=(10, 10, 12))
        sides = ("ATL", "RISE UP")
    else:
        mid = _row([_text("RISE UP", FALCONS["white"])], int(W * 0.40), int(H * 0.42), SCALE * 6, 0.9)
        im.paste(mid, (int(W * 0.30), int(H * 0.16)), mid)
        sides = ("ATL", "ATL")
    left = _row([_text(sides[0], FALCONS["white"])], int(W * 0.26), int(H * 0.5), SCALE * 6, 0.62)
    im.paste(left, (int(W * 0.02), int(H * 0.12)), left)
    right = _row([_text(sides[1], FALCONS["white"])], int(W * 0.26), int(H * 0.5), SCALE * 6,
                 0.5 if sides[1] == "RISE UP" else 0.62)
    im.paste(right, (int(W * 0.72), int(H * 0.12)), right)
    word = _row([_text("FALCONS", FALCONS["white"])], int(W * 0.5), int(H * 0.3), SCALE * 6, 0.8)
    im.paste(word, (int(W * 0.25), int(H * 0.62)), word)
    return im


def halo(size=(256, 128)):
    """The Halo's graphic panels between the live pictures (the 2019 and 2025 photos: red and black club graphics, the
    teams' names as type, the score and clock in a dark window where the game's digits sit): plain type, no logos. Two
    layouts stacked (the model maps each half): the top half with the digits' window for the two panels over the
    sidelines, the bottom half the club layout for the other four (the pair lab, 2026-09-28: those four showed the
    window empty)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H))
    im.paste(_halo_layout(W, H // 2, True), (0, 0))
    im.paste(_halo_layout(W, H // 2, False), (0, H // 2))
    return im


def window(size=(128, 128)):
    """The window to the city from inside (the 2018 Peach Bowl photo): a tall steel grid with diagonal members, the panes
    mostly transparent so downtown's towers show through (alpha)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (190, 204, 220, 56))
    d = ImageDraw.Draw(im)
    for x in range(0, W, W // 8):
        d.rectangle([x, 0, x + SCALE, H], fill=(46, 48, 52, 255))
    for y in range(0, H, H // 4):
        d.rectangle([0, y, W, y + SCALE], fill=(46, 48, 52, 255))
    d.line([0, H, W, 0], fill=(40, 42, 46, 255), width=SCALE * 2)
    return im


def panel(size=(128, 128)):
    """The facade's metal petals (the 2019 exteriors and the Super Bowl LIII aerials): silver-grey panels in long courses,
    their seams a darker grey (the aerials read them as silver-grey against the white roof membrane)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(71)
    a = np.zeros((H, W, 3), np.float32)
    n = _blur(r.random((H // 8, W // 8)), 1)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((8, 8)))[:H, :W]
    for k, v in enumerate((180, 186, 194)):
        a[..., k] = v * (0.93 + 0.07 * n)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for y in range(0, H, H // 8):
        d.line([0, y, W, y], fill=(146, 152, 160), width=max(1, SCALE // 2))
    for x in range(0, W, W // 4):
        d.line([x, 0, x, H], fill=(156, 162, 170), width=max(1, SCALE // 2))
    return im


def glass_out(size=(128, 128)):
    """The facade's glass and clear polymer from outside (the 2019 exteriors: blue-grey panes taking the sky, a diagonal
    grid of silver mullions)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (lo, hi) in enumerate(zip((120, 148, 184), (56, 74, 102))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for k in range(-H, W + H, W // 4):
        d.line([k, H, k + H, 0], fill=(200, 206, 214), width=SCALE)
        d.line([k, 0, k + H, H], fill=(200, 206, 214), width=SCALE)
    return im


def glass_base(size=(128, 64)):
    """The glass band round the concourses over the plaza (pass 3, main: "fewer, larger glass facets"; the 2019 and 2024
    exteriors: tall panes on a coarse diagonal frame): four panes across by two up, each split on its diagonal (the
    diagonals turning pane to pane), silver mullions, the glass taking the sky above and darker below."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (lo, hi) in enumerate(zip((126, 154, 190), (60, 78, 106))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    pw, ph = W // 4, H // 2
    mull = (200, 206, 214)
    for i in range(4):
        for j in range(2):
            x0, y0 = i * pw, j * ph
            if (i + j) % 2:
                d.line([x0, y0, x0 + pw, y0 + ph], fill=mull, width=SCALE)
            else:
                d.line([x0, y0 + ph, x0 + pw, y0], fill=mull, width=SCALE)
    for i in range(5):
        d.rectangle([i * pw - SCALE, 0, i * pw + SCALE, H], fill=mull)
    for j in range(3):
        d.rectangle([0, j * ph - SCALE, W, j * ph + SCALE], fill=mull)
    return im


def star(size=128):
    """The Mercedes-Benz star (the official vector, rendered; never redrawn), on transparent."""
    S = size * SCALE
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    if STAR.exists():
        mk = Image.open(STAR).convert("RGBA")
        mk = mk.crop(mk.getbbox()).resize((int(S * 0.96), int(S * 0.96)), Image.LANCZOS)
        im.paste(mk, ((S - mk.width) // 2, (S - mk.height) // 2), mk)
    return im


def wordmark(size=(128, 64)):
    """The venue's sign on the facade's petals (the Super Bowl LIII aerial and the Centennial Olympic Park Drive view:
    "Mercedes-Benz" over "STADIUM" in dark type on the silver panels): the wordmark part of the venue's own logo
    (en.wikipedia ``File:Mercedes-Benz_Stadium_logo.svg``, non-free logo, source mercedesbenzstadium.com; SHA-1
    627b83faedc351d9f06a8cf98067a16abe1d0570, SHA-256 6cb0917978004e76d7a39bcc5a4d0057e1fa4e782e13f0b2cc2432faa6fc64cf
    as downloaded 2026-09-27; rendered with Inkscape), cropped below its building drawing, recoloured dark grey as the
    building shows it, never redrawn."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if LOGO.exists():
        lg = Image.open(LOGO).convert("RGBA")
        a = np.asarray(lg)
        rows = np.nonzero((a[..., 3] > 40).any(axis=1))[0]
        # the drawing ends where the first clear band of rows under it begins (the wordmark starts under that gap)
        cut = int(lg.height * 0.52)
        for yy in range(int(lg.height * 0.40), int(lg.height * 0.62)):
            if not (a[yy, :, 3] > 40).any():
                cut = yy
                break
        text = lg.crop((0, cut, lg.width, int(rows.max()) + 1))
        text = text.crop(text.getbbox())
        arr = np.asarray(text).copy()
        arr[..., :3] = (44, 46, 50)
        text = Image.fromarray(arr)
        f = min(W * 0.94 / text.width, H * 0.90 / text.height)
        text = text.resize((max(1, int(text.width * f)), max(1, int(text.height * f))), Image.LANCZOS)
        im.paste(text, ((W - text.width) // 2, (H - text.height) // 2), text)
    return im


def name_sign(size=(256, 32)):
    """The bridge's name sign (the 2021 photo): "Mercedes-Benz Stadium" in white serif type on black."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (14, 14, 16))
    f = ImageFont.truetype(SERIF, int(H * 0.72))
    word = "Mercedes-Benz Stadium"
    tw = ImageDraw.Draw(im).textlength(word, font=f)
    if tw > W * 0.94:
        f = ImageFont.truetype(SERIF, int(H * 0.72 * W * 0.94 / tw))
        tw = ImageDraw.Draw(im).textlength(word, font=f)
    ImageDraw.Draw(im).text(((W - tw) / 2, H * 0.10), word, font=f, fill=(244, 244, 244))
    return im


def column(size=(32, 128)):
    """The tall board by the window (the 2018 and 2019 photos: a vertical LED column with club graphics): red to black
    with FALCONS up it as plain type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (lo, hi) in enumerate(zip(FALCONS["red"], (20, 4, 8))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    t = _text("FALCONS", FALCONS["white"]).rotate(90, expand=True)
    t = t.resize((int(W * 0.6), int(t.height * W * 0.6 / t.width)), Image.LANCZOS)
    if t.height > H * 0.8:
        t = t.resize((max(1, int(t.width * H * 0.8 / t.height)), int(H * 0.8)), Image.LANCZOS)
    im.paste(t, ((W - t.width) // 2, (H - t.height) // 2), t)
    return im


def skyline(size=(64, 64)):
    """Downtown's towers: glass and stone with rows of windows (lit by night through the LIGHT_ class)."""
    S_w, S_h = size[0] * SCALE, size[1] * SCALE
    r = rng(57)
    im = Image.new("RGB", (S_w, S_h), (104, 112, 124))
    d = ImageDraw.Draw(im)
    for y in range(0, S_h, SCALE * 4):
        for x in range(0, S_w, SCALE * 3):
            if r.random() < 0.5:
                d.rectangle([x, y + SCALE, x + SCALE * 2, y + SCALE * 3], fill=(226, 214, 176))
    return im


def field_turf(size=(128, 64), bands=20):
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    for x in range(W):
        band = int(x * bands / W)
        a[:, x] = np.array(TURF_LIGHT if band % 2 == 0 else TURF_DARK, np.float32)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def field_outside(size=128):
    """The turf outside the field of play (to the walls): the same green, unstriped."""
    S = size * SCALE
    return Image.new("RGB", (S, S), (68, 120, 54))


def sky(kind, size=(128, 64)):
    """The sky backdrop round the building (pass 3; v = 1 at the backdrop's foot, just under the horizon, which sits
    about 0.9 of the way down): Atlanta's blue by day with soft fair-weather cloud (the 2018 and 2024 exteriors), warmer
    and lower in the afternoon, the city's glow under a dark sky at night, an even grey overcast for the rain and snow
    bundles by day."""
    W, H = size[0] * SCALE, size[1] * SCALE
    ends = dict(d=((88, 140, 206), (206, 224, 238)), a=((104, 132, 190), (244, 204, 158)),
                n=((12, 16, 28), (70, 62, 66)), o=((142, 150, 160), (192, 196, 200)))[kind]
    y = np.linspace(0.0, 1.0, H)[:, None, None] ** 1.6
    img = (np.array(ends[0], np.float32) * (1 - y) + np.array(ends[1], np.float32) * y) * np.ones((1, W, 1), np.float32)
    if kind in "da":
        r = rng(41)
        cloud = r.random((H // 16 + 1, W // 16 + 1)).astype(np.float32)
        cloud = np.asarray(Image.fromarray((cloud * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 255
        cloud = _blur(cloud, SCALE * 2)
        band = np.clip(1.0 - np.abs(np.linspace(0.0, 1.0, H) - 0.55) / 0.35, 0, 1)[:, None]
        k = np.clip((cloud - 0.55) * 3.0, 0, 1) * band
        img = img * (1 - 0.55 * k[..., None]) + np.array((242, 242, 240), np.float32) * 0.55 * k[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def drawings():
    return {
        "mb_seat_front": (seat(0.06, 11), (64, 128)), "mb_seat_mid": (seat(0.10, 12), (64, 128)),
        "mb_seat_back": (seat(0.16, 13), (64, 128)),
        "mb_concrete": (base.concrete(), (64, 64)), "mb_wall": (wall(), (256, 32)),
        "LIGHT_mb_ribbon": (ribbon(), (256, 64)), "LIGHT_mb_glass": (base.glass(), (128, 64)),
        "LIGHT_mb_concourse": (base.concourse(), (128, 64)), "mb_portal": (base.vomitory(), (32, 32)),
        "mb_dark": (base.dark(), (32, 32)), "mb_black": (black(), (32, 32)),
        "mb_roof_under": (roof_under(), (128, 128)), "mb_ring": (ring(), (64, 64)), "mb_roof_top": (roof_top(), (64, 64)),
        "mb_pinwheel": (pinwheel(), (64, 64)),
        "LIGHT_mb_lights": (lamps(), (64, 32)), "LIGHT_mb_halo": (halo(), (256, 128)),
        "LIGHT_mb_window": (window(), (128, 128)), "mb_panel": (panel(), (128, 128)), "mb_glass_out": (glass_out(), (64, 64)),
        "mb_star": (star(), (128, 128)), "mb_sign": (wordmark(), (128, 64)), "mb_name": (name_sign(), (256, 32)),
        "LIGHT_mb_column": (column(), (32, 128)),
        "mb_plaza": (base.plaza(), (32, 32)), "LIGHT_mb_skyline": (skyline(), (64, 64)),
        "mb_sky_d": (sky("d"), (128, 64)), "mb_sky_a": (sky("a"), (128, 64)), "mb_sky_n": (sky("n"), (128, 64)),
        "mb_sky_o": (sky("o"), (128, 64)), "mb_glass_base": (glass_base(), (128, 64)),
        "field/mb_grass": (field_turf(), (128, 64)), "field/mb_grass_outside": (field_outside(), (128, 128)),
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
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_mercedes_benz_model_art/v1", art=manifest), indent=1) + "\n")
    print("MERCEDES_BENZ_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
