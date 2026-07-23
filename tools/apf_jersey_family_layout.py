#!/usr/bin/env python3
"""Prove the APF 2K8 nine-mip jersey layout across all 24 packages.

This analyzer is intentionally read-only with respect to the game archive.  It
locates ``uniform_jersey_00.iff`` through ``uniform_jersey_23.iff`` by their
outer CRC identifiers, reparses every IFF/TXTR directly, exercises the
Xenia-derived tiled mip transport, and performs a controlled solid-color IFF
rebuild entirely in memory.  It emits hashes and structure only; it never
writes a replacement entry or volume.

The result establishes structural compatibility with the currently narrow
Americans jersey proof writer.  It does not expose a general writer and does
not claim runtime visibility in Xenia or on Xbox 360 hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zlib

import apf_inner
import apf_outer
import apf_texture_patch as archive_patch
import apf_uniform_mip_patch as uniform_patch
import apf_xenos_mip_layout as xenos_mips


SCHEMA = "apf_jersey_family_layout/v1"
EXPECTED_VOLUME_SIZE = 1_140_850_688
EXPECTED_VOLUME_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)
JERSEY_COUNT = 24
INNER_INDEX = 0
INNER_NAME = "jersey_color"
SOLID_RGBA = (255, 0, 255, 255)
DEPENDENCIES = (
    "apf_inner.py",
    "apf_outer.py",
    "apf_texture_patch.py",
    "apf_uniform_mip_patch.py",
    "apf_xenos_mip_layout.py",
)


class FamilyLayoutError(ValueError):
    """Raised when a jersey package violates the proved family structure."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _outer_name_id(name: str) -> int:
    return zlib.crc32(name.upper().encode("ascii")) & 0xFFFFFFFF


def _hex(value: int) -> str:
    return f"0x{value:08x}"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _block_manifest(
    block: apf_inner.Block, stored: bytes, decoded: bytes
) -> dict[str, object]:
    wrapper = block.wrapper
    return {
        "index": block.descriptor_index,
        "name_hash": _hex(block.name_hash),
        "type_hash": _hex(block.type_hash),
        "unknown_08": _hex(block.unknown_08),
        "unknown_10": _hex(block.unknown_10),
        "indexed": block.indexed,
        "start_offset": block.start_offset,
        "uncompressed_length": block.uncompressed_length,
        "stored_length": block.stored_length,
        "is_h7a_compressed": block.is_compressed,
        "h7a": None
        if wrapper is None
        else {
            "magic": _hex(wrapper.magic),
            "uncompressed_length": wrapper.uncompressed_length,
            "compressed_length": wrapper.compressed_length,
            "unknown": _hex(wrapper.unknown),
            "shift": wrapper.shift,
        },
        "stored_sha256": _sha256(stored),
        "decoded_sha256": _sha256(decoded),
    }


def _part_manifest(
    part_index: int, part: apf_inner.FilePart, blocks: list[bytes]
) -> dict[str, object]:
    payload = blocks[part.block_index][part.offset : part.offset + part.length]
    return {
        "part_index": part_index,
        "block_index": part.block_index,
        "offset": part.offset,
        "length": part.length,
        "sha256": _sha256(payload),
    }


def _dependency_hashes() -> list[dict[str, object]]:
    tools_dir = Path(__file__).resolve().parent
    return [
        {
            "path": f"tools/{name}",
            "sha256": _sha256_file(tools_dir / name),
        }
        for name in DEPENDENCIES
    ]


