#!/usr/bin/env python3
"""Independently verify APF 2K8's whole-shell crest-atlas route."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "tools"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from mod_editor.core import platform_compat  # noqa: E402

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402


PATCH_SCHEMA = "apf2k8_helmet_shell_atlas_patch/v24"
VERIFY_SCHEMA = "apf2k8_helmet_shell_atlas_verify/v24"
OPERATION = "route_shell_draw_to_crest_atlas_and_neutralize_overlay"
VOLUME_SIZE = 1_140_850_688
OUTER_INDEX = 1310
OUTER_NAME_ID = 0xDB5E3E48
OUTER_OFFSET = 0x01570800
OUTER_SIZE = 0x017DE800
SOURCE_OUTER_SHA256 = "752bc94e99ae0bc1a3ec732c5b4912ef6ef234149183e76dc059973c714d792d"
SOURCE_SYSTEM_SHA256 = "5c121fcf01b96f2e087e9238584a511868b09ad60476658d023eb186f33dc1bb"
# Opaque-shell-body contract: the v24 Eagles design (uniform 0x88 alpha) is
# rejected by the writer; the regression input is the same RGB lattice with
# every alpha raised to 255.
EAGLES_DESIGN_RGBA_SHA256 = "ff3ebf78fda1b336cb03c5830511c3dc17bb5efd5e8eaa4792fd669fdc851cc7"
EAGLES_ATLAS_RGBA_SHA256 = "5dfeaeb7402abe37c3fddcff0ede91fd09b26d7600bdddd75791b0e54236bf39"
EAGLES_SCNE_SHA256 = "bd49f04cb2bf58fc91f024af6a76405f3cefab3f63d2d98f445a413b67ef5ca7"
INNER_INDEX = 128
INNER_FILE_ID = 0x4A3503FC
INNER_NAME = "helmet_00"
INNER_TYPE = "SCNE"
SYSTEM_PART_OFFSET = 0x00173680
SYSTEM_LENGTH = 0x000D5680
BLOCK_COUNT = 3
MAX_DECOMPRESSED = 128 * 1024 * 1024
STRIDE = 32
DRAW_RECORD_SIZE = 0x30
DRAW_RECORD_COUNT = 13
SHELL_DRAW_INDEX = 1
CARRIER_DRAW_INDEX = 2
SOURCE_SHELL_MATERIAL = 1
CREST_MATERIAL = 2
WIDTH = 512
HEIGHT = 512
RGBA_LENGTH = WIDTH * HEIGHT * 4
SEMANTIC_FRONT_Z = 13.15
SEMANTIC_REAR_Z = -11.16
SEMANTIC_TOP_Y = 18.87
SEMANTIC_BOTTOM_Y = 3.0


class VerifyError(ValueError):
    """The atlas, geometry route, preservation boundary, or receipt failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


@dataclass(frozen=True)
class LodSpec:
    node_index: int
    node_name: str
    draw_record_offset: int
    material_offset: int
    index_offset: int
    index_count: int
    shell_index_start: int
    shell_index_count: int
    carrier_index_start: int
    carrier_index_count: int
    carrier_vertex_start: int
    carrier_vertex_count: int
    stream_start: int
    vertex_count: int
    center: tuple[float, float, float]
    scale: tuple[float, float, float]
    shell_triangle_count: int


LODS = (
    LodSpec(
        0, "helmet_hi", 0x000099C0, 0x00009A10, 0x00009C30, 9773,
        2623, 4800, 7423, 1046, 2739, 326, 0x0000EA1C, 3856,
        (0.0, 4.927330017089844, 1.7508296966552734),
        (13.967263221740723,) * 3, 2464,
    ),
    LodSpec(
        32, "helmet_lo", 0x000CCA80, 0x000CCAD0, 0x000CCCF0, 1552,
        359, 659, 1018, 231, 476, 128, 0x000CDA9C, 799,
        (0.0, 2.8593978881835938, 2.8941473960876465),
        (16.119155883789062,) * 3, 432,
    ),
)


