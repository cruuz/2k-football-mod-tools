"""Repair the SOFTDRINK 2026 home and away kit art that the b772 uniform review found wrong.

Job uw2 captured all 64 current home and away kits in xemu and compared them
with dated 2025/26 club photos; job uf1 checked every finding against the
decoded native textures and the photos and fixed the real ones here.

The art is ours and lives in ``data/nfl2k5_kit_fixes_2026.json`` as vector
shapes in native texel coordinates (polygons, flood fills and recolours). Each
shape is drawn at four times the native size (a 4x4 sample grid per texel, in
exact integer arithmetic so every platform gets the same bytes) and averaged
down onto the texture's existing native pixels. Only the touched texels and
their mip parents change. The compile keeps the native format, size, mip count,
descriptors, wrapper and stored allocation of every chunk: P8 indices against
the chunk's own palette. Colours the palette lacks take unused entries, then
entries only the repainted texels used, then (only for a full palette) a
near-identical twin entry folded into its neighbour, so a protected texel
moves by at most one level. The ``_mud`` twin palette keeps its existing
entries byte for byte; new entries follow its rule (wet_93 for jersey, pants
and sleeve; darken_60 for socks).

The Studio runs this after its uniform layers. Exact input and output pins
limit it to the known SOFTDRINK kit spans: retail kits and textures a user's
own recipe replaced are left alone. The native repair (strict) refuses any
kit that is not exactly the pinned input or the pinned output.

Job uf2 (b772) added the 2026 alternate, throwback and Rivalries kits in a second data file,
``data/nfl2k5_kit_fixes_2026_alts.json`` (``apply_alternates``). It uses the same compiler plus: inner rings and
outside halos (outlines measured from the art itself), stamps of art that already sits in another texture of the
same kit (a helmet logo placed on a sleeve), palette-only recolours for the linear name plate and the digit
textures, cleared shoulder (TV) digits for kits that have none, and the Unif facemask colour.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

from . import nfl2k5_bump_texture_writer as bump
from nfl_txtr import decode_chunk, parse_chunks, parse_texture, swizzle_2d, unswizzle_2d
from nfl_vc_lz_fill import rebuild_fixed_span_filled

SCHEMA = "nfl2k5_kit_fixes_2026/v1"
DATA = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026.json"
DATA_ALTS = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_alts.json"
DATA_UF3 = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_uf3.json"
DATA_SEA1 = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_sea1.json"
DATA_OV1 = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_ov1.json"
KINDS = ("tset", "txtr", "copy_video", "palette", "clear", "unif", "name")
SUPER = 4                      # samples per texel along each axis (the 4x master)
UNIT = 200                     # fixed-point units per texel for shape coordinates
WET_NUM, WET_DEN = 93, 100     # w1's mud rule: mud = clean * 0.93, rounded
ADD_COLOUR_DISTANCE = 48       # squared RGB distance above which a scope colour earns a spare slot
ALPHA_DRIFT = 2                # helmet reflection alpha may move this far inside the art (as the uni helmet job)
MERGE_LEVELS = 1               # near-identical palette twins may be folded together (protected texels move <= 1 level)


def require(ok, message):
    if not ok:
        raise ValueError("2026 kit fixes: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def spec(path=None):
    document = json.loads(Path(path or DATA).read_text(encoding="utf-8"))
    require(document.get("schema") == SCHEMA, "unexpected data schema")
    seen = set()
    for row in document["textures"]:
        key = (row["selector"], row["chunk"])
        require(key not in seen, "duplicate texture entry " + repr(key))
        seen.add(key)
        require(row["kind"] in KINDS, "unknown chunk kind")
    return document


# -- art -------------------------------------------------------------------------------------------------------------

def hex_rgb(text):
    text = text.lstrip("#")
    require(len(text) == 6, "colour must be #RRGGBB")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def fixed(value):
    """Texel coordinate (float or int from JSON) to exact fixed-point units."""
    return int(round(float(value) * UNIT))


def polygon_coverage(points, width, height):
    """Samples covered (0..SUPER**2) per texel for one even-odd polygon, exact integer arithmetic."""
    pts = [(fixed(x), fixed(y)) for x, y in points]
    require(len(pts) >= 3, "a polygon needs three points")
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0 = max(min(xs) // UNIT, 0)
    x1 = min(-(-max(xs) // UNIT), width)
    y0 = max(min(ys) // UNIT, 0)
    y1 = min(-(-max(ys) // UNIT), height)
    cover = np.zeros((height, width), np.int64)
    if x1 <= x0 or y1 <= y0:
        return cover
    step = UNIT // SUPER
    sub = np.arange(SUPER, dtype=np.int64) * step + step // 2
    sx = (np.arange(x0, x1, dtype=np.int64)[:, None] * UNIT + sub[None, :]).ravel()
    sy = (np.arange(y0, y1, dtype=np.int64)[:, None] * UNIT + sub[None, :]).ravel()
    X, Y = np.meshgrid(sx, sy)
    inside = np.zeros(X.shape, bool)
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        if ay == by:
            continue
        crosses = (ay > Y) != (by > Y)
        dy = by - ay
        # X < ax + (Y - ay) * (bx - ax) / dy, without division
        lhs = (X - ax) * dy
        rhs = (Y - ay) * (bx - ax)
        left = (lhs < rhs) if dy > 0 else (lhs > rhs)
        inside ^= crosses & left
    counts = inside.reshape(y1 - y0, SUPER, x1 - x0, SUPER).sum(axis=(1, 3))
    cover[y0:y1, x0:x1] = counts
    return cover


def multipolygon_coverage(polys, width, height):
    """Samples covered (0..SUPER**2) per texel by the union of several polygons (a shape split into pieces, e.g. one
    piece per mesh triangle): a sample inside any piece counts once, so abutting pieces leave no blended seam."""
    step = UNIT // SUPER
    sub = np.arange(SUPER, dtype=np.int64) * step + step // 2
    inside_all = np.zeros((height * SUPER, width * SUPER), bool)
    for points in polys:
        pts = [(fixed(x), fixed(y)) for x, y in points]
        require(len(pts) >= 3, "a polygon needs three points")
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0 = max(min(xs) // UNIT, 0)
        x1 = min(-(-max(xs) // UNIT), width)
        y0 = max(min(ys) // UNIT, 0)
        y1 = min(-(-max(ys) // UNIT), height)
        if x1 <= x0 or y1 <= y0:
            continue
        sx = (np.arange(x0, x1, dtype=np.int64)[:, None] * UNIT + sub[None, :]).ravel()
        sy = (np.arange(y0, y1, dtype=np.int64)[:, None] * UNIT + sub[None, :]).ravel()
        X, Y = np.meshgrid(sx, sy)
        inside = np.zeros(X.shape, bool)
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if ay == by:
                continue
            crosses = (ay > Y) != (by > Y)
            dy = by - ay
            lhs = (X - ax) * dy
            rhs = (Y - ay) * (bx - ax)
            left = (lhs < rhs) if dy > 0 else (lhs > rhs)
            inside ^= crosses & left
        inside_all[y0 * SUPER:y1 * SUPER, x0 * SUPER:x1 * SUPER] |= inside
    return inside_all.reshape(height, SUPER, width, SUPER).sum(axis=(1, 3)).astype(np.int64)


def composite(rgba, cover, colour):
    """Blend ``colour`` over ``rgba`` by integer coverage; alpha keeps its native value."""
    n = cover[..., None]
    full = SUPER * SUPER
    src = np.array(colour, np.int64)[None, None, :]
    out = rgba.copy()
    blended = (rgba[..., :3].astype(np.int64) * (full - n) + src * n + full // 2) // full
    mask = cover > 0
    out[..., :3][mask] = blended[mask].astype(np.uint8)
    return out


def flood(rgba, seed, colour, tolerance, box):
    """4-connected fill of texels within ``tolerance`` (max channel delta) of the seed colour, inside ``box``."""
    h, w = rgba.shape[:2]
    bx0, by0, bx1, by1 = (int(v) for v in box)
    require(0 <= bx0 < bx1 <= w and 0 <= by0 < by1 <= h, "flood box outside the texture")
    sx, sy = (int(v) for v in seed)
    require(bx0 <= sx < bx1 and by0 <= sy < by1, "flood seed outside its box")
    target = rgba[sy, sx, :3].astype(np.int64)
    near = (np.abs(rgba[..., :3].astype(np.int64) - target).max(axis=2) <= int(tolerance))
    region = np.zeros((h, w), bool)
    stack = [(sx, sy)]
    while stack:
        x, y = stack.pop()
        if not (bx0 <= x < bx1 and by0 <= y < by1) or region[y, x] or not near[y, x]:
            continue
        region[y, x] = True
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    out = rgba.copy()
    out[..., :3][region] = np.array(colour, np.uint8)
    return out, region


def colour_hits(rgba, sources, tolerance):
    hit = np.zeros(rgba.shape[:2], bool)
    for source in sources:
        hit |= np.abs(rgba[..., :3].astype(np.int64) - np.array(hex_rgb(source), np.int64)).max(axis=2) <= int(tolerance)
    return hit


def box_mask(shape, box):
    h, w = shape[:2]
    bx0, by0, bx1, by1 = (int(v) for v in box)
    require(0 <= bx0 < bx1 <= w and 0 <= by0 < by1 <= h, "operation box outside the texture")
    mask = np.zeros((h, w), bool)
    mask[by0:by1, bx0:bx1] = True
    return mask


def recolour(rgba, box, sources, colour, tolerance, reference=None, invert=False):
    """Texels in ``box`` near any source colour (in ``reference``, default the current art) take the new colour;
    with ``invert`` every texel in the box that is NOT near a source colour does (clearing old art to the cloth)."""
    near = colour_hits(rgba if reference is None else reference, sources, tolerance)
    hit = box_mask(rgba.shape, box) & (~near if invert else near)
    out = rgba.copy()
    out[..., :3][hit] = np.array(colour, np.uint8)
    return out, hit


def grow(rgba, box, sources, colour, radius, into, tolerance, except_=None):
    """Widen a colour region: texels in ``box`` that are ``into`` colours (``["*"]``: any colour) and not
    ``except_`` colours, and lie within ``radius`` texels (Euclidean, texel centres) of a source-coloured texel,
    take ``colour``."""
    inside = box_mask(rgba.shape, box)
    seed = colour_hits(rgba, sources, tolerance)
    target = inside & ~seed & (np.ones_like(seed) if into == ["*"] else colour_hits(rgba, into, tolerance))
    if except_:
        target &= ~colour_hits(rgba, except_, tolerance)
    near = np.zeros_like(seed)
    r = float(radius)
    k = int(np.ceil(r))
    h, w = seed.shape
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            if dx * dx + dy * dy > r * r:
                continue
            shifted = np.zeros_like(seed)
            ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
            xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
            shifted[yd, xd] = seed[ys, xs]
            near |= shifted
    hit = target & near
    out = rgba.copy()
    out[..., :3][hit] = np.array(colour, np.uint8)
    return out, hit


def enclosed(rgba, box, edge, colour, tolerance, invert=False):
    """Fill every 4-connected region of non-``edge`` texels inside ``box`` that does not touch the box border
    (the hollow inside of an outlined letter) with ``colour``. With ``invert`` the ``edge`` colours are the open
    field and every other colour is a wall."""
    inside = box_mask(rgba.shape, box)
    wall = colour_hits(rgba, edge, tolerance)
    if invert:
        wall = ~wall
    open_ = inside & ~wall
    bx0, by0, bx1, by1 = (int(v) for v in box)
    reached = np.zeros_like(open_)
    stack = [(x, y) for x in range(bx0, bx1) for y in (by0, by1 - 1)] + \
            [(x, y) for y in range(by0, by1) for x in (bx0, bx1 - 1)]
    while stack:
        x, y = stack.pop()
        if not (bx0 <= x < bx1 and by0 <= y < by1) or reached[y, x] or not open_[y, x]:
            continue
        reached[y, x] = True
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    hit = open_ & ~reached
    out = rgba.copy()
    out[..., :3][hit] = np.array(colour, np.uint8)
    return out, hit


def copy_texels(out, source, op):
    """Move existing art: texels of the ORIGINAL level 0 in ``src`` that differ from ``skip`` (the cloth colour,
    within ``tolerance``) are copied to ``dst``; ``flip`` "h" or "v" mirrors them."""
    h, w = out.shape[:2]
    x0, y0, x1, y1 = (int(v) for v in op["src"])
    dx, dy = (int(v) for v in op["dst"])
    require(0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h, "copy source outside the texture")
    require(0 <= dx and dx + (x1 - x0) <= w and 0 <= dy and dy + (y1 - y0) <= h, "copy target outside the texture")
    block = source[y0:y1, x0:x1].copy()
    if op.get("flip") == "h":
        block = block[:, ::-1]
    elif op.get("flip") == "v":
        block = block[::-1]
    keep = np.ones(block.shape[:2], bool)
    if "skip_col" in op:
        # skip texels equal to their own row's colour at column ``skip_col`` (art lying on horizontal bands)
        ref = source[y0:y1, int(op["skip_col"]), :3].astype(np.int64)[:, None, :]
        if op.get("flip") == "v":
            ref = ref[::-1]
        keep &= np.abs(block[..., :3].astype(np.int64) - ref).max(axis=2) > int(op.get("tolerance", 24))
    if "skip" in op:
        skip = np.array(hex_rgb(op["skip"]), np.int64)
        keep &= np.abs(block[..., :3].astype(np.int64) - skip).max(axis=2) > int(op.get("tolerance", 24))
    region = out[dy:dy + block.shape[0], dx:dx + block.shape[1]]
    region[keep] = block[keep]
    return out


def _offsets(radius):
    r = float(radius)
    k = int(np.ceil(r))
    return sorted(((dx * dx + dy * dy, dx, dy) for dy in range(-k, k + 1) for dx in range(-k, k + 1)
                   if dx * dx + dy * dy <= r * r))


def _shift(mask, dx, dy):
    h, w = mask.shape
    out = np.zeros_like(mask)
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = mask[ys, xs]
    return out


def dist2(mask, radius):
    """Squared texel-centre distance to the nearest True texel, for distances up to ``radius``; farther texels
    (and every texel when the mask is empty) get a value above radius**2."""
    far = int(np.ceil(float(radius))) ** 2 * 4 + 4
    out = np.full(mask.shape, far, np.int64)
    for d2, dx, dy in reversed(_offsets(radius)):
        out[_shift(mask, dx, dy)] = d2
    return out


def ring(rgba, op, original):
    """Inner ring: texels of the ``inside`` colours (or every opaque texel for ``"opaque"``) whose distance to the
    nearest texel outside that set lies in (``from``, ``to``] take ``colour``; ``to`` null means any depth."""
    ref = original if op.get("match") == "original" else rgba
    tolerance = op.get("tolerance", 24)
    opaque = ref[..., 3] >= 128
    if op["inside"] == "opaque":
        inside = opaque
    elif op.get("invert"):
        # every colour except the listed ones (a shape drawn on a known field colour)
        inside = ~colour_hits(ref, op["inside"], tolerance) & opaque
    else:
        inside = colour_hits(ref, op["inside"], tolerance) & opaque
    r0 = float(op.get("from", 0))
    r1 = op.get("to")
    limit = max(r0, float(r1) if r1 is not None else r0) + 1
    d2 = dist2(~inside, limit)
    hit = box_mask(rgba.shape, op["box"]) & inside & (d2 > r0 * r0)
    if r1 is not None:
        hit &= d2 <= float(r1) * float(r1)
    out = rgba.copy()
    out[..., :3][hit] = np.array(hex_rgb(op["color"]), np.uint8)
    return out, hit


def outside_region(rgba, box, edge, tolerance):
    """Texels in ``box`` that reach the box border without crossing an ``edge`` colour."""
    inside = box_mask(rgba.shape, box)
    wall = colour_hits(rgba, edge, tolerance)
    open_ = inside & ~wall
    bx0, by0, bx1, by1 = (int(v) for v in box)
    reached = np.zeros_like(open_)
    stack = [(x, y) for x in range(bx0, bx1) for y in (by0, by1 - 1)] + \
            [(x, y) for y in range(by0, by1) for x in (bx0, bx1 - 1)]
    while stack:
        x, y = stack.pop()
        if not (bx0 <= x < bx1 and by0 <= y < by1) or reached[y, x] or not open_[y, x]:
            continue
        reached[y, x] = True
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return reached, wall


def halo(rgba, op):
    """Outside outline: texels outside an outlined shape (reached from the box border without crossing the ``edge``
    colours) within ``radius`` of an edge texel take ``colour``; ``into`` limits it to those colours."""
    tolerance = op.get("tolerance", 24)
    reached, wall = outside_region(rgba, op["box"], op["edge"], tolerance)
    hit = reached & (dist2(wall, op["radius"]) <= float(op["radius"]) ** 2)
    if op.get("into"):
        hit &= colour_hits(rgba, op["into"], op.get("into_tolerance", tolerance))
    out = rgba.copy()
    out[..., :3][hit] = np.array(hex_rgb(op["color"]), np.uint8)
    return out, hit


def stamp(rgba, op, source):
    """Place existing art: the ``src`` box of ``source`` (this texture's original level 0, or another texture of the
    same kit) is resampled into the ``dst`` box at 4x (4x4 samples per texel, exact integer arithmetic). Source texels
    near a ``skip`` colour or below alpha 128 are not drawn; ``remap`` pairs recolour the drawn samples."""
    h, w = rgba.shape[:2]
    sh, sw = source.shape[:2]
    sx0, sy0, sx1, sy1 = (fixed(v) for v in op["src"])
    dx0, dy0, dx1, dy1 = (fixed(v) for v in op["dst"])
    require(dx1 > dx0 and dy1 > dy0 and sx0 != sx1 and sy0 != sy1, "stamp boxes are empty")
    require(0 <= min(sx0, sx1) and max(sx0, sx1) <= sw * UNIT and 0 <= min(sy0, sy1) and max(sy0, sy1) <= sh * UNIT,
            "stamp source outside its texture")
    colours = source[..., :3].astype(np.int64).copy()
    keep = source[..., 3] >= 128
    if op.get("skip"):
        keep &= ~colour_hits(source, op["skip"], op.get("tolerance", 24))
    if op.get("only"):
        # uf3: draw only source texels near these colours (a logo taken off a differently coloured shell)
        keep &= colour_hits(source, op["only"], op.get("only_tolerance", 24))
    for pair in op.get("remap", []):
        hit = keep & colour_hits(source, pair["from"], pair.get("tolerance", 24))
        colours[hit] = np.array(hex_rgb(pair["to"]), np.int64)
    if op.get("scale_rgb"):
        # brighten or darken drawn samples: channel * num // den, clamped (exact integers)
        num, den = (int(v) for v in op["scale_rgb"])
        colours = np.minimum((colours * num + den // 2) // den, 255)
    weight = None
    if op.get("alpha_line"):
        # uf3: the source is a mark drawn on a plain field; each source texel's position on the line from
        # ``field`` to ``mark`` (0..256, exact integers) is how much of ``color`` it lays down, so the mark lands on
        # any background with its anti-aliasing intact
        f = np.array(hex_rgb(op["alpha_line"]["field"]), np.int64)
        m = np.array(hex_rgb(op["alpha_line"]["mark"]), np.int64)
        d = m - f
        den_l = int((d * d).sum())
        num_l = ((source[..., :3].astype(np.int64) - f) * d).sum(axis=2)
        weight = np.clip((num_l * 256 + den_l // 2) // den_l, 0, 256) * keep
        colours[:] = np.array(hex_rgb(op["color"]), np.int64)
    x0 = max(dx0 // UNIT, 0)
    x1 = min(-(-dx1 // UNIT), w)
    y0 = max(dy0 // UNIT, 0)
    y1 = min(-(-dy1 // UNIT), h)
    out = rgba.copy()
    scope = np.zeros((h, w), bool)
    if x1 <= x0 or y1 <= y0:
        return out, scope
    step = UNIT // SUPER
    sub = np.arange(SUPER, dtype=np.int64) * step + step // 2
    px = (np.arange(x0, x1, dtype=np.int64)[:, None] * UNIT + sub[None, :]).ravel()
    py = (np.arange(y0, y1, dtype=np.int64)[:, None] * UNIT + sub[None, :]).ravel()
    inx = (px >= dx0) & (px < dx1)
    iny = (py >= dy0) & (py < dy1)
    ux = sx0 + ((px - dx0) * (sx1 - sx0)) // (dx1 - dx0)
    uy = sy0 + ((py - dy0) * (sy1 - sy0)) // (dy1 - dy0)
    tx = np.clip(ux // UNIT, 0, sw - 1)
    ty = np.clip(uy // UNIT, 0, sh - 1)
    TX, TY = np.meshgrid(tx, ty)
    IN = np.meshgrid(inx, iny)
    drawn = keep[TY, TX] & IN[0] & IN[1]
    gh, gw = y1 - y0, x1 - x0
    if weight is None:
        sample = colours[TY, TX] * drawn[..., None]
        n = drawn.reshape(gh, SUPER, gw, SUPER).sum(axis=(1, 3))
        total = sample.reshape(gh, SUPER, gw, SUPER, 3).sum(axis=(1, 3))
        full = SUPER * SUPER
    else:
        w = weight[TY, TX] * drawn
        sample = colours[TY, TX] * w[..., None]
        n = w.reshape(gh, SUPER, gw, SUPER).sum(axis=(1, 3))
        total = sample.reshape(gh, SUPER, gw, SUPER, 3).sum(axis=(1, 3))
        full = SUPER * SUPER * 256
    base = rgba[y0:y1, x0:x1, :3].astype(np.int64)
    blended = (base * (full - n)[..., None] + total + full // 2) // full
    hit = n > 0
    region = out[y0:y1, x0:x1]
    region[..., :3][hit] = blended[hit].astype(np.uint8)
    scope[y0:y1, x0:x1] = hit
    return out, scope


def close_gaps(rgba, op):
    """Morphological closing of the ``colors`` mask inside ``box`` (dilate then erode by ``radius``): the texels it
    adds (gaps between the lines of a drawn shape) that match ``into`` take ``colour``."""
    tolerance = op.get("tolerance", 24)
    box = box_mask(rgba.shape, op["box"])
    mask = colour_hits(rgba, op["colors"], tolerance) & box
    r = float(op["radius"])
    dilated = dist2(mask, r) <= r * r
    closed = ~(dist2(~dilated, r) <= r * r)
    hit = closed & ~mask & box
    if op.get("into"):
        hit &= colour_hits(rgba, op["into"], op.get("into_tolerance", tolerance))
    out = rgba.copy()
    out[..., :3][hit] = np.array(hex_rgb(op["color"]), np.uint8)
    return out, hit


def lift(rgba, op):
    """Lighten matched texels toward white: channel' = 255 - (255 - channel) * num // den (exact integers)."""
    hit = box_mask(rgba.shape, op["box"]) & colour_hits(rgba, op["from"], op.get("tolerance", 24))
    num, den = (int(v) for v in op["keep"])
    out = rgba.copy()
    c = out[..., :3].astype(np.int64)
    lifted = 255 - ((255 - c) * num + den // 2) // den
    out[..., :3][hit] = lifted[hit].astype(np.uint8)
    return out, hit


def retint(rgba, op):
    """Recolour a mark drawn on a plain field, keeping its anti-aliasing: each texel in ``box`` that lies on the line
    from ``base`` (the field) towards ``source`` (the mark) at fraction t takes base + t * (colour - base), in exact
    integers. Texels off that line (other art) stay. uf3: ``field`` (default ``base``) moves the field too: those
    texels take field + t * (colour - field), so a mark stamped from a white field lands on a coloured one with its
    anti-aliasing intact."""
    box = box_mask(rgba.shape, op["box"])
    base = np.array(hex_rgb(op["base"]), np.int64)
    src = np.array(hex_rgb(op["source"]), np.int64)
    dst = np.array(hex_rgb(op["color"]), np.int64)
    field = np.array(hex_rgb(op.get("field", op["base"])), np.int64)
    c = rgba[..., :3].astype(np.int64)
    d = src - base
    den = int((d * d).sum())
    num = ((c - base) * d).sum(axis=2)
    num = np.clip(num, 0, den)
    # distance from the line, squared, times den (exact)
    proj = base[None, None, :] * den + d[None, None, :] * num[..., None]
    off = ((c * den - proj) ** 2).sum(axis=2)
    tol = int(op.get("tolerance", 24))
    hit = box & (num * 20 > den) & (off <= (tol * den) ** 2)
    out = rgba.copy()
    new = (field[None, None, :] * den + (dst - field)[None, None, :] * num[..., None] + den // 2) // den
    out[..., :3][hit] = np.clip(new, 0, 255)[hit].astype(np.uint8)
    return out, hit


def paint(rgba, ops, donors=None):
    """Apply the authored operations in order; returns the new level 0 and the changed scope."""
    out = rgba.copy()
    h, w = out.shape[:2]
    for op in ops:
        kind = op["op"]
        if kind == "poly":
            cover = polygon_coverage(op["points"], w, h)
            if "only" in op:
                # draw only over texels of these colours (a pattern that stays inside an existing shape)
                cover = np.where(colour_hits(out, op["only"], op.get("only_tolerance", 24)), cover, 0)
            if "protect" in op:
                # keep existing art: per column inside the box, every row between the first and the last texel of
                # the protected colours (a band with a wordmark on it) stays as it is
                guard = op["protect"]
                hits = box_mask(out.shape, guard["box"]) & colour_hits(out, guard["colors"], guard.get("tolerance", 24))
                rows = np.arange(h)[:, None]
                first = np.where(hits.any(axis=0), hits.argmax(axis=0), h)
                last = np.where(hits.any(axis=0), h - 1 - hits[::-1].argmax(axis=0), -1)
                cover = np.where((rows >= first[None, :]) & (rows <= last[None, :]), 0, cover)
            out = composite(out, cover, hex_rgb(op["color"]))
            if "alpha" in op:
                out[..., 3][cover * 2 >= SUPER * SUPER] = int(op["alpha"])
        elif kind == "multipoly":
            cover = multipolygon_coverage(op["polys"], w, h)
            if "only" in op:
                cover = np.where(colour_hits(out, op["only"], op.get("only_tolerance", 24)), cover, 0)
            out = composite(out, cover, hex_rgb(op["color"]))
            if "alpha" in op:
                # a decal that was hidden (alpha 0) becomes opaque where at least half its samples are covered
                out[..., 3][cover * 2 >= SUPER * SUPER] = int(op["alpha"])
        elif kind == "flood":
            out, _ = flood(out, op["seed"], hex_rgb(op["color"]), op.get("tolerance", 24), op["box"])
        elif kind == "recolor":
            reference = rgba if op.get("match") == "original" else None
            out, _ = recolour(out, op["box"], op["from"], hex_rgb(op["color"]), op.get("tolerance", 24), reference,
                              bool(op.get("invert", False)))
        elif kind == "grow":
            out, _ = grow(out, op["box"], op["from"], hex_rgb(op["color"]), op["radius"], op["into"],
                          op.get("tolerance", 24), op.get("except"))
        elif kind == "enclosed":
            out, _ = enclosed(out, op["box"], op["edge"], hex_rgb(op["color"]), op.get("tolerance", 24),
                              bool(op.get("invert", False)))
        elif kind == "copy":
            out = copy_texels(out, rgba, op)
        elif kind == "ring":
            out, _ = ring(out, op, rgba)
        elif kind == "halo":
            out, _ = halo(out, op)
        elif kind == "close":
            out, _ = close_gaps(out, op)
        elif kind == "lift":
            out, _ = lift(out, op)
        elif kind == "retint":
            out, _ = retint(out, op)
        elif kind == "texels":
            # uf3 (b773): listed texels [x, y] take one colour (left-over pieces of an old decal, measured on the
            # shipped art); ``alpha`` sets their alpha as well
            pts = np.asarray(op["points"], np.int64).reshape(-1, 2)
            require(len(pts) and (pts >= 0).all() and (pts[:, 0] < w).all() and (pts[:, 1] < h).all(),
                    "texel outside the texture")
            out[pts[:, 1], pts[:, 0], :3] = np.array(hex_rgb(op["color"]), np.uint8)
            if "alpha" in op:
                out[pts[:, 1], pts[:, 0], 3] = int(op["alpha"])
        elif kind == "stamp":
            donor = op.get("donor", "self")
            # a chunk of the same kit (an integer) or, uf3, of another kit ("SELECTOR:chunk")
            key = donor if isinstance(donor, str) and ":" in donor else None if donor == "self" else int(donor)
            source = rgba if donor == "self" else (donors or {}).get(key)
            require(source is not None, "stamp donor texture absent")
            out, _ = stamp(out, op, source)
        else:
            raise ValueError("2026 kit fixes: unknown art operation " + repr(kind))
    scope = np.any(out != rgba, axis=2)
    return out, scope


def art_colours(ops):
    return sorted({hex_rgb(op["color"]) for op in ops})


# -- native textures -------------------------------------------------------------------------------------------------

def _tset_textures(decoded):
    count = struct.unpack_from("<I", decoded, 4)[0]
    textures = []
    for reference in range(count):
        base = 0x18 + reference * 0x24
        name_at = base + 4 + struct.unpack_from("<i", decoded, base + 4)[0] - 1
        desc_at = base + 8 + struct.unpack_from("<i", decoded, base + 8)[0] - 1
        end = name_at
        while decoded[end:end + 2] != b"\0\0":
            end += 2
        name = decoded[name_at:end].decode("utf-16le")
        _, pixel, palette, fmt, size, _flags = struct.unpack_from("<6I", decoded, desc_at)
        width = size & 0xFFFF if size else 1 << ((fmt >> 20) & 15)
        height = size >> 16 if size else 1 << ((fmt >> 24) & 15)
        textures.append(dict(name=name, pixel=pixel, palette=palette, width=width, height=height,
                             mips=(fmt >> 16) & 15, format=(fmt >> 8) & 255))
    return textures


def native_textures(span, kind):
    """(chunk, decoded, [textures]) with the clean texture first and its _mud twin (TSET) second."""
    chunks = parse_chunks(span)
    require(len(chunks) == 1 and chunks[0].end_offset == len(span), "expected one complete chunk span")
    chunk = chunks[0]
    require(chunk.compressed, "kit chunk is not compressed")
    decoded, _ = decode_chunk(span, chunk)
    if kind == "tset":
        require(chunk.kind == "TSET", "expected a TSET chunk")
        textures = _tset_textures(decoded)
        require(len(textures) == 2 and textures[1]["name"] == textures[0]["name"] + "_mud",
                "expected one clean texture and its _mud twin")
        require(textures[0]["pixel"] == textures[1]["pixel"], "clean and mud must share their indices")
    else:
        require(chunk.kind == "TXTR", "expected a TXTR chunk")
        texture = parse_texture(decoded, chunk)
        require(texture.format_name == "P8", "expected a P8 texture")
        textures = [dict(name=texture.name, pixel=texture.pixel_offset, palette=texture.palette_offset,
                         width=texture.width, height=texture.height, mips=texture.mip_levels, format=0x0B)]
    for t in textures:
        require(t["format"] == 0x0B, "only P8 kit textures are supported")
    return chunk, decoded, textures


def mip_sizes(texture):
    return [(max(texture["width"] >> i, 1), max(texture["height"] >> i, 1)) for i in range(texture["mips"])]


def read_planes(decoded, chunk, texture):
    base = chunk.system_bytes + texture["pixel"]
    planes = []
    for w, h in mip_sizes(texture):
        raw = unswizzle_2d(decoded[base:base + w * h], w, h, 1)
        planes.append(np.frombuffer(raw, np.uint8).reshape(h, w).copy())
        base += w * h
    return planes


def read_palette(decoded, chunk, texture):
    at = chunk.system_bytes + texture["palette"]
    bgra = np.frombuffer(decoded[at:at + 1024], np.uint8).reshape(256, 4)
    return bgra[:, [2, 1, 0, 3]].astype(np.int64)


def write_texture(decoded, chunk, texture, planes, palette=None):
    out = bytearray(decoded)
    base = chunk.system_bytes + texture["pixel"]
    for (w, h), plane in zip(mip_sizes(texture), planes):
        out[base:base + w * h] = swizzle_2d(np.ascontiguousarray(plane, np.uint8).tobytes(), w, h, 1)
        base += w * h
    if palette is not None:
        at = chunk.system_bytes + texture["palette"]
        out[at:at + 1024] = np.ascontiguousarray(palette[:, [2, 1, 0, 3]], np.uint8).tobytes()
    return bytes(out)


def wet(palette):
    out = palette.copy()
    out[:, :3] = (palette[:, :3] * WET_NUM + WET_DEN // 2) // WET_DEN
    return out


def dark(palette):
    """The retail darken_60 twin rule (equipment chunks such as socks keep it; w1 moved only jersey, pants, sleeve)."""
    out = palette.copy()
    out[:, :3] = (palette[:, :3] * 3 + 2) // 5
    return out


MUD_RULES = {"wet_93": wet, "darken_60": dark}


def mud_rule(clean, mud, used):
    """The rule the chunk's _mud twin follows: every used entry within one level of it (equipment twins were
    quantised separately, so their rounding varies by one)."""
    for name, rule in MUD_RULES.items():
        expect = rule(clean)
        if np.abs(mud[used] - expect[used]).max() <= 1:
            return name
    # uf2: some alternate kits carry a separately painted mud twin (its own dirt colours per index). New entries then
    # take the dirt ratio of the nearest existing clean entry ("pair", see pair_mud).
    return "pair"


def pair_mud(clean, mud, slots, reference):
    """Mud colour for new clean entries ``slots``: the nearest ``reference`` entry's per-channel mud/clean ratio
    (exact integers, clamped), alpha as the clean entry."""
    out = mud.copy()
    ref = np.array(sorted(set(int(i) for i in reference) - set(int(s) for s in slots)), np.int64)
    require(len(ref) > 0, "no reference entries for the mud twin")
    for s in slots:
        d = ((clean[ref, :3] - clean[s, :3]) ** 2).sum(axis=1)
        j = int(ref[int(d.argmin())])
        for k in range(3):
            base = int(clean[j, k])
            out[s, k] = min(255, (int(clean[s, k]) * int(mud[j, k]) + base // 2) // base) if base else int(mud[j, k])
        out[s, 3] = clean[s, 3]
    return out


def nearest(colours, alphas, palette):
    """Nearest palette index per colour: same alpha when the palette has it, else within ALPHA_DRIFT (helmet
    reflection masks), lowest index on ties."""
    result = np.zeros(len(colours), np.int64)
    for alpha in np.unique(alphas):
        candidates = np.flatnonzero(palette[:, 3] == alpha)
        if not len(candidates):
            candidates = np.flatnonzero(np.abs(palette[:, 3] - alpha) <= ALPHA_DRIFT)
        require(len(candidates) > 0, "a stored alpha is absent from the palette")
        pick = alphas == alpha
        distance = ((colours[pick][:, None, :] - palette[candidates, :3][None, :, :]) ** 2).sum(axis=2)
        result[pick] = candidates[distance.argmin(axis=1)]
    return result


def scope_chain(scope, planes):
    """The changed mask at every stored mip (a parent texel changes when any of its children does)."""
    masks = [scope]
    for plane in planes[1:]:
        h, w = plane.shape
        masks.append(masks[-1].reshape(h, 2, w, 2).any(axis=(1, 3)))
    return masks


def free_slots(planes, masks):
    """Palette slots no protected texel uses at any mip: unused entries first, then entries referenced only inside
    the repainted area (every texel using them is re-quantised, so giving them a new colour is invisible elsewhere)."""
    outside = np.zeros(256, bool)
    used = np.zeros(256, bool)
    for plane, mask in zip(planes, masks):
        used[np.unique(plane)] = True
        outside[np.unique(plane[~mask])] = True
    return [i for i in range(256) if not used[i]] + [i for i in range(256) if used[i] and not outside[i]]


def merge_twins(palette, mud, planes, masks, needed, alpha, limit=MERGE_LEVELS):
    """Free ``needed`` palette slots by folding entries into a near-identical twin (same alpha, every clean and
    mud channel within ``limit`` levels): the merged entry's texels take the twin's index, so a protected texel
    moves by at most ``limit`` levels. Returns the freed slots and the number of protected texels moved."""
    if needed <= 0:
        return [], 0
    counts = np.zeros(256, np.int64)
    for plane in planes:
        counts += np.bincount(plane.ravel(), minlength=256)
    candidates = []
    idx = [i for i in range(256) if palette[i, 3] == alpha and counts[i] > 0]
    for a in idx:
        for b in idx:
            if a == b:
                continue
            if np.abs(palette[a, :3] - palette[b, :3]).max() > limit:
                continue
            if mud is not None and np.abs(mud[a, :3] - mud[b, :3]).max() > limit:
                continue
            candidates.append((int(counts[a]), a, b))           # fold a (rarer first) into b
    freed, moved, gone = [], 0, set()
    for count, a, b in sorted(candidates):
        if len(freed) >= needed:
            break
        if a in gone or b in gone:
            continue
        for plane in planes:
            plane[plane == a] = b
        gone.add(a)
        freed.append(a)
        moved += count
    return freed, moved


def extend_palette(palette, free, wanted, alpha):
    """Give exact art colours (and frequent blends far from every entry) unused palette slots from ``free``."""
    added = []
    for colour in wanted:
        rgb = np.array(colour, np.int64)
        same_alpha = np.flatnonzero(palette[:, 3] == alpha)
        distance = ((palette[same_alpha, :3] - rgb) ** 2).sum(axis=1)
        if len(distance) and distance.min() <= ADD_COLOUR_DISTANCE // 4:
            keep = int(same_alpha[distance.argmin()])
            if keep in free:
                free.remove(keep)          # reserved: a reusable entry that already holds this colour
            continue
        if not free:
            break
        slot = free.pop(0)
        palette[slot, :3] = rgb
        palette[slot, 3] = alpha
        added.append(dict(slot=slot, rgb="#%02X%02X%02X" % colour, alpha=int(alpha)))
    return added


def compile_texture(span, row, donors=None):
    """Paint ``row``'s art into one native chunk span; returns (new span, receipt). ``donors`` maps a chunk index
    of the same kit to its level-0 RGBA (stamp sources)."""
    chunk, decoded, textures = native_textures(span, row["kind"])
    clean = textures[0]
    require(clean["name"] == row["texture"], "texture name differs: " + clean["name"])
    require((clean["width"], clean["height"], clean["mips"]) == tuple(row["size"]), "texture size differs")
    planes = read_planes(decoded, chunk, clean)
    original_planes = [p.copy() for p in planes]
    palette = read_palette(decoded, chunk, clean)
    original_palette = palette.copy()
    rule = mud = None
    if row["kind"] == "tset":
        mud = read_palette(decoded, chunk, textures[1])
        rule = mud_rule(palette, mud, np.unique(np.concatenate([p.ravel() for p in planes])))
    h, w = planes[0].shape
    base = palette[planes[0]].astype(np.uint8)
    painted, scope = paint(base, row["ops"], donors)
    require(scope.any(), "the art changed no texel")
    alphas = painted[..., 3].astype(np.int64)
    alpha_changed = painted[..., 3] != base[..., 3]
    # exact art colours first, then the most frequent edge blends far from the palette, per alpha class in the art
    wanted = art_colours([op for op in row["ops"] if "color" in op])
    added, free = [], free_slots(planes, scope_chain(scope, planes))
    merged_moved = merged_slots = 0
    classes, sizes = np.unique(alphas[scope], return_counts=True)
    for alpha, size in sorted(zip(classes.tolist(), sizes.tolist()), key=lambda t: (-t[1], t[0])):
        if alpha == 0 or size * 50 < int(scope.sum()):
            continue                      # transparent holes and stray reflection texels use the nearest entry
        here = scope & (alphas == alpha)
        colours, counts = np.unique(painted[here][:, :3].astype(np.int64), axis=0, return_counts=True)
        order = sorted(range(len(colours)), key=lambda i: (-int(counts[i]), tuple(int(v) for v in colours[i])))
        same = palette[palette[:, 3] == alpha][:, :3]
        blends = []
        for i in order:
            c = tuple(int(v) for v in colours[i])
            if c not in wanted and (not len(same) or ((same - np.array(c)) ** 2).sum(axis=1).min() > ADD_COLOUR_DISTANCE):
                blends.append(c)
        want_here = wanted + blends[:int(row.get("max_blend_slots", 24))]
        missing = [c for c in wanted
                   if not len(same) or ((same - np.array(c)) ** 2).sum(axis=1).min() > ADD_COLOUR_DISTANCE // 4]
        if len(missing) > len(free):
            more, moved = merge_twins(palette, mud, planes, scope_chain(scope, planes), len(missing) - len(free), alpha)
            free += more
            merged_moved += moved
            merged_slots += len(more)
        added += extend_palette(palette, free, want_here, alpha)
    new_planes, rows, mode_planes = [], [], {}
    target = painted.astype(np.int64)
    changed = scope
    for level, plane in enumerate(planes):
        ph, pw = plane.shape
        out = plane.copy()
        points = np.argwhere(changed)
        if len(points) and level in mode_planes:
            out[points[:, 0], points[:, 1]] = mode_planes[level][points[:, 0], points[:, 1]]
        elif len(points):
            colours = target[points[:, 0], points[:, 1], :3]
            # each stored mip keeps its own alpha (helmet reflection masks are authored per level), except where the
            # art itself changed the alpha (a hidden decal made opaque): there the art's alpha, snapped to 0 or 255
            alphas_here = palette[plane][points[:, 0], points[:, 1], 3]
            if alpha_changed.any():
                moved = alpha_changed[points[:, 0], points[:, 1]]
                wanted_alpha = target[points[:, 0], points[:, 1], 3]
                if level:
                    wanted_alpha = np.where(wanted_alpha >= 128, 255, 0)
                alphas_here = np.where(moved, wanted_alpha, alphas_here)
            out[points[:, 0], points[:, 1]] = nearest(colours, alphas_here, palette)
        quantized = palette[out]
        require(np.array_equal(quantized[~changed], palette[plane][~changed]), "protected texel changed")
        if merged_slots:
            # folded twins: protected texels may differ from the shipped colour by at most MERGE_LEVELS
            shipped = original_palette[original_planes[level]]
            require(np.abs(quantized[~changed].astype(np.int64) - shipped[~changed]).max() <= MERGE_LEVELS,
                    "palette twin merge moved a protected texel too far")
        rows.append(dict(level=level, width=pw, height=ph, scope_texels=int(changed.sum()),
                         changed_indices=int((out != plane).sum())))
        new_planes.append(out)
        if level + 1 < len(planes):
            nh, nw = planes[level + 1].shape
            require((nh * 2, nw * 2) == (ph, pw), "unexpected mip chain")
            target = (quantized.reshape(nh, 2, nw, 2, 4).sum(axis=(1, 3)) + 2) // 4
            changed = changed.reshape(nh, 2, nw, 2).any(axis=(1, 3))
            alpha_changed = alpha_changed.reshape(nh, 2, nw, 2).any(axis=(1, 3))
            if row.get("mip") == "mode":
                # uf2: small fixed allocations (digits, busy helmets) keep the parent indices crisp: each changed
                # parent takes the most frequent of its four child indices (lowest index on ties), not a blend
                kids = out.reshape(nh, 2, nw, 2).transpose(0, 2, 1, 3).reshape(nh, nw, 4).astype(np.int64)
                best = np.full((nh, nw), 256, np.int64)
                best_n = np.zeros((nh, nw), np.int64)
                for k in range(4):
                    v = kids[..., k]
                    n = (kids == v[..., None]).sum(axis=2)
                    better = (n > best_n) | ((n == best_n) & (v < best))
                    best = np.where(better, v, best)
                    best_n = np.where(better, n, best_n)
                mode_planes[level + 1] = best
    new = write_texture(decoded, chunk, clean, new_planes, palette)
    if row["kind"] == "tset":
        # existing twin entries stay byte-exact; only the slots this fix filled get the rule's value
        twin = mud.copy()
        slots = [a["slot"] for a in added]
        if rule == "pair":
            used = np.unique(np.concatenate([p.ravel() for p in original_planes]))
            twin = pair_mud(palette, mud, slots, used)
        else:
            twin[slots] = MUD_RULES[rule](palette)[slots]
        new = write_texture(new, chunk, textures[1], new_planes, twin)
    fixed_span, fit = rebuild_fixed_span_filled(span, new, encoder="auto")
    require(len(fixed_span) == len(span) and fixed_span[:32] == span[:32], "wrapper or allocation changed")
    check, _ = decode_chunk(fixed_span, parse_chunks(fixed_span)[0])
    require(check == new, "native round trip differs")
    return fixed_span, dict(texture=clean["name"], mips=rows, palette_slots_added=added, mud_rule=rule,
                            merged_twin_slots=merged_slots, protected_texels_moved_one_level=merged_moved,
                            fit=asdict(fit), level0_scope_texels=int(scope.sum()))


def _txtr(span, kinds=("P8",)):
    chunks = parse_chunks(span)
    require(len(chunks) == 1 and chunks[0].end_offset == len(span), "expected one complete chunk span")
    chunk = chunks[0]
    require(chunk.kind == "TXTR" and chunk.compressed, "expected a compressed TXTR chunk")
    decoded, _ = decode_chunk(span, chunk)
    texture = parse_texture(decoded, chunk)
    require(texture.format_name in kinds, "unsupported texture format " + texture.format_name)
    return chunk, decoded, texture


def _rebuild(span, new):
    fixed_span, fit = rebuild_fixed_span_filled(span, new, encoder="auto")
    require(len(fixed_span) == len(span) and fixed_span[:32] == span[:32], "wrapper or allocation changed")
    check, _ = decode_chunk(fixed_span, parse_chunks(fixed_span)[0])
    require(check == new, "native round trip differs")
    return fixed_span, fit


def compile_palette(span, row):
    """Recolour palette entries only (the linear name plate, digit textures): every entry within ``tolerance`` of a
    ``from`` colour takes the new RGB and keeps its alpha. Indices, size, mips and wrapper stay the same."""
    chunk, decoded, texture = _txtr(span, ("P8", "VC_P8_LINEAR"))
    require(texture.name == row["texture"], "texture name differs: " + texture.name)
    at = chunk.system_bytes + texture.palette_offset
    palette = np.frombuffer(decoded[at:at + 1024], np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]].astype(np.int64)
    new_palette = palette.copy()
    changed = []
    for mapping in row["map"]:
        hit = np.zeros(256, bool)
        for source in mapping["from"]:
            hit |= np.abs(palette[:, :3] - np.array(hex_rgb(source), np.int64)).max(axis=1) <= int(
                mapping.get("tolerance", 24))
        if not mapping.get("transparent", False):
            hit &= palette[:, 3] > 0
        if "alpha_min" in mapping:
            hit &= palette[:, 3] >= int(mapping["alpha_min"])
        if "scale" in mapping:
            # sea1 (b773): darken the hit entries by num/den (rounded), keeping hue and alpha. The shoulder (TV)
            # digits are lit about 1.5 to 2 times brighter in game than the jersey and its chest numbers, so a
            # shoulder digit in the chest digit's own colour reads much lighter (wolf grey showed as white).
            num, den = (int(v) for v in mapping["scale"])
            require(0 < num < den, "a palette scale must darken")
            new_palette[hit, :3] = (palette[hit, :3] * num + den // 2) // den
        else:
            new_palette[hit, :3] = np.array(hex_rgb(mapping["to"]), np.int64)
        changed += [int(i) for i in np.flatnonzero(hit)]
    require(changed and not np.array_equal(new_palette, palette), "the palette recolour changed nothing")
    new = bytearray(decoded)
    new[at:at + 1024] = np.ascontiguousarray(new_palette[:, [2, 1, 0, 3]], np.uint8).tobytes()
    new = bytes(new)
    fixed_span, fit = _rebuild(span, new)
    return fixed_span, dict(texture=texture.name, palette_entries=sorted(set(changed)), fit=asdict(fit))


def compile_clear(span, row):
    """Clear a shoulder (TV) digit: every texel of every stored mip takes the texture's own transparent index, so
    the kit shows no TV number (the 2026 alternates that have none)."""
    chunk, decoded, texture = _txtr(span)
    require(texture.name == row["texture"], "texture name differs: " + texture.name)
    require((texture.width, texture.height, texture.mip_levels) == tuple(row["size"]), "digit size differs")
    t = dict(pixel=texture.pixel_offset, palette=texture.palette_offset, width=texture.width,
             height=texture.height, mips=texture.mip_levels)
    planes = read_planes(decoded, chunk, t)
    palette = read_palette(decoded, chunk, t)
    clear = np.flatnonzero(palette[:, 3] == 0)
    require(len(clear) > 0, "the digit palette has no transparent entry")
    counts = np.bincount(planes[0].ravel(), minlength=256)
    index = int(clear[np.argmax(counts[clear])])
    new = write_texture(decoded, chunk, t, [np.full_like(p, index) for p in planes])
    require(new != decoded, "the digit is already clear")
    fixed_span, fit = _rebuild(span, new)
    return fixed_span, dict(texture=texture.name, transparent_index=index, fit=asdict(fit))


UNIF_FIELDS = {"facemask": 0x30}
# uf3 (b773): the arm-number route at 0x38 (native accessor 0x8E840, route table 0x4EF810): with no neck roll 1/2/3/4
# put the arm digits on shoulder_B/shoulder_A/sleeve_B/sleeve_A. A slot that borrows another kit's jersey must take
# that kit's route too, or its digits land on the borrowed sleeve stripes (ur1, the Unc Bowl Steelers).
UNIF_INTS = {"number_route": (0x38, (1, 2, 3, 4))}


def compile_unif(span, row):
    """Set Unif colour fields (BGRA as stored), e.g. the facemask colour at 0x30, and small integer fields (the
    arm-number route at 0x38). The raw 0x20-byte wrapper and every other byte stay the same."""
    chunks = parse_chunks(span)
    require(len(chunks) == 1 and chunks[0].end_offset == len(span), "expected one complete chunk span")
    chunk = chunks[0]
    require(chunk.kind == "Unif" and not chunk.compressed and chunk.stored_size == 80, "expected the raw Unif chunk")
    new = bytearray(span)
    for name, value in sorted(row.get("fields", {}).items()):
        at = chunk.body_offset + UNIF_FIELDS[name]
        rgb = hex_rgb(value)
        new[at:at + 4] = bytes((rgb[2], rgb[1], rgb[0], 0xFF))
    for name, value in sorted(row.get("ints", {}).items()):
        at, allowed = UNIF_INTS[name]
        require(int(value) in allowed, "unsupported " + name)
        at += chunk.body_offset
        require(struct.unpack_from("<I", span, at)[0] in allowed, "unexpected stored " + name)
        struct.pack_into("<I", new, at, int(value))
    require(bytes(new) != span, "the Unif fields already hold these values")
    return bytes(new), dict(fields=row.get("fields", {}), ints=row.get("ints", {}))


NAME_METRICS = slice(0x2C, 0xA0)        # 29 little-endian (atlas offset, glyph width) pairs in the NAME body


def compile_name(span, donor_span, row):
    """Give a nameplate the glyph metrics of the kit whose name atlas it carries (uf3, b773). The native compositor
    (0x1C2140) copies each letter at its stored width, so a slot that borrowed a wider atlas but kept its own narrow
    widths cuts every letter (the Unc Bowl Steelers: GAINWELL read CAINVELL). Only the metric pairs change; the
    donor must be the same raw NAME layout and identical outside them."""
    pieces = []
    for blob in (span, donor_span):
        chunks = parse_chunks(blob)
        require(len(chunks) == 1 and chunks[0].end_offset == len(blob), "expected one complete NAME span")
        chunk = chunks[0]
        require(chunk.kind == "NAME" and not chunk.compressed and chunk.stored_size == 160,
                "expected the raw 160-byte NAME chunk")
        pieces.append((chunk, blob))
    (chunk, _), (donor, _) = pieces
    body, donor_body = span[chunk.body_offset:], donor_span[donor.body_offset:]
    require(len(body) == len(donor_body) == 160, "NAME body size differs")
    require(body[:NAME_METRICS.start] == donor_body[:NAME_METRICS.start] and
            body[NAME_METRICS.stop:] == donor_body[NAME_METRICS.stop:], "the donor NAME differs outside its metrics")
    require(body[NAME_METRICS] != donor_body[NAME_METRICS], "the nameplate already has the donor's metrics")
    new = bytearray(span)
    new[chunk.body_offset + NAME_METRICS.start:chunk.body_offset + NAME_METRICS.stop] = donor_body[NAME_METRICS]
    old = struct.unpack_from("<58H", body, NAME_METRICS.start)
    now = struct.unpack_from("<58H", donor_body, NAME_METRICS.start)
    require(old[0::2] == now[0::2], "the donor's glyph atlas offsets differ")
    return bytes(new), dict(donor_selector=row["donor_selector"],
                            widths_changed=sum(a != b for a, b in zip(old[1::2], now[1::2])))


def texture_rgba(span):
    """Level-0 RGBA of the first texture in a P8 chunk span (stamp donors)."""
    chunks = parse_chunks(span)
    kind = "tset" if chunks[0].kind == "TSET" else "txtr"
    chunk, decoded, textures = native_textures(span, kind) if kind == "txtr" else _tset_first(span)
    planes = read_planes(decoded, chunk, textures[0])
    return read_palette(decoded, chunk, textures[0])[planes[0]].astype(np.uint8)


def _tset_first(span):
    chunks = parse_chunks(span)
    require(len(chunks) == 1 and chunks[0].end_offset == len(span), "expected one complete chunk span")
    chunk = chunks[0]
    decoded, _ = decode_chunk(span, chunk)
    return chunk, decoded, _tset_textures(decoded)


def copy_video(span, donor_span, row):
    """Give one digit texture another digit texture's palette and complete mip chain, keeping its own descriptor,
    name, wrapper and allocation (the shoulder digit matches the chest digit exactly)."""
    sources = []
    for blob, name in ((donor_span, row["donor_texture"]), (span, row["texture"])):
        chunks = parse_chunks(blob)
        require(len(chunks) == 1 and chunks[0].end_offset == len(blob), "expected one complete digit span")
        chunk = chunks[0]
        decoded, _ = decode_chunk(blob, chunk)
        texture = parse_texture(decoded, chunk)
        require(chunk.kind == "TXTR" and chunk.compressed and texture.name == name, "wrong digit texture " + name)
        require((texture.width, texture.height, texture.mip_levels, texture.format_name) == tuple(row["size"]) + ("P8",),
                "unsupported digit storage")
        sources.append((chunk, decoded, texture))
    (dc, dd, dt), (tc, td, tt) = sources
    require((dc.system_bytes, dc.video_bytes, dt.pixel_offset, dt.palette_offset) ==
            (tc.system_bytes, tc.video_bytes, tt.pixel_offset, tt.palette_offset), "donor and target layouts differ")
    edited = td[:tc.system_bytes] + dd[dc.system_bytes:]
    require(edited != td, "the digit already matches its donor")
    fixed_span, fit = rebuild_fixed_span_filled(span, edited, encoder="auto")
    require(len(fixed_span) == len(span) and fixed_span[:32] == span[:32], "wrapper or allocation changed")
    check, _ = decode_chunk(fixed_span, parse_chunks(fixed_span)[0])
    require(check == edited, "donor mip-chain round trip differs")
    return fixed_span, dict(texture=row["texture"], donor=row["donor_texture"], fit=asdict(fit),
                            donor_video_sha256=sha(dd[dc.system_bytes:]))


# -- kit packages ----------------------------------------------------------------------------------------------------

def _chunk_for(raw, index):
    for chunk in parse_chunks(raw):
        if chunk.index == index:
            return chunk
    raise ValueError("2026 kit fixes: chunk %d absent" % index)


def compile_resource(selector, raw, *, strict=True, document=None, kits=None):
    """Compile every pinned texture of one kit package; refuses partial or unknown inputs when strict. ``kits`` maps
    a donor kit selector to its package bytes (the uf3 ``name`` rows)."""
    document = document or spec()
    rows = [r for r in document["textures"] if r["selector"] == selector]
    require(rows, "no entries for " + selector)
    states = []
    for row in rows:
        chunk = _chunk_for(raw, row["chunk"])
        span = raw[chunk.offset:chunk.end_offset]
        layout_ok = (len(raw), chunk.offset, len(span)) == (row["resource_size"], row["offset"], row["length"])
        digest = sha(span) if layout_ok else None
        # ``after_equivalent_sha256``: the same finished texture stored by an earlier codec (an already repaired disc).
        states.append((row, chunk, span, "before" if digest == row["before_sha256"]
                       else "after" if digest == row["after_sha256"] or digest in row.get("after_equivalent_sha256", ())
                       else "other"))
    kinds = {s[3] for s in states}
    if kinds == {"after"}:
        return [], dict(selector=selector, state="applied", changed_bytes=0, parts=[], skipped_textures=[])
    if strict:
        # The native repair accepts only the pinned unrepaired kit: anything else is corruption or a partial repair.
        require(kinds == {"before"}, selector + ": unknown or partially repaired input hashes")
    elif kinds == {"other"}:
        return [], dict(selector=selector, state="other_uniform", changed_bytes=0, parts=[],
                        skipped_textures=[r["chunk"] for r, *_ in states])
    # Studio builds: each pinned texture is independent. A texture the user's own recipe replaced (unknown hash)
    # keeps the user's art; the known SOFTDRINK ones are finished.
    replacements, parts, skipped = [], [], []
    for row, chunk, span, state in states:
        if state != "before":
            if state == "other":
                skipped.append(row["chunk"])
            continue
        if row["kind"] == "copy_video":
            donor = _chunk_for(raw, row["donor_chunk"])
            donor_span = raw[donor.offset:donor.end_offset]
            if sha(donor_span) != row["donor_sha256"]:
                require(not strict, selector + ": donor digit differs from its pin")
                skipped.append(row["chunk"])
                continue
            new, detail = copy_video(span, donor_span, row)
        elif row["kind"] == "palette":
            new, detail = compile_palette(span, row)
        elif row["kind"] == "clear":
            new, detail = compile_clear(span, row)
        elif row["kind"] == "unif":
            new, detail = compile_unif(span, row)
        elif row["kind"] == "name":
            donor_raw = (kits or {}).get(row["donor_selector"])
            require(donor_raw is not None, selector + ": nameplate donor kit absent")
            donor = _chunk_for(donor_raw, row["chunk"])
            donor_span = donor_raw[donor.offset:donor.end_offset]
            if sha(donor_span) != row["donor_sha256"]:
                # a donor nameplate the user's recipe replaced: keep this kit as it is (strict refuses)
                require(not strict, selector + ": nameplate donor differs from its pin")
                skipped.append(row["chunk"])
                continue
            new, detail = compile_name(span, donor_span, row)
        else:
            donors, missing = {}, False
            for index, pin in sorted((row.get("donors") or {}).items()):
                if ":" in str(index):
                    # uf3: a texture of another kit package ("SELECTOR:chunk"), read from the same image
                    other, at = str(index).split(":")
                    source_raw = (kits or {}).get(other)
                    require(source_raw is not None, selector + ": stamp donor kit absent")
                    key = str(index)
                else:
                    source_raw, at, key = raw, index, int(index)
                donor = _chunk_for(source_raw, int(at))
                donor_span = source_raw[donor.offset:donor.end_offset]
                if sha(donor_span) != pin:
                    # a stamp source the user's recipe replaced: keep the user's art (strict refuses)
                    require(not strict, selector + ": stamp donor differs from its pin")
                    missing = True
                    break
                donors[key] = texture_rgba(donor_span)
            if missing:
                skipped.append(row["chunk"])
                continue
            new, detail = compile_texture(span, row, donors)
        require(sha(new) == row["after_sha256"], selector + ": Studio compile differs from its output pin")
        replacements.append((chunk.offset, new))
        parts.append(dict(selector=selector, chunk_index=chunk.index, offset=chunk.offset, length=len(new),
                          before_sha256=sha(span), after_sha256=sha(new),
                          changed_bytes=sum(a != b for a, b in zip(span, new)), defects=row.get("defects", []),
                          **detail))
    return replacements, dict(selector=selector, state="applied", skipped_textures=skipped,
                              changed_bytes=sum(p["changed_bytes"] for p in parts), parts=parts)


def donor_kits(document):
    """Kit packages read as donors (uf3): nameplate rows' ``donor_selector`` and cross-kit stamp sources."""
    out = {r["donor_selector"] for r in document["textures"] if r.get("donor_selector")}
    out |= {str(k).split(":")[0] for r in document["textures"] for k in (r.get("donors") or {}) if ":" in str(k)}
    return sorted(out)


def selectors(document=None):
    document = document or spec()
    return sorted({r["selector"] for r in document["textures"]})


def apply_to_image(path, *, strict=False, document=None):
    """Studio uniform finish pass: only the pinned kit chunk spans are written."""
    document = document or spec()
    try:
        with bump._Image.open(Path(path), writable=False) as source:
            index = bump._parsed_index(source)
            names = {bump.logical_name_for(e.name_id) for e in index.entries}
    except (ValueError, OSError):
        if strict:
            raise
        return dict(state="other_image", written_spans=0, written_bytes=0, changed_bytes=0, kits=[])
    wanted = selectors(document)
    if not strict and not all(s + ".IFF" in names for s in wanted):
        return dict(state="other_uniform", written_spans=0, written_bytes=0, changed_bytes=0, kits=[])
    kits, written, written_bytes = [], 0, 0
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        # Preflight every kit before the first write, so a refusal leaves the image untouched.
        donors = {}
        for selector in donor_kits(document):
            entries = by_name.get(selector + ".IFF", [])
            require(len(entries) == 1, selector + " donor kit package absent or duplicated")
            donors[selector] = image.read_segments(index.sub_extents(entries[0], 0, entries[0].size))
        plans = []
        for selector in wanted:
            entries = by_name.get(selector + ".IFF", [])
            require(len(entries) == 1, selector + " kit package absent or duplicated")
            entry = entries[0]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            replacements, receipt = compile_resource(selector, raw, strict=strict, document=document, kits=donors)
            plans.append((entry, replacements, receipt))
        states = {p[2]["state"] for p in plans}
        if states == {"other_uniform"}:
            return dict(state="other_uniform", written_spans=0, written_bytes=0, changed_bytes=0, kits=[])
        # A user's own kit recipe (pinned textures with unknown hashes) keeps its art; see compile_resource.
        for entry, replacements, receipt in plans:
            for offset, data in replacements:
                segments = index.sub_extents(entry, offset, len(data))
                image.write_segments(segments, data)
                require(image.read_segments(segments) == data, "written span read-back differs")
                written += 1
                written_bytes += len(data)
            kits.append(receipt)
    skipped = [k["selector"] for k in kits if k["state"] == "other_uniform"]
    return dict(state="applied", written_spans=written, written_bytes=written_bytes,
                changed_bytes=sum(k["changed_bytes"] for k in kits), skipped_kits=skipped, kits=kits)


def alternates():
    """The uf2 document: 2026 alternate, throwback and Rivalries kit fixes."""
    return spec(DATA_ALTS)


def apply_alternates(path, *, strict=False):
    """Studio uniform finish pass for the alternates (after ``apply_to_image``): pinned spans only."""
    return apply_to_image(path, strict=strict, document=alternates())


def finish():
    """The uf3 document: elements judged against the 2026 game highlights, kept, reverted to v0.6 or redrawn."""
    return spec(DATA_UF3)


def apply_finish(path, *, strict=False):
    """Studio uniform finish pass for uf3 (after ``apply_alternates``): pinned spans only."""
    return apply_to_image(path, strict=strict, document=finish())


def seattle():
    """The sea1 document: the Seattle helmet (crown-front logo fragment, helmet-back lines) and shoulder digits."""
    return spec(DATA_SEA1)


def apply_seattle(path, *, strict=False):
    """Studio uniform finish pass for sea1 (after ``apply_finish``): pinned spans only."""
    return apply_to_image(path, strict=strict, document=seattle())


def overlaps():
    """ov1: mechanical decal cleanup, pinned after uf3."""
    return spec(DATA_OV1)


def apply_overlaps(path, *, strict=False):
    return apply_to_image(path, strict=strict, document=overlaps())
