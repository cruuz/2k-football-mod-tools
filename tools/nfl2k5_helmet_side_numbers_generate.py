#!/usr/bin/env python3
"""Generate helmet number set E (b81 helmet-sides): the player's number on BOTH sides of the helmet. Offline tool.

Reads outer 3 of a retail or SOFTDRINK disc (or an extracted copy) and writes ``data/nfl2k5_hair_styles/numbers.json``,
the geometry the player-scene growth (``nfl2k5_hair_styles``) adds as three new materials ``NUMBER_helmet_E_L/M/R``
in hi_head (o3c115) and lo_body (o3c113). Nothing here runs during a build. No photo pixels go into the data.

Owner's words (beta 81): the 2026 Chargers helmet carries the number "on the right part of the helmet"; the owner
then asked for it "for this release". The real helmet has the number large on EACH side under the bolt and none at
the back (club photographs, refs/LAC: lac_a_27a Vidal 28, lac_a_31a Tuipulotu 45, lac_a_32a McConkey 15).

Layout, measured on those photographs in the frame crown-top -> ear-hole centre (D = their vertical distance):
* glyph height 0.372 D (0.357, 0.390, 0.370), centre 0.430 D below the crown (0.405, 0.441, 0.446) and 0.044 D behind
  the ear hole (0.026, 0.039, 0.066); two digits stand almost touching, each glyph 0.52 of its height wide.
* The game's Chargers helmet art paints the bolt about 2.5 cm lower on the shell than the real helmet carries it: its
  lower edge runs at y 50.1..51.6 over the number's width on both shells (24H0/24A0 helmet00 and helmet02 sampled on
  the shell surface), and the Modern helmets side vent and jaw seam (LOGO_helmet_C) reach up to y 44.5. The photographs
  put the number right under the bolt, so the glyph spans y 44.65..50.25 (0.25 clear of each): 5.6 tall, 0.85 of the
  photo-relative 6.6, centred over the ear hole as photographed.
* On the model (shell A: crown y 57.29, ear hole y 39.53 z 9.27, D = 17.76) the kit's 32 x 32 helmet digit draws its
  glyph in rows 1..30 and columns 6..25 (the 2026 Chargers art); the binder samples u' 0.167..0.836, v' 0..1 of it
  (U scale 4, V scale 2 on the model's own window, set D's). So a cell is ``Hq = glyph / 0.9375`` tall and
  ``W = 0.53 Hq`` wide, and the tens and ones cells touch.

Geometry per scene and cell: two curved patches (the helmet's left side +X and right side -X), 3 x 3 vertices each,
laid out in the tangent plane at the number's centre and projected along its normal onto the OUTER of the two
Riddell shells (HI_HELMET_A Standard, HI_HELMET_C Revolution) plus a clearance like the retail rear sets'. Reading
direction: on the right side the tens digit is toward the back, on the left side toward the face, so both read
correctly from outside. Texture coordinates are set D's corner coordinates of the same cell (bilinear), so the
digits are bound and scaled exactly as set D's. Every vertex record is set D's record of the same cell with the
position, normal, texture coordinate (and, in lo_body, the tangent frame) rewritten: same skin selector, so the
number rides the head. lo_body takes the same layout through the affine map that carries the four retail number
sets (A..D, 68 vertices) from hi_head to lo_body, projected onto lo_body's own shells.

Usage::

    nfl2k5_helmet_side_numbers_generate.py --disc XISO [--out data/nfl2k5_hair_styles/numbers.json] [--report R.json]
"""
from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import numpy as np  # noqa: E402

from mod_editor.core import nfl2k5_hair_styles as hair  # noqa: E402
from mod_editor.core import nfl2k5_models as models  # noqa: E402
from nfl2k5_hair_styles_generate import Scene  # noqa: E402

