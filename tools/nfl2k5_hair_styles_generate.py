#!/usr/bin/env python3
"""Generate the hair style geometry and art (b775 job hs1) from the player body set. Offline authoring tool.

Reads outer 3 of a retail or SOFTDRINK disc (or an extracted copy) and writes ``data/nfl2k5_hair_styles/geometry.json``
plus the nine 64 x 64 hair textures in ``data/nfl2k5_hair_styles/art/``. Nothing here runs during a build. No Blender
and no photo pixels: every vertex is placed by measuring the scalp (hi_head SKIN_skull/neck/face), both Riddell shells
(HI_HELMET_A and C, in each scene) and the jersey and shoulder pads (hi_body and lo_body UNIF_jersey); every texture is
drawn procedurally here.

Head frame: cm, Y up, -Z is the back of the head; the helmet shells' axis is x = 0, z = 9. lo_body (and hi_body) use the
body frame = head frame + (0, 33.9, -4.6) (the thorax joint).

DESIGN (sources: hs1 research, ESPN 2026 roster headshots per player; see .b77-scratch/hs1/research):
* long_locs: twelve locks (seven at distance) start on the back of the skull inside the shell, leave the helmet at
  its back rim and fall over the collar down the upper back; side locks slide behind the shoulder pads instead of
  lying out along them (a greedy drape on the jersey's outside envelope, 0.8 cm steps);
* short_twists: thirteen short two-strand twists poking out under the back rim onto the collar (Cam Ward 2025-26);
* long_flow: one continuous sheet from the crown down the back of the skull, out under the rim and over the collar to
  the upper back (Trevor Lawrence, George Kittle, T.J. Hockenson);
* afro_puff: a sheet hugging the skull inside the shell that bulges out under the rim all round the back;
* braids: ten thin box braids falling to the upper back;
* bun: a short cap and a low knot under the back rim;
* mullet: short sides, a sheet at the nape falling over the collar.

Usage::

    nfl2k5_hair_styles_generate.py --outer3 OUTER3.bin | --disc XISO  [--out data/nfl2k5_hair_styles]
    nfl2k5_hair_styles_generate.py --tops --disc RETAIL.xiso           (b778 hr4: the hair tops only)
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from mod_editor.core import nfl2k5_models as models  # noqa: E402
from mod_editor.core import nfl2k5_hair_styles as hair  # noqa: E402

# ------------------------------------------------------------------------------------------------ scenes

def parse(key, decoded):
    inventory = models._tools_module("nfl_scne_inventory")
    probe = models._tools_module("nfl_scene_probe")
    outer, chunk = models.parse_model_key(key)
    record = probe.ResourceRecord(outer, "resource-bytes", 0, chunk, 0, "SCNE", 0, len(decoded), 0, 0xFEEDBEEF, 0,
                                  source="resource-bytes")
    return inventory.parse_scene(outer * 100_000 + chunk, record, bytes(decoded), {})[0]


class Scene:
    def __init__(self, key, decoded):
        self.key = key; self.d = bytes(decoded)
        self.p = parse(key, self.d); self.shape = self.p['shapes'][0]
        self.lanes = models._shape_lanes(self.p, self.shape, self.d)
        self.n = self.shape['vertex_count']
        self.pos = np.array(models.read_positions(self.d, self.shape, self.lanes))
        self.streams = {int(s['stream_index']): (int(s['offset']), int(s['stride'])) for s in self.shape['vertex_streams']}
        self.gltf = models._tools_module('nfl_scne_gltf')
        sel_stream, sel_off, sel_stride = self.lanes.selector
        base = self.streams[sel_stream][0]
        self.sel = np.array([struct.unpack_from('<h', self.d, base + v * sel_stride + sel_off)[0] for v in range(self.n)])
        uvl = self.lanes.texcoord
        base = self.streams[uvl[0]][0]
        raw = [struct.unpack_from('<hh', self.d, base + v * uvl[2] + uvl[1]) for v in range(self.n)]
        self.uv = np.array([models.uv_to_gltf(u, v, self.lanes.uv_scale, self.lanes.uv_offset) for u, v in raw])
        self.subs = self.p['submeshes']
    def tris(self, names):
        out = []
        for s in self.subs:
            if s['material_name'] not in names: continue
            for mode, batch in self.gltf.decode_batches(self.d, s['command_offset'], s['word_count']):
                if mode == 6:
                    for k in range(len(batch) - 2):
                        t = batch[k:k + 3]
                        if len(set(t)) == 3: out.append(t if k % 2 == 0 else (t[1], t[0], t[2]))
                elif mode == 5:
                    out += [tuple(batch[k:k + 3]) for k in range(0, len(batch) - 2, 3)]
                else:
                    raise ValueError(f'mode {mode}')
        return np.array(out, dtype=int).reshape(-1, 3)
    def names(self):
        return sorted({s['material_name'] for s in self.subs})

class Rig:
    """hi_head (115), hi_body (114) and lo_body (113) decoded from outer 3."""

    def __init__(self, outer3: bytes):
        tx = models._tools_module("nfl_txtr")
        chunks = tx.parse_chunks(bytes(outer3), allow_trailing=True)

        def decoded(index):
            c = chunks[index]
            span = bytes(outer3[c.offset:c.offset + 32 + c.stored_size])
            return tx.decode_chunk(span, tx.parse_chunks(span)[0])[0]
        self.hi = Scene("o3c115", decoded(115))
        self.body = Scene("o3c114", decoded(114))
        self.lo = Scene("o3c113", decoded(113))


# ------------------------------------------------------------------------------------------------ surfaces

AXIS_Z = 9.0
BODY_FROM_HEAD = np.array([0.0, 33.9, -4.6])

def tri_samples(sc, names, steps=6, offset=0.0):
    t = sc.tris(names)
    if len(t) == 0:
        return np.zeros((0, 3))
    P = sc.pos[t] + offset
    out = []
    for i in range(steps + 1):
        for j in range(steps + 1 - i):
            a, b = i / steps, j / steps
            out.append(P[:, 0] * (1 - a - b) + P[:, 1] * a + P[:, 2] * b)
    return np.concatenate(out)

def polar(p):
    az = np.degrees(np.arctan2(p[:, 0], -(p[:, 2] - AXIS_Z)))
    r = np.hypot(p[:, 0], p[:, 2] - AXIS_Z)
    return az, r, p[:, 1]

def angdiff(a, b):
    return np.abs(((a - b + 180) % 360) - 180)

class Surfaces:
    def __init__(self, head, body_list):
        """head: hi_head Scene (head frame); body_list: Scenes in the body frame (hi_body, lo_body) for the jersey."""
        self.body = polar(tri_samples(head, ['SKIN_neck', 'SKIN_skull', 'SKIN_face']))
        self.shells = [polar(tri_samples(head, [n])) for n in ('HI_HELMET_A', 'HI_HELMET_C')]
        jer = np.concatenate([tri_samples(b, ['UNIF_jersey'], offset=-BODY_FROM_HEAD) for b in body_list])
        self.jersey = polar(jer)
        self.jersey_pts = jer
    def _sel(self, pol, a, y, da, dy):
        az, r, h = pol
        return (angdiff(az, a) < da) & (np.abs(h - y) < dy)
    def body_radius(self, a, y, da=10.0, dy=1.5):
        m = self._sel(self.body, a, y, da, dy)
        return float(self.body[1][m].max()) if m.any() else 0.0
    def shell_inner(self, a, y, da=10.0, dy=1.5):
        best = math.inf
        for s in self.shells:
            m = self._sel(s, a, y, da, dy)
            if m.any(): best = min(best, float(s[1][m].min()))
        return best
    def rim(self, a, da=6.0):
        """lowest edge of either shell near azimuth a (above y=24)"""
        lo = math.inf
        for az, r, h in self.shells:
            m = (angdiff(az, a) < da) & (h > 24)
            if m.any(): lo = min(lo, float(h[m].min()))
        return lo
    def rim_radius(self, a, da=6.0):
        y = self.rim(a); best = math.inf
        for az, r, h in self.shells:
            m = (angdiff(az, a) < da) & (h < y + 1.2) & (h > 24)
            if m.any(): best = min(best, float(r[m].min()))
        return best
    def jersey_top(self, a, r0, da=5.0, dr=0.8):
        az, r, h = self.jersey
        m = (angdiff(az, a) < da) & (np.abs(r - r0) < dr)
        return float(h[m].max()) if m.any() else -math.inf
    def jersey_env(self, a, r):
        """The top of the jersey seen from outside: the highest jersey point at this radius or further out, so
        hair can never go down inside the neck opening; it has to come over the collar and the pads."""
        key = int(round(a))
        cache = self.__dict__.setdefault('_env', {})
        if key not in cache:
            grid = np.arange(0.0, 44.0, 0.25)
            tops = np.array([self.jersey_top(key, rr) for rr in grid])
            env = np.maximum.accumulate(tops[::-1])[::-1]
            cache[key] = (grid, env)
        grid, env = cache[key]
        i = int(np.clip(np.searchsorted(grid, r), 0, len(grid) - 1))
        return float(env[i])
    def jersey_radius(self, a, y, da=6.0, dy=1.2):
        az, r, h = self.jersey
        m = (angdiff(az, a) < da) & (np.abs(h - y) < dy)
        return float(r[m].max()) if m.any() else 0.0
    def clear_of_jersey(self, p, clearance):
        """True when point p (head frame) is outside the jersey by the clearance (radially, at its azimuth)."""
        az = math.degrees(math.atan2(p[0], -(p[2] - AXIS_Z))); r = math.hypot(p[0], p[2] - AXIS_Z)
        top = self.jersey_top(az, r)
        return p[1] > top + clearance

def point(a, r, y):
    aa = math.radians(a)
    return np.array([r * math.sin(aa), y, AXIS_Z - r * math.cos(aa)])


# ------------------------------------------------------------------------------------------------ meshes

ROOT_ABOVE_RIM = 2.4
SCALP_CLEAR = 0.45
SHELL_CLEAR = 0.5
JERSEY_CLEAR = 0.6

class Mesh:
    def __init__(self):
        self.P, self.N, self.UV, self.J = [], [], [], []
        self.strip = []
    def add(self, p, n, uv, joint):
        self.P.append(np.asarray(p, float)); self.N.append(np.asarray(n, float)); self.UV.append(uv); self.J.append(joint)
        return len(self.P) - 1
    def strip_append(self, idx):
        """Append a run of strip indices that must start on an even triangle parity."""
        if self.strip:
            last = self.strip[-1]
            join = [last, idx[0]]
            # keep the run starting at even parity (triangle index = position - 2)
            if (len(self.strip) + len(join)) % 2:
                join = [last, last, idx[0]]
            self.strip += join
        self.strip += list(idx)
    def arrays(self):
        return (np.array(self.P), np.array(self.N), np.array(self.UV, float), list(self.J), list(self.strip))
    def tris(self):
        s = self.strip; out = []
        for k in range(len(s) - 2):
            t = s[k:k + 3]
            if len(set(t)) == 3:
                out.append(t if k % 2 == 0 else [t[1], t[0], t[2]])
        return np.array(out, int).reshape(-1, 3)

def radial(p):
    v = np.array([p[0], 0.0, p[2] - AXIS_Z]); n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([0, 0, -1.0])

def tangent(a):
    aa = math.radians(a); return np.array([math.cos(aa), 0.0, math.sin(aa)])

# ------------------------------------------------------------------------------------------------ draping

def drape(S, a, r0, y0, length, steps, clear=JERSEY_CLEAR, lean=0.18, a_drift=0.0, max_r=None, sub=0.8):
    """A path of `steps` + 1 points (a, r, y) falling from (r0, y0), traced in `sub` cm steps: straight down (with a
    little outward lean) while clear of the jersey; on the collar or a pad it slides to the lowest neighbouring
    point, drifting behind the shoulder (towards a = 0) on flat pads, always `clear` cm above the jersey's outside
    envelope at its own azimuth. The trace is resampled by arc length."""
    trace = [(a, r0, y0)]
    az, r, y = a, r0, y0
    walked = 0.0
    while walked < length:
        r1, y1 = r + sub * lean, y - sub * math.sqrt(1 - lean * lean)
        if max_r is not None: r1 = min(r1, max_r)
        az1 = az + a_drift * sub / length
        if y1 >= S.jersey_env(az1, r1) + clear:
            nxt = (az1, r1, y1)
        else:
            sgn = 1 if az > 0 else -1
            cands = []
            p0 = point(az, r, y)
            for dA, dR in ((0, 1.0), (3, 0.0), (3, 0.6), (5, 0.0), (0, 0.6)):
                a2 = az - sgn * dA if abs(az) > dA else 0.0
                r2 = r + dR
                if max_r is not None and r2 > max_r: continue
                e = S.jersey_env(a2, r2)
                y2 = min(y, e + clear) if math.isfinite(e) else y - sub
                y2 = max(y2, e + clear) if math.isfinite(e) else y2
                if np.linalg.norm(point(a2, r2, y2) - p0) < 0.25:
                    continue
                la = S.jersey_env(a2, r2 + 3.0)
                look = min(y2, la + clear) if math.isfinite(la) else y2 - 3.0
                cands.append((round(y2 + look, 1) - 0.004 * dA + 0.004 * dR, a2, r2, y2))
            plain = [c for c in cands if c[1] == az]
            far = S.jersey_env(az, r + 6.0)
            descends = math.isfinite(far) and far + clear < y - 2.6
            pool = plain if (plain and descends) else cands
            pool.sort()
            _s, a2, r2, y2 = pool[0]
            nxt = (a2, r2, y2)
        d = float(np.linalg.norm(point(*[nxt[0], nxt[1], nxt[2]]) - point(az, r, y)))
        walked += max(d, 0.3)
        az, r, y = nxt
        trace.append(nxt)
    # resample by arc length into steps + 1 points
    P = np.array([point(*t) for t in trace]); seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)]); total = cum[-1] if cum[-1] > 0 else 1.0
    out = []
    for k in range(steps + 1):
        s_ = total * k / steps
        i = int(np.clip(np.searchsorted(cum, s_) - 1, 0, len(trace) - 2))
        f = 0.0 if seg[i] == 0 else (s_ - cum[i]) / seg[i]
        A = np.array(trace[i]); B = np.array(trace[i + 1])
        out.append(tuple(A + (B - A) * min(max(f, 0), 1)))
    return out


def root_and_rim(S, a, layer=0):
    rim = S.rim(a)
    rim_r = S.rim_radius(a)
    y_root = rim + ROOT_ABOVE_RIM
    shell = S.shell_inner(a, y_root) - SHELL_CLEAR
    scalp = S.body_radius(a, y_root)
    r_root = min((scalp if scalp > 0 else shell - 0.8) + SCALP_CLEAR + 0.25 * layer, shell)
    neck = S.body_radius(a, rim - 0.4)
    r_rim = min((neck if neck > 0 else rim_r - 1.5) + SCALP_CLEAR + 0.5 + 0.35 * layer, rim_r - 0.2)
    return (y_root, r_root), (rim - 0.5, r_rim)

# ------------------------------------------------------------------------------------------------ cards (locks)

def card(m, path_pts, widths, u0, u1, vs, joints, a_list):
    """A ribbon down the path (list of 3-D centre points), widths per row, uv columns u0..u1 and v per row."""
    rows = len(path_pts)
    ids = []
    for i in range(rows):
        c = path_pts[i]
        down = path_pts[min(i + 1, rows - 1)] - path_pts[max(i - 1, 0)]
        t = tangent(a_list[i])
        n = np.cross(t, down)
        if np.linalg.norm(n) < 1e-6: n = radial(c)
        if n @ radial(c) < 0: n = -n
        n /= np.linalg.norm(n)
        across = t - (t @ n) * n; across /= np.linalg.norm(across)
        half = widths[i] / 2
        L = m.add(c - half * across, n, (u0, vs[i]), joints[i])
        R = m.add(c + half * across, n, (u1, vs[i]), joints[i])
        ids += [L, R]
    m.strip_append(ids)

def lock(m, S, a, length, width, column, columns, *, layer=0, steps=3, taper=0.7, lean=0.18, drift=0.0,
         joints_by_row=None, v_rim=0.12, crown=None):
    (yr, rr), (ym, rm) = root_and_rim(S, a, layer)
    path = drape(S, a, rm, ym, length, steps, lean=lean, a_drift=drift)
    pts = [point(a, rr, yr)] + [point(az, r, y) for az, r, y in path]
    a_list = [a] + [az for az, _r, _y in path]
    if crown is not None:     # one extra row up the back of the skull, inside the shell (shows with the helmet off)
        ac = a * 0.75
        sc = S.body_radius(ac, crown); sh = S.shell_inner(ac, crown) - SHELL_CLEAR
        rc = min((sc if sc > 0 else rr) + SCALP_CLEAR + 0.15 * layer, sh if math.isfinite(sh) else 99)
        pts = [point(ac, rc, crown)] + pts; a_list = [ac] + a_list
        v_rim = 0.2
        if joints_by_row: joints_by_row = ['head'] + list(joints_by_row)
    n = len(pts)
    widths = [width] + [width * (1 - (1 - taper) * (k / (n - 2))) for k in range(n - 1)]
    if crown is not None:
        widths = [width * 0.8] + widths[:-1]
        vs = [0.0, 0.1] + [v_rim + (1 - v_rim) * k / (n - 3) for k in range(n - 2)]
    else:
        vs = [0.0] + [v_rim + (1 - v_rim) * k / (n - 2) for k in range(n - 1)]
    joints = joints_by_row or (['head', 'head'] + ['neck'] * (n - 3) + ['thorax'] if n > 3 else ['head', 'head', 'neck'])
    joints = joints[:n] + [joints[-1]] * (n - len(joints))
    pad = 0.06 / columns
    card(m, pts, widths, column / columns + pad, (column + 1) / columns - pad, vs, joints, a_list)

def joints_for(path_len_rows, long=False):
    if path_len_rows <= 3:
        return ['head', 'head', 'neck']
    out = ['head', 'head', 'neck']
    out += ['thorax' if long else 'neck'] * (path_len_rows - 3)
    return out

# ------------------------------------------------------------------------------------------------ curtains

def curtain(m, S, azimuths, length, steps, *, crown=None, v_top=0.0, lean=0.2, bulge=0.0, joints=None,
            width_taper=1.0, layer=0, crown_taper=0.3):
    """A continuous sheet: one column per azimuth; rows: [crown rows hugging the scalp] + root + rim + drape."""
    cols = []
    for j, a in enumerate(azimuths):
        (yr, rr), (ym, rm) = root_and_rim(S, a, layer)
        rows = []
        if crown:
            top = max(crown)
            for yc in crown:   # absolute heights, hugging the scalp inside the shell; narrower towards the crown
                ac = a * (1.0 - crown_taper * (yc - yr) / max(top - yr, 1e-6))
                sc = S.body_radius(ac, yc)
                sh = S.shell_inner(ac, yc) - SHELL_CLEAR
                r = min((sc if sc > 0 else rr) + SCALP_CLEAR + 0.2, sh if math.isfinite(sh) else 99)
                rows.append((ac, r, yc))
        rows.append((a, rr, yr))
        path = drape(S, a, rm + bulge, ym, length, steps, lean=lean)
        rows += path
        cols.append(rows)
    R = len(cols[0]); C = len(cols)
    ids = np.zeros((R, C), int)
    jl = joints or (['head'] * (R - steps) + ['neck'] + ['thorax'] * (steps - 1))
    for j in range(C):
        u = j / (C - 1)
        for i in range(R):
            az, r, y = cols[j][i]
            p = point(az, r, y)
            # normal: radial outward, tilted by the local slope
            v = v_top + (1 - v_top) * i / (R - 1)
            ids[i, j] = m.add(p, radial(p), (u, v), jl[min(i, len(jl) - 1)])
    # recompute normals from the grid
    P = np.array(m.P)
    for i in range(R):
        for j in range(C):
            du = P[ids[i, min(j + 1, C - 1)]] - P[ids[i, max(j - 1, 0)]]
            dv = P[ids[min(i + 1, R - 1), j]] - P[ids[max(i - 1, 0), j]]
            n = np.cross(du, dv)
            if n @ radial(P[ids[i, j]]) < 0: n = -n
            nn = np.linalg.norm(n)
            if nn > 1e-9: m.N[ids[i, j]] = n / nn
    # strips: one per column band, rows down; order (left col j, right col j+1) so the first triangle faces out
    for j in range(C - 1):
        run = []
        for i in range(R):
            run += [ids[i, j], ids[i, j + 1]]
        # orientation check on the first triangle
        a_, b_, c_ = (np.array(m.P[k]) for k in run[:3])
        if np.cross(b_ - a_, c_ - a_) @ radial((a_ + b_ + c_) / 3) < 0:
            run = []
            for i in range(R):
                run += [ids[i, j + 1], ids[i, j]]
        m.strip_append(run)
    return ids



MESHES = ('long_locs', 'short_twists', 'long_flow', 'afro_puff', 'braids', 'bun', 'mullet')

def surfaces(rig, lod):
    if lod == 'hi':
        return Surfaces(rig.hi, [rig.body])
    # distant: lo shells and jersey, hi scalp (lo has no skull)
    s = Surfaces(rig.hi, [rig.lo])
    s.shells = [polar(tri_samples(rig.lo, [n], offset=-BODY_FROM_HEAD)) for n in ('HI_HELMET_A', 'HI_HELMET_C')]
    return s

def build(name, S, lod):
    m = Mesh()
    hi = lod == 'hi'
    F = Fields(S)
    if name == 'long_locs':
        # twelve locks (seven at distance) out of the helmet's back half, falling straight down the back as one dense,
        # slightly gathered mass over the collar; alternate locks twisted a little so a side view sees rope, not wire
        n = 12 if hi else 7
        for i, a in enumerate(np.linspace(-62, 62, n)):
            side = abs(a) / 62
            strand(m, S, F, a, 23 - 5 * side + (1.2 if i % 2 else 0), (3.7 if hi else 5.4), i % 4, 4, layer=i % 2,
                   fractions=(0, 0.15, 0.35, 0.65, 1.0) if hi else (0, 0.3, 1.0), crown=(46.5 if hi else None),
                   back=1.2, centre=0.18 + 0.1 * side, lateral=0.08, twist=(0.35 if i % 2 else -0.35), clear=1.2)
    elif name == 'short_twists':
        n = 13 if hi else 8
        for i, a in enumerate(np.linspace(-70, 70, n)):
            length = 5.6 - 1.8 * (abs(a) / 70) ** 2
            lock(m, S, a, length, (2.8 if hi else 3.6), i % 4, 4, layer=i % 2, steps=1, lean=0.55, taper=0.85,
                 joints_by_row=['head', 'head', 'neck'], crown=(44.0 if hi else None))
    elif name == 'long_flow':
        az = np.linspace(-92, 92, 11 if hi else 7)
        curtain(m, S, az, 15.0, 3 if hi else 2, crown=[50.0, 45.0] if hi else [46.0], lean=0.06,
                joints=(['head'] * 4 + ['neck', 'thorax', 'thorax']) if hi else (['head'] * 3 + ['neck', 'thorax']))
    elif name == 'afro_puff':
        # a rounded volume over the skull (inside the shell under a helmet) and a full roll bulging out under the rim
        afro(m, S, F, hi)
    elif name == 'braids':
        # ten box braids in a neat row from the nape, hanging close down the back over the collar
        n = 10 if hi else 6
        for i, a in enumerate(np.linspace(-58, 58, n)):
            strand(m, S, F, a, 17 - 4 * (abs(a) / 58), (1.9 if hi else 2.8), i % 4, 4, layer=0,
                   fractions=(0, 0.25, 0.6, 1.0) if hi else (0, 0.35, 1.0), back=1.4, centre=0.25, taper=0.8,
                   twist=(0.5 if i % 2 else -0.5))
    elif name == 'bun':
        bun_mesh(m, S, hi)
    elif name == 'mullet':
        az = np.linspace(-85, 85, 9 if hi else 5)
        curtain(m, S, az, 12.0, 2 if hi else 1, crown=[46.0] if hi else None, lean=0.25,
                joints=['head', 'head', 'head', 'neck', 'thorax'] if hi else ['head', 'head', 'neck', 'thorax'])
    push_out(m, F)
    return m

def bun_mesh(m, S, hi):
    # a cap from the nape (inside the helmet) to the knot, then the knot: a squashed ball under the back rim
    curtain(m, S, np.linspace(-40, 40, 5 if hi else 3), 2.0, 1, crown=[48.0] if hi else None, lean=0.6,
            joints=['head'] * 6)
    rim = S.rim(0); rr = S.rim_radius(0)
    c = np.array([0.0, rim - 2.9, 9.0 - (rr + 0.1)])
    rx, ry, rz = 3.0, 2.4, 1.8
    nl, nv = (8, 5) if hi else (5, 3)
    ids = []
    for i in range(nv + 1):
        th = math.pi * i / nv
        row = []
        for j in range(nl + 1):
            ph = 2 * math.pi * j / nl
            d = np.array([math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph)])
            p = c + d * np.array([rx, ry, rz])
            row.append(m.add(p, d, (j / nl, i / nv), 'head'))
        ids.append(row)
    for i in range(nv):
        run = []
        for j in range(nl + 1):
            run += [ids[i][j], ids[i + 1][j]]
        a, b, cc = (m.P[k] for k in run[:3])
        if np.cross(b - a, cc - a) @ (a - c) < 0:
            run = []
            for j in range(nl + 1):
                run += [ids[i + 1][j], ids[i][j]]
        m.strip_append(run)

def all_meshes(rig):
    out = {}
    for lod in ('hi', 'lo'):
        S = surfaces(rig, lod)
        for name in MESHES:
            out[(name, lod)] = build(name, S, lod)
    return out


# ------------------------------------------------------------------------------------------------ gravity drape (v2)
# b775 hs1 v2 (coordinator review 10/17): strands and sheets fall under gravity onto the measured jersey and pads.
# H(x, z) is the top of the jersey seen from above and Z(x, y) its back seen from behind; a point is outside when it
# is above the one or behind the other (and off the neck). Locks are drawn behind the back, slide over the collar and
# pad tops, rows are picked where the path bends, chords are pushed out until they clear, and a last pass moves any
# triangle edge that still dips into the jersey.

RES = 0.5

class Fields:
    def __init__(self, S):
        P = S.jersey_pts
        self.S = S
        self.x0, self.y0, self.z0 = -40.0, -10.0, -40.0
        nx, ny, nz = 160, 120, 160
        H = np.full((nx, nz), -np.inf); Z = np.full((nx, ny), np.inf)
        ix = np.clip(((P[:, 0] - self.x0) / RES).astype(int), 0, nx - 1)
        iy = np.clip(((P[:, 1] - self.y0) / RES).astype(int), 0, ny - 1)
        iz = np.clip(((P[:, 2] - self.z0) / RES).astype(int), 0, nz - 1)
        np.maximum.at(H, (ix, iz), P[:, 1]); np.minimum.at(Z, (ix, iy), P[:, 2])
        # close gaps between samples (1 cell)
        Hd = H.copy(); Zd = Z.copy()
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                Hd = np.maximum(Hd, np.roll(np.roll(H, dx, 0), dz, 1))
                Zd = np.minimum(Zd, np.roll(np.roll(Z, dx, 0), dz, 1))
        self.H, self.Z = Hd, Zd
    def h(self, x, z):
        i = int((x - self.x0) / RES); k = int((z - self.z0) / RES)
        if 0 <= i < self.H.shape[0] and 0 <= k < self.H.shape[1]: return float(self.H[i, k])
        return -math.inf
    def zb(self, x, y):
        i = int((x - self.x0) / RES); k = int((y - self.y0) / RES)
        if 0 <= i < self.Z.shape[0] and 0 <= k < self.Z.shape[1]: return float(self.Z[i, k])
        return math.inf
    def neck_ok(self, p, clear=0.4):
        if p[1] < 24: return True
        a = math.degrees(math.atan2(p[0], -(p[2] - AXIS_Z))); r = math.hypot(p[0], p[2] - AXIS_Z)
        b = self.S.body_radius(a, p[1], da=8, dy=1.0)
        return r >= b + clear
    def outside(self, p, clear):
        x, y, z = p
        return (y > self.h(x, z) + clear or z < self.zb(x, y) - clear) and self.neck_ok(p)

def fall(F, start, length, *, clear=0.6, back=0.9, centre=0.12, sub=0.4, lateral=0.0):
    """Particle path from `start` (head frame) that falls under gravity, is drawn behind the back, and slides over
    the collar and pads; never inside the jersey fields."""
    p = np.array(start, float); out = [p.copy()]; walked = 0.0; t = 0
    while walked < length:
        t += 1
        x, y, z = p
        look = F.zb(x, y - 4.0)
        behind = math.isfinite(look) and z <= look - clear + 0.05
        d = np.array([0.0, -1.0, 0.0])
        if not behind:
            d[2] -= back
        if abs(x) > 0.5:
            d[0] -= centre * math.copysign(1.0, x) * min(1.0, abs(x) / 9.0)
        d[0] += lateral * math.sin(t * sub / 4.0)
        d /= np.linalg.norm(d)
        q = p + sub * d
        if not F.outside(q, clear):
            cands = []
            top = F.h(q[0], q[2])
            if math.isfinite(top) and top + clear <= p[1] + 0.35:
                cands.append(np.array([q[0], top + clear + 0.01, q[2]]))
            zb = F.zb(q[0], q[1])
            if math.isfinite(zb):
                cands.append(np.array([q[0], q[1], zb - clear - 0.01]))
            cands = [c for c in cands if F.outside(c, clear * 0.95)]
            if not cands:
                q = p + np.array([0, 0, -sub])         # step straight back
            else:
                q = min(cands, key=lambda c: np.linalg.norm(c - p))
        walked += float(np.linalg.norm(q - p)); p = q; out.append(p.copy())
        if t > 2000: break
    return np.array(out)

def resample(path, fractions):
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1); cum = np.concatenate([[0], np.cumsum(seg)])
    out = []
    for f in fractions:
        s = f * cum[-1]; i = int(np.clip(np.searchsorted(cum, s) - 1, 0, len(path) - 2))
        w = 0 if seg[i] == 0 else (s - cum[i]) / seg[i]
        out.append(path[i] + (path[i + 1] - path[i]) * w)
    return out

def simplify_safe(F, path, count, clear=0.2):
    """Like simplify, but first adds the path points where the current polyline passes inside the jersey."""
    keep = [0, len(path) - 1]
    while len(keep) < count:
        ks = sorted(keep); worst, where = 0.0, None
        for a, b in zip(ks[:-1], ks[1:]):
            if b - a < 2: continue
            A, B = path[a], path[b]
            for t in np.linspace(0.05, 0.95, 19):
                p = A + (B - A) * t
                if not F.outside(p, clear):
                    i = a + 1 + int(np.argmin(np.linalg.norm(path[a + 1:b] - p, axis=1)))
                    depth = 1.0
                    if depth > worst: worst, where = depth, i
                    break
            if where is not None: break
        if where is None:
            rest = simplify(path, count)
            # fall back to distance-based points not yet kept
            extra = [i for i in range(len(path)) if any((path[i] == r).all() for r in rest) and i not in keep]
            if not extra: break
            keep.append(extra[0]); continue
        keep.append(where)
    return [path[i] for i in sorted(set(keep))]

def clear_chords(F, rows, clear=0.25, step=0.25, rounds=40):
    """Push the rows after the first back (and up a little) until no chord between rows passes inside the jersey."""
    rows = [np.array(r, float) for r in rows]
    for _ in range(rounds):
        moved = False
        for k in range(len(rows) - 1):
            A, B = rows[k], rows[k + 1]
            if any(not F.outside(A + (B - A) * t, clear) for t in np.linspace(0.05, 1.0, 16)):
                for j in (k, k + 1):
                    if j == 0: continue
                    rows[j] = rows[j] + np.array([0.0, 0.08, -step])
                moved = True
        if not moved: break
    return rows

def simplify(path, count):
    """`count` points of the fine path (ends kept), added greedily where the polyline is farthest from the path."""
    keep = [0, len(path) - 1]
    while len(keep) < count:
        best, where = -1.0, None
        ks = sorted(keep)
        for a, b in zip(ks[:-1], ks[1:]):
            if b - a < 2: continue
            A, B = path[a], path[b]; AB = B - A; L = float(AB @ AB) or 1e-9
            for i in range(a + 1, b):
                t = np.clip((path[i] - A) @ AB / L, 0, 1)
                dist = np.linalg.norm(path[i] - (A + t * AB))
                if dist > best: best, where = dist, i
        if where is None: break
        keep.append(where)
    return [path[i] for i in sorted(keep)]

def chord_violations(F, pts, clear=0.3, n=12):
    bad = 0
    for a, b in zip(pts[:-1], pts[1:]):
        for t in np.linspace(0, 1, n):
            if not F.outside(a + (b - a) * t, clear): bad += 1
    return bad

def strand(m, S, F, a, length, width, column, columns, *, layer=0, fractions=(0, 0.2, 0.55, 1.0), crown=None,
           taper=0.75, back=0.9, centre=0.12, joints=None, lateral=0.0, clear=1.0, twist=0.0):
    (yr, rr), (ym, rm) = root_and_rim(S, a, layer)
    rim = point(a, rm, ym)
    path = fall(F, rim, length, back=back, centre=centre, lateral=lateral, clear=clear + 0.15 * layer)
    rows = clear_chords(F, simplify(path, len(fractions)))
    pts = [point(a, rr, yr)] + rows
    if crown is not None:
        ac = a * 0.75
        sc = S.body_radius(ac, crown); sh = S.shell_inner(ac, crown) - SHELL_CLEAR
        rc = min((sc if sc > 0 else rr) + SCALP_CLEAR + 0.15 * layer, sh if math.isfinite(sh) else 99)
        pts = [point(ac, rc, crown)] + pts
    n = len(pts)
    a_list = [math.degrees(math.atan2(p[0], -(p[2] - AXIS_Z))) for p in pts]
    widths = [width * (1 - (1 - taper) * k / (n - 1)) for k in range(n)]
    if crown is not None: widths[0] *= 0.8
    vs = list(np.linspace(0.0, 1.0, n)) if crown is None else [0.0] + list(np.linspace(0.12, 1.0, n - 1))
    js = joints or (['head'] * (n - len(fractions) + 1) + ['neck'] + ['thorax'] * (len(fractions) - 2))
    js = (js + [js[-1]] * n)[:n]
    pad = 0.06 / columns
    card2(m, pts, widths, column / columns + pad, (column + 1) / columns - pad, vs, js, a_list, twist=twist)
    return chord_violations(F, pts[(2 if crown is not None else 1):], clear=0.2)


def card2(m, pts, widths, u0, u1, vs, joints, a_list, twist=0.0):
    """A ribbon whose width stays across the strand: horizontal and perpendicular to the strand's own horizontal
    run where it travels sideways or backwards (so a strand crossing a pad is never seen edge-on as a wire)."""
    rows = len(pts); ids = []
    for i in range(rows):
        c = np.asarray(pts[i], float)
        d = np.asarray(pts[min(i + 1, rows - 1)], float) - np.asarray(pts[max(i - 1, 0)], float)
        t = tangent(a_list[i])
        dh = np.array([d[0], 0.0, d[2]])
        if np.linalg.norm(dh) > 0.35 * np.linalg.norm(d):
            across = np.cross(dh, [0.0, 1.0, 0.0]); across /= np.linalg.norm(across)
            if across @ t < 0: across = -across
            w = min(1.0, (np.linalg.norm(dh) / np.linalg.norm(d) - 0.35) / 0.35)
            across = (1 - w) * t + w * across; across /= np.linalg.norm(across)
        else:
            across = t
        n = np.cross(across, d) if np.linalg.norm(d) > 1e-6 else radial(c)
        if np.linalg.norm(n) < 1e-6: n = radial(c)
        if n @ radial(c) < 0: n = -n
        n /= np.linalg.norm(n)
        if twist:
            tw = twist * min(1.0, i / 2.0)          # the roots stay flat against the head
            across, n = math.cos(tw) * across + math.sin(tw) * n, math.cos(tw) * n - math.sin(tw) * across
            if n @ radial(c) < 0: n = -n
        half = widths[i] / 2
        L = m.add(c - half * across, n, (u0, vs[i]), joints[i])
        R = m.add(c + half * across, n, (u1, vs[i]), joints[i])
        ids += [L, R]
    # first triangle (L0, R0, L1) must face out
    a_, b_, c_ = (np.asarray(m.P[k]) for k in ids[:3])
    if np.cross(b_ - a_, c_ - a_) @ radial((a_ + b_ + c_) / 3) < 0:
        ids = [ids[k ^ 1] for k in range(len(ids))]
    m.strip_append(ids)


def afro(m, S, F, hi):
    """A rounded volume: a dome over the skull (inside the shell when the helmet is on) and a full roll that bulges out
    under the rim at the nape and round the ears, clamped above the collar and pads."""
    cols = 13 if hi else 7
    base = np.linspace(-1.0, 1.0, cols)
    centre = np.array([0.0, 41.0, AXIS_Z])
    # rows: (kind, value, azimuth span)
    rows = ([('crown', 54.0, 168), ('crown', 51.5, 158), ('crown', 48.0, 145), ('crown', 44.0, 130)] if hi else
            [('crown', 47.0, 140)])
    rows += [('root', 0.0, 118), ('roll', (-0.5, 1.7), 108), ('roll', (-2.0, 2.4), 100), ('roll', (-3.5, 1.6), 94),
             ('roll', (-4.6, 0.3), 90)] if hi else [('root', 0.0, 112), ('roll', (-1.6, 2.2), 100), ('roll', (-4.2, 0.6), 90)]
    grid = np.zeros((len(rows), cols), int)
    for j, f in enumerate(base):
        for i, (kind, val, span) in enumerate(rows):
            a = f * span
            if kind == 'crown':
                y = val
                sc = S.body_radius(a, y, da=12, dy=1.5)
                sh = S.shell_inner(a, y, da=12, dy=1.5) - 0.35
                r = min((sc if sc > 0 else 2.0) + 2.4, sh if math.isfinite(sh) else 99)
            else:
                (yr, rr), (ym, rm) = root_and_rim(S, a)
                if kind == 'root':
                    y, r = yr, rr
                else:
                    dy, dr = val
                    rim, rim_r = S.rim(a), S.rim_radius(a)
                    neck = S.body_radius(a, rim + dy, da=10, dy=1.5)
                    y = rim + dy
                    r = max(rim_r + dr, (neck if neck > 0 else rim_r - 2) + 0.6)
            p = point(a, r, y)
            top = F.h(p[0], p[2])
            if math.isfinite(top) and p[1] < top + 0.6 and kind == 'roll':
                p[1] = top + 0.6
            n = p - centre; n /= np.linalg.norm(n)
            grid[i, j] = m.add(p, n, (j / (cols - 1), i / (len(rows) - 1)), 'head')
    for j in range(cols - 1):
        run = []
        for i in range(len(rows)):
            run += [grid[i, j], grid[i, j + 1]]
        a_, b_, c_ = (np.asarray(m.P[k]) for k in run[:3])
        if np.cross(b_ - a_, c_ - a_) @ ((a_ + b_ + c_) / 3 - centre) < 0:
            run = [run[k ^ 1] for k in range(len(run))]
        m.strip_append(run)
    return m


def curtain2(m, S, F, azimuths, length, steps, *, crown=None, joints=None, layer=0, crown_taper=0.3, back=1.0,
             centre=0.08, clear=1.0, bulge=0.0):
    """curtain with the gravity fall: every column falls from under the rim onto the collar, pads and back."""
    cols = []
    for a in azimuths:
        (yr, rr), (ym, rm) = root_and_rim(S, a, layer)
        rows = []
        if crown:
            top = max(crown)
            for yc in crown:
                ac = a * (1.0 - crown_taper * (yc - yr) / max(top - yr, 1e-6))
                sc = S.body_radius(ac, yc); sh = S.shell_inner(ac, yc) - SHELL_CLEAR
                r = min((sc if sc > 0 else rr) + SCALP_CLEAR + 0.2, sh if math.isfinite(sh) else 99)
                rows.append(point(ac, r, yc))
        rows.append(point(a, rr, yr))
        path = fall(F, point(a, rm + bulge, ym), length, back=back, centre=centre, clear=clear)
        rows += clear_chords(F, simplify(path, steps + 1))
        cols.append(rows)
    R, C = len(cols[0]), len(cols)
    # horizontal edges between neighbouring columns must clear the jersey too: push both rows back together
    for _ in range(30):
        moved = False
        for i in range(R - steps - 1, R):
            for j in range(C - 1):
                A, B = cols[j][i], cols[j + 1][i]
                if any(not F.outside(A + (B - A) * t, 0.25) for t in np.linspace(0.1, 0.9, 9)):
                    for jj in (j, j + 1):
                        cols[jj][i] = cols[jj][i] + np.array([0.0, 0.08, -0.25])
                    moved = True
        if not moved: break
    ids = np.zeros((R, C), int)
    jl = joints or (['head'] * (R - steps) + ['neck'] + ['thorax'] * (steps - 1))
    for j in range(C):
        for i in range(R):
            p = np.asarray(cols[j][i], float)
            ids[i, j] = m.add(p, radial(p), (j / (C - 1), i / (R - 1)), jl[min(i, len(jl) - 1)])
    P = np.array(m.P)
    for i in range(R):
        for j in range(C):
            du = P[ids[i, min(j + 1, C - 1)]] - P[ids[i, max(j - 1, 0)]]
            dv = P[ids[min(i + 1, R - 1), j]] - P[ids[max(i - 1, 0), j]]
            n = np.cross(du, dv)
            if n @ radial(P[ids[i, j]]) < 0: n = -n
            if np.linalg.norm(n) > 1e-9: m.N[ids[i, j]] = n / np.linalg.norm(n)
    for j in range(C - 1):
        run = []
        for i in range(R):
            run += [ids[i, j], ids[i, j + 1]]
        a_, b_, c_ = (np.array(m.P[k]) for k in run[:3])
        if np.cross(b_ - a_, c_ - a_) @ radial((a_ + b_ + c_) / 3) < 0:
            run = [run[k ^ 1] for k in range(len(run))]
        m.strip_append(run)
    return ids


def push_out(m, F, clear=0.15, rounds=60):
    """Final pass: any triangle edge that dips into the jersey moves its two vertices back (and a touch up)."""
    P = [np.asarray(p, float) for p in m.P]
    tris = m.tris()
    edges = sorted({tuple(sorted((int(t[u]), int(t[w])))) for t in tris for u, w in ((0, 1), (1, 2), (2, 0))})
    def inside(p):
        return p[1] < 37 and not (p[1] > F.h(p[0], p[2]) + clear or p[2] < F.zb(p[0], p[1]) - clear)
    for _ in range(rounds):
        moved = set()
        for a, b in edges:
            if any(inside(P[a] + (P[b] - P[a]) * t) for t in np.linspace(0, 1, 7)):
                moved.update((a, b))
        if not moved: break
        for k in moved:
            P[k] = P[k] + np.array([0.0, 0.05, -0.2])
    m.P = P
    return len(moved) if moved else 0


# ------------------------------------------------------------------------------------------------ b776 hr2: ride the body
# Noah's b775 test (10/18): Lawrence's long hair looked painted on and the jersey showed through it; Cam Ward's twists
# disappeared under the collar at some angles. Causes measured offline (job hr2): (1) every hair vertex followed ONE
# bone (head, neck or thorax) while the neck skin under it blends thorax/neck/head and the jersey follows the thorax
# and the shoulder pads, so in motion the collar and pads passed through the hair; (2) the drape avoided only
# UNIF_jersey, so the hair lay under the nameplate and the back numbers; (3) 0.15 to 1.0 cm of clearance, measured in
# the bind pose only. v3 (long_flow, short_twists):
# * each vertex is weighted like the body under it: rows inside the helmet ride the head; rows between the helmet rim
#   and the collar copy the nearest neck-skin vertex's palette entry (the game's own thorax/neck/head blends); rows on
#   the jersey ride the thorax (close up; hi_head has no shoulder bones) or copy the nearest jersey vertex's entry
#   (distant: the jersey's own thorax/shoulder-pad blends), so the hair rides on the pads;
# * the jersey is measured with its nameplate and numbers;
# * a pose fit pushes every vertex out until no hair sample is within the clearance of the jersey surface in any of
#   the game poses given (--poses: world matrices of game clips run through the game's high-body pass).

PALETTE_FREE = {"hi": (15, 16, 17, 18, 19, 20, 23, 24, 25, 26), "lo": (25, 26, 27, 28, 29, 30, 31, 32, 33, 34)}
JERSEY_SURFACES = ('UNIF_jersey', 'UNIF_sleeve', 'PLAYERNAME', 'PLAYERNAME_long', 'NUMBER_L', 'NUMBER_M', 'NUMBER_R',
                   'NUMBER_shoulder_A_L', 'NUMBER_shoulder_A_M', 'NUMBER_shoulder_A_R', 'NUMBER_shoulder_B_L',
                   'NUMBER_shoulder_B_M', 'NUMBER_shoulder_B_R')
JOINT_OF = {"hi": {"head": 2, "neck": 1, "thorax": 0}, "lo": {"head": 12, "neck": 11, "thorax": 10}}


def resolved_globals(sc):
    """Per vertex: the palette entry (transform index, or transform count + blend index) its selector resolves to."""
    out = np.full(sc.n, -1, int)
    for s in sc.subs:
        rec = int(s['record_offset'])
        mapping = struct.unpack_from('<56H', sc.d, rec + 8)
        for _mode, batch in sc.gltf.decode_batches(sc.d, s['command_offset'], s['word_count']):
            for v in batch:
                out[v] = mapping[sc.sel[v] // 3]
    return out


def blend_table(sc):
    """{palette entry: [(joint, weight), ...]} for every transform and blend of the scene's shape."""
    rec = sc.lanes.record_offset
    tc = sc.lanes.transform_count
    count = struct.unpack_from('<H', sc.d, rec + 0x52)[0]
    table = {j: [(j, 1.0)] for j in range(tc)}
    if count:
        inv = models._tools_module('nfl_scne_inventory')
        start = inv.resolve_relative(sc.d, rec + 0x60, len(sc.d), 'blends')
        for i in range(count):
            at = start + 0x1C * i
            kind = struct.unpack_from('<I', sc.d, at)[0]
            table[tc + i] = [tuple(struct.unpack_from('<If', sc.d, at + 4 + 8 * k)) for k in range(kind)]
    return table


