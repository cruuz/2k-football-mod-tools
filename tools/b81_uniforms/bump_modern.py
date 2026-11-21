#!/usr/bin/env python3
"""b81-uniforms Track B: a modern (Nike Vapor F.U.S.E. style) jersey relief for the game's bump_jersey slot (512x256
tangent-space normal map, A8R8G8B8). Authoring prototype.

What the real 2026 on-field jersey shows (product and broadcast close-ups, bump/refs_nike): a smooth matte stretch body
with NO open mesh, a flat stitched V collar with a small mesh grill either side of the shield, a wide chevron seam across
the upper chest, two long seams down the front and the back, a stitched name plate, and tight tension wrinkles.
What the 2004 art carries: a coarse open-mesh rectangle on chest and back, a ribbed V collar, loose folds.

The relief is built as a height field on the texture (2x supersampled), placed by the 3D position of each texel on the
player model (tools/uvpos.py), then turned into normals with the retail maps' convention (R = +u, G = up, B = out).
  bump_modern.py RETAIL_BUMP.png TORSO.png OUT.png [--gain G] [--folds F] [--weave W]
"""
import sys, argparse
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
UVPOS = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/uvpos/uvpos_UNIF_jersey.npz')
S = 2
def decode(rgb):
    n = rgb.astype(np.float64) / 127.5 - 1.0
    return n
def encode(nx, ny, nz):
    l = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-9
    out = np.stack([nx / l, ny / l, nz / l], -1)
    return np.clip(np.round(out * 127.5 + 127.5), 0, 255).astype(np.uint8)
def dist_to(f, mask):
    """distance in texels (2x grid) to the zero set of f, from its gradient."""
    gy, gx = np.gradient(f)
    g = np.hypot(gx, gy) + 1e-6
    return np.where(mask, np.abs(f) / g, 1e3)
def groove(d, depth, width):
    return -depth * np.exp(-(d / width) ** 2)
def ridge_pair(d, height, sep, width):
    """two fine raised stitch rows either side of a seam"""
    return height * (np.exp(-((d - sep) / width) ** 2))
