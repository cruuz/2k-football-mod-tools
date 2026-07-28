#!/usr/bin/env python3
"""Low-level fixed-allocation APF pants-color transport.

This module has no retail target catalog.  Callers must provide a hash-pinned
row.  It edits only the ``pants_color`` VRAM subpart, preserves the three
normal-map files, rebuilds H7A/IFF inside the original outer allocation, and
returns bytes in memory.  The public copy-only target gate lives in
``apf_pants_family_patch.py``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct

from PIL import Image, __version__ as PILLOW_VERSION

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_inner
import apf_outer
import apf_texture_patch as archive_patch
import apf_xenos_bc1_mip_layout as bc1_mips
import nfl_dxt1


SCHEMA = "apf_pants_color_transport/v1"
INNER_INDEX = 2
INNER_NAME = "pants_color"
PRODUCTION_DXT1_CAVEAT = (
    "The deterministic opaque DXT1 endpoint search is a bounded proof backend, "
    "not a production perceptual compressor; visually inspect mods and replace "
    "it with a vetted high-quality DXT1 encoder before broad release."
)


class PantsTransportError(ValueError):
    """Raised when a pants package leaves the proved structural class."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_descriptor(metadata: dict[str, object]) -> None:
    required = {
        "vc_file_id": "0x9717866d",
        "vc_width": 512,
        "vc_height": 512,
        "vc_base_data_length": 0x20000,
        "vc_mip_data_length": 0x10000,
        "pitch_pixels": 512,
        "tiled": True,
        "format": 18,
        "endianness": 1,
        "stacked": False,
        "width": 512,
        "height": 512,
        "swizzle_components": [0, 1, 2, 3],
        "mip_min_level": 0,
        "mip_max_level": 7,
        "dimension": 1,
        "packed_mips": True,
        "mip_address_pages": 32,
    }
    disagreements = {
        key: (metadata.get(key), wanted)
        for key, wanted in required.items()
        if metadata.get(key) != wanted
    }
    if disagreements:
        raise PantsTransportError(
            f"PORTME: APF pants_color descriptor changed: {disagreements}"
        )


def decode_linear_bc1(
    linear: bytes, location: bc1_mips.MipLocation
) -> bytes:
    if len(linear) != location.logical_block_count * 8:
        raise PantsTransportError(f"mip {location.level} BC1 length is invalid")
    rgba = bytearray(location.width * location.height * 4)
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            index = block_y * location.width_blocks + block_x
            pixels = apf_inner._decode_bc1(  # type: ignore[attr-defined]
                linear[index * 8 : index * 8 + 8]
            )
            for local_y in range(4):
                for local_x in range(4):
                    x = block_x * 4 + local_x
                    y = block_y * 4 + local_y
                    if x < location.width and y < location.height:
                        destination = (y * location.width + x) * 4
                        rgba[destination : destination + 4] = bytes(
                            pixels[local_y * 4 + local_x]
                        )
    return bytes(rgba)


def _load_png(path: Path, width: int, height: int) -> bytes:
    with Image.open(path) as image:
        image.load()
        if image.format != "PNG" or image.size != (width, height):
            raise PantsTransportError(
                f"pants input must be a decoded {width}x{height} PNG"
            )
        if image.mode != "RGBA":
            raise PantsTransportError("pants PNG must be stored as exact RGBA")
        rgba = image.tobytes()
    if any(rgba[index] != 255 for index in range(3, len(rgba), 4)):
        raise PantsTransportError(
            "pants PNG must be fully opaque; one-bit DXT1 alpha is unsupported"
        )
    return rgba


def _resize(rgba: bytes, source: tuple[int, int], target: tuple[int, int]) -> bytes:
    return Image.frombytes("RGBA", source, rgba).resize(
        target, Image.Resampling.BOX
    ).tobytes()


