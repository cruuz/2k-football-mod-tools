"""The Crib asset catalog, private export service, and bounded compilers.

This module deliberately separates three concerns:

* public product metadata names every known Crib texture without retaining
  retail pixels;
* original PNG exports are decoded lazily from the user's private source
  cache; and
* the writable classes are the code-owned ``##_photo_##`` Team Photo family
  and the one proved ``room:22`` ``bar_monitor`` scene texture.  Both rebuild
  five P8 mip levels without changing their owning allocation.

Compiled spans contain wrapper/system bytes copied from the user's own dump.
They are build-time values only and must never be serialized into a shareable
project. :meth:`CribAsset.provider_edit` intentionally returns only the logical
selector and user-authored PNG path.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Callable, Iterable

from .errors import ValidationError
from .json_stream import (
    file_contains_bytes,
    iter_top_level_array,
    require_regular_file,
)
from .nfl2k5_source_cache import SourceCache


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl_outer import parse_archive, read_entry_range  # noqa: E402
import nfl_tset_png_import as palette_tools  # noqa: E402
from nfl_txtr import (  # noqa: E402
    HEADER,
    TextureInfo,
    decode_chunk,
    encode_rgba_png,
    parse_chunks,
    parse_texture,
    swizzle_2d,
    texture_to_rgba,
    unswizzle_2d,
)


CAPABILITY_ID = "nfl2k5.crib.assets"
TEXTURE_REPORT_SCHEMA = "nfl2k5_all_txtr_inventory/v1"
PHOTO_REPORT_SCHEMA = "nfl2k5_player_portrait_compatibility/v1"
ORIGINAL_SCHEMA = "2k5_mod_studio_crib_original_png/v1"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_PNG_BYTES = 32 * 1024 * 1024
COMPACT_CATALOG_SCHEMA = "2k5_mod_studio_crib_catalog/v1"
COMPACT_CATALOG_PATH = ROOT / "mod_editor/data/nfl2k5_crib_catalog.v1.json"
RESOURCE_HEADER_SIZE = HEADER.size
PHOTO_NAME = re.compile(r"^(\d\d)_photo_(0[0-3])$", re.ASCII)
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
BAR_MONITOR_SELECTOR = "crib_scene_texture:room:22"
BAR_MONITOR_ASSET_ID = "nfl2k5.crib.scene.c0002.t022"


class CribCatalogError(ValidationError):
    """A Crib report or logical selector failed its product boundary."""


class CribAssetStatus(str, Enum):
    EDITABLE = "editable"
    EXPORT_ONLY = "export_only"


class CribStorage(str, Enum):
    TEAM_ITEM_AGGREGATE = "team_item_aggregate"
    EXTERNAL_TEXTURE = "external_texture"
    SCENE_EMBEDDED = "scene_embedded"


@dataclass(frozen=True, slots=True)
class CribReportPaths:
    texture_inventory: Path = (
        ROOT / "reports/assets/nfl2k5_all_txtr_inventory_v2.json"
    )
    photo_ownership: Path = (
        ROOT / "reports/assets/nfl2k5_player_portrait_compatibility.json"
    )
    embedded_textures: Path = (
        ROOT / "reports/assets/nfl2k5_scne_embedded_textures.tsv"
    )
    scenes: Path = ROOT / "reports/assets/nfl2k5_scne_scenes.tsv"


@dataclass(frozen=True, slots=True)
class CribCatalogExpectations:
    team_item_count: int
    photo_count: int
    external_texture_count: int
    embedded_texture_count: int
    embedded_scene_count: int

    @property
    def total_count(self) -> int:
        return (
            self.team_item_count
            + self.external_texture_count
            + self.embedded_texture_count
        )


PRODUCTION_EXPECTATIONS = CribCatalogExpectations(
    team_item_count=242,
    photo_count=128,
    external_texture_count=68,
    embedded_texture_count=188,
    embedded_scene_count=36,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CribCatalogError(message)


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    _require(
        type(value) is int and int(value) >= minimum,
        f"{label} must be an integer at least {minimum}",
    )
    return int(value)


def _tsv_integer(value: str | None, label: str, *, minimum: int = 0) -> int:
    try:
        result = int(str(value), 0)
    except (TypeError, ValueError) as exc:
        raise CribCatalogError(f"{label} is not an integer") from exc
    _require(result >= minimum, f"{label} must be at least {minimum}")
    return result


def _text(value: object, label: str) -> str:
    _require(isinstance(value, str) and bool(value), f"{label} must be text")
    return str(value)


def _sha(value: object, label: str) -> str:
    result = _text(value, label)
    _require(HEX_SHA256.fullmatch(result) is not None, f"{label} is not SHA-256")
    return result


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_small_json(path: Path, schema: str, label: str) -> dict[str, Any]:
    info = require_regular_file(path, label)
    _require(0 < info.st_size <= MAX_JSON_BYTES, f"{label} is outside its size bound")
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CribCatalogError(f"Could not read {label}: {exc}") from exc
    _require(
        isinstance(value, dict) and value.get("schema") == schema,
        f"{label} schema is unsupported",
    )
    return value


def _title(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", " ").split())


def _asset_group(name: str) -> str:
    if PHOTO_NAME.fullmatch(name):
        return "Team Photos"
    if name.endswith("_helmet"):
        return "Team Collectibles / Helmets"
    if name.endswith("_foam_finger"):
        return "Team Collectibles / Foam Fingers"
    if name.endswith("_sign_street"):
        return "Team Collectibles / Street Signs"
    if name.startswith("collection_"):
        return "Collection Art"
    if name.startswith("bobblehead_"):
        return "Bobbleheads"
    if name.endswith("_teamlogo"):
        return "Team Logos"
    return "Shared Crib Art"


def _path_text(path: str | os.PathLike[str]) -> str:
    try:
        value = os.fspath(path)
    except TypeError as exc:
        raise CribCatalogError("Replacement PNG path must be text") from exc
    _require(isinstance(value, str) and bool(value) and "\0" not in value,
             "Replacement PNG path is invalid")
    return value


@dataclass(frozen=True, slots=True)
class CribAsset:
    """One physical Crib texture visible in the product browser."""

    asset_id: str
    selector: str
    label: str
    group: str
    status: CribAssetStatus
    storage: CribStorage
    authoring_note: str
    width: int
    height: int
    mip_levels: int
    format_name: str
    outer_index: int
    outer_id: str
    outer_size: int
    chunk_index: int
    chunk_offset: int
    stored_size: int
    system_bytes: int
    video_bytes: int
    descriptor_offset: int
    pixel_offset: int
    palette_offset: int
    packed_format: int
    packed_size: int
    decoded_sha256: str
    rgba_sha256: str
    scene_name: str | None = None
    texture_index: int | None = None
    material_names: tuple[str, ...] = ()
    resource_decoded_sha256: str | None = None
    span_sha256: str | None = None
    xiso_absolute_offset: int | None = None
    post_span_zero_padding: int = 0
    asset_code: str | None = None
    variant: int | None = None
    capability_id: str = CAPABILITY_ID

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.width, self.height

    @property
    def editable(self) -> bool:
        return self.status is CribAssetStatus.EDITABLE

    @property
    def suggested_filename(self) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.selector).strip("_")
        return f"{safe}.png"

    def provider_edit(self, png_path: str | os.PathLike[str]) -> dict[str, Any]:
        """Return a shareable logical edit containing no retail bytes/offsets."""

        if not self.editable:
            raise CribCatalogError(
                f"{self.label} is Preview/Export-only; replacement is Coming Soon"
            )
        if self.storage is CribStorage.TEAM_ITEM_AGGREGATE:
            _require(
                PHOTO_NAME.fullmatch(self.selector.split(":", 1)[-1]) is not None,
                "Crib photo selector is invalid",
            )
            kind = "crib_team_photo"
        else:
            _require(
                self.storage is CribStorage.SCENE_EMBEDDED
                and self.selector == BAR_MONITOR_SELECTOR
                and self.asset_id == BAR_MONITOR_ASSET_ID,
                "Crib scene-texture selector is not a proved writable target",
            )
            kind = "crib_scene_texture"
        return {
            "kind": kind,
            "png": _path_text(png_path),
            "selector": self.selector,
        }


@dataclass(frozen=True, slots=True)
class CompiledCribPhotoPatch:
    """Private build-time patch; never put ``replacement_span`` in a project."""

    asset_id: str
    selector: str
    absolute_xiso_offset: int
    expected_original_span_sha256: str
    replacement_span_sha256: str
    replacement_rgba_sha256: str
    replacement_span: bytes
    preview_png: bytes
    changed_byte_count: int

    def shareable_edit(self, png_path: str | os.PathLike[str]) -> dict[str, str]:
        return {
            "kind": "crib_team_photo",
            "png": _path_text(png_path),
            "selector": self.selector,
        }


class Nfl2k5CribCatalog:
    """Immutable catalog of all 498 currently known physical Crib textures."""

    def __init__(
        self,
        assets: Iterable[CribAsset],
        report_paths: CribReportPaths,
        expectations: CribCatalogExpectations,
    ) -> None:
        self.assets = tuple(assets)
        self.report_paths = report_paths
        self.expectations = expectations
        self._by_id = {asset.asset_id: asset for asset in self.assets}
        self._by_selector = {asset.selector: asset for asset in self.assets}
        _require(len(self._by_id) == len(self.assets), "Crib asset IDs are duplicated")
        _require(
            len(self._by_selector) == len(self.assets),
            "Crib logical selectors are duplicated",
        )
        _require(
            len(self.assets) == expectations.total_count,
            f"Crib catalog has {len(self.assets)} assets; "
            f"{expectations.total_count} were expected",
        )

    @classmethod
    def from_reports(
        cls,
        report_paths: CribReportPaths = CribReportPaths(),
        *,
        expectations: CribCatalogExpectations = PRODUCTION_EXPECTATIONS,
    ) -> "Nfl2k5CribCatalog":
        ownership = _read_small_json(
            report_paths.photo_ownership,
            PHOTO_REPORT_SCHEMA,
            "Crib Team Photo ownership report",
        )
        photo_rows = ownership.get("crib_action_photo_resources")
        contract = ownership.get("crib_action_photo_contract")
        _require(isinstance(photo_rows, list), "Crib photo ownership rows are missing")
        _require(isinstance(contract, dict), "Crib photo layout contract is missing")
        _require(
            len(photo_rows) == expectations.photo_count
            and contract.get("resource_count") == expectations.photo_count,
            "Crib photo ownership count changed",
        )
        owned_photos: dict[str, dict[str, Any]] = {}
        for number, item in enumerate(photo_rows):
            _require(isinstance(item, dict), f"Crib photo row {number} is invalid")
            name = _text(item.get("name"), f"Crib photo row {number} name")
            _require(PHOTO_NAME.fullmatch(name) is not None,
                     f"Crib photo name {name!r} is invalid")
            _require(name not in owned_photos, f"Crib photo {name} is duplicated")
            owned_photos[name] = item

        texture_path = report_paths.texture_inventory
        require_regular_file(texture_path, "Crib texture inventory")
        _require(
            file_contains_bytes(
                texture_path,
                f'"schema": "{TEXTURE_REPORT_SCHEMA}"'.encode("ascii"),
                label="Crib texture inventory",
            ),
            "Crib texture inventory schema is unsupported",
        )
        aggregate_rows: list[dict[str, Any]] = []
        external_rows: list[dict[str, Any]] = []
        for raw in iter_top_level_array(
            texture_path, "textures", label="Crib texture inventory"
        ):
            _require(isinstance(raw, dict), "Crib texture inventory row is invalid")
            if raw.get("outer_index") == 4274:
                aggregate_rows.append(raw)
            elif raw.get("outer_head") == "CRIB":
                external_rows.append(raw)
        _require(
            len(aggregate_rows) == expectations.team_item_count,
            "Crib team/item aggregate count changed",
        )
        _require(
            len(external_rows) == expectations.external_texture_count,
            "Crib external texture count changed",
        )
        aggregate_names = {_text(row.get("name"), "Crib aggregate texture name")
                           for row in aggregate_rows}
        _require(
            set(owned_photos) <= aggregate_names
            and len(set(owned_photos) & aggregate_names) == expectations.photo_count,
            "Crib photo ownership does not join the texture inventory",
        )

        scene_rows = cls._read_scene_rows(report_paths.scenes)
        embedded_rows = cls._read_embedded_rows(report_paths.embedded_textures)
        selected_embedded = [row for row in embedded_rows
                             if _tsv_integer(row.get("outer_index"),
                                             "embedded outer index") == 4248]
        _require(
            len(selected_embedded) == expectations.embedded_texture_count,
            "Crib embedded texture count changed",
        )
        embedded_scenes = {
            (_tsv_integer(row.get("chunk_index"), "embedded chunk index"),
             _text(row.get("scene_name"), "embedded scene name"))
            for row in selected_embedded
        }
        _require(
            len(embedded_scenes) == expectations.embedded_scene_count,
            "Crib embedded scene count changed",
        )

        assets = [
            *(cls._aggregate_asset(row, owned_photos.get(str(row.get("name"))))
              for row in aggregate_rows),
            *(cls._external_asset(row) for row in external_rows),
            *(cls._embedded_asset(row, scene_rows) for row in selected_embedded),
        ]
        return cls(assets, report_paths, expectations)

    @classmethod
    def from_compact_catalog(
        cls,
        path: Path = COMPACT_CATALOG_PATH,
        *,
        expectations: CribCatalogExpectations = PRODUCTION_EXPECTATIONS,
    ) -> "Nfl2k5CribCatalog":
        """Load the release catalog containing metadata but no retail pixels.

        The compact file is mechanically derived from the audited inventory.
        It carries selectors, bounds, offsets, and checksums needed to decode a
        user's own XISO, but never carries a resource span or decoded image.
        """

        document = _read_small_json(
            path, COMPACT_CATALOG_SCHEMA, "compact Crib asset catalog"
        )
        _require(
            document.get("payload_policy") == "metadata-only-no-retail-bytes",
            "compact Crib catalog payload policy changed",
        )
        expected_record = document.get("expectations")
        required_expectation_fields = {
            "team_item_count",
            "photo_count",
            "external_texture_count",
            "embedded_texture_count",
            "embedded_scene_count",
        }
        _require(
            isinstance(expected_record, dict)
            and set(expected_record) == required_expectation_fields,
            "compact Crib catalog expectations are malformed",
        )
        parsed_expectations = CribCatalogExpectations(**{
            name: _integer(expected_record.get(name), f"Crib expectation {name}")
            for name in required_expectation_fields
        })
        _require(
            parsed_expectations == expectations,
            "compact Crib catalog inventory counts changed",
        )
        rows = document.get("assets")
        _require(
            isinstance(rows, list) and len(rows) == expectations.total_count,
            "compact Crib catalog asset count changed",
        )
        required_asset_fields = {field.name for field in fields(CribAsset)}
        assets: list[CribAsset] = []
        for index, value in enumerate(rows):
            _require(
                isinstance(value, dict) and set(value) == required_asset_fields,
                f"compact Crib asset {index} fields are malformed",
            )
            row = dict(value)
            try:
                row["status"] = CribAssetStatus(row["status"])
                row["storage"] = CribStorage(row["storage"])
            except (TypeError, ValueError) as exc:
                raise CribCatalogError(
                    f"compact Crib asset {index} status is unsupported"
                ) from exc
            materials = row.get("material_names")
            _require(
                isinstance(materials, list)
                and all(isinstance(item, str) for item in materials),
                f"compact Crib asset {index} material names are malformed",
            )
            row["material_names"] = tuple(materials)
            for name in (
                "asset_id", "selector", "label", "group", "authoring_note",
                "format_name", "outer_id", "decoded_sha256", "rgba_sha256",
                "capability_id",
            ):
                _text(row.get(name), f"compact Crib asset {index} {name}")
            _require(
                row.get("capability_id") == CAPABILITY_ID,
                f"compact Crib asset {index} capability changed",
            )
            for name in (
                "width", "height", "mip_levels", "outer_index", "outer_size",
                "chunk_index", "chunk_offset", "stored_size", "system_bytes",
                "video_bytes", "descriptor_offset", "pixel_offset",
                "palette_offset", "packed_format", "packed_size",
                "post_span_zero_padding",
            ):
                row[name] = _integer(
                    row.get(name), f"compact Crib asset {index} {name}"
                )
            for name in (
                "texture_index", "xiso_absolute_offset", "variant"
            ):
                if row.get(name) is not None:
                    row[name] = _integer(
                        row.get(name), f"compact Crib asset {index} {name}"
                    )
            for name in (
                "resource_decoded_sha256", "span_sha256"
            ):
                if row.get(name) is not None:
                    row[name] = _sha(
                        row.get(name), f"compact Crib asset {index} {name}"
                    )
            for name in ("decoded_sha256", "rgba_sha256"):
                row[name] = _sha(
                    row.get(name), f"compact Crib asset {index} {name}"
                )
            for name in ("scene_name", "asset_code"):
                _require(
                    row.get(name) is None or isinstance(row.get(name), str),
                    f"compact Crib asset {index} {name} is malformed",
                )
            assets.append(CribAsset(**row))
        # Report paths are retained only for diagnostics and development
        # regeneration; release-time catalog loading never opens them.
        return cls(assets, CribReportPaths(), expectations)

    @staticmethod
    def _read_scene_rows(path: Path) -> dict[int, dict[str, str]]:
        require_regular_file(path, "Crib scene inventory")
        try:
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
        except OSError as exc:
            raise CribCatalogError(f"Could not read Crib scene inventory: {exc}") from exc
        result: dict[int, dict[str, str]] = {}
        for row in rows:
            if row.get("outer_index") != "4248":
                continue
            chunk = _tsv_integer(row.get("chunk_index"), "Crib scene chunk index")
            _require(chunk not in result, f"Crib scene chunk {chunk} is duplicated")
            result[chunk] = row
        return result

    @staticmethod
    def _read_embedded_rows(path: Path) -> list[dict[str, str]]:
        require_regular_file(path, "Crib embedded-texture inventory")
        try:
            with path.open(newline="", encoding="utf-8") as stream:
                return list(csv.DictReader(stream, delimiter="\t"))
        except OSError as exc:
            raise CribCatalogError(
                f"Could not read Crib embedded-texture inventory: {exc}"
            ) from exc

    @staticmethod
    def _aggregate_asset(row: dict[str, Any], owner: dict[str, Any] | None) -> CribAsset:
        name = _text(row.get("name"), "Crib aggregate texture name")
        photo_match = PHOTO_NAME.fullmatch(name)
        editable = owner is not None
        _require(editable == (photo_match is not None),
                 f"Crib photo ownership mismatch for {name}")
        if owner is not None:
            _require(owner.get("selector") == f"crib_team_photo:{name}",
                     f"Crib photo selector changed for {name}")
            span_sha = _sha(owner.get("span_sha256"), f"{name} span hash")
            xiso_offset = _integer(
                owner.get("xiso_absolute_span_offset"), f"{name} XISO offset"
            )
            padding = _integer(
                owner.get("post_span_zero_padding"), f"{name} slot padding"
            )
            asset_code = _text(owner.get("asset_code"), f"{name} asset code")
            variant = _integer(owner.get("variant"), f"{name} variant")
        else:
            span_sha = None
            xiso_offset = None
            padding = 0
            asset_code = None
            variant = None
        return CribAsset(
            asset_id=f"nfl2k5.crib.aggregate.{name}",
            selector=(f"crib_team_photo:{name}" if editable
                      else f"crib_item_texture:{name}"),
            label=(f"Team {asset_code} — Photo {variant}" if editable
                   else _title(name)),
            group=_asset_group(name),
            status=(CribAssetStatus.EDITABLE if editable
                    else CribAssetStatus.EXPORT_ONLY),
            storage=CribStorage.TEAM_ITEM_AGGREGATE,
            authoring_note=(
                "Paint the complete 128×128 RGBA image. Mod Studio regenerates "
                "all five P8 mip levels and keeps the fixed slot size."
                if editable else
                "Preview/Export-only: ownership is known, but this item class "
                "does not yet have a reviewed import route."
            ),
            width=_integer(row.get("width"), f"{name} width", minimum=1),
            height=_integer(row.get("height"), f"{name} height", minimum=1),
            mip_levels=_integer(row.get("mip_levels"), f"{name} mip count", minimum=1),
            format_name=_text(row.get("format_name"), f"{name} format"),
            outer_index=_integer(row.get("outer_index"), f"{name} outer index"),
            outer_id=_text(row.get("outer_id"), f"{name} outer ID"),
            outer_size=_integer(row.get("outer_size"), f"{name} outer size", minimum=1),
            chunk_index=_integer(row.get("chunk_index"), f"{name} chunk index"),
            chunk_offset=_integer(row.get("chunk_offset"), f"{name} chunk offset"),
            stored_size=_integer(row.get("stored_size"), f"{name} stored size", minimum=1),
            system_bytes=_integer(row.get("system_bytes"), f"{name} system bytes", minimum=1),
            video_bytes=_integer(row.get("video_bytes"), f"{name} video bytes", minimum=1),
            descriptor_offset=_integer(row.get("descriptor_offset"),
                                       f"{name} descriptor offset"),
            pixel_offset=_integer(row.get("pixel_offset"), f"{name} pixel offset"),
            palette_offset=_integer(row.get("palette_offset"), f"{name} palette offset"),
            packed_format=int(_text(row.get("packed_format"), f"{name} packed format"), 0),
            packed_size=int(_text(row.get("packed_size"), f"{name} packed size"), 0),
            decoded_sha256=_sha(row.get("decoded_sha256"), f"{name} decoded hash"),
            rgba_sha256=_sha(row.get("rgba_sha256"), f"{name} RGBA hash"),
            span_sha256=span_sha,
            xiso_absolute_offset=xiso_offset,
            post_span_zero_padding=padding,
            asset_code=asset_code,
            variant=variant,
        )

    @staticmethod
    def _external_asset(row: dict[str, Any]) -> CribAsset:
        name = _text(row.get("name"), "Crib external texture name")
        return CribAsset(
            asset_id=(f"nfl2k5.crib.external.o{int(row['outer_index']):04d}."
                      f"c{int(row['chunk_index']):04d}.{name}"),
            selector=f"crib_external_texture:{int(row['chunk_index'])}:{name}",
            label=_title(name),
            group=_asset_group(name),
            status=CribAssetStatus.EXPORT_ONLY,
            storage=CribStorage.EXTERNAL_TEXTURE,
            authoring_note=(
                "Preview/Export-only: this compressed standalone texture has "
                "known ownership, but no reviewed Crib import route yet."
            ),
            width=_integer(row.get("width"), f"{name} width", minimum=1),
            height=_integer(row.get("height"), f"{name} height", minimum=1),
            mip_levels=_integer(row.get("mip_levels"), f"{name} mip count", minimum=1),
            format_name=_text(row.get("format_name"), f"{name} format"),
            outer_index=_integer(row.get("outer_index"), f"{name} outer index"),
            outer_id=_text(row.get("outer_id"), f"{name} outer ID"),
            outer_size=_integer(row.get("outer_size"), f"{name} outer size", minimum=1),
            chunk_index=_integer(row.get("chunk_index"), f"{name} chunk index"),
            chunk_offset=_integer(row.get("chunk_offset"), f"{name} chunk offset"),
            stored_size=_integer(row.get("stored_size"), f"{name} stored size", minimum=1),
            system_bytes=_integer(row.get("system_bytes"), f"{name} system bytes", minimum=1),
            video_bytes=_integer(row.get("video_bytes"), f"{name} video bytes", minimum=1),
            descriptor_offset=_integer(row.get("descriptor_offset"),
                                       f"{name} descriptor offset"),
            pixel_offset=_integer(row.get("pixel_offset"), f"{name} pixel offset"),
            palette_offset=_integer(row.get("palette_offset"), f"{name} palette offset"),
            packed_format=int(_text(row.get("packed_format"), f"{name} packed format"), 0),
            packed_size=int(_text(row.get("packed_size"), f"{name} packed size"), 0),
            decoded_sha256=_sha(row.get("decoded_sha256"), f"{name} decoded hash"),
            rgba_sha256=_sha(row.get("rgba_sha256"), f"{name} RGBA hash"),
        )

    @staticmethod
    def _embedded_asset(
        row: dict[str, str], scene_rows: dict[int, dict[str, str]]
    ) -> CribAsset:
        chunk_index = _tsv_integer(row.get("chunk_index"), "embedded chunk index")
        texture_index = _tsv_integer(row.get("index"), "embedded texture index")
        scene = _text(row.get("scene_name"), "embedded scene name")
        scene_row = scene_rows.get(chunk_index)
        _require(scene_row is not None and scene_row.get("name") == scene,
                 f"Crib embedded scene {chunk_index}:{scene} has no owner row")
        material_text = row.get("mapped_material_names", "")
        materials = tuple(part for part in material_text.split("|") if part)
        label = " / ".join(materials) if materials else f"Texture {texture_index}"
        selector = f"crib_scene_texture:{scene}:{texture_index}"
        asset_id = (f"nfl2k5.crib.scene.c{chunk_index:04d}."
                    f"t{texture_index:03d}")
        editable = selector == BAR_MONITOR_SELECTOR and asset_id == BAR_MONITOR_ASSET_ID
        return CribAsset(
            asset_id=asset_id,
            selector=selector,
            label=f"{_title(scene)} — {label}",
            group=f"Scene Textures / {_title(scene)}",
            status=(CribAssetStatus.EDITABLE if editable
                    else CribAssetStatus.EXPORT_ONLY),
            storage=CribStorage.SCENE_EMBEDDED,
            authoring_note=(
                "Editable 128×128 Crib wall-screen texture. Paint the complete "
                "RGBA image; Mod Studio regenerates five P8 mips and safely "
                "recompresses the owning room scene. Very flat or heavily "
                "dithered/noisy art may exceed the scene's safe compression envelope."
                if editable else
                "Preview/Export-only: ownership is mapped, but this compressed "
                "SCNE texture does not yet have a reviewed import route."
            ),
            width=_tsv_integer(row.get("width"), "embedded texture width", minimum=1),
            height=_tsv_integer(row.get("height"), "embedded texture height", minimum=1),
            mip_levels=_tsv_integer(row.get("mip_levels"),
                                    "embedded texture mip count", minimum=1),
            format_name=_text(row.get("format_name"), "embedded texture format"),
            outer_index=4248,
            outer_id=_text(scene_row.get("outer_id"), "Crib scene outer ID"),
            outer_size=5_131_344,
            chunk_index=chunk_index,
            chunk_offset=_tsv_integer(scene_row.get("chunk_offset"),
                                      "Crib scene chunk offset"),
            stored_size=_tsv_integer(scene_row.get("stored_size"),
                                     "Crib scene stored size", minimum=1),
            system_bytes=_tsv_integer(scene_row.get("system_bytes"),
                                      "Crib scene system bytes", minimum=1),
            video_bytes=_tsv_integer(scene_row.get("video_bytes"),
                                     "Crib scene video bytes"),
            descriptor_offset=_tsv_integer(row.get("descriptor_offset"),
                                           "embedded descriptor offset"),
            pixel_offset=_tsv_integer(row.get("pixel_offset"),
                                      "embedded pixel offset"),
            palette_offset=_tsv_integer(row.get("palette_offset"),
                                        "embedded palette offset"),
            packed_format=_tsv_integer(row.get("packed_format"),
                                       "embedded packed format"),
            packed_size=_tsv_integer(row.get("packed_size"),
                                     "embedded packed size"),
            decoded_sha256=_sha(row.get("rgba_sha256"), "embedded texture RGBA hash"),
            rgba_sha256=_sha(row.get("rgba_sha256"), "embedded texture RGBA hash"),
            scene_name=scene,
            texture_index=texture_index,
            material_names=materials,
            resource_decoded_sha256=_sha(
                scene_row.get("decoded_sha256"), "Crib scene decoded hash"
            ),
        )

    def get(self, asset_id: str) -> CribAsset:
        try:
            return self._by_id[asset_id]
        except KeyError as exc:
            raise CribCatalogError(f"Unknown Crib asset: {asset_id}") from exc

    def by_selector(self, selector: str) -> CribAsset:
        try:
            return self._by_selector[selector]
        except KeyError as exc:
            raise CribCatalogError(f"Unknown Crib selector: {selector}") from exc

    @property
    def photos(self) -> tuple[CribAsset, ...]:
        return tuple(
            asset for asset in self.assets
            if asset.storage is CribStorage.TEAM_ITEM_AGGREGATE
            and PHOTO_NAME.fullmatch(asset.selector.split(":", 1)[-1]) is not None
        )

    @property
    def objects(self) -> tuple[CribAsset, ...]:
        return tuple(
            asset for asset in self.assets
            if not (
                asset.storage is CribStorage.TEAM_ITEM_AGGREGATE
                and PHOTO_NAME.fullmatch(
                    asset.selector.split(":", 1)[-1]
                ) is not None
            )
        )

    def search(self, query: str) -> tuple[CribAsset, ...]:
        needle = " ".join(query.replace("_", " ").split()).casefold()
        if not needle:
            return self.assets
        return tuple(
            asset for asset in self.assets
            if needle in " ".join((asset.label, asset.group, asset.selector,
                                    *asset.material_names)).replace("_", " ").casefold()
        )


SpanReader = Callable[[CribAsset], bytes]


def _atomic_write(path: Path, payload: bytes, *, replace: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(path) and not replace:
        raise ValidationError(f"A file already exists there: {path}")
    if path.is_symlink():
        raise ValidationError(f"Refusing to replace a symbolic link: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if not replace and os.path.lexists(path):
            raise ValidationError(f"A file appeared at the destination: {path}")
        os.replace(temporary, path)
        return path
    finally:
        temporary.unlink(missing_ok=True)


def _read_png(path: Path, dimensions: tuple[int, int]) -> tuple[bytes, bytes]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"Choose an existing PNG file: {path}") from exc
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise ValidationError("Choose a regular PNG file, not a folder or link")
    if path.suffix.lower() != ".png":
        raise ValidationError("Crib replacements need a PNG file")
    if not 0 < supplied.st_size <= MAX_PNG_BYTES:
        raise ValidationError("That PNG is empty or larger than the 32 MiB input limit")
    resolved = path.resolve(strict=True)
    payload = resolved.read_bytes()
    current = resolved.stat(follow_symlinks=False)
    if (current.st_dev, current.st_ino, current.st_size) != (
        supplied.st_dev,
        supplied.st_ino,
        supplied.st_size,
    ):
        raise ValidationError("That PNG changed while Mod Studio was reading it")
    try:
        width, height, rgba = palette_tools.decode_rgba_png(payload, dimensions)
    except ValueError as exc:
        raise ValidationError(
            f"This Crib asset needs an exact {dimensions[0]}×{dimensions[1]} "
            f"8-bit RGBA PNG with interlacing off. {exc}"
        ) from exc
    if (width, height) != dimensions:
        raise ValidationError(
            f"That image is {width}×{height}; it must stay "
            f"{dimensions[0]}×{dimensions[1]}."
        )
    return payload, rgba


def _generate_mips(rgba: bytes, width: int, height: int, count: int) \
        -> list[palette_tools.MipLevel]:
    if len(rgba) != width * height * 4 or count < 1:
        raise ValidationError("Crib photo base image or mip count is invalid")
    result = [palette_tools.MipLevel(0, width, height, rgba)]
    current = rgba
    current_width = width
    current_height = height
    for level in range(1, count):
        if current_width % 2 or current_height % 2:
            raise ValidationError("Crib photo mip dimensions cannot be halved")
        next_width = current_width // 2
        next_height = current_height // 2
        downsampled = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            for x in range(next_width):
                sources = (
                    ((y * 2) * current_width + x * 2) * 4,
                    ((y * 2) * current_width + x * 2 + 1) * 4,
                    (((y * 2) + 1) * current_width + x * 2) * 4,
                    (((y * 2) + 1) * current_width + x * 2 + 1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    total = sum(current[source + channel] for source in sources)
                    downsampled[target + channel] = (total + 2) // 4
        current = bytes(downsampled)
        current_width = next_width
        current_height = next_height
        result.append(
            palette_tools.MipLevel(level, current_width, current_height, current)
        )
    return result


class Nfl2k5CribIO:
    """Decode every catalog asset and compile bounded Team Photo replacements."""

    def __init__(
        self,
        cache: SourceCache,
        catalog: Nfl2k5CribCatalog,
        *,
        span_reader: SpanReader | None = None,
    ) -> None:
        self.cache = cache
        self.catalog = catalog
        self._span_reader = span_reader
        self._archive: Any | None = None

    @property
    def archive(self) -> Any:
        if self._archive is None:
            try:
                self._archive = parse_archive(self.cache.pack0)
            except (OSError, ValueError) as exc:
                raise ValidationError(f"Could not open the private game archive: {exc}") from exc
        return self._archive

    def _read_span(self, asset: CribAsset) -> bytes:
        if self._span_reader is not None:
            span = self._span_reader(asset)
        else:
            try:
                entry = self.archive.entries[asset.outer_index]
                if entry.name_id != int(asset.outer_id, 0) or entry.size != asset.outer_size:
                    raise ValidationError("The selected Crib container changed")
                span = read_entry_range(
                    self.archive,
                    entry,
                    asset.chunk_offset,
                    RESOURCE_HEADER_SIZE + asset.stored_size,
                )
            except ValidationError:
                raise
            except (OSError, ValueError, IndexError) as exc:
                raise ValidationError(f"Could not read {asset.label}: {exc}") from exc
        if len(span) != RESOURCE_HEADER_SIZE + asset.stored_size:
            raise ValidationError(f"The fixed span for {asset.label} has the wrong size")
        return span

    @staticmethod
    def _embedded_texture(asset: CribAsset) -> TextureInfo:
        return TextureInfo(
            name="|".join(asset.material_names) or asset.selector,
            name_offset=0,
            descriptor_offset=asset.descriptor_offset,
            pixel_offset=asset.pixel_offset,
            palette_offset=asset.palette_offset,
            packed_format=asset.packed_format,
            packed_size=asset.packed_size,
            descriptor_flags=0x80000000,
            dimensions=(asset.packed_format >> 4) & 0xF,
            format_code=(asset.packed_format >> 8) & 0xFF,
            format_name=asset.format_name,
            mip_levels=asset.mip_levels,
            width=asset.width,
            height=asset.height,
            depth=1,
        )

    def _decode_asset(
        self, asset: CribAsset
    ) -> tuple[bytes, Any, bytes, TextureInfo, bytes]:
        span = self._read_span(asset)
        chunks = parse_chunks(span)
        if len(chunks) != 1:
            raise ValidationError(f"{asset.label} is not one bounded resource")
        chunk = chunks[0]
        if (
            chunk.stored_size != asset.stored_size
            or chunk.system_bytes != asset.system_bytes
            or chunk.video_bytes != asset.video_bytes
        ):
            raise ValidationError(f"The wrapper for {asset.label} changed")
        decoded, _info = decode_chunk(span, chunk)
        expected_decoded = (
            asset.resource_decoded_sha256
            if asset.storage is CribStorage.SCENE_EMBEDDED
            else asset.decoded_sha256
        )
        if expected_decoded is not None and _sha256(decoded) != expected_decoded:
            raise ValidationError(f"The decoded resource for {asset.label} changed")
        if asset.storage is CribStorage.SCENE_EMBEDDED:
            if chunk.kind != "SCNE":
                raise ValidationError(f"{asset.label} is no longer inside a SCNE")
            texture = self._embedded_texture(asset)
        else:
            if chunk.kind != "TXTR":
                raise ValidationError(f"{asset.label} is no longer a TXTR")
            texture = parse_texture(decoded, chunk)
            if (
                texture.descriptor_offset != asset.descriptor_offset
                or texture.pixel_offset != asset.pixel_offset
                or texture.palette_offset != asset.palette_offset
                or texture.packed_format != asset.packed_format
                or texture.packed_size != asset.packed_size
                or texture.width != asset.width
                or texture.height != asset.height
                or texture.mip_levels != asset.mip_levels
                or texture.format_name != asset.format_name
            ):
                raise ValidationError(f"The texture descriptor for {asset.label} changed")
        rgba = texture_to_rgba(decoded, chunk, texture)
        if _sha256(rgba) != asset.rgba_sha256:
            raise ValidationError(f"The pixels for {asset.label} differ from the catalog")
        return span, chunk, decoded, texture, rgba

    def original_path(self, asset: CribAsset) -> Path:
        key = hashlib.sha256(asset.asset_id.encode("utf-8")).hexdigest()
        return self.cache.originals / f"{key}.png"

    def ensure_original(self, asset: CribAsset) -> Path:
        path = self.original_path(asset)
        metadata = path.with_suffix(".json")
        if path.is_file() and metadata.is_file() and not path.is_symlink() \
                and not metadata.is_symlink():
            try:
                payload = path.read_bytes()
                width, height, rgba = palette_tools.decode_rgba_png(
                    payload, asset.dimensions
                )
                record = json.loads(metadata.read_text(encoding="utf-8"))
                if (
                    record.get("schema") == ORIGINAL_SCHEMA
                    and record.get("asset_id") == asset.asset_id
                    and record.get("source_sha256") == self.cache.source.sha256
                    and record.get("png_sha256") == _sha256(payload)
                    and record.get("rgba_sha256") == _sha256(rgba)
                    and (width, height) == asset.dimensions
                ):
                    return path
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            raise ValidationError(
                "A private Crib original changed outside Mod Studio. "
                "Remove the source cache and load the XISO again."
            )
        _span, _chunk, _decoded, _texture, rgba = self._decode_asset(asset)
        png = encode_rgba_png(asset.width, asset.height, rgba)
        try:
            reparsed = palette_tools.decode_rgba_png(png, asset.dimensions)
        except ValueError as exc:
            raise ValidationError("Exported Crib PNG failed its strict recheck") from exc
        if reparsed != (asset.width, asset.height, rgba):
            raise ValidationError("Exported Crib PNG failed its pixel round-trip")
        _atomic_write(path, png)
        record = {
            "asset_id": asset.asset_id,
            "dimensions": [asset.width, asset.height],
            "png_sha256": _sha256(png),
            "rgba_sha256": _sha256(rgba),
            "schema": ORIGINAL_SCHEMA,
            "source_sha256": self.cache.source.sha256,
        }
        _atomic_write(
            metadata,
            (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        return path

    def export_original(
        self, asset: CribAsset, destination: Path, *, replace: bool = False
    ) -> Path:
        original = self.ensure_original(asset)
        requested = destination.expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        _atomic_write(requested, original.read_bytes(), replace=replace)
        return requested.resolve(strict=True)

    @staticmethod
    def validate_replacement(asset: CribAsset, path: Path) -> tuple[bytes, bytes]:
        if not asset.editable:
            raise ValidationError(
                f"{asset.label} is Preview/Export-only; replacement is Coming Soon"
            )
        return _read_png(path.expanduser(), asset.dimensions)

    def compile_photo(
        self, asset: CribAsset, png_path: Path
    ) -> CompiledCribPhotoPatch:
        """Compile and independently decode one fixed-allocation photo span."""

        if (
            not asset.editable
            or asset.storage is not CribStorage.TEAM_ITEM_AGGREGATE
            or asset.span_sha256 is None
            or asset.xiso_absolute_offset is None
            or asset.format_name != "P8"
            or asset.dimensions != (128, 128)
            or asset.mip_levels != 5
        ):
            raise ValidationError(f"{asset.label} is not a writable Crib Team Photo")
        _png, rgba = self.validate_replacement(asset, png_path)
        span, chunk, decoded, texture, _original_rgba = self._decode_asset(asset)
        if _sha256(span) != asset.span_sha256 or chunk.compressed:
            raise ValidationError("The Crib Team Photo template changed")
        if (
            asset.pixel_offset != 0
            or asset.palette_offset != 21_824
            or asset.system_bytes != 128
            or asset.video_bytes != 22_848
            or asset.stored_size != 22_976
            or len(span) != 23_008
        ):
            raise ValidationError("The Crib Team Photo fixed layout changed")

        levels = _generate_mips(rgba, asset.width, asset.height, asset.mip_levels)
        expected_dimensions = ((128, 128), (64, 64), (32, 32), (16, 16), (8, 8))
        if tuple((level.width, level.height) for level in levels) != expected_dimensions:
            raise ValidationError("The Crib Team Photo mip dimensions changed")
        palette, linear_levels, _quantization = palette_tools.quantize_levels(levels)
        swizzled_levels = [
            swizzle_2d(indices, level.width, level.height, 1)
            for indices, level in zip(linear_levels, levels)
        ]
        index_chain = b"".join(swizzled_levels)
        palette_bgra = palette_tools.palette_bytes(palette)
        if len(index_chain) != asset.palette_offset or len(palette_bgra) != 1_024:
            raise ValidationError("The Crib Team Photo P8 allocation changed")
        rebuilt_decoded = (
            decoded[:asset.system_bytes] + index_chain + palette_bgra
        )
        if len(rebuilt_decoded) != len(decoded):
            raise ValidationError("The Crib Team Photo rebuild changed allocation")
        rebuilt_span = span[:RESOURCE_HEADER_SIZE] + rebuilt_decoded
        if len(rebuilt_span) != len(span):
            raise ValidationError("The Crib Team Photo rebuild changed span size")

        rebuilt_chunks = parse_chunks(rebuilt_span)
        if len(rebuilt_chunks) != 1:
            raise ValidationError("The rebuilt Crib Team Photo wrapper is invalid")
        rebuilt_chunk = rebuilt_chunks[0]
        roundtrip, info = decode_chunk(rebuilt_span, rebuilt_chunk)
        rebuilt_texture = parse_texture(roundtrip, rebuilt_chunk)
        if (
            info is not None
            or roundtrip[:asset.system_bytes] != decoded[:asset.system_bytes]
            or rebuilt_texture != texture
        ):
            raise ValidationError("The rebuilt Crib Team Photo changed metadata")

        palette_roundtrip = [
            (palette_bgra[index * 4 + 2], palette_bgra[index * 4 + 1],
             palette_bgra[index * 4], palette_bgra[index * 4 + 3])
            for index in range(256)
        ]
        cursor = 0
        decoded_levels: list[bytes] = []
        for level, expected_indices in zip(levels, linear_levels):
            size = level.width * level.height
            indices = unswizzle_2d(
                index_chain[cursor:cursor + size], level.width, level.height, 1
            )
            if indices != expected_indices:
                raise ValidationError("A rebuilt Crib Team Photo mip failed swizzle round-trip")
            decoded_levels.append(
                b"".join(bytes(palette_roundtrip[index]) for index in indices)
            )
            cursor += size
        if cursor != asset.palette_offset:
            raise ValidationError("The rebuilt Crib Team Photo mip chain is incomplete")
        base_rgba = texture_to_rgba(roundtrip, rebuilt_chunk, rebuilt_texture)
        if base_rgba != decoded_levels[0]:
            raise ValidationError("The rebuilt Crib Team Photo base image differs")
        preview = encode_rgba_png(asset.width, asset.height, base_rgba)
        if palette_tools.decode_rgba_png(preview, asset.dimensions) != (
            asset.width, asset.height, base_rgba
        ):
            raise ValidationError("The rebuilt Crib Team Photo preview failed reparse")

        changed = sum(left != right for left, right in zip(span, rebuilt_span))
        if any(
            span[index] != rebuilt_span[index]
            for index in range(RESOURCE_HEADER_SIZE + asset.system_bytes)
        ):
            raise ValidationError("The Crib Team Photo rebuild escaped its video bytes")
        return CompiledCribPhotoPatch(
            asset_id=asset.asset_id,
            selector=asset.selector,
            absolute_xiso_offset=asset.xiso_absolute_offset,
            expected_original_span_sha256=asset.span_sha256,
            replacement_span_sha256=_sha256(rebuilt_span),
            replacement_rgba_sha256=_sha256(base_rgba),
            replacement_span=rebuilt_span,
            preview_png=preview,
            changed_byte_count=changed,
        )


def load_nfl2k5_crib_catalog() -> Nfl2k5CribCatalog:
    if COMPACT_CATALOG_PATH.is_file():
        return Nfl2k5CribCatalog.from_compact_catalog()
    return Nfl2k5CribCatalog.from_reports()


__all__ = [
    "BAR_MONITOR_ASSET_ID",
    "BAR_MONITOR_SELECTOR",
    "CAPABILITY_ID",
    "COMPACT_CATALOG_PATH",
    "COMPACT_CATALOG_SCHEMA",
    "CompiledCribPhotoPatch",
    "CribAsset",
    "CribAssetStatus",
    "CribCatalogError",
    "CribCatalogExpectations",
    "CribReportPaths",
    "CribStorage",
    "Nfl2k5CribCatalog",
    "Nfl2k5CribIO",
    "PRODUCTION_EXPECTATIONS",
    "load_nfl2k5_crib_catalog",
]
