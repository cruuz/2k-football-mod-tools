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
               pieces and old shell squares given as mask rules or found by the art lane's old-logo detector
               (``old_ink``: the user's own retail helmets of the club against the texture, beside the 2026 logo's
               footprint ``foot``); harmonic or nearest-texel fill, the texture's own colours; then the logo moves the
               art lane made after the cleanup (``after``: mirror_box, mirror_side, turn_upper, mirror_off, outline,
               keyline, interior, real_mark),
               colour only, from the texture itself; then the palette entry of each texel's alpha.
kind "row"     each masked texel takes the colour of the nearest unmasked texel on its own row (ties to the left).
kind "clear_near"  inside boxes, texels of one alpha one or two levels off a colour take that colour.
kind "far_helmet"  the far-away player atlas's helmet side composed from the kit's own near-view helmet (the two
               Carolina blue-alternate rows): its shell colour lit by the island's folds and its logo laid in by an
               exact area average (see that section).

Arithmetic: integers, or IEEE float64 + - * / in a written-out order (the harmonic fill is a fixed number of Jacobi
sweeps with explicit neighbour sums; medians are exact middle values of sorted integers; the nearest-texel fill is
the separable Euclidean feature transform in integers). No float32, no library resampling, no unordered reduction.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

#: shipped project art the fill rules read (the league project's own 2026 team logos, the raven mark): see SOURCES.md
ART = Path(__file__).resolve().parents[2] / "data" / "nfl2k5_kit_rule_fill"

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


def helmet(out, op, donors, snap=True):
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
    foot = footprint(op["foot"], texture, donors) if op.get("foot") else None
    if foot is not None:
        keep = dilate4(foot, 1)                     # the 2026 logo's footprint, grown by one: kept out of every fill
    if op.get("old_ink"):
        rule = op["old_ink"]
        old, boxes = old_ink(texture, blank, zone, [_donor(donors, k) for k in rule["refs"]],
                             foot if foot is not None else np.zeros(shape, bool), rule)
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
    for step in op.get("after", ()):
        res = _after(res, step, blank, zone, texture, donors)
    if not snap:
        return res                                  # the cleaned texture before the per-alpha snap (a donor's)
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


# ------------------------------------------------------------------------------- the 2026 logo's footprint
# The art lane's registered official-logo footprint (fixtex2.old_ink 'foot') and keyline band (keyline.remove
# 'changed'), recomputed exactly without PIL, scipy or libm.
#
# What the art lane computes (b81/art/work/reg.py, fixtex2.py, keyline.py):
#     logo = league PNG, cropped to its alpha > 8 box (reg.official)
#     al   = PIL 'F' LANCZOS resize of float32(alpha / 255.0) of ORI[ori](logo) to (w, h), as float64, clipped to [0, 1]
#     foot = OR over the panels used of  (al > 0.04)  placed at (x0, y0)
#     keyline band = OR over every registered panel of  (al(logo) - al(without_keyline(logo))) > 0.03  placed at (x0, y0)
#
# Here Pillow 10.2's Resample.c is written out for the float32 ('F') path: precompute_coeffs (double coefficients,
# the same bounds rounding, k /= sum in tap order), the horizontal pass then the vertical pass, each output a double
# sum of (float32 input) * (double coefficient) in tap order, stored as float32. Rules followed:
#   * sin() is not libm: _sin() evaluates sin of the double argument with integer fixed-point arithmetic (320 bits,
#     Machin pi, Taylor series) and rounds once to the nearest double (Python's int / int true division is correctly
#     rounded); it refuses if the error bound straddles a rounding boundary. Every other step is one IEEE double
#     + - * / in Pillow's order.
#   * no float32 arithmetic and no float32 arrays: "store as float32" is _f32(), an exact round-to-nearest-even onto
#     the float32 grid (frexp / ldexp / rint on doubles; equal to numpy's astype(float32) - checked by check.py).
#   * numpy is used only element-wise (each texel's sum is written out tap by tap, in Pillow's order); no reductions.
# The inputs are integers (the logo's 8-bit alpha, and for the keyline its 8-bit RGB), so the output is the same
# bytes on every IEEE-754 platform.


# ------------------------------------------------------------------------------------------------ exact sin
_P = 320                       # fixed-point fraction bits
_GUARD = 24


