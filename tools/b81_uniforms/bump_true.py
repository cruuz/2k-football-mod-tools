#!/usr/bin/env python3
"""b81-uniforms Track B, second round. Noah on the first modern relief (2026-11-18): "The jersey looks overly sculpted
tbh, should be less obvious and more accurate to the real thing. Find more references."

What this season's game jerseys show (uniforms/bump/refs: 61 broadcast close-ups, 50 game photographs, 24 clubs):
  * at broadcast close-up distance the body is smooth: no weave, no holes; you see soft broad wrinkles, the collar,
    and at most a faint V line under the collar;
  * in game photographs (chest about 700 px wide): a thin V seam whose point sits just under the collar shield and
    whose arms rise gently to the armholes; a thin seam down each side of the front number and of the back number; a
    thin line across the back under the name plate; two small ribbed vents beside the shield; sparse pin holes over
    the body below the V (about 2 cm apart, each a millimetre or two: plain dark dots on white, hardly seen on dark);
    smooth shoulders; a plain or lightly gathered sleeve hem; folds that are broad, soft and shallow.
So the relief here is: the 2004 sculpt's folds, softened, with every 2004 construction detail (open mesh, piping, collar
ribs) lifted out; this season's seams as hairlines; the collar as a flat band with a low edge; the two vents; marks
barely raised; and, from level B up, the sparse pin holes. Nothing stands proud, nothing is stitched in relief.

Levels (all at the game's stock jersey strength 0.10, so the game program does not change):
  A  quiet     folds 0.60, seams 0.12, no pin holes      what a broadcast close-up shows
  B  middle    folds 0.80, seams 0.17, pin holes 0.16    what a game photograph shows
  C  fuller    folds 1.00, seams 0.23, pin holes 0.28    the 2004 fold depth, modern construction

  bump_true.py jersey LEVEL RETAIL_BUMP TORSO.png OUT.png
  bump_true.py sleeve LEVEL RETAIL_BUMP SLEEVE.png OUT.png [--mark-box x0,y0,x1,y1 ...]
  bump_true.py pants  LEVEL CURRENT_BUMP PANTS.png OUT.png [--mark-box ...] [--shield-box ...]
"""
import sys, argparse
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bump_nike import (UV, S, decode, slopes, from_height, reduce, dist_to, bevel, old_construction, neck_hole,
                       mark_mask, boxes)

LEVELS = {  # folds gain, fold blur (texels), seam depth, pin depth, collar edge, vent depth, mark rise, pants mark rise
    'A': dict(fold=0.60, blur=2.2, seam=0.12, pin=0.00, collar=0.20, vent=0.12, mark=0.10, pmark=0.06),
    'B': dict(fold=0.80, blur=1.8, seam=0.17, pin=0.16, collar=0.28, vent=0.17, mark=0.14, pmark=0.08),
    'C': dict(fold=1.00, blur=1.4, seam=0.23, pin=0.28, collar=0.36, vent=0.22, mark=0.18, pmark=0.10),
}


def hair(d, depth, width=0.75):
    """a seam as a hairline groove across its distance d (2x pixels): no stitching row, no raised edge"""
    return -depth * np.exp(-((d / S) / width) ** 2)


def blur2(sl, sigma):
    return np.stack([ndi.gaussian_filter(sl[..., i], sigma * S) for i in range(2)], -1)


def clean_sculpt(r, torso, on, shape):
    """the 2004 sculpt with the 2004 construction (mesh, piping, collar ribs, tab, word block) lifted out"""
    H, W = shape
    sl = slopes(r[..., :2])
    old = old_construction(r[..., :2])
    old_soft = ndi.gaussian_filter(ndi.binary_dilation(old, iterations=5 * S).astype(np.float64), 1.5 * S)
    hole = neck_hole(torso, (H, W))
    dhole = ndi.distance_transform_edt(~hole) / S
    collar_zone = np.clip(1.0 - (dhole - 9.0) / 5.0, 0, 1)
    sculpt = sl * (1 - old_soft)[..., None] + blur2(sl, 2.3) * old_soft[..., None]
    thin = ndi.binary_dilation(old & ~ndi.binary_opening(old, iterations=7 * S), iterations=4 * S)
    thin_soft = ndi.gaussian_filter(thin.astype(np.float64), 2.0 * S)[..., None]
    sculpt = sculpt * (1 - thin_soft) + blur2(sl, 4.5) * thin_soft
    sculpt = sculpt * (1 - collar_zone)[..., None] + blur2(sl, 5.0) * 0.6 * collar_zone[..., None]
    return sculpt, hole, dhole


