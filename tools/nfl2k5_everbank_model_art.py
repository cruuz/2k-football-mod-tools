#!/usr/bin/env python3
"""Draw the EverBank Stadium model's art (job st2, 2026-09-28): deterministic, procedural, plain type only.

  python3 tools/nfl2k5_everbank_model_art.py OUT_DIR [--masters MASTER_DIR]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model, and no logo is drawn (not the Jaguars' mark, not the venue's or the bank's): every name is
plain type (Roboto Condensed Bold, Apache 2.0). Tones follow the reference photos (the 2025 Esri orthophoto, reference
only; Commons): the teal seats, the black and teal field wall, the concrete and teal panels of the building, the white
fabric of Daily's Place; for the 2026 construction the bare concrete risers, the white canopy trusses, the yellow tower
cranes, the black safety netting and the site fencing, drawn as lattices and meshes the game shows through.
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
#: the Jaguars' colours (teal #006778, gold #D7A22A, black #101820) and white
JAGS = dict(teal=(0, 103, 120), gold=(215, 162, 42), black=(16, 24, 32), white=(255, 255, 255))
#: the seats (the 2025 orthophoto: a light teal-blue)
SEAT_TEAL = (58, 132, 150)


def seat(p_dark, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0: teal chairbacks,
    a few darker ones scattered through them (``p_dark``)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (40, 52, 58))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(168, 168, 164))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(28, 34, 40))
        for c in range(cols):
            x = c * pitch
            basec = (36, 92, 108) if r.random() < p_dark else SEAT_TEAL
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
    """The field wall: black padding with a gold line along its top and plain white type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), JAGS["black"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.07)], fill=JAGS["gold"])
    items = [_text("JACKSONVILLE JAGUARS", JAGS["white"]), _text("EVERBANK STADIUM", JAGS["white"]),
             _text("JAGUARS", JAGS["gold"]), _text("JACKSONVILLE", JAGS["white"])]
    band = _row(items, W, int(H * 0.93), SCALE * 12, 0.5)
    im.paste(band, (0, int(H * 0.07)), band)
    return im


def ribbon(size=(256, 64)):
    """The LED ribbons on the fascias (plain type, no logos): a teal band with JAGUARS and JACKSONVILLE in gold and
    white; and a band of black, gold, white and teal segments with names as type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    h = H // 2
    top = Image.new("RGB", (W, h), (0, 70, 82))
    band = _row([_text("JAGUARS", JAGS["gold"]), _text("JACKSONVILLE", JAGS["white"]),
                 _text("JAGUARS", JAGS["gold"]), _text("EVERBANK STADIUM", JAGS["white"])], W, h, SCALE * 10, 0.56)
    top.paste(band, (0, 0), band)
    im.paste(top, (0, 0))
    segs = [(JAGS["black"], [_text("JACKSONVILLE JAGUARS", JAGS["white"])]), (JAGS["gold"], [_text("JAGUARS", JAGS["black"])]),
            ((240, 240, 236), [_text("EVERBANK STADIUM", JAGS["black"])]), ((0, 70, 82), [_text("JACKSONVILLE, FL", JAGS["gold"])])]
    x = 0
    for (bg, items), w in zip(segs, (0.30, 0.18, 0.28, 0.24)):
        sw = int(W * w) if x + int(W * w) <= W else W - x
        seg = Image.new("RGB", (sw, h), bg)
        b = _row(items, sw, h, SCALE * 6, 0.56)
        seg.paste(b, (0, 0), b)
        im.paste(seg, (x, h))
        x += sw
    if x < W:
        im.paste(Image.new("RGB", (W - x, h), (0, 70, 82)), (x, h))
    return im


def steel(size=32):
    """Painted steel (the boards' legs, the light masts, the crane's weights): mid grey."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (150, 154, 158))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(126, 130, 134), width=SCALE)
    return im