SCHEMA = "nfl2k5_hair_styles/numbers/v1"
CELLS = ("L", "M", "R")
SHELLS = ("HI_HELMET_A", "HI_HELMET_C")
# photographs (fractions of D = crown-top to ear-hole centre, vertical); see the module docstring
GLYPH_HEIGHT = 0.372
CENTRE_BELOW_CROWN = 0.430
CENTRE_BEHIND_EAR = 0.044
GLYPH_ROWS = 30.0 / 32.0          # the kit digit's glyph fills rows 1..30 of 32
CELL_ASPECT = 0.53                # cell width / cell height: glyph 0.52 of its height wide (photographs)
CLEARANCE = 0.25                  # model units above the outer shell (the retail rear sets sit 0.2-0.5 off the shell)
GLYPH_TOP = 50.25                 # 0.25 under the game's painted bolt (lowest edge y 50.5 over the number's width)
GLYPH_BOTTOM = 44.65              # 0.15 over the Modern helmets side vent (LOGO_helmet_C up to y 44.5)
GRID = 3                          # vertices per patch edge


def shell_tris(sc: Scene, names) -> np.ndarray:
    t = sc.tris(set(names))
    return sc.pos[t]


def ray_hits(origin, direction, tris):
    """Parameters t >= 0 of every hit of origin + t*direction with the triangles, and the triangle normals."""
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    h = np.cross(direction, e2)
    a = np.einsum("ij,ij->i", e1, h)
    ok = np.abs(a) > 1e-9
    f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
    s = origin - v0
    u = f * np.einsum("ij,ij->i", s, h)
    q = np.cross(s, e1)
    v = f * np.einsum("j,ij->i", direction, q)
    t = f * np.einsum("ij,ij->i", e2, q)
    hit = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & (t >= 0)
    n = np.cross(e1, e2)
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return t[hit], n[hit]


def outer_hit(origin, direction, shells):
    """First surface met coming in from outside along ``direction``: (point, outward normal, per-shell distance)."""
    best_t, best_n, per = None, None, {}
    for name, tris in shells.items():
        t, n = ray_hits(origin, direction, tris)
        if len(t) == 0:
            per[name] = None
            continue
        k = int(np.argmin(t))
        per[name] = float(t[k])
        if best_t is None or t[k] < best_t:
            best_t, best_n = float(t[k]), n[k]
    if best_t is None:
        raise SystemExit(f"no shell under {origin} along {direction}")
    point = origin + best_t * direction
    normal = best_n if np.dot(best_n, -direction) > 0 else -best_n
    return point, normal, per


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def corners(sc: Scene, cell: str):
    """Set D's cell: vertex ids, and its corner texture coordinates (top-left, top-right, bottom-left, bottom-right
    as seen from outside, behind the helmet: viewer's right = -X, up = +Y)."""
    rows = [s for s in sc.subs if s["material_name"] == f"NUMBER_helmet_D_{cell}"]
    assert len(rows) == 1, cell
    ids = sorted({v for t in sc.tris({f"NUMBER_helmet_D_{cell}"}) for v in t})
    assert len(ids) == 4, (cell, ids)
    P = sc.pos[ids]
    a = -P[:, 0]
    b = P[:, 1]
    left, top = a < a.mean(), b > b.mean()
    pick = {}
    for name, (want_left, want_top) in {"tl": (1, 1), "tr": (0, 1), "bl": (1, 0), "br": (0, 0)}.items():
        k = [i for i in range(4) if left[i] == want_left and top[i] == want_top]
        assert len(k) == 1, (cell, name)
        pick[name] = sc.uv[ids[k[0]]]
    return ids, pick


def d_facing(sc: Scene) -> float:
    """+1 when set D's triangles (as Scene.tris orders them) face out of the helmet (-Z), else -1."""
    t = sc.tris({f"NUMBER_helmet_D_{c}" for c in CELLS})
    P = sc.pos[t]
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    s = np.sign(n[:, 2] * -1.0)
    assert (s == s[0]).all(), "set D triangles face both ways"
    return float(s[0])


def patch_strips(flip: bool) -> list[list[int]]:
    """Two strips (the two bands of a 3 x 3 grid, row-major, top row first, left column first)."""
    bands = []
    for j in range(GRID - 1):
        s = []
        for i in range(GRID):
            top, bottom = j * GRID + i, (j + 1) * GRID + i
            s += [bottom, top] if flip else [top, bottom]
        bands.append(s)
    return bands


