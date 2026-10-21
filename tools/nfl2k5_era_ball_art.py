#!/usr/bin/env python3
"""The modern game ball (job me1, N15): Wilson's "The Duke" design, drawn on the retail ball's UV layout.

The retail ball texture (256 x 256) wraps four leather panels round the ball as vertical strips (seams at x = 4.5,
66.5, 127.5, 189.5 and 250.5, the panel tips at the top and bottom rows) with the laces across the panel 1 / panel 2
seam (x 57-77, y 84-171); lettering on both sides of the laces faces the laces. This tool redraws that layout from
measurements only (no retail texel is used): pebbled leather, seams, tips and laces, then the modern marks: the
gold Wilson script left of the laces; right of the laces the eight-star league shield, THE DUKE and the commissioner's
line (a generic signature stroke, not a likeness of a real signature). Drawn at 4x and reduced. The PNG's alpha
marks the laces and marks (255) against plain leather (0): at build time plain leather that is also plain leather on
the user's own ball takes the disc's texel, so both designs share one leather and one index image stays compact.

    python3 tools/nfl2k5_era_ball_art.py OUT_DIR [--master PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 4
N = 256
SEAMS = (4.5, 66.5, 127.5, 189.5, 250.5)
LACE = dict(x0=57, x1=77, y0=84, y1=171)
LEATHER = (112, 54, 34)
SEAM = (54, 25, 15)
GOLD = (214, 168, 66)
INK = (24, 14, 10)
SANS = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"
SCRIPT = "/usr/share/fonts/opentype/urw-base35/Z003-MediumItalic.otf"


def font(path, px):
    return ImageFont.truetype(path, max(4, int(px)))


def word(text, path, px, fill, stroke=0, stroke_fill=INK):
    f = font(path, px)
    box = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f, stroke_width=stroke)
    im = Image.new("RGBA", (box[2] - box[0] + 8, box[3] - box[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - box[0], 4 - box[1]), text, font=f, fill=fill + (255,), stroke_width=stroke,
                            stroke_fill=stroke_fill + (255,))
    return im.crop(im.getbbox())


def fit(im, w, h):
    f = min(w / im.width, h / im.height)
    return im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))), Image.LANCZOS)


def place(canvas, im, cx, cy):
    canvas.alpha_composite(im, (int(cx * S - im.width / 2), int(cy * S - im.height / 2)))


def leather():
    """Pebbled leather: the base colour, a soft roll across each panel and a dense field of small pebbles."""
    W = N * S
    x = (np.arange(W) + 0.5) / S
    roll = np.ones(W)
    for a, b in zip(SEAMS[:-1], SEAMS[1:]):
        inside = (x >= a) & (x < b)
        t = (x[inside] - a) / (b - a)
        roll[inside] = 0.90 + 0.12 * np.sin(t * math.pi)
    rgb = np.asarray(LEATHER, float)[None, None] * roll[None, :, None] * np.ones((W, 1, 1))
    rng = np.random.default_rng(2006)
    pebble = np.zeros((W, W), float)
    count = 52000
    px, py = rng.uniform(0, W, count), rng.uniform(0, W, count)
    r = rng.uniform(1.4, 2.4, count)
    im = Image.new("L", (W, W), 0)
    d = ImageDraw.Draw(im)
    for cx, cy, rr in zip(px, py, r):
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=255)
    hi = np.asarray(im.filter(ImageFilter.GaussianBlur(0.9)), float) / 255
    lo = np.asarray(im.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.8)), float) / 255
    pebble = 0.10 * hi - 0.13 * (lo - hi).clip(0)
    rgb = rgb * (1 + pebble[..., None])
    return Image.fromarray(np.dstack([rgb.clip(0, 255).astype(np.uint8), np.full((W, W), 255, np.uint8)]), "RGBA")


def seams(canvas):
    """The panel seams and tips as soft pressed lines (half-strength over the leather)."""
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x in SEAMS:
        d.line([(x * S, 0), (x * S, N * S)], fill=SEAM + (150,), width=int(1.3 * S))
    for a, b in zip(SEAMS[:-1], SEAMS[1:]):
        c = (a + b) / 2
        for y0, y1 in ((22, 3), (234, 253)):
            d.line([(a * S, y0 * S), (c * S, y1 * S), (b * S, y0 * S)], fill=SEAM + (130,), width=int(1.1 * S),
                   joint="curve")
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.8 * S / 2)))


def laces(canvas):
    d = ImageDraw.Draw(canvas)
    L = LACE
    d.rounded_rectangle([L["x0"] * S, L["y0"] * S, L["x1"] * S, L["y1"] * S], radius=8 * S, fill=(50, 23, 14, 255))
    cx = (L["x0"] + L["x1"]) / 2
    white, shade = (238, 234, 224), (176, 170, 160)
    rungs = 8
    for k in range(rungs):
        y = 93 + k * (70 / (rungs - 1))
        d.rounded_rectangle([(L["x0"] + 2.5) * S, (y - 2.6) * S, (L["x1"] - 2.5) * S, (y + 2.6) * S], radius=2 * S,
                            fill=white + (255,))
        d.line([((L["x0"] + 3) * S, (y + 2.0) * S), ((L["x1"] - 3) * S, (y + 2.0) * S)], fill=shade + (255,),
               width=S)
    d.rounded_rectangle([(cx - 2.2) * S, 88 * S, (cx + 2.2) * S, 167 * S], radius=int(1.5 * S), fill=white + (255,))
    for k in range(rungs - 1):
        y = 93 + (k + 0.5) * (70 / (rungs - 1))
        d.line([((cx - 2.2) * S, y * S), ((cx + 2.2) * S, y * S)], fill=shade + (255,), width=S)


def shield(H):
    """The league shield from 2008 (eight stars): navy crown with a football, white field with NFL, red rule."""
    W = int(H * 0.82)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    outer = [(0, 0), (W * 0.5, H * 0.07), (W, 0), (W, H * 0.62), (W * 0.5, H), (0, H * 0.62)]
    d.polygon(outer, fill=(255, 255, 255, 255))
    navy, red = (1, 51, 105), (213, 10, 10)
    s = H * 0.06
    inner = [(s, s * 1.2), (W * 0.5, H * 0.07 + s), (W - s, s * 1.2), (W - s, H * 0.6), (W * 0.5, H - s * 1.6),
             (s, H * 0.6)]
    d.polygon(outer, outline=navy + (255,), width=max(1, int(s)))
    crown = Image.new("L", (W, H), 0)
    ImageDraw.Draw(crown).polygon(inner, fill=255)
    cut = Image.new("L", (W, H), 0)
    ImageDraw.Draw(cut).rectangle([0, 0, W, H * 0.34], fill=255)
    im.paste(navy + (255,), (0, 0), Image.fromarray(np.minimum(np.asarray(crown), np.asarray(cut))))
    for k in range(8):
        x = W * (0.16 + 0.68 * (k + 0.5) / 8)
        r = H * 0.03
        d.regular_polygon((x, H * 0.24, r), 5, fill=(255, 255, 255, 255))
    d.ellipse([W * 0.38, H * 0.07, W * 0.62, H * 0.17], fill=(124, 76, 42, 255))
    d.line([(W * 0.16, H * 0.37), (W * 0.84, H * 0.37)], fill=red + (255,), width=max(1, int(H * 0.03)))
    nfl = fit(word("NFL", SANS, H, navy), W * 0.66, H * 0.36)
    im.alpha_composite(nfl, (int(W / 2 - nfl.width / 2), int(H * 0.58 - nfl.height / 2)))
    return im


def signature(w, h):
    """A generic flowing pen stroke over COMMISSIONER (not a real signature)."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = []
    for k in range(120):
        t = k / 119
        x = w * (0.04 + 0.92 * t)
        y = h * (0.34 + 0.16 * math.sin(t * math.tau * 3.2) * (1 - 0.5 * t) - 0.10 * math.sin(t * math.pi))
        pts.append((x, y))
    d.line(pts, fill=INK + (255,), width=max(2, h // 18), joint="curve")
    d.line([(w * 0.10, h * 0.58), (w * 0.86, h * 0.52)], fill=INK + (255,), width=max(1, h // 26))
    small = fit(word("COMMISSIONER", SANS, h, INK), w * 0.64, h * 0.20)
    im.alpha_composite(small, (int(w * 0.5 - small.width / 2), int(h * 0.74)))
    return im


def marks(canvas):
    # Left of the laces (letter tops toward the laces, +x): the gold Wilson script and the league line.
    wilson = word("Wilson", SCRIPT, 60 * S, GOLD, stroke=int(1.1 * S))
    place(canvas, fit(wilson, 80 * S, 22 * S).rotate(-90, expand=True, resample=Image.BICUBIC), 43, 128)
    league = fit(word("NATIONAL FOOTBALL LEAGUE", SANS, 20 * S, INK), 66 * S, 5 * S)
    place(canvas, league.rotate(-90, expand=True, resample=Image.BICUBIC), 24, 128)
    # Right of the laces (letter tops toward the laces, -x): THE DUKE, the shield and the commissioner's line.
    duke = fit(word("THE DUKE", SANS, 40 * S, INK), 56 * S, 15 * S)
    place(canvas, duke.rotate(90, expand=True, resample=Image.BICUBIC), 99, 180)
    sh = shield(40 * S).rotate(90, expand=True, resample=Image.BICUBIC)
    place(canvas, sh, 101, 126)
    sig = signature(46 * S, 18 * S).rotate(90, expand=True, resample=Image.BICUBIC)
    place(canvas, sig, 101, 72)


def draw():
    """(RGBA master, L mask of the laces and marks)."""
    canvas = leather()
    seams(canvas)
    plain = canvas.copy()
    laces(canvas)
    marks(canvas)
    diff = np.abs(np.asarray(canvas, int) - np.asarray(plain, int)).max(2) > 0
    return canvas, Image.fromarray(np.where(diff, 255, 0).astype(np.uint8))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--master")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    master, marks_mask = draw()
    if a.master:
        master.save(a.master, optimize=True)
    native = master.resize((N, N), Image.LANCZOS)
    mask = np.asarray(marks_mask.resize((N, N), Image.BOX)) > 0
    native.putalpha(Image.fromarray(np.where(mask, 255, 0).astype(np.uint8)))
    path = out / "modern_ball.png"
    native.save(path, optimize=True)
    doc = dict(schema="nfl2k5_era_ball/v1", modern_from_season=2006,
               note="Authored modern Wilson game ball on the retail ball UV layout. Moments of seasons before 2006 "
                    "keep the ball already on the user's disc.",
               texture=dict(file="modern_ball.png", size=[N, N],
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (out / "manifest.json").write_text(json.dumps(doc, indent=1) + "\n", newline="\n")
    print("ERA_BALL_ART_OK", doc["texture"]["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
