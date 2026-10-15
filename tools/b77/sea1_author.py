#!/usr/bin/env python3
"""sea1 (b773): author the Seattle helmet and shoulder-number touch-up for ``data/nfl2k5_kit_fixes_2026_sea1.json``.

Noah (10/14, playing the v0.6.1 fixes disc): the Seahawks helmet is "95% there", but (1) a piece of the logo shows on
the grey crown stripe at the front, (2) the shoulder numbers look white instead of the grey of the chest and back
numbers, and (3) on the helmet back, where the logos now meet, the lines break and a "spear" sits over the logo.

Causes, on the decoded helmet02 (shell C) texture and the HI_HELMET_C mesh:
  1. Atlas overlap. The side A logo's grey wing and its white edges run 12 texels past the side island into the
     crown-stripe island (texels x 142-154, rows 48-90), which the mesh maps onto the crown front, beside the stripe.
  2. Shoulder-digit lighting. The ``an48``-``an57`` shoulder (TV) digits hold the chest digits' wolf grey (165, 172,
     175) but the game lights the shoulder digit 1.5 to 2 times brighter than the jersey and its chest numbers (Noah's
     shots: chest digits drawn at 0.97x their texels, the shoulder digit at 1.36x and clipped white; NYG's blue shoulder
     digits at 1.7-2.0x in uw2's frames), so wolf grey comes out white.
  3. Helmet back. uf2's band joins well, but its tick clean-up recoloured the white upper V line (the top edge of the
     bird's head, which on the 2026 helmet meets in a V above the band) into faint broken dashes, the band's white
     edges break where the side islands meet the back-centre island (azimuth +-22 to 24), dark navy texels sit in the
     band, and the dark seam strip beside each break reads as a black slash next to the stripe's thin tip.

The fixes (each a texel-space op on the existing art, drawn at 4x like the uf1-uf3 layers):
  1. the crown stripe's own carbon pattern copied over the overlap, mirrored from the stripe's other half (the pattern
     is symmetric about texel column 162), so the logo there keeps only its side-island texels;
  2. every shoulder-digit palette entry darkened to 3/5 (hue and alpha kept), so the shoulder numbers read wolf grey
     like the chest numbers; the 2026 frames (Week 5 v SF) show plain wolf grey TV numbers without the lime outline;
  3. the helmet back redrawn in shell (azimuth, height) space on the mesh and projected through each triangle's UVs:
     the gap between the band and the upper line cleared to shell navy, the band (white edges, grey body, chevron) and
     the upper white V line drawn whole across the seams, ending the stripe's tip on the V as on the 2026 helmet.
The band's chevron and where the logos meet stay where uf2 put them (Noah: "the logos finally meet properly").

  sea1_author.py project --mesh hi_head.gltf          project the design (writes tools/b77/sea1_helmet_back.json)
  sea1_author.py preview --tex DIR --out DIR          paint level 0 onto extracted PNGs (``<selector>_c<chunk>.png``)
  sea1_author.py data --input DISC.iso [--out data/nfl2k5_kit_fixes_2026_sea1.json]

Game-derived files (the mesh, the disc) stay outside the repository; only the shapes and the hashes go in.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402

DATA = fixes.DATA_SEA1
SHAPES = Path(__file__).resolve().parent / "sea1_helmet_back.json"
HELMETS = ("26H0", "26A0", "26H4", "26A4")           # one shell design (uf1/uf2 pinned them as one)
DIGITS = ("26H0", "26H4")                             # the navy jerseys with wolf-grey shoulder digits
NAVY, GRAY, WHITE = "#0C2848", "#A5ABAE", "#ECEDED"   # uf2's shell navy, band grey and white
ZC = 9.8                                              # shell centre (model z) for the azimuth

# -- the crown-front overlap -----------------------------------------------------------------------------------------
# Crown-stripe island texels x >= 142 (its left edge runs u 142.5-144.4 for rows 38-96), rows 40-100: the side A wing
# reaches x 154. The stripe's pattern mirrors about column 162 (x' = 324 - x; 26H0 rows 100-140 differ by 4818 summed
# levels over 560 texels mirrored, against 18601 for the best vertical shift), so its other half is the clean source.
CROWN_ROWS = (40, 100)
CROWN_COLS = (142, 156)


def crown_ops():
    (y0, y1), (xa, xb) = CROWN_ROWS, CROWN_COLS
    return [{"op": "copy", "src": [325 - xb, y0, 325 - xa, y1], "dst": [xa, y0], "flip": "h"}]


# -- the helmet back, in shell (azimuth, height) space ----------------------------------------------------------------
# Azimuth 0 is the back centre (degrees, positive towards the wearer's left), heights are model units. Measured on
# the v0.6.1 art unwrapped through the mesh: the band's outer white edge lies at 48.5 (top) and 44.8 (bottom) at
# azimuth +-26..34; uf2 drew the chevron (top 48.4 at +-22, 46.9 at +-5, 46.0 at 0; bottom 44.7 at +-22, 43.0 at 0);
# its white edge is 0.5 deep at the top and 0.45 at the bottom. The upper line (head outline) runs at 51.7 at +-30..36
# and its faint remains descend to about 50.1 at +-6; the stripe's tip reaches 50.25 at azimuth 0.
LINE_CENTRE = [(36, 51.72), (30, 51.64), (26, 51.46), (22, 51.15), (18, 50.88), (14, 50.62), (10, 50.38),
               (6, 50.14), (0, 49.86)]
LINE_HALF = 0.25
BAND_TOP = [(34, 48.52), (30, 48.51), (26, 48.49), (22, 48.42), (5, 46.9), (0, 46.02)]
BAND_BOTTOM = [(34, 44.86), (30, 44.84), (26, 44.76), (22, 44.66), (0, 43.0)]
BAND_EDGE_TOP, BAND_EDGE_BOTTOM = 0.5, 0.45
SPAN = 34.0                                            # redrawn azimuth range, each side
BODY_INSET = 0.25      # the grey body stops inside the white edges (they are 0.45-0.5 deep), so its grown pieces
                       # never show past them
GROW = 0.6             # texels each projected piece grows about its centroid, closing the seams between pieces


def mirrored(half):
    """[(az, h), ...] for az >= 0, outermost first, to a left-to-right polyline across the back."""
    left = [(-a, h) for a, h in half]
    right = [(a, h) for a, h in reversed(half) if a != 0]
    return left + right


def interp(half, az):
    pts = sorted(half)
    a = abs(az)
    for (a0, h0), (a1, h1) in zip(pts, pts[1:]):
        if a0 <= a <= a1:
            return h0 + (h1 - h0) * (a - a0) / (a1 - a0)
    return pts[-1][1] if a > pts[-1][0] else pts[0][1]


def offset(half, dh):
    return [(a, h + dh) for a, h in half]


def band_shapes():
    """The band's grey body over its whole outline, then its white top and bottom edges as strips, so the redrawn
    stretch blends into the existing band where it ends (grey on grey, white on white)."""
    top, bottom = mirrored(BAND_TOP), mirrored(BAND_BOTTOM)
    body = mirrored(offset(BAND_TOP, -BODY_INSET)) + list(reversed(mirrored(offset(BAND_BOTTOM, BODY_INSET))))
    upper = top + list(reversed(mirrored(offset(BAND_TOP, -BAND_EDGE_TOP))))
    lower = mirrored(offset(BAND_BOTTOM, BAND_EDGE_BOTTOM)) + list(reversed(bottom))
    return body, upper, lower


def line_shape():
    return mirrored(offset(LINE_CENTRE, LINE_HALF)) + list(reversed(mirrored(offset(LINE_CENTRE, -LINE_HALF))))


def clear_shape():
    """Shell navy from just above the band's top edge to above the upper line, out to +-SPAN: up to 52.45 where the
    stripe is clear of it (|azimuth| >= 12, the dark seam strips beside the old breaks reach 52.3), 0.35 above the line
    at +-8 to 12, and inside +-8 (the stripe's tip) only up to the line itself."""
    top = [(34, 52.45), (12, 52.45), (10, interp(LINE_CENTRE, 10) + LINE_HALF + 0.35),
           (8, interp(LINE_CENTRE, 8) + LINE_HALF + 0.35), (7.9, interp(LINE_CENTRE, 7.9) + LINE_HALF),
           (0, interp(LINE_CENTRE, 0) + LINE_HALF)]
    bottom = [(a, interp(BAND_TOP, a) + 0.08) for a in (34, 30, 26, 22, 14, 5)] + [(0, BAND_TOP[-1][1] + 0.08)]
    return mirrored(top) + list(reversed(mirrored(bottom)))


def design():
    body, upper, lower = band_shapes()
    return {"clear": clear_shape(), "band_gray": body, "band_top": upper, "band_bottom": lower, "line": line_shape()}


# -- projection through the mesh (authoring only) --------------------------------------------------------------------

def _mesh(path, name="HI_HELMET_C"):
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    blob = (path.parent / doc["buffers"][0]["uri"]).read_bytes()

    def acc(i):
        a = doc["accessors"][i]
        view = doc["bufferViews"][a["bufferView"]]
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}[a["type"]]
        dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32}[a["componentType"]]
        at = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = view.get("byteStride", 0)
        size = np.dtype(dt).itemsize * n
        if stride and stride != size:
            raw = np.frombuffer(blob, np.uint8, count=stride * a["count"], offset=at).reshape(a["count"], stride)
            return raw[:, :size].copy().view(dt).reshape(a["count"], n)
        return np.frombuffer(blob, dt, count=a["count"] * n, offset=at).reshape(a["count"], n)

    for prim in doc["meshes"][0]["primitives"]:
        if doc["materials"][prim["material"]]["name"] == name:
            P = acc(prim["attributes"]["POSITION"]).astype(np.float64)
            T = acc(prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
            index = acc(prim["indices"]).ravel()
            tris = [(index[k], index[k + 1], index[k + 2]) for k in range(len(index) - 2)
                    if len({index[k], index[k + 1], index[k + 2]}) == 3]
            return P, T, tris
    raise KeyError(name)


def _clip(poly, tri):
    area = (tri[1][0] - tri[0][0]) * (tri[2][1] - tri[0][1]) - (tri[1][1] - tri[0][1]) * (tri[2][0] - tri[0][0])
    s = 1 if area > 0 else -1
    for k in range(3):
        a, b = tri[k], tri[(k + 1) % 3]
        side = lambda p: s * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))
        out = []
        for i in range(len(poly)):
            p, q = poly[i - 1], poly[i]
            sp, sq = side(p), side(q)
            if sq >= -1e-9:
                if sp < -1e-9:
                    t = sp / (sp - sq)
                    out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
                out.append(q)
            elif sp >= -1e-9:
                t = sp / (sp - sq)
                out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
        poly = out
        if not poly:
            break
    return poly


