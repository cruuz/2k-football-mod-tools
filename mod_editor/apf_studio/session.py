"""Editable APF project session with undo and safe original preservation."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from io import BytesIO
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Callable, Iterable, Mapping
from uuid import uuid4

from PIL import Image

from mod_editor.core import audio_conform
from mod_editor.core import platform_compat
from mod_editor.core.apf2k8_playbook_route_writer import (
    PROVIDER_KIND as PLAY_ASSIGNMENT_ROUTE_KIND,
    RouteCloneRequest,
    compile_route_clones,
    decode_route_clone_payload,
    encode_route_clone_payload,
    read_master_play_body,
    request_from_mapping as route_clone_request_from_mapping,
)
from mod_editor.core.apf2k8_splb_writer import (
    PROVIDER_KIND as SPLB_MEMBERSHIP_KIND,
    MembershipChange as SplbMembershipChange,
    TagMove as SplbTagMove,
    change_from_mapping as splb_change_from_mapping,
    change_metadata as splb_change_metadata,
    compile_book as compile_splb_book,
    decode_membership_payload as decode_splb_membership_payload,
    encode_membership_payload as encode_splb_membership_payload,
    read_book as read_splb_book,
)
from mod_editor.core.errors import ValidationError

from .asset_io import ApfAssetIO, AssetIoError, AudioPreviewCancelled
from .audio_annotations import (
    AudioAnnotationError,
    AudioCueAnnotation,
    validate_audio_cue_annotation,
    validate_audio_cue_id,
)
from .audio_replacement_pack import (
    MAX_PCM_PACK_SUPPLIED,
    AudioReplacementApplyProgress,
    AudioReplacementApplyReceipt,
    AudioReplacementPackError,
    AudioReplacementPackPlan,
    AudioReplacementPreviewReceipt,
    current_audio_target_baseline,
    materialize_audio_replacement_pcm,
    read_audio_replacement_payload,
)
from .audio_encoding import (
    AudioEncodingError,
    ExternalEncodingResult,
    ExternalXma1Encoder,
    Pcm16Target,
    Pcm16TemplateReceipt,
    export_pcm16_template,
    validate_pcm16_target,
    verify_xma1_signal_quality,
)
from .backend import ensure_tools_importable
from .catalog import ApfCatalog
from .inspectors import ExportIdentity
from .helmet_crest_design import (
    FULL_SHELL_CREST_PROFILE,
    HELMET_CREST_DESIGN_EDIT_ID,
    HELMET_CREST_DESIGN_KIND,
    HelmetCrestDesignError,
    metadata as helmet_crest_metadata,
    validate_metadata as validate_helmet_crest_metadata,
)
from .helmet_logo_regions import (
    HelmetLogoRegionError,
    opaque_shell_body_rgba,
    validate_full_shell_region_mask_rgba,
    validate_region_mask_rgba,
)
from .models import (
    AUDO_EXACT_SLOT_KIND,
    AUDO_EXACT_SLOT_WRITER_SCHEMA,
    AUSB_EXACT_SLOT_KIND,
    AUSB_EXACT_SLOT_WRITER_SCHEMA,
    DRAFT_LOGO_CATALOG_ID,
    DRAFT_LOGO_EDIT_ID,
    DRAFT_LOGO_INNER_INDEX,
    DRAFT_LOGO_OUTER_INDEX,
    ApfSource,
    ApfStatus,
    Modification,
    UniformAsset,
)
from .project import (
    ProjectError,
    ProjectTargetIdentity,
    decode_text_payload,
    encode_text_payload,
    load_project as read_project_archive,
    save_project as write_project_archive,
)
from .player_positions import PlayerPositionsError


ensure_tools_importable()
import apf_player_rating_patch  # type: ignore  # noqa: E402
import apf_player_position_patch  # type: ignore  # noqa: E402
import apf_custom_team_appearance_patch  # type: ignore  # noqa: E402
import apf_uniform_equipment_color_patch  # type: ignore  # noqa: E402
import apf_audio  # type: ignore  # noqa: E402
import apf_audo_exact_slot  # type: ignore  # noqa: E402
import apf_ausb_exact_slot  # type: ignore  # noqa: E402
import apf_roster  # type: ignore  # noqa: E402
import apf_txt_loc_patch  # type: ignore  # noqa: E402
import apf_roster_identity_patch  # type: ignore  # noqa: E402
import apf_helmet_crest_mask_fit  # type: ignore  # noqa: E402
import apf_team_crests  # type: ignore  # noqa: E402


class SessionError(ValueError):
    """A replacement or project action a modder can correct."""


# Every descriptor this module opens carries replacement or user-asset *bytes*.
# On Windows ``os.open`` defaults to the CRT's text mode, which rewrites CRLF and
# stops reading at a 0x1A byte -- silent corruption of exactly those payloads (a
# PNG begins ``89 50 4E 47 0D 0A 1A 0A``, so a text-mode read both collapses its
# CRLF and truncates at its 0x1A).  ``O_BINARY`` does not exist on POSIX, where
# there is no translation to disable, so this resolves to 0 and the POSIX flags
# are unchanged.
_O_BINARY = getattr(os, "O_BINARY", 0)


_AUDIO_REPLACEMENT_KINDS = frozenset(
    {AUDO_EXACT_SLOT_KIND, AUSB_EXACT_SLOT_KIND}
)
_AUDIO_REPLACEMENT_CONFIRMATION_DOMAIN = (
    "apf2k8.audio-replacement-preview-confirmation.v1"
)


@dataclass(frozen=True)
class _PreparedAudioReplacementPack:
    prepared: tuple[Modification, ...]
    updated: Mapping[str, Modification]
    unchanged_count: int
    changed_ids: frozenset[str]
    validated_count: int
    was_cancelled: bool = False


@dataclass(frozen=True)
class _SessionSnapshot:
    """One chronological Undo checkpoint for edits and project metadata."""

    modifications: Mapping[str, Modification]
    audio_annotations: Mapping[str, AudioCueAnnotation]


class ApfSession:
    def __init__(
        self,
        source: ApfSource,
        catalog: ApfCatalog,
        *,
        cache_root: Path | None = None,
    ):
        self.source = source
        self.catalog = catalog
        self.cache_root = cache_root or Path.home() / ".cache" / "apf2k8-mod-studio"
        self.session_id = uuid4().hex
        self.working_root = self.cache_root / "sessions" / self.session_id
        self.replacements_root = self.working_root / "replacements"
        self.replacements_root.mkdir(parents=True, exist_ok=False)
        self.asset_io = ApfAssetIO(source, catalog, self.cache_root)
        self._modifications: dict[str, Modification] = {}
        self._audio_annotations: dict[str, AudioCueAnnotation] = {}
        self._undo: list[_SessionSnapshot] = []
        self._localization_allocations: dict[
            str, apf_txt_loc_patch.TextAllocation
        ] | None = None
        self._roster_identity_allocations: dict[
            str, apf_roster_identity_patch.RosterIdentityAllocation
        ] | None = None
        self._player_rating_source_body: bytes | None = None
        self._custom_team_appearances: dict[
            int, apf_custom_team_appearance_patch.CustomTeamAppearance
        ] | None = None
        self._custom_team_appearance_targets: dict[
            int, apf_custom_team_appearance_patch.AppearanceTarget
        ] | None = None
        self._uniform_equipment_color_inspections: dict[
            int, apf_uniform_equipment_color_patch.UniformEquipmentColorInspection
        ] | None = None
        self._master_play_source_body: bytes | None = None
        self._audo_source_fingerprints: (
            apf_audo_exact_slot.SourceAudioFingerprints | None
        ) = None
        self._ausb_source_fingerprints: (
            apf_audo_exact_slot.SourceAudioFingerprints | None
        ) = None
        self._audo_preview_receipts: dict[Path, tuple[str, str]] = {}
        # A preview token is valid only for this loaded-game session.  The nonce
        # is private and never enters a project, template, log, or release file.
        self._audio_replacement_preview_nonce = uuid4().hex

    @property
    def modifications(self) -> tuple[Modification, ...]:
        return tuple(self._modifications[key] for key in sorted(self._modifications))

    @property
    def modified_asset_ids(self) -> frozenset[str]:
        return frozenset(self._modifications)

    @property
    def modified_count(self) -> int:
        return len(self._modifications)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    def modification(self, asset_id: str) -> Modification | None:
        return self._modifications.get(asset_id)

    @property
    def audio_annotations(self) -> tuple[AudioCueAnnotation, ...]:
        return tuple(
            self._audio_annotations[cue_id]
            for cue_id in sorted(self._audio_annotations)
        )

    @property
    def labeled_audio_asset_ids(self) -> frozenset[str]:
        return frozenset(self._audio_annotations)

    @property
    def annotation_count(self) -> int:
        return len(self._audio_annotations)

    @property
    def project_metadata_count(self) -> int:
        return self.annotation_count

    @property
    def has_project_metadata(self) -> bool:
        return bool(self._audio_annotations)

    @property
    def project_change_count(self) -> int:
        return self.modified_count + self.project_metadata_count

    def audio_annotation(self, asset_id: str) -> AudioCueAnnotation | None:
        try:
            cue_id = validate_audio_cue_id(asset_id)
        except AudioAnnotationError as exc:
            raise SessionError(str(exc)) from exc
        return self._audio_annotations.get(cue_id)

    def set_audio_annotation(
        self,
        asset_id: str,
        title: str = "",
        note: str = "",
    ) -> bool:
        try:
            annotation = validate_audio_cue_annotation(asset_id, title, note)
        except AudioAnnotationError as exc:
            raise SessionError(str(exc)) from exc
        if self._audio_annotations.get(annotation.cue_id) == annotation:
            return False
        self._record_undo()
        self._audio_annotations[annotation.cue_id] = annotation
        return True

    def clear_audio_annotation(self, asset_id: str) -> bool:
        try:
            cue_id = validate_audio_cue_id(asset_id)
        except AudioAnnotationError as exc:
            raise SessionError(str(exc)) from exc
        if cue_id not in self._audio_annotations:
            return False
        self._record_undo()
        del self._audio_annotations[cue_id]
        return True

    def prepare_audio_preview(
        self,
        identity: ExportIdentity,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Path:
        self._require_audio_preview_not_cancelled(cancel_requested)
        root = self.working_root.lstat()
        if not stat.S_ISDIR(root.st_mode) or stat.S_ISLNK(root.st_mode):
            raise SessionError("The private loaded-game session folder is not safe")
        exact_slot_kind: str | None = None
        exact_slot_asset_id: str | None = None
        if identity.kind == "audo" and identity.substream_index is None:
            exact_slot_kind = AUDO_EXACT_SLOT_KIND
            exact_slot_asset_id = self._audo_asset_id(identity)
        elif identity.kind == "ausb_substream" and identity.substream_index is not None:
            exact_slot_kind = AUSB_EXACT_SLOT_KIND
            exact_slot_asset_id = self._ausb_asset_id(identity)
        modification = (
            self._modifications.get(exact_slot_asset_id)
            if exact_slot_asset_id is not None
            else None
        )
        if modification is not None:
            if modification.kind != exact_slot_kind:
                raise SessionError("The active sound edit has an invalid type")
            destination: Path | None = None
            creating_preview = False

            def discard_unreceipted_preview() -> None:
                if destination is None or not creating_preview:
                    return
                destination.unlink(missing_ok=True)
                self._audo_preview_receipts.pop(destination, None)

            try:
                if modification.kind == AUDO_EXACT_SLOT_KIND:
                    resolved = self._resolve_audo_identity(identity)
                    target = resolved.target

                    def decode(payload: bytes, destination: Path) -> Mapping[str, object]:
                        self._require_audio_preview_not_cancelled(cancel_requested)
                        self._reject_any_source_audio_reuse(payload)
                        if cancel_requested is None:
                            return apf_audo_exact_slot.decode_stored_payload_to_wav(
                                payload, target, destination
                            )
                        return apf_audo_exact_slot.decode_stored_payload_to_wav(
                            payload, target, destination,
                            cancel_requested=cancel_requested,
                        )

                    outer_index = resolved.outer_index
                    inner_index = resolved.inner_index
                else:
                    ausb_resolved = self._resolve_ausb_identity(identity)

                    def decode(payload: bytes, destination: Path) -> Mapping[str, object]:
                        self._require_audio_preview_not_cancelled(cancel_requested)
                        self._reject_any_source_audio_reuse(payload)
                        arguments = (
                            payload,
                            ausb_resolved,
                            self._protected_ausb_fingerprints(),
                            destination,
                        )
                        if cancel_requested is None:
                            return apf_ausb_exact_slot.decode_stored_payload_to_wav(
                                *arguments
                            )
                        return apf_ausb_exact_slot.decode_stored_payload_to_wav(
                            *arguments, cancel_requested=cancel_requested
                        )

                    outer_index = ausb_resolved.requested_owner.descriptor_outer_index
                    inner_index = ausb_resolved.requested_owner.descriptor_inner_index
                preview_root = self.working_root / "audio-previews"
                preview_root.mkdir(parents=True, exist_ok=True)
                root_info = preview_root.lstat()
                if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(
                    root_info.st_mode
                ):
                    raise SessionError("The private audio preview folder is unsafe")
                destination = preview_root / (
                    f"modified-o{outer_index}-i{inner_index}-"
                    f"s{identity.substream_index if identity.substream_index is not None else 'audo'}-"
                    f"{modification.replacement_sha256[:16]}.wav"
                )
                expected_receipt = self._audo_preview_receipts.get(destination)
                if destination.exists() or destination.is_symlink():
                    if expected_receipt is None:
                        raise SessionError(
                            "An unreceipted file appeared in the private audio preview folder"
                        )
                    info = destination.lstat()
                    actual_wav_sha = hashlib.sha256(destination.read_bytes()).hexdigest()
                    self._require_audio_preview_not_cancelled(cancel_requested)
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or stat.S_ISLNK(info.st_mode)
                        or expected_receipt
                        != (
                            modification.replacement_sha256,
                            actual_wav_sha,
                        )
                    ):
                        raise SessionError(
                            "The private replacement-audio preview changed after decoding"
                        )
                    return destination
                creating_preview = True
                self._require_audio_preview_not_cancelled(cancel_requested)
                receipt = decode(
                    modification.replacement_path.read_bytes(), destination
                )
                self._require_audio_preview_not_cancelled(cancel_requested)
                wav_sha = receipt.get("wav_sha256")
                if (
                    receipt.get("payload_sha256")
                    != modification.replacement_sha256
                    or not isinstance(wav_sha, str)
                    or hashlib.sha256(destination.read_bytes()).hexdigest()
                    != wav_sha
                ):
                    destination.unlink(missing_ok=True)
                    raise SessionError(
                        "The replacement-audio preview receipt is inconsistent"
                    )
                self._require_audio_preview_not_cancelled(cancel_requested)
                self._audo_preview_receipts[destination] = (
                    modification.replacement_sha256,
                    wav_sha,
                )
                return destination
            except AudioPreviewCancelled:
                discard_unreceipted_preview()
                raise
            except apf_audio.AudioCancelled as exc:
                discard_unreceipted_preview()
                raise AudioPreviewCancelled("Audio preview cancelled") from exc
            except SessionError:
                discard_unreceipted_preview()
                raise
            except (
                OSError,
                apf_audo_exact_slot.ExactSlotImportError,
                apf_ausb_exact_slot.AusbExactSlotError,
            ) as exc:
                discard_unreceipted_preview()
                raise SessionError(
                    f"Could not preview the staged XMA1 replacement: {exc}"
                ) from exc
        if cancel_requested is None:
            return self.asset_io.prepare_audio_preview(
                identity,
                self.working_root / "audio-previews",
            )
        return self.asset_io.prepare_audio_preview(
            identity,
            self.working_root / "audio-previews",
            cancel_requested=cancel_requested,
        )

    @staticmethod
    def _require_audio_preview_not_cancelled(
        cancel_requested: Callable[[], bool] | None,
    ) -> None:
        if cancel_requested is None:
            return
        try:
            cancelled = cancel_requested()
        except Exception as exc:
            raise SessionError(
                f"Could not check whether audio preview was cancelled: {exc}"
            ) from exc
        if cancelled:
            raise AudioPreviewCancelled("Audio preview cancelled")

    @staticmethod
    def _audo_asset_id(identity: ExportIdentity) -> str:
        if (
            identity.kind != "audo"
            or identity.substream_index is not None
            or type(identity.outer_table_index) is not int
            or type(identity.inner_file_index) is not int
        ):
            raise SessionError(
                "Exact-slot replacement supports standalone AUDO sounds only"
            )
        try:
            return apf_audo_exact_slot.asset_id(
                identity.outer_table_index, identity.inner_file_index
            )
        except apf_audo_exact_slot.ExactSlotImportError as exc:
            raise SessionError(str(exc)) from exc

    def _resolve_audo_identity(
        self, identity: ExportIdentity
    ) -> apf_audo_exact_slot.ResolvedExactSlot:
        expected_asset_id = self._audo_asset_id(identity)
        try:
            resolved = apf_audo_exact_slot.resolve_target(
                self.source.index_0a,
                identity.outer_table_index,
                identity.inner_file_index,
            )
        except apf_audo_exact_slot.ExactSlotImportError as exc:
            raise SessionError(str(exc)) from exc
        if resolved.asset_id != expected_asset_id:
            raise SessionError("The standalone AUDO target identity changed")
        return resolved

    @staticmethod
    def _ausb_asset_id(identity: ExportIdentity) -> str:
        if (
            identity.kind != "ausb_substream"
            or type(identity.outer_table_index) is not int
            or type(identity.inner_file_index) is not int
            or type(identity.substream_index) is not int
        ):
            raise SessionError(
                "AUSB exact-slot replacement requires one individual bank substream"
            )
        try:
            return apf_ausb_exact_slot.asset_id(
                identity.outer_table_index,
                identity.inner_file_index,
                identity.substream_index,
            )
        except apf_ausb_exact_slot.AusbExactSlotError as exc:
            raise SessionError(str(exc)) from exc

    def _resolve_ausb_identity(
        self, identity: ExportIdentity
    ) -> apf_ausb_exact_slot.ResolvedExactSlot:
        expected_asset_id = self._ausb_asset_id(identity)
        assert identity.substream_index is not None
        try:
            resolved = apf_ausb_exact_slot.resolve_target(
                self.source.index_0a,
                identity.outer_table_index,
                identity.inner_file_index,
                identity.substream_index,
            )
        except apf_ausb_exact_slot.AusbExactSlotError as exc:
            raise SessionError(str(exc)) from exc
        if resolved.asset_id != expected_asset_id:
            raise SessionError("The AUSB substream target identity changed")
        return resolved

    @staticmethod
    def _audo_metadata(
        resolved: apf_audo_exact_slot.ResolvedExactSlot,
    ) -> dict[str, object]:
        target = resolved.target
        return {
            "outer_table_index": resolved.outer_index,
            "inner_file_index": resolved.inner_index,
            "encoded_size": target.encoded_size,
            "sample_rate": target.sample_rate,
            "channel_count": target.channels,
            "declared_sample_count": target.declared_sample_count,
            "packet_count": target.encoded_size // 0x800,
            "writer_schema": AUDO_EXACT_SLOT_WRITER_SCHEMA,
        }

    def _protected_audo_fingerprints(
        self,
    ) -> apf_audo_exact_slot.SourceAudioFingerprints:
        if self._audo_source_fingerprints is None:
            try:
                self._audo_source_fingerprints = (
                    apf_audo_exact_slot.original_audio_fingerprints(
                        self.source.index_0a
                    )
                )
            except apf_audo_exact_slot.ExactSlotImportError as exc:
                raise SessionError(
                    f"Could not protect source audio from project export: {exc}"
                ) from exc
        return self._audo_source_fingerprints

    def _protected_audo_payload_hashes(self) -> frozenset[str]:
        return self._protected_audo_fingerprints().payload_sha256s

    def _protected_ausb_fingerprints(
        self,
    ) -> apf_audo_exact_slot.SourceAudioFingerprints:
        if self._ausb_source_fingerprints is None:
            try:
                self._ausb_source_fingerprints = (
                    apf_ausb_exact_slot.original_audio_fingerprints(
                        self.source.index_0a
                    )
                )
            except apf_ausb_exact_slot.AusbExactSlotError as exc:
                raise SessionError(
                    f"Could not protect source bank audio from project export: {exc}"
                ) from exc
        return self._ausb_source_fingerprints

    def _protected_ausb_payload_hashes(self) -> frozenset[str]:
        return self._protected_ausb_fingerprints().payload_sha256s

    def _reject_any_source_audio_reuse(self, payload: bytes) -> None:
        """Reject source packets from either APF audio storage family.

        AUDO and AUSB use different source inventories, but a shareable project
        must not be able to move a retail packet from one family into the other.
        Both complete inventories are cached for the session, and every public
        import/load/preview authorization crosses this combined boundary.
        """

        try:
            apf_audo_exact_slot.reject_source_audio_reuse(
                payload,
                self._protected_audo_fingerprints(),
            )
            apf_ausb_exact_slot.reject_source_audio_reuse(
                payload,
                self._protected_ausb_fingerprints(),
            )
        except (
            apf_audo_exact_slot.ExactSlotImportError,
            apf_ausb_exact_slot.AusbExactSlotError,
        ) as exc:
            raise SessionError(str(exc)) from exc

    @staticmethod
    def _ausb_metadata(
        resolved: apf_ausb_exact_slot.ResolvedExactSlot,
    ) -> dict[str, object]:
        target = resolved.target
        owner_asset_ids = [owner.asset_id for owner in resolved.owners]
        owner_fingerprint = hashlib.sha256(
            "\n".join(owner_asset_ids).encode("ascii")
        ).hexdigest()
        requested = resolved.requested_owner
        return {
            "outer_table_index": requested.descriptor_outer_index,
            "inner_file_index": requested.descriptor_inner_index,
            "substream_index": requested.substream_index,
            "encoded_size": target.encoded_size,
            "sample_rate": target.sample_rate,
            "channel_count": target.channels,
            "declared_sample_count": target.declared_sample_count,
            "packet_count": target.encoded_size // 0x800,
            "shared_owner_asset_ids": owner_asset_ids,
            "owner_fingerprint": owner_fingerprint,
            "writer_schema": AUSB_EXACT_SLOT_WRITER_SCHEMA,
        }

    def audio_pcm_target(self, identity: ExportIdentity) -> Pcm16Target:
        """Return the exact retail-free PCM16 authoring shape for one sound."""

        if identity.kind == "audo" and identity.substream_index is None:
            target = self._resolve_audo_identity(identity).target
        elif identity.kind == "ausb_substream" and identity.substream_index is not None:
            target = self._resolve_ausb_identity(identity).target
        else:
            raise SessionError(
                "PCM authoring supports one standalone AUDO or one AUSB substream"
            )
        try:
            return validate_pcm16_target(
                Pcm16Target(
                    channels=target.channels,
                    sample_rate=target.sample_rate,
                    frame_count=target.declared_sample_count,
                    encoded_size=target.encoded_size,
                )
            )
        except AudioEncodingError as exc:
            raise SessionError(str(exc)) from exc

    def export_audio_pcm_template(
        self,
        identity: ExportIdentity,
        destination: Path,
        *,
        progress: Callable[[str, int, int], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Pcm16TemplateReceipt:
        """Publish one exact silence WAV template without reading source audio."""

        try:
            return export_pcm16_template(
                destination,
                self.audio_pcm_target(identity),
                progress=progress,
                cancel_requested=cancel_requested,
            )
        except AudioEncodingError as exc:
            raise SessionError(str(exc)) from exc

    def replace_audio_from_pcm(
        self,
        identity: ExportIdentity,
        supplied_pcm_wav: Path,
        encoder: ExternalXma1Encoder,
        *,
        progress: Callable[[str, int, int], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Modification:
        """Encode one PCM WAV privately, then use the existing slot validator.

        The modification map and Undo stack remain untouched until the external
        process exits, the output passes its exact AUDO/AUSB validator, and the
        cross-family source-packet gate accepts every encoded packet.
        """

        modification = self._prepare_audio_from_pcm(
            identity,
            supplied_pcm_wav,
            encoder,
            progress=progress,
            cancel_requested=cancel_requested,
        )
        self._set(modification.asset_id, modification)
        return modification

    def _prepare_audio_from_pcm(
        self,
        identity: ExportIdentity,
        supplied_pcm_wav: Path,
        encoder: ExternalXma1Encoder,
        *,
        progress: Callable[[str, int, int], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> Modification:
        """Encode and validate one WAV without changing the edit map or Undo."""

        if not isinstance(encoder, ExternalXma1Encoder):
            raise SessionError(
                "PCM replacement requires a configured ExternalXma1Encoder"
            )
        if identity.kind == "audo" and identity.substream_index is None:
            resolved = self._resolve_audo_identity(identity)
            target = resolved.target
            family = "audo"
        elif identity.kind == "ausb_substream" and identity.substream_index is not None:
            resolved = self._resolve_ausb_identity(identity)
            target = resolved.target
            family = "ausb"
        else:
            raise SessionError(
                "PCM replacement supports one standalone AUDO or one AUSB substream"
            )
        pcm_target = Pcm16Target(
            channels=target.channels,
            sample_rate=target.sample_rate,
            frame_count=target.declared_sample_count,
            encoded_size=target.encoded_size,
        )
        # Conform first, so a modder can supply an ordinary audio file instead of
        # a WAV they had to shape by hand in an audio editor. A file that already
        # matches the target exactly is passed straight through untouched, which
        # keeps the long-standing path byte-identical. Anything else is converted
        # and then meets every check the encoder already ran -- the link count,
        # the RIFF structure, the five-way shape match and the exact data size
        # are all still applied to whatever it is handed, so a bad conversion
        # fails closed in exactly the way a bad hand-made WAV does.
        try:
            audio_shape = audio_conform.shape_for(
                pcm_target.channels, pcm_target.sample_rate, pcm_target.frame_count
            )
        except audio_conform.AudioConformError as exc:
            raise SessionError(str(exc)) from exc
        try:
            with tempfile.TemporaryDirectory(prefix="apf-audio-conform-") as workspace:
                try:
                    encode_input = audio_conform.conform(
                        supplied_pcm_wav, audio_shape, Path(workspace)
                    ).path
                except audio_conform.AudioConformError:
                    # Strictly additive: if the file cannot be converted -- it is
                    # not audio, or FFmpeg is absent -- hand the encoder the
                    # original exactly as before, so its own validation produces
                    # the same refusal it always did. Conversion may add a route,
                    # never take one away or reword an existing failure.
                    encode_input = supplied_pcm_wav
                encoded = encoder.encode(
                    encode_input,
                    pcm_target,
                    progress=progress,
                    cancel_requested=cancel_requested,
                )
                if not isinstance(encoded, ExternalEncodingResult):
                    raise SessionError(
                        "The external XMA1 encoder returned an invalid result"
                    )
                verify_xma1_signal_quality(
                    encode_input,
                    encoded.xma1_riff,
                    pcm_target,
                    cancel_requested=cancel_requested,
                )
        except AudioEncodingError as exc:
            raise SessionError(str(exc)) from exc
        existing_payload_paths = frozenset(self.replacements_root.iterdir())
        self._require_audio_pcm_not_cancelled(cancel_requested)
        modification: Modification | None = None
        try:
            if family == "audo":
                modification = self._prepare_audo_exact_slot_data(
                    resolved, encoded.xma1_riff
                )
            else:
                modification = self._prepare_ausb_exact_slot_data(
                    resolved, encoded.xma1_riff
                )
            # Exact-slot validation includes a complete FFmpeg decode and can
            # take long enough for the GUI Cancel button to be clicked.  The
            # final cooperative check is immediately before the sole edit-map
            # mutation.  A late cancellation owns no packet-cache payload.
            self._require_audio_pcm_not_cancelled(cancel_requested)
        except BaseException:
            if modification is not None:
                self._discard_new_uncommitted_audio_payload(
                    modification,
                    existing_payload_paths=existing_payload_paths,
                )
            raise
        assert modification is not None
        return modification

    @staticmethod
    def _require_audio_pcm_not_cancelled(
        cancel_requested: Callable[[], bool] | None,
    ) -> None:
        if cancel_requested is None:
            return
        try:
            cancelled = cancel_requested()
        except Exception as exc:
            raise SessionError(
                f"Could not check whether PCM audio replacement was cancelled: {exc}"
            ) from exc
        if cancelled:
            raise SessionError(
                "PCM audio replacement was cancelled; no project edit was staged"
            )

    def _discard_new_uncommitted_audio_payload(
        self,
        modification: Modification,
        *,
        existing_payload_paths: frozenset[Path],
    ) -> None:
        """Remove only a new, validator-created, wholly unreferenced packet file."""

        candidate = modification.replacement_path
        if candidate in existing_payload_paths:
            return
        protected_paths = {
            active.replacement_path for active in self._modifications.values()
        }
        protected_paths.update(
            active.replacement_path
            for snapshot in self._undo
            for active in snapshot.modifications.values()
        )
        if (
            candidate in protected_paths
            or candidate.parent != self.replacements_root
            or candidate.suffix != ".xma1-packets"
            or candidate.name
            != f"{modification.replacement_sha256}.xma1-packets"
        ):
            return
        try:
            info = candidate.lstat()
            if (
                stat.S_ISREG(info.st_mode)
                and not stat.S_ISLNK(info.st_mode)
                and info.st_nlink == 1
            ):
                candidate.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise SessionError(
                "PCM audio replacement was cancelled, but its uncommitted private "
                f"packet cache could not be removed: {exc}"
            ) from exc

    def replace_audo_exact_slot(
        self,
        identity: ExportIdentity,
        supplied_xma: Path,
    ) -> Modification:
        """Validate and stage one pre-encoded standalone XMA1 sound."""

        modification = self._prepare_audo_exact_slot(identity, supplied_xma)
        self._set(modification.asset_id, modification)
        return modification

    def _prepare_audo_exact_slot(
        self,
        identity: ExportIdentity,
        supplied_xma: Path,
    ) -> Modification:
        """Validate one AUDO replacement without changing the active edit map."""

        resolved = self._resolve_audo_identity(identity)
        data = self._read_bounded_regular(
            supplied_xma,
            maximum=resolved.encoded_size + 1024 * 1024,
            label="pre-encoded XMA1 replacement",
        )
        return self._prepare_audo_exact_slot_data(resolved, data)

    def _prepare_audo_exact_slot_data(
        self,
        resolved: object,
        data: bytes,
    ) -> Modification:
        """Validate already descriptor-read AUDO bytes into one modification."""

        try:
            result = apf_audo_exact_slot.validate_exact_slot_import(
                data,
                resolved.target,
                self._protected_audo_fingerprints(),
            )
        except apf_audo_exact_slot.ExactSlotImportError as exc:
            raise SessionError(str(exc)) from exc
        digest = hashlib.sha256(result.payload).hexdigest()
        self._reject_any_source_audio_reuse(result.payload)
        replacement_receipt = result.receipt.get("replacement")
        if (
            not isinstance(replacement_receipt, Mapping)
            or digest != replacement_receipt.get("payload_sha256")
        ):
            raise SessionError("The XMA1 validator returned an inconsistent receipt")
        if digest in self._protected_audo_payload_hashes():
            raise SessionError(
                "This XMA1 packet payload matches audio from the loaded retail game. "
                "Shareable projects may contain only user-supplied replacement audio."
            )
        stored = self._store_payload(digest, result.payload, ".xma1-packets")
        modification = Modification(
            asset_id=resolved.asset_id,
            kind=AUDO_EXACT_SLOT_KIND,
            replacement_path=stored,
            replacement_sha256=digest,
            metadata=self._audo_metadata(resolved),
        )
        return modification

    def replace_ausb_exact_slot(
        self,
        identity: ExportIdentity,
        supplied_xma: Path,
    ) -> Modification:
        """Validate and stage one pre-encoded exact AUSB-bank substream."""

        modification = self._prepare_ausb_exact_slot(identity, supplied_xma)
        self._set(modification.asset_id, modification)
        return modification

    def _prepare_ausb_exact_slot(
        self,
        identity: ExportIdentity,
        supplied_xma: Path,
    ) -> Modification:
        """Validate one AUSB replacement without changing the active edit map."""

        resolved = self._resolve_ausb_identity(identity)
        data = self._read_bounded_regular(
            supplied_xma,
            maximum=resolved.target.encoded_size + 1024 * 1024,
            label="pre-encoded AUSB XMA1 replacement",
        )
        return self._prepare_ausb_exact_slot_data(resolved, data)

    def _prepare_ausb_exact_slot_data(
        self,
        resolved: object,
        data: bytes,
    ) -> Modification:
        """Validate already descriptor-read AUSB bytes into one modification."""

        try:
            result = apf_ausb_exact_slot.validate_exact_slot_import(
                data,
                resolved,
                self._protected_ausb_fingerprints(),
            )
        except apf_ausb_exact_slot.AusbExactSlotError as exc:
            raise SessionError(str(exc)) from exc
        digest = hashlib.sha256(result.payload).hexdigest()
        self._reject_any_source_audio_reuse(result.payload)
        replacement_receipt = result.receipt.get("replacement")
        if (
            not isinstance(replacement_receipt, Mapping)
            or digest != replacement_receipt.get("payload_sha256")
        ):
            raise SessionError("The AUSB XMA1 validator returned an inconsistent receipt")
        if digest in self._protected_ausb_payload_hashes():
            raise SessionError(
                "This XMA1 packet payload matches audio from the loaded retail game. "
                "Shareable projects may contain only user-supplied replacement audio."
            )
        stored = self._store_payload(digest, result.payload, ".xma1-packets")
        modification = Modification(
            asset_id=resolved.asset_id,
            kind=AUSB_EXACT_SLOT_KIND,
            replacement_path=stored,
            replacement_sha256=digest,
            metadata=self._ausb_metadata(resolved),
        )
        return modification

    @staticmethod
    def _validate_ausb_alias_replacements(
        modifications: Mapping[str, Modification],
    ) -> None:
        """Refuse divergent semantic edits that own one physical AUSB range."""

        payload_by_owner_group: dict[tuple[str, ...], tuple[str, str]] = {}
        for modification in modifications.values():
            if modification.kind != AUSB_EXACT_SLOT_KIND:
                continue
            raw_owners = modification.metadata.get("shared_owner_asset_ids")
            if not isinstance(raw_owners, list):
                raise SessionError(
                    f"AUSB alias metadata is invalid: {modification.asset_id}"
                )
            owners = tuple(str(value) for value in raw_owners)
            if (
                not 1 <= len(owners) <= 8
                or len(set(owners)) != len(owners)
                or tuple(sorted(owners)) != owners
                or modification.asset_id not in owners
            ):
                raise SessionError(
                    f"AUSB alias metadata changed: {modification.asset_id}"
                )
            prior = payload_by_owner_group.get(owners)
            if prior is not None and prior[0] != modification.replacement_sha256:
                raise SessionError(
                    "Conflicting AUSB alias replacements target the same physical "
                    f"sound: {prior[1]} and {modification.asset_id}. Use the same "
                    "XMA1 payload for every supplied alias owner."
                )
            payload_by_owner_group[owners] = (
                modification.replacement_sha256,
                modification.asset_id,
            )

    def _discard_failed_audio_pack_payloads(
        self, prepared: Iterable[Modification]
    ) -> None:
        """Remove only new, unreferenced packet files from a failed batch."""

        replacement_root = getattr(self, "replacements_root", None)
        if not isinstance(replacement_root, Path):
            return
        protected_paths = {
            modification.replacement_path
            for modification in self._modifications.values()
        }
        protected_paths.update(
            modification.replacement_path
            for snapshot in self._undo
            for modification in snapshot.modifications.values()
        )
        for modification in prepared:
            candidate = modification.replacement_path
            if (
                candidate in protected_paths
                or candidate.parent != replacement_root
                or candidate.suffix != ".xma1-packets"
            ):
                continue
            try:
                info = candidate.lstat()
                if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                    candidate.unlink()
            except OSError:
                continue

    def _require_audio_pack_baseline(
        self,
        plan: AudioReplacementPackPlan,
    ) -> None:
        """Reject stale target edits without coupling the pack to unrelated work."""

        for supplied in plan.supplied:
            entry = supplied.entry
            try:
                current = current_audio_target_baseline(
                    entry,
                    self._modifications,
                )
            except AudioReplacementPackError as exc:
                raise SessionError(str(exc)) from exc
            if current != entry.baseline:
                replacement_kind = (
                    "exact PCM16 WAV"
                    if plan.input_kind == "pcm16"
                    else "pre-encoded XMA1 file"
                )
                raise SessionError(
                    "Project audio changed after this template was created: "
                    f"{entry.asset_id}. Export a fresh replacement template from "
                    "the current project, then add your "
                    f"{replacement_kind} again."
                )

    def _audio_replacement_project_revision(
        self,
        modifications: Mapping[str, Modification] | None = None,
    ) -> str:
        """Hash only private active-audio metadata for confirmation binding."""

        active = self._modifications if modifications is None else modifications
        rows = []
        for asset_id in sorted(active):
            modification = active[asset_id]
            if modification.kind not in _AUDIO_REPLACEMENT_KINDS:
                continue
            rows.append(
                {
                    "asset_id": asset_id,
                    "kind": modification.kind,
                    "replacement_sha256": modification.replacement_sha256,
                    "metadata": dict(modification.metadata),
                }
            )
        encoded = json.dumps(
            rows,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _audio_replacement_session_binding(self) -> str:
        binding = getattr(self, "_audio_replacement_preview_nonce", None)
        if not isinstance(binding, str) or not binding:
            # Supports narrowly constructed test sessions without weakening
            # production sessions created through __init__.
            binding = uuid4().hex
            self._audio_replacement_preview_nonce = binding
        return binding

    def _audio_replacement_confirmation_token(
        self,
        plan: AudioReplacementPackPlan,
        prepared: tuple[Modification, ...],
    ) -> str:
        """Bind confirmation to exact inputs, result, source, and audio revision."""

        if len(prepared) != len(plan.supplied):
            raise SessionError("The audio replacement preview is incomplete")
        members: list[dict[str, object]] = []
        for supplied, modification in zip(plan.supplied, prepared, strict=True):
            member_sha256 = (
                supplied.file_identity.content_sha256
                if supplied.file_identity is not None
                else None
            )
            # Loaded folder and ZIP plans always carry the exact authored member
            # digest.  The fallback keeps synthetic unit plans useful while still
            # binding them to the fully validated packet result.
            if not isinstance(member_sha256, str) or len(member_sha256) != 64:
                member_sha256 = modification.replacement_sha256
            members.append(
                {
                    "asset_id": supplied.entry.asset_id,
                    "kind": supplied.entry.kind,
                    "replacement_file": supplied.entry.replacement_file.as_posix(),
                    "member_sha256": member_sha256,
                    "validated_result_sha256": modification.replacement_sha256,
                }
            )
        message = json.dumps(
            {
                "domain": _AUDIO_REPLACEMENT_CONFIRMATION_DOMAIN,
                "source_sha256": plan.source_sha256,
                "manifest_sha256": plan.manifest_sha256,
                "baseline_sha256": plan.baseline_sha256,
                "input_kind": plan.input_kind,
                "template_entry_count": plan.template_entry_count,
                "missing_count": plan.missing_count,
                "project_audio_revision": self._audio_replacement_project_revision(),
                "members": members,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(
            self._audio_replacement_session_binding().encode("ascii"),
            message,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _audio_replacement_modified_count(
        modifications: Mapping[str, Modification],
    ) -> int:
        return sum(
            modification.kind in _AUDIO_REPLACEMENT_KINDS
            for modification in modifications.values()
        )

    def _prepare_audio_replacement_pack(
        self,
        plan: AudioReplacementPackPlan,
        *,
        encoder: ExternalXma1Encoder | None = None,
        progress: Callable[[AudioReplacementApplyProgress], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> _PreparedAudioReplacementPack:
        """Fully validate one pack without mutating project or Undo state."""

        if plan.input_kind not in {"xma1", "pcm16"}:
            raise SessionError("The audio replacement pack has an unknown input kind")
        if plan.source_sha256 != self.source.source_sha256:
            raise SessionError(
                "This audio replacement pack belongs to a different loaded game source"
            )
        if not plan.supplied:
            raise SessionError(
                "The audio replacement pack contains no supplied audio files"
            )
        if plan.input_kind == "pcm16":
            if len(plan.supplied) > MAX_PCM_PACK_SUPPLIED:
                raise SessionError(
                    "A PCM replacement pack accepts at most 256 supplied PCM16 "
                    "WAV files per import"
                )
            if not isinstance(encoder, ExternalXma1Encoder):
                raise SessionError(
                    "PCM16 audio replacement pack requires a configured "
                    "ExternalXma1Encoder"
                )
        self._require_audio_pack_baseline(plan)
        total = len(plan.supplied)

        def report(
            stage: str,
            completed: int,
            asset_id: str | None = None,
        ) -> None:
            if progress is not None:
                progress(
                    AudioReplacementApplyProgress(
                        stage=stage,
                        completed=completed,
                        total=total,
                        asset_id=asset_id,
                    )
                )

        def cancelled(
            prepared: list[Modification],
        ) -> _PreparedAudioReplacementPack:
            # Validation may have populated private content-addressed packet
            # files.  A cancelled batch owns no active edit, so discard only
            # those new, unreferenced files before returning a normal receipt.
            self._discard_failed_audio_pack_payloads(prepared)
            report("cancelled", len(prepared))
            return _PreparedAudioReplacementPack(
                prepared=(),
                updated=dict(self._modifications),
                unchanged_count=0,
                changed_ids=frozenset(),
                validated_count=len(prepared),
                was_cancelled=True,
            )

        prepared: list[Modification] = []
        try:
            seen_asset_ids: set[str] = set()
            for supplied in plan.supplied:
                if cancel_requested is not None and cancel_requested():
                    return cancelled(prepared)
                entry = supplied.entry
                report(
                    "encoding" if plan.input_kind == "pcm16" else "validating",
                    len(prepared),
                    entry.asset_id,
                )
                if entry.asset_id in seen_asset_ids:
                    raise SessionError(
                        f"The audio replacement pack repeats {entry.asset_id}"
                    )
                seen_asset_ids.add(entry.asset_id)
                identity_presence = (
                    plan.root_identity is not None,
                    plan.payload_directory_identity is not None,
                    supplied.file_identity is not None,
                )
                if any(identity_presence) and not all(identity_presence):
                    raise SessionError(
                        "The audio replacement plan has an incomplete pinned "
                        "filesystem identity"
                    )
                pinned_payload = all(identity_presence)
                expected_kind = (
                    AUDO_EXACT_SLOT_KIND
                    if entry.kind == "audo"
                    else AUSB_EXACT_SLOT_KIND
                    if entry.kind == "ausb_substream"
                    else None
                )
                if expected_kind is None:
                    raise SessionError(
                        f"Unknown audio replacement kind: {entry.kind}"
                    )
                if plan.input_kind == "pcm16":
                    assert isinstance(encoder, ExternalXma1Encoder)
                    pcm_context = (
                        materialize_audio_replacement_pcm(plan, supplied)
                        if pinned_payload
                        else nullcontext(supplied.path)
                    )
                    try:
                        with pcm_context as supplied_pcm:
                            modification = self._prepare_audio_from_pcm(
                                entry.identity,
                                supplied_pcm,
                                encoder,
                                progress=lambda _stage, _completed, _total: report(
                                    "encoding", len(prepared), entry.asset_id
                                ),
                                cancel_requested=cancel_requested,
                            )
                    except AudioReplacementPackError as exc:
                        raise SessionError(str(exc)) from exc
                    except SessionError:
                        if cancel_requested is not None and cancel_requested():
                            return cancelled(prepared)
                        raise
                else:
                    try:
                        supplied_data = (
                            read_audio_replacement_payload(
                                plan,
                                supplied,
                                maximum=int(entry.target["encoded_size"])
                                + 1024 * 1024,
                            )
                            if pinned_payload
                            else None
                        )
                    except AudioReplacementPackError as exc:
                        raise SessionError(str(exc)) from exc
                    if entry.kind == "audo":
                        modification = (
                            self._prepare_audo_exact_slot_data(
                                self._resolve_audo_identity(entry.identity),
                                supplied_data,
                            )
                            if supplied_data is not None
                            else self._prepare_audo_exact_slot(
                                entry.identity,
                                supplied.path,
                            )
                        )
                    else:
                        modification = (
                            self._prepare_ausb_exact_slot_data(
                                self._resolve_ausb_identity(entry.identity),
                                supplied_data,
                            )
                            if supplied_data is not None
                            else self._prepare_ausb_exact_slot(
                                entry.identity,
                                supplied.path,
                            )
                        )
                if (
                    modification.asset_id != entry.asset_id
                    or modification.kind != expected_kind
                    or dict(modification.metadata) != dict(entry.target)
                ):
                    raise SessionError(
                        f"Audio target identity or slot shape changed: {entry.asset_id}"
                    )
                prepared.append(modification)
                if cancel_requested is not None and cancel_requested():
                    return cancelled(prepared)
                report("validated", len(prepared), entry.asset_id)

            # The progress callback for the final file may request
            # cancellation.  Honor it before computing or committing the new
            # active map so cancellation always remains all-or-nothing.
            if cancel_requested is not None and cancel_requested():
                return cancelled(prepared)

            updated = dict(self._modifications)
            unchanged_count = 0
            for modification in prepared:
                active = updated.get(modification.asset_id)
                if active is not None and active.kind != modification.kind:
                    raise SessionError(
                        f"The active edit type is invalid for {modification.asset_id}"
                    )
                if active == modification:
                    unchanged_count += 1
                updated[modification.asset_id] = modification
            self._validate_ausb_alias_replacements(updated)
            # Exact writers and progress callbacks can be slow. Recheck the
            # optimistic target lock before returning a trustworthy result.
            self._require_audio_pack_baseline(plan)
        except BaseException:
            self._discard_failed_audio_pack_payloads(prepared)
            raise
        changed_ids = {
            asset_id
            for asset_id in set(self._modifications).union(updated)
            if self._modifications.get(asset_id) != updated.get(asset_id)
        }
        return _PreparedAudioReplacementPack(
            prepared=tuple(prepared),
            updated=updated,
            unchanged_count=unchanged_count,
            changed_ids=frozenset(changed_ids),
            validated_count=len(prepared),
        )

    def preview_audio_replacement_pack(
        self,
        plan: AudioReplacementPackPlan,
        *,
        encoder: ExternalXma1Encoder | None = None,
        progress: Callable[[AudioReplacementApplyProgress], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> AudioReplacementPreviewReceipt:
        """Fully validate a pack and return counts without staging any edit."""

        batch = self._prepare_audio_replacement_pack(
            plan,
            encoder=encoder,
            progress=progress,
            cancel_requested=cancel_requested,
        )
        if batch.was_cancelled:
            current_count = self._audio_replacement_modified_count(
                self._modifications
            )
            return AudioReplacementPreviewReceipt(
                root=plan.reported_root or plan.root,
                template_entry_count=plan.template_entry_count,
                supplied_count=len(plan.supplied),
                would_change_count=0,
                already_current_count=0,
                missing_count=plan.missing_count,
                current_modified_audio_count=current_count,
                resulting_modified_audio_count=current_count,
                validated_count=batch.validated_count,
                confirmation_token="",
                was_cancelled=True,
                input_kind=plan.input_kind,
            )
        try:
            token = self._audio_replacement_confirmation_token(
                plan,
                batch.prepared,
            )
            receipt = AudioReplacementPreviewReceipt(
                root=plan.reported_root or plan.root,
                template_entry_count=plan.template_entry_count,
                supplied_count=len(plan.supplied),
                would_change_count=len(batch.changed_ids),
                already_current_count=batch.unchanged_count,
                missing_count=plan.missing_count,
                current_modified_audio_count=self._audio_replacement_modified_count(
                    self._modifications
                ),
                resulting_modified_audio_count=self._audio_replacement_modified_count(
                    batch.updated
                ),
                validated_count=batch.validated_count,
                confirmation_token=token,
                input_kind=plan.input_kind,
            )
        finally:
            # Preview never owns active edits. Remove only cache files that no
            # current project/Undo snapshot already references.
            self._discard_failed_audio_pack_payloads(batch.prepared)
        if progress is not None:
            try:
                progress(
                    AudioReplacementApplyProgress(
                        "preview_complete",
                        batch.validated_count,
                        len(plan.supplied),
                    )
                )
            except BaseException:
                pass
        return receipt

    def apply_audio_replacement_pack(
        self,
        plan: AudioReplacementPackPlan,
        *,
        encoder: ExternalXma1Encoder | None = None,
        progress: Callable[[AudioReplacementApplyProgress], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        confirmation_token: str | None = None,
    ) -> AudioReplacementApplyReceipt:
        """Revalidate and apply a replacement pack as exactly one Undo action.

        A product confirmation supplies the opaque token returned by preview.
        Direct core callers may omit it for the legacy atomic API.
        """

        batch = self._prepare_audio_replacement_pack(
            plan,
            encoder=encoder,
            progress=progress,
            cancel_requested=cancel_requested,
        )
        if batch.was_cancelled:
            return AudioReplacementApplyReceipt(
                root=plan.reported_root or plan.root,
                template_entry_count=plan.template_entry_count,
                supplied_count=len(plan.supplied),
                staged_count=0,
                unchanged_count=0,
                missing_count=plan.missing_count,
                undo_action_count=0,
                validated_count=batch.validated_count,
                was_cancelled=True,
                input_kind=plan.input_kind,
            )
        try:
            if confirmation_token is not None:
                current_token = self._audio_replacement_confirmation_token(
                    plan,
                    batch.prepared,
                )
                if not hmac.compare_digest(current_token, confirmation_token):
                    raise SessionError(
                        "The replacement pack or project audio changed after preview. "
                        "Review the pack again before choosing Apply."
                    )
            if not batch.changed_ids:
                raise SessionError(
                    "Every supplied audio replacement is already staged; this pack "
                    "would make no project changes."
                )
        except BaseException:
            self._discard_failed_audio_pack_payloads(batch.prepared)
            raise
        updated = dict(batch.updated)
        self._record_undo()
        self._modifications = updated
        # Progress is advisory. Once the atomic state swap has committed, a
        # broken UI callback must not turn success into a reported failure.
        try:
            if progress is not None:
                progress(
                    AudioReplacementApplyProgress(
                        "complete",
                        batch.validated_count,
                        len(plan.supplied),
                    )
                )
        except BaseException:
            pass
        return AudioReplacementApplyReceipt(
            root=plan.reported_root or plan.root,
            template_entry_count=plan.template_entry_count,
            supplied_count=len(plan.supplied),
            staged_count=len(batch.changed_ids),
            unchanged_count=batch.unchanged_count,
            missing_count=plan.missing_count,
            undo_action_count=1,
            validated_count=batch.validated_count,
            was_cancelled=False,
            input_kind=plan.input_kind,
        )

    def _require_helmet_crest_slot(
        self, crest_asset_index: int, crest_outer_entry_index: int
    ) -> None:
        """Bind a project target to the crest package declared by this disc."""

        try:
            matches = tuple(
                slot
                for slot in apf_team_crests.crest_slots(self.source.index_0a)
                if slot.asset_index == crest_asset_index
            )
        except Exception as exc:  # tool parsers use format-specific errors
            raise SessionError(f"Could not resolve the selected crest slot: {exc}") from exc
        if (
            len(matches) != 1
            or matches[0].outer_entry_index != crest_outer_entry_index
        ):
            raise SessionError(
                "The selected crest package no longer matches this APF game"
            )

    def replace_helmet_crest_design(
        self,
        supplied_png: Path,
        *,
        profile: str,
        crest_asset_index: int,
        crest_outer_entry_index: int,
        fit_visible_mask: bool = False,
    ) -> Modification:
        """Stage one selected-team crest plus its fixed helmet coverage profile.

        The project payload is always one normalized 512x512 RGBA PNG.  The
        full-shell profile changes the shared helmet model at build time; the
        crest package and cache selection remain team-specific.
        """

        data, _source_digest = self._validated_png(
            Path(supplied_png), width=512, height=512, contract="helmet_crest_design"
        )
        try:
            with Image.open(BytesIO(data)) as image:
                image.load()
                rgba = image.tobytes()
        except Exception as exc:  # already decoded above; retain a clear boundary
            raise SessionError(f"Could not decode the helmet crest PNG: {exc}") from exc
        if not any(rgba[index] for index in range(3, len(rgba), 4)):
            raise SessionError("The helmet crest PNG is fully transparent")
        active_x = [
            (offset // 4) % 512
            for offset in range(0, len(rgba), 4)
            if rgba[offset] or rgba[offset + 1] or rgba[offset + 2]
        ]
        if not active_x:
            raise SessionError(
                "The helmet crest has no visible RGB mask regions; use flat red, "
                "green, or blue mask art"
            )
        source_coverage = (max(active_x) - min(active_x) + 1) / 512
        output_coverage = source_coverage
        if fit_visible_mask:
            if profile != FULL_SHELL_CREST_PROFILE:
                raise SessionError(
                    "Fit visible mask to full helmet wrap requires the full-shell "
                    "coverage profile"
                )
            try:
                fitted = apf_helmet_crest_mask_fit.fit_visible_mask_rgba(rgba)
                # Keep the semantic, pre-guard fitted design as the project
                # payload.  The sampler guard is a build-time transport detail;
                # persisting it here would compress the art again on every
                # project reload/build cycle.
                rgba = fitted.output_rgba
                data = apf_helmet_crest_mask_fit.encode_rgba_png(
                    512, 512, rgba
                )
            except apf_helmet_crest_mask_fit.MaskFitError as exc:
                raise SessionError(f"Could not fit the helmet crest mask: {exc}") from exc
            output_coverage = fitted.output_horizontal_coverage
        if profile == FULL_SHELL_CREST_PROFILE:
            # The routed whole shell draws through the crest material, where a
            # translucent shell body renders see-through in game.  GUI-authored
            # canvases (transparent placement background or the bounded-crest
            # 8/15 transport alpha) are normalized to the opaque full-shell
            # contract before storage; the writer rejects anything else.
            normalized = opaque_shell_body_rgba(rgba)
            if normalized != rgba:
                rgba = normalized
                data = apf_helmet_crest_mask_fit.encode_rgba_png(
                    512, 512, rgba
                )
            try:
                validate_full_shell_region_mask_rgba(rgba)
            except HelmetLogoRegionError as exc:
                raise SessionError(
                    "Full-shell helmet crests must be semantic APF region masks "
                    "with an opaque shell body; convert normal artwork or fix "
                    f"the advanced mask first: {exc}"
                ) from exc
        self._require_helmet_crest_slot(
            crest_asset_index, crest_outer_entry_index
        )
        try:
            target_metadata = helmet_crest_metadata(
                profile=profile,
                crest_asset_index=crest_asset_index,
                crest_outer_entry_index=crest_outer_entry_index,
                fit_visible_mask=fit_visible_mask,
                source_horizontal_coverage=source_coverage,
                output_horizontal_coverage=output_coverage,
            )
        except HelmetCrestDesignError as exc:
            raise SessionError(str(exc)) from exc
        digest = hashlib.sha256(data).hexdigest()
        stored = self._store_replacement(
            HELMET_CREST_DESIGN_EDIT_ID, digest, data
        )
        modification = Modification(
            asset_id=HELMET_CREST_DESIGN_EDIT_ID,
            kind=HELMET_CREST_DESIGN_KIND,
            replacement_path=stored,
            replacement_sha256=digest,
            metadata=target_metadata,
        )
        self._set(HELMET_CREST_DESIGN_EDIT_ID, modification)
        return modification

    def replace_uniform(self, asset: UniformAsset | str, supplied_png: Path) -> Modification:
        item = self.catalog.uniform(asset) if isinstance(asset, str) else asset
        # Preserve a verified local original before accepting an edit.
        self.asset_io.preview_uniform(item)
        data, digest = self._validated_png(
            supplied_png,
            width=item.width,
            height=item.height,
            contract=item.family,
        )
        stored = self._store_replacement(item.asset_id, digest, data)
        modification = Modification(
            asset_id=item.asset_id,
            kind="uniform",
            replacement_path=stored,
            replacement_sha256=digest,
            metadata={
                "family": item.family,
                "asset_index": item.asset_index,
                "width": item.width,
                "height": item.height,
                "outer_index": item.outer_index,
                "inner_index": item.inner_index,
            },
        )
        self._set(item.asset_id, modification)
        return modification

    def replace_digital_font(self, supplied_png: Path) -> Modification:
        self.asset_io.preview_digital_font()
        data, digest = self._validated_png(
            supplied_png, width=128, height=128, contract="digital_font"
        )
        asset_id = "apf:presentation:digital_font"
        stored = self._store_replacement(asset_id, digest, data)
        modification = Modification(
            asset_id=asset_id,
            kind="digital_font",
            replacement_path=stored,
            replacement_sha256=digest,
            metadata={
                "width": 128,
                "height": 128,
                "outer_index": 1310,
                "inner_index": 246,
                "stored_channel": "alpha",
            },
        )
        self._set(asset_id, modification)
        return modification

    def replace_draft_logo(self, supplied_png: Path) -> Modification:
        item = self.catalog.get(DRAFT_LOGO_CATALOG_ID)
        if (
            item.outer_index != DRAFT_LOGO_OUTER_INDEX
            or item.inner_index != DRAFT_LOGO_INNER_INDEX
            or item.name != "draft_logo"
            or item.type_name != "TXTR"
            or item.status is not ApfStatus.EDITABLE
        ):
            raise SessionError("The bounded draft_logo target changed in this game")
        # The original is a derived PNG in the private cache, never a project
        # payload. Preserve it before accepting the user's replacement.
        self.asset_io.preview_texture(item)
        data, digest = self._validated_png(
            supplied_png, width=128, height=128, contract="draft_logo"
        )
        stored = self._store_replacement(DRAFT_LOGO_EDIT_ID, digest, data)
        modification = Modification(
            asset_id=DRAFT_LOGO_EDIT_ID,
            kind="draft_logo",
            replacement_path=stored,
            replacement_sha256=digest,
            metadata={
                "width": 128,
                "height": 128,
                "outer_index": DRAFT_LOGO_OUTER_INDEX,
                "inner_index": DRAFT_LOGO_INNER_INDEX,
                "format": "BC3",
                "mip_levels": 1,
            },
        )
        self._set(DRAFT_LOGO_EDIT_ID, modification)
        return modification

    def localization_text_allocations(
        self,
    ) -> tuple[apf_txt_loc_patch.TextAllocation, ...]:
        if self._localization_allocations is None:
            try:
                rows = apf_txt_loc_patch.inventory(self.source.index_0a)
            except apf_txt_loc_patch.TextPatchError as exc:
                raise SessionError(str(exc)) from exc
            self._localization_allocations = {row.asset_id: row for row in rows}
        return tuple(
            self._localization_allocations[key]
            for key in sorted(
                self._localization_allocations,
                key=lambda value: apf_txt_loc_patch.parse_asset_id(value),
            )
        )

    def _localization_allocation(
        self, asset_id: str
    ) -> apf_txt_loc_patch.TextAllocation:
        self.localization_text_allocations()
        assert self._localization_allocations is not None
        try:
            return self._localization_allocations[asset_id]
        except KeyError as exc:
            raise SessionError(f"Unknown APF text allocation: {asset_id}") from exc

    @staticmethod
    def _localization_metadata(
        allocation: apf_txt_loc_patch.TextAllocation,
    ) -> dict[str, object]:
        return {
            "outer_index": allocation.outer_index,
            "inner_index": allocation.inner_index,
            "pool_index": allocation.pool_index,
            "table_name": allocation.table_name,
            "maximum_utf16_units": allocation.maximum_utf16_units,
            "reference_count": allocation.reference_count,
        }

    def replace_localization_text(
        self, asset_id: str, replacement: str
    ) -> Modification:
        allocation = self._localization_allocation(asset_id)
        try:
            apf_txt_loc_patch.validate_replacement(allocation, replacement)
            payload = encode_text_payload(replacement)
        except (apf_txt_loc_patch.TextPatchError, ProjectError) as exc:
            raise SessionError(str(exc)) from exc
        digest = hashlib.sha256(payload).hexdigest()
        stored = self._store_payload(digest, payload, ".json")
        modification = Modification(
            asset_id=asset_id,
            kind="localization_text",
            replacement_path=stored,
            replacement_sha256=digest,
            metadata=self._localization_metadata(allocation),
        )
        self._set(asset_id, modification)
        return modification

    def apply_localization_text_batch(
        self,
        replacements: Mapping[str, str],
        *,
        revert_asset_ids: Iterable[str] = (),
    ) -> int:
        """Validate and apply one text batch as a single undoable action.

        Payloads may be copied into the private session cache while the batch is
        being prepared, but the active edit map is changed only after every
        target and replacement has passed the live allocation contract.
        """

        replacement_items = tuple((str(key), value) for key, value in replacements.items())
        revert_ids = tuple(dict.fromkeys(str(value) for value in revert_asset_ids))
        overlap = set(key for key, _value in replacement_items).intersection(revert_ids)
        if overlap:
            raise SessionError(
                "A text batch cannot replace and revert the same allocation: "
                f"{sorted(overlap)[0]}"
            )

        prepared: list[Modification] = []
        for asset_id, replacement in replacement_items:
            if not isinstance(replacement, str):
                raise SessionError(f"Text replacement must be a string: {asset_id}")
            allocation = self._localization_allocation(asset_id)
            try:
                apf_txt_loc_patch.validate_replacement(allocation, replacement)
                payload = encode_text_payload(replacement)
            except (apf_txt_loc_patch.TextPatchError, ProjectError) as exc:
                raise SessionError(str(exc)) from exc
            digest = hashlib.sha256(payload).hexdigest()
            stored = self._store_payload(digest, payload, ".json")
            prepared.append(
                Modification(
                    asset_id=asset_id,
                    kind="localization_text",
                    replacement_path=stored,
                    replacement_sha256=digest,
                    metadata=self._localization_metadata(allocation),
                )
            )

        for asset_id in revert_ids:
            self._localization_allocation(asset_id)
            active = self._modifications.get(asset_id)
            if active is not None and active.kind != "localization_text":
                raise SessionError(
                    f"The active edit type is invalid for text allocation {asset_id}"
                )

        updated = dict(self._modifications)
        for asset_id in revert_ids:
            updated.pop(asset_id, None)
        for modification in prepared:
            updated[modification.asset_id] = modification
        if updated == self._modifications:
            return 0
        changed_ids = {
            asset_id
            for asset_id in set(self._modifications).union(updated)
            if self._modifications.get(asset_id) != updated.get(asset_id)
        }
        self._record_undo()
        self._modifications = updated
        return len(changed_ids)

    def localization_text_value(self, asset_id: str) -> str:
        allocation = self._localization_allocation(asset_id)
        modification = self._modifications.get(asset_id)
        if modification is None:
            return allocation.text
        if modification.kind != "localization_text":
            raise SessionError(f"The active edit type is invalid for {asset_id}")
        try:
            return decode_text_payload(
                modification.replacement_path.read_bytes(), asset_id
            )
        except (OSError, ProjectError) as exc:
            raise SessionError(f"The active text replacement is invalid: {exc}") from exc

    def roster_identity_allocations(
        self,
    ) -> tuple[apf_roster_identity_patch.RosterIdentityAllocation, ...]:
        if self._roster_identity_allocations is None:
            try:
                rows = apf_roster_identity_patch.inventory(self.source.index_0a)
            except apf_roster_identity_patch.RosterIdentityError as exc:
                raise SessionError(str(exc)) from exc
            self._roster_identity_allocations = {row.asset_id: row for row in rows}
        return tuple(
            self._roster_identity_allocations[key]
            for key in sorted(
                self._roster_identity_allocations,
                key=apf_roster_identity_patch.parse_asset_id,
            )
        )

    def _roster_identity_allocation(
        self, asset_id: str
    ) -> apf_roster_identity_patch.RosterIdentityAllocation:
        self.roster_identity_allocations()
        assert self._roster_identity_allocations is not None
        try:
            return self._roster_identity_allocations[asset_id]
        except KeyError as exc:
            raise SessionError(f"Unknown APF roster-name allocation: {asset_id}") from exc

    def roster_identity_edit_scope(self, asset_id: str) -> str | None:
        """Return the centralized runtime-proved scope for one allocation."""

        return apf_roster_identity_patch.roster_identity_edit_scope(
            self._roster_identity_allocation(asset_id)
        )

    def roster_identity_is_product_editable(self, asset_id: str) -> bool:
        """Return whether the public product may author this ROST allocation."""

        return self.roster_identity_edit_scope(asset_id) is not None

    def roster_identity_is_team_display_name(self, asset_id: str) -> bool:
        """Compatibility wrapper for callers that need the original scope."""

        return self.roster_identity_edit_scope(asset_id) == (
            apf_roster_identity_patch.TEAM_DISPLAY_NAME_EDIT_SCOPE
        )

    def replace_roster_identity_text(
        self, asset_id: str, replacement: str
    ) -> Modification:
        allocation = self._roster_identity_allocation(asset_id)
        if not self.roster_identity_is_product_editable(asset_id):
            raise SessionError(
                "Only team display names and player first/last names are editable "
                "right now. Team abbreviations and mixed, zero-capacity, or "
                "unknown roster-name allocations remain runtime-locked."
            )
        try:
            apf_roster_identity_patch.validate_replacement(allocation, replacement)
            payload = encode_text_payload(replacement)
        except (
            apf_roster_identity_patch.RosterIdentityError,
            ProjectError,
        ) as exc:
            raise SessionError(str(exc)) from exc
        digest = hashlib.sha256(payload).hexdigest()
        stored = self._store_payload(digest, payload, ".json")
        modification = Modification(
            asset_id=asset_id,
            kind="roster_identity_text",
            replacement_path=stored,
            replacement_sha256=digest,
            metadata=apf_roster_identity_patch.allocation_metadata(allocation),
        )
        self._set(asset_id, modification)
        return modification

    def roster_identity_value(self, asset_id: str) -> str:
        allocation = self._roster_identity_allocation(asset_id)
        modification = self._modifications.get(asset_id)
        if modification is None:
            return allocation.text
        if modification.kind != "roster_identity_text":
            raise SessionError(f"The active edit type is invalid for {asset_id}")
        try:
            return decode_text_payload(
                modification.replacement_path.read_bytes(), asset_id
            )
        except (OSError, ProjectError) as exc:
            raise SessionError(
                f"The active roster-name replacement is invalid: {exc}"
            ) from exc

    def _player_rating_body(self) -> bytes:
        """Load the exact private ROST body once for source-value/revert display."""

        if self._player_rating_source_body is None:
            try:
                body, _source = apf_roster.load_roster(self.source.index_0a)
                tables, _root = apf_roster.parse_root(body)
            except (
                OSError,
                apf_roster.RosterError,
            ) as exc:
                raise SessionError(
                    f"Could not read APF player base ratings: {exc}"
                ) from exc
            player_table = tables[0]
            if (
                len(body) != apf_roster.EXPECTED_LENGTH
                or player_table.offset != apf_roster.ROOT_SIZE
                or player_table.count != apf_player_rating_patch.EXPECTED_PLAYER_COUNT
                or player_table.stride != apf_roster.PLAYER_STRIDE
            ):
                raise SessionError("The APF player-rating source layout changed")
            self._player_rating_source_body = body
        return self._player_rating_source_body

    def _load_custom_team_appearances(self) -> None:
        if self._custom_team_appearances is not None:
            return
        try:
            rows = apf_custom_team_appearance_patch.inspect_appearances(
                self.source.index_0a
            )
        except apf_custom_team_appearance_patch.CustomTeamAppearanceError as exc:
            raise SessionError(str(exc)) from exc
        self._custom_team_appearance_targets = {
            target.slot: target for target, _appearance in rows
        }
        self._custom_team_appearances = {
            appearance.slot: appearance for _target, appearance in rows
        }

    def custom_team_appearance_source_value(
        self, slot: int
    ) -> apf_custom_team_appearance_patch.CustomTeamAppearance:
        self._load_custom_team_appearances()
        assert self._custom_team_appearances is not None
        try:
            return self._custom_team_appearances[slot]
        except KeyError as exc:
            raise SessionError(
                "APF custom-team appearance slot must be an integer from 32 to 39"
            ) from exc

    def custom_team_appearance_value(
        self, slot: int
    ) -> apf_custom_team_appearance_patch.CustomTeamAppearance:
        source = self.custom_team_appearance_source_value(slot)
        target_id = apf_custom_team_appearance_patch.asset_id(slot)
        modification = self._modifications.get(target_id)
        if modification is None:
            return source
        if modification.kind != "custom_team_appearance":
            raise SessionError(f"The active edit type is invalid for {target_id}")
        try:
            return apf_custom_team_appearance_patch.decode_replacement_payload(
                modification.replacement_path.read_bytes(), target_id
            )
        except (
            OSError,
            apf_custom_team_appearance_patch.CustomTeamAppearanceError,
        ) as exc:
            raise SessionError(
                f"The active custom-team appearance replacement is invalid: {exc}"
            ) from exc

    def replace_custom_team_appearance(
        self,
        appearance: apf_custom_team_appearance_patch.CustomTeamAppearance,
    ) -> Modification:
        try:
            appearance = apf_custom_team_appearance_patch.validate_appearance(
                appearance
            )
            self.custom_team_appearance_source_value(appearance.slot)
            assert self._custom_team_appearance_targets is not None
            target = self._custom_team_appearance_targets[appearance.slot]
            payload = apf_custom_team_appearance_patch.encode_replacement_payload(
                appearance
            )
        except apf_custom_team_appearance_patch.CustomTeamAppearanceError as exc:
            raise SessionError(str(exc)) from exc
        digest = hashlib.sha256(payload).hexdigest()
        stored = self._store_payload(digest, payload, ".json")
        modification = Modification(
            asset_id=target.asset_id,
            kind="custom_team_appearance",
            replacement_path=stored,
            replacement_sha256=digest,
            metadata=apf_custom_team_appearance_patch.target_metadata(target),
        )
        self._set(modification.asset_id, modification)
        return modification

    def _load_uniform_equipment_colors(self) -> None:
        if self._uniform_equipment_color_inspections is not None:
            return
        try:
            rows = apf_uniform_equipment_color_patch.inspect_colors(
                self.source.index_0a
            )
        except apf_uniform_equipment_color_patch.UniformEquipmentColorError as exc:
            raise SessionError(str(exc)) from exc
        self._uniform_equipment_color_inspections = {
            row.target.team_index: row for row in rows
        }

    def uniform_equipment_color_inspection(
        self, team_index: int
    ) -> apf_uniform_equipment_color_patch.UniformEquipmentColorInspection:
        try:
            apf_uniform_equipment_color_patch.asset_id(team_index)
        except apf_uniform_equipment_color_patch.UniformEquipmentColorError as exc:
            raise SessionError(str(exc)) from exc
        self._load_uniform_equipment_colors()
        assert self._uniform_equipment_color_inspections is not None
        try:
            return self._uniform_equipment_color_inspections[team_index]
        except KeyError as exc:
            raise SessionError("APF team index must be an integer from 0 to 39") from exc

    def uniform_equipment_color_source_value(
        self, team_index: int
    ) -> apf_uniform_equipment_color_patch.UniformEquipmentColors:
        return self.uniform_equipment_color_inspection(team_index).value

    def uniform_equipment_color_value(
        self, team_index: int
    ) -> apf_uniform_equipment_color_patch.UniformEquipmentColors:
        source = self.uniform_equipment_color_source_value(team_index)
        target_id = apf_uniform_equipment_color_patch.asset_id(team_index)
        modification = self._modifications.get(target_id)
        if modification is None:
            return source
        if modification.kind != "uniform_equipment_colors":
            raise SessionError(f"The active edit type is invalid for {target_id}")
        try:
            return apf_uniform_equipment_color_patch.decode_replacement_payload(
                modification.replacement_path.read_bytes(), target_id
            )
        except (
            OSError,
            apf_uniform_equipment_color_patch.UniformEquipmentColorError,
        ) as exc:
            raise SessionError(
                f"The active uniform equipment-color replacement is invalid: {exc}"
            ) from exc

    def replace_uniform_equipment_colors(
        self,
        value: apf_uniform_equipment_color_patch.UniformEquipmentColors,
    ) -> Modification:
        try:
            value = apf_uniform_equipment_color_patch.validate_colors(value)
            inspection = self.uniform_equipment_color_inspection(value.team_index)
            payload = apf_uniform_equipment_color_patch.encode_replacement_payload(value)
        except apf_uniform_equipment_color_patch.UniformEquipmentColorError as exc:
            raise SessionError(str(exc)) from exc
        digest = hashlib.sha256(payload).hexdigest()
        stored = self._store_payload(digest, payload, ".json")
        modification = Modification(
            asset_id=inspection.target.asset_id,
            kind="uniform_equipment_colors",
            replacement_path=stored,
            replacement_sha256=digest,
            metadata=apf_uniform_equipment_color_patch.target_metadata(
                inspection.target
            ),
        )
        self._set(modification.asset_id, modification)
        return modification

    def _master_play_body(self) -> bytes:
        if self._master_play_source_body is None:
            try:
                self._master_play_source_body = read_master_play_body(
                    self.source.index_0a
                )
            except ValidationError as exc:
                raise SessionError(str(exc)) from exc
        return self._master_play_source_body

    @staticmethod
    def _route_request_metadata(request: RouteCloneRequest) -> dict[str, object]:
        return {
            "asset_id": request.asset_id,
            "target_play_index": request.target_play_index,
            "target_slot_index": request.target_slot_index,
            "donor_play_index": request.donor_play_index,
            "donor_slot_index": request.donor_slot_index,
        }

    def _active_route_requests(
        self, modifications: Mapping[str, Modification] | None = None
    ) -> tuple[RouteCloneRequest, ...]:
        source = self._modifications if modifications is None else modifications
        result: list[RouteCloneRequest] = []
        for modification in source.values():
            if modification.kind != PLAY_ASSIGNMENT_ROUTE_KIND:
                continue
            try:
                payload = modification.replacement_path.read_bytes()
                request = decode_route_clone_payload(
                    payload, modification.asset_id
                )
                metadata_request = route_clone_request_from_mapping(
                    modification.metadata
                )
            except (OSError, ValidationError) as exc:
                raise SessionError(
                    f"The active APF route clone is invalid: {exc}"
                ) from exc
            if request != metadata_request:
                raise SessionError(
                    f"APF route-clone target metadata changed: {modification.asset_id}"
                )
            result.append(request)
        return tuple(sorted(result, key=lambda item: item.selector))

    def apply_play_assignment_route_batch(
        self,
        requests: Iterable[RouteCloneRequest],
        *,
        revert_asset_ids: Iterable[str] = (),
    ) -> int:
        """Stage route copies atomically so a two-way swap is one Undo action."""

        normalized = tuple(requests)
        revert_ids = tuple(dict.fromkeys(str(value) for value in revert_asset_ids))
        if not normalized and not revert_ids:
            return 0
        prepared: list[Modification] = []
        seen: set[str] = set()
        for request in normalized:
            if not isinstance(request, RouteCloneRequest):
                raise SessionError("An APF route-copy request is malformed")
            try:
                payload = encode_route_clone_payload(request)
            except ValidationError as exc:
                raise SessionError(str(exc)) from exc
            if request.selector in seen:
                raise SessionError(
                    "An APF route-copy batch repeats one target assignment slot"
                )
            seen.add(request.selector)
            digest = hashlib.sha256(payload).hexdigest()
            stored = self._store_payload(digest, payload, ".json")
            prepared.append(
                Modification(
                    asset_id=request.selector,
                    kind=PLAY_ASSIGNMENT_ROUTE_KIND,
                    replacement_path=stored,
                    replacement_sha256=digest,
                    metadata=self._route_request_metadata(request),
                )
            )
        overlap = seen.intersection(revert_ids)
        if overlap:
            raise SessionError(
                "A route-copy batch cannot replace and revert the same target"
            )
        updated = dict(self._modifications)
        for asset_id in revert_ids:
            existing = updated.get(asset_id)
            if existing is not None and existing.kind != PLAY_ASSIGNMENT_ROUTE_KIND:
                raise SessionError(
                    f"The active edit type is invalid for route target {asset_id}"
                )
            updated.pop(asset_id, None)
        for modification in prepared:
            updated[modification.asset_id] = modification
        try:
            active = self._active_route_requests(updated)
            if active:
                compile_route_clones(self._master_play_body(), active)
        except ValidationError as exc:
            raise SessionError(str(exc)) from exc
        if updated == self._modifications:
            return 0
        changed = {
            key
            for key in set(updated).union(self._modifications)
            if updated.get(key) != self._modifications.get(key)
        }
        self._record_undo()
        self._modifications = updated
        return len(changed)

    def replace_play_assignment_route(
        self,
        target_play_index: int,
        target_slot_index: int,
        donor_play_index: int,
        donor_slot_index: int,
    ) -> Modification:
        """Copy one stock assignment when it preserves every chain start."""

        request = RouteCloneRequest(
            target_play_index,
            target_slot_index,
            donor_play_index,
            donor_slot_index,
        )
        self.apply_play_assignment_route_batch((request,))
        modification = self._modifications.get(request.selector)
        if modification is None:
            raise SessionError("The APF route copy was not staged")
        return modification

    def swap_play_assignment_routes(
        self,
        first_play_index: int,
        first_slot_index: int,
        second_play_index: int,
        second_slot_index: int,
    ) -> tuple[Modification, Modification]:
        """Safely swap two source assignments while preserving the chain set."""

        first = RouteCloneRequest(
            first_play_index,
            first_slot_index,
            second_play_index,
            second_slot_index,
        )
        second = RouteCloneRequest(
            second_play_index,
            second_slot_index,
            first_play_index,
            first_slot_index,
        )
        self.apply_play_assignment_route_batch((first, second))
        return (
            self._modifications[first.selector],
            self._modifications[second.selector],
        )

    # ------------------------------------------------ stock playbook membership

    def _active_splb_changes(
        self, modifications: Mapping[str, Modification] | None = None
    ) -> tuple[SplbMembershipChange | SplbTagMove, ...]:
        """Every staged Fine-tune Plays edit, re-read from its stored payload."""

        source = self._modifications if modifications is None else modifications
        result: list[SplbMembershipChange | SplbTagMove] = []
        for modification in source.values():
            if modification.kind != SPLB_MEMBERSHIP_KIND:
                continue
            try:
                change = decode_splb_membership_payload(
                    modification.replacement_path.read_bytes(),
                    modification.asset_id,
                )
                metadata_change = splb_change_from_mapping(modification.metadata)
            except (OSError, ValidationError) as exc:
                raise SessionError(
                    f"The active stock-playbook edit is invalid: {exc}"
                ) from exc
            if change != metadata_change:
                raise SessionError(
                    "Stock-playbook edit target metadata changed: "
                    f"{modification.asset_id}"
                )
            result.append(change)
        return tuple(sorted(result, key=lambda item: item.selector))

    def staged_splb_outers(self) -> tuple[int, ...]:
        """Every stock playbook that currently has Fine-tune Plays edits."""

        return tuple(
            sorted({change.outer_index for change in self._active_splb_changes()})
        )

    def staged_splb_book(self) -> int | None:
        """The only staged stock playbook, or None if none or more than one."""

        outers = self.staged_splb_outers()
        if len(outers) == 1:
            return outers[0]
        return None

    def staged_splb_changes(self) -> tuple[SplbMembershipChange | SplbTagMove, ...]:
        return self._active_splb_changes()

    def _compile_splb_groups(
        self, active: Iterable[SplbMembershipChange | SplbTagMove]
    ) -> None:
        """Compile each named book separately. The writer is still one book."""

        groups: dict[int, list[SplbMembershipChange | SplbTagMove]] = {}
        for change in active:
            groups.setdefault(change.outer_index, []).append(change)
        for outer_index, group in sorted(groups.items()):
            compile_splb_book(
                read_splb_book(self.source.index_0a, outer_index), tuple(group)
            )

    def apply_splb_membership_batch(
        self,
        changes: Iterable[SplbMembershipChange | SplbTagMove],
        *,
        replace_outer: int | None = None,
    ) -> int:
        """Merge Fine-tune Plays edits for one book, keeping every other book.

        One call still names one stock playbook — the writer compiles one book
        at a time. ``replace_outer`` is the book whose previous ticks are
        replaced. An empty batch with ``replace_outer=None`` clears every book
        (Revert-all). An empty batch with ``replace_outer=N`` clears only N.
        """

        normalized = tuple(changes)
        prepared: list[Modification] = []
        seen: set[str] = set()
        outers: set[int] = set()
        for change in normalized:
            if not isinstance(change, (SplbMembershipChange, SplbTagMove)):
                raise SessionError("A stock-playbook change is malformed")
            try:
                payload = encode_splb_membership_payload(change)
            except ValidationError as exc:
                raise SessionError(str(exc)) from exc
            if change.selector in seen:
                raise SessionError(
                    "A stock-playbook batch repeats one formation slot"
                )
            seen.add(change.selector)
            outers.add(change.outer_index)
            digest = hashlib.sha256(payload).hexdigest()
            stored = self._store_payload(digest, payload, ".json")
            prepared.append(
                Modification(
                    asset_id=change.selector,
                    kind=SPLB_MEMBERSHIP_KIND,
                    replacement_path=stored,
                    replacement_sha256=digest,
                    metadata=splb_change_metadata(change),
                )
            )
        if len(outers) > 1:
            raise SessionError(
                "A Fine-tune Plays batch must name one stock playbook"
            )
        if normalized:
            batch_outer = next(iter(outers))
            if replace_outer is None:
                replace_outer = batch_outer
            elif replace_outer != batch_outer:
                raise SessionError(
                    "replace_outer does not match the Fine-tune Plays batch"
                )
        updated: dict[str, Modification] = {}
        for asset_id, modification in self._modifications.items():
            if modification.kind != SPLB_MEMBERSHIP_KIND:
                updated[asset_id] = modification
                continue
            if replace_outer is None:
                continue
            try:
                existing = splb_change_from_mapping(modification.metadata)
            except ValidationError:
                existing = decode_splb_membership_payload(
                    modification.replacement_path.read_bytes(),
                    modification.asset_id,
                )
            if existing.outer_index == replace_outer:
                continue
            updated[asset_id] = modification
        for modification in prepared:
            updated[modification.asset_id] = modification
        active = self._active_splb_changes(updated)
        if active:
            try:
                self._compile_splb_groups(active)
            except ValidationError as exc:
                raise SessionError(str(exc)) from exc
        if updated == self._modifications:
            return 0
        changed = {
            key
            for key in set(updated).union(self._modifications)
            if updated.get(key) != self._modifications.get(key)
        }
        self._record_undo()
        self._modifications = updated
        return len(changed)

    def clear_splb_membership(self) -> int:
        """Drop every staged Fine-tune Plays edit as one Undo action."""

        return self.apply_splb_membership_batch(())

    def player_base_rating_value(self, player_index: int, field_id: str) -> int:
        """Return the active authored value or the untouched on-disc integer."""

        try:
            target = apf_player_rating_patch.target_for(player_index, field_id)
        except apf_player_rating_patch.PlayerRatingPatchError as exc:
            raise SessionError(str(exc)) from exc
        modification = self._modifications.get(target.asset_id)
        if modification is not None:
            if modification.kind != "player_base_rating":
                raise SessionError(
                    f"The active edit type is invalid for {target.asset_id}"
                )
            try:
                return apf_player_rating_patch.decode_replacement_payload(
                    modification.replacement_path.read_bytes(), target.asset_id
                )
            except (
                OSError,
                apf_player_rating_patch.PlayerRatingPatchError,
            ) as exc:
                raise SessionError(
                    f"The active player-rating replacement is invalid: {exc}"
                ) from exc
        return self.player_base_rating_source_value(player_index, field_id)

    def player_base_rating_source_value(
        self, player_index: int, field_id: str
    ) -> int:
        """Return the untouched native 0..100 byte from the loaded source."""

        try:
            target = apf_player_rating_patch.target_for(player_index, field_id)
        except apf_player_rating_patch.PlayerRatingPatchError as exc:
            raise SessionError(str(exc)) from exc
        body = self._player_rating_body()
        absolute = (
            apf_roster.ROOT_SIZE
            + target.player_index * apf_roster.PLAYER_STRIDE
            + target.record_relative_offset
        )
        value = int(body[absolute])
        if not 0 <= value <= 100:
            raise SessionError(
                f"The source value for {target.asset_id} is outside its native byte contract"
            )
        return value

    def player_rating_edit_fingerprint(self) -> str:
        """Bind a ratings-sheet preview to the exact active semantic edit set."""

        rows: list[tuple[str, str]] = []
        for asset_id, modification in sorted(self._modifications.items()):
            if modification.kind == "player_base_rating":
                rows.append((asset_id, modification.replacement_sha256))
        payload = repr(tuple(rows)).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _prepare_player_base_rating_modification(
        self,
        player_index: int,
        field_id: str,
        value: int,
    ) -> Modification:
        """Validate and cache one authored value without changing session state."""

        try:
            target = apf_player_rating_patch.target_for(player_index, field_id)
            rating = apf_player_rating_patch.validate_field_value(
                target.field_id, value
            )
            self.player_base_rating_source_value(
                target.player_index, target.field_id
            )
            payload = apf_player_rating_patch.encode_replacement_payload(rating)
        except apf_player_rating_patch.PlayerRatingPatchError as exc:
            raise SessionError(str(exc)) from exc
        digest = hashlib.sha256(payload).hexdigest()
        stored = self._store_payload(digest, payload, ".json")
        return Modification(
            asset_id=target.asset_id,
            kind="player_base_rating",
            replacement_path=stored,
            replacement_sha256=digest,
            metadata=apf_player_rating_patch.target_metadata(target),
        )

    def replace_player_base_rating(
        self,
        player_index: int,
        field_id: str,
        value: int,
    ) -> Modification:
        """Stage one strict 0..99 rating as canonical replacement-only JSON."""

        modification = self._prepare_player_base_rating_modification(
            player_index, field_id, value
        )
        self._set(modification.asset_id, modification)
        return modification

    def apply_player_base_rating_batch(
        self,
        replacements: Mapping[tuple[int, str], int],
        *,
        revert_targets: Iterable[tuple[int, str]] = (),
    ) -> int:
        """Prepare and commit a complete ratings import as one Undo action."""

        replacement_items = tuple(replacements.items())
        revert_items = tuple(dict.fromkeys(revert_targets))
        replacement_keys = set(replacements)
        overlap = replacement_keys.intersection(revert_items)
        if overlap:
            player_index, field_id = sorted(overlap)[0]
            raise SessionError(
                "A rating batch cannot replace and revert the same cell: "
                f"player {player_index} {field_id}"
            )
        prepared: list[Modification] = []
        for key, value in replacement_items:
            if (
                not isinstance(key, tuple)
                or len(key) != 2
                or type(key[0]) is not int
                or not isinstance(key[1], str)
            ):
                raise SessionError("A rating batch target is malformed")
            prepared.append(
                self._prepare_player_base_rating_modification(
                    key[0], key[1], value
                )
            )
        revert_asset_ids: list[str] = []
        for key in revert_items:
            if (
                not isinstance(key, tuple)
                or len(key) != 2
                or type(key[0]) is not int
                or not isinstance(key[1], str)
            ):
                raise SessionError("A rating batch revert target is malformed")
            try:
                target = apf_player_rating_patch.target_for(key[0], key[1])
            except apf_player_rating_patch.PlayerRatingPatchError as exc:
                raise SessionError(str(exc)) from exc
            self.player_base_rating_source_value(
                target.player_index, target.field_id
            )
            active = self._modifications.get(target.asset_id)
            if active is not None and active.kind != "player_base_rating":
                raise SessionError(
                    f"The active edit type is invalid for {target.asset_id}"
                )
            revert_asset_ids.append(target.asset_id)

        updated = dict(self._modifications)
        for asset_id in revert_asset_ids:
            updated.pop(asset_id, None)
        for modification in prepared:
            updated[modification.asset_id] = modification
        if updated == self._modifications:
            return 0
        changed_ids = {
            asset_id
            for asset_id in set(self._modifications).union(updated)
            if self._modifications.get(asset_id) != updated.get(asset_id)
        }
        self._record_undo()
        self._modifications = updated
        return len(changed_ids)

    def player_position_value(self, player_index: int) -> int:
        """Return the active authored position code or untouched source code."""

        try:
            target = apf_player_position_patch.target_for(player_index)
        except apf_player_position_patch.PlayerPositionPatchError as exc:
            raise SessionError(str(exc)) from exc
        modification = self._modifications.get(target.asset_id)
        if modification is not None:
            if modification.kind != "player_position":
                raise SessionError(
                    f"The active edit type is invalid for {target.asset_id}"
                )
            try:
                return apf_player_position_patch.decode_replacement_payload(
                    modification.replacement_path.read_bytes(), target.asset_id
                )
            except (
                OSError,
                apf_player_position_patch.PlayerPositionPatchError,
            ) as exc:
                raise SessionError(
                    f"The active player-position replacement is invalid: {exc}"
                ) from exc
        return self.player_position_source_value(player_index)

    def player_position_source_value(self, player_index: int) -> int:
        """Return and validate the untouched semantic/mirror position pair."""

        try:
            target = apf_player_position_patch.target_for(player_index)
        except apf_player_position_patch.PlayerPositionPatchError as exc:
            raise SessionError(str(exc)) from exc
        body = self._player_rating_body()
        record_start = (
            apf_roster.ROOT_SIZE
            + target.player_index * apf_roster.PLAYER_STRIDE
        )
        try:
            position = apf_roster.PLAYER_POSITION_SCHEMA.decode_record(
                body[record_start : record_start + apf_roster.PLAYER_STRIDE]
            )
        except PlayerPositionsError as exc:
            raise SessionError(
                f"The source value for {target.asset_id} violates its mirror contract: {exc}"
            ) from exc
        return position.code

    def replace_player_position(
        self, player_index: int, value: int
    ) -> Modification:
        """Stage one exact 0..16 position code as replacement-only JSON."""

        try:
            target = apf_player_position_patch.target_for(player_index)
            code = apf_player_position_patch.validate_code(value)
            self.player_position_source_value(target.player_index)
            payload = apf_player_position_patch.encode_replacement_payload(code)
        except apf_player_position_patch.PlayerPositionPatchError as exc:
            raise SessionError(str(exc)) from exc
        digest = hashlib.sha256(payload).hexdigest()
        stored = self._store_payload(digest, payload, ".json")
        modification = Modification(
            asset_id=target.asset_id,
            kind="player_position",
            replacement_path=stored,
            replacement_sha256=digest,
            metadata=apf_player_position_patch.target_metadata(target),
        )
        self._set(modification.asset_id, modification)
        return modification

    def revert(self, asset_id: str) -> bool:
        previous = self._modifications.get(asset_id)
        if previous is None:
            return False
        if previous.kind == PLAY_ASSIGNMENT_ROUTE_KIND:
            updated = dict(self._modifications)
            updated.pop(asset_id)

            def route_set_is_safe(candidate: Mapping[str, Modification]) -> bool:
                requests = self._active_route_requests(candidate)
                if not requests:
                    return True
                try:
                    compile_route_clones(self._master_play_body(), requests)
                except ValidationError:
                    return False
                return True

            if not route_set_is_safe(updated):
                try:
                    selected = decode_route_clone_payload(
                        previous.replacement_path.read_bytes(), previous.asset_id
                    )
                except (OSError, ValidationError) as exc:
                    raise SessionError(
                        f"The active APF route clone is invalid: {exc}"
                    ) from exc
                reciprocal = RouteCloneRequest(
                    selected.donor_play_index,
                    selected.donor_slot_index,
                    selected.target_play_index,
                    selected.target_slot_index,
                )
                partner = updated.get(reciprocal.selector)
                if partner is None or partner.kind != PLAY_ASSIGNMENT_ROUTE_KIND:
                    raise SessionError(
                        "Reverting only this assignment would orphan a stock "
                        "chain, and no reciprocal swap partner is staged."
                    )
                try:
                    partner_request = decode_route_clone_payload(
                        partner.replacement_path.read_bytes(), partner.asset_id
                    )
                except (OSError, ValidationError) as exc:
                    raise SessionError(
                        f"The reciprocal APF route clone is invalid: {exc}"
                    ) from exc
                if partner_request != reciprocal:
                    raise SessionError(
                        "Reverting only this assignment would orphan a stock chain."
                    )
                updated.pop(reciprocal.selector)
                if not route_set_is_safe(updated):
                    raise SessionError(
                        "Reverting this assignment pair would leave the staged "
                        "route set unsafe. Revert all route edits together."
                    )
            self._record_undo()
            self._modifications = updated
            return True
        if previous.kind == SPLB_MEMBERSHIP_KIND:
            # One staged change can depend on another: a removal names an heir
            # that a staged add put in the record. Dropping one in isolation can
            # leave a set the writer would refuse, so prove the remainder still
            # compiles rather than discovering it at build time.
            updated = dict(self._modifications)
            updated.pop(asset_id)
            active = self._active_splb_changes(updated)
            if active:
                try:
                    self._compile_splb_groups(active)
                except ValidationError as exc:
                    raise SessionError(
                        "Reverting only this Fine-tune Plays edit would leave the "
                        f"rest outside the proved rule ({exc}). Use Revert changes "
                        "in Fine-tune Plays to drop them together."
                    ) from exc
            self._record_undo()
            self._modifications = updated
            return True
        self._record_undo()
        del self._modifications[asset_id]
        return True

    def revert_all(self) -> int:
        count = self.project_change_count
        if count:
            self._record_undo()
            self._modifications.clear()
            self._audio_annotations.clear()
        return count

    def undo(self) -> bool:
        if not self._undo:
            return False
        snapshot = self._undo.pop()
        self._modifications = dict(snapshot.modifications)
        self._audio_annotations = dict(snapshot.audio_annotations)
        return True

    def save_project(
        self,
        destination: Path,
        *,
        title: str = "APF 2K8 Mod Project",
        replace: bool = False,
        expected_target: ProjectTargetIdentity | None = None,
    ) -> Path:
        protected_audio_hashes: set[str] = set()
        if any(
            modification.kind == AUDO_EXACT_SLOT_KIND
            for modification in self.modifications
        ):
            protected_audio_hashes.update(self._protected_audo_payload_hashes())
        if any(
            modification.kind == AUSB_EXACT_SLOT_KIND
            for modification in self.modifications
        ):
            protected_audio_hashes.update(self._protected_ausb_payload_hashes())
        return write_project_archive(
            destination,
            source_sha256=self.source.source_sha256,
            modifications=self.modifications,
            title=title,
            replace=replace,
            expected_target=expected_target,
            protected_replacement_hashes=protected_audio_hashes,
            audio_annotations=self.audio_annotations,
        )

    def load_project(self, source: Path) -> int:
        incoming = self.working_root / f"import-{uuid4().hex}"
        try:
            manifest, modifications, annotations = read_project_archive(
                source,
                expected_source_sha256=self.source.source_sha256,
                destination_dir=incoming,
            )
            del manifest
            validated: list[Modification] = []
            for modification in modifications:
                suffix = ".png"
                if (
                    modification.kind == HELMET_CREST_DESIGN_KIND
                    and modification.asset_id == HELMET_CREST_DESIGN_EDIT_ID
                ):
                    data, digest = self._validated_png(
                        modification.replacement_path,
                        width=512,
                        height=512,
                        contract="helmet_crest_design",
                    )
                    try:
                        target_metadata = validate_helmet_crest_metadata(
                            modification.asset_id,
                            modification.kind,
                            modification.metadata,
                        )
                    except HelmetCrestDesignError as exc:
                        raise SessionError(str(exc)) from exc
                    self._require_helmet_crest_slot(
                        int(target_metadata["crest_asset_index"]),
                        int(target_metadata["crest_outer_entry_index"]),
                    )
                    with Image.open(BytesIO(data)) as image:
                        image.load()
                        rgba = image.tobytes()
                    if not any(rgba[index] for index in range(3, len(rgba), 4)):
                        raise SessionError(
                            "Project helmet crest PNG is fully transparent"
                        )
                    if not any(
                        rgba[offset] or rgba[offset + 1] or rgba[offset + 2]
                        for offset in range(0, len(rgba), 4)
                    ):
                        raise SessionError(
                            "Project helmet crest has no visible RGB mask regions"
                        )
                    active_x = [
                        (offset // 4) % 512
                        for offset in range(0, len(rgba), 4)
                        if rgba[offset] or rgba[offset + 1] or rgba[offset + 2]
                    ]
                    actual_coverage = (max(active_x) - min(active_x) + 1) / 512
                    if actual_coverage != float(
                        target_metadata["output_horizontal_coverage"]
                    ):
                        raise SessionError(
                            "Project helmet crest mask coverage does not match its "
                            "payload"
                        )
                    if target_metadata["fit_visible_mask"] is True and (
                        min(active_x), max(active_x)
                    ) != (0, 511):
                        raise SessionError(
                            "Project fitted helmet crest does not span the full "
                            "horizontal range"
                        )
                    if target_metadata["profile"] == FULL_SHELL_CREST_PROFILE:
                        try:
                            validate_region_mask_rgba(rgba)
                        except HelmetLogoRegionError as exc:
                            raise SessionError(
                                "Project full-shell helmet crest is not a semantic "
                                f"APF region mask: {exc}"
                            ) from exc
                elif modification.kind == "uniform":
                    asset = self.catalog.uniform(modification.asset_id)
                    data, digest = self._validated_png(
                        modification.replacement_path,
                        width=asset.width,
                        height=asset.height,
                        contract=asset.family,
                    )
                    metadata = modification.metadata
                    if (
                        metadata.get("family") != asset.family
                        or metadata.get("asset_index") != asset.asset_index
                        or metadata.get("outer_index") != asset.outer_index
                        or metadata.get("inner_index") != asset.inner_index
                    ):
                        raise SessionError(
                            f"Project target metadata changed: {asset.asset_id}"
                        )
                elif (
                    modification.kind == "digital_font"
                    and modification.asset_id == "apf:presentation:digital_font"
                ):
                    data, digest = self._validated_png(
                        modification.replacement_path,
                        width=128,
                        height=128,
                        contract="digital_font",
                    )
                elif (
                    modification.kind == "draft_logo"
                    and modification.asset_id == DRAFT_LOGO_EDIT_ID
                ):
                    item = self.catalog.get(DRAFT_LOGO_CATALOG_ID)
                    if (
                        item.outer_index != DRAFT_LOGO_OUTER_INDEX
                        or item.inner_index != DRAFT_LOGO_INNER_INDEX
                        or item.name != "draft_logo"
                        or item.type_name != "TXTR"
                        or item.status is not ApfStatus.EDITABLE
                    ):
                        raise SessionError(
                            "The project draft_logo target changed in this game"
                        )
                    self.asset_io.preview_texture(item)
                    data, digest = self._validated_png(
                        modification.replacement_path,
                        width=128,
                        height=128,
                        contract="draft_logo",
                    )
                    fixed_metadata = {
                        "width": 128,
                        "height": 128,
                        "outer_index": DRAFT_LOGO_OUTER_INDEX,
                        "inner_index": DRAFT_LOGO_INNER_INDEX,
                        "format": "BC3",
                        "mip_levels": 1,
                    }
                    if any(
                        modification.metadata.get(key) != value
                        for key, value in fixed_metadata.items()
                    ):
                        raise SessionError(
                            "Project target metadata changed: draft_logo"
                        )
                elif modification.kind == "localization_text":
                    allocation = self._localization_allocation(
                        modification.asset_id
                    )
                    try:
                        data = modification.replacement_path.read_bytes()
                        value = decode_text_payload(data, modification.asset_id)
                        apf_txt_loc_patch.validate_replacement(allocation, value)
                    except (
                        OSError,
                        ProjectError,
                        apf_txt_loc_patch.TextPatchError,
                    ) as exc:
                        raise SessionError(
                            f"Project text replacement is invalid: {exc}"
                        ) from exc
                    digest = hashlib.sha256(data).hexdigest()
                    if modification.metadata != self._localization_metadata(
                        allocation
                    ):
                        raise SessionError(
                            "Project text allocation changed: "
                            f"{modification.asset_id}"
                        )
                    suffix = ".json"
                elif modification.kind == "roster_identity_text":
                    allocation = self._roster_identity_allocation(
                        modification.asset_id
                    )
                    if not self.roster_identity_is_product_editable(
                        modification.asset_id
                    ):
                        raise SessionError(
                            "This project contains a roster field that is still "
                            "runtime-locked. Only team display names and player "
                            "first/last names can be imported."
                        )
                    try:
                        data = modification.replacement_path.read_bytes()
                        value = decode_text_payload(data, modification.asset_id)
                        apf_roster_identity_patch.validate_replacement(
                            allocation, value
                        )
                    except (
                        OSError,
                        ProjectError,
                        apf_roster_identity_patch.RosterIdentityError,
                    ) as exc:
                        raise SessionError(
                            f"Project roster-name replacement is invalid: {exc}"
                        ) from exc
                    digest = hashlib.sha256(data).hexdigest()
                    if modification.metadata != (
                        apf_roster_identity_patch.allocation_metadata(allocation)
                    ):
                        raise SessionError(
                            "Project roster-name allocation changed: "
                            f"{modification.asset_id}"
                        )
                    suffix = ".json"
                elif modification.kind == PLAY_ASSIGNMENT_ROUTE_KIND:
                    try:
                        data = modification.replacement_path.read_bytes()
                        request = decode_route_clone_payload(
                            data, modification.asset_id
                        )
                        metadata_request = route_clone_request_from_mapping(
                            modification.metadata
                        )
                    except (OSError, ValidationError) as exc:
                        raise SessionError(
                            f"Project APF route clone is invalid: {exc}"
                        ) from exc
                    if request != metadata_request:
                        raise SessionError(
                            "Project APF route-clone target metadata changed: "
                            f"{modification.asset_id}"
                        )
                    digest = hashlib.sha256(data).hexdigest()
                    suffix = ".json"
                elif modification.kind == SPLB_MEMBERSHIP_KIND:
                    try:
                        data = modification.replacement_path.read_bytes()
                        change = decode_splb_membership_payload(
                            data, modification.asset_id
                        )
                        metadata_change = splb_change_from_mapping(
                            modification.metadata
                        )
                    except (OSError, ValidationError) as exc:
                        raise SessionError(
                            f"Project stock-playbook edit is invalid: {exc}"
                        ) from exc
                    if change != metadata_change:
                        raise SessionError(
                            "Project stock-playbook target metadata changed: "
                            f"{modification.asset_id}"
                        )
                    digest = hashlib.sha256(data).hexdigest()
                    suffix = ".json"
                elif modification.kind == AUDO_EXACT_SLOT_KIND:
                    fields = modification.asset_id.split(":")
                    try:
                        if (
                            len(fields) != 5
                            or fields[:3] != ["apf", "audio", "audo"]
                        ):
                            raise ValueError
                        outer_index = int(fields[3])
                        inner_index = int(fields[4])
                    except ValueError as exc:
                        raise SessionError(
                            "Project standalone-audio target is malformed: "
                            f"{modification.asset_id}"
                        ) from exc
                    identity = ExportIdentity(
                        "audo",
                        outer_index,
                        inner_index,
                        None,
                        f"audo-{outer_index}-{inner_index}",
                    )
                    resolved = self._resolve_audo_identity(identity)
                    if modification.metadata != self._audo_metadata(resolved):
                        raise SessionError(
                            "Project exact-slot audio target changed: "
                            f"{modification.asset_id}"
                        )
                    try:
                        data = modification.replacement_path.read_bytes()
                        result = (
                            apf_audo_exact_slot.validate_stored_payload_complete(
                                data,
                                resolved.target,
                                self._protected_audo_fingerprints(),
                            )
                        )
                    except (
                        OSError,
                        apf_audo_exact_slot.ExactSlotImportError,
                    ) as exc:
                        raise SessionError(
                            f"Project XMA1 replacement is invalid: {exc}"
                        ) from exc
                    digest = hashlib.sha256(result.payload).hexdigest()
                    self._reject_any_source_audio_reuse(result.payload)
                    if result.payload != data:
                        raise SessionError(
                            "Project XMA1 validation changed the stored packets"
                        )
                    if digest in self._protected_audo_payload_hashes():
                        raise SessionError(
                            "A project XMA1 replacement matches audio from the "
                            "loaded retail game and cannot be imported."
                        )
                    suffix = ".xma1-packets"
                elif modification.kind == AUSB_EXACT_SLOT_KIND:
                    fields = modification.asset_id.split(":")
                    try:
                        if (
                            len(fields) != 6
                            or fields[:3] != ["apf", "audio", "ausb"]
                        ):
                            raise ValueError
                        outer_index = int(fields[3])
                        inner_index = int(fields[4])
                        substream_index = int(fields[5])
                    except ValueError as exc:
                        raise SessionError(
                            "Project AUSB-audio target is malformed: "
                            f"{modification.asset_id}"
                        ) from exc
                    identity = ExportIdentity(
                        "ausb_substream",
                        outer_index,
                        inner_index,
                        substream_index,
                        f"ausb-{outer_index}-{inner_index}-{substream_index}",
                    )
                    resolved = self._resolve_ausb_identity(identity)
                    if modification.metadata != self._ausb_metadata(resolved):
                        raise SessionError(
                            "Project AUSB exact-slot target changed: "
                            f"{modification.asset_id}"
                        )
                    try:
                        data = modification.replacement_path.read_bytes()
                        result = (
                            apf_ausb_exact_slot.validate_stored_payload_complete(
                                data,
                                resolved,
                                self._protected_ausb_fingerprints(),
                            )
                        )
                    except (
                        OSError,
                        apf_ausb_exact_slot.AusbExactSlotError,
                    ) as exc:
                        raise SessionError(
                            f"Project AUSB XMA1 replacement is invalid: {exc}"
                        ) from exc
                    digest = hashlib.sha256(result.payload).hexdigest()
                    self._reject_any_source_audio_reuse(result.payload)
                    if result.payload != data:
                        raise SessionError(
                            "Project AUSB XMA1 validation changed the stored packets"
                        )
                    if digest in self._protected_ausb_payload_hashes():
                        raise SessionError(
                            "A project AUSB XMA1 replacement matches audio from the "
                            "loaded retail game and cannot be imported."
                        )
                    suffix = ".xma1-packets"
                elif modification.kind == "player_base_rating":
                    try:
                        target = apf_player_rating_patch.parse_asset_id(
                            modification.asset_id
                        )
                        data = modification.replacement_path.read_bytes()
                        apf_player_rating_patch.decode_replacement_payload(
                            data, modification.asset_id
                        )
                    except (
                        OSError,
                        apf_player_rating_patch.PlayerRatingPatchError,
                    ) as exc:
                        raise SessionError(
                            f"Project player-rating replacement is invalid: {exc}"
                        ) from exc
                    if modification.metadata != (
                        apf_player_rating_patch.target_metadata(target)
                    ):
                        raise SessionError(
                            "Project player-rating target changed: "
                            f"{modification.asset_id}"
                        )
                    # Resolve the exact private source coordinate as an import
                    # fence; projects never carry the source record or value.
                    self.player_base_rating_value(
                        target.player_index, target.field_id
                    )
                    digest = hashlib.sha256(data).hexdigest()
                    suffix = ".json"
                elif modification.kind == "player_position":
                    try:
                        target = apf_player_position_patch.parse_asset_id(
                            modification.asset_id
                        )
                        data = modification.replacement_path.read_bytes()
                        apf_player_position_patch.decode_replacement_payload(
                            data, modification.asset_id
                        )
                    except (
                        OSError,
                        apf_player_position_patch.PlayerPositionPatchError,
                    ) as exc:
                        raise SessionError(
                            f"Project player-position replacement is invalid: {exc}"
                        ) from exc
                    if modification.metadata != (
                        apf_player_position_patch.target_metadata(target)
                    ):
                        raise SessionError(
                            "Project player-position target changed: "
                            f"{modification.asset_id}"
                        )
                    self.player_position_source_value(target.player_index)
                    digest = hashlib.sha256(data).hexdigest()
                    suffix = ".json"
                elif modification.kind == "custom_team_appearance":
                    try:
                        slot = apf_custom_team_appearance_patch.parse_asset_id(
                            modification.asset_id
                        )
                        data = modification.replacement_path.read_bytes()
                        appearance = (
                            apf_custom_team_appearance_patch.decode_replacement_payload(
                                data, modification.asset_id
                            )
                        )
                        self.custom_team_appearance_source_value(slot)
                        assert self._custom_team_appearance_targets is not None
                        target = self._custom_team_appearance_targets[slot]
                    except (
                        OSError,
                        apf_custom_team_appearance_patch.CustomTeamAppearanceError,
                    ) as exc:
                        raise SessionError(
                            f"Project custom-team appearance replacement is invalid: {exc}"
                        ) from exc
                    if appearance.slot != slot or modification.metadata != (
                        apf_custom_team_appearance_patch.target_metadata(target)
                    ):
                        raise SessionError(
                            "Project custom-team appearance target changed: "
                            f"{modification.asset_id}"
                        )
                    digest = hashlib.sha256(data).hexdigest()
                    suffix = ".json"
                elif modification.kind == "uniform_equipment_colors":
                    try:
                        team_index = apf_uniform_equipment_color_patch.parse_asset_id(
                            modification.asset_id
                        )
                        data = modification.replacement_path.read_bytes()
                        value = apf_uniform_equipment_color_patch.decode_replacement_payload(
                            data, modification.asset_id
                        )
                        inspection = self.uniform_equipment_color_inspection(team_index)
                    except (
                        OSError,
                        apf_uniform_equipment_color_patch.UniformEquipmentColorError,
                    ) as exc:
                        raise SessionError(
                            f"Project uniform equipment-color replacement is invalid: {exc}"
                        ) from exc
                    if value.team_index != team_index or modification.metadata != (
                        apf_uniform_equipment_color_patch.target_metadata(
                            inspection.target
                        )
                    ):
                        raise SessionError(
                            "Project uniform equipment-color target changed: "
                            f"{modification.asset_id}"
                        )
                    digest = hashlib.sha256(data).hexdigest()
                    suffix = ".json"
                else:
                    raise SessionError(
                        "Project contains an unsupported editable target: "
                        f"{modification.asset_id}"
                    )
                if digest != modification.replacement_sha256:
                    raise SessionError(
                        f"Project replacement hash changed: {modification.asset_id}"
                    )
                stored = self._store_payload(digest, data, suffix)
                validated.append(
                    Modification(
                        asset_id=modification.asset_id,
                        kind=modification.kind,
                        replacement_path=stored,
                        replacement_sha256=digest,
                        metadata=modification.metadata,
                    )
                )
            route_modifications = {
                item.asset_id: item
                for item in validated
                if item.kind == PLAY_ASSIGNMENT_ROUTE_KIND
            }
            if route_modifications:
                try:
                    compile_route_clones(
                        self._master_play_body(),
                        self._active_route_requests(route_modifications),
                    )
                except ValidationError as exc:
                    raise SessionError(
                        f"Project APF route-clone set is unsafe: {exc}"
                    ) from exc
            splb_modifications = {
                item.asset_id: item
                for item in validated
                if item.kind == SPLB_MEMBERSHIP_KIND
            }
            if splb_modifications:
                active = self._active_splb_changes(splb_modifications)
                try:
                    self._compile_splb_groups(active)
                except ValidationError as exc:
                    raise SessionError(
                        f"Project stock-playbook edit set is unsafe: {exc}"
                    ) from exc
            self._record_undo()
            self._modifications = {item.asset_id: item for item in validated}
            self._audio_annotations = {
                annotation.cue_id: annotation for annotation in annotations
            }
            return len(validated)
        finally:
            # Failed imports must not accumulate unpacked user payloads in the
            # private session directory, and they never alter the active edit set.
            shutil.rmtree(incoming, ignore_errors=True)

    def close(self) -> None:
        shutil.rmtree(self.working_root, ignore_errors=True)

    def _set(self, asset_id: str, modification: Modification) -> None:
        self._record_undo()
        self._modifications[asset_id] = modification

    def _record_undo(self) -> None:
        self._undo.append(
            _SessionSnapshot(
                modifications=dict(self._modifications),
                audio_annotations=dict(self._audio_annotations),
            )
        )

    def _store_replacement(self, asset_id: str, digest: str, data: bytes) -> Path:
        del asset_id
        return self._store_payload(digest, data, ".png")

    def _store_payload(
        self, digest: str, data: bytes, suffix: str
    ) -> Path:
        if suffix not in {".png", ".json", ".xma1-packets"}:
            raise SessionError("Unsupported private replacement payload type")
        path = self.replacements_root / f"{digest}{suffix}"
        if path.exists():
            supplied = path.lstat()
            if (
                not stat.S_ISREG(supplied.st_mode)
                or stat.S_ISLNK(supplied.st_mode)
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            ):
                raise SessionError("The private replacement cache is inconsistent")
            return path
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{digest}.", suffix=".importing", dir=self.replacements_root
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, path)
            temporary.unlink()
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)
            raise
        return path

    @staticmethod
    def _read_bounded_regular(
        path: Path,
        *,
        maximum: int,
        label: str,
    ) -> bytes:
        """Read one stable user file without following links or racing changes."""

        path = path.expanduser()
        try:
            supplied = path.lstat()
        except OSError as exc:
            raise SessionError(f"Could not open {label}: {exc}") from exc
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or supplied.st_nlink != 1
        ):
            raise SessionError(
                f"The {label} must be one private regular file, not a link"
            )
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | _O_BINARY,
        )
        try:
            opened = os.fstat(descriptor)
            # ``supplied`` is an lstat and ``opened`` an os.fstat of the same
            # file: the one comparison here that crosses the two stat families,
            # which Windows cannot carry st_ctime across, so that field is
            # dropped there (platform_compat.change_time_identity) and kept on
            # POSIX.  The fd/fd re-check further down keeps it everywhere.
            if (
                (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_size,
                    opened.st_mtime_ns,
                    *platform_compat.change_time_identity(opened),
                    opened.st_nlink,
                )
                != (
                    supplied.st_dev,
                    supplied.st_ino,
                    supplied.st_size,
                    supplied.st_mtime_ns,
                    *platform_compat.change_time_identity(supplied),
                    supplied.st_nlink,
                )
                or opened.st_nlink != 1
                or not 0 < opened.st_size <= maximum
            ):
                raise SessionError(
                    f"The {label} changed or is larger than this slot allows"
                )
            chunks: list[bytes] = []
            total = 0
            while True:
                block = os.read(
                    descriptor,
                    min(1024 * 1024, maximum + 1 - total),
                )
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                if total > maximum:
                    raise SessionError(
                        f"The {label} grew larger than this slot allows"
                    )
            after = os.fstat(descriptor)
            # Both sides are os.fstat of this one descriptor, so the change time
            # is comparable on every platform and stays in the fingerprint --
            # this check keeps its metadata-only-change signal on Windows too.
            if (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
                after.st_nlink,
            ) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
                opened.st_nlink,
            ) or total != opened.st_size:
                raise SessionError(f"The {label} changed while it was read")
        finally:
            os.close(descriptor)
        return b"".join(chunks)

    @staticmethod
    def _validated_png(
        path: Path,
        *,
        width: int,
        height: int,
        contract: str,
    ) -> tuple[bytes, str]:
        path = path.expanduser()
        supplied = path.lstat()
        if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
            raise SessionError("Replacement must be a regular, non-symlink PNG")
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | _O_BINARY,
        )
        try:
            opened = os.fstat(descriptor)
            if opened.st_size > 24 * 1024 * 1024:
                raise SessionError("Replacement PNG is unexpectedly large")
            chunks: list[bytes] = []
            while block := os.read(descriptor, 1024 * 1024):
                chunks.append(block)
            after = os.fstat(descriptor)
            if (after.st_dev, after.st_ino, after.st_size) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
            ):
                raise SessionError("Replacement changed while it was being read")
        finally:
            os.close(descriptor)
        data = b"".join(chunks)
        try:
            with Image.open(BytesIO(data)) as image:
                image.load()
                if image.format != "PNG" or image.mode != "RGBA" or image.size != (
                    width,
                    height,
                ):
                    raise SessionError(
                        f"Expected an exact {width}x{height} RGBA PNG; received "
                        f"{image.size[0]}x{image.size[1]} {image.mode}."
                    )
                rgba = image.tobytes()
        except SessionError:
            raise
        except Exception as exc:
            raise SessionError(f"Could not read replacement PNG: {exc}") from exc
        if contract == "pants" and any(rgba[index] != 255 for index in range(3, len(rgba), 4)):
            raise SessionError("Pants PNG alpha must be 255 (fully opaque) everywhere")
        if contract == "textlogo" and any(
            rgba[index] != 255 for index in range(3, len(rgba), 4)
        ):
            raise SessionError(
                "Wordmark PNG alpha must be 255 everywhere; use the Logos → "
                "Wordmarks importer to flatten transparent art onto black."
            )
        if contract == "helmet":
            if any(rgba[index] != 0 for index in range(2, len(rgba), 4)):
                raise SessionError("Helmet PNG blue must be 0; only the R/G mask channels are stored")
            if any(rgba[index] != 255 for index in range(3, len(rgba), 4)):
                raise SessionError("Helmet PNG alpha must be 255 everywhere")
        if contract == "digital_font" and any(
            rgba[index] != 255 or rgba[index + 1] != 255 or rgba[index + 2] != 255
            for index in range(0, len(rgba), 4)
        ):
            raise SessionError("digital_font RGB must be solid white; draw only in alpha")
        return data, hashlib.sha256(data).hexdigest()
