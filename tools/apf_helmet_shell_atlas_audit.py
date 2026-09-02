#!/usr/bin/env python3
"""Audit/prototype APF's existing whole-shell crest atlas route, headlessly.

The retail exterior shell already has a complete two-island UV unwrap.  This
tool proves its ownership and atlas quality, then optionally emits a raw SCNE
prototype that routes shell draw 1 to crest material 2 and degenerates the old
bounded draw-2 overlay.  It never invokes an emulator or changes its input.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
for search_root in (ROOT, ROOT / "tools"):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

import apf_helmet_crest_wrap_patch as crest  # noqa: E402
import apf_helmet_crest_wrap_verify as independent  # noqa: E402


DRAW_RECORD_SIZE = 0x30
DRAW_RECORD_COUNT = 13
SHELL_DRAW = 1
CARRIER_DRAW = 2
SOURCE_SHELL_MATERIAL = 1
CREST_MATERIAL = 2
MATERIAL_FIELD_OFFSETS = {
    "helmet_hi": 0x00009A10,
    "helmet_lo": 0x000CCAD0,
}


def _draw_records(source: bytes, spec: crest.LodSpec) -> list[tuple[int, ...]]:
    return [
        struct.unpack_from(">12I", source, spec.draw_record_offset + index * DRAW_RECORD_SIZE)
        for index in range(DRAW_RECORD_COUNT)
    ]


def _outer_shell(
    source: bytes, spec: crest.LodSpec,
) -> tuple[
    list[tuple[int, int, int]],
    list[tuple[float, float, float]],
    list[tuple[float, float, float]],
]:
    positions = [crest._decode_position(source, spec, index) for index in range(spec.vertex_count)]
    normals = [
        crest._unit(crest._decode_vec3(source, spec.stream_start + index * crest.STRIDE + 8))
        for index in range(spec.vertex_count)
    ]
    words = crest._indices(source, spec)
    shell = crest._triangles(
        words[spec.shell_index_start : spec.shell_index_start + spec.shell_index_count]
    )
    outer: list[tuple[int, int, int]] = []
    for face in shell:
        center = tuple(sum(positions[index][axis] for index in face) / 3.0 for axis in range(3))
        normal = tuple(sum(normals[index][axis] for index in face) for axis in range(3))
        radial = (
            center[0], center[1] - spec.center[1], center[2] - spec.center[2],
        )
        if crest._dot(normal, radial) > 0.0:
            outer.append(face)
    return outer, positions, normals


def _boundary_metrics(faces: Sequence[tuple[int, int, int]]) -> dict[str, Any]:
    edges = Counter(
        tuple(sorted((face[axis], face[(axis + 1) % 3])))
        for face in faces
        for axis in range(3)
    )
    if any(count not in (1, 2) for count in edges.values()):
        raise crest.PatchError("shell atlas contains a non-manifold edge")
    boundary = [edge for edge, count in edges.items() if count == 1]
    adjacency: dict[int, set[int]] = defaultdict(set)
    for first, second in boundary:
        adjacency[first].add(second)
        adjacency[second].add(first)
    if not adjacency or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise crest.PatchError("shell atlas boundary is not a set of simple cycles")
    components: list[int] = []
    unseen = set(adjacency)
    while unseen:
        stack = [min(unseen)]
        seen = {stack[0]}
        while stack:
            current = stack.pop()
            for following in adjacency[current]:
                if following not in seen:
                    seen.add(following)
                    stack.append(following)
        components.append(len(seen))
        unseen -= seen
    vertices = {index for face in faces for index in face}
    return {
        "boundary_cycle_vertex_counts": sorted(components, reverse=True),
        "edge_count": len(edges),
        "euler_characteristic": len(vertices) - len(edges) + len(faces),
        "face_count": len(faces),
        "is_annulus": len(components) == 2
        and len(vertices) - len(edges) + len(faces) == 0,
        "vertex_count": len(vertices),
    }


def _determinant(
    face: tuple[int, int, int], uv: Mapping[int, tuple[float, float]],
) -> float:
    first, second, third = (uv[index] for index in face)
    return (
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _window_ownership(
    source: bytes, spec: crest.LodSpec, records: Sequence[tuple[int, ...]],
) -> dict[str, Any]:
    indices = crest._indices(source, spec)
    shell_start = records[SHELL_DRAW][5]
    shell_end = shell_start + records[SHELL_DRAW][6]
    shell_vertices = set(range(shell_start, shell_end))
    windows = []
    for number, record in enumerate(records):
        first, count = record[1], record[2]
        references = {value for value in indices[first : first + count] if value != 0xFFFF}
        windows.append({
            "draw": number,
            "first_index_word": first,
            "index_word_count": count,
            "vertex_start": record[5],
            "vertex_count": record[6],
            "material": record[8],
            "unique_referenced_vertices": len(references),
            "references_into_shell_draw_vertex_window": len(references & shell_vertices),
        })
    return {
        "all_index_windows_contiguous": all(
            records[number][1] + records[number][2] == records[number + 1][1]
            for number in range(len(records) - 1)
        ),
        "all_vertex_windows_contiguous": all(
            records[number][5] + records[number][6] == records[number + 1][5]
            for number in range(len(records) - 1)
        ),
        "draws": windows,
        "non_shell_draw_reference_overlap": sum(
            row["references_into_shell_draw_vertex_window"]
            for row in windows if row["draw"] != SHELL_DRAW
        ),
        "shell_draw_references_every_owned_vertex": (
            windows[SHELL_DRAW]["unique_referenced_vertices"] == records[SHELL_DRAW][6]
        ),
    }


def build_prototype(source: bytes) -> tuple[bytes, dict[str, Any]]:
    """Return the two-field route plus degenerate-overlay raw SCNE witness."""

    output = bytearray(source)
    lod_reports: list[dict[str, Any]] = []
    authorized: set[int] = set()
    nodes = crest._scene_nodes(source)
    for spec in crest.LODS:
        crest._validate_layout(source, spec, nodes[spec.node_index])
        records = _draw_records(source, spec)
        if len(records) != DRAW_RECORD_COUNT:
            raise crest.PatchError(f"{spec.node_name} draw count differs")
        if records[SHELL_DRAW][8] != SOURCE_SHELL_MATERIAL:
            raise crest.PatchError(f"{spec.node_name} shell material source differs")
        if records[CARRIER_DRAW][8] != CREST_MATERIAL:
            raise crest.PatchError(f"{spec.node_name} crest material source differs")
        ownership = _window_ownership(source, spec, records)
        if (
            not ownership["all_index_windows_contiguous"]
            or not ownership["all_vertex_windows_contiguous"]
            or ownership["non_shell_draw_reference_overlap"] != 0
            or not ownership["shell_draw_references_every_owned_vertex"]
        ):
            raise crest.PatchError(f"{spec.node_name} shell ownership is not isolated")

        material_offset = MATERIAL_FIELD_OFFSETS[spec.node_name]
        derived_material_offset = spec.draw_record_offset + SHELL_DRAW * DRAW_RECORD_SIZE + 0x20
        if material_offset != derived_material_offset:
            raise crest.PatchError(f"{spec.node_name} material offset derivation differs")
        struct.pack_into(">I", output, material_offset, CREST_MATERIAL)
        authorized.update(range(material_offset, material_offset + 4))

        carrier_index_byte = spec.index_offset + spec.carrier_index_start * 2
        degenerate = struct.pack(">H", spec.carrier_vertex_start) * spec.carrier_index_count
        output[carrier_index_byte : carrier_index_byte + len(degenerate)] = degenerate
        authorized.update(range(carrier_index_byte, carrier_index_byte + len(degenerate)))
        if crest._triangles([spec.carrier_vertex_start] * spec.carrier_index_count):
            raise crest.PatchError(f"{spec.node_name} degenerate overlay still makes faces")

        outer, positions, _normals = _outer_shell(source, spec)
        vertices = {index for face in outer for index in face}
        uv = {index: crest._uv(source, spec, index) for index in vertices}
        determinants = [_determinant(face, uv) for face in outer]
        if not determinants or min(determinants) < 0.0 < max(determinants):
            raise crest.PatchError(f"{spec.node_name} shell atlas has mixed UV orientation")
        overlaps = independent._projected_overlap_count(outer, uv)
        if overlaps:
            raise crest.PatchError(f"{spec.node_name} shell atlas overlaps itself")
        right = [face for face in outer if all(positions[index][0] >= -1.0e-6 for index in face)]
        left = [face for face in outer if all(positions[index][0] <= 1.0e-6 for index in face)]
        if len(right) + len(left) != len(outer) or len(right) != len(left):
            raise crest.PatchError(f"{spec.node_name} shell atlas does not split into two sides")
        right_vertices = {index for face in right for index in face}
        left_vertices = {index for face in left for index in face}
        topology = _boundary_metrics(right)
        if not topology["is_annulus"]:
            raise crest.PatchError(f"{spec.node_name} shell side is not the expected annulus")
        lod_reports.append({
            "node": spec.node_name,
            "material_route": {
                "draw": SHELL_DRAW,
                "field_offset": f"0x{material_offset:08X}",
                "source": SOURCE_SHELL_MATERIAL,
                "output": CREST_MATERIAL,
            },
            "ownership": ownership,
            "exterior_atlas": {
                "face_count": len(outer),
                "vertex_count": len(vertices),
                "faces_per_side": len(right),
                "right_side_topology": topology,
                "uv_domain": {
                    "minimum": [min(value[axis] for value in uv.values()) for axis in range(2)],
                    "maximum": [max(value[axis] for value in uv.values()) for axis in range(2)],
                },
                "right_u_domain": [
                    min(uv[index][0] for index in right_vertices),
                    max(uv[index][0] for index in right_vertices),
                ],
                "left_u_domain": [
                    min(uv[index][0] for index in left_vertices),
                    max(uv[index][0] for index in left_vertices),
                ],
                "minimum_absolute_uv_triangle_determinant": min(map(abs, determinants)),
                "mixed_uv_orientation": False,
                "projected_overlap_count": overlaps,
                "source_uv_stream_reused_exactly": True,
            },
            "old_draw_2_overlay": {
                "fixed_index_word_count": spec.carrier_index_count,
                "replacement_word": spec.carrier_vertex_start,
                "decoded_triangle_count_after": 0,
                "draw_record_unchanged": True,
                "vertex_stream_unchanged": True,
            },
        })

    payload = bytes(output)
    changed = {index for index, pair in enumerate(zip(source, payload)) if pair[0] != pair[1]}
    if not changed or not changed <= authorized:
        raise crest.PatchError("shell-atlas prototype changed an unauthorized SCNE byte")
    for spec in crest.LODS:
        if (
            source[spec.stream_start : spec.stream_start + spec.vertex_count * crest.STRIDE]
            != payload[spec.stream_start : spec.stream_start + spec.vertex_count * crest.STRIDE]
        ):
            raise crest.PatchError(f"{spec.node_name} vertex stream changed")
    return payload, {
        "schema": "apf2k8_helmet_shell_atlas_audit/v1",
        "verdict": "production-feasible whole-shell atlas; no carrier expansion or UV rewrite",
        "source_scne_sha256": hashlib.sha256(source).hexdigest(),
        "prototype_scne_sha256": hashlib.sha256(payload).hexdigest(),
        "changed_byte_count": len(changed),
        "headless": True,
        "emulator_required": False,
        "mask_shader_equation": (
            "shell*(255-red-green)/255 + palette[0]*red/255 + palette[2]*green/255"
        ),
        "black_mask_texel_result": "exact shell base when red=green=0",
        "production_delta": [
            "route helmet_hi and helmet_lo draw 1 material slot 1 to crest slot 2",
            "reuse the retail exterior-shell UV atlas byte-for-byte",
            "author two-sided crest art in the stock 512x512 atlas with black inactive texels",
            "replace each old draw-2 index window with one repeated in-range vertex",
        ],
        "preservation": {
            "all_draw_records_except_two_material_words_exact": True,
            "all_vertex_streams_exact": True,
            "draws_0_and_3_through_12_indices_exact": True,
            "accessory_material_routes_exact": True,
        },
        "lods": lod_reports,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-0a", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output-scne", type=Path)
    return parser.parse_args(argv)


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    source = crest._parse_outer(crest.read_source_outer(args.source_0a), source=True).system
    output, report = build_prototype(source)
    rendered = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if args.output_scne is not None:
        _write_new(args.output_scne, output)
    if args.report is not None:
        _write_new(args.report, rendered)
    sys.stdout.buffer.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
