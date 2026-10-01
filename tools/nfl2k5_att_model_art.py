#!/usr/bin/env python3
"""Draw the AT&T Stadium model's art (job st2, 2026-09-25): deterministic, procedural, plain type only.

  python3 tools/nfl2k5_att_model_art.py OUT_DIR [--masters MASTER_DIR]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model, and no logo is drawn: the stars are plain five-point stars and every name is plain type
(Roboto Condensed Bold, Apache 2.0). Tones are measured from the reference photos (Commons: "AT&T Stadium Inside (Dec
2025)", "AT&T Stadium 2022-08-24", "AT&T Stadium roof closed 2022-08-24", "ATT Stadium Roof Open", "Cowboys Stadium April
10 2010", "Cowboys stadium outside view"; the Cowboys' 2026 week 2 and preseason galleries): the navy and charcoal
seats, the navy field wall with its white stars, the translucent roof on its steel trusses, the black board, the blue
glass curtain wall and the white dome.
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
COWBOYS = dict(navy=(0, 34, 68), royal=(0, 53, 148), silver=(134, 147, 151), white=(255, 255, 255))


def star(size, colour, border=None):
    """A plain five-point star (not a mark): points at radius 1, notches at 0.382."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = []
    for k in range(10):
        r = (size / 2 - 1) * (1.0 if k % 2 == 0 else 0.382)
        a = -math.pi / 2 + k * math.pi / 5
        pts.append((size / 2 + r * math.cos(a), size / 2 + r * math.sin(a)))
    d.polygon(pts, fill=colour + (255,))
    return im


def seat(p_char, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0. The seats are navy
    with charcoal scattered through them, more charcoal toward the back of each tier (the Dec 2025 and 2022 interiors)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (40, 42, 48))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(150, 150, 148))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(46, 48, 52))
        for c in range(cols):
            x = c * pitch
            basec = (54, 58, 66) if r.random() < p_char else (24, 40, 76)
            tone = int(r.integers(-6, 7))
            fill = tuple(int(np.clip(v + tone, 0, 255)) for v in basec)
            d.rectangle([x + SCALE, y0 + int(rh * 0.30), x + pitch - SCALE, y0 + int(rh * 0.94)], fill=fill)
    aisle = int(round(W * 0.16 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(160, 160, 158))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(112, 112, 110), width=SCALE)
    return im


def deck(size=(64, 128)):
    """The Party Pass decks' floors: grey concrete with the railing line at each step's front."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (132, 132, 130))
    d = ImageDraw.Draw(im)
    rh = H / 21
    for k in range(21):
        y = int(k * rh)
        d.rectangle([0, y, W, y + SCALE], fill=(60, 62, 66))
    return im


def wall(size=(256, 32)):
    """The field wall: Cowboys navy padding with plain white stars and a thin white line along its top (the 2026 game-day
    and pregame photos)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), COWBOYS["navy"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.06)], fill=COWBOYS["white"])
    s = int(H * 0.62)
    for x in range(int(W * 0.06), W, int(W / 6)):
        im.paste(star(s, COWBOYS["white"]), (x, int(H * 0.22)), star(s, COWBOYS["white"]))
    return im