def _machin_pi(bits):
    one = 1 << (bits + _GUARD)

    def arctan_inv(n):
        power = one // n
        total = power
        n2, k, sign = n * n, 3, -1
        while True:
            power //= n2
            if power == 0:
                return total
            total += sign * (power // k)
            sign, k = -sign, k + 2

    return (4 * (4 * arctan_inv(5) - arctan_inv(239))) >> _GUARD   # |error| < 2 units of 2^-bits


_PI_FIXED = _machin_pi(_P)
_PI_DOUBLE = float.fromhex('0x1.921fb54442d18p+1')   # M_PI (C) == math.pi, the double Pillow multiplies by
_SIN_CACHE: dict = {}


def _sin(x: float) -> float:
    """sin(x) rounded to the nearest double, for a double |x| <= 16 (Lanczos-3 never passes more than 3*pi)."""
    r = _SIN_CACHE.get(x)
    if r is not None:
        return r
    if x == 0.0:
        return 0.0
    if not (abs(x) <= 16.0 and abs(x) >= 2.0 ** -200):
        raise ValueError("footprint: sin argument out of the supported range")
    n, d = x.as_integer_ratio()                      # d is a power of two <= 2^(1074)
    X = n * ((1 << _P) // d)                         # exact: |x| >= 2^-200 has no bits below 2^-252
    k = (2 * X + _PI_FIXED) // (2 * _PI_FIXED)       # nearest multiple of pi
    R = X - k * _PI_FIXED                            # |R| <= pi/2 + 2^-300; error <= 2|k| <= 12 units
    one = 1 << _P
    R2 = (R * R) >> _P
    term, total, i = R, R, 1
    while term:
        term = -(term * R2 >> _P) // ((i + 1) * (i + 2))
        total += term
        i += 2
    if k & 1:
        total = -total
    # error: R's <= 12 units (|cos| <= 1), R2's floor and each term's two floors (<= 3 units per term, < 70 terms)
    err = 1024
    lo, hi = (total - err) / one, (total + err) / one     # int / int: correctly rounded to the nearest double
    if lo != hi:
        raise ValueError("footprint: sin rounding not decided at 320 bits")
    _SIN_CACHE[x] = lo
    return lo


def _sinc(x: float) -> float:                        # Resample.c sinc_filter
    if x == 0.0:
        return 1.0
    x = x * _PI_DOUBLE
    return _sin(x) / x


def _lanczos(x: float) -> float:                     # Resample.c lanczos_filter (support 3)
    if -3.0 <= x and x < 3.0:
        return _sinc(x) * _sinc(x / 3)
    return 0.0


_COEFFS: dict = {}


def coeffs(in_size: int, out_size: int):
    """Resample.c precompute_coeffs(in_size, 0.0f, (float)in_size, out_size, LANCZOS): [(xmin, [k...]), ...]."""
    key = (in_size, out_size)
    if key in _COEFFS:
        return _COEFFS[key]
    if not (0 < in_size < 1 << 24 and 0 < out_size < 1 << 24):
        raise ValueError("footprint: resize size out of range")
    scale = float(in_size) / out_size                 # (double)(in1 - in0) / outSize, in0 = 0
    filterscale = scale if scale >= 1.0 else 1.0
    support = 3.0 * filterscale
    ss = 1.0 / filterscale
    out = []
    for xx in range(out_size):
        center = 0.0 + (xx + 0.5) * scale
        xmin = int(center - support + 0.5)            # C (int) truncates toward zero, as int() does
        if xmin < 0:
            xmin = 0
        xmax = int(center + support + 0.5)
        if xmax > in_size:
            xmax = in_size
        xmax -= xmin
        k, ww = [], 0.0
        for x in range(xmax):
            w = _lanczos(((x + xmin) - center + 0.5) * ss)
            k.append(w)
            ww += w
        if ww != 0.0:
            k = [w / ww for w in k]
        out.append((xmin, k))
    _COEFFS[key] = out
    return out


# ------------------------------------------------------------------------------------------------ float32 grid
def _f32(v):
    """Each double rounded to the nearest float32 value (ties to even), kept as float64. Exact steps only."""
    v = np.asarray(v, np.float64)
    out = np.zeros(v.shape, np.float64)
    nz = v != 0.0
    if nz.any():
        vals = v[nz]
        _m, e = np.frexp(vals)                        # vals = m * 2^e, 0.5 <= |m| < 1
        q = np.maximum(e - 24, -149)                  # float32 quantum: 24 significant bits, or 2^-149 below 2^-126
        r = np.ldexp(np.rint(np.ldexp(vals, -q)), q)  # |vals * 2^-q| < 2^24: rint is exact ties-to-even
        if not np.all(np.abs(r) < 2.0 ** 128):
            raise ValueError("footprint: float32 overflow")
        out[nz] = r
    return out


def resize_lanczos_f(plane, width: int, height: int):
    """Image.fromarray(plane.astype(float32), 'F').resize((width, height), Image.LANCZOS), written out.
    ``plane`` holds float32 values (as float64); returns float64 holding float32 values, shape (height, width)."""
    a = np.asarray(plane, np.float64)
    h, w = a.shape
    if width != w:                                    # need_horizontal (default box)
        tmp = np.zeros((h, width), np.float64)
        for xx, (xmin, k) in enumerate(coeffs(w, width)):
            ss = np.zeros(h, np.float64)
            for x, kx in enumerate(k):
                ss = ss + a[:, xmin + x] * kx         # double += float32 * double, tap order
            tmp[:, xx] = _f32(ss)
        a = tmp
    if height != h:                                   # need_vertical
        tmp = np.zeros((height, a.shape[1]), np.float64)
        for yy, (ymin, k) in enumerate(coeffs(h, height)):
            ss = np.zeros(a.shape[1], np.float64)
            for y, ky in enumerate(k):
                ss = ss + a[ymin + y] * ky
            tmp[yy] = _f32(ss)
        a = tmp
    return a


# ------------------------------------------------------------------------------------------------ the logo
LOGO_ORI = {'id': lambda a: a, 'fh': lambda a: a[:, ::-1], 'fv': lambda a: a[::-1], 'r180': lambda a: a[::-1, ::-1]}


def crop_box(alpha_u8):
    """reg.official: the box of alpha > 8 (x0, y0, x1, y1)."""
    ys, xs = np.nonzero(np.asarray(alpha_u8) > 8)
    if not len(xs):
        raise ValueError("footprint: the logo is empty")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def logo_alpha(alpha_u8, ori: str, width: int, height: int):
    """reg.resized(...)[1] for an already cropped logo: float32(alpha / 255.0), oriented, resized, clipped to [0, 1]."""
    a = np.asarray(alpha_u8)
    if a.dtype != np.uint8 or a.ndim != 2:
        raise ValueError("footprint: the logo alpha must be a 2-D uint8 plane")
    plane = _f32(LOGO_ORI[ori](a).astype(np.float64) / 255.0)
    return np.clip(resize_lanczos_f(plane, width, height), 0.0, 1.0)


def _check_placements(regs, shape):
    for v in regs:
        if v['ori'] not in LOGO_ORI or not (0 <= v['x0'] and 0 <= v['y0'] and v['x0'] + v['w'] <= shape[1]
                                       and v['y0'] + v['h'] <= shape[0] and v['w'] > 0 and v['h'] > 0):
            raise ValueError("footprint: placement outside the texture")


def logo_footprint(texture_rgba, logo_alpha_u8, regs, threshold=0.04, crop=None):
    """fixtex2.old_ink(...)['foot']: ``logo_alpha_u8`` is the logo's full 8-bit alpha plane (it is cropped to its
    alpha > 8 box here, as reg.official does); ``regs`` the panels the stored decision uses, each
    {ori, w, h, x0, y0}. ``texture_rgba`` gives the shape only (the registration re-check is a stored decision)."""
    shape = np.asarray(texture_rgba).shape[:2]
    _check_placements(regs, shape)
    x0, y0, x1, y1 = crop_box(logo_alpha_u8) if crop is None else (int(v) for v in crop)
    a = np.ascontiguousarray(np.asarray(logo_alpha_u8)[y0:y1, x0:x1])
    foot = np.zeros(shape, bool)
    for v in regs:
        al = logo_alpha(a, v['ori'], v['w'], v['h'])
        foot[v['y0']:v['y0'] + v['h'], v['x0']:v['x0'] + v['w']] |= al > threshold
    return foot


def footprint(spec, texture, donors):
    """The 2026 logo's footprint (fixtex2.old_ink 'foot'): the league logo as the build holds it (donor
    ``spec["logo"]``, a logos.cdf slot written by the league project step), cropped to its alpha above 8, turned as
    registered and resized exactly (Pillow's LANCZOS written out) to each registered placement ``spec["regs"]``
    [{panel, ori, w, h, x0, y0}] of the panels the art lane kept; coverage above ``above`` (0.04: the art lane's
    value; a row whose logo the P8 import changed may name the value at which the cleanup comes out the same) and,
    optionally, the logo's ``crop`` box [x0, y0, x1, y1] (the league PNG's own alpha box, which the import can move)."""
    logo = _donor(donors, spec["logo"])
    return logo_footprint(texture, np.ascontiguousarray(logo[..., 3]), spec["regs"], float(spec.get("above", 0.04)),
                          spec.get("crop"))


# ----------------------------------------------------------------------------------- old logo ink (detector)
PANELS = {"upper": (8, 18, 146, 128), "lower": (8, 128, 146, 238)}     # x0, y0, x1, y1 of the two side islands
NEAR = 24                                       # old ink is looked for this close to the 2026 logo (texels)


def _norm(d):
    """Euclidean length of float64 RGB differences, summed R, G then B (numpy's order), IEEE square root."""
    return np.sqrt(d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1] + d[..., 2] * d[..., 2])


def _explained(cur, ret, shell_cur, shell_ret, thr=40.0, tol=22.0):
    """texdet2.explained: how much of the retail decal texel is left at each texel (0..1.2), and whether the texel
    is that decal at some strength over today's shell (float64, sums written out)."""
    d_ret = ret - shell_cur
    d_cur = cur - shell_cur
    n2 = d_ret[..., 0] * d_ret[..., 0] + d_ret[..., 1] * d_ret[..., 1] + d_ret[..., 2] * d_ret[..., 2]
    dot = d_cur[..., 0] * d_ret[..., 0] + d_cur[..., 1] * d_ret[..., 1] + d_cur[..., 2] * d_ret[..., 2]
    alpha = np.clip(dot / np.maximum(n2, 1e-6), 0.0, 1.2)
    resid = _norm(d_cur - alpha[..., None] * d_ret)
    decal = _norm(ret - shell_ret) > thr
    cur_dev = _norm(d_cur)
    ok = decal & (n2 > thr * thr) & (alpha > 0.12) & (resid <= np.maximum(tol * 0.5, 0.18 * cur_dev)) & (cur_dev > 14.0)
    return alpha, ok


def _sizes(label, n, weight):
    return np.bincount(label.ravel(), weights=weight.ravel().astype(np.int64), minlength=n + 1)[1:].astype(np.int64)


def old_ink(texture, blank, zone, refs, foot, rule):
    """The art lane's old-logo detector (fixtex2.old_ink) on the texture the build holds: ink of the retail decals of
    this club (``refs``: the user's own retail helmets of this slot and the club's home and away kit) left beside the
    2026 logo (``foot``: its footprint), plus the reviewed boxes of ``rule``. Returns (paint, boxes)."""
    shape = texture.shape[:2]
    inside = box_mask(shape, zone)
    hw = hardware_mask_raw(blank, zone)
    hwz = hw.copy()
    if rule.get("vents_free", True):
        for v in vent_masks(blank):
            hwz &= ~dilate4(v, 2)
    z = inside & ~hwz
    cur = texture[..., :3].astype(np.float64)
    shell_cur = _median_rows(cur[inside & ~hw])
    cur_dev = _norm(cur - shell_cur)
    ink = z & (cur_dev > 30.0)
    exp = np.zeros(shape, bool)
    intact = np.zeros(shape, bool)
    for ref in refs:
        ret = ref[..., :3].astype(np.float64)
        shell_ret = _median_rows(ret[inside & ~hw])
        a, ok = _explained(cur, ret, shell_cur, shell_ret)
        ok &= z
        rdecal = z & (_norm(ret - shell_ret) > 40.0)
        label, sizes = _label8(rdecal)
        if sizes:
            kept = _sizes(label, len(sizes), ok & (a >= 0.8))
            whole = [i + 1 for i, (sz, k) in enumerate(zip(sizes, kept)) if sz >= 24 and k / sz >= 0.8]
            intact |= np.isin(label, whole)
        exp |= ok
    intact = dilate4(intact, 1)
    footg = dilate4(foot, 1)
    pz = np.zeros(shape, bool)
    for panel in rule.get("panels", ()):
        pz |= box_mask(shape, PANELS[panel])
    near = dilate4(foot, NEAR) & pz
    near[:, LOGO_X1:] = False
    left = ink & exp & ~footg & ~intact & near
    label, sizes = _label8(left)
    if sizes:
        drop = [i + 1 for i, sz in enumerate(sizes) if sz <= 2 and cur_dev[label == i + 1].max() < 60]
        left &= ~np.isin(label, drop)
    if not rule.get("reviewed"):
        left[:] = False
    for box in rule.get("add", ()):
        left |= box_mask(shape, box) & (cur_dev > float(rule.get("add_dev", 30.0))) & ~foot & inside
    for box in rule.get("keep", ()):
        left &= ~box_mask(shape, box)
    loose = ink & ~footg & near
    label, sizes = _label8(loose)
    if sizes and left.any():
        old = _sizes(label, len(sizes), left)
        whole = [i + 1 for i, (sz, o) in enumerate(zip(sizes, old)) if o >= 3 and o / sz >= 0.3 and sz <= 400]
        left = left | np.isin(label, whole)
    grown = dilate4(left, int(rule.get("grow", 2))) & ~footg & (cur_dev > float(rule.get("grow_dev", 8.0))) & z
    if rule.get("despeckle") or rule.get("gold"):
        box = box_mask(shape, (20, 20, 142, 236)) & inside & ~hw
        r, g, b = cur[..., 0], cur[..., 1], cur[..., 2]
        extra = np.zeros(shape, bool)
        if rule.get("despeckle"):
            white = box & (cur.min(axis=2) > 105) & (cur.max(axis=2) - cur.min(axis=2) < 40)
            label, sizes = _label8(white)
            extra |= np.isin(label, [i + 1 for i, sz in enumerate(sizes) if sz <= 5])
        if rule.get("gold"):
            extra |= dilate4(box & (r - b > 55) & (r > 95) & (g > 60), 1) & box & ~((r > 140) & (g < 70))
        left |= extra
        grown |= extra
    boxes = np.zeros(shape, bool)
    for bx in rule.get("shell_boxes", ()):
        boxes |= box_mask(shape, bx) & (cur.max(axis=2) < 30.0)
    for bx in rule.get("erase", ()):
        m = box_mask(shape, bx)
        boxes |= m & (cur_dev > 4.0) & ~foot & inside
        if rule.get("erase_edge_neutral"):
            band = foot & ~erode4(foot, int(rule["erase_edge_neutral"]))
            lum = cur[..., 0] * 0.299 + cur[..., 1] * 0.587 + cur[..., 2] * 0.114
            shell_l = shell_cur[0] * 0.299 + shell_cur[1] * 0.587 + shell_cur[2] * 0.114
            boxes |= m & band & (cur.max(axis=2) - cur.min(axis=2) < 45.0) & (lum < shell_l - 14.0) & inside
    left = left | boxes
    return left | grown | boxes, boxes


# ------------------------------------------------------------------------------- logo moves after the cleanup
AXIS = 255                                      # both helmet atlases mirror their two side islands about y + y' = 255
LOGO_ABOVE = 40                                 # logo ink: farther than this from the 2026 shell colour
LOGO_X1 = 142                                   # the crown stripes start here


def _label8(mask):
    """8-connected pieces in raster order of their first texel: (labels, sizes)."""
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
            for dy, dx in NEIGHBOURS8:
                v, u = y + dy, x + dx
                if 0 <= v < h and 0 <= u < w and mask[v, u] and not label[v, u]:
                    label[v, u] = n
                    stack.append((v, u))
        sizes.append(size)
    return label, sizes


def logo_ink(res, blank, zone, upper):
    """The logo of one side island (fixes7.logo_box): ink farther than LOGO_ABOVE from the shell colour on the panels
    off the blank shell's hardware, its largest 8-connected piece and the pieces of 3 or more texels within 6 steps of
    it. Returns the ink mask (empty when the island holds none)."""
    x0, y0, x1, y1 = zone
    inside = np.zeros(res.shape[:2], bool)
    inside[y0:y1, x0:x1] = True
    panel = inside & ~hardware_mask_raw(blank, zone)
    rgb = res[..., :3].astype(np.int64)
    shell2 = _median_int(rgb[panel])
    d = 2 * rgb - shell2
    m = panel & ((d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1] + d[..., 2] * d[..., 2]) > 4 * LOGO_ABOVE * LOGO_ABOVE)
    rows = np.arange(res.shape[0])[:, None]
    m &= (rows < 128) if upper else (rows >= 128)
    m[:, LOGO_X1:] = False
    label, sizes = _label8(m)
    if not sizes:
        return m
    big = label == 1 + max(range(len(sizes)), key=lambda i: (sizes[i], -i))
    near = dilate4(big, 6)
    keep = [i + 1 for i in range(len(sizes)) if sizes[i] >= 3 and (near & (label == i + 1)).any()]
    return np.isin(label, keep)


