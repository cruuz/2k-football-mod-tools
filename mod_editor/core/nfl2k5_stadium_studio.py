"""Backend catalog for the NFL 2K5 Stadium Studio.

This adapter joins three existing, user-dump-derived products without
overstating their evidence:

* the complete static glTF scene manifest supplies viewer geometry;
* the embedded-texture PNG manifest supplies exact material/texture
  provenance; and
* the bounded stadium target catalog identifies the narrow position writers.

General SCNE serialization is not claimed.  A texture becomes editable only
when the injected delegate can dynamically replay its embedded P8 descriptor,
complete mip/palette allocation, material ownership, compressed resource span,
and single-pack XISO ownership.  Merely placing an edited PNG beside a glTF
never becomes a build action.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
from threading import RLock
from typing import Protocol
from uuid import uuid4

from .errors import ActionNotImplementedError, ValidationError
from .json_stream import (
    file_contains_bytes,
    iter_top_level_array,
    require_regular_file,
)


GLTF_MANIFEST_SCHEMA = "nfl2k5_static_gltf_manifest/v2"
TEXTURE_MANIFEST_SCHEMA = "nfl2k5_scne_embedded_texture_png/v1"
GEOMETRY_CATALOG_SCHEMA = "nfl2k5_stadium_static_target_catalog/v1"
PREVIEW_EXPORT_ONLY = "Preview/Export-only"
EDITABLE = "Editable"
COPY_BLOCK = 1024 * 1024

TEXTURE_FINDINGS = (
    "The scene's material-to-embedded-texture pointer and exact PNG provenance "
    "are mapped, but shader stage, UV set, sampler behavior, and a general "
    "lossless SCNE texture serializer are not proved. This texture can be "
    "previewed and exported; replacing it would not yet modify the XISO."
)

EDITABLE_TEXTURE_FINDINGS = (
    "Editable source-proved fixed-allocation P8 texture. Replace it with an "
    "exact-dimension RGBA8 PNG. Every material/surface linked to this embedded "
    "texture changes together. If lossless SCNE compression exceeds the retail "
    "slot, simplify noisy detail and try again. Geometry, UVs, shaders, and "
    "collision are unchanged."
)

GEOMETRY_FINDINGS = (
    "Only the listed same-count raw FLOAT3 position targets have bounded offline "
    "writers. General edited-glTF import, UV/material changes, collision, LOD, "
    "semantic attachment, and visible runtime ownership remain unproved."
)


@dataclass(frozen=True)
class StadiumGeometryTarget:
    target_id: str
    shape_index: int
    shape_name: str
    vertex_count: int | None
    writer_route: str
    runtime_visibility_proved: bool
    findings_note: str = GEOMETRY_FINDINGS


@dataclass(frozen=True)
class StadiumScene:
    scene_id: str
    outer_index: int
    chunk_index: int
    scene_index: int
    name: str
    gltf_path: Path
    bin_path: Path
    gltf_sha256: str
    bin_sha256: str
    mesh_count: int
    primitive_count: int
    vertex_count: int
    geometry_targets: tuple[StadiumGeometryTarget, ...]


@dataclass(frozen=True)
class StadiumNode:
    node_index: int
    name: str
    mesh_index: int
    source_shape_index: int | None


@dataclass(frozen=True)
class StadiumSurfaceOwner:
    node_index: int
    node_name: str
    mesh_index: int
    primitive_index: int
    source_shape_index: int | None
    source_submesh_index: int | None


@dataclass(frozen=True)
class StadiumTexture:
    texture_id: str
    scene_id: str
    texture_index: int
    width: int
    height: int
    format_name: str
    rgba_sha256: str
    png_sha256: str
    png_path: Path
    mapped_material_names: tuple[str, ...]
    mapped_material_count: int
    access_status: str
    findings_note: str = TEXTURE_FINDINGS


@dataclass(frozen=True)
class StadiumMaterial:
    material_index: int
    name: str
    mapping_status: str
    texture_id: str | None
    owners: tuple[StadiumSurfaceOwner, ...]


@dataclass(frozen=True)
class StadiumSceneDetails:
    scene: StadiumScene
    nodes: tuple[StadiumNode, ...]
    materials: tuple[StadiumMaterial, ...]
    textures: tuple[StadiumTexture, ...]


@dataclass(frozen=True, slots=True)
class _TextureRow:
    texture_index: int
    width: int
    height: int
    format_name: str
    rgba_sha256: str
    png_sha256: str
    png_path: str
    mapped_material_names: str
    mapped_material_count: int


@dataclass(frozen=True, slots=True)
class _MaterialRow:
    material_index: int
    material_name: str
    mapping_status: str
    texture_index: int | None


class StadiumTextureEditDelegate(Protocol):
    """Narrow bridge for a separately reviewed, exact texture provider."""

    def supports(self, texture: StadiumTexture) -> bool: ...

    def current_png(self, texture: StadiumTexture) -> Path: ...

    def replace(self, texture: StadiumTexture, supplied_png: Path) -> object: ...

    def revert(self, texture: StadiumTexture) -> object: ...


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError(f"Stadium index has an invalid {label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"Stadium index has an invalid {label}")
    return value


def _scene_id(outer_index: int, chunk_index: int, scene_index: int) -> str:
    return (
        f"nfl2k5.stadium.o{outer_index:04d}.c{chunk_index:04d}."
        f"scene{scene_index:04d}"
    )


def _texture_id(scene_id: str, texture_index: int) -> str:
    return f"{scene_id}.texture{texture_index:04d}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(COPY_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


# Stadium "people & sideline" asset categories.  Each entry is
# (category id, human label, case-folded substring tokens).  A name maps to the
# FIRST category whose token it contains; order keeps specific roles (ushers,
# camera crew) ahead of the broad ``crowd`` bucket (e.g. ``crowdusher``).  The
# vocabulary is taken from the decoded SCNE name census (cheerleader*, crowd*,
# coach*, cameraman*, crowdusher, chaingang*, sideline_*).  These are texture /
# material / node / marker names; the geometry that owns them is not editable
# here, only the P8 textures the stadium writer already supports.
STADIUM_PEOPLE_CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("cheerleaders", "Cheerleaders", ("cheer",)),
    ("chain_crew", "Chain crew", ("chain",)),
    ("coaches", "Coaches", ("coach",)),
    ("camera_crew", "Camera / media", ("cameraman", "photog")),
    ("officials", "Officials", ("referee", "official")),
    ("ushers", "Ushers / staff", ("usher", "vendor", "ballboy", "ball_boy")),
    ("sideline", "Sideline props", ("sideline",)),
    ("crowd", "Crowd / fans", ("crowd", "spectator")),
)


def stadium_people_category(name: str) -> str | None:
    """Return the people/sideline category id a stadium asset name belongs to."""
    if not isinstance(name, str):
        return None
    folded = name.casefold()
    for category_id, _label, tokens in STADIUM_PEOPLE_CATEGORIES:
        if any(token in folded for token in tokens):
            return category_id
    return None


def stadium_people_category_label(category_id: str) -> str:
    for stored_id, label, _tokens in STADIUM_PEOPLE_CATEGORIES:
        if stored_id == category_id:
            return label
    raise ValidationError(f"Unknown stadium people category: {category_id!r}")


def stadium_people_categories_for_names(*names: str) -> tuple[str, ...]:
    """Sorted, de-duplicated category ids matched across the given names."""
    found: set[str] = set()
    for name in names:
        category = stadium_people_category(name)
        if category is not None:
            found.add(category)
    return tuple(sorted(found))


def classify_stadium_people_textures(
    scene_name: str,
    textures: Iterable[StadiumTexture],
    materials: Iterable[StadiumMaterial],
) -> dict[str, tuple[str, ...]]:
    """Map each people/sideline texture id to the categories it belongs to.

    A texture is matched by its scene name, mapped material names, the name of
    the material that references it, and the names of the nodes that own that
    material.  Textures with no people/sideline match are omitted.  Pure helper:
    it only reads the given dataclasses, so it is unit-testable without a game
    source cache.
    """
    material_names: dict[str, tuple[str, tuple[str, ...]]] = {}
    for material in materials:
        material_names[material.texture_id or ""] = (
            material.name,
            tuple(owner.node_name for owner in material.owners),
        )
    result: dict[str, tuple[str, ...]] = {}
    for texture in textures:
        names: list[str] = [scene_name, *texture.mapped_material_names]
        material_name, node_names = material_names.get(texture.texture_id, ("", ()))
        if material_name:
            names.append(material_name)
        names.extend(node_names)
        categories = stadium_people_categories_for_names(*names)
        if categories:
            result[texture.texture_id] = categories
    return result


def _confined_file(root: Path, relative: str, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValidationError(f"{label} uses an unsafe path")
    resolved_root = root.resolve(strict=True)
    path = (resolved_root / candidate).resolve(strict=True)
    try:
        path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValidationError(f"{label} escapes its asset directory") from exc
    require_regular_file(path, label)
    return path


class Nfl2k5StadiumStudio:
    """Enumerate stadium scenes and resolve clicked surfaces to textures."""

    def __init__(
        self,
        gltf_manifest: Path,
        texture_manifest: Path,
        texture_root: Path,
        *,
        geometry_catalog: Path | None = None,
        edit_delegate: StadiumTextureEditDelegate | None = None,
    ) -> None:
        self.gltf_manifest = gltf_manifest.expanduser()
        self.texture_manifest = texture_manifest.expanduser()
        self.texture_root = texture_root.expanduser()
        self.geometry_catalog = (
            geometry_catalog.expanduser() if geometry_catalog is not None else None
        )
        self.edit_delegate = edit_delegate
        require_regular_file(self.gltf_manifest, "stadium glTF manifest")
        require_regular_file(self.texture_manifest, "stadium texture manifest")
        if not self.texture_root.is_dir() or self.texture_root.is_symlink():
            raise ValidationError(
                f"Stadium texture export directory is missing: {self.texture_root}"
            )
        if not file_contains_bytes(
            self.texture_manifest,
            f'"schema": "{TEXTURE_MANIFEST_SCHEMA}"'.encode("ascii"),
            label="stadium texture manifest",
        ):
            raise ValidationError("The stadium texture manifest has an unsupported format")
        self._geometry = self._load_geometry_targets()
        self._scenes = self._load_scenes()
        self._scene_by_id = {scene.scene_id: scene for scene in self._scenes}
        self._ownership_loaded = False
        self._texture_rows: dict[tuple[int, int, int], list[_TextureRow]] = {}
        self._material_rows: dict[tuple[int, int, int], list[_MaterialRow]] = {}
        self._details: dict[str, StadiumSceneDetails] = {}
        self._lock = RLock()

    @property
    def scene_count(self) -> int:
        return len(self._scenes)

    def list_scenes(
        self, *, search: str = "", offset: int = 0, limit: int | None = None
    ) -> tuple[StadiumScene, ...]:
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValidationError("Stadium list offset must be zero or greater")
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
        ):
            raise ValidationError("Stadium list limit must be one or greater")
        needle = search.casefold().strip()
        rows = self._scenes
        if needle:
            rows = tuple(
                scene for scene in rows
                if needle in scene.scene_id.casefold()
                or needle in scene.name.casefold()
                or needle in str(scene.outer_index)
            )
        return rows[offset:] if limit is None else rows[offset:offset + limit]

    def people_and_sideline_textures(
        self,
    ) -> tuple[tuple[str, str, tuple[StadiumTexture, ...]], ...]:
        """Group editable stadium textures by people / sideline category.

        A texture is filed under every category its scene name, mapped material
        names, owning material name, or owning node names match.  Only textures
        the stadium writer already supports are returned; the owning 3D geometry
        is not editable here.  Categories with no matching texture are omitted.
        """
        groups: dict[str, list[StadiumTexture]] = {
            category_id: []
            for category_id, _label, _tokens in STADIUM_PEOPLE_CATEGORIES
        }
        for scene in self._scenes:
            details = self.scene_details(scene)
            classified = classify_stadium_people_textures(
                scene.name, details.textures, details.materials
            )
            by_id = {texture.texture_id: texture for texture in details.textures}
            for texture_id, categories in classified.items():
                texture = by_id[texture_id]
                for category in categories:
                    groups[category].append(texture)
        return tuple(
            (category_id, label, tuple(textures))
            for category_id, label, _tokens in STADIUM_PEOPLE_CATEGORIES
            if groups[category_id]
        )

    def scene_people_texture_ids(self, scene_id: str) -> tuple[str, ...]:
        """Texture ids in one scene that belong to a people/sideline category."""
        details = self.scene_details(scene_id)
        classified = classify_stadium_people_textures(
            details.scene.name, details.textures, details.materials
        )
        return tuple(classified.keys())

    def get_scene(self, scene_id: str) -> StadiumScene:
        try:
            return self._scene_by_id[scene_id]
        except KeyError as exc:
            raise ValidationError(f"Unknown stadium scene: {scene_id}") from exc

    def scene_details(self, scene_or_id: StadiumScene | str) -> StadiumSceneDetails:
        scene = (
            self.get_scene(scene_or_id) if isinstance(scene_or_id, str) else scene_or_id
        )
        if self.get_scene(scene.scene_id) != scene:
            raise ValidationError("That stadium scene does not match the manifest")
        with self._lock:
            cached = self._details.get(scene.scene_id)
            if cached is not None:
                return cached
            self._ensure_ownership_loaded()
            details = self._build_details(scene)
            self._details[scene.scene_id] = details
            return details

    def texture_for_surface(
        self, scene_id: str, mesh_index: int, primitive_index: int
    ) -> StadiumTexture | None:
        if min(mesh_index, primitive_index) < 0:
            raise ValidationError("Surface indices must be zero or greater")
        details = self.scene_details(scene_id)
        by_id = {texture.texture_id: texture for texture in details.textures}
        for material in details.materials:
            if any(
                owner.mesh_index == mesh_index
                and owner.primitive_index == primitive_index
                for owner in material.owners
            ):
                return by_id.get(material.texture_id) if material.texture_id else None
        raise ValidationError("That surface is not present in this stadium scene")

    def preview_texture(self, texture_id: str) -> Path:
        texture = self._get_texture(texture_id)
        if self._delegate_supports(texture):
            path = self.edit_delegate.current_png(texture)  # type: ignore[union-attr]
            require_regular_file(path, "current stadium texture PNG")
            return path
        require_regular_file(texture.png_path, "stadium texture PNG")
        if _sha256(texture.png_path) != texture.png_sha256:
            raise ValidationError("The stadium texture PNG no longer matches its manifest")
        return texture.png_path

    def export_texture(self, texture_id: str, destination: Path) -> Path:
        source = self.preview_texture(texture_id)
        target = destination.expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(target):
            raise ValidationError(f"A file already exists there: {target}")
        temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid4().hex}.tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            with source.open("rb") as input_stream, \
                    os.fdopen(descriptor, "wb", closefd=True) as output_stream:
                shutil.copyfileobj(input_stream, output_stream, COPY_BLOCK)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as exc:
                raise ValidationError(f"A file appeared at the export destination: {target}") from exc
        finally:
            temporary.unlink(missing_ok=True)
        return target.resolve(strict=True)

    def replace_texture(self, texture_id: str, supplied_png: Path) -> object:
        texture = self._get_texture(texture_id)
        if not self._delegate_supports(texture):
            raise ActionNotImplementedError(TEXTURE_FINDINGS)
        path = supplied_png.expanduser().resolve(strict=True)
        require_regular_file(path, "replacement stadium texture PNG")
        result = self.edit_delegate.replace(texture, path)  # type: ignore[union-attr]
        with self._lock:
            self._details.pop(texture.scene_id, None)
        return result

    def revert_texture(self, texture_id: str) -> object:
        texture = self._get_texture(texture_id)
        if not self._delegate_supports(texture):
            raise ActionNotImplementedError(TEXTURE_FINDINGS)
        result = self.edit_delegate.revert(texture)  # type: ignore[union-attr]
        with self._lock:
            self._details.pop(texture.scene_id, None)
        return result

    def runtime_manifest(self) -> dict[str, object]:
        """Return metadata-only rows suitable for a private UI model."""

        return {
            "schema": "2k5_mod_studio_stadium_catalog/v1",
            "findings": {
                "geometry": GEOMETRY_FINDINGS,
                "textures": TEXTURE_FINDINGS,
            },
            "scene_count": len(self._scenes),
            "scenes": [
                {
                    "scene_id": scene.scene_id,
                    "outer_index": scene.outer_index,
                    "chunk_index": scene.chunk_index,
                    "scene_index": scene.scene_index,
                    "mesh_count": scene.mesh_count,
                    "primitive_count": scene.primitive_count,
                    "vertex_count": scene.vertex_count,
                    "gltf_path": str(scene.gltf_path),
                    "geometry_target_count": len(scene.geometry_targets),
                    "texture_status": PREVIEW_EXPORT_ONLY,
                }
                for scene in self._scenes
            ],
        }

    def _load_scenes(self) -> tuple[StadiumScene, ...]:
        try:
            manifest = json.loads(self.gltf_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Could not read the stadium glTF manifest: {exc}") from exc
        if not isinstance(manifest, dict) or manifest.get("schema") != GLTF_MANIFEST_SCHEMA:
            raise ValidationError("The stadium glTF manifest has an unsupported format")
        exports = manifest.get("exports")
        if not isinstance(exports, list):
            raise ValidationError("The stadium glTF manifest has no export list")
        root = self.gltf_manifest.parent
        scenes: list[StadiumScene] = []
        seen: set[str] = set()
        for raw in exports:
            if not isinstance(raw, dict) or raw.get("scene_name") != "stadium" \
                    or raw.get("status") != "exported":
                continue
            outer = _integer(raw.get("outer_index"), "outer index")
            chunk = _integer(raw.get("chunk_index"), "chunk index")
            scene_index = _integer(raw.get("scene_index"), "scene index")
            scene_id = _scene_id(outer, chunk, scene_index)
            if scene_id in seen:
                raise ValidationError("The stadium glTF manifest contains a duplicate scene")
            seen.add(scene_id)
            gltf = _confined_file(root, _text(raw.get("gltf"), "glTF path"), "stadium glTF")
            binary = _confined_file(root, _text(raw.get("bin"), "binary path"), "stadium binary")
            key = (outer, chunk, scene_index)
            scenes.append(
                StadiumScene(
                    scene_id=scene_id,
                    outer_index=outer,
                    chunk_index=chunk,
                    scene_index=scene_index,
                    name="stadium",
                    gltf_path=gltf,
                    bin_path=binary,
                    gltf_sha256=_text(raw.get("gltf_sha256"), "glTF hash"),
                    bin_sha256=_text(raw.get("bin_sha256"), "binary hash"),
                    mesh_count=_integer(raw.get("mesh_count"), "mesh count"),
                    primitive_count=_integer(raw.get("primitive_count"), "primitive count"),
                    vertex_count=_integer(raw.get("vertex_count"), "vertex count"),
                    geometry_targets=self._geometry.get(key, ()),
                )
            )
        scenes.sort(key=lambda row: (row.outer_index, row.chunk_index, row.scene_index))
        return tuple(scenes)

    def _load_geometry_targets(
        self,
    ) -> dict[tuple[int, int, int], tuple[StadiumGeometryTarget, ...]]:
        if self.geometry_catalog is None:
            return {}
        require_regular_file(self.geometry_catalog, "bounded stadium geometry catalog")
        try:
            data = json.loads(self.geometry_catalog.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Could not read the stadium geometry catalog: {exc}") from exc
        if not isinstance(data, dict) or data.get("schema") != GEOMETRY_CATALOG_SCHEMA:
            raise ValidationError("The stadium geometry catalog has an unsupported format")
        grouped: dict[tuple[int, int, int], list[StadiumGeometryTarget]] = {}
        for raw in data.get("targets", []):
            if not isinstance(raw, dict):
                raise ValidationError("Stadium geometry catalog has an invalid target row")
            source = raw.get("source_identity")
            shape = raw.get("shape")
            eligibility = raw.get("eligibility")
            if not isinstance(source, dict) or not isinstance(shape, dict) \
                    or not isinstance(eligibility, dict):
                raise ValidationError("Stadium geometry target is incomplete")
            key = (
                _integer(source.get("outer_index"), "geometry outer index"),
                _integer(source.get("chunk_index"), "geometry chunk index"),
                _integer(source.get("scene_index"), "geometry scene index"),
            )
            grouped.setdefault(key, []).append(
                StadiumGeometryTarget(
                    target_id=_text(raw.get("target_id"), "geometry target ID"),
                    shape_index=_integer(shape.get("index"), "geometry shape index"),
                    shape_name=_text(shape.get("name"), "geometry shape name"),
                    vertex_count=_integer(shape.get("vertex_count"), "geometry vertex count", minimum=1),
                    writer_route="catalog-same-count-position-v2",
                    runtime_visibility_proved=bool(
                        eligibility.get("runtime_visibility_proved") is True
                    ),
                )
            )
        reference = data.get("implemented_reference")
        contract = data.get("resource_contract")
        if isinstance(reference, dict) and isinstance(contract, dict):
            resource = contract.get("resource")
            outer_entry = contract.get("outer_entry")
            targets = data.get("targets")
            first_source = (
                targets[0].get("source_identity")
                if isinstance(targets, list) and targets
                and isinstance(targets[0], dict)
                else None
            )
            if isinstance(resource, dict) and isinstance(outer_entry, dict) \
                    and isinstance(first_source, dict):
                key = (
                    _integer(outer_entry.get("index"), "reference outer index"),
                    _integer(resource.get("chunk_index"), "reference chunk index"),
                    _integer(first_source.get("scene_index"), "reference scene index"),
                )
                grouped.setdefault(key, []).append(
                    StadiumGeometryTarget(
                        target_id=_text(reference.get("target_id"), "reference target ID"),
                        shape_index=_integer(reference.get("shape_index"), "reference shape index"),
                        shape_name=_text(reference.get("shape_name"), "reference shape name"),
                        vertex_count=None,
                        writer_route="group36-same-footprint-v1",
                        runtime_visibility_proved=False,
                    )
                )
        return {
            key: tuple(sorted(rows, key=lambda row: row.shape_index))
            for key, rows in grouped.items()
        }

    def _ensure_ownership_loaded(self) -> None:
        if self._ownership_loaded:
            return
        scene_keys = {
            (scene.outer_index, scene.chunk_index, scene.scene_index)
            for scene in self._scenes
        }
        texture_rows: dict[tuple[int, int, int], list[_TextureRow]] = {}
        for raw in iter_top_level_array(
            self.texture_manifest, "occurrences", label="stadium texture manifest"
        ):
            if not isinstance(raw, dict) or raw.get("scene_name") != "stadium":
                continue
            key = self._ownership_key(raw)
            if key in scene_keys:
                mapped_names = raw.get("mapped_material_names")
                if not isinstance(mapped_names, str):
                    raise ValidationError(
                        "Stadium texture manifest has invalid mapped material names"
                    )
                texture_rows.setdefault(key, []).append(
                    _TextureRow(
                        texture_index=_integer(
                            raw.get("texture_index"), "embedded texture index"
                        ),
                        width=_integer(raw.get("width"), "texture width", minimum=1),
                        height=_integer(raw.get("height"), "texture height", minimum=1),
                        format_name=_text(raw.get("format_name"), "texture format"),
                        rgba_sha256=_text(raw.get("rgba_sha256"), "texture RGBA hash"),
                        png_sha256=_text(raw.get("png_sha256"), "texture PNG hash"),
                        png_path=_text(raw.get("png_path"), "texture PNG path"),
                        mapped_material_names=mapped_names,
                        mapped_material_count=_integer(
                            raw.get("mapped_material_count"), "mapped material count"
                        ),
                    )
                )
        material_rows: dict[tuple[int, int, int], list[_MaterialRow]] = {}
        for raw in iter_top_level_array(
            self.texture_manifest, "materials", label="stadium texture manifest"
        ):
            if not isinstance(raw, dict) or raw.get("scene_name") != "stadium":
                continue
            key = self._ownership_key(raw)
            if key in scene_keys:
                raw_texture_index = raw.get("texture_index")
                material_rows.setdefault(key, []).append(
                    _MaterialRow(
                        material_index=_integer(
                            raw.get("material_index"), "material index"
                        ),
                        material_name=_text(raw.get("material_name"), "material name"),
                        mapping_status=_text(
                            raw.get("mapping_status"), "material mapping status"
                        ),
                        texture_index=(
                            _integer(raw_texture_index, "material texture index")
                            if raw_texture_index is not None else None
                        ),
                    )
                )
        self._texture_rows = texture_rows
        self._material_rows = material_rows
        self._ownership_loaded = True

    @staticmethod
    def _ownership_key(row: dict[str, object]) -> tuple[int, int, int]:
        return (
            _integer(row.get("outer_index"), "texture outer index"),
            _integer(row.get("chunk_index"), "texture chunk index"),
            _integer(row.get("scene_index"), "texture scene index"),
        )

    def _build_details(self, scene: StadiumScene) -> StadiumSceneDetails:
        if _sha256(scene.gltf_path) != scene.gltf_sha256 \
                or _sha256(scene.bin_path) != scene.bin_sha256:
            raise ValidationError("The stadium glTF export no longer matches its manifest")
        try:
            gltf = json.loads(scene.gltf_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Could not read that stadium scene: {exc}") from exc
        if not isinstance(gltf, dict):
            raise ValidationError("That stadium glTF is not a JSON object")
        raw_nodes = gltf.get("nodes")
        raw_meshes = gltf.get("meshes")
        buffers = gltf.get("buffers")
        if not isinstance(raw_nodes, list) or not isinstance(raw_meshes, list) \
                or not isinstance(buffers, list) or len(buffers) != 1 \
                or not isinstance(buffers[0], dict) \
                or buffers[0].get("uri") != scene.bin_path.name:
            raise ValidationError("That stadium glTF has an unsupported scene layout")
        if len(raw_meshes) != scene.mesh_count:
            raise ValidationError("That stadium glTF mesh count changed")

        nodes: list[StadiumNode] = []
        mesh_nodes: dict[int, list[StadiumNode]] = {}
        for node_index, raw in enumerate(raw_nodes):
            if not isinstance(raw, dict):
                raise ValidationError("That stadium glTF has an invalid node")
            mesh_index = _integer(raw.get("mesh"), "node mesh index")
            if mesh_index >= len(raw_meshes):
                raise ValidationError("That stadium glTF node names an unknown mesh")
            extras = raw.get("extras", {})
            shape_index = None
            if isinstance(extras, dict) and extras.get("source_shape_index") is not None:
                shape_index = _integer(extras.get("source_shape_index"), "source shape index")
            node = StadiumNode(
                node_index=node_index,
                name=_text(raw.get("name"), "node name"),
                mesh_index=mesh_index,
                source_shape_index=shape_index,
            )
            nodes.append(node)
            mesh_nodes.setdefault(mesh_index, []).append(node)

        owners: dict[int, list[StadiumSurfaceOwner]] = {}
        primitive_total = 0
        for mesh_index, raw in enumerate(raw_meshes):
            if not isinstance(raw, dict) or not isinstance(raw.get("primitives"), list):
                raise ValidationError("That stadium glTF has an invalid mesh")
            for primitive_index, primitive in enumerate(raw["primitives"]):
                primitive_total += 1
                if not isinstance(primitive, dict) or not isinstance(primitive.get("extras"), dict):
                    raise ValidationError("That stadium glTF has an invalid primitive")
                extras = primitive["extras"]
                material_index = _integer(
                    extras.get("source_material_index"), "source material index"
                )
                submesh = extras.get("source_submesh_index")
                submesh_index = (
                    _integer(submesh, "source submesh index") if submesh is not None else None
                )
                for node in mesh_nodes.get(mesh_index, []):
                    owners.setdefault(material_index, []).append(
                        StadiumSurfaceOwner(
                            node_index=node.node_index,
                            node_name=node.name,
                            mesh_index=mesh_index,
                            primitive_index=primitive_index,
                            source_shape_index=node.source_shape_index,
                            source_submesh_index=submesh_index,
                        )
                    )
        if primitive_total != scene.primitive_count:
            raise ValidationError("That stadium glTF primitive count changed")

        key = (scene.outer_index, scene.chunk_index, scene.scene_index)
        textures: list[StadiumTexture] = []
        texture_by_index: dict[int, StadiumTexture] = {}
        for raw in self._texture_rows.get(key, []):
            index = raw.texture_index
            if index in texture_by_index:
                raise ValidationError("Stadium texture manifest has a duplicate occurrence")
            rgba = raw.rgba_sha256
            png_sha = raw.png_sha256
            if len(rgba) != 64 or len(png_sha) != 64:
                raise ValidationError("Stadium texture manifest has an invalid hash")
            relative = Path("by_rgba_sha256") / rgba[:2] / f"{rgba}.png"
            png_path = _confined_file(
                self.texture_root, relative.as_posix(), "stadium texture PNG"
            )
            manifest_png = raw.png_path
            if not Path(manifest_png).as_posix().endswith(relative.as_posix()):
                raise ValidationError("Stadium texture manifest has a noncanonical PNG path")
            names = raw.mapped_material_names
            parsed_names = tuple(name for name in names.split("|") if name)
            if len(parsed_names) != raw.mapped_material_count:
                raise ValidationError(
                    "Stadium texture manifest has an inconsistent material count"
                )
            base = StadiumTexture(
                texture_id=_texture_id(scene.scene_id, index),
                scene_id=scene.scene_id,
                texture_index=index,
                width=raw.width,
                height=raw.height,
                format_name=raw.format_name,
                rgba_sha256=rgba,
                png_sha256=png_sha,
                png_path=png_path,
                mapped_material_names=parsed_names,
                mapped_material_count=raw.mapped_material_count,
                access_status=PREVIEW_EXPORT_ONLY,
            )
            texture = (
                StadiumTexture(**{
                    **base.__dict__,
                    "access_status": EDITABLE,
                    "findings_note": EDITABLE_TEXTURE_FINDINGS,
                })
                if self._delegate_supports(base) else base
            )
            texture_by_index[index] = texture
            textures.append(texture)

        materials: list[StadiumMaterial] = []
        material_indices: set[int] = set()
        for raw in self._material_rows.get(key, []):
            index = raw.material_index
            if index in material_indices:
                raise ValidationError("Stadium texture manifest has a duplicate material")
            material_indices.add(index)
            texture_index = raw.texture_index
            linked = None
            if texture_index is not None:
                linked = texture_by_index.get(texture_index)
                if linked is None:
                    raise ValidationError("Stadium material names a missing texture occurrence")
            materials.append(
                StadiumMaterial(
                    material_index=index,
                    name=raw.material_name,
                    mapping_status=raw.mapping_status,
                    texture_id=linked.texture_id if linked else None,
                    owners=tuple(owners.pop(index, ())),
                )
            )
        # A glTF primitive without a material-manifest row remains visible and
        # explicitly unresolved instead of disappearing from the UI.
        for index, unresolved in sorted(owners.items()):
            materials.append(
                StadiumMaterial(
                    material_index=index,
                    name=f"material_{index}",
                    mapping_status="missing_manifest_row",
                    texture_id=None,
                    owners=tuple(unresolved),
                )
            )
        materials.sort(key=lambda row: row.material_index)
        textures.sort(key=lambda row: row.texture_index)
        return StadiumSceneDetails(
            scene=scene,
            nodes=tuple(nodes),
            materials=tuple(materials),
            textures=tuple(textures),
        )

    def _get_texture(self, texture_id: str) -> StadiumTexture:
        for scene in self._scenes:
            if texture_id.startswith(scene.scene_id + ".texture"):
                for texture in self.scene_details(scene).textures:
                    if texture.texture_id == texture_id:
                        return texture
        raise ValidationError(f"Unknown stadium texture: {texture_id}")

    def _delegate_supports(self, texture: StadiumTexture) -> bool:
        return bool(self.edit_delegate and self.edit_delegate.supports(texture))


__all__ = [
    "EDITABLE",
    "GEOMETRY_FINDINGS",
    "Nfl2k5StadiumStudio",
    "PREVIEW_EXPORT_ONLY",
    "StadiumGeometryTarget",
    "StadiumMaterial",
    "StadiumNode",
    "StadiumScene",
    "StadiumSceneDetails",
    "StadiumSurfaceOwner",
    "StadiumTexture",
    "StadiumTextureEditDelegate",
    "TEXTURE_FINDINGS",
]
