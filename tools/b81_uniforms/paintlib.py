#!/usr/bin/env python3
"""b81-uniforms painting helpers: shapes are placed by where each texel sits on the player model (tools/uvpos.py), drawn
at 4x and box-reduced onto the native texels, so stripes follow the body and keep clean anti-aliased edges."""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
UV = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/uvpos')
V09 = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/v09/uniforms')
SS = 4
LEVELS = 4
_cache = {}
def field(part, size):
    """(pos, mask) of a texture at 4x its native size (pos = game cm: x left(+)/right, y up, z front(+)/back)."""
    key = (part, size)
    if key not in _cache:
        d = np.load(UV / f'uvpos_{part}.npz'); pos, mask = d['pos'].astype(np.float32), d['mask']
        w, h = size
        # fill the empty texels just outside the islands with their nearest valid neighbour, so edges interpolate cleanly
        idx = ndi.distance_transform_edt(~mask, return_distances=False, return_indices=True)
        pos = pos[idx[0], idx[1]]
        big = np.stack([np.asarray(Image.fromarray(pos[..., i]).resize((w * SS, h * SS), Image.BILINEAR)) for i in range(3)], -1)
        m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((w * SS, h * SS), Image.NEAREST)) > 127
        _cache[key] = (big, m)
    return _cache[key]
def hexc(h):
    h = h.lstrip('#'); return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float64)
def load(sel, name):
    return np.asarray(Image.open(V09 / sel / name).convert('RGBA')).copy()
def composite(rgba, cover_big, colour):
    """cover_big: boolean mask at 4x; paints ``colour`` with the box-reduced coverage."""
    h, w = rgba.shape[:2]
    cov = cover_big.reshape(h, SS, w, SS).mean(axis=(1, 3))[..., None]
    cov = np.round(cov * LEVELS) / LEVELS          # few blend steps: a P8 kit texture has little palette room
    out = rgba.astype(np.float64)
    out[..., :3] = out[..., :3] * (1 - cov) + hexc(colour) * cov if isinstance(colour, str) else out[..., :3] * (1 - cov) + np.asarray(colour) * cov
    return np.clip(np.round(out), 0, 255).astype(np.uint8)
def up(mask):
    """native boolean mask -> 4x"""
    return np.repeat(np.repeat(mask, SS, axis=0), SS, axis=1)
def near(rgba, colours, tol=28):
    c = rgba[..., :3].astype(int); out = np.zeros(c.shape[:2], bool)
    for col in colours:
        out |= np.abs(c - (hexc(col) if isinstance(col, str) else np.asarray(col))).max(-1) <= tol
    return out
def pants_hem_rows(rgba, sock_like):
    """per column, the first row of the sock-coloured lower part (the pants end there)"""
    h, w = rgba.shape[:2]
    low = near(rgba, sock_like, 40); low[:150] = False
    first = np.where(low.any(axis=0), low.argmax(axis=0), h).astype(float)
    # a stripe of the sock colour reads as an early hem in its own columns: take the hem from the columns beside it
    med = ndi.median_filter(first, 41, mode='wrap')
    first = np.where(np.abs(first - med) > 6, med, first)
    return np.round(ndi.gaussian_filter1d(first, 1.0, mode='wrap')).astype(int)
def _crossings(z, cols0, cols1, level, rising):
    """per 4x row, the (fractional) column inside [cols0, cols1) where z crosses ``level``; NaN when it does not"""
    seg = z[:, cols0:cols1]; out = np.full(z.shape[0], np.nan)
    d = seg - level
    sign = d[:, 1:] * d[:, :-1] <= 0
    ok = sign & ((d[:, 1:] - d[:, :-1] > 0) if rising else (d[:, 1:] - d[:, :-1] < 0))
    has = ok.any(axis=1); first = ok.argmax(axis=1)
    r = np.flatnonzero(has); j = first[r]
    a, b = d[r, j], d[r, j + 1]
    out[r] = cols0 + j + a / np.where(a - b == 0, 1, a - b)
    return out
def _smooth_rows(c, sigma):
    ok = ~np.isnan(c)
    if ok.sum() < 8: return c
    idx = np.arange(len(c)); filled = np.interp(idx, idx[ok], c[ok])
    return ndi.gaussian_filter1d(filled, sigma, mode='nearest')
def pants_stripe(rgba, bands, base, clear=None, top=0, hem=None, smooth=10):
    """Repaint the pants side stripe. ``bands`` = [(z0, z1, colour)] in cm from the outer side seam, front positive, the same
    on both legs; the old stripe area (``clear`` = (z0, z1)) is first returned to ``base``. Rows from ``top`` to the hem.
    The band edges follow the leg (where the model's surface is z cm in front of the seam), smoothed along the leg so a
    stripe is a clean ribbon and not the mesh's facets."""
    h, w = rgba.shape[:2]
    pos, m = field('UNIF_pants', (w, h))
    z = pos[..., 2]
    H, W = h * SS, w * SS
    cols = np.arange(W)[None, :].repeat(H, 0); rows = np.arange(H)[:, None].repeat(W, 1)
    hemrow = np.repeat(hem if hem is not None else np.full(w, h), SS) * SS
    live = (rows >= top * SS) & (rows < hemrow[None, :])
    out = rgba.copy()
    def region(z0, z1):
        cover = np.zeros((H, W), bool)
        for c0, c1, rising in ((100 * SS, 185 * SS, False), (327 * SS, 412 * SS, True)):     # left leg: z falls with the column
            e0 = _smooth_rows(_crossings(z, c0, c1, z0, rising), smooth * SS)
            e1 = _smooth_rows(_crossings(z, c0, c1, z1, rising), smooth * SS)
            lo, hi = np.minimum(e0, e1), np.maximum(e0, e1)
            cover |= (cols >= lo[:, None]) & (cols < hi[:, None]) & (cols >= c0) & (cols < c1)
        return cover & live
    if clear is not None:
        out = composite(out, region(*clear), base)
    for z0, z1, colour in bands:
        out = composite(out, region(z0, z1), colour)
    return out
def white_lower_leg(rgba, hem, colour='#FFFFFF', margin=2):
    """the sock-coloured lower part of the pants texture (below the hem) and the hem's blended edge take ``colour``"""
    h, w = rgba.shape[:2]
    rows = np.arange(h)[:, None].repeat(w, 1)
    out = rgba.copy(); out[rows >= (hem[None, :] - margin), :3] = hexc(colour).astype(np.uint8)
    return out