def _fill_holes4(mask):
    """Unset texels not 4-connected to the edge through unset texels are set (scipy binary_fill_holes)."""
    h, w = mask.shape
    outside = np.zeros((h, w), bool)
    stack = [(y, x) for y in range(h) for x in (0, w - 1)] + [(y, x) for x in range(w) for y in (0, h - 1)]
    for y, x in stack:
        if not mask[y, x]:
            outside[y, x] = True
    stack = [(y, x) for y, x in stack if outside[y, x]]
    while stack:
        y, x = stack.pop()
        for dy, dx in NEIGHBOURS4:
            v, u = y + dy, x + dx
            if 0 <= v < h and 0 <= u < w and not mask[v, u] and not outside[v, u]:
                outside[v, u] = True
                stack.append((v, u))
    return ~outside


def _after(res, step, blank, zone, texture=None, donors=None):
    """A logo move after the cleanup (the art lane's fixes7 steps), colour only, from the texture so far:
    mirror_box   the ``box`` takes the mirror image about the atlas axis of the same columns (fixes7
                 mirror_upper_from_lower, the box being the two logos' boxes as that step measured them);
    mirror_side  one island's logo becomes the other's mirror image inside the two logos' shapes grown by 3
                 (fixes7.mirror_panel; ``to_upper``);
    turn_upper   the right-side logo is turned half round inside its own filled shape (fixtex2 rot180_upper);
    mirror_off   inside ``boxes``, texels farther than 45 from their mirror image take it (erase_after_mirror)."""
    do = step["do"]
    out = res.copy()
    h = res.shape[0]
    rows = np.arange(h)[:, None]
    if do == "mirror_box":
        x0, y0, x1, y1 = (int(v) for v in step["box"])
        _require(0 <= x0 < x1 <= res.shape[1] and 0 <= y0 < y1 <= h and AXIS - y1 + 1 >= 0 and AXIS - y0 + 1 <= h,
                 "mirror box outside the texture")
        out[y0:y1, x0:x1, :3] = res[AXIS - y1 + 1:AXIS - y0 + 1, x0:x1, :3][::-1]
        return out
    if do == "mirror_side":
        to_upper = bool(step["to_upper"])
        lower, upper = logo_ink(res, blank, zone, False), logo_ink(res, blank, zone, True)
        src, dst = (lower, upper) if to_upper else (upper, lower)
        m = dilate4(dst | src[::-1], 3)
        m &= (rows < 128) if to_upper else (rows >= 128)
        m &= box_mask(res.shape, zone)
        m[:, LOGO_X1:] = False
        out[m, :3] = res[::-1][m][:, :3]
        return out
    if do == "turn_upper":
        keep = logo_ink(res, blank, zone, True)
        ys, xs = np.nonzero(keep)
        _require(len(ys) > 0, "no right-side logo to turn")
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        shape = _fill_holes4(erode4(dilate4(keep[y0:y1, x0:x1], 2), 2))
        both = shape & shape[::-1, ::-1]
        block = res[y0:y1, x0:x1, :3]
        out[y0:y1, x0:x1, :3] = np.where(both[..., None], block[::-1, ::-1], block)
        return out
    if do == "mirror_off":
        rgb = res[..., :3].astype(np.int64)
        d = rgb - rgb[::-1]
        far = (d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1] + d[..., 2] * d[..., 2]) > 45 * 45
        for box in step["boxes"]:
            m = box_mask(res.shape, box) & far
            out[m, :3] = out[::-1][m][:, :3]
        return out
    if do == "outline":
        return _outline(res, step, blank, zone)
    if do == "keyline":
        return _keyline(res, step, blank, zone, texture, donors)
    if do == "interior":
        return _interior(res, step, donors)
    if do == "real_mark":
        return _real_mark(res, step, blank, zone, project_art(step["mark_file"], step["mark_sha256"]))
    raise ValueError("2026 kit fill rule: unknown step " + repr(do))


