#!/usr/bin/env python3
"""Replace any inventoried NFL 2K5 P8 texture in a layout-identical XISO copy.

The editor already located every TXTR on the disc, but only a curated handful
were replaceable: uniforms, live faces, portraits, the Crib, create-team field
art.  Everything else a modder can see in the inventory -- the goalpost pads,
the real teams' end-zone art, grass and the transparent overlays laid over it,
field lines, helmet reflections, shared equipment like ``shoes_taped`` and
``wristband_qb``, even the tailgate props -- had no way to be edited.  This is
the general lane: name a package and a texture inside it, hand it a PNG, get a
patched copy of your own disc.

Three properties make that safe enough to ship:

* **Fixed span.**  Every replacement is recompressed into the exact byte span
  the original occupied, so archive traversal, every descriptor, and the
  position of every other resource are untouched.  A PNG that cannot be made
  to fit is refused rather than shifting the disc around.
* **Per-extent identity, never the container.**  Image size, the sector a file
  landed on, and therefore its absolute byte offset all describe how a disc was
  dumped, not which game it is -- extract-xiso relocates every file.  Identity
  is the exact size and SHA-256 of ``default.xbe`` and of each pack this plan
  actually touches.
* **Copy only.**  The source is opened read-only, hashed before and after, and
  the output is a fresh file that never aliases it.

An outer package -- and, in one measured retail case, the selected TXTR itself
-- may cross a physical pack boundary.  The replacement is still built as one
exact logical TXTR span, then split back across the source-owned extents.  All
pieces are staged before the new XISO is reserved, written into that fresh copy,
and independently read back before the copy is kept.
"""

from __future__ import annotations

import argparse
import dataclasses
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import nfl_uniform_color_xiso_direct_patch as common
import nfl_tset_png_import as palette_tools
from nfl_outer import parse_archive, read_entry_bytes
from nfl_txtr import (HEADER, Chunk, TxtrError, compress_vc_lz, decode_chunk,
                      parse_chunks, parse_texture,
                      rebuild_compressed_chunk_fixed_span, swizzle_2d)


SCHEMA = "nfl2k5_all_texture_xiso_workflow/v1"
PLAN_SCHEMA = "nfl2k5_all_texture_plan/v1"
PACK_ROOT = "vc_53450030"
PALETTE_BYTES = 1024
MAX_PLAN_BYTES = 16 * 1024 * 1024
MAX_EDITS = 512
SUPPORTED_FORMATS = ("P8", "A1R5G5B5")
PLAYER_STRIP_NAMES = frozenset({
    "p001", "p002", "p003", "p004", "p005", "p006",
    "p011", "p012", "p013", "p014", "p015", "p016",
})
RAW_P8_SLOT_ARRAYS = {
    # outer index: (complete size, fixed slot size, slot count, name CRC)
    3_096: (1_704_192, 5_376, 317, 0xF50B1A31),       # flipchip.cdf
    3_102: (105_903_360, 66_816, 1_585, 0x823E3053),  # logos.cdf
    3_103: (5_123_328, 5_376, 953, 0x48F8908C),       # mini.cdf
}


