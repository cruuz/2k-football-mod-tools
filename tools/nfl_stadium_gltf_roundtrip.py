#!/usr/bin/env python3
"""Turn an edited glTF back into a stadium position recipe.

Exporting stadium geometry to glTF has worked for a while, and there is a
proved writer that replaces a target's FLOAT3 position lane inside its exact
allocation. What has never existed is the step between them: taking the file
back out of Blender and turning it into something the writer accepts. Without
it, "import a stadium model" meant hand-authoring a JSON array of several
hundred XYZ triples, which nobody was ever going to do.

This is that step, and it is deliberately narrow. It reads the positions out of
an edited glTF and emits the recipe the same-count writer already validates.

**It moves vertices. It does not add, remove, or reorder them.** The writer
replaces a fixed-size lane inside a fixed allocation, so the vertex count is
part of the target's identity -- a mesh that comes back with a different count
is a different mesh, and no amount of clever packing makes it fit. Reshape the
roof, raise the upper deck, lean the stands: yes. Model a new stadium: no, and
saying otherwise would be a lie the byte layout immediately exposes.

That count is checked here so the failure is a clear sentence in a terminal
rather than a refusal several steps later, and it is checked again by the
writer, which is the one that actually matters.

    python3 tools/nfl_stadium_gltf_roundtrip.py \\
        --gltf edited_roof.gltf --target-id nfl2k5/stadium/o3280/c5/s0 \\
        --recipe roof_recipe.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECIPE_SCHEMA = "nfl2k5_catalog_static_position_recipe/v2"
CATALOG_SCHEMA = "nfl2k5_stadium_static_target_catalog/v1"
CATALOG_PATH = ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
CATALOG_SHA256 = "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa"
MAX_GLTF_BYTES = 256 * 1024 * 1024
GLTF_FLOAT = 5126
DATA_URI = "data:application/octet-stream;base64,"


class RoundTripError(ValueError):
    """Raised when the glTF cannot become a recipe this writer would accept."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RoundTripError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    """Read the pinned target catalog.

    The catalog is research metadata that the release gate deliberately keeps
    out of a shipped tree, so a packaged copy of this tool needs it pointed at
    with --catalog. The writer this feeds has the same requirement, so anyone
    already using that lane already has the file.
    """
    require(
        path.is_file(),
        f"target catalog is missing: {path}. Pass --catalog to point at "
        "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json from a "
        "full checkout.",
    )
    payload = path.read_bytes()
    document = json.loads(payload.decode("utf-8"))
    require(document.get("schema") == CATALOG_SCHEMA,
            f"target catalog schema must be {CATALOG_SCHEMA}")
    rows = document.get("targets")
    rows = rows if isinstance(rows, list) else list((rows or {}).values())
    by_id = {str(row["target_id"]): row for row in rows}
    require(by_id, "target catalog lists no targets")
    return by_id


def _buffer_bytes(document: dict[str, Any], index: int, base: Path) -> bytes:
    buffers = document.get("buffers") or []
    require(0 <= index < len(buffers), f"glTF buffer {index} is missing")
    buffer = buffers[index]
    uri = buffer.get("uri")
    require(isinstance(uri, str) and uri,
            "GLB and buffer-less glTF are not supported; export .gltf + .bin")
    if uri.startswith("data:"):
        require(uri.startswith(DATA_URI), "unsupported embedded buffer encoding")
        return base64.b64decode(uri[len(DATA_URI):])
    resolved = (base / uri).resolve()
    require(resolved.is_file(), f"glTF buffer file is missing: {uri}")
    require(resolved.stat().st_size <= MAX_GLTF_BYTES, "glTF buffer is too large")
    return resolved.read_bytes()


def read_positions(gltf_path: Path, mesh_name: str | None = None
                   ) -> tuple[list[tuple[float, float, float]], str]:
    """Return the POSITION accessor of one primitive, and which mesh it came from."""
    path = Path(gltf_path).expanduser()
    require(path.is_file(), f"glTF is missing: {path}")
    require(path.stat().st_size <= MAX_GLTF_BYTES, "glTF is unreasonably large")
    document = json.loads(path.read_text(encoding="utf-8"))
    meshes = document.get("meshes") or []
    require(meshes, "glTF contains no meshes")

    chosen = None
    for mesh in meshes:
        if mesh_name is None or str(mesh.get("name")) == mesh_name:
            chosen = mesh
            break
    require(chosen is not None,
            f"glTF has no mesh named {mesh_name!r}; found "
            + ", ".join(repr(m.get("name")) for m in meshes[:8]))
    assert chosen is not None
    primitives = chosen.get("primitives") or []
    require(len(primitives) == 1,
            f"mesh {chosen.get('name')!r} has {len(primitives)} primitives; "
            "this lane edits one position lane, so export a single primitive")
    accessor_index = (primitives[0].get("attributes") or {}).get("POSITION")
    require(accessor_index is not None, "primitive has no POSITION attribute")

    accessors = document.get("accessors") or []
    require(0 <= accessor_index < len(accessors), "POSITION accessor is missing")
    accessor = accessors[accessor_index]
    require(accessor.get("type") == "VEC3",
            "POSITION accessor must be VEC3")
    require(accessor.get("componentType") == GLTF_FLOAT,
            "POSITION accessor must be 32-bit float")
    count = int(accessor.get("count", 0))
    require(count > 0, "POSITION accessor is empty")

    views = document.get("bufferViews") or []
    view_index = accessor.get("bufferView")
    require(view_index is not None and 0 <= view_index < len(views),
            "POSITION accessor has no bufferView")
    view = views[view_index]
    data = _buffer_bytes(document, int(view.get("buffer", 0)), path.parent)
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    stride = int(view.get("byteStride") or 12)
    require(stride >= 12, "POSITION bufferView stride is smaller than a VEC3")
    end = start + stride * (count - 1) + 12
    require(0 <= start < end <= len(data),
            "POSITION accessor range falls outside its buffer")

    positions = [
        struct.unpack_from("<3f", data, start + stride * vertex)
        for vertex in range(count)
    ]
    return positions, str(chosen.get("name"))


def build_recipe(
    gltf_path: Path,
    target_id: str,
    catalog: dict[str, Any] | None = None,
    mesh_name: str | None = None,
) -> dict[str, Any]:
    catalog = catalog if catalog is not None else load_catalog()
    require(target_id in catalog,
            f"{target_id} is not one of the {len(catalog)} authorized targets")
    row = catalog[target_id]
    expected = int(row["shape"]["vertex_count"])
    positions, source_mesh = read_positions(gltf_path, mesh_name)
    require(
        len(positions) == expected,
        f"{target_id} holds exactly {expected} vertices and the glTF mesh "
        f"{source_mesh!r} has {len(positions)}. This lane moves vertices "
        "inside a fixed allocation; it cannot add or remove them. In Blender, "
        "edit positions only -- no subdivide, decimate, delete, extrude, or "
        "merge-by-distance.",
    )
    for vertex, xyz in enumerate(positions):
        for axis, value in enumerate(xyz):
            require(
                value == value and abs(value) != float("inf"),
                f"positions[{vertex}][{axis}] is not a finite number",
            )
    return {
        "catalog": {"schema": CATALOG_SCHEMA, "sha256": CATALOG_SHA256},
        "positions": [list(xyz) for xyz in positions],
        "schema": RECIPE_SCHEMA,
        "target_id": target_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gltf", required=True, type=Path)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--mesh", default=None,
                        help="mesh name, when the glTF holds more than one")
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    args = parser.parse_args()
    try:
        recipe = build_recipe(args.gltf, args.target_id,
                              load_catalog(args.catalog), args.mesh)
    except RoundTripError as exc:
        print(f"nfl_stadium_gltf_roundtrip: {exc}", file=sys.stderr)
        return 2
    payload = (json.dumps(recipe, indent=2, sort_keys=True) + "\n").encode("utf-8")
    destination = args.recipe.expanduser()
    require(not destination.is_symlink(),
            f"refusing to write through a symlink: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    print(json.dumps({
        "recipe": str(destination),
        "sha256": _sha256(payload),
        "target_id": args.target_id,
        "vertices": len(recipe["positions"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
