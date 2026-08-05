#!/usr/bin/env python3
"""Build and render a source-bound static visual proof of the exact APF v18 helmet.

This is deliberately not an emulator proof.  It decodes the real ``helmet_00``
SCNE from outer entry 1310, splits its high-detail draw records without joining
triangle strips across draw boundaries, and extracts the hidden crest UV lanes
from draw 2.  It also decodes catalog 30 from both the real ``uniform_logo_30``
package and ``uniform_logocache`` and requires those copies to agree exactly.

``render`` invokes Blender in background/factory mode with DISPLAY and Wayland
variables removed.  The companion Blender script receives only the extracted,
hash-accounted geometry and textures.  It never opens or mutates the game.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_custom_team_appearance_patch as appearance  # noqa: E402
import apf_inner  # noqa: E402
import apf_logocache_patch as logocache  # noqa: E402
import apf_logo_patch as logo  # noqa: E402
import apf_outer  # noqa: E402
import apf_scene  # noqa: E402
from nfl_txtr import encode_rgba_png  # noqa: E402


SCHEMA = "apf2k8_exact_helmet_static_visual_proof/v2"
RENDER_SCHEMA = "apf2k8_exact_helmet_static_visual_render/v2"

# This tool is intentionally an exact final-v18 editor-build witness, not a
# generic renderer.
EXPECTED_VOLUME_SHA256 = "ae573cdd448fdd1235e18e37f2be5e5ab6725828277728b13b050fd492626a69"
EXPECTED_BUILD_MANIFEST_SHA256 = "88d47f10b9dbf1834eca9a6c66f3fa16de9457a47343fe8488aaafc71d7c6e32"
EXPECTED_HELMET_OUTER_SHA256 = "dc9ff1f357827244887844b6ab91ef366fe8926af7fe6b245745668c252aee2f"
EXPECTED_SCNE_SHA256 = "d90084476ca9ee83d667ec7c6d0ef65713a75510639fa00208a8abd74d45e1ee"
EXPECTED_PACKAGE_SHA256 = "19145f595c85be20456db4768b712c2734405785f61be3884b9363ce62bbd8b0"
EXPECTED_CACHE_DIRECTORY_SHA256 = "208ee667e003e4860abac8c53b73e09965565418913e2ff7a29f97bbc422379b"
EXPECTED_CACHE_PAYLOAD_SHA256 = "f32af34968102aae9ffb4800992abda19fc9c4f748f7adc48fcdb986f473e93d"
EXPECTED_APPEARANCE_ENTRY_SHA256 = "a63242bcd1e29745217116e1f42370863e82e0a84cda6491f117e64dc54e0b43"
EXPECTED_BASE_SHA256 = "7bde6fa51bdbc99974e5592c99d3d67634bd43e0345f2d7298e2a9ae0c141b26"
EXPECTED_RGBA_SHA256 = "ba0bdd53ae43f28dd49af66e40c5f51de7ed679bf9b7dac4460589624e9ad96a"
EXPECTED_MATERIAL_RGBA_SHA256 = "66731dd78ce3ddf43061573506addfd804e01f950280b13149a1f1689958eece"
EXPECTED_MASK_PNG_SHA256 = "bbebf7171a90ba2847b1a6c5647d78fa589ad7390c31380313ed431f6f8cf516"
EXPECTED_MATERIAL_PNG_SHA256 = "35e06e0f009c31cb1e27cab126f072d67e12d6b3efc9ff4032091075640573f8"
EXPECTED_L0_MIP_SHA256 = "8f213d76a2a8486c2e6310298ec382a54e049ced65c3ed18d54460bef49ee855"
EXPECTED_L1_MIP_SHA256 = "1282ce64c47845bc18ad6a34b945ec3f117fd6c4860ea5a717dd27355cc36152"

HELMET_OUTER_INDEX = 1310
HELMET_INNER_INDEX = 128
PACKAGE_OUTER_INDEX = 1133
APPEARANCE_OUTER_INDEX = 1126
HELMET_NODE_INDEX = 0
VISOR_NODE_INDEX = 1
FACEMASK_NODE_INDEX = 2  # one stock cage for orientation/context only
SCNE_MAX = 64 * 1024 * 1024
STRIDE = 32

# Exact high-LOD layout inside the pinned SCNE.
INDEX_OFFSET = 0x00009C30
INDEX_COUNT = 9773
STREAM_START = 0x0000EA1C
VERTEX_COUNT = 3856
POSITION_CENTER = (0.0, 4.927330017089844, 1.7508296966552734)
POSITION_SCALE = (13.967263221740723,) * 3
SHELL_DRAW = 1
CREST_DRAW = 2
EXPECTED_DRAW_COUNT = 13
EXPECTED_SHELL_TRIANGLES = 2464
EXPECTED_CREST_TRIANGLES = 536
EXPECTED_CREST_VERTICES = 326
EXPECTED_CREST_SIDE_TRIANGLES = 268
EXPECTED_CREST_SIDE_VERTICES = 163
EXPECTED_CREST_SIDE_ZERO_VERTICES = 3

VIEW_NAMES = ("side-right", "side-left", "crown", "rear")
DEBUG_VIEW_NAMES = (
    "debug-carrier-material",
    "debug-carrier-uv",
    "debug-carrier-material-roll90",
    "debug-camera-axes",
)


class ProofError(ValueError):
    """The exact-v18 source or generated proof left its bounded contract."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProofError(message)


def _regular_input(path: Path, label: str) -> Path:
    path = Path(path)
    _require(path.is_file(), f"{label} is not a readable file: {path}")
    return path


def _snorm(word: int) -> float:
    return max(word / 32767.0, -1.0)


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(value * value for value in vector))
    _require(math.isfinite(length) and length > 1.0e-12, "zero/non-finite source normal")
    return tuple(value / length for value in vector)  # type: ignore[return-value]


def _position(system: bytes, vertex: int) -> tuple[float, float, float]:
    words = struct.unpack_from(">3h", system, STREAM_START + vertex * STRIDE)
    return tuple(
        POSITION_CENTER[axis] + _snorm(words[axis]) * POSITION_SCALE[axis]
        for axis in range(3)
    )  # type: ignore[return-value]


def _normal(system: bytes, vertex: int) -> tuple[float, float, float]:
    words = struct.unpack_from(">3h", system, STREAM_START + vertex * STRIDE + 8)
    return _unit(tuple(_snorm(word) for word in words))  # type: ignore[arg-type]


def _crest_uv(system: bytes, vertex: int) -> tuple[float, float]:
    at = STREAM_START + vertex * STRIDE
    # APF stores U/V in NORMAL0.w and TANGENT0.w as 2*SNORM.
    return (
        2.0 * _snorm(struct.unpack_from(">h", system, at + 14)[0]),
        2.0 * _snorm(struct.unpack_from(">h", system, at + 22)[0]),
    )


def expand_triangle_strip(indices: Iterable[int]) -> list[tuple[int, int, int]]:
    """Expand one source draw's D3D strip, respecting restart and parity."""

    triangles: list[tuple[int, int, int]] = []
    strip: list[int] = []
    for value in indices:
        if value == 0xFFFF:
            strip.clear()
            continue
        strip.append(value)
        if len(strip) < 3:
            continue
        number = len(strip) - 3
        a, b, c = strip[-3:]
        if number & 1:
            a, b = b, a
        if len({a, b, c}) == 3:
            triangles.append((a, b, c))
    return triangles


