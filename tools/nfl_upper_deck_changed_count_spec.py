#!/usr/bin/env python3
"""Recover the fail-closed NFL 2K5 ``upper_deck`` changed-count boundary.

This is a specification/probe generator, not a mesh writer.  It validates the
pinned retail source, re-derives the target's two vertex streams and complete
NV2A DRAW_ARRAYS program, and performs in-memory count-only prefix-shrink
probes.  It never publishes a modified archive or embeds retail vertex,
attribute, or command payload bytes in the checked JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import struct
from typing import Any, Iterable

import nfl_stadium_static_target_catalog as catalog_tool
from nfl_scne_inventory import parse_scene
from nfl_txtr import (
    HEADER,
    compress_vc_lz,
    decompress_vc_lz,
    minimum_vc_lz_overlap_scratch,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
DEFAULT_SPEC = ROOT / "reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json"

SCHEMA = "nfl2k5_upper_deck_changed_count_boundary/v1"
TARGET_ID = "nfl2k5/stadium/o3280/c5/s1"
SHAPE_INDEX = 1
SHAPE_NAME = "upper_deck"
SOURCE_VERTEX_COUNT = 12

SHAPE_OFFSET = 30_464
VERTEX_COUNT_FIELD = SHAPE_OFFSET + 0x4C
BLEND_COUNT_FIELD = SHAPE_OFFSET + 0x52
BLEND_POINTER_FIELD = SHAPE_OFFSET + 0x60
TRANSFORM_POINTER_FIELD = SHAPE_OFFSET + 0x64
SUBMESH_POINTER_FIELD = SHAPE_OFFSET + 0x70
MORPH_POINTER_FIELD = SHAPE_OFFSET + 0x74
AUX_POINTER_78_FIELD = SHAPE_OFFSET + 0x78
AUX_POINTER_7C_FIELD = SHAPE_OFFSET + 0x7C
STREAM_STRIDE_FIELDS = (SHAPE_OFFSET + 0xC4, SHAPE_OFFSET + 0xC6)
STREAM_POINTER_FIELDS = (SHAPE_OFFSET + 0xD4, SHAPE_OFFSET + 0xD8)

TRANSFORM_OFFSET = 69_632
SUBMESH_OFFSET = 69_744
PUSH_POINTER_FIELD = SUBMESH_OFFSET + 0x78
PRIMARY_WORD_COUNT_FIELD = SUBMESH_OFFSET + 0x7C
SECONDARY_WORD_COUNT_FIELD = SUBMESH_OFFSET + 0x7E
PUSH_OFFSET = 69_872
PUSH_SIZE = 24
DRAW_PARAMETER_OFFSET = PUSH_OFFSET + 12
DRAW_COUNT_BYTE_OFFSET = DRAW_PARAMETER_OFFSET + 3

STREAM0_OFFSET = 69_920
STREAM0_STRIDE = 12
STREAM1_OFFSET = 70_080
STREAM1_STRIDE = 10
STREAM0_SOURCE_END = STREAM0_OFFSET + SOURCE_VERTEX_COUNT * STREAM0_STRIDE
STREAM1_SOURCE_END = STREAM1_OFFSET + SOURCE_VERTEX_COUNT * STREAM1_STRIDE

EVIDENCE_PINS = {
    "nfl_parent_static_scne_spec": (
        "reports/specs/nfl2k5_xbox_static_scne.v1.json",
        47_126,
        "d1e684a0b86c3a933355217174938cb95c5192eb2680c8b9698f7eb15ac39884",
    ),
    "stadium_target_catalog": (
        "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json",
        858_600,
        "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa",
    ),
    "upper_deck_same_count_roundtrip": (
        "reports/assets/nfl_stadium_catalog_position_patch_roundtrip.v2.json",
        7_150,
        "05ab26057b0ebd244a0a090d2268f1cac49b3b820269b410e38c5e6b89a6d9c3",
    ),
    "scne_parser": (
        "tools/nfl_scne_inventory.py",
        50_116,
        "1925041fb672fd9529d3cd7d01bdbbc2758e73eb1e14042c25c9ec454e6f5b5c",
    ),
    "stadium_catalog_generator": (
        "tools/nfl_stadium_static_target_catalog.py",
        41_962,
        "35adf4e719f4e057bf687fa4d658d730966ccba2c4494d92454c287706f89ee4",
    ),
    "resource_decoder_and_compressor": (
        "tools/nfl_txtr.py",
        42_563,
        "15327068fcfa0de55022c4704212f5010e73ff4710d4c1f4ce3804c1b8e30139",
    ),
    "resource_wrapper_parser": (
        "tools/nfl_scene_probe.py",
        39_862,
        "0cab4e10367c950aada642853995b6a954e82b7e37c88c0539abd2a90a78dc2e",
    ),
    "shape_loader_and_skin_pseudo_c": (
        "reports/assets/nfl_transform_semantics_ghidra/nfl_transform_semantics_focused_pseudo_c.c",
        74_384,
        "8dec09544d3d8b182f8028f37f8d0641f4cc60c6521ca7e852f27d75fbe05e5e",
    ),
    "complete_function_export_shard_for_scne_consumers": (
        "research/functions/nfl2k5/pseudo_c/shard_000000_000511.c",
        705_559,
        "58637c7fa52456e7b615a24692301b8567063d998056c06b7528fca0f312f4c1",
    ),
    "future_source_subset_recipe_schema": (
        "reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json",
        2_209,
        "4fac01c6cffe03481b456899ec2b2f3cd25f74954d5db94ccb3b8351f841ca4b",
    ),
}


class BoundaryError(ValueError):
    """A source pin, format invariant, or fail-closed rule drifted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BoundaryError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def regular_file(path: Path, label: str) -> Path:
    path = path.expanduser()
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise BoundaryError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def relative_target(field_offset: int, stored_s32: int) -> int | None:
    if stored_s32 == 0:
        return None
    return field_offset - 1 + stored_s32