@dataclass(frozen=True)
class ParsedOuter:
    raw: bytes
    record: apf_inner.IFFRecord
    stored: tuple[bytes, ...]
    blocks: tuple[bytes, ...]
    system: bytes


class _BytesReader:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self, _entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.payload):
            raise apf_inner.FormatError("memory IFF read exceeds allocation")
        return self.payload[offset : offset + size]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fixed_entry() -> apf_outer.Entry:
    return apf_outer.Entry(
        table_index=OUTER_INDEX,
        name_id=OUTER_NAME_ID,
        offset_blocks=OUTER_OFFSET // 2048,
        size_blocks=OUTER_SIZE // 2048,
        virtual_offset=OUTER_OFFSET,
        size=OUTER_SIZE,
        head_hex="ff3bef94",
        segments=(apf_outer.Segment(0, "0A", OUTER_OFFSET, OUTER_SIZE),),
    )


def _parse_outer(payload: bytes, label: str) -> ParsedOuter:
    require(len(payload) == OUTER_SIZE, f"{label} outer length differs")
    reader = _BytesReader(payload)
    entry = _fixed_entry()
    try:
        record = apf_inner.parse_iff(reader, entry)
        stored = tuple(
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        )
        blocks = tuple(
            apf_inner.decode_block(reader, record, index, MAX_DECOMPRESSED)
            for index in range(record.block_count)
        )
    except apf_inner.FormatError as exc:
        raise VerifyError(f"could not parse {label} global.iff: {exc}") from exc
    require(not record.warnings and record.block_count == BLOCK_COUNT,
            f"{label} block inventory differs")
    require(len(record.files) > INNER_INDEX, f"{label} helmet_00 is missing")
    item = record.files[INNER_INDEX]
    require(
        item.file_id == INNER_FILE_ID
        and item.name == INNER_NAME
        and item.type_name == INNER_TYPE
        and len(item.parts) == 1
        and item.parts[0].block_index == 0
        and item.parts[0].offset == SYSTEM_PART_OFFSET
        and item.parts[0].length == SYSTEM_LENGTH,
        f"{label} helmet_00 ownership differs",
    )
    part = item.parts[0]
    system = blocks[0][part.offset : part.offset + part.length]
    require(len(system) == SYSTEM_LENGTH, f"{label} SCNE length differs")
    return ParsedOuter(payload, record, stored, blocks, system)


def _snorm(word: int) -> float:
    return max(word / 32767.0, -1.0)


def _vec3(payload: bytes, offset: int) -> tuple[float, float, float]:
    words = struct.unpack_from(">3h", payload, offset)
    return tuple(_snorm(word) for word in words)  # type: ignore[return-value]


def _position(payload: bytes, spec: LodSpec, vertex: int) -> tuple[float, float, float]:
    raw = _vec3(payload, spec.stream_start + vertex * STRIDE)
    return tuple(
        spec.center[axis] + raw[axis] * spec.scale[axis] for axis in range(3)
    )  # type: ignore[return-value]


def _unit(value: Sequence[float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in value))
    require(math.isfinite(length) and length > 1.0e-12, "invalid vector")
    return tuple(component / length for component in value)  # type: ignore[return-value]


def _uv(payload: bytes, spec: LodSpec, vertex: int) -> tuple[float, float]:
    offset = spec.stream_start + vertex * STRIDE
    return (
        2.0 * _snorm(struct.unpack_from(">h", payload, offset + 14)[0]),
        2.0 * _snorm(struct.unpack_from(">h", payload, offset + 22)[0]),
    )


def _indices(payload: bytes, spec: LodSpec) -> tuple[int, ...]:
    return struct.unpack_from(f">{spec.index_count}H", payload, spec.index_offset)


