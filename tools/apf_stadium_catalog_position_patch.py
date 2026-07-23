#!/usr/bin/env python3
"""Fail-closed catalog-backed APF 2K8 stadium POSITION0 writer.

This v2 writer dispatches only to the 77 structural-static targets in the
hashes-only checked catalog.  The catalog supplies the exact vertex count,
stream, stride, lane offset, declarations, index topology, and structural
spans.  A recipe may replace every FLOAT32x3_BE POSITION0 lane, in retail
stream order, but may not change count, topology, interleaves, attachment
data, any sibling part, the fixed outer allocation, or bytes outside outer14.

Runtime visibility, rigid attachment, hardware acceptance, and a production
external-mesh importer remain explicitly unproved.
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
import sys
from typing import Any

import apf_inner
import apf_outer
import apf_scene
import apf_stadium_static_position_patch as container


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "reports/assets/apf_stadium_static_position_target_catalog.json"
CATALOG_SCHEMA = "apf2k8_stadium_static_position_target_catalog/v1"
CATALOG_SIZE = 456_821
CATALOG_SHA256 = "e2b21ebf4d358358627d26b7d7ea3c6cf600ea3f9d1e139cb9caa8ff1748a424"
RECIPE_SCHEMA_PATH = ROOT / "reports/specs/apf2k8_scne_catalog_position_recipe.schema.json"
RECIPE_SCHEMA = "apf2k8_scne_catalog_position_recipe/v2"
RECIPE_SCHEMA_SIZE = 5_585
RECIPE_SCHEMA_SHA256 = "41fcf955c65d81bb5da2d229d6a2ffee692a9c5ae80eda1c0849911c90950277"
MANIFEST_SCHEMA = "apf2k8_scne_catalog_position_patch/v2"
MANIFEST_NAME = "apf2k8_scne_catalog_position_manifest.json"
OUTPUT_PACK_NAME = "1A"
MAX_RECIPE_BYTES = 1024 * 1024

SOURCE_PACKS = container.SOURCE_PACKS
OUTER_INDEX = container.OUTER_INDEX
OUTER_NAME_ID = container.OUTER_NAME_ID
OUTER_PACK_OFFSET = container.OUTER_PACK_OFFSET
OUTER_LENGTH = container.OUTER_LENGTH
OUTER_SHA256 = container.OUTER_SHA256
INNER_INDEX = container.INNER_INDEX
INNER_NAME = container.INNER_NAME
INNER_FILE_ID = container.INNER_FILE_ID
INNER_TYPE_HASH = container.INNER_TYPE_HASH
SYSTEM_LENGTH = container.SYSTEM_LENGTH
SYSTEM_SHA256 = container.SYSTEM_SHA256
VRAM_LENGTH = container.VRAM_LENGTH
VRAM_SHA256 = container.VRAM_SHA256
SOURCE_FILE_LENGTH = container.SOURCE_FILE_LENGTH
FOOTER_TOTAL = container.FOOTER_TOTAL
FOOTER_SHA256 = container.FOOTER_SHA256
SOURCE_TAIL_LENGTH = container.SOURCE_TAIL_LENGTH
SOURCE_PREFIX_SHA256 = container.SOURCE_PREFIX_SHA256
SOURCE_SUFFIX_SHA256 = container.SOURCE_SUFFIX_SHA256
POSITION_SIZE = 12

RECIPE_CONSTANTS = {
    "schema": RECIPE_SCHEMA,
    "operation": "replace_catalog_target_exact_same_count_position0",
    "catalog": {
        "schema": CATALOG_SCHEMA,
        "size_bytes": CATALOG_SIZE,
        "sha256": CATALOG_SHA256,
    },
    "game": {"title": "All-Pro Football 2K8", "platform": "Xbox 360"},
    "source_contract": {
        "index_pack": "0A",
        "physical_pack": "1A",
        "index_sha256": SOURCE_PACKS["0A"][1],
        "physical_pack_sha256": SOURCE_PACKS["1A"][1],
    },
    "coordinate_space": "serialized_scne_object_space",
    "vertex_order": "retail_stream_order",
    "position_type": {
        "shape": "FLOAT3",
        "component": "IEEE754_BINARY32",
        "serialized_byte_order": "big-endian",
    },
    "claim_flags": {
        "same_count_position_only": True,
        "changed_topology_proved": False,
        "rigid_attachment_proved": False,
        "material_or_uv_authoring_proved": False,
        "skin_authoring_proved": False,
        "emulator_runtime_visibility_proved": False,
        "xbox_360_hardware_proved": False,
        "production_mesh_importer_proved": False,
    },
}


class PatchError(ValueError):
    """The catalog, recipe, source fixture, or preservation proof failed."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=4, sort_keys=True) + "\n").encode("utf-8")


