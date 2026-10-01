#!/usr/bin/env python3
"""Draw the Hard Rock Stadium model's art (job st2, 2026-09-28): deterministic, procedural, plain type only.

  python3 tools/nfl2k5_hard_rock_model_art.py OUT_DIR [--masters MASTER_DIR]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model, and no logo is drawn (not the Dolphins' mark, not the venue's guitar or circle): every
name is plain type (Roboto Condensed Bold, Apache 2.0). Tones follow the reference photos (Commons: the 2026 College
Football Playoff pregame views, the 2016 and 2022 interiors, the 2020 aerials and exteriors): the aqua seats, the white
canopy on its white steel with the translucent ETFE ring round the opening, the white spires, the white concrete
building with its spiral ramps, the aqua and orange LED ribbons, the Paspalum grass mown in bands and the flat, green
South Florida horizon.
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
rng, _blur, reduce, font, _text, _row = base.rng, base._blur, base.reduce, base.font, base._text, base._row
#: the Dolphins' colours (aqua, orange, marine blue) and white
DOLPHINS = dict(aqua=(0, 142, 151), orange=(252, 76, 2), blue=(0, 87, 120), white=(255, 255, 255))
#: the seats (the 2016 renovation: "the orange colored seats were also replaced with aqua colored ones", Wikipedia; the
#: 2026 pregame views: a bright aqua)
SEAT_AQUA = (26, 150, 158)


def seat(p_light, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0: aqua seats, a
    few lighter ones scattered through them (``p_light``)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (30, 88, 94))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(168, 172, 172))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(22, 60, 64))
        for c in range(cols):
            x = c * pitch
            basec = (70, 186, 192) if r.random() < p_light else SEAT_AQUA
            tone = int(r.integers(-8, 9))
            fill = tuple(int(np.clip(v + tone, 0, 255)) for v in basec)
            d.rectangle([x + SCALE, y0 + int(rh * 0.30), x + pitch - SCALE, y0 + int(rh * 0.94)], fill=fill)
    aisle = int(round(W * 0.16 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(170, 170, 166))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(128, 128, 124), width=SCALE)
    return im


def wall(size=(256, 32)):
    """The field wall: aqua padding with a white line along its top and plain white type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), DOLPHINS["aqua"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.07)], fill=DOLPHINS["white"])
    items = [_text("MIAMI DOLPHINS", DOLPHINS["white"]), _text("FINS UP", DOLPHINS["white"]),
             _text("MIAMI DOLPHINS", DOLPHINS["white"]), _text("HARD ROCK STADIUM", DOLPHINS["white"])]
    band = _row(items, W, int(H * 0.93), SCALE * 12, 0.5)
    im.paste(band, (0, int(H * 0.07)), band)
    return im