def decode_header(header: int) -> tuple[int, int, int]:
    require((header & 0xE0030003) in (0, 0x40000000),
            "NV2A command header signature is not admitted")
    return (header >> 29) & 7, (header >> 18) & 0x7FF, header & 0x1FFC


def decode_draw_arrays(parameter: int) -> tuple[int, int]:
    return parameter & 0x00FFFFFF, ((parameter >> 24) & 0xFF) + 1


def encode_draw_arrays(start: int, count: int) -> int:
    require(type(start) is int and 0 <= start <= 0xFFFFFF,
            "DRAW_ARRAYS start is outside its 24-bit field")
    require(type(count) is int and 1 <= count <= 256,
            "DRAW_ARRAYS count is outside its one-through-256 field")
    return start | ((count - 1) << 24)


def admissible_quad_counts(source_count: int = SOURCE_VERTEX_COUNT) -> tuple[int, ...]:
    require(type(source_count) is int and 1 <= source_count <= 256,
            "source count is outside the bounded DRAW_ARRAYS domain")
    return tuple(count for count in range(4, source_count + 1, 4))


def validate_subset_ids(source_count: int, subset: Iterable[int]) -> tuple[int, ...]:
    values = tuple(subset)
    require(values, "source subset must not be empty")
    require(len(values) in admissible_quad_counts(source_count),
            "source subset count must be an admitted complete-quad count")
    require(all(type(value) is int for value in values),
            "source subset IDs must be integers, not booleans or numeric lookalikes")
    require(all(0 <= value < source_count for value in values),
            "source subset ID is outside the source vertex domain")
    require(len(set(values)) == len(values),
            "source subset IDs must be distinct; implicit welding is forbidden")
    return values


def remap_stream_prefix(
    source_stream: bytes, stride: int, source_count: int, subset: Iterable[int]
) -> bytes:
    """Synthetic/reference whole-record remap with an exact physical tail."""
    require(type(stride) is int and stride > 0, "stream stride must be positive")
    require(len(source_stream) == stride * source_count,
            "stream extent does not equal source_count * stride")
    ids = validate_subset_ids(source_count, subset)
    result = bytearray(source_stream)
    for destination, source_id in enumerate(ids):
        source_start = source_id * stride
        destination_start = destination * stride
        result[destination_start:destination_start + stride] = (
            source_stream[source_start:source_start + stride]
        )
    # The bytes after the new logical end are deliberately not zeroed, packed,
    # or treated as capacity.  They remain the source physical tail.
    return bytes(result)


def _validate_evidence_files() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for label, (relative, expected_size, expected_hash) in EVIDENCE_PINS.items():
        path = regular_file(ROOT / relative, label)
        require(path.stat().st_size == expected_size, f"{label} size drift")
        require(sha256_file(path) == expected_hash, f"{label} SHA-256 drift")
        result[label] = {
            "path": relative,
            "size_bytes": expected_size,
            "sha256": expected_hash,
        }
    return result


def _select_catalog_target() -> dict[str, Any]:
    relative, _, _ = EVIDENCE_PINS["stadium_target_catalog"]
    data = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    require(data.get("schema") == "nfl2k5_stadium_static_target_catalog/v1",
            "stadium target catalog schema drift")
    targets = [row for row in data.get("targets", []) if row.get("target_id") == TARGET_ID]
    require(len(targets) == 1, "upper_deck catalog target is not unique")
    return targets[0]


def _span(offset: int, size: int, decoded: bytes) -> dict[str, object]:
    require(0 <= offset <= offset + size <= len(decoded), "span is outside decoded SCNE")
    return {
        "offset": offset,
        "end_offset": offset + size,
        "size_bytes": size,
        "sha256": sha256_bytes(decoded[offset:offset + size]),
    }


def _pointer_row(decoded: bytes, field_offset: int, role: str, status: str) -> dict[str, object]:
    stored = struct.unpack_from("<i", decoded, field_offset)[0]
    return {
        "field_offset": field_offset,
        "encoding": "s32le one-based self-relative",
        "role": role,
        "target_offset": relative_target(field_offset, stored),
        "null": stored == 0,
        "evidence_status": status,
        "writer_policy": "preserve_exact",
    }


