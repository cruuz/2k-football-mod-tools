#!/usr/bin/env python3
"""Generate and strictly validate the APF 2K8 static SCNE serializer spec.

The checked-in JSON is a normative, serializer-oriented data artifact.  This
module deliberately keeps the canonical facts in code as an independent
oracle, pins every evidence input, checks the full-corpus proof projection,
and provides small reference encoders for the only three POSITION0 encodings
closed by executable evidence.  It does not patch a game archive.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "reports/specs/apf2k8_scne_static_serializer.v1.json"
SCHEMA = "apf2k8_scne_static_serializer/v1"
VALIDATION_SCHEMA = "apf2k8_scne_static_serializer_validation/v1"


class SpecError(ValueError):
    """A normative fact, evidence pin, or fail-closed invariant drifted."""


SOURCE_PINS = {
    "scene_inventory": {
        "path": "reports/assets/apf_scene_inventory.json",
        "size_bytes": 98_732_152,
        "sha256": "93269dbc2fbace97890af389cd97a35e5291fec39bdfd1ed411639550e4dac36",
        "schema": "apf_scene_inventory/v1",
        "role": "complete 1,303-resource structural and POSITION/topology evidence ledger",
    },
    "inner_manifest": {
        "path": "reports/manifests/apf_inner.json",
        "size_bytes": 9_509_144,
        "sha256": "b57772a88e969db47aca6add24b1387ab2470b53cdb2f6f21bd4a3d8999fb6d1",
        "schema": "apf_inner_manifest/v1",
        "role": "complete IFF/H7A block, file, part, footer, and DRAM/VRAM/SRAM ownership ledger",
    },
    "scene_parser": {
        "path": "tools/apf_scene.py",
        "size_bytes": 61_388,
        "sha256": "0f416e57fe02b8ac7a3695820f23af6875d2413a50905a0292c88e231fd899c2",
        "schema": None,
        "role": "strict SCNE parser, POSITION decoder, strip decoder, and corpus generator",
    },
    "iff_h7a_parser": {
        "path": "tools/apf_inner.py",
        "size_bytes": 81_272,
        "sha256": "4a7014fe79cc445d83d86e9e06b68468931bb29d5018b0e91d5c2772ed64cedf",
        "schema": None,
        "role": "strict IFF/H7A parser and part-range derivation",
    },
    "iff_h7a_rebuild_proof": {
        "path": "tools/apf_texture_patch.py",
        "size_bytes": 48_541,
        "sha256": "194d37682ac28fef1853e4c27c8a0327b75ef52218afcf1fbc6f4fa169e1b7b9",
        "schema": None,
        "role": "proved copied-entry H7A encode/decode and fixed-allocation IFF rebuild pattern",
    },
    "xex_vertex_encoder_pseudoc": {
        "path": "research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_18688_18943.c",
        "size_bytes": 224_321,
        "sha256": "2264c1b155e84696584dbee72cc7b7b657b331095d06ba3b3115da450cecc1c9",
        "schema": None,
        "role": "XEX-derived Function_84B8BE00 inverse-format evidence and helper FUN_84B8BD88",
    },
    "xex_reconstruction_report": {
        "path": "reports/headers/apf2k8_xex_report.json",
        "size_bytes": 293_129,
        "sha256": "dfd21f9db2fdb683b2dbd0390d351fdac84ba1e796a0e0c5e0e60c28827f3f1c",
        "schema": "apf2k8-xex-recon-v1",
        "role": "executable identity and reconstruction evidence",
    },
    "scene_research": {
        "path": "docs/research/apf_scene.md",
        "size_bytes": 24_735,
        "sha256": "3c972eab05effe039e26ac620b639c918f21733b946884aafecf4cc4dc9216c4",
        "schema": None,
        "role": "human-auditable derivation, examples, limitations, and reproduction contract",
    },
    "static_gltf_research": {
        "path": "docs/research/apf_static_gltf.md",
        "size_bytes": 4_930,
        "sha256": "6eb87bd39efe136b60d9596f66aa70acc4ce8c591aba68d2aa4f893db6160da5",
        "schema": None,
        "role": "complete read-side glTF corpus scope and omission contract",
    },
    "same_count_recipe_schema": {
        "path": "reports/specs/apf2k8_scne_same_count_position_recipe.schema.json",
        "size_bytes": 4_064,
        "sha256": "8094a4a64325728082091e87ba3fcd0e5ed30c8c6f06f1e7074934720438af51",
        "schema": None,
        "role": "constant-pinned four-FLOAT3 recipe grammar for the first write-back target",
    },
    "same_count_nonretail_sample_recipe": {
        "path": "reports/asset_samples/apf_scene/stadium_polySurface19930_nonretail_zero_recipe.json",
        "size_bytes": 1_938,
        "sha256": "fc3b3e010cc534634470e29e8395a5e56c6b0cbc2d714464355a27be3f59764b",
        "schema": "apf2k8_scne_same_count_position_recipe/v1",
        "role": "public recipe-shape sample with four independently authored all-zero positions and no retail geometry",
    },
    "same_count_local_proof_recipe_generator": {
        "path": "tools/apf_stadium_static_position_proof_recipes.py",
        "size_bytes": 4_943,
        "sha256": "7b8202a0287ec2e74279ad00fbf84c356cb02154848b29b5591cce6b4167a1cb",
        "schema": None,
        "role": "derives retail/no-op and +1/+2/+3 proof recipes only into user-local temporary paths",
    },
    "same_count_writer": {
        "path": "tools/apf_stadium_static_position_patch.py",
        "size_bytes": 43_189,
        "sha256": "37210991eb4c470facd778358c477931e6074e4e84915d330e6adbb44c2c2f4b",
        "schema": None,
        "role": "fail-closed copied-1A writer for outer14/inner8/node17 only",
    },
    "same_count_independent_verifier": {
        "path": "tools/apf_stadium_static_position_verify.py",
        "size_bytes": 48_792,
        "sha256": "545d3f362ad4bf94a8d9ccff303ec0d37608c60a22af9bbbc18a7c10ab76415e",
        "schema": None,
        "role": "stdlib-only independent outer/IFF/H7A/SCNE/parser and preservation verifier",
    },
    "same_count_roundtrip_report": {
        "path": "reports/assets/apf_scne_same_count_position_roundtrip.json",
        "size_bytes": 6_971,
        "sha256": "5e85c58cf258b19ab40f7b046f7da3010a510dac8d2cd83ede976883af8ab5dd",
        "schema": "apf2k8_scne_same_count_position_roundtrip/v1",
        "role": "complete copied-1A no-op and +1/+2/+3 independent byte-level witnesses",
    },
    "stadium_static_target_catalog": {
        "path": "mod_editor/data/apf2k8_stadium_static_position_target_catalog.v1.json",
        "size_bytes": 456_898,
        "sha256": "c3122019b74645380052670f9fdce389277a454b440dd7b7f438276b05f57469",
        "schema": "apf2k8_stadium_static_position_target_catalog/v1",
        "role": "hashes-only outer14/inner8 catalog of 77 additional bounded FLOAT32x3/no-blend same-count targets and exact node3 handoff",
    },
    "stadium_static_target_catalog_generator": {
        "path": "tools/apf_stadium_static_target_catalog.py",
        "size_bytes": 35_106,
        "sha256": "0f14bc77d890494429b5e1dd898b2e166c4df6eecdb23b63cc52b1878c01a401",
        "schema": None,
        "role": "deterministically re-derives target spans, all part ownership, H7A envelope, and the local-only node3 fit witness",
    },
    "stadium_static_target_catalog_research": {
        "path": "docs/research/apf_stadium_static_target_catalog.md",
        "size_bytes": 2_700,
        "sha256": "8eb81e7afaa065fedaef9a338ef5fc5c541268e57da52060a0b3c879d49a7fbe",
        "schema": None,
        "role": "human-readable catalog scope, fixed-allocation boundary, second-target selection, and non-runtime claim boundary",
    },
    "catalog_position_recipe_schema": {
        "path": "mod_editor/data/apf2k8_stadium_position_recipe.v2.schema.json",
        "size_bytes": 5_585,
        "sha256": "ff24b219f4d00a7342dcc41e37ef4d8afe487af8a23ce1c1fcf523fd498c28ac",
        "schema": None,
        "role": "canonical v2 recipe contract that pins the hashes-only catalog and derives count, stride, lane offset, and FLOAT32x3_BE encoding from target_id",
    },
    "catalog_position_nonretail_sample_recipe": {
        "path": "reports/asset_samples/apf_scene/stadium_node3_nonretail_zero_recipe.json",
        "size_bytes": 2_971,
        "sha256": "329d3290201407f1acb905d432bf8b53547a654fd895cd37a347ae979c4b60a9",
        "schema": "apf2k8_scne_catalog_position_recipe/v2",
        "role": "public node3 recipe-shape witness with 24 independently authored all-zero positions and no retail geometry",
    },
    "catalog_position_local_proof_recipe_generator": {
        "path": "tools/apf_stadium_catalog_position_proof_recipes.py",
        "size_bytes": 3_889,
        "sha256": "b0a53188d67d4ef9ae5974bc4708311ce3c0b83d9d3bfd7d06127699d840f653",
        "schema": None,
        "role": "derives the exact node3 no-op recipe only into a caller-owned local path without printing or committing retail coordinates",
    },
    "catalog_position_writer": {
        "path": "tools/apf_stadium_catalog_position_patch.py",
        "size_bytes": 32_982,
        "sha256": "8a68a4aaa73daf1fd35543e5f6e3f41ab20daf6649a9c98eea367c984d321e7b",
        "schema": None,
        "role": "fail-closed copied-1A v2 dispatcher for all 77 additional hashes-only outer14 stadium targets",
    },
    "catalog_position_independent_verifier": {
        "path": "tools/apf_stadium_catalog_position_verify.py",
        "size_bytes": 36_068,
        "sha256": "3ce51ea6721939efb3b1f73bd10310f1db36d78a36b248a68b94ac2ce09db4d9",
        "schema": None,
        "role": "writer-independent catalog/IFF/H7A/SCNE target re-derivation and complete manifest/byte verifier",
    },
    "catalog_position_roundtrip_report": {
        "path": "reports/assets/apf_scne_catalog_position_roundtrip.json",
        "size_bytes": 5_932,
        "sha256": "eebd060dbcbeb07a01ccb2ac5a3491f0306ec43424080b33ad49258819333eea",
        "schema": "apf2k8_scne_catalog_position_roundtrip/v2",
        "role": "node3 complete copied-1A no-op and public all-zero changed witnesses plus all 77-target dispatcher claim boundary",
    },
    "catalog_position_research": {
        "path": "docs/research/apf_stadium_catalog_position_writeback.md",
        "size_bytes": 5_679,
        "sha256": "28e7cd0f91ca70dd0140104237093cba8be1b657d6d0f1a61a5f13d75ed0d4b7",
        "schema": None,
        "role": "human-auditable v2 dispatcher, node3 proof, preservation, refusal, and remaining-runtime-boundary record",
    },
    "draw_topology_spec": {
        "path": "reports/specs/apf2k8_scne_draw_topology.v1.json",
        "size_bytes": 11_851,
        "sha256": "ef29fc07d80582d938fbb0a00985c9bd0669ca88ba296d06cd39d9029233224b",
        "schema": "apf2k8_scne_draw_topology/v1",
        "role": "normative full 0x30 draw-record layout, corpus-wide index coupling, and bounded node17 same-footprint topology profile",
    },
    "draw_topology_corpus": {
        "path": "reports/assets/apf_scne_draw_topology_corpus.v1.json",
        "size_bytes": 3_591,
        "sha256": "8032c0eda8fefe75d61ae607feabad7bf477c845469374781856237bd13c16a2",
        "schema": "apf2k8_scne_draw_topology_corpus/v1",
        "role": "complete 1,303-resource draw/index relationship proof with aggregate-only topology evidence",
    },
    "draw_topology_generator": {
        "path": "tools/apf_scne_draw_topology_spec.py",
        "size_bytes": 30_576,
        "sha256": "f92c90a2e29f4490b199fc012b3671f02776332d30b05b2fd255d12d207ff275",
        "schema": None,
        "role": "strict corpus scanner, canonical topology-spec generator, and source-backed validator",
    },
    "same_footprint_topology_recipe_schema": {
        "path": "reports/specs/apf2k8_scne_same_footprint_topology_recipe.schema.json",
        "size_bytes": 5_949,
        "sha256": "a201d33a1fd44daebb05e68ded770c08966ff6b8bf28267e8603df91fb63bb8e",
        "schema": None,
        "role": "constant-pinned four-index permutation recipe grammar for the node17 topology target",
    },
    "same_footprint_topology_nonretail_sample": {
        "path": "reports/asset_samples/apf_scene/stadium_node17_nonretail_permuted_strip_recipe.json",
        "size_bytes": 1_568,
        "sha256": "9fb9262a415632e7b430375c35cefcd4a72128c029172dcd59ca1f695c49cb99",
        "schema": "apf2k8_scne_same_footprint_topology_recipe/v1",
        "role": "public nonretail four-index permutation witness containing no retail index sequence",
    },
    "same_footprint_topology_writer": {
        "path": "tools/apf_stadium_node17_topology_patch.py",
        "size_bytes": 26_804,
        "sha256": "f94ae1306e5483820a133bad4cd01d4a8acd0dead2cb7fffef0b2730b7842a32",
        "schema": None,
        "role": "fail-closed copied-1A same-footprint topology writer for outer14/inner8/node17 only",
    },
    "same_footprint_topology_independent_verifier": {
        "path": "tools/apf_stadium_node17_topology_verify.py",
        "size_bytes": 31_202,
        "sha256": "2da959176066b5b202eaf5794161d0c205f71b64d5ebd5b8519652cec5c76f3c",
        "schema": None,
        "role": "writer-independent stdlib-only IFF/H7A/SCNE topology and complete-preservation verifier",
    },
    "same_footprint_topology_roundtrip": {
        "path": "reports/assets/apf_stadium_node17_same_footprint_topology_roundtrip.json",
        "size_bytes": 6_781,
        "sha256": "3294bec0a2906433885391cc826c47fe4cd6c0fb601a1840ffb46b24dadc34b4",
        "schema": "apf2k8_scne_same_footprint_topology_roundtrip/v1",
        "role": "complete copied-1A no-op and public nonretail changed-index byte-level witnesses",
    },
    "draw_topology_research": {
        "path": "docs/research/apf_scne_draw_topology_writeback.md",
        "size_bytes": 7_186,
        "sha256": "c517bb4ba0207b385f114ba06a738e3a9e63a0d4929f6e2c9522207ac316b3e8",
        "schema": None,
        "role": "human-auditable draw-field derivation, bounded writer proof, refusals, and remaining boundary",
    },
}


CORPUS_FACTS = {
    "retail_0a_sha256": "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "scne_resources": 1_303,
    "structural_failures": 0,
    "mesh_nodes": 13_006,
    "source_vertices": 16_217_141,
    "serialized_indices": 24_519_417,
    "hierarchy_records": 40_991,
    "vertex_declarations": 43_098,
    "draw_records": 47_112,
    "position_formats": {
        "float32x3": 12_416,
        "snorm16x4": 365,
        "snorm10_10_10": 225,
    },
    "stream_count_distribution": {"1": 12_713, "2": 292, "3": 1},
    "stream_records": 13_300,
    "stream_enabled_one": 13_300,
    "primitive_type_5_nodes": 13_006,
    "index_width_distribution": {"16": 13_003, "32": 3},
    "mesh_descriptor_count_one_nodes": 13_006,
    "dram_only_scne": 504,
    "dram_vram_scne": 799,
    "scne_sram_part_count": 0,
    "matrix_semantic_variants": 49,
    "hierarchy_semantic_variants": 8,
    "scenes_with_portme": 57,
}


def _field(offset: int, size: int, name: str, storage: str, status: str, rule: str) -> dict[str, Any]:
    return {
        "offset_bytes": offset,
        "size_bytes": size,
        "name": name,
        "storage": storage,
        "status": status,
        "rule": rule,
    }


def _source_pin_rows() -> list[dict[str, Any]]:
    return [{"id": key, **copy.deepcopy(value)} for key, value in SOURCE_PINS.items()]


def build_spec() -> dict[str, Any]:
    """Return the complete canonical v1 specification without reading retail data."""

    return {
        "schema": SCHEMA,
        "spec_version": 1,
        "title": "All-Pro Football 2K8 Xbox 360 static SCNE serializer specification",
        "status": "read grammar, full draw/index coupling, the pinned node17 same-count POSITION writer, its same-footprint topology writer, and the catalog-backed POSITION dispatcher for 77 additional outer14/inner8 structural-static candidates are proved offline; no general SCNE dispatcher, runtime rigidity, changed-count, material authoring, hardware, or production-import claim",
        "game": {
            "title": "All-Pro Football 2K8",
            "platform": "Xbox 360",
            "region_evidence": "USA retail archive identity",
            "source_volume_identity_sha256": CORPUS_FACTS["retail_0a_sha256"],
        },
        "data_policy": {
            "contains_retail_geometry": False,
            "contains_retail_vertex_values": False,
            "contains_retail_index_values": False,
            "contains_retail_stream_payloads": False,
            "contains_retail_archive_bytes": False,
            "allowed_evidence": "format constants, aggregate counts, hashes, field offsets, algorithms, and claim boundaries only",
        },
        "scope": {
            "closed_read_contracts": [
                "IFF/H7A ownership and decompressed file-part boundaries",
                "big-endian SCNE envelope and bounded pointer traversal",
                "0xB0 mesh-node table and variable hierarchy-table extent",
                "0x40 vertex declarations and stream/byte-offset layout fields",
                "single mesh descriptor with one to three exact-size streams",
                "POSITION0 decode for every retail node in three formats",
                "BE16/BE32 triangle-strip index validation and read-side expansion",
            ],
            "specified_write_contracts": [
                "same_count_position_only/v1",
                "outer14_inner8_node17_four_be16_strip/v1",
            ],
            "implemented_write_targets": [
                "outer14/inner8/stadium/node17/polySurface19930: four FLOAT32x3 positions through the pinned v1 writer",
                "outer14/inner8/stadium/node17/polySurface19930: one fixed four-element BE16 strip through the invariant-preserving same-footprint topology writer",
                "all 77 additional targets in the frozen outer14/inner8 stadium hashes-only catalog: exact catalog-derived same-count FLOAT32x3 positions through the v2 dispatcher",
            ],
            "catalog_backed_implemented_write_target_count": 77,
            "not_closed": [
                "changed vertex count or changed topology outside the pinned node17 same-footprint profile",
                "draw-record rewriting outside the invariant-preserving node17 profile or material serialization",
                "UV, normal, tangent, color, blend-index, or blend-weight authoring",
                "matrix, skeleton, inverse-bind, morph, attachment, or animation serialization",
                "general SCNE relocation or size-changing file-part repacking",
                "runtime visibility, Xbox 360 hardware acceptance, or production-quality mesh import",
            ],
        },
        "source_pins": _source_pin_rows(),
        "corpus_proof": copy.deepcopy(CORPUS_FACTS),
        "byte_conventions": {
            "scne_scalar_byte_order": "big-endian",
            "scne_float_byte_order": "big-endian IEEE-754 binary32",
            "scne_name_encoding": "UTF-16BE NUL-terminated",
            "iff_scalar_byte_order": "big-endian except little-endian name-footer payload",
            "h7a_match_word_byte_order": "big-endian",
            "one_based_self_relative_pointer": {
                "storage": "u32 in the containing structure's byte order",
                "null_value": 0,
                "non_null_target_formula": "target_offset = pointer_field_offset + stored_u32 - 1",
                "encode_formula": "stored_u32 = target_offset - pointer_field_offset + 1",
                "writer_rule": "reject zero where a required table/string/stream pointer has nonzero count; reject target outside its owning decompressed part",
            },
        },
        "container_ownership": {
            "outer_archive": {
                "allocation_model": "each outer entry has a fixed indexed allocation; this profile may replace only a copied entry with exactly the same byte length",
                "writer_requirements": [
                    "never open the user-supplied source volume for write",
                    "copy all source volumes before mutation",
                    "preserve every byte outside the selected outer allocation",
                    "reject a rebuilt active IFF plus footer that exceeds the selected allocation",
                    "reject nonzero allocation-tail bytes unless a separately proved rule explains and preserves them",
                    "do not borrow slack from the following entry or move another outer entry",
                ],
            },
            "iff": {
                "magic_u32be": 4_282_118_036,
                "magic_hex": "0xff3bef94",
                "header_size_bytes": 32,
                "header_fields": [
                    _field(0x00, 4, "magic", "u32be", "proved", "must equal 0xff3bef94"),
                    _field(0x04, 4, "header_size", "u32be", "proved", "bounds header, block descriptors, pointer table, file descriptors, and header padding"),
                    _field(0x08, 4, "file_length_excluding_name_footer", "u32be", "proved", "end of stored block body and start of name footer"),
                    _field(0x0C, 4, "zero", "u32be", "observed", "preserve exactly; retail parser requires no authored semantic"),
                    _field(0x10, 4, "block_count", "u32be", "proved", "number of 0x20-byte block descriptors"),
                    _field(0x14, 4, "block_table_pointer", "relptr_u32be", "proved", "must resolve to +0x20"),
                    _field(0x18, 4, "file_count", "u32be", "proved", "number of file pointers and packed file descriptors"),
                    _field(0x1C, 4, "file_pointer_table", "relptr_u32be", "proved", "must resolve immediately after block descriptors"),
                ],
                "block_descriptor": {
                    "size_bytes": 32,
                    "fields": [
                        _field(0x00, 4, "name_hash", "u32be", "proved_identity", "CRC32 label when known; preserve"),
                        _field(0x04, 4, "type_hash", "u32be", "proved_identity", "CRC32 label when known; preserve"),
                        _field(0x08, 4, "alignment_or_flags", "u32be", "unknown", "preserve bit-exact"),
                        _field(0x0C, 4, "uncompressed_length", "u32be", "proved", "fixed for same-count profile"),
                        _field(0x10, 4, "codec_field", "u32be", "partly_proved", "must equal H7A wrapper field and be preserved"),
                        _field(0x14, 4, "stored_start_offset", "u32be", "proved", "may be recomputed during same-entry block packing"),
                        _field(0x18, 4, "stored_length", "u32be", "proved", "includes H7A wrapper when compressed"),
                        _field(0x1C, 4, "indexed", "u32be", "unknown", "preserve bit-exact"),
                    ],
                    "known_block_hashes": {
                        "DRAM": "0xbb05a9c1",
                        "VRAM": "0x411536d5",
                        "SRAM": "0x76cbc6e7",
                    },
                },
                "file_pointer_and_descriptor": {
                    "file_pointer_table_entry": "one relptr_u32be per file; each must resolve to the next packed descriptor",
                    "descriptor_prefix_size_bytes": 12,
                    "fields": [
                        _field(0x00, 4, "file_id", "u32be", "proved_identity", "CRC32(exact ASCII name)"),
                        _field(0x04, 4, "type_hash", "u32be", "proved_identity", "CRC32(exact ASCII type); SCNE is 0xe26c9b5d"),
                        _field(0x08, 4, "offset_count", "u32be", "proved", "must be <= block_count"),
                        _field(0x0C, 0, "decompressed_block_offsets", "offset_count*u32be", "proved", "one offset per represented block; 0xffffffff means absent part"),
                    ],
                    "absent_part_sentinel_u32": 4_294_967_295,
                    "part_range_derivation": [
                        "for one decompressed block, retain files whose represented offset is not 0xffffffff",
                        "sort those files by decompressed offset",
                        "part.start is that file's offset",
                        "part.end is the next present file's offset or the block uncompressed_length",
                        "require 0 <= start <= end <= uncompressed_length",
                    ],
                },
                "scne_part_ownership": {
                    "system_part": "every one of 1,303 SCNE files owns exactly one DRAM part; the SCNE grammar and vertex streams parsed here live wholly inside that part",
                    "additional_parts": "799 SCNE files also own one VRAM part; 504 are DRAM-only; no retail SCNE owns an SRAM part",
                    "three_block_packages": "SRAM may still exist as a sibling block in the containing IFF, and block ordering is not globally fixed; resolve ownership by block hash/descriptor, never by assuming block index 1 is VRAM",
                    "position_write_owner": "only the selected SCNE DRAM part and only its proved POSITION0 component byte lanes",
                    "mandatory_preservation": [
                        "selected SCNE VRAM part, if present",
                        "every SRAM block and every file part that occupies it",
                        "all nonselected file parts sharing the changed DRAM block",
                        "all bytes of the selected SCNE DRAM part outside approved POSITION0 lanes",
                        "all other decompressed blocks and their stored bytes where their start offsets need not move",
                    ],
                },
                "name_footer": {
                    "magic_u32be": 2_853_639_446,
                    "magic_hex": "0xaa171516",
                    "payload_size_at_footer_plus_4": "u32le",
                    "payload_byte_order": "little-endian",
                    "names": "UTF-16LE NUL-terminated",
                    "pointer_rule": "one-based self-relative u32le",
                    "write_rule": "footer bytes must remain bit-exact; footer may move only because preceding stored block lengths changed",
                },
            },
            "h7a": {
                "magic_u32be": 239_613_891,
                "magic_hex": "0x0e4837c3",
                "wrapper_size_bytes": 20,
                "wrapper_fields": [
                    _field(0x00, 4, "magic", "u32be", "proved", "must equal 0x0e4837c3"),
                    _field(0x04, 4, "uncompressed_length", "u32be", "proved", "must equal IFF descriptor uncompressed_length"),
                    _field(0x08, 4, "stored_length_including_wrapper", "u32be", "proved", "must equal IFF descriptor stored_length"),
                    _field(0x0C, 4, "codec_field", "u32be", "partly_proved", "must equal and preserve IFF descriptor codec_field"),
                    _field(0x10, 4, "window_shift", "u32be", "proved_transport", "1..15; preserve retail value"),
                ],
                "token_grammar": {
                    "descriptor": "one byte, least-significant bit first, at most eight following tokens",
                    "literal_flag": 0,
                    "literal_payload": "one byte",
                    "match_flag": 1,
                    "match_payload": "one u16be word",
                    "distance_formula": "word & ((1 << shift) - 1)",
                    "length_formula": "((word >> shift) & ((1 << (16 - shift)) - 1)) + 3",
                    "decode_invariants": [
                        "distance >= 1 and distance <= bytes already emitted",
                        "no match may overrun declared uncompressed length",
                        "decoder must emit exactly declared uncompressed length",
                        "remaining stored payload bytes, if any, must all be zero",
                    ],
                },
                "changed_block_rebuild_rule": [
                    "preserve window_shift and codec_field",
                    "require encode then independent decode to reproduce the intended decompressed block byte-for-byte",
                    "update only stored_length/start offsets/file_length fields required by repacking",
                    "reject if active IFF plus exact footer exceeds fixed outer allocation",
                ],
                "no_op_rule": "do not recompress; return the original outer-entry bytes verbatim",
            },
        },
        "scne": {
            "system_part": {
                "minimum_header_bytes": 100,
                "byte_order": "big-endian",
                "fields": [
                    _field(0x00, 4, "root_name", "relptr_u32be", "proved", "UTF-16BE name equals exact inner resource name"),
                    _field(0x04, 0x38, "unknown_04_3b", "opaque", "unknown", "preserve bit-exact"),
                    _field(0x3C, 4, "matrix_count", "u32be", "proved_extent", "count of 0x40-byte matrix-like records; ownership not proved"),
                    _field(0x40, 4, "matrices", "relptr_u32be", "proved_extent", "matrix_count * 0x40 bytes"),
                    _field(0x44, 4, "mesh_node_count", "u32be", "proved", "count of 0xB0-byte mesh nodes"),
                    _field(0x48, 4, "mesh_nodes", "relptr_u32be", "proved", "mesh_node_count * 0xB0 bytes"),
                    _field(0x4C, 0x18, "unknown_4c_63", "opaque", "unknown", "preserve bit-exact"),
                ],
                "matrix_record": {
                    "size_bytes": 64,
                    "observed_shape": "normally 16 big-endian float32 words",
                    "status": "extent proved; transform/bounds/camera/bind ownership unknown",
                    "variant_warning": "49 scenes contain 104 non-finite components; never normalize, repair, or rewrite them",
                },
            },
            "mesh_node": {
                "size_bytes": 176,
                "fields": [
                    _field(0x00, 4, "name", "relptr_u32be", "proved", "UTF-16BE NUL-terminated"),
                    _field(0x04, 4, "name_crc32", "u32be", "proved", "CRC32(exact ASCII name)"),
                    _field(0x08, 4, "unknown_08", "opaque_u32be", "unknown", "preserve bit-exact"),
                    _field(0x0C, 4, "type_or_flags_0c", "opaque_u32be", "unknown", "preserve bit-exact"),
                    _field(0x10, 4, "hash_10", "opaque_u32be", "unknown", "preserve bit-exact"),
                    _field(0x14, 0x4C, "unknown_14_5f", "opaque", "unknown", "preserve bit-exact"),
                    _field(0x60, 4, "hierarchy_count", "u32be", "proved_extent", "retail range 1..109"),
                    _field(0x64, 4, "hierarchy", "relptr_u32be", "proved_extent", "hierarchy_count * 0x30 bytes"),
                    _field(0x68, 0x14, "unknown_68_7b", "opaque", "unknown", "preserve bit-exact"),
                    _field(0x7C, 4, "draw_record_count", "u32be", "proved_extent", "retail range 1..206"),
                    _field(0x80, 4, "draw_records", "relptr_u32be", "proved", "draw_record_count * 0x30; complete field layout and index-window coupling are specified below"),
                    _field(0x84, 4, "mesh_descriptor_count", "u32be", "proved", "exactly 1 in all 13,006 retail nodes"),
                    _field(0x88, 4, "mesh_descriptor", "relptr_u32be", "proved_extent", "one variable descriptor in retail corpus"),
                    _field(0x8C, 0x0C, "unknown_8c_97", "opaque", "unknown", "preserve bit-exact"),
                    _field(0x98, 4, "vertex_declaration_count", "u32be", "proved", "count of 0x40-byte records"),
                    _field(0x9C, 4, "vertex_declarations", "relptr_u32be", "proved", "vertex_declaration_count * 0x40"),
                    _field(0xA0, 4, "unknown_a0", "opaque_u32be", "unknown", "preserve bit-exact"),
                    _field(0xA4, 4, "index_component_bits", "u32be", "proved", "16 or 32"),
                    _field(0xA8, 4, "index_count", "u32be", "proved", "number of serialized strip elements including restart values"),
                    _field(0xAC, 4, "index_buffer", "relptr_u32be", "proved", "index_count * (index_component_bits / 8)"),
                ],
            },
            "hierarchy_table": {
                "header_size_bytes": 0,
                "header_status": "no separate header; the first two float4 values belong to record 0",
                "record_core_size_bytes": 16,
                "ordinary_record_size_bytes": 48,
                "byte_length_formula": "count * 0x30",
                "terminal_rule": "all records, including the last, contain vector_a and vector_b",
                "core_fields": [
                    _field(0x00, 16, "vector_a", "4*f32be", "unknown", "present in every record; preserve bit-exact"),
                    _field(0x10, 16, "vector_b", "4*f32be", "unknown", "present in every record; preserve bit-exact"),
                    _field(0x20, 4, "name", "relptr_u32be", "proved", "UTF-16BE NUL-terminated"),
                    _field(0x24, 4, "name_crc32", "u32be", "proved", "CRC32(exact ASCII name)"),
                    _field(0x28, 2, "parent", "i16be", "proved_graph", "-1 or record index"),
                    _field(0x2A, 2, "first_child", "i16be", "proved_graph", "-1 or record index"),
                    _field(0x2C, 2, "next_sibling", "i16be", "proved_graph", "-1 or record index"),
                    _field(0x2E, 2, "reserved", "u16be", "unknown", "preserve bit-exact"),
                ],
                "claim_boundary": "names and graph links are proved; skeleton, joint palette, attachment socket, bind matrix, inverse bind, and runtime transform meanings are not",
                "variants": "eight tables fail the common child/sibling-versus-parent identity; preserve all signed indices and reject hierarchy authoring",
            },
            "draw_record": {
                "size_bytes": 48,
                "count_corpus": 47_112,
                "status": "field layout and index-window coupling proved across the complete retail corpus; selected renderer forwarding and material-slot stride proved from XEX code",
                "fields": [
                    _field(0x00, 4, "draw_primitive_code", "u32be", "proved_renderer_and_corpus", "6 in every retail draw; forwarded to native submission; separate enum domain from descriptor primitive 5"),
                    _field(0x04, 4, "first_element", "u32be", "proved_renderer_and_corpus", "first serialized index element; sorted draw windows exactly partition the node index payload"),
                    _field(0x08, 4, "element_count", "u32be", "proved_renderer_and_corpus", "serialized elements in this draw including restart values; at least 3"),
                    _field(0x0C, 4, "primitive_capacity", "u32be", "proved_corpus", "element_count - 2; not restart/degenerate-filtered triangle count"),
                    _field(0x10, 4, "base_vertex", "u32be", "proved_renderer_and_corpus", "forwarded to indexed submission; zero in all 47,112 retail draws"),
                    _field(0x14, 4, "minimum_vertex", "u32be", "proved_corpus", "minimum non-restart index inside this draw window"),
                    _field(0x18, 4, "vertex_range", "u32be", "proved_corpus", "maximum non-restart index - minimum_vertex + 1"),
                    _field(0x1C, 4, "optional_draw_state", "relptr_u32be_or_null", "partly_proved", "46,348 null; all 764 non-null targets are in-system and 8-byte aligned; relocated/runtime value is forwarded but payload meaning is unknown"),
                    _field(0x20, 4, "material_slot", "u32be", "proved_renderer", "material address = instance material base + slot * 0xf0; retail slots 0..242"),
                    _field(0x24, 4, "reserved_24", "u32be", "proved_zero_corpus", "zero in every retail draw; preserve"),
                    _field(0x28, 4, "reserved_28", "u32be", "proved_zero_corpus", "zero in every retail draw; preserve"),
                    _field(0x2C, 4, "render_flags_2c", "u32be", "observed", "retail values 0..3; exact meaning unknown; preserve"),
                ],
                "window_contract": [
                    "sort records by first_element; windows begin at zero, are contiguous and nonoverlapping, and end at node.index_count",
                    "first_element + element_count never exceeds node.index_count",
                    "primitive_capacity equals element_count - 2 even when restart or repeated-index degenerates reduce emitted triangles",
                    "minimum_vertex and vertex_range derive from non-restart elements before base_vertex",
                ],
                "write_rule": "preserve all 48 bytes unless a separately specified profile proves every affected derived field; the pinned same-footprint node17 permutation preserves all derived fields and therefore forbids draw mutation",
                "remaining_unknowns": [
                    "optional_draw_state payload meaning",
                    "render_flags_2c bit meanings",
                    "shader, sampler, and TXTR binding behind material objects",
                    "bounds/culling coupling",
                ],
            },
            "vertex_declaration": {
                "size_bytes": 64,
                "fields": [
                    _field(0x00, 4, "indexed_semantic_crc", "u32be", "proved_identity", "CRC32 such as POSITION0"),
                    _field(0x04, 4, "semantic_crc", "u32be", "proved_identity", "CRC32 such as POSITION"),
                    _field(0x08, 4, "layout_word", "u32be", "partly_proved", "stream and byte-offset subfields; preserve other bits"),
                    _field(0x0C, 4, "format_code", "u32be", "proved_dispatch", "XEX Function_84B8BE00 format selector"),
                    _field(0x10, 16, "vector_10", "4*f32be", "partly_proved", "POSITION normalized formats use xyz as center; otherwise preserve"),
                    _field(0x20, 16, "vector_20", "4*f32be", "partly_proved", "POSITION normalized formats use xyz as scale; otherwise preserve"),
                    _field(0x30, 16, "vector_30", "4*f32be", "unknown", "preserve bit-exact"),
                ],
                "layout_word": {
                    "stream_index": {"bit_offset": 8, "bit_count": 8, "decode": "(layout >> 8) & 0xff"},
                    "byte_offset": {"bit_offset": 16, "bit_count": 8, "decode": "(layout >> 16) & 0xff"},
                    "unknown_preserve_mask_hex": "0xff0000ff",
                    "writer_rule": "never reconstruct the word from only named fields; preserve the full source word",
                },
                "position_identity": {
                    "indexed_semantic": "POSITION0",
                    "indexed_semantic_crc32_hex": "0x46e6cb71",
                    "semantic": "POSITION",
                    "semantic_crc32_hex": "0x801f78b9",
                },
            },
            "mesh_descriptor": {
                "minimum_prefix_size_bytes": 20,
                "byte_length_formula": "0x14 + stream_count * 0x18",
                "fields": [
                    _field(0x00, 4, "unknown_00", "opaque_u32be", "unknown", "preserve bit-exact"),
                    _field(0x04, 4, "optional_pointer_raw", "opaque_u32be", "unknown", "do not resolve or rewrite without loader proof"),
                    _field(0x08, 4, "vertex_count", "u32be", "proved", "must equal each stream byte_length / stride"),
                    _field(0x0C, 4, "packed_stream_count", "u32be", "partly_proved", "high 16 bits are stream_count; preserve low 16 bits"),
                    _field(0x10, 4, "primitive_type", "u32be", "proved_corpus", "5 in all retail nodes; read as D3DPT_TRIANGLESTRIP"),
                ],
                "stream_count_decode": "(packed_stream_count >> 16) & 0xffff",
                "stream_count_retail_distribution": {"1": 12_713, "2": 292, "3": 1},
                "stream_record": {
                    "size_bytes": 24,
                    "fields": [
                        _field(0x00, 4, "flags", "opaque_u32be", "unknown", "preserve bit-exact"),
                        _field(0x04, 4, "enabled", "u32be", "observed", "1 in all 13,300 retail stream records; preserve"),
                        _field(0x08, 4, "stride", "u32be", "proved", "nonzero"),
                        _field(0x0C, 4, "byte_length", "u32be", "proved", "vertex_count * stride"),
                        _field(0x10, 4, "start", "relptr_u32be", "proved", "first payload byte"),
                        _field(0x14, 4, "end", "relptr_u32be", "proved", "one-past-last payload byte"),
                    ],
                    "invariants": [
                        "end >= start",
                        "end - start == byte_length",
                        "byte_length == vertex_count * stride",
                        "both resolved targets are within the selected SCNE DRAM part, allowing end == part length",
                    ],
                },
            },
            "position0_formats": [
                {
                    "format_code": 2_761_657,
                    "format_code_hex": "0x002a23b9",
                    "name": "float32x3",
                    "element_size_bytes": 12,
                    "retail_node_count": 12_416,
                    "decode_raw": "x,y,z = three consecutive f32be values; reject non-finite values",
                    "declaration_transform": "none; vector_10/vector_20/vector_30 remain preserved metadata",
                    "xex_inverse": "write three native Xbox 360 binary32 values; serialized bytes are big-endian",
                    "safe_inverse": [
                        "require exactly three finite input components",
                        "convert each component to IEEE-754 binary32 and reject overflow/non-finite result",
                        "write exactly 12 bytes at POSITION0 byte_offset for the same vertex",
                        "decode back from the patched bytes and require exact equality to the accepted binary32 values",
                    ],
                    "preserved_lanes": "all bytes in the stride outside these 12 bytes",
                },
                {
                    "format_code": 1_712_474,
                    "format_code_hex": "0x001a215a",
                    "name": "snorm16x4",
                    "element_size_bytes": 8,
                    "retail_node_count": 365,
                    "raw_layout": "four consecutive i16be lanes x,y,z,w",
                    "decode_snorm": "signed = int16(raw); normalized = max(signed, -32767) / 32767.0",
                    "decode_position": "position.xyz = vector_10.xyz + normalized.xyz * vector_20.xyz",
                    "xex_inverse": "for each supplied normalized lane: clamp [-1,1], multiply by 32767, truncate toward zero, store i16be",
                    "safe_xyz_inverse": [
                        "require finite position, finite center, and strictly positive finite scale for x/y/z",
                        "normalized = (position - center) / scale",
                        "reject normalized outside [-1,1] before clamping; never silently clamp an edited position",
                        "quantized = trunc(normalized * 32767) toward zero",
                        "write only x/y/z i16be lanes",
                        "preserve the source w lane bytes at element offsets +6..+7",
                        "decode back and require per-axis error <= scale / 32767 plus one binary32 ULP",
                    ],
                    "noncanonical_raw_minimum": "source -32768 decodes as -1.0; a no-op must preserve it instead of canonicalizing to -32767",
                },
                {
                    "format_code": 2_761_095,
                    "format_code_hex": "0x002a2187",
                    "name": "snorm10_10_10",
                    "element_size_bytes": 4,
                    "retail_node_count": 225,
                    "raw_layout": {"x_bits": [0, 9], "y_bits": [10, 19], "z_bits": [20, 29], "unknown_bits_preserved": [30, 31]},
                    "decode_snorm": "sign-extend each 10-bit lane; normalized = max(signed, -511) / 511.0",
                    "decode_position": "position.xyz = vector_10.xyz + normalized.xyz * vector_20.xyz",
                    "xex_inverse": "clamp xyz [-1,1], multiply by 511, truncate toward zero, mask each to 10 bits, pack x | (y << 10) | (z << 20)",
                    "safe_xyz_inverse": [
                        "require finite position, finite center, and strictly positive finite scale for x/y/z",
                        "normalized = (position - center) / scale",
                        "reject normalized outside [-1,1] before clamping; never silently clamp an edited position",
                        "quantized = trunc(normalized * 511) toward zero",
                        "replace bits 0..29 with the three masked lanes while preserving source bits 30..31",
                        "decode back and require per-axis error <= scale / 511 plus one binary32 ULP",
                    ],
                    "noncanonical_raw_minimum": "source signed -512 decodes as -1.0; a no-op must preserve it instead of canonicalizing to -511",
                },
            ],
            "index_strip": {
                "component_width_field": "mesh_node +0xa4",
                "component_byte_order": "big-endian",
                "supported_widths": [
                    {"bits": 16, "bytes": 2, "restart_value": 65_535, "retail_nodes": 13_003},
                    {"bits": 32, "bytes": 4, "restart_value": 4_294_967_295, "retail_nodes": 3},
                ],
                "primitive_type": 5,
                "primitive_name": "D3DPT_TRIANGLESTRIP",
                "read_algorithm": [
                    "restart value clears the current strip",
                    "after the first two elements, emit (a,b,c) for even triangle number and (b,a,c) for odd triangle number",
                    "omit triangles whose three indices are not distinct",
                    "require every non-restart index < vertex_count",
                ],
                "write_claim": "same_count_position_only/v1 preserves every index byte; outer14_inner8_node17_four_be16_strip/v1 may replace only the existing four-element BE16 allocation with a permutation of 0,1,2,3 while preserving all draw fields",
            },
        },
        "write_profiles": {
            "same_count_position_only/v1": {
                "purpose": "first fail-closed structural boundary for edited raw-coordinate static-candidate geometry",
                "implementation_status": "implemented for the pinned node17 target and all 77 additional targets authorized by the frozen outer14 stadium hashes-only catalog; no general SCNE or non-FLOAT32x3 dispatcher",
                "implemented_target": {
                    "outer_table_index": 14,
                    "physical_pack": "1A",
                    "inner_file_index": 8,
                    "inner_name": "stadium",
                    "node_index": 17,
                    "node_name": "polySurface19930",
                    "vertex_count": 4,
                    "format": "FLOAT32x3_BE",
                    "stream_stride_bytes": 24,
                    "authorized_lane_bytes": 48,
                    "catalog_eligible_node_dispatch_implemented": True,
                },
                "catalog_dispatcher": {
                    "recipe_schema": "apf2k8_scne_catalog_position_recipe/v2",
                    "catalog_schema": "apf2k8_stadium_static_position_target_catalog/v1",
                    "catalog_sha256": "c3122019b74645380052670f9fdce389277a454b440dd7b7f438276b05f57469",
                    "authorized_target_count": 77,
                    "target_scope": "every additional_targets row in the frozen outer14/inner8/stadium catalog",
                    "selection": "canonical target_id; derive exact vertex_count, stream_index, stream_start, stride, byte_offset, lane width, format, and structural hashes from the catalog",
                    "implemented_format": "FLOAT32x3_BE only",
                    "independent_verifier_imports_writer": False,
                    "general_scne_dispatch_implemented": False,
                },
                "runtime_status": "unproved",
                "input_contract": [
                    "selected retail identity and every evidence/layout invariant must match this spec",
                    "exactly one existing mesh node and its POSITION0 declaration are selected",
                    "input has exactly vertex_count finite XYZ positions in original serialized vertex order",
                    "node contains neither BLENDINDICES* nor BLENDWEIGHT* declarations; this is a structural static-candidate gate, not proof of runtime attachment independence",
                    "position declaration uses one of the three closed formats",
                    "position element is bounded by its stream stride and does not overlap any other declared element lane",
                    "all declaration format sizes needed for overlap checking are known; otherwise reject",
                    "all position payload lanes are disjoint from structural tables, index payload, and other stream payloads except their owning interleaved stream",
                ],
                "allowed_changes": [
                    "float32x3: 12 POSITION0 bytes per vertex",
                    "snorm16x4: first 6 POSITION0 bytes per vertex; preserve w lane",
                    "snorm10_10_10: packed bits 0..29 per vertex; preserve bits 30..31",
                    "IFF block stored offsets/lengths and file_length only as mechanically required by H7A recompression",
                ],
                "forbidden_changes": [
                    "vertex_count, stream_count, stride, byte_length, declarations, layout words, or declaration vectors",
                    "mesh/node/hierarchy/matrix/draw counts, pointers, records, names, hashes, or unknown words",
                    "index width, index count, index payload, restart placement, primitive type, or topology",
                    "normal, tangent, binormal, UV, color, blend, material, shader, sampler, skin, morph, attachment, or animation data",
                    "selected SCNE VRAM bytes, any SRAM bytes, any sibling file part, footer bytes, or bytes outside the selected fixed outer allocation",
                    "growth of any decompressed block, SCNE part, outer allocation, or archive table",
                ],
                "no_op_contract": {
                    "external_identity": "compare imported accessor bytes/values to the exact canonical exported POSITION accessor for the same source proof",
                    "action": "if unchanged, bypass POSITION encoding, H7A encoding, IFF rebuilding, and archive writing",
                    "required_result": "the complete selected outer-entry byte string and copied volume are byte-for-byte identical to source",
                    "reason": "normalized raw minima and H7A tokenization can have multiple equivalent encodings; decode equality is weaker than byte identity",
                },
                "changed_write_verification": [
                    "construct the intended decompressed DRAM block from a source copy and change only approved position lanes",
                    "independently decode every patched POSITION0 and compare to the accepted input under the format-specific bound",
                    "derive a changed-byte interval set and require it to be a subset of approved lanes",
                    "hash every selected-SCNE non-position span and every sibling file part before/after; require equality",
                    "require every selected-SCNE VRAM part, every SRAM block, all other decompressed blocks, and the footer to be byte-identical",
                    "H7A-decode the rebuilt changed block and require byte identity with the intended decompressed block",
                    "reparse the rebuilt IFF and independently re-derive every file-part range",
                    "require identical file IDs, types, counts, offsets in decompressed blocks, uncompressed block lengths, footer payload, and outer allocation length",
                    "require all copied-volume bytes outside the selected outer allocation to retain their source hashes",
                ],
                "failure_policy": "reject on any mismatch, ambiguity, unsupported layout, range escape, alias, count change, allocation overflow, non-finite value, or unverifiable preservation claim",
            },
            "outer14_inner8_node17_four_be16_strip/v1": {
                "purpose": "smallest fail-closed changed-topology boundary with invariant-preserving draw coupling",
                "implementation_status": "offline copied-volume writer and writer-independent verifier implemented for exactly one target; runtime unproved",
                "implemented_target": {
                    "outer_table_index": 14,
                    "physical_pack": "1A",
                    "inner_file_index": 8,
                    "inner_name": "stadium",
                    "node_index": 17,
                    "node_name": "polySurface19930",
                    "vertex_count": 4,
                    "index_component_bits": 16,
                    "index_count": 4,
                    "index_allocation_bytes": 8,
                    "draw_record_count": 1,
                },
                "runtime_status": "unproved",
                "input_contract": [
                    "recipe and every source/profile hash match the pinned schema and retail identity",
                    "recipe contains exactly four JSON integers and no additional topology fields",
                    "indices are exactly one permutation of 0,1,2,3 with no restart or duplicate",
                    "native triangle-strip decode emits exactly two nondegenerate triangles",
                    "the one draw remains first=0, count=4, capacity=2, base=0, minimum=0, range=4",
                    "the existing eight-byte BE16 allocation stays at its source offset and no structural extent changes",
                ],
                "allowed_changes": [
                    "only the eight decoded index-buffer bytes may differ inside the selected SCNE",
                    "IFF stored offsets/lengths and file_length only as mechanically required by H7A recompression",
                ],
                "forbidden_changes": [
                    "any draw byte, draw count, pointer, primitive code, material slot, optional state, reserved word, or render flag",
                    "vertex count, stream payload or layout, declaration, descriptor, matrix, hierarchy, node metadata, bounds, or unknown bytes",
                    "index width, index count, allocation size or offset, restart insertion, duplicate index, or degenerate output",
                    "any sibling file part, SCNE VRAM byte, footer byte, fixed outer allocation length, or copied-volume byte outside outer14",
                    "changed vertex count, material/UV/normal authoring, skin/attachment changes, or general SCNE dispatch",
                ],
                "draw_preservation_reason": "all admitted permutations retain every derived draw invariant, so rewriting any of the 48 draw bytes is unnecessary and forbidden",
                "no_op_contract": {
                    "action": "if all four source indices are requested unchanged, bypass H7A encoding and return the original outer-entry and complete copied 1A bytes",
                    "required_result": "zero decoded changes, no recompression, and complete copied-volume byte identity",
                },
                "changed_write_verification": [
                    "independently parse the output container and re-derive the selected SCNE, draw, and eight-byte index span without importing the writer or production parser",
                    "require the output sequence to equal the admitted permutation and re-decode to two nondegenerate strip triangles",
                    "require the changed decoded-byte interval set to be a subset of the eight authorized index bytes",
                    "require the complete draw record, vertex stream, declarations, descriptor, matrix, hierarchy, sibling parts, VRAM, footer, and copied-volume complement to retain exact source hashes",
                    "independently H7A-decode the changed block and require exact intended decompressed bytes",
                    "reject before publication if the recompressed active IFF plus footer exceeds the fixed outer allocation",
                ],
                "failure_policy": "reject any identity, schema, type, count, permutation, decode, invariant, preservation, alias, range, compression, or fixed-allocation mismatch",
            },
        },
        "pinned_implementation_witness": {
            "scope": "outer14/inner8/stadium/node17/polySurface19930 only; exactly four serialized object-space FLOAT32x3 positions",
            "recipe_schema": "apf2k8_scne_same_count_position_recipe/v1",
            "public_recipe_sample": "four all-zero nonretail authored positions",
            "retail_or_retail_derived_recipe_coordinates_committed": False,
            "full_proof_recipe_policy": "derive from the user-owned source into temporary paths; retain hashes and metrics only",
            "physical_input_output_pack": "source complete game directory indexed by 0A; copied sibling 1A only",
            "fixed_outer_allocation_bytes": 12_931_072,
            "no_op": {
                "complete_1a_byte_identical": True,
                "source_and_output_1a_sha256": "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
                "source_and_output_outer_sha256": "347503ffdcd910b57425584869e1520238b1298e516f643936568b83d5a5a07a",
                "h7a_recompressed": False,
            },
            "changed_plus_1_2_3": {
                "operation": "add +1 X, +2 Y, +3 Z to all four authored positions",
                "output_1a_sha256": "6f275ccb780acfee0cba9cd59c38e4bb2aedb18d01dec7030d61546441026b40",
                "output_outer_sha256": "89ec32ee6da2a73f494667c01aa8ea9968c49c97317ec85d3c0342c84eb632fa",
                "output_stadium_dram_sha256": "6ccfc27ed46491961378fc170409d9e183bcb3302ccc444be80f8e710821b02a",
                "changed_decoded_dram_bytes": 14,
                "authorized_lane_bytes": 48,
                "block0_stored_length_before": 3_299_082,
                "block0_stored_length_after": 3_299_717,
                "allocation_slack_after_bytes": 1_391,
            },
            "preservation": {
                "uv_normal_interleaves_exact": True,
                "matrix_hierarchy_draw_index_declarations_descriptor_exact": True,
                "iff_header_complement_and_file_descriptors_exact": True,
                "stadium_vram_exact": True,
                "sibling_parts_exact": 11,
                "non_target_parts_exact": 12,
                "block1_stored_footer_tail_and_pack_complement_exact": True,
                "independent_verifier_imports_production_writer_or_parsers": False,
            },
            "claim_boundary": "this pinned POSITION witness proves offline bytes for one target only; catalog dispatch is established separately by the v2 witness; it does not itself prove topology, rigid attachment, runtime visibility, material/UV/skin authoring, general SCNE dispatch, or production import",
        },
        "catalog_dispatcher_implementation_witness": {
            "scope": "all 77 frozen-catalog additional targets are structurally authorized for exact same-count FLOAT32x3_BE POSITION0 replacement; node3 is the second complete byte-level witness",
            "recipe_schema": "apf2k8_scne_catalog_position_recipe/v2",
            "public_recipe_sample": "node3 with 24 all-zero nonretail authored positions",
            "retail_or_retail_derived_recipe_coordinates_committed": False,
            "full_no_op_recipe_policy": "derive exact retail node3 positions only into a caller-owned temporary path; print and retain hashes/metrics only",
            "physical_input_output_pack": "source complete game directory indexed by 0A; copied sibling 1A only",
            "fixed_outer_allocation_bytes": 12_931_072,
            "no_op": {
                "complete_1a_byte_identical": True,
                "source_and_output_1a_sha256": "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
                "source_and_output_outer_sha256": "347503ffdcd910b57425584869e1520238b1298e516f643936568b83d5a5a07a",
                "h7a_recompressed": False,
            },
            "changed_all_zero_node3": {
                "target_id": "outer14.inner8.node3",
                "node_name": "polySurface19821",
                "vertex_count": 24,
                "draw_record_count": 3,
                "operation": "replace all 24 positions with the public nonretail all-zero witness",
                "output_1a_sha256": "cf8cd039e6ef3f078f193c1563bce76d3983372cd67b30a0b051487699378022",
                "output_outer_sha256": "23e15b372b7e3be49a2b0a475232c4f44b9c4de9d4a7a572e5e98a8df9d7af9e",
                "output_stadium_dram_sha256": "af1efab4cab214ef796258d685eeb5fd9608c3ee238147fde610bd3eeac0b4c1",
                "changed_decoded_block0_bytes": 284,
                "authorized_lane_bytes": 288,
                "block0_stored_length_before": 3_299_082,
                "block0_stored_length_after": 3_279_201,
                "allocation_slack_after_bytes": 21_907,
            },
            "preservation": {
                "target_stream_non_position_interleaves_exact": True,
                "all_scne_bytes_outside_selected_position_lanes_exact": True,
                "node_matrix_hierarchy_draw_index_declarations_descriptor_exact": True,
                "iff_header_complement_and_file_descriptors_exact": True,
                "stadium_vram_exact": True,
                "sibling_parts_exact": 11,
                "non_target_parts_exact": 12,
                "block1_stored_footer_tail_and_pack_complement_exact": True,
                "independent_verifier_imports_any_position_writer": False,
                "independent_verifier_rederives_manifest_every_field": True,
            },
            "refusals": {
                "wrong_catalog_hash_target_or_count": True,
                "allocation_overflow": True,
                "symlink_or_hardlink_alias": True,
                "unsafe_publication_path_replacement": True,
                "forbidden_structural_mutation": True,
            },
            "claim_boundary": "catalog-backed same-count FLOAT32x3 dispatcher and node3 offline bytes proved; this POSITION witness does not prove topology/count changes, runtime rigidity or visibility, material/UV/skin authoring, hardware acceptance, general SCNE dispatch, or production import",
        },
        "pinned_same_footprint_topology_implementation_witness": {
            "scope": "outer14/inner8/stadium/node17/polySurface19930 only; exactly four serialized BE16 strip elements inside the existing eight-byte allocation",
            "profile": "outer14_inner8_node17_four_be16_strip/v1",
            "recipe_schema": "apf2k8_scne_same_footprint_topology_recipe/v1",
            "public_recipe_sample": "nonretail permutation of 0,1,2,3; no retail sequence is committed",
            "physical_input_output_pack": "source complete game directory indexed by 0A; copied sibling 1A only",
            "fixed_outer_allocation_bytes": 12_931_072,
            "draw_coupling": {
                "draw_record_bytes_preserved": 48,
                "reason": "every admitted permutation retains first=0, count=4, capacity=2, base=0, minimum=0, range=4",
                "material_slot_preserved": True,
                "optional_draw_state_preserved": True,
                "render_flags_preserved": True,
            },
            "no_op": {
                "complete_1a_byte_identical": True,
                "source_and_output_1a_sha256": "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
                "source_and_output_outer_sha256": "347503ffdcd910b57425584869e1520238b1298e516f643936568b83d5a5a07a",
                "changed_decoded_dram_bytes": 0,
                "h7a_recompressed": False,
            },
            "changed_nonretail_permutation": {
                "authorized_index_bytes": 8,
                "changed_decoded_dram_bytes": 2,
                "native_triangle_count": 2,
                "native_degenerate_triangle_count": 0,
                "output_1a_sha256": "7768585fdbfa37144f3b153292da16b6f9beb95b4e3b12c15f62e95c98500df9",
                "output_outer_sha256": "c3421aa724ff1e8e991524f0394346d3ac3e4703f14d203fb596d1030258f17d",
                "output_stadium_dram_sha256": "5527a6eac6bf35de5f7aa5cb3521d7a7b967901b93dac109dce51d5de3c6a5cb",
                "output_index_buffer_sha256": "f206bdbe6ccb7e731c14e4f828fc341338dbf5626182ffe99503107f58d375f3",
                "block0_stored_length_before": 3_299_082,
                "block0_stored_length_after": 3_299_705,
                "allocation_slack_after_bytes": 1_403,
            },
            "preservation": {
                "all_decoded_bytes_outside_index_allocation_exact": True,
                "draw_record_exact": True,
                "vertex_stream_exact": True,
                "declarations_descriptor_matrix_hierarchy_node_exact": True,
                "stadium_vram_exact": True,
                "sibling_parts_exact": 11,
                "non_target_parts_exact": 12,
                "stored_block1_footer_and_iff_header_complement_exact": True,
                "all_output_1a_bytes_outside_outer14_exact": True,
                "independent_verifier_imports_topology_writer_or_production_parser": False,
            },
            "claim_boundary": "same-footprint node17 index permutation is byte-proved offline; changed vertex count, draw rewriting, bounds/culling ownership, runtime acceptance, hardware acceptance, and production import remain unproved",
        },
        "outer14_stadium_static_target_catalog": {
            "schema": "apf2k8_stadium_static_position_target_catalog/v1",
            "scope": "outer14/inner8/stadium only; excludes already implemented node17",
            "contains_retail_vertex_values": False,
            "eligible_including_node17": 78,
            "additional_target_count": 77,
            "selection": {
                "position": "one bounded FLOAT32x3 POSITION0 declaration",
                "deformation_gate": "no BLENDINDICES* or BLENDWEIGHT* declarations",
                "topology": "validated BE16/BE32 D3DPT_TRIANGLESTRIP indices",
                "structural_spans": "node, ordinal-correlated matrix slot, hierarchy, draw, index, declarations, descriptor, stream records, payload, and strided position-lane hashes",
                "runtime_rigidity_inferred": False,
            },
            "shared_container_envelope": {
                "inner_part_count": 13,
                "non_target_part_count_per_position_edit": 12,
                "fixed_outer_allocation_bytes": 12_931_072,
                "source_stored_block0_bytes": 3_299_082,
                "maximum_stored_block0_bytes": 3_301_108,
                "source_headroom_bytes": 2_026,
                "overflow_rule": "fail closed before pack write",
            },
            "selected_second_target_handoff": {
                "node_index": 3,
                "node_name": "polySurface19821",
                "vertex_count": 24,
                "draw_record_count": 3,
                "index_count": 32,
                "stream_stride_bytes": 24,
                "authorized_position_lane_bytes": 288,
                "representative_operation": "local-only exact +1 X/+2 Y/+3 Z serialized translation",
                "stored_block0_length_after": 3_299_741,
                "allocation_slack_after_bytes": 1_367,
                "changed_inner_part": "file8/part0 only",
                "historical_catalog_generation_time_writer_complete": False,
                "downstream_catalog_dispatcher_now_implemented": True,
                "downstream_node3_writer_and_independent_verifier_proved": True,
                "runtime_rigid_attachment_proved": False,
                "runtime_visibility_proved": False,
            },
        },
        "known_unknowns": {
            "scne_envelope": ["unknown header ranges", "matrix-table ownership", "non-finite matrix variants", "bounds/culling coupling"],
            "mesh_node": ["type/flag words", "hash_10", "unknown ranges", "optional mesh pointer", "unknown packed-stream low 16 bits"],
            "rendering": ["optional draw-state payload meaning", "render_flags_2c bit meanings", "shader programs", "samplers", "TXTR binding behind material slots", "bounds/culling coupling", "runtime buffer ownership"],
            "attributes": ["complete NORMAL/TANGENT/BINORMAL transforms", "UV conventions and texture channels", "COLOR semantics", "all non-POSITION format inverses in context"],
            "deformation": ["joint palette", "blend-index meaning", "weight normalization", "bind/inverse-bind matrices", "morph target storage", "CurveAnim/SingleMoCap/CDAN binding"],
            "hierarchy_and_attachment": ["which hierarchy records are bones", "attachment/socket rules", "helmet/head attachment", "matrix application order", "runtime parent overrides"],
            "container": ["general size-changing SCNE relocation", "production H7A packing strategy", "runtime memory allocation and 360 memory ceiling effects"],
        },
        "claim_flags": {
            "complete_scne_read_grammar_proved": False,
            "complete_scne_serializer_proved": False,
            "same_count_position_profile_specified": True,
            "same_count_position_writer_implemented": False,
            "pinned_outer14_node17_same_count_position_writer_implemented": True,
            "pinned_outer14_node17_offline_structural_writeback_proved": True,
            "outer14_additional_static_target_catalog_proved": True,
            "outer14_catalog_all_77_targets_structurally_authorized": True,
            "outer14_catalog_same_count_position_dispatcher_implemented": True,
            "pinned_outer14_node3_representative_h7a_rebuild_fit_proved": True,
            "pinned_outer14_node3_writer_implemented": True,
            "pinned_outer14_node3_offline_structural_writeback_proved": True,
            "general_scne_same_count_position_dispatcher_implemented": False,
            "changed_topology_writer_proved": True,
            "pinned_outer14_node17_same_footprint_topology_writer_implemented": True,
            "pinned_outer14_node17_same_footprint_topology_offline_roundtrip_proved": True,
            "general_scne_topology_dispatcher_implemented": False,
            "changed_vertex_count_writer_proved": False,
            "static_runtime_classification_proved": False,
            "skinned_mesh_writer_proved": False,
            "material_uv_writer_proved": False,
            "attachment_rules_proved": False,
            "fixed_allocation_required_by_current_profile": True,
            "no_op_whole_entry_byte_identity_required": True,
            "independent_changed_span_verification_required": True,
            "emulator_runtime_visibility_proved": False,
            "xbox_360_hardware_acceptance_proved": False,
            "production_mesh_importer_proved": False,
        },
        "next_closure_steps": [
            "runtime-witness the pinned outer14/inner8 node17 position and topology edits and the node3 deformation in Xenia",
            "recover matrix and attachment ownership before calling any cataloged node independently rigid",
            "extend beyond the frozen outer14 stadium catalog only after an equally strict hashes-only target derivation and independent byte verifier",
            "generalize topology only through hashes-only target admission plus per-target draw/index re-derivation; retain the pinned node17 profile as the only implemented APF topology target until then",
            "recover bounds/culling, material, and UV ownership before changed-count or textured external-mesh import",
            "recover attachment and skin rules before treating gameplay helmet/head resources as static shells",
        ],
    }


def render_spec() -> bytes:
    return (json.dumps(build_spec(), indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SpecError(f"top level is not an object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SpecError(message)


def _validate_source_pins() -> None:
    for key, pin in SOURCE_PINS.items():
        path = ROOT / str(pin["path"])
        _require(path.is_file(), f"missing evidence source {key}: {path}")
        _require(path.stat().st_size == pin["size_bytes"], f"evidence size drift: {key}")
        _require(_sha256(path) == pin["sha256"], f"evidence SHA-256 drift: {key}")
        if pin["schema"] is not None:
            document = _load_object(path)
            _require(document.get("schema") == pin["schema"], f"evidence schema drift: {key}")


def _validate_evidence_projection() -> None:
    scene = _load_object(ROOT / SOURCE_PINS["scene_inventory"]["path"])
    summary = scene.get("summary")
    _require(isinstance(summary, dict), "scene inventory has no summary object")
    expected_summary = {
        "scne_selected": CORPUS_FACTS["scne_resources"],
        "scne_parsed": CORPUS_FACTS["scne_resources"],
        "scne_failures": CORPUS_FACTS["structural_failures"],
        "scene_nodes": CORPUS_FACTS["mesh_nodes"],
        "hierarchy_records": CORPUS_FACTS["hierarchy_records"],
        "vertex_declarations": CORPUS_FACTS["vertex_declarations"],
        "position_format_counts": CORPUS_FACTS["position_formats"],
        "scenes_with_portme": CORPUS_FACTS["scenes_with_portme"],
    }
    for key, expected in expected_summary.items():
        _require(summary.get(key) == expected, f"scene corpus projection drift: {key}")

    nodes = [node for item in scene.get("scenes", []) for node in item.get("nodes", [])]
    _require(len(nodes) == CORPUS_FACTS["mesh_nodes"], "scene node enumeration drift")
    _require(sum(int(node["draw_record_count"]) for node in nodes) == CORPUS_FACTS["draw_records"], "draw record count drift")
    _require(sum(int(node["index_count"]) for node in nodes) == CORPUS_FACTS["serialized_indices"], "serialized index count drift")
    _require(sum(int(node["meshes"][0]["vertex_count"]) for node in nodes) == CORPUS_FACTS["source_vertices"], "source vertex count drift")
    _require(all(int(node["mesh_descriptor_count"]) == 1 for node in nodes), "mesh descriptor count-one invariant drift")
    _require(all(int(node["meshes"][0]["primitive_type"]) == 5 for node in nodes), "primitive type invariant drift")
    width_counts = {"16": 0, "32": 0}
    stream_counts = {"1": 0, "2": 0, "3": 0}
    stream_records = 0
    for node in nodes:
        width_counts[str(node["index_component_bits"])] += 1
        streams = node["meshes"][0]["streams"]
        stream_counts[str(len(streams))] += 1
        stream_records += len(streams)
        _require(all(int(item["enabled"]) == 1 for item in streams), "stream enabled invariant drift")
    _require(width_counts == CORPUS_FACTS["index_width_distribution"], "index width distribution drift")
    _require(stream_counts == CORPUS_FACTS["stream_count_distribution"], "stream count distribution drift")
    _require(stream_records == CORPUS_FACTS["stream_records"], "stream record count drift")

    inner = _load_object(ROOT / SOURCE_PINS["inner_manifest"]["path"])
    ownership: dict[tuple[str, ...], int] = {}
    scne_sram_parts = 0
    for record in inner.get("iff_entries", []):
        labels = [block.get("name_label") for block in record.get("blocks", [])]
        for file in record.get("files", []):
            if file.get("type_name") != "SCNE":
                continue
            part_labels = tuple(str(labels[int(part["block_index"])]) for part in file.get("parts", []))
            ownership[part_labels] = ownership.get(part_labels, 0) + 1
            scne_sram_parts += part_labels.count("SRAM")
    _require(ownership == {("DRAM",): 504, ("DRAM", "VRAM"): 799}, "SCNE DRAM/VRAM ownership distribution drift")
    _require(scne_sram_parts == CORPUS_FACTS["scne_sram_part_count"], "SCNE SRAM part count drift")


def _validate_topology_projection() -> None:
    topology = _load_object(ROOT / SOURCE_PINS["draw_topology_spec"]["path"])
    corpus = _load_object(ROOT / SOURCE_PINS["draw_topology_corpus"]["path"])
    report = _load_object(ROOT / SOURCE_PINS["same_footprint_topology_roundtrip"]["path"])

    proof = topology.get("corpus_proof", {})
    _require(proof.get("scne_resources") == CORPUS_FACTS["scne_resources"], "topology SCNE projection drift")
    _require(proof.get("mesh_nodes") == CORPUS_FACTS["mesh_nodes"], "topology node projection drift")
    _require(proof.get("draw_records") == CORPUS_FACTS["draw_records"], "topology draw projection drift")
    _require(proof.get("serialized_indices") == CORPUS_FACTS["serialized_indices"], "topology index projection drift")
    _require(proof.get("partitioned_nodes") == CORPUS_FACTS["mesh_nodes"], "topology partition proof drift")
    _require(topology.get("draw_record", {}).get("size_bytes") == 0x30, "topology draw size drift")
    _require(len(topology.get("draw_record", {}).get("fields", [])) == 12, "topology draw field count drift")
    _require(topology.get("claim_flags", {}).get("draw_layout_proved") is True, "topology draw proof missing")
    _require(topology.get("claim_flags", {}).get("node17_writer_implemented") is True, "topology writer proof missing")
    _require(topology.get("claim_flags", {}).get("runtime_proved") is False, "topology runtime claim overreach")

    invariants = corpus.get("proved_invariants", {})
    for key in (
        "draw_windows_exactly_partition_each_node_index_payload",
        "primitive_capacity_equals_element_count_minus_two",
        "minimum_vertex_equals_window_nonrestart_minimum",
        "vertex_range_equals_window_nonrestart_maximum_minus_minimum_plus_one",
        "every_nonrestart_index_below_vertex_count",
    ):
        _require(invariants.get(key) is True, f"topology corpus invariant drift: {key}")

    changed = report.get("changed_nonretail_permutation", {})
    no_op = report.get("no_op", {})
    preservation = report.get("preservation", {})
    claims = report.get("claim_flags", {})
    _require(report.get("profile") == "outer14_inner8_node17_four_be16_strip/v1", "topology profile drift")
    _require(changed.get("authorized_decoded_bytes") == 8, "topology authorized span drift")
    _require(changed.get("changed_decoded_dram_bytes") == 2, "topology changed-byte proof drift")
    _require(changed.get("native_triangle_count") == 2, "topology triangle proof drift")
    _require(changed.get("native_degenerate_triangle_count") == 0, "topology degeneracy proof drift")
    _require(changed.get("allocation_slack_after_bytes") == 1_403, "topology allocation-fit proof drift")
    _require(no_op.get("complete_1a_byte_identical") is True, "topology no-op byte identity missing")
    _require(no_op.get("h7a_recompressed") is False, "topology no-op recompression regression")
    _require(preservation.get("draw_record_exact") is True, "topology draw preservation missing")
    _require(preservation.get("vertex_stream_exact") is True, "topology vertex preservation missing")
    _require(preservation.get("independent_verifier_imports_topology_writer_or_production_parser") is False, "topology verifier independence drift")
    _require(claims.get("same_footprint_topology_writer_implemented") is True, "topology report writer proof missing")
    _require(claims.get("offline_byte_level_roundtrip_proved") is True, "topology byte proof missing")
    _require(claims.get("runtime_proved") is False, "topology report runtime claim overreach")
    _require(claims.get("hardware_proved") is False, "topology report hardware claim overreach")


def decode_snorm(raw_unsigned: int, bits: int) -> float:
    """Reference the proved parser rule, including the negative-minimum clamp."""

    if not 0 <= raw_unsigned < 1 << bits:
        raise SpecError("raw signed-normalized lane is outside its bit width")
    signed = raw_unsigned - (1 << bits) if raw_unsigned & (1 << (bits - 1)) else raw_unsigned
    maximum = (1 << (bits - 1)) - 1
    return max(signed, -maximum) / float(maximum)


def _quantize_snorm(value: float, maximum: int) -> int:
    if not math.isfinite(value) or not -1.0 <= value <= 1.0:
        raise SpecError("normalized component must be finite and inside [-1,1]")
    return math.trunc(value * maximum)


def encode_position_float32x3(values: tuple[float, float, float]) -> bytes:
    if len(values) != 3 or not all(math.isfinite(value) for value in values):
        raise SpecError("float32x3 POSITION requires three finite values")
    try:
        packed = struct.pack(">3f", *values)
    except (OverflowError, struct.error) as exc:
        raise SpecError("float32x3 POSITION is outside binary32 range") from exc
    if not all(math.isfinite(value) for value in struct.unpack(">3f", packed)):
        raise SpecError("float32x3 POSITION encoded to a non-finite value")
    return packed


def encode_position_snorm16_xyz(normalized: tuple[float, float, float], source_element: bytes) -> bytes:
    if len(source_element) != 8:
        raise SpecError("snorm16x4 source element must be exactly 8 bytes")
    quantized = [_quantize_snorm(value, 32_767) for value in normalized]
    return struct.pack(">3h", *quantized) + source_element[6:8]


def encode_position_snorm10_xyz(normalized: tuple[float, float, float], source_word: bytes) -> bytes:
    if len(source_word) != 4:
        raise SpecError("snorm10_10_10 source element must be exactly 4 bytes")
    original = struct.unpack(">I", source_word)[0]
    quantized = [_quantize_snorm(value, 511) & 0x3FF for value in normalized]
    packed = (original & 0xC0000000) | quantized[0] | (quantized[1] << 10) | (quantized[2] << 20)
    return struct.pack(">I", packed)


def validate(path: Path = DEFAULT_SPEC) -> dict[str, Any]:
    actual_bytes = path.read_bytes()
    canonical_bytes = render_spec()
    _require(actual_bytes == canonical_bytes, "spec differs from canonical generated data")
    document = _load_object(path)
    _require(document == build_spec(), "spec semantic content differs from canonical data")
    _require(document["data_policy"]["contains_retail_geometry"] is False, "retail geometry policy drift")
    _require(document["claim_flags"]["complete_scne_serializer_proved"] is False, "serializer claim overreach")
    _require(document["claim_flags"]["same_count_position_writer_implemented"] is False, "writer implementation claim overreach")
    _require(document["claim_flags"]["pinned_outer14_node17_same_count_position_writer_implemented"] is True, "pinned writer proof missing")
    _require(document["claim_flags"]["outer14_additional_static_target_catalog_proved"] is True, "target catalog proof missing")
    _require(document["claim_flags"]["pinned_outer14_node3_representative_h7a_rebuild_fit_proved"] is True, "node3 rebuild-fit proof missing")
    _require(document["claim_flags"]["outer14_catalog_all_77_targets_structurally_authorized"] is True, "catalog authorization proof missing")
    _require(document["claim_flags"]["outer14_catalog_same_count_position_dispatcher_implemented"] is True, "catalog dispatcher proof missing")
    _require(document["claim_flags"]["pinned_outer14_node3_writer_implemented"] is True, "node3 writer proof missing")
    _require(document["claim_flags"]["pinned_outer14_node3_offline_structural_writeback_proved"] is True, "node3 byte proof missing")
    _require(document["claim_flags"]["general_scne_same_count_position_dispatcher_implemented"] is False, "general SCNE dispatcher claim overreach")
    _require(document["claim_flags"]["changed_topology_writer_proved"] is True, "bounded topology proof missing")
    _require(document["claim_flags"]["pinned_outer14_node17_same_footprint_topology_writer_implemented"] is True, "pinned topology writer proof missing")
    _require(document["claim_flags"]["pinned_outer14_node17_same_footprint_topology_offline_roundtrip_proved"] is True, "pinned topology byte proof missing")
    _require(document["claim_flags"]["general_scne_topology_dispatcher_implemented"] is False, "general topology dispatcher claim overreach")
    _require(document["claim_flags"]["emulator_runtime_visibility_proved"] is False, "runtime claim overreach")
    _require(document["claim_flags"]["xbox_360_hardware_acceptance_proved"] is False, "hardware claim overreach")
    _validate_source_pins()
    _validate_evidence_projection()
    _validate_topology_projection()

    # Exercise ambiguity-preserving inverse edges independently of JSON prose.
    _require(decode_snorm(0x200, 10) == -1.0, "10-bit negative-minimum decode drift")
    _require(decode_snorm(0x8000, 16) == -1.0, "16-bit negative-minimum decode drift")
    _require(encode_position_snorm16_xyz((-1.0, 0.0, 1.0), b"\x00" * 6 + b"\x12\x34")[-2:] == b"\x12\x34", "snorm16 W preservation drift")
    _require(struct.unpack(">I", encode_position_snorm10_xyz((-1.0, 0.0, 1.0), b"\xc0\x00\x00\x00"))[0] & 0xC0000000 == 0xC0000000, "snorm10 high-bit preservation drift")

    return {
        "schema": VALIDATION_SCHEMA,
        "spec_sha256": hashlib.sha256(actual_bytes).hexdigest(),
        "scne_resources": CORPUS_FACTS["scne_resources"],
        "mesh_nodes": CORPUS_FACTS["mesh_nodes"],
        "position_formats": 3,
        "write_profiles": 2,
        "retail_geometry": False,
        "writer_implemented": False,
        "pinned_writer_implemented": True,
        "catalog_targets": 77,
        "catalog_dispatcher_implemented": True,
        "node3_writer_implemented": True,
        "node3_rebuild_fit": True,
        "topology_writer_implemented": True,
        "topology_changed_decoded_bytes": 2,
        "topology_allocation_slack_after": 1_403,
        "runtime_proved": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC, help="specification JSON to validate")
    parser.add_argument("--generate", type=Path, help="write canonical JSON to this path instead of validating")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.generate is not None:
            args.generate.parent.mkdir(parents=True, exist_ok=True)
            args.generate.write_bytes(render_spec())
            print(json.dumps({"schema": SCHEMA, "output": str(args.generate), "sha256": _sha256(args.generate)}, sort_keys=True))
            return 0
        print(json.dumps(validate(args.spec), sort_keys=True))
        return 0
    except (OSError, SpecError, KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