def project(mesh, shape, grow=GROW, reach=60.0):
    """Clip a design polygon against every back shell triangle and map each piece through that triangle's UVs
    (texel units), each piece grown ``grow`` texels about its centroid so neighbouring pieces close up."""
    P, T, tris = mesh
    pieces = []
    for a, b, c in tris:
        D = [(math.degrees(math.atan2(P[i][0], -(P[i][2] - ZC))), float(P[i][1])) for i in (a, b, c)]
        if max(d[0] for d in D) - min(d[0] for d in D) > 90 or min(abs(d[0]) for d in D) > reach:
            continue
        M = np.array([[D[1][0] - D[0][0], D[2][0] - D[0][0]], [D[1][1] - D[0][1], D[2][1] - D[0][1]]])
        if abs(np.linalg.det(M)) < 1e-9:
            continue
        Mi = np.linalg.inv(M)
        UV = np.array([T[a], T[b], T[c]]) * 256.0
        cut = _clip(list(shape), D)
        if len(cut) < 3:
            continue
        q = []
        for x, y in cut:
            l1, l2 = Mi @ np.array([x - D[0][0], y - D[0][1]])
            u = UV[0] + l1 * (UV[1] - UV[0]) + l2 * (UV[2] - UV[0])
            q.append((float(u[0]), float(u[1])))
        q = np.array(q)
        if np.ptp(q[:, 0]) < 1e-3 or np.ptp(q[:, 1]) < 1e-3:
            continue
        centre = q.mean(axis=0)
        out = []
        for p in q:
            v = p - centre
            n = np.linalg.norm(v)
            out.append([round(float(x), 3) for x in (p + (v / n * grow if n > 1e-9 else 0))])
        pieces.append(out)
    return pieces


