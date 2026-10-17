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
    if name == 'long_locs':
        # two layers of locks around the back half; back ones longest, side ones lie on the pads
        n = 12 if hi else 7
        az = np.linspace(-84, 84, n)
        for i, a in enumerate(az):
            side = abs(a) / 84
            length = (23 - 7 * side ** 1.5) + (1.5 if i % 2 else 0)
            lock(m, S, a, length, (3.9 if hi else 5.6), i % 4, 4, layer=i % 2, steps=3 if hi else 2,
                 lean=0.08 + 0.06 * side, joints_by_row=['head', 'head', 'neck', 'thorax', 'thorax'],
                 crown=(46.5 if hi else None))
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
        az = np.linspace(-108, 108, 11 if hi else 7)
        curtain(m, S, az, 6.0, 2 if hi else 1, crown=[51.0, 46.0] if hi else [47.0], lean=0.75, bulge=2.4,
                joints=['head'] * 8)
    elif name == 'braids':
        n = 10 if hi else 6
        for i, a in enumerate(np.linspace(-95, 95, n)):
            side = abs(a) / 95
            lock(m, S, a, 17 - 6 * side, (1.9 if hi else 2.8), i % 4, 4, layer=i % 2, steps=3 if hi else 2,
                 lean=0.14 + 0.1 * side, taper=0.8, joints_by_row=['head', 'head', 'neck', 'thorax', 'thorax'])
    elif name == 'bun':
        bun_mesh(m, S, hi)
    elif name == 'mullet':
        az = np.linspace(-85, 85, 9 if hi else 5)
        curtain(m, S, az, 12.0, 2 if hi else 1, crown=[46.0] if hi else None, lean=0.25,
                joints=['head', 'head', 'head', 'neck', 'thorax'] if hi else ['head', 'head', 'neck', 'thorax'])
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


def records_for(mesh: Mesh, lod: str, scene: Scene) -> tuple[bytes, list[int]]:
    """Raw vertex records in the scene's stream order (position + normal | uv + selector | tangent frame)."""
    lanes = scene.lanes
    P, N, UV, J, strip = mesh.arrays()
    if lod == "lo":
        P = P + BODY_FROM_HEAD
    out = bytearray()
    for i in range(len(P)):
        q = tuple(models.encode_normshort(max(-1.0, min(1.0, (float(P[i][k]) - lanes.offset[k]) / lanes.scale)))
                  for k in range(3))
        n = N[i] / np.linalg.norm(N[i])
        out += struct.pack("<3h", *q) + struct.pack("<I", models.encode_normpacked3(*n))
        uu, vv = models.uv_from_gltf(float(UV[i][0]), float(UV[i][1]), lanes.uv_scale, lanes.uv_offset)
        out += struct.pack("<hhh", uu, vv, SELECTORS[lod][J[i]])
        if len(scene.streams) > 2:
            t = np.cross(np.array([0.0, 1.0, 0.0]), n)
            t = t / np.linalg.norm(t) if np.linalg.norm(t) > 1e-6 else np.array([1.0, 0.0, 0.0])
            b = np.cross(n, t)
            out += struct.pack("<II", models.encode_normpacked3(*t), models.encode_normpacked3(*b))
    return bytes(out), strip


def generate(outer3: bytes) -> tuple[dict, dict[str, Image.Image]]:
    rig = Rig(outer3)
    meshes = all_meshes(rig)
    document = {"schema": hair.GEOMETRY_SCHEMA, "meshes": list(hair.MESHES), "scenes": {}}
    for key, lod, scene in ((hair.HI, "hi", rig.hi), (hair.LO, "lo", rig.lo)):
        parts = {}
        for name in hair.MESHES:
            records, strip = records_for(meshes[(name, lod)], lod, scene)
            parts[name] = {"records": base64.b64encode(records).decode("ascii"),
                           "strip": base64.b64encode(struct.pack(f"<{len(strip)}H", *strip)).decode("ascii"),
                           "vertices": len(meshes[(name, lod)].P), "strip_length": len(strip)}
        document["scenes"][key] = {"vertex_count": scene.n,
                                   "strides": [scene.streams[s][1] for s in sorted(scene.streams)],
                                   "parts": parts}
    art = {name: ART[name]() for name in hair.TEXTURES}
    return document, art


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--disc", help="a retail or SOFTDRINK XISO (read only)")
    parser.add_argument("--outer3", help="or outer 3 already extracted from one")
    parser.add_argument("--out", default=str(hair.DATA_DIR))
    args = parser.parse_args(argv)
    if args.outer3:
        outer3 = Path(args.outer3).read_bytes()
    else:
        sys.path.insert(0, str(ROOT / "tools"))
        import nfl2k5_playbook_position_recode as recode
        with recode.OuterImage(args.disc) as archive:
            entry = archive.entries[hair.OUTER]
            outer3 = archive.read(entry.virtual_offset, entry.size)
    document, art = generate(outer3)
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
