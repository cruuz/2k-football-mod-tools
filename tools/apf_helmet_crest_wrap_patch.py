#!/usr/bin/env python3
"""Build APF 2K8's source-bound, whole-shell helmet crest route.

The retail helmet shell already owns a complete, non-overlapping UV atlas.
This backend keeps that atlas and every shell vertex/index byte exact, routes
shell draw 1 from material 1 to the existing crest material 2, and neutralizes
the old bounded draw-2 overlay with repeated in-range degenerate indices.  A
single-side semantic 512x512 APF region mask is baked into both retail atlas
islands with nearest-neighbour sampling; black inactive texels retain the team
shell term in the recovered palette-weight shader equation.

No executable, emulator, accessory draw, vertex stream, or sibling IFF block
is changed.  The module never copies or writes a 1.1 GB game volume.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_scene  # noqa: E402


SCHEMA = "apf2k8_helmet_shell_atlas_patch/v24"
OPERATION = "route_shell_draw_to_crest_atlas_and_neutralize_overlay"
RECEIPT_SUFFIX = ".apf-helmet-crest-wrap.json"

VOLUME_SIZE = 1_140_850_688
OUTER_INDEX = 1310
OUTER_NAME_ID = 0xDB5E3E48
OUTER_OFFSET = 0x01570800
OUTER_SIZE = 0x017DE800
SOURCE_OUTER_SHA256 = (
    "752bc94e99ae0bc1a3ec732c5b4912ef6ef234149183e76dc059973c714d792d"
)
EXPECTED_OUTPUT_OUTER_SHA256 = (
    "ae51ccdea7124bc9615fe39fda6632363e9bf4270e0b623b0707635fcd701323"
)
INNER_INDEX = 128
INNER_FILE_ID = 0x4A3503FC
INNER_NAME = "helmet_00"
INNER_TYPE = "SCNE"
BLOCK_COUNT = 3
SYSTEM_BLOCK_INDEX = 0
SYSTEM_PART_OFFSET = 0x00173680
SYSTEM_LENGTH = 0x000D5680
SOURCE_SYSTEM_SHA256 = (
    "5c121fcf01b96f2e087e9238584a511868b09ad60476658d023eb186f33dc1bb"
)
EXPECTED_OUTPUT_SYSTEM_SHA256 = (
    "bd49f04cb2bf58fc91f024af6a76405f3cefab3f63d2d98f445a413b67ef5ca7"
)
MAX_DECOMPRESSED = 128 * 1024 * 1024
# The candidate-4 allocation audit found 64 search candidates 3,875 bytes too
# large and 96 candidates 7,151 bytes inside the fixed outer slot.  Keep the
# smallest proved depth: it cuts fallback time by more than half while retaining
# deterministic headroom.
MAX_H7A_CANDIDATES = 96

STRIDE = 32
CANVAS_WIDTH = 512
CANVAS_HEIGHT = 512
RGBA_LENGTH = CANVAS_WIDTH * CANVAS_HEIGHT * 4
# Fixed semantic placement envelope for the stock shell atlas.  Unlike v20,
# this never normalizes against the art's active bounding box: moving art in X
# or Y therefore moves it along the physical helmet.  Y=3 cm is the audited
# lower bound above the ear/opening discontinuity in both retail LODs.
SEMANTIC_FRONT_Z = 13.15
SEMANTIC_REAR_Z = -11.16
SEMANTIC_TOP_Y = 18.87
SEMANTIC_BOTTOM_Y = 3.0
# The opaque-shell-body contract replaced the v24 Eagles regression design
# (sha c9a915df7f66dae85a5f620ad4907aadc2cf3f4941fcfc86a074c68a34362d6c),
# whose uniform 0x88 alpha rendered the routed shell semi-transparent in game.
# The pinned regression input is the same RGB lattice with every alpha raised
# to the opaque transport value.
EAGLES_REGRESSION_DESIGN_RGBA_SHA256 = (
    "ff3ebf78fda1b336cb03c5830511c3dc17bb5efd5e8eaa4792fd669fdc851cc7"
)
# Retail bounded crests transport a constant 8/15 (0x88) alpha sentinel in the
# Xenos 4_4_4_4 crest layers; that value is correct for the retail decal lane
# but acts as transparency once the whole shell is drawn through the crest
# material, so the full-shell lane requires an opaque shell body instead.
RETAIL_CREST_TRANSPORT_ALPHA = 0x88
OPAQUE_SHELL_ALPHA = 255
MATERIAL_FIELD_OFFSETS = {"helmet_hi": 0x00009A10, "helmet_lo": 0x000CCAD0}
SHELL_DRAW_INDEX = 1
CARRIER_DRAW_INDEX = 2
DRAW_RECORD_SIZE = 0x30
DRAW_RECORD_COUNT = 13
SOURCE_SHELL_MATERIAL = 1
CREST_MATERIAL = 2


class PatchError(ValueError):
    """The fixed source, geometry contract, or rebuild failed closed."""


@dataclass(frozen=True)
class LodSpec:
    node_index: int
    node_name: str
    draw_record_offset: int
    index_offset: int
    index_count: int
    shell_index_start: int
    shell_index_count: int
    shell_vertex_start: int
    shell_vertex_count: int
    carrier_index_start: int
    carrier_index_count: int
    carrier_vertex_start: int
    carrier_vertex_count: int
    stream_start: int
    vertex_count: int
    center: tuple[float, float, float]
    scale: tuple[float, float, float]
    shell_triangle_count: int
    carrier_triangle_count: int


LODS = (
    LodSpec(
        0, "helmet_hi", 0x000099C0, 0x00009C30, 9773,
        2623, 4800, 1312, 1427, 7423, 1046, 2739, 326,
        0x0000EA1C, 3856,
        (0.0, 4.927330017089844, 1.7508296966552734),
        (13.967263221740723,) * 3, 2464, 536,
    ),
    LodSpec(
        32, "helmet_lo", 0x000CCA80, 0x000CCCF0, 1552,
        359, 659, 193, 283, 1018, 231, 476, 128,
        0x000CDA9C, 799,
        (0.0, 2.8593978881835938, 2.8941473960876465),
        (16.119155883789062,) * 3, 432, 184,
    ),
)


@dataclass(frozen=True)
class SourceEntry:
    entry: apf_outer.Entry
    raw: bytes
    record: apf_inner.IFFRecord
    stored: tuple[bytes, ...]
    blocks: tuple[bytes, ...]
    system: bytes


@dataclass(frozen=True)
class PatchResult:
    rebuilt_entry: bytes
    atlas_rgba: bytes
    manifest: dict[str, Any]


class _BytesReader:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self, _entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.payload):
            raise apf_inner.FormatError("memory IFF read exceeds outer allocation")
        return self.payload[offset : offset + size]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _fixed_entry() -> apf_outer.Entry:
    return apf_outer.Entry(
        table_index=OUTER_INDEX,
        name_id=OUTER_NAME_ID,
        offset_blocks=OUTER_OFFSET // 2048,
        size_blocks=OUTER_SIZE // 2048,
        virtual_offset=OUTER_OFFSET,
        size=OUTER_SIZE,
        head_hex="ff3bef94",
        segments=(
            apf_outer.Segment(
                pack_ordinal=0,
                pack_name="0A",
                pack_offset=OUTER_OFFSET,
                size=OUTER_SIZE,
            ),
        ),
    )


def _dot(a: Iterable[float], b: Iterable[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _mul(
    a: tuple[float, float, float], scalar: float,
) -> tuple[float, float, float]:
    return tuple(component * scalar for component in a)  # type: ignore[return-value]


def _length(a: tuple[float, float, float]) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: tuple[float, float, float]) -> tuple[float, float, float]:
    length = _length(a)
    if not math.isfinite(length) or length <= 1.0e-12:
        raise PatchError("could not normalize a carrier vector")
    return _mul(a, 1.0 / length)


def _snorm(word: int) -> float:
    return max(word / 32767.0, -1.0)


def _decode_vec3(payload: bytes, offset: int) -> tuple[float, float, float]:
    return tuple(
        _snorm(word) for word in struct.unpack_from(">3h", payload, offset)
    )  # type: ignore[return-value]


def _decode_position(
    payload: bytes, spec: LodSpec, vertex: int,
) -> tuple[float, float, float]:
    raw = _decode_vec3(payload, spec.stream_start + vertex * STRIDE)
    return tuple(
        spec.center[index] + raw[index] * spec.scale[index]
        for index in range(3)
    )  # type: ignore[return-value]


def _uv(payload: bytes, spec: LodSpec, vertex: int) -> tuple[float, float]:
    start = spec.stream_start + vertex * STRIDE
    return (
        2.0 * _snorm(struct.unpack_from(">h", payload, start + 14)[0]),
        2.0 * _snorm(struct.unpack_from(">h", payload, start + 22)[0]),
    )


def _indices(payload: bytes, spec: LodSpec) -> list[int]:
    end = spec.index_offset + spec.index_count * 2
    if end > len(payload):
        raise PatchError(f"{spec.node_name} index table is truncated")
    return list(
        struct.unpack_from(f">{spec.index_count}H", payload, spec.index_offset)
    )


def _triangles(indices: list[int]) -> list[tuple[int, int, int]]:
    output: list[tuple[int, int, int]] = []
    strip: list[int] = []
    for index in indices:
        if index == 0xFFFF:
            strip.clear()
            continue
        strip.append(index)
        if len(strip) < 3:
            continue
        number = len(strip) - 3
        a, b, c = strip[-3:]
        if number & 1:
            a, b = b, a
        if len({a, b, c}) == 3:
            output.append((a, b, c))
    return output


def _validate_layout(payload: bytes, spec: LodSpec, node: Mapping[str, Any]) -> None:
    if (
        node.get("name") != spec.node_name
        or node.get("draw_record_offset") != spec.draw_record_offset
        or node.get("index_offset") != spec.index_offset
        or node.get("index_count") != spec.index_count
        or node.get("index_component_bits") != 16
    ):
        raise PatchError(f"{spec.node_name} scene identity drift")
    meshes = node.get("meshes")
    if not isinstance(meshes, list) or len(meshes) != 1:
        raise PatchError(f"{spec.node_name} mesh inventory drift")
    streams = meshes[0].get("streams")
    if (
        meshes[0].get("vertex_count") != spec.vertex_count
        or not isinstance(streams, list)
        or len(streams) != 1
        or streams[0].get("start") != spec.stream_start
        or streams[0].get("stride") != STRIDE
    ):
        raise PatchError(f"{spec.node_name} vertex stream drift")
    declarations = node.get("vertex_declarations")
    wanted = [
        ("POSITION0", 0, "snorm16x4"),
        ("NORMAL0", 8, "snorm16x4"),
        ("TANGENT0", 16, "snorm16x4"),
        ("BLENDINDICES0", 24, "uint8x4"),
        ("BLENDWEIGHT0", 28, "unorm8x4"),
    ]
    actual = [
        (
            item.get("indexed_semantic"),
            item.get("byte_offset"),
            item.get("format_name"),
        )
        for item in declarations
    ] if isinstance(declarations, list) else []
    if actual != wanted:
        raise PatchError(f"{spec.node_name} declaration layout drift")
    draws = [
        struct.unpack_from(">12I", payload, spec.draw_record_offset + index * 0x30)
        for index in range(3)
    ]
    expected = (
        (
            spec.shell_index_start,
            spec.shell_index_count,
            spec.shell_vertex_start,
            spec.shell_vertex_count,
            1,
        ),
        (
            spec.carrier_index_start,
            spec.carrier_index_count,
            spec.carrier_vertex_start,
            spec.carrier_vertex_count,
            2,
        ),
    )
    for record, wanted_draw in zip(draws[1:3], expected):
        if (record[1], record[2], record[5], record[6], record[8]) != wanted_draw:
            raise PatchError(f"{spec.node_name} shell/carrier draw window drift")


def _require_rgba(value: bytes | bytearray | memoryview, label: str) -> bytes:
    try:
        payload = bytes(value)
    except (TypeError, ValueError) as exc:
        raise PatchError(f"{label} must be a bytes-like 512x512 RGBA payload") from exc
    if len(payload) != RGBA_LENGTH:
        raise PatchError(
            f"{label} has {len(payload)} bytes; expected {RGBA_LENGTH} "
            "for a 512x512 RGBA payload"
        )
    return payload


def _parse_outer(
    payload: bytes,
    *,
    source: bool,
    expected_output_sha256: str | None = None,
    expected_system_sha256: str | None = None,
) -> SourceEntry:
    expected_hash = SOURCE_OUTER_SHA256 if source else expected_output_sha256
    label = "source" if source else "output"
    if len(payload) != OUTER_SIZE or (
        expected_hash is not None and sha256_bytes(payload) != expected_hash
    ):
        raise PatchError(f"outer 1310 is not the pinned {label} allocation")
    entry = _fixed_entry()
    reader = _BytesReader(payload)
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
        raise PatchError(f"could not parse pinned {label} global.iff: {exc}") from exc
    if record.warnings or record.block_count != BLOCK_COUNT:
        raise PatchError(f"{label} global.iff block inventory drift")
    try:
        item = record.files[INNER_INDEX]
    except IndexError as exc:
        raise PatchError("helmet_00 inner index is missing") from exc
    if (
        item.file_id != INNER_FILE_ID
        or item.name != INNER_NAME
        or item.type_name != INNER_TYPE
        or len(item.parts) != 1
        or item.parts[0].block_index != SYSTEM_BLOCK_INDEX
        or item.parts[0].offset != SYSTEM_PART_OFFSET
        or item.parts[0].length != SYSTEM_LENGTH
    ):
        raise PatchError("helmet_00 SCNE ownership drift")
    part = item.parts[0]
    system = blocks[part.block_index][part.offset : part.offset + part.length]
    wanted_system = SOURCE_SYSTEM_SHA256 if source else expected_system_sha256
    if len(system) != SYSTEM_LENGTH or (
        wanted_system is not None and sha256_bytes(system) != wanted_system
    ):
        raise PatchError(f"helmet_00 SCNE is not the pinned {label} payload")
    return SourceEntry(entry, payload, record, stored, blocks, system)


def _scene_nodes(payload: bytes) -> list[dict[str, Any]]:
    try:
        scene = apf_scene.parse_scene_system_part(
            payload,
            outer_index=OUTER_INDEX,
            inner_index=INNER_INDEX,
            capture_geometry=True,
        )
    except apf_scene.SceneError as exc:
        raise PatchError(f"helmet_00 geometry parse failed: {exc}") from exc
    nodes = scene.get("nodes")
    if not isinstance(nodes, list):
        raise PatchError("helmet node inventory is missing")
    return nodes


def _h7a_match_length(
    data: bytes, current: int, candidate: int, maximum: int,
) -> int:
    length = 0
    while length < maximum and data[current + length] == data[candidate + length]:
        length += 1
    return length


def _compress_h7a_bounded(data: bytes, shift: int) -> bytes:
    """Memory-bounded, non-overlapping H7A encoder for a tight outer slot."""

    if not 1 <= shift <= 15:
        raise PatchError(f"invalid H7A shift {shift}")
    max_distance = (1 << shift) - 1
    max_length = ((1 << (16 - shift)) - 1) + 3
    positions: dict[bytes, deque[int]] = defaultdict(deque)
    output = bytearray()
    cursor = 0

    def remember(position: int) -> None:
        if position + 3 > len(data):
            return
        key = data[position : position + 3]
        positions[key].append(position)
        expired = position - max_distance - 1
        if expired >= 0 and expired + 3 <= len(data):
            expired_key = data[expired : expired + 3]
            bucket = positions.get(expired_key)
            if bucket is not None:
                while bucket and bucket[0] <= expired:
                    bucket.popleft()
                if not bucket:
                    del positions[expired_key]

    def best_match(at: int) -> tuple[int, int]:
        best_length = 0
        best_distance = 0
        if at + 3 <= len(data):
            bucket = positions.get(data[at : at + 3])
            if bucket:
                minimum = at - max_distance
                candidates = 0
                for candidate in reversed(bucket):
                    if candidate < minimum:
                        break
                    distance = at - candidate
                    if distance <= 0:
                        continue
                    length = _h7a_match_length(
                        data,
                        at,
                        candidate,
                        min(max_length, len(data) - at),
                    )
                    # Console-safe retail streams never read bytes still being
                    # emitted, so cap each match at its backwards distance.
                    length = min(length, distance)
                    if length < 3:
                        continue
                    if length > best_length or (
                        length == best_length and distance > best_distance
                    ):
                        best_length = length
                        best_distance = distance
                        if best_length == max_length:
                            break
                    candidates += 1
                    if candidates >= MAX_H7A_CANDIDATES:
                        break
        return best_length, best_distance

    while cursor < len(data):
        descriptor_offset = len(output)
        output.append(0)
        descriptor = 0
        for bit in range(8):
            if cursor >= len(data):
                break
            best_length, best_distance = best_match(cursor)
            if 3 <= best_length < max_length and cursor + 1 < len(data):
                ahead_length, _ahead_distance = best_match(cursor + 1)
                if ahead_length > best_length:
                    best_length = 0
            if best_length >= 3:
                descriptor |= 1 << bit
                output.extend(
                    (((best_length - 3) << shift) | best_distance).to_bytes(2, "big")
                )
                consumed = best_length
            else:
                output.append(data[cursor])
                consumed = 1
            for position in range(cursor, cursor + consumed):
                remember(position)
            cursor += consumed
        output[descriptor_offset] = descriptor
    encoded = bytes(output)
    if apf_inner.decompress_h7a(encoded, len(data), shift) != data:
        raise PatchError("bounded H7A encode/decode is not exact")
    return encoded


def _rebuild_entry(
    source: SourceEntry, new_block0: bytes,
) -> tuple[bytes, dict[str, int], int]:
    descriptor = source.record.blocks[0]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise PatchError("helmet DRAM block lost its H7A wrapper")
    try:
        encoded, metrics = apf_inner.encode_h7a_preserving_tokens(
            source.stored[0][apf_inner.H7A_HEADER_SIZE :],
            source.blocks[0],
            new_block0,
            descriptor.wrapper.shift,
        )
    except apf_inner.FormatError as exc:
        raise PatchError(f"could not preservation-encode helmet DRAM: {exc}") from exc
    if source.record.footer is None:
        raise PatchError("global.iff name footer is missing")
    footer_size = 8 + source.record.footer.payload_size
    footer = source.raw[
        source.record.file_length : source.record.file_length + footer_size
    ]
    tail = source.raw[source.record.file_length + footer_size :]
    if len(footer) != footer_size or any(tail):
        raise PatchError("global.iff footer or zero-allocation tail drift")

    def assemble(first_stored: bytes) -> tuple[bytes, int]:
        stored = (first_stored, *source.stored[1:])
        header = bytearray(source.raw[: source.record.header_size])
        body = bytearray()
        cursor = source.record.header_size
        for index, (old, payload) in enumerate(zip(source.record.blocks, stored)):
            struct.pack_into(
                ">8I",
                header,
                apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
                old.name_hash,
                old.type_hash,
                old.unknown_08,
                old.uncompressed_length,
                old.unknown_10,
                cursor,
                len(payload),
                old.indexed,
            )
            body.extend(payload)
            cursor += len(payload)
        struct.pack_into(">I", header, 0x08, cursor)
        return bytes(header) + bytes(body) + footer, cursor

    def wrapped(encoded_payload: bytes) -> bytes:
        return struct.pack(
            ">5I",
            apf_inner.H7A_MAGIC,
            len(new_block0),
            apf_inner.H7A_HEADER_SIZE + len(encoded_payload),
            descriptor.unknown_10,
            descriptor.wrapper.shift,
        ) + encoded_payload

    changed_stored = wrapped(encoded)
    active, cursor = assemble(changed_stored)
    metrics["preservation_encoded_payload_bytes"] = len(encoded)
    metrics["bounded_fallback_used"] = 0
    if len(active) > OUTER_SIZE:
        encoded = _compress_h7a_bounded(new_block0, descriptor.wrapper.shift)
        changed_stored = wrapped(encoded)
        active, cursor = assemble(changed_stored)
        metrics["bounded_fallback_used"] = 1
        metrics["bounded_encoded_payload_bytes"] = len(encoded)
    if len(active) > OUTER_SIZE:
        raise PatchError(
            "rebuilt global.iff exceeds its fixed allocation by "
            f"{len(active) - OUTER_SIZE} bytes even after bounded H7A compression; "
            "reduce or simplify the visible crest footprint"
        )
    return active + bytes(OUTER_SIZE - len(active)), metrics, cursor


def _validate_design_mask(design: bytes) -> tuple[bytes, int]:
    background = design[:4]
    if background[:3] != b"\0\0\0":
        raise PatchError("design_rgba top-left background must have zero RGB")
    if background[3] != OPAQUE_SHELL_ALPHA:
        raise PatchError(
            "design_rgba shell-body background must be opaque (alpha 255); "
            "the retail bounded-crest 8/15 transport sentinel (alpha 0x88) "
            "renders the routed whole shell semi-transparent in game"
        )
    palette = {design[offset : offset + 4] for offset in range(0, len(design), 4)}
    for color in palette:
        red, green, blue, alpha = color
        if (
            blue != 0
            or red % 17
            or green % 17
            or alpha % 17
            or red + green > 255
        ):
            raise PatchError(
                "design_rgba must be a palette-safe Xenos 4-bit APF region mask "
                "(blue zero, channels on the 17-step lattice, red+green <= 255)"
            )
        if not (red or green or blue) and alpha != OPAQUE_SHELL_ALPHA:
            raise PatchError(
                "design_rgba shell-body texels (zero RGB) must be opaque "
                "(alpha 255); translucent black texels render the routed "
                "helmet shell see-through"
            )
    active = sum(
        bool(design[offset] or design[offset + 1] or design[offset + 2])
        for offset in range(0, len(design), 4)
    )
    if not active:
        raise PatchError("design_rgba has no nonblack visible texels")
    return background, active


def _outer_shell_faces(
    system: bytes, spec: LodSpec,
) -> tuple[
    list[tuple[int, int, int]],
    list[tuple[float, float, float]],
]:
    positions = [
        _decode_position(system, spec, index) for index in range(spec.vertex_count)
    ]
    normals = [
        _unit(_decode_vec3(system, spec.stream_start + index * STRIDE + 8))
        for index in range(spec.vertex_count)
    ]
    words = _indices(system, spec)
    shell = _triangles(words[
        spec.shell_index_start : spec.shell_index_start + spec.shell_index_count
    ])
    if len(shell) != spec.shell_triangle_count:
        raise PatchError(f"{spec.node_name} shell topology drift")
    outer: list[tuple[int, int, int]] = []
    for face in shell:
        center = tuple(
            sum(positions[index][axis] for index in face) / 3.0
            for axis in range(3)
        )
        normal = tuple(
            sum(normals[index][axis] for index in face) for axis in range(3)
        )
        radial = (
            center[0], center[1] - spec.center[1], center[2] - spec.center[2]
        )
        if _dot(normal, radial) > 0.0:
            outer.append(face)
    if not outer:
        raise PatchError(f"{spec.node_name} exterior shell is missing")
    return outer, positions


def _semantic_coordinate(
    point: tuple[float, float, float],
) -> tuple[float, float]:
    """Map a stock shell point to the editor's front-to-rear side canvas."""

    return (
        (SEMANTIC_FRONT_Z - point[2]) / (SEMANTIC_FRONT_Z - SEMANTIC_REAR_Z),
        (SEMANTIC_TOP_Y - point[1]) / (SEMANTIC_TOP_Y - SEMANTIC_BOTTOM_Y),
    )


