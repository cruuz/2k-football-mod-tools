#!/usr/bin/env python3
"""Generate and validate the cross-title static-topology conformance contract.

The contract records the narrow, offline-proved NFL group36 same-footprint
writer and the still-unimplemented steps toward fixed-budget conformance.
No retail vertex, index, or command payload is embedded in the generated JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "reports/specs/2k_static_topology_conformance_requirements.v1.json"


class SpecError(ValueError):
    """The contract or one of its evidence sources has drifted."""


SOURCE_PINS = {
    "nfl_parent_spec": (
        "reports/specs/nfl2k5_xbox_static_scne.v1.json",
        47_126,
        "5947b18a7f9fe4b4f6895ca4ea37e5aadd55edb5d365128f46561011fdf8a01e",
    ),
    "apf_parent_spec": (
        "reports/specs/apf2k8_scne_static_serializer.v1.json",
        75_227,
        "8c945740e987b1a27786b29858e46d6a99da65fa96abb019b7e1f28cc1f92b0c",
    ),
    "nfl_roundtrip_report": (
        "reports/assets/nfl_stadium_group36_position_patch_roundtrip.json",
        7_455,
        "45f65c16b4b4d25a30fb63643d3ec1a8f7476a8993e3ca370df33c244cbbef05",
    ),
    "apf_roundtrip_report": (
        "reports/assets/apf_scne_same_count_position_roundtrip.json",
        6_971,
        "5e85c58cf258b19ab40f7b046f7da3010a510dac8d2cd83ede976883af8ab5dd",
    ),
    "nfl_topology_parser": (
        "tools/nfl_scne_inventory.py",
        50_580,
        "0f58222812df6b380588f8b0a2592101136a863cd0dd170b0f32df726de2fc6b",
    ),
    "nfl_topology_exporter": (
        "tools/nfl_scne_gltf.py",
        15_043,
        "69f560d9a665a40868f25334f6f90c5713135f9c4ee8321d0abd30bf3c847058",
    ),
    "nfl_bulk_exporter": (
        "tools/nfl_static_gltf.py",
        35_165,
        "5249732b635374eb33bcb39f162224bccd2163cf1cfd01b1dfc8db42ac40bea3",
    ),
    "apf_topology_parser_and_exporter": (
        "tools/apf_scene.py",
        61_388,
        "0f416e57fe02b8ac7a3695820f23af6875d2413a50905a0292c88e231fd899c2",
    ),
    "nfl_same_count_writer": (
        "tools/nfl_stadium_group36_position_patch.py",
        31_961,
        "d781d49a8adaa23941e5854f734d531b458d1da70c6725f5ad0f2c7c1f92e82b",
    ),
    "apf_same_count_writer": (
        "tools/apf_stadium_static_position_patch.py",
        43_189,
        "37210991eb4c470facd778358c477931e6074e4e84915d330e6adbb44c2c2f4b",
    ),
    "nfl_group36_geometry_writer": (
        "tools/nfl_stadium_group36_geometry_patch.py",
        27_657,
        "0361d4b22286271c6d0f0328f3c86b5ace0f8fc8ef829a387242025e299c1967",
    ),
    "nfl_group36_geometry_independent_verifier": (
        "tools/nfl_stadium_group36_geometry_verify.py",
        25_899,
        "3b14f95c73d64def0a352ea09c106c4ecbc43eea79b5ae59cb4bb72f2db6f1e6",
    ),
    "nfl_group36_geometry_recipe_schema": (
        "reports/specs/nfl2k5_group36_same_footprint_geometry_recipe.schema.json",
        2_691,
        "98a3467b4ece8876f9e613a46aedbfbf5e98ed7d9ae6d913a637276d65051802",
    ),
    "nfl_group36_geometry_nonretail_recipe": (
        "reports/asset_samples/nfl_scne/stadium_group36_zero_positions_permuted_quad_recipe.json",
        1_786,
        "e940739abb9f901607ce2b3c35a629b2cf3ccbda0ba11c4d8963fccadad078fe",
    ),
    "nfl_group36_geometry_roundtrip_report": (
        "reports/assets/nfl_stadium_group36_same_footprint_geometry_roundtrip.json",
        5_488,
        "75e20ced325aa09f75ba0831a28eaee1436ae31b669985396f967d047d0aff20",
    ),
    "nfl_upper_deck_changed_count_boundary": (
        "reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json",
        25_285,
        "e583dde9bca86971eb7355fd07b6a6646a09af8356623b4114c3003998ea4bdb",
    ),
    "apf_draw_topology_spec": (
        "reports/specs/apf2k8_scne_draw_topology.v1.json",
        11_851,
        "ef29fc07d80582d938fbb0a00985c9bd0669ca88ba296d06cd39d9029233224b",
    ),
    "apf_draw_topology_corpus": (
        "reports/assets/apf_scne_draw_topology_corpus.v1.json",
        3_591,
        "8032c0eda8fefe75d61ae607feabad7bf477c845469374781856237bd13c16a2",
    ),
    "apf_topology_writer": (
        "tools/apf_stadium_node17_topology_patch.py",
        26_804,
        "f94ae1306e5483820a133bad4cd01d4a8acd0dead2cb7fffef0b2730b7842a32",
    ),
    "apf_topology_independent_verifier": (
        "tools/apf_stadium_node17_topology_verify.py",
        31_202,
        "2da959176066b5b202eaf5794161d0c205f71b64d5ebd5b8519652cec5c76f3c",
    ),
    "apf_topology_recipe_schema": (
        "reports/specs/apf2k8_scne_same_footprint_topology_recipe.schema.json",
        5_949,
        "a201d33a1fd44daebb05e68ded770c08966ff6b8bf28267e8603df91fb63bb8e",
    ),
    "apf_topology_public_nonretail_recipe": (
        "reports/asset_samples/apf_scene/stadium_node17_nonretail_permuted_strip_recipe.json",
        1_568,
        "9fb9262a415632e7b430375c35cefcd4a72128c029172dcd59ca1f695c49cb99",
    ),
    "apf_topology_roundtrip_report": (
        "reports/assets/apf_stadium_node17_same_footprint_topology_roundtrip.json",
        6_781,
        "3294bec0a2906433885391cc826c47fe4cd6c0fb601a1840ffb46b24dadc34b4",
    ),
}


NFL_GROUP36_PROFILE_CONTRACT = {
    "schema": "2k_static_topology_immutable_profile_contract/v1",
    "profile_id": "nfl2k5_group36_same_footprint_quad_index_replace/v1",
    "source_identity": {
        "outer_id": "0xe4d6b0bc",
        "decoded_sha256": "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8",
        "position_stream_sha256": "65ab99a567a43ebe13c38f6921834896f56f609d954573bb3ae94d414562ab7d",
        "push_sha256": "f1fe835f194447d442a92f13548fde128425d3b8e839f16971a389a96968d3f2",
    },
    "target": {
        "outer_index": 3280,
        "chunk_index": 5,
        "scene_index": 2648,
        "scene_name": "stadium",
        "shape_index": 4,
        "shape_name": "group36",
        "vertex_count": 4,
        "submesh_count": 1,
        "primary_command_word_count": 7,
        "secondary_command_word_count": 0,
    },
    "position_lane": {
        "decoded_offset": 78_368,
        "size_bytes": 48,
        "component_type": "float32_le",
        "components_per_vertex": 3,
        "stride_bytes": 12,
        "coordinate_space": "raw_xbox",
    },
    "quad_index_lane": {
        "push_decoded_offset": 78_320,
        "push_size_bytes": 28,
        "parameter_decoded_offset": 78_332,
        "parameter_size_bytes": 8,
        "component_type": "uint16_le",
        "index_count": 4,
        "minimum_id": 0,
        "maximum_id": 3,
        "index_order": "native_quad_order",
        "primitive_method": "NV097_SET_BEGIN_END_QUADS",
        "primitive_mode": 8,
        "index_method": "NV097_ARRAY_ELEMENT16",
        "index_method_code": "0x1800",
        "begin_end_method_code": "0x17fc",
        "command_sequence": ["SET_BEGIN_END(QUADS)", "ARRAY_ELEMENT16(count=2)", "SET_BEGIN_END(END)"],
    },
    "container_budget": {
        "codec": "VC-LZ",
        "stream_tag": 1,
        "offset_bits": 12,
        "decoded_size_bytes": 1_524_864,
        "retail_consumed_cap_bytes": 908_864,
        "fixed_opaque_tail_bytes": 16,
        "fixed_opaque_tail_sha256": "cb57e42b9b8d9e1cba31e18c38dbc3347c8caa1361fcf7fe9cfad5b9f138fae4",
        "scratch_cap_bytes": 64,
        "fixed_outer_and_chunk_allocation": True,
    },
    "authorized_changes": {
        "same_count_positions": True,
        "same_count_quad_indices": True,
        "changed_vertex_or_index_count": False,
        "changed_command_headers_methods_counts_modes_or_pointers": False,
        "changed_stream_declarations_material_transform_selectors_or_bounds": False,
        "changed_allocation_or_relocation": False,
    },
    "claim_boundary": {
        "offline_structural_write_back": True,
        "runtime_visibility": False,
        "xemu_visibility": False,
        "original_xbox_hardware": False,
        "material_uv_normal_writer": False,
        "automatic_decimator": False,
        "production_mesh_importer": False,
    },
}


def canonical_profile_contract_bytes(contract: dict[str, Any]) -> bytes:
    return (json.dumps(contract, indent=2, sort_keys=True) + "\n").encode("utf-8")


NFL_GROUP36_PROFILE_CONTRACT_FINGERPRINT = hashlib.sha256(
    canonical_profile_contract_bytes(NFL_GROUP36_PROFILE_CONTRACT)
).hexdigest()

NFL_GROUP36_PROFILE_CONTRACT_REFERENCE = {
    "id": NFL_GROUP36_PROFILE_CONTRACT["profile_id"],
    "fingerprint_algorithm": "sha256-canonical-json-indent2-sortkeys-v1",
    "fingerprint": NFL_GROUP36_PROFILE_CONTRACT_FINGERPRINT,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def nfl_element16_command_words(index_count: int) -> int:
    """Words for BEGIN, ARRAY_ELEMENT16, and END with one exact batch."""
    if index_count <= 0 or index_count % 2:
        raise SpecError("ARRAY_ELEMENT16 profile requires a positive even index count")
    return 2 + 1 + index_count // 2 + 2


def nfl_element32_command_words(index_count: int) -> int:
    if index_count <= 0:
        raise SpecError("ARRAY_ELEMENT32 profile requires a positive index count")
    return 2 + 1 + index_count + 2


def apf_index_payload_bytes(component_bits: int, index_count: int) -> int:
    if component_bits not in (16, 32) or index_count <= 0:
        raise SpecError("APF index payload requires 16/32-bit positive element count")
    return index_count * (component_bits // 8)


def relative_target(pointer_field: int, stored_value: int) -> int | None:
    if stored_value == 0:
        return None
    return pointer_field + stored_value - 1


def relative_value(pointer_field: int, target: int) -> int:
    value = target - pointer_field + 1
    if not 1 <= value <= 0xFFFFFFFF:
        raise SpecError("relative pointer is not representable as non-null u32")
    return value


def canonical_spec() -> dict[str, Any]:
    evidence = {
        key: {"path": path, "size_bytes": size, "sha256": digest}
        for key, (path, size, digest) in SOURCE_PINS.items()
    }
    return {
        "schema": "2k_static_topology_conformance_requirements/v1",
        "version": 1,
        "title": "NFL 2K5 Xbox and APF 2K8 Xbox 360 fixed-budget static-topology conformance requirements",
        "status": "NFL group36 and APF node17 same-footprint topology writers are offline byte-proved; NFL upper_deck changed-count control boundary is probed; changed-count archive writers, runtime, and hardware acceptance remain unproved",
        "data_policy": {
            "contains_retail_vertex_values": False,
            "contains_retail_index_values": False,
            "contains_retail_command_payload": False,
            "contains_retail_geometry": False,
            "allowed_evidence": "identities, offsets, extents, hashes, aggregate counts, encodings, algorithms, and rejection rules",
        },
        "source_evidence": evidence,
        "scope": {
            "purpose": "define the implemented NFL group36 and APF node17 same-footprint topology boundaries and the exact fail-closed gap to fixed-budget changed-count conformance writers",
            "covers": [
                "native index or draw-command encoding",
                "vertex declarations, streams, and record-preserving remap constraints",
                "pointer, relocation, alias, and fixed-allocation rules",
                "bounds/culling unknowns",
                "container recompression limits",
                "no-op and changed-output independent verification",
                "mandatory refusal conditions",
            ],
            "does_not_claim": [
                "a topology writer outside the selected NFL group36 and APF node17 same-footprint profiles",
                "changed vertex-count archive write-back",
                "edited-glTF import",
                "automatic decimation",
                "material, UV, normal, skin, attachment, collision, or LOD authoring",
                "emulator or hardware acceptance",
            ],
        },
        "definitions": {
            "topology_change": "any change to a native index element, primitive mode, command stream, restart placement, draw range, submesh membership, index count, or vertex count",
            "same_footprint": "the native decoded structural span begins at the same address and has the same declared byte/word count as retail",
            "fixed_budget": "all decoded parts, archive allocations, and neighboring objects retain their retail extents; compression must fit without borrowing adjacent storage",
            "source_vertex_subset": "each output vertex names one distinct source vertex and copies that source vertex's complete record in every active stream before any separately authorized POSITION edit",
            "independent_verifier": "a verifier that does not import writer, production parser, compressor, or serializer modules and independently derives every authorized changed span",
        },
        "shared_conformance_contract": {
            "external_mesh_admission": {
                "required": [
                    "one explicitly selected source target with exact archive, resource, node/shape, declaration, stream, topology, and source-hash identity",
                    "one indexed primitive; POSITION count equals the admitted native vertex count; all coordinates finite and canonical binary32",
                    "explicit source coordinate space; no implicit axis, unit, winding, or transform conversion",
                    "no sparse accessors, morph targets, skin, joints, weights, animation, compression extension, instancing, or unrecognized extension",
                    "native submesh/material count and ownership remain unchanged unless a later profile proves their serializers",
                ],
                "attribute_rule": "new arbitrary vertices are forbidden until every active native attribute has a proved semantic and inverse; a source-vertex subset decimation profile may instead copy complete source records across every stream",
                "topology_rule": "input triangles must be converted to the selected native primitive grammar deterministically, then decoded again and compared to the admitted nondegenerate triangle multiset with winding retained",
                "duplicate_and_degenerate_rule": "reject duplicate primitive ownership, out-of-range indices, implicit vertex welding, or unrequested degenerates; format-required degenerates must be explicit in the profile and independently removed to the intended triangle list",
            },
            "allocation_ledger": {
                "required_intervals": [
                    "every structural record and pointer field",
                    "every vertex stream's logical and physical capacity",
                    "every index/push stream's logical and physical capacity",
                    "all compressed and uncompressed part boundaries",
                    "all sibling file parts and outer-entry boundaries",
                ],
                "rules": [
                    "prove intervals are bounded, nonoverlapping except for exact documented aliases, and owned by the selected object",
                    "padding, alignment bytes, compression savings, and bytes after a logical end are not writable capacity without independent ownership proof",
                    "do not grow any decompressed part, outer entry, pack volume, or archive directory",
                    "do not move a neighboring record, stream, file part, or outer entry",
                ],
            },
            "pointer_and_alias_rules": [
                "independently enumerate every pointer that resolves into or through a proposed changed span",
                "reject interior aliases, shared stream payloads, shared index/push spans, or overlapping table records unless every owner is selected and the profile authorizes the joint update",
                "preserve all pointer bytes for a same-footprint profile",
                "for a future relayout profile, encode one-based self-relative pointers from the final field and target offsets, decode them independently, and reject null/non-null or range changes not explicitly authorized",
            ],
            "bounds_and_culling": {
                "current_status": "not recovered for either title",
                "rules": [
                    "preserve all candidate bounds, matrix, transform, hierarchy, node flag, draw, collision, and LOD bytes",
                    "a same-position index remap may retain the exact retail position set and therefore the retail geometric AABB",
                    "a source-subset profile must keep every accepted position inside the source decoded AABB, but containment is only a conservative gate and not proof of runtime culling correctness",
                    "reject new positions outside the source AABB until the owning bounds serializer and runtime consumer are proved",
                    "runtime visibility may be claimed only after camera-frustum and representative-distance witnesses show no unexpected culling",
                ],
            },
            "no_op_verification": [
                "after canonical native encoding for an exact byte comparison, detect identity before decoded-object mutation or container recompression",
                "return the original complete selected resource/outer-entry bytes verbatim",
                "require complete copied pack/volume byte identity and matching SHA-256",
                "reparse the source and output independently and require identical interval, pointer, topology, stream, and ownership ledgers",
            ],
            "changed_output_verification": [
                "construct the intended decoded object from a source copy and mutate only profile-authorized lanes",
                "derive the exact decoded changed-byte set and require it to be a subset of the authorized interval/bit mask",
                "independently decode native topology and compare ordered batches, primitive modes, restart placement, winding, nondegenerate triangles, and all vertex bounds to the admitted authoring result",
                "independently decode every changed POSITION under its exact native format and compare under the format-specific exact/error rule",
                "hash every preserved table, unknown field, stream lane, sibling part, footer/tail, archive entry, and copied-volume complement",
                "independently decompress the rebuilt fixed span to the intended complete decoded bytes",
                "reparse all final pointers, extents, counts, declarations, streams, index/push commands, and archive routing",
                "retain source and output hashes plus structural metrics only; do not commit retail-derived geometry",
            ],
            "mandatory_rejections": [
                "source identity, parser grammar, declaration, stream, topology, or allocation drift",
                "unknown native primitive, command method, attribute format, semantic, pointer, or draw-range dependency touched by the requested edit",
                "non-finite, noncanonical, silently rounded, out-of-range, or excess-count input",
                "attribute overlap, stream overlap, pointer alias, interior reference, or ownership ambiguity",
                "unproved material/submesh split, new material, new stream, new declaration, skin, morph, attachment, collision, or LOD",
                "topology decode mismatch, winding mismatch, unexpected degenerates, invalid restart, or index at least vertex_count",
                "decoded-span growth, fixed allocation overflow, recompression overflow, failed independent decompression, or any unauthorized byte change",
                "writer/verifier dependency coupling, source mutation, non-exclusive output publication, or a no-op that is not whole-pack identical",
            ],
        },
        "titles": {
            "nfl2k5_xbox": {
                "read_status": {
                    "topology": "proved for all 276,642 bounded submesh push streams",
                    "observed_batches": {"TRIANGLE_STRIP": 275_213, "QUADS": 1_429},
                    "unknown_methods_in_corpus": 0,
                    "vertex_references_in_bounds": True,
                },
                "native_topology_encoding": {
                    "word_storage": "u32le",
                    "header": {
                        "accepted_signature": "(header & 0xe0030003) in {0x00000000,0x40000000}",
                        "instruction": "(header >> 29) & 7",
                        "parameter_count": "(header >> 18) & 0x7ff",
                        "method": "header & 0x1ffc",
                        "boundary": "header plus parameter_count words must fit primary_command_word_count",
                    },
                    "methods": {
                        "0x17fc": "SET_BEGIN_END; primitive 0 ends the current batch",
                        "0x1800": "ARRAY_ELEMENT16; two u16 indices in each u32 parameter, low halfword first",
                        "0x1808": "ARRAY_ELEMENT32; one u32 index per parameter",
                        "0x1810": "DRAW_ARRAYS; start=low24, count=high8+1",
                    },
                    "primitive_modes": {
                        "0": "END", "1": "POINTS", "2": "LINES", "3": "LINE_LOOP",
                        "4": "LINE_STRIP", "5": "TRIANGLES", "6": "TRIANGLE_STRIP",
                        "7": "TRIANGLE_FAN", "8": "QUADS", "9": "QUAD_STRIP", "10": "POLYGON",
                    },
                    "single_batch_word_budget": {
                        "ARRAY_ELEMENT16_even_indices": "5 + index_count/2",
                        "ARRAY_ELEMENT32": "5 + index_count",
                        "DRAW_ARRAYS": "5 + range_count",
                        "rule": "the first profile preserves original headers and word count; a later serializer must reject any generated stream larger than a separately proved owned command capacity",
                    },
                },
                "vertex_and_stream_constraints": {
                    "shape_vertex_count": "u16le at shape +0x4c; currently immutable",
                    "declaration": "16 register descriptors: (byte_offset<<16)|(stream_index<<8)|format_code",
                    "streams": "8 stride/pointer slots; active span is pointer through vertex_count*stride in the decoded system buffer",
                    "first_target": [
                        "register 0 FLOAT3 in stream 0 at offset 0, stride 12",
                        "register 1 SHORT1, register 3 D3DCOLOR, and register 6 NORMSHORT2 in stream 1, stride 10",
                        "all non-POSITION streams and lanes remain bit-exact for the selected first profile",
                    ],
                    "changed_vertex_count_future_rule": [
                        "new count must be positive, at most source count, and fit u16",
                        "without full attribute inverses, every output vertex must be a unique source-vertex subset member and its complete record must be copied in every active stream",
                        "stream strides/pointers/declarations remain exact; copied records occupy each stream prefix; bytes after new_count*stride remain bit-exact and unowned by the writer",
                        "shape vertex_count is updated once; every topology reference must be below it",
                    ],
                },
                "records_and_pointers": {
                    "shape_stride": 256,
                    "submesh_stride": 128,
                    "submesh_push_pointer": "s32le one-based self-relative at +0x78",
                    "primary_word_count": "u16le at +0x7c",
                    "secondary_word_count": "u16le at +0x7e; semantics unknown and immutable",
                    "relative_target": "pointer_field_offset - 1 + s32le(stored)",
                    "first_profile_rule": "preserve every count, pointer, record, declaration, stream, material, transform, and unknown byte; change only authorized ARRAY_ELEMENT16 halfwords",
                    "future_subset_rule": "primary word count may decrease only after proving no alias and exact command-prefix ownership; push pointer stays fixed and unused tail bytes stay exact",
                },
                "container_limit": {
                    "decoded": "system_bytes and video_bytes remain exact",
                    "vc_lz": "rebuilt consumed stream must not exceed the pinned retail consumed boundary; preserve the fixed opaque tail; independently derive alias scratch",
                    "outer": "entry offset and size stay exact; every byte outside the selected resource span stays exact",
                    "headroom": "compression savings and padding are not mesh allocation headroom",
                },
                "selected_first_topology_profile": {
                    "schema": "nfl2k5_group36_same_footprint_quad_index_replace/v1",
                    "status": "offline_writer_and_independent_verifier_implemented_runtime_unproved",
                    "profile_contract_reference": dict(NFL_GROUP36_PROFILE_CONTRACT_REFERENCE),
                    "immutable_profile_contract": json.loads(json.dumps(NFL_GROUP36_PROFILE_CONTRACT)),
                    "reason_selected": "reuses the only byte-proved static-position target, preserves the entire vertex set and AABB, has one material/submesh/batch, and changes no pointer, count, command header, primitive mode, draw range, stream, or allocation",
                    "target": {
                        "outer_index": 3280,
                        "chunk_index": 5,
                        "scene_index": 2648,
                        "scene_name": "stadium",
                        "shape_index": 4,
                        "shape_name": "group36",
                        "vertex_count": 4,
                        "submesh_count": 1,
                        "primary_command_word_count": 7,
                        "secondary_command_word_count": 0,
                        "push_decoded_offset": 78_320,
                        "push_size_bytes": 28,
                        "push_sha256": "f1fe835f194447d442a92f13548fde128425d3b8e839f16971a389a96968d3f2",
                    },
                    "source_command_shape": [
                        "exactly one SET_BEGIN_END(QUADS) command",
                        "exactly one ARRAY_ELEMENT16 command carrying four indices in two parameter words",
                        "exactly one SET_BEGIN_END(END) command",
                    ],
                    "authoring_input": "exactly four ordered u16 vertex IDs, each below vertex_count; duplicates are structurally encodable and are not silently rejected by the mechanical serializer boundary",
                    "degenerate_policy": {
                        "mechanical_boundary": "duplicate IDs are accepted only when explicitly present in the authored four-element list; the independent decoder reports the resulting degenerate/nondegenerate triangles",
                        "first_non_degenerate_witness": "use a permutation of every integer in [0,vertex_count) exactly once",
                        "claim_boundary": "structural encodability does not prove that a degenerate quad is useful, visible, or runtime accepted",
                    },
                    "allowed_decoded_changes": [
                        "the four u16 index halfwords inside the two already located ARRAY_ELEMENT16 parameter words",
                        "optionally the already proved 48 FLOAT3 POSITION bytes under the existing same-count writer contract",
                    ],
                    "must_remain_exact": [
                        "all seven command headers/word positions, QUADS mode, begin/end placement, methods, parameter counts, push pointer, and primary/secondary word counts",
                        "vertex count, vertex set for topology-only use, two stream payloads, declarations, transform/root/selectors, material and submesh records",
                        "all decoded bytes outside the authorized index halfwords and optional proved position lanes",
                    ],
                    "profile_rejections": [
                        "anything other than exactly four integer IDs, or any negative/out-of-range/non-u16 ID",
                        "changed command header, primitive mode, method, word count, submesh/material, declaration, stream, transform, or vertex count",
                        "any request whose intended primitive cannot be represented as exactly one native quad with the admitted ordered IDs",
                    ],
                    "implemented_proof": "the writer and independently implemented push parser reconstruct the requested ordered quad, prove exact changed halfwords and optional proved positions, satisfy the VC-LZ/fixed-tail/full-volume contract, and retain every runtime/hardware/production claim false",
                },
                "fixed_budget_subset_profile_gap": {
                    "status": "upper_deck_target_contract_and_count_only_fixed_span_probes_proved_writer_not_implemented",
                    "would_enable": "source-derived vertex-count reduction and deterministic decimation while retaining opaque per-vertex attributes",
                    "selected_probe_boundary": {
                        "spec_schema": "nfl2k5_upper_deck_changed_count_boundary/v1",
                        "spec_path": "reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json",
                        "spec_sha256": "e583dde9bca86971eb7355fd07b6a6646a09af8356623b4114c3003998ea4bdb",
                        "recipe_schema_path": "reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json",
                        "recipe_schema_sha256": "4fac01c6cffe03481b456899ec2b2f3cd25f74954d5db94ccb3b8351f841ca4b",
                        "target_id": "nfl2k5/stadium/o3280/c5/s1",
                        "shape_name": "upper_deck",
                        "source_vertex_count": 12,
                        "changed_vertex_counts": [4, 8],
                        "active_stream_strides": [12, 10],
                        "native_topology": "one six-word start-zero DRAW_ARRAYS QUADS batch",
                        "coupled_changed_bytes_for_prefix_shrink": [30540, 69887],
                        "count_8_rebuilt_consumed_bytes": 908_863,
                        "count_4_rebuilt_consumed_bytes": 908_862,
                        "retail_consumed_cap_bytes": 908_864,
                        "physical_stream_bytes_changed_by_count_only_probes": False,
                        "archive_writer_implemented": False,
                        "independent_verifier_implemented": False,
                        "runtime_proved": False,
                    },
                    "still_required": [
                        "implement and independently verify the exact upper_deck shape-count plus existing DRAW_ARRAYS-count mutation without changing its six-word command footprint",
                        "prove a nonidentity complete-record prefix remap across both active streams on retail bytes; keep every logical tail exact",
                        "close semantics-unknown/runtime alias ownership for both shortened logical stream tails",
                        "recover bounds/culling, collision, and LOD ownership or retain source positions and obtain a conservative runtime witness",
                        "runtime-witness both four- and eight-vertex variants before exposing changed-count support",
                    ],
                    "arbitrary_external_mesh_blockers": [
                        "register semantics and inverses for normal, UV, color, selector/attachment, and shader-specific lanes",
                        "material/texture binding and transform/attachment ownership",
                        "bounds, collision, and LOD serialization",
                    ],
                },
            },
            "apf2k8_xbox360": {
                "read_status": {
                    "topology": "BE16/BE32 D3DPT_TRIANGLESTRIP payloads bounded for all 13,006 retail nodes",
                    "primitive_type": 5,
                    "index_width_distribution": {"16": 13_003, "32": 3},
                    "draw_record_semantics": "all 47,112 full 0x30 layouts and draw/index windows recovered; optional-state payload and final render-flag meaning remain opaque",
                    "draw_windows_partition_all_node_index_payloads": True,
                },
                "native_topology_encoding": {
                    "storage": "u16be or u32be selected by mesh node +0xa4",
                    "index_count": "u32be at mesh node +0xa8, includes restart elements",
                    "index_pointer": "one-based self-relative u32be at mesh node +0xac",
                    "restart": {"16": "0xffff", "32": "0xffffffff"},
                    "primitive": "mesh descriptor +0x10 equals D3DPT_TRIANGLESTRIP (5)",
                    "decode": [
                        "restart clears the current strip and resets parity",
                        "emit (a,b,c) on even strip triangle and (b,a,c) on odd strip triangle",
                        "omit triangles with fewer than three distinct indices",
                        "require every non-restart index below vertex_count",
                    ],
                    "write_status": "offline same-footprint writer and independent verifier implemented for the pinned node17 four-BE16 permutation profile; no general APF topology dispatcher",
                },
                "vertex_and_stream_constraints": {
                    "mesh_descriptor": "vertex_count u32be at +0x08; high 16 bits of +0x0c are stream_count; low 16 bits remain opaque",
                    "stream_record": "0x18 bytes with flags, enabled, stride, byte_length, start relptr, end relptr",
                    "stream_invariants": "end-start == byte_length == vertex_count*stride; all targets stay in the selected DRAM part",
                    "declaration": "0x40-byte semantic record; stream=(layout>>8)&0xff, byte_offset=(layout>>16)&0xff; preserve layout mask 0xff0000ff",
                    "first_target": "one 24-byte stream: POSITION0 float32x3 bytes 0..11, TEXCOORD0 float16x4 bytes 12..19, NORMAL0 snorm10_10_10 bytes 20..23",
                    "changed_vertex_count_future_rule": [
                        "new count is positive and no greater than source unless a full relocation and attribute writer is proved",
                        "copy each source-subset vertex's complete 24-byte record to the new stream prefix",
                        "update vertex_count, byte_length, and stream end pointer consistently while preserving stream start/stride/flags/enabled",
                        "leave bytes after the new logical end exact; never treat them as writable slack",
                    ],
                },
                "records_and_pointers": {
                    "mesh_node_stride": 176,
                    "draw_record_stride": 48,
                    "declaration_stride": 64,
                    "relative_target": "pointer_field_offset + stored_u32 - 1",
                    "draw_record_fields": {
                        "0x00": "draw primitive code; 6 corpus-wide and forwarded to native submission",
                        "0x04": "first serialized index element",
                        "0x08": "element count including restarts",
                        "0x0c": "primitive capacity = element_count - 2",
                        "0x10": "base vertex; zero corpus-wide and forwarded",
                        "0x14": "minimum non-restart index",
                        "0x18": "maximum - minimum + 1",
                        "0x1c": "optional one-based self-relative draw state; payload meaning unproved",
                        "0x20": "material slot; address stride 0xf0 proved from renderer",
                        "0x24": "reserved zero; preserve",
                        "0x28": "reserved zero; preserve",
                        "0x2c": "render flags 0..3; meaning unproved; preserve",
                    },
                    "draw_window_contract": "sorted windows begin at zero, are contiguous and nonoverlapping, end at node.index_count, and derive capacity/minimum/range from their serialized element windows",
                    "first_safe_write_boundary": "preserve node, hierarchy, matrix, draw, declaration, descriptor, stream metadata, pointer, count, primitive, and unknown bytes; node17 topology is writable only because all admitted permutations preserve every draw invariant",
                },
                "container_limit": {
                    "decoded": "selected SCNE DRAM and VRAM part lengths remain exact; all sibling parts remain exact",
                    "h7a": "recompress only the changed block with preserved shift/codec and require independent full-block decode",
                    "iff": "update only mechanically required stored offsets/lengths/file_length; preserve footer and file descriptors; active IFF must fit the fixed outer allocation",
                    "outer": "copy pack before mutation, preserve entry length and every pack byte outside it, and reject allocation overflow",
                    "headroom": "zero allocation tail and H7A savings are transport headroom only, not permission to grow a decoded SCNE part",
                },
                "analogous_same_footprint_profile": {
                    "schema": "outer14_inner8_node17_four_be16_strip/v1",
                    "status": "offline_writer_and_independent_verifier_implemented_runtime_unproved",
                    "target": {
                        "outer_table_index": 14,
                        "inner_file_index": 8,
                        "inner_name": "stadium",
                        "node_index": 17,
                        "node_name": "polySurface19930",
                        "vertex_count": 4,
                        "index_component_bits": 16,
                        "index_count": 4,
                        "index_decoded_offset": 375_760,
                        "index_size_bytes": 8,
                        "index_sha256": "96b383ee0d221556a56277315db425256549a46ccc5217a392181783327a6dc5",
                        "draw_record_count": 1,
                        "draw_record_sha256": "161a2e06c0b875b6679423f490c2c89691d1da9899003768a0f4eac01cfe873f",
                    },
                    "admission": "exactly four JSON integers forming one permutation of 0,1,2,3; no restart, duplicate, extra topology field, or alternative width/count is accepted",
                    "implemented_boundary": "rewrite only the existing eight decoded BE16 index bytes; preserve width/count/pointer/primitive, all 48 draw bytes, all vertex and structural bytes, all sibling parts, and the complete copied-volume complement",
                    "degenerate_policy": {
                        "writer_rule": "reject every duplicate or restart and independently require exactly two nondegenerate triangles and zero degenerates",
                        "winding_rule": "decode with native alternating triangle-strip parity and compare the exact ordered triangles to the admitted permutation",
                    },
                    "draw_invariants": {
                        "draw_record_exact": True,
                        "reason": "permutation preserves first=0, count=4, capacity=2, base=0, minimum=0, range=4",
                        "material_slot_optional_state_and_render_flags_exact": True,
                    },
                    "proof": {
                        "changed_decoded_bytes": 2,
                        "authorized_decoded_bytes": 8,
                        "block0_stored_length_before": 3_299_082,
                        "block0_stored_length_after": 3_299_705,
                        "fixed_outer_allocation_bytes": 12_931_072,
                        "allocation_slack_after_bytes": 1_403,
                        "native_triangle_count": 2,
                        "native_degenerate_triangle_count": 0,
                        "no_op_complete_1a_byte_identical": True,
                        "no_op_recompressed": False,
                        "independent_verifier_imports_writer_or_production_parser": False,
                    },
                    "remaining_before_generalization": [
                        "runtime visibility and culling witness for this exact profile",
                        "hashes-only target admission and per-target draw/index invariant derivation before supporting another APF node",
                        "bounds/culling ownership before changed-count or out-of-source-AABB geometry",
                    ],
                },
                "fixed_budget_subset_profile_gap": {
                    "status": "same_footprint_closed_changed_count_unimplemented",
                    "required_structural_updates": [
                        "mesh vertex_count",
                        "every stream byte_length and end relative pointer",
                        "index_count and index payload prefix",
                        "every affected draw first_element, element_count, primitive_capacity, minimum_vertex, and vertex_range field",
                    ],
                    "still_required": [
                        "implement deterministic draw-window repartition and independently re-derive every changed draw field",
                        "preserve or prove the optional draw-state payload, material slot, reserved words, and render flags for every affected draw",
                        "prove pointer/alias ownership for shrunken stream and index logical spans",
                        "define deterministic triangle-stripification, restart, winding, degeneracy, and BE16/BE32 selection rules",
                        "prove bounds/culling and matrix/attachment ownership",
                        "add changed-count independent writer/verifier and Xenia witness",
                    ],
                    "arbitrary_external_mesh_blockers": [
                        "TEXCOORD float16 inverse and UV convention",
                        "NORMAL/TANGENT/BINORMAL contextual inverse and handedness",
                        "materials, shaders, samplers, and selected SCNE VRAM ownership",
                        "skin, attachment, collision, LOD, and bounds serialization",
                    ],
                },
            },
        },
        "first_profile_selection": {
            "selected": "nfl2k5_group36_same_footprint_quad_index_replace/v1",
            "selection_is_implementation_claim": True,
            "selection_is_runtime_claim": False,
            "why_not_apf_first": "historically, APF node17 was deferred because its draw record was opaque; that draw/index coupling is now corpus-closed and the analogous bounded writer is implemented, without changing which profile was completed first",
            "why_not_changed_count_first": "changed count expands the proof surface to vertex-record remap, count fields, logical stream extents, possible aliases, bounds, and draw-range ownership",
            "exit_criteria": [
                "canonical recipe/schema with no retail-derived indices",
                "fail-closed copied-volume writer changing only four located index halfwords and optional already-proved positions",
                "independent native push and full-container verifier",
                "whole-volume no-op identity, changed-span proof, VC-LZ overflow refusal, and mutation tests",
                "runtime witness before any runtime-supported label",
            ],
        },
        "gap_matrix": [
            {"area": "same-count POSITION", "nfl2k5": "75 catalog targets dispatched with two byte-level witnesses", "apf2k8": "77 catalog targets dispatched with two byte-level witnesses", "needed_for_conformer": "runtime/semantic ownership before production exposure"},
            {"area": "native topology read", "nfl2k5": "NV2A methods and modes corpus-proved", "apf2k8": "BE16/BE32 triangle strips plus full draw windows corpus-proved", "needed_for_conformer": "general deterministic inverse and target admission beyond pinned profiles"},
            {"area": "same-footprint index write", "nfl2k5": "selected group36 quad profile offline writer and independent verifier proved; runtime unproved", "apf2k8": "selected node17 four-BE16 strip profile offline writer and independent verifier proved; runtime unproved", "needed_for_conformer": "runtime witnesses and per-target generalization"},
            {"area": "changed vertex count", "nfl2k5": "upper_deck two-byte count control plus fixed-span 4/8 in-memory probes proved; archive writer unimplemented", "apf2k8": "descriptor, streams, and draw fields known; coordinated writer unimplemented", "needed_for_conformer": "count writers, independent verification, bounds ownership, and runtime"},
            {"area": "arbitrary new vertex records", "nfl2k5": "register semantics/inverses incomplete", "apf2k8": "UV/normal contextual inverses incomplete", "needed_for_conformer": "all active attribute writers"},
            {"area": "materials/submeshes", "nfl2k5": "material index read; records mostly opaque", "apf2k8": "draw material slot and 0xf0 stride proved; material payload/bindings opaque", "needed_for_conformer": "binding serializers"},
            {"area": "bounds/culling", "nfl2k5": "unknown", "apf2k8": "unknown", "needed_for_conformer": "owner fields plus runtime witness"},
            {"area": "fixed allocation", "nfl2k5": "VC-LZ and outer cap proved", "apf2k8": "H7A/IFF/outer cap proved", "needed_for_conformer": "budget estimator before mutation"},
        ],
        "implementation_sequence": [
            "runtime-witness that exact NFL topology change",
            "implement the upper_deck count-only prefix shrink with an independent verifier, then prove nonidentity whole-record subset remap",
            "runtime-witness the completed APF node17 same-footprint strip remap before exposing runtime support",
            "APF source-vertex-subset decimation after coordinated draw/count/end-pointer and bounds closure",
            "only then add arbitrary external vertex attributes, material binding, and automatic target-budget decimation",
        ],
        "claim_flags": {
            "requirements_specified": True,
            "nfl_same_footprint_profile_selected": True,
            "nfl_topology_writer_implemented": True,
            "nfl_selected_profile_offline_writeback_proved": True,
            "nfl_changed_count_target_contract_probed": True,
            "apf_topology_writer_implemented": True,
            "changed_vertex_count_writer_implemented": False,
            "automatic_decimator_implemented": False,
            "edited_gltf_importer_implemented": False,
            "bounds_culling_proved": False,
            "material_uv_normal_writer_proved": False,
            "runtime_proved": False,
            "hardware_proved": False,
            "production_ready": False,
        },
    }


def canonical_bytes() -> bytes:
    return (json.dumps(canonical_spec(), indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_sources() -> None:
    for label, (relative, expected_size, expected_hash) in SOURCE_PINS.items():
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise SpecError(f"{label}: missing regular evidence file {relative}")
        if path.stat().st_size != expected_size:
            raise SpecError(f"{label}: size drift for {relative}")
        if sha256_file(path) != expected_hash:
            raise SpecError(f"{label}: SHA-256 drift for {relative}")


def validate_parent_specs() -> None:
    nfl = json.loads((ROOT / SOURCE_PINS["nfl_parent_spec"][0]).read_text(encoding="utf-8"))
    apf = json.loads((ROOT / SOURCE_PINS["apf_parent_spec"][0]).read_text(encoding="utf-8"))
    if nfl.get("schema") != "nfl2k5_xbox_static_scne_format/v1":
        raise SpecError("NFL parent schema drift")
    push = nfl.get("nv2a_push_topology", {})
    if set(push.get("methods", {})) != {"0x17fc", "0x1800", "0x1808", "0x1810"}:
        raise SpecError("NFL native topology methods drift")
    if push.get("canonical_corpus", {}).get("unknown_methods") != 0:
        raise SpecError("NFL corpus gained unknown push methods")
    witness = nfl.get("same_count_position_write_boundary_v1", {}).get("implemented_group36_witness", {})
    if (witness.get("outer_index"), witness.get("chunk_index"), witness.get("shape_index"), witness.get("vertex_count")) != (3280, 5, 4, 4):
        raise SpecError("NFL group36 witness drift")
    if nfl.get("claim_flags", {}).get("topology_write_proved") is not False:
        raise SpecError("NFL parent unexpectedly claims topology write proof")

    if apf.get("schema") != "apf2k8_scne_static_serializer/v1":
        raise SpecError("APF parent schema drift")
    strip = apf.get("scne", {}).get("index_strip", {})
    if strip.get("primitive_type") != 5 or [row.get("bits") for row in strip.get("supported_widths", [])] != [16, 32]:
        raise SpecError("APF strip grammar drift")
    target = apf.get("write_profiles", {}).get("same_count_position_only/v1", {}).get("implemented_target", {})
    if (target.get("outer_table_index"), target.get("inner_file_index"), target.get("node_index"), target.get("vertex_count")) != (14, 8, 17, 4):
        raise SpecError("APF node17 witness drift")
    apf_claims = apf.get("claim_flags", {})
    if (
        apf_claims.get("changed_topology_writer_proved") is not True
        or apf_claims.get("pinned_outer14_node17_same_footprint_topology_writer_implemented") is not True
        or apf_claims.get("pinned_outer14_node17_same_footprint_topology_offline_roundtrip_proved") is not True
        or apf_claims.get("general_scne_topology_dispatcher_implemented") is not False
        or apf_claims.get("emulator_runtime_visibility_proved") is not False
    ):
        raise SpecError("APF parent topology claim boundary drift")
    draw = apf.get("scne", {}).get("draw_record", {})
    if draw.get("size_bytes") != 48 or len(draw.get("fields", [])) != 12:
        raise SpecError("APF draw-record layout drift")
    topology_target = apf.get("write_profiles", {}).get(
        "outer14_inner8_node17_four_be16_strip/v1", {}
    ).get("implemented_target", {})
    if (
        topology_target.get("outer_table_index"), topology_target.get("inner_file_index"),
        topology_target.get("node_index"), topology_target.get("index_component_bits"),
        topology_target.get("index_count"), topology_target.get("index_allocation_bytes"),
    ) != (14, 8, 17, 16, 4, 8):
        raise SpecError("APF topology target drift")


def validate_roundtrip_claims() -> None:
    nfl = json.loads((ROOT / SOURCE_PINS["nfl_roundtrip_report"][0]).read_text(encoding="utf-8"))
    if nfl.get("schema") != "nfl2k5_static_position_patch_roundtrip/v1":
        raise SpecError("NFL roundtrip schema drift")
    if nfl.get("claims", {}).get("changed_topology_write_back_proved") is not False:
        raise SpecError("NFL roundtrip unexpectedly claims topology write-back")
    target = nfl.get("target", {})
    if (target.get("outer_index"), target.get("chunk_index"), target.get("shape_index")) != (3280, 5, 4):
        raise SpecError("NFL roundtrip target drift")
    rigid = target.get("rigid_static_proof", {})
    if rigid.get("native_primitive") != "QUADS" or rigid.get("indices") != list(range(4)):
        raise SpecError("NFL selected source command shape drift")

    apf = json.loads((ROOT / SOURCE_PINS["apf_roundtrip_report"][0]).read_text(encoding="utf-8"))
    if apf.get("schema") != "apf2k8_scne_same_count_position_roundtrip/v1":
        raise SpecError("APF roundtrip schema drift")
    if apf.get("claims", {}).get("changed_topology_proved") is not False:
        raise SpecError("APF roundtrip unexpectedly claims topology write-back")
    target = apf.get("target", {})
    if (target.get("outer_table_index"), target.get("inner_file_index"), target.get("node_index"), target.get("vertex_count")) != (14, 8, 17, 4):
        raise SpecError("APF roundtrip target drift")

    apf_topology_spec = json.loads((
        ROOT / SOURCE_PINS["apf_draw_topology_spec"][0]
    ).read_text(encoding="utf-8"))
    if apf_topology_spec.get("schema") != "apf2k8_scne_draw_topology/v1":
        raise SpecError("APF topology spec schema drift")
    topology_flags = apf_topology_spec.get("claim_flags", {})
    if (
        topology_flags.get("draw_layout_proved") is not True
        or topology_flags.get("draw_index_coupling_corpus_proved") is not True
        or topology_flags.get("node17_writer_implemented") is not True
        or topology_flags.get("node17_independent_offline_verifier_proved") is not True
        or any(topology_flags.get(key) is not False for key in (
            "changed_count_writer_implemented", "bounds_culling_proved",
            "runtime_proved", "hardware_proved", "production_ready",
        ))
    ):
        raise SpecError("APF topology spec claim boundary drift")

    apf_topology_corpus = json.loads((
        ROOT / SOURCE_PINS["apf_draw_topology_corpus"][0]
    ).read_text(encoding="utf-8"))
    coverage = apf_topology_corpus.get("coverage", {})
    invariants = apf_topology_corpus.get("proved_invariants", {})
    if (
        coverage.get("scne_resources") != 1_303
        or coverage.get("mesh_nodes") != 13_006
        or coverage.get("draw_records") != 47_112
        or coverage.get("serialized_indices") != 24_519_417
        or coverage.get("partitioned_nodes") != 13_006
        or invariants.get("draw_windows_exactly_partition_each_node_index_payload") is not True
        or invariants.get("every_nonrestart_index_below_vertex_count") is not True
    ):
        raise SpecError("APF topology corpus projection drift")

    apf_topology = json.loads((
        ROOT / SOURCE_PINS["apf_topology_roundtrip_report"][0]
    ).read_text(encoding="utf-8"))
    if apf_topology.get("schema") != "apf2k8_scne_same_footprint_topology_roundtrip/v1":
        raise SpecError("APF topology roundtrip schema drift")
    topology_claims = apf_topology.get("claim_flags", {})
    if (
        topology_claims.get("same_footprint_topology_writer_implemented") is not True
        or topology_claims.get("independent_verifier_proved") is not True
        or topology_claims.get("offline_byte_level_roundtrip_proved") is not True
        or any(topology_claims.get(key) is not False for key in (
            "changed_vertex_count_proved", "bounds_culling_proved", "runtime_proved",
            "hardware_proved", "material_or_vertex_authoring_proved", "production_ready",
        ))
    ):
        raise SpecError("APF topology roundtrip claim boundary drift")
    changed_topology = apf_topology.get("changed_nonretail_permutation", {})
    noop_topology = apf_topology.get("no_op", {})
    topology_preservation = apf_topology.get("preservation", {})
    if (
        changed_topology.get("authorized_decoded_bytes") != 8
        or changed_topology.get("changed_decoded_dram_bytes") != 2
        or changed_topology.get("native_triangle_count") != 2
        or changed_topology.get("native_degenerate_triangle_count") != 0
        or changed_topology.get("allocation_slack_after_bytes") != 1_403
        or noop_topology.get("complete_1a_byte_identical") is not True
        or noop_topology.get("h7a_recompressed") is not False
        or topology_preservation.get("draw_record_exact") is not True
        or topology_preservation.get("vertex_stream_exact") is not True
        or topology_preservation.get("independent_verifier_imports_topology_writer_or_production_parser") is not False
    ):
        raise SpecError("APF topology byte proof drift")

    geometry = json.loads((
        ROOT / SOURCE_PINS["nfl_group36_geometry_roundtrip_report"][0]
    ).read_text(encoding="utf-8"))
    if geometry.get("schema") != "nfl2k5_group36_same_footprint_geometry_roundtrip/v1":
        raise SpecError("NFL geometry roundtrip schema drift")
    if geometry.get("profile_contract") != NFL_GROUP36_PROFILE_CONTRACT_REFERENCE:
        raise SpecError("NFL geometry roundtrip profile fingerprint drift")
    claims = geometry.get("claims", {})
    if claims.get("offline_same_footprint_native_quad_write_back_proved") is not True:
        raise SpecError("NFL geometry roundtrip does not prove offline topology write-back")
    if any(claims.get(key) is not False for key in (
        "changed_vertex_or_index_count_write_back",
        "runtime_visibility_proved",
        "original_xbox_hardware_proved",
        "automatic_decimator_implemented",
        "production_mesh_importer",
    )):
        raise SpecError("NFL geometry roundtrip overclaims unproved behavior")
    changed = geometry.get("controlled_nonretail_changed_witness", {})
    if (
        changed.get("decoded_changed_byte_count") != 50
        or changed.get("rebuilt_consumed_bytes") != 908_830
        or changed.get("scratch_bytes") != 64
        or changed.get("indices_are_permutation") is not True
        or changed.get("nondegenerate_triangle_count") != 2
        or changed.get("outside_authorized_geometry_bit_exact") is not True
    ):
        raise SpecError("NFL geometry changed witness drift")
    policy = geometry.get("data_policy", {})
    if any(policy.get(key) is not False for key in (
        "contains_replacement_bytes", "contains_retail_command_payload",
        "contains_retail_geometry", "contains_retail_index_values",
        "contains_retail_vertex_values",
    )):
        raise SpecError("NFL geometry report embeds forbidden retail geometry")

    changed_count = json.loads((
        ROOT / SOURCE_PINS["nfl_upper_deck_changed_count_boundary"][0]
    ).read_text(encoding="utf-8"))
    if changed_count.get("schema") != "nfl2k5_upper_deck_changed_count_boundary/v1":
        raise SpecError("NFL upper_deck changed-count boundary schema drift")
    changed_flags = changed_count.get("claim_flags", {})
    if (
        changed_flags.get("target_structure_closed_for_prefix_shrink_probe") is not True
        or changed_flags.get("two_count_bytes_and_fixed_span_fit_probed") is not True
        or any(changed_flags.get(key) is not False for key in (
            "changed_count_archive_writer_implemented",
            "independent_changed_count_verifier_implemented",
            "bounds_or_culling_serializer_proved",
            "runtime_visibility_proved",
            "production_ready",
        ))
    ):
        raise SpecError("NFL upper_deck changed-count claim boundary drift")
    target = changed_count.get("target_selection", {})
    topology = changed_count.get("topology_contract", {})
    if (
        target.get("target_id") != "nfl2k5/stadium/o3280/c5/s1"
        or topology.get("admissible_vertex_counts") != [4, 8, 12]
        or topology.get("changed_vertex_counts") != [4, 8]
        or topology.get("primary_word_count") != 6
        or topology.get("secondary_word_count") != 0
    ):
        raise SpecError("NFL upper_deck changed-count structural boundary drift")
    probes = changed_count.get("prefix_shrink_probe", {}).get("probes", [])
    if (
        [row.get("new_vertex_count") for row in probes] != [8, 4]
        or [row.get("rebuilt_consumed_bytes") for row in probes] != [908_863, 908_862]
        or any(row.get("changed_decoded_offsets") != [30_540, 69_887] for row in probes)
        or any(row.get("runtime_tested") is not False for row in probes)
    ):
        raise SpecError("NFL upper_deck changed-count fixed-span probes drift")
    changed_policy = changed_count.get("data_policy", {})
    if any(changed_policy.get(key) is not False for key in (
        "contains_retail_vertex_values", "contains_retail_attribute_values",
        "contains_retail_index_values", "contains_retail_command_payload",
        "contains_modified_archive_bytes",
    )):
        raise SpecError("NFL upper_deck changed-count spec embeds forbidden payload")


def validate_spec(data: dict[str, Any]) -> dict[str, Any]:
    expected = canonical_spec()
    if data != expected:
        raise SpecError("checked specification is not canonical")
    if nfl_element16_command_words(4) != 7:
        raise SpecError("NFL selected push budget derivation failed")
    if nfl_element32_command_words(4) != 9:
        raise SpecError("NFL ARRAY_ELEMENT32 budget derivation failed")
    if apf_index_payload_bytes(16, 4) != 8:
        raise SpecError("APF selected index extent derivation failed")
    for pointer_field, target in ((0x100, 0x200), (0x200, 0x300), (0, 1)):
        encoded = relative_value(pointer_field, target)
        if relative_target(pointer_field, encoded) != target:
            raise SpecError("one-based self-relative pointer inverse failed")
    flags = data["claim_flags"]
    if flags.get("nfl_topology_writer_implemented") is not True or flags.get(
        "nfl_selected_profile_offline_writeback_proved"
    ) is not True:
        raise SpecError("selected NFL offline topology proof claim is not true")
    if flags.get("nfl_changed_count_target_contract_probed") is not True:
        raise SpecError("NFL changed-count target/probe claim is not true")
    if flags.get("apf_topology_writer_implemented") is not True:
        raise SpecError("selected APF offline topology proof claim is not true")
    forbidden_true = [
        "changed_vertex_count_writer_implemented", "automatic_decimator_implemented",
        "edited_gltf_importer_implemented", "bounds_culling_proved",
        "material_uv_normal_writer_proved", "runtime_proved", "hardware_proved",
        "production_ready",
    ]
    if any(flags[name] for name in forbidden_true):
        raise SpecError("an unproved implementation/runtime claim is true")
    policy = data["data_policy"]
    if any(policy[name] for name in (
        "contains_retail_vertex_values", "contains_retail_index_values",
        "contains_retail_command_payload", "contains_retail_geometry",
    )):
        raise SpecError("retail geometry policy violated")
    selected = data["titles"]["nfl2k5_xbox"]["selected_first_topology_profile"]
    if selected["target"]["primary_command_word_count"] != nfl_element16_command_words(4):
        raise SpecError("selected NFL target exceeds or understates its exact word budget")
    if selected["status"] != "offline_writer_and_independent_verifier_implemented_runtime_unproved":
        raise SpecError("selected NFL profile status differs from proved boundary")
    reference = selected.get("profile_contract_reference")
    contract = selected.get("immutable_profile_contract")
    if reference != NFL_GROUP36_PROFILE_CONTRACT_REFERENCE or contract != NFL_GROUP36_PROFILE_CONTRACT:
        raise SpecError("selected NFL immutable profile contract differs")
    if hashlib.sha256(canonical_profile_contract_bytes(contract)).hexdigest() != reference["fingerprint"]:
        raise SpecError("selected NFL immutable profile fingerprint differs")
    apf = data["titles"]["apf2k8_xbox360"]["analogous_same_footprint_profile"]
    if apf["target"]["index_size_bytes"] != apf_index_payload_bytes(16, 4):
        raise SpecError("APF selected target index extent drift")
    if apf["status"] != "offline_writer_and_independent_verifier_implemented_runtime_unproved":
        raise SpecError("APF selected profile status differs from proved boundary")
    if (
        apf.get("proof", {}).get("changed_decoded_bytes") != 2
        or apf.get("proof", {}).get("allocation_slack_after_bytes") != 1_403
        or apf.get("draw_invariants", {}).get("draw_record_exact") is not True
    ):
        raise SpecError("APF selected topology proof metrics drift")
    subset = data["titles"]["nfl2k5_xbox"]["fixed_budget_subset_profile_gap"]
    probe = subset.get("selected_probe_boundary", {})
    if (
        subset.get("status") != "upper_deck_target_contract_and_count_only_fixed_span_probes_proved_writer_not_implemented"
        or probe.get("target_id") != "nfl2k5/stadium/o3280/c5/s1"
        or probe.get("changed_vertex_counts") != [4, 8]
        or probe.get("archive_writer_implemented") is not False
        or probe.get("runtime_proved") is not False
    ):
        raise SpecError("NFL changed-count selected probe boundary drift")
    return {
        "schema": "2k_static_topology_conformance_validation/v1",
        "selected_profile": selected["schema"],
        "nfl_command_words": selected["target"]["primary_command_word_count"],
        "apf_index_bytes": apf["target"]["index_size_bytes"],
        "gap_rows": len(data["gap_matrix"]),
        "topology_writer_implemented": True,
        "apf_topology_writer_implemented": True,
        "changed_count_target_probed": True,
        "changed_count_writer_implemented": False,
        "runtime_proved": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--write", action="store_true", help="write canonical JSON before validating")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.write:
        args.spec.parent.mkdir(parents=True, exist_ok=True)
        args.spec.write_bytes(canonical_bytes())
    validate_sources()
    validate_parent_specs()
    validate_roundtrip_claims()
    if not args.spec.is_file() or args.spec.is_symlink():
        raise SpecError(f"missing regular checked specification: {args.spec}")
    raw = args.spec.read_bytes()
    if raw != canonical_bytes():
        raise SpecError("checked specification bytes are not canonical")
    result = validate_spec(json.loads(raw))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, SpecError) as exc:
        print(f"STATIC_TOPOLOGY_CONFORMANCE_SPEC_ERROR: {exc}")
        raise SystemExit(1)
