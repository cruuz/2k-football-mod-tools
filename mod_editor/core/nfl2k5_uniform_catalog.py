"""Read-only NFL 2K5 uniform catalog for the product asset browser.

The Team Select inventory contains one ``unif`` card and two ``helm`` cards
for every physical team/side/style uniform set.  Those three records provide a
compact, metadata-only source of truth for the 634 sets understood by the
unified visual provider.  This module expands each set into the provider's 39
editable components without reading an XISO, exporting retail artwork, or
running a writer.

Only logical selectors and display metadata are retained.  Physical offsets,
compressed spans, retail PNG paths, and other research-only report fields do
not escape into the catalog model.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

from .errors import ValidationError


_TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


CAPABILITY_ID = "nfl2k5.uniforms.all_visual"
REPORT_SCHEMA = "nfl2k5_team_select_card_inventory/v1"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json"
EXPECTED_SET_COUNT = 634
EXPECTED_REPORT_TARGET_COUNT = EXPECTED_SET_COUNT * 3
ASSETS_PER_SET = 39

#: Digit dimensions are not a property of the family.  Retail authored 380 of the
#: 6,340 arm digits at 32x32 rather than 64x64, and 200 of the helmet digits at
#: 64x64 rather than 32x32, so one constant per family is wrong for 580 targets.
#: That is what a modder saw as Titans arm/shoulder numbers "missing" -- 28H0,
#: 28H7 and 28H8 are three of the 32x32 packages, and everything downstream of
#: this catalog was handed the wrong size for them.  Resolving against the same
#: compatibility report the decoder uses means the two cannot drift apart.
#:
#: ``nameplate_atlas`` is deliberately absent.  The catalog ships 1024x32 because
#: that is the real horizontal character strip; the report still carries the
#: pre-fix transposed 32x1024, and letting it win here would reintroduce the
#: scrambled export that transposition originally caused.
DIGIT_DIMENSION_FAMILIES = frozenset({"jersey_digit", "helmet_digit", "arm_digit"})


class UniformCatalogError(ValidationError):
    """The catalog report, selector, or requested provider edit is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise UniformCatalogError(message)


def _path_text(path: str | os.PathLike[str]) -> str:
    try:
        value = os.fspath(path)
    except TypeError as exc:
        raise UniformCatalogError("Replacement PNG path must be a string or path") from exc
    _require(isinstance(value, str), "Replacement PNG path must be text, not bytes")
    _require(bool(value) and "\0" not in value, "Replacement PNG path cannot be empty")
    # Provider edit records are portable JSON contracts.  Preserve relative or
    # absolute spelling while canonicalizing Windows separators so identical
    # input emits identical manifest bytes on every supported host.
    return value.replace("\\", "/")