def write_shapes(mesh_path):
    mesh = _mesh(mesh_path)
    d = design()
    doc = {"source": "sea1 (b773): the Seahawks helmet back (band, upper V line, the gap between them) designed in "
                     "shell (azimuth, height) space on the HI_HELMET_C mesh and projected through each shell "
                     "triangle's UVs; texel-space pieces only (no game art). Azimuth 0 is the back centre; heights "
                     "are model units.",
           "design": {k: [[round(a, 3), round(h, 3)] for a, h in v] for k, v in d.items()},
           "layers": {k: project(mesh, v) for k, v in d.items()}}
    with SHAPES.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(doc, stream, indent=None, separators=(",", ":"))
        stream.write("\n")
    print("pieces", {k: len(v) for k, v in doc["layers"].items()})


def helmet_ops():
    layers = json.loads(SHAPES.read_text(encoding="utf-8"))["layers"]
    # Repainted texels take alpha 255 (as uf3's Washington W): the shell's reflection mask is 233-251 in scattered
    # texels here, and the compiler keeps a texel's alpha, so those would quantise to the few colours the palette
    # holds at that alpha (navy) and come back as dark specks in the band.
    return crown_ops() + [{"op": "multipoly", "color": NAVY, "alpha": 255, "polys": layers["clear"]},
                          {"op": "multipoly", "color": GRAY, "alpha": 255, "polys": layers["band_gray"]},
                          {"op": "multipoly", "color": WHITE, "alpha": 255,
                           "polys": layers["band_top"] + layers["band_bottom"]},
                          {"op": "multipoly", "color": WHITE, "alpha": 255, "polys": layers["line"]}]