def _encode_changed_blocks(
    original_linear: bytes,
    original_rgba: bytes,
    wanted_rgba: bytes,
    location: bc1_mips.MipLocation,
) -> tuple[bytes, list[int], dict[str, int]]:
    result = bytearray(original_linear)
    changed: list[int] = []
    total_error = total_pairs = total_selectors = 0
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            offsets = [
                ((block_y * 4 + local_y) * location.width + block_x * 4 + local_x)
                * 4
                for local_y in range(4)
                for local_x in range(4)
            ]
            if all(
                wanted_rgba[offset : offset + 4]
                == original_rgba[offset : offset + 4]
                for offset in offsets
            ):
                continue
            pixels = tuple(
                tuple(wanted_rgba[offset : offset + 3]) for offset in offsets
            )
            block, error, pairs, selectors = nfl_dxt1.encode_block(pixels)  # type: ignore[arg-type]
            index = block_y * location.width_blocks + block_x
            result[index * 8 : index * 8 + 8] = block
            changed.append(index)
            total_error += error
            total_pairs += pairs
            total_selectors += selectors
    return bytes(result), changed, {
        "total_squared_rgb_error": total_error,
        "endpoint_pair_evaluations": total_pairs,
        "selector_evaluations": total_selectors,
    }


def _indices_summary(indices: list[int]) -> dict[str, object]:
    serialized = b"".join(item.to_bytes(4, "big") for item in indices)
    return {
        "count": len(indices),
        "first": indices[0] if indices else None,
        "last": indices[-1] if indices else None,
        "big_endian_u32_sha256": sha256(serialized),
        "indices_embedded": indices if len(indices) <= 256 else None,
    }


def active_byte_mask(
    texture_length: int, locations: tuple[bc1_mips.MipLocation, ...]
) -> bytearray:
    mask = bytearray(texture_length)
    for location in locations:
        for block_y in range(location.height_blocks):
            for block_x in range(location.width_blocks):
                relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                    block_x + location.origin_block_x,
                    block_y + location.origin_block_y,
                    location.pitch_blocks,
                    3,
                )
                start = location.data_offset + relative
                mask[start : start + 8] = b"\1" * 8
    return mask


def hash_inactive(data: bytes, mask: bytearray) -> str:
    return sha256(bytes(value for index, value in enumerate(data) if not mask[index]))