def _nearest_semantic_pixel(u_value: float, v_value: float) -> int | None:
    if not (0.0 <= u_value <= 1.0 and 0.0 <= v_value <= 1.0):
        return None
    x_value = min(
        CANVAS_WIDTH - 1,
        max(0, round(u_value * CANVAS_WIDTH - 0.5)),
    )
    y_value = min(
        CANVAS_HEIGHT - 1,
        max(0, round(v_value * CANVAS_HEIGHT - 0.5)),
    )
    return y_value * CANVAS_WIDTH + x_value


@lru_cache(maxsize=4)
def _atlas_sample_map(
    system: bytes,
    spec: LodSpec,
    width: int = CANVAS_WIDTH,
    height: int = CANVAS_HEIGHT,
) -> tuple[list[int], dict[str, Any]]:
    """Raster the stock exterior UV atlas to nearest semantic source pixels.

    ``width``/``height`` select the raster resolution of the target texture
    space: 512x512 for the routed crest-layer atlas and 256x1024 for the
    retail ``helmet_color`` shell texture.
    """

    faces, positions = _outer_shell_faces(system, spec)
    vertices = {index for face in faces for index in face}
    uv = {index: _uv(system, spec, index) for index in vertices}
    determinants: list[float] = []
    for face in faces:
        first, second, third = (uv[index] for index in face)
        determinants.append(
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        )
    if min(abs(value) for value in determinants) <= 1.0e-12:
        raise PatchError(f"{spec.node_name} stock shell UV triangle collapsed")
    if min(determinants) < 0.0 < max(determinants):
        raise PatchError(f"{spec.node_name} stock shell UV orientation is mixed")

    right = [
        face for face in faces
        if all(positions[index][0] >= -1.0e-6 for index in face)
    ]
    left = [
        face for face in faces
        if all(positions[index][0] <= 1.0e-6 for index in face)
    ]
    if len(right) != len(left) or len(right) + len(left) != len(faces):
        raise PatchError(f"{spec.node_name} stock atlas does not split bilaterally")

    unset = -2
    background = -1
    samples = [unset] * (width * height)
    duplicate_texels = 0
    conflicting_texels = 0
    for face in faces:
        triangle = [uv[index] for index in face]
        first_x = max(
            0, math.ceil(min(value[0] for value in triangle) * width - 0.5)
        )
        last_x = min(
            width - 1,
            math.floor(max(value[0] for value in triangle) * width - 0.5),
        )
        first_y = max(
            0, math.ceil(min(value[1] for value in triangle) * height - 0.5)
        )
        last_y = min(
            height - 1,
            math.floor(max(value[1] for value in triangle) * height - 0.5),
        )
        first, second, third = triangle
        denominator = (
            (second[1] - third[1]) * (first[0] - third[0])
            + (third[0] - second[0]) * (first[1] - third[1])
        )
        for y_pixel in range(first_y, last_y + 1):
            atlas_v = (y_pixel + 0.5) / height
            for x_pixel in range(first_x, last_x + 1):
                atlas_u = (x_pixel + 0.5) / width
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
                semantic = _semantic_coordinate(point)
                sample = _nearest_semantic_pixel(*semantic)
                value = background if sample is None else sample
                atlas_index = y_pixel * width + x_pixel
                if samples[atlas_index] != unset:
                    duplicate_texels += 1
                    conflicting_texels += samples[atlas_index] != value
                else:
                    samples[atlas_index] = value
    if duplicate_texels or conflicting_texels:
        raise PatchError(
            f"{spec.node_name} stock atlas raster overlaps: "
            f"duplicate={duplicate_texels}, conflicting={conflicting_texels}"
        )
    covered = sum(value != unset for value in samples)
    mapped = sum(value >= 0 for value in samples)
    if not covered or not mapped:
        raise PatchError(f"{spec.node_name} stock atlas maps no semantic texels")
    right_vertices = {index for face in right for index in face}
    left_vertices = {index for face in left for index in face}
    semantic_vertices = {
        index: _semantic_coordinate(positions[index]) for index in vertices
    }
    front = min(vertices, key=lambda index: semantic_vertices[index][0])
    rear = max(vertices, key=lambda index: semantic_vertices[index][0])
    return samples, {
        "node_index": spec.node_index,
        "node_name": spec.node_name,
        "exterior_face_count": len(faces),
        "exterior_vertex_count": len(vertices),
        "faces_per_side": len(right),
        "atlas_covered_texels": covered,
        "semantic_envelope_texels": mapped,
        "minimum_absolute_uv_triangle_determinant": min(map(abs, determinants)),
        "mixed_uv_orientation": False,
        "projected_overlap_count": 0,
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
        "front_anchor": {
            "atlas_uv": list(uv[front]),
            "semantic_uv": list(semantic_vertices[front]),
            "position_cm": list(positions[front]),
        },
        "rear_anchor": {
            "atlas_uv": list(uv[rear]),
            "semantic_uv": list(semantic_vertices[rear]),
            "position_cm": list(positions[rear]),
        },
        "front_to_rear_semantic_u_increases": (
            semantic_vertices[front][0] < semantic_vertices[rear][0]
        ),
        "bilateral_same_semantic_canvas": True,
    }