def strip_tris(strip):
    out = []
    for k in range(len(strip) - 2):
        t = strip[k:k + 3]
        if len(set(t)) == 3:
            out.append(tuple(t) if k % 2 == 0 else (t[1], t[0], t[2]))
    return out


class Layout:
    """The number's frame on one side of one scene."""

    def __init__(self, centre, normal, side):
        self.centre, self.normal = np.asarray(centre, float), unit(normal)
        up = np.array([0.0, 1.0, 0.0])
        up = unit(up - np.dot(up, self.normal) * self.normal)
        ahead = np.array([0.0, 0.0, 1.0 if side < 0 else -1.0])      # viewer's right: face on the right side (-X)
        right = ahead - np.dot(ahead, self.normal) * self.normal - np.dot(ahead, up) * up
        self.up, self.right = up, unit(right)


def build_scene(sc: Scene, shells, frames, sizes, record_of, uv_of, flip, clearance, lo_tangents):
    """Records and strips of the three cells. ``frames``: side -> Layout; sizes: (Hq, W)."""
    lanes = sc.lanes
    hq, w = sizes
    pos_off = lanes.position_offset
    nrm = lanes.normal
    tex = lanes.texcoord
    stream_offsets = {}
    at = 0
    for si in sorted(sc.streams):
        stream_offsets[si] = at
        at += sc.streams[si][1]
    record_size = at
    cells, checks = {}, []
    span = {"L": (-w, 0.0), "M": (-w / 2, w / 2), "R": (0.0, w)}
    for cell in CELLS:
        records = bytearray()
        strips = []
        base = record_of(cell)
        assert len(base) == record_size
        uvc = uv_of(cell)
        a0, a1 = span[cell]
        for side_index, side in enumerate((+1, -1)):
            fr = frames[side]
            for j in range(GRID):
                bt = hq / 2 - hq * j / (GRID - 1)
                fy = j / (GRID - 1)
                for i in range(GRID):
                    ai = a0 + (a1 - a0) * i / (GRID - 1)
                    fx = i / (GRID - 1)
                    q = fr.centre + ai * fr.right + bt * fr.up
                    p, n, per = outer_hit(q + 6.0 * fr.normal, -fr.normal, shells)
                    v = p + clearance * fr.normal
                    t_best = min(d for d in per.values() if d is not None)
                    gaps = {k: (None if d is None else round(float(d - t_best + clearance), 3)) for k, d in per.items()}
                    checks.append(dict(cell=cell, side="left" if side > 0 else "right", i=i, j=j,
                                       pos=[round(float(x), 3) for x in v], gap=gaps))
                    uv = ((1 - fx) * (1 - fy) * uvc["tl"] + fx * (1 - fy) * uvc["tr"]
                          + (1 - fx) * fy * uvc["bl"] + fx * fy * uvc["br"])
                    rec = bytearray(base)
                    so = stream_offsets[lanes.position_stream] + pos_off
                    qv = tuple(models.encode_normshort(max(-1.0, min(1.0, (float(v[k]) - lanes.offset[k]) / lanes.scale)))
                               for k in range(3))
                    struct.pack_into("<3h", rec, so, *qv)
                    nn = unit(n)
                    struct.pack_into("<I", rec, stream_offsets[nrm[0]] + nrm[1], models.encode_normpacked3(*nn))
                    uu, vv = models.uv_from_gltf(float(uv[0]), float(uv[1]), lanes.uv_scale, lanes.uv_offset)
                    struct.pack_into("<hh", rec, stream_offsets[tex[0]] + tex[1], uu, vv)
                    if lo_tangents:
                        t = np.cross(np.array([0.0, 1.0, 0.0]), nn)
                        t = unit(t) if np.linalg.norm(t) > 1e-6 else np.array([1.0, 0.0, 0.0])
                        b = np.cross(nn, t)
                        s2 = max(sc.streams)
                        struct.pack_into("<II", rec, stream_offsets[s2], models.encode_normpacked3(*t),
                                         models.encode_normpacked3(*b))
                    records += rec
            first = side_index * GRID * GRID
            strips += [[first + k for k in band] for band in patch_strips(flip[side])]
        cells[cell] = dict(records=bytes(records), strips=strips)
    return cells, checks, record_size


