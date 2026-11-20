"""Exact build-time fill rules for the 2026 kit fixes (b81 retail-free lane, ruling 2: the "fill" family).

A fill erases an old mark and repaints the texels from the shading around it, as the b81-art helmet cleanup
(tools/b81_art/fixtex.py, tools/b81_helmet_cleanup.py) and the b81-uniforms mark removals did when they were authored.
Their documents stored the result as runs of texel colours: base content. Here the same result is computed at build
time from what the build holds: the row's input texture (``rgba``/``out``), its donors, and the blank retail shell the
Studio reads from the user's disc. Nothing in an operation is a texel position list or a per-texel colour: masks are
rules (boxes, colour thresholds, the retail shell's painted vents, the texture's own alpha) and the colours come from
the texture's own palette (plus, for a snap, the named palette entries the texture's mips hold).

Reached as ``{"op": "rule", "module": "fill", "kind": ..., ...}`` from ``nfl2k5_kit_fixes_2026.paint``:

kind "helmet"  the b81-art cleanup of a finished modern-shell helmet (helmet02): the 2004 Revolution vents painted
               beside the modern vents (their outline is the blank retail Cleveland shell's hardware, donor
               ``hardware``), the 2004 flag's outline (the texture's own transparent diamond, or a donor's), old logo
               pieces and old shell squares given as mask rules; harmonic or nearest-texel fill, the texture's own
               colours, then the palette entry of each texel's alpha.
kind "row"     each masked texel takes the colour of the nearest unmasked texel on its own row (ties to the left).

Arithmetic: integers, or IEEE float64 + - * / in a written-out order (the harmonic fill is a fixed number of Jacobi
sweeps with explicit neighbour sums; medians are exact middle values of sorted integers; the nearest-texel fill is
the separable Euclidean feature transform in integers). No float32, no library resampling, no unordered reduction.
"""
from __future__ import annotations

import numpy as np

JACOBI = 1500                                   # harmonic sweeps after the outside-in start (as the authoring fill)
ZONE = (6, 16, 146, 240)                        # x0, y0, x1, y1: the two side panels of the helmet02 atlas
VENT_BOXES = ((32, 104, 60, 124), (70, 110, 96, 126), (70, 128, 96, 144), (32, 132, 60, 152),
              (102, 90, 124, 114), (102, 142, 124, 166))   # 4 crown crescents, 2 rear slits of the 2004 shell
VENT_ABOVE = 10                                 # a vent texel: largest RGB step from the shell above this
HARDWARE_ABOVE = 8                              # shell hardware (screws, vents, creases): above this, grown by 2
FLAG_BOX = (95, 90, 150, 165)                   # where the 2004 flag sat on the back of the shell
FLAG_ALPHA = 128                                # the 2026 art keeps the flag's place transparent (alpha below this)
NEIGHBOURS8 = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
NEIGHBOURS4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def _require(ok, message):
    if not ok:
        raise ValueError("2026 kit fill rule: " + message)


def _hex(text):
    text = text.lstrip("#")
    _require(len(text) == 6, "colour must be #RRGGBB")
    return np.array([int(text[i:i + 2], 16) for i in (0, 2, 4)], np.int64)


# ---------------------------------------------------------------------------------------------- masks and morphology
def _shifted(array, dy, dx, fill):
    out = np.full_like(array, fill)
    h, w = array.shape[:2]
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = array[max(-dy, 0):h + min(-dy, 0),
                                                                       max(-dx, 0):w + min(-dx, 0)]
    return out


def dilate8(mask, steps):
    out = mask.copy()
    for _ in range(int(steps)):
        grown = out.copy()
        for dy, dx in NEIGHBOURS8:
            grown |= _shifted(out, dy, dx, False)
        out = grown
    return out


def dilate4(mask, steps):
    out = mask.copy()
    for _ in range(int(steps)):
        grown = out.copy()
        for dy, dx in NEIGHBOURS4:
            grown |= _shifted(out, dy, dx, False)
        out = grown
    return out


def erode4(mask, steps):
    """Erosion by the 4-neighbour cross; outside the texture counts as unset."""
    out = mask.copy()
    for _ in range(int(steps)):
        kept = out.copy()
        for dy, dx in NEIGHBOURS4:
            kept &= _shifted(out, dy, dx, False)
        out = kept
    return out


