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

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from threading import RLock
from typing import Protocol

from . import platform_compat
from .errors import ActionNotImplementedError, ValidationError
from .nfl2k5_models import (
    GLTF_MATERIAL_INDEX_KEY,
    GLTF_TEXTURE_ID_KEY,
    scene_contract_id,
    texture_contract_id,
)
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

#: glTF's unit is the metre; NFL 2K5 authors stadium geometry in centimetres.
#: Measured on real exports, a stadium spans over 23,000 authored units, which
#: an unscaled file declares as 23 km -- past Blender's default 1 km view
#: distance, so the model appears to vanish.  Exported models carry one root
#: node scaled by this instead of having their vertices rewritten, so the buffer
#: stays byte-identical to what the game shipped.
GLTF_UNIT_SCALE = 0.01

#: glTF extras keys that carry the game-side identity of an export.  The
#: texture write-back (:meth:`Nfl2k5StadiumStudio.replace_textures_from_gltf`)
#: maps Blender-edited image slots back to stadium texture slots through them.
#: The Models page export (``nfl2k5_models.export_model``) writes the same
#: contract, so the keys and the id format live there (imported above) and are
#: shared: ``GLTF_TEXTURE_ID_KEY``, ``GLTF_MATERIAL_INDEX_KEY``,
#: ``scene_contract_id``, ``texture_contract_id``.

#: Flat preview factors for stadium materials, matching the bounded single-shape
#: exporter.  The game's real shader parameters are not proved, so the preview
#: stays a neutral matte surface with the game image bound to it.
GLTF_PREVIEW_BASE_COLOR = [0.8, 0.8, 0.8, 1.0]

#: glTF sampler wrap mode REPEAT -- a preview default, recorded as such,
#: because the game's sampler state is not proved.
GLTF_WRAP_REPEAT = 10497

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
    "The proved full scene accepts edited glTF vertex positions when every mesh "
    "keeps its exact vertex count and equivalent faces. The importer writes only "
    "catalogued FLOAT3 position lanes and preserves game UV, material, collision, "
    "LOD, selector, and other stream bytes. Adding/removing topology, changing "
    "UV/material data, semantic attachment, and visible runtime ownership remain "
    "unproved."
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


@dataclass(frozen=True)
class StadiumGltfTextureSlot:
    """One image slot of a Blender-edited stadium glTF, mapped toward the game.

    ``payload`` holds exactly the image bytes the edited file carries;
    ``texture_id`` is the canonical stadium texture id when the file still has
    the export's extras, else ``None`` (the caller falls back to the material
    name).
    """

    material_index: int
    material_name: str
    texture_id: str | None
    image_index: int
    image_name: str
    payload: bytes


