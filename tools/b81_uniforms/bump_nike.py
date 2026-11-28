#!/usr/bin/env python3
"""b81-uniforms Track B (Noah 2026-11-18): "the old reebok jersey template 2k5 used had some artificial wrinkling and
nice depth with its sculpted mesh texture for jersey holes ... carefully craft a modernized nike version of that ...
using the sculpting and depth in a modernized way", and "the nike swoosh on jerseys gets its own bump texture replacing
the reebok texture bump and is in its proper location".

What the 2004 relief is (measured on the retail maps): tangent-space normals, R = +u, G = up, B = out, A unused;
  * sculpted folds over shoulders, armholes and the belly (median tilt about 14 of 127, strongest about 40);
  * an open mesh of pits on a 4-texel diagonal lattice, a trapezoid on the chest and a rectangle on the back (median
    tilt 45, pit walls to 78), framed by raised piping; a ribbed V collar; a shield tab and a word block under it;
  * on the pants (strength 0.3): pads, seams, belt loops, an embossed shield at the left hip and the Reebok vector at
    the right hip; on the sleeves: folds and, club by club, an embossed sleeve patch.
The jersey strength is 0.1 in the game program (sleeves share the number), so only steep relief reads: the new map is
built to the same steepness, never flatter.

The modern map keeps the 2004 SCULPT (its folds, untouched outside the old mesh and collar, lifted out from under the
mesh inside it) and replaces the 2004 CONSTRUCTION with this season's Nike body (bump/refs_nike, broadcast close-ups):
  * a flat stitched V collar with the small mesh grill either side of the shield, and the shield itself embossed;
  * the chevron seam across the upper chest; one long seam down each side of the front and the back, each with the short
    seam that breaks off toward the side; the stitched name plate (the 2004 plate, kept);
  * perforated side panels (outboard of the long seams, armhole to hem): round pits on a staggered 4-texel lattice, the
    same scale and depth as the 2004 mesh, so the sculpted depth stays but sits where a modern jersey breathes;
  * smooth chest, back and shoulders (where numbers and wordmarks sit);
  * the maker's mark embossed exactly under the painted one (found in the kit's own colour texture), on the sleeve or
    shoulder and on the pants, with the shield under the painted shield; every Reebok-era emboss is lifted out.

  bump_nike.py jersey RETAIL_BUMP TORSO.png OUT.png [--mark-box x0,y0,x1,y1 ...]
  bump_nike.py sleeve RETAIL_BUMP SLEEVE.png OUT.png [--mark-box ...]
  bump_nike.py pants  CURRENT_BUMP PANTS.png OUT.png
"""
import sys, argparse
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
UV = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/uvpos')
S = 2                                   # the height field is drawn at twice the native size


def decode(path, size=None):
    im = Image.open(path).convert('RGB')
    if size: im = im.resize(size, Image.BILINEAR)
    return np.asarray(im).astype(np.float64) / 127.5 - 1.0


def encode(nx, ny):
    nz = np.ones_like(nx)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    out = np.stack([nx / l, ny / l, nz / l], -1)
    return np.clip(np.round(out * 127.5 + 127.5), 0, 255).astype(np.uint8)


def slopes(nxy):
    """normal map xy (components of a unit normal) -> surface slopes (the same quantity a height gradient gives)"""
    nz = np.sqrt(np.clip(1.0 - (nxy ** 2).sum(-1), 0.04, 1.0))
    return nxy / nz[..., None]


def from_height(h):
    """height (native texel units, drawn on the 2x grid) -> slopes: +x tilts toward +u, +y toward image up"""
    gy, gx = np.gradient(h)
    return np.stack([-gx * S, gy * S], -1)


def reduce(slope):
    nx, ny = slope[..., 0], slope[..., 1]
    rgb = encode(nx, ny).astype(np.float64)
    h, w = rgb.shape[0] // S, rgb.shape[1] // S
    v = rgb.reshape(h, S, w, S, 3).mean(axis=(1, 3)) / 127.5 - 1.0
    v /= np.sqrt((v ** 2).sum(-1, keepdims=True)) + 1e-9
    rgb = np.clip(np.round(v * 127.5 + 127.5), 0, 255).astype(np.uint8)
    return np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])


def dist_to(f, where):
    """distance (2x pixels) to the zero line of f, inside ``where``"""
    gy, gx = np.gradient(f)
    return np.where(where, np.abs(f) / (np.hypot(gx, gy) + 1e-6), 1e3)


def seam(d):
    """a felled seam drawn across its distance d (2x pixels): a narrow groove with one raised row of stitching beside
    it. Heights in native texels; the groove wall is about as steep as the 2004 piping."""
    t = d / S
    return -1.0 * np.exp(-(t / 0.95) ** 2) + 0.42 * np.exp(-((t - 2.3) / 0.85) ** 2)


