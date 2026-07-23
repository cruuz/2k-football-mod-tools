#!/usr/bin/env python3
"""Independent verifier for APF node17 same-footprint topology output.

This module imports only the prior standard-library independent container
verifier for primitive I/O helpers.  It does not import the topology writer,
APF production parsers, compressor, or SCNE parser.  It independently derives
the copied-volume routing, H7A/IFF contents, draw equations, native strip,
changed-byte set, and every manifest field.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

import apf_stadium_static_position_verify as base


RECIPE_SCHEMA = "apf2k8_scne_same_footprint_topology_recipe/v1"
MANIFEST_SCHEMA = "apf2k8_scne_same_footprint_topology_patch/v1"
VERIFY_SCHEMA = "apf2k8_scne_same_footprint_topology_verification/v1"
MANIFEST_NAME = "apf2k8_scne_same_footprint_topology_manifest.json"
RECIPE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "reports/specs/apf2k8_scne_same_footprint_topology_recipe.schema.json"
)
RECIPE_SCHEMA_SIZE = 5_949
RECIPE_SCHEMA_SHA256 = "a201d33a1fd44daebb05e68ded770c08966ff6b8bf28267e8603df91fb63bb8e"
MAX_RECIPE_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024

INDEX_OFFSET = 375_760
INDEX_SIZE = 8
INDEX_SOURCE_SHA256 = "96b383ee0d221556a56277315db425256549a46ccc5217a392181783327a6dc5"
DRAW_OFFSET = 375_712
DRAW_SHA256 = "161a2e06c0b875b6679423f490c2c89691d1da9899003768a0f4eac01cfe873f"

RECIPE_CONSTANTS = {
    "schema": RECIPE_SCHEMA,
    "operation": "replace_node17_exact_four_be16_strip",
    "game": {"title": "All-Pro Football 2K8", "platform": "Xbox 360"},
    "source_contract": {
        "index_pack": "0A",
        "physical_pack": "1A",
        "index_sha256": base.SOURCE_PACKS["0A"][1],
        "physical_pack_sha256": base.SOURCE_PACKS["1A"][1],
    },
    "target": {
        "outer_table_index": 14,
        "outer_name_id": "0x02bae370",
        "inner_file_index": 8,
        "inner_name": "stadium",
        "inner_file_id": "0xe604044f",
        "inner_type": "SCNE",
        "node_index": 17,
        "node_name": "polySurface19930",
        "vertex_count": 4,
        "index_component_bits": 16,
        "index_count": 4,
        "draw_record_sha256": DRAW_SHA256,
    },
    "topology": {
        "native_primitive": "D3DPT_TRIANGLESTRIP",
        "serialized_byte_order": "big-endian",
        "restart_value": 65535,
        "vertex_order": "existing_native_vertex_order",
    },
    "claim_flags": {
        "same_footprint_topology_only": True,
        "changed_count_proved": False,
        "material_or_vertex_authoring_proved": False,
        "emulator_runtime_visibility_proved": False,
        "xbox_360_hardware_proved": False,
        "production_mesh_importer_proved": False,
    },
}


class VerifyError(ValueError):
    """Independent verification failed closed."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=4, sort_keys=True) + "\n").encode("utf-8")


