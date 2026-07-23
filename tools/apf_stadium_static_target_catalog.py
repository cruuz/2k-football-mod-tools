#!/usr/bin/env python3
"""Build the hashes-only APF outer-14 stadium static POSITION target catalog.

The catalog deliberately contains no vertex coordinates.  It records the
fixed IFF/H7A ownership envelope once and then pins every additional node that
has one bounded FLOAT32x3 POSITION0 stream and no blend declaration.  These
are structural-static candidates only; matrix/attachment semantics and
runtime rigidity are not inferred.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any

import apf_inner
import apf_outer
import apf_scene
from apf_texture_patch import compress_h7a


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GAME_DIR = ROOT / "extracted/All-Pro Football 2K8 (USA)"
DEFAULT_REPORT = ROOT / "reports/assets/apf_stadium_static_position_target_catalog.json"

SCHEMA = "apf2k8_stadium_static_position_target_catalog/v1"
SOURCE_PACKS = {
    "0A": {
        "size_bytes": 1_140_850_688,
        "sha256": "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    },
    "1A": {
        "size_bytes": 1_140_850_688,
        "sha256": "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
    },
}

OUTER_INDEX = 14
OUTER_NAME_ID = 0x02BAE370
OUTER_PACK = "1A"
OUTER_PACK_OFFSET = 404_643_840
OUTER_LENGTH = 12_931_072
OUTER_SHA256 = "347503ffdcd910b57425584869e1520238b1298e516f643936568b83d5a5a07a"
INNER_INDEX = 8
INNER_FILE_ID = 0xE604044F
INNER_TYPE_HASH = 0xE26C9B5D
INNER_NAME = "stadium"
SYSTEM_LENGTH = 4_199_168
SYSTEM_SHA256 = "b3028883de8d71d90850bab68ba29b91badd7107f8f9fbfab132a19a818379e4"
VRAM_LENGTH = 12_918_784
VRAM_SHA256 = "5662f3866f83e33bab217f80ac8e9a6267ae94842c0727f77019355cc2cb3a95"
PROVED_FIRST_NODE = 17
SECOND_NODE = 3
POSITION_CODE = 0x002A23B9
POSITION_BYTES = 12
PRIMITIVE_TRIANGLE_STRIP = 5
FOOTER_TOTAL = 954
SOURCE_FILE_LENGTH = 12_928_092
SOURCE_TAIL_LENGTH = 2_026


class CatalogError(ValueError):
    """The source, structural selection, or deterministic report drifted."""


class BytesReader:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise apf_inner.FormatError("memory entry read is out of bounds")
        return self.data[offset : offset + size]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(value: int) -> str:
    return f"0x{value:08x}"


def _span(data: bytes, offset: int, length: int) -> dict[str, Any]:
    if offset < 0 or length < 0 or offset + length > len(data):
        raise CatalogError(f"span 0x{offset:x}+0x{length:x} is out of bounds")
    return {"offset": offset, "length": length, "sha256": _sha(data[offset : offset + length])}


def _indices(data: bytes, node: dict[str, Any]) -> tuple[list[int], int]:
    bits = int(node["index_component_bits"])
    count = int(node["index_count"])
    offset = int(node["index_offset"])
    if bits == 16:
        values = list(struct.unpack_from(f">{count}H", data, offset))
        return values, 0xFFFF
    if bits == 32:
        values = list(struct.unpack_from(f">{count}I", data, offset))
        return values, 0xFFFFFFFF
    raise CatalogError(f"unsupported index width {bits}")


def _strip_metrics(values: list[int], restart: int) -> dict[str, int]:
    strip: list[int] = []
    triangles = 0
    degenerates = 0
    restarts = 0
    for value in values:
        if value == restart:
            strip.clear()
            restarts += 1
            continue
        strip.append(value)
        if len(strip) < 3:
            continue
        triangle = strip[-3:]
        if len(set(triangle)) == 3:
            triangles += 1
        else:
            degenerates += 1
    return {
        "restart_count": restarts,
        "nondegenerate_triangle_count": triangles,
        "degenerate_window_count": degenerates,
    }


def _part_catalog(record: apf_inner.IFFRecord, blocks: list[bytes]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for file in record.files:
        parts: list[dict[str, Any]] = []
        for part_index, part in enumerate(file.parts):
            payload = blocks[part.block_index][part.offset : part.offset + part.length]
            if len(payload) != part.length:
                raise CatalogError("inner part exceeds decoded block")
            parts.append(
                {
                    "part_index": part_index,
                    "block_index": part.block_index,
                    "offset": part.offset,
                    "length": part.length,
                    "sha256": _sha(payload),
                    "target_position_owner": file.index == INNER_INDEX and part_index == 0,
                }
            )
        output.append(
            {
                "file_index": file.index,
                "file_id": _hex(file.file_id),
                "type_hash": _hex(file.type_hash),
                "type_name": file.type_name,
                "name": file.name,
                "parts": parts,
            }
        )
    return output


def _candidate(
    system: bytes,
    scene: dict[str, Any],
    node: dict[str, Any],
) -> dict[str, Any] | None:
    if node["mesh_descriptor_count"] != 1 or len(node["meshes"]) != 1:
        return None
    mesh = node["meshes"][0]
    position = mesh.get("position")
    if not isinstance(position, dict) or position.get("format") != "float32x3":
        return None
    declarations = node["vertex_declarations"]
    semantics = [item.get("indexed_semantic") for item in declarations]
    if any(
        isinstance(semantic, str)
        and semantic.startswith(("BLENDINDICES", "BLENDWEIGHT"))
        for semantic in semantics
    ):
        return None
    position_declarations = [
        item
        for item in declarations
        if item.get("indexed_semantic") == "POSITION0"
        and item.get("semantic") == "POSITION"
    ]
    if len(position_declarations) != 1:
        return None
    declaration = position_declarations[0]
    if int(str(declaration["format_code"]), 16) != POSITION_CODE:
        return None
    if int(mesh["primitive_type"]) != PRIMITIVE_TRIANGLE_STRIP:
        return None
    if int(node["index_component_bits"]) not in (16, 32) or int(node["index_count"]) < 3:
        return None
    stream_index = int(declaration["stream_index"])
    byte_offset = int(declaration["byte_offset"])
    if stream_index < 0 or stream_index >= len(mesh["streams"]):
        raise CatalogError("POSITION stream index escaped descriptor")
    stream = mesh["streams"][stream_index]
    stride = int(stream["stride"])
    vertex_count = int(mesh["vertex_count"])
    stream_start = int(stream["start"])
    stream_end = int(stream["end"])
    if byte_offset + POSITION_BYTES > stride or stream_end - stream_start != vertex_count * stride:
        raise CatalogError("POSITION lane is not bounded by its retail stream")

    values, restart = _indices(system, node)
    if max((value for value in values if value != restart), default=-1) >= vertex_count:
        raise CatalogError("catalog candidate index exceeds vertex count")
    position_payload = b"".join(
        system[
            stream_start + vertex * stride + byte_offset :
            stream_start + vertex * stride + byte_offset + POSITION_BYTES
        ]
        for vertex in range(vertex_count)
    )
    if len(position_payload) != vertex_count * POSITION_BYTES:
        raise CatalogError("position lane extraction length drift")

    hierarchy = node["hierarchy"]
    if not isinstance(hierarchy, dict):
        raise CatalogError("candidate has no bounded hierarchy table")
    draw_offset = node["draw_record_offset"]
    draw_count = int(node["draw_record_count"])
    if draw_offset is None or draw_count < 1:
        raise CatalogError("candidate has no bounded draw record")
    declaration_offset = int(declarations[0]["offset"])
    declaration_length = len(declarations) * apf_scene.DECLARATION_RECORD_SIZE
    descriptor_offset = int(mesh["offset"])
    descriptor_length = 0x14 + int(mesh["stream_count"]) * apf_scene.STREAM_RECORD_SIZE
    matrix_offset = int(scene["matrix_offset"]) + int(node["index"]) * apf_scene.MATRIX_SIZE
    if int(scene["matrix_count"]) != int(scene["scene_node_count"]):
        raise CatalogError("matrix/node ordinal cardinality differs")

    declaration_catalog = [
        {
            "index": int(item["index"]),
            "indexed_semantic": item["indexed_semantic"],
            "indexed_semantic_hash": item["indexed_semantic_hash"],
            "semantic": item["semantic"],
            "semantic_hash": item["semantic_hash"],
            "stream_index": int(item["stream_index"]),
            "byte_offset": int(item["byte_offset"]),
            "format_code": item["format_code"],
            "format_name": item["format_name"],
        }
        for item in declarations
    ]
    streams = []
    for item in mesh["streams"]:
        record_offset = int(item["record_offset"])
        streams.append(
            {
                "index": int(item["index"]),
                "record": _span(system, record_offset, apf_scene.STREAM_RECORD_SIZE),
                "flags": item["flags"],
                "enabled": int(item["enabled"]),
                "stride": int(item["stride"]),
                "payload": _span(system, int(item["start"]), int(item["byte_length"])),
            }
        )

    priority = "mesh_like_single_hierarchy"
    if int(hierarchy["count"]) != 1:
        priority = "mesh_like_multi_hierarchy_attachment_unknown"
    if not any(semantic == "NORMAL0" for semantic in semantics):
        priority = "position_only_effect_or_variant"
    return {
        "candidate_id": f"outer14.inner8.node{int(node['index'])}",
        "classification": "structural_static_same_count_position_candidate",
        "priority_tier": priority,
        "runtime_rigid_attachment_proved": False,
        "runtime_visibility_proved": False,
        "node": {
            "index": int(node["index"]),
            "name": node["name"],
            "name_crc32": node["name_crc32"],
            "type_or_flags_0c": node["type_or_flags_0c"],
            "hash_10": node["hash_10"],
            "record": _span(system, int(node["offset"]), apf_scene.SCENE_NODE_SIZE),
        },
        "matrix_slot_by_serialized_node_ordinal": {
            **_span(system, matrix_offset, apf_scene.MATRIX_SIZE),
            "semantic_attachment_interpretation_proved": False,
        },
        "hierarchy": {
            **_span(system, int(hierarchy["offset"]), int(hierarchy["byte_length"])),
            "record_count": int(hierarchy["count"]),
            "topology_status": hierarchy["topology_status"],
        },
        "draw_records": {
            **_span(system, int(draw_offset), draw_count * apf_scene.DRAW_RECORD_SIZE),
            "count": draw_count,
            "material_slot_semantics_proved": False,
        },
        "index_topology": {
            **_span(
                system,
                int(node["index_offset"]),
                int(node["index_count"]) * (int(node["index_component_bits"]) // 8),
            ),
            "component_bits": int(node["index_component_bits"]),
            "index_count": int(node["index_count"]),
            "primitive_code": int(mesh["primitive_type"]),
            "primitive_name": "D3DPT_TRIANGLESTRIP",
            **_strip_metrics(values, restart),
        },
        "declarations": {
            **_span(system, declaration_offset, declaration_length),
            "count": len(declarations),
            "items": declaration_catalog,
            "has_blendindices_or_blendweight": False,
        },
        "mesh_descriptor_and_stream_records": {
            **_span(system, descriptor_offset, descriptor_length),
            "stream_count": int(mesh["stream_count"]),
        },
        "streams": streams,
        "position0": {
            "format_code": _hex(POSITION_CODE),
            "format_name": "float32x3",
            "serialized_byte_order": "big-endian",
            "vertex_count": vertex_count,
            "stream_index": stream_index,
            "stream_start": stream_start,
            "stream_stride": stride,
            "byte_offset": byte_offset,
            "lane_bytes_per_vertex": POSITION_BYTES,
            "authorized_lane_bytes": vertex_count * POSITION_BYTES,
            "last_lane_end": stream_start + (vertex_count - 1) * stride + byte_offset + POSITION_BYTES,
            "retail_lane_sha256": _sha(position_payload),
            "retail_vertex_values_in_catalog": False,
        },
    }


def _second_target_fit(
    original_entry: bytes,
    record: apf_inner.IFFRecord,
    blocks: list[bytes],
    stored_blocks: list[bytes],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    position = candidate["position0"]
    vertex_count = int(position["vertex_count"])
    stream_start = int(position["stream_start"])
    stride = int(position["stream_stride"])
    byte_offset = int(position["byte_offset"])
    changed_block0 = bytearray(blocks[0])
    changed_payload = bytearray()
    authorized: set[int] = set()
    for vertex in range(vertex_count):
        lane = stream_start + vertex * stride + byte_offset
        source = struct.unpack_from(">3f", blocks[0], lane)
        authored = tuple(source[axis] + float(axis + 1) for axis in range(3))
        if not all(math.isfinite(value) for value in authored):
            raise CatalogError("second-target derived translation is non-finite")
        encoded = struct.pack(">3f", *authored)
        if struct.unpack(">3f", encoded) != authored:
            raise CatalogError("second-target derived translation silently rounds")
        changed_block0[lane : lane + POSITION_BYTES] = encoded
        changed_payload.extend(encoded)
        authorized.update(range(lane, lane + POSITION_BYTES))
    changed_offsets = {
        index
        for index, (before, after) in enumerate(zip(blocks[0], changed_block0))
        if before != after
    }
    if not changed_offsets or not changed_offsets.issubset(authorized):
        raise CatalogError("second-target edit escaped or failed to change POSITION lanes")

    descriptor = record.blocks[0]
    if descriptor.wrapper is None or descriptor.wrapper.shift != 12:
        raise CatalogError("second-target DRAM H7A profile drift")
    compressed = compress_h7a(bytes(changed_block0), descriptor.wrapper.shift)
    new_stored0 = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(changed_block0),
        apf_inner.H7A_HEADER_SIZE + len(compressed),
        descriptor.unknown_10,
        descriptor.wrapper.shift,
    ) + compressed
    if apf_inner.decompress_h7a(
        new_stored0[apf_inner.H7A_HEADER_SIZE :],
        len(changed_block0),
        descriptor.wrapper.shift,
    ) != bytes(changed_block0):
        raise CatalogError("second-target H7A round-trip failed")

    footer = original_entry[record.file_length : record.file_length + FOOTER_TOTAL]
    if len(footer) != FOOTER_TOTAL:
        raise CatalogError("second-target footer length drift")
    header = bytearray(original_entry[: record.header_size])
    new_file_length = record.header_size + len(new_stored0) + len(stored_blocks[1])
    struct.pack_into(">I", header, 0x08, new_file_length)
    struct.pack_into(">I", header, 0x38, len(new_stored0))
    struct.pack_into(">I", header, 0x54, record.header_size + len(new_stored0))
    active = bytes(header) + new_stored0 + stored_blocks[1] + footer
    if len(active) > OUTER_LENGTH:
        raise CatalogError("second-target representative edit exceeds outer allocation")
    rebuilt = active + bytes(OUTER_LENGTH - len(active))
    rebuilt_record = apf_inner.parse_iff(BytesReader(rebuilt), record.entry)
    rebuilt_blocks = [
        apf_inner.decode_block(BytesReader(rebuilt), rebuilt_record, index, 1 << 30)
        for index in range(rebuilt_record.block_count)
    ]
    if rebuilt_blocks != [bytes(changed_block0), blocks[1]]:
        raise CatalogError("second-target rebuilt IFF decoded bytes differ")

    before_parts = {
        (file.index, part_index): _sha(
            blocks[part.block_index][part.offset : part.offset + part.length]
        )
        for file in record.files
        for part_index, part in enumerate(file.parts)
    }
    after_parts = {
        (file.index, part_index): _sha(
            rebuilt_blocks[part.block_index][part.offset : part.offset + part.length]
        )
        for file in rebuilt_record.files
        for part_index, part in enumerate(file.parts)
    }
    changed_parts = sorted(key for key in before_parts if before_parts[key] != after_parts[key])
    if changed_parts != [(INNER_INDEX, 0)]:
        raise CatalogError(f"second-target changed unexpected inner parts: {changed_parts}")
    return {
        "candidate_id": candidate["candidate_id"],
        "node_index": SECOND_NODE,
        "node_name": candidate["node"]["name"],
        "selection_reason": (
            "24 vertices and three draw records extend the first four-vertex/one-draw proof while "
            "retaining one hierarchy record, FLOAT32x3 POSITION0, BE16 strip topology, one stream, "
            "and no blend declarations"
        ),
        "new_structural_coverage": {"vertex_count": vertex_count, "draw_record_count": 3},
        "representative_local_only_fit_witness": {
            "operation": "add exact +1 X, +2 Y, +3 Z to each serialized POSITION0",
            "recipe_coordinates_committed": False,
            "output_or_replacement_bytes_committed": False,
            "authored_position_payload_sha256": _sha(bytes(changed_payload)),
            "authorized_position_lane_bytes": len(authorized),
            "changed_decoded_block0_bytes": len(changed_offsets),
            "changed_decoded_bytes_subset_of_authorized_lanes": True,
            "decoded_block0_sha256": _sha(bytes(changed_block0)),
            "stored_block0_sha256": _sha(new_stored0),
            "stored_block0_length_before": len(stored_blocks[0]),
            "stored_block0_length_after": len(new_stored0),
            "stored_block0_growth_bytes": len(new_stored0) - len(stored_blocks[0]),
            "rebuilt_file_length": new_file_length,
            "rebuilt_outer_sha256": _sha(rebuilt),
            "allocation_slack_after_bytes": OUTER_LENGTH - len(active),
            "changed_inner_parts": [{"file_index": INNER_INDEX, "part_index": 0}],
            "all_twelve_non_target_parts_exact": True,
            "stored_block1_exact": True,
            "footer_exact": True,
            "zero_tail_exact": True,
            "runtime_visibility_proved": False,
            "runtime_rigid_attachment_proved": False,
        },
        "dispatcher_handoff": {
            "target_key": "outer14.inner8.node3",
            "required_recipe_position_count": vertex_count,
            "required_position_type": "FLOAT32x3_BE",
            "required_vertex_order": "retail_stream_order",
            "authorized_edit": "replace exactly the 12-byte POSITION0 lane at byte 0 of each 24-byte vertex",
            "preserve_exact": (
                "UV/normal interleaves, node/matrix/hierarchy/draw/index/declarations/descriptor, "
                "stadium VRAM, eleven sibling parts, stored block1, footer, outer size and all pack bytes outside outer14"
            ),
            "overflow_rule": "refuse when rebuilt block0 stored length exceeds the catalog H7A maximum",
            "general_topology_or_attachment_writer": False,
        },
    }


def build_report(game_dir: Path = DEFAULT_GAME_DIR) -> dict[str, Any]:
    game_dir = game_dir.expanduser().resolve(strict=True)
    for name, identity in SOURCE_PACKS.items():
        path = game_dir / name
        if not path.is_file() or path.stat().st_size != identity["size_bytes"]:
            raise CatalogError(f"source pack size/regular-file identity drift: {name}")
    archive = apf_outer.parse_archive(game_dir / "0A")
    if len(archive.entries) <= OUTER_INDEX:
        raise CatalogError("source archive has no outer14")
    entry = archive.entries[OUTER_INDEX]
    if not (
        entry.name_id == OUTER_NAME_ID
        and entry.size == OUTER_LENGTH
        and len(entry.segments) == 1
        and entry.segments[0].pack_name == OUTER_PACK
        and entry.segments[0].pack_offset == OUTER_PACK_OFFSET
        and entry.segments[0].size == OUTER_LENGTH
    ):
        raise CatalogError("outer14 routing/allocation drift")
    with apf_inner.ArchiveReader(archive) as reader:
        original_entry = reader.read(entry, 0, entry.size)
        record = apf_inner.parse_iff(reader, entry)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        stored_blocks = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]
    if _sha(original_entry) != OUTER_SHA256:
        raise CatalogError("outer14 payload identity drift")
    if record.header_size != 292 or record.file_length != SOURCE_FILE_LENGTH:
        raise CatalogError("IFF header/file-length drift")
    if record.block_count != 2 or record.file_count != 9 or len(record.files) != 9:
        raise CatalogError("IFF block/file cardinality drift")
    inner = record.files[INNER_INDEX]
    if not (
        inner.file_id == INNER_FILE_ID
        and inner.type_hash == INNER_TYPE_HASH
        and inner.name == INNER_NAME
        and inner.type_name == "SCNE"
        and inner.parts == (
            apf_inner.FilePart(0, 0, SYSTEM_LENGTH),
            apf_inner.FilePart(1, 0, VRAM_LENGTH),
        )
    ):
        raise CatalogError("stadium inner-file identity/ownership drift")
    system = blocks[0][:SYSTEM_LENGTH]
    vram = blocks[1][:VRAM_LENGTH]
    if _sha(system) != SYSTEM_SHA256 or _sha(vram) != VRAM_SHA256:
        raise CatalogError("stadium DRAM/VRAM identity drift")

    scene = apf_scene.parse_scene_system_part(
        system, outer_index=OUTER_INDEX, inner_index=INNER_INDEX, capture_geometry=False
    )
    if scene["root_name"] != INNER_NAME or scene["scene_node_count"] != 89 or scene["matrix_count"] != 89:
        raise CatalogError("stadium SCNE scene/matrix cardinality drift")
    all_candidates = [
        candidate
        for node in scene["nodes"]
        if (candidate := _candidate(system, scene, node)) is not None
    ]
    if len(all_candidates) != 78:
        raise CatalogError(f"eligible target count drift: {len(all_candidates)}")
    if [item["node"]["index"] for item in all_candidates] != sorted(
        item["node"]["index"] for item in all_candidates
    ):
        raise CatalogError("candidate order is not serialized node order")
    proved = next((item for item in all_candidates if item["node"]["index"] == PROVED_FIRST_NODE), None)
    if proved is None:
        raise CatalogError("proved node17 disappeared from eligibility set")
    additional = [item for item in all_candidates if item["node"]["index"] != PROVED_FIRST_NODE]
    second = next((item for item in additional if item["node"]["index"] == SECOND_NODE), None)
    if second is None:
        raise CatalogError("selected node3 disappeared from additional targets")

    footer_offset = record.file_length
    footer = original_entry[footer_offset : footer_offset + FOOTER_TOTAL]
    tail = original_entry[footer_offset + FOOTER_TOTAL :]
    if len(footer) != FOOTER_TOTAL or len(tail) != SOURCE_TAIL_LENGTH or any(tail):
        raise CatalogError("footer/fixed-allocation tail drift")
    maximum_file_length = OUTER_LENGTH - FOOTER_TOTAL
    maximum_stored_block0 = maximum_file_length - record.header_size - len(stored_blocks[1])
    if maximum_stored_block0 != len(stored_blocks[0]) + SOURCE_TAIL_LENGTH:
        raise CatalogError("H7A rebuild envelope arithmetic drift")

    blocks_catalog = []
    for block, stored in zip(record.blocks, stored_blocks):
        if block.wrapper is None:
            raise CatalogError("cataloged outer block is not H7A wrapped")
        blocks_catalog.append(
            {
                "block_index": block.descriptor_index,
                "name_hash": _hex(block.name_hash),
                "type_hash": _hex(block.type_hash),
                "unknown_08": block.unknown_08,
                "uncompressed_length": block.uncompressed_length,
                "unknown_10": block.unknown_10,
                "start_offset": block.start_offset,
                "stored_length": block.stored_length,
                "stored_sha256": _sha(stored),
                "decoded_sha256": _sha(blocks[block.descriptor_index]),
                "h7a": {
                    "magic": _hex(block.wrapper.magic),
                    "uncompressed_length": block.wrapper.uncompressed_length,
                    "stored_length": block.wrapper.compressed_length,
                    "unknown": block.wrapper.unknown,
                    "shift": block.wrapper.shift,
                },
            }
        )

    second_fit = _second_target_fit(
        original_entry, record, blocks, stored_blocks, second
    )
    priority_counts: dict[str, int] = {}
    for candidate in additional:
        tier = str(candidate["priority_tier"])
        priority_counts[tier] = priority_counts.get(tier, 0) + 1
    return {
        "schema": SCHEMA,
        "status": (
            "77 additional outer14 stadium structural-static same-count FLOAT32x3 POSITION0 "
            "targets cataloged; runtime rigidity and visibility remain unproved"
        ),
        "contains_retail_vertex_values": False,
        "contains_replacement_bytes": False,
        "normative_format_spec": {
            "path": "reports/specs/apf2k8_scne_static_serializer.v1.json",
            "schema": "apf2k8_scne_static_serializer/v1",
            "relationship": "upstream grammar and same-count serializer contract; this catalog is pinned downstream by that spec's evidence ledger",
        },
        "source_identity": {
            "game": "All-Pro Football 2K8 Xbox 360 USA retail",
            "known_complete_pack_identities": SOURCE_PACKS,
            "outer_payload_sha256_recomputed": True,
            "complete_pack_sha256_recomputed_by_this_generator": False,
        },
        "selection_contract": {
            "scope": "outer14/inner8 stadium only; immediate dispatcher extension of the first proved writer container",
            "required": [
                "exactly one parsed mesh descriptor",
                "exactly one POSITION0/POSITION declaration with format 0x002a23b9 FLOAT32x3",
                "POSITION lane bounded inside its declared stream stride and payload",
                "no BLENDINDICES or BLENDWEIGHT declaration",
                "D3DPT_TRIANGLESTRIP primitive 5 with validated BE16 or BE32 indices",
                "at least one bounded draw record and a bounded hierarchy table",
            ],
            "not_inferred": [
                "runtime rigid attachment",
                "matrix semantics despite matrix/node ordinal pairing",
                "material-slot meaning",
                "runtime visibility or hardware acceptance",
            ],
        },
        "container": {
            "outer": {
                "table_index": OUTER_INDEX,
                "name_id": _hex(OUTER_NAME_ID),
                "offset_blocks": entry.offset_blocks,
                "virtual_offset": entry.virtual_offset,
                "physical_pack": OUTER_PACK,
                "physical_pack_offset": OUTER_PACK_OFFSET,
                "fixed_allocation_bytes": OUTER_LENGTH,
                "sha256": OUTER_SHA256,
            },
            "iff": {
                "header": _span(original_entry, 0, record.header_size),
                "header_size": record.header_size,
                "file_length": record.file_length,
                "block_count": record.block_count,
                "file_count": record.file_count,
                "blocks": blocks_catalog,
                "footer": {**_span(original_entry, footer_offset, FOOTER_TOTAL), "payload_size": record.footer.payload_size if record.footer else None},
                "zero_tail": {"offset": footer_offset + FOOTER_TOTAL, "length": len(tail), "sha256": _sha(tail), "all_zero": True},
            },
            "h7a_rebuild_envelope": {
                "fixed_outer_allocation_bytes": OUTER_LENGTH,
                "fixed_header_bytes": record.header_size,
                "fixed_footer_bytes": FOOTER_TOTAL,
                "fixed_stored_block1_bytes": len(stored_blocks[1]),
                "source_stored_block0_bytes": len(stored_blocks[0]),
                "maximum_file_length": maximum_file_length,
                "maximum_stored_block0_bytes": maximum_stored_block0,
                "maximum_h7a_payload_bytes_excluding_20_byte_wrapper": maximum_stored_block0 - apf_inner.H7A_HEADER_SIZE,
                "source_headroom_bytes": maximum_stored_block0 - len(stored_blocks[0]),
                "block0_required_shift": 12,
                "overflow_policy": "fail closed before pack write",
                "headroom_is_not_a_guarantee_for_arbitrary_position_data": True,
            },
            "inner_files_and_all_part_ownership": _part_catalog(record, blocks),
        },
        "scene": {
            "inner_file_index": INNER_INDEX,
            "inner_file_id": _hex(INNER_FILE_ID),
            "inner_type_hash": _hex(INNER_TYPE_HASH),
            "inner_name": INNER_NAME,
            "system_part": _span(blocks[0], 0, SYSTEM_LENGTH),
            "vram_part": _span(blocks[1], 0, VRAM_LENGTH),
            "scene_node_count": scene["scene_node_count"],
            "matrix_count": scene["matrix_count"],
            "matrix_table": _span(
                system,
                int(scene["matrix_offset"]),
                int(scene["matrix_count"]) * apf_scene.MATRIX_SIZE,
            ),
        },
        "summary": {
            "eligible_including_first_proved_node": len(all_candidates),
            "first_proved_node_excluded_from_additional_catalog": PROVED_FIRST_NODE,
            "additional_target_count": len(additional),
            "additional_priority_tier_counts": dict(sorted(priority_counts.items())),
            "selected_second_target_node": SECOND_NODE,
        },
        "additional_targets": additional,
        "selected_second_target_handoff": second_fit,
        "claim_boundary": {
            "catalog_proves_bounded_structural_position_lanes": True,
            "catalog_proves_same_count_dispatcher_targets": True,
            "second_target_representative_h7a_fit_proved_offline": True,
            "general_writer_implemented": False,
            "changed_vertex_count_or_topology_proved": False,
            "runtime_rigid_attachment_proved": False,
            "runtime_visibility_proved": False,
            "xbox_360_hardware_proved": False,
        },
    }


def render(game_dir: Path = DEFAULT_GAME_DIR) -> bytes:
    return (json.dumps(build_report(game_dir), indent=4, sort_keys=True) + "\n").encode("utf-8")


def validate_document(document: dict[str, Any]) -> None:
    if document.get("schema") != SCHEMA:
        raise CatalogError("catalog schema drift")
    if document.get("contains_retail_vertex_values") is not False:
        raise CatalogError("catalog retail-value boundary drift")
    summary = document.get("summary")
    if not isinstance(summary, dict) or summary.get("additional_target_count") != 77:
        raise CatalogError("catalog target count drift")
    targets = document.get("additional_targets")
    if not isinstance(targets, list) or len(targets) != 77:
        raise CatalogError("catalog target array drift")
    if any(target.get("runtime_rigid_attachment_proved") is not False for target in targets):
        raise CatalogError("catalog overclaims runtime rigidity")
    handoff = document.get("selected_second_target_handoff")
    if not isinstance(handoff, dict) or handoff.get("node_index") != SECOND_NODE:
        raise CatalogError("second-target handoff drift")
    witness = handoff.get("representative_local_only_fit_witness")
    envelope = document.get("container", {}).get("h7a_rebuild_envelope", {})
    if not isinstance(witness, dict) or witness.get("allocation_slack_after_bytes") != 1367:
        raise CatalogError("second-target fit witness drift")
    if witness.get("stored_block0_length_after") > envelope.get("maximum_stored_block0_bytes", -1):
        raise CatalogError("second-target witness exceeds recorded H7A envelope")


def validate(path: Path = DEFAULT_REPORT, game_dir: Path = DEFAULT_GAME_DIR) -> dict[str, Any]:
    actual = path.read_bytes()
    expected = render(game_dir)
    if actual != expected:
        raise CatalogError("checked catalog differs from deterministic source derivation")
    document = json.loads(actual)
    if not isinstance(document, dict):
        raise CatalogError("catalog top level is not an object")
    validate_document(document)
    return {
        "schema": "apf2k8_stadium_static_position_target_catalog_validation/v1",
        "report_sha256": _sha(actual),
        "additional_targets": 77,
        "selected_second_node": SECOND_NODE,
        "selected_second_vertices": 24,
        "selected_second_draw_records": 3,
        "selected_second_slack_bytes": 1367,
        "retail_vertex_values": False,
        "runtime": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, default=DEFAULT_GAME_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--generate", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.generate:
            args.generate.parent.mkdir(parents=True, exist_ok=True)
            data = render(args.game_dir)
            args.generate.write_bytes(data)
            print(f"APF_STADIUM_STATIC_TARGET_CATALOG_GENERATED sha256={_sha(data)}")
        else:
            result = validate(args.report, args.game_dir)
            print(
                "APF_STADIUM_STATIC_TARGET_CATALOG_PASS "
                f"targets={result['additional_targets']} second_node={result['selected_second_node']} "
                f"vertices={result['selected_second_vertices']} draws={result['selected_second_draw_records']} "
                f"slack={result['selected_second_slack_bytes']} retail_vertices=false runtime=false "
                f"sha256={result['report_sha256']}"
            )
        return 0
    except (CatalogError, apf_inner.FormatError, apf_outer.FormatError, apf_scene.SceneError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
