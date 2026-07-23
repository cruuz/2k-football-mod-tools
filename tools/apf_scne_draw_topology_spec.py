#!/usr/bin/env python3
"""Recover and specify APF 2K8 SCNE draw/topology coupling.

The full mode independently walks every SCNE system part named by the pinned
inventory, decodes every draw window and native index element, and emits an
aggregate-only corpus report.  The normal mode regenerates the normative
machine-readable specification from that pinned report.  Neither output
contains retail vertex coordinates or retail index sequences.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any

import apf_inner
import apf_outer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
DEFAULT_INVENTORY = ROOT / "reports/assets/apf_scene_inventory.json"
DEFAULT_TRACE = (
    ROOT
    / "reports/assets/apf_player_shadow_skin_semantics_ghidra"
    / "player_shadow_skin_palette_trace.txt"
)
DEFAULT_CORPUS = ROOT / "reports/assets/apf_scne_draw_topology_corpus.v1.json"
DEFAULT_SPEC = ROOT / "reports/specs/apf2k8_scne_draw_topology.v1.json"
IMPLEMENTATION_PATHS = {
    "writer": ROOT / "tools/apf_stadium_node17_topology_patch.py",
    "independent_verifier": ROOT / "tools/apf_stadium_node17_topology_verify.py",
    "proof_recipe_helper": ROOT / "tools/apf_stadium_node17_topology_proof_recipes.py",
    "proof_report_generator": ROOT / "tools/apf_stadium_node17_topology_proof.py",
    "recipe_schema": ROOT / "reports/specs/apf2k8_scne_same_footprint_topology_recipe.schema.json",
    "public_nonretail_recipe": ROOT / "reports/asset_samples/apf_scene/stadium_node17_nonretail_permuted_strip_recipe.json",
    "changed_verification": ROOT / "reports/assets/apf_stadium_node17_same_footprint_topology_verification.json",
    "noop_verification": ROOT / "reports/assets/apf_stadium_node17_same_footprint_topology_noop_verification.json",
}

CORPUS_SCHEMA = "apf2k8_scne_draw_topology_corpus/v1"
SPEC_SCHEMA = "apf2k8_scne_draw_topology/v1"
INDEX_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
INVENTORY_SHA256 = "2243b5a3eb4dfcdebdda055e1a6fd9399b12b2704338f80ae4529d8476e85a17"
TRACE_SHA256 = "2e3b301a085bbbfb1ff7f735a05358c222efe14807b540ad440885b07af120c2"

EXPECTED = {
    "scne": 1_303,
    "nodes": 13_006,
    "draws": 47_112,
    "indices": 24_519_417,
    "draw_primitive_code": 6,
    "descriptor_primitive_code": 5,
    "null_optional_pointer": 46_348,
    "non_null_optional_pointer": 764,
}

NODE17 = {
    "outer_table_index": 14,
    "inner_file_index": 8,
    "node_index": 17,
    "node_name": "polySurface19930",
    "system_sha256": "b3028883de8d71d90850bab68ba29b91badd7107f8f9fbfab132a19a818379e4",
    "draw_offset": 375_712,
    "draw_sha256": "161a2e06c0b875b6679423f490c2c89691d1da9899003768a0f4eac01cfe873f",
    "index_offset": 375_760,
    "index_bytes": 8,
    "index_sha256": "96b383ee0d221556a56277315db425256549a46ccc5217a392181783327a6dc5",
    "vertex_count": 4,
    "index_count": 4,
}


class SpecError(ValueError):
    """The pinned evidence or a recovered invariant differs."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SpecError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: root must be an object")
    return value


