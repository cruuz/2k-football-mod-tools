#!/usr/bin/env python3
"""Low-level fixed-allocation APF ``shoulder_color`` BC3 transport.

The caller supplies a separately hash-pinned family row.  Only the
``shoulder_color`` VRAM subpart is changed; the complete DRAM block,
``jersey_regionmap``, and both sideline-player textures are preserved.  The
rebuilt H7A/IFF must fit the original outer allocation.  This module has no
runtime-visibility claim and never chooses a retail target on its own.
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
import apf_uniform_mip_patch as bc3_backend
import apf_xenos_mip_layout as xenos_mips


SCHEMA = "apf_shoulder_color_transport/v1"
INNER_INDEX = 3
INNER_NAME = "shoulder_color"
WIDTH = HEIGHT = 1024
TEXTURE_LENGTH = 0x160000
PRODUCTION_BC3_CAVEAT = (
    "The deterministic touched-block BC3 endpoint search is a bounded proof "
    "backend, not a production perceptual compressor; visually inspect mods "
    "and replace it with a vetted high-quality BC3 encoder before broad release."
)


class ShoulderTransportError(ValueError):
    """Raised when a shoulder package leaves the proved structural class."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_descriptor(metadata: dict[str, object]) -> None:
    required = {
        "vc_file_id": "0xb2f2b5ff",
        "vc_width": WIDTH,
        "vc_height": HEIGHT,
        "vc_base_data_length": 0x100000,
        "vc_mip_data_length": 0x60000,
        "pitch_pixels": WIDTH,
        "tiled": True,
        "format": 20,
        "endianness": 1,
        "stacked": False,
        "width": WIDTH,
        "height": HEIGHT,
        "swizzle_components": [0, 1, 2, 3],
        "mip_min_level": 0,
        "mip_max_level": 8,
        "dimension": 1,
        "packed_mips": True,
        "mip_address_pages": 256,
    }
    disagreements = {
        key: (metadata.get(key), wanted)
        for key, wanted in required.items()
        if metadata.get(key) != wanted
    }
    if disagreements:
        raise ShoulderTransportError(
            f"PORTME: APF shoulder_color descriptor changed: {disagreements}"
        )


def _load_png(path: Path) -> bytes:
    with Image.open(path) as image:
        image.load()
        if (
            image.format != "PNG"
            or image.size != (WIDTH, HEIGHT)
            or image.mode != "RGBA"
        ):
            raise ShoulderTransportError(
                "shoulder PNG must be exact 1024x1024 RGBA PNG"
            )
        return image.tobytes()


def _resize(rgba: bytes, target: tuple[int, int]) -> bytes:
    return Image.frombytes("RGBA", (WIDTH, HEIGHT), rgba).resize(
        target, Image.Resampling.BOX
    ).tobytes()


def _validate_structure(
    record: apf_inner.IFFRecord, blocks: list[bytes]
) -> tuple[apf_inner.IFFFile, dict[str, object], bytes]:
    expected_names = [
        "sideline_player_l0",
        "sideline_player_l1",
        "jersey_regionmap",
        "shoulder_color",
    ]
    if record.block_count != 2 or record.file_count != 4 or record.warnings:
        raise ShoulderTransportError("PORTME: shoulder IFF structure changed")
    if [item.name for item in record.files] != expected_names or any(
        item.type_name != "TXTR" for item in record.files
    ):
        raise ShoulderTransportError("PORTME: shoulder inner file roster changed")
    expected_parts = [
        [(0, 0x1C0, 0xE0), (1, 0x2C0000, 0xB4000)],
        [(0, 0x2A0, 0xE0), (1, 0x374000, 0xB4000)],
        [(0, 0x0E0, 0xE0), (1, 0x160000, 0x160000)],
        [(0, 0x000, 0xE0), (1, 0x000000, 0x160000)],
    ]
    actual_parts = [
        [(part.block_index, part.offset, part.length) for part in item.parts]
        for item in record.files
    ]
    if actual_parts != expected_parts:
        raise ShoulderTransportError(
            "PORTME: shoulder DRAM/VRAM subpart layout changed"
        )
    if [len(block) for block in blocks] != [0x380, 0x428000]:
        raise ShoulderTransportError("PORTME: shoulder decoded block lengths changed")
    target = record.files[INNER_INDEX]
    metadata = apf_inner.parse_txtr_metadata(blocks[0][:0xE0])
    strict_descriptor(metadata)
    return target, metadata, blocks[1][:TEXTURE_LENGTH]


