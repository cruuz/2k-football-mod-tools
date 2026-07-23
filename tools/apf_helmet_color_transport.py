#!/usr/bin/env python3
"""Low-level, fixed-allocation APF ``helmet_color`` DXN transport.

Callers provide a separately hash-pinned family row.  This module changes
only the two-channel helmet-color VRAM subpart, preserves ``helmet_normal``
and both DRAM descriptors, and returns an in-memory rebuilt IFF.  PNG files
are a lossless representation of the two DXN channels as R and G; B must be
zero and A must be 255 so no unsupported channel semantics are implied.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct

from PIL import Image, __version__ as PILLOW_VERSION

import apf_inner
import apf_outer
import apf_texture_patch as archive_patch
import apf_xenos_dxn_mip_layout as dxn_mips


SCHEMA = "apf_helmet_color_transport/v1"
INNER_INDEX = 0
INNER_NAME = "helmet_color"
PRODUCTION_DXN_CAVEAT = (
    "The deterministic BC4 endpoint search is a bounded proof backend, not a "
    "production perceptual DXN compressor; visually inspect mods and replace "
    "it with a vetted high-quality BC5/DXN encoder before broad release."
)


class HelmetTransportError(ValueError):
    """Raised when a helmet package leaves the proved structural class."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_descriptor(metadata: dict[str, object]) -> None:
    required = {
        "vc_file_id": "0xcf7f3bdf",
        "vc_width": 256,
        "vc_height": 1024,
        "vc_base_data_length": 0x40000,
        "vc_mip_data_length": 0x20000,
        "pitch_pixels": 256,
        "tiled": True,
        "format": 49,
        "endianness": 1,
        "stacked": False,
        "width": 256,
        "height": 1024,
        "swizzle_components": [0, 1, 2, 3],
        "mip_min_level": 0,
        "mip_max_level": 6,
        "dimension": 1,
        "packed_mips": True,
        "mip_address_pages": 64,
    }
    disagreements = {
        key: (metadata.get(key), wanted)
        for key, wanted in required.items()
        if metadata.get(key) != wanted
    }
    if disagreements:
        raise HelmetTransportError(
            f"PORTME: APF helmet_color descriptor changed: {disagreements}"
        )


def _bc4_palette(endpoint_0: int, endpoint_1: int) -> tuple[int, ...]:
    if endpoint_0 > endpoint_1:
        return (
            endpoint_0,
            endpoint_1,
            (6 * endpoint_0 + endpoint_1) // 7,
            (5 * endpoint_0 + 2 * endpoint_1) // 7,
            (4 * endpoint_0 + 3 * endpoint_1) // 7,
            (3 * endpoint_0 + 4 * endpoint_1) // 7,
            (2 * endpoint_0 + 5 * endpoint_1) // 7,
            (endpoint_0 + 6 * endpoint_1) // 7,
        )
    return (
        endpoint_0,
        endpoint_1,
        (4 * endpoint_0 + endpoint_1) // 5,
        (3 * endpoint_0 + 2 * endpoint_1) // 5,
        (2 * endpoint_0 + 3 * endpoint_1) // 5,
        (endpoint_0 + 4 * endpoint_1) // 5,
        0,
        255,
    )


def decode_bc4(block: bytes) -> tuple[int, ...]:
    if len(block) != 8:
        raise HelmetTransportError("BC4 block must contain eight bytes")
    palette = _bc4_palette(block[0], block[1])
    selectors = int.from_bytes(block[2:], "little")
    return tuple(palette[(selectors >> (3 * index)) & 7] for index in range(16))


def decode_dxn(block: bytes) -> tuple[tuple[int, int], ...]:
    if len(block) != 16:
        raise HelmetTransportError("DXN block must contain sixteen bytes")
    first, second = decode_bc4(block[:8]), decode_bc4(block[8:])
    return tuple(zip(first, second))