def _barycentric_yz(
    point: tuple[float, float, float],
    triangle: tuple[int, int, int],
    positions: list[tuple[float, float, float]],
) -> tuple[float, float, float] | None:
    """Return projected Y/Z weights when ``point`` lies in ``triangle``."""

    first, second, third = (positions[index] for index in triangle)
    denominator = (
        (second[1] - third[1]) * (first[2] - third[2])
        + (third[2] - second[2]) * (first[1] - third[1])
    )
    if abs(denominator) <= 1.0e-12:
        return None
    first_weight = (
        (second[1] - third[1]) * (point[2] - third[2])
        + (third[2] - second[2]) * (point[1] - third[1])
    ) / denominator
    second_weight = (
        (third[1] - first[1]) * (point[2] - third[2])
        + (first[2] - third[2]) * (point[1] - third[1])
    ) / denominator
    third_weight = 1.0 - first_weight - second_weight
    if min(first_weight, second_weight, third_weight) < -1.0e-7:
        return None
    return first_weight, second_weight, third_weight


@lru_cache(maxsize=2)
def _retail_atlas_sample_map(
    system: bytes, spec: LodSpec,
) -> tuple[list[int], dict[str, Any]]:
    """Map the stock draw-2 decal onto the shell atlas at the same Y/Z place.

    This compatibility bake is used for every non-selected team when the
    shared helmet material route is enabled.  It keeps each retail crest at its
    existing physical side-of-helmet placement instead of interpreting its
    bounded decal texture as a whole-shell atlas.
    """

    shell_faces, positions = _outer_shell_faces(system, spec)
    words = _indices(system, spec)
    carrier_faces = _triangles(words[
        spec.carrier_index_start : spec.carrier_index_start + spec.carrier_index_count
    ])
    if len(carrier_faces) != spec.carrier_triangle_count:
        raise PatchError(f"{spec.node_name} retail crest topology drift")
    shell_vertices = {index for face in shell_faces for index in face}
    carrier_vertices = {index for face in carrier_faces for index in face}
    shell_uv = {index: _uv(system, spec, index) for index in shell_vertices}
    carrier_uv = {index: _uv(system, spec, index) for index in carrier_vertices}
    by_side = {
        -1: [
            face for face in carrier_faces
            if all(positions[index][0] <= 1.0e-5 for index in face)
        ],
        1: [
            face for face in carrier_faces
            if all(positions[index][0] >= -1.0e-5 for index in face)
        ],
    }
    if not by_side[-1] or len(by_side[-1]) != len(by_side[1]):
        raise PatchError(f"{spec.node_name} retail crest is not bilateral")

    unset = -2
    background = -1
    samples = [unset] * (CANVAS_WIDTH * CANVAS_HEIGHT)
    mapped_per_side = {-1: 0, 1: 0}
    for face in shell_faces:
        triangle = [shell_uv[index] for index in face]
        first_x = max(
            0, math.ceil(min(value[0] for value in triangle) * CANVAS_WIDTH - 0.5)
        )
        last_x = min(
            CANVAS_WIDTH - 1,
            math.floor(max(value[0] for value in triangle) * CANVAS_WIDTH - 0.5),
        )
        first_y = max(
            0, math.ceil(min(value[1] for value in triangle) * CANVAS_HEIGHT - 0.5)
        )
        last_y = min(
            CANVAS_HEIGHT - 1,
            math.floor(max(value[1] for value in triangle) * CANVAS_HEIGHT - 0.5),
        )
        first, second, third = triangle
        denominator = (
            (second[1] - third[1]) * (first[0] - third[0])
            + (third[0] - second[0]) * (first[1] - third[1])
        )
        side = 1 if sum(positions[index][0] for index in face) >= 0.0 else -1
        for y_pixel in range(first_y, last_y + 1):
            atlas_v = (y_pixel + 0.5) / CANVAS_HEIGHT
            for x_pixel in range(first_x, last_x + 1):
                atlas_u = (x_pixel + 0.5) / CANVAS_WIDTH
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
                best: tuple[float, float] | None = None
                best_x_error = math.inf
                for carrier_face in by_side[side]:
                    weights = _barycentric_yz(point, carrier_face, positions)
                    if weights is None:
                        continue
                    projected_x = sum(
                        weight * positions[index][0]
                        for weight, index in zip(weights, carrier_face)
                    )
                    x_error = abs(abs(projected_x) - abs(point[0]))
                    if x_error < best_x_error:
                        best_x_error = x_error
                        best = tuple(
                            sum(
                                weight * carrier_uv[index][axis]
                                for weight, index in zip(weights, carrier_face)
                            )
                            for axis in range(2)
                        )
                value = background
                if best is not None:
                    value = _nearest_semantic_pixel(*best)
                    if value is None:
                        value = background
                    else:
                        mapped_per_side[side] += 1
                atlas_index = y_pixel * CANVAS_WIDTH + x_pixel
                if samples[atlas_index] == unset:
                    samples[atlas_index] = value
                elif samples[atlas_index] != value:
                    raise PatchError(
                        f"{spec.node_name} retail compatibility raster overlaps"
                    )
    if not all(mapped_per_side.values()):
        raise PatchError(f"{spec.node_name} retail crest maps no texels on one side")
    return samples, {
        "node_index": spec.node_index,
        "node_name": spec.node_name,
        "retail_carrier_triangle_count": len(carrier_faces),
        "mapped_texels_left": mapped_per_side[-1],
        "mapped_texels_right": mapped_per_side[1],
        "same_physical_yz_placement": True,
        "bilateral_source_uv_preserved": True,
    }


