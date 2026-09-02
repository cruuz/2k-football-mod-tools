"""Bounded private glTF round trips for APF's stock helmet and player body.

The paired importer can write same-count POSITION edits only.  Every other
vertex lane and SCNE structure remains outside the authoring boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable

from .backend import ensure_tools_importable


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_scene  # type: ignore  # noqa: E402


Progress = Callable[[str, int, int], None]
MODEL_EXPORT_BOUNDARY = (
    "Static POSITION/topology export with a paired same-topology POSITION-only "
    "importer. The importer requires this source-bound manifest and exact source "
    "triangle lists. Materials, textures, normals, packed tangent/UV data, skin "
    "weights/indices, helmet/head attachment, animation, collision, and topology "
    "changes cannot be authored."
)


class ModelExportError(ValueError):
    """A model export cannot be completed inside the proved boundary."""


@dataclass(frozen=True)
class ModelExportTarget:
    key: str
    title: str
    outer_index: int
    inner_index: int
    root_name: str
    expected_mesh_count: int
    description: str


@dataclass(frozen=True)
class ModelExportReceipt:
    target: ModelExportTarget
    gltf: Path
    binary: Path
    manifest: Path
    mesh_count: int
    vertex_count: int
    triangle_count: int
    model_import_available: bool = True


TARGETS = (
    ModelExportTarget(
        key="helmet",
        title="Stock helmet shell + equipment",
        outer_index=1310,
        inner_index=128,
        root_name="helmet_00",
        expected_mesh_count=33,
        description=(
            "Exports the stock shell, visor, 30 facemask groups, and low-detail shell "
            "as 33 meshes. Same-topology POSITION edits can be imported; attachment, "
            "materials, skin data, and topology remain preserved and uneditable."
        ),
    ),
    ModelExportTarget(
        key="player",
        title="Stock player body",
        outer_index=1310,
        inner_index=273,
        root_name="player",
        expected_mesh_count=1,
        description=(
            "Exports the stock high-detail player body's position/topology mesh. "
            "Same-topology POSITION edits can be imported while existing skin data is "
            "preserved; rig, material, UV, animation, and topology editing stay blocked."
        ),
    ),
)


def target(key: str) -> ModelExportTarget:
    normalized = str(key).strip().casefold()
    for row in TARGETS:
        if row.key == normalized:
            return row
    raise ModelExportError(f"unknown model export: {key!r}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_new(source: Path, destination: Path) -> None:
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    try:
        descriptor = os.open(destination, flags, 0o600)
    except OSError as exc:
        raise ModelExportError(f"refusing to overwrite export: {destination}: {exc}") from exc
    try:
        with source.open("rb") as reader, os.fdopen(descriptor, "wb", closefd=False) as writer:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
            writer.flush()
            os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        descriptor = -1
        destination.unlink(missing_ok=True)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_system(index_0a: Path, selected: ModelExportTarget) -> bytes:
    try:
        archive = apf_outer.parse_archive(index_0a)
        entry = archive.entries[selected.outer_index]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            item = record.files[selected.inner_index]
            if item.type_name != "SCNE" or item.name != selected.root_name:
                raise ModelExportError(
                    f"the expected {selected.root_name}/SCNE record changed identity"
                )
            if not item.parts:
                raise ModelExportError("the selected SCNE has no system part")
            part = item.parts[0]
            block = apf_inner.decode_block(reader, record, part.block_index, 64 * 1024 * 1024)
            end = part.offset + part.length
            if part.offset < 0 or end > len(block):
                raise ModelExportError("the selected SCNE exceeds its decoded block")
            return block[part.offset:end]
    except (IndexError, OSError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        raise ModelExportError(f"could not read the selected model SCNE: {exc}") from exc


def export_model(
    index_0a: Path,
    key: str,
    destination: Path,
    progress: Progress | None = None,
) -> ModelExportReceipt:
    selected = target(key)
    report = progress or (lambda _stage, _completed, _total: None)
    destination = Path(destination)
    if destination.suffix.casefold() != ".gltf":
        raise ModelExportError("model exports require a new .gltf filename")
    binary = destination.with_suffix(".bin")
    manifest = destination.with_name(f"{destination.name}.apf-model.json")
    if not destination.parent.is_dir():
        raise ModelExportError(f"export directory does not exist: {destination.parent}")
    for path in (destination, binary, manifest):
        if path.exists() or path.is_symlink():
            raise ModelExportError(f"refusing to overwrite export: {path}")

    report(f"Reading {selected.title} read-only", 0, 3)
    system = _read_system(Path(index_0a), selected)
    try:
        scene = apf_scene.parse_scene_system_part(
            system,
            outer_index=selected.outer_index,
            inner_index=selected.inner_index,
            capture_geometry=True,
        )
    except (apf_scene.SceneError, ValueError) as exc:
        raise ModelExportError(f"the selected model could not be decoded: {exc}") from exc
    if scene.get("root_name") != selected.root_name:
        raise ModelExportError("the decoded model root changed identity")

    staging = Path(tempfile.mkdtemp(prefix=".apf-model-", dir=destination.parent))
    published: list[Path] = []
    try:
        staged_gltf = staging / destination.name
        staged_binary = staging / binary.name
        report(f"Building private {selected.title} glTF", 1, 3)
        export = apf_scene.write_gltf_collection(
            staged_gltf,
            staged_binary,
            scene,
            selected.outer_index,
            selected.inner_index,
        )
        if export.get("status") != "exported":
            raise ModelExportError("the static exporter withheld this model")
        if int(export.get("mesh_count", -1)) != selected.expected_mesh_count:
            raise ModelExportError("the model mesh inventory changed")
        document = {
            "schema": "apf2k8_private_static_model_export/v2",
            "target": {
                "key": selected.key,
                "title": selected.title,
                "outer_index": selected.outer_index,
                "inner_index": selected.inner_index,
                "root_name": selected.root_name,
            },
            "source_system_sha256": hashlib.sha256(system).hexdigest(),
            "gltf": {"name": destination.name, "sha256": _sha256(staged_gltf)},
            "binary": {"name": binary.name, "sha256": _sha256(staged_binary)},
            "export": export,
            "claim_boundary": MODEL_EXPORT_BOUNDARY,
            "model_import_available": True,
            "import_contract": {
                "operation": "same_topology_position_only",
                "source_system_sha256_required": True,
                "expanded_triangle_list_must_match": True,
                "vertex_count_must_match": True,
                "position_storage": "snorm16_xyz_preserve_w",
                "unsupported_fields_fail_closed": [
                    "materials",
                    "normal",
                    "tangent_packed_uv",
                    "blend_indices",
                    "blend_weights",
                    "skin_attachments",
                    "animation",
                    "collision",
                    "topology",
                ],
            },
            "retail_data_policy": (
                "Private derivative of the user's own game; do not redistribute."
            ),
        }
        staged_manifest = staging / manifest.name
        staged_manifest.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        # Publish the glTF last: a visible .gltf therefore never points to a
        # binary that failed to arrive.  A failure removes only files reserved
        # by this call.
        for staged, final in (
            (staged_binary, binary),
            (staged_manifest, manifest),
            (staged_gltf, destination),
        ):
            _copy_new(staged, final)
            published.append(final)
        report(f"{selected.title} export ready", 3, 3)
        return ModelExportReceipt(
            target=selected,
            gltf=destination,
            binary=binary,
            manifest=manifest,
            mesh_count=int(export["mesh_count"]),
            vertex_count=int(export["vertex_count"]),
            triangle_count=int(export["triangle_count"]),
        )
    except Exception:
        for path in reversed(published):
            path.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


__all__ = [
    "MODEL_EXPORT_BOUNDARY",
    "ModelExportError",
    "ModelExportReceipt",
    "ModelExportTarget",
    "TARGETS",
    "export_model",
    "target",
]
