#!/usr/bin/env python3
"""Safely replace the proven Americans jersey in a copied APF 2K8 volume.

This is an evidence-bounded writer for exactly outer entry 875
(``uniform_jersey_06.iff``), inner file 0 (``jersey_color``).  It regenerates
the visible base plus all eight stored BC3 mip levels, including the Xenos
packed tail, rebuilds the H7A/IFF inside the existing 32 KiB allocation, and
can only write a newly copied ``0A`` volume.  Retail source files are never
opened for writing.

The bundled BC3 encoder is deterministic and useful for transport proof, but
is not a production-quality perceptual encoder.  The command reports that
caveat on every changed output and refuses any image whose rebuilt IFF does not
fit the original allocation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

try:
    from PIL import Image, __version__ as PILLOW_VERSION
except ImportError as exc:  # pragma: no cover
    raise SystemExit("error: Pillow is required for PNG import and mip generation") from exc

import apf_inner
import apf_outer
import apf_texture_patch as archive_patch
import apf_xenos_mip_layout as xenos_mips


SCHEMA = "apf_uniform_mip_patch/v1"
ENTRY_INDEX = 875
FILE_INDEX = 0
ENTRY_NAME = "uniform_jersey_06.iff"
INNER_NAME = "jersey_color"
EXPECTED_ENTRY_SHA256 = "9f4740ddbbcc86d1d7a880a50f12d9e2580e049633b9beb065fc193a78130ca2"
EXPECTED_TEXTURE_SHA256 = "027e49dc8b1445cba4ec73c9cdadada15360ac755f87b5c4b6db6f8772c95cdf"
PRODUCTION_BC3_CAVEAT = (
    "The project-native deterministic BC3 endpoint search is a proof backend, "
    "not a production-quality perceptual compressor; visually inspect mods and "
    "replace it with a vetted high-quality BC3 encoder before broad release."
)


class UniformPatchError(ValueError):
    """Raised when a uniform patch cannot be proved safe."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_linear_bc3(
    linear: bytes, location: xenos_mips.MipLocation
) -> bytes:
    expected = location.logical_block_count * xenos_mips.BYTES_PER_BLOCK
    if len(linear) != expected:
        raise UniformPatchError(
            f"mip {location.level} BC3 payload has the wrong length"
        )
    rgba = bytearray(location.width * location.height * 4)
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            block_index = block_y * location.width_blocks + block_x
            pixels = apf_inner._decode_bc3(  # type: ignore[attr-defined]
                linear[
                    block_index * xenos_mips.BYTES_PER_BLOCK :
                    (block_index + 1) * xenos_mips.BYTES_PER_BLOCK
                ]
            )
            for local_y in range(4):
                for local_x in range(4):
                    x = block_x * 4 + local_x
                    y = block_y * 4 + local_y
                    if x >= location.width or y >= location.height:
                        continue
                    destination = (y * location.width + x) * 4
                    rgba[destination : destination + 4] = bytes(
                        pixels[local_y * 4 + local_x]
                    )
    return bytes(rgba)


def _load_png(path: Path, width: int, height: int) -> bytes:
    with Image.open(path) as image:
        image.load()
        if image.size != (width, height):
            raise UniformPatchError(
                f"PNG is {image.width}x{image.height}; target is {width}x{height}"
            )
        return image.convert("RGBA").tobytes()


def _resize_rgba_box(
    rgba: bytes, source_size: tuple[int, int], target_size: tuple[int, int]
) -> bytes:
    image = Image.frombytes("RGBA", source_size, rgba)
    return image.resize(target_size, Image.Resampling.BOX).tobytes()


