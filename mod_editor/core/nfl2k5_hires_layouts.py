"""Pinned shared-palette TSET and append-only SCNE texture layouts.

SCNE keeps all original video bytes, including the now-unused native logo.
Only its selected descriptor points at an aligned appended raster. This avoids
moving any vertex buffer, command, other texture, or self-relative pointer.
TSET replaces the shared index chain and BOTH authored clean/mud palettes.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from functools import lru_cache
import struct

from . import nfl2k5_hires_texture as t


def inspect_span(raw, asset):
    limit = t.MAX_SCENE_SPAN if asset.kind == "SCNE" else t.MAX_SPAN
    t.require(isinstance(raw, bytes) and 42 <= len(raw) <= limit, "Texture span exceeds bounds")
    kind, stored, system, video, magic, scratch, r0, r1 = t.txtr.HEADER.unpack_from(raw)
    t.require(kind == asset.kind.encode() and stored == len(raw)-32 and stored % 16 == 0
              and system == asset.system_size and magic == t.txtr.COMPRESSED_SENTINEL
              and r0 == r1 == 0 and 0 <= scratch <= limit and scratch % 16 == 0,
              "Foreign texture wrapper")
    appended = (asset.original_video+127) & ~127
    sizes = {asset.video_size(s)+(appended if asset.kind == "SCNE" else 0): s for s in (1, 2)}
    retail_scene = asset.kind == "SCNE" and video == asset.original_video
    t.require(retail_scene or video in sizes, "Foreign texture video allocation")
    scale = 1 if retail_scene else sizes[video]
    t.require(system+video <= 16*1024**2, "Decoded resource exceeds 16 MiB")
    chunk = t.txtr.parse_chunks(raw)[0]
    decoded, compression = t.txtr.decode_chunk(raw, chunk)
    t.require(compression.stream_tag == asset.stream_tag and compression.offset_bits == asset.offset_bits,
              "Foreign VC-LZ stream parameters")
    minimum = t.txtr.minimum_vc_lz_overlap_scratch(raw[32:32+compression.consumed_bytes], stored, len(decoded))
    t.require(scratch >= max(minimum, stored-compression.consumed_bytes, stored-len(decoded)),
              "Unsafe in-place decompression scratch")
    descriptors = (asset.descriptor, asset.second_descriptor) if asset.kind == "TSET" else (asset.descriptor,)
    base = bytearray(decoded[:system+asset.original_video] if asset.kind == "SCNE" else decoded[:system])
    chain = asset.video_size(scale)-1024*asset.palette_count
    pixel = asset.original_pixels if retail_scene else appended if asset.kind == "SCNE" else 0
    palette_at = asset.original_palette if retail_scene else pixel+chain
    native_chain = asset.video_size(1)-1024*asset.palette_count
    for i, descriptor in enumerate(descriptors):
        t.require(0 <= descriptor <= system-24, "Descriptor outside system object")
        words = struct.unpack_from("<6I", decoded, descriptor)
        t.require(words[1:5] == (pixel, palette_at+i*1024, asset.format_word(scale), 0)
                  and words[5] == 0x80000000, "Foreign texture descriptor or shared layout")
        struct.pack_into("<III", base, descriptor+4,
                         asset.original_pixels if asset.kind == "SCNE" else 0,
                         asset.original_palette if asset.kind == "SCNE" else native_chain+i*1024,
                         asset.format_word(1))
    if asset.kind == "SCNE":
        t.require(t.sha(base) == asset.baseline_sha256, "Foreign scene baseline")
        if not retail_scene:
            t.require(not any(decoded[system+asset.original_video:system+appended]), "Foreign append alignment")
    else:
        t.require(t.sha(base) == asset.system_sha256, "Foreign texture system object")
    levels = []
    for palette_index in range(asset.palette_count):
        palette = t.palettes.parse_palette(decoded[system:], palette_at+palette_index*1024)
        at = system+pixel
        for level, (width, height) in enumerate(asset.dimensions(scale)):
            indices = t.txtr.unswizzle_2d(decoded[at:at+width*height], width, height, 1)
            levels.append(dict(level=level, palette=palette_index, width=width, height=height,
                               index_sha256=t.sha(indices), rgba_sha256=t.sha(t.palettes.rgba_from_indices(indices, palette))))
            at += width*height
    return dict(key=asset.key, scale=scale, kind=asset.kind, span_sha256=t.sha(raw),
                decoded_sha256=t.sha(decoded), system_bytes=system, video_bytes=video,
                texture_video_bytes=asset.video_size(scale), stored_bytes=stored, span_bytes=len(raw),
                scratch_bytes=scratch, load_allocation_bytes=system+video+scratch,
                palette_offset=palette_at, compression=asdict(compression), minimum_overlap_scratch=minimum,
                retained_native_video_bytes=asset.original_video if asset.kind == "SCNE" else 0,
                mips=levels), bytes(base)


def paired_palette(clean, mud):
    """One index per texel, two RGBA palettes; median cut in eight channels.

    A work limit prevents adversarial paired photographs from causing an
    unbounded nearest-colour search. Ordinary single-palette imports retain
    the inherited quantizer and its exact output.
    """
    colors = [[a.rgba[i:i+4]+b.rgba[i:i+4] for i in range(0, len(a.rgba), 4)] for a, b in zip(clean, mud)]
    histogram = Counter(color for level in colors for color in level)
    t.require(len(histogram) <= 8192, "Jersey pair exceeds 8192 shared colors across mips; reduce input colors")
    boxes = [sorted(histogram)]
    while len(boxes) < 256:
        choices = []
        for i, box in enumerate(boxes):
            if len(box) < 2:
                continue
            ranges = [max(c[ch] for c in box)-min(c[ch] for c in box) for ch in range(8)]
            channel = max(range(8), key=lambda ch: (ranges[ch], -ch))
            choices.append((ranges[channel], sum(histogram[c] for c in box), -i, channel))
        if not choices:
            break
        _, _, neg_i, channel = max(choices)
        i = -neg_i
        box = sorted(boxes[i], key=lambda c: (c[channel], c))
        halfway = (sum(histogram[c] for c in box)+1)//2
        weight, cut = 0, 0
        for cut, color in enumerate(box[:-1], 1):
            weight += histogram[color]
            if weight >= halfway:
                break
        boxes[i:i+1] = [box[:cut], box[cut:]]
    palette = []
    for box in boxes:
        weight = sum(histogram[c] for c in box)
        palette.append(tuple((sum(c[ch]*histogram[c] for c in box)+weight//2)//weight for ch in range(8)))
    mapping, squared, maximum, changed = {}, 0, 0, 0
    for color, count in sorted(histogram.items()):
        index = min(range(len(palette)), key=lambda j: (sum((x-y)**2 for x, y in zip(color, palette[j])), j))
        mapping[color] = index
        error = [abs(x-y) for x, y in zip(color, palette[index])]
        maximum = max(maximum, *error)
        squared += count*sum(e*e for e in error)
        changed += count*bool(max(error))
    return ([p[:4] for p in palette], [p[4:] for p in palette]), [bytes(mapping[c] for c in level) for level in colors], dict(
        input_unique_rgba_pairs=len(histogram), palette_entries=len(palette), maximum_channel_error=maximum,
        total_squared_rgba_error=squared, differing_pixel_count=changed, total_pixel_count=sum(histogram.values()))


def compile_texture(base, rgba, asset, scale):
    asset.dimensions(scale)
    t.require(t.sha(base) == (asset.baseline_sha256 if asset.kind == "SCNE" else asset.system_sha256),
              "Compiler requires the pinned native resource")
    if asset.kind == "TSET":
        t.require(isinstance(rgba, tuple) and len(rgba) == 2
                  and all(len(r) == asset.native*asset.height*16 for r in rgba), "Supply both clean and mud rasters")
        chains = [t._mips(r, asset, scale) for r in rgba]
        palettes, indices, quality = _paired_raster(rgba, asset.native, asset.height, asset.levels, scale)
    else:
        t.require(isinstance(rgba, bytes) and len(rgba) == asset.native*asset.height*16, "Authored raster size differs")
        chains = [t._mips(rgba, asset, scale)]
        palette, indices, quality = t._quantized(rgba, asset.native, asset.height, asset.levels, scale)
        palettes = [palette]
    pixels = b"".join(t.txtr.swizzle_2d(ind, level.width, level.height, 1) for ind, level in zip(indices, chains[0]))
    video = pixels+b"".join(t.palettes.palette_bytes(p) for p in palettes)
    header = bytearray(base)
    pixel = (asset.original_video+127) & ~127 if asset.kind == "SCNE" else 0
    descriptors = (asset.descriptor, asset.second_descriptor) if asset.kind == "TSET" else (asset.descriptor,)
    for i, descriptor in enumerate(descriptors):
        struct.pack_into("<III", header, descriptor+4, pixel, pixel+len(pixels)+i*1024, asset.format_word(scale))
    decoded = bytes(header)+bytes(pixel-asset.original_video if asset.kind == "SCNE" else 0)+video
    limit = t.MAX_SCENE_SPAN if asset.kind == "SCNE" else t.MAX_SPAN
    encoded, compression = t.txtr.compress_vc_lz(decoded, stream_tag=asset.stream_tag, offset_bits=asset.offset_bits,
        max_encoded_size=limit-32, max_candidate_comparisons=50_000_000)
    stored = (len(encoded)+15) & ~15
    minimum = t.txtr.minimum_vc_lz_overlap_scratch(encoded, stored, len(decoded))
    scratch = (max(minimum, stored-len(encoded), stored-len(decoded))+15) & ~15
    raw = t.txtr.HEADER.pack(asset.kind.encode(), stored, asset.system_size, len(decoded)-asset.system_size,
                           t.txtr.COMPRESSED_SENTINEL, scratch, 0, 0)+encoded+bytes(stored-len(encoded))
    checked, _ = inspect_span(raw, asset)
    for palette_i, palette in enumerate(palettes):
        for level, ind in enumerate(indices):
            t.require(checked['mips'][palette_i*asset.levels+level]['rgba_sha256'] ==
                      t.sha(t.palettes.rgba_from_indices(ind, palette)), "Mip read-back differs")
    return raw, dict(compiler=t.VERSION, quality=dict(quality), encoder=asdict(compression), decoded=checked,
                     mip_policy="retain-retail-count", mip_filter="RGBA box, round half up",
                     layout="append logo without moving original scene data" if asset.kind == "SCNE" else "one chain, two authored palettes",
                     authored_rgba_sha256=[t.sha(r) for r in rgba] if isinstance(rgba, tuple) else t.sha(rgba))


@lru_cache(maxsize=4)
def _paired_raster(rgba, width, height, levels, scale):
    return paired_palette(*(t._raster_mips(r, width, height, levels, scale) for r in rgba))