def jersey(level, retail, torso):
    k = LEVELS[level]
    d = np.load(UV / 'uvpos_UNIF_jersey.npz')
    pos, on = d['pos'].astype(np.float64), d['mask']
    nrm = d['nrm'].astype(np.float64); nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True) + 1e-9
    H, W = on.shape
    x, y = pos[..., 0], pos[..., 1]; ax = np.abs(x)
    cols = np.arange(W)[None, :].repeat(H, 0); rows = np.arange(H)[:, None].repeat(W, 1)
    front_isl = cols < W * 0.535; back_isl = ~front_isl
    facing_f = nrm[..., 2] > 0.25; facing_b = nrm[..., 2] < -0.25
    r = decode(retail, (W, H))
    sculpt, hole, dhole = clean_sculpt(r, torso, on, (H, W))
    folds = blur2(sculpt, k['blur']) * k['fold']
    h = np.zeros((H, W))
    # the collar V and the shield under it
    fh = hole & front_isl
    vtip = rows[fh].max(); utip = cols[fh & (rows == vtip)].mean()
    du = np.abs(cols - utip) / S; dv = (rows - vtip) / S
    # the V seam: its point 5 texels under the shield's foot, arms rising gently to the armholes
    apex_r, apex_c = int(vtip + 11 * S), int(round(utip))
    y0 = float(np.median(y[apex_r - 1:apex_r + 2, apex_c - 2:apex_c + 3]))
    chev = y - (y0 + 0.22 * ax)
    m = on & front_isl & facing_f & (ax < 23.0) & (y > y0 - 2) & (y < 63.0)
    h += hair(dist_to(chev, m), k['seam'])
    below = chev < -0.3
    fl = ax - (9.4 + 0.045 * (y - 10))                                        # the seam down each side of the front number
    m = on & front_isl & facing_f & below & (ax < 16) & (ax > 5)
    h += hair(dist_to(fl, m), k['seam'])
    # the back: a line under the name plate, a seam down each side of the number
    yoke = y - 54.2
    m = on & back_isl & facing_b & (ax < 23.0) & (y > 50) & (y < 58)
    h += hair(dist_to(yoke, m), k['seam'])
    bl = ax - (11.2 + 0.03 * (y - 10))
    m = on & back_isl & facing_b & (y < 54.0) & (ax < 17) & (ax > 6)
    h += hair(dist_to(bl, m), k['seam'])
    # the collar: a flat band, one low edge
    h += np.where(on, k['collar'] * np.clip((4.4 - dhole) / 1.2, 0, 1) * np.clip(dhole / 0.8, 0, 1), 0)
    # the two ribbed vents beside the shield: fine slanted slits, leaning away from the shield
    vent = on & front_isl & (dhole > 4.6) & (du > 4.2) & (du < 13.0) & (dv > -8.5 + 0.55 * du) & (dv < 3.5 - 0.15 * du)
    side = np.sign(cols - utip)
    slit = np.sin((cols * side + rows * 0.8) * np.pi / (1.25 * S))
    soft = np.clip(ndi.distance_transform_edt(vent) / S / 1.2, 0, 1)
    h += np.where(vent, -k['vent'] * np.clip(slit, 0, 1) * soft, 0)
    # the shield: barely raised
    shield = on & (du < 3.0 - 0.28 * np.maximum(dv - 1.5, 0) ** 1.3) & (dv > -2.2) & (dv < 6.0) & (dhole > 0.3)
    h += bevel(shield, k['mark'], 1.0)
    # sparse pin holes over the body below the V and below the back line (about 2 cm apart = 7 texels, staggered)
    if k['pin'] > 0:
        P = 7.0 * S
        v = rows / (P * 0.866); u = cols / P + 0.5 * (np.floor(v) % 2)
        rr = np.hypot((u - np.floor(u) - 0.5) * P, (v - np.floor(v) - 0.5) * P * 0.866) / S
        pit = -k['pin'] * np.clip(1.0 - (rr / 0.8) ** 2, 0, 1)
        body = on & (((front_isl & (chev < -1.2)) | (back_isl & (yoke < -1.2)))) & (y > 11.5) & (dhole > 6)
        edge = np.clip((ndi.distance_transform_edt(body) / S - 1.5) / 2.0, 0, 1)
        h += np.where(body, pit * edge, 0)
    h = ndi.gaussian_filter(h, 0.5)
    total = folds + from_height(h)
    total[~ndi.binary_dilation(on, iterations=3 * S)] = 0
    return reduce(total)


