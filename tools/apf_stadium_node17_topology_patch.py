#!/usr/bin/env python3
"""Fail-closed APF stadium node17 same-footprint topology writer.

The sole authorized decoded mutation is the existing eight-byte BE16 index
allocation for outer14/inner8/stadium/node17.  The admitted recipe is a
permutation of the four existing vertex ordinals, so every draw range/count,
minimum/range field, stream, vertex record, pointer, and allocation remains
bit-exact.  Runtime and hardware acceptance are deliberately not claimed.
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

import apf_inner
import apf_outer
import apf_scene
import apf_stadium_static_position_patch as container


RECIPE_SCHEMA = "apf2k8_scne_same_footprint_topology_recipe/v1"
MANIFEST_SCHEMA = "apf2k8_scne_same_footprint_topology_patch/v1"
RECIPE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "reports/specs/apf2k8_scne_same_footprint_topology_recipe.schema.json"
)
RECIPE_SCHEMA_SIZE = 5_949
RECIPE_SCHEMA_SHA256 = "a201d33a1fd44daebb05e68ded770c08966ff6b8bf28267e8603df91fb63bb8e"
MANIFEST_NAME = "apf2k8_scne_same_footprint_topology_manifest.json"
OUTPUT_PACK_NAME = "1A"
MAX_RECIPE_BYTES = 1024 * 1024

INDEX_OFFSET = 375_760
INDEX_SIZE = 8
INDEX_COUNT = 4
INDEX_BITS = 16
INDEX_SOURCE_SHA256 = "96b383ee0d221556a56277315db425256549a46ccc5217a392181783327a6dc5"
DRAW_OFFSET = 375_712
DRAW_SIZE = 48
DRAW_SHA256 = "161a2e06c0b875b6679423f490c2c89691d1da9899003768a0f4eac01cfe873f"

RECIPE_CONSTANTS = {
    "schema": RECIPE_SCHEMA,
    "operation": "replace_node17_exact_four_be16_strip",
    "game": {"title": "All-Pro Football 2K8", "platform": "Xbox 360"},
    "source_contract": {
        "index_pack": "0A",
        "physical_pack": "1A",
        "index_sha256": container.SOURCE_PACKS["0A"][1],
        "physical_pack_sha256": container.SOURCE_PACKS["1A"][1],
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


class PatchError(ValueError):
    """Recipe, source profile, preservation, or publication validation failed."""


class BytesReader:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        del entry
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise apf_inner.FormatError("memory entry read is out of bounds")
        return self.data[offset : offset + size]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=4, sort_keys=True) + "\n").encode("utf-8")


def _strict_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_RECIPE_BYTES:
        raise PatchError("recipe size is outside bounded range")

    def reject_constant(value: str) -> None:
        raise PatchError(f"non-JSON numeric constant {value!r}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PatchError(f"duplicate JSON object key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw, parse_constant=reject_constant, object_pairs_hook=unique_object
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PatchError(f"invalid recipe JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PatchError("recipe top level must be an object")
    if raw != canonical_json_bytes(value):
        raise PatchError("recipe must be canonical sorted UTF-8 JSON")
    return value, raw


def load_recipe(path: Path) -> tuple[dict[str, Any], bytes, bytes]:
    if (
        RECIPE_SCHEMA_PATH.stat().st_size != RECIPE_SCHEMA_SIZE
        or container.sha256_file(RECIPE_SCHEMA_PATH) != RECIPE_SCHEMA_SHA256
    ):
        raise PatchError("recipe schema identity drift")
    schema = json.loads(RECIPE_SCHEMA_PATH.read_bytes())
    if schema.get("$id") != RECIPE_SCHEMA:
        raise PatchError("recipe schema ID drift")
    recipe, raw = _strict_json(path)
    if set(recipe) != set(RECIPE_CONSTANTS) | {"indices"}:
        raise PatchError("recipe top-level key set differs")
    for key, expected in RECIPE_CONSTANTS.items():
        if recipe.get(key) != expected:
            raise PatchError(f"recipe constant-pinned field differs: {key}")
    indices = recipe.get("indices")
    if (
        not isinstance(indices, list)
        or len(indices) != INDEX_COUNT
        or any(isinstance(value, bool) or not isinstance(value, int) for value in indices)
    ):
        raise PatchError("indices must be exactly four JSON integers")
    if sorted(indices) != list(range(INDEX_COUNT)):
        raise PatchError("indices must be a duplicate-free permutation of 0,1,2,3")
    packed = struct.pack(">4H", *indices)
    if list(struct.unpack(">4H", packed)) != indices:
        raise PatchError("BE16 index round-trip differs")
    triangles = expand_strip(indices)
    if len(triangles) != 6 or len({tuple(triangles[:3]), tuple(triangles[3:])}) != 2:
        raise PatchError("admitted strip must decode to two distinct nondegenerate triangles")
    return recipe, raw, packed


def expand_strip(indices: list[int] | tuple[int, ...]) -> list[int]:
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
        triangle_number = len(strip) - 3
        triangle = (a, b, c) if triangle_number % 2 == 0 else (b, a, c)
        if len(set(triangle)) == 3:
            output.extend(triangle)
    return output


def _non_index_system_hash(system: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(system[:INDEX_OFFSET])
    digest.update(system[INDEX_OFFSET + INDEX_SIZE :])
    return digest.hexdigest()


def _draw_semantics(system: bytes) -> dict[str, int | bool]:
    if sha256_bytes(system[DRAW_OFFSET : DRAW_OFFSET + DRAW_SIZE]) != DRAW_SHA256:
        raise PatchError("target draw record identity drift")
    words = struct.unpack_from(">12I", system, DRAW_OFFSET)
    expected = (6, 0, 4, 2, 0, 0, 4, 0, 12, 0, 0, 1)
    if words != expected:
        raise PatchError("target draw semantic invariants drift")
    return {
        "draw_primitive_code": words[0],
        "first_element": words[1],
        "element_count": words[2],
        "primitive_capacity": words[3],
        "base_vertex": words[4],
        "minimum_vertex": words[5],
        "vertex_range": words[6],
        "optional_draw_state_is_null": words[7] == 0,
        "material_slot": words[8],
        "render_flags_2c": words[11],
    }


def _validate_output_scene(system: bytes, wanted_indices: list[int]) -> dict[str, Any]:
    scene = apf_scene.parse_scene_system_part(
        system, outer_index=container.OUTER_INDEX, inner_index=container.INNER_INDEX,
        capture_geometry=True,
    )
    if scene["root_name"] != container.INNER_NAME or scene["scene_node_count"] != 89:
        raise PatchError("output stadium SCNE envelope drift")
    node = scene["nodes"][container.NODE_INDEX]
    mesh = node["meshes"][0]
    if (
        node["name"] != container.NODE_NAME
        or node["draw_record_count"] != 1
        or node["index_component_bits"] != INDEX_BITS
        or node["index_count"] != INDEX_COUNT
        or node["index_offset"] != INDEX_OFFSET
        or mesh["vertex_count"] != 4
        or mesh["primitive_type"] != 5
        or mesh["stream_count"] != 1
        or mesh["streams"][0]["start"] != container.STREAM_START
        or mesh["streams"][0]["byte_length"] != container.STREAM_LENGTH
        or mesh["streams"][0]["sha256"] != container.STREAM_SHA256
    ):
        raise PatchError("output target structural identity drift")
    decoded = list(mesh["_geometry"]["indices"])
    if decoded != wanted_indices:
        raise PatchError("output native indices differ from recipe")
    triangles = expand_strip(decoded)
    if len(triangles) != 6:
        raise PatchError("output strip does not decode to exactly two triangles")
    return {"indices": decoded, "triangles": triangles, "draw": _draw_semantics(system)}


def build_patch(game_dir: Path, recipe_path: Path) -> tuple[bytes, dict[str, Any]]:
    recipe, recipe_raw, wanted_bytes = load_recipe(recipe_path)
    wanted_indices = list(struct.unpack(">4H", wanted_bytes))
    archive, entry = container._validate_archive(game_dir)
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        original_blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        original_stored = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]
    if sha256_bytes(original_entry) != container.OUTER_SHA256:
        raise PatchError("retail outer 14 identity drift")
    if (
        record.header_size != 292
        or record.file_length != container.SOURCE_FILE_LENGTH
        or record.block_count != 2
        or record.file_count != 9
    ):
        raise PatchError("retail IFF header identity drift")
    target = record.files[container.INNER_INDEX]
    if (
        target.name != container.INNER_NAME
        or target.file_id != container.INNER_FILE_ID
        or target.type_hash != container.INNER_TYPE_HASH
        or target.parts != (
            apf_inner.FilePart(0, 0, container.SYSTEM_LENGTH),
            apf_inner.FilePart(1, 0, container.VRAM_LENGTH),
        )
    ):
        raise PatchError("retail stadium part ownership drift")
    source_system = original_blocks[0][: container.SYSTEM_LENGTH]
    container._validate_scene(source_system)
    _draw_semantics(source_system)
    source_index = source_system[INDEX_OFFSET : INDEX_OFFSET + INDEX_SIZE]
    if sha256_bytes(source_index) != INDEX_SOURCE_SHA256:
        raise PatchError("retail node17 index allocation identity drift")
    if sha256_bytes(original_blocks[1][: container.VRAM_LENGTH]) != container.VRAM_SHA256:
        raise PatchError("retail stadium VRAM identity drift")

    mode = "no_op" if wanted_bytes == source_index else "changed"
    before_parts = container._part_hashes(record, original_blocks)
    if mode == "no_op":
        rebuilt_entry = original_entry
        rebuilt_blocks = original_blocks
        new_stored = original_stored
        new_file_length = record.file_length
        h7a_invoked = False
    else:
        new_block0 = bytearray(original_blocks[0])
        new_block0[INDEX_OFFSET : INDEX_OFFSET + INDEX_SIZE] = wanted_bytes
        if _non_index_system_hash(bytes(new_block0[: container.SYSTEM_LENGTH])) != _non_index_system_hash(source_system):
            raise PatchError("SCNE bytes outside index allocation changed before rebuild")
        rebuilt_entry, new_stored, new_file_length = container._rebuild_entry(
            original_entry, record, original_blocks, original_stored, bytes(new_block0)
        )
        memory = BytesReader(rebuilt_entry)
        rebuilt_record = apf_inner.parse_iff(memory, entry)
        rebuilt_blocks = [
            apf_inner.decode_block(memory, rebuilt_record, index, 1 << 30)
            for index in range(rebuilt_record.block_count)
        ]
        if rebuilt_blocks != [bytes(new_block0), original_blocks[1]]:
            raise PatchError("rebuilt IFF does not decode to intended blocks")
        record = rebuilt_record
        h7a_invoked = True

    output_system = rebuilt_blocks[0][: container.SYSTEM_LENGTH]
    decoded = _validate_output_scene(output_system, wanted_indices)
    if _non_index_system_hash(output_system) != _non_index_system_hash(source_system):
        raise PatchError("decoded output SCNE non-index bytes changed")
    for label, (offset, length, expected_hash) in container.TARGET_SPANS.items():
        if label == "index_buffer":
            continue
        if sha256_bytes(output_system[offset : offset + length]) != expected_hash:
            raise PatchError(f"decoded output structural span changed: {label}")

    after_parts = container._part_hashes(record, rebuilt_blocks)
    changed_parts = sorted(key for key in before_parts if before_parts[key] != after_parts[key])
    if changed_parts != ([] if mode == "no_op" else [(container.INNER_INDEX, 0)]):
        raise PatchError(f"inner part preservation failed: {changed_parts}")
    if len(before_parts) != 13:
        raise PatchError("retail part count drift")
    footer = rebuilt_entry[new_file_length : new_file_length + container.FOOTER_TOTAL]
    tail = rebuilt_entry[new_file_length + container.FOOTER_TOTAL :]
    if sha256_bytes(footer) != container.FOOTER_SHA256 or any(tail):
        raise PatchError("rebuilt footer/tail preservation failed")
    if new_stored[1] != original_stored[1]:
        raise PatchError("stored VRAM block changed")

    header_changed = [
        index for index, (before, after) in enumerate(
            zip(original_entry[: record.header_size], rebuilt_entry[: record.header_size])
        ) if before != after
    ]
    allowed_header = set(range(0x08, 0x0C)) | set(range(0x38, 0x3C)) | set(range(0x54, 0x58))
    if not set(header_changed).issubset(allowed_header):
        raise PatchError("IFF header change escapes mechanical length/start fields")
    before_header = bytearray(original_entry[: record.header_size])
    after_header = bytearray(rebuilt_entry[: record.header_size])
    for offset in allowed_header:
        before_header[offset] = 0
        after_header[offset] = 0
    if before_header != after_header:
        raise PatchError("IFF header complement differs")

    changed_decoded = [
        index for index, (before, after) in enumerate(zip(original_blocks[0], rebuilt_blocks[0]))
        if before != after
    ]
    if not set(changed_decoded).issubset(range(INDEX_OFFSET, INDEX_OFFSET + INDEX_SIZE)):
        raise PatchError("changed decoded DRAM byte escapes eight-byte index allocation")

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "mode": mode,
        "recipe": {
            "schema": recipe["schema"],
            "sha256": sha256_bytes(recipe_raw),
            "index_count": INDEX_COUNT,
            "native_primitive": "D3DPT_TRIANGLESTRIP",
        },
        "source": {
            "game": "All-Pro Football 2K8 Xbox 360 USA retail",
            "packs": [
                {"name": name, "size_bytes": size, "sha256": digest}
                for name, (size, digest) in container.SOURCE_PACKS.items()
            ],
            "outer_entry_sha256": container.OUTER_SHA256,
            "stadium_dram_sha256": container.SYSTEM_SHA256,
            "stadium_vram_sha256": container.VRAM_SHA256,
            "index_buffer_sha256": INDEX_SOURCE_SHA256,
        },
        "target": {
            "outer_table_index": container.OUTER_INDEX,
            "physical_pack": OUTPUT_PACK_NAME,
            "fixed_outer_allocation_bytes": container.OUTER_LENGTH,
            "inner_file_index": container.INNER_INDEX,
            "inner_name": container.INNER_NAME,
            "node_index": container.NODE_INDEX,
            "node_name": container.NODE_NAME,
            "vertex_count": 4,
            "index_component_bits": INDEX_BITS,
            "index_count": INDEX_COUNT,
            "index_buffer_offset": INDEX_OFFSET,
            "index_allocation_bytes": INDEX_SIZE,
            "draw_record_offset": DRAW_OFFSET,
            "draw_record_sha256": DRAW_SHA256,
        },
        "result": {
            "output_directory_contract": [OUTPUT_PACK_NAME, MANIFEST_NAME],
            "output_pack_name": OUTPUT_PACK_NAME,
            "output_pack_size_bytes": container.SOURCE_PACKS["1A"][0],
            "output_pack_sha256": None,
            "outer_entry_sha256": sha256_bytes(rebuilt_entry),
            "stadium_dram_sha256": sha256_bytes(output_system),
            "stadium_vram_sha256": sha256_bytes(rebuilt_blocks[1][: container.VRAM_LENGTH]),
            "index_buffer_sha256": sha256_bytes(wanted_bytes),
            "changed_decoded_dram_byte_count": len(changed_decoded),
            "changed_inner_parts": [
                {"file_index": file_index, "part_index": part_index}
                for file_index, part_index in changed_parts
            ],
            "native_triangle_count": len(decoded["triangles"]) // 3,
            "native_degenerate_triangle_count": 0,
            "h7a_block0_recompressed": h7a_invoked,
            "h7a_block0_shift": 12,
            "block0_stored_length_before": len(original_stored[0]),
            "block0_stored_length_after": len(new_stored[0]),
            "block1_stored_sha256": sha256_bytes(new_stored[1]),
            "file_length_before": container.SOURCE_FILE_LENGTH,
            "file_length_after": new_file_length,
            "allocation_slack_after_bytes": len(tail),
        },
        "preservation": {
            "scne_non_index_sha256": _non_index_system_hash(output_system),
            "draw_semantics": decoded["draw"],
            "draw_record_exact": True,
            "vertex_stream_exact": True,
            "declarations_and_descriptor_exact": True,
            "matrix_hierarchy_and_node_exact": True,
            "stadium_vram_exact": True,
            "sibling_part_count": 11,
            "non_target_part_count": 12,
            "all_non_target_parts_exact": True,
            "block1_stored_exact": True,
            "footer_sha256": sha256_bytes(footer),
            "footer_exact": True,
            "iff_header_complement_exact": True,
            "file_descriptor_table_exact": True,
            "outer_length_exact": len(rebuilt_entry) == container.OUTER_LENGTH,
            "outer_tail_zero_and_bounded": True,
            "source_files_rechecked_after_write": False,
            "output_pack_prefix_sha256": None,
            "output_pack_suffix_sha256": None,
        },
        "claims": {
            "offline_same_footprint_topology_writeback_proved": True,
            "changed_count_proved": False,
            "material_or_vertex_authoring_proved": False,
            "emulator_runtime_visibility_proved": False,
            "xbox_360_hardware_proved": False,
            "production_mesh_importer_proved": False,
        },
        "contains_replacement_bytes": False,
    }
    return rebuilt_entry, manifest


def write_output(game_dir: Path, recipe_path: Path, output_dir: Path) -> dict[str, Any]:
    raw_game_dir = game_dir.expanduser()
    if not raw_game_dir.is_absolute():
        raw_game_dir = Path.cwd() / raw_game_dir
    raw_game_dir = Path(os.path.normpath(raw_game_dir))
    game_metadata = os.lstat(raw_game_dir)
    if stat.S_ISLNK(game_metadata.st_mode) or not stat.S_ISDIR(game_metadata.st_mode):
        raise PatchError("source game directory must be a real non-symlink directory")
    game_dir = raw_game_dir.resolve(strict=True)
    if game_dir != raw_game_dir.absolute():
        raise PatchError("source game directory path contains a symlink")

    raw_recipe = recipe_path.expanduser()
    if not raw_recipe.is_absolute():
        raw_recipe = Path.cwd() / raw_recipe
    raw_recipe = Path(os.path.normpath(raw_recipe))
    recipe_metadata = os.lstat(raw_recipe)
    if stat.S_ISLNK(recipe_metadata.st_mode) or not stat.S_ISREG(recipe_metadata.st_mode) or recipe_metadata.st_size > MAX_RECIPE_BYTES:
        raise PatchError("recipe must be a bounded regular non-symlink file")
    recipe_path = raw_recipe.resolve(strict=True)
    if recipe_path != raw_recipe.absolute():
        raise PatchError("recipe path contains a symlink")

    requested_output = output_dir.expanduser()
    if not requested_output.is_absolute():
        requested_output = Path.cwd() / requested_output
    requested_output = Path(os.path.normpath(requested_output))
    parent = requested_output.parent
    parent_metadata = os.lstat(parent)
    if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(parent_metadata.st_mode):
        raise PatchError("output parent must be a real directory, not a symlink")
    resolved_parent = parent.resolve(strict=True)
    if resolved_parent != parent.absolute():
        raise PatchError("output parent path contains a symlink")
    output_dir = resolved_parent / requested_output.name
    try:
        output_dir.relative_to(game_dir)
    except ValueError:
        pass
    else:
        raise PatchError("output directory must not be inside source game directory")
    if os.path.lexists(output_dir):
        raise PatchError("refusing existing output directory")

    source_before, source_inodes = container._source_file_identities(game_dir)
    rebuilt_entry, manifest = build_patch(game_dir, recipe_path)
    os.mkdir(output_dir, 0o755)
    created = os.lstat(output_dir)
    directory_identity = (created.st_dev, created.st_ino)
    directory_fd = os.open(
        output_dir,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    opened = os.fstat(directory_fd)
    if (opened.st_dev, opened.st_ino) != directory_identity or not container._directory_path_matches(output_dir, directory_identity):
        os.close(directory_fd)
        raise PatchError("reserved output directory pathname changed during open")
    owned: dict[str, tuple[int, int]] = {}
    try:
        output_descriptor, output_identity = container._copy_new_at(
            game_dir / OUTPUT_PACK_NAME,
            directory_fd,
            OUTPUT_PACK_NAME,
            source_inodes["1A"],
            container.SOURCE_PACKS["1A"][1],
        )
        owned[OUTPUT_PACK_NAME] = output_identity
        try:
            written = 0
            while written < len(rebuilt_entry):
                count = os.pwrite(output_descriptor, rebuilt_entry[written:], container.OUTER_PACK_OFFSET + written)
                if count <= 0:
                    raise PatchError("short outer-entry write")
                written += count
            os.fsync(output_descriptor)
            if os.fstat(output_descriptor).st_size != container.SOURCE_PACKS["1A"][0]:
                raise PatchError("output 1A length changed")
            manifest["result"]["output_pack_sha256"] = container.sha256_fd(output_descriptor)
            manifest["preservation"]["output_pack_prefix_sha256"] = container.sha256_fd_range(
                output_descriptor, 0, container.OUTER_PACK_OFFSET
            )
            suffix_offset = container.OUTER_PACK_OFFSET + container.OUTER_LENGTH
            manifest["preservation"]["output_pack_suffix_sha256"] = container.sha256_fd_range(
                output_descriptor, suffix_offset, os.fstat(output_descriptor).st_size - suffix_offset
            )
            if (
                manifest["preservation"]["output_pack_prefix_sha256"] != container.SOURCE_PREFIX_SHA256
                or manifest["preservation"]["output_pack_suffix_sha256"] != container.SOURCE_SUFFIX_SHA256
            ):
                raise PatchError("output 1A complement outside outer 14 differs")
            if manifest["mode"] == "no_op":
                if manifest["result"]["output_pack_sha256"] != container.SOURCE_PACKS["1A"][1]:
                    raise PatchError("no-op output 1A is not byte-identical")
        finally:
            os.close(output_descriptor)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = write_output(args.game_dir, args.recipe, args.output_dir)
        print(
            "APF_SCNE_NODE17_TOPOLOGY_PATCH_PASS "
            f"mode={manifest['mode']} indices=4 triangles=2 copied_pack=1A "
            f"outer_sha256={manifest['result']['outer_entry_sha256']} "
            f"output_pack_sha256={manifest['result']['output_pack_sha256']} "
            "runtime=false hardware=false"
        )
        return 0
    except (
        PatchError,
        container.PatchError,
        apf_outer.FormatError,
        apf_inner.FormatError,
        apf_scene.SceneError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
