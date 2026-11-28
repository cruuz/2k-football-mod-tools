#!/usr/bin/env python3
"""b81-uniforms audit helpers (read only).
  px.py crop IMAGE X Y W H OUT.png [SCALE]      crop a box of an image (optionally enlarged, nearest for textures)
  px.py med IMAGE X Y W H                      median and mean RGB of a box
  px.py albedo IMAGE X Y W H  WX WY WW WH      colour box vs a WHITE reference box in the SAME frame (same light):
                                               linear-light ratio, printed as the sRGB albedo a white-is-255 texture would need
  px.py clusters IMAGE X Y W H [K]              dominant colours of a box (k-means in a rough box around a player: read the
                                               fabric colour and the white off the list instead of guessing tiny boxes);
                                               also prints each cluster as albedo against the brightest near-white cluster
  px.py tex KITDIR                             main colours of the decoded torso / pants / sleeve / socks textures
"""
import sys
import numpy as np
from PIL import Image
def lin(c): c = np.asarray(c, float) / 255; return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
def srgb(l): l = np.clip(np.asarray(l, float), 0, 1); return np.where(l <= 0.0031308, l * 12.92, 1.055 * l ** (1 / 2.4) - 0.055) * 255
def box(path, x, y, w, h):
    return np.asarray(Image.open(path).convert('RGB'))[y:y + h, x:x + w].reshape(-1, 3)
def hexs(c): return '#%02X%02X%02X' % tuple(int(round(v)) for v in c)
a = sys.argv
if a[1] == 'crop':
    im = Image.open(a[2]).convert('RGB'); x, y, w, h = map(int, a[3:7]); s = float(a[8]) if len(a) > 8 else 1
    c = im.crop((x, y, x + w, y + h))
    if s != 1: c = c.resize((round(w * s), round(h * s)), Image.LANCZOS if s < 1 or max(im.size) > 600 else Image.NEAREST)
    c.save(a[7]); print(a[7], c.size)
elif a[1] == 'med':
    p = box(a[2], *map(int, a[3:7])); print('median', hexs(np.median(p, 0)), 'mean', hexs(p.mean(0)), 'n', len(p))
elif a[1] == 'albedo':
    p = np.median(box(a[2], *map(int, a[3:7])), 0); w = np.median(box(a[2], *map(int, a[7:11])), 0)
    note = ' (WARNING: white reference is clipped or not white; estimate unreliable)' if w.max() > 250 or w.min() < 120 or w.max() - w.min() > 40 else ''
    print('colour', hexs(p), 'white ref', hexs(w), '-> estimated albedo', hexs(srgb(lin(p) / lin(w))), note)
elif a[1] == 'tex':
    for n in ('torso', 'pants', 'sleeve', 'socks00'):
        im = np.asarray(Image.open(f'{a[2]}/{n}.png').convert('RGB')).reshape(-1, 3)
        q = (im // 8) * 8 + 4
        u, c = np.unique(q, axis=0, return_counts=True); o = np.argsort(-c)[:6]
        print(n, ' '.join(f'{hexs(u[i])}:{100 * c[i] // len(im)}%' for i in o))
elif a[1] == 'clusters':
    p = box(a[2], *map(int, a[3:7])).astype(float); k = int(a[7]) if len(a) > 7 else 6
    rng = np.random.default_rng(1); c = p[rng.choice(len(p), k, replace=False)]
    for _ in range(25):
        d = ((p[:, None, :] - c[None]) ** 2).sum(2); lab = d.argmin(1)
        c = np.array([p[lab == i].mean(0) if (lab == i).any() else c[i] for i in range(k)])
    n = np.bincount(lab, minlength=k); order = np.argsort(-n)
    whites = [i for i in range(k) if c[i].min() > 150 and c[i].max() - c[i].min() < 45 and n[i] > 0.01 * len(p)]
    w = c[max(whites, key=lambda i: c[i].sum())] if whites else None
    print('white ref', hexs(w) if w is not None else 'none found', '(clipped: albedo too dark)' if w is not None and w.max() > 250 else '')
    for i in order:
        if n[i] == 0: continue
        print(f'{100 * n[i] / len(p):5.1f}%  seen {hexs(c[i])}' + (f'  albedo vs white {hexs(srgb(lin(c[i]) / lin(w)))}' if w is not None else ''))
