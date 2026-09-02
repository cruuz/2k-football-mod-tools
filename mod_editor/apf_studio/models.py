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
NUMBER_TEXTURE_KIND = "number_texture"
NUMBER_TEXTURE_WRITER_SCHEMA = "apf_number_texture_patch/v1"


class ApfProductAction(str, Enum):
    """User-visible actions that an APF product handler actually implements."""

    PREVIEW = "preview"
    EXPORT = "export"
    REPLACE = "replace"
    REVERT = "revert"
    BUILD_COPY = "build-copy"


class ApfStatus(str, Enum):
    EDITABLE = "Editable"
    PREVIEW = "Preview"
    EXPORT_ONLY = "Export-only"
    COMING_SOON = "Coming Soon"
    EVIDENCE = "Proof boundary"
    RESEARCH = "Research boundary"


@dataclass(frozen=True)
class CapabilityActionBinding:
    """One reviewed bridge from a capability row to a concrete product route.

    A capability omitted from :data:`CAPABILITY_ACTION_BINDINGS` remains a clearly
    labeled research/proof boundary. Registry classification alone never fabricates
    a button.
    """

    capability_id: str
    handler_id: str
    actions: frozenset[ApfProductAction]
    replace_method: str | None = None
    revert_method: str | None = None
    product_note: str = ""
    additional_replace_methods: tuple[str, ...] = ()
    one_shot_target: str | None = None
    output_kind: str = ""

    @property
    def has_complete_editor(self) -> bool:
        return (
            {ApfProductAction.REPLACE, ApfProductAction.REVERT}
            <= self.actions
            and bool(self.replace_method)
            and bool(self.revert_method)
        )

    @property
    def has_verified_one_shot_writer(self) -> bool:
        """Whether the action publishes a verified copy instead of staging Undo.

        Source-bound model imports never mutate the loaded game or the project edit
        map, so inventing a Revert action would be misleading.  They are complete
        editors when their concrete callable and copied-volume output are named.
        """

        return (
            ApfProductAction.BUILD_COPY in self.actions
            and bool(self.one_shot_target)
            and bool(self.output_kind)
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
            "together. A selected sound can start from ordinary decodable audio "
            "(including WAV, MP3, FLAC, OGG and M4A): Mod Studio conforms it to the "
            "target PCM shape before running a user-configured external XMA1 encoder. "
            "Batch packs remain pre-encoded XMA1 or exact PCM16 WAV. "
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
            "from ordinary decodable audio (including WAV, MP3, FLAC, OGG and M4A); "
            "it is conformed to the target PCM shape before the user-configured "
            "external XMA1 encoder runs. No encoder ships with Mod Studio, and "
            "batch packs remain pre-encoded XMA1 or exact PCM16 WAV."
        ),
    ),
    "apf2k8.colors.uniform_selector_bytes": CapabilityActionBinding(
        "apf2k8.colors.uniform_selector_bytes",
        "team_identity.selector_inspector",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
    ),
    "apf2k8.colors.uniform_selector_appearance_custom_team": CapabilityActionBinding(
        "apf2k8.colors.uniform_selector_appearance_custom_team",
        "uniforms.custom_team_appearance_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_custom_team_appearance",
        revert_method="revert",
        product_note=(
            "Equipment Colors independently selects each HOME/AWAY facemask-bar "
            "and Team-turtleneck palette index for all 40 teams; it changes only "
            "proved selector slot 3 byte 6 and slot 0 byte 2. Player visors remain "
            "the separate None/Clear/Dark choice because APF has no per-uniform "
            "visor tint. The Custom Team Appearance tab edits only user slots 32–39. HOME "
            "and AWAY each expose ten ARGB colors, a bounded helmet asset and "
            "proved shell-palette index, a bounded crest catalog asset, and "
            "truthfully opaque selector bytes. The 2017 Eagles preset preserves "
            "the helmet model and helmet tail, selects crest 30 with its complete "
            "Xenia-proved routing tail, and composes through the common "
            "ROST transaction. Team Logo builds can include the staged slot in "
            "the same copied 0A as the crest package and logo cache."
        ),
    ),
    "apf2k8.cross_title_model_conversion.nfl_to_apf": CapabilityActionBinding(
        "apf2k8.cross_title_model_conversion.nfl_to_apf",
        "stadium.cross_title_model_compatibility_inspector",
        _actions(ApfProductAction.PREVIEW),
        product_note=(
            "The Stadium research surface presents the mapped cross-title geometry "
            "compatibility findings. It does not claim a conversion writer."
        ),
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
            "The Field Art editor writes the original six offline-proved base "
            "textures (endzone_l0/l1, pc_field_goal, Field_Pass_text, "
            "Stride_number_field, divots), package-659 weave/dirtmaps, and "
            "format-18 endzones into a copied 0A through "
            "tools/apf_field_art_patch.py -- one texture per build. Each build "
            "regenerates only the selected base mip level; the descriptor pad, "
            "the packed mip tail, and every sibling inner part are verified "
            "unchanged against the whole volume, and the read-only source is "
            "never opened for writing. Format-59 DXT5A endzones, the deferred "
            "field_radiance and divot_Grass* codecs, and the SCNE/CurveAnim "
            "rows have no bounded writer and stay export-only. In-game "
            "appearance is not proved without a Xenia capture."
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
    "apf2k8.logos_cards.uniform_catalog": CapabilityActionBinding(
        "apf2k8.logos_cards.uniform_catalog",
        "logos.uniform_and_textlogo_catalog",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
        product_note=(
            "The universal logo browser previews and exports every decoded catalog "
            "row. Team Logo owns the separate coupled package/cache writer; text "
            "logos and menu-card descriptor families retain their exact export route."
        ),
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
        replace_method="replace_helmet_crest_design",
        revert_method="revert",
        product_note=(
            "The Team Logo editor stages one exact 512x512 RGBA crest, and one "
            "build co-writes the two linked selector-slot-5 owners at crest index "
            "N: the selected team's uniform_logo_NN package (logo_l0/logo_l1) through "
            "tools/apf_logo_patch.py "
            "and index N of the prebuilt uniform_logocache aggregate "
            "through tools/apf_logocache_patch.py, chained over one intermediate "
            "copy. Static XEX ownership maps that aggregate to the frontend LOGOS / "
            "Team Select path. The rectangular uniform_textlogo wordmark is a "
            "separate selector-slot-6 owner in Wordmarks; Team Logo never resizes "
            "or writes it. Each writer byte-diffs the whole copied volume so only its "
            "own fixed extents change, each is paired with an independent "
            "verifier, and the read-only source is never opened for writing. "
            "Colors are stored at 4 bits per channel and the build reports the "
            "exact decode-back error. Both writers regenerate the packed mip "
            "levels from the new base, so the crest is right at every "
            "distance rather than only in close-up. Package/cache writeback and "
            "static shell appearance are proved. The frontend cache path is "
            "statically mapped, but changed-logo runtime consumption, the scorebug's "
            "package-versus-cache resolver, and Xbox 360 hardware parity remain "
            "unproved."
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
        replace_method="replace_helmet_crest_design",
        revert_method="revert",
        product_note=(
            "This statically mapped frontend/Team Select logo cache is a coupled "
            "companion of the team-logo "
            "package: the single Team Logo build writes it from the same staged "
            "512x512 crest through tools/apf_logocache_patch.py at the "
            "selected team's catalog index, rewriting the matching entry of "
            "the prebuilt uniform_logocache "
            "aggregate and verifying every other byte unchanged. There is no "
            "cache-only editor -- staging or reverting the Team Logo crest "
            "stages or reverts this cache write with it -- so it shares the "
            "team-logo replace/revert route. It is linked by the same selector-slot-5 "
            "index; the independent selector-slot-6 uniform_textlogo wordmark stays "
            "under Wordmarks and is never derived from this square crest. The writer re-checks its pinned "
            "retail directory and payload and fails closed. Changed-cache gameplay "
            "or frontend consumption, the scorebug resolver, and Xbox 360 hardware "
            "parity remain unproved."
        ),
    ),
    "apf2k8.logos_cards.textlogo_wordmarks": CapabilityActionBinding(
        "apf2k8.logos_cards.textlogo_wordmarks",
        "logos_cards.textlogo_wordmark_png_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_uniform",
        revert_method="revert",
        product_note=(
            "The Wordmark editor owns all 206 selector-slot-6 "
            "uniform_textlogo_00..205 packages. It prepares ordinary artwork "
            "with explicit Contain or Cover fitting on the native 512x128 "
            "canvas, flattens transparency onto the retail black background, "
            "regenerates all six tiled BC1 mips, and rebuilds only the selected "
            "fixed-allocation package in the normal shareable project/Build. "
            "This rectangular selector-slot-6 menu/uniform wordmark is deliberately "
            "separate from the selector-slot-5 square helmet crest and its linked "
            "frontend/Team Select uniform_logocache index. Team Logo never squeezes "
            "or copies a crest into this wordmark family."
        ),
    ),
    "apf2k8.models.scne_gltf": CapabilityActionBinding(
        "apf2k8.models.scne_gltf",
        "uniforms.model_position_roundtrip",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.BUILD_COPY,
        ),
        one_shot_target="mod_editor.apf_studio.model_import:import_model",
        output_kind="verified copied 0A",
        product_note=(
            "Uniforms & Equipment exposes dedicated helmet/player glTF export and "
            "same-topology POSITION-only import buttons. Import creates a new "
            "source-bound 0A immediately rather than staging a shareable project "
            "replacement; materials, topology, transforms, skin data, normals, "
            "packed UV/tangent data, animation, and collision are rejected."
        ),
    ),
    "apf2k8.models.scne_same_count_position": CapabilityActionBinding(
        "apf2k8.models.scne_same_count_position",
        "stadium.selected_mesh_position_roundtrip",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.BUILD_COPY,
        ),
        one_shot_target=(
            "mod_editor.apf_studio.stadium_model_import:import_edited_mesh"
        ),
        output_kind="verified copied 1A",
        product_note=(
            "Stadium Studio exports a clicked catalog-authorized mesh and imports "
            "same-count POSITION edits into a separately verified copied 1A. The "
            "loaded source and project edit map remain unchanged, so this complete "
            "one-shot writer correctly has no staged Revert action."
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
    "apf2k8.mode_state_routing.state_graph": CapabilityActionBinding(
        "apf2k8.mode_state_routing.state_graph",
        "menus.mode_state_graph_inspector",
        _actions(ApfProductAction.PREVIEW),
        product_note=(
            "The Menus research surface exposes the mapped state/transition graph "
            "as an inspector; it does not claim layout or executable writeback."
        ),
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
            "Every player also exposes 31 independent native base ratings with "
            "exact 0–99 Replace/Revert; a source native 100 remains visible and "
            "revertible but cannot be applied as a new edit. Every player position "
            "also has bounded 0–16 Replace/Revert through a 17-choice desktop "
            "dropdown and the paired "
            "semantic +0x34 and source-mirror +0x35 bytes. That position writer "
            "is offline-proved; its first Xenia spot check is still pending. "
            "CODEXTEAM and Dan "
            "CODEX both rendered in Xenia. The rating candidate also booted and "
            "loaded Dan Marino, though its star-selection UI had no numeric byte "
            "readout. Both abbreviation fields and zero-capacity names in the "
            "on-disc project route remain locked. The separate Save Players "
            "workspace authors exact raw-save jersey, tier, abilities, depth, "
            "appearance/equipment, all 15 fixed-allocation player text fields, "
            "and safe membership swaps. Overall and active-capacity expansion "
            "remain locked because their complete engine contracts are not proved."
        ),
        additional_replace_methods=(
            "replace_player_base_rating",
            "replace_player_position",
        ),
    ),
    "apf2k8.portraits_faces.hi_head": CapabilityActionBinding(
        "apf2k8.portraits_faces.hi_head",
        "rosters.face_head_reference_export",
        _actions(ApfProductAction.PREVIEW, ApfProductAction.EXPORT),
        product_note=(
            "The Rosters asset browser previews supported rows and preserves the "
            "exact source-bound head/face reference export route. No importer is claimed."
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
        "playbook.stock_assignment_routes",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="replace_play_assignment_route",
        revert_method="revert",
        additional_replace_methods=("swap_play_assignment_routes",),
        product_note=(
            "Assignment Routes copies or atomically swaps exact stock descriptor/"
            "chain assignments. Route-node waypoint/opcode authoring remains locked."
        ),
    ),
    "apf2k8.schedules_franchise.retained": CapabilityActionBinding(
        "apf2k8.schedules_franchise.retained",
        "franchise.retained_structure_inspector",
        _actions(ApfProductAction.PREVIEW),
        product_note=(
            "The Franchise page presents the retained season/schedule findings as "
            "a bounded inspector; no franchise-mode writer is claimed."
        ),
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
    "apf2k8.stadiums.textures": CapabilityActionBinding(
        "apf2k8.stadiums.textures",
        "stadium.embedded_texture_editor",
        _actions(
            ApfProductAction.PREVIEW,
            ApfProductAction.EXPORT,
            ApfProductAction.REPLACE,
            ApfProductAction.REVERT,
        ),
        replace_method="stage_stadium_texture",
        revert_method="revert_stadium_texture",
        product_note=(
            "Stadium Studio owns this specialized route: clicked outer-14/inner-8 "
            "surfaces expose only their statically joined embedded textures, stage "
            "a native-size private PNG, and build a new copied 1A."
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
    "textlogo": "apf2k8.logos_cards.textlogo_wordmarks",
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