def _rebuild_entry(
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    new_texture: bytes,
) -> tuple[bytes, dict[str, object]]:
    if len(new_texture) != TEXTURE_LENGTH or len(original_blocks) != 2:
        raise ShoulderTransportError("shoulder block or color length changed")
    new_vram = bytearray(original_blocks[1])
    new_vram[:TEXTURE_LENGTH] = new_texture
    new_blocks = [original_blocks[0], bytes(new_vram)]
    if len(original_stored) != 2 or any(
        not block.is_compressed or block.wrapper is None for block in record.blocks
    ):
        raise ShoulderTransportError("PORTME: shoulder blocks are not H7A-wrapped")
    shifts = [block.wrapper.shift for block in record.blocks if block.wrapper]
    if shifts != [9, 9]:
        raise ShoulderTransportError(f"PORTME: shoulder H7A shifts changed: {shifts}")
    if record.footer is None:
        raise ShoulderTransportError("PORTME: shoulder IFF has no validated footer")
    footer_total = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_total]
    if len(footer) != footer_total:
        raise ShoulderTransportError("PORTME: shoulder IFF footer is truncated")
    if any(original_entry[record.file_length + footer_total :]):
        raise ShoulderTransportError("PORTME: shoulder allocation tail is nonzero")
    descriptor = record.blocks[1]
    assert descriptor.wrapper is not None
    encoded = archive_patch.compress_h7a(new_blocks[1], descriptor.wrapper.shift)
    greedy_active_length = (
        record.header_size
        + len(original_stored[0])
        + apf_inner.H7A_HEADER_SIZE
        + len(encoded)
        + footer_total
    )
    if greedy_active_length > entry.size:
        encoded = archive_patch.compress_h7a_best(
            new_blocks[1], descriptor.wrapper.shift, greedy=encoded
        )
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
        raise ShoulderTransportError("shoulder H7A encode/decode round-trip failed")
    new_stored = [original_stored[0], encoded_stored]

    header = bytearray(original_entry[: record.header_size])
    body = bytearray()
    cursor = record.header_size
    block_report: list[dict[str, object]] = []
    for index, (block, stored) in enumerate(zip(record.blocks, new_stored)):
        start = cursor
        stored_length = len(stored) if block.is_compressed else block.uncompressed_length
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
            stored_length,
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
    active = bytes(header) + bytes(body) + footer
    if len(active) > entry.size:
        raise ShoulderTransportError(
            "rebuilt shoulder IFF exceeds fixed allocation by "
            f"{len(active) - entry.size} bytes"
        )
    rebuilt = active + bytes(entry.size - len(active))

    memory = archive_patch.BytesReader(rebuilt)
    check_record = apf_inner.parse_iff(memory, entry)
    check_blocks = [
        apf_inner.decode_block(memory, check_record, index, 1 << 30)
        for index in range(check_record.block_count)
    ]
    if check_blocks != new_blocks:
        raise ShoulderTransportError("rebuilt shoulder IFF did not decode as intended")
    before_parts = archive_patch._file_part_hashes(record, original_blocks)  # type: ignore[attr-defined]
    after_parts = archive_patch._file_part_hashes(check_record, check_blocks)  # type: ignore[attr-defined]
    changed_parts = [key for key in before_parts if before_parts[key] != after_parts[key]]
    if changed_parts != [(INNER_INDEX, 1)]:
        raise ShoulderTransportError(
            f"unexpected shoulder inner parts changed: {changed_parts}"
        )
    siblings = [0, 1, 2]
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
        "dram_block_preserved": new_blocks[0] == original_blocks[0],
        "three_sibling_textures_preserved": all(
            before_parts[(file_index, part_index)]
            == after_parts[(file_index, part_index)]
            for file_index in siblings
            for part_index in (0, 1)
        ),
        "preserved_inner_names": [record.files[index].name for index in siblings],
        "changed_inner_parts": [
            {"file_index": INNER_INDEX, "part_index": 1, "block_index": 1}
        ],
    }