def bake_retail_crest_atlas(
    system: bytes,
    retail_rgba: bytes | bytearray | memoryview,
) -> tuple[bytes, dict[str, Any]]:
    """Migrate one bounded retail crest into the routed shell UV atlas."""

    if len(system) != SYSTEM_LENGTH or sha256_bytes(system) != SOURCE_SYSTEM_SHA256:
        raise PatchError("helmet_00 SCNE is not the pinned retail source")
    retail = _require_rgba(retail_rgba, "retail_rgba")
    background = retail[:4]
    if background[:3] != b"\0\0\0":
        raise PatchError("retail crest top-left must be a black mask background")
    maps: list[list[int]] = []
    rows: list[dict[str, Any]] = []
    for spec in LODS:
        sample_map, row = _retail_atlas_sample_map(system, spec)
        maps.append(sample_map)
        rows.append(row)
    atlas = bytearray(background * (CANVAS_WIDTH * CANVAS_HEIGHT))
    high, low = maps
    low_only = 0
    for atlas_index, (high_sample, low_sample) in enumerate(zip(high, low)):
        sample = high_sample
        if high_sample == -2:
            sample = low_sample
            low_only += low_sample != -2
        if sample >= 0:
            atlas[atlas_index * 4 : atlas_index * 4 + 4] = retail[
                sample * 4 : sample * 4 + 4
            ]
    output = bytes(atlas)
    if not {
        output[offset : offset + 4] for offset in range(0, len(output), 4)
    } <= {
        retail[offset : offset + 4] for offset in range(0, len(retail), 4)
    }:
        raise PatchError("retail crest migration introduced a palette value")
    return output, {
        "schema": "apf2k8_retail_crest_shell_atlas_migration/v1",
        "source_rgba_sha256": sha256_bytes(retail),
        "atlas_rgba_sha256": sha256_bytes(output),
        "nearest_neighbour": True,
        "palette_values_preserved": True,
        "low_lod_only_edge_texels": low_only,
        "lods": rows,
    }


