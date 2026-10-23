"""Nameplate repairs Noah asked for after the b778 playtest (job uf2, 10/22).

1. Jaguars last names. The 2026 JAX nameplate atlases (12H0 home, 12A0/12H6/12A6 road and Bold City) were
   authored from the retail letter *alpha* masks. The retail 2K5 atlas keeps each letter's counters and its
   one-texel outline in the **colour** structure while the alpha covers the whole cell, so the 2026 atlases are
   filled silhouettes: P, R, O, B, D, A, Q, H, M and N lose their counters and the gold/white fill has no outline.
   The repair reads the retail letter structure from the user's own disc (the same route the b776 Bears/Chiefs
   letters take), recolours it to the kit's colours, keeps a one-texel outline around the fill, makes the counters
   and the plate transparent, and leaves every countour, glyph metric and the NAME chunk exactly as they are.
   Home: white fill with a black outline, the real Jacksonville plate. Road and Bold City: black fill with a black
   outline (a black glyph at the retail weight) on the white or alabaster jersey.

2. Solid hyphens. The Seahawks' nameplate font draws ``-`` as a hollow rectangle and the 2026 project imported that
   glyph into every Seattle 2026 kit, so SMITH-NJIGBA read with a hollow hyphen. The studio pass below scans every
   kit nameplate (all teams, all uniform slots, classic and Anniversary moment kits) and fills any enclosed hole in
   the hyphen cell with the same palette entry its letters use. It touches only a hyphen whose own layout fits its
   NAME metrics, so the Dallas Arctic Cowboy atlas (whose metrics are repaired by uf1) is left for that job.

Both passes are art-only: no executable code and no XBE space. Exact pins limit the structure rows to the known
SOFTDRINK atlases; a user's own JAX nameplate is left alone.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

from . import nfl2k5_bump_texture_writer as bump
from . import nfl2k5_glyph_fixes_2026 as glyph
from . import nfl2k5_kit_fixes_2026 as kit
from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba

SCHEMA = "nfl2k5_nameplate_fixes_2026/v1"
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_nameplate_fixes_2026.json"
NAME_CHUNK = 44
ATLAS_CHUNK = 43
GLYPHS = "'-ABCDEFGHIJKLMNOPQRSTUVWXYZc"
FILL_THRESHOLD = 0.5


def require(ok, message):
    if not ok:
        raise ValueError("2026 nameplate fixes: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def spec(path=None):
    document = json.loads(Path(path or DATA).read_text(encoding="utf-8"))
    require(document.get("schema") == SCHEMA, "unexpected data schema")
    seen = set()
    for row in document.get("structures", ()):
        require(row["selector"] not in seen, "duplicate structure entry " + repr(row["selector"]))
        seen.add(row["selector"])
        require(row["chunk"] == ATLAS_CHUNK, "structure rows are nameplate atlases")
        for key in ("selector", "retail_selector", "fill", "outline", "retail_fill", "retail_outline",
                    "resource_size", "offset", "length", "before_sha256", "after_sha256", "retail_sha256",
                    "name_sha256", "retail_name_sha256"):
            require(key in row, "structure row lacks " + key)
    hyphen = document.get("hyphen") or {}
    require(hyphen.get("kind", "hyphen_fill") == "hyphen_fill", "unknown hyphen setting")
    return document


def structures(document=None):
    return (document or spec()).get("structures", ())


# -- shared helpers ---------------------------------------------------------------------------------------------------

def _one_txtr(span):
    chunks = parse_chunks(span)
    require(len(chunks) == 1 and chunks[0].end_offset == len(span), "expected one complete chunk span")
    chunk = chunks[0]
    require(chunk.kind == "TXTR" and chunk.compressed, "expected a compressed TXTR chunk")
    decoded, info = decode_chunk(span, chunk)
    return chunk, decoded, info, parse_texture(decoded, chunk)


def _layout(chunk, texture):
    return (chunk.system_bytes, chunk.video_bytes, texture.width, texture.height, texture.mip_levels,
            texture.pixel_offset, texture.palette_offset, texture.packed_format, texture.packed_size)


def _levels(decoded, chunk, texture):
    """Every stored mip as (width, height, video offset, index array). Nameplate atlases are linear P8."""
    require(texture.format_name == "VC_P8_LINEAR", "not a linear P8 nameplate atlas")
    video = decoded[chunk.system_bytes:chunk.system_bytes + chunk.video_bytes]
    offset = texture.pixel_offset
    width, height = texture.width, texture.height
    out = []
    for _level in range(texture.mip_levels):
        count = width * height
        require(offset + count <= texture.palette_offset, "mip chain overlaps the palette")
        indices = np.frombuffer(video[offset:offset + count], np.uint8).reshape(height, width).copy()
        out.append((width, height, offset, indices))
        offset += count
        width //= 2
        height //= 2
    return out


def _palette(decoded, chunk, texture):
    at = chunk.system_bytes + texture.palette_offset
    bgra = np.frombuffer(decoded[at:at + 1024], np.uint8).reshape(256, 4)
    return bgra[:, [2, 1, 0, 3]].astype(np.int64)


def _palette_t(palette, outline, fill):
    """Each palette entry's position (0..1) on the retail outline-to-fill line."""
    o = np.array(outline, np.int64)
    d = np.array(fill, np.int64) - o
    den = int((d * d).sum())
    require(den > 0, "retail outline and fill colours are the same")
    num = np.clip(((palette[:, :3] - o) * d).sum(axis=1), 0, den)
    return num / den


