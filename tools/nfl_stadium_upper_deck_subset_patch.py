#!/usr/bin/env python3
"""Fail-closed NFL 2K5 ``upper_deck`` source-subset count writer.

This is a single-target, fixed-allocation writer rather than a general mesh
importer.  Changed recipes select four or eight distinct records from the
pinned 12-vertex retail source.  The writer copies each selected record in
full across both active streams, updates only the coupled shape/DRAW_ARRAYS
count controls, preserves both physical stream tails, and rebuilds the exact
fixed SCNE span under the retail VC-LZ consumed-stream cap.

The 12-vertex identity operation is exposed only through ``--identity-noop``.
It validates the same pinned source and returns the complete source resource
span verbatim without invoking the compressor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any, Iterable

import nfl_stadium_catalog_position_patch as base
from nfl_txtr import (
    HEADER,
    TxtrError,
    compress_vc_lz,
    decompress_vc_lz,
    minimum_vc_lz_overlap_scratch,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
DEFAULT_BOUNDARY = ROOT / "reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json"
DEFAULT_RECIPE_SCHEMA = ROOT / "reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json"

RECIPE_SCHEMA = "nfl2k5_upper_deck_source_subset_recipe/v1"
IDENTITY_REQUEST_SCHEMA = "nfl2k5_upper_deck_identity_noop_request/v1"
MANIFEST_SCHEMA = "nfl2k5_upper_deck_source_subset_patch/v1"
BOUNDARY_SCHEMA = "nfl2k5_upper_deck_changed_count_boundary/v1"
TARGET_ID = "nfl2k5/stadium/o3280/c5/s1"

CATALOG_SIZE = 858_600
CATALOG_SHA256 = "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa"
BOUNDARY_SIZE = 25_285
BOUNDARY_SHA256 = "e583dde9bca86971eb7355fd07b6a6646a09af8356623b4114c3003998ea4bdb"
RECIPE_SCHEMA_SIZE = 2_209
RECIPE_SCHEMA_SHA256 = "4fac01c6cffe03481b456899ec2b2f3cd25f74954d5db94ccb3b8351f841ca4b"
MAX_RECIPE_BYTES = 4 * 1024

SOURCE_VERTEX_COUNT = 12
CHANGED_COUNTS = (4, 8)
SHAPE_INDEX = 1
SHAPE_NAME = "upper_deck"
SHAPE_VERTEX_COUNT_OFFSET = 30_540
DRAW_COUNT_BYTE_OFFSET = 69_887
PUSH_OFFSET = 69_872
PUSH_SIZE = 24
STREAMS = (
    {
        "stream_index": 0,
        "offset": 69_920,
        "end_offset": 70_064,
        "stride_bytes": 12,
        "source_sha256": "95164ce59e125ac1775003846a1eb780c63f001c65f2b3da8d2aebd20fbe67f7",
    },
    {
        "stream_index": 1,
        "offset": 70_080,
        "end_offset": 70_200,
        "stride_bytes": 10,
        "source_sha256": "5ad69b6eff91ed58f1882d08f9f69b299d0ea32d53cf729a6c0fb8a2a7c7cabe",
    },
)
PUSH_SHA256 = "6811dd478e03b4be22628c3f07c27d2dcb7791b98e0f409086e3c4267bfce1b0"


class UpperDeckSubsetPatchError(ValueError):
    """An authority, request, source, edit, budget, or publication rule failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise UpperDeckSubsetPatchError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def regular(path: Path, label: str) -> Path:
    path = path.expanduser()
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise UpperDeckSubsetPatchError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def _load_json(path: Path, label: str, maximum: int) -> tuple[dict[str, Any], bytes]:
    selected = regular(path, label)
    size = selected.stat().st_size
    require(0 < size <= maximum, f"{label} size is outside its limit")
    payload = selected.read_bytes()
    require(len(payload) == size, f"{label} changed while reading")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                UpperDeckSubsetPatchError(
                    f"non-finite JSON constant {token} is forbidden"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpperDeckSubsetPatchError(f"{label} is not UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict), f"{label} root must be an object")
    require(payload == canonical_json(value), f"{label} must be canonical sorted JSON")
    return value, payload


def _load_pinned_json(
    path: Path, label: str, size: int, digest: str
) -> tuple[dict[str, Any], bytes]:
    value, payload = _load_json(path, label, size)
    require(len(payload) == size and sha256(payload) == digest,
            f"{label} size or SHA-256 differs from the pinned authority")
    return value, payload


def _validate_boundary(boundary: dict[str, Any]) -> None:
    require(boundary.get("schema") == BOUNDARY_SCHEMA,
            "changed-count boundary schema differs")
    require(boundary.get("target_selection", {}).get("target_id") == TARGET_ID,
            "changed-count target identity differs")
    identity = boundary.get("source_identity", {})
    require(identity == {
        "archive_index": {
            "name": "0", "sha256": base.INDEX_SHA256,
            "size_bytes": base.INDEX_SIZE,
        },
        "chunk_index": base.CHUNK_INDEX,
        "decoded_sha256": base.DECODED_SHA256,
        "decoded_size_bytes": base.DECODED_SIZE,
        "outer_id": "0xe4d6b0bc",
        "outer_index": base.OUTER_INDEX,
        "scene_index": 2648,
        "scene_name": "stadium",
        "volume": {
            "name": "9", "sha256": base.PACK_SHA256,
            "size_bytes": base.PACK_SIZE,
        },
    }, "changed-count source identity differs")
    shape = boundary.get("shape_and_coupled_fields", {})
    require(shape.get("source_vertex_count") == SOURCE_VERTEX_COUNT,
            "boundary source vertex count differs")
    require(shape.get("vertex_count_field", {}).get("offset") == SHAPE_VERTEX_COUNT_OFFSET,
            "boundary shape count offset differs")
    topology = boundary.get("topology_contract", {})
    require(topology.get("changed_vertex_counts") == [4, 8]
            and topology.get("no_op_vertex_count") == SOURCE_VERTEX_COUNT,
            "boundary admitted counts differ")
    require(topology.get("primary_word_count") == 6
            and topology.get("secondary_word_count") == 0,
            "boundary push allocation differs")
    mutable = topology.get("only_mutable_topology_bits", {})
    require(mutable.get("count_byte_offset") == DRAW_COUNT_BYTE_OFFSET
            and mutable.get("bit_mask") == "0xff000000",
            "boundary DRAW_ARRAYS count control differs")
    require(topology.get("push", {}).get("span") == {
        "end_offset": PUSH_OFFSET + PUSH_SIZE,
        "offset": PUSH_OFFSET,
        "sha256": PUSH_SHA256,
        "size_bytes": PUSH_SIZE,
    }, "boundary push span differs")
    stream_rows = boundary.get("vertex_record_contract", {}).get("streams")
    require(isinstance(stream_rows, list) and len(stream_rows) == len(STREAMS),
            "boundary stream list differs")
    for expected, observed in zip(STREAMS, stream_rows):
        span = observed.get("source_physical_span", {})
        require(observed.get("stream_index") == expected["stream_index"]
                and observed.get("stride_bytes") == expected["stride_bytes"]
                and span == {
                    "end_offset": expected["end_offset"],
                    "offset": expected["offset"],
                    "sha256": expected["source_sha256"],
                    "size_bytes": SOURCE_VERTEX_COUNT * expected["stride_bytes"],
                }, f"boundary stream {expected['stream_index']} differs")
    no_op_rule = boundary.get("future_writer_fail_closed_contract", {}).get("no_op_rule")
    require(isinstance(no_op_rule, str) and "without recompression" in no_op_rule,
            "boundary identity no-op rule differs")


def _validate_recipe_schema(schema: dict[str, Any]) -> None:
    require(schema.get("$id") == RECIPE_SCHEMA
            and schema.get("additionalProperties") is False,
            "recipe schema identity or closed-object rule differs")
    required = schema.get("required")
    require(required == [
        "schema", "target_id", "source_decoded_sha256",
        "new_vertex_count", "source_vertex_ids",
    ], "recipe schema required fields differ")
    properties = schema.get("properties", {})
    require(properties.get("schema", {}).get("const") == RECIPE_SCHEMA
            and properties.get("target_id", {}).get("const") == TARGET_ID
            and properties.get("source_decoded_sha256", {}).get("const") == base.DECODED_SHA256,
            "recipe schema source/target pins differ")
    require(properties.get("new_vertex_count", {}).get("enum") == [4, 8],
            "recipe schema changed-count domain differs")
    ids = properties.get("source_vertex_ids", {})
    require(ids.get("uniqueItems") is True
            and ids.get("minItems") == 4 and ids.get("maxItems") == 8
            and ids.get("items") == {
                "maximum": 11, "minimum": 0, "type": "integer",
            }, "recipe schema source-ID domain differs")


def load_authorities(
    catalog_path: Path = DEFAULT_CATALOG,
    boundary_path: Path = DEFAULT_BOUNDARY,
    recipe_schema_path: Path = DEFAULT_RECIPE_SCHEMA,
) -> dict[str, Any]:
    catalog_selected = regular(catalog_path, "stadium target catalog")
    require(catalog_selected.stat().st_size == CATALOG_SIZE
            and sha256_file(catalog_selected) == CATALOG_SHA256,
            "stadium target catalog size or SHA-256 differs from the pinned authority")
    try:
        catalog = base.load_catalog(catalog_selected)
    except base.CatalogPositionPatchError as exc:
        raise UpperDeckSubsetPatchError(str(exc)) from exc
    require(catalog["sha256"] == CATALOG_SHA256 and catalog["size"] == CATALOG_SIZE,
            "loaded catalog identity differs")
    row = catalog["targets"].get(TARGET_ID)
    require(isinstance(row, dict), "pinned catalog does not contain upper_deck")
    try:
        contract = base._validate_target_row(row)
    except base.CatalogPositionPatchError as exc:
        raise UpperDeckSubsetPatchError(str(exc)) from exc
    require(contract == {
        "offset": STREAMS[0]["offset"],
        "size": SOURCE_VERTEX_COUNT * STREAMS[0]["stride_bytes"],
        "end": STREAMS[0]["end_offset"],
        "vertex_count": SOURCE_VERTEX_COUNT,
        "shape_index": SHAPE_INDEX,
        "shape_name": SHAPE_NAME,
    }, "catalog upper_deck target contract differs")
    require(row.get("selectors", {}).get("stream") == {
        "end_offset": STREAMS[1]["end_offset"],
        "offset": STREAMS[1]["offset"],
        "sha256": STREAMS[1]["source_sha256"],
        "size": SOURCE_VERTEX_COUNT * STREAMS[1]["stride_bytes"],
    }, "catalog upper_deck secondary stream differs")

    boundary, boundary_payload = _load_pinned_json(
        boundary_path, "upper_deck changed-count boundary",
        BOUNDARY_SIZE, BOUNDARY_SHA256,
    )
    _validate_boundary(boundary)
    recipe_schema, schema_payload = _load_pinned_json(
        recipe_schema_path, "upper_deck source-subset recipe schema",
        RECIPE_SCHEMA_SIZE, RECIPE_SCHEMA_SHA256,
    )
    _validate_recipe_schema(recipe_schema)
    return {
        "catalog": catalog,
        "row": row,
        "boundary": boundary,
        "recipe_schema": recipe_schema,
        "authority": {
            "catalog": {
                "schema": base.CATALOG_SCHEMA,
                "size": CATALOG_SIZE,
                "sha256": CATALOG_SHA256,
                "authorized_target_count": len(catalog["targets"]),
            },
            "changed_count_boundary": {
                "schema": BOUNDARY_SCHEMA,
                "size": len(boundary_payload),
                "sha256": BOUNDARY_SHA256,
            },
            "recipe_schema": {
                "schema": RECIPE_SCHEMA,
                "size": len(schema_payload),
                "sha256": RECIPE_SCHEMA_SHA256,
            },
        },
    }


def _validate_source_ids(values: object, expected_count: int) -> list[int]:
    require(isinstance(values, list) and len(values) == expected_count,
            f"source_vertex_ids must contain exactly {expected_count} IDs")
    result: list[int] = []
    for ordinal, value in enumerate(values):
        require(type(value) is int,
                f"source_vertex_ids[{ordinal}] must be an integer, not a boolean")
        require(0 <= value < SOURCE_VERTEX_COUNT,
                f"source_vertex_ids[{ordinal}] is outside [0,11]")
        result.append(value)
    require(len(set(result)) == len(result),
            "source_vertex_ids must be unique; implicit welding is forbidden")
    return result


def _request_summary(kind: str, schema: str, payload: bytes,
        new_count: int, source_ids: list[int]) -> dict[str, Any]:
    return {
        "kind": kind,
        "schema": schema,
        "sha256": sha256(payload),
        "new_vertex_count": new_count,
        "source_vertex_id_count": len(source_ids),
        "source_vertex_ids_sha256": sha256(canonical_json(source_ids)),
        "contains_external_vertex_or_attribute_values": False,
    }


def load_request(
    recipe_path: Path | None,
    identity_noop: bool,
    authorities: dict[str, Any],
) -> dict[str, Any]:
    require(identity_noop != (recipe_path is not None),
            "select exactly one of identity_noop or a changed recipe")
    if identity_noop:
        source_ids = list(range(SOURCE_VERTEX_COUNT))
        identity = {
            "operation": "validated_identity_noop",
            "schema": IDENTITY_REQUEST_SCHEMA,
            "source_decoded_sha256": base.DECODED_SHA256,
            "source_vertex_ids": source_ids,
            "target_id": TARGET_ID,
            "vertex_count": SOURCE_VERTEX_COUNT,
        }
        payload = canonical_json(identity)
        return {
            "mode": "identity_noop",
            "new_count": SOURCE_VERTEX_COUNT,
            "source_ids": source_ids,
            "summary": _request_summary(
                "identity_noop_flag", IDENTITY_REQUEST_SCHEMA,
                payload, SOURCE_VERTEX_COUNT, source_ids,
            ),
        }

    assert recipe_path is not None
    value, payload = _load_json(recipe_path, "upper_deck source-subset recipe", MAX_RECIPE_BYTES)
    require(set(value) == {
        "schema", "target_id", "source_decoded_sha256",
        "new_vertex_count", "source_vertex_ids",
    }, "recipe fields differ from source-subset v1")
    require(value.get("schema") == RECIPE_SCHEMA, "recipe schema differs")
    require(value.get("target_id") == TARGET_ID, "recipe target differs from upper_deck")
    require(value.get("source_decoded_sha256") == base.DECODED_SHA256,
            "recipe decoded-source identity differs")
    new_count = value.get("new_vertex_count")
    require(type(new_count) is int and new_count in CHANGED_COUNTS,
            "changed recipe vertex count must be exactly 4 or 8")
    source_ids = _validate_source_ids(value.get("source_vertex_ids"), new_count)
    mode = "count_only_prefix" if source_ids == list(range(new_count)) else "source_subset_remap"
    return {
        "mode": mode,
        "new_count": new_count,
        "source_ids": source_ids,
        "summary": _request_summary(
            "changed_source_subset_recipe", RECIPE_SCHEMA,
            payload, new_count, source_ids,
        ),
    }


def _decode_header(header: int) -> tuple[int, int, int]:
    require((header & 0xE0030003) in (0, 0x40000000),
            "NV2A command header signature differs")
    return (header >> 29) & 7, (header >> 18) & 0x7FF, header & 0x1FFC


def _draw_count(decoded: bytes) -> tuple[int, int]:
    parameter = struct.unpack_from("<I", decoded, PUSH_OFFSET + 12)[0]
    return parameter & 0x00FFFFFF, ((parameter >> 24) & 0xFF) + 1


def _validate_source_decoded(decoded: bytes) -> None:
    require(len(decoded) == base.DECODED_SIZE and sha256(decoded) == base.DECODED_SHA256,
            "source decoded SCNE identity differs")
    require(struct.unpack_from("<H", decoded, SHAPE_VERTEX_COUNT_OFFSET)[0]
            == SOURCE_VERTEX_COUNT, "source shape vertex count differs")
    require(sha256(decoded[PUSH_OFFSET:PUSH_OFFSET + PUSH_SIZE]) == PUSH_SHA256,
            "source push stream differs")
    words = struct.unpack_from("<6I", decoded, PUSH_OFFSET)
    require(_decode_header(words[0]) == (0, 1, 0x17FC) and words[1] == 8,
            "source push BEGIN/QUADS command differs")
    require(_decode_header(words[2]) == (0, 1, 0x1810)
            and _draw_count(decoded) == (0, SOURCE_VERTEX_COUNT),
            "source push DRAW_ARRAYS command differs")
    require(_decode_header(words[4]) == (0, 1, 0x17FC) and words[5] == 0,
            "source push END command differs")
    for stream in STREAMS:
        start, end = stream["offset"], stream["end_offset"]
        require(end - start == SOURCE_VERTEX_COUNT * stream["stride_bytes"]
                and sha256(decoded[start:end]) == stream["source_sha256"],
                f"source stream {stream['stream_index']} differs")


def remap_stream_prefix(
    source_stream: bytes,
    stride: int,
    source_count: int,
    source_ids: Iterable[int],
) -> bytes:
    """Copy synchronized whole records into a prefix and retain the physical tail."""
    require(type(stride) is int and stride > 0, "stream stride must be positive")
    require(type(source_count) is int and source_count == SOURCE_VERTEX_COUNT,
            "source record count differs from the pinned target")
    require(len(source_stream) == stride * source_count,
            "source stream extent differs from count * stride")
    ids = list(source_ids)
    require(len(ids) in CHANGED_COUNTS or ids == list(range(SOURCE_VERTEX_COUNT)),
            "source subset length is not an admitted changed count or identity")
    checked = _validate_source_ids(ids, len(ids))
    result = bytearray(source_stream)
    for destination, source_id in enumerate(checked):
        source_start = source_id * stride
        destination_start = destination * stride
        result[destination_start:destination_start + stride] = (
            source_stream[source_start:source_start + stride]
        )
    return bytes(result)


def _ranges_complement(data: bytes, ranges: list[tuple[int, int]]) -> bytes:
    normalized = sorted(ranges)
    cursor = 0
    output = bytearray()
    for start, end in normalized:
        require(0 <= cursor <= start <= end <= len(data), "authorized range is invalid or overlaps")
        output.extend(data[cursor:start])
        cursor = end
    output.extend(data[cursor:])
    return bytes(output)


def _changed_byte_count(left: bytes, right: bytes) -> int:
    require(len(left) == len(right), "changed-byte operands differ in length")
    return sum(a != b for a, b in zip(left, right))


def _validate_edited_scene(decoded: bytes, new_count: int) -> None:
    record = base.ResourceRecord(
        outer_index=base.OUTER_INDEX,
        outer_id="0xe4d6b0bc",
        outer_size=base.OUTER_SIZE,
        chunk_index=base.CHUNK_INDEX,
        chunk_offset=base.CHUNK_ENTRY_OFFSET,
        kind="SCNE",
        stored_size=base.CHUNK_STORED_SIZE,
        word_08=base.SYSTEM_BYTES,
        word_0c=base.VIDEO_BYTES,
        word_10=0xFEEDBEEF,
        word_14=base.SOURCE_SCRATCH,
    )
    scene, _, _, _ = base.parse_scene(2648, record, decoded, {})
    require(scene.get("name") == "stadium", "rebuilt scene name differs")
    shapes = scene.get("shapes")
    require(isinstance(shapes, list) and len(shapes) > SHAPE_INDEX,
            "rebuilt scene does not contain upper_deck")
    shape = shapes[SHAPE_INDEX]
    require(shape.get("index") == SHAPE_INDEX and shape.get("name") == SHAPE_NAME
            and shape.get("version") == 2 and shape.get("vertex_count") == new_count,
            "rebuilt upper_deck shape/count differs")
    streams = shape.get("vertex_streams")
    require(isinstance(streams, list) and [
        (row.get("stream_index"), row.get("stride"), row.get("offset"), row.get("end_offset"))
        for row in streams
    ] == [
        (stream["stream_index"], stream["stride_bytes"], stream["offset"],
         stream["offset"] + new_count * stream["stride_bytes"])
        for stream in STREAMS
    ], "rebuilt logical stream ranges differ")
    submeshes = [
        row for row in scene.get("submeshes", [])
        if row.get("shape_index") == SHAPE_INDEX
    ]
    require(len(submeshes) == 1, "rebuilt upper_deck submesh count differs")
    push = submeshes[0]
    require(push.get("primary_command_word_count") == 6
            and push.get("secondary_command_word_count") == 0
            and push.get("command_offset") == PUSH_OFFSET
            and push.get("command_count") == 3,
            "rebuilt upper_deck command allocation differs")
    require(push.get("method_counts") == {"0x17fc": 2, "0x1810": 1}
            and push.get("unknown_method_counts") == {}
            and push.get("primitive_mode_counts") == {"END": 1, "QUADS": 1},
            "rebuilt upper_deck push grammar differs")
    require(push.get("index_element_count") == 0
            and push.get("draw_array_vertex_count") == new_count
            and push.get("maximum_vertex_index") == new_count - 1
            and push.get("all_vertex_references_in_bounds") is True,
            "rebuilt upper_deck draw range differs")


def _aligned16(value: int) -> int:
    return (value + 15) & ~15


def build_span(
    source: dict[str, Any], request: dict[str, Any], authorities: dict[str, Any]
) -> tuple[bytes, dict[str, Any]]:
    decoded = bytes(source["decoded"])
    _validate_source_decoded(decoded)
    source_span = bytes(source["span"])
    source_tail = bytes(source["tail"])
    retail_stream = bytes(source["retail_stream"])
    require(len(source_span) == base.CHUNK_SPAN_SIZE
            and len(source_tail) == base.OPAQUE_TAIL_SIZE
            and sha256(source_tail) == base.OPAQUE_TAIL_SHA256
            and source_span[-base.OPAQUE_TAIL_SIZE:] == source_tail,
            "source fixed span or opaque tail differs")
    require(len(retail_stream) == base.RETAIL_CONSUMED
            and sha256(retail_stream) == base.RETAIL_STREAM_SHA256,
            "source retail VC-LZ stream differs")
    new_count = request["new_count"]
    source_ids = request["source_ids"]
    mode = request["mode"]

    if mode == "identity_noop":
        require(new_count == SOURCE_VERTEX_COUNT
                and source_ids == list(range(SOURCE_VERTEX_COUNT)),
                "identity no-op request differs from retail order")
        padding = base.CHUNK_STORED_SIZE - len(retail_stream)
        alias = minimum_vc_lz_overlap_scratch(
            retail_stream, base.CHUNK_STORED_SIZE, base.DECODED_SIZE
        )
        scratch = _aligned16(max(padding, alias))
        require(padding == base.OPAQUE_TAIL_SIZE and scratch == base.SOURCE_SCRATCH,
                "identity no-op scratch derivation differs")
        edited = decoded
        rebuilt = source_span
        encoded = retail_stream
        gap = 0
    else:
        require(new_count in CHANGED_COUNTS and len(source_ids) == new_count,
                "changed request escaped the 4/8 subset boundary")
        edited_mutable = bytearray(decoded)
        for stream in STREAMS:
            start, end, stride = (
                stream["offset"], stream["end_offset"], stream["stride_bytes"]
            )
            source_stream = decoded[start:end]
            remapped = remap_stream_prefix(
                source_stream, stride, SOURCE_VERTEX_COUNT, source_ids
            )
            edited_mutable[start:end] = remapped
        struct.pack_into("<H", edited_mutable, SHAPE_VERTEX_COUNT_OFFSET, new_count)
        edited_mutable[DRAW_COUNT_BYTE_OFFSET] = new_count - 1
        edited = bytes(edited_mutable)

        require(struct.unpack_from("<H", edited, SHAPE_VERTEX_COUNT_OFFSET)[0] == new_count
                and edited[SHAPE_VERTEX_COUNT_OFFSET + 1] == decoded[SHAPE_VERTEX_COUNT_OFFSET + 1],
                "shape u16le count update differs")
        require(_draw_count(edited) == (0, new_count),
                "DRAW_ARRAYS start/count update differs")
        require(decoded[PUSH_OFFSET:DRAW_COUNT_BYTE_OFFSET]
                == edited[PUSH_OFFSET:DRAW_COUNT_BYTE_OFFSET]
                and decoded[DRAW_COUNT_BYTE_OFFSET + 1:PUSH_OFFSET + PUSH_SIZE]
                == edited[DRAW_COUNT_BYTE_OFFSET + 1:PUSH_OFFSET + PUSH_SIZE],
                "push edit escaped the DRAW_ARRAYS high count byte")
        authorized_ranges = [
            (SHAPE_VERTEX_COUNT_OFFSET, SHAPE_VERTEX_COUNT_OFFSET + 2),
            (DRAW_COUNT_BYTE_OFFSET, DRAW_COUNT_BYTE_OFFSET + 1),
            *[
                (stream["offset"], stream["offset"] + new_count * stream["stride_bytes"])
                for stream in STREAMS
            ],
        ]
        require(_ranges_complement(decoded, authorized_ranges)
                == _ranges_complement(edited, authorized_ranges),
                "decoded edit escaped the two count controls or destination prefixes")
        for destination, source_id in enumerate(source_ids):
            for stream in STREAMS:
                start, stride = stream["offset"], stream["stride_bytes"]
                destination_record = edited[
                    start + destination * stride:start + (destination + 1) * stride
                ]
                source_record = decoded[
                    start + source_id * stride:start + (source_id + 1) * stride
                ]
                require(destination_record == source_record,
                        "destination record differs from synchronized source record")
        _validate_edited_scene(edited, new_count)
        try:
            encoded, metrics = compress_vc_lz(
                edited, stream_tag=1, offset_bits=12,
                max_encoded_size=base.RETAIL_CONSUMED,
                verify_roundtrip=True,
            )
        except TxtrError as exc:
            raise UpperDeckSubsetPatchError(
                "source-subset replacement exceeds the retail VC-LZ consumed-stream cap"
            ) from exc
        decoded_back, info = decompress_vc_lz(encoded, base.DECODED_SIZE)
        require(decoded_back == edited and info.consumed_bytes == len(encoded),
                "writer-side full VC-LZ decode differs from the intended SCNE")
        gap = base.RETAIL_CONSUMED - len(encoded)
        padding = base.CHUNK_STORED_SIZE - len(encoded)
        alias = minimum_vc_lz_overlap_scratch(
            encoded, base.CHUNK_STORED_SIZE, base.DECODED_SIZE
        )
        scratch = _aligned16(max(padding, alias))
        observed_max = authorities["catalog"]["value"]["resource_contract"]["vc_lz"][
            "scratch_field_observed_corpus"
        ]["maximum"]
        require(type(observed_max) is int and scratch <= observed_max,
                "derived scratch exceeds the pinned retail SCNE observed maximum")
        header = bytearray(source_span[:HEADER.size])
        struct.pack_into("<I", header, 0x14, scratch)
        rebuilt = bytes(header) + encoded + bytes(gap) + source_tail
        require(len(rebuilt) == base.CHUNK_SPAN_SIZE
                and rebuilt[-base.OPAQUE_TAIL_SIZE:] == source_tail,
                "rebuilt fixed SCNE span or final opaque tail differs")
        del metrics

    authorized_ranges = [
        (SHAPE_VERTEX_COUNT_OFFSET, SHAPE_VERTEX_COUNT_OFFSET + 2),
        (DRAW_COUNT_BYTE_OFFSET, DRAW_COUNT_BYTE_OFFSET + 1),
        *[
            (stream["offset"], stream["offset"] + new_count * stream["stride_bytes"])
            for stream in STREAMS
        ],
    ]
    prefixes: list[dict[str, Any]] = []
    tails: list[dict[str, Any]] = []
    stream_changed_counts: list[int] = []
    for stream in STREAMS:
        prefix_start = stream["offset"]
        prefix_end = prefix_start + new_count * stream["stride_bytes"]
        physical_end = stream["end_offset"]
        before_prefix = decoded[prefix_start:prefix_end]
        after_prefix = edited[prefix_start:prefix_end]
        before_tail = decoded[prefix_end:physical_end]
        after_tail = edited[prefix_end:physical_end]
        changed = _changed_byte_count(before_prefix, after_prefix)
        stream_changed_counts.append(changed)
        require(before_tail == after_tail, f"stream {stream['stream_index']} physical tail changed")
        prefixes.append({
            "stream_index": stream["stream_index"],
            "span": [prefix_start, prefix_end],
            "source_sha256": sha256(before_prefix),
            "output_sha256": sha256(after_prefix),
            "changed_byte_count": changed,
        })
        tails.append({
            "stream_index": stream["stream_index"],
            "span": [prefix_end, physical_end],
            "source_sha256": sha256(before_tail),
            "output_sha256": sha256(after_tail),
            "bit_exact": True,
        })
    complement_before = _ranges_complement(decoded, authorized_ranges)
    complement_after = _ranges_complement(edited, authorized_ranges)
    require(complement_before == complement_after,
            "decoded authorized-range complement changed")
    count_changed = _changed_byte_count(
        decoded[SHAPE_VERTEX_COUNT_OFFSET:SHAPE_VERTEX_COUNT_OFFSET + 2],
        edited[SHAPE_VERTEX_COUNT_OFFSET:SHAPE_VERTEX_COUNT_OFFSET + 2],
    ) + int(decoded[DRAW_COUNT_BYTE_OFFSET] != edited[DRAW_COUNT_BYTE_OFFSET])
    total_changed = _changed_byte_count(decoded, edited)
    require(total_changed == count_changed + sum(stream_changed_counts),
            "changed-byte accounting does not close")
    if mode == "identity_noop":
        require(total_changed == 0 and rebuilt == source_span,
                "identity no-op did not return source bytes verbatim")
    elif mode == "count_only_prefix":
        require(stream_changed_counts == [0, 0] and count_changed == 2,
                "count-only prefix mode changed stream bytes or not both count bytes")
    else:
        require(mode == "source_subset_remap" and count_changed == 2
                and sum(stream_changed_counts) > 0,
                "source-subset remap did not produce its expected changed regions")
    return rebuilt, {
        "mode": mode,
        "new_count": new_count,
        "decoded_after_sha256": sha256(edited),
        "decoded_changed_byte_count": total_changed,
        "count_control_changed_byte_count": count_changed,
        "stream_changed_byte_counts": stream_changed_counts,
        "destination_prefixes": prefixes,
        "physical_tails": tails,
        "complement_before_sha256": sha256(complement_before),
        "complement_after_sha256": sha256(complement_after),
        "encoded_bytes": len(encoded),
        "encoded_sha256": sha256(encoded),
        "zero_gap_bytes": gap,
        "stored_padding_bytes": padding,
        "minimum_alias_scratch_bytes": alias,
        "scratch_after": scratch,
    }


def _hash_file_range(path: Path, offset: int, size: int) -> str:
    require(offset >= 0 and size >= 0, "file-range hash extent is invalid")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        remaining = size
        while remaining:
            block = stream.read(min(8 * 1024 * 1024, remaining))
            require(bool(block), "short file while hashing bounded range")
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def _outside_chunk_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        remaining = base.CHUNK_PACK_OFFSET
        while remaining:
            block = stream.read(min(8 * 1024 * 1024, remaining))
            require(bool(block), "short output before target resource")
            digest.update(block)
            remaining -= len(block)
        stream.seek(base.CHUNK_PACK_END)
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest(
    request: dict[str, Any], authorities: dict[str, Any],
    output_pack: Path, build: dict[str, Any], source_after_sha256: str,
) -> dict[str, Any]:
    output_sha256 = sha256_file(output_pack)
    outside_sha256 = _outside_chunk_hash(output_pack)
    require(outside_sha256 == base.OUTSIDE_CHUNK_SHA256,
            "copied volume changed outside the target resource span")
    output_outer_sha256 = _hash_file_range(
        output_pack, base.OUTER_PACK_OFFSET, base.OUTER_SIZE
    )
    new_count = build["new_count"]
    observed_max = authorities["catalog"]["value"]["resource_contract"]["vc_lz"][
        "scratch_field_observed_corpus"
    ]["maximum"]
    return {
        "schema": MANIFEST_SCHEMA,
        "mode": build["mode"],
        "authority": authorities["authority"],
        "request": request["summary"],
        "target": {
            "target_id": TARGET_ID,
            "scene_index": 2648,
            "scene_name": "stadium",
            "shape_index": SHAPE_INDEX,
            "shape_name": SHAPE_NAME,
            "source_vertex_count": SOURCE_VERTEX_COUNT,
            "output_vertex_count": new_count,
            "streams": [
                {
                    "stream_index": stream["stream_index"],
                    "physical_span": [stream["offset"], stream["end_offset"]],
                    "stride_bytes": stream["stride_bytes"],
                    "source_sha256": stream["source_sha256"],
                    "logical_prefix_bytes": new_count * stream["stride_bytes"],
                }
                for stream in STREAMS
            ],
            "count_controls": [
                {
                    "kind": "shape_vertex_count_u16le",
                    "decoded_offset": SHAPE_VERTEX_COUNT_OFFSET,
                    "source_count": SOURCE_VERTEX_COUNT,
                    "output_count": new_count,
                },
                {
                    "kind": "draw_arrays_high_count_byte",
                    "decoded_offset": DRAW_COUNT_BYTE_OFFSET,
                    "source_count": SOURCE_VERTEX_COUNT,
                    "output_count": new_count,
                },
            ],
        },
        "source": {
            "index": {
                "name": "0", "size_bytes": base.INDEX_SIZE,
                "sha256": base.INDEX_SHA256,
            },
            "volume": {
                "name": "9", "size_bytes": base.PACK_SIZE,
                "sha256_before": base.PACK_SHA256,
                "sha256_after": source_after_sha256,
                "modified": False,
            },
            "outer_entry": {
                "outer_index": base.OUTER_INDEX,
                "outer_id": "0xe4d6b0bc",
                "size_bytes": base.OUTER_SIZE,
                "pack_offset": base.OUTER_PACK_OFFSET,
                "source_sha256": base.OUTER_SHA256,
            },
            "resource": {
                "chunk_index": base.CHUNK_INDEX,
                "entry_offset": base.CHUNK_ENTRY_OFFSET,
                "pack_span": [base.CHUNK_PACK_OFFSET, base.CHUNK_PACK_END],
                "fixed_span_bytes": base.CHUNK_SPAN_SIZE,
                "source_span_sha256": base.CHUNK_SPAN_SHA256,
                "source_decoded_sha256": base.DECODED_SHA256,
            },
        },
        "edit": {
            "decoded_after_sha256": build["decoded_after_sha256"],
            "decoded_changed_byte_count": build["decoded_changed_byte_count"],
            "count_control_changed_byte_count": build["count_control_changed_byte_count"],
            "stream_changed_byte_counts": [
                {
                    "stream_index": stream["stream_index"],
                    "changed_byte_count": changed,
                }
                for stream, changed in zip(STREAMS, build["stream_changed_byte_counts"])
            ],
            "destination_prefixes": build["destination_prefixes"],
            "physical_tails": build["physical_tails"],
            "decoded_authorized_complement_source_sha256": build["complement_before_sha256"],
            "decoded_authorized_complement_output_sha256": build["complement_after_sha256"],
            "decoded_authorized_complement_bit_exact": True,
            "complete_records_copied_across_every_active_stream": True,
            "source_record_order_synchronized_across_streams": True,
            "source_vertex_ids_published": False,
        },
        "compression": {
            "codec": "VC-LZ",
            "stream_tag": 1,
            "offset_bits": 12,
            "retail_consumed_cap_bytes": base.RETAIL_CONSUMED,
            "rebuilt_consumed_bytes": build["encoded_bytes"],
            "rebuilt_stream_sha256": build["encoded_sha256"],
            "zero_gap_before_fixed_tail_bytes": build["zero_gap_bytes"],
            "total_stored_padding_bytes": build["stored_padding_bytes"],
            "minimum_alias_scratch_bytes": build["minimum_alias_scratch_bytes"],
            "scratch_before": base.SOURCE_SCRATCH,
            "scratch_after": build["scratch_after"],
            "retail_scne_observed_scratch_max": observed_max,
            "fixed_final_tail_bytes": base.OPAQUE_TAIL_SIZE,
            "fixed_final_tail_sha256": base.OPAQUE_TAIL_SHA256,
            "full_decode_exact": True,
            "identity_noop_returned_source_span_verbatim":
                build["mode"] == "identity_noop",
            "changed_path_recompressed": build["mode"] != "identity_noop",
        },
        "output": {
            "volume_name": "9",
            "volume_size_bytes": base.PACK_SIZE,
            "volume_sha256": output_sha256,
            "outer_entry_sha256": output_outer_sha256,
            "outside_target_resource_sha256": outside_sha256,
            "outside_target_resource_bit_exact": True,
            "fixed_resource_span_preserved": True,
            "directory_files": ["9", "manifest.json"],
            "manifest_contains_retail_records": False,
            "manifest_contains_source_vertex_ids": False,
        },
        "claims": {
            "offline_fixed_span_source_subset_writer_implemented": True,
            "runtime_visibility_proved": False,
            "original_xbox_hardware_proved": False,
            "bounds_or_culling_serializer_proved": False,
            "collision_or_lod_ownership_proved": False,
            "arbitrary_external_vertex_authoring_proved": False,
            "production_ready": False,
            "gui_exposed": False,
            "distribution_ready": False,
        },
    }


def _inode(path: Path) -> tuple[int, int]:
    info = path.lstat()
    return info.st_dev, info.st_ino


def _is_regular_inode(path: Path, expected: tuple[int, int]) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return (stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and (info.st_dev, info.st_ino) == expected)


def _unlink_owned_regular_or_refuse(
    path: Path, expected: tuple[int, int], label: str
) -> None:
    require(_is_regular_inode(path, expected),
            f"{label} inode changed before owned cleanup")
    path.unlink()


def _publish_staged_no_replace(
    reservation: Path,
    reservation_inode: tuple[int, int],
    staging: Path,
    staging_inode: tuple[int, int],
    known: dict[str, tuple[int, int]],
) -> None:
    require(_inode(reservation) == reservation_inode
            and _inode(staging) == staging_inode,
            "output reservation or staging inode changed")
    require(sorted(path.name for path in reservation.iterdir()) == [staging.name],
            "output reservation gained an unexpected raced artifact")
    require(sorted(path.name for path in staging.iterdir()) == ["9", "manifest.json"]
            and set(known) == {"9", "manifest.json"},
            "staging directory is not exclusive")
    for name in ("9", "manifest.json"):
        require(_is_regular_inode(staging / name, known[name]),
                f"staged {name} inode changed")
    try:
        for name in ("9", "manifest.json"):
            os.link(staging / name, reservation / name, follow_symlinks=False)
            require(_is_regular_inode(reservation / name, known[name]),
                    f"published {name} inode differs from staged artifact")
    except FileExistsError as exc:
        raise UpperDeckSubsetPatchError(
            "refusing to replace a destination artifact created during publication"
        ) from exc
    for name in ("9", "manifest.json"):
        _unlink_owned_regular_or_refuse(staging / name, known[name], f"staged {name}")
    require(_inode(staging) == staging_inode and not any(staging.iterdir()),
            "staging directory changed before cleanup")
    staging.rmdir()
    require(_inode(reservation) == reservation_inode
            and sorted(path.name for path in reservation.iterdir()) == ["9", "manifest.json"]
            and all(_is_regular_inode(reservation / name, known[name]) for name in known),
            "published output directory is not exclusive")


def _safe_cleanup_owned_reservation(
    reservation: Path,
    reservation_inode: tuple[int, int] | None,
    staging: Path | None,
    staging_inode: tuple[int, int] | None,
    known: dict[str, tuple[int, int]],
) -> None:
    if reservation_inode is None:
        return
    try:
        if _inode(reservation) != reservation_inode:
            return
    except FileNotFoundError:
        return

    def unlink_owned(path: Path, expected: tuple[int, int]) -> None:
        try:
            if _is_regular_inode(path, expected):
                path.unlink()
        except FileNotFoundError:
            pass

    for name, expected in known.items():
        unlink_owned(reservation / name, expected)
    if staging is not None:
        try:
            owned_staging = staging_inode is not None and _inode(staging) == staging_inode
        except FileNotFoundError:
            owned_staging = False
        if owned_staging:
            for name, expected in known.items():
                unlink_owned(staging / name, expected)
            try:
                if not any(staging.iterdir()):
                    staging.rmdir()
            except (FileNotFoundError, NotADirectoryError):
                pass
    try:
        if _inode(reservation) == reservation_inode and not any(reservation.iterdir()):
            reservation.rmdir()
    except FileNotFoundError:
        pass


def _copy_and_patch_owned_volume(
    source_pack: Path, output_pack: Path, rebuilt: bytes
) -> tuple[int, int]:
    """Copy and patch one exclusive-created inode without reopening its path."""
    require(len(rebuilt) == base.CHUNK_SPAN_SIZE,
            "rebuilt resource span length differs")
    with source_pack.open("rb") as source_stream, output_pack.open("x+b") as output_stream:
        source_info = os.fstat(source_stream.fileno())
        output_info = os.fstat(output_stream.fileno())
        owned = (output_info.st_dev, output_info.st_ino)
        require(owned != (source_info.st_dev, source_info.st_ino),
                "output inode aliases the retail source")
        require(_inode(output_pack) == owned,
                "staged volume pathname changed after exclusive creation")
        for block in iter(lambda: source_stream.read(8 * 1024 * 1024), b""):
            output_stream.write(block)
        output_stream.flush()
        require(os.fstat(output_stream.fileno()).st_size == base.PACK_SIZE,
                "copied volume size differs")
        output_stream.seek(base.CHUNK_PACK_OFFSET)
        output_stream.write(rebuilt)
        output_stream.flush()
        os.fsync(output_stream.fileno())
        require(os.fstat(output_stream.fileno()).st_size == base.PACK_SIZE,
                "patched volume size differs")
        require(_inode(output_pack) == owned,
                "staged volume pathname changed during copy/patch")
    return owned


def patch(
    index: Path,
    recipe_path: Path | None,
    identity_noop: bool,
    output_dir: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    boundary_path: Path = DEFAULT_BOUNDARY,
    recipe_schema_path: Path = DEFAULT_RECIPE_SCHEMA,
) -> dict[str, Any]:
    authorities = load_authorities(catalog_path, boundary_path, recipe_schema_path)
    request = load_request(recipe_path, identity_noop, authorities)
    output_dir = output_dir.expanduser()
    try:
        parent_info = output_dir.parent.lstat()
    except FileNotFoundError as exc:
        raise UpperDeckSubsetPatchError("output parent does not exist") from exc
    require(stat.S_ISDIR(parent_info.st_mode) and not stat.S_ISLNK(parent_info.st_mode),
            "output parent must be a real non-symlink directory")
    requested = output_dir.parent.resolve(strict=True) / output_dir.name
    source_index = regular(index, "NFL archive index")
    source_pack_candidate = regular(source_index.parent / "9", "NFL source volume 9")
    require(requested != source_pack_candidate.parent,
            "refusing to use the retail source directory as output")
    try:
        requested.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise UpperDeckSubsetPatchError(
            f"refusing to overwrite existing output directory: {output_dir}"
        ) from exc
    reservation_inode: tuple[int, int] | None = _inode(requested)
    staging: Path | None = None
    staging_inode: tuple[int, int] | None = None
    known: dict[str, tuple[int, int]] = {}
    try:
        try:
            source = base._validate_source(
                source_index, authorities["catalog"], authorities["row"]
            )
        except base.CatalogPositionPatchError as exc:
            raise UpperDeckSubsetPatchError(str(exc)) from exc
        rebuilt, build = build_span(source, request, authorities)
        source_pack = Path(source["pack"])
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=requested))
        staging_inode = _inode(staging)
        output_pack = staging / "9"
        known["9"] = _copy_and_patch_owned_volume(source_pack, output_pack, rebuilt)
        require(_is_regular_inode(output_pack, known["9"]),
                "staged volume inode changed before manifest construction")
        source_after_sha256 = sha256_file(source_pack)
        require(source_after_sha256 == base.PACK_SHA256,
                "retail source volume changed during copied-volume write")
        manifest = _manifest(
            request, authorities, output_pack, build, source_after_sha256
        )
        manifest_path = staging / "manifest.json"
        with manifest_path.open("xb") as stream:
            info = os.fstat(stream.fileno())
            known["manifest.json"] = (info.st_dev, info.st_ino)
            require(_inode(manifest_path) == known["manifest.json"],
                    "staged manifest pathname changed after exclusive creation")
            stream.write(canonical_json(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        _publish_staged_no_replace(
            requested, reservation_inode, staging, staging_inode, known
        )
        return manifest
    except Exception:
        _safe_cleanup_owned_reservation(
            requested, reservation_inode, staging, staging_inode, known
        )
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--recipe", type=Path)
    operation.add_argument("--identity-noop", action="store_true")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--recipe-schema", type=Path, default=DEFAULT_RECIPE_SCHEMA)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = patch(
        args.index, args.recipe, args.identity_noop, args.output_dir,
        args.catalog, args.boundary, args.recipe_schema,
    )
    print(
        "NFL_UPPER_DECK_SUBSET_PATCH_COMPLETE "
        f"mode={manifest['mode']} vertices={manifest['target']['output_vertex_count']} "
        f"output={args.output_dir / '9'} sha256={manifest['output']['volume_sha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError, UpperDeckSubsetPatchError, base.CatalogPositionPatchError,
        TxtrError, struct.error, KeyError, IndexError, TypeError,
    ) as exc:
        raise SystemExit(f"error: {exc}") from exc
