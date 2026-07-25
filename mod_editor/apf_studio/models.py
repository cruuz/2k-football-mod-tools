"""UI-independent product models for APF 2K8 Mod Studio."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


DRAFT_LOGO_EDIT_ID = "apf:franchise:draft_logo"
DRAFT_LOGO_OUTER_INDEX = 810
DRAFT_LOGO_INNER_INDEX = 117
DRAFT_LOGO_CATALOG_ID = (
    f"apf:outer:{DRAFT_LOGO_OUTER_INDEX}:inner:{DRAFT_LOGO_INNER_INDEX}"
)
DIGITAL_FONT_EDIT_ID = "apf:presentation:digital_font"
DIGITAL_FONT_OUTER_INDEX = 1310
DIGITAL_FONT_INNER_INDEX = 246
DIGITAL_FONT_CATALOG_ID = (
    f"apf:outer:{DIGITAL_FONT_OUTER_INDEX}:inner:{DIGITAL_FONT_INNER_INDEX}"
)
AUDO_EXACT_SLOT_KIND = "audo_exact_slot_xma1"
AUDO_EXACT_SLOT_WRITER_SCHEMA = "apf2k8_audo_exact_slot_xma1/v1"
AUSB_EXACT_SLOT_KIND = "ausb_exact_slot_xma1"
AUSB_EXACT_SLOT_WRITER_SCHEMA = "apf2k8_ausb_exact_slot_xma1/v1"


class ApfProductAction(str, Enum):
    """User-visible actions that an APF product handler actually implements."""

    PREVIEW = "preview"
    EXPORT = "export"
    REPLACE = "replace"
    REVERT = "revert"


class ApfStatus(str, Enum):
    EDITABLE = "Editable"
    PREVIEW = "Preview"
    EXPORT_ONLY = "Export-only"
    COMING_SOON = "Coming Soon"


@dataclass(frozen=True)
class CapabilityActionBinding:
    """One reviewed bridge from a capability row to a concrete product route.

    A capability omitted from :data:`CAPABILITY_ACTION_BINDINGS` remains visible
    as Coming Soon.  Registry classification alone never fabricates a button.
    """

    capability_id: str
    handler_id: str
    actions: frozenset[ApfProductAction]
    replace_method: str | None = None
    revert_method: str | None = None
    product_note: str = ""
    additional_replace_methods: tuple[str, ...] = ()

    @property
    def has_complete_editor(self) -> bool:
        return (
            {ApfProductAction.REPLACE, ApfProductAction.REVERT}
            <= self.actions
            and bool(self.replace_method)
            and bool(self.revert_method)
        )

    @property
    def bound_replace_methods(self) -> tuple[str, ...]:
        """Every concrete mutation route represented by this capability row."""

        primary = (self.replace_method,) if self.replace_method else ()
        return primary + self.additional_replace_methods


@dataclass(frozen=True)
class AssetActionBinding:
    """Exact archive identity and facade route for one universal-browser editor."""

    capability_id: str
    handler_id: str
    asset_id: str
    outer_index: int
    inner_index: int
    name: str
    type_name: str
    edit_id: str
    preview_method: str
    export_method: str
    replace_method: str
    authoring_note: str
    notes: tuple[str, ...]

    def matches(
        self,
        asset_id: str,
        outer_index: int,
        inner_index: int | None,
        name: str,
        type_name: str,
    ) -> bool:
        return (
            asset_id == self.asset_id
            and outer_index == self.outer_index
            and inner_index == self.inner_index
            and name == self.name
            and type_name == self.type_name
        )


def _actions(*values: ApfProductAction) -> frozenset[ApfProductAction]:
    return frozenset(values)


# This is the product's single capability/action truth table.  Capabilities
# with safe research backends but no desktop handler are intentionally absent.
CAPABILITY_ACTION_BINDINGS: Mapping[str, CapabilityActionBinding] = {
    "apf2k8.audio.ausb_xma_export": CapabilityActionBinding(
        "apf2k8.audio.ausb_xma_export",
        "audio.ausb_exact_slot_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_ausb_exact_slot",
        revert_method="revert",
        product_note=(
            "All 45,514 AUSB soundtrack, commentary, speech, PA, music, and "
            "presentation rows accept strict pre-encoded RIFF XMA1 replacement "
            "without repacking their shared banks. Channels, sample rate, packet "
            "allocation, and decoded duration must match the selected slot exactly. "
            "One physical cwdloop row has two disclosed owners; both are affected "
            "together. A selected sound can start from an exact PCM16 WAV through "
            "a user-configured external XMA1 encoder; FLAC/MP3 and batch PCM input "
            "remain unsupported. "
            "Every accepted payload is checked against complete-packet fingerprints "
            "from both the loaded game's AUDO and AUSB audio families."
        ),
    ),
    "apf2k8.audio.xma_export": CapabilityActionBinding(
        "apf2k8.audio.xma_export",
        "audio.standalone_audo_exact_slot_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_audo_exact_slot",
        revert_method="revert",
        product_note=(
            "All 2,261 standalone AUDO slots accept strict pre-encoded RIFF "
            "XMA1 replacement when channels, sample rate, encoded length, "
            "packet framing, and decoded duration match exactly. Projects store "
            "only the user's raw replacement packets. A selected sound can start "
            "from an exact PCM16 WAV through a user-configured external XMA1 "
            "encoder; no encoder ships with Mod Studio, and FLAC/MP3 plus batch "
            "PCM input remain unsupported."
        ),
    ),
    "apf2k8.colors.uniform_selector_bytes": CapabilityActionBinding(
        "apf2k8.colors.uniform_selector_bytes",
        "team_identity.selector_inspector",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
    ),
    "apf2k8.cpu_ai_draft.logic": CapabilityActionBinding(
        "apf2k8.cpu_ai_draft.logic",
        "gameplay.findings_inspector",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
    ),
    "apf2k8.field_art.base_texture": CapabilityActionBinding(
        "apf2k8.field_art.base_texture",
        "field_art.base_texture_png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_field_art",
        revert_method="revert_field_art",
        product_note=(
            "The Field Art editor writes exactly the six offline-proved base "
            "textures (endzone_l0/l1, pc_field_goal, Field_Pass_text, "
            "Stride_number_field, divots) into a copied 0A through "
            "tools/apf_field_art_patch.py -- one texture per build. Each build "
            "regenerates only the selected base mip level; the descriptor pad, "
            "the packed mip tail, and every sibling inner part are verified "
            "unchanged against the whole volume, and the read-only source is "
            "never opened for writing. The deferred field_radiance and "
            "divot_Grass* codecs and the SCNE/CurveAnim rows have no bounded "
            "writer and stay export-only. In-game appearance is not proved "
            "without a Xenia capture."
        ),
    ),
    "apf2k8.gameplay_tuning_sliders.roster_view": CapabilityActionBinding(
        "apf2k8.gameplay_tuning_sliders.roster_view",
        "gameplay.findings_inspector",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
    ),
    "apf2k8.logos_cards.draft_logo": CapabilityActionBinding(
        "apf2k8.logos_cards.draft_logo",
        "asset.draft_logo_png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_draft_logo",
        revert_method="revert",
    ),
    "apf2k8.logos_cards.team_logo": CapabilityActionBinding(
        "apf2k8.logos_cards.team_logo",
        "logos_cards.team_logo_png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_team_logo",
        revert_method="revert_team_logo",
        product_note=(
            "The Team Logo editor stages one exact 512x512 RGBA crest, and one "
            "build writes it into both places the disc stores it: the "
            "uniform_logo_01 package (logo_l0) through tools/apf_logo_patch.py "
            "and the matching entry of the prebuilt uniform_logocache aggregate "
            "through tools/apf_logocache_patch.py, chained over one intermediate "
            "copy. Each writer byte-diffs the whole copied volume so only its "
            "own fixed extents change, each is paired with an independent "
            "verifier, and the read-only source is never opened for writing. "
            "Colors are stored at 4 bits per channel and the build reports the "
            "exact decode-back error. Which runtime surface reads which copy -- "
            "helmet crest, team-select grid, or scorebug -- is not proved "
            "without a Xenia capture."
        ),
    ),
    "apf2k8.logos_cards.team_logo_cache": CapabilityActionBinding(
        "apf2k8.logos_cards.team_logo_cache",
        "logos_cards.team_logo_png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_team_logo",
        revert_method="revert_team_logo",
        product_note=(
            "This runtime logo cache is a coupled companion of the team-logo "
            "package: the single Team Logo build writes it from the same staged "
            "512x512 crest through tools/apf_logocache_patch.py (catalog index "
            "1), rewriting the matching entry of the prebuilt uniform_logocache "
            "aggregate and verifying every other byte unchanged. There is no "
            "cache-only editor -- staging or reverting the Team Logo crest "
            "stages or reverts this cache write with it -- so it shares the "
            "team-logo replace/revert route. The writer re-checks its pinned "
            "retail directory and payload and fails closed. In-game consumption "
            "is not proved without a Xenia capture."
        ),
    ),
    "apf2k8.menus.layouts": CapabilityActionBinding(
        "apf2k8.menus.layouts",
        "text.allocation_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_localization_text",
        revert_method="revert",
    ),
    "apf2k8.players.roster": CapabilityActionBinding(
        "apf2k8.players.roster",
        "roster.player_team_name_and_base_rating_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_roster_identity_text",
        revert_method="revert",
        product_note=(
            "The 40 existing team display-name allocations and every nonempty "
            "pure player first/last-name allocation support bounded Replace/Revert "
            "through the runtime-proved token-preserving ROST transport. Shared "
            "allocations disclose every owner and change those owners together. "
            "Every player also exposes 28 independent native base ratings with "
            "exact 0–99 Replace/Revert; a source native 100 remains visible and "
            "revertible but cannot be applied as a new edit. Every player position "
            "also has bounded 0–16 Replace/Revert through a 17-choice desktop "
            "dropdown and the paired "
            "semantic +0x34 and source-mirror +0x35 bytes. That position writer "
            "is offline-proved; its first Xenia spot check is still pending. "
            "CODEXTEAM and Dan "
            "CODEX both rendered in Xenia. The rating candidate also booted and "
            "loaded Dan Marino, though its star-selection UI had no numeric byte "
            "readout. Both abbreviation fields, zero-capacity names, jersey "
            "numbers, Overall, abilities, tier, membership, and depth charts "
            "remain separate and locked."
        ),
        additional_replace_methods=(
            "replace_player_base_rating",
            "replace_player_position",
        ),
    ),
    "apf2k8.scorebug_presentation.digital_font": CapabilityActionBinding(
        "apf2k8.scorebug_presentation.digital_font",
        "asset.digital_font_png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_digital_font",
        revert_method="revert",
    ),
    "apf2k8.scorebug_presentation.inventory": CapabilityActionBinding(
        "apf2k8.scorebug_presentation.inventory",
        "scorebug.presentation_inspector",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
        product_note=(
            "The Presentation Map covers the seven field components and the "
            "digital-font boundary; GameCast, replay, halftime, and overlay "
            "resources retain raw-only access."
        ),
    ),
    "apf2k8.scripts.director_playbook": CapabilityActionBinding(
        "apf2k8.scripts.director_playbook",
        "playbook.inspector",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
    ),
    "apf2k8.stadiums.geometry": CapabilityActionBinding(
        "apf2k8.stadiums.geometry",
        "stadium.gltf_viewer",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
        product_note=(
            "Semantic glTF preview/export is available only in Stadium Studio; "
            "package rows retain their exact raw export contract."
        ),
    ),
    "apf2k8.uniforms.catalog": CapabilityActionBinding(
        "apf2k8.uniforms.catalog",
        "uniform.inventory_browser",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
        product_note=(
            "The desktop inventories 408 uniform/equipment records and all 96 "
            "editable material slots; the broader package model is not exposed "
            "as a separate semantic table."
        ),
    ),
    "apf2k8.uniforms.helmet_color_00_23": CapabilityActionBinding(
        "apf2k8.uniforms.helmet_color_00_23",
        "uniform.png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_uniform",
        revert_method="revert",
    ),
    "apf2k8.uniforms.jersey_00_23": CapabilityActionBinding(
        "apf2k8.uniforms.jersey_00_23",
        "uniform.png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_uniform",
        revert_method="revert",
    ),
    "apf2k8.uniforms.jersey_06_runtime": CapabilityActionBinding(
        "apf2k8.uniforms.jersey_06_runtime",
        "uniform.png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_uniform",
        revert_method="revert",
        product_note=(
            "This runtime witness uses the same jersey PNG editor as the 24-slot "
            "jersey writer; it is not a second independent editor."
        ),
    ),
    "apf2k8.uniforms.pants_color_00_23": CapabilityActionBinding(
        "apf2k8.uniforms.pants_color_00_23",
        "uniform.png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_uniform",
        revert_method="revert",
    ),
    "apf2k8.uniforms.shoulder_color_00_23": CapabilityActionBinding(
        "apf2k8.uniforms.shoulder_color_00_23",
        "uniform.png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_uniform",
        revert_method="revert",
    ),
}


UNIFORM_FAMILY_CAPABILITY_IDS: Mapping[str, str] = {
    "jersey": "apf2k8.uniforms.jersey_00_23",
    "pants": "apf2k8.uniforms.pants_color_00_23",
    "helmet": "apf2k8.uniforms.helmet_color_00_23",
    "shoulder": "apf2k8.uniforms.shoulder_color_00_23",
}


ASSET_ACTION_BINDINGS: tuple[AssetActionBinding, ...] = (
    AssetActionBinding(
        capability_id="apf2k8.logos_cards.draft_logo",
        handler_id="asset.draft_logo_png_editor",
        asset_id=DRAFT_LOGO_CATALOG_ID,
        outer_index=DRAFT_LOGO_OUTER_INDEX,
        inner_index=DRAFT_LOGO_INNER_INDEX,
        name="draft_logo",
        type_name="TXTR",
        edit_id=DRAFT_LOGO_EDIT_ID,
        preview_method="preview_draft_logo",
        export_method="export_draft_logo",
        replace_method="replace_draft_logo",
        authoring_note=(
            "128×128 RGBA PNG. This exact draft_logo uses a bounded "
            "single-level BC3 writer."
        ),
        notes=(
            "128×128 RGBA PNG; the bounded writer stores one BC3 base level with no mip chain.",
            "The archive writer is offline-proved. Franchise-menu runtime consumption remains unproved.",
        ),
    ),
    AssetActionBinding(
        capability_id="apf2k8.scorebug_presentation.digital_font",
        handler_id="asset.digital_font_png_editor",
        asset_id=DIGITAL_FONT_CATALOG_ID,
        outer_index=DIGITAL_FONT_OUTER_INDEX,
        inner_index=DIGITAL_FONT_INNER_INDEX,
        name="digital_font",
        type_name="TXTR",
        edit_id=DIGITAL_FONT_EDIT_ID,
        preview_method="preview_digital_font",
        export_method="export_digital_font",
        replace_method="replace_digital_font",
        authoring_note=(
            "128×128 RGBA PNG. RGB stays white; draw the score digits only in alpha."
        ),
        notes=(
            "128×128 RGBA PNG; RGB stays white and the glyph mask is authored in alpha.",
            "This is a shared global texture whose on-screen consumers remain under study.",
        ),
    ),
)


def capability_action_binding(
    capability_id: str,
) -> CapabilityActionBinding | None:
    return CAPABILITY_ACTION_BINDINGS.get(capability_id)


def asset_action_binding(
    asset_id: str,
    outer_index: int,
    inner_index: int | None,
    name: str,
    type_name: str,
) -> AssetActionBinding | None:
    for binding in ASSET_ACTION_BINDINGS:
        if binding.matches(asset_id, outer_index, inner_index, name, type_name):
            return binding
    return None


class ApfCategory(str, Enum):
    GETTING_STARTED = "getting_started"
    UNIFORMS = "uniforms"
    ROSTERS = "rosters"
    TEAM_IDENTITY = "team_identity"
    LOGOS = "logos"
    SCOREBUG = "scorebug"
    FIELD_ART = "field_art"
    STADIUMS = "stadiums"
    MENUS = "menus"
    AUDIO = "audio"
    GAMEPLAY = "gameplay"
    PLAYBOOKS = "playbooks"
    FRANCHISE = "franchise"
    ALL_ASSETS = "all_assets"

    @property
    def title(self) -> str:
        return {
            self.GETTING_STARTED: "Getting Started",
            self.UNIFORMS: "Uniforms & Equipment",
            self.ROSTERS: "Rosters & Players",
            self.TEAM_IDENTITY: "Team Identity",
            self.LOGOS: "Logos & Team Art",
            self.SCOREBUG: "Scorebug & Presentation",
            self.FIELD_ART: "Field Art",
            self.STADIUMS: "Stadium Studio",
            self.MENUS: "Menus & Text",
            self.AUDIO: "Audio",
            self.GAMEPLAY: "Sliders & Gameplay",
            self.PLAYBOOKS: "Playbooks & Plays",
            self.FRANCHISE: "Season & Franchise Lab",
            self.ALL_ASSETS: "All Game Assets",
        }[self]


APF_CATEGORY_ORDER: tuple[ApfCategory, ...] = tuple(ApfCategory)


@dataclass(frozen=True)
class ApfSource:
    """Validated, user-owned APF extracted game tree."""

    selected_path: Path
    game_root: Path
    index_0a: Path
    source_sha256: str
    source_size: int
    xex_sha256: str
    display_name: str
    extracted_from_iso: bool = False
    source_iso_sha256: str | None = None


@dataclass(frozen=True)
class ApfAsset:
    asset_id: str
    outer_index: int
    inner_index: int | None
    name: str
    type_name: str
    asset_class: str
    category: ApfCategory
    status: ApfStatus
    decoded_size: int
    outer_size: int
    part_count: int
    notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def location(self) -> str:
        if self.inner_index is None:
            return f"outer {self.outer_index}"
        return f"outer {self.outer_index} / inner {self.inner_index}"

    @property
    def export_label(self) -> str:
        """Describe what the universal-browser Export action actually emits."""

        if self.type_name == "XMA1_BANK":
            return "Original external XMA1 bank (.bin)"
        if self.status is ApfStatus.EDITABLE and self.type_name == "TXTR":
            return "Editable PNG"
        if self.type_name == "TXTR":
            return "PNG when decoded; raw ZIP always"
        if self.type_name == "AUDO":
            return "XMA/WAV or raw ZIP"
        if self.inner_index is None:
            return "Raw record only"
        return "Raw parts ZIP only"


@dataclass(frozen=True)
class ExternalAudioBankOwner:
    """One AUSB descriptor that addresses a physical external packet bank."""

    descriptor_outer_index: int
    descriptor_inner_index: int
    bank_name: str
    substream_count: int
    sample_rate: int
    channel_count: int

    @property
    def audio_source_id(self) -> str:
        return (
            f"ausb:{self.descriptor_outer_index}:"
            f"{self.descriptor_inner_index}"
        )

    @property
    def coordinates(self) -> tuple[int, int]:
        return self.descriptor_outer_index, self.descriptor_inner_index


@dataclass(frozen=True)
class ExternalAudioBankIdentity:
    """Source-derived ownership contract for one raw external XMA1 bank.

    This identifies a physical read-only outer record.  It deliberately does
    not make the container playable or writable: its AUSB-addressed substreams
    remain the only playable rows, and replacement still has no safe writer.
    """

    external_filename: str
    outer_table_index: int
    name_id: int
    encoded_size: int
    owners: tuple[ExternalAudioBankOwner, ...]

    @property
    def raw_asset_id(self) -> str:
        return f"apf:outer:{self.outer_table_index}"

    @property
    def linked_audio_source_ids(self) -> tuple[str, ...]:
        return tuple(owner.audio_source_id for owner in self.owners)


@dataclass(frozen=True)
class UniformAsset:
    family: str
    asset_index: int
    asset_id: str
    title: str
    width: int
    height: int
    png_contract: str
    status: ApfStatus
    outer_index: int
    inner_index: int
    affected_teams: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilityCard:
    capability_id: str
    title: str
    summary: str
    category: ApfCategory
    status: ApfStatus
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Modification:
    asset_id: str
    kind: str
    replacement_path: Path
    replacement_sha256: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class BuildReceipt:
    output_game: Path
    output_0a: Path
    manifest: Path
    modified_assets: tuple[str, ...]
    changed_outer_entries: tuple[int, ...]
    output_0a_sha256: str
    source_unchanged: bool
