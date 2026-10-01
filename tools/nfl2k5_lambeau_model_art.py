#!/usr/bin/env python3
"""Draw the Lambeau Field model's art (job st2, 2026-09-28): deterministic, procedural, plain type only.

  python3 tools/nfl2k5_lambeau_model_art.py OUT_DIR [--masters MASTER_DIR]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model, and no logo is drawn (not the Packers' "G", not the venue's mark): every name is plain
type (Roboto Condensed Bold, Apache 2.0). Tones follow the reference photos (Commons: the 2015 aerial, the 2016
December game panorama, the 2017 north end, the 2024 and 2025 exteriors; the Esri orthophoto, reference only): the
aluminium bleachers, the green field wall and fascias with their gold lines, the red-brown brick and the green metal
and glass of the building, the green backs of the end zone boards, the grass in bands and the flat wooded horizon.
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
#: the Packers' colours (the club's style: dark green #203731, gold #FFB612) and white
PACK = dict(green=(32, 55, 49), gold=(255, 182, 18), white=(255, 255, 255))
#: the bleachers (the 2015 aerial: bare aluminium benches, silver-grey, the risers darker)
BENCH = (176, 180, 182)


def seat(p_green, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0: aluminium
    bleacher benches on darker risers, a few green chairbacks through them (``p_green``, the club rows)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (70, 74, 76))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 8
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.22)], fill=(150, 150, 146))
        d.rectangle([0, y0 + int(rh * 0.22), W, y0 + int(rh * 0.36)], fill=(58, 62, 64))
        for c in range(cols):
            x = c * pitch
            green = r.random() < p_green
            basec = (46, 78, 64) if green else BENCH
            tone = int(r.integers(-8, 9))
            fill = tuple(int(np.clip(v + tone, 0, 255)) for v in basec)
            d.rectangle([x, y0 + int(rh * 0.36), x + pitch - (SCALE if green else 0), y0 + int(rh * 0.9)], fill=fill)
    aisle = int(round(W * 0.16 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(186, 184, 178))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(140, 138, 132), width=SCALE)
    return im


def wall(size=(256, 32)):
    """The field wall: green padding with a gold line along its top and plain white type (the famous leap wall)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), PACK["green"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.07)], fill=PACK["gold"])
    items = [_text("GREEN BAY PACKERS", PACK["white"]), _text("LAMBEAU FIELD", PACK["white"]),
             _text("PACKERS", PACK["gold"]), _text("GREEN BAY", PACK["white"])]
    band = _row(items, W, int(H * 0.93), SCALE * 12, 0.5)
    im.paste(band, (0, int(H * 0.07)), band)
    return im


