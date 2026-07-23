#!/usr/bin/env python3
"""Independent verifier for the APF stadium same-count POSITION0 writer.

This module intentionally does not import the production writer, APF archive
parsers, SCNE parser, or H7A implementation.  It re-parses the outer table,
IFF file-part ownership, H7A streams, target SCNE declarations/stream/index,
and every manifest field from source, recipe, copied 1A, and fixed constants.
The verification artifact is an explicit separate absent path; the writer's
output directory must remain exactly ``1A`` plus its manifest.
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
import zlib


RECIPE_SCHEMA = "apf2k8_scne_same_count_position_recipe/v1"
MANIFEST_SCHEMA = "apf2k8_scne_same_count_position_patch/v1"
VERIFY_SCHEMA = "apf2k8_scne_same_count_position_verification/v1"
MANIFEST_NAME = "apf2k8_scne_same_count_position_manifest.json"
RECIPE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "reports/specs/apf2k8_scne_same_count_position_recipe.schema.json"
RECIPE_SCHEMA_SIZE = 4_064
RECIPE_SCHEMA_SHA256 = "8094a4a64325728082091e87ba3fcd0e5ed30c8c6f06f1e7074934720438af51"

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
INNER_FILE_ID = 0xE604044F
INNER_TYPE_HASH = 0xE26C9B5D
SYSTEM_LENGTH = 4_199_168
SYSTEM_SHA256 = "b3028883de8d71d90850bab68ba29b91badd7107f8f9fbfab132a19a818379e4"
VRAM_LENGTH = 12_918_784
VRAM_SHA256 = "5662f3866f83e33bab217f80ac8e9a6267ae94842c0727f77019355cc2cb3a95"
NODE_INDEX = 17
NODE_NAME = "polySurface19930"
NODE_CRC = 0xB13B08B6
STREAM_START = 376_044
STREAM_LENGTH = 96
STREAM_STRIDE = 24
POSITION_SIZE = 12
VERTEX_COUNT = 4
SOURCE_FILE_LENGTH = 12_928_092
SOURCE_FOOTER_TOTAL = 954
SOURCE_FOOTER_SHA = "a115b9c25fda962a1a60573a2d10beff9990a8007f60b78f8b497dfd2486114b"
SOURCE_TAIL_LENGTH = 2_026
BLOCK1_STORED_SHA = "97b9ae08ed50d261f3d97ad02486c6268684d690174af8e430f7b3cabd13c01e"
SOURCE_PREFIX_SHA256 = "a9cff61c985cfa8e29ee10cd4e1b653eecd7f49de0a6b979b59e943a0d27a906"
SOURCE_SUFFIX_SHA256 = "fad57e63688614c87bd02d68100871615bc18a50c630b1aa10f44e1448cc77fb"
MAX_RECIPE_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024

TARGET_SPANS = {
    "matrix_table": (38_912, 5_696, "5fa0a6f9aa4444ad14676e989a521963d32e1693559f288202ac1bb3b81d8828"),
    "node_record": (26_240, 176, "24f8b734350d0447879ae0fd2899794fbcd3cc455ddbe064ad1da9dbce4ef428"),
    "hierarchy": (375_664, 48, "21df6a8e4e475144de905a555bad3799c61f10ee3a233f8d05d51025f3c8067a"),
    "draw_record": (375_712, 48, "161a2e06c0b875b6679423f490c2c89691d1da9899003768a0f4eac01cfe873f"),
    "index_buffer": (375_760, 8, "96b383ee0d221556a56277315db425256549a46ccc5217a392181783327a6dc5"),
    "declarations": (375_808, 192, "e105cd8c86a82b60e0bd65cd432bda0433d384a7ed08587b56baaa233bba9066"),
    "mesh_descriptor": (376_000, 44, "1de69481e216149b692fd64f0264ba5750903e02d99c63ab9082afc10a3d88be"),
}

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
        "outer_table_index": 14,
        "outer_name_id": "0x02bae370",
        "inner_file_index": 8,
        "inner_name": "stadium",
        "inner_file_id": "0xe604044f",
        "inner_type": "SCNE",
        "node_index": 17,
        "node_name": NODE_NAME,
        "node_name_crc32": "0xb13b08b6",
        "vertex_count": 4,
        "stream_index": 0,
        "stream_stride_bytes": 24,
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


class VerifyError(ValueError):
    """Independent verification failed."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    size = os.fstat(descriptor).st_size
    cursor = 0
    while cursor < size:
        chunk = os.pread(descriptor, min(8 * 1024 * 1024, size - cursor), cursor)
        if not chunk:
            raise VerifyError("short descriptor read")
        digest.update(chunk)
        cursor += len(chunk)
    return digest.hexdigest()


def sha256_fd_range(descriptor: int, offset: int, size: int) -> str:
    if offset < 0 or size < 0 or offset + size > os.fstat(descriptor).st_size:
        raise VerifyError("descriptor range out of bounds")
    digest = hashlib.sha256()
    cursor = offset
    remaining = size
    while remaining:
        chunk = os.pread(descriptor, min(8 * 1024 * 1024, remaining), cursor)
        if not chunk:
            raise VerifyError("short descriptor range read")
        digest.update(chunk)
        cursor += len(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=4, sort_keys=True) + "\n").encode("utf-8")


