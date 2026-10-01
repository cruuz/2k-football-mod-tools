#!/usr/bin/env python3
"""Generate the modern helmet and facemask geometry (beta 76 job hm) from the retail disc.

Offline tool. It reads the user's retail disc (the player body set hi_head o3c115 / lo_body o3c113 and the Guardian
overlay's shell B), builds every authored part and writes the data file the Build step
(``mod_editor.core.nfl2k5_modern_helmets``) copies into the disc. Nothing here runs during a build.

DESIGN, with sources in HM_HELMETS_2026-09-24.md:
* ``--mode revolution`` (the shipped mode, ``data/nfl2k5_modern_helmets/geometry.json``; Noah 9/25: keep the game's
  Riddell helmet and add the modern details): slot C (Revolution, raw 1) keeps the retail shell, so every team's art
  maps exactly as painted, and gains thin dark parts just above it after the Riddell SpeedFlex (US D752,821 and the
  riddell.com team photos): the flex panel's U-shaped cut, vents, the jaw-flap seam and the rear shelf, placed by
  azimuth / elevation around C = (0, 42, 9), around the logos (REV_FEATURES), drawn by the helmet decal submesh;
* masks 12-26 become 15 current Riddell masks (the SpeedFlex SF- catalogue and four Axiom W- masks) with the
  manufacturer's recommended positions, each fitted to riddell.com's front and side product photos of that mask
  (MASK_PHOTO: the bars traced on the front photo, the depth read on the side photo; Noah 9/25: the pass-4 masks were
  "too tall and skinny") and seated on the retail Revolution shell; masks 0-11 and slot A (Standard, raw 0) stay
  retail for the classic scenarios;
* ``--mode speedflex`` (research, not shipped; ``geometry_speedflex.json``) rebuilds the pass-3 SpeedFlex shell:
  three Coons patches in direction space around C whose texture coordinates transfer rim to rim from the retail
  shell, kept at least 0.45 cm inside the Guardian cap;
* masks are bars on a per-shell envelope: triangular tubes for the frame and horizontal bars, outward-facing
  ribbons for verticals and connectors; the low LOD draws each mask as a 64 x 64 alpha texture on LO_FACEMASK_C.

Every run ends with the product's refit (author both scenes from the retail disc and refit them into their retail
stored spans) and reports the stored bytes used and the headroom.

Usage::

    nfl2k5_modern_helmets_generate.py --index <pack 0 of vc_53450030> --inventory <nfl2k5_resource_chunks_v2.json>
        [--mode revolution|speedflex] [--out PATH]
"""
from __future__ import annotations

import argparse
import base64
import collections
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_models as models  # noqa: E402
from mod_editor.core import nfl2k5_modern_helmets as mh  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402



# ====================================================================================================
# hmlib
# ====================================================================================================
PACK0: Path | None = None
INVENTORY: Path | None = None
_src = None
def source():
    global _src
    if _src is None:
        _src = models.ModelSource(PACK0, INVENTORY)
    return _src
_topo = None
def topo():
    global _topo
    if _topo is None:
        _topo = models._tools_module("nfl_scne_gltf")
    return _topo

def strip_triangles(mode, idx):
    """Triangles from one decoded NV2A batch (5 list, 6 strip, 7 fan, 8 quads, 9 quad strip); degenerates dropped."""
    mode = int(mode)
    tris = []
    if mode == 6:
        for i in range(len(idx) - 2):
            a, b, c = idx[i], idx[i + 1], idx[i + 2]
            if a == b or b == c or a == c:
                continue
            tris.append((a, b, c) if i % 2 == 0 else (b, a, c))
    elif mode == 5:
        for i in range(0, len(idx) - 2, 3):
            tris.append(tuple(idx[i:i + 3]))
    elif mode == 7:
        for i in range(1, len(idx) - 1):
            tris.append((idx[0], idx[i], idx[i + 1]))
    elif mode == 8:
        for i in range(0, len(idx) - 3, 4):
            a, b, c, d = idx[i:i + 4]
            tris += [(a, b, c), (a, c, d)]
    elif mode == 9:
        for i in range(0, len(idx) - 3, 2):
            a, b, c, d = idx[i:i + 4]
            tris += [(a, b, d), (a, d, c)]
    else:
        raise ValueError(f"unsupported NV2A primitive mode {mode}")
    return [t for t in tris if len(set(t)) == 3]

class Scene:
    def __init__(self, key, span=None):
        src = source()
        if span is not None:
            s2 = models.ModelSpanSource({key: span})
            self.resource, self.decoded, self.scene = s2.parse(key)
        else:
            self.resource, self.decoded, self.scene = src.parse(key)
        self.key = key
        self.shape = self.scene["shapes"][0]
        self.lanes = models._shape_lanes(self.scene, self.shape, self.decoded)
        self.pos = models.read_positions(self.decoded, self.shape, self.lanes)
        self.uvq = models.read_lane_2h(self.decoded, self.shape, self.lanes.texcoord, self.lanes.vertex_count)
        self.uv = [models.uv_to_gltf(u, v, self.lanes.uv_scale, self.lanes.uv_offset) for u, v in self.uvq]
        nw = models.read_lane_u32(self.decoded, self.shape, self.lanes.normal, self.lanes.vertex_count)
        self.nrm = [models.decode_normpacked3(w) for w in nw]
        self.sel = models.read_lane_h(self.decoded, self.shape, self.lanes.selector, self.lanes.vertex_count)
        self.materials = {m["index"]: m for m in self.scene["materials"]}
        self.subs = []
        for s in self.scene["submeshes"]:
            batches = topo().decode_batches(self.decoded, int(s["command_offset"]), int(s["primary_command_word_count"]))
            tris = []
            for mode, b in batches:
                tris += strip_triangles(mode, list(b))
            verts = sorted({i for _, b in batches for i in b})
            self.subs.append(dict(s, material=self.materials[s["material_index"]]["name"], tris=tris, verts=verts,
                                  batches=[(int(m), list(b)) for m, b in batches]))
    def by_material(self, name):
        return [s for s in self.subs if s["material"] == name]

def submesh_dump(scene, names):
    """{material: {'pos','uv','nrm','tris'}} with local indices (game cm, y up, +z forward)."""
    out = {}
    for sub in scene.subs:
        if sub["material"] not in names:
            continue
        verts = sorted({i for t in sub["tris"] for i in t})
        local = {v: k for k, v in enumerate(verts)}
        key = sub["material"] if sub["material"] not in out else f"{sub['material']}#{sub['submesh_index']}"
        out[key] = {"pos": [scene.pos[v] for v in verts], "uv": [scene.uv[v] for v in verts],
                    "nrm": [scene.nrm[v] for v in verts], "tris": [[local[i] for i in t] for t in sub["tris"]]}
    return out

def outer_bytes(outer_index):
    """The whole outer entry payload from the retail pack (read-only)."""
    src = source()
    entry = src.archive.entries[outer_index]
    return src._outer.read_entry_range(src.archive, entry, 0, entry.size)

def txtr_rgba(outer_index, chunk_index, payload=None):
    """(name, width, height, rgba) of a TXTR chunk's base level."""
    tx = models._tools_module("nfl_txtr")
    data = payload if payload is not None else outer_bytes(outer_index)
    chunks = tx.parse_chunks(data, allow_trailing=True)
    ch = chunks[chunk_index]
    out, _ = tx.decode_chunk(data, ch)
    t = tx.parse_texture(out, ch)
    return t.name, t.width, t.height, tx.texture_to_rgba(out, ch, t)


# ====================================================================================================
# shellgen
# ====================================================================================================

C = (0.0, 42.0, 9.0)


def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def norm(a):
    l = math.sqrt(dot(a, a)); return (a[0] / l, a[1] / l, a[2] / l) if l > 1e-12 else (0.0, 0.0, 1.0)
def lerp(a, b, t): return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)
def mirror(p): return (-p[0], p[1], p[2])


def smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0))); return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------------------------- curves

def polyline_resample(points, n):
    """n points evenly spaced by arc length along a polyline (Catmull-Rom smoothed first)."""
    pts = catmull(points, 8)
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(seg)
    out = []
    for k in range(n):
        target = total * k / (n - 1)
        acc = 0.0
        for i, l in enumerate(seg):
            if acc + l >= target or i == len(seg) - 1:
                t = 0.0 if l == 0 else (target - acc) / l
                out.append(lerp(pts[i], pts[i + 1], min(1.0, max(0.0, t))))
                break
            acc += l
    return out


def catmull(points, sub_n):
    if len(points) < 3:
        return list(points)
    out = []
    p = [points[0]] + list(points) + [points[-1]]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for k in range(sub_n):
            t = k / sub_n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[a]) + (-p0[a] + p2[a]) * t + (2 * p0[a] - 5 * p1[a] + 4 * p2[a] - p3[a]) * t2
                                    + (-p0[a] + 3 * p1[a] - 3 * p2[a] + p3[a]) * t3) for a in range(3)))
    out.append(points[-1])
    return out


def coons(top, bottom, left, right, i, j, nu, nv):
    """Coons patch point: top/bottom indexed by u (nu), left/right by v (nv); corners shared."""
    u = i / (nu - 1); v = j / (nv - 1)
    a = lerp(top[i], bottom[i], v)
    b = lerp(left[j], right[j], u)
    c = add(add(mul(top[0], (1 - u) * (1 - v)), mul(top[-1], u * (1 - v))),
            add(mul(bottom[0], (1 - u) * v), mul(bottom[-1], u * v)))
    return sub(add(a, b), c)


# ---------------------------------------------------------------------------------------------- retail islands

def retail_islands(scene, material):
    """{'crown','R','L'}: list of (p0,p1,p2,uv0,uv1,uv2) triangles of the retail shell's three main UV islands."""
    sub_ = scene.by_material(material)[0]
    parent = {}
    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for t in sub_["tris"]:
        for a, b in ((t[0], t[1]), (t[1], t[2])):
            ra, rb = find(a), find(b)
            if ra != rb: parent[ra] = rb
    comps = collections.defaultdict(list)
    for v in sub_["verts"]:
        comps[find(v)].append(v)
    out = {}
    for c, vs in comps.items():
        if len(vs) < 20:
            continue
        xs = [scene.pos[v][0] for v in vs]
        name = "crown" if min(xs) < -2 and max(xs) > 2 else ("R" if sum(xs) > 0 else "L")
        tris = []
        for t in sub_["tris"]:
            if find(t[0]) == c:
                tris.append(tuple(scene.pos[v] for v in t) + tuple(scene.uv[v] for v in t))
        out[name] = tris
    return out


def seam_points(scene, material, side):
    """Retail crown/side seam positions ordered front (high z) to back, side 'R' (x>0) or 'L'."""
    isl = retail_islands(scene, material)
    def keyset(tris):
        return {tuple(round(c, 3) for c in p) for t in tris for p in t[:3]}
    shared = keyset(isl["crown"]) & keyset(isl[side])
    pts = sorted(shared, key=lambda p: -math.atan2(p[2] - C[2], p[1] - C[1]))    # by longitudinal angle, front first
    return pts


def ray_uv(d, tris):
    """UV where the ray C + t d hits the island (nearest hit); else the UV of the angularly nearest vertex."""
    best = None
    for t in tris:
        p0, p1, p2, u0, u1, u2 = t
        e1, e2 = sub(p1, p0), sub(p2, p0)
        h = cross(d, e2); a = dot(e1, h)
        if abs(a) < 1e-12:
            continue
        f = 1.0 / a; s_ = sub(C, p0); u = f * dot(s_, h)
        if u < -1e-6 or u > 1 + 1e-6:
            continue
        q = cross(s_, e1); v = f * dot(d, q)
        if v < -1e-6 or u + v > 1 + 1e-6:
            continue
        tt = f * dot(e2, q)
        if tt > 0 and (best is None or tt < best[0]):
            w = 1 - u - v
            best = (tt, (w * u0[0] + u * u1[0] + v * u2[0], w * u0[1] + u * u1[1] + v * u2[1]))
    if best:
        return best[1], True
    # fallback: project onto the island's boundary (closest point on triangles in direction space)
    bestd, bestuv = 1e9, None
    for t in tris:
        for p, uv in zip(t[:3], t[3:]):
            dd = norm(sub(p, C))
            ang = math.acos(max(-1, min(1, dot(dd, d))))
            if ang < bestd:
                bestd, bestuv = ang, uv
    return bestuv, False


# ---------------------------------------------------------------------------------------------- mesh assembly

def grid_strip(rows, base=0):
    """Triangle strip indices covering a grid given as rows of vertex indices (each row same length)."""
    strips = []
    for r in range(len(rows) - 1):
        a, b = rows[r], rows[r + 1]
        strip = []
        for i in range(len(a)):
            strip += [a[i], b[i]]
        strips.append(strip)
    return strips


def orient_strip(strip, pos, out):
    """The sub-strip with its winding facing out(vertex): one leading duplicate flips every triangle of a strip.
    Retail parts wind every triangle with its stored normal (cross(b - a, c - a) . n > 0, PROVED OFFLINE on the retail
    helmets and masks), and the game may cull the other side."""
    vote = 0
    for a, b, c in strip_tris(strip):
        n = cross(sub(pos[b], pos[a]), sub(pos[c], pos[a]))
        o = add(add(out(a), out(b)), out(c))
        vote += 1 if dot(n, o) > 0 else -1
    if vote >= 0:
        return list(strip)
    # an odd-length strip read backwards is the same triangles wound the other way; otherwise lead with a duplicate
    return list(reversed(strip)) if len(strip) % 2 else [strip[0]] + list(strip)


def join_strips(strips, pos=None, out=None):
    """One strip from several; each keeps its own triangle parity. With pos and out (vertex -> the direction its
    face should look), each sub-strip is first oriented to face out."""
    out_ = []
    for strip in strips:
        if len(strip) < 3:
            continue
        if pos is not None and out is not None:
            strip = orient_strip(strip, pos, out)
        if out_:
            out_ += [out_[-1], strip[0]]
            if len(out_) % 2:
                out_.append(strip[0])
        out_ += strip
    return out_


def strip_tris(idx):
    tris = []
    for i in range(len(idx) - 2):
        a, b, c = idx[i], idx[i + 1], idx[i + 2]
        if a == b or b == c or a == c:
            continue
        tris.append((a, b, c) if i % 2 == 0 else (b, a, c))
    return tris


def vertex_normals(pos, tris):
    acc = [(0.0, 0.0, 0.0)] * len(pos)
    for a, b, c in tris:
        n = cross(sub(pos[b], pos[a]), sub(pos[c], pos[a]))
        for k in (a, b, c):
            acc[k] = add(acc[k], n)
    return [norm(n) for n in acc]


# ---------------------------------------------------------------------------------------------- shell builder

def dirs_of(points):
    return [norm(sub(p, C)) for p in points]


def slerp_dir(a, b, t):
    return norm(lerp(a, b, t))


