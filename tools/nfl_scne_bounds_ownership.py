#!/usr/bin/env python3
"""Prove NFL 2K5 SCNE serialized bounding-sphere ownership.

This is a read-only evidence tool.  It joins the exact retail XBE consumers
with every decoded SCNE shape, then closes the narrower ``upper_deck`` source-
subset question: because every admitted output vertex is copied from a source
record already contained by the preserved sphere, the 4/8-record writer does
not need to author a new bound.  External positions and a general bounds
writer remain excluded.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import BinaryIO

from nfl_outer import Archive, Entry, parse_archive
from nfl_scene_probe import decode_resource, parse_inventory
from nfl_scne_inventory import resolve_relative


SCHEMA = "nfl2k5_scne_bounds_ownership/v1"
ROOT = Path(__file__).resolve().parents[1]
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
EXPECTED_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
EXPECTED_INDEX_SIZE = 193_710_080
EXPECTED_INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
EXPECTED_SCAN_SIZE = 55_746_414
EXPECTED_SCAN_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"

TARGET_OUTER = 3280
TARGET_CHUNK = 5
TARGET_SHAPE = 1
TARGET_NAME = "upper_deck"
TARGET_DECODED_SHA256 = "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8"
TARGET_VERTEX_COUNT = 12
TARGET_POSITION_OFFSET = 69_920
TARGET_POSITION_SIZE = 144
TARGET_POSITION_SHA256 = "95164ce59e125ac1775003846a1eb780c63f001c65f2b3da8d2aebd20fbe67f7"

# Ends are exclusive and include each function's final return.
FUNCTION_RANGES = (
    ("transform_bound_center", 0x00021520, 0x00021591),
    ("node_sphere_visibility_dispatch", 0x000215A0, 0x00021627),
    ("node_relocator", 0x00021630, 0x000216F6),
    ("render_node", 0x00021860, 0x000218C3),
    ("shape_relocator", 0x00022F90, 0x0002322D),
    ("shape_center_getter", 0x00023750, 0x00023753),
    ("shape_radius_getter", 0x00023760, 0x00023764),
    ("frustum_sphere_test", 0x0002ADC0, 0x0002AEA1),
)

AUTHORITIES = (
    (
        "changed_count_boundary",
        "reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json",
        25_285,
        "54e6d20dcf9c525a5248d94b4f45516425f0e69702df31dfd93fc351efd43eab",
    ),
    (
        "source_subset_recipe_schema",
        "reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json",
        2_209,
        "4fac01c6cffe03481b456899ec2b2f3cd25f74954d5db94ccb3b8351f841ca4b",
    ),
    (
        "source_subset_writeback_closure",
        "reports/specs/nfl2k5_upper_deck_source_subset_writeback_closure.v1.json",
        13_933,
        "38a4b176fb39cab86b134d3b1c6d03043513771229cdf1e444ef6baa01912fba",
    ),
    (
        "source_triangle_mesh_schema",
        "reports/specs/nfl2k5_upper_deck_source_triangle_mesh.schema.json",
        1_571,
        "ac2822d22a01e66e004d9e65510c5ed100a1b58d1bdba11e55373a932a8c2dff",
    ),
    (
        "source_subset_writer",
        "tools/nfl_stadium_upper_deck_subset_patch.py",
        49_632,
        "0b20b0d365fa2bb99745b305a52c0372c1db2214d8986b1e409fb2aa09a2ea10",
    ),
    (
        "source_subset_verifier",
        "tools/nfl_stadium_upper_deck_subset_verify.py",
        64_069,
        "8eaf78f4a0a4a26777d2b9d672e50d4298b3b4f3afd2565c84947ceb799e1585",
    ),
    (
        "source_triangle_conformer",
        "tools/nfl_upper_deck_source_triangle_conform.py",
        21_016,
        "804379c61667c981b95559743ea7bef06801e52a2596259b6e0896539a7322eb",
    ),
)


class BoundsError(ValueError):
    """A source pin, executable sequence, or sphere invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BoundsError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def authority_evidence() -> dict[str, object]:
    rows: dict[str, object] = {}
    parsed: dict[str, object] = {}
    for name, relative, expected_size, expected_sha256 in AUTHORITIES:
        path = ROOT / relative
        payload = path.read_bytes()
        require(len(payload) == expected_size and sha256(payload) == expected_sha256,
                f"authority {name} size or SHA-256 differs")
        rows[name] = {
            "path": relative,
            "size": expected_size,
            "sha256": expected_sha256,
        }
        if path.suffix == ".json":
            parsed[name] = json.loads(payload.decode("utf-8"))

    boundary = parsed["changed_count_boundary"]
    require(boundary["schema"] == "nfl2k5_upper_deck_changed_count_boundary/v1" and
            boundary["topology_contract"]["changed_vertex_counts"] == [4, 8],
            "changed-count authority differs")
    recipe = parsed["source_subset_recipe_schema"]
    ids = recipe["properties"]["source_vertex_ids"]
    require(recipe["properties"]["new_vertex_count"]["enum"] == [4, 8] and
            ids["uniqueItems"] is True and ids["items"] == {
                "maximum": 11, "minimum": 0, "type": "integer",
            }, "source-subset recipe authority differs")
    closure = parsed["source_subset_writeback_closure"]
    claims = closure["claim_flags"]
    require(claims["changed_count_source_subset_writer_implemented"] is True and
            claims["independent_changed_count_verifier_implemented"] is True and
            claims["arbitrary_external_vertex_authoring_proved"] is False,
            "source-subset writeback closure differs")
    triangles = parsed["source_triangle_mesh_schema"]
    require(triangles["properties"]["triangles"]["minItems"] == 2 and
            triangles["properties"]["triangles"]["maxItems"] == 4,
            "source-triangle authoring authority differs")
    return {
        "files": rows,
        "admitted_source_vertex_ids": "distinct IDs in [0,11]",
        "admitted_changed_counts": [4, 8],
        "external_vertex_values_admitted": False,
    }


