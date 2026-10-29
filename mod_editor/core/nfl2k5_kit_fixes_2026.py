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

Job ku1 (b776) redid the 2026 Chiefs kits in ``data/nfl2k5_kit_fixes_2026_ku1.json`` (``apply_chiefs``, after the
pants hem). It adds ``palette_remap`` rows: the whole colour scheme moves in the palette (every shade and blend kept,
indices unchanged) before the row's art operations paint the new bands and patch.

Job sw1 (b777, Noah 10/20: "the Nike swoosh needs to be centered on the sleeve, not blocking or getting blocked by
anything") moves the sleeve swoosh in ``data/nfl2k5_kit_fixes_2026_sw1.json`` (``apply_swooshes``, the last kit
writer). One rule for every 2026 kit: on kits whose arm number sits on the sleeve, the swoosh is centred over the
number just above it; on the others it stays at the shared place below the shoulder number; either way on one plain
field, clear of the number, stripes, logos and holes. Its ``warp`` operation carries an existing swoosh (the
Packers home sleeve's pixels on the user's disc, never a drawing of the mark) through a mesh measured on the player
model onto the model's surface, across the shoulder cap of the torso texture where it must.

Job uf1 (b778, SWeaR 10/21: "Last names are glitched on Dallas Alternate 1 uni") gives a nameplate the glyph metrics
of the letter atlas it actually carries, atlas offsets included (``data/nfl2k5_kit_fixes_2026_names.json``,
``apply_nameplates``). The Arctic Cowboy slots (07H7/07A7) wear the 2026 road kit's letters (07A0, apostrophe and
hyphen 32 texels apart, A at 96) over the retail 1994 metrics (wide hyphen, A at 128), so every letter of a name
was copied from its neighbour's cell. A ``relayout`` name row is applied only when the kit's own atlas, measured
column by column, has exactly the donor's glyph layout and not its own (``nameplate_layout``).
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

from . import nfl2k5_bump_texture_writer as bump
from nfl_txtr import decode_chunk, parse_chunks, parse_texture, swizzle_2d, texture_to_rgba, unswizzle_2d
from nfl_vc_lz_fill import rebuild_fixed_span_filled

SCHEMA = "nfl2k5_kit_fixes_2026/v1"
DATA = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026.json"
DATA_ALTS = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_alts.json"
DATA_UF3 = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_uf3.json"
DATA_SEA1 = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_sea1.json"
DATA_OV1 = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_ov1.json"
DATA_KU1 = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_ku1.json"
DATA_SW1 = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_sw1.json"
DATA_NAMES = Path(__file__).resolve().parents[2] / "data/nfl2k5_kit_fixes_2026_names.json"
DATA_SIDELINE = Path(__file__).resolve().parents[2] / "data/nfl2k5_sideline_2026.json"
KINDS = ("tset", "txtr", "copy_video", "palette", "clear", "unif", "name")
SIDELINE_SCHEMA = "nfl2k5_sideline_2026/v1"
SIDELINE_PARTS = ("pants", "sleeve", "helmet", "torso")
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


def _cross(ax, ay, bx, by):
    return ax * by - ay * bx