def build(retail, torso, gain=1.0, folds=0.55, weave=0.0, seams=True):
    d = np.load(UVPOS); pos, mask = d['pos'].astype(np.float64), d['mask']
    nrm = d['nrm'].astype(np.float64); nrm /= (np.linalg.norm(nrm, axis=-1, keepdims=True) + 1e-9)
    facing_f = nrm[..., 2] > 0.25; facing_b = nrm[..., 2] < -0.25
    H2, W2 = mask.shape
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    ax = np.abs(x)
    front = mask & (z > 0.5); back = mask & (z < -0.5)
    # the two islands in the texture: front on the left half, back on the right half (shoulder caps wrap over)
    uu = np.arange(W2)[None, :].repeat(H2, 0); vv = np.arange(H2)[:, None].repeat(W2, 1)
    isl_front = uu < W2 * 0.535; isl_back = ~isl_front
    hgt = np.zeros((H2, W2))
    if seams:
        w = 1.25 * S / 2 * 1.6          # groove half width in 2x texels
        # 1. chevron across the upper chest: from the shoulders down to a point under the collar shield
        f = y - (50.2 + 0.50 * ax)
        m = mask & isl_front & facing_f & (ax < 22.5) & (y > 44) & (y < 62.5)
        dd = dist_to(f, m)
        hgt += groove(dd, 1.0, w) + ridge_pair(dd, 0.35, 2.6 * S / 2, 1.0)
        # 2. two long seams down the front, from the chevron to the hem, drawing in a little toward the waist
        fx = ax - (9.4 + 0.045 * (y - 10))
        m = mask & isl_front & facing_f & (y < 50.2 + 0.50 * ax - 0.2) & (ax < 16) & (ax > 5)
        dd = dist_to(fx, m)
        hgt += groove(dd, 0.85, w) + ridge_pair(dd, 0.3, 2.6 * S / 2, 1.0)
        # 3. back: the yoke seam over the name plate, the stitched plate, two long seams below it
        fy = y - 58.6
        m = mask & isl_back & facing_b & (ax < 21) & (y > 52) & (y < 62)
        dd = dist_to(fy, m)
        hgt += groove(dd, 0.9, w) + ridge_pair(dd, 0.3, 2.6 * S / 2, 1.0)
        plate = mask & isl_back & (ax < 13.2) & (y > 50.4) & (y < 58.2)
        edge = ndi.distance_transform_edt(plate) + ndi.distance_transform_edt(~plate) - 0.5
        inside = ndi.distance_transform_edt(plate)
        hgt += np.where(plate, 0.55 * np.clip(inside / (1.2 * S), 0, 1), 0)          # the plate sits proud of the body
        hgt += np.where(mask & isl_back, 0.22 * np.exp(-((ndi.distance_transform_edt(plate) - 1.6 * S) / 1.0) ** 2) * plate, 0)
        fx = ax - (11.2 + 0.03 * (y - 10))
        m = mask & isl_back & facing_b & (y < 50.0) & (ax < 17) & (ax > 6)
        dd = dist_to(fx, m)
        hgt += groove(dd, 0.85, w) + ridge_pair(dd, 0.3, 2.6 * S / 2, 1.0)
        # 4. the collar: a flat stitched band round the neck opening, with a fine mesh grill beside the front V
        t = np.asarray(Image.open(torso).convert('RGB').resize((W2, H2), Image.NEAREST)).astype(int)
        grey = (np.abs(t - np.array([220, 220, 220])).max(-1) < 14) & (vv < H2 * 0.62)
        lab, n = ndi.label(grey)
        hole = np.zeros_like(grey)
        for i in range(1, n + 1):
            if (lab == i).sum() > 400 * S * S / 4 and vv[lab == i].min() < 6 * S: hole |= lab == i
        if hole.any():
            dout = ndi.distance_transform_edt(~hole)
            band = (dout > 0) & (dout <= 4.2 * S) & mask
            hgt += np.where(band, 0.7 * np.clip((4.2 * S - dout) / (1.0 * S), 0, 1) * np.clip(dout / (0.8 * S), 0, 1), 0)
            hgt += np.where(mask, 0.3 * np.exp(-((dout - 2.1 * S) / 0.9) ** 2), 0)      # one stitch row along the band
            # grill: fine diagonal mesh in the two small triangles between the band and the chevron, beside the V point
            vtip = vv[hole & isl_front].max() if (hole & isl_front).any() else 0
            utip = uu[hole & isl_front & (vv == vtip)].mean() if vtip else 0
            tri = mask & isl_front & (dout > 4.2 * S) & (dout < 11 * S) & (vv > vtip - 20 * S) & (vv < vtip + 1 * S) & (np.abs(uu - utip) > 3 * S) & (np.abs(uu - utip) < 15 * S)
            mesh = (np.sin((uu + vv) * np.pi / (1.5 * S)) * np.sin((uu - vv) * np.pi / (1.5 * S)))
            hgt += np.where(tri, -0.45 * np.clip(mesh, 0, 1), 0)
    if weave:
        # a faint woven grain (kept under one level at the default; off unless asked): two crossed sines at 2 texels
        hgt += weave * 0.5 * (np.sin(uu * np.pi / S) * np.sin(vv * np.pi / S)) * mask
    hgt = ndi.gaussian_filter(hgt, 0.6)
    gy, gx = np.gradient(hgt)
    k = 1.15 * gain
    nx, ny = -k * gx, k * gy            # R = +u, G = up (image up = -v)
    # tension folds: the 2004 map's own large folds, low-passed so the open mesh and the old rib collar drop out
    r = decode(np.asarray(Image.open(retail).convert('RGB').resize((W2, H2), Image.BILINEAR)))
    lo = np.stack([ndi.gaussian_filter(r[..., i], 3.2 * S) for i in range(2)], -1)
    keep = np.ones((H2, W2))
    if seams and 'hole' in dir() and hole.any():
        keep = np.clip((dout - 5 * S) / (6 * S), 0, 1)          # no old collar ribs near the neck
    nx += folds * lo[..., 0] * keep; ny += folds * lo[..., 1] * keep
    nz = np.ones_like(nx)
    n2 = encode(nx, ny, nz)
    n2[~ndi.binary_dilation(mask, iterations=3 * S)] = (128, 128, 255)
    # box 2x2 down to the native 512x256
    out = n2.reshape(H2 // S, S, W2 // S, S, 3).astype(np.float64).mean(axis=(1, 3))
    v = out / 127.5 - 1.0; v /= (np.sqrt((v ** 2).sum(-1, keepdims=True)) + 1e-9)
    rgb = np.clip(np.round(v * 127.5 + 127.5), 0, 255).astype(np.uint8)
    return np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])
if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('retail'); p.add_argument('torso'); p.add_argument('out')
    p.add_argument('--gain', type=float, default=1.0); p.add_argument('--folds', type=float, default=0.55); p.add_argument('--weave', type=float, default=0.0)
    a = p.parse_args()
    im = build(a.retail, a.torso, a.gain, a.folds, a.weave)
    Image.fromarray(im, 'RGBA').save(a.out); print(a.out, im.shape)