def _triangles(words: Sequence[int]) -> list[tuple[int, int, int]]:
    output: list[tuple[int, int, int]] = []
    strip: list[int] = []
    for index in words:
        if index == 0xFFFF:
            strip.clear()
            continue
        strip.append(index)
        if len(strip) >= 3:
            first, second, third = strip[-3:]
            if (len(strip) - 3) & 1:
                first, second = second, first
            if len({first, second, third}) == 3:
                output.append((first, second, third))
    return output


def _outer_shell_faces(
    payload: bytes, spec: LodSpec,
) -> tuple[list[tuple[int, int, int]], list[tuple[float, float, float]]]:
    positions = [_position(payload, spec, index) for index in range(spec.vertex_count)]
    normals = [
        _unit(_vec3(payload, spec.stream_start + index * STRIDE + 8))
        for index in range(spec.vertex_count)
    ]
    words = _indices(payload, spec)
    faces = _triangles(words[
        spec.shell_index_start : spec.shell_index_start + spec.shell_index_count
    ])
    require(len(faces) == spec.shell_triangle_count,
            f"{spec.node_name} shell topology differs")
    outer: list[tuple[int, int, int]] = []
    for face in faces:
        center = tuple(
            sum(positions[index][axis] for index in face) / 3.0 for axis in range(3)
        )
        normal = tuple(sum(normals[index][axis] for index in face) for axis in range(3))
        radial = (center[0], center[1] - spec.center[1], center[2] - spec.center[2])
        if sum(a * b for a, b in zip(normal, radial)) > 0.0:
            outer.append(face)
    require(bool(outer), f"{spec.node_name} exterior shell is missing")
    return outer, positions


def _semantic_pixel(point: tuple[float, float, float]) -> int | None:
    u_value = (SEMANTIC_FRONT_Z - point[2]) / (SEMANTIC_FRONT_Z - SEMANTIC_REAR_Z)
    v_value = (SEMANTIC_TOP_Y - point[1]) / (SEMANTIC_TOP_Y - SEMANTIC_BOTTOM_Y)
    if not (0.0 <= u_value <= 1.0 and 0.0 <= v_value <= 1.0):
        return None
    x_value = min(WIDTH - 1, max(0, round(u_value * WIDTH - 0.5)))
    y_value = min(HEIGHT - 1, max(0, round(v_value * HEIGHT - 0.5)))
    return y_value * WIDTH + x_value