def _alpha_line_weight(source, op):
    """Per-texel weight 0..256 of a mark drawn on a plain field (``alpha_line``: field and mark colours), as stamp's
    ``alpha_line``; texels below alpha 128 weigh nothing."""
    f = np.array(hex_rgb(op["alpha_line"]["field"]), np.int64)
    m = np.array(hex_rgb(op["alpha_line"]["mark"]), np.int64)
    d = m - f
    den = int((d * d).sum())
    require(den > 0, "warp field and mark colours are the same")
    num = ((source[..., :3].astype(np.int64) - f) * d).sum(axis=2)
    return np.clip((num * 256 + den // 2) // den, 0, 256) * (source[..., 3] >= 128)


def warp(rgba, op, source):
    """sw1 (b777): place an existing mark through a mesh, so it follows the model's surface across a curved, rotated
    UV layout (the sleeve swoosh moved onto the shoulder cap of the torso texture).

    ``grid`` maps decal coordinates to the SOURCE texture: ``s`` and ``t`` (1/1000 of the decal box, ascending,
    evenly spaced) and ``x``/``y`` (rows per t, columns per s; fixed-point UNIT per texel) are where each decal point
    sits on the source. ``nodes`` give the decal axes ``a`` (across the mark) and ``b`` (up it), 1/1000, and per
    node (row-major, ``b`` rows of ``a`` columns) its DESTINATION point ``dst`` (UNIT); ``use`` (a string of 0/1,
    one per node) drops nodes off this UV island: each grid quad is two triangles, drawn when all three nodes are
    used. ``mask`` ([y, x0, x1) rows) lists the only destination texels that may change. Each of the 4x4 samples per
    texel takes the source texel under it (``sample`` "bilinear": between texel centres) as an ``alpha_line`` weight
    (0..256), optionally sharpened (``gain`` [num, den] about the half weight), and ``color`` is laid down with it,
    all in exact integer arithmetic."""
    h, w = rgba.shape[:2]
    sh, sw = source.shape[:2]
    g = op["grid"]
    gs = np.asarray(g["s"], np.int64)
    gt = np.asarray(g["t"], np.int64)
    gx = np.asarray(g["x"], np.int64)
    gy = np.asarray(g["y"], np.int64)
    require(len(gs) >= 2 and len(gt) >= 2 and gx.shape == (len(gt), len(gs)) == gy.shape, "warp grid shape")
    ds, dt = int(gs[1] - gs[0]), int(gt[1] - gt[0])
    require(ds > 0 and dt > 0 and (np.diff(gs) == ds).all() and (np.diff(gt) == dt).all(), "warp grid spacing")
    n = op["nodes"]
    na = np.asarray(n["a"], np.int64)
    nb = np.asarray(n["b"], np.int64)
    cols, rows_n = len(na), len(nb)
    require(cols >= 2 and rows_n >= 2, "warp node axes")
    dst = np.asarray(n["dst"], np.int64).reshape(rows_n, cols, 2)
    ab = np.stack(np.broadcast_arrays(na[None, :], nb[:, None]), axis=-1)
    use = np.asarray([int(c) for c in n["use"]], np.int64).reshape(rows_n, cols).astype(bool)
    allow = np.zeros((h, w), bool)
    for y, x0, x1 in op["mask"]:
        require(0 <= y < h and 0 <= x0 < x1 <= w, "warp mask outside the texture")
        allow[int(y), int(x0):int(x1)] = True
    weight = _alpha_line_weight(source, op)
    step = UNIT // SUPER
    sub = np.arange(SUPER, dtype=np.int64) * step + step // 2
    acc = np.zeros((h, w), np.int64)
    taken = np.zeros((h * SUPER, w * SUPER), bool)
    tris = []
    for r in range(rows_n - 1):
        for c in range(cols - 1):
            q = [(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)]
            for tri in ((q[0], q[1], q[2]), (q[0], q[2], q[3])):
                if all(use[i, j] for i, j in tri):
                    tris.append(tri)
    for tri in tris:
        P = [dst[i, j] for i, j in tri]
        A = [ab[i, j] for i, j in tri]
        den = _cross(P[1][0] - P[0][0], P[1][1] - P[0][1], P[2][0] - P[0][0], P[2][1] - P[0][1])
        if den == 0:
            continue
        if den < 0:
            P = [P[0], P[2], P[1]]
            A = [A[0], A[2], A[1]]
            den = -den
        xs = [p[0] for p in P]
        ys = [p[1] for p in P]
        x0 = max(int(min(xs)) // UNIT, 0)
        x1 = min(-(-int(max(xs)) // UNIT), w)
        y0 = max(int(min(ys)) // UNIT, 0)
        y1 = min(-(-int(max(ys)) // UNIT), h)
        if x1 <= x0 or y1 <= y0:
            continue
        px = (np.arange(x0, x1, dtype=np.int64)[:, None] * UNIT + sub[None, :]).ravel()
        py = (np.arange(y0, y1, dtype=np.int64)[:, None] * UNIT + sub[None, :]).ravel()
        X, Y = np.meshgrid(px, py)
        e0 = _cross(P[2][0] - P[1][0], P[2][1] - P[1][1], X - P[1][0], Y - P[1][1])
        e1 = _cross(P[0][0] - P[2][0], P[0][1] - P[2][1], X - P[2][0], Y - P[2][1])
        e2 = den - e0 - e1
        sx0, sy0 = x0 * SUPER, y0 * SUPER
        inside = (e0 >= 0) & (e1 >= 0) & (e2 >= 0) & ~taken[sy0:sy0 + X.shape[0], sx0:sx0 + X.shape[1]]
        inside &= np.repeat(np.repeat(allow[y0:y1, x0:x1], SUPER, axis=0), SUPER, axis=1)
        if not inside.any():
            continue
        taken[sy0:sy0 + X.shape[0], sx0:sx0 + X.shape[1]] |= inside
        a = (e0 * A[0][0] + e1 * A[1][0] + e2 * A[2][0]) // den
        b = (e0 * A[0][1] + e1 * A[1][1] + e2 * A[2][1]) // den
        # decal -> source through the grid (bilinear, clamped to the grid's span)
        a = np.clip(a, gs[0], gs[-1])
        b = np.clip(b, gt[0], gt[-1])
        i = np.minimum((a - gs[0]) // ds, len(gs) - 2)
        j = np.minimum((b - gt[0]) // dt, len(gt) - 2)
        fa = a - gs[0] - i * ds
        fb = b - gt[0] - j * dt
        wa, wb = ds - fa, dt - fb
        sx = (gx[j, i] * wa * wb + gx[j, i + 1] * fa * wb + gx[j + 1, i] * wa * fb + gx[j + 1, i + 1] * fa * fb) // (ds * dt)
        sy = (gy[j, i] * wa * wb + gy[j, i + 1] * fa * wb + gy[j + 1, i] * wa * fb + gy[j + 1, i + 1] * fa * fb) // (ds * dt)
        if op.get("sample") == "bilinear":
            # bilinear source weight between texel centres
            ux, uy = sx - UNIT // 2, sy - UNIT // 2
            kx, ky = ux // UNIT, uy // UNIT
            fx, fy = ux - kx * UNIT, uy - ky * UNIT

            def at(xx, yy):
                ok = (xx >= 0) & (xx < sw) & (yy >= 0) & (yy < sh)
                return np.where(ok, weight[np.clip(yy, 0, sh - 1), np.clip(xx, 0, sw - 1)], 0)

            wgt = (at(kx, ky) * (UNIT - fx) * (UNIT - fy) + at(kx + 1, ky) * fx * (UNIT - fy) +
                   at(kx, ky + 1) * (UNIT - fx) * fy + at(kx + 1, ky + 1) * fx * fy) // (UNIT * UNIT)
        else:
            # the source texel under each sample (as stamp does): the 4x4 samples per texel do the filtering
            kx, ky = sx // UNIT, sy // UNIT
            ok = (kx >= 0) & (kx < sw) & (ky >= 0) & (ky < sh)
            wgt = np.where(ok, weight[np.clip(ky, 0, sh - 1), np.clip(kx, 0, sw - 1)], 0)
        if op.get("gain"):
            # sharpen the resampled anti-aliasing: weight' = 128 + (weight - 128) * num // den, clamped (exact)
            num, den = (int(v) for v in op["gain"])
            wgt = np.clip(128 + ((wgt - 128) * num) // den, 0, 256)
        wgt = np.where(inside, wgt, 0)
        acc[y0:y1, x0:x1] += wgt.reshape(y1 - y0, SUPER, x1 - x0, SUPER).sum(axis=(1, 3))
    full = SUPER * SUPER * 256
    colour = np.array(hex_rgb(op["color"]), np.int64)
    out = rgba.copy()
    hit = acc > 0
    base = rgba[..., :3].astype(np.int64)
    blended = (base * (full - acc)[..., None] + colour[None, None, :] * acc[..., None] + full // 2) // full
    out[..., :3][hit] = blended[hit].astype(np.uint8)
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
        elif kind == "warp":
            donor = op.get("donor", "self")
            key = donor if isinstance(donor, str) and ":" in donor else None if donor == "self" else int(donor)
            source = rgba if donor == "self" else (donors or {}).get(key)
            require(source is not None, "warp donor texture absent")
            out, _ = warp(out, op, source)
        else:
            raise ValueError("2026 kit fixes: unknown art operation " + repr(kind))
    scope = np.any(out != rgba, axis=2)
    return out, scope


def art_colours(ops):
    return sorted({hex_rgb(op["color"]) for op in ops})


def remap_colours(rgb, pairs, tolerance):
    """ku1 (b776): move a whole colour scheme, keeping every blend and shade. ``pairs`` lists (old, new) colours; a
    colour on the segment between two old colours (within ``tolerance`` RGB levels, nearest segment first, ties to the
    first pair) takes the same point between their new colours, in exact integers. A shade of a cloth colour is a
    blend with black, a highlight one with white, an anti-aliased edge one between its two art colours, so listing
    black, white and the old art colours carries all of them. ``rgb`` is (N, 3); returns (new rgb, hit mask)."""
    old = np.array([hex_rgb(a) for a, _ in pairs], np.int64)
    new = np.array([hex_rgb(b) for _, b in pairs], np.int64)
    require(len(old) >= 2, "a remap needs at least two colours")
    c = np.asarray(rgb, np.int64)
    best = np.full(len(c), np.iinfo(np.int64).max, np.int64)
    out = c.copy()
    for i in range(len(old)):
        for j in range(i + 1, len(old)):
            d = old[j] - old[i]
            den = int((d * d).sum())
            require(den > 0, "remap colours must differ")
            num = np.clip(((c - old[i]) * d).sum(axis=1), 0, den)
            off = c * den - old[i][None, :] * den - d[None, :] * num[:, None]
            dist = (off * off).sum(axis=1) // (den * den)
            take = dist < best
            best = np.where(take, dist, best)
            moved = (new[i][None, :] * (den - num)[:, None] + new[j][None, :] * num[:, None] + den // 2) // den
            out = np.where(take[:, None], moved, out)
    hit = best <= int(tolerance) ** 2
    return np.where(hit[:, None], np.clip(out, 0, 255), c), hit


def remap_palette(palette, row):
    """``palette_remap`` of a row: the palette entries ``remap_colours`` moves (clear entries stay). Returns the new
    palette and the moved entry indices."""
    spec = row["palette_remap"]
    out = palette.copy()
    moved, hit = remap_colours(palette[:, :3], spec["pairs"], spec.get("tolerance", 12))
    hit &= palette[:, 3] > 0
    hit &= (moved != palette[:, :3]).any(axis=1)
    out[hit, :3] = moved[hit]
    return out, [int(i) for i in np.flatnonzero(hit)]


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


def compile_texture(span, row, donors=None, *, fixed=True):
    """Paint ``row``'s art into one native chunk span; returns (new span, receipt). ``donors`` maps a chunk index
    of the same kit to its level-0 RGBA (stamp sources)."""
    chunk, decoded, textures = native_textures(span, row["kind"])
    clean = textures[0]
    require(clean["name"] == row["texture"], "texture name differs: " + clean["name"])
    require((clean["width"], clean["height"], clean["mips"]) == tuple(row["size"]), "texture size differs")
    planes = read_planes(decoded, chunk, clean)
    original_planes = [p.copy() for p in planes]
    palette = read_palette(decoded, chunk, clean)
    rule = mud = None
    if row["kind"] == "tset":
        mud = read_palette(decoded, chunk, textures[1])
        rule = mud_rule(palette, mud, np.unique(np.concatenate([p.ravel() for p in planes])))
    remapped = []
    if "palette_remap" in row:
        # ku1 (b776): the whole scheme moves in the palette first (indices kept, so every protected texel takes its
        # entry's new colour); the art operations then paint on the remapped texture
        palette, remapped = remap_palette(palette, row)
        require(remapped, "the palette remap moved no entry")
    original_palette = palette.copy()
    h, w = planes[0].shape
    base = palette[planes[0]].astype(np.uint8)
    painted, scope = paint(base, row.get("ops", []), donors)
    require(scope.any() or remapped, "the art changed no texel")
    alphas = painted[..., 3].astype(np.int64)
    alpha_changed = painted[..., 3] != base[..., 3]
    # exact art colours first, then the most frequent edge blends far from the palette, per alpha class in the art
    wanted = art_colours([op for op in row.get("ops", []) if "color" in op])
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
        slots += [i for i in remapped if i not in slots]
        if rule == "pair":
            used = np.unique(np.concatenate([p.ravel() for p in original_planes]))
            twin = pair_mud(palette, mud, slots, used)
        else:
            twin[slots] = MUD_RULES[rule](palette)[slots]
        new = write_texture(new, chunk, textures[1], new_planes, twin)
    if not fixed:
        # b775-ct1: a NEW kit package (nfl2k5_moment_kits) has no fixed allocation to keep: the chunk is re-encoded at
        # its own size with the same decoded allocation (as the era-kit encoder does)
        from . import nfl2k5_era_kits as era
        fresh = era._encoded_span(span, new, chunk.video_bytes)
        return fresh, dict(texture=clean["name"], mips=rows, palette_slots_added=added, mud_rule=rule,
                           merged_twin_slots=merged_slots, protected_texels_moved_one_level=merged_moved,
                           fit=None, level0_scope_texels=int(scope.sum()))
    fixed_span, fit = rebuild_fixed_span_filled(span, new, encoder="auto")
    require(len(fixed_span) == len(span) and fixed_span[:32] == span[:32], "wrapper or allocation changed")
    check, _ = decode_chunk(fixed_span, parse_chunks(fixed_span)[0])
    require(check == new, "native round trip differs")
    detail = dict(texture=clean["name"], mips=rows, palette_slots_added=added, mud_rule=rule,
                  merged_twin_slots=merged_slots, protected_texels_moved_one_level=merged_moved,
                  fit=asdict(fit), level0_scope_texels=int(scope.sum()))
    if remapped:
        detail["palette_remapped"] = len(remapped)
    return fixed_span, detail


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


NAME_ATLAS_CHUNK = 43                   # the 1024x32 linear P8 letter strip the NAME metrics index
NAME_ATLAS_ALPHA = 64                   # a texel at or above this alpha is letter (fill, outline or anti-aliasing)


def name_metrics(name_span):
    """The 29 (atlas offset, glyph width) pairs (' - A..Z c) of one raw NAME chunk span."""
    chunks = parse_chunks(name_span)
    require(len(chunks) == 1 and chunks[0].kind == "NAME" and not chunks[0].compressed, "expected one raw NAME chunk")
    pairs = struct.unpack_from("<58H", name_span, chunks[0].body_offset + NAME_METRICS.start)
    return list(zip(pairs[0::2], pairs[1::2]))


def atlas_glyph_starts(atlas_span):
    """Where each glyph of a nameplate letter atlas starts, measured: the first column of every run of columns that
    hold a letter texel at the top mip. Every retail kit (634) has exactly one run per NAME pair, starting at its
    offset and exactly its width wide."""
    chunks = parse_chunks(atlas_span)
    require(len(chunks) == 1 and chunks[0].kind == "TXTR", "expected one nameplate atlas chunk")
    decoded, _ = decode_chunk(atlas_span, chunks[0])
    texture = parse_texture(decoded, chunks[0])
    require(texture.name == "names", "not a nameplate atlas: " + texture.name)
    alpha = np.frombuffer(texture_to_rgba(decoded, chunks[0], texture), np.uint8).reshape(
        texture.height, texture.width, 4)[..., 3]
    filled = (alpha >= NAME_ATLAS_ALPHA).any(axis=0)
    edges = np.flatnonzero(np.diff(np.concatenate(([0], filled.astype(np.int8)))) == 1)
    return [int(x) for x in edges]


def layout_fits(starts, metrics):
    """The atlas holds one glyph per NAME pair, each starting at its stored offset (one texel of slack)."""
    return len(starts) == len(metrics) and all(abs(s - x) <= 1 for s, (x, _) in zip(starts, metrics))


def nameplate_layout(raw):
    """(measured glyph starts, NAME pairs, fits) for one kit package: the uf1 (b778) audit of every kit."""
    atlas = _chunk_for(raw, NAME_ATLAS_CHUNK)
    names = [c for c in parse_chunks(raw) if c.kind == "NAME"]
    require(len(names) == 1, "expected one NAME chunk")
    starts = atlas_glyph_starts(raw[atlas.offset:atlas.end_offset])
    metrics = name_metrics(raw[names[0].offset:names[0].end_offset])
    return starts, metrics, layout_fits(starts, metrics)


def compile_name(span, donor_span, row, atlas_starts=None):
    """Give a nameplate the glyph metrics of the kit whose name atlas it carries (uf3, b773). The native compositor
    (0x1C2140) copies each letter at its stored width, so a slot that borrowed a wider atlas but kept its own narrow
    widths cuts every letter (the Unc Bowl Steelers: GAINWELL read CAINVELL). Only the metric pairs change; the
    donor must be the same raw NAME layout and identical outside them. A ``relayout`` row (uf1, b778) also takes the
    donor's atlas offsets, and only when ``atlas_starts`` (the kit's own atlas, measured) fit the donor's metrics
    and not the kit's own."""
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
    detail = dict(donor_selector=row["donor_selector"], widths_changed=sum(a != b for a, b in zip(old[1::2], now[1::2])))
    if row.get("relayout"):
        require(atlas_starts is not None, "a relayout nameplate needs its measured atlas")
        mine, theirs = list(zip(old[0::2], old[1::2])), list(zip(now[0::2], now[1::2]))
        require(not layout_fits(atlas_starts, mine), "the nameplate atlas already fits its own metrics")
        require(layout_fits(atlas_starts, theirs), "the nameplate atlas does not have the donor's glyph layout")
        detail["offsets_changed"] = sum(a != b for a, b in zip(old[0::2], now[0::2]))
    else:
        require(old[0::2] == now[0::2], "the donor's glyph atlas offsets differ")
    return bytes(new), detail


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
            starts = None
            if row.get("relayout"):
                atlas = _chunk_for(raw, NAME_ATLAS_CHUNK)
                starts = atlas_glyph_starts(raw[atlas.offset:atlas.end_offset])
                if not layout_fits(starts, name_metrics(donor_span)):
                    # the user's own letters (not the donor's layout): keep the kit as it is (strict refuses)
                    require(not strict, selector + ": nameplate atlas does not have the donor's glyph layout")
                    skipped.append(row["chunk"])
                    continue
            new, detail = compile_name(span, donor_span, row, starts)
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


def chiefs():
    """ku1 (b776): the 2026 Kansas City Chiefs home and road kits (13H0, 13A0) redone to the current look."""
    return spec(DATA_KU1)


def apply_chiefs(path, *, strict=False):
    """Studio uniform finish pass for ku1, after the pants hem (the last writer of these kits): pinned spans only."""
    return apply_to_image(path, strict=strict, document=chiefs())


def swooshes():
    """sw1 (b777): the sleeve swoosh centred on the sleeve, clear of numbers and art, on every 2026 kit."""
    return spec(DATA_SW1)


def apply_swooshes(path, *, strict=False):
    """Studio uniform finish pass for sw1, after ku1 (the last writer of the kit textures): pinned spans only."""
    return apply_to_image(path, strict=strict, document=swooshes())


def nameplates():
    """uf1 (b778): nameplate metrics that follow the letter atlas a kit carries (Dallas Arctic Cowboy, 07H7/07A7)."""
    return spec(DATA_NAMES)


def apply_nameplates(path, *, strict=False):
    """Studio uniform finish pass for uf1 (b778), after sw1 (every atlas writer has run): pinned NAME spans only."""
    return apply_to_image(path, strict=strict, document=nameplates())


# -------------------------------------------------------------------------------------------------- sideline atlas
# b779-vk1 (SWeaR 10/27): the bench and far players are drawn from the kit's chunk 51 ``splayer`` atlas (256x128),
# not from the field torso/pants/sleeve textures. A retail style slot reused for a 2026 alternate can carry the
# retail slot's own sideline atlas, whose pants (and, for some slots, sleeve or helmet) are another design's art.
# The field textures were repainted, the sideline atlas was not, so the same style wears the right kit on the field
# and the retail slot's pants/parts on the sideline. This pass repairs only the kits the v0.7 audit listed, and only
# the parts that do not match: the pants fabric takes the field pants colour, and a sleeve/helmet side that belongs
# to another design is taken from the team's 2026 primary atlas and recoloured to the field colour. Pinned selectors
# and parts; every other kit and every unlisted part is left alone.

SIDELINE_BOXES = {"pants": (0, 0, 128, 90), "pants_stripe": (46, 0, 66, 90), "pants_maker": (69, 13, 85, 23),
                  "sleeve": (190, 100, 256, 128), "helmet": (37, 90, 128, 128), "torso": (128, 0, 256, 100)}
SIDELINE_SLEEVE_FABRIC = (194, 103, 218, 117)     # plain sleeve fabric, clear of the logo, band and padding
SIDELINE_PANTS_STRIPES = ((130, 155), (357, 382))  # the pants texture's two stripe bands (native pixels)
SIDELINE_PANTS_SHIELD = (92, 40, 104, 51)
SIDELINE_PANTS_MAKER = (401, 41, 420, 48)
SIDELINE_LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def sideline():
    """The pinned 2026 alternate sideline-atlas list (b779-vk1)."""
    path = DATA_SIDELINE
    require(path.is_file(), "the sideline atlas list is missing")
    document = json.loads(path.read_text(encoding="utf-8"))
    require(document.get("schema") == SIDELINE_SCHEMA, "unexpected sideline atlas schema")
    return document


def _sideline_box(shape, box):
    mask = np.zeros(shape, bool)
    x0, y0, x1, y1 = box
    mask[y0:y1, x0:x1] = True
    return mask


def _sideline_smooth(a, lo=0.3, hi=0.7):
    t = np.clip((a - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _sideline_median(rgba, mask):
    px = rgba[..., :3][mask & (rgba[..., 3] > 128)]
    require(len(px), "the sideline region has no opaque texels")
    return np.median(px, axis=0).astype(np.int64)


def _sideline_fabric(rgba, part):
    """The field texture's fabric colour: pants without the stripe bands and marks, the rest the whole texture."""
    if part == "pants":
        mask = np.ones(rgba.shape[:2], bool)
        for x0, x1 in SIDELINE_PANTS_STRIPES:
            mask[:, x0:x1] = False
        for x0, y0, x1, y1 in (SIDELINE_PANTS_SHIELD, SIDELINE_PANTS_MAKER):
            mask[y0:y1, x0:x1] = False
        return _sideline_median(rgba, mask)
    return _sideline_median(rgba, np.ones(rgba.shape[:2], bool))


def _sideline_region_fabric(rgba, box, exclude=()):
    mask = _sideline_box(rgba.shape[:2], box)
    for x0, y0, x1, y1 in exclude:
        mask[y0:y1, x0:x1] = False
    return _sideline_median(rgba, mask)


def _sideline_shell(rgba, box):
    """The helmet shell colour inside the atlas box: the most frequent non-white colour, so the white padding,
    a light facemask or a logo's highlight does not win."""
    mask = _sideline_box(rgba.shape[:2], box)
    px = rgba[..., :3][mask & (rgba[..., 3] > 128)]
    require(len(px), "the sideline helmet box has no opaque texels")
    quantised = (px // 32) * 32
    values, counts = np.unique(quantised, axis=0, return_counts=True)
    order = np.argsort(-counts)
    pick = None
    for i in order:
        if int(values[i].min()) >= 224 and len(order) > 1:
            continue
        pick = values[i]
        break
    return np.median(px[(quantised == pick).all(axis=1)], axis=0).astype(np.int64)


def _sideline_recolour(rgba, region, source, target, tolerance=0.18):
    """Every shaded version of ``source`` inside ``region`` takes ``target`` with its brightness kept."""
    rgb = rgba[..., :3].astype(np.float32) / 255.0
    src = np.asarray(source, np.float32) / 255.0
    dst = np.asarray(target, np.float32) / 255.0
    luma = rgb @ SIDELINE_LUMA
    k = np.clip(luma / max(float(src @ SIDELINE_LUMA), 1e-3), 0.0, 2.5)
    distance = np.linalg.norm(rgb - src[None, None, :] * k[..., None], axis=2)
    mask = _sideline_smooth(np.clip(1.0 - distance / tolerance, 0.0, 1.0)) * region
    if float(dst.mean()) > 0.8:
        k = 1.0 - (1.0 - k) * 0.45                 # a light target keeps less of the retail contrast
    new = np.clip(dst[None, None, :] * k[..., None], 0.0, 1.0)
    out = rgba.copy()
    out[..., :3] = np.round((rgb * (1 - mask[..., None]) + new * mask[..., None]) * 255).astype(np.uint8)
    # ignore palette-rounding noise: a re-run over an already repaired part must not report a change
    moved = (np.abs(out[..., :3].astype(np.int16) - rgba[..., :3]).max(axis=2) > 2) & (mask > 0.5)
    return out, int(moved.sum())


def sideline_repair(alt, donor, field, parts):
    """Repair the listed parts of one splayer atlas. ``field`` maps part -> the field texture's fabric colour.
    ``changed`` is the net number of texels each part moved, so a run over an already repaired atlas reports zero
    (and the build does not rewrite an identical span)."""
    out = alt.copy()
    if "helmet" in parts:
        box = SIDELINE_BOXES["helmet"]
        region = _sideline_box(out.shape[:2], box)
        out[region] = donor[region]
        shell = _sideline_shell(out, box)
        out, _n = _sideline_recolour(out, region, shell, field["helmet"])
    if "sleeve" in parts:
        box = SIDELINE_BOXES["sleeve"]
        region = _sideline_box(out.shape[:2], box)
        out[region] = donor[region]
        fabric = _sideline_region_fabric(out, SIDELINE_SLEEVE_FABRIC)
        out, _n = _sideline_recolour(out, region, fabric, field["sleeve"])
    if "pants" in parts:
        box = SIDELINE_BOXES["pants"]
        region = _sideline_box(out.shape[:2], box)
        region[0:6, :] = False                      # the belt strip on top stays
        fabric = _sideline_region_fabric(out, box, (SIDELINE_BOXES["pants_stripe"],
                                                    SIDELINE_BOXES["pants_maker"]))
        if np.abs(fabric - np.asarray(field["pants"])).max() > SIDELINE_SAME:   # b779-vk2: already matching
            out, _n = _sideline_recolour(out, region, fabric, field["pants"])
    out = _sideline_settle(alt, out, parts)    # b779-vk2: a re-run over a repaired atlas changes nothing
    changed = {}
    for part in parts:
        box = SIDELINE_BOXES[part]
        region = _sideline_box(out.shape[:2], box)
        if part == "pants":
            region[0:6, :] = False
        moved = np.abs(out[..., :3].astype(np.int16) - alt[..., :3]).max(axis=2)
        changed[part] = int(((moved > 2) & region).sum())
    return out, changed


# b779-vk2: the full sideline audit (every 2026 kit package on the v0.7 disc, primaries and alternates, home and
# away, decoded beside its field textures and looked at). A row that names its expected ``field`` colours uses the
# measured path below instead of vk1's: colours are sampled as the most frequent colour family (a stripe, logo or
# padding column cannot drag a median), a part may be the torso, a part may name its own donor (``donors``), a part
# may carry explicit ``recolour`` rules (several source colours moved at once, e.g. the Bengals' sleeve stripes
# swap colour with their fabric) and ``fill`` boxes (a logo the field helmet does not have, filled from the shell
# around it). The row only acts while the field textures still read as the audited 2026 kit (``field``), so a
# retail build, an era kit or a user's own repaint of that slot is left alone; a primary (style 0) row also needs
# the 2026 kit set on the roster.
SIDELINE_RULE_REGIONS = {"pants": (0, 6, 128, 90), "torso": (128, 0, 256, 100), "sleeve": (195, 100, 256, 127),
                         "helmet": (38, 91, 126, 128)}
SIDELINE_FIELD_TOLERANCE = 24      # the measured field colour may differ this much from the audited one
SIDELINE_SAME = 16                 # a part already within this many levels of its field colour is left as it is
SIDELINE_SETTLED = 0.005           # a repair that moves under 0.5% of a part's texels by more than 32 levels is
                                   # palette noise over an already repaired part: the part is kept as it is


def _sideline_settle(alt, out, parts):
    """Keep every part whose repair would only re-quantise it (a re-run over a repaired atlas), so the pass
    converges: the second run reports no change and the build does not rewrite an identical span."""
    out = out.copy()
    moved = np.abs(out[..., :3].astype(np.int16) - alt[..., :3]).max(axis=2)
    for part in parts:
        region = _sideline_box(out.shape[:2], SIDELINE_BOXES[part])
        if part == "pants":
            region[0:6, :] = False
        if int(((moved > 32) & region).sum()) <= SIDELINE_SETTLED * int(region.sum()):
            out[region] = alt[region]
    return out


def _sideline_rule_region(shape, part, sampling=False):
    """Where a part is recoloured (the pants below the belt strip; the sleeve and helmet sides inside their white
    island border). ``sampling`` also leaves out the pants stripe band and maker mark, so they never set the
    fabric colour; the recolour itself spares them by colour, as vk1's pass does."""
    region = _sideline_box(shape, SIDELINE_RULE_REGIONS[part])
    if part == "pants" and sampling:
        for x0, y0, x1, y1 in (SIDELINE_BOXES["pants_stripe"], SIDELINE_BOXES["pants_maker"]):
            region[y0:y1, x0:x1] = False
    return region


def _sideline_mode(rgba, mask):
    """The most frequent colour family (24-level cells) inside ``mask``, as the median of its members."""
    px = rgba[..., :3][mask & (rgba[..., 3] > 128)].astype(np.int64)
    require(len(px), "the sideline region has no opaque texels")
    cells = px // 24
    values, inverse, counts = np.unique(cells, axis=0, return_inverse=True, return_counts=True)
    return np.median(px[inverse.reshape(-1) == int(counts.argmax())], axis=0).astype(np.int64)


def _sideline_field_mode(rgba, part):
    """The field texture's fabric colour: jersey00's torso rows, pants00 without its stripe bands, the whole
    sleeve00, and the shell side of the helmet sheet (clear of its decal column)."""
    h, w = rgba.shape[:2]
    mask = np.ones((h, w), bool)
    if part == "torso":
        mask[(100 * h) // 256:, :] = False
    elif part == "pants":
        for x0, x1 in SIDELINE_PANTS_STRIPES:
            mask[:, max(0, x0 - 10):x1 + 10] = False
        mask[(100 * h) // 256:, :] = False
    elif part == "helmet":
        mask[:, (100 * w) // 256:] = False
    return _sideline_mode(rgba, mask)


def _sideline_membership(rgb, luma, source, tolerance, narrow=False):
    """How much each texel is a shade of ``source`` (0..1), and its brightness relative to the source. ``narrow``
    keeps only the near shades (0.6..1.6) of a saturated colour too."""
    src = np.asarray(source, np.float32) / 255.0
    src_luma = float(src @ SIDELINE_LUMA)
    if src_luma < 0.1:
        # a near-black source has no usable brightness ratio: plain distance, shading from the luma offset
        distance = np.linalg.norm(rgb - src[None, None, :], axis=2)
        k = np.clip(1.0 + (luma - src_luma) * 4.0, 0.7, 1.4)
    else:
        # shades of the source: a saturated colour keeps vk1's wide shading range (its hue already separates it),
        # a grey source only its near shades, so it cannot take black or white with it
        ratio = luma / src_luma
        lo, hi = (0.25, 2.5) if float(src.max() - src.min()) > 0.15 and not narrow else (0.6, 1.6)
        k = np.clip(ratio, lo, hi)
        distance = np.linalg.norm(rgb - src[None, None, :] * k[..., None], axis=2)
        distance = np.where((ratio < lo) | (ratio > hi), np.inf, distance)
    return _sideline_smooth(np.clip(1.0 - distance / tolerance, 0.0, 1.0)), k


def _sideline_inpaint(rgba, box, keep, tolerance=0.18):
    """Inside ``box``, every texel that is not a shade of the fabric ``keep`` (a retail side panel, its piping) is
    filled from the fabric around it, ring by ring, then smoothed, so the painted folds continue across it."""
    x0, y0, x1, y1 = box
    sub = rgba[y0:y1, x0:x1, :3].astype(np.float32) / 255.0
    member, _k = _sideline_membership(sub, sub @ SIDELINE_LUMA, keep, tolerance, narrow=True)
    known = member > 0.5
    hole = ~known
    if not hole.any() or not known.any():
        return rgba
    value = np.where(known[..., None], sub, 0.0)
    filled = known.copy()

    def neighbours(v, m):
        total = np.zeros_like(v)
        count = np.zeros(m.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            shifted_v = np.roll(v, (dy, dx), axis=(0, 1))
            shifted_m = np.roll(m, (dy, dx), axis=(0, 1)).astype(np.float32)
            if dy == 1:
                shifted_m[0, :] = 0
            elif dy == -1:
                shifted_m[-1, :] = 0
            elif dx == 1:
                shifted_m[:, 0] = 0
            else:
                shifted_m[:, -1] = 0
            total += shifted_v * shifted_m[..., None]
            count += shifted_m
        return total, count

    for _ring in range(max(sub.shape[:2])):
        if filled.all():
            break
        total, count = neighbours(value, filled)
        grow = (~filled) & (count > 0)
        value[grow] = total[grow] / count[grow][:, None]
        filled |= grow
    for _smooth in range(24):
        total, count = neighbours(value, np.ones_like(filled))
        value[hole] = (total[hole] / np.maximum(count[hole], 1)[:, None])
    out = rgba.copy()
    out[y0:y1, x0:x1, :3] = np.round(np.clip(value, 0.0, 1.0) * 255).astype(np.uint8)
    return out


def _sideline_apply_rules(rgba, region, rules):
    """Move every listed source colour family inside ``region`` to its target at once, painted shading kept.
    ``rules`` are (source, target, tolerance, box-or-None); the masks are all taken from the input, so a swap of
    two colours works, and a texel that two rules claim takes the rule it belongs to most."""
    rgb = rgba[..., :3].astype(np.float32) / 255.0
    luma = rgb @ SIDELINE_LUMA
    best = np.zeros(rgb.shape[:2], np.float32)
    acc = np.zeros(rgb.shape, np.float32)
    for source, target, tolerance, box in rules:
        dst = np.asarray(target, np.float32) / 255.0
        member, k = _sideline_membership(rgb, luma, source, tolerance)
        area = region if box is None else region & _sideline_box(region.shape, box)
        # a texel that already is the target colour stays put (a re-run converges instead of darkening shades)
        area = area & (np.abs(rgb - dst[None, None, :]).max(axis=2) * 255.0 > SIDELINE_SAME)
        mask = member * area
        if float(dst.mean()) > 0.8:
            k = 1.0 - (1.0 - k) * 0.45
        take = mask > best
        acc[take] = np.clip(dst[None, None, :] * k[..., None], 0.0, 1.0)[take]
        best = np.where(take, mask, best)
    weight = best[..., None]
    out = rgba.copy()
    out[..., :3] = np.round((rgb * (1.0 - weight) + acc * weight) * 255).astype(np.uint8)
    return out


def _sideline_fill(rgba, part_box, box):
    """Fill ``box`` flat with the most frequent colour of the 2-texel ring around it (inside the part's box)."""
    x0, y0, x1, y1 = box
    ring = _sideline_box(rgba.shape[:2], (x0 - 2, y0 - 2, x1 + 2, y1 + 2)) & _sideline_box(rgba.shape[:2], part_box)
    ring[y0:y1, x0:x1] = False
    colour = _sideline_mode(rgba, ring)
    out = rgba.copy()
    out[y0:y1, x0:x1, :3] = colour.astype(np.uint8)
    return out


def _sideline_part_colour(atlas, part):
    return _sideline_mode(atlas, _sideline_rule_region(atlas.shape[:2], part, sampling=True))


def sideline_measured_repair(alt, donors, field, row):
    """vk2's measured path for one row. ``donors`` maps part -> donor atlas (absent: repaired in place), ``field``
    part -> the measured field colour. Returns the atlas and the texels each part moved (net, so a re-run over a
    repaired atlas reports zero)."""
    out = alt.copy()
    rules = row.get("recolour") or {}
    fills = row.get("fill") or {}
    inpaints = row.get("inpaint") or {}
    for part in ("torso", "helmet", "sleeve", "pants"):
        if part not in row["parts"]:
            continue
        box = SIDELINE_BOXES[part]
        donor = donors.get(part)
        if donor is not None:
            region = _sideline_box(out.shape[:2], box)
            out[region] = donor[region]
        region = _sideline_rule_region(out.shape[:2], part)
        settled = np.abs(_sideline_part_colour(out, part) - field[part]).max() <= SIDELINE_SAME
        if settled and part not in (row.get("always") or ()):
            # the part already reads as its field colour: a repaired atlas (re-running a colour swap would swap
            # it back). ``always`` names parts whose stray colours sit on the right fabric (MIN's purple blotches).
            pass
        elif part not in rules and (part in fills or part in inpaints):
            pass        # only the boxed fixes below: the fabric itself is already the field kit's
        elif part in rules:
            todo = []
            for rule in rules[part]:
                target = field[part] if rule.get("to", "field") == "field" else np.asarray(rule["to"], np.int64)
                source = np.asarray(rule["from"], np.int64)
                if rule.get("to", "field") == "field" and np.abs(source - target).max() <= SIDELINE_SAME:
                    continue
                todo.append((source, target, float(rule.get("tolerance", 0.18)), rule.get("box")))
            if todo:
                out = _sideline_apply_rules(out, region, todo)
        else:
            out = _sideline_apply_rules(out, region, [(_sideline_part_colour(out, part), field[part], 0.18, None)])
        for fill_box in fills.get(part, ()):
            out = _sideline_fill(out, box, tuple(fill_box))
        for op in inpaints.get(part, ()):
            out = _sideline_inpaint(out, tuple(op["box"]), op["keep"], float(op.get("tolerance", 0.18)))
    out = _sideline_settle(alt, out, row["parts"])
    changed = {}
    moved = np.abs(out[..., :3].astype(np.int16) - alt[..., :3]).max(axis=2)
    for part in row["parts"]:
        region = _sideline_box(out.shape[:2], SIDELINE_BOXES[part])
        if part == "pants":
            region[0:6, :] = False
        changed[part] = int(((moved > 2) & region).sum())
    return out, changed


def _sideline_rgba(span, kind, name):
    chunk, decoded, textures = native_textures(span, kind)
    texture = textures[0]
    require(texture["name"] == name, "texture name differs: " + texture["name"])
    planes = read_planes(decoded, chunk, texture)
    palette = read_palette(decoded, chunk, texture)
    return palette[planes[0]].astype(np.uint8)


def _sideline_mips(rgba, width, height, levels):
    import nfl_tset_png_import as palette_tools
    require(np.asarray(rgba).size == width * height * 4, "sideline RGBA size mismatch")
    current, w, h = np.ascontiguousarray(rgba).tobytes(), width, height
    out = [palette_tools.MipLevel(0, width, height, current)]
    for level in range(1, levels):
        require(w % 2 == 0 and h % 2 == 0, "sideline mip chain cannot be halved")
        nw, nh = w // 2, h // 2
        reduced = bytearray(nw * nh * 4)
        for y in range(nh):
            for x in range(nw):
                offsets = (((y * 2) * w + x * 2) * 4, ((y * 2) * w + x * 2 + 1) * 4,
                           (((y * 2) + 1) * w + x * 2) * 4, (((y * 2) + 1) * w + x * 2 + 1) * 4)
                target = (y * nw + x) * 4
                for c in range(4):
                    reduced[target + c] = (sum(current[o + c] for o in offsets) + 2) // 4
        current, w, h = bytes(reduced), nw, nh
        out.append(palette_tools.MipLevel(level, w, h, current))
    return out


def _sideline_compile(span, rgba):
    """Re-quantise the edited RGBA into the splayer's own P8 chunk span (size, mips and wrapper kept)."""
    import nfl_tset_png_import as palette_tools
    chunk, decoded, textures = native_textures(span, "txtr")
    texture = textures[0]
    levels = _sideline_mips(np.ascontiguousarray(rgba), texture["width"], texture["height"], texture["mips"])
    _decoded, info = decode_chunk(span, chunk)

    def build(palette, index_levels):
        chain = b"".join(swizzle_2d(indices, mip.width, mip.height, 1)
                         for indices, mip in zip(index_levels, levels))
        return decoded[:chunk.system_bytes] + chain + palette_tools.palette_bytes(palette)

    bounded = palette_tools.quantize_levels_to_vc_lz_bound(
        levels, build, stream_tag=info.stream_tag, offset_bits=info.offset_bits,
        max_encoded_size=chunk.stored_size)
    fixed, fit = _rebuild(span, bounded.decoded)
    check = _sideline_rgba(fixed, "txtr", "splayer")
    require(check.shape == rgba.shape, "sideline span round trip changed the texture size")
    return fixed, fit


def _sideline_rows(document=None):
    document = document or sideline()
    rows = document.get("kits") or []
    seen = set()
    for row in rows:
        selector = row.get("selector")
        require(isinstance(selector, str) and 4 <= len(selector) <= 5 and selector[:2].isdigit()
                and selector[2] in "HA" and selector[3:].isdigit(),
                "a sideline row has no NN[HA]N selector")
        require(selector not in seen, selector + ": sideline row repeated")
        seen.add(selector)
        parts = row.get("parts")
        require(isinstance(parts, list) and parts and all(p in SIDELINE_PARTS for p in parts)
                and len(set(parts)) == len(parts), selector + ": sideline parts must be pants/sleeve/helmet/torso")
        measured = "field" in row
        if not measured:
            require("torso" not in parts and int(selector[3:]) > 0
                    and not any(key in row for key in ("donors", "recolour", "fill", "inpaint", "always")),
                    selector + ": torso, primary-kit, per-part donor, recolour and fill rows need their field colours")
            if any(p in parts for p in ("sleeve", "helmet")):
                require(_sideline_selector(row.get("donor")),
                        selector + ": a sleeve/helmet repair needs its NN[HA]N donor")
            continue
        field = row["field"]
        require(isinstance(field, dict) and sorted(field) == sorted(parts)
                and all(_sideline_colour(v) for v in field.values()),
                selector + ": field must give one [r, g, b] per repaired part")
        require(row.get("donor") is None or _sideline_selector(row["donor"]), selector + ": bad donor")
        donors = row.get("donors") or {}
        require(isinstance(donors, dict) and all(k in parts and _sideline_selector(v) for k, v in donors.items()),
                selector + ": donors must map repaired parts to NN[HA]N kits")
        require(isinstance(row.get("always", []), list) and all(p in (row.get("recolour") or {}) for p in row.get("always", [])),
                selector + ": always names parts with recolour rules")
        for key in ("recolour", "fill", "inpaint"):
            require(isinstance(row.get(key, {}), dict) and all(k in parts for k in row.get(key, {})),
                    selector + ": " + key + " must be keyed by repaired parts")
        for part, rules in (row.get("recolour") or {}).items():
            require(isinstance(rules, list) and rules, selector + ": empty recolour list")
            for rule in rules:
                require(_sideline_colour(rule.get("from"))
                        and (rule.get("to", "field") == "field" or _sideline_colour(rule.get("to")))
                        and 0.0 < float(rule.get("tolerance", 0.18)) <= 0.5
                        and (rule.get("box") is None or _sideline_inside(rule["box"], SIDELINE_BOXES[part])),
                        selector + ": bad " + part + " recolour rule")
        for part, ops in (row.get("inpaint") or {}).items():
            require(isinstance(ops, list) and ops and all(
                isinstance(op, dict) and _sideline_inside(op.get("box"), SIDELINE_BOXES[part])
                and _sideline_colour(op.get("keep")) and 0.0 < float(op.get("tolerance", 0.18)) <= 0.5 for op in ops),
                selector + ": a " + part + " inpaint needs a box inside the part and the fabric colour to keep")
        for part, boxes in (row.get("fill") or {}).items():
            require(isinstance(boxes, list) and boxes and all(_sideline_inside(b, SIDELINE_BOXES[part]) for b in boxes),
                    selector + ": a " + part + " fill box must sit inside the part")
    return rows


def _sideline_selector(value):
    return (isinstance(value, str) and 4 <= len(value) <= 5 and value[:2].isdigit() and value[2] in "HA"
            and value[3:].isdigit())


def _sideline_colour(value):
    return isinstance(value, list) and len(value) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in value)


def _sideline_inside(box, outer):
    return (isinstance(box, list) and len(box) == 4 and all(isinstance(v, int) for v in box)
            and outer[0] <= box[0] < box[2] <= outer[2] and outer[1] <= box[1] < box[3] <= outer[3])


def _sideline_field_textures(raw, chunks, selector, parts):
    """The field textures of one kit package that the listed parts are measured against."""
    out = {}
    for part in parts:
        if part == "helmet":
            chunk = chunks.get(12) if 12 in chunks and chunks[12].kind == "TXTR" else chunks.get(11)
            require(chunk is not None and chunk.kind == "TXTR", selector + ": helmet chunk absent")
            out[part] = _sideline_rgba(raw[chunk.offset:chunk.end_offset], "txtr",
                                       "helmet02" if chunk.index == 12 else "helmet00")
        else:
            index, name = {"torso": (1, "jersey00"), "pants": (2, "pants00"), "sleeve": (3, "sleeve00")}[part]
            require(index in chunks, selector + ": " + name + " chunk absent")
            out[part] = _sideline_rgba(raw[chunks[index].offset:chunks[index].end_offset], "tset", name)
    return out


def _sideline_measured_plan(row, entry, raw, chunks, splayer, alt, package):
    """Plan one vk2 (measured) row: guard on the audited field colours, repair, compile and check the result."""
    selector = row["selector"]
    textures = _sideline_field_textures(raw, chunks, selector, row["parts"])
    field = {part: _sideline_field_mode(textures[part], part) for part in row["parts"]}
    drift = {part: int(np.abs(field[part] - np.asarray(row["field"][part])).max()) for part in row["parts"]}
    if max(drift.values()) > SIDELINE_FIELD_TOLERANCE:
        # the field kit is not the audited 2026 kit (retail, era kit or a user's repaint): leave the atlas alone
        return (entry, [], dict(selector=selector, state="field_differs", drift=drift))
    donor_atlas = {}
    donors = {part: (row.get("donors") or {}).get(part, row.get("donor")) for part in row["parts"]}
    for part, donor in donors.items():
        if donor and part != "pants":
            if donor not in donor_atlas:
                _donor_entry, donor_raw = package(donor)
                donor_chunks = {chunk.index: chunk for chunk in parse_chunks(donor_raw)}
                require(51 in donor_chunks, donor + ": donor splayer chunk absent")
                donor_atlas[donor] = _sideline_rgba(
                    donor_raw[donor_chunks[51].offset:donor_chunks[51].end_offset], "txtr", "splayer")
    repaired, changed = sideline_measured_repair(
        alt, {part: donor_atlas[d] for part, d in donors.items() if d and part != "pants"}, field, row)
    if not any(changed.values()):
        return (entry, [], dict(selector=selector, state="unchanged", changed_texels=changed))
    new_span, fit = _sideline_compile(splayer, repaired)
    check = _sideline_rgba(new_span, "txtr", "splayer")
    for part in row["parts"]:
        now = _sideline_part_colour(check, part)
        before = _sideline_part_colour(alt, part)
        # within the atlas's own painted shading of that fabric (a white torso is shaded to about 210), and never
        # further from the field colour than the shipped atlas was
        require(np.abs(now - field[part]).max() <= max(48, int(np.abs(before - field[part]).max()) + 16),
                selector + ": the repaired " + part + " colour did not take")
    return (entry, [(chunks[51].offset, new_span)],
            dict(selector=selector, state="repaired", changed_texels=changed,
                 field={k: [int(v) for v in f] for k, f in field.items()}, fit=asdict(fit)))


def apply_sideline(path, *, strict=False, document=None):
    """Studio uniform finish pass: repair the pinned 2026 alternate sideline atlases (after every kit writer)."""
    rows = _sideline_rows(document)
    if not rows:
        return dict(state="applied", written_spans=0, written_bytes=0, changed_bytes=0, kits=[])
    try:
        with bump._Image.open(Path(path), writable=False) as source:
            index = bump._parsed_index(source)
            names = {bump.logical_name_for(e.name_id) for e in index.entries}
    except (ValueError, OSError):
        if strict:
            raise
        return dict(state="other_image", written_spans=0, written_bytes=0, changed_bytes=0, kits=[])
    wanted = sorted({row["selector"] for row in rows} | {row["donor"] for row in rows if row.get("donor")}
                    | {d for row in rows for d in (row.get("donors") or {}).values()})
    if not strict and not all(s + ".IFF" in names for s in wanted):
        return dict(state="other_uniform", written_spans=0, written_bytes=0, changed_bytes=0, kits=[])
    plans, written, written_bytes = [], 0, 0
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        # Only a target whose roster carries the 2026 alternate labels is repaired. A retail build keeps the
        # retail style pairs (e.g. MIN style 6 is 2004 Alternate 2), so its kits are left exactly as they are.
        from . import nfl2k5_historic_styles as hs
        from . import nfl2k5_uniform_slots as us
        roster_entry = next((entry for entry in index.entries if entry.name_id == hs.ROSTER_OUTER_ID), None)
        require(roster_entry is not None, "the main roster is absent")
        roster = image.read_segments(index.sub_extents(roster_entry, 0, roster_entry.size))
        roster_body = roster[32:]
        roster_pairs = {code: us.team_pairs(roster_body, at) for at, code in hs.team_records(roster)[:32]}

        def package(selector):
            entries = by_name.get(selector + ".IFF", [])
            require(len(entries) == 1, selector + " kit package absent or duplicated")
            return entries[0], image.read_segments(index.sub_extents(entries[0], 0, entries[0].size))

        # Preflight every read and compile before the first write, so a refusal leaves the image untouched.
        for row in rows:
            selector = row["selector"]
            entry = by_name.get(selector + ".IFF", [None])[0]
            require(entry is not None, selector + " kit package absent")
            style = int(selector[3:])
            pairs = roster_pairs.get(selector[:2]) or []
            pair = pairs[style - 1] if 1 <= style <= len(pairs) else None
            if style == 0:
                # a primary kit: only on a roster that carries the 2026 kit set (retail keeps its retail kits)
                ok = any(p[0] == us.ALTERNATE_YEAR for p in pairs)
            else:
                ok = pair is not None and pair[0] == us.ALTERNATE_YEAR
            if not ok:
                plans.append((entry, [], dict(selector=selector, state="not_2026")))
                continue
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            chunks = {chunk.index: chunk for chunk in parse_chunks(raw)}
            require(51 in chunks and chunks[51].kind == "TXTR", selector + ": splayer chunk absent")
            splayer = raw[chunks[51].offset:chunks[51].end_offset]
            alt = _sideline_rgba(splayer, "txtr", "splayer")
            if "field" in row:
                plan = _sideline_measured_plan(row, entry, raw, chunks, splayer, alt, package)
                plans.append(plan)
                continue
            field = {}
            if "pants" in row["parts"]:
                require(2 in chunks, selector + ": pants chunk absent")
                field["pants"] = _sideline_fabric(
                    _sideline_rgba(raw[chunks[2].offset:chunks[2].end_offset], "tset", "pants00"), "pants")
            if "sleeve" in row["parts"]:
                require(3 in chunks, selector + ": sleeve chunk absent")
                field["sleeve"] = _sideline_fabric(
                    _sideline_rgba(raw[chunks[3].offset:chunks[3].end_offset], "tset", "sleeve00"), "sleeve")
            if "helmet" in row["parts"]:
                helmet_chunk = chunks.get(12) if 12 in chunks and chunks[12].kind == "TXTR" else chunks.get(11)
                require(helmet_chunk is not None and helmet_chunk.kind == "TXTR", selector + ": helmet chunk absent")
                helmet = _sideline_rgba(raw[helmet_chunk.offset:helmet_chunk.end_offset], "txtr",
                                        "helmet02" if helmet_chunk.index == 12 else "helmet00")
                field["helmet"] = _sideline_fabric(helmet, "helmet")
            donor = None
            if row.get("donor"):
                _donor_entry, donor_raw = package(row["donor"])
                donor_chunks = {chunk.index: chunk for chunk in parse_chunks(donor_raw)}
                require(51 in donor_chunks, row["donor"] + ": donor splayer chunk absent")
                donor = _sideline_rgba(donor_raw[donor_chunks[51].offset:donor_chunks[51].end_offset],
                                       "txtr", "splayer")
            repaired, changed = sideline_repair(alt, donor if donor is not None else alt, field, row["parts"])
            if not any(changed.values()):
                plans.append((entry, [], dict(selector=selector, state="unchanged", changed_texels=changed)))
                continue
            new_span, fit = _sideline_compile(splayer, repaired)
            check = _sideline_rgba(new_span, "txtr", "splayer")
            # the repaired fabrics must now read as the field colours (palette quantisation allows a few levels)
            if "pants" in row["parts"]:
                now = _sideline_region_fabric(check, SIDELINE_BOXES["pants"],
                                              (SIDELINE_BOXES["pants_stripe"], SIDELINE_BOXES["pants_maker"]))
                require(np.abs(now - field["pants"]).max() <= 24, selector + ": the repaired pants colour did not take")
            if "sleeve" in row["parts"]:
                now = _sideline_region_fabric(check, SIDELINE_SLEEVE_FABRIC)
                require(np.abs(now - field["sleeve"]).max() <= 40, selector + ": the repaired sleeve colour did not take")
            if "helmet" in row["parts"]:
                now = _sideline_shell(check, SIDELINE_BOXES["helmet"])
                require(np.abs(now - field["helmet"]).max() <= 40, selector + ": the repaired helmet colour did not take")
            plans.append((entry, [(chunks[51].offset, new_span)],
                          dict(selector=selector, state="repaired", changed_texels=changed,
                               field={k: [int(v) for v in f] for k, f in field.items()}, fit=asdict(fit))))
        for entry, replacements, receipt in plans:
            for offset, data in replacements:
                segments = index.sub_extents(entry, offset, len(data))
                image.write_segments(segments, data)
                require(image.read_segments(segments) == data, "written sideline span read-back differs")
                written += 1
                written_bytes += len(data)
        kits = plans and [receipt for _e, _r, receipt in plans]
    changed = sum(sum(k.get("changed_texels", {}).values()) for k in (kits or []))
    return dict(state="applied", written_spans=written, written_bytes=written_bytes,
                changed_bytes=changed, kits=kits or [])


def apply_sideline_pack(path, *, strict=False):
    """Alias used by the build receipt: the pinned 2026 alternate sideline-atlas pass."""
    return apply_sideline(path, strict=strict)