def largest4(mask):
    """The largest 4-connected component (the first in raster order on a tie of sizes)."""
    h, w = mask.shape
    label = np.zeros((h, w), np.int64)
    sizes = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if label[y0, x0]:
            continue
        n = len(sizes) + 1
        label[y0, x0] = n
        stack, size = [(int(y0), int(x0))], 0
        while stack:
            y, x = stack.pop()
            size += 1
            for dy, dx in NEIGHBOURS4:
                v, u = y + dy, x + dx
                if 0 <= v < h and 0 <= u < w and mask[v, u] and not label[v, u]:
                    label[v, u] = n
                    stack.append((v, u))
        sizes.append(size)
    if not sizes:
        return mask.copy()
    best = max(range(len(sizes)), key=lambda i: (sizes[i], -i))
    return label == best + 1


def box_mask(shape, box):
    x0, y0, x1, y1 = (int(v) for v in box)
    _require(0 <= x0 < x1 <= shape[1] and 0 <= y0 < y1 <= shape[0], "box outside the texture")
    m = np.zeros(shape[:2], bool)
    m[y0:y1, x0:x1] = True
    return m


def mask_of(spec, src, refs=None):
    """A mask rule over the texture ``src`` (RGBA uint8). ``refs`` names masks computed earlier ("vents", "flag").
    Rules: {"box": [x0, y0, x1, y1]}; {"far": "#RRGGBB", "above": n} (largest RGB channel step above n);
    {"near": "#RRGGBB", "within": n}; {"far2": "#RRGGBB", "above": n} (squared RGB distance above n);
    {"dark": n} (every channel below n); {"alpha_below": n}; {"all": [...]}, {"any": [...]}, {"not": rule};
    {"grow": n, "of": rule} (8-neighbour steps; "cross": true for 4-neighbour); {"largest": rule}; {"ref": name}."""
    shape = src.shape[:2]
    rgb = src[..., :3].astype(np.int64)
    if "box" in spec:
        return box_mask(shape, spec["box"])
    if "far" in spec:
        return np.abs(rgb - _hex(spec["far"])).max(axis=2) > int(spec["above"])
    if "near" in spec:
        return np.abs(rgb - _hex(spec["near"])).max(axis=2) <= int(spec["within"])
    if "far2" in spec:
        d = rgb - _hex(spec["far2"])
        return (d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1] + d[..., 2] * d[..., 2]) > int(spec["above"])
    if "dark" in spec:
        return rgb.max(axis=2) < int(spec["dark"])
    if "alpha_below" in spec:
        return src[..., 3].astype(np.int64) < int(spec["alpha_below"])
    if "all" in spec:
        out = np.ones(shape, bool)
        for part in spec["all"]:
            out &= mask_of(part, src, refs)
        return out
    if "any" in spec:
        out = np.zeros(shape, bool)
        for part in spec["any"]:
            out |= mask_of(part, src, refs)
        return out
    if "not" in spec:
        return ~mask_of(spec["not"], src, refs)
    if "grow" in spec:
        inner = mask_of(spec["of"], src, refs)
        return dilate4(inner, spec["grow"]) if spec.get("cross") else dilate8(inner, spec["grow"])
    if "largest" in spec:
        return largest4(mask_of(spec["largest"], src, refs))
    if "ref" in spec:
        _require(refs is not None and spec["ref"] in refs, "unknown mask reference")
        return refs[spec["ref"]].copy()
    raise ValueError("2026 kit fill rule: unknown mask rule " + repr(sorted(spec)))