def ribbon(size=(256, 64)):
    """The LED ribbons, two bands a texture, lively as the Dec 2025 photo's (plain type, no logos): a band of navy, royal,
    white and red segments with DALLAS COWBOYS, stars and the partners' names as type; a band of black and silver with
    AT&T STADIUM and HOW BOUT THEM COWBOYS."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    h = H // 2
    segs = [(COWBOYS["navy"], [star(200, COWBOYS["white"]), _text("DALLAS COWBOYS", COWBOYS["white"])]),
            ((230, 32, 44), [_text("PEPSI", COWBOYS["white"])]),
            (COWBOYS["royal"], [_text("COWBOYS", COWBOYS["white"]), star(200, COWBOYS["white"])]),
            ((245, 246, 248), [_text("AT&T", (0, 90, 200))]),
            ((180, 20, 120), [_text("GAME DAY", COWBOYS["white"])])]
    x = 0
    widths = [0.30, 0.14, 0.24, 0.14, 0.18]
    for (bg, items), w in zip(segs, widths):
        sw = int(W * w)
        seg = Image.new("RGB", (sw, h), bg)
        band = _row(items, sw, h, SCALE * 6, 0.56)
        seg.paste(band, (0, 0), band)
        im.paste(seg, (x, 0))
        x += sw
    bot = Image.new("RGB", (W, h), (8, 10, 14))
    band = _row([_text("AT&T STADIUM", COWBOYS["silver"]), star(200, (40, 110, 255)),
                 _text("HOW BOUT THEM COWBOYS", COWBOYS["white"]), star(200, (40, 110, 255))], W, h, SCALE * 8, 0.5)
    bot.paste(band, (0, 0), band)
    im.paste(bot, (0, h))
    return im


def black(size=32):
    """The board's housing: near black with faint panel seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (12, 13, 15))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(24, 25, 28), width=SCALE // 2)
        d.line([0, k, S, k], fill=(24, 25, 28), width=SCALE // 2)
    return im


def membrane(bright, seed, size=128, grid=8):
    """The roof from below: translucent membrane panels (``bright``) between dark steel trusses on a grid (the roof
    closed and roof open photos, 2022: long white panels framed by black trusses)."""
    S = size * SCALE
    r = rng(seed)
    a = np.zeros((S, S, 3), np.float32)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    for k in range(3):
        a[..., k] = bright[k] * (0.92 + 0.08 * n)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    step = S // grid
    for k in range(0, S, step):
        d.rectangle([k, 0, k + SCALE * 2, S], fill=(38, 40, 44))              # the trusses across
        d.line([0, k, S, k], fill=(70, 72, 76), width=SCALE)                  # the purlins
        for j in range(0, S, step // 2):                                      # the truss's diagonals
            d.line([k, j, k + SCALE * 2, j + step // 2], fill=(58, 60, 64), width=max(1, SCALE // 2))
    return im


def roof_under(size=128):
    """The fixed roof from below: grey translucent panels on big white steel trusses and purlins (the Dec 2025 interior and
    the 2022 roof photos: white girders, the panels outside the central corridor a mid grey)."""
    S = size * SCALE
    r = rng(23)
    a = np.zeros((S, S, 3), np.float32)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    for k, v in enumerate((132, 136, 142)):
        a[..., k] = v * (0.9 + 0.1 * n)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    step = S // 6
    for k in range(0, S, step):
        d.rectangle([k, 0, k + SCALE * 3, S], fill=(226, 228, 230))          # the trusses across (white steel)
        d.line([0, k, S, k], fill=(200, 202, 206), width=SCALE)             # the purlins
        for j in range(0, S, step // 2):
            d.line([k, j, k + step // 2, j + step // 2], fill=(188, 190, 194), width=max(1, SCALE // 2))
    return im


def panels(size=128):
    """The operable panels closed, from below: bright translucent membrane between white girders (the Dec 2025 interior,
    the 2010 full view)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (240, 242, 240))
    d = ImageDraw.Draw(im)
    step = S // 6
    for k in range(0, S, step):
        d.rectangle([k, 0, k + SCALE * 2, S], fill=(206, 208, 212))
        d.line([0, k, S, k], fill=(218, 220, 222), width=SCALE)
    return im


def rail(size=(64, 16)):
    """A Party Pass deck's railing: glass (alpha) with a steel top rail and posts."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (150, 170, 190, 90))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.16)], fill=(196, 200, 206, 255))
    for x in range(0, W, W // 4):
        d.rectangle([x, 0, x + SCALE, H], fill=(170, 174, 180, 255))
    return im


def roof_top(size=128):
    """The dome from outside: white membrane with faint seams (the 2010 and 2018 photos)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (230, 232, 234))
    d = ImageDraw.Draw(im)
    for x in range(0, S, SCALE * 8):
        d.line([x, 0, x, S], fill=(210, 212, 216), width=max(1, SCALE // 2))
    return im


def roof_edge(size=(64, 32)):
    """The eave's band over the glass wall: silver metal (the exterior photos)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (196, 200, 204))
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(H * 0.8), W, H], fill=(120, 124, 130))
    return im


def truss(size=(64, 32)):
    """The arches' side faces: grey steel lattice (chords and X bracing) with the sky through it (alpha)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (150, 154, 160, 255)
    t = SCALE * 3
    d.rectangle([0, 0, W, t], fill=c); d.rectangle([0, H - t, W, H], fill=c)
    for x in range(0, W + 1, W // 2):
        d.rectangle([x - t // 2, 0, x + t // 2, H], fill=c)
    for x0 in range(0, W, W // 2):
        d.line([x0, 0, x0 + W // 2, H], fill=c, width=t // 2)
        d.line([x0, H, x0 + W // 2, 0], fill=c, width=t // 2)
    return im


def steel(size=32):
    S = size * SCALE
    return Image.new("RGB", (S, S), (170, 174, 178))


def lamps(size=(64, 32)):
    """The light fixtures on the roof trusses: bright lamps in a dark frame."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (30, 32, 36))
    d = ImageDraw.Draw(im)
    for x in range(SCALE * 2, W, SCALE * 8):
        d.rectangle([x, int(H * 0.25), x + SCALE * 5, int(H * 0.75)], fill=(255, 252, 240))
    return im


def facade(size=128):
    """The curtain wall: blue-grey glass with its grid of mullions (the 2010 and outside-view photos), a lighter spandrel
    band at each floor."""
    S = size * SCALE
    r = rng(31)
    a = np.zeros((S, S, 3), np.float32)
    g = np.linspace(0.0, 1.0, S)[:, None]
    for k, (lo, hi) in enumerate(zip((70, 92, 116), (104, 128, 152))):
        a[..., k] = lo + (hi - lo) * (0.5 + 0.5 * np.cos(g * math.pi * 2))
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 4):
        d.rectangle([x, 0, x + SCALE, S], fill=(46, 54, 64))
    for y in range(0, S, S // 4):
        d.rectangle([0, y, S, y + SCALE * 2], fill=(150, 160, 172))
    for _ in range(40):
        x, y = int(r.integers(0, S)), int(r.integers(0, S))
        d.rectangle([x, y, x + SCALE * 6, y + SCALE * 3], fill=(128, 146, 166))
    return im


def endglass(size=(64, 64)):
    """The glass end walls (the end-zone doors) seen from inside: daylight through a tall grid of glass (bright by day;
    the model's night light darkens it)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (lo, hi) in enumerate(zip((196, 214, 232), (150, 176, 206))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for x in range(0, W, W // 6):
        d.rectangle([x, 0, x + SCALE, H], fill=(70, 76, 84))
    for y in range(0, H, H // 5):
        d.rectangle([0, y, W, y + SCALE], fill=(90, 96, 104))
    return im


def stone(size=64):
    S = size * SCALE
    r = rng(41)
    a = (168 + 12 * _blur(r.random((S, S)), 2)).astype(np.uint8)
    im = Image.fromarray(np.dstack([a, a - 4, a - 12]))
    d = ImageDraw.Draw(im)
    for y in range(0, S, S // 4):
        d.line([0, y, S, y], fill=(120, 116, 108), width=SCALE)
    return im


#: the field: Hellas Matrix turf (Wikipedia) with light and dark 5-yard bands (the 2022, Dec 2025 and 2026 photos)
TURF_LIGHT, TURF_DARK = (82, 138, 64), (62, 114, 50)


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


def drawings():
    return {
        "att_seat_front": (seat(0.18, 11), (64, 128)), "att_seat_mid": (seat(0.32, 12), (64, 128)),
        "att_seat_back": (seat(0.48, 13), (64, 128)), "att_deck": (deck(), (64, 128)),
        "att_concrete": (base.concrete(), (64, 64)), "att_wall": (wall(), (256, 32)), "att_rail": (rail(), (64, 16)),
        "LIGHT_att_ribbon": (ribbon(), (256, 64)), "LIGHT_att_glass": (base.glass(), (128, 64)),
        "LIGHT_att_concourse": (base.concourse(), (128, 64)), "att_portal": (base.vomitory(), (32, 32)),
        "att_dark": (base.dark(), (32, 32)), "att_black": (black(), (32, 32)),
        "att_roof_under": (roof_under(), (64, 64)),
        "att_panels": (panels(), (128, 128)),
        "att_roof_top": (roof_top(), (64, 64)), "att_roof_edge": (roof_edge(), (64, 32)),
        "att_truss": (truss(), (64, 32)), "att_steel": (steel(), (32, 32)), "LIGHT_att_lights": (lamps(), (64, 32)),
        "att_facade": (facade(), (128, 128)), "LIGHT_att_endglass": (endglass(), (64, 64)), "att_stone": (stone(), (64, 64)),
        "att_plaza": (base.plaza(), (32, 32)), "att_ground": (base.ground(), (32, 32)),
        "att_asphalt": (base.asphalt(), (32, 32)), "att_road": (base.road(), (32, 32)),
        "att_building": (base.building(), (32, 32)),
        "field/att_grass": (field_turf(), (128, 64)), "field/att_grass_outside": (field_outside(), (128, 128)),
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
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_att_model_art/v1", art=manifest), indent=1) + "\n")
    print("ATT_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
