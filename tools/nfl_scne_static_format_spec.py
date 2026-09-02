#!/usr/bin/env python3
"""Generate and strictly validate the NFL 2K5 static SCNE format spec.

This is deliberately serializer-oriented.  The checked-in JSON is generated
from literal format invariants, while this program independently verifies the
current parser constants, pinned corpus reports, and every source identity
before accepting it.  Unknown record bytes remain unknown and preservation is
part of the format contract.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "reports/specs/nfl2k5_xbox_static_scne.v1.json"


class SpecError(ValueError):
    """The specification, its parser constants, or its evidence has drifted."""


SOURCE_PINS = {
    "scne_inventory_parser": (
        "tools/nfl_scne_inventory.py", 50580,
        "0f58222812df6b380588f8b0a2592101136a863cd0dd170b0f32df726de2fc6b",
    ),
    "bulk_static_exporter": (
        "tools/nfl_static_gltf.py", 35165,
        "5249732b635374eb33bcb39f162224bccd2163cf1cfd01b1dfc8db42ac40bea3",
    ),
    "topology_exporter": (
        "tools/nfl_scne_gltf.py", 15043,
        "69f560d9a665a40868f25334f6f90c5713135f9c4ee8321d0abd30bf3c847058",
    ),
    "normshort3_proof_tool": (
        "tools/nfl_normshort3_positions.py", 18060,
        "2423528567e0e9a24bd2e07767ad225ed737e86e87e4c5286eb1f4dbc0af5672",
    ),
    "outer_archive_parser": (
        "tools/nfl_outer.py", 17176,
        "0f27ac4157f13704e4303dbf2e146427cc56d1d910a3e242fac4081a04d9ee6d",
    ),
    "resource_probe": (
        "tools/nfl_scene_probe.py", 40326,
        "31b17ded825d4379b517affece54fc5cd96abea49330017296a10a029216fc26",
    ),
    "resource_wrapper_vc_lz": (
        "tools/nfl_txtr.py", 43341,
        "0896e3f409f38116602d37a8902f1403e8afe6ad9e17e9ee9d36244ae97a5107",
    ),
    "layout_evidence": (
        "docs/research/nfl_scne_layout.md", 11681,
        "215afc7d72de69ac6acc8291f73e53d852c71daedbbc104601e2586e6bbeb934",
    ),
    "static_export_evidence": (
        "docs/research/nfl_static_gltf.md", 6576,
        "7eda23f5bab9c75da9dadca53ce85bfa37ca3d6f188f7c8271142bafebbfc1ba",
    ),
    "normshort3_evidence": (
        "docs/research/nfl_normshort3_positions.md", 5115,
        "6efd91d2e23671f3d0b2058b5b2cec303a2d8d32eceec307cf2102b9a0ad097e",
    ),
    "scne_inventory_report": (
        "reports/assets/nfl2k5_scne_inventory.json", 13756367,
        "8aa5f3d952b2264455280039793ef92a5a382dcec31680b2375bede24b4b2444",
    ),
    "normshort3_report": (
        "reports/assets/nfl_normshort3_positions.json", 10498,
        "50a60ebf8ac8bc6d70a4239356f08851bfa444b224607e1b1dd411e3a7208068",
    ),
    "resource_inventory_report": (
        "reports/assets/nfl2k5_resource_chunks_v2.json", 55746414,
        "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac",
    ),
    "scne_shape_rows": (
        "reports/assets/nfl2k5_scne_shapes.tsv", 20512302,
        "085f2946ddf573c101765d41f2e5ae72876db251d2237e7cb1fd7083b89a7d3e",
    ),
    "group36_position_writer": (
        "tools/nfl_stadium_group36_position_patch.py", 31961,
        "d781d49a8adaa23941e5854f734d531b458d1da70c6725f5ad0f2c7c1f92e82b",
    ),
    "group36_independent_verifier": (
        "tools/nfl_stadium_group36_position_verify.py", 37290,
        "626a54b109f604274311ce14576516a3f6dd3f583a4617f2420c741e76a6c8cc",
    ),
    "group36_recipe_schema": (
        "reports/specs/nfl2k5_static_position_recipe.schema.json", 1381,
        "a43644c1e75addc9f478aad655fa74120aede16406195a37f2cde94fb081cefb",
    ),
    "group36_zero_recipe": (
        "reports/asset_samples/nfl_scne/stadium_group36_zero_recipe.json", 787,
        "ad6b4fd7e658512c54770c66731adeea81e8b08b7731c981a0757b713a356781",
    ),
    "group36_roundtrip": (
        "reports/assets/nfl_stadium_group36_position_patch_roundtrip.json", 7455,
        "45f65c16b4b4d25a30fb63643d3ec1a8f7476a8993e3ca370df33c244cbbef05",
    ),
    "stadium_static_target_catalog": (
        "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json", 858600,
        "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa",
    ),
    "catalog_position_writer": (
        "tools/nfl_stadium_catalog_position_patch.py", 29227,
        "c43dcf39fec5c7bc542fe7c8ebf98abd7ab23491878dcf3b36295a45d6c01885",
    ),
    "catalog_position_independent_verifier": (
        "tools/nfl_stadium_catalog_position_verify.py", 30504,
        "05236caff5f518a8703ef9196621ac5d284f2c8a958e87253abdd700b5896cf1",
    ),
    "catalog_position_recipe_schema": (
        "reports/specs/nfl2k5_catalog_static_position_recipe.v2.schema.json", 1399,
        "6fd2213905d2333650581ace6d5bfd8b5381fe92dc070f2d8ef61179bae39920",
    ),
    "upper_deck_nonretail_zero_recipe": (
        "reports/asset_samples/nfl_scne/stadium_upper_deck_nonretail_zero_recipe.v2.json", 751,
        "f8781df9ebb6af67f47be2024bf7992285423f7aa149a589cef5630e5e9b35a4",
    ),
    "catalog_position_roundtrip": (
        "reports/assets/nfl_stadium_catalog_position_patch_roundtrip.v2.json", 7150,
        "05ab26057b0ebd244a0a090d2268f1cac49b3b820269b410e38c5e6b89a6d9c3",
    ),
}


TABLES = [
    ("aux_14", "unknown auxiliary records", 0x0C, 0x10, 0x14, "0x000252a0"),
    ("textures", "embedded Xbox texture descriptors", 0x14, 0x18, 0x20, "0x00034df0"),
    ("materials", "named material candidates", 0x1C, 0x20, 0x80, "0x000304b0"),
    ("nodes", "named node/reference candidates", 0x24, 0x28, 0x60, "0x00021630"),
    ("shapes", "complex mesh/shape candidates", 0x2C, 0x30, 0x100, "0x00022f90"),
    ("markers", "named marker candidates", 0x34, 0x38, 0x40, "0x00038530"),
    ("aux_60", "unknown records with pointer at +0x00", 0x3C, 0x40, 0x60, None),
    ("aux_50", "unknown records with pointer at +0x40", 0x44, 0x48, 0x50, None),
]


VERTEX_FORMATS = [
    (0x02, "NONE", 0, 0),
    (0x11, "NORMSHORT1", 2, 1),
    (0x12, "FLOAT1", 4, 1),
    (0x14, "PBYTE1", 1, 1),
    (0x15, "SHORT1", 2, 1),
    (0x16, "NORMPACKED3", 4, 3),
    (0x21, "NORMSHORT2", 4, 2),
    (0x22, "FLOAT2", 8, 2),
    (0x24, "PBYTE2", 2, 2),
    (0x25, "SHORT2", 4, 2),
    (0x31, "NORMSHORT3", 6, 3),
    (0x32, "FLOAT3", 12, 3),
    (0x34, "PBYTE3", 3, 3),
    (0x35, "SHORT3", 6, 3),
    (0x40, "D3DCOLOR", 4, 4),
    (0x41, "NORMSHORT4", 8, 4),
    (0x42, "FLOAT4", 16, 4),
    (0x44, "PBYTE4", 4, 4),
    (0x45, "SHORT4", 8, 4),
    (0x72, "FLOAT2H", 12, 4),
]


def field(offset: int, size: int, name: str, encoding: str, status: str,
          meaning: str, writer: str = "preserve") -> dict[str, Any]:
    return {
        "offset": offset,
        "size": size,
        "name": name,
        "encoding": encoding,
        "status": status,
        "meaning": meaning,
        "writer_policy": writer,
    }


def canonical_spec() -> dict[str, Any]:
    """Return the canonical specification without reading the checked-in JSON."""
    source_evidence = {
        key: {"path": path, "size": size, "sha256": digest}
        for key, (path, size, digest) in SOURCE_PINS.items()
    }
    tables = [
        {
            "key": key,
            "semantic": semantic,
            "count_field": {"offset": count, "encoding": "u32le"},
            "pointer_field": {
                "offset": pointer,
                "encoding": "s32le one-based self-relative",
            },
            "record_stride": stride,
            "record_relocator_xbe_va": relocator,
            "writer_policy": "preserve count, pointer, record stride, order, and every unknown byte",
        }
        for key, semantic, count, pointer, stride, relocator in TABLES
    ]
    formats = {
        f"0x{code:02x}": {
            "name": name,
            "byte_size": byte_size,
            "component_count": components,
        }
        for code, name, byte_size, components in VERTEX_FORMATS
    }
    descriptor_fields = sorted(
        [
            field(0x00, 4, "name_pointer", "s32le one-based self-relative", "proved", "duplicate UTF-16LE scene name"),
            field(0x04, 0x08, "unknown_04", "opaque bytes", "unknown", "unassigned descriptor bytes"),
            *[
                field(count, 4, f"{key}_count", "u32le", "proved", semantic)
                for key, semantic, count, _pointer, _stride, _relocator in TABLES
            ],
            *[
                field(pointer, 4, f"{key}_pointer", "s32le one-based self-relative", "proved", f"first 0x{stride:x}-byte record")
                for key, _semantic, _count, pointer, stride, _relocator in TABLES
            ],
            field(0x4C, 0x08, "unknown_4c", "opaque bytes", "unknown", "unassigned descriptor tail"),
        ],
        key=lambda item: int(item["offset"]),
    )
    return {
        "schema": "nfl2k5_xbox_static_scne_format/v1",
        "title": "ESPN NFL 2K5 (Xbox) serializer-oriented static SCNE format",
        "version": 1,
        "byte_order": "little-endian unless a field says otherwise",
        "contains_retail_geometry_or_pixel_bytes": False,
        "scope": {
            "proved_read": [
                "4,616 canonical SCNE objects and their eight top-level tables",
                "54,966 shape records and 276,642 submesh records",
                "register-0 FLOAT3 and NORMSHORT3 static positions",
                "bounded retail NV2A push streams and their topology",
            ],
            "serializer_boundary": "same-vertex-count position-only replacement in an existing decoded SCNE allocation",
            "not_a_writer": True,
            "implemented_witness": {
                "target": "outer 3280 / chunk 5 / stadium shape 4 group36",
                "format": "four raw-Xbox FLOAT3 positions at fixed 12-byte stride",
                "writer": "tools/nfl_stadium_group36_position_patch.py",
                "independent_verifier": "tools/nfl_stadium_group36_position_verify.py",
                "roundtrip_report": "reports/assets/nfl_stadium_group36_position_patch_roundtrip.json",
                "runtime_proved": False,
            },
            "implemented_stadium_catalog_dispatcher": {
                "catalog": "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json",
                "catalog_sha256": "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa",
                "authorized_target_count": 75,
                "position_format": "contiguous register-0 FLOAT3 only",
                "writer": "tools/nfl_stadium_catalog_position_patch.py",
                "independent_verifier": "tools/nfl_stadium_catalog_position_verify.py",
                "second_target": "outer 3280 / chunk 5 / stadium shape 1 upper_deck",
                "roundtrip_report": "reports/assets/nfl_stadium_catalog_position_patch_roundtrip.v2.json",
                "runtime_proved": False,
                "semantic_rigidity_proved": False,
            },
            "not_claimed": [
                "edited glTF to SCNE implementation",
                "topology or vertex-count regeneration",
                "stream, table, pointer, or archive relayout",
                "material, UV, normal, skin, morph, skeleton, attachment, animation, collision, or LOD semantics",
                "runtime acceptance on xemu or original Xbox hardware",
                "production readiness",
            ],
        },
        "source_evidence": source_evidence,
        "binary_evidence": {
            "default_xbe": {
                "sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
                "md5": "444064a9ec984dd29d2c05a43f5c96e8",
                "scne_loader_registration_va": "0x00045bc0",
                "scene_descriptor_relocator_va": "0x0002f140",
                "shape_relocator_va": "0x00022f90",
                "static_render_function_va": "0x000243d0",
            },
            "cxbx_reloaded": {
                "commit": "585c49a50af1255ab155099e06f24505f9c5a800",
                "role": "corroborating Xbox vertex formats, NV2A methods, and NORMSHORT normalization",
            },
            "raw_executable_or_geometry_bytes_embedded": False,
        },
        "outer_archive": {
            "name": "vc_53450030",
            "index_volume_name": "0",
            "alignment_bytes": 0x800,
            "pack_name_alphabet": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "fixed_header_bytes": 0x9C,
            "header_fields": [
                field(0x00, 4, "entry_count", "u32le", "proved", "number of directory entries"),
                field(0x04, 4, "reserved", "u32le", "proved", "must be zero"),
                field(0x08, 4, "populated_pack_count", "u32le", "proved", "number of active pack volumes"),
                field(0x0C, 0x90, "pack_size_blocks", "36*u32le", "proved", "each populated pack size in 0x800-byte blocks"),
            ],
            "entry_record": {
                "stride": 0x0C,
                "fields": [
                    field(0x00, 4, "name_id", "u32le", "proved", "unique resource entry identifier"),
                    field(0x04, 4, "size_bytes", "u32le", "proved", "fixed outer entry extent in bytes"),
                    field(0x08, 4, "offset_blocks", "u32le", "proved", "virtual byte offset divided by 0x800"),
                ],
            },
            "invariants": [
                "payload entries are aligned to 0x800, monotonic, and nonoverlapping",
                "an entry may cross a pack-volume boundary without changing its virtual byte range",
                "a position-only writer preserves the complete directory, every entry offset, and every entry size",
                "bytes outside the selected 0x20+stored_size resource span remain bit-identical",
            ],
        },
        "resource_chunk": {
            "wrapper_size": 0x20,
            "wrapper_struct": "<4s7I",
            "fields": [
                field(0x00, 4, "kind", "ASCII FourCC", "proved", "SCNE for this specification"),
                field(0x04, 4, "stored_size", "u32le", "proved", "body allocation following the wrapper"),
                field(0x08, 4, "system_bytes", "u32le", "proved", "decoded system-buffer length"),
                field(0x0C, 4, "video_bytes", "u32le", "proved", "decoded video-buffer length"),
                field(0x10, 4, "compression_magic", "u32le", "proved", "0xfeedbeef means VC-LZ; zero means raw"),
                field(0x14, 4, "overlap_scratch_bytes", "u32le", "proved", "in-place VC-LZ loader safety scratch"),
                field(0x18, 4, "reserved0", "u32le", "proved", "zero in parsed resources"),
                field(0x1C, 4, "reserved1", "u32le", "proved", "zero in parsed resources"),
            ],
            "decoded_partition": {
                "decoded_size_rule": "system_bytes + video_bytes for every canonical SCNE after raw copy or VC-LZ decode",
                "system_range": "[0, system_bytes)",
                "video_range": "[system_bytes, system_bytes + video_bytes)",
                "pointer_domain": "all SCNE structural pointers are bounded to the system range",
            },
            "corpus": {"compressed_scne_count": 4239, "raw_scne_count": 377},
            "raw": {
                "compression_magic": "0x00000000",
                "decode": "stored body is the decoded body verbatim",
                "canonical_scne_invariant": "stored_size == system_bytes + video_bytes",
                "changed_resource_requirement": "replace bytes only inside the same stored body and preserve the complete wrapper",
            },
            "vc_lz": {
                "sentinel": "0xfeedbeef",
                "stream_prefix": [
                    field(0x00, 4, "decoded_size", "u32le", "proved", "must equal system_bytes + video_bytes"),
                    field(0x04, 4, "stream_tag", "u32le", "opaque", "preserve from target stream"),
                    field(0x08, 1, "offset_bits", "u8", "proved", "range 1..15; preserve from target stream"),
                ],
                "token_grammar": {
                    "flag_order": "one flag byte, least-significant bit first, up to eight tokens",
                    "literal_flag": 0,
                    "match_flag": 1,
                    "match_word": "u16le",
                    "distance": "match_word & ((1 << offset_bits) - 1)",
                    "length": "((match_word >> offset_bits) & ((1 << (16 - offset_bits)) - 1)) + 3",
                    "copy_direction": "high index to low index; matches must not depend on forward overlap",
                },
                "changed_resource_requirements": [
                    "encoded stream length must not exceed the existing stored_size",
                    "independently decode the rebuilt stream to the exact edited decoded bytes",
                    "re-derive the minimum in-place alias scratch and raise wrapper +0x14 when required",
                    "zero-fill only the unused tail inside the existing stored body",
                    "preserve kind, stored_size, system_bytes, video_bytes, target stream tag, offset_bits, and reserved words",
                ],
            },
        },
        "scne_object": {
            "minimum_system_bytes": 0x18,
            "fields": [
                field(0x00, 0x0C, "object_prefix", "opaque bytes", "unknown", "unassigned object header bytes"),
                field(0x0C, 4, "object_marker", "ASCII", "proved", "literal SCNE"),
                field(0x10, 4, "name_pointer", "s32le one-based self-relative", "proved", "UTF-16LE NUL-terminated scene name"),
                field(0x14, 4, "descriptor_pointer", "s32le one-based self-relative", "proved", "target is a 0x54-byte scene descriptor"),
            ],
            "name_invariant": "object +0x10 name equals descriptor +0x00 name in all 4,616 canonical scenes",
        },
        "relative_pointer": {
            "encoding": "signed 32-bit little-endian",
            "null_value": 0,
            "target_formula": "pointer_field_offset - 1 + s32le(pointer_field)",
            "inverse_formula": "stored_s32 = target_offset - pointer_field_offset + 1",
            "domain": "decoded SCNE system buffer",
            "fail_closed": [
                "reject a nonzero pointer whose target is outside [0, system_bytes)",
                "reject a nonzero count with a null table pointer",
                "reject target + count*stride beyond system_bytes",
                "preserve existing pointer bytes for the position-only writer boundary",
            ],
        },
        "scene_descriptor": {
            "size": 0x54,
            "relocator_xbe_va": "0x0002f140",
            "fields": descriptor_fields,
            "top_level_tables": tables,
        },
        "shape_record": {
            "stride": 0x100,
            "relocator_xbe_va": "0x00022f90",
            "version": {"offset": 0x44, "encoding": "u32le", "canonical_value": 2},
            "fields": [
                field(0x00, 0x10, "unknown_00", "opaque bytes", "unknown", "unassigned shape bytes"),
                field(0x10, 4, "position_scale", "f32le", "proved-static-position", "NORMSHORT3 common static-shader scale; otherwise preserve", "preserve-v1"),
                field(0x14, 0x0C, "unknown_14", "opaque bytes", "unknown", "unassigned shape bytes"),
                field(0x20, 0x0C, "position_bias_xyz", "3*f32le", "proved-static-position", "NORMSHORT3 common static-shader bias; otherwise preserve", "preserve-v1"),
                field(0x2C, 0x14, "unknown_2c", "opaque bytes", "unknown", "unassigned shape bytes"),
                field(0x40, 4, "name_pointer", "s32le one-based self-relative", "proved", "UTF-16LE shape name/reference"),
                field(0x44, 4, "version", "u32le", "proved", "canonical value 2"),
                field(0x48, 4, "unknown_48", "opaque bytes", "unknown", "unassigned shape bytes"),
                field(0x4C, 2, "vertex_count", "u16le", "proved", "number of vertices addressed by every active stream"),
                field(0x4E, 2, "morph_channel_count", "u16le", "proved-structure-only", "count of 0x0c-byte records; semantics unknown"),
                field(0x50, 2, "transform_count", "u16le", "proved-structure-only", "count of 0x70-byte records; excluded from static writer"),
                field(0x52, 2, "unknown_52", "opaque bytes", "unknown", "unassigned shape bytes"),
                field(0x54, 2, "submesh_count", "u16le", "proved", "count of 0x80-byte submesh records"),
                field(0x56, 0x0E, "unknown_56", "opaque bytes", "unknown", "unassigned shape bytes"),
                field(0x64, 4, "transform_table_pointer", "s32le one-based self-relative", "proved-structure-only", "0x70-byte records"),
                field(0x68, 0x08, "unknown_68", "opaque bytes", "unknown", "unassigned shape bytes"),
                field(0x70, 4, "submesh_table_pointer", "s32le one-based self-relative", "proved", "0x80-byte records"),
                field(0x74, 4, "morph_channel_table_pointer", "s32le one-based self-relative", "proved-structure-only", "0x0c-byte records"),
                field(0x78, 0x0C, "unknown_78", "opaque bytes", "unknown", "unassigned shape bytes"),
                field(0x84, 0x40, "vertex_input_descriptors", "16*u32le", "proved", "one descriptor for each Xbox input register"),
                field(0xC4, 0x10, "vertex_stream_strides", "8*u16le", "proved", "stride for streams 0..7"),
                field(0xD4, 0x20, "vertex_stream_pointers", "8*s32le one-based self-relative", "proved", "start pointer for streams 0..7"),
                field(0xF4, 0x0C, "unknown_f4", "opaque bytes", "unknown", "unassigned shape tail"),
            ],
            "nested_tables": [
                {"name": "transform", "count_offset": 0x50, "pointer_offset": 0x64, "stride": 0x70, "semantics": "excluded/partially recovered"},
                {"name": "submesh", "count_offset": 0x54, "pointer_offset": 0x70, "stride": 0x80, "semantics": "material binding and push topology fields below"},
                {"name": "morph_channel", "count_offset": 0x4E, "pointer_offset": 0x74, "stride": 0x0C, "semantics": "unknown; excluded"},
            ],
        },
        "vertex_declaration": {
            "descriptor_formula": "(byte_offset << 16) | (stream_index << 8) | format_code",
            "register_count": 16,
            "stream_count": 8,
            "formats": formats,
            "active_corpus_formats": ["NONE", "FLOAT3", "D3DCOLOR", "SHORT1", "NORMSHORT2", "NORMSHORT3", "NORMPACKED3"],
            "static_position": {
                "register": 0,
                "accepted_formats": [
                    {
                        "name": "FLOAT3", "format_code": "0x32", "byte_size": 12,
                        "decode": "three finite little-endian binary32 values",
                        "same_count_encode": "pack each accepted finite coordinate as binary32 into the existing register-0 byte lane",
                    },
                    {
                        "name": "NORMSHORT3", "format_code": "0x31", "byte_size": 6,
                        "normalization": "q/32767 for q >= 0; q/32768 for q < 0",
                        "decode": "binary32(normalize(q) * shape.position_scale + shape.position_bias_xyz)",
                        "same_count_encode_v1": "preserve scale and bias; accept only signed-short triples whose independent binary32 decode exactly equals the requested binary32 positions",
                        "scale_bias_reauthoring": "not in v1 writer boundary; selection/error policy is not proved",
                    },
                ],
            },
            "stream_invariants": [
                "descriptor stream_index is 0..7",
                "byte_offset + format byte_size <= selected stream stride",
                "an active stream has both nonzero stride and nonnull pointer",
                "stream_start + vertex_count*stride <= system_bytes",
                "same-count position writing changes only the register-0 component byte lane for each existing vertex",
            ],
        },
        "submesh_record": {
            "stride": 0x80,
            "fields": [
                field(0x00, 2, "material_index", "u16le", "proved", "index into scene material table"),
                field(0x02, 2, "auxiliary_index", "u16le", "opaque", "cache/palette interpretation unproved"),
                field(0x04, 0x74, "unknown_04", "opaque bytes", "unknown", "unassigned submesh bytes"),
                field(0x78, 4, "push_stream_pointer", "s32le one-based self-relative", "proved", "first NV2A command word"),
                field(0x7C, 2, "primary_command_word_count", "u16le", "proved", "bounded word count consumed for topology"),
                field(0x7E, 2, "secondary_command_word_count", "u16le", "opaque", "preserve; semantics unproved"),
            ],
            "invariants": [
                "material_index < scene material count",
                "nonzero primary word count requires a nonnull push pointer",
                "push_start + primary_word_count*4 <= system_bytes",
                "topology and the complete 0x80-byte record are preserved by the v1 position-only boundary",
            ],
        },
        "nv2a_push_topology": {
            "word_encoding": "u32le",
            "header_decode": {
                "accepted_signature": "(header & 0xe0030003) is 0x00000000 or 0x40000000",
                "instruction": "(header >> 29) & 7",
                "method": "header & 0x1ffc",
                "parameter_count": "(header >> 18) & 0x7ff",
                "boundary": "header plus parameter_count words must remain within the declared primary word count",
            },
            "methods": {
                "0x17fc": {"name": "NV097_SET_BEGIN_END", "parameters": "primitive mode values; zero ends the active batch"},
                "0x1800": {"name": "NV097_ARRAY_ELEMENT16", "parameters": "two u16 vertex indices per u32, low halfword then high halfword"},
                "0x1808": {"name": "NV097_ARRAY_ELEMENT32", "parameters": "one u32 vertex index per parameter"},
                "0x1810": {"name": "NV097_DRAW_ARRAYS", "parameters": "start = low 24 bits; count = high 8 bits + 1"},
            },
            "primitive_modes": {
                "0": "END", "1": "POINTS", "2": "LINES", "3": "LINE_LOOP",
                "4": "LINE_STRIP", "5": "TRIANGLES", "6": "TRIANGLE_STRIP",
                "7": "TRIANGLE_FAN", "8": "QUADS", "9": "QUAD_STRIP", "10": "POLYGON",
            },
            "canonical_corpus": {
                "submesh_streams": 276642,
                "observed_draw_modes": {"TRIANGLE_STRIP": 275213, "QUADS": 1429},
                "end_markers": 276642,
                "unknown_methods": 0,
                "all_streams_end_at_declared_word_boundary": True,
                "all_vertex_references_below_vertex_count": True,
            },
            "writer_boundary": "decode and validate but preserve every push word bit-exact; topology regeneration is excluded",
        },
        "fixed_allocation_safety": {
            "required": True,
            "rules": [
                "do not change decoded system_bytes or video_bytes",
                "do not change any table count, pointer, record stride, vertex_count, stream stride, stream pointer, submesh count, or push stream",
                "do not write beyond any existing vertex component lane or decoded SCNE extent",
                "for compressed targets, reject edits whose independently verified VC-LZ encoding exceeds stored_size",
                "preserve the outer entry size and offset and every byte outside the selected resource span",
                "reject instead of relocating, truncating, decimating, or silently quantizing outside the declared exact-acceptance rule",
            ],
            "headroom_claim": "none; padding or compressed slack is not a proved relocatable mesh allocation",
            "over_budget_result": "writer must fail closed; retail runtime behavior is untested",
        },
        "same_count_position_write_boundary_v1": {
            "status": "implemented for pinned group36 plus a 75-target stadium FLOAT3 catalog; general 51,679-shape eligibility-profile dispatch not implemented",
            "purpose": "first fail-closed static deformation slice; not arbitrary mesh import",
            "eligibility": [
                "shape version is exactly 2",
                "vertex_count is nonzero and unchanged",
                "morph_channel_count is zero",
                "transform_count is exactly one, conservatively excluding multi-transform shapes",
                "register 0 exists and is exactly FLOAT3 or NORMSHORT3",
                "the register-0 byte lane is in bounds and does not overlap another active attribute lane",
                "all source tables, streams, submeshes, push words, and pointers pass the complete structural validator",
            ],
            "eligibility_corpus_count": 51679,
            "eligibility_caveat": "one transform and zero morph channels is a conservative mechanical boundary, not a complete semantic proof of attachment or skin ownership",
            "input_contract": [
                "exactly vertex_count ordered XYZ triples",
                "each requested coordinate is finite and already canonical binary32; reject implicit precision loss",
                "FLOAT3 writes only three f32le values in each existing register-0 lane",
                "NORMSHORT3 preserves scale and bias and requires an s16 triple whose independent binary32 decode exactly equals each requested binary32 triple",
            ],
            "mandatory_rejections": [
                "changed vertex count or ordering",
                "changed topology, submesh membership, material index, transform count, morph count, declaration, stride, pointer, or allocation",
                "non-finite or non-binary32-exact input",
                "NORMSHORT3 target not exactly representable under the preserved scale and bias",
                "overlapping register lanes",
                "fixed-span VC-LZ overflow or failed independent reconstruction",
            ],
            "excluded_extensions": [
                "automatic decimation",
                "scale/bias refitting",
                "topology generation",
                "new stream or record allocation",
                "node or transform editing",
            ],
            "implemented_group36_witness": {
                "outer_index": 3280,
                "outer_id": "0xe4d6b0bc",
                "chunk_index": 5,
                "scene_index": 2648,
                "scene_name": "stadium",
                "shape_index": 4,
                "shape_name": "group36",
                "vertex_count": 4,
                "position_format": "FLOAT3",
                "position_span": [78368, 78416],
                "position_stream_sha256": "65ab99a567a43ebe13c38f6921834896f56f609d954573bb3ae94d414562ab7d",
                "source_decoded_sha256": "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8",
                "no_op_whole_volume_bit_exact": True,
                "changed_all_zero_decoded_outside_position_bit_exact": True,
                "changed_output_volume_sha256": "c48117938862fa03b5b3d871db87cb7d3c32a9653be497d46dc188ba51993fca",
                "fixed_final_opaque_tail_preserved": True,
                "independent_verifier": True,
                "runtime_proved": False,
            },
            "implemented_stadium_catalog_v2": {
                "catalog_schema": "nfl2k5_stadium_static_target_catalog/v1",
                "catalog_sha256": "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa",
                "authorized_target_count": 75,
                "writer_dispatch": "target_id selects exact count, encoding, and decoded lane from the pinned hashes-only catalog",
                "second_target_id": "nfl2k5/stadium/o3280/c5/s1",
                "second_target_name": "upper_deck",
                "second_target_vertex_count": 12,
                "second_target_no_op_whole_volume_bit_exact": True,
                "second_target_changed_decoded_outside_position_bit_exact": True,
                "second_target_changed_output_volume_sha256": "96c2d8dd4ed4f65df67157ad6a822878bcbd4eefc960135176cd8030c9f9b176",
                "second_target_rebuilt_consumed_bytes": 908799,
                "second_target_rebuilt_scratch_bytes": 96,
                "fixed_final_opaque_tail_preserved": True,
                "independent_verifier": True,
                "runtime_proved": False,
                "semantic_rigidity_proved": False,
            },
        },
        "roundtrip_contract": {
            "no_op": [
                "retain the original backing bytes for all unknown and preserved fields",
                "decode then project the unchanged position data without rewriting",
                "emit a byte-identical complete 0x20+stored_size resource span, not merely an equivalent decompression",
                "verify the complete no-op span SHA-256 equals the source span SHA-256",
            ],
            "changed_position": [
                "reparse the source and replacement independently under every structural bound in this spec",
                "independently decode every written FLOAT3 or NORMSHORT3 position and compare exact binary32 values to the accepted target",
                "derive an exact changed-byte set and require it to be a subset of approved register-0 lanes and, only in a future explicit extension, scale/bias fields",
                "require every byte outside the approved decoded lanes to equal the decoded source",
                "for VC-LZ, independently decode the complete rebuilt fixed span to the exact edited decoded body",
                "require complete outer entry size/offset stability and bit identity outside the selected resource span",
            ],
            "runtime_witness_required_for_runtime_claim": True,
        },
        "known_unknowns": [
            "SCNE object prefix and descriptor fields not listed as proved",
            "aux_14, aux_60, and aux_50 record semantics",
            "most material fields; only name and +0x30 embedded-texture link are proved",
            "node hierarchy and complete transform application",
            "shape fields explicitly labeled unknown",
            "meanings of Xbox input registers other than register-0 position",
            "normal and UV registers and shader-specific semantics",
            "transform, skin influence, attachment, morph, skeleton, animation, collision, and LOD serialization",
            "submesh auxiliary index and secondary command count semantics",
            "safe changed-topology push serialization and allocation/relocation",
            "general scale/bias fitting policy for edited NORMSHORT3 geometry",
            "runtime acceptance and original-Xbox memory ownership",
        ],
        "claim_flags": {
            "complete_static_position_read_spec": True,
            "complete_scne_serializer": False,
            "same_count_position_writer_implemented": False,
            "pinned_group36_float3_same_count_writer_implemented": True,
            "stadium_catalog_75_float3_dispatch_implemented": True,
            "general_eligibility_profile_writer_dispatch_implemented": False,
            "static_topology_read_proved": True,
            "topology_write_proved": False,
            "material_uv_write_proved": False,
            "skinning_write_proved": False,
            "runtime_proved": False,
            "production_ready": False,
        },
        "corpus_facts": {
            "scene_count": 4616,
            "shape_count": 54966,
            "submesh_count": 276642,
            "vertex_count": 13731388,
            "conservative_v1_position_write_candidate_shape_count": 51679,
            "register_zero_format_counts": {"FLOAT3": 46192, "NORMSHORT3": 8774},
            "all_eight_top_level_tables_bounded": True,
            "all_vertex_streams_bounded": True,
            "all_push_streams_bounded": True,
        },
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SpecError(message)


def validate_sources() -> None:
    for key, (relative, size, expected_hash) in SOURCE_PINS.items():
        path = ROOT / relative
        require(path.is_file(), f"{key}: missing {relative}")
        require(path.stat().st_size == size, f"{key}: size drift in {relative}")
        require(sha256(path) == expected_hash, f"{key}: SHA-256 drift in {relative}")


def validate_parser_constants() -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    import nfl_outer  # type: ignore
    import nfl_scne_inventory  # type: ignore
    import nfl_txtr  # type: ignore

    require(nfl_outer.ALIGNMENT == 0x800, "outer alignment drift")
    require(nfl_outer.PACK_SLOT_COUNT == 36, "outer pack slot count drift")
    require(nfl_outer.HEADER_SIZE == 0x9C, "outer header size drift")
    require(nfl_outer.ENTRY_SIZE == 0x0C, "outer entry stride drift")
    require(nfl_txtr.HEADER.size == 0x20 and nfl_txtr.HEADER.format == "<4s7I",
            "resource wrapper drift")
    require(nfl_txtr.COMPRESSED_SENTINEL == 0xFEEDBEEF, "VC-LZ sentinel drift")
    require(nfl_scne_inventory.DESCRIPTOR_SIZE == 0x54, "SCNE descriptor size drift")
    actual_tables = [
        (item.key, item.semantic, item.count_offset, item.pointer_offset,
         item.stride, f"0x{item.relocator:08x}" if item.relocator is not None else None)
        for item in nfl_scne_inventory.TABLE_SPECS
    ]
    require(actual_tables == TABLES, "top-level SCNE table constants drift")
    actual_formats = [
        (code, *nfl_scne_inventory.VERTEX_FORMATS[code])
        for code in sorted(nfl_scne_inventory.VERTEX_FORMATS)
    ]
    require(actual_formats == VERTEX_FORMATS, "Xbox vertex format table drift")


def validate_reports() -> None:
    inventory = json.loads((ROOT / SOURCE_PINS["scne_inventory_report"][0]).read_text())
    norm = json.loads((ROOT / SOURCE_PINS["normshort3_report"][0]).read_text())
    resources = json.loads((ROOT / SOURCE_PINS["resource_inventory_report"][0]).read_text())
    group36 = json.loads((ROOT / SOURCE_PINS["group36_roundtrip"][0]).read_text())
    catalog_roundtrip = json.loads(
        (ROOT / SOURCE_PINS["catalog_position_roundtrip"][0]).read_text()
    )
    require(inventory.get("schema") == "nfl2k5_scne_inventory/v1", "SCNE report schema drift")
    summary = inventory["summary"]
    require(summary["scene_count"] == 4616, "SCNE scene count drift")
    require(summary["shape_count"] == 54966, "SCNE shape count drift")
    require(summary["submesh_count"] == 276642, "SCNE submesh count drift")
    require(summary["all_descriptors_valid"] is True, "invalid SCNE descriptor")
    require(summary["all_eight_table_ranges_bounded"] is True, "unbounded SCNE table")
    require(summary["all_vertex_stream_ranges_bounded"] is True, "unbounded vertex stream")
    require(summary["all_push_streams_bounded"] is True, "unbounded push stream")
    require(summary["all_push_vertex_references_in_bounds"] is True,
            "out-of-bounds push vertex reference")
    require(summary["primitive_mode_counts"] == {
        "END": 276642, "QUADS": 1429, "TRIANGLE_STRIP": 275213,
    }, "push primitive corpus drift")
    require(summary["vertex_attribute_format_counts"]["FLOAT3"] == 46192,
            "FLOAT3 corpus drift")
    require(summary["vertex_attribute_format_counts"]["NORMSHORT3"] == 8774,
            "NORMSHORT3 corpus drift")
    require(norm.get("schema") == "nfl2k5_normshort3_positions/v1",
            "NORMSHORT3 report schema drift")
    require(norm["complete_decode_equation"] ==
            "position.xyz = normshort3(register0.xyz) * serialized_shape_float(+0x10) + serialized_shape_float3(+0x20)",
            "NORMSHORT3 equation drift")
    require(norm["corpus"]["vertex_count"] == 13731388, "position vertex count drift")
    require(norm["corpus"]["register_zero_format_counts"] == {
        "FLOAT3": 46192, "NORMSHORT3": 8774,
    }, "register-zero corpus drift")
    require(norm["executable"]["sha256"] ==
            "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
            "default.xbe SHA-256 drift")
    require(norm["executable"]["md5"] == "444064a9ec984dd29d2c05a43f5c96e8",
            "default.xbe MD5 drift")
    with (ROOT / SOURCE_PINS["scne_shape_rows"][0]).open(
        encoding="utf-8", newline=""
    ) as stream:
        conservative = sum(
            int(row["morph_channel_count"]) == 0 and int(row["transform_count"]) == 1
            for row in csv.DictReader(stream, dialect="excel-tab")
        )
    require(conservative == 51679, "conservative position-write candidate count drift")
    require(resources.get("schema") == "nfl2k5_resource_chunk_inventory/v1",
            "resource inventory schema drift")
    scne = [item for item in resources["chunks"] if item["kind"] == "SCNE"]
    require(len(scne) == 4616, "resource inventory SCNE count drift")
    compressed = sum(int(str(item["word_10"]), 0) == 0xFEEDBEEF for item in scne)
    raw = sum(int(str(item["word_10"]), 0) == 0 for item in scne)
    require((compressed, raw) == (4239, 377), "SCNE compression corpus drift")
    require(all(
        int(item["stored_size"]) == int(item["word_08"]) + int(item["word_0c"])
        for item in scne if int(str(item["word_10"]), 0) == 0
    ), "raw SCNE stored/decoded size drift")
    require(group36.get("schema") == "nfl2k5_static_position_patch_roundtrip/v1",
            "group36 roundtrip schema drift")
    require(group36["source"] == {
        "index_sha256_after":
            "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
        "index_sha256_before":
            "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
        "retail_modified": False,
        "volume_9_sha256_after":
            "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
        "volume_9_sha256_before":
            "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
    }, "group36 source-preservation proof drift")
    require(group36["no_op"]["mode"] == "no_op"
            and group36["no_op"]["output"]["volume_sha256"] ==
                "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a"
            and group36["no_op"]["output"]["pack_changed_byte_count"] == 0
            and group36["no_op"]["compression"]["consumed_bytes"] == 908864
            and group36["no_op"]["compression"]["scratch_bytes"] == 16,
            "group36 no-op whole-volume proof drift")
    changed = group36["controlled_all_zero_edit"]
    require(changed["mode"] == "patched"
            and changed["output"]["volume_sha256"] ==
                "c48117938862fa03b5b3d871db87cb7d3c32a9653be497d46dc188ba51993fca"
            and changed["decoded"]["outside_position_bit_exact"] is True
            and changed["compression"]["consumed_bytes"] == 908825
            and changed["compression"]["zero_gap_bytes"] == 39
            and changed["compression"]["scratch_bytes"] == 64,
            "group36 changed copied-volume proof drift")
    require(group36["refusals"] == {
        "existing_output_directory": True,
        "growth_output_artifact_created": False,
        "hardlink_source_alias": True,
        "partial_second_link_collision": True,
        "prepublication_raced_name": True,
        "recursive_manifest_extra_key": True,
        "retail_source_directory_as_output": True,
        "staged_replacement_before_unlink": True,
        "symlinked_output_parent": True,
        "tail_consuming_growth_recipe": True,
    }, "group36 refusal proof drift")
    require(group36["safety"]["fixed_final_opaque_tail"] is True
            and group36["safety"]["pack_outside_chunk_bit_exact"] is True
            and group36["safety"]["cleanup_unlinks_owned_regular_inodes_only"] is True
            and group36["claims"] == {
                "arbitrary_static_mesh_write_back_proved": False,
                "changed_topology_write_back_proved": False,
                "production_ready": False,
                "runtime_visibility_proved": False,
                "same_count_group36_float3_write_back_proved": True,
            }, "group36 claim boundary drift")
    require(catalog_roundtrip.get("schema") ==
            "nfl2k5_catalog_static_position_patch_roundtrip/v2",
            "catalog position roundtrip schema drift")
    require(catalog_roundtrip["catalog"] == {
        "authorized_target_count": 75,
        "path": "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json",
        "sha256": "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa",
        "size": 858600,
    }, "catalog position authority drift")
    require(catalog_roundtrip["source"]["retail_modified"] is False
            and catalog_roundtrip["no_op"]["mode"] == "no_op"
            and catalog_roundtrip["no_op"]["output"]["pack_changed_byte_count"] == 0
            and catalog_roundtrip["no_op"]["output"]["volume_sha256"] ==
                "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
            "catalog position no-op proof drift")
    catalog_changed = catalog_roundtrip["controlled_nonretail_all_zero_edit"]
    require(catalog_changed["mode"] == "patched"
            and catalog_changed["output"]["volume_sha256"] ==
                "96c2d8dd4ed4f65df67157ad6a822878bcbd4eefc960135176cd8030c9f9b176"
            and catalog_changed["decoded"]["decoded_changed_byte_count"] == 144
            and catalog_changed["decoded"]["outside_position_bit_exact"] is True
            and catalog_changed["compression"]["consumed_bytes"] == 908799
            and catalog_changed["compression"]["minimum_alias_scratch_bytes"] == 66
            and catalog_changed["compression"]["scratch_bytes"] == 96,
            "catalog position changed proof drift")
    catalog_refusals = catalog_roundtrip["refusals"]
    require(catalog_refusals["overflow_output_artifact_created"] is False
            and all(value is True for key, value in catalog_refusals.items()
                    if key != "overflow_output_artifact_created")
            and catalog_roundtrip["claims"] == {
                "authorized_catalog_targets": 75,
                "catalog_backed_same_count_float3_dispatcher_implemented": True,
                "changed_topology_or_count_proved": False,
                "hardware_visibility_proved": False,
                "production_ready": False,
                "runtime_visibility_proved": False,
                "semantic_rigidity_proved": False,
                "upper_deck_full_copied_volume_roundtrip_proved": True,
            }, "catalog position refusal or claim boundary drift")


def validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    validate_sources()
    validate_parser_constants()
    validate_reports()
    expected = canonical_spec()
    require(spec == expected, "checked-in static SCNE specification differs from canonical data")
    return {
        "schema": "nfl2k5_xbox_static_scne_format_spec_validation/v1",
        "tables": len(spec["scene_descriptor"]["top_level_tables"]),
        "vertex_formats": len(spec["vertex_declaration"]["formats"]),
        "scenes": spec["corpus_facts"]["scene_count"],
        "shapes": spec["corpus_facts"]["shape_count"],
        "submeshes": spec["corpus_facts"]["submesh_count"],
        "general_writer_implemented":
            spec["claim_flags"]["general_eligibility_profile_writer_dispatch_implemented"],
        "group36_writer_implemented":
            spec["claim_flags"]["pinned_group36_float3_same_count_writer_implemented"],
        "stadium_catalog_writer_implemented":
            spec["claim_flags"]["stadium_catalog_75_float3_dispatch_implemented"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--write", action="store_true",
                        help="write canonical JSON after all evidence checks")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.write:
        validate_sources()
        validate_parser_constants()
        validate_reports()
        args.spec.parent.mkdir(parents=True, exist_ok=True)
        args.spec.write_text(
            json.dumps(canonical_spec(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    require(args.spec.is_file(), f"missing specification: {args.spec}")
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    result = validate_spec(spec)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, SpecError, KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