def _encode_bc4(values: tuple[int, ...]) -> tuple[bytes, int, int]:
    if len(values) != 16 or any(not 0 <= value <= 255 for value in values):
        raise HelmetTransportError("BC4 encoder needs sixteen byte values")
    if len(set(values)) == 1:
        return bytes((values[0], values[0])) + bytes(6), 0, 1
    minimum, maximum = min(values), max(values)
    candidates: set[tuple[int, int]] = set()
    for delta_max in range(-2, 3):
        for delta_min in range(-2, 3):
            high = min(255, max(0, maximum + delta_max))
            low = min(255, max(0, minimum + delta_min))
            if high != low:
                candidates.add((high, low))
                candidates.add((low, high))
    best: tuple[int, bytes] | None = None
    selector_evaluations = 0
    for endpoint_0, endpoint_1 in sorted(candidates):
        palette = _bc4_palette(endpoint_0, endpoint_1)
        bits = 0
        error = 0
        for index, value in enumerate(values):
            selector, distance = min(
                enumerate(palette), key=lambda item: ((value - item[1]) ** 2, item[0])
            )
            selector_evaluations += 8
            error += distance * distance
            bits |= selector << (3 * index)
        payload = bytes((endpoint_0, endpoint_1)) + bits.to_bytes(6, "little")
        candidate = (error, payload)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    return best[1], best[0], selector_evaluations


def encode_dxn(pairs: tuple[tuple[int, int], ...]) -> tuple[bytes, dict[str, int]]:
    if len(pairs) != 16:
        raise HelmetTransportError("DXN encoder needs sixteen channel pairs")
    first, error_0, evals_0 = _encode_bc4(tuple(pair[0] for pair in pairs))
    second, error_1, evals_1 = _encode_bc4(tuple(pair[1] for pair in pairs))
    return first + second, {
        "total_squared_rg_error": error_0 + error_1,
        "selector_evaluations": evals_0 + evals_1,
    }


def decode_linear_dxn(
    linear: bytes, location: dxn_mips.MipLocation
) -> bytes:
    if len(linear) != location.logical_block_count * 16:
        raise HelmetTransportError(f"mip {location.level} DXN length is invalid")
    rgba = bytearray(location.width * location.height * 4)
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            block_index = block_y * location.width_blocks + block_x
            pixels = decode_dxn(linear[block_index * 16:block_index * 16 + 16])
            for local_y in range(4):
                for local_x in range(4):
                    x, y = block_x * 4 + local_x, block_y * 4 + local_y
                    if x < location.width and y < location.height:
                        r, g = pixels[local_y * 4 + local_x]
                        offset = (y * location.width + x) * 4
                        rgba[offset:offset + 4] = bytes((r, g, 0, 255))
    return bytes(rgba)


def _load_png(path: Path) -> bytes:
    with Image.open(path) as image:
        image.load()
        if image.format != "PNG" or image.size != (256, 1024) or image.mode != "RGBA":
            raise HelmetTransportError(
                "helmet PNG must be exact 256x1024 RGBA PNG"
            )
        rgba = image.tobytes()
    if any(rgba[index] != 0 for index in range(2, len(rgba), 4)):
        raise HelmetTransportError("helmet PNG B channel must be zero for two-channel DXN")
    if any(rgba[index] != 255 for index in range(3, len(rgba), 4)):
        raise HelmetTransportError("helmet PNG A channel must be 255")
    return rgba


def _resize(rgba: bytes, target: tuple[int, int]) -> bytes:
    resized = Image.frombytes("RGBA", (256, 1024), rgba).resize(
        target, Image.Resampling.BOX
    ).tobytes()
    # BOX preserves the fixed B/A channels, but assert rather than assume.
    if any(resized[index] != 0 for index in range(2, len(resized), 4)) or any(
        resized[index] != 255 for index in range(3, len(resized), 4)
    ):
        raise HelmetTransportError("mip generation changed fixed B/A channels")
    return resized


def _encode_changed_blocks(
    original_linear: bytes,
    original_rgba: bytes,
    wanted_rgba: bytes,
    location: dxn_mips.MipLocation,
) -> tuple[bytes, list[int], dict[str, int]]:
    result = bytearray(original_linear)
    changed: list[int] = []
    error = evaluations = 0
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            offsets = [
                ((block_y * 4 + y) * location.width + block_x * 4 + x) * 4
                for y in range(4) for x in range(4)
            ]
            if all(wanted_rgba[o:o + 4] == original_rgba[o:o + 4] for o in offsets):
                continue
            pairs = tuple((wanted_rgba[o], wanted_rgba[o + 1]) for o in offsets)
            encoded, info = encode_dxn(pairs)
            index = block_y * location.width_blocks + block_x
            result[index * 16:index * 16 + 16] = encoded
            changed.append(index)
            error += info["total_squared_rg_error"]
            evaluations += info["selector_evaluations"]
    return bytes(result), changed, {
        "total_squared_rg_error": error,
        "selector_evaluations": evaluations,
    }