def _encode_changed_blocks(
    original_linear: bytes,
    original_rgba: bytes,
    wanted_rgba: bytes,
    location: xenos_mips.MipLocation,
) -> tuple[bytes, list[int]]:
    if len(original_rgba) != location.width * location.height * 4:
        raise UniformPatchError(f"mip {location.level} original RGBA length is invalid")
    if len(wanted_rgba) != len(original_rgba):
        raise UniformPatchError(f"mip {location.level} wanted RGBA length is invalid")
    result = bytearray(original_linear)
    changed: list[int] = []
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            pixel_offsets = [
                ((block_y * 4 + local_y) * location.width + block_x * 4 + local_x)
                * 4
                for local_y in range(4)
                for local_x in range(4)
            ]
            if all(
                wanted_rgba[offset : offset + 4]
                == original_rgba[offset : offset + 4]
                for offset in pixel_offsets
            ):
                continue
            pixels = [
                tuple(wanted_rgba[offset : offset + 4]) for offset in pixel_offsets
            ]
            block_index = block_y * location.width_blocks + block_x
            result[
                block_index * xenos_mips.BYTES_PER_BLOCK :
                (block_index + 1) * xenos_mips.BYTES_PER_BLOCK
            ] = archive_patch.encode_bc3_block(pixels)  # type: ignore[arg-type]
            changed.append(block_index)
    return bytes(result), changed


def _indices_summary(indices: list[int]) -> dict[str, object]:
    serialized = b"".join(index.to_bytes(4, "big") for index in indices)
    return {
        "count": len(indices),
        "first": indices[0] if indices else None,
        "last": indices[-1] if indices else None,
        "big_endian_u32_sha256": _sha256(serialized),
        "indices_embedded": indices if len(indices) <= 256 else None,
    }


def _active_byte_mask(
    texture_length: int, locations: tuple[xenos_mips.MipLocation, ...]
) -> bytearray:
    mask = bytearray(texture_length)
    for location in locations:
        for block_y in range(location.height_blocks):
            for block_x in range(location.width_blocks):
                relative = apf_inner._tiled_2d_offset(  # type: ignore[attr-defined]
                    block_x + location.origin_block_x,
                    block_y + location.origin_block_y,
                    location.pitch_blocks,
                    xenos_mips.BYTES_PER_BLOCK.bit_length() - 1,
                )
                start = location.data_offset + relative
                mask[start : start + xenos_mips.BYTES_PER_BLOCK] = b"\1" * 16
    return mask


def _hash_inactive(data: bytes, active_mask: bytearray) -> str:
    digest = hashlib.sha256()
    for index, value in enumerate(data):
        if not active_mask[index]:
            digest.update(bytes((value,)))
    return digest.hexdigest()


def _strict_descriptor(metadata: dict[str, object]) -> None:
    required = {
        "vc_file_id": "0x1ff6ec38",
        "vc_width": 1024,
        "vc_height": 1024,
        "vc_base_data_length": 1048576,
        "vc_mip_data_length": 393216,
        "pitch_pixels": 1024,
        "tiled": True,
        "format": 20,
        "endianness": 1,
        "stacked": False,
        "width": 1024,
        "height": 1024,
        "swizzle_components": [0, 1, 2, 3],
        "mip_min_level": 0,
        "mip_max_level": 8,
        "dimension": 1,
        "packed_mips": True,
        "mip_address_pages": 256,
    }
    disagreements = {
        key: (metadata.get(key), expected)
        for key, expected in required.items()
        if metadata.get(key) != expected
    }
    if disagreements:
        raise UniformPatchError(
            f"PORTME: Americans jersey descriptor changed: {disagreements}"
        )


