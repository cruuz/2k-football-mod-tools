#!/usr/bin/env python3
"""Independently verify the pinned APF dual-LOD UV crest-wrap witness."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_carrier_expand_verify as prior  # noqa: E402


PATCH_SCHEMA = "apf2k8_helmet_crest_carrier_uv_wrap_patch/v1"
VERIFY_SCHEMA = "apf2k8_helmet_crest_carrier_uv_wrap_verify/v1"
OPERATION = "uv_wrap_helmet_hi_and_lo_draw_2_crest_carrier"
OUTPUT_OUTER_SHA256 = "4cc6dc169b862aee08c4429735d9daadf81e65df4bb01ac807975b72b2869b08"
OUTPUT_SYSTEM_SHA256 = "828adba0f31eeafa769d538628f98bf7eaffff745084b2d707a0ac1949c81939"
OUTPUT_VOLUME_SHA256 = "a5999b863b54b8f552555cbe5ecc87633636c19f6b7d4e56e7b88b5f54f8f718"
OUTWARD_BIAS = 0.045
MIN_CLEARANCE = 0.044
MAX_CLEARANCE = 0.046

VerifyError = prior.VerifyError
require = prior.require


def _add(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return tuple(left[index] + right[index] for index in range(3))  # type: ignore[return-value]


def _mul(
    value: tuple[float, float, float], scalar: float,
) -> tuple[float, float, float]:
    return tuple(component * scalar for component in value)  # type: ignore[return-value]


def _closest_point(
    point: tuple[float, float, float],
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Closest triangle point, implemented independently from the writer."""

    ab, ac, ap = prior._sub(b, a), prior._sub(c, a), prior._sub(point, a)
    d1, d2 = prior._dot(ab, ap), prior._dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a
    bp = prior._sub(point, b)
    d3, d4 = prior._dot(ab, bp), prior._dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        value = d1 / (d1 - d3)
        return _add(a, _mul(ab, value))
    cp = prior._sub(point, c)
    d5, d6 = prior._dot(ab, cp), prior._dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        value = d2 / (d2 - d6)
        return _add(a, _mul(ac, value))
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and d4 - d3 >= 0.0 and d5 - d6 >= 0.0:
        value = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return _add(b, _mul(prior._sub(c, b), value))
    denominator = 1.0 / (va + vb + vc)
    v, w = vb * denominator, vc * denominator
    return _add(a, _add(_mul(ab, v), _mul(ac, w)))


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
    require(denominator > 1.0e-12, "UV-to-shell correlation collapsed")
    return numerator / denominator


def _uv(system: bytes, stream: int, vertex: int) -> tuple[float, float]:
    offset = stream + vertex * prior.STRIDE
    return (
        2.0 * prior._snorm(struct.unpack_from(">h", system, offset + 14)[0]),
        2.0 * prior._snorm(struct.unpack_from(">h", system, offset + 22)[0]),
    )


