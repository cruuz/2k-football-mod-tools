#!/usr/bin/env python3
"""Draw the SoFi Stadium model's art (job u6): deterministic, procedural, from sourced marks only.

  python3 tools/nfl2k5_sofi_model_art.py OUT_DIR [--masters MASTER_DIR] [--rams-marks DIR] [--chargers-marks DIR]
                                         [--sofi-logo PNG]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model. Sources:
* the SoFi Stadium logo: Wikimedia Commons ``SoFi_Stadium_Logo.svg`` (public domain; StadCo LA), rendered to PNG;
* the Rams' club logo (NFL.com club logo SVG) and 2020 wordmark (Commons ``LA_Rams_wordmark.svg``, PD-textlogo) and
  the Chargers' club bolt, from the 2026 team folders of job u1 (d8, d4; sources recorded there); the Rams' marks may
  be replaced by job u7's, which is just a new ``--marks-root`` folder;
* the Chargers' 2020 wordmark: Commons ``Los_Angeles_Chargers_2020_wordmark.svg`` (public domain);
* type: Roboto Condensed Bold (Apache 2.0);
* tones measured from the Commons photos (the CFP title game set, 2023; the 2026 World Cup set): the charcoal seats,
  the sky-lit ETFE, the white aluminium canopy.
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
LOGO = Path("/media/noah/Storage/.b76-research/u6/refs/logos/sofi_logo_2048.png")
LAC_WORDMARK = Path("/media/noah/Storage/.b76-research/u6/refs/logos/lac_wordmark_2020.png")
RAMS = dict(royal=(0, 53, 148), sol=(255, 209, 0), white=(255, 255, 255))            # u7 (therams.com)
CHARGERS = dict(powder=(0, 128, 198), gold=(255, 194, 14), navy=(0, 42, 94), white=(255, 255, 255))  # d4
SCALE = 4


def rng(seed):
    return np.random.default_rng(seed)


def _blur(a, radius):
    """Separable box blur (three passes approximate a Gaussian) of a float array, wrapping at the edges."""
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
    """A sourced mark scaled to ``height`` px, optionally recoloured (keeping its alpha)."""
    im = Image.open(path).convert("RGBA")
    bbox = im.getbbox()
    im = im.crop(bbox)
    w = max(1, int(im.width * height / im.height))
    im = im.resize((w, height), Image.LANCZOS)
    if colour is not None:
        a = np.asarray(im).copy()
        a[..., :3] = colour
        im = Image.fromarray(a)
    return im


# --- the bowl ---------------------------------------------------------------------------------------------------

def seat(size=128):
    """One seating section per repeat (the model runs u from aisle to aisle) and 21 rows per repeat (the retail
    convention): charcoal seat backs over a pale concrete riser edge on every row, so empty rows read as rows (c082),
    and the aisle's steps centred on u = 0 (split across the two edges), with a handrail down the middle. The crowd
    covers the seats, so the steps show only through its 1.2 m gaps."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (36, 38, 42))
    d = ImageDraw.Draw(im)
    r = rng(1)
    rows = 21
    rh = S / rows
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, S, y0 + int(rh * 0.16)], fill=(118, 118, 114))                 # the riser's lit edge
        d.rectangle([0, y0 + int(rh * 0.16), S, y0 + int(rh * 0.30)], fill=(30, 31, 35))   # the tread in shadow
        for x in range(0, S, SCALE * 5):
            tone = int(r.integers(-5, 6))
            d.rectangle([x + SCALE, y0 + int(rh * 0.30), x + SCALE * 4, y0 + int(rh * 0.94)],
                        fill=(52 + tone, 55 + tone, 62 + tone))                              # the seat backs
    aisle = int(round(S * 0.16 / 2))            # half the steps' width: twice the crowd's gap, so a gap seen at an angle
                                                # still looks onto the steps, not the seats beside them (offline, v15)
    for x0, x1 in ((0, aisle), (S - aisle, S)):
        d.rectangle([x0, 0, x1, S], fill=(146, 146, 142))                                   # the steps
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (S - aisle, S)):
            d.line([x0, y, x1, y], fill=(104, 104, 100), width=SCALE)                        # the step nosings
    d.rectangle([0, 0, SCALE // 2, S], fill=(200, 200, 196))                                 # the handrail
    d.rectangle([S - SCALE // 2, 0, S, S], fill=(200, 200, 196))
    return im


def concrete(size=64):
    S = size * SCALE
    im = Image.new("RGB", (S, S), (206, 206, 202))
    d = ImageDraw.Draw(im)
    d.line([0, S // 2, S, S // 2], fill=(128, 128, 124), width=SCALE)
    return im


def _row(items, W, H, pad):
    """Lay items (RGBA images) along a W x H band, scaled to the band and spaced to fill it exactly, so the band tiles
    without cut words."""
    scaled = []
    for im in items:
        h = int(H * im.info.get("hscale", 0.62))
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


def _text(word, colour, px=200):
    f = font(px)
    w = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(word, font=f))
    im = Image.new("RGBA", (w + 8, int(px * 1.25)), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4, 0), word, font=f, fill=colour + (255,))
    return im.crop(im.getbbox())


def _mark(path, colour=None, hscale=0.62):
    im = mark(path, 400, colour) if Path(path).is_file() else Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    im.info["hscale"] = hscale
    return im


#: the Super Bowl ribbons' second band: the deep teal of the LXI mark's wave
SB_TEAL_DARK = (6, 58, 66)


def _sb(hscale):
    im = super_bowl_mark()
    im.info["hscale"] = hscale
    return im


def _shield(hscale):
    return _mark(U3 / "nfl_shield_master_2048.png", None, hscale)


def _rams_word(line, colour):
    return _mark(U1 / "LAR" / "marks" / f"wordmark2020_line{line}.png", colour, 0.5)


def _lac_word(part, colour):
    """The Chargers' 2020 wordmark (Commons, public domain): 'LOS ANGELES' (top line) or 'CHARGERS' (bottom line)."""
    im = Image.open(LAC_WORDMARK).convert("RGBA")
    a = np.asarray(im)
    rows = np.nonzero(a[..., 3].max(axis=1) > 40)[0]
    gaps = [r for r in range(rows[0], rows[-1]) if a[r, :, 3].max() <= 40]
    split = gaps[len(gaps) // 2] if gaps else a.shape[0] // 2
    im = im.crop((0, 0, im.width, split)) if part == "top" else im.crop((0, split, im.width, im.height))
    im = im.crop(im.getbbox())
    arr = np.asarray(im).copy()
    arr[..., :3] = colour
    out = Image.fromarray(arr)
    out.info["hscale"] = 0.5
    return out


def ribbon(venue, size=(256, 64)):
    """The LED ribbons (two bands a texture) in team colour on every level (Noah's reference, 2026-09-24: thin royal
    fascia bands on every level; the game-day photos show the same bands in team content): for the Rams royal, with
    white type and the club marks, and RAMS in sol; for the Chargers powder blue with the bolt, #BOLTUP and the gold
    LOS ANGELES; for the Super Bowl the LXI mark and the shield. Official wordmarks (Commons, public domain) and the
    club marks; plain type only for the small web and slogan lines."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    half = H // 2
    if venue == "s23":
        logo = U1 / "LAR" / "marks" / "club_logo_full.png"
        bands = [(RAMS["royal"], [_mark(logo, None, 0.7), _rams_word(1, (255, 255, 255)), _rams_word(2, (255, 255, 255)),
                                   _rams_word(3, RAMS["sol"]), _text("THERAMS.COM", (255, 255, 255))]),
                 (RAMS["royal"], [_rams_word(3, RAMS["sol"]), _mark(logo, None, 0.7), _text("HORNS UP", (255, 255, 255))])]
    elif venue == "s40":
        bands = [((10, 12, 16), [_sb(0.8), _shield(0.7), _sb(0.8), _shield(0.7)]),
                 (SB_TEAL_DARK, [_shield(0.7), _sb(0.8), _shield(0.7), _sb(0.8)])]
    else:
        bolt = U1 / "LAC" / "marks" / "lac_bolt_club.png"
        bands = [(CHARGERS["powder"], [_mark(bolt, None, 0.55), _lac_word("bottom", (255, 255, 255)),
                                       _text("#BOLTUP", (255, 255, 255)), _lac_word("top", CHARGERS["gold"])]),
                 (CHARGERS["powder"], [_lac_word("bottom", (255, 255, 255)), _mark(bolt, (255, 255, 255), 0.55),
                                       _text("BOLT UP", CHARGERS["navy"])])]
    for k, (bg, items) in enumerate(bands):
        y0 = k * half
        ImageDraw.Draw(im).rectangle([0, y0, W, y0 + half], fill=bg)
        band = _row(items, W, half, SCALE * 8)
        im.paste(band, (0, y0), band)
    return im


def glass(size=(128, 64)):
    """Suite and club glazing as the suite fronts read in c082 and c105: a white slab edge over uniform dark glass,
    a fine row of warm downlights under the ceiling, thin mullions every metre and only faint warm shapes of the
    rooms behind (the vertex light lifts it at night)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (24, 28, 36))
    d = ImageDraw.Draw(im)
    r = rng(3)
    for y in range(int(H * 0.26), int(H * 0.88)):                                    # the glass: a soft sky reflection
        t = (y - H * 0.26) / (H * 0.62)
        c = tuple(int(a + (b - a) * t) for a, b in zip((40, 46, 56), (22, 26, 33)))
        d.line([0, y, W, y], fill=c)
    for x in range(0, W, SCALE * 8):                                                  # the rooms behind, faint
        if r.random() < 0.55:
            w = int(SCALE * r.integers(2, 6))
            d.rectangle([x + SCALE, int(H * 0.62), x + SCALE + w, int(H * 0.84)], fill=(58, 50, 44))
    d.rectangle([0, 0, W, int(H * 0.14)], fill=(216, 216, 212))                       # the white slab edge
    d.rectangle([0, int(H * 0.14), W, int(H * 0.26)], fill=(30, 32, 38))              # the ceiling
    for x in range(SCALE * 2, W, SCALE * 8):                                          # the downlights
        d.rectangle([x, int(H * 0.19), x + SCALE * 3, int(H * 0.19) + SCALE * 2], fill=(255, 226, 176))
    for x in range(0, W, SCALE * 16):                                                 # the mullions
        d.rectangle([x, int(H * 0.26), x + SCALE - 1, int(H * 0.88)], fill=(66, 70, 78))
    d.rectangle([0, int(H * 0.88), W, H], fill=(16, 18, 22))                          # the sill
    return im


def concourse(size=(128, 64)):
    """The walls under the overhangs and the rim's back wall: the concourse behind, in shade (c082: no bare concrete
    shows between the tiers): the slab above, a row of warm ceiling lights, the dark hall with its columns and a few
    figures, a steel-topped glass rail and the floor edge (the vertex light lifts the lights at night)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (22, 24, 28))
    d = ImageDraw.Draw(im)
    r = rng(8)
    d.rectangle([0, 0, W, int(H * 0.10)], fill=(58, 60, 64))                          # the slab edge above
    for x in range(SCALE * 3, W, SCALE * 16):                                         # the ceiling lights
        d.rectangle([x, int(H * 0.13), x + SCALE * 6, int(H * 0.13) + SCALE * 2], fill=(255, 230, 184))
    for x in (int(W * 0.30), int(W * 0.80)):                                          # the columns
        d.rectangle([x, int(H * 0.10), x + SCALE * 3, int(H * 0.74)], fill=(46, 48, 52))
    for _ in range(14):                                                               # the figures in the hall
        x = int(r.integers(0, W - SCALE * 3))
        h = int(SCALE * r.integers(5, 8))
        tone = int(r.integers(34, 70))
        d.rectangle([x, int(H * 0.74) - h, x + SCALE * 2, int(H * 0.74)], fill=(tone, tone - 4, tone - 8))
    d.rectangle([0, int(H * 0.74), W, int(H * 0.76)], fill=(150, 152, 156))            # the rail's steel top
    d.rectangle([0, int(H * 0.76), W, int(H * 0.92)], fill=(44, 50, 58))              # the glass rail
    for x in range(0, W, SCALE * 12):
        d.rectangle([x, int(H * 0.76), x + SCALE - 1, int(H * 0.92)], fill=(96, 100, 106))
    d.rectangle([0, int(H * 0.92), W, H], fill=(104, 104, 102))                        # the floor edge
    return im


def facade(size=(128, 64)):
    """The bowl's outside under the canopy, seen past the columns: four open concourse levels (c103 at night, c109 and
    c111 by day), read mostly as lit white slab edges and people: a row of bright fixtures under each slab, fine
    steel X-bracing in each 8 m bay, a railing and the concourse's depth behind (16 m a repeat). By day the white
    structure reads against the shaded concourses; at night (the vertex light lifts LIGHT_ materials to full) the
    fixtures glow."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (40, 46, 54))                                                 # concourse depth
    d = ImageDraw.Draw(im)
    r = rng(5)
    level = H / 4
    bay = W // 2                                                                               # 8 m bays
    for k in range(4):
        y0 = int(k * level)
        y1 = int((k + 1) * level)
        slab = int(level * 0.10)
        for x in range(0, W, bay):                                                             # fine X-bracing
            d.line([x, y0 + slab, x + bay, y1], fill=(104, 110, 118), width=max(1, SCALE // 2))
            d.line([x + bay, y0 + slab, x, y1], fill=(104, 110, 118), width=max(1, SCALE // 2))
            d.rectangle([x, y0, x + SCALE, y1], fill=(170, 174, 180))                          # the bay's column
        for _p in range(18):                                                                   # people on the ramps
            px = int(r.integers(0, W - SCALE * 2))
            ph = int(level * float(r.uniform(0.16, 0.24)))
            tone = int(r.integers(40, 90))
            d.rectangle([px, y1 - ph - int(level * 0.06), px + SCALE, y1 - int(level * 0.06)], fill=(tone, tone - 6, tone - 10))
        d.rectangle([0, y1 - int(level * 0.30), W, y1 - int(level * 0.28)], fill=(176, 180, 186))  # the railing
        d.rectangle([0, y0, W, y0 + slab], fill=(228, 230, 232))                               # slab edge
        for x in range(SCALE * 4, W, SCALE * 8):                                               # fixtures under the slab
            d.rectangle([x, y0 + slab + SCALE, x + SCALE * 3, y0 + slab + SCALE * 2], fill=(255, 252, 238))
    return im


# --- the canopy -------------------------------------------------------------------------------------------------

def _net(im, colour, width, cell, angle_deg=0.0):
    d = ImageDraw.Draw(im)
    S = im.width
    for k in range(-2, S // cell + 3):
        o = k * cell
        d.line([o, 0, o + S * math.tan(math.radians(angle_deg)), S], fill=colour, width=width)
        d.line([0, o, S, o + S * math.tan(math.radians(-angle_deg))], fill=colour, width=width)


def etfe_under(night=False, size=128):
    """The roof from below (24 m a repeat), after the photos (c002, c105) and Noah's reference: the translucent ETFE
    in a soft grey, crossed by the white steel structure: the primary members on the diagonals every 12 m, bold, and
    the panel frames every 6 m, thinner; at night the dark roof shows the lit white members."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (38, 44, 54) if night else (178, 186, 196))
    d = ImageDraw.Draw(im)
    frame = (118, 124, 134) if night else (226, 230, 236)
    member = (168, 174, 184) if night else (250, 251, 253)
    for k in range(4):
        o = k * S // 4
        d.line([o, 0, o, S], fill=frame, width=SCALE * 2)
        d.line([0, o, S, o], fill=frame, width=SCALE * 2)
    for k in range(-2, 3):
        o = k * S // 2
        d.line([o, 0, o + S, S], fill=member, width=SCALE * 4)
        d.line([o, S, o + S, 0], fill=member, width=SCALE * 4)
    return im


def etfe_top(night=False, size=128):
    """The roof from above as the aerials show it (c107, c014, c016, c088): pale ETFE cushions in long panels (two
    across and four along a 24 m repeat) with thin dark joints, each panel a slightly different grey, and the raised
    operable louvres (lighter, with a shadow edge and their slats); lit from inside at night."""
    S = size * SCALE
    base = (64, 72, 86) if night else (201, 204, 207)
    joint = (34, 38, 46) if night else (124, 130, 138)
    im = Image.new("RGB", (S, S), base)
    d = ImageDraw.Draw(im)
    r = rng(12)
    cols, rows = 2, 4
    pw, ph = S // cols, S // rows
    louvres = {(0, 1), (1, 3)}
    for i in range(cols):
        for j in range(rows):
            x0, y0 = i * pw, j * ph
            tone = int(r.integers(-7, 5))
            fill = tuple(max(0, min(255, c + tone)) for c in base)
            if (i, j) in louvres:
                fill = tuple(min(255, c + (10 if night else 12)) for c in base)
            d.rectangle([x0, y0, x0 + pw, y0 + ph], fill=fill)
            if (i, j) in louvres:
                for k in range(y0 + SCALE * 3, y0 + ph - SCALE * 2, SCALE * 3):          # the slats
                    d.line([x0 + SCALE * 2, k, x0 + pw - SCALE * 2, k], fill=tuple(c - 18 for c in fill), width=SCALE // 2)
                d.rectangle([x0, y0 + ph - SCALE * 2, x0 + pw, y0 + ph], fill=tuple(c - 40 for c in fill))  # shadow
    for i in range(cols + 1):                  # the joints two texels wide: the aerial shot sees the roof from 400 m
        d.rectangle([i * pw - SCALE, 0, i * pw + SCALE, S], fill=joint)
    for j in range(rows + 1):
        d.rectangle([0, j * ph - SCALE, S, j * ph + SCALE], fill=joint)
    return im


def aluminium(size=128):
    """The canopy's anodised aluminium panels: uniquely shaped triangles with perforation speckle (HKS shell
    diagram)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (226, 227, 226))
    d = ImageDraw.Draw(im)
    r = rng(6)
    n = 6
    step = S / n
    for i in range(n + 1):
        for j in range(n + 1):
            x, y = i * step + r.uniform(-step * 0.15, step * 0.15), j * step + r.uniform(-step * 0.15, step * 0.15)
            d.line([x, y, x + step, y], fill=(200, 202, 202), width=SCALE)
            d.line([x, y, x, y + step], fill=(200, 202, 202), width=SCALE)
            d.line([x, y, x + step, y + step], fill=(206, 208, 208), width=SCALE)
    return im


def white(size=64):
    S = size * SCALE
    return Image.new("RGB", (S, S), (240, 240, 238))


def lights(size=(64, 32)):
    """A light bank: a frame of LED modules, all lit (the sports lights under the canopy's rim, on during games)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (150, 152, 158))
    d = ImageDraw.Draw(im)
    for x in range(0, W, SCALE * 8):
        for y in range(0, H, SCALE * 8):
            d.rectangle([x + SCALE // 2, y + SCALE // 2, x + SCALE * 8 - SCALE // 2, y + SCALE * 8 - SCALE // 2],
                        fill=(255, 254, 248))
    return im


def dark(size=32):
    S = size * SCALE
    return Image.new("RGB", (S, S), (17, 18, 20))


# --- the Infinity Screen ------------------------------------------------------------------------------------------

#: the players on the Infinity Screen's team panels (main, 2026-09-24, after Noah's reference: royal team panels with
#: player images, names and numbers). Official 2026 portraits: nflverse-data roster_2026.csv (CC-BY-4.0) headshot_url,
#: the NFL.com images u1's league project fits its faces from; recorded with their SHA-256 in HEADSHOTS / headshots.json.
HEADSHOTS = Path("/media/noah/Storage/.b76-research/u6/refs/headshots")
SCREEN_PLAYERS = {
    "s23": (("00-0026498", "STAFFORD", "9"), ("00-0039075", "NACUA", "12"), ("00-0037840", "WILLIAMS", "23")),
    "s24": (("00-0036355", "HERBERT", "10"), ("00-0039915", "MCCONKEY", "15"), ("00-0031040", "MACK", "52")),
}
SCREEN_SIZE = {"s23": (512, 64), "s24": (512, 64), "s40": (256, 64)}


def _portrait(gsis, height):
    """An official portrait cut out (its own alpha), cropped to head and shoulders, scaled to ``height`` px."""
    im = Image.open(HEADSHOTS / f"{gsis}.png").convert("RGBA")
    x0, y0, x1, y1 = im.getbbox()
    w = x1 - x0
    top = y0 + int((y1 - y0) * 0.02)
    bottom = min(y1, top + int(w * 0.62))
    im = im.crop((x0 + int(w * 0.08), top, x1 - int(w * 0.08), bottom))
    return im.resize((max(1, int(im.width * height / im.height)), height), Image.LANCZOS)


def screen_panels(venue, portraits=True):
    """The Infinity Screen between its live windows, as on game days and in Noah's reference: bright team panels. For
    the Rams, royal with each featured player's official 2026 portrait, his number in sol and his name in white,
    between the club marks; for the Chargers, powder blue with the numbers in gold; for the Super Bowl, the LXI mark and
    the NFL shield on the deep teal of the LXI wave. Faint seams stand for the LED cabinets."""
    W, H = SCREEN_SIZE[venue][0] * SCALE, SCREEN_SIZE[venue][1] * SCALE
    if venue == "s40":
        im = Image.new("RGB", (W, H), SB_TEAL_DARK)
        band = _row([_sb(0.86), _shield(0.62)], W, H, SCALE * 16)
        im.paste(band, (0, 0), band)
        return im
    bg, number, name, mark = ((RAMS["royal"], RAMS["sol"], RAMS["white"], U1 / "LAR" / "marks" / "club_logo_full.png")
                              if venue == "s23" else
                              (CHARGERS["powder"], CHARGERS["gold"], CHARGERS["white"], U1 / "LAC" / "marks" / "lac_bolt_club.png"))
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    # a lighter diagonal sweep behind each player, the broadcast graphics' look
    light = tuple(min(255, int(c * 1.22 + 18)) for c in bg)
    block = W // 3
    for k in range(3):
        x = k * block
        d.polygon([(x + block * 0.08, H), (x + block * 0.30, 0), (x + block * 0.52, 0), (x + block * 0.30, H)], fill=light)
    for x in range(0, W, W // 16):                        # the LED cabinet seams, behind the content
        d.line([(x, 0), (x, H)], fill=tuple(int(c * 0.86) for c in bg), width=max(1, SCALE // 2))
    for k, (gsis, surname, num) in enumerate(SCREEN_PLAYERS[venue]):
        x = k * block
        if portraits:
            face = _portrait(gsis, H)
            im.paste(face, (x + int(block * 0.04), H - face.height), face)
        else:
            # the committed panel (main, 2026-09-24: official portraits stay private): the club mark in the portrait's
            # place
            big = _mark(mark, None, 0.5)
            f = min(H * 0.78 / big.height, block * 0.40 / big.width)
            big = big.resize((max(1, int(big.width * f)), max(1, int(big.height * f))), Image.LANCZOS)
            im.paste(big, (x + int(block * 0.06) + (int(block * 0.40) - big.width) // 2, (H - big.height) // 2), big)
        numeral = _text(num, number, px=int(H * 0.62))
        im.paste(numeral, (x + int(block * 0.50), int(H * 0.08)), numeral)
        label = _text(surname, name, px=int(H * 0.22))
        if label.width > block * 0.46:
            label = label.resize((int(block * 0.46), label.height), Image.LANCZOS)
        im.paste(label, (x + int(block * 0.50), int(H * 0.70)), label)
        if portraits:
            club = _mark(mark, None, 0.5)
            f = min(H * 0.3 / club.height, block * 0.16 / club.width)   # the mark in the top corner, clear of the number
            club = club.resize((max(1, int(club.width * f)), max(1, int(club.height * f))), Image.LANCZOS)
            im.paste(club, (x + block - club.width - int(block * 0.04), int(H * 0.06)), club)
    return im


#: the private portrait panels (main, 2026-09-24): official player portraits stay out of the repo and the release, like
#: the league project's; the build reads them from this gitignored hydration folder when present
PRIVATE_OUT = Path(__file__).resolve().parents[1] / "mod_editor" / "assets" / "nfl2k5_sofi_model"


def write_private_panels(out_dir, masters=None):
    """The portrait panels (natives, their 4x masters and a manifest with each portrait's provenance) into the private
    folder."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = dict(schema="nfl2k5_sofi_model_private/v1", note="official 2026 player portraits: private, never released",
               portraits=json.loads((HEADSHOTS / "headshots.json").read_text()), panels={})
    for venue in ("s23", "s24"):
        master = screen_panels(venue, portraits=True)
        native = reduce(master, SCREEN_SIZE[venue])
        path = out_dir / f"LIGHT_sf_screen_{venue}.png"
        native.save(path, optimize=True)
        (out_dir / "master4x").mkdir(exist_ok=True)
        master.save(out_dir / "master4x" / f"LIGHT_sf_screen_{venue}.png", optimize=True)
        doc["panels"][venue] = dict(file=path.name, size=list(SCREEN_SIZE[venue]),
                                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (out_dir / "private.json").write_text(json.dumps(doc, indent=1) + "\n")
    return doc


def sofi_logo(white_all=True, size=(512, 64)):
    """The SoFi Stadium logo (Commons, public domain) on transparency: white for the building letters and the roof
    wordmarks; teal SoFi and white Stadium for the screen band (the CFP press-box photo)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    logo = Image.open(LOGO).convert("RGBA")
    logo = logo.crop(logo.getbbox())
    h = int(H * 0.8)
    w = int(logo.width * h / logo.height)
    if w > W * 0.96:
        w = int(W * 0.96)
        h = int(logo.height * w / logo.width)
    logo = logo.resize((w, h), Image.LANCZOS)
    a = np.asarray(logo).copy()
    if white_all:
        a[..., :3] = 255
    else:
        cols = (a[..., 3] > 40).any(axis=0)
        # the widest gap after the first third splits "SoFi + mark" from "Stadium"
        runs, start = [], None
        for x, on in enumerate(cols):
            if not on and start is None:
                start = x
            if on and start is not None:
                runs.append((x - start, start, x))
                start = None
        split = max((r for r in runs if r[1] > w * 0.25), default=(0, w // 2, w // 2))[2]
        a[:, :split, :3] = (2, 169, 206)
        a[:, split:, :3] = 255
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(Image.fromarray(a), ((W - w) // 2, (H - h) // 2), Image.fromarray(a))
    return out


def letters_back(size=(512, 64)):
    """The dark backs of the channel letters: the same silhouette, dark."""
    im = sofi_logo(True, size)
    a = np.asarray(im).copy()
    a[..., :3] = 34
    return Image.fromarray(a)


# --- outside ----------------------------------------------------------------------------------------------------

def plaza(size=128):
    S = size * SCALE
    im = Image.new("RGB", (S, S), (206, 200, 190))
    d = ImageDraw.Draw(im)
    for k in range(0, S, SCALE * 16):
        d.line([k, 0, k, S], fill=(180, 174, 164), width=SCALE)
        d.line([0, k, S, k], fill=(180, 174, 164), width=SCALE)
    return im


def ground(size=128):
    """Hollywood Park's parking lots from the air (the aerials c014, c016, c088, c107): asphalt, white stall lines in
    double rows, cars (1.25 m a pixel at 160 m a repeat), a few trees along the aisles."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (98, 100, 102))
    d = ImageDraw.Draw(im)
    r = rng(9)
    px = S / 160.0                                   # pixels per metre
    y = 4 * px
    cars = [(40, 42, 46), (210, 212, 214), (150, 152, 156), (30, 32, 36), (120, 30, 30), (60, 70, 100), (200, 200, 196)]
    while y < S - 12 * px:
        for row in (0, 1):
            y0 = y + row * 5.5 * px
            for x in np.arange(2 * px, S - 3 * px, 2.7 * px):
                d.line([x, y0, x, y0 + 5.0 * px], fill=(196, 196, 190), width=max(1, SCALE // 2))
                if r.random() < 0.72:
                    c = cars[int(r.integers(0, len(cars)))]
                    d.rectangle([x + 0.35 * px, y0 + 0.4 * px, x + 2.3 * px, y0 + 4.6 * px], fill=c)
        y += 18.0 * px
    for _k in range(10):
        x, yy = r.integers(0, S), r.integers(0, S)
        d.ellipse([x, yy, x + 4 * px, yy + 4 * px], fill=(72, 94, 58))
    return im


def water(size=64):
    S = size * SCALE
    im = Image.new("RGB", (S, S), (46, 84, 96))
    d = ImageDraw.Draw(im)
    for y in range(0, S, SCALE * 6):
        d.line([0, y, S, y + SCALE * 2], fill=(58, 98, 110), width=SCALE)
    return im


def sky(kind, size=(128, 64)):
    """Sky over Inglewood with the basin's low skyline at the horizon (v = 1 at the bottom of the backdrop). At night
    the Los Angeles sky is an overcast lit from below by the city (c103): dark grey-blue overhead, a warm glow toward
    the horizon, soft cloud banks."""
    W, H = size[0] * SCALE, size[1] * SCALE
    tops = dict(d=((96, 150, 214), (196, 220, 240)), a=((110, 140, 200), (246, 206, 160)),
                n=((22, 26, 38), (86, 78, 80)), o=((150, 158, 168), (196, 200, 204)))[kind]
    y = np.linspace(0, 1, H)[:, None, None]
    img = (np.array(tops[0], np.float32) * (1 - y) + np.array(tops[1], np.float32) * y) * np.ones((1, W, 1))
    if kind == "n":
        r0 = rng(21)
        cloud = r0.random((H // 16 + 1, W // 16 + 1)).astype(np.float32)
        cloud = np.asarray(Image.fromarray((cloud * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 255
        cloud = _blur(cloud, SCALE * 3)
        lift = np.clip((cloud - 0.45) * 2.2, 0, 1)[..., None] * (0.35 + 0.65 * y) * np.array((26, 24, 26), np.float32)
        img = img + lift
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    r = rng(11)
    hy = int(H * 0.955)
    city = (40, 46, 58) if kind != "n" else (22, 22, 28)
    x = 0
    while x < W:
        w_ = int(r.integers(SCALE * 2, SCALE * 8))
        h_ = int(r.integers(SCALE * 1, SCALE * (6 if 0.35 < x / W < 0.45 else 3)))
        d.rectangle([x, hy - h_, x + w_, H], fill=city)
        if kind == "n":
            for _k in range(3):
                d.point((x + int(r.integers(0, max(1, w_))), hy - int(r.integers(0, max(1, h_)))), fill=(255, 214, 150))
        x += w_
    return im


def portal(size=32):
    S = size * SCALE
    return Image.new("RGB", (S, S), (14, 14, 16))


# --- driver -----------------------------------------------------------------------------------------------------

def drawings():
    out = {
        "sf_seat": (seat(), (128, 128)), "sf_concrete": (concrete(), (64, 64)),
        "LIGHT_sf_glass": (glass(), (128, 64)), "LIGHT_sf_facade": (facade(), (128, 64)),
        "LIGHT_sf_concourse": (concourse(), (128, 64)),
        "sf_etfe_under_d": (etfe_under(False), (128, 128)), "sf_etfe_under_n": (etfe_under(True), (128, 128)),
        "sf_etfe_top_d": (etfe_top(False), (128, 128)), "sf_etfe_top_n": (etfe_top(True), (128, 128)),
        "sf_alu": (aluminium(), (128, 128)), "sf_white": (white(), (64, 64)),
        "LIGHT_sf_lights": (lights(), (64, 32)), "sf_dark": (dark(), (32, 32)),
        "sf_letters": (sofi_logo(True), (512, 64)), "sf_letters_screen": (sofi_logo(False), (256, 32)),
        "sf_plaza": (plaza(), (128, 128)), "sf_ground": (ground(), (128, 128)), "sf_water": (water(), (64, 64)),
        "sf_sky_d": (sky("d"), (128, 64)), "sf_sky_a": (sky("a"), (128, 64)), "sf_sky_n": (sky("n"), (128, 64)),
        "sf_sky_o": (sky("o"), (128, 64)), "sf_portal": (portal(), (32, 32)),
    }
    for venue in ("s23", "s24", "s40"):
        out[f"LIGHT_sf_ribbon_{venue}"] = (ribbon(venue), (256, 64))
        out[f"LIGHT_sf_screen_{venue}"] = (screen_panels(venue, portraits=False), SCREEN_SIZE[venue])
    return out


def main(argv=None):
    global U1, LOGO, LAC_WORDMARK, U7, U3, LAC_REFS, RAMS_ALT, SB_SOURCE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--masters")
    ap.add_argument("--marks-root", default=str(U1), help="the 2026 team folders (<root>/LAR/marks, <root>/LAC/marks)")
    ap.add_argument("--sofi-logo", default=str(LOGO))
    ap.add_argument("--chargers-wordmark", default=str(LAC_WORDMARK))
    ap.add_argument("--rams-marks", default=str(U7), help="u7's Rams masters (the LA monogram and the 2020 wordmarks)")
    ap.add_argument("--league-marks", default=str(U3), help="u3's league marks (the current NFL shield)")
    ap.add_argument("--chargers-refs", default=str(LAC_REFS), help="d4's LAC refs (the NFL.com club bolt render)")
    ap.add_argument("--rams-ram-head", default=str(RAMS_ALT), help="the Rams' 2020 alternate (ram head) image")
    ap.add_argument("--super-bowl-source", default=str(SB_SOURCE),
                    help="the NFL's Super Bowl LXI reveal image (checked against its SHA-256)")
    ap.add_argument("--private-out", default=str(PRIVATE_OUT),
                    help="where the private portrait panels go (a gitignored hydration folder); '' to skip")
    a = ap.parse_args(argv)
    U1, LOGO, LAC_WORDMARK = Path(a.marks_root), Path(a.sofi_logo), Path(a.chargers_wordmark)
    U7, U3, LAC_REFS, RAMS_ALT = Path(a.rams_marks), Path(a.league_marks), Path(a.chargers_refs), Path(a.rams_ram_head)
    SB_SOURCE = Path(a.super_bowl_source)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    masters = Path(a.masters) if a.masters else None
    if masters:
        masters.mkdir(parents=True, exist_ok=True)
    manifest = {}
    field_dir = out / "field"
    field_dir.mkdir(exist_ok=True)
    for name, (master, size) in field_drawings().items():
        native = reduce(master, size)
        path = field_dir / f"{name}.png"
        native.save(path, optimize=True)
        manifest["field/" + name] = dict(size=list(size), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if name.endswith("_midfield"):
            manifest["field/" + name]["quad_m"] = [round(v, 4) for v in midfield_quad(name[:3])]
        if name == "s40_shield":
            manifest["field/" + name]["quad_m"] = [round(v, 4) for v in shield_quad()]
        if masters:
            (masters / "field").mkdir(exist_ok=True)
            master.save(masters / "field" / f"{name}.png", optimize=True)
    for name, (master, size) in drawings().items():
        native = reduce(master, size)
        path = out / f"{name}.png"
        native.save(path, optimize=True)
        manifest[name] = dict(size=list(size), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if masters:
            master.save(masters / f"{name}.png", optimize=True)
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_sofi_model_art/v1", art=manifest), indent=1) + "\n")
    if a.private_out:
        write_private_panels(a.private_out)
    print("SOFI_ART_OK", len(manifest))
    return 0



# --- the field (job u6; main, 2026-09-24: u6 authors both SoFi end zones and midfields) -------------------------
#
# The retail field maps one set of three end-zone panel textures (256 x 128, L M R) to both ends. SoFi paints the two
# ends differently, so each panel texture carries the south end in its top half and the north end in its bottom half,
# and the model splits the panels' V (0 to 0.5 south, 0.5 to 1 north; both halves start at the end line). A half is
# 768 x 64 native over 53.33 x 10 yards, so every mark is drawn with separate across and deep scales at its true
# proportions (no stretching). Read from the field of play: south (the retail endzone_N panels, at -z) is the team
# end, north is LOS ANGELES (the Rams v Colts 2025 photo, Commons c082, CC0, taken from behind the south end zone with
# the Rams' east bench on the right; the Chargers v Vikings 2021 photo c105 with the visitors on the east; the
# Chargers bench is west, the Rams' east). The midfield mark reads from the west sideline, as the retail texture does
# (c082: the LA monogram's top points east).
U7 = Path("/media/noah/Storage/.b76-research/u7/masters")
#: Super Bowl LXI (main's option 1, 2026-09-24): the NFL's own reveal image, as @NFL posted it on X on 2026-02-09
#: (https://x.com/NFL/status/2020916447971623233) and SportsLogos.net republished it credited to @NFL
#: (https://content.sportslogos.net/news/2026/02/IMG_9139-1000x562.jpeg, SHA-256 6cec89ad...af54). The mark is used
#: exactly as sourced: cropped to the primary mark (the host "Los Angeles" script below it is left out) and its black
#: background keyed by a flood fill from the border; never redrawn, traced or generated. It stays out of the 4x pack.
SB_SOURCE = Path("/media/noah/Storage/.b76-research/u6/refs/sb61/sportslogos_nfl_x_sblxi.jpeg")
SB_SOURCE_SHA256 = "6cec89ad1a7760008a8d6d2868a4493f0d62dedf5e395f0cb3fc220b6af2af54"
U3 = Path("/media/noah/Storage/.b76-research/u3/league_marks")
LAC_REFS = Path("/media/noah/Storage/.b76-research/u1/teams/LAC/refs")
RAMS_ALT = Path("/media/noah/Storage/.b76-research/u6/refs/logos/rams_alternate_2020_sportslogos.png")
HALF_W, HALF_H = 768, 64                          # native pixels of one end in the split panel textures
XS, ZS = HALF_W / 53.333, HALF_H / 10.0           # native pixels per yard across and deep (14.4 and 6.4)


def _recolour(im, colour):
    a = np.asarray(im.convert("RGBA")).copy()
    a[..., :3] = colour
    return Image.fromarray(a)


def _true(im, width_yd=None, height_yd=None, *, xs, zs):
    """A mark resized to its true proportions on a grid of ``xs`` x ``zs`` pixels per yard (across x deep)."""
    im = im.crop(im.getbbox())
    aspect = im.width / im.height
    if width_yd is None:
        width_yd = height_yd * aspect
    height_yd = width_yd / aspect
    return im.resize((max(1, int(round(width_yd * xs))), max(1, int(round(height_yd * zs)))), Image.LANCZOS)


def _place(canvas, im, cx, cy):
    canvas.alpha_composite(im, (int(round(cx - im.width / 2)), int(round(cy - im.height / 2))))


def rams_ram_head():
    """The Rams' ram head (the 2020 alternate logo; sportslogos.net's copy of the official mark) as the end zones
    paint it: horn flattened to sol (the 2025 and 2026 photos; the 2026 marks are gradient-free), the white outside
    the royal outline made transparent (flood from the corners)."""
    a = np.asarray(Image.open(RAMS_ALT).convert("RGBA")).astype(np.int32).copy()
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    warm = (r > 180) & (g > 90) & (b < 90)
    grey = (abs(r - g) < 12) & (abs(g - b) < 16) & (r > 170) & (r < 235)
    a[warm, :3] = RAMS["sol"]
    a[grey, :3] = (255, 255, 255)
    light = (a[..., :3].min(axis=2) > 225)
    outside = np.zeros(light.shape, bool)
    h, w = light.shape
    stack = [(0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)]
    while stack:
        y, x = stack.pop()
        if 0 <= y < h and 0 <= x < w and light[y, x] and not outside[y, x]:
            outside[y, x] = True
            stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
    a[outside, 3] = 0
    return Image.fromarray(a.astype(np.uint8))


def _lac_bolt():
    """The small bolt of the 2020 wordmark (the descender under CHARGERS' A), public domain."""
    im = Image.open(LAC_WORDMARK).convert("RGBA")
    a = np.asarray(im)
    rows = np.nonzero(a[..., 3].max(axis=1) > 40)[0]
    gaps = [r for r in range(rows[0], rows[-1]) if a[r, :, 3].max() <= 40]
    split = gaps[len(gaps) // 2]
    bottom = a[split:]
    counts = (bottom[..., 3] > 40).sum(axis=1)
    base = int(np.nonzero(counts > counts.max() * 0.5)[0].max())
    bolt = Image.fromarray(np.ascontiguousarray(bottom[base + 2:]))
    return bolt.crop(bolt.getbbox())


def end_zone(venue, end):
    """One end at 4x (3072 x 256), reading upright from the field (top = the end line)."""
    xs, zs = XS * SCALE, ZS * SCALE
    W, H = HALF_W * SCALE, HALF_H * SCALE
    if venue == "s23":
        im = Image.new("RGBA", (W, H), RAMS["royal"] + (255,))
        if end == "south":
            # c082 (2025) and the 2026 Week 2 frames: RAMS in solid sol (no outline), the ram head at the east corner,
            # the NFL shield at the west
            word = _true(_recolour(Image.open(U7 / "rams_wordmark_2020_mask.png"), RAMS["sol"]), 28.5, xs=xs, zs=zs)
            _place(im, word, W / 2, H / 2)
            head = _true(rams_ram_head(), height_yd=6.6, xs=xs, zs=zs)
            _place(im, head, 7.0 * xs, H / 2)
            shield = _true(Image.open(U3 / "nfl_shield_master_2048.png").convert("RGBA"), height_yd=6.0, xs=xs, zs=zs)
            _place(im, shield, W - 7.0 * xs, H / 2)
        else:
            # c082: LOS ANGELES in sol on one line across the north end
            word = _true(_recolour(Image.open(U7 / "los_angeles_wordmark_2020_mask.png"), RAMS["sol"]), 44.0, xs=xs, zs=zs)
            _place(im, word, W / 2, H / 2)
    else:
        # c018 and c105 (2021, 2023): the 2020 wordmarks in white on powder; one small gold bolt at the west corner
        im = Image.new("RGBA", (W, H), CHARGERS["powder"] + (255,))
        bolt = _true(_recolour(_lac_bolt(), CHARGERS["gold"]), height_yd=1.6, xs=xs, zs=zs)
        if end == "south":
            word = _true(_lac_word("bottom", (255, 255, 255)), 38.0, xs=xs, zs=zs)
            _place(im, bolt, W - 3.4 * xs, H - 1.8 * zs)          # west is on the right, facing south
        else:
            word = _true(_lac_word("top", (255, 255, 255)), 40.0, xs=xs, zs=zs)
            _place(im, bolt, 3.4 * xs, H - 1.8 * zs)              # west is on the left, facing north
        _place(im, word, W / 2, H / 2)
    return im


def end_zone_panels(venue):
    """{panel: 4x master (1024 x 512)} for L, M and R: the south end on top, the north end below."""
    south, north = end_zone(venue, "south"), end_zone(venue, "north")
    out = {}
    for k, part in enumerate("LMR"):
        box = (k * 256 * SCALE, 0, (k + 1) * 256 * SCALE, HALF_H * SCALE)
        panel = Image.new("RGB", (256 * SCALE, 128 * SCALE))
        panel.paste(south.crop(box).convert("RGB"), (0, 0))
        panel.paste(north.crop(box).convert("RGB"), (0, HALF_H * SCALE))
        out[part] = panel
    return out


#: the midfield marks: the source, and the size of the mark on the field (metres, across x and along z), measured on
#: the photos (c082: the LA monogram 8.9 m across the field; c018 and the 2026 top shot: the club bolt about 14 yd
#: along the field); the other side follows the mark's own aspect
MIDFIELD = {"s23": dict(across=8.9), "s24": dict(along=12.8), "s40": dict(across=9.9)}
#: the Super Bowl field: the LXI mark at midfield and the current NFL shield on both 25-yard lines, as recent Super
#: Bowl fields have them (the retail s40 field had the reverse: the old shield at midfield, the XXXIX logo on the 25s)
SHIELD_25 = dict(across=6.6)
MARGIN = 4                                           # native pixels of transparency around the mark


def super_bowl_mark():
    """The Super Bowl LXI primary mark from the NFL's reveal raster (SB_SOURCE), RGBA at the source's resolution."""
    data = SB_SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest() != SB_SOURCE_SHA256:
        raise SystemExit(f"{SB_SOURCE}: not the NFL reveal image this art was made from")
    rgb = np.asarray(Image.open(SB_SOURCE).convert("RGB")).astype(np.int32)
    lit = rgb.max(axis=2)
    rows = np.nonzero((lit > 40).any(axis=1))[0]
    top = rows[0]
    gap = next(r for r in range(top, rows[-1]) if not (lit[r] > 40).any())     # the empty rows above the script
    band = lit[top:gap]
    cols = np.nonzero((band > 40).any(axis=0))[0]
    pad = 3
    y0, y1, x0, x1 = max(0, top - pad), gap, max(0, cols[0] - pad), min(rgb.shape[1], cols[-1] + 1 + pad)
    rgb, lit = rgb[y0:y1, x0:x1], lit[y0:y1, x0:x1]
    # the background: the black around the mark and the black counters inside the L and the X (the mark's holes, which
    # the NFL's image fills with its black background): every dark region that touches the border or is large; the
    # mark's own dark lines are thin and stay
    from scipy import ndimage
    dark = lit <= 34
    labels, count = ndimage.label(dark)
    sizes = ndimage.sum(dark, labels, range(1, count + 1))
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
    keep = [k for k in range(1, count + 1) if k in border or sizes[k - 1] >= 300]
    bg = np.isin(labels, keep)
    alpha = np.where(bg, 0.0, 1.0)
    # the one-pixel rim next to the background: the JPEG blends the edge into black, so its alpha follows its light
    edge = ~bg & (np.roll(bg, 1, 0) | np.roll(bg, -1, 0) | np.roll(bg, 1, 1) | np.roll(bg, -1, 1))
    alpha = np.where(edge, np.clip(lit / 90.0, 0.0, 1.0), alpha)
    colour = np.where(edge[..., None], np.clip(rgb / np.maximum(alpha[..., None], 0.35), 0, 255), rgb)
    out = np.dstack([colour, alpha * 255.0]).astype(np.uint8)
    im = Image.fromarray(out, "RGBA")
    return im.crop(im.getbbox())


def midfield_mark(venue):
    if venue == "s40":
        return super_bowl_mark()
    if venue == "s23":
        return Image.open(U7 / "la_monogram_fullcolour_2048.png").convert("RGBA")
    return Image.open(LAC_REFS / "nfl_club_logo_LAC_2048.png").convert("RGBA")


def midfield_quad(venue):
    """(across m, along m) of the midfield quad: the mark at its true size, plus the texture's transparent margin."""
    m = midfield_mark(venue)
    m = m.crop(m.getbbox())
    aspect = m.width / m.height                       # image width runs along the field (read from the west)
    q = MIDFIELD[venue]
    along = q.get("along") or q["across"] * aspect
    across = q.get("across") or along / aspect
    f = 256 / (256 - 2 * MARGIN)
    return across * f, along * f


def midfield(venue):
    """The mark at 4x (1024 x 1024), upright, filling the texture inside the margin; the quad restores its aspect."""
    S = 256 * SCALE
    m = midfield_mark(venue)
    m = m.crop(m.getbbox()).resize((S - 2 * MARGIN * SCALE, S - 2 * MARGIN * SCALE), Image.LANCZOS)
    box = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    box.alpha_composite(m, (MARGIN * SCALE, MARGIN * SCALE))
    return box


def shield_quad():
    """(across m, along m) of the 25-yard-line shields at their true proportions, plus the texture's margin."""
    m = Image.open(U3 / "nfl_shield_master_2048.png").convert("RGBA")
    m = m.crop(m.getbbox())
    across = SHIELD_25["across"]
    along = across * m.width / m.height
    f = 256 / (256 - 2 * MARGIN)
    return across * f, along * f


def shield():
    """The current NFL shield (u3's master of the league's file) filling the texture inside the margin."""
    S = 256 * SCALE
    m = Image.open(U3 / "nfl_shield_master_2048.png").convert("RGBA")
    m = m.crop(m.getbbox()).resize((S - 2 * MARGIN * SCALE, S - 2 * MARGIN * SCALE), Image.LANCZOS)
    box = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    box.alpha_composite(m, (MARGIN * SCALE, MARGIN * SCALE))
    return box


def field_drawings():
    out = {}
    for venue in ("s23", "s24"):
        for part, master in end_zone_panels(venue).items():
            out[f"{venue}_endzone_{part}"] = (master, (256, 128))
        out[f"{venue}_midfield"] = (midfield(venue), (256, 256))
    out["s40_midfield"] = (midfield("s40"), (256, 256))
    out["s40_shield"] = (shield(), (256, 256))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