def bevel(mask, rise, soft):
    """a raised (rise > 0) or sunk shape with a soft shoulder ``soft`` native texels wide"""
    inside = ndi.distance_transform_edt(mask) / S
    return rise * np.clip(inside / soft, 0, 1)


def old_construction(xy):
    """where the 2004 map carries mesh, piping and collar ribs: fine relief a 1.6 texel blur removes"""
    lo = np.stack([ndi.gaussian_filter(xy[..., i], 1.6 * S) for i in range(2)], -1)
    energy = ndi.gaussian_filter(((xy - lo) ** 2).sum(-1), 3.0 * S)
    mesh = ndi.binary_opening(energy > 0.035, iterations=2 * S)
    lab, n = ndi.label(mesh)
    sizes = ndi.sum(mesh, lab, np.arange(1, n + 1))
    mesh = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s > 2500 * S * S])
    return ndi.binary_fill_holes(ndi.binary_closing(mesh, iterations=3 * S))


def neck_hole(torso, shape):
    t = np.asarray(Image.open(torso).convert('RGB').resize((shape[1], shape[0]), Image.NEAREST)).astype(int)
    rows = np.arange(shape[0])[:, None]
    grey = (np.abs(t - 220).max(-1) < 14) & (rows < shape[0] * 0.62)
    lab, n = ndi.label(grey)
    hole = np.zeros(shape, bool)
    for i in range(1, n + 1):
        part = lab == i
        if part.sum() > 100 * S * S and np.nonzero(part)[0].min() < 6 * S: hole |= part
    # the texture's one-texel staircase becomes a clean curve
    return ndi.gaussian_filter(hole.astype(np.float64), 0.8 * S) > 0.5


def mark_mask(texture, boxes, shape):
    """the painted maker's mark: texels inside the given boxes (native) that differ clearly from the fabric there"""
    t = np.asarray(Image.open(texture).convert('RGB')).astype(int)
    out = np.zeros(t.shape[:2], bool)
    for x0, y0, x1, y1 in boxes:
        part = t[y0:y1, x0:x1]
        flat = part.reshape(-1, 3)
        colours, counts = np.unique(flat, axis=0, return_counts=True)
        base = colours[counts.argmax()]
        out[y0:y1, x0:x1] = np.abs(part - base).max(-1) > 60
    out = ndi.binary_fill_holes(ndi.binary_closing(out, iterations=1)) | out      # a patch is one raised piece
    big = np.asarray(Image.fromarray((out * 255).astype(np.uint8)).resize((shape[1], shape[0]), Image.BILINEAR)) > 110
    return big