def artifact_pin(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"implementation artifact missing: {path}")
    return {
        "path": str(path.relative_to(ROOT)),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def u32be(data: bytes, offset: int, what: str) -> int:
    require(0 <= offset <= len(data) - 4, f"{what}: u32 exceeds system part")
    return struct.unpack_from(">I", data, offset)[0]


def decode_indices(system: bytes, offset: int, count: int, bits: int) -> list[int]:
    require(bits in (16, 32), f"unsupported index width {bits}")
    size = bits // 8
    require(0 <= offset <= len(system) - count * size, "index payload exceeds system part")
    code = ">H" if bits == 16 else ">I"
    return [struct.unpack_from(code, system, offset + index * size)[0] for index in range(count)]


def strip_metrics(elements: list[int], restart: int) -> tuple[int, int]:
    strip: list[int] = []
    emitted = 0
    degenerate = 0
    for value in elements:
        if value == restart:
            strip.clear()
            continue
        strip.append(value)
        if len(strip) < 3:
            continue
        a, b, c = strip[-3:]
        if a == b or a == c or b == c:
            degenerate += 1
        else:
            emitted += 1
    return emitted, degenerate


def _pointer_target(field_offset: int, raw: int) -> int:
    return (field_offset + raw - 1) & 0xFFFFFFFF


def scan_corpus(index_path: Path, inventory_path: Path) -> dict[str, Any]:
    require(sha256_file(index_path) == INDEX_SHA256, "APF 0A identity differs")
    require(sha256_file(inventory_path) == INVENTORY_SHA256, "scene inventory identity differs")
    inventory = read_json(inventory_path)
    require(inventory.get("schema") == "apf_scene_inventory/v1", "scene inventory schema differs")
    require(inventory["summary"]["scne_parsed"] == EXPECTED["scne"], "scene inventory SCNE count differs")
    require(inventory["summary"]["scene_nodes"] == EXPECTED["nodes"], "scene inventory node count differs")

    by_outer: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for scene in inventory["scenes"]:
        by_outer[int(scene["outer_table_index"])].append(scene)

    archive = apf_outer.parse_archive(index_path)
    counts: Counter[str] = Counter()
    index_widths: Counter[int] = Counter()
    pointer_targets: Counter[str] = Counter()
    material_slots: set[int] = set()
    final_flags: Counter[int] = Counter()
    per_word_distinct: list[set[int]] = [set() for _ in range(12)]
    word_min: list[int | None] = [None] * 12
    word_max: list[int | None] = [None] * 12
    node17_summary: dict[str, Any] | None = None
    decoded_block_count = 0
    decoded_block_bytes = 0

    with apf_inner.ArchiveReader(archive) as reader:
        for outer_index, scenes in sorted(by_outer.items()):
            entry = archive.entries[outer_index]
            record = apf_inner.parse_iff(reader, entry)
            block_cache: dict[int, bytes] = {}
            for scene in scenes:
                part = scene["parts"][0]
                block_index = int(part["block_index"])
                if block_index not in block_cache:
                    block_cache[block_index] = apf_inner.decode_block(
                        reader, record, block_index, 64 * 1024 * 1024
                    )
                    decoded_block_count += 1
                    decoded_block_bytes += len(block_cache[block_index])
                start = int(part["offset"])
                length = int(part["length"])
                system = block_cache[block_index][start : start + length]
                require(sha256_bytes(system) == scene["system_sha256"], "SCNE system identity differs")
                counts["scne"] += 1
                for node in scene["nodes"]:
                    counts["nodes"] += 1
                    mesh = node["meshes"][0]
                    vertex_count = int(mesh["vertex_count"])
                    descriptor_primitive = int(mesh["primitive_type"])
                    require(
                        descriptor_primitive == EXPECTED["descriptor_primitive_code"],
                        "descriptor primitive code differs",
                    )
                    index_count = int(node["index_count"])
                    bits = int(node["index_component_bits"])
                    index_widths[bits] += 1
                    indices = decode_indices(system, int(node["index_offset"]), index_count, bits)
                    counts["indices"] += index_count
                    restart = (1 << bits) - 1
                    counts["restart_elements"] += sum(value == restart for value in indices)
                    for value in indices:
                        if value != restart:
                            require(value < vertex_count, "native index exceeds vertex count")

                    draw_ranges: list[tuple[int, int]] = []
                    draw_offset = int(node["draw_record_offset"])
                    draw_count = int(node["draw_record_count"])
                    for draw_index in range(draw_count):
                        offset = draw_offset + draw_index * 0x30
                        words = struct.unpack_from(">12I", system, offset)
                        counts["draws"] += 1
                        for word_index, value in enumerate(words):
                            per_word_distinct[word_index].add(value)
                            word_min[word_index] = value if word_min[word_index] is None else min(word_min[word_index], value)
                            word_max[word_index] = value if word_max[word_index] is None else max(word_max[word_index], value)

                        primitive, first, element_count, primitive_capacity = words[:4]
                        base_vertex, minimum_vertex, vertex_range = words[4:7]
                        optional_raw, material_slot, reserved_24, reserved_28, final_flag = words[7:]
                        require(primitive == EXPECTED["draw_primitive_code"], "draw primitive code differs")
                        require(element_count >= 3, "draw window has fewer than three elements")
                        require(first + element_count <= index_count, "draw window exceeds index payload")
                        require(primitive_capacity == element_count - 2, "draw primitive capacity differs")
                        require(base_vertex == 0, "nonzero serialized base vertex")
                        window = indices[first : first + element_count]
                        nonrestart = [value for value in window if value != restart]
                        require(nonrestart, "draw window has no non-restart element")
                        require(minimum_vertex == min(nonrestart), "draw minimum vertex differs")
                        require(vertex_range == max(nonrestart) - min(nonrestart) + 1, "draw vertex range differs")
                        require(reserved_24 == 0 and reserved_28 == 0, "reserved draw words are nonzero")
                        draw_ranges.append((first, first + element_count))
                        material_slots.add(material_slot)
                        final_flags[final_flag] += 1
                        emitted, degenerates = strip_metrics(window, restart)
                        counts["nondegenerate_triangles"] += emitted
                        counts["degenerate_triangles"] += degenerates
                        if optional_raw == 0:
                            counts["null_optional_pointer"] += 1
                        else:
                            counts["non_null_optional_pointer"] += 1
                            target = _pointer_target(offset + 0x1C, optional_raw)
                            require(0 <= target <= len(system) - 8, "optional draw pointer target is out of bounds")
                            require(target % 8 == 0, "optional draw pointer target is not eight-byte aligned")
                            pointer_targets["eight_byte_aligned_in_system"] += 1

                    ordered = sorted(draw_ranges)
                    require(ordered and ordered[0][0] == 0 and ordered[-1][1] == index_count, "draw windows do not cover index payload")
                    require(
                        all(ordered[index][1] == ordered[index + 1][0] for index in range(len(ordered) - 1)),
                        "draw windows overlap or leave a gap",
                    )
                    counts["partitioned_nodes"] += 1

                    if (
                        outer_index == NODE17["outer_table_index"]
                        and int(scene["inner_file_index"]) == NODE17["inner_file_index"]
                        and int(node["index"]) == NODE17["node_index"]
                    ):
                        require(scene["root_name"] == "stadium", "node17 scene name differs")
                        require(node["name"] == NODE17["node_name"], "node17 name differs")
                        require(scene["system_sha256"] == NODE17["system_sha256"], "node17 system hash differs")
                        require(draw_offset == NODE17["draw_offset"] and draw_count == 1, "node17 draw extent differs")
                        require(int(node["index_offset"]) == NODE17["index_offset"], "node17 index offset differs")
                        draw_bytes = system[draw_offset : draw_offset + 0x30]
                        index_bytes = system[NODE17["index_offset"] : NODE17["index_offset"] + NODE17["index_bytes"]]
                        require(sha256_bytes(draw_bytes) == NODE17["draw_sha256"], "node17 draw hash differs")
                        require(sha256_bytes(index_bytes) == NODE17["index_sha256"], "node17 index hash differs")
                        words = struct.unpack(">12I", draw_bytes)
                        node17_summary = {
                            "draw_record_count": 1,
                            "draw_record_offset": NODE17["draw_offset"],
                            "draw_record_sha256": NODE17["draw_sha256"],
                            "index_buffer_offset": NODE17["index_offset"],
                            "index_buffer_size_bytes": NODE17["index_bytes"],
                            "index_buffer_sha256": NODE17["index_sha256"],
                            "index_component_bits": bits,
                            "index_count": index_count,
                            "vertex_count": vertex_count,
                            "semantic_draw_invariants": {
                                "draw_primitive_code": words[0],
                                "first_index": words[1],
                                "element_count": words[2],
                                "primitive_capacity": words[3],
                                "base_vertex": words[4],
                                "minimum_vertex": words[5],
                                "vertex_range": words[6],
                                "optional_pointer_is_null": words[7] == 0,
                                "material_slot": words[8],
                                "reserved_words_are_zero": words[9] == words[10] == 0,
                                "final_flag": words[11],
                            },
                        }

    require(counts["scne"] == EXPECTED["scne"], "full scan SCNE count differs")
    require(counts["nodes"] == EXPECTED["nodes"], "full scan node count differs")
    require(counts["draws"] == EXPECTED["draws"], "full scan draw count differs")
    require(counts["indices"] == EXPECTED["indices"], "full scan index count differs")
    require(counts["null_optional_pointer"] == EXPECTED["null_optional_pointer"], "null optional pointer count differs")
    require(counts["non_null_optional_pointer"] == EXPECTED["non_null_optional_pointer"], "non-null optional pointer count differs")
    require(node17_summary is not None, "node17 profile target was not found")

    return {
        "schema": CORPUS_SCHEMA,
        "game": {"title": "All-Pro Football 2K8", "platform": "Xbox 360"},
        "data_policy": {
            "contains_retail_vertex_coordinates": False,
            "contains_retail_index_sequences": False,
            "contains_retail_draw_record_payloads": False,
            "contains_only_aggregate_metrics_hashes_offsets_and_semantic_invariants": True,
        },
        "source": {
            "index_path": str(index_path.relative_to(ROOT)),
            "index_sha256": INDEX_SHA256,
            "inventory_path": str(inventory_path.relative_to(ROOT)),
            "inventory_sha256": INVENTORY_SHA256,
        },
        "coverage": {
            "scne_resources": counts["scne"],
            "mesh_nodes": counts["nodes"],
            "draw_records": counts["draws"],
            "serialized_indices": counts["indices"],
            "partitioned_nodes": counts["partitioned_nodes"],
            "decoded_unique_blocks": decoded_block_count,
            "decoded_block_bytes": decoded_block_bytes,
            "index_width_nodes": {str(key): index_widths[key] for key in sorted(index_widths)},
        },
        "proved_invariants": {
            "all_descriptor_primitive_code_5": True,
            "all_draw_primitive_code_6": True,
            "draw_windows_exactly_partition_each_node_index_payload": True,
            "element_count_at_least_three": True,
            "primitive_capacity_equals_element_count_minus_two": True,
            "base_vertex_zero": True,
            "minimum_vertex_equals_window_nonrestart_minimum": True,
            "vertex_range_equals_window_nonrestart_maximum_minus_minimum_plus_one": True,
            "every_nonrestart_index_below_vertex_count": True,
            "reserved_24_and_28_zero": True,
            "all_nonnull_optional_targets_in_bounds_and_eight_byte_aligned": True,
        },
        "aggregate_values": {
            "restart_elements": counts["restart_elements"],
            "nondegenerate_triangles": counts["nondegenerate_triangles"],
            "degenerate_triangles": counts["degenerate_triangles"],
            "optional_pointer_null": counts["null_optional_pointer"],
            "optional_pointer_nonnull": counts["non_null_optional_pointer"],
            "material_slot_distinct": len(material_slots),
            "material_slot_minimum": min(material_slots),
            "material_slot_maximum": max(material_slots),
            "final_flag_distribution": {str(key): final_flags[key] for key in sorted(final_flags)},
            "draw_word_distinct_counts": [len(values) for values in per_word_distinct],
            "draw_word_minimums": word_min,
            "draw_word_maximums": word_max,
        },
        "selected_profile": node17_summary,
        "claim_flags": {
            "corpus_read_relationships_proved": True,
            "selected_same_footprint_profile_mechanically_closed": True,
            "writer_implemented": False,
            "runtime_proved": False,
            "hardware_proved": False,
            "production_ready": False,
        },
    }


def validate_trace(path: Path) -> dict[str, Any]:
    require(sha256_file(path) == TRACE_SHA256, "renderer trace identity differs")
    text = path.read_text(encoding="utf-8")
    required = {
        "0x84B108D8": "lwz r11,0x80(r28)",
        "0x84B108E0": "add r4,r31,r11",
        "0x84B2D4FC": "lwz r10,0x1c(r30)",
        "0x84B2D50C": "lwz r5,0x1c(r30)",
        "0x84B2D550": "lwz r10,0x8(r30)",
        "0x84B2D554": "lwz r8,0x10(r30)",
        "0x84B2D564": "lwz r9,0x4(r30)",
        "0x84B2D568": "lwz r7,0x0(r30)",
    }
    for address, instruction in required.items():
        require(f"GHIDRA {address} {instruction}" in text, f"renderer evidence missing {address}")
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": TRACE_SHA256,
        "required_instruction_count": len(required),
        "renderer_contract": (
            "the per-draw loop selects a 0x30-byte record; the native submission path "
            "forwards record +0x00 primitive code, +0x04 first element, +0x08 element "
            "count, +0x10 base vertex, and relocated/runtime +0x1c optional state"
        ),
    }