def xbe_reader(xbe: bytes, header: dict[str, object]):
    def read(va: int, size: int) -> bytes:
        for section in header["sections"]:  # type: ignore[index]
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                offset = int(section["raw_address"]) + va - start
                return xbe[offset:offset + size]
        raise BoundsError(f"XBE VA 0x{va:08x}+0x{size:x} is not raw-backed")
    return read


def executable_evidence(xbe_path: Path, header_path: Path) -> dict[str, object]:
    xbe = xbe_path.read_bytes()
    require(hashlib.md5(xbe).hexdigest() == EXPECTED_XBE_MD5,
            "unexpected NFL 2K5 executable MD5")
    require(sha256(xbe) == EXPECTED_XBE_SHA256,
            "unexpected NFL 2K5 executable SHA-256")
    header = json.loads(header_path.read_text(encoding="utf-8"))
    read = xbe_reader(xbe, header)

    center_getter = read(0x00023750, 3)
    radius_getter = read(0x00023760, 4)
    require(center_getter == bytes.fromhex("8bc1c3"),
            "shape-center getter no longer returns the shape base")
    require(radius_getter == bytes.fromhex("d94148c3"),
            "shape-radius getter no longer loads shape +0x48")

    dispatch = read(0x000215A0, 0x87)
    required_dispatch = (
        bytes.fromhex("8b4e08578bfae8992100008bd08b46148d4c2410e85bffffff"),
        bytes.fromhex("8b4e08e893210000d95c240c"),
        bytes.fromhex("8b460ca801740bd94610d84c240cd95c240c"),
        bytes.fromhex("50") + bytes.fromhex("8d5424148bcf") + bytes.fromhex("e8"),
    )
    for sequence in required_dispatch:
        require(sequence in dispatch,
                f"node sphere-dispatch sequence missing: {sequence.hex()}")

    render_node = read(0x00021860, 0x63)
    for sequence in (
        bytes.fromhex("8b460885c07504"),
        bytes.fromhex("f6c3107405"),
        bytes.fromhex("f6c3047512"),
        bytes.fromhex("8bd08bcee811fdffff85c074e4"),
    ):
        require(sequence in render_node,
                f"render-node culling gate missing: {sequence.hex()}")

    frustum = read(0x0002ADC0, 0xE1)
    require(frustum.count(bytes.fromhex("d84508")) == 3 and
            frustum.count(bytes.fromhex("d86d08")) == 2,
            "frustum test no longer expands its planes by the supplied radius")
    require(frustum.endswith(bytes.fromhex("c20400")),
            "frustum sphere test return convention changed")

    return {
        "path": str(xbe_path),
        "md5": EXPECTED_XBE_MD5,
        "sha256": EXPECTED_XBE_SHA256,
        "function_ranges": [
            {
                "name": name,
                "start_va": f"0x{start:08x}",
                "end_va_exclusive": f"0x{end:08x}",
                "size": end - start,
                "sha256": sha256(read(start, end - start)),
            }
            for name, start, end in FUNCTION_RANGES
        ],
        "proved_dataflow": {
            "serialized_center": "shape +0x00/+0x04/+0x08 f32le; +0x0c homogeneous 1.0",
            "serialized_radius": "shape +0x48 f32le",
            "center_transform": "node +0x14 current matrix transforms the local center",
            "radius_scale": "node flags +0x0c bit 0 selects radius *= node +0x10",
            "culling_bypass": "node flags +0x0c bit 2 bypasses the sphere test",
            "render_suppress": "node flags +0x0c bit 4 suppresses the node before culling",
            "consumer": "0x0002adc0 camera/frustum sphere test",
        },
    }


