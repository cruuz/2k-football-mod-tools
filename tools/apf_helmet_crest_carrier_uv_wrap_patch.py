#!/usr/bin/env python3
"""Build the private dual-LOD UV-driven APF helmet crest wrap witness.

The retail crest carrier already has a complete, mirrored logo UV square, but
its shell patch is small.  This source-bound diagnostic keeps that UV topology
and maps it from the front crown seam toward the rear shell.  Projection is
restricted to outward-facing shell triangles and receives a tiny outward bias
so signed-normalized rounding cannot bury the carrier behind the base helmet.

Only POSITION0.xyz, NORMAL0.xyz, and TANGENT0.xyz in draw 2 of ``helmet_hi``
and ``helmet_lo`` may change.  This remains a private runtime witness until an
emulator capture proves the intended Eagles appearance.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_carrier_expand_patch as previous  # noqa: E402


SCHEMA = "apf2k8_helmet_crest_carrier_uv_wrap_patch/v1"
OPERATION = "uv_wrap_helmet_hi_and_lo_draw_2_crest_carrier"
RECEIPT_SUFFIX = ".apf-helmet-crest-carrier-uv-wrap.json"

# These are helmet-local units.  The requested point traces a front-to-rear
# path; closest-point projection supplies the exact shell curvature.
FRONT_Z = 13.0
REAR_Z = -11.0
TOP_Y = 18.45
BOTTOM_Y = 3.95
MAX_SIDE_X = 11.7
MIN_SIDE_X = 0.2
FRONT_RAMP_START = 0.02
FRONT_RAMP_END = 0.27
REAR_TAPER_START = 0.76
REAR_TAPER = 0.43
OUTWARD_BIAS = 0.045

PatchError = previous.PatchError


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _outer_projection(
    wanted: tuple[float, float, float],
    side: int,
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
    shell_triangles: list[tuple[int, int, int]],
    spec: previous.LodSpec,
) -> previous.Projection:
    """Project onto the same-side exterior, never an inner helmet face."""

    best: tuple[
        float,
        tuple[float, float, float],
        tuple[int, int, int],
        tuple[float, float, float],
    ] | None = None
    for triangle in shell_triangles:
        if not all(positions[index][0] * side >= -1.0e-6 for index in triangle):
            continue
        center = tuple(
            sum(positions[index][axis] for index in triangle) / 3.0
            for axis in range(3)
        )
        average_normal = tuple(
            sum(normals[index][axis] for index in triangle)
            for axis in range(3)
        )
        radial = (
            center[0],
            center[1] - spec.center[1],
            center[2] - spec.center[2],
        )
        if previous._dot(average_normal, radial) <= 0.0:
            continue
        point, barycentric = previous._closest_point(
            wanted,
            positions[triangle[0]],
            positions[triangle[1]],
            positions[triangle[2]],
        )
        delta = previous._sub(wanted, point)
        distance = previous._dot(delta, delta)
        candidate = (distance, point, triangle, barycentric)
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        raise PatchError("could not project a crest vertex onto the outer shell")
    _, point, triangle, barycentric = best
    normal = previous._unit(tuple(
        sum(barycentric[j] * normals[triangle[j]][axis] for j in range(3))
        for axis in range(3)
    ))
    radial = (
        point[0],
        point[1] - spec.center[1],
        point[2] - spec.center[2],
    )
    if previous._dot(normal, radial) < 0.0:
        normal = previous._mul(normal, -1.0)
    return previous.Projection(
        previous._add(point, previous._mul(normal, OUTWARD_BIAS)),
        normal,
    )


def _uv_wrap_geometry(
    payload: bytes,
    spec: previous.LodSpec,
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
    shell_triangles: list[tuple[int, int, int]],
    carrier_triangles: list[tuple[int, int, int]],
) -> tuple[dict[int, previous.Projection], int]:
    carrier = list(range(
        spec.carrier_vertex_start,
        spec.carrier_vertex_start + spec.carrier_vertex_count,
    ))
    uvs = {index: previous._uv(payload, spec, index) for index in carrier}
    u_min = min(value[0] for value in uvs.values())
    u_max = max(value[0] for value in uvs.values())
    v_min = min(value[1] for value in uvs.values())
    v_max = max(value[1] for value in uvs.values())
    if u_max - u_min <= 1.0e-6 or v_max - v_min <= 1.0e-6:
        raise PatchError(f"{spec.node_name} crest UV domain collapsed")

    aggressive: dict[int, tuple[float, float, float]] = {}
    for index in carrier:
        side = 1 if positions[index][0] > 0.0 else -1
        u = (uvs[index][0] - u_min) / (u_max - u_min)
        v = (uvs[index][1] - v_min) / (v_max - v_min)
        front = _smoothstep(
            (u - FRONT_RAMP_START) / (FRONT_RAMP_END - FRONT_RAMP_START)
        )
        rear = 1.0 - REAR_TAPER * _smoothstep(
            (u - REAR_TAPER_START) / (1.0 - REAR_TAPER_START)
        )
        aggressive[index] = (
            side * (MIN_SIDE_X + (MAX_SIDE_X - MIN_SIDE_X) * front * rear),
            TOP_Y + (BOTTOM_Y - TOP_Y) * v,
            FRONT_Z + (REAR_Z - FRONT_Z) * u,
        )

    alpha = {index: 1.0 for index in carrier}
    for repair_round in range(previous.MAX_REPAIR_ROUNDS + 1):
        projections: dict[int, previous.Projection] = {}
        for index in carrier:
            wanted = previous._add(
                positions[index],
                previous._mul(
                    previous._sub(aggressive[index], positions[index]),
                    alpha[index],
                ),
            )
            side = 1 if positions[index][0] > 0.0 else -1
            projections[index] = _outer_projection(
                wanted, side, positions, normals, shell_triangles, spec,
            )
        bad = previous._bad_triangles(projections, carrier_triangles)
        if not bad:
            return projections, repair_round
        if repair_round >= previous.MAX_REPAIR_ROUNDS:
            break
        for index in {vertex for triangle in bad for vertex in triangle}:
            alpha[index] *= 0.78
    raise PatchError(
        f"{spec.node_name} UV wrap retained {len(bad)} folded/degenerate triangles"
    )


def _correlation(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (left[index] - left_mean) * (right[index] - right_mean)
        for index in range(len(left))
    )
    denominator = math.sqrt(
        sum((value - left_mean) ** 2 for value in left)
        * sum((value - right_mean) ** 2 for value in right)
    )
    if denominator <= 1.0e-12:
        raise PatchError("could not prove UV-to-shell correlation")
    return numerator / denominator


def _mapping_metrics(payload: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in previous.LODS:
        carrier = range(
            spec.carrier_vertex_start,
            spec.carrier_vertex_start + spec.carrier_vertex_count,
        )
        points = [previous._decode_position(payload, spec, index) for index in carrier]
        u_values = [previous._uv(payload, spec, index)[0] for index in carrier]
        outward_dots: list[float] = []
        for index, point in zip(carrier, points):
            offset = spec.stream_start + index * previous.STRIDE + 8
            normal = previous._unit(previous._decode_vec3(payload, offset))
            radial = (
                point[0],
                point[1] - spec.center[1],
                point[2] - spec.center[2],
            )
            outward_dots.append(previous._dot(normal, radial))
        rows.append({
            "minimum_absolute_x": min(abs(point[0]) for point in points),
            "minimum_outward_normal_dot": min(outward_dots),
            "minimum_z": min(point[2] for point in points),
            "node_name": spec.node_name,
            "u_to_z_correlation": _correlation(u_values, [point[2] for point in points]),
        })
    return rows


def build_patch(source_0a: Path) -> previous.BuiltPatch:
    built = previous.build_patch(
        source_0a, geometry_builder=_uv_wrap_geometry,
    )
    built.metrics["mapping_contract"] = {
        "bottom_y": BOTTOM_Y,
        "front_ramp_end": FRONT_RAMP_END,
        "front_ramp_start": FRONT_RAMP_START,
        "front_z": FRONT_Z,
        "mapping": "preserved_logo_uv_to_front_crown_seam_and_rear_outer_shell",
        "max_side_x": MAX_SIDE_X,
        "min_side_x": MIN_SIDE_X,
        "outer_shell_faces_only": True,
        "outward_surface_bias_units": OUTWARD_BIAS,
        "rear_taper": REAR_TAPER,
        "rear_taper_start": REAR_TAPER_START,
        "rear_z": REAR_Z,
        "top_y": TOP_Y,
    }
    built.metrics["mapping_proof"] = _mapping_metrics(built.output_system)
    return built


def _receipt(
    built: previous.BuiltPatch,
    **kwargs: Any,
) -> dict[str, Any]:
    document = previous._receipt(built, **kwargs)
    document["schema"] = SCHEMA
    document["operation"] = OPERATION
    document["preservation"]["outer_shell_faces_only"] = True
    document["preservation"]["outward_surface_bias_units"] = OUTWARD_BIAS
    document["target"]["mapping"] = (
        "preserved logo UV, front crown seam through rear outer shell"
    )
    return document


def publish(
    source_0a: Path,
    output_0a: Path,
    receipt_path: Path | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    return previous.publish(
        source_0a,
        output_0a,
        receipt_path,
        build_fn=build_patch,
        receipt_fn=_receipt,
        receipt_suffix=RECEIPT_SUFFIX,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        output, receipt, document = publish(args.source, args.output, args.receipt)
    except (OSError, PatchError) as exc:
        parser.exit(2, f"crest-carrier UV wrap failed: {exc}\n")
    print(json.dumps({
        "output": str(output),
        "output_sha256": document["result"]["output_volume_sha256"],
        "outer_entry_sha256": document["result"]["outer_entry_sha256"],
        "receipt": str(receipt),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