def bake_shell_atlas(
    system: bytes,
    design_rgba: bytes | bytearray | memoryview,
) -> tuple[bytes, dict[str, Any]]:
    """Bake one semantic side canvas into both stock shell-atlas islands."""

    if len(system) != SYSTEM_LENGTH or sha256_bytes(system) != SOURCE_SYSTEM_SHA256:
        raise PatchError("helmet_00 SCNE is not the pinned retail source")
    design = _require_rgba(design_rgba, "design_rgba")
    background, design_active = _validate_design_mask(design)
    maps: list[list[int]] = []
    rows: list[dict[str, Any]] = []
    for spec in LODS:
        sample_map, row = _atlas_sample_map(system, spec)
        maps.append(sample_map)
        rows.append(row)

    atlas = bytearray(background * (CANVAS_WIDTH * CANVAS_HEIGHT))
    high, low = maps
    high_priority = 0
    low_only = 0
    common = 0
    low_common_sample_difference = 0
    for atlas_index, (high_sample, low_sample) in enumerate(zip(high, low)):
        sample = high_sample
        if high_sample == -2:
            sample = low_sample
            low_only += low_sample != -2
        elif low_sample != -2:
            common += 1
            low_common_sample_difference += high_sample != low_sample
        if high_sample != -2:
            high_priority += 1
        if sample >= 0:
            source = sample * 4
            target = atlas_index * 4
            atlas[target : target + 4] = design[source : source + 4]
    atlas_bytes = bytes(atlas)
    design_palette = {
        design[offset : offset + 4] for offset in range(0, len(design), 4)
    }
    atlas_palette = {
        atlas_bytes[offset : offset + 4]
        for offset in range(0, len(atlas_bytes), 4)
    }
    if not atlas_palette <= design_palette:
        raise PatchError("nearest shell-atlas bake introduced a palette value")
    atlas_active = sum(
        bool(atlas_bytes[offset] or atlas_bytes[offset + 1] or atlas_bytes[offset + 2])
        for offset in range(0, len(atlas_bytes), 4)
    )
    if not atlas_active:
        raise PatchError(
            "the semantic design does not intersect the stock helmet-shell atlas; "
            "move visible art into the labeled front/crown/rear envelope"
        )
    return atlas_bytes, {
        "schema": "apf2k8_helmet_shell_atlas_bake/v1",
        "design_rgba_sha256": sha256_bytes(design),
        "atlas_rgba_sha256": sha256_bytes(atlas_bytes),
        "design_active_texels": design_active,
        "atlas_active_texels": atlas_active,
        "background_rgba_hex": background.hex(),
        "opaque_shell_body_contract": True,
        "required_shell_body_alpha": OPAQUE_SHELL_ALPHA,
        "retail_bounded_crest_transport_alpha_hex": "88",
        "nearest_neighbour": True,
        "palette_values_preserved": True,
        "high_lod_authoritative_common_texels": high_priority,
        "low_lod_only_edge_texels": low_only,
        "common_lod_atlas_texels": common,
        "low_lod_common_sample_difference_count": low_common_sample_difference,
        "lods": rows,
    }


