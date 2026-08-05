#!/usr/bin/env python3
"""Independently verify the private APF dual-LOD crest-carrier expansion."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_shell_material_route_verify as common  # noqa: E402


PATCH_SCHEMA = "apf2k8_helmet_crest_carrier_expand_patch/v1"
VERIFY_SCHEMA = "apf2k8_helmet_crest_carrier_expand_verify/v1"
OPERATION = "expand_helmet_hi_and_lo_draw_2_crest_carrier"
OUTPUT_OUTER_SHA256 = "dd3332fdb007bc540110aef86baf5d31968b38fbdab294ae101a78c22dd642a6"
OUTPUT_SYSTEM_SHA256 = "47a50756d8a239964157d9bdaa53ae83d161069d6438d25440ab6f797da50a8f"
OUTPUT_VOLUME_SHA256 = "946e8b3222ead42922121b1c6c92f8e6531fdfc870f36edb649c779ddd06c8d2"
STRIDE = 32
MIN_AREA = 1.0e-4
MIN_WINDING = 1.0e-4

# node, draw table, index table/count, draw1 index/count and vertex window,
# draw2 index/count and vertex window, stream, vertex count, center, scale
LODS = (
    (0, "helmet_hi", 0x99C0, 0x9C30, 9773, 2623, 4800, 1312, 1427,
     7423, 1046, 2739, 326, 0xEA1C, 3856,
     (0.0, 4.927330017089844, 1.7508296966552734), (13.967263221740723,) * 3,
     536),
    (32, "helmet_lo", 0xCCA80, 0xCCCF0, 1552, 359, 659, 193, 283,
     1018, 231, 476, 128, 0xCDA9C, 799,
     (0.0, 2.8593978881835938, 2.8941473960876465), (16.119155883789062,) * 3,
     184),
)

VerifyError = common.VerifyError
require = common.require


def _dot(a: Iterable[float], b: Iterable[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(a[i] - b[i] for i in range(3))  # type: ignore[return-value]


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _length(a: tuple[float, float, float]) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: tuple[float, float, float]) -> tuple[float, float, float]:
    length = _length(a)
    require(math.isfinite(length) and length > 1.0e-12, "zero/non-finite vertex vector")
    return tuple(value / length for value in a)  # type: ignore[return-value]


def _snorm(word: int) -> float:
    return max(word / 32767.0, -1.0)


def _vec3(system: bytes, offset: int) -> tuple[float, float, float]:
    return tuple(_snorm(word) for word in struct.unpack_from(">3h", system, offset))  # type: ignore[return-value]


def _position(system: bytes, stream: int, vertex: int, center: tuple[float, ...], scale: tuple[float, ...]) -> tuple[float, float, float]:
    raw = _vec3(system, stream + vertex * STRIDE)
    return tuple(center[i] + raw[i] * scale[i] for i in range(3))  # type: ignore[return-value]


def _triangles(indices: list[int]) -> list[tuple[int, int, int]]:
    output: list[tuple[int, int, int]] = []
    strip: list[int] = []
    for index in indices:
        if index == 0xFFFF:
            strip.clear()
            continue
        strip.append(index)
        if len(strip) >= 3:
            number = len(strip) - 3
            a, b, c = strip[-3:]
            if number & 1:
                a, b = b, a
            if len({a, b, c}) == 3:
                output.append((a, b, c))
    return output


def _authorized_and_preserved() -> tuple[set[int], set[int]]:
    allowed: set[int] = set()
    preserved: set[int] = set()
    for row in LODS:
        stream, start, count = row[13], row[11], row[12]
        for vertex in range(start, start + count):
            offset = stream + vertex * STRIDE
            for begin, end in ((0, 6), (8, 14), (16, 22)):
                allowed.update(range(offset + begin, offset + end))
            for begin, end in ((6, 8), (14, 16), (22, 32)):
                preserved.update(range(offset + begin, offset + end))
    return allowed, preserved


def _geometry_proof(source: bytes, output: bytes) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    changed = {i for i, pair in enumerate(zip(source, output)) if pair[0] != pair[1]}
    allowed, preserved = _authorized_and_preserved()
    require(len(source) == len(output), "SCNE lengths differ")
    require(bool(changed) and changed <= allowed, "SCNE diff escapes carrier xyz lanes")
    require(not changed & preserved, "logo UV, W, or blend bytes changed")
    for row in LODS:
        (node_index, name, draw, index_offset, index_count, shell_i, shell_ic,
         shell_v, shell_vc, carrier_i, carrier_ic, carrier_v, carrier_vc,
         stream, vertex_count, center, scale, expected_triangles) = row
        require(struct.unpack_from(">5I", source, draw + 0x30 + 4)[:2] == (shell_i, shell_ic), f"{name} shell index draw drift")
        require(struct.unpack_from(">2I", source, draw + 0x30 + 20) == (shell_v, shell_vc), f"{name} shell vertex draw drift")
        require(struct.unpack_from(">5I", source, draw + 0x60 + 4)[:2] == (carrier_i, carrier_ic), f"{name} carrier index draw drift")
        require(struct.unpack_from(">2I", source, draw + 0x60 + 20) == (carrier_v, carrier_vc), f"{name} carrier vertex draw drift")
        require(source[draw : draw + 3 * 0x30] == output[draw : draw + 3 * 0x30], f"{name} draw records changed")
        require(source[index_offset : index_offset + index_count * 2] == output[index_offset : index_offset + index_count * 2], f"{name} indices changed")
        indices = list(struct.unpack_from(f">{index_count}H", output, index_offset))
        triangles = _triangles(indices[carrier_i : carrier_i + carrier_ic])
        require(len(triangles) == expected_triangles, f"{name} triangle count differs")
        points = {i: _position(output, stream, i, center, scale) for i in range(carrier_v, carrier_v + carrier_vc)}
        normals = {i: _unit(_vec3(output, stream + i * STRIDE + 8)) for i in points}
        minimum_area, minimum_winding = math.inf, math.inf
        for triangle in triangles:
            a, b, c = (points[index] for index in triangle)
            geometric = _cross(_sub(b, a), _sub(c, a))
            area = 0.5 * _length(geometric)
            average = _unit(tuple(sum(normals[index][axis] for index in triangle) for axis in range(3)))
            winding = _dot(geometric, average)
            minimum_area = min(minimum_area, area)
            minimum_winding = min(minimum_winding, winding)
        require(minimum_area > MIN_AREA, f"{name} has a degenerate triangle")
        require(minimum_winding > MIN_WINDING, f"{name} has a flipped triangle")
        for index in points:
            offset = stream + index * STRIDE
            tangent = _unit(_vec3(output, offset + 16))
            require(abs(_dot(normals[index], tangent)) <= 2.0e-3, f"{name} tangent is not orthogonal")
        rows.append({
            "carrier_triangle_count": len(triangles),
            "carrier_vertex_count": carrier_vc,
            "minimum_absolute_x": min(abs(point[0]) for point in points.values()),
            "minimum_position": [min(point[axis] for point in points.values()) for axis in range(3)],
            "maximum_position": [max(point[axis] for point in points.values()) for axis in range(3)],
            "minimum_triangle_area": minimum_area,
            "minimum_winding_dot": minimum_winding,
            "node_index": node_index,
            "node_name": name,
            "zero_degenerate_triangles": True,
            "zero_flipped_triangles": True,
        })
    return rows, len(changed)


def _validate_receipt(
    receipt: dict[str, Any],
    source_sha: str,
    output_sha: str,
    prefix: str,
    suffix: str,
    changed_count: int,
    *,
    patch_schema: str = PATCH_SCHEMA,
    operation: str = OPERATION,
    output_outer_sha256: str = OUTPUT_OUTER_SHA256,
    output_system_sha256: str = OUTPUT_SYSTEM_SHA256,
    output_volume_sha256: str = OUTPUT_VOLUME_SHA256,
) -> None:
    require(receipt.get("schema") == patch_schema, "receipt schema differs")
    require(receipt.get("operation") == operation, "receipt operation differs")
    source, result = receipt.get("source"), receipt.get("result")
    preservation, claims, metrics = receipt.get("preservation"), receipt.get("claim_flags"), receipt.get("metrics")
    require(all(isinstance(value, dict) for value in (source, result, preservation, claims, metrics)), "receipt sections missing")
    require(source.get("source_volume_sha256") == source_sha, "receipt source volume hash differs")
    require(source.get("outer_entry_sha256") == common.SOURCE_OUTER_SHA256, "receipt source outer hash differs")
    require(source.get("source_scne_sha256") == common.SOURCE_SYSTEM_SHA256, "receipt source SCNE hash differs")
    require(result.get("output_volume_sha256") == output_sha == output_volume_sha256, "receipt output volume hash differs")
    require(result.get("outer_entry_sha256") == output_outer_sha256, "receipt output outer hash differs")
    require(result.get("output_scne_sha256") == output_system_sha256, "receipt output SCNE hash differs")
    require(preservation.get("outside_outer_1310_prefix_sha256") == prefix, "receipt prefix hash differs")
    require(preservation.get("outside_outer_1310_suffix_sha256") == suffix, "receipt suffix hash differs")
    require(preservation.get("logo_uv_w_lanes_exact") is True and preservation.get("blend_lanes_exact") is True, "receipt preservation boundary differs")
    require(metrics.get("changed_byte_count") == changed_count, "receipt changed-byte count differs")
    require(claims.get("private_diagnostic_only") is True and claims.get("visual_eagles_match_proved") is False, "receipt claim boundary differs")


def verify_candidate(
    source_path: Path,
    output_path: Path,
    receipt_path: Path,
    *,
    patch_schema: str,
    verify_schema: str,
    operation: str,
    output_outer_sha256: str,
    output_system_sha256: str,
    output_volume_sha256: str,
) -> dict[str, Any]:
    source_meta, source_directory, source_raw = common._read_volume(source_path, "source 0A")
    output_meta, output_directory, output_raw = common._read_volume(output_path, "output 0A")
    receipt_meta = common._regular(receipt_path, "writer receipt")
    require(len({(source_meta.st_dev, source_meta.st_ino), (output_meta.st_dev, output_meta.st_ino), (receipt_meta.st_dev, receipt_meta.st_ino)}) == 3, "source/output/receipt alias")
    require(source_directory == output_directory, "outer directory changed")
    source = common._parse_entry(source_raw, common.SOURCE_OUTER_SHA256, "source")
    output = common._parse_entry(output_raw, output_outer_sha256, "output")
    require(common.sha256_bytes(source.system) == common.SOURCE_SYSTEM_SHA256, "source SCNE hash differs")
    require(common.sha256_bytes(output.system) == output_system_sha256, "output SCNE hash differs")
    geometry, changed_count = _geometry_proof(source.system, output.system)
    require(source.blocks[1:] == output.blocks[1:], "decoded sibling blocks changed")
    require(source.stored[1:] == output.stored[1:], "stored sibling blocks changed")
    prefix = common._hash_range(source_path, 0, common.OUTER_OFFSET)
    suffix_offset = common.OUTER_OFFSET + common.OUTER_SIZE
    suffix = common._hash_range(source_path, suffix_offset, common.VOLUME_SIZE - suffix_offset)
    require(prefix == common._hash_range(output_path, 0, common.OUTER_OFFSET), "volume prefix changed")
    require(suffix == common._hash_range(output_path, suffix_offset, common.VOLUME_SIZE - suffix_offset), "volume suffix changed")
    source_sha, output_sha = common._hash_file(source_path), common._hash_file(output_path)
    receipt = common._strict_receipt(receipt_path)
    _validate_receipt(
        receipt, source_sha, output_sha, prefix, suffix, changed_count,
        patch_schema=patch_schema,
        operation=operation,
        output_outer_sha256=output_outer_sha256,
        output_system_sha256=output_system_sha256,
        output_volume_sha256=output_volume_sha256,
    )
    return {
        "geometry": geometry,
        "output": {"outer_entry_sha256": output_outer_sha256, "scne_sha256": output_system_sha256, "volume_sha256": output_sha},
        "proof": {"changed_scne_byte_count": changed_count, "logo_uv_w_and_blend_exact": True, "sibling_blocks_exact": True, "whole_volume_outside_outer_1310_exact": True},
        "schema": verify_schema,
        "verified": True,
    }


def verify(source_path: Path, output_path: Path, receipt_path: Path) -> dict[str, Any]:
    return verify_candidate(
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = verify(args.source, args.output, args.receipt)
    except (OSError, VerifyError) as exc:
        parser.exit(2, f"crest-carrier verification failed: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
