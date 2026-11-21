"""b81-retail-free-art (ruling 1 and 2): the Saints sleeve fleur drawn at build time from the mod's own emblem.

Order R2-C item 4 redrew the sleeve fleur-de-lis from the repo's Saints emblem (data/nfl2k5_scorebug_assets/logos/
no.png, the mod's own logo) at the emblem's proportions, at the old fleur's height and centre, in colours fitted to the
old fleur and snapped to colours the sleeve already holds (uniforms/work/fix/R2C/tools/nopaint.py). Those colours and
that place come from the sleeve itself, so they are not shipped: this rule finds the old fleur on the texture the build
holds, fits the colours there, renders the emblem and snaps every texel to the sleeve's own colours, as nopaint.py did.
Shipped per half: the rows of the half, the render size (nh x nw texels: the order's "same height, emblem proportions",
chosen on the player model when the art was made) and the facing.

Exact arithmetic, the same on every platform: the emblem reduction is Pillow's BOX resample written out (double
accumulation, float32 storage, horizontal then vertical); every sum is written in a fixed order; the one-column least
squares fit is the closed form; medians are of integers. No library resampling, BLAS or LAPACK at build time.
Reached from nfl2k5_kit_fixes_2026.paint as {"op": "rule", "module": "emblem", ...}."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "data"
GOLD = (0xDC, 0xBD, 0x8C)


def _require(condition, message):
    if not condition:
        raise ValueError("2026 sleeve emblem: " + message)


def _png_rgba(path):
    from PIL import Image
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA")).astype(np.float64)


def _coeffs(in_size, out_size):
    """Pillow's precompute_coeffs for the BOX filter (support 0.5), in double."""
    scale = float(in_size) / out_size
    filterscale = max(scale, 1.0)
    support = 0.5 * filterscale
    out = []
    for xx in range(out_size):
        center = (xx + 0.5) * scale
        ss = 1.0 / filterscale
        xmin = max(int(center - support + 0.5), 0)
        xmax = min(int(center + support + 0.5), in_size) - xmin
        k = []
        ww = 0.0
        for x in range(xmax):
            t = (x + xmin - center + 0.5) * ss
            w = 1.0 if (t > -0.5 and t <= 0.5) else 0.0
            k.append(w)
            ww += w
        if ww != 0.0:
            k = [w / ww for w in k]
        out.append((xmin, k))
    return out


def _box_resize(image, width, height):
    """Image.fromarray(image.astype(float32), 'F').resize((width, height), Image.BOX), written out."""
    a = np.asarray(image, np.float32)
    h, w = a.shape
    if width != w:
        tmp = np.zeros((h, width), np.float32)
        for xx, (xmin, k) in enumerate(_coeffs(w, width)):
            ss = np.zeros(h, np.float64)
            for x, kx in enumerate(k):
                ss = ss + a[:, xmin + x].astype(np.float64) * kx
            tmp[:, xx] = ss.astype(np.float32)
        a = tmp
    if height != h:
        tmp = np.zeros((height, a.shape[1]), np.float32)
        for yy, (ymin, k) in enumerate(_coeffs(h, height)):
            ss = np.zeros(a.shape[1], np.float64)
            for y, ky in enumerate(k):
                ss = ss + a[ymin + y].astype(np.float64) * ky
            tmp[yy] = ss.astype(np.float32)
        a = tmp
    return a


