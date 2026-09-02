#!/usr/bin/env python3
"""Prove the selected APF player_shadow skin and glTF contract.

This is a read-only, deterministic join over the shipped SCNE bytes, the
selected embedded Xenos vertex shader, and focused XEX/Ghidra evidence.  It
does not guess a generic APF skin format: every exported rule is scoped to
outer 1310 / inner 415 / SCNE player_shadow.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any, Iterable

import apf_inner
import apf_outer


SCHEMA = "apf_player_shadow_skin_semantics/v1"
OUTER_INDEX = 1310
INNER_INDEX = 415
RESOURCE_NAME = "player_shadow"
EXPECTED_SYSTEM_SIZE = 0x5B80
EXPECTED_SYSTEM_SHA256 = "2042ce844a84a3f4b311bd8554b81744555d3efd6f2e4b5cac6c28a2e0735819"
EXPECTED_XEX_MD5 = "217eea6084c3d03f0f1143802b1f5636"
EXPECTED_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"

NODE_OFFSET = 0x160
HIERARCHY_OFFSET = 0x1C00
HIERARCHY_COUNT = 21
HIERARCHY_STRIDE = 0x30
DRAW_OFFSET = 0x1FF0
DECLARATION_OFFSET = 0x2510
MESH_OFFSET = 0x2650
STREAM_RECORD_OFFSET = 0x2664
STREAM_OFFSET = 0x267C
STREAM_END = 0x525C
STREAM_STRIDE = 32
VERTEX_COUNT = 351
INDEX_COUNT = 615
VERTEX_SHADER_OFFSET = 0x0B98
VERTEX_SHADER_SIZE = 0x04E4
VERTEX_SHADER_SHA256 = "1f21ebe4488f9d4163c186dfc808cd548b92b0343704c88f453268dba646f288"
XENOSRECOMP_HLSL_SHA256 = "8cd25351644ea47b9b2c274f386a7e8df41daf4bfd58a95851763d050175913e"

XENOSRECOMP_REPOSITORY = "https://github.com/hedge-dev/XenosRecomp"
XENOSRECOMP_COMMIT = "990d03b28a27b50277ee5d8d942e1c5f873869d1"
XENIA_REPOSITORY = "https://github.com/xenia-project/xenia"
XENIA_COMMIT = "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"
GLTF_SPEC = "https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html"


EXPECTED_TRACE_RANGES = [
    (0x84A11B58, 0x84A11D88),
    (0x84A12EF0, 0x84A130E0),
    (0x84AA4288, 0x84AA4348),
    (0x84AA4728, 0x84AA4774),
    (0x84B0E7F0, 0x84B0E8C0),
    (0x84B0FA88, 0x84B0FBF4),
    (0x84B10438, 0x84B1054C),
    (0x84B10630, 0x84B10994),
    (0x84B10998, 0x84B10B48),
    (0x84B10B48, 0x84B10BE4),
    (0x84B24C88, 0x84B24CE0),
    (0x84B27510, 0x84B27AD0),
    (0x84B27AD0, 0x84B27B78),
    (0x84B2BDD0, 0x84B2BF6C),
    (0x84B2D4A8, 0x84B2D604),
]

TRACE_WORDS = {
    # Direct hierarchy-order inverse-bind palette builder.
    0x84B0E7F4: 0x81640064,
    0x84B0E7FC: 0x81440060,
    0x84B0E804: 0x19A10710,
    0x84B0E82C: 0x100058C3,
    0x84B0E834: 0x14003890,
    0x84B0E83C: 0x396B0030,
    0x84B0E85C: 0x38A50040,
    0x84B0E880: 0x15A069D0,
    0x84B0E888: 0x158061D0,
    0x84B0E88C: 0x140059D0,
    0x84B0E890: 0x19416F10,
    0x84B0E894: 0x19216710,
    0x84B0E898: 0x19010710,
    0x84B0E8A8: 0x7D8041CE,
    0x84B0E8AC: 0x7C0019CE,
    0x84B0E8B0: 0x38630030,
    0x84B0E8B4: 0x7DA049CE,
    # Descriptor allocation and queue ownership.
    0x84B10454: 0x817E0060,
    0x84B10460: 0x556A083C,
    0x84B1046C: 0x556B2036,
    0x84B104D8: 0x915F0000,
    0x84B104DC: 0x913F0008,
    0x84B104E0: 0x917F0004,
    0x84B104F4: 0x4BFFE2FD,
    0x84B10714: 0x93740028,
    0x84B10A58: 0x937C0028,
    # Draw consumer and generic Xenos constant descriptor upload.
    0x84B2D4EC: 0x808B0028,
    0x84B2D50C: 0x80BE001C,
    0x84B27548: 0x81760004,
    0x84B27560: 0x82F60008,
    0x84B276A8: 0x81560000,
    0x84B276AC: 0x83B6000C,
    0x84B276C0: 0x554B477E,
    0x84B27754: 0x93AB000C,
    0x84B27758: 0x912B0010,
    # Final stream binding reads stride/pointer, but not serialized flags.
    0x84B27AF0: 0xA1640004,
    0x84B27B34: 0x80E90008,
    0x84B27B38: 0x81290014,
}

VMX_EXPECTED = {
    0x84B0E804: ("vrlimi128", "v13,v0,1,0"),
    0x84B0E834: ("vmulfp128", "v0,v0,v7"),
    0x84B0E854: ("vmrghw", "v9,v13,v11"),
    0x84B0E880: ("vmsum4fp128", "v13,v0,v13"),
    0x84B0E888: ("vmsum4fp128", "v12,v0,v12"),
    0x84B0E88C: ("vmsum4fp128", "v0,v0,v11"),
    0x84B0E890: ("vrlimi128", "v10,v13,1,0"),
    0x84B0E894: ("vrlimi128", "v9,v12,1,0"),
    0x84B0E898: ("vrlimi128", "v8,v0,1,0"),
}

EXPECTED_VERTEX_ELEMENTS = [
    (5, "POSITION", 0),
    (6, "NORMAL", 0),
    (7, "TANGENT", 0),
    (8, "BLENDWEIGHT", 0),
    (9, "BLENDINDICES", 0),
]

USAGES = {
    0: "POSITION",
    1: "BLENDWEIGHT",
    2: "BLENDINDICES",
    3: "NORMAL",
    4: "POINTSIZE",
    5: "TEXCOORD",
    6: "TANGENT",
    7: "BINORMAL",
    10: "COLOR",
}


class SkinSemanticsError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SkinSemanticsError(message)


def digest_bytes(data: bytes, algorithm: str = "sha256") -> str:
    return hashlib.new(algorithm, data).hexdigest()


def digest_file(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def i16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">h", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def f32x4(data: bytes, offset: int) -> tuple[float, float, float, float]:
    value = struct.unpack_from(">4f", data, offset)
    require(all(math.isfinite(component) for component in value),
            f"non-finite float4 at 0x{offset:x}")
    return value


def f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def utf16be_relative(data: bytes, field: int) -> tuple[str, int]:
    raw = u32(data, field)
    require(raw != 0, f"null string pointer at 0x{field:x}")
    target = field + raw - 1
    require(0 <= target < len(data), f"string pointer at 0x{field:x} is out of bounds")
    chars: list[str] = []
    cursor = target
    while True:
        codepoint = u16(data, cursor)
        cursor += 2
        if codepoint == 0:
            return "".join(chars), target
        require(codepoint < 0xD800 or codepoint > 0xDFFF,
                f"surrogate in string at 0x{target:x}")
        chars.append(chr(codepoint))


def read_selected_system(index_path: Path) -> tuple[bytes, dict[str, Any]]:
    archive = apf_outer.parse_archive(index_path)
    matches = [entry for entry in archive.entries if entry.table_index == OUTER_INDEX]
    require(len(matches) == 1, "selected outer entry is not unique")
    entry = matches[0]
    require(entry.head_hex == "ff3bef94", "selected outer entry is not a VC IFF")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        files = [item for item in record.files if item.index == INNER_INDEX]
        require(len(files) == 1, "selected inner file is not unique")
        selected = files[0]
        require(selected.type_name == "SCNE" and selected.name == RESOURCE_NAME,
                "selected inner identity changed")
        require(len(selected.parts) >= 1, "selected SCNE has no system part")
        part = selected.parts[0]
        block = apf_inner.decode_block(
            reader, record, part.block_index, apf_inner.DEFAULT_MAX_DECOMPRESSED
        )
        system = block[part.offset:part.offset + part.length]
    metadata = {
        "index_path": str(index_path),
        "outer_table_index": OUTER_INDEX,
        "outer_name_id": f"0x{entry.name_id:08x}",
        "inner_file_index": INNER_INDEX,
        "inner_name": selected.name,
        "inner_type": selected.type_name,
        "system_part": {
            "block_index": part.block_index,
            "offset": part.offset,
            "length": part.length,
        },
    }
    return system, metadata


def load_scene_inventory(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    inventory = json.loads(path.read_text(encoding="utf-8"))
    require(inventory.get("schema") == "apf_scene_inventory/v1",
            "unexpected APF scene inventory schema")
    matches = [
        item for item in inventory["scenes"]
        if item.get("outer_table_index") == OUTER_INDEX
        and item.get("inner_file_index") == INNER_INDEX
        and item.get("root_name") == RESOURCE_NAME
    ]
    require(len(matches) == 1, "selected scene inventory row is not unique")
    return inventory, matches[0]


def parse_hierarchy(system: bytes, inventory_scene: dict[str, Any]) -> list[dict[str, Any]]:
    node = inventory_scene["nodes"][0]
    inventory_hierarchy = node["hierarchy"]
    require(inventory_hierarchy["offset"] == HIERARCHY_OFFSET,
            "hierarchy offset changed")
    require(inventory_hierarchy["record_offset"] == HIERARCHY_OFFSET,
            "hierarchy record offset changed")
    require(inventory_hierarchy["byte_length"] == HIERARCHY_COUNT * HIERARCHY_STRIDE,
            "hierarchy byte length changed")
    require(inventory_hierarchy["count"] == HIERARCHY_COUNT,
            "hierarchy count changed")
    rows: list[dict[str, Any]] = []
    recursive_globals: list[tuple[float, float, float]] = []
    for joint in range(HIERARCHY_COUNT):
        record = HIERARCHY_OFFSET + joint * HIERARCHY_STRIDE
        metadata = record + 0x20
        name, name_offset = utf16be_relative(system, metadata)
        parent = i16(system, metadata + 8)
        first_child = i16(system, metadata + 10)
        next_sibling = i16(system, metadata + 12)
        reserved = u16(system, metadata + 14)
        bind = f32x4(system, record)
        local = f32x4(system, record + 0x10)
        require(bind[3] == 1.0 and local[3] == 1.0,
                f"joint {joint} translation w changed")
        require(parent == -1 if joint == 0 else 0 <= parent < joint,
                f"joint {joint} parent ordering is invalid")
        if parent < 0:
            recursive = local[:3]
        else:
            recursive = tuple(
                f32(recursive_globals[parent][axis] + local[axis])
                for axis in range(3)
            )
        recursive_globals.append(recursive)  # type: ignore[arg-type]
        error = max(abs(recursive[axis] - bind[axis]) for axis in range(3))
        inventory_record = inventory_hierarchy["records"][joint]
        require(inventory_record["name"] == name and
                inventory_record["parent"] == parent,
                f"joint {joint} metadata disagrees with scene inventory")
        require(inventory_record["offset"] == record,
                f"joint {joint} inventory record offset changed")
        require(tuple(inventory_record["vector_a"]) == bind,
                f"inventory vector_a cross-check failed at joint {joint}")
        require(tuple(inventory_record["vector_b"]) == local,
                f"inventory vector_b cross-check failed at joint {joint}")
        bind_m = [component * 0.01 for component in bind[:3]]
        local_m = [component * 0.01 for component in local[:3]]
        inverse_bind_column_major = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            -bind_m[0], -bind_m[1], -bind_m[2], 1.0,
        ]
        rows.append({
            "joint": joint,
            "name": name,
            "name_offset": name_offset,
            "name_crc32": f"0x{u32(system, metadata + 4):08x}",
            "parent": parent,
            "first_child": first_child,
            "next_sibling": next_sibling,
            "reserved_u16": reserved,
            "record_offset": record,
            "metadata_offset": metadata,
            "bind_global_cm": list(bind[:3]),
            "local_bind_cm": list(local[:3]),
            "recursive_bind_global_cm": list(recursive),
            "recursive_error_cm": error,
            "gltf_node_translation_m": local_m,
            "gltf_inverse_bind_column_major": inverse_bind_column_major,
            "palette_float4_start": joint * 3,
            "palette_byte_offset": joint * 0x30,
        })
    require(max(row["recursive_error_cm"] for row in rows) == 0.0,
            "shipped bind globals are not exact float32 recursive local sums")
    return rows


def parse_vertices(system: bytes, joints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    require(u32(system, STREAM_RECORD_OFFSET) == 0x40000000,
            "selected stream flag changed")
    require(u32(system, STREAM_RECORD_OFFSET + 4) == 1, "selected stream disabled")
    require(u32(system, STREAM_RECORD_OFFSET + 8) == STREAM_STRIDE,
            "selected stream stride changed")
    require(u32(system, STREAM_RECORD_OFFSET + 0xC) == VERTEX_COUNT * STREAM_STRIDE,
            "selected stream length changed")
    stream = system[STREAM_OFFSET:STREAM_END]
    require(len(stream) == VERTEX_COUNT * STREAM_STRIDE, "selected stream bounds changed")
    rows: list[dict[str, Any]] = []
    for vertex in range(VERTEX_COUNT):
        offset = vertex * STREAM_STRIDE
        raw_indices = tuple(stream[offset + 24:offset + 28])
        raw_weights = tuple(stream[offset + 28:offset + 32])
        # Xenos k8in32 reverses each fetched dword before 8_8_8_8 unpacking.
        fetch_indices = tuple(reversed(raw_indices))
        fetch_weight_bytes = tuple(reversed(raw_weights))
        fetch_weights = tuple(value / 255.0 for value in fetch_weight_bytes)
        require(fetch_indices[1:] == (0, 0, 0),
                f"vertex {vertex} has more than one live index")
        require(fetch_weight_bytes == (255, 0, 0, 0),
                f"vertex {vertex} is not one-hot weighted")
        palette_row = fetch_indices[0]
        require(palette_row % 3 == 0, f"vertex {vertex} index is not a palette row triplet")
        joint = palette_row // 3
        require(0 <= joint < HIERARCHY_COUNT, f"vertex {vertex} joint is out of range")
        rows.append({
            "vertex": vertex,
            "stream_offset": STREAM_OFFSET + offset,
            "raw_blendindices": raw_indices,
            "raw_blendweights": raw_weights,
            "fetch_blendindices": fetch_indices,
            "fetch_blendweights": fetch_weights,
            "palette_row_offset": palette_row,
            "joint": joint,
            "joint_name": joints[joint]["name"],
            "gltf_joints_0": (joint, 0, 0, 0),
            "gltf_weights_0": (1.0, 0.0, 0.0, 0.0),
        })
    return rows


def c_string(data: bytes, offset: int) -> str:
    require(0 <= offset < len(data), f"C string offset 0x{offset:x} out of bounds")
    end = data.find(b"\0", offset)
    require(end >= 0, f"unterminated C string at 0x{offset:x}")
    return data[offset:end].decode("ascii")


def parse_shader(system: bytes) -> dict[str, Any]:
    container = system[VERTEX_SHADER_OFFSET:VERTEX_SHADER_OFFSET + VERTEX_SHADER_SIZE]
    require(len(container) == VERTEX_SHADER_SIZE, "vertex shader slice is truncated")
    require(digest_bytes(container) == VERTEX_SHADER_SHA256, "vertex shader hash changed")
    flags, virtual_size, physical_size = struct.unpack_from(">3I", container, 0)
    require((flags, virtual_size, physical_size) == (0x102A1101, 0x27C, 0x268),
            "vertex shader container header changed")
    require(virtual_size + physical_size == len(container),
            "vertex shader virtual/physical sizes changed")
    constant_table_offset = u32(container, 0x10)
    definition_table_offset = u32(container, 0x14)
    shader_offset = u32(container, 0x18)
    require((constant_table_offset, definition_table_offset, shader_offset) ==
            (0x24, 0x1F4, 0x21C), "vertex shader table offsets changed")

    constant_container = constant_table_offset
    constant_base = constant_container + 4
    require(u32(container, constant_container) == 0x1CC, "constant table size changed")
    table_size, creator_offset, version, constant_count, info_offset, table_flags, target_offset = \
        struct.unpack_from(">7I", container, constant_base)
    require(table_size == 0x1C and constant_count == 9, "constant table shape changed")
    constants: list[dict[str, Any]] = []
    for index in range(constant_count):
        offset = constant_base + info_offset + index * 20
        name_offset, register_set, register_index, register_count, reserved, type_offset, default_offset = \
            struct.unpack_from(">IHHHHII", container, offset)
        name = c_string(container, constant_base + name_offset)
        constants.append({
            "index": index,
            "name": name,
            "register_set": register_set,
            "register_index": register_index,
            "register_count": register_count,
            "reserved": reserved,
            "type_offset": type_offset,
            "default_value_offset": default_offset,
        })
    matrix_constants = [item for item in constants if item["name"] == "__MATRIX_LIST"]
    require(matrix_constants == [{
        "index": 4,
        "name": "__MATRIX_LIST",
        "register_set": 2,
        "register_index": 40,
        "register_count": 216,
        "reserved": 0,
        "type_offset": 0x14C,
        "default_value_offset": 0,
    }], "matrix constant reflection changed")

    shader = shader_offset
    physical_offset, instruction_size = struct.unpack_from(">2I", container, shader)
    field18 = u32(container, shader + 0x18)
    element_count = u32(container, shader + 0x1C)
    field20 = u32(container, shader + 0x20)
    require((physical_offset, instruction_size, field18, element_count, field20) ==
            (0x40, 0x228, 1, 5, 5), "vertex shader declaration header changed")
    array_base = shader + 0x24
    elements: list[dict[str, Any]] = []
    for index in range(element_count):
        word = u32(container, array_base + (field18 + index) * 4)
        address = word & 0xFFF
        usage = (word >> 12) & 0xF
        usage_index = (word >> 16) & 0xF
        elements.append({
            "index": index,
            "raw": f"0x{word:08x}",
            "address": address,
            "usage": USAGES.get(usage, f"UNKNOWN_{usage}"),
            "usage_index": usage_index,
        })
    require([(row["address"], row["usage"], row["usage_index"]) for row in elements]
            == EXPECTED_VERTEX_ELEMENTS, "vertex shader inputs changed")
    return {
        "system_offset": VERTEX_SHADER_OFFSET,
        "byte_length": len(container),
        "sha256": digest_bytes(container),
        "flags": f"0x{flags:08x}",
        "virtual_size": virtual_size,
        "physical_size": physical_size,
        "constant_table_offset": constant_table_offset,
        "definition_table_offset": definition_table_offset,
        "shader_offset": shader_offset,
        "creator": c_string(container, constant_base + creator_offset),
        "target": c_string(container, constant_base + target_offset),
        "version": f"0x{version:08x}",
        "constant_table_flags": f"0x{table_flags:08x}",
        "constants": constants,
        "vertex_elements": elements,
        "xenosrecomp": {
            "repository": XENOSRECOMP_REPOSITORY,
            "commit": XENOSRECOMP_COMMIT,
            "generated_hlsl_sha256": XENOSRECOMP_HLSL_SHA256,
            "command": "XenosRecomp player_shadow.vertex.bin player_shadow.vertex.hlsl XenosRecomp/shader_common.h",
            "limitations": "XenosRecomp documents game-specific vertex-fetch handling; raw container reflection and shipped vertex invariants are validated independently here.",
            "proved_body_contract": {
                "input_copy": "r7.xyz = iBlendWeight0.xyz; r0.xyz = iBlendIndices0.xyz",
                "live_lanes": "only BLENDWEIGHT0.xyz and BLENDINDICES0.xyz are consumed; w is ignored",
                "index_rounding": "a0 = clamp(floor(index + 0.5), -256, 255)",
                "palette_rows": "__MATRIX_LIST(a0+0), __MATRIX_LIST(a0+1), __MATRIX_LIST(a0+2)",
                "matrix_constant_register": "__MATRIX_LIST starts at c40",
            },
        },
    }


def trace_words(path: Path) -> dict[int, int]:
    result: dict[int, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == "RAW32":
            result[int(fields[1], 16)] = int(fields[2], 16)
    return result


def validate_trace(path: Path) -> tuple[list[dict[str, Any]], dict[int, int]]:
    words = trace_words(path)
    for address, expected in TRACE_WORDS.items():
        require(words.get(address) == expected,
                f"trace word at 0x{address:08X} changed")
    ranges: list[dict[str, Any]] = []
    observed_spans: list[tuple[int, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0] != "RAW_RANGE":
            continue
        first, after = int(fields[1], 16), int(fields[2], 16)
        declared_bytes = int(fields[3].split("=", 1)[1])
        declared_hash = fields[4].split("=", 1)[1]
        require(after - first == declared_bytes, "trace range length mismatch")
        payload = b"".join(words[address].to_bytes(4, "big")
                           for address in range(first, after, 4))
        require(len(payload) == declared_bytes, f"trace range 0x{first:x} has missing words")
        actual_hash = digest_bytes(payload)
        require(actual_hash == declared_hash, f"trace range 0x{first:x} hash mismatch")
        observed_spans.append((first, after))
        ranges.append({
            "first": f"0x{first:08X}",
            "after_last": f"0x{after:08X}",
            "bytes": declared_bytes,
            "sha256": actual_hash,
        })
    require(observed_spans == EXPECTED_TRACE_RANGES, "focused trace ranges changed")
    return ranges, words


def validate_vmx(path: Path) -> dict[int, tuple[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    parsed = {
        int(row["address"], 16): (row["mnemonic"], row["operands"])
        for row in rows
    }
    for address, expected in VMX_EXPECTED.items():
        require(parsed.get(address) == expected,
                f"VMX decode at 0x{address:08X} changed")
    return parsed


def write_vertices(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "vertex", "stream_offset", "raw_blendindices", "raw_blendweights",
        "fetch_blendindices", "fetch_blendweights", "palette_row_offset",
        "joint", "joint_name", "gltf_joints_0", "gltf_weights_0",
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **row,
                "stream_offset": f"0x{row['stream_offset']:04x}",
                "raw_blendindices": ",".join(str(value) for value in row["raw_blendindices"]),
                "raw_blendweights": ",".join(str(value) for value in row["raw_blendweights"]),
                "fetch_blendindices": ",".join(str(value) for value in row["fetch_blendindices"]),
                "fetch_blendweights": ",".join(f"{value:.9g}" for value in row["fetch_blendweights"]),
                "gltf_joints_0": ",".join(str(value) for value in row["gltf_joints_0"]),
                "gltf_weights_0": ",".join(f"{value:.1f}" for value in row["gltf_weights_0"]),
            })


def write_joints(path: Path, rows: list[dict[str, Any]], counts: Counter[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "joint", "name", "parent", "first_child", "next_sibling",
        "record_offset", "metadata_offset",
        "bind_global_x_cm", "bind_global_y_cm", "bind_global_z_cm",
        "local_bind_x_cm", "local_bind_y_cm", "local_bind_z_cm",
        "recursive_error_cm", "palette_float4_start", "palette_byte_offset",
        "inverse_bind_tx_m", "inverse_bind_ty_m", "inverse_bind_tz_m",
        "node_translation_x_m", "node_translation_y_m", "node_translation_z_m",
        "vertex_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            bind = row["bind_global_cm"]
            local = row["local_bind_cm"]
            ibm = row["gltf_inverse_bind_column_major"]
            node = row["gltf_node_translation_m"]
            writer.writerow({
                "joint": row["joint"], "name": row["name"], "parent": row["parent"],
                "first_child": row["first_child"], "next_sibling": row["next_sibling"],
                "record_offset": f"0x{row['record_offset']:04x}",
                "metadata_offset": f"0x{row['metadata_offset']:04x}",
                "bind_global_x_cm": bind[0], "bind_global_y_cm": bind[1],
                "bind_global_z_cm": bind[2], "local_bind_x_cm": local[0],
                "local_bind_y_cm": local[1], "local_bind_z_cm": local[2],
                "recursive_error_cm": row["recursive_error_cm"],
                "palette_float4_start": row["palette_float4_start"],
                "palette_byte_offset": f"0x{row['palette_byte_offset']:03x}",
                "inverse_bind_tx_m": ibm[12], "inverse_bind_ty_m": ibm[13],
                "inverse_bind_tz_m": ibm[14], "node_translation_x_m": node[0],
                "node_translation_y_m": node[1], "node_translation_z_m": node[2],
                "vertex_count": counts[row["joint"]],
            })


def write_shader_tsv(path: Path, shader: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str, str, str]] = [
        ("container", "0x0b98", shader["sha256"], "embedded vertex shader container SHA-256"),
        ("reflection", "c40", "__MATRIX_LIST[216]", "matrix palette float4 register array"),
        ("input", "HLSL:266", "BLENDWEIGHT0.xyz", "only xyz is copied to r7.xyz"),
        ("input", "HLSL:267", "BLENDINDICES0.xyz", "only xyz is copied to r0.xyz"),
        ("index", "HLSL:356/361/367", "round(z), round(y), round(x)", "three influence lanes"),
        ("palette", "HLSL:357-371", "c[a0+0],c[a0+1],c[a0+2]", "index is a float4 row offset, not a joint ordinal"),
        ("position", "HLSL:372-374", "three homogeneous dots", "position consumes three palette columns"),
        ("provenance", XENOSRECOMP_COMMIT, XENOSRECOMP_HLSL_SHA256, "pinned XenosRecomp generated-HLSL hash"),
    ]
    for element in shader["vertex_elements"]:
        rows.append((
            "vertex_element", f"address={element['address']}", element["raw"],
            f"{element['usage']}{element['usage_index']}",
        ))
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("category", "source", "raw_or_expression", "meaning"))
        writer.writerows(rows)


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parent.parent
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--index", type=Path,
                        default=root / "extracted/All-Pro Football 2K8 (USA)/0A")
    result.add_argument("--xex", type=Path,
                        default=root / "extracted/All-Pro Football 2K8 (USA)/default.xex")
    result.add_argument("--scene-inventory", type=Path,
                        default=root / "reports/assets/apf_scene_inventory.json")
    result.add_argument("--trace", type=Path,
                        default=root / "reports/assets/apf_player_shadow_skin_semantics_ghidra/player_shadow_skin_palette_trace.txt")
    result.add_argument("--pseudo", type=Path,
                        default=root / "reports/assets/apf_player_shadow_skin_semantics_ghidra/player_shadow_skin_palette_focused_pseudo_c.c")
    result.add_argument("--vmx", type=Path,
                        default=root / "reports/assets/apf_player_shadow_skin_semantics_ghidra/player_shadow_skin_palette_vmx128.tsv")
    result.add_argument("--nfl-contract", type=Path,
                        default=root / "reports/assets/nfl_transform_semantics.json")
    result.add_argument("--json", type=Path,
                        default=root / "reports/assets/apf_player_shadow_skin_semantics.json")
    result.add_argument("--vertices-tsv", type=Path,
                        default=root / "reports/assets/apf_player_shadow_skin_vertices.tsv")
    result.add_argument("--joints-tsv", type=Path,
                        default=root / "reports/assets/apf_player_shadow_skin_joints.tsv")
    result.add_argument("--shader-tsv", type=Path,
                        default=root / "reports/assets/apf_player_shadow_vertex_shader_contract.tsv")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    require(digest_file(args.xex, "md5") == EXPECTED_XEX_MD5, "APF XEX MD5 changed")
    require(digest_file(args.xex) == EXPECTED_XEX_SHA256, "APF XEX SHA-256 changed")
    system, source = read_selected_system(args.index)
    require(len(system) == EXPECTED_SYSTEM_SIZE, "selected SCNE size changed")
    require(digest_bytes(system) == EXPECTED_SYSTEM_SHA256, "selected SCNE hash changed")
    _, inventory_scene = load_scene_inventory(args.scene_inventory)
    require(inventory_scene["system_sha256"] == EXPECTED_SYSTEM_SHA256,
            "scene inventory selected system hash changed")
    require(inventory_scene["nodes"][0]["offset"] == NODE_OFFSET,
            "selected node offset changed")
    require(inventory_scene["nodes"][0]["draw_record_offset"] == DRAW_OFFSET,
            "selected draw offset changed")
    require(inventory_scene["nodes"][0]["mesh_descriptor_offset"] == MESH_OFFSET,
            "selected mesh offset changed")
    require(inventory_scene["nodes"][0]["index_count"] == INDEX_COUNT,
            "selected index count changed")
    require(inventory_scene["nodes"][0]["vertex_declarations"][0]["offset"] == DECLARATION_OFFSET,
            "selected declaration offset changed")
    require(u32(system, DRAW_OFFSET + 0x1C) == 0,
            "selected draw acquired an optional palette remap")

    joints = parse_hierarchy(system, inventory_scene)
    vertices = parse_vertices(system, joints)
    shader = parse_shader(system)
    trace_ranges, _ = validate_trace(args.trace)
    validate_vmx(args.vmx)
    pseudo_text = args.pseudo.read_text(encoding="utf-8")
    require("Recovered contract from 0x84B0E7F0" in pseudo_text,
            "focused pseudo-C lost recovered palette contract")
    require("PORTME before 0x84B27AD0" in pseudo_text,
            "focused pseudo-C lost address-specific fetch PORTME")

    nfl = json.loads(args.nfl_contract.read_text(encoding="utf-8"))
    nfl_equation = nfl["proved_contract"]["base_skin_palette_equation"]
    require("T(-absolute_bind_translation)" in nfl_equation,
            "NFL cross-title inverse-bind equation changed")

    joint_counts: Counter[int] = Counter(row["joint"] for row in vertices)
    palette_rows = Counter(row["palette_row_offset"] for row in vertices)
    expected_palette_rows = {
        0: 28, 6: 23, 9: 21, 12: 37, 18: 23, 21: 21, 24: 37,
        27: 49, 36: 8, 39: 8, 42: 17, 45: 46, 54: 8, 57: 8, 60: 17,
    }
    require(dict(sorted(palette_rows.items())) == expected_palette_rows,
            "selected influence histogram changed")
    used_joints = sorted(joint_counts)
    require(used_joints == [0, 2, 3, 4, 6, 7, 8, 9, 12, 13, 14, 15, 18, 19, 20],
            "selected used-joint set changed")
    max_recursive_error = max(row["recursive_error_cm"] for row in joints)

    report = {
        "schema": SCHEMA,
        "selection": {
            **source,
            "resource_name": RESOURCE_NAME,
            "system_size": len(system),
            "system_sha256": digest_bytes(system),
            "node_offset": f"0x{NODE_OFFSET:04x}",
            "mesh_offset": f"0x{MESH_OFFSET:04x}",
            "stream_offset": f"0x{STREAM_OFFSET:04x}",
            "stream_end": f"0x{STREAM_END:04x}",
            "vertex_count": VERTEX_COUNT,
            "index_count": INDEX_COUNT,
        },
        "executable": {
            "path": str(args.xex),
            "md5": EXPECTED_XEX_MD5,
            "sha256": EXPECTED_XEX_SHA256,
            "focused_trace": str(args.trace),
            "focused_pseudo_c": str(args.pseudo),
            "vmx128_tsv": str(args.vmx),
            "trace_ranges": trace_ranges,
        },
        "corrected_hierarchy_layout": {
            "count": HIERARCHY_COUNT,
            "table_offset": f"0x{HIERARCHY_OFFSET:04x}",
            "record_stride": "0x30",
            "record_fields": {
                "+0x00": "float4 bind-global translation",
                "+0x10": "float4 parent-local bind translation",
                "+0x20": "self-relative UTF-16BE name pointer",
                "+0x24": "CRC32 name",
                "+0x28": "i16 parent",
                "+0x2a": "i16 first child",
                "+0x2c": "i16 next sibling",
                "+0x2e": "u16 reserved",
            },
            "scene_inventory_cross_check": "apf_scene_inventory/v1 starts at the first 0x30-byte record, keeps each record's two vectors with its own metadata, and includes both vectors on the terminal row; all 21 rows are byte-cross-checked here",
            "recursive_global_max_error_cm": max_recursive_error,
            "rest_rotation": "identity for all 21 rows; bind_global = parent bind_global + local translation exactly in float32",
        },
        "vertex_influences": {
            "stream_flags": "0x40000000",
            "stream_stride": STREAM_STRIDE,
            "blendindices": {"offset": 24, "format": "uint8x4", "format_code": "0x001a2286"},
            "blendweights": {"offset": 28, "format": "unorm8x4", "format_code": "0x001a2086"},
            "all_raw_indices_equation": "raw bytes = [0,0,0,N]",
            "all_raw_weights_equation": "raw bytes = [0,0,0,255]",
            "k8in32_fetch_equation": "fetch reverses each dword: index=[N,0,0,0], weight=[1,0,0,0]",
            "shader_index_equation": "palette_float4_row = round(BLENDINDICES0 lane); joint = palette_float4_row / 3",
            "gltf_equation": "JOINTS_0=[joint,0,0,0], WEIGHTS_0=[1,0,0,0]",
            "palette_row_histogram": {str(key): value for key, value in sorted(palette_rows.items())},
            "used_joints": used_joints,
            "unused_joints": sorted(set(range(HIERARCHY_COUNT)) - set(used_joints)),
            "all_vertex_rows_validated": len(vertices),
            "low_level_lane_invariance": "even before the serialized stream flag is symbolized, the only live byte is one-hot and any of shader lanes x/y/z selects the same N with weight 1; the emitted glTF influence is therefore exact",
        },
        "xenos_vertex_shader": shader,
        "xex_skin_palette": {
            "current_global_builder": {
                "address": "0x84B0FA88",
                "equation": "current_global[j] = local[j] * (parent current_global or external_root); local translation += hierarchy[j].local_bind",
            },
            "palette_builder": {
                "address": "0x84B0E7F0",
                "inputs": "r3=destination data, r4=SCNE scene object, r5=current globals",
                "row_vector_equation": "skin_row[j] = T(-bind_global[j]) * current_global[j]",
                "output": "three float4 columns per joint, 0x30 bytes; current stride 0x40; hierarchy stride 0x30",
                "order": "direct hierarchy order; no lookup/remap",
                "rest_cancellation": "T(-bind_global) * T(bind_global) = identity for every shipped joint",
            },
            "descriptor_builder": {
                "address": "0x84B10438",
                "header": "flags=0xE3000000, count=21, stride=48, data=header+16",
                "payload_float4_count": 63,
            },
            "queue": {
                "primary_store": "0x84B10714 -> draw packet +0x28",
                "alternate_store": "0x84B10A58 -> draw packet +0x28",
            },
            "renderer_consumer": {
                "address": "0x84B2D4A8",
                "packet_load": "0x84B2D4EC loads packet +0x28",
                "generic_uploader": "0x84B27510 reads descriptor flags/count/stride/data and emits the constant-write command",
                "command_callback": "0x84B24C88 -> 0x84BA45B8",
                "vertex_stream_binding": "0x84B27AD0 reads resulting stream count/stride/pointer; it does not read serialized flag 0x40000000",
            },
        },
        "gltf_contract": {
            "specification": GLTF_SPEC,
            "skin_joints": "all hierarchy nodes 0..20 in direct order",
            "node_translation": "hierarchy.local_bind_xyz_cm * 0.01, retain XYZ",
            "node_rotation": "identity at bind; animated quaternion conversion is proved in apf_animation_transform_semantics/v1",
            "inverse_bind_matrix": "column-major T(-bind_global_xyz_cm * 0.01)",
            "vertex_joints": "[palette_row/3,0,0,0]",
            "vertex_weights": "[1,0,0,0]",
            "palette_equivalence": "transpose(APF T(-bind)*current) = glTF current_column * inverseBind_column",
            "external_root": "keep the separately proved player_shadow_external_root parent outside the skin joint list",
        },
        "cross_title": {
            "nfl_report": str(args.nfl_contract),
            "nfl_column_vector_equation": nfl_equation,
            "equivalence": "NFL current*T(-bind) column convention is the transpose of APF's T(-bind)*current row convention",
        },
        "decision": {
            "blendindices_blendweights_decoded_for_every_vertex": True,
            "palette_order_and_no_remap_proved": True,
            "bind_current_equation_proved": True,
            "renderer_descriptor_upload_proved": True,
            "inverse_bind_matrices_proved": True,
            "exact_selected_gltf_skin_contract_ready": True,
            "complete_selected_skinned_gltf_export_ready": True,
            "serialized_stream_flag_to_xenos_endian_symbolized": False,
            "official_final_xdk_constant_helper_name_proved": False,
        },
        "portme": [
            "// PORTME before 0x84B27AD0: name the earlier GPU-buffer creation instruction that maps SCNE stream flag 0x40000000 to Xenos k8in32; the selected one-hot glTF result is lane-invariant.",
            "// PORTME at 0x84B24C88 -> 0x84BA45B8: assign the official XDK/Xenos symbol name to the final constant-write helper; the direct 63-float4 upload handoff is already proved.",
        ],
    }

    write_vertices(args.vertices_tsv, vertices)
    write_joints(args.joints_tsv, joints, joint_counts)
    write_shader_tsv(args.shader_tsv, shader)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                         encoding="utf-8")
    print(
        "APF_PLAYER_SHADOW_SKIN_SEMANTICS_COMPLETE "
        f"joints={len(joints)} vertices={len(vertices)} used={len(used_joints)} "
        "palette=direct ibm=T(-bind) gltf_ready=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