def b64_lines(data: bytes, width: int = 4000) -> list[str]:
    text = base64.b64encode(data).decode("ascii")
    return [text[i:i + width] for i in range(0, len(text), width)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--disc", required=True)
    ap.add_argument("--out", default=str(ROOT / "data" / "nfl2k5_hair_styles" / "numbers.json"))
    ap.add_argument("--report")
    args = ap.parse_args(argv)
    with hair._archive().Disc(Path(args.disc), descriptors=()) as disc:
        _entry, coll = hair._outer3(disc)
    chunks = hair._chunks(coll)
    scenes = {}
    for key in (hair.HI, hair.LO):
        decoded = hair.decode_span(hair._chunk_span(coll, chunks[models.parse_model_key(key)[1]]))
        scenes[key] = Scene(key, hair.retail_shaped(key, decoded))
    hi, lo = scenes[hair.HI], scenes[hair.LO]
    # landmarks on shell A of hi_head
    shell_a = shell_tris(hi, ["HI_HELMET_A"])
    pts = shell_a.reshape(-1, 3)
    crown_y = float(pts[:, 1].max())
    ear = np.array([0.0, 39.53, 9.27])      # ear-hole centre of shell A (boundary loop, work/geo/landmarks_hi.json)
    d = crown_y - ear[1]
    glyph = GLYPH_TOP - GLYPH_BOTTOM                  # the photographs' 0.372 D does not fit under the game's bolt
    hq = glyph / GLYPH_ROWS
    w = CELL_ASPECT * hq
    cy = (GLYPH_TOP + GLYPH_BOTTOM) / 2
    cz = ear[2] - CENTRE_BEHIND_EAR * d
    hi_shells = {n: shell_tris(hi, [n]) for n in SHELLS}
    lo_shells = {n: shell_tris(lo, [n]) for n in SHELLS}
    # hi -> lo affine map from the four retail number sets
    names = [f"NUMBER_helmet_{s}_{c}" for s in "ABCD" for c in CELLS]
    src, dst = [], []
    for n in names:
        hv = sorted({v for t in hi.tris({n}) for v in t})
        lv = sorted({v for t in lo.tris({n}) for v in t})
        assert len(hv) == len(lv), n
        src += [hi.pos[v] for v in hv]
        dst += [lo.pos[v] for v in lv]
    src, dst = np.array(src), np.array(dst)
    X = np.hstack([src, np.ones((len(src), 1))])
    M, *_ = np.linalg.lstsq(X, dst, rcond=None)
    residual = float(np.abs(X @ M - dst).max())
    A, t0 = M[:3].T, M[3]
    report = dict(crown_y=crown_y, ear=ear.tolist(), D=d, glyph=glyph, photo_glyph=GLYPH_HEIGHT * d,
                  photo_centre_y=crown_y - CENTRE_BELOW_CROWN * d, cell_height=hq, cell_width=w,
                  centre_yz=[cy, cz], hi_to_lo=dict(matrix=A.tolist(), offset=t0.tolist(), max_residual=residual))
    flips = {}
    out_scenes = {}
    for key, sc, shells, mapped in ((hair.HI, hi, hi_shells, False), (hair.LO, lo, lo_shells, True)):
        frames = {}
        sizes = (hq, w)
        for side in (+1, -1):
            c0 = np.array([0.0, cy, cz])
            direction = np.array([float(side), 0.0, 0.0])
            if mapped:
                c0 = A @ c0 + t0
            p, n, _per = outer_hit(c0 + 20.0 * direction, -direction, shells)
            frames[side] = Layout(p, n, side)
        if mapped:
            scale = float(np.cbrt(abs(np.linalg.det(A))))
            sizes = (hq * scale, w * scale)
        facing = d_facing(sc)
        # choose each side's band order so its triangles face out the way set D's do
        flip = {}
        for side, fr in frames.items():
            grid = [fr.centre + (i - 1) * fr.right + (1 - j) * fr.up for j in range(GRID) for i in range(GRID)]
            tri = strip_tris(patch_strips(False)[0])[0]
            nrm = np.cross(grid[tri[1]] - grid[tri[0]], grid[tri[2]] - grid[tri[0]])
            flip[side] = bool(np.sign(np.dot(nrm, fr.normal)) != facing)
        flips[key] = {("left" if s > 0 else "right"): f for s, f in flip.items()}
        cell_ids = {c: corners(sc, c)[0] for c in CELLS}
        rec_size = sum(st[1] for st in sc.streams.values())

        def record_of(cell, sc=sc, cell_ids=cell_ids):
            v = cell_ids[cell][0]
            return b"".join(sc.d[off + v * stride: off + (v + 1) * stride] for _s, (off, stride) in sorted(sc.streams.items()))

        def uv_of(cell, sc=sc):
            return {k: np.asarray(u, float) for k, u in corners(sc, cell)[1].items()}

        cells, checks, record_size = build_scene(sc, shells, frames, sizes, record_of, uv_of, flip,
                                                 CLEARANCE * (sizes[0] / hq), lo_tangents=len(sc.streams) > 2)
        assert record_size == rec_size
        # every triangle faces out like set D's
        for cell, item in cells.items():
            P = []
            for k in range(len(item["records"]) // record_size):
                rec = item["records"][k * record_size:(k + 1) * record_size]
                so = sum(sc.streams[s][1] for s in sorted(sc.streams) if s < sc.lanes.position_stream) + sc.lanes.position_offset
                q = struct.unpack_from("<3h", rec, so)
                P.append([models.normshort(q[a]) * sc.lanes.scale + sc.lanes.offset[a] for a in range(3)])
            P = np.array(P)
            for band in item["strips"]:
                for tri in strip_tris(band):
                    nrm = np.cross(P[tri[1]] - P[tri[0]], P[tri[2]] - P[tri[0]])
                    outward = np.array([np.sign(P[tri[0]][0]), 0.0, 0.0])
                    assert np.sign(np.dot(nrm, outward)) == facing, (key, cell, tri)
        gaps = [g for c in checks for g in c["gap"].values() if g is not None]
        report[key] = dict(frames={("left" if s > 0 else "right"): dict(centre=f.centre.round(3).tolist(),
                                                                     normal=f.normal.round(3).tolist(),
                                                                     right=f.right.round(3).tolist(),
                                                                     up=f.up.round(3).tolist())
                                   for s, f in frames.items()},
                           sizes=list(sizes), flips=flips[key], gap_min=min(gaps), gap_max=max(gaps), vertices=checks)
        out_scenes[key] = {"vertex_count": sc.n, "strides": [sc.streams[s][1] for s in sorted(sc.streams)],
                           "cells": {c: {"records": b64_lines(v["records"]),
                                         "strips": [b64_lines(struct.pack(f"<{len(s)}H", *s)) for s in v["strips"]]}
                                     for c, v in cells.items()}}
    document = {"schema": SCHEMA,
                "materials": [f"NUMBER_helmet_E_{c}" for c in CELLS],
                "templates": [f"NUMBER_helmet_D_{c}" for c in CELLS],
                "layout": {k: v for k, v in report.items() if k not in (hair.HI, hair.LO)},
                "scenes": out_scenes}
    Path(args.out).write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
    if Path(args.out).resolve() == hair.NUMBERS_PATH.resolve():
        # the growth's pins follow the shipped files (hair.record_pins); every other pin must stay what it was
        old = json.loads(hair.PINS_PATH.read_text())
        new = hair.record_pins(coll)
        changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
        if changed != ["numbers_sha256"]:
            raise SystemExit(f"pins other than numbers_sha256 would change: {changed}")
        hair.PINS_PATH.write_text(json.dumps(new, indent=1, sort_keys=True) + "\n")
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1))
    print(json.dumps({k: (v if k not in (hair.HI, hair.LO) else {kk: vv for kk, vv in v.items() if kk != "vertices"})
                      for k, v in report.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
