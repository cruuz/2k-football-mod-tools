"""Private APF stadium-scene preparation for the desktop product.

The public application ships only code.  Every glTF, binary buffer, preview,
and manifest produced here is derived on demand from the user's own APF copy
and remains in a source-hash-fenced private cache unless the user explicitly
exports a local ZIP.

This module deliberately stops at geometry and package identity.  APF SCNE
draw/material semantics are not yet mapped to TXTR resources, so a selected
surface never claims an owning texture and no stadium replacement writer is
exposed here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Callable

from .backend import ensure_tools_importable
from .catalog import ApfCatalog
from .models import ApfAsset, ApfSource


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_scene  # type: ignore  # noqa: E402


Progress = Callable[[str, int, int], None]
STADIUM_CACHE_SCHEMA = "apf2k8_mod_studio_stadium_preview/v1"
STADIUM_SCENE_NAME = "stadium"
STADIUM_SCENE_TYPE = "SCNE"


class StadiumStudioError(ValueError):
    """A stadium scene or its private derived cache failed validation."""


@dataclass(frozen=True, slots=True)
class ApfStadiumScene:
    asset_id: str
    outer_index: int
    inner_index: int
    decoded_size: int
    package_asset_count: int

    @property
    def display_name(self) -> str:
        return f"Outer {self.outer_index} / inner {self.inner_index}"


@dataclass(frozen=True, slots=True)
class ApfStadiumPreview:
    scene: ApfStadiumScene
    root: Path
    gltf_path: Path
    bin_path: Path
    manifest_path: Path
    system_sha256: str
    mesh_count: int
    skipped_mesh_count: int
    vertex_count: int
    triangle_count: int
    package_assets: tuple[ApfAsset, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _regular(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise StadiumStudioError(f"The private {label} is missing") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise StadiumStudioError(f"The private {label} is not a regular file")
    return info


def stadium_package_assets(
    catalog: ApfCatalog, scene: ApfStadiumScene | str
) -> tuple[ApfAsset, ...]:
    item = catalog.get(scene) if isinstance(scene, str) else catalog.get(scene.asset_id)
    _validate_scene_asset(item)
    return tuple(
        sorted(
            (asset for asset in catalog.assets if asset.outer_index == item.outer_index),
            key=lambda asset: (
                -1 if asset.inner_index is None else asset.inner_index,
                asset.asset_id,
            ),
        )
    )


def stadium_scenes(
    catalog: ApfCatalog, search: str = ""
) -> tuple[ApfStadiumScene, ...]:
    """List exact stadium SCNE records without guessing venue ownership."""

    needle = search.strip().casefold()
    package_counts: dict[int, int] = {}
    for asset in catalog.assets:
        package_counts[asset.outer_index] = package_counts.get(asset.outer_index, 0) + 1
    values: list[ApfStadiumScene] = []
    for asset in catalog.assets:
        if (
            asset.type_name != STADIUM_SCENE_TYPE
            or asset.name != STADIUM_SCENE_NAME
            or asset.inner_index is None
        ):
            continue
        searchable = (
            f"{asset.asset_id} outer {asset.outer_index} inner {asset.inner_index} "
            f"{asset.name} {asset.type_name}"
        ).casefold()
        if needle and needle not in searchable:
            continue
        values.append(
            ApfStadiumScene(
                asset_id=asset.asset_id,
                outer_index=asset.outer_index,
                inner_index=asset.inner_index,
                decoded_size=asset.decoded_size,
                package_asset_count=package_counts[asset.outer_index],
            )
        )
    return tuple(sorted(values, key=lambda item: (item.outer_index, item.inner_index)))


def _validate_scene_asset(asset: ApfAsset) -> None:
    if (
        asset.type_name != STADIUM_SCENE_TYPE
        or asset.name != STADIUM_SCENE_NAME
        or asset.inner_index is None
    ):
        raise StadiumStudioError(
            "Choose an exact stadium SCNE record before preparing a 3D preview"
        )


class ApfStadiumService:
    """Prepare and validate one source-derived APF stadium glTF at a time."""

    def __init__(
        self,
        source: ApfSource,
        catalog: ApfCatalog,
        cache_root: Path | None = None,
    ):
        self.source = source
        self.catalog = catalog
        self.cache_root = cache_root or Path.home() / ".cache" / "apf2k8-mod-studio"

    @property
    def private_root(self) -> Path:
        return (
            self.cache_root
            / "derived"
            / self.source.source_sha256
            / "stadium-studio-v1"
        )

    def scenes(self, search: str = "") -> tuple[ApfStadiumScene, ...]:
        return stadium_scenes(self.catalog, search)

    def package_assets(self, scene: ApfStadiumScene | str) -> tuple[ApfAsset, ...]:
        return stadium_package_assets(self.catalog, scene)

    def prepare(
        self,
        scene: ApfStadiumScene | str,
        progress: Progress | None = None,
    ) -> ApfStadiumPreview:
        report = progress or (lambda _stage, _completed, _total: None)
        selected = self._scene(scene)
        final = self.private_root / (
            f"outer-{selected.outer_index:04d}-inner-{selected.inner_index:04d}"
        )
        manifest = final / "manifest.json"
        if manifest.is_file() and not manifest.is_symlink():
            report("Opening private stadium cache", 1, 1)
            return self._load_cached(selected, final)
        if final.exists() or final.is_symlink():
            raise StadiumStudioError(
                "The private stadium cache path is not a valid completed scene; "
                "remove that one cache folder and try again"
            )

        self.private_root.mkdir(parents=True, exist_ok=True)
        report("Reading the selected stadium scene", 0, 3)
        system = self._read_scene_system(selected)
        system_sha256 = hashlib.sha256(system).hexdigest()
        report("Decoding private stadium geometry", 1, 3)
        try:
            decoded = apf_scene.parse_scene_system_part(
                system,
                outer_index=selected.outer_index,
                inner_index=selected.inner_index,
                capture_geometry=True,
            )
        except (apf_scene.SceneError, apf_inner.FormatError, ValueError) as exc:
            raise StadiumStudioError(f"Could not decode this stadium scene: {exc}") from exc
        if decoded.get("root_name") != STADIUM_SCENE_NAME:
            raise StadiumStudioError("The selected SCNE no longer has the stadium root")
        if decoded.get("system_sha256") != system_sha256:
            raise StadiumStudioError("The stadium decoder returned a mismatched scene identity")

        staging = Path(
            tempfile.mkdtemp(prefix=f".{final.name}.", suffix=".preparing", dir=final.parent)
        )
        try:
            gltf_path = staging / "scene.gltf"
            bin_path = staging / "scene.bin"
            report("Building the private stadium glTF", 2, 3)
            try:
                export = apf_scene.write_gltf_collection(
                    gltf_path,
                    bin_path,
                    decoded,
                    selected.outer_index,
                    selected.inner_index,
                )
            except (apf_scene.SceneError, OSError, ValueError) as exc:
                raise StadiumStudioError(
                    f"This stadium has no supported static 3D preview: {exc}"
                ) from exc
            if export.get("status") != "exported":
                raise StadiumStudioError("The stadium glTF exporter withheld this scene")
            package = self.package_assets(selected)
            document = {
                "schema": STADIUM_CACHE_SCHEMA,
                "source_sha256": self.source.source_sha256,
                "scene": {
                    "asset_id": selected.asset_id,
                    "outer_index": selected.outer_index,
                    "inner_index": selected.inner_index,
                    "system_sha256": system_sha256,
                },
                "gltf": {
                    "path": gltf_path.name,
                    "sha256": _sha256(gltf_path),
                },
                "binary": {
                    "path": bin_path.name,
                    "sha256": _sha256(bin_path),
                },
                "export": export,
                "package_asset_ids": [asset.asset_id for asset in package],
                "claim_boundary": {
                    "geometry_preview": "raw-coordinate POSITION/topology only",
                    "texture_ownership_resolved": False,
                    "stadium_texture_writer_available": False,
                    "geometry_import_available": False,
                },
                "retail_data_policy": (
                    "Private derivative of the user's own game; do not redistribute. "
                    "This cache never enters an APF project or public release."
                ),
            }
            manifest_path = staging / "manifest.json"
            manifest_path.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            # A directory rename publishes the complete triplet at once.  If a
            # concurrent worker won the race, validate and use that completed
            # cache rather than replacing it.
            try:
                staging.rename(final)
            except FileExistsError:
                if not (final / "manifest.json").is_file():
                    raise StadiumStudioError(
                        "Another stadium preview did not finish cleanly"
                    )
            report("Private stadium preview ready", 3, 3)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return self._load_cached(selected, final)

    def _scene(self, scene: ApfStadiumScene | str) -> ApfStadiumScene:
        if isinstance(scene, ApfStadiumScene):
            asset = self.catalog.get(scene.asset_id)
            _validate_scene_asset(asset)
            if (asset.outer_index, asset.inner_index) != (
                scene.outer_index,
                scene.inner_index,
            ):
                raise StadiumStudioError("The selected stadium scene identity changed")
            return scene
        asset = self.catalog.get(scene)
        _validate_scene_asset(asset)
        assert asset.inner_index is not None
        package_count = sum(
            candidate.outer_index == asset.outer_index for candidate in self.catalog.assets
        )
        return ApfStadiumScene(
            asset_id=asset.asset_id,
            outer_index=asset.outer_index,
            inner_index=asset.inner_index,
            decoded_size=asset.decoded_size,
            package_asset_count=package_count,
        )

    def _read_scene_system(self, scene: ApfStadiumScene) -> bytes:
        archive = apf_outer.parse_archive(self.source.index_0a)
        try:
            entry = archive.entries[scene.outer_index]
        except IndexError as exc:
            raise StadiumStudioError(
                f"The APF archive has no outer entry {scene.outer_index}"
            ) from exc
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            try:
                item = record.files[scene.inner_index]
            except IndexError as exc:
                raise StadiumStudioError(
                    f"Outer {scene.outer_index} has no inner {scene.inner_index}"
                ) from exc
            if item.name != STADIUM_SCENE_NAME or item.type_name != STADIUM_SCENE_TYPE:
                raise StadiumStudioError("The selected archive record is no longer stadium/SCNE")
            if not item.parts:
                raise StadiumStudioError("The selected stadium SCNE has no system part")
            part = item.parts[0]
            block = apf_inner.decode_block(
                reader, record, part.block_index, 512 * 1024 * 1024
            )
            end = part.offset + part.length
            if part.offset < 0 or end > len(block):
                raise StadiumStudioError("The stadium SCNE system part exceeds its block")
            return block[part.offset:end]

    def _load_cached(self, scene: ApfStadiumScene, root: Path) -> ApfStadiumPreview:
        root_info = root.lstat()
        if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
            raise StadiumStudioError("The private stadium cache is not a safe directory")
        manifest_path = root / "manifest.json"
        _regular(manifest_path, "stadium manifest")
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise StadiumStudioError("The private stadium manifest is invalid") from exc
        scene_row = document.get("scene")
        export = document.get("export")
        if (
            document.get("schema") != STADIUM_CACHE_SCHEMA
            or document.get("source_sha256") != self.source.source_sha256
            or not isinstance(scene_row, dict)
            or scene_row.get("asset_id") != scene.asset_id
            or scene_row.get("outer_index") != scene.outer_index
            or scene_row.get("inner_index") != scene.inner_index
            or not isinstance(scene_row.get("system_sha256"), str)
            or not isinstance(export, dict)
            or export.get("status") != "exported"
        ):
            raise StadiumStudioError("The private stadium manifest identity changed")
        gltf_row = document.get("gltf")
        binary_row = document.get("binary")
        if not isinstance(gltf_row, dict) or not isinstance(binary_row, dict):
            raise StadiumStudioError("The private stadium manifest is incomplete")
        if gltf_row.get("path") != "scene.gltf" or binary_row.get("path") != "scene.bin":
            raise StadiumStudioError("The private stadium filenames changed")
        gltf_path = root / "scene.gltf"
        bin_path = root / "scene.bin"
        _regular(gltf_path, "stadium glTF")
        _regular(bin_path, "stadium binary")
        if _sha256(gltf_path) != gltf_row.get("sha256"):
            raise StadiumStudioError("The private stadium glTF changed after generation")
        if _sha256(bin_path) != binary_row.get("sha256"):
            raise StadiumStudioError("The private stadium binary changed after generation")
        package = self.package_assets(scene)
        if document.get("package_asset_ids") != [asset.asset_id for asset in package]:
            raise StadiumStudioError("The stadium package inventory changed")
        try:
            return ApfStadiumPreview(
                scene=scene,
                root=root,
                gltf_path=gltf_path,
                bin_path=bin_path,
                manifest_path=manifest_path,
                system_sha256=str(scene_row["system_sha256"]),
                mesh_count=int(export["mesh_count"]),
                skipped_mesh_count=int(export["skipped_mesh_count"]),
                vertex_count=int(export["vertex_count"]),
                triangle_count=int(export["triangle_count"]),
                package_assets=package,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StadiumStudioError("The private stadium summary is invalid") from exc


__all__ = [
    "ApfStadiumPreview",
    "ApfStadiumScene",
    "ApfStadiumService",
    "STADIUM_CACHE_SCHEMA",
    "StadiumStudioError",
    "stadium_package_assets",
    "stadium_scenes",
]