def build_spec(corpus: dict[str, Any], trace_path: Path) -> dict[str, Any]:
    require(corpus.get("schema") == CORPUS_SCHEMA, "corpus report schema differs")
    coverage = corpus["coverage"]
    require(coverage["scne_resources"] == EXPECTED["scne"], "pinned corpus SCNE count differs")
    require(coverage["mesh_nodes"] == EXPECTED["nodes"], "pinned corpus node count differs")
    require(coverage["draw_records"] == EXPECTED["draws"], "pinned corpus draw count differs")
    require(coverage["serialized_indices"] == EXPECTED["indices"], "pinned corpus index count differs")
    require(all(corpus["proved_invariants"].values()), "pinned corpus has an unproved invariant")
    selected = corpus["selected_profile"]
    require(selected["draw_record_sha256"] == NODE17["draw_sha256"], "selected draw hash differs")
    require(selected["index_buffer_sha256"] == NODE17["index_sha256"], "selected index hash differs")
    trace = validate_trace(trace_path)

    fields = [
        (0x00, "draw_primitive_code", "u32be", "proved_renderer_and_corpus", "6 in every retail draw; passed to native submission; paired mesh descriptor primitive is 5/D3DPT_TRIANGLESTRIP"),
        (0x04, "first_element", "u32be", "proved_renderer_and_corpus", "first serialized index element; all draw windows exactly partition the node index payload"),
        (0x08, "element_count", "u32be", "proved_renderer_and_corpus", "serialized strip elements in this draw, including restart values"),
        (0x0C, "primitive_capacity", "u32be", "proved_corpus", "element_count - 2; not the restart/degenerate-filtered triangle count"),
        (0x10, "base_vertex", "u32be", "proved_renderer_and_corpus", "passed to indexed submission; zero in every retail draw"),
        (0x14, "minimum_vertex", "u32be", "proved_corpus", "minimum non-restart index in this draw window"),
        (0x18, "vertex_range", "u32be", "proved_corpus", "maximum non-restart index - minimum_vertex + 1"),
        (0x1C, "optional_draw_state", "relptr_u32be_or_null", "partly_proved", "null in 46,348 draws; every 764 non-null one-based self-relative target is in-system and 8-byte aligned; relocated/runtime value is forwarded to the constant/state uploader; payload meaning remains unproved"),
        (0x20, "material_slot", "u32be", "proved_renderer", "material = instance_material_base + slot * 0xf0"),
        (0x24, "reserved_24", "u32be", "proved_zero_corpus", "zero in all retail draws; preserve"),
        (0x28, "reserved_28", "u32be", "proved_zero_corpus", "zero in all retail draws; preserve"),
        (0x2C, "render_flags_2c", "u32be", "observed", "retail values 0..3; exact meaning unproved; preserve"),
    ]

    return {
        "schema": SPEC_SCHEMA,
        "spec_version": 1,
        "title": "APF 2K8 Xbox 360 SCNE draw/topology coupling",
        "status": "all retail draw/index relationships are corpus-closed; node17 same-footprint index replacement has a fail-closed copied-volume writer and independent offline verifier; runtime acceptance remains unproved",
        "data_policy": corpus["data_policy"],
        "byte_conventions": {
            "draw_fields": "big-endian u32",
            "index_components": "big-endian u16 or u32",
            "relative_pointer": "target = (field_offset + stored_u32 - 1) modulo 2^32; stored zero is null",
        },
        "draw_record": {
            "size_bytes": 48,
            "fields": [
                {"offset_bytes": offset, "size_bytes": 4, "name": name, "storage": storage, "status": status, "rule": rule}
                for offset, name, storage, status, rule in fields
            ],
            "window_contract": [
                "sort records by first_element; windows must begin at zero, be contiguous and nonoverlapping, and end at node.index_count",
                "for each window require element_count >= 3 and first_element + element_count <= node.index_count",
                "primitive_capacity equals element_count - 2 even when restart or repeated-index degenerates reduce emitted triangles",
                "minimum_vertex and vertex_range are derived from non-restart elements before applying base_vertex",
            ],
        },
        "native_topology": {
            "descriptor_primitive_code": 5,
            "descriptor_primitive_name": "D3DPT_TRIANGLESTRIP",
            "draw_submission_primitive_code": 6,
            "index_widths_bits": [16, 32],
            "restart": {"16": 65535, "32": 4294967295},
            "decode": [
                "restart clears the current strip",
                "after three elements, alternate strip winding; omit repeated-index triangles as degenerates",
                "every non-restart element must be below vertex_count",
            ],
        },
        "corpus_proof": {
            "path": str(DEFAULT_CORPUS.relative_to(ROOT)),
            "sha256": sha256_bytes(canonical(corpus)),
            **coverage,
            **corpus["aggregate_values"],
        },
        "renderer_proof": trace,
        "same_footprint_profile": {
            "profile": "outer14_inner8_node17_four_be16_strip/v1",
            "status": "offline_writer_and_independent_verifier_implemented_runtime_unproved",
            "target": {
                "outer_table_index": 14,
                "inner_file_index": 8,
                "inner_name": "stadium",
                "node_index": 17,
                "node_name": NODE17["node_name"],
                "draw_record_offset": NODE17["draw_offset"],
                "draw_record_size_bytes": 48,
                "draw_record_sha256": NODE17["draw_sha256"],
                "index_buffer_offset": NODE17["index_offset"],
                "index_buffer_size_bytes": NODE17["index_bytes"],
                "index_buffer_sha256": NODE17["index_sha256"],
                "index_component_bits": 16,
                "index_count": 4,
                "vertex_count": 4,
            },
            "admission": [
                "recipe supplies exactly four JSON integers and no additional topology fields",
                "indices are a permutation of 0,1,2,3 with no restart or duplicate",
                "native strip decode emits exactly two nondegenerate triangles",
                "the one draw remains first=0, count=4, capacity=2, base=0, minimum=0, range=4",
                "all 48 draw bytes, all vertex/declaration/descriptor bytes, every pointer, and all non-index SCNE bytes remain exact",
                "the eight-byte decoded index allocation does not grow or move",
            ],
            "why_draw_rewrite_is_forbidden": "the admitted permutation preserves every derived draw invariant; changing a draw byte would expand the proof surface without being mechanically necessary",
            "compressed_container_rule": "rebuild only stadium DRAM block 0; decoded length and fixed outer allocation remain exact; reject H7A overflow before publication",
            "implementation": {
                name: artifact_pin(path)
                for name, path in IMPLEMENTATION_PATHS.items()
            },
            "runtime_status": "unproved",
        },
        "changed_count_boundary": {
            "status": "deferred",
            "required_updates": [
                "node +0xa8 index_count and index payload extent",
                "every draw first/count/capacity/minimum/range field",
                "mesh descriptor vertex_count and every stream byte_length/end pointer",
                "complete source-record remap across every active vertex stream",
                "bounds/culling ownership and compressed-part budget",
            ],
        },
        "mandatory_rejections": [
            "source/corpus/profile hash or structural drift",
            "draw windows that overlap, leave gaps, or escape the index allocation",
            "index outside the admitted vertex range, restart, duplicate, unexpected degenerate, or winding/decode mismatch",
            "any draw, descriptor, declaration, stream, vertex, hierarchy, matrix, material, unknown, sibling-part, footer, or outer-complement change",
            "decoded-part growth, H7A overflow, source mutation, unsafe output path, or non-exclusive publication",
        ],
        "claim_flags": {
            "draw_layout_proved": True,
            "draw_index_coupling_corpus_proved": True,
            "node17_same_footprint_profile_closed": True,
            "node17_writer_implemented": True,
            "node17_independent_offline_verifier_proved": True,
            "changed_count_writer_implemented": False,
            "bounds_culling_proved": False,
            "runtime_proved": False,
            "hardware_proved": False,
            "production_ready": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--corpus-output", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--spec-output", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--full", action="store_true", help="rescan every SCNE from the user-owned source")
    args = parser.parse_args(argv)
    try:
        if args.full:
            corpus = scan_corpus(args.index, args.inventory)
            args.corpus_output.parent.mkdir(parents=True, exist_ok=True)
            args.corpus_output.write_bytes(canonical(corpus))
        else:
            corpus = read_json(args.corpus_output)
        spec = build_spec(corpus, args.trace)
        args.spec_output.parent.mkdir(parents=True, exist_ok=True)
        args.spec_output.write_bytes(canonical(spec))
        print(
            "APF_SCNE_DRAW_TOPOLOGY_SPEC_PASS "
            f"scne={spec['corpus_proof']['scne_resources']} "
            f"nodes={spec['corpus_proof']['mesh_nodes']} "
            f"draws={spec['corpus_proof']['draw_records']} "
            f"indices={spec['corpus_proof']['serialized_indices']} "
            "node17_profile=true writer=true independent_verify=true runtime=false hardware=false "
            f"sha256={sha256_file(args.spec_output)}"
        )
        return 0
    except (SpecError, apf_outer.FormatError, apf_inner.FormatError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