def _atlas_sample_map(
    payload: bytes, spec: LodSpec,
) -> tuple[list[int], dict[str, Any]]:
    faces, positions = _outer_shell_faces(payload, spec)
    vertices = {index for face in faces for index in face}
    uvs = {index: _uv(payload, spec, index) for index in vertices}
    determinants = []
    for face in faces:
        first, second, third = (uvs[index] for index in face)
        determinants.append(
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        )
    require(min(map(abs, determinants)) > 1.0e-12,
            f"{spec.node_name} stock atlas has a collapsed triangle")
    require(not (min(determinants) < 0.0 < max(determinants)),
            f"{spec.node_name} stock atlas orientation is mixed")
    right = [face for face in faces if all(positions[index][0] >= -1.0e-6 for index in face)]
    left = [face for face in faces if all(positions[index][0] <= 1.0e-6 for index in face)]
    require(len(right) == len(left) and len(right) + len(left) == len(faces),
            f"{spec.node_name} stock atlas is not bilateral")
    samples = [-2] * (WIDTH * HEIGHT)
    for face in faces:
        triangle = [uvs[index] for index in face]
        first_x = max(0, math.ceil(min(value[0] for value in triangle) * WIDTH - 0.5))
        last_x = min(WIDTH - 1, math.floor(max(value[0] for value in triangle) * WIDTH - 0.5))
        first_y = max(0, math.ceil(min(value[1] for value in triangle) * HEIGHT - 0.5))
        last_y = min(HEIGHT - 1, math.floor(max(value[1] for value in triangle) * HEIGHT - 0.5))
        first, second, third = triangle
        denominator = (
            (second[1] - third[1]) * (first[0] - third[0])
            + (third[0] - second[0]) * (first[1] - third[1])
        )
        for y_pixel in range(first_y, last_y + 1):
            atlas_v = (y_pixel + 0.5) / HEIGHT
            for x_pixel in range(first_x, last_x + 1):
                atlas_u = (x_pixel + 0.5) / WIDTH
                first_weight = (
                    (second[1] - third[1]) * (atlas_u - third[0])
                    + (third[0] - second[0]) * (atlas_v - third[1])
                ) / denominator
                second_weight = (
                    (third[1] - first[1]) * (atlas_u - third[0])
                    + (first[0] - third[0]) * (atlas_v - third[1])
                ) / denominator
                third_weight = 1.0 - first_weight - second_weight
                if min(first_weight, second_weight, third_weight) < -1.0e-10:
                    continue
                point = tuple(
                    first_weight * positions[face[0]][axis]
                    + second_weight * positions[face[1]][axis]
                    + third_weight * positions[face[2]][axis]
                    for axis in range(3)
                )
                sample = _semantic_pixel(point)
                value = -1 if sample is None else sample
                atlas_index = y_pixel * WIDTH + x_pixel
                require(samples[atlas_index] == -2,
                        f"{spec.node_name} stock atlas raster overlaps")
                samples[atlas_index] = value
    return samples, {
        "node_index": spec.node_index,
        "node_name": spec.node_name,
        "exterior_face_count": len(faces),
        "faces_per_side": len(right),
        "atlas_covered_texels": sum(value != -2 for value in samples),
        "semantic_envelope_texels": sum(value >= 0 for value in samples),
        "minimum_absolute_uv_triangle_determinant": min(map(abs, determinants)),
        "mixed_uv_orientation": False,
        "projected_overlap_count": 0,
    }


def _expected_atlas(source: bytes, design: bytes) -> tuple[bytes, list[dict[str, Any]]]:
    require(len(design) == RGBA_LENGTH, "design RGBA length differs")
    require(design[:3] == b"\0\0\0", "design background is not black")
    active = 0
    for pixel, offset in enumerate(range(0, len(design), 4)):
        red, green, blue, alpha = design[offset : offset + 4]
        require(
            blue == 0 and not (red % 17 or green % 17 or alpha % 17)
            and red + green <= 255,
            f"design region-mask texel {pixel} is outside the proved contract",
        )
        active += bool(red or green)
    require(bool(active), "design region mask is empty")
    maps: list[list[int]] = []
    rows: list[dict[str, Any]] = []
    for spec in LODS:
        sample_map, row = _atlas_sample_map(source, spec)
        maps.append(sample_map)
        rows.append(row)
    output = bytearray(design[:4] * (WIDTH * HEIGHT))
    for atlas_index, (high, low) in enumerate(zip(*maps)):
        sample = low if high == -2 else high
        if sample >= 0:
            output[atlas_index * 4 : atlas_index * 4 + 4] = design[
                sample * 4 : sample * 4 + 4
            ]
    return bytes(output), rows