def ribbon(size=(256, 64)):
    """The LED ribbons on the club and upper fascias (plain type, no logos): a marine blue band with DOLPHINS and FINS UP
    in white and aqua; and a band of aqua, orange, white and blue segments with names as type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    h = H // 2
    top = Image.new("RGB", (W, h), (0, 40, 60))
    band = _row([_text("DOLPHINS", DOLPHINS["white"]), _text("FINS UP", DOLPHINS["aqua"]),
                 _text("MIAMI", DOLPHINS["white"]), _text("FINS UP", DOLPHINS["aqua"])], W, h, SCALE * 10, 0.56)
    top.paste(band, (0, 0), band)
    im.paste(top, (0, 0))
    segs = [(DOLPHINS["aqua"], [_text("MIAMI DOLPHINS", DOLPHINS["white"])]),
            (DOLPHINS["orange"], [_text("FINS UP", DOLPHINS["white"])]),
            ((245, 245, 245), [_text("HARD ROCK STADIUM", DOLPHINS["blue"])]),
            (DOLPHINS["blue"], [_text("MIAMI GARDENS", DOLPHINS["white"])])]
    x = 0
    for (bg, items), w in zip(segs, (0.28, 0.18, 0.30, 0.24)):
        sw = int(W * w) if x + int(W * w) <= W else W - x
        seg = Image.new("RGB", (sw, h), bg)
        b = _row(items, sw, h, SCALE * 6, 0.56)
        seg.paste(b, (0, 0), b)
        im.paste(seg, (x, h))
        x += sw
    if x < W:
        im.paste(Image.new("RGB", (W - x, h), (0, 40, 60)), (x, h))
    return im


def black(size=32):
    """The boards' housings: near black with faint panel seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (12, 13, 15))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(24, 25, 28), width=SCALE // 2)
        d.line([0, k, S, k], fill=(24, 25, 28), width=SCALE // 2)
    return im


def roof_under(size=128):
    """The canopy from below (the 2026 press-box and sideline views): white steel trusses in a square grid with their
    diagonals, over the decking in the canopy's own shade (mid grey)."""
    S = size * SCALE
    r = rng(29)
    a = np.zeros((S, S, 3), np.float32)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    for k, v in enumerate((118, 122, 130)):
        a[..., k] = v * (0.92 + 0.08 * n)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    step = S // 4
    for k in range(0, S, step):
        d.rectangle([k, 0, k + SCALE * 3, S], fill=(236, 238, 240))
        d.rectangle([0, k, S, k + SCALE * 3], fill=(236, 238, 240))
        d.line([k, 0, k + step, step * 4], fill=(222, 224, 228), width=SCALE)
    for k in range(0, S, step):
        d.line([k, 0, k + step, step], fill=(214, 216, 220), width=SCALE)
        d.line([k + step, 0, k, step], fill=(214, 216, 220), width=SCALE)
    return im


def roof_top(size=64):
    """The canopy from above: the white TPO membrane (the Dolphins' 2016 modernization sheet: 530,000 sq ft of single-ply
    TPO) with faint seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (236, 238, 238))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 8):
        d.line([x, 0, x, S], fill=(222, 224, 226), width=SCALE)
    return im


def roof_edge(size=(128, 32)):
    """The canopy's outer fascia: white panels with a grey shadow line under the top edge."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (230, 232, 234))
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(H * 0.12), W, int(H * 0.2)], fill=(196, 198, 202))
    for x in range(0, W, W // 8):
        d.line([x, 0, x, H], fill=(214, 216, 220), width=SCALE)
    return im


def etfe(size=(64, 64)):
    """The ETFE ring round the opening (94,000 sq ft, the modernization sheet): translucent white cushions on a white
    frame (alpha)."""
    S_w, S_h = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (S_w, S_h), (238, 242, 246, 150))
    d = ImageDraw.Draw(im)
    for x in range(0, S_w, S_w // 4):
        d.rectangle([x, 0, x + SCALE * 2, S_h], fill=(250, 250, 250, 255))
    for y in range(0, S_h, S_h // 4):
        d.rectangle([0, y, S_w, y + SCALE * 2], fill=(250, 250, 250, 255))
    return im


def lattice(size=(128, 32), members=6):
    """A white steel truss seen side on (the opening's edge truss and the arches over it): chords and diagonals on
    transparent (alpha)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (244, 246, 248, 255)
    t = SCALE * 3
    d.rectangle([0, 0, W, t], fill=c)
    d.rectangle([0, H - t, W, H], fill=c)
    step = W // members
    for k in range(members + 1):
        x = k * step
        d.rectangle([x - t // 2, 0, x + t // 2, H], fill=c)
        if k < members:
            d.line([x, 0, x + step, H], fill=c, width=t)
    return im


def mast(size=(32, 128)):
    """The spires: white, a soft shade down one side."""
    W, H = size[0] * SCALE, size[1] * SCALE
    g = np.linspace(0.0, 1.0, W)[None, :]
    a = np.zeros((H, W, 3), np.float32)
    for k, v in enumerate((244, 246, 248)):
        a[..., k] = v * (0.86 + 0.14 * np.sin(np.pi * g))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def cable(size=(8, 32)):
    S_w, S_h = size[0] * SCALE, size[1] * SCALE
    return Image.new("RGB", (S_w, S_h), (70, 72, 76))


def lamps(size=(64, 32)):
    S_w, S_h = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (S_w, S_h), (30, 32, 36))
    d = ImageDraw.Draw(im)
    for x in range(SCALE * 2, S_w, SCALE * 8):
        d.rectangle([x, int(S_h * 0.25), x + SCALE * 5, int(S_h * 0.75)], fill=(255, 252, 244))
    return im


def board_panels(size=(128, 128)):
    """The corner boards' side panels, lit like the rest of the board: a marine-to-aqua field with a white rule, a black
    window where the game's digits sit, the club's name and the down and distance as plain type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (lo, hi) in enumerate(zip((0, 120, 132), (0, 50, 72))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.06)], fill=DOLPHINS["white"])
    d.rectangle([int(W * 0.06), int(H * 0.14), int(W * 0.94), int(H * 0.50)], fill=(12, 12, 14))
    word = _row([_text("DOLPHINS", DOLPHINS["white"])], W, int(H * 0.16), SCALE * 8, 0.8)
    im.paste(word, (0, int(H * 0.54)), word)
    down = _row([_text("1ST & 10", DOLPHINS["white"])], W, int(H * 0.12), SCALE * 8, 0.8)
    im.paste(down, (0, int(H * 0.72)), down)
    return im