def _rebuild_entry(
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    new_texture: bytes,
) -> tuple[bytes, dict[str, object]]:
    if len(original_blocks) != 2 or len(original_stored) != 2:
        raise UniformPatchError("PORTME: uniform IFF no longer has exactly two blocks")
    new_blocks = [original_blocks[0], new_texture]
    descriptor = record.blocks[1]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise UniformPatchError("PORTME: uniform VRAM block is no longer H7A-compressed")
    encoded = archive_patch.compress_h7a(new_texture, descriptor.wrapper.shift)
    encoded_stored = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(new_texture),
        apf_inner.H7A_HEADER_SIZE + len(encoded),
        descriptor.unknown_10,
        descriptor.wrapper.shift,
    ) + encoded
    if apf_inner.decompress_h7a(
        encoded, len(new_texture), descriptor.wrapper.shift
    ) != new_texture:
        raise UniformPatchError("H7A encode/decode round-trip failed")
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
                "stored_sha256_before": _sha256(original_stored[index]),
                "stored_sha256_after": _sha256(stored),
                "decoded_sha256_before": _sha256(original_blocks[index]),
                "decoded_sha256_after": _sha256(new_blocks[index]),
            }
        )

    new_file_length = record.header_size + len(body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    if record.footer is None:
        raise UniformPatchError("PORTME: uniform IFF has no validated name footer")
    footer_total = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_total]
    old_tail = original_entry[record.file_length + footer_total :]
    if any(old_tail):
        raise UniformPatchError("PORTME: uniform outer allocation tail is nonzero")
    active = bytes(header) + bytes(body) + footer
    if len(active) > entry.size:
        raise UniformPatchError(
            "rebuilt uniform IFF exceeds its fixed outer allocation by "
            f"{len(active) - entry.size} bytes; refusing output"
        )
    rebuilt = active + b"\0" * (entry.size - len(active))

    memory_reader = archive_patch.BytesReader(rebuilt)
    rebuilt_record = apf_inner.parse_iff(memory_reader, entry)
    rebuilt_blocks = [
        apf_inner.decode_block(memory_reader, rebuilt_record, index, 1 << 30)
        for index in range(rebuilt_record.block_count)
    ]
    if rebuilt_blocks != new_blocks:
        raise UniformPatchError("rebuilt uniform IFF does not decode as intended")
    before_parts = archive_patch._file_part_hashes(record, original_blocks)  # type: ignore[attr-defined]
    after_parts = archive_patch._file_part_hashes(rebuilt_record, rebuilt_blocks)  # type: ignore[attr-defined]
    changed_parts = [key for key in before_parts if before_parts[key] != after_parts[key]]
    if changed_parts != [(FILE_INDEX, 1)]:
        raise UniformPatchError(f"unexpected inner parts changed: {changed_parts}")

    return rebuilt, {
        "allocation_size": entry.size,
        "file_length_before": record.file_length,
        "file_length_after": new_file_length,
        "allocation_slack_after": entry.size - len(active),
        "h7a_shift": descriptor.wrapper.shift,
        "h7a_decode_encode_decode_exact": True,
        "footer_sha256_before": _sha256(footer),
        "footer_sha256_after": _sha256(
            rebuilt[new_file_length : new_file_length + footer_total]
        ),
        "footer_bit_exact": rebuilt[
            new_file_length : new_file_length + footer_total
        ] == footer,
        "blocks": block_report,
        "rebuilt_iff_reparsed": True,
        "unrelated_dram_part_preserved": before_parts[(0, 0)] == after_parts[(0, 0)],
        "changed_inner_parts": [
            {"file_index": FILE_INDEX, "part_index": 1, "block_index": 1}
        ],
    }


