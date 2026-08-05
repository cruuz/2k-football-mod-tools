#!/usr/bin/env python3
"""Recover the exact selected APF player_shadow surface/material boundary.

The scope is intentionally narrow: outer 1310 (global.iff), inner 415
(SCNE/player_shadow), system bytes SHA-256 2042ce84....  The tool exports the
proved normal/UV authoring channels to a separately named glTF derivative.
It never invents a texture binding or material when the shipped bytes only
provide a runtime interface.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any
import zlib

import apf_inner
import apf_outer


SCHEMA = "apf_player_shadow_surface_materials/v1"
OUTER_INDEX = 1310
OUTER_NAME_ID = 0xDB5E3E48
OUTER_VIRTUAL_OFFSET = 22480896
OUTER_SIZE = 25028608
INNER_INDEX = 415
INNER_ID = 0xEA7614F3
SYSTEM_SIZE = 0x5B80
SYSTEM_SHA256 = "2042ce844a84a3f4b311bd8554b81744555d3efd6f2e4b5cac6c28a2e0735819"
XEX_MD5 = "217eea6084c3d03f0f1143802b1f5636"
XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"

DRAW_OFFSET = 0x1FF0
DECLARATION_OFFSET = 0x2510
STREAM_OFFSET = 0x267C
STREAM_STRIDE = 32
VERTEX_COUNT = 351
PIXEL_SHADER_OFFSET = 0x107C
PIXEL_SHADER_SIZE = 0x774
PIXEL_SHADER_SHA256 = "c7e1ed011010fef44591c7c477ac3c18582282cd2fe205dd9489b0b6c77ad383"
VERTEX_SHADER_OFFSET = 0x0B98
VERTEX_SHADER_SIZE = 0x4E4
VERTEX_SHADER_SHA256 = "1f21ebe4488f9d4163c186dfc808cd548b92b0343704c88f453268dba646f288"

CANONICAL_GLTF_SHA256 = "cf93ad2660e13b7b8999350d85d4a7fdd67abaaab54da687b8b090af8644bc2d"
CANONICAL_BIN_SHA256 = "574229cf5c8dfa0946ad81f47585f6b01442956b32afc5fe2cbc28910d4a4bd1"
XENOSRECOMP_REPOSITORY = "https://github.com/hedge-dev/XenosRecomp"
XENOSRECOMP_COMMIT = "990d03b28a27b50277ee5d8d942e1c5f873869d1"
VERTEX_HLSL_SHA256 = "8cd25351644ea47b9b2c274f386a7e8df41daf4bfd58a95851763d050175913e"
PIXEL_HLSL_SHA256 = "89da3cf04a5061841b97659ece0ea74d51dd6eff90c994bbf5fe064b77c7e4fe"

SAMPLER_DESCRIPTOR_OFFSETS = {
    "GlossOcclusionMap": 0x0A0C,
    "BaseMap": 0x0A30,
    "NormalMap": 0x0A54,
    "SpecularLightmapSampler": 0x0A78,
    "GroundShadowSampler": 0x0A9C,
}

EXPECTED_SAMPLERS = {
    "BaseMap": (0, "sampler2D", 0x178),
    "NormalMap": (1, "sampler2D", 0x178),
    "GlossOcclusionMap": (2, "sampler2D", 0x178),
    "GroundShadowSampler": (3, "sampler2D", 0x178),
    "SpecularLightmapSampler": (4, "samplerCUBE", 0x30C),
}

EXPECTED_TRACE_RANGES = {
    (0x849CF280, 0x849CF340): "9dafaaa0790f18deca90df079e276b6e678bde1d3ba721287e590adbde78f517",
    (0x84AA4728, 0x84AA4774): "6cf7de327a90eacf464947c8f00e9f3e20b346a0d161951967f612097fa822b9",
    (0x84B107A4, 0x84B108E8): "3dee202d7b8229a9cee746d9588209f2c0c90a5305e7ef8e9869293da2769b9f",
    (0x84B14640, 0x84B149F8): "5e5148e7c792b8dd6c3e471b8668f4e7ed984f5e8072fb2e554c48fc7969e503",
    (0x84B14DA0, 0x84B14F80): "8a57da5c387dc0e3f6303ff419d588100c24a0f0e317ce4080c191daadb54521",
    (0x84B14F80, 0x84B14FF4): "44bfa9fc17136d8b35da29de556f396b230953c3b9d50962656c35d2cda810a0",
    (0x84B15488, 0x84B15B80): "7cdadb092b1f86b712cdb18a6f092186be4ad356fb1f4bc7c0339f8fad963a4a",
    (0x84B47790, 0x84B47834): "5358cd92a43946d83acedc15233f5584f53e0f848af869d16f8f1277b355394d",
}

EXPECTED_TRACE_WORDS = {
    0x849CF2D0: 0x80AB007C,  # instance material array
    0x849CF2DC: 0x481418BD,  # wrapper call
    0x84B107B8: 0x816B0020,  # draw +0x20 material slot
    0x84B107BC: 0x1D6B00F0,  # slot * 0xf0
    0x84B107C0: 0x7F4B9A14,  # add material base
    0x84B14F98: 0x3BE4008C,  # shader mapping +0x8c
    0x84B14FA4: 0x2F0B0008,  # value 8 is unused
    0x84B14FB0: 0x7C8BEA14,  # material texture-record address
    0x84B14FCC: 0x80C40000,  # live texture object
    0x84B14FD8: 0x4BFFFDC9,  # bind one texture/sampler
    0x84B15AB8: 0x817B00AC,  # pixel shader +0xac mapping-present field
    0x84B15AD8: 0x3BBB008C,  # eight-entry shader mapping
    0x84B15AF4: 0x7C8BF214,  # material +0x50+0x14*n
    0x84B15B1C: 0x4BFFF285,  # bind one texture/sampler
    0x84B15B28: 0x2F1C0008,  # exactly eight slots
    0x84B47818: 0x4BFCDC71,  # renderer -> material apply
}

NAME_ONLY_CANDIDATES = {
    "blank_nm": (47, 0x1DEA09AE, "TXTR"),
    "lightmap_player_clothspecular": (49, 0x1EFBF04A, "TXTR"),
    "lightmap_player_specular": (409, 0xE91BFBEF, "TXTR"),
}


class SurfaceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SurfaceError(message)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def c_string(data: bytes, offset: int) -> str:
    require(0 <= offset < len(data), f"string offset 0x{offset:x} is out of bounds")
    end = data.find(b"\0", offset)
    require(end >= 0, f"unterminated string at 0x{offset:x}")
    return data[offset:end].decode("ascii")


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def snorm16(value: int) -> float:
    return f32(max(value / 32767.0, -1.0))


def read_selection(index_path: Path) -> tuple[bytes, dict[str, Any], tuple[apf_inner.DataFile, ...]]:
    archive = apf_outer.parse_archive(index_path)
    matches = [entry for entry in archive.entries if entry.table_index == OUTER_INDEX]
    require(len(matches) == 1, "outer 1310 is not unique")
    entry = matches[0]
    require(entry.name_id == OUTER_NAME_ID, "outer name ID changed")
    require(entry.virtual_offset == OUTER_VIRTUAL_OFFSET and entry.size == OUTER_SIZE,
            "outer virtual offset/size changed")
    require(entry.head_hex == "ff3bef94", "outer is no longer VC IFF")
    require(len(entry.segments) == 1 and entry.segments[0].pack_name == "0A",
            "outer 1310 is no longer a single 0A segment")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        require(len(record.blocks) == 3, "global.iff block count changed")
        require([block.name_hash for block in record.blocks] == [
            zlib.crc32(name.encode("ascii")) & 0xFFFFFFFF
            for name in ("DRAM", "VRAM", "SRAM")
        ], "global.iff DRAM/VRAM/SRAM ownership changed")
        files = [item for item in record.files if item.index == INNER_INDEX]
        require(len(files) == 1, "inner 415 is not unique")
        selected = files[0]
        require((selected.file_id, selected.name, selected.type_name) ==
                (INNER_ID, "player_shadow", "SCNE"), "selected file identity changed")
        require(len(selected.parts) == 1, "selected SCNE acquired another block part")
        part = selected.parts[0]
        require((part.block_index, part.offset, part.length) == (0, 3633664, SYSTEM_SIZE),
                "selected DRAM part changed")
        block = apf_inner.decode_block(
            reader, record, part.block_index, apf_inner.DEFAULT_MAX_DECOMPRESSED)
        system = block[part.offset:part.offset + part.length]
        all_files = record.files
    require(len(system) == SYSTEM_SIZE and sha_bytes(system) == SYSTEM_SHA256,
            "selected system bytes changed")
    source = {
        "index_path": str(index_path.resolve()),
        "outer_table_index": OUTER_INDEX,
        "outer_name": "global.iff",
        "outer_name_id": f"0x{OUTER_NAME_ID:08x}",
        "outer_virtual_offset": OUTER_VIRTUAL_OFFSET,
        "outer_size": OUTER_SIZE,
        "segments": [{"pack": "0A", "pack_offset": OUTER_VIRTUAL_OFFSET,
                      "size": OUTER_SIZE}],
        "iff_blocks": ["DRAM", "VRAM", "SRAM"],
        "inner_file_index": INNER_INDEX,
        "inner_file_id": f"0x{INNER_ID:08x}",
        "inner_name": "player_shadow",
        "inner_type": "SCNE",
        "parts": [{"block": "DRAM", "block_index": 0,
                   "offset": part.offset, "length": part.length}],
        "has_vram_part": False,
        "system_size": len(system),
        "system_sha256": sha_bytes(system),
    }
    return system, source, all_files


def validate_scene_inventory(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    matches = [row for row in document["scenes"]
               if row.get("outer_table_index") == OUTER_INDEX
               and row.get("inner_file_index") == INNER_INDEX
               and row.get("root_name") == "player_shadow"]
    require(len(matches) == 1, "scene inventory selection is not unique")
    node = matches[0]["nodes"][0]
    declarations = node["vertex_declarations"]
    require(declarations[0]["offset"] == DECLARATION_OFFSET, "declaration offset changed")
    expected = [
        ("POSITION", 0, "snorm16x4"),
        ("NORMAL", 8, "snorm16x4"),
        ("TANGENT", 16, "snorm16x4"),
        ("BLENDINDICES", 24, "uint8x4"),
        ("BLENDWEIGHT", 28, "unorm8x4"),
    ]
    observed = [(row["semantic"], row["byte_offset"], row["format_name"])
                for row in declarations]
    require(observed == expected, "selected vertex declarations changed")
    require(not any(row["semantic"] == "TEXCOORD" for row in declarations),
            "selected stream unexpectedly gained TEXCOORD")
    return {
        "path": str(path.resolve()),
        "sha256": sha_file(path),
        "declaration_offset": f"0x{DECLARATION_OFFSET:04x}",
        "declarations": declarations,
        "has_texcoord_declaration": False,
    }


def parse_pixel_shader(system: bytes) -> dict[str, Any]:
    container = system[PIXEL_SHADER_OFFSET:PIXEL_SHADER_OFFSET + PIXEL_SHADER_SIZE]
    require(len(container) == PIXEL_SHADER_SIZE and sha_bytes(container) == PIXEL_SHADER_SHA256,
            "pixel shader container changed")
    flags, virtual_size, physical_size = struct.unpack_from(">3I", container, 0)
    require((flags, virtual_size, physical_size) == (0x102A1100, 0x3B0, 0x3C4),
            "pixel shader header changed")
    require(virtual_size + physical_size == len(container), "pixel shader sizes disagree")
    constant_table_offset, definition_offset, shader_offset = struct.unpack_from(">3I", container, 0x10)
    require((constant_table_offset, definition_offset, shader_offset) == (0x24, 0x358, 0x380),
            "pixel shader table offsets changed")
    base = constant_table_offset + 4
    require(u32(container, constant_table_offset) == 0x330, "pixel constant table size changed")
    table_size, creator_offset, version, count, info_offset, table_flags, target_offset = \
        struct.unpack_from(">7I", container, base)
    require((table_size, version, count, info_offset, table_flags) ==
            (0x1C, 0xFFFF0300, 17, 0x1C, 0x1000), "pixel reflection header changed")
    constants: list[dict[str, Any]] = []
    for index in range(count):
        offset = base + info_offset + index * 20
        name_offset, register_set, register_index, register_count, reserved, type_offset, default_offset = \
            struct.unpack_from(">IHHHHII", container, offset)
        row: dict[str, Any] = {
            "index": index,
            "name": c_string(container, base + name_offset),
            "register_set": register_set,
            "register_index": register_index,
            "register_count": register_count,
            "reserved": reserved,
            "type_offset": f"0x{type_offset:x}",
            "default_offset": f"0x{default_offset:x}" if default_offset else None,
        }
        if default_offset:
            row["default_float4"] = list(struct.unpack_from(">4f", container, base + default_offset))
        constants.append(row)
    samplers: list[dict[str, Any]] = []
    by_name = {row["name"]: row for row in constants}
    for name, (register, kind, type_offset) in sorted(
            EXPECTED_SAMPLERS.items(), key=lambda item: item[1][0]):
        reflected = by_name.get(name)
        require(reflected is not None, f"missing reflected sampler {name}")
        require((reflected["register_set"], reflected["register_index"],
                 reflected["register_count"], reflected["type_offset"]) ==
                (3, register, 1, f"0x{type_offset:x}"), f"sampler {name} reflection changed")
        descriptor_offset = SAMPLER_DESCRIPTOR_OFFSETS[name]
        words = list(struct.unpack_from(">9I", system, descriptor_offset))
        expected_crc = zlib.crc32(name.encode("ascii")) & 0xFFFFFFFF
        require(words[0] == expected_crc, f"serialized sampler CRC changed for {name}")
        coordinate = (
            "TEXCOORD0.w/TEXCOORD1.w -> (u,v)=(2*NORMAL0.w,2*TANGENT0.w)"
            if name in {"BaseMap", "NormalMap", "GlossOcclusionMap"}
            else "TEXCOORD3.xy generated from world position and SunXZToShadowScale"
            if name == "GroundShadowSampler"
            else "cube reflection direction generated by pixel shader"
        )
        samplers.append({
            "name": name,
            "register": register,
            "kind": kind,
            "reflection_type_offset": f"0x{type_offset:x}",
            "serialized_descriptor_offset": f"0x{descriptor_offset:04x}",
            "serialized_name_crc32": f"0x{expected_crc:08x}",
            "serialized_words": [f"0x{word:08x}" for word in words],
            "coordinate": coordinate,
            "concrete_resource": None,
        })
    return {
        "system_offset": f"0x{PIXEL_SHADER_OFFSET:04x}",
        "byte_length": len(container),
        "sha256": sha_bytes(container),
        "flags": f"0x{flags:08x}",
        "virtual_size": virtual_size,
        "physical_size": physical_size,
        "creator": c_string(container, base + creator_offset),
        "target": c_string(container, base + target_offset),
        "constants": constants,
        "samplers": samplers,
        "xenosrecomp": {
            "repository": XENOSRECOMP_REPOSITORY,
            "commit": XENOSRECOMP_COMMIT,
            "generated_pixel_hlsl_sha256": PIXEL_HLSL_SHA256,
            "generated_vertex_hlsl_sha256": VERTEX_HLSL_SHA256,
            "commands": [
                "XenosRecomp player_shadow.vertex.bin player_shadow.vertex.hlsl shader_common.h",
                "XenosRecomp player_shadow.pixel.bin player_shadow.pixel.hlsl shader_common.h",
            ],
            "body_contract": {
                "vertex_normal_w": "oTexCoord0.w = iNormal0.w + iNormal0.w",
                "vertex_tangent_w": "oTexCoord1.w = iTangent0.w + iTangent0.w",
                "pixel_uv_select": "r5.xy = select(c251.zy == 0, iTexCoord1.ww, iTexCoord0.ww); c251=(1.5,1,0,1.9921875)",
                "shared_2d_uv": "BaseMap, NormalMap, and GlossOcclusionMap all fetch at r5.yx = (2*NORMAL0.w,2*TANGENT0.w)",
                "ground_uv": "GroundShadowSampler fetches generated iTexCoord3.xy",
                "cube_direction": "SpecularLightmapSampler fetches a generated cube reflection vector",
            },
            "limitation": "The generated HLSL hashes pin the translator result; raw containers, reflection, descriptor CRCs, declarations, and all-vertex invariants are independently validated here.",
        },
    }


def parse_surface(system: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for vertex in range(VERTEX_COUNT):
        base = STREAM_OFFSET + vertex * STREAM_STRIDE
        normal_raw = struct.unpack_from(">4h", system, base + 8)
        tangent_raw = struct.unpack_from(">4h", system, base + 16)
        normal = tuple(snorm16(value) for value in normal_raw)
        tangent = tuple(snorm16(value) for value in tangent_raw)
        uv = (f32(2.0 * normal[3]), f32(2.0 * tangent[3]))
        normal_length = f32(math.sqrt(sum(value * value for value in normal[:3])))
        tangent_length = f32(math.sqrt(sum(value * value for value in tangent[:3])))
        rows.append({
            "vertex": vertex,
            "stream_offset": base,
            "normal_raw_i16": normal_raw,
            "tangent_raw_i16": tangent_raw,
            "normal_xyz": normal[:3],
            "tangent_xyz": tangent[:3],
            "normal_w": normal[3],
            "tangent_w": tangent[3],
            "uv": uv,
            "normal_xyz_length": normal_length,
            "tangent_xyz_length": tangent_length,
        })
    require(all(abs(row["normal_xyz_length"] - 1.0) < 0.001 for row in rows),
            "normal XYZ unit invariant failed")
    require(all(abs(row["tangent_xyz_length"] - 1.0) < 0.001 for row in rows),
            "tangent XYZ unit invariant failed")
    require(len({row["uv"] for row in rows}) == 278, "packed UV unique count changed")
    return rows


def scan_static_links(system: bytes, files: tuple[apf_inner.DataFile, ...]) -> list[dict[str, Any]]:
    by_id: dict[int, list[apf_inner.DataFile]] = {}
    for item in files:
        by_id.setdefault(item.file_id, []).append(item)
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(system) - 3, 4):
        value = u32(system, offset)
        for item in by_id.get(value, []):
            rows.append({
                "system_offset": offset,
                "value": value,
                "inner_file_index": item.index,
                "name": item.name,
                "type": item.type_name,
            })
    require([(row["system_offset"], row["value"], row["inner_file_index"])
             for row in rows] == [
                 (0x164, INNER_ID, INNER_INDEX),
                 (0x254, INNER_ID, INNER_INDEX),
                 (0x274, INNER_ID, INNER_INDEX),
             ], "selected SCNE aligned file-ID scan changed")
    for name, (index, file_id, kind) in NAME_ONLY_CANDIDATES.items():
        matches = [item for item in files if item.index == index]
        require(len(matches) == 1 and (matches[0].name, matches[0].file_id,
                matches[0].type_name) == (name, file_id, kind),
                f"name-only candidate {name} changed")
    return rows


def trace_words(path: Path) -> dict[int, int]:
    words: dict[int, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == "RAW32":
            words[int(fields[1], 16)] = int(fields[2], 16)
    return words


def validate_trace(path: Path, pseudo: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    words = trace_words(path)
    for address, expected in EXPECTED_TRACE_WORDS.items():
        require(words.get(address) == expected, f"trace word 0x{address:08x} changed")
    observed: dict[tuple[int, int], str] = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 5 and fields[0] == "RAW_RANGE":
            observed[(int(fields[1], 16), int(fields[2], 16))] = fields[4].split("=", 1)[1]
    require(observed == EXPECTED_TRACE_RANGES, "focused XEX trace ranges changed")
    pseudo_text = pseudo.read_text(encoding="utf-8")
    for needle in (
        "material + 0x50 + 0x14*n",
        "PORTME at 0x84B15488",
        "PORTME at 0x84B14DA0 -> 0x84B28EA0",
        "PORTME at 0x84AA4728",
    ):
        require(needle in pseudo_text, f"focused pseudo-C lost {needle}")
    return {
        "trace_path": str(path.resolve()),
        "trace_sha256": sha_file(path),
        "trace_ranges": [{"first": f"0x{first:08x}", "after_last": f"0x{after:08x}",
                          "sha256": digest}
                         for (first, after), digest in EXPECTED_TRACE_RANGES.items()],
        "pseudo_c_path": str(pseudo.resolve()),
        "pseudo_c_sha256": sha_file(pseudo),
    }


def write_surface_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "vertex", "stream_offset", "normal_raw_i16", "tangent_raw_i16",
        "normal_x", "normal_y", "normal_z", "normal_w",
        "tangent_x", "tangent_y", "tangent_z", "tangent_w",
        "uv_u", "uv_v", "normal_xyz_length", "tangent_xyz_length",
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "vertex": row["vertex"],
                "stream_offset": f"0x{row['stream_offset']:04x}",
                "normal_raw_i16": ",".join(map(str, row["normal_raw_i16"])),
                "tangent_raw_i16": ",".join(map(str, row["tangent_raw_i16"])),
                "normal_x": repr(row["normal_xyz"][0]),
                "normal_y": repr(row["normal_xyz"][1]),
                "normal_z": repr(row["normal_xyz"][2]),
                "normal_w": repr(row["normal_w"]),
                "tangent_x": repr(row["tangent_xyz"][0]),
                "tangent_y": repr(row["tangent_xyz"][1]),
                "tangent_z": repr(row["tangent_xyz"][2]),
                "tangent_w": repr(row["tangent_w"]),
                "uv_u": repr(row["uv"][0]),
                "uv_v": repr(row["uv"][1]),
                "normal_xyz_length": repr(row["normal_xyz_length"]),
                "tangent_xyz_length": repr(row["tangent_xyz_length"]),
            })


def write_samplers_tsv(path: Path, samplers: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["name", "register", "kind", "descriptor_offset", "name_crc32",
              "coordinate", "concrete_resource"]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in samplers:
            writer.writerow({
                "name": row["name"], "register": row["register"], "kind": row["kind"],
                "descriptor_offset": row["serialized_descriptor_offset"],
                "name_crc32": row["serialized_name_crc32"], "coordinate": row["coordinate"],
                "concrete_resource": "PORTME: runtime binding not captured",
            })


def write_links_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("system_offset", "value", "inner_file_index", "name", "type", "classification"))
        for row in rows:
            writer.writerow((f"0x{row['system_offset']:04x}", f"0x{row['value']:08x}",
                             row["inner_file_index"], row["name"], row["type"], "self-reference"))


def emit_gltf(canonical_gltf: Path, canonical_bin: Path, output_gltf: Path,
              output_bin: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    require(sha_file(canonical_gltf) == CANONICAL_GLTF_SHA256, "canonical skin glTF changed")
    require(sha_file(canonical_bin) == CANONICAL_BIN_SHA256, "canonical skin binary changed")
    document = json.loads(canonical_gltf.read_text(encoding="utf-8"))
    binary = bytearray(canonical_bin.read_bytes())
    prefix_length = len(binary)
    normal_offset = len(binary)
    for row in rows:
        binary.extend(struct.pack("<3f", *row["normal_xyz"]))
    uv_offset = len(binary)
    for row in rows:
        binary.extend(struct.pack("<2f", *row["uv"]))
    require(normal_offset % 4 == 0 and uv_offset % 4 == 0, "new buffer view is unaligned")
    normal_view = len(document["bufferViews"])
    document["bufferViews"].append({
        "buffer": 0, "byteLength": VERTEX_COUNT * 12,
        "byteOffset": normal_offset, "target": 34962,
    })
    uv_view = len(document["bufferViews"])
    document["bufferViews"].append({
        "buffer": 0, "byteLength": VERTEX_COUNT * 8,
        "byteOffset": uv_offset, "target": 34962,
    })
    normal_accessor = len(document["accessors"])
    normal_values = [row["normal_xyz"] for row in rows]
    document["accessors"].append({
        "bufferView": normal_view, "componentType": 5126, "count": VERTEX_COUNT,
        "max": [max(value[axis] for value in normal_values) for axis in range(3)],
        "min": [min(value[axis] for value in normal_values) for axis in range(3)],
        "type": "VEC3",
    })
    uv_accessor = len(document["accessors"])
    uv_values = [row["uv"] for row in rows]
    document["accessors"].append({
        "bufferView": uv_view, "componentType": 5126, "count": VERTEX_COUNT,
        "max": [max(value[axis] for value in uv_values) for axis in range(2)],
        "min": [min(value[axis] for value in uv_values) for axis in range(2)],
        "type": "VEC2",
    })
    primitive = document["meshes"][0]["primitives"][0]
    primitive["attributes"]["NORMAL"] = normal_accessor
    primitive["attributes"]["TEXCOORD_0"] = uv_accessor
    require("material" not in primitive, "canonical primitive unexpectedly has a material")
    document["meshes"][0]["extras"].update({
        "normal_conversion": "float32(snorm16(raw big-endian NORMAL0.xyz))",
        "uv_conversion": "u=2*snorm16(NORMAL0.w), v=2*snorm16(TANGENT0.w)",
        "material_withheld": "no concrete TXTR/render-target binding occurs in selected SCNE bytes",
        "tangent_withheld": "TANGENT0.w stores V; glTF tangent handedness is not proved",
    })
    document["asset"]["generator"] = "apf_player_shadow_surface_materials.py proved no-material surface derivative"
    document["asset"]["extras"].update({
        "surface_source_system_sha256": SYSTEM_SHA256,
        "surface_scope": "proved NORMAL and TEXCOORD_0 only; no invented material or texture",
    })
    document["buffers"][0] = {"byteLength": len(binary), "uri": output_bin.name}
    document["extras"]["surface_contract"] = {
        "normal": "source NORMAL0.xyz signed-normalized 16-bit -> glTF float32 NORMAL",
        "uv": "source NORMAL0.w/TANGENT0.w signed-normalized 16-bit, each multiplied by 2",
        "material": None,
        "images": [],
        "textures": [],
        "samplers": [],
    }
    document["extras"].setdefault("portme", []).extend([
        "PORTME before 0x84B27AD0: assign the official Xenos fetch endian/component-lane symbol to stream flag 0x40000000; this portable authoring derivative does not claim bit-exact GPU fetch serialization.",
        "PORTME at 0x84B15488: capture the selected instance material array and shader mapping before assigning concrete images/materials.",
        "PORTME at 0x84B14DA0 -> 0x84B28EA0: prove sampler filter/address bitfields before recreating a glTF sampler.",
    ])
    for forbidden in ("materials", "images", "textures", "samplers"):
        require(forbidden not in document, f"derivative invented top-level {forbidden}")
    output_gltf.parent.mkdir(parents=True, exist_ok=True)
    output_bin.parent.mkdir(parents=True, exist_ok=True)
    output_bin.write_bytes(bytes(binary))
    output_gltf.write_text(json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    return {
        "gltf_path": str(output_gltf.resolve()), "gltf_sha256": sha_file(output_gltf),
        "bin_path": str(output_bin.resolve()), "bin_sha256": sha_file(output_bin),
        "byte_length": len(binary), "canonical_prefix_bytes": prefix_length,
        "canonical_prefix_byte_identical": bytes(binary[:prefix_length]) == canonical_bin.read_bytes(),
        "normal_buffer_view": normal_view, "normal_accessor": normal_accessor,
        "uv_buffer_view": uv_view, "uv_accessor": uv_accessor,
        "has_material": False, "has_images": False, "has_textures": False,
        "status": "portable authoring-surface derivative; not a captured Xenon runtime material",
    }


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parent.parent
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--index", type=Path, default=root / "extracted/All-Pro Football 2K8 (USA)/0A")
    result.add_argument("--xex", type=Path, default=root / "extracted/All-Pro Football 2K8 (USA)/default.xex")
    result.add_argument("--scene-inventory", type=Path, default=root / "reports/assets/apf_scene_inventory.json")
    result.add_argument("--trace", type=Path, default=root / "reports/assets/apf_player_shadow_surface_material_ghidra/player_shadow_surface_material_trace.txt")
    result.add_argument("--pseudo", type=Path, default=root / "reports/assets/apf_player_shadow_surface_material_ghidra/player_shadow_surface_material_pseudo_c.c")
    result.add_argument("--canonical-gltf", type=Path, default=root / "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_skin.gltf")
    result.add_argument("--canonical-bin", type=Path, default=root / "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_skin.bin")
    result.add_argument("--output-gltf", type=Path, default=root / "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_surface.gltf")
    result.add_argument("--output-bin", type=Path, default=root / "assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_surface.bin")
    result.add_argument("--json", type=Path, default=root / "reports/assets/apf_player_shadow_surface_materials.json")
    result.add_argument("--vertices-tsv", type=Path, default=root / "reports/assets/apf_player_shadow_surface_vertices.tsv")
    result.add_argument("--samplers-tsv", type=Path, default=root / "reports/assets/apf_player_shadow_shader_samplers.tsv")
    result.add_argument("--links-tsv", type=Path, default=root / "reports/assets/apf_player_shadow_static_texture_links.tsv")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    require(sha_file(args.xex, "md5") == XEX_MD5 and sha_file(args.xex) == XEX_SHA256,
            "APF default.xex changed")
    system, source, files = read_selection(args.index)
    inventory = validate_scene_inventory(args.scene_inventory)
    require(u32(system, DRAW_OFFSET + 0x20) == 0, "selected draw material slot changed")
    require(sha_bytes(system[VERTEX_SHADER_OFFSET:VERTEX_SHADER_OFFSET + VERTEX_SHADER_SIZE]) ==
            VERTEX_SHADER_SHA256, "vertex shader container changed")
    pixel = parse_pixel_shader(system)
    surface = parse_surface(system)
    links = scan_static_links(system, files)
    executable = validate_trace(args.trace, args.pseudo)

    write_surface_tsv(args.vertices_tsv, surface)
    write_samplers_tsv(args.samplers_tsv, pixel["samplers"])
    write_links_tsv(args.links_tsv, links)
    gltf = emit_gltf(args.canonical_gltf, args.canonical_bin,
                     args.output_gltf, args.output_bin, surface)

    normal_lengths = [row["normal_xyz_length"] for row in surface]
    tangent_lengths = [row["tangent_xyz_length"] for row in surface]
    uv_values = [row["uv"] for row in surface]
    report = {
        "schema": SCHEMA,
        "selection": source,
        "scene_inventory": inventory,
        "draw_material_handoff": {
            "draw_record_offset": f"0x{DRAW_OFFSET:04x}",
            "selected_material_slot_at_0x20": 0,
            "xex_equation": "material = instance_material_base + draw.material_slot * 0xf0",
            "instance_material_array": "instance+0x7c passed to 0x84B10B98",
            "material_texture_records": "eight records at material+0x50+0x14*n selected by pixel_shader+0x8c mapping; mapping value 8 means unused",
            "concrete_runtime_values_captured": False,
        },
        "executable": executable,
        "vertex_shader": {
            "system_offset": f"0x{VERTEX_SHADER_OFFSET:04x}",
            "byte_length": VERTEX_SHADER_SIZE,
            "sha256": VERTEX_SHADER_SHA256,
            "declared_inputs": ["POSITION0", "NORMAL0", "TANGENT0", "BLENDWEIGHT0", "BLENDINDICES0"],
            "has_texcoord_input": False,
        },
        "pixel_shader": pixel,
        "surface": {
            "vertex_count": len(surface),
            "stream_offset": f"0x{STREAM_OFFSET:04x}",
            "stream_stride": STREAM_STRIDE,
            "normal_offset": 8,
            "tangent_offset": 16,
            "source_format": "snorm16x4 big-endian components",
            "normal_xyz_length": {"min": min(normal_lengths), "max": max(normal_lengths),
                                  "mean": f32(sum(normal_lengths) / len(normal_lengths)),
                                  "all_within_0_001_of_one": True},
            "tangent_xyz_length": {"min": min(tangent_lengths), "max": max(tangent_lengths),
                                   "mean": f32(sum(tangent_lengths) / len(tangent_lengths)),
                                   "all_within_0_001_of_one": True},
            "uv_equation": "u=2*snorm16(NORMAL0.w), v=2*snorm16(TANGENT0.w)",
            "uv_min": [min(value[axis] for value in uv_values) for axis in range(2)],
            "uv_max": [max(value[axis] for value in uv_values) for axis in range(2)],
            "unique_uv_count": len(set(uv_values)),
            "all_vertices_validated": len(surface),
            "tangent_xyz_exported_as_gltf_tangent": False,
            "tangent_reason": "glTF TANGENT.w is handedness, but selected TANGENT0.w stores V",
        },
        "static_file_id_scan": {
            "aligned_u32_offsets_scanned": len(system) // 4,
            "global_iff_file_count": len(files),
            "matches": [{**row, "system_offset": f"0x{row['system_offset']:04x}",
                         "value": f"0x{row['value']:08x}"} for row in links],
            "txtr_matches": 0,
            "conclusion": "only three self-ID occurrences; no TXTR file ID occurs in selected SCNE system bytes",
        },
        "name_only_candidates_not_bound": [
            {"name": name, "inner_file_index": values[0], "file_id": f"0x{values[1]:08x}",
             "type": values[2], "classification": "global.iff name-only candidate; rejected as a concrete binding"}
            for name, values in NAME_ONLY_CANDIDATES.items()
        ],
        "artifacts": {
            "surface_vertices_tsv": {"path": relative(args.vertices_tsv, root),
                                     "sha256": sha_file(args.vertices_tsv)},
            "shader_samplers_tsv": {"path": relative(args.samplers_tsv, root),
                                    "sha256": sha_file(args.samplers_tsv)},
            "static_texture_links_tsv": {"path": relative(args.links_tsv, root),
                                         "sha256": sha_file(args.links_tsv)},
            "gltf": {**gltf, "gltf_path": relative(args.output_gltf, root),
                     "bin_path": relative(args.output_bin, root)},
        },
        "decision": {
            "exact_iff_ownership_proved": True,
            "normal_and_packed_uv_authoring_contract_proved_for_all_vertices": True,
            "shader_sampler_interface_and_dimensions_proved": True,
            "draw_to_runtime_material_indirection_proved": True,
            "concrete_txtr_or_render_target_bindings_proved": False,
            "exact_sampler_filter_and_address_modes_proved": False,
            "mod_ready_png_and_gltf_material_safe_to_emit": False,
            "png_emitted": False,
            "gltf_material_emitted": False,
            "separate_no_material_surface_gltf_emitted": True,
        },
        "portme": [
            "// PORTME before 0x84B27AD0: name/prove stream flag 0x40000000 -> Xenos fetch endian/component-lane setup; the portable W-channel UV contract is corpus/shader proved but is not claimed as bit-exact Xenon fetch serialization.",
            "// PORTME at 0x84B15488: capture selected player_shadow instance material array (+0x7c) and pixel-shader mapping (+0x8c) at runtime to identify concrete TXTR objects/render targets.",
            "// PORTME at 0x84B14DA0 -> 0x84B28EA0: name exact Xenos sampler filter/address fields in the runtime texture record before recreating sampler state.",
            "// PORTME at 0x84AA4728: do not assign blank_nm/lightmap_player_* name-only candidates without a live pointer trace.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                         encoding="utf-8")
    print("APF_PLAYER_SHADOW_SURFACE_MATERIALS_COMPLETE vertices=351 uv=278 "
          "samplers=5 static_txtr_links=0 material=false png=false surface_gltf=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
