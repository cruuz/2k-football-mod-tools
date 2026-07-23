#!/usr/bin/env python3
"""Prove NFL 2K5 SCNE bind translations and matrix-palette skin selectors.

This is deliberately a proof/validation tool, not a skeletal glTF exporter.
It joins three independent evidence layers:

* pinned default.xbe functions and the complete 13-program NV2A shader table;
* every serialized 0x70-byte transform and 0x1c-byte CPU blend record; and
* every register-1 SHORT1 selector, including per-submesh palette remaps.

Axes, handedness, units, rest orientation, and current-matrix ownership remain
unassigned.  The tool emits no glTF skin while those contracts are incomplete.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import BinaryIO, Iterable

from nfl_outer import Archive, Entry, parse_archive
from nfl_scene_probe import ResourceRecord, decode_resource, parse_inventory
from nfl_scne_gltf import decode_batches
from nfl_scne_inventory import read_name, resolve_relative


SCHEMA = "nfl2k5_transform_semantics/v1"
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
SHADER_OBJECT_FIRST = 0x00A6C540
SHADER_OBJECT_COUNT = 13
SHADER_OBJECT_STRIDE = 0x20
PALETTE_CONSTANT_BASE_NATIVE = -69
PALETTE_SLOT_LIMIT = 56
REMAP_SENTINEL = 0x7F7F

# Function ends are exclusive and stop immediately after the final RET/JMP.
# The whole XBE MD5 is checked first; these smaller hashes make the evidence
# relevant to each individual semantic claim.
FUNCTION_RANGES = (
    ("render_entry", 0x00021860, 0x000218C3),
    ("blend_two_matrices", 0x00021E40, 0x00021EA2),
    ("blend_three_matrices", 0x00021EB0, 0x00021F37),
    ("upload_full_palette", 0x00022950, 0x00022A5C),
    ("upload_remapped_palette", 0x00022A70, 0x00022BE6),
    ("build_skin_palette", 0x00022C00, 0x00022ECA),
    ("shape_loader", 0x00022F90, 0x0002322D),
    ("parent_record", 0x00023690, 0x000236A3),
    ("name_lookup", 0x000236B0, 0x000236F6),
    ("record_to_index", 0x00023710, 0x0002372B),
    ("local_bind_vector", 0x00023730, 0x00023734),
    ("render_shape", 0x000243D0, 0x00024978),
    ("player_accessory_setup", 0x000DE810, 0x000DE8EB),
    ("player_accessory_lookup", 0x000DE910, 0x000DE976),
    ("player_pose_callback", 0x000901E0, 0x00090247),
    ("player_scene_setup", 0x00090570, 0x000911DE),
    ("player_pose_callback_thunk", 0x00091890, 0x000918AA),
    ("referee_pose_callback", 0x00095B40, 0x00095BA9),
    ("coach_scene_setup", 0x00095D40, 0x00095F7E),
    ("coach_transform_cache", 0x00095FB0, 0x00096007),
    ("coach_pose_callback", 0x00096590, 0x000965F9),
    ("referee_scene_setup", 0x00096600, 0x00096A15),
    ("referee_transform_cache", 0x00096A80, 0x00096ACC),
    ("local_vector_to_quaternion_a", 0x001C2530, 0x001C2865),
    ("local_vector_to_quaternion_b", 0x001C2870, 0x001C2BC2),
    ("sample_and_compose_pose", 0x002176D0, 0x00217793),
    ("quaternion_multiply", 0x003CA150, 0x003CA1DC),
)

PLAYER_NAMES = (
    "root", "lfemur", "ltibia", "lfoot", "ltoes",
    "rfemur", "rtibia", "rfoot", "rtoes", "waist",
    "thorax", "neck", "head", "lcollar", "lhumerus",
    "lelbow", "lwrist", "lhand", "rcollar", "rhumerus",
    "relbow", "rwrist", "rhand", "lshoulderpad", "rshoulderpad",
)
REF_COACH_NAMES = (
    "root", "lfemur", "ltibia", "lfoot", "ltoes",
    "rfemur", "rtibia", "rfoot", "rtoes", "waist",
    "thorax", "neck", "head", "lcollar", "lhumerus",
    "ltwist", "lelbow", "lwrist", "lhand", "rcollar",
    "rhumerus", "rtwist", "relbow", "rwrist", "rhand",
)

SAMPLE_SHAPES = {
    (3, 113, "LO_res"): "player_LO_res",
    (346, 109, "ref_high"): "referee_high",
    (346, 109, "ref_low"): "referee_low",
    (348, 0, "coachBodyGrp1"): "coach_body",
    (348, 0, "coachLodGrp1"): "coach_lod",
}

MAC_PARAMS = {
    0: (), 1: ("a",), 2: ("a", "b"), 3: ("a", "c"),
    4: ("a", "b", "c"), 5: ("a", "b"), 6: ("a", "b"),
    7: ("a", "b"), 8: ("a", "b"), 9: ("a", "b"),
    10: ("a", "b"), 11: ("a", "b"), 12: ("a", "b"), 13: ("a",),
}


class TransformError(ValueError):
    """A pinned executable or bounded SCNE invariant failed."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def float_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def compact_counter(counter: Counter[int | str]) -> dict[str, int]:
    def key(item: int | str) -> tuple[int, object]:
        return (0, item) if isinstance(item, int) else (1, item)
    return {str(value): counter[value] for value in sorted(counter, key=key)}