def _strict_json(path: Path, maximum: int, what: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if not 0 < len(raw) <= maximum:
        raise PatchError(f"{what} size is outside bounded range")

    def reject_constant(value: str) -> None:
        raise PatchError(f"{what} contains non-JSON numeric constant {value!r}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PatchError(f"{what} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PatchError(f"invalid {what} JSON: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise PatchError(f"{what} must be canonical sorted UTF-8 object JSON")
    return value, raw


def load_catalog() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    metadata = os.lstat(CATALOG_PATH)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise PatchError("checked target catalog must be a regular non-symlink file")
    if metadata.st_size != CATALOG_SIZE or sha256_file(CATALOG_PATH) != CATALOG_SHA256:
        raise PatchError("checked target catalog identity drift")
    catalog, _ = _strict_json(CATALOG_PATH, CATALOG_SIZE, "catalog")
    targets = catalog.get("additional_targets")
    if (
        catalog.get("schema") != CATALOG_SCHEMA
        or catalog.get("contains_retail_vertex_values") is not False
        or catalog.get("contains_replacement_bytes") is not False
        or not isinstance(targets, list)
        or len(targets) != 77
    ):
        raise PatchError("checked target catalog contract drift")
    by_id: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict) or not isinstance(target.get("candidate_id"), str):
            raise PatchError("catalog target is malformed")
        target_id = target["candidate_id"]
        if target_id in by_id:
            raise PatchError("catalog contains duplicate target ID")
        position = target.get("position0")
        if (
            target.get("classification") != "structural_static_same_count_position_candidate"
            or target.get("runtime_rigid_attachment_proved") is not False
            or target.get("runtime_visibility_proved") is not False
            or not isinstance(position, dict)
            or position.get("format_code") != "0x002a23b9"
            or position.get("format_name") != "float32x3"
            or position.get("serialized_byte_order") != "big-endian"
            or position.get("lane_bytes_per_vertex") != POSITION_SIZE
            or position.get("authorized_lane_bytes") != position.get("vertex_count", -1) * POSITION_SIZE
        ):
            raise PatchError(f"catalog target contract drift: {target_id}")
        by_id[target_id] = target
    return catalog, by_id


def load_recipe(path: Path) -> tuple[dict[str, Any], bytes, bytes, dict[str, Any]]:
    if RECIPE_SCHEMA_PATH.stat().st_size != RECIPE_SCHEMA_SIZE or sha256_file(RECIPE_SCHEMA_PATH) != RECIPE_SCHEMA_SHA256:
        raise PatchError("recipe schema identity drift")
    _, targets = load_catalog()
    recipe, raw = _strict_json(path, MAX_RECIPE_BYTES, "recipe")
    expected_keys = set(RECIPE_CONSTANTS) | {"target_id", "positions"}
    if set(recipe) != expected_keys:
        raise PatchError("recipe top-level key set differs")
    for key, expected in RECIPE_CONSTANTS.items():
        if recipe.get(key) != expected:
            raise PatchError(f"recipe constant-pinned field differs: {key}")
    target_id = recipe.get("target_id")
    if not isinstance(target_id, str) or target_id not in targets:
        raise PatchError("recipe target_id is not authorized by the pinned catalog")
    target = targets[target_id]
    vertex_count = int(target["position0"]["vertex_count"])
    positions = recipe.get("positions")
    if not isinstance(positions, list) or len(positions) != vertex_count:
        raise PatchError(f"recipe must contain exactly {vertex_count} positions for {target_id}")
    encoded = bytearray()
    for vertex, position in enumerate(positions):
        if not isinstance(position, list) or len(position) != 3:
            raise PatchError(f"position {vertex} is not FLOAT3")
        values: list[float] = []
        for component, value in enumerate(position):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise PatchError(f"position {vertex}/{component} is not finite numeric data")
            values.append(float(value))
        try:
            packed = struct.pack(">3f", *values)
        except (OverflowError, struct.error) as exc:
            raise PatchError(f"position {vertex} is outside FLOAT32 range") from exc
        if struct.unpack(">3f", packed) != tuple(values):
            raise PatchError(f"position {vertex} is not exactly representable as FLOAT32")
        encoded.extend(packed)
    return recipe, raw, bytes(encoded), target


def _target_layout(target: dict[str, Any]) -> tuple[int, int, int, int]:
    position = target["position0"]
    return (
        int(position["vertex_count"]),
        int(position["stream_start"]),
        int(position["stream_stride"]),
        int(position["byte_offset"]),
    )


def _position_payload(system: bytes, target: dict[str, Any]) -> bytes:
    count, start, stride, lane_offset = _target_layout(target)
    return b"".join(
        system[start + vertex * stride + lane_offset : start + vertex * stride + lane_offset + POSITION_SIZE]
        for vertex in range(count)
    )


def _non_position_system_hash(system: bytes, target: dict[str, Any]) -> str:
    count, start, stride, lane_offset = _target_layout(target)
    digest = hashlib.sha256()
    cursor = 0
    for vertex in range(count):
        lane = start + vertex * stride + lane_offset
        digest.update(system[cursor:lane])
        cursor = lane + POSITION_SIZE
    digest.update(system[cursor:])
    return digest.hexdigest()


def _stream_complement_hash(system: bytes, target: dict[str, Any]) -> str:
    count, start, stride, lane_offset = _target_layout(target)
    digest = hashlib.sha256()
    for vertex in range(count):
        record = start + vertex * stride
        digest.update(system[record : record + lane_offset])
        digest.update(system[record + lane_offset + POSITION_SIZE : record + stride])
    return digest.hexdigest()


def _structural_spans(target: dict[str, Any]) -> dict[str, tuple[int, int, str]]:
    names = {
        "node_record": target["node"]["record"],
        "matrix_slot": target["matrix_slot_by_serialized_node_ordinal"],
        "hierarchy": target["hierarchy"],
        "draw_records": target["draw_records"],
        "index_topology": target["index_topology"],
        "declarations": target["declarations"],
        "mesh_descriptor_and_stream_records": target["mesh_descriptor_and_stream_records"],
    }
    return {
        name: (int(value["offset"]), int(value["length"]), str(value["sha256"]))
        for name, value in names.items()
    }


def _validate_source_target(system: bytes, target: dict[str, Any]) -> None:
    if len(system) != SYSTEM_LENGTH or sha256_bytes(system) != SYSTEM_SHA256:
        raise PatchError("retail stadium DRAM identity drift")
    target_id = target["candidate_id"]
    node_index = int(target["node"]["index"])
    scene = apf_scene.parse_scene_system_part(
        system, outer_index=OUTER_INDEX, inner_index=INNER_INDEX, capture_geometry=True
    )
    if scene["root_name"] != INNER_NAME or scene["scene_node_count"] != 89 or scene["matrix_count"] != 89:
        raise PatchError("stadium SCNE envelope drift")
    node = scene["nodes"][node_index]
    mesh = node["meshes"][0] if len(node["meshes"]) == 1 else None
    position = target["position0"]
    expected_semantics = [item["indexed_semantic"] for item in target["declarations"]["items"]]
    actual_semantics = [item["indexed_semantic"] for item in node["vertex_declarations"]]
    if (
        node["index"] != node_index
        or node["name"] != target["node"]["name"]
        or node["name_crc32"] != target["node"]["name_crc32"]
        or node["mesh_descriptor_count"] != 1
        or mesh is None
        or mesh["vertex_count"] != position["vertex_count"]
        or mesh["stream_count"] != target["mesh_descriptor_and_stream_records"]["stream_count"]
        or mesh["primitive_type"] != target["index_topology"]["primitive_code"]
        or node["index_component_bits"] != target["index_topology"]["component_bits"]
        or node["index_count"] != target["index_topology"]["index_count"]
        or actual_semantics != expected_semantics
        or any(value and value.startswith(("BLENDINDICES", "BLENDWEIGHT")) for value in actual_semantics)
    ):
        raise PatchError(f"catalog target structural parse differs: {target_id}")
    declaration = next((item for item in node["vertex_declarations"] if item["indexed_semantic"] == "POSITION0"), None)
    stream_index = int(position["stream_index"])
    stream = mesh["streams"][stream_index]
    if (
        declaration is None
        or declaration["format_code"] != position["format_code"]
        or declaration["stream_index"] != stream_index
        or declaration["byte_offset"] != position["byte_offset"]
        or stream["start"] != position["stream_start"]
        or stream["stride"] != position["stream_stride"]
        or stream["byte_length"] != position["vertex_count"] * position["stream_stride"]
        or stream["sha256"] != target["streams"][stream_index]["payload"]["sha256"]
        or sha256_bytes(_position_payload(system, target)) != position["retail_lane_sha256"]
    ):
        raise PatchError(f"catalog target POSITION0 parse differs: {target_id}")
    for label, (offset, length, expected_hash) in _structural_spans(target).items():
        if offset < 0 or offset + length > len(system) or sha256_bytes(system[offset : offset + length]) != expected_hash:
            raise PatchError(f"catalog target structural span drift: {label}")


def _part_hashes(record: apf_inner.IFFRecord, blocks: list[bytes]) -> dict[tuple[int, int], str]:
    return {
        (file.index, part_index): sha256_bytes(
            blocks[part.block_index][part.offset : part.offset + part.length]
        )
        for file in record.files
        for part_index, part in enumerate(file.parts)
    }


def copy_claims() -> dict[str, bool]:
    return {
        "offline_structural_write_back_proved": True,
        "catalog_backed_dispatcher_implemented": True,
        "same_count_position_only": True,
        "changed_topology_proved": False,
        "rigid_attachment_proved": False,
        "material_or_uv_authoring_proved": False,
        "skin_authoring_proved": False,
        "emulator_runtime_visibility_proved": False,
        "xbox_360_hardware_proved": False,
        "production_mesh_importer_proved": False,
    }


def _validate_stored0_capacity(stored_length: int, catalog: dict[str, Any]) -> None:
    envelope = catalog.get("container", {}).get("h7a_rebuild_envelope", {})
    maximum = envelope.get("maximum_stored_block0_bytes")
    if isinstance(stored_length, bool) or not isinstance(stored_length, int) or stored_length < 20:
        raise PatchError("rebuilt H7A block0 length is invalid")
    if not isinstance(maximum, int) or maximum != 3_301_108:
        raise PatchError("catalog H7A fixed-allocation maximum drift")
    if stored_length > maximum:
        raise PatchError("rebuilt H7A block0 exceeds catalog fixed-allocation maximum")


def build_patch(game_dir: Path, recipe_path: Path) -> tuple[bytes, dict[str, Any]]:
    recipe, recipe_raw, packed_positions, target = load_recipe(recipe_path)
    _, entry = container._validate_archive(game_dir)
    with apf_inner.ArchiveReader(apf_outer.parse_archive(game_dir / "0A")) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        original_blocks = [apf_inner.decode_block(reader, record, index, 1 << 30) for index in range(record.block_count)]
        original_stored = [reader.read(entry, block.start_offset, block.stored_length) for block in record.blocks]
    if sha256_bytes(original_entry) != OUTER_SHA256:
        raise PatchError("retail outer14 identity drift")
    if record.header_size != 292 or record.file_length != SOURCE_FILE_LENGTH or record.block_count != 2 or record.file_count != 9:
        raise PatchError("retail IFF header identity drift")
    inner = record.files[INNER_INDEX]
    if (
        inner.name != INNER_NAME
        or inner.file_id != INNER_FILE_ID
        or inner.type_hash != INNER_TYPE_HASH
        or inner.parts != (
            apf_inner.FilePart(0, 0, SYSTEM_LENGTH),
            apf_inner.FilePart(1, 0, VRAM_LENGTH),
        )
    ):
        raise PatchError("retail stadium part ownership drift")
    if sha256_bytes(original_blocks[1][:VRAM_LENGTH]) != VRAM_SHA256:
        raise PatchError("retail stadium VRAM identity drift")
    source_system = original_blocks[0][:SYSTEM_LENGTH]
    _validate_source_target(source_system, target)

    count, start, stride, lane_offset = _target_layout(target)
    source_positions = _position_payload(source_system, target)
    mode = "no_op" if source_positions == packed_positions else "changed"
    before_parts = _part_hashes(record, original_blocks)
    if mode == "no_op":
        rebuilt_entry = original_entry
        rebuilt_blocks = original_blocks
        new_stored = original_stored
        new_file_length = record.file_length
        h7a_invoked = False
    else:
        new_block0 = bytearray(original_blocks[0])
        for vertex in range(count):
            destination = start + vertex * stride + lane_offset
            source = vertex * POSITION_SIZE
            new_block0[destination : destination + POSITION_SIZE] = packed_positions[source : source + POSITION_SIZE]
        if _non_position_system_hash(bytes(new_block0[:SYSTEM_LENGTH]), target) != _non_position_system_hash(source_system, target):
            raise PatchError("SCNE bytes outside catalog-authorized POSITION0 lanes changed")
        rebuilt_entry, new_stored, new_file_length = container._rebuild_entry(
            original_entry, record, original_blocks, original_stored, bytes(new_block0)
        )
        _validate_stored0_capacity(len(new_stored[0]), load_catalog()[0])
        memory = container.BytesReader(rebuilt_entry)
        rebuilt_record = apf_inner.parse_iff(memory, entry)
        rebuilt_blocks = [apf_inner.decode_block(memory, rebuilt_record, index, 1 << 30) for index in range(rebuilt_record.block_count)]
        if rebuilt_blocks != [bytes(new_block0), original_blocks[1]]:
            raise PatchError("rebuilt IFF does not decode to intended blocks")
        record = rebuilt_record
        h7a_invoked = True

    output_system = rebuilt_blocks[0][:SYSTEM_LENGTH]
    if _position_payload(output_system, target) != packed_positions:
        raise PatchError("decoded output positions differ from recipe")
    if _stream_complement_hash(output_system, target) != _stream_complement_hash(source_system, target):
        raise PatchError("decoded output target stream interleaves changed")
    if _non_position_system_hash(output_system, target) != _non_position_system_hash(source_system, target):
        raise PatchError("decoded output SCNE non-position bytes changed")
    for label, (offset, length, expected_hash) in _structural_spans(target).items():
        if sha256_bytes(output_system[offset : offset + length]) != expected_hash:
            raise PatchError(f"decoded output structural span changed: {label}")

    after_parts = _part_hashes(record, rebuilt_blocks)
    changed_parts = sorted(key for key in before_parts if before_parts[key] != after_parts[key])
    if changed_parts != ([] if mode == "no_op" else [(INNER_INDEX, 0)]) or len(before_parts) != 13:
        raise PatchError(f"inner part preservation failed: {changed_parts}")
    footer = rebuilt_entry[new_file_length : new_file_length + FOOTER_TOTAL]
    tail = rebuilt_entry[new_file_length + FOOTER_TOTAL :]
    if sha256_bytes(footer) != FOOTER_SHA256 or any(tail) or new_stored[1] != original_stored[1]:
        raise PatchError("stored block1/footer/fixed-allocation tail preservation failed")

    source_header = bytearray(original_entry[: record.header_size])
    output_header = bytearray(rebuilt_entry[: record.header_size])
    for offset in set(range(0x08, 0x0C)) | set(range(0x38, 0x3C)) | set(range(0x54, 0x58)):
        source_header[offset] = output_header[offset] = 0
    if source_header != output_header:
        raise PatchError("IFF header differs outside mechanical length/start fields")

    changed_offsets = [
        index for index, (before, after) in enumerate(zip(original_blocks[0], rebuilt_blocks[0])) if before != after
    ]
    allowed_offsets = {
        start + vertex * stride + lane_offset + byte
        for vertex in range(count)
        for byte in range(POSITION_SIZE)
    }
    if not set(changed_offsets).issubset(allowed_offsets):
        raise PatchError("changed decoded block0 byte escapes catalog-authorized POSITION0 lanes")

    structural = {label: digest for label, (_, _, digest) in _structural_spans(target).items()}
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "mode": mode,
        "catalog": {
            "schema": CATALOG_SCHEMA,
            "size_bytes": CATALOG_SIZE,
            "sha256": CATALOG_SHA256,
            "authorized_target_count": 77,
        },
        "recipe": {
            "schema": recipe["schema"],
            "sha256": sha256_bytes(recipe_raw),
            "authored_position_count": count,
            "coordinate_space": recipe["coordinate_space"],
            "vertex_order": recipe["vertex_order"],
            "position_type": recipe["position_type"],
        },
        "source": {
            "game": "All-Pro Football 2K8 Xbox 360 USA retail",
            "packs": [
                {"name": name, "size_bytes": size, "sha256": digest}
                for name, (size, digest) in SOURCE_PACKS.items()
            ],
            "outer_entry_sha256": OUTER_SHA256,
            "stadium_dram_sha256": SYSTEM_SHA256,
            "stadium_vram_sha256": VRAM_SHA256,
            "position_payload_sha256": sha256_bytes(source_positions),
        },
        "target": {
            "target_id": target["candidate_id"],
            "outer_table_index": OUTER_INDEX,
            "physical_pack": OUTPUT_PACK_NAME,
            "fixed_outer_allocation_bytes": OUTER_LENGTH,
            "inner_file_index": INNER_INDEX,
            "inner_name": INNER_NAME,
            "node_index": target["node"]["index"],
            "node_name": target["node"]["name"],
            "vertex_count": count,
            "stream_index": target["position0"]["stream_index"],
            "stream_start": start,
            "stream_stride_bytes": stride,
            "position_byte_offset": lane_offset,
            "position_lane_bytes_per_vertex": POSITION_SIZE,
            "approved_position_lane_bytes": count * POSITION_SIZE,
            "position_format": "FLOAT32x3_BE",
        },
        "result": {
            "output_directory_contract": [OUTPUT_PACK_NAME, MANIFEST_NAME],
            "output_pack_name": OUTPUT_PACK_NAME,
            "output_pack_size_bytes": SOURCE_PACKS["1A"][0],
            "output_pack_sha256": None,
            "outer_entry_sha256": sha256_bytes(rebuilt_entry),
            "stadium_dram_sha256": sha256_bytes(output_system),
            "stadium_vram_sha256": sha256_bytes(rebuilt_blocks[1][:VRAM_LENGTH]),
            "position_payload_sha256": sha256_bytes(packed_positions),
            "changed_decoded_block0_byte_count": len(changed_offsets),
            "changed_inner_parts": [
                {"file_index": file_index, "part_index": part_index}
                for file_index, part_index in changed_parts
            ],
            "h7a_block0_recompressed": h7a_invoked,
            "h7a_block0_shift": 12,
            "block0_stored_length_before": len(original_stored[0]),
            "block0_stored_length_after": len(new_stored[0]),
            "block1_stored_sha256": sha256_bytes(new_stored[1]),
            "file_length_before": SOURCE_FILE_LENGTH,
            "file_length_after": new_file_length,
            "allocation_slack_after_bytes": len(tail),
        },
        "preservation": {
            "target_stream_non_position_sha256": _stream_complement_hash(output_system, target),
            "scne_non_position_sha256": _non_position_system_hash(output_system, target),
            "structural_spans": structural,
            "stadium_vram_exact": True,
            "sibling_part_count": 11,
            "non_target_part_count": 12,
            "all_non_target_parts_exact": True,
            "block1_stored_exact": True,
            "footer_sha256": sha256_bytes(footer),
            "footer_exact": True,
            "iff_header_complement_exact": True,
            "file_descriptor_table_exact": True,
            "outer_length_exact": len(rebuilt_entry) == OUTER_LENGTH,
            "outer_tail_zero_and_bounded": True,
            "source_files_rechecked_after_write": False,
            "output_pack_prefix_sha256": None,
            "output_pack_suffix_sha256": None,
        },
        "claims": copy_claims(),
        "contains_replacement_bytes": False,
    }
    return rebuilt_entry, manifest


def write_output(game_dir: Path, recipe_path: Path, output_dir: Path) -> dict[str, Any]:
    raw_game_dir = Path(os.path.normpath((Path.cwd() / game_dir).expanduser() if not game_dir.expanduser().is_absolute() else game_dir.expanduser()))
    game_metadata = os.lstat(raw_game_dir)
    if stat.S_ISLNK(game_metadata.st_mode) or not stat.S_ISDIR(game_metadata.st_mode):
        raise PatchError("source game directory must be a real non-symlink directory")
    game_dir = raw_game_dir.resolve(strict=True)
    if game_dir != raw_game_dir.absolute():
        raise PatchError("source game directory path contains a symlink")
    raw_recipe = Path(os.path.normpath((Path.cwd() / recipe_path).expanduser() if not recipe_path.expanduser().is_absolute() else recipe_path.expanduser()))
    recipe_metadata = os.lstat(raw_recipe)
    if stat.S_ISLNK(recipe_metadata.st_mode) or not stat.S_ISREG(recipe_metadata.st_mode) or recipe_metadata.st_size > MAX_RECIPE_BYTES:
        raise PatchError("recipe must be a bounded regular non-symlink file")
    recipe_path = raw_recipe.resolve(strict=True)
    if recipe_path != raw_recipe.absolute():
        raise PatchError("recipe path contains a symlink")
    requested_output = Path(os.path.normpath((Path.cwd() / output_dir).expanduser() if not output_dir.expanduser().is_absolute() else output_dir.expanduser()))
    parent = requested_output.parent
    parent_metadata = os.lstat(parent)
    if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(parent_metadata.st_mode) or parent.resolve(strict=True) != parent.absolute():
        raise PatchError("output parent must be a real non-symlink directory")
    output_dir = parent.resolve(strict=True) / requested_output.name
    try:
        output_dir.relative_to(game_dir)
    except ValueError:
        pass
    else:
        raise PatchError("output directory must not be inside the source game directory")
    if os.path.lexists(output_dir):
        raise PatchError("refusing existing output directory")

    source_before, source_inodes = container._source_file_identities(game_dir)
    rebuilt_entry, manifest = build_patch(game_dir, recipe_path)
    os.mkdir(output_dir, 0o755)
    created = os.lstat(output_dir)
    directory_identity = (created.st_dev, created.st_ino)
    directory_fd = os.open(output_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    owned: dict[str, tuple[int, int]] = {}
    try:
        opened = os.fstat(directory_fd)
        if (opened.st_dev, opened.st_ino) != directory_identity or not container._directory_path_matches(output_dir, directory_identity):
            raise PatchError("reserved output directory pathname changed during open")
        output_fd, output_identity = container._copy_new_at(
            game_dir / OUTPUT_PACK_NAME,
            directory_fd,
            OUTPUT_PACK_NAME,
            source_inodes["1A"],
            SOURCE_PACKS["1A"][1],
        )
        owned[OUTPUT_PACK_NAME] = output_identity
        try:
            written = 0
            while written < len(rebuilt_entry):
                count = os.pwrite(output_fd, rebuilt_entry[written:], OUTER_PACK_OFFSET + written)
                if count <= 0:
                    raise PatchError("short outer-entry write")
                written += count
            os.fsync(output_fd)
            if os.fstat(output_fd).st_size != SOURCE_PACKS["1A"][0]:
                raise PatchError("output 1A length changed")
            manifest["result"]["output_pack_sha256"] = container.sha256_fd(output_fd)
            manifest["preservation"]["output_pack_prefix_sha256"] = container.sha256_fd_range(output_fd, 0, OUTER_PACK_OFFSET)
            suffix_offset = OUTER_PACK_OFFSET + OUTER_LENGTH
            manifest["preservation"]["output_pack_suffix_sha256"] = container.sha256_fd_range(
                output_fd, suffix_offset, os.fstat(output_fd).st_size - suffix_offset
            )
            if (
                manifest["preservation"]["output_pack_prefix_sha256"] != SOURCE_PREFIX_SHA256
                or manifest["preservation"]["output_pack_suffix_sha256"] != SOURCE_SUFFIX_SHA256
            ):
                raise PatchError("output 1A complement outside outer14 differs")
            if manifest["mode"] == "no_op" and manifest["result"]["output_pack_sha256"] != SOURCE_PACKS["1A"][1]:
                raise PatchError("no-op output 1A is not byte-identical")
        finally:
            os.close(output_fd)
        source_after, source_after_inodes = container._source_file_identities(game_dir)
        if source_after != source_before or source_after_inodes != source_inodes:
            raise PatchError("source pack identity changed during write")
        manifest["preservation"]["source_files_rechecked_after_write"] = True
        owned[MANIFEST_NAME] = container._write_manifest_new_at(directory_fd, MANIFEST_NAME, manifest)
        if sorted(os.listdir(directory_fd)) != sorted(owned):
            raise PatchError("output directory contains an unexpected artifact")
        if not all(container._path_matches_at(directory_fd, name, identity) for name, identity in owned.items()):
            raise PatchError("published output child identity changed")
        if not container._directory_path_matches(output_dir, directory_identity):
            raise PatchError("published output directory pathname changed")
        os.close(directory_fd)
        return manifest
    except Exception:
        container._safe_cleanup(output_dir, directory_fd, directory_identity, owned)
        os.close(directory_fd)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = write_output(args.game_dir, args.recipe, args.output_dir)
        print(
            "APF_SCNE_CATALOG_POSITION_PATCH_PASS "
            f"mode={manifest['mode']} target={manifest['target']['target_id']} "
            f"vertices={manifest['target']['vertex_count']} copied_pack=1A "
            f"outer_sha256={manifest['result']['outer_entry_sha256']} "
            f"output_pack_sha256={manifest['result']['output_pack_sha256']} "
            "runtime=false hardware=false production=false"
        )
        return 0
    except (PatchError, container.PatchError, apf_outer.FormatError, apf_inner.FormatError, apf_scene.SceneError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
