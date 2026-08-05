#!/usr/bin/env python3
"""Fail-closed APF 2K8 same-count static-candidate POSITION0 writer.

The only supported target is retail outer 14 / inner 8 ``stadium`` / node 17
``polySurface19930``.  The source is a complete four-pack game directory; the
tool creates a new output directory containing only a copied ``1A`` and a
hash-only manifest.  It never writes a source pack and never copies unrelated
packs.  No-op recipes bypass H7A/IFF rebuilding and preserve the copied 1A
byte-for-byte.
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

_TOOLS = str(Path(__file__).resolve().parent)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import apf_inner
import apf_outer
import apf_scene
from apf_texture_patch import compress_h7a, compress_h7a_best


RECIPE_SCHEMA = "apf2k8_scne_same_count_position_recipe/v1"
MANIFEST_SCHEMA = "apf2k8_scne_same_count_position_patch/v1"
RECIPE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "reports/specs/apf2k8_scne_same_count_position_recipe.schema.json"
RECIPE_SCHEMA_SIZE = 4_064
RECIPE_SCHEMA_SHA256 = "8094a4a64325728082091e87ba3fcd0e5ed30c8c6f06f1e7074934720438af51"
MANIFEST_NAME = "apf2k8_scne_same_count_position_manifest.json"
OUTPUT_PACK_NAME = "1A"

SOURCE_PACKS = {
    "0A": (1_140_850_688, "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"),
    "0B": (1_073_838_080, "775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53"),
    "1A": (1_140_850_688, "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb"),
    "1B": (517_971_968, "04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084"),
}

OUTER_INDEX = 14
OUTER_NAME_ID = 0x02BAE370
OUTER_PACK_OFFSET = 404_643_840
OUTER_LENGTH = 12_931_072
OUTER_SHA256 = "347503ffdcd910b57425584869e1520238b1298e516f643936568b83d5a5a07a"
INNER_INDEX = 8
INNER_NAME = "stadium"
INNER_FILE_ID = 0xE604044F
INNER_TYPE_HASH = 0xE26C9B5D
SYSTEM_LENGTH = 4_199_168
SYSTEM_SHA256 = "b3028883de8d71d90850bab68ba29b91badd7107f8f9fbfab132a19a818379e4"
VRAM_LENGTH = 12_918_784
VRAM_SHA256 = "5662f3866f83e33bab217f80ac8e9a6267ae94842c0727f77019355cc2cb3a95"
NODE_INDEX = 17
NODE_NAME = "polySurface19930"
NODE_NAME_CRC32 = 0xB13B08B6
VERTEX_COUNT = 4
STREAM_STRIDE = 24
POSITION_SIZE = 12
POSITION_FORMAT = 0x002A23B9

TARGET_SPANS = {
    "matrix_table": (38_912, 5_696, "5fa0a6f9aa4444ad14676e989a521963d32e1693559f288202ac1bb3b81d8828"),
    "node_record": (26_240, 176, "24f8b734350d0447879ae0fd2899794fbcd3cc455ddbe064ad1da9dbce4ef428"),
    "hierarchy": (375_664, 48, "21df6a8e4e475144de905a555bad3799c61f10ee3a233f8d05d51025f3c8067a"),
    "draw_record": (375_712, 48, "161a2e06c0b875b6679423f490c2c89691d1da9899003768a0f4eac01cfe873f"),
    "index_buffer": (375_760, 8, "96b383ee0d221556a56277315db425256549a46ccc5217a392181783327a6dc5"),
    "declarations": (375_808, 192, "e105cd8c86a82b60e0bd65cd432bda0433d384a7ed08587b56baaa233bba9066"),
    "mesh_descriptor": (376_000, 44, "1de69481e216149b692fd64f0264ba5750903e02d99c63ab9082afc10a3d88be"),
}
STREAM_START = 376_044
STREAM_LENGTH = 96
STREAM_SHA256 = "86f3c7a4cc3d5c46d9bcfcf48bd465e96f954ce1a3e764e20c595633e70264eb"
FOOTER_TOTAL = 954
FOOTER_SHA256 = "a115b9c25fda962a1a60573a2d10beff9990a8007f60b78f8b497dfd2486114b"
SOURCE_FILE_LENGTH = 12_928_092
SOURCE_TAIL_LENGTH = 2_026
SOURCE_PREFIX_SHA256 = "a9cff61c985cfa8e29ee10cd4e1b653eecd7f49de0a6b979b59e943a0d27a906"
SOURCE_SUFFIX_SHA256 = "fad57e63688614c87bd02d68100871615bc18a50c630b1aa10f44e1448cc77fb"
MAX_RECIPE_BYTES = 1024 * 1024

RECIPE_CONSTANTS = {
    "schema": RECIPE_SCHEMA,
    "operation": "replace_exact_same_count_position0",
    "game": {"title": "All-Pro Football 2K8", "platform": "Xbox 360"},
    "source_contract": {
        "index_pack": "0A",
        "physical_pack": "1A",
        "index_sha256": SOURCE_PACKS["0A"][1],
        "physical_pack_sha256": SOURCE_PACKS["1A"][1],
    },
    "target": {
        "outer_table_index": OUTER_INDEX,
        "outer_name_id": "0x02bae370",
        "inner_file_index": INNER_INDEX,
        "inner_name": INNER_NAME,
        "inner_file_id": "0xe604044f",
        "inner_type": "SCNE",
        "node_index": NODE_INDEX,
        "node_name": NODE_NAME,
        "node_name_crc32": "0xb13b08b6",
        "vertex_count": VERTEX_COUNT,
        "stream_index": 0,
        "stream_stride_bytes": STREAM_STRIDE,
        "position_byte_offset": 0,
        "position_format_code": "0x002a23b9",
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
    """The recipe, source fixture, or preservation proof failed closed."""


class BytesReader:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise apf_inner.FormatError("memory entry read is out of bounds")
        return self.data[offset : offset + size]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_range(path: Path, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        remaining = size
        while remaining:
            chunk = stream.read(min(8 * 1024 * 1024, remaining))
            if not chunk:
                raise PatchError("short read while hashing range")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def sha256_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    size = os.fstat(descriptor).st_size
    while offset < size:
        chunk = os.pread(descriptor, min(8 * 1024 * 1024, size - offset), offset)
        if not chunk:
            raise PatchError("short descriptor read while hashing")
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def sha256_fd_range(descriptor: int, offset: int, size: int) -> str:
    if offset < 0 or size < 0 or offset + size > os.fstat(descriptor).st_size:
        raise PatchError("descriptor hash range is out of bounds")
    digest = hashlib.sha256()
    cursor = offset
    remaining = size
    while remaining:
        chunk = os.pread(descriptor, min(8 * 1024 * 1024, remaining), cursor)
        if not chunk:
            raise PatchError("short descriptor range read")
        digest.update(chunk)
        cursor += len(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


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
        value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PatchError(f"invalid recipe JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PatchError("recipe top level must be an object")
    if raw != canonical_json_bytes(value):
        raise PatchError("recipe must be canonical sorted UTF-8 JSON")
    return value, raw


def _schema_document() -> dict[str, Any]:
    if RECIPE_SCHEMA_PATH.stat().st_size != RECIPE_SCHEMA_SIZE or sha256_file(RECIPE_SCHEMA_PATH) != RECIPE_SCHEMA_SHA256:
        raise PatchError("recipe schema identity drift")
    value = json.loads(RECIPE_SCHEMA_PATH.read_bytes())
    if not isinstance(value, dict):
        raise PatchError("recipe schema is not an object")
    return value


def load_recipe(path: Path) -> tuple[dict[str, Any], bytes, bytes]:
    recipe, raw = _strict_json(path)
    schema = _schema_document()
    if schema.get("$id") != RECIPE_SCHEMA:
        raise PatchError("recipe schema ID drift")
    if set(recipe) != set(RECIPE_CONSTANTS) | {"positions"}:
        raise PatchError("recipe top-level key set differs")
    for key, expected in RECIPE_CONSTANTS.items():
        if recipe.get(key) != expected:
            raise PatchError(f"recipe constant-pinned field differs: {key}")
    positions = recipe.get("positions")
    if not isinstance(positions, list) or len(positions) != VERTEX_COUNT:
        raise PatchError("recipe must contain exactly four positions")
    encoded = bytearray()
    for vertex, position in enumerate(positions):
        if not isinstance(position, list) or len(position) != 3:
            raise PatchError(f"position {vertex} is not FLOAT3")
        values: list[float] = []
        for component, value in enumerate(position):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise PatchError(f"position {vertex} component {component} is not finite numeric data")
            values.append(float(value))
        try:
            packed = struct.pack(">3f", *values)
        except (OverflowError, struct.error) as exc:
            raise PatchError(f"position {vertex} is outside FLOAT32 range") from exc
        roundtrip = struct.unpack(">3f", packed)
        if tuple(values) != roundtrip:
            raise PatchError(f"position {vertex} is not exactly representable as FLOAT32")
        encoded.extend(packed)
    return recipe, raw, bytes(encoded)


def patch_interleaved_stream(source: bytes, packed_positions: bytes) -> bytes:
    if len(source) != STREAM_LENGTH:
        raise PatchError("target stream length drift")
    if len(packed_positions) != VERTEX_COUNT * POSITION_SIZE:
        raise PatchError("packed position payload length drift")
    output = bytearray(source)
    for vertex in range(VERTEX_COUNT):
        destination = vertex * STREAM_STRIDE
        source_offset = vertex * POSITION_SIZE
        output[destination : destination + POSITION_SIZE] = packed_positions[
            source_offset : source_offset + POSITION_SIZE
        ]
    for vertex in range(VERTEX_COUNT):
        start = vertex * STREAM_STRIDE
        if output[start + POSITION_SIZE : start + STREAM_STRIDE] != source[start + POSITION_SIZE : start + STREAM_STRIDE]:
            raise PatchError("UV/normal interleave changed")
    return bytes(output)


def _position_payload(stream: bytes) -> bytes:
    return b"".join(
        stream[vertex * STREAM_STRIDE : vertex * STREAM_STRIDE + POSITION_SIZE]
        for vertex in range(VERTEX_COUNT)
    )


def _non_position_system_hash(system: bytes) -> str:
    digest = hashlib.sha256()
    cursor = 0
    for vertex in range(VERTEX_COUNT):
        lane = STREAM_START + vertex * STREAM_STRIDE
        digest.update(system[cursor:lane])
        cursor = lane + POSITION_SIZE
    digest.update(system[cursor:])
    return digest.hexdigest()


def _interleave_hashes(stream: bytes) -> dict[str, str]:
    return {
        "uv_float16x4": sha256_bytes(b"".join(stream[i * 24 + 12 : i * 24 + 20] for i in range(4))),
        "normal_snorm10_10_10": sha256_bytes(b"".join(stream[i * 24 + 20 : i * 24 + 24] for i in range(4))),
    }


def _part_hashes(record: apf_inner.IFFRecord, blocks: list[bytes]) -> dict[tuple[int, int], str]:
    result: dict[tuple[int, int], str] = {}
    for file in record.files:
        for part_index, part in enumerate(file.parts):
            result[(file.index, part_index)] = sha256_bytes(
                blocks[part.block_index][part.offset : part.offset + part.length]
            )
    return result


def _source_file_identities(
    game_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, tuple[int, int]]]:
    identities: list[dict[str, Any]] = []
    inodes: dict[str, tuple[int, int]] = {}
    for name, (size, expected_hash) in SOURCE_PACKS.items():
        path = game_dir / name
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise PatchError(f"cannot lstat source pack {name}: {exc}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_size != size:
            raise PatchError(f"source pack identity differs: {name}")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        try:
            descriptor_metadata = os.fstat(descriptor)
            identity = (descriptor_metadata.st_dev, descriptor_metadata.st_ino)
            if identity != (metadata.st_dev, metadata.st_ino) or not stat.S_ISREG(descriptor_metadata.st_mode) or descriptor_metadata.st_size != size:
                raise PatchError(f"source pack pathname changed during open: {name}")
            actual_hash = sha256_fd(descriptor)
            final_metadata = os.lstat(path)
            if (final_metadata.st_dev, final_metadata.st_ino) != identity:
                raise PatchError(f"source pack pathname changed during hash: {name}")
        finally:
            os.close(descriptor)
        if actual_hash != expected_hash:
            raise PatchError(f"source pack SHA-256 differs: {name}")
        identities.append({"name": name, "size_bytes": size, "sha256": actual_hash})
        inodes[name] = identity
    return identities, inodes


def _validate_archive(game_dir: Path) -> tuple[apf_outer.Archive, apf_outer.Entry]:
    archive = apf_outer.parse_archive(game_dir / "0A")
    if [pack.name for pack in archive.packs] != list(SOURCE_PACKS):
        raise PatchError("outer archive pack list drift")
    if len(archive.entries) <= OUTER_INDEX:
        raise PatchError("outer archive has no target entry")
    entry = archive.entries[OUTER_INDEX]
    expected = (
        entry.name_id == OUTER_NAME_ID
        and entry.size == OUTER_LENGTH
        and len(entry.segments) == 1
        and entry.segments[0].pack_name == OUTPUT_PACK_NAME
        and entry.segments[0].pack_offset == OUTER_PACK_OFFSET
        and entry.segments[0].size == OUTER_LENGTH
    )
    if not expected:
        raise PatchError("outer 14 routing/allocation drift")
    return archive, entry


def _validate_scene(system: bytes) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if len(system) != SYSTEM_LENGTH or sha256_bytes(system) != SYSTEM_SHA256:
        raise PatchError("retail stadium DRAM identity drift")
    scene = apf_scene.parse_scene_system_part(system, outer_index=OUTER_INDEX, inner_index=INNER_INDEX, capture_geometry=True)
    if scene["root_name"] != INNER_NAME or scene["scene_node_count"] != 89:
        raise PatchError("stadium SCNE envelope drift")
    node = scene["nodes"][NODE_INDEX]
    if (
        node["index"] != NODE_INDEX
        or node["name"] != NODE_NAME
        or node["name_crc32"] != "0xb13b08b6"
        or node["hierarchy"]["count"] != 1
        or node["draw_record_count"] != 1
        or node["mesh_descriptor_count"] != 1
        or node["index_component_bits"] != 16
        or node["index_count"] != 4
    ):
        raise PatchError("target node structural identity drift")
    semantics = [item["indexed_semantic"] for item in node["vertex_declarations"]]
    if semantics != ["POSITION0", "TEXCOORD0", "NORMAL0"] or any(
        semantic and (semantic.startswith("BLENDINDICES") or semantic.startswith("BLENDWEIGHT"))
        for semantic in semantics
    ):
        raise PatchError("target static-candidate declaration identity drift")
    position_decl = node["vertex_declarations"][0]
    mesh = node["meshes"][0]
    stream = mesh["streams"][0]
    if (
        position_decl["format_code"] != "0x002a23b9"
        or position_decl["stream_index"] != 0
        or position_decl["byte_offset"] != 0
        or mesh["vertex_count"] != VERTEX_COUNT
        or mesh["stream_count"] != 1
        or mesh["primitive_type"] != 5
        or stream["stride"] != STREAM_STRIDE
        or stream["byte_length"] != STREAM_LENGTH
        or stream["start"] != STREAM_START
        or stream["end"] != STREAM_START + STREAM_LENGTH
        or stream["sha256"] != STREAM_SHA256
    ):
        raise PatchError("target POSITION0 stream identity drift")
    for label, (offset, length, expected_hash) in TARGET_SPANS.items():
        if sha256_bytes(system[offset : offset + length]) != expected_hash:
            raise PatchError(f"target structural span drift: {label}")
    return scene, node, mesh


def _rebuild_entry(
    original_entry: bytes,
    record: apf_inner.IFFRecord,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    new_block0: bytes,
) -> tuple[bytes, list[bytes], int]:
    descriptor = record.blocks[0]
    if not descriptor.is_compressed or descriptor.wrapper is None or descriptor.wrapper.shift != 12:
        raise PatchError("target DRAM H7A profile drift")
    compressed = compress_h7a(new_block0, 12)
    greedy_active_length = (
        record.header_size
        + apf_inner.H7A_HEADER_SIZE
        + len(compressed)
        + len(original_stored[1])
        + FOOTER_TOTAL
    )
    if greedy_active_length > OUTER_LENGTH:
        compressed = compress_h7a_best(new_block0, 12, greedy=compressed)
    if apf_inner.decompress_h7a(compressed, len(new_block0), 12) != new_block0:
        raise PatchError("H7A encode/decode round-trip failed")
    new_stored = list(original_stored)
    new_stored[0] = struct.pack(">5I", apf_inner.H7A_MAGIC, len(new_block0), apf_inner.H7A_HEADER_SIZE + len(compressed), descriptor.unknown_10, 12) + compressed
    if new_stored[1] != original_stored[1]:
        raise PatchError("VRAM stored block changed before rebuild")

    header = bytearray(original_entry[: record.header_size])
    body = bytearray()
    cursor = record.header_size
    for index, (old, stored) in enumerate(zip(record.blocks, new_stored)):
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            old.name_hash,
            old.type_hash,
            old.unknown_08,
            old.uncompressed_length,
            old.unknown_10,
            cursor,
            len(stored),
            old.indexed,
        )
        body.extend(stored)
        cursor += len(stored)
    new_file_length = record.header_size + len(body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    footer = original_entry[record.file_length : record.file_length + FOOTER_TOTAL]
    if len(footer) != FOOTER_TOTAL or sha256_bytes(footer) != FOOTER_SHA256:
        raise PatchError("retail name footer identity drift")
    old_tail = original_entry[record.file_length + FOOTER_TOTAL :]
    if len(old_tail) != SOURCE_TAIL_LENGTH or any(old_tail):
        raise PatchError("retail outer allocation tail drift")
    active = bytes(header) + bytes(body) + footer
    if len(active) > OUTER_LENGTH:
        raise PatchError(f"rebuilt IFF exceeds fixed outer allocation by {len(active) - OUTER_LENGTH} bytes")
    return active + bytes(OUTER_LENGTH - len(active)), new_stored, new_file_length


def build_patch(game_dir: Path, recipe_path: Path) -> tuple[bytes, dict[str, Any]]:
    recipe, recipe_raw, packed_positions = load_recipe(recipe_path)
    archive, entry = _validate_archive(game_dir)
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        original_blocks = [apf_inner.decode_block(reader, record, index, 1 << 30) for index in range(record.block_count)]
        original_stored = [reader.read(entry, block.start_offset, block.stored_length) for block in record.blocks]
    if sha256_bytes(original_entry) != OUTER_SHA256:
        raise PatchError("retail outer 14 identity drift")
    if record.header_size != 292 or record.file_length != SOURCE_FILE_LENGTH or record.block_count != 2 or record.file_count != 9:
        raise PatchError("retail IFF header identity drift")
    if len(record.files) != 9 or record.files[INNER_INDEX].name != INNER_NAME or record.files[INNER_INDEX].file_id != INNER_FILE_ID or record.files[INNER_INDEX].type_hash != INNER_TYPE_HASH:
        raise PatchError("retail inner stadium identity drift")
    target = record.files[INNER_INDEX]
    if len(target.parts) != 2 or target.parts[0] != apf_inner.FilePart(0, 0, SYSTEM_LENGTH) or target.parts[1] != apf_inner.FilePart(1, 0, VRAM_LENGTH):
        raise PatchError("retail stadium part ownership drift")
    if sha256_bytes(original_blocks[1][:VRAM_LENGTH]) != VRAM_SHA256:
        raise PatchError("retail stadium VRAM identity drift")
    _validate_scene(original_blocks[0][:SYSTEM_LENGTH])

    original_stream = original_blocks[0][STREAM_START : STREAM_START + STREAM_LENGTH]
    wanted_stream = patch_interleaved_stream(original_stream, packed_positions)
    source_positions = _position_payload(original_stream)
    wanted_positions = _position_payload(wanted_stream)
    mode = "no_op" if wanted_positions == source_positions else "changed"
    before_parts = _part_hashes(record, original_blocks)

    if mode == "no_op":
        rebuilt_entry = original_entry
        rebuilt_blocks = original_blocks
        new_stored = original_stored
        new_file_length = record.file_length
        h7a_invoked = False
    else:
        new_block0 = bytearray(original_blocks[0])
        new_block0[STREAM_START : STREAM_START + STREAM_LENGTH] = wanted_stream
        if _non_position_system_hash(bytes(new_block0[:SYSTEM_LENGTH])) != _non_position_system_hash(original_blocks[0][:SYSTEM_LENGTH]):
            raise PatchError("SCNE bytes outside POSITION lanes changed")
        rebuilt_entry, new_stored, new_file_length = _rebuild_entry(
            original_entry, record, original_blocks, original_stored, bytes(new_block0)
        )
        memory = BytesReader(rebuilt_entry)
        rebuilt_record = apf_inner.parse_iff(memory, entry)
        rebuilt_blocks = [apf_inner.decode_block(memory, rebuilt_record, index, 1 << 30) for index in range(rebuilt_record.block_count)]
        if rebuilt_blocks != [bytes(new_block0), original_blocks[1]]:
            raise PatchError("rebuilt IFF does not decode to intended blocks")
        record = rebuilt_record
        h7a_invoked = True

    output_system = rebuilt_blocks[0][:SYSTEM_LENGTH]
    output_stream = output_system[STREAM_START : STREAM_START + STREAM_LENGTH]
    if _position_payload(output_stream) != wanted_positions:
        raise PatchError("decoded output positions differ from recipe")
    if _interleave_hashes(output_stream) != _interleave_hashes(original_stream):
        raise PatchError("decoded output UV/normal interleaves changed")
    if _non_position_system_hash(output_system) != _non_position_system_hash(original_blocks[0][:SYSTEM_LENGTH]):
        raise PatchError("decoded output SCNE non-position bytes changed")
    for label, (offset, length, expected_hash) in TARGET_SPANS.items():
        if sha256_bytes(output_system[offset : offset + length]) != expected_hash:
            raise PatchError(f"decoded output structural span changed: {label}")

    after_parts = _part_hashes(record, rebuilt_blocks)
    changed_parts = sorted(key for key in before_parts if before_parts[key] != after_parts[key])
    expected_changed_parts = [] if mode == "no_op" else [(INNER_INDEX, 0)]
    if changed_parts != expected_changed_parts:
        raise PatchError(f"inner part preservation failed: {changed_parts}")
    if len(before_parts) != 13:
        raise PatchError("retail part count drift")
    footer = rebuilt_entry[new_file_length : new_file_length + FOOTER_TOTAL]
    tail = rebuilt_entry[new_file_length + FOOTER_TOTAL :]
    if sha256_bytes(footer) != FOOTER_SHA256 or any(tail):
        raise PatchError("rebuilt footer/tail preservation failed")
    if new_stored[1] != original_stored[1]:
        raise PatchError("stored VRAM block changed")

    header_changed_offsets = [
        index
        for index, (before, after) in enumerate(
            zip(original_entry[: record.header_size], rebuilt_entry[: record.header_size])
        )
        if before != after
    ]
    allowed_header_offsets = set(range(0x08, 0x0C)) | set(range(0x38, 0x3C)) | set(range(0x54, 0x58))
    if not set(header_changed_offsets).issubset(allowed_header_offsets):
        raise PatchError("rebuilt IFF header change escapes mechanical length/start fields")
    source_header_normalized = bytearray(original_entry[: record.header_size])
    output_header_normalized = bytearray(rebuilt_entry[: record.header_size])
    for offset in allowed_header_offsets:
        source_header_normalized[offset] = 0
        output_header_normalized[offset] = 0
    if output_header_normalized != source_header_normalized:
        raise PatchError("rebuilt IFF header complement differs")

    changed_decoded_offsets = [
        index for index, (before, after) in enumerate(zip(original_blocks[0], rebuilt_blocks[0])) if before != after
    ]
    allowed_offsets = {
        STREAM_START + vertex * STREAM_STRIDE + byte
        for vertex in range(VERTEX_COUNT)
        for byte in range(POSITION_SIZE)
    }
    if not set(changed_decoded_offsets).issubset(allowed_offsets):
        raise PatchError("changed decoded DRAM byte escapes approved POSITION lanes")

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "mode": mode,
        "recipe": {
            "schema": recipe["schema"],
            "sha256": sha256_bytes(recipe_raw),
            "authored_position_count": 4,
            "coordinate_space": recipe["coordinate_space"],
            "vertex_order": recipe["vertex_order"],
            "position_type": recipe["position_type"],
        },
        "source": {
            "game": "All-Pro Football 2K8 Xbox 360 USA retail",
            "packs": [{"name": name, "size_bytes": size, "sha256": digest} for name, (size, digest) in SOURCE_PACKS.items()],
            "outer_entry_sha256": OUTER_SHA256,
            "stadium_dram_sha256": SYSTEM_SHA256,
            "stadium_vram_sha256": VRAM_SHA256,
            "position_payload_sha256": sha256_bytes(source_positions),
        },
        "target": {
            "outer_table_index": OUTER_INDEX,
            "physical_pack": OUTPUT_PACK_NAME,
            "fixed_outer_allocation_bytes": OUTER_LENGTH,
            "inner_file_index": INNER_INDEX,
            "inner_name": INNER_NAME,
            "node_index": NODE_INDEX,
            "node_name": NODE_NAME,
            "vertex_count": VERTEX_COUNT,
            "stream_stride_bytes": STREAM_STRIDE,
            "position_lane_bytes_per_vertex": POSITION_SIZE,
            "approved_position_lane_bytes": VERTEX_COUNT * POSITION_SIZE,
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
            "position_payload_sha256": sha256_bytes(wanted_positions),
            "changed_decoded_dram_byte_count": len(changed_decoded_offsets),
            "changed_inner_parts": [{"file_index": file_index, "part_index": part_index} for file_index, part_index in changed_parts],
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
            "uv_normal_interleaves": _interleave_hashes(output_stream),
            "scne_non_position_sha256": _non_position_system_hash(output_system),
            "structural_spans": {label: expected_hash for label, (_, _, expected_hash) in TARGET_SPANS.items()},
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


def copy_claims() -> dict[str, bool]:
    return {
        "offline_structural_write_back_proved": True,
        "same_count_position_only": True,
        "changed_topology_proved": False,
        "rigid_attachment_proved": False,
        "material_or_uv_authoring_proved": False,
        "skin_authoring_proved": False,
        "emulator_runtime_visibility_proved": False,
        "xbox_360_hardware_proved": False,
        "production_mesh_importer_proved": False,
    }


def _path_matches_at(directory_fd: int, name: str, identity: tuple[int, int]) -> bool:
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and (metadata.st_dev, metadata.st_ino) == identity


def _unlink_owned_at(directory_fd: int, name: str, identity: tuple[int, int]) -> bool:
    if not _path_matches_at(directory_fd, name, identity):
        return False
    try:
        os.unlink(name, dir_fd=directory_fd)
    except OSError:
        return False
    return True


def _copy_new_at(
    source: Path,
    directory_fd: int,
    name: str,
    expected_source_identity: tuple[int, int],
    expected_source_sha256: str,
) -> tuple[int, tuple[int, int]]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(name, flags, 0o644, dir_fd=directory_fd)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        source_descriptor = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            source_metadata = os.fstat(source_descriptor)
            if (
                (source_metadata.st_dev, source_metadata.st_ino) != expected_source_identity
                or not stat.S_ISREG(source_metadata.st_mode)
                or source_metadata.st_size != SOURCE_PACKS["1A"][0]
                or sha256_fd(source_descriptor) != expected_source_sha256
            ):
                raise PatchError("source 1A descriptor identity changed before copy")
            if (os.fstat(source_descriptor).st_dev, os.fstat(source_descriptor).st_ino) == (
                os.fstat(descriptor).st_dev,
                os.fstat(descriptor).st_ino,
            ):
                raise PatchError("output 1A aliases source 1A")
            while True:
                chunk = os.read(source_descriptor, 16 * 1024 * 1024)
                if not chunk:
                    break
                written = 0
                while written < len(chunk):
                    count = os.write(descriptor, chunk[written:])
                    if count <= 0:
                        raise PatchError("short copied-pack write")
                    written += count
            if sha256_fd(source_descriptor) != expected_source_sha256:
                raise PatchError("source 1A descriptor changed during copy")
            final_source = os.lstat(source)
            if (final_source.st_dev, final_source.st_ino) != expected_source_identity:
                raise PatchError("source 1A pathname changed during copy")
        finally:
            os.close(source_descriptor)
        os.fsync(descriptor)
        if not _path_matches_at(directory_fd, name, identity):
            raise PatchError("reserved output 1A pathname changed during copy")
        return descriptor, identity
    except Exception:
        os.close(descriptor)
        _unlink_owned_at(directory_fd, name, identity)
        raise


def _write_manifest_new_at(directory_fd: int, name: str, manifest: dict[str, Any]) -> tuple[int, int]:
    data = canonical_json_bytes(manifest)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(name, flags, 0o644, dir_fd=directory_fd)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        written = 0
        while written < len(data):
            count = os.write(descriptor, data[written:])
            if count <= 0:
                raise PatchError("short manifest write")
            written += count
        os.fsync(descriptor)
        if not _path_matches_at(directory_fd, name, identity):
            raise PatchError("reserved manifest pathname changed during write")
        return identity
    except Exception:
        _unlink_owned_at(directory_fd, name, identity)
        raise
    finally:
        os.close(descriptor)


def _safe_cleanup(
    directory: Path,
    directory_fd: int,
    identity: tuple[int, int],
    owned: dict[str, tuple[int, int]],
) -> None:
    for name, child_identity in owned.items():
        _unlink_owned_at(directory_fd, name, child_identity)
    try:
        metadata = os.lstat(directory)
        if stat.S_ISDIR(metadata.st_mode) and (metadata.st_dev, metadata.st_ino) == identity:
            os.rmdir(directory)
    except OSError:
        pass


def _directory_path_matches(path: Path, identity: tuple[int, int]) -> bool:
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode) and (
        metadata.st_dev,
        metadata.st_ino,
    ) == identity


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
    if (
        stat.S_ISLNK(recipe_metadata.st_mode)
        or not stat.S_ISREG(recipe_metadata.st_mode)
        or recipe_metadata.st_size > MAX_RECIPE_BYTES
    ):
        raise PatchError("recipe must be a bounded regular non-symlink file")
    recipe_path = raw_recipe.resolve(strict=True)
    if recipe_path != raw_recipe.absolute():
        raise PatchError("recipe path contains a symlink")
    requested_output = output_dir.expanduser()
    if not requested_output.is_absolute():
        requested_output = Path.cwd() / requested_output
    requested_output = Path(os.path.normpath(requested_output))
    parent = requested_output.parent
    try:
        parent_metadata = os.lstat(parent)
    except OSError as exc:
        raise PatchError(f"output parent must already exist: {exc}") from exc
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
        raise PatchError("output directory must not be inside the source game directory")
    if os.path.lexists(output_dir):
        raise PatchError("refusing existing output directory")
    if not game_dir.is_dir() or not recipe_path.is_file():
        raise PatchError("source game directory or recipe is not a regular input")

    source_before, source_inodes = _source_file_identities(game_dir)
    rebuilt_entry, manifest = build_patch(game_dir, recipe_path)
    os.mkdir(output_dir, 0o755)
    created_directory_metadata = os.lstat(output_dir)
    created_directory_identity = (
        created_directory_metadata.st_dev,
        created_directory_metadata.st_ino,
    )
    directory_fd = os.open(
        output_dir,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    directory_metadata = os.fstat(directory_fd)
    directory_identity = (directory_metadata.st_dev, directory_metadata.st_ino)
    if directory_identity != created_directory_identity or not _directory_path_matches(
        output_dir, directory_identity
    ):
        os.close(directory_fd)
        raise PatchError("reserved output directory pathname changed during open")
    owned: dict[str, tuple[int, int]] = {}
    try:
        output_descriptor, output_identity = _copy_new_at(
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
                count = os.pwrite(output_descriptor, rebuilt_entry[written:], OUTER_PACK_OFFSET + written)
                if count <= 0:
                    raise PatchError("short outer-entry write")
                written += count
            os.fsync(output_descriptor)
            if os.fstat(output_descriptor).st_size != SOURCE_PACKS["1A"][0]:
                raise PatchError("output 1A length changed")
            manifest["result"]["output_pack_sha256"] = sha256_fd(output_descriptor)
            manifest["preservation"]["output_pack_prefix_sha256"] = sha256_fd_range(output_descriptor, 0, OUTER_PACK_OFFSET)
            suffix_offset = OUTER_PACK_OFFSET + OUTER_LENGTH
            manifest["preservation"]["output_pack_suffix_sha256"] = sha256_fd_range(
                output_descriptor,
                suffix_offset,
                os.fstat(output_descriptor).st_size - suffix_offset,
            )
            if (
                manifest["preservation"]["output_pack_prefix_sha256"] != SOURCE_PREFIX_SHA256
                or manifest["preservation"]["output_pack_suffix_sha256"] != SOURCE_SUFFIX_SHA256
            ):
                raise PatchError("output 1A complement outside outer 14 differs")
            if manifest["mode"] == "no_op" and manifest["result"]["output_pack_sha256"] != SOURCE_PACKS["1A"][1]:
                raise PatchError("no-op output 1A is not byte-identical")
        finally:
            os.close(output_descriptor)
        source_after, source_after_inodes = _source_file_identities(game_dir)
        if source_after != source_before:
            raise PatchError("source pack identity changed during write")
        if source_after_inodes != source_inodes:
            raise PatchError("source pack inode changed during write")
        manifest["preservation"]["source_files_rechecked_after_write"] = True
        owned[MANIFEST_NAME] = _write_manifest_new_at(directory_fd, MANIFEST_NAME, manifest)
        if sorted(os.listdir(directory_fd)) != sorted(owned):
            raise PatchError("output directory contains an unexpected artifact")
        if not all(_path_matches_at(directory_fd, name, identity) for name, identity in owned.items()):
            raise PatchError("published output child identity changed")
        if not _directory_path_matches(output_dir, directory_identity):
            raise PatchError("published output directory pathname changed")
        os.close(directory_fd)
        return manifest
    except Exception:
        _safe_cleanup(output_dir, directory_fd, directory_identity, owned)
        os.close(directory_fd)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True, help="complete APF game directory containing 0A/0B/1A/1B")
    parser.add_argument("--recipe", type=Path, required=True, help="const-pinned v1 position recipe")
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory to create with copied 1A and manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = write_output(args.game_dir, args.recipe, args.output_dir)
        print(
            "APF_SCNE_SAME_COUNT_POSITION_PATCH_PASS "
            f"mode={manifest['mode']} vertices=4 copied_pack=1A "
            f"outer_sha256={manifest['result']['outer_entry_sha256']} "
            f"output_pack_sha256={manifest['result']['output_pack_sha256']} "
            "runtime=false hardware=false"
        )
        return 0
    except (PatchError, apf_outer.FormatError, apf_inner.FormatError, apf_scene.SceneError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