LITERAL_SCHEMA = "apf2k8_helmet_shell_literal_bake/v1"
# Default shell body: the 2017-Eagles-preset midnight green (ARGB).
DEFAULT_SHELL_COLOR_ARGB = 0xFF004C54
SHELL_COLOR_WIDTH = 256
SHELL_COLOR_HEIGHT = 1024


def shell_color_rgba(argb: int) -> bytes:
    """Return the opaque RGBA quad for one ARGB shell colour dword."""

    if type(argb) is not int or not 0 <= argb <= 0xFFFFFFFF:
        raise PatchError("shell colour must be a 32-bit ARGB dword")
    return bytes((
        (argb >> 16) & 0xFF,
        (argb >> 8) & 0xFF,
        argb & 0xFF,
        OPAQUE_SHELL_ALPHA,
    ))


def literal_rgba_from_region_mask(
    mask_rgba: bytes | bytearray | memoryview,
    *,
    shell_color: int = DEFAULT_SHELL_COLOR_ARGB,
    light_color: tuple[int, int, int] = (255, 255, 255),
    dark_color: tuple[int, int, int] = (192, 192, 192),
) -> bytes:
    """Convert a Xenos 4-bit APF weight mask into a literal painted canvas.

    The v25 opaque design's R/G lattice is the palette-weight mask (red renders
    the light wing ink, green the dark one).  The native material lane carries
    literal RGB instead, so the weights are composited over the shell colour
    with the same AA fringe the mask encodes.
    """

    mask = _require_rgba(mask_rgba, "mask_rgba")
    _validate_design_mask(mask)
    body = shell_color_rgba(shell_color)
    shell = (body[0], body[1], body[2])
    out = bytearray()
    for offset in range(0, len(mask), 4):
        red, green = mask[offset], mask[offset + 1]
        if not red and not green:
            out += body
            continue
        weight_light = red / 255.0
        weight_dark = green / 255.0
        weight_shell = max(0.0, 1.0 - weight_light - weight_dark)
        out += bytes((
            round(
                shell[0] * weight_shell
                + light_color[0] * weight_light
                + dark_color[0] * weight_dark
            ),
            round(
                shell[1] * weight_shell
                + light_color[1] * weight_light
                + dark_color[1] * weight_dark
            ),
            round(
                shell[2] * weight_shell
                + light_color[2] * weight_light
                + dark_color[2] * weight_dark
            ),
            OPAQUE_SHELL_ALPHA,
        ))
    return bytes(out)


def _require_opaque_literal(literal: bytes, label: str) -> int:
    transparent = sum(
        1 for offset in range(3, len(literal), 4)
        if literal[offset] != OPAQUE_SHELL_ALPHA
    )
    if transparent:
        raise PatchError(
            f"{label} must be fully opaque; {transparent} texels carry "
            "non-255 alpha and the retail shell material has no alpha lane"
        )
    return sum(
        1 for offset in range(0, len(literal), 4)
        if literal[offset : offset + 3] != literal[:3]
    )


def bake_shell_atlas_literal(
    system: bytes,
    literal_rgba: bytes | bytearray | memoryview,
    *,
    shell_color: int = DEFAULT_SHELL_COLOR_ARGB,
    width: int = SHELL_COLOR_WIDTH,
    height: int = SHELL_COLOR_HEIGHT,
) -> tuple[bytes, dict[str, Any]]:
    """Bake one literal painted side canvas into the shell colour texture space.

    Unlike :func:`bake_shell_atlas` (palette weights for the crest material),
    this emits literal RGBA: the shell body is ``shell_color`` and crest art
    keeps its authored colours, so the retail opaque+glossy material 1 can
    carry the artwork without any palette indirection.
    """

    if len(system) != SYSTEM_LENGTH or sha256_bytes(system) != SOURCE_SYSTEM_SHA256:
        raise PatchError("helmet_00 SCNE is not the pinned retail source")
    literal = _require_rgba(literal_rgba, "literal_rgba")
    _require_opaque_literal(literal, "literal_rgba")
    body = shell_color_rgba(shell_color)
    art_texels = sum(
        1 for offset in range(0, len(literal), 4)
        if literal[offset : offset + 3] != body[:3]
    )
    if not art_texels:
        raise PatchError("literal_rgba is a flat shell colour; nothing to bake")
    maps: list[list[int]] = []
    rows: list[dict[str, Any]] = []
    for spec in LODS:
        sample_map, row = _atlas_sample_map(system, spec, width, height)
        maps.append(sample_map)
        rows.append(row)

    atlas = bytearray(body * (width * height))
    high, low = maps
    high_priority = 0
    low_only = 0
    common = 0
    for atlas_index, (high_sample, low_sample) in enumerate(zip(high, low)):
        sample = high_sample
        if high_sample == -2:
            sample = low_sample
            low_only += low_sample != -2
        elif low_sample != -2:
            common += 1
        if high_sample != -2:
            high_priority += 1
        if sample >= 0:
            atlas[atlas_index * 4 : atlas_index * 4 + 4] = literal[
                sample * 4 : sample * 4 + 4
            ]
    atlas_bytes = bytes(atlas)
    atlas_art = sum(
        1 for offset in range(0, len(atlas_bytes), 4)
        if atlas_bytes[offset : offset + 4] != body
    )
    if not atlas_art:
        raise PatchError(
            "the literal design does not intersect the stock helmet-shell atlas; "
            "move visible art into the labeled front/crown/rear envelope"
        )
    return atlas_bytes, {
        "schema": LITERAL_SCHEMA,
        "literal_rgba_sha256": sha256_bytes(literal),
        "atlas_rgba_sha256": sha256_bytes(atlas_bytes),
        "literal_art_texels": art_texels,
        "atlas_art_texels": atlas_art,
        "shell_body_rgba_hex": body.hex(),
        "shell_body_argb_hex": f"{shell_color:08X}",
        "opaque_alpha": True,
        "nearest_neighbour": True,
        "target_width": width,
        "target_height": height,
        "high_lod_authoritative_common_texels": high_priority,
        "low_lod_only_edge_texels": low_only,
        "common_lod_atlas_texels": common,
        "lods": rows,
    }