def _without_keyline(logo):
    """keyline.without_keyline: the logo's outer white ring (white texels reachable from outside through white, and
    the semi-transparent light rim texels beside them) made transparent. ``logo`` RGBA uint8; returns the new alpha."""
    rgb = logo[..., :3].astype(np.int64)
    al = logo[..., 3].astype(np.int64)
    white = (al > 40) & (rgb.min(axis=2) > 190) & (rgb.max(axis=2) - rgb.min(axis=2) < 40)
    outside = al <= 40
    reach = outside.copy()
    for _ in range(64):
        grown = dilate8(reach, 1) & (white | outside)
        if (grown == reach).all():
            break
        reach = grown
    ring = reach & white
    rim = dilate4(ring, 1) & (al < 250) & ~ring & (rgb.min(axis=2) > 150)
    out = logo[..., 3].copy()
    out[ring | rim] = 0
    return out


def _outline_colour(logo, alpha2):
    """keyline.outline_colour: the middle colour of the de-keylined logo's opaque texels within 3 steps of its outside."""
    opaque = alpha2 > 250
    rim = opaque & dilate4(alpha2 < 40, 3)
    return _median_rows(logo[..., :3].astype(np.float64)[rim])


def project_art(name, sha256):
    """RGBA uint8 of a shipped project picture in ART, checked against its SHA-256 (PNG decoding is lossless)."""
    path = ART / name
    _require(path.parent == ART and path.is_file(), "project art absent: " + str(name))
    data = path.read_bytes()
    _require(hashlib.sha256(data).hexdigest() == sha256, "project art differs from its pin: " + str(name))
    from PIL import Image
    import io
    with Image.open(io.BytesIO(data)) as image:
        return np.array(image.convert("RGBA"), np.uint8)


def _keyline(res, step, blank, zone, texture, donors):
    """keyline.remove (mode outline) and its palette snap: at each registered placement ``regs`` of the 2026 logo
    (the league project's own logo file shipped in ART, ``logo_file`` pinned by ``logo_sha256``, or a donor ``logo``;
    cropped to its alpha above 8 or to ``crop``), the texels where the logo's coverage exceeds the
    de-keylined logo's by more than 0.03 (``grow``: grown by that many 4-neighbour steps where the de-keylined
    coverage is below 0.98) take the logo's own outline colour at the logo's coverage over the shell colour; then the
    nearest colour of the row's input texture."""
    logo = (project_art(step["logo_file"], step["logo_sha256"]) if step.get("logo_file")
            else _donor(donors, step["logo"]))
    x0, y0, x1, y1 = crop_box(logo[..., 3]) if step.get("crop") is None else (int(v) for v in step["crop"])
    lg = np.ascontiguousarray(logo[y0:y1, x0:x1])
    a2 = _without_keyline(lg)
    ring_col = _outline_colour(lg, a2)
    inside = box_mask(res.shape, zone)
    rgb = res[..., :3].astype(np.float64)
    shell = _median_rows(rgb[inside & ~hardware_mask_raw(blank, zone)])
    out = rgb.copy()
    changed = np.zeros(res.shape[:2], bool)
    above = float(step.get("above", 0.03))
    for v in step["regs"]:
        al = logo_alpha(np.ascontiguousarray(lg[..., 3]), v["ori"], v["w"], v["h"])
        al2 = logo_alpha(np.ascontiguousarray(a2), v["ori"], v["w"], v["h"])
        band = (al - al2) > above
        if step.get("grow"):
            band = dilate4(band, int(step["grow"])) & (al2 < 0.98)
        new = ring_col * al[..., None] + shell * (1 - al[..., None])
        sub = out[v["y0"]:v["y0"] + v["h"], v["x0"]:v["x0"] + v["w"]]
        sub[band] = new[band]
        changed[v["y0"]:v["y0"] + v["h"], v["x0"]:v["x0"] + v["w"]] |= band
    result = res.copy()
    pal, _ = unique_colours(texture[..., :3])
    result[changed, :3] = nearest_colour(out[changed], pal).astype(np.uint8)
    return result


def _interior(res, step, donors):
    """refine.interior: inside the registered 2026 logo (its footprint at ``regs`` grown by one, shrunk by three: the
    rim stays), the texels take the home kit's cleaned texture there (donor ``donor``: the home kit's helmet as the
    build holds it, cleaned here by its own row's rule ``recipe``; ``shift`` per panel: the offset between the two
    registrations), then the nearest colour of the texture so far."""
    home = helmet(_donor(donors, step["donor"]), step["recipe"], donors, snap=False)
    logo = (project_art(step["logo_file"], step["logo_sha256"]) if step.get("logo_file")
            else _donor(donors, step["logo"]))
    foot = dilate4(logo_footprint(res, np.ascontiguousarray(logo[..., 3]), step["regs"]), 1)
    inner = erode4(foot, 3)
    rows = np.arange(res.shape[0])[:, None]
    out = res[..., :3].astype(np.float64)
    changed = np.zeros(res.shape[:2], bool)
    for panel in ("lower", "upper"):
        dx, dy = (int(v) for v in step["shift"][panel])
        m = inner & ((rows >= 128) if panel == "lower" else (rows < 128))
        ys, xs = np.nonzero(m)
        out[ys, xs] = home[ys + dy, xs + dx, :3]
        changed |= m
    result = res.copy()
    pal, _ = unique_colours(res[..., :3])
    result[changed, :3] = nearest_colour(out[changed], pal).astype(np.uint8)
    return result