class Riding:
    """Which palette entry a hair vertex takes from the body under it (per LOD)."""

    def __init__(self, rig, lod):
        self.lod = lod
        head_scene = rig.hi if lod == 'hi' else rig.lo
        self.table = blend_table(head_scene)
        names = [t['name'] for t in models.decode_skin(head_scene.d, head_scene.shape, head_scene.lanes,
                                                       head_scene.subs).transforms]
        self.joint_names = names
        allowed = {names.index(n) for n in ('thorax', 'neck', 'head')}
        if lod == 'lo':
            allowed |= {names.index(n) for n in ('lshoulderpad', 'rshoulderpad')}
        self.ok = {g for g, parts in self.table.items() if all(int(j) in allowed for j, _w in parts)}
        g = resolved_globals(head_scene)
        off = np.zeros(3) if lod == 'hi' else BODY_FROM_HEAD
        neck = np.unique(head_scene.tris(['SKIN_neck']))
        thorax = names.index('thorax')
        # the hair below the rim copies the LOWER neck: entries that carry at least a fifth of the thorax, so it stays
        # with the collar when the head tips back (crouched stance, looking up) instead of being pressed into it
        neck = neck[[g[v] in self.ok and sum(w for j, w in self.table[g[v]] if int(j) == thorax) >= 0.19
                     for v in neck]]
        self.neck_pos, self.neck_g = head_scene.pos[neck] - off, g[neck]
        if lod == 'lo':
            jt = np.unique(head_scene.tris(['UNIF_jersey']))
            jt = jt[[g[v] in self.ok for v in jt]]
            self.jersey_pos, self.jersey_g = head_scene.pos[jt] - off, g[jt]

    def entry(self, tag, p):
        """'head' | 'gap' (between the rim and the collar: like the neck skin) | 'body' (on the jersey)."""
        if tag == 'head':
            return 'head'
        if tag == 'gap':
            a = math.degrees(math.atan2(p[0], -(p[2] - AXIS_Z)))
            az = np.degrees(np.arctan2(self.neck_pos[:, 0], -(self.neck_pos[:, 2] - AXIS_Z)))
            cost = 0.08 * angdiff(az, a) + np.abs(self.neck_pos[:, 1] - p[1])
            g = int(self.neck_g[int(np.argmin(cost))])
            return self.name_or_global(g)
        if self.lod == 'hi':
            return 'thorax'
        d = np.linalg.norm(self.jersey_pos - p, axis=1)
        return self.name_or_global(int(self.jersey_g[int(np.argmin(d))]))

    def name_or_global(self, g):
        for name, j in JOINT_OF[self.lod].items():
            if g == j:
                return name
        return g

    def parts(self, entry):
        if isinstance(entry, str):
            return [(JOINT_OF[self.lod][entry], 1.0)]
        return [(int(j), float(w)) for j, w in self.table[entry]]


