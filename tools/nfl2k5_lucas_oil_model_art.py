#!/usr/bin/env python3
"""Lucas Oil Stadium model art (job st3): the textures the model draws, deterministic, at 4x masters reduced to their
native sizes.

The Colts' blue bowl (every seat blue), the field wall's pads, the loge and upper-suite ribbons (plain type), the gabled
roof (the two retractable panels on the axis, painted LUCAS OIL STADIUM in plain type as the orthophotos show it, and the
fixed roof either side) with its dark steel trusses from below, the north window (six glass panels in a steel frame,
see-through inside, reflective outside), the corner boards' wings, the brick and Indiana limestone of the fieldhouse
facade with its tall arched windows, the corner towers, and the stadium's own wordmark (Wikimedia Commons
File:Lucas_Oil_Stadium_logo.svg, a public-domain text logo, cut from the file and never redrawn). Downtown's towers, the
plaza, the lots, the roads and the sky reuse the U.S. Bank art's drawings.

    python3 tools/nfl2k5_lucas_oil_model_art.py OUT_DIR --logo LOGO.png [--masters DIR]
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
#: the Colts' colours (NFL Record and Fact Book: Speed Blue #002C5F, white, Gray #A2AAAD)
COLTS = dict(blue=(0, 44, 95), white=(255, 255, 255), gray=(162, 170, 173), royal=(0, 83, 160))
#: the seats as the photos show them under the stadium's light (l096, l137: a mid royal blue)
SEAT = (28, 58, 132)
BRICK = (128, 62, 44)
LIMESTONE = (214, 204, 182)
LOGO = None


def _logo():
    im = Image.open(LOGO).convert("RGBA")
    return im.crop(im.getbbox())


def seat(p_light, seed, size=(64, 128)):
    """One section per u repeat, 21 rows per v repeat (the retail convention), the aisle steps at u = 0; blue seats, a
    few lighter ones where the light catches them (``p_light``)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (22, 40, 92))
    d = ImageDraw.Draw(im)
    r = rng(seed)
    rows = 21
    rh = H / rows
    pitch = SCALE * 5
    cols = W // pitch
    for k in range(rows):
        y0 = int(k * rh)
        d.rectangle([0, y0, W, y0 + int(rh * 0.16)], fill=(150, 150, 152))
        d.rectangle([0, y0 + int(rh * 0.16), W, y0 + int(rh * 0.30)], fill=(14, 22, 48))
        for c in range(cols):
            x = c * pitch
            basec = (52, 92, 176) if r.random() < p_light else SEAT
            tone = int(r.integers(-6, 7))
            fill = tuple(int(np.clip(v + tone, 0, 255)) for v in basec)
            d.rectangle([x + SCALE, y0 + int(rh * 0.30), x + pitch - SCALE, y0 + int(rh * 0.94)], fill=fill)
    aisle = int(round(W * 0.16 / 2))
    for x0, x1 in ((0, aisle), (W - aisle, W)):
        d.rectangle([x0, 0, x1, H], fill=(156, 156, 154))
    for k in range(rows * 2):
        y = int(k * rh / 2)
        for x0, x1 in ((0, aisle), (W - aisle, W)):
            d.line([x0, y, x1, y], fill=(112, 112, 110), width=SCALE)
    return im