def compact_mesh(
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
    uvs: dict[int, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    used = sorted({vertex for triangle in triangles for vertex in triangle})
    _require(bool(used), "source draw has no non-degenerate triangles")
    _require(used[-1] < len(positions), "source draw index exceeds its vertex stream")
    remap = {source: output for output, source in enumerate(used)}
    result: dict[str, Any] = {
        "positions_cm": [list(positions[index]) for index in used],
        "normals": [list(normals[index]) for index in used],
        "triangles": [[remap[index] for index in triangle] for triangle in triangles],
        "source_vertex_indices": used,
    }
    if uvs is not None:
        _require(set(used) <= set(uvs), "crest draw contains a vertex without source UV")
        result["uv_d3d"] = [list(uvs[index]) for index in used]
        # D3D display images use a top-left origin; Blender UV images use bottom-left.
        result["uv_blender"] = [[uvs[index][0], 1.0 - uvs[index][1]] for index in used]
    return result


def colorize_region_mask(
    rgba: bytes,
    silver_argb: int,
    white_argb: int,
) -> bytes:
    """Make a review texture from APF's exact flat R/G region mask.

    The staged Eagles design previews establish red as silver and green as the
    dominant white feather region.  Black is unpainted shell.  The corresponding
    appearance palette slots are 0 and 2; slot 1 is the dark uniform region and
    must not replace the white feather channel.  This function is intentionally
    strict: any blue, mixed, or non-flat region fails rather than inventing a
    shader blend.
    """

    _require(len(rgba) == 512 * 512 * 4, "crest mask is not 512x512 RGBA")

    def rgb(argb: int) -> bytes:
        return bytes(((argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF))

    silver = rgb(silver_argb)
    white = rgb(white_argb)
    output = bytearray(len(rgba))
    for offset in range(0, len(rgba), 4):
        red, green, blue, _alpha = rgba[offset : offset + 4]
        if (red, green, blue) == (0, 0, 0):
            output[offset : offset + 4] = b"\0\0\0\0"
        elif (red, green, blue) == (255, 0, 0):
            output[offset : offset + 4] = silver + b"\xff"
        elif (red, green, blue) == (0, 255, 0):
            output[offset : offset + 4] = white + b"\xff"
        else:
            raise ProofError(
                "v18 crest is not the expected flat black/red/green APF region mask"
            )
    return bytes(output)


def colorize_weighted_region_mask(
    rgba: bytes,
    shell_argb: int,
    silver_argb: int,
    white_argb: int,
) -> bytes:
    """Reproduce the recovered crest shader's weighted palette equation.

    The final clean Eagles mask uses exact decoded Xenos 4:4:4:4 weights: red
    selects silver, green selects white, and the unused coverage is helmet
    shell.  Blue is unused.  This compositor is intentionally integer and
    independently rechecks the complete transport lattice before publishing a
    fully opaque review material.
    """

    _require(len(rgba) == 512 * 512 * 4, "weighted crest mask is not 512x512 RGBA")

    def rgb(argb: int) -> tuple[int, int, int]:
        return ((argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF)

    shell = rgb(shell_argb)
    silver = rgb(silver_argb)
    white = rgb(white_argb)
    output = bytearray(len(rgba))
    for offset in range(0, len(rgba), 4):
        red, green, blue, alpha = rgba[offset : offset + 4]
        _require(blue == 0 and alpha == 136,
                 "weighted crest mask differs from zero-blue/alpha136 transport")
        _require(red % 17 == 0 and green % 17 == 0,
                 "weighted crest mask is outside the Xenos 4-bit channel lattice")
        _require(red + green <= 255,
                 "weighted crest mask exceeds one palette coverage unit")
        residual = 255 - red - green
        for channel in range(3):
            output[offset + channel] = (
                shell[channel] * residual
                + silver[channel] * red
                + white[channel] * green
                + 127
            ) // 255
        output[offset + 3] = 255
    return bytes(output)


def uv_diagnostic_rgba() -> bytes:
    """Opaque deterministic U/V grid; this is a diagnostic, never game art."""

    output = bytearray(512 * 512 * 4)
    for y in range(512):
        for x in range(512):
            offset = (y * 512 + x) * 4
            color = (x * 255 // 511, y * 255 // 511, 72, 255)
            if x in range(252, 260):
                color = (255, 255, 255, 255)  # vertical U midpoint
            if y in range(252, 260):
                color = (0, 0, 0, 255)  # horizontal V midpoint
            if x < 6 or x >= 506 or y < 6 or y >= 506:
                color = (255, 196, 0, 255)
            output[offset : offset + 4] = bytes(color)
    return bytes(output)


def _bounds(points: Iterable[Iterable[float]]) -> dict[str, list[float]]:
    values = [tuple(point) for point in points]
    return {
        "minimum": [min(point[axis] for point in values) for axis in range(3)],
        "maximum": [max(point[axis] for point in values) for axis in range(3)],
    }


def _correlation(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    _require(denominator > 1.0e-12, "carrier coordinate correlation collapsed")
    return numerator / denominator


def _carrier_axis_proof(carrier: dict[str, Any]) -> dict[str, Any]:
    points = carrier["positions_cm"]
    uvs = carrier["uv_d3d"]
    result: dict[str, Any] = {}
    for label, side in (("left", -1), ("right", 1)):
        selected = [index for index, point in enumerate(points) if point[0] * side > 0]
        result[label] = {
            "vertex_count_excluding_seam": len(selected),
            "u_to_z_correlation": _correlation(
                [uvs[index][0] for index in selected],
                [points[index][2] for index in selected],
            ),
            "v_to_y_correlation": _correlation(
                [uvs[index][1] for index in selected],
                [points[index][1] for index in selected],
            ),
        }
    return result


def _carrier_component_contract(carrier: dict[str, Any]) -> dict[str, Any]:
    """Prove draw 2 is exactly two disconnected signed-side islands.

    Each island owns one distinct x=0 seam vertex.  A triangle is assigned by
    its nonzero x coordinates; a triangle that crosses x=0 or has no signed
    vertex is rejected.  This is also the contract used by Blender to keep the
    hidden far-side carrier out of side-specific diagnostic renders.
    """

    points = carrier["positions_cm"]
    triangles = carrier["triangles"]
    sides: dict[str, dict[str, Any]] = {
        "left": {"indices": set(), "triangles": []},
        "right": {"indices": set(), "triangles": []},
    }
    for triangle in triangles:
        x_values = [points[index][0] for index in triangle]
        has_negative = any(value < 0.0 for value in x_values)
        has_positive = any(value > 0.0 for value in x_values)
        _require(not (has_negative and has_positive),
                 "crest carrier triangle crosses the x=0 side boundary")
        _require(has_negative or has_positive,
                 "crest carrier triangle has no signed x coordinate")
        label = "right" if has_positive else "left"
        sides[label]["triangles"].append(triangle)
        sides[label]["indices"].update(triangle)

    _require(
        sides["left"]["indices"].isdisjoint(sides["right"]["indices"]),
        "crest carrier side islands share a source vertex",
    )
    _require(
        sides["left"]["indices"] | sides["right"]["indices"] == set(range(len(points))),
        "crest carrier split does not cover every source vertex",
    )
    output: dict[str, Any] = {}
    for label, sign in (("left", -1), ("right", 1)):
        indices = sides[label]["indices"]
        side_triangles = sides[label]["triangles"]
        zero_count = sum(points[index][0] == 0.0 for index in indices)
        _require(len(indices) == EXPECTED_CREST_SIDE_VERTICES,
                 f"crest carrier {label} vertex count differs")
        _require(len(side_triangles) == EXPECTED_CREST_SIDE_TRIANGLES,
                 f"crest carrier {label} triangle count differs")
        _require(zero_count == EXPECTED_CREST_SIDE_ZERO_VERTICES,
                 f"crest carrier {label} x=0 seam vertex count differs")
        _require(
            all(points[index][0] * sign >= 0.0 for index in indices),
            f"crest carrier {label} island contains the opposite x sign",
        )
        # A side is one connected mesh component, not several fragments that
        # merely happen to occupy the same signed half-space.
        adjacency = {index: set() for index in indices}
        for triangle in side_triangles:
            for index in triangle:
                adjacency[index].update(other for other in triangle if other != index)
        pending = [next(iter(indices))]
        visited: set[int] = set()
        while pending:
            index = pending.pop()
            if index in visited:
                continue
            visited.add(index)
            pending.extend(adjacency[index] - visited)
        _require(visited == indices, f"crest carrier {label} island is disconnected")
        output[label] = {
            "selection": (
                "x<0 topology island plus its distinct x=0 seam vertices"
                if label == "left"
                else "x>0 topology island plus its distinct x=0 seam vertices"
            ),
            "vertex_count": len(indices),
            "triangle_count": len(side_triangles),
            "x_zero_seam_vertex_count": zero_count,
            "connected_component_count": 1,
        }
    return {
        "contract": "signed_x_topology_islands_with_distinct_zero_seams_v2",
        "component_count": 2,
        "sides": output,
    }


def _project_carrier_side_right(carrier: dict[str, Any]) -> dict[str, Any]:
    camera = (0.72, 0.055, 0.018)
    target = (0.0, 0.045, 0.015)
    world_up = (0.0, 1.0, 0.0)

    def subtract(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
        return tuple(a[index] - b[index] for index in range(3))

    def dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def cross(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float]:
        return (a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0])

    def unit(value: tuple[float, ...]) -> tuple[float, ...]:
        length = math.sqrt(dot(value, value))
        return tuple(component / length for component in value)

    forward = unit(subtract(target, camera))
    right = unit(cross(forward, world_up))
    up = cross(right, forward)
    focal_pixels = 55.0 / 36.0 * 768.0
    projected: list[tuple[float, float]] = []
    for point_cm in carrier["positions_cm"]:
        if point_cm[0] <= 0.0:
            continue
        point = tuple(component * 0.01 for component in point_cm)
        delta = subtract(point, camera)
        depth = dot(delta, forward)
        _require(depth > 0.0, "carrier point is behind the side-right camera")
        projected.append((
            384.0 + focal_pixels * dot(delta, right) / depth,
            384.0 + focal_pixels * dot(delta, up) / depth,
        ))
    bounds = [
        min(point[0] for point in projected), min(point[1] for point in projected),
        max(point[0] for point in projected), max(point[1] for point in projected),
    ]
    return {
        "camera_contract": "lens55mm_side0.72m_crown_rear0.75m_v1",
        "selected_side": "x>0",
        "projected_vertex_count": len(projected),
        "projected_bbox_pixels": bounds,
        "projected_width_pixels": bounds[2] - bounds[0],
        "projected_height_pixels": bounds[3] - bounds[1],
    }


def _read_outer_raw(
    archive: apf_outer.Archive, reader: apf_inner.ArchiveReader, index: int,
) -> tuple[apf_outer.Entry, bytes]:
    try:
        entry = archive.entries[index]
    except IndexError as exc:
        raise ProofError(f"APF archive has no outer entry {index}") from exc
    return entry, reader.read(entry, 0, entry.size)


def _helmet_system(
    archive: apf_outer.Archive, reader: apf_inner.ArchiveReader,
) -> tuple[bytes, bytes, dict[str, Any]]:
    entry, raw = _read_outer_raw(archive, reader, HELMET_OUTER_INDEX)
    _require(_sha256_bytes(raw) == EXPECTED_HELMET_OUTER_SHA256,
             "v18 helmet outer 1310 hash differs")
    try:
        record = apf_inner.parse_iff(reader, entry)
        item = record.files[HELMET_INNER_INDEX]
        _require(item.name == "helmet_00" and item.type_name == "SCNE",
                 "outer 1310 inner 128 is no longer helmet_00/SCNE")
        _require(len(item.parts) >= 1, "helmet_00 has no system part")
        part = item.parts[0]
        block = apf_inner.decode_block(reader, record, part.block_index, SCNE_MAX)
        system = block[part.offset : part.offset + part.length]
    except (IndexError, apf_inner.FormatError) as exc:
        raise ProofError(f"could not decode exact helmet_00 SCNE: {exc}") from exc
    _require(_sha256_bytes(system) == EXPECTED_SCNE_SHA256, "v18 helmet SCNE hash differs")
    try:
        scene = apf_scene.parse_scene_system_part(
            system, outer_index=HELMET_OUTER_INDEX,
            inner_index=HELMET_INNER_INDEX, capture_geometry=True,
        )
    except apf_scene.SceneError as exc:
        raise ProofError(f"helmet SCNE parser rejected v18: {exc}") from exc
    _require(scene.get("root_name") == "helmet_00", "helmet SCNE root differs")
    _require(len(scene.get("nodes", [])) == 33, "helmet SCNE no longer has 33 nodes")
    hierarchy = scene["nodes"][0].get("hierarchy")
    records = hierarchy.get("records") if isinstance(hierarchy, dict) else None
    _require(
        isinstance(records, list) and records
        and records[0].get("name") == "helmet_hi_root"
        and records[0].get("parent") == -1
        and tuple(records[0].get("vector_a", ())) == (0.0, 0.0, 0.0, 1.0)
        and tuple(records[0].get("vector_b", ())) == (0.0, 0.0, 0.0, 1.0),
        "helmet_hi root hierarchy anchor is not identity-valued",
    )
    return raw, system, scene


def _node_mesh(scene: dict[str, Any], node_index: int, expected_name: str) -> dict[str, Any]:
    node = scene["nodes"][node_index]
    _require(node.get("name") == expected_name, f"helmet node {node_index} identity differs")
    meshes = node.get("meshes")
    _require(isinstance(meshes, list) and len(meshes) == 1, f"{expected_name} mesh differs")
    geometry = meshes[0].get("_geometry")
    _require(isinstance(geometry, dict), f"{expected_name} geometry is unavailable")
    return geometry


def _draw_rows(system: bytes, scene: dict[str, Any]) -> list[dict[str, int]]:
    node = scene["nodes"][HELMET_NODE_INDEX]
    _require(node.get("name") == "helmet_hi", "high-detail helmet node moved")
    _require(node.get("draw_record_count") == EXPECTED_DRAW_COUNT,
             "helmet_hi draw-record count differs")
    start = node.get("draw_record_offset")
    _require(type(start) is int, "helmet_hi draw-record pointer is unavailable")
    rows: list[dict[str, int]] = []
    for index in range(EXPECTED_DRAW_COUNT):
        words = struct.unpack_from(">12I", system, start + index * 0x30)
        _require(words[0] == 6, f"helmet_hi draw {index} primitive identity differs")
        rows.append({
            "draw": index,
            "index_start": words[1],
            "index_count": words[2],
            "vertex_start": words[5],
            "vertex_count": words[6],
            "material_index": words[8],
        })
    _require(rows[SHELL_DRAW] == {
        "draw": 1, "index_start": 2623, "index_count": 4800,
        "vertex_start": 1312, "vertex_count": 1427, "material_index": 1,
    }, "v18 exterior shell draw window differs")
    _require(rows[CREST_DRAW] == {
        "draw": 2, "index_start": 7423, "index_count": 1046,
        "vertex_start": 2739, "vertex_count": 326, "material_index": 2,
    }, "v18 crest-carrier draw window differs")
    return rows


def _all_geometry(system: bytes, scene: dict[str, Any]) -> dict[str, Any]:
    mesh = _node_mesh(scene, HELMET_NODE_INDEX, "helmet_hi")
    _require(len(mesh.get("positions", [])) == VERTEX_COUNT,
             "helmet_hi vertex count differs")
    _require(scene["nodes"][0].get("index_offset") == INDEX_OFFSET,
             "helmet_hi index pointer differs")
    indices = list(struct.unpack_from(f">{INDEX_COUNT}H", system, INDEX_OFFSET))
    positions = [_position(system, index) for index in range(VERTEX_COUNT)]
    normals = [_normal(system, index) for index in range(VERTEX_COUNT)]
    rows = _draw_rows(system, scene)
    groups: dict[str, Any] = {}
    for row in rows:
        window = indices[row["index_start"] : row["index_start"] + row["index_count"]]
        triangles = expand_triangle_strip(window)
        uvs = None
        if row["draw"] == CREST_DRAW:
            uvs = {
                index: _crest_uv(system, index)
                for index in range(row["vertex_start"], row["vertex_start"] + row["vertex_count"])
            }
        groups[f"helmet_hi_draw_{row['draw']:02d}"] = {
            "source": row,
            **compact_mesh(positions, normals, triangles, uvs),
        }
    _require(len(groups["helmet_hi_draw_01"]["triangles"]) == EXPECTED_SHELL_TRIANGLES,
             "v18 shell triangle count differs")
    carrier = groups["helmet_hi_draw_02"]
    _require(len(carrier["triangles"]) == EXPECTED_CREST_TRIANGLES,
             "v18 crest triangle count differs")
    _require(len(carrier["positions_cm"]) == EXPECTED_CREST_VERTICES,
             "v18 crest vertex count differs")

    # Exact visor and one exact stock cage provide orientation without claiming
    # that this static proof knows a gameplay player's selected facemask.
    for node_index, name in ((VISOR_NODE_INDEX, "visor_hi_grp"),
                             (FACEMASK_NODE_INDEX, "cage_01_grp")):
        node = scene["nodes"][node_index]
        geometry = _node_mesh(scene, node_index, name)
        node_positions = [tuple(item) for item in geometry["positions"]]
        node_triangles = expand_triangle_strip(geometry["indices"])
        # SCNE normals for these context meshes are not part of the current
        # semantic proof; Blender calculates review-only surface normals.
        placeholder = [(0.0, 1.0, 0.0)] * len(node_positions)
        groups[name] = {
            "source": {"node_index": node_index, "context_only": True},
            **compact_mesh(node_positions, placeholder, node_triangles),
        }
    return {"draw_records": rows, "groups": groups}


def _package_layers(
    archive: apf_outer.Archive, reader: apf_inner.ArchiveReader,
) -> tuple[bytes, dict[str, Any]]:
    entry, raw = _read_outer_raw(archive, reader, PACKAGE_OUTER_INDEX)
    _require(_sha256_bytes(raw) == EXPECTED_PACKAGE_SHA256,
             "v18 uniform_logo_30 package hash differs")
    try:
        record = apf_inner.parse_iff(reader, entry)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        found = {item.name: index for index, item in enumerate(record.files)}
        layers = {
            name: logo._extract_layer(record, blocks, found[name], name, None)
            for name in ("logo_l0", "logo_l1")
        }
    except (KeyError, apf_inner.FormatError, logo.PatchError) as exc:
        raise ProofError(f"could not decode v18 crest package: {exc}") from exc
    for name, layer in layers.items():
        expected_mip = EXPECTED_L0_MIP_SHA256 if name == "logo_l0" else EXPECTED_L1_MIP_SHA256
        _require(_sha256_bytes(layer.base) == EXPECTED_BASE_SHA256,
                 f"v18 {name} package base differs")
        _require(_sha256_bytes(layer.rgba) == EXPECTED_RGBA_SHA256,
                 f"v18 {name} package RGBA differs")
        _require(_sha256_bytes(layer.mip_tail) == expected_mip,
                 f"v18 {name} package mip tail differs")
    _require(layers["logo_l0"].rgba == layers["logo_l1"].rgba,
             "v18 package l0/l1 decoded crests differ")
    return layers["logo_l0"].rgba, {
        name: {
            "base_sha256": _sha256_bytes(layer.base),
            "decoded_rgba_sha256": _sha256_bytes(layer.rgba),
            "mip_tail_sha256": _sha256_bytes(layer.mip_tail),
        }
        for name, layer in layers.items()
    }


def _cache_layers(
    archive: apf_outer.Archive, reader: apf_inner.ArchiveReader,
) -> dict[str, Any]:
    dir_entry, dir_raw = _read_outer_raw(archive, reader, logocache.DIR_TABLE_INDEX)
    pay_entry, pay_raw = _read_outer_raw(archive, reader, logocache.PAYLOAD_TABLE_INDEX)
    _require(dir_entry.size == logocache.DIR_SIZE and pay_entry.size == logocache.PAYLOAD_SIZE,
             "v18 logo-cache allocations differ")
    _require(_sha256_bytes(dir_raw) == EXPECTED_CACHE_DIRECTORY_SHA256,
             "v18 logo-cache directory hash differs")
    _require(_sha256_bytes(pay_raw) == EXPECTED_CACHE_PAYLOAD_SHA256,
             "v18 logo-cache payload hash differs")
    try:
        directory = logocache.parse_cache_directory(dir_raw)
        layers = {
            name: logocache._extract_target(directory, pay_raw, f"30_{name}", None)
            for name in ("logo_l0", "logo_l1")
        }
    except logocache.PatchError as exc:
        raise ProofError(f"could not decode v18 logo cache: {exc}") from exc
    result: dict[str, Any] = {}
    for name, layer in layers.items():
        expected_mip = EXPECTED_L0_MIP_SHA256 if name == "logo_l0" else EXPECTED_L1_MIP_SHA256
        _require(_sha256_bytes(layer.base) == EXPECTED_BASE_SHA256,
                 f"v18 cached {name} base differs")
        _require(_sha256_bytes(layer.rgba) == EXPECTED_RGBA_SHA256,
                 f"v18 cached {name} RGBA differs")
        _require(_sha256_bytes(layer.mip_tail) == expected_mip,
                 f"v18 cached {name} mip tail differs")
        result[name] = {
            "base_sha256": _sha256_bytes(layer.base),
            "decoded_rgba_sha256": _sha256_bytes(layer.rgba),
            "mip_tail_sha256": _sha256_bytes(layer.mip_tail),
            "aggregate_slot": layer.entry.aggregate_slot,
        }
    return result


def _appearance(
    archive: apf_outer.Archive, reader: apf_inner.ArchiveReader, input_0a: Path,
) -> dict[str, Any]:
    _entry, raw = _read_outer_raw(archive, reader, APPEARANCE_OUTER_INDEX)
    _require(_sha256_bytes(raw) == EXPECTED_APPEARANCE_ENTRY_SHA256,
             "v18 custom-team appearance entry hash differs")
    try:
        rows = appearance.read_appearances(input_0a)
    except appearance.CustomTeamAppearanceError as exc:
        raise ProofError(f"could not decode v18 appearance: {exc}") from exc
    _require(len(rows) == 8 and tuple(row.slot for row in rows) == appearance.USER_SLOTS,
             "v18 appearance slot inventory differs")
    first = next(row for row in rows if row.slot == 32)
    _require(first.home == first.away, "v18 slot 32 HOME/AWAY banks differ")
    _require(first.home.palette == appearance.EAGLES_2017_PALETTE,
             "v18 slot 32 palette is not the staged Eagles palette")
    _require(first.home.logo_selector == bytes.fromhex("1E00010009000000"),
             "v18 slot 32 is not routed to catalog 30")
    _require(first.home.helmet_selector[1] == appearance.EAGLES_SHELL_PALETTE_INDEX,
             "v18 slot 32 does not select the Eagles shell color")
    return {
        "slots": [32],
        "home_away_identical_per_slot": True,
        "palette_argb": [f"{value:08X}" for value in first.home.palette],
        "helmet_selectors_by_slot": {
            "32": first.home.helmet_selector.hex().upper()
        },
        "logo_selector": first.home.logo_selector.hex().upper(),
        "shell_palette_index": first.home.helmet_selector[1],
        "shell_argb": f"{first.home.palette[first.home.helmet_selector[1]]:08X}",
        "silver_region_argb": f"{first.home.palette[0]:08X}",
        "white_region_argb": f"{first.home.palette[2]:08X}",
    }


def _editor_build_manifest(input_0a: Path) -> dict[str, Any]:
    path = input_0a.parent / ".apf2k8-mod-studio-build.json"
    _require(path.is_file() and not path.is_symlink(),
             "final editor build manifest is unavailable")
    _require(_sha256_file(path) == EXPECTED_BUILD_MANIFEST_SHA256,
             "final editor build manifest hash differs")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProofError(f"could not read final editor build manifest: {exc}") from exc
    _require(document.get("schema") == "apf2k8_mod_studio_build/v1",
             "final editor build manifest schema differs")
    _require(document.get("output", {}).get("0a_sha256") == EXPECTED_VOLUME_SHA256,
             "final editor build manifest output hash differs")
    _require(document.get("output", {}).get("published_atomically") is True,
             "final editor build was not published atomically")
    _require(document.get("source", {}).get("opened_read_only") is True
             and document.get("source", {}).get("source_modified") is False,
             "final editor build did not preserve its retail source")
    verification = document.get("verification")
    _require(isinstance(verification, dict) and verification
             and all(value is True for value in verification.values()),
             "final editor build verification is incomplete")
    edits = document.get("edits")
    _require(isinstance(edits, list) and len(edits) == 2,
             "final editor build edit inventory differs")
    crest = next((row for row in edits if row.get("kind") == "helmet_crest_design"), None)
    team = next((row for row in edits if row.get("kind") == "custom_team_appearance_batch"), None)
    _require(isinstance(crest, dict)
             and crest.get("replacement_png_sha256") == EXPECTED_MASK_PNG_SHA256
             and crest.get("profile") == "front_crown_to_rear_v1"
             and crest.get("outer_indices") == [171, 213, 1133, 1310],
             "final editor crest-design edit differs")
    _require(isinstance(team, dict)
             and team.get("outer_index") == APPEARANCE_OUTER_INDEX
             and team.get("entry_sha256") == EXPECTED_APPEARANCE_ENTRY_SHA256
             and team.get("asset_ids") == ["apf:custom-team-appearance:32"],
             "final editor appearance edit differs")
    return {
        "file": path.name,
        "sha256": EXPECTED_BUILD_MANIFEST_SHA256,
        "source_opened_read_only": True,
        "source_modified": False,
        "published_atomically": True,
        "edit_kinds": [row["kind"] for row in edits],
        "profile": crest["profile"],
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def prepare_exact(input_0a: Path, destination: Path) -> dict[str, Any]:
    input_0a = _regular_input(input_0a, "APF final v18 0A")
    _require(_sha256_file(input_0a) == EXPECTED_VOLUME_SHA256,
             "input 0A is not the exact final v18 editor build")
    build_manifest = _editor_build_manifest(input_0a)
    destination.mkdir(mode=0o700)
    try:
        archive = apf_outer.parse_archive(input_0a)
        with apf_inner.ArchiveReader(archive) as reader:
            _outer, system, scene = _helmet_system(archive, reader)
            geometry = _all_geometry(system, scene)
            mask_rgba, package = _package_layers(archive, reader)
            cache = _cache_layers(archive, reader)
            staged_appearance = _appearance(archive, reader, input_0a)

        _require(all(row["decoded_rgba_sha256"] == EXPECTED_RGBA_SHA256
                     for row in (*package.values(), *cache.values())),
                 "v18 package/cache decoded crest copies disagree")
        pixels = [tuple(mask_rgba[offset : offset + 4])
                  for offset in range(0, len(mask_rgba), 4)]
        pixel_counts = {
            "black_unpainted": sum(red == 0 and green == 0
                                     for red, green, _blue, _alpha in pixels),
            "red_weighted_texels": sum(red > 0 for red, _green, _blue, _alpha in pixels),
            "green_weighted_texels": sum(green > 0 for _red, green, _blue, _alpha in pixels),
            "mixed_weight_texels": sum(red > 0 and green > 0
                                         for red, green, _blue, _alpha in pixels),
            "antialiased_weight_texels": sum(
                red not in (0, 255) or green not in (0, 255)
                for red, green, _blue, _alpha in pixels
            ),
        }
        _require(pixel_counts == {
            "black_unpainted": 214125,
            "red_weighted_texels": 13379,
            "green_weighted_texels": 36473,
            "mixed_weight_texels": 1833,
            "antialiased_weight_texels": 7927,
        }, "v18 weighted crest mask pixel census differs")
        active = [(index % 512, index // 512) for index, pixel in enumerate(pixels)
                  if pixel[0] or pixel[1]]
        active_bbox = [min(x for x, _y in active), min(y for _x, y in active),
                       max(x for x, _y in active), max(y for _x, y in active)]
        _require(active_bbox == [0, 143, 511, 368],
                 "v18 weighted crest active bbox differs")
        palette = [int(value, 16) for value in staged_appearance["palette_argb"]]
        colored = colorize_weighted_region_mask(
            mask_rgba, palette[8], palette[0], palette[2],
        )
        _require(_sha256_bytes(colored) == EXPECTED_MATERIAL_RGBA_SHA256,
                 "v18 weighted crest material differs")

        geometry_path = destination / "helmet-v18.geometry.json"
        raw_mask_path = destination / "helmet-v18-region-mask.png"
        material_path = destination / "helmet-v18-crest-material.png"
        diagnostic_path = destination / "helmet-v18-uv-diagnostic.png"
        _write_json(geometry_path, geometry)
        raw_mask_path.write_bytes(encode_rgba_png(512, 512, mask_rgba))
        material_path.write_bytes(encode_rgba_png(512, 512, colored))
        diagnostic_path.write_bytes(encode_rgba_png(512, 512, uv_diagnostic_rgba()))
        _require(_sha256_file(raw_mask_path) == EXPECTED_MASK_PNG_SHA256,
                 "v18 weighted crest PNG differs")
        _require(_sha256_file(material_path) == EXPECTED_MATERIAL_PNG_SHA256,
                 "v18 weighted crest review-material PNG differs")

        carrier = geometry["groups"]["helmet_hi_draw_02"]
        receipt = {
            "schema": SCHEMA,
            "claim": "exact_v18_editor_build_static_asset_space_visualization",
            "source": {
                "whole_volume_sha256": EXPECTED_VOLUME_SHA256,
                "editor_build_manifest": build_manifest,
                "helmet_outer_index": HELMET_OUTER_INDEX,
                "helmet_outer_sha256": EXPECTED_HELMET_OUTER_SHA256,
                "helmet_inner_index": HELMET_INNER_INDEX,
                "helmet_scne_sha256": EXPECTED_SCNE_SHA256,
                "crest_package_outer_index": PACKAGE_OUTER_INDEX,
                "crest_package_sha256": EXPECTED_PACKAGE_SHA256,
                "logo_cache_directory_sha256": EXPECTED_CACHE_DIRECTORY_SHA256,
                "logo_cache_payload_sha256": EXPECTED_CACHE_PAYLOAD_SHA256,
                "appearance_entry_sha256": EXPECTED_APPEARANCE_ENTRY_SHA256,
            },
            "geometry": {
                "file": geometry_path.name,
                "sha256": _sha256_file(geometry_path),
                "high_lod_draw_count": EXPECTED_DRAW_COUNT,
                "shell_draw": SHELL_DRAW,
                "shell_triangle_count": EXPECTED_SHELL_TRIANGLES,
                "crest_draw": CREST_DRAW,
                "crest_triangle_count": EXPECTED_CREST_TRIANGLES,
                "crest_vertex_count": EXPECTED_CREST_VERTICES,
                "crest_bounds_cm": _bounds(carrier["positions_cm"]),
                "minimum_crest_absolute_x_cm": min(abs(row[0]) for row in carrier["positions_cm"]),
                "minimum_crest_z_cm": min(row[2] for row in carrier["positions_cm"]),
                "source_uv_bounds": {
                    "minimum": [min(row[axis] for row in carrier["uv_d3d"]) for axis in range(2)],
                    "maximum": [max(row[axis] for row in carrier["uv_d3d"]) for axis in range(2)],
                },
                "coordinate_proof": {
                    "serialized_axes": {
                        "x": "left_to_right_side",
                        "y": "vertical",
                        "z": "rear_to_front",
                    },
                    "helmet_hi_root_hierarchy_anchor": {
                        "parent": -1,
                        "vector_a": [0.0, 0.0, 0.0, 1.0],
                        "vector_b": [0.0, 0.0, 0.0, 1.0],
                    },
                    "carrier_sides": _carrier_axis_proof(carrier),
                    "carrier_components": _carrier_component_contract(carrier),
                "camera_axes": {
                        "side_right": "+x looking toward origin, quaternion roll +pi/2",
                        "side_left": "-x looking toward origin, quaternion roll -pi/2",
                        "crown": "+y looking toward origin, zero roll",
                        "rear": "-z looking toward origin, zero roll",
                    },
                    "side_right_projection": _project_carrier_side_right(carrier),
                },
                "triangle_strips_expanded_per_draw": True,
                "cross_draw_strip_join_forbidden": True,
            },
            "crest": {
                "package": package,
                "cache": cache,
                "raw_region_mask": {
                    "file": raw_mask_path.name,
                    "png_sha256": _sha256_file(raw_mask_path),
                    "decoded_rgba_sha256": EXPECTED_RGBA_SHA256,
                    "active_bbox": active_bbox,
                    "pixel_counts": pixel_counts,
                    "channel_levels": {
                        "red": list(range(0, 256, 17)),
                        "green": list(range(0, 256, 17)),
                    },
                    "xenos_4bit_weight_lattice": True,
                    "red_plus_green_maximum": 255,
                },
                "review_material": {
                    "file": material_path.name,
                    "png_sha256": _sha256_file(material_path),
                    "rgba_sha256": _sha256_bytes(colored),
                    "mapping": (
                        "shell*(255-red-green)/255 + palette[0]*red/255 + "
                        "palette[2]*green/255; nearest integer rounding"
                    ),
                    "weighted_shader_equation": True,
                    "fully_opaque_shell_composite": True,
                    "no_redraw_or_resampling": True,
                },
                "uv_diagnostic": {
                    "file": diagnostic_path.name,
                    "png_sha256": _sha256_file(diagnostic_path),
                    "purpose": "opaque U/V orientation and carrier visibility only; not game art",
                },
            },
            "appearance": staged_appearance,
            "render_contract": {
                "renderer": "Blender background factory-startup via companion script",
                "shading": "unlit_emission_exact_palette_no_lights_v1",
                "visible_source_draws": [1, 2],
                "explicit_uv_binding": "Exact APF crest UV",
                "texture_overscan": "transparent clip outside normalized 0..1 domain",
                "carrier_component_contract": (
                    "signed_x_topology_islands_with_distinct_zero_seams_v2"
                ),
                "carrier_material_background": (
                    "inactive_black_mask_pixels_simulated_as_exact_shell_rgb_opaque_v1"
                ),
                "region_palette_binding": (
                    "recovered_shader_red_c12_palette0_silver_"
                    "green_c13_palette2_white_residual_shell_v1"
                ),
                "side_diagnostic_visibility": "right_x_positive_component_only_v1",
                "carrier_visual_normal_bias": {
                    "meters": 0.0005,
                    "purpose": "render-only coplanar shell depth separation",
                    "game_geometry_changed": False,
                },
                "debug_views": list(DEBUG_VIEW_NAMES),
                "views": list(VIEW_NAMES),
                "centimeters_to_meters": 0.01,
                "d3d_to_blender_v": "v_blender = 1 - v_d3d",
                "shell_material_color_from_staged_palette": True,
                "facemask_context": "stock cage_01 only; no gameplay selector claim",
            },
            "limitations": [
                "This is an exact static asset-space visualization, not Xenia, gameplay, original-hardware, draw-binding, animation, lighting, or shader-bytecode proof.",
                "The recovered continuous R/G palette-weight equation is applied without APF's runtime lighting.",
                "Blender offsets the carrier outward by a disclosed 0.5 mm along source normals only to prevent coplanar depth fighting; game geometry is unchanged.",
                "SCNE node transforms/material records remain unresolved; exact serialized positions/topology are shown in their shared object space.",
                "The selected stock cage is context only and does not claim a player's gameplay facemask choice.",
            ],
        }
        receipt_path = destination / "helmet-v18-proof.json"
        _write_json(receipt_path, receipt)
        return receipt
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _atomic_destination(destination: Path) -> tuple[Path, Path]:
    destination = Path(destination)
    _require(not destination.exists() and not destination.is_symlink(),
             f"refusing to overwrite proof output: {destination}")
    _require(destination.parent.is_dir(), f"proof output parent does not exist: {destination.parent}")
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    staging.rmdir()  # prepare_exact owns the exclusive final mkdir.
    return destination, staging


def _validate_render_outputs(directory: Path) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ProofError("Pillow is required to validate proof renders") from exc
    rows: dict[str, Any] = {}
    for view in VIEW_NAMES:
        path = directory / f"helmet-v18-{view}.png"
        _require(path.is_file(), f"Blender did not produce {path.name}")
        with Image.open(path) as image:
            image.load()
            _require(image.size == (768, 768), f"{path.name} is not 768x768")
            rgb = image.convert("RGB")
            colors = rgb.getcolors(maxcolors=768 * 768)
            _require(colors is not None and len(colors) >= 64,
                     f"{path.name} is visually empty or unexpectedly flat")
            dominant = max(count for count, _color in colors)
            _require(dominant < 560000, f"{path.name} is almost entirely one color")
            pixels = list(rgb.getdata())
            background = pixels[0]
            foreground = [
                (index % 768, index // 768)
                for index, color in enumerate(pixels)
                if max(abs(color[channel] - background[channel]) for channel in range(3)) > 3
            ]
            _require(bool(foreground), f"{path.name} has no foreground against its corner")
            minimum_x = min(point[0] for point in foreground)
            maximum_x = max(point[0] for point in foreground)
            minimum_y = min(point[1] for point in foreground)
            maximum_y = max(point[1] for point in foreground)
            margin = min(minimum_x, minimum_y, 767 - maximum_x, 767 - maximum_y)
            _require(margin >= 24,
                     f"{path.name} subject touches/crops its proof frame (margin={margin}px)")
            shell_pixels = sum(
                max(abs(color[channel] - (0, 76, 84)[channel]) for channel in range(3)) <= 3
                for color in pixels
            )
            _require(shell_pixels >= 1000,
                     f"{path.name} does not contain the exact staged shell color")
            rows[view] = {
                "file": path.name,
                "sha256": _sha256_file(path),
                "width": 768,
                "height": 768,
                "unique_rgb_colors": len(colors),
                "largest_single_color_pixel_count": dominant,
                "background_rgb": list(background),
                "foreground_bbox": [minimum_x, minimum_y, maximum_x, maximum_y],
                "minimum_border_margin_pixels": margin,
                "exact_004c54_shell_pixel_count": shell_pixels,
            }
    return rows


def _validate_debug_outputs(directory: Path) -> dict[str, Any]:
    from PIL import Image

    rows: dict[str, Any] = {}
    for view in DEBUG_VIEW_NAMES:
        path = directory / f"helmet-v18-{view}.png"
        _require(path.is_file(), f"Blender did not produce {path.name}")
        with Image.open(path) as image:
            image.load()
            _require(image.size == (768, 768), f"{path.name} is not 768x768")
            rgb = image.convert("RGB")
            colors = rgb.getcolors(maxcolors=768 * 768)
            _require(colors is not None and len(colors) >= 32,
                     f"{path.name} is visually empty or unexpectedly flat")
            pixels = list(rgb.getdata())
            background = pixels[0]
            foreground = [
                (index % 768, index // 768)
                for index, color in enumerate(pixels)
                if max(abs(color[channel] - background[channel]) for channel in range(3)) > 3
            ]
            _require(bool(foreground), f"{path.name} has no diagnostic foreground")
            bounds = [
                min(point[0] for point in foreground), min(point[1] for point in foreground),
                max(point[0] for point in foreground), max(point[1] for point in foreground),
            ]
            margin = min(bounds[0], bounds[1], 767 - bounds[2], 767 - bounds[3])
            _require(margin >= 24, f"{path.name} diagnostic carrier is cropped")
            rows[view] = {
                "file": path.name,
                "sha256": _sha256_file(path),
                "foreground_bbox": bounds,
                "minimum_border_margin_pixels": margin,
                "unique_rgb_colors": len(colors),
            }
    return rows


def _contact_sheet(
    directory: Path,
    path: Path | None = None,
    names: tuple[str, ...] = VIEW_NAMES,
) -> Path:
    from PIL import Image, ImageDraw

    rows = (len(names) + 1) // 2
    output = Image.new("RGB", (1536, 768 * rows), (24, 28, 32))
    for index, view in enumerate(names):
        with Image.open(directory / f"helmet-v18-{view}.png") as source:
            tile = source.convert("RGB")
        x = (index % 2) * 768
        y = (index // 2) * 768
        output.paste(tile, (x, y))
        draw = ImageDraw.Draw(output)
        draw.rectangle((x + 18, y + 18, x + 175, y + 52), fill=(8, 10, 12))
        draw.text((x + 28, y + 27), view.upper(), fill=(245, 245, 245))
    path = path or directory / "helmet-v18-contact-sheet.png"
    output.save(path, format="PNG", compress_level=9, optimize=False)
    return path


def _finalize_render(
    directory: Path,
    *,
    expected_schema: str,
    expected_claim: str,
) -> dict[str, Any]:
    """Validate Blender's staged files and commit the render receipt last."""

    directory = Path(directory)
    _require(directory.is_dir() and not directory.is_symlink(),
             f"prepared proof is not a real directory: {directory}")
    receipt_path = directory / "helmet-v18-proof.json"
    _require(receipt_path.is_file() and not receipt_path.is_symlink(),
             "prepared proof receipt is unavailable")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    _require(receipt.get("schema") == expected_schema,
             "prepared proof receipt schema differs")
    _require(receipt.get("claim") == expected_claim,
             "prepared proof receipt claim differs")
    _require("render" not in receipt, "proof has already been finalized")
    for section, key in (("geometry", "file"),):
        row = receipt[section]
        path = directory / row[key]
        _require(path.is_file() and _sha256_file(path) == row["sha256"],
                 f"prepared {section} hash differs")
    for key in ("raw_region_mask", "review_material", "uv_diagnostic"):
        row = receipt["crest"][key]
        path = directory / row["file"]
        _require(path.is_file() and _sha256_file(path) == row["png_sha256"],
                 f"prepared crest {key} hash differs")

    completion_path = directory / "helmet-v18-blender-stage.json"
    _require(completion_path.is_file() and not completion_path.is_symlink(),
             "Blender completion marker is unavailable")
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    _require(completion.get("schema") == "apf2k8_exact_helmet_blender_stage/v2",
             "Blender completion marker schema differs")
    _require(completion.get("source_claim") == expected_claim,
             "Blender completion marker came from another claim boundary")
    _require(completion.get("shading_contract") ==
             "unlit_emission_exact_palette_no_lights_v1",
             "Blender did not use the pinned unlit proof shading")
    _require(completion.get("physical_light_count") == 0,
             "Blender proof unexpectedly contains physical lights")
    _require(completion.get("visible_source_draws") == [1, 2],
             "Blender proof did not isolate shell draw 1 plus crest draw 2")
    _require(completion.get("uv_binding") == "explicit:Exact APF crest UV",
             "Blender proof did not explicitly bind the recovered crest UV map")
    _require(completion.get("texture_extension") == "CLIP",
             "Blender proof did not clip UV overscan texture sampling")
    _require(
        completion.get("carrier_material_background_contract") ==
        "inactive_black_mask_pixels_simulated_as_exact_shell_rgb_opaque_v1",
        "Blender proof did not use the opaque exact-shell carrier background",
    )
    normal_bias = completion.get("carrier_visual_normal_bias")
    _require(
        isinstance(normal_bias, dict)
        and normal_bias.get("meters") == 0.0005
        and normal_bias.get("purpose") == "render-only coplanar shell depth separation"
        and normal_bias.get("game_geometry_changed") is False,
        "Blender did not use the disclosed render-only carrier depth bias",
    )
    component_contract = completion.get("carrier_component_contract")
    _require(isinstance(component_contract, dict),
             "Blender carrier component contract is missing")
    _require(
        component_contract.get("split") ==
        "signed_x_topology_islands_with_distinct_zero_seams_v2"
        and component_contract.get("component_count") == 2,
        "Blender carrier component split differs",
    )
    for label in ("left", "right"):
        row = component_contract.get(label)
        _require(
            isinstance(row, dict)
            and row.get("vertex_count") == EXPECTED_CREST_SIDE_VERTICES
            and row.get("triangle_count") == EXPECTED_CREST_SIDE_TRIANGLES
            and row.get("x_zero_seam_vertex_count") == EXPECTED_CREST_SIDE_ZERO_VERTICES,
            f"Blender carrier {label} component counts differ",
        )
    _require(component_contract.get("main_visibility") == ["left", "right"],
             "Blender main views did not include both carrier sides")
    _require(component_contract.get("side_diagnostic_visibility") == ["right"],
             "Blender side diagnostic did not isolate the right carrier")
    _require(completion.get("camera_contract") ==
             "lens55mm_side0.72m_crown_rear0.75m_v1",
             "Blender proof did not use the uncropped camera contract")
    _require(completion.get("camera_axis_contract") ==
             "right_roll_plus_pi_over_2_left_minus_pi_over_2_crown_rear_zero_v2",
             "Blender proof did not use the measured APF axis/roll contract")
    side_basis = completion.get("camera_bases", {}).get("side-right")
    _require(isinstance(side_basis, dict), "Blender side-right camera basis is missing")
    right = side_basis.get("screen_right_world")
    up = side_basis.get("screen_up_world")
    forward = side_basis.get("forward_world")
    _require(
        isinstance(right, list) and len(right) == 3
        and isinstance(up, list) and len(up) == 3
        and isinstance(forward, list) and len(forward) == 3,
        "Blender side-right camera basis is malformed",
    )
    _require(abs(right[2]) > 0.999 and abs(right[0]) < 0.02 and abs(right[1]) < 0.02,
             "side-right screen horizontal is not world Z")
    _require(up[1] > 0.999 and abs(up[0]) < 0.02 and abs(up[2]) < 0.02,
             "side-right screen vertical is not world +Y")
    _require(forward[0] < -0.999 and abs(forward[1]) < 0.02 and abs(forward[2]) < 0.02,
             "side-right camera does not look along world -X")
    views = _validate_render_outputs(directory)
    for name, row in views.items():
        _require(completion.get("views", {}).get(name, {}).get("sha256") == row["sha256"],
                 f"Blender completion hash differs for {name}")
    debug_views = _validate_debug_outputs(directory)
    for name, row in debug_views.items():
        _require(completion.get("debug_views", {}).get(name, {}).get("sha256") == row["sha256"],
                 f"Blender completion hash differs for {name}")
    blend = directory / "helmet-v18-proof.blend"
    _require(blend.is_file() and blend.stat().st_size > 0,
             "Blender did not save the review scene")
    _require(completion.get("blend_scene", {}).get("sha256") == _sha256_file(blend),
             "Blender scene hash differs from its completion marker")

    sheet = directory / "helmet-v18-contact-sheet.png"
    debug_sheet = directory / "helmet-v18-debug-contact-sheet.png"
    _require(not sheet.exists() and not sheet.is_symlink(),
             "refusing to overwrite an existing contact sheet")
    _require(not debug_sheet.exists() and not debug_sheet.is_symlink(),
             "refusing to overwrite an existing debug contact sheet")
    sheet_temp = directory / ".helmet-v18-contact-sheet.finalize.png"
    debug_sheet_temp = directory / ".helmet-v18-debug-contact-sheet.finalize.png"
    receipt_temp = directory / ".helmet-v18-proof.finalize.json"
    _require(not sheet_temp.exists() and not debug_sheet_temp.exists() and not receipt_temp.exists(),
             "stale finalize temporary file exists; inspect it before retrying")
    try:
        _contact_sheet(directory, sheet_temp)
        _contact_sheet(directory, debug_sheet_temp, DEBUG_VIEW_NAMES)
        receipt["render"] = {
            "schema": RENDER_SCHEMA,
            "headless": True,
            "display_environment_required": False,
            "command": ["blender", "--background", "--factory-startup", "--python",
                        "apf_helmet_static_visual_proof_blender.py", "--", receipt_path.name],
            "blender_version": completion.get("blender_version"),
            "shading_contract": completion.get("shading_contract"),
            "physical_light_count": completion.get("physical_light_count"),
            "visible_source_draws": completion.get("visible_source_draws"),
            "uv_binding": completion.get("uv_binding"),
            "texture_extension": completion.get("texture_extension"),
            "carrier_material_background_contract": completion.get(
                "carrier_material_background_contract"
            ),
            "carrier_visual_normal_bias": normal_bias,
            "carrier_component_contract": component_contract,
            "camera_contract": completion.get("camera_contract"),
            "camera_axis_contract": completion.get("camera_axis_contract"),
            "camera_bases": completion.get("camera_bases"),
            "blender_completion": {
                "file": completion_path.name,
                "sha256": _sha256_file(completion_path),
            },
            "views": views,
            "debug_views": debug_views,
            "contact_sheet": {"file": sheet.name, "sha256": _sha256_file(sheet_temp)},
            "debug_contact_sheet": {
                "file": debug_sheet.name,
                "sha256": _sha256_file(debug_sheet_temp),
            },
            "blend_scene": {"file": blend.name, "sha256": _sha256_file(blend)},
        }
        if (directory / "blender.log").is_file():
            receipt["render"]["blender_log"] = {
                "file": "blender.log",
                "sha256": _sha256_file(directory / "blender.log"),
            }
        _write_json(receipt_temp, receipt)
        os.replace(sheet_temp, sheet)
        os.replace(debug_sheet_temp, debug_sheet)
        # The receipt is the commit marker and is therefore replaced last.
        os.replace(receipt_temp, receipt_path)
        return receipt
    except Exception:
        sheet_temp.unlink(missing_ok=True)
        debug_sheet_temp.unlink(missing_ok=True)
        receipt_temp.unlink(missing_ok=True)
        raise


def finalize_exact(directory: Path) -> dict[str, Any]:
    return _finalize_render(
        directory,
        expected_schema=SCHEMA,
        expected_claim="exact_v18_editor_build_static_asset_space_visualization",
    )


def render_exact(input_0a: Path, destination: Path, blender: Path) -> dict[str, Any]:
    destination, staging = _atomic_destination(destination)
    try:
        prepare_exact(input_0a, staging)
        renderer = ROOT / "tools" / "apf_helmet_static_visual_proof_blender.py"
        command = [
            str(blender), "--background", "--factory-startup", "--python", str(renderer),
            "--", str(staging / "helmet-v18-proof.json"),
        ]
        environment = os.environ.copy()
        environment.pop("DISPLAY", None)
        environment.pop("WAYLAND_DISPLAY", None)
        environment.pop("XAUTHORITY", None)
        completed = subprocess.run(
            command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            timeout=180, check=False,
        )
        (staging / "blender.log").write_text(completed.stdout, encoding="utf-8", newline="\n")
        _require(
            completed.returncode == 0 and "APF_EXACT_HELMET_BLENDER_RENDER_PASS views=4" in completed.stdout,
            "Blender background render failed or omitted its completion marker "
            f"(exit {completed.returncode}):\n{completed.stdout[-4000:]}",
        )
        receipt = finalize_exact(staging)
        staging.rename(destination)
        return receipt
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="extract exact proof inputs without rendering")
    prepare.add_argument("input_0a", type=Path)
    prepare.add_argument("output_dir", type=Path)
    render = commands.add_parser("render", help="prepare and render four background Blender views")
    render.add_argument("input_0a", type=Path)
    render.add_argument("output_dir", type=Path)
    render.add_argument("--blender", type=Path, default=Path("/usr/bin/blender"))
    finalize = commands.add_parser(
        "finalize", help="validate a separately rendered prepared directory"
    )
    finalize.add_argument("prepared_dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "finalize":
            receipt = finalize_exact(args.prepared_dir)
            print(
                "APF_EXACT_HELMET_STATIC_PROOF_FINALIZED "
                f"views={len(receipt['render']['views'])} output={args.prepared_dir}"
            )
            return 0
        destination, staging = _atomic_destination(args.output_dir)
        if args.command == "prepare":
            try:
                receipt = prepare_exact(args.input_0a, staging)
                staging.rename(destination)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise
        else:
            _require(Path(args.blender).is_file(), f"Blender executable is unavailable: {args.blender}")
            # render_exact reserves its own staging directory.
            receipt = render_exact(args.input_0a, args.output_dir, args.blender)
        print(
            "APF_EXACT_HELMET_STATIC_PROOF_READY "
            f"volume={receipt['source']['whole_volume_sha256']} "
            f"scne={receipt['source']['helmet_scne_sha256']} "
            f"output={args.output_dir}"
        )
        return 0
    except (ProofError, OSError, apf_outer.FormatError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
