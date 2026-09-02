"""Bounded same-count position-only import for ten proved Crib meshes.

The selected meshes are exactly the geometry owning the 25 electronics
surfaces.  A complete source-derived glTF may be edited in Blender, but the
compiler retains only changed vertex positions after proving the original
vertex count and triangle topology.  UVs, materials, collision, indices,
normals/other registers, commands, bounds, and every non-position byte remain
the user's source bytes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import struct
from typing import Any, Mapping, Sequence

from .errors import ValidationError
from . import nfl2k5_stadium_texture_writer as stadium
from .nfl2k5_crib_scene_texture_writer import _Resolver

try:
    from nfl_scne_inventory import parse_scene
    from nfl_static_gltf import export_scene
except ImportError as exc:  # pragma: no cover - packaged runtime boundary
    raise RuntimeError("The NFL SCNE geometry toolchain is unavailable") from exc


CATALOG_SCHEMA = "nfl2k5_crib_static_position_targets/v1"
CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "reports/specs/nfl2k5_crib_static_position_targets.v1.json"
)
CATALOG_SIZE = 14_024
CATALOG_SHA256 = "90f955166c8582f7041bd0d936bacbef1f44b3869487f71535acec1caeb44b4f"
RECIPE_SCHEMA = "2k5_mod_studio_crib_geometry_recipe/v1"
IMPORT_SCHEMA = "nfl2k5_crib_geometry_unified_import/v1"
MAX_RECIPE_BYTES = 64 * 1024 * 1024
UNIT_SCALE = 0.01


class CribGeometryWriterError(ValidationError):
    """A glTF, recipe, or source scene escaped the bounded contract."""


@dataclass(frozen=True)
class CompiledCribGeometryRecipe:
    scene_id: str
    recipe: bytes = field(repr=False)
    recipe_sha256: str
    changed_target_count: int
    changed_vertex_count: int
    preserved_triangle_count: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CribGeometryWriterError(message)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _load_catalog(
    path: Path = CATALOG_PATH, *, enforce_pin: bool = True
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    try:
        info = path.lstat()
        payload = path.read_bytes()
    except OSError as exc:
        raise CribGeometryWriterError(f"Could not read the Crib geometry catalog ({exc}).") from exc
    _require(path.is_file() and not path.is_symlink(), "Crib geometry catalog must be a regular file")
    if enforce_pin:
        _require(
            info.st_size == CATALOG_SIZE and _sha(payload) == CATALOG_SHA256,
            "Bounded Crib geometry catalog identity changed",
        )
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CribGeometryWriterError(f"Could not decode the Crib geometry catalog ({exc}).") from exc
    raw = document.get("targets") if isinstance(document, dict) else None
    _require(
        isinstance(document, dict)
        and document.get("schema") == CATALOG_SCHEMA
        and isinstance(raw, list)
        and len(raw) == 10,
        "Bounded Crib geometry catalog schema changed",
    )
    rows: dict[str, dict[str, Any]] = {}
    for row in raw:
        _require(isinstance(row, dict) and isinstance(row.get("target_id"), str),
                 "Crib geometry catalog has an invalid target")
        target_id = str(row["target_id"])
        _require(target_id not in rows, "Crib geometry catalog target repeats")
        rows[target_id] = row
    return document, rows


def list_editable_scenes() -> tuple[dict[str, object], ...]:
    """Return retail-free scene/shape metadata for the GUI."""

    _document, rows = _load_catalog()
    grouped: dict[str, dict[str, object]] = {}
    for row in rows.values():
        source = row["source_identity"]
        item = grouped.setdefault(str(row["scene_id"]), {
            "scene_id": str(row["scene_id"]),
            "scene_name": str(source["scene_name"]),
            "chunk_index": int(source["chunk_index"]),
            "shape_names": [],
            "target_count": 0,
        })
        item["shape_names"].append(str(row["shape"]["name"]))
        item["target_count"] = int(item["target_count"]) + 1
    return tuple(
        {**item, "shape_names": tuple(item["shape_names"])}
        for _key, item in sorted(grouped.items())
    )


def _rows_for_scene(
    scene_id: str, catalog: Mapping[str, dict[str, Any]]
) -> tuple[dict[str, Any], ...]:
    rows = tuple(
        sorted(
            (row for row in catalog.values() if row.get("scene_id") == scene_id),
            key=lambda row: int(row["shape"]["index"]),
        )
    )
    _require(bool(rows), "Choose one of the seven bounded Crib electronics scenes")
    return rows


def _read_gltf(path: Path) -> tuple[dict[str, Any], tuple[bytes, ...]]:
    try:
        return stadium._read_gltf_bundle(path)
    except stadium.StadiumTextureWriterError as exc:
        raise CribGeometryWriterError(str(exc).replace("Stadium", "Crib")) from exc


def _mesh(document: Mapping[str, Any], row: Mapping[str, Any]) -> Mapping[str, Any]:
    shape = row["shape"]
    try:
        return stadium._mesh_by_shape(document, int(shape["index"]), str(shape["name"]))
    except stadium.StadiumTextureWriterError as exc:
        raise CribGeometryWriterError(str(exc).replace("Stadium", "Crib")) from exc


def _positions(
    document: Mapping[str, Any], buffers: Sequence[bytes], mesh: Mapping[str, Any]
) -> tuple[tuple[float, float, float], ...]:
    try:
        return stadium._mesh_positions(document, buffers, mesh)
    except stadium.StadiumTextureWriterError as exc:
        raise CribGeometryWriterError(str(exc).replace("Stadium", "Crib")) from exc


def _triangles(
    document: Mapping[str, Any], buffers: Sequence[bytes], mesh: Mapping[str, Any]
) -> Counter[tuple[int, int, int]]:
    try:
        return stadium._mesh_triangles(document, buffers, mesh)
    except stadium.StadiumTextureWriterError as exc:
        raise CribGeometryWriterError(str(exc).replace("Stadium", "Crib")) from exc


def _triangle_hash(value: Counter[tuple[int, int, int]]) -> str:
    # The public catalog is generated with the established Stadium canonical
    # evidence serializer; keep that exact identity separate from compact
    # private recipe serialization.
    return _sha(stadium._canonical_json(
        sorted((list(key), count) for key, count in value.items())
    ))


def compile_crib_geometry_recipe(
    scene_id: str,
    source_gltf: Path,
    imported_gltf: Path,
    *,
    catalog_path: Path = CATALOG_PATH,
    enforce_catalog_pin: bool = True,
) -> CompiledCribGeometryRecipe:
    """Validate one edited glTF and keep only user-changed vertex positions."""

    _document, catalog = _load_catalog(catalog_path, enforce_pin=enforce_catalog_pin)
    rows = _rows_for_scene(scene_id, catalog)
    before_document, before_buffers = _read_gltf(source_gltf)
    after_document, after_buffers = _read_gltf(imported_gltf)
    edits: list[dict[str, object]] = []
    changed_vertices = 0
    triangle_count = 0
    for row in rows:
        source_mesh = _mesh(before_document, row)
        edited_mesh = _mesh(after_document, row)
        before = _positions(before_document, before_buffers, source_mesh)
        after = _positions(after_document, after_buffers, edited_mesh)
        expected = int(row["shape"]["vertex_count"])
        _require(
            len(before) == len(after) == expected,
            f"{row['shape']['name']} must keep exactly {expected} vertices; "
            "add/remove, subdivide, weld, decimate, and topology modifiers are unsupported",
        )
        before_bytes = b"".join(struct.pack("<3f", *xyz) for xyz in before)
        _require(
            _sha(before_bytes) == row["position"]["source_gltf_float3_sha256"],
            f"The source {row['shape']['name']} positions changed from the private export",
        )
        source_topology = _triangles(before_document, before_buffers, source_mesh)
        edited_topology = _triangles(after_document, after_buffers, edited_mesh)
        _require(
            edited_topology == source_topology
            and _triangle_hash(source_topology) == row["topology_sha256"],
            f"{row['shape']['name']} topology changed. Move vertices only; "
            "faces and indices must remain the same.",
        )
        triangle_count += sum(source_topology.values())
        changes = [
            [index, *xyz]
            for index, (old, xyz) in enumerate(zip(before, after, strict=True))
            if struct.pack("<3f", *old) != struct.pack("<3f", *xyz)
        ]
        if changes:
            changed_vertices += len(changes)
            edits.append({
                "changes": changes,
                "source_position_sha256": _sha(before_bytes),
                "target_id": row["target_id"],
                "topology_sha256": row["topology_sha256"],
            })
    _require(bool(edits), "That model has the original Crib positions; no geometry edit was staged")
    recipe = {
        "catalog": {"schema": CATALOG_SCHEMA, "sha256": CATALOG_SHA256},
        "edits": edits,
        "preservation": {
            "collision": "unchanged game bytes",
            "materials": "unchanged game bytes",
            "normals_and_other_vertex_registers": "unchanged game bytes",
            "topology": "validated equivalent before import",
            "uvs": "unchanged game bytes",
        },
        "scene_id": scene_id,
        "schema": RECIPE_SCHEMA,
    }
    payload = _canonical(recipe)
    _require(len(payload) <= MAX_RECIPE_BYTES, "Edited Crib position recipe is too large")
    return CompiledCribGeometryRecipe(
        scene_id, payload, _sha(payload), len(edits), changed_vertices, triangle_count
    )


def _source_shape(
    decoded: bytes, resolved: stadium._ResolvedStadiumScene, row: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source = row["source_identity"]
    _require(
        source["outer_index"] == 4248
        and source["chunk_index"] == resolved.contract.chunk_index
        and source["scene_index"] == resolved.contract.scene_index
        and source["decoded_sha256"] == _sha(decoded),
        "Crib geometry recipe belongs to a different source scene",
    )
    scene, _names, _mappings, _sample = parse_scene(
        resolved.contract.scene_index, resolved.resource, decoded, {}
    )
    _require(scene.get("name") == source["scene_name"], "Crib geometry scene name changed")
    shape_row = row["shape"]
    shapes = [
        shape for shape in scene["shapes"]
        if int(shape["index"]) == int(shape_row["index"])
        and shape["name"] == shape_row["name"]
    ]
    _require(len(shapes) == 1, "Crib geometry target shape no longer resolves uniquely")
    shape = shapes[0]
    _require(int(shape["vertex_count"]) == int(shape_row["vertex_count"]),
             "Crib geometry source vertex count changed")
    descriptors = [row for row in shape["attribute_descriptors"] if int(row["register"]) == 0]
    _require(len(descriptors) == 1, "Crib geometry source position descriptor changed")
    descriptor = descriptors[0]
    position = row["position"]
    _require(
        descriptor["format_name"] == row["decode"]["format"]
        and int(descriptor["byte_size"]) == int(position["component_size"])
        and int(descriptor["byte_offset"]) == int(position["byte_offset"]),
        "Crib geometry position format changed",
    )
    streams = [
        stream for stream in shape["vertex_streams"]
        if int(stream["stream_index"]) == int(descriptor["stream_index"])
    ]
    _require(len(streams) == 1, "Crib geometry source position stream changed")
    stream = streams[0]
    _require(
        int(stream["offset"]) == int(position["stream_offset"])
        and int(stream["stride"]) == int(position["stride"]),
        "Crib geometry source position lane moved",
    )
    return shape, descriptor, stream


def _lane_bytes(
    decoded: bytes, vertex_count: int, position: Mapping[str, Any]
) -> bytes:
    start = int(position["stream_offset"]) + int(position["byte_offset"])
    stride = int(position["stride"])
    size = int(position["component_size"])
    return b"".join(decoded[start + index * stride:start + index * stride + size]
                    for index in range(vertex_count))


def _encode_normshort(value: float, offset: float, scale: float) -> int:
    _require(math.isfinite(value) and math.isfinite(offset) and math.isfinite(scale) and scale != 0.0,
             "Crib NORMSHORT3 position is not finite")
    normalized = (value - offset) / scale
    _require(-1.000001 <= normalized <= 1.000001,
             "A moved Crib vertex is outside this model's fixed NORMSHORT3 decode range")
    normalized = min(1.0, max(-1.0, normalized))
    encoded = round(normalized * (32767.0 if normalized >= 0.0 else 32768.0))
    return min(32767, max(-32768, encoded))


def _load_apply_recipe(
    resolved: stadium._ResolvedStadiumScene,
    recipe_path: Path,
) -> tuple[Path, bytes, bytes, list[range], set[str], int, list[int]]:
    _document, catalog = _load_catalog()
    try:
        info = recipe_path.lstat()
        payload = recipe_path.read_bytes()
    except OSError as exc:
        raise CribGeometryWriterError(f"Could not read the private Crib geometry recipe ({exc}).") from exc
    _require(recipe_path.is_file() and not recipe_path.is_symlink()
             and 0 < info.st_size <= MAX_RECIPE_BYTES,
             "Private Crib geometry recipe is empty, too large, or not a regular file")
    try:
        recipe = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CribGeometryWriterError(f"Could not decode the Crib geometry recipe ({exc}).") from exc
    preservation = {
        "collision": "unchanged game bytes",
        "materials": "unchanged game bytes",
        "normals_and_other_vertex_registers": "unchanged game bytes",
        "topology": "validated equivalent before import",
        "uvs": "unchanged game bytes",
    }
    _require(
        payload == _canonical(recipe)
        and isinstance(recipe, dict)
        and set(recipe) == {"catalog", "edits", "preservation", "scene_id", "schema"}
        and recipe.get("schema") == RECIPE_SCHEMA
        and recipe.get("catalog") == {"schema": CATALOG_SCHEMA, "sha256": CATALOG_SHA256}
        and recipe.get("preservation") == preservation
        and isinstance(recipe.get("edits"), list)
        and bool(recipe["edits"]),
        "Crib geometry recipe contract changed",
    )
    rows = _rows_for_scene(str(recipe["scene_id"]), catalog)
    _require(
        resolved.contract.scene_id.replace("nfl2k5.stadium.", "nfl2k5.crib.", 1)
        == recipe["scene_id"],
        "Crib geometry recipe belongs to a different SCNE",
    )
    edited = bytearray(resolved.decoded)
    allowed: list[range] = []
    target_ids: set[str] = set()
    changed_vertices = 0
    for edit in recipe["edits"]:
        _require(
            isinstance(edit, dict)
            and set(edit) == {"changes", "source_position_sha256", "target_id", "topology_sha256"}
            and isinstance(edit.get("target_id"), str)
            and edit["target_id"] in catalog
            and edit["target_id"] not in target_ids,
            "Crib geometry recipe has an invalid or repeated target",
        )
        row = catalog[edit["target_id"]]
        _require(row in rows and edit["topology_sha256"] == row["topology_sha256"],
                 "Crib geometry recipe scene/topology changed")
        target_ids.add(edit["target_id"])
        shape, _descriptor, _stream = _source_shape(resolved.decoded, resolved, row)
        count = int(shape["vertex_count"])
        position = row["position"]
        lane = _lane_bytes(resolved.decoded, count, position)
        _require(
            _sha(lane) == position["source_lane_sha256"],
            "Crib source position lane changed from its bounded catalog",
        )
        changes = edit.get("changes")
        _require(isinstance(changes, list) and bool(changes),
                 "Crib geometry recipe has no changed vertices")
        seen: set[int] = set()
        for change in changes:
            _require(
                isinstance(change, list) and len(change) == 4
                and type(change[0]) is int and 0 <= change[0] < count
                and change[0] not in seen
                and all(type(value) in (int, float) and math.isfinite(float(value))
                        for value in change[1:]),
                "Crib geometry recipe contains an invalid changed vertex",
            )
            vertex = int(change[0])
            seen.add(vertex)
            xyz = tuple(float(value) for value in change[1:])
            start = (
                int(position["stream_offset"]) + vertex * int(position["stride"])
                + int(position["byte_offset"])
            )
            if row["decode"]["format"] == "FLOAT3":
                try:
                    packed = struct.pack("<3f", *xyz)
                except (OverflowError, struct.error) as exc:
                    raise CribGeometryWriterError("Crib FLOAT3 position is outside binary32") from exc
            else:
                scale = float(row["decode"]["scale"])
                offsets = tuple(float(value) for value in row["decode"]["offset"])
                encoded = tuple(
                    _encode_normshort(value, offsets[axis], scale)
                    for axis, value in enumerate(xyz)
                )
                packed = struct.pack("<3h", *encoded)
            end = start + len(packed)
            _require(end <= len(edited), "Crib geometry position falls outside its scene")
            if edited[start:end] != packed:
                changed_vertices += 1
            edited[start:end] = packed
            allowed.append(range(start, end))
    changed_offsets = [
        index for index, (before, after) in enumerate(zip(resolved.decoded, edited, strict=True))
        if before != after
    ]
    _require(bool(changed_offsets), "Crib geometry recipe quantizes to a no-op")
    _require(all(any(index in span for span in allowed) for index in changed_offsets),
             "Crib geometry edit escaped its proved position components")
    return recipe_path, payload, bytes(edited), allowed, target_ids, changed_vertices, changed_offsets


def _resolved_for_scene(
    index_path: Path, inventory_path: Path, scene_id: str
) -> stadium._ResolvedStadiumScene:
    _document, catalog = _load_catalog()
    rows = _rows_for_scene(scene_id, catalog)
    selector = str(rows[0]["texture_selectors"][0])
    return _Resolver(index_path, inventory_path).resolve_many([selector])[0]


def build_unified_crib_geometry_import(
    index_path: Path,
    inventory_path: Path,
    recipe_path: Path,
    texture_edits: Sequence[tuple[str, Path]] = (),
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Compile geometry, optionally composed with P8 edits from the same SCNE."""

    try:
        recipe_hint = json.loads(recipe_path.read_text(encoding="utf-8"))
        scene_id = str(recipe_hint["scene_id"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CribGeometryWriterError(f"Could not identify the Crib geometry recipe ({exc}).") from exc
    if texture_edits:
        resolver = _Resolver(index_path, inventory_path)
        resolved_rows = resolver.resolve_many([selector for selector, _png in texture_edits])
        resolved = resolved_rows[0]
    else:
        resolved = _resolved_for_scene(index_path, inventory_path, scene_id)
        resolved_rows = (resolved,)
    (
        recipe_file, recipe_payload, geometry_decoded, geometry_ranges,
        target_ids, changed_vertices, geometry_changed_offsets,
    ) = _load_apply_recipe(resolved, recipe_path)
    previews: list[tuple[str, bytes]] = []
    try:
        if texture_edits:
            compiled = stadium._compile_resolved_scene(
                resolved_rows,
                [png for _selector, png in texture_edits],
                base_decoded=geometry_decoded,
                base_allowed_ranges=geometry_ranges,
            )
            fixed = compiled.fixed
            changed_byte_count = compiled.decoded_changed_byte_count
            previews = [
                (f"crib-geometry-c{payload.contract.chunk_index:04d}-"
                 f"t{payload.contract.texture_index:03d}-preview.png",
                 payload.quantized_preview_png)
                for payload in compiled.textures
            ]
        else:
            fixed = stadium._rebuild_vc_lz_fixed_span(
                geometry_decoded,
                resolved.span[:stadium.HEADER.size],
                resolved.opaque_tail,
                consumed_cap=resolved.contract.retail_consumed,
                scratch_cap=stadium.SCNE_OBSERVED_SCRATCH_MAX,
                template_stream_prefix=(
                    resolved.span[stadium.HEADER.size:stadium.HEADER.size + 9]
                ),
            )
            changed_byte_count = len(geometry_changed_offsets)
    except stadium.StadiumTextureWriterError as exc:
        message = str(exc).replace("Stadium", "Crib").replace("stadium", "Crib")
        raise CribGeometryWriterError(message) from exc
    selector = f"{scene_id}.geometry"
    target = resolved.contract.target_metadata()
    target.update({
        "selector": selector,
        "scene_id": scene_id,
        "target_ids": sorted(target_ids),
        "target_count": len(target_ids),
        "texture_ids": [selector for selector, _png in texture_edits],
        "texture_count": len(texture_edits),
    })
    report = {
        "schema": IMPORT_SCHEMA,
        "input_recipe": {"path": str(recipe_file), "sha256": _sha(recipe_payload)},
        "target": target,
        "replacement": {
            "span_size": len(fixed.span),
            "span_sha256": _sha(fixed.span),
            "decoded_after_sha256": fixed.decoded_sha256,
            "decoded_changed_byte_count": changed_byte_count,
            "geometry_changed_byte_count": len(geometry_changed_offsets),
            "changed_vertex_count": changed_vertices,
            "normshort3_edits_quantized_to_source_format": True,
        },
        "claims": {
            "same_count_position_components_only": True,
            "topology_validated_equivalent_before_import": True,
            "source_uv_material_collision_indices_normals_and_other_bytes_preserved": True,
            "geometry_and_same_scene_textures_composed_before_compression": bool(texture_edits),
            "fixed_scne_allocation_preserved": True,
            "opaque_tail_preserved": True,
            "arbitrary_model_replacement": False,
            "contains_retail_bytes": False,
        },
    }
    return fixed.span, previews, report, selector, target


def _add_unit_root(document: dict[str, Any]) -> None:
    nodes = document.get("nodes")
    _require(isinstance(nodes, list) and bool(nodes), "Crib glTF has no nodes to export")
    scenes = document.get("scenes")
    if isinstance(scenes, list) and scenes:
        scene_index = document.get("scene", 0)
        _require(type(scene_index) is int and 0 <= scene_index < len(scenes),
                 "Crib glTF has no default scene")
        entry = scenes[scene_index]
        _require(isinstance(entry, dict) and isinstance(entry.get("nodes"), list),
                 "Crib glTF scene has no roots")
        roots = list(entry["nodes"])
    else:
        claimed = {
            child for node in nodes if isinstance(node, dict)
            for child in node.get("children", ()) if type(child) is int
        }
        roots = [index for index in range(len(nodes)) if index not in claimed]
        _require(bool(roots), "Crib glTF has no top-level nodes")
        entry = {}
        document["scenes"] = [entry]
        document["scene"] = 0
    nodes.append({
        "name": "nfl2k5_units_centimetre_to_metre",
        "scale": [UNIT_SCALE, UNIT_SCALE, UNIT_SCALE],
        "children": roots,
    })
    entry["nodes"] = [len(nodes) - 1]
    extras = document.setdefault("extras", {})
    if isinstance(extras, dict):
        extras["nfl2k5_unit_contract"] = {
            "authored_unit": "centimetre", "gltf_unit": "metre",
            "applied_as": "root node scale", "scale": UNIT_SCALE,
            "buffer_rewritten": False,
        }


def export_crib_scene_gltf(
    index_path: Path, inventory_path: Path, scene_id: str, destination: Path
) -> tuple[Path, Path]:
    """Derive one bounded Crib scene glTF directly from the private source."""

    resolved = _resolved_for_scene(index_path, inventory_path, scene_id)
    scene, _names, _mappings, _sample = parse_scene(
        resolved.contract.scene_index, resolved.resource, resolved.decoded, {}
    )
    target = destination.expanduser().absolute()
    binary_name = f"4248_{resolved.contract.chunk_index:04d}_{scene['name']}.bin"
    document, binary, _detail = export_scene(
        resolved.decoded, scene, {"decoded_sha256": _sha(resolved.decoded)}, binary_name
    )
    _require(document is not None and binary is not None,
             "The selected Crib scene has no proved static geometry")
    _add_unit_root(document)
    binary_target = target.with_name(binary_name)
    _require(target != binary_target, "Crib glTF and buffer cannot share one filename")
    _require(not os.path.lexists(target) and not os.path.lexists(binary_target),
             "A Crib model export file already exists at that destination")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    written: list[Path] = []
    try:
        with target.open("xb") as stream:
            stream.write(payload)
        written.append(target)
        with binary_target.open("xb") as stream:
            stream.write(binary)
        written.append(binary_target)
    except BaseException:
        for path in reversed(written):
            path.unlink(missing_ok=True)
        raise
    return target, binary_target


__all__ = [
    "CATALOG_PATH",
    "CompiledCribGeometryRecipe",
    "CribGeometryWriterError",
    "build_unified_crib_geometry_import",
    "compile_crib_geometry_recipe",
    "export_crib_scene_gltf",
    "list_editable_scenes",
]
