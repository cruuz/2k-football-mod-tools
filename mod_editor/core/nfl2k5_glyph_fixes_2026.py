"""Repair two SOFTDRINK uniform font defects Noah found in the b775 playtest (b776 job fn2).

1. Nameplate letters (``names``, chunk 43, a 1024x32 linear P8 strip). The 2026 Bears (and Chiefs) atlases were
   authored from the retail glyph silhouettes with an outline cut INSIDE them (about 1.6 to 1.9 texels of a 24 texel
   cap). The retail letters are 4 to 13 texels wide with 2 to 3 texel strokes, so the cut ate them: the I kept no
   fill at all (``W R GHT`` on #58 WRIGHT), the W/M/N/V counters and the small ``c`` opening closed, and the Bears
   road plate drew a white and grey-blue ring that reads as boxes on the white jersey. The repair keeps every
   texel's retail STRUCTURE (which texel is letter fill, which is its one-texel outline, which is clear, at every
   stored mip) and gives it the kit's own colours: the retail palette is re-tinted along its outline-to-fill line
   (exact integers), so the retail anti-aliasing survives. The structure is read from the user's own retail disc at
   build time; no retail pixels ship with the Studio. The glyph metrics (NAME chunk) already equal retail.

2. ku1 (b776): the 2026 Chiefs jersey and shoulder digits (``digit_retint``) are the retail 2K5 Chiefs digits, read
   from the user's own disc like the letters and re-tinted to the 2026 colours (Noah: the 2K5 font is the Chiefs'
   font). No retail pixels ship.

3. Jersey and shoulder digits from authored PNG art (``digit_png``): the 2026 Titans 7 (``data/nfl2k5_teams_2026/
   TEN.json`` glyph_shapes, redrawn from club photographs). The PNG is the team-art pipeline's output for the new
   shape; it goes through the Studio's own digit preparation and fixed-span fit (As authored registration), the
   same route a project edit takes, onto the pinned kit span.

4. b81-uniforms batch 4 (Noah 11/19: "Jags road nameplate and all nameplates should match real ones"): nameplate
   letter strips redrawn to this season's measured lettering, from authored PNG art (``names_png``: the 1024x32 strip
   of chunk 43, level 0 exactly the PNG, the smaller levels area averages of it whose clear texels keep the letters'
   colour) with the glyph widths that go with them (``name_widths``: the 29 width halves of the NAME chunk 44 pairs;
   the atlas offsets stay). The rows ride in the b81-uniforms digit document and are pinned to the strip a build holds
   when that step runs (after the nameplate pass).

The Studio runs this after its uniform layers. Exact input and output pins limit it to the known SOFTDRINK spans:
retail kits and textures a user's own recipe replaced are left alone (strict refuses them).
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
from io import BytesIO
import json
from pathlib import Path
import struct

import numpy as np

from . import nfl2k5_bump_texture_writer as bump
from nfl_txtr import TxtrError, decode_chunk, parse_chunks, parse_texture, swizzle_2d
from nfl_vc_lz_fill import rebuild_fixed_span_filled

SCHEMA = "nfl2k5_glyph_fixes_2026/v1"
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_glyph_fixes_2026.json"
ART = ROOT / "data/nfl2k5_glyph_fixes_2026"
#: b81-uniforms (beta 81): digits redrawn against this season's game highlights, pinned to the finished digits of the
#: released v0.9 build and applied as the last uniform step (``apply_digits_b81``). The document names its own art folder.
DATA_B81U = ROOT / "data/nfl2k5_glyph_fixes_2026_b81u.json"
KINDS = ("names_retint", "digit_png", "digit_retint", "names_png", "name_widths")
NAMES_CHUNK = 43
NAME_CHUNK = 44                         # the raw NAME chunk: 29 (atlas offset, glyph width) pairs for ' - A..Z c
NAME_METRICS = slice(0x2C, 0xA0)
NAMES_SIZE = (1024, 32)
NAMES_GRID_STEPS = (1, 2, 4, 8, 16, 32)


def require(ok, message):
    if not ok:
        raise ValueError("2026 glyph fixes: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hex_rgb(text):
    text = text.lstrip("#")
    require(len(text) == 6, "colour must be #RRGGBB")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def spec(path=None):
    document = json.loads(Path(path or DATA).read_text(encoding="utf-8"))
    require(document.get("schema") == SCHEMA, "unexpected data schema")
    seen = set()
    for row in document["textures"]:
        key = (row["selector"], row["chunk"])
        require(key not in seen, "duplicate texture entry " + repr(key))
        seen.add(key)
        require(row["kind"] in KINDS, "unknown row kind")
    return document


def art_folder(document):
    """Where a document's authored PNGs live: its own ``art`` folder under ``data`` (a plain folder name), or the
    first document's folder."""
    name = document.get("art")
    if not name:
        return ART
    require(isinstance(name, str) and name == Path(name).name and name.startswith("nfl2k5_glyph_fixes_2026"),
            "unexpected art folder")
    return ROOT / "data" / name