def xbe_reader(xbe: bytes, header: dict[str, object]):
    def read(va: int, size: int) -> bytes:
        for section in header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                offset = int(section["raw_address"]) + va - start
                return xbe[offset:offset + size]
        raise TransformError(
            f"XBE VA range 0x{va:08x}+0x{size:x} is not raw-backed"
        )
    return read


class PersistentArchiveReader:
    """Read bounded entry ranges while keeping the 36 pack files open."""

    def __init__(self, archive: Archive):
        self.archive = archive
        self.streams: list[BinaryIO] = []

    def __enter__(self) -> "PersistentArchiveReader":
        self.streams = [pack.path.open("rb") for pack in self.archive.packs]
        return self

    def __exit__(self, *_: object) -> None:
        for stream in self.streams:
            stream.close()
        self.streams = []

    def read(self, entry: Entry, relative_offset: int, size: int) -> bytes:
        if relative_offset < 0 or size < 0 or relative_offset + size > entry.size:
            raise TransformError(
                f"entry {entry.table_index}: invalid range "
                f"0x{relative_offset:x}+0x{size:x}"
            )
        relative_end = relative_offset + size
        result = bytearray()
        entry_segment_start = 0
        for segment in entry.segments:
            entry_segment_end = entry_segment_start + segment.size
            part_start = max(relative_offset, entry_segment_start)
            part_end = min(relative_end, entry_segment_end)
            if part_start < part_end:
                stream = self.streams[segment.pack_ordinal]
                stream.seek(segment.pack_offset + part_start - entry_segment_start)
                part = stream.read(part_end - part_start)
                if len(part) != part_end - part_start:
                    raise TransformError(
                        f"entry {entry.table_index}: short pack read"
                    )
                result.extend(part)
            entry_segment_start = entry_segment_end
            if part_end == relative_end:
                break
        if len(result) != size:
            raise TransformError(
                f"entry {entry.table_index}: read {len(result)}/{size} bytes"
            )
        return bytes(result)


def field(words: tuple[int, int, int, int], word: int, start: int, size: int) -> int:
    return (words[word] >> start) & ((1 << size) - 1)


def token_fields(words: tuple[int, int, int, int]) -> dict[str, object]:
    return {
        "mac": field(words, 1, 21, 4),
        "ilu": field(words, 1, 25, 3),
        "constant_raw": field(words, 1, 13, 8),
        "constant_native": field(words, 1, 13, 8) - 96,
        "vertex": field(words, 1, 9, 4),
        "a_mux": field(words, 2, 26, 2),
        "a_register": field(words, 2, 28, 4),
        "a_swizzle": [field(words, 1, shift, 2) for shift in (6, 4, 2, 0)],
        "b_mux": field(words, 2, 11, 2),
        "b_register": field(words, 2, 13, 4),
        "c_mux": field(words, 3, 28, 2),
        "c_register": (field(words, 2, 0, 2) << 2) | field(words, 3, 30, 2),
        "output_mac_mask": field(words, 3, 24, 4),
        "output_register": field(words, 3, 20, 4),
        "relative_a0x": field(words, 3, 1, 1),
        "final": field(words, 3, 0, 1),
    }


def vertex_reads(fields: dict[str, object]) -> list[int]:
    result: list[int] = []
    mac = int(fields["mac"])
    for source in MAC_PARAMS[mac]:
        if int(fields[f"{source}_mux"]) == 2:
            result.append(int(fields["vertex"]))
    if int(fields["ilu"]) != 0 and int(fields["c_mux"]) == 2:
        result.append(int(fields["vertex"]))
    return result