def _unique_pairs(pairs: list[tuple[str, Any]], what: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise VerifyError(f"duplicate {what} JSON key {key!r}")
        output[key] = value
    return output


def _reject_constant(value: str, what: str) -> None:
    raise VerifyError(f"non-JSON {what} numeric constant {value!r}")


def _strict_json(path: Path, what: str, limit: int) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if not 0 < len(raw) <= limit:
        raise VerifyError(f"{what} size is outside bounded range")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=lambda pairs: _unique_pairs(pairs, what),
            parse_constant=lambda item: _reject_constant(item, what),
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerifyError(f"invalid {what} JSON: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise VerifyError(f"{what} must be canonical sorted object JSON")
    return value, raw


def expand_strip(indices: list[int]) -> list[int]:
    output: list[int] = []
    strip: list[int] = []
    for value in indices:
        if value == 0xFFFF:
            strip.clear()
            continue
        strip.append(value)
        if len(strip) < 3:
            continue
        a, b, c = strip[-3:]
        number = len(strip) - 3
        triangle = (a, b, c) if number % 2 == 0 else (b, a, c)
        if len(set(triangle)) == 3:
            output.extend(triangle)
    return output


def _load_recipe(path: Path) -> tuple[dict[str, Any], bytes, bytes]:
    if (
        RECIPE_SCHEMA_PATH.stat().st_size != RECIPE_SCHEMA_SIZE
        or base.sha256_file(RECIPE_SCHEMA_PATH) != RECIPE_SCHEMA_SHA256
    ):
        raise VerifyError("recipe schema identity drift")
    schema = json.loads(RECIPE_SCHEMA_PATH.read_bytes())
    if schema.get("$id") != RECIPE_SCHEMA:
        raise VerifyError("recipe schema ID drift")
    recipe, raw = _strict_json(path, "recipe", MAX_RECIPE_BYTES)
    if set(recipe) != set(RECIPE_CONSTANTS) | {"indices"}:
        raise VerifyError("recipe top-level key set differs")
    for key, expected in RECIPE_CONSTANTS.items():
        if recipe.get(key) != expected:
            raise VerifyError(f"recipe constant-pinned field differs: {key}")
    indices = recipe.get("indices")
    if (
        not isinstance(indices, list)
        or len(indices) != 4
        or any(isinstance(value, bool) or not isinstance(value, int) for value in indices)
        or sorted(indices) != [0, 1, 2, 3]
    ):
        raise VerifyError("indices must be a duplicate-free permutation of 0,1,2,3")
    packed = struct.pack(">4H", *indices)
    if list(struct.unpack(">4H", packed)) != indices or len(expand_strip(indices)) != 6:
        raise VerifyError("recipe native strip round-trip differs")
    return recipe, raw, packed


def _non_index_hash(system: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(system[:INDEX_OFFSET])
    digest.update(system[INDEX_OFFSET + INDEX_SIZE :])
    return digest.hexdigest()


def _parse_target_scne(system: bytes, require_retail_index: bool) -> dict[str, Any]:
    if len(system) != base.SYSTEM_LENGTH:
        raise VerifyError("stadium DRAM part length differs")
    root = base._utf16be(system, base._rel(system, 0, "SCNE root name"), "SCNE root name")
    if root != "stadium" or base._u32(system, 0x44, "node count") != 89:
        raise VerifyError("SCNE root/node identity differs")
    node_table = base._rel(system, 0x48, "node table")
    node = node_table + base.NODE_INDEX * 0xB0
    if (
        node != 26_240
        or base._utf16be(system, base._rel(system, node, "node name"), "node name") != base.NODE_NAME
        or base._u32(system, node + 4, "node CRC") != base.NODE_CRC
    ):
        raise VerifyError("target node identity differs")
    counts = (
        base._u32(system, node + 0x60, "hierarchy count"),
        base._u32(system, node + 0x7C, "draw count"),
        base._u32(system, node + 0x84, "mesh count"),
        base._u32(system, node + 0x98, "declaration count"),
        base._u32(system, node + 0xA4, "index bits"),
        base._u32(system, node + 0xA8, "index count"),
    )
    if counts != (1, 1, 1, 3, 16, 4):
        raise VerifyError("target node count contract differs")
    hierarchy = base._rel(system, node + 0x64, "hierarchy")
    draw = base._rel(system, node + 0x80, "draw")
    descriptor = base._rel(system, node + 0x88, "mesh descriptor")
    declarations = base._rel(system, node + 0x9C, "declarations")
    index = base._rel(system, node + 0xAC, "indices")
    if (hierarchy, draw, descriptor, declarations, index) != (
        375_664, DRAW_OFFSET, 376_000, 375_808, INDEX_OFFSET
    ):
        raise VerifyError("target node table pointers differ")
    expected_declarations = [
        (0x46E6CB71, 0x801F78B9, 0x20000000, 0x002A23B9),
        (0xF51CD0CF, 0x1C7EE841, 0x200C0000, 0x001A2360),
        (0x57B6A2FA, 0xD17DAF62, 0x20140000, 0x002A2187),
    ]
    for item, expected in enumerate(expected_declarations):
        if struct.unpack_from(">4I", system, declarations + item * 64) != expected:
            raise VerifyError("target vertex declaration differs")
    _, optional, vertices, packed_streams, primitive = struct.unpack_from(">5I", system, descriptor)
    if (optional, vertices, packed_streams, primitive) != (0, 4, 0x00010000, 5):
        raise VerifyError("target mesh descriptor differs")
    flags, enabled, stride, byte_length = struct.unpack_from(">4I", system, descriptor + 20)
    stream_start = base._rel(system, descriptor + 36, "stream start")
    stream_end = base._rel(system, descriptor + 40, "stream end", allow_end=True)
    if (flags, enabled, stride, byte_length, stream_start, stream_end) != (
        0x40000000, 1, 24, 96, base.STREAM_START, base.STREAM_START + base.STREAM_LENGTH
    ):
        raise VerifyError("target stream descriptor differs")
    if sha256_bytes(system[DRAW_OFFSET : DRAW_OFFSET + 48]) != DRAW_SHA256:
        raise VerifyError("target draw record hash differs")
    draw_words = struct.unpack_from(">12I", system, DRAW_OFFSET)
    if draw_words != (6, 0, 4, 2, 0, 0, 4, 0, 12, 0, 0, 1):
        raise VerifyError("target draw semantic equations differ")
    indices = [base._u16(system, index + item * 2, "index") for item in range(4)]
    if require_retail_index and indices != [0, 1, 2, 3]:
        raise VerifyError("source strip indices differ")
    if sorted(indices) != [0, 1, 2, 3]:
        raise VerifyError("output strip is not the admitted vertex permutation")
    triangles = expand_strip(indices)
    if len(triangles) != 6:
        raise VerifyError("native strip does not emit exactly two triangles")
    stream = system[stream_start:stream_end]
    if sha256_bytes(stream) != "86f3c7a4cc3d5c46d9bcfcf48bd465e96f954ce1a3e764e20c595633e70264eb":
        raise VerifyError("target vertex stream differs")
    for label, (offset, length, expected_hash) in base.TARGET_SPANS.items():
        if label == "index_buffer" and not require_retail_index:
            continue
        if sha256_bytes(system[offset : offset + length]) != expected_hash:
            raise VerifyError(f"target structural span differs: {label}")
    return {
        "indices": indices,
        "index_bytes": system[index : index + INDEX_SIZE],
        "triangles": triangles,
        "stream": stream,
        "non_index": _non_index_hash(system),
        "draw": {
            "draw_primitive_code": draw_words[0],
            "first_element": draw_words[1],
            "element_count": draw_words[2],
            "primitive_capacity": draw_words[3],
            "base_vertex": draw_words[4],
            "minimum_vertex": draw_words[5],
            "vertex_range": draw_words[6],
            "optional_draw_state_is_null": draw_words[7] == 0,
            "material_slot": draw_words[8],
            "render_flags_2c": draw_words[11],
        },
    }


def _claims() -> dict[str, bool]:
    return {
        "offline_same_footprint_topology_writeback_proved": True,
        "changed_count_proved": False,
        "material_or_vertex_authoring_proved": False,
        "emulator_runtime_visibility_proved": False,
        "xbox_360_hardware_proved": False,
        "production_mesh_importer_proved": False,
    }


def _expected_manifest(
    recipe: dict[str, Any],
    recipe_raw: bytes,
    mode: str,
    source_target: dict[str, Any],
    output_target: dict[str, Any],
    source_record: dict[str, Any],
    output_record: dict[str, Any],
    output_pack_sha: str,
    output_outer_sha: str,
    changed_offsets: list[int],
    changed_parts: list[tuple[int, int]],
    prefix_sha: str,
    suffix_sha: str,
) -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "mode": mode,
        "recipe": {
            "schema": recipe["schema"],
            "sha256": sha256_bytes(recipe_raw),
            "index_count": 4,
            "native_primitive": "D3DPT_TRIANGLESTRIP",
        },
        "source": {
            "game": "All-Pro Football 2K8 Xbox 360 USA retail",
            "packs": [
                {"name": name, "size_bytes": size, "sha256": digest}
                for name, (size, digest) in base.SOURCE_PACKS.items()
            ],
            "outer_entry_sha256": base.OUTER_SHA256,
            "stadium_dram_sha256": base.SYSTEM_SHA256,
            "stadium_vram_sha256": base.VRAM_SHA256,
            "index_buffer_sha256": INDEX_SOURCE_SHA256,
        },
        "target": {
            "outer_table_index": 14,
            "physical_pack": "1A",
            "fixed_outer_allocation_bytes": base.OUTER_LENGTH,
            "inner_file_index": 8,
            "inner_name": "stadium",
            "node_index": 17,
            "node_name": base.NODE_NAME,
            "vertex_count": 4,
            "index_component_bits": 16,
            "index_count": 4,
            "index_buffer_offset": INDEX_OFFSET,
            "index_allocation_bytes": INDEX_SIZE,
            "draw_record_offset": DRAW_OFFSET,
            "draw_record_sha256": DRAW_SHA256,
        },
        "result": {
            "output_directory_contract": ["1A", MANIFEST_NAME],
            "output_pack_name": "1A",
            "output_pack_size_bytes": base.SOURCE_PACKS["1A"][0],
            "output_pack_sha256": output_pack_sha,
            "outer_entry_sha256": output_outer_sha,
            "stadium_dram_sha256": sha256_bytes(output_record["blocks"][0]["decoded"][: base.SYSTEM_LENGTH]),
            "stadium_vram_sha256": sha256_bytes(output_record["blocks"][1]["decoded"][: base.VRAM_LENGTH]),
            "index_buffer_sha256": sha256_bytes(output_target["index_bytes"]),
            "changed_decoded_dram_byte_count": len(changed_offsets),
            "changed_inner_parts": [
                {"file_index": first, "part_index": second}
                for first, second in changed_parts
            ],
            "native_triangle_count": len(output_target["triangles"]) // 3,
            "native_degenerate_triangle_count": 0,
            "h7a_block0_recompressed": mode == "changed",
            "h7a_block0_shift": 12,
            "block0_stored_length_before": source_record["blocks"][0]["stored_length"],
            "block0_stored_length_after": output_record["blocks"][0]["stored_length"],
            "block1_stored_sha256": sha256_bytes(output_record["blocks"][1]["stored"]),
            "file_length_before": source_record["file_length"],
            "file_length_after": output_record["file_length"],
            "allocation_slack_after_bytes": len(output_record["tail"]),
        },
        "preservation": {
            "scne_non_index_sha256": output_target["non_index"],
            "draw_semantics": output_target["draw"],
            "draw_record_exact": True,
            "vertex_stream_exact": True,
            "declarations_and_descriptor_exact": True,
            "matrix_hierarchy_and_node_exact": True,
            "stadium_vram_exact": True,
            "sibling_part_count": 11,
            "non_target_part_count": 12,
            "all_non_target_parts_exact": True,
            "block1_stored_exact": True,
            "footer_sha256": sha256_bytes(output_record["footer"]),
            "footer_exact": True,
            "iff_header_complement_exact": True,
            "file_descriptor_table_exact": True,
            "outer_length_exact": True,
            "outer_tail_zero_and_bounded": True,
            "source_files_rechecked_after_write": True,
            "output_pack_prefix_sha256": prefix_sha,
            "output_pack_suffix_sha256": suffix_sha,
        },
        "claims": _claims(),
        "contains_replacement_bytes": False,
    }


def verify(game_dir: Path, recipe_path: Path, output_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_game = Path(os.path.normpath(game_dir.expanduser() if game_dir.is_absolute() else Path.cwd() / game_dir.expanduser()))
    game_meta = os.lstat(raw_game)
    if stat.S_ISLNK(game_meta.st_mode) or not stat.S_ISDIR(game_meta.st_mode):
        raise VerifyError("source game directory must be a real non-symlink directory")
    game_dir = raw_game.resolve(strict=True)
    if game_dir != raw_game.absolute():
        raise VerifyError("source game directory path contains a symlink")
    raw_recipe = Path(os.path.normpath(recipe_path.expanduser() if recipe_path.is_absolute() else Path.cwd() / recipe_path.expanduser()))
    recipe_meta = os.lstat(raw_recipe)
    if stat.S_ISLNK(recipe_meta.st_mode) or not stat.S_ISREG(recipe_meta.st_mode) or recipe_meta.st_size > MAX_RECIPE_BYTES:
        raise VerifyError("recipe must be a bounded regular non-symlink file")
    recipe_path = raw_recipe.resolve(strict=True)
    if recipe_path != raw_recipe.absolute():
        raise VerifyError("recipe path contains a symlink")
    raw_output = Path(os.path.normpath(output_dir.expanduser() if output_dir.is_absolute() else Path.cwd() / output_dir.expanduser()))
    output_meta = os.lstat(raw_output)
    if stat.S_ISLNK(output_meta.st_mode) or not stat.S_ISDIR(output_meta.st_mode):
        raise VerifyError("output directory must be a real directory, not a symlink")
    output_dir = raw_output.resolve(strict=True)
    if output_dir != raw_output.absolute():
        raise VerifyError("output directory path contains a symlink")

    directory_fd = os.open(output_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        directory_stat = os.fstat(directory_fd)
        directory_identity = (directory_stat.st_dev, directory_stat.st_ino)
        if directory_identity != (output_meta.st_dev, output_meta.st_ino):
            raise VerifyError("output directory pathname changed during open")
        if sorted(os.listdir(directory_fd)) != ["1A", MANIFEST_NAME]:
            raise VerifyError("output directory must contain exactly copied 1A and manifest")
        output_fd = os.open("1A", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        manifest_fd = os.open(MANIFEST_NAME, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            output_stat = os.fstat(output_fd)
            manifest_stat = os.fstat(manifest_fd)
            if not stat.S_ISREG(output_stat.st_mode) or not stat.S_ISREG(manifest_stat.st_mode):
                raise VerifyError("output children must be regular files")
            if output_stat.st_size != base.SOURCE_PACKS["1A"][0] or manifest_stat.st_size > MAX_MANIFEST_BYTES:
                raise VerifyError("output child size differs")
            source_stat = os.stat(game_dir / "1A", follow_symlinks=False)
            if (output_stat.st_dev, output_stat.st_ino) == (source_stat.st_dev, source_stat.st_ino):
                raise VerifyError("output 1A hardlink-aliases source 1A")
            output_identity = (output_stat.st_dev, output_stat.st_ino)
            manifest_identity = (manifest_stat.st_dev, manifest_stat.st_ino)
            manifest_raw = os.pread(manifest_fd, manifest_stat.st_size, 0)
            manifest = json.loads(
                manifest_raw,
                object_pairs_hook=lambda pairs: _unique_pairs(pairs, "manifest"),
                parse_constant=lambda value: _reject_constant(value, "manifest"),
            )
            if not isinstance(manifest, dict) or manifest_raw != canonical_json_bytes(manifest):
                raise VerifyError("manifest is not canonical sorted object JSON")
            output_pack_sha = base.sha256_fd(output_fd)
            prefix_sha = base.sha256_fd_range(output_fd, 0, base.OUTER_PACK_OFFSET)
            suffix_offset = base.OUTER_PACK_OFFSET + base.OUTER_LENGTH
            suffix_sha = base.sha256_fd_range(output_fd, suffix_offset, output_stat.st_size - suffix_offset)
            output_entry = os.pread(output_fd, base.OUTER_LENGTH, base.OUTER_PACK_OFFSET)
            final_output = os.stat("1A", dir_fd=directory_fd, follow_symlinks=False)
            final_manifest = os.stat(MANIFEST_NAME, dir_fd=directory_fd, follow_symlinks=False)
            if (final_output.st_dev, final_output.st_ino) != output_identity or (final_manifest.st_dev, final_manifest.st_ino) != manifest_identity:
                raise VerifyError("output child pathname identity changed")
        finally:
            os.close(output_fd)
            os.close(manifest_fd)
    finally:
        final_dir = os.lstat(output_dir)
        if (final_dir.st_dev, final_dir.st_ino) != directory_identity:
            os.close(directory_fd)
            raise VerifyError("output directory pathname identity changed")
        os.close(directory_fd)

    recipe, recipe_raw, wanted_indices = _load_recipe(recipe_path)
    source_identities = base._source_identities(game_dir)
    routing = base._parse_outer(game_dir / "0A")
    if routing["physical_pack"] != "1A" or routing["physical_offset"] != base.OUTER_PACK_OFFSET or routing["size"] != base.OUTER_LENGTH:
        raise VerifyError("independently derived outer routing differs")
    source_path = game_dir / "1A"
    source_lstat = os.lstat(source_path)
    source_fd = os.open(source_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        source_meta = os.fstat(source_fd)
        source_identity = (source_meta.st_dev, source_meta.st_ino)
        if source_identity != (source_lstat.st_dev, source_lstat.st_ino) or source_meta.st_size != base.SOURCE_PACKS["1A"][0] or base.sha256_fd(source_fd) != base.SOURCE_PACKS["1A"][1]:
            raise VerifyError("source 1A descriptor identity differs")
        source_entry = os.pread(source_fd, base.OUTER_LENGTH, base.OUTER_PACK_OFFSET)
        source_prefix = base.sha256_fd_range(source_fd, 0, base.OUTER_PACK_OFFSET)
        source_suffix = base.sha256_fd_range(source_fd, suffix_offset, base.SOURCE_PACKS["1A"][0] - suffix_offset)
        final_source = os.lstat(source_path)
        if (final_source.st_dev, final_source.st_ino) != source_identity:
            raise VerifyError("source 1A pathname changed")
    finally:
        os.close(source_fd)
    if (
        sha256_bytes(source_entry) != base.OUTER_SHA256
        or prefix_sha != source_prefix
        or suffix_sha != source_suffix
        or source_prefix != base.SOURCE_PREFIX_SHA256
        or source_suffix != base.SOURCE_SUFFIX_SHA256
    ):
        raise VerifyError("output bytes outside outer14 differ from source")

    source_record = base._parse_iff(source_entry)
    output_record = base._parse_iff(output_entry)
    base.validate_iff_header_preservation(source_entry, output_entry)
    source_descriptors = [(item["file_id"], item["type_hash"], item["offsets"]) for item in source_record["files"]]
    output_descriptors = [(item["file_id"], item["type_hash"], item["offsets"]) for item in output_record["files"]]
    if output_descriptors != source_descriptors:
        raise VerifyError("output IFF file descriptor table differs")
    for source_block, output_block in zip(source_record["blocks"], output_record["blocks"]):
        for field in ("index", "name_hash", "type_hash", "unknown08", "unpacked", "codec", "indexed"):
            if source_block[field] != output_block[field]:
                raise VerifyError(f"output IFF block metadata differs: {field}")
    if source_record["file_length"] != base.SOURCE_FILE_LENGTH or len(source_record["footer"]) != base.SOURCE_FOOTER_TOTAL or sha256_bytes(source_record["footer"]) != base.SOURCE_FOOTER_SHA or len(source_record["tail"]) != base.SOURCE_TAIL_LENGTH or any(source_record["tail"]):
        raise VerifyError("source IFF footer/tail identity differs")
    expected_parts = [
        {"block_index": 0, "offset": 0, "length": base.SYSTEM_LENGTH},
        {"block_index": 1, "offset": 0, "length": base.VRAM_LENGTH},
    ]
    if source_record["files"][8]["parts"] != expected_parts or output_record["files"][8]["parts"] != expected_parts:
        raise VerifyError("stadium part ownership differs")
    source_system = source_record["blocks"][0]["decoded"][: base.SYSTEM_LENGTH]
    output_system = output_record["blocks"][0]["decoded"][: base.SYSTEM_LENGTH]
    if sha256_bytes(source_system) != base.SYSTEM_SHA256 or sha256_bytes(source_record["blocks"][1]["decoded"][: base.VRAM_LENGTH]) != base.VRAM_SHA256:
        raise VerifyError("source stadium identity differs")
    source_target = _parse_target_scne(source_system, True)
    output_target = _parse_target_scne(output_system, False)
    if output_target["index_bytes"] != wanted_indices:
        raise VerifyError("output native BE16 indices differ from recipe")
    mode = "no_op" if wanted_indices == source_target["index_bytes"] else "changed"
    if mode == "no_op" and (output_pack_sha != base.SOURCE_PACKS["1A"][1] or output_entry != source_entry):
        raise VerifyError("no-op output 1A is not byte-identical")
    if output_target["stream"] != source_target["stream"] or output_target["non_index"] != source_target["non_index"]:
        raise VerifyError("vertex stream or SCNE non-index bytes changed")
    changed_offsets = [
        index for index, (before, after) in enumerate(
            zip(source_record["blocks"][0]["decoded"], output_record["blocks"][0]["decoded"])
        ) if before != after
    ]
    if not set(changed_offsets).issubset(range(INDEX_OFFSET, INDEX_OFFSET + INDEX_SIZE)):
        raise VerifyError("decoded DRAM change escapes index allocation")
    source_parts = base._part_hashes(source_record)
    output_parts = base._part_hashes(output_record)
    if set(source_parts) != set(output_parts) or len(source_parts) != 13:
        raise VerifyError("file-part corpus differs")
    changed_parts = sorted(key for key in source_parts if source_parts[key] != output_parts[key])
    if changed_parts != ([] if mode == "no_op" else [(8, 0)]):
        raise VerifyError("changed inner part set differs")
    if source_record["blocks"][1]["stored"] != output_record["blocks"][1]["stored"] or sha256_bytes(output_record["blocks"][1]["stored"]) != base.BLOCK1_STORED_SHA:
        raise VerifyError("stored block1 differs")
    if output_record["footer"] != source_record["footer"] or any(output_record["tail"]):
        raise VerifyError("output footer/tail differs")

    expected_manifest = _expected_manifest(
        recipe, recipe_raw, mode, source_target, output_target, source_record,
        output_record, output_pack_sha, sha256_bytes(output_entry), changed_offsets,
        changed_parts, prefix_sha, suffix_sha,
    )
    if manifest != expected_manifest:
        raise VerifyError("manifest differs from complete independent re-derivation")
    if source_identities != expected_manifest["source"]["packs"]:
        raise VerifyError("source identities differ after verification")
    artifact = {
        "schema": VERIFY_SCHEMA,
        "mode": mode,
        "recipe_sha256": sha256_bytes(recipe_raw),
        "manifest_sha256": sha256_bytes(manifest_raw),
        "source_pack_sha256": base.SOURCE_PACKS["1A"][1],
        "output_pack_sha256": output_pack_sha,
        "source_outer_sha256": base.OUTER_SHA256,
        "output_outer_sha256": sha256_bytes(output_entry),
        "output_stadium_dram_sha256": sha256_bytes(output_system),
        "output_index_buffer_sha256": sha256_bytes(output_target["index_bytes"]),
        "native_triangle_count": len(output_target["triangles"]) // 3,
        "checks": {
            "recipe_canonical_duplicate_free_const_pinned": True,
            "source_four_pack_identity_rechecked": True,
            "output_source_inode_alias_rejected": True,
            "outer_routing_independently_derived": True,
            "iff_h7a_independently_reparsed": True,
            "target_scne_layout_independently_rederived": True,
            "draw_equations_independently_rederived": True,
            "native_strip_equals_recipe": True,
            "two_nondegenerate_triangles": True,
            "changed_decoded_bytes_subset_of_eight_index_bytes": True,
            "draw_record_exact": True,
            "vertex_stream_exact": True,
            "matrix_hierarchy_declarations_descriptor_exact": True,
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
            "no_op_complete_1a_byte_identity": mode != "no_op" or output_pack_sha == base.SOURCE_PACKS["1A"][1],
        },
        "claims": _claims(),
        "contains_replacement_bytes": False,
    }
    return artifact, expected_manifest


def _write_artifact(path: Path, artifact: dict[str, Any], forbidden_dir: Path) -> None:
    raw = path.expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    raw = Path(os.path.normpath(raw))
    parent = raw.parent.resolve(strict=True)
    target = parent / raw.name
    try:
        target.relative_to(forbidden_dir)
    except ValueError:
        pass
    else:
        raise VerifyError("verification artifact must be outside writer output directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(target, flags, 0o644)
    try:
        data = canonical_json_bytes(artifact)
        written = 0
        while written < len(data):
            count = os.write(descriptor, data[written:])
            if count <= 0:
                raise VerifyError("short verification artifact write")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verification-out", type=Path)
    args = parser.parse_args(argv)
    try:
        artifact, _ = verify(args.game_dir, args.recipe, args.output_dir)
        if args.verification_out is not None:
            _write_artifact(args.verification_out, artifact, args.output_dir.resolve(strict=True))
        print(
            "APF_SCNE_NODE17_TOPOLOGY_VERIFY_PASS "
            f"mode={artifact['mode']} triangles={artifact['native_triangle_count']} "
            f"output_pack_sha256={artifact['output_pack_sha256']} "
            "runtime=false hardware=false"
        )
        return 0
    except (VerifyError, base.VerifyError, OSError, ValueError, KeyError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