def _indices_summary(indices: list[int]) -> dict[str, object]:
    payload = b"".join(value.to_bytes(4, "big") for value in indices)
    return {
        "count": len(indices),
        "first": indices[0] if indices else None,
        "last": indices[-1] if indices else None,
        "big_endian_u32_sha256": sha256(payload),
        "indices_embedded": indices if len(indices) <= 256 else None,
    }


def active_byte_mask(
    length: int, locations: tuple[dxn_mips.MipLocation, ...]
) -> bytearray:
    mask = bytearray(length)
    for location in locations:
        for y in range(location.height_blocks):
            for x in range(location.width_blocks):
                relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                    x + location.origin_block_x, y + location.origin_block_y,
                    location.pitch_blocks, 4,
                )
                start = location.data_offset + relative
                mask[start:start + 16] = b"\1" * 16
    return mask


def hash_inactive(data: bytes, mask: bytearray) -> str:
    return sha256(bytes(value for index, value in enumerate(data) if not mask[index]))


def _validate_structure(
    record: apf_inner.IFFRecord, blocks: list[bytes]
) -> tuple[dict[str, object], bytes]:
    if record.block_count != 2 or record.file_count != 2 or record.warnings:
        raise HelmetTransportError("PORTME: helmet IFF structure changed")
    if [item.name for item in record.files] != ["helmet_color", "helmet_normal"] or any(
        item.type_name != "TXTR" for item in record.files
    ):
        raise HelmetTransportError("PORTME: helmet inner file roster changed")
    expected = [
        [(0, 0x000, 0xE0), (1, 0x000000, 0x60000)],
        [(0, 0x0E0, 0xE0), (1, 0x060000, 0x160000)],
    ]
    actual = [[(part.block_index, part.offset, part.length) for part in item.parts]
              for item in record.files]
    if actual != expected:
        raise HelmetTransportError("PORTME: helmet DRAM/VRAM subpart layout changed")
    metadata = apf_inner.parse_txtr_metadata(blocks[0][:0xE0])
    strict_descriptor(metadata)
    return metadata, blocks[1][:0x60000]