def build_patch(index_path: Path, png_path: Path) -> archive_patch.PatchResult:
    archive = apf_outer.parse_archive(index_path)
    try:
        entry = archive.entries[ENTRY_INDEX]
    except IndexError as exc:
        raise UniformPatchError(f"outer archive has no entry {ENTRY_INDEX}") from exc
    if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
        raise UniformPatchError("PORTME: Americans jersey is not in one 0A segment")

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
    if _sha256(original_entry) != EXPECTED_ENTRY_SHA256:
        raise UniformPatchError(
            "source entry hash is not the pinned retail Americans jersey; refusing"
        )
    if record.file_count != 1 or record.block_count != 2:
        raise UniformPatchError("PORTME: uniform IFF structure changed")
    target = record.files[FILE_INDEX]
    if target.name != INNER_NAME or target.type_name != "TXTR":
        raise UniformPatchError(
            f"expected {INNER_NAME!r}/TXTR, got {target.name!r}/{target.type_name!r}"
        )
    if len(target.parts) != 2 or target.parts[0].block_index != 0 or target.parts[1].block_index != 1:
        raise UniformPatchError("PORTME: uniform TXTR DRAM/VRAM pairing changed")

    dram_part, texture_part = target.parts
    dram = original_blocks[0][dram_part.offset : dram_part.offset + dram_part.length]
    texture = original_blocks[1][
        texture_part.offset : texture_part.offset + texture_part.length
    ]
    if _sha256(texture) != EXPECTED_TEXTURE_SHA256:
        raise UniformPatchError("decoded uniform texture hash is not the pinned retail data")
    metadata = apf_inner.parse_txtr_metadata(dram)
    _strict_descriptor(metadata)
    locations = xenos_mips.derive_layout(metadata)
    if len(texture) != int(metadata["vc_base_data_length"]) + int(
        metadata["vc_mip_data_length"]
    ):
        raise UniformPatchError("declared base+mip lengths do not cover the TXTR payload")
    if xenos_mips.transport_roundtrip(texture, locations) != texture:
        raise UniformPatchError("nine-level Xenos extract/reinsert is not bit-exact")

    original_linear = [
        xenos_mips.extract_linear_bc3(texture, location) for location in locations
    ]
    original_rgba = [
        _decode_linear_bc3(linear, location)
        for linear, location in zip(original_linear, locations)
    ]
    wanted_base = _load_png(png_path, locations[0].width, locations[0].height)
    common_source = {
        "archive_index": str(index_path),
        "physical_volume": entry.segments[0].pack_name,
        "outer_entry_index": ENTRY_INDEX,
        "outer_name": ENTRY_NAME,
        "inner_file_index": FILE_INDEX,
        "inner_name": INNER_NAME,
        "entry_sha256": _sha256(original_entry),
        "texture_sha256": _sha256(texture),
        "png_rgba_sha256": _sha256(wanted_base),
    }
    layout_report = [location.manifest() for location in locations]
    level_source_report = [
        {
            "level": location.level,
            "linear_bc3_sha256": _sha256(linear),
            "decoded_rgba_sha256": _sha256(rgba),
        }
        for location, linear, rgba in zip(locations, original_linear, original_rgba)
    ]

    if wanted_base == original_rgba[0]:
        return archive_patch.PatchResult(
            original_entry,
            {
                "schema": SCHEMA,
                "mode": "no_op",
                "source": common_source,
                "target": {"descriptor": metadata, "layout": layout_report},
                "levels": level_source_report,
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
                "portme": [
                    "validate a changed copied volume in Xenia and on hardware",
                    PRODUCTION_BC3_CAVEAT,
                    "generalize only after independently proving other descriptors",
                ],
            },
        )

    wanted_levels = [wanted_base]
    for location in locations[1:]:
        wanted_levels.append(
            _resize_rgba_box(
                wanted_base,
                (locations[0].width, locations[0].height),
                (location.width, location.height),
            )
        )

    new_texture = texture
    changed_linear: list[bytes] = []
    changed_indices: list[list[int]] = []
    for location, source_linear, source_rgba, wanted_rgba in zip(
        locations, original_linear, original_rgba, wanted_levels
    ):
        new_linear, indices = _encode_changed_blocks(
            source_linear, source_rgba, wanted_rgba, location
        )
        new_texture = xenos_mips.insert_linear_bc3(
            new_texture, location, new_linear
        )
        changed_linear.append(new_linear)
        changed_indices.append(indices)
    if not changed_indices[0]:
        raise UniformPatchError("changed PNG produced no changed base BC3 block")
    if xenos_mips.transport_roundtrip(new_texture, locations) != new_texture:
        raise UniformPatchError("patched nine-level Xenos transport is not bit-exact")

    active_mask = _active_byte_mask(len(texture), locations)
    inactive_before = _hash_inactive(texture, active_mask)
    inactive_after = _hash_inactive(new_texture, active_mask)
    if inactive_before != inactive_after:
        raise UniformPatchError("inactive mip padding bytes changed")
    level_reports: list[dict[str, object]] = []
    for location, before_linear, after_linear, wanted, indices in zip(
        locations, original_linear, changed_linear, wanted_levels, changed_indices
    ):
        decoded = _decode_linear_bc3(after_linear, location)
        level_reports.append(
            {
                "level": location.level,
                "width": location.width,
                "height": location.height,
                "packed_tail": location.packed_tail,
                "origin_block_x": location.origin_block_x,
                "origin_block_y": location.origin_block_y,
                "linear_bc3_sha256_before": _sha256(before_linear),
                "linear_bc3_sha256_after": _sha256(after_linear),
                "wanted_rgba_sha256": _sha256(wanted),
                "decoded_rgba_sha256_after": _sha256(decoded),
                "changed_bc3_blocks": _indices_summary(indices),
                "decode_back_metrics": archive_patch._rgba_metrics(wanted, decoded),  # type: ignore[attr-defined]
            }
        )

    rebuilt_entry, iff_report = _rebuild_entry(
        entry,
        record,
        original_entry,
        original_blocks,
        original_stored,
        new_texture,
    )
    manifest = {
        "schema": SCHEMA,
        "mode": "patched",
        "source": common_source,
        "target": {"descriptor": metadata, "layout": layout_report},
        "levels": level_reports,
        "texture": {
            "length": len(texture),
            "sha256_before": _sha256(texture),
            "sha256_after": _sha256(new_texture),
            "inactive_padding_sha256_before": inactive_before,
            "inactive_padding_sha256_after": inactive_after,
            "inactive_padding_bit_exact": True,
        },
        "iff": iff_report,
        "binary_patch_manifest": {
            "physical_volume": entry.segments[0].pack_name,
            "physical_offset": entry.segments[0].pack_offset,
            "replacement_length": entry.size,
            "original_sha256": _sha256(original_entry),
            "replacement_sha256": _sha256(rebuilt_entry),
            **archive_patch._changed_extents(original_entry, rebuilt_entry),  # type: ignore[attr-defined]
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
            "unrelated_dram_part_preserved": True,
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
            "validate this changed copied volume in Xenia and on hardware",
            PRODUCTION_BC3_CAVEAT,
            "replace BOX filtering with an artist-selectable gamma-aware mip filter",
            "generalize only after independently proving other descriptors",
        ],
    }
    return archive_patch.PatchResult(rebuilt_entry, manifest)