def ride_tag(S, p, above=0.8):
    """'gap' above the collar/pad top round the neck at this azimuth, else 'body'."""
    a = math.degrees(math.atan2(p[0], -(p[2] - AXIS_Z))); r = math.hypot(p[0], p[2] - AXIS_Z)
    top = S.jersey_env(a, min(r, 13.0))
    return 'gap' if (not math.isfinite(top) or p[1] > top + above) else 'body'


def tag_rows(m, tags):
    """Remember the riding tag of the vertices just added (one tag per vertex, in order)."""
    m.__dict__.setdefault('tags', [])
    m.tags += list(tags)


def curtain3(m, S, F, azimuths, lengths, steps, *, crown=None, flare=(2.2, 1.4), back=1.1, centre=0.1, clear=1.0,
             crown_taper=0.3, v_top=0.0):
    """Long hair v3: a sheet whose columns run crown (inside the shell) -> root -> rim (filling the gap under the
    shell's edge) -> flare (bunched just under the rim, standing off the neck) -> a gravity fall of each column's own
    length over the collar, pads and back (with the nameplate and numbers in the jersey fields)."""
    cols, tags = [], []
    for a, length in zip(azimuths, lengths):
        (yr, rr), (ym, rm) = root_and_rim(S, a)
        rim_r = S.rim_radius(a)
        rows, tg = [], []
        if crown:
            top = max(crown)
            for yc in crown:
                ac = a * (1.0 - crown_taper * (yc - yr) / max(top - yr, 1e-6))
                sc = S.body_radius(ac, yc); sh = S.shell_inner(ac, yc) - SHELL_CLEAR
                r = min((sc if sc > 0 else rr) + SCALP_CLEAR + 0.3, sh if math.isfinite(sh) else 99)
                rows.append(point(ac, r, yc)); tg.append('head')
        rows.append(point(a, rr, yr)); tg.append('head')
        rows.append(point(a, max(rm, min(rim_r - 0.4, rm + 1.2)), ym)); tg.append('head')
        dy, dr = flare
        r0 = max(rm, rim_r) + dr
        f0 = point(a, r0, max(ym - dy, S.jersey_env(a, r0) + clear + 0.4))
        path = fall(F, f0, length, back=back, centre=centre, clear=clear)
        fallen = clear_chords(F, simplify(path, steps + 1))
        for k, p in enumerate(fallen):
            rows.append(p)
            tg.append('gap' if k == 0 else ride_tag(S, p))
        cols.append(rows); tags.append(tg)
    R, C = len(cols[0]), len(cols)
    ids = np.zeros((R, C), int)
    for j in range(C):
        for i in range(R):
            p = np.asarray(cols[j][i], float)
            ids[i, j] = m.add(p, radial(p), (j / (C - 1), v_top + (1 - v_top) * i / (R - 1)), 'head')
            tag_rows(m, [tags[j][i]])
    P = np.array(m.P)
    for i in range(R):
        for j in range(C):
            du = P[ids[i, min(j + 1, C - 1)]] - P[ids[i, max(j - 1, 0)]]
            dv = P[ids[min(i + 1, R - 1), j]] - P[ids[max(i - 1, 0), j]]
            n = np.cross(du, dv)
            if n @ radial(P[ids[i, j]]) < 0: n = -n
            if np.linalg.norm(n) > 1e-9: m.N[ids[i, j]] = n / np.linalg.norm(n)
    for j in range(C - 1):
        run = []
        for i in range(R):
            run += [ids[i, j], ids[i, j + 1]]
        a_, b_, c_ = (np.array(m.P[k]) for k in run[:3])
        if np.cross(b_ - a_, c_ - a_) @ radial((a_ + b_ + c_) / 3) < 0:
            run = [run[k ^ 1] for k in range(len(run))]
        m.strip_append(run)
    return ids