def wall(size=(256, 32)):
    """The field wall (l110 to l124: blue pads with white plain type, FOR THE SHOE and COLTS; the club's horseshoe is
    never drawn here)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), COLTS["blue"])
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.08)], fill=COLTS["white"])
    items = [_text("FOR THE SHOE", COLTS["white"]), _text("COLTS", COLTS["white"]), _text("INDIANAPOLIS", COLTS["white"]),
             _text("COLTS", COLTS["white"])]
    band = _row(items, W, int(H * 0.92), SCALE * 12, 0.56)
    im.paste(band, (0, int(H * 0.08)), band)
    return im


def ribbon(size=(256, 64)):
    """The ribbon boards (1,550 ft on the loge facade, 660 ft in the upper suites' corners; the stadium's own facts):
    two bands a texture, the club's words and the partners in plain type (l096, l137: FOR THE SHOE, COLTS, Verizon,
    Huntington; no partner logo is drawn)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (0, 0, 0))
    half = H // 2
    bands = [((6, 16, 40), [_text("FOR THE SHOE", COLTS["white"]), _text("COLTS", COLTS["gray"]),
                            _text("FOR THE SHOE", COLTS["white"]), _text("INDIANAPOLIS COLTS", COLTS["white"])]),
             (COLTS["blue"], [_text("VERIZON", COLTS["white"]), _text("HUNTINGTON", COLTS["white"]),
                              _text("LUCAS OIL", COLTS["white"]), _text("CAESARS", COLTS["white"])])]
    for k, (bg, items) in enumerate(bands):
        y0 = k * half
        ImageDraw.Draw(im).rectangle([0, y0, W, y0 + half], fill=bg)
        band = _row(items, W, half, SCALE * 10)
        im.paste(band, (0, y0), band)
    return im