class PersistentArchiveReader:
    """Read bounded entry ranges while retaining one handle per pack."""

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
        require(0 <= relative_offset <= relative_offset + size <= entry.size,
                f"entry {entry.table_index}: requested span is outside the entry")
        relative_end = relative_offset + size
        result = bytearray()
        segment_start = 0
        for segment in entry.segments:
            segment_end = segment_start + segment.size
            part_start = max(relative_offset, segment_start)
            part_end = min(relative_end, segment_end)
            if part_start < part_end:
                stream = self.streams[segment.pack_ordinal]
                stream.seek(segment.pack_offset + part_start - segment_start)
                part = stream.read(part_end - part_start)
                require(len(part) == part_end - part_start,
                        f"entry {entry.table_index}: short pack read")
                result.extend(part)
            segment_start = segment_end
            if part_end == relative_end:
                break
        require(len(result) == size,
                f"entry {entry.table_index}: incomplete multi-pack read")
        return bytes(result)


def normshort(value: int) -> float:
    return value / (32767.0 if value >= 0 else 32768.0)


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def next_f32_up(value: float) -> float:
    require(math.isfinite(value) and value >= 0.0,
            "next-f32 input must be finite and nonnegative")
    bits = struct.unpack("<I", struct.pack("<f", value))[0]
    require(bits < 0x7F7FFFFF, "next-f32 input is already the largest finite value")
    return struct.unpack("<f", struct.pack("<I", bits + 1))[0]


def decode_position(
    data: bytes,
    source: int,
    format_name: str,
    scale: float,
    bias: tuple[float, float, float],
) -> tuple[float, float, float]:
    if format_name == "FLOAT3":
        return struct.unpack_from("<3f", data, source)
    if format_name == "NORMSHORT3":
        raw = struct.unpack_from("<3h", data, source)
        return tuple(
            f32(f32(normshort(value)) * scale + bias[axis])
            for axis, value in enumerate(raw)
        )
    raise BoundsError(f"unsupported register-0 position format {format_name}")


def sphere_measurement(
    center: tuple[float, float, float],
    radius: float,
    positions: list[tuple[float, float, float]],
) -> dict[str, float | bool]:
    require(positions, "sphere measurement requires at least one position")
    maximum_squared = max(
        sum((position[axis] - center[axis]) ** 2 for axis in range(3))
        for position in positions
    )
    maximum_distance = math.sqrt(maximum_squared)
    return {
        "maximum_vertex_distance": maximum_distance,
        "radius": radius,
        "signed_slack": radius - maximum_distance,
        "contains_all_vertices": maximum_distance <= radius,
    }