def build_shell(design, scene, material, nt, nc, ns, *, mirror_x=True):
    """A shell mesh: dict(pos, uv, tris, strip, islands) from a design (boundary anchors + radius function).

    design: dict with
      'brow'      : right-half brow edge points from the centre (x=0) outwards to the seam-crossing and on to the
                    temple (list of 3D points, x >= 0), used as the crown's t=0 edge and the start of the side's edge
      'face_side' : face-opening side edge from the temple down to the jaw corner J (3D points)
      'lower'     : lower rim from J back to the rear-side corner K (3D points)
      'rear'      : rear rim from K round to the centre back (x=0) (3D points)
      'radius'    : function(direction) -> radius in cm
    The crown/side seam is the retail seam, extended to the new rims."""
    isl = retail_islands(scene, material)
    seamR = seam_points(scene, material, "R")
    # retail seam as directions, front -> back; extend by the design's rims
    seam_dirs = dirs_of(seamR)
    radius = design["radius"]
    # boundary curves in direction space (right half, x >= 0)
    brow = dirs_of(design["brow"])            # centre -> temple
    face = dirs_of(design["face_side"])       # temple -> J
    lower = dirs_of(design["lower"])          # J -> K
    rear = dirs_of(design["rear"])            # K -> centre back
    # seam: from where it meets the brow to where it meets the rear rim
    def closest_param(curve, target):
        best = min(range(len(curve)), key=lambda i: math.acos(max(-1, min(1, dot(curve[i], target)))))
        return best
    brow_f = [lerp_dir_curve for lerp_dir_curve in brow]
    # dense resample of all boundary curves
    brow_d = resample_dirs(brow, 64)
    rear_d = resample_dirs(rear, 64)
    seam_front = seam_dirs[0]; seam_back = seam_dirs[-1]
    ib = closest_param(brow_d, seam_front)
    ir = 0                                   # the retail seam ends at the rear-side corner K
    seam_curve = [brow_d[ib]] + seam_dirs[1:-1] + [rear_d[ir]]
    seam_curve = resample_dirs(seam_curve, nt)
    # crown patch: u across (right seam -> left seam), t front -> back
    crown_front_half = resample_dirs(list(reversed(brow_d[:ib + 1])), (nc + 1) // 2 + 1)   # seam -> centre
    crown_back_half = resample_dirs(rear_d[ir:], (nc + 1) // 2 + 1)                     # seam -> centre
    def full_row(half):     # right seam -> centre -> left seam
        left = [mirror(p) for p in reversed(half[:-1])]
        row = half + left
        return resample_dirs(row, nc)
    crown_top = full_row(crown_front_half)
    crown_bot = full_row(crown_back_half)
    seam_L = [mirror(p) for p in seam_curve]
    # side patch (right): u from seam (0) to lower rim (1); t front (0) -> back (1)
    face_edge = resample_dirs(brow_d[ib:] + face[1:], ns)                    # seam front point -> J
    lower_edge = resample_dirs(lower, nt)                                      # J -> K  (t)
    rear_edge = [rear_d[0]] * ns                                              # collapsed at K (3-sided side patch)
    verts, uvs, isl_of = [], [], []
    rows_crown, rows_R, rows_L = [], [], []
    for j in range(nt):
        row = []
        for i in range(nc):
            d = norm(coons(crown_top, crown_bot, seam_curve, seam_L, i, j, nc, nt))
            row.append(len(verts)); verts.append(d); isl_of.append("crown")
        rows_crown.append(row)
    for side, sgn in (("R", 1), ("L", -1)):
        rows = []
        for j in range(nt):
            row = []
            for i in range(ns):
                top = face_edge if sgn > 0 else [mirror(p) for p in face_edge]
                bot = rear_edge if sgn > 0 else [mirror(p) for p in rear_edge]
                le = seam_curve if sgn > 0 else seam_L
                ri = lower_edge if sgn > 0 else [mirror(p) for p in lower_edge]
                d = norm(coons(top, bot, le, ri, i, j, ns, nt))
                row.append(len(verts)); verts.append(d); isl_of.append(side)
            rows.append(row)
        (rows_R if side == "R" else rows_L).extend(rows)
    pos = [add(C, mul(d, radius(d))) for d in verts]
    for d, name in zip(verts, isl_of):
        uv, hit = ray_uv(d, isl[name])
        uvs.append(uv)
    # strips along t (columns)
    strips = []
    for rows, flip in ((rows_crown, False), (rows_R, False), (rows_L, True)):
        cols = [[rows[j][i] for j in range(nt)] for i in range(len(rows[0]))]
        for c in range(len(cols) - 1):
            a, b = (cols[c], cols[c + 1]) if not flip else (cols[c + 1], cols[c])
            s_ = []
            for k in range(nt):
                s_ += [a[k], b[k]]
            strips.append(s_)
    strip = join_strips(strips, pos, lambda k: sub(pos[k], C))
    tris = strip_tris(strip)
    # orient outward
    out_votes = 0
    for a, b, c in tris[:50]:
        n = cross(sub(pos[b], pos[a]), sub(pos[c], pos[a]))
        out_votes += 1 if dot(n, sub(pos[a], C)) > 0 else -1
    if out_votes < 0:
        strip = [strip[0]] + strip           # flip parity -> flips every triangle's winding
        tris = strip_tris(strip)
    nrm = vertex_normals(pos, tris)
    # seam normals: average across duplicated positions
    groups = collections.defaultdict(list)
    for k, p in enumerate(pos):
        groups[tuple(round(c, 3) for c in p)].append(k)
    for ks in groups.values():
        if len(ks) > 1:
            n = norm(sum_vec([nrm[k] for k in ks]))
            for k in ks:
                nrm[k] = n
    return dict(pos=pos, uv=uvs, nrm=nrm, tris=tris, strip=strip, rows=dict(crown=rows_crown, R=rows_R, L=rows_L))


def sum_vec(vs):
    s_ = (0.0, 0.0, 0.0)
    for v in vs:
        s_ = add(s_, v)
    return s_


def resample_dirs(dirs, n):
    pts = polyline_resample(dirs, n)
    return [norm(p) for p in pts]


def boundary_corrected_radius(design, dirs_all):
    """Egg radius, blended near the rim toward the anchor radius so the rim passes through the anchors."""
    egg_r = design["egg"]
    anchors = []
    for key in ("brow", "face_side", "lower", "rear"):
        for p in design[key]:
            anchors.append(p)
            anchors.append(mirror(p))
    dense = []
    pts = polyline_resample(design["brow"] + design["face_side"][1:] + design["lower"][1:] + design["rear"][1:], 200)
    for p in pts + [mirror(q) for q in pts]:
        d = norm(sub(p, C)); r = math.dist(p, C)
        dense.append((d, r - egg_r(d)))
    def radius(d):
        best = min(dense, key=lambda e: -dot(e[0], d))
        ang = math.degrees(math.acos(max(-1.0, min(1.0, dot(best[0], d)))))
        w = 1.0 - smooth(0.0, 28.0, ang)
        feat = design.get("features")
        return egg_r(d) + best[1] * w + (feat(d) * smooth(0.0, 6.0, ang) if feat else 0.0)
    return radius


# ---------------------------------------------------------------------------------------------- v2: patch grids + retail correspondence

def boundary_loop(scene, material):
    """The retail shell's outer boundary loop (welded positions), as an ordered list."""
    sub_ = scene.by_material(material)[0]
    key = lambda v: tuple(round(c, 2) for c in scene.pos[v])
    parent = {}
    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for t in sub_["tris"]:
        for a, b in ((t[0], t[1]), (t[1], t[2])):
            ra, rb = find(a), find(b)
            if ra != rb: parent[ra] = rb
    comp = collections.Counter(find(v) for v in sub_["verts"])
    big = {c for c, k in comp.items() if k > 20}
    edges = collections.Counter()
    for t in sub_["tris"]:
        if find(t[0]) not in big:
            continue
        kk = [key(v) for v in t]
        for a, b in ((kk[0], kk[1]), (kk[1], kk[2]), (kk[2], kk[0])):
            if a != b:
                edges[tuple(sorted((a, b)))] += 1
    boundary = [e for e, c in edges.items() if c == 1]
    adj = collections.defaultdict(list)
    for a, b in boundary:
        adj[a].append(b); adj[b].append(a)
    loops, seen = [], set()
    for start in adj:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [p for p in adj[cur] if p != prev and p not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]; loop.append(cur); seen.add(cur)
        loops.append(loop)
    return max(loops, key=len)


def retail_design(scene, material):
    """Retail shell boundary split into brow / face_side / lower / rear (right half), like a design."""
    loop = boundary_loop(scene, material)
    seam = seam_points(scene, material, "R")
    K = min(loop, key=lambda p: math.dist(p, seam[-1]))
    right = [p for p in loop if p[0] > -0.05]
    # order the right half from the rear centre (x~0, z small) round to the brow centre (x~0, z large)
    rear_c = min((p for p in right if abs(p[0]) < 0.3), key=lambda p: p[2])
    brow_c = max((p for p in right if abs(p[0]) < 0.3), key=lambda p: p[2])
    i0 = loop.index(rear_c)
    seq = loop[i0:] + loop[:i0]
    if seq[1][0] < 0:                           # walk towards +x
        seq = [seq[0]] + list(reversed(seq[1:]))
    seq = seq[:seq.index(brow_c) + 1]
    iK = seq.index(K)
    side = seq[iK:]
    # J: the lowest point of the side section before it climbs to the brow
    iJ = min(range(len(side)), key=lambda i: side[i][1] - 0.15 * side[i][2])
    J = side[iJ]
    rear = list(reversed(seq[:iK + 1]))         # K -> centre
    lower = side[:iJ + 1][::-1]                 # J -> K reversed later
    lower = list(reversed(side[:iJ + 1]))       # J ... K?  (side goes K -> J -> brow)
    lower = side[:iJ + 1]                       # K -> J
    lower = list(reversed(lower))               # J -> K
    up = side[iJ:]                              # J -> brow centre
    up = list(reversed(up))                     # brow centre -> J
    # brow = centre -> temple (the most lateral point of the upper opening), face_side = temple -> J
    it = max(range(len(up)), key=lambda i: up[i][0] if up[i][1] > 35 else -1)
    return dict(brow=up[:it + 1], face_side=up[it:], lower=lower, rear=[K] + [p for p in rear[1:]]), seam


def patch_dirs(design, seam_pts, nt, nc, ns, *, extend_seam=True):
    """Direction grids for the three patches: {'crown': rows[j][i], 'R': rows, 'L': rows}."""
    brow_d = resample_dirs(dirs_of(design["brow"]), 64)
    rear_d = resample_dirs(dirs_of(design["rear"]), 64)
    face = dirs_of(design["face_side"])
    lower = dirs_of(design["lower"])
    seam_dirs = dirs_of(seam_pts)
    ib = min(range(len(brow_d)), key=lambda i: -dot(brow_d[i], seam_dirs[0]))
    seam_curve = [brow_d[ib]] + seam_dirs[1:-1] + [rear_d[0]]
    seam_curve = resample_dirs(seam_curve, nt)
    half = (nc + 1) // 2 + 1
    def full_row(h):
        left = [mirror(p) for p in reversed(h[:-1])]
        return resample_dirs(h + left, nc)
    crown_top = full_row(resample_dirs(list(reversed(brow_d[:ib + 1])), half))
    crown_bot = full_row(resample_dirs(rear_d, half))
    seam_L = [mirror(p) for p in seam_curve]
    face_edge = resample_dirs(brow_d[ib:] + face[1:], ns)
    lower_edge = resample_dirs(lower, nt)
    rear_edge = [rear_d[0]] * ns
    grids = {"crown": [[norm(coons(crown_top, crown_bot, seam_curve, seam_L, i, j, nc, nt)) for i in range(nc)]
                       for j in range(nt)]}
    for side, sgn in (("R", 1), ("L", -1)):
        f = (lambda p: p) if sgn > 0 else mirror
        top = [f(p) for p in face_edge]; bot = [f(p) for p in rear_edge]
        le = seam_curve if sgn > 0 else seam_L; ri = [f(p) for p in lower_edge]
        grids[side] = [[norm(coons(top, bot, le, ri, i, j, ns, nt)) for i in range(ns)] for j in range(nt)]
    return grids


CROWN_V_EASE, CROWN_V_MAX = 0.78, 0.875
CROWN_V_FRONT_MIN, CROWN_V_FRONT_EASE = 0.092, 0.2      # below the crown strip's white brow box (v < 0.085)


# The helmet C art (retail template, all 2026 team masters share it): regions a SpeedFlex must not sample, (u0, u1, v0,
# v1): the crown strip's white brow box (hidden under the retail front bumper plate), the jaw pad pictures at the left
# edge of both side islands, the flag picture. The Revolution's painted ear holes are left where the transfer puts them
# (the ear, below the logo), but nothing is moved onto them. Outside the islands the art holds the team's base colour.
ART_KEEP_OUT = [(0.53, 0.745, 0.0, 0.085), (0.0, 0.14, 0.765, 0.915), (0.0, 0.14, 0.085, 0.235), (0.39, 0.55, 0.41, 0.59)]
ART_EARS = [(0.244, 0.36, 0.826, 0.888), (0.248, 0.364, 0.112, 0.174)]


def allowed_uv_mask(scene_obj=None, material="HI_HELMET_C", n=512, extra=()):
    """True where the SpeedFlex may sample the helmet C art (everything but the keep-out boxes and `extra`)."""
    img = Image.new("L", (n, n), 255)
    d = ImageDraw.Draw(img)
    for u0, u1, v0, v1 in list(ART_KEEP_OUT) + list(extra):
        d.rectangle([u0 * n, v0 * n, u1 * n, v1 * n], fill=0)
    return np.asarray(img) > 0


def sanitize_uvs(uv, tris, allowed, target=None, rounds=8):
    """Every triangle samples only allowed art: vertices outside move to the nearest `target` texel; a triangle that
    still straddles a keep-out region collapses onto the target texel nearest its centroid (flat local colour)."""
    n = allowed.shape[0]
    ok_pts = np.argwhere(allowed if target is None else target).astype(float) + 0.5
    uv = list(uv)
    def ok(u, v):
        return bool(allowed[min(n - 1, max(0, int(v * n))), min(n - 1, max(0, int(u * n)))])
    def nearest(u, v):
        d = (ok_pts[:, 0] - v * n) ** 2 + (ok_pts[:, 1] - u * n) ** 2
        k = int(np.argmin(d))
        return (float(ok_pts[k, 1] / n), float(ok_pts[k, 0] / n))
    grid = [(i / 6, j / 6) for i in range(7) for j in range(7 - i)]
    fixed = 0
    for r in range(rounds):
        bad = []
        for t in tris:
            a, b, c = (uv[k] for k in t)
            for l1, l2 in grid:
                l0 = 1.0 - l1 - l2
                if not ok(a[0] * l0 + b[0] * l1 + c[0] * l2, a[1] * l0 + b[1] * l1 + c[1] * l2):
                    bad.append(t)
                    break
        if not bad:
            break
        for t in bad:
            if r < rounds // 2:
                for k in t:
                    if not ok(*uv[k]):
                        uv[k] = nearest(*uv[k]); fixed += 1
            else:
                cu = sum(uv[k][0] for k in t) / 3; cv = sum(uv[k][1] for k in t) / 3
                q = nearest(cu, cv) if not ok(cu, cv) else (cu, cv)
                for k in t:
                    uv[k] = q; fixed += 1
    return uv, fixed


# (Tried 9/25: real openings where the art paints the Revolution's ear holes. At this mesh density whole cells open up;
# rejected. The painted ear hole stays: it sits at the ear below the logo, where the team art expects it.)
EAR_HOLE_UV = []


def build_shell_v2(design, scene, material, nt, nc, ns, holes=()):
    """New shell from the design; UVs from the retail shell at the same patch coordinates (rim to rim)."""
    isl = retail_islands(scene, material)
    rdesign, rseam = retail_design(scene, material)
    new_g = patch_dirs(design, rseam, nt, nc, ns)
    old_g = patch_dirs(rdesign, rseam, nt, nc, ns)
    radius = design["radius"]
    pos, uv, rows = [], [], {}
    for name in ("crown", "R", "L"):
        rows[name] = []
        for j in range(nt):
            row = []
            for i in range(len(new_g[name][j])):
                d = new_g[name][j][i]
                row.append(len(pos))
                pos.append(add(C, mul(d, radius(d))))
                uv.append(ray_uv(old_g[name][j][i], isl[name])[0])
            rows[name].append(row)
    # the helmet art keeps a white back-plate picture right under the crown island (v > ~0.89 at u 0.51-0.75); the
    # new shell reaches lower at the back than retail, so the crown's rear rows are eased up to stay on the shell colour
    crown = sorted({k for row in rows["crown"] for k in row})
    top = max(uv[k][1] for k in crown)
    if top > CROWN_V_MAX:
        for k in crown:
            u_, v_ = uv[k]
            if v_ > CROWN_V_EASE:
                uv[k] = (u_, CROWN_V_EASE + (v_ - CROWN_V_EASE) * (CROWN_V_MAX - CROWN_V_EASE) / (top - CROWN_V_EASE))
    bottom = min(uv[k][1] for k in crown)
    if bottom < CROWN_V_FRONT_MIN:
        for k in crown:
            u_, v_ = uv[k]
            if v_ < CROWN_V_FRONT_EASE:
                uv[k] = (u_, CROWN_V_FRONT_MIN + (v_ - bottom) * (CROWN_V_FRONT_EASE - CROWN_V_FRONT_MIN)
                         / (CROWN_V_FRONT_EASE - bottom))
    strips = []
    for name, flip in (("crown", False), ("R", False), ("L", True)):
        r = rows[name]
        cols = [[r[j][i] for j in range(nt)] for i in range(len(r[0]))]
        for c in range(len(cols) - 1):
            a, b = (cols[c], cols[c + 1]) if not flip else (cols[c + 1], cols[c])
            s_ = []
            for k in range(nt):
                s_ += [a[k], b[k]]
                if k + 1 < nt and holes:
                    cu = (uv[a[k]][0] + uv[b[k]][0] + uv[a[k + 1]][0] + uv[b[k + 1]][0]) / 4
                    cv = (uv[a[k]][1] + uv[b[k]][1] + uv[a[k + 1]][1] + uv[b[k + 1]][1]) / 4
                    if any(u0 <= cu <= u1 and v0 <= cv <= v1 for u0, u1, v0, v1 in holes):
                        strips.append(s_)          # the cell between rows k and k + 1 is left open
                        s_ = []
            strips.append(s_)
    strip = join_strips(strips, pos, lambda k: sub(pos[k], C))
    tris = strip_tris(strip)
    votes = sum(1 if dot(cross(sub(pos[b], pos[a]), sub(pos[c], pos[a])), sub(pos[a], C)) > 0 else -1
                for a, b, c in tris if len({a, b, c}) == 3)
    if votes < 0:
        strip = [strip[0]] + strip
        tris = strip_tris(strip)
    nrm = vertex_normals(pos, tris)
    groups = collections.defaultdict(list)
    for k, p in enumerate(pos):
        groups[tuple(round(c, 3) for c in p)].append(k)
    for ks in groups.values():
        if len(ks) > 1:
            n = norm(sum_vec([nrm[k] for k in ks]))
            for k in ks:
                nrm[k] = n
    return dict(pos=pos, uv=uv, nrm=nrm, tris=tris, strip=strip, rows=rows, grids=new_g, retail_grids=old_g)


# ---------------------------------------------------------------------------------------------- guardian cap clamp

def cap_triangles(decoded_with_cap, key="o3c115"):
    """Triangles of the Guardian-sculpted shell B (hi frame), for the inside-the-cap clamp."""
    lay = mh.parse_layout(key, decoded_with_cap)
    pos = mh._positions(lay, decoded_with_cap)
    retail = Scene(key)
    sub_ = retail.by_material("HI_HELMET_B")[0]
    return [tuple(pos[v] for v in t) for t in sub_["tris"]]


def ray_hit(d, tris, origin=None):
    o = C if origin is None else origin
    best = None
    for p0, p1, p2 in tris:
        e1, e2 = sub(p1, p0), sub(p2, p0)
        h = cross(d, e2); a = dot(e1, h)
        if abs(a) < 1e-12:
            continue
        f = 1.0 / a; s_ = sub(o, p0); u = f * dot(s_, h)
        if u < 0 or u > 1:
            continue
        q = cross(s_, e1); v = f * dot(d, q)
        if v < 0 or u + v > 1:
            continue
        t = f * dot(e2, q)
        if t > 0 and (best is None or t < best):
            best = t
    return best


def clamped_radius(radius, cap_tris, margin=0.45):
    def r(d):
        base = radius(d)
        hit = ray_hit(d, cap_tris)
        if hit is not None and base > hit - margin:
            return hit - margin
        return base
    return r


def clamped_radius_smooth(radius, cap_tris, margin=0.45, spread_deg=35.0, samples=None):
    """Inside-the-cap clamp without a ledge: the clamp delta measured where the cap covers a direction is carried
    smoothly onto the directions below the cap's rim (nearest covered direction, fading over spread_deg)."""
    cache = {}
    covered = []          # (direction, delta<=0) where the cap is hit
    def delta_hit(d):
        base = radius(d)
        hit = ray_hit(d, cap_tris)
        if hit is None:
            return None
        return min(0.0, (hit - margin) - base)
    if samples:
        for d in samples:
            dh = delta_hit(d)
            if dh is not None:
                covered.append((d, dh))
    def r(d):
        base = radius(d)
        dh = delta_hit(d)
        if dh is not None:
            return base + dh
        if not covered:
            return base
        best = max(covered, key=lambda e: dot(e[0], d))
        ang = math.degrees(math.acos(max(-1.0, min(1.0, dot(best[0], d)))))
        fade = 1.0 - smooth(0.0, spread_deg, ang)
        return base + best[1] * fade
    return r


def cap_interior_triangles(cap_tris):
    """Cap triangles away from the cap's open rim (triangles touching a boundary edge's vertices removed): a ray
    that leaves through the rim region is not a covering."""
    import collections as _c
    key = lambda p: tuple(round(v, 3) for v in p)
    edges = _c.Counter()
    for t in cap_tris:
        k = [key(p) for p in t]
        for a, b in ((k[0], k[1]), (k[1], k[2]), (k[2], k[0])):
            edges[tuple(sorted((a, b)))] += 1
    rim = {p for e, c in edges.items() if c == 1 for p in e}
    return [t for t in cap_tris if not any(key(p) in rim for p in t)]


# ====================================================================================================
# designs
# ====================================================================================================


def egg(a, b_up, b_dn, c_f, c_b, p_up=2.0, p_dn=2.6):
    def f(d):
        b = b_up if d[1] >= 0 else b_dn
        c = c_f if d[2] >= 0 else c_b
        p = p_up if d[1] >= 0 else p_up + (p_dn - p_up) * min(1.0, -d[1] / 0.7)
        s = abs(d[0] / a) ** p + abs(d[1] / b) ** p + abs(d[2] / c) ** p
        return s ** (-1.0 / p)
    return f


def angles(d):
    """(lateral phi, longitudinal theta) in degrees: theta 0 = up, +90 = front, -90 = back, +-180 = down."""
    phi = math.degrees(math.asin(max(-1.0, min(1.0, d[0]))))
    theta = math.degrees(math.atan2(d[2], d[1]))
    return phi, theta


def window(x, a, b, soft):
    return smooth(a - soft, a + soft, x) * (1.0 - smooth(b - soft, b + soft, x))


def speedflex_features(d):
    phi, theta = angles(d)
    out = 0.0
    # (pass 2: no rear lip flare; the real shell curves in toward the neck)
    # (pass 2: the front flex panel is the dark flex_notch ribbon; a groove this narrow falls between the grid rows
    # and only let the chords past the Guardian cap's front edge)
    return out


def f7_features(d):
    phi, theta = angles(d)
    out = 0.0
    # two raised crown rails from the front vents to the back
    out += 0.5 * math.exp(-((abs(phi) - 18.0) / 4.5) ** 2) * window(theta, -95.0, 62.0, 10.0)
    # rear bumper ledge: a horizontal shelf low on the back, the lip tucked under it
    out += 0.7 * window(theta, -150.0, -118.0, 6.0) * max(0.0, 1.0 - abs(phi) / 55.0)
    out -= 0.4 * window(theta, -178.0, -152.0, 6.0) * max(0.0, 1.0 - abs(phi) / 55.0)
    # front brow overhang above the facemask (the F7 bumper plate)
    out += 0.45 * window(theta, 55.0, 80.0, 6.0) * max(0.0, 1.0 - abs(phi) / 30.0)
    return out


SPEEDFLEX = dict(
    name="SpeedFlex",
    brow=[(0.0, 45.4, 25.4), (4.0, 45.2, 24.8), (7.4, 44.3, 22.8), (9.9, 42.3, 20.4)],
    face_side=[(9.9, 42.3, 20.4), (10.7, 38.2, 19.8), (10.6, 33.8, 20.2), (9.8, 29.8, 20.8), (8.8, 27.0, 21.2)],
    # pass 2 (main, 2026-09-24): the rim curves in toward the neck behind the jaw (no rear flare, no flat lip); the
    # crown sits 1.3 cm lower (the photo's side proportions: length / height ~1.14) and the back runs to the
    # Guardian cap's limit
    lower=[(8.8, 27.0, 21.2), (9.9, 27.1, 16.0), (10.4, 28.6, 10.0), (10.1, 30.1, 4.0), (9.2, 30.6, 0.0),
           (8.0, 30.9, -1.6)],
    rear=[(8.0, 30.9, -1.6), (6.0, 31.0, -2.4), (3.1, 31.0, -2.9), (0.0, 31.0, -3.0)],
    egg=egg(12.7, 15.3, 15.5, 16.7, 14.2, p_dn=2.1),
    features=speedflex_features,
)

F7PRO = dict(
    name="F7 Pro",
    brow=[(0.0, 46.0, 25.0), (4.0, 45.8, 24.5), (7.2, 44.8, 22.5), (9.7, 42.6, 20.0)],
    face_side=[(9.7, 42.6, 20.0), (10.3, 38.4, 19.4), (10.0, 33.8, 19.8), (9.2, 29.8, 20.6), (8.2, 27.2, 21.0)],
    lower=[(8.2, 27.2, 21.0), (10.2, 27.0, 15.6), (11.8, 28.6, 9.6), (12.4, 30.4, 4.0), (12.0, 30.6, -1.0),
           (10.6, 30.4, -4.4)],
    rear=[(10.6, 30.4, -4.4), (8.0, 30.0, -6.4), (4.0, 29.8, -7.4), (0.0, 29.8, -7.6)],
    egg=egg(12.6, 17.4, 15.2, 16.4, 15.6, p_up=2.15),
    features=f7_features,
)


# ====================================================================================================
# SpeedFlex pass 3 (2026-09-25): a loft fitted to the orthographic views of US design patent D752,821 (Riddell, Inc.,
# "Football helmet", filed 2014-02-12: FIG. 2 left side, FIG. 4 front, FIG. 5 top), with the production helmet's
# rounder back from the riddell.com side photo ("NFL Shield Authentic SpeedFlex"). Normalised side coordinates: u from
# the brow's front (0) to the patent's back (1), v from the crown (0) to the jaw bottom (1). The knots were measured
# from the patent figures and the photo by hm (scratch fit/profiles.json, tools/profiles.py).
# ====================================================================================================

SF_H, SF_TOP, SF_BACK = 26.4, 57.0, -4.9    # crown to jaw bottom, crown height, back-most z (inside the Guardian cap)
SF_LP = 1.0822 * SF_H                       # FIG. 2: length / height
SF_BACK_U = 1.0407                          # the photo's back-most point (v = 0.525) lies past the patent's back
SF_BROW_Z = SF_BACK + SF_BACK_U * SF_LP
# FIG. 2 forehead (front branch above the brow, v <= 0.49)
U_FRONT = [(0.0, 0.3964), (0.025, 0.3074), (0.05, 0.2554), (0.075, 0.2127), (0.1, 0.1844), (0.125, 0.1564),
           (0.15, 0.1313), (0.175, 0.1118), (0.2, 0.0911), (0.225, 0.0752), (0.25, 0.0607), (0.275, 0.0542),
           (0.3, 0.0479), (0.325, 0.0344), (0.35, 0.0267), (0.375, 0.0216), (0.4, 0.0145), (0.425, 0.011),
           (0.45, 0.0051), (0.475, 0.0019), (0.49, 0.0)]
# FIG. 2 back over the crown (v <= 0.325), then the photo's rounder back; below v = 0.9 the rear bumper curves under
U_BACK = [(0.0, 0.6083), (0.025, 0.6977), (0.05, 0.7498), (0.075, 0.793), (0.1, 0.8286), (0.125, 0.8567),
          (0.15, 0.8827), (0.175, 0.9075), (0.2, 0.9262), (0.225, 0.9431), (0.25, 0.9593), (0.275, 0.9734),
          (0.3, 0.9868), (0.325, 0.9986), (0.35, 1.009), (0.375, 1.0172), (0.4, 1.0244), (0.425, 1.0305),
          (0.45, 1.0346), (0.475, 1.0387), (0.5, 1.0397), (0.525, 1.0407), (0.55, 1.0387), (0.575, 1.0244),
          (0.6, 1.0101), (0.625, 1.0039), (0.65, 0.9978), (0.675, 0.9917), (0.7, 0.9845), (0.725, 0.9763),
          (0.75, 0.9672), (0.775, 0.9559), (0.8, 0.9437), (0.825, 0.9294), (0.85, 0.9161), (0.875, 0.9038),
          (0.9, 0.8997), (0.95, 0.875), (1.0, 0.845), (1.06, 0.80)]
# FIG. 4 half-width / H (both sides averaged)
W_OVER_H = [(0.0, 0.0002), (0.05, 0.1888), (0.1, 0.2558), (0.15, 0.3152), (0.2, 0.3568), (0.25, 0.3897),
            (0.3, 0.4139), (0.35, 0.4306), (0.4, 0.4427), (0.45, 0.4493), (0.5, 0.4507), (0.55, 0.4481),
            (0.6, 0.4411), (0.65, 0.4318), (0.7, 0.4202), (0.75, 0.4113), (0.8, 0.3999), (0.85, 0.3908),
            (0.9, 0.3818), (0.95, 0.3682), (1.0, 0.3408), (1.06, 0.3408)]
# FIG. 5 plan half-width / maximum, from the front (s = 0) to the back (s = 1)
T_PLAN = [(0.0, 0.0405), (0.05, 0.4954), (0.1, 0.6498), (0.15, 0.754), (0.2, 0.8244), (0.25, 0.8816), (0.3, 0.9211),
          (0.35, 0.956), (0.4, 0.9884), (0.45, 0.996), (0.5, 0.9985), (0.55, 0.9909), (0.6, 0.9696), (0.65, 0.9453),
          (0.7, 0.9094), (0.75, 0.8654), (0.8, 0.8047), (0.85, 0.7176), (0.9, 0.6068), (0.95, 0.4423), (1.0, 0.0633)]
SF_BROW_V = 0.49                            # FIG. 2 / FIG. 4: the face opening's top edge at the centre
# the rim in side coordinates (FIG. 2: temple corner, notch, jaw flap; the lower back follows the photo's rear bumper,
# raised at the back so the game's neck stays clear)
SF_TEMPLE = (0.2, 0.535)
SF_FACE_SIDE = [(0.2, 0.535), (0.25, 0.58), (0.28, 0.63), (0.282, 0.66), (0.265, 0.72), (0.225, 0.79), (0.19, 0.85),
                (0.175, 0.9), (0.2, 0.955)]
SF_LOWER = [(0.2, 0.955), (0.25, 0.99), (0.32, 1.0), (0.42, 0.99), (0.52, 0.975), (0.62, 0.955), (0.72, 0.935),
            (0.8, 0.91), (0.86, 0.89)]
SF_REAR_V = 0.88
SF_UPPER_CLIP, SF_LOWER_CLIP = (0.29, 0.54), (0.26, 0.92)     # FIG. 2 clip holes: the facemask's attachment points


def sf_y(v):
    return SF_TOP - v * SF_H


def sf_z(u):
    return SF_BROW_Z - u * SF_LP


def sf_v(y):
    return (SF_TOP - y) / SF_H


class Loft:
    """The SpeedFlex outer surface: at height y the section spans z_b..z_f (FIG. 2 / photo), its half-width is
    w(y) * T(s) (FIG. 4 width, FIG. 5 plan shape, s = 0 at the section's front). Below the brow the section's front is
    the brow's plane (virtual: the face opening and the rim cut the shell out of it)."""
    V_END = 1.06

    def section(self, y):
        v = sf_v(y)
        uf = smooth_interp(U_FRONT, v) if v < SF_BROW_V else 0.0
        ub = smooth_interp(U_BACK, v)
        return sf_z(max(uf, 0.0)), sf_z(ub), max(smooth_interp(W_OVER_H, v), 0.0) * SF_H

    def half_width(self, y, z):
        v = sf_v(y)
        if v < 0.0 or v > self.V_END:
            return -1.0
        zf, zb, w = self.section(y)
        if z > zf or z < zb or zf - zb < 1e-6:
            return -1.0
        s = (zf - z) / (zf - zb)
        return w * max(smooth_interp(T_PLAN, s), 0.0)

    def inside(self, p):
        hw = self.half_width(p[1], p[2])
        return hw >= 0.0 and abs(p[0]) <= hw

    def radius(self, d, origin=None):
        o = C if origin is None else origin
        lo, hi = 0.0, 40.0
        for _ in range(34):
            mid = 0.5 * (lo + hi)
            if self.inside(add(o, mul(d, mid))):
                lo = mid
            else:
                hi = mid
        return lo

    def front_z(self, x, y):
        """The surface point's z at (x, y) on the front half (largest z)."""
        zf, zb, w = self.section(y)
        lo, hi = 0.5 * (zf + zb), zf
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if self.half_width(y, mid) >= abs(x):
                lo = mid
            else:
                hi = mid
        return lo

    def point(self, u, v, side=1.0):
        y, z = sf_y(v), sf_z(u)
        return (side * max(self.half_width(y, z), 0.0), y, z)


SF_LOFT = Loft()


def accessory_positions(scene_obj, layout, key, frame_offset=(0.0, 0.0, 0.0), margin=0.55):
    """HELMET_C_accessories (the retail chin strap, pads and snaps): every vertex that the SpeedFlex would not cover
    by at least `margin` is pulled in along its ray from the helmet centre to `margin` inside the loft; the rest keep
    their retail positions. Returns the position lanes (NORMSHORT3 x count) as bytes."""
    first, count = mh.ACCESSORIES[key]
    lanes = layout.lanes
    pos = mh._positions(layout, scene_obj.decoded)
    out = bytearray()
    moved = 0
    for v in range(first, first + count):
        q = sub(pos[v], frame_offset)
        d = norm(sub(q, C))
        r, rs = math.dist(q, C), SF_LOFT.radius(d)
        if r > rs - margin:
            q = add(C, mul(d, rs - margin))
            moved += 1
        p = add(q, frame_offset)
        out += struct.pack("<3h", *(models.encode_normshort(max(-1.0, min(1.0, (p[a] - lanes.offset[a]) / lanes.scale)))
                                    for a in range(3)))
    return bytes(out), moved


def speedflex_design():
    """Rim anchors on the loft (right side) for patch_dirs / build_shell_v2."""
    L = SF_LOFT
    T_ = L.point(*SF_TEMPLE)
    brow = []
    for k in range(9):
        xi = k / 8
        y = sf_y(SF_BROW_V + (SF_TEMPLE[1] - SF_BROW_V) * xi ** 2.5)
        x = xi * T_[0]
        brow.append((x, y, L.front_z(x, y)))
    brow[-1] = T_
    face_side = [L.point(u, v) for u, v in SF_FACE_SIDE]
    lower = [L.point(u, v) for u, v in SF_LOWER]
    K = lower[-1]
    yK, yR = K[1], sf_y(SF_REAR_V)
    zf, zb, _w = L.section(yK)
    sK = (zf - K[2]) / (zf - zb)
    rear = []
    for k in range(7):
        t = k / 6
        y = yK + (yR - yK) * t
        zf, zb, _w = L.section(y)
        s_ = sK + (1.0 - sK) * t
        z = zf - s_ * (zf - zb)
        rear.append((0.0 if k == 6 else max(L.half_width(y, z), 0.0), y, z))
    rear[0] = K
    return dict(name="SpeedFlex", brow=brow, face_side=face_side, lower=lower, rear=rear, radius=L.radius)


# ====================================================================================================
# maskgen
# ====================================================================================================


def smooth_interp(knots, v):
    """Piecewise-cubic (Catmull-Rom) interpolation of [(v, value)] knots at v."""
    ks = sorted(knots)
    if v <= ks[0][0]:
        return ks[0][1]
    if v >= ks[-1][0]:
        return ks[-1][1]
    for i in range(len(ks) - 1):
        v0, a = ks[i]; v1, b = ks[i + 1]
        if v0 <= v <= v1:
            t = (v - v0) / (v1 - v0)
            pa = ks[i - 1][1] if i > 0 else a - (b - a)
            pb = ks[i + 2][1] if i + 2 < len(ks) else b + (b - a)
            t2, t3 = t * t, t * t * t
            return 0.5 * (2 * a + (-pa + b) * t + (2 * pa - 5 * a + 4 * b - pb) * t2 + (-pa + 3 * a - 3 * b + pb) * t3)


class Envelope:
    """E(u, v): u in [-1, 1] across (x = u * w(v)), v in [0, 1] top (brow) to bottom (chin)."""

    def __init__(self, y_knots, zc_knots, w_knots, zedge_knots):
        self.y, self.zc, self.w, self.ze = y_knots, zc_knots, w_knots, zedge_knots

    def __call__(self, u, v):
        y = smooth_interp(self.y, v)
        w = smooth_interp(self.w, v)
        zc = smooth_interp(self.zc, v)
        ze = smooth_interp(self.ze, v)
        x = u * w
        # horizontal section: a curve from the centre (zc) back to the edge (ze), flatter in the middle
        a = abs(u)
        z = zc - (zc - ze) * (0.55 * a * a + 0.45 * a ** 4)
        return (x, y, z)


def sample_path(env, uv_pts, step=1.6):
    """3D points along a path given as (u, v) control points on the envelope (or raw 3D points)."""
    pts3 = [resolve_point(env, p) for p in uv_pts]
    dense = catmull(pts3, 10) if len(pts3) > 2 else [lerp(pts3[0], pts3[1], k / 20) for k in range(21)]
    length = sum(math_dist(dense[i], dense[i + 1]) for i in range(len(dense) - 1))
    n = max(2, int(math.ceil(length / step)) + 1)
    return polyline_resample(pts3, n) if len(pts3) > 2 else [lerp(pts3[0], pts3[1], k / (n - 1)) for k in range(n)]


def math_dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def tube(path, radius, sides=4, out_hint=(0.0, 0.0, 1.0)):
    """Rings around the path: vertices, normals, strip (local indices) of a closed tube, open ends."""
    n = len(path)
    verts, nrms = [], []
    prev_side = None
    for k in range(n):
        t = norm(sub(path[min(k + 1, n - 1)], path[max(k - 1, 0)]))
        ref = out_hint if abs(dot(out_hint, t)) < 0.9 else (0.0, 1.0, 0.0)
        side = norm(cross(t, ref)) if prev_side is None else norm(sub(prev_side, mul(t, dot(prev_side, t))))
        up = norm(cross(side, t))
        prev_side = side
        for s in range(sides):
            ang = 2 * math.pi * (s + 0.5) / sides
            dvec = add(mul(side, math.cos(ang)), mul(up, math.sin(ang)))
            verts.append(add(path[k], mul(dvec, radius)))
            nrms.append(dvec)
    strips = []
    for s in range(sides):
        s2 = (s + 1) % sides
        strip = []
        for k in range(n):
            strip += [k * sides + s, k * sides + s2]
        strips.append(strip)
    return verts, nrms, strips


def build_mask(env, elements, radius):
    """elements: list of (kind, params); returns dict(pos, nrm, strip, tris)."""
    pos, nrm, strips = [], [], []
    for kind, p in elements:
        r = radius * p.get("scale", 1.0) if isinstance(p, dict) else radius
        if kind == "path":
            path = sample_path(env, p["pts"], p.get("step", 1.6))
        else:
            raise ValueError(kind)
        v, n, s = tube(path, r)
        base = len(pos)
        pos += v
        nrm += n
        strips += [[base + i for i in st] for st in s]
    strip = join_strips(strips, pos, lambda k: nrm[k])
    return dict(pos=pos, nrm=nrm, strip=strip, tris=strip_tris(strip))


# ---------------------------------------------------------------------------------------------- element helpers

def P(*pts, **kw):
    d = {"pts": list(pts)}
    d.update(kw)
    return ("path", d)


def hbar(v, u0=-1.0, u1=1.0, **kw):
    n = max(2, int(round((u1 - u0) / 0.25)) + 1)
    return P(*[(u0 + (u1 - u0) * k / (n - 1), v) for k in range(n)], **kw)


def vbar(u, v0, v1, **kw):
    n = max(2, int(round((v1 - v0) / 0.2)) + 1)
    return P(*[(u, v0 + (v1 - v0) * k / (n - 1)) for k in range(n)], **kw)


def seg(u0, v0, u1, v1, **kw):
    return P((u0, v0), (u1, v1), **kw)


# ---------------------------------------------------------------------------------------------- v2: budgeted bars

MASK_STEP, MASK_TURN = 3.0, 10.0       # bar sampling (cm, degrees): the seated masks wrap back to the shell


def resolve_point(env, p):
    """(u, v) on the envelope, a raw 3D point, or ("clip", name, side): one of the shell's facemask attachment points."""
    if isinstance(p[0], str):
        return env.clip(p[1], p[2])
    return p if len(p) == 3 else env(*p)


def adaptive_path(env, uv_pts, max_step=2.5, max_turn_deg=8.0):
    """Points along a path: dense Catmull-Rom, then keep a point when the direction has turned max_turn_deg or the
    distance since the last kept point exceeds max_step."""
    pts3 = [resolve_point(env, p) for p in uv_pts]
    dense = catmull(pts3, 16) if len(pts3) > 2 else [lerp(pts3[0], pts3[1], k / 32) for k in range(33)]
    out = [dense[0]]
    last_dir = None
    acc = 0.0
    for i in range(1, len(dense) - 1):
        seg_len = math_dist(dense[i], out[-1])
        d_prev = norm(sub(dense[i], out[-1]))
        d_next = norm(sub(dense[i + 1], dense[i]))
        turn = math.degrees(math.acos(max(-1.0, min(1.0, dot(d_prev, d_next))))) if seg_len > 1e-6 else 0.0
        if seg_len >= max_step or (turn >= max_turn_deg and seg_len > 0.6):
            out.append(dense[i])
    out.append(dense[-1])
    return out


def ribbon(path, width, out_dir_fn):
    """A flat bar facing outward: two vertices per point, stored in strip order (sequential indices)."""
    verts, nrms = [], []
    n = len(path)
    for k in range(n):
        t = norm(sub(path[min(k + 1, n - 1)], path[max(k - 1, 0)]))
        o = out_dir_fn(path[k])
        side = norm(cross(t, o))
        o2 = norm(cross(side, t))
        a = add(path[k], mul(side, width / 2)); b = sub(path[k], mul(side, width / 2))
        verts += [a, b]
        nrms += [norm(add(o2, mul(side, 0.8))), norm(sub(o2, mul(side, 0.8)))]
    return verts, nrms, [list(range(2 * n))]


def tube3(path, radius, out_dir_fn):
    """A triangular tube, one edge facing outward; smooth normals. Face strips (three per tube)."""
    n = len(path)
    verts, nrms = [], []
    for k in range(n):
        t = norm(sub(path[min(k + 1, n - 1)], path[max(k - 1, 0)]))
        o = out_dir_fn(path[k])
        o = norm(sub(o, mul(t, dot(o, t))))
        side = norm(cross(t, o))
        for s in range(3):
            ang = 2 * math.pi * s / 3
            dvec = add(mul(o, math.cos(ang)), mul(side, math.sin(ang)))
            verts.append(add(path[k], mul(dvec, radius)))
            nrms.append(dvec)
    strips = []
    for s in range(3):
        s2 = (s + 1) % 3
        strip = []
        for k in range(n):
            strip += [k * 3 + s, k * 3 + s2]
        strips.append(strip)
    return verts, nrms, strips


def build_mask_v2(env, elements, radius, centre=(0.0, 36.0, 10.0)):
    """elements: ('tube'|'ribbon', params) with params['pts'] as (u, v) or 3D points."""
    def out_dir(p):
        return norm(sub(p, centre))
    pos, nrm, strips = [], [], []
    for kind, p in elements:
        path = adaptive_path(env, p["pts"], p.get("max_step", MASK_STEP), p.get("turn", MASK_TURN))
        r = radius * p.get("scale", 1.0)
        if kind == "ribbon":
            v, n, s = ribbon(path, 2.0 * r * 1.15, out_dir)
        else:
            v, n, s = tube3(path, r, out_dir)
        base = len(pos)
        pos += v; nrm += n
        strips += [[base + i for i in st] for st in s]
    strip = join_strips(strips, pos, lambda k: nrm[k])
    return dict(pos=pos, nrm=nrm, strip=strip, tris=strip_tris(strip))


# ====================================================================================================
# masks15
# ====================================================================================================

class RoundEnvelope(Envelope):
    def __call__(self, u, v):
        y = smooth_interp(self.y, v); w = smooth_interp(self.w, v)
        zc = smooth_interp(self.zc, v); ze = smooth_interp(self.ze, v)
        a = abs(u)
        return (u * w, y, zc - (zc - ze) * (0.8 * a * a + 0.2 * a ** 4))

class SeatedEnvelope:
    """The facemask surface seated on a shell: E(u, v) blends the mask's centre profile (x = 0: y, z by v) into its
    edge, which follows the shell's face-opening rim offset outward (so the frame's side bars sit on the shell), with
    x = u * edge_x. v = 0 is the top bar (on the brow edge), v = 1 the chin bar. clips: the shell's attachment points."""

    def __init__(self, centre, edge, clips, name=""):
        self.centre = centre      # [(v, y, z)]
        self.edge = edge          # [(v, x, y, z)] right side
        self.clips = clips        # {"top": (x, y, z), "low": (x, y, z)} right side
        self.name = name

    def _c(self, v):
        return (smooth_interp([(k[0], k[1]) for k in self.centre], v), smooth_interp([(k[0], k[2]) for k in self.centre], v))

    def _e(self, v):
        return tuple(smooth_interp([(k[0], k[i]) for k in self.edge], v) for i in (1, 2, 3))

    def __call__(self, u, v):
        cy, cz = self._c(v)
        ex, ey, ez = self._e(v)
        a = abs(u)
        return (u * ex, cy + (ey - cy) * a ** 4, cz - (cz - ez) * (0.8 * a * a + 0.2 * a ** 4))

    def clip(self, name, side):
        x, y, z = self.clips[name]
        return (side * x, y, z)


def rim_polyline_at(poly, y):
    """The point of a (top to bottom) rim polyline at height y (linear between its points)."""
    for a, b in zip(poly, poly[1:]):
        if (a[1] - y) * (b[1] - y) <= 0 and abs(a[1] - b[1]) > 1e-9:
            t = (y - a[1]) / (b[1] - a[1])
            return lerp(a, b, t)
    return poly[0] if abs(poly[0][1] - y) < abs(poly[-1][1] - y) else poly[-1]


# the mask's front profile from the riddell.com side photo (the facemask's front stands ~0.18 of the patent length
# ahead of the brow from the nose to the mouth): (v on the mask, z ahead of the brow's front / SF_LP)
SF_MASK_FRONT = [(-0.1, None), (0.0, None), (0.1, 0.075), (0.2, 0.14), (0.32, 0.17), (0.5, 0.176), (0.7, 0.175),
                 (0.85, 0.165), (0.95, 0.14), (1.0, 0.12)]
SF_MASK_V = (0.475, 1.08)          # the top bar and the chin bar in FIG. 2 v (the photo's chin bar hangs below the jaw)
BAR_R = 0.45
SF_MASK_SIDE_X = 10.5              # the frame's sides stand straight down to about the mouth


def seated_envelope_speedflex(design, offset=0.55):
    L = SF_LOFT
    v0, v1 = SF_MASK_V
    centre = []
    for v, ahead in SF_MASK_FRONT:
        y = sf_y(v0 + (v1 - v0) * v)
        z = L.front_z(0.0, y) + BAR_R + 0.1 if ahead is None else SF_BROW_Z + ahead * SF_LP
        centre.append((v, y, z))
    rim = [design["brow"][-1]] + list(design["face_side"][1:])          # temple -> jaw flap front-bottom
    yT, yJ = rim[0][1], rim[-1][1]
    y_top_end = sf_y(SF_BROW_V) - 0.45       # the top bar runs nearly straight: its ends sit on the shell above the temple
    edge = []
    for v in [-0.1] + [k / 12 for k in range(13)]:
        if v <= 0.0:
            y = y_top_end + (0.9 if v < 0 else 0.0)
            z = rim[0][2] + 0.4
            p = (max(L.half_width(y, z), 0.0), y, z)
        else:
            y = yT + (yJ - yT) * v
            p = rim_polyline_at(rim, y)
        n = norm(sub(p, (0.0, p[1], 9.0)))                  # outward in the section
        x = p[0] + n[0] * offset
        if v <= 0.6:                                        # straight sides in the front view (product photos)
            x = max(x, SF_MASK_SIDE_X)
        edge.append((v, x, p[1], p[2] + n[2] * offset))
    top = L.point(*SF_UPPER_CLIP); low = L.point(*SF_LOWER_CLIP)
    clips = {"top": (top[0] + 0.3, top[1], top[2]), "low": (low[0] + 0.3, low[1], low[2])}
    return SeatedEnvelope(centre, edge, clips, "SpeedFlex")


SF_ENV = RoundEnvelope(
    y_knots=[(0.0, 43.5), (1.0, 25.2)],
    zc_knots=[(0.0, 26.3), (0.3, 27.0), (0.55, 27.5), (0.8, 27.2), (1.0, 25.6)],
    w_knots=[(0.0, 11.8), (0.12, 11.25), (0.4, 11.0), (0.65, 10.3), (0.85, 8.6), (1.0, 5.9)],
    zedge_knots=[(0.0, 21.2), (0.4, 21.4), (0.65, 21.7), (0.85, 22.8), (1.0, 24.3)],
)
TOP_CLIP = (10.9, 43.0, 20.2)
R_SW, R_STD, R_HD = 0.34, 0.40, 0.45


def T(*pts, **kw):
    d = {"pts": list(pts)}; d.update(kw); return ("tube", d)


def Rb(*pts, **kw):
    d = {"pts": list(pts)}; d.update(kw); return ("ribbon", d)


def hbar(v, u0=-1.0, u1=1.0, kind="tube", dip=0.0):
    n = 9
    pts = [(u0 + (u1 - u0) * k / (n - 1), v + dip * (1.0 - abs(u0 + (u1 - u0) * k / (n - 1))) ** 2) for k in range(n)]
    return (kind, {"pts": pts})


def vbar(u, v0, v1):
    return Rb((u, v0), (u, (v0 + v1) / 2), (u, v1))


def frame(axiom=False):
    els = [T((-1.0, 0.0), (-0.5, -0.004), (0.0, -0.006), (0.5, -0.004), (1.0, 0.0)),
           T((1.0, 0.0), ("clip", "top", 1.0)), T((-1.0, 0.0), ("clip", "top", -1.0)),
           T((0.98, 0.84), ("clip", "low", 1.0)), T((-0.98, 0.84), ("clip", "low", -1.0)),
           T((1.0, 0.0), (1.0, 0.35), (1.0, 0.68), (0.97, 0.88), (0.9, 1.0)),
           T((-1.0, 0.0), (-1.0, 0.35), (-1.0, 0.68), (-0.97, 0.88), (-0.9, 1.0)),
           T((-0.9, 1.0), (-0.45, 1.0), (0.0, 1.0), (0.45, 1.0), (0.9, 1.0))]
    if not axiom:   # the SpeedFlex masks' raised top bar with four short connectors
        els.append(T((-0.8, -0.07), (-0.4, -0.078), (0.0, -0.08), (0.4, -0.078), (0.8, -0.07), max_step=4.0))
        for u in (-0.74, -0.26, 0.26, 0.74):
            els.append(Rb((u, -0.075), (u, 0.0)))
    return els


def below(v, us, v1=1.0):
    return [vbar(u, v, v1) for u in us]


def sf(name, positions, radius, els):
    return dict(family="SpeedFlex", name=name, positions=positions, radius=radius, elements=els)


F = frame()
FA = frame(axiom=True)
W_BAR = [T((-1.0, 0.52), (-0.55, 0.60), (-0.2, 0.66), (0.0, 0.62), (0.2, 0.66), (0.55, 0.60), (1.0, 0.52))]
MASKS15 = [
    sf("SF-2BD-SW", "QB, WR", R_SW, F + [hbar(0.60)] + below(0.60, (-0.42, 0.0, 0.42))),
    sf("SF-2BD", "QB, WR", R_STD, F + [hbar(0.60)] + below(0.60, (-0.42, 0.0, 0.42))),
    sf("SF-2BD-HD", "QB, WR", R_HD, F + [hbar(0.55), hbar(0.63)] + below(0.63, (-0.6, -0.3, 0.0, 0.3, 0.6))),
    sf("SF-2EG-SW", "WR, RB/FB, DB, LB, L", R_SW, F + [vbar(-0.58, 0.0, 0.56), vbar(0.58, 0.0, 0.56), hbar(0.56)]
       + below(0.56, (-0.42, 0.0, 0.42))),
    sf("SF-2EG-SW-HD", "WR, RB/FB, DB, LB, L", R_HD, F + [vbar(-0.6, 0.0, 0.54), vbar(0.6, 0.0, 0.54), hbar(0.54),
       hbar(0.62)] + below(0.62, (-0.42, 0.0, 0.42))),
    sf("SF-2EG-II", "WR, RB/FB, DB, LB, L", R_STD, F + [vbar(-0.6, 0.0, 0.54), vbar(0.6, 0.0, 0.54), hbar(0.54),
       hbar(0.64)] + below(0.64, (-0.62, -0.31, 0.0, 0.31, 0.62))),
    sf("SF-2EG-II-HD", "WR, RB/FB, DB, LB, L", R_HD, F + [vbar(-0.6, 0.0, 0.54), vbar(0.6, 0.0, 0.54), hbar(0.54),
       hbar(0.64)] + below(0.64, (-0.62, -0.31, 0.0, 0.31, 0.62))),
    sf("SF-2BDC", "LB, L", R_STD, F + [hbar(0.46), hbar(0.60), vbar(-0.3, 0.46, 0.60), vbar(0.3, 0.46, 0.60)]
       + below(0.60, (-0.62, -0.31, 0.0, 0.31, 0.62))),
    sf("SF-2BDC-HD", "LB, L", R_HD, F + [hbar(0.46), hbar(0.60), vbar(-0.3, 0.46, 0.60), vbar(0.3, 0.46, 0.60)]
       + below(0.60, (-0.62, -0.31, 0.0, 0.31, 0.62))),
    sf("SF-3BD", "L", R_STD, F + [hbar(0.40), hbar(0.53), hbar(0.66)] + below(0.40, (-0.62, -0.31, 0.0, 0.31, 0.62))),
    sf("SF-KICKER", "K/P", R_SW, F + [hbar(0.66)] + below(0.66, (-0.36, 0.0, 0.36))),
    sf("AXIOM W-2B-SW-HP", "QB, WR, DB, LB", R_SW, FA + W_BAR + [Rb((-0.35, 0.645), (-0.3, 1.0)), Rb((0.35, 0.645), (0.3, 1.0))]),
    sf("AXIOM W-2B-HP", "QB, WR, DB, LB", R_STD, FA + W_BAR + [Rb((-0.35, 0.645), (-0.3, 1.0)), Rb((0.35, 0.645), (0.3, 1.0))]),
    sf("AXIOM W-2BC-HP", "LB, L", R_STD, FA + W_BAR + [hbar(0.80, -0.95, 0.95)] +
       [Rb((u, 0.62 + 0.04 * (1 - abs(u))), (u, 1.0)) for u in (-0.62, -0.3, 0.0, 0.3, 0.62)]),
    sf("AXIOM W-2EG-HP", "WR, RB/FB, DB, LB, L", R_STD, FA + [vbar(-0.55, 0.0, 0.53), vbar(0.55, 0.0, 0.53)] + W_BAR +
       [Rb((-0.35, 0.645), (-0.3, 1.0)), Rb((0.35, 0.645), (0.3, 1.0)), Rb((0.0, 0.62), (0.0, 1.0))]),
]
assert len(MASKS15) == 15
SLOT_OF = {m["name"]: 12 + i for i, m in enumerate(MASKS15)}


# ====================================================================================================
# build_geometry
# ====================================================================================================

LO_OFFSET = (0.0, 33.89, -4.581)
HEAD_JOINT = {"o3c115": 2, "o3c113": 12}


class FrameScene:
    """A retail scene seen in the hi frame (lo positions shifted back by LO_OFFSET)."""
    def __init__(self, scene, offset):
        self.s = scene
        self.pos = [sub(p, offset) for p in scene.pos]
        self.uv = scene.uv
        self.subs = scene.subs

    def by_material(self, name):
        return self.s.by_material(name)


def cap_vertex_clamp(radius, cap_points, margin=0.35, spread_deg=18.0):
    """Pull the surface in around each cap vertex it would reach past (smooth over spread_deg)."""
    pulls = []
    for q in cap_points:
        dq = norm(sub(q, C))
        need = radius(dq) - (math.dist(q, C) - margin)
        if need > 0:
            pulls.append((dq, need))
    cos_s = math.cos(math.radians(spread_deg))
    def r(d):
        base = radius(d)
        cut = 0.0
        for dq, need in pulls:
            c = dot(d, dq)
            if c > cos_s:
                ang = math.degrees(math.acos(min(1.0, c)))
                cut = max(cut, need * (1.0 - smooth(0.0, spread_deg, ang)))
        return base - cut
    r.pulls = len(pulls)
    return r


def shell(scene_hi_frame, cap, nt, nc, ns, material="HI_HELMET_C", holes=()):
    d = speedflex_design()
    base_r = d["radius"]
    pre = patch_dirs(dict(d), retail_design(scene_hi_frame, material)[1], nt, nc, ns)
    samples = [dd for g in pre.values() for row in g for dd in row]
    cap_points = sorted({q for t in cap for q in t})
    d["radius"] = cap_vertex_clamp(clamped_radius_smooth(base_r, cap, 0.45, 35.0, samples), cap_points)
    m = build_shell_v2(d, scene_hi_frame, material, nt, nc, ns, holes)
    m["uv"], m["uv_fixed"] = sanitize_uvs(m["uv"], m["tris"], allowed_uv_mask(), allowed_uv_mask(extra=ART_EARS))
    m["pos"] = settle_under_cap(m["pos"], m["tris"], cap_points)
    m["nrm"] = seam_normals(m["pos"], m["tris"])
    m["radius_fn"] = d["radius"]
    return m


def closest_on_triangle(p, a, b, c):
    """The closest point of triangle abc to p, as barycentric weights (Ericson, Real-Time Collision Detection 5.1.5)."""
    ab, ac, ap = sub(b, a), sub(c, a), sub(p, a)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return (1.0, 0.0, 0.0)
    bp = sub(p, b); d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return (0.0, 1.0, 0.0)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3); return (1.0 - v, v, 0.0)
    cp = sub(p, c); d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return (0.0, 0.0, 1.0)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6); return (1.0 - w, 0.0, w)
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6)); return (0.0, 1.0 - w, w)
    denom = 1.0 / (va + vb + vc)
    v, w = vb * denom, vc * denom
    return (1.0 - v - w, v, w)


