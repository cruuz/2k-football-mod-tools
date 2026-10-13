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
        require(row["kind"] in ("tset", "txtr", "copy_video"), "unknown chunk kind")
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


def enclosed(rgba, box, edge, colour, tolerance):
    """Fill every 4-connected region of non-``edge`` texels inside ``box`` that does not touch the box border
    (the hollow inside of an outlined letter) with ``colour``."""
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


def paint(rgba, ops):
    """Apply the authored operations in order; returns the new level 0 and the changed scope."""
    out = rgba.copy()
    h, w = out.shape[:2]
    for op in ops:
        kind = op["op"]
        if kind == "poly":
            cover = polygon_coverage(op["points"], w, h)
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
            out, _ = enclosed(out, op["box"], op["edge"], hex_rgb(op["color"]), op.get("tolerance", 24))
        elif kind == "copy":
            out = copy_texels(out, rgba, op)
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
    raise ValueError("2026 kit fixes: the _mud palette follows neither wet_93 nor darken_60 of the clean palette")


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


def compile_texture(span, row):
    """Paint ``row``'s art into one native chunk span; returns (new span, receipt)."""
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
    painted, scope = paint(base, row["ops"])
    require(scope.any(), "the art changed no texel")
    alphas = base[..., 3].astype(np.int64)
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
    new_planes, rows = [], []
    target = painted.astype(np.int64)
    changed = scope
    for level, plane in enumerate(planes):
        ph, pw = plane.shape
        out = plane.copy()
        points = np.argwhere(changed)
        if len(points):
            colours = target[points[:, 0], points[:, 1], :3]
            # each stored mip keeps its own alpha (helmet reflection masks are authored per level)
            alphas_here = palette[plane][points[:, 0], points[:, 1], 3]
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
    new = write_texture(decoded, chunk, clean, new_planes, palette)
    if row["kind"] == "tset":
        # existing twin entries stay byte-exact; only the slots this fix filled get the rule's value
        twin = mud.copy()
        slots = [a["slot"] for a in added]
        twin[slots] = MUD_RULES[rule](palette)[slots]
        new = write_texture(new, chunk, textures[1], new_planes, twin)
    fixed_span, fit = rebuild_fixed_span_filled(span, new, encoder="auto")
    require(len(fixed_span) == len(span) and fixed_span[:32] == span[:32], "wrapper or allocation changed")
    check, _ = decode_chunk(fixed_span, parse_chunks(fixed_span)[0])
    require(check == new, "native round trip differs")
    return fixed_span, dict(texture=clean["name"], mips=rows, palette_slots_added=added, mud_rule=rule,
                            merged_twin_slots=merged_slots, protected_texels_moved_one_level=merged_moved,
                            fit=asdict(fit), level0_scope_texels=int(scope.sum()))


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


def compile_resource(selector, raw, *, strict=True, document=None):
    """Compile every pinned texture of one kit package; refuses partial or unknown inputs when strict."""
    document = document or spec()
    rows = [r for r in document["textures"] if r["selector"] == selector]
    require(rows, "no entries for " + selector)
    states = []
    for row in rows:
        chunk = _chunk_for(raw, row["chunk"])
        span = raw[chunk.offset:chunk.end_offset]
        layout_ok = (len(raw), chunk.offset, len(span)) == (row["resource_size"], row["offset"], row["length"])
        digest = sha(span) if layout_ok else None
        states.append((row, chunk, span, "before" if digest == row["before_sha256"]
                       else "after" if digest == row["after_sha256"] else "other"))
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
        else:
            new, detail = compile_texture(span, row)
        require(sha(new) == row["after_sha256"], selector + ": Studio compile differs from its output pin")
        replacements.append((chunk.offset, new))
        parts.append(dict(selector=selector, chunk_index=chunk.index, offset=chunk.offset, length=len(new),
                          before_sha256=sha(span), after_sha256=sha(new),
                          changed_bytes=sum(a != b for a, b in zip(span, new)), defects=row.get("defects", []),
                          **detail))
    return replacements, dict(selector=selector, state="applied", skipped_textures=skipped,
                              changed_bytes=sum(p["changed_bytes"] for p in parts), parts=parts)


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
        plans = []
        for selector in wanted:
            entries = by_name.get(selector + ".IFF", [])
            require(len(entries) == 1, selector + " kit package absent or duplicated")
            entry = entries[0]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            replacements, receipt = compile_resource(selector, raw, strict=strict, document=document)
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