def _parse_push(decoded: bytes) -> dict[str, object]:
    words = struct.unpack_from("<6I", decoded, PUSH_OFFSET)
    cursor = 0
    commands: list[dict[str, object]] = []
    while cursor < len(words):
        header_offset = PUSH_OFFSET + cursor * 4
        instruction, count, method = decode_header(words[cursor])
        require(cursor + 1 + count <= len(words), "upper_deck command overruns six-word span")
        parameters = words[cursor + 1:cursor + 1 + count]
        row: dict[str, object] = {
            "header_offset": header_offset,
            "instruction": instruction,
            "method": f"0x{method:04x}",
            "parameter_count": count,
            "parameter_offsets": [header_offset + 4 + index * 4 for index in range(count)],
        }
        if method == 0x17FC:
            require(count == 1, "upper_deck SET_BEGIN_END count drift")
            row["semantic"] = "SET_BEGIN_END"
            row["primitive"] = "QUADS" if parameters[0] == 8 else "END" if parameters[0] == 0 else "OTHER"
        elif method == 0x1810:
            require(count == 1, "upper_deck DRAW_ARRAYS count drift")
            start, draw_count = decode_draw_arrays(parameters[0])
            row.update({
                "semantic": "DRAW_ARRAYS",
                "start": start,
                "draw_count": draw_count,
                "count_bit_mask": "0xff000000",
                "preserved_start_bit_mask": "0x00ffffff",
                "count_byte_offset": header_offset + 7,
            })
        else:
            raise BoundaryError(f"upper_deck gained unexpected method 0x{method:04x}")
        commands.append(row)
        cursor += 1 + count
    require(cursor == 6 and len(commands) == 3, "upper_deck command shape drift")
    require(
        [row["semantic"] for row in commands] == ["SET_BEGIN_END", "DRAW_ARRAYS", "SET_BEGIN_END"]
        and commands[0].get("primitive") == "QUADS"
        and commands[1].get("start") == 0
        and commands[1].get("draw_count") == SOURCE_VERTEX_COUNT
        and commands[2].get("primitive") == "END",
        "upper_deck is no longer one start-zero 12-vertex quad draw",
    )
    return {
        "span": _span(PUSH_OFFSET, PUSH_SIZE, decoded),
        "word_count": 6,
        "command_count": 3,
        "commands": commands,
        "retail_command_words_embedded": False,
    }


