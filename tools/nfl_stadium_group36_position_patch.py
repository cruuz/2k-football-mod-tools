#!/usr/bin/env python3
"""Fail-closed same-count position writer for one NFL 2K5 stadium mesh.

The only writable payload is the four FLOAT3 positions of retail shape
``stadium/group36`` (outer 3280, chunk 5, shape 4).  The command copies volume
9, rebuilds the target VC-LZ stream inside its retail consumed-length bound,
preserves the final 16 opaque stored bytes, and refuses every relayout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any

from nfl_outer import parse_archive, read_entry_range
from nfl_scene_probe import ResourceRecord, decode_resource
from nfl_scne_inventory import parse_scene
from nfl_txtr import (
    HEADER,
    TxtrError,
    compress_vc_lz,
    decompress_vc_lz,
    minimum_vc_lz_overlap_scratch,
)


RECIPE_SCHEMA = "nfl2k5_static_position_recipe/v1"
PATCH_SCHEMA = "nfl2k5_static_position_patch/v1"
MAX_RECIPE_BYTES = 16 * 1024

INDEX_NAME = "0"
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
PACK_NAME = "9"
PACK_SIZE = 634_941_440
PACK_SHA256 = "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a"

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
MAX_SCRATCH = 0x40
CHUNK_SPAN_SHA256 = "0cd1977a6097851f9366d935098bdd9e97144f3ffce0f8690593c2623fbbd73a"
WRAPPER_SHA256 = "d4049cd35f3588259072ff9d05952c6bd830f6c1cd6181fc1d72b25b8cdc41ae"
DECODED_SHA256 = "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8"
RETAIL_CONSUMED = 908_864
RETAIL_STREAM_SHA256 = "beb71504d82a7634d73bf6603fb96d8d0ba33beb4fd0eaa870efd4007a8d3af8"
OPAQUE_TAIL_SIZE = 16
OPAQUE_TAIL_SHA256 = "cb57e42b9b8d9e1cba31e18c38dbc3347c8caa1361fcf7fe9cfad5b9f138fae4"

SCENE_INDEX = 2648
SCENE_NAME = "stadium"
SHAPE_INDEX = 4
SHAPE_NAME = "group36"
SHAPE_RECORD_OFFSET = 0x7A00
SHAPE_RECORD_SHA256 = "08a6f050e62929e1c4b1702f17c7bcd99a0d1c8ade97a2ba8d7edd8a92d25182"
POSITION_OFFSET = 0x13220
POSITION_SIZE = 48
POSITION_SHA256 = "65ab99a567a43ebe13c38f6921834896f56f609d954573bb3ae94d414562ab7d"
TRANSFORM_OFFSET = 0x13100
TRANSFORM_SHA256 = "216582fd48a3aa6474a98c129bc7fd66089c394a7eebdb5f05f85f240549510c"
SUBMESH_OFFSET = 0x13170
SUBMESH_SHA256 = "03103543e6fd877f5cbe5d9ff31bb9092f8d50a4db5d27981a7930e2ee7834be"
PUSH_OFFSET = 0x131F0
PUSH_SIZE = 28
PUSH_SHA256 = "f1fe835f194447d442a92f13548fde128425d3b8e839f16971a389a96968d3f2"
SECOND_STREAM_OFFSET = 0x13260
SECOND_STREAM_SIZE = 40
SECOND_STREAM_SHA256 = "a18f6c545d87d2fd892b9291e0b07e74152e8d6543d66ca4c09057a518b89847"
OUTSIDE_CHUNK_SHA256 = "8ef9522d0b4e4c5dfd9bb65c2e18d6ddf4c506ce5513f341701958666edc2bc6"

TARGET = {
    "chunk_index": CHUNK_INDEX,
    "decoded_sha256": DECODED_SHA256,
    "outer_id": "0xe4d6b0bc",
    "outer_index": OUTER_INDEX,
    "position_stream_sha256": POSITION_SHA256,
    "scene_index": SCENE_INDEX,
    "scene_name": SCENE_NAME,
    "shape_index": SHAPE_INDEX,
    "shape_name": SHAPE_NAME,
}
ENCODING = {
    "component_type": "float32_le",
    "components_per_vertex": 3,
    "coordinate_space": "raw_xbox",
    "stride_bytes": 12,
    "vertex_count": 4,
}


class PositionPatchError(ValueError):
    """An input or source violates the fixed target contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PositionPatchError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_outside_chunk(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        remaining = CHUNK_PACK_OFFSET
        while remaining:
            block = stream.read(min(8 * 1024 * 1024, remaining))
            require(bool(block), "short read before target chunk")
            digest.update(block)
            remaining -= len(block)
        stream.seek(CHUNK_PACK_END)
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular(path: Path, label: str) -> Path:
    path = path.expanduser()
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise PositionPatchError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _canonical_f32(value: object, label: str) -> float:
    require(type(value) in (int, float), f"{label} must be a JSON number")
    numeric = float(value)
    require(math.isfinite(numeric), f"{label} must be finite")
    try:
        packed = struct.pack("<f", numeric)
    except (OverflowError, struct.error) as exc:
        raise PositionPatchError(f"{label} is outside finite FLOAT3 range") from exc
    decoded = struct.unpack("<f", packed)[0]
    require(numeric == decoded,
            f"{label} must be exactly representable as IEEE-754 binary32")
    return decoded


def load_recipe(path: Path) -> dict[str, object]:
    recipe_path = regular(path, "static-position recipe")
    size = recipe_path.stat().st_size
    require(0 < size <= MAX_RECIPE_BYTES, "recipe size is outside 1..16384 bytes")
    payload = recipe_path.read_bytes()
    require(len(payload) == size, "recipe changed while reading")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                PositionPatchError(f"non-finite JSON constant {token} is forbidden")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PositionPatchError(f"recipe is not canonical UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict), "recipe root must be an object")
    require(payload == canonical_json(value), "recipe must use canonical sorted JSON formatting")
    require(set(value) == {"schema", "target", "encoding", "positions"},
            "recipe fields differ from v1")
    require(value.get("schema") == RECIPE_SCHEMA, "recipe schema differs from v1")
    require(value.get("target") == TARGET, "recipe target constants differ from group36")
    require(value.get("encoding") == ENCODING, "recipe encoding constants differ from FLOAT3 v1")
    rows = value.get("positions")
    require(isinstance(rows, list) and len(rows) == 4,
            "recipe positions must contain exactly four vertices")
    positions: list[tuple[float, float, float]] = []
    for vertex, row in enumerate(rows):
        require(isinstance(row, list) and len(row) == 3,
                f"recipe vertex {vertex} must contain exactly XYZ")
        positions.append(tuple(
            _canonical_f32(component, f"positions[{vertex}][{axis}]")
            for axis, component in enumerate(row)
        ))
    packed = b"".join(struct.pack("<3f", *row) for row in positions)
    require(len(packed) == POSITION_SIZE, "packed recipe position size changed")
    return {
        "path": recipe_path,
        "sha256": sha256(payload),
        "positions": positions,
        "packed": packed,
    }


def _validate_source(index_path: Path) -> dict[str, object]:
    index_path = regular(index_path, "NFL archive index")
    require(index_path.name == INDEX_NAME, "NFL archive index must be volume 0")
    require(index_path.stat().st_size == INDEX_SIZE, "source index size changed")
    require(sha256_file(index_path) == INDEX_SHA256, "source index SHA-256 changed")
    pack_path = regular(index_path.parent / PACK_NAME, "NFL source volume 9")
    require(pack_path.stat().st_size == PACK_SIZE, "source volume 9 size changed")
    require(sha256_file(pack_path) == PACK_SHA256, "source volume 9 SHA-256 changed")

    archive = parse_archive(index_path)
    entry = archive.entries[OUTER_INDEX]
    require(
        entry.name_id == OUTER_ID and entry.size == OUTER_SIZE
        and entry.offset_blocks == OUTER_OFFSET_BLOCKS
        and entry.virtual_offset == OUTER_VIRTUAL_OFFSET,
        "outer entry 3280 identity or extent changed",
    )
    require(
        len(entry.segments) == 1
        and entry.segments[0].pack_name == PACK_NAME
        and entry.segments[0].pack_offset == OUTER_PACK_OFFSET
        and entry.segments[0].size == OUTER_SIZE,
        "outer entry 3280 is not the pinned single span in volume 9",
    )
    entry_bytes = read_entry_range(archive, entry, 0, entry.size)
    require(sha256(entry_bytes) == OUTER_SHA256, "outer entry 3280 bytes changed")
    span = entry_bytes[CHUNK_ENTRY_OFFSET:CHUNK_ENTRY_OFFSET + CHUNK_SPAN_SIZE]
    require(len(span) == CHUNK_SPAN_SIZE and sha256(span) == CHUNK_SPAN_SHA256,
            "source group36 SCNE span changed")
    require(sha256(span[:HEADER.size]) == WRAPPER_SHA256, "source SCNE wrapper changed")
    fields = HEADER.unpack_from(span)
    require(fields == (
        b"SCNE", CHUNK_STORED_SIZE, SYSTEM_BYTES, VIDEO_BYTES,
        0xFEEDBEEF, RETAIL_SCRATCH, 0, 0,
    ), "source SCNE wrapper fields changed")
    record = ResourceRecord(
        outer_index=OUTER_INDEX, outer_id="0xe4d6b0bc", outer_size=OUTER_SIZE,
        chunk_index=CHUNK_INDEX, chunk_offset=CHUNK_ENTRY_OFFSET, kind="SCNE",
        stored_size=CHUNK_STORED_SIZE, word_08=SYSTEM_BYTES,
        word_0c=VIDEO_BYTES, word_10=0xFEEDBEEF, word_14=RETAIL_SCRATCH,
    )
    decoded, detail = decode_resource(span, record)
    require(len(decoded) == DECODED_SIZE and sha256(decoded) == DECODED_SHA256,
            "source decoded SCNE changed")
    lz = detail.get("lz")
    require(isinstance(lz, dict) and lz == {
        "declared_output_size": DECODED_SIZE,
        "stream_tag": 1,
        "offset_bits": 12,
        "length_bits": 4,
        "consumed_bytes": RETAIL_CONSUMED,
        "literal_count": 508197,
        "match_count": 158651,
    }, "source VC-LZ parse changed")
    retail_stream = span[HEADER.size:HEADER.size + RETAIL_CONSUMED]
    tail = span[HEADER.size + RETAIL_CONSUMED:]
    require(sha256(retail_stream) == RETAIL_STREAM_SHA256, "retail compressed stream changed")
    require(len(tail) == OPAQUE_TAIL_SIZE and sha256(tail) == OPAQUE_TAIL_SHA256,
            "retail final opaque tail changed")
    scene, _, _, _ = parse_scene(SCENE_INDEX, record, decoded, {})
    require(scene["scene_index"] == SCENE_INDEX and scene["name"] == SCENE_NAME,
            "target scene identity changed")
    shape = scene["shapes"][SHAPE_INDEX]
    require(
        shape["record_offset"] == SHAPE_RECORD_OFFSET
        and shape["name"] == SHAPE_NAME and shape["version"] == 2
        and shape["vertex_count"] == 4 and shape["morph_channel_count"] == 0
        and shape["transform_count"] == 1 and shape["submesh_count"] == 1,
        "target group36 shape contract changed",
    )
    require(sha256(decoded[SHAPE_RECORD_OFFSET:SHAPE_RECORD_OFFSET + 0x100]) ==
            SHAPE_RECORD_SHA256, "target shape record changed")
    position = next(item for item in shape["attribute_descriptors"] if item["register"] == 0)
    require(position == {
        "register": 0, "encoded": "0x00000032", "format_code": 0x32,
        "format_name": "FLOAT3", "component_count": 3, "byte_size": 12,
        "stream_index": 0, "byte_offset": 0,
    }, "target register-0 declaration changed")
    streams = shape["vertex_streams"]
    require(streams == [
        {"stream_index": 0, "stride": 12, "offset": POSITION_OFFSET,
         "end_offset": POSITION_OFFSET + POSITION_SIZE, "byte_size": POSITION_SIZE},
        {"stream_index": 1, "stride": 10, "offset": SECOND_STREAM_OFFSET,
         "end_offset": SECOND_STREAM_OFFSET + SECOND_STREAM_SIZE,
         "byte_size": SECOND_STREAM_SIZE},
    ], "target vertex streams changed")
    require(sha256(decoded[POSITION_OFFSET:POSITION_OFFSET + POSITION_SIZE]) == POSITION_SHA256,
            "source position stream changed")
    require(sha256(decoded[SECOND_STREAM_OFFSET:SECOND_STREAM_OFFSET + SECOND_STREAM_SIZE]) ==
            SECOND_STREAM_SHA256, "source secondary vertex stream changed")
    require(sha256(decoded[TRANSFORM_OFFSET:TRANSFORM_OFFSET + 0x70]) == TRANSFORM_SHA256,
            "source transform record changed")
    require(struct.unpack_from("<4f", decoded, TRANSFORM_OFFSET + 0x40) == (0.0, 0.0, 0.0, 1.0)
            and struct.unpack_from("<4f", decoded, TRANSFORM_OFFSET + 0x50) == (0.0, 0.0, 0.0, 1.0)
            and struct.unpack_from("<i", decoded, TRANSFORM_OFFSET + 0x64)[0] == -1,
            "group36 is no longer one zero root transform")
    selectors = [
        struct.unpack_from("<h", decoded, SECOND_STREAM_OFFSET + vertex * 10 + 8)[0]
        for vertex in range(4)
    ]
    require(selectors == [0, 0, 0, 0], "group36 SHORT1 selectors are no longer all zero")
    subs = [item for item in scene["submeshes"] if item["shape_index"] == SHAPE_INDEX]
    require(len(subs) == 1, "group36 submesh count changed")
    sub = subs[0]
    require(
        sub["record_offset"] == SUBMESH_OFFSET and sub["material_index"] == 3
        and sub["material_name"] == "cement01" and sub["submesh_index"] == 0
        and sub["primary_command_word_count"] == 7
        and sub["secondary_command_word_count"] == 0
        and sub["command_offset"] == PUSH_OFFSET
        and sub["primitive_mode_counts"] == {"END": 1, "QUADS": 1}
        and sub["maximum_vertex_index"] == 3,
        "group36 material or native QUADS topology changed",
    )
    require(sha256(decoded[SUBMESH_OFFSET:SUBMESH_OFFSET + 0x80]) == SUBMESH_SHA256,
            "group36 submesh record changed")
    require(sha256(decoded[PUSH_OFFSET:PUSH_OFFSET + PUSH_SIZE]) == PUSH_SHA256,
            "group36 push stream changed")
    return {
        "index": index_path,
        "pack": pack_path,
        "archive": archive,
        "entry": entry,
        "span": span,
        "decoded": decoded,
        "retail_stream": retail_stream,
        "tail": tail,
    }


def _aligned16(value: int) -> int:
    return (value + 15) & ~15


def build_span(source: dict[str, object], packed_positions: bytes) -> tuple[bytes, dict[str, object]]:
    decoded = bytes(source["decoded"])
    require(len(packed_positions) == POSITION_SIZE, "replacement position size changed")
    original_positions = decoded[POSITION_OFFSET:POSITION_OFFSET + POSITION_SIZE]
    edited = bytearray(decoded)
    edited[POSITION_OFFSET:POSITION_OFFSET + POSITION_SIZE] = packed_positions
    edited_bytes = bytes(edited)
    changed_offsets = [index for index, (a, b) in enumerate(zip(decoded, edited_bytes)) if a != b]
    require(all(POSITION_OFFSET <= offset < POSITION_OFFSET + POSITION_SIZE
                for offset in changed_offsets), "decoded edit escaped position stream")

    try:
        encoded, compression = compress_vc_lz(
            edited_bytes, stream_tag=1, offset_bits=12,
            max_encoded_size=RETAIL_CONSUMED, verify_roundtrip=True,
        )
    except TxtrError as exc:
        raise PositionPatchError(
            "replacement exceeds the retail 908864-byte consumed-stream cap; "
            "the final 16 opaque bytes must remain fixed"
        ) from exc
    decoded_back, info = decompress_vc_lz(encoded, DECODED_SIZE)
    require(decoded_back == edited_bytes and info.consumed_bytes == len(encoded),
            "independent writer-side VC-LZ decode did not reconstruct the edit")
    gap = RETAIL_CONSUMED - len(encoded)
    padding = CHUNK_STORED_SIZE - len(encoded)
    alias = minimum_vc_lz_overlap_scratch(encoded, CHUNK_STORED_SIZE, DECODED_SIZE)
    scratch = _aligned16(max(padding, alias))
    require(scratch <= MAX_SCRATCH,
            f"replacement needs scratch 0x{scratch:x}, above the 0x40 safety cap")
    source_span = bytes(source["span"])
    tail = bytes(source["tail"])
    header = bytearray(source_span[:HEADER.size])
    struct.pack_into("<I", header, 0x14, scratch)
    rebuilt = bytes(header) + encoded + bytes(gap) + tail
    require(len(rebuilt) == CHUNK_SPAN_SIZE, "rebuilt fixed span size changed")
    require(rebuilt[-OPAQUE_TAIL_SIZE:] == tail, "rebuilt final opaque tail changed")
    mode = "no_op" if packed_positions == original_positions else "patched"
    if mode == "no_op":
        require(encoded == source["retail_stream"], "no-op compressor did not reproduce retail bytes")
        require(gap == 0 and scratch == RETAIL_SCRATCH and rebuilt == source_span,
                "no-op span is not byte-identical")
    return rebuilt, {
        "mode": mode,
        "decoded": edited_bytes,
        "position_before_sha256": sha256(original_positions),
        "position_after_sha256": sha256(packed_positions),
        "decoded_after_sha256": sha256(edited_bytes),
        "decoded_changed_byte_count": len(changed_offsets),
        "encoded_sha256": sha256(encoded),
        "encoded_bytes": len(encoded),
        "zero_gap_bytes": gap,
        "padding_bytes": padding,
        "minimum_alias_scratch_bytes": alias,
        "scratch_after": scratch,
        "literal_count": compression.literal_count,
        "match_count": compression.match_count,
    }


def _manifest(
    recipe: dict[str, object], source: dict[str, object], output_pack: Path,
    build: dict[str, object], source_after_sha: str,
) -> dict[str, object]:
    output_sha = sha256_file(output_pack)
    outside_sha = sha256_outside_chunk(output_pack)
    require(outside_sha == OUTSIDE_CHUNK_SHA256, "output bytes outside target chunk changed")
    return {
        "schema": PATCH_SCHEMA,
        "mode": build["mode"],
        "recipe": {
            "schema": RECIPE_SCHEMA,
            "sha256": recipe["sha256"],
            "contains_only_authored_positions_and_const_metadata": True,
        },
        "target": TARGET,
        "encoding": ENCODING,
        "source": {
            "index": {"name": INDEX_NAME, "size": INDEX_SIZE, "sha256": INDEX_SHA256},
            "volume": {
                "name": PACK_NAME, "size": PACK_SIZE,
                "sha256_before": PACK_SHA256, "sha256_after": source_after_sha,
                "modified": False,
            },
            "outer_entry": {
                "table_index": OUTER_INDEX, "name_id": "0xe4d6b0bc",
                "size": OUTER_SIZE, "offset_blocks": OUTER_OFFSET_BLOCKS,
                "virtual_offset": OUTER_VIRTUAL_OFFSET,
                "pack_offset": OUTER_PACK_OFFSET, "sha256": OUTER_SHA256,
            },
            "resource": {
                "chunk_index": CHUNK_INDEX, "entry_offset": CHUNK_ENTRY_OFFSET,
                "pack_span": [CHUNK_PACK_OFFSET, CHUNK_PACK_END],
                "stored_size": CHUNK_STORED_SIZE, "system_bytes": SYSTEM_BYTES,
                "video_bytes": VIDEO_BYTES, "source_span_sha256": CHUNK_SPAN_SHA256,
                "source_decoded_sha256": DECODED_SHA256,
            },
        },
        "edit": {
            "decoded_position_span": [POSITION_OFFSET, POSITION_OFFSET + POSITION_SIZE],
            "position_before_sha256": build["position_before_sha256"],
            "position_after_sha256": build["position_after_sha256"],
            "decoded_after_sha256": build["decoded_after_sha256"],
            "decoded_changed_byte_count": build["decoded_changed_byte_count"],
            "every_decoded_byte_outside_position_span_bit_exact": True,
            "topology_transform_material_and_secondary_stream_bit_exact": True,
        },
        "compression": {
            "codec": "VC-LZ", "stream_tag": 1, "offset_bits": 12,
            "retail_consumed_bytes": RETAIL_CONSUMED,
            "rebuilt_consumed_bytes": build["encoded_bytes"],
            "rebuilt_stream_sha256": build["encoded_sha256"],
            "zero_gap_before_fixed_tail_bytes": build["zero_gap_bytes"],
            "total_stored_padding_bytes": build["padding_bytes"],
            "minimum_alias_scratch_bytes": build["minimum_alias_scratch_bytes"],
            "scratch_before": RETAIL_SCRATCH, "scratch_after": build["scratch_after"],
            "scratch_cap": MAX_SCRATCH,
            "fixed_opaque_tail_bytes": OPAQUE_TAIL_SIZE,
            "fixed_opaque_tail_sha256": OPAQUE_TAIL_SHA256,
            "independent_decode_matches_edited_bytes": True,
        },
        "output": {
            "volume_name": PACK_NAME, "volume_size": PACK_SIZE,
            "volume_sha256": output_sha,
            "outside_target_chunk_sha256": outside_sha,
            "outside_target_chunk_bit_exact": True,
            "wrapper_changed_only_scratch": build["scratch_after"] != RETAIL_SCRATCH,
            "directory_files": ["9", "manifest.json"],
            "exclusive_manifest_contains_positions": False,
            "exclusive_manifest_contains_replacement_bytes": False,
        },
        "claims": {
            "same_count_position_write_back": True,
            "changed_topology_write_back": False,
            "material_uv_skin_morph_or_transform_write_back": False,
            "xemu_runtime_visibility_proved": False,
            "original_xbox_runtime_visibility_proved": False,
            "production_ready": False,
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
    return (
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
        and (info.st_dev, info.st_ino) == expected
    )


def _unlink_owned_regular_or_refuse(
    path: Path, expected: tuple[int, int], label: str
) -> None:
    require(_is_regular_inode(path, expected),
            f"{label} inode changed before owned cleanup")
    path.unlink()


def _publish_staged_no_replace(
    reservation: Path, reservation_inode: tuple[int, int], staging: Path,
    staging_inode: tuple[int, int], known_inodes: dict[str, tuple[int, int]],
) -> None:
    """Publish two files using atomic link-if-absent operations.

    The destination directory itself was atomically reserved by this process.
    Hard-link publication is same-filesystem and fails if a raced destination
    name exists; it never replaces that name.
    """
    require(_inode(reservation) == reservation_inode,
            "output reservation inode changed before publication")
    require(_inode(staging) == staging_inode,
            "staging directory inode changed before publication")
    require(sorted(path.name for path in reservation.iterdir()) == [staging.name],
            "output reservation gained an unexpected raced artifact")
    staged_pack = staging / PACK_NAME
    staged_manifest = staging / "manifest.json"
    require(sorted(path.name for path in staging.iterdir()) == ["9", "manifest.json"],
            "staging directory is not exclusive")
    require(set(known_inodes) == {"9", "manifest.json"}
            and _is_regular_inode(staged_pack, known_inodes["9"])
            and _is_regular_inode(staged_manifest, known_inodes["manifest.json"]),
            "staged artifact inode changed before publication")
    try:
        os.link(staged_pack, reservation / PACK_NAME, follow_symlinks=False)
        require(_is_regular_inode(reservation / PACK_NAME, known_inodes["9"]),
                "published volume inode differs from staged file")
        os.link(staged_manifest, reservation / "manifest.json", follow_symlinks=False)
        require(_is_regular_inode(
            reservation / "manifest.json", known_inodes["manifest.json"]
        ), "published manifest inode differs from staged file")
    except FileExistsError as exc:
        raise PositionPatchError(
            "refusing to replace a destination artifact created during publication"
        ) from exc
    require(_inode(reservation) == reservation_inode,
            "output reservation inode changed during publication")
    require(_is_regular_inode(reservation / PACK_NAME, known_inodes["9"])
            and _is_regular_inode(
                reservation / "manifest.json", known_inodes["manifest.json"]
            ),
            "published artifact inode differs from staged file")
    _unlink_owned_regular_or_refuse(
        staged_pack, known_inodes["9"], "staged volume"
    )
    _unlink_owned_regular_or_refuse(
        staged_manifest, known_inodes["manifest.json"], "staged manifest"
    )
    require(_inode(staging) == staging_inode and not any(staging.iterdir()),
            "staging directory inode or contents changed before cleanup")
    staging.rmdir()
    require(_inode(reservation) == reservation_inode
            and sorted(path.name for path in reservation.iterdir()) == ["9", "manifest.json"]
            and _is_regular_inode(reservation / PACK_NAME, known_inodes["9"])
            and _is_regular_inode(
                reservation / "manifest.json", known_inodes["manifest.json"]
            ),
            "published output directory is not exclusive")


def _safe_cleanup_owned_reservation(
    reservation: Path,
    reservation_inode: tuple[int, int] | None,
    staging: Path | None,
    staging_inode: tuple[int, int] | None,
    known_inodes: dict[str, tuple[int, int]],
) -> None:
    """Remove only names whose inode was created by this process."""
    if reservation_inode is None:
        return
    try:
        if _inode(reservation) != reservation_inode:
            return
    except FileNotFoundError:
        return
    def unlink_owned_regular(path: Path, expected: tuple[int, int]) -> None:
        try:
            info = path.lstat()
            if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == expected:
                path.unlink()
        except FileNotFoundError:
            pass

    for name, expected in known_inodes.items():
        unlink_owned_regular(reservation / name, expected)
    if staging is not None:
        try:
            staging_owned = staging_inode is not None and _inode(staging) == staging_inode
        except FileNotFoundError:
            staging_owned = False
        if staging_owned:
            for name, expected in known_inodes.items():
                unlink_owned_regular(staging / name, expected)
        try:
            if (staging_owned and staging.parent == reservation
                    and _inode(staging) == staging_inode and not any(staging.iterdir())):
                staging.rmdir()
        except (FileNotFoundError, NotADirectoryError):
            pass
    try:
        if _inode(reservation) == reservation_inode and not any(reservation.iterdir()):
            reservation.rmdir()
    except FileNotFoundError:
        pass


def patch(index: Path, recipe_path: Path, output_dir: Path) -> dict[str, object]:
    recipe = load_recipe(recipe_path)
    output_dir = output_dir.expanduser()
    parent_info = output_dir.parent.lstat()
    require(stat.S_ISDIR(parent_info.st_mode) and not stat.S_ISLNK(parent_info.st_mode),
            "output parent must be a real non-symlink directory")
    parent = output_dir.parent.resolve(strict=True)
    requested = parent / output_dir.name
    index_candidate = regular(index, "NFL archive index")
    source_pack_candidate = regular(index_candidate.parent / PACK_NAME, "NFL source volume 9")
    require(requested != source_pack_candidate.parent,
            "refusing to use the retail source directory as output")
    try:
        requested.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise PositionPatchError(
            f"refusing to overwrite existing output directory: {output_dir}"
        ) from exc
    reservation_inode: tuple[int, int] | None = _inode(requested)
    staging: Path | None = None
    staging_inode: tuple[int, int] | None = None
    known: dict[str, tuple[int, int]] = {}
    try:
        source = _validate_source(index_candidate)
        source_pack = Path(source["pack"])
        rebuilt, build = build_span(source, bytes(recipe["packed"]))
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=requested))
        staging_inode = _inode(staging)
        output_pack = staging / PACK_NAME
        with source_pack.open("rb") as source_stream, output_pack.open("xb") as output_stream:
            output_stat = os.fstat(output_stream.fileno())
            known[PACK_NAME] = (output_stat.st_dev, output_stat.st_ino)
            require(_inode(output_pack) == known[PACK_NAME],
                    "staged volume pathname changed after exclusive creation")
            while block := source_stream.read(8 * 1024 * 1024):
                output_stream.write(block)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        with output_pack.open("r+b") as stream:
            stream.seek(CHUNK_PACK_OFFSET)
            stream.write(rebuilt)
            stream.flush()
            os.fsync(stream.fileno())
        require(output_pack.stat().st_size == PACK_SIZE, "output volume size changed")
        source_after = sha256_file(source_pack)
        require(source_after == PACK_SHA256, "retail source volume changed during write")
        manifest = _manifest(recipe, source, output_pack, build, source_after)
        manifest_path = staging / "manifest.json"
        with manifest_path.open("xb") as stream:
            manifest_stat = os.fstat(stream.fileno())
            known["manifest.json"] = (manifest_stat.st_dev, manifest_stat.st_ino)
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
    parser.add_argument("--index", required=True, type=Path,
                        help="retail vc_53450030 volume 0 index")
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="new directory receiving only volume 9 and manifest.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = patch(args.index, args.recipe, args.output_dir)
    print(
        "NFL_GROUP36_POSITION_PATCH_COMPLETE "
        f"mode={manifest['mode']} output={args.output_dir / PACK_NAME} "
        f"sha256={manifest['output']['volume_sha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, PositionPatchError, TxtrError, struct.error, KeyError, IndexError) as exc:
        raise SystemExit(f"error: {exc}") from exc