def _analyze_jersey(
    reader: apf_inner.ArchiveReader,
    entry: apf_outer.Entry,
    asset_index: int,
    outer_name: str,
    solid_bc3: bytes,
    reference_descriptor: dict[str, object] | None,
    reference_layout: list[dict[str, object]] | None,
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    if len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
        raise FamilyLayoutError(
            f"{outer_name}: expected one physical segment in 0A"
        )
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

    if record.block_count != 2 or record.file_count != 1:
        raise FamilyLayoutError(
            f"{outer_name}: expected two blocks and one inner file"
        )
    if record.warnings:
        raise FamilyLayoutError(f"{outer_name}: IFF warnings: {record.warnings}")
    if record.footer is None:
        raise FamilyLayoutError(f"{outer_name}: missing validated name footer")
    if not all(block.is_compressed and block.wrapper for block in record.blocks):
        raise FamilyLayoutError(f"{outer_name}: both blocks must be H7A-wrapped")
    h7a_shifts = [block.wrapper.shift for block in record.blocks if block.wrapper]
    if h7a_shifts != [8, 8]:
        raise FamilyLayoutError(
            f"{outer_name}: unexpected H7A shifts {h7a_shifts}"
        )

    target = record.files[INNER_INDEX]
    if target.name != INNER_NAME or target.type_name != "TXTR":
        raise FamilyLayoutError(
            f"{outer_name}: expected {INNER_NAME!r}/TXTR, got "
            f"{target.name!r}/{target.type_name!r}"
        )
    if (
        len(target.parts) != 2
        or target.parts[0].block_index != 0
        or target.parts[1].block_index != 1
        or target.parts[0].offset != 0
        or target.parts[1].offset != 0
        or target.parts[0].length != len(original_blocks[0])
        or target.parts[1].length != len(original_blocks[1])
    ):
        raise FamilyLayoutError(
            f"{outer_name}: TXTR is not the complete block-0/block-1 DRAM/VRAM pair"
        )

    dram = original_blocks[0]
    texture = original_blocks[1]
    descriptor = apf_inner.parse_txtr_metadata(dram)
    # Reuse the narrow writer's exact descriptor gate, then additionally
    # require complete descriptor identity across the family.
    uniform_patch._strict_descriptor(descriptor)  # type: ignore[attr-defined]
    if reference_descriptor is not None and _canonical(descriptor) != _canonical(
        reference_descriptor
    ):
        raise FamilyLayoutError(f"{outer_name}: complete TXTR descriptor drift")

    locations = xenos_mips.derive_layout(descriptor)
    if len(locations) != 9:
        raise FamilyLayoutError(f"{outer_name}: expected nine stored mip levels")
    layout = [location.manifest() for location in locations]
    if reference_layout is not None and _canonical(layout) != _canonical(
        reference_layout
    ):
        raise FamilyLayoutError(f"{outer_name}: Xenos mip layout drift")
    if [(item.level, item.origin_block_x, item.origin_block_y) for item in locations[6:]] != [
        (6, 4, 0),
        (7, 2, 0),
        (8, 1, 0),
    ]:
        raise FamilyLayoutError(f"{outer_name}: packed-tail origins drifted")
    declared_texture_length = int(descriptor["vc_base_data_length"]) + int(
        descriptor["vc_mip_data_length"]
    )
    if len(texture) != declared_texture_length:
        raise FamilyLayoutError(
            f"{outer_name}: decoded texture length differs from TXTR declaration"
        )

    linear_levels = [
        xenos_mips.extract_linear_bc3(texture, location) for location in locations
    ]
    if xenos_mips.transport_roundtrip(texture, locations) != texture:
        raise FamilyLayoutError(
            f"{outer_name}: retail nine-level extract/reinsert is not bit-exact"
        )
    levels = [
        {
            **location.manifest(),
            "linear_bc3_sha256": _sha256(linear),
        }
        for location, linear in zip(locations, linear_levels)
    ]

    active_mask = uniform_patch._active_byte_mask(  # type: ignore[attr-defined]
        len(texture), locations
    )
    inactive_before = uniform_patch._hash_inactive(  # type: ignore[attr-defined]
        texture, active_mask
    )
    solid_texture = texture
    solid_level_hashes: list[dict[str, object]] = []
    for location in locations:
        wanted_linear = solid_bc3 * location.logical_block_count
        solid_texture = xenos_mips.insert_linear_bc3(
            solid_texture, location, wanted_linear
        )
        extracted = xenos_mips.extract_linear_bc3(solid_texture, location)
        if extracted != wanted_linear:
            raise FamilyLayoutError(
                f"{outer_name}: solid mip {location.level} did not extract exactly"
            )
        solid_level_hashes.append(
            {
                "level": location.level,
                "logical_block_count": location.logical_block_count,
                "linear_bc3_sha256": _sha256(wanted_linear),
                "extract_after_insert_bit_exact": True,
            }
        )
    if xenos_mips.transport_roundtrip(solid_texture, locations) != solid_texture:
        raise FamilyLayoutError(
            f"{outer_name}: controlled texture transport is not bit-exact"
        )
    inactive_after = uniform_patch._hash_inactive(  # type: ignore[attr-defined]
        solid_texture, active_mask
    )
    if inactive_before != inactive_after:
        raise FamilyLayoutError(
            f"{outer_name}: controlled rebuild changed inactive mip bytes"
        )

    rebuilt_entry, iff_rebuild = uniform_patch._rebuild_entry(  # type: ignore[attr-defined]
        entry,
        record,
        original_entry,
        original_blocks,
        original_stored,
        solid_texture,
    )
    if len(rebuilt_entry) != entry.size:
        raise FamilyLayoutError(
            f"{outer_name}: controlled rebuild changed the fixed allocation"
        )

    footer_size = 8 + record.footer.payload_size
    active_length = record.file_length + footer_size
    tail = original_entry[active_length:]
    if any(tail):
        raise FamilyLayoutError(f"{outer_name}: allocation tail is not all zero")
    parts = [
        _part_manifest(index, part, original_blocks)
        for index, part in enumerate(target.parts)
    ]
    file_payload = b"".join(
        original_blocks[part.block_index][part.offset : part.offset + part.length]
        for part in target.parts
    )
    footer = original_entry[record.file_length:active_length]

    result = {
        "asset_index": asset_index,
        "outer_name": outer_name,
        "outer_name_id": _hex(entry.name_id),
        "outer_table_index": entry.table_index,
        "physical": {
            "pack_name": entry.segments[0].pack_name,
            "pack_offset": entry.segments[0].pack_offset,
            "virtual_offset": entry.virtual_offset,
        },
        "outer_allocation": {
            "size": entry.size,
            "sha256": _sha256(original_entry),
            "active_length": active_length,
            "slack_before": entry.size - active_length,
            "slack_tail_all_zero": True,
            "slack_tail_sha256": _sha256(tail),
        },
        "iff": {
            "header_size": record.header_size,
            "file_length_excluding_footer": record.file_length,
            "block_count": record.block_count,
            "file_count": record.file_count,
            "header_padding_size": record.header_padding_size,
            "zero": record.zero,
            "unknown_14": _hex(record.unknown_14),
            "unknown_1c": _hex(record.unknown_1c),
            "warnings": record.warnings,
            "blocks": [
                _block_manifest(block, stored, decoded)
                for block, stored, decoded in zip(
                    record.blocks, original_stored, original_blocks
                )
            ],
            "footer": {
                "magic": _hex(record.footer.magic),
                "payload_size": record.footer.payload_size,
                "name_count": record.footer.name_count,
                "total_size": footer_size,
                "sha256": _sha256(footer),
            },
        },
        "inner_file": {
            "index": target.index,
            "name": target.name,
            "file_id": _hex(target.file_id),
            "type_name": target.type_name,
            "type_hash": _hex(target.type_hash),
            "parts": parts,
            "concatenated_parts_length": len(file_payload),
            "concatenated_parts_sha256": _sha256(file_payload),
            "dram_sha256": _sha256(dram),
            "texture_sha256": _sha256(texture),
        },
        "txtr_descriptor": descriptor,
        "nine_level_layout": levels,
        "transport": {
            "retail_extract_reinsert_bit_exact": True,
            "active_blocks_non_aliasing": True,
            "packed_tail_levels": [6, 7, 8],
            "packed_tail_origins_blocks": [[4, 0], [2, 0], [1, 0]],
        },
        "controlled_solid_rebuild_in_memory": {
            "solid_rgba": list(SOLID_RGBA),
            "levels": solid_level_hashes,
            "texture_sha256": _sha256(solid_texture),
            "inactive_padding_sha256_before": inactive_before,
            "inactive_padding_sha256_after": inactive_after,
            "inactive_padding_bit_exact": True,
            "transport_bit_exact": True,
            "rebuilt_entry_length": len(rebuilt_entry),
            "rebuilt_entry_sha256": _sha256(rebuilt_entry),
            "fixed_outer_allocation": True,
            "iff": iff_rebuild,
            "entry_or_volume_written": False,
        },
    }
    return result, descriptor, layout


def analyze(index_path: Path) -> tuple[dict[str, object], str]:
    index_path = index_path.expanduser().resolve()
    before_stat = index_path.stat()
    if before_stat.st_size != EXPECTED_VOLUME_SIZE:
        raise FamilyLayoutError(
            f"0A is {before_stat.st_size} bytes, expected {EXPECTED_VOLUME_SIZE}"
        )
    source_sha_before = _sha256_file(index_path)
    if source_sha_before != EXPECTED_VOLUME_SHA256:
        raise FamilyLayoutError(
            "source is not the pinned retail APF 2K8 0A volume"
        )

    archive = apf_outer.parse_archive(index_path)
    entries_by_name_id: dict[int, apf_outer.Entry] = {}
    for entry in archive.entries:
        if entry.name_id in entries_by_name_id:
            raise FamilyLayoutError(
                f"duplicate outer name ID {_hex(entry.name_id)}"
            )
        entries_by_name_id[entry.name_id] = entry

    solid_bc3 = archive_patch.encode_bc3_block([SOLID_RGBA] * 16)
    decoded_solid = apf_inner._decode_bc3(solid_bc3)  # type: ignore[attr-defined]
    if any(tuple(pixel) != SOLID_RGBA for pixel in decoded_solid):
        raise FamilyLayoutError("controlled BC3 solid block is not lossless")

    jerseys: list[dict[str, object]] = []
    reference_descriptor: dict[str, object] | None = None
    reference_layout: list[dict[str, object]] | None = None
    with apf_inner.ArchiveReader(archive) as reader:
        for asset_index in range(JERSEY_COUNT):
            outer_name = f"uniform_jersey_{asset_index:02d}.iff"
            name_id = _outer_name_id(outer_name)
            entry = entries_by_name_id.get(name_id)
            if entry is None:
                raise FamilyLayoutError(
                    f"missing {outer_name} ({_hex(name_id)})"
                )
            jersey, descriptor, layout = _analyze_jersey(
                reader,
                entry,
                asset_index,
                outer_name,
                solid_bc3,
                reference_descriptor,
                reference_layout,
            )
            if reference_descriptor is None:
                reference_descriptor = descriptor
                reference_layout = layout
            jerseys.append(jersey)

    after_stat = index_path.stat()
    source_sha_after = _sha256_file(index_path)
    if (
        source_sha_after != source_sha_before
        or after_stat.st_size != before_stat.st_size
        or after_stat.st_mtime_ns != before_stat.st_mtime_ns
        or after_stat.st_ctime_ns != before_stat.st_ctime_ns
    ):
        raise FamilyLayoutError("source volume changed during read-only analysis")
    assert reference_descriptor is not None and reference_layout is not None

    minimum_original_slack = min(
        int(item["outer_allocation"]["slack_before"])  # type: ignore[index]
        for item in jerseys
    )
    minimum_solid_slack = min(
        int(item["controlled_solid_rebuild_in_memory"]["iff"]["allocation_slack_after"])  # type: ignore[index]
        for item in jerseys
    )
    report: dict[str, object] = {
        "schema": SCHEMA,
        "scope": {
            "game": "All-Pro Football 2K8 (USA)",
            "family": "uniform_jersey",
            "asset_indices": list(range(JERSEY_COUNT)),
            "inner_file_index": INNER_INDEX,
            "inner_name": INNER_NAME,
        },
        "source": {
            "volume": "0A",
            "size": before_stat.st_size,
            "sha256_before": source_sha_before,
            "sha256_after": source_sha_after,
            "size_mtime_ctime_unchanged": True,
            "opened_for_write": False,
            "copied_volume_used": False,
        },
        "implementation": {
            "dependency_hashes": _dependency_hashes(),
            "xenos_layout_reference": {
                "upstream": "Xenia",
                "commit": xenos_mips.XENIA_COMMIT,
                "derivation_module": "tools/apf_xenos_mip_layout.py",
            },
            "archive_rebuild_helper": "tools/apf_uniform_mip_patch.py::_rebuild_entry",
            "controlled_rebuild_storage": "RAM only",
        },
        "family_equivalence": {
            "package_count": len(jerseys),
            "all_24_names_resolved_by_outer_crc": True,
            "all_complete_txtr_descriptors_identical": True,
            "all_iff_structures_two_blocks_one_file": True,
            "all_blocks_h7a_shift_8": True,
            "all_nine_level_layouts_identical": True,
            "all_retail_transports_bit_exact": True,
            "all_controlled_solid_rebuilds_fit_fixed_allocations": True,
            "minimum_original_allocation_slack": minimum_original_slack,
            "minimum_controlled_solid_allocation_slack": minimum_solid_slack,
            "canonical_txtr_descriptor": reference_descriptor,
            "canonical_nine_level_layout": reference_layout,
        },
        "controlled_fixture": {
            "description": "opaque magenta, encoded once as one deterministic BC3 block",
            "rgba": list(SOLID_RGBA),
            "bc3_block_sha256": _sha256(solid_bc3),
            "bc3_block_decode_exact": True,
            "contains_retail_pixels": False,
            "contains_replacement_entry_bytes": False,
        },
        "jerseys": jerseys,
        "claim_boundary": {
            "structural_layout_generalizes_across_all_24_jerseys": True,
            "in_memory_transport_and_fixed_allocation_rebuild_proved_for_all_24": True,
            "general_writer_complete": False,
            "runtime_visibility_proved": False,
            "xenia_rendering_proved": False,
            "xbox_360_hardware_rendering_proved": False,
            "production_quality_bc3_encoder_proved": False,
            "retail_or_copied_game_volume_written": False,
        },
        "portme": [
            "Expose additional jersey targets only after adding per-entry retail hash pins and safe copy-only CLI gates.",
            "Capture representative changed jerseys from every selector bank in Xenia and on Xbox 360 hardware before claiming runtime visibility.",
            "Replace the deterministic BC3 proof backend with a vetted production-quality perceptual encoder.",
        ],
    }
    return report, _tsv(jerseys)


def _tsv(jerseys: list[dict[str, object]]) -> str:
    columns = [
        "asset_index",
        "outer_name",
        "outer_name_id",
        "outer_table_index",
        "pack_name",
        "pack_offset",
        "allocation_size",
        "allocation_sha256",
        "iff_header_size",
        "iff_file_length",
        "iff_active_length",
        "original_slack",
        "block_count",
        "file_count",
        "block0_h7a_shift",
        "block1_h7a_shift",
        "dram_sha256",
        "texture_sha256",
        "inner_file_sha256",
        "width",
        "height",
        "format_name",
        "endianness_name",
        "base_length",
        "mip_length",
        "mip_levels",
        "packed_tail_levels",
        "packed_tail_origins_blocks",
        "retail_transport_bit_exact",
        "controlled_rebuilt_entry_sha256",
        "controlled_slack_after",
        "controlled_h7a_roundtrip_exact",
        "controlled_transport_bit_exact",
        "entry_or_volume_written",
    ]
    rows = ["\t".join(columns)]
    for item in jerseys:
        physical = item["physical"]
        allocation = item["outer_allocation"]
        iff = item["iff"]
        blocks = iff["blocks"]
        inner = item["inner_file"]
        descriptor = item["txtr_descriptor"]
        transport = item["transport"]
        controlled = item["controlled_solid_rebuild_in_memory"]
        values: dict[str, object] = {
            "asset_index": item["asset_index"],
            "outer_name": item["outer_name"],
            "outer_name_id": item["outer_name_id"],
            "outer_table_index": item["outer_table_index"],
            "pack_name": physical["pack_name"],
            "pack_offset": f"0x{int(physical['pack_offset']):08x}",
            "allocation_size": allocation["size"],
            "allocation_sha256": allocation["sha256"],
            "iff_header_size": iff["header_size"],
            "iff_file_length": iff["file_length_excluding_footer"],
            "iff_active_length": allocation["active_length"],
            "original_slack": allocation["slack_before"],
            "block_count": iff["block_count"],
            "file_count": iff["file_count"],
            "block0_h7a_shift": blocks[0]["h7a"]["shift"],
            "block1_h7a_shift": blocks[1]["h7a"]["shift"],
            "dram_sha256": inner["dram_sha256"],
            "texture_sha256": inner["texture_sha256"],
            "inner_file_sha256": inner["concatenated_parts_sha256"],
            "width": descriptor["width"],
            "height": descriptor["height"],
            "format_name": descriptor["format_name"],
            "endianness_name": descriptor["endianness_name"],
            "base_length": descriptor["vc_base_data_length"],
            "mip_length": descriptor["vc_mip_data_length"],
            "mip_levels": "0-8",
            "packed_tail_levels": ",".join(
                str(value) for value in transport["packed_tail_levels"]
            ),
            "packed_tail_origins_blocks": ";".join(
                f"{origin[0]},{origin[1]}"
                for origin in transport["packed_tail_origins_blocks"]
            ),
            "retail_transport_bit_exact": str(
                transport["retail_extract_reinsert_bit_exact"]
            ).lower(),
            "controlled_rebuilt_entry_sha256": controlled[
                "rebuilt_entry_sha256"
            ],
            "controlled_slack_after": controlled["iff"][
                "allocation_slack_after"
            ],
            "controlled_h7a_roundtrip_exact": str(
                controlled["iff"]["h7a_decode_encode_decode_exact"]
            ).lower(),
            "controlled_transport_bit_exact": str(
                controlled["transport_bit_exact"]
            ).lower(),
            "entry_or_volume_written": str(
                controlled["entry_or_volume_written"]
            ).lower(),
        }
        rows.append("\t".join(str(values[column]) for column in columns))
    return "\n".join(rows) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="retail APF 0A")
    parser.add_argument("--report", required=True, type=Path, help="JSON output")
    parser.add_argument("--tsv", required=True, type=Path, help="TSV output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        source = args.index.expanduser().resolve()
        for output in (args.report, args.tsv):
            if output.expanduser().resolve() == source:
                raise FamilyLayoutError("output path may not be the source volume")
        report, tsv = analyze(source)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        args.tsv.write_text(tsv, encoding="utf-8")
        print(
            "APF_JERSEY_FAMILY_LAYOUT_PASS "
            f"packages={len(report['jerseys'])} levels=9 "
            f"min_original_slack={report['family_equivalence']['minimum_original_allocation_slack']} "
            f"min_solid_slack={report['family_equivalence']['minimum_controlled_solid_allocation_slack']}"
        )
        return 0
    except (
        FamilyLayoutError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        archive_patch.PatchError,
        uniform_patch.UniformPatchError,
        xenos_mips.MipLayoutError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
