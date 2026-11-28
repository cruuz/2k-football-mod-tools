"""The Ravens' dark alternate helmet ("ALT 2" in 2026): the real front-facing raven mark in place of beta 80's stand-in
drawing, the 2004 logo's wings that still showed beside it, and the black squares left around the screws.

Source of the mark: the helmet as drawn on Wikipedia's 2026 Ravens uniform diagram (Wikimedia Commons file "Baltimore
Ravens Uniforms (2026).png"), lifted at about 240 px. Nothing here is drawn by hand: the shape and its three colours are the
reference's, scaled to the size and place the old drawing had."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet, fixtex
from scipy import ndimage
from PIL import Image
REF = C.WORK.parent / 'refs' / 'bal_dark' / 'uniforms2026.png'
BOX = (5250, 40, 5850, 640)
HEIGHT = 51        # texels: the height beta 80's drawing had on the modern shell; the same on both shells
_m = {}
def mark():
    """RGBA of the mark, cut from the reference along its own grey outline."""
    if 'm' not in _m:
        a = np.asarray(Image.open(REF).convert('RGB').crop(BOX)).astype(np.float64)
        lum = a @ np.array([0.299, 0.587, 0.114])
        red = (a[..., 0] > 120) & (a[..., 1] < 70)
        m = (lum > 55) | red
        lab, n = ndimage.label(m)
        best = None
        for i in range(1, n + 1):
            ys, xs = np.nonzero(lab == i)
            if ys.min() == 0 or xs.min() == 0 or ys.max() == a.shape[0] - 1 or xs.max() == a.shape[1] - 1: continue
            if best is None or len(ys) > best[0]: best = (len(ys), i)
        ring = lab == best[1]
        alpha = ndimage.binary_fill_holes(ring)
        ys, xs = np.nonzero(alpha); y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        rgba = np.dstack([a, alpha * 255.0])[y0:y1, x0:x1]
        _m['m'] = np.clip(rgba, 0, 255).astype(np.uint8)
    return _m['m']
def hw_core(fam):
    m = ndimage.binary_dilation(texdet.hardware(fam)[1] > 8, iterations=1)
    if fam == 'helmet02':
        for v in fixtex.vent_regions(): m &= ~ndimage.binary_dilation(v, iterations=3)
        m &= ~ndimage.binary_dilation(fixtex.diamond_region(), iterations=3)
    return m
def old_drawing(rgb, fam, upper):
    """Bounding box of beta 80's drawing in one panel: its lighter-than-shell outline and beak and the red eyes."""
    z = texdet.zone_mask(fam) & ~hw_core(fam)
    shell = np.median(rgb[texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]], axis=0)
    lum = rgb @ np.array([0.299, 0.587, 0.114]); sl = float(shell @ np.array([0.299, 0.587, 0.114]))
    red = (rgb[..., 0] > 120) & (rgb[..., 1] < 80)
    m = z & ((lum > sl + 12) | red)
    rows = np.arange(256)[:, None]
    m &= (rows < 128) if upper else (rows >= 128)
    m[:, :36] = False; m[:, 126:] = False
    lab, n = ndimage.label(ndimage.binary_dilation(m, iterations=2))
    sizes = ndimage.sum(m, lab, np.arange(1, n + 1)); big = lab == (1 + int(np.argmax(sizes)))
    ys, xs = np.nonzero(big & m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
def apply(name, T):
    fam = name.split('_')[0]
    rgb = T[..., :3].astype(np.float64); out = rgb.copy()
    zone = texdet.zone_mask(fam); core = hw_core(fam)
    shell = np.median(rgb[zone & ~texdet.hardware(fam)[0]], axis=0)
    dev = np.linalg.norm(rgb - shell, axis=2)
    paint = np.zeros((256, 256), bool); places = []
    for upper in (False, True):
        x0, y0, x1, y1 = old_drawing(rgb, fam, upper); places.append((upper, x0, y0, x1, y1))
        box = np.zeros((256, 256), bool); box[max(0, y0 - 18):y1 + 18, max(0, x0 - 30):min(142, x1 + 30)] = True
        box &= (np.arange(256)[:, None] < 128) if upper else (np.arange(256)[:, None] >= 128)
        paint |= box & zone & ~core & (dev > 3.0)
    side = zone.copy(); side[:, 142:] = False
    paint |= side & ~core & (rgb.max(axis=2) < 30.0) & (dev > 12.0)        # squares of the old black shell
    not_shell = (dev > 12.0) | paint
    a = fixtex.nn_fill(out, paint, keep_out=not_shell); b = fixtex.fill(a, paint, keep_out=not_shell)
    out[paint] = 0.5 * a[paint] + 0.5 * b[paint]
    changed = paint.copy(); M = mark()
    for upper, x0, y0, x1, y1 in places:
        h = HEIGHT; w = max(1, int(round(h * M.shape[1] / M.shape[0])))
        m = np.asarray(Image.fromarray(M).resize((w, h), Image.LANCZOS)).astype(np.float64)
        if upper: m = m[::-1]
        cx = (x0 + x1) / 2.0; px = int(round(cx - w / 2.0)); py = int(round((y0 + y1) / 2.0 - h / 2.0))
        al = m[..., 3:4] / 255.0
        region = out[py:py + h, px:px + w]
        ok = ~core[py:py + h, px:px + w]
        blend = region * (1 - al) + m[..., :3] * al
        region[ok] = blend[ok]
        changed[py:py + h, px:px + w] |= (al[..., 0] > 0.02) & ok
    pal = np.unique(T[..., :3].reshape(-1, 3), axis=0)
    res = T.copy(); snapped = fixtex.nearest_palette(out[changed], pal)
    err = float(np.abs(snapped.astype(np.float64) - out[changed]).max(axis=1).mean())
    res[changed, :3] = snapped
    return res, changed, dict(places=places, palette=len(pal), mean_snap_error=round(err, 2))
if __name__ == '__main__':
    import fixtex2
    tiles = []
    for n in ('helmet02_02H3', 'helmet00_02H3'):
        T, res0, d, masks = fixtex2.cleanup(n)
        res, ch, info = apply(n, res0); print(n, info, int(ch.sum()))
        tiles.append(C.hstack([C.up(res[132:232, 20:142, :3], 4), C.up(res[24:124, 20:142, :3], 4)], gap=3))
    Image.fromarray(np.concatenate(tiles, axis=0)).save(C.WORK / 'view_bal_dark.png')