def uvs_from_shell(coarse, fine):
    """UVs for `coarse` sampled from `fine` (both shell() results in the same frame): each coarse vertex takes the UV
    of the nearest point on the fine shell's triangles of the same patch (crown / R / L)."""
    def patch_of(m):
        out = {}
        for name, rows in m["rows"].items():
            for row in rows:
                for k in row:
                    out[k] = name
        return out
    cp, fp = patch_of(coarse), patch_of(fine)
    tris = {name: [t for t in fine["tris"] if len(set(t)) == 3 and all(fp.get(k) == name for k in t)]
            for name in fine["rows"]}
    uv = list(coarse["uv"])
    for k, p in enumerate(coarse["pos"]):
        name = cp.get(k)
        if name is None:
            continue
        best = None
        for t in tris[name]:
            a, b, c = (fine["pos"][i] for i in t)
            w = closest_on_triangle(p, a, b, c)
            q = add(add(mul(a, w[0]), mul(b, w[1])), mul(c, w[2]))
            d = math.dist(p, q)
            if best is None or d < best[0]:
                best = (d, t, w)
        _d, t, w = best
        uv[k] = tuple(sum(fine["uv"][t[i]][j] * w[i] for i in range(3)) for j in range(2))
    return uv


def seam_normals(pos, tris):
    nrm = vertex_normals(pos, tris)
    groups = collections.defaultdict(list)
    for k, p in enumerate(pos):
        groups[tuple(round(c, 3) for c in p)].append(k)
    for ks in groups.values():
        if len(ks) > 1:
            n = norm(sum_vec([nrm[k] for k in ks]))
            for k in ks:
                nrm[k] = n
    return nrm


