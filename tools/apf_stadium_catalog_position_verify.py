#!/usr/bin/env python3
"""Independent verifier for the APF catalog-backed POSITION0 writer.

This verifier imports no writer.  It uses the pre-existing independent
outer/IFF/H7A byte parser, then separately loads the pinned hashes-only target
catalog, re-derives the selected SCNE node/stream/lane, checks every changed
decoded byte, and reconstructs every manifest field from source, recipe, and
output bytes.
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

import apf_stadium_static_position_verify as archive


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
VERIFY_SCHEMA = "apf2k8_scne_catalog_position_verification/v2"
MANIFEST_NAME = "apf2k8_scne_catalog_position_manifest.json"
MAX_RECIPE_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024

VerifyError = archive.VerifyError
SOURCE_PACKS = archive.SOURCE_PACKS
OUTER_INDEX = archive.OUTER_INDEX
OUTER_NAME_ID = archive.OUTER_NAME_ID
OUTER_PACK_OFFSET = archive.OUTER_PACK_OFFSET
OUTER_LENGTH = archive.OUTER_LENGTH
OUTER_SHA256 = archive.OUTER_SHA256
INNER_INDEX = archive.INNER_INDEX
INNER_FILE_ID = archive.INNER_FILE_ID
INNER_TYPE_HASH = archive.INNER_TYPE_HASH
SYSTEM_LENGTH = archive.SYSTEM_LENGTH
SYSTEM_SHA256 = archive.SYSTEM_SHA256
VRAM_LENGTH = archive.VRAM_LENGTH
VRAM_SHA256 = archive.VRAM_SHA256
SOURCE_FILE_LENGTH = archive.SOURCE_FILE_LENGTH
SOURCE_FOOTER_TOTAL = archive.SOURCE_FOOTER_TOTAL
SOURCE_FOOTER_SHA = archive.SOURCE_FOOTER_SHA
SOURCE_TAIL_LENGTH = archive.SOURCE_TAIL_LENGTH
BLOCK1_STORED_SHA = archive.BLOCK1_STORED_SHA
SOURCE_PREFIX_SHA256 = archive.SOURCE_PREFIX_SHA256
SOURCE_SUFFIX_SHA256 = archive.SOURCE_SUFFIX_SHA256
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
        raise VerifyError(f"{what}: size outside bounded range")

    def reject_constant(value: str) -> None:
        raise VerifyError(f"{what}: non-JSON numeric constant {value!r}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise VerifyError(f"{what}: duplicate key {key!r}")
            output[key] = value
        return output

    try:
        value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerifyError(f"{what}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise VerifyError(f"{what}: not canonical sorted UTF-8 object JSON")
    return value, raw


def _load_catalog() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    metadata = os.lstat(CATALOG_PATH)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size != CATALOG_SIZE
        or sha256_file(CATALOG_PATH) != CATALOG_SHA256
    ):
        raise VerifyError("checked catalog identity drift")
    catalog, _ = _strict_json(CATALOG_PATH, CATALOG_SIZE, "catalog")
    targets = catalog.get("additional_targets")
    if (
        catalog.get("schema") != CATALOG_SCHEMA
        or catalog.get("contains_retail_vertex_values") is not False
        or catalog.get("contains_replacement_bytes") is not False
        or not isinstance(targets, list)
        or len(targets) != 77
    ):
        raise VerifyError("checked catalog contract drift")
    by_id: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict) or not isinstance(target.get("candidate_id"), str):
            raise VerifyError("catalog target is malformed")
        target_id = target["candidate_id"]
        if target_id in by_id:
            raise VerifyError("catalog target ID is duplicated")
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
            raise VerifyError(f"catalog target contract drift: {target_id}")
        by_id[target_id] = target
    return catalog, by_id


def _load_recipe(path: Path) -> tuple[dict[str, Any], bytes, bytes, dict[str, Any]]:
    if RECIPE_SCHEMA_PATH.stat().st_size != RECIPE_SCHEMA_SIZE or sha256_file(RECIPE_SCHEMA_PATH) != RECIPE_SCHEMA_SHA256:
        raise VerifyError("recipe schema identity drift")
    _, targets = _load_catalog()
    recipe, raw = _strict_json(path, MAX_RECIPE_BYTES, "recipe")
    if set(recipe) != set(RECIPE_CONSTANTS) | {"target_id", "positions"}:
        raise VerifyError("recipe top-level key set differs")
    for key, expected in RECIPE_CONSTANTS.items():
        if recipe.get(key) != expected:
            raise VerifyError(f"recipe constant differs: {key}")
    target_id = recipe.get("target_id")
    if not isinstance(target_id, str) or target_id not in targets:
        raise VerifyError("recipe target_id is not catalog-authorized")
    target = targets[target_id]
    count = int(target["position0"]["vertex_count"])
    positions = recipe.get("positions")
    if not isinstance(positions, list) or len(positions) != count:
        raise VerifyError(f"recipe must contain exactly {count} positions")
    encoded = bytearray()
    for vertex, position in enumerate(positions):
        if not isinstance(position, list) or len(position) != 3:
            raise VerifyError(f"recipe position {vertex} is not FLOAT3")
        values: list[float] = []
        for component, value in enumerate(position):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise VerifyError(f"recipe position {vertex}/{component} is not finite")
            values.append(float(value))
        try:
            packed = struct.pack(">3f", *values)
        except (OverflowError, struct.error) as exc:
            raise VerifyError(f"recipe position {vertex} is outside FLOAT32") from exc
        if struct.unpack(">3f", packed) != tuple(values):
            raise VerifyError(f"recipe position {vertex} silently rounds in FLOAT32")
        encoded.extend(packed)
    return recipe, raw, bytes(encoded), target


def _layout(target: dict[str, Any]) -> tuple[int, int, int, int]:
    position = target["position0"]
    return (
        int(position["vertex_count"]),
        int(position["stream_start"]),
        int(position["stream_stride"]),
        int(position["byte_offset"]),
    )


def _positions(system: bytes, target: dict[str, Any]) -> bytes:
    count, start, stride, lane_offset = _layout(target)
    return b"".join(
        system[start + vertex * stride + lane_offset : start + vertex * stride + lane_offset + POSITION_SIZE]
        for vertex in range(count)
    )


def _non_position_hash(system: bytes, target: dict[str, Any]) -> str:
    count, start, stride, lane_offset = _layout(target)
    digest = hashlib.sha256()
    cursor = 0
    for vertex in range(count):
        lane = start + vertex * stride + lane_offset
        digest.update(system[cursor:lane])
        cursor = lane + POSITION_SIZE
    digest.update(system[cursor:])
    return digest.hexdigest()


def _stream_complement_hash(system: bytes, target: dict[str, Any]) -> str:
    count, start, stride, lane_offset = _layout(target)
    digest = hashlib.sha256()
    for vertex in range(count):
        record = start + vertex * stride
        digest.update(system[record : record + lane_offset])
        digest.update(system[record + lane_offset + POSITION_SIZE : record + stride])
    return digest.hexdigest()


def _structural_spans(target: dict[str, Any]) -> dict[str, tuple[int, int, str]]:
    values = {
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
        for name, value in values.items()
    }


def _parse_target_scne(system: bytes, target: dict[str, Any], require_retail_hash: bool) -> dict[str, Any]:
    if len(system) != SYSTEM_LENGTH:
        raise VerifyError("stadium DRAM part length differs")
    root = archive._utf16be(system, archive._rel(system, 0, "SCNE root name"), "SCNE root name")
    if root != "stadium" or archive._u32(system, 0x44, "node count") != 89:
        raise VerifyError("SCNE root/node identity differs")
    node_table = archive._rel(system, 0x48, "node table")
    node_index = int(target["node"]["index"])
    node = node_table + node_index * 0xB0
    node_record = target["node"]["record"]
    if (
        node != node_record["offset"]
        or archive._utf16be(system, archive._rel(system, node, "node name"), "node name") != target["node"]["name"]
        or f"0x{archive._u32(system, node + 4, 'node CRC'):08x}" != target["node"]["name_crc32"]
    ):
        raise VerifyError("catalog target node identity differs")
    counts = (
        archive._u32(system, node + 0x60, "hierarchy count"),
        archive._u32(system, node + 0x7C, "draw count"),
        archive._u32(system, node + 0x84, "mesh count"),
        archive._u32(system, node + 0x98, "declaration count"),
        archive._u32(system, node + 0xA4, "index bits"),
        archive._u32(system, node + 0xA8, "index count"),
    )
    expected_counts = (
        target["hierarchy"]["record_count"],
        target["draw_records"]["count"],
        1,
        target["declarations"]["count"],
        target["index_topology"]["component_bits"],
        target["index_topology"]["index_count"],
    )
    if counts != expected_counts:
        raise VerifyError("catalog target count contract differs")
    pointers = (
        archive._rel(system, node + 0x64, "hierarchy"),
        archive._rel(system, node + 0x80, "draw records"),
        archive._rel(system, node + 0x88, "mesh descriptor"),
        archive._rel(system, node + 0x9C, "declarations"),
        archive._rel(system, node + 0xAC, "indices"),
    )
    expected_pointers = (
        target["hierarchy"]["offset"],
        target["draw_records"]["offset"],
        target["mesh_descriptor_and_stream_records"]["offset"],
        target["declarations"]["offset"],
        target["index_topology"]["offset"],
    )
    if pointers != expected_pointers:
        raise VerifyError("catalog target pointers differ")
    descriptor = pointers[2]
    _, optional, vertices, packed_streams, primitive = struct.unpack_from(">5I", system, descriptor)
    stream_count = int(target["mesh_descriptor_and_stream_records"]["stream_count"])
    if optional != 0 or vertices != target["position0"]["vertex_count"] or packed_streams >> 16 != stream_count or primitive != 5:
        raise VerifyError("catalog mesh descriptor differs")
    for item in target["streams"]:
        stream_index = int(item["index"])
        record = descriptor + 20 + stream_index * 24
        flags, enabled, stride, byte_length = struct.unpack_from(">4I", system, record)
        start = archive._rel(system, record + 16, "stream start")
        end = archive._rel(system, record + 20, "stream end", allow_end=True)
        payload = item["payload"]
        if (
            record != item["record"]["offset"]
            or flags != int(item["flags"], 16)
            or enabled != item["enabled"]
            or stride != item["stride"]
            or start != payload["offset"]
            or byte_length != payload["length"]
            or end != start + byte_length
        ):
            raise VerifyError("catalog stream descriptor differs")
        if require_retail_hash and sha256_bytes(system[start:end]) != payload["sha256"]:
            raise VerifyError("retail catalog stream hash differs")
    for label, (offset, length, digest) in _structural_spans(target).items():
        if offset < 0 or offset + length > len(system) or sha256_bytes(system[offset : offset + length]) != digest:
            raise VerifyError(f"catalog structural span differs: {label}")
    positions = _positions(system, target)
    if require_retail_hash and sha256_bytes(positions) != target["position0"]["retail_lane_sha256"]:
        raise VerifyError("retail catalog POSITION0 lane hash differs")
    bits = int(target["index_topology"]["component_bits"])
    count = int(target["index_topology"]["index_count"])
    index_offset = int(target["index_topology"]["offset"])
    values = struct.unpack_from(f">{count}{'H' if bits == 16 else 'I'}", system, index_offset)
    restart = 0xFFFF if bits == 16 else 0xFFFFFFFF
    if max((value for value in values if value != restart), default=-1) >= int(target["position0"]["vertex_count"]):
        raise VerifyError("catalog topology index exceeds vertex count")
    return {
        "positions": positions,
        "stream_complement": _stream_complement_hash(system, target),
        "non_position": _non_position_hash(system, target),
    }


def _claims() -> dict[str, bool]:
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


def _expected_manifest(
    recipe: dict[str, Any], recipe_raw: bytes, target: dict[str, Any], mode: str,
    source_target: dict[str, Any], output_target: dict[str, Any], source_record: dict[str, Any],
    output_record: dict[str, Any], output_pack_sha: str, output_outer_sha: str,
    changed_offsets: list[int], changed_parts: list[tuple[int, int]], prefix_sha: str, suffix_sha: str,
) -> dict[str, Any]:
    count, start, stride, lane_offset = _layout(target)
    return {
        "schema": MANIFEST_SCHEMA,
        "mode": mode,
        "catalog": {"schema": CATALOG_SCHEMA, "size_bytes": CATALOG_SIZE, "sha256": CATALOG_SHA256, "authorized_target_count": 77},
        "recipe": {
            "schema": recipe["schema"], "sha256": sha256_bytes(recipe_raw),
            "authored_position_count": count, "coordinate_space": recipe["coordinate_space"],
            "vertex_order": recipe["vertex_order"], "position_type": recipe["position_type"],
        },
        "source": {
            "game": "All-Pro Football 2K8 Xbox 360 USA retail",
            "packs": [{"name": name, "size_bytes": size, "sha256": digest} for name, (size, digest) in SOURCE_PACKS.items()],
            "outer_entry_sha256": OUTER_SHA256, "stadium_dram_sha256": SYSTEM_SHA256,
            "stadium_vram_sha256": VRAM_SHA256, "position_payload_sha256": sha256_bytes(source_target["positions"]),
        },
        "target": {
            "target_id": target["candidate_id"], "outer_table_index": 14, "physical_pack": "1A",
            "fixed_outer_allocation_bytes": OUTER_LENGTH, "inner_file_index": 8, "inner_name": "stadium",
            "node_index": target["node"]["index"], "node_name": target["node"]["name"],
            "vertex_count": count, "stream_index": target["position0"]["stream_index"], "stream_start": start,
            "stream_stride_bytes": stride, "position_byte_offset": lane_offset,
            "position_lane_bytes_per_vertex": 12, "approved_position_lane_bytes": count * 12,
            "position_format": "FLOAT32x3_BE",
        },
        "result": {
            "output_directory_contract": ["1A", MANIFEST_NAME], "output_pack_name": "1A",
            "output_pack_size_bytes": SOURCE_PACKS["1A"][0], "output_pack_sha256": output_pack_sha,
            "outer_entry_sha256": output_outer_sha,
            "stadium_dram_sha256": sha256_bytes(output_record["blocks"][0]["decoded"][:SYSTEM_LENGTH]),
            "stadium_vram_sha256": sha256_bytes(output_record["blocks"][1]["decoded"][:VRAM_LENGTH]),
            "position_payload_sha256": sha256_bytes(output_target["positions"]),
            "changed_decoded_block0_byte_count": len(changed_offsets),
            "changed_inner_parts": [{"file_index": a, "part_index": b} for a, b in changed_parts],
            "h7a_block0_recompressed": mode == "changed", "h7a_block0_shift": 12,
            "block0_stored_length_before": source_record["blocks"][0]["stored_length"],
            "block0_stored_length_after": output_record["blocks"][0]["stored_length"],
            "block1_stored_sha256": sha256_bytes(output_record["blocks"][1]["stored"]),
            "file_length_before": source_record["file_length"], "file_length_after": output_record["file_length"],
            "allocation_slack_after_bytes": len(output_record["tail"]),
        },
        "preservation": {
            "target_stream_non_position_sha256": output_target["stream_complement"],
            "scne_non_position_sha256": output_target["non_position"],
            "structural_spans": {label: digest for label, (_, _, digest) in _structural_spans(target).items()},
            "stadium_vram_exact": True, "sibling_part_count": 11, "non_target_part_count": 12,
            "all_non_target_parts_exact": True, "block1_stored_exact": True,
            "footer_sha256": sha256_bytes(output_record["footer"]), "footer_exact": True,
            "iff_header_complement_exact": True, "file_descriptor_table_exact": True,
            "outer_length_exact": True, "outer_tail_zero_and_bounded": True,
            "source_files_rechecked_after_write": True,
            "output_pack_prefix_sha256": prefix_sha, "output_pack_suffix_sha256": suffix_sha,
        },
        "claims": _claims(),
        "contains_replacement_bytes": False,
    }


def verify(game_dir: Path, recipe_path: Path, output_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_game_dir = Path(os.path.normpath((Path.cwd() / game_dir).expanduser() if not game_dir.expanduser().is_absolute() else game_dir.expanduser()))
    game_metadata = os.lstat(raw_game_dir)
    if stat.S_ISLNK(game_metadata.st_mode) or not stat.S_ISDIR(game_metadata.st_mode):
        raise VerifyError("source game directory must be a real non-symlink directory")
    game_dir = raw_game_dir.resolve(strict=True)
    if game_dir != raw_game_dir.absolute():
        raise VerifyError("source game directory path contains a symlink")
    raw_recipe = Path(os.path.normpath((Path.cwd() / recipe_path).expanduser() if not recipe_path.expanduser().is_absolute() else recipe_path.expanduser()))
    recipe_metadata = os.lstat(raw_recipe)
    if stat.S_ISLNK(recipe_metadata.st_mode) or not stat.S_ISREG(recipe_metadata.st_mode) or recipe_metadata.st_size > MAX_RECIPE_BYTES:
        raise VerifyError("recipe must be a bounded regular non-symlink file")
    recipe_path = raw_recipe.resolve(strict=True)
    if recipe_path != raw_recipe.absolute():
        raise VerifyError("recipe path contains a symlink")
    recipe, recipe_raw, wanted_positions, target = _load_recipe(recipe_path)

    output_raw = Path(os.path.normpath((Path.cwd() / output_dir).expanduser() if not output_dir.expanduser().is_absolute() else output_dir.expanduser()))
    output_metadata = os.lstat(output_raw)
    if stat.S_ISLNK(output_metadata.st_mode) or not stat.S_ISDIR(output_metadata.st_mode):
        raise VerifyError("output directory must be a real non-symlink directory")
    output_dir = output_raw.resolve(strict=True)
    if output_dir != output_raw.absolute():
        raise VerifyError("output directory path contains a symlink")
    directory_fd = os.open(output_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        directory_stat = os.fstat(directory_fd)
        directory_identity = (directory_stat.st_dev, directory_stat.st_ino)
        if directory_identity != (output_metadata.st_dev, output_metadata.st_ino):
            raise VerifyError("output directory pathname changed during open")
        if sorted(os.listdir(directory_fd)) != ["1A", MANIFEST_NAME]:
            raise VerifyError("output directory must contain exactly copied 1A and manifest")
        pack_fd = os.open("1A", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        manifest_fd = os.open(MANIFEST_NAME, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            pack_stat = os.fstat(pack_fd)
            manifest_stat = os.fstat(manifest_fd)
            if not stat.S_ISREG(pack_stat.st_mode) or not stat.S_ISREG(manifest_stat.st_mode) or manifest_stat.st_size > MAX_MANIFEST_BYTES:
                raise VerifyError("output children type/size differs")
            source_stat = os.stat(game_dir / "1A", follow_symlinks=False)
            if (pack_stat.st_dev, pack_stat.st_ino) == (source_stat.st_dev, source_stat.st_ino):
                raise VerifyError("output 1A hardlink-aliases source 1A")
            if pack_stat.st_size != SOURCE_PACKS["1A"][0]:
                raise VerifyError("output 1A size differs")
            manifest_raw = os.pread(manifest_fd, manifest_stat.st_size, 0)
            manifest = json.loads(
                manifest_raw,
                object_pairs_hook=lambda pairs: archive._unique_pairs(pairs, "manifest"),
                parse_constant=lambda value: archive._reject_constant(value, "manifest"),
            )
            if not isinstance(manifest, dict) or manifest_raw != canonical_json_bytes(manifest):
                raise VerifyError("manifest is not canonical sorted object JSON")
            output_pack_sha = archive.sha256_fd(pack_fd)
            prefix_sha = archive.sha256_fd_range(pack_fd, 0, OUTER_PACK_OFFSET)
            suffix_offset = OUTER_PACK_OFFSET + OUTER_LENGTH
            suffix_sha = archive.sha256_fd_range(pack_fd, suffix_offset, pack_stat.st_size - suffix_offset)
            output_entry = os.pread(pack_fd, OUTER_LENGTH, OUTER_PACK_OFFSET)
            pack_identity = (pack_stat.st_dev, pack_stat.st_ino)
            manifest_identity = (manifest_stat.st_dev, manifest_stat.st_ino)
            final_pack = os.stat("1A", dir_fd=directory_fd, follow_symlinks=False)
            final_manifest = os.stat(MANIFEST_NAME, dir_fd=directory_fd, follow_symlinks=False)
            if (final_pack.st_dev, final_pack.st_ino) != pack_identity or (final_manifest.st_dev, final_manifest.st_ino) != manifest_identity:
                raise VerifyError("output child pathname identity changed")
        finally:
            os.close(pack_fd)
            os.close(manifest_fd)
    finally:
        final_directory = os.lstat(output_dir)
        if (final_directory.st_dev, final_directory.st_ino) != directory_identity:
            os.close(directory_fd)
            raise VerifyError("output directory pathname identity changed")
        os.close(directory_fd)

    source_identities = archive._source_identities(game_dir)
    routing = archive._parse_outer(game_dir / "0A")
    if routing["physical_pack"] != "1A" or routing["physical_offset"] != OUTER_PACK_OFFSET or routing["size"] != OUTER_LENGTH:
        raise VerifyError("independently derived outer routing differs")
    source_path = game_dir / "1A"
    source_lstat = os.lstat(source_path)
    source_fd = os.open(source_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        source_fd_stat = os.fstat(source_fd)
        source_identity = (source_fd_stat.st_dev, source_fd_stat.st_ino)
        if source_identity != (source_lstat.st_dev, source_lstat.st_ino) or archive.sha256_fd(source_fd) != SOURCE_PACKS["1A"][1]:
            raise VerifyError("source 1A descriptor identity differs")
        source_entry = os.pread(source_fd, OUTER_LENGTH, OUTER_PACK_OFFSET)
        source_prefix = archive.sha256_fd_range(source_fd, 0, OUTER_PACK_OFFSET)
        source_suffix = archive.sha256_fd_range(source_fd, suffix_offset, SOURCE_PACKS["1A"][0] - suffix_offset)
        final_source = os.lstat(source_path)
        if (final_source.st_dev, final_source.st_ino) != source_identity:
            raise VerifyError("source 1A pathname changed")
    finally:
        os.close(source_fd)
    if (
        sha256_bytes(source_entry) != OUTER_SHA256
        or prefix_sha != source_prefix
        or suffix_sha != source_suffix
        or source_prefix != SOURCE_PREFIX_SHA256
        or source_suffix != SOURCE_SUFFIX_SHA256
    ):
        raise VerifyError("output bytes outside outer14 differ from source")

    source_record = archive._parse_iff(source_entry)
    output_record = archive._parse_iff(output_entry)
    archive.validate_iff_header_preservation(source_entry, output_entry)
    source_descriptors = [(item["file_id"], item["type_hash"], item["offsets"]) for item in source_record["files"]]
    output_descriptors = [(item["file_id"], item["type_hash"], item["offsets"]) for item in output_record["files"]]
    if source_descriptors != output_descriptors:
        raise VerifyError("IFF file descriptor table differs")
    for source_block, output_block in zip(source_record["blocks"], output_record["blocks"]):
        for field in ("index", "name_hash", "type_hash", "unknown08", "unpacked", "codec", "indexed"):
            if source_block[field] != output_block[field]:
                raise VerifyError(f"IFF block metadata differs: {field}")
    if (
        source_record["file_length"] != SOURCE_FILE_LENGTH
        or len(source_record["footer"]) != SOURCE_FOOTER_TOTAL
        or sha256_bytes(source_record["footer"]) != SOURCE_FOOTER_SHA
        or len(source_record["tail"]) != SOURCE_TAIL_LENGTH
        or any(source_record["tail"])
    ):
        raise VerifyError("source IFF footer/tail identity differs")
    expected_parts = [{"block_index": 0, "offset": 0, "length": SYSTEM_LENGTH}, {"block_index": 1, "offset": 0, "length": VRAM_LENGTH}]
    if (
        source_record["files"][INNER_INDEX]["file_id"] != INNER_FILE_ID
        or source_record["files"][INNER_INDEX]["type_hash"] != INNER_TYPE_HASH
        or source_record["files"][INNER_INDEX]["parts"] != expected_parts
        or output_record["files"][INNER_INDEX]["parts"] != expected_parts
    ):
        raise VerifyError("stadium file descriptor/part ownership differs")
    source_system = source_record["blocks"][0]["decoded"][:SYSTEM_LENGTH]
    output_system = output_record["blocks"][0]["decoded"][:SYSTEM_LENGTH]
    if sha256_bytes(source_system) != SYSTEM_SHA256 or sha256_bytes(source_record["blocks"][1]["decoded"][:VRAM_LENGTH]) != VRAM_SHA256:
        raise VerifyError("source stadium DRAM/VRAM identity differs")
    source_target = _parse_target_scne(source_system, target, True)
    output_target = _parse_target_scne(output_system, target, False)
    if output_target["positions"] != wanted_positions:
        raise VerifyError("output serialized positions differ from recipe")
    mode = "no_op" if wanted_positions == source_target["positions"] else "changed"
    if mode == "no_op" and (output_pack_sha != SOURCE_PACKS["1A"][1] or output_entry != source_entry):
        raise VerifyError("no-op output 1A is not byte-identical")
    if output_target["stream_complement"] != source_target["stream_complement"] or output_target["non_position"] != source_target["non_position"]:
        raise VerifyError("target interleaves or SCNE non-position bytes changed")
    changed_offsets = [
        index for index, (before, after) in enumerate(zip(source_record["blocks"][0]["decoded"], output_record["blocks"][0]["decoded"])) if before != after
    ]
    count, start, stride, lane_offset = _layout(target)
    allowed = {start + vertex * stride + lane_offset + byte for vertex in range(count) for byte in range(POSITION_SIZE)}
    if not set(changed_offsets).issubset(allowed):
        raise VerifyError("decoded block0 change escapes catalog-authorized lanes")
    source_parts = archive._part_hashes(source_record)
    output_parts = archive._part_hashes(output_record)
    if set(source_parts) != set(output_parts) or len(source_parts) != 13:
        raise VerifyError("file-part corpus differs")
    changed_parts = sorted(key for key in source_parts if source_parts[key] != output_parts[key])
    if changed_parts != ([] if mode == "no_op" else [(8, 0)]):
        raise VerifyError("changed inner part set differs")
    if source_record["blocks"][1]["stored"] != output_record["blocks"][1]["stored"] or sha256_bytes(output_record["blocks"][1]["stored"]) != BLOCK1_STORED_SHA:
        raise VerifyError("stored block1 differs")
    if output_record["footer"] != source_record["footer"] or any(output_record["tail"]):
        raise VerifyError("output footer/tail differs")
    maximum_stored0 = int(_load_catalog()[0]["container"]["h7a_rebuild_envelope"]["maximum_stored_block0_bytes"])
    if output_record["blocks"][0]["stored_length"] > maximum_stored0:
        raise VerifyError("output H7A block0 exceeds catalog allocation maximum")

    expected_manifest = _expected_manifest(
        recipe, recipe_raw, target, mode, source_target, output_target, source_record, output_record,
        output_pack_sha, sha256_bytes(output_entry), changed_offsets, changed_parts, prefix_sha, suffix_sha,
    )
    if manifest != expected_manifest:
        raise VerifyError("manifest differs from complete independent re-derivation")
    if source_identities != expected_manifest["source"]["packs"]:
        raise VerifyError("source identities differ after verification")

    artifact = {
        "schema": VERIFY_SCHEMA,
        "mode": mode,
        "target_id": target["candidate_id"],
        "vertex_count": count,
        "catalog_sha256": CATALOG_SHA256,
        "recipe_sha256": sha256_bytes(recipe_raw),
        "manifest_sha256": sha256_bytes(manifest_raw),
        "source_pack_sha256": SOURCE_PACKS["1A"][1],
        "output_pack_sha256": output_pack_sha,
        "source_outer_sha256": OUTER_SHA256,
        "output_outer_sha256": sha256_bytes(output_entry),
        "output_stadium_dram_sha256": sha256_bytes(output_system),
        "output_position_payload_sha256": sha256_bytes(output_target["positions"]),
        "checks": {
            "catalog_hash_size_schema_and_77_targets_pinned": True,
            "recipe_canonical_duplicate_free_const_pinned": True,
            "recipe_count_derived_from_catalog": True,
            "recipe_positions_exact_finite_binary32": True,
            "source_four_pack_identity_rechecked": True,
            "output_source_inode_alias_rejected": True,
            "outer_routing_independently_derived": True,
            "iff_h7a_independently_reparsed": True,
            "target_scne_node_stream_lane_independently_rederived": True,
            "decoded_positions_equal_recipe": True,
            "changed_decoded_bytes_subset_of_catalog_position_lanes": True,
            "target_stream_non_position_interleaves_exact": True,
            "all_scne_non_position_bytes_exact": True,
            "node_matrix_hierarchy_draw_index_declarations_descriptor_exact": True,
            "stadium_vram_exact": True,
            "eleven_sibling_parts_exact": True,
            "twelve_non_target_parts_exact": True,
            "stored_block1_exact": True,
            "footer_exact": True,
            "iff_header_complement_exact": True,
            "file_descriptor_table_exact": True,
            "fixed_outer_length_and_zero_tail": True,
            "all_output_1a_bytes_outside_outer14_exact": True,
            "manifest_every_field_independently_rederived": True,
            "no_op_complete_1a_byte_identity": mode != "no_op" or output_pack_sha == SOURCE_PACKS["1A"][1],
        },
        "claims": _claims(),
        "contains_replacement_bytes": False,
    }
    return artifact, expected_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        artifact, _ = verify(args.game_dir, args.recipe, args.output_dir)
        archive._write_artifact(args.artifact, artifact, args.output_dir)
        print(
            "APF_SCNE_CATALOG_POSITION_VERIFY_PASS "
            f"mode={artifact['mode']} target={artifact['target_id']} vertices={artifact['vertex_count']} "
            f"output_pack_sha256={artifact['output_pack_sha256']} siblings=11 non_target_parts=12 "
            "runtime=false hardware=false production=false"
        )
        return 0
    except (VerifyError, OSError, ValueError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