def _label(mask, eight=True):
    """Connected components in raster order of first texel (scipy.ndimage.label numbering), integers only."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int64)
    n = 0
    steps = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)] if eight else \
        [(-1, 0), (0, -1), (0, 1), (1, 0)]
    for y in range(h):
        for x in range(w):
            if mask[y, x] and not lab[y, x]:
                n += 1
                lab[y, x] = n
                stack = [(y, x)]
                while stack:
                    cy, cx = stack.pop()
                    for dy, dx in steps:
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                            lab[ny, nx] = n
                            stack.append((ny, nx))
    return lab, n


def _fill_holes(mask):
    """scipy.ndimage.binary_fill_holes: background not 4-connected to the border is filled."""
    h, w = mask.shape
    outside = np.zeros((h, w), bool)
    stack = [(y, x) for y in range(h) for x in (0, w - 1) if not mask[y, x]]
    stack += [(y, x) for x in range(w) for y in (0, h - 1) if not mask[y, x]]
    for y, x in stack:
        outside[y, x] = True
    while stack:
        cy, cx = stack.pop()
        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if 0 <= ny < h and 0 <= nx < w and not mask[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                stack.append((ny, nx))
    return ~outside


def _dilate_cross(mask):
    out = mask.copy()
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def _most_common(rgb):
    """collections.Counter(map(tuple, rgb.reshape(-1, 3))).most_common(1): ties go to the first seen."""
    flat = rgb.reshape(-1, 3).astype(np.int64)
    key = (flat[:, 0] << 16) | (flat[:, 1] << 8) | flat[:, 2]
    values, first, counts = np.unique(key, return_index=True, return_counts=True)
    best = max(range(len(values)), key=lambda i: (counts[i], -first[i]))
    return flat[first[best]].copy()


_MAPS = {}


def _emblem_maps(path):
    """The emblem split into its four colour classes, as alpha coverage maps (nopaint.py's classes)."""
    key = str(path)
    if key not in _MAPS:
        _MAPS[key] = _emblem_maps_uncached(path)
    return _MAPS[key]


def _emblem_maps_uncached(path):
    L = _png_rgba(path)
    ys, xs = np.nonzero(L[..., 3] > 8)
    L = L[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    al = L[..., 3] / 255
    rgb = L[..., :3]

    def dist(c):
        d = rgb - np.array(c, np.float64)
        return np.sqrt((d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1]) + d[..., 2] * d[..., 2])

    cls = np.stack([dist(GOLD), dist((255.0, 255.0, 255.0)), dist((0.0, 0.0, 0.0))], -1)
    lab = cls.argmin(-1)
    inked = al > 0.5
    ring = inked & (lab == 1)
    outside, _n = _label(~ring, eight=False)
    ext = outside == outside[0, 0]
    outer = (lab == 2) & ext
    inner = (lab == 2) & ~ext
    return [np.where(lab == 0, al, 0.0), np.where(lab == 1, al, 0.0), np.where(inner, al, 0.0),
            np.where(outer | ((lab == 2) & ~inked & ext), al, 0.0)]


def _reduce(maps, width, height, flip):
    red = np.stack([_box_resize(m, width, height) for m in maps], -1)
    return red[:, ::-1] if flip else red


def _old_fleur(off, swoosh, rows):
    half = np.zeros(off.shape, bool)
    half[rows] = True
    fl = off & ~swoosh & half
    lab, n = _label(fl)
    sz = np.bincount(lab.ravel(), minlength=n + 1).astype(np.float64)
    sz[0] = 0
    for i in range(1, n + 1):                       # a sleeve stripe (full width) is not the fleur
        yy, xx = np.nonzero(lab == i)
        if xx.max() - xx.min() > 60 or yy.max() - yy.min() < 12:
            sz[i] = 0
    return _fill_holes(lab == int(np.argmax(sz))), half


def apply(out, op, rgba, donors):
    """Draw the emblem on each half of the sleeve the build holds (``rgba``), as nopaint.py drew it."""
    _require(op.get("module") == "emblem", "not an emblem rule")
    a = np.asarray(rgba, np.uint8)
    t = a[..., :3].astype(np.int64)
    template = (donors or {}).get(op["template"])
    _require(template is not None, "the swoosh template sleeve is absent")
    tpl = np.asarray(template)[..., :3].astype(np.int64)
    tb = _most_common(tpl)
    swoosh = _dilate_cross(np.abs(tpl - tb).sum(-1) > 60)
    bg = _most_common(t)
    off = np.abs(t - bg).sum(-1) > 24
    maps = _emblem_maps(DATA / op["emblem"])
    pal = np.unique(t.reshape(-1, 3), axis=0).astype(np.float64)        # sorted, as sorted(set(...)) is
    res = np.asarray(out, np.uint8).copy()
    for half in op["halves"]:
        rows = slice(int(half["rows"][0]), int(half["rows"][1]))
        fl, hmask = _old_fleur(off, swoosh, rows)
        yy, xx = np.nonzero(fl)
        x0, x1, y0, y1 = xx.min(), xx.max() + 1, yy.min(), yy.max() + 1
        ow, oh = int(x1 - x0), int(y1 - y0)
        tt = t[y0:y1, x0:x1].astype(np.float64)
        core = tt[fl[y0:y1, x0:x1]]
        dark = bg.max() > 150
        if dark:
            F = np.median(core[core.max(-1) < 40], 0)
            known, free = {0: F, 1: F, 2: F}, 3
        else:
            F = np.median(core[core[:, 0] > 180], 0)
            known, free = {0: F, 2: bg.astype(np.float64), 3: bg.astype(np.float64)}, 1
        best = None
        for flip in (False, True):
            red = _reduce(maps, ow, oh, flip).astype(np.float64)
            C = red.reshape(-1, 4)
            T = tt.reshape(-1, 3) - bg
            rest = np.zeros_like(T)
            for k in sorted(known):
                rest = rest + C[:, k:k + 1] * (np.asarray(known[k], np.float64) - bg)
            c = C[:, free]
            denom = float(np.sum(c * c))
            x = np.array([float(np.sum(c * (T[:, j] - rest[:, j]))) / denom for j in range(3)])
            err = float(np.abs(C[:, free:free + 1] * x + rest - T).mean())
            if best is None or err < best[0]:
                best = (err, flip, x + bg)
        _err, flip, freecol = best
        _require(bool(half["flip"]) == flip, "the emblem's facing differs from the one the art was made with")
        colours = np.zeros((4, 3))
        for k, v in known.items():
            colours[k] = v
        colours[free] = np.clip(freecol, 0, 255)
        nh, nw = int(half["nh"]), int(half["nw"])
        lab, n = _label(fl & off)                       # the fleur's visible body: its rows give the centre row
        sizes = np.bincount(lab.ravel(), minlength=n + 1)
        sizes[0] = 0
        by = np.nonzero(lab == int(np.argmax(sizes)))[0]
        cy = (int(by.min()) + int(by.max()) + 1) / 2
        oy0 = int(round(cy - nh / 2))
        cx = (x0 + x1) / 2
        nx0 = int(round(cx - nw / 2))
        red = _reduce(maps, nw, nh, flip)
        clear = _dilate_cross(fl) & ~swoosh & hmask
        new = t.astype(np.float64)
        new[clear] = bg
        reg = new[oy0:oy0 + nh, nx0:nx0 + nw]
        cov = np.clip(((red[..., 0] + red[..., 1]) + red[..., 2]) + red[..., 3], 0, 1)[..., None]
        r64 = red.astype(np.float64)
        draw = (((r64[..., 0:1] * colours[0] + r64[..., 1:2] * colours[1]) + r64[..., 2:3] * colours[2])
                + r64[..., 3:4] * colours[3])
        reg[:] = draw + reg * (1 - cov)
        box = np.zeros(t.shape[:2], bool)
        box[oy0:oy0 + nh, nx0:nx0 + nw] = True
        box |= clear
        q = new[box]
        d = q[:, None, :] - pal[None, :, :]
        dist = (d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1]) + d[..., 2] * d[..., 2]
        new[box] = pal[np.argmin(dist, 1)]
        tried = a.copy()
        tried[..., :3][box] = new[box].astype(np.uint8)
        moved = tried[..., :3] != a[..., :3]
        res[..., :3][moved] = tried[..., :3][moved]
    return res
