"""The 2026 pants hem: football pants that end above the knee, as the NFL wears them now (b773-pa1, N32).

The game's one shared player body ends its pants shell in a cuff just below the knee and starts the sock there. Job
pt0 measured the body and specified a texture-only hem: paint the pants-to-legging boundary higher on the pants
texture and carry the kit's own sock colour over the lower pants, so the knee reads as covered by the sock as in the
2026 game highlights. The cuff geometry stays (no shared mesh, skin or morph changes, so every era and body type keeps
working); only the kit textures of the current-season kits change.

``data/nfl2k5_pants_hem_2026.json`` holds the hem as data: one contour per atlas (the native body's pants triangles cut
by the horizontal plane at hip-to-ankle fraction ``fraction`` in the bind pose, averaged over the high and low detail
bodies; texel coordinates), the overhang shadow bands under it, and one row per kit texture with its legging colour
(the kit's own upper-sock colour, clean and wet) and its exact input and output pins.

Three textures per kit change, each in its own native span (format, size, mips, descriptors, wrapper and stored
allocation kept):

* ``pants00`` (chunk 2, P8 TSET, clean and ``_mud`` palettes sharing one index plane): below the contour the legging
  colour, drawn at 4x4 samples per texel in exact integer arithmetic and averaged onto the native texels, with the
  overhang shadow in the first texels under the hem. Clean and wet (mud) colours are quantised together, so the
  legging also takes the sock's own wet colour in rain games. New colours take palette entries no texel outside the
  repainted area uses, then near-identical twins folded together (a protected texel moves by at most two levels).
* ``splayer`` (chunk 51, P8 TXTR): the sideline player's pants island gets the same hem from its own contour. An
  atlas whose retail stream leaves no in-place decode margin for the edit keeps its retail hem (``sideline_kept``).
* ``bump_pants`` (chunk 47, A8R8G8B8 TXTR): the pants relief (knee pad creases, the cuff edge) is faded to a flat
  normal under the hem, so the legging does not carry pants folds.

Only changed texels and their mip parents move. The Studio runs this after the uf3 kit finish; exact pins limit it to
the known SOFTDRINK kit spans, so retail kits, the era and throwback kits and textures a user's recipe replaced are
left alone. The native repair (strict) refuses any kit that is not exactly the pinned input or the pinned output.
"""
from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
import json
from pathlib import Path

import numpy as np

from . import nfl2k5_bump_texture_writer as bump
from . import nfl2k5_kit_fixes_2026 as kit
from nfl_txtr import TxtrError, decode_chunk, parse_chunks, parse_texture, swizzle_2d, unswizzle_2d
from nfl_vc_lz_fill import rebuild_fixed_span_filled

SCHEMA = "nfl2k5_pants_hem_2026/v1"
DATA = Path(__file__).resolve().parents[2] / "data/nfl2k5_pants_hem_2026.json"
KINDS = ("pants", "splayer", "bump")
FULL = kit.SUPER * kit.SUPER          # samples per texel
WET_WEIGHT = 4                        # clean colour error counts four times the wet colour error when quantising
ADD_DISTANCE = 48                     # weighted squared distance above which a frequent colour earns a palette entry
MERGE_LIMITS = (1, 2)                 # twin folds tried in turn (levels a protected texel may move)
FLAT = (128, 128, 255)                # tangent-space flat normal (RGB)

sha = kit.sha


def require(ok, message):
    if not ok:
        raise ValueError("2026 pants hem: " + message)


def spec(path=None):
    document = json.loads(Path(path or DATA).read_text(encoding="utf-8"))
    require(document.get("schema") == SCHEMA, "unexpected data schema")
    seen = set()
    for row in document["textures"]:
        key = (row["selector"], row["chunk"])
        require(key not in seen, "duplicate texture entry " + repr(key))
        seen.add(key)
        require(row["kind"] in KINDS, "unknown texture kind")
    return document


# -- the hem shape ---------------------------------------------------------------------------------------------------

def below(points, depth, bottom, x0, x1):
    """The region under the contour lowered by ``depth`` texels, from ``x0`` to ``x1`` and down to ``bottom``: the
    contour's end heights carry on to the box edges (the atlas gutters)."""
    pts = [(float(x), float(y) + depth) for x, y in points]
    return [(float(x0), pts[0][1])] + pts + [(float(x1), pts[-1][1]), (float(x1), float(bottom)), (float(x0), float(bottom))]