# ------------------------------------------------------------------------------------------------------------- fills
def harmonic_fill(rgb, unknown, known):
    """Fill ``unknown`` from ``known`` (float64 RGB): outside-in 8-neighbour means, then JACOBI sweeps of the
    4-neighbour Laplace equation (known texels fixed; neighbours that are neither are left out). Every sum is
    written out neighbour by neighbour in a fixed order."""
    out = rgb.copy()
    if not unknown.any():
        return out
    _require(known.any(), "a region has nothing around it to fill from")
    ys, xs = np.nonzero(unknown | known)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = out[y0:y1, x0:x1].copy()
    u, k = unknown[y0:y1, x0:x1], known[y0:y1, x0:x1] & ~unknown[y0:y1, x0:x1]
    have, todo = k.copy(), u.copy()
    while todo.any():
        total = np.zeros(sub.shape, np.float64)
        count = np.zeros(sub.shape[:2], np.float64)
        for dy, dx in NEIGHBOURS8:
            ok = _shifted(have, dy, dx, False)
            total += np.where(ok[..., None], _shifted(sub, dy, dx, 0.0), 0.0)
            count += ok
        ready = todo & (count > 0)
        if not ready.any():
            # texels cut off from everything known take the known texels' middle colour
            sub[todo] = _median_rows(sub[k])
            break
        sub[ready] = total[ready] / count[ready][:, None]
        have |= ready
        todo &= ~ready
    valid = u | k
    for _ in range(JACOBI):
        total = np.zeros(sub.shape, np.float64)
        count = np.zeros(sub.shape[:2], np.float64)
        for dy, dx in NEIGHBOURS4:
            ok = _shifted(valid, dy, dx, False)
            total += np.where(ok[..., None], _shifted(sub, dy, dx, 0.0), 0.0)
            count += ok
        new = total / np.maximum(count, 1.0)[..., None]
        sub[u] = new[u]
    out[y0:y1, x0:x1] = sub
    return out


def _median_rows(values):
    """Per-channel median of an (n, 3) float64 array (the two middle values of a sort, averaged)."""
    s = np.sort(values, axis=0)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _voronoi(feat, other, d):
    """One line of the Euclidean feature transform (separable, as scipy.ndimage's ni_morphology.c _VoronoiFT for
    rank 2 without sampling); integers only. ``feat`` holds [y, x] or [-1, 0] (no feature yet)."""
    o = 1 - d
    g = []
    for ii, fi in enumerate(feat):
        if fi[0] < 0:
            continue
        fd = fi[d]
        tw = fi[o] - other
        wr = tw * tw
        while len(g) >= 2:
            f1 = feat[g[-1]]
            f2 = feat[g[-2]]
            a = f1[d] - f2[d]
            b = fd - f1[d]
            c = a + b
            tu = f2[o] - other
            tv = f1[o] - other
            if c * (tv * tv) - b * (tu * tu) - a * wr - a * b * c <= 0:
                break
            g.pop()
        g.append(ii)
    if not g:
        return feat
    out = [None] * len(feat)
    best = 0
    last = len(g) - 1
    for ii in range(len(feat)):
        f = feat[g[best]]
        t0, t1 = f[d] - ii, f[o] - other
        delta1 = t0 * t0 + t1 * t1
        while best < last:
            f = feat[g[best + 1]]
            t0, t1 = f[d] - ii, f[o] - other
            delta2 = t0 * t0 + t1 * t1
            if delta1 <= delta2:
                break
            delta1 = delta2
            best += 1
        out[ii] = feat[g[best]]
    return out


def nearest_source(not_source):
    """(row, column) of the nearest source texel (False in ``not_source``) for every texel."""
    h, w = not_source.shape
    cols = []
    for x in range(w):
        cols.append(_voronoi([[-1, 0] if not_source[y, x] else [y, x] for y in range(h)], x, 0))
    iy = np.zeros((h, w), np.int64)
    ix = np.zeros((h, w), np.int64)
    for y in range(h):
        row = _voronoi([cols[x][y] for x in range(w)], y, 1)
        for x in range(w):
            iy[y, x], ix[y, x] = row[x]
    return iy, ix


def nearest_fill(rgb, paint, keep_out=None):
    """Every painted texel takes the colour of the nearest texel outside the region (and outside ``keep_out``)."""
    src = ~paint
    if keep_out is not None:
        src &= ~keep_out
    _require(src.any(), "nothing to fill from")
    iy, ix = nearest_source(~src)
    out = rgb.copy()
    out[paint] = rgb[iy[paint], ix[paint]]
    return out