def _rebuild_entry(
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    new_color_texture: bytes,
) -> tuple[bytes, dict[str, object]]:
    if len(original_blocks) != 2 or len(original_stored) != 2:
        raise PantsTransportError("PORTME: pants IFF must have exactly two blocks")
    target = record.files[INNER_INDEX]
    texture_part = target.parts[1]
    if (texture_part.block_index, texture_part.offset, texture_part.length) != (
        1,
        0,
        0x30000,
    ):
        raise PantsTransportError("PORTME: pants_color VRAM subpart moved")
    if len(new_color_texture) != texture_part.length:
        raise PantsTransportError("replacement pants texture length changed")

    new_block_1 = bytearray(original_blocks[1])
    new_block_1[: texture_part.length] = new_color_texture
    new_blocks = [original_blocks[0], bytes(new_block_1)]
    descriptor = record.blocks[1]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise PantsTransportError("PORTME: pants VRAM block is not H7A-compressed")
    encoded = archive_patch.compress_h7a(new_blocks[1], descriptor.wrapper.shift)
    encoded_stored = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(new_blocks[1]),
        apf_inner.H7A_HEADER_SIZE + len(encoded),
        descriptor.unknown_10,
        descriptor.wrapper.shift,
    ) + encoded
    if apf_inner.decompress_h7a(
        encoded, len(new_blocks[1]), descriptor.wrapper.shift
    ) != new_blocks[1]:
        raise PantsTransportError("pants H7A encode/decode round-trip failed")
    new_stored = [original_stored[0], encoded_stored]

    header = bytearray(original_entry[: record.header_size])
    body = bytearray()
    cursor = record.header_size
    block_report: list[dict[str, object]] = []
    for index, (block, stored) in enumerate(zip(record.blocks, new_stored)):
        start = cursor
        compressed_length = len(stored) if block.is_compressed else block.uncompressed_length
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            block.name_hash,
            block.type_hash,
            block.unknown_08,
            block.uncompressed_length,
            block.unknown_10,
            start,
            compressed_length,
            block.indexed,
        )
        body.extend(stored)
        cursor += len(stored)
        block_report.append(
            {
                "index": index,
                "start_before": block.start_offset,
                "start_after": start,
                "stored_length_before": len(original_stored[index]),
                "stored_length_after": len(stored),
                "stored_sha256_before": sha256(original_stored[index]),
                "stored_sha256_after": sha256(stored),
                "decoded_sha256_before": sha256(original_blocks[index]),
                "decoded_sha256_after": sha256(new_blocks[index]),
            }
        )

    new_file_length = record.header_size + len(body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    if record.footer is None:
        raise PantsTransportError("PORTME: pants IFF has no validated footer")
    footer_total = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_total]
    old_tail = original_entry[record.file_length + footer_total :]
    if any(old_tail):
        raise PantsTransportError("PORTME: pants outer allocation tail is nonzero")
    active = bytes(header) + bytes(body) + footer
    if len(active) > entry.size:
        raise PantsTransportError(
            "rebuilt pants IFF exceeds fixed allocation by "
            f"{len(active) - entry.size} bytes"
        )
    rebuilt = active + bytes(entry.size - len(active))

    memory_reader = archive_patch.BytesReader(rebuilt)
    rebuilt_record = apf_inner.parse_iff(memory_reader, entry)
    rebuilt_blocks = [
        apf_inner.decode_block(memory_reader, rebuilt_record, index, 1 << 30)
        for index in range(rebuilt_record.block_count)
    ]
    if rebuilt_blocks != new_blocks:
        raise PantsTransportError("rebuilt pants IFF does not decode as intended")
    before_parts = archive_patch._file_part_hashes(record, original_blocks)  # type: ignore[attr-defined]
    after_parts = archive_patch._file_part_hashes(rebuilt_record, rebuilt_blocks)  # type: ignore[attr-defined]
    changed_parts = [key for key in before_parts if before_parts[key] != after_parts[key]]
    if changed_parts != [(INNER_INDEX, 1)]:
        raise PantsTransportError(f"unexpected pants inner parts changed: {changed_parts}")
    return rebuilt, {
        "allocation_size": entry.size,
        "file_length_before": record.file_length,
        "file_length_after": new_file_length,
        "allocation_slack_after": entry.size - len(active),
        "h7a_shift": descriptor.wrapper.shift,
        "h7a_decode_encode_decode_exact": True,
        "footer_sha256_before": sha256(footer),
        "footer_sha256_after": sha256(
            rebuilt[new_file_length : new_file_length + footer_total]
        ),
        "footer_bit_exact": rebuilt[
            new_file_length : new_file_length + footer_total
        ] == footer,
        "blocks": block_report,
        "rebuilt_iff_reparsed": True,
        "dram_block_preserved": before_parts[(INNER_INDEX, 0)] == after_parts[(INNER_INDEX, 0)],
        "three_normal_maps_preserved": all(
            before_parts[(file_index, part_index)] == after_parts[(file_index, part_index)]
            for file_index in (0, 1, 3)
            for part_index in (0, 1)
        ),
        "changed_inner_parts": [
            {"file_index": INNER_INDEX, "part_index": 1, "block_index": 1}
        ],
    }


def _validate_structure(
    record: apf_inner.IFFRecord, blocks: list[bytes]
) -> tuple[apf_inner.IFFFile, dict[str, object], bytes]:
    expected_names = [
        "pants_heavy_normal",
        "pants_medium_normal",
        "pants_color",
        "pants_light_normal",
    ]
    if record.block_count != 2 or record.file_count != 4 or record.warnings:
        raise PantsTransportError("PORTME: pants IFF structure changed")
    if [item.name for item in record.files] != expected_names or any(
        item.type_name != "TXTR" for item in record.files
    ):
        raise PantsTransportError("PORTME: pants inner file roster changed")
    expected_parts = [
        [(0, 0x2A0, 0xE0), (1, 0xF0000, 0x60000)],
        [(0, 0x1C0, 0xE0), (1, 0x90000, 0x60000)],
        [(0, 0x000, 0xE0), (1, 0x00000, 0x30000)],
        [(0, 0x0E0, 0xE0), (1, 0x30000, 0x60000)],
    ]
    actual_parts = [
        [(part.block_index, part.offset, part.length) for part in item.parts]
        for item in record.files
    ]
    if actual_parts != expected_parts:
        raise PantsTransportError("PORTME: pants DRAM/VRAM subpart layout changed")
    target = record.files[INNER_INDEX]
    dram = blocks[0][:0xE0]
    texture = blocks[1][:0x30000]
    metadata = apf_inner.parse_txtr_metadata(dram)
    strict_descriptor(metadata)
    return target, metadata, texture


