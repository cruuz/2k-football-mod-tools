"""The two native kits used by the October 16, 2025 Unc Bowl.

Only 22A4 and 06H5 are owned. The photographs show black/gold Pittsburgh
with white italic numbers, and Cincinnati's White Bengal kit with broad
black pants stripes and black rear helmet numbers. Player equipment choices
remain in the moment roster, separate from these uniform resources.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from types import SimpleNamespace

# Establish the packaged native codec path through its existing owner.
from . import nfl2k5_bump_texture_writer as bump
from nfl_txtr import (HEADER, decode_chunk, parse_chunks, parse_texture,
                     minimum_vc_lz_overlap_scratch, rebuild_compressed_chunk_fixed_span,
                     unswizzle_2d, swizzle_2d)

OWNED = ("06H5.IFF", "22A4.IFF")
PINS = Path(__file__).resolve().parents[2] / "data/nfl2k5_unc_bowl_uniforms_pins.json"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_owned(name, raw):
    """Only owned compressed spans are pinned, so other repairs can compose."""
    document = json.loads(PINS.read_text(encoding="utf-8"))
    require(document.get("schema") == "nfl2k5_unc_bowl_uniforms/v1" and
            set(document["resources"]) == set(OWNED), "unexpected Unc Bowl pins")
    require(name in OWNED, "unowned uniform slot")
    spec = document["resources"][name]
    require(len(raw) == spec["size"], "uniform file allocation differs")
    hashes = [sha(raw[p["offset"]:p["offset"] + p["length"]]) for p in spec["spans"]]
    require(all(h == p["before_sha256"] for h, p in zip(hashes, spec["spans"])) or
            all(h == p["after_sha256"] for h, p in zip(hashes, spec["spans"])),
            "foreign or partially repaired Unc Bowl uniform spans")
    return spec


def _compact(span):
    chunk = parse_chunks(span)[0]
    decoded, info = decode_chunk(span, chunk)
    require(info is not None, "expected a compressed uniform texture")
    stream = span[32:32 + info.consumed_bytes]
    fields = list(HEADER.unpack_from(span))
    fields[1] = (len(stream) + 15) & ~15
    fields[5] = max(fields[5], (max(fields[1] - len(stream),
        minimum_vc_lz_overlap_scratch(stream, fields[1], len(decoded))) + 15) & ~15)
    return HEADER.pack(*fields) + stream + bytes(fields[1] - len(stream))


def finish_pittsburgh(raw, donor):
    """Copy all ten current jersey numeral mip chains without quantization.

    The gold block slots are too small individually. Compact only chunks
    13..43 and let the last wrapper absorb the remaining original space.
    Every other decoded texture and allocation stays exact.
    """
    old, current = parse_chunks(raw), parse_chunks(donor)
    require(len(old) == len(current) == 53, "unexpected uniform chunk inventory")
    if all(decode_chunk(raw, old[i])[0] == decode_chunk(donor, current[i])[0]
           for i in range(13, 23)):
        return raw
    pieces = []
    for i in range(13, 44):
        source, chunk = (donor, current[i]) if i < 23 else (raw, old[i])
        require((chunk.kind, chunk.system_bytes, chunk.video_bytes) ==
                (old[i].kind, old[i].system_bytes, old[i].video_bytes),
                "Pittsburgh numeral allocation differs")
        pieces.append(_compact(source[chunk.offset:chunk.end_offset]))
    budget = old[44].offset - old[13].offset
    total = sum(map(len, pieces))
    require(total <= budget, "white numeral mip chains exceed the kit allocation")
    last = pieces[-1]
    decoded, info = decode_chunk(last, parse_chunks(last)[0])
    stream = last[32:32 + info.consumed_bytes]
    fields = list(HEADER.unpack_from(last))
    fields[1] += budget - total
    fields[5] = max(fields[5], (max(fields[1] - len(stream),
        minimum_vc_lz_overlap_scratch(stream, fields[1], len(decoded))) + 15) & ~15)
    pieces[-1] = HEADER.pack(*fields) + stream + bytes(fields[1] - len(stream))
    out = bytearray(raw)
    out[old[13].offset:old[44].offset] = b"".join(pieces)
    return bytes(out)


def _pants(decoded, chunk):
    """Widen the existing tiger bands, retaining the native palettes and cloth.

    Polygon coordinates are an estimate fitted against the dated side views.
    Four samples per axis retain antialiasing in the game's existing palette.
    The paired mud texture shares these indices, keeping its own wet palette.
    """
    import numpy as np
    from PIL import Image, ImageDraw
    desc = 0x20 + struct.unpack_from("<i", decoded, 0x20)[0] - 1
    _self, pixel, pal, fmt, size, _flags = struct.unpack_from("<6I", decoded, desc)
    t = SimpleNamespace(width=size & 0xFFFF if size else 1 << ((fmt >> 20) & 15),
        height=size >> 16 if size else 1 << ((fmt >> 24) & 15), format_code=(fmt >> 8) & 255,
        palette_offset=pal, pixel_offset=pixel, mip_levels=(fmt >> 16) & 15)
    require((t.width, t.height, t.format_code) == (512, 256, 11), "unexpected CIN pants layout")
    palette = np.frombuffer(decoded, dtype=np.uint8, count=1024,
                            offset=chunk.system_bytes + t.palette_offset).reshape(256, 4)
    # Palette bytes are BGRA. Neutral entries have the same channel order.
    grey = palette[:, :3].astype(np.int32).mean(axis=1)
    neutral = (palette[:, :3].max(axis=1).astype(int) - palette[:, :3].min(axis=1) < 35) & (palette[:, 3] == 255)
    require(neutral.any(), "CIN pants have no opaque neutral palette entries")
    choices = np.flatnonzero(neutral)
    lookup = choices[np.abs(grey[choices, None] - np.arange(256)[None, :]).argmin(axis=0)]
    mask = Image.new("L", (2048, 1024), 0)
    draw = ImageDraw.Draw(mask)
    for row in range(7):
        y = row * 32
        points = [(111, y + 44), (111, y + 23), (174, y + 10), (157, y + 28)]
        draw.polygon([(x * 4, yy * 4) for x, yy in points], fill=255)
        draw.polygon([((512 - x) * 4, yy * 4) for x, yy in points], fill=255)
    out = bytearray(decoded)
    base = np.frombuffer(unswizzle_2d(decoded[chunk.system_bytes + t.pixel_offset:
        chunk.system_bytes + t.pixel_offset + 512 * 256], 512, 256, 1), dtype=np.uint8).reshape(256, 512)
    cloth_columns = [np.maximum(grey[base[:, lo - 1]], grey[base[:, hi]])
                     for lo, hi in ((111, 174), (338, 401))]
    cursor = t.pixel_offset
    for level in range(t.mip_levels):
        w, h = max(1, t.width >> level), max(1, t.height >> level)
        start, size = chunk.system_bytes + cursor, w * h
        plane = np.frombuffer(unswizzle_2d(decoded[start:start + size], w, h, 1), dtype=np.uint8).reshape(h, w).copy()
        coverage = np.asarray(mask.resize((w, h), Image.Resampling.BOX), dtype=np.float64) / 255
        for (lo, hi), column in zip(((111, 174), (338, 401)), cloth_columns):
            x0, x1 = lo >> level, min(w, (hi + (1 << level) - 1) >> level)
            if x0 == x1:
                continue
            # Sample untouched fabric beside the band, never the previous stripe.
            cloth = np.asarray(Image.fromarray(column.astype(np.float32).reshape(256, 1)).resize(
                (1, h), Image.Resampling.BOX))
            values = np.rint(cloth * (1 - coverage[:, x0:x1]) + 12 * coverage[:, x0:x1]).clip(0, 255).astype(np.uint8)
            plane[:, x0:x1] = lookup[values]
        out[start:start + size] = swizzle_2d(plane.tobytes(), w, h, 1)
        cursor += size
    return bytes(out)


def finish_cincinnati(raw):
    """Only H5: broad pants tiger bands and the 2025 black rear helmet digits."""
    chunks = parse_chunks(raw)
    require(len(chunks) == 53 and chunks[2].kind == "TSET", "unexpected CIN kit inventory")
    out = bytearray(raw)
    c = chunks[2]
    decoded, _ = decode_chunk(raw, c)
    edited = _pants(decoded, c)
    if edited != decoded:
        out[c.offset:c.end_offset] = rebuild_compressed_chunk_fixed_span(raw[c.offset:c.end_offset], edited)[0]
    for value in range(10):
        source, target = chunks[13 + value], chunks[23 + value]
        decoded, _ = decode_chunk(raw, source)
        t = parse_texture(decoded, source)
        require((t.width, t.height, t.format_code) == (64, 64, 11), "unexpected CIN digit layout")
        old, _ = decode_chunk(raw, target)
        target_texture = parse_texture(old, target)
        require((target_texture.width, target_texture.height, target_texture.mip_levels,
                 target_texture.name, target.system_bytes, target.video_bytes) ==
                (32, 32, 3, "hn" + str(48 + value), 128, 2368),
                "CIN helmet digit storage differs")
        # Jersey level 1 is the native 32x32 helmet size. Copy its existing
        # levels 1..3 exactly, retaining the target hn48..hn57 descriptors.
        require((t.mip_levels, t.pixel_offset, t.palette_offset) == (4, 0, 5440),
                "CIN jersey numeral mip storage differs")
        edited = bytearray(old)
        edited[128:128 + 1344] = decoded[source.system_bytes + 4096:source.system_bytes + 5440]
        edited[128 + 1344:128 + 2368] = decoded[source.system_bytes + 5440:source.system_bytes + 6464]
        at = target.system_bytes + target_texture.palette_offset
        for index in range(256):
            b, g, r, a = edited[at + index * 4:at + index * 4 + 4]
            # Remove the orange outline, retain the native black face and alpha.
            edited[at + index * 4:at + index * 4 + 4] = bytes((0, 0, 0, 0 if r > g + 40 else a))
        if bytes(edited) != old:
            out[target.offset:target.end_offset] = rebuild_compressed_chunk_fixed_span(raw[target.offset:target.end_offset], bytes(edited))[0]
    c = chunks[51]
    decoded, _ = decode_chunk(raw, c)
    edited = _far_pants(decoded, c)
    if edited != decoded:
        out[c.offset:c.end_offset] = rebuild_compressed_chunk_fixed_span(raw[c.offset:c.end_offset], edited)[0]
    return bytes(out)


def _far_pants(decoded, chunk):
    """Carry the black tiger band into the distant player's pants atlas island."""
    import numpy as np
    from PIL import Image, ImageDraw
    t = parse_texture(decoded, chunk)
    require((t.width, t.height, t.format_code) == (256, 128, 11), "unexpected CIN far atlas")
    palette = np.frombuffer(decoded, dtype=np.uint8, count=1024,
        offset=chunk.system_bytes + t.palette_offset).reshape(256, 4)
    grey = palette[:, :3].astype(np.int32).mean(axis=1)
    choices = np.flatnonzero((palette[:, :3].max(axis=1).astype(int) -
        palette[:, :3].min(axis=1) < 35) & (palette[:, 3] == 255))
    require(len(choices) > 0, "far atlas has no neutral palette")
    lookup = choices[np.abs(grey[choices, None] - np.arange(256)[None, :]).argmin(axis=0)]
    mask = Image.new("L", (1024, 512), 0)
    draw = ImageDraw.Draw(mask)
    for row in range(7):
        y = row * 12
        draw.polygon([(42 * 4, (y + 18) * 4), (42 * 4, (y + 9) * 4),
                      (68 * 4, (y + 3) * 4), (61 * 4, (y + 11) * 4)], fill=255)
    base = np.frombuffer(unswizzle_2d(decoded[chunk.system_bytes + t.pixel_offset:
        chunk.system_bytes + t.pixel_offset + 256 * 128], 256, 128, 1), dtype=np.uint8).reshape(128, 256)
    fabric = Image.fromarray(np.maximum(grey[base[:, 40]], grey[base[:, 72]]).astype(np.float32).reshape(128, 1))
    out, cursor = bytearray(decoded), t.pixel_offset
    for level in range(t.mip_levels):
        w, h = max(1, 256 >> level), max(1, 128 >> level)
        start, size = chunk.system_bytes + cursor, w * h
        plane = np.frombuffer(unswizzle_2d(decoded[start:start + size], w, h, 1), dtype=np.uint8).reshape(h, w).copy()
        cov = np.asarray(mask.resize((w, h), Image.Resampling.BOX), dtype=np.float64) / 255
        x0, x1, y1 = 42 >> level, min(w, (68 + (1 << level) - 1) >> level), min(h, 90 >> level)
        cloth = np.asarray(fabric.resize((1, h), Image.Resampling.BOX))[:y1]
        values = np.rint(cloth * (1 - cov[:y1, x0:x1]) + 12 * cov[:y1, x0:x1]).clip(0, 255).astype(np.uint8)
        plane[:y1, x0:x1] = lookup[values]
        out[start:start + size] = swizzle_2d(plane.tobytes(), w, h, 1)
        cursor += size
    return bytes(out)


