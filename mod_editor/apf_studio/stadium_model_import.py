"""Bounded APF stadium mesh hand-off for catalog-authorized static surfaces.

The product can round-trip the 77 statically proved outer-14/inner-8 targets,
but it still cannot author arbitrary stadium models.  An exported hand-off is
a POSITION plus expanded-triangle glTF.  Import requires the exact source
vertex count and exact expanded topology, rejects transforms/materials/skins
and every non-POSITION attribute, then delegates to the copied-1A writer and
its independent verifier.  Game UVs, normals, materials, attachments and all
container bytes outside the selected FLOAT32x3 lane remain byte-identical.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import struct
import tempfile
from typing import Any

from .backend import ensure_tools_importable


ensure_tools_importable()
import apf_stadium_catalog_position_patch as stadium_writer  # type: ignore  # noqa: E402
import apf_stadium_catalog_position_verify as stadium_verifier  # type: ignore  # noqa: E402


HANDOFF_SCHEMA = "apf2k8_stadium_position_gltf_handoff/v1"
SERVICE_SCHEMA = "apf2k8_stadium_position_import_service/v1"
MAX_GLTF_BYTES = 16 * 1024 * 1024
MAX_BUFFER_BYTES = 256 * 1024 * 1024
BOUNDARY = (
    "Catalog-authorized same-count POSITION-only stadium import. Expanded "
    "triangle topology must match the private source-derived reference exactly. "
    "Node transforms, UV/normal/tangent edits, materials, skins, animation, "
    "collision, attachments and changed topology are rejected; those original "
    "game lanes are preserved byte-for-byte in the copied 1A output."
)


class StadiumModelImportError(ValueError):
    """A glTF or destination leaves the proved stadium write boundary."""


@dataclass(frozen=True, slots=True)
class StadiumTarget:
    target_id: str
    outer_index: int
    inner_index: int
    node_index: int
    node_name: str
    vertex_count: int


@dataclass(frozen=True, slots=True)
class StadiumMeshExport:
    target: StadiumTarget
    gltf_path: Path
    bin_path: Path
    triangle_count: int


@dataclass(frozen=True, slots=True)
class StadiumMeshImportReceipt:
    target: StadiumTarget
    output_directory: Path
    output_pack: Path
    manifest: Path
    changed_byte_count: int
    no_op: bool
    verification: dict[str, Any]


def _target(row: dict[str, Any]) -> StadiumTarget:
    return StadiumTarget(
        target_id=str(row["candidate_id"]),
        outer_index=int(stadium_writer.OUTER_INDEX),
        inner_index=int(stadium_writer.INNER_INDEX),
        node_index=int(row["node"]["index"]),
        node_name=str(row["node"]["name"]),
        vertex_count=int(row["position0"]["vertex_count"]),
    )


def targets() -> tuple[StadiumTarget, ...]:
    """Return the shipped 77-target catalog in stable scene-node order."""

    _catalog, by_id = stadium_writer.load_catalog()
    return tuple(sorted((_target(row) for row in by_id.values()), key=lambda value: value.node_index))


def target_by_id(target_id: str) -> StadiumTarget:
    _catalog, by_id = stadium_writer.load_catalog()
    row = by_id.get(target_id)
    if row is None:
        raise StadiumModelImportError("That stadium surface is not in the shipped 77-target catalog")
    return _target(row)


def target_for_surface(
    outer_index: int,
    inner_index: int,
    scene_node_indices: tuple[int, ...] | list[int],
) -> StadiumTarget | None:
    if (outer_index, inner_index) != (
        stadium_writer.OUTER_INDEX,
        stadium_writer.INNER_INDEX,
    ):
        return None
    wanted = {int(value) for value in scene_node_indices}
    matches = [value for value in targets() if value.node_index in wanted]
    return matches[0] if len(matches) == 1 else None


def _regular_bytes(path: Path, maximum: int, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise StadiumModelImportError(f"Could not inspect {label}: {exc}") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or not 0 < metadata.st_size <= maximum
    ):
        raise StadiumModelImportError(f"{label} must be a bounded regular non-symlink file")
    return path.read_bytes()


def _strict_json(path: Path) -> dict[str, Any]:
    raw = _regular_bytes(path, MAX_GLTF_BYTES, "glTF")

    def reject_constant(value: str) -> None:
        raise StadiumModelImportError(f"glTF contains non-JSON numeric constant {value!r}")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise StadiumModelImportError(f"glTF contains duplicate key {key!r}")
            output[key] = value
        return output

    try:
        value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StadiumModelImportError(f"Invalid glTF JSON: {exc}") from exc
    asset = value.get("asset") if isinstance(value, dict) else None
    if not isinstance(value, dict) or not isinstance(asset, dict) or asset.get("version") != "2.0":
        raise StadiumModelImportError("The edited file must be a glTF 2.0 JSON object")
    return value


def _buffer(document: dict[str, Any], gltf_path: Path) -> bytes:
    rows = document.get("buffers")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise StadiumModelImportError("The stadium hand-off must contain exactly one external buffer")
    uri = rows[0].get("uri")
    if (
        not isinstance(uri, str)
        or not uri
        or Path(uri).name != uri
        or "/" in uri
        or "\\" in uri
    ):
        raise StadiumModelImportError("The stadium hand-off buffer URI must be one local filename")
    payload = _regular_bytes(gltf_path.parent / uri, MAX_BUFFER_BYTES, "glTF binary buffer")
    if rows[0].get("byteLength") != len(payload):
        raise StadiumModelImportError("The glTF binary length differs from its declaration")
    return payload


def _list(document: dict[str, Any], name: str) -> list[Any]:
    value = document.get(name)
    if not isinstance(value, list):
        raise StadiumModelImportError(f"glTF {name} must be an array")
    return value


def _accessor(
    document: dict[str, Any],
    payload: bytes,
    accessor_index: int,
    *,
    position: bool,
) -> tuple[Any, ...]:
    accessors = _list(document, "accessors")
    views = _list(document, "bufferViews")
    if isinstance(accessor_index, bool) or not isinstance(accessor_index, int) or not 0 <= accessor_index < len(accessors):
        raise StadiumModelImportError("glTF accessor index is outside the accessor table")
    row = accessors[accessor_index]
    if not isinstance(row, dict) or "sparse" in row or row.get("normalized", False):
        raise StadiumModelImportError("Sparse or normalized accessors are not supported")
    view_index = row.get("bufferView")
    if isinstance(view_index, bool) or not isinstance(view_index, int) or not 0 <= view_index < len(views):
        raise StadiumModelImportError("glTF accessor has no valid bufferView")
    view = views[view_index]
    if not isinstance(view, dict) or view.get("buffer") != 0:
        raise StadiumModelImportError("Every hand-off accessor must use the one declared buffer")
    count = row.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise StadiumModelImportError("glTF accessor count is invalid")
    component = row.get("componentType")
    kind = row.get("type")
    if position:
        if component != 5126 or kind != "VEC3":
            raise StadiumModelImportError("POSITION must be non-normalized FLOAT VEC3")
        fmt, components, item_size = "<3f", 3, 12
    else:
        if kind != "SCALAR" or component not in (5121, 5123, 5125):
            raise StadiumModelImportError("Triangle indices must be unsigned SCALAR data")
        fmt, components, item_size = {
            5121: ("<B", 1, 1),
            5123: ("<H", 1, 2),
            5125: ("<I", 1, 4),
        }[component]
    accessor_offset = row.get("byteOffset", 0)
    view_offset = view.get("byteOffset", 0)
    view_length = view.get("byteLength")
    stride = view.get("byteStride", item_size)
    integers = (accessor_offset, view_offset, view_length, stride)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in integers):
        raise StadiumModelImportError("glTF accessor offsets, lengths and stride must be integers")
    if accessor_offset < 0 or view_offset < 0 or view_length < 0 or stride < item_size:
        raise StadiumModelImportError("glTF accessor offsets, lengths or stride are invalid")
    start = view_offset + accessor_offset
    end = start + (count - 1) * stride + item_size
    if end > view_offset + view_length or end > len(payload):
        raise StadiumModelImportError("glTF accessor reads past its declared bufferView")
    values: list[Any] = []
    for index in range(count):
        decoded = struct.unpack_from(fmt, payload, start + index * stride)
        if position:
            if len(decoded) != components or not all(math.isfinite(value) for value in decoded):
                raise StadiumModelImportError("POSITION contains a non-finite component")
            values.append(tuple(float(value) for value in decoded))
        else:
            values.append(int(decoded[0]))
    return tuple(values)


def _identity_nodes(
    document: dict[str, Any], mesh_index: int, *, allow_reference_unit_root: bool
) -> None:
    nodes = document.get("nodes", [])
    if not isinstance(nodes, list):
        raise StadiumModelImportError("glTF nodes must be an array")
    owners = 0
    for row in nodes:
        if not isinstance(row, dict):
            raise StadiumModelImportError("glTF node is malformed")
        owns_mesh = row.get("mesh") == mesh_index
        for key in ("matrix", "translation", "rotation", "scale"):
            if key in row:
                allowed = {
                    "translation": [0, 0, 0],
                    "rotation": [0, 0, 0, 1],
                    "scale": [1, 1, 1],
                }.get(key)
                actual = row[key]
                reference_scale = (
                    allow_reference_unit_root
                    and not owns_mesh
                    and key == "scale"
                    and actual == [0.01, 0.01, 0.01]
                )
                if (
                    not reference_scale
                    and (allowed is None or not isinstance(actual, list) or actual != allowed)
                ):
                    raise StadiumModelImportError("Apply every object transform before stadium import")
        if owns_mesh:
            owners += 1
            if "skin" in row or "weights" in row:
                raise StadiumModelImportError("Stadium skin or morph authoring is not supported")
    if owners != 1:
        raise StadiumModelImportError("The selected hand-off mesh must be owned by exactly one node")


def _mesh_payload(
    gltf_path: Path,
    selected: StadiumTarget,
    *,
    private_reference: bool = False,
) -> tuple[tuple[tuple[float, float, float], ...], tuple[int, ...]]:
    document = _strict_json(gltf_path)
    for name in ("materials", "textures", "images", "samplers", "skins", "animations"):
        value = document.get(name)
        if value not in (None, []):
            raise StadiumModelImportError(f"{name} authoring is outside the POSITION-only stadium boundary")
    payload = _buffer(document, gltf_path)
    meshes = _list(document, "meshes")
    candidates: list[tuple[int, dict[str, Any]]] = []
    for index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            raise StadiumModelImportError("glTF mesh is malformed")
        extras = mesh.get("extras", {})
        if not isinstance(extras, dict):
            raise StadiumModelImportError("glTF mesh extras are malformed")
        tagged = extras.get("apf_scene_node_index") == selected.node_index
        handoff = extras.get("apf2k8_target_id") == selected.target_id
        if tagged or handoff:
            candidates.append((index, mesh))
    if not candidates and len(meshes) == 1:
        candidates = [(0, meshes[0])]
    if len(candidates) != 1:
        raise StadiumModelImportError("Could not identify exactly one catalog-selected mesh in the glTF")
    mesh_index, mesh = candidates[0]
    primitives = mesh.get("primitives")
    if not isinstance(primitives, list) or len(primitives) != 1 or not isinstance(primitives[0], dict):
        raise StadiumModelImportError("The selected mesh must contain exactly one triangle primitive")
    primitive = primitives[0]
    attributes = primitive.get("attributes")
    if not isinstance(attributes, dict) or set(attributes) != {"POSITION"}:
        raise StadiumModelImportError("Export only POSITION; UV, normal, tangent and other attributes cannot be authored")
    if primitive.get("mode", 4) != 4 or "indices" not in primitive or "targets" in primitive or "material" in primitive:
        raise StadiumModelImportError("The selected mesh must keep one unmaterialed indexed TRIANGLES primitive")
    _identity_nodes(
        document, mesh_index, allow_reference_unit_root=private_reference
    )
    positions = _accessor(document, payload, attributes["POSITION"], position=True)
    indices = _accessor(document, payload, primitive["indices"], position=False)
    if len(positions) != selected.vertex_count:
        raise StadiumModelImportError(f"This surface requires exactly {selected.vertex_count:,} vertices")
    if len(indices) % 3 or any(index < 0 or index >= len(positions) for index in indices):
        raise StadiumModelImportError("Expanded triangle topology contains an invalid index")
    return positions, indices  # type: ignore[return-value]


def _source_position_hash(positions: tuple[tuple[float, float, float], ...]) -> str:
    return hashlib.sha256(b"".join(struct.pack(">3f", *value) for value in positions)).hexdigest()


def export_editable_mesh(
    private_reference_gltf: Path,
    target_id: str,
    destination_gltf: Path,
) -> StadiumMeshExport:
    """Export one source-authenticated, retail-private POSITION hand-off."""

    selected = target_by_id(target_id)
    positions, indices = _mesh_payload(
        Path(private_reference_gltf), selected, private_reference=True
    )
    _catalog, by_id = stadium_writer.load_catalog()
    expected_position_hash = str(by_id[target_id]["position0"]["retail_lane_sha256"])
    if _source_position_hash(positions) != expected_position_hash:
        raise StadiumModelImportError("The private preview no longer matches the pinned retail POSITION lane")
    destination = Path(destination_gltf)
    if destination.suffix.casefold() != ".gltf":
        raise StadiumModelImportError("Choose a new .gltf filename for the stadium hand-off")
    binary_path = destination.with_suffix(".bin")
    if destination.exists() or destination.is_symlink() or binary_path.exists() or binary_path.is_symlink():
        raise StadiumModelImportError("Stadium mesh export never overwrites an existing glTF or binary")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise StadiumModelImportError("The stadium export parent must be a real directory")
    position_bytes = b"".join(struct.pack("<3f", *value) for value in positions)
    index_offset = (len(position_bytes) + 3) & ~3
    binary = position_bytes + b"\0" * (index_offset - len(position_bytes)) + b"".join(
        struct.pack("<I", value) for value in indices
    )
    minimum = [min(value[axis] for value in positions) for axis in range(3)]
    maximum = [max(value[axis] for value in positions) for axis in range(3)]
    document = {
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(positions), "max": maximum, "min": minimum, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5125, "count": len(indices), "type": "SCALAR"},
        ],
        "asset": {"generator": "APF 2K8 Mod Studio", "version": "2.0"},
        "bufferViews": [
            {"buffer": 0, "byteLength": len(position_bytes), "byteOffset": 0, "target": 34962},
            {"buffer": 0, "byteLength": len(indices) * 4, "byteOffset": index_offset, "target": 34963},
        ],
        "buffers": [{"byteLength": len(binary), "uri": binary_path.name}],
        "extras": {
            "apf2k8_stadium_position_handoff": {
                "boundary": BOUNDARY,
                "catalog_sha256": stadium_writer.CATALOG_SHA256,
                "schema": HANDOFF_SCHEMA,
                "source_position_sha256": expected_position_hash,
                "target_id": target_id,
            }
        },
        "meshes": [{
            "extras": {"apf2k8_target_id": target_id, "apf_scene_node_index": selected.node_index},
            "name": selected.node_name,
            "primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}],
        }],
        "nodes": [{"mesh": 0, "name": selected.node_name}],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
    }
    try:
        with binary_path.open("xb") as stream:
            stream.write(binary)
        try:
            with destination.open("xb") as stream:
                stream.write((json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        except Exception:
            binary_path.unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise StadiumModelImportError(f"Could not publish the stadium mesh hand-off: {exc}") from exc
    return StadiumMeshExport(selected, destination, binary_path, len(indices) // 3)


def import_edited_mesh(
    game_root: Path,
    private_reference_gltf: Path,
    target_id: str,
    edited_gltf: Path,
    output_directory: Path,
) -> StadiumMeshImportReceipt:
    """Write and independently verify one copied-1A POSITION-only edit."""

    selected = target_by_id(target_id)
    source_positions, source_indices = _mesh_payload(
        Path(private_reference_gltf), selected, private_reference=True
    )
    _catalog, by_id = stadium_writer.load_catalog()
    if _source_position_hash(source_positions) != by_id[target_id]["position0"]["retail_lane_sha256"]:
        raise StadiumModelImportError(
            "The private reference no longer matches the pinned retail POSITION lane"
        )
    positions, indices = _mesh_payload(Path(edited_gltf), selected)
    if indices != source_indices:
        raise StadiumModelImportError("Expanded triangle topology differs from the private source-derived reference")
    output = Path(output_directory)
    if output.exists() or output.is_symlink():
        raise StadiumModelImportError("Stadium import never overwrites an existing output directory")
    parent = output.parent
    try:
        parent_info = parent.lstat()
    except OSError as exc:
        raise StadiumModelImportError(f"Could not inspect the output parent: {exc}") from exc
    if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
        raise StadiumModelImportError("The output parent must be a real non-symlink directory")
    recipe = copy.deepcopy(stadium_writer.RECIPE_CONSTANTS)
    recipe["target_id"] = target_id
    recipe["positions"] = [list(value) for value in positions]
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", suffix=".stadium-import", dir=parent))
    artifact_dir = staging / "artifact"
    recipe_path = staging / "recipe.json"
    try:
        recipe_path.write_bytes(stadium_writer.canonical_json_bytes(recipe))
        manifest = stadium_writer.write_output(Path(game_root), recipe_path, artifact_dir)
        verification, independently_derived = stadium_verifier.verify(
            Path(game_root), recipe_path, artifact_dir
        )
        if manifest != independently_derived:
            raise StadiumModelImportError("Independent stadium verification returned a different manifest")
        artifact_dir.rename(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    changed = int(manifest["result"]["changed_decoded_block0_byte_count"])
    return StadiumMeshImportReceipt(
        selected,
        output,
        output / stadium_writer.OUTPUT_PACK_NAME,
        output / stadium_writer.MANIFEST_NAME,
        changed,
        positions == source_positions,
        verification,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="export one catalog-selected mesh hand-off")
    export.add_argument("--reference-gltf", type=Path, required=True)
    export.add_argument("--target", required=True)
    export.add_argument("--output-gltf", type=Path, required=True)
    imported = commands.add_parser("import", help="build and verify a copied-1A POSITION edit")
    imported.add_argument("--game-dir", type=Path, required=True)
    imported.add_argument("--reference-gltf", type=Path, required=True)
    imported.add_argument("--target", required=True)
    imported.add_argument("--edited-gltf", type=Path, required=True)
    imported.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "export":
            receipt = export_editable_mesh(
                args.reference_gltf, args.target, args.output_gltf
            )
            print(
                "APF_STADIUM_MESH_EXPORT_PASS "
                f"target={receipt.target.target_id} vertices={receipt.target.vertex_count} "
                f"triangles={receipt.triangle_count} gltf={receipt.gltf_path}"
            )
        else:
            receipt = import_edited_mesh(
                args.game_dir,
                args.reference_gltf,
                args.target,
                args.edited_gltf,
                args.output_dir,
            )
            print(
                "APF_STADIUM_MESH_IMPORT_PASS "
                f"target={receipt.target.target_id} changed_bytes={receipt.changed_byte_count} "
                f"output={receipt.output_directory} runtime=false hardware=false"
            )
        return 0
    except (StadiumModelImportError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=__import__("sys").stderr)
        return 1


__all__ = [
    "BOUNDARY",
    "StadiumMeshExport",
    "StadiumMeshImportReceipt",
    "StadiumModelImportError",
    "StadiumTarget",
    "export_editable_mesh",
    "import_edited_mesh",
    "target_by_id",
    "target_for_surface",
    "targets",
]


if __name__ == "__main__":
    raise SystemExit(main())
