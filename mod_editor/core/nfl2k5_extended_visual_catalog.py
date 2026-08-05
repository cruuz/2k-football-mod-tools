"""Product metadata for NFL 2K5's extended visual surfaces.

Writable research families discard physical archive offsets at this boundary
and keep only stable named selectors, dimensions, labels, and provider routes.
The package-local uniform-equipment family keeps exact TSET offsets and source
hashes in pinned, retail-payload-free metadata. Reviewed swizzled P8 records are
palette-importable through one fixed-span project writer. An unproved format
stays preview/export-only instead of inheriting that capability by association.

Three families (player portraits, live face/head textures, and create-team
field art) are accepted by the unified visual provider.  Scorebug textures use
the separate typed scorebug provider.  Keeping that routing explicit prevents
the GUI from accidentally putting a scorebug edit into a unified-project JSON
that cannot consume it.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable, Mapping

from .errors import ValidationError
from .nfl2k5_uniform_catalog import (
    Nfl2k5UniformCatalog,
    load_nfl2k5_uniform_catalog,
)
from .recipes import ScorebugRecipeEdit


ROOT = Path(__file__).resolve().parents[2]
UNIFIED_CAPABILITY_ID = "nfl2k5.uniforms.all_visual"
SCOREBUG_CAPABILITY_ID = "nfl2k5.scorebug_presentation.inventory"


class ExtendedVisualCatalogError(ValidationError):
    """A visual report or logical selector failed its product boundary."""


class VisualWriterRoute(str, Enum):
    """The typed project family which owns one visual replacement."""

    UNIFIED_VISUAL = "unified_visual"
    SCOREBUG = "scorebug"
    EXPORT_ONLY = "export_only"


@dataclass(frozen=True, slots=True)
class VisualReportPaths:
    portraits: Path = ROOT / "reports/assets/nfl2k5_player_portrait_compatibility.json"
    live_faces: Path = ROOT / "reports/assets/nfl2k5_live_face_texture_compatibility.json"
    field_art: Path = ROOT / "reports/assets/nfl2k5_create_team_field_art_inventory.json"
    scorebug: Path = ROOT / "reports/assets/scorebug_presentation_audit.json"
    p8_textures: Path = ROOT / "reports/assets/nfl2k5_p8_texture_inventory.json"
    uniform_equipment: Path = (
        ROOT / "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json"
    )


@dataclass(frozen=True, slots=True)
class VisualCatalogExpectations:
    """Report counts pinned by the currently proved writer surface.

    Tests may supply a smaller explicit instance for retail-free synthetic
    reports.  Product callers use :data:`PRODUCTION_EXPECTATIONS`.
    """

    portrait_count: int
    face_selector_count: int
    face_resource_count: int
    field_package_count: int
    field_texture_count: int
    scorebug_count: int
    p8_texture_count: int = 0
    uniform_equipment_count: int = 0


PRODUCTION_EXPECTATIONS = VisualCatalogExpectations(
    portrait_count=4_303,
    face_selector_count=624,
    face_resource_count=1_872,
    field_package_count=126,
    field_texture_count=1_134,
    scorebug_count=3,
    p8_texture_count=11_395,
    uniform_equipment_count=28_530,
)

UNIFORM_EQUIPMENT_CATALOG_SIZE = 5_851_450
UNIFORM_EQUIPMENT_CATALOG_SHA256 = (
    "fa2c9ca9bcc267b6981735347bf6daf6243d6ab8b83fba268804c280cfd94173"
)
UNIFORM_EQUIPMENT_CATALOG_SCHEMA = (
    "nfl2k5_uniform_equipment_export_catalog/v1"
)
_UNIFORM_EQUIPMENT_COLUMNS = (
    "outer_index",
    "set_selector",
    "tset_chunk_index",
    "reference_index",
    "name",
    "width",
    "height",
    "pixel_offset",
    "palette_offset",
    "packed_format",
    "packed_size",
    "descriptor_flags",
    "base_pixel_sha256",
    "palette_bgra_sha256",
)


_FOUR_DIGITS = re.compile(r"^[0-9]{4}$", re.ASCII)
_EQUIPMENT_NAME = re.compile(
    r"^(socks|elbowpad|glove|longsleeve|shoes|wristband)([0-9]{2})(_mud)?$",
    re.ASCII,
)
_EQUIPMENT_LABELS = {
    "socks": "Socks",
    "elbowpad": "Elbow Pad",
    "glove": "Glove",
    "longsleeve": "Long Sleeve",
    "shoes": "Shoes",
    "wristband": "Wristband",
}
_FIELD_TEXTURES: Mapping[str, tuple[int, int, str]] = {
    "center_logo": (256, 256, "Midfield Logo"),
    "endzone_north_left": (256, 128, "North End Zone — Left"),
    "endzone_north_middle": (256, 128, "North End Zone — Middle"),
    "endzone_north_right": (256, 128, "North End Zone — Right"),
    "endzone_south_left": (256, 128, "South End Zone — Left"),
    "endzone_south_middle": (256, 128, "South End Zone — Middle"),
    "endzone_south_right": (256, 128, "South End Zone — Right"),
    "pad_north": (128, 128, "North Goalpost Pad"),
    "pad_south": (128, 128, "South Goalpost Pad"),
}
_WEATHERS = {"D": "Dry", "R": "Rain", "S": "Snow"}
_FACE_FAMILIES = {
    "f": ("Face / Eye Texture", "Face Textures"),
    "h": ("Alternate Face Texture", "Alternate Face Textures"),
    "n": ("Neck / Skull Texture", "Neck & Skull Textures"),
}
_TEAM_PRESENTATION_FAMILIES = {
    "menu_logo_large": "Full-size menu team logo",
    "menu_logo_small": "Compact menu team logo",
    "menu_flipchip": "Shared menu flip chip",
    "menu_mini_card": "Compact side-specific team card",
    "franchise_team_logo": "Franchise office team logo",
    "draft_pda_logo": "Draft/PDA team logo",
}
_SCOREBUG = {
    "score_buga": (
        64,
        64,
        "Field Scorebug Frame Atlas",
        "Visible in xemu gameplay; fixed P8 allocation.",
    ),
    "shield_espn": (
        128,
        64,
        "ESPN Scorebug Strip",
        "Visible in xemu gameplay; fixed P8 allocation.",
    ),
    "digital_font": (
        128,
        128,
        "Shared Digital Font Atlas",
        "Editable, but visibility is not yet proved and changes may affect UI outside the scorebug.",
    ),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExtendedVisualCatalogError(message)


def _path_text(path: str | os.PathLike[str]) -> str:
    try:
        value = os.fspath(path)
    except TypeError as exc:
        raise ExtendedVisualCatalogError(
            "Replacement PNG path must be a string or path"
        ) from exc
    _require(isinstance(value, str), "Replacement PNG path must be text")
    _require(bool(value) and "\0" not in value, "Replacement PNG path cannot be empty")
    return value


def _read_report(path: Path, schema: str, label: str) -> dict[str, Any]:
    requested = path.expanduser()
    try:
        supplied = requested.lstat()
    except FileNotFoundError as exc:
        raise ExtendedVisualCatalogError(f"{label} report is missing: {requested}") from exc
    _require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        f"{label} report must be a regular, non-link file",
    )
    _require(0 < supplied.st_size <= 64 * 1024 * 1024,
             f"{label} report size is outside the allowed range")
    resolved = requested.resolve(strict=True)
    try:
        payload = resolved.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExtendedVisualCatalogError(f"Could not read {label} report: {exc}") from exc
    current = resolved.stat(follow_symlinks=False)
    _require(
        (current.st_dev, current.st_ino, current.st_size)
        == (supplied.st_dev, supplied.st_ino, supplied.st_size),
        f"{label} report changed while it was read",
    )
    _require(isinstance(value, dict) and value.get("schema") == schema,
             f"{label} report schema is unsupported")
    return value


def _read_uniform_equipment_catalog(path: Path) -> dict[str, Any]:
    """Read the compact reviewed export-only catalog with exact identity."""

    requested = path.expanduser()
    try:
        supplied = requested.lstat()
    except FileNotFoundError as exc:
        raise ExtendedVisualCatalogError(
            f"Uniform equipment export catalog is missing: {requested}"
        ) from exc
    _require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        "Uniform equipment export catalog must be a regular, non-link file",
    )
    _require(
        supplied.st_size == UNIFORM_EQUIPMENT_CATALOG_SIZE,
        "Uniform equipment export catalog size changed",
    )
    resolved = requested.resolve(strict=True)
    payload = resolved.read_bytes()
    current = resolved.stat(follow_symlinks=False)
    _require(
        (current.st_dev, current.st_ino, current.st_size)
        == (supplied.st_dev, supplied.st_ino, supplied.st_size),
        "Uniform equipment export catalog changed while it was read",
    )
    _require(
        hashlib.sha256(payload).hexdigest()
        == UNIFORM_EQUIPMENT_CATALOG_SHA256,
        "Uniform equipment export catalog hash changed",
    )
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExtendedVisualCatalogError(
            f"Uniform equipment export catalog is not valid JSON: {exc}"
        ) from exc
    _require(
        isinstance(value, dict)
        and value.get("schema") == UNIFORM_EQUIPMENT_CATALOG_SCHEMA,
        "Uniform equipment export catalog schema is unsupported",
    )
    return value


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _equipment_friendly_name(name: str) -> str:
    match = _EQUIPMENT_NAME.fullmatch(name)
    _require(match is not None, f"Unknown uniform equipment texture name: {name}")
    family, number, mud = match.groups()
    label = f"{_EQUIPMENT_LABELS[family]} {number}"
    return f"{label} — Mud" if mud else label


def _portrait_owners(report: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    owners: dict[str, list[str]] = {}
    rows = report.get("roster_selector_mapping", [])
    _require(isinstance(rows, list), "Portrait roster selector map must be a list")
    for row in rows:
        if not isinstance(row, dict) or row.get("portrait_present") is not True:
            continue
        portrait_id = row.get("portrait_resource_name")
        if not isinstance(portrait_id, str) or _FOUR_DIGITS.fullmatch(portrait_id) is None:
            continue
        first = row.get("first_name")
        last = row.get("last_name")
        name = " ".join(
            value.strip() for value in (first, last)
            if isinstance(value, str) and value.strip()
        )
        team_names = row.get("team_names")
        terms = [name]
        if isinstance(team_names, str):
            terms.extend(part.strip() for part in team_names.split(";") if part.strip())
        bucket = owners.setdefault(portrait_id, [])
        for term in terms:
            if term and term not in bucket:
                bucket.append(term)
    return {key: tuple(value) for key, value in owners.items()}


@dataclass(frozen=True, slots=True)
class UniformEquipmentDescriptor:
    """Private physical selector used only to decode a reviewed export target."""

    outer_index: int
    chunk_index: int
    reference_index: int
    pixel_offset: int
    palette_offset: int
    packed_format: int
    packed_size: int
    descriptor_flags: int
    base_pixel_sha256: str
    palette_bgra_sha256: str


@dataclass(frozen=True, slots=True)
class ExtendedVisualAsset:
    """One safely named, PNG-backed NFL 2K5 visual target."""

    asset_id: str
    label: str
    group: str
    kind: str
    target_selector: str
    width: int
    height: int
    writer_route: VisualWriterRoute
    capability_id: str
    replacement_supported: bool = True
    search_terms: tuple[str, ...] = ()
    authoring_note: str = ""
    portrait_id: str | None = None
    face_id: str | None = None
    family: str | None = None
    logo_code: int | None = None
    weather: str | None = None
    texture: str | None = None
    scorebug_target: str | None = None
    presentation_family: str | None = None
    asset_code: str | None = None
    style: int | None = None
    set_selectors: tuple[str, ...] = ()
    outer_name: str | None = None
    consumer_scope: str = ""
    equipment_descriptor: UniformEquipmentDescriptor | None = dataclass_field(
        default=None, repr=False
    )

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.width, self.height

    @property
    def editable(self) -> bool:
        return self.replacement_supported

    def provider_edit(self, png_path: str | os.PathLike[str]) -> dict[str, Any]:
        """Return one logical, retail-byte-free unified-provider edit."""

        _require(
            self.editable,
            f"{self.label} is preview/export-only because its texture format "
            "has no proved fixed-span importer",
        )
        png = _path_text(png_path)
        if self.writer_route is VisualWriterRoute.SCOREBUG:
            _require(
                self.kind == "scorebug_texture"
                and self.scorebug_target in _SCOREBUG,
                "Scorebug catalog selector is missing",
            )
            return {
                "kind": "scorebug_texture",
                "png": png,
                "target": self.scorebug_target,
            }
        if self.writer_route is not VisualWriterRoute.UNIFIED_VISUAL:
            raise ExtendedVisualCatalogError(f"Unsupported writer route: {self.writer_route}")
        if self.kind == "player_portrait":
            _require(self.portrait_id is not None, "Portrait catalog selector is missing")
            return {"kind": "player_portrait", "png": png,
                    "portrait_id": self.portrait_id}
        if self.kind == "live_face":
            _require(self.face_id is not None and self.family in _FACE_FAMILIES,
                     "Live face catalog selector is missing")
            return {"face_id": self.face_id, "family": self.family,
                    "kind": "live_face", "png": png}
        if self.kind == "create_team_field_art":
            _require(
                self.logo_code is not None and self.weather in _WEATHERS
                and self.texture in _FIELD_TEXTURES,
                "Create-team field-art catalog selector is missing",
            )
            return {
                "kind": "create_team_field_art",
                "logo_code": self.logo_code,
                "png": png,
                "texture": self.texture,
                "weather": self.weather,
            }
        if self.kind == "p8_texture":
            _require(self.texture is not None and self.target_selector,
                     "P8 texture catalog selector is missing")
            return {"asset_id": self.target_selector, "kind": "p8_texture",
                    "png": png}
        if self.kind == "uniform_equipment_texture":
            descriptor = self.equipment_descriptor
            _require(
                descriptor is not None
                and self.target_selector == self.asset_id
                and ((descriptor.packed_format >> 8) & 0xFF) == 0x0B
                and descriptor.packed_size == 0,
                "Uniform-equipment P8 selector is missing or unsupported",
            )
            return {
                "asset_id": self.target_selector,
                "kind": "uniform_equipment_texture",
                "png": png,
            }
        raise ExtendedVisualCatalogError(f"Unsupported visual kind: {self.kind}")

    def scorebug_recipe_edit(self, png_path: str | os.PathLike[str]) -> ScorebugRecipeEdit:
        """Return the existing typed scorebug recipe adapter for this asset."""

        png = _path_text(png_path)
        if self.writer_route is not VisualWriterRoute.SCOREBUG \
                or self.scorebug_target not in _SCOREBUG:
            raise ExtendedVisualCatalogError(
                f"{self.label} belongs to the unified visual build route"
            )
        return ScorebugRecipeEdit(self.scorebug_target, Path(png))


class Nfl2k5ExtendedVisualCatalog:
    """Immutable catalog of proved writers plus bounded export-only visuals."""

    def __init__(self, assets: Iterable[ExtendedVisualAsset],
                 report_paths: VisualReportPaths) -> None:
        self.assets = tuple(assets)
        self.report_paths = report_paths
        self._by_id = {asset.asset_id: asset for asset in self.assets}
        _require(len(self.assets) == len(self._by_id),
                 "Extended visual asset IDs are duplicated")

    @classmethod
    def from_reports(
        cls,
        report_paths: VisualReportPaths = VisualReportPaths(),
        *,
        expectations: VisualCatalogExpectations = PRODUCTION_EXPECTATIONS,
    ) -> "Nfl2k5ExtendedVisualCatalog":
        portraits = _read_report(
            report_paths.portraits,
            "nfl2k5_player_portrait_compatibility/v1",
            "Player portrait",
        )
        faces = _read_report(
            report_paths.live_faces,
            "nfl2k5_live_face_texture_compatibility/v1",
            "Live face",
        )
        field = _read_report(
            report_paths.field_art,
            "nfl2k5_create_team_field_art_inventory/v1",
            "Create-team field art",
        )
        scorebug = _read_report(
            report_paths.scorebug,
            "vc_scorebug_presentation_audit/v1",
            "Scorebug",
        )
        # Retail-free tests build the other four families from synthetic
        # reports and have no standalone-P8 inventory to point at. Expecting
        # zero of them is how such a catalog says "not this family", so do not
        # demand the report in that case.
        p8: dict[str, Any] = {"targets": []}
        if expectations.p8_texture_count:
            p8 = _read_report(
                report_paths.p8_textures,
                "nfl2k5_p8_texture_inventory/v1",
                "Standalone P8 texture",
            )
        equipment: dict[str, Any] = {"rows": []}
        if expectations.uniform_equipment_count:
            equipment = _read_uniform_equipment_catalog(
                report_paths.uniform_equipment
            )
        owners = _portrait_owners(portraits)
        assets = [
            *cls._portrait_assets(portraits, owners, expectations),
            *cls._face_assets(faces, owners, expectations),
            *cls._field_assets(field, expectations),
            *cls._scorebug_assets(scorebug, expectations),
            *cls._p8_texture_assets(p8, expectations),
            *cls._uniform_equipment_assets(equipment, expectations),
        ]
        return cls(assets, report_paths)

    @staticmethod
    def _uniform_equipment_assets(
        report: dict[str, Any],
        expectations: VisualCatalogExpectations,
    ) -> list[ExtendedVisualAsset]:
        """Package-local equipment with a bounded P8 palette writer."""

        if expectations.uniform_equipment_count == 0:
            return []
        rows = report.get("rows") or []
        columns = report.get("columns")
        summary = report.get("summary")
        contract = report.get("contract")
        _require(
            columns == list(_UNIFORM_EQUIPMENT_COLUMNS),
            "Uniform equipment export catalog columns changed",
        )
        _require(
            isinstance(rows, list)
            and len(rows) == expectations.uniform_equipment_count
            and summary == {
                "package_count": 634,
                "target_count": expectations.uniform_equipment_count,
                "targets_per_package": 45,
            },
            "Uniform equipment export catalog count changed",
        )
        _require(
            isinstance(contract, dict)
            and contract.get("access") == "preview-export-and-palette-import"
            and contract.get("import_mode") == "fixed-shared-index-palette"
            and contract.get("import_supported") is True
            and contract.get("retail_payload_bytes") is False,
            "Uniform equipment catalog contract changed",
        )
        uniform_catalog = load_nfl2k5_uniform_catalog()
        group_by_chunk = {
            4: "Uniform Equipment — Socks",
            5: "Uniform Equipment — Elbow Pads",
            6: "Uniform Equipment — Gloves",
            7: "Uniform Equipment — Long Sleeves",
            8: "Uniform Equipment — Shoes 1 / 4 / 9",
            9: "Uniform Equipment — Shoes 2 / 3 / 10",
            10: "Uniform Equipment — Wristbands",
        }
        assets: list[ExtendedVisualAsset] = []
        seen: set[tuple[int, int, int]] = set()
        for number, raw in enumerate(rows, 1):
            _require(
                isinstance(raw, list) and len(raw) == len(_UNIFORM_EQUIPMENT_COLUMNS),
                f"Uniform equipment row {number} has the wrong shape",
            )
            row = dict(zip(_UNIFORM_EQUIPMENT_COLUMNS, raw))
            outer = row["outer_index"]
            selector = row["set_selector"]
            chunk = row["tset_chunk_index"]
            reference = row["reference_index"]
            name = row["name"]
            _require(
                type(outer) is int and type(chunk) is int and type(reference) is int
                and isinstance(selector, str) and isinstance(name, str)
                and chunk in group_by_chunk,
                f"Uniform equipment row {number} selector is invalid",
            )
            key = (outer, chunk, reference)
            _require(key not in seen, f"Uniform equipment selector {key} is duplicated")
            seen.add(key)
            uniform_set = uniform_catalog.get_uniform_set(selector)
            owner = " / ".join(uniform_set.team_names) or f"Asset {uniform_set.asset_code}"
            friendly = _equipment_friendly_name(name)
            asset_id = f"tset:{outer}:{chunk}:{reference}:{name}"
            packed_format = int(row["packed_format"])
            editable = (
                ((packed_format >> 8) & 0xFF) == 0x0B
                and int(row["packed_size"]) == 0
                and int(row["pixel_offset"]) == 0
            )
            assets.append(ExtendedVisualAsset(
                asset_id=asset_id,
                label=f"{friendly} — {owner} {uniform_set.side_name.title()}",
                group=group_by_chunk[chunk],
                kind="uniform_equipment_texture",
                target_selector=asset_id,
                width=int(row["width"]),
                height=int(row["height"]),
                writer_route=(
                    VisualWriterRoute.UNIFIED_VISUAL
                    if editable else VisualWriterRoute.EXPORT_ONLY
                ),
                capability_id="nfl2k5.textures.all_p8",
                replacement_supported=editable,
                search_terms=_ordered_unique((
                    selector,
                    name,
                    friendly,
                    owner,
                    *uniform_set.team_names,
                    *uniform_set.team_abbreviations,
                    *uniform_set.historic_abbreviations,
                )),
                authoring_note=(
                    "Editable P8 palette inside its exact package-local TSET "
                    "span. Import keeps the retail shared shape/mip indices and "
                    "every sibling texture exact; highly detailed art may be "
                    "reduced to fewer colours to fit."
                    if editable else
                    "Preview and Export PNG are available. This texture format "
                    "has no proved fixed-span importer, so Replace, Edit, "
                    "drag/drop, and Revert remain disabled."
                ),
                texture=name,
                equipment_descriptor=UniformEquipmentDescriptor(
                    outer_index=outer,
                    chunk_index=chunk,
                    reference_index=reference,
                    pixel_offset=int(row["pixel_offset"]),
                    palette_offset=int(row["palette_offset"]),
                    packed_format=packed_format,
                    packed_size=int(row["packed_size"]),
                    descriptor_flags=int(row["descriptor_flags"]),
                    base_pixel_sha256=str(row["base_pixel_sha256"]),
                    palette_bgra_sha256=str(row["palette_bgra_sha256"]),
                ),
            ))
        return assets

    @staticmethod
    def _p8_texture_assets(
        report: dict[str, Any],
        expectations: VisualCatalogExpectations,
    ) -> list[ExtendedVisualAsset]:
        """The standalone TXTR corpus: fields, equipment, and presentation art.

        Deliberately distinct from Stadium Studio, which edits textures
        embedded inside SCNE scenes. These sit beside those scenes as their own
        chunks and had no workspace at all until now.
        """
        rows = report.get("targets") or []
        _require(
            len(rows) == expectations.p8_texture_count,
            "Standalone P8 texture inventory count changed",
        )
        assets: list[ExtendedVisualAsset] = []
        for row in rows:
            asset_id = str(row["asset_id"])
            texture = str(row["texture"])
            outer = int(row["outer_index"])
            presentation_family = str(row.get("presentation_family") or "")
            is_uniform_presentation = texture in {
                "logo", "chiclet", "splayer", "flipchip",
            }
            is_team_presentation = (
                is_uniform_presentation or bool(presentation_family)
            )
            set_selector = str(row.get("set_selector") or "")
            team_names = str(row.get("team_names") or "")
            team_abbreviations = str(row.get("team_abbreviations") or "")
            historic_abbreviations = str(
                row.get("historic_abbreviations") or ""
            )
            style_display = str(row.get("style_display") or "")
            if is_uniform_presentation:
                _require(
                    re.fullmatch(r"[0-9]{2}[HA][0-9]{1,2}", set_selector)
                    is not None,
                    f"Presentation texture {asset_id} has no uniform selector",
                )
            asset_code = str(row.get("asset_code") or "")
            style_value = row.get("style")
            style = int(style_value) if type(style_value) is int else None
            set_selectors_value = row.get("set_selectors") or []
            _require(
                isinstance(set_selectors_value, list)
                and all(isinstance(value, str) for value in set_selectors_value),
                f"Presentation texture {asset_id} has invalid uniform-set owners",
            )
            set_selectors = tuple(set_selectors_value)
            outer_name = str(row.get("outer_name") or "")
            consumer_scope = str(row.get("consumer_scope") or "")
            if presentation_family:
                expected_group = (
                    "Team Mini Cards — Menus / Presentation"
                    if presentation_family == "menu_mini_card" else
                    "Franchise & Draft Presentation"
                    if presentation_family in {
                        "franchise_team_logo", "draft_pda_logo",
                    } else
                    "Team Logos — Menus / Presentation"
                )
                _require(
                    presentation_family in _TEAM_PRESENTATION_FAMILIES
                    and str(row["group"]) == expected_group
                    and re.fullmatch(r"[0-9]{2}", asset_code) is not None
                    and outer_name
                    and consumer_scope,
                    f"Menu presentation texture {asset_id} lost its typed owner",
                )
                if presentation_family.startswith("menu_"):
                    _require(
                        style is not None
                        and len(set_selectors) == 2
                        and all(
                            re.fullmatch(rf"{asset_code}[HA]{style}", selector)
                            is not None
                            for selector in set_selectors
                        ),
                        f"Menu presentation texture {asset_id} lost its team/style join",
                    )
                else:
                    _require(
                        style is None and set_selector == asset_code,
                        f"Franchise presentation texture {asset_id} has a false uniform owner",
                    )
                if presentation_family == "menu_mini_card":
                    _require(
                        set_selector in set_selectors,
                        f"Mini-card texture {asset_id} lost its side selector",
                    )
            owner = team_names or (
                f"Team asset {asset_code}" if presentation_family
                else f"Uniform {set_selector}"
            )
            editable = row.get("replacement_supported", True) is True
            label = (
                f"{row['label']} — {owner} — {set_selector}"
                if is_team_presentation else
                f"{row['label']} — package {outer}"
            )
            family_aliases: tuple[str, ...] = ()
            if presentation_family:
                aliases = {
                    "menu_logo_large": (
                        "menu logo", "frontend logo", "full team logo",
                    ),
                    "menu_logo_small": (
                        "menu logo", "frontend logo", "compact team logo",
                    ),
                    "menu_flipchip": (
                        "flipchip", "menu lineup", "playoff picture",
                    ),
                    "menu_mini_card": (
                        "mini helmet", "mini card", "online user card",
                    ),
                    "franchise_team_logo": (
                        "franchise logo", "coach desk", "team logo",
                    ),
                    "draft_pda_logo": (
                        "draft logo", "pda logo", "franchise draft",
                    ),
                }
                family_aliases = aliases[presentation_family]
            assets.append(ExtendedVisualAsset(
                asset_id=asset_id,
                label=label,
                group=str(row["group"]),
                kind="p8_texture",
                target_selector=asset_id,
                width=int(row["width"]),
                height=int(row["height"]),
                writer_route=(
                    VisualWriterRoute.UNIFIED_VISUAL
                    if editable else VisualWriterRoute.EXPORT_ONLY
                ),
                capability_id="nfl2k5.textures.all_p8",
                replacement_supported=editable,
                search_terms=(
                    texture,
                    str(row["group"]),
                    str(outer),
                    str(row["label"]),
                    set_selector,
                    team_names,
                    team_abbreviations,
                    historic_abbreviations,
                    style_display,
                    presentation_family,
                    _TEAM_PRESENTATION_FAMILIES.get(presentation_family, ""),
                    asset_code,
                    outer_name,
                    consumer_scope,
                    *set_selectors,
                ) + (
                    ("menu logo", "frontend logo", "team presentation")
                    if is_uniform_presentation
                    else ()
                ) + family_aliases,
                authoring_note=(
                    (
                        "This is presentation/menu/UI art stored separately "
                        "from the live helmet/jersey textures and from the "
                        "pre-rendered Team Select cards. Its exact screen-by-"
                        "screen runtime consumers are not fully mapped. "
                    )
                    if is_uniform_presentation
                    else (
                        "This is a raw fixed-slot menu atlas. Import regenerates "
                        "only its swizzled P8 indices and palette while preserving "
                        "the wrapper, system region, exact span, and slot padding. "
                    )
                    if presentation_family.startswith("menu_")
                    else (
                        "This is franchise/draft presentation art, not midfield "
                        "or live uniform art. It remains inside its exact compressed "
                        "P8 resource span. "
                    )
                    if presentation_family
                    else ""
                ) + (
                    "Replaced inside its exact retail byte span, so the PNG "
                    "must match the listed size exactly."
                    if editable else
                    "Preview and Export PNG are available. This one retail "
                    "resource crosses a physical pack boundary, so Replace, "
                    "drag/drop, and Revert remain disabled until the composed "
                    "builder owns a two-pack atomic write."
                ),
                texture=texture,
                presentation_family=presentation_family or None,
                asset_code=asset_code or None,
                style=style,
                set_selectors=set_selectors,
                outer_name=outer_name or None,
                consumer_scope=consumer_scope,
            ))
        return assets

    @staticmethod
    def _portrait_assets(
        report: dict[str, Any],
        owners: Mapping[str, tuple[str, ...]],
        expectations: VisualCatalogExpectations,
    ) -> list[ExtendedVisualAsset]:
        rows = report.get("targets")
        summary = report.get("summary", {})
        _require(isinstance(rows, list) and len(rows) == expectations.portrait_count,
                 "Portrait report target count changed")
        _require(summary.get("numeric_portrait_count") == expectations.portrait_count,
                 "Portrait report summary count changed")
        result: list[ExtendedVisualAsset] = []
        selectors: set[str] = set()
        for number, row in enumerate(rows):
            _require(isinstance(row, dict), f"Portrait row {number} is not an object")
            portrait_id = row.get("name")
            selector = row.get("selector")
            _require(
                isinstance(portrait_id, str)
                and _FOUR_DIGITS.fullmatch(portrait_id) is not None
                and selector == f"portrait:{portrait_id}"
                and row.get("portrait_id") == int(portrait_id),
                f"Portrait row {number} has an invalid logical selector",
            )
            _require(selector not in selectors, f"Portrait selector {selector} is duplicated")
            selectors.add(selector)
            owner_terms = owners.get(portrait_id, ())
            person = owner_terms[0] if owner_terms else "Unassigned / Historical"
            result.append(ExtendedVisualAsset(
                asset_id=f"nfl2k5.portrait.{portrait_id}",
                label=f"Portrait {portrait_id} — {person}",
                group="Player Portraits",
                kind="player_portrait",
                target_selector=selector,
                width=128,
                height=128,
                writer_route=VisualWriterRoute.UNIFIED_VISUAL,
                capability_id=UNIFIED_CAPABILITY_ID,
                search_terms=_ordered_unique((portrait_id, *owner_terms)),
                authoring_note="128×128 RGBA PNG; the game stores a fixed P8 portrait slot.",
                portrait_id=portrait_id,
            ))
        return sorted(result, key=lambda asset: int(asset.portrait_id or -1))

    @staticmethod
    def _face_assets(
        report: dict[str, Any],
        owners: Mapping[str, tuple[str, ...]],
        expectations: VisualCatalogExpectations,
    ) -> list[ExtendedVisualAsset]:
        rows = report.get("resources")
        summary = report.get("summary", {})
        _require(isinstance(rows, list) and len(rows) == expectations.face_resource_count,
                 "Live face report resource count changed")
        _require(
            summary.get("selector_count") == expectations.face_selector_count
            and summary.get("texture_resource_count") == expectations.face_resource_count,
            "Live face report summary count changed",
        )
        result: list[ExtendedVisualAsset] = []
        selectors: set[str] = set()
        for number, row in enumerate(rows):
            _require(isinstance(row, dict), f"Live face row {number} is not an object")
            face_id = row.get("face_id")
            family = row.get("family")
            _require(
                isinstance(face_id, str)
                and _FOUR_DIGITS.fullmatch(face_id) is not None
                and family in _FACE_FAMILIES
                and row.get("resource_name") == f"{family}{face_id}"
                and row.get("width") == 256
                and row.get("height") == 256
                and row.get("fixed_span_png_importer_compatible") is True,
                f"Live face row {number} violates its logical writer contract",
            )
            selector = f"{face_id}:{family}"
            _require(selector not in selectors, f"Live face selector {selector} is duplicated")
            selectors.add(selector)
            family_label, group = _FACE_FAMILIES[family]
            owner_terms = owners.get(face_id, ())
            person = owner_terms[0] if owner_terms else "Generic / Unassigned"
            result.append(ExtendedVisualAsset(
                asset_id=f"nfl2k5.live-face.{face_id}.{family}",
                label=f"{family_label} {face_id} — {person}",
                group=group,
                kind="live_face",
                target_selector=selector,
                width=256,
                height=256,
                writer_route=VisualWriterRoute.UNIFIED_VISUAL,
                capability_id=UNIFIED_CAPABILITY_ID,
                search_terms=_ordered_unique((face_id, family, *owner_terms)),
                authoring_note=(
                    "256×256 fully opaque RGBA PNG. This edits live 3D-player texture art, "
                    "not the head mesh or menu portrait."
                ),
                face_id=face_id,
                family=family,
            ))
        return sorted(result, key=lambda asset: (int(asset.face_id or -1), asset.family or ""))

    @staticmethod
    def _field_assets(
        report: dict[str, Any],
        expectations: VisualCatalogExpectations,
    ) -> list[ExtendedVisualAsset]:
        rows = report.get("textures")
        summary = report.get("summary", {})
        _require(isinstance(rows, list) and len(rows) == expectations.field_texture_count,
                 "Create-team field-art texture count changed")
        _require(
            summary.get("package_count") == expectations.field_package_count
            and summary.get("texture_count") == expectations.field_texture_count,
            "Create-team field-art summary count changed",
        )
        result: list[ExtendedVisualAsset] = []
        selectors: set[str] = set()
        for number, row in enumerate(rows):
            _require(isinstance(row, dict), f"Field-art row {number} is not an object")
            logo = row.get("logo_code")
            weather = row.get("weather_suffix")
            texture = row.get("name")
            profile = _FIELD_TEXTURES.get(texture) if isinstance(texture, str) else None
            _require(
                type(logo) is int and weather in _WEATHERS and profile is not None
                and row.get("selector") == f"{logo}:{weather}:{texture}"
                and row.get("width") == profile[0]
                and row.get("height") == profile[1]
                and row.get("format_name") == "P8",
                f"Field-art row {number} violates its named writer contract",
            )
            selector = str(row["selector"])
            _require(selector not in selectors, f"Field-art selector {selector} is duplicated")
            selectors.add(selector)
            result.append(ExtendedVisualAsset(
                asset_id=f"nfl2k5.create-field.{logo}.{weather.lower()}.{texture}",
                label=f"Logo {logo} • {_WEATHERS[weather]} • {profile[2]}",
                group="Create-Team Field Art",
                kind="create_team_field_art",
                target_selector=selector,
                width=profile[0],
                height=profile[1],
                writer_route=VisualWriterRoute.UNIFIED_VISUAL,
                capability_id=UNIFIED_CAPABILITY_ID,
                search_terms=(str(logo), _WEATHERS[weather], texture, profile[2]),
                authoring_note=(
                    f"Exact {profile[0]}×{profile[1]} RGBA PNG. The fixed P8/VC-LZ slot "
                    "may refuse artwork that cannot be compressed safely."
                ),
                logo_code=logo,
                weather=weather,
                texture=texture,
            ))
        return sorted(result, key=lambda asset: (
            asset.logo_code or -1,
            ("D", "R", "S").index(asset.weather or "D"),
            asset.texture or "",
        ))

    @staticmethod
    def _scorebug_assets(
        report: dict[str, Any],
        expectations: VisualCatalogExpectations,
    ) -> list[ExtendedVisualAsset]:
        nfl = report.get("nfl2k5")
        rows = nfl.get("texture_targets") if isinstance(nfl, dict) else None
        _require(isinstance(rows, list) and len(rows) == expectations.scorebug_count,
                 "Scorebug texture target count changed")
        result: list[ExtendedVisualAsset] = []
        seen: set[str] = set()
        for number, row in enumerate(rows):
            _require(isinstance(row, dict), f"Scorebug row {number} is not an object")
            name = row.get("name")
            profile = _SCOREBUG.get(name) if isinstance(name, str) else None
            _require(
                profile is not None and name not in seen
                and row.get("width") == profile[0]
                and row.get("height") == profile[1]
                and row.get("format_name") == "P8"
                and row.get("conversion_status") == "base_level_supported",
                f"Scorebug row {number} violates its named writer contract",
            )
            seen.add(name)
            result.append(ExtendedVisualAsset(
                asset_id=f"nfl2k5.scorebug.{name}",
                label=profile[2],
                group="Scorebug Textures",
                kind="scorebug_texture",
                target_selector=name,
                width=profile[0],
                height=profile[1],
                writer_route=VisualWriterRoute.SCOREBUG,
                capability_id=SCOREBUG_CAPABILITY_ID,
                search_terms=(name, profile[2], str(row.get("role", ""))),
                authoring_note=profile[3],
                scorebug_target=name,
            ))
        _require(seen == set(_SCOREBUG), "Scorebug report does not contain all named targets")
        order = {name: index for index, name in enumerate(_SCOREBUG)}
        return sorted(result, key=lambda asset: order[asset.scorebug_target or ""])

    def get_asset(self, asset_id: str) -> ExtendedVisualAsset:
        try:
            return self._by_id[asset_id]
        except KeyError as exc:
            raise ExtendedVisualCatalogError(
                f"Unknown extended visual asset ID: {asset_id}"
            ) from exc

    def assets_for_kind(self, kind: str) -> tuple[ExtendedVisualAsset, ...]:
        return tuple(asset for asset in self.assets if asset.kind == kind)

    def assets_for_group(self, group: str) -> tuple[ExtendedVisualAsset, ...]:
        return tuple(asset for asset in self.assets if asset.group == group)

    def search(self, text: str) -> tuple[ExtendedVisualAsset, ...]:
        needle = text.strip().casefold()
        if not needle:
            return self.assets
        return tuple(
            asset for asset in self.assets
            if needle in " ".join((asset.label, asset.target_selector,
                                   *asset.search_terms)).casefold()
        )


class Nfl2k5ProductVisualCatalog:
    """One asset lookup surface spanning Phase 1 and Phase 2 visuals.

    Uniform browsing still uses :attr:`uniforms` for its set hierarchy, while
    reversible sessions can use this aggregate's :meth:`get_asset` method for
    either catalog without knowing where the asset originated.
    """

    def __init__(
        self,
        uniforms: Nfl2k5UniformCatalog,
        extended: Nfl2k5ExtendedVisualCatalog,
    ) -> None:
        self.uniforms = uniforms
        self.extended = extended
        self.assets = (*uniforms.assets, *extended.assets)
        self._by_id = {asset.asset_id: asset for asset in self.assets}
        _require(len(self._by_id) == len(self.assets),
                 "Product visual asset IDs overlap across catalogs")

    def get_asset(self, asset_id: str) -> Any:
        try:
            return self._by_id[asset_id]
        except KeyError as exc:
            raise ExtendedVisualCatalogError(
                f"Unknown product visual asset ID: {asset_id}"
            ) from exc


@lru_cache(maxsize=1)
def load_nfl2k5_product_visual_catalog() -> Nfl2k5ProductVisualCatalog:
    return Nfl2k5ProductVisualCatalog(
        load_nfl2k5_uniform_catalog(),
        load_nfl2k5_extended_visual_catalog(),
    )


@lru_cache(maxsize=1)
def load_nfl2k5_extended_visual_catalog() -> Nfl2k5ExtendedVisualCatalog:
    return Nfl2k5ExtendedVisualCatalog.from_reports()


__all__ = [
    "ExtendedVisualAsset",
    "ExtendedVisualCatalogError",
    "Nfl2k5ExtendedVisualCatalog",
    "Nfl2k5ProductVisualCatalog",
    "PRODUCTION_EXPECTATIONS",
    "SCOREBUG_CAPABILITY_ID",
    "UNIFIED_CAPABILITY_ID",
    "UniformEquipmentDescriptor",
    "VisualCatalogExpectations",
    "VisualReportPaths",
    "VisualWriterRoute",
    "load_nfl2k5_extended_visual_catalog",
    "load_nfl2k5_product_visual_catalog",
]
