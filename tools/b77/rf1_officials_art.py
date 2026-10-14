#!/usr/bin/env python3
"""rf1: author the 2025/26 NFL officials' uniform for the game's officials (gamedata.iff, scene ``referee``).

Every texel of each texture is painted from the 3D point of the referee model it lands on (bind pose, game
centimetres; +y up, +z the front of the body), found by rasterising the model's own triangles into UV space (repeat
addressing, high LOD first, then the low LOD where the high LOD leaves the texel free). No retail pixel is copied:
the retail model only supplies the geometry and the UV layout.

Outputs, authored at 4x (``--masters``) and area-downscaled to the native slot (``--out``):
  shirt.png         256x256  the 2006-and-later shirt: black collar and centre placket, wide white and thin black
                             stripes that flare over the shoulders, the black shoulder yoke and the white number
                             panel on the back, long black sleeves with one white stripe down the outer arm and a black
                             cuff, the NFL shield on the wearer's left chest; black shoes with a white midsole line
  pants.png         256x256  black long pants with a thin white stripe down the outside of each leg, black belt
                             with a silver buckle, a small NFL shield on the wearer's right hip
  hat_white.png      64x64   the referee's white cap with the NFL shield on the front
  hat_black.png      64x64   the other officials' black cap with white piping on the seams and the shield
  numbers/ref_*.png 128x128  black role letters above the number (R, U, DJ, LJ, FJ, SJ, BJ); the down judge was the
                             head linesman (HL) until 2017. Rows 0-50 are clear: the retired front-chest number patch
                             samples there (see the module).

  python3 tools/b77/rf1_officials_art.py --gltf REFEREE.gltf --masters DIR --out data/nfl2k5_modern_officials

``REFEREE.gltf`` is the Studio's own export of the retail referee scene (mod_editor.core.nfl2k5_models.export_model).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

JOINTS = ('root lfemur ltibia lfoot ltoes rfemur rtibia rfoot rtoes waist thorax neck head '
          'lcollar lhumerus ltwist lelbow lwrist lhand rcollar rhumerus rtwist relbow rwrist rhand').split()
TORSO_J = (0, 9, 10, 11)
ARM_J = tuple(range(13, 25))
FOOT_J = (1, 2, 3, 4, 5, 6, 7, 8)
K = 4                                   # master scale
# +x is the wearer's LEFT in the game's bind pose (the retail front-chest number patch, x 0..17, sits there; checked
# against the emulator frames of the retail coin toss)
LEFT = 1.0
# UV-only geometry plan (the module writes the same lanes on the disc; positions, skin and topology stay retail):
# * the retired front-chest number patch samples the clear top rows of the numbers texture;
# * the high LOD collar ring and the two front collar points (shirt vertices 1317..1352 and 1291..1302) sample one
#   black texel; the ring sampled the retail black square at
#   u 0.744-0.813, v 0.663-0.732, which the back of the shirt behind the number also samples (it becomes the white
#   number panel).
FRONT_PATCH = {'ref_high': tuple(range(1433, 1442)), 'ref_low': tuple(range(418, 422))}
FRONT_PATCH_UV = (0.5, 0.15)
COLLAR = {'ref_high': tuple(range(1291, 1303)) + tuple(range(1317, 1353))}
COLLAR_UV = (0.490234375, 0.396484375)

WHITE = np.array((236, 236, 233), np.float64)
BLACK = np.array((26, 26, 28), np.float64)
PANTS_BLACK = np.array((30, 30, 33), np.float64)
BELT = np.array((18, 18, 19), np.float64)
SILVER = np.array((178, 180, 184), np.float64)
NAVY = np.array((1, 51, 105), np.float64)
RED = np.array((213, 10, 10), np.float64)
SHIELD_SILVER = np.array((200, 202, 206), np.float64)
# body centimetres (game units): the shirt's stripe spacing and width, the sleeve stripe
STRIPE_PERIOD = 8.3
PANTS_STRIPE = 3.4
STRIPE_WIDTH = 2.8
SLEEVE_STRIPE_DEG = 30.0
SLEEVE_STRIPE_HALF = 27.0


# --- the model in UV space -----------------------------------------------------------------------------------------

def load_gltf(path, overrides=True):
    g = json.loads(Path(path).read_text())
    binp = Path(path).with_suffix('.bin').read_bytes()

    def acc(i):
        a = g['accessors'][i]
        v = g['bufferViews'][a['bufferView']]
        n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
        dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8, 5122: np.int16}[a['componentType']]
        off = v.get('byteOffset', 0) + a.get('byteOffset', 0)
        return np.frombuffer(binp, dt, a['count'] * n, off).reshape(a['count'], n).astype(np.float64)
    prims = []
    for mesh in g['meshes']:
        for p in mesh['primitives']:
            at = p['attributes']
            idx = acc(p['indices']).ravel().astype(int)
            tris = []
            if p.get('mode', 4) == 5:
                for k in range(len(idx) - 2):
                    a, b, c = idx[k], idx[k + 1], idx[k + 2]
                    if len({a, b, c}) == 3:
                        tris.append((a, b, c) if k % 2 == 0 else (b, a, c))
            else:
                tris = [tuple(t) for t in idx.reshape(-1, 3)]
            w, j = acc(at['WEIGHTS_0']), acc(at['JOINTS_0'])
            uv = acc(at['TEXCOORD_0']).copy()
            game = acc(at['_NFL_VERTEX_INDEX']).ravel().astype(int)
            material = g['materials'][p['material']]['name']
            if overrides:
                plan = {'numbers': (FRONT_PATCH, FRONT_PATCH_UV), 'shirt': (COLLAR, COLLAR_UV)}.get(material)
                if plan is not None:
                    for k, gi in enumerate(game):
                        if gi in plan[0].get(mesh['name'], ()):
                            uv[k] = plan[1]
            prims.append(dict(mesh=mesh['name'], material=material, pos=acc(at['POSITION']),
                              nrm=acc(at['NORMAL']), uv=uv, tris=np.array(tris, int), game=game,
                              used=np.unique(np.array(tris, int).ravel()),
                              joint=j[np.arange(len(j)), np.argmax(w, axis=1)].astype(int)))
    return prims


def uvmap(prims, material, size, meshes=('ref_high', 'ref_low')):
    """Per texel: the bind-pose surface point, normal and dominant joint (repeat addressing; first mesh wins)."""
    H = W = size
    pos = np.zeros((H, W, 3))
    nrm = np.zeros((H, W, 3))
    joint = np.full((H, W), -1, int)
    lod = np.full((H, W), -1, int)
    for li, meshname in enumerate(meshes):
        for p in prims:
            if p['material'] != material or p['mesh'] != meshname:
                continue
            uv = p['uv']
            for a, b, c in p['tris']:
                U, V = uv[[a, b, c], 0] * W, uv[[a, b, c], 1] * H
                for ku in range(int(np.floor(U.min() / W)), int(np.floor(U.max() / W)) + 1):
                    for kv in range(int(np.floor(V.min() / H)), int(np.floor(V.max() / H)) + 1):
                        u0, v0 = U - ku * W, V - kv * H
                        x0, x1 = max(0, int(np.floor(u0.min() - 0.5))), min(W - 1, int(np.ceil(u0.max() + 0.5)))
                        y0, y1 = max(0, int(np.floor(v0.min() - 0.5))), min(H - 1, int(np.ceil(v0.max() + 0.5)))
                        if x1 < x0 or y1 < y0:
                            continue
                        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
                        d = (v0[1] - v0[2]) * (u0[0] - u0[2]) + (u0[2] - u0[1]) * (v0[0] - v0[2])
                        if abs(d) < 1e-12:
                            continue
                        l0 = ((v0[1] - v0[2]) * (xs - u0[2]) + (u0[2] - u0[1]) * (ys - v0[2])) / d
                        l1 = ((v0[2] - v0[0]) * (xs - u0[2]) + (u0[0] - u0[2]) * (ys - v0[2])) / d
                        l2 = 1 - l0 - l1
                        inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
                        iy, ix = np.nonzero(inside)
                        gy, gx = iy + y0, ix + x0
                        if li > 0:
                            free = lod[gy, gx] == -1
                            gy, gx, iy, ix = gy[free], gx[free], iy[free], ix[free]
                        if not len(gy):
                            continue
                        L = np.stack([l0[iy, ix], l1[iy, ix], l2[iy, ix]], -1)
                        pos[gy, gx] = L @ p['pos'][[a, b, c]]
                        n = L @ p['nrm'][[a, b, c]]
                        nrm[gy, gx] = n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)
                        joint[gy, gx] = p['joint'][[a, b, c]][np.argmax(L, axis=1)]
                        lod[gy, gx] = li
    return dict(pos=pos, nrm=nrm, joint=joint, cover=lod >= 0, lod=lod)


def dilate(rgba, cover, steps=64):
    """Fill uncovered texels from covered neighbours (so mip levels and bilinear taps do not pull in stray colour)."""
    out = rgba.astype(np.float64).copy()
    have = cover.copy()
    for _ in range(steps):
        if have.all():
            break
        acc = np.zeros_like(out)
        cnt = np.zeros(have.shape)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            sh = np.roll(np.roll(have, dy, 0), dx, 1)
            acc += np.roll(np.roll(out * have[..., None], dy, 0), dx, 1)
            cnt += sh
        grow = (~have) & (cnt > 0)
        out[grow] = acc[grow] / cnt[grow][:, None]
        have = have | grow
    return out


def area_down(master, k=K):
    h, w = master.shape[0] // k, master.shape[1] // k
    return master.reshape(h, k, w, k, -1).mean(axis=(1, 3))


def smooth_table(xs, values, width=2):
    out = np.array(values, np.float64)
    for _ in range(width):
        out = np.convolve(np.pad(out, 1, mode='edge'), np.ones(3) / 3, mode='valid')
    return out


# --- emblems ---------------------------------------------------------------------------------------------------------

def shield_mask(u, v):
    """The NFL shield silhouette in its own unit box (u, v in 0..1, v down): 1 inside."""
    top = 0.12 + 0.10 * np.abs(np.cos(np.pi * (u - 0.5) * 2.0))      # the notched top edge
    body = (v >= top) & (u >= 0.04) & (u <= 0.96)
    taper = v > 0.62
    half = np.where(taper, 0.46 * np.sqrt(np.clip(1.0 - (v - 0.62) / 0.38, 0.0, 1.0)), 0.46)
    return body & (np.abs(u - 0.5) <= half) & (v <= 1.0)


def shield_colour(u, v):
    """RGB of the shield at (u, v): silver rim, navy border, navy top field with white stars and football, white lower
    field with red NFL letters. ``None`` outside."""
    inside = shield_mask(u, v)
    inner = shield_mask(0.5 + (u - 0.5) / 0.84, 0.10 + (v - 0.10) / 0.86)
    core = shield_mask(0.5 + (u - 0.5) / 0.74, 0.16 + (v - 0.16) / 0.78)
    col = np.zeros(u.shape + (3,))
    col[...] = SHIELD_SILVER
    col[inner] = NAVY
    upper = core & (v < 0.44)
    lower = core & (v >= 0.44)
    col[upper] = NAVY
    col[lower] = WHITE
    ball = upper & (((u - 0.5) / 0.07) ** 2 + ((v - 0.30) / 0.11) ** 2 <= 1.0)
    col[ball] = WHITE
    for su in (0.26, 0.36, 0.64, 0.74):
        for sv in (0.25, 0.36):
            star = upper & (((u - su) / 0.035) ** 2 + ((v - sv) / 0.035) ** 2 <= 1.0)
            col[star] = WHITE
    # N F L as three red block letters
    letters = lower & (v > 0.50) & (v < 0.80)
    ln = letters & (((u > 0.24) & (u < 0.29)) | ((u > 0.37) & (u < 0.42)) | ((u >= 0.29) & (u <= 0.37) & (np.abs((v - 0.50) / 0.30 - (u - 0.29) / 0.08) < 0.28)))
    lf = letters & (((u > 0.46) & (u < 0.51)) | ((u >= 0.51) & (u < 0.59) & ((v < 0.56) | ((v > 0.62) & (v < 0.68)))))
    ll = letters & (((u > 0.62) & (u < 0.67)) | ((u >= 0.67) & (u < 0.77) & (v > 0.74)))
    col[ln | lf | ll] = RED
    return col, inside


def stamp_shield(rgb, cover, pos, centre, normal_axis, width, height, up_axis=1, right_sign=1.0):
    """Paint the shield on the surface: ``centre`` (x, y, z) cm; the shield is projected along ``normal_axis``
    (2 for the front of the body); ``right_sign`` flips the horizontal so the emblem reads right way round."""
    cx, cy, cz = centre
    h_axis = 0 if normal_axis == 2 else 2
    u = 0.5 + right_sign * (pos[..., h_axis] - (cx if h_axis == 0 else cz)) / width
    v = 0.5 - (pos[..., up_axis] - cy) / height
    near = np.abs(pos[..., normal_axis] - centre[normal_axis]) < 6.0
    col, inside = shield_colour(u, v)
    sel = inside & near & cover
    rgb[sel] = col[sel]
    return sel


# --- the shirt -------------------------------------------------------------------------------------------------------

def torso_tables(prims):
    """Per height (1 cm steps): the torso cross-section ellipse (a = half width, b = half depth, cz = centre z)."""
    sh = [p for p in prims if p['mesh'] == 'ref_high' and p['material'] == 'shirt'][0]
    P = sh['pos'][sh['used']]
    J = sh['joint'][sh['used']]
    P = P[np.isin(J, TORSO_J)]
    ys = np.arange(-25, 72)
    a, b, cz = [], [], []
    for y in ys:
        q = P[np.abs(P[:, 1] - y) <= 4.0]
        if len(q) < 4:
            a.append(np.nan); b.append(np.nan); cz.append(np.nan)
            continue
        a.append(np.abs(q[:, 0]).max())
        b.append((q[:, 2].max() - q[:, 2].min()) / 2)
        cz.append((q[:, 2].max() + q[:, 2].min()) / 2)
    out = []
    for arr in (a, b, cz):
        arr = np.array(arr)
        good = ~np.isnan(arr)
        arr = np.interp(ys, ys[good], arr[good])
        out.append(smooth_table(ys, arr, 3))
    return ys, out[0], out[1], out[2]


def paint_shirt(prims, size=256 * K, meshes=('ref_high', 'ref_low')):
    m = uvmap(prims, 'shirt', size, meshes)
    P, N, J, C = m['pos'], m['nrm'], m['joint'], m['cover']
    rgb = np.zeros(P.shape)
    rgb[...] = BLACK
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    ys, A, B, CZ = torso_tables(prims)

    foot = C & ((y < -88) | np.isin(J, FOOT_J))
    arm = C & ~foot & (np.abs(x) > 20.5) & (y > 30)
    torso = C & ~foot & ~arm

    # torso: straight vertical stripes in x on the front and the back, black side panels under the arms
    idx = np.nonzero(torso)
    ty, tx, tz = y[idx], x[idx], z[idx]
    a = np.interp(ty, ys, A)
    cz = np.interp(ty, ys, CZ)
    ax_ = np.abs(tx)
    front = tz >= cz
    back = ~front
    P_, w = STRIPE_PERIOD, STRIPE_WIDTH
    side_start = 2 * P_ - w / 2
    black = np.zeros(len(ty), bool)
    # front: centre placket, one black stripe each side, the side panel; above the chest the stripe flares out and
    # widens and the side panel climbs over the shoulder, so the outer white stripe ends in a point (the yoke)
    f = np.clip((ty - 40.0) / (62.0 - 40.0), 0.0, 1.0)
    black |= front & (ax_ <= w / 2 * (1.0 - 0.1 * f))
    black |= front & (np.abs(ax_ - P_ * (1.0 + 0.25 * f)) <= w * (1.0 + 1.2 * f) / 2)
    black |= front & (ax_ >= side_start - 4.5 * f)
    black |= front & (ty > 58.5) & (ax_ > 9.0)
    black |= front & (ty > 59.5)                    # under the collar flaps: the stripes end at the collar seam
    # back: stripes below the number panel, a clear white panel, the centre stripe up to the collar, the yoke
    panel_lo, panel_hi = 31.5, 52.0
    below = back & (ty < panel_lo)
    black |= below & ((ax_ <= w / 2) | (np.abs(ax_ - P_) <= w / 2))
    black |= back & (ax_ >= side_start)
    above = back & (ty > panel_hi)
    black |= above & (ax_ <= w * 0.45)
    g = np.clip((ty - panel_hi) / (64.0 - panel_hi), 0.0, 1.0)
    black |= above & (ax_ >= side_start - (side_start - 7.5) * g)
    # collar: the neck band
    black |= ty > 61.0
    rgb[idx] = np.where(black[:, None], BLACK[None, :], WHITE[None, :])

    # sleeves: black, one white stripe down the outer front of the arm (from the surface normal round the arm:
    # 0 = top of the T-posed arm = the outside of a hanging arm, +90 = front), black cuff
    idx = np.nonzero(arm)
    ax2 = np.abs(x[idx])
    phi = np.degrees(np.arctan2(N[..., 2][idx], N[..., 1][idx]))
    stripe = (np.abs(phi - SLEEVE_STRIPE_DEG) <= SLEEVE_STRIPE_HALF) & (ax2 < 61.5) & (ax2 > 21.0)
    rgb[idx] = np.where(stripe[:, None], WHITE[None, :], BLACK[None, :])

    # shoes: black upper, dark sole, a white midsole line
    idx = np.nonzero(foot)
    fy = y[idx]
    sole_top = -106.8
    shoe = np.where(fy[:, None] < sole_top - 1.8, np.array([(34, 34, 36)]), BLACK[None, :] * 0.85)
    shoe = np.where(((fy >= sole_top - 1.8) & (fy < sole_top))[:, None], np.array([(226, 226, 222)]), shoe)
    rgb[idx] = shoe

    # the NFL shield on the wearer's left chest, on the black stripe below the shoulder
    stamp_shield(rgb, torso, P, (LEFT * 15.5, 41.0, 14.0), 2, 4.2, 5.0, right_sign=LEFT)

    # a little cloth shading: the creases where the shirt tucks in and under the arms
    shade = np.ones(P.shape[:2])
    shade[torso] *= 1.0 - 0.10 * np.clip((16.0 - y[torso]) / 6.0, 0.0, 1.0)
    rgba = np.concatenate([rgb * shade[..., None], np.full(P.shape[:2] + (1,), 255.0)], -1)
    return dilate(rgba, C), m


# --- the pants -------------------------------------------------------------------------------------------------------

def leg_tables(prims):
    pa = [p for p in prims if p['mesh'] == 'ref_high' and p['material'] == 'pants'][0]
    P = pa['pos'][pa['used']]
    P = P[P[:, 1] < 20]
    ys = np.arange(-102, 20)
    out = {}
    for side in (1.0, -1.0):
        Q = P[np.sign(P[:, 0]) == side]
        cx, cz, r = [], [], []
        for y in ys:
            q = Q[np.abs(Q[:, 1] - y) <= 3.0]
            if len(q) < 3:
                cx.append(np.nan); cz.append(np.nan); r.append(np.nan)
                continue
            cx.append((q[:, 0].max() + q[:, 0].min()) / 2)
            cz.append((q[:, 2].max() + q[:, 2].min()) / 2)
            r.append(((q[:, 0].max() - q[:, 0].min()) + (q[:, 2].max() - q[:, 2].min())) / 4)
        tabs = []
        for arr in (cx, cz, r):
            arr = np.array(arr)
            good = ~np.isnan(arr)
            tabs.append(smooth_table(ys, np.interp(ys, ys[good], arr[good]), 12))
        out[side] = tabs
    return ys, out


def paint_pants(prims, size=256 * K, meshes=('ref_high', 'ref_low')):
    m = uvmap(prims, 'pants', size, meshes)
    P, N, J, C = m['pos'], m['nrm'], m['joint'], m['cover']
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    rgb = np.zeros(P.shape)
    rgb[...] = PANTS_BLACK
    ys, tabs = leg_tables(prims)
    legs = C & (y < 9.6)
    idx = np.nonzero(legs)
    lx, ly, lz = x[idx], y[idx], z[idx]
    side = np.where(lx >= 0, 1.0, -1.0)
    cx = np.where(side > 0, np.interp(ly, ys, tabs[1.0][0]), np.interp(ly, ys, tabs[-1.0][0]))
    cz = np.where(side > 0, np.interp(ly, ys, tabs[1.0][1]), np.interp(ly, ys, tabs[-1.0][1]))
    r = np.where(side > 0, np.interp(ly, ys, tabs[1.0][2]), np.interp(ly, ys, tabs[-1.0][2]))
    # the stripe runs straight down the outside of the leg: the leg's mid depth fitted as a straight line in y
    line = {}
    for sd in (1.0, -1.0):
        keep = (ys > -97) & (ys < 8)
        line[sd] = np.polyfit(ys[keep], tabs[sd][1][keep], 1)
    zl = np.where(side > 0, np.polyval(line[1.0], ly), np.polyval(line[-1.0], ly))
    stripe = (np.abs(lz - zl) <= PANTS_STRIPE / 2) & ((lx - cx) * side > 0) & (N[..., 0][idx] * side > 0.25)
    rgb[idx] = np.where(stripe[:, None], WHITE[None, :] * 0.97, PANTS_BLACK[None, :])
    # belt and buckle
    belt = C & (y >= 9.6)
    rgb[belt] = BELT
    buckle = belt & (np.abs(x) < 2.6) & (z > 0) & (y > 10.0) & (y < 13.2)
    rgb[buckle] = SILVER
    inner = buckle & (np.abs(x) < 1.6) & (y > 10.8) & (y < 12.4)
    rgb[inner] = BELT * 1.6
    # the NFL shield on the wearer's right hip, below the belt
    stamp_shield(rgb, legs, P, (-LEFT * 12.5, 3.0, 13.0), 2, 3.4, 4.0, right_sign=LEFT)
    rgba = np.concatenate([rgb, np.full(P.shape[:2] + (1,), 255.0)], -1)
    return dilate(rgba, C), m


# --- the caps --------------------------------------------------------------------------------------------------------

def _island(prims, material, mesh, size, keep):
    """Mask of the texels the given triangles of one mesh cover (repeat addressing)."""
    sub = []
    for p in prims:
        if p['material'] == material and p['mesh'] == mesh:
            tris = np.array([t for t in p['tris'] if keep(p, t)], int).reshape(-1, 3)
            sub.append(dict(p, tris=tris, mesh='island'))
    return uvmap(sub, material, size, meshes=('island',))['cover']


def paint_hats(prims, size=64 * K):
    """(white, black) masters with identical structure (the two caps share one index image and differ by palette).
    All six crown panels of the cap share one UV island, so a front emblem would repeat on every panel: the caps carry
    no emblem. The black cap has white piping on the panel seams (the island's side and top edges)."""
    from scipy import ndimage
    mh = uvmap(prims, 'hat', size, ('ref_high',))
    ml = uvmap(prims, 'hat', size, ('ref_low',))
    C = mh['cover'] | ml['cover']
    brim_v = set(range(1423, 1433))
    crown = _island(prims, 'hat', 'ref_high', size,
                    lambda p, t: not (set(p['game'][t].tolist()) & brim_v))
    dist = ndimage.distance_transform_edt(crown)
    v = (np.arange(size) + 0.5)[:, None] / size * np.ones((1, size))
    seam = crown & (dist <= 1.25 * K) & (v < 0.685)
    white = np.zeros((size, size, 3))
    black = np.zeros((size, size, 3))
    white[...] = (240, 240, 238)
    black[...] = (22, 22, 24)
    white[seam] = (224, 224, 222)
    black[seam] = (230, 230, 228)
    rgba_w = np.concatenate([white, np.full((size, size, 1), 255.0)], -1)
    rgba_b = np.concatenate([black, np.full((size, size, 1), 255.0)], -1)
    return dilate(rgba_w, C), dilate(rgba_b, C), mh


# --- the numbers ------------------------------------------------------------------------------------------------------

ROLES = (('ref_R', 'R', '34'), ('ref_U', 'U', '40'), ('ref_HL', 'DJ', '26'), ('ref_LJ', 'LJ', '66'),
         ('ref_FJ', 'FJ', '22'), ('ref_SJ', 'SJ', '97'), ('ref_BJ', 'BJ', '6'))
# the back patch (ref_high): v = 0.452 + (49.6 - y) * 0.02744, u = 0.499 - x * 0.0312 (y, x in cm on the body)
CLEAR_ROWS = 51
# body heights (cm) of the role letters and the number on the back (REF: letter about half the number's height)
LETTER_TOP, LETTER_BOTTOM = 48.6, 44.6
NUMBER_TOP, NUMBER_BOTTOM = 43.2, 35.6


def _v(y):
    return 0.452 + (49.6 - y) * 0.02744


def paint_numbers(letters, number, font, size=128 * K):
    """Black role letters above the number on a clear texture. The back patch maps the body at 0.0312 u and
    0.02744 v per centimetre, so glyphs are laid out in body centimetres and then mapped."""
    from PIL import Image, ImageDraw, ImageFont
    img = np.zeros((size, size, 4), np.float64)
    per_cm_u, per_cm_v = 0.0312 * size, 0.02744 * size
    for text, y_top, y_bot, widen in ((letters, LETTER_TOP, LETTER_BOTTOM, 1.0), (number, NUMBER_TOP, NUMBER_BOTTOM, 1.12)):
        big = 512
        f = ImageFont.truetype(font, big)
        canvas = Image.new('L', (big * 4, int(big * 1.6)), 0)
        ImageDraw.Draw(canvas).text((big // 4, 0), text, font=f, fill=255)
        arr = np.asarray(canvas)
        ys_, xs_ = np.nonzero(arr > 0)
        glyph = canvas.crop((xs_.min(), ys_.min(), xs_.max() + 1, ys_.max() + 1))
        gw, gh = glyph.size
        height_cm = y_top - y_bot
        width_cm = height_cm * gw / gh * widen
        tw, th = width_cm * per_cm_u, height_cm * per_cm_v
        glyph = glyph.resize((max(1, int(round(tw))), max(1, int(round(th)))), Image.LANCZOS)
        g = np.asarray(glyph, np.float64)
        x0 = int(round(0.499 * size - g.shape[1] / 2))
        y0 = int(round(_v(y_top) * size))
        region = img[y0:y0 + g.shape[0], x0:x0 + g.shape[1], 3]
        img[y0:y0 + g.shape[0], x0:x0 + g.shape[1], 3] = np.maximum(region, g)
    img[..., :3] = 12.0                        # black ink; clear texels are black too (no light fringe)
    img[:CLEAR_ROWS * K, :, 3] = 0
    return img


# --- output ----------------------------------------------------------------------------------------------------------

def save(arr, path):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    a = np.clip(np.rint(arr), 0, 255).astype(np.uint8)
    Image.fromarray(a, 'RGBA' if a.shape[-1] == 4 else 'RGB').save(path, optimize=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--gltf', type=Path, required=True)
    ap.add_argument('--masters', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--font', default='/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf')
    ap.add_argument('--only', default='shirt,pants,hats,numbers')
    a = ap.parse_args(argv)
    prims = load_gltf(a.gltf)
    only = set(a.only.split(','))
    if 'shirt' in only:
        master, _m = paint_shirt(prims)
        save(master, a.masters / 'shirt.png')
        native = area_down(master)
        r, c = int(COLLAR_UV[1] * 256), int(COLLAR_UV[0] * 256)
        assert native[r - 6:r + 7, c - 6:c + 7, :3].max() < 60, 'the collar texel is not inside a black area'
        save(native, a.out / 'shirt.png')
    if 'pants' in only:
        master, _m = paint_pants(prims)
        save(master, a.masters / 'pants.png')
        save(area_down(master), a.out / 'pants.png')
    if 'hats' in only:
        white, black, _m = paint_hats(prims)
        save(white, a.masters / 'hat_white.png')
        save(black, a.masters / 'hat_black.png')
        save(area_down(white), a.out / 'hat_white.png')
        save(area_down(black), a.out / 'hat_black.png')
    if 'numbers' in only:
        for name, letters, number in ROLES:
            master = paint_numbers(letters, number, a.font)
            save(master, a.masters / 'numbers' / f'{name}.png')
            save(area_down(master), a.out / 'numbers' / f'{name}.png')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