def strand3(m, S, F, a, length, width, column, columns, *, crown=None, fractions=(0, 0.5, 1.0), back=1.6,
            centre=0.06, clear=1.0, taper=0.8, twist=0.0, rim_out=0.6):
    """Short twist v3: root and rim ride the head; the lock leaves the rim outward over the collar (never down into the
    neck opening) and its tip rests on the collar/upper back."""
    (yr, rr), (ym, rm) = root_and_rim(S, a)
    rim_r = S.rim_radius(a)
    r0 = max(rm, rim_r - 0.2) + rim_out
    start = point(a, r0, max(ym, S.jersey_env(a, r0) + clear + 0.4))
    path = fall(F, start, length, back=back, centre=centre, clear=clear)
    rows = clear_chords(F, simplify(path, len(fractions)))
    pts = [point(a, rr, yr)] + rows
    tags = ['head', 'head'] + [ride_tag(S, p) for p in rows[1:]]
    if crown is not None:
        ac = a * 0.75
        sc = S.body_radius(ac, crown); sh = S.shell_inner(ac, crown) - SHELL_CLEAR
        rc = min((sc if sc > 0 else rr) + SCALP_CLEAR, sh if math.isfinite(sh) else 99)
        pts = [point(ac, rc, crown)] + pts; tags = ['head'] + tags
    n = len(pts)
    a_list = [math.degrees(math.atan2(p[0], -(p[2] - AXIS_Z))) for p in pts]
    widths = [width * (1 - (1 - taper) * k / (n - 1)) for k in range(n)]
    if crown is not None: widths[0] *= 0.8
    vs = list(np.linspace(0.0, 1.0, n)) if crown is None else [0.0] + list(np.linspace(0.12, 1.0, n - 1))
    before = len(m.P)
    pad = 0.06 / columns
    card2(m, pts, widths, column / columns + pad, (column + 1) / columns - pad, vs, ['head'] * n, a_list, twist=twist)
    tag_rows(m, [t for t in tags for _side in (0, 1)])
    assert len(m.P) - before == 2 * n