def ribbon(size=(256, 64)):
    """The LED ribbons on the fascias (plain type, no logos): a green band with PACKERS and GREEN BAY in gold and white;
    and a band of green, gold and white segments with names as type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    h = H // 2
    top = Image.new("RGB", (W, h), (24, 44, 38))
    band = _row([_text("PACKERS", PACK["gold"]), _text("GREEN BAY", PACK["white"]),
                 _text("PACKERS", PACK["gold"]), _text("LAMBEAU FIELD", PACK["white"])], W, h, SCALE * 10, 0.56)
    top.paste(band, (0, 0), band)
    im.paste(top, (0, 0))
    segs = [(PACK["green"], [_text("GREEN BAY PACKERS", PACK["white"])]), (PACK["gold"], [_text("PACKERS", PACK["green"])]),
            ((240, 240, 236), [_text("LAMBEAU FIELD", PACK["green"])]), ((24, 44, 38), [_text("GREEN BAY, WI", PACK["gold"])])]
    x = 0
    for (bg, items), w in zip(segs, (0.30, 0.18, 0.28, 0.24)):
        sw = int(W * w) if x + int(W * w) <= W else W - x
        seg = Image.new("RGB", (sw, h), bg)
        b = _row(items, sw, h, SCALE * 6, 0.56)
        seg.paste(b, (0, 0), b)
        im.paste(seg, (x, h))
        x += sw
    if x < W:
        im.paste(Image.new("RGB", (W - x, h), (24, 44, 38)), (x, h))
    return im


def steel(size=32):
    """Painted steel (the boards' legs, the light masts): green-grey."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (96, 110, 104))
    d = ImageDraw.Draw(im)
    for k in range(0, S, S // 4):
        d.line([k, 0, k, S], fill=(80, 92, 88), width=SCALE)
    return im


def board_panels(size=(128, 128)):
    """The boards' stat panels, lit like the rest of the board: a green field with a gold rule, a black window where the
    game's digits sit, the club's name and the down and distance as plain type."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    g = np.linspace(0.0, 1.0, H)[:, None]
    for k, (lo, hi) in enumerate(zip((32, 55, 49), (14, 30, 24))):
        a[..., k] = lo + (hi - lo) * g
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.06)], fill=PACK["gold"])
    d.rectangle([int(W * 0.06), int(H * 0.14), int(W * 0.94), int(H * 0.50)], fill=(12, 12, 14))
    word = _row([_text("PACKERS", PACK["gold"])], W, int(H * 0.16), SCALE * 8, 0.8)
    im.paste(word, (0, int(H * 0.54)), word)
    down = _row([_text("1ST & 10", PACK["white"])], W, int(H * 0.12), SCALE * 8, 0.8)
    im.paste(down, (0, int(H * 0.72)), down)
    return im


def letters(size=(256, 64)):
    """The venue's name as plain type, white on transparent (the venue's own mark is never drawn)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    t = _text("LAMBEAU FIELD", PACK["white"], px=240)
    h = int(H * 0.62)
    w = int(t.width * h / t.height)
    if w > W * 0.96:
        w = int(W * 0.96)
        h = int(t.height * w / t.width)
    t = t.resize((max(1, w), max(1, h)), Image.LANCZOS)
    im.paste(t, ((W - t.width) // 2, (H - t.height) // 2), t)
    return im


def facade(size=128):
    """The building (the 2015 to 2025 exteriors): green metal and glass levels over the brick base, dark window bands,
    red-brown brick piers."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (58, 84, 72))
    d = ImageDraw.Draw(im)
    for k in range(3):
        y = int(S * (0.08 + 0.22 * k))
        d.rectangle([0, y, S, y + int(S * 0.12)], fill=(40, 52, 58))
    d.rectangle([0, int(S * 0.72), S, S], fill=(128, 62, 46))
    for x in range(0, S, S // 4):
        d.rectangle([x, 0, x + SCALE * 5, S], fill=(136, 66, 48))
    for y in range(int(S * 0.72), S, SCALE * 3):
        d.line([0, y, S, y], fill=(112, 54, 40), width=max(1, SCALE // 2))
    return im


def brick(size=64):
    """The tower gates' and the atrium's red-brown brick with its courses and cream stone bands."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (140, 70, 50))
    d = ImageDraw.Draw(im)
    r = rng(71)
    for y in range(0, S, SCALE * 2):
        d.line([0, y, S, y], fill=(118, 58, 42), width=max(1, SCALE // 2))
    for k in range(200):
        x, y = int(r.integers(0, S)), int(r.integers(0, S))
        d.point((x, y), fill=(154, 80, 58))
    for y in (int(S * 0.3), int(S * 0.8)):
        d.rectangle([0, y, S, y + SCALE * 3], fill=(214, 200, 170))
    return im


def board_back(size=64):
    """The end zone boards' backs and the gates' plinths: deep green metal panels with their seams."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (34, 60, 50))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 4):
        d.line([x, 0, x, S], fill=(26, 48, 40), width=SCALE)
    for y in range(0, S, S // 2):
        d.line([0, y, S, y], fill=(28, 52, 44), width=max(1, SCALE // 2))
    return im


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
        "gb_seat_front": (seat(0.03, 11), (64, 128)), "gb_seat_mid": (seat(0.06, 12), (64, 128)),
        "gb_seat_back": (seat(0.10, 13), (64, 128)),
        "gb_concrete": (base.concrete(), (64, 64)), "gb_wall": (wall(), (256, 32)),
        "LIGHT_gb_ribbon": (ribbon(), (256, 64)), "LIGHT_gb_glass": (base.glass(), (128, 64)),
        "LIGHT_gb_concourse": (base.concourse(), (128, 64)), "gb_portal": (base.vomitory(), (32, 32)),
        "gb_dark": (base.dark(), (32, 32)), "gb_black": (hr_art.black(), (32, 32)), "gb_steel": (steel(), (32, 32)),
        "LIGHT_gb_lights": (hr_art.lamps(), (64, 32)), "LIGHT_gb_board_panel": (board_panels(), (128, 128)),
        "gb_letters": (letters(), (256, 64)), "gb_facade": (facade(), (128, 128)), "gb_brick": (brick(), (64, 64)),
        "gb_board_back": (board_back(), (64, 64)), "gb_roof": (roof(), (64, 64)),
        "gb_plaza": (base.plaza(), (32, 32)),
        "field/gb_grass": (hr_art.field_grass(), (128, 64)), "field/gb_grass_outside": (hr_art.field_outside(), (128, 128)),
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
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_lambeau_model_art/v1", art=manifest), indent=1) + "\n")
    print("LAMBEAU_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