def digits_b81():
    """The b81-uniforms digit document."""
    return spec(DATA_B81U)


def apply_digits_b81(path, *, strict=False):
    """Studio uniform finish pass for the b81-uniforms digits (authored PNGs only, so no retail disc is read)."""
    return apply_to_image(path, None, strict=strict, document=digits_b81())


def _one_txtr(span):
    chunks = parse_chunks(span)
    require(len(chunks) == 1 and chunks[0].end_offset == len(span), "expected one complete chunk span")
    chunk = chunks[0]
    require(chunk.kind == "TXTR" and chunk.compressed, "expected a compressed TXTR chunk")
    decoded, info = decode_chunk(span, chunk)
    return chunk, decoded, info, parse_texture(decoded, chunk)


def _rebuild(span, new):
    fixed_span, fit = rebuild_fixed_span_filled(span, new, encoder="auto")
    require(len(fixed_span) == len(span) and fixed_span[:32] == span[:32], "wrapper or allocation changed")
    check, _ = decode_chunk(fixed_span, parse_chunks(fixed_span)[0])
    require(check == new, "native round trip differs")
    return fixed_span, fit


# -- nameplate letters -----------------------------------------------------------------------------------------------

def retint_palette(palette, retail_outline, retail_fill, outline, fill):
    """Each retail entry's position t on the line from the retail outline colour to the retail fill colour (projected,
    clamped to 0..1, exact integers) gives outline + t * (fill - outline). Alpha stays; clear entries take the outline
    colour, so a filtered letter edge fades in its own outline colour (retail's dark grey made a dark fringe)."""
    o0 = np.array(retail_outline, np.int64)
    d = np.array(retail_fill, np.int64) - o0
    den = int((d * d).sum())
    require(den > 0, "retail outline and fill colours are the same")
    rgb = palette[:, :3].astype(np.int64)
    num = np.clip(((rgb - o0) * d).sum(axis=1), 0, den)
    a = np.array(outline, np.int64)
    b = np.array(fill, np.int64)
    out = palette.copy()
    out[:, :3] = (a[None, :] * (den - num)[:, None] + b[None, :] * num[:, None] + den // 2) // den
    clear = palette[:, 3] == 0
    out[clear, :3] = a
    return out


def compile_names(span, retail_span, row, *, name="names", storage="VC_P8_LINEAR"):
    """The kit's nameplate letters on the retail letter structure (see the module notes). ku1 (b776): the same
    retint carries the retail jersey and shoulder digits (``digit_retint``: P8 textures 48..57 and an48..an57)."""
    chunk, decoded, _, texture = _one_txtr(span)
    rchunk, rdecoded, _, rtexture = _one_txtr(retail_span)
    require(texture.name == rtexture.name == name, "not the expected retail texture: " + texture.name)
    require(texture.format_name == rtexture.format_name == storage, "unexpected retail texture storage")
    layout = lambda c, t: (c.system_bytes, c.video_bytes, t.width, t.height, t.mip_levels, t.pixel_offset,
                           t.palette_offset, t.packed_format, t.packed_size)
    require(layout(chunk, texture) == layout(rchunk, rtexture), "kit and retail nameplate layouts differ")
    require(decoded[:chunk.system_bytes] == rdecoded[:rchunk.system_bytes], "kit and retail descriptors differ")
    at = rchunk.system_bytes + rtexture.palette_offset
    bgra = np.frombuffer(rdecoded[at:at + 1024], np.uint8).reshape(256, 4)
    palette = bgra[:, [2, 1, 0, 3]].astype(np.int64)
    new_palette = retint_palette(palette, hex_rgb(row["retail_outline"]), hex_rgb(row["retail_fill"]),
                                 hex_rgb(row["outline"]), hex_rgb(row["fill"]))
    new = bytearray(rdecoded)
    new[at:at + 1024] = np.ascontiguousarray(new_palette[:, [2, 1, 0, 3]], np.uint8).tobytes()
    new = bytes(new)
    fixed_span, fit = _rebuild(span, new)
    return fixed_span, dict(texture=name, retail_structure_sha256=sha(rdecoded[:at]), fit=asdict(fit),
                            fill=row["fill"], outline=row["outline"])


# -- authored digits -------------------------------------------------------------------------------------------------

def compile_digit(span, png_payload):
    """Authored digit PNG -> the pinned digit span, through the Studio's digit preparation and fixed-span fit."""
    from PIL import Image
    from nfl_tset_png_import import decode_rgba_png, palette_bytes
    from nfl_txtr import rebuild_compressed_chunk_fixed_span
    from .nfl2k5_digit_art import fit_digit, registration_mode
    chunk, decoded, info, texture = _one_txtr(span)
    require(texture.format_name == "P8", "digit textures are swizzled P8")
    width, height, rgba = decode_rgba_png(png_payload, (texture.width, texture.height))
    require((width, height) == (texture.width, texture.height), "digit PNG size differs")
    require(registration_mode(png_payload) == "as_authored", "fixed digits are placed As authored")
    sizes = [(max(texture.width >> i, 1), max(texture.height >> i, 1)) for i in range(texture.mip_levels)]
    chain = sum(w * h for w, h in sizes)
    video = decoded[chunk.system_bytes:]
    require(texture.pixel_offset == 0 and chain <= texture.palette_offset, "unexpected digit layout")
    gap = video[chain:texture.palette_offset]

    def candidate(palette, levels):
        require(len(levels) == len(sizes) and sum(len(level) for level in levels) == chain,
                "quantized mip chain differs from the allocation")
        encoded = b"".join(swizzle_2d(level, w, h, 1) for level, (w, h) in zip(levels, sizes))
        rebuilt = encoded + gap + palette_bytes(palette)
        require(len(rebuilt) == chunk.video_bytes, "rebuilt video size differs")
        return decoded[:chunk.system_bytes] + rebuilt

    # As authored placement keeps the PNG's own position; the shipped digit only serves the measurement receipt
    from nfl_live_numbers_nameplate_png_import import decode_levels
    template = Image.frombytes("RGBA", (width, height), decode_levels(decoded, chunk, texture)[0].rgba)
    bounded, _levels, receipt = fit_digit(
        Image.frombytes("RGBA", (width, height), rgba), template, "as_authored", texture.mip_levels,
        lambda _levels, p, i: candidate(p, i), stream_tag=info.stream_tag, offset_bits=info.offset_bits,
        stored_size=chunk.stored_size)
    rebuilt_span, rebuild = rebuild_compressed_chunk_fixed_span(span, bounded.decoded)
    require(len(rebuilt_span) == len(span) and rebuild.loader_in_place_end_guard and
            rebuild.loader_in_place_alias_guard, "fixed-span rebuild contract failed")
    check, _ = decode_chunk(rebuilt_span, parse_chunks(rebuilt_span)[0])
    require(check == bounded.decoded and check[:chunk.system_bytes] == decoded[:chunk.system_bytes],
            "digit round trip differs")
    return rebuilt_span, dict(texture=texture.name, palette_entries=len(bounded.palette),
                              registration=receipt["registration"]["mode"])


# -- authored nameplate letters (b81-uniforms batch 4) ---------------------------------------------------------------

def _names_levels(rgba, count):
    """The stored mip chain of an authored nameplate strip. Level 0 is the strip exactly; each smaller level is the
    alpha-weighted average of its exact footprint of level 0 (coverage kept). A fully clear footprint keeps the colour
    the strip's clear texels carry (the letters' own colour), so a filtered letter edge never fades through black."""
    rgba = np.asarray(rgba, np.uint8)
    height, width = rgba.shape[:2]
    clear = rgba[rgba[..., 3] == 0][:, :3].astype(np.int64)
    if len(clear):
        colours, counts = np.unique(clear, axis=0, return_counts=True)
        clear_rgb = colours[np.lexsort((colours[:, 2], colours[:, 1], colours[:, 0], -counts))[0]]
    else:
        clear_rgb = np.zeros(3, np.int64)
    alpha = rgba[..., 3].astype(np.int64)
    rgb = rgba[..., :3].astype(np.int64)
    levels = [rgba.copy()]
    for level in range(1, count):
        k = 1 << level
        h, w = height // k, width // k
        total = alpha.reshape(h, k, w, k).sum(axis=(1, 3))
        out = np.zeros((h, w, 4), np.int64)
        out[..., 3] = (total + (k * k) // 2) // (k * k)
        for channel in range(3):
            weighted = (rgb[..., channel] * alpha).reshape(h, k, w, k).sum(axis=(1, 3))
            out[..., channel] = np.where(total > 0, (weighted + total // 2) // np.maximum(total, 1), clear_rgb[channel])
        out[out[..., 3] == 0, :3] = clear_rgb
        levels.append(out.astype(np.uint8))
    return levels


def _pack_rgba(rgba):
    v = np.asarray(rgba, np.uint32).reshape(-1, 4)
    return (v[:, 0] << 24) | (v[:, 1] << 16) | (v[:, 2] << 8) | v[:, 3]


def _names_palettes(levels):
    """(palette RGBA, index array per level, grid step) candidates, richest first. Level 0's colours are exact entries
    (by alpha, most used first); the smaller levels' colours follow, a partly clear or blended one rounded to a coarser
    grid only when the entries would run out. Deterministic: integer arithmetic and sorted unique values only."""
    first, counts = np.unique(_pack_rgba(levels[0]), return_counts=True)
    first = first[np.lexsort((first, -counts, first & 0xFF))]
    for step in NAMES_GRID_STEPS:
        mips = []
        for level in levels[1:]:
            q = level.astype(np.int64)
            if step > 1:
                blended = (q[..., 3] > 0) & ~np.isin(_pack_rgba(level), first).reshape(q.shape[:2])
                rounded = np.clip(((q + step // 2) // step) * step, 0, 255)
                rounded[..., 3] = np.where((q[..., 3] == 255) | (q[..., 3] == 0), q[..., 3], np.clip(rounded[..., 3], 1, 254))
                q = np.where(blended[..., None], rounded, q)
            mips.append(q.astype(np.uint8))
        extra = np.setdiff1d(np.unique(np.concatenate([_pack_rgba(m) for m in mips])), first) if mips else \
            np.zeros(0, np.uint32)
        extra = extra[np.lexsort((extra, extra & 0xFF))]
        if len(first) + len(extra) > 256:
            continue
        values = np.concatenate([first, extra]).astype(np.uint32)
        order = np.argsort(values, kind="stable")
        ordered = values[order]
        indices = []
        for level in [levels[0]] + mips:
            packed = _pack_rgba(level)
            at = np.minimum(np.searchsorted(ordered, packed), len(ordered) - 1)
            require(bool((ordered[at] == packed).all()), "a strip colour lost its palette entry")
            indices.append(order[at].astype(np.uint8))
        palette = np.stack([(values >> 24) & 0xFF, (values >> 16) & 0xFF, (values >> 8) & 0xFF, values & 0xFF], axis=1)
        yield palette.astype(np.uint8), indices, step


def names_png_rgba(png_payload):
    """The authored strip of a ``names_png`` row as RGBA (32 rows by 1024)."""
    from PIL import Image
    with Image.open(BytesIO(png_payload)) as image:
        require(image.size == NAMES_SIZE, "the nameplate strip PNG is not 1024 x 32")
        return np.asarray(image.convert("RGBA"), np.uint8).copy()


def names_level0(span):
    """Level 0 of a compiled nameplate strip span as RGBA (what the game's compositor copies letters from)."""
    chunk, decoded, _info, texture = _one_txtr(span)
    require(texture.name == "names" and texture.format_name == "VC_P8_LINEAR", "not a linear nameplate strip")
    at = chunk.system_bytes + texture.palette_offset
    palette = np.frombuffer(decoded[at:at + 1024], np.uint8).reshape(256, 4)[:, [2, 1, 0, 3]]
    start = chunk.system_bytes + texture.pixel_offset
    top = np.frombuffer(decoded[start:start + texture.width * texture.height], np.uint8)
    return palette[top].reshape(texture.height, texture.width, 4)


def compile_names_png(span, png_payload):
    """Authored nameplate strip (1024 x 32 RGBA PNG) -> the pinned chunk 43 span: level 0 is the PNG exactly, the
    smaller levels average it (``_names_levels``), the palette holds level 0's colours exactly; the native format,
    size, mip count, descriptor, wrapper and stored allocation stay. A palette whose stream does not fit the stored
    span is tried again with the smaller levels' blends on a coarser grid."""
    chunk, decoded, _info, texture = _one_txtr(span)
    require(texture.name == "names" and texture.format_name == "VC_P8_LINEAR" and
            (texture.width, texture.height) == NAMES_SIZE, "not a 1024 x 32 linear nameplate strip")
    rgba = names_png_rgba(png_payload)
    levels = _names_levels(rgba, texture.mip_levels)
    video = decoded[chunk.system_bytes:chunk.system_bytes + chunk.video_bytes]
    chain = sum(level.shape[0] * level.shape[1] for level in levels)
    require(texture.pixel_offset + chain <= texture.palette_offset, "the mip chain overlaps the palette")
    last = None
    for palette, indices, step in _names_palettes(levels):
        new_video = bytearray(video)
        at = texture.pixel_offset
        for index in indices:
            new_video[at:at + index.size] = index.tobytes()
            at += index.size
        table = np.zeros((256, 4), np.uint8)
        table[:len(palette)] = palette
        new_video[texture.palette_offset:texture.palette_offset + 1024] = table[:, [2, 1, 0, 3]].tobytes()
        new = decoded[:chunk.system_bytes] + bytes(new_video) + decoded[chunk.system_bytes + chunk.video_bytes:]
        try:
            fixed, fit = _rebuild(span, new)
        except TxtrError as exc:
            last = exc
            continue
        require(bool((names_level0(fixed) == rgba).all()), "the compiled strip differs from the authored strip")
        return fixed, dict(texture="names", palette_entries=int(len(palette)), mip_grid_step=int(step), fit=asdict(fit))
    raise ValueError("2026 glyph fixes: the nameplate strip does not fit its stored span" + (": " + str(last) if last else ""))


def name_widths(name_span):
    """The 29 (atlas offset, glyph width) pairs (' - A..Z c) of one raw NAME chunk span."""
    chunks = parse_chunks(name_span)
    require(len(chunks) == 1 and chunks[0].kind == "NAME" and not chunks[0].compressed and
            chunks[0].end_offset == len(name_span), "expected one raw NAME chunk")
    pairs = struct.unpack_from("<58H", name_span, chunks[0].body_offset + NAME_METRICS.start)
    return list(zip(pairs[0::2], pairs[1::2]))


def compile_name_widths(span, widths):
    """The NAME span with a redrawn strip's 29 glyph widths (each glyph's ink and its letter gap); the atlas offsets
    and every other byte stay. The game's compositor copies each letter at its stored width."""
    require(len(widths) == 29 and all(1 <= int(w) <= 32 for w in widths), "29 glyph widths of 1 to 32 texels")
    pairs = name_widths(span)
    flat = []
    for (offset, _old), width in zip(pairs, widths):
        flat += [offset, int(width)]
    new = bytearray(span)
    struct.pack_into("<58H", new, parse_chunks(span)[0].body_offset + NAME_METRICS.start, *flat)
    require(bytes(new) != span, "the nameplate already has these widths")
    return bytes(new), dict(texture="NAME", widths_changed=sum(int(a[1]) != int(b) for a, b in zip(pairs, widths)))


# -- kit packages ----------------------------------------------------------------------------------------------------

def _chunk_for(raw, index):
    for chunk in parse_chunks(raw):
        if chunk.index == index:
            return chunk
    raise ValueError("2026 glyph fixes: chunk %d absent" % index)


def compile_resource(selector, raw, *, strict=True, document=None, retail_kits=None):
    """Compile every pinned texture of one kit package. ``retail_kits`` maps a retail donor selector to its package
    bytes (the nameplate structure), or is None when no retail disc is available."""
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
        require(kinds <= {"before", "after"}, selector + ": unknown input hashes")
    elif kinds == {"other"}:
        return [], dict(selector=selector, state="other_uniform", changed_bytes=0, parts=[],
                        skipped_textures=[r["chunk"] for r, *_ in states])
    replacements, parts, skipped = [], [], []
    for row, chunk, span, state in states:
        if state != "before":
            if state == "other":
                skipped.append(row["chunk"])
            continue
        if row["kind"] in ("names_retint", "digit_retint"):
            donor_raw = (retail_kits or {}).get(row["retail_selector"])
            if donor_raw is None:
                require(not strict, selector + (": the retail nameplate donor is absent" if row["kind"] == "names_retint"
                                                 else ": the retail digit donor is absent"))
                skipped.append(row["chunk"])
                continue
            donor = _chunk_for(donor_raw, row["chunk"])
            donor_span = donor_raw[donor.offset:donor.end_offset]
            if sha(donor_span) != row["retail_sha256"]:
                require(not strict, selector + (": the retail nameplate differs from its pin" if row["kind"] == "names_retint"
                                                 else ": the retail digit differs from its pin"))
                skipped.append(row["chunk"])
                continue
            if row["kind"] == "names_retint":
                new, detail = compile_names(span, donor_span, row)
            else:
                new, detail = compile_names(span, donor_span, row, name=row["texture"], storage="P8")
        elif row["kind"] == "name_widths":
            new, detail = compile_name_widths(span, row["widths"])
        else:
            payload = (art_folder(document) / row["png"]).read_bytes()
            require(sha(payload) == row["png_sha256"], selector + ": authored " +
                    ("nameplate" if row["kind"] == "names_png" else "digit") + " PNG differs from its pin")
            if row["kind"] == "names_png":
                new, detail = compile_names_png(span, payload)
                detail = {k: v for k, v in detail.items() if k != "fit"}
            else:
                new, detail = compile_digit(span, payload)
        require(sha(new) == row["after_sha256"], selector + ": Studio compile differs from its output pin")
        replacements.append((chunk.offset, new))
        parts.append(dict(selector=selector, chunk_index=chunk.index, offset=chunk.offset, length=len(new),
                          before_sha256=sha(span), after_sha256=sha(new), kind=row["kind"],
                          changed_bytes=sum(a != b for a, b in zip(span, new)), defects=row.get("defects", []),
                          **detail))
    return replacements, dict(selector=selector, state="applied", skipped_textures=skipped,
                              changed_bytes=sum(p["changed_bytes"] for p in parts), parts=parts)


def selectors(document=None):
    return sorted({r["selector"] for r in (document or spec())["textures"]})


def _read_kits(path, wanted):
    """Kit package bytes by selector from one image (read only)."""
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


def apply_to_image(path, retail=None, *, strict=False, document=None):
    """Studio uniform finish pass: only the pinned kit chunk spans are written. ``retail`` is the retail disc (a path,
    or a callable returning one) the nameplate structure is read from; without it those rows are skipped."""
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
    donors = sorted({r["retail_selector"] for r in document["textures"] if r["kind"] in ("names_retint", "digit_retint")})
    retail_kits = None
    if donors and retail is not None:
        retail_path = retail() if callable(retail) else retail
        retail_kits = _read_kits(retail_path, donors)
    kits, written, written_bytes = [], 0, 0
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        plans = []
        for selector in wanted:
            entries = by_name.get(selector + ".IFF", [])
            require(len(entries) == 1, selector + " kit package absent or duplicated")
            entry = entries[0]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            replacements, receipt = compile_resource(selector, raw, strict=strict, document=document,
                                                     retail_kits=retail_kits)
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
    return dict(state="applied", written_spans=written, written_bytes=written_bytes,
                changed_bytes=sum(k["changed_bytes"] for k in kits),
                skipped_kits=[k["selector"] for k in kits if k["state"] == "other_uniform"], kits=kits)