def build_v3(name, S, lod):
    m = Mesh()
    hi = lod == 'hi'
    F = Fields(S)
    if name == 'long_flow':
        cols = 13 if hi else 7
        az = np.linspace(-72, 72, cols)
        ragged = np.array([0.0, 1.6, -0.8, 1.1, -1.3, 0.7, 0.0, -0.9, 1.4, -0.6, 1.0, -1.2, 0.5])[:cols] if hi else \
            np.array([0.0, 1.2, -0.8, 0.6, -0.8, 1.2, 0.0])
        lengths = [27.0 - 10.0 * (abs(a) / 72) ** 1.6 + r for a, r in zip(az, ragged)]
        curtain3(m, S, F, az, lengths, 4 if hi else 2, crown=[50.5, 46.5] if hi else [46.0], clear=1.0, centre=0.07)
    elif name == 'short_twists':
        n = 17 if hi else 9
        for i, a in enumerate(np.linspace(-86, 86, n)):
            side = abs(a) / 86
            length = 9.0 - 3.6 * side ** 2 + (0.5 if i % 2 else 0.0)
            strand3(m, S, F, a, length, (2.6 if hi else 3.6), i % 4, 4, crown=(44.0 if hi else None),
                    fractions=(0, 0.5, 1.0) if hi else (0, 1.0), twist=(0.4 if i % 2 else -0.4), rim_out=0.9)
    else:
        raise ValueError(name)
    return m


def ride(m, riding):
    """Replace every vertex's joint by the palette entry of the body under it."""
    m.J = [riding.entry(t, p) for t, p in zip(m.tags, m.P)]
    return m


# --------------------------------------------------------------------------------- pose fit

def _palettes(worlds, absolute):
    out = np.empty_like(worlds, dtype=np.float64)
    for j, a in enumerate(absolute):
        T = np.eye(4); T[3, :3] = -np.asarray(a)
        out[:, j] = T @ worlds[:, j]
    return out


class PoseFit:
    """The hair and the jersey surface skinned together in every given pose (body bind frame, cm)."""

    def __init__(self, rig, lod, poses):
        body = rig.body if lod == 'hi' else rig.lo
        self.lod = lod
        skin = models.decode_skin(body.d, body.shape, body.lanes, body.subs)
        names = [t['name'] for t in skin.transforms]
        absolute = np.array([t['absolute'] for t in skin.transforms])
        worlds = np.asarray(poses['hi_body' if lod == 'hi' else 'lo_body'], np.float64)
        pose_names = [str(n) for n in poses['hi_names' if lod == 'hi' else 'lo_names']]
        require_names = [n for n in names if n not in pose_names]
        if require_names:
            raise ValueError(f'poses lack joints {require_names}')
        worlds = worlds[:, [pose_names.index(n) for n in names]]
        self.pal = _palettes(worlds, absolute)                         # (P, J, 4, 4)
        self.names = names
        tris = body.tris(list(JERSEY_SURFACES))
        tris = tris[body.pos[tris].mean(axis=1)[:, 1] > 38.0]      # the upper body (the hair never reaches lower)
        verts = np.unique(tris)
        remap = {v: i for i, v in enumerate(verts)}
        self.jt = np.vectorize(remap.get)(tris)
        self.jpos = np.c_[body.pos[verts], np.ones(len(verts))]
        raw = models.read_lane_u32(body.d, body.shape, body.lanes.normal, body.n)
        self.jnrm = np.array([models.decode_normpacked3(raw[v]) for v in verts])
        J = np.zeros((len(verts), 3), int); W = np.zeros((len(verts), 3))
        for i, v in enumerate(verts):
            for k, (j, w) in enumerate(skin.influences[v][:3]):
                J[i, k] = j; W[i, k] = w
        self.jJ, self.jW = J, W
        # hair joints are named in the hair's own scene; for close-ups those are the body joints of the same name
        head_scene = rig.hi if lod == 'hi' else rig.lo
        hn = [t['name'] for t in models.decode_skin(head_scene.d, head_scene.shape, head_scene.lanes,
                                                    head_scene.subs).transforms]
        self.hair_to_body = {j: names.index(n) for j, n in enumerate(hn) if n in names}

    def jersey(self, p):
        M = self.pal[p]
        pos = sum(self.jW[:, k:k + 1] * np.einsum('ni,nij->nj', self.jpos, M[self.jJ[:, k]])[:, :3] for k in range(3))
        nrm = sum(self.jW[:, k:k + 1] * np.einsum('ni,nij->nj', self.jnrm, M[self.jJ[:, k], :3, :3]) for k in range(3))
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        return pos, nrm

    def matrices(self, p, parts_list):
        M = self.pal[p]
        out = np.zeros((len(parts_list), 4, 4))
        for i, parts in enumerate(parts_list):
            for j, w in parts:
                out[i] += w * M[self.hair_to_body[j]]
        return out


def _bary(steps):
    out = []
    for i in range(steps + 1):
        for j in range(steps + 1 - i):
            a, b = i / steps, j / steps
            out.append((1 - a - b, a, b))
    return np.array(out)


def keep_under_rim(S, P, J, below=0.8):
    """Hair that does not ride the head stays below the helmet's rim: it is never pushed up into the shell (where it
    would show through it)."""
    P = np.array(P, float)
    for i, p in enumerate(P):
        if J[i] == 'head':
            continue
        a = math.degrees(math.atan2(p[0], -(p[2] - AXIS_Z)))
        P[i, 1] = min(p[1], S.rim(a) - below)
    return P