def settle_under_cap(pos, tris, cap_points, margin=0.3, rounds=8):
    """Where a triangle's chord still passes a covering cap vertex (the brow lip under the cap's front edge), scale
    that triangle's vertices toward C until it sits margin inside; coincident seam copies move together."""
    pos = list(pos)
    groups = collections.defaultdict(list)
    for k, p in enumerate(pos):
        groups[tuple(round(c, 3) for c in p)].append(k)
    group_of = {k: key for key, ks in groups.items() for k in ks}
    rays = [(norm(sub(q, C)), math.dist(q, C)) for q in cap_points]
    live = [t for t in tris if len(set(t)) == 3]
    for _ in range(rounds):
        moved = False
        for dq, rq in rays:
            for a, b, c in live:
                h = ray_hit(dq, [(pos[a], pos[b], pos[c])])
                if h is not None and h > rq - margin:
                    f = (rq - margin) / h
                    for k in {a, b, c}:
                        for j in groups[group_of[k]]:
                            pos[j] = add(C, mul(sub(pos[j], C), f))
                    moved = True
        if not moved:
            break
    return pos


def surface_point(radius_fn, p, lift):
    """Project p radially onto the shell surface and lift it outward."""
    dd = norm(sub(p, C))
    return add(C, mul(dd, radius_fn(dd) + lift)), dd