def jersey(retail, torso, mark_boxes=(), mesh_depth=0.95, fold_gain=1.25):
    d = np.load(UV / 'uvpos_UNIF_jersey.npz')
    pos, on = d['pos'].astype(np.float64), d['mask']
    nrm = d['nrm'].astype(np.float64); nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True) + 1e-9
    H, W = on.shape
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]; ax = np.abs(x)
    cols = np.arange(W)[None, :].repeat(H, 0); rows = np.arange(H)[:, None].repeat(W, 1)
    front_isl = cols < W * 0.535; back_isl = ~front_isl
    facing_f = nrm[..., 2] > 0.25; facing_b = nrm[..., 2] < -0.25
    r = decode(retail, (W, H)); sl = slopes(r[..., :2])
    # ---- 1. the 2004 sculpt with the 2004 construction lifted out
    old = old_construction(r[..., :2])
    old_soft = ndi.gaussian_filter(ndi.binary_dilation(old, iterations=5 * S).astype(np.float64), 1.5 * S)
    hole = neck_hole(torso, (H, W))
    dhole = ndi.distance_transform_edt(~hole) / S
    collar_zone = np.clip(1.0 - (dhole - 9.0) / 5.0, 0, 1)                    # ribs, tab and word block live here
    lifted = np.stack([ndi.gaussian_filter(sl[..., i], 2.3 * S) for i in range(2)], -1) * fold_gain
    flat = np.stack([ndi.gaussian_filter(sl[..., i], 5.0 * S) for i in range(2)], -1) * 0.6
    sculpt = sl * (1 - old_soft)[..., None] + lifted * old_soft[..., None]
    # the piping that ran from the panel corners to the shoulders is thin and steep: a wider lift where the old
    # construction is only a line (the mask less its own opening), so no ghost of it stays
    thin = ndi.binary_dilation(old & ~ndi.binary_opening(old, iterations=7 * S), iterations=4 * S)
    thin_soft = ndi.gaussian_filter(thin.astype(np.float64), 2.0 * S)[..., None]
    wide = np.stack([ndi.gaussian_filter(sl[..., i], 4.5 * S) for i in range(2)], -1)
    sculpt = sculpt * (1 - thin_soft) + wide * thin_soft
    sculpt = sculpt * (1 - collar_zone)[..., None] + flat * collar_zone[..., None]
    # ---- 2. this season's construction, as a height field
    h = np.zeros((H, W))
    chev = y - (50.2 + 0.50 * ax)
    m = on & front_isl & facing_f & (ax < 22.5) & (y > 44) & (y < 62.5)
    h += seam(dist_to(chev, m))
    below_chev = y < 50.2 + 0.50 * ax - 0.3
    fl = ax - (9.4 + 0.045 * (y - 10))                                        # the long front seam
    m = on & front_isl & facing_f & below_chev & (ax < 16) & (ax > 5)
    h += seam(dist_to(fl, m))
    fbreak = y - (30.0 + 0.55 * (ax - 10.3))                                  # its short seam toward the side
    m = on & front_isl & (fl > 0.15) & (y > 26) & (y < 40) & (nrm[..., 2] > -0.2)
    h += seam(dist_to(fbreak, m))
    bl = ax - (11.2 + 0.03 * (y - 10))                                        # the long back seam, from the plate down
    m = on & back_isl & facing_b & (y < 50.0) & (ax < 17) & (ax > 6)
    h += seam(dist_to(bl, m))
    bbreak = y - 33.0
    m = on & back_isl & (bl > 0.15) & (y > 29) & (y < 37) & (nrm[..., 2] < 0.2)
    h += seam(dist_to(bbreak, m))
    # the collar: a flat band with a stitched outer edge
    band = (dhole > 0) & (dhole <= 4.6) & on
    h += np.where(band, 0.85 * np.clip((4.6 - dhole) / 0.9, 0, 1) * np.clip(dhole / 0.7, 0, 1), 0)
    h += np.where(on, 0.32 * np.exp(-((dhole - 2.4) / 0.6) ** 2), 0)
    # the grill: the small panel under the V, fine diagonal mesh either side of the shield
    fh = hole & front_isl
    if fh.any():
        vtip = rows[fh].max(); utip = cols[fh & (rows == vtip)].mean()
        du = np.abs(cols - utip) / S; dv = (rows - vtip) / S
        grill = on & front_isl & (dhole > 4.6) & (dv > -13) & (dv < 6.5) & (du < 13.5 - 0.9 * np.maximum(dv, 0) + 0.35 * np.minimum(dv, 0)) & (du > 3.2)
        lat = np.sin((cols + rows) * np.pi / (1.6 * S)) * np.sin((cols - rows) * np.pi / (1.6 * S))
        h += np.where(grill, -0.55 * np.clip(lat, 0, 1), 0)
        edge = ndi.binary_dilation(grill, iterations=S) & ~grill & on & (dhole > 4.6)
        h += 0.5 * ndi.gaussian_filter(edge.astype(np.float64), 0.6 * S)
        shield = on & (du < 3.0 - 0.28 * np.maximum(dv - 1.5, 0) ** 1.3) & (dv > -2.2) & (dv < 6.0) & (dhole > 0.3)
        h += bevel(shield, 0.9, 0.9)
    # perforated side panels: round pits on a staggered lattice, armhole to hem, outboard of the long seams
    P = 4.0 * S
    def pits(region):
        v = rows / (P * 0.866); u = cols / P + 0.5 * (np.floor(v) % 2)
        du_, dv_ = (u - np.floor(u) - 0.5) * P, (v - np.floor(v) - 0.5) * P * 0.866
        rr = np.hypot(du_, dv_) / S
        pit = -mesh_depth * np.clip(1.0 - (rr / 1.25) ** 2, 0, 1) ** 0.8
        edge_ = ndi.distance_transform_edt(region) / S
        return np.where(region, pit * np.clip((edge_ - 1.2) / 1.5, 0, 1), 0)
    # up into the armpit: the panel ends on a line that rises toward the side seam, as the underarm does
    side_f = on & front_isl & (fl > 0.9) & (y < 41.0 + 0.55 * (ax - 10.0)) & (y > 10.8) & (nrm[..., 1] < 0.55)
    side_b = on & back_isl & (bl > 0.9) & (y < 42.0 + 0.55 * (ax - 11.5)) & (y > 10.8) & (nrm[..., 1] < 0.55)
    h += pits(side_f) + pits(side_b)
    # the maker's mark on the shoulder cap, when this kit paints it on the jersey texture
    if mark_boxes:
        h += bevel(mark_mask(torso, mark_boxes, (H, W)) & on, 0.7, 0.8)
    h = ndi.gaussian_filter(h, 0.45)
    total = sculpt + from_height(h)
    total[~ndi.binary_dilation(on, iterations=3 * S)] = 0
    return reduce(total), dict(old_construction_texels=int(old.sum() / S / S), side_panel_texels=int((side_f | side_b).sum() / S / S))