def corpus_evidence(
    index_path: Path,
    scan_path: Path,
    progress_every: int,
) -> dict[str, object]:
    require(index_path.stat().st_size == EXPECTED_INDEX_SIZE,
            "archive index size differs")
    require(sha256_file(index_path) == EXPECTED_INDEX_SHA256,
            "archive index SHA-256 differs")
    require(scan_path.stat().st_size == EXPECTED_SCAN_SIZE,
            "resource inventory size differs")
    require(sha256_file(scan_path) == EXPECTED_SCAN_SHA256,
            "resource inventory SHA-256 differs")

    archive = parse_archive(index_path)
    inventory, all_resources = parse_inventory(scan_path)
    resources = [record for record in all_resources if record.kind == "SCNE"]
    require(len(resources) == 4_616,
            "SCNE resource count differs")
    require(int(inventory["summary"]["resource_kind_counts"]["SCNE"]) == len(resources),
            "resource inventory SCNE declaration differs")

    counts: Counter[str] = Counter()
    format_counts: Counter[str] = Counter()
    flag_counts: Counter[int] = Counter()
    exact_containment_by_format: Counter[str] = Counter()
    one_ulp_containment_by_format: Counter[str] = Counter()
    negative_slack_count = 0
    more_than_one_ulp_outside_count = 0
    minimum_slack = math.inf
    maximum_slack = -math.inf
    maximum_deficit = 0.0
    maximum_deficit_in_radius_ulps = 0.0
    target: dict[str, object] | None = None

    with PersistentArchiveReader(archive) as source:
        for scene_index, resource in enumerate(resources):
            entry = archive.entries[resource.outer_index]
            span = source.read(entry, resource.chunk_offset, 0x20 + resource.stored_size)
            output, detail = decode_resource(span, resource)
            system_size = resource.word_08
            require(len(output) == resource.word_08 + resource.word_0c,
                    f"scene {scene_index}: decoded size differs")
            require(output[0x0C:0x10] == b"SCNE",
                    f"scene {scene_index}: missing SCNE marker")
            descriptor = resolve_relative(
                output, 0x14, system_size, f"scene {scene_index} descriptor"
            )
            require(descriptor is not None and descriptor + 0x54 <= system_size,
                    f"scene {scene_index}: descriptor unavailable")
            shape_count = struct.unpack_from("<I", output, descriptor + 0x2C)[0]
            shape_start = resolve_relative(
                output, descriptor + 0x30, system_size,
                f"scene {scene_index} shape table",
            )
            require((shape_count == 0 and shape_start is None) or
                    (shape_start is not None and shape_start + shape_count * 0x100 <= system_size),
                    f"scene {scene_index}: shape table differs")

            node_count = struct.unpack_from("<I", output, descriptor + 0x24)[0]
            node_start = resolve_relative(
                output, descriptor + 0x28, system_size,
                f"scene {scene_index} node table",
            )
            require((node_count == 0 and node_start is None) or
                    (node_start is not None and node_start + node_count * 0x60 <= system_size),
                    f"scene {scene_index}: node table differs")
            for node_index in range(node_count):
                assert node_start is not None
                node = node_start + node_index * 0x60
                flags = struct.unpack_from("<I", output, node + 0x0C)[0]
                scale = struct.unpack_from("<f", output, node + 0x10)[0]
                require(math.isfinite(scale),
                        f"scene {scene_index} node {node_index}: non-finite sphere scale")
                matrix = resolve_relative(
                    output, node + 0x14, system_size,
                    f"scene {scene_index} node {node_index} current matrix",
                )
                require(matrix is not None and matrix + 0x40 <= system_size,
                        f"scene {scene_index} node {node_index}: current matrix unavailable")
                flag_counts[flags] += 1
                counts["node_count"] += 1
                counts["radius_scaled_node_count"] += int(bool(flags & 1))
                counts["culling_bypass_node_count"] += int(bool(flags & 4))
                counts["render_suppressed_node_count"] += int(bool(flags & 0x10))
                counts["special_matrix_node_count"] += int(bool(flags & 0x20))

            for shape_index in range(shape_count):
                assert shape_start is not None
                shape = shape_start + shape_index * 0x100
                center4 = struct.unpack_from("<4f", output, shape)
                radius = struct.unpack_from("<f", output, shape + 0x48)[0]
                require(all(math.isfinite(value) for value in center4) and center4[3] == 1.0,
                        f"scene {scene_index} shape {shape_index}: invalid homogeneous sphere center")
                require(math.isfinite(radius) and radius >= 0.0,
                        f"scene {scene_index} shape {shape_index}: invalid sphere radius")
                vertex_count = struct.unpack_from("<H", output, shape + 0x4C)[0]
                encoded = struct.unpack_from("<I", output, shape + 0x84)[0]
                format_code = encoded & 0xFF
                stream_index = (encoded >> 8) & 0xFF
                byte_offset = encoded >> 16
                format_name = {0x32: "FLOAT3", 0x31: "NORMSHORT3"}.get(format_code)
                require(format_name is not None and stream_index < 8,
                        f"scene {scene_index} shape {shape_index}: unsupported r0 0x{encoded:08x}")
                stride = struct.unpack_from("<H", output, shape + 0xC4 + stream_index * 2)[0]
                stream_start = resolve_relative(
                    output, shape + 0xD4 + stream_index * 4, system_size,
                    f"scene {scene_index} shape {shape_index} r0 stream",
                )
                width = 12 if format_name == "FLOAT3" else 6
                require(vertex_count > 0 and stride > 0 and byte_offset + width <= stride,
                        f"scene {scene_index} shape {shape_index}: invalid r0 lane")
                require(stream_start is not None and
                        stream_start + vertex_count * stride <= system_size,
                        f"scene {scene_index} shape {shape_index}: r0 stream unavailable")
                scale = struct.unpack_from("<f", output, shape + 0x10)[0]
                bias = struct.unpack_from("<3f", output, shape + 0x20)
                require(math.isfinite(scale) and all(math.isfinite(value) for value in bias),
                        f"scene {scene_index} shape {shape_index}: invalid r0 scale/bias")
                positions = [
                    decode_position(
                        output,
                        stream_start + vertex * stride + byte_offset,
                        format_name,
                        scale,
                        bias,
                    )
                    for vertex in range(vertex_count)
                ]
                require(all(all(math.isfinite(value) for value in point) for point in positions),
                        f"scene {scene_index} shape {shape_index}: non-finite position")
                measured = sphere_measurement(center4[:3], radius, positions)
                slack = float(measured["signed_slack"])
                next_radius = next_f32_up(radius)
                within_one_ulp = float(measured["maximum_vertex_distance"]) <= next_radius
                minimum_slack = min(minimum_slack, slack)
                maximum_slack = max(maximum_slack, slack)
                if measured["contains_all_vertices"]:
                    exact_containment_by_format[format_name] += 1
                if within_one_ulp:
                    one_ulp_containment_by_format[format_name] += 1
                else:
                    more_than_one_ulp_outside_count += 1
                if not measured["contains_all_vertices"]:
                    negative_slack_count += 1
                    maximum_deficit = max(maximum_deficit, -slack)
                    radius_ulp = next_radius - radius
                    require(radius_ulp > 0.0,
                            f"scene {scene_index} shape {shape_index}: radius ULP is not positive")
                    maximum_deficit_in_radius_ulps = max(
                        maximum_deficit_in_radius_ulps, -slack / radius_ulp
                    )
                counts["shape_count"] += 1
                counts["vertex_count"] += vertex_count
                format_counts[format_name] += 1

                if (resource.outer_index, resource.chunk_index, shape_index) == (
                    TARGET_OUTER, TARGET_CHUNK, TARGET_SHAPE
                ):
                    require(detail["decoded_sha256"] == TARGET_DECODED_SHA256,
                            "upper_deck decoded source differs")
                    require(vertex_count == TARGET_VERTEX_COUNT and format_name == "FLOAT3",
                            "upper_deck position contract differs")
                    raw_positions = output[
                        stream_start + byte_offset:
                        stream_start + byte_offset + vertex_count * stride
                    ]
                    require(stream_start == TARGET_POSITION_OFFSET and stride == 12 and
                            len(raw_positions) == TARGET_POSITION_SIZE and
                            sha256(raw_positions) == TARGET_POSITION_SHA256,
                            "upper_deck position span differs")
                    target = {
                        "target_id": "nfl2k5/stadium/o3280/c5/s1",
                        "shape_record_offset": shape,
                        "center_field": {
                            "offset": shape,
                            "size": 16,
                            "sha256": sha256(output[shape:shape + 16]),
                        },
                        "radius_field": {
                            "offset": shape + 0x48,
                            "size": 4,
                            "sha256": sha256(output[shape + 0x48:shape + 0x4C]),
                        },
                        "position_span_sha256": TARGET_POSITION_SHA256,
                        "source_vertex_count": vertex_count,
                        "maximum_distance_le_radius": bool(measured["contains_all_vertices"]),
                        "signed_slack": slack,
                        "all_admissible_4_or_8_source_subsets_contained": bool(
                            measured["contains_all_vertices"]
                        ),
                    }

            counts["scene_count"] += 1
            if progress_every and (scene_index + 1) % progress_every == 0:
                print(
                    f"validated {scene_index + 1}/{len(resources)} SCNE bounding spheres",
                    file=sys.stderr,
                    flush=True,
                )

    require(target is not None, "upper_deck target was not found")
    return {
        "source": {
            "archive_index": str(index_path),
            "archive_index_size": EXPECTED_INDEX_SIZE,
            "archive_index_sha256": EXPECTED_INDEX_SHA256,
            "resource_inventory": str(scan_path),
            "resource_inventory_size": EXPECTED_SCAN_SIZE,
            "resource_inventory_sha256": EXPECTED_SCAN_SHA256,
        },
        "counts": {key: counts[key] for key in sorted(counts)},
        "register_zero_format_counts": dict(sorted(format_counts.items())),
        "node_flag_word_counts": {
            f"0x{key:08x}": flag_counts[key] for key in sorted(flag_counts)
        },
        "sphere_containment": {
            "exact_containment_shape_count": counts["shape_count"] - negative_slack_count,
            "exact_containment_by_format": dict(sorted(exact_containment_by_format.items())),
            "negative_slack_shape_count": negative_slack_count,
            "within_one_upward_radius_ulp_shape_count": sum(one_ulp_containment_by_format.values()),
            "within_one_upward_radius_ulp_by_format": dict(sorted(one_ulp_containment_by_format.items())),
            "more_than_one_upward_radius_ulp_outside_count": more_than_one_ulp_outside_count,
            "minimum_signed_slack": minimum_slack,
            "maximum_signed_slack": maximum_slack,
            "maximum_deficit": maximum_deficit,
            "maximum_deficit_in_radius_ulps": maximum_deficit_in_radius_ulps,
        },
        "upper_deck": target,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xbe", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"),
    )
    parser.add_argument(
        "--xbe-header", type=Path,
        default=Path("reports/headers/nfl2k5_xbe_header.json"),
    )
    parser.add_argument(
        "--index", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"),
    )
    parser.add_argument(
        "--resource-scan", type=Path,
        default=Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
    )
    parser.add_argument(
        "--json", type=Path,
        default=Path("reports/assets/nfl_scne_bounds_ownership.json"),
    )
    parser.add_argument("--progress-every", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = {
        "schema": SCHEMA,
        "authorities": authority_evidence(),
        "executable": executable_evidence(args.xbe, args.xbe_header),
        "corpus": corpus_evidence(args.index, args.resource_scan, args.progress_every),
        "proved_contract": {
            "shape_center_fields": ["+0x00 f32le", "+0x04 f32le", "+0x08 f32le"],
            "shape_center_homogeneous_w": "+0x0c f32le == 1.0",
            "shape_radius_field": "+0x48 f32le",
            "runtime_center_equation": "world_center = node_current_matrix * local_shape_center",
            "runtime_radius_equation": "radius = shape_radius * (node_scale when flags bit0 else 1)",
            "frustum_test": "0x0002adc0 tests the transformed sphere against six camera planes",
            "upper_deck_policy": "preserve the retail sphere for every 4/8 distinct source-record subset",
        },
        "claim_flags": {
            "serialized_sphere_owner_proved": True,
            "frustum_culling_consumer_proved": True,
            "complete_static_shape_corpus_audited": True,
            "upper_deck_source_subset_needs_bounds_rewrite": False,
            "bounds_serializer_implemented": False,
            "arbitrary_external_positions_proved": False,
            "collision_or_lod_ownership_proved": False,
            "runtime_visibility_proved": False,
            "original_xbox_hardware_proved": False,
        },
        "portme": [
            "PORTME: implement and independently verify conservative sphere authoring before admitting external positions outside the retail sphere.",
            "PORTME: recover collision and LOD ownership independently; the render sphere does not prove either system.",
            "PORTME: obtain runtime camera-distance/frustum witnesses for a changed geometry artifact.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(canonical_json(report), encoding="utf-8")
    counts = report["corpus"]["counts"]  # type: ignore[index]
    containment = report["corpus"]["sphere_containment"]  # type: ignore[index]
    print(
        "NFL_SCNE_BOUNDS_OWNERSHIP_COMPLETE "
        f"scenes={counts['scene_count']} shapes={counts['shape_count']} "
        f"vertices={counts['vertex_count']} "
        f"outside={containment['negative_slack_shape_count']} "
        "upper_deck_subset_contained=true writer=false runtime=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, BoundsError, ValueError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