def _write_new(path: Path, data: bytes) -> None:
    archive_patch._write_new(path, data)  # type: ignore[attr-defined]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="user-owned APF 0A")
    parser.add_argument("--png", required=True, type=Path, help="edited 1024x1024 RGBA PNG")
    parser.add_argument("--output-entry", type=Path, help="new rebuilt logical IFF path")
    parser.add_argument(
        "--output-volume",
        type=Path,
        help="copy 0A to this new path, then patch only the fixed jersey entry",
    )
    parser.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest_reservation: archive_patch.OutputReservation | None = None
    manifest_path = args.manifest.expanduser()
    try:
        index_path = args.index.expanduser()
        png_path = args.png.expanduser()
        output_entry = (
            args.output_entry.expanduser() if args.output_entry is not None else None
        )
        output_volume = (
            args.output_volume.expanduser() if args.output_volume is not None else None
        )
        archive_patch._preflight_output_paths(  # type: ignore[attr-defined]
            [index_path, png_path],
            [("manifest", manifest_path), ("output entry", output_entry),
             ("output volume", output_volume)],
        )
        manifest_reservation = archive_patch._reserve_new(manifest_path)  # type: ignore[attr-defined]
        result = build_patch(index_path, png_path)
        archive = apf_outer.parse_archive(index_path)
        document = result.manifest
        if output_entry is not None:
            _write_new(output_entry, result.entry_bytes)
            document["output_entry"] = {
                "path": str(output_entry),
                "size": len(result.entry_bytes),
                "sha256": _sha256(result.entry_bytes),
            }
        if output_volume is not None:
            document["copied_volume"] = archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                index_path,
                output_volume,
                archive.entries[ENTRY_INDEX],
                result.entry_bytes,
            )
        archive_patch._commit_reserved(  # type: ignore[attr-defined]
            manifest_path,
            manifest_reservation,
            (json.dumps(document, indent=2) + "\n").encode("utf-8"),
        )
        archive_patch._close_reserved(manifest_reservation)  # type: ignore[attr-defined]
        manifest_reservation = None
        print(
            "APF_UNIFORM_MIP_PATCH_PASS "
            f"mode={document['mode']} entry={ENTRY_INDEX} file={FILE_INDEX} "
            f"sha256={_sha256(result.entry_bytes)}"
        )
    except (
        UniformPatchError,
        xenos_mips.MipLayoutError,
        archive_patch.PatchError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        OSError,
    ) as exc:
        if manifest_reservation is not None:
            archive_patch._abort_reserved(  # type: ignore[attr-defined]
                manifest_path, manifest_reservation
            )
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