# ------------------------------------------------------------------------------- the real mark (Ravens dark alternate)
# Written to paste into mod_editor/core/nfl2k5_kit_rule_fill.py after _outline (it uses the module's own primitives:
# box_mask, dilate4, shell_hardware, vent_masks, flag_masks, _median_int, nearest_fill, band_fill, unique_colours,
# nearest_colour, coeffs, project_art, _require, HARDWARE_ABOVE, LOGO_X1, NEIGHBOURS4). Reached from _after as
#     if do == "real_mark":
#         return _real_mark(res, step, blank, zone, project_art(step["mark_file"], step["mark_sha256"]))
# with the step {"do": "real_mark", "mark_file": "bal_dark_mark_2026.png", "mark_sha256": "4fc5ef83...", "height": 51}
# (the PNG in data/nfl2k5_kit_rule_fill/, its file SHA-256; SOURCE.txt / sources_entry.json beside this file).
#
# The art lane's realmark.apply (b81/art/work/realmark.py, called from fixtex2._cleanup on the cleaned texture) on the
# texture the build holds: beta 80's stand-in raven drawing (found by its lighter-than-shell outline and red eyes) and
# the old black shell squares are repainted from the shell round them (nearest texel and harmonic, averaged), the real
# front-facing mark (cut from the Commons 2026 Ravens uniform diagram, shipped as a PNG with its source note) is
# resized with Pillow's 8-bit LANCZOS written out (premultiplied RGBa, integer coefficients, clip, un-premultiply) to
# ``height`` texels at the drawing's centre, blended over the repaint by its alpha, off the blank shell's hardware,
# and every texel the step touched takes the nearest colour the texture already holds.
#
# Arithmetic: masks, medians and thresholds in integers (the shell is held as twice its median; Euclidean thresholds as
# squared integers; the luminance as 299 R + 587 G + 114 B); the fills are the module's; the blend is IEEE double
# region * (1 - a) + mark * a with a = A / 255.0, in that order; the resize is integer apart from its coefficients,
# which are Pillow's doubles from the module's coeffs() (exact sin, no libm), rounded to 22 fraction bits as Pillow does.

REAL_MARK_LUM = (299, 587, 114)        # luminance weights in thousandths (realmark: rgb @ [0.299, 0.587, 0.114])
REAL_MARK_LIGHTER = 12                 # the old drawing: luminance above the shell's by more than this, or ...
REAL_MARK_RED = (120, 80)              # ... its red eyes: R above 120 and G below 80
REAL_MARK_COLS = (36, 126)             # the old drawing is looked for in these columns of each side island
REAL_MARK_PAD = (30, 18)               # the repaint box: the drawing's box grown 30 columns and 18 rows (columns < LOGO_X1)
REAL_MARK_DEV = 3                      # inside that box: texels farther than this from the shell colour
REAL_MARK_FAR = 12                     # "not shell": farther than this from the shell colour (Euclidean RGB)
REAL_MARK_DARK = 30                    # old black shell squares: every channel below this (and not shell)
REAL_MARK_COVER = 50                   # a mark texel counts as painted where its alpha / 255 > 1 / 50 (0.02)


def _label4(mask):
    """4-connected pieces in raster order of their first texel: (labels, sizes) (scipy ndimage.label's default)."""
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
    return label, sizes


def _round_half_even(num, den):
    """round(num / den) for integers, den > 0, ties to even (Python's round of the exact quotient)."""
    q, r = divmod(int(num), int(den))
    if 2 * r > den or (2 * r == den and q % 2):
        q += 1
    return q


_PRECISION_BITS = 22                   # Resample.c: 32 - 8 - 2
_COEFFS8: dict = {}


def coeffs8(in_size: int, out_size: int):
    """Resample.c normalize_coeffs_8bpc of precompute_coeffs (LANCZOS): [(xmin, [INT32 k...]), ...]; each double k
    becomes (int)(k * 2^22 + 0.5), or (int)(-0.5 + k * 2^22) below 0 (C casts truncate toward zero, as int() does)."""
    key = (in_size, out_size)
    if key not in _COEFFS8:
        scale = float(1 << _PRECISION_BITS)
        out = []
        for xmin, k in coeffs(in_size, out_size):
            ints = [int(-0.5 + v * scale) if v < 0 else int(0.5 + v * scale) for v in k]
            # Pillow sums in a C int: 255 * sum |k| plus the rounding half must stay below 2^31
            _require(255 * sum(abs(v) for v in ints) + (1 << (_PRECISION_BITS - 1)) < 1 << 31, "resize overflow")
            out.append((xmin, ints))
        _COEFFS8[key] = out
    return _COEFFS8[key]


