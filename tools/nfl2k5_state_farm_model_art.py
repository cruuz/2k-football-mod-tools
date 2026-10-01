#!/usr/bin/env python3
"""State Farm Stadium model art (job st3): the textures the model draws, deterministic, at 4x masters reduced to their
native sizes.

The Cardinals' red bowl (every seat red), the field wall's pads and the ribbons (plain type), the translucent Birdair
fabric roof from below (pale panels on the white steel trusses) and from above (white fabric in radial bays), the two
retractable panels parked open, the Brunel trusses and the rails, the silver "barrel cactus" drum (tall curved metal
panels split by dark vertical slots), the glass at the gates, the desert ground, the White Tank Mountains, and the
stadium's own wordmark (Wikimedia Commons File:State_Farm_Stadium_logo.svg, a public-domain text logo, cut from the
file and never redrawn). The lots, roads and buildings reuse the Highmark art's drawings.

    python3 tools/nfl2k5_state_farm_model_art.py OUT_DIR --logo LOGO.png [--masters DIR]
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
import nfl2k5_usbank_model_art as usb  # noqa: E402

SCALE = base.SCALE
rng, _blur, reduce, _text, _row = base.rng, base._blur, base.reduce, base._text, base._row
_fit = usb._fit
#: the Cardinals' colours (NFL Record and Fact Book: Cardinal red #97233F, black, white, yellow #FFB612)
CARDS = dict(red=(151, 35, 63), black=(0, 0, 0), white=(255, 255, 255), gold=(255, 182, 18))
#: the seats as the photos show them under the sun (f008, f009, f032: a bright brick red)
SEAT = (160, 36, 40)
SILVER = (178, 184, 190)
LOGO = None


def _logo():
    im = Image.open(LOGO).convert("RGBA")
    return im.crop(im.getbbox())


def seat(p_light, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0; red seats, a few
    lighter ones where the sun catches them (``p_light``)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (120, 26, 30))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(156, 150, 146))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(56, 14, 16))
        for c in range(cols):
            x = c * pitch
            basec = (196, 60, 60) if r.random() < p_light else SEAT
            tone = int(r.integers(-6, 7))
            fill = tuple(int(np.clip(v + tone, 0, 255)) for v in basec)
            d.rectangle([x + SCALE, y0 + int(rh * 0.30), x + pitch - SCALE, y0 + int(rh * 0.94)], fill=fill)
    aisle = int(round(W * 0.16 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(160, 156, 150))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(116, 112, 108), width=SCALE)
    return im


def wall(size=(256, 32)):
    """The field wall (f010, f032: red pads with white plain type; the club's head is never drawn here)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), CARDS["red"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.08)], fill=CARDS["white"])
    items = [_text("CARDINALS", CARDS["white"]), _text("RED SEA", CARDS["white"]), _text("ARIZONA", CARDS["white"]),
             _text("CARDINALS", CARDS["white"])]
    band = _row(items, W, int(H * 0.92), SCALE * 12, 0.56)
    im.paste(band, (0, int(H * 0.08)), band)
    return im


def ribbon(size=(256, 64)):
    """The ribbon displays (Daktronics 2022): two bands a texture, the club's words and the partners in plain type (no
    partner logo is drawn)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    half = H // 2
    bands = [((24, 6, 10), [_text("RED SEA", CARDS["white"]), _text("CARDINALS", CARDS["white"]),
                           _text("BIRD GANG", CARDS["gold"]), _text("ARIZONA CARDINALS", CARDS["white"])]),
             (CARDS["red"], [_text("STATE FARM", CARDS["white"]), _text("DESERT DIAMOND", CARDS["white"]),
                             _text("REDZONE", CARDS["white"]), _text("STATE FARM", CARDS["white"])])]
    for k, (bg, items) in enumerate(bands):
        y0 = k * half
        ImageDraw.Draw(im).rectangle([0, y0, W, y0 + half], fill=bg)
        band = _row(items, W, half, SCALE * 10)
        im.paste(band, (0, y0), band)
    return im


def fabric_under(size=128):
    """The fabric roof from below (f008, f009, f037: translucent light grey panels between dark steel purlins and the
    trusses' chords; greyer than the sky)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (206, 210, 212))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 8):
        d.rectangle([x, 0, x + SCALE * 2, S], fill=(92, 96, 102))
    for y in range(0, S, S // 4):
        d.rectangle([0, y, S, y + SCALE * 2], fill=(76, 80, 86))
    for k in range(0, S, S // 4):
        d.line([k, 0, k + S // 4, S // 4], fill=(120, 124, 130), width=SCALE)
    return im


def fabric_top(size=64):
    """The fabric roof from above (the orthophotos, f000, f001: white fabric in radial bays, a seam every bay)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (236, 236, 232))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 2):
        d.line([x, 0, x, S], fill=(200, 202, 204), width=SCALE)
    for y in range(0, S, S // 8):
        d.line([0, y, S, y], fill=(222, 224, 224), width=max(1, SCALE // 2))
    return im


def panel_top(size=(128, 64)):
    """The retractable panels from above (f001: bright white fabric on the panel's frame, a dark rib across it every
    bay, the frame's edges grey)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (248, 250, 252))
    d = ImageDraw.Draw(im)
    for x in range(0, W, W // 8):
        d.rectangle([x, 0, x + SCALE * 2, H], fill=(150, 156, 164))
    d.rectangle([0, 0, W, SCALE * 3], fill=(120, 126, 134))
    d.rectangle([0, H - SCALE * 3, W, H], fill=(120, 126, 134))
    return im


def panel_edge(size=32):
    """The panels' frame and fascia, and the rails they ride on (f001: grey steel)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (118, 124, 132))
    d = ImageDraw.Draw(im)
    for y in range(0, S, S // 4):
        d.line([0, y, S, y], fill=(90, 96, 104), width=SCALE)
    return im


def rib(size=(32, 8)):
    """The fabric roof's radial ribs from above (the orthophotos, f000: light grey steel lines from the opening to the
    drum)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    return Image.new("RGB", (W, H), (164, 170, 178))


def inner(size=(64, 64)):
    """The drum's inside above the stands (f008, f009: light grey panels, daylight through the slots)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (150, 154, 160))
    d = ImageDraw.Draw(im)
    for y in range(0, H, H // 6):
        d.line([0, y, W, y], fill=(128, 132, 138), width=SCALE)
    d.rectangle([int(W * 0.46), 0, int(W * 0.54), H], fill=(232, 238, 244))
    return im


def truss(size=64):
    """The Brunel trusses and the roof's trusses (f008, f037: white steel lattices, the fabric showing through; alpha)."""
    S = size * SCALE
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (226, 228, 230, 255)
    t = SCALE * 2
    d.rectangle([0, 0, S, t], fill=c)
    d.rectangle([0, S - t, S, S], fill=c)
    for x in (0, S // 2, S):
        d.rectangle([x - t // 2, 0, x + t // 2, S], fill=c)
    for k in (0, S // 2):
        d.line([k, 0, k + S // 2, S], fill=c, width=max(1, SCALE * 3 // 2))
        d.line([k + S // 2, 0, k, S], fill=c, width=max(1, SCALE * 3 // 2))
    return im


def drum(size=(128, 128)):
    """The silver drum (f000, f001, f045 to f077): one tall curved metal "petal" a repeat, in horizontal courses, with a
    wide dark slot of glass at its edge (the "barrel cactus" skin; about 40 m a petal, the slot about 3.5 m)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(81)
    im = Image.new("RGB", (W, H), SILVER)
    d = ImageDraw.Draw(im)
    for y in range(0, H, SCALE * 3):
        tone = int(r.integers(-6, 7))
        d.rectangle([0, y, W, y + SCALE * 3], fill=tuple(int(np.clip(v + tone, 0, 255)) for v in SILVER))
        d.line([0, y, W, y], fill=(150, 156, 162), width=max(1, SCALE // 2))
    for x in range(0, int(W * 0.09)):
        shade = int(40 + 30 * x / (W * 0.09))
        d.line([x, 0, x, H], fill=(shade, shade + 4, shade + 10))
    d.rectangle([int(W * 0.09), 0, int(W * 0.10), H], fill=(210, 214, 218))
    return im


def desert(size=64):
    """The desert and the dirt round the site (the orthophotos: tan ground with a little scrub)."""
    S = size * SCALE
    r = rng(83)
    n = _blur(r.random((S, S)), SCALE * 2)
    n = (n - n.min()) / max(1e-6, n.max() - n.min())
    a = np.zeros((S, S, 3), np.float32)
    for k, (lo, hi) in enumerate(zip((170, 150, 116), (196, 176, 140))):
        a[..., k] = lo + (hi - lo) * n
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def mountains(size=(128, 64)):
    """The White Tank Mountains and the ranges round the valley (f000, f001): hazy brown-grey ridges, lighter at the
    top edge, transparent over the ridge line (alpha)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(85)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = []
    for x in range(0, W + SCALE * 4, SCALE * 4):
        h = 0.25 + 0.55 * abs(np.sin(x / W * np.pi * 3.0)) + 0.15 * float(r.random())
        pts.append((x, int(H * (1.0 - min(0.95, h)))))
    d.polygon(pts + [(W, H), (0, H)], fill=(128, 118, 110, 255))
    return im


def logo_sign(size=(128, 64)):
    """The stadium's wordmark on the drum, the roof and the boards (f000, the orthophotos), cut from the Commons file on
    a transparent ground (alpha)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), SILVER + (0,))
    mark = _fit(_logo(), W, H, 0.92)
    im.alpha_composite(mark, ((W - mark.width) // 2, (H - mark.height) // 2))
    return im


def board_wing(size=(64, 128)):
    """The boards' side panels: black with the stat grid (the game's digits sit on them)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (10, 8, 10))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.12)], fill=CARDS["red"])
    for y in range(int(H * 0.2), H, int(H * 0.18)):
        d.line([SCALE * 2, y, W - SCALE * 2, y], fill=(50, 40, 44), width=SCALE)
    return im


def drawings():
    return {
        "sf_seat_front": (seat(0.04, 31), (64, 128)), "sf_seat_mid": (seat(0.08, 32), (64, 128)),
        "sf_seat_back": (seat(0.12, 33), (64, 128)),
        "sf_concrete": (base.concrete(), (64, 64)), "sf_wall": (wall(), (256, 32)),
        "LIGHT_sf_ribbon": (ribbon(), (256, 64)), "LIGHT_sf_glass": (base.glass(), (128, 64)),
        "LIGHT_sf_concourse": (base.concourse(), (128, 64)), "sf_portal": (base.vomitory(), (32, 32)),
        "sf_dark": (base.dark(), (32, 32)), "sf_black": (usb.black(), (32, 32)),
        "sf_fabric_under": (fabric_under(), (64, 64)), "sf_fabric_top": (fabric_top(), (64, 64)),
        "sf_panel_top": (panel_top(), (64, 32)), "sf_truss": (truss(), (64, 64)),
        "sf_panel_edge": (panel_edge(), (32, 32)), "sf_rib": (rib(), (32, 8)), "sf_inner": (inner(), (64, 64)),
        "LIGHT_sf_lights": (usb.lamps(), (64, 32)), "sf_drum": (drum(), (64, 128)),
        "LIGHT_sf_facade_glass": (usb.facade_glass(), (128, 64)), "sf_logo": (logo_sign(), (128, 64)),
        "LIGHT_sf_board_wing": (board_wing(), (64, 128)),
        "sf_plaza": (base.plaza(), (32, 32)), "sf_lawn": (usb.lawn(), (32, 32)), "sf_asphalt": (base.asphalt(), (32, 32)),
        "sf_road": (base.road(), (32, 32)), "sf_building": (base.building(), (32, 32)), "sf_desert": (desert(), (32, 32)),
        "sf_mountains": (mountains(), (64, 32)),
    }


def main(argv=None):
    global LOGO
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--logo", required=True, help="the Commons State Farm Stadium logo rendered to PNG (author time only)")
    ap.add_argument("--masters")
    a = ap.parse_args(argv)
    LOGO = a.logo
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    masters = Path(a.masters) if a.masters else None
    if masters:
        masters.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, (master, size) in drawings().items():
        native = reduce(master, size)
        path = out / f"{name}.png"
        native.save(path, optimize=True)
        manifest[name] = dict(size=list(size), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if masters:
            master.save(masters / f"{name}.png", optimize=True)
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_state_farm_model_art/v1", art=manifest), indent=1) + "\n")
    print("STATE_FARM_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