def roof_under(size=64):
    """The roof from below (l096, l116, l117: a pale grey deck between dark steel purlins)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (150, 154, 160))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 4):
        d.rectangle([x, 0, x + SCALE * 2, S], fill=(62, 66, 72))
    for y in range(0, S, S // 8):
        d.line([0, y, S, y], fill=(120, 124, 130), width=SCALE)
    return im


def truss(size=64):
    """The roof's steel trusses (l096, l117, l137: dark grey lattices, the sky and the deck showing through): chords,
    posts and X bracing on a transparent ground (alpha)."""
    S = size * SCALE
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (72, 76, 82, 255)
    t = SCALE * 3
    d.rectangle([0, 0, S, t], fill=c)
    d.rectangle([0, S - t, S, S], fill=c)
    for x in (0, S // 2, S):
        d.rectangle([x - t // 2, 0, x + t // 2, S], fill=c)
    for k in (0, S // 2):
        d.line([k, 0, k + S // 2, S], fill=c, width=SCALE * 2)
        d.line([k + S // 2, 0, k, S], fill=c, width=SCALE * 2)
    return im


def panel_top(size=(128, 64)):
    """The two retractable panels from above (the orthophotos: pale grey standing seams along the slope, a darker seam
    every panel bay)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (178, 182, 186))
    d = ImageDraw.Draw(im)
    for x in range(0, W, SCALE * 3):
        d.line([x, 0, x, H], fill=(156, 160, 164), width=SCALE)
    for y in range(0, H, H // 4):
        d.rectangle([0, y, W, y + SCALE * 2], fill=(118, 122, 128))
    return im


def fixed_top(size=64):
    """The fixed roof either side of the panels (the orthophotos: a grey membrane crossed by the dark transverse trusses
    that rise over it)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (140, 144, 148))
    d = ImageDraw.Draw(im)
    for x in range(0, S, SCALE * 4):
        d.line([x, 0, x, S], fill=(128, 132, 136), width=SCALE)
    d.rectangle([0, int(S * 0.44), S, int(S * 0.56)], fill=(54, 58, 64))
    return im


def roof_letters(size=(256, 64)):
    """LUCAS OIL STADIUM painted on the east panel (the orthophotos: white plain capitals along the axis)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band = _row([_text("LUCAS OIL STADIUM", (244, 244, 246))], W, H, SCALE * 8, 0.8)
    im.paste(band, (0, 0), band)
    return im


def window(size=(128, 64), night=False):
    """The north window from inside (l095, l096): six tall panels, each a grid of lites in slim dark mullions, mostly
    transparent so downtown shows (alpha); by night dark and nearly clear, the mullions catching the light."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (18, 22, 30, 16) if night else (186, 206, 226, 52))
    d = ImageDraw.Draw(im)
    mullion = (108, 112, 120, 255) if night else (40, 44, 50, 255)
    for x in range(0, W, W // 12):
        d.rectangle([x, 0, x + SCALE, H], fill=mullion)
    for x in range(0, W, W // 6):
        d.rectangle([x - SCALE, 0, x + SCALE * 2, H], fill=mullion)
    for y in range(0, H, H // 6):
        d.rectangle([0, y, W, y + SCALE - 1], fill=mullion)
    return im


def window_frame(size=64):
    """The window's steel frame and the dark wall round it (l096)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), (44, 48, 54))
    d = ImageDraw.Draw(im)
    for x in range(0, S, S // 4):
        d.rectangle([x, 0, x + SCALE * 2, S], fill=(70, 74, 80))
    return im


def brick(size=(128, 128)):
    """The fieldhouse facade (l035 to l049): red-brown brick in courses with a limestone band every storey."""
    W, H = size[0] * SCALE, size[1] * SCALE
    r = rng(71)
    im = Image.new("RGB", (W, H), BRICK)
    d = ImageDraw.Draw(im)
    ch = SCALE * 2
    for k, y in enumerate(range(0, H, ch)):
        off = (k % 2) * SCALE * 3
        for x in range(-off, W, SCALE * 6):
            tone = int(r.integers(-10, 11))
            d.rectangle([x + 1, y + 1, x + SCALE * 6 - 1, y + ch - 1],
                        fill=tuple(int(np.clip(v + tone, 0, 255)) for v in BRICK))
        d.line([0, y, W, y], fill=(170, 160, 146), width=max(1, SCALE // 2))
    for y in (0, H // 2):
        d.rectangle([0, y, W, y + SCALE * 4], fill=LIMESTONE)
    return im


def arch_windows(size=(128, 128)):
    """The tall arched windows in the brick (l035 to l049): dark reflective glass in a limestone surround with a round
    head, two a texture repeat."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), BRICK)
    d = ImageDraw.Draw(im)
    for k in range(2):
        x0 = int(W * (0.06 + 0.5 * k))
        x1 = int(W * (0.44 + 0.5 * k))
        top = int(H * 0.18)
        d.rectangle([x0 - SCALE * 2, top, x1 + SCALE * 2, H], fill=LIMESTONE)
        d.ellipse([x0 - SCALE * 2, top - (x1 - x0) // 2 - SCALE * 2, x1 + SCALE * 2, top + (x1 - x0) // 2], fill=LIMESTONE)
        d.rectangle([x0, top, x1, H], fill=(70, 86, 104))
        d.ellipse([x0, top - (x1 - x0) // 2, x1, top + (x1 - x0) // 2], fill=(70, 86, 104))
        for gx in np.linspace(x0, x1, 5)[1:-1]:
            d.line([gx, top - (x1 - x0) // 2, gx, H], fill=(40, 44, 50), width=SCALE)
        for gy in range(top, H, SCALE * 8):
            d.line([x0, gy, x1, gy], fill=(40, 44, 50), width=SCALE)
    return im


def tower_cap(size=64):
    """The corner towers' limestone tops and the mechanical louvres (the orthophotos, l048, l056)."""
    S = size * SCALE
    im = Image.new("RGB", (S, S), LIMESTONE)
    d = ImageDraw.Draw(im)
    for y in range(0, S, SCALE * 3):
        d.line([0, y, S, y], fill=(168, 160, 144), width=SCALE)
    return im


def logo_sign(size=(128, 64)):
    """The stadium's wordmark on the facades and over the north window (l040, l041, l096), cut from the Commons file on
    a transparent ground (alpha)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mark = _fit(_logo(), W, H, 0.92)
    im.paste(mark, ((W - mark.width) // 2, (H - mark.height) // 2), mark)
    return im


def board_wing(size=(64, 128)):
    """The auxiliary boards and the wings of the two main boards: black with the stat grid (the game's digits sit on
    them)."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), (8, 10, 16))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.12)], fill=COLTS["blue"])
    for y in range(int(H * 0.2), H, int(H * 0.18)):
        d.line([SCALE * 2, y, W - SCALE * 2, y], fill=(40, 46, 60), width=SCALE)
    return im


def banners(size=(128, 128)):
    """The Colts' championship banners hung from the roof (l096, l137): blue cloths with a white border and the year and
    title in white plain type (the horseshoe is never drawn here), four a texture."""
    W, H = size[0] * SCALE, size[1] * SCALE
    im = Image.new("RGB", (W, H), COLTS["blue"])
    d = ImageDraw.Draw(im)
    titles = (("2006", "WORLD CHAMPIONS"), ("2009", "AFC CHAMPIONS"), ("2014", "AFC SOUTH"), ("2023", "COLTS"))
    q = W // 4
    for k, (year, title) in enumerate(titles):
        x0 = k * q
        d.rectangle([x0 + SCALE * 2, SCALE * 2, x0 + q - SCALE * 2, H - SCALE * 2], outline=COLTS["white"], width=SCALE * 2)
        col = Image.new("RGBA", (q, H), (0, 0, 0, 0))
        top = _row([_text(year, COLTS["white"])], q, H // 3, SCALE * 4, 0.7)
        col.paste(top, (0, H // 10), top)
        low = _row([_text(title, COLTS["white"])], q, H // 5, SCALE * 3, 0.6)
        col.paste(low, (0, int(H * 0.55)), low)
        im.paste(col, (x0, 0), col)
    return im


def drawings():
    return {
        "los_seat_front": (seat(0.04, 21), (64, 128)), "los_seat_mid": (seat(0.08, 22), (64, 128)),
        "los_seat_back": (seat(0.12, 23), (64, 128)),
        "los_concrete": (base.concrete(), (64, 64)), "los_wall": (wall(), (256, 32)),
        "LIGHT_los_ribbon": (ribbon(), (256, 64)), "LIGHT_los_glass": (base.glass(), (128, 64)),
        "LIGHT_los_concourse": (base.concourse(), (128, 64)), "los_portal": (base.vomitory(), (32, 32)),
        "los_dark": (base.dark(), (32, 32)), "los_black": (usb.black(), (32, 32)),
        "los_roof_under": (roof_under(), (64, 64)), "los_truss": (truss(), (64, 64)),
        "los_panel_top": (panel_top(), (128, 64)), "los_fixed_top": (fixed_top(), (64, 64)),
        "los_roof_letters": (roof_letters(), (128, 32)),
        "LIGHT_los_lights": (usb.lamps(), (64, 32)),
        "LIGHT_los_window": (window(), (128, 64)), "LIGHT_los_window_n": (window(night=True), (128, 64)),
        "los_window_frame": (window_frame(), (64, 64)),
        "LIGHT_los_facade_glass": (usb.facade_glass(), (128, 64)),
        "los_brick": (brick(), (64, 64)), "los_arch_windows": (arch_windows(), (64, 64)),
        "los_tower_cap": (tower_cap(), (64, 64)), "los_logo": (logo_sign(), (128, 64)),
        "LIGHT_los_board_wing": (board_wing(), (64, 128)), "los_banners": (banners(size=(128, 64)), (128, 64)),
        "LIGHT_los_clerestory": (usb.clerestory(), (64, 64)), "LIGHT_los_clerestory_n": (usb.clerestory(night=True), (64, 64)),
        "los_flag": (usb.flag(), (64, 32)),
        "los_plaza": (base.plaza(), (32, 32)), "los_lawn": (usb.lawn(), (32, 32)), "los_asphalt": (base.asphalt(), (32, 32)),
        "los_road": (base.road(), (32, 32)), "los_building": (base.building(), (32, 32)),
        "LIGHT_los_towers": (usb.towers(), (64, 64)), "LIGHT_los_towers_n": (usb.towers(night=True), (64, 64)),
        "los_sky_d": (usb.sky("d"), (128, 64)), "los_sky_a": (usb.sky("a"), (128, 64)), "los_sky_n": (usb.sky("n"), (128, 64)),
    }


def main(argv=None):
    global LOGO
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--logo", required=True, help="the Commons Lucas Oil Stadium logo rendered to PNG (author time only)")
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
    (out / "art.json").write_text(json.dumps(dict(schema="nfl2k5_lucas_oil_model_art/v1", art=manifest), indent=1) + "\n")
    print("LUCAS_OIL_ART_OK", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
