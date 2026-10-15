#!/usr/bin/env python3
"""fa1 field art: authored vector drawings exported to the Studio's PNG inputs.

Everything here is drawn from geometry in this file. Reference photographs were
only looked at while choosing the geometry; none is read, traced or shipped.

giants   the MetLife midfield helmet (s18 center_logo, 256x256). The shell is an
         ellipse fitted to the accepted silhouette (mean deviation 0.7 texel),
         the lower contour is a few cubic curves, and every facemask bar has one
         constant width. The accepted ny pixels are kept exactly.
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
    p.add_argument("item", choices=["giants", "seal"])
    p.add_argument("--out", type=Path, help="write here instead of the repository input")
    p.add_argument("--check", action="store_true", help="seal: report only, exit 1 when stale")
    a = p.parse_args(argv)
    if a.item == "seal":
        return seal(a.check)
    if a.item == "giants":
        image = giants_helmet()
        target = a.out or HELMET
        print(json.dumps({"file": str(target.name), "sha256": save_png(image, target)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