def sleeve(level, retail, sleeve_png, mark_boxes=()):
    """the master sleeve's folds, softened; a plain hem as one hairline; the painted maker's mark barely raised"""
    k = LEVELS[level]
    H = W = 128 * S
    r = decode(retail, (W, H)); sl = blur2(slopes(r[..., :2]), max(k['blur'], 1.6)) * k['fold']
    rows = np.arange(H)[:, None].repeat(W, 1)
    h = np.zeros((H, W))
    for top in (0, 64 * S):
        t = (rows - top) / S
        island = (t >= 0) & (t < 64)
        sl = sl * np.clip((59.0 - t) / 3.0, 0, 1)[..., None] * island[..., None] + sl * (~island)[..., None]
        h += np.where(island, -k['seam'] * np.exp(-((t - 58.0) / 0.75) ** 2), 0)
    if mark_boxes:
        h += bevel(mark_mask(sleeve_png, mark_boxes, (H, W)), k['mark'], 1.0)
    h = ndi.gaussian_filter(h, 0.5)
    return reduce(sl + from_height(h))


def pants(level, current, pants_png, mark_boxes=(), shield_boxes=(), old_boxes=((86, 36, 110, 56), (398, 36, 426, 56))):
    """the pants sculpt kept as it is; the 2004 shield and Reebok embosses lifted out; the painted maker's mark and
    shield barely raised where the colour texture has them"""
    k = LEVELS[level]
    H, W = 256 * S, 512 * S
    r = decode(current, (W, H)); sl = slopes(r[..., :2])
    for x0, y0, x1, y1 in old_boxes:
        soft = np.zeros((H, W)); soft[y0 * S:y1 * S, x0 * S:x1 * S] = 1
        soft = ndi.gaussian_filter(soft, 1.5 * S)[..., None]
        sl = sl * (1 - soft) + blur2(sl, 4.0) * soft
    h = np.zeros((H, W))
    for bx in (mark_boxes or ((80, 22, 116, 40),), shield_boxes or ((402, 26, 420, 42),)):
        h += bevel(mark_mask(pants_png, bx, (H, W)), k['pmark'], 1.0)
    h = ndi.gaussian_filter(h, 0.5)
    return reduce(sl + from_height(h))


def keep_exact(new, base_png, boxes_, pad=4):
    """pants only: outside the boxes that were worked the map keeps the base map's exact bytes"""
    from PIL import Image
    base = np.asarray(Image.open(base_png).convert('RGBA')).copy()
    for x0, y0, x1, y1 in boxes_:
        base[max(y0 - pad, 0):y1 + pad, max(x0 - pad, 0):x1 + pad] = new[max(y0 - pad, 0):y1 + pad, max(x0 - pad, 0):x1 + pad]
    base[..., 3] = 255
    return base


if __name__ == '__main__':
    from PIL import Image
    p = argparse.ArgumentParser(); p.add_argument('part', choices=['jersey', 'sleeve', 'pants'])
    p.add_argument('level', choices=list(LEVELS)); p.add_argument('bump'); p.add_argument('texture'); p.add_argument('out')
    p.add_argument('--mark-box', action='append', default=[]); p.add_argument('--shield-box', action='append', default=[])
    a = p.parse_args()
    if a.part == 'jersey':
        im = jersey(a.level, a.bump, a.texture)
    elif a.part == 'sleeve':
        im = sleeve(a.level, a.bump, a.texture, boxes(a.mark_box))
    else:
        old = ((86, 36, 110, 56), (398, 36, 426, 56))
        mb, sb = boxes(a.mark_box) or [(80, 22, 116, 40)], boxes(a.shield_box) or [(402, 26, 420, 42)]
        im = keep_exact(pants(a.level, a.bump, a.texture, mb, sb, old), a.bump, list(old) + mb + sb)
    Image.fromarray(im).save(a.out)
    n = im[..., :2].astype(float) / 127.5 - 1.0; tilt = np.hypot(n[..., 0], n[..., 1]) * 127
    print(a.part, a.level, a.out, 'tilt median %.1f p90 %.1f p99 %.1f max %.0f of 127' % (np.median(tilt[tilt > 0.5]) if (tilt > 0.5).any() else 0,
          np.percentile(tilt, 90), np.percentile(tilt, 99), tilt.max()))