def resize_lanczos_rgba8(rgba, width: int, height: int):
    """Image.fromarray(rgba, "RGBA").resize((width, height), Image.LANCZOS) (Pillow 10.2), written out in integers:
    RGBA -> RGBa (Convert.c rgbA2rgba: MULDIV255), the horizontal then the vertical 8-bit pass (Resample.c
    ImagingResampleHorizontal_8bpc / Vertical_8bpc: 2^21 + sum of value * k, then clip8 = clamp(sum >> 22, 0, 255)),
    then RGBa -> RGBA (Convert.c rgba2rgbA: alpha 0 or 255 kept, else CLIP8(255 * c / alpha), integer division).
    The same size is a plain copy, as Image.resize returns one."""
    a = np.asarray(rgba)
    _require(a.dtype == np.uint8 and a.ndim == 3 and a.shape[2] == 4, "the mark must be RGBA uint8")
    _require(width > 0 and height > 0, "resize to nothing")
    if (height, width) == a.shape[:2]:
        return a.copy()                               # Image.resize: the same size is a plain copy
    a = a.astype(np.int64)
    t = a[..., :3] * a[..., 3:4] + 128
    img = np.concatenate([((t >> 8) + t) >> 8, a[..., 3:4]], axis=2)
    h, w = img.shape[:2]
    half = 1 << (_PRECISION_BITS - 1)
    if width != w:                                    # need_horizontal (default box)
        tmp = np.zeros((h, width, 4), np.int64)
        for xx, (xmin, k) in enumerate(coeffs8(w, width)):
            ss = np.full((h, 4), half, np.int64)
            for x, kx in enumerate(k):
                ss = ss + img[:, xmin + x] * kx
            tmp[:, xx] = np.clip(ss >> _PRECISION_BITS, 0, 255)
        img = tmp
    if height != h:                                   # need_vertical
        tmp = np.zeros((height, img.shape[1], 4), np.int64)
        for yy, (ymin, k) in enumerate(coeffs8(h, height)):
            ss = np.full((img.shape[1], 4), half, np.int64)
            for y, ky in enumerate(k):
                ss = ss + img[ymin + y] * ky
            tmp[yy] = np.clip(ss >> _PRECISION_BITS, 0, 255)
        img = tmp
    al = img[..., 3:4]
    keep = (al == 0) | (al == 255)
    un = np.minimum((255 * img[..., :3]) // np.maximum(al, 1), 255)
    return np.concatenate([np.where(keep, img[..., :3], un), al], axis=2).astype(np.uint8)


def _real_mark_core(blank, zone, diamond):
    """realmark.hw_core: the blank shell's hardware (largest step above HARDWARE_ABOVE) grown by one 4-neighbour step,
    less the six painted 2004 vents grown by 3 and the flag diamond grown by 3."""
    _shell2, dev2 = shell_hardware(blank, zone)
    core = dilate4(dev2 > 2 * HARDWARE_ABOVE, 1)
    for v in vent_masks(blank):
        core &= ~dilate4(v, 3)
    return core & ~dilate4(diamond, 3)


def _old_drawing(rgb, lum2, sl2, inside, core, upper):
    """realmark.old_drawing: the box (x0, y0, x1, y1) of beta 80's drawing on one side island: texels of the panels off
    the core lighter than the shell by more than REAL_MARK_LIGHTER (twice the luminance in thousandths against twice
    the shell's) or red; grown by two 4-neighbour steps, the 4-connected piece holding most of them."""
    r_hi, g_lo = REAL_MARK_RED
    red = (rgb[..., 0] > r_hi) & (rgb[..., 1] < g_lo)
    m = inside & ~core & ((lum2 > sl2 + 2 * 1000 * REAL_MARK_LIGHTER) | red)
    rows = np.arange(rgb.shape[0])[:, None]
    m &= (rows < 128) if upper else (rows >= 128)
    m[:, :REAL_MARK_COLS[0]] = False
    m[:, REAL_MARK_COLS[1]:] = False
    label, _sizes = _label4(dilate4(m, 2))
    _require(len(_sizes) > 0, "no old drawing on this side")
    counts = [int((m & (label == i + 1)).sum()) for i in range(len(_sizes))]
    big = label == 1 + max(range(len(counts)), key=lambda i: (counts[i], -i))
    ys, xs = np.nonzero(big & m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _real_mark_parts(res, step, blank, zone, mark_rgba):
    """(the new texture, the texels the step touched); see _real_mark."""
    shape = res.shape[:2]
    rgb = res[..., :3].astype(np.int64)
    inside = box_mask(shape, zone)
    _shell2, dev2 = shell_hardware(blank, zone)
    hw = dilate4(dev2 > 2 * HARDWARE_ABOVE, 2)                    # hardware_mask_raw(blank, zone)
    diamond, _ring = flag_masks(res, "ring")                       # the flag's place: the texture's transparent diamond
    core = _real_mark_core(blank, zone, diamond)
    shell2 = _median_int(rgb[inside & ~hw])                       # twice the shell colour of this texture
    d = 2 * rgb - shell2
    dev4 = d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1] + d[..., 2] * d[..., 2]     # (2 * distance) squared
    wr, wg, wb = REAL_MARK_LUM
    lum2 = 2 * (wr * rgb[..., 0] + wg * rgb[..., 1] + wb * rgb[..., 2])           # 2000 * luminance
    sl2 = wr * int(shell2[0]) + wg * int(shell2[1]) + wb * int(shell2[2])        # 2000 * the shell's
    rows = np.arange(shape[0])[:, None]
    paint = np.zeros(shape, bool)
    places = []
    pad_x, pad_y = REAL_MARK_PAD
    for upper in (False, True):
        x0, y0, x1, y1 = _old_drawing(rgb, lum2, sl2, inside, core, upper)
        places.append((upper, x0, y0, x1, y1))
        box = np.zeros(shape, bool)
        box[max(0, y0 - pad_y):y1 + pad_y, max(0, x0 - pad_x):min(LOGO_X1, x1 + pad_x)] = True
        box &= (rows < 128) if upper else (rows >= 128)
        paint |= box & inside & ~core & (dev4 > 4 * REAL_MARK_DEV * REAL_MARK_DEV)
    side = inside.copy()
    side[:, LOGO_X1:] = False
    far = dev4 > 4 * REAL_MARK_FAR * REAL_MARK_FAR
    paint |= side & ~core & (rgb.max(axis=2) < REAL_MARK_DARK) & far          # squares of the old black shell
    not_shell = far | paint
    out = rgb.astype(np.float64)
    a = nearest_fill(out, paint, not_shell)
    b = band_fill(a, paint, not_shell)
    out[paint] = 0.5 * a[paint] + 0.5 * b[paint]
    changed = paint.copy()
    mark = np.asarray(mark_rgba, np.uint8)
    h = int(step["height"])
    _require(h > 0, "mark height must be positive")
    w = max(1, _round_half_even(h * mark.shape[1], mark.shape[0]))
    sized = resize_lanczos_rgba8(mark, w, h)
    for upper, x0, y0, x1, y1 in places:
        m = sized[::-1] if upper else sized
        px = _round_half_even(x0 + x1 - w, 2)                     # round(cx - w / 2), cx = (x0 + x1) / 2
        py = _round_half_even(y0 + y1 - h, 2)
        _require(0 <= px and px + w <= shape[1] and 0 <= py and py + h <= shape[0], "mark outside the texture")
        A = m[..., 3].astype(np.int64)
        al = (A.astype(np.float64) / 255.0)[..., None]
        region = out[py:py + h, px:px + w]
        ok = ~core[py:py + h, px:px + w]
        blend = region * (1.0 - al) + m[..., :3].astype(np.float64) * al
        region[ok] = blend[ok]
        changed[py:py + h, px:px + w] |= (A * REAL_MARK_COVER > 255) & ok
    pal, _ = unique_colours(res[..., :3])
    new = res.copy()
    new[changed, :3] = nearest_colour(out[changed], pal).astype(np.uint8)
    return new, changed


def _real_mark(res, step, blank, zone, mark_rgba):
    """realmark.apply as a step after the cleanup (see the section text); ``mark_rgba`` is the shipped mark
    (project_art(step["mark_file"], step["mark_sha256"])), ``step["height"]`` its height in texels (51: beta 80's
    drawing on the modern shell). The flag diamond kept out of the core is the texture's own transparent one
    (flag_masks of ``res``; the art lane read the 2026 Cleveland helmet's, the same texels on this row)."""
    return _real_mark_parts(res, step, blank, zone, mark_rgba)[0]


#: outline coverage beside the logo (refine.outline: clip(1.7 - d, 0, 1) * 0.9 at the Euclidean distance d from the
#: white mark), as float64 bit patterns: d = 1 (4-neighbour) and d = sqrt(2) (diagonal); farther texels get none
OUTLINE_COVER = {1: float.fromhex("0x1.428f5c28f5c29p-1"), 2: float.fromhex("0x1.07617adbb143cp-2")}


def _outline(res, step, blank, zone):
    """A thin soft outline of colour ``ink`` round the project's white mark (refine.outline: the Vikings' horn has the
    thin black outline the 2026 helmet shows): the white pieces of at least 250 texels (luminance 0.299 R + 0.587 G +
    0.114 B above 200, channel spread below 40) are the mark; texels beside it, off gold and off the blank shell's
    hardware, take ink over their own colour at OUTLINE_COVER, then the nearest colour the texture already holds."""
    rgb = res[..., :3].astype(np.int64)
    lum1000 = 299 * rgb[..., 0] + 587 * rgb[..., 1] + 114 * rgb[..., 2]
    white = (lum1000 > 200000) & (rgb.max(axis=2) - rgb.min(axis=2) < 40)
    h, w = white.shape
    label = np.zeros((h, w), np.int64)
    horn = np.zeros((h, w), bool)
    count = 0
    for y0, x0 in zip(*np.nonzero(white)):
        if label[y0, x0]:
            continue
        count += 1
        label[y0, x0] = count
        stack, piece = [(int(y0), int(x0))], []
        while stack:
            y, x = stack.pop()
            piece.append((y, x))
            for dy, dx in NEIGHBOURS4:
                v, u = y + dy, x + dx
                if 0 <= v < h and 0 <= u < w and white[v, u] and not label[v, u]:
                    label[v, u] = count
                    stack.append((v, u))
        if len(piece) >= 250:
            ys, xs = zip(*piece)
            horn[list(ys), list(xs)] = True
    side = dilate4(horn, 1) & ~horn
    corner = dilate8(horn, 1) & ~horn & ~side
    cover = np.where(side, OUTLINE_COVER[1], np.where(corner, OUTLINE_COVER[2], 0.0))
    gold = (rgb[..., 0] - rgb[..., 2]) > 70
    _shell2, dev2 = shell_hardware(blank, zone)
    region = (cover > 0.03) & ~horn & ~gold & ~dilate4(gold, 1) & ~(dev2 > 2 * HARDWARE_ABOVE)
    ink = _hex(step["ink"]).astype(np.float64)
    a = cover[region][:, None]
    painted = rgb[region].astype(np.float64) * (1 - a) + ink * a
    out = res.copy()
    pal, _ = unique_colours(res[..., :3])
    out[region, :3] = nearest_colour(painted, pal).astype(np.uint8)
    return out


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


# ------------------------------------------------------------------------- far-away atlas helmet (Carolina)
# Fill rule kind "far_helmet": the far-away player atlas's helmet side composed at build time from the kit's own
# near-view helmet (b81 retail-free, the two Carolina blue-alternate rows 04H2:51 / 04A2:51). Every name here is
# prefixed far_ / FAR_, so the file can be pasted into nfl2k5_kit_rule_fill.py beside the helmet and row kinds.
#
# This is the Studio's own sideline "shell" repaint with a decal (nfl2k5_kit_fixes_2026._sideline_shell_repaint, the
# path the 05H4/05A4, 18H7, 19H2/19A2, 25H7/25A7 and 27A6 sideline rows use) restated in exact arithmetic:
#
# 1. shell colour  = the near helmet's field colour, measured as the sideline step measures it
#                    (_sideline_field_mode(texture, "helmet")): the columns x < 100 of helmet02, texels with alpha > 128,
#                    the most frequent 24-level colour cell (np.unique order, first maximum), the per-channel median of
#                    its members (integers; an even count takes the floor of the two middle values' mean).
# 2. folds         = the island's own painted folds as a brightness ratio (_sideline_folds, strength 0.7): the island's
#                    fabric is its own most frequent colour cell; a texel is fabric when it is a near shade of it
#                    (luma ratio 0.6..1.6 and squared RGB distance to the scaled fabric < 0.09^2; near-black fabric:
#                    plain squared distance), eroded by one texel when that keeps over a fifth of the island; ratio =
#                    (luma + 0.05) / median over fabric, 1.0 elsewhere; faded by 0.7 x clip(fabric luma / 0.25, 0.25, 1);
#                    two passes of the separable [1, 2, 1] / 4 blur with clamped edges; three times divided by its
#                    median and clipped to 0.75..1.2.
# 3. shell         = shell / 255 x ratio, clipped to 0..1 (a light shell, R+G+B > 612, keeps 45% of the contrast).
# 4. decal         = the near helmet's logo box [x0, y0, x1, y1] laid onto the atlas rectangle [u0, v0, u1, v1] by an
#                    exact area average: source texel k covers [k*W, (k+1)*W) and target texel i covers
#                    [i*B, (i+1)*B) on a common integer axis (B = box width, W = target width; the same for rows), so
#                    every weight is an integer overlap. Each source texel's coverage is a40 = clip(max channel
#                    |colour - shell| - 24, 0, 40) (the sideline decal's alpha, times 40). Per target texel:
#                    A = min(2 sum(w a40) / (40 B H), 1) (coverage doubled: the near logo's 2-3 texel outline is
#                    under a texel wide at far size and would otherwise fade into the shell),
#                    colour = sum(w a40 rgb) / sum(w a40) / 255 (premultiplied, so the shell around the logo does not
#                    tint it), lit by clip(1 - (1 - ratio) / 2, 0.85, 1.1), laid as shell (1 - A) + colour A.
#                    ``flip`` mirrors the box first.
# 5. result        = floor(value x 255 + 0.5) into the island's RGB; alpha and every texel outside the island stay.
#
# Arithmetic: integers, and IEEE float64 + - * / in the written order (numpy elementwise; the only reductions are
# exact integer sums and medians of sorted values). No sqrt (distances are compared squared), no float32, no library
# resampling, no libm call. The luma weights 0.299 / 0.587 / 0.114 and the other constants are decimal literals,
# parsed to the same float64 everywhere.
#
# Operation (no "color" key; the compile adds palette entries for the new blends itself, max_blend_slots 64):
#   {"op": "rule", "module": "fill", "kind": "far_helmet", "near": 12,
#    "island": [38, 91, 126, 128], "decal": {"box": [34, 148, 132, 202], "to": [99, 107, 121, 119]}}
#   "near" is the donor key: 12 = the kit's own chunk 12 (row "donors": {"12": <sha256>}), or "SEL:chunk".
# Dispatch in nfl2k5_kit_rule_fill.apply:  if kind == "far_helmet": return far_helmet(out, op, rgba, donors)
FAR_FIELD_COLUMNS = 100             # helmet02 columns x < 100 * width / 256: the shell side (sideline field mode)
FAR_CELL = 24                           # colour cells of the mode (sideline _sideline_mode)
FAR_NEAR_SHADE = (0.6, 1.6)             # fabric shades: luma ratio range (sideline narrow membership)
FAR_NEAR_D2 = 0.0081                    # fabric shades: squared distance below (0.18 / 2) ** 2 (membership > 0.5)
FAR_NEAR_BLACK = 0.1                    # a fabric darker than this luma is matched by plain distance
FAR_FOLD_STRENGTH = 0.7                 # sideline shell repaint
FAR_FOLD_OFFSET = 0.05
FAR_FOLD_DARK = 0.25                    # folds of a fabric darker than this luma are faded (down to a quarter)
FAR_FOLD_CLIP = (0.75, 1.2)
FAR_LIGHT_SUM = 612                     # R + G + B above this: a light shell keeps 45% of the contrast
FAR_DECAL_FLOOR, FAR_DECAL_RANGE = 24, 40   # a near texel this far from the shell starts to be logo, fully at +40
FAR_SHADE_CLIP = (0.85, 1.1)
FAR_COVERAGE_GAIN = 2               # the averaged coverage times this, clipped to 1 (thin outlines keep colour)


def _far_require(ok, message):
    if not ok:
        raise ValueError("2026 kit fill rule far_helmet: " + message)


def _far_box(value, w, h, name):
    _far_require(isinstance(value, (list, tuple)) and len(value) == 4 and all(isinstance(v, int) for v in value),
             name + " must be four integers")
    x0, y0, x1, y1 = value
    _far_require(0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h, name + " outside the texture")
    return x0, y0, x1, y1


def _far_median_int(values):
    v = np.sort(np.asarray(values, np.int64))
    n = len(v)
    return int(v[n // 2]) if n % 2 else int((v[n // 2 - 1] + v[n // 2]) // 2)


def _far_median_f64(values):
    v = np.sort(np.asarray(values, np.float64).ravel())
    n = len(v)
    return float(v[n // 2]) if n % 2 else float((v[n // 2 - 1] + v[n // 2]) / 2.0)


def far_mode_colour(rgba, mask):
    """The most frequent 24-level colour cell inside ``mask`` (opaque texels), as the per-channel median of its
    members (integers)."""
    px = rgba[..., :3][mask & (rgba[..., 3] > 128)].astype(np.int64)
    _far_require(len(px) > 0, "no opaque texels to measure")
    cells = px // FAR_CELL
    values, inverse, counts = np.unique(cells, axis=0, return_inverse=True, return_counts=True)
    members = px[inverse.reshape(-1) == int(np.argmax(counts))]
    return np.array([_far_median_int(members[:, c]) for c in range(3)], np.int64)


def _far_luma(r, g, b):
    return r * 0.299 + g * 0.587 + b * 0.114


def _far_blur121(a):
    out = a
    for _ in range(2):
        p = np.pad(out, 1, mode="edge")
        out = ((p[1:-1, :-2] + 2.0 * p[1:-1, 1:-1]) + p[1:-1, 2:]) / 4.0
        p = np.pad(out, 1, mode="edge")
        out = ((p[:-2, 1:-1] + 2.0 * p[1:-1, 1:-1]) + p[2:, 1:-1]) / 4.0
    return out


def far_folds(rgba, box):
    """The island's painted folds as a brightness ratio (about 1.0), measured on its fabric only."""
    x0, y0, x1, y1 = box
    mask = np.zeros(rgba.shape[:2], bool)
    mask[y0:y1, x0:x1] = True
    fabric = far_mode_colour(rgba, mask)
    sub = rgba[y0:y1, x0:x1, :3].astype(np.float64) / 255.0
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    luma = _far_luma(r, g, b)
    sr, sg, sb = (float(v) / 255.0 for v in fabric)
    src_luma = _far_luma(sr, sg, sb)
    if src_luma < FAR_NEAR_BLACK:
        d2 = ((r - sr) * (r - sr) + (g - sg) * (g - sg)) + (b - sb) * (b - sb)
        known = d2 < FAR_NEAR_D2
    else:
        ratio = luma / src_luma
        k = np.clip(ratio, FAR_NEAR_SHADE[0], FAR_NEAR_SHADE[1])
        dr, dg, db = r - sr * k, g - sg * k, b - sb * k
        d2 = (dr * dr + dg * dg) + db * db
        known = (d2 < FAR_NEAR_D2) & (ratio >= FAR_NEAR_SHADE[0]) & (ratio <= FAR_NEAR_SHADE[1])
    core = known.copy()
    core[1:, :] &= known[:-1, :]
    core[:-1, :] &= known[1:, :]
    core[:, 1:] &= known[:, :-1]
    core[:, :-1] &= known[:, 1:]
    if int(core.sum()) * 5 > core.size:
        known = core
    lum = luma + FAR_FOLD_OFFSET
    out = np.ones_like(lum)
    if known.any():
        out[known] = lum[known] / _far_median_f64(lum[known])
    strength = FAR_FOLD_STRENGTH * min(max(src_luma / FAR_FOLD_DARK, 0.25), 1.0)
    out = 1.0 + (_far_blur121(out) - 1.0) * strength
    for _ in range(3):
        out = np.clip(out / _far_median_f64(out), FAR_FOLD_CLIP[0], FAR_FOLD_CLIP[1])
    return out


def _far_weights(source, target):
    """Integer overlaps: row i (target texel) x column k (source texel) on a common axis of source * target units."""
    w = np.zeros((target, source), np.int64)
    for i in range(target):
        lo, hi = i * source, (i + 1) * source
        for k in range(source):
            a, b = max(lo, k * target), min(hi, (k + 1) * target)
            if b > a:
                w[i, k] = b - a
    return w


def far_decal(near, shell, box, flip=False):
    """(a40 coverage, premultiplied sums) of the near helmet's logo box: integers."""
    x0, y0, x1, y1 = box
    crop = near[y0:y1, x0:x1, :3].astype(np.int64)
    if flip:
        crop = crop[:, ::-1]
    diff = np.abs(crop - np.asarray(shell, np.int64)[None, None, :]).max(axis=2)
    a40 = np.clip(diff - FAR_DECAL_FLOOR, 0, FAR_DECAL_RANGE)
    return a40, crop * a40[..., None]


def far_helmet(out, op, rgba, donors):
    """The far atlas helmet side of ``out``: the near helmet's shell colour lit by the island's folds of ``rgba``
    (the row's input), with the near helmet's logo laid in by an exact area average."""
    h, w = out.shape[:2]
    key = op.get("near")
    near = (donors or {}).get(key)
    _far_require(near is not None, "near-view helmet donor %r absent" % (key,))
    near = np.asarray(near)
    nh, nw = near.shape[:2]
    x0, y0, x1, y1 = _far_box(op.get("island"), w, h, "island")
    spec = op.get("decal")
    _far_require(isinstance(spec, dict), "decal {box, to} missing")
    bx0, by0, bx1, by1 = _far_box(spec.get("box"), nw, nh, "decal box")
    u0, v0, u1, v1 = _far_box(spec.get("to"), w, h, "decal target")
    _far_require(x0 <= u0 and u1 <= x1 and y0 <= v0 and v1 <= y1, "decal target outside the island")
    _far_require(bx1 - bx0 >= u1 - u0 and by1 - by0 >= v1 - v0, "the decal is a downsample: target larger than box")
    columns = np.zeros((nh, nw), bool)
    columns[:, :(FAR_FIELD_COLUMNS * nw) // 256] = True
    shell = far_mode_colour(near, columns)
    ratio = far_folds(rgba, (x0, y0, x1, y1))
    rs, gs, bs = (int(v) for v in shell)
    base = np.stack([float(rs) / 255.0 * ratio, float(gs) / 255.0 * ratio, float(bs) / 255.0 * ratio], axis=-1)
    if rs + gs + bs > FAR_LIGHT_SUM:
        k = 1.0 - (1.0 - ratio) * 0.45
        base = np.stack([float(rs) / 255.0 * k, float(gs) / 255.0 * k, float(bs) / 255.0 * k], axis=-1)
    new = np.clip(base, 0.0, 1.0)
    a40, pre = far_decal(near, shell, (bx0, by0, bx1, by1), bool(spec.get("flip", False)))
    wx = _far_weights(bx1 - bx0, u1 - u0)          # (target w, source w)
    wy = _far_weights(by1 - by0, v1 - v0)          # (target h, source h)
    cov = wy @ a40 @ wx.T                      # exact integer sums (int64)
    sums = [wy @ pre[..., c] @ wx.T for c in range(3)]
    total = FAR_DECAL_RANGE * (bx1 - bx0) * (by1 - by0)
    for ty in range(v1 - v0):
        for tx in range(u1 - u0):
            c = int(cov[ty, tx])
            if c == 0:
                continue
            a = min(float(c * FAR_COVERAGE_GAIN) / float(total), 1.0)
            iy, ix = v0 - y0 + ty, u0 - x0 + tx
            shade = min(max(1.0 - (1.0 - float(ratio[iy, ix])) / 2.0, FAR_SHADE_CLIP[0]), FAR_SHADE_CLIP[1])
            for ch in range(3):
                colour = float(int(sums[ch][ty, tx])) / float(c) / 255.0
                lit = min(max(colour * shade, 0.0), 1.0)
                new[iy, ix, ch] = new[iy, ix, ch] * (1.0 - a) + lit * a
    result = np.array(out, np.uint8, copy=True)
    result[y0:y1, x0:x1, :3] = np.floor(new * 255.0 + 0.5).astype(np.uint8)
    return result


def clear_near(out, op):
    """Inside ``boxes``, texels of alpha ``alpha`` whose largest RGB step from ``to`` is 1..``within`` take ``to``
    (a colour one or two levels off a field the import quantised; the Jaguars teal alternate's 3 transparent texels)."""
    to = _hex(op["to"])
    zone = np.zeros(out.shape[:2], bool)
    for box in op["boxes"]:
        zone |= box_mask(out.shape, box)
    step = np.abs(out[..., :3].astype(np.int64) - to).max(axis=2)
    hit = zone & (out[..., 3].astype(np.int64) == int(op["alpha"])) & (step > 0) & (step <= int(op["within"]))
    res = out.copy()
    res[hit, :3] = to.astype(np.uint8)
    return res


def apply(out, op, rgba, donors):
    """The fill rule ``op`` on ``out`` (the texture so far); ``rgba`` is the row's input level 0, ``donors`` its
    donor textures by key."""
    kind = op.get("kind")
    if kind == "helmet":
        return helmet(out, op, donors)
    if kind == "row":
        return row_fill(out, op)
    if kind == "far_helmet":
        return far_helmet(out, op, rgba, donors)
    if kind == "clear_near":
        return clear_near(out, op)
    raise ValueError("2026 kit fill rule: unknown kind " + repr(kind))
