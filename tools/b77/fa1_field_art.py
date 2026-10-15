#!/usr/bin/env python3
"""fa1 field art: authored vector drawings exported to the Studio's PNG inputs.

Everything here is drawn from geometry in this file. Reference photographs were
only looked at while choosing the geometry; none is read, traced or shipped.

giants         the MetLife midfield helmet (s18 center_logo, 256x256). The shell is
               an ellipse fitted to the accepted silhouette (mean deviation 0.7
               texel), the lower contour is a few cubic curves, and every facemask
               bar has one constant width. The accepted ny pixels are kept exactly.
washington     REDSKINS for Anniversary row 10 (768x104 lettering layer).
raiders        RAIDERS for Anniversary rows 2 and 5.
numbers-block  modern block yard numerals in the native 256x256 ``numbers`` atlas
               cells; no Studio input consumes it yet, so it needs --out.
seal           upsert this job's rows in the reviewed PNG catalogs, move the pins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
METLIFE = ROOT / "data/nfl2k5_modern_metlife"
HELMET = METLIFE / "art/s18/field/center_logo.png"

#: Supersampling factor over the 256-texel texture; geometry is written in 1024 units.
S = 8
U = S / 4

WHITE = (244, 245, 247)
BLUE = (14, 60, 117)
RED = (167, 25, 48)
GREY = (165, 172, 175)

#: The accepted ny mark, white with its navy edge, copied texel for texel.
NY_RECT = (62, 40, 155, 115)


def cubic(p0, p1, p2, p3, n=64):
    t = np.linspace(0.0, 1.0, n)[:, None]
    p0, p1, p2, p3 = (np.asarray(p, float) for p in (p0, p1, p2, p3))
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def rounded(points, radius, closed=False, n=24):
    """A polyline with circular fillets of ``radius`` at every interior corner."""
    pts = [np.asarray(p, float) for p in points]
    if closed:
        pts = pts + pts[:2]
    out = [pts[0]] if not closed else []
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        u, v = a - b, c - b
        lu, lv = np.hypot(*u), np.hypot(*v)
        u, v = u / lu, v / lv
        half = np.arccos(np.clip(np.dot(u, v), -1, 1)) / 2
        r = radius[i] if isinstance(radius, (list, tuple)) else radius
        if r <= 0 or half < 1e-3 or abs(half - np.pi / 2) < 1e-3:
            out.append(b)
            continue
        d = min(r / np.tan(half), lu / 2, lv / 2)
        r = d * np.tan(half)
        p, q = b + u * d, b + v * d
        bis = (u + v) / np.hypot(*(u + v))
        centre = b + bis * (r / np.sin(half))
        a0 = np.arctan2(*(p - centre)[::-1])
        a1 = np.arctan2(*(q - centre)[::-1])
        sweep = (a1 - a0 + np.pi) % (2 * np.pi) - np.pi
        for t in np.linspace(0, 1, n):
            ang = a0 + sweep * t
            out.append(centre + r * np.array([np.cos(ang), np.sin(ang)]))
    out.append(out[0] if closed else pts[-1])
    return np.array(out)


def poly_mask(points, size):
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).polygon([tuple(np.asarray(p, float) * U) for p in points], fill=255)
    return np.asarray(im) > 127


def centre_distance(paths, size):
    """Distance in 1024 units from every pixel to the union of centre lines."""
    im = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(im)
    for path in paths:
        d.line([tuple(np.asarray(p, float) * U) for p in path], fill=255, width=1)
    return ndi.distance_transform_edt(np.asarray(im) == 0) / U


class Canvas:
    def __init__(self, size):
        self.size = size
        self.rgb = np.zeros((size, size, 3))
        self.alpha = np.zeros((size, size))

    def paint(self, mask, colour):
        m = mask.astype(float)
        self.rgb = self.rgb * (1 - m[..., None]) + np.asarray(colour, float) * m[..., None]
        self.alpha = np.maximum(self.alpha, m)

    def bar(self, paths, width, rim, separator=0.0, colour=GREY):
        """A constant-width bar: white rim, grey core, optional white centre line (a doubled bar)."""
        dist = centre_distance(paths, self.size)
        self.paint(dist <= width / 2, WHITE)
        self.paint(dist <= width / 2 - rim, colour)
        if separator:
            self.paint(dist <= separator / 2, WHITE)

    def reduce(self, w, h):
        k = self.size // w
        pre = np.dstack([self.rgb * self.alpha[..., None], self.alpha])
        small = pre.reshape(h, k, w, k, 4).mean(axis=(1, 3))
        a = small[..., 3]
        rgb = np.where(a[..., None] > 1e-6, small[..., :3] / np.maximum(a[..., None], 1e-6), 0)
        return np.dstack([rgb, a * 255]).round().clip(0, 255).astype(np.uint8)


# --- the Giants midfield helmet ------------------------------------------------------------------------------
#: Shell dome: least-squares ellipse through the accepted silhouette (1024 units).
DOME = dict(cx=458.64, cy=428.91, a=409.75, b=393.45)
STRIPE = 21.0          # the red band's width inside the dome edge
OUTLINE = 22.0         # the white outline around shell and back patch
BACK_Y, FRONT_Y = 564.0, 440.0


def dome_x(y, side):
    t = np.sqrt(max(0.0, 1 - ((y - DOME["cy"]) / DOME["b"]) ** 2))
    return DOME["cx"] + side * DOME["a"] * t


def dome_arc(n=400):
    a0 = np.arctan2((FRONT_Y - DOME["cy"]) / DOME["b"], (dome_x(FRONT_Y, 1) - DOME["cx"]) / DOME["a"])
    a1 = np.arctan2((BACK_Y - DOME["cy"]) / DOME["b"], (dome_x(BACK_Y, -1) - DOME["cx"]) / DOME["a"])
    ang = np.linspace(a0, a1 - 2 * np.pi if a1 > a0 else a1, n)
    return np.stack([DOME["cx"] + DOME["a"] * np.cos(ang), DOME["cy"] + DOME["b"] * np.sin(ang)], 1)


#: Facemask centre lines (1024 units). Bars meet the shell under their own rims.
TOP_BAR = [(628, 482), (893, 482), (893, 396)]
SIDE_UP = [(626, 580), (700, 478)]                 # ear clip up to the top bar
SIDE_DOWN = [(612, 482), (740, 664)]               # forehead down across it to the upright's foot
UPRIGHT = [(740, 482), (740, 684)]
MID_BAR = [(552, 672), (732, 688)]
LOOP = [(732, 688), (974, 710), (950, 958), (780, 958), (732, 688)]
CLIP = [(554, 572), (630, 572), (630, 672), (554, 672)]
BAR, DOUBLE, RIM, SEPARATOR = 48.0, 78.0, 12.0, 7.0


def giants_helmet():
    size = 256 * S
    back = (dome_x(BACK_Y, -1), BACK_Y)
    bottom = [np.array([back])]
    bottom.append(np.linspace(back, (152, 645), 16))
    bottom.append(cubic((152, 645), (190, 662), (250, 680), (290, 700)))
    bottom.append(cubic((290, 700), (330, 740), (380, 832), (480, 834)))
    bottom.append(cubic((480, 834), (560, 836), (640, 800), (646, 742)))
    bottom.append(cubic((646, 742), (648, 712), (600, 694), (548, 684)))
    hidden = [(560, 676), (725, 690), (725, 482), (dome_x(FRONT_Y, 1), 482)]
    shell_pts = np.concatenate(bottom + [np.array(hidden), dome_arc()])
    shell = poly_mask(shell_pts, size)
    patch = poly_mask([back, (152, 645), (190, 658), (back[0] - 14, 658), (back[0] - 14, back[1])], size)

    yy, xx = (np.mgrid[0:size, 0:size] + 0.5) / U
    inner = ((xx - DOME["cx"]) / (DOME["a"] - STRIPE)) ** 2 + ((yy - DOME["cy"]) / (DOME["b"] - STRIPE)) ** 2 > 1
    stripe = shell & inner & (yy <= np.where(xx < DOME["cx"], BACK_Y, FRONT_Y))

    c = Canvas(size)
    body = shell | patch
    c.paint(ndi.distance_transform_edt(~body) / U <= OUTLINE, WHITE)
    c.paint(patch, WHITE)
    c.paint(shell, BLUE)
    c.paint(stripe, RED)
    c.paint(((xx - 448.1) / 46) ** 2 + ((yy - 596.1) / 49) ** 2 <= 1, WHITE)     # ear hole
    for x0, y0, r in ((333.2, 696.5, 11.5), (554.8, 764.4, 11.0)):              # snaps
        c.paint((xx - x0) ** 2 + (yy - y0) ** 2 <= r * r, WHITE)

    c.bar([rounded(CLIP, 22, closed=True)], BAR - 6, RIM)
    c.bar([np.array(SIDE_UP, float)], BAR, RIM)
    c.bar([rounded(TOP_BAR, 30)], DOUBLE, RIM, SEPARATOR)
    c.bar([np.array(SIDE_DOWN, float)], BAR, RIM)
    c.bar([np.array(UPRIGHT, float)], BAR, RIM)
    c.bar([np.array(MID_BAR, float), rounded(LOOP, [0, 30, 56, 56, 0])], DOUBLE, RIM, SEPARATOR)

    out = c.reduce(256, 256)
    accepted = np.asarray(Image.open(HELMET).convert("RGBA"))
    x0, y0, x1, y1 = NY_RECT
    out[y0:y1, x0:x1] = accepted[y0:y1, x0:x1]
    return Image.fromarray(out, "RGBA")


# --- period end-zone lettering ---------------------------------------------------------------------------------
FIELDS = ROOT / "data/nfl2k5_espn25_fields"
#: Lettering band: the 104-texel slot composited at y=12 of the 768x128 end-zone strip.
BAND_W, BAND_H = 768, 104


class Glyphs:
    """Athletic block capitals on a supersampled canvas: square terminals, uniform stems, rounded bowls.

    Coordinates are band texels; ``t`` is the stem, ``th`` the horizontal bar, ``h`` the cap height.
    """

    def __init__(self, h, t, th, radius, size=(BAND_W, BAND_H)):
        self.h, self.t, self.th, self.r = h, t, th, radius
        self.im = Image.new("L", (size[0] * S, size[1] * S), 0)
        self.d = ImageDraw.Draw(self.im)

    def _xy(self, pts):
        return [(x * S, y * S) for x, y in pts]

    def rect(self, x0, y0, x1, y1, fill=255):
        self.d.rectangle(self._xy([(x0, y0), (x1, y1)]), fill=fill)

    def poly(self, pts, fill=255):
        self.d.polygon(self._xy(pts), fill=fill)

    def ring(self, x0, y0, x1, y1, t, th, corners):
        """A rounded-rectangle ring; ``corners`` (tl, tr, br, bl) choose the rounded corners."""
        r = self.r
        self.d.rounded_rectangle(self._xy([(x0, y0), (x1, y1)]), radius=r * S, fill=255, corners=corners)
        ri = max(r - min(t, th), 0.6)
        self.d.rounded_rectangle(self._xy([(x0 + t, y0 + th), (x1 - t, y1 - th)]), radius=ri * S, fill=0,
                                 corners=corners)

    def slant(self, top, bottom, y0, y1, t):
        """A diagonal stroke of perpendicular width ``t`` whose left edge runs from (top, y0) to (bottom, y1)."""
        tw = t * np.hypot(bottom - top, y1 - y0) / (y1 - y0)
        self.poly([(top, y0), (top + tw, y0), (bottom + tw, y1), (bottom, y1)])
        return tw

    def letter(self, ch, x, y, w):
        h, t, th = self.h, self.t, self.th
        mid = y + h * 0.52
        if ch == "I":
            self.rect(x, y, x + t, y + h)
        elif ch == "E":
            self.rect(x, y, x + t, y + h)
            self.rect(x, y, x + w, y + th)
            self.rect(x, mid - th / 2, x + w * 0.84, mid + th / 2)
            self.rect(x, y + h - th, x + w, y + h)
        elif ch == "D":
            self.ring(x, y, x + w, y + h, t, th, (False, True, True, False))
        elif ch == "R":
            bowl = y + h * 0.56
            self.rect(x, y, x + t, y + h)
            self.ring(x, y, x + w, bowl + th / 2, t, th, (False, True, True, False))
            self.slant(x + w * 0.40, x + w - t * 1.18, bowl - th / 2, y + h, t)
        elif ch == "S":
            spur = h * 0.13
            self.ring(x, y, x + w, mid + th / 2, t, th, (True, True, False, True))
            self.rect(x + w - t - 0.5, y + th + spur, x + w + 0.5, mid - th / 2, fill=0)
            self.ring(x, mid - th / 2, x + w, y + h, t, th, (False, True, True, True))
            self.rect(x - 0.5, mid + th / 2, x + t + 0.5, y + h - th - spur, fill=0)
        elif ch == "K":
            self.rect(x, y, x + t, y + h)
            arm = t * 1.04
            tw = self.slant(x + w - t * 1.25, x + t * 0.35, y, y + h * 0.62, arm)
            self.poly([(x + t * 0.35 + tw * 0.2, mid - th * 0.2), (x + w * 0.42, mid - th * 0.6),
                       (x + w, y + h), (x + w - tw, y + h)])
        elif ch == "N":
            self.rect(x, y, x + t, y + h)
            self.rect(x + w - t, y, x + w, y + h)
            self.slant(x, x + w - t * 1.5, y, y + h, t * 1.02)
        elif ch == "A":
            self.ring(x, y, x + w, y + h + self.r + th, t, th, (True, True, False, False))
            self.rect(x - 0.5, y + h, x + w + 0.5, y + h + self.r + th + 1, fill=0)
            self.rect(x, mid - th / 2, x + w, mid + th / 2)
        else:
            raise ValueError(ch)

    def word(self, text, cx, widths, gap, outline):
        width = sum(widths[c] + 2 * outline for c in text) + gap * (len(text) - 1)
        x = cx - width / 2 + outline
        y = (BAND_H - self.h) / 2
        for c in text:
            self.letter(c, x, y, widths[c])
            x += widths[c] + 2 * outline + gap
        return width


    def digit(self, ch, x0, y0, x1, y1):
        """A block numeral filling the box; ``h0`` is the left half of a zero whose mirror axis is x1."""
        t, th, r = self.t, self.th, self.r
        w = x1 - x0; mid = (y0 + y1) / 2
        if ch == "h0":
            x2 = x1 + w
            self.ring(x0, y0, x2, y1, t, th, (True, True, True, True))
            self.rect(x1, y0 - 1, x2 + 1, y1 + 1, fill=0)
        elif ch == "1":
            flag = w * 0.42
            self.rect(x1 - t, y0, x1, y1)
            self.rect(x1 - t - flag, y0, x1, y0 + th)
        elif ch == "2":
            spur = (y1 - y0) * 0.14
            self.ring(x0, y0, x1, mid + th / 2, t, th, (True, True, True, False))
            self.rect(x0 - 0.5, y0 + th + spur, x0 + t + 0.5, mid + th / 2 + 0.5, fill=0)
            self.d.rounded_rectangle(self._xy([(x0, mid - th / 2), (x1 - r, y1)]), radius=r * S, fill=255,
                                     corners=(True, False, False, False))
            self.rect(x0 + t, mid + th / 2, x1 + 0.5, y1 - th, fill=0)
            self.rect(x0, y1 - th, x1, y1)
        elif ch == "3":
            self.ring(x0, y0, x1, y1, t, th, (False, True, True, False))
            self.rect(x0 - 0.5, y0 + th, x0 + t + 0.5, y1 - th, fill=0)
            self.rect(x0 + w * 0.30, mid - th / 2, x1, mid + th / 2)
        elif ch == "4":
            cross = y0 + (y1 - y0) * 0.60
            stem = x1 - t * 1.2
            self.rect(x0, y0, x0 + t, cross + th)
            self.rect(x0, cross, x1, cross + th)
            self.rect(stem - t, y0 + (y1 - y0) * 0.30, stem, y1)
        elif ch == "5":
            spur = (y1 - y0) * 0.14
            self.rect(x0, y0, x1, y0 + th)
            self.rect(x0, y0, x0 + t, mid + th / 2)
            self.ring(x0, mid - th / 2, x1, y1, t, th, (False, True, True, True))
            self.rect(x0 - 0.5, mid + th / 2, x0 + t + 0.5, y1 - th - spur, fill=0)
        else:
            raise ValueError(ch)


#: Native ``numbers`` atlas glyph boxes (256 texels): the retail ink bounds inside each sampled UV cell.
NUMBER_BOXES = {"h0": (17, 11, 52.02, 116), "2": (89.5, 13, 161.5, 116), "4": (170, 12, 245, 115),
                "1": (12, 143, 75, 244), "3": (91, 141, 162, 246), "5": (177, 141, 248, 246)}
#: Modern block numerals (Lucas Oil, Nissan, U.S. Bank, Paycor in 2025-26 game frames): white, no edge.
BLOCK_NUMBERS = dict(t=19.0, th=17.5, radius=17.0, fill=(245, 246, 247))


def number_atlas(spec=BLOCK_NUMBERS):
    g = Glyphs(0, spec["t"], spec["th"], spec["radius"], size=(256, 256))
    for ch, box in NUMBER_BOXES.items():
        g.digit(ch, *box)
    body = np.asarray(g.im, float) / 255.0
    k = S
    a = body.reshape(256, k, 256, k).mean(axis=(1, 3))
    rgb = np.broadcast_to(np.asarray(spec["fill"], float), (256, 256, 3))
    return Image.fromarray(np.dstack([rgb, a * 255]).round().clip(0, 255).astype(np.uint8), "RGBA")


def lettering(text, h, t, th, radius, widths, gap, outline, fill, edge, cx=BAND_W / 2):
    g = Glyphs(h, t, th, radius)
    g.word(text, cx, widths, gap, outline)
    body = np.asarray(g.im) > 127
    ring = ndi.distance_transform_edt(~body) / S <= outline
    c = Canvas(1)
    c.rgb = np.zeros(body.shape + (3,))
    c.alpha = np.zeros(body.shape)
    c.paint(ring, edge)
    c.paint(body, fill)
    k = S
    pre = np.dstack([c.rgb * c.alpha[..., None], c.alpha])
    small = pre.reshape(BAND_H, k, BAND_W, k, 4).mean(axis=(1, 3))
    a = small[..., 3]
    rgb = np.where(a[..., None] > 1e-6, small[..., :3] / np.maximum(a[..., None], 1e-6), 0)
    return Image.fromarray(np.dstack([rgb, a * 255]).round().clip(0, 255).astype(np.uint8), "RGBA")


def hexrgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


#: Washington 1983: gold capitals, white edge, inside the 152..616 slot between the native side helmets.
WASHINGTON = dict(text="REDSKINS", h=78, t=13.5, th=11.5, radius=12, gap=11, outline=3,
                  widths=dict(R=44, E=38, D=45, S=43, K=45, I=13.5, N=46), fill="#ffb612", edge="#ffffff")
#: Oakland 1968 and 1974: white capitals, silver edge, across the 104..664 slot of the black end zone.
RAIDERS = dict(text="RAIDERS", h=80, t=15, th=13, radius=14, gap=16, outline=3,
               widths=dict(R=52, A=60, I=15, D=54, E=46, S=51), fill="#ffffff", edge="#a5acaf")
LETTERING = {"washington": (WASHINGTON, (10,)), "raiders": (RAIDERS, (2, 5))}


def lettering_art(spec):
    s = dict(spec)
    return lettering(s.pop("text"), s.pop("h"), s.pop("t"), s.pop("th"), s.pop("radius"), s.pop("widths"),
                     s.pop("gap"), s.pop("outline"), hexrgb(s.pop("fill")), hexrgb(s.pop("edge")))


def save_png(image, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- release catalogs ------------------------------------------------------------------------------------------
CHECKER = ROOT / "packaging/check_2k5_mod_studio_release.py"
ALLOWLIST = ROOT / "packaging/release-allowlist.txt"
#: Reviewed PNG catalog -> (checker pin name, the rows this job owns in it).
CATALOGS = {
    "packaging/nfl2k5_scorebug_template_pngs.json": (
        "SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256",
        ("data/nfl2k5_modern_metlife/art/s18/field/center_logo.png",)),
    "packaging/nfl2k5_espn25_field_pngs.json": (
        "ANNIVERSARY_FIELD_PNG_CATALOG_SHA256",
        tuple(f"data/nfl2k5_espn25_fields/row{r:02d}/lettering.png" for r in (2, 5, 10))),
}


def png_row(relative):
    data = (ROOT / relative).read_bytes()
    if data[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR":
        raise SystemExit(f"not a PNG: {relative}")
    w, h = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    return dict(height=h, sha256=hashlib.sha256(data).hexdigest(), size=len(data), width=w)


def seal(check=False):
    """Upsert this job's rows in the reviewed PNG catalogs and move each catalog's checker pin."""
    checker = CHECKER.read_text(encoding="utf-8")
    allow = set(ALLOWLIST.read_text(encoding="utf-8").split("\n"))
    writes, report = {}, {}
    for catalog, (pin, owned) in CATALOGS.items():
        missing = [r for r in owned if r not in allow]
        if missing:
            raise SystemExit(f"not in the release allowlist: {missing}")
        doc = json.loads((ROOT / catalog).read_text(encoding="utf-8"))
        doc["files"].update({r: png_row(r) for r in owned})
        payload = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
        line = re.compile(r'(?m)^%s = "[0-9a-f]{64}"$' % pin)
        if len(line.findall(checker)) != 1:
            raise SystemExit(f"checker pin {pin} is not unique")
        checker = line.sub(f'{pin} = "{hashlib.sha256(payload).hexdigest()}"', checker)
        writes[ROOT / catalog] = payload
        report[catalog] = hashlib.sha256(payload).hexdigest()
    writes[CHECKER] = checker.encode("utf-8")
    current = all(p.read_bytes() == b for p, b in writes.items())
    if not check:
        for p, b in writes.items():
            if p.read_bytes() != b:
                p.write_bytes(b)
    print(json.dumps(dict(sealed=current or not check, catalogs=report)))
    return 0 if current or not check else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("item", choices=["giants", "washington", "raiders", "numbers-block", "seal"])
    p.add_argument("--out", type=Path, help="write here instead of the repository input")
    p.add_argument("--check", action="store_true", help="seal: report only, exit 1 when stale")
    a = p.parse_args(argv)
    if a.item == "seal":
        return seal(a.check)
    if a.item == "giants":
        image = giants_helmet()
        target = a.out or HELMET
        print(json.dumps({"file": str(target.name), "sha256": save_png(image, target)}))
    if a.item == "numbers-block":
        p.error("numbers-block has no Studio input yet; pass --out") if not a.out else None
        print(json.dumps({"file": a.out.name, "sha256": save_png(number_atlas(), a.out)}))
    if a.item in LETTERING:
        spec, rows = LETTERING[a.item]
        image = lettering_art(spec)
        targets = [a.out] if a.out else [FIELDS / f"row{r:02d}/lettering.png" for r in rows]
        for target in targets:
            print(json.dumps({"file": str(target.relative_to(ROOT) if not a.out else target.name),
                              "sha256": save_png(image, target)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