def build_patch(
    index_path: Path, png_path: Path, row: dict[str, object]
) -> archive_patch.PatchResult:
    archive = apf_outer.parse_archive(index_path)
    entry_index = int(row["outer_table_index"])
    try:
        entry = archive.entries[entry_index]
    except IndexError as exc:
        raise ShoulderTransportError(f"outer archive has no entry {entry_index}") from exc
    if (
        entry.name_id != int(str(row["outer_name_id"]), 16)
        or len(entry.segments) != 1
        or entry.segments[0].pack_name != "0A"
    ):
        raise ShoulderTransportError("catalog target does not resolve to one 0A segment")
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
        raise ShoulderTransportError("source shoulder entry differs from pinned hash")
    _, metadata, texture = _validate_structure(record, original_blocks)
    if sha256(texture) != row["inner_file"]["texture_sha256"]:  # type: ignore[index]
        raise ShoulderTransportError("source shoulder_color differs from pinned hash")

    locations = xenos_mips.derive_layout(metadata)
    if (
        len(locations) != 9
        or len(texture) != TEXTURE_LENGTH
        or xenos_mips.transport_roundtrip(texture, locations) != texture
    ):
        raise ShoulderTransportError("retail nine-level BC3 transport is not bit-exact")
    original_linear = [
        xenos_mips.extract_linear_bc3(texture, location) for location in locations
    ]
    original_rgba = [
        bc3_backend._decode_linear_bc3(linear, location)  # type: ignore[attr-defined]
        for linear, location in zip(original_linear, locations)
    ]
    wanted_base = _load_png(png_path)
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
    if wanted_base == original_rgba[0]:
        return archive_patch.PatchResult(
            original_entry,
            {
                "schema": SCHEMA,
                "mode": "no_op",
                "source": common_source,
                "target": {"descriptor": metadata, "layout": layout_report},
                "levels": [
                    {
                        "level": item.level,
                        "linear_bc3_sha256": sha256(linear),
                        "decoded_rgba_sha256": sha256(rgba),
                    }
                    for item, linear, rgba in zip(
                        locations, original_linear, original_rgba
                    )
                ],
                "validation": {
                    "all_nine_levels_extracted": True,
                    "all_nine_levels_transport_bit_exact": True,
                    "input_matches_decoded_base": True,
                    "entry_bit_exact": True,
                    "source_opened_read_only": True,
                },
                "backend": {
                    "png_and_mips": f"Pillow {PILLOW_VERSION}; BOX filter",
                    "bc3": "not invoked for bit-exact no-op",
                    "xenos_layout": f"Xenia-derived, commit {xenos_mips.XENIA_COMMIT}",
                    "h7a": "not invoked for bit-exact no-op",
                },
                "portme": [PRODUCTION_BC3_CAVEAT],
            },
        )

    wanted_levels = [wanted_base] + [
        _resize(wanted_base, (item.width, item.height)) for item in locations[1:]
    ]
    new_texture = texture
    changed_linear: list[bytes] = []
    changed_indices: list[list[int]] = []
    for location, source_linear, source_rgba, wanted in zip(
        locations, original_linear, original_rgba, wanted_levels
    ):
        # shoulder_color is a selector mask whose retail alpha is unused and
        # uniformly zero. Preview/export display may force it opaque so RGB is
        # visible, but the encoder must restore the original zero alpha.
        wanted = apf_inner.restore_unused_mask_alpha_for_encode(
            wanted, source_rgba
        )
        linear, indices = bc3_backend._encode_changed_blocks(  # type: ignore[attr-defined]
            source_linear, source_rgba, wanted, location
        )
        new_texture = xenos_mips.insert_linear_bc3(new_texture, location, linear)
        changed_linear.append(linear)
        changed_indices.append(indices)
    if not changed_indices[0]:
        raise ShoulderTransportError("changed PNG produced no changed base BC3 block")
    if xenos_mips.transport_roundtrip(new_texture, locations) != new_texture:
        raise ShoulderTransportError("patched nine-level BC3 transport is not bit-exact")
    mask = bc3_backend._active_byte_mask(len(texture), locations)  # type: ignore[attr-defined]
    inactive_before = bc3_backend._hash_inactive(texture, mask)  # type: ignore[attr-defined]
    inactive_after = bc3_backend._hash_inactive(new_texture, mask)  # type: ignore[attr-defined]
    if inactive_before != inactive_after:
        raise ShoulderTransportError("inactive shoulder mip bytes changed")

    levels = []
    for location, before, after, wanted, indices in zip(
        locations, original_linear, changed_linear, wanted_levels, changed_indices
    ):
        decoded = bc3_backend._decode_linear_bc3(after, location)  # type: ignore[attr-defined]
        levels.append(
            {
                "level": location.level,
                "width": location.width,
                "height": location.height,
                "packed_tail": location.packed_tail,
                "origin_block_x": location.origin_block_x,
                "origin_block_y": location.origin_block_y,
                "linear_bc3_sha256_before": sha256(before),
                "linear_bc3_sha256_after": sha256(after),
                "wanted_rgba_sha256": sha256(wanted),
                "decoded_rgba_sha256_after": sha256(decoded),
                "changed_bc3_blocks": bc3_backend._indices_summary(indices),  # type: ignore[attr-defined]
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
                "all_nine_levels_regenerated": True,
                "all_nine_levels_decoded_back": True,
                "all_nine_levels_transport_bit_exact": True,
                "packed_tail_levels": [6, 7, 8],
                "packed_tail_origins_blocks": [[4, 0], [2, 0], [1, 0]],
                "inactive_mip_padding_preserved": True,
                "h7a_decode_encode_decode_exact": True,
                "rebuilt_iff_reparsed": True,
                "footer_bit_exact": True,
                "shoulder_color_dram_preserved": True,
                "jersey_regionmap_preserved": True,
                "two_sideline_textures_preserved": True,
                "fixed_outer_allocation": True,
                "source_opened_read_only": True,
            },
            "backend": {
                "png_and_mips": f"Pillow {PILLOW_VERSION}; BOX filter",
                "bc3": "project-native deterministic touched-block proof encoder",
                "bc3_production_caveat": PRODUCTION_BC3_CAVEAT,
                "xenos_layout": f"Xenia-derived, commit {xenos_mips.XENIA_COMMIT}",
                "h7a": "project-native greedy H7A encoder",
            },
            "portme": [
                "validate changed copied volumes in Xenia and on hardware",
                PRODUCTION_BC3_CAVEAT,
                "replace BOX filtering with an artist-selectable gamma-aware mip filter",
            ],
        },
    )
