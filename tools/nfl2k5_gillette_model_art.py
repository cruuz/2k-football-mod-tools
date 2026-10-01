#!/usr/bin/env python3
"""Draw the Gillette Stadium model's art (job st2, 2026-09-28): deterministic, procedural, plain type only.

  python3 tools/nfl2k5_gillette_model_art.py OUT_DIR [--masters MASTER_DIR]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model, and no logo is drawn (not the Patriots' mark, not the venue's lighthouse mark): every
name is plain type (Roboto Condensed Bold, Apache 2.0). Tones follow the reference photos (Commons: the 2023 Army-Navy
Game's north board, the 2024 and 2025 interiors and the 2025 north entrance; the Esri orthophoto, reference only): the
navy and blue-grey seats, the grey precast and glass building, the white and grey lighthouse, the navy, red and silver
ribbons, the grass in bands and the wooded horizon.
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
import nfl2k5_hard_rock_model_art as hr_art  # noqa: E402

SCALE = base.SCALE
rng, _blur, reduce, font, _text, _row = base.rng, base._blur, base.reduce, base.font, base._text, base._row
#: the Patriots' colours (navy, red, silver) and white
PATS = dict(navy=(0, 34, 68), red=(198, 12, 48), silver=(176, 183, 188), white=(255, 255, 255))
#: the seats (the orthophoto and the 2024 photo: a dark blue-grey, the club sections red)
SEAT_BLUE = (52, 66, 92)


def seat(p_light, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0: blue-grey seats,
    a few lighter ones scattered through them (``p_light``)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (34, 42, 58))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(160, 162, 164))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(24, 28, 38))
        for c in range(cols):
            x = c * pitch
            basec = (92, 108, 134) if r.random() < p_light else SEAT_BLUE
            tone = int(r.integers(-8, 9))
            fill = tuple(int(np.clip(v + tone, 0, 255)) for v in basec)
            d.rectangle([x + SCALE, y0 + int(rh * 0.30), x + pitch - SCALE, y0 + int(rh * 0.94)], fill=fill)
    aisle = int(round(W * 0.16 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(166, 166, 162))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(124, 124, 120), width=SCALE)
    return im


def wall(size=(256, 32)):
    """The field wall: navy padding with a silver line along its top and plain white type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), PATS["navy"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.07)], fill=PATS["silver"])
    items = [_text("NEW ENGLAND PATRIOTS", PATS["white"]), _text("GILLETTE STADIUM", PATS["white"]),
             _text("PATRIOTS", PATS["white"]), _text("FOXBOROUGH", PATS["white"])]
    band = _row(items, W, int(H * 0.93), SCALE * 12, 0.5)
    im.paste(band, (0, int(H * 0.07)), band)
    return im


