#!/usr/bin/env python3
"""Strict drift validator for the APF uniform texture format specification.

The specification is deliberately a checked-in data artifact.  This validator
does not regenerate it or trust it as its own oracle: source report identities
are hard-pinned here, family facts are independently projected from those
reports, and transport/container constants are checked against a second set of
literal invariants.  Any disagreement is a hard failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
V1_SPEC = ROOT / "reports/specs/apf2k8_uniform_texture_formats.v1.json"
V2_SPEC = ROOT / "reports/specs/apf2k8_uniform_texture_formats.v2.json"
DEFAULT_SPEC = V2_SPEC
V1_SPEC_SIZE = 53829
V1_SPEC_SHA256 = "80acb6f48408b59d305b3cfac3cfe8b61104bcd189c1fda9ff28e17df7b1c218"


class SpecError(ValueError):
    """Raised when the checked-in format specification or evidence drifts."""


SOURCE_PINS_V1 = {
    "jersey_layout": (
        "reports/assets/apf_jersey_family_layout.json",
        366327,
        "b60783b9c47b57e9b9f545e95f5c17d3c850e263e0d7d453aa6c3be4a0f809e4",
        "apf_jersey_family_layout/v1",
    ),
    "pants_layout": (
        "reports/assets/apf_pants_family_layout.json",
        274895,
        "707d916213f04499608b492ce2ea37a0e33b770af0f69c57248755d71ef5c32a",
        "apf_pants_family_layout/v1",
    ),
    "helmet_layout": (
        "reports/assets/apf_helmet_family_layout.json",
        280392,
        "29c3f097f63105f0ae2067d8f99f0ce8666e447d8bf13de4b1cb071e9638ed4c",
        "apf_helmet_family_layout/v1",
    ),
    "jersey_roundtrip": (
        "reports/assets/apf_jersey_family_patch_roundtrip.json",
        5198,
        "1273cb27f9869affa3fd4fb69b6ee2b3a3282dafc9e55e918159b6620ff4834a",
        "apf_jersey_family_patch_roundtrip/v1",
    ),
    "pants_roundtrip": (
        "reports/assets/apf_pants_family_patch_roundtrip.json",
        4568,
        "57faf1c600a306d50c298dc6810640fe886078c789ea0d174df740e9b7b29d08",
        "apf_pants_family_patch_roundtrip/v1",
    ),
    "helmet_roundtrip": (
        "reports/assets/apf_helmet_family_patch_roundtrip.json",
        5224,
        "f85e37695b3b118f2a555e260dbfb6f207165677b68741a5b4c099fad811eb5c",
        "apf_helmet_family_patch_roundtrip/v1",
    ),
    "selector_sharing": (
        "reports/assets/uniform_texture_sharing.json",
        414887,
        "4c6557f8e9732267a078ecf42f2d8e8696d7207c9ed6aacd9a76a3e1c67c9910",
        "uniform_texture_sharing_audit/v1",
    ),
    "uniform_inventory": (
        "reports/assets/apf_uniform_inventory.json",
        4350600,
        "b3ad0e44af0163b30857e20c7c4e90ceb89cbc3dbc8cc41508fce3aaf1c136c7",
        "apf_uniform_inventory/v1",
    ),
    "jersey_xenia_runtime": (
        "reports/assets/apf_uniform_xenia_runtime.json",
        9287,
        "0eabe929101c08d7e83b36ed6ef12e61e18703d3d7bbdb6808650a1181d021bf",
        "apf_uniform_xenia_runtime/v1",
    ),
}

SOURCE_PINS_V2 = {
    **SOURCE_PINS_V1,
    "shoulder_layout": (
        "reports/assets/apf_shoulder_family_layout.json",
        345091,
        "6899b356c6364fb6f315dcb7ef599572ca1cb5771735a5540fcc70ef202456b8",
        "apf_shoulder_family_layout/v1",
    ),
    "shoulder_layout_tsv": (
        "reports/assets/apf_shoulder_family_layout.tsv",
        7226,
        "b95a5342d4b7dd92ad3624aa62f811c743066c5b195d89db33387a7b2bc47dec",
        "apf_shoulder_family_layout_tsv/v1",
    ),
    "shoulder_roundtrip": (
        "reports/assets/apf_shoulder_family_patch_roundtrip.json",
        5059,
        "b471dc33cb9f30be45dfbf057219e6f3b8dff9b5be969ef3e66602c229cef2ef",
        "apf_shoulder_family_patch_roundtrip/v1",
    ),
}


PER_SLOT_FIELDS = [
    "asset_index",
    "outer_name",
    "outer_name_id",
    "outer_table_index",
    "pack_name",
    "pack_offset_bytes",
    "fixed_allocation_bytes",
    "retail_entry_sha256",
    "h7a_shift_profile",
]

MIP_FIELDS = [
    "level",
    "width",
    "height",
    "data_offset_bytes",
    "allocation_length_bytes",
    "pitch_blocks",
    "origin_block_x",
    "origin_block_y",
    "packed_tail",
    "logical_block_count",
]


CONTAINER_INVARIANTS = {
    "outer_archive_format": {
        "byte_order": "big-endian",
        "magic_u32": "0xaa00b3bf",
        "fixed_header_bytes": 24,
        "alignment_bytes": 2048,
        "pack_descriptor_bytes": 16,
        "entry_record_bytes": 12,
        "entry_record_fields": ["name_id_u32be", "offset_blocks_u32be", "size_blocks_u32be"],
        "pack_descriptor_fields": ["size_blocks_u32be", "reserved_zero_u32be", "name_utf16be_8_bytes"],
        "entry_offset_rule": "virtual_offset_bytes = offset_blocks * alignment_bytes",
        "entry_size_rule": "fixed_allocation_bytes = size_blocks * alignment_bytes",
        "name_id_rule": "CRC32(uppercase ASCII exact filename)",
        "selected_families_are_single_segment_in_pack_0A": True,
    },
    "iff_format": {
        "byte_order": "big-endian except name-footer payload",
        "magic_u32": "0xff3bef94",
        "fixed_header_bytes": 32,
        "block_descriptor_bytes": 32,
        "header_fields": [
            [0, "magic_u32be"], [4, "header_size_u32be"],
            [8, "file_length_excluding_footer_u32be"], [12, "zero_u32be"],
            [16, "block_count_u32be"], [20, "block_table_relptr_u32be"],
            [24, "file_count_u32be"], [28, "file_pointer_table_relptr_u32be"],
        ],
        "relative_pointer_rule": "target = pointer_field_offset + stored_u32be - 1",
        "block_descriptor_fields": [
            [0, "name_hash_u32be"], [4, "type_hash_u32be"],
            [8, "alignment_or_flags_u32be_semantics_unknown"],
            [12, "uncompressed_length_u32be"], [16, "codec_field_u32be"],
            [20, "start_offset_u32be"], [24, "stored_length_u32be"],
            [28, "indexed_u32be"],
        ],
        "file_descriptor_fields": [
            "file_id_u32be", "type_hash_u32be", "offset_count_u32be",
            "one_decompressed_block_offset_u32be_per_present_part",
        ],
        "absent_part_sentinel_u32": "0xffffffff",
        "footer": {
            "magic_u32be": "0xaa171516",
            "payload_size_u32le_at_footer_plus_4": True,
            "payload_pointer_byte_order": "little-endian",
            "names_encoding": "UTF-16LE NUL-terminated",
            "pointer_rule": "target = pointer_field_offset + stored_u32le - 1",
            "must_remain_bit_exact_on_write": True,
        },
    },
    "h7a_format": {
        "byte_order": "big-endian header and big-endian 16-bit match words",
        "magic_u32": "0x0e4837c3",
        "header_bytes": 20,
        "header_fields": [
            [0, "magic_u32be"], [4, "uncompressed_length_u32be"],
            [8, "stored_length_including_header_u32be"], [12, "codec_field_u32be"],
            [16, "window_shift_u32be"],
        ],
        "flag_order": "one descriptor byte, least-significant bit first, up to 8 tokens",
        "literal_flag": 0,
        "match_flag": 1,
        "match_distance_rule": "distance = match_word & ((1 << shift) - 1)",
        "match_length_rule": "length = ((match_word >> shift) & ((1 << (16 - shift)) - 1)) + 3",
        "distance_bounds": "1 <= distance <= bytes_already_decoded",
        "output_rule": "decode exactly declared uncompressed length; reject overrun, underrun, or nonzero trailing compressed bytes",
        "rebuild_rule": "preserve each retail block shift and codec field; require encode-decode exact before IFF rebuild",
    },
    "txtr_format": {
        "dram_descriptor_bytes": 224,
        "byte_order": "big-endian descriptor dwords",
        "fields": [
            [0, "file_id_u32be"], [96, "declared_width_u16be"],
            [98, "declared_height_u16be"], [112, "base_data_length_u32be"],
            [116, "mip_data_length_u32be"], [148, "xenos_texture_fetch_6xu32be"],
        ],
        "fetch_decode": {
            "type": "dword0 bits 0..1",
            "pitch_pixels": "((dword0 >> 22) & 0x1ff) << 5",
            "tiled": "dword0 bit 31",
            "format": "dword1 bits 0..5",
            "endianness": "dword1 bits 6..7",
            "stacked": "dword1 bit 10",
            "base_address_pages": "dword1 >> 12",
            "width": "(dword2 & 0x1fff) + 1",
            "height": "((dword2 >> 13) & 0x1fff) + 1",
            "swizzle": "(dword3 >> 1) & 0xfff",
            "mip_min_level": "(dword4 >> 2) & 0xf",
            "mip_max_level": "(dword4 >> 6) & 0xf",
            "dimension": "(dword5 >> 9) & 0x3",
            "packed_mips": "dword5 bit 11",
            "mip_address_pages": "dword5 >> 12",
        },
    },
    "xenos_transport": {
        "reference": {"project": "Xenia", "commit": "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"},
        "block_geometry_pixels": [4, 4],
        "storage_pitch_alignment_blocks": 32,
        "operation_order_encode": [
            "encode logical row-major 4x4 blocks",
            "swap bytes within each 16-bit word for endianness mode 1",
            "place each block at xenos_tiled_2d_offset",
        ],
        "operation_order_decode": [
            "read each block from xenos_tiled_2d_offset",
            "swap bytes within each 16-bit word for endianness mode 1",
            "decode logical row-major blocks",
        ],
        "tiled_2d_formula": {
            "inputs": ["x_block", "y_block", "pitch_blocks_aligned_32", "bytes_per_block_log2"],
            "outer_blocks": "(((y >> 5) * (pitch >> 5)) + (x >> 5)) << 6",
            "inner_blocks": "(((y >> 1) & 7) << 3) | (x & 7)",
            "outer_inner_bytes": "(outer_blocks | inner_blocks) << bytes_per_block_log2",
            "bank": "(y >> 4) & 1",
            "pipe": "((x >> 3) & 3) ^ (((y >> 3) & 1) << 1)",
            "byte_offset": "((y & 1) << 4) | (pipe << 6) | (bank << 11) | (outer_inner_bytes & 0xf) | (((outer_inner_bytes >> 4) & 1) << 5) | (((outer_inner_bytes >> 5) & 7) << 8) | ((outer_inner_bytes >> 8) << 12)",
        },
        "packed_tail_origin_rule": "Xenia GetPackedTileOffset; origins in 4x4 compression blocks",
        "endianness_mode_1": "8-in-16: reverse each two-byte unit; operation is self-inverse",
    },
}


FAMILY_STATIC = {
    "jersey_color": {
        "report_pin": "jersey_layout",
        "roundtrip_pin": "jersey_roundtrip",
        "report_rows": "jerseys",
        "layout_key": "canonical_nine_level_layout",
        "inner": [0, "jersey_color", "0x1ff6ec38"],
        "iff": {
            "header_size_bytes": 120, "block_count": 2, "file_count": 1,
            "block_uncompressed_lengths": [224, 1441792],
            "block_name_type_hashes": [["0xbb05a9c1", "0xbb05a9c1"], ["0x411536d5", "0x411536d5"]],
            "footer_payload_bytes": 140, "footer_total_bytes": 148, "footer_name_count": 1,
        },
        "target_parts": [[0, 0, 0, 224], [1, 1, 0, 1441792]],
        "related_exact": ["entire DRAM descriptor part", "inactive tiled and packed-tail bytes", "name footer", "outer allocation slack", "all bytes outside selected outer allocation"],
        "png": {"format": "PNG", "width": 1024, "height": 1024, "mode": "RGBA", "max_file_bytes": 67108864, "alpha_rule": "stored RGBA accepted", "channel_rule": "RGBA supplies BC3 color and alpha", "mip_filter": "Pillow BOX"},
        "codec": {"xenos_format": 20, "xenos_format_name": "DXT4_5", "logical_codec": "BC3/DXT5", "bytes_per_block": 16, "stored_channels": "RGBA", "production_encoder_proved": False},
        "selector_slot": 4,
    },
    "pants_color": {
        "report_pin": "pants_layout",
        "roundtrip_pin": "pants_roundtrip",
        "report_rows": "pants",
        "layout_key": "canonical_eight_level_layout",
        "inner": [2, "pants_color", "0x9717866d"],
        "iff": {
            "header_size_bytes": 192, "block_count": 2, "file_count": 4,
            "block_uncompressed_lengths": [896, 1376256],
            "block_name_type_hashes": [["0xbb05a9c1", "0xbb05a9c1"], ["0x411536d5", "0x411536d5"]],
            "footer_payload_bytes": 572, "footer_total_bytes": 580, "footer_name_count": 4,
        },
        "target_parts": [[0, 0, 0, 224], [1, 1, 0, 196608]],
        "related_exact": ["all four DRAM descriptor parts", "pants_light_normal VRAM", "pants_medium_normal VRAM", "pants_heavy_normal VRAM", "inactive tiled and packed-tail bytes", "name footer", "outer allocation slack", "all bytes outside selected outer allocation"],
        "png": {"format": "PNG", "width": 512, "height": 512, "mode": "RGBA", "max_file_bytes": 67108864, "alpha_rule": "every alpha byte must equal 255", "channel_rule": "RGB encoded as opaque four-color BC1; transparency rejected", "mip_filter": "Pillow BOX"},
        "codec": {"xenos_format": 18, "xenos_format_name": "DXT1", "logical_codec": "BC1 opaque four-color mode", "bytes_per_block": 8, "stored_channels": "RGB565 endpoints plus 2-bit indices", "production_encoder_proved": False},
        "selector_slot": 9,
    },
    "helmet_color": {
        "report_pin": "helmet_layout",
        "roundtrip_pin": "helmet_roundtrip",
        "report_rows": "helmets",
        "layout_key": "canonical_seven_level_layout",
        "inner": [0, "helmet_color", "0xcf7f3bdf"],
        "iff": {
            "header_size_bytes": 144, "block_count": 2, "file_count": 2,
            "block_uncompressed_lengths": [448, 1835008],
            "block_name_type_hashes": [["0xbb05a9c1", "0xbb05a9c1"], ["0x411536d5", "0x411536d5"]],
            "footer_payload_bytes": 274, "footer_total_bytes": 282, "footer_name_count": 2,
        },
        "target_parts": [[0, 0, 0, 224], [1, 1, 0, 393216]],
        "related_exact": ["both DRAM descriptor parts", "helmet_normal VRAM bytes 0x60000..0x1bffff", "inactive tiled and packed-tail bytes", "name footer", "outer allocation slack", "all bytes outside selected outer allocation"],
        "png": {"format": "PNG", "width": 256, "height": 1024, "mode": "RGBA", "max_file_bytes": 67108864, "alpha_rule": "every alpha byte must equal 255", "channel_rule": "R and G are raw DXN channels; every B byte must be 0; shader meanings unknown", "mip_filter": "Pillow BOX"},
        "codec": {"xenos_format": 49, "xenos_format_name": "DXN", "logical_codec": "BC5: two independent BC4 channels", "bytes_per_block": 16, "stored_channels": "raw R and G data channels", "production_encoder_proved": False},
        "selector_slot": 3,
    },
    "shoulder_color": {
        "report_pin": "shoulder_layout",
        "roundtrip_pin": "shoulder_roundtrip",
        "report_rows": "shoulders",
        "layout_key": "canonical_nine_level_layout",
        "inner": [3, "shoulder_color", "0xb2f2b5ff"],
        "iff": {
            "header_size_bytes": 192, "block_count": 2, "file_count": 4,
            "block_uncompressed_lengths": [896, 4358144],
            "block_name_type_hashes": [["0xbb05a9c1", "0xbb05a9c1"], ["0x411536d5", "0x411536d5"]],
            "footer_payload_bytes": 572, "footer_total_bytes": 580, "footer_name_count": 4,
            "h7a_window_shift_profiles": {"9,9": list(range(24))},
            "h7a_codec_field_profiles": {
                "7,7": [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 21, 22],
                "7,8": [6, 17, 23],
            },
        },
        "target_parts": [[0, 0, 0, 224], [1, 1, 0, 1441792]],
        "related_exact": ["all four DRAM descriptor parts", "jersey_regionmap VRAM", "sideline_player_l0 VRAM", "sideline_player_l1 VRAM", "entire paired uniform_shoulder_normal asset-index package", "inactive tiled and packed-tail bytes", "name footer", "outer allocation slack", "all bytes outside selected outer allocation"],
        "png": {"format": "PNG", "width": 1024, "height": 1024, "mode": "RGBA", "max_file_bytes": 67108864, "alpha_rule": "stored RGBA accepted", "channel_rule": "RGBA supplies BC3 color and alpha", "mip_filter": "Pillow BOX"},
        "codec": {"xenos_format": 20, "xenos_format_name": "DXT4_5", "logical_codec": "BC3/DXT5", "bytes_per_block": 16, "stored_channels": "RGBA", "production_encoder_proved": False},
        "selector_slot": 11,
    },
}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SpecError(f"top level is not an object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SpecError(message)


def _equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise SpecError(f"{label} drifted: {actual!r} != {expected!r}")


def _source_reports(
    spec: dict[str, Any], source_pins: dict[str, tuple[str, int, str, str]]
) -> dict[str, dict[str, Any]]:
    expected_rows = [
        {"id": key, "path": path, "size": size, "sha256": digest, "schema": schema}
        for key, (path, size, digest, schema) in source_pins.items()
    ]
    _equal(spec.get("source_pins"), expected_rows, "source_pins")
    reports: dict[str, dict[str, Any]] = {}
    for key, (relative, size, digest, schema) in source_pins.items():
        path = ROOT / relative
        _require(path.is_file() and not path.is_symlink(), f"source report is missing or symlinked: {relative}")
        _equal(path.stat().st_size, size, f"{key} size")
        _equal(_sha256(path), digest, f"{key} sha256")
        if path.suffix == ".json":
            report = _load(path)
            _equal(report.get("schema"), schema, f"{key} schema")
        else:
            report = {}
        reports[key] = report
    return reports


def _slot_rows(report: dict[str, Any], rows_key: str) -> list[list[Any]]:
    result = []
    for row in report[rows_key]:
        shifts = row["iff"].get("h7a_shift_profile") or [
            block.get("h7a", {}).get("shift", block.get("h7a_shift"))
            for block in row["iff"]["blocks"]
        ]
        result.append([
            row["asset_index"], row["outer_name"], row["outer_name_id"],
            row["outer_table_index"], row["physical"]["pack_name"],
            row["physical"]["pack_offset"], row["outer_allocation"]["size"],
            row["outer_allocation"]["sha256"], shifts,
        ])
    return result


def _paired_normal_rows(report: dict[str, Any]) -> list[list[Any]]:
    return [[
        row["asset_index"], row["paired_normal_package"]["outer_name"],
        row["paired_normal_package"]["outer_name_id"],
        row["paired_normal_package"]["outer_table_index"],
        row["paired_normal_package"]["allocation_size"],
        row["paired_normal_package"]["allocation_sha256"],
    ] for row in report["shoulders"]]


def _preserved_sibling_map(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "index": sibling["index"],
        "name": sibling["name"],
        "parts": [[
            part["part_index"], part["block_index"], part["offset"], part["length"]
        ] for part in sibling["parts"]],
    } for sibling in row["preserved_sibling_files"]]


def _mip_rows(report: dict[str, Any], layout_key: str) -> list[list[Any]]:
    return [[
        row["level"], row["width"], row["height"], row["data_offset"],
        row["allocation_length"], row["pitch_blocks"], row["origin_block_x"],
        row["origin_block_y"], row["packed_tail"], row["logical_block_count"],
    ] for row in report["family_equivalence"][layout_key]]


def _sharing_for(key: str, reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if key == "jersey_color":
        apf = reports["selector_sharing"]["apf2k8"]
        counts = [row["selector_owner_count"] for row in apf["assets"]]
        used = apf["used_asset_indices"]
        unused = apf["unreferenced_asset_indices"]
    else:
        source = reports[FAMILY_STATIC[key]["report_pin"]]["selector_sharing"]
        counts = [source["asset_use_counts"][str(index)] for index in range(24)]
        used = source["used_asset_indices"]
        unused = source["unused_asset_indices"]
    result = {
        "selector_slot": FAMILY_STATIC[key]["selector_slot"],
        "asset_index_byte_in_selector_record": 0,
        "selector_record_bytes": 8,
        "team_count": 40,
        "banks_per_team": 2,
        "team_bank_use_count": 80,
        "asset_use_counts_by_asset_index": counts,
        "used_asset_indices": used,
        "unused_asset_indices": unused,
        "editing_asset_affects_all_listed_owners": True,
        "selector_writer_proved": False,
    }
    if key == "shoulder_color":
        result.update({
            "selected_families": ["shoulder", "shoulder_normal"],
            "one_asset_index_selects_both_paired_packages": True,
        })
    return result


def _validate_family(key: str, family: dict[str, Any], reports: dict[str, dict[str, Any]]) -> None:
    static = FAMILY_STATIC[key]
    expected_keys = {
        "family", "asset_index_range", "outer_name_template", "inner_file",
        "iff_instance", "target_parts", "related_resources_must_remain_exact",
        "txtr_descriptor", "codec", "png_input_contract", "mip_layout",
        "selector_sharing", "per_slot_fixed_allocations", "write_contract",
        "claim_flags", "known_unknowns",
    }
    if key == "shoulder_color":
        expected_keys.update({
            "preserved_sibling_files", "paired_normal_allocation_fields",
            "paired_normal_fixed_allocations", "controlled_fit_proof",
        })
    _equal(set(family), expected_keys, f"{key} keys")
    report = reports[static["report_pin"]]
    rows = report[static["report_rows"]]
    _equal(family["family"], report["scope"]["family"], f"{key} family")
    _equal(family["asset_index_range"], [0, 23], f"{key} asset range")
    _equal(family["outer_name_template"], f"uniform_{key.removesuffix('_color')}_{{asset_index:02d}}.iff", f"{key} template")
    _equal(family["inner_file"], {"index": static["inner"][0], "name": static["inner"][1], "type": "TXTR", "file_id": static["inner"][2]}, f"{key} inner file")
    _equal(family["iff_instance"], static["iff"], f"{key} IFF instance")
    _equal(family["target_parts"], static["target_parts"], f"{key} target parts")
    _equal(family["related_resources_must_remain_exact"], static["related_exact"], f"{key} preservation list")
    descriptor = report["family_equivalence"]["canonical_txtr_descriptor"]
    _equal(family["txtr_descriptor"], descriptor, f"{key} TXTR descriptor")
    _equal(family["codec"], static["codec"], f"{key} codec")
    _equal(family["png_input_contract"], static["png"], f"{key} PNG contract")
    _equal(family["mip_layout"], _mip_rows(report, static["layout_key"]), f"{key} mip layout")
    _equal(family["selector_sharing"], _sharing_for(key, reports), f"{key} selector sharing")
    _equal(family["per_slot_fixed_allocations"], _slot_rows(report, static["report_rows"]), f"{key} per-slot allocation table")
    if key == "shoulder_color":
        _equal(
            family["preserved_sibling_files"],
            _preserved_sibling_map(rows[0]),
            "shoulder preserved sibling part map",
        )
        _equal(
            family["paired_normal_allocation_fields"],
            ["asset_index", "outer_name", "outer_name_id", "outer_table_index", "fixed_allocation_bytes", "retail_entry_sha256"],
            "shoulder paired-normal field schema",
        )
        _equal(
            family["paired_normal_fixed_allocations"],
            _paired_normal_rows(report),
            "shoulder paired-normal allocation table",
        )
        _equal(family["controlled_fit_proof"], {
            "fixture_rgba": [255, 0, 255, 255],
            "contains_retail_pixels": False,
            "all_24_fixed_allocations_fit_controlled_rebuild": True,
            "minimum_post_rebuild_slack_bytes": report["family_equivalence"]["minimum_controlled_allocation_slack"],
            "minimum_slack_asset_index": 20,
            "copied_volume_asset_index": 23,
            "arbitrary_png_fit_guaranteed": False,
        }, "shoulder controlled-fit proof")

    _equal(len(rows), 24, f"{key} report member count")
    _equal([row["asset_index"] for row in rows], list(range(24)), f"{key} report indices")
    for row in rows:
        _equal(row["iff"]["header_size"], static["iff"]["header_size_bytes"], f"{key} slot header size")
        _equal(row["iff"]["block_count"], static["iff"]["block_count"], f"{key} slot block count")
        _equal(row["iff"]["file_count"], static["iff"]["file_count"], f"{key} slot file count")
        _equal([block["uncompressed_length"] for block in row["iff"]["blocks"]], static["iff"]["block_uncompressed_lengths"], f"{key} slot block spans")
        _equal(row["inner_file"]["index"], static["inner"][0], f"{key} inner index")
        _equal(row["inner_file"]["name"], static["inner"][1], f"{key} inner name")
        _equal([[part["part_index"], part["block_index"], part["offset"], part["length"]] for part in row["inner_file"]["parts"]], static["target_parts"], f"{key} part map")
        _require(row["outer_allocation"]["size"] % 2048 == 0, f"{key} slot allocation lost 0x800 alignment")
        _require(row["physical"]["pack_name"] == "0A", f"{key} slot left pack 0A")
        if key == "shoulder_color":
            _equal(row["iff"]["h7a_shift_profile"], [9, 9], "shoulder H7A shifts")
            _equal(_preserved_sibling_map(row), family["preserved_sibling_files"], "shoulder sibling part-layout equivalence")
            _require(row["paired_normal_package"]["same_selector_slot_and_asset_index"], "shoulder paired selector binding lost")
            _require(row["paired_normal_package"]["physically_separate_from_color_package"], "shoulder paired normal is no longer separate")

    write_contract = family["write_contract"]
    _equal(set(write_contract), {
        "source_opened_read_only", "output_must_not_exist", "source_output_alias_rejected",
        "all_mips_regenerated", "inactive_bytes_preserved", "h7a_encode_decode_exact",
        "rebuilt_iff_reparsed", "footer_preserved_bit_exact", "related_parts_preserved_bit_exact",
        "fixed_allocation_overflow_rejected", "bytes_outside_selected_allocation_preserved",
        "independent_verifier_rederives_png_mips_and_archive_diff",
    }, f"{key} write-contract keys")
    _require(all(value is True for value in write_contract.values()), f"{key} write contract must be all true")

    claims = family["claim_flags"]
    _require(claims["format_closed_for_declared_24_slot_family"], f"{key} format closure lost")
    _require(claims["read_write_byte_roundtrip_proved_all_24"], f"{key} roundtrip claim lost")
    _require(claims["copied_volume_write_proved"], f"{key} copied-volume claim lost")
    _require(not claims["arbitrary_png_guaranteed_to_fit"], f"{key} cannot guarantee arbitrary PNG fit")
    _require(not claims["xbox_360_hardware_proved"], f"{key} hardware claim must remain false")
    _require(not claims["production_encoder_proved"], f"{key} production encoder claim must remain false")
    if key == "jersey_color":
        runtime = reports["jersey_xenia_runtime"]["outcome"]
        _require(runtime["target_binding_proved"] and runtime["solid_color_runtime_visibility_proved"], "jersey runtime evidence lost")
        _equal(claims["xenia_runtime_visibility"], {"proved_for_asset_indices": [6], "solid_color_target_binding_only": True, "generalized_all_24": False}, "jersey runtime claim")
    else:
        _equal(claims["xenia_runtime_visibility"], {"proved_for_asset_indices": [], "generalized_all_24": False}, f"{key} runtime claim")
    if key == "shoulder_color":
        roundtrip = reports["shoulder_roundtrip"]
        equivalence = report["family_equivalence"]
        _require(equivalence["paired_normal_package_count"] == 24, "shoulder paired-normal catalog changed")
        _require(equivalence["all_three_sibling_textures_preserved"], "shoulder all-24 sibling preservation lost")
        _require(equivalence["all_controlled_solid_rebuilds_fit_fixed_allocations"], "shoulder all-24 controlled fit lost")
        _require(roundtrip["conclusion"]["all_three_sibling_textures_preserved"], "shoulder sibling roundtrip claim lost")
        _require(roundtrip["conclusion"]["paired_normal_package_preserved"], "shoulder paired-normal preservation claim lost")
        _require(claims["three_sibling_textures_preserved_all_24"], "shoulder sibling claim missing")
        _require(claims["paired_normal_packages_preserved_all_24"], "shoulder paired-normal claim missing")
    _require(isinstance(family["known_unknowns"], list) and family["known_unknowns"], f"{key} known unknowns missing")


def validate(spec_path: Path = DEFAULT_SPEC) -> dict[str, Any]:
    spec = _load(spec_path)
    expected_top = {
        "schema", "title", "scope", "contains_retail_pixels", "source_pins",
        "outer_archive_format", "iff_format", "h7a_format", "txtr_format",
        "xenos_transport", "fixed_allocation_safety", "per_slot_allocation_fields",
        "mip_layout_fields", "families", "global_known_unknowns",
    }
    _equal(set(spec), expected_top, "top-level keys")
    schema = spec.get("schema")
    if schema == "apf2k8_uniform_texture_formats/v1":
        version = 1
        source_pins = SOURCE_PINS_V1
        family_keys = ["jersey_color", "pants_color", "helmet_color"]
    elif schema == "apf2k8_uniform_texture_formats/v2":
        version = 2
        source_pins = SOURCE_PINS_V2
        family_keys = ["jersey_color", "pants_color", "helmet_color", "shoulder_color"]
    else:
        raise SpecError(f"unsupported spec schema: {schema!r}")
    _equal(V1_SPEC.stat().st_size, V1_SPEC_SIZE, "immutable v1 size")
    _equal(_sha256(V1_SPEC), V1_SPEC_SHA256, "immutable v1 sha256")
    _equal(spec["contains_retail_pixels"], False, "retail-pixel boundary")
    _equal(spec["per_slot_allocation_fields"], PER_SLOT_FIELDS, "per-slot field schema")
    _equal(spec["mip_layout_fields"], MIP_FIELDS, "mip field schema")
    for key, expected in CONTAINER_INVARIANTS.items():
        _equal(spec[key], expected, key)
    reports = _source_reports(spec, source_pins)
    expected_scope = {
        "game": "All-Pro Football 2K8 (USA Xbox 360)",
        "retail_volume": {"name": "0A", "size": 1140850688, "sha256": "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"},
        "closed_families": family_keys,
        "asset_indices_per_family": 24,
        "spec_boundary": "exact fixed-allocation texture transport; not a general APF TXTR or mesh specification",
    }
    _equal(spec["scope"], expected_scope, "scope")
    _equal(spec["fixed_allocation_safety"], {
        "fail_closed": True,
        "never_grow_or_relocate_outer_entry": True,
        "validate_selected_retail_entry_sha256_before_edit": True,
        "reject_if_rebuilt_iff_plus_footer_exceeds_selected_allocation": True,
        "preserve_zero_slack_to_exact_allocation_length": True,
        "source_volume_never_opened_for_write": True,
        "destination_created_exclusively": True,
        "copied_volume_must_equal_source_outside_selected_allocation": True,
        "independent_verifier_required": True,
    }, "fixed-allocation safety")
    families = spec["families"]
    _equal(set(families), set(family_keys), "family set")
    if version == 2:
        v1 = _load(V1_SPEC)
        for original_family in ("jersey_color", "pants_color", "helmet_color"):
            _equal(
                families[original_family],
                v1["families"][original_family],
                f"v2 additive preservation of {original_family}",
            )
    for key in family_keys:
        _validate_family(key, families[key], reports)
    _require(isinstance(spec["global_known_unknowns"], list) and spec["global_known_unknowns"], "global known unknowns missing")
    serialized = json.dumps(spec, sort_keys=True)
    _require("data:image" not in serialized and "base64," not in serialized, "embedded image payload detected")
    return {"version": version, "families": len(families), "slots": sum(len(item["per_slot_fixed_allocations"]) for item in families.values()), "mips": sum(len(item["mip_layout"]) for item in families.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    args = parser.parse_args()
    try:
        result = validate(args.spec)
    except SpecError as exc:
        parser.error(str(exc))
    print(json.dumps({"schema": "apf2k8_uniform_texture_format_spec_validation/v2", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