def _strict_json(path: Path, what: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_RECIPE_BYTES:
        raise VerifyError(f"{what}: JSON size is outside bounded range")

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
    if not isinstance(value, dict):
        raise VerifyError(f"{what}: top level is not an object")
    if raw != canonical_json_bytes(value):
        raise VerifyError(f"{what}: JSON is not canonical sorted UTF-8")
    return value, raw


def _load_recipe(path: Path) -> tuple[dict[str, Any], bytes, bytes]:
    if RECIPE_SCHEMA_PATH.stat().st_size != RECIPE_SCHEMA_SIZE or sha256_file(RECIPE_SCHEMA_PATH) != RECIPE_SCHEMA_SHA256:
        raise VerifyError("recipe schema identity drift")
    recipe, raw = _strict_json(path, "recipe")
    if set(recipe) != set(RECIPE_CONSTANTS) | {"positions"}:
        raise VerifyError("recipe top-level key set differs")
    for key, expected in RECIPE_CONSTANTS.items():
        if recipe.get(key) != expected:
            raise VerifyError(f"recipe constant differs: {key}")
    positions = recipe.get("positions")
    if not isinstance(positions, list) or len(positions) != 4:
        raise VerifyError("recipe does not contain exactly four positions")
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
    return recipe, raw, bytes(encoded)


def _u16(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise VerifyError(f"{what}: u16 out of bounds")
    return struct.unpack_from(">H", data, offset)[0]


def _u32(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise VerifyError(f"{what}: u32 out of bounds")
    return struct.unpack_from(">I", data, offset)[0]


def _rel(data: bytes, field: int, what: str, allow_end: bool = False) -> int:
    raw = _u32(data, field, what)
    if raw == 0:
        raise VerifyError(f"{what}: null relative pointer")
    target = field + raw - 1
    maximum = len(data) if allow_end else len(data) - 1
    if target < 0 or target > maximum:
        raise VerifyError(f"{what}: relative target out of bounds")
    return target


def _utf16be(data: bytes, offset: int, what: str) -> str:
    values: list[int] = []
    for _ in range(2048):
        value = _u16(data, offset, what)
        offset += 2
        if value == 0:
            return "".join(chr(item) for item in values)
        if 0xD800 <= value <= 0xDFFF:
            raise VerifyError(f"{what}: surrogate is unsupported")
        values.append(value)
    raise VerifyError(f"{what}: unterminated name")


def _decompress_h7a(stored: bytes, expected_size: int, expected_shift: int) -> bytes:
    if len(stored) < 20:
        raise VerifyError("H7A wrapper is truncated")
    magic, unpacked, stored_length, codec, shift = struct.unpack_from(">5I", stored, 0)
    if magic != 0x0E4837C3 or unpacked != expected_size or stored_length != len(stored) or shift != expected_shift or codec != 7:
        raise VerifyError("H7A wrapper identity differs")
    payload = stored[20:]
    output = bytearray(expected_size)
    source = 0
    target = 0
    distance_mask = (1 << shift) - 1
    length_mask = (1 << (16 - shift)) - 1
    while target < expected_size:
        if source >= len(payload):
            raise VerifyError("truncated H7A descriptor")
        descriptor = payload[source]
        source += 1
        for bit in range(8):
            if target >= expected_size:
                break
            if descriptor & (1 << bit):
                if source + 2 > len(payload):
                    raise VerifyError("truncated H7A match")
                word = int.from_bytes(payload[source : source + 2], "big")
                source += 2
                distance = word & distance_mask
                length = ((word >> shift) & length_mask) + 3
                if distance < 1 or distance > target or target + length > expected_size:
                    raise VerifyError("invalid H7A match bounds")
                for _ in range(length):
                    output[target] = output[target - distance]
                    target += 1
            else:
                if source >= len(payload):
                    raise VerifyError("truncated H7A literal")
                output[target] = payload[source]
                source += 1
                target += 1
    if any(payload[source:]):
        raise VerifyError("H7A has nonzero trailing payload")
    return bytes(output)


def _parse_outer(index_path: Path) -> dict[str, Any]:
    path_metadata = os.lstat(index_path)
    descriptor = os.open(
        index_path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        descriptor_metadata = os.fstat(descriptor)
        identity = (descriptor_metadata.st_dev, descriptor_metadata.st_ino)
        if (
            stat.S_ISLNK(path_metadata.st_mode)
            or not stat.S_ISREG(descriptor_metadata.st_mode)
            or identity != (path_metadata.st_dev, path_metadata.st_ino)
            or descriptor_metadata.st_size != SOURCE_PACKS["0A"][0]
            or sha256_fd(descriptor) != SOURCE_PACKS["0A"][1]
        ):
            raise VerifyError("outer index descriptor identity differs")
        fixed = os.pread(descriptor, 24, 0)
        if len(fixed) != 24:
            raise VerifyError("outer index header is truncated")
        magic, alignment, pack_count, reserved_0c, entry_count, reserved_14 = struct.unpack(">6I", fixed)
        if (magic, alignment, pack_count, reserved_0c, entry_count, reserved_14) != (0xAA00B3BF, 2048, 4, 0, 1543, 0):
            raise VerifyError("outer index header identity differs")
        packs: list[dict[str, Any]] = []
        virtual_start = 0
        for ordinal in range(pack_count):
            raw = os.pread(descriptor, 16, 24 + ordinal * 16)
            if len(raw) != 16:
                raise VerifyError("outer pack descriptor is truncated")
            size_blocks, reserved, raw_name = struct.unpack(">II8s", raw)
            name = raw_name.decode("utf-16be").split("\0", 1)[0]
            if reserved != 0 or name not in SOURCE_PACKS:
                raise VerifyError("outer pack descriptor identity differs")
            size = size_blocks * alignment
            if size != SOURCE_PACKS[name][0]:
                raise VerifyError("outer pack declared size differs")
            packs.append({"ordinal": ordinal, "name": name, "virtual_start": virtual_start, "size": size})
            virtual_start += size
        raw_entry = os.pread(descriptor, 12, 24 + 4 * 16 + OUTER_INDEX * 12)
        if len(raw_entry) != 12:
            raise VerifyError("outer target record is truncated")
        name_id, offset_blocks, size_blocks = struct.unpack(">3I", raw_entry)
        final_metadata = os.lstat(index_path)
        if (final_metadata.st_dev, final_metadata.st_ino) != identity:
            raise VerifyError("outer index pathname changed during parse")
    finally:
        os.close(descriptor)
    virtual_offset = offset_blocks * alignment
    size = size_blocks * alignment
    if name_id != OUTER_NAME_ID or size != OUTER_LENGTH:
        raise VerifyError("outer target identity/allocation differs")
    owner = next((pack for pack in packs if pack["virtual_start"] <= virtual_offset < pack["virtual_start"] + pack["size"]), None)
    if owner is None or owner["name"] != "1A" or virtual_offset - owner["virtual_start"] != OUTER_PACK_OFFSET or virtual_offset + size > owner["virtual_start"] + owner["size"]:
        raise VerifyError("outer target physical routing differs")
    return {"packs": packs, "physical_pack": "1A", "physical_offset": OUTER_PACK_OFFSET, "size": size}


def _parse_iff(entry: bytes) -> dict[str, Any]:
    if len(entry) != OUTER_LENGTH:
        raise VerifyError("IFF outer allocation length differs")
    fields = struct.unpack_from(">8I", entry, 0)
    magic, header_size, file_length, zero, block_count, block_ptr, file_count, file_ptr = fields
    if magic != 0xFF3BEF94 or header_size != 292 or zero != 0 or block_count != 2 or file_count != 9:
        raise VerifyError("IFF header identity differs")
    if 0x14 + block_ptr - 1 != 32 or 0x1C + file_ptr - 1 != 96:
        raise VerifyError("IFF table pointers differ")
    blocks: list[dict[str, Any]] = []
    for index in range(block_count):
        values = struct.unpack_from(">8I", entry, 32 + index * 32)
        name_hash, type_hash, unknown08, unpacked, codec, start, stored_length, indexed = values
        if start < header_size or start + stored_length > file_length:
            raise VerifyError("IFF stored block range out of bounds")
        stored = entry[start : start + stored_length]
        expected_shift = 12 if index == 0 else 10
        decoded = _decompress_h7a(stored, unpacked, expected_shift)
        blocks.append({
            "index": index,
            "name_hash": name_hash,
            "type_hash": type_hash,
            "unknown08": unknown08,
            "unpacked": unpacked,
            "codec": codec,
            "start": start,
            "stored_length": stored_length,
            "indexed": indexed,
            "stored": stored,
            "decoded": decoded,
        })
    if blocks[0]["name_hash"] != 0xBB05A9C1 or blocks[1]["name_hash"] != 0x411536D5:
        raise VerifyError("IFF DRAM/VRAM block identities differ")
    if blocks[0]["unpacked"] != 5_719_968 or blocks[1]["unpacked"] != 24_453_120:
        raise VerifyError("IFF block uncompressed lengths differ")
    if blocks[0]["start"] != 292 or blocks[1]["start"] != blocks[0]["start"] + blocks[0]["stored_length"] or file_length != blocks[1]["start"] + blocks[1]["stored_length"]:
        raise VerifyError("IFF block packing differs")
    cursor = 96
    descriptor_offsets: list[int] = []
    for index in range(file_count):
        raw = _u32(entry, cursor + index * 4, "file descriptor pointer")
        descriptor_offsets.append(cursor + index * 4 + raw - 1)
    cursor += file_count * 4
    files: list[dict[str, Any]] = []
    for index, expected_offset in enumerate(descriptor_offsets):
        if expected_offset != cursor or cursor + 12 > header_size:
            raise VerifyError("IFF file descriptor packing differs")
        file_id, type_hash, offset_count = struct.unpack_from(">3I", entry, cursor)
        if offset_count > block_count or cursor + 12 + offset_count * 4 > header_size:
            raise VerifyError("IFF file descriptor offsets are invalid")
        offsets = list(struct.unpack_from(f">{offset_count}I", entry, cursor + 12)) if offset_count else []
        files.append({"index": index, "file_id": file_id, "type_hash": type_hash, "offsets": offsets, "parts": []})
        cursor += 12 + offset_count * 4
    if cursor != header_size:
        raise VerifyError("IFF header contains unexpected padding")
    for block_index, block in enumerate(blocks):
        present = [file for file in files if len(file["offsets"]) > block_index and file["offsets"][block_index] != 0xFFFFFFFF]
        present.sort(key=lambda file: file["offsets"][block_index])
        for position, file in enumerate(present):
            start = file["offsets"][block_index]
            end = present[position + 1]["offsets"][block_index] if position + 1 < len(present) else block["unpacked"]
            if not 0 <= start <= end <= block["unpacked"]:
                raise VerifyError("IFF derived part range is invalid")
            file["parts"].append({"block_index": block_index, "offset": start, "length": end - start})
    footer_size = struct.unpack_from("<I", entry, file_length + 4)[0] if file_length + 8 <= len(entry) else -1
    footer_total = 8 + footer_size
    if _u32(entry, file_length, "footer magic") != 0xAA171516 or file_length + footer_total > len(entry):
        raise VerifyError("IFF footer is invalid")
    footer = entry[file_length : file_length + footer_total]
    tail = entry[file_length + footer_total :]
    return {"header_size": header_size, "file_length": file_length, "blocks": blocks, "files": files, "footer": footer, "tail": tail}


def _part_hashes(record: dict[str, Any]) -> dict[tuple[int, int], str]:
    output: dict[tuple[int, int], str] = {}
    for file in record["files"]:
        for part_index, part in enumerate(file["parts"]):
            block = record["blocks"][part["block_index"]]["decoded"]
            output[(file["index"], part_index)] = sha256_bytes(block[part["offset"] : part["offset"] + part["length"]])
    return output


def validate_iff_header_preservation(source_entry: bytes, output_entry: bytes) -> None:
    if len(source_entry) < 292 or len(output_entry) < 292:
        raise VerifyError("IFF header comparison is truncated")
    allowed = set(range(0x08, 0x0C)) | set(range(0x38, 0x3C)) | set(range(0x54, 0x58))
    source = bytearray(source_entry[:292])
    output = bytearray(output_entry[:292])
    for offset in allowed:
        source[offset] = 0
        output[offset] = 0
    if output != source:
        raise VerifyError("output IFF header differs outside mechanical length/start fields")


def _parse_target_scne(system: bytes, require_retail_stream_hash: bool) -> dict[str, Any]:
    if len(system) != SYSTEM_LENGTH:
        raise VerifyError("stadium DRAM part length differs")
    root = _utf16be(system, _rel(system, 0, "SCNE root name"), "SCNE root name")
    if root != "stadium" or _u32(system, 0x44, "node count") != 89:
        raise VerifyError("SCNE root/node identity differs")
    node_table = _rel(system, 0x48, "node table")
    node = node_table + NODE_INDEX * 0xB0
    if node != 26_240 or _utf16be(system, _rel(system, node, "node name"), "node name") != NODE_NAME or _u32(system, node + 4, "node CRC") != NODE_CRC:
        raise VerifyError("target node identity differs")
    if (_u32(system, node + 0x60, "hierarchy count"), _u32(system, node + 0x7C, "draw count"), _u32(system, node + 0x84, "mesh count"), _u32(system, node + 0x98, "declaration count"), _u32(system, node + 0xA4, "index bits"), _u32(system, node + 0xA8, "index count")) != (1, 1, 1, 3, 16, 4):
        raise VerifyError("target node count contract differs")
    hierarchy = _rel(system, node + 0x64, "hierarchy")
    draw = _rel(system, node + 0x80, "draw")
    descriptor = _rel(system, node + 0x88, "mesh descriptor")
    declarations = _rel(system, node + 0x9C, "declarations")
    index = _rel(system, node + 0xAC, "indices")
    if (hierarchy, draw, descriptor, declarations, index) != (375_664, 375_712, 376_000, 375_808, 375_760):
        raise VerifyError("target node table pointers differ")
    expected_declarations = [
        (0x46E6CB71, 0x801F78B9, 0x20000000, 0x002A23B9),
        (0xF51CD0CF, 0x1C7EE841, 0x200C0000, 0x001A2360),
        (0x57B6A2FA, 0xD17DAF62, 0x20140000, 0x002A2187),
    ]
    for item, expected in enumerate(expected_declarations):
        if struct.unpack_from(">4I", system, declarations + item * 64) != expected:
            raise VerifyError("target vertex declaration differs")
    unknown00, optional, vertices, packed_streams, primitive = struct.unpack_from(">5I", system, descriptor)
    if (optional, vertices, packed_streams, primitive) != (0, 4, 0x00010000, 5):
        raise VerifyError("target mesh descriptor differs")
    flags, enabled, stride, byte_length = struct.unpack_from(">4I", system, descriptor + 20)
    stream_start = _rel(system, descriptor + 36, "stream start")
    stream_end = _rel(system, descriptor + 40, "stream end", allow_end=True)
    if (flags, enabled, stride, byte_length, stream_start, stream_end) != (0x40000000, 1, 24, 96, STREAM_START, STREAM_START + STREAM_LENGTH):
        raise VerifyError("target stream descriptor differs")
    if [_u16(system, index + item * 2, "index") for item in range(4)] != [0, 1, 2, 3]:
        raise VerifyError("target strip indices differ")
    stream = system[stream_start:stream_end]
    if require_retail_stream_hash and sha256_bytes(stream) != "86f3c7a4cc3d5c46d9bcfcf48bd465e96f954ce1a3e764e20c595633e70264eb":
        raise VerifyError("retail target stream hash differs")
    for label, (offset, length, expected_hash) in TARGET_SPANS.items():
        if sha256_bytes(system[offset : offset + length]) != expected_hash:
            raise VerifyError(f"target structural span differs: {label}")
    return {"stream": stream, "positions": _position_payload(stream), "interleaves": _interleave_hashes(stream), "non_position": _non_position_system_hash(system)}


def _position_payload(stream: bytes) -> bytes:
    return b"".join(stream[item * 24 : item * 24 + 12] for item in range(4))


def _interleave_hashes(stream: bytes) -> dict[str, str]:
    return {
        "uv_float16x4": sha256_bytes(b"".join(stream[i * 24 + 12 : i * 24 + 20] for i in range(4))),
        "normal_snorm10_10_10": sha256_bytes(b"".join(stream[i * 24 + 20 : i * 24 + 24] for i in range(4))),
    }


def _non_position_system_hash(system: bytes) -> str:
    digest = hashlib.sha256()
    cursor = 0
    for vertex in range(4):
        lane = STREAM_START + vertex * 24
        digest.update(system[cursor:lane])
        cursor = lane + 12
    digest.update(system[cursor:])
    return digest.hexdigest()


def _source_identities(game_dir: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for name, (size, expected_hash) in SOURCE_PACKS.items():
        path = game_dir / name
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise VerifyError(f"cannot lstat source pack {name}: {exc}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_size != size:
            raise VerifyError(f"source pack type/size differs: {name}")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        try:
            descriptor_metadata = os.fstat(descriptor)
            identity = (descriptor_metadata.st_dev, descriptor_metadata.st_ino)
            if identity != (metadata.st_dev, metadata.st_ino) or descriptor_metadata.st_size != size:
                raise VerifyError(f"source pack pathname changed: {name}")
            digest = sha256_fd(descriptor)
            final_metadata = os.lstat(path)
            if (final_metadata.st_dev, final_metadata.st_ino) != identity:
                raise VerifyError(f"source pack pathname changed during hash: {name}")
        finally:
            os.close(descriptor)
        if digest != expected_hash:
            raise VerifyError(f"source pack hash differs: {name}")
        output.append({"name": name, "size_bytes": size, "sha256": digest})
    return output


def _claims() -> dict[str, bool]:
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


def _expected_manifest(
    recipe: dict[str, Any], recipe_raw: bytes, mode: str, source_target: dict[str, Any], output_target: dict[str, Any],
    source_record: dict[str, Any], output_record: dict[str, Any], output_pack_sha: str, output_outer_sha: str,
    changed_offsets: list[int], changed_parts: list[tuple[int, int]], prefix_sha: str, suffix_sha: str,
) -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "mode": mode,
        "recipe": {
            "schema": recipe["schema"], "sha256": sha256_bytes(recipe_raw), "authored_position_count": 4,
            "coordinate_space": recipe["coordinate_space"], "vertex_order": recipe["vertex_order"], "position_type": recipe["position_type"],
        },
        "source": {
            "game": "All-Pro Football 2K8 Xbox 360 USA retail",
            "packs": [{"name": name, "size_bytes": size, "sha256": digest} for name, (size, digest) in SOURCE_PACKS.items()],
            "outer_entry_sha256": OUTER_SHA256, "stadium_dram_sha256": SYSTEM_SHA256,
            "stadium_vram_sha256": VRAM_SHA256, "position_payload_sha256": sha256_bytes(source_target["positions"]),
        },
        "target": {
            "outer_table_index": 14, "physical_pack": "1A", "fixed_outer_allocation_bytes": OUTER_LENGTH,
            "inner_file_index": 8, "inner_name": "stadium", "node_index": 17, "node_name": NODE_NAME,
            "vertex_count": 4, "stream_stride_bytes": 24, "position_lane_bytes_per_vertex": 12,
            "approved_position_lane_bytes": 48, "position_format": "FLOAT32x3_BE",
        },
        "result": {
            "output_directory_contract": ["1A", MANIFEST_NAME], "output_pack_name": "1A",
            "output_pack_size_bytes": SOURCE_PACKS["1A"][0], "output_pack_sha256": output_pack_sha,
            "outer_entry_sha256": output_outer_sha,
            "stadium_dram_sha256": sha256_bytes(output_record["blocks"][0]["decoded"][:SYSTEM_LENGTH]),
            "stadium_vram_sha256": sha256_bytes(output_record["blocks"][1]["decoded"][:VRAM_LENGTH]),
            "position_payload_sha256": sha256_bytes(output_target["positions"]),
            "changed_decoded_dram_byte_count": len(changed_offsets),
            "changed_inner_parts": [{"file_index": a, "part_index": b} for a, b in changed_parts],
            "h7a_block0_recompressed": mode == "changed", "h7a_block0_shift": 12,
            "block0_stored_length_before": source_record["blocks"][0]["stored_length"],
            "block0_stored_length_after": output_record["blocks"][0]["stored_length"],
            "block1_stored_sha256": sha256_bytes(output_record["blocks"][1]["stored"]),
            "file_length_before": source_record["file_length"], "file_length_after": output_record["file_length"],
            "allocation_slack_after_bytes": len(output_record["tail"]),
        },
        "preservation": {
            "uv_normal_interleaves": output_target["interleaves"], "scne_non_position_sha256": output_target["non_position"],
            "structural_spans": {label: digest for label, (_, _, digest) in TARGET_SPANS.items()},
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
    raw_game_dir = game_dir.expanduser()
    if not raw_game_dir.is_absolute():
        raw_game_dir = Path.cwd() / raw_game_dir
    raw_game_dir = Path(os.path.normpath(raw_game_dir))
    game_metadata = os.lstat(raw_game_dir)
    if stat.S_ISLNK(game_metadata.st_mode) or not stat.S_ISDIR(game_metadata.st_mode):
        raise VerifyError("source game directory must be a real non-symlink directory")
    game_dir = raw_game_dir.resolve(strict=True)
    if game_dir != raw_game_dir.absolute():
        raise VerifyError("source game directory path contains a symlink")
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
        raise VerifyError("recipe must be a bounded regular non-symlink file")
    recipe_path = raw_recipe.resolve(strict=True)
    if recipe_path != raw_recipe.absolute():
        raise VerifyError("recipe path contains a symlink")
    output_dir_raw = output_dir.expanduser()
    if not output_dir_raw.is_absolute():
        output_dir_raw = Path.cwd() / output_dir_raw
    output_metadata = os.lstat(output_dir_raw)
    if stat.S_ISLNK(output_metadata.st_mode) or not stat.S_ISDIR(output_metadata.st_mode):
        raise VerifyError("output directory must be a real directory, not a symlink")
    output_dir = output_dir_raw.resolve(strict=True)
    if output_dir != output_dir_raw.absolute():
        raise VerifyError("output directory path contains a symlink")
    directory_fd = os.open(output_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        directory_stat = os.fstat(directory_fd)
        directory_identity = (directory_stat.st_dev, directory_stat.st_ino)
        if directory_identity != (output_metadata.st_dev, output_metadata.st_ino):
            raise VerifyError("output directory pathname changed during open")
        if sorted(os.listdir(directory_fd)) != ["1A", MANIFEST_NAME]:
            raise VerifyError("output directory must contain exactly copied 1A and manifest")
        output_pack_fd = os.open("1A", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        manifest_fd = os.open(MANIFEST_NAME, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            output_pack_stat = os.fstat(output_pack_fd)
            manifest_stat = os.fstat(manifest_fd)
            if not stat.S_ISREG(output_pack_stat.st_mode) or not stat.S_ISREG(manifest_stat.st_mode):
                raise VerifyError("output children must be regular files")
            if manifest_stat.st_size > MAX_MANIFEST_BYTES:
                raise VerifyError("manifest exceeds size limit")
            output_pack_identity = (output_pack_stat.st_dev, output_pack_stat.st_ino)
            manifest_identity = (manifest_stat.st_dev, manifest_stat.st_ino)
            source_1a_stat = os.stat(game_dir / "1A", follow_symlinks=False)
            if (output_pack_stat.st_dev, output_pack_stat.st_ino) == (source_1a_stat.st_dev, source_1a_stat.st_ino):
                raise VerifyError("output 1A hardlink-aliases source 1A")
            if output_pack_stat.st_size != SOURCE_PACKS["1A"][0]:
                raise VerifyError("output 1A size differs")
            manifest_raw = os.pread(manifest_fd, manifest_stat.st_size, 0)
            manifest_temp = json.loads(manifest_raw, object_pairs_hook=lambda pairs: _unique_pairs(pairs, "manifest"), parse_constant=lambda value: _reject_constant(value, "manifest"))
            if not isinstance(manifest_temp, dict) or manifest_raw != canonical_json_bytes(manifest_temp):
                raise VerifyError("manifest is not canonical sorted object JSON")
            manifest = manifest_temp
            output_pack_sha = sha256_fd(output_pack_fd)
            prefix_sha = sha256_fd_range(output_pack_fd, 0, OUTER_PACK_OFFSET)
            suffix_offset = OUTER_PACK_OFFSET + OUTER_LENGTH
            suffix_sha = sha256_fd_range(output_pack_fd, suffix_offset, output_pack_stat.st_size - suffix_offset)
            output_entry = os.pread(output_pack_fd, OUTER_LENGTH, OUTER_PACK_OFFSET)
            final_pack = os.stat("1A", dir_fd=directory_fd, follow_symlinks=False)
            final_manifest = os.stat(MANIFEST_NAME, dir_fd=directory_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(final_pack.st_mode)
                or not stat.S_ISREG(final_manifest.st_mode)
                or (final_pack.st_dev, final_pack.st_ino) != output_pack_identity
                or (final_manifest.st_dev, final_manifest.st_ino) != manifest_identity
            ):
                raise VerifyError("output child pathname identity changed during verification")
        finally:
            os.close(output_pack_fd)
            os.close(manifest_fd)
    finally:
        final_directory = os.lstat(output_dir)
        if (final_directory.st_dev, final_directory.st_ino) != directory_identity:
            os.close(directory_fd)
            raise VerifyError("output directory pathname identity changed during verification")
        os.close(directory_fd)

    recipe, recipe_raw, wanted_positions = _load_recipe(recipe_path)
    source_identities = _source_identities(game_dir)
    routing = _parse_outer(game_dir / "0A")
    if routing != {"packs": [
        {"ordinal": 0, "name": "0A", "virtual_start": 0, "size": 1_140_850_688},
        {"ordinal": 1, "name": "0B", "virtual_start": 1_140_850_688, "size": 1_073_838_080},
        {"ordinal": 2, "name": "1A", "virtual_start": 2_214_688_768, "size": 1_140_850_688},
        {"ordinal": 3, "name": "1B", "virtual_start": 3_355_539_456, "size": 517_971_968},
    ], "physical_pack": "1A", "physical_offset": OUTER_PACK_OFFSET, "size": OUTER_LENGTH}:
        raise VerifyError("independently derived outer routing differs")
    source_1a_path = game_dir / "1A"
    source_1a_lstat = os.lstat(source_1a_path)
    source_1a_fd = os.open(
        source_1a_path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        source_1a_metadata = os.fstat(source_1a_fd)
        source_1a_identity = (source_1a_metadata.st_dev, source_1a_metadata.st_ino)
        if (
            source_1a_identity != (source_1a_lstat.st_dev, source_1a_lstat.st_ino)
            or source_1a_metadata.st_size != SOURCE_PACKS["1A"][0]
            or sha256_fd(source_1a_fd) != SOURCE_PACKS["1A"][1]
        ):
            raise VerifyError("source 1A descriptor identity differs")
        source_entry = os.pread(source_1a_fd, OUTER_LENGTH, OUTER_PACK_OFFSET)
        source_prefix_sha = sha256_fd_range(source_1a_fd, 0, OUTER_PACK_OFFSET)
        source_suffix_sha = sha256_fd_range(source_1a_fd, suffix_offset, SOURCE_PACKS["1A"][0] - suffix_offset)
        final_source_1a = os.lstat(source_1a_path)
        if (final_source_1a.st_dev, final_source_1a.st_ino) != source_1a_identity:
            raise VerifyError("source 1A pathname changed during verification")
    finally:
        os.close(source_1a_fd)
    if (
        sha256_bytes(source_entry) != OUTER_SHA256
        or prefix_sha != source_prefix_sha
        or suffix_sha != source_suffix_sha
        or source_prefix_sha != SOURCE_PREFIX_SHA256
        or source_suffix_sha != SOURCE_SUFFIX_SHA256
    ):
        raise VerifyError("output bytes outside outer 14 differ from source")

    source_record = _parse_iff(source_entry)
    output_record = _parse_iff(output_entry)
    validate_iff_header_preservation(source_entry, output_entry)
    source_file_descriptors = [
        (item["file_id"], item["type_hash"], item["offsets"])
        for item in source_record["files"]
    ]
    output_file_descriptors = [
        (item["file_id"], item["type_hash"], item["offsets"])
        for item in output_record["files"]
    ]
    if output_file_descriptors != source_file_descriptors:
        raise VerifyError("output IFF file descriptor table differs")
    for source_block, output_block in zip(source_record["blocks"], output_record["blocks"]):
        for field in ("index", "name_hash", "type_hash", "unknown08", "unpacked", "codec", "indexed"):
            if output_block[field] != source_block[field]:
                raise VerifyError(f"output IFF block metadata differs: {field}")
    if source_record["file_length"] != SOURCE_FILE_LENGTH or len(source_record["footer"]) != SOURCE_FOOTER_TOTAL or sha256_bytes(source_record["footer"]) != SOURCE_FOOTER_SHA or len(source_record["tail"]) != SOURCE_TAIL_LENGTH or any(source_record["tail"]):
        raise VerifyError("source IFF footer/tail identity differs")
    if source_record["files"][INNER_INDEX]["file_id"] != INNER_FILE_ID or source_record["files"][INNER_INDEX]["type_hash"] != INNER_TYPE_HASH:
        raise VerifyError("source target file descriptor differs")
    expected_parts = [{"block_index": 0, "offset": 0, "length": SYSTEM_LENGTH}, {"block_index": 1, "offset": 0, "length": VRAM_LENGTH}]
    if source_record["files"][INNER_INDEX]["parts"] != expected_parts or output_record["files"][INNER_INDEX]["parts"] != expected_parts:
        raise VerifyError("stadium part ownership differs")
    source_system = source_record["blocks"][0]["decoded"][:SYSTEM_LENGTH]
    output_system = output_record["blocks"][0]["decoded"][:SYSTEM_LENGTH]
    if sha256_bytes(source_system) != SYSTEM_SHA256 or sha256_bytes(source_record["blocks"][1]["decoded"][:VRAM_LENGTH]) != VRAM_SHA256:
        raise VerifyError("source stadium DRAM/VRAM identity differs")
    source_target = _parse_target_scne(source_system, True)
    output_target = _parse_target_scne(output_system, False)
    if output_target["positions"] != wanted_positions:
        raise VerifyError("output serialized FLOAT3 positions differ from recipe")
    mode = "no_op" if wanted_positions == source_target["positions"] else "changed"
    if mode == "no_op" and (output_pack_sha != SOURCE_PACKS["1A"][1] or output_entry != source_entry):
        raise VerifyError("no-op output 1A is not byte-identical")
    if output_target["interleaves"] != source_target["interleaves"] or output_target["non_position"] != source_target["non_position"]:
        raise VerifyError("UV/normal or SCNE non-position bytes changed")
    changed_offsets = [index for index, (a, b) in enumerate(zip(source_record["blocks"][0]["decoded"], output_record["blocks"][0]["decoded"])) if a != b]
    allowed = {STREAM_START + vertex * 24 + byte for vertex in range(4) for byte in range(12)}
    if not set(changed_offsets).issubset(allowed):
        raise VerifyError("decoded DRAM change escapes approved lanes")
    source_parts = _part_hashes(source_record)
    output_parts = _part_hashes(output_record)
    if set(source_parts) != set(output_parts) or len(source_parts) != 13:
        raise VerifyError("file-part corpus differs")
    changed_parts = sorted(key for key in source_parts if source_parts[key] != output_parts[key])
    if changed_parts != ([] if mode == "no_op" else [(8, 0)]):
        raise VerifyError("changed inner part set differs")
    if source_record["blocks"][1]["stored"] != output_record["blocks"][1]["stored"] or sha256_bytes(output_record["blocks"][1]["stored"]) != BLOCK1_STORED_SHA:
        raise VerifyError("stored block1 differs")
    if output_record["footer"] != source_record["footer"] or any(output_record["tail"]):
        raise VerifyError("output footer/tail differs")
    if mode == "no_op" and output_record["file_length"] != SOURCE_FILE_LENGTH:
        raise VerifyError("no-op file length differs")

    expected_manifest = _expected_manifest(
        recipe, recipe_raw, mode, source_target, output_target, source_record, output_record,
        output_pack_sha, sha256_bytes(output_entry), changed_offsets, changed_parts, prefix_sha, suffix_sha,
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
        "source_pack_sha256": SOURCE_PACKS["1A"][1],
        "output_pack_sha256": output_pack_sha,
        "source_outer_sha256": OUTER_SHA256,
        "output_outer_sha256": sha256_bytes(output_entry),
        "output_stadium_dram_sha256": sha256_bytes(output_system),
        "output_position_payload_sha256": sha256_bytes(output_target["positions"]),
        "checks": {
            "recipe_canonical_duplicate_free_const_pinned": True,
            "recipe_positions_exact_finite_binary32": True,
            "source_four_pack_identity_rechecked": True,
            "output_source_inode_alias_rejected": True,
            "outer_routing_independently_derived": True,
            "iff_h7a_independently_reparsed": True,
            "target_scne_layout_independently_rederived": True,
            "decoded_positions_equal_recipe": True,
            "changed_decoded_bytes_subset_of_48_position_lanes": True,
            "uv_normal_interleaves_exact": True,
            "matrix_hierarchy_draw_index_declarations_descriptor_exact": True,
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


def _unique_pairs(pairs: list[tuple[str, Any]], what: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise VerifyError(f"{what}: duplicate key {key!r}")
        output[key] = value
    return output


def _reject_constant(value: str, what: str) -> None:
    raise VerifyError(f"{what}: non-JSON constant {value!r}")


def _write_artifact(path: Path, artifact: dict[str, Any], forbidden_dir: Path) -> None:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested = Path(os.path.normpath(requested))
    parent = requested.parent
    metadata = os.lstat(parent)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode) or parent.resolve(strict=True) != parent.absolute():
        raise VerifyError("artifact parent must be an existing real non-symlink directory")
    resolved = parent.resolve(strict=True) / requested.name
    if os.path.lexists(resolved):
        raise VerifyError("refusing existing verification artifact")
    try:
        resolved.relative_to(forbidden_dir.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise VerifyError("verification artifact must remain outside writer output directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(resolved, flags, 0o644)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    try:
        data = canonical_json_bytes(artifact)
        written = 0
        while written < len(data):
            count = os.write(descriptor, data[written:])
            if count <= 0:
                raise VerifyError("short verification artifact write")
            written += count
        os.fsync(descriptor)
        current = os.lstat(resolved)
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != identity:
            raise VerifyError("verification artifact pathname changed during publication")
    except Exception:
        try:
            current = os.lstat(resolved)
            if stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == identity:
                os.unlink(resolved)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True, help="new verification JSON path outside output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        artifact, _ = verify(args.game_dir, args.recipe, args.output_dir)
        _write_artifact(args.artifact, artifact, args.output_dir)
        print(
            "APF_SCNE_SAME_COUNT_POSITION_VERIFY_PASS "
            f"mode={artifact['mode']} vertices=4 output_pack_sha256={artifact['output_pack_sha256']} "
            "siblings=11 non_target_parts=12 runtime=false hardware=false"
        )
        return 0
    except (VerifyError, OSError, ValueError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