def _raw_aligned_pointer_candidates(
    decoded: bytes, start: int, end: int, known_payload_intervals: list[tuple[int, int, str]]
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for field in range(0, catalog_tool.SYSTEM_BYTES - 3, 4):
        stored = struct.unpack_from("<i", decoded, field)[0]
        target = relative_target(field, stored)
        if target is None or not start <= target < end:
            continue
        container = next(
            (label for left, right, label in known_payload_intervals if left <= field < right),
            "unclassified_aligned_word",
        )
        result.append({
            "field_offset": field,
            "target_offset": target,
            "containing_payload_class": container,
        })
    return result


def _probe_prefix_shrink(source: dict[str, Any], new_count: int) -> dict[str, object]:
    require(new_count in (4, 8), "checked changed-count probes are exactly 4 and 8")
    before = bytes(source["decoded"])
    edited = bytearray(before)
    struct.pack_into("<H", edited, VERTEX_COUNT_FIELD, new_count)
    old_parameter = struct.unpack_from("<I", edited, DRAW_PARAMETER_OFFSET)[0]
    old_start, old_count = decode_draw_arrays(old_parameter)
    require((old_start, old_count) == (0, SOURCE_VERTEX_COUNT), "source draw parameter drift")
    struct.pack_into("<I", edited, DRAW_PARAMETER_OFFSET, encode_draw_arrays(0, new_count))
    after = bytes(edited)
    changed_offsets = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    require(changed_offsets == [VERTEX_COUNT_FIELD, DRAW_COUNT_BYTE_OFFSET],
            "prefix shrink changed bytes outside the two coupled count bytes")

    reparsed, _, _, _ = parse_scene(
        catalog_tool.SCENE_INDEX, source["resource"], after, {}
    )
    shape = reparsed["shapes"][SHAPE_INDEX]
    submeshes = [row for row in reparsed["submeshes"] if row["shape_index"] == SHAPE_INDEX]
    require(len(submeshes) == 1, "prefix shrink target submesh set drift")
    submesh = submeshes[0]
    require(
        shape["vertex_count"] == new_count
        and [row["byte_size"] for row in shape["vertex_streams"]] == [
            new_count * STREAM0_STRIDE, new_count * STREAM1_STRIDE
        ]
        and submesh["draw_array_vertex_count"] == new_count
        and submesh["maximum_vertex_index"] == new_count - 1
        and submesh["all_vertex_references_in_bounds"] is True,
        "independent structural reparse did not derive the reduced count consistently",
    )

    encoded, compression = compress_vc_lz(
        after,
        stream_tag=1,
        offset_bits=12,
        max_encoded_size=catalog_tool.RETAIL_CONSUMED,
        verify_roundtrip=True,
    )
    decoded_back, parsed = decompress_vc_lz(encoded, catalog_tool.DECODED_SIZE)
    require(decoded_back == after and parsed.consumed_bytes == len(encoded),
            "prefix shrink VC-LZ reconstruction failed")
    gap = catalog_tool.RETAIL_CONSUMED - len(encoded)
    padding = catalog_tool.CHUNK_STORED_SIZE - len(encoded)
    alias = minimum_vc_lz_overlap_scratch(
        encoded, catalog_tool.CHUNK_STORED_SIZE, catalog_tool.DECODED_SIZE
    )
    scratch = (max(padding, alias) + 15) & ~15
    header = bytearray(bytes(source["span"])[:HEADER.size])
    struct.pack_into("<I", header, 0x14, scratch)
    rebuilt = bytes(header) + encoded + bytes(gap) + bytes(source["tail"])
    require(
        len(rebuilt) == catalog_tool.CHUNK_SPAN_SIZE
        and rebuilt[-catalog_tool.OPAQUE_TAIL_SIZE:] == source["tail"],
        "prefix shrink did not preserve the fixed resource span and final tail",
    )
    return {
        "new_vertex_count": new_count,
        "physical_stream_payloads_changed": False,
        "changed_decoded_byte_count": len(changed_offsets),
        "changed_decoded_offsets": changed_offsets,
        "outside_two_count_bytes_bit_exact": True,
        "reparsed_shape_vertex_count": int(shape["vertex_count"]),
        "reparsed_draw_vertex_count": int(submesh["draw_array_vertex_count"]),
        "reparsed_maximum_vertex_index": int(submesh["maximum_vertex_index"]),
        "reparsed_all_references_in_bounds": True,
        "decoded_sha256": sha256_bytes(after),
        "rebuilt_consumed_bytes": len(encoded),
        "retail_consumed_cap_bytes": catalog_tool.RETAIL_CONSUMED,
        "zero_gap_bytes": gap,
        "total_stored_padding_bytes": padding,
        "minimum_alias_scratch_bytes": alias,
        "aligned_scratch_bytes": scratch,
        "encoded_sha256": sha256_bytes(encoded),
        "rebuilt_fixed_span_sha256": sha256_bytes(rebuilt),
        "literal_count": compression.literal_count,
        "match_count": compression.match_count,
        "full_decode_exact": True,
        "fixed_final_tail_exact": True,
        "output_archive_published": False,
        "independent_writer_verifier_used": False,
        "runtime_tested": False,
    }


def build_spec(index_path: Path = DEFAULT_INDEX) -> dict[str, Any]:
    evidence = _validate_evidence_files()
    catalog = _select_catalog_target()
    source = catalog_tool._load_source(index_path, catalog_tool.DEFAULT_SCAN)
    decoded = bytes(source["decoded"])
    scene = source["scene"]
    require(scene["name"] == "stadium" and len(scene["shapes"]) == 76,
            "pinned stadium scene drift")
    shape = scene["shapes"][SHAPE_INDEX]
    require(
        shape["record_offset"] == SHAPE_OFFSET
        and shape["name"] == SHAPE_NAME
        and shape["vertex_count"] == SOURCE_VERTEX_COUNT
        and shape["morph_channel_count"] == 0
        and shape["transform_count"] == 1
        and shape["submesh_count"] == 1,
        "upper_deck shape identity or counts drift",
    )
    attributes = [row for row in shape["attribute_descriptors"] if row["byte_size"]]
    require(
        [(row["register"], row["stream_index"], row["byte_offset"], row["byte_size"], row["format_name"])
         for row in attributes]
        == [
            (0, 0, 0, 12, "FLOAT3"),
            (1, 1, 8, 2, "SHORT1"),
            (3, 1, 0, 4, "D3DCOLOR"),
            (6, 1, 4, 4, "NORMSHORT2"),
        ],
        "upper_deck active declarations drift",
    )
    streams = shape["vertex_streams"]
    require(
        [(row["stream_index"], row["stride"], row["offset"], row["end_offset"])
         for row in streams]
        == [
            (0, STREAM0_STRIDE, STREAM0_OFFSET, STREAM0_SOURCE_END),
            (1, STREAM1_STRIDE, STREAM1_OFFSET, STREAM1_SOURCE_END),
        ],
        "upper_deck active stream layout drift",
    )
    submeshes = [row for row in scene["submeshes"] if row["shape_index"] == SHAPE_INDEX]
    require(len(submeshes) == 1, "upper_deck submesh identity drift")
    submesh = submeshes[0]
    require(
        submesh["record_offset"] == SUBMESH_OFFSET
        and submesh["command_offset"] == PUSH_OFFSET
        and submesh["primary_command_word_count"] == 6
        and submesh["secondary_command_word_count"] == 0
        and submesh["material_index"] == 1
        and submesh["auxiliary_index"] == 1,
        "upper_deck submesh fields drift",
    )

    push = _parse_push(decoded)
    pointer_rows = [
        _pointer_row(decoded, BLEND_POINTER_FIELD, "blended-palette table; inactive because blend_count is zero", "proved-loader-conditional"),
        _pointer_row(decoded, TRANSFORM_POINTER_FIELD, "one 0x70-byte transform record", "proved"),
        _pointer_row(decoded, SUBMESH_POINTER_FIELD, "one 0x80-byte submesh record", "proved"),
        _pointer_row(decoded, MORPH_POINTER_FIELD, "morph table; count is zero", "proved-structure-only"),
        _pointer_row(decoded, AUX_POINTER_78_FIELD, "relocated shape pointer with unresolved semantics", "proved-pointer-semantics-unknown"),
        _pointer_row(decoded, AUX_POINTER_7C_FIELD, "relocated shape pointer with unresolved semantics", "proved-pointer-semantics-unknown"),
        _pointer_row(decoded, STREAM_POINTER_FIELDS[0], "vertex stream 0", "proved"),
        _pointer_row(decoded, STREAM_POINTER_FIELDS[1], "vertex stream 1", "proved"),
        _pointer_row(decoded, PUSH_POINTER_FIELD, "six-word NV2A push stream", "proved"),
    ]
    require(
        [(row["field_offset"], row["target_offset"]) for row in pointer_rows]
        == [
            (BLEND_POINTER_FIELD, SUBMESH_OFFSET),
            (TRANSFORM_POINTER_FIELD, TRANSFORM_OFFSET),
            (SUBMESH_POINTER_FIELD, SUBMESH_OFFSET),
            (MORPH_POINTER_FIELD, None),
            (AUX_POINTER_78_FIELD, None),
            (AUX_POINTER_7C_FIELD, None),
            (STREAM_POINTER_FIELDS[0], STREAM0_OFFSET),
            (STREAM_POINTER_FIELDS[1], STREAM1_OFFSET),
            (PUSH_POINTER_FIELD, PUSH_OFFSET),
        ],
        "upper_deck pointer ledger drift",
    )
    require(struct.unpack_from("<H", decoded, BLEND_COUNT_FIELD)[0] == 0,
            "upper_deck blend count drift")

    known_payloads: list[tuple[int, int, str]] = []
    for source_shape in scene["shapes"]:
        source_shape_index = int(source_shape["index"])
        target_id = (
            f"nfl2k5/stadium/o{catalog_tool.OUTER_INDEX}/"
            f"c{catalog_tool.CHUNK_INDEX}/s{source_shape_index}"
        )
        for stream in source_shape["vertex_streams"]:
            stream_index = int(stream["stream_index"])
            key = "position_stream" if stream_index == 0 else f"attribute_stream_{stream_index}"
            known_payloads.append((
                int(stream["offset"]), int(stream["end_offset"]), f"{target_id}:{key}"
            ))
        for key, start, count, stride in (
            ("transform_table", source_shape["transform_offset"], source_shape["transform_count"], 0x70),
            ("submesh_table", source_shape["submesh_offset"], source_shape["submesh_count"], 0x80),
            ("morph_table", source_shape["morph_channel_offset"], source_shape["morph_channel_count"], 0x0C),
        ):
            if start is not None:
                known_payloads.append((int(start), int(start) + int(count) * stride, f"{target_id}:{key}"))
    for source_submesh in scene["submeshes"]:
        start = source_submesh["command_offset"]
        if start is not None:
            target_id = (
                f"nfl2k5/stadium/o{catalog_tool.OUTER_INDEX}/"
                f"c{catalog_tool.CHUNK_INDEX}/s{int(source_submesh['shape_index'])}"
            )
            known_payloads.append((
                int(start),
                int(start) + int(source_submesh["primary_command_word_count"]) * 4,
                f"{target_id}:push_stream",
            ))
    stream0_candidates = _raw_aligned_pointer_candidates(
        decoded, STREAM0_OFFSET, STREAM0_SOURCE_END, known_payloads
    )
    stream1_candidates = _raw_aligned_pointer_candidates(
        decoded, STREAM1_OFFSET, STREAM1_SOURCE_END, known_payloads
    )
    require(stream0_candidates == [{
        "field_offset": STREAM_POINTER_FIELDS[0],
        "target_offset": STREAM0_OFFSET,
        "containing_payload_class": "unclassified_aligned_word",
    }], "stream 0 aligned-pointer candidate census drift")
    require(
        len(stream1_candidates) == 2
        and stream1_candidates[0]["field_offset"] == STREAM_POINTER_FIELDS[1]
        and stream1_candidates[0]["target_offset"] == STREAM1_OFFSET
        and stream1_candidates[1]["field_offset"] == 399_120
        and stream1_candidates[1]["containing_payload_class"].endswith(":attribute_stream_1"),
        "stream 1 aligned-pointer candidate census drift",
    )

    probes = [_probe_prefix_shrink(source, count) for count in (8, 4)]
    source_index_hash = sha256_file(regular_file(index_path, "NFL archive index"))
    source_volume_hash = sha256_file(regular_file(index_path.parent / "9", "NFL volume 9"))
    require(source_index_hash == catalog_tool.INDEX_SHA256, "source index changed during analysis")
    require(source_volume_hash == catalog_tool.PACK_SHA256, "source volume changed during analysis")

    return {
        "schema": SCHEMA,
        "version": 1,
        "title": "NFL 2K5 upper_deck fixed-footprint source-subset changed-vertex-count boundary",
        "status": "target-specific requirements and in-memory fixed-span prefix-shrink probes proved; no writer, independent verifier, runtime, bounds, or production claim",
        "data_policy": {
            "contains_retail_vertex_values": False,
            "contains_retail_attribute_values": False,
            "contains_retail_index_values": False,
            "contains_retail_command_payload": False,
            "contains_modified_archive_bytes": False,
            "contains_hashes_offsets_counts_and_structural_semantics": True,
        },
        "claim_flags": {
            "target_structure_closed_for_prefix_shrink_probe": True,
            "two_count_bytes_and_fixed_span_fit_probed": True,
            "source_subset_record_copy_algorithm_specified": True,
            "changed_count_archive_writer_implemented": False,
            "independent_changed_count_verifier_implemented": False,
            "arbitrary_external_vertex_authoring_proved": False,
            "bounds_or_culling_serializer_proved": False,
            "collision_or_lod_ownership_proved": False,
            "runtime_visibility_proved": False,
            "original_xbox_hardware_proved": False,
            "production_ready": False,
        },
        "source_evidence": evidence,
        "source_identity": {
            "archive_index": {"name": "0", "size_bytes": catalog_tool.INDEX_SIZE, "sha256": source_index_hash},
            "volume": {"name": "9", "size_bytes": catalog_tool.PACK_SIZE, "sha256": source_volume_hash},
            "outer_index": catalog_tool.OUTER_INDEX,
            "outer_id": "0xe4d6b0bc",
            "chunk_index": catalog_tool.CHUNK_INDEX,
            "scene_index": catalog_tool.SCENE_INDEX,
            "scene_name": "stadium",
            "decoded_size_bytes": catalog_tool.DECODED_SIZE,
            "decoded_sha256": catalog_tool.DECODED_SHA256,
        },
        "target_selection": {
            "target_id": TARGET_ID,
            "shape_index": SHAPE_INDEX,
            "shape_name": SHAPE_NAME,
            "why_selected_over_group36": [
                "12 source vertices admit useful reductions to eight or four while group36 starts at four",
                "one material, one submesh, and one start-zero DRAW_ARRAYS QUADS batch eliminate index-buffer and command-capacity relayout",
                "both active streams have completely bounded fixed records and can be remapped as opaque whole records",
                "primary and secondary command word counts, push pointer, headers, methods, primitive mode, and allocation can remain exact",
            ],
            "selection_is_writer_claim": False,
            "selection_is_runtime_claim": False,
        },
        "recipe_contract": {
            "schema": "nfl2k5_upper_deck_source_subset_recipe/v1",
            "path": "reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json",
            "sha256": "4fac01c6cffe03481b456899ec2b2f3cd25f74954d5db94ccb3b8351f841ca4b",
            "admitted_changed_counts": [4, 8],
            "source_vertex_id_domain": [0, 11],
            "source_vertex_ids_must_be_unique": True,
            "external_positions_or_attributes_admitted": False,
            "writer_implemented": False,
        },
        "shape_and_coupled_fields": {
            "shape_record": _span(SHAPE_OFFSET, 0x100, decoded),
            "shape_version": 2,
            "source_vertex_count": SOURCE_VERTEX_COUNT,
            "vertex_count_field": {
                "offset": VERTEX_COUNT_FIELD,
                "encoding": "u16le",
                "evidence_status": "proved-serialized-and-runtime-allocation-consumer",
                "runtime_consumers": [
                    "0x000234a0 sizes copied stream-0 bytes as stream0_stride * vertex_count",
                    "0x00023510 copies that same stream-0 byte count into the runtime shape clone",
                    "NV2A topology must independently remain below the serialized count",
                ],
                "consumer_closure": "partial; no exhaustive bounds/collision/LOD/culling ownership proof",
            },
            "other_count_fields_preserved": [
                {"offset": SHAPE_OFFSET + 0x4E, "name": "morph_channel_count", "value": 0},
                {"offset": SHAPE_OFFSET + 0x50, "name": "base_transform_count", "value": 1},
                {"offset": BLEND_COUNT_FIELD, "name": "blended_palette_count", "value": 0},
                {"offset": SHAPE_OFFSET + 0x54, "name": "submesh_count", "value": 1},
            ],
            "pointer_ledger": pointer_rows,
            "loader_derived_fields_preserved": [
                {
                    "offset": SHAPE_OFFSET + 0x58,
                    "serialized_value": 0,
                    "runtime_meaning": "loader recomputes total primary push bytes; six words derive 24 bytes",
                    "evidence_status": "proved-at-0x00022f90",
                }
            ],
            "inactive_blend_pointer_alias": {
                "count_field_offset": BLEND_COUNT_FIELD,
                "count": 0,
                "pointer_field_offset": BLEND_POINTER_FIELD,
                "pointer_target": SUBMESH_OFFSET,
                "interpretation": "serialized pointer aliases the submesh start but loader relocation/use is conditional on nonzero blend count",
                "writer_policy": "preserve count and pointer bytes exactly; never treat alias target as blend capacity",
            },
        },
        "vertex_record_contract": {
            "active_stream_count": 2,
            "declarations_preserved_exact": True,
            "streams": [
                {
                    "stream_index": 0,
                    "pointer_field_offset": STREAM_POINTER_FIELDS[0],
                    "stride_field_offset": STREAM_STRIDE_FIELDS[0],
                    "stride_bytes": STREAM0_STRIDE,
                    "source_physical_span": _span(STREAM0_OFFSET, SOURCE_VERTEX_COUNT * STREAM0_STRIDE, decoded),
                    "record_lanes": [
                        {"register": 0, "offset": 0, "size_bytes": 12, "format": "FLOAT3", "semantic": "POSITION"}
                    ],
                    "record_bytes_covered_by_declarations": 12,
                },
                {
                    "stream_index": 1,
                    "pointer_field_offset": STREAM_POINTER_FIELDS[1],
                    "stride_field_offset": STREAM_STRIDE_FIELDS[1],
                    "stride_bytes": STREAM1_STRIDE,
                    "source_physical_span": _span(STREAM1_OFFSET, SOURCE_VERTEX_COUNT * STREAM1_STRIDE, decoded),
                    "record_lanes": [
                        {"register": 3, "offset": 0, "size_bytes": 4, "format": "D3DCOLOR", "semantic": "shader-specific-preserve"},
                        {"register": 6, "offset": 4, "size_bytes": 4, "format": "NORMSHORT2", "semantic": "shader-specific-preserve"},
                        {"register": 1, "offset": 8, "size_bytes": 2, "format": "SHORT1", "semantic": "sole-transform selector; preserve by whole-record copy"},
                    ],
                    "record_bytes_covered_by_declarations": 10,
                },
            ],
            "source_subset_rule": [
                "recipe length is the new vertex_count and must be four or eight for a changed build",
                "each source ID is a distinct integer in [0,12); source order is the authored native quad order",
                "copy the selected source's complete 12-byte stream-0 record and complete 10-byte stream-1 record to the corresponding destination prefix slot",
                "do not decode, synthesize, normalize, weld, or independently reorder shader-specific lanes",
                "bytes after new_count*stride through the original physical end remain exact retail tail bytes and are not slack",
            ],
            "reference_remap_algorithm": "remap_stream_prefix in the spec generator; unit-tested only on synthetic nonretail records",
            "arbitrary_position_edit_policy": "blocked; this first changed-count profile copies source positions exactly because bounds/culling ownership is unresolved",
        },
        "topology_contract": {
            "submesh_record": _span(SUBMESH_OFFSET, 0x80, decoded),
            "material_index": 1,
            "auxiliary_index": 1,
            "push_pointer_field_offset": PUSH_POINTER_FIELD,
            "primary_word_count_field_offset": PRIMARY_WORD_COUNT_FIELD,
            "primary_word_count": 6,
            "secondary_word_count_field_offset": SECONDARY_WORD_COUNT_FIELD,
            "secondary_word_count": 0,
            "push": push,
            "admissible_vertex_counts": list(admissible_quad_counts()),
            "changed_vertex_counts": [4, 8],
            "no_op_vertex_count": 12,
            "derivation": "one DRAW_ARRAYS range starts at zero; QUADS consumes complete groups of four; source has 12 vertices; count field holds one-through-256",
            "only_mutable_topology_bits": {
                "parameter_offset": DRAW_PARAMETER_OFFSET,
                "count_byte_offset": DRAW_COUNT_BYTE_OFFSET,
                "bit_mask": "0xff000000",
                "encode": "(new_count - 1) << 24 with preserved start zero",
            },
            "must_remain_exact": [
                "all three command headers, instructions, methods, parameter counts, and word positions",
                "QUADS begin mode, END marker, DRAW_ARRAYS start, push pointer, and six-word primary count",
                "submesh/material/auxiliary indices and the entire secondary-count path",
            ],
            "command_capacity_result": "closed for this profile because no command is added or removed and the six-word span remains fully occupied",
        },
        "interval_and_alias_ledger": {
            "ordered_target_intervals": [
                {"name": "transform", "start": TRANSFORM_OFFSET, "end": SUBMESH_OFFSET, "policy": "preserve"},
                {"name": "submesh", "start": SUBMESH_OFFSET, "end": PUSH_OFFSET, "policy": "preserve except no fields in this profile"},
                {"name": "push", "start": PUSH_OFFSET, "end": PUSH_OFFSET + PUSH_SIZE, "policy": "only draw count byte may change"},
                {"name": "alignment_gap_before_stream0", "start": PUSH_OFFSET + PUSH_SIZE, "end": STREAM0_OFFSET, "policy": "preserve; not capacity"},
                {"name": "stream0_physical", "start": STREAM0_OFFSET, "end": STREAM0_SOURCE_END, "policy": "prefix whole-record remap; logical tail exact"},
                {"name": "alignment_gap_between_streams", "start": STREAM0_SOURCE_END, "end": STREAM1_OFFSET, "policy": "preserve; not capacity"},
                {"name": "stream1_physical", "start": STREAM1_OFFSET, "end": STREAM1_SOURCE_END, "policy": "prefix whole-record remap; logical tail exact"},
                {"name": "gap_before_next_shape_payload", "start": STREAM1_SOURCE_END, "end": 70_400, "policy": "preserve; not capacity"},
            ],
            "logical_end_formula": "stream_start + new_count * stride",
            "recognized_owner_pointers": {
                "stream0": [STREAM_POINTER_FIELDS[0]],
                "stream1": [STREAM_POINTER_FIELDS[1]],
                "push": [PUSH_POINTER_FIELD],
            },
            "aligned_raw_word_scan": {
                "scope": "every four-byte-aligned word in the decoded system buffer interpreted conservatively as a one-based relative pointer",
                "stream0_candidates": stream0_candidates,
                "stream1_candidates": stream1_candidates,
                "stream1_nonowner_explanation": "the extra aligned value occurs inside another shape's fully bounded vertex stream, not a recovered structural pointer field",
                "proof_limit": "this heuristic does not exclude unaligned, encoded, executable-created, or semantics-unknown aliases",
            },
        },
        "prefix_shrink_probe": {
            "method": "in-memory only; leave both physical streams exact, reduce shape count and the existing start-zero DRAW_ARRAYS count, reparse full SCNE, recompress under the retail cap, and independently decode the rebuilt stream",
            "probes": probes,
            "source_archive_modified": False,
            "modified_archive_published": False,
            "proof_scope": "serialized count/control coupling and deterministic fixed-span fit only",
            "not_proved": [
                "runtime loader acceptance of the changed wrapper scratch",
                "visibility, culling, collision, LOD, or semantic usefulness",
                "whole-record nonidentity subset remap on retail bytes",
                "writer publication safety or independent verifier separation",
            ],
        },
        "future_writer_fail_closed_contract": {
            "authorized_decoded_changes": [
                "u16le shape vertex_count field",
                "high count byte of the one DRAW_ARRAYS parameter",
                "for a nonidentity subset only, complete records in each stream prefix through new_count*stride",
            ],
            "mandatory_preservation": [
                "all physical bytes after each new logical stream end",
                "all declarations, strides, pointers, non-count command bits, records, tables, unknowns, gaps, and sibling payloads",
                "system_bytes, video_bytes, decoded length, outer offset/size, fixed final 16-byte tail, and copied-volume complement",
            ],
            "mandatory_rejections": [
                "new count outside {4,8}, duplicate/out-of-range/non-integer source ID, or subset length mismatch",
                "any external POSITION or shader-specific attribute value in this source-subset-only profile",
                "any command other than the existing start-zero DRAW_ARRAYS range or any change to its headers/mode/start/word count",
                "any pointer, alias, declaration, stride, material, transform, selector semantics, morph, skin, bounds, collision, or LOD ambiguity touched by the request",
                "VC-LZ cap overflow, scratch outside a separately accepted runtime boundary, failed full decode, fixed-tail drift, or unauthorized byte difference",
                "source mutation, existing output, aliasing source/output paths, or non-exclusive publication",
            ],
            "no_op_rule": "new_count 12 with identity source order must return the validated retail resource/volume bytes verbatim without recompression",
            "independent_verifier_requirements": [
                "must not import writer, production parser, compressor, or serializer modules",
                "rederive target identity, every pointer/span/declaration/stride/count, the complete six-word command grammar, and exact authorized changed-byte set",
                "reconstruct every destination record from source ID and compare both complete stream prefixes plus exact physical tails",
                "decode final topology to ordered quads, require draw_count == vertex_count and all references below count",
                "independently decompress the complete fixed resource and hash the final tail, wrapper complement, sibling bytes, source, output, and copied-volume complement",
            ],
        },
        "evidence_classification": {
            "proved": [
                "shape count field, both streams, all active record lanes, one submesh/material, and complete six-word push grammar are bounded and source-hash pinned",
                "loader relocates the enumerated pointers, conditionally relocates +0x60 by blend count, and derives total push bytes from primary counts",
                "runtime clone sizing/copy functions 0x000234a0 and 0x00023510 consume stream0_stride * vertex_count",
                "count-only reductions to eight and four reparse with draw_count equal to vertex_count and fit the fixed VC-LZ span in memory",
            ],
            "derived": [
                "the admissible count set {4,8,12} follows from start-zero DRAW_ARRAYS, QUADS groups of four, source count 12, and the one-byte count encoding",
                "a source subset can retain unknown attributes only by copying each selected vertex's entire record in every active stream",
                "logical tails created by a smaller count are preservation regions, not writable allocation",
            ],
            "candidate_not_implemented": [
                "count-only copied-volume prefix-shrink writer and independent verifier",
                "nonidentity ordered source-subset remap using complete records in both streams",
                "runtime witness for both four- and eight-vertex variants",
            ],
            "blockers": [
                "bounds/frustum culling owner fields and update semantics are not recovered",
                "collision and LOD ownership for this stadium shape are not recovered",
                "runtime acceptance of changed VC-LZ scratch and changed count is untested",
                "arbitrary external positions, UVs, normals, colors, materials, and topology are outside this source-record subset profile",
                "an exhaustive proof that no semantics-unknown or runtime-created alias consumes the shortened logical tails is still missing",
            ],
        },
    }


def canonical_bytes(index_path: Path = DEFAULT_INDEX) -> bytes:
    return canonical_json(build_spec(index_path))


def validate_spec(data: dict[str, Any]) -> dict[str, object]:
    require(data.get("schema") == SCHEMA, "checked changed-count schema drift")
    policy = data.get("data_policy", {})
    for key in (
        "contains_retail_vertex_values",
        "contains_retail_attribute_values",
        "contains_retail_index_values",
        "contains_retail_command_payload",
        "contains_modified_archive_bytes",
    ):
        require(policy.get(key) is False, f"data policy overclaims {key}")
    flags = data.get("claim_flags", {})
    require(flags.get("target_structure_closed_for_prefix_shrink_probe") is True,
            "target structural closure claim is missing")
    require(flags.get("two_count_bytes_and_fixed_span_fit_probed") is True,
            "fixed-span probe claim is missing")
    for key in (
        "changed_count_archive_writer_implemented",
        "independent_changed_count_verifier_implemented",
        "arbitrary_external_vertex_authoring_proved",
        "bounds_or_culling_serializer_proved",
        "collision_or_lod_ownership_proved",
        "runtime_visibility_proved",
        "original_xbox_hardware_proved",
        "production_ready",
    ):
        require(flags.get(key) is False, f"unproved claim is true: {key}")
    topology = data["topology_contract"]
    require(topology["admissible_vertex_counts"] == [4, 8, 12],
            "admissible count derivation drift")
    require(topology["changed_vertex_counts"] == [4, 8], "changed count set drift")
    require(topology["primary_word_count"] == 6 and topology["secondary_word_count"] == 0,
            "command word counts drift")
    recipe = data.get("recipe_contract", {})
    require(
        recipe.get("schema") == "nfl2k5_upper_deck_source_subset_recipe/v1"
        and recipe.get("admitted_changed_counts") == [4, 8]
        and recipe.get("source_vertex_ids_must_be_unique") is True
        and recipe.get("external_positions_or_attributes_admitted") is False
        and recipe.get("writer_implemented") is False,
        "future recipe contract drift",
    )
    probes = data["prefix_shrink_probe"]["probes"]
    require([row["new_vertex_count"] for row in probes] == [8, 4], "probe order/count drift")
    require(all(row["changed_decoded_offsets"] == [VERTEX_COUNT_FIELD, DRAW_COUNT_BYTE_OFFSET] for row in probes),
            "probe authorized changed offsets drift")
    require(all(row["rebuilt_consumed_bytes"] <= row["retail_consumed_cap_bytes"] for row in probes),
            "checked prefix probe exceeds retail VC-LZ cap")
    require(data["evidence_classification"]["blockers"], "blocker list must not be empty")
    return {
        "schema": "nfl2k5_upper_deck_changed_count_boundary_validation/v1",
        "target": TARGET_ID,
        "source_vertices": SOURCE_VERTEX_COUNT,
        "changed_counts": [4, 8],
        "streams": 2,
        "push_words": 6,
        "changed_bytes_per_prefix_probe": 2,
        "writer_implemented": False,
        "runtime_proved": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--write", action="store_true", help="write canonical checked JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generated = canonical_bytes(args.index)
    if args.write:
        args.spec.parent.mkdir(parents=True, exist_ok=True)
        args.spec.write_bytes(generated)
    require(args.spec.is_file() and not args.spec.is_symlink(),
            f"checked spec is missing or unsafe: {args.spec}")
    checked = args.spec.read_bytes()
    require(checked == generated, "checked changed-count spec is not canonical")
    result = validate_spec(json.loads(checked))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BoundaryError, OSError, json.JSONDecodeError, struct.error) as exc:
        print(f"NFL_UPPER_DECK_CHANGED_COUNT_SPEC_ERROR: {exc}")
        raise SystemExit(1)