def _dilate(mask):
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    out[1:, 1:] |= mask[:-1, :-1]
    out[:-1, :-1] |= mask[1:, 1:]
    out[1:, :-1] |= mask[:-1, 1:]
    out[:-1, 1:] |= mask[1:, :-1]
    return out


def _enclosed(mask):
    """The connected components of mask that do not touch the array border."""
    height, width = mask.shape
    seen = np.zeros_like(mask, bool)
    out = np.zeros_like(mask, bool)
    for start_y in range(height):
        for start_x in range(width):
            if not mask[start_y, start_x] or seen[start_y, start_x]:
                continue
            stack = [(start_y, start_x)]
            seen[start_y, start_x] = True
            points = []
            touches = False
            while stack:
                y, x = stack.pop()
                points.append((y, x))
                if y in (0, height - 1) or x in (0, width - 1):
                    touches = True
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < height and 0 <= xx < width and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        stack.append((yy, xx))
            if not touches:
                for y, x in points:
                    out[y, x] = True
    return out


def _replace_atlas(span, new):
    fixed, fit = glyph._rebuild(span, new)
    check, _ = decode_chunk(fixed, parse_chunks(fixed)[0])
    require(check == new, "native round trip differs")
    return fixed, fit


# -- 1. Jaguars letters on the retail structure -----------------------------------------------------------------------

def structure_plan(fill, outline):
    """(fill, outline, clear) masks for one glyph cell. ``fill`` is the retail fill mask, ``outline`` every other
    opaque texel. The one-texel band around the fill is the outline; enclosed components (counters) and the rest of
    the opaque plate become clear."""
    band = outline & _dilate(fill)
    inner = _enclosed(outline)
    keep = band & ~inner
    clear = outline & ~keep
    return fill, keep, clear


