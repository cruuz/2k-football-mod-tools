#!/usr/bin/env python3
"""Prove the NFL-reference-book remnants shipped in APF 2K8.

This is a read-only, bounded evidence generator.  It decodes APF outer entry
1135 (``reference.iff``), resolves the embedded Xenos textures in the
``closed_book`` SCNE, compares its text database with NFL 2K5 outer entry 110,
and cross-checks the migrated shield quad against the existing evidence-checked
glTF exports.  It never writes either game image.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import dataclass
import difflib
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
from typing import Iterable
import zlib

from PIL import Image

import apf_inner
import apf_outer
import nfl_outer


SCHEMA = "vc_apf_reference_nfl_remnants/v1"
APF_OUTER_INDEX = 1135
NFL_OUTER_INDEX = 110
APF_OUTER_ID = 0xBE047DD2
NFL_OUTER_ID = 0x107A62A5
REFR_TYPE_HASH = 0x15578F45
APF_TEXTURE_RECORD_SIZE = 0xE0
APF_MATERIAL_RECORD_SIZE = 0xF0
MAX_DECOMPRESSED = 16 * 1024 * 1024

EXPECTED_APF_INDEX_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)
EXPECTED_NFL_INDEX_SHA256 = (
    "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
)
EXPECTED_NFL_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)

UTF16BE_ASCII_RUN = re.compile(rb"(?:\x00[\x20-\x7e]){3,}\x00\x00")
UTF16LE_ASCII_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){3,}\x00\x00")

TEAM_TOKENS = (
    "49ers", "Bears", "Bengals", "Bills", "Broncos", "Browns",
    "Buccaneers", "Cardinals", "Chargers", "Chiefs", "Colts", "Cowboys",
    "Dolphins", "Eagles", "Falcons", "Giants", "Jaguars", "Jets",
    "Lions", "Oilers", "Packers", "Panthers", "Patriots", "Raiders",
    "Rams", "Ravens", "Redskins", "Saints", "Seahawks", "Steelers",
    "Texans", "Titans", "Vikings",
)


class EvidenceError(ValueError):
    """Raised when a shipped invariant does not match the proved layout."""


@dataclass(frozen=True)
class TextRun:
    offset: int
    text: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_pin(path: Path, expected_sha256: str | None = None) -> dict[str, object]:
    actual = sha256_file(path)
    if expected_sha256 is not None and actual != expected_sha256:
        raise EvidenceError(
            f"source changed: {path} SHA-256 {actual}, expected {expected_sha256}"
        )
    return {"path": str(path.resolve()), "size": path.stat().st_size, "sha256": actual}


def u32be(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise EvidenceError(f"{what}: u32be at 0x{offset:x} is out of bounds")
    return struct.unpack_from(">I", data, offset)[0]


def u32le(data: bytes, offset: int, what: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise EvidenceError(f"{what}: u32le at 0x{offset:x} is out of bounds")
    return struct.unpack_from("<I", data, offset)[0]


def relative_target_be(data: bytes, field_offset: int, what: str) -> int:
    raw = u32be(data, field_offset, what)
    if raw == 0:
        raise EvidenceError(f"{what}: null relative pointer")
    target = field_offset + raw - 1
    if not 0 <= target < len(data):
        raise EvidenceError(f"{what}: target 0x{target:x} is out of bounds")
    return target


def utf16be_z(data: bytes, offset: int, what: str) -> str:
    cursor = offset
    while cursor + 1 < len(data):
        if data[cursor : cursor + 2] == b"\0\0":
            try:
                return data[offset:cursor].decode("utf-16be")
            except UnicodeDecodeError as exc:
                raise EvidenceError(f"{what}: invalid UTF-16BE") from exc
        cursor += 2
    raise EvidenceError(f"{what}: unterminated UTF-16BE string")


def read_apf_file_parts(
    record: apf_inner.IFFRecord, decoded_blocks: list[bytes], file_index: int
) -> list[bytes]:
    file = record.files[file_index]
    result: list[bytes] = []
    for part in file.parts:
        block = decoded_blocks[part.block_index]
        end = part.offset + part.length
        if end > len(block):
            raise EvidenceError(f"APF file {file_index} part exceeds decoded block")
        result.append(block[part.offset:end])
    return result


def extract_text_runs(data: bytes, byte_order: str) -> list[TextRun]:
    if byte_order == "big":
        pattern, encoding = UTF16BE_ASCII_RUN, "utf-16be"
    elif byte_order == "little":
        pattern, encoding = UTF16LE_ASCII_RUN, "utf-16le"
    else:
        raise EvidenceError(f"unsupported string byte order {byte_order}")
    return [
        TextRun(match.start(), match.group()[:-2].decode(encoding))
        for match in pattern.finditer(data)
    ]


def parse_apf_refr_structure(data: bytes) -> dict[str, object]:
    """Validate the four-table layout proved by XEX callback 0x84AB0D58."""

    group_counts = list(struct.unpack_from(">4I", data, 0))
    group_starts = [
        relative_target_be(data, 0x10 + index * 4, f"REFR group {index} table")
        for index in range(4)
    ]
    if group_counts != [93, 46, 217, 82]:
        raise EvidenceError(f"APF REFR group counts changed: {group_counts}")
    cursor = 0x20
    for index, (count, start) in enumerate(zip(group_counts, group_starts)):
        if start != cursor:
            raise EvidenceError(
                f"APF REFR group {index} begins 0x{start:x}, expected 0x{cursor:x}"
            )
        cursor += count * 0x1C
    pool_start = cursor
    if pool_start != 0x3008:
        raise EvidenceError(f"APF REFR string pool begins 0x{pool_start:x}, expected 0x3008")

    pointer_count = 0
    pointer_targets: list[int] = []
    for group_index, (count, start) in enumerate(zip(group_counts, group_starts)):
        for record_index in range(count):
            record = start + record_index * 0x1C
            for field_index in range(5):
                field = record + field_index * 4
                raw = u32be(data, field, "REFR record string pointer")
                if raw == 0:
                    continue
                target = field + raw - 1
                if target < pool_start or target >= len(data) or target & 1:
                    raise EvidenceError(
                        f"APF REFR group {group_index} record {record_index} field "
                        f"{field_index} resolves outside/eccentrically into the string pool"
                    )
                utf16be_z(data, target, "REFR pointed string")
                pointer_count += 1
                pointer_targets.append(target)
    if pointer_count != 1092 or len(set(pointer_targets)) != 1092:
        raise EvidenceError(
            f"APF REFR pointer closure changed: {pointer_count} / "
            f"{len(set(pointer_targets))} unique"
        )
    return {
        "record_group_counts": group_counts,
        "record_group_offsets": [f"0x{value:x}" for value in group_starts],
        "record_stride": 0x1C,
        "record_pointer_fields_relocated_by_xex_callback": 5,
        "total_record_count": sum(group_counts),
        "string_pool_offset": f"0x{pool_start:x}",
        "string_pool_size": len(data) - pool_start,
        "nonzero_string_pointer_count": pointer_count,
        "unique_string_pointer_target_count": len(set(pointer_targets)),
        "all_nonzero_string_pointers_valid": True,
        "xex_relocation_worker": "0x84ab0d58",
    }


def parse_apf_closed_book(
    apf_index: Path, output_dir: Path
) -> tuple[dict[str, object], bytes, Path]:
    archive = apf_outer.parse_archive(apf_index)
    entry = archive.entries[APF_OUTER_INDEX]
    if entry.name_id != APF_OUTER_ID:
        raise EvidenceError(
            f"APF outer {APF_OUTER_INDEX} ID 0x{entry.name_id:08x} != "
            f"0x{APF_OUTER_ID:08x}"
        )

    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        decoded_blocks = [
            apf_inner.decode_block(reader, record, index, MAX_DECOMPRESSED)
            for index in range(record.block_count)
        ]

    files = [(file.name, file.type_name) for file in record.files]
    expected_files = [
        ("open_book", "SCNE"),
        ("closed_book", "SCNE"),
        ("reference_data", "REFR"),
    ]
    if files != expected_files:
        raise EvidenceError(f"APF reference.iff files changed: {files!r}")
    if record.files[2].type_hash != REFR_TYPE_HASH:
        raise EvidenceError("APF reference_data REFR type hash changed")

    closed_parts = read_apf_file_parts(record, decoded_blocks, 1)
    reference_parts = read_apf_file_parts(record, decoded_blocks, 2)
    if len(closed_parts) != 2 or len(reference_parts) != 1:
        raise EvidenceError("unexpected APF closed_book/reference_data part layout")
    system, video = closed_parts
    reference_body = reference_parts[0]
    reference_structure = parse_apf_refr_structure(reference_body)

    texture_count = u32be(system, 0x20, "SCNE texture count")
    texture_start = relative_target_be(system, 0x24, "SCNE texture table")
    material_count = u32be(system, 0x30, "SCNE material count")
    material_start = relative_target_be(system, 0x34, "SCNE material table")
    if (texture_count, texture_start, material_count, material_start) != (5, 0x90, 5, 0x4F0):
        raise EvidenceError(
            "APF closed_book texture/material table no longer matches the proved layout"
        )

    texture_records: list[dict[str, object]] = []
    texture_by_id: dict[int, dict[str, object]] = {}
    for index in range(texture_count):
        start = texture_start + index * APF_TEXTURE_RECORD_SIZE
        end = start + APF_TEXTURE_RECORD_SIZE
        if end > len(system):
            raise EvidenceError("APF embedded texture record exceeds SCNE system part")
        raw = system[start:end]
        metadata = apf_inner.parse_txtr_metadata(raw)
        texture_id = u32be(raw, 0, "embedded texture ID")
        video_offset_word = u32be(raw, 0x6C, "embedded texture video offset")
        if video_offset_word & 0xFFF != 1:
            raise EvidenceError(
                f"embedded texture {index} video offset flags changed: "
                f"0x{video_offset_word:08x}"
            )
        video_offset = video_offset_word & ~0xFFF
        base_length = int(metadata["vc_base_data_length"])
        if video_offset + base_length > len(video):
            raise EvidenceError(f"embedded texture {index} base data exceeds VRAM part")
        rgba_width, rgba_height, rgba = apf_inner.decode_txtr_base_rgba(
            metadata, video[video_offset : video_offset + base_length]
        )
        row = {
            "index": index,
            "record_offset": f"0x{start:04x}",
            "texture_id": f"0x{texture_id:08x}",
            "video_offset": f"0x{video_offset:x}",
            "base_data_length": base_length,
            "metadata": metadata,
            "decoded_width": rgba_width,
            "decoded_height": rgba_height,
            "decoded_rgba_sha256": sha256_bytes(rgba),
            "_rgba": rgba,
        }
        texture_records.append(row)
        texture_by_id[texture_id] = row

    materials: list[dict[str, object]] = []
    for index in range(material_count):
        start = material_start + index * APF_MATERIAL_RECORD_SIZE
        end = start + APF_MATERIAL_RECORD_SIZE
        if end > len(system):
            raise EvidenceError("APF material record exceeds SCNE system part")
        name_offset = relative_target_be(system, start, f"material {index} name")
        name = utf16be_z(system, name_offset, f"material {index} name")
        name_hash = u32be(system, start + 4, f"material {index} name hash")
        expected_hash = zlib.crc32(name.encode("ascii")) & 0xFFFFFFFF
        if name_hash != expected_hash:
            raise EvidenceError(f"material {index} name CRC32 mismatch")
        texture_id = u32be(system, start + 0x50, f"material {index} texture ID")
        if texture_id not in texture_by_id:
            raise EvidenceError(f"material {index} references unknown texture ID")
        materials.append(
            {
                "index": index,
                "record_offset": f"0x{start:04x}",
                "name": name,
                "name_hash": f"0x{name_hash:08x}",
                "texture_id": f"0x{texture_id:08x}",
                "texture_index": int(texture_by_id[texture_id]["index"]),
            }
        )

    expected_materials = [
        "corner_right", "corner_left", "cover", "nfl_shield", "tab_corner_left"
    ]
    if [row["name"] for row in materials] != expected_materials:
        raise EvidenceError("APF closed_book material order changed")

    shield_material = materials[3]
    shield_texture = texture_records[int(shield_material["texture_index"])]
    if (
        shield_texture["metadata"]["format_name"] != "DXT4_5"
        or shield_texture["decoded_width"] != 128
        or shield_texture["decoded_height"] != 128
    ):
        raise EvidenceError("APF nfl_shield texture format/dimensions changed")

    output_dir.mkdir(parents=True, exist_ok=True)
    apf_png = output_dir / "apf_reference_nfl_shield.png"
    apf_inner.write_rgba_png(
        apf_png,
        int(shield_texture["decoded_width"]),
        int(shield_texture["decoded_height"]),
        shield_texture["_rgba"],
    )
    apf_png_pin = {
        "path": str(apf_png.resolve()),
        "size": apf_png.stat().st_size,
        "sha256": sha256_file(apf_png),
    }

    # The shield node is node 1 in the proved three-node table.  Its draw table
    # has one 0x30-byte record; field +0x20 is the material index.
    node_count = u32be(system, 0x44, "SCNE node count")
    node_start = relative_target_be(system, 0x48, "SCNE node table")
    if (node_count, node_start) != (3, 0x9A0):
        raise EvidenceError("APF closed_book node table changed")
    shield_node = node_start + 0xB0
    shield_name_offset = relative_target_be(system, shield_node, "shield node name")
    shield_node_name = utf16be_z(system, shield_name_offset, "shield node name")
    draw_count = u32be(system, shield_node + 0x7C, "shield draw count")
    draw_start = relative_target_be(system, shield_node + 0x80, "shield draw table")
    draw_material_index = u32be(system, draw_start + 0x20, "shield draw material index")
    if (shield_node_name, draw_count, draw_start, draw_material_index) != (
        "nfl_shield1", 1, 0x2870, 3
    ):
        raise EvidenceError("APF nfl_shield1 draw/material binding changed")

    for row in texture_records:
        row.pop("_rgba", None)

    result = {
        "outer_index": APF_OUTER_INDEX,
        "outer_id": f"0x{entry.name_id:08x}",
        "outer_size": entry.size,
        "filename": "reference.iff",
        "filename_hash_rule": "CRC32 uppercase ASCII",
        "files": [
            {
                "index": file.index,
                "name": file.name,
                "type": file.type_name,
                "file_id": f"0x{file.file_id:08x}",
                "type_hash": f"0x{file.type_hash:08x}",
            }
            for file in record.files
        ],
        "closed_book": {
            "system_size": len(system),
            "system_sha256": sha256_bytes(system),
            "video_size": len(video),
            "video_sha256": sha256_bytes(video),
            "node_order": ["book", "nfl_shield1", "tabs"],
            "material_order": expected_materials,
            "textures": texture_records,
            "materials": materials,
            "shield_binding": {
                "node": shield_node_name,
                "node_index": 1,
                "draw_record_offset": f"0x{draw_start:04x}",
                "draw_material_index": draw_material_index,
                "material": shield_material["name"],
                "texture_id": shield_material["texture_id"],
                "texture_format": shield_texture["metadata"]["format_name"],
                "dimensions": [128, 128],
                "decoded_rgba_sha256": shield_texture["decoded_rgba_sha256"],
                "png": apf_png_pin,
            },
        },
        "reference_data": {
            "size": len(reference_body),
            "sha256": sha256_bytes(reference_body),
            "first_serialized_group_count": u32be(reference_body, 0, "APF REFR count"),
            "structure": reference_structure,
        },
    }
    return result, reference_body, apf_png


def parse_nfl_reference(nfl_index: Path) -> tuple[dict[str, object], bytes]:
    archive = nfl_outer.parse_archive(nfl_index)
    entry = archive.entries[NFL_OUTER_INDEX]
    if entry.name_id != NFL_OUTER_ID:
        raise EvidenceError(
            f"NFL outer {NFL_OUTER_INDEX} ID 0x{entry.name_id:08x} != "
            f"0x{NFL_OUTER_ID:08x}"
        )
    outer = nfl_outer.read_entry_bytes(archive, entry, max_size=4 * 1024 * 1024)
    chunks: list[dict[str, object]] = []
    offset = 0
    while offset < len(outer):
        if offset + 32 > len(outer):
            raise EvidenceError("NFL reference.iff has a truncated chunk header")
        kind = outer[offset : offset + 4].decode("ascii")
        stored_size = u32le(outer, offset + 4, "NFL chunk stored size")
        total_size = 32 + stored_size
        if offset + total_size > len(outer):
            raise EvidenceError("NFL reference.iff chunk exceeds outer entry")
        chunks.append(
            {
                "index": len(chunks),
                "offset": offset,
                "kind": kind,
                "stored_size": stored_size,
                "total_size": total_size,
            }
        )
        offset += total_size
    if offset != len(outer) or [row["kind"] for row in chunks] != ["SCNE", "SCNE", "REFR"]:
        raise EvidenceError("NFL reference.iff chunk sequence changed")
    refr = chunks[2]
    chunk_start = int(refr["offset"])
    # 0x20-byte outer chunk wrapper + 0x40-byte resource/name preamble.
    body_start = chunk_start + 0x60
    body_end = chunk_start + int(refr["total_size"])
    body = outer[body_start:body_end]
    if u32le(body, 0, "NFL REFR count") != 93:
        raise EvidenceError("NFL reference_data top-level count changed")
    return {
        "outer_index": NFL_OUTER_INDEX,
        "outer_id": f"0x{entry.name_id:08x}",
        "outer_size": entry.size,
        "outer_sha256": sha256_bytes(outer),
        "filename": "reference.iff",
        "filename_hash_rule": "CRC32 uppercase UTF-16LE",
        "chunks": chunks,
        "reference_data": {
            "body_offset_in_outer": f"0x{body_start:x}",
            "size": len(body),
            "sha256": sha256_bytes(body),
            "first_serialized_count": 93,
        },
    }, body


def png_rgba(path: Path) -> tuple[tuple[int, int], bytes]:
    with Image.open(path) as image:
        converted = image.convert("RGBA")
        return converted.size, converted.tobytes()


def channel_metrics(left: bytes, right: bytes) -> dict[str, object]:
    if len(left) != len(right) or len(left) % 4:
        raise EvidenceError("RGBA comparison buffers differ in length")
    result: dict[str, object] = {}
    for channel, name in enumerate("RGBA"):
        xs = left[channel::4]
        ys = right[channel::4]
        count = len(xs)
        mean_x = sum(xs) / count
        mean_y = sum(ys) / count
        dx = [value - mean_x for value in xs]
        dy = [value - mean_y for value in ys]
        covariance = sum(a * b for a, b in zip(dx, dy))
        denominator = math.sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
        correlation = covariance / denominator if denominator else 1.0
        absolute = [abs(a - b) for a, b in zip(xs, ys)]
        squared = [(a - b) ** 2 for a, b in zip(xs, ys)]
        result[name] = {
            "pearson_correlation": correlation,
            "mean_absolute_error": sum(absolute) / count,
            "root_mean_square_error": math.sqrt(sum(squared) / count),
        }
    return result


def accessor_values(gltf_path: Path, accessor_index: int) -> list[tuple[float, ...] | int]:
    document = json.loads(gltf_path.read_text())
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    buffer = document["buffers"][view["buffer"]]
    blob = (gltf_path.parent / buffer["uri"]).read_bytes()
    component_type = accessor["componentType"]
    value_type = accessor["type"]
    format_by_component = {5123: "H", 5125: "I", 5126: "f"}
    components_by_type = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    if component_type not in format_by_component or value_type not in components_by_type:
        raise EvidenceError("unsupported glTF accessor format in focused comparison")
    count_components = components_by_type[value_type]
    item_format = "<" + format_by_component[component_type] * count_components
    item_size = struct.calcsize(item_format)
    stride = int(view.get("byteStride", item_size))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    values: list[tuple[float, ...] | int] = []
    for index in range(int(accessor["count"])):
        value = struct.unpack_from(item_format, blob, start + index * stride)
        values.append(value[0] if count_components == 1 else tuple(float(x) for x in value))
    return values


def mesh_primitive(document: dict[str, object], mesh_name: str) -> dict[str, object]:
    for mesh in document["meshes"]:
        if mesh["name"] == mesh_name:
            primitives = mesh["primitives"]
            if len(primitives) != 1:
                raise EvidenceError(f"{mesh_name} does not have exactly one primitive")
            return primitives[0]
    raise EvidenceError(f"mesh {mesh_name!r} not found")


def directed_hausdorff(
    left: Iterable[tuple[float, ...]], right: Iterable[tuple[float, ...]]
) -> float:
    right_values = list(right)
    if not right_values:
        raise EvidenceError("empty right vertex set")
    maximum = 0.0
    for point in left:
        nearest = min(
            math.sqrt(sum((a - b) ** 2 for a, b in zip(point, candidate)))
            for candidate in right_values
        )
        maximum = max(maximum, nearest)
    return maximum


def compare_shield_geometry(apf_gltf: Path, nfl_gltf: Path) -> dict[str, object]:
    apf_document = json.loads(apf_gltf.read_text())
    nfl_document = json.loads(nfl_gltf.read_text())
    if [row["name"] for row in apf_document["nodes"]] != ["book", "nfl_shield1", "tabs"]:
        raise EvidenceError("APF closed_book glTF node order changed")
    if [row["name"] for row in nfl_document["nodes"]] != ["book", "nfl_shield1", "tabs"]:
        raise EvidenceError("NFL closed_book glTF node order changed")
    apf_primitive = mesh_primitive(apf_document, "nfl_shield1")
    nfl_primitive = mesh_primitive(nfl_document, "nfl_shield1")
    apf_positions = accessor_values(apf_gltf, apf_primitive["attributes"]["POSITION"])
    nfl_positions = accessor_values(nfl_gltf, nfl_primitive["attributes"]["POSITION"])
    apf_indices = accessor_values(apf_gltf, apf_primitive["indices"])
    nfl_indices = accessor_values(nfl_gltf, nfl_primitive["indices"])
    if not all(isinstance(value, tuple) for value in apf_positions + nfl_positions):
        raise EvidenceError("shield POSITION accessor is not vector data")
    hausdorff = max(
        directed_hausdorff(apf_positions, nfl_positions),
        directed_hausdorff(nfl_positions, apf_positions),
    )
    return {
        "node_order_exact_match": True,
        "apf_vertex_count": len(apf_positions),
        "nfl_vertex_count": len(nfl_positions),
        "apf_triangle_count": len(apf_indices) // 3,
        "nfl_triangle_count": len(nfl_indices) // 3,
        "unordered_vertex_hausdorff_distance": hausdorff,
        "interpretation": (
            "same four-vertex/two-triangle logo quad with sub-unit repacking drift; "
            "whole scenes are not claimed byte-identical"
        ),
    }


def compare_texts(
    apf_body: bytes, nfl_body: bytes
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    apf_runs = extract_text_runs(apf_body, "big")
    nfl_runs_all = extract_text_runs(nfl_body, "little")
    # NFL's platform wrapper leaves one resource-name string before the body
    # proper in some extraction paths.  The body slice used here should not,
    # but tolerate and explicitly account for it rather than changing counts.
    nfl_runs = (
        nfl_runs_all[1:]
        if nfl_runs_all and nfl_runs_all[0].text == "reference_data"
        else nfl_runs_all
    )
    apf_text = [run.text for run in apf_runs]
    nfl_text = [run.text for run in nfl_runs]
    matcher = difflib.SequenceMatcher(a=apf_text, b=nfl_text, autojunk=False)
    exact_ordered_match_count = sum(
        i2 - i1 for tag, i1, i2, _j1, _j2 in matcher.get_opcodes() if tag == "equal"
    )
    multiset_match_count = sum((Counter(apf_text) & Counter(nfl_text)).values())
    if exact_ordered_match_count != multiset_match_count:
        raise EvidenceError("ordered and multiset exact-string matches disagree")

    diffs: list[dict[str, object]] = []
    removed_entry_titles: list[str] = []
    modified_pairs: list[dict[str, str]] = []
    apf_added: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        a_rows = apf_runs[i1:i2]
        n_rows = nfl_runs[j1:j2]
        if tag == "insert" and n_rows:
            removed_entry_titles.append(n_rows[0].text)
        elif tag == "replace" and len(a_rows) == len(n_rows) == 1:
            modified_pairs.append({"apf": a_rows[0].text, "nfl": n_rows[0].text})
        elif tag == "delete":
            apf_added.extend(row.text for row in a_rows)
        width = max(len(a_rows), len(n_rows))
        for index in range(width):
            apf_run = a_rows[index] if index < len(a_rows) else None
            nfl_run = n_rows[index] if index < len(n_rows) else None
            diffs.append(
                {
                    "operation": tag,
                    "apf_sequence_index": None if apf_run is None else i1 + index,
                    "apf_offset": None if apf_run is None else f"0x{apf_run.offset:x}",
                    "apf_text": None if apf_run is None else apf_run.text,
                    "nfl_sequence_index": None if nfl_run is None else j1 + index,
                    "nfl_offset": None if nfl_run is None else f"0x{nfl_run.offset:x}",
                    "nfl_text": None if nfl_run is None else nfl_run.text,
                }
            )

    licensed_rows: list[dict[str, object]] = []
    for index, run in enumerate(apf_runs):
        categories: list[str] = []
        if re.search(r"\bNFL\b", run.text, re.IGNORECASE):
            categories.append("NFL_token")
        if "ESPN NFL Football".lower() in run.text.lower():
            categories.append("ESPN_NFL_Football")
        if "Super Bowl".lower() in run.text.lower():
            categories.append("Super_Bowl")
        matched_teams = [
            token for token in TEAM_TOKENS
            if re.search(r"\b" + re.escape(token) + r"\b", run.text, re.IGNORECASE)
        ]
        if matched_teams:
            categories.append("NFL_team_names")
        if categories:
            licensed_rows.append(
                {
                    "sequence_index": index,
                    "offset": f"0x{run.offset:x}",
                    "categories": ",".join(categories),
                    "team_tokens": ",".join(matched_teams),
                    "text": run.text,
                }
            )

    nfl_only_count = sum((Counter(nfl_text) - Counter(apf_text)).values())
    apf_only_count = sum((Counter(apf_text) - Counter(nfl_text)).values())
    result = {
        "apf_printable_utf16_string_occurrences": len(apf_runs),
        "nfl_printable_utf16_string_occurrences": len(nfl_runs),
        "exact_ordered_string_occurrence_matches": exact_ordered_match_count,
        "exact_match_fraction_of_apf": exact_ordered_match_count / len(apf_runs),
        "exact_match_fraction_of_nfl": exact_ordered_match_count / len(nfl_runs),
        "sequence_match_ratio": matcher.ratio(),
        "nfl_only_string_occurrences": nfl_only_count,
        "apf_only_string_occurrences": apf_only_count,
        "removed_nfl_glossary_entry_count": len(removed_entry_titles),
        "removed_nfl_glossary_entry_titles": removed_entry_titles,
        "selectively_modified_pair_count": len(modified_pairs),
        "selectively_modified_pairs": modified_pairs,
        "apf_added_string_count": len(apf_added),
        "apf_added_strings": apf_added,
        "apf_explicit_nfl_token_string_count": sum(
            bool(re.search(r"\bNFL\b", value, re.IGNORECASE)) for value in apf_text
        ),
        "apf_espn_nfl_football_string_count": sum(
            "espn nfl football" in value.lower() for value in apf_text
        ),
        "apf_super_bowl_string_count": sum(
            "super bowl" in value.lower() for value in apf_text
        ),
        "apf_nfl_team_name_string_count": sum(
            any(
                re.search(r"\b" + re.escape(token) + r"\b", value, re.IGNORECASE)
                for token in TEAM_TOKENS
            )
            for value in apf_text
        ),
        "interpretation": (
            "APF contains a platform-converted and selectively edited descendant "
            "of NFL 2K5 reference_data, not an accidental byte-for-byte archive copy"
        ),
    }
    return result, diffs, licensed_rows


def locate_nfl_texture_from_tsv(tsv_path: Path, root: Path) -> Path:
    with tsv_path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        for row in reader:
            if (
                row.get("outer_index") == str(NFL_OUTER_INDEX)
                and row.get("chunk_index") == "1"
                and row.get("scene_name") == "closed_book"
                and row.get("material_name") == "nfl_shield"
            ):
                candidate = Path(row["png_path"])
                return candidate if candidate.is_absolute() else root / candidate
    raise EvidenceError("NFL closed_book nfl_shield texture row was not found")


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apf-index", type=Path,
        default=root / "extracted/All-Pro Football 2K8 (USA)/0A",
    )
    parser.add_argument(
        "--nfl-index", type=Path,
        default=root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0",
    )
    parser.add_argument(
        "--nfl-xbe", type=Path,
        default=root / "extracted/ESPN NFL 2K5 (USA)/default.xbe",
    )
    parser.add_argument(
        "--apf-gltf", type=Path,
        default=root / "assets/intermediate/apf2k8/models/1135_0001_closed_book.gltf",
    )
    parser.add_argument(
        "--nfl-gltf", type=Path,
        default=root / "assets/intermediate/nfl2k5/models/0110_0001_closed_book.gltf",
    )
    parser.add_argument(
        "--nfl-material-tsv", type=Path,
        default=root / "reports/assets/nfl2k5_scne_texture_png_materials.tsv",
    )
    parser.add_argument(
        "--ghidra-trace", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/reference_remnants/ghidra_trace.txt",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/reference_remnants",
    )
    parser.add_argument(
        "--json-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/reference_remnants.json",
    )
    parser.add_argument(
        "--diff-tsv-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/reference_remnants_text_diff.tsv",
    )
    parser.add_argument(
        "--licensed-tsv-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/reference_remnants_licensed_text.tsv",
    )
    parser.add_argument(
        "--claims-tsv-out", type=Path,
        default=root / "reports/cut_content/apf_nfl_lineage/reference_remnants_video_claims.tsv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    for path in (
        args.apf_index, args.nfl_index, args.nfl_xbe, args.apf_gltf,
        args.nfl_gltf, args.nfl_material_tsv, args.ghidra_trace,
    ):
        if not path.is_file():
            raise EvidenceError(f"required input is missing: {path}")

    apf_pin = source_pin(args.apf_index, EXPECTED_APF_INDEX_SHA256)
    nfl_pin = source_pin(args.nfl_index, EXPECTED_NFL_INDEX_SHA256)
    xbe_pin = source_pin(args.nfl_xbe, EXPECTED_NFL_XBE_SHA256)

    apf, apf_reference_body, apf_png = parse_apf_closed_book(
        args.apf_index, args.output_dir
    )
    nfl, nfl_reference_body = parse_nfl_reference(args.nfl_index)
    texts, diff_rows, licensed_rows = compare_texts(apf_reference_body, nfl_reference_body)

    xbe = args.nfl_xbe.read_bytes()
    filename_literal = "reference.iff".encode("utf-16le")
    literal_offsets: list[int] = []
    cursor = 0
    while True:
        offset = xbe.find(filename_literal, cursor)
        if offset < 0:
            break
        literal_offsets.append(offset)
        cursor = offset + 1
    if literal_offsets != [0x00B4B71C]:
        raise EvidenceError(f"NFL reference.iff XBE literal offsets changed: {literal_offsets}")

    nfl_png = locate_nfl_texture_from_tsv(args.nfl_material_tsv, root)
    apf_size, apf_rgba = png_rgba(apf_png)
    nfl_size, nfl_rgba = png_rgba(nfl_png)
    if apf_size != nfl_size or apf_size != (128, 128):
        raise EvidenceError("APF/NFL shield PNG dimensions changed")
    texture_metrics = channel_metrics(apf_rgba, nfl_rgba)
    if min(float(row["pearson_correlation"]) for row in texture_metrics.values()) < 0.97:
        raise EvidenceError("APF/NFL shield channel correlation fell below 0.97")

    geometry = compare_shield_geometry(args.apf_gltf, args.nfl_gltf)
    if geometry["unordered_vertex_hausdorff_distance"] >= 0.11:
        raise EvidenceError("APF/NFL shield geometry drift exceeded proved bound")

    ghidra_trace = args.ghidra_trace.read_bytes()
    if b"0x15578F45" not in ghidra_trace or b"0x84AB10C0" not in ghidra_trace:
        raise EvidenceError("focused Ghidra REFR trace lacks required witnesses")

    filename_hashes = {
        "uppercase_name": "REFERENCE.IFF",
        "apf_crc32_uppercase_ascii": f"0x{zlib.crc32(b'REFERENCE.IFF') & 0xffffffff:08x}",
        "nfl_crc32_uppercase_utf16le": f"0x{zlib.crc32('REFERENCE.IFF'.encode('utf-16le')) & 0xffffffff:08x}",
        "matches_apf_outer_id": (zlib.crc32(b"REFERENCE.IFF") & 0xFFFFFFFF) == APF_OUTER_ID,
        "matches_nfl_outer_id": (
            zlib.crc32("REFERENCE.IFF".encode("utf-16le")) & 0xFFFFFFFF
        ) == NFL_OUTER_ID,
        "nfl_xbe_utf16le_literal_count": len(literal_offsets),
        "nfl_xbe_utf16le_literal_offsets": [f"0x{value:08x}" for value in literal_offsets],
    }

    report = {
        "schema": SCHEMA,
        "scope": {
            "read_only_static_and_asset_analysis": True,
            "launches_game_or_emulator": False,
            "executes_translated_guest_code": False,
            "writes_game_images": False,
            "runtime_reachability_proved": False,
        },
        "sources": {
            "apf_index": apf_pin,
            "nfl_index": nfl_pin,
            "nfl_xbe": xbe_pin,
            "apf_closed_book_gltf": source_pin(args.apf_gltf),
            "nfl_closed_book_gltf": source_pin(args.nfl_gltf),
            "nfl_material_texture_ledger": source_pin(args.nfl_material_tsv),
            "nfl_shield_png": source_pin(nfl_png),
            "ghidra_trace": source_pin(args.ghidra_trace),
        },
        "filename_identity": filename_hashes,
        "apf": apf,
        "nfl": nfl,
        "cross_title_text_lineage": texts,
        "cross_title_shield_art": {
            "dimensions": [128, 128],
            "apf_rgba_sha256": sha256_bytes(apf_rgba),
            "nfl_rgba_sha256": sha256_bytes(nfl_rgba),
            "rgba_byte_identical": apf_rgba == nfl_rgba,
            "channel_metrics": texture_metrics,
            "interpretation": (
                "the visible NFL shield survived a platform texture conversion; "
                "the decoded pixels are strongly correlated but not byte-identical"
            ),
        },
        "cross_title_shield_geometry": geometry,
        "executable_evidence": {
            "refr_type_hash": "0x15578f45",
            "apf_registry_descriptor_address": "0x820feafc",
            "apf_registry_runtime_node_address": "0x84eab870",
            "apf_refr_record_relocation_worker": "0x84ab0d58",
            "apf_refr_resource_lookup_owner_witness": "0x84ab0fa8",
            "apf_load_callback": "0x84ab10c0",
            "apf_destructor_callback": "0x84ab11a8",
            "compiled_refr_handler_present": True,
            "relocation_worker_proves": (
                "four counted 0x1c-byte record tables and five optional "
                "one-based self-relative pointer fields per record"
            ),
            "menu_or_state_route_to_reference_screen_proved": False,
        },
        "claims": {
            "safe": [
                "APF outer 1135 is the cross-platform descendant of NFL outer 110 reference.iff.",
                "APF ships an nfl_shield1 quad bound to material nfl_shield and a decoded NFL shield texture.",
                "APF ships a selectively edited, endian-converted descendant of NFL 2K5 reference_data.",
                "APF default.xex retains a registered REFR resource handler.",
            ],
            "not_proved": [
                "The reference-book screen is reachable from APF's shipped menus.",
                "The NFL shield is displayed during normal APF gameplay.",
                "The entire reference package is byte-identical across platforms.",
            ],
        },
        "portme": [
            "// PORTME: recover the APF menu/state owner that requests reference.iff or prove the package orphaned.",
            "// PORTME: recover source-equivalent REFR relocation/load callbacks at 0x84AB0D58 and 0x84AB10C0.",
            "// PORTME: map every REFR record field and build a reversible editor only after pointer/capacity ownership is proved.",
        ],
    }

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_tsv(
        args.diff_tsv_out,
        diff_rows,
        [
            "operation", "apf_sequence_index", "apf_offset", "apf_text",
            "nfl_sequence_index", "nfl_offset", "nfl_text",
        ],
    )
    write_tsv(
        args.licensed_tsv_out,
        licensed_rows,
        ["sequence_index", "offset", "categories", "team_tokens", "text"],
    )
    write_tsv(
        args.claims_tsv_out,
        [
            {
                "grade": "A_proven",
                "claim": "Retail APF 2K8 ships a converted NFL 2K5 reference.iff descendant with an actual bound NFL shield texture.",
                "evidence": "exact dual filename hashes; same three resources; nfl_shield1 draw -> material 3 nfl_shield -> 128x128 BC3 NFL shield; 4-vertex quad lineage",
                "boundary": "package/art/geometry lineage; normal APF display is not proved",
                "visual": str(apf_png.resolve()),
            },
            {
                "grade": "A_proven",
                "claim": "APF's reference database was selectively ported from NFL 2K5 rather than copied as untouched dead bytes.",
                "evidence": "987/988 APF printable strings match in order; 13 glossary entries removed; one Bengals/Raiders example shortened; 438 records and 1092 pointers close",
                "boundary": "compiled REFR handler exists; retail menu/state owner remains unproved",
                "visual": "reports/cut_content/apf_nfl_lineage/reference_remnants_text_diff.tsv",
            },
            {
                "grade": "boundary",
                "claim": "A playable or normally reachable APF reference-book screen has not been established.",
                "evidence": "no proved APF menu/state route to reference.iff in this pass",
                "boundary": "do not call the decoded shield an in-game APF screenshot",
                "visual": "docs/research/apf_reference_nfl_remnants.md",
            },
        ],
        ["grade", "claim", "evidence", "boundary", "visual"],
    )
    print(
        "APF_REFERENCE_NFL_REMNANTS_COMPLETE "
        f"shared_strings={texts['exact_ordered_string_occurrence_matches']} "
        f"apf_strings={texts['apf_printable_utf16_string_occurrences']} "
        f"removed_entries={texts['removed_nfl_glossary_entry_count']} "
        f"shield_corr_min={min(float(row['pearson_correlation']) for row in texture_metrics.values()):.6f} "
        "runtime=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceError, apf_inner.FormatError, apf_outer.FormatError, nfl_outer.FormatError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