def _rebuild_entry(
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    new_texture: bytes,
) -> tuple[bytes, dict[str, object]]:
    if len(original_blocks) != 2 or len(new_texture) != 0x60000:
        raise HelmetTransportError("helmet block or color length changed")
    new_vram = bytearray(original_blocks[1])
    new_vram[:0x60000] = new_texture
    new_blocks = [original_blocks[0], bytes(new_vram)]
    descriptor = record.blocks[1]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise HelmetTransportError("PORTME: helmet VRAM block is not H7A-compressed")
    encoded = archive_patch.compress_h7a(new_blocks[1], descriptor.wrapper.shift)
    encoded_stored = struct.pack(
        ">5I", apf_inner.H7A_MAGIC, len(new_blocks[1]),
        apf_inner.H7A_HEADER_SIZE + len(encoded), descriptor.unknown_10,
        descriptor.wrapper.shift,
    ) + encoded
    if apf_inner.decompress_h7a(encoded, len(new_blocks[1]),
                                descriptor.wrapper.shift) != new_blocks[1]:
        raise HelmetTransportError("helmet H7A encode/decode round-trip failed")
    new_stored = [original_stored[0], encoded_stored]
    header = bytearray(original_entry[:record.header_size])
    body = bytearray()
    cursor = record.header_size
    block_report = []
    for index, (block, stored) in enumerate(zip(record.blocks, new_stored)):
        start = cursor
        stored_length = len(stored) if block.is_compressed else block.uncompressed_length
        struct.pack_into(
            ">8I", header, apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            block.name_hash, block.type_hash, block.unknown_08,
            block.uncompressed_length, block.unknown_10, start, stored_length,
            block.indexed,
        )
        body.extend(stored)
        cursor += len(stored)
        block_report.append({
            "index": index,
            "start_before": block.start_offset,
            "start_after": start,
            "stored_length_before": len(original_stored[index]),
            "stored_length_after": len(stored),
            "stored_sha256_before": sha256(original_stored[index]),
            "stored_sha256_after": sha256(stored),
            "decoded_sha256_before": sha256(original_blocks[index]),
            "decoded_sha256_after": sha256(new_blocks[index]),
        })
    new_file_length = record.header_size + len(body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    if record.footer is None:
        raise HelmetTransportError("PORTME: helmet IFF has no footer")
    footer_size = 8 + record.footer.payload_size
    footer = original_entry[record.file_length:record.file_length + footer_size]
    if any(original_entry[record.file_length + footer_size:]):
        raise HelmetTransportError("PORTME: helmet allocation tail is nonzero")
    active = bytes(header) + bytes(body) + footer
    if len(active) > entry.size:
        raise HelmetTransportError(
            f"rebuilt helmet IFF exceeds fixed allocation by {len(active)-entry.size} bytes"
        )
    rebuilt = active + bytes(entry.size - len(active))
    memory = archive_patch.BytesReader(rebuilt)
    check_record = apf_inner.parse_iff(memory, entry)
    check_blocks = [apf_inner.decode_block(memory, check_record, index, 1 << 30)
                    for index in range(check_record.block_count)]
    if check_blocks != new_blocks:
        raise HelmetTransportError("rebuilt helmet IFF does not decode as intended")
    before_parts = archive_patch._file_part_hashes(record, original_blocks)  # type: ignore[attr-defined]
    after_parts = archive_patch._file_part_hashes(check_record, check_blocks)  # type: ignore[attr-defined]
    changed = [key for key in before_parts if before_parts[key] != after_parts[key]]
    if changed != [(0, 1)]:
        raise HelmetTransportError(f"unexpected helmet inner parts changed: {changed}")
    return rebuilt, {
        "allocation_size": entry.size,
        "file_length_before": record.file_length,
        "file_length_after": new_file_length,
        "allocation_slack_after": entry.size - len(active),
        "h7a_shift": descriptor.wrapper.shift,
        "h7a_decode_encode_decode_exact": True,
        "footer_sha256_before": sha256(footer),
        "footer_sha256_after": sha256(rebuilt[new_file_length:new_file_length + footer_size]),
        "footer_bit_exact": rebuilt[new_file_length:new_file_length + footer_size] == footer,
        "blocks": block_report,
        "rebuilt_iff_reparsed": True,
        "both_dram_descriptors_preserved": check_blocks[0] == original_blocks[0],
        "helmet_normal_preserved": before_parts[(1, 0)] == after_parts[(1, 0)] and
                                   before_parts[(1, 1)] == after_parts[(1, 1)],
        "changed_inner_parts": [{"file_index": 0, "part_index": 1, "block_index": 1}],
    }


def build_patch(
    index_path: Path, png_path: Path, row: dict[str, object]
) -> archive_patch.PatchResult:
    archive = apf_outer.parse_archive(index_path)
    entry_index = int(row["outer_table_index"])
    try:
        entry = archive.entries[entry_index]
    except IndexError as exc:
        raise HelmetTransportError(f"outer archive has no entry {entry_index}") from exc
    if (entry.name_id != int(str(row["outer_name_id"]), 16) or
            len(entry.segments) != 1 or entry.segments[0].pack_name != "0A"):
        raise HelmetTransportError("catalog target does not resolve to one 0A segment")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        blocks = [apf_inner.decode_block(reader, record, index, 1 << 30)
                  for index in range(record.block_count)]
        stored = [reader.read(entry, block.start_offset, block.stored_length)
                  for block in record.blocks]
    if sha256(original_entry) != row["outer_allocation"]["sha256"]:  # type: ignore[index]
        raise HelmetTransportError("source helmet entry differs from catalog hash")
    metadata, texture = _validate_structure(record, blocks)
    if sha256(texture) != row["inner_file"]["texture_sha256"]:  # type: ignore[index]
        raise HelmetTransportError("source helmet_color differs from catalog hash")
    locations = dxn_mips.derive_layout(metadata)
    if len(locations) != 7 or dxn_mips.transport_roundtrip(texture, locations) != texture:
        raise HelmetTransportError("retail seven-level DXN transport is not bit-exact")
    original_linear = [dxn_mips.extract_linear_dxn(texture, item) for item in locations]
    original_rgba = [decode_linear_dxn(linear, item)
                     for linear, item in zip(original_linear, locations)]
    wanted_base = _load_png(png_path)
    common_source = {
        "archive_index": str(index_path),
        "physical_volume": "0A",
        "outer_entry_index": entry_index,
        "outer_name": row["outer_name"],
        "inner_file_index": 0,
        "inner_name": INNER_NAME,
        "entry_sha256": sha256(original_entry),
        "texture_sha256": sha256(texture),
        "png_rgba_sha256": sha256(wanted_base),
    }
    source_levels = [{
        "level": item.level,
        "linear_dxn_sha256": sha256(linear),
        "decoded_rgba_sha256": sha256(rgba),
    } for item, linear, rgba in zip(locations, original_linear, original_rgba)]
    if wanted_base == original_rgba[0]:
        return archive_patch.PatchResult(original_entry, {
            "schema": SCHEMA,
            "mode": "no_op",
            "source": common_source,
            "target": {"descriptor": metadata,
                       "layout": [item.manifest() for item in locations]},
            "levels": source_levels,
            "validation": {
                "all_seven_levels_extracted": True,
                "all_seven_levels_transport_bit_exact": True,
                "input_matches_decoded_base": True,
                "entry_bit_exact": True,
                "source_opened_read_only": True,
            },
            "backend": {
                "png_and_mips": f"Pillow {PILLOW_VERSION}; BOX filter",
                "dxn": "not invoked for bit-exact no-op",
                "xenos_layout": f"Xenia-derived, commit {dxn_mips.XENIA_COMMIT}",
                "h7a": "not invoked for bit-exact no-op",
            },
            "portme": [PRODUCTION_DXN_CAVEAT],
        })
    wanted_levels = [wanted_base] + [
        _resize(wanted_base, (item.width, item.height)) for item in locations[1:]
    ]
    new_texture = texture
    changed_linear, changed_indices, encoder_info = [], [], []
    for item, source_linear, source_rgba, wanted in zip(
        locations, original_linear, original_rgba, wanted_levels
    ):
        linear, indices, info = _encode_changed_blocks(
            source_linear, source_rgba, wanted, item
        )
        new_texture = dxn_mips.insert_linear_dxn(new_texture, item, linear)
        changed_linear.append(linear)
        changed_indices.append(indices)
        encoder_info.append(info)
    if not changed_indices[0]:
        raise HelmetTransportError("changed PNG produced no changed base DXN block")
    if dxn_mips.transport_roundtrip(new_texture, locations) != new_texture:
        raise HelmetTransportError("patched seven-level DXN transport failed")
    mask = active_byte_mask(len(texture), locations)
    inactive_before, inactive_after = hash_inactive(texture, mask), hash_inactive(new_texture, mask)
    if inactive_before != inactive_after:
        raise HelmetTransportError("inactive DXN mip bytes changed")
    levels = []
    for item, before, after, wanted, indices, info in zip(
        locations, original_linear, changed_linear, wanted_levels,
        changed_indices, encoder_info,
    ):
        decoded = decode_linear_dxn(after, item)
        levels.append({
            "level": item.level,
            "width": item.width,
            "height": item.height,
            "packed_tail": item.packed_tail,
            "origin_block_x": item.origin_block_x,
            "origin_block_y": item.origin_block_y,
            "linear_dxn_sha256_before": sha256(before),
            "linear_dxn_sha256_after": sha256(after),
            "wanted_rgba_sha256": sha256(wanted),
            "decoded_rgba_sha256_after": sha256(decoded),
            "changed_dxn_blocks": _indices_summary(indices),
            "encoder": info,
            "decode_back_metrics": archive_patch._rgba_metrics(wanted, decoded),  # type: ignore[attr-defined]
        })
    rebuilt, iff = _rebuild_entry(entry, record, original_entry, blocks, stored, new_texture)
    return archive_patch.PatchResult(rebuilt, {
        "schema": SCHEMA,
        "mode": "patched",
        "source": common_source,
        "target": {"descriptor": metadata,
                   "layout": [item.manifest() for item in locations]},
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
            "all_seven_levels_regenerated": True,
            "all_seven_levels_decoded_back": True,
            "all_seven_levels_transport_bit_exact": True,
            "packed_tail_levels": [4, 5, 6],
            "packed_tail_origins_blocks": [[4, 0], [2, 0], [1, 0]],
            "inactive_mip_padding_preserved": True,
            "h7a_decode_encode_decode_exact": True,
            "rebuilt_iff_reparsed": True,
            "footer_bit_exact": True,
            "both_dram_descriptors_preserved": True,
            "helmet_normal_preserved": True,
            "fixed_outer_allocation": True,
            "source_opened_read_only": True,
        },
        "backend": {
            "png_contract": "R/G are DXN channels; B=0; A=255",
            "png_and_mips": f"Pillow {PILLOW_VERSION}; BOX filter",
            "dxn": "project-native deterministic touched-block BC4-pair proof encoder",
            "dxn_production_caveat": PRODUCTION_DXN_CAVEAT,
            "xenos_layout": f"Xenia-derived, commit {dxn_mips.XENIA_COMMIT}",
            "h7a": "project-native greedy H7A encoder",
        },
        "portme": [
            "validate changed copied volumes in Xenia and on hardware",
            PRODUCTION_DXN_CAVEAT,
            "name the two helmet_color channel semantics from runtime shader evidence",
        ],
    })