def letters(size=(256, 64)):
    """The venue's name as plain type, white on transparent (the guitar and the circle mark are never drawn)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    t = _text("HARD ROCK STADIUM", DOLPHINS["white"], px=240)
    h = int(H * 0.62)
    w = int(t.width * h / t.height)
    if w > W * 0.96:
        w = int(W * 0.96)
        h = int(t.height * w / t.width)
    t = t.resize((max(1, w), max(1, h)), Image.LANCZOS)
    im.paste(t, ((W - t.width) // 2, (H - t.height) // 2), t)
    return im


def facade(size=128):
    """The building (the 2020 and 2026 exteriors): white concrete levels with dark ribbon windows and the concourses'
    open bays between the columns."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (228, 228, 224))
    d = ImageDraw.Draw(im)
    for k in range(4):
        y = int(S * (0.1 + 0.25 * k))
        d.rectangle([0, y, S, y + int(S * 0.09)], fill=(58, 70, 80))
    for x in range(0, S, S // 4):
        d.rectangle([x, 0, x + SCALE * 3, S], fill=(206, 206, 202))
    return im


def ramp(size=(64, 64)):
    """The spiral ramps at the building's corners: white parapets with the dark ramp floors between them."""
    S_w, S_h = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (S_w, S_h), (40, 44, 48))
    d = ImageDraw.Draw(im)
    for k in range(0, S_h, S_h // 4):
        d.polygon([(0, k), (S_w, k - S_h // 8), (S_w, k - S_h // 8 + S_h // 10), (0, k + S_h // 10)], fill=(234, 234, 230))
    return im


def column(size=32):
    S = size * SCALE
    r = rng(41)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    a = np.dstack([214 + 16 * n, 214 + 16 * n, 208 + 16 * n])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


#: the field: Platinum TE Paspalum (the modernization sheet: "a lighter green shade") mown in 5-yard bands
GRASS_LIGHT, GRASS_DARK = (96, 156, 70), (74, 132, 56)


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
    return Image.new("RGB", (S, S), (80, 136, 60))


def drawings():
    return {
        "hr_seat_front": (seat(0.05, 11), (64, 128)), "hr_seat_mid": (seat(0.09, 12), (64, 128)),
        "hr_seat_back": (seat(0.14, 13), (64, 128)),
        "hr_concrete": (base.concrete(), (64, 64)), "hr_wall": (wall(), (256, 32)),
        "LIGHT_hr_ribbon": (ribbon(), (256, 64)), "LIGHT_hr_glass": (base.glass(), (128, 64)),
        "LIGHT_hr_concourse": (base.concourse(), (128, 64)), "hr_portal": (base.vomitory(), (32, 32)),
        "hr_dark": (base.dark(), (32, 32)), "hr_black": (black(), (32, 32)),
        "hr_roof_under": (roof_under(), (128, 128)), "hr_roof_top": (roof_top(), (64, 64)),
        "hr_roof_edge": (roof_edge(), (128, 32)), "hr_etfe": (etfe(), (64, 64)),
        "hr_truss": (lattice(), (128, 32)), "hr_arch": (lattice((128, 32), 10), (128, 32)),
        "hr_mast": (mast(), (32, 128)), "hr_cable": (cable(), (8, 32)),
        "LIGHT_hr_lights": (lamps(), (64, 32)), "LIGHT_hr_board_panel": (board_panels(), (128, 128)),
        "hr_letters": (letters(), (256, 64)), "hr_facade": (facade(), (128, 128)), "hr_ramp": (ramp(), (64, 64)),
        "hr_column": (column(), (32, 32)),
        "hr_plaza": (base.plaza(), (32, 32)),
        "field/hr_grass": (field_grass(), (128, 64)), "field/hr_grass_outside": (field_outside(), (128, 128)),
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
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_hard_rock_model_art/v1", art=manifest), indent=1) + "\n")
    print("HARD_ROCK_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