def executable_evidence(
    xbe_path: Path,
    header_path: Path,
    cxbx_vsh_path: Path,
) -> dict[str, object]:
    xbe = xbe_path.read_bytes()
    md5 = hashlib.md5(xbe).hexdigest()
    if md5 != EXPECTED_XBE_MD5:
        raise TransformError(f"unexpected NFL 2K5 XBE MD5 {md5}")
    header = json.loads(header_path.read_text(encoding="utf-8"))
    read = xbe_reader(xbe, header)

    functions = []
    for name, start, end in FUNCTION_RANGES:
        body = read(start, end - start)
        functions.append(
            {
                "name": name,
                "start": f"0x{start:08x}",
                "end_exclusive": f"0x{end:08x}",
                "size": len(body),
                "sha256": sha256(body),
            }
        )

    shader_objects = []
    total_arl = 0
    for shader_index in range(SHADER_OBJECT_COUNT):
        object_va = SHADER_OBJECT_FIRST + shader_index * SHADER_OBJECT_STRIDE
        raw_object = read(object_va, SHADER_OBJECT_STRIDE)
        declaration = struct.unpack_from("<I", raw_object, 8)[0]
        version = struct.unpack_from("<I", raw_object, 12)[0]
        instruction_count = struct.unpack_from("<I", raw_object, 0x14)[0]
        program_va = struct.unpack_from("<I", raw_object, 0x1C)[0]
        if not 1 <= instruction_count <= 256:
            raise TransformError(
                f"shader {shader_index}: implausible instruction count {instruction_count}"
            )
        raw_program = read(program_va, instruction_count * 16)
        decoded = []
        register_reads: Counter[int] = Counter()
        arl_indices: list[int] = []
        position_mad_indices: list[int] = []
        position_rows: dict[int, int] = {}
        normal_rows: dict[int, int] = {}
        for instruction_index in range(instruction_count):
            words = struct.unpack_from("<4I", raw_program, instruction_index * 16)
            item = token_fields(words)
            item["index"] = instruction_index
            item["words"] = [f"0x{word:08x}" for word in words]
            reads = vertex_reads(item)
            register_reads.update(reads)
            item["vertex_reads"] = reads
            decoded.append(item)

            if (
                item["mac"] == 13 and item["a_mux"] == 2
                and item["vertex"] == 1 and item["a_swizzle"] == [0, 0, 0, 0]
            ):
                arl_indices.append(instruction_index)
            if (
                item["mac"] == 4 and item["a_mux"] == 2
                and item["vertex"] == 0 and item["b_mux"] == 3
                and item["c_mux"] == 3 and item["constant_native"] == -88
                and item["output_register"] == 4
                and item["output_mac_mask"] == 14
                and item["relative_a0x"] == 0
            ):
                position_mad_indices.append(instruction_index)
            if (
                item["mac"] == 6 and item["a_mux"] == 1
                and item["a_register"] == 4 and item["b_mux"] == 3
                and item["relative_a0x"] == 1
                and item["output_register"] == 0
                and item["constant_native"] in (-69, -68, -67)
            ):
                position_rows[int(item["constant_native"])] = instruction_index
            if (
                item["mac"] == 5 and item["a_mux"] == 2
                and item["vertex"] == 2 and item["b_mux"] == 3
                and item["relative_a0x"] == 1
                and item["constant_native"] in (-69, -68, -67)
            ):
                normal_rows[int(item["constant_native"])] = instruction_index

        if len(arl_indices) != 1:
            raise TransformError(
                f"shader {shader_index}: expected one ARL a0.x,v1.x, got {arl_indices}"
            )
        if len(position_mad_indices) != 1:
            raise TransformError(
                f"shader {shader_index}: position decode MAD count differs"
            )
        if set(position_rows) != {-69, -68, -67}:
            raise TransformError(
                f"shader {shader_index}: incomplete palette DPH rows {position_rows}"
            )
        if register_reads[1] != 1:
            raise TransformError(
                f"shader {shader_index}: v1 is read {register_reads[1]} times"
            )
        total_arl += len(arl_indices)
        shader_objects.append(
            {
                "index": shader_index,
                "object_va": f"0x{object_va:08x}",
                "object_sha256": sha256(raw_object),
                "declaration": f"0x{declaration:08x}",
                "version": f"0x{version:08x}",
                "instruction_count": instruction_count,
                "program_va": f"0x{program_va:08x}",
                "program_sha256": sha256(raw_program),
                "vertex_register_read_counts": compact_counter(register_reads),
                "arl_a0x_v1x_instruction": arl_indices[0],
                "position_decode_mad_instruction": position_mad_indices[0],
                "position_palette_dph_instructions": {
                    str(value): position_rows[value] for value in sorted(position_rows)
                },
                "normal_palette_dp3_instructions": {
                    str(value): normal_rows[value] for value in sorted(normal_rows)
                },
                "tokens": decoded,
            }
        )

    return {
        "path": str(xbe_path),
        "md5": md5,
        "sha256": sha256(xbe),
        "header_path": str(header_path),
        "function_ranges": functions,
        "shader_object_table_va": f"0x{SHADER_OBJECT_FIRST:08x}",
        "shader_object_count": len(shader_objects),
        "shader_arl_a0x_v1x_count": total_arl,
        "shader_objects": shader_objects,
        "cxbx_nv2a_vsh_path": str(cxbx_vsh_path),
        "cxbx_nv2a_vsh_sha256": sha256_file(cxbx_vsh_path),
    }


def pointer_name(data: bytes, field_offset: int, limit: int, label: str) -> str:
    target = resolve_relative(data, field_offset, limit, label)
    value = read_name(data, target, limit, label)
    if value is None:
        raise TransformError(f"{label}: null name")
    return value


def influence_arity(global_palette_index: int, base_count: int, blend_types: list[int]) -> int:
    if global_palette_index < base_count:
        return 1
    blend_index = global_palette_index - base_count
    if not 0 <= blend_index < len(blend_types):
        raise TransformError(
            f"palette index {global_palette_index} exceeds {base_count}+{len(blend_types)}"
        )
    return blend_types[blend_index]