class TextureWorkflowError(ValueError):
    """Raised when an input, target, or output fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TextureWorkflowError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class PhysicalSpan:
    """One ordered physical slice of a logical TXTR span."""

    pack_name: str
    pack_relative_offset: int
    replacement_offset: int
    size: int
    span_sha256: str


@dataclass(frozen=True)
class ResolvedTarget:
    pack_name: str
    outer_index: int
    chunk_index: int
    texture: str
    width: int
    height: int
    mip_levels: int
    format_name: str
    packed_size: int
    pixel_chain_bytes: int
    pixel_offset: int
    palette_offset: int
    system_bytes: int
    video_bytes: int
    pack_relative_offset: int
    span_size: int
    span_sha256: str
    decoded: bytes
    template_span: bytes
    chunk: Chunk
    physical_spans: tuple[PhysicalSpan, ...]


def _physical_spans(entry: Any, offset: int, payload: bytes) \
        -> tuple[PhysicalSpan, ...]:
    """Map a logical entry range to every physical pack slice, in order."""

    require(offset >= 0 and offset + len(payload) <= entry.size,
            "TXTR span lies outside its outer package")
    result: list[PhysicalSpan] = []
    logical_start = 0
    replacement_offset = 0
    range_end = offset + len(payload)
    for segment in entry.segments:
        logical_end = logical_start + segment.size
        part_start = max(offset, logical_start)
        part_end = min(range_end, logical_end)
        if part_start < part_end:
            size = part_end - part_start
            piece = payload[replacement_offset:replacement_offset + size]
            require(len(piece) == size, "TXTR physical split is incomplete")
            result.append(PhysicalSpan(
                pack_name=segment.pack_name,
                pack_relative_offset=(
                    segment.pack_offset + part_start - logical_start
                ),
                replacement_offset=replacement_offset,
                size=size,
                span_sha256=digest(piece),
            ))
            replacement_offset += size
        logical_start = logical_end
        if part_end == range_end:
            break
    require(result and replacement_offset == len(payload),
            "TXTR span could not be mapped across physical packs")
    require(len(result) <= 2,
            "TXTR span reaches more than two physical packs")
    return tuple(result)


def read_plan(path: Path) -> tuple[Path, bytes, list[dict[str, Any]]]:
    plan = path.resolve(strict=True)
    info = plan.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            "plan must be a regular, non-symlink file")
    require(info.st_size <= MAX_PLAN_BYTES, "plan file is too large")
    payload = plan.read_bytes()
    document = json.loads(payload.decode("utf-8"))
    require(isinstance(document, dict) and document.get("schema") == PLAN_SCHEMA,
            f"plan schema must be {PLAN_SCHEMA}")
    edits = document.get("edits")
    require(isinstance(edits, list) and 1 <= len(edits) <= MAX_EDITS,
            f"plan must carry 1..{MAX_EDITS} edits")
    fields = {"outer_index", "texture", "png"}
    for edit in edits:
        require(isinstance(edit, dict) and set(edit) == fields,
                f"each edit must carry exactly {sorted(fields)}")
        require(type(edit["outer_index"]) is int and edit["outer_index"] >= 0,
                "edit outer_index must be a non-negative integer")
        require(isinstance(edit["texture"], str) and edit["texture"],
                "edit texture must be a name")
        require(isinstance(edit["png"], str) and edit["png"], "edit png must be a path")
    return plan, payload, edits


def resolve_target(archive: Any, outer_index: int, texture: str) -> ResolvedTarget:
    """Find one named P8 TXTR inside one outer package, fail-closed."""
    require(0 <= outer_index < len(archive.entries),
            f"outer index {outer_index} is outside this archive")
    entry = archive.entries[outer_index]
    data = read_entry_bytes(archive, entry)
    matches: list[tuple[int, Chunk, bytes, Any]] = []
    raw_layout = RAW_P8_SLOT_ARRAYS.get(outer_index)
    if raw_layout is None:
        candidate_chunks = tuple(enumerate(parse_chunks(data, allow_trailing=True)))
    else:
        outer_size, slot_size, slot_count, outer_name_id = raw_layout
        require(
            entry.name_id == outer_name_id
            and entry.size == len(data) == outer_size == slot_size * slot_count,
            f"outer {outer_index} no longer has its reviewed raw fixed-slot layout",
        )
        raw_candidates: list[tuple[int, Chunk]] = []
        for position in range(slot_count):
            offset = position * slot_size
            fields = HEADER.unpack_from(data, offset)
            chunk = Chunk(
                index=position,
                offset=offset,
                kind=fields[0].decode("ascii", errors="replace"),
                stored_size=fields[1],
                system_bytes=fields[2],
                video_bytes=fields[3],
                compression_magic=fields[4],
                overlap_scratch_bytes=fields[5],
                reserved0=fields[6],
                reserved1=fields[7],
            )
            # Read only the tiny descriptor while searching. Decoding every
            # 256x256 slot would copy the entire 106 MB logos.cdf once per edit.
            try:
                descriptor = data[
                    chunk.body_offset:chunk.body_offset + chunk.system_bytes
                ]
                candidate_info = parse_texture(descriptor, chunk)
            except (TxtrError, UnicodeError):
                continue
            if candidate_info.name == texture:
                raw_candidates.append((position, chunk))
        candidate_chunks = tuple(raw_candidates)
    for position, chunk in candidate_chunks:
        if chunk.kind != "TXTR":
            continue
        try:
            decoded, _info = decode_chunk(data, chunk)
            info = parse_texture(decoded, chunk)
        except Exception:  # noqa: BLE001 - a chunk we cannot read is simply skipped
            continue
        if info.name == texture:
            if raw_layout is not None:
                _outer_size, slot_size, _slot_count, _outer_name_id = raw_layout
                span_end = chunk.offset + HEADER.size + chunk.stored_size
                require(
                    span_end + 96 == (position + 1) * slot_size
                    and data[span_end:span_end + 96] == bytes(96),
                    f"{texture} fixed-slot padding changed",
                )
            matches.append((position, chunk, decoded, info))
    require(matches, f"outer {outer_index} has no TXTR named {texture!r}")
    require(len(matches) == 1,
            f"outer {outer_index} has {len(matches)} textures named {texture!r}")
    position, chunk, decoded, info = matches[0]
    require(info.format_name in SUPPORTED_FORMATS,
            f"{texture} is {info.format_name}; this lane replaces "
            f"{'/'.join(SUPPORTED_FORMATS)} textures only")
    require(info.pixel_offset == 0,
            f"{texture} does not begin its pixel chain at the video buffer start")
    span_size = HEADER.size + chunk.stored_size
    require(chunk.offset + span_size <= len(data),
            f"{texture} span runs past the end of outer {outer_index}")
    bytes_per_pixel = 1 if info.format_name == "P8" else 2
    expected_chain = sum(
        max(1, info.width >> level) * max(1, info.height >> level)
        * bytes_per_pixel
        for level in range(info.mip_levels)
    )
    if info.format_name == "P8":
        require(info.packed_size == 0,
                f"{texture} stores linear P8 pixels; that layout is unsupported")
        require(info.palette_offset == expected_chain,
                f"{texture} palette does not follow its {info.mip_levels}-level chain")
        require(info.palette_offset + PALETTE_BYTES <= chunk.video_bytes,
                f"{texture} palette runs past its video buffer")
    else:
        # These twelve explicit-size strips are the complete proved A1 lane.
        # Their five linear mip levels occupy the prefix computed above; the
        # small source-owned tail is retained byte-for-byte.  Do not infer this
        # contract for crowdbase, seat, or an arbitrary 16-bit texture.
        require(texture in PLAYER_STRIP_NAMES,
                f"{texture} is not a reviewed A1R5G5B5 player strip")
        require(info.packed_size != 0 and info.palette_offset == 0,
                f"{texture} does not use the reviewed explicit-size A1 layout")
        require(info.mip_levels == 5 and info.dimensions == 2 and info.depth == 1,
                f"{texture} A1 descriptor shape changed")
        require(expected_chain <= chunk.video_bytes,
                f"{texture} A1 mip chain runs past its video buffer")
        require(
            chunk.video_bytes - expected_chain == (info.width * 3) // 2,
            f"{texture} A1 source-owned video tail changed",
        )
    template_span = data[chunk.offset:chunk.offset + span_size]
    physical_spans = _physical_spans(entry, chunk.offset, template_span)
    first_span = physical_spans[0]
    return ResolvedTarget(
        pack_name=first_span.pack_name,
        outer_index=outer_index,
        chunk_index=position,
        texture=texture,
        width=info.width,
        height=info.height,
        mip_levels=info.mip_levels,
        format_name=info.format_name,
        packed_size=info.packed_size,
        pixel_chain_bytes=expected_chain,
        pixel_offset=info.pixel_offset,
        palette_offset=info.palette_offset,
        system_bytes=chunk.system_bytes,
        video_bytes=chunk.video_bytes,
        pack_relative_offset=first_span.pack_relative_offset,
        span_size=span_size,
        span_sha256=digest(template_span),
        decoded=decoded,
        template_span=template_span,
        chunk=chunk,
        physical_spans=physical_spans,
    )


def generate_mips(rgba: bytes, width: int, height: int,
                  levels: int) -> list[Any]:
    """Box-filter mip chain for an arbitrary texture size.

    ``palette_tools.generate_mips`` computes exactly this, then asserts the
    result equals the jersey TSET's pinned 512x256 chain -- correct for that
    target, useless for the other 57,000 textures. The arithmetic below is the
    same box filter with the pin replaced by the level count the retail
    descriptor actually declares.
    """
    require(len(rgba) == width * height * 4, "base RGBA size mismatch")
    result = [palette_tools.MipLevel(0, width, height, rgba)]
    current, current_width, current_height = rgba, width, height
    for level in range(1, levels):
        require(current_width % 2 == 0 and current_height % 2 == 0,
                f"{width}x{height} cannot be halved {levels - 1} times exactly")
        next_width, next_height = current_width // 2, current_height // 2
        downsampled = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            for x in range(next_width):
                sources = (
                    ((y * 2) * current_width + x * 2) * 4,
                    ((y * 2) * current_width + x * 2 + 1) * 4,
                    (((y * 2) + 1) * current_width + x * 2) * 4,
                    (((y * 2) + 1) * current_width + x * 2 + 1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    total = sum(current[source + channel] for source in sources)
                    downsampled[target + channel] = (total + 2) // 4
        current = bytes(downsampled)
        current_width, current_height = next_width, next_height
        result.append(palette_tools.MipLevel(level, current_width, current_height, current))
    return result


def build_replacement(target: ResolvedTarget,
                      png_path: Path) -> tuple[bytes, dict[str, Any]]:
    """Quantize a PNG into this target's own palette layout and refit its span."""
    # palette_tools.read_rgba_png is pinned to the jersey TSET's 512x256, so
    # read through the underlying decoder with THIS texture's dimensions.
    resolved_png = png_path.resolve(strict=True)
    png_info = resolved_png.lstat()
    require(stat.S_ISREG(png_info.st_mode) and not stat.S_ISLNK(png_info.st_mode),
            f"PNG must be a regular, non-symlink file: {png_path}")
    require(png_info.st_size <= palette_tools.MAX_PNG_BYTES,
            "PNG exceeds the 32 MiB file bound")
    png_payload = resolved_png.read_bytes()
    png_sha256 = digest(png_payload)
    width, height, rgba = palette_tools.decode_rgba_png(
        png_payload, (target.width, target.height))
    levels = generate_mips(rgba, width, height, target.mip_levels)
    require(len(levels) == target.mip_levels, "mip generation level-count mismatch")
    if target.format_name == "A1R5G5B5":
        return _build_a1r5g5b5_replacement(
            target, levels, png_sha256, width, height
        )

    def candidate_decoded(
        candidate_palette: list[tuple[int, int, int, int]],
        candidate_levels: list[bytes],
    ) -> bytes:
        require(len(candidate_levels) == len(levels),
                "quantized mip level count changed")
        chain = b"".join(
            swizzle_2d(indices, level.width, level.height, 1)
            for level, indices in zip(levels, candidate_levels)
        )
        require(len(chain) == target.palette_offset,
                "encoded index chain does not fill the retail chain span")
        rebuilt = bytearray(target.decoded)
        video = target.system_bytes
        rebuilt[video:video + len(chain)] = chain
        encoded_palette = palette_tools.palette_bytes(candidate_palette)
        require(len(encoded_palette) == PALETTE_BYTES,
                "encoded palette size mismatch")
        rebuilt[video + target.palette_offset:
                video + target.palette_offset + PALETTE_BYTES] = encoded_palette
        result = bytes(rebuilt)
        require(len(result) == len(target.decoded),
                "rebuilt texture payload changed size")
        return result

    # logos.cdf, mini.cdf, and flipchip.cdf use the same raw fixed-slot P8
    # transport already proved by the Team Select card importer.  There is no
    # VC-LZ stream to refit: retain the wrapper, descriptor/system bytes, and
    # any source-owned video tail, then replace only the swizzled index chain
    # and 1,024-byte palette.  Keeping this branch here lets All Textures use
    # its existing typed project/composed-XISO route without inventing a
    # parallel menu-logo writer.
    if not target.chunk.compressed:
        require(
            target.chunk.compression_magic == 0
            and target.chunk.stored_size
            == target.chunk.system_bytes + target.chunk.video_bytes
            and target.chunk.overlap_scratch_bytes == 0
            and target.chunk.reserved0 == 0
            and target.chunk.reserved1 == 0,
            f"{target.texture} is not the reviewed raw TXTR wrapper class",
        )
        palette, index_levels, quantization = palette_tools.quantize_levels(levels)
        rebuilt_decoded = candidate_decoded(palette, index_levels)
        rebuilt_span = target.template_span[:HEADER.size] + rebuilt_decoded
        require(
            len(rebuilt_span) == len(target.template_span)
            and rebuilt_span[:HEADER.size] == target.template_span[:HEADER.size]
            and rebuilt_decoded[:target.system_bytes]
            == target.decoded[:target.system_bytes],
            "raw P8 wrapper, descriptor, or fixed span changed",
        )
        standalone = dataclasses.replace(target.chunk, offset=0)
        roundtrip, decode_info = decode_chunk(rebuilt_span, standalone)
        require(
            decode_info is None and roundtrip == rebuilt_decoded,
            "rebuilt raw P8 span does not decode back to its authored payload",
        )
        runs = [
            index for index, (before, after) in enumerate(
                zip(target.template_span, rebuilt_span)
            ) if before != after
        ]
        require(runs, "input PNG quantized to the retail target unchanged")
        require(
            min(runs) >= HEADER.size + target.system_bytes
            and max(runs) < HEADER.size + target.system_bytes + target.video_bytes,
            "raw P8 differences escape the video allocation",
        )
        return rebuilt_span, {
            "png_sha256": png_sha256,
            "png_width": width,
            "png_height": height,
            "format": "P8",
            "mip_levels": target.mip_levels,
            "palette_entries": quantization.get("palette_entries"),
            "raw_uncompressed_fixed_span": True,
            "vc_lz_not_applicable": True,
            "rebuilt_span_sha256": digest(rebuilt_span),
            "rebuilt_decoded_sha256": digest(rebuilt_decoded),
            "changed_byte_count": len(runs),
            "wrapper_identical": True,
            "system_bytes_identical": True,
        }

    template_stream = target.template_span[HEADER.size:]
    require(len(template_stream) >= 9,
            "compressed retail texture stream prefix is truncated")
    output_size, stream_tag = struct.unpack_from("<II", template_stream, 0)
    offset_bits = template_stream[8]
    require(output_size == len(target.decoded),
            "compressed retail texture output size changed")
    bounded = palette_tools.quantize_levels_to_vc_lz_bound(
        levels,
        candidate_decoded,
        stream_tag=stream_tag,
        offset_bits=offset_bits,
        max_encoded_size=target.chunk.stored_size,
    )
    palette = bounded.palette
    index_levels = bounded.index_levels
    quantization = bounded.quantization
    rebuilt_decoded = bounded.decoded
    rebuilt_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
        target.template_span, rebuilt_decoded)
    require(len(rebuilt_span) == len(target.template_span),
            "rebuilt span size differs from the retail span")
    require(
        rebuild_info.recompressed_bytes == len(bounded.compressed)
        and rebuilt_span[HEADER.size:
                         HEADER.size + len(bounded.compressed)] == bounded.compressed,
        "bounded-palette stream differs from the fixed-span rebuild",
    )
    # target.chunk.offset points into the whole package; the rebuilt span is
    # standalone, so decode it through a copy anchored at its own byte 0.
    standalone = dataclasses.replace(target.chunk, offset=0)
    roundtrip, _info = decode_chunk(rebuilt_span, standalone)
    require(roundtrip == rebuilt_decoded,
            "rebuilt span does not decode back to the payload it was built from")
    report = {
        "png_sha256": png_sha256,
        "png_width": width,
        "png_height": height,
        "palette_entries": quantization.get("palette_entries"),
        "mip_levels": target.mip_levels,
        "rebuilt_span_sha256": digest(rebuilt_span),
        "rebuilt_decoded_sha256": digest(rebuilt_decoded),
        "recompressed_bytes": rebuild_info.recompressed_bytes,
        "zero_padding_bytes": rebuild_info.zero_padding_bytes,
    }
    if len(bounded.attempts) > 1:
        report["bounded_palette_fit"] = {
            "attempts": list(bounded.attempts),
            "selected_palette_entries": len(palette),
            "selected_encoded_bytes": len(bounded.compressed),
            "stored_size_bound": target.chunk.stored_size,
        }
    return rebuilt_span, report