def band(points, top, bottom, x0, x1):
    """The strip between the contour lowered by ``top`` and by ``bottom`` texels."""
    upper = [(float(x), float(y) + top) for x, y in points]
    lower = [(float(x), float(y) + bottom) for x, y in points]
    upper = [(float(x0), upper[0][1])] + upper + [(float(x1), upper[-1][1])]
    lower = [(float(x0), lower[0][1])] + lower + [(float(x1), lower[-1][1])]
    return upper + lower[::-1]


@lru_cache(maxsize=32)
def _coverage(polygon, width, height):
    out = kit.polygon_coverage(list(polygon), width, height)
    out.flags.writeable = False
    return out


def coverage(polygon, width, height):
    """``kit.polygon_coverage``, computed once per polygon and atlas size (every kit shares the hem)."""
    return _coverage(tuple(polygon), int(width), int(height))


def hem_shape(hem, width, height):
    """(legging samples per texel, shaded weight per texel): the weight is the sum over the texel's legging samples of
    each sample's brightness in percent (100 outside the shadow bands)."""
    x0, y0, x1, y1 = hem.get("box", (0, 0, width, height))
    points = hem["points"]
    cover = coverage(below(points, 0.0, y1, x0, x1), width, height)
    weight = cover * 100
    for top, bottom, keep in hem.get("shadow", []):
        strip = coverage(band(points, float(top), float(bottom), x0, x1), width, height)
        weight = weight - strip * (100 - int(keep))
    box = np.zeros((height, width), bool)
    box[int(y0):int(y1), int(x0):int(x1)] = True
    cover = np.where(box, cover, 0)
    weight = np.where(box, weight, 0)
    return cover.astype(np.int64), weight.astype(np.int64)


def blend(base, colour, cover, weight):
    """Per texel: (16 - cover) samples of ``base`` and the legging samples of ``colour`` at their shaded weight."""
    c = np.array(colour, np.int64)[None, None, :]
    total = base.astype(np.int64) * ((FULL - cover) * 100)[..., None] + c * weight[..., None]
    return (total + FULL * 50) // (FULL * 100)


# -- P8 hem (pants with the wet twin, the sideline atlas) ------------------------------------------------------------

def nearest_pairs(clean, wet, palette, mud, candidates):
    """Nearest entry among ``candidates`` for each (clean, wet) target: weighted squared distance, lowest index on
    ties. Without a wet twin only the clean colour counts."""
    cand = np.asarray(candidates, np.int64)
    pairs, inverse = np.unique(np.concatenate([clean, wet], axis=1), axis=0, return_inverse=True)
    clean, wet = pairs[:, :3], pairs[:, 3:]
    d = ((clean[:, None, :] - palette[cand, :3][None, :, :]) ** 2).sum(axis=2) * WET_WEIGHT
    if mud is not None:
        d += ((wet[:, None, :] - mud[cand, :3][None, :, :]) ** 2).sum(axis=2)
    return cand[d.argmin(axis=1)][inverse.reshape(-1)]


def _weighted(clean, wet, palette, mud, entries):
    """Weighted squared distance from each target to its nearest entry."""
    if not len(entries):
        return np.full(len(clean), 1 << 40, np.int64)
    e = np.asarray(entries, np.int64)
    d = ((clean[:, None, :] - palette[e, :3][None, :, :]) ** 2).sum(axis=2) * WET_WEIGHT
    if mud is not None:
        d += ((wet[:, None, :] - mud[e, :3][None, :, :]) ** 2).sum(axis=2)
    return d.min(axis=1)


