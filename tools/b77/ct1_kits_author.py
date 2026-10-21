#!/usr/bin/env python3
"""Author the two classic-team kits ct1 adds as NEW slots (coordinator 10/17): the 2018-2023 Titans and the 2015-2019
Browns. Writes their entries into data/nfl2k5_moment_kits.json (ids CT1-TEN and CT1-CLE; nothing else changes).

All art is authored here as vector operations for the kit compiler (nfl2k5_kit_fixes_2026 ops: poly / multipoly /
recolor / ring / flood): ct1's own block numerals and letters, drawn from stroke paths on a 10 x 17 grid. The look
follows the Gridiron Uniform Database season pages (2019 TEN, 2017 CLE; reference only, never shipped):

* Titans 2018-2023 (style 14): navy home / white road over navy pants; titanium-grey shoulders and upper sleeves with
  a Titans-blue edge; white (home) or navy (road) numerals with a Titans-blue outline; navy helmet shell carrying the
  existing Titans logo; a grey sword stripe on the pants that ends in a point. Base kits: the retail 1999 kit on the
  franchise spare (28H9 home / 28A9 road), navy pants from 28A9.
* Browns 2015-2019 (style 14): brown home / white road over white pants; CLEVELAND across the chest; BROWNS down the
  pant leg beside the stripe; orange numerals with a brown (road) or white (home) drop shadow; solid orange road socks
  and brown home socks; the 2020-era "1946" collar mark removed. Base kits: the current kits 30H0 / 30A0.

Geometry that depends on the donor art (the sleeve patches, the helmet shell seeds) is measured from the donor
packages given on the command line and written as plain numbers, so the data alone reproduces the art.

  ct1_kits_author.py --donors DIR_WITH_28H9.IFF_ETC [--check]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_moment_kits.json"

# ---------------------------------------------------------------------------------------------- the stroke font
W, H = 10.0, 17.0


def _grid(w=3.0, c=1.6):
    x0, x1, y0, y1 = w / 2, W - w / 2, w / 2, H - w / 2
    return x0, x1, y0, y1, (y0 + y1) / 2, c


def glyph(ch, w=3.0):
    """Centre-line paths of one character on the 10 x 17 grid (stroke width ``w`` grid units)."""
    x0, x1, y0, y1, ym, c = _grid(w)
    xm = (x0 + x1) / 2
    loop = [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c),
            (x0, y0 + c), (x0 + c, y0)]
    g = {
        "0": [loop],
        "1": [[(xm - 2.4, y0 + 2.8), (xm + 0.6, y0), (xm + 0.6, y1)]],
        "2": [[(x0, y0 + c + 0.6), (x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, ym - 1.2), (x0, y1 - 2.4),
               (x0, y1), (x1, y1)]],
        "3": [[(x0, y0), (x1 - c, y0), (x1, y0 + c), (x1, ym - c), (x1 - c, ym), (x0 + 2.2, ym)],
              [(x1 - c, ym), (x1, ym + c), (x1, y1 - c), (x1 - c, y1), (x0, y1)]],
        "4": [[(x1 - 1.8, y1), (x1 - 1.8, y0), (x0, ym + 2.6), (x1, ym + 2.6)]],
        "5": [[(x1, y0), (x0, y0), (x0, ym - 0.6), (x1 - c, ym - 0.6), (x1, ym - 0.6 + c), (x1, y1 - c),
               (x1 - c, y1), (x0, y1)]],
        "6": [[(x1, y0 + c), (x1 - c, y0), (x0 + c, y0), (x0, y0 + c), (x0, y1 - c), (x0 + c, y1), (x1 - c, y1),
               (x1, y1 - c), (x1, ym + c), (x1 - c, ym), (x0, ym)]],
        "7": [[(x0, y0), (x1, y0), (x1, y0 + c), (xm - 0.6, y1)]],
        "8": [[(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, ym - c), (x1 - c, ym), (x0 + c, ym), (x0, ym - c),
               (x0, y0 + c), (x0 + c, y0)],
              [(x0 + c, ym), (x1 - c, ym), (x1, ym + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c),
               (x0, ym + c), (x0 + c, ym)]],
        "9": [[(x0, y1 - c), (x0 + c, y1), (x1 - c, y1), (x1, y1 - c), (x1, y0 + c), (x1 - c, y0), (x0 + c, y0),
               (x0, y0 + c), (x0, ym - c), (x0 + c, ym), (x1, ym)]],
        "C": [[(x1, y0 + c), (x1 - c, y0), (x0 + c, y0), (x0, y0 + c), (x0, y1 - c), (x0 + c, y1), (x1 - c, y1),
               (x1, y1 - c)]],
        "L": [[(x0, y0), (x0, y1), (x1, y1)]],
        "E": [[(x1, y0), (x0, y0), (x0, y1), (x1, y1)], [(x0, ym), (x1 - 1.4, ym)]],
        "V": [[(x0, y0), (xm, y1), (x1, y0)]],
        "A": [[(x0, y1), (x0, y0 + c), (x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1)], [(x0, ym + 0.8), (x1, ym + 0.8)]],
        "N": [[(x0, y1), (x0, y0), (x1, y1), (x1, y0)]],
        "D": [[(x0, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0, y1), (x0, y0)]],
        "B": [[(x0, y0), (x0, y1), (x1 - c, y1), (x1, y1 - c), (x1, ym + c), (x1 - c, ym), (x0, ym)],
              [(x0, y0), (x1 - c, y0), (x1, y0 + c), (x1, ym - c), (x1 - c, ym)]],
        "R": [[(x0, y1), (x0, y0), (x1 - c, y0), (x1, y0 + c), (x1, ym - c), (x1 - c, ym), (x0, ym)],
              [(xm, ym), (x1, y1)]],
        "O": [loop],
        "W": [[(x0, y0), (x0 + 1.2, y1), (xm, ym + 0.5), (x1 - 1.2, y1), (x1, y0)]],
        "S": [[(x1, y0 + c), (x1 - c, y0), (x0 + c, y0), (x0, y0 + c), (x0, ym - c), (x0 + c, ym), (x1 - c, ym),
               (x1, ym + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c)]],
    }
    return g[ch]


def stroke_polys(paths, w):
    """Quads along every segment (square ends) plus an octagon at each joint: one union of polygons."""
    out = []
    r = w / 2
    for path in paths:
        closed = path[0] == path[-1]
        for i, ((ax, ay), (bx, by)) in enumerate(zip(path, path[1:])):
            dx, dy = bx - ax, by - ay
            n = math.hypot(dx, dy)
            ux, uy = dx / n, dy / n
            px, py = -uy * r, ux * r
            ea = 0.0 if (closed or i > 0) else r      # square cap at an open end
            eb = 0.0 if (closed or i < len(path) - 2) else r
            a = (ax - ux * ea, ay - uy * ea)
            b = (bx + ux * eb, by + uy * eb)
            out.append([(a[0] + px, a[1] + py), (b[0] + px, b[1] + py), (b[0] - px, b[1] - py), (a[0] - px, a[1] - py)])
        joints = path[1:-1] + ([path[0]] if closed else [])
        for (jx, jy) in joints:
            k = r / math.cos(math.pi / 8)
            out.append([(jx + k * math.cos(math.pi / 8 + j * math.pi / 4), jy + k * math.sin(math.pi / 8 + j * math.pi / 4))
                        for j in range(8)])
    return out


def place(polys, box, *, rotate=0, shift=(0.0, 0.0), grid=(W, H)):
    """Grid polygons into texture coordinates inside ``box`` (x0, y0, x1, y1); rotate 90 = reading downward."""
    x0, y0, x1, y1 = box
    gw, gh = grid
    out = []
    for poly in polys:
        pts = []
        for gx, gy in poly:
            if rotate == 90:          # grid x runs down the box, grid y runs right-to-left
                u, v = gy / gh, gx / gw
                tx, ty = x1 - u * (x1 - x0), y0 + v * (y1 - y0)
            else:
                tx, ty = x0 + gx / gw * (x1 - x0), y0 + gy / gh * (y1 - y0)
            pts.append([round(tx + shift[0], 3), round(ty + shift[1], 3)])
        out.append(pts)
    return out


def text_polys(text, box, w, *, gap=2.0, rotate=0):
    """A word as one polygon list: letters on a (10 + gap) pitch, scaled to fill ``box``."""
    n = len(text)
    total = n * W + (n - 1) * gap
    polys = []
    for i, ch in enumerate(text):
        for p in stroke_polys(glyph(ch, w), w):
            polys.append([(x + i * (W + gap), y) for x, y in p])
    return place(polys, box, rotate=rotate, grid=(total, H))


# ----------------------------------------------------------------------------------------------- art rows
NAVY, TBLUE, TGREY, WHITE = "#0C2340", "#4B92DB", "#8A8D8F", "#FFFFFF"
PANTS_NAVY = "#001342"                     # the navy of the 28A9 pants cloth (0, 19, 66)
BROWN, ORANGE = "#311D00", "#FF3C00"


def require_size(ok, message):
    if not ok:
        raise ValueError(message)


def row(names, chunk, kind, ops):
    name, tw, th, mips = names[chunk]
    return {"chunk": chunk, "kind": kind, "texture": name, "size": [tw, th, mips], "ops": ops, "reencode": True}


def digit_rows(size, box, fill, outline=None, shadow=None, w=3.0, t=0.75, chunks=range(13, 23), texture_names=None):
    rows = []
    for d, chunk in zip("0123456789", chunks):
        paths = glyph(d, w)
        ops = [{"op": "poly", "points": [[0, 0], [size, 0], [size, size], [0, size]], "color": fill, "alpha": 0}]
        if outline:
            ops.append({"op": "multipoly", "polys": place(stroke_polys(paths, w + 2 * t), box), "color": outline,
                        "alpha": 255})
        if shadow:
            color, (sx, sy) = shadow
            ops.append({"op": "multipoly", "polys": place(stroke_polys(paths, w), box, shift=(sx, sy)), "color": color,
                        "alpha": 255})
        ops.append({"op": "multipoly", "polys": place(stroke_polys(paths, w), box), "color": fill, "alpha": 255})
        name, tw, th, mips = texture_names[chunk]
        require_size(tw == th == size, f"digit chunk {chunk} is {tw}x{th}, expected {size}")
        rows.append({"chunk": chunk, "kind": "txtr", "texture": name, "size": [tw, th, mips], "ops": ops,
                     "max_blend_slots": 12, "reencode": True})
    return rows


def measure(donors):
    """Numbers the art needs from the donor packages."""
    sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b765")]
    import numpy as np
    from nfl_txtr import parse_chunks, decode_chunk, parse_texture, texture_to_rgba
    import u1_audit as u
    from mod_editor.core import nfl2k5_kit_fixes_2026 as fx

    def tex(name, i):
        raw = (Path(donors) / f"{name}.IFF").read_bytes()
        ch = parse_chunks(raw)[i]
        dec, _ = decode_chunk(raw, ch)
        t = u.tset_texture(dec, 0) if ch.kind == "TSET" else parse_texture(dec, ch)
        return np.array(__import__("PIL.Image", fromlist=["Image"]).frombytes("RGBA", (t.width, t.height),
                                                                               texture_to_rgba(dec, ch, t)))

    def names(name):
        """{chunk: [texture name, width, height, mips]} of the clean texture of every TSET/TXTR chunk."""
        raw = (Path(donors) / f"{name}.IFF").read_bytes()
        out = {}
        for c in parse_chunks(raw)[:53]:
            if c.kind not in ("TSET", "TXTR"):
                continue
            try:
                t = fx.native_textures(raw[c.offset:c.end_offset], c.kind.lower())[2][0]
            except Exception:  # noqa: BLE001
                continue
            out[c.index] = [t["name"], t["width"], t["height"], t["mips"]]
        return out

    m = {"names": {n: names(n) for n in ("28H9", "28A9", "30H0", "30A0")}}
    # Titans sleeve patches: the light-blue (60,123,220) areas, one convex hull per piece
    s = tex("28H9", 3)
    blue = (abs(s[..., 0].astype(int) - 60) < 30) & (abs(s[..., 1].astype(int) - 123) < 30) & (abs(s[..., 2].astype(int) - 220) < 30)
    pieces = []
    for y0, y1 in ((0, 64), (64, 128)):
        ys, xs = np.where(blue[y0:y1])
        pts = sorted({(int(x), int(y) + y0) for x, y in zip(xs, ys)})
        pieces.append(_hull([(x + dx, y + dy) for x, y in pts for dx in (0, 1) for dy in (0, 1)]))
    m["sleeve_patches"] = pieces
    for k in ("28H9", "28A9"):
        t = tex(k, 12)
        m.setdefault("helmet_white", {})[k] = [int(v) for v in t[40, 40, :3]]
    return m


def _hull(points):
    pts = sorted(set(points))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [list(p) for p in lower[:-1] + upper[:-1]]


def titans_side(letter, m):
    base = "28H9" if letter == "H" else "28A9"
    names = m["names"][base]
    yoke = "#3C7BDC"                         # the retail light blue (60, 123, 220)
    torso = row(names, 1, "tset", [
        {"op": "recolor", "box": [0, 0, 512, 64], "from": [yoke], "color": TGREY, "tolerance": 40},
        {"op": "ring", "box": [0, 0, 512, 72], "inside": [TGREY], "from": 0, "to": 1.5, "color": TBLUE, "tolerance": 6}])
    sleeve_ops = [{"op": "poly", "points": hull, "color": TGREY} for hull in m["sleeve_patches"]]
    sleeve_ops.append({"op": "ring", "box": [0, 0, 128, 128], "inside": [TGREY], "from": 0, "to": 1.5, "color": TBLUE,
                       "tolerance": 6})
    sleeve = row(names, 3, "tset", sleeve_ops)
    # navy pants (28A9): the light-blue / white side stripe becomes navy, then a grey sword stripe from the waist to a
    # point at mid-thigh on each leg
    pants_ops = [{"op": "recolor", "box": [0, 0, 512, 256], "from": [yoke, "#F5F5F5"], "color": PANTS_NAVY,
                  "tolerance": 60}]
    for cx in (143.5, 373.5):
        pants_ops.append({"op": "poly", "points": [[cx - 9, 0], [cx + 9, 0], [cx + 9, 96], [cx, 124], [cx - 9, 96]],
                          "color": TGREY})
        pants_ops.append({"op": "poly", "points": [[cx - 2, 0], [cx + 2, 0], [cx + 2, 100], [cx, 106], [cx - 2, 100]],
                          "color": TBLUE})
    pants = row(m["names"]["28A9"], 2, "tset", pants_ops)
    helmet = []
    for chunk in (11, 12):
        helmet.append(row(names, chunk, "txtr",
                          [{"op": "flood", "seed": [40, 40], "color": NAVY, "tolerance": 30, "box": [0, 0, 256, 256]},
                           {"op": "flood", "seed": [40, 200], "color": NAVY, "tolerance": 30, "box": [0, 0, 256, 256]}]))
    fill, outline = (WHITE, TBLUE) if letter == "H" else (NAVY, TBLUE)
    digits = digit_rows(64, (14.5, 1.5, 48.5, 62.5), fill, outline=outline, t=0.7, texture_names=names)
    arms = digit_rows(32, (7.5, 1.5, 24.5, 30.5), fill, outline=outline, t=0.8, chunks=range(33, 43), texture_names=names)
    side = {"base": base, "art": [torso, sleeve, pants] + helmet + digits + arms}
    side["chunks"] = {"2": "28A9", "4": "28A9"}
    return side


def browns_side(letter, m):
    base = "30H0" if letter == "H" else "30A0"
    names = m["names"][base]
    cloth, mark, shadow = (BROWN, ORANGE, WHITE) if letter == "H" else (WHITE, BROWN, BROWN)
    torso_ops = [
        # the 2020 "1946" back-collar mark goes
        {"op": "poly", "points": [[366, 43], [414, 43], [414, 58], [366, 58]],
         "color": "#3A2208" if letter == "H" else WHITE},          # the jersey cloth: brown (58, 34, 8) or white
        {"op": "multipoly", "polys": text_polys("CLEVELAND", (126.0, 87.0, 194.0, 99.0), 3.2, gap=2.2),
         "color": mark if letter == "A" else ORANGE},
    ]
    torso = row(names, 1, "tset", torso_ops)
    pants_ops = []
    for x in (114.0, 342.0):           # BROWNS down the leg, just inside the side stripe
        pants_ops.append({"op": "multipoly", "polys": text_polys("BROWNS", (x, 18.0, x + 11.0, 94.0), 3.2, gap=2.0,
                                                                  rotate=90), "color": BROWN})
    pants = row(names, 2, "tset", pants_ops)
    # socks: solid orange on the road (the Broncos' all-orange sock texture, 08H0, re-tinted to Browns orange) and
    # solid brown at home (the Browns' own all-brown alternate sock, 30H3)
    if letter == "A":
        socks = {"chunk": 4, "kind": "palette_map", "texture_kind": "tset", "tolerance": 40,
                 "map": [{"from": "#FC4C02", "to": ORANGE}]}
        sock_donor = "08H0"
    else:
        socks = None
        sock_donor = "30H3"
    digits = digit_rows(64, (14.5, 2.0, 46.5, 60.5), ORANGE, shadow=(shadow, (1.6, 1.6)), w=3.1, texture_names=names)
    arms = digit_rows(64, (14.5, 2.0, 46.5, 60.5), ORANGE, shadow=(shadow, (1.6, 1.6)), w=3.1, chunks=range(33, 43),
                      texture_names=names)
    return {"base": base, "chunks": {"4": sock_donor},
            "art": [torso, pants] + ([socks] if socks else []) + digits + arms}


def kits(m):
    return [
        {"id": "CT1-TEN", "team": "TEN", "code": "28", "style": 14, "label": [2018, 2023],
         "look": "2018-2023 Titans: navy home and white road over navy pants; titanium-grey shoulders and upper "
                 "sleeves edged in Titans blue; ct1's block numerals (white or navy with a Titans-blue outline); navy "
                 "helmet shell with the Titans logo; a grey sword stripe on the pants",
         "sides": {"H": titans_side("H", m), "A": titans_side("A", m)},
         "cards": {"H": "28H9", "A": "28A9", "logo": "28H9"}, "moments": [],
         "classic": ["titans_2019"],
         "evidence": ["GUD 2019_TEN_H2.png, 2019_TEN_B.png, 2019_TEN_A.png (2019 season page)",
                      "art authored by ct1 (vector ops, tools/b77/ct1_kits_author.py); no reference pixels ship"]},
        {"id": "CT1-CLE", "team": "CLE", "code": "30", "style": 14, "label": [2015, 2019],
         "look": "2015-2019 Browns: brown home and white road over white pants; CLEVELAND across the chest; BROWNS down "
                 "the pant leg; orange numerals with a brown (road) or white (home) drop shadow; orange road socks, brown "
                 "home socks; no 1946 collar mark",
         "sides": {"H": browns_side("H", m), "A": browns_side("A", m)},
         "cards": {"H": "30H0", "A": "30A0", "logo": "30H0"}, "moments": [],
         "classic": ["browns_2017"],
         "evidence": ["GUD 2017_CLE_B.png, 2017_CLE_A.png, 2017_CLE_G.png (2017 season page)",
                      "art authored by ct1 (vector ops, tools/b77/ct1_kits_author.py); no reference pixels ship"]},
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--donors", required=True, type=Path, help="folder with 28H9/28A9/30H0/30A0 .IFF packages")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    mine = kits(measure(args.donors))
    rest = [k for k in doc["kits"] if not k["id"].startswith("CT1-")]
    new = dict(doc, kits=rest + mine)
    text = json.dumps(new, indent=1, ensure_ascii=True) + "\n"
    if args.check:
        same = DATA.read_text(encoding="utf-8") == text
        print("ct1 kits reproduce exactly" if same else "ct1 kits differ")
        return 0 if same else 1
    DATA.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({k["id"]: {s: len(v["art"]) for s, v in k["sides"].items()} for k in mine}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
