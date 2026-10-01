#!/usr/bin/env python3
"""Draw the practice facility model's art (job pf, 2026-09-27): deterministic, procedural, plain type only.

  python3 tools/nfl2k5_practice_field_model_art.py OUT_DIR [--masters MASTER_DIR]

Every texture is drawn at 4x its game size and reduced (the 4x drawings are the 2K5 Edition pack's masters). Nothing is
generated with an image model and no mark is drawn: the facility is shared by all 32 teams. The midfield's current NFL
shield is not drawn here and never ships: the Build takes it from the 2026 venue art folder's league marks
(``nfl2k5_practice_field_model.midfield_art``), and without that folder the field keeps the game's own mark. Tones
follow the reference photos (Wikimedia Commons, listed in the pf report): the white metal
walls and trusses of the Ravens' and Seahawks' indoor field houses, the glass fronts of Halas Hall and the Dolphins'
Baptist Health Training Complex, the dark windscreens of the 49ers' and Chargers' camps, the yellow goalposts, the
aluminium bleachers of the Eagles' and Giants' camps, the black blocking-sled pads (the Broncos' camp), and natural
grass mown in 5-yard bands.

The trees, the ground grass, the parking lots and the horizon are not drawn here: the model takes them from the
retail cityscape of the same bundle at build time (the user's own game data; native first).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"
SCALE = 4

#: natural grass (Kentucky bluegrass, the practice fields of the references) in two mown tones, and synthetic turf. The
#: stadium scene draws texture x vertex colour, so the side fields aim at the main field's on-screen colour (job tf's G-A
#: day target (88, 110, 64)) through the model's baked light (214/255): a mean of about (105, 131, 76) (DESIGN)
GRASS_LIGHT, GRASS_DARK = (114, 140, 82), (96, 122, 70)
TURF_LIGHT, TURF_DARK = (100, 130, 74), (90, 118, 68)
PAINT = (236, 238, 234)
#: the NFL's goalposts are bright gold (the practice fields in the references: yellow single-post goalposts)
GOAL_YELLOW = (246, 202, 28)
#: a field is 53 1/3 yards wide; the hash marks sit 70 ft 9 in from each sideline (NFL rule 1, section 2)
FIELD_W = 48.768
HASH_FROM_SIDELINE = 21.5646


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


def _noise(shape, seed, radius=2, cell=4):
    """Smooth value noise in [0, 1] (tileable: the blur wraps)."""
    H, W = shape
    r = rng(seed)
    n = _blur(r.random((max(1, H // cell), max(1, W // cell))), radius)
    n = np.kron((n - n.min()) / max(1e-6, float(n.max() - n.min())), np.ones((cell, cell)))
    return n[:H, :W]


def reduce(master, size):
    return master.resize(size, Image.LANCZOS)


def font(px):
    return ImageFont.truetype(FONT, px)


def _rgb(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


# --- fields -------------------------------------------------------------------------------------------------------

def _grass(W, H, light, dark, seed, bands=True, split=0.5):
    """Grass in two mown tones: the first ``split`` of the height light, the rest dark (v runs along the field), a fine
    blade grain on top."""
    a = np.zeros((H, W, 3), np.float32)
    top = int(round(H * split))
    a[:top] = np.array(light, np.float32)
    a[top:] = np.array(dark if bands else light, np.float32)
    grain = _noise((H, W), seed, radius=1, cell=2)
    streak = _noise((H, W), seed + 1, radius=3, cell=8)
    a *= (0.93 + 0.08 * grain + 0.04 * streak)[..., None]
    return a


def _lines(im, *, yard_rows, hashes=True, ticks=True):
    """Paint the yard lines (full width) at the given rows and the hash marks and sideline ticks every yard between
    them (u across the field, v along it; 10 yards per texture)."""
    W, H = im.size
    d = ImageDraw.Draw(im)
    per_yd = H / 10.0
    line = max(2, int(round(per_yd * 0.1016 / 0.9144)))          # 4 in wide
    for y in yard_rows:
        d.rectangle([0, int(y), W, int(y) + line], fill=PAINT)
    u_hash = HASH_FROM_SIDELINE / FIELD_W
    hash_w = int(round(W * 0.6096 / FIELD_W))                    # 2 ft long
    tick_w = int(round(W * 0.6096 / FIELD_W))
    for yd in range(10):
        y = int(round(yd * per_yd))
        if any(abs(y - r) < 2 for r in yard_rows):
            continue
        if hashes:
            for u in (u_hash, 1 - u_hash):
                x = int(round(u * W))
                d.rectangle([x - hash_w // 2, y, x + hash_w // 2, y + line], fill=PAINT)
        if ticks:
            for x0 in (int(W * 0.004), W - int(W * 0.004) - tick_w):
                d.rectangle([x0, y, x0 + tick_w, y + line], fill=PAINT)


def field_strip(size=(64, 128)):
    """Ten yards of a natural-grass practice field: two 5-yard mowing bands, the yard lines at 0 and 5, the hash marks
    and sideline ticks every yard (u across 53 1/3 yards, v along 10 yards)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = _rgb(_grass(W, H, GRASS_LIGHT, GRASS_DARK, 11))
    _lines(im, yard_rows=(0, H // 2))
    return im


def turf_strip(size=(64, 128)):
    """Ten yards of a synthetic practice field (TCO's and the Steelers' outdoor synthetic fields): the rolls' two tones,
    the same lines."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = _grass(W, H, TURF_LIGHT, TURF_DARK, 13)
    fibre = _noise((H, W), 14, radius=1, cell=1)
    a *= (0.96 + 0.06 * fibre)[..., None]
    im = _rgb(a)
    _lines(im, yard_rows=(0, H // 2))
    return im


def endzone_grass(size=64):
    """A side field's end zone: plain grass, no paint (the practice fields in the references)."""
    S = size * SCALE
    return _rgb(_grass(S, S, GRASS_LIGHT, GRASS_DARK, 17, bands=False))


def endzone_turf(size=64):
    S = size * SCALE
    return _rgb(_grass(S, S, TURF_LIGHT, TURF_DARK, 19, bands=False))


def paint(size=8):
    S = size * SCALE
    return Image.new("RGB", (S, S), PAINT)


def field_numbers(size=(128, 256)):
    """The side fields' yard numbers, 10 to 50, one per row of five (plain condensed type, white on a transparent ground;
    on the field 6 ft tall, their bottoms toward the sideline, NFL rule 1)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    row = H / 5
    px = int(row * 0.95)
    f = font(px)
    while max(d.textlength(t, font=f) for t in ("10", "20", "30", "40", "50")) > W * 0.86 and px > 8:
        px -= 2
        f = font(px)
    for k, text in enumerate(("10", "20", "30", "40", "50")):
        w = d.textlength(text, font=f)
        bbox = d.textbbox((0, 0), text, font=f)
        th = bbox[3] - bbox[1]
        d.text((int((W - w) / 2), int(k * row + (row - th) / 2 - bbox[1])), text, font=f, fill=PAINT + (255,))
    return im


def clear(size=(128, 128)):
    """A fully transparent overlay (the conference shields and the playoff mark: no practice field carries them)."""
    return Image.new("RGBA", (size[0] * SCALE, size[1] * SCALE), (0, 0, 0, 0))


# --- walks, buildings ---------------------------------------------------------------------------------------------

def path(size=32):
    """The walkways between the fields: light concrete with saw-cut joints."""
    S = size * SCALE
    n = _noise((S, S), 23, radius=1, cell=2)
    a = np.dstack([176 + 14 * n, 176 + 14 * n, 170 + 14 * n])
    im = _rgb(a)
    d = ImageDraw.Draw(im)
    for k in (0, S // 2):
        d.line([0, k, S, k], fill=(140, 140, 136), width=SCALE)
    return im


def fh_wall(size=(128, 64)):
    """The indoor field house's walls (the Ravens' and Seahawks' field houses, R06 and R14 to R18): white ribbed metal
    panels over a dark base band; u one panel run of 12 m, v the wall up to the clerestory (the base the lowest fifth)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    a[:] = (224, 226, 228)
    x = np.arange(W)
    rib = ((x % (SCALE * 3)) < SCALE).astype(np.float32)
    a *= (1.0 - 0.10 * rib)[None, :, None]
    seam = ((x % (W // 4)) < SCALE).astype(np.float32)
    a *= (1.0 - 0.22 * seam)[None, :, None]
    base = int(H * 0.80)
    a[base:] = (74, 78, 84)
    a[base:base + SCALE] = (150, 152, 156)
    a *= (0.97 + 0.04 * _noise((H, W), 29, radius=2, cell=4))[..., None]
    return _rgb(a)


def clerestory(size=(64, 32), lit=False):
    """The field house's translucent clerestory band (UPMC's and the Ravens' field houses: a band of translucent panels
    under the eaves), glowing warm white at night."""
    W, H = size[0] * SCALE, size[1] * SCALE
    fill = (252, 246, 226) if lit else (196, 206, 214)
    im = Image.new("RGB", (W, H), fill)
    d = ImageDraw.Draw(im)
    frame = (120, 124, 130) if not lit else (150, 146, 136)
    for x in range(0, W, W // 8):
        d.rectangle([x, 0, x + SCALE, H], fill=frame)
    for y in (0, H // 2, H - SCALE):
        d.rectangle([0, y, W, y + SCALE], fill=frame)
    return im


def fh_roof(size=64):
    """The field house roof: light-grey standing-seam metal, the seams running down the slope (v)."""
    S = size * SCALE
    a = np.zeros((S, S, 3), np.float32)
    a[:] = (176, 180, 184)
    x = np.arange(S)
    a *= (1.0 - 0.12 * ((x % (SCALE * 4)) < SCALE))[None, :, None]
    a *= (0.96 + 0.05 * _noise((S, S), 31, radius=2, cell=4))[..., None]
    return _rgb(a)


def door(size=64):
    """A roll-up door: grey horizontal slats in a dark frame."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (150, 154, 158))
    d = ImageDraw.Draw(im)
    for y in range(0, S, SCALE * 3):
        d.line([0, y, S, y], fill=(118, 122, 126), width=SCALE)
    d.rectangle([0, 0, S, SCALE * 2], fill=(52, 54, 58))
    d.rectangle([0, 0, SCALE * 2, S], fill=(52, 54, 58))
    d.rectangle([S - SCALE * 2, 0, S, S], fill=(52, 54, 58))
    return im


def curtain(size=(128, 128), lit=False):
    """The headquarters' glass front (Halas Hall's entrance, R03; the Dolphins' complex, R00): one storey per v repeat,
    eight 0.75 m panes per u repeat between slim dark mullions, a thin light slab edge at the floor line; blue-grey
    glass by day with a soft sky reflection per pane (no gradient across the storey, so the storeys do not band), the
    offices lit warm at night with some panes dark."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    r = rng(38 if lit else 39)
    panes = 8
    pw = W / panes
    slab = int(H * 0.08)
    for k in range(panes):
        x0, x1 = int(k * pw), int((k + 1) * pw)
        if lit:
            on = r.random() < 0.78
            base = np.array([222, 204, 160] if on else [44, 44, 50], np.float32)
            tone = 0.88 + 0.18 * r.random()
        else:
            base = np.array([70, 88, 106], np.float32)
            tone = 0.90 + 0.16 * r.random()
        a[:, x0:x1] = base * tone
        if not lit:
            # a faint diagonal sheen of the sky in each pane
            yy, xx = np.mgrid[0:H, x0:x1]
            sheen = np.clip(1.0 - np.abs((xx - x0) * 1.6 + yy * 0.35 - pw * 0.8) / (pw * 0.9), 0, 1) * 0.16
            a[:, x0:x1] *= (1.0 + sheen)[..., None]
    a[:slab] = (196, 198, 200) if not lit else (120, 118, 112)
    for k in range(panes + 1):
        x = int(k * pw)
        a[:, max(0, x - SCALE // 2):x + SCALE // 2] = (48, 52, 58)
    a[int(H * 0.55):int(H * 0.55) + SCALE // 2] = (58, 62, 68)
    return _rgb(a)


def stone(size=64):
    """Light warm-grey stone panels (the headquarters' base and side walls)."""
    S = size * SCALE
    n = _noise((S, S), 41, radius=2, cell=4)
    a = np.dstack([196 + 12 * n, 190 + 12 * n, 178 + 12 * n])
    im = _rgb(a)
    d = ImageDraw.Draw(im)
    for k in (0, S // 2):
        d.line([0, k, S, k], fill=(160, 154, 144), width=SCALE)
    for k in (0, S // 3, 2 * S // 3):
        d.line([k, 0, k, S], fill=(160, 154, 144), width=SCALE)
    return im


def flat(colour, size=32):
    S = size * SCALE
    return Image.new("RGB", (S, S), colour)


def steel(size=32):
    S = size * SCALE
    n = _noise((S, S), 43, radius=1, cell=2)
    return _rgb(np.dstack([150 + 16 * n, 154 + 16 * n, 158 + 16 * n]))


def led(size=32, lit=False):
    """An LED floodlight head: a grid of emitters, grey by day, white at night."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (40, 42, 46))
    d = ImageDraw.Draw(im)
    c = (255, 252, 240) if lit else (176, 180, 186)
    step = S // 4
    for i in range(4):
        for j in range(4):
            d.rectangle([i * step + SCALE, j * step + SCALE, (i + 1) * step - SCALE, (j + 1) * step - SCALE], fill=c)
    return im


def windscreen(size=(128, 32)):
    """The perimeter fence: dark green windscreen mesh on a chain-link fence (the 49ers' and Chargers' camps, R08 to R10,
    R23 to R27; no marks), a galvanised post every 3 m (u runs 12 m), the top rail along the top (v 0 at the top)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    a[:] = (30, 46, 38)
    weave = _noise((H, W), 47, radius=1, cell=1)
    a *= (0.88 + 0.20 * weave)[..., None]
    fold = _noise((H, W), 48, radius=4, cell=16)
    a *= (0.92 + 0.12 * fold)[..., None]
    a[:SCALE * 2] = (164, 168, 172)
    for k in range(4):
        x = int(k * W / 4)
        a[:, max(0, x - SCALE):x + SCALE] = (150, 154, 158)
    return _rgb(a)


def scissor(size=64):
    """The filming tower's scissor lift (UPMC's viewing towers; the scissor lifts at every NFL practice): two grey X
    braces on a transparent ground (alpha-tested), one stage per v repeat."""
    S = size * SCALE
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (176, 180, 184, 255)
    w = SCALE * 3
    d.line([0, 0, S, S], fill=c, width=w)
    d.line([0, S, S, 0], fill=c, width=w)
    d.ellipse([S // 2 - SCALE * 3, S // 2 - SCALE * 3, S // 2 + SCALE * 3, S // 2 + SCALE * 3], fill=(60, 62, 66, 255))
    return im


def bleacher(size=(64, 64)):
    """Aluminium bleachers (the Eagles' and Giants' camps, R07, R13): ten rows per v repeat, each a bright seat plank, a
    darker footboard and the shadow gap between them; u runs 6 m."""
    W, H = size[0] * SCALE, size[1] * SCALE
    a = np.zeros((H, W, 3), np.float32)
    rows = 10
    rh = H / rows
    for k in range(rows):
        y0 = int(k * rh)
        a[y0:y0 + int(rh * 0.30)] = (206, 210, 214)
        a[y0 + int(rh * 0.30):y0 + int(rh * 0.42)] = (60, 62, 66)
        a[y0 + int(rh * 0.42):y0 + int(rh * 0.78)] = (168, 172, 176)
        a[y0 + int(rh * 0.78):int((k + 1) * rh)] = (40, 42, 46)
    a *= (0.96 + 0.05 * _noise((H, W), 53, radius=1, cell=2))[..., None]
    return _rgb(a)


def canvas(size=32):
    S = size * SCALE
    n = _noise((S, S), 59, radius=2, cell=4)
    return _rgb(np.dstack([232 + 10 * n, 232 + 10 * n, 228 + 10 * n]))


def pad(size=64):
    """A blocking-sled pad (the Broncos' camp, R12): black vinyl with grey seams, no marks."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (22, 23, 25))
    d = ImageDraw.Draw(im)
    for k in (S // 8, S - S // 8):
        d.line([0, k, S, k], fill=(78, 80, 84), width=SCALE)
        d.line([k, 0, k, S], fill=(78, 80, 84), width=SCALE)
    return im


def clock_face(size=(128, 64)):
    """A portable practice scoreboard's face: black, with the labels in plain type; the game's own digits sit in the
    windows (the model places them)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (10, 10, 12))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W - 1, H - 1], outline=(96, 98, 102), width=SCALE * 2)
    f = font(int(H * 0.11))
    for text, x, y in (("PERIOD TIME", 0.50, 0.06), ("HOME", 0.19, 0.64), ("PLAY", 0.50, 0.64), ("AWAY", 0.81, 0.64)):
        w = d.textlength(text, font=f)
        d.text((int(W * x - w / 2), int(H * y)), text, font=f, fill=(236, 236, 232))
    return im


# --- the catalogue ------------------------------------------------------------------------------------------------

def drawings():
    """{name: (master image, native size)}; ``_night`` names are the night bundles' variants of the LIGHT_ textures."""
    return {
        "pf_field_strip": (field_strip(), (64, 128)), "pf_turf_strip": (turf_strip(), (64, 128)),
        "pf_endzone_grass": (endzone_grass(), (64, 64)), "pf_endzone_turf": (endzone_turf(), (64, 64)),
        "pf_paint": (paint(), (8, 8)), "pf_path": (path(), (32, 32)),
        "pf_fh_wall": (fh_wall(), (128, 64)), "LIGHT_pf_clere": (clerestory(), (64, 32)),
        "LIGHT_pf_clere_night": (clerestory(lit=True), (64, 32)), "pf_fh_roof": (fh_roof(), (64, 64)),
        "pf_door": (door(), (64, 64)), "LIGHT_pf_glass": (curtain(), (128, 128)),
        "LIGHT_pf_glass_night": (curtain(lit=True), (128, 128)), "pf_stone": (stone(), (64, 64)),
        "pf_white": (flat((236, 236, 232)), (32, 32)), "pf_roof": (flat((150, 152, 150)), (32, 32)),
        "pf_steel": (steel(), (32, 32)), "pf_dark": (flat((34, 36, 40)), (32, 32)),
        "pf_yellow": (flat(GOAL_YELLOW), (32, 32)), "LIGHT_pf_led": (led(), (32, 32)),
        "LIGHT_pf_led_night": (led(lit=True), (32, 32)), "pf_windscreen": (windscreen(), (128, 32)),
        "pf_scissor": (scissor(), (64, 64)), "pf_bleacher": (bleacher(), (64, 64)), "pf_canvas": (canvas(), (32, 32)),
        "pf_pad": (pad(), (64, 64)), "pf_clock": (clock_face(), (128, 64)), "pf_numbers": (field_numbers(), (64, 128)),
        "field/pf_clear": (clear(), (128, 128)),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--masters")
    a = ap.parse_args(argv)
    out = Path(a.out)
    (out / "field").mkdir(parents=True, exist_ok=True)
    masters = Path(a.masters) if a.masters else None
    if masters:
        (masters / "field").mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, (master, size) in drawings().items():
        native = reduce(master, size)
        p = out / f"{name}.png"
        native.save(p, optimize=True)
        manifest[name] = dict(size=list(size), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        if masters:
            master.save(masters / f"{name}.png", optimize=True)
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_practice_field_model_art/v1", art=manifest),
                                             indent=2, sort_keys=True) + "\n")
    print("PRACTICE_FIELD_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