def verify_geometry(
    source: bytes,
    output: bytes,
    *,
    design_rgba: bytes,
    atlas_rgba: bytes,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    require(len(source) == SYSTEM_LENGTH and len(output) == SYSTEM_LENGTH,
            "source/output SCNE length differs")
    require(sha256_bytes(source) == SOURCE_SYSTEM_SHA256, "source SCNE hash differs")
    expected_atlas, atlas_rows = _expected_atlas(source, bytes(design_rgba))
    require(bytes(atlas_rgba) == expected_atlas,
            "shell atlas is not the independent fixed-coordinate bake")
    allowed: set[int] = set()
    rows: list[dict[str, Any]] = []
    for spec, atlas_row in zip(LODS, atlas_rows):
        stream_end = spec.stream_start + spec.vertex_count * STRIDE
        require(source[spec.stream_start:stream_end] == output[spec.stream_start:stream_end],
                f"{spec.node_name} vertex/UV stream changed")
        before_records = [
            source[spec.draw_record_offset + number * DRAW_RECORD_SIZE:
                   spec.draw_record_offset + (number + 1) * DRAW_RECORD_SIZE]
            for number in range(DRAW_RECORD_COUNT)
        ]
        after_records = [
            output[spec.draw_record_offset + number * DRAW_RECORD_SIZE:
                   spec.draw_record_offset + (number + 1) * DRAW_RECORD_SIZE]
            for number in range(DRAW_RECORD_COUNT)
        ]
        require(struct.unpack_from(">I", before_records[1], 0x20)[0] == SOURCE_SHELL_MATERIAL,
                f"{spec.node_name} source shell material differs")
        require(struct.unpack_from(">I", after_records[1], 0x20)[0] == CREST_MATERIAL,
                f"{spec.node_name} output shell material differs")
        normalized = bytearray(after_records[1])
        normalized[0x20:0x24] = before_records[1][0x20:0x24]
        require(bytes(normalized) == before_records[1],
                f"{spec.node_name} shell draw changed outside material")
        for number in (0, *range(2, DRAW_RECORD_COUNT)):
            require(after_records[number] == before_records[number],
                    f"{spec.node_name} draw {number} record changed")
        allowed.update(range(spec.material_offset, spec.material_offset + 4))
        before_indices = _indices(source, spec)
        after_indices = _indices(output, spec)
        require(
            before_indices[:spec.carrier_index_start]
            == after_indices[:spec.carrier_index_start]
            and before_indices[spec.carrier_index_start + spec.carrier_index_count:]
            == after_indices[spec.carrier_index_start + spec.carrier_index_count:],
            f"{spec.node_name} indices changed outside draw 2",
        )
        neutral = after_indices[
            spec.carrier_index_start : spec.carrier_index_start + spec.carrier_index_count
        ]
        require(len(set(neutral)) == 1, f"{spec.node_name} draw 2 is not one degenerate index")
        repeated = neutral[0]
        require(
            spec.carrier_vertex_start <= repeated
            < spec.carrier_vertex_start + spec.carrier_vertex_count,
            f"{spec.node_name} degenerate index escapes draw-2 allocation",
        )
        require(not _triangles(neutral), f"{spec.node_name} draw 2 still has triangles")
        index_start = spec.index_offset + spec.carrier_index_start * 2
        allowed.update(range(index_start, index_start + spec.carrier_index_count * 2))
        rows.append({
            **atlas_row,
            "shell_draw_material_before": SOURCE_SHELL_MATERIAL,
            "shell_draw_material_after": CREST_MATERIAL,
            "neutralized_draw": CARRIER_DRAW_INDEX,
            "neutralized_index_word_count": len(neutral),
            "neutralized_repeated_vertex": repeated,
            "neutralized_triangle_count": 0,
            "vertex_uv_stream_exact": True,
            "draws_0_and_3_through_12_exact": True,
        })
    changed = {index for index, pair in enumerate(zip(source, output)) if pair[0] != pair[1]}
    require(bool(changed) and changed <= allowed,
            "SCNE diff escapes material words/draw-2 index windows")
    relation = {
        "design_rgba_sha256": sha256_bytes(bytes(design_rgba)),
        "atlas_rgba_sha256": sha256_bytes(bytes(atlas_rgba)),
        "fixed_physical_semantic_mapping": True,
        "nearest_neighbour": True,
        "palette_values_preserved": True,
    }
    return rows, len(changed), relation


def _normalized_header(parsed: ParsedOuter) -> bytes:
    header = bytearray(parsed.raw[:parsed.record.header_size])
    header[0x08:0x0C] = b"\0" * 4
    for index in range(parsed.record.block_count):
        start = apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE
        header[start + 20:start + 28] = b"\0" * 8
    return bytes(header)


def _footer(parsed: ParsedOuter) -> bytes:
    require(parsed.record.footer is not None, "IFF footer is missing")
    size = 8 + parsed.record.footer.payload_size
    value = parsed.raw[parsed.record.file_length:parsed.record.file_length + size]
    require(not any(parsed.raw[parsed.record.file_length + size:]),
            "outer allocation tail is nonzero")
    return value


def _receipt(receipt: Mapping[str, Any] | Path) -> dict[str, Any]:
    try:
        value = json.loads(receipt.read_bytes()) if isinstance(receipt, Path) else dict(receipt)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerifyError(f"could not read receipt: {exc}") from exc
    require(isinstance(value, dict), "receipt root is not an object")
    return value


def verify_outer(
    source_outer: bytes,
    output_outer: bytes,
    receipt: Mapping[str, Any] | Path,
    *,
    design_rgba: bytes,
    atlas_rgba: bytes,
) -> dict[str, Any]:
    source = _parse_outer(bytes(source_outer), "source")
    output = _parse_outer(bytes(output_outer), "output")
    require(sha256_bytes(source.raw) == SOURCE_OUTER_SHA256, "source outer hash differs")
    geometry, changed_count, relation = verify_geometry(
        source.system, output.system,
        design_rgba=bytes(design_rgba), atlas_rgba=bytes(atlas_rgba),
    )
    require(source.blocks[1:] == output.blocks[1:], "decoded sibling blocks changed")
    require(source.stored[1:] == output.stored[1:], "stored sibling blocks changed")
    require(
        source.blocks[0][:SYSTEM_PART_OFFSET] == output.blocks[0][:SYSTEM_PART_OFFSET]
        and source.blocks[0][SYSTEM_PART_OFFSET + SYSTEM_LENGTH:]
        == output.blocks[0][SYSTEM_PART_OFFSET + SYSTEM_LENGTH:],
        "decoded block 0 changed outside helmet_00 SCNE",
    )
    require(_normalized_header(source) == _normalized_header(output),
            "IFF metadata outside compressed offsets/lengths changed")
    require(_footer(source) == _footer(output), "IFF footer changed")
    document = _receipt(receipt)
    require((document.get("schema"), document.get("operation")) == (PATCH_SCHEMA, OPERATION),
            "receipt schema/operation differs")
    source_row = document.get("source", {})
    result = document.get("result", {})
    metrics = document.get("metrics", {})
    preservation = document.get("preservation", {})
    require(source_row.get("outer_entry_sha256") == sha256_bytes(source.raw),
            "receipt source outer hash differs")
    require(source_row.get("source_scne_sha256") == sha256_bytes(source.system),
            "receipt source SCNE hash differs")
    require(result.get("outer_entry_sha256") == sha256_bytes(output.raw),
            "receipt output outer hash differs")
    require(result.get("output_scne_sha256") == sha256_bytes(output.system),
            "receipt output SCNE hash differs")
    require(result.get("shell_atlas_rgba_sha256") == relation["atlas_rgba_sha256"],
            "receipt atlas hash differs")
    require(metrics.get("changed_byte_count") == changed_count,
            "receipt changed-byte count differs")
    atlas_bake = metrics.get("atlas_bake", {})
    require(atlas_bake.get("design_rgba_sha256") == relation["design_rgba_sha256"]
            and atlas_bake.get("atlas_rgba_sha256") == relation["atlas_rgba_sha256"],
            "receipt atlas bake hashes differ")
    for flag in (
        "all_vertex_streams_including_stock_uv_atlas_exact",
        "decoded_block0_outside_scne_exact",
        "draws_0_and_3_through_12_exact",
        "draw_1_exact_except_material_word_1_to_2",
        "draw_2_record_and_vertices_exact",
        "draw_2_indices_replaced_only_by_in_range_degenerates",
        "accessory_draws_and_material_routes_exact",
        "sibling_blocks_decoded_exact",
        "sibling_blocks_stored_exact",
    ):
        require(preservation.get(flag) is True, f"receipt preservation flag {flag} differs")
    eagles = relation["design_rgba_sha256"] == EAGLES_DESIGN_RGBA_SHA256
    if eagles:
        require(relation["atlas_rgba_sha256"] == EAGLES_ATLAS_RGBA_SHA256,
                "Eagles regression atlas hash differs")
        require(sha256_bytes(output.system) == EAGLES_SCNE_SHA256,
                "Eagles regression SCNE hash differs")
    return {
        "schema": VERIFY_SCHEMA,
        "verified": True,
        "geometry": geometry,
        "inputs": relation,
        "output": {
            "outer_entry_sha256": sha256_bytes(output.raw),
            "scne_sha256": sha256_bytes(output.system),
        },
        "proof": {
            "stock_shell_atlas_noncollapsed_unmixed_and_nonoverlapping": True,
            "fixed_semantic_bake_exact": True,
            "bilateral_shell_mapping": True,
            "shell_vertices_indices_and_uv_exact": True,
            "old_overlay_zero_triangle_degenerate": True,
            "accessory_draws_exact": True,
            "changed_scne_byte_count": changed_count,
            "eagles_regression_hash_checked": eagles,
            "sibling_blocks_exact": True,
        },
    }


def _regular_volume(path: Path, label: str) -> None:
    metadata = path.lstat()
    require(stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode),
            f"{label} must be a regular non-symlink file")
    require(metadata.st_size == VOLUME_SIZE, f"{label} size differs")


