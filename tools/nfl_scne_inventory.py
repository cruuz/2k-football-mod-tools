#!/usr/bin/env python3
"""Inventory and validate every recovered NFL 2K5 SCNE descriptor.

The executable relocator at default.xbe:0x0002F140 proves a 0x54-byte scene
descriptor containing eight (count, pointer) pairs.  Each serialized pointer
is signed, field-local, and biased by -1::

    target = field_address - 1 + signed_relative_value

This tool applies that rule without mutating the decoded data, checks every
table range against the declared system buffer, enumerates the names exposed
by the corresponding record relocators, and validates the embedded Xbox
texture descriptors with the already verified ``nfl_txtr`` converter.

It also inventories the code-proven multi-stream vertex declarations and
bounded NV2A push-command topology.  Attribute semantics beyond the Xbox
input-register numbers remain explicit rather than being guessed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from nfl_outer import parse_archive, read_entry_range
from nfl_scene_probe import ProbeError, ResourceRecord, decode_resource, parse_inventory, utf16z
from nfl_txtr import Chunk, TextureInfo, TxtrError, XBOX_FORMAT_NAMES, texture_to_rgba, write_png


SCHEMA = "nfl2k5_scne_inventory/v1"
DESCRIPTOR_SIZE = 0x54
MAX_TABLE_RECORDS = 1_000_000


@dataclass(frozen=True)
class TableSpec:
    key: str
    semantic: str
    count_offset: int
    pointer_offset: int
    stride: int
    relocator: int | None


TABLE_SPECS = (
    TableSpec("aux_14", "unknown auxiliary records", 0x0C, 0x10, 0x14, 0x000252A0),
    TableSpec("textures", "embedded Xbox texture descriptors", 0x14, 0x18, 0x20, 0x00034DF0),
    TableSpec("materials", "named material candidates", 0x1C, 0x20, 0x80, 0x000304B0),
    TableSpec("nodes", "named node/reference candidates", 0x24, 0x28, 0x60, 0x00021630),
    TableSpec("shapes", "complex mesh/shape candidates", 0x2C, 0x30, 0x100, 0x00022F90),
    TableSpec("markers", "named marker candidates", 0x34, 0x38, 0x40, 0x00038530),
    TableSpec("aux_60", "unknown records with pointer at +0x00", 0x3C, 0x40, 0x60, None),
    TableSpec("aux_50", "unknown records with pointer at +0x40", 0x44, 0x48, 0x50, None),
)

# Cxbx-Reloaded XbD3D8Types.h names and byte widths for the retail Xbox
# vertex input encodings used by the 16 register descriptors at shape +0x84.
VERTEX_FORMATS: dict[int, tuple[str, int, int]] = {
    0x02: ("NONE", 0, 0),
    0x11: ("NORMSHORT1", 2, 1),
    0x12: ("FLOAT1", 4, 1),
    0x14: ("PBYTE1", 1, 1),
    0x15: ("SHORT1", 2, 1),
    0x16: ("NORMPACKED3", 4, 3),
    0x21: ("NORMSHORT2", 4, 2),
    0x22: ("FLOAT2", 8, 2),
    0x24: ("PBYTE2", 2, 2),
    0x25: ("SHORT2", 4, 2),
    0x31: ("NORMSHORT3", 6, 3),
    0x32: ("FLOAT3", 12, 3),
    0x34: ("PBYTE3", 3, 3),
    0x35: ("SHORT3", 6, 3),
    0x40: ("D3DCOLOR", 4, 4),
    0x41: ("NORMSHORT4", 8, 4),
    0x42: ("FLOAT4", 16, 4),
    0x44: ("PBYTE4", 4, 4),
    0x45: ("SHORT4", 8, 4),
    0x72: ("FLOAT2H", 12, 4),
}


class ScneError(ValueError):
    """A strict SCNE structural assertion failed."""


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def s32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def resolve_relative(data: bytes, field_offset: int, limit: int, label: str) -> int | None:
    if field_offset < 0 or field_offset + 4 > limit:
        raise ScneError(f"{label}: pointer field 0x{field_offset:x} is out of bounds")
    relative = s32(data, field_offset)
    if relative == 0:
        return None
    target = field_offset - 1 + relative
    if not 0 <= target < limit:
        raise ScneError(
            f"{label}: pointer at 0x{field_offset:x} resolves to 0x{target:x}, "
            f"outside 0x{limit:x}-byte system buffer"
        )
    return target


def read_name(data: bytes, target: int | None, limit: int, label: str) -> str | None:
    if target is None:
        return None
    try:
        value, _ = utf16z(data, target, limit)
    except ProbeError as exc:
        raise ScneError(f"{label}: {exc}") from exc
    if not value:
        raise ScneError(f"{label}: empty UTF-16LE string at 0x{target:x}")
    if any(ord(character) < 0x20 for character in value):
        raise ScneError(f"{label}: control character in UTF-16LE string {value!r}")
    return value


def pointer_name(
    data: bytes,
    field: int,
    limit: int,
    label: str,
) -> tuple[int | None, str | None]:
    target = resolve_relative(data, field, limit, label)
    return target, read_name(data, target, limit, label)


def texture_info(data: bytes, offset: int, scene_name: str, index: int) -> TextureInfo:
    if offset < 0 or offset + 0x20 > len(data):
        raise ScneError(f"embedded texture {index}: descriptor 0x{offset:x} is out of bounds")
    unknown0, pixel_offset, palette_offset, packed_format, packed_size, flags = struct.unpack_from(
        "<6I", data, offset
    )
    dimensions = (packed_format >> 4) & 0xF
    format_code = (packed_format >> 8) & 0xFF
    mip_levels = (packed_format >> 16) & 0xF
    if packed_size == 0:
        width = 1 << ((packed_format >> 20) & 0xF)
        height = 1 << ((packed_format >> 24) & 0xF)
    else:
        width = packed_size & 0xFFFF
        height = (packed_size >> 16) & 0xFFFF
    depth = 1 << ((packed_format >> 28) & 0xF)
    return TextureInfo(
        name=f"{scene_name}/embedded_{index:04d}",
        name_offset=0,
        descriptor_offset=offset,
        pixel_offset=pixel_offset,
        palette_offset=palette_offset,
        packed_format=packed_format,
        packed_size=packed_size,
        descriptor_flags=flags,
        dimensions=dimensions,
        format_code=format_code,
        format_name=XBOX_FORMAT_NAMES.get(format_code, f"UNKNOWN_0x{format_code:02X}"),
        mip_levels=mip_levels,
        width=width,
        height=height,
        depth=depth,
    )


def texture_record(
    output: bytes,
    resource: ResourceRecord,
    descriptor_offset: int,
    scene_name: str,
    texture_index: int,
    video_sha256: str,
    conversion_cache: dict[tuple[object, ...], dict[str, str]],
) -> dict[str, object]:
    info = texture_info(output, descriptor_offset, scene_name, texture_index)
    chunk = Chunk(
        index=resource.chunk_index,
        offset=0,
        kind="TXTR",
        stored_size=0,
        system_bytes=resource.word_08,
        video_bytes=resource.word_0c,
        compression_magic=0,
        overlap_scratch_bytes=0,
        reserved0=0,
        reserved1=0,
    )
    record: dict[str, object] = {
        "index": texture_index,
        "descriptor_offset": descriptor_offset,
        "unknown0": f"0x{u32(output, descriptor_offset):08x}",
        "extra_word_18": f"0x{u32(output, descriptor_offset + 0x18):08x}",
        "extra_word_1c": f"0x{u32(output, descriptor_offset + 0x1C):08x}",
        **{
            key: value
            for key, value in asdict(info).items()
            if key not in ("name", "name_offset", "descriptor_offset")
        },
    }
    cache_key = (
        video_sha256,
        info.pixel_offset,
        info.palette_offset,
        info.packed_format,
        info.packed_size,
        info.descriptor_flags,
    )
    cached = conversion_cache.get(cache_key)
    if cached is None:
        try:
            rgba = texture_to_rgba(output, chunk, info)
        except TxtrError as exc:
            cached = {"conversion_status": "portme", "conversion_error": str(exc)}
        else:
            cached = {
                "conversion_status": "base_level_supported",
                "rgba_sha256": hashlib.sha256(rgba).hexdigest(),
            }
        conversion_cache[cache_key] = cached
    record.update(cached)
    return record


def parse_push_stream(
    data: bytes,
    offset: int,
    word_count: int,
    system_size: int,
    vertex_count: int,
    label: str,
) -> dict[str, object]:
    """Parse a bounded NV2A push stream without executing it."""
    end = offset + word_count * 4
    if end > system_size:
        raise ScneError(
            f"{label}: {word_count} command words at 0x{offset:x} exceed "
            f"system buffer 0x{system_size:x}"
        )
    cursor = offset
    method_counts: Counter[str] = Counter()
    primitive_modes: Counter[str] = Counter()
    index_count = 0
    max_index: int | None = None
    draw_array_vertex_count = 0
    command_count = 0
    unknown_methods: Counter[str] = Counter()
    primitive_names = {
        0: "END",
        1: "POINTS",
        2: "LINES",
        3: "LINE_LOOP",
        4: "LINE_STRIP",
        5: "TRIANGLES",
        6: "TRIANGLE_STRIP",
        7: "TRIANGLE_FAN",
        8: "QUADS",
        9: "QUAD_STRIP",
        10: "POLYGON",
    }
    while cursor < end:
        header = u32(data, cursor)
        cursor += 4
        instruction = (header >> 29) & 7
        signature = header & 0xE0030003
        if signature not in (0, 0x40000000):
            raise ScneError(
                f"{label}: unsupported NV2A push instruction {instruction} "
                f"(word 0x{header:08x}) at 0x{cursor - 4:x}"
            )
        method = header & 0x1FFC
        parameter_count = (header >> 18) & 0x7FF
        if cursor + parameter_count * 4 > end:
            raise ScneError(
                f"{label}: method 0x{method:04x} declares {parameter_count} "
                "parameters beyond the serialized word count"
            )
        parameters = struct.unpack_from(f"<{parameter_count}I", data, cursor)
        cursor += parameter_count * 4
        command_count += 1
        method_counts[f"0x{method:04x}"] += 1
        if method == 0x17FC:
            for parameter in parameters:
                primitive_modes[primitive_names.get(parameter, f"UNKNOWN_{parameter}")] += 1
        elif method == 0x1800:
            for parameter in parameters:
                for index in (parameter & 0xFFFF, parameter >> 16):
                    index_count += 1
                    max_index = index if max_index is None else max(max_index, index)
        elif method == 0x1808:
            for index in parameters:
                index_count += 1
                max_index = index if max_index is None else max(max_index, index)
        elif method == 0x1810:
            for parameter in parameters:
                start = parameter & 0x00FFFFFF
                count = (parameter >> 24) + 1
                draw_array_vertex_count += count
                draw_max = start + count - 1
                max_index = draw_max if max_index is None else max(max_index, draw_max)
        else:
            unknown_methods[f"0x{method:04x}"] += 1
    if cursor != end:
        raise ScneError(f"{label}: command parser did not end on the declared boundary")
    indices_in_bounds = max_index is None or max_index < vertex_count
    if not indices_in_bounds:
        raise ScneError(
            f"{label}: maximum referenced vertex {max_index} >= vertex_count {vertex_count}"
        )
    return {
        "command_offset": offset,
        "word_count": word_count,
        "command_count": command_count,
        "method_counts": dict(sorted(method_counts.items())),
        "unknown_method_counts": dict(sorted(unknown_methods.items())),
        "primitive_mode_counts": dict(sorted(primitive_modes.items())),
        "index_element_count": index_count,
        "draw_array_vertex_count": draw_array_vertex_count,
        "maximum_vertex_index": max_index,
        "all_vertex_references_in_bounds": indices_in_bounds,
    }


def table_layout(data: bytes, descriptor: int, system_size: int) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for spec in TABLE_SPECS:
        count = u32(data, descriptor + spec.count_offset)
        if count > MAX_TABLE_RECORDS:
            raise ScneError(f"{spec.key}: implausible count {count}")
        pointer_field = descriptor + spec.pointer_offset
        start = resolve_relative(data, pointer_field, system_size, spec.key)
        if count and start is None:
            raise ScneError(f"{spec.key}: count {count} has a null table pointer")
        end = start if start is not None else None
        if start is not None:
            end = start + count * spec.stride
            if end > system_size:
                raise ScneError(
                    f"{spec.key}: 0x{start:x} + {count}*0x{spec.stride:x} "
                    f"ends at 0x{end:x}, beyond system buffer 0x{system_size:x}"
                )
        result[spec.key] = {
            "semantic": spec.semantic,
            "count": count,
            "pointer_field": pointer_field,
            "offset": start,
            "end_offset": end,
            "stride": spec.stride,
            "relocator": f"0x{spec.relocator:08x}" if spec.relocator is not None else None,
        }
    return result


def add_name(
    rows: list[dict[str, object]],
    scene_index: int,
    resource: ResourceRecord,
    scene_name: str,
    role: str,
    record_index: int,
    record_offset: int,
    pointer_field: int,
    pointer_target: int | None,
    value: str | None,
) -> None:
    if value is None:
        return
    rows.append(
        {
            "scene_index": scene_index,
            "outer_index": resource.outer_index,
            "chunk_index": resource.chunk_index,
            "scene_name": scene_name,
            "role": role,
            "record_index": record_index,
            "record_offset": record_offset,
            "pointer_field": pointer_field,
            "pointer_target": pointer_target,
            "value": value,
        }
    )


def parse_scene(
    scene_index: int,
    resource: ResourceRecord,
    output: bytes,
    conversion_cache: dict[tuple[object, ...], dict[str, str]],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]], bytes | None]:
    if len(output) != resource.word_08 + resource.word_0c:
        raise ScneError(
            f"scene {scene_index}: decoded 0x{len(output):x}, wrapper declares "
            f"0x{resource.word_08 + resource.word_0c:x}"
        )
    system_size = resource.word_08
    if system_size < 0x18 or output[0x0C:0x10] != b"SCNE":
        raise ScneError(f"scene {scene_index}: missing SCNE object marker at +0x0c")

    header_name_target, header_name = pointer_name(
        output, 0x10, system_size, f"scene {scene_index} header name"
    )
    descriptor = resolve_relative(output, 0x14, system_size, f"scene {scene_index} descriptor")
    if descriptor is None or descriptor + DESCRIPTOR_SIZE > system_size:
        raise ScneError(f"scene {scene_index}: unavailable 0x54-byte descriptor")
    descriptor_name_target, descriptor_name = pointer_name(
        output, descriptor, system_size, f"scene {scene_index} descriptor name"
    )
    if header_name != descriptor_name:
        raise ScneError(
            f"scene {scene_index}: header name {header_name!r} != descriptor name {descriptor_name!r}"
        )
    assert header_name is not None
    layout = table_layout(output, descriptor, system_size)

    name_rows: list[dict[str, object]] = []
    add_name(
        name_rows, scene_index, resource, header_name, "scene", 0, 0,
        0x10, header_name_target, header_name,
    )

    textures: list[dict[str, object]] = []
    video_sha256 = hashlib.sha256(output[system_size:]).hexdigest()
    texture_layout = layout["textures"]
    texture_start = texture_layout["offset"]
    assert texture_start is not None or texture_layout["count"] == 0
    for index in range(int(texture_layout["count"])):
        offset = int(texture_start) + index * 0x20
        item = texture_record(
            output, resource, offset, header_name, index, video_sha256, conversion_cache
        )
        textures.append(item)

    materials: list[dict[str, object]] = []
    mappings: list[dict[str, object]] = []
    material_layout = layout["materials"]
    material_start = material_layout["offset"]
    assert material_start is not None or material_layout["count"] == 0
    mapped_names: dict[int, list[str]] = defaultdict(list)
    for index in range(int(material_layout["count"])):
        offset = int(material_start) + index * 0x80
        name_target, name = pointer_name(
            output, offset, system_size, f"scene {scene_index} material {index} name"
        )
        add_name(
            name_rows, scene_index, resource, header_name, "material_candidate", index,
            offset, offset, name_target, name,
        )
        texture_pointer_field = offset + 0x30
        texture_target = resolve_relative(
            output, texture_pointer_field, system_size,
            f"scene {scene_index} material {index} texture",
        )
        texture_index: int | None = None
        if texture_target is not None:
            if texture_start is None or not (
                int(texture_start) <= texture_target < int(texture_layout["end_offset"])
            ) or (texture_target - int(texture_start)) % 0x20:
                raise ScneError(
                    f"scene {scene_index} material {index}: +0x30 target "
                    f"0x{texture_target:x} is not an embedded texture descriptor"
                )
            texture_index = (texture_target - int(texture_start)) // 0x20
            mapped_names[texture_index].append(name or "<unnamed>")
        material = {
            "index": index,
            "record_offset": offset,
            "name": name,
            "name_target": name_target,
            "texture_pointer_field": texture_pointer_field,
            "texture_target": texture_target,
            "texture_index": texture_index,
        }
        materials.append(material)
        texture = textures[texture_index] if texture_index is not None else None
        mappings.append(
            {
                "scene_index": scene_index,
                "outer_index": resource.outer_index,
                "chunk_index": resource.chunk_index,
                "scene_name": header_name,
                "material_index": index,
                "material_name": name,
                "material_offset": offset,
                "texture_pointer_field": texture_pointer_field,
                "texture_target": texture_target,
                "texture_index": texture_index,
                "format_name": texture["format_name"] if texture else None,
                "width": texture["width"] if texture else None,
                "height": texture["height"] if texture else None,
                "conversion_status": texture["conversion_status"] if texture else "unmapped",
            }
        )

    for texture in textures:
        index = int(texture["index"])
        texture["mapped_material_count"] = len(mapped_names[index])
        texture["mapped_material_names"] = mapped_names[index]

    nodes: list[dict[str, object]] = []
    node_layout = layout["nodes"]
    node_start = node_layout["offset"]
    assert node_start is not None or node_layout["count"] == 0
    for index in range(int(node_layout["count"])):
        offset = int(node_start) + index * 0x60
        primary_target, primary = pointer_name(
            output, offset, system_size, f"scene {scene_index} node {index} primary name"
        )
        secondary_target, secondary = pointer_name(
            output, offset + 4, system_size, f"scene {scene_index} node {index} secondary name"
        )
        add_name(
            name_rows, scene_index, resource, header_name, "node_candidate", index,
            offset, offset, primary_target, primary,
        )
        if secondary is not None and secondary != primary:
            add_name(
                name_rows, scene_index, resource, header_name, "node_secondary", index,
                offset, offset + 4, secondary_target, secondary,
            )
        nodes.append(
            {
                "index": index,
                "record_offset": offset,
                "name": primary,
                "name_target": primary_target,
                "secondary_name": secondary,
                "secondary_name_target": secondary_target,
            }
        )

    shapes: list[dict[str, object]] = []
    submeshes: list[dict[str, object]] = []
    shape_layout = layout["shapes"]
    shape_start = shape_layout["offset"]
    assert shape_start is not None or shape_layout["count"] == 0
    for index in range(int(shape_layout["count"])):
        offset = int(shape_start) + index * 0x100
        name_target, name = pointer_name(
            output, offset + 0x40, system_size,
            f"scene {scene_index} shape {index} +0x40 name/reference",
        )
        add_name(
            name_rows, scene_index, resource, header_name, "shape_candidate", index,
            offset, offset + 0x40, name_target, name,
        )
        version = u32(output, offset + 0x44)
        vertex_count = struct.unpack_from("<H", output, offset + 0x4C)[0]
        morph_count = struct.unpack_from("<H", output, offset + 0x4E)[0]
        transform_count = struct.unpack_from("<H", output, offset + 0x50)[0]
        submesh_count = struct.unpack_from("<H", output, offset + 0x54)[0]
        attribute_descriptors: list[dict[str, object]] = []
        stream_strides = list(struct.unpack_from("<8H", output, offset + 0xC4))
        stream_offsets = [
            resolve_relative(
                output, offset + 0xD4 + stream * 4, system_size,
                f"scene {scene_index} shape {index} vertex stream {stream}",
            )
            for stream in range(8)
        ]
        for register in range(16):
            encoded = u32(output, offset + 0x84 + register * 4)
            if encoded == 0:
                continue
            format_code = encoded & 0xFF
            stream_index = (encoded >> 8) & 0xFF
            byte_offset = encoded >> 16
            if format_code not in VERTEX_FORMATS:
                raise ScneError(
                    f"scene {scene_index} shape {index}: register {register} uses "
                    f"unknown X_D3DVSDT 0x{format_code:02x}"
                )
            format_name, byte_size, components = VERTEX_FORMATS[format_code]
            if format_code != 0x02:
                if stream_index >= 8:
                    raise ScneError(
                        f"scene {scene_index} shape {index}: register {register} "
                        f"uses stream {stream_index}"
                    )
                if stream_strides[stream_index] == 0 or stream_offsets[stream_index] is None:
                    raise ScneError(
                        f"scene {scene_index} shape {index}: register {register} "
                        f"uses unavailable stream {stream_index}"
                    )
                if byte_offset + byte_size > stream_strides[stream_index]:
                    raise ScneError(
                        f"scene {scene_index} shape {index}: register {register} "
                        f"range {byte_offset}+{byte_size} exceeds stream {stream_index} "
                        f"stride {stream_strides[stream_index]}"
                    )
            attribute_descriptors.append(
                {
                    "register": register,
                    "encoded": f"0x{encoded:08x}",
                    "format_code": format_code,
                    "format_name": format_name,
                    "component_count": components,
                    "byte_size": byte_size,
                    "stream_index": stream_index,
                    "byte_offset": byte_offset,
                }
            )
        transform_start = resolve_relative(
            output, offset + 0x64, system_size,
            f"scene {scene_index} shape {index} transform table",
        )
        submesh_start = resolve_relative(
            output, offset + 0x70, system_size,
            f"scene {scene_index} shape {index} submesh table",
        )
        morph_start = resolve_relative(
            output, offset + 0x74, system_size,
            f"scene {scene_index} shape {index} morph/channel table",
        )
        for table_name, count, start, stride in (
            ("transform", transform_count, transform_start, 0x70),
            ("submesh", submesh_count, submesh_start, 0x80),
            ("morph/channel", morph_count, morph_start, 0x0C),
        ):
            if count and start is None:
                raise ScneError(
                    f"scene {scene_index} shape {index}: {table_name} count {count} has null pointer"
                )
            if start is not None and start + count * stride > system_size:
                raise ScneError(
                    f"scene {scene_index} shape {index}: {table_name} table exceeds system buffer"
                )
        active_streams: list[dict[str, object]] = []
        for stream, (stride, stream_start) in enumerate(zip(stream_strides, stream_offsets)):
            if stride == 0 and stream_start is None:
                continue
            if stride == 0 or stream_start is None:
                raise ScneError(
                    f"scene {scene_index} shape {index}: vertex stream {stream} "
                    "has only one of stride/pointer"
                )
            stream_end = stream_start + vertex_count * stride
            if stream_end > system_size:
                raise ScneError(
                    f"scene {scene_index} shape {index}: vertex stream {stream} "
                    "exceeds system buffer"
                )
            active_streams.append(
                {
                    "stream_index": stream,
                    "stride": stride,
                    "offset": stream_start,
                    "end_offset": stream_end,
                    "byte_size": vertex_count * stride,
                }
            )

        if submesh_start is not None:
            for submesh_index in range(submesh_count):
                submesh_offset = submesh_start + submesh_index * 0x80
                material_index, auxiliary_index = struct.unpack_from(
                    "<HH", output, submesh_offset
                )
                if material_index >= int(material_layout["count"]):
                    raise ScneError(
                        f"scene {scene_index} shape {index} submesh {submesh_index}: "
                        f"material index {material_index} >= {material_layout['count']}"
                    )
                command_start = resolve_relative(
                    output, submesh_offset + 0x78, system_size,
                    f"scene {scene_index} shape {index} submesh {submesh_index} commands",
                )
                primary_words, secondary_words = struct.unpack_from(
                    "<HH", output, submesh_offset + 0x7C
                )
                if primary_words and command_start is None:
                    raise ScneError(
                        f"scene {scene_index} shape {index} submesh {submesh_index}: "
                        "nonzero command count with null pointer"
                    )
                push = (
                    parse_push_stream(
                        output, command_start, primary_words, system_size, vertex_count,
                        f"scene {scene_index} shape {index} submesh {submesh_index}",
                    )
                    if command_start is not None
                    else {
                        "command_offset": None,
                        "word_count": primary_words,
                        "command_count": 0,
                        "method_counts": {},
                        "unknown_method_counts": {},
                        "primitive_mode_counts": {},
                        "index_element_count": 0,
                        "draw_array_vertex_count": 0,
                        "maximum_vertex_index": None,
                        "all_vertex_references_in_bounds": True,
                    }
                )
                submeshes.append(
                    {
                        "shape_index": index,
                        "shape_name": name,
                        "submesh_index": submesh_index,
                        "record_offset": submesh_offset,
                        "material_index": material_index,
                        "material_name": materials[material_index]["name"],
                        "auxiliary_index": auxiliary_index,
                        "primary_command_word_count": primary_words,
                        "secondary_command_word_count": secondary_words,
                        **push,
                    }
                )
        shapes.append(
            {
                "index": index,
                "record_offset": offset,
                "name": name,
                "name_target": name_target,
                "version": version,
                "vertex_count": vertex_count,
                "attribute_descriptors": attribute_descriptors,
                "vertex_streams": active_streams,
                "morph_channel_count": morph_count,
                "morph_channel_offset": morph_start,
                "transform_count": transform_count,
                "transform_offset": transform_start,
                "submesh_count": submesh_count,
                "submesh_offset": submesh_start,
            }
        )

    shape_indices_by_name: dict[str, list[int]] = defaultdict(list)
    for shape in shapes:
        if shape["name"] is not None:
            shape_indices_by_name[str(shape["name"])].append(int(shape["index"]))
    for node in nodes:
        lookup_name = node["secondary_name"] or node["name"]
        node["matching_shape_indices"] = shape_indices_by_name.get(str(lookup_name), [])
        node["matching_shape_count"] = len(node["matching_shape_indices"])

    markers: list[dict[str, object]] = []
    marker_layout = layout["markers"]
    marker_start = marker_layout["offset"]
    assert marker_start is not None or marker_layout["count"] == 0
    for index in range(int(marker_layout["count"])):
        offset = int(marker_start) + index * 0x40
        name_target, name = pointer_name(
            output, offset, system_size, f"scene {scene_index} marker {index} name"
        )
        link_target, link_name = pointer_name(
            output, offset + 0x30, system_size, f"scene {scene_index} marker {index} link"
        )
        add_name(
            name_rows, scene_index, resource, header_name, "marker_candidate", index,
            offset, offset, name_target, name,
        )
        if link_name is not None:
            add_name(
                name_rows, scene_index, resource, header_name, "marker_link", index,
                offset, offset + 0x30, link_target, link_name,
            )
        markers.append(
            {
                "index": index,
                "record_offset": offset,
                "name": name,
                "name_target": name_target,
                "link_name": link_name,
                "link_target": link_target,
            }
        )

    sample_rgba: bytes | None = None
    sample_texture_index: int | None = None
    sample_material_name: str | None = None
    if resource.outer_index == 3161 and resource.chunk_index == 6:
        preferred = next((item for item in materials if item["name"] == "flags"), None)
        if preferred is None:
            preferred = next((item for item in materials if item["texture_index"] is not None), None)
        if preferred is not None and preferred["texture_index"] is not None:
            sample_texture_index = int(preferred["texture_index"])
            sample_material_name = str(preferred["name"])
            sample_info = texture_info(
                output,
                int(textures[sample_texture_index]["descriptor_offset"]),
                header_name,
                sample_texture_index,
            )
            sample_chunk = Chunk(
                index=resource.chunk_index, offset=0, kind="TXTR", stored_size=0,
                system_bytes=resource.word_08, video_bytes=resource.word_0c,
                compression_magic=0, overlap_scratch_bytes=0, reserved0=0, reserved1=0,
            )
            try:
                sample_rgba = texture_to_rgba(output, sample_chunk, sample_info)
            except TxtrError:
                sample_rgba = None

    record = {
        "scene_index": scene_index,
        "outer_index": resource.outer_index,
        "outer_id": resource.outer_id,
        "chunk_index": resource.chunk_index,
        "chunk_offset": resource.chunk_offset,
        "stored_size": resource.stored_size,
        "system_bytes": resource.word_08,
        "video_bytes": resource.word_0c,
        "name": header_name,
        "header_name_target": header_name_target,
        "descriptor_offset": descriptor,
        "descriptor_name_target": descriptor_name_target,
        "tables": layout,
        "materials": materials,
        "nodes": nodes,
        "shapes": shapes,
        "submeshes": submeshes,
        "markers": markers,
        "embedded_textures": textures,
        "sample_candidate": (
            {
                "material_name": sample_material_name,
                "texture_index": sample_texture_index,
                "width": textures[sample_texture_index]["width"],
                "height": textures[sample_texture_index]["height"],
                "format_name": textures[sample_texture_index]["format_name"],
            }
            if sample_texture_index is not None
            else None
        ),
    }
    return record, name_rows, mappings, sample_rgba


def write_tsv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="vc_53450030/0 outer archive index")
    parser.add_argument(
        "--resource-scan", type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--scenes-tsv", type=Path, required=True)
    parser.add_argument("--names-tsv", type=Path, required=True)
    parser.add_argument("--mappings-tsv", type=Path, required=True)
    parser.add_argument("--textures-tsv", type=Path, required=True)
    parser.add_argument("--shapes-tsv", type=Path, required=True)
    parser.add_argument("--submeshes-tsv", type=Path, required=True)
    parser.add_argument("--sample-png", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory, resources = parse_inventory(args.resource_scan)
    selected = [record for record in resources if record.kind == "SCNE"]
    declared = int(inventory["summary"]["resource_kind_counts"]["SCNE"])
    if len(selected) != declared:
        raise ScneError(f"inventory selected {len(selected)} SCNE chunks, declares {declared}")
    archive = parse_archive(args.index)

    scenes: list[dict[str, object]] = []
    all_names: list[dict[str, object]] = []
    all_mappings: list[dict[str, object]] = []
    sample_rgba: bytes | None = None
    sample_metadata: dict[str, object] | None = None
    format_counts: Counter[str] = Counter()
    conversion_counts: Counter[str] = Counter()
    table_totals: Counter[str] = Counter()
    conversion_cache: dict[tuple[object, ...], dict[str, str]] = {}

    for scene_index, resource in enumerate(selected):
        entry = archive.entries[resource.outer_index]
        span = read_entry_range(
            archive, entry, resource.chunk_offset, 0x20 + resource.stored_size
        )
        output, decode_detail = decode_resource(span, resource)
        try:
            scene, names, mappings, candidate_rgba = parse_scene(
                scene_index, resource, output, conversion_cache
            )
        except (ScneError, ProbeError, TxtrError, struct.error) as exc:
            raise ScneError(
                f"outer {resource.outer_index} chunk {resource.chunk_index}: {exc}"
            ) from exc
        scene["decoded_sha256"] = decode_detail["decoded_sha256"]
        scenes.append(scene)
        all_names.extend(names)
        all_mappings.extend(mappings)
        for key, table in scene["tables"].items():
            table_totals[key] += int(table["count"])
        for texture in scene["embedded_textures"]:
            format_counts[str(texture["format_name"])] += 1
            conversion_counts[str(texture["conversion_status"])] += 1
        if candidate_rgba is not None:
            if sample_rgba is not None:
                raise ScneError("more than one stadium sample candidate was selected")
            sample_rgba = candidate_rgba
            sample_metadata = {
                "outer_index": resource.outer_index,
                "chunk_index": resource.chunk_index,
                **scene["sample_candidate"],
                "rgba_sha256": hashlib.sha256(candidate_rgba).hexdigest(),
            }
        if (scene_index + 1) % 250 == 0:
            print(
                f"validated {scene_index + 1}/{len(selected)} SCNE chunks",
                file=sys.stderr,
                flush=True,
            )

    if args.sample_png is not None:
        if sample_rgba is None or sample_metadata is None:
            raise ScneError("stadium outer 3161/chunk 6 sample texture was not available")
        write_png(
            args.sample_png,
            int(sample_metadata["width"]),
            int(sample_metadata["height"]),
            sample_rgba,
        )
        sample_metadata["png_sha256"] = hashlib.sha256(args.sample_png.read_bytes()).hexdigest()

    texture_rows: list[dict[str, object]] = []
    shape_rows: list[dict[str, object]] = []
    submesh_rows: list[dict[str, object]] = []
    scene_rows: list[dict[str, object]] = []
    for scene in scenes:
        row: dict[str, object] = {
            key: scene[key]
            for key in (
                "scene_index", "outer_index", "outer_id", "chunk_index", "chunk_offset",
                "stored_size", "system_bytes", "video_bytes", "name", "descriptor_offset",
                "decoded_sha256",
            )
        }
        for spec in TABLE_SPECS:
            row[f"{spec.key}_count"] = scene["tables"][spec.key]["count"]
        scene_rows.append(row)
        for texture in scene["embedded_textures"]:
            texture_rows.append(
                {
                    "scene_index": scene["scene_index"],
                    "outer_index": scene["outer_index"],
                    "chunk_index": scene["chunk_index"],
                    "scene_name": scene["name"],
                    **texture,
                    "mapped_material_names": "|".join(texture["mapped_material_names"]),
                }
            )
        for shape in scene["shapes"]:
            compact_attributes = "|".join(
                f"r{item['register']}:{item['format_name']}:s{item['stream_index']}:o{item['byte_offset']}"
                for item in shape["attribute_descriptors"]
            )
            compact_streams = "|".join(
                f"s{item['stream_index']}:stride{item['stride']}:0x{item['offset']:x}-0x{item['end_offset']:x}"
                for item in shape["vertex_streams"]
            )
            shape_rows.append(
                {
                    "scene_index": scene["scene_index"],
                    "outer_index": scene["outer_index"],
                    "chunk_index": scene["chunk_index"],
                    "scene_name": scene["name"],
                    **shape,
                    "attribute_descriptors": compact_attributes,
                    "vertex_streams": compact_streams,
                }
            )
        for submesh in scene["submeshes"]:
            submesh_rows.append(
                {
                    "scene_index": scene["scene_index"],
                    "outer_index": scene["outer_index"],
                    "chunk_index": scene["chunk_index"],
                    "scene_name": scene["name"],
                    **submesh,
                    "method_counts": json.dumps(
                        submesh["method_counts"], sort_keys=True, separators=(",", ":")
                    ),
                    "unknown_method_counts": json.dumps(
                        submesh["unknown_method_counts"], sort_keys=True, separators=(",", ":")
                    ),
                    "primitive_mode_counts": json.dumps(
                        submesh["primitive_mode_counts"], sort_keys=True, separators=(",", ":")
                    ),
                }
            )

    primitive_mode_counts: Counter[str] = Counter()
    for scene in scenes:
        for submesh in scene["submeshes"]:
            primitive_mode_counts.update(submesh["primitive_mode_counts"])

    summary = {
        "scene_count": len(scenes),
        "all_descriptors_valid": True,
        "all_eight_table_ranges_bounded": True,
        "table_record_totals": dict(sorted(table_totals.items())),
        "name_row_count": len(all_names),
        "material_mapping_count": len(all_mappings),
        "mapped_material_count": sum(item["texture_index"] is not None for item in all_mappings),
        "unmapped_material_count": sum(item["texture_index"] is None for item in all_mappings),
        "embedded_texture_count": sum(format_counts.values()),
        "embedded_texture_format_counts": dict(sorted(format_counts.items())),
        "embedded_texture_conversion_status_counts": dict(sorted(conversion_counts.items())),
        "conversion_failure_count": conversion_counts.get("portme", 0),
        "shape_count": len(shape_rows),
        "submesh_count": len(submesh_rows),
        "all_vertex_stream_ranges_bounded": True,
        "all_push_streams_bounded": True,
        "all_push_vertex_references_in_bounds": all(
            item["all_vertex_references_in_bounds"] for item in submesh_rows
        ),
        "node_shape_name_match_counts": dict(
            sorted(
                Counter(
                    str(node["matching_shape_count"])
                    for scene in scenes
                    for node in scene["nodes"]
                ).items()
            )
        ),
        "vertex_attribute_format_counts": dict(
            sorted(
                Counter(
                    attribute["format_name"]
                    for scene in scenes
                    for shape in scene["shapes"]
                    for attribute in shape["attribute_descriptors"]
                ).items()
            )
        ),
        "vertex_stream_index_counts": dict(
            sorted(
                Counter(
                    str(stream["stream_index"])
                    for scene in scenes
                    for shape in scene["shapes"]
                    for stream in shape["vertex_streams"]
                ).items()
            )
        ),
        "primitive_mode_counts": dict(
            sorted(primitive_mode_counts.items())
        ),
    }
    compact_scenes: list[dict[str, object]] = []
    for scene in scenes:
        compact_scenes.append(
            {
                key: scene[key]
                for key in (
                    "scene_index", "outer_index", "outer_id", "chunk_index",
                    "chunk_offset", "stored_size", "system_bytes", "video_bytes",
                    "name", "header_name_target", "descriptor_offset",
                    "descriptor_name_target", "decoded_sha256", "sample_candidate",
                )
            }
            | {
                "tables": scene["tables"],
                "node_count": len(scene["nodes"]),
                "shape_count": len(scene["shapes"]),
                "submesh_count": len(scene["submeshes"]),
                "material_count": len(scene["materials"]),
                "embedded_texture_count": len(scene["embedded_textures"]),
                "node_shape_match_counts": dict(
                    sorted(Counter(str(item["matching_shape_count"]) for item in scene["nodes"]).items())
                ),
                "attribute_format_counts": dict(
                    sorted(
                        Counter(
                            item["format_name"]
                            for shape in scene["shapes"]
                            for item in shape["attribute_descriptors"]
                        ).items()
                    )
                ),
                "primitive_mode_counts": dict(
                    sorted(
                        sum(
                            (Counter(item["primitive_mode_counts"]) for item in scene["submeshes"]),
                            Counter(),
                        ).items()
                    )
                ),
            }
        )
    report = {
        "schema": SCHEMA,
        "source_index": str(args.index),
        "source_inventory": str(args.resource_scan),
        "executable_evidence": {
            "scne_loader_registration": "default.xbe:0x00045BC0",
            "scene_descriptor_relocator": "default.xbe:0x0002F140",
            "relative_pointer_rule": "target = field_address - 1 + signed_relative",
            "descriptor_size": DESCRIPTOR_SIZE,
            "tables": [asdict(spec) for spec in TABLE_SPECS],
            "xbox_vertex_input_reference": {
                "repository": "tools/vendor/Cxbx-Reloaded",
                "commit": "585c49a50af1255ab155099e06f24505f9c5a800",
                "format_definitions": "src/core/hle/D3D8/XbD3D8Types.h",
                "format_conversion": "src/core/hle/D3D8/XbVertexBuffer.cpp",
                "nv2a_methods": "src/devices/video/nv2a_regs.h",
                "push_parser": "src/devices/video/EmuNV2A_PFIFO.cpp",
            },
        },
        "summary": summary,
        "sample_png": sample_metadata,
        "portme": [
            "PORTME: name the remaining descriptor and record fields from executable consumers.",
            "PORTME: map shader-specific Xbox input registers to NORMAL/TEXCOORD/JOINTS/WEIGHTS and recover transforms, skin weights, and morph semantics for complete glTF export; static FLOAT3 positions and push topology are already exported by nfl_scne_gltf.py.",
            "PORTME: prove material shader parameters and sampler semantics beyond the recovered material-to-texture pointer at record +0x30.",
            "PORTME: prove node parent/child semantics and transforms before reconstructing a scene hierarchy.",
        ],
        "scenes": compact_scenes,
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(
        args.scenes_tsv, scene_rows,
        [
            "scene_index", "outer_index", "outer_id", "chunk_index", "chunk_offset",
            "stored_size", "system_bytes", "video_bytes", "name", "descriptor_offset",
            *[f"{spec.key}_count" for spec in TABLE_SPECS], "decoded_sha256",
        ],
    )
    write_tsv(
        args.names_tsv, all_names,
        [
            "scene_index", "outer_index", "chunk_index", "scene_name", "role",
            "record_index", "record_offset", "pointer_field", "pointer_target", "value",
        ],
    )
    write_tsv(
        args.mappings_tsv, all_mappings,
        [
            "scene_index", "outer_index", "chunk_index", "scene_name", "material_index",
            "material_name", "material_offset", "texture_pointer_field", "texture_target",
            "texture_index", "format_name", "width", "height", "conversion_status",
        ],
    )
    write_tsv(
        args.textures_tsv, texture_rows,
        [
            "scene_index", "outer_index", "chunk_index", "scene_name", "index",
            "descriptor_offset", "unknown0", "pixel_offset", "palette_offset",
            "packed_format", "packed_size", "descriptor_flags", "extra_word_18",
            "extra_word_1c", "dimensions", "format_code", "format_name", "mip_levels",
            "width", "height", "depth", "conversion_status", "rgba_sha256",
            "mapped_material_count", "mapped_material_names", "conversion_error",
        ],
    )
    write_tsv(
        args.shapes_tsv, shape_rows,
        [
            "scene_index", "outer_index", "chunk_index", "scene_name", "index",
            "record_offset", "name", "name_target", "version", "vertex_count",
            "morph_channel_count", "morph_channel_offset", "transform_count",
            "transform_offset", "submesh_count", "submesh_offset",
            "attribute_descriptors", "vertex_streams",
        ],
    )
    write_tsv(
        args.submeshes_tsv, submesh_rows,
        [
            "scene_index", "outer_index", "chunk_index", "scene_name", "shape_index",
            "shape_name", "submesh_index", "record_offset", "material_index",
            "material_name", "auxiliary_index", "command_offset",
            "primary_command_word_count", "secondary_command_word_count", "command_count",
            "method_counts", "unknown_method_counts", "primitive_mode_counts",
            "index_element_count", "draw_array_vertex_count", "maximum_vertex_index",
            "all_vertex_references_in_bounds",
        ],
    )
    print(
        "NFL2K5_SCNE_INVENTORY_COMPLETE "
        f"scenes={summary['scene_count']} textures={summary['embedded_texture_count']} "
        f"materials={summary['material_mapping_count']} "
        f"conversion_failures={summary['conversion_failure_count']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ScneError, ProbeError, TxtrError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