def plate(radius_fn, centre, half_w, half_h, uv_rect, cols, lift, *, mirror_u=False, facing=None):
    """A decal plate (cols x 2 vertices) on the shell around centre; uv_rect = (u0, u1, v_top, v_bottom)."""
    dd = norm(sub(centre, C))
    up = (0.0, 1.0, 0.0)
    right = norm(cross(up, dd)) if facing is None else facing
    upv = norm(cross(dd, right))
    pos, uv = [], []
    for r, (sy, vt) in enumerate(((1.0, uv_rect[2]), (-1.0, uv_rect[3]))):
        for c in range(cols):
            sx = -1.0 + 2.0 * c / (cols - 1)
            target = add(centre, add(mul(right, sx * half_w), mul(upv, sy * half_h)))
            p, _ = surface_point(radius_fn, target, lift)
            u = uv_rect[0] + (uv_rect[1] - uv_rect[0]) * (c / (cols - 1))
            if mirror_u:
                u = uv_rect[1] - (uv_rect[1] - uv_rect[0]) * (c / (cols - 1))
            pos.append(p); uv.append((u, vt))
    strip = []
    for c in range(cols):
        strip += [c, cols + c]
    return pos, uv, strip


# A UV spot that is dark in every team's 2026 helmet02 master (a vent oval of the retail template, radius 4 px of
# 256; measured over the 31 u1 masters): the notch samples only this texel, so it reads as a dark cut.
DARK_UV = (0.2754, 0.8613)


def surface_at(radius_fn, x, y, lift, z_hi=40.0):
    """The shell point seen from the front at (x, y) (the largest z on the surface), lifted along its radial."""
    lo, hi = C[2], z_hi
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        p = (x, y, mid)
        d = norm(sub(p, C))
        if math.dist(p, C) <= radius_fn(d):
            lo = mid
        else:
            hi = mid
    p = (x, y, lo)
    d = norm(sub(p, C))
    return add(C, mul(d, radius_fn(d) + lift))


# FIG. 4 (front view) flex panel cut, centre line of the drawn double line: (u across the front view, v from the crown)
SF_FLEX_U = [(0.37, 0.075), (0.30, 0.18), (0.355, 0.305), (0.645, 0.305), (0.70, 0.18), (0.63, 0.075)]


def flex_notch(radius_fn=None, width=0.5, lift=0.25):
    """The SpeedFlex front flex panel's cut (US D752,821, the claimed U: its closed bar low on the forehead, the legs
    running up toward the crown) as a thin dark ribbon: 6 path points, 12 vertices, one strip."""
    W = 2.0 * 0.4507 * SF_H                   # FIG. 4 width
    path = []
    for u, v in SF_FLEX_U:
        x, y = (u - 0.5) * W, sf_y(v)
        p = (x, y, SF_LOFT.front_z(x, y))
        path.append(add(p, mul(norm(sub(p, C)), lift)))
    pos = []
    n = len(path)
    for k, p in enumerate(path):
        t = norm(sub(path[min(k + 1, n - 1)], path[max(k - 1, 0)]))
        o = norm(sub(p, C))
        side = norm(cross(t, o))
        pos += [add(p, mul(side, width / 2)), sub(p, mul(side, width / 2))]
    return pos, [DARK_UV] * len(pos), list(range(len(pos)))


def visor(env, cols, rows, inset, frame_offset=(0.0, 0.0, 0.0)):
    pos, strip = [], []
    for r in range(rows):
        for c in range(cols):
            u = -0.9 + 1.8 * c / (cols - 1)
            v = 0.02 + 0.40 * r / (rows - 1)
            p = env(u, v)
            # pull the visor inside the bars, toward the face
            p = (p[0] * 0.97, p[1], p[2] - inset)
            pos.append(add(p, frame_offset))
    strips = []
    for r in range(rows - 1):
        s_ = []
        for c in range(cols):
            s_ += [r * cols + c, (r + 1) * cols + c]
        strips.append(s_)
    centre = add((0.0, 38.0, 8.0), frame_offset)      # the visor's normals look away from this point
    return pos, join_strips(strips, pos, lambda k: sub(pos[k], centre))


def lo_facemask(env, frame_offset):
    """19 vertices on the mask envelope: 7 rows x (centre + 2 sides mirrored) + wings; half-mask UVs."""
    pos, uv = [], []
    idx = {}
    vs = (0.0, 0.33, 0.66, 1.0)
    us = (0.0, 0.5, 1.0)
    for vi, v in enumerate(vs):
        for ui, u in enumerate(us):
            for side in ((1,) if u == 0.0 else (1, -1)):
                p = env(side * u, v)
                idx[(vi, ui, side)] = len(pos)
                pos.append(add(p, frame_offset))
                uv.append((0.007 + 0.74 * u, 0.02 + 0.97 * v))
    # wings back to the top clip (2) + lower clip (2): 4 more -> 7*... keep total at 19 with the rows above (4*5=20)
    return pos, uv, idx


def normals_for(pos, tris):
    return vertex_normals(pos, tris)


def tangents(pos, uv, tris, nrm):
    acc_t = [(0.0, 0.0, 0.0)] * len(pos); acc_b = [(0.0, 0.0, 0.0)] * len(pos)
    for a, b, c in tris:
        e1, e2 = sub(pos[b], pos[a]), sub(pos[c], pos[a])
        du1, dv1 = uv[b][0] - uv[a][0], uv[b][1] - uv[a][1]
        du2, dv2 = uv[c][0] - uv[a][0], uv[c][1] - uv[a][1]
        det = du1 * dv2 - du2 * dv1
        if abs(det) < 1e-12:
            continue
        t = mul(sub(mul(e1, dv2), mul(e2, dv1)), 1.0 / det)
        bv = mul(sub(mul(e2, du1), mul(e1, du2)), 1.0 / det)
        for k in (a, b, c):
            acc_t[k] = add(acc_t[k], t); acc_b[k] = add(acc_b[k], bv)
    out_t, out_b = [], []
    for k in range(len(pos)):
        n = nrm[k]
        t = sub(acc_t[k], mul(n, dot(acc_t[k], n)))
        t = norm(t) if dot(t, t) > 1e-12 else norm(cross((0.0, 1.0, 0.0), n))
        b = mul(acc_b[k], -1.0)                       # the retail binormal points against increasing v
        b = sub(b, mul(n, dot(b, n)))
        b = norm(b) if dot(b, b) > 1e-12 else norm(cross(n, t))
        out_t.append(t); out_b.append(b)
    return out_t, out_b


def encode_part(layout, positions, normals, uvs, selector, strip, tangent=None, binormal=None):
    lanes = layout.lanes
    recs = bytearray()
    for k, p in enumerate(positions):
        q = [models.encode_normshort(max(-1.0, min(1.0, (p[a] - lanes.offset[a]) / lanes.scale))) for a in range(3)]
        n = normals[k]
        s0 = struct.pack("<3hI", q[0], q[1], q[2], models.encode_normpacked3(*n))
        uq = models.uv_from_gltf(uvs[k][0], uvs[k][1], lanes.uv_scale, lanes.uv_offset)
        s1 = struct.pack("<2hh", uq[0], uq[1], selector)
        rec = s0 + s1
        if tangent is not None:
            rec += struct.pack("<II", models.encode_normpacked3(*tangent[k]), models.encode_normpacked3(*binormal[k]))
        recs += rec
    return {"records": base64.b64encode(bytes(recs)).decode(),
            "strip": base64.b64encode(struct.pack(f"<{len(strip)}H", *strip)).decode(),
            "selector": selector}


def head_selector(scene_obj, layout, name, joint):
    sub_ = layout.by_name()[name]
    first, last = struct.unpack_from("<HH", scene_obj.decoded, sub_.record + 4)
    maps = struct.unpack_from("<56H", scene_obj.decoded, sub_.record + 8)
    for slot in range(first, last + 1):
        if maps[slot] == joint:
            return 3 * slot
    raise ValueError(f"{name}: no palette slot maps the head joint")


def front_silhouette(scene, name, size=48):
    """Front-view coverage raster of a retail facemask, normalised to its own bounding box."""
    sub_ = scene.by_material(name)[0]
    pts = [scene.pos[v] for v in sub_["verts"]]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    img = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(img)
    for t in sub_["tris"]:
        poly = [((scene.pos[v][0] - x0) / (x1 - x0) * (size - 1), (y1 - scene.pos[v][1]) / (y1 - y0) * (size - 1)) for v in t]
        d.polygon(poly, fill=255)
    return img.tobytes()


def nearest_retail_masks(scene):
    """For every mask outside 0-11, the retail mask 0-11 with the most similar front silhouette (IoU)."""
    sil = {m: front_silhouette(scene, f"FACEMASK{m:02d}") for m in range(27)}
    out = {}
    for m in range(12, 27):
        def iou(k):
            a, b = sil[m], sil[k]
            inter = sum(1 for x, y in zip(a, b) if x and y)
            union = sum(1 for x, y in zip(a, b) if x or y)
            return inter / union if union else 0.0
        out[m] = max(range(12), key=lambda k: (iou(k), -k))
    return out


def historic_equipment_edits(scene):
    """Every historic record that would otherwise show a modern part: Revolution -> Standard, masks 12-26 -> the
    nearest retail mask 0-11. {outer: [[index, field, retail, classic], ...]}"""
    from mod_editor.core import nfl2k5_roster_records as rr
    nearest = nearest_retail_masks(scene)
    edits = {}
    for outer in mh.HISTORIC_OUTERS:
        payload = outer_bytes(outer)
        doc = rr.RosterDocument(payload[32:])
        rows = []
        for p in doc.players:
            v = p.record.values
            if v["helmet"] != 0:
                rows.append([p.index, "helmet", v["helmet"], 0])
            if v["face_mask"] not in mh.CLASSIC_MASKS:
                rows.append([p.index, "face_mask", v["face_mask"], nearest[v["face_mask"]]])
        if rows:
            edits[str(outer)] = rows
    return edits, nearest


def shape_entry(layout):
    return {"vertex_count": layout.vertex_count, "scale": layout.lanes.scale, "offset": list(layout.lanes.offset),
            "uv": [*layout.lanes.uv_scale, *layout.lanes.uv_offset]}


# ---------------------------------------------------------------------------------------------- Revolution details
# Pass 4 (Noah 9/25: "take the game's default Riddell helmet, maintain its shape, and simply add the details and
# indentions that the modern helmets have"): the retail Revolution shell C keeps its geometry and texture coordinates,
# so every team's art maps as designed. Thin dark parts sit just above it: the SpeedFlex's flex-panel cut (the claimed
# design of US D752,821), its vents and its jaw and rear-shelf seams, placed after the patent's FIG. 1-5 and the
# riddell.com team photos, over the art's own painted Revolution vents where they fall, and around the logos
# (hm busy map of the 32 team masters). The mesh has no vertex colour, so darkness comes from the texture: every
# detail vertex samples DARK_UV, a texel that is near black in all 32 helmet masters. They are drawn by
# LOGO_helmet_C (the helmet decals: the same team texture, without the shell's reflection weight, so the vents read
# as matte openings); that submesh's commands move to the facemask run's spare words (its 26 retail indices, then
# the details) and the details' vertices follow the masks there.
REV_CENTRE = C                  # features are placed by azimuth / elevation seen from here (az 0 front, +90 the +x side)
REV_HOST_SUBMESH = "LOGO_helmet_C"
REV_LIFT = 0.12                 # cm above the shell
REV_MAX_SAG = 0.04              # cm: a path segment whose chord dips further below the shell is split
# (name, [(azimuth, elevation, width cm), ...], mirrored to -azimuth)
REV_FEATURES = [
    # the flex panel's U-shaped cut (the claimed design of US D752,821; riddell.com front photos): the bar across the
    # forehead above the front bumper, the legs up over the crown, widening where they run through the art's painted
    # front vents so those read as the legs' ends
    ("flex_panel", [(-48, 65.0, 0.6), (-45, 63.5, 1.2), (-41, 60.5, 1.4), (-37, 56.5, 1.2), (-33, 51.5, 0.5),
                    (-29.5, 46.0, 0.45), (-26.5, 40.5, 0.45), (-23, 36.5, 0.45), (-19, 34.8, 0.45), (-12, 34.2, 0.45),
                    (0, 34.0, 0.45), (12, 34.2, 0.45), (19, 34.8, 0.45), (23, 36.5, 0.45), (26.5, 40.5, 0.45),
                    (29.5, 46.0, 0.45), (33, 51.5, 0.5), (37, 56.5, 1.2), (41, 60.5, 1.4), (45, 63.5, 1.2),
                    (48, 65.0, 0.6)], False),
    # the temple vent outside the U's leg, in front of the logo, pointing forward and down (FIG. 1, 2, 4)
    ("temple_vent", [(31, 29.0, 0.4), (34, 31.5, 1.1), (37.5, 34.5, 1.3), (40.5, 38.0, 0.6)], True),
    # the crown vents at mid-length, over the art's painted top vents (FIG. 5)
    ("top_vent", [(62, 76.0, 0.6), (75, 77.5, 1.2), (90, 78.0, 1.25), (105, 77.5, 1.2), (118, 76.0, 0.6)], True),
    # the upper rear vents, over the art's painted rear vents (FIG. 2, 5)
    ("rear_top_vent", [(128, 62.0, 0.5), (137, 60.0, 1.3), (146, 57.0, 1.5), (152, 54.0, 0.7)], True),
    # the side vent behind the ear, below the logo (FIG. 1, 2; riddell.com side photos)
    ("side_vent", [(104, 10.0, 0.6), (111, 9.5, 1.2), (120, 9.0, 1.2), (127, 9.5, 0.6)], True),
    # the two slots on the back (FIG. 2)
    ("back_vent", [(156, 40.0, 0.5), (159, 34.0, 1.0), (162, 28.0, 0.5)], True),
    # the jaw flap's seam: from the brow corner back above the ear hole, then down behind it (FIG. 2)
    ("jaw_seam", [(34, 12.0, 0.3), (45, 9.0, 0.3), (56, 5.0, 0.3), (66, 2.0, 0.3), (80, 2.0, 0.3), (96, 2.5, 0.3),
                  (108, 1.5, 0.3), (114, -3.0, 0.3), (117, -10.0, 0.3), (118, -20.0, 0.3)], True),
    # the rear shelf's step above the rear bumper (clear of the flag decal at azimuth -155 .. -138)
    ("rear_shelf", [(160, -9.5, 0.4), (170, -10.2, 0.4), (180, -10.5, 0.4), (190, -10.2, 0.4), (200, -9.5, 0.4)], False),
]


def rev_dir(az, el):
    a, e = math.radians(az), math.radians(el)
    return (math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e))


class RetailShell:
    """The retail HI_HELMET_C surface: rays from REV_CENTRE give the outermost point, its face normal and the
    texture coordinates there."""

    def __init__(self, scene_obj):
        sub_ = scene_obj.by_material("HI_HELMET_C")[0]
        self.tris = [t for t in sub_["tris"] if len(set(t)) == 3]
        self.pos, self.uv = scene_obj.pos, scene_obj.uv

    def cast(self, az, el):
        d = rev_dir(az, el)
        best = None
        for t in self.tris:
            a, b, c = (self.pos[i] for i in t)
            e1, e2 = sub(b, a), sub(c, a)
            h = cross(d, e2); det = dot(e1, h)
            if abs(det) < 1e-12:
                continue
            f = 1.0 / det; s_ = sub(REV_CENTRE, a); u = f * dot(s_, h)
            if u < -1e-6 or u > 1 + 1e-6:
                continue
            q = cross(s_, e1); v = f * dot(d, q)
            if v < -1e-6 or u + v > 1 + 1e-6:
                continue
            tt = f * dot(e2, q)
            if tt > 0 and (best is None or tt > best[0]):
                n = norm(cross(e1, e2))
                if dot(n, d) < 0:
                    n = mul(n, -1.0)
                w = (1.0 - u - v, u, v)
                uv = tuple(sum(self.uv[t[i]][j] * w[i] for i in range(3)) for j in range(2))
                best = (tt, add(REV_CENTRE, mul(d, tt)), n, uv)
        mh.require(best is not None, f"no retail shell at azimuth {az}, elevation {el}")
        return best[1], best[2], best[3]


def rev_samples(shell_, path):
    """The path's points plus the ones needed so no chord dips more than REV_MAX_SAG below the shell."""
    def split(p, q, depth):
        m = tuple((p[k] + q[k]) / 2 for k in range(3))
        hp, hq, hm = shell_.cast(p[0], p[1]), shell_.cast(q[0], q[1]), shell_.cast(m[0], m[1])
        below = dot(sub(hm[0], mul(add(hp[0], hq[0]), 0.5)), hm[1])
        if depth < 4 and below > REV_MAX_SAG:
            return split(p, m, depth + 1) + [m] + split(m, q, depth + 1)
        return []
    out = [path[0]]
    for p, q in zip(path, path[1:]):
        out += split(p, q, 0) + [q]
    return out


def rev_ribbon(shell_, path):
    """A dark ribbon along (az, el, width) samples, lifted REV_LIFT above the shell; corners are mitred."""
    pts = rev_samples(shell_, path)
    hits = [shell_.cast(a, e) for a, e, _w in pts]
    pos, nrm = [], []
    n = len(hits)
    for i, (p, nv, _uv) in enumerate(hits):
        t = norm(sub(hits[min(i + 1, n - 1)][0], hits[max(i - 1, 0)][0]))
        side = norm(cross(t, nv))
        scale = 1.0
        if 0 < i < n - 1:                           # mitre: keep the width across a bend
            t1 = norm(sub(hits[i][0], hits[i - 1][0])); t2 = norm(sub(hits[i + 1][0], hits[i][0]))
            c = max(-1.0, min(1.0, dot(t1, t2)))
            scale = min(1.6, 1.0 / max(math.cos(math.acos(c) / 2), 1e-3))
        half = pts[i][2] / 2 * scale
        base = add(p, mul(nv, REV_LIFT))
        pos += [add(base, mul(side, half)), sub(base, mul(side, half))]
        nrm += [nv, nv]
    return pos, nrm, [list(range(len(pos)))]


def rev_parts(hi):
    """{feature name (with _L for the mirrored copy): (positions, normals, strips)} on the retail shell."""
    shell_ = RetailShell(hi)
    out = {}
    for name, path, mirrored in REV_FEATURES:
        out[name] = rev_ribbon(shell_, path)
        if mirrored:
            out[name + "_L"] = rev_ribbon(shell_, [(-a, e, w) for a, e, w in path])
    return out


def build_shell_details(hi, lay_hi):
    """The pass-4 details as one extra-vertex block drawn by REV_HOST_SUBMESH (see nfl2k5_modern_helmets.author)."""
    pos, nrm, strips = [], [], []
    for p_, n_, s_ in rev_parts(hi).values():
        base = len(pos)
        pos.extend(p_); nrm.extend(n_)
        strips.extend([[base + i for i in st] for st in s_])
    strip = join_strips(strips, pos, lambda k: nrm[k])
    part = encode_part(lay_hi, pos, nrm, [DARK_UV] * len(pos),
                       head_selector(hi, lay_hi, REV_HOST_SUBMESH, HEAD_JOINT["o3c115"]), strip)
    batches = hi.by_material(REV_HOST_SUBMESH)[0]["batches"]
    mh.require(len(batches) == 1 and batches[0][0] == 6, f"the retail {REV_HOST_SUBMESH} is expected as one strip")
    retail = batches[0][1]
    return {"host": "FACEMASK12", "submesh": REV_HOST_SUBMESH, "records": part["records"], "strip": part["strip"],
            "retail_strip": base64.b64encode(struct.pack(f"<{len(retail)}H", *retail)).decode()}, len(pos)


