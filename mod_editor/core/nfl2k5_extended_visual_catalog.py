"""Product metadata for NFL 2K5's proved non-uniform visual writers.

The research reports used here contain physical archive offsets and hashes.
Those details are deliberately discarded at this boundary.  Mod Studio keeps
only stable named selectors, dimensions, labels, search terms, and the exact
provider route needed to turn a user-authored PNG into a project edit.

Three families (player portraits, live face/head textures, and create-team
field art) are accepted by the unified visual provider.  Scorebug textures use
the separate typed scorebug provider.  Keeping that routing explicit prevents
the GUI from accidentally putting a scorebug edit into a unified-project JSON
that cannot consume it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
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


@dataclass(frozen=True, slots=True)
class VisualReportPaths:
    portraits: Path = ROOT / "reports/assets/nfl2k5_player_portrait_compatibility.json"
    live_faces: Path = ROOT / "reports/assets/nfl2k5_live_face_texture_compatibility.json"
    field_art: Path = ROOT / "reports/assets/nfl2k5_create_team_field_art_inventory.json"
    scorebug: Path = ROOT / "reports/assets/scorebug_presentation_audit.json"
    p8_textures: Path = ROOT / "reports/assets/nfl2k5_p8_texture_inventory.json"


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


PRODUCTION_EXPECTATIONS = VisualCatalogExpectations(
    portrait_count=4_303,
    face_selector_count=624,
    face_resource_count=1_872,
    field_package_count=126,
    field_texture_count=1_134,
    scorebug_count=3,
    p8_texture_count=3_024,
)


_FOUR_DIGITS = re.compile(r"^[0-9]{4}$", re.ASCII)
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


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


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
    search_terms: tuple[str, ...] = ()
    authoring_note: str = ""
    portrait_id: str | None = None
    face_id: str | None = None
    family: str | None = None
    logo_code: int | None = None
    weather: str | None = None
    texture: str | None = None
    scorebug_target: str | None = None

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.width, self.height

    @property
    def editable(self) -> bool:
        return True

    def provider_edit(self, png_path: str | os.PathLike[str]) -> dict[str, Any]:
        """Return one logical, retail-byte-free unified-provider edit."""

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
    """Immutable catalog of the four proved Phase 2 visual families."""

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
        owners = _portrait_owners(portraits)
        assets = [
            *cls._portrait_assets(portraits, owners, expectations),
            *cls._face_assets(faces, owners, expectations),
            *cls._field_assets(field, expectations),
            *cls._scorebug_assets(scorebug, expectations),
            *cls._p8_texture_assets(p8, expectations),
        ]
        return cls(assets, report_paths)

    @staticmethod
    def _p8_texture_assets(
        report: dict[str, Any],
        expectations: VisualCatalogExpectations,
    ) -> list[ExtendedVisualAsset]:
        """The standalone TXTR corpus: end zones, pads, divots, equipment.

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
            assets.append(ExtendedVisualAsset(
                asset_id=asset_id,
                label=f"{row['label']} — package {outer}",
                group=str(row["group"]),
                kind="p8_texture",
                target_selector=asset_id,
                width=int(row["width"]),
                height=int(row["height"]),
                writer_route=VisualWriterRoute.UNIFIED_VISUAL,
                capability_id="nfl2k5.textures.all_p8",
                search_terms=(texture, str(row["group"]), str(outer),
                              str(row["label"])),
                authoring_note=(
                    "Replaced inside its exact retail byte span, so the PNG "
                    "must match the listed size exactly."
                ),
                texture=texture,
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
    "VisualCatalogExpectations",
    "VisualReportPaths",
    "VisualWriterRoute",
    "load_nfl2k5_extended_visual_catalog",
    "load_nfl2k5_product_visual_catalog",
]