def apply_to_image(path):
    """Finish the two kits when the disc's Unc Bowl actually selects H5/A4.

    Retail and other moment selections are left to their own owners. Read all
    inputs and compile both packages before writing either package.
    """
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        situ_entry = index.entries[22]
        require(situ_entry.name_id == 0x3F407CF4, "unexpected SITU resource identity")
        situ = image.read_segments(index.sub_extents(situ_entry, 0, situ_entry.size))
        if not unc_bowl_uses_slots(situ):
            return dict(state="other_moment_slots", changed=False)
        entries = {bump.logical_name_for(e.name_id): e for e in index.entries}
        read = lambda name: image.read_segments(index.sub_extents(entries[name], 0, entries[name].size))
        originals = {name: read(name) for name in OWNED}
        specs = {name: validate_owned(name, raw) for name, raw in originals.items()}
        fixed = {"06H5.IFF": finish_cincinnati(originals["06H5.IFF"]),
                 "22A4.IFF": finish_pittsburgh(originals["22A4.IFF"], read("22H0.IFF"))}
        for name, data in fixed.items():
            require(all(sha(data[p["offset"]:p["offset"] + p["length"]]) == p["after_sha256"]
                        for p in specs[name]["spans"]), "compiled Unc Bowl uniform differs from output pins")
        for name, data in fixed.items():
            if data != originals[name]:
                image.write_segments(index.sub_extents(entries[name], 0, len(data)), data)
            require(read(name) == data, "Unc Bowl kit read-back differs")
        return dict(state="applied", runtime_witnessed=False,
                    resources={name: dict(before_sha256=sha(originals[name]), after_sha256=sha(data),
                                          changed=data != originals[name]) for name, data in fixed.items()})


def unc_bowl_uses_slots(situ):
    """Physical row 51 is zero-based row 50. Check teams as well as styles."""
    require(situ[:4] == b"SITU" and situ[44:48] == b"SITU", "unexpected situation wrapper")
    count = struct.unpack_from("<I", situ, 96)[0]
    if count < 51:
        return False
    at = 32 + 0x44 + 50 * 0x6C
    require(len(situ) >= at + 0x6C, "truncated situation table")
    if struct.unpack_from("<II", situ, at + 0x58) != (4, 5):
        return False
    if struct.unpack_from("<II", situ, at + 0x1C) != (2025, 2025):
        return False
    for field, text in ((0x14, "steelers"), (0x18, "bengals")):
        pointer = at + field
        target = pointer - 1 + struct.unpack_from("<i", situ, pointer)[0]
        if target < 0 or situ[target:target + 2 * (len(text) + 1)] != (text + "\0").encode("utf-16le"):
            return False
    return True