# ---------------------------------------------------------------------------------------------- pass 5: the masks
# Noah 9/25 on pass 4: "the facemasks don't look like the references, they are too tall and skinny". Each of the 15
# masks is measured on riddell.com's product photos of that mask (front and side CAD renders of the mask alone,
# 1200 px, one camera per family): MASK_PHOTO holds the bar centrelines traced on the FRONT photo (right half, photo
# px; tools/hm scratch mask_digitize.py snaps waypoints to the photo's bar skeleton) and, from the SIDE photo, the
# depth of the bars that cross the centre (their centreline's x on the side photo); MASK_FAMILY the frame's and the
# SpeedFlex side bar's x on the side photo by row. Front view: x = (px - PHOTO_CX) * s and y = PHOTO_TOP_Y - (py -
# the top bar's row) * s, s from the frame's outer width, 22.8 cm (the span of the retail masks on this shell).
# Depth: z = z_front - k * (side px - front px) * s, where k and z_front are solved per mask so that the top bar
# clears the shell's brow and the frame's back-most point sits on the shell (the Revolution is shallower than the
# SpeedFlex, so k < 1). Between the centre and the side bars the depth eases in (MASK_EASE: the photos' masks are
# flat across the inner bars). Every point then stays outside the shell and the face.
PHOTO_CX = 599.0
PHOTO_SCALE = {"SF": 22.8 / 980.0, "AX": 22.8 / 1056.0}
# The SpeedFlex masks whose photos show the same frame (the traced frames agree after the given shift, px) wear it byte
# for byte: the frame is the reference style's, at MASK_FRAME_RADIUS, and the style's own bars are shifted onto it
# (the same frame in consecutive masks also keeps hi_head inside its stored span). The Axiom frames differ per mask.
MASK_FRAME_REF = {"SF-2BD": ("SF-2BD-SW", 0, 0), "SF-2EG-SW": ("SF-2BD-SW", 0, 0),
                  "SF-2EG-SW-HD": ("SF-2BD-HD", 8, 4), "SF-2EG-II": ("SF-2BD-HD", 0, 0),
                  "SF-2EG-II-HD": ("SF-2BD-HD", 0, 0), "SF-2BDC": ("SF-2BD-HD", 0, 0), "SF-2BDC-HD": ("SF-2BD-HD", 0, 0)}
MASK_FRAME_ROLES = ("raised", "ear", "ear2", "tab", "tab2", "top", "B", "chin", "A")
MASK_FRAME_RADIUS = 0.40
PHOTO_TOP_Y = {"SF": 44.7, "AX": 44.5}
MASK_EASE = 4.0
SEAT_GAP = 0.25
MASK_FAMILY = {
    'SF': dict(ref='SF-2BD-SW', front_x=329,
              frame=[(245, 855), (300, 875), (350, 895), (372, 890), (440, 780), (500, 755), (570, 735), (600, 770),
                     (670, 815), (745, 860), (810, 760), (880, 660), (920, 560), (955, 440)],
              A=[(285, 620), (450, 635), (600, 645), (890, 660)]),
    'AX': dict(ref='AXIOM-W-2B-HP-S', front_x=281,
              frame=[(232, 620), (300, 700), (355, 775), (400, 770), (545, 745), (640, 790), (725, 840), (800, 720),
                     (860, 630), (920, 530), (955, 515)]),
}
MASK_PHOTO = {
    'SF-2BD-SW': dict(ref='SF-2BD-SW', family='SF', radius=0.34,
        centre=[(246, 384), (290, 377), (638, 329), (952, 437)],
        bars={
            'raised': [(600, 246), (870, 246), (916, 254), (956, 276)],
            'ear': [(956, 276), (1010, 274), (1016, 268), (1056, 258)],
            'tab': [(598, 250), (598, 288)],
            'top': [(600, 290), (834, 300), (1008, 324)],
            'B': [(1056, 258), (1062, 260), (1066, 272), (1072, 362), (1068, 380), (1038, 438), (1024, 490),
                  (1008, 580), (1010, 602), (1006, 608), (1000, 748), (978, 818)],
            'chin': [(978, 818), (958, 836), (900, 866), (876, 870), (864, 886), (796, 922), (760, 934), (730, 936),
                     (722, 942), (688, 948), (600, 952)],
            'A': [(1004, 274), (1012, 278), (1010, 320), (1006, 324), (996, 322), (1004, 326), (1002, 350),
                  (956, 574), (954, 608), (944, 620), (940, 678), (934, 684), (926, 716), (880, 836), (874, 870)],
            'h1': [(600, 638), (720, 638), (828, 632), (914, 616), (946, 616), (952, 610), (1004, 608), (1006, 616)],
            'v1': [(772, 636), (764, 728), (728, 906), (726, 938)],
        }),
    'SF-2BD': dict(ref='SF-2BD-SW', family='SF', radius=0.4,
        centre=[(246, 384), (290, 377), (638, 329), (952, 437)],
        bars={
            'raised': [(600, 246), (870, 246), (916, 254), (956, 276)],
            'ear': [(956, 276), (1010, 274), (1016, 268), (1056, 258)],
            'tab': [(598, 250), (598, 288)],
            'top': [(600, 290), (834, 300), (1008, 324)],
            'B': [(1056, 258), (1062, 260), (1066, 272), (1072, 362), (1068, 380), (1038, 438), (1024, 490),
                  (1008, 580), (1010, 602), (1006, 608), (1000, 748), (978, 818)],
            'chin': [(978, 818), (958, 836), (900, 866), (876, 870), (864, 886), (796, 922), (760, 934), (730, 936),
                     (722, 942), (688, 948), (600, 952)],
            'A': [(1004, 274), (1012, 278), (1010, 320), (1006, 324), (996, 322), (1004, 326), (1002, 350),
                  (956, 574), (954, 608), (944, 620), (940, 678), (934, 684), (926, 716), (880, 836), (874, 870)],
            'h1': [(600, 638), (720, 638), (828, 632), (914, 616), (946, 616), (952, 610), (1004, 608), (1006, 616)],
            'v1': [(772, 636), (764, 728), (728, 906), (726, 938)],
        }),
    'SF-2BD-HD': dict(ref='SF-2BD-HD', family='SF', radius=0.45,
        centre=[(246, 378), (294, 367), (652, 310), (658, 311), (718, 321), (722, 321), (778, 335), (838, 356),
                (898, 383), (952, 413)],
        bars={
            'raised': [(600, 246), (674, 244), (796, 250), (800, 256), (804, 252), (846, 254), (874, 258), (888, 272),
                       (1000, 284)],
            'ear': [(1000, 284), (1056, 270)],
            'tab': [(598, 250), (600, 294)],
            'tab2': [(800, 258), (800, 300)],
            'top': [(600, 294), (818, 302), (870, 288), (884, 272)],
            'B': [(1056, 270), (1072, 278), (1078, 364), (1044, 440), (1030, 492), (1016, 562), (1006, 750),
                  (982, 822)],
            'chin': [(982, 822), (968, 834), (902, 868), (874, 874), (860, 892), (802, 922), (758, 936), (728, 938),
                     (694, 948), (600, 952)],
            'A': [(1002, 284), (1008, 292), (1008, 320), (956, 574), (954, 608), (944, 620), (940, 680), (928, 690),
                  (924, 720), (876, 848), (874, 874)],
            'h1': [(598, 652), (600, 638), (802, 634), (860, 628), (914, 616), (946, 616), (952, 610), (1002, 608)],
            'h2': [(598, 722), (600, 708), (768, 706), (930, 688), (946, 680), (1006, 678), (1008, 684)],
            'v0': [(598, 638), (598, 952)],
            'v1': [(772, 636), (770, 704), (762, 714), (760, 754), (728, 906), (726, 938)],
        }),
    'SF-2EG-SW': dict(ref='SF-2EG-SW', family='SF', radius=0.34,
        centre=[(246, 384), (290, 377), (638, 329), (952, 437)],
        bars={
            'raised': [(600, 246), (870, 246), (916, 254), (956, 276)],
            'ear': [(956, 276), (1010, 274), (1016, 268), (1056, 258)],
            'tab': [(598, 250), (598, 288)],
            'top': [(600, 290), (834, 300), (1008, 324)],
            'B': [(1056, 258), (1062, 260), (1066, 272), (1072, 362), (1068, 380), (1038, 438), (1024, 490),
                  (1008, 580), (1010, 602), (1006, 608), (1000, 748), (978, 818)],
            'chin': [(978, 818), (962, 834), (900, 866), (876, 870), (864, 886), (780, 928), (688, 948), (600, 952)],
            'A': [(1004, 274), (1012, 278), (1010, 320), (1006, 324), (996, 322), (1004, 326), (1002, 350),
                  (956, 574), (954, 608), (944, 620), (940, 678), (934, 684), (926, 716), (882, 830), (874, 870)],
            'h1': [(600, 638), (720, 638), (828, 632), (894, 622), (910, 614), (946, 616), (952, 610), (1004, 608),
                   (1006, 616)],
            'v1': [(772, 636), (764, 728), (728, 906), (726, 938)],
            'eg1': [(930, 316), (906, 592), (908, 614)],
        }),
    'SF-2EG-SW-HD': dict(ref='SF-2EG-SW-HD', family='SF', radius=0.45,
        centre=[(256, 371), (304, 354), (618, 302), (946, 405)],
        bars={
            'raised': [(600, 256), (730, 258), (874, 270), (882, 272), (896, 288), (940, 292), (950, 300), (992, 302),
                       (1004, 298)],
            'ear': [(1004, 298), (1014, 298), (1034, 286), (1054, 282), (1060, 270)],
            'tab': [(600, 256), (596, 258), (596, 292)],
            'tab2': [(800, 264), (792, 270), (792, 300)],
            'top': [(600, 304), (838, 310), (882, 302), (896, 288), (940, 292)],
            'B': [(1060, 270), (1056, 282), (1070, 294), (1074, 374), (1070, 390), (1036, 454), (1006, 550),
                  (998, 748), (976, 822)],
            'chin': [(976, 822), (970, 830), (910, 862), (882, 866), (864, 886), (786, 922), (690, 942), (600, 946)],
            'A': [(1004, 298), (992, 302), (996, 318), (994, 346), (956, 548), (954, 586), (944, 602), (940, 660),
                  (884, 838), (882, 866)],
            'h1': [(600, 618), (762, 616), (868, 606), (896, 602), (912, 594), (946, 594), (968, 588), (1000, 588),
                   (1002, 604)],
            'v1': [(762, 616), (752, 712), (716, 904), (714, 934)],
            'eg1': [(948, 298), (936, 312), (904, 596)],
        }),
    'SF-2EG-II': dict(ref='SF-2EG-II-HD', family='SF', radius=0.4,
        centre=[(246, 378), (294, 367), (652, 310), (658, 311), (718, 321), (722, 321), (778, 335), (838, 356),
                (898, 383), (952, 413)],
        bars={
            'raised': [(600, 246), (676, 244), (796, 250), (800, 256), (804, 252), (846, 254), (874, 258), (888, 272),
                       (930, 274), (950, 282), (1000, 284)],
            'ear': [(1000, 284), (1056, 270)],
            'tab': [(598, 250), (600, 294)],
            'tab2': [(800, 258), (800, 300)],
            'top': [(600, 294), (818, 302), (870, 288), (884, 272)],
            'B': [(1056, 270), (1072, 278), (1078, 364), (1044, 440), (1030, 492), (1016, 562), (1006, 750),
                  (982, 822)],
            'chin': [(982, 822), (968, 834), (902, 868), (876, 872), (860, 892), (802, 922), (758, 936), (728, 938),
                     (694, 948), (600, 952)],
            'A': [(1002, 284), (1008, 292), (1008, 320), (956, 574), (954, 608), (944, 620), (940, 680), (928, 690),
                  (924, 720), (876, 848), (874, 872)],
            'h1': [(598, 652), (600, 638), (802, 634), (892, 624), (910, 614), (946, 616), (952, 610), (1002, 608)],
            'h2': [(598, 722), (600, 708), (768, 706), (930, 688), (946, 680), (1006, 678), (1008, 684)],
            'v0': [(598, 638), (598, 952)],
            'v1': [(772, 636), (770, 704), (762, 714), (760, 754), (728, 906), (726, 938)],
            'eg1': [(938, 280), (928, 294), (910, 614)],
        }),
    'SF-2EG-II-HD': dict(ref='SF-2EG-II-HD', family='SF', radius=0.45,
        centre=[(246, 378), (294, 367), (652, 310), (658, 311), (718, 321), (722, 321), (778, 335), (838, 356),
                (898, 383), (952, 413)],
        bars={
            'raised': [(600, 246), (676, 244), (796, 250), (800, 256), (804, 252), (846, 254), (874, 258), (888, 272),
                       (930, 274), (950, 282), (1000, 284)],
            'ear': [(1000, 284), (1056, 270)],
            'tab': [(598, 250), (600, 294)],
            'tab2': [(800, 258), (800, 300)],
            'top': [(600, 294), (818, 302), (870, 288), (884, 272)],
            'B': [(1056, 270), (1072, 278), (1078, 364), (1044, 440), (1030, 492), (1016, 562), (1006, 750),
                  (982, 822)],
            'chin': [(982, 822), (968, 834), (902, 868), (876, 872), (860, 892), (802, 922), (758, 936), (728, 938),
                     (694, 948), (600, 952)],
            'A': [(1002, 284), (1008, 292), (1008, 320), (956, 574), (954, 608), (944, 620), (940, 680), (928, 690),
                  (924, 720), (876, 848), (874, 872)],
            'h1': [(598, 652), (600, 638), (802, 634), (892, 624), (910, 614), (946, 616), (952, 610), (1002, 608)],
            'h2': [(598, 722), (600, 708), (768, 706), (930, 688), (946, 680), (1006, 678), (1008, 684)],
            'v0': [(598, 638), (598, 952)],
            'v1': [(772, 636), (770, 704), (762, 714), (760, 754), (728, 906), (726, 938)],
            'eg1': [(938, 280), (928, 294), (910, 614)],
        }),
    'SF-2BDC': dict(ref='SF-2BDC-HD', family='SF', radius=0.4,
        centre=[(246, 378), (294, 367), (582, 309), (652, 313), (658, 314), (718, 324), (778, 339), (838, 359),
                (898, 386), (952, 417)],
        bars={
            'raised': [(600, 246), (674, 244), (796, 250), (800, 256), (804, 252), (846, 254), (874, 258), (888, 272),
                       (1000, 284)],
            'ear': [(1000, 284), (1056, 270)],
            'tab': [(598, 250), (600, 294)],
            'tab2': [(800, 258), (800, 300)],
            'top': [(600, 294), (818, 302), (870, 288), (884, 272)],
            'B': [(1056, 270), (1072, 278), (1078, 364), (1038, 456), (1028, 528), (1018, 538), (1006, 750),
                  (982, 822)],
            'chin': [(982, 822), (972, 832), (902, 868), (874, 874), (860, 892), (802, 922), (766, 934), (728, 938),
                     (694, 948), (600, 952)],
            'A': [(1002, 284), (1008, 292), (1008, 320), (970, 502), (968, 538), (958, 550), (954, 608), (944, 620),
                  (944, 640), (932, 698), (876, 848), (874, 874)],
            'h1': [(598, 582), (600, 570), (832, 562), (916, 546), (960, 544), (970, 538), (1004, 538)],
            'h2': [(598, 652), (600, 638), (720, 638), (828, 632), (914, 616), (946, 616), (952, 610), (1002, 608)],
            'v0': [(598, 638), (598, 952)],
            'v1': [(780, 566), (778, 632), (772, 636), (766, 718), (746, 836), (728, 910), (726, 938)],
        }),
    'SF-2BDC-HD': dict(ref='SF-2BDC-HD', family='SF', radius=0.45,
        centre=[(246, 378), (294, 367), (582, 309), (652, 313), (658, 314), (718, 324), (778, 339), (838, 359),
                (898, 386), (952, 417)],
        bars={
            'raised': [(600, 246), (674, 244), (796, 250), (800, 256), (804, 252), (846, 254), (874, 258), (888, 272),
                       (1000, 284)],
            'ear': [(1000, 284), (1056, 270)],
            'tab': [(598, 250), (600, 294)],
            'tab2': [(800, 258), (800, 300)],
            'top': [(600, 294), (818, 302), (870, 288), (884, 272)],
            'B': [(1056, 270), (1072, 278), (1078, 364), (1038, 456), (1028, 528), (1018, 538), (1006, 750),
                  (982, 822)],
            'chin': [(982, 822), (972, 832), (902, 868), (874, 874), (860, 892), (802, 922), (766, 934), (728, 938),
                     (694, 948), (600, 952)],
            'A': [(1002, 284), (1008, 292), (1008, 320), (970, 502), (968, 538), (958, 550), (954, 608), (944, 620),
                  (944, 640), (932, 698), (876, 848), (874, 874)],
            'h1': [(598, 582), (600, 570), (832, 562), (916, 546), (960, 544), (970, 538), (1004, 538)],
            'h2': [(598, 652), (600, 638), (720, 638), (828, 632), (914, 616), (946, 616), (952, 610), (1002, 608)],
            'v0': [(598, 638), (598, 952)],
            'v1': [(780, 566), (778, 632), (772, 636), (766, 718), (746, 836), (728, 910), (726, 938)],
        }),
    'SF-3BD': dict(ref='SF-3BD', family='SF', radius=0.4,
        centre=[(246, 384), (290, 377), (582, 307), (654, 311), (658, 312), (718, 321), (778, 334), (810, 344),
                (838, 354), (898, 378), (958, 409), (1006, 439)],
        bars={
            'raised': [(600, 246), (790, 250), (1000, 274)],
            'ear': [(1000, 274), (1060, 258)],
            'tab': [(598, 250), (598, 288)],
            'top': [(600, 290), (834, 300), (1008, 324)],
            'B': [(1060, 258), (1066, 258), (1072, 270), (1078, 364), (1042, 444), (1030, 492), (1028, 526),
                  (1018, 536), (1016, 598), (1012, 604), (1012, 650), (1016, 660), (1010, 674), (1006, 750),
                  (982, 822)],
            'chin': [(982, 822), (968, 834), (928, 854), (894, 884), (882, 886), (874, 900), (828, 940), (770, 976),
                     (684, 1000), (600, 1006)],
            'A': [(1004, 274), (1012, 278), (1010, 320), (1006, 324), (996, 322), (1004, 326), (1002, 350),
                  (972, 492), (968, 536), (960, 542), (954, 606), (944, 620), (934, 708), (900, 760), (896, 796),
                  (870, 864), (870, 874), (878, 888)],
            'h1': [(598, 582), (600, 568), (832, 560), (930, 542), (960, 542), (970, 536), (1016, 536), (1018, 550)],
            'h2': [(598, 654), (598, 640), (608, 636), (724, 636), (830, 630), (916, 614), (946, 614), (954, 608),
                   (992, 606), (1010, 606), (1012, 616)],
            'h3': [(598, 810), (600, 824), (670, 824), (794, 802), (834, 788), (870, 768), (898, 762), (930, 714),
                   (1004, 696), (1010, 690)],
            'v0': [(598, 638), (598, 1006)],
            'v1': [(780, 564), (778, 630), (772, 636), (772, 670), (756, 768), (754, 806)],
        }),
    'SF-KICKER': dict(ref='SF-KICKER', family='SF', radius=0.34,
        centre=[(276, 394), (698, 333), (952, 430)],
        bars={
            'top': [(600, 276), (816, 282), (880, 288), (984, 306), (1000, 304)],
            'ear': [(1000, 304), (1016, 302), (1036, 288), (1056, 284), (1062, 270)],
            'B': [(1062, 270), (1058, 282), (1072, 296), (1076, 372), (1036, 462), (1008, 554), (1000, 748),
                  (980, 818)],
            'chin': [(980, 818), (968, 834), (914, 864), (884, 870), (866, 890), (804, 922), (696, 948), (600, 952)],
            'A': [(996, 306), (996, 350), (958, 552), (956, 592), (950, 600), (944, 630), (942, 664), (934, 672),
                  (930, 708), (888, 834), (884, 870)],
            'h1': [(600, 698), (826, 688), (902, 672), (936, 670), (942, 664), (954, 662), (1002, 660)],
            'v1': [(756, 694), (752, 750), (720, 910), (718, 940)],
        }),
    'AXIOM W-2B-SW-HP': dict(ref='AXIOM-W-2B-SW-HP-S', family='AX', radius=0.34,
        centre=[(276, 273), (652, 326), (950, 545)],
        bars={
            'top': [(600, 276), (782, 274), (960, 262), (1056, 252), (1072, 236), (1084, 234)],
            'ear': [(1084, 234), (1108, 236), (1110, 272), (1108, 300), (1092, 316), (1090, 344), (1080, 380)],
            'ear2': [(1064, 258), (1070, 268), (1072, 298), (1092, 316), (1090, 344), (1080, 380)],
            'B': [(1080, 380), (1048, 442), (1008, 574), (1014, 618), (1014, 672), (1006, 724)],
            'chin': [(1006, 724), (1004, 738), (992, 754), (934, 812), (824, 898), (786, 916), (766, 918), (758, 930),
                     (688, 944), (600, 950)],
            'w': [(600, 652), (684, 648), (806, 628), (892, 588), (944, 608), (970, 592), (1006, 582), (1012, 560)],
            'v1': [(820, 620), (814, 626), (812, 654), (796, 692), (740, 798), (758, 910), (764, 920), (762, 928)],
        }),
    'AXIOM W-2B-HP': dict(ref='AXIOM-W-2B-HP-S', family='AX', radius=0.4,
        centre=[(250, 284), (628, 317), (702, 345), (938, 520)],
        bars={
            'top': [(600, 250), (950, 244), (1056, 238), (1070, 224), (1084, 224)],
            'ear': [(1084, 224), (1104, 224), (1108, 228), (1110, 270), (1108, 290), (1092, 306), (1092, 332),
                    (1080, 380)],
            'ear2': [(1068, 256), (1072, 288), (1092, 306), (1092, 332), (1080, 380)],
            'B': [(1080, 380), (1046, 446), (1008, 574), (1014, 580), (1014, 678), (1006, 728)],
            'chin': [(1006, 728), (1002, 746), (952, 794), (838, 882), (792, 904), (766, 908), (760, 918), (686, 932),
                     (600, 938)],
            'w': [(600, 628), (672, 626), (804, 608), (892, 572), (906, 576), (938, 598), (950, 596)],
            'h2': [(600, 702), (666, 700), (778, 688), (796, 680), (804, 670), (832, 670), (860, 660), (924, 624),
                   (940, 598), (1004, 576)],
            'v1': [(820, 600), (814, 606), (804, 672), (778, 688), (772, 720), (740, 778), (758, 896), (764, 910),
                   (760, 918)],
        }),
    'AXIOM W-2BC-HP': dict(ref='AXIOM-W-2BC-HP-S', family='AX', radius=0.4,
        centre=[(316, 252), (620, 293), (640, 290), (700, 317), (744, 341), (760, 350), (820, 391), (880, 440),
                (940, 501), (968, 535)],
        bars={
            'top': [(600, 316), (726, 314), (920, 298), (1060, 274), (1074, 256), (1088, 252)],
            'ear': [(1088, 252), (1104, 250), (1110, 256), (1110, 282), (1108, 298), (1092, 314), (1090, 346),
                    (1080, 384)],
            'ear2': [(1068, 280), (1072, 296), (1092, 314), (1090, 346), (1080, 384)],
            'B': [(1080, 384), (1080, 392), (1054, 436), (1036, 478), (1010, 570), (1014, 668), (1006, 720)],
            'chin': [(1006, 720), (998, 746), (980, 768), (886, 862), (826, 910), (800, 924), (776, 930), (770, 942),
                     (724, 954), (658, 966), (600, 968)],
            'w': [(600, 620), (692, 614), (806, 594), (818, 582), (870, 562), (900, 574), (944, 602)],
            'h2': [(598, 744), (600, 756), (708, 750), (732, 744), (744, 736), (774, 734), (812, 722), (884, 686),
                   (948, 632), (958, 608), (1002, 596), (1008, 592), (1008, 584)],
            'v0': [(600, 620), (600, 968)],
            'v1': [(812, 588), (806, 594), (800, 624), (752, 708), (746, 734), (722, 746), (726, 776), (764, 896),
                   (768, 922), (774, 930), (770, 942)],
        }),
    'AXIOM W-2EG-HP': dict(ref='AXIOM-W-2EG-HP-S', family='AX', radius=0.4,
        centre=[(276, 273), (652, 327), (724, 359), (952, 546)],
        bars={
            'top': [(600, 276), (756, 276), (926, 268), (934, 264), (1058, 252), (1070, 238), (1088, 236)],
            'ear': [(1088, 236), (1102, 234), (1110, 240), (1110, 274), (1108, 300), (1092, 316), (1082, 380)],
            'ear2': [(1064, 258), (1070, 270), (1072, 298), (1092, 316), (1082, 380)],
            'B': [(1082, 380), (1048, 442), (1042, 464), (1016, 490), (996, 558), (994, 570), (1012, 588),
                  (1014, 620), (1012, 696), (1000, 744)],
            'chin': [(1000, 744), (930, 816), (830, 896), (784, 918), (764, 920), (760, 930), (684, 946), (600, 952)],
            'w': [(600, 652), (694, 648), (814, 628), (826, 618), (890, 590), (926, 598), (940, 606), (950, 600)],
            'h2': [(600, 724), (656, 724), (780, 708), (808, 690), (832, 688), (854, 680), (906, 650), (930, 630),
                   (938, 610), (962, 586), (994, 570), (1006, 582)],
            'v1': [(814, 632), (806, 690), (778, 710), (774, 736), (740, 798), (762, 928)],
            'eg1': [(904, 268), (930, 266), (938, 274), (948, 310), (1008, 404), (1012, 420), (1006, 468),
                    (1020, 484), (996, 566), (972, 582)],
        }),
}


