#!/usr/bin/env python3
"""Build the first multi-shape NFL 2K5 rigid-static target catalog.

This catalog deliberately stops short of being a writer.  It pins every
mechanically rigid same-count FLOAT3 target in the already proved
outer-3280/chunk-5 ``stadium`` SCNE, omitting the implemented ``group36``
witness from the *additional* target rows.  Rows contain structure, spans,
and hashes only; no retail position or topology values are emitted.

The generator also derives a hashes-only all-zero compression probe for the
selected second target, ``upper_deck``.  That probe proves fixed-allocation
fit and exact VC-LZ reconstruction offline.  It is not a pack writer and it
does not claim runtime visibility.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import stat
import struct
from typing import Any

from nfl_outer import parse_archive, read_entry_range
from nfl_scene_probe import ResourceRecord, decode_resource, parse_inventory
from nfl_scne_inventory import parse_scene
from nfl_txtr import (
    HEADER,
    compress_vc_lz,
    decompress_vc_lz,
    minimum_vc_lz_overlap_scratch,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN = ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"
DEFAULT_JSON = ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
DEFAULT_REPORT = ROOT / "docs/research/nfl_stadium_static_target_catalog.md"

SCHEMA = "nfl2k5_stadium_static_target_catalog/v1"

INDEX_NAME = "0"
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
PACK_NAME = "9"
PACK_SIZE = 634_941_440
PACK_SHA256 = "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a"

SCAN_SIZE = 55_746_414
SCAN_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"

OUTER_INDEX = 3280
OUTER_ID = 0xE4D6B0BC
OUTER_SIZE = 1_390_448
OUTER_OFFSET_BLOCKS = 1_747_476
OUTER_VIRTUAL_OFFSET = 3_578_830_848
OUTER_PACK_OFFSET = 0x07E47000
OUTER_SHA256 = "3b2a505e2f0cab433fbe74c5211e4b370112e4e70a2ad45f1fa39a59af9a92cd"

CHUNK_INDEX = 5
CHUNK_ENTRY_OFFSET = 0x5EA40
CHUNK_PACK_OFFSET = 0x07EA5A40
CHUNK_STORED_SIZE = 908_880
CHUNK_SPAN_SIZE = 908_912
CHUNK_PACK_END = 0x07F838B0
SYSTEM_BYTES = 577_792
VIDEO_BYTES = 947_072
DECODED_SIZE = 1_524_864
RETAIL_SCRATCH = 0x10
CHUNK_SPAN_SHA256 = "0cd1977a6097851f9366d935098bdd9e97144f3ffce0f8690593c2623fbbd73a"
WRAPPER_SHA256 = "d4049cd35f3588259072ff9d05952c6bd830f6c1cd6181fc1d72b25b8cdc41ae"
DECODED_SHA256 = "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8"
RETAIL_CONSUMED = 908_864
RETAIL_STREAM_SHA256 = "beb71504d82a7634d73bf6603fb96d8d0ba33beb4fd0eaa870efd4007a8d3af8"
OPAQUE_TAIL_SIZE = 16
OPAQUE_TAIL_SHA256 = "cb57e42b9b8d9e1cba31e18c38dbc3347c8caa1361fcf7fe9cfad5b9f138fae4"

SCENE_INDEX = 2648
SCENE_NAME = "stadium"
IMPLEMENTED_SHAPE_INDEX = 4
IMPLEMENTED_SHAPE_NAME = "group36"
SECOND_SHAPE_INDEX = 1
SECOND_SHAPE_NAME = "upper_deck"

FORMAT_OBSERVED_SCRATCH_MIN = 0
FORMAT_OBSERVED_SCRATCH_MAX = 3_120
FORMAT_OBSERVED_SCRATCH_0X60_COUNT = 165
FORMAT_SCNE_COUNT = 4_616


class CatalogError(ValueError):
    """A source pin or conservative eligibility invariant drifted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CatalogError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular(path: Path, label: str) -> Path:
    path = path.expanduser()
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise CatalogError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def compact_hash(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return sha256(payload)


def _span(offset: int, size: int, payload: bytes) -> dict[str, object]:
    require(0 <= offset <= offset + size <= len(payload), "decoded span is out of bounds")
    return {
        "offset": offset,
        "end_offset": offset + size,
        "size": size,
        "sha256": sha256(payload[offset:offset + size]),
    }


def _aligned16(value: int) -> int:
    return (value + 15) & ~15


def _validate_scan(scan_path: Path) -> tuple[dict[str, Any], list[ResourceRecord]]:
    scan_path = regular(scan_path, "NFL resource inventory")
    require(scan_path.stat().st_size == SCAN_SIZE, "resource inventory size changed")
    require(sha256_file(scan_path) == SCAN_SHA256, "resource inventory SHA-256 changed")
    inventory, resources = parse_inventory(scan_path)
    require(inventory.get("schema") == "nfl2k5_resource_chunk_inventory/v1",
            "resource inventory schema changed")
    selected = [item for item in resources if item.kind == "SCNE"]
    scratch = [item.word_14 for item in selected]
    require(len(scratch) == FORMAT_SCNE_COUNT, "SCNE scratch corpus count changed")
    require(min(scratch) == FORMAT_OBSERVED_SCRATCH_MIN, "SCNE scratch minimum changed")
    require(max(scratch) == FORMAT_OBSERVED_SCRATCH_MAX, "SCNE scratch maximum changed")
    require(Counter(scratch)[0x60] == FORMAT_OBSERVED_SCRATCH_0X60_COUNT,
            "SCNE 0x60 scratch precedent count changed")
    return inventory, resources


def _load_source(index_path: Path, scan_path: Path) -> dict[str, Any]:
    index_path = regular(index_path, "NFL archive index")
    require(index_path.name == INDEX_NAME, "NFL archive index must be volume 0")
    require(index_path.stat().st_size == INDEX_SIZE, "NFL archive index size changed")
    require(sha256_file(index_path) == INDEX_SHA256, "NFL archive index SHA-256 changed")
    pack_path = regular(index_path.parent / PACK_NAME, "NFL volume 9")
    require(pack_path.stat().st_size == PACK_SIZE, "NFL volume 9 size changed")
    require(sha256_file(pack_path) == PACK_SHA256, "NFL volume 9 SHA-256 changed")

    _, resources = _validate_scan(scan_path)
    matching = [
        item for item in resources
        if item.kind == "SCNE" and item.outer_index == OUTER_INDEX
        and item.chunk_index == CHUNK_INDEX
    ]
    require(len(matching) == 1, "target SCNE inventory identity is not unique")
    resource = matching[0]
    require(
        resource.outer_id == "0xe4d6b0bc"
        and resource.outer_size == OUTER_SIZE
        and resource.chunk_offset == CHUNK_ENTRY_OFFSET
        and resource.stored_size == CHUNK_STORED_SIZE
        and resource.word_08 == SYSTEM_BYTES
        and resource.word_0c == VIDEO_BYTES
        and resource.word_10 == 0xFEEDBEEF
        and resource.word_14 == RETAIL_SCRATCH,
        "target SCNE inventory fields changed",
    )

    archive = parse_archive(index_path)
    entry = archive.entries[OUTER_INDEX]
    require(
        entry.name_id == OUTER_ID and entry.size == OUTER_SIZE
        and entry.offset_blocks == OUTER_OFFSET_BLOCKS
        and entry.virtual_offset == OUTER_VIRTUAL_OFFSET,
        "outer entry identity or extent changed",
    )
    require(
        len(entry.segments) == 1
        and entry.segments[0].pack_name == PACK_NAME
        and entry.segments[0].pack_offset == OUTER_PACK_OFFSET
        and entry.segments[0].size == OUTER_SIZE,
        "outer entry is not the pinned single span in volume 9",
    )
    entry_bytes = read_entry_range(archive, entry, 0, entry.size)
    require(sha256(entry_bytes) == OUTER_SHA256, "outer entry bytes changed")
    span = entry_bytes[CHUNK_ENTRY_OFFSET:CHUNK_ENTRY_OFFSET + CHUNK_SPAN_SIZE]
    require(len(span) == CHUNK_SPAN_SIZE and sha256(span) == CHUNK_SPAN_SHA256,
            "target SCNE stored span changed")
    require(sha256(span[:HEADER.size]) == WRAPPER_SHA256, "target wrapper changed")
    require(HEADER.unpack_from(span) == (
        b"SCNE", CHUNK_STORED_SIZE, SYSTEM_BYTES, VIDEO_BYTES,
        0xFEEDBEEF, RETAIL_SCRATCH, 0, 0,
    ), "target wrapper fields changed")

    decoded, detail = decode_resource(span, resource)
    require(len(decoded) == DECODED_SIZE and sha256(decoded) == DECODED_SHA256,
            "target decoded SCNE changed")
    expected_lz = {
        "declared_output_size": DECODED_SIZE,
        "stream_tag": 1,
        "offset_bits": 12,
        "length_bits": 4,
        "consumed_bytes": RETAIL_CONSUMED,
        "literal_count": 508_197,
        "match_count": 158_651,
    }
    require(detail.get("lz") == expected_lz, "target VC-LZ parse changed")
    compressed = span[HEADER.size:HEADER.size + RETAIL_CONSUMED]
    tail = span[HEADER.size + RETAIL_CONSUMED:]
    require(sha256(compressed) == RETAIL_STREAM_SHA256, "retail VC-LZ stream changed")
    require(len(tail) == OPAQUE_TAIL_SIZE and sha256(tail) == OPAQUE_TAIL_SHA256,
            "retail fixed final tail changed")
    scene, _, _, _ = parse_scene(SCENE_INDEX, resource, decoded, {})
    require(scene["name"] == SCENE_NAME and scene["scene_index"] == SCENE_INDEX,
            "target scene identity changed")
    return {
        "index_path": index_path,
        "pack_path": pack_path,
        "archive": archive,
        "entry": entry,
        "resource": resource,
        "span": span,
        "decoded": decoded,
        "detail": detail,
        "compressed": compressed,
        "tail": tail,
        "scene": scene,
    }


def _attribute(shape: dict[str, Any], register: int) -> dict[str, Any]:
    matches = [
        item for item in shape["attribute_descriptors"]
        if int(item["register"]) == register
    ]
    require(len(matches) == 1, f"shape {shape['index']} register {register} is not unique")
    return matches[0]


def _stream(shape: dict[str, Any], stream_index: int) -> dict[str, Any]:
    matches = [
        item for item in shape["vertex_streams"]
        if int(item["stream_index"]) == stream_index
    ]
    require(len(matches) == 1, f"shape {shape['index']} stream {stream_index} is not unique")
    return matches[0]


def _target_row(
    scene: dict[str, Any], shape: dict[str, Any], decoded: bytes,
    resource_contract_sha256: str,
) -> dict[str, Any]:
    shape_index = int(shape["index"])
    shape_name = str(shape["name"])
    vertex_count = int(shape["vertex_count"])
    require(shape["version"] == 2 and vertex_count > 0,
            f"shape {shape_index} is not a nonempty v2 shape")
    require(shape["morph_channel_count"] == 0,
            f"shape {shape_index} has morph/channel records")
    require(shape["transform_count"] == 1,
            f"shape {shape_index} is not single-transform")
    shape_offset = int(shape["record_offset"])
    blend_count = struct.unpack_from("<H", decoded, shape_offset + 0x52)[0]
    require(blend_count == 0, f"shape {shape_index} has blended palette entries")

    position = _attribute(shape, 0)
    require(position == {
        "register": 0, "encoded": "0x00000032", "format_code": 0x32,
        "format_name": "FLOAT3", "component_count": 3, "byte_size": 12,
        "stream_index": 0, "byte_offset": 0,
    }, f"shape {shape_index} position declaration differs from isolated FLOAT3")
    position_stream = _stream(shape, 0)
    require(
        position_stream["stride"] == 12
        and position_stream["byte_size"] == vertex_count * 12,
        f"shape {shape_index} position stream is not contiguous FLOAT3",
    )
    position_offset = int(position_stream["offset"])
    position_size = int(position_stream["byte_size"])

    selector = _attribute(shape, 1)
    require(selector == {
        "register": 1, "encoded": "0x00080115", "format_code": 0x15,
        "format_name": "SHORT1", "component_count": 1, "byte_size": 2,
        "stream_index": 1, "byte_offset": 8,
    }, f"shape {shape_index} selector declaration changed")
    selector_stream = _stream(shape, 1)
    require(selector_stream["stride"] == 10,
            f"shape {shape_index} selector stream stride changed")
    selector_start = int(selector_stream["offset"])
    selector_lane = b"".join(
        decoded[
            selector_start + vertex * 10 + 8:
            selector_start + vertex * 10 + 10
        ]
        for vertex in range(vertex_count)
    )
    selector_values = struct.unpack(f"<{vertex_count}h", selector_lane)
    require(all(value == 0 for value in selector_values),
            f"shape {shape_index} does not select only its sole transform")

    transform_offset = int(shape["transform_offset"])
    require(struct.unpack_from("<4f", decoded, transform_offset + 0x40) == (0.0, 0.0, 0.0, 1.0)
            and struct.unpack_from("<4f", decoded, transform_offset + 0x50) == (0.0, 0.0, 0.0, 1.0)
            and struct.unpack_from("<i", decoded, transform_offset + 0x64)[0] == -1,
            f"shape {shape_index} is not rooted at the zero transform")

    nodes = [
        item for item in scene["nodes"]
        if shape_index in [int(value) for value in item["matching_shape_indices"]]
    ]
    require(len(nodes) == 1, f"shape {shape_index} does not have one matching node")
    node = nodes[0]
    require(node["matching_shape_count"] == 1,
            f"shape {shape_index} node name is ambiguous")

    submeshes = [
        item for item in scene["submeshes"] if int(item["shape_index"]) == shape_index
    ]
    require(len(submeshes) == int(shape["submesh_count"]) > 0,
            f"shape {shape_index} has no exact submesh set")
    primitive_counts: Counter[str] = Counter()
    push_rows: list[dict[str, Any]] = []
    material_rows: list[dict[str, Any]] = []
    for submesh in submeshes:
        require(submesh["all_vertex_references_in_bounds"] is True,
                f"shape {shape_index} topology exceeds vertex count")
        require(submesh["unknown_method_counts"] == {},
                f"shape {shape_index} has unknown push methods")
        primitive_counts.update(submesh["primitive_mode_counts"])
        command_offset = int(submesh["command_offset"])
        command_size = int(submesh["primary_command_word_count"]) * 4
        submesh_offset = int(submesh["record_offset"])
        push_rows.append({
            "submesh_index": int(submesh["submesh_index"]),
            "record": _span(submesh_offset, 0x80, decoded),
            "commands": _span(command_offset, command_size, decoded),
            "primary_word_count": int(submesh["primary_command_word_count"]),
            "secondary_word_count": int(submesh["secondary_command_word_count"]),
            "method_counts": submesh["method_counts"],
            "primitive_mode_counts": submesh["primitive_mode_counts"],
            "inline_index_count": int(submesh["index_element_count"]),
            "draw_array_vertex_count": int(submesh["draw_array_vertex_count"]),
            "maximum_vertex_index": submesh["maximum_vertex_index"],
        })
        material_rows.append({
            "submesh_index": int(submesh["submesh_index"]),
            "material_index": int(submesh["material_index"]),
            "material_name": submesh["material_name"],
            "auxiliary_index_preserved": int(submesh["auxiliary_index"]),
        })

    submesh_offset = int(shape["submesh_offset"])
    submesh_size = int(shape["submesh_count"]) * 0x80
    morph_pointer_raw = struct.unpack_from("<i", decoded, shape_offset + 0x74)[0]
    return {
        "target_id": f"nfl2k5/stadium/o{OUTER_INDEX}/c{CHUNK_INDEX}/s{shape_index}",
        "source_identity": {
            "outer_index": OUTER_INDEX,
            "outer_id": "0xe4d6b0bc",
            "chunk_index": CHUNK_INDEX,
            "scene_index": SCENE_INDEX,
            "scene_name": SCENE_NAME,
            "decoded_sha256": DECODED_SHA256,
            "resource_contract_sha256": resource_contract_sha256,
        },
        "shape": {
            "index": shape_index,
            "name": shape_name,
            "version": 2,
            "vertex_count": vertex_count,
            "record": _span(shape_offset, 0x100, decoded),
            "node": {
                "index": int(node["index"]),
                "name": node["name"],
                "secondary_name": node["secondary_name"],
                "record": _span(int(node["record_offset"]), 0x60, decoded),
                "one_name_match": True,
                "complete_runtime_ownership_proved": False,
            },
        },
        "position": {
            "register": 0,
            "declaration": position,
            "component_storage": "3*f32le",
            "coordinate_space": "raw_xbox",
            "stream_index": 0,
            "stream_stride": 12,
            "lane_offset_within_stride": 0,
            "lane_size": 12,
            "contiguous_decoded_span": _span(position_offset, position_size, decoded),
            "retail_values_embedded": False,
        },
        "transform": {
            "base_count": 1,
            "blended_palette_entry_count": 0,
            "table": _span(transform_offset, 0x70, decoded),
            "one_zero_root_parent_minus_one": True,
            "editing_allowed": False,
        },
        "morph": {
            "count": 0,
            "resolved_table_offset": shape["morph_channel_offset"],
            "serialized_pointer_is_null": morph_pointer_raw == 0,
            "editing_allowed": False,
        },
        "selectors": {
            "register": 1,
            "declaration": selector,
            "stream": _span(
                selector_start, int(selector_stream["byte_size"]), decoded
            ),
            "stream_stride": 10,
            "lane_offset_within_stride": 8,
            "lane_size": 2,
            "lane_element_count": vertex_count,
            "lane_sha256": sha256(selector_lane),
            "all_select_sole_transform": True,
            "retail_selector_values_embedded": False,
        },
        "topology_and_materials": {
            "submesh_count": int(shape["submesh_count"]),
            "submesh_table": _span(submesh_offset, submesh_size, decoded),
            "primitive_mode_counts": dict(sorted(primitive_counts.items())),
            "all_vertex_references_in_bounds": True,
            "unknown_push_methods": False,
            "materials": material_rows,
            "push_streams": push_rows,
            "topology_values_embedded": False,
            "editing_allowed": False,
        },
        "fixed_allocation": {
            "stored_body_bytes": CHUNK_STORED_SIZE,
            "retail_consumed_stream_bytes": RETAIL_CONSUMED,
            "changed_stream_cap_bytes": RETAIL_CONSUMED,
            "fixed_final_tail_bytes": OPAQUE_TAIL_SIZE,
            "fixed_final_tail_sha256": OPAQUE_TAIL_SHA256,
            "source_wrapper_scratch_bytes": RETAIL_SCRATCH,
            "rebuilt_scratch_rule": "align16(max(stored_size-rebuilt_consumed, minimum_in_place_alias_scratch))",
            "scratch_must_be_rederived_per_edit": True,
            "runtime_acceptance_of_changed_scratch_proved": False,
            "decoded_system_and_video_extents_must_remain_fixed": True,
        },
        "eligibility": {
            "mechanically_rigid_same_count_float3": True,
            "reason": (
                "v2 stadium shape with nonzero fixed vertex count, isolated contiguous "
                "FLOAT3 register-0 stream, one zero root, zero blended palette entries, "
                "zero morph records, all selectors bound to the sole transform, and "
                "fully bounded preserved topology"
            ),
            "semantic_attachment_or_runtime_ownership_proved": False,
            "same_count_position_writer_implemented_for_this_target": False,
            "runtime_visibility_proved": False,
            "production_ready": False,
        },
    }


def _resource_contract(source: dict[str, Any]) -> dict[str, Any]:
    entry = source["entry"]
    detail = source["detail"]["lz"]
    return {
        "source": {
            "index": {"name": INDEX_NAME, "size": INDEX_SIZE, "sha256": INDEX_SHA256},
            "volume": {"name": PACK_NAME, "size": PACK_SIZE, "sha256": PACK_SHA256},
            "resource_inventory": {
                "path": "reports/assets/nfl2k5_resource_chunks_v2.json",
                "size": SCAN_SIZE,
                "sha256": SCAN_SHA256,
            },
        },
        "outer_entry": {
            "index": OUTER_INDEX,
            "id": "0xe4d6b0bc",
            "size": OUTER_SIZE,
            "offset_blocks": OUTER_OFFSET_BLOCKS,
            "virtual_offset": OUTER_VIRTUAL_OFFSET,
            "volume": PACK_NAME,
            "volume_span": [OUTER_PACK_OFFSET, OUTER_PACK_OFFSET + OUTER_SIZE],
            "sha256": OUTER_SHA256,
            "single_volume_span": len(entry.segments) == 1,
        },
        "resource": {
            "chunk_index": CHUNK_INDEX,
            "entry_offset": CHUNK_ENTRY_OFFSET,
            "volume_span": [CHUNK_PACK_OFFSET, CHUNK_PACK_END],
            "span_size": CHUNK_SPAN_SIZE,
            "span_sha256": CHUNK_SPAN_SHA256,
            "wrapper_sha256": WRAPPER_SHA256,
            "stored_size": CHUNK_STORED_SIZE,
            "system_bytes": SYSTEM_BYTES,
            "video_bytes": VIDEO_BYTES,
            "decoded_size": DECODED_SIZE,
            "decoded_sha256": DECODED_SHA256,
        },
        "vc_lz": {
            "stream_tag": int(detail["stream_tag"]),
            "offset_bits": int(detail["offset_bits"]),
            "length_bits": int(detail["length_bits"]),
            "retail_consumed_bytes": RETAIL_CONSUMED,
            "retail_stream_sha256": RETAIL_STREAM_SHA256,
            "changed_stream_cap_bytes": RETAIL_CONSUMED,
            "fixed_final_tail_bytes": OPAQUE_TAIL_SIZE,
            "fixed_final_tail_sha256": OPAQUE_TAIL_SHA256,
            "source_scratch_bytes": RETAIL_SCRATCH,
            "changed_scratch_rule": "align16(max(stored_size-rebuilt_consumed, minimum_in_place_alias_scratch))",
            "scratch_field_observed_corpus": {
                "scne_resources": FORMAT_SCNE_COUNT,
                "minimum": FORMAT_OBSERVED_SCRATCH_MIN,
                "maximum": FORMAT_OBSERVED_SCRATCH_MAX,
                "value_0x60_occurrences": FORMAT_OBSERVED_SCRATCH_0X60_COUNT,
            },
            "group36_0x40_cap_is_fixture_specific_not_format_wide": True,
            "changed_scratch_runtime_proved": False,
        },
        "immutable_policy": [
            "preserve index and source volume; a later writer must emit a copied volume",
            "preserve outer and resource extents and every byte outside this resource span",
            "preserve all decoded bytes outside the selected register-0 FLOAT3 lane",
            "cap rebuilt VC-LZ at the retail consumed boundary and preserve the final 16 bytes",
            "independently decode the rebuilt stream and rederive overlap scratch",
            "reject rather than relocate, truncate, change count, change topology, or borrow tail bytes",
        ],
    }


def _all_zero_second_probe(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    require(target["shape"]["index"] == SECOND_SHAPE_INDEX, "second target index changed")
    position = target["position"]["contiguous_decoded_span"]
    start = int(position["offset"])
    end = int(position["end_offset"])
    require(end - start == 12 * 12, "upper_deck position span is not 12 FLOAT3 values")
    decoded = bytes(source["decoded"])
    replacement = bytes(end - start)
    edited = bytearray(decoded)
    edited[start:end] = replacement
    edited_bytes = bytes(edited)
    changed = [offset for offset, (before, after) in enumerate(zip(decoded, edited_bytes)) if before != after]
    require(len(changed) == 144 and changed == list(range(start, end)),
            "all-zero upper_deck edit no longer changes exactly its 144-byte lane")
    encoded, compression = compress_vc_lz(
        edited_bytes,
        stream_tag=int(source["detail"]["lz"]["stream_tag"]),
        offset_bits=int(source["detail"]["lz"]["offset_bits"]),
        max_encoded_size=RETAIL_CONSUMED,
        verify_roundtrip=True,
    )
    decoded_back, parsed = decompress_vc_lz(encoded, DECODED_SIZE)
    require(decoded_back == edited_bytes and parsed.consumed_bytes == len(encoded),
            "upper_deck probe VC-LZ reconstruction failed")
    gap = RETAIL_CONSUMED - len(encoded)
    padding = CHUNK_STORED_SIZE - len(encoded)
    alias = minimum_vc_lz_overlap_scratch(encoded, CHUNK_STORED_SIZE, DECODED_SIZE)
    scratch = _aligned16(max(padding, alias))
    header = bytearray(bytes(source["span"])[:HEADER.size])
    struct.pack_into("<I", header, 0x14, scratch)
    rebuilt = bytes(header) + encoded + bytes(gap) + bytes(source["tail"])
    require(len(rebuilt) == CHUNK_SPAN_SIZE, "upper_deck probe fixed span size changed")
    require(rebuilt[-OPAQUE_TAIL_SIZE:] == source["tail"],
            "upper_deck probe did not preserve the fixed final tail")
    return {
        "target_id": target["target_id"],
        "selection_reason": (
            "second shape after the implemented witness; 12 rather than four vertices, "
            "one submesh, and DRAW_ARRAYS QUADS exercises a topology command path "
            "different from group36 ARRAY_ELEMENT16 while remaining mechanically rigid"
        ),
        "authored_probe": {
            "description": "replace all 12 ordered FLOAT3 triples with independently authored zero triples",
            "contains_retail_position_values": False,
            "position_after_sha256": sha256(replacement),
            "decoded_after_sha256": sha256(edited_bytes),
            "decoded_changed_byte_count": len(changed),
            "every_changed_decoded_byte_inside_position_lane": True,
        },
        "compression": {
            "retail_consumed_bytes": RETAIL_CONSUMED,
            "rebuilt_consumed_bytes": len(encoded),
            "rebuilt_stream_sha256": sha256(encoded),
            "zero_gap_bytes": gap,
            "total_stored_padding_bytes": padding,
            "minimum_alias_scratch_bytes": alias,
            "aligned_scratch_bytes": scratch,
            "scratch_0x60_has_retail_scne_precedent_count": FORMAT_OBSERVED_SCRATCH_0X60_COUNT,
            "literal_count": compression.literal_count,
            "match_count": compression.match_count,
            "independent_decode_exact": True,
            "fixed_final_tail_exact": True,
            "rebuilt_fixed_span_sha256": sha256(rebuilt),
            "rebuilt_wrapper_sha256": sha256(bytes(header)),
        },
        "claim_boundary": {
            "offline_fixed_allocation_fit_proved": True,
            "pack_write_implemented": False,
            "independent_writer_verifier_implemented": False,
            "runtime_visibility_proved": False,
            "production_ready": False,
        },
    }


def build_catalog(index_path: Path, scan_path: Path = DEFAULT_SCAN) -> dict[str, Any]:
    source = _load_source(index_path, scan_path)
    resource_contract = _resource_contract(source)
    resource_contract_sha = compact_hash(resource_contract)
    scene = source["scene"]
    require(len(scene["shapes"]) == 76, "target scene shape count changed")
    rows = [
        _target_row(scene, shape, source["decoded"], resource_contract_sha)
        for shape in scene["shapes"]
    ]
    require([row["shape"]["index"] for row in rows] == list(range(76)),
            "target scene shape order changed")
    implemented = rows[IMPLEMENTED_SHAPE_INDEX]
    require(implemented["shape"]["name"] == IMPLEMENTED_SHAPE_NAME,
            "implemented group36 reference changed")
    additional = [
        row for row in rows if int(row["shape"]["index"]) != IMPLEMENTED_SHAPE_INDEX
    ]
    require(len(additional) == 75, "additional target count changed")
    second = next(row for row in additional if row["shape"]["index"] == SECOND_SHAPE_INDEX)
    require(second["shape"]["name"] == SECOND_SHAPE_NAME, "second target identity changed")
    primitive_counts: Counter[str] = Counter()
    vertex_total = 0
    submesh_total = 0
    for row in additional:
        vertex_total += int(row["shape"]["vertex_count"])
        submesh_total += int(row["topology_and_materials"]["submesh_count"])
        primitive_counts.update(row["topology_and_materials"]["primitive_mode_counts"])
    catalog = {
        "schema": SCHEMA,
        "title": "NFL 2K5 outer3280/chunk5 stadium rigid-static FLOAT3 target catalog",
        "data_policy": {
            "contains_retail_geometry_values": False,
            "contains_retail_position_values": False,
            "contains_retail_index_values": False,
            "contains_retail_vertex_or_push_payload_bytes": False,
            "contains_nonretail_authored_probe_values": True,
            "allowed_evidence": "identities, field constants, spans, counts, names, hashes, booleans, and nonretail all-zero probe facts",
        },
        "scope": {
            "catalogued_resource_count": 1,
            "catalogued_scene": f"{OUTER_INDEX}/{CHUNK_INDEX}/{SCENE_INDEX}:{SCENE_NAME}",
            "mechanically_eligible_shape_count_in_resource": 76,
            "implemented_reference_shape_count": 1,
            "additional_catalog_target_count": 75,
            "exhaustive_for_selected_resource": True,
            "exhaustive_for_all_477_stadium_scenes": False,
            "reason_for_bounded_v1": "close multi-shape dispatch in the already byte-proved resource before expanding archive coverage",
        },
        "claim_flags": {
            "additional_targets_structurally_catalogued": True,
            "all_catalog_targets_mechanically_rigid_same_count_float3": True,
            "general_position_writer_implemented": False,
            "changed_topology_writer_implemented": False,
            "runtime_visibility_proved": False,
            "production_ready": False,
        },
        "eligibility_profile": {
            "required": [
                "scene is the pinned stadium SCNE and all source structural bounds pass",
                "shape version 2 and vertex_count nonzero and unchanged",
                "register 0 is isolated FLOAT3 in stream 0 at offset 0 with stride 12",
                "morph/channel count is zero",
                "one base transform, zero blended entries, zero root translations, parent -1",
                "register-1 SHORT1 selectors all select the sole transform",
                "one unambiguous matching node name",
                "all submesh command streams bounded with known methods and in-range references",
            ],
            "preserved_not_authored": [
                "vertex count/order and every non-position stream byte",
                "node, transform, selector, morph, material, submesh, and push-command bytes",
                "outer/resource extents, wrapper except rederived scratch, and fixed final tail",
            ],
            "caveat": "mechanical rigid-static eligibility does not prove complete node attachment semantics, collision/LOD ownership, runtime acceptance, or visibility",
        },
        "resource_contract": resource_contract,
        "resource_contract_sha256": resource_contract_sha,
        "implemented_reference": {
            "target_id": implemented["target_id"],
            "shape_index": IMPLEMENTED_SHAPE_INDEX,
            "shape_name": IMPLEMENTED_SHAPE_NAME,
            "writer": "tools/nfl_stadium_group36_position_patch.py",
            "independent_verifier": "tools/nfl_stadium_group36_position_verify.py",
            "catalog_row_omitted_from_additional_targets": True,
        },
        "selected_second_target": _all_zero_second_probe(source, second),
        "summary": {
            "target_count": len(additional),
            "vertex_count_total": vertex_total,
            "submesh_count_total": submesh_total,
            "primitive_mode_counts": dict(sorted(primitive_counts.items())),
            "position_format_counts": {"FLOAT3": len(additional)},
            "transform_pattern_counts": {"one_zero_root_no_blends": len(additional)},
            "selector_pattern_counts": {"all_zero_short1": len(additional)},
            "morph_count_zero_targets": len(additional),
        },
        "targets": additional,
    }
    validate_catalog(catalog)
    return catalog


def _walk_keys(value: object) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys


def validate_catalog(catalog: dict[str, Any]) -> None:
    require(catalog.get("schema") == SCHEMA, "catalog schema changed")
    policy = catalog.get("data_policy", {})
    for key in (
        "contains_retail_geometry_values", "contains_retail_position_values",
        "contains_retail_index_values", "contains_retail_vertex_or_push_payload_bytes",
    ):
        require(policy.get(key) is False, f"catalog data policy {key} changed")
    targets = catalog.get("targets")
    require(isinstance(targets, list) and len(targets) == 75,
            "catalog must contain exactly 75 additional targets")
    ids = [str(row["target_id"]) for row in targets]
    require(len(set(ids)) == len(ids), "catalog target IDs are not unique")
    indices = [int(row["shape"]["index"]) for row in targets]
    require(indices == [value for value in range(76) if value != IMPLEMENTED_SHAPE_INDEX],
            "catalog target index coverage changed")
    require(catalog["resource_contract_sha256"] == compact_hash(catalog["resource_contract"]),
            "resource contract hash changed")
    require(all(row["source_identity"]["resource_contract_sha256"]
                == catalog["resource_contract_sha256"] for row in targets),
            "target resource contract reference changed")
    require(all(row["eligibility"]["mechanically_rigid_same_count_float3"] is True
                for row in targets), "catalog contains an ineligible target")
    require(all(row["position"]["retail_values_embedded"] is False for row in targets),
            "catalog position row claims embedded retail values")
    require(all(row["topology_and_materials"]["topology_values_embedded"] is False
                for row in targets), "catalog topology row claims embedded values")
    second = catalog["selected_second_target"]
    require(second["target_id"].endswith("/s1"), "selected second target changed")
    require(second["compression"]["rebuilt_consumed_bytes"] == 908_799,
            "selected second target compressed size changed")
    require(second["compression"]["aligned_scratch_bytes"] == 0x60,
            "selected second target scratch changed")
    require(second["claim_boundary"]["runtime_visibility_proved"] is False,
            "catalog may not claim runtime proof")
    require(catalog["claim_flags"]["general_position_writer_implemented"] is False,
            "catalog may not claim a general writer")
    forbidden_exact_keys = {"positions", "position_values", "indices", "index_values", "vertices"}
    require(not (forbidden_exact_keys & set(_walk_keys(catalog))),
            "catalog embeds a forbidden retail geometry value key")


def render_report(catalog: dict[str, Any]) -> str:
    second = catalog["selected_second_target"]
    compression = second["compression"]
    summary = catalog["summary"]
    return f"""# NFL 2K5 rigid-static stadium target catalog v1

## Result

The first multi-shape dispatch catalog now pins all 76 mechanically rigid
`FLOAT3` shapes in outer `{OUTER_INDEX}`, chunk `{CHUNK_INDEX}`, scene
`{SCENE_INDEX}` (`{SCENE_NAME}`). The already implemented `group36` witness is
retained as a reference; the machine-readable `targets` array contains the 75
additional shapes.

Every target row pins its outer/chunk/scene/shape identity, shape and matching
node record hashes, position declaration and decoded lane, the one-zero-root
transform boundary, zero morph boundary, all-zero selector lane, complete
submesh/material summaries, every bounded push-stream span/hash, and the shared
VC-LZ fixed-allocation contract. No retail position or index values are in the
catalog.

This is exhaustive for one selected SCNE, not for all 477 stadium SCNEs.

## Catalog result

| Property | Value |
|---|---:|
| Additional targets | {summary['target_count']} |
| Vertices across additional targets | {summary['vertex_count_total']} |
| Submeshes across additional targets | {summary['submesh_count_total']} |
| Position declaration | 75 `FLOAT3`, stream 0, offset 0, stride 12 |
| Transform boundary | 75 one-zero-root, no blended entries |
| Morph boundary | 75 zero-count |
| Selector boundary | 75 all-zero `SHORT1` lanes |

## Strongest safe second target

`upper_deck` (shape 1) is the selected second writer witness:

- 12 `FLOAT3` vertices rather than `group36`'s four;
- one `sign01` submesh;
- native `QUADS` using `DRAW_ARRAYS`, exercising a different topology command
  path from `group36`'s `ARRAY_ELEMENT16` indices;
- one zero root, zero blended entries, zero morph records, and all selectors
  bound to the sole transform; and
- a fully nonretail all-zero authored probe, so no mixed retail coordinates
  need to be committed.

The all-zero probe changes exactly 144 decoded bytes in the position lane. Its
VC-LZ stream is {compression['rebuilt_consumed_bytes']:,} bytes, below the
{compression['retail_consumed_bytes']:,}-byte retail consumed boundary. It
leaves a {compression['zero_gap_bytes']}-byte gap before the preserved final
16 bytes and independently re-derives `0x{compression['aligned_scratch_bytes']:02x}`
scratch. That value is structurally ordinary: `0x60` occurs in
{compression['scratch_0x60_has_retail_scne_precedent_count']} retail SCNE
wrappers, while the complete SCNE scratch field spans 0..3120.

The earlier `0x40` limit belongs only to the `group36` proof fixture; it is not
a format-wide maximum. The `upper_deck` result is still offline evidence only.
The v2 catalog dispatcher and its independent verifier now close the copied-
volume byte proof for this target; there is still no xemu witness, original-
Xbox witness, or semantic-ownership proof.

## Fixed-allocation policy

The implemented catalog-dispatch writer preserves the outer entry and resource
extents, changes only one selected register-0 lane, caps the rebuilt VC-LZ
stream at 908,864 bytes, preserves the final 16 stored bytes at their exact
location, re-derives in-place overlap scratch for each edit, independently
decompresses to the exact edited body, and rejects any overflow or structural
drift.

No padding or shorter compressed stream is claimed as relocatable geometry
headroom. Vertex counts, topology, materials, transforms, morphs, selectors,
node records, and all non-position stream bytes remain immutable.

## Artifacts and reproduction

- `reports/specs/nfl2k5_stadium_static_target_catalog.v1.json`
- `tools/nfl_stadium_static_target_catalog.py`
- `tests/test_nfl_stadium_static_target_catalog.py`
- `tools/validate_nfl_stadium_static_target_catalog.sh`

Rebuild and byte-compare the catalog and report with:

```bash
bash tools/validate_nfl_stadium_static_target_catalog.sh
```

## Claim boundary

Proved by the catalog itself: 75 additional mechanically rigid same-count
`FLOAT3` target contracts in one canonical stadium SCNE, plus offline
fixed-allocation fit for the nonretail all-zero `upper_deck` probe.

Downstream work now implements the catalog dispatcher for all 75 rows and
closes `upper_deck` as a second full copied-volume byte proof; see
`nfl_stadium_catalog_position_writeback.md`. Separately, `group36` now has one
same-footprint native-quad writer. Still not proved: changed vertex/index
counts, UV/normal/material/transform/morph/skin authoring, collision or LOD
ownership, all-stadium coverage, runtime visibility, or production readiness.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "index", nargs="?", type=Path,
        default=ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0",
    )
    parser.add_argument("--resource-scan", type=Path, default=DEFAULT_SCAN)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check", action="store_true", help="compare generated bytes to checked-in outputs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = build_catalog(args.index, args.resource_scan)
    json_bytes = canonical_json(catalog)
    report_bytes = render_report(catalog).encode("utf-8")
    if args.check:
        require(args.json.read_bytes() == json_bytes, "checked-in catalog JSON differs")
        require(args.report.read_bytes() == report_bytes, "checked-in catalog report differs")
    else:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_bytes(json_bytes)
        args.report.write_bytes(report_bytes)
    print(
        "NFL_STADIUM_STATIC_TARGET_CATALOG_PASS "
        f"targets={len(catalog['targets'])} second=upper_deck "
        f"second_consumed={catalog['selected_second_target']['compression']['rebuilt_consumed_bytes']} "
        f"second_scratch={catalog['selected_second_target']['compression']['aligned_scratch_bytes']} "
        f"runtime=false sha256={sha256(json_bytes)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
