"""Replace HUD fonts and scorebug art by appending new resources to pack 0.

The game's resource registry returns the most recently registered resource of
a name (proved natively: two FONTs named font4, the global lookup returns the
second), and its boot sequence loads global.iff, dir_ingame.iff and roster.iff,
waits, then fills the ten-entry font table by name (0xEF570). So a FONT chunk
appended to global.iff with the name "FirstPersonComic" is bound to font slot
9 by the game itself, and a bigger "font4"/"font8"/"score_buga" appended after
the retail one replaces it for every lookup. No executable code changes; the
retail chunks stay in place (their offsets and every existing writer are
unchanged) and only cost their own resident size.

Every chunk written here is an uncompressed wrapper (no VC-LZ scratch). The
pack transaction appends a complete grown pack 0 at the end of the image and
switches its XDVDFS node, like the runtime scorebug transport.
EXPERIMENTAL / UNWITNESSED in game.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
import struct
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "nfl2k5_scorebug_assets"
GLYPH_SHEET, GLYPH_JSON = DATA / "espn_glyphs.png", DATA / "espn_glyphs.json"
VERSION = "scorebug-assets-v1"
# pack 0 outers: global.iff (fonts) and gamedata.iff (the HUD)
GLOBAL_OUTER, GLOBAL_ID, GLOBAL_START, GLOBAL_SIZE = 3, 0x8EE9EEED, 416 * 2048, 2387424
HUD_OUTER, HUD_ID, HUD_START, HUD_SIZE = 346, 0x00B6926C, 109895680, 2977184
PACK_SIZE = 193710080
RETAIL_FONTS = {3: dict(name="font4", offset=32096, stored=7184, width=128),
                7: dict(name="font8", offset=74336, stored=13280, width=256)}
SLOT9_NAME = "FirstPersonComic"   # the game's own tenth font-table name (0xE6B490)
FONT_TABLE, FONT_NAMES = 0xA90ECC, 0xA91928
MASK_LEVELS = 15
MISSING_GLYPH_DONOR = "donor"
P8_FORMAT = 0x00010B29  # OR (log2 h << 24) | (log2 w << 20)


class AssetsError(ValueError):
    pass


def digest(data) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def require(ok, message):
    if not ok:
        raise AssetsError(message)


# --------------------------------------------------------------------------- fonts
def _sources():
    from PIL import Image
    meta = json.loads(GLYPH_JSON.read_text(encoding="utf-8"))
    sheet = Image.open(GLYPH_SHEET).convert("L")
    return {char: sheet.crop(tuple(row["box"])) for char, row in meta.items()}


def _donor_glyphs(decoded, width):
    """Retail glyph masks by character (used for characters not sampled from the broadcast)."""
    from PIL import Image
    from .runtime_dependencies import require_numpy
    np = require_numpy("Scorebug texture conversion")
    from . import nfl2k5_scorebug_ingame as r
    system = struct.unpack_from("<I", decoded, 8)[0]
    plane = np.frombuffer(r.tx.unswizzle_2d(decoded[system:system + width * width], width, width, 1),
                          dtype=np.uint8).reshape(width, width)
    obj = 48
    count = struct.unpack_from("<I", decoded, obj + 4)[0]
    ranges = obj + 8 + struct.unpack_from("<I", decoded, obj + 8)[0] - 1
    out = {}
    for i in range(count):
        first, last, relative = struct.unpack_from("<HHI", decoded, ranges + 8 * i)
        glyphs = ranges + 8 * i + 4 + relative - 1
        for cp in range(first, last + 1):
            rec = glyphs + 96 * (cp - first)
            adv = struct.unpack_from("<I", decoded, rec)[0]
            q = struct.unpack_from("<16f", decoded, rec + 16)
            u0, v0, u1, v1 = struct.unpack_from("<4f", decoded, rec + 80)
            x0, y0, x1, y1 = (round(u0 * width), round(v0 * width), round(u1 * width), round(v1 * width))
            cell = plane[y0:y1, x0:x1] * 17 if x1 > x0 and y1 > y0 else np.zeros((1, 1), np.uint8)
            out[chr(cp)] = dict(advance=adv, quad=(q[0], q[1], q[4], q[9]), image=Image.fromarray(cell.astype(np.uint8)))
    return out


@dataclass
class FontSpec:
    name: str
    cap: int                 # cap height in HUD units (the drawn size)
    atlas: int = 256         # mask width and height
    supersample: float = 1.0   # mask pixels per HUD unit (1 = texel per unit, like retail)
    chars: str = "0123456789:&-~ stndrhGOALDowIcael"


def espn_font_chunk(donor_span: bytes, spec: FontSpec) -> tuple[bytes, dict]:
    """A complete uncompressed FONT chunk: broadcast glyphs, designed metrics.

    Sampled broadcast glyphs are used for every character in the sheet; other
    characters keep the donor font's retail shapes, scaled to the same cap
    height, so any string the game prints with this font stays legible.
    """
    from PIL import Image
    from .runtime_dependencies import require_numpy
    np = require_numpy("Scorebug texture conversion")
    from . import nfl2k5_scorebug_ingame as r
    chunk, decoded, _ = r.decode(donor_span)
    require(chunk.kind == "FONT", "font donor must be a FONT chunk")
    width = spec.atlas
    require(width in (128, 256, 512), "font atlas must be 128, 256 or 512 wide")
    sources = _sources()
    donor = _donor_glyphs(decoded, RETAIL_FONTS[7]["width"] if chunk.video_bytes > 20000 else RETAIL_FONTS[3]["width"])
    cell_h = int(round(spec.cap * spec.supersample))
    require(cell_h + 2 <= width, "cap height too large for the atlas")
    sources_cap = sources["0"].height if "0" in sources else cell_h
    donor_cap = donor["0"]["image"].height if "0" in donor else cell_h
    plane = np.zeros((width, width), dtype=np.uint8)
    records = {}
    glyphs = []
    for char in dict.fromkeys(spec.chars):
        if char == " ":
            records[char] = dict(advance=round(spec.cap * 0.32), x0=0.0, x1=0.0, height=0.0, uv=(0, 0, 0, 0))
            continue
        if char in sources:
            src, scale = sources[char], cell_h / sources_cap
        elif char == "~":
            src = Image.new("L", (round(cell_h * 0.75), cell_h), 0)
            bar = max(2, round(cell_h * 0.16))
            top = round(cell_h * 0.62)
            src.paste(255, (0, top, src.width, top + bar))
            scale = 1.0
        elif char in donor and donor[char]["image"].width > 1:
            src, scale = donor[char]["image"], cell_h / donor_cap
        else:
            continue
        glyph = src.resize((max(1, round(src.width * scale)), max(1, round(src.height * scale))), Image.Resampling.LANCZOS)
        glyphs.append((char, glyph))
    row_h = max(g.height for _, g in glyphs) + 2
    x = y = 1
    for char, glyph in glyphs:
        gw, gh = glyph.size
        if x + gw + 1 > width:
            x, y = 1, y + row_h
        require(y + gh + 1 <= width, "font atlas overflow; use a larger atlas or fewer characters")
        levels = (np.asarray(glyph, dtype=np.float32) * MASK_LEVELS / 255.0 + 0.5).astype(np.uint8)
        plane[y:y + gh, x:x + gw] = np.clip(levels, 0, MASK_LEVELS)
        # Quad in HUD units: the glyph sits on the baseline with the cap top at
        # the line's cap height; taller glyphs (ascenders) rise above it.
        drawn_w, drawn_h = gw / spec.supersample, gh / spec.supersample
        records[char] = dict(advance=round(drawn_w + spec.cap * 0.1), x0=0.0, x1=drawn_w, height=drawn_h,
                             uv=(x / width, y / width, (x + gw) / width, (y + gh) / width))
        x += gw + 2
    # Object layout mirrors the retail FONT: header copy, UTF-16 name, object,
    # one codepoint range, 96-byte glyph records, then the swizzled mask.
    name = (spec.name + "\0").encode("utf-16le")
    body = bytearray(decoded[:32])
    body += name
    while len(body) % 16:
        body += b"\xff"
    obj = len(body)
    codes = sorted(ord(c) for c in records)
    first, last = min(codes), max(codes)
    line = round(spec.cap * 1.29)
    metrics = (round(spec.cap * 0.45), round(spec.cap * 1.33), spec.cap, -round(spec.cap * 0.33), line)
    body += struct.pack("<HH", first, last)       # obj+0
    body += struct.pack("<I", 1)                  # obj+4 one range
    body += struct.pack("<I", 0)                  # obj+8 relative pointer to ranges (filled below)
    body += struct.pack("<5i", *metrics)          # obj+12..28
    body += struct.pack("<II", 0, 0)              # obj+32, +36
    body += struct.pack("<I", width * width)      # obj+40 mask bytes
    lg = width.bit_length() - 1
    body += struct.pack("<I", (lg << 24) | (lg << 20) | P8_FORMAT)  # obj+44 texture format
    while len(body) % 16:
        body += b"\xff"
    ranges = len(body)
    struct.pack_into("<I", body, obj + 8, ranges - (obj + 8) + 1)
    body += struct.pack("<HHI", first, last, 0)   # the glyph pointer is filled below
    while len(body) % 16:
        body += b"\xff"
    glyphs = len(body)
    struct.pack_into("<I", body, ranges + 4, glyphs - (ranges + 4) + 1)
    empty = dict(advance=0, x0=0.0, x1=0.0, height=0.0, uv=(0, 0, 0, 0))
    for cp in range(first, last + 1):
        rec = records.get(chr(cp), empty)
        y1 = float(line)
        y0 = float(line - rec.get("height", spec.cap))
        x0, x1 = float(rec["x0"]), float(rec["x1"])
        body += struct.pack("<I", rec["advance"]) + b"\xff" * 12
        body += struct.pack("<16f", x0, y0, 0, 0, x1, y0, 0, 0, x0, y1, 0, 0, x1, y1, 0, 0)
        body += struct.pack("<4f", *rec["uv"])
    while len(body) % 128:
        body += b"\xff"
    struct.pack_into("<I", body, 0x10, 0x20 - 0x10 + 1)   # name pointer
    struct.pack_into("<I", body, 0x14, obj - 0x14 + 1)     # object pointer
    system = bytes(body)
    video = r.tx.swizzle_2d(plane.tobytes(), width, width, 1) + decoded[-1024:]
    payload = system + video
    header = struct.pack("<4s7I", b"FONT", len(payload), len(system), len(video), 0, 0, 0, 0)
    result = header + payload
    check, again, _ = r.decode(result)
    require(check.kind == "FONT" and again == payload, "font chunk round trip failed")
    return result, dict(name=spec.name, cap=spec.cap, atlas=width, characters="".join(sorted(records)),
                        sampled="".join(sorted(c for c in records if c in sources)),
                        first=first, last=last, system_bytes=len(system), video_bytes=len(video),
                        resident_bytes=len(system) + len(video), sha256=digest(result))


def retail_font_span(pack_read, slot: int) -> bytes:
    spec = RETAIL_FONTS[slot]
    return pack_read(32 + spec["stored"], GLOBAL_START + spec["offset"])


# ------------------------------------------------------------------------ textures
def alpha_bleed(image, pixels=6):
    """Extend visible RGB into zero-alpha texels without expanding the silhouette.

    NV2A samples straight RGBA. Transparent black therefore darkens a bilinear
    edge even though it contributes no coverage. Keep this RGB after resizing
    and after placing a mark on its transparent canvas.
    """
    from .runtime_dependencies import require_numpy
    np = require_numpy("Scorebug texture conversion")
    from PIL import Image
    a = np.asarray(image.convert("RGBA")).copy()
    known = a[:, :, 3] > 0
    for _ in range(pixels):
        previous = known.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            sy = slice(max(0, -dy), min(a.shape[0], a.shape[0]-dy))
            sx = slice(max(0, -dx), min(a.shape[1], a.shape[1]-dx))
            ty = slice(max(0, dy), min(a.shape[0], a.shape[0]+dy))
            tx = slice(max(0, dx), min(a.shape[1], a.shape[1]+dx))
            take = previous[sy, sx] & ~known[ty, tx]
            a[ty, tx, :3][take] = a[sy, sx, :3][take]
            known[ty, tx][take] = True
        if np.array_equal(previous, known):
            break
    return Image.fromarray(a)


def resample_logo(image, size):
    """Bleed before filtering, explicitly filter premultiplied, retain one feather.

    The source marks contain faint Lanczos ringing outside their outline. Drop
    the <1/16-coverage tail and snap the opaque core; retain intermediate edge
    coverage instead of thresholding the silhouette to a hard cutout.
    """
    from PIL import Image
    image = image.convert("RGBA")
    image.putalpha(image.getchannel("A").point(lambda a: 0 if a < 16 else 255 if a > 239 else a))
    image = alpha_bleed(image)
    image = image.convert("RGBa").resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    image.putalpha(image.getchannel("A").point(lambda a: 0 if a < 16 else 255 if a > 239 else a))
    # Keep fractional coverage only in the one-texel silhouette boundary band.
    # Anisotropic logo fitting can otherwise stretch a source feather to two
    # texels, leaving a few faint islands even after the ringing tail is removed.
    from .runtime_dependencies import require_numpy
    np = require_numpy("Scorebug texture conversion")
    alpha = np.asarray(image.getchannel("A")).copy()
    solid = alpha >= 128
    padded = np.pad(solid, 1, mode="edge")
    neighbors = [padded[y:y+image.height, x:x+image.width] for y in range(3) for x in range(3)]
    boundary = np.logical_or.reduce(neighbors) & ~np.logical_and.reduce(neighbors)
    alpha[~boundary] = np.where(solid[~boundary], 255, 0)
    image.putalpha(Image.fromarray(alpha))
    return alpha_bleed(image)


def quantize_alpha_aware(image, maximum=256, *, reserved=()):
    """P8 with exact alpha endpoints and a dedicated white-mask alpha ramp.

    Never average transparent, opaque and feather texels into the same palette
    entry. Rank feather colours in premultiplied RGBA, and preserve the RGB of
    zero-alpha gutters for the GPU's straight-RGBA bilinear sampler. No dithering.
    Historical texture authors keep their original quantizer unless opted in.
    """
    from collections import Counter
    from .runtime_dependencies import require_numpy
    np = require_numpy("Scorebug texture conversion")
    import nfl_tset_png_import as palettes
    require(32 <= maximum <= 256, "alpha-aware P8 needs 32..256 entries")
    a = np.asarray(image.convert("RGBA")).copy()
    if reserved:
        fixed=sorted(set(tuple(map(int,c)) for c in reserved))
        require(len(fixed)<=32 and maximum-len(fixed)>=32, "too many reserved atlas colours")
        palette,indices=quantize_alpha_aware(image,maximum-len(fixed))
        indices=np.frombuffer(indices,dtype=np.uint8).copy()+len(fixed)
        flat=a.reshape(-1,4)
        for i,colour in enumerate(fixed):indices[(flat==colour).all(axis=1)]=i
        return fixed+palette,indices.tobytes()
    # Sub-3% filter ringing is outside the one-texel feather, not new detail.
    a[:, :, 3][(a[:, :, 3] < 8) & (a[:, :, :3].min(axis=2) < 250)] = 0
    colors, inverse, counts = np.unique(a.reshape(-1, 4), axis=0, return_inverse=True, return_counts=True)
    groups = np.where(colors[:, 3] == 0, 0, np.where(colors[:, 3] == 255, 1,
                      np.where((colors[:, :3] == 255).all(axis=1), 2, 3)))
    budgets = [maximum//8, maximum//2, maximum//4, maximum-maximum//8-maximum//2-maximum//4]
    # Reclaim unused categories (especially neutral fallback and simple logos).
    sizes = [int((groups == i).sum()) for i in range(4)]
    limits = [min(n, b) for n, b in zip(sizes, budgets)]
    while sum(limits) < min(maximum, len(colors)):
        candidates = [i for i in range(4) if limits[i] < sizes[i]]
        i = max(candidates, key=lambda i: (sizes[i]-limits[i], -i))
        limits[i] += 1
    palette = []
    mapping = np.zeros(len(colors), dtype=np.uint8)
    for group, limit in enumerate(limits):
        ids = np.flatnonzero(groups == group)
        if not len(ids):
            continue
        raw = colors[ids].astype(np.int32)
        working = raw.copy()
        if group == 3:
            working[:, :3] = (working[:, :3]*working[:, 3:]+127)//255
        histogram = Counter()
        for color, count in zip(working, counts[ids]):
            histogram[tuple(map(int, color))] += int(count)
        representatives = np.array(palettes.median_cut_palette(histogram, limit), dtype=np.int32)
        error = working[:, None, :]-representatives[None, :, :]
        # Coverage matters more than faint RGB. This also keeps the white ramp monotonic.
        error[:, :, 3] *= 2
        nearest = (error*error).sum(axis=2).argmin(axis=1)
        mapping[ids] = nearest + len(palette)
        if group == 3:
            representatives[:, :3] = np.minimum(255, (representatives[:, :3]*255+representatives[:, 3:]//2)//np.maximum(1, representatives[:, 3:]))
        palette.extend(tuple(map(int, color)) for color in representatives)
    return palette, mapping[inverse].tobytes()


def texture_chunk(name: str, image, template: bytes, *, colours: int = 256, alpha_aware: bool = False, reserved_colours=()) -> tuple[bytes, dict]:
    """An uncompressed P8 TXTR chunk of any power-of-two size (32..512 per side).

    ``template`` is a retail P8 TXTR span (score_buga); its 128-byte system
    buffer supplies the object layout and the descriptor words. Only the name,
    the palette offset and the format word change.
    """
    require(all(side in (32, 64, 128, 256, 512) for side in image.size), "texture size must be a power of two")
    require(len((name + "\0").encode("utf-16le")) <= 24, "texture name too long")
    # Preflight/status checks repeatedly request identical atlas and logo bytes.
    # Key every input byte and option, never a path, mtime or ctime. The cache is
    # bounded to 40 textures (about 50 MB at the maximum supported dimensions).
    rgba = image.convert("RGBA")
    result, receipt = _texture_chunk(name, rgba.size, rgba.tobytes(), bytes(template),
                                     colours, alpha_aware, tuple(tuple(c) for c in reserved_colours))
    return result, dict(receipt)


@lru_cache(maxsize=40)
def _texture_chunk(name, size, pixels, template, colours, alpha_aware, reserved_colours):
    from PIL import Image
    from . import nfl2k5_scorebug_ingame as r
    import nfl_tset_png_import as palettes
    image = Image.frombytes("RGBA", size, pixels)
    w, h = image.size
    require(w in (32, 64, 128, 256, 512) and h in (32, 64, 128, 256, 512), "texture size must be a power of two")
    encoded = (name + "\0").encode("utf-16le")
    require(len(encoded) <= 24, "texture name too long")
    chunk, decoded, _ = r.decode(template)
    require(chunk.kind == "TXTR" and chunk.system_bytes == 128, "texture template must be a retail P8 TXTR")
    system = bytearray(decoded[:128])
    system[32:56] = encoded.ljust(24, b"\0")
    descriptor = struct.unpack_from("<I", system, 0x14)[0] + 0x13
    lw, lh = w.bit_length() - 1, h.bit_length() - 1
    struct.pack_into("<I", system, descriptor + 8, w * h)                       # palette follows the indices
    struct.pack_into("<I", system, descriptor + 12, (lh << 24) | (lw << 20) | P8_FORMAT)
    struct.pack_into("<I", system, descriptor + 16, 0)                          # dimensions from the format word
    rgba = image.convert("RGBA")
    if alpha_aware:
        palette, indices = quantize_alpha_aware(rgba, colours, reserved=reserved_colours)
        levels = [indices]
    else:
        palette, levels, _ = palettes.quantize_levels([palettes.MipLevel(0, w, h, rgba.tobytes())], colours)
    video = r.tx.swizzle_2d(levels[0], w, h, 1) + palettes.palette_bytes(palette)
    payload = bytes(system) + video
    header = struct.pack("<4s7I", b"TXTR", len(payload), 128, len(video), 0, 0, 0, 0)
    result = header + payload
    chunk, again, _ = r.decode(result)
    tex = r.tx.parse_texture(again, chunk)
    require(again == payload and (tex.width, tex.height, tex.name, tex.format_name) == (w, h, name, "P8"),
            "texture chunk round trip failed")
    return result, dict(name=name, width=w, height=h, colours=len(palette), resident_bytes=len(payload), sha256=digest(result))


def retail_texture_span(pack_read, name: str) -> bytes:
    from . import nfl2k5_scorebug_resources as art
    rec = art.RESOURCES[name]
    return pack_read(rec["span_size"], rec["pack_offset"])


# ------------------------------------------------------------------- pack 0 growth
def _align16(n):
    return (n + 15) & -16


def grow_pack(read, size: int, additions: dict[int, list[bytes]]):
    """Append chunks to the given outers of pack 0; return (views, receipt).

    ``read(count, offset)`` reads the source pack. Outers are processed in
    ascending index order; every later outer's virtual sector moves by the
    accumulated growth, exactly as the runtime scorebug transport does for one
    outer. The result is a list of (bytes_or_reader, offset, length) views.
    """
    from . import nfl2k5_scorebug_resources as art
    import nfl_outer as outer
    require(size == PACK_SIZE, "pack 0 size changed")
    header = read(outer.HEADER_SIZE, 0)
    count = struct.unpack_from("<I", header, 0)[0]
    table = bytearray(read(outer.HEADER_SIZE + count * 12, 0))
    entries = [struct.unpack_from("<3I", table, outer.HEADER_SIZE + i * 12) for i in range(count)]
    views, cursor, shift, rows = [], len(table), 0, []
    views.append(("table", 0, len(table)))
    for index in sorted(additions):
        identity, length, sector = entries[index]
        start = sector * 2048
        require(start >= cursor, "outer order")
        aligned_end = outer.align_up(start + length)
        appended = b"".join(c + b"\0" * (_align16(len(c)) - len(c)) for c in additions[index])
        new_length = _align16(length) + len(appended) if length % 16 else length + len(appended)
        new_end = outer.align_up(start + new_length)
        growth = new_end - aligned_end
        views.append(("pack", cursor, start - cursor))
        views.append(("pack", start, length))
        pad = b"\0" * (_align16(length) - length) if length % 16 else b""
        tail = pad + appended + b"\0" * (new_end - (start + new_length))
        views.append((tail, 0, len(tail)))
        struct.pack_into("<I", table, outer.HEADER_SIZE + index * 12 + 4, new_length)
        for later in range(index + 1, count):
            at = outer.HEADER_SIZE + later * 12 + 8
            struct.pack_into("<I", table, at, struct.unpack_from("<I", table, at)[0] + growth // 2048)
        shift += growth
        rows.append(dict(outer=index, identity=f"{identity:08x}", size_before=length, size_after=new_length,
                         appended=[digest(c) for c in additions[index]], growth=growth))
        cursor = aligned_end
    views.append(("pack", cursor, size - cursor))
    struct.pack_into("<I", table, 12, (size + shift) // 2048)
    parts = [(bytes(table), 0, len(table)) if kind == "table" else (kind, off, ln) for kind, off, ln in views]
    return parts, dict(growth=shift, size_before=size, size_after=size + shift, outers=rows)


class GrownPack:
    """Bounded reader over the composed views (no whole pack in memory)."""
    def __init__(self, read, parts):
        self.read, self.parts, self.size = read, parts, sum(p[2] for p in parts)

    def blocks(self, block=1024 * 1024):
        for source, off, ln in self.parts:
            at = 0
            while at < ln:
                take = min(block, ln - at)
                yield source[off + at:off + at + take] if isinstance(source, bytes) else self.read(take, off + at)
                at += take

    def digest(self):
        h = hashlib.sha256()
        for b in self.blocks():
            h.update(b)
        return h.hexdigest()


# ------------------------------------------------------------------- image apply
def default_plan(pack_read, *, slot9: FontSpec | None = None, font4: bool = False, font8: bool = False,
                 atlas=None):
    """Chunks to append per outer for the chosen replacements."""
    additions, receipt = {}, {}
    fonts = []
    if slot9 is not None:
        donor = retail_font_span(pack_read, 7)
        chunk, rec = espn_font_chunk(donor, slot9)
        fonts.append(chunk); receipt["slot9"] = rec
    if font4:
        chunk, rec = espn_font_chunk(retail_font_span(pack_read, 3), FontSpec("font4", cap=11, atlas=256, supersample=3))
        fonts.append(chunk); receipt["font4"] = rec
    if font8:
        chunk, rec = espn_font_chunk(retail_font_span(pack_read, 7), FontSpec("font8", cap=21, atlas=256, supersample=2))
        fonts.append(chunk); receipt["font8"] = rec
    if fonts:
        additions[GLOBAL_OUTER] = fonts
    if atlas is not None:
        chunk, rec = texture_chunk("score_buga", atlas, retail_texture_span(pack_read, "score_buga"))
        additions[HUD_OUTER] = [chunk]; receipt["atlas"] = rec
    return additions, receipt


def apply_in_place(path, *, slot9: FontSpec | None = None, font4=False, font8=False, atlas=None) -> dict:
    """Append the grown pack 0 to the image and switch its directory node."""
    from . import nfl2k5_depth_chart_storage as storage, platform_compat as io
    from . import nfl2k5_scorebug_ingame as ingame
    with Path(path).open("r+b") as stream:
        fd = stream.fileno()
        image_size = os.fstat(fd).st_size
        entries, _ = ingame.layout.xc.parse_xdvdfs(fd, image_size)
        entry = entries.get("vc_53450030/0")
        require(entry is not None and entry.size == PACK_SIZE, "pack 0 is not retail-sized; this route needs the retail pack")
        read = lambda count, offset: io.pread(fd, count, entry.byte_offset + offset)  # noqa: E731
        additions, receipt = default_plan(read, slot9=slot9, font4=font4, font8=font8, atlas=atlas)
        require(additions, "nothing to apply")
        parts, growth = grow_pack(read, entry.size, additions)
        grown = GrownPack(read, parts)
        node, sector, length = storage.image_file_node(lambda c, o: io.pread(fd, c, o), entry.base_offset, image_size, entry.path)
        require((sector, length) == (entry.sector, entry.size), "pack node differs from the directory")
        old_node = io.pread(fd, 8, node)
        offset = (image_size + 2047) & -2048
        try:
            if offset > image_size:
                io.pwrite(fd, bytes(offset - image_size), image_size)
            cursor = offset
            for block in grown.blocks():
                require(io.pwrite(fd, block, cursor) == len(block), "short pack write")
                cursor += len(block)
            written = GrownPack(lambda c, o: io.pread(fd, c, offset + o), [("pack", 0, grown.size)])
            require(written.digest() == grown.digest(), "grown pack readback failed")
            io.pwrite(fd, struct.pack("<II", (offset - entry.base_offset) // 2048, grown.size), node)
            after, _ = ingame.layout.xc.parse_xdvdfs(fd, os.fstat(fd).st_size)
            require(after["vc_53450030/0"].byte_offset == offset and after["vc_53450030/0"].size == grown.size,
                    "directory readback failed")
            os.fsync(fd)
        except Exception:
            io.pwrite(fd, old_node, node)
            os.ftruncate(fd, image_size)
            os.fsync(fd)
            raise
    return dict(version=VERSION, status="applied", experimental=True, witnessed=False,
                pack_offset=offset, pack_size=grown.size, image_growth=grown.size + (offset - image_size),
                **growth, resources=receipt)


def image_status(path) -> str:
    from . import nfl2k5_scorebug_ingame as ingame
    try:
        with Path(path).open("rb") as stream:
            fd = stream.fileno()
            entries, _ = ingame.layout.xc.parse_xdvdfs(fd, os.fstat(fd).st_size)
            entry = entries["vc_53450030/0"]
            if entry.size == PACK_SIZE:
                return "retail"
            import nfl_outer as outer
            from . import platform_compat as io
            table = io.pread(fd, outer.HEADER_SIZE + 400 * 12, entry.byte_offset)
            _, length, _ = struct.unpack_from("<3I", table, outer.HEADER_SIZE + GLOBAL_OUTER * 12)
            return "applied" if length > GLOBAL_SIZE else "foreign"
    except (OSError, KeyError, struct.error, ValueError):
        return "foreign"


# ------------------------------------------------------------------ 2026 atlas art
LOGOS = DATA / "logos"
WORDMARK = DATA / "espn_wordmark.png"
TEAM_FILES = {"ARI": "ari", "ATL": "atl", "BAL": "bal", "BUF": "buf", "CAR": "car", "CHI": "chi", "CIN": "cin",
              "CLE": "cle", "DAL": "dal", "DEN": "den", "DET": "det", "GB": "gb", "HOU": "hou", "IND": "ind",
              "JAX": "jax", "KC": "kc", "LAC": "lac", "LAR": "lar", "LV": "lv", "MIA": "mia", "MIN": "min",
              "NE": "ne", "NO": "no", "NYG": "nyg", "NYJ": "nyj", "PHI": "phi", "PIT": "pit", "SEA": "sea",
              "SF": "sf", "TB": "tb", "TEN": "ten", "WAS": "wsh"}
# Atlas regions in texels of a 256x256 atlas (x0, y0, x1, y1). The first four
# rows keep the retail 64x64 atlas's proportions at 4x so the existing
# nine-slice frame, plate and strip UV conventions still address them.
ATLAS_REGIONS = {
    "frame": (0, 0, 96, 96),          # nine-slice pill tile: rounded caps, top lip
    "wordmark": (96, 0, 256, 48),     # ESPN wordmark, white on transparent
    "wing_ramp": (96, 48, 256, 96),   # white to black ramp (material tint = team colour)
    "plate": (0, 96, 256, 160),       # light rounded down-and-distance plate (tinted by possession)
    "capsule": (0, 160, 256, 240),    # light clock capsule with cell separators
    "solid": (0, 240, 16, 256),       # solid white
    "dark": (16, 240, 32, 256),       # solid charcoal
}
LOGO_CELL, LOGO_ORIGIN = 40, (0, 256)   # logos start below the 256-row art in a 256x512 atlas


def atlas_2026(*, logos=True):
    """The 2026 MNF scorebug atlas: art in the top 256 rows, 32 logos below.

    256 x 512 P8: one palette for everything (the quantizer shares 256 colours
    across the logos, so team marks keep their own reds, blues and golds).
    """
    from PIL import Image, ImageDraw
    size = (256, 512 if logos else 256)
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    body, hi, lip = (11, 14, 20, 255), (23, 27, 35, 255), (201, 208, 218, 255)
    # frame tile: pill body with rounded caps and a bright top lip
    d.rounded_rectangle((0, 0, 95, 95), 16, fill=body)
    for yy in range(0, 96):
        t = yy / 95
        row = tuple(round(hi[i] * (1 - t) + body[i] * t) for i in range(3)) + (255,)
        d.line((16, yy, 79, yy), fill=row)
    d.rounded_rectangle((0, 0, 95, 95), 16, outline=(40, 44, 52, 255))
    d.line((14, 0, 81, 0), fill=lip)
    d.line((14, 1, 81, 1), fill=(150, 156, 166, 255))
    # ESPN wordmark
    mark = Image.open(WORDMARK).convert("L")
    x0, y0, x1, y1 = ATLAS_REGIONS["wordmark"]
    scale = min((x1 - x0 - 8) / mark.width, (y1 - y0 - 8) / mark.height)
    mark = mark.resize((round(mark.width * scale), round(mark.height * scale)), Image.Resampling.LANCZOS)
    white = Image.new("RGBA", mark.size, (245, 247, 250, 255))
    white.putalpha(mark)
    im.alpha_composite(white, (x0 + (x1 - x0 - mark.width) // 2, y0 + (y1 - y0 - mark.height) // 2))
    # wing ramp: white at the outer edge to charcoal at the inner edge
    x0, y0, x1, y1 = ATLAS_REGIONS["wing_ramp"]
    for xx in range(x0, x1):
        t = (xx - x0) / (x1 - x0 - 1)
        v = round(255 * (1 - t) ** 1.6)
        d.line((xx, y0, xx, y1 - 1), fill=(v, v, v, 255))
    # plate: near-white rounded rectangle (possession colour is the material tint)
    x0, y0, x1, y1 = ATLAS_REGIONS["plate"]
    d.rounded_rectangle((x0 + 2, y0 + 2, x1 - 3, y1 - 3), 14, fill=(236, 238, 242, 255), outline=(255, 255, 255, 255))
    d.line((x0 + 16, y0 + 3, x1 - 17, y0 + 3), fill=(255, 255, 255, 255))
    # capsule: light pill with two separators
    x0, y0, x1, y1 = ATLAS_REGIONS["capsule"]
    d.rounded_rectangle((x0 + 2, y0 + 4, x1 - 3, y1 - 5), 36, fill=(236, 239, 243, 255), outline=(200, 205, 212, 255))
    for xx in (x0 + 84, x0 + 188):
        d.line((xx, y0 + 12, xx, y1 - 13), fill=(190, 195, 203, 255))
    d.rectangle(ATLAS_REGIONS["solid"], fill=(255, 255, 255, 255))
    d.rectangle(ATLAS_REGIONS["dark"], fill=body)
    if logos:
        for index, (abbr, stem) in enumerate(sorted(TEAM_FILES.items())):
            logo = Image.open(LOGOS / f"{stem}.png").convert("RGBA")
            logo.thumbnail((LOGO_CELL - 2, LOGO_CELL - 2), Image.Resampling.LANCZOS)
            cx = LOGO_ORIGIN[0] + (index % 6) * LOGO_CELL
            cy = LOGO_ORIGIN[1] + (index // 6) * LOGO_CELL
            im.alpha_composite(logo, (cx + (LOGO_CELL - logo.width) // 2, cy + (LOGO_CELL - logo.height) // 2))
    return im


def logo_uv(abbr: str, atlas_height: int = 512):
    """Normalized UV box of a team's logo cell in the 2026 atlas."""
    index = sorted(TEAM_FILES).index(abbr)
    x = LOGO_ORIGIN[0] + (index % 6) * LOGO_CELL
    y = LOGO_ORIGIN[1] + (index // 6) * LOGO_CELL
    return (x / 256, y / atlas_height, (x + LOGO_CELL) / 256, (y + LOGO_CELL) / atlas_height)
