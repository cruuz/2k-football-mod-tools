"""Source-bound, same-topology APF helmet/player glTF POSITION importer.

This intentionally does not pretend to be a general model importer.  It reads
only glTFs emitted by :mod:`model_export`, requires their expanded triangle
lists to match the currently loaded SCNE byte-for-byte, and writes only the
three signed-normalized POSITION components in each source vertex record.  The
fourth position component, normals, tangent/packed-UV data, blend indices,
blend weights, matrices, materials, attachments, animation, and collision stay
bit-exact.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
from typing import Any, Callable, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from mod_editor.apf_studio.backend import ensure_tools_importable
    from mod_editor.apf_studio.model_export import ModelExportTarget, target
    from mod_editor.core import platform_compat
    from mod_editor.core.platform_compat import try_reflink
else:
    from mod_editor.core import platform_compat
    from mod_editor.core.platform_compat import try_reflink

    from .backend import ensure_tools_importable
    from .model_export import ModelExportTarget, target


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_scene  # type: ignore  # noqa: E402


Progress = Callable[[str, int, int], None]
IMPORT_SCHEMA = "apf2k8_same_topology_model_import/v1"
EXPORT_SCHEMA = "apf2k8_private_static_model_export/v2"
MAX_GLTF_BYTES = 16 * 1024 * 1024
MAX_BUFFER_BYTES = 128 * 1024 * 1024
POSITION_FORMAT = "snorm16x4"
POSITION_FORMAT_CODE = "0x001a215a"
MODEL_IMPORT_BOUNDARY = (
    "Same-topology POSITION-only import for the exported stock helmet and player. "
    "Vertex count and expanded triangles must match the loaded source exactly. "
    "The source POSITION W component, normals, packed tangent/UV data, blend "
    "indices/weights, skin attachments, materials, animation, collision, and every "
    "SCNE byte outside POSITION XYZ are preserved and cannot be authored."
)


class ModelImportError(ValueError):
    """An edited glTF leaves the proved APF model write boundary."""


@dataclass(frozen=True)
class ModelPatch:
    target: ModelExportTarget
    outer_offset: int
    outer_size: int
    rebuilt_entry: bytes
    source_entry_sha256: str
    output_entry_sha256: str
    changed_vertex_count: int
    changed_position_component_bytes: int
    maximum_quantization_error: float
    no_op: bool
    manifest: dict[str, object]


@dataclass(frozen=True)
class ModelImportReceipt:
    target: ModelExportTarget
    output_0a: Path
    receipt: Path
    changed_vertex_count: int
    maximum_quantization_error: float
    no_op: bool


class _BytesReader:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self, _entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.payload):
            raise apf_inner.FormatError("memory IFF read exceeds rebuilt entry")
        return self.payload[offset : offset + size]


@dataclass(frozen=True)
class _Source:
    selected: ModelExportTarget
    entry: apf_outer.Entry
    record: apf_inner.IFFRecord
    original_entry: bytes
    blocks: tuple[bytes, ...]
    stored: tuple[bytes, ...]
    system_part: apf_inner.FilePart
    system: bytes
    scene: dict[str, object]


@dataclass(frozen=True)
class _Mesh:
    node_index: int
    source_mesh_index: int
    vertex_count: int
    stream_start: int
    stream_stride: int
    lane_offset: int
    center: tuple[float, float, float]
    scale: tuple[float, float, float]
    source_positions: tuple[tuple[float, float, float], ...]
    source_triangles: tuple[int, ...]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_json(path: Path, maximum: int, label: str) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ModelImportError(f"could not inspect {label}: {exc}") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or not 0 < metadata.st_size <= maximum
    ):
        raise ModelImportError(f"{label} must be a bounded regular non-symlink file")

    def reject_constant(value: str) -> None:
        raise ModelImportError(f"{label} contains non-JSON number {value!r}")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ModelImportError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_bytes(), parse_constant=reject_constant, object_pairs_hook=unique
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ModelImportError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ModelImportError(f"{label} must contain one JSON object")
    return value


def _regular_bytes(path: Path, maximum: int, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ModelImportError(f"could not inspect {label}: {exc}") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or not 0 < metadata.st_size <= maximum
    ):
        raise ModelImportError(f"{label} must be a bounded regular non-symlink file")
    return path.read_bytes()


def _source(index_0a: Path, selected: ModelExportTarget) -> _Source:
    try:
        archive = apf_outer.parse_archive(Path(index_0a))
        entry = archive.entries[selected.outer_index]
        if (
            len(entry.segments) != 1
            or entry.segments[0].pack_name != "0A"
            or entry.segments[0].size != entry.size
        ):
            raise ModelImportError("model outer entry no longer has one 0A allocation")
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            original_entry = reader.read(entry, 0, entry.size)
            blocks = tuple(
                apf_inner.decode_block(reader, record, index, 128 * 1024 * 1024)
                for index in range(record.block_count)
            )
            stored = tuple(
                reader.read(entry, block.start_offset, block.stored_length)
                for block in record.blocks
            )
        item = record.files[selected.inner_index]
        if (
            item.name != selected.root_name
            or item.type_name != "SCNE"
            or len(item.parts) != 1
            or item.parts[0].block_index != 0
        ):
            raise ModelImportError("selected model SCNE ownership changed")
        part = item.parts[0]
        system = blocks[0][part.offset : part.offset + part.length]
        scene = apf_scene.parse_scene_system_part(
            system,
            outer_index=selected.outer_index,
            inner_index=selected.inner_index,
            capture_geometry=True,
        )
        if scene.get("root_name") != selected.root_name:
            raise ModelImportError("selected model SCNE root changed")
        return _Source(
            selected,
            entry,
            record,
            original_entry,
            blocks,
            stored,
            part,
            system,
            scene,
        )
    except ModelImportError:
        raise
    except (IndexError, OSError, apf_inner.FormatError, apf_outer.FormatError, apf_scene.SceneError) as exc:
        raise ModelImportError(f"could not read source model: {exc}") from exc


def _source_meshes(source: _Source) -> tuple[_Mesh, ...]:
    result: list[_Mesh] = []
    for node in source.scene["nodes"]:  # type: ignore[index]
        for mesh_index, mesh in enumerate(node["meshes"]):
            geometry = mesh.get("_geometry")
            position = mesh.get("position")
            if not isinstance(geometry, dict) or not isinstance(position, dict):
                continue
            positions = geometry.get("positions")
            indices = geometry.get("indices")
            if not isinstance(positions, list) or not isinstance(indices, list):
                continue
            triangles = apf_scene._expand_triangle_strip(indices)
            if not triangles:
                continue
            declarations = node["vertex_declarations"]
            semantics = [item.get("indexed_semantic") for item in declarations]
            declaration = next(
                (item for item in declarations if item.get("indexed_semantic") == "POSITION0"),
                None,
            )
            stream_index = position.get("stream_index")
            if (
                mesh.get("primitive_type") != 5
                or node.get("index_component_bits") not in (16, 32)
                or position.get("format") != POSITION_FORMAT
                or declaration is None
                or declaration.get("format_code") != POSITION_FORMAT_CODE
                or type(stream_index) is not int
                or not any(str(value).startswith("BLENDINDICES") for value in semantics)
                or not any(str(value).startswith("BLENDWEIGHT") for value in semantics)
            ):
                raise ModelImportError(
                    f"model mesh {node['index']} left the proved POSITION-preserve-skin layout"
                )
            stream = mesh["streams"][stream_index]
            center = tuple(float(value) for value in position["center"])
            scale = tuple(float(value) for value in position["scale"])
            if len(center) != 3 or len(scale) != 3 or any(value <= 0 for value in scale):
                raise ModelImportError("model POSITION quantization transform changed")
            result.append(
                _Mesh(
                    int(node["index"]),
                    mesh_index,
                    int(mesh["vertex_count"]),
                    int(stream["start"]),
                    int(stream["stride"]),
                    int(position["byte_offset"]),
                    center,  # type: ignore[arg-type]
                    scale,  # type: ignore[arg-type]
                    tuple(tuple(float(v) for v in row) for row in positions),  # type: ignore[arg-type]
                    tuple(int(value) for value in triangles),
                )
            )
    if len(result) != source.selected.expected_mesh_count:
        raise ModelImportError("source model mesh inventory changed")
    return tuple(result)


def _buffer_uri(document: dict[str, Any], gltf_path: Path) -> tuple[bytes, dict[str, Any]]:
    buffers = document.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1 or not isinstance(buffers[0], dict):
        raise ModelImportError("edited glTF must contain one external binary buffer")
    buffer = buffers[0]
    uri = buffer.get("uri")
    if (
        not isinstance(uri, str)
        or not uri
        or Path(uri).name != uri
        or "/" in uri
        or "\\" in uri
        or uri.startswith("data:")
    ):
        raise ModelImportError("edited glTF buffer URI must be one safe sibling filename")
    payload = _regular_bytes(gltf_path.parent / uri, MAX_BUFFER_BYTES, "glTF buffer")
    if buffer.get("byteLength") != len(payload):
        raise ModelImportError("glTF buffer byteLength differs from its file")
    return payload, buffer


def _accessor_values(
    document: dict[str, Any], payload: bytes, accessor_index: object, *, position: bool
) -> tuple[Any, ...]:
    if type(accessor_index) is not int:
        raise ModelImportError("glTF primitive accessor index is invalid")
    accessors = document.get("accessors")
    views = document.get("bufferViews")
    if (
        not isinstance(accessors, list)
        or not 0 <= accessor_index < len(accessors)
        or not isinstance(views, list)
        or not isinstance(accessors[accessor_index], dict)
    ):
        raise ModelImportError("glTF accessor is missing")
    accessor = accessors[accessor_index]
    if "sparse" in accessor or accessor.get("normalized") not in (None, False):
        raise ModelImportError("sparse or normalized glTF accessors are unsupported")
    view_index = accessor.get("bufferView")
    if type(view_index) is not int or not 0 <= view_index < len(views) or not isinstance(views[view_index], dict):
        raise ModelImportError("glTF accessor bufferView is invalid")
    view = views[view_index]
    if view.get("buffer") != 0:
        raise ModelImportError("glTF accessor refers to an unexpected buffer")
    count = accessor.get("count")
    if type(count) is not int or not 0 <= count <= 1_000_000:
        raise ModelImportError("glTF accessor count is invalid")
    if position:
        component, kind, components, fmt = 5126, "VEC3", 3, "<3f"
    else:
        component, kind, components, fmt = 5125, "SCALAR", 1, "<I"
    if accessor.get("componentType") != component or accessor.get("type") != kind:
        raise ModelImportError("glTF accessor type changed")
    element_size = components * 4
    stride = view.get("byteStride", element_size)
    view_start = view.get("byteOffset", 0)
    accessor_offset = accessor.get("byteOffset", 0)
    view_length = view.get("byteLength")
    if (
        type(stride) is not int
        or stride < element_size
        or stride % 4
        or type(view_start) is not int
        or type(accessor_offset) is not int
        or type(view_length) is not int
        or view_start < 0
        or accessor_offset < 0
        or view_length < 0
        or view_start + view_length > len(payload)
    ):
        raise ModelImportError("glTF accessor leaves its bounded buffer")
    start = view_start + accessor_offset
    end = start if not count else start + (count - 1) * stride + element_size
    if start < view_start or end > view_start + view_length:
        raise ModelImportError("glTF accessor leaves its bounded bufferView")
    values: list[Any] = []
    for index in range(count):
        row = struct.unpack_from(fmt, payload, start + index * stride)
        if position:
            if not all(math.isfinite(value) for value in row):
                raise ModelImportError("glTF POSITION contains non-finite values")
            values.append(tuple(float(value) for value in row))
        else:
            values.append(int(row[0]))
    return tuple(values)


def _edited_meshes(
    gltf_path: Path,
    manifest_path: Path,
    source: _Source,
    source_meshes: tuple[_Mesh, ...],
) -> tuple[tuple[tuple[float, float, float], ...], ...]:
    manifest = _strict_json(manifest_path, 2 * 1024 * 1024, "model manifest")
    document = _strict_json(gltf_path, MAX_GLTF_BYTES, "edited glTF")
    fixed_target = {
        "key": source.selected.key,
        "title": source.selected.title,
        "outer_index": source.selected.outer_index,
        "inner_index": source.selected.inner_index,
        "root_name": source.selected.root_name,
    }
    if (
        manifest.get("schema") != EXPORT_SCHEMA
        or manifest.get("target") != fixed_target
        or manifest.get("source_system_sha256") != _sha256(source.system)
        or manifest.get("model_import_available") is not True
    ):
        raise ModelImportError("model manifest does not bind this source SCNE and target")
    asset = document.get("asset")
    extras = asset.get("extras") if isinstance(asset, dict) else None
    contract = extras.get("coordinate_contract") if isinstance(extras, dict) else None
    if (
        not isinstance(asset, dict)
        or asset.get("version") != "2.0"
        or not isinstance(extras, dict)
        or extras.get("outer_table_index") != source.selected.outer_index
        or extras.get("inner_file_index") != source.selected.inner_index
        or extras.get("scne_root_name") != source.selected.root_name
        or extras.get("system_sha256") != _sha256(source.system)
        or not isinstance(contract, dict)
        or contract.get("buffer_space") != "serialized_scne_object_space"
        or contract.get("linear_scale") != apf_scene.UNIT_SCALE
    ):
        raise ModelImportError("edited glTF lost its source/coordinate binding")
    for forbidden in (
        "animations", "skins", "materials", "textures", "images", "samplers",
        "cameras", "extensionsUsed", "extensionsRequired",
    ):
        if document.get(forbidden) not in (None, []):
            raise ModelImportError(f"edited glTF contains unsupported {forbidden}")
    payload, _buffer = _buffer_uri(document, gltf_path)
    meshes = document.get("meshes")
    nodes = document.get("nodes")
    scenes = document.get("scenes")
    scene_index = document.get("scene")
    if (
        not isinstance(meshes, list)
        or len(meshes) != len(source_meshes)
        or not isinstance(nodes, list)
        or not isinstance(scenes, list)
        or len(scenes) != 1
        or scene_index != 0
        or not isinstance(scenes[0], dict)
    ):
        raise ModelImportError("edited glTF scene/mesh inventory changed")
    roots = scenes[0].get("nodes")
    if not isinstance(roots, list) or len(roots) != 1 or type(roots[0]) is not int:
        raise ModelImportError("edited glTF must retain one unit-conversion root")
    root_index = roots[0]
    if not 0 <= root_index < len(nodes) or not isinstance(nodes[root_index], dict):
        raise ModelImportError("edited glTF root node is invalid")
    root = nodes[root_index]
    if (
        root.get("scale") != [apf_scene.UNIT_SCALE] * 3
        or any(key in root for key in ("mesh", "skin", "matrix", "translation", "rotation"))
    ):
        raise ModelImportError("edited glTF changed the coordinate-conversion root")

    source_by_key = {
        (mesh.node_index, mesh.source_mesh_index): mesh for mesh in source_meshes
    }
    edited_by_key: dict[tuple[int, int], tuple[tuple[float, float, float], ...]] = {}
    for mesh in meshes:
        if not isinstance(mesh, dict) or mesh.get("weights") not in (None, []):
            raise ModelImportError("edited glTF mesh contains unsupported morph weights")
        extras = mesh.get("extras")
        primitives = mesh.get("primitives")
        if not isinstance(extras, dict) or not isinstance(primitives, list) or len(primitives) != 1:
            raise ModelImportError("edited glTF mesh lost its source identity")
        key = (extras.get("apf_scene_node_index"), extras.get("apf_source_mesh_index"))
        if key not in source_by_key or key in edited_by_key:
            raise ModelImportError("edited glTF mesh identity is missing or duplicated")
        primitive = primitives[0]
        attributes = primitive.get("attributes") if isinstance(primitive, dict) else None
        if (
            not isinstance(primitive, dict)
            or primitive.get("mode", 4) != 4
            or set(attributes or {}) != {"POSITION"}
            or "material" in primitive
            or "targets" in primitive
        ):
            raise ModelImportError("edited glTF added unsupported attributes/material/topology")
        source_mesh = source_by_key[key]  # type: ignore[index]
        positions = _accessor_values(document, payload, attributes["POSITION"], position=True)
        triangles = _accessor_values(document, payload, primitive.get("indices"), position=False)
        if len(positions) != source_mesh.vertex_count:
            raise ModelImportError("edited glTF vertex count changed")
        if triangles != source_mesh.source_triangles:
            raise ModelImportError("edited glTF topology or index order changed")
        edited_by_key[key] = positions  # type: ignore[assignment]
    if set(edited_by_key) != set(source_by_key):
        raise ModelImportError("edited glTF omitted a source mesh")

    mesh_nodes: dict[int, tuple[int, int]] = {}
    for node in nodes:
        if not isinstance(node, dict) or "mesh" not in node:
            continue
        mesh_index = node.get("mesh")
        if type(mesh_index) is not int or not 0 <= mesh_index < len(meshes):
            raise ModelImportError("edited glTF mesh node is invalid")
        if any(key in node for key in ("skin", "matrix", "translation", "rotation", "scale")):
            raise ModelImportError("edited glTF applies unsupported mesh transforms or skinning")
        mesh_extras = meshes[mesh_index]["extras"]
        mesh_nodes[mesh_index] = (
            mesh_extras["apf_scene_node_index"], mesh_extras["apf_source_mesh_index"]
        )
    if len(mesh_nodes) != len(meshes):
        raise ModelImportError("edited glTF must retain one untransformed node per mesh")
    children = root.get("children")
    if not isinstance(children, list) or set(children) != {
        index for index, node in enumerate(nodes) if isinstance(node, dict) and "mesh" in node
    }:
        raise ModelImportError("edited glTF root no longer owns every mesh node")
    return tuple(edited_by_key[(mesh.node_index, mesh.source_mesh_index)] for mesh in source_meshes)


def _source_export_float(position: Iterable[float]) -> bytes:
    return struct.pack("<3f", *(float(value) for value in position))


def _encode_position(
    wanted: tuple[float, float, float], mesh: _Mesh, source_lane: bytes
) -> tuple[bytes, float]:
    if len(source_lane) != 8:
        raise ModelImportError("source POSITION lane is truncated")
    words: list[int] = []
    decoded: list[float] = []
    for axis in range(3):
        normalized = (wanted[axis] - mesh.center[axis]) / mesh.scale[axis]
        if not math.isfinite(normalized) or normalized < -1.0 or normalized > 1.0:
            raise ModelImportError(
                "edited POSITION leaves the source mesh's fixed signed-normalized bounds"
            )
        word = max(-32767, min(32767, round(normalized * 32767.0)))
        words.append(word)
        decoded.append(mesh.center[axis] + (word / 32767.0) * mesh.scale[axis])
    encoded = struct.pack(">3h", *words) + source_lane[6:8]
    error = max(abs(decoded[axis] - wanted[axis]) for axis in range(3))
    return encoded, error


def _rebuild_entry(source: _Source, new_block0: bytes) -> tuple[bytes, dict[str, int]]:
    descriptor = source.record.blocks[0]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise ModelImportError("model DRAM block no longer uses the proved H7A wrapper")
    retail_payload = source.stored[0][apf_inner.H7A_HEADER_SIZE :]
    try:
        encoded, token_metrics = apf_inner.encode_h7a_preserving_tokens(
            retail_payload,
            source.blocks[0],
            new_block0,
            descriptor.wrapper.shift,
        )
    except apf_inner.FormatError as exc:
        raise ModelImportError(f"could not encode changed model DRAM: {exc}") from exc
    changed_stored = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(new_block0),
        apf_inner.H7A_HEADER_SIZE + len(encoded),
        descriptor.unknown_10,
        descriptor.wrapper.shift,
    ) + encoded
    stored = list(source.stored)
    stored[0] = changed_stored
    header = bytearray(source.original_entry[: source.record.header_size])
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
    if source.record.footer is None:
        raise ModelImportError("model outer entry lost its name footer")
    footer_total = 8 + source.record.footer.payload_size
    footer = source.original_entry[
        source.record.file_length : source.record.file_length + footer_total
    ]
    old_tail = source.original_entry[source.record.file_length + footer_total :]
    if len(footer) != footer_total or any(old_tail):
        raise ModelImportError("model outer footer/allocation tail changed")
    active = bytes(header) + bytes(body) + footer
    if len(active) > source.entry.size:
        raise ModelImportError(
            f"edited model exceeds its fixed outer allocation by {len(active) - source.entry.size} bytes"
        )
    return active + bytes(source.entry.size - len(active)), token_metrics


def build_model_patch(
    index_0a: Path,
    key: str,
    edited_gltf: Path,
    export_manifest: Path | None = None,
) -> ModelPatch:
    selected = target(key)
    gltf_path = Path(edited_gltf)
    manifest_path = (
        Path(export_manifest)
        if export_manifest is not None
        else gltf_path.with_name(f"{gltf_path.name}.apf-model.json")
    )
    source = _source(Path(index_0a), selected)
    meshes = _source_meshes(source)
    edited = _edited_meshes(gltf_path, manifest_path, source, meshes)
    new_system = bytearray(source.system)
    allowed: set[int] = set()
    changed_vertices = 0
    maximum_error = 0.0
    for mesh, wanted_positions in zip(meshes, edited):
        for vertex, (source_position, wanted) in enumerate(
            zip(mesh.source_positions, wanted_positions)
        ):
            lane = mesh.stream_start + vertex * mesh.stream_stride + mesh.lane_offset
            original = source.system[lane : lane + 8]
            allowed.update(range(lane, lane + 6))
            # The exporter writes decoded coordinates as float32.  Reimporting
            # that exact float32 triple must therefore be a byte-identical no-op
            # even when float32 lost enough precision to select an adjacent
            # signed-normalized integer on a naïve inverse calculation.
            if _source_export_float(source_position) == _source_export_float(wanted):
                encoded, error = original, 0.0
            else:
                encoded, error = _encode_position(wanted, mesh, original)
                changed_vertices += encoded != original
            new_system[lane : lane + 8] = encoded
            maximum_error = max(maximum_error, error)
    changed_offsets = {
        index
        for index, pair in enumerate(zip(source.system, new_system))
        if pair[0] != pair[1]
    }
    if not changed_offsets <= allowed:
        raise ModelImportError("model patch changed a byte outside POSITION XYZ")
    new_block0 = bytearray(source.blocks[0])
    start = source.system_part.offset
    new_block0[start : start + source.system_part.length] = new_system
    if not changed_offsets:
        rebuilt = source.original_entry
        token_metrics: dict[str, int] = {}
    else:
        rebuilt, token_metrics = _rebuild_entry(source, bytes(new_block0))

    memory = _BytesReader(rebuilt)
    try:
        rebuilt_record = apf_inner.parse_iff(memory, source.entry)
        rebuilt_blocks = tuple(
            apf_inner.decode_block(memory, rebuilt_record, index, 128 * 1024 * 1024)
            for index in range(rebuilt_record.block_count)
        )
    except apf_inner.FormatError as exc:
        raise ModelImportError(f"rebuilt model entry failed independent reopen: {exc}") from exc
    if rebuilt_blocks != (bytes(new_block0), *source.blocks[1:]):
        raise ModelImportError("rebuilt model entry does not decode to the intended blocks")
    output_item = rebuilt_record.files[selected.inner_index]
    output_part = output_item.parts[0]
    output_system = rebuilt_blocks[0][
        output_part.offset : output_part.offset + output_part.length
    ]
    if output_system != bytes(new_system):
        raise ModelImportError("rebuilt model SCNE differs after independent reopen")
    output_scene = apf_scene.parse_scene_system_part(
        output_system,
        outer_index=selected.outer_index,
        inner_index=selected.inner_index,
        capture_geometry=True,
    )
    output_meshes = _source_meshes(
        _Source(
            selected,
            source.entry,
            rebuilt_record,
            rebuilt,
            rebuilt_blocks,
            tuple(),
            output_part,
            output_system,
            output_scene,
        )
    )
    if tuple(mesh.source_triangles for mesh in output_meshes) != tuple(
        mesh.source_triangles for mesh in meshes
    ):
        raise ModelImportError("rebuilt model topology changed")
    segment = source.entry.segments[0]
    manifest: dict[str, object] = {
        "schema": IMPORT_SCHEMA,
        "target": {
            "key": selected.key,
            "outer_index": selected.outer_index,
            "inner_index": selected.inner_index,
            "root_name": selected.root_name,
        },
        "source": {
            "system_sha256": _sha256(source.system),
            "outer_entry_sha256": _sha256(source.original_entry),
        },
        "output": {
            "system_sha256": _sha256(output_system),
            "outer_entry_sha256": _sha256(rebuilt),
            "outer_pack_offset": segment.pack_offset,
            "outer_allocation_bytes": source.entry.size,
        },
        "changes": {
            "changed_vertex_count": changed_vertices,
            "changed_position_component_bytes": len(changed_offsets),
            "maximum_object_space_quantization_error": maximum_error,
            "no_op": not changed_offsets,
        },
        "preservation": {
            "expanded_triangle_lists_exact": True,
            "vertex_counts_exact": True,
            "position_w_exact": True,
            "normal_tangent_uv_blend_skin_material_attachment_bytes_exact": True,
            "non_target_scne_and_sibling_parts_exact": True,
            "fixed_outer_allocation_exact": True,
            "independent_reopen_exact": True,
        },
        "h7a_token_metrics": token_metrics,
        "claim_boundary": MODEL_IMPORT_BOUNDARY,
        "runtime_visibility_proved": False,
        "contains_retail_geometry": False,
    }
    return ModelPatch(
        selected,
        segment.pack_offset,
        source.entry.size,
        rebuilt,
        _sha256(source.original_entry),
        _sha256(rebuilt),
        changed_vertices,
        len(changed_offsets),
        maximum_error,
        not changed_offsets,
        manifest,
    )


def _copy_new(source: Path, destination: Path, progress: Progress) -> None:
    try:
        source_meta = source.lstat()
    except OSError as exc:
        raise ModelImportError(f"could not inspect source 0A: {exc}") from exc
    if stat.S_ISLNK(source_meta.st_mode) or not stat.S_ISREG(source_meta.st_mode):
        raise ModelImportError("source 0A must be a regular non-symlink file")
    flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    )
    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0),
    )
    try:
        destination_fd = os.open(destination, flags, stat.S_IMODE(source_meta.st_mode))
    except BaseException:
        os.close(source_fd)
        raise
    try:
        opened = os.fstat(source_fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            source_meta.st_dev, source_meta.st_ino, source_meta.st_size
        ):
            raise ModelImportError("source 0A changed while opening")
        copied = opened.st_size if try_reflink(destination_fd, source_fd) else 0
        copy_range_available = True
        if not copied:
            os.ftruncate(destination_fd, 0)
            while copied < opened.st_size:
                count = min(16 * 1024 * 1024, opened.st_size - copied)
                amount = 0
                if copy_range_available:
                    try:
                        amount = platform_compat.copy_file_range(source_fd, destination_fd, count)
                    except OSError as exc:
                        unsupported = {
                            errno.EXDEV,
                            errno.EINVAL,
                            errno.ENOSYS,
                            getattr(errno, "ENOTSUP", errno.EINVAL),
                            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
                        }
                        if exc.errno not in unsupported:
                            raise
                        copy_range_available = False
                if not copy_range_available:
                    data = os.read(source_fd, count)
                    pending = memoryview(data)
                    while pending:
                        written = os.write(destination_fd, pending)
                        if written <= 0:
                            raise ModelImportError("short copy while creating output 0A")
                        pending = pending[written:]
                    amount = len(data)
                if amount <= 0:
                    raise ModelImportError("short copy while creating output 0A")
                copied += amount
                progress("Copying a safe separate 0A", copied, opened.st_size)
        os.fsync(destination_fd)
        if os.fstat(destination_fd).st_size != opened.st_size:
            raise ModelImportError("copied 0A has the wrong size")
    except BaseException:
        os.close(destination_fd)
        os.close(source_fd)
        destination.unlink(missing_ok=True)
        raise
    os.close(destination_fd)
    os.close(source_fd)


def import_model(
    index_0a: Path,
    key: str,
    edited_gltf: Path,
    output_0a: Path,
    export_manifest: Path | None = None,
    progress: Progress | None = None,
) -> ModelImportReceipt:
    report = progress or (lambda _stage, _completed, _total: None)
    source_path = Path(index_0a)
    destination = Path(output_0a)
    receipt_path = destination.with_name(f"{destination.name}.apf-model-import.json")
    if destination.name != "0A":
        raise ModelImportError("model import output must be a new file named 0A")
    if not destination.parent.is_dir():
        raise ModelImportError("model import output directory does not exist")
    if destination.resolve(strict=False) == source_path.resolve(strict=True):
        raise ModelImportError("model import never overwrites the source 0A")
    for path in (destination, receipt_path):
        if path.exists() or path.is_symlink():
            raise ModelImportError(f"refusing to overwrite model import output: {path}")
    report("Validating source-bound edited glTF", 0, 3)
    patch = build_model_patch(source_path, key, Path(edited_gltf), export_manifest)
    try:
        _copy_new(source_path, destination, report)
        descriptor = os.open(
            destination,
            os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_BINARY", 0),
        )
        try:
            amount = platform_compat.pwrite(descriptor, patch.rebuilt_entry, patch.outer_offset)
            if amount != patch.outer_size:
                raise ModelImportError("short write while installing rebuilt model entry")
            os.fsync(descriptor)
            reopened = platform_compat.pread(descriptor, patch.outer_size, patch.outer_offset)
            if _sha256(reopened) != patch.output_entry_sha256:
                raise ModelImportError("published 0A model entry failed independent reread")
        finally:
            os.close(descriptor)
        document = {
            **patch.manifest,
            "published_output": {
                "name": destination.name,
                "size_bytes": destination.stat().st_size,
                "outer_entry_reread_sha256": patch.output_entry_sha256,
            },
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        receipt_fd = os.open(receipt_path, flags, 0o600)
        try:
            payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
            if os.write(receipt_fd, payload) != len(payload):
                raise ModelImportError("short model import receipt write")
            os.fsync(receipt_fd)
        finally:
            os.close(receipt_fd)
    except BaseException:
        receipt_path.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    report("Verified model import 0A ready", 3, 3)
    return ModelImportReceipt(
        patch.target,
        destination,
        receipt_path,
        patch.changed_vertex_count,
        patch.maximum_quantization_error,
        patch.no_op,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Import a source-bound, same-topology APF helmet/player glTF POSITION "
            "edit into a separate verified 0A."
        )
    )
    parser.add_argument("--index", required=True, type=Path, help="source retail 0A")
    parser.add_argument("--target", required=True, choices=("helmet", "player"))
    parser.add_argument("--gltf", required=True, type=Path, help="edited exported glTF")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="source export manifest (defaults to <gltf>.apf-model.json)",
    )
    parser.add_argument(
        "--output-volume",
        required=True,
        type=Path,
        help="new output path whose filename must be 0A",
    )
    args = parser.parse_args(argv)

    def progress(stage: str, completed: int, total: int) -> None:
        print(f"[{completed}/{total}] {stage}", file=sys.stderr, flush=True)

    try:
        receipt = import_model(
            args.index,
            args.target,
            args.gltf,
            args.output_volume,
            args.manifest,
            progress,
        )
    except (ModelImportError, OSError) as exc:
        parser.exit(2, f"model import failed: {exc}\n")
    print(
        json.dumps(
            {
                "output_0a": str(receipt.output_0a),
                "receipt": str(receipt.receipt),
                "target": receipt.target.key,
                "changed_vertex_count": receipt.changed_vertex_count,
                "maximum_quantization_error": receipt.maximum_quantization_error,
                "no_op": receipt.no_op,
            },
            sort_keys=True,
        )
    )
    return 0


__all__ = [
    "IMPORT_SCHEMA",
    "MODEL_IMPORT_BOUNDARY",
    "ModelImportError",
    "ModelImportReceipt",
    "ModelPatch",
    "build_model_patch",
    "import_model",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