def _mapping_proof(source: bytes, output: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in prior.LODS:
        (
            _node_index, name, _draw, index_offset, index_count,
            shell_index_start, shell_index_count, _shell_vertex_start,
            _shell_vertex_count, _carrier_index_start, _carrier_index_count,
            carrier_vertex_start, carrier_vertex_count, stream, vertex_count,
            center, scale, _expected_triangles,
        ) = row
        indices = list(struct.unpack_from(f">{index_count}H", source, index_offset))
        shell_triangles = prior._triangles(
            indices[shell_index_start : shell_index_start + shell_index_count]
        )
        source_points = [
            prior._position(source, stream, index, center, scale)
            for index in range(vertex_count)
        ]
        source_normals = [
            prior._unit(prior._vec3(source, stream + index * prior.STRIDE + 8))
            for index in range(vertex_count)
        ]
        outer_triangles: list[tuple[int, int, int]] = []
        for triangle in shell_triangles:
            triangle_center = tuple(
                sum(source_points[index][axis] for index in triangle) / 3.0
                for axis in range(3)
            )
            average_normal = tuple(
                sum(source_normals[index][axis] for index in triangle)
                for axis in range(3)
            )
            radial = (
                triangle_center[0],
                triangle_center[1] - center[1],
                triangle_center[2] - center[2],
            )
            if prior._dot(average_normal, radial) > 0.0:
                outer_triangles.append(triangle)
        require(bool(outer_triangles), f"{name} has no independently found outer shell")

        points: list[tuple[float, float, float]] = []
        u_values: list[float] = []
        outward_dots: list[float] = []
        clearances: list[float] = []
        for index in range(
            carrier_vertex_start, carrier_vertex_start + carrier_vertex_count,
        ):
            offset = stream + index * prior.STRIDE
            point = prior._position(output, stream, index, center, scale)
            normal = prior._unit(prior._vec3(output, offset + 8))
            radial = (
                point[0], point[1] - center[1], point[2] - center[2],
            )
            side = 1 if struct.unpack_from(">h", output, offset + 6)[0] > 0 else -1
            distance = math.inf
            for triangle in outer_triangles:
                if not all(source_points[item][0] * side >= -1.0e-6 for item in triangle):
                    continue
                shell_point = _closest_point(
                    point,
                    source_points[triangle[0]],
                    source_points[triangle[1]],
                    source_points[triangle[2]],
                )
                distance = min(distance, prior._length(prior._sub(point, shell_point)))
            require(math.isfinite(distance), f"{name} carrier has no same-side shell point")
            points.append(point)
            u_values.append(_uv(output, stream, index)[0])
            outward_dots.append(prior._dot(normal, radial))
            clearances.append(distance)

        correlation = _correlation(u_values, [point[2] for point in points])
        minimum_x = min(abs(point[0]) for point in points)
        minimum_z = min(point[2] for point in points)
        require(correlation < -0.98, f"{name} is not a front-to-rear UV wrap")
        require(minimum_z < -9.0, f"{name} does not reach the rear shell")
        require(minimum_x < (0.001 if name == "helmet_hi" else 0.2), f"{name} does not reach the crown seam")
        require(min(outward_dots) > 4.0, f"{name} contains inward carrier normals")
        require(min(clearances) >= MIN_CLEARANCE, f"{name} carrier is buried in the shell")
        require(max(clearances) <= MAX_CLEARANCE, f"{name} carrier bias is excessive")
        rows.append({
            "maximum_outer_shell_clearance": max(clearances),
            "minimum_absolute_x": minimum_x,
            "minimum_outward_normal_dot": min(outward_dots),
            "minimum_outer_shell_clearance": min(clearances),
            "minimum_z": minimum_z,
            "node_name": name,
            "u_to_z_correlation": correlation,
        })
    return rows


def _receipt_contract(receipt: dict[str, Any], mapping: list[dict[str, Any]]) -> None:
    metrics = receipt.get("metrics")
    preservation = receipt.get("preservation")
    require(isinstance(metrics, dict) and isinstance(preservation, dict), "receipt contract sections missing")
    contract = metrics.get("mapping_contract")
    writer_proof = metrics.get("mapping_proof")
    require(isinstance(contract, dict) and isinstance(writer_proof, list), "receipt mapping contract missing")
    require(contract.get("mapping") == "preserved_logo_uv_to_front_crown_seam_and_rear_outer_shell", "receipt mapping identity differs")
    require(contract.get("outer_shell_faces_only") is True, "receipt outer-shell guard differs")
    require(contract.get("outward_surface_bias_units") == OUTWARD_BIAS, "receipt carrier bias differs")
    require(preservation.get("outer_shell_faces_only") is True, "receipt outer-shell preservation differs")
    require(preservation.get("outward_surface_bias_units") == OUTWARD_BIAS, "receipt outward bias differs")
    require(len(writer_proof) == len(mapping), "receipt mapping proof count differs")
    for written, proved in zip(writer_proof, mapping):
        require(written.get("node_name") == proved["node_name"], "receipt mapping node differs")
        for key in ("minimum_absolute_x", "minimum_outward_normal_dot", "minimum_z", "u_to_z_correlation"):
            require(math.isclose(written.get(key), proved[key], rel_tol=0.0, abs_tol=1.0e-12), f"receipt {key} differs")


def verify(source_path: Path, output_path: Path, receipt_path: Path) -> dict[str, Any]:
    report = prior.verify_candidate(
        source_path,
        output_path,
        receipt_path,
        patch_schema=PATCH_SCHEMA,
        verify_schema=VERIFY_SCHEMA,
        operation=OPERATION,
        output_outer_sha256=OUTPUT_OUTER_SHA256,
        output_system_sha256=OUTPUT_SYSTEM_SHA256,
        output_volume_sha256=OUTPUT_VOLUME_SHA256,
    )
    _, _, source_raw = prior.common._read_volume(source_path, "source 0A")
    _, _, output_raw = prior.common._read_volume(output_path, "output 0A")
    source = prior.common._parse_entry(source_raw, prior.common.SOURCE_OUTER_SHA256, "source")
    output = prior.common._parse_entry(output_raw, OUTPUT_OUTER_SHA256, "output")
    mapping = _mapping_proof(source.system, output.system)
    receipt = prior.common._strict_receipt(receipt_path)
    _receipt_contract(receipt, mapping)
    report["mapping"] = mapping
    report["proof"]["front_crown_seam_to_rear_outer_shell"] = True
    report["proof"]["quantized_outward_bias"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = verify(args.source, args.output, args.receipt)
    except (OSError, VerifyError) as exc:
        parser.exit(2, f"crest-carrier UV-wrap verification failed: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