def _split_owners(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    result: list[str] = []
    for part in value.split(";"):
        cleaned = part.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _normalize_side(side: str) -> tuple[str, str]:
    _require(isinstance(side, str), "Uniform side must be HOME/H or AWAY/A")
    normalized = side.strip().upper()
    normalized = {"HOME": "H", "AWAY": "A"}.get(normalized, normalized)
    _require(normalized in {"H", "A"}, "Uniform side must be HOME/H or AWAY/A")
    return normalized, "HOME" if normalized == "H" else "AWAY"


@dataclass(frozen=True, slots=True)
class UniformAsset:
    """One replaceable PNG target in a physical uniform set."""

    asset_id: str
    set_selector: str
    label: str
    group: str
    kind: str
    asset_code: str
    side_code: str
    side_name: str
    variant: int
    family: str | None
    digit: int | None
    resolution: int | None
    width: int
    height: int
    target_selector: str
    capability_id: str = CAPABILITY_ID

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.width, self.height

    def provider_edit(self, png_path: str | os.PathLike[str]) -> dict[str, Any]:
        """Return this asset's exact unified-provider v1 edit record.

        The returned path is deliberately not resolved.  Product project files
        may use a path relative to their own JSON document, while a live editor
        session may supply an absolute path.
        """

        png = _path_text(png_path)
        if self.kind in {"torso", "sleeve", "pants"}:
            return {
                "asset_code": self.asset_code,
                "clean_png": png,
                "kind": self.kind,
                "mud_mode": "darken_60",
                "mud_png": None,
                "side": self.side_code,
                "variant": self.variant,
            }
        if self.kind == "live_helmet":
            _require(self.family in {"helmet00", "helmet02"},
                     "Live helmet catalog family is invalid")
            return {
                "asset_code": self.asset_code,
                "family": self.family,
                "kind": "live_helmet",
                "png": png,
                "side": self.side_code,
                "variant": self.variant,
            }
        if self.kind == "live_number_nameplate":
            _require(self.family in {"jersey", "helmet", "arm", "nameplate"},
                     "Live digit/nameplate catalog family is invalid")
            return {
                "asset_code": self.asset_code,
                "digit": self.digit,
                "family": self.family,
                "kind": "live_number_nameplate",
                "png": png,
                "side": self.side_code,
                "variant": self.variant,
            }
        if self.kind == "team_select":
            _require(self.family in {"unif", "helm"} and
                     self.resolution in {128, 256},
                     "Team Select catalog family/resolution is invalid")
            return {
                "asset_code": self.asset_code,
                "family": self.family,
                "kind": "team_select",
                "png": png,
                "resolution": self.resolution,
                "side": self.side_name.lower(),
                "style": self.variant,
            }
        raise UniformCatalogError(f"Unsupported uniform catalog kind: {self.kind}")


@dataclass(frozen=True, slots=True)
class UniformSet:
    """One asset-code/side/style package and its 39 editable components."""

    selector: str
    label: str
    team_names: tuple[str, ...]
    team_abbreviations: tuple[str, ...]
    historic_abbreviations: tuple[str, ...]
    asset_code: str
    side_code: str
    side_name: str
    variant: int
    style_label: str
    uniform_package: str
    asset_ids: tuple[str, ...]
    thumbnail_asset_id: str


@dataclass(frozen=True, slots=True)
class _ComponentSpec:
    key: str
    label: str
    group: str
    kind: str
    width: int
    height: int
    family: str | None = None
    digit: int | None = None
    resolution: int | None = None


def _component_specs() -> tuple[_ComponentSpec, ...]:
    specs: list[_ComponentSpec] = [
        _ComponentSpec("torso", "Torso / Jersey", "Live Uniform", "torso", 512, 256),
        _ComponentSpec("sleeve", "Sleeves", "Live Uniform", "sleeve", 128, 128),
        _ComponentSpec("pants", "Pants", "Live Uniform", "pants", 512, 256),
        _ComponentSpec(
            "helmet.helmet00", "Helmet — Player Model A", "Live Helmets",
            "live_helmet", 256, 256, family="helmet00",
        ),
        _ComponentSpec(
            "helmet.helmet02", "Helmet — Player Model C", "Live Helmets",
            "live_helmet", 256, 256, family="helmet02",
        ),
    ]
    for family, label, group, size in (
        ("jersey", "Jersey Digit", "Jersey Digits", 64),
        ("helmet", "Helmet Digit", "Helmet Digits", 32),
        ("arm", "Arm / Shoulder Digit", "Arm / Shoulder Digits", 64),
    ):
        specs.extend(
            _ComponentSpec(
                f"digit.{family}.{digit}", f"{label} {digit}", group,
                "live_number_nameplate", size, size, family=family, digit=digit,
            )
            for digit in range(10)
        )
    specs.extend((
        _ComponentSpec(
            "nameplate", "Nameplate Atlas", "Nameplate",
            # 1024x32, not 32x1024: this is a horizontal character strip.
            # The transposed value came from the descriptor bug fixed in
            # nfl_txtr.parse_texture and is why the export looked scrambled.
            "live_number_nameplate", 1024, 32, family="nameplate",
        ),
        _ComponentSpec(
            "team-select.unif.256", "Uniform Card", "Team Select Cards",
            "team_select", 256, 256, family="unif", resolution=256,
        ),
        _ComponentSpec(
            "team-select.helm.256", "Helmet Card — Large", "Team Select Cards",
            "team_select", 256, 256, family="helm", resolution=256,
        ),
        _ComponentSpec(
            "team-select.helm.128", "Helmet Card — Small", "Team Select Cards",
            "team_select", 128, 128, family="helm", resolution=128,
        ),
    ))
    _require(len(specs) == ASSETS_PER_SET, "Internal uniform component count changed")
    return tuple(specs)


COMPONENT_SPECS = _component_specs()


#: Component family -> the family name used by the live-art compatibility report
#: and by every target selector.  Shared so a selector and a dimension lookup can
#: never disagree about what to call the same family.
_REPORT_FAMILIES = {
    "jersey": "jersey_digit",
    "helmet": "helmet_digit",
    "arm": "arm_digit",
    "nameplate": "nameplate_atlas",
}


def _target_selector_family(spec: "_ComponentSpec") -> str | None:
    """The report's family name for one component, or None if it has none."""

    if spec.kind != "live_number_nameplate":
        return None
    return _REPORT_FAMILIES.get(str(spec.family))


def _target_selector(set_selector: str, spec: _ComponentSpec,
                     asset_code: str, side_name: str, variant: int) -> str:
    if spec.kind in {"torso", "sleeve", "pants"}:
        return f"{set_selector}:{spec.kind}"
    if spec.kind == "live_helmet":
        return f"{set_selector}:{spec.family}"
    if spec.kind == "live_number_nameplate":
        family = _target_selector_family(spec)
        assert family is not None
        suffix = "" if spec.digit is None else f":{spec.digit}"
        return f"{set_selector}:{family}{suffix}"
    _require(spec.kind == "team_select", "Internal component kind is invalid")
    return (
        f"{spec.family}:{asset_code}:{side_name.lower()}:"
        f"{variant}:{spec.resolution}"
    )


@lru_cache(maxsize=1)
def _authored_digit_dimensions() -> dict[tuple[str, str, int, str, int], tuple[int, int]]:
    """Real per-target digit dimensions, keyed ``(code, side, variant, family, digit)``.

    Read from the hash-pinned live-art compatibility report, which is the same
    source the decoder resolves a target against.  Returns an empty mapping when
    that report is unavailable -- it lives under the gitignored ``reports/assets``
    tree, exactly like this catalog's own inventory report -- so a tree without it
    keeps the previous per-family constants instead of failing to build a catalog.
    """

    try:
        import nfl_live_numbers_nameplate_targets as live_targets
    except Exception:  # pragma: no cover - report/tooling absent
        return {}
    try:
        report = json.loads(
            Path(live_targets.DEFAULT_REPORT).read_text(encoding="utf-8"))
        resources = report["resources"]
    except (OSError, ValueError, KeyError):  # pragma: no cover - absent or changed
        return {}
    dimensions: dict[tuple[str, str, int, str, int], tuple[int, int]] = {}
    for row in resources:
        family = row.get("family")
        if family not in DIGIT_DIMENSION_FAMILIES or row.get("digit") is None:
            continue
        selector = row.get("selector") or {}
        layout = row.get("layout") or {}
        try:
            key = (str(selector["asset_code"]), str(selector["side"]),
                   int(selector["variant"]), str(family), int(row["digit"]))
            dimensions[key] = (int(layout["width"]), int(layout["height"]))
        except (KeyError, TypeError, ValueError):  # pragma: no cover - malformed row
            continue
    return dimensions


def _digit_dimensions_for(asset_code: str, side_code: str, variant: int,
                          spec: "_ComponentSpec") -> tuple[int, int]:
    """The authored size for one digit target, or the family default."""

    family = _target_selector_family(spec)
    if family is None or spec.digit is None:
        return (spec.width, spec.height)
    authored = _authored_digit_dimensions().get(
        (asset_code, side_code, variant, family, spec.digit))
    return authored or (spec.width, spec.height)


def _assets_for_seed(asset_code: str, side_code: str, side_name: str,
                     variant: int, set_selector: str) -> tuple[UniformAsset, ...]:
    result = []
    prefix = f"nfl2k5.uniform.{set_selector.lower()}"
    for spec in COMPONENT_SPECS:
        width, height = _digit_dimensions_for(
            asset_code, side_code, variant, spec)
        result.append(UniformAsset(
            asset_id=f"{prefix}.{spec.key}",
            set_selector=set_selector,
            label=spec.label,
            group=spec.group,
            kind=spec.kind,
            asset_code=asset_code,
            side_code=side_code,
            side_name=side_name,
            variant=variant,
            family=spec.family,
            digit=spec.digit,
            resolution=spec.resolution,
            width=width,
            height=height,
            target_selector=_target_selector(
                set_selector, spec, asset_code, side_name, variant),
        ))
    return tuple(result)


class Nfl2k5UniformCatalog:
    """Immutable indexed view of all provider-editable NFL 2K5 uniforms."""

    def __init__(self, uniform_sets: Iterable[UniformSet],
                 assets: Iterable[UniformAsset], source_report: Path):
        self.uniform_sets = tuple(uniform_sets)
        self.assets = tuple(assets)
        self.source_report = source_report
        self._sets_by_selector = {item.selector: item for item in self.uniform_sets}
        self._assets_by_id = {item.asset_id: item for item in self.assets}
        _require(len(self.uniform_sets) == EXPECTED_SET_COUNT and
                 len(self._sets_by_selector) == EXPECTED_SET_COUNT,
                 "Uniform catalog must contain 634 unique sets")
        _require(len(self.assets) == EXPECTED_SET_COUNT * ASSETS_PER_SET and
                 len(self._assets_by_id) == len(self.assets),
                 "Uniform catalog asset IDs are missing or duplicated")

    @classmethod
    def from_report(cls, report_path: Path = DEFAULT_REPORT) -> "Nfl2k5UniformCatalog":
        path = report_path.expanduser().resolve(strict=True)
        if not path.is_file():
            raise UniformCatalogError(f"Team Select catalog report is not a file: {path}")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UniformCatalogError(f"Cannot read Team Select catalog report: {exc}") from exc
        _require(isinstance(document, dict) and
                 document.get("schema") == REPORT_SCHEMA,
                 "Team Select catalog report schema is unsupported")
        targets = document.get("targets")
        _require(isinstance(targets, list) and
                 len(targets) == EXPECTED_REPORT_TARGET_COUNT,
                 "Team Select report must contain 1,902 card targets")

        grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        for number, raw in enumerate(targets):
            _require(isinstance(raw, dict),
                     f"Team Select target {number} is not an object")
            asset_code = raw.get("asset_code")
            side_name = raw.get("side_context")
            side_code = raw.get("side_code")
            variant = raw.get("style")
            family = raw.get("family")
            resolution = raw.get("width")
            _require(isinstance(asset_code, str) and len(asset_code) == 2 and
                     asset_code.isdecimal(),
                     f"Team Select target {number} has an invalid asset code")
            _require(side_name in {"HOME", "AWAY"} and
                     side_code == ("H" if side_name == "HOME" else "A"),
                     f"Team Select target {number} has an invalid side")
            _require(type(variant) is int and 0 <= variant <= 99,
                     f"Team Select target {number} has an invalid style")
            _require((family, resolution) in {
                ("unif", 256), ("helm", 256), ("helm", 128),
            }, f"Team Select target {number} has an invalid card class")
            expected_selector = (
                f"{family}:{asset_code}:{side_name.lower()}:{variant}:{resolution}"
            )
            _require(raw.get("selector") == expected_selector,
                     f"Team Select target {number} selector is inconsistent")
            grouped.setdefault((asset_code, side_code, variant), []).append(raw)

        _require(len(grouped) == EXPECTED_SET_COUNT,
                 "Team Select report must resolve to 634 uniform sets")
        all_sets: list[UniformSet] = []
        all_assets: list[UniformAsset] = []
        side_order = {"H": 0, "A": 1}
        for asset_code, side_code, variant in sorted(
            grouped, key=lambda key: (int(key[0]), key[2], side_order[key[1]]),
        ):
            rows = grouped[(asset_code, side_code, variant)]
            signatures = sorted((str(row["family"]), int(row["width"])) for row in rows)
            _require(signatures == [("helm", 128), ("helm", 256), ("unif", 256)],
                     f"Uniform set {asset_code}{side_code}{variant} lacks its three cards")
            first = rows[0]
            consistency_fields = (
                "asset_code", "side_code", "side_context", "style",
                "style_display", "team_names", "team_abbreviations",
                "historic_abbreviations", "uniform_package",
            )
            for row in rows[1:]:
                _require(all(row.get(field) == first.get(field)
                             for field in consistency_fields),
                         f"Uniform set {asset_code}{side_code}{variant} metadata disagrees")
            side_name = str(first["side_context"])
            set_selector = f"{asset_code}{side_code}{variant}"
            uniform_package = first.get("uniform_package")
            _require(uniform_package == f"{set_selector}.IFF",
                     f"Uniform set {set_selector} package name is inconsistent")
            raw_style_label = first.get("style_display")
            _require(isinstance(raw_style_label, str),
                     f"Uniform set {set_selector} has an invalid display label")
            # Some generic/create-team banks deliberately have no compiled menu
            # caption.  Keep them browsable under a neutral factual fallback.
            style_label = raw_style_label.strip() or f"Style {variant}"
            team_names = _split_owners(first.get("team_names"))
            team_abbreviations = _split_owners(first.get("team_abbreviations"))
            historic_abbreviations = _split_owners(first.get("historic_abbreviations"))
            owner_label = " / ".join(team_names) if team_names else f"Uniform Asset {asset_code}"
            label = f"{owner_label} — {style_label} — {side_name.title()}"
            assets = _assets_for_seed(
                asset_code, side_code, side_name, variant, set_selector)
            asset_ids = tuple(item.asset_id for item in assets)
            thumbnail_asset_id = (
                f"nfl2k5.uniform.{set_selector.lower()}.team-select.unif.256"
            )
            _require(thumbnail_asset_id in asset_ids,
                     f"Uniform set {set_selector} thumbnail target is absent")
            all_sets.append(UniformSet(
                selector=set_selector,
                label=label,
                team_names=team_names,
                team_abbreviations=team_abbreviations,
                historic_abbreviations=historic_abbreviations,
                asset_code=asset_code,
                side_code=side_code,
                side_name=side_name,
                variant=variant,
                style_label=style_label,
                uniform_package=str(uniform_package),
                asset_ids=asset_ids,
                thumbnail_asset_id=thumbnail_asset_id,
            ))
            all_assets.extend(assets)
        return cls(all_sets, all_assets, path)

    @classmethod
    def load(cls, report_path: Path = DEFAULT_REPORT) -> "Nfl2k5UniformCatalog":
        return load_nfl2k5_uniform_catalog(report_path)

    def get_asset(self, asset_id: str) -> UniformAsset:
        try:
            return self._assets_by_id[asset_id]
        except KeyError as exc:
            raise UniformCatalogError(f"Unknown uniform asset ID: {asset_id}") from exc

    def get_uniform_set(self, selector: str) -> UniformSet:
        normalized = selector.strip().upper() if isinstance(selector, str) else ""
        try:
            return self._sets_by_selector[normalized]
        except KeyError as exc:
            raise UniformCatalogError(f"Unknown uniform set selector: {selector}") from exc

    def assets_for_set(self, selector: str) -> tuple[UniformAsset, ...]:
        uniform_set = self.get_uniform_set(selector)
        return tuple(self._assets_by_id[asset_id] for asset_id in uniform_set.asset_ids)

    def uniform_set_for(self, asset_code: str, side: str, variant: int) -> UniformSet:
        _require(isinstance(asset_code, str) and len(asset_code) == 2 and
                 asset_code.isdecimal(), "Uniform asset code must be two decimal digits")
        side_code, _ = _normalize_side(side)
        _require(type(variant) is int and 0 <= variant <= 99,
                 "Uniform variant must be an integer from 0 through 99")
        return self.get_uniform_set(f"{asset_code}{side_code}{variant}")


@lru_cache(maxsize=4)
def _load_cached(report_path: str) -> Nfl2k5UniformCatalog:
    return Nfl2k5UniformCatalog.from_report(Path(report_path))


def load_nfl2k5_uniform_catalog(
    report_path: Path = DEFAULT_REPORT,
) -> Nfl2k5UniformCatalog:
    """Load and memoize the immutable metadata-only uniform catalog."""

    return _load_cached(str(report_path.expanduser().resolve(strict=True)))


__all__ = [
    "ASSETS_PER_SET",
    "CAPABILITY_ID",
    "DEFAULT_REPORT",
    "EXPECTED_SET_COUNT",
    "Nfl2k5UniformCatalog",
    "UniformAsset",
    "UniformCatalogError",
    "UniformSet",
    "load_nfl2k5_uniform_catalog",
]