def compile_structure(span, retail_span, retail_name_span, target_name_span, row):
    """Replace one JAX nameplate atlas with the retail letter structure, recoloured, counters transparent."""
    chunk, decoded, _, texture = _one_txtr(span)
    retail_chunk, retail_decoded, _, retail_texture = _one_txtr(retail_span)
    require(texture.name == retail_texture.name == "names", "not a nameplate atlas: " + texture.name)
    require(_layout(chunk, texture) == _layout(retail_chunk, retail_texture), "kit and retail nameplate layouts differ")
    require(decoded[:chunk.system_bytes] == retail_decoded[:retail_chunk.system_bytes],
            "kit and retail descriptors differ")
    require(sha(target_name_span) == sha(retail_name_span), "kit and retail NAME differ")
    metrics = kit.name_metrics(target_name_span)
    require(kit.layout_fits(kit.atlas_glyph_starts(retail_span), metrics),
            "the retail atlas does not fit the NAME metrics")

    retail_outline = glyph.hex_rgb(row["retail_outline"])
    retail_fill = glyph.hex_rgb(row["retail_fill"])
    outline = glyph.hex_rgb(row["outline"])
    fill = glyph.hex_rgb(row["fill"])
    palette = _palette(retail_decoded, retail_chunk, retail_texture)
    new_palette = glyph.retint_palette(palette, retail_outline, retail_fill, outline, fill)
    position = _palette_t(palette, retail_outline, retail_fill)

    levels = _levels(retail_decoded, retail_chunk, retail_texture)
    width0, height0, _, top = levels[0]
    is_fill = (position[top] >= FILL_THRESHOLD) & (palette[top, 3] > 0)
    opaque = palette[top, 3] > 0
    outline_mask = opaque & ~is_fill
    clear = np.zeros_like(opaque)
    for x, width in metrics:
        x0, x1 = max(0, x), min(width0, x + width)
        if x1 <= x0:
            continue
        fill_mask, keep, cut = structure_plan(is_fill[:, x0:x1], outline_mask[:, x0:x1])
        clear[:, x0:x1] |= cut
    top_new = top.copy()
    top_new[clear] = 0
    levels[0] = (width0, height0, levels[0][2], top_new)

    outline_px = int(row.get("outline_px", 1))
    if outline_px != 1:
        # widen the kept band before the clear above; rows use 1 for now
        raise ValueError("2026 nameplate fixes: only a one-texel outline is supported")

    for level in range(1, len(levels)):
        width, height, offset, indices = levels[level]
        step = 1 << level
        blocks = clear.reshape(height0 // step, step, width0 // step, step).mean(axis=(1, 3)) > 0.5
        indices = indices.copy()
        indices[blocks] = 0
        levels[level] = (width, height, offset, indices)

    new = bytearray(retail_decoded)
    new[retail_chunk.system_bytes + retail_texture.palette_offset:
        retail_chunk.system_bytes + retail_texture.palette_offset + 1024] = \
        new_palette[:, [2, 1, 0, 3]].astype(np.uint8).tobytes()
    for _width, _height, offset, indices in levels:
        base = retail_chunk.system_bytes + offset
        new[base:base + indices.size] = indices.astype(np.uint8).tobytes()
    fixed, fit = _replace_atlas(span, bytes(new))
    return fixed, dict(texture="names", fill=row["fill"], outline=row["outline"],
                       retail_structure_sha256=sha(retail_decoded[:retail_chunk.system_bytes + retail_texture.palette_offset]),
                       fit=asdict(fit))


# -- 2. solid hyphen in every kit --------------------------------------------------------------------------------------

def _fill_index(indices, palette, metrics):
    """The palette entry the letters' interiors use (the fill, not the outline or an anti-aliased edge)."""
    ink = palette[indices, 3] > 0
    inner = ink.copy()
    inner[1:, :] &= ink[:-1, :]
    inner[:-1, :] &= ink[1:, :]
    inner[:, 1:] &= ink[:, :-1]
    inner[:, :-1] &= ink[:, 1:]
    letters = np.zeros_like(inner)
    for index, (x, width) in enumerate(metrics):
        if index in (0, 1):
            continue
        letters[:, x:x + width] = True
    counts = np.bincount(indices[inner & letters], minlength=256)
    for index in np.argsort(-counts):
        if counts[index] == 0:
            break
        if int(palette[index, 3]) >= 250:
            return int(index)
    return None


def _hyphen_holes(indices, palette, x, width, level):
    x0 = x >> level
    x1 = (x + width + (1 << level) - 1) >> level
    x1 = min(x1, indices.shape[1])
    if x1 <= x0:
        return None
    ink = palette[indices[:, x0:x1], 3] > 0
    return _enclosed(~ink)


def hyphen_report(raw):
    """(fill index, [(level, holes)]) for one kit, or None when the kit has no hollow hyphen (or is not a
    nameplate package at all; the pass scans every selector-shaped package and must not refuse a custom one)."""
    chunks = [c for c in parse_chunks(raw) if c.kind == "TXTR" and c.index == ATLAS_CHUNK]
    names = [c for c in parse_chunks(raw) if c.kind == "NAME"]
    if len(chunks) != 1 or len(names) != 1:
        return None
    try:
        span = raw[chunks[0].offset:chunks[0].end_offset]
        atlas_chunk, decoded, _, texture = _one_txtr(span)
    except (ValueError, IndexError, struct.error):
        return None
    if texture.name != "names" or texture.format_name != "VC_P8_LINEAR":
        return None
    name_span = raw[names[0].offset:names[0].end_offset]
    try:
        metrics = kit.name_metrics(name_span)
        starts = kit.atlas_glyph_starts(span)
        levels = _levels(decoded, atlas_chunk, texture)
        palette = _palette(decoded, atlas_chunk, texture)
    except (ValueError, IndexError, struct.error):
        return None
    if len(metrics) != 29 or not kit.layout_fits(starts, metrics):
        return None
    x, width = metrics[1]
    fill = _fill_index(levels[0][3], palette, metrics)
    found = []
    for level, (width_l, height_l, _offset, indices) in enumerate(levels):
        holes = _hyphen_holes(indices, palette, x, width, level)
        if holes is not None and holes.any():
            found.append((level, int(holes.sum())))
    if not found:
        return None
    require(fill is not None, "the letters have no opaque fill colour")
    return fill, found


def _chunk_atlas(raw):
    chunks = [c for c in parse_chunks(raw) if c.kind == "TXTR" and c.index == ATLAS_CHUNK]
    require(len(chunks) == 1, "expected one nameplate atlas chunk")
    chunk = chunks[0]
    return raw[chunk.offset:chunk.end_offset]


def compile_hyphen(raw):
    """Fill every enclosed hole in the hyphen cell with the letters' fill palette entry."""
    report = hyphen_report(raw)
    if report is None:
        return None, dict(state="solid")
    fill, found = report
    atlas_chunk, decoded, _, texture = _one_txtr(_chunk_atlas(raw))
    names = [c for c in parse_chunks(raw) if c.kind == "NAME"]
    metrics = kit.name_metrics(raw[names[0].offset:names[0].end_offset])
    x, width = metrics[1]
    levels = _levels(decoded, atlas_chunk, texture)
    palette = _palette(decoded, atlas_chunk, texture)
    video = bytearray(decoded[atlas_chunk.system_bytes:atlas_chunk.system_bytes + atlas_chunk.video_bytes])
    for level, (_width, _height, offset, indices) in enumerate(levels):
        holes = _hyphen_holes(indices, palette, x, width, level)
        if holes is None or not holes.any():
            continue
        indices = indices.copy()
        x0 = x >> level
        indices[:, x0:x0 + holes.shape[1]][holes] = fill
        video[offset:offset + indices.size] = indices.astype(np.uint8).tobytes()
    new = decoded[:atlas_chunk.system_bytes] + bytes(video) + decoded[atlas_chunk.system_bytes + atlas_chunk.video_bytes:]
    fixed, fit = _replace_atlas(_chunk_atlas(raw), new)
    return fixed, dict(state="filled", fill_index=fill, fill=palette[fill][:3].tolist(), holes=found,
                       fit=asdict(fit))


# -- image pass --------------------------------------------------------------------------------------------------------

def _read_kits(path, wanted):
    with bump._Image.open(Path(path), writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        out = {}
        for selector in wanted:
            entries = by_name.get(selector + ".IFF", [])
            if len(entries) == 1:
                out[selector] = image.read_segments(index.sub_extents(entries[0], 0, entries[0].size))
        return out


def _candidate_selectors(by_name):
    found = []
    for code in range(100):
        for side in "HA":
            for style in range(256):
                selector = "%02d%s%d" % (code, side, style)
                if selector + ".IFF" in by_name:
                    found.append(selector)
    return sorted(set(found))


def _compile_package(selector, raw, document, retail_kits, strict):
    rows = {row["selector"]: row for row in structures(document)}
    replacements = []
    detail = dict(selector=selector, state="applied")
    row = rows.get(selector)
    if row is not None:
        chunks = [c for c in parse_chunks(raw) if c.kind == "TXTR" and c.index == ATLAS_CHUNK]
        names = [c for c in parse_chunks(raw) if c.kind == "NAME"]
        require(len(chunks) == 1 and len(names) == 1, selector + ": expected one nameplate atlas and NAME")
        chunk = chunks[0]
        name_chunk = names[0]
        span = raw[chunk.offset:chunk.end_offset]
        name_span = raw[name_chunk.offset:name_chunk.end_offset]
        digest = sha(span)
        if digest == row["after_sha256"]:
            detail.update(structure="applied", changed_bytes=0)
        elif digest != row["before_sha256"]:
            require(not strict, selector + ": the Jaguars nameplate is not the pinned input")
            detail.update(structure="other_uniform", changed_bytes=0)
        else:
            retail_raw = (retail_kits or {}).get(row["retail_selector"])
            if retail_raw is None:
                require(not strict, selector + ": the retail nameplate donor is absent")
                detail.update(structure="no_donor", changed_bytes=0)
            else:
                retail_chunk = [c for c in parse_chunks(retail_raw)
                                if c.kind == "TXTR" and c.index == ATLAS_CHUNK][0]
                retail_span = retail_raw[retail_chunk.offset:retail_chunk.end_offset]
                retail_name = [c for c in parse_chunks(retail_raw) if c.kind == "NAME"][0]
                retail_name_span = retail_raw[retail_name.offset:retail_name.end_offset]
                require(sha(retail_span) == row["retail_sha256"], selector + ": the retail nameplate differs from its pin")
                require(sha(name_span) == row["name_sha256"], selector + ": the NAME differs from its pin")
                require(sha(retail_name_span) == row["retail_name_sha256"],
                        selector + ": the retail NAME differs from its pin")
                fixed, structure = compile_structure(span, retail_span, retail_name_span, name_span, row)
                require(sha(fixed) == row["after_sha256"], selector + ": Studio compile differs from its output pin")
                replacements.append((chunk.offset, fixed))
                detail.update(structure="applied", changed_bytes=sum(a != b for a, b in zip(span, fixed)),
                              **{k: v for k, v in structure.items() if k != "fit"})
        if detail["structure"] == "applied":
            detail["hyphen"] = "covered by the structure"
            return replacements, detail
    fixed, hyphen = compile_hyphen(raw)
    if fixed is not None:
        chunk = [c for c in parse_chunks(raw) if c.kind == "TXTR" and c.index == ATLAS_CHUNK][0]
        replacements.append((chunk.offset, fixed))
        detail["changed_bytes"] = detail.get("changed_bytes", 0) + sum(
            a != b for a, b in zip(raw[chunk.offset:chunk.end_offset], fixed))
    detail["hyphen"] = hyphen["state"]
    return replacements, detail


def apply_to_image(path, retail=None, *, strict=False, document=None):
    """Studio uniform finish pass, after the Anniversary moment kits. ``retail`` is the retail disc (path or
    callable) the Jaguars letter structure is read from; without it the pinned structure rows are skipped."""
    document = document or spec()
    try:
        with bump._Image.open(Path(path), writable=False) as source:
            index = bump._parsed_index(source)
            by_name = {}
            for entry in index.entries:
                by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
    except (ValueError, OSError):
        if strict:
            raise
        return dict(state="other_image", written_spans=0, written_bytes=0, changed_bytes=0,
                    structures=[], hyphens=[], skipped=[])
    selectors = _candidate_selectors(by_name)
    wanted = {row["selector"] for row in structures(document)}
    if not strict and wanted and not wanted <= {s + ".IFF" for s in selectors}:
        return dict(state="other_uniform", written_spans=0, written_bytes=0, changed_bytes=0,
                    structures=[], hyphens=[], skipped=[])
    donors = sorted({row["retail_selector"] for row in structures(document)})
    retail_kits = None
    if donors and retail is not None:
        retail_path = retail() if callable(retail) else retail
        retail_kits = _read_kits(retail_path, donors)
    plans = []
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        for selector in selectors:
            entries = by_name[selector + ".IFF"]
            if len(entries) != 1:
                continue
            entry = entries[0]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            replacements, detail = _compile_package(selector, raw, document, retail_kits, strict)
            plans.append((entry, replacements, detail))
        written = written_bytes = 0
        for entry, replacements, detail in plans:
            for offset, data in replacements:
                segments = index.sub_extents(entry, offset, len(data))
                image.write_segments(segments, data)
                require(image.read_segments(segments) == data, "written span read-back differs")
                written += 1
                written_bytes += len(data)
    result = dict(state="applied", written_spans=written, written_bytes=written_bytes,
                  changed_bytes=sum(p[2].get("changed_bytes", 0) for p in plans),
                  structures=[p[2] for p in plans if p[2].get("structure")],
                  hyphens=[p[2] for p in plans if p[2].get("hyphen") == "filled"],
                  hyphen_kits=sum(1 for p in plans if p[2].get("hyphen") == "filled"),
                  skipped=[p[2]["selector"] for p in plans if p[2].get("structure") in
                           ("other_uniform", "no_donor")])
    return result