def sleeve(retail, sleeve_png, mark_boxes=(), patch_boxes=()):
    """the 2004 sleeve sculpt (its folds) kept; a bound cuff added; the painted maker's mark embossed; an old club patch
    emboss inside ``patch_boxes`` lifted out"""
    r = decode(retail, (128 * S, 128 * S)); sl = slopes(r[..., :2])
    H = W = 128 * S
    rows = np.arange(H)[:, None].repeat(W, 1)
    for x0, y0, x1, y1 in patch_boxes:
        soft = np.zeros((H, W)); soft[y0 * S:y1 * S, x0 * S:x1 * S] = 1
        soft = ndi.gaussian_filter(soft, 2.0 * S)[..., None]
        sl = sl * (1 - soft) + np.stack([ndi.gaussian_filter(sl[..., i], 3.0 * S) for i in range(2)], -1) * soft
    h = np.zeros((H, W))
    for top in (0, 64 * S):
        t = (rows - top) / S
        island = (t >= 0) & (t < 64)
        sl = sl * np.clip((57.0 - t) / 2.0, 0, 1)[..., None] * island[..., None] + sl * (~island)[..., None]   # the bound cuff is flat
        h += np.where(island, 0.8 * np.clip((t - 58.2) / 0.9, 0, 1), 0)                 # the cuff band stands proud
        h += np.where(island, -0.9 * np.exp(-((t - 57.6) / 0.9) ** 2), 0)                # its seam
        h += np.where(island, 0.3 * np.exp(-((t - 61.0) / 0.7) ** 2), 0)                 # a row of stitching on it
    if mark_boxes:
        h += bevel(mark_mask(sleeve_png, mark_boxes, (H, W)), 0.7, 0.8)
    h = ndi.gaussian_filter(h, 0.45)
    return reduce(sl + from_height(h))


def pants(current, pants_png, old_boxes=((86, 36, 110, 56), (398, 36, 426, 56)), mark_boxes=None, shield_boxes=None):
    """the pants sculpt kept; the 2004 shield and Reebok embosses lifted out; the painted maker's mark and shield
    embossed where the colour texture has them"""
    r = decode(current, (512 * S, 256 * S)); sl = slopes(r[..., :2])
    H, W = 256 * S, 512 * S
    for x0, y0, x1, y1 in old_boxes:
        soft = np.zeros((H, W)); soft[y0 * S:y1 * S, x0 * S:x1 * S] = 1
        soft = ndi.gaussian_filter(soft, 1.5 * S)[..., None]
        sl = sl * (1 - soft) + np.stack([ndi.gaussian_filter(sl[..., i], 4.0 * S) for i in range(2)], -1) * soft
    t = np.asarray(Image.open(pants_png).convert('RGB')).astype(int)
    h = np.zeros((H, W))
    for boxes, rise in ((mark_boxes or ((80, 22, 116, 40),), 0.5), (shield_boxes or ((402, 26, 420, 42),), 0.5)):
        h += bevel(mark_mask(pants_png, boxes, (H, W)), rise, 0.8)
    h = ndi.gaussian_filter(h, 0.45)
    return reduce(sl + from_height(h))


def keep_exact(new, base_png, tolerance=3):
    """Texels the craft did not really move keep the base map's exact bytes (resampling alone shifts values by a level,
    and every such level costs room in the fixed span: these slots are stored compressed at a fixed size)."""
    base = np.asarray(Image.open(base_png).convert('RGBA'))
    moved = (np.abs(new[..., :3].astype(int) - base[..., :3].astype(int)).max(-1) > tolerance)
    moved = ndi.binary_dilation(moved, iterations=1)
    out = base.copy(); out[moved] = new[moved]; out[..., 3] = 255
    return out, float(moved.mean())


def boxes(text):
    return [tuple(int(v) for v in b.split(',')) for b in text]


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('part', choices=['jersey', 'sleeve', 'pants'])
    p.add_argument('bump'); p.add_argument('texture'); p.add_argument('out')
    p.add_argument('--mark-box', action='append', default=[]); p.add_argument('--patch-box', action='append', default=[])
    a = p.parse_args()
    if a.part == 'jersey':
        im, info = jersey(a.bump, a.texture, boxes(a.mark_box)); print(info)
    elif a.part == 'sleeve':
        im = sleeve(a.bump, a.texture, boxes(a.mark_box), boxes(a.patch_box))
    else:
        im = pants(a.bump, a.texture)
    im, share = keep_exact(im, a.bump); print('texels redrawn: %.1f%%' % (100 * share))
    Image.fromarray(im, 'RGBA').save(a.out); print(a.out, im.shape)