def band_fill(rgb, paint, keep_out):
    """Harmonic fill of ``paint`` from the texels within two (else four) steps around it, not ``keep_out``."""
    band = dilate8(paint, 2) & ~paint & ~keep_out
    if band.sum() < 6:
        band = dilate8(paint, 4) & ~paint & ~keep_out
    return harmonic_fill(rgb, paint, band)


def clean_fill(rgb, paint, keep_out, soft, how):
    """A fill that draws from old ink (``soft``) only when nothing else is near; ``how`` "h" harmonic, "n" nearest."""
    ko = keep_out | soft
    if (dilate8(paint, 4) & ~paint & ~ko).sum() < 6:
        ko = keep_out
    if how == "n":
        return nearest_fill(rgb, paint, ko)
    _require(how == "h", "fill must be h (harmonic) or n (nearest)")
    return band_fill(rgb, paint, ko)


# ---------------------------------------------------------------------------------------------------------- palettes
def nearest_colour(values, palette):
    """Nearest palette row (int64 RGB) to each float64 RGB value by squared distance, first row on a tie."""
    pal = palette.astype(np.float64)
    best = np.zeros(len(values), np.int64)
    best_d = None
    for j in range(len(pal)):
        dr = values[:, 0] - pal[j, 0]
        dg = values[:, 1] - pal[j, 1]
        db = values[:, 2] - pal[j, 2]
        d = dr * dr + dg * dg
        d = d + db * db
        if best_d is None:
            best_d = d
            continue
        better = d < best_d
        best = np.where(better, j, best)
        best_d = np.where(better, d, best_d)
    return palette[best]


def unique_colours(rgb_u8, mask=None):
    """The distinct RGB colours (sorted by R, G, B), with their counts."""
    flat = rgb_u8.reshape(-1, 3) if mask is None else rgb_u8[mask]
    keys = (flat[:, 0].astype(np.int64) << 16) | (flat[:, 1].astype(np.int64) << 8) | flat[:, 2].astype(np.int64)
    vals, counts = np.unique(keys, return_counts=True)
    return np.stack([vals >> 16, (vals >> 8) & 255, vals & 255], axis=1).astype(np.int64), counts


def snap_to_alpha(colours, alphas, texture, extra):
    """Each colour as the nearest colour the texture holds at that texel's alpha (level 0, plus the ``extra`` palette
    entries [alpha, "#RRGGBB"] its mips hold), by integer squared distance; ties to the first by R, G, B."""
    out = np.zeros_like(colours)
    for alpha in np.unique(alphas):
        have = texture[..., 3] == alpha
        cand, _ = unique_colours(texture[..., :3], have)
        more = [_hex(c) for a, c in extra if int(a) == int(alpha)]
        if more:
            cand = np.unique(np.concatenate([cand, np.array(more, np.int64)]), axis=0)
        _require(len(cand) > 0, "no colour at this alpha")
        pick = alphas == alpha
        c = colours[pick]
        d = ((c[:, None, :] - cand[None, :, :]) ** 2).sum(axis=2)
        out[pick] = cand[d.argmin(axis=1)]
    return out