# The navy/grey-pants combo (26H4/26A4, uf2's copy of the same shell art) also kept red dotted lines from an older
# pass on the back: two ticks over the band ends and a ")" under the band at azimuth -12..-17 (26H0 has shell navy
# there). Measured on the v0.6.1 26H4 art; the blends beside the ticks take 26H0's values.
ALT_REMNANTS = [
    (NAVY, [(119, 74), (120, 74), (119, 181), (120, 181), (178, 212), (179, 212), (177, 213), (178, 213), (176, 214),
            (177, 214), (176, 215), (177, 215), (177, 216), (178, 216), (178, 217), (179, 217), (179, 218),
            (180, 218)]),
    ("#475D73", [(119, 73), (120, 73)]),
    ("#7D8D9C", [(120, 182)]),
]


def alt_ops():
    return [{"op": "texels", "color": colour, "alpha": 255, "points": [list(p) for p in points]}
            for colour, points in ALT_REMNANTS]


DIGIT_SCALE = [3, 5]


def entries():
    rows = []
    for sel in HELMETS:
        alt = sel.endswith("4")
        note = ("the side A logo's wing tip painted out of the crown-stripe island (the stripe's own mirrored "
                "pattern), and the helmet back's white upper V line, band edges and the gap between them redrawn "
                "whole across the island seams; the band and its chevron stay")
        rows.append({"selector": sel, "chunk": 12, "texture": "helmet02", "kind": "txtr", "size": [256, 256, 6],
                     "defects": ["noah-1014-SEA-crown-fragment", "noah-1014-SEA-helmet-back-lines"],
                     "note": note + ("; the old red dotted remnants on the back painted shell navy" if alt else ""),
                     "ops": helmet_ops() + (alt_ops() if alt else [])})
    for sel in DIGITS:
        for d in range(10):
            rows.append({"selector": sel, "chunk": 33 + d, "texture": "an%d" % (48 + d), "kind": "palette",
                         "defects": ["noah-1014-SEA-shoulder-numbers"],
                         "note": "shoulder (TV) digit darkened to 3/5 so it reads wolf grey like the chest numbers "
                                 "(the game lights shoulder digits 1.5-2x brighter, so it showed white); "
                                 "26H4 lime outline is mapped to the same plain wolf grey",
                         "map": [{"from": ["#000000"], "tolerance": 255, "transparent": True,
                                  **({"scale": DIGIT_SCALE} if sel == "26H0" else {"to": "#636769"})}]})
    return sorted(rows, key=lambda r: (r["selector"], r["chunk"]))


