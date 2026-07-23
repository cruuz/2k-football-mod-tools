#!/usr/bin/env python3
"""Independently verify an NFL 2K5 group36 copied-volume position patch.

This module intentionally imports no writer-side project module.  It parses
the recipe, archive directory record, VC-LZ streams, SCNE descriptor/shape,
rigid transform/selectors, native QUADS push stream, fixed tail, wrapper and
whole-volume diff independently from ``nfl_stadium_group36_position_patch``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import stat
import struct
from typing import Any


VERIFY_SCHEMA = "nfl2k5_static_position_verify/v1"
RECIPE_SCHEMA = "nfl2k5_static_position_recipe/v1"
PATCH_SCHEMA = "nfl2k5_static_position_patch/v1"
MAX_RECIPE_BYTES = 16 * 1024
MAX_MANIFEST_BYTES = 256 * 1024

INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
PACK_SIZE = 634_941_440
PACK_SHA256 = "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a"
ENTRY_INDEX = 3280
ENTRY_ID = 0xE4D6B0BC
ENTRY_SIZE = 1_390_448
ENTRY_OFFSET_BLOCKS = 1_747_476
ENTRY_VIRTUAL_OFFSET = 3_578_830_848
ENTRY_PACK_OFFSET = 0x07E47000
ENTRY_SHA256 = "3b2a505e2f0cab433fbe74c5211e4b370112e4e70a2ad45f1fa39a59af9a92cd"
CHUNK_INDEX = 5
CHUNK_ENTRY_OFFSET = 0x5EA40
CHUNK_START = 0x07EA5A40
CHUNK_END = 0x07F838B0
CHUNK_STORED = 908_880
CHUNK_SPAN = 908_912
SYSTEM_BYTES = 577_792
VIDEO_BYTES = 947_072
DECODED_SIZE = 1_524_864
SOURCE_SPAN_SHA256 = "0cd1977a6097851f9366d935098bdd9e97144f3ffce0f8690593c2623fbbd73a"
SOURCE_DECODED_SHA256 = "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8"
SOURCE_WRAPPER_SHA256 = "d4049cd35f3588259072ff9d05952c6bd830f6c1cd6181fc1d72b25b8cdc41ae"
RETAIL_CONSUMED = 908_864
RETAIL_STREAM_SHA256 = "beb71504d82a7634d73bf6603fb96d8d0ba33beb4fd0eaa870efd4007a8d3af8"
TAIL_SIZE = 16
TAIL_SHA256 = "cb57e42b9b8d9e1cba31e18c38dbc3347c8caa1361fcf7fe9cfad5b9f138fae4"
OUTSIDE_SHA256 = "8ef9522d0b4e4c5dfd9bb65c2e18d6ddf4c506ce5513f341701958666edc2bc6"

SCENE_INDEX = 2648
SHAPE_INDEX = 4
SHAPE_OFFSET = 0x7A00
SHAPE_SHA256 = "08a6f050e62929e1c4b1702f17c7bcd99a0d1c8ade97a2ba8d7edd8a92d25182"
TRANSFORM_OFFSET = 0x13100
TRANSFORM_SHA256 = "216582fd48a3aa6474a98c129bc7fd66089c394a7eebdb5f05f85f240549510c"
SUBMESH_OFFSET = 0x13170
SUBMESH_SHA256 = "03103543e6fd877f5cbe5d9ff31bb9092f8d50a4db5d27981a7930e2ee7834be"
PUSH_OFFSET = 0x131F0
PUSH_SIZE = 28
PUSH_SHA256 = "f1fe835f194447d442a92f13548fde128425d3b8e839f16971a389a96968d3f2"
POSITION_OFFSET = 0x13220
POSITION_SIZE = 48
SOURCE_POSITION_SHA256 = "65ab99a567a43ebe13c38f6921834896f56f609d954573bb3ae94d414562ab7d"
STREAM1_OFFSET = 0x13260
STREAM1_SIZE = 40
STREAM1_SHA256 = "a18f6c545d87d2fd892b9291e0b07e74152e8d6543d66ca4c09057a518b89847"

TARGET = {
    "chunk_index": 5,
    "decoded_sha256": SOURCE_DECODED_SHA256,
    "outer_id": "0xe4d6b0bc",
    "outer_index": ENTRY_INDEX,
    "position_stream_sha256": SOURCE_POSITION_SHA256,
    "scene_index": SCENE_INDEX,
    "scene_name": "stadium",
    "shape_index": SHAPE_INDEX,
    "shape_name": "group36",
}
ENCODING = {
    "component_type": "float32_le",
    "components_per_vertex": 3,
    "coordinate_space": "raw_xbox",
    "stride_bytes": 12,
    "vertex_count": 4,
}


class VerifyError(ValueError):
    """The copied-volume result violates an independently derived invariant."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def require_keys(value: object, expected: set[str], label: str) -> dict[str, object]:
    require(isinstance(value, dict) and set(value) == expected,
            f"{label} key set differs from v1")
    return value


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
        raise VerifyError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def require_distinct_files(source: Path, output: Path) -> None:
    """Reject pathname, symlink-resolved, and hardlink aliases."""
    source_stat = source.stat()
    output_stat = output.stat()
    require(
        source != output
        and (source_stat.st_dev, source_stat.st_ino) !=
            (output_stat.st_dev, output_stat.st_ino),
        "output volume path or inode aliases the retail source",
    )


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, label: str, maximum: int) -> tuple[dict[str, object], bytes]:
    path = regular(path, label)
    size = path.stat().st_size
    require(0 < size <= maximum, f"{label} size is outside its limit")
    payload = path.read_bytes()
    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                VerifyError(f"non-finite JSON constant {token} is forbidden")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerifyError(f"{label} is not UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict), f"{label} root must be an object")
    require(payload == canonical_json(value), f"{label} is not canonical sorted JSON")
    return value, payload


def _f32(value: object, label: str) -> float:
    require(type(value) in (int, float), f"{label} is not a JSON number")
    number = float(value)
    require(math.isfinite(number), f"{label} is non-finite")
    try:
        decoded = struct.unpack("<f", struct.pack("<f", number))[0]
    except (OverflowError, struct.error) as exc:
        raise VerifyError(f"{label} exceeds FLOAT3") from exc
    require(number == decoded, f"{label} is not exactly binary32")
    return decoded


def load_recipe(path: Path) -> dict[str, object]:
    value, payload = _load_json(path, "static-position recipe", MAX_RECIPE_BYTES)
    require(set(value) == {"schema", "target", "encoding", "positions"}
            and value.get("schema") == RECIPE_SCHEMA, "recipe fields/schema changed")
    require(value.get("target") == TARGET, "recipe target is not pinned group36")
    require(value.get("encoding") == ENCODING, "recipe encoding is not pinned FLOAT3")
    rows = value.get("positions")
    require(isinstance(rows, list) and len(rows) == 4, "recipe needs exactly four positions")
    packed = bytearray()
    for vertex, row in enumerate(rows):
        require(isinstance(row, list) and len(row) == 3,
                f"recipe vertex {vertex} is not XYZ")
        values = tuple(_f32(item, f"positions[{vertex}]") for item in row)
        packed.extend(struct.pack("<3f", *values))
    require(len(packed) == POSITION_SIZE, "recipe packed position length changed")
    return {"sha256": sha256(payload), "packed": bytes(packed)}


def _read_exact(path: Path, offset: int, size: int) -> bytes:
    with path.open("rb") as stream:
        stream.seek(offset)
        value = stream.read(size)
    require(len(value) == size, f"short read at 0x{offset:x}")
    return value


def parse_index(index: Path) -> dict[str, int]:
    index = regular(index, "NFL archive index")
    require(index.name == "0" and index.stat().st_size == INDEX_SIZE,
            "source index name/size changed")
    require(sha256_file(index) == INDEX_SHA256, "source index SHA-256 changed")
    head = _read_exact(index, 0, 0x9C)
    entry_count, reserved, pack_count = struct.unpack_from("<III", head)
    require((entry_count, reserved, pack_count) == (4323, 0, 16),
            "source index fixed header changed")
    blocks = struct.unpack_from("<36I", head, 0x0C)
    require(all(value > 0 for value in blocks[:pack_count])
            and all(value == 0 for value in blocks[pack_count:]),
            "source pack block roster changed")
    require(blocks[9] * 0x800 == PACK_SIZE, "source pack 9 extent changed")
    virtual_start = sum(blocks[:9]) * 0x800
    entry_offset = 0x9C + ENTRY_INDEX * 0x0C
    name_id, size, offset_blocks = struct.unpack("<III", _read_exact(index, entry_offset, 12))
    require((name_id, size, offset_blocks) ==
            (ENTRY_ID, ENTRY_SIZE, ENTRY_OFFSET_BLOCKS),
            "source outer directory entry 3280 changed")
    virtual = offset_blocks * 0x800
    require(virtual == ENTRY_VIRTUAL_OFFSET and virtual - virtual_start == ENTRY_PACK_OFFSET,
            "source entry 3280 physical mapping changed")
    return {"virtual_start": virtual_start, "entry_pack_offset": virtual - virtual_start}


def decompress_vc_lz(body: bytes, expected: int) -> tuple[bytes, dict[str, int]]:
    require(len(body) >= 10, "VC-LZ body is too short")
    declared, tag = struct.unpack_from("<II", body)
    bits = body[8]
    require(declared == expected and tag == 1 and bits == 12,
            "VC-LZ prefix differs from target")
    distance_mask = (1 << bits) - 1
    length_mask = (1 << (16 - bits)) - 1
    output = bytearray(expected)
    source = 10
    flags = body[9]
    flag_bit = 1
    target = 0
    literals = matches = 0
    while target < expected:
        if flags & flag_bit:
            require(source + 2 <= len(body), "truncated VC-LZ match")
            word = struct.unpack_from("<H", body, source)[0]
            source += 2
            distance = word & distance_mask
            length = ((word >> bits) & length_mask) + 3
            require(0 < distance <= target and target + length <= expected,
                    "invalid VC-LZ match")
            for index in range(length - 1, -1, -1):
                output[target + index] = output[target - distance + index]
            target += length
            matches += 1
        else:
            require(source < len(body), "truncated VC-LZ literal")
            output[target] = body[source]
            source += 1
            target += 1
            literals += 1
        flag_bit = (flag_bit << 1) & 0xFF
        if flag_bit == 0 and target < expected:
            require(source < len(body), "missing VC-LZ flag byte")
            flags = body[source]
            source += 1
            flag_bit = 1
    return bytes(output), {
        "consumed": source, "literals": literals, "matches": matches,
        "tag": tag, "offset_bits": bits,
    }


def minimum_overlap_scratch(body: bytes, stored_size: int, expected: int) -> int:
    require(len(body) >= 10, "VC-LZ body too short for scratch audit")
    declared = struct.unpack_from("<I", body)[0]
    bits = body[8]
    require(declared == expected and bits == 12, "VC-LZ scratch prefix changed")
    mask = (1 << bits) - 1
    length_mask = (1 << (16 - bits)) - 1
    source, flags, flag_bit, target, maximum = 10, body[9], 1, 0, 0
    while target < expected:
        if flags & flag_bit:
            require(source + 2 <= len(body), "truncated scratch match")
            word = struct.unpack_from("<H", body, source)[0]
            source += 2
            distance = word & mask
            length = ((word >> bits) & length_mask) + 3
            require(0 < distance <= target, "invalid scratch match")
        else:
            require(source < len(body), "truncated scratch literal")
            source += 1
            length = 1
        target += length
        require(target <= expected, "scratch token overruns output")
        if target < expected:
            maximum = max(maximum, stored_size - expected + target - source)
        flag_bit = (flag_bit << 1) & 0xFF
        if flag_bit == 0 and target < expected:
            require(source < len(body), "missing scratch flag")
            flags = body[source]
            source += 1
            flag_bit = 1
    return maximum


def s32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def resolve(data: bytes, field: int, limit: int, label: str) -> int | None:
    require(0 <= field <= limit - 4, f"{label} pointer field outside system")
    relative = s32(data, field)
    if relative == 0:
        return None
    target = field - 1 + relative
    require(0 <= target < limit, f"{label} pointer target outside system")
    return target


def utf16z(data: bytes, offset: int | None, limit: int, label: str) -> str:
    require(offset is not None and offset % 2 == 0, f"{label} pointer unavailable")
    cursor = int(offset)
    while cursor + 2 <= limit and data[cursor:cursor + 2] != b"\0\0":
        cursor += 2
    require(cursor + 2 <= limit, f"{label} string unterminated")
    try:
        return data[int(offset):cursor].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise VerifyError(f"{label} is invalid UTF-16LE") from exc


def parse_push(data: bytes, offset: int, words: int) -> list[int]:
    end = offset + words * 4
    require(end <= SYSTEM_BYTES, "push stream outside system")
    cursor = offset
    active: int | None = None
    indices: list[int] = []
    begin_modes: list[int] = []
    while cursor < end:
        header = u32(data, cursor)
        cursor += 4
        require((header & 0xE0030003) in (0, 0x40000000), "invalid push header")
        method = header & 0x1FFC
        count = (header >> 18) & 0x7FF
        require(cursor + count * 4 <= end, "push parameters exceed count")
        params = struct.unpack_from(f"<{count}I", data, cursor)
        cursor += count * 4
        require(method in (0x17FC, 0x1800), "unexpected group36 push method")
        if method == 0x17FC:
            for item in params:
                if item == 0:
                    require(active is not None, "push END without active primitive")
                    active = None
                else:
                    require(active is None, "nested push primitive")
                    active = item
                    begin_modes.append(item)
        else:
            require(active == 8, "group36 indices are not inside native QUADS")
            for item in params:
                indices.extend((item & 0xFFFF, item >> 16))
    require(cursor == end and active is None and begin_modes == [8],
            "group36 push batch boundary changed")
    return indices


def parse_target(decoded: bytes, expected_positions: bytes) -> dict[str, object]:
    require(len(decoded) == DECODED_SIZE and decoded[0x0C:0x10] == b"SCNE",
            "decoded output is not the pinned SCNE")
    name = utf16z(decoded, resolve(decoded, 0x10, SYSTEM_BYTES, "scene name"),
                  SYSTEM_BYTES, "scene name")
    descriptor = resolve(decoded, 0x14, SYSTEM_BYTES, "scene descriptor")
    require(name == "stadium" and descriptor == 0x100, "scene identity/descriptor changed")
    descriptor_name = utf16z(
        decoded, resolve(decoded, int(descriptor), SYSTEM_BYTES, "descriptor name"),
        SYSTEM_BYTES, "descriptor name",
    )
    require(descriptor_name == name, "descriptor and object names differ")
    shape_count = u32(decoded, int(descriptor) + 0x2C)
    shape_table = resolve(decoded, int(descriptor) + 0x30, SYSTEM_BYTES, "shape table")
    require(shape_count == 76 and shape_table is not None,
            "stadium shape table changed")
    shape = int(shape_table) + SHAPE_INDEX * 0x100
    require(shape == SHAPE_OFFSET and sha256(decoded[shape:shape + 0x100]) == SHAPE_SHA256,
            "group36 shape record changed")
    shape_name = utf16z(decoded, resolve(decoded, shape + 0x40, SYSTEM_BYTES, "shape name"),
                        SYSTEM_BYTES, "shape name")
    require(shape_name == "group36" and u32(decoded, shape + 0x44) == 2,
            "group36 name/version changed")
    counts = struct.unpack_from("<5H", decoded, shape + 0x4C)
    require(counts == (4, 0, 1, 0, 1), "group36 vertex/morph/transform/blend/submesh counts changed")
    declarations = struct.unpack_from("<16I", decoded, shape + 0x84)
    require(declarations == (
        0x00000032, 0x00080115, 0x00000002, 0x00000140,
        0x00000002, 0x00000002, 0x00040121, 0x00000002,
        0x00000002, 0x00000002, 0x00000002, 0x00000002,
        0x00000002, 0x00000002, 0x00000002, 0x00000002,
    ), "group36 vertex declaration changed")
    require(struct.unpack_from("<8H", decoded, shape + 0xC4) == (12, 10, 0, 0, 0, 0, 0, 0),
            "group36 stream strides changed")
    stream0 = resolve(decoded, shape + 0xD4, SYSTEM_BYTES, "position stream")
    stream1 = resolve(decoded, shape + 0xD8, SYSTEM_BYTES, "secondary stream")
    require(stream0 == POSITION_OFFSET and stream1 == STREAM1_OFFSET,
            "group36 stream pointers changed")
    require(decoded[POSITION_OFFSET:POSITION_OFFSET + POSITION_SIZE] == expected_positions,
            "output positions do not equal recipe")
    require(sha256(decoded[STREAM1_OFFSET:STREAM1_OFFSET + STREAM1_SIZE]) == STREAM1_SHA256,
            "group36 secondary stream changed")
    transform = resolve(decoded, shape + 0x64, SYSTEM_BYTES, "transform table")
    submesh = resolve(decoded, shape + 0x70, SYSTEM_BYTES, "submesh table")
    require(transform == TRANSFORM_OFFSET and submesh == SUBMESH_OFFSET,
            "group36 nested table pointers changed")
    require(sha256(decoded[TRANSFORM_OFFSET:TRANSFORM_OFFSET + 0x70]) == TRANSFORM_SHA256,
            "group36 transform bytes changed")
    require(struct.unpack_from("<4f", decoded, TRANSFORM_OFFSET + 0x40) == (0.0, 0.0, 0.0, 1.0)
            and struct.unpack_from("<4f", decoded, TRANSFORM_OFFSET + 0x50) == (0.0, 0.0, 0.0, 1.0)
            and s32(decoded, TRANSFORM_OFFSET + 0x64) == -1,
            "group36 is no longer a zero root transform")
    selectors = [struct.unpack_from("<h", decoded, STREAM1_OFFSET + i * 10 + 8)[0]
                 for i in range(4)]
    require(selectors == [0, 0, 0, 0], "group36 selectors changed")
    require(sha256(decoded[SUBMESH_OFFSET:SUBMESH_OFFSET + 0x80]) == SUBMESH_SHA256,
            "group36 submesh record changed")
    material_index, auxiliary = struct.unpack_from("<HH", decoded, SUBMESH_OFFSET)
    require((material_index, auxiliary) == (3, 1), "group36 submesh indices changed")
    material_count = u32(decoded, int(descriptor) + 0x1C)
    material_table = resolve(decoded, int(descriptor) + 0x20, SYSTEM_BYTES, "material table")
    require(material_count > 3 and material_table is not None, "material table changed")
    material_name = utf16z(
        decoded,
        resolve(decoded, int(material_table) + material_index * 0x80, SYSTEM_BYTES,
                "material name"),
        SYSTEM_BYTES, "material name",
    )
    require(material_name == "cement01", "group36 material changed")
    push = resolve(decoded, SUBMESH_OFFSET + 0x78, SYSTEM_BYTES, "push stream")
    primary, secondary = struct.unpack_from("<HH", decoded, SUBMESH_OFFSET + 0x7C)
    require(push == PUSH_OFFSET and (primary, secondary) == (7, 0),
            "group36 push pointer/count changed")
    require(sha256(decoded[PUSH_OFFSET:PUSH_OFFSET + PUSH_SIZE]) == PUSH_SHA256,
            "group36 push bytes changed")
    indices = parse_push(decoded, PUSH_OFFSET, primary)
    require(indices == [0, 1, 2, 3], "group36 native QUADS indices changed")
    return {"indices": indices, "material": material_name, "selectors": selectors}


def compare_packs(source: Path, output: Path) -> dict[str, object]:
    require(source.stat().st_size == output.stat().st_size == PACK_SIZE,
            "source/output volume sizes differ")
    outside = hashlib.sha256()
    changed = 0
    first: int | None = None
    last: int | None = None
    with source.open("rb") as left, output.open("rb") as right:
        remaining = CHUNK_START
        while remaining:
            size = min(8 * 1024 * 1024, remaining)
            a, b = left.read(size), right.read(size)
            require(len(a) == len(b) == size and a == b,
                    "pack changed before target chunk")
            outside.update(b)
            remaining -= size
        a, b = left.read(CHUNK_END - CHUNK_START), right.read(CHUNK_END - CHUNK_START)
        require(len(a) == len(b) == CHUNK_END - CHUNK_START,
                "short target chunk read")
        for local, (x, y) in enumerate(zip(a, b)):
            if x != y:
                absolute = CHUNK_START + local
                changed += 1
                first = absolute if first is None else first
                last = absolute
        remaining = PACK_SIZE - CHUNK_END
        while remaining:
            size = min(8 * 1024 * 1024, remaining)
            a, b = left.read(size), right.read(size)
            require(len(a) == len(b) == size and a == b,
                    "pack changed after target chunk")
            outside.update(b)
            remaining -= size
        require(left.read(1) == right.read(1) == b"", "pack has trailing bytes")
    require(outside.hexdigest() == OUTSIDE_SHA256,
            "outside-chunk hash changed")
    return {
        "changed_byte_count": changed,
        "first_changed_offset": first,
        "last_changed_offset": last,
        "outside_sha256": outside.hexdigest(),
    }


def _aligned16(value: int) -> int:
    return (value + 15) & ~15


def verify(index: Path, recipe_path: Path, output_dir: Path) -> dict[str, object]:
    parse_index(index)
    index = regular(index, "NFL archive index")
    source_pack = regular(index.parent / "9", "source volume 9")
    require(source_pack.stat().st_size == PACK_SIZE and sha256_file(source_pack) == PACK_SHA256,
            "source volume 9 identity changed")
    output_dir = output_dir.expanduser()
    output_info = output_dir.lstat()
    require(stat.S_ISDIR(output_info.st_mode) and not stat.S_ISLNK(output_info.st_mode),
            "output directory is invalid")
    output_dir = output_dir.resolve(strict=True)
    require(sorted(path.name for path in output_dir.iterdir()) == ["9", "manifest.json"],
            "output directory must contain only 9 and manifest.json")
    output_pack = regular(output_dir / "9", "output volume 9")
    manifest, manifest_payload = _load_json(
        output_dir / "manifest.json", "patch manifest", MAX_MANIFEST_BYTES
    )
    recipe = load_recipe(recipe_path)
    require_distinct_files(source_pack, output_pack)

    source_entry = _read_exact(source_pack, ENTRY_PACK_OFFSET, ENTRY_SIZE)
    require(sha256(source_entry) == ENTRY_SHA256, "source outer entry changed")
    source_span = _read_exact(source_pack, CHUNK_START, CHUNK_SPAN)
    output_span = _read_exact(output_pack, CHUNK_START, CHUNK_SPAN)
    require(sha256(source_span) == SOURCE_SPAN_SHA256, "source chunk span changed")
    require(sha256(source_span[:32]) == SOURCE_WRAPPER_SHA256, "source wrapper changed")
    source_fields = struct.unpack("<4s7I", source_span[:32])
    output_fields = struct.unpack("<4s7I", output_span[:32])
    require(source_fields == (b"SCNE", CHUNK_STORED, SYSTEM_BYTES, VIDEO_BYTES,
                              0xFEEDBEEF, 0x10, 0, 0),
            "source wrapper fields changed")
    require(output_fields[:5] == source_fields[:5] and output_fields[6:] == source_fields[6:],
            "output wrapper changed outside scratch +0x14")
    require(all(a == b for index_, (a, b) in enumerate(zip(source_span[:32], output_span[:32]))
                if not 0x14 <= index_ < 0x18),
            "output wrapper byte diff escaped scratch")

    source_body, output_body = source_span[32:], output_span[32:]
    source_decoded, source_lz = decompress_vc_lz(source_body, DECODED_SIZE)
    output_decoded, output_lz = decompress_vc_lz(output_body, DECODED_SIZE)
    require(source_lz == {"consumed": RETAIL_CONSUMED, "literals": 508197,
                          "matches": 158651, "tag": 1, "offset_bits": 12},
            "source VC-LZ metrics changed")
    require(sha256(source_body[:RETAIL_CONSUMED]) == RETAIL_STREAM_SHA256,
            "source compressed stream changed")
    require(sha256(source_decoded) == SOURCE_DECODED_SHA256,
            "source decoded SCNE changed")
    require(source_body[RETAIL_CONSUMED:] == output_body[RETAIL_CONSUMED:]
            and len(source_body[RETAIL_CONSUMED:]) == TAIL_SIZE
            and sha256(output_body[RETAIL_CONSUMED:]) == TAIL_SHA256,
            "fixed final 16-byte opaque tail changed")
    consumed = int(output_lz["consumed"])
    require(consumed <= RETAIL_CONSUMED, "output consumed stream overlaps fixed tail")
    require(not any(output_body[consumed:RETAIL_CONSUMED]),
            "new gap before fixed tail is not zero")
    padding = CHUNK_STORED - consumed
    alias = minimum_overlap_scratch(output_body[:consumed], CHUNK_STORED, DECODED_SIZE)
    required_scratch = _aligned16(max(padding, alias))
    require(output_fields[5] == required_scratch and required_scratch <= 0x40,
            "output scratch is not the exact bounded reconstruction")
    expected_positions = bytes(recipe["packed"])
    source_position = source_decoded[POSITION_OFFSET:POSITION_OFFSET + POSITION_SIZE]
    require(sha256(source_position) == SOURCE_POSITION_SHA256,
            "source position stream changed")
    require(output_decoded[POSITION_OFFSET:POSITION_OFFSET + POSITION_SIZE] == expected_positions,
            "decoded output positions differ from recipe")
    require(source_decoded[:POSITION_OFFSET] == output_decoded[:POSITION_OFFSET]
            and source_decoded[POSITION_OFFSET + POSITION_SIZE:] ==
                output_decoded[POSITION_OFFSET + POSITION_SIZE:],
            "decoded output changed outside the 48-byte position stream")
    target = parse_target(output_decoded, expected_positions)

    pack_diff = compare_packs(source_pack, output_pack)
    output_sha = sha256_file(output_pack)
    mode = "no_op" if expected_positions == source_position else "patched"
    if mode == "no_op":
        require(output_sha == PACK_SHA256 and pack_diff["changed_byte_count"] == 0
                and output_span == source_span,
                "no-op is not whole-volume byte-identical")
    else:
        require(output_sha != PACK_SHA256 and pack_diff["changed_byte_count"] > 0,
                "changed recipe did not change copied volume")

    require_keys(manifest, {
        "schema", "mode", "recipe", "target", "encoding", "source",
        "edit", "compression", "output", "claims",
    }, "manifest")
    require(manifest.get("schema") == PATCH_SCHEMA and manifest.get("mode") == mode,
            "manifest schema/mode differs from reconstructed result")
    require(manifest.get("target") == TARGET and manifest.get("encoding") == ENCODING,
            "manifest target/encoding changed")
    manifest_recipe = require_keys(
        manifest["recipe"],
        {"schema", "sha256", "contains_only_authored_positions_and_const_metadata"},
        "manifest recipe",
    )
    require(manifest_recipe == {
        "schema": RECIPE_SCHEMA,
        "sha256": recipe["sha256"],
        "contains_only_authored_positions_and_const_metadata": True,
    }, "manifest recipe reconstruction differs")
    manifest_source = require_keys(
        manifest["source"], {"index", "volume", "outer_entry", "resource"},
        "manifest source",
    )
    require_keys(manifest_source["index"], {"name", "size", "sha256"},
                 "manifest source index")
    require_keys(manifest_source["volume"],
                 {"name", "size", "sha256_before", "sha256_after", "modified"},
                 "manifest source volume")
    require_keys(manifest_source["outer_entry"], {
        "table_index", "name_id", "size", "offset_blocks", "virtual_offset",
        "pack_offset", "sha256",
    }, "manifest outer entry")
    require_keys(manifest_source["resource"], {
        "chunk_index", "entry_offset", "pack_span", "stored_size", "system_bytes",
        "video_bytes", "source_span_sha256", "source_decoded_sha256",
    }, "manifest resource")
    require(manifest_source["index"] ==
            {"name": "0", "sha256": INDEX_SHA256, "size": INDEX_SIZE},
            "manifest source index differs")
    require(manifest_source["volume"] == {
        "modified": False, "name": "9", "sha256_after": PACK_SHA256,
        "sha256_before": PACK_SHA256, "size": PACK_SIZE,
    }, "manifest source volume differs")
    require(manifest_source["outer_entry"] == {
        "table_index": ENTRY_INDEX, "name_id": "0xe4d6b0bc", "size": ENTRY_SIZE,
        "offset_blocks": ENTRY_OFFSET_BLOCKS, "virtual_offset": ENTRY_VIRTUAL_OFFSET,
        "pack_offset": ENTRY_PACK_OFFSET, "sha256": ENTRY_SHA256,
    }, "manifest outer-entry reconstruction differs")
    require(manifest_source["resource"] == {
        "chunk_index": CHUNK_INDEX, "entry_offset": CHUNK_ENTRY_OFFSET,
        "pack_span": [CHUNK_START, CHUNK_END], "stored_size": CHUNK_STORED,
        "system_bytes": SYSTEM_BYTES, "video_bytes": VIDEO_BYTES,
        "source_span_sha256": SOURCE_SPAN_SHA256,
        "source_decoded_sha256": SOURCE_DECODED_SHA256,
    }, "manifest resource reconstruction differs")
    changed_decoded = sum(a != b for a, b in zip(source_decoded, output_decoded))
    manifest_edit = require_keys(manifest["edit"], {
        "decoded_position_span", "position_before_sha256", "position_after_sha256",
        "decoded_after_sha256", "decoded_changed_byte_count",
        "every_decoded_byte_outside_position_span_bit_exact",
        "topology_transform_material_and_secondary_stream_bit_exact",
    }, "manifest edit")
    require(manifest_edit == {
        "decoded_position_span": [POSITION_OFFSET, POSITION_OFFSET + POSITION_SIZE],
        "position_before_sha256": SOURCE_POSITION_SHA256,
        "position_after_sha256": sha256(expected_positions),
        "decoded_after_sha256": sha256(output_decoded),
        "decoded_changed_byte_count": changed_decoded,
        "every_decoded_byte_outside_position_span_bit_exact": True,
        "topology_transform_material_and_secondary_stream_bit_exact": True,
    }, "manifest edit reconstruction differs")
    compression = require_keys(manifest["compression"], {
        "codec", "stream_tag", "offset_bits", "retail_consumed_bytes",
        "rebuilt_consumed_bytes", "rebuilt_stream_sha256",
        "zero_gap_before_fixed_tail_bytes", "total_stored_padding_bytes",
        "minimum_alias_scratch_bytes", "scratch_before", "scratch_after",
        "scratch_cap", "fixed_opaque_tail_bytes", "fixed_opaque_tail_sha256",
        "independent_decode_matches_edited_bytes",
    }, "manifest compression")
    require(compression["codec"] == "VC-LZ" and compression["stream_tag"] == 1
            and compression["offset_bits"] == 12
            and compression["retail_consumed_bytes"] == RETAIL_CONSUMED
            and compression["scratch_before"] == 0x10
            and compression["scratch_cap"] == 0x40
            and compression["fixed_opaque_tail_bytes"] == TAIL_SIZE
            and compression["independent_decode_matches_edited_bytes"] is True
            and compression["rebuilt_consumed_bytes"] == consumed
            and compression["rebuilt_stream_sha256"] == sha256(output_body[:consumed])
            and compression["zero_gap_before_fixed_tail_bytes"] == RETAIL_CONSUMED - consumed
            and compression["total_stored_padding_bytes"] == padding
            and compression["minimum_alias_scratch_bytes"] == alias
            and compression["scratch_after"] == required_scratch
            and compression["fixed_opaque_tail_sha256"] == TAIL_SHA256,
            "manifest compression reconstruction differs")
    manifest_output = require_keys(manifest["output"], {
        "volume_name", "volume_size", "volume_sha256", "outside_target_chunk_sha256",
        "outside_target_chunk_bit_exact", "wrapper_changed_only_scratch",
        "directory_files", "exclusive_manifest_contains_positions",
        "exclusive_manifest_contains_replacement_bytes",
    }, "manifest output")
    require(manifest_output == {
        "volume_name": "9", "volume_size": PACK_SIZE, "volume_sha256": output_sha,
        "outside_target_chunk_sha256": OUTSIDE_SHA256,
        "outside_target_chunk_bit_exact": True,
        "wrapper_changed_only_scratch": required_scratch != 0x10,
        "directory_files": ["9", "manifest.json"],
        "exclusive_manifest_contains_positions": False,
        "exclusive_manifest_contains_replacement_bytes": False,
    }, "manifest output reconstruction differs")
    require_keys(manifest["claims"], {
        "same_count_position_write_back", "changed_topology_write_back",
        "material_uv_skin_morph_or_transform_write_back",
        "xemu_runtime_visibility_proved", "original_xbox_runtime_visibility_proved",
        "production_ready",
    }, "manifest claims")
    require(manifest["claims"] == {
        "changed_topology_write_back": False,
        "material_uv_skin_morph_or_transform_write_back": False,
        "original_xbox_runtime_visibility_proved": False,
        "production_ready": False,
        "same_count_position_write_back": True,
        "xemu_runtime_visibility_proved": False,
    }, "manifest claim boundary changed")
    def contains_forbidden_key(item: object) -> bool:
        if isinstance(item, dict):
            return "positions" in item or "replacement_bytes" in item or any(
                contains_forbidden_key(value) for value in item.values()
            )
        if isinstance(item, list):
            return any(contains_forbidden_key(value) for value in item)
        return isinstance(item, (bytes, bytearray))

    require(not contains_forbidden_key(manifest),
            "exclusive manifest embeds authored positions or replacement bytes")
    require(sha256_file(index) == INDEX_SHA256 and sha256_file(source_pack) == PACK_SHA256,
            "retail source changed during verification")

    return {
        "schema": VERIFY_SCHEMA,
        "mode": mode,
        "recipe_sha256": recipe["sha256"],
        "manifest_sha256": sha256(manifest_payload),
        "source": {
            "index_sha256": INDEX_SHA256, "volume_sha256": PACK_SHA256,
            "source_unchanged": True,
        },
        "output": {
            "volume_size": PACK_SIZE, "volume_sha256": output_sha,
            "pack_changed_byte_count": pack_diff["changed_byte_count"],
            "first_changed_offset": pack_diff["first_changed_offset"],
            "last_changed_offset": pack_diff["last_changed_offset"],
            "outside_chunk_sha256": pack_diff["outside_sha256"],
            "outside_chunk_bit_exact": True,
        },
        "decoded": {
            "source_sha256": SOURCE_DECODED_SHA256,
            "output_sha256": sha256(output_decoded),
            "position_before_sha256": SOURCE_POSITION_SHA256,
            "position_after_sha256": sha256(expected_positions),
            "outside_position_bit_exact": True,
        },
        "compression": {
            "consumed_bytes": consumed, "retail_cap": RETAIL_CONSUMED,
            "zero_gap_bytes": RETAIL_CONSUMED - consumed,
            "padding_bytes": padding, "minimum_alias_scratch_bytes": alias,
            "scratch_bytes": required_scratch, "fixed_tail_sha256": TAIL_SHA256,
        },
        "rigid_static": {
            "one_zero_root": True, "selectors": target["selectors"],
            "material": target["material"], "native_quads_indices": target["indices"],
        },
        "claims": {
            "same_count_position_write_back": True,
            "topology_write_back": False, "runtime_proved": False,
            "production_ready": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-index", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = verify(args.source_index, args.recipe, args.output_dir)
    if args.report is not None:
        require(not args.report.exists(), f"refusing to overwrite report: {args.report}")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(canonical_json(report))
    print(
        "NFL_GROUP36_POSITION_VERIFY_PASS "
        f"mode={report['mode']} consumed={report['compression']['consumed_bytes']} "
        f"scratch={report['compression']['scratch_bytes']} runtime=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerifyError, struct.error, KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"error: {exc}") from exc