def wrap_system(
    payload: bytes,
    *,
    design_rgba: bytes | bytearray | memoryview,
) -> tuple[bytes, bytes, dict[str, Any]]:
    """Route the exact stock shell atlas and neutralize the bounded overlay."""

    if len(payload) != SYSTEM_LENGTH or sha256_bytes(payload) != SOURCE_SYSTEM_SHA256:
        raise PatchError("helmet_00 SCNE is not the pinned retail source")
    design = _require_rgba(design_rgba, "design_rgba")
    atlas, atlas_report = bake_shell_atlas(payload, design)
    nodes = _scene_nodes(payload)
    output = bytearray(payload)
    allowed: set[int] = set()
    lod_rows: list[dict[str, Any]] = []
    for spec in LODS:
        if len(nodes) <= spec.node_index:
            raise PatchError(f"{spec.node_name} node is missing")
        _validate_layout(payload, spec, nodes[spec.node_index])
        records = [
            struct.unpack_from(">12I", payload, spec.draw_record_offset + number * DRAW_RECORD_SIZE)
            for number in range(DRAW_RECORD_COUNT)
        ]
        if (
            records[SHELL_DRAW_INDEX][8] != SOURCE_SHELL_MATERIAL
            or records[CARRIER_DRAW_INDEX][8] != CREST_MATERIAL
        ):
            raise PatchError(f"{spec.node_name} material route drift")
        if not all(
            records[number][1] + records[number][2] == records[number + 1][1]
            and records[number][5] + records[number][6] == records[number + 1][5]
            for number in range(DRAW_RECORD_COUNT - 1)
        ):
            raise PatchError(f"{spec.node_name} draw windows are not contiguous")
        material_offset = MATERIAL_FIELD_OFFSETS[spec.node_name]
        if material_offset != spec.draw_record_offset + DRAW_RECORD_SIZE + 0x20:
            raise PatchError(f"{spec.node_name} material field offset drift")
        struct.pack_into(">I", output, material_offset, CREST_MATERIAL)
        allowed.update(range(material_offset, material_offset + 4))

        index_start = spec.index_offset + spec.carrier_index_start * 2
        index_end = index_start + spec.carrier_index_count * 2
        output[index_start:index_end] = struct.pack(
            f">{spec.carrier_index_count}H",
            *([spec.carrier_vertex_start] * spec.carrier_index_count),
        )
        allowed.update(range(index_start, index_end))
        if _triangles(_indices(bytes(output), spec)[
            spec.carrier_index_start : spec.carrier_index_start + spec.carrier_index_count
        ]):
            raise PatchError(f"{spec.node_name} old overlay did not become degenerate")
        lod_rows.append({
            "node_index": spec.node_index,
            "node_name": spec.node_name,
            "shell_draw_material_before": SOURCE_SHELL_MATERIAL,
            "shell_draw_material_after": CREST_MATERIAL,
            "material_field_offset": f"0x{material_offset:08X}",
            "neutralized_draw": CARRIER_DRAW_INDEX,
            "neutralized_index_word_count": spec.carrier_index_count,
            "neutralized_repeated_vertex": spec.carrier_vertex_start,
            "neutralized_triangle_count": 0,
        })
    changed = {
        index for index, values in enumerate(zip(payload, output))
        if values[0] != values[1]
    }
    if not changed or not changed <= allowed:
        raise PatchError("SCNE changed outside shell-route fields/draw-2 index windows")
    for spec in LODS:
        stream_end = spec.stream_start + spec.vertex_count * STRIDE
        if payload[spec.stream_start:stream_end] != output[spec.stream_start:stream_end]:
            raise PatchError(f"{spec.node_name} vertex/UV atlas stream changed")
    return bytes(output), atlas, {
        "authorized_byte_count": len(allowed),
        "changed_byte_count": len(changed),
        "atlas_bake": atlas_report,
        "lods": lod_rows,
        "mask_shader_equation": (
            "shell*(255-red-green)/255 + palette[0]*red/255 + palette[2]*green/255"
        ),
        "black_mask_texels_reproduce_shell_base": True,
    }