# -- commands --------------------------------------------------------------------------------------------------------

def preview(tex: Path, out: Path) -> None:
    from PIL import Image
    out.mkdir(parents=True, exist_ok=True)
    for row in entries():
        if row["kind"] != "txtr":
            continue
        src = tex / f"{row['selector']}_c{row['chunk']}.png"
        rgba = np.asarray(Image.open(src).convert("RGBA")).copy()
        painted, scope = fixes.paint(rgba, row["ops"])
        Image.fromarray(painted).save(out / f"{row['selector']}_c{row['chunk']}_sea1.png")
        print(row["selector"], row["chunk"], "scope texels", int(scope.sum()))


def data(disc: Path, out: Path) -> None:
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    rows = entries()
    with bump._Image.open(disc, writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
        for row in rows:
            entry = by_name[row["selector"] + ".IFF"]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            chunk = fixes._chunk_for(raw, row["chunk"])
            span = raw[chunk.offset:chunk.end_offset]
            if row["kind"] == "palette":
                new, detail = fixes.compile_palette(span, row)
                detail = dict(entries=len(detail["palette_entries"]))
            else:
                new, detail = fixes.compile_texture(span, row)
                detail = dict(added=len(detail["palette_slots_added"]), scope=detail["level0_scope_texels"])
            print(row["selector"], row["chunk"], row["texture"], json.dumps(detail), flush=True)
            row.update(resource_size=len(raw), offset=chunk.offset, length=len(span),
                       before_sha256=fixes.sha(span), after_sha256=fixes.sha(new))
    document = {"schema": fixes.SCHEMA,
                "source": "sea1 (b773): Noah's 10/14 Seattle notes on the v0.6.1 fixes disc: the logo fragment on "
                          "the crown stripe, white shoulder numbers, the helmet back's broken lines and spear",
                "method": "Vector art in native texel coordinates, drawn at 4x (4x4 samples per texel, exact "
                          "integer arithmetic) and averaged onto the existing native pixels; palette-only darkening "
                          "for the shoulder digits; fixed spans. Runs after the uf1, uf2 and uf3 layers.",
                "textures": [{k: row[k] for k in ("selector", "chunk", "texture", "kind", "size", "resource_size",
                                                  "offset", "length", "before_sha256", "after_sha256", "defects",
                                                  "note", "ops", "map")
                              if k in row} for row in rows]}
    with out.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=1)
        stream.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("project")
    j.add_argument("--mesh", type=Path, required=True)
    p = sub.add_parser("preview")
    p.add_argument("--tex", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    d = sub.add_parser("data")
    d.add_argument("--input", type=Path, required=True)
    d.add_argument("--out", type=Path, default=DATA)
    args = parser.parse_args(argv)
    if args.cmd == "project":
        write_shapes(args.mesh)
    elif args.cmd == "preview":
        preview(args.tex, args.out)
    else:
        data(args.input, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