def ribbon(size=(256, 64)):
    """The LED ribbons on the fascias (plain type, no logos): a navy band with PATRIOTS and NEW ENGLAND in white and red;
    and a band of navy, red, silver and white segments with names as type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    h = H // 2
    top = Image.new("RGB", (W, h), (0, 24, 50))
    band = _row([_text("PATRIOTS", PATS["white"]), _text("NEW ENGLAND", PATS["red"]),
                 _text("PATRIOTS", PATS["white"]), _text("FOXBOROUGH", PATS["silver"])], W, h, SCALE * 10, 0.56)
    top.paste(band, (0, 0), band)
    im.paste(top, (0, 0))
    segs = [(PATS["navy"], [_text("NEW ENGLAND PATRIOTS", PATS["white"])]), (PATS["red"], [_text("PATRIOTS", PATS["white"])]),
            ((240, 240, 240), [_text("GILLETTE STADIUM", PATS["navy"])]), (PATS["silver"], [_text("FOXBOROUGH, MA", PATS["navy"])])]
    x = 0
    for (bg, items), w in zip(segs, (0.30, 0.18, 0.28, 0.24)):
        sw = int(W * w) if x + int(W * w) <= W else W - x
        seg = Image.new("RGB", (sw, h), bg)
        b = _row(items, sw, h, SCALE * 6, 0.56)
        seg.paste(b, (0, 0), b)
        im.paste(seg, (x, h))
        x += sw
    if x < W:
        im.paste(Image.new("RGB", (W - x, h), (0, 24, 50)), (x, h))
    return im


def steel(size=32):
    """Painted steel (the board frames, the light banks' posts): light grey."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (180, 184, 188))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(160, 164, 168), width=SCALE)
    return im


def board_panels(size=(128, 128)):
    """The boards' stat panels and wings, lit like the rest of the board: a navy-to-red field with a white rule, a black
    window where the game's digits sit, the club's name and the down and distance as plain type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (lo, hi) in enumerate(zip((0, 34, 68), (120, 10, 30))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.06)], fill=PATS["white"])
    d.rectangle([int(W * 0.06), int(H * 0.14), int(W * 0.94), int(H * 0.50)], fill=(12, 12, 14))
    word = _row([_text("PATRIOTS", PATS["white"])], W, int(H * 0.16), SCALE * 8, 0.8)
    im.paste(word, (0, int(H * 0.54)), word)
    down = _row([_text("1ST & 10", PATS["white"])], W, int(H * 0.12), SCALE * 8, 0.8)
    im.paste(down, (0, int(H * 0.72)), down)
    return im


def letters(size=(256, 64)):
    """The venue's name as plain type, white on transparent (the venue's own mark is never drawn)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    t = _text("GILLETTE STADIUM", PATS["white"], px=240)
    h = int(H * 0.62)
    w = int(t.width * h / t.height)
    if w > W * 0.96:
        w = int(W * 0.96)
        h = int(t.height * w / t.width)
    t = t.resize((max(1, w), max(1, h)), Image.LANCZOS)
    im.paste(t, ((W - t.width) // 2, (H - t.height) // 2), t)
    return im


def facade(size=128):
    """The 2002 building (the orthophoto, the 2025 entrance photo): grey precast levels with dark glass bands."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (196, 198, 200))
    d = ImageDraw.Draw(im)
    for k in range(4):
        y = int(S * (0.1 + 0.25 * k))
        d.rectangle([0, y, S, y + int(S * 0.11)], fill=(48, 62, 78))
    for x in range(0, S, S // 4):
        d.rectangle([x, 0, x + SCALE * 3, S], fill=(172, 174, 176))
    return im


def tower(size=(64, 128)):
    """The lighthouse's shaft (the 2025 entrance photo): white and light grey panels in vertical bands."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (226, 228, 230))
    d = ImageDraw.Draw(im)
    for x in range(0, W, W // 4):
        d.rectangle([x, 0, x + W // 10, H], fill=(186, 190, 194))
    for y in range(0, H, H // 8):
        d.line([0, y, W, y], fill=(206, 208, 210), width=SCALE)
    return im


def lantern(size=(64, 32)):
    """The lighthouse's lantern: lit glass between dark mullions."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (236, 232, 206))
    d = ImageDraw.Draw(im)
    for x in range(0, W, W // 8):
        d.rectangle([x, 0, x + SCALE * 2, H], fill=(40, 44, 50))
    return im


def drawings():
    return {
        "ne_seat_front": (seat(0.05, 11), (64, 128)), "ne_seat_mid": (seat(0.09, 12), (64, 128)),
        "ne_seat_back": (seat(0.14, 13), (64, 128)),
        "ne_concrete": (base.concrete(), (64, 64)), "ne_wall": (wall(), (256, 32)),
        "LIGHT_ne_ribbon": (ribbon(), (256, 64)), "LIGHT_ne_glass": (base.glass(), (128, 64)),
        "LIGHT_ne_concourse": (base.concourse(), (128, 64)), "ne_portal": (base.vomitory(), (32, 32)),
        "ne_dark": (base.dark(), (32, 32)), "ne_black": (hr_art.black(), (32, 32)), "ne_steel": (steel(), (32, 32)),
        "LIGHT_ne_lights": (hr_art.lamps(), (64, 32)), "LIGHT_ne_board_panel": (board_panels(), (128, 128)),
        "ne_letters": (letters(), (256, 64)), "ne_facade": (facade(), (128, 128)), "ne_tower": (tower(), (64, 128)),
        "LIGHT_ne_lantern": (lantern(), (64, 32)),
        "ne_plaza": (base.plaza(), (32, 32)),
        "field/ne_grass": (hr_art.field_grass(), (128, 64)), "field/ne_grass_outside": (hr_art.field_outside(), (128, 128)),
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
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_gillette_model_art/v1", art=manifest), indent=1) + "\n")
    print("GILLETTE_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