def build_patch(
    source_outer: bytes,
    *,
    design_rgba: bytes | bytearray | memoryview,
) -> PatchResult:
    """Return rebuilt outer-1310, gameplay atlas RGBA, and hash manifest."""

    source = _parse_outer(bytes(source_outer), source=True)
    design = _require_rgba(design_rgba, "design_rgba")
    output_system, atlas, metrics = wrap_system(source.system, design_rgba=design)
    output_system_hash = sha256_bytes(output_system)
    eagles_regression = sha256_bytes(design) == EAGLES_REGRESSION_DESIGN_RGBA_SHA256
    if (
        eagles_regression
        and EXPECTED_OUTPUT_SYSTEM_SHA256
        and output_system_hash != EXPECTED_OUTPUT_SYSTEM_SHA256
    ):
        raise PatchError(
            "Eagles full-shell regression SCNE hash differs: "
            f"{output_system_hash}; expected {EXPECTED_OUTPUT_SYSTEM_SHA256}"
        )
    new_block0 = bytearray(source.blocks[0])
    new_block0[
        SYSTEM_PART_OFFSET : SYSTEM_PART_OFFSET + SYSTEM_LENGTH
    ] = output_system
    rebuilt, compression, file_length = _rebuild_entry(source, bytes(new_block0))
    rebuilt_hash = sha256_bytes(rebuilt)
    if (
        eagles_regression and EXPECTED_OUTPUT_OUTER_SHA256
        and rebuilt_hash != EXPECTED_OUTPUT_OUTER_SHA256
    ):
        raise PatchError(
            "Eagles full-shell regression outer hash differs: "
            f"{rebuilt_hash}; expected {EXPECTED_OUTPUT_OUTER_SHA256}"
        )
    reopened = _parse_outer(
        rebuilt,
        source=False,
        expected_output_sha256=rebuilt_hash,
        expected_system_sha256=output_system_hash,
    )
    if reopened.system != output_system:
        raise PatchError("reopened crest-wrap SCNE differs")
    if reopened.blocks[1:] != source.blocks[1:]:
        raise PatchError("decoded sibling blocks changed")
    if reopened.stored[1:] != source.stored[1:]:
        raise PatchError("stored sibling blocks changed")
    if (
        reopened.blocks[0][:SYSTEM_PART_OFFSET]
        != source.blocks[0][:SYSTEM_PART_OFFSET]
        or reopened.blocks[0][SYSTEM_PART_OFFSET + SYSTEM_LENGTH :]
        != source.blocks[0][SYSTEM_PART_OFFSET + SYSTEM_LENGTH :]
    ):
        raise PatchError("decoded block 0 changed outside helmet_00 SCNE")
    metrics["eagles_regression"] = {
        "matched_inputs": eagles_regression,
        "expected_output_outer_sha256": (
            EXPECTED_OUTPUT_OUTER_SHA256 if eagles_regression else None
        ),
        "expected_output_scne_sha256": (
            EXPECTED_OUTPUT_SYSTEM_SHA256 if eagles_regression else None
        ),
    }
    footer_size = 8 + source.record.footer.payload_size  # type: ignore[union-attr]
    manifest = {
        "claim_flags": {
            "editor_gui_integrated": True,
            "emulator_runtime_visibility_proved": False,
            "original_xbox_360_hardware_proved": False,
            "visual_eagles_match_proved": False,
        },
        "compression": dict(sorted(compression.items())),
        "metrics": metrics,
        "operation": OPERATION,
        "preservation": {
            "all_vertex_streams_including_stock_uv_atlas_exact": True,
            "decoded_block0_outside_scne_exact": True,
            "draws_0_and_3_through_12_exact": True,
            "draw_1_exact_except_material_word_1_to_2": True,
            "draw_2_record_and_vertices_exact": True,
            "draw_2_indices_replaced_only_by_in_range_degenerates": True,
            "accessory_draws_and_material_routes_exact": True,
            "sibling_blocks_decoded_exact": True,
            "sibling_blocks_stored_exact": True,
        },
        "result": {
            "file_length_after": file_length,
            "outer_allocation_tail_bytes": OUTER_SIZE - file_length - footer_size,
            "outer_entry_sha256": rebuilt_hash,
            "outer_entry_size_bytes": len(rebuilt),
            "output_scne_sha256": output_system_hash,
            "shell_atlas_rgba_sha256": sha256_bytes(atlas),
        },
        "schema": SCHEMA,
        "source": {
            "outer_entry_sha256": sha256_bytes(source.raw),
            "outer_entry_size_bytes": len(source.raw),
            "source_scne_sha256": sha256_bytes(source.system),
        },
        "target": {
            "inner_file_index": INNER_INDEX,
            "inner_name": INNER_NAME,
            "lods": [
                {
                    "draw_record_index": 2,
                    "shell_draw_record_index": 1,
                    "node_index": spec.node_index,
                    "node_name": spec.node_name,
                }
                for spec in LODS
            ],
            "mapping": "semantic single-side canvas baked bilaterally into retail shell atlas",
            "outer_entry_index": OUTER_INDEX,
            "profile": "whole_shell_stock_atlas_v1",
        },
    }
    return PatchResult(rebuilt, atlas, manifest)


def bind_volume_receipt(
    manifest: Mapping[str, Any],
    *,
    source_volume_sha256: str,
    output_volume_sha256: str,
    prefix_sha256: str,
    suffix_sha256: str,
    volume_size_bytes: int = VOLUME_SIZE,
) -> dict[str, Any]:
    """Return a copy of a manifest bound to any composed source/output pair."""

    def checked(value: str, label: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise PatchError(f"{label} is not a lowercase SHA-256")
        return value

    if volume_size_bytes != VOLUME_SIZE:
        raise PatchError("composed APF volume size differs")
    document = json.loads(json.dumps(manifest))
    if document.get("schema") != SCHEMA or document.get("operation") != OPERATION:
        raise PatchError("cannot bind an unrelated crest-wrap manifest")
    document["source"]["source_volume_sha256"] = checked(
        source_volume_sha256, "source volume hash",
    )
    document["source"]["source_volume_size_bytes"] = volume_size_bytes
    document["result"]["output_volume_sha256"] = checked(
        output_volume_sha256, "output volume hash",
    )
    document["result"]["output_volume_size_bytes"] = volume_size_bytes
    document["preservation"]["whole_volume_outside_outer_1310_exact"] = True
    document["preservation"]["outside_outer_1310_prefix_sha256"] = checked(
        prefix_sha256, "volume prefix hash",
    )
    document["preservation"]["outside_outer_1310_suffix_sha256"] = checked(
        suffix_sha256, "volume suffix hash",
    )
    return document


def read_source_outer(path: Path) -> bytes:
    """Read outer 1310 from either an allocation file or a fixed-size 0A."""

    source = Path(path)
    metadata = source.stat()
    if not source.is_file() or source.is_symlink():
        raise PatchError("source must be a regular non-symlink file")
    if metadata.st_size == OUTER_SIZE:
        payload = source.read_bytes()
    elif metadata.st_size == VOLUME_SIZE:
        with source.open("rb") as stream:
            stream.seek(OUTER_OFFSET)
            payload = stream.read(OUTER_SIZE)
    else:
        raise PatchError("source must be outer 1310 or a fixed-size APF 0A")
    if len(payload) != OUTER_SIZE:
        raise PatchError("short read while reading outer 1310")
    return payload


def _write_new(path: Path, payload: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise PatchError("short write while publishing crest-wrap artifact")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_rgba_png(path: Path, label: str) -> bytes:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow ships with the app
        raise PatchError("Pillow is required to decode helmet crest PNGs") from exc
    path = Path(path)
    metadata = path.lstat()
    if not path.is_file() or path.is_symlink() or metadata.st_size > 64 * 1024 * 1024:
        raise PatchError(f"{label} must be a regular non-symlink PNG at most 64 MiB")
    try:
        with Image.open(path) as image:
            image.load()
            if image.size != (CANVAS_WIDTH, CANVAS_HEIGHT):
                raise PatchError(f"{label} must be exactly 512x512")
            return image.convert("RGBA").tobytes()
    except PatchError:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow uses format-specific errors
        raise PatchError(f"could not decode {label}: {exc}") from exc


def publish_outer(
    source: Path,
    design_png: Path,
    output_outer: Path,
    receipt_path: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    """Publish only outer-entry bytes and its receipt, never a game volume."""

    output_outer = Path(output_outer)
    receipt_path = Path(receipt_path)
    if not output_outer.parent.is_dir() or not receipt_path.parent.is_dir():
        raise PatchError("output and receipt parents must already exist")
    for path, label in ((output_outer, "output outer"), (receipt_path, "receipt")):
        if path.exists() or path.is_symlink():
            raise PatchError(f"refusing to overwrite {label}: {path}")
    result = build_patch(
        read_source_outer(Path(source)),
        design_rgba=_read_rgba_png(design_png, "design PNG"),
    )
    created: list[Path] = []
    try:
        _write_new(output_outer, result.rebuilt_entry)
        created.append(output_outer)
        _write_new(receipt_path, canonical_json_bytes(result.manifest))
        created.append(receipt_path)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return output_outer, receipt_path, result.manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, type=Path,
        help="pinned outer-1310 allocation or APF 0A containing it",
    )
    parser.add_argument("--design-png", required=True, type=Path)
    parser.add_argument("--output-outer", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        output, receipt, manifest = publish_outer(
            args.source,
            args.design_png,
            args.output_outer,
            args.receipt,
        )
    except (OSError, PatchError) as exc:
        parser.exit(2, f"helmet crest wrap failed: {exc}\n")
    print(json.dumps({
        "outer_entry_sha256": manifest["result"]["outer_entry_sha256"],
        "output_outer": str(output),
        "receipt": str(receipt),
        "scne_sha256": manifest["result"]["output_scne_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