def write_transform_tsv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    rows = list(rows)
    fields = [
        "sample", "outer_index", "chunk_index", "scene_name", "shape_name",
        "transform_index", "transform_name", "parent_index",
        "absolute_x", "absolute_y", "absolute_z", "absolute_w",
        "local_x", "local_y", "local_z", "local_w",
        "expected_local_x", "expected_local_y", "expected_local_z",
        "maximum_delta_error",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def write_influence_tsv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    rows = list(rows)
    fields = [
        "sample", "outer_index", "chunk_index", "scene_name", "shape_name",
        "vertex_index", "selector_short1", "local_palette_slot",
        "global_palette_index", "influence_count",
        "joint0_index", "joint0_name", "weight0",
        "joint1_index", "joint1_name", "weight1",
        "joint2_index", "joint2_name", "weight2",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def corpus_evidence(
    index_path: Path,
    scan_path: Path,
    progress_every: int,
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    archive = parse_archive(index_path)
    inventory, all_resources = parse_inventory(scan_path)
    resources = [record for record in all_resources if record.kind == "SCNE"]
    declared = int(inventory["summary"]["resource_kind_counts"]["SCNE"])
    if len(resources) != declared:
        raise TransformError(f"SCNE inventory has {len(resources)}/{declared} records")

    stats: Counter[str] = Counter()
    base_count_distribution: Counter[int] = Counter()
    blend_count_distribution: Counter[int] = Counter()
    blend_type_distribution: Counter[int] = Counter()
    version_distribution: Counter[int] = Counter()
    selector_value_distribution: Counter[int] = Counter()
    influence_arity_distribution: Counter[int] = Counter()
    active_weight_sum_error_max = 0.0
    local_delta_error_max = 0.0
    selector_min: int | None = None
    selector_max: int | None = None
    sample_rows: list[dict[str, object]] = []
    sample_influence_rows: list[dict[str, object]] = []
    sample_shapes: list[dict[str, object]] = []
    conflict_samples: list[dict[str, object]] = []
    unresolved_samples: list[dict[str, object]] = []
    ignored_blend_tail = hashlib.sha256()

    with PersistentArchiveReader(archive) as source:
        for scene_index, resource in enumerate(resources):
            entry = archive.entries[resource.outer_index]
            span = source.read(
                entry, resource.chunk_offset, 0x20 + resource.stored_size
            )
            output, _ = decode_resource(span, resource)
            system_size = resource.word_08
            if len(output) != resource.word_08 + resource.word_0c:
                raise TransformError(f"scene {scene_index}: decoded size differs")
            if output[0x0C:0x10] != b"SCNE":
                raise TransformError(f"scene {scene_index}: missing SCNE marker")
            scene_name = pointer_name(
                output, 0x10, system_size, f"scene {scene_index} name"
            )
            descriptor = resolve_relative(
                output, 0x14, system_size, f"scene {scene_index} descriptor"
            )
            if descriptor is None or descriptor + 0x54 > system_size:
                raise TransformError(f"scene {scene_index}: missing descriptor")
            shape_count = struct.unpack_from("<I", output, descriptor + 0x2C)[0]
            shape_start = resolve_relative(
                output, descriptor + 0x30, system_size,
                f"scene {scene_index} shape table",
            )
            if shape_count and shape_start is None:
                raise TransformError(f"scene {scene_index}: null shape table")
            if shape_start is not None and shape_start + shape_count * 0x100 > system_size:
                raise TransformError(f"scene {scene_index}: shape table exceeds system part")
            stats["scene_count"] += 1
            stats["shape_count"] += shape_count

            for shape_index in range(shape_count):
                assert shape_start is not None
                shape = shape_start + shape_index * 0x100
                shape_name = pointer_name(
                    output, shape + 0x40, system_size,
                    f"scene {scene_index} shape {shape_index} name",
                )
                version = struct.unpack_from("<I", output, shape + 0x44)[0]
                vertex_count = struct.unpack_from("<H", output, shape + 0x4C)[0]
                base_count, blend_count, submesh_count = struct.unpack_from(
                    "<HHH", output, shape + 0x50
                )
                version_distribution[version] += 1
                base_count_distribution[base_count] += 1
                blend_count_distribution[blend_count] += 1
                stats["vertex_count"] += vertex_count
                stats["base_transform_count"] += base_count
                stats["cpu_blend_record_count"] += blend_count
                stats["shape_with_cpu_blends_count"] += int(blend_count != 0)

                transform_start = resolve_relative(
                    output, shape + 0x64, system_size,
                    f"scene {scene_index} shape {shape_index} transform table",
                )
                blend_start = resolve_relative(
                    output, shape + 0x60, system_size,
                    f"scene {scene_index} shape {shape_index} blend table",
                )
                submesh_start = resolve_relative(
                    output, shape + 0x70, system_size,
                    f"scene {scene_index} shape {shape_index} submesh table",
                )
                for label, count, start, stride in (
                    ("transform", base_count, transform_start, 0x70),
                    ("blend", blend_count, blend_start, 0x1C),
                    ("submesh", submesh_count, submesh_start, 0x80),
                ):
                    if count and start is None:
                        raise TransformError(
                            f"scene {scene_index} shape {shape_index}: null {label} table"
                        )
                    if start is not None and start + count * stride > system_size:
                        raise TransformError(
                            f"scene {scene_index} shape {shape_index}: {label} table exceeds system part"
                        )

                transform_names: list[str] = []
                transform_values: list[tuple[tuple[float, ...], tuple[float, ...], int]] = []
                root_count = 0
                for transform_index in range(base_count):
                    assert transform_start is not None
                    record = transform_start + transform_index * 0x70
                    prefix = output[record:record + 0x40]
                    stats["serialized_runtime_matrix_prefix_zero_count"] += int(
                        prefix == bytes(0x40)
                    )
                    stats["serialized_runtime_matrix_prefix_nonzero_count"] += int(
                        prefix != bytes(0x40)
                    )
                    absolute = struct.unpack_from("<4f", output, record + 0x40)
                    local = struct.unpack_from("<4f", output, record + 0x50)
                    if not all(math.isfinite(value) for value in absolute + local):
                        raise TransformError(
                            f"scene {scene_index} shape {shape_index} transform {transform_index}: non-finite vector"
                        )
                    if absolute[3] != 1.0 or local[3] != 1.0:
                        raise TransformError(
                            f"scene {scene_index} shape {shape_index} transform {transform_index}: non-homogeneous w"
                        )
                    parent = struct.unpack_from("<i", output, record + 0x64)[0]
                    if parent == -1:
                        root_count += 1
                        parent_absolute = (0.0, 0.0, 0.0)
                    elif not 0 <= parent < transform_index:
                        raise TransformError(
                            f"scene {scene_index} shape {shape_index} transform {transform_index}: invalid parent {parent}"
                        )
                    else:
                        parent_absolute = transform_values[parent][0][:3]
                    expected_local = tuple(
                        f32(absolute[axis] - parent_absolute[axis])
                        for axis in range(3)
                    )
                    errors = tuple(
                        abs(local[axis] - expected_local[axis]) for axis in range(3)
                    )
                    maximum_error = max(errors)
                    local_delta_error_max = max(local_delta_error_max, maximum_error)
                    if maximum_error > 0.00004:
                        raise TransformError(
                            f"scene {scene_index} shape {shape_index} transform {transform_index}: "
                            f"local delta error {maximum_error}"
                        )
                    exact_components = sum(
                        float_bits(local[axis]) == float_bits(expected_local[axis])
                        for axis in range(3)
                    )
                    stats["local_delta_component_count"] += 3
                    stats["local_delta_bit_exact_component_count"] += exact_components
                    stats["local_delta_tolerance_component_count"] += 3 - exact_components
                    transform_name = pointer_name(
                        output, record + 0x60, system_size,
                        f"scene {scene_index} shape {shape_index} transform {transform_index} name",
                    )
                    transform_names.append(transform_name)
                    transform_values.append((absolute, local, parent))

                    sample = SAMPLE_SHAPES.get(
                        (resource.outer_index, resource.chunk_index, shape_name)
                    )
                    if sample is not None:
                        sample_rows.append(
                            {
                                "sample": sample,
                                "outer_index": resource.outer_index,
                                "chunk_index": resource.chunk_index,
                                "scene_name": scene_name,
                                "shape_name": shape_name,
                                "transform_index": transform_index,
                                "transform_name": transform_name,
                                "parent_index": parent,
                                "absolute_x": absolute[0],
                                "absolute_y": absolute[1],
                                "absolute_z": absolute[2],
                                "absolute_w": absolute[3],
                                "local_x": local[0],
                                "local_y": local[1],
                                "local_z": local[2],
                                "local_w": local[3],
                                "expected_local_x": expected_local[0],
                                "expected_local_y": expected_local[1],
                                "expected_local_z": expected_local[2],
                                "maximum_delta_error": maximum_error,
                            }
                        )
                if root_count != 1:
                    raise TransformError(
                        f"scene {scene_index} shape {shape_index}: {root_count} transform roots"
                    )
                stats["root_transform_count"] += root_count
                stats["nonroot_transform_count"] += base_count - root_count

                consumer_family: str | None = None
                if scene_name == "lo_body" and shape_name == "LO_res":
                    consumer_family = "player"
                    if tuple(transform_names) != PLAYER_NAMES:
                        raise TransformError("player LO_res transform order differs")
                elif scene_name == "referee" and shape_name in ("ref_high", "ref_low"):
                    consumer_family = "referee"
                    if tuple(transform_names) != REF_COACH_NAMES:
                        raise TransformError("referee transform order differs")
                elif scene_name == "coach" and shape_name in ("coachBodyGrp1", "coachLodGrp1"):
                    consumer_family = "coach"
                    if tuple(transform_names) != REF_COACH_NAMES:
                        raise TransformError("coach transform order differs")
                if consumer_family is not None:
                    stats[f"{consumer_family}_transform_copy_count"] += 1

                blend_types: list[int] = []
                blend_records: list[list[tuple[int, float]]] = []
                active_weight_max_here = 0.0
                for blend_index in range(blend_count):
                    assert blend_start is not None
                    record = blend_start + blend_index * 0x1C
                    blend_type = struct.unpack_from("<I", output, record)[0]
                    if blend_type not in (2, 3):
                        raise TransformError(
                            f"scene {scene_index} shape {shape_index} blend {blend_index}: type {blend_type}"
                        )
                    blend_type_distribution[blend_type] += 1
                    blend_types.append(blend_type)
                    active_weights = []
                    active_indices = []
                    for source_index in range(blend_type):
                        base_index, weight = struct.unpack_from(
                            "<If", output, record + 4 + source_index * 8
                        )
                        if base_index >= base_count:
                            raise TransformError(
                                f"scene {scene_index} shape {shape_index} blend {blend_index}: base index {base_index}"
                            )
                        if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
                            raise TransformError(
                                f"scene {scene_index} shape {shape_index} blend {blend_index}: weight {weight}"
                            )
                        active_indices.append(base_index)
                        active_weights.append(weight)
                    if len(set(active_indices)) != blend_type:
                        raise TransformError(
                            f"scene {scene_index} shape {shape_index} blend {blend_index}: duplicate base index"
                        )
                    sum_error = abs(sum(active_weights) - 1.0)
                    active_weight_sum_error_max = max(
                        active_weight_sum_error_max, sum_error
                    )
                    active_weight_max_here = max(active_weight_max_here, sum_error)
                    if sum_error > 0.000001:
                        raise TransformError(
                            f"scene {scene_index} shape {shape_index} blend {blend_index}: weights sum error {sum_error}"
                        )
                    blend_records.append(list(zip(active_indices, active_weights)))
                    if blend_type == 2:
                        ignored_blend_tail.update(output[record + 0x14:record + 0x1C])
                        stats["ignored_two_source_tail_nonzero_count"] += int(
                            output[record + 0x14:record + 0x1C] != bytes(8)
                        )

                encoded_r1 = struct.unpack_from("<I", output, shape + 0x88)[0]
                format_code = encoded_r1 & 0xFF
                stream_index = (encoded_r1 >> 8) & 0xFF
                byte_offset = encoded_r1 >> 16
                if format_code != 0x15 or stream_index >= 8:
                    raise TransformError(
                        f"scene {scene_index} shape {shape_index}: r1 is 0x{encoded_r1:08x}, not SHORT1"
                    )
                stride = struct.unpack_from(
                    "<H", output, shape + 0xC4 + stream_index * 2
                )[0]
                stream_start = resolve_relative(
                    output, shape + 0xD4 + stream_index * 4, system_size,
                    f"scene {scene_index} shape {shape_index} r1 stream",
                )
                if stream_start is None or stride == 0 or byte_offset + 2 > stride:
                    raise TransformError(
                        f"scene {scene_index} shape {shape_index}: invalid r1 stream"
                    )
                if stream_start + vertex_count * stride > system_size:
                    raise TransformError(
                        f"scene {scene_index} shape {shape_index}: r1 stream exceeds system part"
                    )
                selectors = [
                    struct.unpack_from(
                        "<h", output, stream_start + vertex * stride + byte_offset
                    )[0]
                    for vertex in range(vertex_count)
                ]
                if any(value < 0 or value % 3 for value in selectors):
                    raise TransformError(
                        f"scene {scene_index} shape {shape_index}: r1 is not a nonnegative 3-row offset"
                    )
                stats["short1_selector_shape_count"] += 1
                stats["selector_vertex_count"] += len(selectors)
                selector_value_distribution.update(selectors)
                if selectors:
                    selector_min = min(selectors) if selector_min is None else min(selector_min, min(selectors))
                    selector_max = max(selectors) if selector_max is None else max(selector_max, max(selectors))
                palette_count = base_count + blend_count
                if palette_count == 0:
                    raise TransformError(
                        f"scene {scene_index} shape {shape_index}: empty palette"
                    )

                resolved_by_vertex: dict[int, int] = {}
                if palette_count < PALETTE_SLOT_LIMIT:
                    stats["full_palette_shape_count"] += 1
                    for vertex, selector in enumerate(selectors):
                        global_index = selector // 3
                        if global_index >= palette_count:
                            raise TransformError(
                                f"scene {scene_index} shape {shape_index} vertex {vertex}: selector {selector} >= palette {palette_count}"
                            )
                        resolved_by_vertex[vertex] = global_index
                else:
                    stats["remapped_palette_shape_count"] += 1
                    if any(selector // 3 >= PALETTE_SLOT_LIMIT for selector in selectors):
                        raise TransformError(
                            f"scene {scene_index} shape {shape_index}: remapped selector exceeds 55"
                        )
                    assert submesh_start is not None or submesh_count == 0
                    for submesh_index in range(submesh_count):
                        assert submesh_start is not None
                        submesh = submesh_start + submesh_index * 0x80
                        first_slot, last_slot = struct.unpack_from(
                            "<HH", output, submesh + 4
                        )
                        if first_slot > last_slot or last_slot >= PALETTE_SLOT_LIMIT:
                            raise TransformError(
                                f"scene {scene_index} shape {shape_index} submesh {submesh_index}: remap range {first_slot}..{last_slot}"
                            )
                        mappings = struct.unpack_from(
                            f"<{PALETTE_SLOT_LIMIT}H", output, submesh + 8
                        )
                        command_start = resolve_relative(
                            output, submesh + 0x78, system_size,
                            f"scene {scene_index} shape {shape_index} submesh {submesh_index} commands",
                        )
                        primary_words = struct.unpack_from("<H", output, submesh + 0x7C)[0]
                        if primary_words and command_start is None:
                            raise TransformError(
                                f"scene {scene_index} shape {shape_index} submesh {submesh_index}: null commands"
                            )
                        batches = (
                            decode_batches(output, command_start, primary_words)
                            if command_start is not None else []
                        )
                        referenced = {
                            vertex for _, indices in batches for vertex in indices
                        }
                        stats["remapped_submesh_count"] += 1
                        stats["remapped_submesh_unique_vertex_reference_count"] += len(referenced)
                        for vertex in referenced:
                            if vertex >= vertex_count:
                                raise TransformError(
                                    f"scene {scene_index} shape {shape_index} submesh {submesh_index}: vertex {vertex}"
                                )
                            slot = selectors[vertex] // 3
                            global_index = mappings[slot]
                            if not first_slot <= slot <= last_slot:
                                raise TransformError(
                                    f"scene {scene_index} shape {shape_index} submesh {submesh_index}: slot {slot} outside {first_slot}..{last_slot}"
                                )
                            if global_index == REMAP_SENTINEL or global_index >= palette_count:
                                raise TransformError(
                                    f"scene {scene_index} shape {shape_index} submesh {submesh_index}: slot {slot} maps to {global_index}"
                                )
                            previous = resolved_by_vertex.get(vertex)
                            if previous is not None and previous != global_index:
                                stats["cross_submesh_mapping_conflict_count"] += 1
                                if len(conflict_samples) < 16:
                                    conflict_samples.append(
                                        {
                                            "outer_index": resource.outer_index,
                                            "chunk_index": resource.chunk_index,
                                            "shape_index": shape_index,
                                            "shape_name": shape_name,
                                            "vertex": vertex,
                                            "first_global_palette_index": previous,
                                            "second_global_palette_index": global_index,
                                        }
                                    )
                            else:
                                resolved_by_vertex[vertex] = global_index
                    unresolved = vertex_count - len(resolved_by_vertex)
                    stats["remapped_unreferenced_vertex_count"] += unresolved
                    if unresolved and len(unresolved_samples) < 16:
                        unresolved_samples.append(
                            {
                                "outer_index": resource.outer_index,
                                "chunk_index": resource.chunk_index,
                                "shape_index": shape_index,
                                "shape_name": shape_name,
                                "vertex_count": vertex_count,
                                "resolved_vertex_count": len(resolved_by_vertex),
                                "unreferenced_vertex_count": unresolved,
                            }
                        )

                stats["resolved_selector_vertex_count"] += len(resolved_by_vertex)
                for global_index in resolved_by_vertex.values():
                    arity = influence_arity(global_index, base_count, blend_types)
                    influence_arity_distribution[arity] += 1

                sample = SAMPLE_SHAPES.get(
                    (resource.outer_index, resource.chunk_index, shape_name)
                )
                if sample is not None:
                    for vertex, global_index in sorted(resolved_by_vertex.items()):
                        if global_index < base_count:
                            influences = [(global_index, 1.0)]
                        else:
                            influences = blend_records[global_index - base_count]
                        row: dict[str, object] = {
                            "sample": sample,
                            "outer_index": resource.outer_index,
                            "chunk_index": resource.chunk_index,
                            "scene_name": scene_name,
                            "shape_name": shape_name,
                            "vertex_index": vertex,
                            "selector_short1": selectors[vertex],
                            "local_palette_slot": selectors[vertex] // 3,
                            "global_palette_index": global_index,
                            "influence_count": len(influences),
                        }
                        for influence_index in range(3):
                            if influence_index < len(influences):
                                joint, weight = influences[influence_index]
                                row[f"joint{influence_index}_index"] = joint
                                row[f"joint{influence_index}_name"] = transform_names[joint]
                                row[f"weight{influence_index}"] = weight
                            else:
                                row[f"joint{influence_index}_index"] = ""
                                row[f"joint{influence_index}_name"] = ""
                                row[f"weight{influence_index}"] = ""
                        sample_influence_rows.append(row)
                    sample_shapes.append(
                        {
                            "sample": sample,
                            "outer_index": resource.outer_index,
                            "chunk_index": resource.chunk_index,
                            "scene_name": scene_name,
                            "shape_index": shape_index,
                            "shape_name": shape_name,
                            "vertex_count": vertex_count,
                            "base_transform_count": base_count,
                            "cpu_blend_record_count": blend_count,
                            "palette_count": palette_count,
                            "palette_upload_mode": (
                                "full" if palette_count < PALETTE_SLOT_LIMIT else "per_submesh_remap"
                            ),
                            "selector_min": min(selectors) if selectors else None,
                            "selector_max": max(selectors) if selectors else None,
                            "selector_unique_count": len(set(selectors)),
                            "resolved_vertex_count": len(resolved_by_vertex),
                            "active_weight_sum_error_max": active_weight_max_here,
                        }
                    )

            if progress_every and (scene_index + 1) % progress_every == 0:
                print(
                    f"validated {scene_index + 1}/{len(resources)} SCNE transform/palette records",
                    file=sys.stderr,
                    flush=True,
                )

    if stats["cross_submesh_mapping_conflict_count"]:
        raise TransformError(
            f"found {stats['cross_submesh_mapping_conflict_count']} cross-submesh palette conflicts"
        )
    if len(sample_shapes) != len(SAMPLE_SHAPES):
        raise TransformError(f"found {len(sample_shapes)}/{len(SAMPLE_SHAPES)} sample shapes")

    for key in (
        "cross_submesh_mapping_conflict_count",
        "remapped_unreferenced_vertex_count",
    ):
        stats.setdefault(key, 0)
    result = {
        "source_index": str(index_path),
        "source_index_sha256": sha256_file(index_path),
        "resource_scan": str(scan_path),
        "resource_scan_sha256": sha256_file(scan_path),
        "counts": {key: stats[key] for key in sorted(stats)},
        "shape_version_counts": compact_counter(version_distribution),
        "base_transform_count_distribution": compact_counter(base_count_distribution),
        "cpu_blend_count_distribution": compact_counter(blend_count_distribution),
        "cpu_blend_type_counts": compact_counter(blend_type_distribution),
        "active_weight_sum_error_max": active_weight_sum_error_max,
        "ignored_two_source_tail_sha256": ignored_blend_tail.hexdigest(),
        "local_parent_delta_error_max": local_delta_error_max,
        "selector_min": selector_min,
        "selector_max": selector_max,
        "selector_unique_value_count": len(selector_value_distribution),
        "selector_value_counts": compact_counter(selector_value_distribution),
        "resolved_influence_arity_counts": compact_counter(influence_arity_distribution),
        "cross_submesh_mapping_conflict_samples": conflict_samples,
        "remapped_unreferenced_vertex_samples": unresolved_samples,
        "sample_shapes": sorted(sample_shapes, key=lambda item: str(item["sample"])),
    }
    return (
        result,
        sorted(
            sample_rows,
            key=lambda item: (str(item["sample"]), int(item["transform_index"])),
        ),
        sorted(
            sample_influence_rows,
            key=lambda item: (str(item["sample"]), int(item["vertex_index"])),
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to vc_53450030/0")
    parser.add_argument(
        "--resource-scan", type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    parser.add_argument(
        "--xbe", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"),
    )
    parser.add_argument(
        "--xbe-header", type=Path,
        default=Path("reports/headers/nfl2k5_xbe_header.json"),
    )
    parser.add_argument(
        "--cxbx-vsh", type=Path,
        default=Path("tools/vendor/Cxbx-Reloaded/src/devices/video/nv2a_vsh.cpp"),
    )
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--samples-tsv", type=Path, required=True)
    parser.add_argument("--influences-tsv", type=Path, required=True)
    parser.add_argument("--progress-every", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    executable = executable_evidence(args.xbe, args.xbe_header, args.cxbx_vsh)
    corpus, sample_rows, sample_influence_rows = corpus_evidence(
        args.index, args.resource_scan, args.progress_every
    )
    report = {
        "schema": SCHEMA,
        "executable": executable,
        "proved_contract": {
            "transform_record_stride": 0x70,
            "absolute_bind_translation_offset": "0x40",
            "parent_local_bind_translation_offset": "0x50",
            "name_pointer_offset": "0x60",
            "parent_index_offset": "0x64",
            "loader_runtime_prefix_offset": "0x00",
            "loader_runtime_prefix_size": "0x40",
            "loader_runtime_prefix_equation": "identity 4x4 with translation (-absolute.x,-absolute.y,-absolute.z)",
            "base_skin_palette_equation": "current_transform_4x4 * T(-absolute_bind_translation), stored as 3x4 rows",
            "current_transform_space": "PORTME: caller supplies one 4x4 per base transform; exact model/world ownership is not proved",
            "cpu_blend_record_stride": "0x1c",
            "cpu_blend_record_equation": "elementwise weighted sum of 2 or 3 base 3x4 skin matrices",
            "two_source_trailing_pair": "ignored by 0x00022c00 and intentionally preserved as opaque bytes",
            "vertex_selector_register": 1,
            "vertex_selector_format": "SHORT1",
            "vertex_selector_equation": "local_matrix_slot = v1.x / 3",
            "shader_palette_rows": ["c[a0.x-69]", "c[a0.x-68]", "c[a0.x-67]"],
            "full_palette_condition": "base_count + cpu_blend_count < 56",
            "remap_first_slot_offset": "submesh +0x04 u16",
            "remap_last_slot_offset": "submesh +0x06 u16 inclusive",
            "remap_table_offset": "submesh +0x08, 56 u16 global palette indices",
            "remap_sentinel": "0x7f7f",
            "global_palette_contract": "indices below base_count select one transform; later indices select a CPU blend record",
        },
        "corpus": corpus,
        "portme": [
            "PORTME: prove whether the caller matrices consumed at 0x00022c00 are model-space or world-space in every render path.",
            "PORTME: recover rest-joint orientation construction from the +0x50 vector consumers at 0x001c2530 and 0x001c2870.",
            "PORTME: prove coordinate axes, handedness, units, root motion, and quaternion convention.",
            "PORTME: do not emit skeletal glTF until node ownership, rest rotations, inverse-bind convention, and animation composition are all proved.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_transform_tsv(args.samples_tsv, sample_rows)
    write_influence_tsv(args.influences_tsv, sample_influence_rows)
    print(
        "NFL_TRANSFORM_SEMANTICS_COMPLETE "
        f"scenes={corpus['counts']['scene_count']} "
        f"shapes={corpus['counts']['shape_count']} "
        f"transforms={corpus['counts']['base_transform_count']} "
        f"blends={corpus['counts']['cpu_blend_record_count']} "
        f"selectors={corpus['counts']['resolved_selector_vertex_count']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, TransformError, struct.error, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