def _read_outer_volume(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        value = platform_compat.pread(descriptor, OUTER_SIZE, OUTER_OFFSET)
    finally:
        os.close(descriptor)
    require(len(value) == OUTER_SIZE, "short outer allocation read")
    return value


def verify_volumes(
    source_volume: Path,
    output_volume: Path,
    receipt: Mapping[str, Any] | Path,
    *,
    design_rgba: bytes,
    atlas_rgba: bytes,
) -> dict[str, Any]:
    _regular_volume(source_volume, "source volume")
    _regular_volume(output_volume, "output volume")
    report = verify_outer(
        _read_outer_volume(source_volume), _read_outer_volume(output_volume), receipt,
        design_rgba=design_rgba, atlas_rgba=atlas_rgba,
    )
    report["proof"]["outer_1310_reopened_from_volume"] = True
    return report


def _read_outer_file(path: Path, label: str) -> bytes:
    metadata = path.lstat()
    require(stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode),
            f"{label} must be a regular non-symlink file")
    require(metadata.st_size == OUTER_SIZE, f"{label} size differs")
    return path.read_bytes()


def _load_rgba(path: Path, label: str) -> bytes:
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = WIDTH * HEIGHT
        with Image.open(path) as image:
            image.load()
            require(image.size == (WIDTH, HEIGHT), f"{label} is not 512x512")
            return image.convert("RGBA").tobytes()
    except VerifyError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise VerifyError(f"could not decode {label}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--atlas", required=True, type=Path)
    parser.add_argument("--volumes", action="store_true")
    args = parser.parse_args(argv)
    try:
        design = _load_rgba(args.design, "design PNG")
        atlas = _load_rgba(args.atlas, "atlas PNG")
        if args.volumes:
            report = verify_volumes(
                args.source, args.output, args.receipt,
                design_rgba=design, atlas_rgba=atlas,
            )
        else:
            report = verify_outer(
                _read_outer_file(args.source, "source outer"),
                _read_outer_file(args.output, "output outer"),
                args.receipt, design_rgba=design, atlas_rgba=atlas,
            )
    except (OSError, VerifyError) as exc:
        parser.exit(2, f"helmet crest wrap verification failed: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