@dataclass(frozen=True)
class StadiumGltfTextureWriteBack:
    """One stadium texture slot successfully fed to the bounded P8 writer."""

    texture_id: str
    scene_id: str
    texture_index: int
    supplied_png_sha256: str
    write_result: object


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

    def supports_geometry(self, scene: StadiumScene) -> bool: ...

    def replace_geometry(self, scene: StadiumScene, compiled: object) -> object: ...


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError(f"Stadium index has an invalid {label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"Stadium index has an invalid {label}")
    return value


def _scene_id(outer_index: int, chunk_index: int, scene_index: int) -> str:
    return scene_contract_id("stadium", outer_index, chunk_index, scene_index)


def _texture_id(scene_id: str, texture_index: int) -> str:
    return texture_contract_id(scene_id, texture_index)


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


def _gltf_data_uri(uri: str, label: str) -> bytes:
    header, separator, encoded = uri.partition(",")
    if not separator or not header.endswith(";base64"):
        raise ValidationError(f"The edited stadium glTF {label} is not a base64 data URI")
    try:
        return base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValidationError(
            f"The edited stadium glTF {label} carries corrupt data URI bytes"
        ) from exc


def _gltf_relative_file(root: Path, uri: str, label: str) -> Path:
    candidate = Path(uri)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValidationError(f"The edited stadium glTF {label} uses an unsafe path")
    path = (root / candidate).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError(
            f"The edited stadium glTF {label} escapes its directory"
        ) from exc
    require_regular_file(path, label)
    return path


def _gltf_reference(value: object, limit: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < limit:
        raise ValidationError(f"The edited stadium glTF {label} names an unknown entry")
    return value


def _gltf_buffers(document: dict[str, object], root: Path) -> tuple[bytes, ...]:
    buffers = document.get("buffers")
    if not isinstance(buffers, list):
        return ()
    resolved: list[bytes] = []
    for index, buffer in enumerate(buffers):
        label = f"buffer {index}"
        if not isinstance(buffer, dict):
            raise ValidationError(f"The edited stadium glTF {label} is not an object")
        uri = buffer.get("uri")
        if isinstance(uri, str) and uri.startswith("data:"):
            resolved.append(_gltf_data_uri(uri, label))
        elif isinstance(uri, str) and uri:
            resolved.append(_gltf_relative_file(root, uri, label).read_bytes())
        else:
            raise ValidationError(
                f"The edited stadium glTF {label} has no readable URI; "
                "GLB containers are not supported"
            )
    return tuple(resolved)


def stadium_gltf_texture_slots(
    source_gltf: Path,
) -> tuple[StadiumGltfTextureSlot, ...]:
    """Map a Blender-edited stadium glTF's image slots back toward the game.

    Reads the ``materials`` -> ``textures`` -> ``images`` chain of the edited
    file and returns one slot per material that carries a ``baseColorTexture``,
    with the exact image bytes Blender wrote (bufferView slice, external file,
    or data URI) and the canonical ``nfl2k5_texture_id`` when the file still
    carries the export's extras.  Pure reader: it never writes anything and
    does not need the game source, so a Blender-side script can audit what
    would be written before handing the file to
    :meth:`Nfl2k5StadiumStudio.replace_textures_from_gltf`.
    """

    require_regular_file(source_gltf, "edited stadium glTF")
    try:
        document = json.loads(source_gltf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Could not read that edited stadium glTF: {exc}") from exc
    if not isinstance(document, dict):
        raise ValidationError("That edited stadium glTF is not a JSON object")
    root = source_gltf.parent.resolve(strict=True)
    buffers = _gltf_buffers(document, root)
    raw_views = document.get("bufferViews")
    buffer_views = raw_views if isinstance(raw_views, list) else []
    raw_images = document.get("images")
    images = raw_images if isinstance(raw_images, list) else []
    raw_textures = document.get("textures")
    textures = raw_textures if isinstance(raw_textures, list) else []
    raw_materials = document.get("materials")
    materials = raw_materials if isinstance(raw_materials, list) else []

    slots: list[StadiumGltfTextureSlot] = []
    for material_index, material in enumerate(materials):
        label = f"material {material_index}"
        if not isinstance(material, dict):
            raise ValidationError(f"The edited stadium glTF {label} is not an object")
        pbr = material.get("pbrMetallicRoughness")
        binding = pbr.get("baseColorTexture") if isinstance(pbr, dict) else None
        if not isinstance(binding, dict):
            continue
        texture_index = _gltf_reference(
            binding.get("index"), len(textures), f"{label} baseColorTexture"
        )
        texture_row = textures[texture_index]
        if not isinstance(texture_row, dict):
            raise ValidationError(f"The edited stadium glTF texture {texture_index} is not an object")
        image_index = _gltf_reference(
            texture_row.get("source"), len(images), f"texture {texture_index} source"
        )
        image_row = images[image_index]
        if not isinstance(image_row, dict):
            raise ValidationError(f"The edited stadium glTF image {image_index} is not an object")
        mime = image_row.get("mimeType")
        if mime is not None and mime != "image/png":
            raise ValidationError(
                f"The edited stadium glTF image {image_index} must stay a PNG; "
                "the bounded P8 writer admits only exact-dimension RGBA8 PNGs"
            )
        buffer_view_ref = image_row.get("bufferView")
        uri = image_row.get("uri")
        image_label = f"image {image_index}"
        if not isinstance(buffer_view_ref, bool) and isinstance(buffer_view_ref, int):
            view_index = _gltf_reference(buffer_view_ref, len(buffer_views), image_label)
            view = buffer_views[view_index]
            if not isinstance(view, dict):
                raise ValidationError(
                    f"The edited stadium glTF bufferView {view_index} is not an object"
                )
            buffer_index = _gltf_reference(
                view.get("buffer", 0), len(buffers), f"bufferView {view_index} buffer"
            )
            offset = view.get("byteOffset", 0)
            length = view.get("byteLength")
            if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0 \
                    or isinstance(length, bool) or not isinstance(length, int) or length < 0 \
                    or offset + length > len(buffers[buffer_index]):
                raise ValidationError(
                    f"The edited stadium glTF bufferView {view_index} is out of bounds"
                )
            payload = buffers[buffer_index][offset:offset + length]
        elif isinstance(uri, str) and uri.startswith("data:"):
            payload = _gltf_data_uri(uri, image_label)
        elif isinstance(uri, str) and uri:
            payload = _gltf_relative_file(root, uri, image_label).read_bytes()
        else:
            raise ValidationError(
                f"The edited stadium glTF {image_label} has no readable bytes"
            )
        texture_id: str | None = None
        for carrier in (material, texture_row, image_row):
            extras = carrier.get("extras")
            if isinstance(extras, dict) \
                    and isinstance(extras.get(GLTF_TEXTURE_ID_KEY), str):
                texture_id = extras[GLTF_TEXTURE_ID_KEY]
                break
        raw_name = material.get("name")
        raw_image_name = image_row.get("name")
        slots.append(
            StadiumGltfTextureSlot(
                material_index=material_index,
                material_name=(
                    raw_name if isinstance(raw_name, str) else f"material_{material_index}"
                ),
                texture_id=texture_id,
                image_index=image_index,
                image_name=(
                    raw_image_name
                    if isinstance(raw_image_name, str)
                    else f"image_{image_index}"
                ),
                payload=payload,
            )
        )
    return tuple(slots)


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
        temporary = platform_compat.temporary_sibling(target)
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

    def export_scene_gltf(
        self, scene_or_id: "StadiumScene | str", destination: Path
    ) -> tuple[Path, Path]:
        """Save the stadium model the viewport is already showing.

        The Stadiums page could render a scene but offered no way to get the
        file out, so a modder could look at a stadium and still not open it in
        Blender -- which is exactly what was reported.  The model is a glTF that
        already exists, so this re-verifies it against the manifest and writes a
        copy rather than re-deriving any geometry.

        Two things change on the way out.  NFL 2K5 authors stadium geometry in
        centimetres and glTF's unit is the metre, so an untouched copy opens
        about a hundred times too large: a real stadium here measures over
        23,000 units across, which Blender reads as 23 km and clips away at its
        default 1 km view distance.  The exported file therefore carries a
        single root node scaled by :data:`GLTF_UNIT_SCALE`, with every former
        root parented to it.  The buffer is copied byte for byte and no vertex
        is re-encoded, so the geometry still means exactly what the game says it
        means -- only the file's declared units change.

        Second, the scene's game surfaces get their textures.  Every material
        the texture manifest links to an embedded stadium texture gains the
        decoded image as a glTF ``image``/``texture`` and a
        ``pbrMetallicRoughness.baseColorTexture`` binding, so Blender's
        material preview shows the game surface instead of flat gray.  The
        image bytes are appended after the untouched geometry bytes -- never a
        second decode -- and each image carries the canonical
        ``nfl2k5_texture_id`` that :meth:`replace_textures_from_gltf` maps back
        to the game slot.

        Returns the written ``(gltf, bin)`` pair.  Both land or neither does.
        """

        scene = (
            self.get_scene(scene_or_id)
            if isinstance(scene_or_id, str)
            else scene_or_id
        )
        if self.get_scene(scene.scene_id) != scene:
            raise ValidationError("That stadium scene does not match the manifest")
        if _sha256(scene.gltf_path) != scene.gltf_sha256 \
                or _sha256(scene.bin_path) != scene.bin_sha256:
            raise ValidationError(
                "The stadium glTF export no longer matches its manifest"
            )

        try:
            document = json.loads(scene.gltf_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Could not read that stadium scene: {exc}") from exc
        if not isinstance(document, dict):
            raise ValidationError("That stadium glTF is not a JSON object")

        nodes = document.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise ValidationError("That stadium glTF has no nodes to export")

        # ``scenes``/``scene`` are optional in glTF 2.0 and the corpus here is
        # not uniform about them, so both shapes are handled. When a scene is
        # declared its root list is what gets re-parented; when none is, the
        # roots are every node nothing else claims as a child, which is the same
        # set a viewer would treat as top level.
        scenes = document.get("scenes")
        entry: dict[str, object]
        if isinstance(scenes, list) and scenes:
            scene_index = document.get("scene", 0)
            if not isinstance(scene_index, int) or not 0 <= scene_index < len(scenes):
                raise ValidationError("That stadium glTF names no default scene")
            candidate = scenes[scene_index]
            if not isinstance(candidate, dict):
                raise ValidationError("That stadium glTF scene is not an object")
            entry = candidate
            roots = entry.get("nodes")
            if not isinstance(roots, list) or not roots:
                raise ValidationError("That stadium glTF scene has no root nodes")
        else:
            claimed: set[int] = set()
            for node in nodes:
                if isinstance(node, dict) and isinstance(node.get("children"), list):
                    claimed.update(
                        child for child in node["children"] if isinstance(child, int)
                    )
            roots = [index for index in range(len(nodes)) if index not in claimed]
            if not roots:
                raise ValidationError(
                    "That stadium glTF has no top-level nodes to export"
                )
            entry = {}
            document["scenes"] = [entry]
            document["scene"] = 0

        nodes.append({
            "name": "nfl2k5_units_centimetre_to_metre",
            "scale": [GLTF_UNIT_SCALE, GLTF_UNIT_SCALE, GLTF_UNIT_SCALE],
            "children": list(roots),
        })
        entry["nodes"] = [len(nodes) - 1]
        extras = document.setdefault("extras", {})
        if isinstance(extras, dict):
            extras["nfl2k5_unit_contract"] = {
                "authored_unit": "centimetre",
                "gltf_unit": "metre",
                "applied_as": "root node scale",
                "scale": GLTF_UNIT_SCALE,
                "buffer_rewritten": False,
            }

        document, binary = self._embed_textures(scene, document)

        target = destination.expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        target.parent.mkdir(parents=True, exist_ok=True)
        # The glTF names its buffer by filename, so the pair must keep that name
        # and land side by side or the copy will not open.
        binary_target = target.with_name(scene.bin_path.name)
        if target.name == binary_target.name:
            raise ValidationError(
                "The stadium model and its buffer cannot share one filename; "
                f"choose a name other than {scene.bin_path.name}"
            )
        for candidate in (target, binary_target):
            if os.path.lexists(candidate):
                raise ValidationError(f"A file already exists there: {candidate}")

        payload = json.dumps(document, indent=2, sort_keys=True).encode("utf-8")
        written: list[Path] = []
        try:
            self._write_new_file(target, payload)
            written.append(target)
            self._write_new_file(binary_target, binary)
            written.append(binary_target)
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
            raise
        return target.resolve(strict=True), binary_target.resolve(strict=True)

    def _embed_textures(
        self, scene: StadiumScene, document: dict[str, object]
    ) -> tuple[dict[str, object], bytes]:
        """Bind the scene's decoded embedded-texture PNGs to the exported glTF.

        Returns ``(document, binary)``.  When the texture manifest carries no
        rows for this scene the geometry buffer comes back byte-identical to
        what the game shipped and the document is untouched.  Otherwise one
        glTF material is emitted per manifest material row, mapped rows gain a
        ``pbrMetallicRoughness.baseColorTexture``, and the very PNG bytes the
        bounded P8 decoder produced are appended after the untouched geometry
        bytes -- never a second decode.  Each image records the canonical
        ``nfl2k5_texture_id`` that :meth:`replace_textures_from_gltf` maps back
        to the game slot.
        """

        try:
            geometry = scene.bin_path.read_bytes()
        except OSError as exc:
            raise ValidationError(f"Could not read that stadium buffer: {exc}") from exc
        key = (scene.outer_index, scene.chunk_index, scene.scene_index)
        with self._lock:
            self._ensure_ownership_loaded()
            has_rows = bool(self._texture_rows.get(key)) or bool(
                self._material_rows.get(key)
            )
        if not has_rows:
            return document, geometry
        details = self.scene_details(scene)
        textures_by_id = {texture.texture_id: texture for texture in details.textures}
        used: list[StadiumTexture] = []
        claimed: set[str] = set()
        for material in details.materials:
            texture_id = material.texture_id
            if texture_id is None or texture_id in claimed:
                continue
            texture = textures_by_id.get(texture_id)
            if texture is None:
                continue
            claimed.add(texture_id)
            used.append(texture)
        if not used:
            return document, geometry

        for section in ("materials", "images", "textures", "samplers"):
            existing = document.get(section)
            if isinstance(existing, list) and existing:
                raise ValidationError(
                    f"That stadium glTF already declares {section}; "
                    "textures cannot be embedded"
                )
        buffers = document.get("buffers")
        buffer_views = document.get("bufferViews")
        meshes = document.get("meshes")
        if not isinstance(buffers, list) or len(buffers) != 1 \
                or not isinstance(buffers[0], dict) \
                or not isinstance(buffer_views, list) or not isinstance(meshes, list):
            raise ValidationError("That stadium glTF has an unsupported scene layout")

        binary = bytearray(geometry)
        samplers = [
            {
                "name": "nfl2k5_stadium_preview",
                "wrapS": GLTF_WRAP_REPEAT,
                "wrapT": GLTF_WRAP_REPEAT,
                "extras": {
                    "note": "preview defaults; NFL 2K5 sampler state is not proved",
                },
            }
        ]
        images: list[dict[str, object]] = []
        gltf_textures: list[dict[str, object]] = []
        texture_slot: dict[str, int] = {}
        mapping_rows: list[dict[str, object]] = []
        for texture in used:
            png_path = self.preview_texture(texture.texture_id)
            try:
                payload = png_path.read_bytes()
            except OSError as exc:
                raise ValidationError(
                    f"Could not read stadium texture PNG {png_path}: {exc}"
                ) from exc
            binary.extend(b"\0" * ((-len(binary)) & 3))
            buffer_views.append(
                {
                    "buffer": 0,
                    "byteOffset": len(binary),
                    "byteLength": len(payload),
                }
            )
            binary.extend(payload)
            image_name = (
                texture.mapped_material_names[0]
                if texture.mapped_material_names
                else f"texture{texture.texture_index:04d}"
            )
            image_index = len(images)
            images.append(
                {
                    "name": image_name,
                    "bufferView": len(buffer_views) - 1,
                    "mimeType": "image/png",
                    "extras": {
                        GLTF_TEXTURE_ID_KEY: texture.texture_id,
                        "nfl2k5_texture_index": texture.texture_index,
                        "nfl2k5_scene_id": texture.scene_id,
                        "rgba_sha256": texture.rgba_sha256,
                        "width": texture.width,
                        "height": texture.height,
                        "format_name": texture.format_name,
                    },
                }
            )
            texture_slot[texture.texture_id] = len(gltf_textures)
            gltf_textures.append(
                {
                    "name": image_name,
                    "sampler": 0,
                    "source": image_index,
                    "extras": {GLTF_TEXTURE_ID_KEY: texture.texture_id},
                }
            )
            mapping_rows.append(
                {
                    "texture_id": texture.texture_id,
                    "texture_index": texture.texture_index,
                    "image_index": image_index,
                    "image_name": image_name,
                    "width": texture.width,
                    "height": texture.height,
                    "mapped_material_names": list(texture.mapped_material_names),
                }
            )

        materials_out: list[dict[str, object]] = []
        material_slot: dict[int, int] = {}
        textured_material_count = 0
        for material in details.materials:
            material_slot[material.material_index] = len(materials_out)
            pbr: dict[str, object] = {
                "baseColorFactor": list(GLTF_PREVIEW_BASE_COLOR),
                "metallicFactor": 0.0,
                "roughnessFactor": 1.0,
            }
            slot = (
                texture_slot.get(material.texture_id)
                if material.texture_id is not None
                else None
            )
            if slot is not None:
                pbr["baseColorTexture"] = {"index": slot, "texCoord": 0}
                textured_material_count += 1
            materials_out.append(
                {
                    "name": material.name,
                    "doubleSided": True,
                    "pbrMetallicRoughness": pbr,
                    "extras": {
                        GLTF_MATERIAL_INDEX_KEY: material.material_index,
                        "nfl2k5_mapping_status": material.mapping_status,
                        GLTF_TEXTURE_ID_KEY: material.texture_id,
                    },
                }
            )

        for mesh in meshes:
            primitives = mesh.get("primitives") if isinstance(mesh, dict) else None
            if not isinstance(primitives, list):
                raise ValidationError("That stadium glTF has an invalid mesh")
            for primitive in primitives:
                primitive_extras = (
                    primitive.get("extras") if isinstance(primitive, dict) else None
                )
                if not isinstance(primitive_extras, dict):
                    continue
                source_index = primitive_extras.get("source_material_index")
                if isinstance(source_index, bool) or not isinstance(source_index, int):
                    continue
                if source_index in material_slot:
                    primitive["material"] = material_slot[source_index]

        document["materials"] = materials_out
        document["samplers"] = samplers
        document["textures"] = gltf_textures
        document["images"] = images
        buffers[0]["byteLength"] = len(binary)
        extras = document.setdefault("extras", {})
        if isinstance(extras, dict):
            extras["nfl2k5_texture_contract"] = {
                "embedded_image_count": len(images),
                "material_count": len(materials_out),
                "textured_material_count": textured_material_count,
                "geometry_bytes_preserved": True,
                "image_bytes_appended": len(binary) - len(geometry),
                "provenance": (
                    "SCNE embedded P8 base levels decoded by "
                    "tools/nfl_txtr.texture_to_rgba and PNG-encoded by "
                    "encode_rgba_png in the private Stadium cache; the export "
                    "appends those exact PNG bytes without a second decode"
                ),
                "sampler_note": (
                    "wrap modes are preview defaults; game sampler state is unproved"
                ),
                "texcoord_note": (
                    "This export copies the cached geometry byte for byte and so "
                    "carries no TEXCOORD_0. The UV rule is proved (uv = normshort2 * "
                    "(Su, Sv) + (Ou, Ov) from shape record +0x30, the vertex shaders' "
                    "c[-89]); the Models page exports this scene with TEXCOORD_0 bound "
                    "and the same nfl2k5_texture_id contract, and that file is accepted "
                    "by replace_textures_from_gltf"
                ),
                "mapping": mapping_rows,
            }
        return document, bytes(binary)

    def import_scene_gltf(
        self, scene_or_id: "StadiumScene | str", edited_gltf: Path
    ) -> object:
        """Validate and stage same-topology position edits for one full scene.

        The importer consumes only position lanes authorized by the bounded
        catalog. Topology is proved equivalent before staging; UV, material,
        collision, transform, selector, and every other game stream are kept
        from the source SCNE rather than copied from the glTF.
        """

        scene = (
            self.get_scene(scene_or_id)
            if isinstance(scene_or_id, str)
            else scene_or_id
        )
        if self.get_scene(scene.scene_id) != scene:
            raise ValidationError("That stadium scene does not match the manifest")
        supports = getattr(self.edit_delegate, "supports_geometry", None)
        replace_geometry = getattr(self.edit_delegate, "replace_geometry", None)
        if not callable(supports) or not supports(scene) or not callable(replace_geometry):
            raise ActionNotImplementedError(GEOMETRY_FINDINGS)
        from .nfl2k5_stadium_texture_writer import compile_stadium_geometry_recipe

        compiled = compile_stadium_geometry_recipe(
            scene,
            edited_gltf,
            catalog_path=self.geometry_catalog,
        )
        return replace_geometry(scene, compiled)

    @staticmethod
    def _write_new_file(target: Path, payload: bytes) -> None:
        """Exclusive create through a temporary, the way export_texture does."""

        temporary = platform_compat.temporary_sibling(target)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as exc:
                raise ValidationError(
                    f"A file appeared at the export destination: {target}"
                ) from exc
        finally:
            temporary.unlink(missing_ok=True)

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

    def replace_textures_from_gltf(
        self, scene_or_id: "StadiumScene | str", edited_gltf: Path
    ) -> tuple[StadiumGltfTextureWriteBack, ...]:
        """Write Blender-edited glTF images back through the bounded P8 writer.

        This is the import half of the texture loop.  :meth:`export_scene_gltf`
        embeds each game texture as a glTF image carrying its canonical
        ``nfl2k5_texture_id``; a modder edits those images in Blender and
        re-exports; this method maps every replaced image slot back to its
        stadium texture slot -- by that id, falling back to the material name
        when extras were stripped -- and feeds the bytes to the same replace
        route the Stadiums page uses, which compiles them through the
        fixed-allocation P8 writer of ``nfl2k5_stadium_texture_writer.py``.

        A Blender-side script only needs to hand over the edited ``.gltf``
        path; image bytes may live in the glTF bufferView, an external file
        beside it, or a data URI.  Textures are compiled and committed in
        texture-index order, one at a time, exactly like single Replace
        actions: a PNG that does not fit the fixed allocation stops the run
        and leaves any earlier slots in this call replaced.  Unmapped image
        slots are ignored; a file with no mapped slot at all is refused.
        """

        scene = (
            self.get_scene(scene_or_id)
            if isinstance(scene_or_id, str)
            else scene_or_id
        )
        if self.get_scene(scene.scene_id) != scene:
            raise ValidationError("That stadium scene does not match the manifest")
        try:
            path = edited_gltf.expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValidationError(f"Could not open that edited stadium glTF: {exc}") from exc
        slots = stadium_gltf_texture_slots(path)
        details = self.scene_details(scene)
        textures_by_id = {texture.texture_id: texture for texture in details.textures}
        materials_by_name = {material.name: material for material in details.materials}
        resolved: dict[str, bytes] = {}
        for slot in slots:
            texture: StadiumTexture | None = None
            if slot.texture_id is not None:
                texture = textures_by_id.get(slot.texture_id)
            if texture is None:
                named = materials_by_name.get(slot.material_name)
                if named is not None and named.texture_id is not None:
                    texture = textures_by_id.get(named.texture_id)
            if texture is None:
                continue
            existing = resolved.get(texture.texture_id)
            if existing is not None and existing != slot.payload:
                raise ValidationError(
                    "That edited stadium glTF disagrees with itself about one texture"
                )
            resolved[texture.texture_id] = slot.payload
        if not resolved:
            raise ValidationError(
                "That edited stadium glTF names no editable stadium texture"
            )
        selected = sorted(
            (textures_by_id[texture_id] for texture_id in resolved),
            key=lambda texture: texture.texture_index,
        )
        unsupported = [
            texture.texture_id
            for texture in selected
            if not self._delegate_supports(texture)
        ]
        if unsupported:
            raise ActionNotImplementedError(TEXTURE_FINDINGS)
        results: list[StadiumGltfTextureWriteBack] = []
        with tempfile.TemporaryDirectory(prefix="nfl2k5-stadium-gltf-") as staging_name:
            staging = Path(staging_name)
            for texture in selected:
                payload = resolved[texture.texture_id]
                png = staging / f"texture{texture.texture_index:04d}.png"
                self._write_new_file(png, payload)
                write_result = self.replace_texture(texture.texture_id, png)
                results.append(
                    StadiumGltfTextureWriteBack(
                        texture_id=texture.texture_id,
                        scene_id=texture.scene_id,
                        texture_index=texture.texture_index,
                        supplied_png_sha256=hashlib.sha256(payload).hexdigest(),
                        write_result=write_result,
                    )
                )
        return tuple(results)

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
    "GLTF_MATERIAL_INDEX_KEY",
    "GLTF_TEXTURE_ID_KEY",
    "Nfl2k5StadiumStudio",
    "PREVIEW_EXPORT_ONLY",
    "StadiumGeometryTarget",
    "StadiumGltfTextureSlot",
    "StadiumGltfTextureWriteBack",
    "StadiumMaterial",
    "StadiumNode",
    "StadiumScene",
    "StadiumSceneDetails",
    "StadiumSurfaceOwner",
    "StadiumTexture",
    "StadiumTextureEditDelegate",
    "TEXTURE_FINDINGS",
    "stadium_gltf_texture_slots",
]