# ---------------------------------------------------------------------------------------------------- helmet shells
def _median_int(values):
    """Twice the per-channel median of an (n, 3) int64 array (exact)."""
    s = np.sort(values, axis=0)
    n = len(s)
    return 2 * s[n // 2] if n % 2 else s[n // 2 - 1] + s[n // 2]


def shell_hardware(blank, zone=ZONE):
    """(twice the shell colour, largest-step deviation times two) of a blank shell (RGBA): the shell is the middle
    colour of the side panels (``zone``)."""
    x0, y0, x1, y1 = zone
    rgb = blank[..., :3].astype(np.int64)
    shell2 = _median_int(rgb[y0:y1, x0:x1].reshape(-1, 3))
    dev2 = np.abs(2 * rgb - shell2).max(axis=2)
    return shell2, dev2


def vent_masks(blank):
    """The six painted 2004 vents: in each box the largest 4-connected piece of the blank shell's texels more than
    VENT_ABOVE from the shell, grown by two 4-neighbour steps."""
    _shell2, dev2 = shell_hardware(blank)
    out = []
    for x0, y0, x1, y1 in VENT_BOXES:
        m = np.zeros(dev2.shape, bool)
        m[y0:y1, x0:x1] = dev2[y0:y1, x0:x1] > 2 * VENT_ABOVE
        out.append(dilate4(largest4(m), 2))
    return out


def hardware_mask(blank, zone=ZONE):
    """Everything that is not flat shell on the blank shell (screws, vents, ear holes, creases, the flag), grown by 2,
    with the six painted vents taken out (on the 2026 shell they are no longer hardware)."""
    _shell2, dev2 = shell_hardware(blank, zone)
    hw = dilate4(dev2 > 2 * HARDWARE_ABOVE, 2)
    for m in vent_masks(blank):
        hw &= ~dilate4(m, 2)
    return hw


def flag_masks(source, paint):
    """The 2004 flag's place (the transparent diamond of ``source``) and what is repainted: its outline ring (three
    steps out, two in) or, with paint "full", the ring and the inside."""
    x0, y0, x1, y1 = FLAG_BOX
    d = np.zeros(source.shape[:2], bool)
    d[y0:y1, x0:x1] = source[y0:y1, x0:x1, 3] < FLAG_ALPHA
    _require(d.any(), "the flag donor has no transparent diamond")
    ring = dilate4(d, 3) & ~erode4(d, 2)
    return d, (ring | d) if paint == "full" else ring


def _donor(donors, key):
    texture = (donors or {}).get(key)
    _require(texture is not None, "donor texture absent: " + str(key))
    return texture


def helmet(out, op, donors):
    """See the module text; ``op``: hardware (donor key of the blank retail shell), vents ("hhhhhh": per vent h
    harmonic, n nearest, - none), keep (mask rule: the 2026 logo kept out of the vents' fills), flag ({"from":
    "self" or a donor key, "paint": "ring" | "full", "how": "h" | "n"}), boxes / old (mask rules: old shell squares,
    old logo ink; see the code), shell (palette rule for repaired shell beside old ink), snap ([alpha, "#RRGGBB"]
    palette entries of the texture's mips)."""
    texture = out
    shape = texture.shape[:2]
    rgb = texture[..., :3].astype(np.float64)
    work = rgb.copy()
    blank = _donor(donors, op["hardware"])
    _require(blank.shape == texture.shape, "the blank shell is not this texture's size")
    zone = tuple(int(v) for v in op.get("zone", ZONE))      # the side panels: (6, 16, 150, 240) on the Standard shell
    refs = {}
    keep = mask_of(op["keep"], texture) if op.get("keep") else np.zeros(shape, bool)
    old = mask_of(op["old"], texture) if op.get("old") else np.zeros(shape, bool)
    boxes = mask_of(op["boxes"], texture) if op.get("boxes") else np.zeros(shape, bool)
    soft = old | boxes
    changed = np.zeros(shape, bool)
    how = op.get("vents", "------")
    _require(len(how) == len(VENT_BOXES), "vents names one fill per vent")
    vents = np.zeros(shape, bool)
    for m0, h in zip(vent_masks(blank) if how.strip("-") else [None] * len(how), how):
        if h == "-":
            continue
        m = m0 & ~keep
        if not m.any():
            continue
        work = clean_fill(work, m, keep, soft & ~m, h)
        vents |= m
    refs["vents"] = vents
    changed |= vents
    flag = op.get("flag")
    if flag:
        source = texture if flag["from"] == "self" else _donor(donors, flag["from"])
        _d, paint = flag_masks(source, flag.get("paint", "ring"))
        work = clean_fill(work, paint, np.zeros(shape, bool), soft & ~paint, flag["how"])
        refs["flag"] = paint
        changed |= paint
    if boxes.any():
        # old shell-colour squares: only texels of today's shell colour may fill them (nearest, then half harmonic)
        shell2 = _shell_of(texture, blank, zone)
        d = 2 * work - shell2
        not_shell = (d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1] + d[..., 2] * d[..., 2]) > 4 * 45.0 * 45.0
        work = nearest_fill(work, boxes, not_shell | keep)
        smooth = band_fill(work, boxes, not_shell | keep)
        work[boxes] = 0.5 * work[boxes] + 0.5 * smooth[boxes]
        changed |= boxes
        old = old & ~boxes
    if old.any():
        work = band_fill(work, old, keep)
        changed |= old
    res = texture.copy()
    if changed.any():
        pal, _ = unique_colours(texture[..., :3])
        res[changed, :3] = nearest_colour(work[changed], pal).astype(np.uint8)
        if soft.any():
            res = _shell_palette(res, texture, work, changed, blank, zone)
    moved = (res[..., :3] != texture[..., :3]).any(axis=2)
    if moved.any():
        snapped = snap_to_alpha(res[moved][:, :3].astype(np.int64), texture[moved][:, 3], texture, op.get("snap", []))
        res[moved, :3] = snapped.astype(np.uint8)
    return res