def _a1r5g5b5_level(rgba: bytes, *, retained_bits: int) -> bytes:
    """Encode one linear A1R5G5B5 level with deterministic colour fallback.

    The native five-bit candidate is tried first.  When authored noise cannot
    fit the retail VC-LZ allocation, progressively clearing low colour bits
    lowers entropy without changing dimensions, mip ownership, alpha shape, or
    any descriptor bytes.  A one-bit-per-channel image is the last usable tier;
    the writer refuses rather than flattening the art to one colour.
    """

    require(1 <= retained_bits <= 5, "A1 retained colour bits must be 1..5")
    require(len(rgba) % 4 == 0, "A1 RGBA byte count is not pixel-aligned")
    low_mask = (1 << (5 - retained_bits)) - 1
    encoded = bytearray(len(rgba) // 2)
    for source in range(0, len(rgba), 4):
        red5 = (rgba[source] * 31 + 127) // 255
        green5 = (rgba[source + 1] * 31 + 127) // 255
        blue5 = (rgba[source + 2] * 31 + 127) // 255
        if low_mask:
            red5 &= ~low_mask
            green5 &= ~low_mask
            blue5 &= ~low_mask
        value = (
            (0x8000 if rgba[source + 3] >= 128 else 0)
            | (red5 << 10) | (green5 << 5) | blue5
        )
        target_offset = source // 2
        encoded[target_offset:target_offset + 2] = value.to_bytes(2, "little")
    return bytes(encoded)


def _is_size_overflow(exc: TxtrError) -> bool:
    message = str(exc)
    return (
        message.startswith("VC-LZ stream needs more than the ")
        or (message.startswith("VC-LZ stream is ") and " exceeds " in message)
    )


def _build_a1r5g5b5_replacement(
    target: ResolvedTarget,
    levels: list[Any],
    png_sha256: str,
    width: int,
    height: int,
) -> tuple[bytes, dict[str, Any]]:
    """Rebuild a reviewed explicit-size player strip in its exact span."""

    require(target.texture in PLAYER_STRIP_NAMES,
            "A1 replacement target is not a reviewed player strip")
    template_stream = target.template_span[HEADER.size:]
    require(len(template_stream) >= 9,
            "compressed retail A1 texture stream prefix is truncated")
    output_size, stream_tag = struct.unpack_from("<II", template_stream, 0)
    offset_bits = template_stream[8]
    require(output_size == len(target.decoded),
            "compressed retail A1 texture output size changed")

    attempts: list[dict[str, object]] = []
    selected_decoded: bytes | None = None
    selected_compressed: bytes | None = None
    selected_bits: int | None = None
    for retained_bits in (5, 4, 3, 2, 1):
        chain = b"".join(
            _a1r5g5b5_level(level.rgba, retained_bits=retained_bits)
            for level in levels
        )
        require(len(chain) == target.pixel_chain_bytes,
                "encoded A1 mip chain does not fill its reviewed prefix")
        rebuilt = bytearray(target.decoded)
        video = target.system_bytes
        tail_before = bytes(rebuilt[
            video + target.pixel_chain_bytes:video + target.video_bytes
        ])
        rebuilt[video:video + len(chain)] = chain
        decoded = bytes(rebuilt)
        require(
            decoded[video + target.pixel_chain_bytes:video + target.video_bytes]
            == tail_before,
            "A1 source-owned video tail changed",
        )
        try:
            compressed, _compression = compress_vc_lz(
                decoded,
                stream_tag=stream_tag,
                offset_bits=offset_bits,
                max_encoded_size=target.chunk.stored_size,
            )
        except TxtrError as exc:
            if not _is_size_overflow(exc):
                raise
            attempts.append({
                "retained_color_bits": retained_bits,
                "result": "vc_lz_overflow",
            })
            continue
        attempts.append({
            "retained_color_bits": retained_bits,
            "result": "fit",
            "encoded_bytes": len(compressed),
        })
        selected_decoded = decoded
        selected_compressed = compressed
        selected_bits = retained_bits
        break
    if selected_decoded is None or selected_compressed is None \
            or selected_bits is None:
        raise TextureWorkflowError(
            f"VC-LZ target cannot fit a usable A1R5G5B5 player strip inside "
            f"its {target.chunk.stored_size}-byte bound; simplify texture or noise"
        )

    rebuilt_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
        target.template_span, selected_decoded
    )
    require(
        rebuild_info.recompressed_bytes == len(selected_compressed)
        and rebuilt_span[
            HEADER.size:HEADER.size + len(selected_compressed)
        ] == selected_compressed,
        "A1 bounded stream differs from the fixed-span rebuild",
    )
    standalone = dataclasses.replace(target.chunk, offset=0)
    roundtrip, _info = decode_chunk(rebuilt_span, standalone)
    require(roundtrip == selected_decoded,
            "rebuilt A1 span does not decode back to its authored payload")
    report: dict[str, Any] = {
        "png_sha256": png_sha256,
        "png_width": width,
        "png_height": height,
        "format": "A1R5G5B5",
        "mip_levels": target.mip_levels,
        "pixel_chain_bytes": target.pixel_chain_bytes,
        "source_owned_tail_bytes": target.video_bytes - target.pixel_chain_bytes,
        "retained_color_bits": selected_bits,
        "rebuilt_span_sha256": digest(rebuilt_span),
        "rebuilt_decoded_sha256": digest(selected_decoded),
        "recompressed_bytes": rebuild_info.recompressed_bytes,
        "zero_padding_bytes": rebuild_info.zero_padding_bytes,
    }
    if len(attempts) > 1:
        report["bounded_a1_fit"] = {
            "attempts": attempts,
            "selected_retained_color_bits": selected_bits,
            "selected_encoded_bytes": len(selected_compressed),
            "stored_size_bound": target.chunk.stored_size,
        }
    return rebuilt_span, report