def fit_to_poses(m, riding, fit, clear=0.5, rounds=24, steps=3, smooth=0.35, log=None, S=None, max_move=2.5):
    """Push the hair (bind, head frame) out of the jersey until no sample is within `clear` cm of it (inside or
    outside) in any pose. Pushes are made in each vertex's own bind frame (its blended palette matrix inverted).
    Triangles with a corner riding the head (the root band under and just below the rim) are not fitted."""
    from scipy.spatial import cKDTree
    P = np.array(m.P, float)
    P0 = P.copy()
    parts = [riding.parts(e) for e in m.J]
    tris = m.tris()
    # the root band (any corner riding the head) leaves the helmet with the head; when the helmet itself is pressed
    # into the collar it goes under the collar with it (hair tucked in), so only the rest is fitted strictly
    tris = tris[[not any(m.J[int(v)] == 'head' for v in t) for t in tris]]
    B = _bary(steps)
    jtri_b = _bary(6)
    stats = []
    for rnd in range(rounds + 1):
        push = np.zeros_like(P); need_max = np.zeros(len(P)); bad = 0; worst = 0.0
        hb = np.c_[P + BODY_FROM_HEAD, np.ones(len(P))]
        for p in range(fit.pal.shape[0]):
            jp, jn = fit.jersey(p)
            js = np.einsum('sk,tkd->tsd', jtri_b, jp[fit.jt]).reshape(-1, 3)
            jns = np.einsum('sk,tkd->tsd', jtri_b, jn[fit.jt]).reshape(-1, 3)
            Mv = fit.matrices(p, parts)
            hw = np.einsum('ni,nij->nj', hb, Mv)[:, :3]
            hs = np.einsum('sk,tkd->tsd', B, hw[tris]).reshape(-1, 3)
            d, i = cKDTree(js).query(hs)
            n = jns[i] / np.maximum(np.linalg.norm(jns[i], axis=1, keepdims=True), 1e-9)
            sd = np.einsum('ij,ij->i', hs - js[i], n)
            # behind or within `clear` of the surface ACROSS it (past an open edge such as the collar rim the offset
            # runs along the surface: that is free space)
            hit = (d < 5.0) & (sd < clear) & (np.abs(sd) >= 0.5 * d)
            if not hit.any():
                continue
            bad += int(((d < 5.0) & (sd < 0.1)).sum()); worst = max(worst, float(clear - sd[hit].min()))
            idx = np.nonzero(hit)[0]
            t_of = idx // len(B); b_of = B[idx % len(B)]
            need = (clear - sd[idx])[:, None] * n[idx]                  # world push
            for k in range(3):
                v = tris[t_of, k]
                inv = np.linalg.inv(Mv[v, :3, :3])
                local = np.einsum('ni,nij->nj', need * b_of[:, k:k + 1], inv) / np.maximum(b_of[:, k:k + 1], 1e-6)
                mag = np.linalg.norm(local, axis=1) * b_of[:, k]
                for vv, mg, vec in zip(v, mag, local):
                    if mg > need_max[vv]:
                        need_max[vv] = mg; push[vv] = vec * min(1.0, 0.5 + b_of[:, k].max())
        stats.append(dict(round=rnd, inside_samples=bad, worst_cm=round(worst, 3), moved=int((need_max > 0).sum())))
        if log: log(stats[-1])
        if not need_max.any() or rnd == rounds:
            break
        # smooth the pushes along the strip neighbourhood so the hair keeps its shape
        nb = {i: set() for i in range(len(P))}
        for t in tris:
            for a_ in t:
                nb[int(a_)].update(int(b_) for b_ in t if b_ != a_)
        sm = push.copy()
        for i_ in range(len(P)):
            if nb[i_]:
                sm[i_] = (1 - smooth) * push[i_] + smooth * np.mean([push[j] for j in nb[i_]], axis=0)
            if np.linalg.norm(sm[i_]) < np.linalg.norm(push[i_]):
                sm[i_] = push[i_]
        P = P + sm * 1.15
        move = P - P0
        length = np.linalg.norm(move, axis=1, keepdims=True)
        P = P0 + move * np.minimum(1.0, max_move / np.maximum(length, 1e-9))   # the authored shape is kept
        if S is not None:
            P = keep_under_rim(S, P, m.J)
    m.P = [p for p in P]
    m.fit_stats = stats
    return m


def build_v3_fitted(name, rig, lod, poses, log=None):
    S = surfaces_v3(rig, lod)
    m = build_v3(name, S, lod)
    riding = Riding(rig, lod)
    ride(m, riding)
    if poses is not None:
        m.P = list(keep_under_rim(S, m.P, m.J))
        fit_to_poses(m, riding, PoseFit(rig, lod, poses), clear=0.5 if lod == 'hi' else 0.8, log=log, S=S,
                     max_move=2.5 if lod == 'hi' else 3.0)
    m.riding = riding
    return m


def surfaces_v3(rig, lod):
    """surfaces() with the nameplate and the numbers counted as jersey."""
    S = surfaces(rig, lod)
    body = [rig.body] if lod == 'hi' else [rig.lo]
    jer = np.concatenate([tri_samples(b, list(JERSEY_SURFACES), offset=-BODY_FROM_HEAD) for b in body])
    S.jersey = polar(jer)
    S.jersey_pts = jer
    return S


# ------------------------------------------------------------------------------------------------ art

M = 4          # textures are drawn at 4x and area-downscaled
TEX = 64