def board_panels(size=(128, 128)):
    """The boards' stat panels, lit like the rest of the board: a teal field with a gold rule, a black window where the
    game's digits sit, the club's name and the down and distance as plain type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (lo, hi) in enumerate(zip((0, 103, 120), (0, 44, 54))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.06)], fill=JAGS["gold"])
    d.rectangle([int(W * 0.06), int(H * 0.14), int(W * 0.94), int(H * 0.50)], fill=(12, 12, 14))
    word = _row([_text("JAGUARS", JAGS["gold"])], W, int(H * 0.16), SCALE * 8, 0.8)
    im.paste(word, (0, int(H * 0.54)), word)
    down = _row([_text("1ST & 10", JAGS["white"])], W, int(H * 0.12), SCALE * 8, 0.8)
    im.paste(down, (0, int(H * 0.72)), down)
    return im


def letters(size=(256, 64)):
    """The venue's name as plain type, white on transparent (the venue's own mark is never drawn)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    t = _text("EVERBANK STADIUM", JAGS["white"], px=240)
    h = int(H * 0.62)
    w = int(t.width * h / t.height)
    if w > W * 0.96:
        w = int(W * 0.96)
        h = int(t.height * w / t.width)
    t = t.resize((max(1, w), max(1, h)), Image.LANCZOS)
    im.paste(t, ((W - t.width) // 2, (H - t.height) // 2), t)
    return im


def facade(size=128):
    """The building (the orthophoto and the 2010 to 2020 exteriors): pale grey concrete levels, the ramps' dark bands and
    the concourses' openings."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (206, 204, 198))
    d = ImageDraw.Draw(im)
    for k in range(3):
        y = int(S * (0.1 + 0.28 * k))
        d.rectangle([0, y, S, y + int(S * 0.1)], fill=(44, 56, 64))
    for x in range(0, S, S // 4):
        d.rectangle([x, int(S * 0.22), x + int(S * 0.12), int(S * 0.36)], fill=(74, 84, 90))
    for x in range(0, S, S // 8):
        d.line([x, 0, x, S], fill=(186, 184, 178), width=max(1, SCALE // 2))
    return im


def board_back(size=64):
    """The boards' housings behind the screens: dark grey metal panels with their seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (54, 58, 62))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 4):
        d.line([x, 0, x, S], fill=(44, 48, 52), width=SCALE)
    for y in range(0, S, S // 2):
        d.line([0, y, S, y], fill=(46, 50, 54), width=max(1, SCALE // 2))
    return im


def riser(size=64):
    """The stripped 400 level (2026): bare concrete treads and risers, the seats' anchor holes in rows, stained."""
    S = size * SCALE
    r = rng(81)
    n = _blur(r.random((S // 4, S // 4)), 2)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((4, 4)))
    a = np.dstack([166 + 22 * n, 164 + 22 * n, 158 + 20 * n])
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for k in range(4):
        y = int(S * k / 4)
        d.rectangle([0, y, S, y + int(S * 0.07)], fill=(120, 118, 112))
        for x in range(SCALE * 3, S, SCALE * 8):
            d.rectangle([x, y + int(S * 0.12), x + SCALE, y + int(S * 0.12) + SCALE], fill=(96, 94, 90))
    return im


def deck(size=32):
    """The north pool deck: light concrete pavers."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (210, 206, 196))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(190, 186, 176), width=max(1, SCALE // 2))
        d.line([0, k, S, k], fill=(190, 186, 176), width=max(1, SCALE // 2))
    return im


def water(size=32):
    """The pools' water (the 2025 orthophoto: light blue)."""
    S = size * SCALE
    r = rng(83)
    n = _blur(r.random((S // 2, S // 2)), 1)
    n = np.kron((n - n.min()) / max(1e-6, n.max() - n.min()), np.ones((2, 2)))
    a = np.dstack([70 + 30 * n, 168 + 30 * n, 206 + 24 * n])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def drained(size=32):
    """The drained pools (2026): pale grey plaster with a dark drain line."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (178, 184, 186))
    d = ImageDraw.Draw(im)
    d.line([0, S // 2, S, S // 2], fill=(110, 116, 118), width=SCALE)
    return im


def _mesh(size, colour, cell, width, alpha=255, frame=None):
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for k in range(-H, W + H, cell * SCALE):
        d.line([k, H, k + H, 0], fill=colour + (alpha,), width=width * SCALE)
        d.line([k, 0, k + H, H], fill=colour + (alpha,), width=width * SCALE)
    if frame:
        d.rectangle([0, 0, W - 1, H - 1], outline=frame + (255,), width=SCALE * 2)
    return im


def fence(size=(64, 32)):
    """Site fencing round the closed pool deck: a dark mesh on posts with a teal screen along its middle."""
    im = _mesh(size, (40, 44, 48), 3, 1, 230)
    d = ImageDraw.Draw(im)
    W, H = im.size
    d.rectangle([0, int(H * 0.35), W, int(H * 0.65)], fill=(0, 92, 108, 235))
    for x in range(0, W, W // 4):
        d.rectangle([x, 0, x + SCALE * 2, H], fill=(70, 74, 78, 255))
    return im


def fabric(size=64):
    """Daily's Place's roof: white fabric panels with their seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (236, 236, 232))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(214, 214, 210), width=SCALE)
    return im


def truss(size=(32, 32)):
    """The canopy's steel trusses (2026): white-grey chords and a diagonal lattice the sky shows through."""
    im = _mesh(size, (214, 216, 218), 16, 2, 255, frame=(222, 224, 226))
    return im


def crane(size=(32, 32)):
    """The tower cranes' lattice (2026): yellow chords and bracing the sky shows through."""
    im = _mesh(size, (232, 186, 24), 16, 2, 255, frame=(240, 196, 30))
    return im


def cab(size=32):
    """A crane's cab: white with a dark window band."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (236, 234, 226))
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(S * 0.2), S, int(S * 0.55)], fill=(40, 52, 64))
    return im


def netting(size=(32, 32)):
    """Safety netting (2026): a fine black mesh, mostly see-through."""
    return _mesh(size, (18, 20, 22), 3, 1, 200)


def roof(size=64):
    """The building's roofs round the bowl (the 2015 aerial and the orthophoto: white membrane with grey seams and the
    odd rooftop unit)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (222, 222, 218))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 8):
        d.line([x, 0, x, S], fill=(204, 204, 200), width=max(1, SCALE // 2))
    r = rng(73)
    for _k in range(3):
        x, y = int(r.integers(0, S - SCALE * 10)), int(r.integers(0, S - SCALE * 8))
        d.rectangle([x, y, x + SCALE * 9, y + SCALE * 6], fill=(168, 170, 172))
    return im


def drawings():
    return {
        "jx_seat_front": (seat(0.04, 11), (64, 128)), "jx_seat_mid": (seat(0.07, 12), (64, 128)),
        "jx_seat_back": (seat(0.10, 13), (64, 128)),
        "jx_concrete": (base.concrete(), (64, 64)), "jx_wall": (wall(), (256, 32)),
        "LIGHT_jx_ribbon": (ribbon(), (256, 64)), "LIGHT_jx_glass": (base.glass(), (128, 64)),
        "LIGHT_jx_concourse": (base.concourse(), (128, 64)), "jx_portal": (base.vomitory(), (32, 32)),
        "jx_dark": (base.dark(), (32, 32)), "jx_black": (hr_art.black(), (32, 32)), "jx_steel": (steel(), (32, 32)),
        "LIGHT_jx_lights": (hr_art.lamps(), (64, 32)), "LIGHT_jx_board_panel": (board_panels(), (128, 128)),
        "jx_letters": (letters(), (256, 64)), "jx_facade": (facade(), (128, 128)), "jx_board_back": (board_back(), (64, 64)),
        "jx_roof": (roof(), (64, 64)), "jx_riser": (riser(), (64, 64)), "jx_deck": (deck(), (32, 32)),
        "jx_water": (water(), (32, 32)), "jx_drained": (drained(), (32, 32)), "jx_fence": (fence(), (64, 32)),
        "jx_fabric": (fabric(), (64, 64)), "jx_truss": (truss(), (32, 32)), "jx_crane": (crane(), (32, 32)),
        "jx_cab": (cab(), (32, 32)), "jx_netting": (netting(), (32, 32)),
        "jx_plaza": (base.plaza(), (32, 32)),
        "field/jx_grass": (hr_art.field_grass(), (128, 64)), "field/jx_grass_outside": (hr_art.field_outside(), (128, 128)),
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
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_everbank_model_art/v1", art=manifest), indent=1) + "\n")
    print("EVERBANK_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