def run(source_path: Path, output_path: Path, manifest_path: Path,
        plan_path: Path, index_path: Path) -> dict[str, Any]:
    supplied = source_path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_path.resolve(strict=True)
    output = common.canonical_new_path(output_path)
    manifest = common.canonical_new_path(manifest_path)
    require(not output.exists() and not manifest.exists(),
            "output XISO or manifest already exists")
    plan, plan_payload, edits = read_plan(plan_path)
    index = index_path.resolve(strict=True)

    archive = parse_archive(index)
    resolved: list[tuple[ResolvedTarget, bytes, dict[str, Any]]] = []
    seen: set[tuple[int, str]] = set()
    for edit in edits:
        key = (int(edit["outer_index"]), str(edit["texture"]))
        require(key not in seen, f"plan repeats target {key[0]}:{key[1]}")
        seen.add(key)
        target = resolve_target(archive, key[0], key[1])
        replacement, report = build_replacement(target, Path(str(edit["png"])))
        require(replacement != target.template_span,
                f"replacement equals retail for {key[0]}:{key[1]}")
        resolved.append((target, replacement, report))

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    success = False
    try:
        info = os.fstat(source_fd)
        source_size = info.st_size
        source_identity = common.fd_identity(source_fd)
        require(common.path_identity(source) == source_identity,
                "source pathname changed while opening")
        source_sha_before = common.sha256_fd(source_fd)
        entries, directory = common.parse_xdvdfs(source_fd, source_size)
        xbe = entries.get("default.xbe")
        require(xbe is not None and xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "retail default.xbe identity differs")

        packs: dict[str, Any] = {}
        writes: list[dict[str, Any]] = []
        spans: list[tuple[int, int]] = []
        for target, replacement, report in resolved:
            require(
                sum(piece.size for piece in target.physical_spans)
                == target.span_size == len(replacement),
                f"physical split for {target.outer_index}:{target.texture} changed",
            )
            for part_index, piece in enumerate(target.physical_spans):
                pack_path = f"{PACK_ROOT}/{piece.pack_name}"
                pack = entries.get(pack_path.casefold())
                require(pack is not None, f"source XISO has no {pack_path}")
                if piece.pack_name not in packs:
                    packs[piece.pack_name] = {
                        "path": pack_path,
                        "size": pack.size,
                        "sha256": common.sha256_fd(
                            source_fd, pack.byte_offset, pack.size
                        ),
                    }
                absolute = pack.byte_offset + piece.pack_relative_offset
                require(absolute + piece.size <= pack.byte_offset + pack.size,
                        f"{target.texture} part does not lie inside {pack_path}")
                actual = common.read_exact(source_fd, absolute, piece.size)
                require(digest(actual) == piece.span_sha256,
                        f"source part for {target.outer_index}:{target.texture} "
                        "differs from the extracted index it was resolved against")
                end = absolute + piece.size
                require(all(end <= first or absolute >= last
                            for first, last in spans),
                        "plan target spans overlap")
                spans.append((absolute, end))
                replacement_piece = replacement[
                    piece.replacement_offset:piece.replacement_offset + piece.size
                ]
                require(len(replacement_piece) == piece.size,
                        "replacement physical split is incomplete")
                writes.append({
                    "absolute": absolute,
                    "replacement": replacement_piece,
                    "target": target,
                    "report": report,
                    "pack_path": pack_path,
                    "physical_span": piece,
                    "part_index": part_index,
                    "part_count": len(target.physical_spans),
                })

        output_owned = common.reserve_file(output)
        require(output_owned.identity != source_identity, "output XISO aliases source")
        copy_method = common.copy_fd_exact(
            source_fd, output_owned.descriptor, source_size)
        allowed: set[int] = set()
        for write in writes:
            common.pwrite(output_owned.descriptor, write["replacement"], write["absolute"])
            before = common.read_exact(source_fd, write["absolute"],
                                       write["physical_span"].size)
            allowed.update(
                write["absolute"] + position
                for position, (old, new) in enumerate(zip(before, write["replacement"]))
                if old != new
            )
        os.fsync(output_owned.descriptor)
        for write in writes:
            readback = common.read_exact(output_owned.descriptor, write["absolute"],
                                         write["physical_span"].size)
            require(readback == write["replacement"],
                    f"output part readback differs for {write['target'].texture}")
        # A per-piece readback proves each physical write. Reassembly proves
        # that their order and split recreate the exact logical TXTR chain.
        for target, replacement, _report in resolved:
            target_writes = sorted(
                (write for write in writes if write["target"] is target),
                key=lambda write: write["part_index"],
            )
            reassembled = b"".join(
                common.read_exact(
                    output_owned.descriptor,
                    write["absolute"],
                    write["physical_span"].size,
                )
                for write in target_writes
            )
            require(reassembled == replacement,
                    f"output logical span readback differs for {target.texture}")
        source_sha_after, output_sha, changed = common.compare_and_hash(
            source_fd, output_owned.descriptor, source_size, allowed)
        require(source_sha_after == source_sha_before,
                "source XISO changed during the workflow")
        require(changed == sorted(allowed),
                "output differs from source outside the planned spans")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_size)
        require(output_entries == entries and output_directory == directory,
                "output XISO filesystem tree/layout differs from source")

        record = {
            "schema": SCHEMA,
            "plan": {"path": plan.name, "sha256": digest(plan_payload)},
            "source": {"size": source_size, "sha256_before_and_after": source_sha_before},
            "output": {"size": source_size, "sha256": output_sha,
                       "copy_method": copy_method},
            "packs": packs,
            "identity": {
                "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
                "note": "Identity is per-extent. The container size and hash are "
                        "recorded, never gated: a legally repacked dump differs.",
            },
            "transaction": {
                "all_replacements_staged_before_output_reservation": True,
                "source_opened_read_only": True,
                "output_reserved_with_no_overwrite": True,
                "every_physical_piece_read_back": True,
                "every_logical_txtr_reassembled_and_verified": True,
            },
            "edits": [
                {
                    "outer_index": target.outer_index,
                    "chunk_index": target.chunk_index,
                    "texture": target.texture,
                    "width": target.width,
                    "height": target.height,
                    "format": target.format_name,
                    "span_size": target.span_size,
                    "source_span_sha256": target.span_sha256,
                    "physical_spans": [
                        {
                            "part_index": write["part_index"],
                            "pack_path": write["pack_path"],
                            "absolute_offset": write["absolute"],
                            "replacement_offset": write["physical_span"].replacement_offset,
                            "span_size": write["physical_span"].size,
                            "source_span_sha256": write["physical_span"].span_sha256,
                        }
                        for write in sorted(
                            (item for item in writes if item["target"] is target),
                            key=lambda item: item["part_index"],
                        )
                    ],
                    **report,
                }
                for target, _replacement, report in resolved
            ],
            "changed_byte_count": len(changed),
        }
        manifest_owned = common.reserve_file(manifest)
        common.write_owned_json(manifest_owned, record)
        success = True
        return record
    finally:
        os.close(source_fd)
        if output_owned is not None:
            if not success:
                common.unlink_if_owned(output_owned)
            else:
                os.close(output_owned.descriptor)
        if manifest_owned is not None:
            if not success:
                common.unlink_if_owned(manifest_owned)
            else:
                os.close(manifest_owned.descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path,
                        help="extracted vc_53450030/0, used to resolve targets")
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest,
                     args.plan, args.index)
    except (TextureWorkflowError, common.PatchError) as exc:
        print(f"nfl_all_texture_xiso_workflow: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