def _knot_interp(knots, t):
    """Linear interpolation over [(t, value)] (sorted by t), clamped at the ends."""
    if t <= knots[0][0]:
        return knots[0][1]
    for (t0, a), (t1, b) in zip(knots, knots[1:]):
        if t <= t1:
            return a + (b - a) * (t - t0) / (t1 - t0) if t1 > t0 else b
    return knots[-1][1]


def _row_x(poly, py):
    """x of a polyline that runs down the photo (y increasing) at row py, clamped at its ends."""
    pts = sorted(poly, key=lambda p: p[1])
    return _knot_interp([(p[1], p[0]) for p in pts], py)


class ShellSurface:
    """Front-most z of a set of triangles over a 1 mm grid of (|x|, y) (rays along -z), for seating the masks. With
    `rim`, a point just inside an opening also takes the surface beside it (up to `rim` cm further out in x), so a bar
    near the face opening's edge stays in front of the edge; hits below `floor` (seen through the opening) count
    as no surface."""

    STEP, X0, X1, Y0, Y1 = 0.1, 0.0, 12.5, 24.0, 48.0

    def __init__(self, tris, floor=None, rim=0.0):
        nx = int(round((self.X1 - self.X0) / self.STEP)) + 1
        ny = int(round((self.Y1 - self.Y0) / self.STEP)) + 1
        gx = self.X0 + np.arange(nx) * self.STEP
        gy = self.Y0 + np.arange(ny) * self.STEP
        zmap = np.full((ny, nx), -np.inf)
        for a, b, c in tris:
            for sgn in (1.0, -1.0):                       # both sides of the head fold onto |x|
                ax, bx, cx = sgn * a[0], sgn * b[0], sgn * c[0]
                x_lo, x_hi = min(ax, bx, cx), max(ax, bx, cx)
                y_lo, y_hi = min(a[1], b[1], c[1]), max(a[1], b[1], c[1])
                if x_hi < self.X0 or x_lo > self.X1:
                    continue
                i0, i1 = max(0, int(np.floor((x_lo - self.X0) / self.STEP))), min(nx - 1, int(np.ceil((x_hi - self.X0) / self.STEP)))
                j0, j1 = max(0, int(np.floor((y_lo - self.Y0) / self.STEP))), min(ny - 1, int(np.ceil((y_hi - self.Y0) / self.STEP)))
                if i1 < i0 or j1 < j0:
                    continue
                X, Y = np.meshgrid(gx[i0:i1 + 1], gy[j0:j1 + 1])
                d = (bx - ax) * (c[1] - a[1]) - (cx - ax) * (b[1] - a[1])
                if abs(d) < 1e-12:
                    continue
                u = ((X - ax) * (c[1] - a[1]) - (cx - ax) * (Y - a[1])) / d
                v = ((bx - ax) * (Y - a[1]) - (X - ax) * (b[1] - a[1])) / d
                inside = (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
                z = a[2] + u * (b[2] - a[2]) + v * (c[2] - a[2])
                sub_ = zmap[j0:j1 + 1, i0:i1 + 1]
                np.maximum(sub_, np.where(inside, z, -np.inf), out=sub_)
        if floor is not None:
            zmap[zmap < floor] = -np.inf
        if rim > 0:
            w = int(round(rim / self.STEP))
            dil = zmap.copy()
            for k in range(1, w + 1):
                dil[:, :-k] = np.maximum(dil[:, :-k], zmap[:, k:])
            zmap = dil
        self.zmap = zmap

    def front_z(self, x, y):
        i = int(round((abs(x) - self.X0) / self.STEP)); j = int(round((y - self.Y0) / self.STEP))
        if not (0 <= i < self.zmap.shape[1] and 0 <= j < self.zmap.shape[0]):
            return None
        z = self.zmap[j, i]
        return None if not np.isfinite(z) else float(z)


class MaskPhotoFit:
    """One mask measured on its product photos, placed on the retail helmet C (hi frame, cm)."""

    def __init__(self, style, shell, face):
        m = MASK_PHOTO[style]
        ref, dx, dy = MASK_FRAME_REF.get(style, (style, 0, 0))
        r = MASK_PHOTO[ref]
        self.style, self.ref, self.radius, self.fam = style, ref, m["radius"], m["family"]
        self.frame_radius = MASK_FRAME_RADIUS
        # the frame's bars are the reference's; the style's own bars are shifted onto the reference photo
        self.bars = {role: [tuple(p) for p in poly] for role, poly in r["bars"].items() if role in MASK_FRAME_ROLES}
        self.bars.update({role: [(p[0] + dx, p[1] + dy) for p in poly] for role, poly in m["bars"].items()
                          if role not in MASK_FRAME_ROLES})
        self.frame_roles = [role for role in r["bars"] if role in MASK_FRAME_ROLES]
        self.fam_data = MASK_FAMILY[self.fam]
        self.s = PHOTO_SCALE[self.fam]
        top_role = "raised" if "raised" in self.bars else "top"
        self.py_top = min(self.bars[top_role], key=lambda p: abs(p[0] - PHOTO_CX))[1]
        # centre depth: the reference's knots on the frame's rows, the style's own on its bars' rows; the frame itself
        # is placed with the reference's knots only, so it is the same in every mask that shares it
        own_rows = {min(poly, key=lambda p: abs(p[0] - PHOTO_CX))[1] for role, poly in self.bars.items()
                    if role not in MASK_FRAME_ROLES}
        self.ref_centre = [(y, x) for y, x in r["centre"]]
        own = [(y + dy, x) for y, x in m["centre"] if any(abs(y + dy - q) < 4 for q in own_rows)]
        self.centre = sorted({(y, x) for y, x in self.ref_centre if not any(abs(y - q) < 4 for q in own_rows)}
                             | set(own))
        self.frame = self.bars["B"] + self.bars["chin"][1:]              # ear tip -> down -> chin centre (right half)
        self.shell, self.face = shell, face
        # solve the depth map on the reference: the top bar's centre clears the brow; the largest k that keeps the
        # upper frame (the temples) on or outside the shell (the binding row sits on it; the lower frame sits on
        # the jaw flaps' edge)
        y_t = self.y(self.py_top)
        side_t = _knot_interp(self.ref_centre, self.py_top)
        z_t = shell.front_z(0.0, y_t) + self.frame_radius + SEAT_GAP
        ks = []
        rows = [py for py, _side in self.fam_data["frame"]]
        mid = (min(rows) + max(rows)) / 2
        for py, side in self.fam_data["frame"]:
            zs = shell.front_z(abs(self.x(_row_x(self.frame, py))), self.y(py))
            if zs is not None and side > side_t and py <= mid:
                ks.append(((z_t - zs - self.frame_radius - 0.1) / ((side - side_t) * self.s), py))
        mh.require(ks, f"{style}: the frame never meets the shell")
        self.k, self.k_row = min(ks)
        self.z_front = z_t + self.k * (side_t - self.fam_data["front_x"]) * self.s
        mh.require(0.5 < self.k < 1.2, f"{style}: depth scale {self.k:.2f} out of range")

    def x(self, px):
        return (px - PHOTO_CX) * self.s

    def y(self, py):
        return PHOTO_TOP_Y[self.fam] - (py - self.py_top) * self.s

    def side(self, x, py, centre=None):
        """The point's x on the family's side photo (px): centre -> side bar A (SpeedFlex) -> frame."""
        dc = _knot_interp(self.centre if centre is None else centre, py)
        fx = abs(self.x(_row_x(self.frame, py)))
        fs = _knot_interp(self.fam_data["frame"], py)
        ax_ = abs(x)
        if "A" in self.fam_data and "A" in self.bars:
            axx = abs(self.x(_row_x(self.bars["A"], py)))
            as_ = _knot_interp(self.fam_data["A"], py)
            if ax_ <= axx:
                return dc + (as_ - dc) * (ax_ / axx) ** MASK_EASE
            t = min(1.0, max(0.0, (ax_ - axx) / max(fx - axx, 1e-6)))
            return as_ + (fs - as_) * t
        return dc + (fs - dc) * min(1.0, ax_ / max(fx, 1e-6)) ** MASK_EASE

    def point(self, px, py, mirror=False, frame=False):
        x, y = self.x(px), self.y(py)
        z = self.z_front - self.k * (self.side(x, py, self.ref_centre if frame else None) - self.fam_data["front_x"]) * self.s
        radius = self.frame_radius if frame else self.radius
        for surf, gap in ((self.shell, SEAT_GAP), (self.face, 0.3)):
            zs = surf.front_z(abs(x), y)
            if zs is not None and z < zs + radius + gap:
                z = zs + radius + gap
        return (-x if mirror else x, y, z)

    def clear(self, q):
        """A tube vertex kept in front of the shell and the face (the tube wraps a centreline that clears them; on the
        shell's steep sides its inner vertices can still dip in)."""
        z = q[2]
        for surf in (self.shell, self.face):
            zs = surf.front_z(q[0], q[1])
            if zs is not None and z < zs + 0.08:
                z = zs + 0.08
        return (q[0], q[1], z)

    def paths(self):
        """3D bar paths, the frame's first: (role, points, is_frame). Centre-crossing bars are one path across both
        halves, the others come twice (right, left)."""
        out = []
        def dense(poly, step_px=12):
            pts = []
            for (x0, y0), (x1, y1) in zip(poly, poly[1:]):
                n = max(1, int(math.hypot(x1 - x0, y1 - y0) // step_px))
                pts += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
            return pts + [poly[-1]]
        items = [("frame", self.frame, True)]
        items += [(role, self.bars[role], True) for role in self.frame_roles if role not in ("B", "chin")]
        items += [(role, poly, False) for role, poly in self.bars.items() if role not in MASK_FRAME_ROLES]
        for role, poly, is_frame in items:
            poly = dense([tuple(p) for p in poly])
            near = [abs(p[0] - PHOTO_CX) * self.s < 0.5 for p in poly]
            pt = lambda px, py, m=False: self.point(px, py, mirror=m, frame=is_frame)       # noqa: E731
            if all(near):                                               # a centre bar (tabs, the centre vertical)
                out.append((role, [pt(PHOTO_CX, py) for _px, py in poly], is_frame))
            elif near[0] or near[-1]:                                   # crosses the centre: one path, both halves
                if near[-1]:
                    poly = poly[::-1]
                right = [pt(px, py) for px, py in poly]
                left = [pt(px, py, True) for px, py in poly[::-1]]
                out.append((role, left[:-1] + [(0.0, right[0][1], right[0][2])] + right[1:], is_frame))
            else:
                out.append((role, [pt(px, py) for px, py in poly], is_frame))
                out.append((role, [pt(px, py, True) for px, py in poly], is_frame))
        return out


MASK_RIBBON_ROLES = ("A", "v0", "v1", "eg1", "tab", "tab2", "ear2")      # thin inner bars: flat, facing out
MASK_PATH_STEP, MASK_PATH_TURN, MASK_SMOOTH = 3.5, 14.0, 3        # the frame (the outline everyone sees)
MASK_INNER_STEP, MASK_INNER_TURN = 4.5, 18.0                         # the inner bars (hi_head's stored span is tight)


def smooth_path(pts, passes=MASK_SMOOTH):
    """(1, 2, 1) / 4 smoothing of a densely sampled path; the ends stay put (the traced skeleton's pixel steps)."""
    for _ in range(passes):
        pts = [pts[0]] + [tuple((pts[i - 1][k] + 2 * pts[i][k] + pts[i + 1][k]) / 4 for k in range(3))
                          for i in range(1, len(pts) - 1)] + [pts[-1]]
    return pts


def build_mask_photo(fit):
    pos, nrm, strips = [], [], []
    centre = (0.0, 36.5, 12.0)
    def out_dir(p):
        return norm(sub(p, centre))
    for role, path3, is_frame in fit.paths():
        step, turn = (MASK_PATH_STEP, MASK_PATH_TURN) if is_frame else (MASK_INNER_STEP, MASK_INNER_TURN)
        path = adaptive_path(None, smooth_path(path3), step, turn)
        radius = fit.frame_radius if is_frame else fit.radius
        if role in MASK_RIBBON_ROLES:
            v, n, s_ = ribbon(path, 2.0 * radius * 1.15, out_dir)
        else:
            v, n, s_ = tube3(path, radius, out_dir)
        base = len(pos)
        pos += [fit.clear(q) for q in v]; nrm += n
        strips += [[base + i for i in st] for st in s_]
    strip = join_strips(strips, pos, lambda k: nrm[k])
    return dict(pos=pos, nrm=nrm, strip=strip, tris=strip_tris(strip))


class LoMaskPlate:
    """The distance model's facemask plate (LO_FACEMASK_C in lo_body, moved into the hi frame) and its texture
    coordinates: a mask drawn onto the plate's texture along rays from `centre` lands where the 3D bars are."""

    def __init__(self, lo, centre=(0.0, 36.5, 12.0)):
        sub_ = lo.by_material("LO_FACEMASK_C")[0]
        to_hi = lambda p: (p[0], p[1] - LO_OFFSET[1], p[2] - LO_OFFSET[2])        # noqa: E731
        self.tris = [(tuple(to_hi(lo.pos[a]) for a in t), tuple(lo.uv[a] for a in t)) for t in sub_["tris"]]
        self.centre = centre

    def uv(self, p):
        d = norm(sub(p, self.centre))
        best = None
        for (a, b, c), (ua, ub, uc) in self.tris:
            e1, e2 = sub(b, a), sub(c, a)
            h = cross(d, e2); det = dot(e1, h)
            if abs(det) < 1e-12:
                continue
            f = 1.0 / det; s_ = sub(self.centre, a); u = f * dot(s_, h)
            q = cross(s_, e1); v = f * dot(d, q)
            t = f * dot(e2, q)
            # the nearest face, clamping barycentrics a little so points just past an edge keep a coordinate
            if t <= 0 or u < -0.25 or v < -0.25 or u + v > 1.25:
                continue
            err = max(0.0, -u) + max(0.0, -v) + max(0.0, u + v - 1.0)
            if best is None or err < best[0]:
                w = (1.0 - u - v, u, v)
                best = (err, tuple(ua[k] * w[0] + ub[k] * w[1] + uc[k] * w[2] for k in range(2)))
        return None if best is None else best[1]


def draw_mask_photo(fit, plate):
    """The low-LOD mask texture (64 x 64 alpha, the right half; the plate mirrors it): the fitted 3D bars of the
    right half are carried onto the distance plate's texture along rays from its centre."""
    img = Image.new("L", (SIZE * SS, SIZE * SS), 0)
    d = ImageDraw.Draw(img)
    for role, path3, is_frame in fit.paths():
        radius = fit.frame_radius if is_frame else fit.radius
        width = max(2, int(round(2.0 * radius * 3.0 * SS * 1.15)))
        pts = []
        for p in path3:
            if p[0] < -0.05:                        # the left half is the right half mirrored on the plate
                continue
            uv = plate.uv(p)
            if uv is not None:
                pts.append((min(0.999, max(0.0, uv[0])) * SIZE * SS, min(0.999, max(0.0, uv[1])) * SIZE * SS))
        if len(pts) >= 2:
            d.line(pts, fill=255, width=width, joint="curve")
            for x, y in (pts[0], pts[-1]):
                r = width / 2
                d.ellipse((x - r, y - r, x + r, y + r), fill=255)
    small = img.resize((SIZE, SIZE), Image.BOX)
    return bytes(min(255, (a + 4) // 8 * 8) for a in small.tobytes())     # 32 alpha levels


def mask_surfaces(hi):
    """The retail helmet C shell (its front surface, the face opening's edge carried 1.5 cm inward) and the face."""
    shell = ShellSurface([tuple(tuple(hi.pos[v]) for v in t) for t in hi.by_material("HI_HELMET_C")[0]["tris"]],
                         floor=8.0, rim=1.5)
    face_tris = []
    for name in ("SKIN_face", "SKIN_skull"):
        for sub_ in hi.by_material(name):
            face_tris += [tuple(tuple(hi.pos[v]) for v in t) for t in sub_["tris"]]
    return shell, ShellSurface(face_tris)


def build_revolution():
    """The Revolution mode's document: the retail helmet C with the modern details, and the 15 modern masks fitted to
    their product photos and seated on it (the shell, visor, decals, accessories and the whole distance scene stay
    retail; the distance plate draws each mask from its texture, baked from the 3D bars), and the historic fix."""
    hi = Scene("o3c115"); lo = Scene("o3c113")
    lay_hi = mh.parse_layout("o3c115", hi.decoded); lay_lo = mh.parse_layout("o3c113", lo.decoded)
    shell_surf, face_surf = mask_surfaces(hi)
    fits = [MaskPhotoFit(mk["name"], shell_surf, face_surf) for mk in MASKS15]
    parts = {}
    for i, mk in enumerate(MASKS15):
        slot = 12 + i
        mm = build_mask_photo(fits[i])
        name = f"FACEMASK{slot:02d}"
        parts[name] = encode_part(lay_hi, mm["pos"], mm["nrm"], [(0.059, 0.504)] * len(mm["pos"]),
                                  head_selector(hi, lay_hi, name, 2), mm["strip"])
        parts[name]["style"] = mk["name"]; parts[name]["positions"] = mk["positions"]
    detail, detail_verts = build_shell_details(hi, lay_hi)
    doc = {"schema": mh.GEOMETRY_SCHEMA,
           "design": "Revolution: the retail helmet C shell with modern surface details and 15 modern Riddell masks",
           "mode": "revolution",
           "resources": {"o3c115": {"shape": shape_entry(lay_hi), "parts": parts, "sphere": None, "shell_detail": detail},
                         "o3c113": {"shape": shape_entry(lay_lo), "parts": {}, "sphere": None}}}
    plate = LoMaskPlate(lo)
    doc["mask_alpha"] = {str(12 + i): base64.b64encode(draw_mask_photo(fits[i], plate)).decode()
                         for i in range(len(MASKS15))}
    doc["historic_edits"], nearest = historic_equipment_edits(hi)
    doc["historic_mask_map"] = {str(k): v for k, v in nearest.items()}
    doc["mask_fit"] = {f.style: {"k": round(f.k, 4), "z_front": round(f.z_front, 3), "k_row": f.k_row} for f in fits}
    doc["report"] = {"masks": {"verts": sum(len(base64.b64decode(p["records"])) // 16 for p in parts.values())},
                     "shell_detail": {"verts": detail_verts}}
    return doc, {}


def build():
    hi = Scene("o3c115"); lo = Scene("o3c113")
    lay_hi = mh.parse_layout("o3c115", hi.decoded); lay_lo = mh.parse_layout("o3c113", lo.decoded)
    cap_hi = cap_interior_triangles(cap_triangles(mh.guardian_lanes("o3c115", hi.decoded)))
    # lo cap in the hi frame
    lo_cap_dec = mh.guardian_lanes("o3c113", lo.decoded)
    lo_lay = mh.parse_layout("o3c113", lo_cap_dec)
    lo_pos = mh._positions(lo_lay, lo_cap_dec)
    lo_b = lo.by_material("HI_HELMET_B")[0]
    cap_lo = cap_interior_triangles([tuple(sub(lo_pos[v], LO_OFFSET) for v in t) for t in lo_b["tris"]])
    doc = {"schema": mh.GEOMETRY_SCHEMA, "design": "Option A: SpeedFlex in slot C, masks 12-26 modern Riddell",
           "resources": {}}
    report = {}
    # ---------------------------------------------------------------- hi
    parts = {}
    m = shell(hi, cap_hi, 18, 5, 9)
    pos, uv, strip = list(m["pos"]), list(m["uv"]), list(m["strip"])
    rfn = m["radius_fn"]
    # the rear bumper plate (low centre back, the retail rear bumper UV rect: the team name); no front plate (9/25:
    # the white forehead box read as glued on; the real SpeedFlex has the flex panel there)
    rp, ru, rs = plate(rfn, (0.0, 35.7, -2.0), 4.6, 1.2, (0.747, 0.99, 0.251, 0.307), 3, 0.18)
    xp, xu, xs = flex_notch(rfn)
    strips = [strip]
    for pp, uu, ss in ((rp, ru, rs), (xp, xu, xs)):
        base = len(pos); pos += pp; uv += uu; strips.append([base + i for i in ss])
    strip = join_strips(strips, pos, lambda k: sub(pos[k], C))
    tris = strip_tris(strip)
    nrm = list(m["nrm"]) + vertex_normals(pos, tris)[len(m["nrm"]):]
    sel = head_selector(hi, lay_hi, "HI_HELMET_C", HEAD_JOINT["o3c115"])
    parts["HI_HELMET_C"] = encode_part(lay_hi, pos, nrm, uv, sel, strip)
    report["hi_shell"] = {"verts": len(pos), "words": len(mh.encode_strip(strip))}
    shell_hi = {"pos": pos, "uv": uv, "tris": tris}
    # decals: NFL shield (x < 0 side) and flag (x > 0 side), rear upper sides (u7: the 2026 helmet is swapped vs retail)
    np_, nu, ns_ = plate(rfn, (-6.9, 41.2, -2.6), 0.95, 1.55, (0.723, 0.854, 0.663, 0.831), 2, 0.12)
    gp, gu, gs = plate(rfn, (7.4, 41.0, -2.2), 1.4, 0.9, (0.395, 0.54, 0.423, 0.576), 2, 0.12)
    # the retail flag quad is a rotated parallelogram in UV; use its four corners
    gu = [(0.471, 0.423), (0.543, 0.48), (0.395, 0.52), (0.467, 0.576)]
    lp, lu = np_ + gp, nu + gu
    ls = join_strips([ns_, [4 + i for i in gs]], lp, lambda k: sub(lp[k], C))
    ltris = strip_tris(ls)
    lnrm = vertex_normals(lp, ltris)
    parts["LOGO_helmet_C"] = encode_part(lay_hi, lp, lnrm, lu, head_selector(hi, lay_hi, "LOGO_helmet_C", 2), ls)
    report["hi_logos"] = {"verts": len(lp), "words": len(mh.encode_strip(ls))}
    # visor
    env = seated_envelope_speedflex(speedflex_design())
    doc["envelope"] = {"centre": env.centre, "edge": env.edge, "clips": env.clips}
    vp, vs = visor(env, 5, 4, 1.0)
    vtris = strip_tris(vs)
    vnrm = [norm(sub(p, (0.0, 38.0, 8.0))) for p in vp]
    parts["HI_faceshield_C"] = encode_part(lay_hi, vp, vnrm, [(0.9, 0.69)] * len(vp),
                                           head_selector(hi, lay_hi, "HI_faceshield_C", 2), vs)
    report["hi_visor"] = {"verts": len(vp), "words": len(mh.encode_strip(vs))}
    # masks
    mask_meshes = {}
    for i, mk in enumerate(MASKS15):
        slot = 12 + i
        mm = build_mask_v2(env, mk["elements"], mk["radius"])
        name = f"FACEMASK{slot:02d}"
        parts[name] = encode_part(lay_hi, mm["pos"], mm["nrm"], [(0.059, 0.504)] * len(mm["pos"]),
                                  head_selector(hi, lay_hi, name, 2), mm["strip"])
        parts[name]["style"] = mk["name"]; parts[name]["positions"] = mk["positions"]
        mask_meshes[slot] = mm
    acc, report["hi_accessories_moved"] = accessory_positions(hi, lay_hi, "o3c115")
    doc["resources"]["o3c115"] = {"accessory_positions": base64.b64encode(acc).decode(),
                                  "shape": {"vertex_count": lay_hi.vertex_count, "scale": lay_hi.lanes.scale,
                                            "offset": list(lay_hi.lanes.offset),
                                            "uv": [*lay_hi.lanes.uv_scale, *lay_hi.lanes.uv_offset]},
                                  "parts": parts, "sphere": None}
    # ---------------------------------------------------------------- lo (built in the hi frame, shifted)
    lof = FrameScene(lo, LO_OFFSET)
    ml = shell(lof, cap_lo, 9, 3, 4)       # 10 rows no longer fit the stored span (135,838 of 135,808 B)
    # the coarse distance shell takes its texture coordinates from the close-up shell's (patch by patch, nearest
    # point): a direct transfer at this density folds the logos
    ml["uv"] = uvs_from_shell(ml, m)
    ml["uv"], _fixed = sanitize_uvs(ml["uv"], ml["tris"], allowed_uv_mask(), allowed_uv_mask(extra=ART_EARS))
    lpos = [add(p, LO_OFFSET) for p in ml["pos"]]
    ltris = ml["tris"]
    lt, lb = tangents(ml["pos"], ml["uv"], ltris, ml["nrm"])
    lparts = {}
    lparts["HI_HELMET_C"] = encode_part(lay_lo, lpos, ml["nrm"], ml["uv"], head_selector(lo, lay_lo, "HI_HELMET_C", 12),
                                        ml["strip"], lt, lb)
    report["lo_shell"] = {"verts": len(lpos), "words": len(mh.encode_strip(ml["strip"]))}
    vp, vs = visor(env, 4, 2, 1.0, LO_OFFSET)
    vtris = strip_tris(vs)
    vnrm = [norm(sub(p, add((0.0, 38.0, 8.0), LO_OFFSET))) for p in vp]
    vuv = [(0.89, 0.69)] * len(vp)
    vt, vb = tangents(vp, vuv, vtris, vnrm)
    lparts["HI_faceshield_C"] = encode_part(lay_lo, vp, vnrm, vuv, head_selector(lo, lay_lo, "HI_faceshield_C", 12), vs, vt, vb)
    # LO_FACEMASK_C: 5 columns (u -1 -0.5 0 0.5 1) x 4 rows (v 0 .33 .66 1) = 20 > 19 -> drop one: use 4 rows of
    # (0, +-0.55, +-1) = 5 each = 20; the budget is 19, so the bottom row uses 3 points (0, +-0.8)
    rows = [(0.0, (0.0, 0.55, 1.0)), (0.34, (0.0, 0.55, 1.0)), (0.68, (0.0, 0.55, 1.0)), (1.0, (0.0, 0.8))]
    fpos, fuv, grid = [], [], []
    for v, us in rows:
        row = {}
        for u in us:
            for s in ((1,) if u == 0.0 else (1, -1)):
                p = env(s * u, v)
                row[s * u] = len(fpos)
                fpos.append(add(p, LO_OFFSET))
                fuv.append((0.007 + 0.72 * u, 0.02 + 0.96 * v))
        grid.append(row)
    def rowlist(row):
        return [row[k] for k in sorted(row)]
    strips = []
    for r in range(len(grid) - 1):
        a, b = rowlist(grid[r]), rowlist(grid[r + 1])
        if len(a) == len(b):          # rows run top to bottom; this pair order faces away from the head
            s_ = []
            for k in range(len(a)):
                s_ += [a[k], b[k]]
            strips.append(s_)
        else:   # 5 -> 3: the last two top points share the bottom corner
            s_ = [a[0], b[0], a[1], b[1], a[2], b[2], a[3], a[4]]
            strips.append(s_)
    fs = join_strips(strips, fpos, lambda k: sub(fpos[k], add((0.0, 36.0, 10.0), LO_OFFSET)))
    ftris = strip_tris(fs)
    fnrm = [norm(sub(p, add((0.0, 36.0, 10.0), LO_OFFSET))) for p in fpos]
    ft, fb = tangents(fpos, fuv, ftris, fnrm)
    lparts["LO_FACEMASK_C"] = encode_part(lay_lo, fpos, fnrm, fuv, head_selector(lo, lay_lo, "LO_FACEMASK_C", 12), fs, ft, fb)
    report["lo_mask"] = {"verts": len(fpos), "words": len(mh.encode_strip(fs))}
    acc, report["lo_accessories_moved"] = accessory_positions(lo, lay_lo, "o3c113", LO_OFFSET)
    doc["resources"]["o3c113"] = {"accessory_positions": base64.b64encode(acc).decode(),
                                  "shape": {"vertex_count": lay_lo.vertex_count, "scale": lay_lo.lanes.scale,
                                            "offset": list(lay_lo.lanes.offset),
                                            "uv": [*lay_lo.lanes.uv_scale, *lay_lo.lanes.uv_offset]},
                                  "parts": lparts, "sphere": None}
    doc["mask_alpha"] = {str(12 + i): base64.b64encode(draw_mask(m)).decode() for i, m in enumerate(MASKS15)}
    doc["historic_edits"], nearest = historic_equipment_edits(hi)
    doc["historic_mask_map"] = {str(k): v for k, v in nearest.items()}
    report["historic"] = {"files": len(doc["historic_edits"]), "helmet": sum(1 for r in doc["historic_edits"].values() for e in r if e[1] == "helmet"), "face_mask": sum(1 for r in doc["historic_edits"].values() for e in r if e[1] == "face_mask")}
    doc["report"] = report
    return doc, dict(shell_hi=shell_hi, masks=mask_meshes, lo_mask=dict(pos=fpos, uv=fuv, tris=ftris))

    return doc



# ====================================================================================================
# mask_textures
# ====================================================================================================

SIZE, SS = 64, 4
PX_PER_CM_U = 0.72 * SIZE / 10.0      # envelope half-width ~10 cm maps to u_tex 0..0.72


def uv_to_tex(u, v):
    return ((0.007 + 0.72 * abs(u)) * SIZE * SS, (0.02 + 0.96 * max(-0.02, v)) * SIZE * SS)


def element_uv_points(kind, p):
    out = []
    for q in p["pts"]:
        if isinstance(q[0], str):   # a clip connector: past the frame's edge
            out.append((1.12 * q[2], 0.0 if q[1] == "top" else 0.84))
        elif len(q) == 3:           # a raw 3D point: past the frame edge at the top
            out.append((1.12, 0.0))
        else:
            out.append(q)
    return out


def draw_mask(mask):
    img = Image.new("L", (SIZE * SS, SIZE * SS), 0)
    d = ImageDraw.Draw(img)
    for kind, p in mask["elements"]:
        pts = element_uv_points(kind, p)
        # densify in uv for smooth curves
        dense = []
        for a, b in zip(pts, pts[1:]):
            for k in range(8):
                t = k / 8
                dense.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        dense.append(pts[-1])
        width_cm = 2.0 * mask["radius"] * p.get("scale", 1.0) * (1.25 if kind == "ribbon" else 1.0)
        width = max(2, int(round(width_cm * PX_PER_CM_U * SS * 1.05)))
        for side in (1.0, -1.0):
            poly = [uv_to_tex(side * u, v) for u, v in dense]
            d.line(poly, fill=255, width=width, joint="curve")
            for x, y in (poly[0], poly[-1]):
                r = width / 2
                d.ellipse((x - r, y - r, x + r, y + r), fill=255)
    small = img.resize((SIZE, SIZE), Image.BOX)
    return bytes(min(255, (a + 4) // 8 * 8) for a in small.tobytes())     # 32 alpha levels


def refit_report(doc):
    """Author both scenes from the retail disc and refit them into their retail stored spans (the product's path):
    the stored size used and the headroom. Raises when a scene does not fit."""
    fill = models._tools_module("nfl_vc_lz_fill")
    src = source()
    out = {}
    for key in mh.KEYS:
        _r, decoded, _s = src.parse(key)
        authored, _receipt = mh.author(key, decoded, doc)
        span = src.span(src.resource(key))
        rebuilt, info = fill.rebuild_fixed_span_filled(span, authored, encoder="auto")
        mh.require(len(rebuilt) == len(span), f"{key}: the refit changed the span size")
        out[key] = {"stored_span": len(span) - 32, "compressed": info.compressed_bytes,
                    "headroom": info.stored_size - info.compressed_bytes}
    return out


def release_safe(value, width: int = 76):
    """The 2K5 release check refuses any whitespace-free run over 4,096 characters in a shipped text file
    (packaging/check_2k5_mod_studio_release.py), and geometry.json ships. Long base64 strings get a space every
    ``width`` characters, which base64.b64decode (the module's reader) discards, so the decoded geometry is unchanged;
    main() also writes the JSON with spaces after its separators."""
    if isinstance(value, dict):
        return {key: release_safe(item, width) for key, item in value.items()}
    if isinstance(value, list):
        return [release_safe(item, width) for item in value]
    if (isinstance(value, str) and len(value) > width
            and value.rstrip("=").isascii() and all(c.isalnum() or c in "+/" for c in value.rstrip("="))):
        return " ".join(value[i:i + width] for i in range(0, len(value), width))
    return value


def main(argv=None):
    global PACK0, INVENTORY
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", type=Path, required=True, help="pack 0 of the retail vc_53450030 archive")
    parser.add_argument("--inventory", type=Path, required=True, help="nfl2k5_resource_chunks_v2.json")
    parser.add_argument("--mode", choices=mh.MODES, default="revolution")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    PACK0, INVENTORY = args.index, args.inventory
    args.out = mh.mode_paths(args.mode)[0] if args.out is None else args.out
    doc, _previews = build() if args.mode == "speedflex" else build_revolution()
    fit = refit_report(doc)
    doc["report"]["stored"] = fit
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(release_safe(doc), sort_keys=True, separators=(", ", ": ")) + "\n", encoding="utf-8",
                        newline="\n")
    print("MODERN_HELMETS_GEOMETRY_OK", json.dumps(doc["report"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
