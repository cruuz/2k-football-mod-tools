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
    charcoal and black (the 2021 and 2022 interiors), a few mid-grey seats scattered through them (``p_grey``)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (58, 60, 64))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(150, 152, 154))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(36, 38, 40))
        for c in range(cols):
            x = c * pitch
            basec = (96, 98, 102) if r.random() < p_grey else (44, 46, 50)
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


def ribbon(size=(256, 64)):
    """The LED ribbons on the 200 and 300 levels (plain type, no logos): a black band with RAIDERS and LAS VEGAS in silver
    and white; and a lively band of red, silver, black and white segments with the partners' names as type (the 2021 and
    2022 photos: red and white LED ribbons with partner names)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    h = H // 2
    top = Image.new("RGB", (W, h), (6, 6, 8))
    band = _row([_text("RAIDERS", RAIDERS["silver"]), _text("LAS VEGAS", RAIDERS["white"]),
                 _text("RAIDER NATION", RAIDERS["silver"]), _text("LAS VEGAS", RAIDERS["white"])], W, h, SCALE * 10, 0.56)
    top.paste(band, (0, 0), band)
    im.paste(top, (0, 0))
    segs = [((200, 20, 30), [_text("SUMMERLIN.COM", RAIDERS["white"])]),
            (RAIDERS["silver"], [_text("RAIDERS", RAIDERS["black"])]),
            ((10, 10, 12), [_text("ALLEGIANT STADIUM", RAIDERS["white"])]),
            ((240, 240, 242), [_text("NEW HOMES NOW SELLING", (200, 20, 30))])]
    x = 0
    for (bg, items), w in zip(segs, (0.24, 0.20, 0.28, 0.28)):
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
    """The boards' housings and the lanai's frame: near black with faint panel seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (12, 13, 15))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(24, 25, 28), width=SCALE // 2)
        d.line([0, k, S, k], fill=(24, 25, 28), width=SCALE // 2)
    return im


def roof_under(size=128):
    """The ETFE roof from below (the 2021 and 2022 interiors): bright translucent cushions on a dense white steel grid,
    the cable net's lines across them."""
    S = size * SCALE
    r = rng(29)
    a = np.zeros((S, S, 3), np.float32)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    for k, v in enumerate((232, 236, 240)):
        a[..., k] = v * (0.93 + 0.07 * n)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    step = S // 8
    for k in range(0, S, step):
        d.rectangle([k, 0, k + SCALE * 2, S], fill=(196, 198, 202))
        d.rectangle([0, k, S, k + SCALE * 2], fill=(196, 198, 202))
    for k in range(0, S, step // 2):
        d.line([k, 0, k + step // 2, S], fill=(214, 216, 220), width=max(1, SCALE // 2))
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


def lanai(size=(128, 128)):
    """The lanai's tall glass (the torch photo: a grid of tall panes with the Strip bright beyond): thin dark mullions and
    a faint blue tint, the panes mostly transparent so the Strip's towers show through (alpha)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (150, 176, 206, 64))
    d = ImageDraw.Draw(im)
    for x in range(0, W, W // 8):
        d.rectangle([x, 0, x + SCALE, H], fill=(40, 42, 46, 255))
    for y in range(0, H, H // 4):
        d.rectangle([0, y, W, y + SCALE], fill=(40, 42, 46, 255))
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
    for x in range(0, S, S // 8):
        d.rectangle([x, 0, x + SCALE // 2, S], fill=(46, 48, 54))
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
    """The LED mesh toward I-15 (27,600 sq ft; the 2024 photo shows it running game-day graphics): a black field with
    RAIDERS and ALLEGIANT STADIUM in silver and white (plain type)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (8, 8, 10))
    band = _row([_text("RAIDERS", RAIDERS["silver"]), _text("ALLEGIANT STADIUM", RAIDERS["white"]),
                 _text("LAS VEGAS", RAIDERS["silver"])], W, H, SCALE * 16, 0.5)
    im.paste(band, (0, 0), band)
    return im


def strip(size=(64, 64)):
    """The Strip's towers: glass with rows of lit windows (bright by night through the LIGHT_ class)."""
    S_w, S_h = size[0] * SCALE, size[1] * SCALE
    r = rng(57)
    im = Image.new("RGB", (S_w, S_h), (70, 78, 90))
    d = ImageDraw.Draw(im)
    for y in range(0, S_h, SCALE * 4):
        for x in range(0, S_w, SCALE * 3):
            if r.random() < 0.55:
                d.rectangle([x, y + SCALE, x + SCALE * 2, y + SCALE * 3], fill=(236, 218, 170))
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
        "LIGHT_ag_ribbon": (ribbon(), (256, 64)), "LIGHT_ag_glass": (base.glass(), (128, 64)),
        "LIGHT_ag_concourse": (base.concourse(), (128, 64)), "ag_portal": (base.vomitory(), (32, 32)),
        "ag_dark": (base.dark(), (32, 32)), "ag_black": (black(), (32, 32)),
        "ag_roof_under": (roof_under(), (128, 128)), "ag_roof_top": (roof_top(), (64, 64)),
        "ag_roof_rim": (roof_rim(), (64, 64)),
        "LIGHT_ag_lights": (lamps(), (64, 32)), "LIGHT_ag_lanai": (lanai(), (128, 128)),
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