def choose_entries(palette, mud, entries, clean, wet, legging, wet_legging, keeps, budget):
    """The palette entries the hem needs, in order: the legging colour (unless an entry already holds it exactly,
    wet colour included), its shadow tones, then edge colours picked one at a time by (texels x squared distance to
    the nearest available colour), so the anti-aliased edge gets evenly spread steps. Exact integers."""
    pal, wpal = palette.copy(), None if mud is None else mud.copy()
    avail = list(entries)
    out = []

    def take(c, m, role):
        slot = 256 + len(out)               # virtual entry while choosing
        nonlocal pal, wpal
        pal = np.vstack([pal, np.array([[*c, 255]], np.int64)])
        if wpal is not None:
            wpal = np.vstack([wpal, np.array([[*m, 255]], np.int64)])
        avail.append(slot)
        out.append((tuple(int(v) for v in c), None if m is None else tuple(int(v) for v in m), role))

    def gap(c, m):
        return int(_weighted(np.array([c], np.int64), np.array([m if m is not None else (0, 0, 0)], np.int64),
                             pal, wpal, avail)[0])

    if gap(legging, wet_legging) > 0:
        take(legging, wet_legging, "legging")
    for keep in keeps:
        c = tuple((v * keep + 50) // 100 for v in legging)
        m = None if wet_legging is None else tuple((v * keep + 50) // 100 for v in wet_legging)
        if gap(c, m) > ADD_DISTANCE // 4:
            take(c, m, "shadow")
    pairs = np.concatenate([clean, wet], axis=1).astype(np.int64)
    values, counts = np.unique(pairs, axis=0, return_counts=True)
    while len(out) < budget:
        d = _weighted(values[:, :3], values[:, 3:], pal, wpal, avail)
        score = d * counts
        i = int(score.argmax())
        if d[i] <= ADD_DISTANCE:
            break
        take(values[i, :3], None if mud is None else values[i, 3:], "edge")
    return out


def merge_twins(palette, mud, planes, needed, limit, exclude):
    """Free ``needed`` entries by folding an entry into a near-identical twin (alpha 255, every clean and wet channel
    within ``limit`` levels); neither may be an ``exclude`` entry (the slots about to take new colours). The rarer
    entry folds first, lowest indices on ties. Returns the freed entries and the texels that moved."""
    counts = np.zeros(256, np.int64)
    for plane in planes:
        counts += np.bincount(plane.ravel(), minlength=256)
    live = [i for i in range(256) if palette[i, 3] == 255 and counts[i] > 0 and i not in exclude]
    pairs = []
    for a in live:
        for b in live:
            if a == b or np.abs(palette[a, :3] - palette[b, :3]).max() > limit:
                continue
            if mud is not None and np.abs(mud[a, :3] - mud[b, :3]).max() > limit:
                continue
            pairs.append((int(counts[a]), a, b))
    freed, moved, gone, kept = [], 0, set(), set()
    for count, a, b in sorted(pairs):
        if len(freed) >= needed:
            break
        if a in gone or b in gone or a in kept:
            continue                        # a texel moves once, so by at most ``limit`` levels
        for plane in planes:
            plane[plane == a] = b
        gone.add(a)
        kept.add(b)
        freed.append(a)
        moved += count
    return freed, moved


FALLBACK_BUDGETS = (6, 4, 2)            # fewer edge colours, tried in turn when the palette tail will not fit


def compile_p8(span, row, hem, kind):
    """Paint the hem into one P8 chunk span (TSET with its ``_mud`` twin, or a TXTR); returns (span, receipt).
    When the stream cannot keep the retail in-place margin, fewer edge colours are tried in turn."""
    budget = int(row.get("max_new_entries", 10))
    for attempt in (budget,) + tuple(b for b in FALLBACK_BUDGETS if b < budget):
        try:
            fixed_span, receipt = _compile_p8(span, row, hem, kind, attempt)
        except ScratchError:
            continue
        return fixed_span, dict(receipt, entry_budget=attempt)
    raise ScratchError("2026 pants hem: the texture cannot keep the retail loader scratch allowance")


def _compile_p8(span, row, hem, kind, budget):
    chunk, decoded, textures = kit.native_textures(span, kind)
    clean = textures[0]
    require(clean["name"] == row["texture"], "texture name differs: " + clean["name"])
    require((clean["width"], clean["height"], clean["mips"]) == tuple(row["size"]), "texture size differs")
    planes = kit.read_planes(decoded, chunk, clean)
    original = [p.copy() for p in planes]
    palette = kit.read_palette(decoded, chunk, clean)
    original_palette = palette.copy()
    mud = kit.read_palette(decoded, chunk, textures[1]) if kind == "tset" else None
    original_mud = None if mud is None else mud.copy()
    h, w = planes[0].shape
    cover, weight = hem_shape(hem, w, h)
    scope = cover > 0
    require(scope.any(), "the hem changed no texel")
    alpha = palette[planes[0]][..., 3]
    require((alpha[scope] == 255).all(), "the hem lies on transparent texels")
    legging = kit.hex_rgb(row["legging"])
    target = blend(palette[planes[0]][..., :3], legging, cover, weight)
    if mud is not None:
        wet_legging = kit.hex_rgb(row["legging_wet"])
        wet_target = blend(mud[planes[0]][..., :3], wet_legging, cover, weight)
    else:
        wet_legging, wet_target = None, np.zeros_like(target)

    masks = kit.scope_chain(scope, planes)
    free = kit.free_slots(planes, masks)
    keep_entries = [i for i in range(256) if i not in set(free) and palette[i, 3] == 255]
    wanted = choose_entries(palette, mud, keep_entries, target[scope], wet_target[scope], legging, wet_legging,
                            [int(keep) for _t, _b, keep in hem.get("shadow", [])], budget)
    merged, moved, limit_used = [], 0, 0
    for limit in MERGE_LIMITS:
        if len(free) + len(merged) >= len(wanted):
            break
        more, count = merge_twins(palette, mud, planes, len(wanted) - len(free) - len(merged), limit,
                                  set(free) | set(merged))
        merged += more
        moved += count
        limit_used = limit if more else limit_used
    gone = set(merged)
    keep_entries = [i for i in keep_entries if i not in gone]
    slots = free + merged
    require(len(slots) >= 1 or not wanted or wanted[0][2] != "legging", "no palette entry left for the legging colour")
    added = []
    for (c, m, role), slot in zip(wanted, slots):
        palette[slot, :3] = c
        palette[slot, 3] = 255
        if mud is not None:
            mud[slot, :3] = m
            mud[slot, 3] = 255
        added.append(dict(slot=int(slot), role=role, rgb="#%02X%02X%02X" % tuple(c),
                          wet=None if mud is None else "#%02X%02X%02X" % tuple(m)))
    candidates = keep_entries + [a["slot"] for a in added]

    rows, new_planes = [], []
    changed, t_clean, t_wet = scope, target, wet_target
    for level, plane in enumerate(planes):
        ph, pw = plane.shape
        out = plane.copy()
        pts = np.argwhere(changed)
        out[pts[:, 0], pts[:, 1]] = nearest_pairs(t_clean[pts[:, 0], pts[:, 1]], t_wet[pts[:, 0], pts[:, 1]],
                                                  palette, mud, candidates)
        shipped = original_palette[original[level]]
        quantised = palette[out]
        drift = np.abs(quantised[~changed].astype(np.int64) - shipped[~changed]).max(initial=0)
        require(drift <= limit_used, "a protected texel moved")
        if mud is not None:
            wet_drift = np.abs(mud[out][~changed].astype(np.int64) - original_mud[original[level]][~changed]).max(initial=0)
            require(wet_drift <= limit_used, "a protected wet texel moved")
        rows.append(dict(level=level, width=pw, height=ph, scope_texels=int(changed.sum()),
                         changed_indices=int((out != original[level]).sum())))
        new_planes.append(out)
        if level + 1 < len(planes):
            nh, nw = planes[level + 1].shape
            require((nh * 2, nw * 2) == (ph, pw), "unexpected mip chain")
            t_clean = (quantised[..., :3].reshape(nh, 2, nw, 2, 3).sum(axis=(1, 3)) + 2) // 4
            if mud is not None:
                t_wet = (mud[out][..., :3].reshape(nh, 2, nw, 2, 3).sum(axis=(1, 3)) + 2) // 4
            else:
                t_wet = np.zeros_like(t_clean)
            changed = changed.reshape(nh, 2, nw, 2).any(axis=(1, 3))
    def encode():
        out = kit.write_texture(decoded, chunk, clean, new_planes, palette)
        if mud is not None:
            out = kit.write_texture(out, chunk, textures[1], new_planes, mud)
        return out

    new = encode()
    try:
        fixed_span, fit = rebuild_p8_span(span, new)
    except ScratchError:
        # The stored stream ends with the palette, which must stay compact enough for the retail in-place margin:
        # entries no texel uses any more (freed by the hem) repeat their neighbour, which no texel can show.
        used = set(np.unique(np.concatenate([p.ravel() for p in new_planes])).tolist())
        unused = [i for i in sorted(set(free) | gone) if i > 0 and i not in used]
        if not unused:
            raise ScratchError("2026 pants hem: no unused palette entry left to compact the palette tail")
        for i in unused:
            palette[i] = palette[i - 1]
            if mud is not None:
                mud[i] = mud[i - 1]
        new = encode()
        fixed_span, fit = rebuild_p8_span(span, new)
        fit = dict(fit, unused_entries_repeated=len(unused))
    require(len(fixed_span) == len(span) and fixed_span[:32] == span[:32], "wrapper or allocation changed")
    check, _ = decode_chunk(fixed_span, parse_chunks(fixed_span)[0])
    require(check == new, "native round trip differs")
    return fixed_span, dict(texture=clean["name"], mips=rows, palette_entries_added=added,
                            merged_twin_slots=len(merged), protected_texels_moved=moved, merge_limit=limit_used,
                            level0_scope_texels=int(scope.sum()), fit=fit)


class ScratchError(ValueError):
    """The recompressed stream needs more in-place overlap room than the retail scratch word allows."""


FILL_SLACKS = (0, 4, 8, 32, 64)        # tried in turn when the standard fill cannot keep the retail scratch word


def rebuild_p8_span(span, new):
    """Recompress into the fixed span with the kit compiler's packer; when its stream would need more in-place
    overlap room than the retail scratch word allows, the greedy then the optimal stream is expanded (lossless)
    with each slack of ``FILL_SLACKS`` in turn and the first that keeps the retail wrapper is taken."""
    try:
        fixed_span, fit = rebuild_fixed_span_filled(span, new, encoder="auto")
        return fixed_span, asdict(fit)
    except TxtrError:
        pass
    from nfl_txtr import HEADER, compress_vc_lz, minimum_vc_lz_overlap_scratch
    from nfl_vc_lz_fill import compress_optimal, fill_stream
    chunk = parse_chunks(span)[0]
    _kind, stored, _sys, _vid, _magic, scratch, _r0, _r1 = HEADER.unpack_from(span)
    _old, info = decode_chunk(span, chunk)
    head = span[HEADER.size:HEADER.size + info.consumed_bytes]
    tag, bits = int.from_bytes(head[4:8], "little"), head[8]
    streams = []
    try:
        streams.append(("greedy", compress_vc_lz(new, stream_tag=tag, offset_bits=bits, max_encoded_size=stored,
                                                 max_candidate_comparisons=50_000_000, verify_roundtrip=True)[0]))
    except TxtrError:
        pass
    streams.append(("optimal", compress_optimal(new, stream_tag=tag, offset_bits=bits)))
    for name, stream in streams:
        if len(stream) > stored:
            continue
        for slack in FILL_SLACKS:
            filled, expanded = fill_stream(stream, new, stored, slack=min(slack, scratch))
            padding = stored - len(filled)
            need = minimum_vc_lz_overlap_scratch(filled, stored, len(new))
            if padding > scratch or need > scratch:
                continue
            out = span[:HEADER.size] + filled + bytes(padding)
            back, binfo = decode_chunk(out, chunk)
            require(back == new and binfo.consumed_bytes == len(filled), "filled span failed its decode check")
            return out, dict(encoder=name, slack=slack, compressed_bytes=len(stream), filled_bytes=len(filled),
                             padding_bytes=padding, matches_expanded=expanded, scratch_bytes=scratch,
                             exact_minimum_scratch=need)
    raise ScratchError("2026 pants hem: the texture cannot keep the retail loader scratch allowance")


# -- bump relief -----------------------------------------------------------------------------------------------------

def _argb(span):
    chunks = parse_chunks(span)
    require(len(chunks) == 1 and chunks[0].end_offset == len(span), "expected one complete chunk span")
    chunk = chunks[0]
    require(chunk.kind == "TXTR" and chunk.compressed, "expected a compressed TXTR chunk")
    decoded, _ = decode_chunk(span, chunk)
    texture = parse_texture(decoded, chunk)
    require(texture.format_name == "A8R8G8B8", "expected an A8R8G8B8 bump map")
    return chunk, decoded, texture


def compile_bump(span, row, hem):
    """Fade the pants relief to the flat normal under the hem: the first band keeps ``fade`` of the relief, every
    texel under it none. Stored mips: changed parents are the box average of their four children."""
    chunk, decoded, texture = _argb(span)
    require(texture.name == row["texture"], "texture name differs: " + texture.name)
    require((texture.width, texture.height, texture.mip_levels) == tuple(row["size"]), "bump size differs")
    base = chunk.system_bytes + texture.pixel_offset
    levels, at = [], base
    for i in range(texture.mip_levels):
        lw, lh = max(texture.width >> i, 1), max(texture.height >> i, 1)
        raw = unswizzle_2d(decoded[at:at + lw * lh * 4], lw, lh, 4)
        levels.append(np.frombuffer(raw, np.uint8).reshape(lh, lw, 4).astype(np.int64))
        at += lw * lh * 4
    h, w = levels[0].shape[:2]
    x0, y0, x1, y1 = hem.get("box", (0, 0, w, h))
    points = hem["points"]
    flat_from = float(hem["bump_flat_from"])
    cover = coverage(below(points, 0.0, y1, x0, x1), w, h)
    deep = coverage(below(points, flat_from, y1, x0, x1), w, h)
    # relief kept in 1/(16*100): outside 100 %, in the fade band ``fade`` %, under it 0
    fade = int(hem["bump_fade"])
    lose = (cover - deep) * (100 - fade) + deep * 100
    flat = np.array([FLAT[2], FLAT[1], FLAT[0], 255], np.int64)       # stored B, G, R, A
    out0 = (levels[0] * (FULL * 100 - lose)[..., None] + flat[None, None, :] * lose[..., None] + FULL * 50) // (FULL * 100)
    out0[..., 3] = levels[0][..., 3]
    changed = np.any(out0 != levels[0], axis=2)
    require(changed.any(), "the bump fade changed no texel")
    new_levels, scope, rows = [out0], changed, []
    rows.append(dict(level=0, changed_texels=int(changed.sum())))
    for i in range(1, len(levels)):
        lh, lw = levels[i].shape[:2]
        parent = scope.reshape(lh, 2, lw, 2).any(axis=(1, 3))
        avg = (new_levels[-1].reshape(lh, 2, lw, 2, 4).sum(axis=(1, 3)) + 2) // 4
        level = np.where(parent[..., None], avg, levels[i])
        new_levels.append(level)
        scope = parent
        rows.append(dict(level=i, changed_texels=int(np.any(level != levels[i], axis=2).sum())))
    new = bytearray(decoded)
    at = base
    for level in new_levels:
        lh, lw = level.shape[:2]
        new[at:at + lw * lh * 4] = swizzle_2d(np.ascontiguousarray(level, np.uint8).tobytes(), lw, lh, 4)
        at += lw * lh * 4
    new = bytes(new)
    fixed_span, fit = rebuild_bump_span(span, chunk, new)
    require(len(fixed_span) == len(span) and fixed_span[:32] == span[:32], "wrapper or allocation changed")
    check, _ = decode_chunk(fixed_span, parse_chunks(fixed_span)[0])
    require(check == new, "native round trip differs")
    return fixed_span, dict(texture=texture.name, mips=rows, fit=fit)


def rebuild_bump_span(span, chunk, new):
    """Recompress a bump body into its fixed span the way the Studio's bump writer does: the retail in-place
    loader's scratch word stays exact, so a stream that would need more tail room is expanded (lossless) into the
    stored span with eight bytes of slack."""
    from nfl_txtr import HEADER, minimum_vc_lz_overlap_scratch, rebuild_compressed_chunk_fixed_span
    from nfl_vc_lz_fill import fill_stream
    rebuilt, info = rebuild_compressed_chunk_fixed_span(span, new)
    require(len(rebuilt) == len(span), "span size changed")
    encoded = rebuilt[HEADER.size:HEADER.size + info.recompressed_bytes]
    scratch = HEADER.unpack_from(span)[5]
    if (chunk.stored_size - len(encoded) > scratch
            or minimum_vc_lz_overlap_scratch(encoded, chunk.stored_size, len(new)) > scratch):
        encoded, _ = fill_stream(encoded, new, chunk.stored_size, slack=min(scratch, 8))
    require(chunk.stored_size - len(encoded) <= scratch
            and minimum_vc_lz_overlap_scratch(encoded, chunk.stored_size, len(new)) <= scratch,
            "the bump map cannot keep the retail loader scratch allowance")
    out = span[:HEADER.size] + encoded + bytes(chunk.stored_size - len(encoded))
    return out, dict(recompressed_bytes=len(encoded), zero_padding_bytes=chunk.stored_size - len(encoded),
                     overlap_scratch_bytes=scratch)


# -- kit packages ----------------------------------------------------------------------------------------------------

def compile_row(span, row, document, raw, cache=None):
    """Compile one pinned texture. ``cache`` (one build) reuses the output of an identical span compiled with the
    same parameters: kits of one club often share their retail bump map."""
    if row["kind"] == "pants":
        sock = kit._chunk_for(raw, int(row["socks_chunk"]))
        if sha(raw[sock.offset:sock.end_offset]) != row["socks_sha256"]:
            return None, "socks"
    key = (row["kind"], row["texture"], sha(span), row.get("legging"), row.get("legging_wet"))
    if cache is not None and key in cache:
        return cache[key]
    out = _compile_row(span, row, document)
    if cache is not None:
        cache[key] = out
    return out


def _compile_row(span, row, document):
    hems = document["hem"]
    if row["kind"] == "pants":
        return compile_p8(span, row, hems["pants"], "tset")
    if row["kind"] == "splayer":
        return compile_p8(span, row, hems["splayer"], "txtr")
    return compile_bump(span, row, hems["pants"])


def compile_resource(selector, raw, *, strict=True, document=None, cache=None):
    """Compile every pinned texture of one kit package; refuses partial or unknown inputs when strict."""
    document = document or spec()
    rows = [r for r in document["textures"] if r["selector"] == selector]
    require(rows, "no entries for " + selector)
    states = []
    for row in rows:
        chunk = kit._chunk_for(raw, row["chunk"])
        span = raw[chunk.offset:chunk.end_offset]
        layout_ok = (len(raw), chunk.offset, len(span)) == (row["resource_size"], row["offset"], row["length"])
        digest = sha(span) if layout_ok else None
        states.append((row, chunk, span, "before" if digest == row["before_sha256"]
                       else "after" if digest == row["after_sha256"] else "other"))
    kinds = {s[3] for s in states}
    if kinds == {"after"}:
        return [], dict(selector=selector, state="applied", changed_bytes=0, parts=[], skipped_textures=[])
    if strict:
        require(kinds == {"before"}, selector + ": unknown or partially repaired input hashes")
    elif kinds == {"other"}:
        return [], dict(selector=selector, state="other_uniform", changed_bytes=0, parts=[],
                        skipped_textures=[r["chunk"] for r, *_ in states])
    replacements, parts, skipped = [], [], []
    for row, chunk, span, state in states:
        if state != "before":
            if state == "other":
                skipped.append(row["chunk"])
            continue
        new, detail = compile_row(span, row, document, raw, cache)
        if new is None:
            # the kit's socks are not the pinned SOFTDRINK socks (a user's recipe): its pants keep their art
            require(not strict, selector + ": socks differ from their pin")
            skipped.append(row["chunk"])
            continue
        require(sha(new) == row["after_sha256"], selector + ": Studio compile differs from its output pin")
        replacements.append((chunk.offset, new))
        parts.append(dict(selector=selector, chunk_index=chunk.index, offset=chunk.offset, length=len(new),
                          before_sha256=sha(span), after_sha256=sha(new),
                          changed_bytes=sum(a != b for a, b in zip(span, new)), **detail))
    return replacements, dict(selector=selector, state="applied", skipped_textures=skipped,
                              changed_bytes=sum(p["changed_bytes"] for p in parts), parts=parts)


def selectors(document=None):
    document = document or spec()
    return sorted({r["selector"] for r in document["textures"]})


def apply_to_image(path, *, strict=False, document=None):
    """Studio uniform finish pass (after the uf3 kit finish): only the pinned kit chunk spans are written."""
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
        plans, cache = [], {}
        for selector in wanted:
            entries = by_name.get(selector + ".IFF", [])
            require(len(entries) == 1, selector + " kit package absent or duplicated")
            entry = entries[0]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            replacements, receipt = compile_resource(selector, raw, strict=strict, document=document, cache=cache)
            plans.append((entry, replacements, receipt))
        if {p[2]["state"] for p in plans} == {"other_uniform"}:
            return dict(state="other_uniform", written_spans=0, written_bytes=0, changed_bytes=0, kits=[])
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