def _finish(rgb, alpha, colours=200):
    H, W = alpha.shape
    img = np.dstack([rgb, alpha])
    small = img.reshape(TEX, H // TEX, TEX, W // TEX, 4)
    a = small[..., 3].mean(axis=(1, 3))
    c = (small[..., :3] * small[..., 3:4]).mean(axis=(1, 3)) / np.maximum(a[..., None], 1e-6)
    fill = (rgb * alpha[..., None]).reshape(-1, 3).sum(0) / max(alpha.sum(), 1e-6)
    c[a < 1e-3] = fill
    a = np.where(a >= 0.5, 1.0, np.where(a >= 0.2, a, 0.0))   # mostly binary for alpha test, soft rims kept low
    a = np.where(a >= 0.5, 1.0, 0.0)
    rgb8 = np.clip(np.round(c * 255), 0, 255).astype(np.uint8)
    q = Image.fromarray(rgb8, 'RGB').quantize(colors=min(colours, 255), method=Image.Quantize.MEDIANCUT,
                                               dither=Image.Dither.NONE).convert('RGB')
    out = np.dstack([np.asarray(q), (a * 255).astype(np.uint8)])
    out[a < 0.5, :3] = np.round(fill * 255).astype(np.uint8)
    return Image.fromarray(out, 'RGBA')


def _grid():
    H = W = TEX * M
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    return x, y, (y + 0.5) / H, (x + 0.5) / W

def ropes(columns=4, base=(0.11, 0.08, 0.065), hi=(0.36, 0.27, 0.20), lo=(0.03, 0.025, 0.02), tip=None, kind='locs',
          seed=1, root_shade=0.12, width=0.82, end=0.9):
    """Locs / twists / braids: one rope per texture column."""
    x, y, v, u_all = _grid()
    H, W = x.shape
    rng = np.random.default_rng(seed)
    col_w = W / columns
    rgb = np.zeros((H, W, 3), np.float32); alpha = np.zeros((H, W), np.float32)
    base, hi, lo = map(np.array, (base, hi, lo))
    for c in range(columns):
        cx = (c + 0.5) * col_w + rng.uniform(-1.5, 1.5) * M
        u = (x - cx) / (col_w * 0.5)
        half = width - 0.12 * v
        capv = end + rng.uniform(-0.04, 0.03)
        cap = np.sqrt(np.clip(1.0 - ((v - capv) / (1.0 - capv)) ** 2, 0, 1))
        half = np.where(v > capv, half * cap, half)
        wob = 0.05 * np.sin(v * (7 + c) + c * 1.3)
        d = np.abs(u - wob) / np.maximum(half, 0.02)
        inside = np.clip((1 - d) * 6, 0, 1) * (np.abs(x - cx) < col_w * 0.5)
        shade = np.sqrt(np.clip(1 - d ** 2, 0, 1))
        if kind == 'twists':
            period = (8.5 + 1.5 * c) / 64
            phase = v / period + 0.9 * np.abs(u - wob)
            band = 0.5 + 0.5 * np.cos(2 * math.pi * phase + c)
            seam = np.clip(1 - np.abs(u - wob) / 0.07, 0, 1)
            crest = band ** 2 * shade
            col = lo + (base - lo) * (0.4 + 0.6 * shade)[..., None] + (hi - base) * (0.55 * crest)[..., None]
            col *= (1 - 0.45 * seam * (1 - band))[..., None]
        elif kind == 'braids':
            period = 5.5 / 64
            phase = v / period + 1.4 * (u - wob)
            phase2 = v / period - 1.4 * (u - wob)
            band = np.where(u - wob > 0, 0.5 + 0.5 * np.cos(2 * math.pi * phase), 0.5 + 0.5 * np.cos(2 * math.pi * phase2))
            crest = band ** 1.5 * shade
            col = lo + (base - lo) * (0.35 + 0.65 * shade)[..., None] + (hi - base) * (0.7 * crest)[..., None]
            seam = np.clip(1 - np.abs(u - wob) / 0.06, 0, 1)
            col *= (1 - 0.35 * seam)[..., None]
        else:   # locs: matted, segmented rope
            noise = rng.normal(0, 1, (H // 8 + 1, W // 8 + 1))
            n = np.kron(noise, np.ones((8, 8)))[:H, :W]
            seg = 0.5 + 0.5 * np.sin(v * 2 * math.pi * (5 + c * 0.7) + n * 0.8)
            crest = (0.35 + 0.65 * seg) * shade
            col = lo + (base - lo) * (0.35 + 0.65 * shade)[..., None] + (hi - base) * (0.5 * crest)[..., None]
        if tip is not None:
            t = np.clip((v - 0.45) / 0.45, 0, 1)[..., None]
            col = col * (1 - t) + np.array(tip) * (0.55 + 0.45 * shade)[..., None] * t
        col *= (1 - root_shade * np.clip((0.12 - v) / 0.12, 0, 1))[..., None]
        col = np.clip(col + rng.normal(0, 0.01, (H, W))[..., None], 0, 1)
        sel = inside > alpha
        rgb[sel] = col[sel]; alpha = np.maximum(alpha, inside)
    return _finish(rgb, alpha)

def strands(base=(0.78, 0.62, 0.36), hi=(0.97, 0.88, 0.62), lo=(0.42, 0.30, 0.15), seed=3, ragged=0.22, wave=0.0,
            root=None):
    """A sheet of straight or wavy hair: vertical strands, ragged tips at the bottom (alpha), clean top."""
    x, y, v, u = _grid()
    H, W = x.shape
    rng = np.random.default_rng(seed)
    base, hi, lo = map(np.array, (base, hi, lo))
    # strand field: 1-D noise across u, stretched along v, plus a little waviness
    k = rng.normal(0, 1, W)
    k = np.convolve(k, np.ones(3) / 3, mode='same')
    xs = (x + wave * M * 3 * np.sin(v * 2 * math.pi * 2.0 + u * 6)).astype(int) % W
    s = k[xs]
    s = (s - s.min()) / (s.max() - s.min())
    sheen = np.exp(-((v - 0.30) / 0.09) ** 2) * 0.6 + np.exp(-((v - 0.62) / 0.12) ** 2) * 0.3
    col = lo + (base - lo) * (0.45 + 0.55 * s)[..., None] + (hi - base) * (sheen * s)[..., None]
    if root is not None:
        t = np.clip((0.18 - v) / 0.18, 0, 1)[..., None]
        col = col * (1 - t) + np.array(root) * t
    # ragged tips: each strand group ends at its own length
    groups = rng.uniform(1 - ragged, 1.0, W // M + 1)
    ends = np.kron(groups, np.ones(M))[:W]
    ends = np.convolve(ends, np.ones(M) / M, mode='same')
    alpha = (v < ends[None, :]).astype(np.float32)
    # thin the extreme sides a little
    alpha *= ((u > 0.01) & (u < 0.99)).astype(np.float32)
    col = np.clip(col + rng.normal(0, 0.012, (H, W))[..., None], 0, 1)
    return _finish(col.astype(np.float32), alpha)

def curls(base=(0.13, 0.095, 0.075), hi=(0.42, 0.31, 0.22), lo=(0.025, 0.02, 0.018), seed=5, fuzz=0.22):
    """Tight curls (afro): many small coils, a fuzzy bottom and side edge."""
    x, y, v, u = _grid()
    H, W = x.shape
    rng = np.random.default_rng(seed)
    base, hi, lo = map(np.array, (base, hi, lo))
    f = np.zeros((H, W), np.float32)
    for _ in range(900):
        cx, cy, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(2.0, 4.5) * M / 2
        d = np.hypot(x - cx, y - cy)
        ring = np.exp(-((d - r) / (0.35 * M)) ** 2)
        f = np.maximum(f, ring * rng.uniform(0.5, 1.0))
    col = lo + (base - lo) * (0.5 + 0.5 * f)[..., None] + (hi - base) * (0.6 * f ** 3)[..., None]
    edge = 1 - fuzz + fuzz * rng.uniform(0, 1, (H // M + 1, W // M + 1))
    edge = np.kron(edge, np.ones((M, M)))[:H, :W]
    alpha = (v < 0.86 + 0.14 * edge).astype(np.float32)
    return _finish(np.clip(col, 0, 1).astype(np.float32), alpha)

def paint_bun(base=(0.10, 0.08, 0.065), hi=(0.32, 0.25, 0.19), lo=(0.03, 0.025, 0.02), seed=7):
    """Hair pulled back into a knot: strands converging, wrapped coil in the lower half (no alpha holes)."""
    x, y, v, u = _grid()
    H, W = x.shape
    rng = np.random.default_rng(seed)
    base, hi, lo = map(np.array, (base, hi, lo))
    k = rng.normal(0, 1, W * 2); k = np.convolve(k, np.ones(5) / 5, mode='same')
    # top half: strands pulled back (vertical); bottom half: the coil (strands along u)
    a = np.where(v < 0.5, k[(x).astype(int) % (2 * W)], k[(y * 2).astype(int) % (2 * W)])
    a = (a - a.min()) / (a.max() - a.min())
    sheen = np.where(v < 0.5, np.exp(-((v - 0.25) / 0.1) ** 2), 0.5 + 0.5 * np.cos((v - 0.75) * 2 * math.pi * 2))
    col = lo + (base - lo) * (0.45 + 0.55 * a)[..., None] + (hi - base) * (0.5 * sheen * a)[..., None]
    alpha = np.ones((H, W), np.float32)
    return _finish(np.clip(col, 0, 1).astype(np.float32), alpha)

BLOND = dict(base=(0.80, 0.64, 0.37), hi=(0.98, 0.90, 0.64), lo=(0.45, 0.32, 0.16))
BROWN = dict(base=(0.30, 0.20, 0.12), hi=(0.55, 0.40, 0.26), lo=(0.10, 0.065, 0.04))
BLACK = dict(base=(0.09, 0.07, 0.06), hi=(0.30, 0.24, 0.20), lo=(0.02, 0.018, 0.016))

ART = {
    'locs_dark': lambda: ropes(kind='locs', seed=11),
    'locs_light': lambda: ropes(kind='locs', seed=12, tip=(0.80, 0.60, 0.32)),
    'twists_dark': lambda: ropes(kind='twists', seed=13, base=(0.12, 0.09, 0.07), hi=(0.40, 0.30, 0.215)),
    'braids_dark': lambda: ropes(kind='braids', seed=14, width=0.62, end=0.93, base=(0.10, 0.08, 0.065), hi=(0.38, 0.30, 0.23)),
    'strands_blond': lambda: strands(seed=21, wave=0.25, **BLOND),
    'strands_brown': lambda: strands(seed=22, wave=0.35, **BROWN),
    'strands_black': lambda: strands(seed=23, wave=0.3, **BLACK),
    'curls_dark': lambda: curls(seed=31),
    'bun_dark': lambda: paint_bun(seed=41),
}



# ------------------------------------------------------------------------------------------------ records

SELECTORS = {"hi": {j: 3 * slot for j, (slot, _joint) in hair.PALETTE[hair.HI].items()},
             "lo": {j: 3 * slot for j, (slot, _joint) in hair.PALETTE[hair.LO].items()}}


def records_for(mesh: Mesh, lod: str, scene: Scene, riding: "Riding | None" = None) -> tuple[bytes, list[int], list]:
    """Raw vertex records in the scene's stream order (position + normal | uv + selector | tangent frame), and the
    extra palette slots (b776 hr2) the mesh's riding entries need: [[slot, entry, [[joint, weight], ...]], ...]."""
    lanes = scene.lanes
    P, N, UV, J, strip = mesh.arrays()
    if lod == "lo":
        P = P + BODY_FROM_HEAD
    extra = sorted({j for j in J if not isinstance(j, str)})
    free = PALETTE_FREE[lod]
    if len(extra) > len(free):
        raise ValueError(f"{len(extra)} riding entries need palette slots; {len(free)} are free")
    slot_of = {g: free[k] for k, g in enumerate(extra)}
    palette = [[slot_of[g], int(g), [[int(j), float(w)] for j, w in riding.table[g]]] for g in extra]
    out = bytearray()
    for i in range(len(P)):
        q = tuple(models.encode_normshort(max(-1.0, min(1.0, (float(P[i][k]) - lanes.offset[k]) / lanes.scale)))
                  for k in range(3))
        n = N[i] / np.linalg.norm(N[i])
        out += struct.pack("<3h", *q) + struct.pack("<I", models.encode_normpacked3(*n))
        uu, vv = models.uv_from_gltf(float(UV[i][0]), float(UV[i][1]), lanes.uv_scale, lanes.uv_offset)
        selector = SELECTORS[lod][J[i]] if isinstance(J[i], str) else 3 * slot_of[J[i]]
        out += struct.pack("<hhh", uu, vv, selector)
        if len(scene.streams) > 2:
            t = np.cross(np.array([0.0, 1.0, 0.0]), n)
            t = t / np.linalg.norm(t) if np.linalg.norm(t) > 1e-6 else np.array([1.0, 0.0, 0.0])
            b = np.cross(n, t)
            out += struct.pack("<II", models.encode_normpacked3(*t), models.encode_normpacked3(*b))
    return bytes(out), strip, palette


# ------------------------------------------------------------------------------------------------ b778 hr4: tops
# Noah (10/22, Jaylen Warren PIT #30 on the v0.6.1 disc): "guys who have dreads should never be bald". Every dreads
# style hangs from under the helmet's back rim, so with the helmet off the top of the head is whatever the player's
# skull texture paints there, and many 2026 faces paint bare skin. A top is a layer of locks lying back over the
# whole scalp (hairline -> crown -> gathered at the back), inside both Riddell shells, riding the head. One top
# ("locs") is shared by long_locs and short_twists (their rope textures have the same four opaque columns); the other
# ("dreads") is drawn by the retail HAIR_dreads material with the retail 'dread' texture (its opaque top band).
#
# Where the scalp carries hair is measured, not guessed: the generic heads' skull textures (n9001 ...) paint dark hair
# exactly where a hairline is, so the mask is the share of those templates that are dark at each skull texel. The
# mask is read from the user's own disc while authoring and never shipped; only the authored vertices are.

TOP_CENTRE = np.array([0.0, 41.0, 9.5])
TOP_TILT = 15.0                       # the gathering point sits 15 degrees above the back of the head
TOP_TEMPLATES = (9001, 9002, 9004, 9005, 9006, 9101, 9104, 9106, 9107)   # generic heads with dark hair, light skin
TOP_ROPE_COLUMNS = ((5.5, 11.5), (20.5, 27.5), (37.5, 43.5), (52.5, 58.5))  # opaque in locs_dark/light, twists_dark
TOP_ROPE_V = 0.42                     # locs_light turns blond from v 0.45: the top keeps the dark roots
TOP_DREAD_UV = ((6.5 / 64, 58.5 / 64), (3.5 / 64, 12.5 / 64))   # the retail dread's opaque top band
TOP_PARAMS = dict(ribbons=24, spacing=3.5, widen=1.35, bulk=0.55, edge_bulk=0.15, layer=0.15, clear=0.45,
                  shell_clear=0.5, tip=0.6, theta_step=2.0, dread_span=0.22)


def hair_mask_from_disc(path) -> np.ndarray:
    """(256, 256) share of the generic dark-haired heads whose skull texture is dark at each texel."""
    sys.path.insert(0, str(ROOT / "tools"))
    import nfl2k5_playbook_position_recode as recode
    from mod_editor.core import nfl2k5_alien_prospect as ap
    tx = models._tools_module("nfl_txtr")
    dark = []
    with recode.OuterImage(path) as archive:
        for face in TOP_TEMPLATES:
            entry = next((e for e in archive.entries if e.name_id == ap.name_id(f"pf{face:04d}.iff")), None)
            if entry is None:
                raise ValueError(f"the disc has no generic head pf{face:04d}.iff")
            raw = archive.read(entry.virtual_offset, entry.size)
            for c in tx.parse_chunks(raw, allow_trailing=True):
                if c.kind != "TXTR":
                    continue
                span = raw[c.offset:c.offset + 32 + c.stored_size]
                cc = tx.parse_chunks(span)[0]
                d, _ = tx.decode_chunk(span, cc)
                t = tx.parse_texture(d, cc)
                if t.name == f"n{face:04d}":
                    rgb = np.frombuffer(tx.texture_to_rgba(d, cc, t), np.uint8).reshape(t.height, t.width, 4)[..., :3]
                    img = Image.fromarray(rgb, "RGB").resize((256, 256), Image.BILINEAR)
                    dark.append(np.asarray(img, np.float64) @ np.array([0.3, 0.59, 0.11]) < 85)
    if len(dark) != len(TOP_TEMPLATES):
        raise ValueError("a generic head has no skull texture")
    return np.mean(dark, axis=0)


def _raycast(origin, dirs, tris):
    e1 = tris[:, 1] - tris[:, 0]; e2 = tris[:, 2] - tris[:, 0]
    p = np.cross(dirs[:, None, :], e2[None])
    det = np.einsum('rmk,mk->rm', p, e1)
    with np.errstate(divide='ignore', invalid='ignore'):
        inv = np.where(np.abs(det) < 1e-12, np.nan, 1.0 / det)
    s = origin - tris[:, 0]
    u = np.einsum('rmk,mk->rm', p, s) * inv
    q = np.cross(s, e1)
    v = np.einsum('rk,mk->rm', dirs, q) * inv
    t = np.einsum('mk,mk->m', e2, q)[None] * inv
    ok = (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & (t > 0)
    return np.where(ok, t, np.inf), u, v


class Scalp:
    """Rays from TOP_CENTRE: the outermost skin (skull, face, neck), the hair mask there, the innermost shell."""

    def __init__(self, head: Scene, mask: np.ndarray):
        self.head, self.mask = head, mask
        tris, kinds = [], []
        for k, name in enumerate(("SKIN_skull", "SKIN_face", "SKIN_neck")):
            t = head.tris([name]); tris.append(t); kinds += [k] * len(t)
        self.skin_t = np.concatenate(tris); self.kind = np.array(kinds)
        self.skin = head.pos[self.skin_t]
        self.shell = head.pos[head.tris(['HI_HELMET_A', 'HI_HELMET_B', 'HI_HELMET_C'])]

    def cast(self, dirs):
        n = len(dirs)
        skin = np.full(n, -np.inf); hair = np.zeros(n); shell = np.full(n, np.inf)
        for a in range(0, n, 128):
            d = dirs[a:a + 128]
            t, u, v = _raycast(TOP_CENTRE, d, self.skin)
            tt = np.where(np.isfinite(t), t, -np.inf)
            j = np.argmax(tt, axis=1)
            for r in range(len(d)):
                m = j[r]; skin[a + r] = tt[r, m]
                if not np.isfinite(tt[r, m]) or self.kind[m] != 0:
                    continue
                tri = self.skin_t[m]; uu, vv = u[r, m], v[r, m]
                uv = (1 - uu - vv) * self.head.uv[tri[0]] + uu * self.head.uv[tri[1]] + vv * self.head.uv[tri[2]]
                H, W = self.mask.shape
                hair[a + r] = self.mask[int(np.clip(uv[1] * H, 0, H - 1)), int(np.clip(uv[0] * W, 0, W - 1))]
            ts, _u, _v = _raycast(TOP_CENTRE, d, self.shell)
            shell[a:a + 128] = ts.min(axis=1)
        return skin, hair, shell


def top_dirs(theta, phi):
    """Meridians round an axis from the face (theta 0, tipped down) to the gathering point (theta 180, tipped up)."""
    th, ph = np.radians(theta), np.radians(phi)
    d = np.stack([np.sin(th) * np.sin(ph), np.sin(th) * np.cos(ph), np.cos(th)], -1)
    a = math.radians(TOP_TILT)
    R = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    return d @ R.T


def build_top(scalp: Scalp, kind: str, p=TOP_PARAMS) -> Mesh:
    """``kind`` 'locs' (rope columns) or 'dreads' (the retail dread's top band). A Mesh riding the head."""
    n = p['ribbons']; dphi = 360.0 / n
    thetas = np.arange(0, 180 + 1e-6, p['theta_step'])
    ribbons = []
    for k in range(n):
        phi = -180 + dphi * (k + 0.5)
        skin, hair, _shell = scalp.cast(top_dirs(thetas, np.full(len(thetas), phi)))
        ok = (hair > 0.5) & np.isfinite(skin)
        # every run of hair along the meridian is a lock (an ear splits the side meridians into temple and back)
        i = 0
        while i < len(ok):
            if not ok[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(ok) and ok[j + 1]:
                j += 1
            start, end = thetas[i], thetas[j]
            if i > 0 and hair[i] != hair[i - 1]:        # the hairline, between two samples
                start = thetas[i - 1] + (0.5 - hair[i - 1]) / (hair[i] - hair[i - 1]) * p['theta_step']
            if j + 1 < len(ok) and hair[j] != hair[j + 1]:
                end = thetas[j] + (hair[j] - 0.5) / (hair[j] - hair[j + 1]) * p['theta_step']
            th = np.unique(np.clip(np.concatenate([[start], thetas[i:j + 1], [end]]), start, end))
            i = j + 1
            if len(th) < 2:
                continue
            sk, _h, _s = scalp.cast(top_dirs(th, np.full(len(th), phi)))
            if not np.isfinite(sk).all():
                continue
            arc = np.concatenate([[0.0], np.cumsum(np.radians(np.diff(th)) * sk[:-1])])
            if arc[-1] < 1.5:
                continue
            rows = max(3, int(round(arc[-1] / p['spacing'])) + 1)
            want = np.linspace(0.0, arc[-1], rows)
            ribbons.append((k, phi, np.interp(want, arc, th), want))
    longest = max(r[3][-1] for r in ribbons)
    m = Mesh()
    half = 0.5 * p['widen'] * dphi
    for k, phi, ths, arcs in ribbons:
        lay = p['layer'] * (k % 2)
        rows = []
        for i, (t_, a_) in enumerate(zip(ths, arcs)):
            hw = half * (p['tip'] if i == 0 else 1.0)
            bulk = p['edge_bulk'] + (p['bulk'] - p['edge_bulk']) * min(a_ / 3.0, 1.0)
            d = top_dirs(np.array([t_, t_]), np.array([phi - hw, phi + hw]))
            sk, _h, sh = scalp.cast(d)
            r = np.minimum(sk + p['clear'] + bulk + lay, sh - p['shell_clear'])
            rows.append((TOP_CENTRE + d[0] * r[0], TOP_CENTRE + d[1] * r[1], a_))
        l0, r0, _a = rows[0]; l1 = rows[1][0]
        swap = np.cross(r0 - l0, l1 - l0) @ ((l0 + r0 + l1) / 3 - TOP_CENTRE) < 0
        if kind == 'locs':
            u0, u1 = (c / 64 for c in TOP_ROPE_COLUMNS[k % len(TOP_ROPE_COLUMNS)])
        else:
            (lo, hi), _v = TOP_DREAD_UV
            u0 = lo + (hi - lo - p['dread_span']) * ((k * 7) % n) / (n - 1)
            u1 = u0 + p['dread_span']
        ids = []
        for pl, pr, a_ in rows:
            if kind == 'locs':
                v = TOP_ROPE_V * a_ / longest
            else:
                (v0, v1) = TOP_DREAD_UV[1]
                v = v0 + (v1 - v0) * a_ / max(arcs[-1], 1e-6)
            nrm = (pl + pr) / 2 - TOP_CENTRE; nrm /= np.linalg.norm(nrm)
            first, second = ((pr, u1), (pl, u0)) if swap else ((pl, u0), (pr, u1))
            ids.append(m.add(first[0], nrm, (first[1], v), 'head'))
            ids.append(m.add(second[0], nrm, (second[1], v), 'head'))
        m.strip_append(ids)
    return m


def top_checks(scalp: Scalp, m: Mesh, steps=4) -> dict:
    """Every sample of the top's triangles: cm above the outermost skin and cm inside the innermost shell."""
    P = np.array(m.P); tris = m.tris(); B = _bary(steps)
    S = np.einsum('sk,tkd->tsd', B, P[tris]).reshape(-1, 3)
    rel = S - TOP_CENTRE; dist = np.linalg.norm(rel, axis=1); d = rel / dist[:, None]
    skin, _h, shell = scalp.cast(d)
    above = dist - skin; inside = shell - dist
    return {"samples": int(len(S)), "min_above_skin_cm": round(float(above.min()), 3),
            "min_inside_shell_cm": round(float(inside[np.isfinite(inside)].min()), 3),
            "samples_without_shell": int((~np.isfinite(inside)).sum())}


TOP_KEYS = ("locs", "dreads")


def generate_tops(outer3: bytes, mask: np.ndarray, base: dict) -> dict:
    """``base`` (the shipped geometry) with the hair tops of hi_head added; every part stays byte-identical."""
    rig = Rig(outer3)
    if hair.scene_state(rig.hi.key, rig.hi.d) != "retail":
        raise ValueError("generate the tops from a retail-shaped outer 3 (no hair growth)")
    scalp = Scalp(rig.hi, mask)
    document = json.loads(json.dumps(base))
    tops = {}
    for kind in TOP_KEYS:
        mesh = build_top(scalp, kind)
        records, strip, palette = records_for(mesh, "hi", rig.hi)
        if palette:
            raise ValueError("a top rides only the head")
        tops[kind] = {"records": b64_lines(records),
                      "strip": base64.b64encode(struct.pack(f"<{len(strip)}H", *strip)).decode("ascii"),
                      "vertices": len(mesh.P), "strip_length": len(strip), "checks": top_checks(scalp, mesh)}
    document["scenes"][hair.HI]["tops"] = tops
    return document


def b64_lines(data: bytes, width: int = 4000) -> str | list[str]:
    """b778 3d1: base64 text, split into lines of ``width`` characters when longer (the release check refuses any run
    of more than 4,096 characters without whitespace; the module joins the lines back, nfl2k5_hair_styles._b64_field)."""
    text = base64.b64encode(data).decode("ascii")
    return text if len(text) <= width else [text[i:i + width] for i in range(0, len(text), width)]


V3_MESHES = ("long_flow", "short_twists")


def generate(outer3: bytes, *, only: tuple[str, ...] | None = None, poses=None, base: dict | None = None,
             log=None) -> tuple[dict, dict[str, Image.Image]]:
    """The geometry document (and the art). With ``only``, every other mesh is copied unchanged from ``base`` (the
    shipped geometry) and no art is drawn; the v3 meshes (long_flow, short_twists) are built riding the body and,
    with ``poses``, fitted to the game poses."""
    rig = Rig(outer3)
    for sc in (rig.hi, rig.lo):
        if hair.scene_state(sc.key, sc.d) != "retail":
            raise ValueError(f"{sc.key}: generate from a retail-shaped outer 3 (no hair growth)")
    names = tuple(hair.MESHES) if only is None else tuple(only)
    meshes = {}
    for lod in ("hi", "lo"):
        S = surfaces(rig, lod)
        for name in names:
            if name in V3_MESHES:
                meshes[(name, lod)] = build_v3_fitted(name, rig, lod, poses, log=log)
            else:
                meshes[(name, lod)] = build(name, S, lod)
    document = {"schema": hair.GEOMETRY_SCHEMA, "meshes": list(hair.MESHES), "scenes": {}}
    for key, lod, scene in ((hair.HI, "hi", rig.hi), (hair.LO, "lo", rig.lo)):
        parts = {}
        for name in hair.MESHES:
            if name not in names:
                parts[name] = dict(base["scenes"][key]["parts"][name])
                continue
            mesh = meshes[(name, lod)]
            records, strip, palette = records_for(mesh, lod, scene, getattr(mesh, "riding", None))
            parts[name] = {"records": base64.b64encode(records).decode("ascii"),
                           "strip": base64.b64encode(struct.pack(f"<{len(strip)}H", *strip)).decode("ascii"),
                           "vertices": len(mesh.P), "strip_length": len(strip)}
            if palette:
                parts[name]["palette"] = palette
            if getattr(mesh, "fit_stats", None):
                parts[name]["fit"] = mesh.fit_stats[-1]
        document["scenes"][key] = {"vertex_count": scene.n,
                                   "strides": [scene.streams[s][1] for s in sorted(scene.streams)],
                                   "parts": parts}
    art = {} if only is not None else {name: ART[name]() for name in hair.TEXTURES}
    return document, art


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--disc", help="a retail or SOFTDRINK XISO (read only)")
    parser.add_argument("--outer3", help="or outer 3 already extracted from one")
    parser.add_argument("--out", default=str(hair.DATA_DIR))
    parser.add_argument("--only", help="comma-separated meshes to rebuild; every other mesh is copied from the shipped "
                        "geometry and the art is left alone")
    parser.add_argument("--poses", help="npz of game-pose world matrices (hi_body, lo_body, hi_names, lo_names) for "
                        "the v3 pose fit; see the module notes (b776 hr2)")
    parser.add_argument("--tops", action="store_true", help="b778 hr4: (re)build only the hair tops of hi_head from "
                        "the --disc (a retail disc: its outer 3 and generic heads); every mesh part is kept as shipped")
    args = parser.parse_args(argv)
    if args.tops:
        if not args.disc:
            parser.error("--tops reads the generic heads from a disc: give --disc")
        sys.path.insert(0, str(ROOT / "tools"))
        import nfl2k5_playbook_position_recode as recode
        with recode.OuterImage(args.disc) as archive:
            entry = archive.entries[hair.OUTER]
            outer3 = archive.read(entry.virtual_offset, entry.size)
        base = hair.load_geometry()
        base["scenes"][hair.HI].pop("tops", None)
        document = generate_tops(outer3, hair_mask_from_disc(args.disc), base)
        out = Path(args.out)
        (out / "geometry.json").write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                           newline="\n")
        for kind, top in document["scenes"][hair.HI]["tops"].items():
            print("top", kind, top["vertices"], "vertices", top["checks"])
        print("GEOMETRY_OK", out)
        return 0
    if args.outer3:
        outer3 = Path(args.outer3).read_bytes()
    else:
        sys.path.insert(0, str(ROOT / "tools"))
        import nfl2k5_playbook_position_recode as recode
        with recode.OuterImage(args.disc) as archive:
            entry = archive.entries[hair.OUTER]
            outer3 = archive.read(entry.virtual_offset, entry.size)
    only = tuple(args.only.split(",")) if args.only else None
    poses = dict(np.load(args.poses)) if args.poses else None
    base = hair.load_geometry() if only else None
    document, art = generate(outer3, only=only, poses=poses, base=base,
                             log=lambda row: print("  fit", row, flush=True))
    out = Path(args.out)
    (out / "art").mkdir(parents=True, exist_ok=True)
    for name, image in art.items():
        image.save(out / "art" / f"{name}.png", optimize=True)
    (out / "geometry.json").write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                       newline="\n")
    for key, entry in document["scenes"].items():
        print(key, {name: part["vertices"] for name, part in entry["parts"].items()})
    print("GEOMETRY_OK", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
