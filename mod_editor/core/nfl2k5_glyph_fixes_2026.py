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

5. b81-retail-free-art (``digit_derived``): b81u digits that the uniform lane made by editing a glyph the Studio itself
   builds from a retail donor (whole rows and columns repeated or removed, fill strokes grown or thinned with the
   outline rebuilt, an edge ring or an inline recoloured) do not ship as pictures. The row carries the edit as
   operations with their parameters (``derive``); the Studio applies them at build time to the glyph the build holds
   (the retail-derived v0.9 digit, made from the user's own disc) and compiles the result through the same route as
   ``digit_png``. ``rgba_sha256`` pins the derived picture, ``after_sha256`` the compiled span, both unchanged.
   A redraw no operation list rebuilds ships as ``paint``: only the texels that differ from the glyph the build holds
   at that point (row, first column, the new RGBA values); a texel equal to that glyph is never shipped. The same
   holds for a nameplate strip (``names_derived``, on the strip the build holds after the nameplate pass).

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
from nfl_txtr import TxtrError, decode_chunk, parse_chunks, parse_texture, swizzle_2d, texture_to_rgba
from nfl_vc_lz_fill import rebuild_fixed_span_filled

SCHEMA = "nfl2k5_glyph_fixes_2026/v1"
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_glyph_fixes_2026.json"
ART = ROOT / "data/nfl2k5_glyph_fixes_2026"
#: b81-uniforms (beta 81): digits redrawn against this season's game highlights, pinned to the finished digits of the
#: released v0.9 build and applied as the last uniform step (``apply_digits_b81``). The document names its own art folder.
DATA_B81U = ROOT / "data/nfl2k5_glyph_fixes_2026_b81u.json"
KINDS = ("names_retint", "digit_png", "digit_retint", "names_png", "name_widths", "digit_derived", "names_derived")
DERIVE_OPS = ("remap", "embolden", "edge", "inline_fill", "inline_dark", "recolour", "paint", "thin_letters", "clear_rgb",
              "hidden_from_base", "keep")
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
    from nfl_tset_png_import import decode_rgba_png
    from .nfl2k5_digit_art import registration_mode
    chunk, decoded, info, texture = _one_txtr(span)
    width, height, rgba = decode_rgba_png(png_payload, (texture.width, texture.height))
    require((width, height) == (texture.width, texture.height), "digit PNG size differs")
    require(registration_mode(png_payload) == "as_authored", "fixed digits are placed As authored")
    return compile_digit_rgba(span, rgba)


def compile_digit_rgba(span, rgba):
    """A digit picture (level-0 RGBA bytes, placed As authored) -> the pinned digit span (``compile_digit``'s route)."""
    from PIL import Image
    from nfl_tset_png_import import palette_bytes
    from nfl_txtr import rebuild_compressed_chunk_fixed_span
    from .nfl2k5_digit_art import fit_digit
    chunk, decoded, info, texture = _one_txtr(span)
    require(texture.format_name == "P8", "digit textures are swizzled P8")
    width, height = texture.width, texture.height
    rgba = bytes(rgba)
    require(len(rgba) == width * height * 4, "digit picture size differs")
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


# -- digits derived at build time from the glyph the build holds (b81-retail-free-art) --------------------------------
# The uniform lane's edits as operations (tools/b81_uniforms/glyph_derive.py finds their parameters): BATCH5 reshape.py
# (whole rows and columns repeated or removed, then placed: ``remap``), BATCH5 embolden.py (``embolden``), BATCH6
# edge6.py (``edge``), BATCH5 inline3.py / DECISIONS tb_four.py (``inline_fill``) and tb_home_inline.py (``inline_dark``).

def _grow(mask, n=1, eight=False):
    m = np.asarray(mask, bool)
    for _ in range(n):
        o = m.copy()
        o[1:] |= m[:-1]
        o[:-1] |= m[1:]
        o[:, 1:] |= m[:, :-1]
        o[:, :-1] |= m[:, 1:]
        if eight:
            o[1:, 1:] |= m[:-1, :-1]
            o[1:, :-1] |= m[:-1, 1:]
            o[:-1, 1:] |= m[1:, :-1]
            o[:-1, :-1] |= m[1:, 1:]
        m = o
    return m


def _shrink(mask, n=1):
    m = np.asarray(mask, bool)
    for _ in range(n):
        o = m.copy()
        o[1:] &= m[:-1]
        o[0] = False
        o[:-1] &= m[1:]
        o[-1] = False
        o[:, 1:] &= m[:, :-1]
        o[:, 0] = False
        o[:, :-1] &= m[:, 1:]
        o[:, -1] = False
        m = o
    return m


def _taxicab_depth(mask):
    """Taxicab distance of each texel of ``mask`` to the nearest texel outside it (0 outside)."""
    depth = np.zeros(mask.shape, np.int64)
    current = np.asarray(mask, bool)
    k = 0
    while current.any():
        k += 1
        depth[current] = k
        current = _shrink(current)
    return depth


def _colour(text):
    return None if text is None else np.array(hex_rgb(text), np.int64)


def derive_digit(before_rgba, ops):
    """The digit picture an op list makes from the glyph the build holds (level-0 RGBA, uint8 h x w x 4)."""
    a = np.array(before_rgba, np.uint8, copy=True)
    for op in ops:
        kind = op["op"]
        require(kind in DERIVE_OPS, "unknown digit operation " + repr(kind))
        if kind == "remap":
            pad = np.zeros((a.shape[0] + 1, a.shape[1] + 1, 4), np.uint8)
            pad[:a.shape[0], :a.shape[1]] = a
            rows = np.array([r if r >= 0 else a.shape[0] for r in op["rows"]])
            cols = np.array([c if c >= 0 else a.shape[1] for c in op["cols"]])
            require(rows.max() <= a.shape[0] and cols.max() <= a.shape[1], "remap outside the glyph")
            a = pad[rows][:, cols]
        elif kind == "embolden":
            b = np.pad(a.astype(np.int64), ((8, 8), (8, 8), (0, 0)))
            fill_c, out_c, k = _colour(op["fill"]), _colour(op["outline"]), int(op["k"])
            glyph = b[..., 3] >= 128
            fill = glyph & (np.abs(b[..., :3] - fill_c).max(-1) <= 40)
            nf = fill.copy() if k == 0 else _grow(fill, k) if k > 0 else _shrink(fill, -k)
            if op["extra"] and k > 0:
                nf = nf | np.roll(nf, 1, axis=1) | np.roll(nf, 1, axis=0)
            elif op["extra"]:
                nf = nf & np.roll(nf, -1, axis=1) & np.roll(nf, -1, axis=0)
            ng = _grow(nf, int(op["ring"])) if op["ring"] else nf
            out = np.zeros_like(b)
            out[ng, 3] = 255
            out[ng, :3] = out_c if out_c is not None else fill_c
            out[nf, :3] = fill_c
            a = out.astype(np.uint8)
        elif kind == "edge":
            opaque = a[..., 3] >= 128
            depth = _taxicab_depth(np.pad(opaque, 1))[1:-1, 1:-1]
            is_edge = opaque & (np.abs(a[..., :3].astype(np.int64) - _colour(op["edge"])).sum(-1) <= 24)
            a[is_edge & (depth > int(op["keep"])), :3] = _colour(op["fill"])
        elif kind == "recolour":
            # exact colour swaps (a club colour corrected): every visible texel of a listed colour takes the new one;
            # b81-retail-free-art: with ``hidden`` the colour stored under clear texels moves too (as a picture editor
            # swaps it), so no texel of the glyph's clear surround is listed
            rgb = a[..., :3].copy()
            seen = np.ones(a.shape[:2], bool) if op.get("hidden") else a[..., 3] > 0
            for old, new in op["pairs"]:
                hit = seen & (rgb == _colour(old)).all(-1)
                a[hit, :3] = _colour(new)
        elif kind == "thin_letters":
            a = thin_letters(a, op)
        elif kind == "hidden_from_base":
            # b81-retail-free-art (ruling 2): the colour under every clear texel is the glyph's own colour at that texel
            # (as a picture editor leaves it), by rule
            base0 = np.asarray(before_rgba, np.uint8)
            require(base0.shape == a.shape, "hidden_from_base needs the glyph's own size")
            clear = a[..., 3] == 0
            a[clear, :3] = base0[clear, :3]
        elif kind == "keep":
            # b81-retail-free-art (ruling 2): texels the edit leaves as the glyph the build holds had them, by place only
            # ([row, first column, count]): no texel value is stored
            base0 = np.asarray(before_rgba, np.uint8)
            require(base0.shape == a.shape, "keep needs the glyph's own size")
            for y, x0, count in op["runs"]:
                require(0 <= y < a.shape[0] and 0 <= x0 and count > 0 and x0 + count <= a.shape[1], "keep outside the glyph")
                a[y, x0:x0 + count] = base0[y, x0:x0 + count]
        elif kind == "clear_rgb":
            # b81-retail-free-art: the colour stored under every clear texel (alpha 0), by rule, never by listing them
            a[a[..., 3] == 0, :3] = _colour(op["colour"])
        elif kind == "paint":
            # the texels that differ from the glyph the build holds: [row, first column, "RRGGBBAA" per texel]
            for y, x0, values in op["runs"]:
                count = len(values) // 8
                require(len(values) == 8 * count and count and 0 <= y < a.shape[0] and 0 <= x0 and
                        x0 + count <= a.shape[1], "paint run outside the picture")
                a[y, x0:x0 + count] = np.frombuffer(bytes.fromhex(values), np.uint8).reshape(count, 4)
        elif kind == "inline_fill":
            opaque = a[..., 3] == 255
            fill = opaque & (np.abs(a[..., :3].astype(np.int64) - _colour(op["fill"])).max(-1) <= 24)
            a[fill & _grow(~fill, 1, eight=True), :3] = _colour(op["colour"])
        else:
            opaque = a[..., 3] == 255
            soft = (a[..., 3] > 0) & ~opaque
            dark = opaque & (a[..., :3].max(-1) < 0x60)
            inner = opaque & ~dark
            ring = inner & _grow(dark | soft | (a[..., 3] == 0), 1, eight=True)
            a[ring, :3] = _colour(op["colour"])
            a[inner & ~ring, :3] = 255
    return a


# -- the Jaguars road strip (Noah's decision 8, "Thin them to match"): work/fix/DECISIONS/tools/jax_thin.py as an
# instruction. Each letter keeps the silhouette of the strip the build holds and comes down to bands 2 texels across and
# 2 rows; the per-letter rules are the lane's. The only float steps are basic IEEE operations; the diagonal weights
# (jax_thin's arctan2/cos) are stored per letter as float64 hex, so no transcendental function runs at build time.

_THIN_GLYPHS = "'-ABCDEFGHIJKLMNOPQRSTUVWXYZc"


def _silhouette(m):
    rows = np.zeros_like(m)
    for y in range(m.shape[0]):
        xs = np.flatnonzero(m[y])
        if len(xs):
            rows[y, xs[0]:xs[-1] + 1] = True
    cols = np.zeros_like(m)
    for x in range(m.shape[1]):
        ys = np.flatnonzero(m[:, x])
        if len(ys):
            cols[ys[0]:ys[-1] + 1, x] = True
    return rows & cols


def _bands(S, s, b):
    H, W = S.shape
    L = np.zeros_like(S); R = np.zeros_like(S); T = np.zeros_like(S); B = np.zeros_like(S)
    for y in range(H):
        xs = np.flatnonzero(S[y])
        if len(xs):
            L[y, xs[0]:xs[0] + s] = True
            R[y, max(0, xs[-1] - s + 1):xs[-1] + 1] = True
    for x in range(W):
        ys = np.flatnonzero(S[:, x])
        if len(ys):
            T[ys[0]:ys[0] + b, x] = True
            B[max(0, ys[-1] - b + 1):ys[-1] + 1, x] = True
    return L & S, R & S, T & S, B & S


def _straight(S, side, s):
    H, W = S.shape
    edges = []
    for y in range(6, H - 6):
        xs = np.flatnonzero(S[y])
        if len(xs):
            edges.append(xs[0] if side == "L" else xs[-1])
    e = sorted(edges)
    k = len(e)
    e = e[k // 2] if k % 2 else (e[k // 2 - 1] + e[k // 2]) / 2      # np.median, exactly
    e = int(e)
    out = np.zeros_like(S)
    if side == "L":
        out[:, e:e + s] = True
    else:
        out[:, e - s + 1:e + 1] = True
    return out & S


def _rows(S, y0, y1):
    out = np.zeros_like(S)
    out[max(0, y0):max(0, y1)] = True
    return out


def _hbar(S, y0, b, x0=None, x1=None):
    out = np.zeros_like(S)
    out[y0:y0 + b, (x0 or 0):(x1 if x1 is not None else S.shape[1])] = True
    return out & S


def _diag(S, s, xa, ya, xb, yb, t):
    H, W = S.shape
    n = max(s, int(round(t)))
    out = np.zeros_like(S)
    for y in range(H):
        yc = y + 0.5
        if not (min(ya, yb) <= yc <= max(ya, yb)):
            continue
        x0 = int(round(xa + (yc - ya) * (xb - xa) / (yb - ya)))
        out[y, max(0, x0):max(0, x0 + n)] = True
    return out & S


def _thin_letter(ch, m, s, b, t):
    """jax_thin.thin: one glyph (its ink mask, cap rows, from column 0) -> the thinned mask. ``t``: the stored diagonal
    weights of this letter, in the order jax_thin computes them."""
    S = _silhouette(m)
    H, W = S.shape
    L, R, T, B = _bands(S, s, b)
    SL, SR = _straight(S, "L", s), _straight(S, "R", s)
    mid = 11
    t = list(t)
    if ch == "O":
        return L | R | T | B
    if ch == "D":
        return SL | R | T | B
    if ch == "Q":
        return (L | R | T | B) | _diag(S, s, W * 0.48, H * 0.66, W - 2.0, H, 2)
    if ch == "B":
        return SL | R | T | B | _hbar(S, mid, b)
    if ch == "C":
        return L | T | B | (R & (_rows(S, 0, 4) | _rows(S, H - 4, H)))
    if ch == "c":
        top = int(np.flatnonzero(S.any(1))[0])
        return L | T | B | (R & (_rows(S, top, top + 3) | _rows(S, H - 3, H)))
    if ch in "EF":
        xs = np.flatnonzero(m[mid + 1])
        xe = (int(xs[-1]) if len(xs) else -1) + 1
        return SL | T | (B if ch == "E" else np.zeros_like(S)) | _hbar(S, mid, b, 0, xe)
    if ch == "G":
        jaw = 10
        return L | T | B | (R & (_rows(S, 0, 4) | _rows(S, jaw, H))) | _hbar(S, jaw, b, W - 6, W)
    if ch == "H":
        return SL | SR | _hbar(S, mid, b)
    if ch in "IT":
        x0 = int(round((W - s) / 2))
        stem = np.zeros_like(S)
        stem[:, x0:x0 + s] = True
        return (T if ch == "T" else np.zeros_like(S)) | (stem & S)
    if ch == "J":
        return R | (B & ~_rows(S, 0, H - 6)) | (L & _rows(S, H - 7, H))
    if ch == "L":
        return SL | B
    if ch == "U":
        return (SL | SR) & _rows(S, 0, H - 6) | L & _rows(S, H - 6, H) | R & _rows(S, H - 6, H) | B
    if ch in "PR":
        yb = 12
        out = SL | T | (R & _rows(S, 0, yb + 1)) | _hbar(S, yb - b + 1, b, 0, W)
        return out | (R & _rows(S, yb, H)) if ch == "R" else out
    if ch == "A":
        return L | R | T | _hbar(S, 14, b)
    if ch == "V":
        return L | R | B
    # diagonal letters: ``t`` lists, in jax_thin's order, the position weight(s) it computes first and then the weight
    # of each diagonal (jax_thin's diag() default), all stored at authoring time
    if ch == "W":
        q1, q3 = W * 0.30, W * 0.70
        w, d1, d2 = t
        return L | R | _diag(S, s, W / 2 - w / 2, H * 0.22, q1 - w / 2, H, d1) | \
            _diag(S, s, W / 2 - w / 2, H * 0.22, q3 - w / 2, H, d2)
    if ch == "M":
        depth = H * 0.70
        w, d1, d2 = t
        stems = np.zeros_like(S)
        stems[:, :s] = True
        stems[:, W - s:] = True
        return stems | _diag(S | stems, s, 0, 0, W / 2 - w / 2, depth, d1) | \
            _diag(S | stems, s, W - w, 0, W / 2 - w / 2, depth, d2)
    if ch == "N":
        w, d1 = t
        return SL | SR | _diag(S, s, 0, 0, W - w, H, d1)
    if ch == "K":
        w, d1, w2, d2 = t
        yk = H * 0.58
        arm = _diag(S, s, W - w, 0, s, yk, d1)
        ya = yk - 4.0
        xa = (W - w) + (ya / yk) * (s - (W - w)) + 1.0
        leg = _diag(S, s, xa, ya, W - round(w2), H, d2)
        return SL | arm | leg
    if ch == "X":
        w, d1, d2 = t
        return _diag(S, s, 0, 0, W - w, H, d1) | _diag(S, s, W - w, 0, 0, H, d2)
    if ch == "Y":
        w, d1, d2 = t
        yj = H * 0.52
        x0 = int(round((W - s) / 2))
        stem = np.zeros_like(S)
        stem[int(yj) - 1:, x0:x0 + s] = True
        return _diag(S, s, 0, 0, x0, yj, d1) | _diag(S, s, W - w, 0, x0 + s - w, yj, d2) | (stem & S)
    if ch == "Z":
        w, d1 = t
        return T | B | _diag(S, s, W - w, b - 0.5, 0, H - b + 0.5, d1)
    if ch == "S":
        sp = mid
        up = (L & _rows(S, 0, sp + 2)) | (R & _rows(S, 0, 4))
        lo = (R & _rows(S, sp, H)) | (L & _rows(S, H - 4, H))
        return T | B | up | lo | _hbar(S, sp, b)
    if ch == "'":
        out = np.zeros_like(S)
        for y in range(H):
            xs = np.flatnonzero(S[y])
            if len(xs):
                c = int(round((xs[0] + xs[-1]) / 2))
                out[y, max(xs[0], c - 1):min(xs[-1], c + 1) + 1] = True
        return out
    if ch == "-":
        ys = np.flatnonzero(S.any(1))
        y0 = int(round((ys[0] + ys[-1]) / 2)) - 1
        return _hbar(S, y0, 3)
    raise ValueError("2026 glyph fixes: no thinning rule for " + repr(ch))


def thin_letters(strip, op):
    """The ``thin_letters`` operation on a nameplate strip (32 x 1024 RGBA): every glyph cell of the strip the build
    holds (``offsets``: the 29 atlas columns) thinned by its letter's rule, moved to its cell's column 0, in the colour
    ``fill`` on a clear strip of that colour (the old letters are cleared by the instruction, never by shipped texels)."""
    rgba = np.asarray(strip, np.uint8)
    fill = _colour(op["fill"]).astype(np.uint8)
    top, cap, cell = int(op["top"]), int(op["cap"]), 32
    out = np.zeros(rgba.shape, np.uint8)
    out[..., :3] = fill
    weights = op["weights"]
    for i, ch in enumerate(_THIN_GLYPHS):
        x0 = int(op["offsets"][i])
        m = rgba[top:top + cap, x0:x0 + cell, 3] >= 128
        cols = np.flatnonzero(m.any(0))
        m = m[:, cols[0]:cols[-1] + 1]
        new = _thin_letter(ch, m, int(op["stem"]), int(op["bar"]), [float.fromhex(w) for w in weights.get(ch, [])])
        ncols = np.flatnonzero(new.any(0))
        new = new[:, ncols[0]:ncols[-1] + 1]
        region = out[top:top + cap, x0:x0 + new.shape[1]]
        region[new, 3] = 255
    return out


def digit_level0(span):
    """Level 0 of a digit span as RGBA (the glyph the build holds)."""
    chunk, decoded, _info, texture = _one_txtr(span)
    return np.frombuffer(texture_to_rgba(decoded, chunk, texture), np.uint8).reshape(texture.height, texture.width, 4)


def compile_derived_names(span, row):
    """A ``names_derived`` row: its operations on the strip the build holds, then the ``names_png`` route."""
    rgba = derive_digit(names_level0(span), row["derive"])
    require(sha(rgba.tobytes()) == row["rgba_sha256"], "the derived nameplate strip differs from its pin")
    return compile_names_rgba(span, rgba)


def compile_derived_digit(span, row):
    """A ``digit_derived`` row: its operations on the glyph the build holds, then the ``digit_png`` route."""
    rgba = derive_digit(digit_level0(span), row["derive"])
    require(sha(rgba.tobytes()) == row["rgba_sha256"], "the derived digit differs from its pin")
    return compile_digit_rgba(span, rgba.tobytes())


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
    return compile_names_rgba(span, names_png_rgba(png_payload))


def compile_names_rgba(span, rgba):
    """A nameplate strip picture (32 x 1024 RGBA array) -> the pinned chunk 43 span (``compile_names_png``'s route)."""
    chunk, decoded, _info, texture = _one_txtr(span)
    require(texture.name == "names" and texture.format_name == "VC_P8_LINEAR" and
            (texture.width, texture.height) == NAMES_SIZE, "not a 1024 x 32 linear nameplate strip")
    rgba = np.asarray(rgba, np.uint8)
    require(rgba.shape == (NAMES_SIZE[1], NAMES_SIZE[0], 4), "the nameplate strip picture is not 1024 x 32")
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
        elif row["kind"] == "digit_derived":
            new, detail = compile_derived_digit(span, row)
        elif row["kind"] == "names_derived":
            new, detail = compile_derived_names(span, row)
            detail = {k: v for k, v in detail.items() if k != "fit"}
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