def build_patch(
    index_path: Path, png_path: Path, row: dict[str, object]
) -> archive_patch.PatchResult:
    archive = apf_outer.parse_archive(index_path)
    entry_index = int(row["outer_table_index"])
    try:
        entry = archive.entries[entry_index]
    except IndexError as exc:
        raise PantsTransportError(f"outer archive has no entry {entry_index}") from exc
    if (
        entry.name_id != int(str(row["outer_name_id"]), 16)
        or len(entry.segments) != 1
        or entry.segments[0].pack_name != "0A"
    ):
        raise PantsTransportError("catalog target does not resolve to one 0A segment")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        original_blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        original_stored = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]
    if sha256(original_entry) != row["outer_allocation"]["sha256"]:  # type: ignore[index]
        raise PantsTransportError("source pants entry differs from pinned retail hash")
    _, metadata, texture = _validate_structure(record, original_blocks)
    if sha256(texture) != row["inner_file"]["texture_sha256"]:  # type: ignore[index]
        raise PantsTransportError("source pants_color differs from pinned retail hash")

    locations = bc1_mips.derive_layout(metadata)
    if len(texture) != 0x30000 or bc1_mips.transport_roundtrip(texture, locations) != texture:
        raise PantsTransportError("retail eight-level BC1 transport is not bit-exact")
    original_linear = [
        bc1_mips.extract_linear_bc1(texture, location) for location in locations
    ]
    original_rgba = [
        decode_linear_bc1(linear, location)
        for linear, location in zip(original_linear, locations)
    ]
    wanted_base = _load_png(png_path, 512, 512)
    common_source = {
        "archive_index": str(index_path),
        "physical_volume": "0A",
        "outer_entry_index": entry_index,
        "outer_name": row["outer_name"],
        "inner_file_index": INNER_INDEX,
        "inner_name": INNER_NAME,
        "entry_sha256": sha256(original_entry),
        "texture_sha256": sha256(texture),
        "png_rgba_sha256": sha256(wanted_base),
    }
    layout_report = [item.manifest() for item in locations]
    source_levels = [
        {
            "level": item.level,
            "linear_bc1_sha256": sha256(linear),
            "decoded_rgba_sha256": sha256(rgba),
        }
        for item, linear, rgba in zip(locations, original_linear, original_rgba)
    ]
    if wanted_base == original_rgba[0]:
        return archive_patch.PatchResult(
            original_entry,
            {
                "schema": SCHEMA,
                "mode": "no_op",
                "source": common_source,
                "target": {"descriptor": metadata, "layout": layout_report},
                "levels": source_levels,
                "validation": {
                    "all_eight_levels_extracted": True,
                    "all_eight_levels_transport_bit_exact": True,
                    "input_matches_decoded_base": True,
                    "entry_bit_exact": True,
                    "source_opened_read_only": True,
                },
                "backend": {
                    "png_and_mips": f"Pillow {PILLOW_VERSION}; BOX filter",
                    "dxt1": "not invoked for bit-exact no-op",
                    "xenos_layout": f"Xenia-derived, commit {bc1_mips.XENIA_COMMIT}",
                    "h7a": "not invoked for bit-exact no-op",
                },
                "portme": [PRODUCTION_DXT1_CAVEAT],
            },
        )

    wanted_levels = [wanted_base] + [
        _resize(wanted_base, (512, 512), (item.width, item.height))
        for item in locations[1:]
    ]
    new_texture = texture
    changed_linear: list[bytes] = []
    changed_indices: list[list[int]] = []
    encode_info: list[dict[str, int]] = []
    for location, source_linear, source_rgba, wanted in zip(
        locations, original_linear, original_rgba, wanted_levels
    ):
        new_linear, indices, info = _encode_changed_blocks(
            source_linear, source_rgba, wanted, location
        )
        new_texture = bc1_mips.insert_linear_bc1(new_texture, location, new_linear)
        changed_linear.append(new_linear)
        changed_indices.append(indices)
        encode_info.append(info)
    if not changed_indices[0]:
        raise PantsTransportError("changed PNG produced no changed base DXT1 block")
    if bc1_mips.transport_roundtrip(new_texture, locations) != new_texture:
        raise PantsTransportError("patched eight-level BC1 transport is not bit-exact")
    mask = active_byte_mask(len(texture), locations)
    inactive_before = hash_inactive(texture, mask)
    inactive_after = hash_inactive(new_texture, mask)
    if inactive_before != inactive_after:
        raise PantsTransportError("inactive BC1 mip bytes changed")

    levels = []
    for location, before, after, wanted, indices, info in zip(
        locations,
        original_linear,
        changed_linear,
        wanted_levels,
        changed_indices,
        encode_info,
    ):
        decoded = decode_linear_bc1(after, location)
        levels.append(
            {
                "level": location.level,
                "width": location.width,
                "height": location.height,
                "packed_tail": location.packed_tail,
                "origin_block_x": location.origin_block_x,
                "origin_block_y": location.origin_block_y,
                "linear_bc1_sha256_before": sha256(before),
                "linear_bc1_sha256_after": sha256(after),
                "wanted_rgba_sha256": sha256(wanted),
                "decoded_rgba_sha256_after": sha256(decoded),
                "changed_dxt1_blocks": _indices_summary(indices),
                "encoder": info,
                "decode_back_metrics": archive_patch._rgba_metrics(wanted, decoded),  # type: ignore[attr-defined]
            }
        )
    rebuilt, iff = _rebuild_entry(
        entry,
        record,
        original_entry,
        original_blocks,
        original_stored,
        new_texture,
    )
    return archive_patch.PatchResult(
        rebuilt,
        {
            "schema": SCHEMA,
            "mode": "patched",
            "source": common_source,
            "target": {"descriptor": metadata, "layout": layout_report},
            "levels": levels,
            "texture": {
                "length": len(texture),
                "sha256_before": sha256(texture),
                "sha256_after": sha256(new_texture),
                "inactive_padding_sha256_before": inactive_before,
                "inactive_padding_sha256_after": inactive_after,
                "inactive_padding_bit_exact": True,
            },
            "iff": iff,
            "binary_patch_manifest": {
                "physical_volume": "0A",
                "physical_offset": entry.segments[0].pack_offset,
                "replacement_length": entry.size,
                "original_sha256": sha256(original_entry),
                "replacement_sha256": sha256(rebuilt),
                **archive_patch._changed_extents(original_entry, rebuilt),  # type: ignore[attr-defined]
                "contains_replacement_bytes": False,
            },
            "validation": {
                "all_eight_levels_regenerated": True,
                "all_eight_levels_decoded_back": True,
                "all_eight_levels_transport_bit_exact": True,
                "packed_tail_levels": [5, 6, 7],
                "packed_tail_origins_blocks": [[4, 0], [2, 0], [1, 0]],
                "inactive_mip_padding_preserved": True,
                "h7a_decode_encode_decode_exact": True,
                "rebuilt_iff_reparsed": True,
                "footer_bit_exact": True,
                "pants_color_dram_preserved": True,
                "three_normal_maps_preserved": True,
                "fixed_outer_allocation": True,
                "source_opened_read_only": True,
            },
            "backend": {
                "png_and_mips": f"Pillow {PILLOW_VERSION}; BOX filter",
                "dxt1": "project-native deterministic opaque touched-block proof encoder",
                "dxt1_production_caveat": PRODUCTION_DXT1_CAVEAT,
                "xenos_layout": f"Xenia-derived, commit {bc1_mips.XENIA_COMMIT}",
                "h7a": "project-native greedy H7A encoder",
            },
            "portme": [
                "validate changed copied volumes in Xenia and on hardware",
                PRODUCTION_DXT1_CAVEAT,
                "replace BOX filtering with an artist-selectable gamma-aware mip filter",
            ],
        },
    )