def _shell_of(texture, blank, zone=ZONE):
    """Twice the 2026 shell colour: the middle colour of the side panels away from the blank shell's hardware."""
    x0, y0, x1, y1 = zone
    inside = np.zeros(texture.shape[:2], bool)
    inside[y0:y1, x0:x1] = True
    return _median_int(texture[..., :3].astype(np.int64)[inside & ~hardware_mask_raw(blank, zone)])


def hardware_mask_raw(blank, zone=ZONE):
    """The blank shell's hardware grown by 2 (vents included)."""
    _shell2, dev2 = shell_hardware(blank, zone)
    return dilate4(dev2 > 2 * HARDWARE_ABOVE, 2)


def _shell_palette(res, texture, work, changed, blank, zone_box=ZONE):
    """Repaired shell beside old ink takes only colours the plain shell already uses (at least 6 texels of it): a
    logo-edge blend from the whole palette would leave a tinted cloud where the old piece was."""
    x0, y0, x1, y1 = zone_box
    zone = np.zeros(texture.shape[:2], bool)
    zone[y0:y1, x0:x1] = True
    rgb = texture[..., :3].astype(np.int64)
    shell2 = _median_int(rgb[zone & ~hardware_mask_raw(blank, zone_box)])
    d = 2 * rgb - shell2
    dev = d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1] + d[..., 2] * d[..., 2]          # (2 * distance) squared
    plain = zone & ~changed & (dev < 4 * 45 * 45) & ~dilate4(zone & (dev > 4 * 30 * 30), 3)
    cols, counts = unique_colours(texture[..., :3], plain)
    pal_shell = cols[counts >= 6]
    w = 2 * work - shell2
    m = changed & ((w[..., 0] * w[..., 0] + w[..., 1] * w[..., 1] + w[..., 2] * w[..., 2]) < 4 * 45.0 * 45.0)
    if len(pal_shell) >= 2 and m.any():
        res[m, :3] = nearest_colour(work[m], pal_shell).astype(np.uint8)
    return res


# --------------------------------------------------------------------------------------------------- row fill
def row_fill(out, op):
    """Every texel of the mask takes the colour of the nearest texel off the mask on its own row (ties to the
    left); the colours are the texture's own."""
    mask = mask_of(op["mask"], out)
    res = out.copy()
    h, w = mask.shape
    for y in range(h):
        xs = np.flatnonzero(mask[y])
        if not len(xs):
            continue
        keep = np.flatnonzero(~mask[y])
        _require(len(keep) > 0, "a row with nothing to fill from")
        right = np.searchsorted(keep, xs)
        left = right - 1
        has_left = left >= 0
        has_right = right < len(keep)
        lx = np.where(has_left, keep[np.maximum(left, 0)], -10 ** 9)
        rx = np.where(has_right, keep[np.minimum(right, len(keep) - 1)], 10 ** 9)
        pick = np.where(xs - lx <= rx - xs, lx, rx)
        res[y, xs, :3] = out[y, pick, :3]
    return res


def apply(out, op, rgba, donors):
    """The fill rule ``op`` on ``out`` (the texture so far); ``rgba`` is the row's input level 0, ``donors`` its
    donor textures by key."""
    kind = op.get("kind")
    if kind == "helmet":
        return helmet(out, op, donors)
    if kind == "row":
        return row_fill(out, op)
    raise ValueError("2026 kit fill rule: unknown kind " + repr(kind))
