#!/usr/bin/env python3
"""b81-uniforms: stand a club's slanted jersey digits upright (the Chargers: the real 2026 numbers are upright, the
nameplate letters are the italic ones). The digit art itself is kept: each 64x64 digit is enlarged, sheared back about
its own middle row by the measured slant, and box-reduced, in premultiplied colour so the outline stays clean.
  unslant.py KITDIR OUTDIR PREFIX [--k SLANT]   -> OUTDIR/PREFIX_digit_jersey_N.png (N = 0..9), prints the slant used"""
import sys, argparse
from pathlib import Path
import numpy as np
from PIL import Image
S = 8
def load(p):
    return np.asarray(Image.open(p).convert('RGBA')).astype(np.float64) / 255.0
def shear(rgba, k, clean=False, colours=None):
    """x' = x + k * (y - mid): positive k leans the top to the right, so k = -slant stands an italic digit up."""
    h, w = rgba.shape[:2]
    pm = rgba.copy(); pm[..., :3] *= pm[..., 3:4]
    big = np.asarray(Image.fromarray((pm * 255 + 0.5).astype(np.uint8), 'RGBA').resize((w * S, h * S), Image.BICUBIC)).astype(np.float64) / 255.0
    # crisp the three flat regions a little before resampling (the 64 px art is soft after the first enlargement)
    out = np.zeros_like(big)
    ys = np.arange(h * S)
    a = big[..., 3]
    rows = np.flatnonzero(a.max(axis=1) > 0.5)
    mid = (rows.min() + rows.max()) / 2.0 if len(rows) else h * S / 2.0
    for y in ys:
        d = k * (y - mid)                       # in big pixels
        x = np.arange(w * S) - d
        x0 = np.floor(x).astype(int); f = x - x0
        x0c = np.clip(x0, 0, w * S - 1); x1c = np.clip(x0 + 1, 0, w * S - 1)
        inside = (x0 >= 0) & (x0 + 1 <= w * S - 1)
        row = big[y, x0c] * (1 - f)[:, None] + big[y, x1c] * f[:, None]
        out[y] = np.where(inside[:, None], row, 0)
    if clean:
        # redraw the sheared digit as flat shapes: a slanted edge drawn on a 64 px grid comes back as a sawtooth once it
        # is stood up, so the glyph and its fill are regularised (a median along the stroke direction, then a small
        # round-off) and painted again in the digit's own two colours
        from scipy import ndimage as ndi
        al = out[..., 3]
        rgb = np.where(al[..., None] > 1e-3, out[..., :3] / np.maximum(al[..., None], 1e-3), 0)
        fill, edge = colours
        tf = ((rgb - edge) * (fill - edge)).sum(-1) / max(((fill - edge) ** 2).sum(), 1e-6)   # 0 = outline, 1 = fill
        L = int(round(1.0 / max(abs(k), 0.05))) * S
        glyph = ndi.uniform_filter1d((al > 0.5).astype(np.float64), L, axis=0) > 0.5
        inner = ndi.uniform_filter1d(((al > 0.5) & (tf > 0.5)).astype(np.float64), L, axis=0) > 0.5
        glyph = ndi.gaussian_filter(glyph.astype(np.float64), 0.45 * S) > 0.5
        # one even outline: its width is the art's own (glyph area less fill area over the glyph's edge length)
        soft = (ndi.gaussian_filter(inner.astype(np.float64), 0.45 * S) > 0.5) & glyph
        dist = ndi.distance_transform_edt(glyph)
        ring = glyph & ~soft
        width = float(np.median(dist[soft & ndi.binary_dilation(ring, iterations=2)])) if (soft & ndi.binary_dilation(ring, iterations=2)).any() else 1.6 * S
        inner = dist > width - 0.5
        out = np.zeros_like(out)
        out[glyph] = np.append(edge, 1.0); out[inner] = np.append(fill, 1.0)
    small = out.reshape(h, S, w, S, 4).mean(axis=(1, 3))
    al = small[..., 3:4]
    rgb = np.where(al > 1e-4, small[..., :3] / np.maximum(al, 1e-4), 0)
    return np.concatenate([np.clip(rgb, 0, 1), np.clip(al, 0, 1)], axis=2)
def sharpness(rgba, k):
    a = shear(rgba, k)[..., 3]
    col = a.sum(axis=0)
    return float((np.diff(col) ** 2).sum())
def measure(kit, digits=(1, 4, 7, 0, 8)):
    ks = np.linspace(-0.35, 0.35, 71); score = np.zeros_like(ks)
    for d in digits:
        g = load(Path(kit) / f'digit_jersey_{d}.png')
        score += np.array([sharpness(g, k) for k in ks])
    return float(ks[score.argmax()]), ks, score
def centre(rgba, like):
    """keep the upright digit where the slanted one sat: same horizontal middle of the opaque box"""
    def mid(a):
        cols = np.flatnonzero(a[..., 3].max(axis=0) > 0.5)
        return (cols.min() + cols.max()) / 2.0 if len(cols) else a.shape[1] / 2.0
    dx = int(round(mid(like) - mid(rgba)))
    return np.roll(rgba, dx, axis=1) if dx else rgba
if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('kit'); p.add_argument('out'); p.add_argument('prefix'); p.add_argument('--k', type=float); p.add_argument('--paint', help='FILLHEX,EDGEHEX: repaint the two flat colours (the same shapes for a kit that wears other colours)')
    a = p.parse_args()
    k = a.k
    if k is None:
        k, ks, score = measure(a.kit)
    print('shear', round(k, 3))
    Path(a.out).mkdir(parents=True, exist_ok=True)
    allpx = np.concatenate([load(Path(a.kit) / f'digit_jersey_{d}.png').reshape(-1, 4) for d in range(10)])
    op = (allpx[allpx[:, 3] > 0.99][:, :3] * 255 + 0.5).astype(int)
    u_, c_ = np.unique(op, axis=0, return_counts=True); order = np.argsort(-c_)
    fill = u_[order[0]] / 255.0
    edge = next(u_[i] for i in order[1:] if np.abs(u_[i] - u_[order[0]]).max() > 40) / 255.0
    print('fill', (fill * 255).astype(int).tolist(), 'outline', (edge * 255).astype(int).tolist())
    for d in range(10):
        g = load(Path(a.kit) / f'digit_jersey_{d}.png')
        u = centre(shear(g, k, True, (fill, edge)), g)
        if a.paint:
            nf, ne = [np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0 for h in a.paint.replace('#', '').split(',')]
            tf = ((u[..., :3] - edge) * (fill - edge)).sum(-1) / max(((fill - edge) ** 2).sum(), 1e-6)
            tf = np.clip(tf, 0, 1)[..., None]
            u = np.concatenate([ne + (nf - ne) * tf, u[..., 3:4]], axis=2)
        Image.fromarray((u * 255 + 0.5).astype(np.uint8), 'RGBA').save(Path(a.out) / f'{a.prefix}_digit_jersey_{d}.png')
