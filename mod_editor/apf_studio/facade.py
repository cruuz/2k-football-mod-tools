"""Thin product facade consumed by the APF Qt shell."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Callable, Iterable

from .audio_batch_export import (
    ApfAudioBatchExporter,
    ApfExternalAudioBankBundleExporter,
    AudioBatchProgress,
    AudioBatchReceipt,
    ExternalAudioBankBundleProgress,
    ExternalAudioBankBundleReceipt,
)
from .audio_annotations import (
    AudioCueAnnotation,
    MAX_AUDIO_ANNOTATIONS,
)
from .audio_replacement_pack import (
    AudioReplacementApplyProgress,
    AudioReplacementApplyReceipt,
    AudioReplacementPackError,
    AudioReplacementPreviewReceipt,
    AudioReplacementTemplateReceipt,
    create_audio_replacement_template,
    load_audio_replacement_pack,
    open_audio_replacement_pack,
)
from .audio_encoding import (
    ExternalXma1Encoder,
    Pcm16Target,
    Pcm16TemplateReceipt,
)
from .asset_io import ApfAssetIO
from .build import ApfBuildService
from .catalog import ApfCatalog, CatalogBuilder
from .inspectors import (
    ApfInspectorService,
    ExportIdentity,
    InspectorRow,
    PagedModel,
    export_player_rating_sheet,
    export_semantic_rows,
)
from .launcher import LaunchReceipt, XeniaLauncher
from .models import (
    ApfAsset,
    ApfCategory,
    ApfSource,
    ApfStatus,
    BuildReceipt,
    CapabilityCard,
    DRAFT_LOGO_CATALOG_ID,
    ExternalAudioBankIdentity,
    Modification,
    UniformAsset,
)
from .project import ProjectError, ProjectTargetIdentity, project_target_identity
from .player_rating_sheet import (
    PlayerRatingSheetApplyReceipt,
    PlayerRatingSheetPreviewReceipt,
    apply_player_rating_sheet as apply_private_player_rating_sheet,
    preview_player_rating_sheet as preview_private_player_rating_sheet,
)
from .roster_workspace import (
    ReserveRosterPlan,
    RosterWorkspace,
    RosterWorkspaceError,
    bind_membership_rows,
    load_reserve_plan,
    save_reserve_plan,
)
from .session import ApfSession
from .source import SourceManager
from .stadium import ApfStadiumPreview, ApfStadiumScene
from .text_sheet import (
    TextSheetExportReceipt,
    TextSheetImportReceipt,
    export_text_sheet,
    import_text_sheet,
)


Progress = Callable[[str, int, int], None]


ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE = (
    "Team display names and player first/last names are editable through the "
    "runtime-proved token-preserving route. Team abbreviations, jersey numbers, "
    "membership, depth charts, and mixed or unknown identity allocations remain "
    "runtime-locked until each route is separately proved."
)

TEAM_DISPLAY_NAME_EDIT_SCOPE_MESSAGE = (
    "Team display-name replacement uses the runtime-proved token-preserving ROST "
    "transport. The replacement must fit the source allocation; the source game "
    "is never changed and this one edit can be reverted."
)


def _noop(_stage: str, _completed: int, _total: int) -> None:
    return None


class FacadeError(RuntimeError):
    """Raised when an action requires a loaded source first."""


class ApfStudioFacade:
    def __init__(
        self,
        *,
        cache_root: Path | None = None,
        source_manager: SourceManager | None = None,
        launcher: XeniaLauncher | None = None,
    ):
        self.cache_root = cache_root
        self.source_manager = source_manager or SourceManager(cache_root=cache_root)
        self.catalog_builder = CatalogBuilder(cache_root=cache_root)
        self.launcher = launcher or XeniaLauncher()
        self.source: ApfSource | None = None
        self.catalog: ApfCatalog | None = None
        self.session: ApfSession | None = None
        self.inspectors: ApfInspectorService | None = None
        self.last_build: BuildReceipt | None = None
        self.last_project_identity: ProjectTargetIdentity | None = None
        self._playable_audio_rows: dict[str, InspectorRow] | None = None
        # A 53-player planning roster deliberately remains separate from the
        # playable 42-membership ROST edit set.  It contains only user-selected
        # reserve player indices and is reset whenever the loaded game changes.
        self._reserve_roster_plan = ReserveRosterPlan.empty()
        # Private recovery saves run off the GUI thread.  Every mutation and
        # session swap participates in this same boundary so an autosave can
        # never be published from one source and labeled as another.
        self._session_lock = RLock()

    @property
    def source_ready(self) -> bool:
        return self.source is not None and self.catalog is not None and self.session is not None

    @property
    def source_display_name(self) -> str:
        return self.source.display_name if self.source else "No game loaded"

    @property
    def modified_asset_ids(self) -> frozenset[str]:
        return self.session.modified_asset_ids if self.session else frozenset()

    @property
    def modified_count(self) -> int:
        return self.session.modified_count if self.session else 0

    @property
    def annotation_count(self) -> int:
        return self.session.annotation_count if self.session else 0

    @property
    def project_metadata_count(self) -> int:
        return self.session.project_metadata_count if self.session else 0

    @property
    def has_project_metadata(self) -> bool:
        return bool(self.session and self.session.has_project_metadata)

    @property
    def audio_annotations(self) -> tuple[AudioCueAnnotation, ...]:
        return self.session.audio_annotations if self.session else ()

    @property
    def project_change_count(self) -> int:
        return self.modified_count + self.project_metadata_count

    @property
    def labeled_audio_asset_ids(self) -> frozenset[str]:
        return (
            self.session.labeled_audio_asset_ids
            if self.session is not None
            else frozenset()
        )

    @property
    def can_undo(self) -> bool:
        return bool(self.session and self.session.can_undo)

    @property
    def can_launch_xenia(self) -> bool:
        return self.last_build is not None and self.launcher.settings.configured

    def load_source(self, selected: Path, progress: Progress = _noop) -> ApfCatalog:
        with self._session_lock:
            source = self.source_manager.resolve(selected, progress)
            catalog = self.catalog_builder.build(source, progress)
            new_session = ApfSession(source, catalog, cache_root=self.cache_root)
            try:
                new_inspectors = ApfInspectorService(source)
            except BaseException:
                new_session.close()
                raise
            previous_session = self.session
            if previous_session is not None:
                previous_session.close()
            self.source = source
            self.catalog = catalog
            self.session = new_session
            self.inspectors = new_inspectors
            self.last_build = None
            self.last_project_identity = None
            self._playable_audio_rows = None
            self._reserve_roster_plan = ReserveRosterPlan.empty()
            return catalog

    def require_catalog(self) -> ApfCatalog:
        if self.catalog is None:
            raise FacadeError("Load your APF 2K8 game first")
        return self.catalog

    def require_session(self) -> ApfSession:
        if self.session is None:
            raise FacadeError("Load your APF 2K8 game first")
        return self.session

    def require_inspectors(self) -> ApfInspectorService:
        if self.inspectors is None:
            raise FacadeError("Load your APF 2K8 game first")
        return self.inspectors

    def _live_playable_audio_rows(self) -> dict[str, InspectorRow]:
        if self._playable_audio_rows is None:
            snapshot = self.require_inspectors().audio()
            rows = (*snapshot.audo.rows, *snapshot.ausb_substreams.rows)
            playable = {
                row.row_id: row
                for row in rows
                if row.export_identity is not None
                and row.export_identity.kind in {"audo", "ausb_substream"}
            }
            if len(playable) != MAX_AUDIO_ANNOTATIONS or len(playable) != len(rows):
                raise FacadeError(
                    "The loaded APF audio cue inventory changed; cue labels were "
                    "left untouched"
                )
            self._playable_audio_rows = playable
        return self._playable_audio_rows

    def _require_playable_audio_row(self, asset_id: str) -> InspectorRow:
        if type(asset_id) is not str:
            raise FacadeError("Choose one individual APF sound to label")
        row = self._live_playable_audio_rows().get(asset_id)
        if row is None:
            raise FacadeError(
                "Audio labels apply only to one standalone AUDO sound or one "
                "individual AUSB substream"
            )
        return row

    def audio_annotation(self, asset_id: str) -> AudioCueAnnotation | None:
        with self._session_lock:
            row = self._require_playable_audio_row(asset_id)
            return self.require_session().audio_annotation(row.row_id)

    def set_audio_annotation(
        self,
        asset_id: str,
        title: str = "",
        note: str = "",
    ) -> bool:
        with self._session_lock:
            row = self._require_playable_audio_row(asset_id)
            return self.require_session().set_audio_annotation(
                row.row_id, title, note
            )

    def clear_audio_annotation(self, asset_id: str) -> bool:
        with self._session_lock:
            row = self._require_playable_audio_row(asset_id)
            return self.require_session().clear_audio_annotation(row.row_id)

    def audio_row_with_annotation(self, row: InspectorRow) -> InspectorRow:
        """Overlay user metadata without changing cue identity or coordinates."""

        session = self.require_session()
        labeled_ids = getattr(session, "labeled_audio_asset_ids", frozenset())
        annotation = (
            session.audio_annotation(row.row_id)
            if isinstance(labeled_ids, (set, frozenset))
            and row.row_id in labeled_ids
            else None
        )
        return self._overlay_audio_annotation(row, annotation)

    @staticmethod
    def _overlay_audio_annotation(
        row: InspectorRow,
        annotation: AudioCueAnnotation | None,
    ) -> InspectorRow:
        if annotation is None:
            return row
        fields = dict(row.fields)
        fields.update(
            {
                "game_catalog_title": row.title,
                "custom_title": annotation.title or None,
                "annotation_note": annotation.note or None,
            }
        )
        effective_title = annotation.title or row.title
        annotation_search = " ".join(
            value for value in (annotation.title, annotation.note) if value
        ).casefold()
        return replace(
            row,
            title=effective_title,
            fields=fields,
            _search_text=(
                f"{row._search_text} {annotation_search}".strip()
            ),
        )

    def annotated_audio_rows(
        self,
        rows: Iterable[InspectorRow],
        *,
        labeled_only: bool = False,
    ) -> tuple[InspectorRow, ...]:
        """Overlay cue labels, optionally restricting to labeled cues only."""
        if type(labeled_only) is not bool:
            raise FacadeError("Audio labeled-only filter is invalid.")
        annotations = {
            annotation.cue_id: annotation
            for annotation in getattr(
                self.require_session(), "audio_annotations", ()
            )
        }
        overlaid: list[InspectorRow] = []
        for row in rows:
            annotation = annotations.get(row.row_id)
            if labeled_only and annotation is None:
                continue
            overlaid.append(self._overlay_audio_annotation(row, annotation))
        return tuple(overlaid)

    @property
    def reserve_roster_plan(self) -> ReserveRosterPlan:
        """Return the replacement-only 32-by-11 planning layer.

        This is intentionally not a game modification.  The first 42 players
        remain source-derived and private; only the eleven authored reserve
        indices per team can be saved to ``.apf2k8roster``.
        """

        return self._reserve_roster_plan

    def roster_workspace(self) -> RosterWorkspace:
        """Bind the current reserve plan to the loaded source's exact 32x42 view."""

        rows = self.require_inspectors().roster().model.rows
        memberships = tuple(
            row.fields for row in rows if row.kind == "membership"
        )
        try:
            return bind_membership_rows(self._reserve_roster_plan, memberships)
        except RosterWorkspaceError as exc:
            raise FacadeError(f"Could not build the 53-player planning view: {exc}") from exc

    def assign_roster_reserve(
        self,
        team_index: int,
        reserve_slot: int,
        player_index: int | None,
    ) -> RosterWorkspace:
        """Assign one project-only reserve after checking the live 42-player rosters."""

        with self._session_lock:
            try:
                proposed = self._reserve_roster_plan.assign(
                    team_index, reserve_slot, player_index
                )
                rows = self.require_inspectors().roster().model.rows
                workspace = bind_membership_rows(
                    proposed,
                    (row.fields for row in rows if row.kind == "membership"),
                )
            except RosterWorkspaceError as exc:
                raise FacadeError(f"Could not assign the project reserve: {exc}") from exc
            self._reserve_roster_plan = proposed
            return workspace

    def open_roster_reserve_plan(self, source: Path) -> RosterWorkspace:
        """Load and live-bind one retail-free 32-team reserve plan."""

        with self._session_lock:
            try:
                proposed = load_reserve_plan(source)
                rows = self.require_inspectors().roster().model.rows
                workspace = bind_membership_rows(
                    proposed,
                    (row.fields for row in rows if row.kind == "membership"),
                )
            except (OSError, RosterWorkspaceError) as exc:
                raise FacadeError(f"Could not open the reserve roster plan: {exc}") from exc
            self._reserve_roster_plan = proposed
            return workspace

    def save_roster_reserve_plan(self, destination: Path) -> Path:
        """Save only authored reserve indices; no source memberships are serialized."""

        with self._session_lock:
            # Rebind immediately before publication so a stale or colliding
            # plan can never be labeled valid for the loaded source.
            self.roster_workspace()
            try:
                return save_reserve_plan(self._reserve_roster_plan, destination)
            except (OSError, RosterWorkspaceError) as exc:
                raise FacadeError(f"Could not save the reserve roster plan: {exc}") from exc

    def browse_assets(
        self,
        *,
        search: str = "",
        category: ApfCategory | None = None,
        status: ApfStatus | None = None,
        type_name: str | None = None,
        offset: int = 0,
        limit: int = 250,
    ) -> tuple[ApfAsset, ...]:
        return self.require_catalog().browse(
            search=search,
            category=category,
            status=status,
            type_name=type_name,
            offset=offset,
            limit=limit,
        )

    def uniform_assets(self, family: str | None = None) -> tuple[UniformAsset, ...]:
        values = self.require_catalog().uniform_assets
        return values if family is None else tuple(item for item in values if item.family == family)

    def capability_cards(self, category: ApfCategory | None = None) -> tuple[CapabilityCard, ...]:
        values = self.require_catalog().capabilities
        return values if category is None else tuple(item for item in values if item.category is category)

    def preview_uniform(self, asset_id: str, progress: Progress = _noop) -> Path:
        progress("Preparing uniform preview", 0, 0)
        return self.require_session().asset_io.preview_uniform(asset_id)

    def export_uniform(self, asset_id: str, destination: Path, progress: Progress = _noop) -> Path:
        progress("Exporting uniform PNG", 0, 0)
        return self.require_session().asset_io.export_uniform(asset_id, destination)

    def replace_uniform(
        self, asset_id: str, supplied_png: Path, progress: Progress = _noop
    ) -> Modification:
        with self._session_lock:
            progress("Checking replacement PNG", 0, 0)
            result = self.require_session().replace_uniform(asset_id, supplied_png)
            self.last_build = None
            return result

    def preview_digital_font(self, progress: Progress = _noop) -> Path:
        progress("Preparing digital_font preview", 0, 0)
        return self.require_session().asset_io.preview_digital_font()

    def export_digital_font(self, destination: Path, progress: Progress = _noop) -> Path:
        progress("Exporting digital_font PNG", 0, 0)
        return self.require_session().asset_io.export_digital_font(destination)

    def replace_digital_font(
        self, supplied_png: Path, progress: Progress = _noop
    ) -> Modification:
        with self._session_lock:
            progress("Checking digital_font PNG", 0, 0)
            result = self.require_session().replace_digital_font(supplied_png)
            self.last_build = None
            return result

    def preview_draft_logo(self, progress: Progress = _noop) -> Path:
        progress("Preparing draft logo preview", 0, 0)
        return self.require_session().asset_io.preview_texture(
            DRAFT_LOGO_CATALOG_ID
        )

    def export_draft_logo(
        self, destination: Path, progress: Progress = _noop
    ) -> Path:
        progress("Exporting draft logo PNG", 0, 0)
        return self.require_session().asset_io.export_asset(
            DRAFT_LOGO_CATALOG_ID, destination
        )

    def replace_draft_logo(
        self, supplied_png: Path, progress: Progress = _noop
    ) -> Modification:
        with self._session_lock:
            progress("Checking draft logo PNG", 0, 0)
            result = self.require_session().replace_draft_logo(supplied_png)
            self.last_build = None
            return result

    def localization_text_allocations(self) -> tuple[object, ...]:
        return self.require_session().localization_text_allocations()

    def localization_text_value(self, asset_id: str) -> str:
        return self.require_session().localization_text_value(asset_id)

    def replace_localization_text(
        self,
        asset_id: str,
        replacement: str,
        progress: Progress = _noop,
    ) -> Modification:
        with self._session_lock:
            progress("Checking text allocation", 0, 1)
            result = self.require_session().replace_localization_text(
                asset_id, replacement
            )
            progress("Checking text allocation", 1, 1)
            self.last_build = None
            return result

    def roster_identity_allocations(self) -> tuple[object, ...]:
        return self.require_session().roster_identity_allocations()

    def roster_identity_value(self, asset_id: str) -> str:
        return self.require_session().roster_identity_value(asset_id)

    def roster_identity_edit_scope(self, asset_id: str) -> str | None:
        return self.require_session().roster_identity_edit_scope(asset_id)

    def roster_identity_is_product_editable(self, asset_id: str) -> bool:
        return self.require_session().roster_identity_is_product_editable(
            asset_id
        )

    def replace_roster_identity_text(
        self,
        asset_id: str,
        replacement: str,
        progress: Progress = _noop,
    ) -> Modification:
        with self._session_lock:
            session = self.require_session()
            if not session.roster_identity_is_product_editable(asset_id):
                raise FacadeError(ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE)
            progress("Checking roster-name allocation", 0, 1)
            result = session.replace_roster_identity_text(asset_id, replacement)
            progress("Checking roster-name allocation", 1, 1)
            self.last_build = None
            return result

    def player_base_rating_value(self, player_index: int, field_id: str) -> int:
        return self.require_session().player_base_rating_value(
            player_index, field_id
        )

    def replace_player_base_rating(
        self,
        player_index: int,
        field_id: str,
        value: int,
        progress: Progress = _noop,
    ) -> Modification:
        with self._session_lock:
            progress("Checking player base rating", 0, 1)
            result = self.require_session().replace_player_base_rating(
                player_index, field_id, value
            )
            progress("Checking player base rating", 1, 1)
            self.last_build = None
            return result

    def player_position_value(self, player_index: int) -> int:
        return self.require_session().player_position_value(player_index)

    def replace_player_position(
        self,
        player_index: int,
        value: int,
        progress: Progress = _noop,
    ) -> Modification:
        with self._session_lock:
            progress("Checking player position", 0, 1)
            result = self.require_session().replace_player_position(
                player_index, value
            )
            progress("Checking player position", 1, 1)
            self.last_build = None
            return result

    def export_localization_text_sheet(
        self,
        destination: Path,
        progress: Progress = _noop,
    ) -> TextSheetExportReceipt:
        progress("Exporting APF text sheet", 0, 1)
        result = export_text_sheet(self.require_session(), destination)
        progress("Exporting APF text sheet", 1, 1)
        return result

    def import_localization_text_sheet(
        self,
        source: Path,
        progress: Progress = _noop,
    ) -> TextSheetImportReceipt:
        with self._session_lock:
            progress("Validating APF text sheet", 0, 1)
            result = import_text_sheet(self.require_session(), source)
            progress("Applying APF text sheet", 1, 1)
            if result.changed_count:
                self.last_build = None
            return result

    def preview_asset(self, asset_id: str, progress: Progress = _noop) -> Path:
        progress("Preparing texture preview", 0, 0)
        return self.require_session().asset_io.preview_texture(asset_id)

    def export_asset(self, asset_id: str, destination: Path, progress: Progress = _noop) -> Path:
        progress("Exporting game asset", 0, 0)
        return self.require_session().asset_io.export_asset(asset_id, destination)

    def stadium_scenes(self, search: str = "") -> tuple[ApfStadiumScene, ...]:
        return self.require_session().asset_io.stadium_scenes(search)

    def stadium_package_assets(
        self, scene: ApfStadiumScene | str
    ) -> tuple[ApfAsset, ...]:
        return self.require_session().asset_io.stadium_package_assets(scene)

    def prepare_stadium_scene(
        self,
        scene: ApfStadiumScene | str,
        progress: Progress = _noop,
    ) -> ApfStadiumPreview:
        return self.require_session().asset_io.prepare_stadium_scene(
            scene, progress
        )

    def export_stadium_scene_bundle(
        self,
        scene: ApfStadiumScene | str,
        destination: Path,
        progress: Progress = _noop,
    ) -> Path:
        return self.require_session().asset_io.export_stadium_scene_bundle(
            scene, destination, progress
        )

    def export_audio_identity(
        self,
        identity: ExportIdentity,
        destination: Path,
        progress: Progress = _noop,
    ) -> Path:
        progress("Exporting APF audio", 0, 0)
        return self.require_session().asset_io.export_audio_identity(
            identity, destination
        )

    def export_external_audio_bank(
        self,
        identity: ExternalAudioBankIdentity,
        destination: Path,
        progress: Progress = _noop,
    ) -> Path:
        with self._session_lock:
            progress(
                "Exporting original APF external audio bank",
                0,
                identity.encoded_size,
            )
            return self.require_session().asset_io.export_external_audio_bank(
                identity,
                destination,
                progress=lambda completed, total: progress(
                    "Exporting original APF external audio bank",
                    completed,
                    total,
                ),
            )

    def export_external_audio_bank_bundle(
        self,
        identities: Iterable[ExternalAudioBankIdentity],
        destination: Path,
        *,
        bundle_name: str = "APF 2K8 original external audio banks",
        progress: Progress = _noop,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> ExternalAudioBankBundleReceipt:
        """Export proved original external banks without changing project state."""

        selected = tuple(identities)
        with self._session_lock:
            session = self.require_session()
            source = self.source
            if source is None:
                raise FacadeError("Load your APF 2K8 game first")

            def report(event: ExternalAudioBankBundleProgress) -> None:
                if event.stage == "preparing":
                    message = "Preparing original APF audio-bank bundle"
                elif event.stage == "exporting_bank":
                    message = (
                        "Copying original APF audio bank "
                        f"{event.bank_name or ''}"
                    ).rstrip()
                elif event.stage == "cancelled":
                    message = (
                        "Original APF audio-bank bundle cancelled "
                        f"({event.succeeded} exported, {event.cancelled} skipped)"
                    )
                else:
                    message = (
                        "Original APF audio-bank bundle complete "
                        f"({event.succeeded} exported, {event.failed} failed)"
                    )
                progress(message, event.completed, event.total)

            return ApfExternalAudioBankBundleExporter(
                session.asset_io
            ).export_all(
                selected,
                destination,
                source_sha256=source.source_sha256,
                bundle_name=bundle_name,
                progress=report,
                cancel_requested=cancel_requested,
            )

    def export_all_external_audio_banks(
        self,
        destination: Path,
        *,
        bundle_name: str = "APF 2K8 original external audio banks",
        progress: Progress = _noop,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> ExternalAudioBankBundleReceipt:
        """Discover and export the complete source-owned physical-bank set."""

        with self._session_lock:
            rows = self.require_inspectors().audio().external_banks.rows
            identities = tuple(
                row.external_bank_identity
                for row in rows
                if row.external_bank_identity is not None
            )
            if len(identities) != len(rows):
                raise FacadeError(
                    "The loaded APF audio inventory has an unowned external bank"
                )
            return self.export_external_audio_bank_bundle(
                identities,
                destination,
                bundle_name=bundle_name,
                progress=progress,
                cancel_requested=cancel_requested,
            )

    def prepare_audio_preview(
        self,
        identity: ExportIdentity,
        progress: Progress = _noop,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Path:
        progress("Decoding private APF audio preview", 0, 0)
        session = self.require_session()
        if cancel_requested is None:
            return session.prepare_audio_preview(identity)
        return session.prepare_audio_preview(
            identity,
            cancel_requested=cancel_requested,
        )

    def audio_pcm_target(self, identity: ExportIdentity) -> Pcm16Target:
        """Return the exact PCM16 shape required by one selected sound."""

        with self._session_lock:
            return self.require_session().audio_pcm_target(identity)

    def export_audio_pcm_template(
        self,
        identity: ExportIdentity,
        destination: Path,
        progress: Progress = _noop,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Pcm16TemplateReceipt:
        """Export a retail-free silence template for one fixed audio slot."""

        with self._session_lock:
            return self.require_session().export_audio_pcm_template(
                identity,
                destination,
                progress=progress,
                cancel_requested=cancel_requested,
            )

    def replace_audio_from_pcm(
        self,
        identity: ExportIdentity,
        supplied_pcm_wav: Path,
        encoder: ExternalXma1Encoder,
        progress: Progress = _noop,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Modification:
        """Encode privately and stage only validator-authorized XMA1 packets."""

        with self._session_lock:
            result = self.require_session().replace_audio_from_pcm(
                identity,
                supplied_pcm_wav,
                encoder,
                progress=progress,
                cancel_requested=cancel_requested,
            )
            self.last_build = None
            return result

    def replace_audo_exact_slot(
        self,
        identity: ExportIdentity,
        supplied_xma: Path,
        progress: Progress = _noop,
    ) -> Modification:
        """Stage one strict pre-encoded standalone XMA1 replacement."""

        with self._session_lock:
            progress("Reading exact standalone-audio target", 0, 3)
            result = self.require_session().replace_audo_exact_slot(
                identity, supplied_xma
            )
            progress("XMA1 packets and complete decode verified", 3, 3)
            self.last_build = None
            return result

    def replace_ausb_exact_slot(
        self,
        identity: ExportIdentity,
        supplied_xma: Path,
        progress: Progress = _noop,
    ) -> Modification:
        """Stage one strict pre-encoded external-bank XMA1 replacement."""

        with self._session_lock:
            progress("Reading exact AUSB substream target", 0, 3)
            result = self.require_session().replace_ausb_exact_slot(
                identity, supplied_xma
            )
            progress("XMA1 packets and complete decode verified", 3, 3)
            self.last_build = None
            return result

    def export_audio_replacement_template(
        self,
        rows: Iterable[InspectorRow],
        destination: Path,
        progress: Progress = _noop,
        *,
        container: str | None = None,
        input_kind: str = "xma1",
    ) -> AudioReplacementTemplateReceipt:
        """Create one metadata-only authoring folder or deterministic ZIP."""

        selected = tuple(rows)
        with self._session_lock:
            source = self.source
            if source is None:
                raise FacadeError("Load your APF 2K8 game first")
            progress("Validating audio replacement targets", 0, len(selected))
            try:
                session = self.require_session()
                template_arguments: dict[str, object] = {
                    "source_sha256": source.source_sha256,
                    "active_modifications": session.modifications,
                }
                if input_kind != "xma1":
                    template_arguments["input_kind"] = input_kind
                if container is not None:
                    template_arguments["container"] = container
                receipt = create_audio_replacement_template(
                    selected,
                    destination,
                    **template_arguments,
                )
            except AudioReplacementPackError as exc:
                raise FacadeError(str(exc)) from exc
            progress(
                "Metadata-only replacement template created",
                len(selected),
                len(selected),
            )
            return receipt

    def import_audio_replacement_pack(
        self,
        root: Path,
        progress: Progress = _noop,
        *,
        encoder: ExternalXma1Encoder | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        confirmation_token: str | None = None,
    ) -> AudioReplacementApplyReceipt:
        """Revalidate a previewed folder or ZIP, then stage one Undo action."""

        with self._session_lock:
            source = self.source
            if source is None:
                raise FacadeError("Load your APF 2K8 game first")
            if not isinstance(confirmation_token, str) or len(confirmation_token) != 64:
                raise FacadeError(
                    "Review and fully validate this audio replacement pack before "
                    "choosing Apply."
                )
            snapshot = self.require_inspectors().audio()
            live_rows = (*snapshot.audo.rows, *snapshot.ausb_substreams.rows)
            progress("Checking replacement manifest and source binding", 0, 0)
            try:
                pack_context = (
                    open_audio_replacement_pack(
                        root,
                        expected_source_sha256=source.source_sha256,
                        live_rows=live_rows,
                    )
                    if root.suffix.casefold() == ".zip"
                    else nullcontext(
                        load_audio_replacement_pack(
                            root,
                            expected_source_sha256=source.source_sha256,
                            live_rows=live_rows,
                        )
                    )
                )
            except AudioReplacementPackError as exc:
                raise FacadeError(str(exc)) from exc
            try:
                with pack_context as plan:
                    total = len(plan.supplied)
                    pcm_pack = plan.input_kind == "pcm16"
                    if pcm_pack and not isinstance(encoder, ExternalXma1Encoder):
                        raise FacadeError(
                            "This PCM16 replacement pack needs an external XMA1 "
                            "encoder. Choose Configure XMA1 encoder first, then "
                            "import the pack again."
                        )

                    def report(event: AudioReplacementApplyProgress) -> None:
                        if event.stage == "encoding" and event.asset_id is not None:
                            message = (
                                f"Encoding PCM WAV {event.completed + 1:,} of "
                                f"{event.total:,}: {event.asset_id}"
                            )
                        elif event.stage == "validating" and event.asset_id is not None:
                            message = (
                                f"Validating XMA1 file {event.completed + 1:,} of "
                                f"{event.total:,}: {event.asset_id}"
                            )
                        elif event.stage == "validated":
                            message = (
                                f"{'Encoded and validated' if pcm_pack else 'Validated'} "
                                f"{event.completed:,} of {event.total:,} exact "
                                f"{'PCM-authored sounds' if pcm_pack else 'XMA1 files'}"
                            )
                        elif event.stage == "cancelled":
                            message = (
                                f"Replacement import cancelled after {event.completed:,} "
                                "complete files; no project edits changed"
                            )
                        else:
                            message = (
                                f"Validated all {event.completed:,} exact audio files"
                            )
                        progress(message, event.completed, event.total)

                    progress(
                        (
                            f"Encoding and validating {total:,} exact PCM16 WAV replacements"
                            if pcm_pack
                            else f"Validating {total:,} exact XMA1 replacements"
                        ),
                        0,
                        total,
                    )
                    apply_arguments: dict[str, object] = {
                        "progress": report,
                        "cancel_requested": cancel_requested,
                        "confirmation_token": confirmation_token,
                    }
                    if encoder is not None:
                        apply_arguments["encoder"] = encoder
                    result = self.require_session().apply_audio_replacement_pack(
                        plan,
                        **apply_arguments,
                    )
                    if result.was_cancelled:
                        progress(
                            f"Import cancelled after {result.validated_count:,} complete files; "
                            "no project edits changed",
                            result.validated_count,
                            total,
                        )
                    else:
                        progress(
                            f"Staged {result.staged_count:,} audio changes as one Undo action",
                            total,
                            total,
                        )
                    if result.staged_count:
                        self.last_build = None
                    return result
            except AudioReplacementPackError as exc:
                raise FacadeError(str(exc)) from exc

    def preview_audio_replacement_pack(
        self,
        root: Path,
        progress: Progress = _noop,
        *,
        encoder: ExternalXma1Encoder | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> AudioReplacementPreviewReceipt:
        """Fully validate one folder or ZIP without changing project state."""

        with self._session_lock:
            source = self.source
            if source is None:
                raise FacadeError("Load your APF 2K8 game first")
            snapshot = self.require_inspectors().audio()
            live_rows = (*snapshot.audo.rows, *snapshot.ausb_substreams.rows)
            progress("Checking replacement manifest and source binding", 0, 0)
            try:
                pack_context = (
                    open_audio_replacement_pack(
                        root,
                        expected_source_sha256=source.source_sha256,
                        live_rows=live_rows,
                    )
                    if root.suffix.casefold() == ".zip"
                    else nullcontext(
                        load_audio_replacement_pack(
                            root,
                            expected_source_sha256=source.source_sha256,
                            live_rows=live_rows,
                        )
                    )
                )
            except AudioReplacementPackError as exc:
                raise FacadeError(str(exc)) from exc
            try:
                with pack_context as plan:
                    total = len(plan.supplied)
                    pcm_pack = plan.input_kind == "pcm16"
                    if pcm_pack and not isinstance(encoder, ExternalXma1Encoder):
                        raise FacadeError(
                            "This PCM16 replacement pack needs an external XMA1 "
                            "encoder. Choose Configure XMA1 encoder first, then "
                            "review the pack again."
                        )

                    def report(event: AudioReplacementApplyProgress) -> None:
                        if event.stage == "encoding" and event.asset_id is not None:
                            message = (
                                f"Preview-encoding PCM WAV {event.completed + 1:,} of "
                                f"{event.total:,}: {event.asset_id}"
                            )
                        elif event.stage == "validating" and event.asset_id is not None:
                            message = (
                                f"Preview-validating XMA1 file {event.completed + 1:,} of "
                                f"{event.total:,}: {event.asset_id}"
                            )
                        elif event.stage == "validated":
                            message = (
                                f"{'Encoded and validated' if pcm_pack else 'Validated'} "
                                f"{event.completed:,} of {event.total:,} exact "
                                f"{'PCM-authored sounds' if pcm_pack else 'XMA1 files'}"
                            )
                        elif event.stage == "cancelled":
                            message = (
                                f"Replacement preview cancelled after {event.completed:,} "
                                "complete files; no project edits changed"
                            )
                        else:
                            message = (
                                f"Previewed all {event.completed:,} exact audio files"
                            )
                        progress(message, event.completed, event.total)

                    progress(
                        (
                            f"Preview-encoding and validating {total:,} exact PCM16 WAV replacements"
                            if pcm_pack
                            else f"Preview-validating {total:,} exact XMA1 replacements"
                        ),
                        0,
                        total,
                    )
                    preview_arguments: dict[str, object] = {
                        "progress": report,
                        "cancel_requested": cancel_requested,
                    }
                    if encoder is not None:
                        preview_arguments["encoder"] = encoder
                    result = self.require_session().preview_audio_replacement_pack(
                        plan,
                        **preview_arguments,
                    )
                    if result.was_cancelled:
                        progress(
                            f"Preview cancelled after {result.validated_count:,} complete files; "
                            "no project edits changed",
                            result.validated_count,
                            total,
                        )
                    else:
                        progress(
                            f"Preview complete: {result.would_change_count:,} would change, "
                            f"{result.already_current_count:,} already current",
                            total,
                            total,
                        )
                    return result
            except AudioReplacementPackError as exc:
                raise FacadeError(str(exc)) from exc

    def export_audio_bank(
        self,
        identities: Iterable[ExportIdentity],
        destination: Path,
        *,
        bank_name: str,
        output_extension: str = ".xma",
        progress: Progress = _noop,
    ) -> Path:
        selected = tuple(identities)
        progress("Exporting APF audio bank", 0, len(selected))
        return self.require_session().asset_io.export_audio_bank(
            selected,
            destination,
            bank_name=bank_name,
            output_extension=output_extension,
            progress=lambda completed, total: progress(
                "Exporting APF audio bank", completed, total
            ),
        )

    def export_audio_bundle(
        self,
        rows: Iterable[InspectorRow],
        destination: Path,
        *,
        bundle_name: str,
        output_extension: str = ".xma",
        progress: Progress = _noop,
    ) -> Path:
        with self._session_lock:
            selected = self.annotated_audio_rows(rows)
            progress("Exporting matching APF sounds", 0, len(selected))
            return self.require_session().asset_io.export_audio_bundle(
                selected,
                destination,
                bundle_name=bundle_name,
                output_extension=output_extension,
                progress=lambda completed, total: progress(
                    "Exporting matching APF sounds", completed, total
                ),
            )

    def export_audio_batch(
        self,
        rows: Iterable[InspectorRow],
        destination: Path,
        *,
        output_extension: str = ".xma",
        batch_name: str = "APF 2K8 audio export",
        progress: Progress = _noop,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> AudioBatchReceipt:
        """Export semantic audio rows through the loaded source's proved route.

        This is deliberately an export-only operation: it neither creates a
        project modification nor invalidates an existing build receipt.  The
        session lock keeps the asset exporter and source fingerprint paired for
        the complete atomic batch publication.
        """

        with self._session_lock:
            session = self.require_session()
            selected = self.annotated_audio_rows(rows)
            source = self.source
            if source is None:
                raise FacadeError("Load your APF 2K8 game first")

            def report(event: AudioBatchProgress) -> None:
                if event.stage == "preparing":
                    message = "Preparing APF audio batch export"
                elif event.stage == "exporting":
                    message = (
                        "Exporting APF audio batch "
                        f"({event.succeeded} exported, {event.failed} failed, "
                        f"{event.unsupported} unsupported)"
                    )
                elif event.stage == "cancelled":
                    message = (
                        "APF audio batch export cancelled "
                        f"({event.succeeded} exported, {event.cancelled} skipped)"
                    )
                else:
                    message = (
                        "APF audio batch export complete "
                        f"({event.succeeded} exported, {event.failed} failed, "
                        f"{event.unsupported} unsupported)"
                    )
                progress(message, event.completed, event.total)

            return ApfAudioBatchExporter(session.asset_io).export_selected(
                selected,
                destination,
                output_extension=output_extension,
                batch_name=batch_name,
                source_sha256=source.source_sha256,
                progress=report,
                cancel_requested=cancel_requested,
            )

    def export_inspector_rows(
        self,
        model: PagedModel,
        destination: Path,
        *,
        search: str = "",
        kinds: str | Iterable[str] | None = None,
        roles: str | Iterable[str] | None = None,
        sources: str | Iterable[str] | None = None,
        progress: Progress = _noop,
    ) -> Path:
        self.require_session()
        progress("Exporting decoded inspector rows", 0, 0)
        return export_semantic_rows(
            model,
            destination,
            search=search,
            kinds=kinds,
            roles=roles,
            sources=sources,
        )

    def export_player_rating_sheet(
        self,
        model: PagedModel,
        destination: Path,
        *,
        progress: Progress = _noop,
    ) -> Path:
        with self._session_lock:
            progress("Exporting complete APF player ratings sheet", 0, 2_254)
            session = self.require_session()
            source = self.source
            if source is None:
                raise FacadeError("Load your APF 2K8 game first")
            result = export_player_rating_sheet(
                model,
                destination,
                source_sha256=source.source_sha256,
                value_resolver=session.player_base_rating_value,
            )
            progress("Exporting complete APF player ratings sheet", 2_254, 2_254)
            return result

    def preview_player_rating_sheet(
        self,
        source: Path,
        progress: Progress = _noop,
    ) -> PlayerRatingSheetPreviewReceipt:
        with self._session_lock:
            progress("Checking complete APF ratings sheet", 0, 2_254 * 28)
            result = preview_private_player_rating_sheet(
                self.require_session(),
                self.require_inspectors().roster().model,
                source,
            )
            progress(
                "Ratings-sheet preview ready",
                result.cell_count,
                2_254 * 28,
            )
            return result

    def apply_player_rating_sheet(
        self,
        preview: PlayerRatingSheetPreviewReceipt,
        *,
        allow_conflicts: bool = False,
        progress: Progress = _noop,
    ) -> PlayerRatingSheetApplyReceipt:
        with self._session_lock:
            progress("Rechecking APF ratings sheet", 0, 2_254 * 28)
            result = apply_private_player_rating_sheet(
                self.require_session(),
                self.require_inspectors().roster().model,
                preview,
                allow_conflicts=allow_conflicts,
            )
            progress(
                "APF ratings sheet applied",
                result.applied_count,
                result.changed_count,
            )
            if result.applied_count:
                self.last_build = None
            return result

    def revert(self, asset_id: str, progress: Progress = _noop) -> bool:
        with self._session_lock:
            progress("Reverting edit", 0, 1)
            result = self.require_session().revert(asset_id)
            progress("Reverting edit", 1, 1)
            if result:
                self.last_build = None
            return result

    def revert_all(self, progress: Progress = _noop) -> int:
        with self._session_lock:
            progress("Reverting all edits", 0, 0)
            count = self.require_session().revert_all()
            if count:
                self.last_build = None
            return count

    def undo(self, progress: Progress = _noop) -> bool:
        with self._session_lock:
            progress("Undoing last action", 0, 0)
            result = self.require_session().undo()
            if result:
                self.last_build = None
            return result

    def save_project(
        self,
        destination: Path,
        progress: Progress = _noop,
        *,
        replace: bool = False,
        expected_target: ProjectTargetIdentity | None = None,
    ) -> Path:
        with self._session_lock:
            progress("Saving retail-free project", 0, 0)
            path = self.require_session().save_project(
                destination,
                replace=replace,
                expected_target=expected_target,
            )
            self.last_project_identity = project_target_identity(path)
            return path

    def save_recovery_project(
        self,
        destination: Path,
        expected_source_sha256: str,
        progress: Progress = _noop,
    ) -> Path:
        """Save a private empty-or-nonempty project under one source fence."""

        with self._session_lock:
            source = self.source
            session = self.require_session()
            if source is None or source.source_sha256 != expected_source_sha256:
                raise FacadeError(
                    "The loaded source changed before recovery could be saved"
                )
            progress("Saving private recovery snapshot", 0, 1)
            path = session.save_project(
                destination,
                title="APF 2K8 Mod Studio Unsaved Recovery",
                replace=True,
            )
            if self.source is not source or self.session is not session:
                raise FacadeError(
                    "The loaded source changed before recovery could be saved"
                )
            progress("Recovery snapshot saved", 1, 1)
            return path

    def load_project(self, source: Path, progress: Progress = _noop) -> int:
        with self._session_lock:
            progress("Loading retail-free project", 0, 0)
            active_session = self.require_session()
            assert self.source is not None and self.catalog is not None
            opened_identity = project_target_identity(source)
            candidate = ApfSession(self.source, self.catalog, cache_root=self.cache_root)
            try:
                count = candidate.load_project(source)
                candidate_annotation_ids = getattr(
                    candidate, "labeled_audio_asset_ids", frozenset()
                )
                if isinstance(candidate_annotation_ids, (set, frozenset)) \
                        and candidate_annotation_ids:
                    playable_ids = self._live_playable_audio_rows()
                    unknown_annotation_ids = sorted(
                        candidate_annotation_ids.difference(playable_ids)
                    )
                    if unknown_annotation_ids:
                        raise ProjectError(
                            "Project audio annotation targets a sound that is not "
                            f"present in this game: {unknown_annotation_ids[0]}"
                        )
                current_identity = project_target_identity(source)
                if current_identity != opened_identity:
                    raise ProjectError(
                        "The project changed outside Mod Studio while it was opening. "
                        "The current workspace was kept; open the project again."
                    )
            except BaseException:
                candidate.close()
                raise
            self.session = candidate
            active_session.close()
            self.last_build = None
            self.last_project_identity = current_identity
            return count

    def build(self, output_game: Path, progress: Progress = _noop) -> BuildReceipt:
        with self._session_lock:
            session = self.require_session()
            locked_roster_edits = tuple(
                modification.asset_id
                for modification in session.modifications
                if modification.kind == "roster_identity_text"
                and not session.roster_identity_is_product_editable(
                    modification.asset_id
                )
            )
            if locked_roster_edits:
                raise FacadeError(
                    f"{ROSTER_IDENTITY_RUNTIME_LOCK_MESSAGE} Revert the locked "
                    "roster edit before building: "
                    f"{locked_roster_edits[0]}"
                )
            assert self.source is not None
            receipt = ApfBuildService(self.source).build(
                session.modifications, output_game, progress
            )
            self.last_build = receipt
            return receipt

    def configure_xenia(self, executable: Path, wine: Path | None = None) -> None:
        self.launcher.settings.configure(executable, wine)

    def launch_xenia(self) -> LaunchReceipt:
        if self.last_build is None:
            raise FacadeError("Build a modded game folder first")
        return self.launcher.launch(self.last_build.output_game)

    def close(self) -> None:
        with self._session_lock:
            if self.session is not None:
                self.session.close()
            self.session = None
            self.inspectors = None
            self.last_project_identity = None
