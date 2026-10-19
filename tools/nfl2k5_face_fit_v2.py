#!/usr/bin/env python3
"""Face fit v2 (job fx, 2026-09-24): 2026 player faces that sit on the 3D head the way retail's do.

u1's first 2026 faces pasted the headshot onto the face texture with a flat similarity warp to landmark positions
measured by a face detector on unwrapped retail textures. Those positions are wrong for the head mesh (the eyes land
on the inner eye corners, the mouth on the upper lip, the photo about 20% small), and the photo keeps its studio
light and its smile, so at the coin toss the faces read as masks with painted teeth. This module rebuilds them:

1. the retail ``hi_head`` (a Models export, glTF) is rasterised into texture space, so every face texel knows its 3D
   point and normal; the head's own features (eye openings, nose tip, lip line and corners) are measured on the mesh;
2. a weak-perspective camera is fitted from the head's features to the headshot's five YuNet landmarks, every texel
   is projected into the photo (with an occlusion test and a facing weight), and a smooth residual field puts each
   photo feature exactly on the mesh's;
3. the photo is relit: its skin-only low-frequency light is swapped for the template's (the retail face nearest in
   skin and hair) and its fine detail and studio highlights are toned down to retail's levels;
4. open mouths get the template's closed lips (in the player's skin), the player's moustache and goatee stay on top,
   the template's own facial hair is removed, and the beard continues under the jaw with its own strands;
5. the skin colour is the photo's diffuse skin under a calibrated exposure (studio photos are brighter than the
   game's albedo), kept inside retail's spread for the player's roster skin tone, so the face matches the arms;
6. face (f, h) and skull (n) share one skin and hair mapping, so there is no band at the hairline and no teal hair.

A photo that fails the checks (detector score, head turn, fit residual, coverage) falls back to method B (the
template re-skinned with only the photo's beard and brows) or C (the template as it is). Everything is authored at 4x
(1024) and area-downscaled to 256; ``nfl2k5_team_2026_faces.py fit`` then fits h and n into their slots' spans.
Headshots and outputs are private inputs: keep them off the repository.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.optimize import least_squares


CT = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8, 5122: np.int16, 5120: np.int8}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class Gltf:
    def __init__(self, path):
        self.path = Path(path)
        self.g = json.loads(self.path.read_text())
        self.bufs = [(self.path.parent / b["uri"]).read_bytes() for b in self.g["buffers"]]

    def acc(self, i):
        ac = self.g["accessors"][i]
        bv = self.g["bufferViews"][ac["bufferView"]]
        dt = np.dtype(CT[ac["componentType"]])
        n = NC[ac["type"]]
        off = bv.get("byteOffset", 0) + ac.get("byteOffset", 0)
        stride = bv.get("byteStride", dt.itemsize * n)
        raw = np.frombuffer(self.bufs[bv["buffer"]], np.uint8, count=stride * (ac["count"] - 1) + dt.itemsize * n, offset=off)
        if stride == dt.itemsize * n:
            out = raw.view(dt).reshape(ac["count"], n)
        else:
            out = np.stack([raw[k * stride:k * stride + dt.itemsize * n].view(dt) for k in range(ac["count"])])
        out = out.astype(np.float64)
        if ac.get("normalized"):
            out /= float(np.iinfo(dt).max)
        return out


def strip_to_tris(idx):
    tris = []
    for k in range(len(idx) - 2):
        a, b, c = idx[k], idx[k + 1], idx[k + 2]
        if a == b or b == c or a == c:
            continue
        tris.append((a, b, c) if k % 2 == 0 else (b, a, c))
    return np.array(tris, np.int64).reshape(-1, 3)


class HeadMesh:
    def __init__(self, gltf_path):
        G = Gltf(gltf_path)
        g = G.g
        self.materials = [m.get("name", "") for m in g["materials"]]
        mesh = g["meshes"][0]
        p0 = mesh["primitives"][0]["attributes"]
        self.pos = G.acc(p0["POSITION"])
        self.nrm = G.acc(p0["NORMAL"])
        self.uv = G.acc(p0["TEXCOORD_0"])
        self.joints = G.acc(p0["JOINTS_0"]).astype(int) if "JOINTS_0" in p0 else None
        self.weights = G.acc(p0["WEIGHTS_0"]) if "WEIGHTS_0" in p0 else None
        self.tris = {}
        for p in mesh["primitives"]:
            name = self.materials[p["material"]]
            idx = G.acc(p["indices"]).astype(np.int64).ravel()
            mode = p.get("mode", 4)
            t = idx.reshape(-1, 3) if mode == 4 else strip_to_tris(idx)
            self.tris.setdefault(name, []).append(t)
        self.tris = {k: np.concatenate(v) for k, v in self.tris.items()}
        skin = g["skins"][0] if g.get("skins") else None
        self.joint_names = [g["nodes"][j]["name"].split(":")[-1] for j in skin["joints"]] if skin else []
        self.g = g



# mesh landmarks (PROVED OFFLINE from the mesh: eye-opening rings, nose tip vertex, lip-line corner vertices), in
# texture pixels at 256 and in centimetres (the head's own space)
UV_EYES = np.array([[84.9, 54.8], [170.5, 52.8]])
UV_NOSE = np.array([128.0, 98.9])
UV_MOUTH = np.array([[100.9, 145.7], [155.1, 145.7]])
UV_LIPLINE_Y = 145.0
P_EYES = np.array([[-3.28, 41.08, 18.9], [3.28, 41.08, 18.9]])      # front of the eyeballs (pupils)
P_NOSE = np.array([0.0, 37.09, 22.13])
P_MOUTH = np.array([[-2.5, 33.2, 19.4], [2.5, 33.2, 19.4]])


def atlas_uv(uv):
    return (uv[..., 1] > 0.77) & (uv[..., 0] < 0.53)


def skin_triangles(h):
    t = h.tris['SKIN_face']
    uv = h.uv[t]
    keep = ~atlas_uv(uv % 1.0).all(axis=1)
    t = t[keep]
    # the inner lip (its u is stored one repeat to the left) shares texels with the outer lower lip: draw it first
    # so the outer, visible surface wins
    inner = (h.uv[t][:, :, 0] < 0).all(axis=1)
    return np.concatenate([t[inner], t[~inner]])


def raster(h, size=1024):
    """pos (S,S,3) cm, nrm (S,S,3), cov (S,S) bool."""
    S = size
    pos = np.zeros((S, S, 3), np.float32); nrm = np.zeros((S, S, 3), np.float32); cov = np.zeros((S, S), bool)
    for tri in skin_triangles(h):
        uv = h.uv[tri].copy()
        if (uv[:, 0] < 0).all():
            uv[:, 0] += 1.0
        xs, ys = uv[:, 0] * S, uv[:, 1] * S
        x0, x1 = int(max(0, np.floor(xs.min()))), int(min(S - 1, np.ceil(xs.max())))
        y0, y1 = int(max(0, np.floor(ys.min()))), int(min(S - 1, np.ceil(ys.max())))
        (ax, ay), (bx, by), (cx, cy) = zip(xs, ys)
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
        w1 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
        w2 = 1 - w0 - w1
        m = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
        if not m.any():
            continue
        P = w0[..., None] * h.pos[tri[0]] + w1[..., None] * h.pos[tri[1]] + w2[..., None] * h.pos[tri[2]]
        N = w0[..., None] * h.nrm[tri[0]] + w1[..., None] * h.nrm[tri[1]] + w2[..., None] * h.nrm[tri[2]]
        sub = cov[y0:y1 + 1, x0:x1 + 1]
        pos[y0:y1 + 1, x0:x1 + 1][m] = P[m]
        nrm[y0:y1 + 1, x0:x1 + 1][m] = N[m]
        sub[m] = True
    nrm /= np.maximum(np.linalg.norm(nrm, axis=2, keepdims=True), 1e-9)
    return pos, nrm, cov



S = 1024
K = S / 256.0
_R = None


def use_head(gltf_path) -> None:
    """Load the retail hi_head (a Models export) and rasterise its face surface into texture space."""
    global _R, _OPENINGS, _SYNTH_EYE
    _R = raster(HeadMesh(gltf_path), S)
    _OPENINGS = _SYNTH_EYE = None


def uvr():
    if _R is None:
        raise RuntimeError("call use_head(<hi_head glTF>) first")
    return _R


YY, XX = np.mgrid[0:S, 0:S].astype(np.float32)


def ellipse(cx, cy, rx, ry, feather):
    d = np.sqrt(((XX - cx * K) / (rx * K)) ** 2 + ((YY - cy * K) / (ry * K)) ** 2)
    return np.clip((1.0 - d) * (min(rx, ry) * K) / (feather * K) + 0.5, 0, 1)


def rot(rx, ry, rz):
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def project(params, X):
    s, rx, ry, rz, tx, ty, ay = params
    Y = X @ rot(rx, ry, rz).T
    return np.stack([s * Y[..., 0] + tx, -s * ay * Y[..., 1] + ty], -1), Y


def fit_camera(pts):
    """pts: YuNet order (image-left eye, image-right eye, nose, image-left mouth corner, image-right mouth corner)."""
    P3 = np.array([P_EYES[0], P_EYES[1], P_NOSE, P_MOUTH[0], P_MOUTH[1]])
    eye_d = float(np.linalg.norm(pts[1] - pts[0]))
    s0 = eye_d / 6.56
    mid = (pts[0] + pts[1]) / 2
    x0 = np.array([s0, 0.0, 0.0, 0.0, mid[0], mid[1] + s0 * 41.08, 1.0])
    # the eyes decide scale and position; the mouth line decides the vertical scale; the mouth corners barely count
    # (a smile widens them), the nose tip mostly decides the head's turn and tilt
    wx = np.array([3.0, 3.0, 0.8, 0.25, 0.25]); wy = np.array([3.0, 3.0, 0.8, 1.2, 1.2])

    def res(p):
        q, _ = project(p, P3)
        r = q - pts
        prior = [(p[6] - 1.0) * 2.0, p[1] * 1.5, p[2] * 1.5, p[3] * 1.5]   # stay near a frontal, even-scaled camera
        return np.concatenate([r[:, 0] * wx / eye_d, r[:, 1] * wy / eye_d, prior])
    sol = least_squares(res, x0, x_scale=[s0, 0.3, 0.3, 0.3, eye_d, eye_d, 0.2])
    q, _ = project(sol.x, P3)
    return sol.x, pts - q


def rbf_field(uv_pts, vals, sigma):
    d2 = ((uv_pts[:, None, :] - uv_pts[None, :, :]) ** 2).sum(-1)
    Phi = np.exp(-d2 / (2 * sigma ** 2)) + 1e-6 * np.eye(len(uv_pts))
    w = np.linalg.solve(Phi, vals)
    out = np.zeros((S, S, vals.shape[1]), np.float32)
    for (u, v), wi in zip(uv_pts, w):
        g = np.exp(-(((XX - u) ** 2 + (YY - v) ** 2) / (2 * sigma ** 2)))
        out += g[..., None] * wi
    return out


def lab(rgb_u8):
    return cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2LAB).astype(np.float32)


def rgb(lab_f):
    return cv2.cvtColor(np.clip(lab_f, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)


def normconv(img, mask, sigma):
    """Skin-only low-pass: a Gaussian of the masked image over the Gaussian of the mask, falling back to wider
    Gaussians (then the global mean) where the mask is thin. Computed at a quarter of the size (it is smooth)."""
    h, w_ = mask.shape
    q = 4
    small = cv2.resize(img, (w_ // q, h // q), interpolation=cv2.INTER_AREA)
    m = cv2.resize(mask.astype(np.float32), (w_ // q, h // q), interpolation=cv2.INTER_AREA)
    glob_mean = img[mask].mean(axis=0) if mask.any() else img.reshape(-1, img.shape[-1]).mean(axis=0)
    out, c_acc = None, None
    for f in (1, 2, 4):
        sg = sigma * f / q
        num = cv2.GaussianBlur(small * m[..., None], (0, 0), sg)
        den = cv2.GaussianBlur(m, (0, 0), sg)[..., None]
        est = num / np.maximum(den, 1e-6)
        conf = np.clip(den / 0.25, 0, 1)
        if out is None:
            out, c_acc = est * conf, conf
        else:
            add = (1 - c_acc) * conf
            out, c_acc = out + est * add, c_acc + add
    out = out + (1 - c_acc) * glob_mean[None, None, :]
    return cv2.resize(out, (w_, h), interpolation=cv2.INTER_CUBIC)


def load_rgb(path, size=S):
    return np.asarray(Image.open(path).convert('RGB').resize((size, size), Image.LANCZOS), np.uint8)


# zones in texture space (256 px units): eye-opening rings, lips, the atlas block
def zones():
    eyes = np.maximum(ellipse(UV_EYES[0][0], UV_EYES[0][1], 21, 10, 3), ellipse(UV_EYES[1][0], UV_EYES[1][1], 21, 10, 3))
    lips = ellipse(128, UV_LIPLINE_Y + 1, 31, 12.5, 4)
    atlas = np.zeros((S, S), np.float32); atlas[int(0.77 * S):, :int(0.53 * S)] = 1
    return eyes, lips, atlas


def bake(photo_rgba, pts, opts):
    """The headshot projected into texture space: colour (S,S,3) uint8 and weight (S,S)."""
    pos, nrm, cov = uvr()
    params, resid = fit_camera(pts)
    if opts.get('eye_shift') is not None:
        # fc1: each eye's residual moved by the photo-space shift eye_shift() measured, so the photo's own eye (not
        # the detector's eye point, which sits on the upper lid) lands in the mesh's eye opening
        resid = resid + np.vstack([np.asarray(opts['eye_shift'], np.float64), np.zeros((3, 2))])
    uv_l = np.array([UV_EYES[0], UV_EYES[1], UV_NOSE, UV_MOUTH[0], UV_MOUTH[1]]) * K
    field = rbf_field(uv_l, resid.astype(np.float32), sigma=opts.get('rbf_sigma', 28) * K)
    q, Y = project(params, pos)
    q = q + field
    R = rot(*params[1:4])
    n_cam = nrm @ R.T
    facing = n_cam[..., 2]
    # occlusion: the camera-space depth of every covered texel splatted into a coarse photo-space z-buffer
    cell = max(2.0, params[0] * 0.25)
    gx = np.floor(q[..., 0] / cell).astype(np.int64); gy = np.floor(q[..., 1] / cell).astype(np.int64)
    ok = cov & (gx >= 0) & (gy >= 0)
    W_, H_ = int(gx[ok].max()) + 2, int(gy[ok].max()) + 2
    zb = np.full((H_, W_), -1e9, np.float32)
    np.maximum.at(zb, (gy[ok], gx[ok]), Y[..., 2][ok])
    zb = ndimage.maximum_filter(zb, size=2)
    vis = np.zeros((S, S), bool)
    vis[ok] = Y[..., 2][ok] >= zb[gy[ok], gx[ok]] - 0.6
    ph = photo_rgba[..., :3].astype(np.float32)
    al = photo_rgba[..., 3].astype(np.float32) / 255.0
    mx, my = q[..., 0].astype(np.float32), q[..., 1].astype(np.float32)
    col = cv2.remap(ph, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    alpha = cv2.remap(al, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    w = np.clip((facing - 0.18) / 0.35, 0, 1) * np.clip((alpha - 0.5) / 0.4, 0, 1) * cov * vis
    # the forehead top keeps the template's hairline; the chin and jaw stay the photo's
    top = np.clip((YY / K - opts.get('top_fade0', 12.0)) / opts.get('top_fade', 16.0), 0, 1)
    bottom = np.clip((opts.get('chin_v', 206.0) - YY / K) / 10.0, 0, 1)
    w = w * top * bottom
    w = cv2.GaussianBlur(w.astype(np.float32), (0, 0), 1.5 * K)
    return np.clip(col, 0, 255).astype(np.uint8), w, dict(params=params.tolist(), resid=resid.tolist())


# --------------------------------------------------------------------------------------------- eyes (fc1, 2026-10-18)
# Noah (b775 test, 10/18): the custom faces "put an eye over an eye". Cause (PROVED OFFLINE): YuNet's eye points on
# the league's headshots sit on the upper eyelid, above the pupil, and the fit pinned them onto the centre of the
# mesh's eye opening, so the photo's eye was drawn about 1.5 game texels low (p95 5.6, some photos 2.5 high) against
# an opening about 11 texels tall: the photo's lower lid, lash line and the bottom of its sclera landed on the lid
# skin under the 3D eyeball (SKIN_eyegloss, textured from the atlas), and the 70% template ring left a 30% ghost.
# The fix: measure where the photo's eye really is (the photo projected into texture space, both eyes registered
# against a reference eye that sits on the openings), shift the eyes' residuals by it, fill the openings with the
# template's eye (hidden at full size, seen through the mip levels), keep the template's lid only on a thin rim,
# hand any photo sclera left on the lids back to the template, and give the eyeball the iris colour of the
# player's eyes.
_OPENINGS = None
_SYNTH_EYE = None
_EYE_REF = None
EYE_DY_MEDIAN = 1.5          # the league's median photo-eye offset (game texels, positive = drawn low), the fallback
EYE_DY_MAX = 12.0            # a larger registered offset is a failed match
EYE_NCC_MIN = 0.2            # and so is a weaker correlation
# the eyeball's texture square in the atlas (SKIN_eyegloss uv: u 0.005-0.128, v 0.774-0.867), as fractions of S
EYE_PATCH = (0.770, 0.871, 0.0, 0.132)


def eye_openings():
    """The two eye openings of the face surface in texture space: per eye the texels (at S) the SKIN_face mesh does
    not cover around UV_EYES, its box, and its centre (between the rims' medians over the middle 60%)."""
    global _OPENINGS
    if _OPENINGS is None:
        _pos, _nrm, cov = uvr()
        out = []
        for cx, cy in UV_EYES:
            box = np.zeros((S, S), bool)
            box[int((cy - 14) * K):int((cy + 14) * K), int((cx - 26) * K):int((cx + 26) * K)] = True
            sub = box & ~cov
            lab_, n = ndimage.label(sub)
            sizes = ndimage.sum(sub, lab_, range(1, n + 1))
            m = lab_ == (1 + int(np.argmax(sizes)))
            yy, xx = np.nonzero(m)
            x0, x1 = int(xx.min()), int(xx.max())
            mid = (xx > x0 + 0.2 * (x1 - x0)) & (xx < x1 - 0.2 * (x1 - x0))
            tops = [yy[mid & (xx == x)].min() for x in np.unique(xx[mid])]
            bots = [yy[mid & (xx == x)].max() for x in np.unique(xx[mid])]
            out.append({"mask": m, "x0": x0, "x1": x1, "y0": int(yy.min()), "y1": int(yy.max()),
                        "cx": (x0 + x1) / 2.0, "cy": (float(np.median(tops)) + float(np.median(bots))) / 2.0})
        _OPENINGS = out
    return _OPENINGS


def _eye_region():
    m = np.zeros((S, S), bool)
    m[int(28 * K):int(84 * K), int(52 * K):int(206 * K)] = True
    return m


def fill_openings(q):
    """q (S,S,2): the texels of the eye region the mesh does not cover (the openings and the lid seam) get a linear
    interpolation of the covered texels around them, so the photo can be looked at inside the openings."""
    from scipy.interpolate import griddata
    _pos, _nrm, cov = uvr()
    q = q.copy()
    tgt = _eye_region() & ~cov
    ring = ndimage.binary_dilation(tgt, iterations=int(3 * K)) & ~tgt & cov
    ys, xs = np.nonzero(ring)
    yh, xh = np.nonzero(tgt)
    for c in range(q.shape[2]):
        vals = griddata((xs, ys), q[ys, xs, c], (xh, yh), method="linear")
        bad = np.isnan(vals)
        if bad.any():
            vals[bad] = griddata((xs, ys), q[ys, xs, c], (xh[bad], yh[bad]), method="nearest")
        q[yh, xh, c] = vals
    return q


def _norm_band(L):
    band = L[int(37.5 * K):int(75 * K), int(50 * K):int(205 * K)]
    return (L - np.median(band)) / (band.std() + 1e-3)


def eye_reference_from(retail_faces: Path, ids=None) -> np.ndarray:
    """The reference eye: the mean of retail's alternate faces (h), each normalised over the eye band. Retail paints
    its eyes on the openings, so the mean is sharp and sits on them. Computed from the user's own retail textures."""
    paths = sorted(Path(retail_faces).glob("h*.png")) if ids is None else [Path(retail_faces) / f"h{i}.png" for i in ids]
    acc, n = np.zeros((S, S), np.float64), 0
    for p in paths:
        if not p.is_file():
            continue
        a = np.asarray(Image.open(p).convert("RGB").resize((S, S), Image.BICUBIC))
        acc += _norm_band(cv2.cvtColor(a, cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32))
        n += 1
    if n == 0:
        raise ValueError(f"no retail h textures in {retail_faces}")
    return (acc / n).astype(np.float32)


def synthetic_eye() -> np.ndarray:
    """A drawn reference eye on the mesh openings (sclera, iris, lash lines), for when no retail faces are at hand;
    over the league its offsets agree with the retail mean's (r 0.91, median difference 0.5 texel)."""
    global _SYNTH_EYE
    if _SYNTH_EYE is None:
        T = np.zeros((S, S), np.float32)
        for o in eye_openings():
            m = o["mask"]
            din = ndimage.distance_transform_edt(m) / K
            dout = ndimage.distance_transform_edt(~m) / K
            hh = (o["y1"] - o["y0"]) / K
            r = np.hypot(XX - o["cx"], YY - o["cy"]) / K
            above = YY < o["cy"]
            t = np.where(m, 1.0, 0.0)
            t = np.where(m & (r < 0.62 * hh), -1.6, t)
            t = t - np.where(~m & above, 2.2 * np.exp(-(dout / 1.3) ** 2), 0) - np.where(~m & ~above, 0.9 * np.exp(-(dout / 1.0) ** 2), 0)
            t = t - np.where(m, 0.6 * np.exp(-(din / 0.8) ** 2), 0)
            T += t.astype(np.float32)
        _SYNTH_EYE = cv2.GaussianBlur(T, (0, 0), 0.8 * K)
    return _SYNTH_EYE


def use_eye_reference(ref) -> None:
    """Set the reference eye (an (S,S) array or an .npy path); None goes back to the synthetic one."""
    global _EYE_REF
    _EYE_REF = None if ref is None else (np.load(ref) if isinstance(ref, (str, Path)) else np.asarray(ref, np.float32))


def _ncc_map(L, ref, o, kx, ky):
    hw, hh = o["x1"] - o["x0"], o["y1"] - o["y0"]
    tx0, tx1 = int(o["x0"] - 0.22 * hw), int(o["x1"] + 0.22 * hw)
    ty0, ty1 = int(o["y0"] - 0.55 * hh), int(o["y1"] + 0.55 * hh)
    T = ref[ty0:ty1, tx0:tx1]
    DX, DYU, DYD = int(0.2 * hw), int(1.2 * hh), int(1.6 * hh)
    ys = o["cy"] + (np.arange(ty0 - DYU, ty1 + DYD) - o["cy"]) * ky
    xs = o["cx"] + (np.arange(tx0 - DX, tx1 + DX) - o["cx"]) * kx
    reg = cv2.remap(L, np.tile(xs[None, :], (len(ys), 1)).astype(np.float32),
                    np.tile(ys[:, None], (1, len(xs))).astype(np.float32), cv2.INTER_LINEAR)
    return cv2.matchTemplate(reg, T, cv2.TM_CCOEFF_NORMED), DYU


def register_eyes(col):
    """Where the photo's eyes sit against the mesh openings: col is the photo in texture space (openings filled).
    Each eye is matched against the reference eye by normalised cross-correlation over vertical offsets and x/y
    scales (the horizontal peak is flat, so x stays the detector's; the two eyes are measured on their own, since the
    detector misplaces each eye on its own). Returns per eye (dy in game texels, positive = the photo eye is low; the
    correlation; whether the best match is on the edge of the search, i.e. failed)."""
    ref = _EYE_REF if _EYE_REF is not None else synthetic_eye()
    L = cv2.GaussianBlur(cv2.cvtColor(col, cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32), (0, 0), 1.0)
    out = []
    for o in eye_openings():
        best = None
        for kx in (0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25):
            for ky in (0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4):
                r, DYU = _ncc_map(L, ref, o, kx, ky)
                rows = r.max(axis=1)
                j = int(np.argmax(rows))
                val = float(rows[j]) - 0.15 * abs(math.log(kx)) - 0.15 * abs(math.log(ky))
                if best is None or val > best[0]:
                    edge = j < 1.5 * K or j > len(rows) - 1 - 1.5 * K
                    best = (val, (j - DYU) * ky / K, float(rows[j]), bool(edge))
        out.append(best[1:])
    return out


def opening_view(photo_rgba, pts, opts=None):
    """The photo in texture space with the eye openings filled (bake's mapping, eye_shift included when opts has
    one): (S,S,3) uint8 and the photo coordinates q (S,S,2)."""
    opts = opts or {}
    pos, nrm, cov = uvr()
    params, resid = fit_camera(pts)
    if opts.get('eye_shift') is not None:
        resid = resid + np.vstack([np.asarray(opts['eye_shift'], np.float64), np.zeros((3, 2))])
    uv_l = np.array([UV_EYES[0], UV_EYES[1], UV_NOSE, UV_MOUTH[0], UV_MOUTH[1]]) * K
    field = rbf_field(uv_l, resid.astype(np.float32), sigma=opts.get('rbf_sigma', 28) * K)
    q, _Y = project(params, pos)
    q = fill_openings((q + field).astype(np.float32))
    ph = photo_rgba[..., :3].astype(np.float32)
    col = np.clip(cv2.remap(ph, q[..., 0], q[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT), 0, 255).astype(np.uint8)
    return col, q


def eye_shift(photo_rgba, pts, opts=None):
    """The photo-space shift of each eye's residual that puts the photo's eye in the mesh's opening, and the
    measurement. Each eye takes its own registered offset; one that failed (the best match on the edge of the
    search, beyond EYE_DY_MAX or under EYE_NCC_MIN) takes its partner's, or the league median when both failed."""
    opts = dict(opts or {})
    opts.pop("eye_shift", None)
    col, q = opening_view(photo_rgba, pts, opts)
    reg = register_eyes(col)
    ok = [not edge and abs(dy) <= EYE_DY_MAX and c >= EYE_NCC_MIN for dy, c, edge in reg]
    shift = np.zeros((2, 2), np.float64)
    info = []
    for k, (dy, c, edge) in enumerate(reg):
        use = dy if ok[k] else (reg[1 - k][0] if ok[1 - k] else EYE_DY_MEDIAN)
        p0 = np.array(UV_EYES[k], np.float32) * K
        p1 = p0 + np.array([0.0, use * K], np.float32)
        a = cv2.remap(q, np.array([[p0[0], p1[0]]], np.float32), np.array([[p0[1], p1[1]]], np.float32), cv2.INTER_LINEAR)[0]
        shift[k] = a[1] - a[0]
        info.append({"dy": round(float(dy), 2), "ncc": round(c, 3), "edge": bool(edge), "used": round(float(use), 2)})
    return shift, info


def brow_shift(q0, q1, brow_y=37.0):
    """How far (game texels, positive = up) the photo's brows move in the texture with the eye shift: for each eye's
    column, the texel of the new mapping that samples the photo row the old mapping sampled at the brows."""
    out = []
    for cx, _cy in UV_EYES:
        x = int(round(cx * K))
        yb = int(round(brow_y * K))
        target = float(q0[yb, x, 1])
        col = q1[:, x, 1].astype(np.float64)
        lo, hi = yb - int(10 * K), yb + int(10 * K)
        ys = np.arange(lo, hi)
        v = np.maximum.accumulate(col[lo:hi])          # the column runs down the photo (tiny reversals ironed out)
        if not (v[0] <= target <= v[-1]) or v[-1] - v[0] < 1e-6:
            out.append(0.0)
            continue
        out.append(float(np.clip((yb - np.interp(target, v, ys)) / K, -10.0, 10.0)))
    return out


def photo_iris(col):
    """The photo's iris colour (Lab, uint8 scale) from the photo in texture space after the eye shift: inside both
    openings, the sclera and catchlights (the brightest 30%) and the pupil and lashes (the darkest 30%) left out."""
    vals = []
    P = lab(col)
    for o in eye_openings():
        m = ndimage.binary_erosion(o["mask"], iterations=int(1 * K))
        r = np.hypot((XX - o["cx"]) / K, (YY - o["cy"]) / K)
        m &= r < 0.5 * (o["y1"] - o["y0"]) / K
        if m.sum() < 20:
            continue
        v = P[m]
        lo, hi = np.percentile(v[:, 0], [30, 70])
        vals.append(v[(v[:, 0] >= lo) & (v[:, 0] <= hi)])
    if not vals:
        return None
    return np.median(np.concatenate(vals), axis=0)


def patch_iris(rgb_tex):
    """The iris colour (Lab) of a texture's eyeball square: an annulus around the square's centre (the iris ring
    between the pupil and the limbus; retail centres its irises), its darkest 30% (pupil, limbal ring) and brightest
    15% (catchlights) left out. rgb_tex at any size."""
    Hh = rgb_tex.shape[0]
    y0, y1, x0, x1 = (int(EYE_PATCH[0] * Hh), int(EYE_PATCH[1] * Hh), int(EYE_PATCH[2] * Hh), int(EYE_PATCH[3] * Hh))
    p = np.ascontiguousarray(rgb_tex[y0:y1, x0:x1, :3]).astype(np.uint8)
    P = lab(p)
    hh, ww = p.shape[:2]
    yy, xx = np.mgrid[0:hh, 0:ww]
    r = np.hypot(yy - (hh - 1) / 2, xx - (ww - 1) / 2) / hh
    v = P[(r >= 0.13) & (r <= 0.27)]
    if len(v) < 10:
        return None
    lo, hi = np.percentile(v[:, 0], [30, 85])
    return np.median(v[(v[:, 0] >= lo) & (v[:, 0] <= hi)], axis=0)


def iris_target(iris_photo):
    """The photo's iris in texture terms: the skin's exposure calibration applied to it (studio light)."""
    cal = calibration()
    Lp = float(iris_photo[0]) * 100 / 255
    Lt = float(y_to_lstar(cal['k'] * lstar_to_y(Lp)))
    f = Lt / max(Lp, 1.0)
    return np.array([Lt * 255 / 100, 128 + (iris_photo[1] - 128) * f * cal['s_a'], 128 + (iris_photo[2] - 128) * f * cal['s_b']], np.float32)


def iris_distance(a, b):
    """Iris colour distance: hue and chroma count fully; lightness only beyond 25 (of 255) and by 0.3 (the photo's
    iris reads darker than retail paints one: pupil and lid shadow), so a brown iris stays a brown iris and a light
    blue or green one finds a light retail iris."""
    a = np.asarray(a, np.float64); b = np.asarray(b, np.float64)
    dl = max(0.0, abs(a[0] - b[0]) - 25.0)
    return float(math.sqrt((0.3 * dl) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2))


def iris_light(lab_v) -> bool:
    """Light eyes (blue, grey, green-grey): not yellow-brown (b* under 3) and not dark (L over 55 of 255)."""
    return bool(lab_v[2] - 128 < 3 and lab_v[0] > 55)


def copy_eye_patch(dst_rgb, src_rgb):
    """The eyeball square of src_rgb copied into dst_rgb (same size)."""
    out = dst_rgb.copy()
    Hh = out.shape[0]
    y0, y1, x0, x1 = (int(EYE_PATCH[0] * Hh), int(EYE_PATCH[1] * Hh), int(EYE_PATCH[2] * Hh), int(EYE_PATCH[3] * Hh))
    out[y0:y1, x0:x1] = src_rgb[y0:y1, x0:x1]
    return out


def skin_lab_of(photo_lab, w):
    """The photo's diffuse skin: the upper face (forehead to the cheekbones, eyes and brows left out), skin-coloured
    pixels only, the 20th to 50th percentile of lightness (studio highlights and deep shadows left out). Over the
    league's 193 players its rank agrees with the roster skin tones as well as u1's measure (Spearman 0.858)."""
    eyes = np.maximum(ellipse(UV_EYES[0][0], UV_EYES[0][1], 21, 10, 3), ellipse(UV_EYES[1][0], UV_EYES[1][1], 21, 10, 3))
    brows = np.maximum(ellipse(85, 38, 24, 9, 3), ellipse(170, 38, 24, 9, 3))
    ys = YY / K
    m = (ys > 20) & (ys < 112) & (w > 0.8) & (eyes < 0.2) & (brows < 0.2)
    px = photo_lab[m]
    px = px[(px[:, 1] > 131) & (px[:, 2] > 131)]
    if len(px) < 200:
        px = photo_lab[w > 0.8]
    lo, hi = np.percentile(px[:, 0], [20, 50])
    return np.median(px[(px[:, 0] >= lo) & (px[:, 0] <= hi)], axis=0)



def template_skin(T0_face):
    cheeks = np.maximum(ellipse(95, 105, 14, 14, 2), ellipse(161, 105, 14, 14, 2)) > 0.5
    return np.median(T0_face[cheeks], axis=0)


def template_hair(T0_n):
    return np.median(T0_n[int(80 / 1024 * S):int(940 / 1024 * S), int(690 / 1024 * S):int(1000 / 1024 * S)].reshape(-1, 3), axis=0)


def reskin(T0, skin_p, skin_t=None, hair_p=None, hair_t=None, hair_zone=None, force_skin=None):
    """A retail texture (face or skull) moved to the player: skin pixels keep the template's shading pattern
    (lightness scaled to the player's skin) and a softened copy of its chroma pattern around the player's skin
    chroma; hair pixels move toward the player's hair (lightness, and chroma only partly, inside retail's range).
    The face and the skull use the same mapping, so their seam matches the way retail's does."""
    if skin_t is None:
        skin_t = template_skin(T0)
    d = np.linalg.norm(T0 - skin_t, axis=2)
    ws = np.clip(1.25 - d / 40.0, 0, 1)
    ws = cv2.GaussianBlur(ws.astype(np.float32), (0, 0), 1.0 * K)
    if force_skin is not None:
        ws = np.maximum(ws, force_skin)
    ratio = skin_p[0] / max(skin_t[0], 1.0)
    sk = np.empty_like(T0)
    sk[..., 0] = T0[..., 0] * ratio
    sk[..., 1:] = skin_p[1:] + 0.6 * (T0[..., 1:] - skin_t[1:])
    other = T0.copy()
    other[..., 0] = T0[..., 0] * (0.5 + 0.5 * ratio)          # brows, lashes, eye shadow: follow the skin a little
    if hair_p is not None and hair_t is not None:
        # hair: an additive move of the template's hair toward the player's (lightness in full, chroma by a third,
        # inside retail's range), only where a pixel is clearly hair (darker than the template's skin)
        hair = T0.copy()
        hair[..., 0] = T0[..., 0] + (hair_p[0] - hair_t[0])
        hair[..., 1:] = T0[..., 1:] + 0.7 * (hair_p[1:] - hair_t[1:])[None, None, :]
        hair[..., 1] = np.clip(hair[..., 1], 128 - 1, 128 + 13)
        hair[..., 2] = np.clip(hair[..., 2], 128 - 1, 128 + 24)
        like = np.clip((skin_t[0] - 12 - T0[..., 0]) / 25.0, 0, 1)
        hz = (np.ones(T0.shape[:2], np.float32) if hair_zone is None else hair_zone) * like
        other = hair * hz[..., None] + other * (1 - hz[..., None])
    return sk * ws[..., None] + other * (1 - ws[..., None])



# Photo skin -> texture skin (fx 2026-09-24): the exposure factor k (studio photos are brighter than the game's
# albedo) and the chroma scales were fitted over the league's 193 custom-face players, each player's diffuse photo skin
# against retail's cheek colour for his roster skin tone; the per-tone table is retail's (the retail roster's skin
# field for every custom face id, the median cheek colour of its h texture; L* and a*/b* in CIE units).
CALIBRATION = {
 "k": 0.7477985127002649,
 "s_a": 0.8239487026099588,
 "s_b": 0.9658200062715586,
 "tones": {
  "0": {
   "L_med": 61.96078431372549,
   "L_p10": 57.254901960784316,
   "L_p90": 65.56862745098039,
   "a_med": 22.0,
   "b_med": 30.0,
   "n": 109
  },
  "1": {
   "L_med": 56.86274509803921,
   "L_p10": 52.0,
   "L_p90": 59.84313725490196,
   "a_med": 17.0,
   "b_med": 36.0,
   "n": 25
  },
  "2": {
   "L_med": 45.88235294117647,
   "L_p10": 41.529411764705884,
   "L_p90": 50.23529411764706,
   "a_med": 16.0,
   "b_med": 23.0,
   "n": 80
  },
  "3": {
   "L_med": 37.254901960784316,
   "L_p10": 33.333333333333336,
   "L_p90": 40.3921568627451,
   "a_med": 13.0,
   "b_med": 20.0,
   "n": 123
  },
  "4": {
   "L_med": 34.11764705882353,
   "L_p10": 30.980392156862745,
   "L_p90": 37.64705882352941,
   "a_med": 12.0,
   "b_med": 15.0,
   "n": 120
  },
  "5": {
   "L_med": 30.58823529411765,
   "L_p10": 27.294117647058822,
   "L_p90": 34.35294117647059,
   "a_med": 11.0,
   "b_med": 8.0,
   "n": 53
  }
 }
}
_CAL = None


def calibration():
    return _CAL or CALIBRATION


def set_calibration(path) -> None:
    global _CAL
    _CAL = json.loads(Path(path).read_text(encoding="utf-8"))


def lstar_to_y(Ls):
    Ls = np.asarray(Ls, np.float64)
    return np.where(Ls > 8, ((Ls + 16) / 116) ** 3, Ls / 903.3)


def y_to_lstar(Y):
    Y = np.asarray(Y, np.float64)
    return np.where(Y > 0.008856, 116 * np.cbrt(Y) - 16, 903.3 * Y)


def target_skin(skin_p, tone, cal=None):
    """The texture skin colour for a player: his photo skin under the calibrated exposure, kept inside retail's
    spread for his roster skin tone (so the face matches the arms the game draws for that tone)."""
    cal = cal or calibration()
    Lp = float(skin_p[0]) * 100 / 255
    Lt = float(y_to_lstar(cal['k'] * lstar_to_y(Lp)))
    f = Lt / max(Lp, 1.0)
    a = (float(skin_p[1]) - 128) * f * cal['s_a']
    b = (float(skin_p[2]) - 128) * f * cal['s_b']
    if tone is not None and str(int(tone)) in cal['tones']:
        c = cal['tones'][str(int(tone))]
        Lt = float(np.clip(Lt, c['L_p10'], c['L_p90']))
        a = float(np.clip(a, c['a_med'] - 6, c['a_med'] + 6))
        b = float(np.clip(b, c['b_med'] - 7, c['b_med'] + 7))
    return np.array([Lt * 255 / 100, a + 128, b + 128], np.float32)


def eye_blend(P, skin_p, w, rim=0.5, rim_width=2.5):
    """The template's share around the eyes (fc1): 1 inside the openings, ``rim`` at their rims falling to 0
    ``rim_width`` game texels out, and 1 over photo sclera (bright, near neutral) left within 5 texels of them or a
    light iris (near neutral, between the skin and a lash line in lightness) within 4."""
    _pos, _nrm, cov = uvr()
    m = np.zeros((S, S), np.float32)
    lids = np.zeros((S, S), bool)
    for o in eye_openings():
        dout = ndimage.distance_transform_edt(~o["mask"]) / K
        m = np.maximum(m, np.where(o["mask"], 1.0, rim * np.clip(1 - dout / rim_width, 0, 1)).astype(np.float32))
        lids |= cov & (dout <= 5)
    Cs = float(np.hypot(skin_p[1] - 128, skin_p[2] - 128))
    C = np.hypot(P[..., 1] - 128, P[..., 2] - 128)
    scl = lids & (P[..., 0] > skin_p[0] + 6 * 2.55) & (C < 0.55 * Cs + 2) & (w > 0.3)
    # a light iris left on the lids (blue, grey: near neutral, darker than the skin but not as dark as a lash line)
    near = np.zeros((S, S), bool)
    for o in eye_openings():
        near |= cov & (ndimage.distance_transform_edt(~o["mask"]) / K <= 4)
    dL = (P[..., 0] - skin_p[0]) / 2.55
    iris = near & (dL > -28) & (dL < -5) & (C < 0.45 * Cs + 1) & (w > 0.3)
    iris = ndimage.binary_opening(iris, iterations=1)
    scl = ndimage.binary_dilation(scl | iris, iterations=int(K))
    m = np.maximum(m, cv2.GaussianBlur(scl.astype(np.float32), (0, 0), 0.7 * K))
    return cv2.GaussianBlur(m, (0, 0), 0.35 * K)


def compose(photo_rgba, pts, tpl_rgb, opts, hair_p=None, hair_t=None, skin_t=None, tone=None):
    """One face texture (f or h) at 1024. method 'A': the photo baked over the template, relit to the template's
    shading, open mouths closed with the template's lips. method 'B': the retail template re-skinned, with only the
    photo's facial hair and brows laid over it."""
    col, w, info = bake(photo_rgba, pts, opts)
    eyes_z, lips_z, atlas_z = zones()
    P = lab(col)
    T0 = lab(tpl_rgb)
    skin_p = skin_lab_of(P, w)
    teeth_before = 0.0
    skin_x = target_skin(skin_p, tone) if opts.get('calibrate', True) else skin_p
    hz = np.clip(np.maximum((24 * K - YY) / (8 * K), (np.abs(XX / K - 128) - 100) / 10.0), 0, 1).astype(np.float32)
    T = reskin(T0, skin_x, skin_t, hair_p, hair_t, hair_zone=hz, force_skin=np.clip((lips_z - 0.1) / 0.5, 0, 1).astype(np.float32))
    feat = np.maximum(eyes_z, lips_z) > 0.3
    de = opts.get('skin_de', 24)
    dP = np.linalg.norm(P - skin_p, axis=2)
    # the photo's own hair beside the face (twists, long hair, curls on the temples) is not face: drop dark non-skin
    # pixels outside the beard and brow zones
    beard_zone = ellipse(128, 168, 62, 46, 8)
    # fc1: with the eye shift the photo's brows sit higher in the texture by brow_dy texels; the brow zones follow
    bdy = opts.get('brow_dy') or (0.0, 0.0)
    brow_zone = np.maximum(ellipse(UV_EYES[0][0], 36 - bdy[0], 26, 10, 4), ellipse(UV_EYES[1][0], 36 - bdy[1], 26, 10, 4))
    # dark hair-coloured pixels anywhere on the upper face outside the brows, the eyes and the nostrils are hair
    # falling over the face (twists, dreads, curls): beside it, over the forehead, down the nose bridge
    brow_band = np.maximum(ellipse(UV_EYES[0][0], 38 - bdy[0], 21, 6.5, 2), ellipse(UV_EYES[1][0], 37 - bdy[1], 21, 6.5, 2))
    nostrils = ellipse(128, 105, 21, 9, 3)
    upper = YY / K < 124
    # (hair is near neutral; the face's own creases and shadows keep the skin's hue). Beside the face and above the
    # brows such pixels are always hair; lower on the face only when the forehead itself is covered (dreads, bangs),
    # since there the same test would also take the player's own lids and shadows
    skin_c = float(np.hypot(skin_p[1] - 128, skin_p[2] - 128))
    hairlike = ((P[..., 0] < skin_p[0] - 28) & (dP > de) & upper & (beard_zone < 0.3)
                & (np.hypot(P[..., 1] - 128, P[..., 2] - 128) < 0.65 * skin_c + 3))
    fore = (YY / K > 12) & (YY / K < 30 - max(0.0, max(bdy))) & (np.abs(XX / K - 128) < 40) & (w > 0.5)
    covered = bool(fore.any() and hairlike[fore].mean() > opts.get('forehead_hair', 0.12))
    sides = (np.abs(XX / K - 128) > 50) | (YY / K < 30)
    darkhair = hairlike & (sides | covered) & (np.maximum.reduce([brow_band, nostrils, eyes_z]) < 0.3)
    darkhair = cv2.GaussianBlur(ndimage.binary_dilation(darkhair, iterations=int(2 * K)).astype(np.float32), (0, 0), 1.5 * K)
    w = w * (1 - darkhair)
    Mp = (w > 0.6) & (dP < de) & ~feat
    Mt = (np.linalg.norm(T - skin_x, axis=2) < de) & ~feat & (atlas_z < 0.5)
    sig = opts.get('light_sigma', 10) * K
    Ip = normconv(P, Mp, sig)
    It = normconv(T, Mt, sig)
    # the template's forehead skin carries a retail band under the hairline: above the photo it is the smooth skin
    # field, so only the template's hair (not its skin pattern) shows there
    # (the top rows stay the template's own: retail painted them to meet the skull texture)
    ramp = np.clip((52 * K - YY) / (10 * K), 0, 1) * np.clip((YY - 4 * K) / (6 * K), 0, 1)
    tskin = np.clip(1.4 - np.linalg.norm(T - skin_x, axis=2) / 40.0, 0, 1) * ramp
    tskin = cv2.GaussianBlur(tskin.astype(np.float32), (0, 0), 1.0 * K)
    T = T * (1 - tskin[..., None]) + It * tskin[..., None]
    # the template's own facial hair (goatee, moustache, stubble) goes: the only beard is the player's
    lower = np.clip((YY / K - 108) / 10.0, 0, 1) * (1 - lips_z) * (1 - atlas_z)
    shave = lower * np.clip((It[..., 0] - T[..., 0] - 6) / 14.0, 0, 1)
    shave = cv2.GaussianBlur(shave.astype(np.float32), (0, 0), 1.0 * K)
    T = T * (1 - shave[..., None]) + It * shave[..., None]
    Pr = P - Ip + It
    # chroma moves by ratio, not by offset: skin at the photo's skin chroma lands on the target's, and neutral pixels
    # (hair, beard, teeth, eye whites) stay neutral instead of taking the negative of the photo's warm studio cast
    # up to the skin's own chroma; colour beyond it (lips, flush) passes as an excess over the target skin, softly
    # capped, since studio light makes lips far more saturated than retail paints them
    for c in (1, 2):
        ip, it, d = Ip[..., c] - 128, It[..., c] - 128, P[..., c] - 128
        safe = np.where(np.abs(ip) < 2.0, np.where(ip < 0, -2.0, 2.0), ip)
        t = d / safe
        cap = opts.get('chroma_excess', 12.0)
        excess = cap * np.tanh((d - safe) * np.sign(safe) / cap) * np.sign(safe)
        ratio = np.where(t < 0, 0.6, np.clip(it / safe, 0.3, 2.0))   # opposite to the skin's cast: damped, not amplified
        Pr[..., c] = 128 + np.where(t <= 1.0, d * ratio, it + excess)
    fine = Pr - cv2.GaussianBlur(Pr, (0, 0), 1.6 * K)
    Pr = Pr - (1 - opts.get('detail', 0.72)) * fine
    L = Pr[..., 0]; base = It[..., 0]
    knee = base + opts.get('knee', 7.0) * 2.55
    Pr[..., 0] = np.where(L > knee, knee + (L - knee) * 0.35, L)
    # beards read darker than retail's painted ones: scale the darkness under the nose by beard_gain, strand detail kept
    lowf = np.clip((YY / K - 112) / 10.0, 0, 1)
    dd = np.minimum(0.0, Pr[..., 0] - It[..., 0])
    Pr[..., 0] = Pr[..., 0] - (1 - opts.get('beard_gain', 0.8)) * dd * lowf
    # studio highlights lose their colour in the photo; after the relight they would read grey-blue: give them the
    # skin field's chroma
    hl = np.clip((L - (base + 4 * 2.55)) / (8 * 2.55), 0, 1)[..., None]
    Pr[..., 1:] = Pr[..., 1:] * (1 - hl) + It[..., 1:] * hl
    method = opts.get('method', 'A')
    if method == 'B':
        # identity features only: darkening where the photo has hair on the face (beard, moustache, brows)
        dark = np.minimum(0.0, Pr[..., 0] - It[..., 0])
        zone = np.maximum(beard_zone, brow_zone) * w
        out = T.copy()
        out[..., 0] = T[..., 0] + opts.get('hair_gain', 0.9) * dark * zone
        out[..., 1:] = T[..., 1:] * (1 - 0.5 * zone[..., None] * (dark[..., None] < -8)) + Pr[..., 1:] * (0.5 * zone[..., None] * (dark[..., None] < -8))
    else:
        out = T * (1 - w[..., None]) + Pr * w[..., None]
    teeth = 0.0
    if method != 'B':
        L_ = P[..., 0]
        sat = np.hypot(P[..., 1] - 128, P[..., 2] - 128)
        skin_sat = float(np.hypot(skin_p[1] - 128, skin_p[2] - 128))
        mzone = (np.abs(XX / K - 128) < 44) & (np.abs(YY / K - 146) < 22) & (w > 0.3)
        # teeth: brighter than the skin, near neutral (lips, even glossy ones, are pinker), in the mouth; lip sheen on
        # closed mouths scores 0.000-0.001 over the league's photos, open smiles 0.04 and up
        tzone = (np.abs(XX / K - 128) < 40) & (np.abs(YY / K - 146) < 16) & (w > 0.3)
        Ls = L_ * 100 / 255
        teeth_px = tzone & (Ls > max(skin_p[0] * 100 / 255 + 8, 58)) & (P[..., 1] - 128 < 9) & (sat < 24)
        teeth_px = ndimage.binary_opening(teeth_px, iterations=2)
        teeth = float(teeth_px.sum() / max(1, tzone.sum()))
        teeth_before = max(teeth_before, teeth)
        # hair-like pixels (beard, moustache): darker than the local skin and not as saturated as lips
        hairy = (Pr[..., 0] < It[..., 0] - 10) & (np.hypot(Pr[..., 1] - 128, Pr[..., 2] - 128) < 0.9 * skin_sat + 4)
        Dh = np.where(hairy, np.minimum(0.0, Pr[..., 0] - It[..., 0]), 0.0).astype(np.float32)
        if teeth > opts.get('teeth_thr', 0.005):
            # an open mouth: the photo's teeth and the lips around them go, the template's closed lips (in the
            # player's skin) come in, and the player's moustache and goatee stay on top
            near = ndimage.binary_dilation(teeth_px, iterations=int(4 * K))
            lipsy = mzone & near & ~teeth_px & (P[..., 1] > skin_p[1] + 2)
            M = ndimage.binary_dilation(teeth_px | lipsy, iterations=int(2 * K))
            # the smile's corner creases go with the mouth
            M = ndimage.binary_dilation(M, structure=np.ones((1, int(20 * K) | 1), bool))
            M = ndimage.binary_dilation(M, structure=np.ones((int(6 * K) | 1, 1), bool)) & mzone
            M = np.maximum(M.astype(np.float32), (lips_z > 0.5).astype(np.float32))
            M = cv2.GaussianBlur(M, (0, 0), 2.5 * K)
            inside = T.copy()
            keep_hair = Dh * (1 - (lips_z > 0.3))
            Lold = np.maximum(inside[..., 0], 1.0)
            inside[..., 0] = inside[..., 0] + keep_hair
            f = (np.maximum(inside[..., 0], 0) / Lold)[..., None]
            inside[..., 1:] = 128 + (inside[..., 1:] - 128) * f
            out = out * (1 - M[..., None]) + inside * M[..., None]
        else:
            M = np.zeros((S, S), np.float32)
        # the beard follows the jaw past the photo's edge: below the last solid photo row of each column, the
        # photo's own beard darkness is mirrored back (real strands, so the hair breaks up) and fades out
        solid = (w > 0.85) & (YY / K > 150)
        has = solid.any(axis=0)
        edge = np.where(has, S - 1 - np.argmax(solid[::-1, :], axis=0), 0).astype(np.float32)
        edge = ndimage.gaussian_filter1d(edge, 2 * K)
        beardcol = ndimage.gaussian_filter1d((Dh * (solid & (YY / K > edge[None, :] / K - 25))).sum(0), 3 * K) < -1.0
        vv = YY - edge[None, :]
        vsrc = (edge[None, :] - vv).astype(np.float32)
        Dm = cv2.remap(Dh, XX, vsrc, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        fade = np.clip(1 - vv / (18 * K), 0, 1) ** 1.5 * (vv > 0)
        side = np.clip((74 - np.abs(XX / K - 128)) / 12.0, 0, 1) * (1 - atlas_z)
        add = Dm * fade * side * beardcol[None, :] * (1 - w) * opts.get('beard_gain', 0.8)
        Lold = np.maximum(out[..., 0], 1.0)
        out[..., 0] = out[..., 0] + add
        f = (np.maximum(out[..., 0], 0) / Lold)[..., None]
        out[..., 1:] = 128 + (out[..., 1:] - 128) * f
    if opts.get('eye_fix'):
        # fc1: the opening holds the template's eye (the mesh hides it at full size, the mip levels show it), the
        # template's lid only on a thin rim, and photo sclera left on the lids goes back to the template's lid
        m = eye_blend(P, skin_p, w, opts.get('eye_rim', 0.5), opts.get('eye_rim_width', 2.5))[..., None]
        out = out * (1 - m) + T * m
    elif opts.get('eye_rings', True):
        rings =np.maximum(ellipse(UV_EYES[0][0], UV_EYES[0][1], 19, 8.5, 3), ellipse(UV_EYES[1][0], UV_EYES[1][1], 19, 8.5, 3))
        m = (rings * opts.get('ring', 0.7))[..., None]
        out = out * (1 - m) + T * m
    out_rgb = rgb(out)
    a = atlas_z[..., None] > 0.5
    out_rgb = np.where(a, tpl_rgb, out_rgb)
    info.update(teeth=round(teeth, 3), teeth_photo=round(teeth_before, 3), skin_lab=[round(float(v), 1) for v in skin_p],
                skin_target=[round(float(v), 1) for v in skin_x])
    return out_rgb, info


def hair_lab(photo_rgba, pts):
    """Hair colour above the forehead: opaque, non-skin pixels, chroma kept inside retail's range."""
    bgr = photo_rgba[..., :3][..., ::-1].copy()
    L = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    le, re_ = pts[0], pts[1]
    eye_d = float(np.linalg.norm(re_ - le))
    top = int(((le + re_) / 2)[1] - 1.05 * eye_d)
    x0, x1 = int(le[0] - 0.2 * eye_d), int(re_[0] + 0.2 * eye_d)
    band = L[max(0, top - int(0.35 * eye_d)):top, x0:x1].reshape(-1, 3)
    al = photo_rgba[max(0, top - int(0.35 * eye_d)):top, x0:x1, 3].reshape(-1)
    band = band[al > 240]
    if len(band) < 50:
        return None
    Lk = np.percentile(band[:, 0], 60)
    h = np.median(band[band[:, 0] <= Lk], axis=0)
    a, b = h[1] - 128, h[2] - 128
    a = float(np.clip(a, 0.0, 12.0)); b = float(np.clip(b, 0.0, 23.0))
    return np.array([h[0], a + 128, b + 128], np.float32)


def skull(tpl_n_rgb, skin_p, skin_t, hair_p, hair_t):
    """The neck and skull texture with exactly the face's skin and hair mapping."""
    return rgb(reskin(lab(tpl_n_rgb), skin_p, skin_t, hair_p, hair_t))


# --------------------------------------------------------------------------------------------- mesh features
def mesh_features(h: "HeadMesh") -> dict:
    """The head's own features, measured on the mesh (the constants above are these, rounded): the centre of each
    eye opening (the boundary ring of the skin around each eyeball) and the nose tip (the most forward skin vertex),
    in texture pixels at 256."""
    from collections import Counter
    t = skin_triangles(h)
    uvw = h.uv % 1.0
    edges = Counter()
    for tri in t:
        for a_, b_ in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edges[(min(a_, b_), max(a_, b_))] += 1
    boundary = np.unique(np.array([e for e, c in edges.items() if c == 1]))
    eg = np.unique(h.tris["SKIN_eyegloss"])
    eyes = []
    for side in (-1, 1):
        c = h.pos[eg][np.sign(h.pos[eg, 0]) == side].mean(0)
        ring = boundary[np.linalg.norm(h.pos[boundary][:, :2] - c[:2], axis=1) < 1.6]
        eyes.append((uvw[ring] * 256).mean(0))
    v = np.unique(t)
    tip = v[np.argmax(h.pos[v, 2])]
    return {"eyes": np.array(eyes), "nose": uvw[tip] * 256, "nose_pos": h.pos[tip]}


# --------------------------------------------------------------------------------------------- one player
def photo_checks(score, params, resid, eye_d, w) -> tuple[dict, bool]:
    """The checks a photo passes before method A: detector score, head turn, how well the head's features fit the
    photo's (eyes and nose, mouth), how much of the face the photo covers, and resolution."""
    r = np.abs(resid) / eye_d
    cz = ellipse(128, 100, 52, 62, 2) > 0.5
    cover = float((w[cz] > 0.5).mean())
    checks = {"score": round(float(score), 3), "pose_deg": [round(float(np.degrees(v)), 1) for v in params[1:4]],
              "resid_eyes_nose": round(float(r[:3].max()), 3), "resid_mouth": round(float(r[3:].max()), 3),
              "coverage": round(cover, 3), "eye_px": round(float(eye_d), 1)}
    ok = (score >= 0.8 and max(abs(v) for v in checks["pose_deg"]) <= 20 and checks["resid_eyes_nose"] <= 0.15
          and checks["resid_mouth"] <= 0.3 and cover >= 0.85 and eye_d >= 150)
    return checks, ok


def build_player(photo_rgba, found, retail_faces: Path, template: str, tone, hair_override=None, eyes=True,
                 irises=None):
    """f, h and n at 1024 (RGB uint8) for one player, the method used and the checks. ``found`` is YuNet's
    (points, score, box) or None. ``eyes`` (fc1): the photo's eyes moved into the mesh's openings (eye_shift) and
    the eye blend of eye_blend(); False keeps face fit v2's 9/24 eyes byte for byte. ``irises``: {retail face id:
    iris Lab} (iris_table), to give the eyeball a retail iris close to the player's."""
    checks, method = {}, "A"
    if found is None:
        method = "C"
        checks["detected"] = False
    else:
        pts, score, _box = found
        eye_d = float(np.linalg.norm(pts[1] - pts[0]))
        params, resid = fit_camera(pts)
        _col, w, _ = bake(photo_rgba, pts, {})
        c, ok = photo_checks(score, params, resid, eye_d, w)
        checks.update(detected=True, **c)
        if not ok:
            method = "B" if score >= 0.8 else "C"
    if method == "C":
        return {fam: load_rgb(retail_faces / f"{fam}{template}.png") for fam in "fhn"}, method, checks
    opts = {"method": method}
    if eyes and method == "A":
        shift, einfo = eye_shift(photo_rgba, pts, opts)
        _c0, q0 = opening_view(photo_rgba, pts, opts)
        _c1, q1 = opening_view(photo_rgba, pts, {**opts, "eye_shift": shift})
        opts.update(eye_shift=shift, eye_fix=True, brow_dy=brow_shift(q0, q1))
        checks["brow_dy"] = [round(v, 2) for v in opts["brow_dy"]]
        checks["eyes"] = einfo
        checks["eye_shift_px"] = np.round(shift, 3).tolist()
    hair = hair_lab(photo_rgba, pts)
    if hair_override is not None:
        hair = np.asarray(hair_override, np.float32)
    T0h = lab(load_rgb(retail_faces / f"h{template}.png"))
    T0n_rgb = load_rgb(retail_faces / f"n{template}.png")
    skin_t = template_skin(T0h)
    hair_t = template_hair(lab(T0n_rgb))
    out, info_h = {}, None
    for fam in ("f", "h"):
        img, info = compose(photo_rgba, pts, load_rgb(retail_faces / f"{fam}{template}.png"), opts, hair_p=hair,
                            hair_t=hair_t, skin_t=skin_t, tone=tone)
        out[fam] = img
        if fam == "h":
            info_h = info
    out["n"] = skull(T0n_rgb, np.array(info_h["skin_target"], np.float32), skin_t, hair, hair_t)
    if eyes and method == "A" and irises:
        col, _q = opening_view(photo_rgba, pts, opts)
        ip = photo_iris(col)
        if ip is not None:
            want = iris_target(ip)
            # only a clear mismatch is changed: light eyes on a brown iris or brown eyes on a light one; the iris
            # then comes from the nearest retail eye of the photo's kind
            own = irises.get(template)
            pool = [k for k in sorted(irises) if iris_light(irises[k]) == iris_light(want)] or sorted(irises)
            best = min(pool, key=lambda k: iris_distance(irises[k], want))
            d_own = iris_distance(own, want) if own is not None else 1e9
            d_best = iris_distance(irises[best], want)
            swap = own is None or iris_light(own) != iris_light(want)
            checks["iris"] = {"photo": np.round(want, 1).tolist(), "light": iris_light(want), "template": None if own is None else np.round(own, 1).tolist(),
                              "patch_from": best if swap else template, "d_template": round(d_own, 1), "d_best": round(d_best, 1)}
            if swap:
                for fam in ("f", "h"):
                    out[fam] = copy_eye_patch(out[fam], load_rgb(retail_faces / f"{fam}{best}.png"))
    checks.update(teeth_photo=info_h.get("teeth_photo"), skin_photo=info_h["skin_lab"],
                  skin_target=info_h["skin_target"], hair_lab=None if hair is None else np.round(hair, 1).tolist())
    return out, method, checks


def iris_table(retail_faces: Path, ids) -> dict:
    """{retail face id: iris Lab of its eyeball square} for the retail faces ``ids`` (their h textures)."""
    out = {}
    for fid in ids:
        p = Path(retail_faces) / f"h{fid}.png"
        if p.is_file():
            v = patch_iris(np.asarray(Image.open(p).convert("RGB")))
            if v is not None:
                out[fid] = [float(x) for x in v]
    return out


# --------------------------------------------------------------------------------------------- template choice
IRIS_BOX = (int(0.773 * 256), int(0.868 * 256), 0, int(0.13 * 256))     # the eye patch of the atlas, at 256


def template_features(retail_faces: Path, tones: dict) -> dict:
    """Per retail custom face: its roster skin tone (from the retail roster, ``tones``), cheek skin, skull hair,
    iris colour, beard (lower-face darkness under the cheeks) and whether the skull is bare."""
    out = {}
    yy, xx = np.mgrid[0:256, 0:256]
    cheeks = ((((xx - 95) / 14.0) ** 2 + ((yy - 105) / 14.0) ** 2) <= 1) | ((((xx - 161) / 14.0) ** 2 + ((yy - 105) / 14.0) ** 2) <= 1)
    chin = ((((xx - 128) / 40.0) ** 2 + ((yy - 172) / 22.0) ** 2) <= 1) & ~((((xx - 128) / 30.0) ** 2 + ((yy - 146) / 11.0) ** 2) <= 1)
    for fid, tone in sorted(tones.items()):
        paths = [Path(retail_faces) / f"{fam}{fid}.png" for fam in "fhn"]
        if not all(p.is_file() for p in paths):
            continue
        h = lab(np.asarray(Image.open(paths[1]).convert("RGB")))
        n = lab(np.asarray(Image.open(paths[2]).convert("RGB")))
        skin = np.median(h[cheeks], axis=0)
        hair = np.median(n[20:236, 172:250].reshape(-1, 3), axis=0)
        y0, y1, x0, x1 = IRIS_BOX
        patch = h[y0:y1, x0:x1].reshape(-1, 3)
        sat = np.hypot(patch[:, 1] - 128, patch[:, 2] - 128)
        ring = patch[(sat > 6) & (patch[:, 0] > 30) & (patch[:, 0] < 190)]
        iris = np.median(ring, axis=0) if len(ring) > 10 else np.array([90.0, 135.0, 140.0])
        beard = float(max(0.0, skin[0] - np.percentile(h[chin][:, 0], 30)))
        out[fid] = {"tone": int(tone), "skin": np.round(skin, 1).tolist(), "hair": np.round(hair, 1).tolist(),
                    "iris": np.round(iris, 1).tolist(), "beard": round(beard, 1),
                    "bald": bool(np.linalg.norm(hair - skin) < 25)}
    return out


def photo_features(photo_rgba, pts) -> dict:
    """The player's side of the template choice: diffuse skin, beard (lower-face darkness under the skin, from the
    projected photo) and hair (above the forehead)."""
    col, w, _ = bake(photo_rgba, pts, {})
    P = lab(col)
    skin = skin_lab_of(P, w)
    chin = (ellipse(128, 172, 40, 22, 2) > 0.5) & (ellipse(128, 146, 30, 11, 2) < 0.5) & (w > 0.8)
    beard = float(max(0.0, skin[0] - np.percentile(P[chin][:, 0], 30))) if chin.any() else 0.0
    hair = hair_lab(photo_rgba, pts)
    return {"skin": skin, "beard": beard, "hair": hair}


def choose_template(table: dict, tone, hair, beard: float, skin, used=()) -> str:
    """The retail face to build on: same roster skin tone (the arms the game draws), then the nearest skull hair
    (bare skull for a bare head), then the nearest beard; a brown iris for tones 2 and darker; each template once a
    team where possible."""
    tone = None if tone is None else int(tone)
    pool = {k: v for k, v in table.items() if tone is None or v["tone"] == tone}
    if len(pool) < 15 and tone is not None:
        pool = {k: v for k, v in table.items() if abs(v["tone"] - tone) <= 1}
    if tone is not None and tone >= 2:
        brown = {k: v for k, v in pool.items() if v["iris"][2] - 128 > 6}
        pool = brown or pool
    bald_p = hair is None or float(np.linalg.norm(np.asarray(hair) - np.asarray(skin))) < 25
    def cost(k):
        v = table[k]
        c = 0.0
        if hair is not None:
            dh = np.asarray(v["hair"]) - np.asarray(hair)
            c += abs(dh[0]) + 0.5 * float(np.hypot(dh[1], dh[2]))
        c += 40.0 * (v["bald"] != bald_p)
        c += 0.8 * abs(v["beard"] - beard)
        c += 0.3 * float(np.linalg.norm(np.asarray(v["skin"]) - np.asarray(skin)))
        c += 25.0 * (k in used)
        return c
    return min(sorted(pool), key=cost)
