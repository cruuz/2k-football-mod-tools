#!/usr/bin/env python3
"""Render a headless static proof of APF's compiled whole-shell crest atlas.

This tool reads a completed copied ``0A`` volume.  It independently extracts
``helmet_00`` from outer entry 1310, requires both LODs to route draw 1 to crest
material 2, requires the legacy draw-2 overlay to contain no triangles, and
decodes both 512x512 ``uniform_logo_NN`` layers.  The layers must be identical,
so the renders do not claim an unproved high/low layer binding.

A small deterministic software rasterizer emits bilateral, front/rear, and
crown views for both exact draw-1 LOD meshes.  Numeric receipts include sampled
physical coverage, bilateral screen-space parity, x=0 seam continuity, and
high/low screen-space parity.  These are static asset-space diagnostics only:
they are not Xenia, gameplay, original-hardware, or visual-quality proof.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
for search_root in (ROOT, ROOT / "tools"):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

import apf_custom_team_appearance_patch as appearance  # noqa: E402
import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_team_crests  # noqa: E402


SCHEMA = "apf2k8_helmet_shell_static_proof/v1"
CLAIM = "headless_static_asset_space_whole_shell_visualization_only"
HELMET_OUTER_INDEX = 1310
HELMET_INNER_NAME = "helmet_00"
HELMET_INNER_TYPE = "SCNE"
HELMET_SYSTEM_LENGTH = 0xD5680
MAX_DECOMPRESSED = 128 * 1024 * 1024
STRIDE = 32
DRAW_RECORD_SIZE = 0x30
DRAW_RECORD_COUNT = 13
SHELL_DRAW = 1
LEGACY_OVERLAY_DRAW = 2
CREST_MATERIAL = 2
WIDTH = 512
HEIGHT = 512
BASE_LENGTH = 0x80000
MIP_LENGTH = 0x2C000
RGBA_LENGTH = WIDTH * HEIGHT * 4
BACKGROUND = np.array((8, 11, 16, 255), dtype=np.uint8)
VIEW_NAMES = ("side-right", "side-left", "front", "rear", "crown")


class ProofError(ValueError):
    """The built volume or proof request left the bounded static contract."""


@dataclass(frozen=True)
class LodSpec:
    name: str
    draw_record_offset: int
    index_offset: int
    index_count: int
    shell_index_start: int
    shell_index_count: int
    shell_vertex_start: int
    shell_vertex_count: int
    overlay_index_start: int
    overlay_index_count: int
    overlay_vertex_start: int
    overlay_vertex_count: int
    stream_start: int
    vertex_count: int
    center: tuple[float, float, float]
    scale: tuple[float, float, float]
    shell_triangle_count: int
    exterior_triangle_count: int
    exterior_triangles_per_side: int


LODS = (
    LodSpec(
        "helmet_hi", 0x99C0, 0x9C30, 9773,
        2623, 4800, 1312, 1427, 7423, 1046, 2739, 326,
        0xEA1C, 3856,
        (0.0, 4.927330017089844, 1.7508296966552734),
        (13.967263221740723,) * 3,
        2464, 2214, 1107,
    ),
    LodSpec(
        "helmet_lo", 0xCCA80, 0xCCCF0, 1552,
        359, 659, 193, 283, 1018, 231, 476, 128,
        0xCDA9C, 799,
        (0.0, 2.8593978881835938, 2.8941473960876465),
        (16.119155883789062,) * 3,
        432, 432, 216,
    ),
)


@dataclass(frozen=True)
class Layer:
    name: str
    rgba: bytes
    base_sha256: str
    mip_sha256: str
    decoded_rgba_sha256: str


@dataclass(frozen=True)
class Geometry:
    spec: LodSpec
    positions: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray
    faces: np.ndarray
    side_faces: Mapping[str, np.ndarray]
    material_before_route: int
    overlay_triangle_count: int


@dataclass(frozen=True)
class Frame:
    horizontal: np.ndarray
    vertical: np.ndarray
    depth: np.ndarray
    minimum: tuple[float, float]
    maximum: tuple[float, float]
    scale: float
    offset: tuple[float, float]


@dataclass
class Render:
    image: np.ndarray
    semantic: np.ndarray
    shell: np.ndarray
    active: np.ndarray


class _MemoryReader:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self, _entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.payload):
            raise apf_inner.FormatError("memory IFF read exceeds allocation")
        return self.payload[offset : offset + size]


def require(value: object, message: str) -> None:
    if not value:
        raise ProofError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _link_read_only_reference(source: Path, destination: Path) -> None:
    """Expose one existing pack in a private parse view without copying it."""

    try:
        os.symlink(source.resolve(strict=True), destination)
        return
    except (OSError, NotImplementedError, AttributeError) as symlink_error:
        try:
            os.link(source, destination)
            return
        except OSError as hardlink_error:
            raise ProofError(
                f"could not create private read-only reference for {source.name}: "
                f"symlink={symlink_error}; hardlink={hardlink_error}"
            ) from hardlink_error


@contextmanager
def _standalone_parse_view(
    input_0a: Path,
    sibling_source_0a: Path | None,
) -> Iterable[tuple[Path, dict[str, object]]]:
    """Yield a complete private archive view for a standalone copied 0A."""

    if sibling_source_0a is None:
        yield input_0a, {
            "used": False,
            "retained_sibling_links_created": False,
        }
        return
    sibling_source_0a = Path(
        os.path.abspath(os.fspath(Path(sibling_source_0a).expanduser()))
    )
    require(
        sibling_source_0a.is_file() and not sibling_source_0a.is_symlink(),
        f"sibling source 0A is not a regular non-symlink file: {sibling_source_0a}",
    )
    try:
        source_archive = apf_outer.parse_archive(sibling_source_0a)
    except apf_outer.FormatError as exc:
        raise ProofError(f"could not parse sibling source archive: {exc}") from exc
    require(input_0a.name == source_archive.packs[0].name,
            "standalone input basename does not match the source index pack")
    with tempfile.TemporaryDirectory(prefix="apf-shell-static-view-") as directory:
        view = Path(directory)
        parse_0a = view / input_0a.name
        _link_read_only_reference(input_0a, parse_0a)
        for pack in source_archive.packs[1:]:
            _link_read_only_reference(pack.path, view / pack.name)
        try:
            parsed = apf_outer.parse_archive(parse_0a)
        except apf_outer.FormatError as exc:
            raise ProofError(f"could not parse standalone input with pristine siblings: {exc}") from exc
        require(
            [(pack.name, pack.declared_size) for pack in parsed.packs]
            == [(pack.name, pack.declared_size) for pack in source_archive.packs],
            "standalone input changed the declared sibling-pack contract",
        )
        yield parse_0a, {
            "used": True,
            "pristine_sibling_source_0a": str(sibling_source_0a),
            "private_view_cleaned_after_render": True,
            "retained_sibling_links_created": False,
        }


def _snorm(value: int) -> float:
    return max(value / 32767.0, -1.0)


def _unit(vector: Iterable[float]) -> np.ndarray:
    result = np.asarray(tuple(vector), dtype=np.float64)
    length = float(np.linalg.norm(result))
    require(math.isfinite(length) and length > 1.0e-12, "zero/non-finite vector")
    return result / length


def expand_strip(indices: Iterable[int]) -> list[tuple[int, int, int]]:
    """Expand one D3D triangle strip, preserving restart and parity."""

    output: list[tuple[int, int, int]] = []
    strip: list[int] = []
    for value in indices:
        if value == 0xFFFF:
            strip.clear()
            continue
        strip.append(value)
        if len(strip) < 3:
            continue
        number = len(strip) - 3
        first, second, third = strip[-3:]
        if number & 1:
            first, second = second, first
        if len({first, second, third}) == 3:
            output.append((first, second, third))
    return output


def _decode_4444(metadata: Mapping[str, object], base: bytes) -> bytes:
    """Independent display-order decoder for the selected Xenos 4:4:4:4 base."""

    expected = {
        "width": WIDTH, "height": HEIGHT, "pitch_pixels": WIDTH,
        "format": 15, "endianness": 1, "dimension": 1,
        "tiled": True, "stacked": False,
        "vc_base_data_length": BASE_LENGTH, "vc_mip_data_length": MIP_LENGTH,
    }
    disagreements = {
        key: (metadata.get(key), wanted)
        for key, wanted in expected.items() if metadata.get(key) != wanted
    }
    require(not disagreements, f"crest TXTR descriptor differs: {disagreements}")
    selectors = list(metadata.get("swizzle_components", ()))
    require(selectors == [2, 1, 0, 3], "crest TXTR swizzle differs")
    require(len(base) == BASE_LENGTH, "crest base allocation differs")
    linear = apf_inner._untile_2d(  # type: ignore[attr-defined]
        base, WIDTH, HEIGHT, WIDTH, 1, 1, 2,
    )
    linear = apf_inner._endian_swap(linear, 1)  # type: ignore[attr-defined]
    output = bytearray(RGBA_LENGTH)
    for index in range(WIDTH * HEIGHT):
        value = int.from_bytes(linear[index * 2 : index * 2 + 2], "little")
        raw = (
            (value & 15) * 17,
            ((value >> 4) & 15) * 17,
            ((value >> 8) & 15) * 17,
            ((value >> 12) & 15) * 17,
        )
        pixel = tuple((*raw, 0, 255, 0, 0)[selector] for selector in selectors)
        output[index * 4 : index * 4 + 4] = bytes(pixel)
    return bytes(output)


def _read_layers(
    archive: apf_outer.Archive,
    reader: apf_inner.ArchiveReader,
    outer_index: int,
) -> tuple[Layer, Layer, dict[str, object]]:
    try:
        entry = archive.entries[outer_index]
    except IndexError as exc:
        raise ProofError(f"archive has no crest outer entry {outer_index}") from exc
    require(
        len(entry.segments) == 1
        and entry.segments[0].pack_name == archive.index_path.name,
        "selected crest package is not contained in the input 0A",
    )
    try:
        record = apf_inner.parse_iff(reader, entry)
        blocks = [
            apf_inner.decode_block(reader, record, number, MAX_DECOMPRESSED)
            for number in range(record.block_count)
        ]
    except apf_inner.FormatError as exc:
        raise ProofError(f"could not decode crest package: {exc}") from exc
    require(record.block_count == 2 and record.file_count == 2,
            "crest package block/file inventory differs")
    found = {item.name: item for item in record.files}
    layers: list[Layer] = []
    for name in ("logo_l0", "logo_l1"):
        item = found.get(name)
        require(item is not None and item.type_name == "TXTR",
                f"crest package is missing {name}/TXTR")
        require(len(item.parts) == 2, f"{name} part inventory differs")
        dram_part = next((part for part in item.parts if part.length == 0xE0), None)
        vram_part = next((part for part in item.parts if part.length == BASE_LENGTH + MIP_LENGTH), None)
        require(dram_part is not None and vram_part is not None,
                f"{name} DRAM/VRAM ownership differs")
        dram = blocks[dram_part.block_index][dram_part.offset : dram_part.offset + dram_part.length]
        vram = blocks[vram_part.block_index][vram_part.offset : vram_part.offset + vram_part.length]
        require(len(dram) == 0xE0 and len(vram) == BASE_LENGTH + MIP_LENGTH,
                f"{name} decoded allocation is truncated")
        try:
            metadata = apf_inner.parse_txtr_metadata(dram)
            rgba = _decode_4444(metadata, vram[:BASE_LENGTH])
        except apf_inner.FormatError as exc:
            raise ProofError(f"could not decode {name}: {exc}") from exc
        layers.append(Layer(
            name=name,
            rgba=rgba,
            base_sha256=sha256_bytes(vram[:BASE_LENGTH]),
            mip_sha256=sha256_bytes(vram[BASE_LENGTH:]),
            decoded_rgba_sha256=sha256_bytes(rgba),
        ))
    require(layers[0].rgba == layers[1].rgba,
            "selected whole-shell logo_l0/logo_l1 decoded atlases differ")
    return layers[0], layers[1], {
        "outer_entry_index": outer_index,
        "outer_name_id": f"{entry.name_id:08X}",
        "outer_sha256": sha256_bytes(reader.read(entry, 0, entry.size)),
        "layers_identical": True,
        "layer_binding_claim": (
            "none_required_for_static_render_because_logo_l0_equals_logo_l1"
        ),
    }


def _read_helmet_system(
    archive: apf_outer.Archive,
    reader: apf_inner.ArchiveReader,
) -> tuple[bytes, dict[str, object]]:
    try:
        entry = archive.entries[HELMET_OUTER_INDEX]
        require(
            len(entry.segments) == 1
            and entry.segments[0].pack_name == archive.index_path.name,
            "helmet_00 outer entry is not contained in the input 0A",
        )
        record = apf_inner.parse_iff(reader, entry)
    except (IndexError, apf_inner.FormatError) as exc:
        raise ProofError(f"could not parse helmet outer entry: {exc}") from exc
    matches = [
        item for item in record.files
        if item.name == HELMET_INNER_NAME and item.type_name == HELMET_INNER_TYPE
    ]
    require(len(matches) == 1, "helmet_00/SCNE ownership differs")
    item = matches[0]
    require(len(item.parts) == 1, "helmet_00 SCNE part inventory differs")
    part = item.parts[0]
    try:
        block = apf_inner.decode_block(reader, record, part.block_index, MAX_DECOMPRESSED)
    except apf_inner.FormatError as exc:
        raise ProofError(f"could not decode helmet SCNE block: {exc}") from exc
    system = block[part.offset : part.offset + part.length]
    require(len(system) == HELMET_SYSTEM_LENGTH,
            f"helmet_00 system length is 0x{len(system):x}, expected 0x{HELMET_SYSTEM_LENGTH:x}")
    return system, {
        "outer_entry_index": HELMET_OUTER_INDEX,
        "outer_sha256": sha256_bytes(reader.read(entry, 0, entry.size)),
        "inner_file_index": item.index,
        "system_sha256": sha256_bytes(system),
    }


def _decode_geometry(system: bytes, spec: LodSpec) -> Geometry:
    require(spec.stream_start + spec.vertex_count * STRIDE <= len(system),
            f"{spec.name} vertex stream is truncated")
    require(spec.index_offset + spec.index_count * 2 <= len(system),
            f"{spec.name} index stream is truncated")
    records = [
        struct.unpack_from(">12I", system, spec.draw_record_offset + number * DRAW_RECORD_SIZE)
        for number in range(DRAW_RECORD_COUNT)
    ]
    shell_record = records[SHELL_DRAW]
    overlay_record = records[LEGACY_OVERLAY_DRAW]
    require(
        shell_record[1:3] == (spec.shell_index_start, spec.shell_index_count)
        and shell_record[5:7] == (spec.shell_vertex_start, spec.shell_vertex_count),
        f"{spec.name} draw-1 ownership differs",
    )
    require(
        overlay_record[1:3] == (spec.overlay_index_start, spec.overlay_index_count)
        and overlay_record[5:7] == (spec.overlay_vertex_start, spec.overlay_vertex_count),
        f"{spec.name} draw-2 ownership differs",
    )
    require(shell_record[8] == CREST_MATERIAL,
            f"{spec.name} draw 1 is not routed to crest material 2")

    words = struct.unpack_from(f">{spec.index_count}H", system, spec.index_offset)
    shell_faces = expand_strip(words[
        spec.shell_index_start : spec.shell_index_start + spec.shell_index_count
    ])
    overlay_faces = expand_strip(words[
        spec.overlay_index_start : spec.overlay_index_start + spec.overlay_index_count
    ])
    require(len(shell_faces) == spec.shell_triangle_count,
            f"{spec.name} shell triangle census differs")
    require(not overlay_faces, f"{spec.name} legacy draw-2 overlay is not degenerate")

    positions = np.empty((spec.vertex_count, 3), dtype=np.float64)
    normals = np.empty_like(positions)
    uvs = np.empty((spec.vertex_count, 2), dtype=np.float64)
    for vertex in range(spec.vertex_count):
        start = spec.stream_start + vertex * STRIDE
        raw_position = tuple(_snorm(value) for value in struct.unpack_from(">3h", system, start))
        positions[vertex] = [
            spec.center[axis] + raw_position[axis] * spec.scale[axis]
            for axis in range(3)
        ]
        normals[vertex] = _unit(
            _snorm(value) for value in struct.unpack_from(">3h", system, start + 8)
        )
        uvs[vertex] = (
            2.0 * _snorm(struct.unpack_from(">h", system, start + 14)[0]),
            2.0 * _snorm(struct.unpack_from(">h", system, start + 22)[0]),
        )

    exterior: list[tuple[int, int, int]] = []
    for face in shell_faces:
        indices = np.asarray(face, dtype=np.int64)
        center = positions[indices].mean(axis=0)
        normal = normals[indices].sum(axis=0)
        radial = center - np.asarray(spec.center)
        if float(np.dot(normal, radial)) > 0.0:
            exterior.append(face)
    require(len(exterior) == spec.exterior_triangle_count,
            f"{spec.name} exterior triangle census differs")

    sides: dict[str, list[tuple[int, int, int]]] = {"left": [], "right": []}
    for face in exterior:
        x_values = positions[np.asarray(face), 0]
        if float(x_values.min()) >= -1.0e-6 and float(x_values.max()) > 1.0e-6:
            sides["right"].append(face)
        elif float(x_values.max()) <= 1.0e-6 and float(x_values.min()) < -1.0e-6:
            sides["left"].append(face)
        else:
            raise ProofError(f"{spec.name} exterior face crosses/is ambiguous at x=0")
    require(all(len(value) == spec.exterior_triangles_per_side for value in sides.values()),
            f"{spec.name} bilateral exterior census differs")
    used = sorted({index for face in exterior for index in face})
    used_uv = uvs[np.asarray(used)]
    require(float(used_uv.min()) >= 0.0 and float(used_uv.max()) <= 1.0,
            f"{spec.name} exterior UV leaves the 512 atlas")
    return Geometry(
        spec=spec,
        positions=positions,
        normals=normals,
        uvs=uvs,
        faces=np.asarray(exterior, dtype=np.int32),
        side_faces={key: np.asarray(value, dtype=np.int32) for key, value in sides.items()},
        material_before_route=shell_record[8],
        overlay_triangle_count=len(overlay_faces),
    )


def _validate_atlas(rgba: bytes) -> dict[str, object]:
    require(len(rgba) == RGBA_LENGTH, "whole-shell atlas is not 512x512 RGBA")
    pixels = np.frombuffer(rgba, dtype=np.uint8).reshape((HEIGHT, WIDTH, 4))
    require(np.all(pixels[:, :, 2] == 0), "whole-shell atlas uses the unsupported blue channel")
    require(np.all(pixels[:, :, 3] % 17 == 0),
            "whole-shell atlas alpha leaves the Xenos four-bit lattice")
    require(np.all(pixels[:, :, :2] % 17 == 0),
            "whole-shell atlas leaves the Xenos four-bit channel lattice")
    sums = pixels[:, :, 0].astype(np.uint16) + pixels[:, :, 1].astype(np.uint16)
    require(np.all(sums <= 255), "whole-shell atlas exceeds one coverage unit")
    body = (pixels[:, :, 0] == 0) & (pixels[:, :, 1] == 0)
    require(bool(body.any()), "whole-shell atlas has no shell-body texels")
    require(np.all(pixels[:, :, 3][body] == 255),
            "whole-shell atlas shell-body texels must be opaque (alpha 255); "
            "the retail 8/15 transport sentinel (alpha 0x88) renders the routed "
            "shell semi-transparent")
    active = sums > 0
    require(bool(active.any()), "whole-shell atlas has no active region texels")
    y_values, x_values = np.nonzero(active)
    return {
        "active_texel_count": int(active.sum()),
        "active_fraction": float(active.mean()),
        "active_bbox_inclusive": [
            int(x_values.min()), int(y_values.min()), int(x_values.max()), int(y_values.max()),
        ],
        "unique_rgba_count": len(Counter(map(tuple, pixels.reshape((-1, 4))))),
        "blue_zero": True,
        "opaque_shell_body_alpha_255": True,
        "four_bit_red_green_lattice": True,
        "red_plus_green_at_most_255": True,
    }


def _argb_rgb(value: int) -> np.ndarray:
    return np.asarray(((value >> 16) & 255, (value >> 8) & 255, value & 255), dtype=np.uint32)


def colorize_atlas(rgba: bytes, shell: int, red: int, green: int) -> np.ndarray:
    """Apply the recovered integer shader equation to one semantic atlas."""

    pixels = np.frombuffer(rgba, dtype=np.uint8).reshape((HEIGHT, WIDTH, 4))
    red_weight = pixels[:, :, 0].astype(np.uint32)
    green_weight = pixels[:, :, 1].astype(np.uint32)
    residual = 255 - red_weight - green_weight
    result = np.empty((HEIGHT, WIDTH, 4), dtype=np.uint8)
    shell_rgb, red_rgb, green_rgb = map(_argb_rgb, (shell, red, green))
    for channel in range(3):
        values = (
            shell_rgb[channel] * residual
            + red_rgb[channel] * red_weight
            + green_rgb[channel] * green_weight
            + 127
        ) // 255
        result[:, :, channel] = values.astype(np.uint8)
    result[:, :, 3] = 255
    return result


def _view_axes(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    axes = {
        "side-right": ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
        "side-left": ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),
        "front": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        "rear": ((-1, 0, 0), (0, 1, 0), (0, 0, -1)),
        "crown": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    }
    try:
        horizontal, vertical, depth = axes[name]
    except KeyError as exc:
        raise ProofError(f"unknown render view {name}") from exc
    return tuple(np.asarray(row, dtype=np.float64) for row in (horizontal, vertical, depth))  # type: ignore[return-value]


def _frame(name: str, geometries: Sequence[Geometry]) -> Frame:
    horizontal, vertical, depth = _view_axes(name)
    rows = []
    for geometry in geometries:
        used = np.unique(geometry.faces)
        rows.append(geometry.positions[used])
    points = np.concatenate(rows, axis=0)
    projected = np.column_stack((points @ horizontal, points @ vertical))
    minimum = projected.min(axis=0)
    maximum = projected.max(axis=0)
    span = maximum - minimum
    require(bool(np.all(span > 1.0e-6)), f"{name} projection is degenerate")
    margin = 28.0
    scale = min((WIDTH - 2 * margin) / span[0], (HEIGHT - 2 * margin) / span[1])
    rendered_span = span * scale
    offset = np.asarray((
        (WIDTH - rendered_span[0]) * 0.5 - minimum[0] * scale,
        (HEIGHT + rendered_span[1]) * 0.5 + minimum[1] * scale,
    ))
    return Frame(
        horizontal, vertical, depth,
        tuple(map(float, minimum)), tuple(map(float, maximum)), float(scale),
        tuple(map(float, offset)),
    )


def rasterize(
    geometry: Geometry,
    faces: np.ndarray,
    semantic_atlas: np.ndarray,
    material_atlas: np.ndarray,
    frame: Frame,
) -> Render:
    """Rasterize exact triangles with orthographic projection and a z buffer."""

    positions = geometry.positions
    projected = np.empty((len(positions), 3), dtype=np.float64)
    projected[:, 0] = (positions @ frame.horizontal) * frame.scale + frame.offset[0]
    projected[:, 1] = frame.offset[1] - (positions @ frame.vertical) * frame.scale
    projected[:, 2] = positions @ frame.depth
    depth = np.full((HEIGHT, WIDTH), -np.inf, dtype=np.float64)
    semantic = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    semantic[:, :] = (0, 0, 0, 255)
    image = np.empty((HEIGHT, WIDTH, 4), dtype=np.uint8)
    image[:, :] = BACKGROUND
    shell = np.zeros((HEIGHT, WIDTH), dtype=np.bool_)
    active = np.zeros_like(shell)

    for face in faces:
        points = projected[face]
        x0, y0 = points[0, :2]
        x1, y1 = points[1, :2]
        x2, y2 = points[2, :2]
        denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(float(denominator)) < 1.0e-9:
            continue
        minimum_x = max(0, int(math.floor(float(points[:, 0].min()))))
        maximum_x = min(WIDTH - 1, int(math.ceil(float(points[:, 0].max()))))
        minimum_y = max(0, int(math.floor(float(points[:, 1].min()))))
        maximum_y = min(HEIGHT - 1, int(math.ceil(float(points[:, 1].max()))))
        if minimum_x > maximum_x or minimum_y > maximum_y:
            continue
        grid_y, grid_x = np.mgrid[minimum_y : maximum_y + 1, minimum_x : maximum_x + 1]
        sample_x = grid_x + 0.5
        sample_y = grid_y + 0.5
        first = ((y1 - y2) * (sample_x - x2) + (x2 - x1) * (sample_y - y2)) / denominator
        second = ((y2 - y0) * (sample_x - x2) + (x0 - x2) * (sample_y - y2)) / denominator
        third = 1.0 - first - second
        inside = (first >= -1.0e-9) & (second >= -1.0e-9) & (third >= -1.0e-9)
        if not bool(inside.any()):
            continue
        candidate_depth = first * points[0, 2] + second * points[1, 2] + third * points[2, 2]
        current = depth[minimum_y : maximum_y + 1, minimum_x : maximum_x + 1]
        update = inside & (candidate_depth > current)
        if not bool(update.any()):
            continue
        uv = geometry.uvs[face]
        sample_u = first * uv[0, 0] + second * uv[1, 0] + third * uv[2, 0]
        sample_v = first * uv[0, 1] + second * uv[1, 1] + third * uv[2, 1]
        texture_x = np.clip(np.floor(sample_u * WIDTH).astype(np.int32), 0, WIDTH - 1)
        texture_y = np.clip(np.floor(sample_v * HEIGHT).astype(np.int32), 0, HEIGHT - 1)
        sampled_semantic = semantic_atlas[texture_y, texture_x]
        sampled_material = material_atlas[texture_y, texture_x]
        normals = geometry.normals[face]
        interpolated = (
            first[:, :, None] * normals[0]
            + second[:, :, None] * normals[1]
            + third[:, :, None] * normals[2]
        )
        normal_length = np.linalg.norm(interpolated, axis=2)
        normal_length[normal_length < 1.0e-12] = 1.0
        facing = np.abs((interpolated @ frame.depth) / normal_length)
        brightness = 0.74 + 0.26 * facing
        shaded = sampled_material.copy()
        shaded[:, :, :3] = np.clip(
            sampled_material[:, :, :3].astype(np.float64) * brightness[:, :, None],
            0, 255,
        ).astype(np.uint8)

        current[update] = candidate_depth[update]
        region_semantic = semantic[minimum_y : maximum_y + 1, minimum_x : maximum_x + 1]
        region_image = image[minimum_y : maximum_y + 1, minimum_x : maximum_x + 1]
        region_shell = shell[minimum_y : maximum_y + 1, minimum_x : maximum_x + 1]
        region_active = active[minimum_y : maximum_y + 1, minimum_x : maximum_x + 1]
        region_semantic[update] = sampled_semantic[update]
        region_image[update] = shaded[update]
        region_shell[update] = True
        sampled_active = (
            sampled_semantic[:, :, 0].astype(np.uint16)
            + sampled_semantic[:, :, 1].astype(np.uint16)
        ) > 0
        region_active[update] = sampled_active[update]
    return Render(image=image, semantic=semantic, shell=shell, active=active)


def _triangle_area(points: np.ndarray) -> float:
    return 0.5 * float(np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[0])))


def sampled_surface_metrics(
    geometry: Geometry,
    faces: np.ndarray,
    atlas: np.ndarray,
    subdivisions: int = 10,
) -> dict[str, object]:
    """Estimate physical active area with a fixed barycentric sampling lattice."""

    require(subdivisions >= 2, "surface sampling subdivisions must be at least two")
    weights = np.asarray([
        (first / subdivisions, second / subdivisions,
         1.0 - first / subdivisions - second / subdivisions)
        for first in range(subdivisions + 1)
        for second in range(subdivisions + 1 - first)
    ], dtype=np.float64)
    total_area = 0.0
    active_area = 0.0
    active_points: list[np.ndarray] = []
    for face in faces:
        points = geometry.positions[face]
        area = _triangle_area(points)
        total_area += area
        uv = weights @ geometry.uvs[face]
        x_values = np.clip(np.floor(uv[:, 0] * WIDTH).astype(np.int32), 0, WIDTH - 1)
        y_values = np.clip(np.floor(uv[:, 1] * HEIGHT).astype(np.int32), 0, HEIGHT - 1)
        samples = atlas[y_values, x_values]
        active = samples[:, 0].astype(np.uint16) + samples[:, 1].astype(np.uint16) > 0
        active_area += area * float(active.mean())
        if bool(active.any()):
            active_points.append((weights[active] @ points))
    require(total_area > 0.0, f"{geometry.spec.name} surface area is zero")
    all_positions = geometry.positions[np.unique(faces)]
    result: dict[str, object] = {
        "sample_lattice_subdivisions": subdivisions,
        "sample_count_per_triangle": len(weights),
        "surface_area_cm2": total_area,
        "estimated_active_area_cm2": active_area,
        "estimated_active_area_fraction": active_area / total_area,
        "shell_bounds_cm": {
            "minimum": all_positions.min(axis=0).tolist(),
            "maximum": all_positions.max(axis=0).tolist(),
        },
    }
    if active_points:
        points = np.concatenate(active_points, axis=0)
        minimum = points.min(axis=0)
        maximum = points.max(axis=0)
        shell_minimum = all_positions.min(axis=0)
        shell_maximum = all_positions.max(axis=0)
        shell_span = shell_maximum - shell_minimum
        result["active_bounds_cm"] = {"minimum": minimum.tolist(), "maximum": maximum.tolist()}
        result["active_span_fraction_of_shell"] = [
            float((maximum[axis] - minimum[axis]) / shell_span[axis])
            if shell_span[axis] > 1.0e-9 else None
            for axis in range(3)
        ]
    else:
        result["active_bounds_cm"] = None
        result["active_span_fraction_of_shell"] = None
    return result


def mask_metrics(first: Render, second: Render) -> dict[str, object]:
    """Compare two renders in their shared fixed orthographic frame."""

    shell_union = first.shell | second.shell
    shell_intersection = first.shell & second.shell
    active_union = first.active | second.active
    active_intersection = first.active & second.active
    exact = np.all(first.semantic == second.semantic, axis=2)
    comparable = shell_intersection
    return {
        "shell_iou": float(shell_intersection.sum() / max(1, shell_union.sum())),
        "active_art_iou": float(active_intersection.sum() / max(1, active_union.sum())),
        "shell_pixel_count_first": int(first.shell.sum()),
        "shell_pixel_count_second": int(second.shell.sum()),
        "active_pixel_count_first": int(first.active.sum()),
        "active_pixel_count_second": int(second.active.sum()),
        "semantic_exact_fraction_on_shell_intersection": float(
            exact[comparable].mean() if comparable.any() else 0.0
        ),
    }


def seam_metrics(geometry: Geometry, atlas: np.ndarray) -> dict[str, object]:
    """Pair duplicated x=0 side vertices and compare their sampled semantics."""

    rows: dict[str, list[int]] = {}
    for side in ("right", "left"):
        used = np.unique(geometry.side_faces[side])
        rows[side] = [int(index) for index in used if abs(geometry.positions[index, 0]) <= 1.0e-9]
    right = rows["right"]
    left = rows["left"]
    candidates = sorted(
        (
            float(np.linalg.norm(geometry.positions[r, 1:] - geometry.positions[l, 1:])),
            r, l,
        )
        for r in right for l in left
    )
    pairs: list[tuple[float, int, int]] = []
    used_right: set[int] = set()
    used_left: set[int] = set()
    for distance, r_value, l_value in candidates:
        if r_value not in used_right and l_value not in used_left:
            used_right.add(r_value)
            used_left.add(l_value)
            pairs.append((distance, r_value, l_value))
    semantic_matches = 0
    maximum_channel_error = 0
    for _distance, right_index, left_index in pairs:
        colors = []
        for vertex in (right_index, left_index):
            uv = geometry.uvs[vertex]
            x_value = min(WIDTH - 1, max(0, int(math.floor(uv[0] * WIDTH))))
            y_value = min(HEIGHT - 1, max(0, int(math.floor(uv[1] * HEIGHT))))
            colors.append(atlas[y_value, x_value].astype(np.int16))
        difference = np.abs(colors[0] - colors[1])
        maximum_channel_error = max(maximum_channel_error, int(difference.max()))
        semantic_matches += int(bool(np.all(difference == 0)))
    return {
        "right_seam_vertex_count": len(right),
        "left_seam_vertex_count": len(left),
        "paired_vertex_count": len(pairs),
        "unpaired_right_vertex_count": len(right) - len(pairs),
        "unpaired_left_vertex_count": len(left) - len(pairs),
        "maximum_paired_position_error_cm": max((row[0] for row in pairs), default=0.0),
        "semantic_exact_pair_fraction": semantic_matches / max(1, len(pairs)),
        "maximum_semantic_channel_error": maximum_channel_error,
    }


def _save_png(path: Path, pixels: np.ndarray) -> None:
    Image.fromarray(pixels, mode="RGBA").save(path, format="PNG", optimize=False)


def _contact_sheet(paths: Sequence[tuple[str, Path]], destination: Path) -> None:
    sheet = Image.new("RGBA", (1536, 1024), tuple(BACKGROUND.tolist()))
    draw = ImageDraw.Draw(sheet)
    for number, (label, path) in enumerate(paths):
        with Image.open(path) as source:
            source.load()
            image = source.convert("RGBA")
        x_value = (number % 3) * 512
        y_value = (number // 3) * 512
        sheet.alpha_composite(image, (x_value, y_value))
        draw.rectangle((x_value + 8, y_value + 8, x_value + 188, y_value + 34),
                       fill=(8, 11, 16, 224))
        draw.text((x_value + 14, y_value + 14), label.upper(), fill=(255, 255, 255, 255))
    sheet.save(destination, format="PNG", optimize=False)


def _resolve_target(
    input_0a: Path,
    asset_index: int | None,
    outer_entry: int | None,
    appearance_slot: int,
    bank_name: str,
    palette_override: tuple[int, int, int] | None = None,
) -> tuple[int, int, tuple[int, int, int], dict[str, object]]:
    bank = None
    selector_asset: int | None = None
    if asset_index is None or palette_override is None:
        try:
            selected_appearance = appearance.read_appearance(input_0a, appearance_slot)
        except appearance.CustomTeamAppearanceError as exc:
            raise ProofError(f"could not decode custom-team appearance slot: {exc}") from exc
        bank = selected_appearance.home if bank_name == "home" else selected_appearance.away
        selector_asset = bank.logo_selector[0]
    require(asset_index is not None or selector_asset is not None,
            "crest asset cannot be inferred without an appearance selector")
    wanted_asset = selector_asset if asset_index is None else asset_index
    assert wanted_asset is not None
    require(0 <= wanted_asset < apf_team_crests.CATALOG_SLOT_COUNT,
            "crest asset index is outside 0..117")
    slots = {row.asset_index: row for row in apf_team_crests.crest_slots(input_0a)}
    require(wanted_asset in slots, f"crest asset index {wanted_asset} is absent from archive")
    resolved_outer = slots[wanted_asset].outer_entry_index
    if outer_entry is not None:
        require(outer_entry == resolved_outer,
                f"crest outer {outer_entry} does not own asset {wanted_asset}; expected {resolved_outer}")
    if palette_override is None:
        assert bank is not None
        shell_index = bank.helmet_selector[1]
        require(shell_index < len(bank.palette), "helmet shell palette selector is out of bounds")
        colors = (bank.palette[shell_index], bank.palette[0], bank.palette[2])
        palette_source = "custom_team_appearance"
    else:
        require(all(0 <= value <= 0xFFFFFFFF for value in palette_override),
                "palette override contains a value outside ARGB32")
        shell_index = None
        colors = palette_override
        palette_source = "explicit_cli_argb_override"
    return wanted_asset, resolved_outer, colors, {
        "palette_source": palette_source,
        "appearance_slot": appearance_slot if bank is not None else None,
        "appearance_bank": bank_name if bank is not None else None,
        "appearance_logo_selector_asset_index": selector_asset,
        "selected_asset_matches_appearance_selector": (
            wanted_asset == selector_asset if selector_asset is not None else None
        ),
        "shell_palette_index": shell_index,
        "shell_argb": f"{colors[0]:08X}",
        "red_region_palette_0_argb": f"{colors[1]:08X}",
        "green_region_palette_2_argb": f"{colors[2]:08X}",
    }


def _prepare_from_parse_path(
    input_0a: Path,
    parse_0a: Path,
    output: Path,
    *,
    asset_index: int | None = None,
    outer_entry: int | None = None,
    appearance_slot: int = 32,
    bank_name: str = "home",
    palette_override: tuple[int, int, int] | None = None,
    parse_view_receipt: Mapping[str, object] | None = None,
) -> dict[str, object]:
    input_0a = Path(os.path.abspath(os.fspath(Path(input_0a).expanduser())))
    output = Path(os.path.abspath(os.fspath(Path(output).expanduser())))
    require(input_0a.is_file() and not input_0a.is_symlink(),
            f"input 0A is not a regular non-symlink file: {input_0a}")
    require(not output.exists() and not output.is_symlink(),
            f"refusing to overwrite proof destination: {output}")
    require(output.parent.is_dir(), f"proof parent directory does not exist: {output.parent}")
    input_sha256_before = sha256_file(input_0a)
    selected_asset, selected_outer, colors, appearance_receipt = _resolve_target(
        parse_0a, asset_index, outer_entry, appearance_slot, bank_name,
        palette_override,
    )
    try:
        archive = apf_outer.parse_archive(parse_0a)
    except apf_outer.FormatError as exc:
        raise ProofError(f"could not parse input archive: {exc}") from exc
    with apf_inner.ArchiveReader(archive) as reader:
        system, helmet_receipt = _read_helmet_system(archive, reader)
        l0, l1, package_receipt = _read_layers(archive, reader, selected_outer)
    geometries = [_decode_geometry(system, spec) for spec in LODS]
    atlas_metrics = _validate_atlas(l0.rgba)
    semantic_atlas = np.frombuffer(l0.rgba, dtype=np.uint8).reshape((HEIGHT, WIDTH, 4))
    material_atlas = colorize_atlas(l0.rgba, *colors)

    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        renders: dict[str, dict[str, Render]] = {geometry.spec.name: {} for geometry in geometries}
        image_rows: dict[str, dict[str, object]] = {}
        frames = {name: _frame(name, geometries) for name in VIEW_NAMES}
        for geometry in geometries:
            row: dict[str, object] = {}
            for view_name in VIEW_NAMES:
                rendered = rasterize(
                    geometry, geometry.faces, semantic_atlas, material_atlas, frames[view_name],
                )
                renders[geometry.spec.name][view_name] = rendered
                path = stage / f"helmet-shell-{geometry.spec.name}-{view_name}.png"
                _save_png(path, rendered.image)
                row[view_name] = {
                    "file": path.name,
                    "sha256": sha256_file(path),
                    "shell_pixel_count": int(rendered.shell.sum()),
                    "active_art_pixel_count": int(rendered.active.sum()),
                }
            image_rows[geometry.spec.name] = row
            _contact_sheet(
                [(name, stage / str(row[name]["file"])) for name in VIEW_NAMES],
                stage / f"helmet-shell-{geometry.spec.name}-contact-sheet.png",
            )

        for geometry in geometries:
            for side in ("right", "left"):
                require(
                    renders[geometry.spec.name][f"side-{side}"].active.any(),
                    f"{geometry.spec.name} side-{side} render contains no active art",
                )

        bilateral = {
            geometry.spec.name: mask_metrics(
                renders[geometry.spec.name]["side-right"],
                renders[geometry.spec.name]["side-left"],
            )
            for geometry in geometries
        }
        lod_parity = {
            view_name: mask_metrics(
                renders["helmet_hi"][view_name], renders["helmet_lo"][view_name],
            )
            for view_name in VIEW_NAMES
        }
        geometry_rows: dict[str, object] = {}
        for geometry in geometries:
            used = np.unique(geometry.faces)
            geometry_rows[geometry.spec.name] = {
                "draw_1_material": geometry.material_before_route,
                "draw_1_uses_crest_material_2": True,
                "draw_2_triangle_count": geometry.overlay_triangle_count,
                "draw_2_degenerate": True,
                "exterior_triangle_count": len(geometry.faces),
                "exterior_vertex_count": len(used),
                "triangles_per_side": {
                    key: len(value) for key, value in geometry.side_faces.items()
                },
                "uv_domain": {
                    "minimum": geometry.uvs[used].min(axis=0).tolist(),
                    "maximum": geometry.uvs[used].max(axis=0).tolist(),
                },
                "surface_coverage": {
                    side: sampled_surface_metrics(geometry, geometry.side_faces[side], semantic_atlas)
                    for side in ("right", "left")
                },
                "x_zero_seam": seam_metrics(geometry, semantic_atlas),
            }

        input_sha256_after = sha256_file(input_0a)
        require(input_sha256_after == input_sha256_before,
                "input 0A changed while the static proof was being prepared")
        proof: dict[str, object] = {
            "schema": SCHEMA,
            "claim": CLAIM,
            "proof_eligible_for_runtime_or_visual_quality_claim": False,
            "limitations": [
                "static asset-space software rendering only; no emulator/gameplay/hardware execution",
                "does not prove which logo layer a runtime LOD samples",
                "does not independently inventory nonselected crest packages",
                "no visual-quality claim is made by numeric metrics or generated images",
            ],
            "source": {
                "input_0a": str(input_0a),
                "input_0a_size": input_0a.stat().st_size,
                "input_0a_sha256": input_sha256_before,
                "opened_read_only": True,
                "source_modified": False,
                "standalone_parse_view": dict(parse_view_receipt or {"used": False}),
                "helmet": helmet_receipt,
                "crest_package": {
                    **package_receipt,
                    "asset_index": selected_asset,
                    "package_name": f"uniform_logo_{selected_asset:02d}.iff",
                    "logo_l0": {
                        "base_sha256": l0.base_sha256,
                        "mip_sha256": l0.mip_sha256,
                        "decoded_rgba_sha256": l0.decoded_rgba_sha256,
                    },
                    "logo_l1": {
                        "base_sha256": l1.base_sha256,
                        "mip_sha256": l1.mip_sha256,
                        "decoded_rgba_sha256": l1.decoded_rgba_sha256,
                    },
                },
                "appearance": appearance_receipt,
            },
            "atlas": atlas_metrics,
            "geometry": geometry_rows,
            "metrics": {
                "bilateral_screen_space": bilateral,
                "high_low_screen_space": lod_parity,
            },
            "render_contract": {
                "renderer": "deterministic_numpy_orthographic_triangle_zbuffer_v1",
                "resolution": [WIDTH, HEIGHT],
                "views": list(VIEW_NAMES),
                "texture_sampling": "nearest_floor_clamped_to_exact_512_atlas",
                "shading": "view_aligned_symmetric_ambient_0.74_plus_facing_0.26",
                "palette_equation": (
                    "shell*(255-red-green)/255 + palette[0]*red/255 + "
                    "palette[2]*green/255; nearest integer rounding"
                ),
                "layer_binding_independent": True,
                "no_gui": True,
                "no_emulator": True,
            },
            "renders": image_rows,
        }
        for lod_name in ("helmet_hi", "helmet_lo"):
            contact = stage / f"helmet-shell-{lod_name}-contact-sheet.png"
            proof["renders"][lod_name]["contact_sheet"] = {  # type: ignore[index]
                "file": contact.name, "sha256": sha256_file(contact),
            }
        receipt = stage / "helmet-shell-static-proof.json"
        receipt.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        stage.rename(output)
        return proof
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def prepare(
    input_0a: Path,
    output: Path,
    *,
    asset_index: int | None = None,
    outer_entry: int | None = None,
    appearance_slot: int = 32,
    bank_name: str = "home",
    palette_override: tuple[int, int, int] | None = None,
    sibling_source_0a: Path | None = None,
) -> dict[str, object]:
    """Render either a complete archive folder or one standalone copied 0A."""

    normalized_input = Path(os.path.abspath(os.fspath(Path(input_0a).expanduser())))
    normalized_output = Path(os.path.abspath(os.fspath(Path(output).expanduser())))
    require(
        normalized_input.is_file() and not normalized_input.is_symlink(),
        f"input 0A is not a regular non-symlink file: {normalized_input}",
    )
    require(
        not normalized_output.exists() and not normalized_output.is_symlink(),
        f"refusing to overwrite proof destination: {normalized_output}",
    )
    require(normalized_output.parent.is_dir(),
            f"proof parent directory does not exist: {normalized_output.parent}")
    with _standalone_parse_view(
        normalized_input, sibling_source_0a,
    ) as (parse_0a, parse_view_receipt):
        return _prepare_from_parse_path(
            normalized_input,
            parse_0a,
            normalized_output,
            asset_index=asset_index,
            outer_entry=outer_entry,
            appearance_slot=appearance_slot,
            bank_name=bank_name,
            palette_override=palette_override,
            parse_view_receipt=parse_view_receipt,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-0a", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--asset-index", type=int)
    parser.add_argument("--outer-entry", type=int)
    parser.add_argument("--appearance-slot", type=int, default=32)
    parser.add_argument("--bank", choices=("home", "away"), default="home")
    parser.add_argument(
        "--sibling-source-0a",
        type=Path,
        help=(
            "pristine 0A whose unmodified 0B/1A/1B are linked only inside a "
            "private temporary parse view for a standalone copied input 0A"
        ),
    )
    parser.add_argument("--shell-argb", type=_parse_argb)
    parser.add_argument("--red-region-argb", type=_parse_argb)
    parser.add_argument("--green-region-argb", type=_parse_argb)
    return parser


def _parse_argb(value: str) -> int:
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if text.lower().startswith("0x"):
        text = text[2:]
    if len(text) != 8 or any(character not in "0123456789abcdefABCDEF" for character in text):
        raise argparse.ArgumentTypeError("ARGB colors must contain exactly 8 hex digits")
    return int(text, 16)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    override_values = (
        args.shell_argb, args.red_region_argb, args.green_region_argb,
    )
    if any(value is not None for value in override_values) and not all(
        value is not None for value in override_values
    ):
        print(
            "error: --shell-argb, --red-region-argb, and --green-region-argb "
            "must be supplied together",
            file=sys.stderr,
        )
        return 1
    if all(value is not None for value in override_values):
        shell_argb, red_argb, green_argb = override_values
        assert shell_argb is not None and red_argb is not None and green_argb is not None
        palette_override = (shell_argb, red_argb, green_argb)
    else:
        palette_override = None
    try:
        proof = prepare(
            args.input_0a,
            args.output,
            asset_index=args.asset_index,
            outer_entry=args.outer_entry,
            appearance_slot=args.appearance_slot,
            bank_name=args.bank,
            palette_override=palette_override,
            sibling_source_0a=args.sibling_source_0a,
        )
    except (OSError, ProofError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "ready": True,
        "claim": proof["claim"],
        "output": str(args.output.resolve()),
        "receipt": str((args.output / "helmet-shell-static-proof.json").resolve()),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
