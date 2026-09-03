"""Registry-driven product navigation for 2K5 Mod Studio.

The research registry is intentionally organized by reverse-engineering
``surface``.  The product sidebar is organized around the way a modder thinks
about the game.  This module is the small, UI-independent bridge between those
two vocabularies.

Category assignment and product status are deliberately separate:

* every NFL 2K5 registry capability is assigned to exactly one sidebar
  category;
* a capability's classification alone determines its user-facing status; and
* optional findings hooks may add concise UI notes without changing either
  assignment or status.

The Team Identity category is present even though the v1 registry has no
standalone team-identity row.  Its writer is currently a kind inside the
unified visual capability, which remains assigned to Uniforms & Equipment so
that capability counts stay one-to-one and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Sequence

from .capabilities import Capability, CapabilityRegistry, Classification
from .model import GameId


class ProductCatalogError(ValueError):
    """Raised when a registry row cannot be placed in the product catalog."""


class ProductCategory(str, Enum):
    UNIFORMS_EQUIPMENT = "uniforms_equipment"
    ROSTERS_PLAYERS = "rosters_players"
    TEAM_IDENTITY = "team_identity"
    FIELD_ART_CREATE_TEAM = "field_art_create_team"
    STADIUMS = "stadiums"
    SCOREBUG_PRESENTATION = "scorebug_presentation"
    MENUS_UI = "menus_ui"
    CRIB = "crib"
    AUDIO = "audio"
    SLIDERS_GAMEPLAY = "sliders_gameplay"
    PLAYBOOKS_PLAYS = "playbooks_plays"
    TEXTURES = "textures"

    @property
    def title(self) -> str:
        return _CATEGORY_TITLES[self]


class ProductStatus(str, Enum):
    EDITABLE = "Editable"
    PREVIEW = "Preview"
    EXPORT_ONLY = "Export-only"
    COMING_SOON = "Coming Soon"
    EVIDENCE = "Proof boundary"
    RESEARCH = "Research boundary"


PRODUCT_CATEGORY_ORDER: tuple[ProductCategory, ...] = (
    ProductCategory.UNIFORMS_EQUIPMENT,
    ProductCategory.ROSTERS_PLAYERS,
    ProductCategory.TEAM_IDENTITY,
    ProductCategory.FIELD_ART_CREATE_TEAM,
    ProductCategory.STADIUMS,
    ProductCategory.SCOREBUG_PRESENTATION,
    ProductCategory.MENUS_UI,
    ProductCategory.CRIB,
    ProductCategory.AUDIO,
    ProductCategory.SLIDERS_GAMEPLAY,
    ProductCategory.PLAYBOOKS_PLAYS,
    ProductCategory.TEXTURES,
)

PRODUCT_STATUS_ORDER: tuple[ProductStatus, ...] = (
    ProductStatus.EDITABLE,
    ProductStatus.PREVIEW,
    ProductStatus.EXPORT_ONLY,
    ProductStatus.EVIDENCE,
    ProductStatus.RESEARCH,
    ProductStatus.COMING_SOON,
)

_CATEGORY_TITLES: dict[ProductCategory, str] = {
    ProductCategory.UNIFORMS_EQUIPMENT: "Uniforms & Equipment",
    ProductCategory.ROSTERS_PLAYERS: "Rosters & Players",
    ProductCategory.TEAM_IDENTITY: "Team Identity",
    ProductCategory.FIELD_ART_CREATE_TEAM: "Field Art & Create-Team Art",
    ProductCategory.STADIUMS: "Stadiums",
    ProductCategory.SCOREBUG_PRESENTATION: "Presentation",
    ProductCategory.MENUS_UI: "Menus & UI",
    ProductCategory.CRIB: "The Crib",
    ProductCategory.AUDIO: "Audio",
    ProductCategory.SLIDERS_GAMEPLAY: "Gameplay",
    ProductCategory.PLAYBOOKS_PLAYS: "Playbooks & Plays",
    ProductCategory.TEXTURES: "All Textures",
}

# Exact-ID overrides resolve surfaces which intentionally span more than one
# product category.  All other assignments are surface based so a
# classification upgrade does not require a UI change.
_CAPABILITY_CATEGORY_OVERRIDES: dict[str, ProductCategory] = {
    "nfl2k5.stadiums.create_team_field_art":
        ProductCategory.FIELD_ART_CREATE_TEAM,
}

_SURFACE_CATEGORIES: dict[str, ProductCategory] = {
    "audio": ProductCategory.AUDIO,
    "catching_drops": ProductCategory.SLIDERS_GAMEPLAY,
    "colors": ProductCategory.UNIFORMS_EQUIPMENT,
    "cpu_ai_draft": ProductCategory.SLIDERS_GAMEPLAY,
    "crib_assets": ProductCategory.CRIB,
    "cross_title_model_conversion": ProductCategory.STADIUMS,
    "franchise_restoration_cross_title": ProductCategory.SLIDERS_GAMEPLAY,
    "gameplay_tuning_sliders": ProductCategory.SLIDERS_GAMEPLAY,
    "logos_cards": ProductCategory.UNIFORMS_EQUIPMENT,
    "menus": ProductCategory.MENUS_UI,
    "mode_state_routing": ProductCategory.MENUS_UI,
    "models_shap_scne": ProductCategory.STADIUMS,
    "players_rosters": ProductCategory.ROSTERS_PLAYERS,
    "portraits_faces": ProductCategory.ROSTERS_PLAYERS,
    "saves": ProductCategory.SLIDERS_GAMEPLAY,
    "schedules_franchise": ProductCategory.SLIDERS_GAMEPLAY,
    "scorebug_presentation": ProductCategory.SCOREBUG_PRESENTATION,
    "scripts_config": ProductCategory.PLAYBOOKS_PLAYS,
    "stadiums_fields": ProductCategory.STADIUMS,
    "textures": ProductCategory.TEXTURES,
    "uniforms": ProductCategory.UNIFORMS_EQUIPMENT,
}

_CLASSIFICATION_STATUSES: dict[Classification, ProductStatus] = {
    Classification.RUNTIME_PROVED: ProductStatus.EDITABLE,
    Classification.OFFLINE_WRITER_PROVED: ProductStatus.EDITABLE,
    Classification.READ_ONLY_MAPPED: ProductStatus.PREVIEW,
    Classification.EXTRACT_ONLY: ProductStatus.EXPORT_ONLY,
    Classification.UNKNOWN: ProductStatus.COMING_SOON,
    Classification.UNSAFE_DEFERRED: ProductStatus.COMING_SOON,
}

_CATEGORY_FINDINGS: dict[ProductCategory, tuple[str, ...]] = {
    ProductCategory.TEAM_IDENTITY: (
        "Team identity is currently owned by the team_identity kind inside "
        "nfl2k5.uniforms.all_visual; the v1 registry has no standalone Team "
        "Identity capability row.",
    ),
    ProductCategory.FIELD_ART_CREATE_TEAM: (
        "Create-Team field art is the only proved field-art writer: 1,134 targets "
        "(center_logo + six end-zone panels + pad_north/pad_south) inside the "
        "create-team packages. Stock NFL midfield art is not a separate 'field art' "
        "file — it is baked into each stadium's texture set. Browse that team's "
        "midfield and end-zone in Stadium Studio (477 scenes, People & sideline "
        "filter) or search 'field'/'midfield'/'endzone' in All Textures — those "
        "1,134 create-team targets plus the 28,530 equipment palettes are the "
        "11,395 All Textures targets, and NFL stadium field pieces are also there "
        "under their stadium packages.",
    ),
    ProductCategory.CRIB: (
        "Crib photos and object textures are surfaced by a dedicated ownership "
        "catalog. Model swapping remains a bounded research spike.",
    ),
    ProductCategory.AUDIO: (
        "The Audio browser separates 850 playable standalone AUDO cues from "
        "17 AUSB streaming-bank descriptors covering 53,571 indexed ranges. "
        "Every bank and exact range is independently raw-exportable; streaming "
        "ranges also support private Xbox IMA playback/WAV export and exact-shape "
        "PCM16 replacement into their existing fixed slots. Complete-bank "
        "replacement, cue names, loops, gain/pan/priority, and mixer routing remain "
        "unowned; a raw bank is still Export-only rather than a repack target.",
    ),
}

_CATEGORY_RELATED_CAPABILITIES: dict[ProductCategory, tuple[str, ...]] = {
    ProductCategory.TEAM_IDENTITY: ("nfl2k5.uniforms.all_visual",),
    ProductCategory.CRIB: ("nfl2k5.models.scne_gltf",),
}


@dataclass(frozen=True)
class ProductCounts:
    total: int
    editable: int
    preview: int
    export_only: int
    coming_soon: int
    evidence: int
    research: int

    @classmethod
    def from_statuses(cls, statuses: Iterable[ProductStatus]) -> "ProductCounts":
        values = tuple(statuses)
        return cls(
            total=len(values),
            editable=values.count(ProductStatus.EDITABLE),
            preview=values.count(ProductStatus.PREVIEW),
            export_only=values.count(ProductStatus.EXPORT_ONLY),
            coming_soon=values.count(ProductStatus.COMING_SOON),
            evidence=values.count(ProductStatus.EVIDENCE),
            research=values.count(ProductStatus.RESEARCH),
        )

    def for_status(self, status: ProductStatus) -> int:
        return {
            ProductStatus.EDITABLE: self.editable,
            ProductStatus.PREVIEW: self.preview,
            ProductStatus.EXPORT_ONLY: self.export_only,
            ProductStatus.COMING_SOON: self.coming_soon,
            ProductStatus.EVIDENCE: self.evidence,
            ProductStatus.RESEARCH: self.research,
        }[status]


@dataclass(frozen=True)
class FindingsContext:
    """Stable input passed to optional product findings-note hooks."""

    capability: Capability
    category: ProductCategory
    status: ProductStatus


FindingsNote = str | Iterable[str] | None
FindingsNoteHook = Callable[[FindingsContext], FindingsNote]


@dataclass(frozen=True)
class ProductCapability:
    capability: Capability
    category: ProductCategory
    status: ProductStatus
    findings_notes: tuple[str, ...] = ()

    @property
    def capability_id(self) -> str:
        return self.capability.capability_id

    @property
    def title(self) -> str:
        return self.capability.title


@dataclass(frozen=True)
class ProductCategorySection:
    category: ProductCategory
    capabilities: tuple[ProductCapability, ...]
    counts: ProductCounts
    findings_notes: tuple[str, ...] = ()
    related_capability_ids: tuple[str, ...] = ()

    @property
    def title(self) -> str:
        return self.category.title


@dataclass(frozen=True)
class ProductCatalog:
    sections: tuple[ProductCategorySection, ...]
    counts: ProductCounts

    @property
    def capabilities(self) -> tuple[ProductCapability, ...]:
        return tuple(
            binding
            for section in self.sections
            for binding in section.capabilities
        )

    def section(self, category: ProductCategory | str) -> ProductCategorySection:
        normalized = _normalize_category(category)
        for section in self.sections:
            if section.category == normalized:
                return section
        raise ProductCatalogError(f"Product category is absent: {normalized.value}")

    def binding(self, capability_id: str) -> ProductCapability:
        matches = [
            binding
            for binding in self.capabilities
            if binding.capability_id == capability_id
        ]
        if len(matches) != 1:
            raise ProductCatalogError(
                f"Product capability is absent or ambiguous: {capability_id}"
            )
        return matches[0]


def product_status(classification: Classification) -> ProductStatus:
    try:
        return _CLASSIFICATION_STATUSES[classification]
    except KeyError as exc:
        raise ProductCatalogError(
            f"Unsupported capability classification: {classification!r}"
        ) from exc


def product_category(capability: Capability) -> ProductCategory:
    if capability.game != GameId.NFL2K5:
        raise ProductCatalogError(
            f"Product catalog accepts NFL 2K5 capabilities only: "
            f"{capability.capability_id}"
        )
    override = _CAPABILITY_CATEGORY_OVERRIDES.get(capability.capability_id)
    if override is not None:
        return override
    try:
        return _SURFACE_CATEGORIES[capability.surface]
    except KeyError as exc:
        raise ProductCatalogError(
            f"No product category owns surface {capability.surface!r} "
            f"for {capability.capability_id}"
        ) from exc


def build_nfl2k5_product_catalog(
    registry: CapabilityRegistry,
    *,
    findings_note_hooks: Sequence[FindingsNoteHook] = (),
) -> ProductCatalog:
    """Build the complete ten-section NFL 2K5 product catalog.

    Hooks run in their supplied order after category and status have been
    resolved. Empty notes are ignored and duplicate notes are collapsed while
    preserving first occurrence. A hook cannot change assignment or status.
    """

    bindings: list[ProductCapability] = []
    for capability in registry.for_game(GameId.NFL2K5):
        category = product_category(capability)
        gui = capability.raw.get("gui", {})
        exposed = isinstance(gui, dict) and gui.get("expose") is True
        if not exposed:
            status = (
                ProductStatus.EVIDENCE
                if capability.classification
                in {
                    Classification.RUNTIME_PROVED,
                    Classification.OFFLINE_WRITER_PROVED,
                }
                else ProductStatus.RESEARCH
            )
        else:
            status = product_status(capability.classification)
        context = FindingsContext(capability, category, status)
        notes: list[str] = []
        for hook in findings_note_hooks:
            notes.extend(_normalize_notes(hook(context)))
        bindings.append(
            ProductCapability(
                capability=capability,
                category=category,
                status=status,
                findings_notes=_unique(notes),
            )
        )

    ids = [binding.capability_id for binding in bindings]
    if len(ids) != len(set(ids)):
        raise ProductCatalogError("NFL product catalog contains duplicate capability IDs")

    sections: list[ProductCategorySection] = []
    for category in PRODUCT_CATEGORY_ORDER:
        rows = tuple(
            sorted(
                (binding for binding in bindings if binding.category == category),
                key=lambda binding: (
                    PRODUCT_STATUS_ORDER.index(binding.status),
                    binding.title.casefold(),
                    binding.capability_id,
                ),
            )
        )
        sections.append(
            ProductCategorySection(
                category=category,
                capabilities=rows,
                counts=ProductCounts.from_statuses(
                    binding.status for binding in rows
                ),
                findings_notes=_CATEGORY_FINDINGS.get(category, ()),
                related_capability_ids=
                    _CATEGORY_RELATED_CAPABILITIES.get(category, ()),
            )
        )

    flattened = tuple(
        binding for section in sections for binding in section.capabilities
    )
    if len(flattened) != len(bindings) or set(ids) != {
        binding.capability_id for binding in flattened
    }:
        raise ProductCatalogError(
            "NFL capabilities were not assigned to exactly one product category"
        )
    return ProductCatalog(
        sections=tuple(sections),
        counts=ProductCounts.from_statuses(
            binding.status for binding in flattened
        ),
    )


def _normalize_category(category: ProductCategory | str) -> ProductCategory:
    if isinstance(category, ProductCategory):
        return category
    try:
        return ProductCategory(category)
    except (TypeError, ValueError) as exc:
        raise ProductCatalogError(f"Unknown product category: {category!r}") from exc


def _normalize_notes(value: FindingsNote) -> list[str]:
    if value is None:
        return []
    candidates = (value,) if isinstance(value, str) else tuple(value)
    notes: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            raise ProductCatalogError("Findings hooks must return strings")
        cleaned = " ".join(candidate.split())
        if cleaned:
            notes.append(cleaned)
    return notes


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


__all__ = [
    "FindingsContext",
    "FindingsNoteHook",
    "PRODUCT_CATEGORY_ORDER",
    "PRODUCT_STATUS_ORDER",
    "ProductCapability",
    "ProductCatalog",
    "ProductCatalogError",
    "ProductCategory",
    "ProductCategorySection",
    "ProductCounts",
    "ProductStatus",
    "build_nfl2k5_product_catalog",
    "product_category",
    "product_status",
]
