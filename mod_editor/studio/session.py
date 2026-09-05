"""Private working session for 2K5 Mod Studio.

The session owns only user-supplied replacement PNGs and small JSON metadata.
Retail originals live in the separate, private source cache and are never
copied into a session or a shareable project.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Any, Callable, Iterable, Iterator
from uuid import UUID, uuid4

from mod_editor.core import platform_compat
from mod_editor.core.errors import ValidationError
from mod_editor.core.json_stream import read_bounded_regular_file
from mod_editor.core.nfl2k5_asset_io import copy_user_asset_atomic, sha256_bytes
from mod_editor.core.nfl2k5_extended_visual_catalog import (
    Nfl2k5ProductVisualCatalog,
    Nfl2k5UniformCatalog as _Nfl2k5UniformCatalog,
    load_nfl2k5_extended_visual_catalog,
)
from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ProductVisualIO
from mod_editor.core.nfl2k5_source_cache import SourceCache
from mod_editor.core.nfl2k5_playbook_inspector import (
    Nfl2k5Playbook,
    Nfl2k5PlaybookInspector,
)
from mod_editor.core.nfl2k5_playbook_route_writer import (
    PlayRouteCloneRequest,
    request_from_mapping as play_route_request_from_mapping,
)
from mod_editor.core.nfl2k5_formation_play_writer import (
    FormationCreateRequest,
    FormationLinkRequest,
    PlayCreateRequest,
    formation_request_from_mapping,
    link_request_from_mapping,
    play_request_from_mapping as formation_play_request_from_mapping,
)
from mod_editor.core.nfl2k5_audio_catalog import (
    AudioReplacementSnapshot,
    MENU_BACK_SELECTOR,
    Nfl2k5AudioAsset,
    Nfl2k5AudioService,
    Nfl2k5StreamingAudioRange,
)
from mod_editor.core.nfl2k5_crib import (
    CribAsset,
    Nfl2k5CribCatalog,
    Nfl2k5CribIO,
)
from mod_editor.core.nfl2k5_crib_geometry_writer import (
    CompiledCribGeometryRecipe,
    build_unified_crib_geometry_import,
    list_editable_scenes as list_editable_crib_geometry_scenes,
)
from mod_editor.core.nfl2k5_stadium_studio import StadiumScene, StadiumTexture
from mod_editor.core.nfl2k5_stadium_texture_writer import (
    CompiledStadiumGeometryRecipe,
    CompiledStadiumTextureEdit,
    Nfl2k5StadiumTextureWriter,
    SELECTOR_RE as STADIUM_TEXTURE_SELECTOR_RE,
    TARGET_SCENE_ID as STADIUM_GEOMETRY_SCENE_ID,
)
from mod_editor.core.nfl2k5_text_catalog import (
    Nfl2k5TextCatalog,
    Nfl2k5TextEdits,
    RosterNumberAsset,
    TextAsset,
)

from .project_archive import (
    AuthorizedProjectAudioEdit,
    ProjectTargetIdentity,
    load_project_archive,
    save_project_archive,
)
from .audio_annotations import (
    AudioCueAnnotation,
    annotation_document,
    validate_audio_cue_annotation,
    validate_audio_cue_id,
)


SESSION_SCHEMA = "2k5_mod_studio_session/v1"
BACKEND_SCHEMA = "nfl2k5_visual_mod_project/v1"


def default_session_root() -> Path:
    return Path.home() / ".local" / "share" / "2k5-mod-studio" / "sessions"


def _asset_key(asset_id: str) -> str:
    return hashlib.sha256(asset_id.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


@contextmanager
def _explain_write_failure(path: Path) -> Iterator[None]:
    """Give the Studio error dialog an actionable Windows path-length error."""

    try:
        yield
    except OSError as exc:
        if platform_compat.IS_WINDOWS:
            paths = []
            for filename in (path, exc.filename, exc.filename2):
                if filename is not None:
                    value = os.fsdecode(filename)
                    if value.startswith("\\\\?\\UNC\\"):
                        value = "\\\\" + value[8:]
                    elif value.startswith("\\\\?\\"):
                        value = value[4:]
                    paths.append(value)
            length = max(map(len, paths))
            if length >= 260:
                raise ValidationError(
                    "Windows limits file paths to 260 characters and this one is "
                    f"{length}. Enable long paths in Windows (Settings or "
                    "HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem "
                    "LongPathsEnabled=1, then restart) or move your sessions folder."
                ) from exc
        raise


def _write_new_atomic(path: Path, payload: bytes) -> Path:
    """Publish a new file atomically and never overwrite an existing path."""

    with _explain_write_failure(path):
        Path(platform_compat.long_path(path.parent)).mkdir(parents=True, exist_ok=True)
        temporary = platform_compat.temporary_sibling(path)
        descriptor = os.open(
            platform_compat.long_path(temporary),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                platform_compat.publish_no_replace(
                    platform_compat.long_path(temporary), platform_compat.long_path(path)
                )
            except FileExistsError as exc:
                raise ValidationError(f"A file already exists there: {path}") from exc
            return path
        finally:
            Path(platform_compat.long_path(temporary)).unlink(missing_ok=True)


def _replace_atomic(path: Path, payload: bytes) -> None:
    with _explain_write_failure(path):
        Path(platform_compat.long_path(path.parent)).mkdir(parents=True, exist_ok=True)
        temporary = platform_compat.temporary_sibling(path)
        descriptor = os.open(
            platform_compat.long_path(temporary),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(platform_compat.long_path(temporary), platform_compat.long_path(path))
        finally:
            Path(platform_compat.long_path(temporary)).unlink(missing_ok=True)


@dataclass(frozen=True)
class SessionEdit:
    asset_id: str
    replacement_path: Path
    replacement_sha256: str
    rgba_sha256: str


@dataclass(frozen=True)
class AudioSessionEdit:
    # ``asset_id`` is always one public logical selector. ``physical_id`` is
    # private working-session state only and is never serialized to a project.
    asset_id: str
    replacement_path: Path
    replacement_sha256: str
    physical_id: str | None = None
    affected_asset_ids: tuple[str, ...] = ()

    @property
    def state_id(self) -> str:
        return self.physical_id or self.asset_id


@dataclass(frozen=True)
class StadiumSessionEdit:
    asset_id: str
    replacement_path: Path
    replacement_sha256: str
    rgba_sha256: str
    preview_path: Path
    preview_sha256: str


@dataclass(frozen=True)
class StadiumGeometrySessionEdit:
    scene_id: str
    recipe_path: Path
    recipe_sha256: str
    changed_target_count: int
    changed_vertex_count: int
    preserved_triangle_count: int

    @property
    def asset_id(self) -> str:
        return f"{self.scene_id}.geometry"


@dataclass(frozen=True)
class CribGeometrySessionEdit:
    scene_id: str
    recipe_path: Path
    recipe_sha256: str
    changed_target_count: int
    changed_vertex_count: int
    preserved_triangle_count: int

    @property
    def asset_id(self) -> str:
        return f"{self.scene_id}.geometry"


@dataclass(frozen=True)
class _ProjectStadiumAsset:
    """Archive-facing label around one source-proved Stadium texture row."""

    texture: StadiumTexture
    label: str = "Stadium embedded P8 surface texture"

    @property
    def asset_id(self) -> str:
        return self.texture.texture_id


@dataclass(frozen=True)
class ReplaceResult:
    asset_id: str
    modified: bool
    message: str


@dataclass(frozen=True)
class BatchReplaceResult:
    """Result of one validate-all visual transaction.

    ``changed_asset_ids`` are the targets whose working-session state changed
    during this operation. ``modified_asset_ids`` are the targets that remain
    authored replacements afterward; a batch may intentionally restore one or
    more targets to their source pixels.
    """

    requested_asset_ids: tuple[str, ...]
    changed_asset_ids: tuple[str, ...]
    modified_asset_ids: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class AudioBatchPreflightRow:
    """Read-only outcome for one logical WAV supplied by a batch caller."""

    asset_id: str
    label: str
    would_change: bool
    would_restore_original: bool
    affected_asset_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AudioBatchPreflightResult:
    """Frozen simulation of an authorized audio batch with no session writes."""

    rows: tuple[AudioBatchPreflightRow, ...]
    resulting_modified_asset_ids: tuple[str, ...]
    unique_physical_change_count: int
    unique_physical_restore_count: int
    affected_asset_ids: tuple[str, ...]


class StadiumProjectPreparationRequired(ValidationError):
    """A valid project references Stadium content before its cache is ready."""


class AudioProjectPreparationRequired(ValidationError):
    """A valid project references audio before private safety data is ready."""


@dataclass(frozen=True)
class _UndoItem:
    asset_id: str
    previous_snapshot: Path | None
    logical_asset_id: str | None = None
    affected_asset_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _UndoAction:
    label: str
    items: tuple[_UndoItem, ...]


@dataclass(frozen=True)
class _SessionUndo:
    source: str
    label: str
    payload: object | None = None


class _ProjectCatalogRouter:
    def __init__(self, session: "StudioSession") -> None:
        self.session = session

    def get_asset(self, asset_id: str) -> Any:
        return self.session._project_png_asset(asset_id)


class _ProjectAssetIORouter:
    def __init__(self, session: "StudioSession") -> None:
        self.session = session

    def validate_replacement(self, asset: Any, path: Path) -> tuple[bytes, bytes]:
        if isinstance(asset, _ProjectStadiumAsset):
            return self.session._validate_stadium_project_png(asset.texture, path)
        if isinstance(asset, CribAsset):
            return self.session._require_crib_io().validate_replacement(asset, path)
        return self.session.asset_io.validate_replacement(asset, path)

    def ensure_original(self, asset: Any) -> Path:
        if isinstance(asset, _ProjectStadiumAsset):
            return asset.texture.png_path
        if isinstance(asset, CribAsset):
            return self.session._require_crib_io().ensure_original(asset)
        return self.session.asset_io.ensure_original(asset)


class _SessionStadiumDelegate:
    """Expose session-owned P8 edit state through Stadium Studio's protocol."""

    def __init__(self, session: "StudioSession") -> None:
        self.session = session

    def supports(self, texture: StadiumTexture) -> bool:
        return self.session.supports_stadium_texture(texture)

    def current_png(self, texture: StadiumTexture) -> Path:
        return self.session.current_stadium_png(texture)

    def replace(self, texture: StadiumTexture, supplied_png: Path) -> ReplaceResult:
        return self.session.replace_stadium_texture(texture, supplied_png)

    def revert(self, texture: StadiumTexture) -> bool:
        return self.session.revert_stadium_texture(texture)

    def supports_geometry(self, scene: StadiumScene) -> bool:
        return self.session.supports_stadium_geometry(scene)

    def replace_geometry(
        self, scene: StadiumScene, compiled: CompiledStadiumGeometryRecipe
    ) -> ReplaceResult:
        return self.session.replace_stadium_geometry(scene, compiled)


class StudioSession:
    """A reversible edit set bound to one recognized, user-owned XISO."""

    def __init__(
        self,
        cache: SourceCache,
        uniform_catalog: Any,
        *,
        root: Path | None = None,
        session_id: str | None = None,
    ) -> None:
        self.cache = cache
        self.catalog = uniform_catalog
        # ``catalog`` owns the uniform set hierarchy and nothing else. A staged
        # PNG edit can come from any visual browser, so resolving an edit by its
        # ID needs the aggregate instead -- see :meth:`_visual_asset`.
        self.visual_catalog: Any | None = None
        self.asset_io = Nfl2k5ProductVisualIO(cache)
        self.session_id = session_id or str(uuid4())
        parent = (root or default_session_root()).expanduser()
        parent.mkdir(parents=True, exist_ok=True)
        self._session_parent = parent
        self.root = parent / self.session_id
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise ValidationError(
                "That Mod Studio working session already exists; choose a new session."
            ) from exc
        self.replacements = self.root / "replacements"
        self.history = self.root / "undo"
        self.replacements.mkdir(mode=0o700)
        self.history.mkdir(mode=0o700)
        self._edits: dict[str, SessionEdit] = {}
        self._undo: list[_UndoAction] = []
        self._undo_order: list[_SessionUndo] = []
        self.text_catalog: Nfl2k5TextCatalog | None = None
        self.text_edits: Nfl2k5TextEdits | None = None
        self.audio_service: Nfl2k5AudioService | None = None
        self._audio_edits: dict[str, AudioSessionEdit] = {}
        self._audio_undo: list[_UndoAction] = []
        self._audio_annotations: dict[str, AudioCueAnnotation] = {}
        self.crib_catalog: Nfl2k5CribCatalog | None = None
        self.crib_io: Nfl2k5CribIO | None = None
        self._crib_edits: dict[str, SessionEdit] = {}
        self._crib_undo: list[_UndoAction] = []
        self._crib_geometry_edits: dict[str, CribGeometrySessionEdit] = {}
        self.playbook_inspector: Nfl2k5PlaybookInspector | None = None
        self._play_route_edits: dict[str, PlayRouteCloneRequest] = {}
        self._formation_creates: dict[str, FormationCreateRequest] = {}
        self._play_creates: dict[str, PlayCreateRequest] = {}
        self._formation_links: dict[str, FormationLinkRequest] = {}
        self.stadium_writer: Nfl2k5StadiumTextureWriter | None = None
        self.stadium_texture: StadiumTexture | None = None
        self._stadium_textures: dict[str, StadiumTexture] = {}
        self.stadium_delegate = _SessionStadiumDelegate(self)
        self._stadium_edits: dict[str, StadiumSessionEdit] = {}
        self._stadium_geometry_edit: StadiumGeometrySessionEdit | None = None
        # Each physical uniform package owns its own pair. Word 0 jointly
        # tints facemask/faceshield; word 1 is HI_turtleneck. The old global
        # pair was actually Detroit HOME/AWAY and must never be revived.
        self._unif_colors: dict[str, tuple[str, str]] = {}
        self._stadium_undo: list[_UndoAction] = []
        self._project_catalog_router = _ProjectCatalogRouter(self)
        self._project_io_router = _ProjectAssetIORouter(self)
        self._history_sequence = 0
        self._audio_pack_preflight_secret = os.urandom(32)
        self._mutation_revision = 0
        self._write_manifest()

    def discard_private_workspace(self) -> None:
        """Delete only this disposable UUID session after a failed handoff.

        The UUID, exact parent/name relationship, non-symlink directory, and
        self-identifying session manifest are all checked before recursive
        deletion. This method is intentionally unsuitable for named test or
        user directories.
        """

        try:
            parsed = UUID(self.session_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValidationError(
                "Refusing to discard a private workspace without a UUID session ID."
            ) from exc
        if str(parsed) != self.session_id:
            raise ValidationError(
                "Refusing to discard a non-canonical private session directory."
            )
        root = self.root
        if root != self._session_parent / self.session_id or root.name != self.session_id:
            raise ValidationError(
                "Refusing to discard a workspace outside its exact session parent."
            )
        try:
            info = root.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValidationError(
                "Refusing to discard a private workspace that is not a real directory."
            )
        if root.resolve(strict=True) != (
            self._session_parent.resolve(strict=True) / self.session_id
        ):
            raise ValidationError(
                "Refusing to discard a redirected private session directory."
            )
        manifest_path = root / "session.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValidationError(
                "Refusing to discard a workspace without its valid session manifest."
            ) from exc
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema") != SESSION_SCHEMA
            or manifest.get("session_id") != self.session_id
        ):
            raise ValidationError(
                "Refusing to discard a workspace whose manifest identifies another session."
            )
        shutil.rmtree(root)

    @property
    def modified_count(self) -> int:
        return (
            len(self._edits) + len(self._crib_edits) + len(self._stadium_edits)
            + len(self._crib_geometry_edits)
            + int(self._stadium_geometry_edit is not None)
            + len(self._audio_edits)
            + len(self._unif_colors)
            + len(self._play_route_edits)
            + len(self._formation_creates)
            + len(self._play_creates)
            + len(self._formation_links)
            + (self.text_edits.modified_count if self.text_edits is not None else 0)
        )

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_order)

    @property
    def audio_annotations(self) -> tuple[AudioCueAnnotation, ...]:
        """Return project metadata in deterministic logical-cue order."""

        return tuple(
            self._audio_annotations[asset_id]
            for asset_id in sorted(self._audio_annotations)
        )

    @property
    def annotation_count(self) -> int:
        return len(self._audio_annotations)

    @property
    def project_metadata_count(self) -> int:
        """Count non-build metadata stored in the shareable project."""

        return self.annotation_count

    @property
    def has_project_metadata(self) -> bool:
        return bool(self._audio_annotations)

    @property
    def labeled_audio_asset_ids(self) -> frozenset[str]:
        return frozenset(self._audio_annotations)

    def audio_annotation(self, asset_id: str) -> AudioCueAnnotation | None:
        return self._audio_annotations.get(validate_audio_cue_id(asset_id))

    def set_audio_annotation(
        self,
        asset_id: str,
        title: str = "",
        note: str = "",
    ) -> bool:
        """Create/update one retail-free cue annotation as one Undo action."""

        annotation = validate_audio_cue_annotation(asset_id, title, note)
        if self.audio_service is not None:
            self.audio_service.resolve_playable_audio(annotation.cue_id)
        previous = self._audio_annotations.get(annotation.cue_id)
        if previous == annotation:
            return False
        self._audio_annotations[annotation.cue_id] = annotation
        label = (
            f"Edit audio label: {annotation.title or annotation.cue_id}"
            if previous is not None
            else f"Label audio: {annotation.title or annotation.cue_id}"
        )
        self._undo_order.append(_SessionUndo(
            "audio_annotation", label, (annotation.cue_id, previous)
        ))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            if previous is None:
                del self._audio_annotations[annotation.cue_id]
            else:
                self._audio_annotations[annotation.cue_id] = previous
            raise
        return True

    def clear_audio_annotation(self, asset_id: str) -> bool:
        """Remove one cue annotation while preserving an exact Undo snapshot."""

        cue_id = validate_audio_cue_id(asset_id)
        previous = self._audio_annotations.get(cue_id)
        if previous is None:
            return False
        del self._audio_annotations[cue_id]
        label = f"Clear audio label: {previous.title or cue_id}"
        self._undo_order.append(_SessionUndo(
            "audio_annotation", label, (cue_id, previous)
        ))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            self._audio_annotations[cue_id] = previous
            raise
        return True

    @property
    def modified_asset_ids(self) -> frozenset[str]:
        text_ids: set[str] = set()
        if self.text_edits is not None:
            text_ids.update(
                row["asset_id"]
                for row in self.text_edits.replacement_document()["edits"]
            )
        audio_ids = {
            asset_id
            for edit in self._audio_edits.values()
            for asset_id in (edit.affected_asset_ids or (edit.asset_id,))
        }
        return frozenset((
            *self._edits, *self._crib_edits, *self._stadium_edits,
            *(edit.asset_id for edit in self._crib_geometry_edits.values()),
            *((self._stadium_geometry_edit.asset_id,)
              if self._stadium_geometry_edit is not None else ()),
            *audio_ids, *text_ids, *self._play_route_edits,
        ))

    @property
    def modified_audio_asset_ids(self) -> frozenset[str]:
        return frozenset(
            asset_id
            for edit in self._audio_edits.values()
            for asset_id in (edit.affected_asset_ids or (edit.asset_id,))
        )

    @property
    def mutation_revision(self) -> int:
        """Monotonic in-memory witness for project/edit-state mutations."""

        return self._mutation_revision

    def _audio_pack_preflight_signature(
        self, *, member_digest: str, schema: str
    ) -> str:
        if (
            type(member_digest) is not str
            or len(member_digest) != 64
            or any(character not in "0123456789abcdef" for character in member_digest)
            or not isinstance(schema, str)
            or not schema
        ):
            raise ValidationError("Audio replacement-pack preflight identity is invalid.")
        payload = "\0".join((
            "2k5-audio-pack-preflight/v1",
            member_digest,
            schema,
            self.cache.source.sha256,
            self.session_id,
            str(self._mutation_revision),
        )).encode("utf-8")
        return hmac.new(
            self._audio_pack_preflight_secret, payload, hashlib.sha256
        ).hexdigest()

    def issue_audio_pack_preflight_token(
        self, *, member_digest: str, schema: str
    ) -> str:
        """Issue an opaque, session-local confirmation witness."""

        return (
            "2k5apf1."
            + self._audio_pack_preflight_signature(
                member_digest=member_digest, schema=schema
            )
        )

    def verify_audio_pack_preflight_token(
        self, token: str, *, member_digest: str, schema: str
    ) -> None:
        """Require the exact preflighted members and unmutated session/source."""

        expected = self.issue_audio_pack_preflight_token(
            member_digest=member_digest, schema=schema
        )
        if not isinstance(token, str) or not hmac.compare_digest(token, expected):
            raise ValidationError(
                "This audio replacement pack or the working project changed after "
                "preflight. Run Preview changes again before importing."
            )

    @property
    def modified_crib_asset_ids(self) -> frozenset[str]:
        return frozenset((
            *self._crib_edits,
            *(edit.asset_id for edit in self._crib_geometry_edits.values()),
        ))

    @property
    def modified_crib_model_scene_ids(self) -> frozenset[str]:
        return frozenset(self._crib_geometry_edits)

    @property
    def modified_stadium_asset_ids(self) -> frozenset[str]:
        return frozenset((
            *self._stadium_edits,
            *((self._stadium_geometry_edit.asset_id,)
              if self._stadium_geometry_edit is not None else ()),
        ))

    def attach_text_catalog(self, catalog: Nfl2k5TextCatalog) -> None:
        if self.text_catalog is not None or self.modified_count:
            raise ValidationError("Text editing must be attached to a fresh session.")
        self.text_catalog = catalog
        self.text_edits = Nfl2k5TextEdits(catalog)
        self._write_manifest()

    def attach_playbook_inspector(
        self, inspector: Nfl2k5PlaybookInspector
    ) -> None:
        if self.playbook_inspector is not None:
            if self.playbook_inspector is not inspector:
                raise ValidationError("A different PLAY source is already attached.")
            return
        if self._play_route_edits:
            raise ValidationError("PLAY editing must be attached before route edits.")
        self.playbook_inspector = inspector

    @staticmethod
    def _validate_play_route_set(
        book: Nfl2k5Playbook,
        requests: Iterable[PlayRouteCloneRequest],
    ) -> None:
        rows = tuple(requests)
        targets: set[tuple[int, int]] = set()
        replacement_starts: dict[tuple[int, int], int] = {}
        for request in rows:
            if request.asset_id != book.asset_id:
                raise ValidationError("PLAY route selector names another playbook.")
            if not 0 <= request.target_play_index < len(book.plays) \
                    or not 0 <= request.donor_play_index < len(book.plays):
                raise ValidationError("PLAY route play index is outside this book.")
            if not 0 <= request.target_slot_index < 11 \
                    or not 0 <= request.donor_slot_index < 11:
                raise ValidationError("PLAY assignment slots must be between 0 and 10.")
            target_key = (
                request.target_play_index, request.target_slot_index
            )
            if target_key in targets:
                raise ValidationError("A PLAY route target is already edited.")
            targets.add(target_key)
            if target_key == (
                request.donor_play_index, request.donor_slot_index
            ):
                raise ValidationError("Choose a different donor assignment route.")
            donor = book.plays[request.donor_play_index].assignments[
                request.donor_slot_index
            ]
            target = book.plays[request.target_play_index].assignments[
                request.target_slot_index
            ]
            if (
                donor.chain_start_index == target.chain_start_index
                and donor.descriptor_word == target.descriptor_word
            ):
                raise ValidationError("That donor already matches the target route.")
            replacement_starts[target_key] = donor.chain_start_index
        before_starts = {
            assignment.chain_start_index
            for play in book.plays for assignment in play.assignments
        }
        after_starts = {
            replacement_starts.get(
                (play.index, assignment.slot_index),
                assignment.chain_start_index,
            )
            for play in book.plays for assignment in play.assignments
        }
        if before_starts != after_starts:
            raise ValidationError(
                "That copy would orphan an existing route chain. Choose a target "
                "whose current chain is also used elsewhere, or use a balanced swap."
            )

    @property
    def play_route_edits(self) -> tuple[PlayRouteCloneRequest, ...]:
        return tuple(
            self._play_route_edits[key] for key in sorted(self._play_route_edits)
        )

    def copy_play_assignment_route(
        self, request: PlayRouteCloneRequest
    ) -> bool:
        inspector = self.playbook_inspector
        if inspector is None:
            raise ValidationError("Open the Playbooks & Plays editor first.")
        book = inspector.load(request.asset_id)
        previous = self._play_route_edits.get(request.selector)
        if previous == request:
            return False
        candidate = dict(self._play_route_edits)
        candidate[request.selector] = request
        self._validate_play_route_set(
            book,
            (row for row in candidate.values() if row.asset_id == book.asset_id),
        )
        self._play_route_edits = candidate
        label = (
            f"Copy assignment route to play {request.target_play_index + 1}, "
            f"slot {request.target_slot_index + 1}"
        )
        self._undo_order.append(_SessionUndo(
            "play_route", label, (request.selector, previous)
        ))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            if previous is None:
                self._play_route_edits.pop(request.selector, None)
            else:
                self._play_route_edits[request.selector] = previous
            raise
        return True

    def revert_play_assignment_route(self, selector: str) -> bool:
        previous = self._play_route_edits.get(selector)
        if previous is None:
            return False
        del self._play_route_edits[selector]
        label = (
            f"Revert assignment route at play {previous.target_play_index + 1}, "
            f"slot {previous.target_slot_index + 1}"
        )
        self._undo_order.append(_SessionUndo(
            "play_route", label, (selector, previous)
        ))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            self._play_route_edits[selector] = previous
            raise
        return True

    @property
    def formation_creates(self) -> tuple[FormationCreateRequest, ...]:
        return tuple(self._formation_creates[key] for key in sorted(self._formation_creates))

    @property
    def play_creates(self) -> tuple[PlayCreateRequest, ...]:
        return tuple(self._play_creates[key] for key in sorted(self._play_creates))

    @property
    def formation_links(self) -> tuple[FormationLinkRequest, ...]:
        return tuple(self._formation_links[key] for key in sorted(self._formation_links))

    @staticmethod
    def _build_order_key(row: Mapping[str, object]) -> tuple[str, str, str]:
        import json as _json

        return (str(row["asset_id"]), str(row["kind"]), _json.dumps(row, sort_keys=True, default=list))

    def staged_formation_index(self, selector: str, book_formation_count: int) -> int:
        """Index a staged formation create occupies after Build.

        The project archive sorts create rows by (asset, kind, canonical JSON) and the
        build compiles a book's creates in that order, so the same key is used here.
        """
        request = self._formation_creates.get(selector)
        if request is None:
            raise ValidationError("That formation is not staged in this session.")
        if request.replace_index is not None:
            return request.replace_index
        rows = sorted(
            (r.provider_edit() for r in self._formation_creates.values()
             if r.asset_id == request.asset_id and r.replace_index is None),
            key=self._build_order_key,
        )
        return book_formation_count + rows.index(request.provider_edit())

    def staged_play_index(self, selector: str, book_play_count: int) -> int:
        """Index a staged play create occupies after Build (same ordering rule as formations)."""
        request = self._play_creates.get(selector)
        if request is None:
            raise ValidationError("That play is not staged in this session.")
        if request.replace_index is not None:
            return request.replace_index
        rows = sorted(
            (r.provider_edit() for r in self._play_creates.values()
             if r.asset_id == request.asset_id and r.replace_index is None),
            key=self._build_order_key,
        )
        return book_play_count + rows.index(request.provider_edit())

    def create_formation(self, request: FormationCreateRequest) -> bool:
        inspector = self.playbook_inspector
        if inspector is None:
            raise ValidationError("Open the Playbooks & Plays editor first.")
        book = inspector.load(request.asset_id)
        # Use donor index as key until compiled new index known; deduplicate per donor
        key = request.selector
        previous = self._formation_creates.get(key)
        if previous == request:
            return False
        candidate = dict(self._formation_creates)
        candidate[key] = request
        # Validate via writer on donor book raw (lightweight, checks capacity via writer)
        from nfl_outer import read_entry_range

        raw = read_entry_range(
            inspector.index.archive,
            inspector.index.archive.entries[inspector.index.get(request.asset_id).outer_index],
            inspector.index.get(request.asset_id).chunk_offset,
            inspector.index.get(request.asset_id).raw_size,
        )
        from mod_editor.core.nfl2k5_formation_play_writer import compile_formation_play_creations

        # The compiler edits one book per call, and a project may now hold designs for
        # several books at once (a community pack applied to more than one team), so the
        # candidate set is filtered to the book this request touches.
        book_id = request.asset_id
        compile_formation_play_creations(
            raw,
            formation_requests=[r for r in candidate.values() if r.asset_id == book_id],
            play_requests=[r for r in self._play_creates.values() if r.asset_id == book_id],
            link_requests=[r for r in self._formation_links.values() if r.asset_id == book_id],
        )
        self._formation_creates = candidate
        self._undo_order.append(_SessionUndo("formation_create", f"Create formation from {request.donor_formation_index}", (key, previous)))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            if previous is None:
                self._formation_creates.pop(key, None)
            else:
                self._formation_creates[key] = previous
            raise
        return True

    def create_play(self, request: PlayCreateRequest) -> bool:
        inspector = self.playbook_inspector
        if inspector is None:
            raise ValidationError("Open the Playbooks & Plays editor first.")
        key = request.selector
        previous = self._play_creates.get(key)
        if previous == request:
            return False
        candidate = dict(self._play_creates)
        candidate[key] = request
        from nfl_outer import read_entry_range

        raw = read_entry_range(
            inspector.index.archive,
            inspector.index.archive.entries[inspector.index.get(request.asset_id).outer_index],
            inspector.index.get(request.asset_id).chunk_offset,
            inspector.index.get(request.asset_id).raw_size,
        )
        from mod_editor.core.nfl2k5_formation_play_writer import compile_formation_play_creations

        book_id = request.asset_id
        compile_formation_play_creations(
            raw,
            formation_requests=[r for r in self._formation_creates.values() if r.asset_id == book_id],
            play_requests=[r for r in candidate.values() if r.asset_id == book_id],
            link_requests=[r for r in self._formation_links.values() if r.asset_id == book_id],
        )
        self._play_creates = candidate
        self._undo_order.append(_SessionUndo("play_create", f"Create play from {request.donor_play_index}", (key, previous)))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            if previous is None:
                self._play_creates.pop(key, None)
            else:
                self._play_creates[key] = previous
            raise
        return True

    def revert_formation_create(self, selector: str) -> bool:
        previous = self._formation_creates.get(selector)
        if previous is None:
            return False
        del self._formation_creates[selector]
        self._undo_order.append(_SessionUndo("formation_create", f"Revert formation {selector}", (selector, previous)))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            self._formation_creates[selector] = previous
            raise
        return True

    def revert_play_create(self, selector: str) -> bool:
        previous = self._play_creates.get(selector)
        if previous is None:
            return False
        del self._play_creates[selector]
        self._undo_order.append(_SessionUndo("play_create", f"Revert play {selector}", (selector, previous)))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            self._play_creates[selector] = previous
            raise
        return True

    def create_formation_link(self, request: FormationLinkRequest) -> bool:
        inspector = self.playbook_inspector
        if inspector is None:
            raise ValidationError("Open the Playbooks & Plays editor first.")
        key = request.selector
        previous = self._formation_links.get(key)
        if previous == request:
            return False
        candidate = dict(self._formation_links)
        candidate[key] = request
        from nfl_outer import read_entry_range

        raw = read_entry_range(
            inspector.index.archive,
            inspector.index.archive.entries[inspector.index.get(request.asset_id).outer_index],
            inspector.index.get(request.asset_id).chunk_offset,
            inspector.index.get(request.asset_id).raw_size,
        )
        from mod_editor.core.nfl2k5_formation_play_writer import compile_formation_play_creations

        book_id = request.asset_id
        compile_formation_play_creations(
            raw,
            formation_requests=[r for r in self._formation_creates.values() if r.asset_id == book_id],
            play_requests=[r for r in self._play_creates.values() if r.asset_id == book_id],
            link_requests=[r for r in candidate.values() if r.asset_id == book_id],
        )
        self._formation_links = candidate
        self._undo_order.append(_SessionUndo("formation_link", f"List play {request.play_index} in formation {request.formation_index}", (key, previous)))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            if previous is None:
                self._formation_links.pop(key, None)
            else:
                self._formation_links[key] = previous
            raise
        return True

    def revert_formation_link(self, selector: str) -> bool:
        previous = self._formation_links.get(selector)
        if previous is None:
            return False
        del self._formation_links[selector]
        self._undo_order.append(_SessionUndo("formation_link", f"Revert link {selector}", (selector, previous)))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            self._formation_links[selector] = previous
            raise
        return True

    def attach_audio_service(self, service: Nfl2k5AudioService) -> None:
        if self.audio_service is not None or self.modified_count:
            raise ValidationError("Audio editing must be attached to a fresh session.")
        if service.cache.root != self.cache.root:
            raise ValidationError("Audio service and working session use different caches.")
        # Annotation-only projects may load before the audio catalog is ready.
        # Bind every saved logical ID to this exact source before attachment so
        # a foreign or stale cue label cannot become silently accepted later.
        for annotation in self.audio_annotations:
            service.resolve_playable_audio(annotation.cue_id)
        self.audio_service = service
        self._write_manifest()

    def attach_crib(
        self, catalog: Nfl2k5CribCatalog, crib_io: Nfl2k5CribIO
    ) -> None:
        if self.crib_catalog is not None or self.modified_count:
            raise ValidationError("The Crib editor must be attached to a fresh session.")
        if crib_io.catalog is not catalog or crib_io.cache.root != self.cache.root:
            raise ValidationError("The Crib catalog and working session do not match.")
        self.crib_catalog = catalog
        self.crib_io = crib_io
        self._write_manifest()

    def attach_stadium_texture(
        self, writer: Nfl2k5StadiumTextureWriter, texture: StadiumTexture
    ) -> None:
        if self.stadium_writer is not None:
            raise ValidationError(
                "The Stadium texture editor is already attached to this session."
            )
        if writer.cache.root != self.cache.root or not writer.supports(texture):
            raise ValidationError(
                "The Stadium texture writer and working session do not match."
            )
        self.stadium_writer = writer
        # Keep the original first-target attribute for callers/tests that use
        # it as an attachment sentinel. The writer itself owns all 23,838
        # source-derived editable occurrences.
        self.stadium_texture = texture
        self._stadium_textures[texture.texture_id] = texture
        self._write_manifest()

    def supports_stadium_texture(self, texture: StadiumTexture) -> bool:
        writer = self.stadium_writer
        return bool(writer is not None and writer.supports(texture))

    def current_stadium_png(self, texture: StadiumTexture) -> Path:
        self._require_supported_stadium_texture(texture)
        self._stadium_textures[texture.texture_id] = texture
        edit = self._stadium_edits.get(texture.texture_id)
        return edit.preview_path if edit is not None else texture.png_path

    def replace_stadium_texture(
        self, texture: StadiumTexture, supplied_png: Path
    ) -> ReplaceResult:
        writer = self._require_supported_stadium_texture(texture)
        self._stadium_textures[texture.texture_id] = texture
        payload, rgba, compiled = writer.validated_replacement(texture, supplied_png)
        _original_payload, original_rgba = writer.read_validated_png(
            texture.png_path, texture
        )
        if sha256_bytes(original_rgba) != texture.rgba_sha256:
            raise ValidationError(
                "The private Stadium preview no longer matches its source SCNE."
            )
        previous = self._snapshot_stadium(texture.texture_id)
        current = self._stadium_edits.get(texture.texture_id)
        if rgba == original_rgba:
            if current is None:
                return ReplaceResult(
                    texture.texture_id,
                    False,
                    "That PNG matches the original stadium texture.",
                )
            self._remove_stadium_edit_files(current)
            del self._stadium_edits[texture.texture_id]
            self._stadium_undo.append(_UndoAction(
                "Restore Stadium texture",
                (_UndoItem(texture.texture_id, previous),),
            ))
            self._undo_order.append(_SessionUndo(
                "stadium", "Restore Stadium texture"
            ))
            self._write_manifest()
            return ReplaceResult(
                texture.texture_id,
                False,
                "That PNG matches the original pixels, so the Stadium texture was reverted.",
            )

        staged = self._stage_stadium_edit(texture, payload, rgba, compiled)
        self._stadium_edits[texture.texture_id] = staged
        if current is not None:
            self._remove_stadium_edit_files(current)
        self._stadium_undo.append(_UndoAction(
            "Replace Stadium texture",
            (_UndoItem(texture.texture_id, previous),),
        ))
        self._undo_order.append(_SessionUndo(
            "stadium", "Replace Stadium texture"
        ))
        self._write_manifest()
        return ReplaceResult(
            texture.texture_id,
            True,
            f"Stadium texture is ready to build. {texture.mapped_material_count} "
            "linked material surface set(s) change together.",
        )

    def revert_stadium_texture(self, texture: StadiumTexture) -> bool:
        self._require_supported_stadium_texture(texture)
        self._stadium_textures[texture.texture_id] = texture
        current = self._stadium_edits.get(texture.texture_id)
        if current is None:
            return False
        previous = self._snapshot_stadium(texture.texture_id)
        self._remove_stadium_edit_files(current)
        del self._stadium_edits[texture.texture_id]
        self._stadium_undo.append(_UndoAction(
            "Revert Stadium texture",
            (_UndoItem(texture.texture_id, previous),),
        ))
        self._undo_order.append(_SessionUndo(
            "stadium", "Revert Stadium texture"
        ))
        self._write_manifest()
        return True

    def supports_stadium_geometry(self, scene: StadiumScene) -> bool:
        return bool(
            self.stadium_writer is not None
            and scene.scene_id == STADIUM_GEOMETRY_SCENE_ID
            and scene.geometry_targets
        )

    def replace_stadium_geometry(
        self,
        scene: StadiumScene,
        compiled: CompiledStadiumGeometryRecipe,
    ) -> ReplaceResult:
        """Stage one private, source-bound position recipe as an Undo action."""

        if not self.supports_stadium_geometry(scene):
            raise ValidationError(
                "That Stadium scene is export-only because its bounded position "
                "catalog is unavailable."
            )
        if (
            not isinstance(compiled, CompiledStadiumGeometryRecipe)
            or compiled.scene_id != scene.scene_id
            or sha256_bytes(compiled.recipe) != compiled.recipe_sha256
            or compiled.changed_target_count <= 0
            or compiled.changed_vertex_count <= 0
            or compiled.preserved_triangle_count <= 0
        ):
            raise ValidationError(
                "The compiled Stadium geometry recipe changed before staging."
            )
        current = self._stadium_geometry_edit
        if current is not None and current.recipe_sha256 == compiled.recipe_sha256:
            return ReplaceResult(
                current.asset_id,
                True,
                "That edited model is already staged.",
            )

        key = _asset_key(f"{scene.scene_id}.geometry")
        destination = self.replacements / f"{key}-{uuid4().hex}.geometry.json"
        _write_new_atomic(destination, compiled.recipe)
        staged = StadiumGeometrySessionEdit(
            scene.scene_id,
            destination,
            compiled.recipe_sha256,
            compiled.changed_target_count,
            compiled.changed_vertex_count,
            compiled.preserved_triangle_count,
        )
        self._stadium_geometry_edit = staged
        self._undo_order.append(_SessionUndo(
            "stadium_geometry",
            "Import edited Stadium model",
            current,
        ))
        try:
            self._write_manifest()
        except BaseException:
            self._stadium_geometry_edit = current
            self._undo_order.pop()
            destination.unlink(missing_ok=True)
            raise
        return ReplaceResult(
            staged.asset_id,
            True,
            f"Stadium geometry is ready to build: {staged.changed_vertex_count:,} "
            f"vertices across {staged.changed_target_count} fixed target(s).",
        )

    def is_modified(self, asset_or_id: Any) -> bool:
        asset_id = (
            asset_or_id if isinstance(asset_or_id, str) else asset_or_id.asset_id
        )
        return asset_id in self.modified_asset_ids

    def current_path(self, asset: Any) -> Path:
        edit = self._edits.get(asset.asset_id)
        return edit.replacement_path if edit else self.asset_io.ensure_original(asset)

    def export_asset(
        self, asset: Any, destination: Path, *, replace: bool = False
    ) -> Path:
        source = self.current_path(asset)
        destination = destination.expanduser()
        if not destination.is_absolute():
            destination = Path.cwd() / destination
        if destination.exists() and not replace:
            raise ValidationError(f"A file already exists there: {destination}")
        if destination.is_symlink():
            raise ValidationError(f"Refusing to replace a symbolic link: {destination}")
        payload = source.read_bytes()
        if replace:
            _replace_atomic(destination, payload)
        else:
            _write_new_atomic(destination, payload)
        return destination.resolve(strict=True)

    def replace(self, asset: Any, supplied_png: Path) -> ReplaceResult:
        if not bool(getattr(asset, "editable", True)):
            raise ValidationError(
                f"{asset.label} is preview/export-only because its texture "
                "format has no proved fixed-span importer."
            )
        original_path = self.asset_io.ensure_original(asset)
        _original_payload, original_rgba = self.asset_io.validate_replacement(
            asset, original_path
        )
        supplied_payload, supplied_rgba = self.asset_io.validate_replacement(
            asset, supplied_png
        )
        previous = self._snapshot_previous(asset.asset_id)
        if supplied_rgba == original_rgba:
            existing = self._edits.pop(asset.asset_id, None)
            if existing is not None:
                existing.replacement_path.unlink(missing_ok=True)
            self._undo.append(
                _UndoAction(f"Restore {asset.label}", (_UndoItem(asset.asset_id, previous),))
            )
            self._undo_order.append(_SessionUndo("visual", f"Restore {asset.label}"))
            self._write_manifest()
            return ReplaceResult(
                asset.asset_id,
                False,
                "That PNG matches the original pixels, so the asset was reverted.",
            )

        destination = self.replacements / f"{_asset_key(asset.asset_id)}.png"
        # Stage the exact bytes that were validated above.  Re-reading the
        # caller's path here would let an external editor change it between
        # validation and the private copy.
        _replace_atomic(destination, supplied_payload)
        self._edits[asset.asset_id] = SessionEdit(
            asset_id=asset.asset_id,
            replacement_path=destination,
            replacement_sha256=sha256_bytes(supplied_payload),
            rgba_sha256=sha256_bytes(supplied_rgba),
        )
        self._undo.append(
            _UndoAction(f"Replace {asset.label}", (_UndoItem(asset.asset_id, previous),))
        )
        self._undo_order.append(_SessionUndo("visual", f"Replace {asset.label}"))
        self._write_manifest()
        return ReplaceResult(asset.asset_id, True, f"{asset.label} is ready to build.")

    def replace_batch(
        self,
        replacements: Iterable[tuple[Any, Path]],
        *,
        label: str = "Import visual bundle",
    ) -> BatchReplaceResult:
        """Validate and stage several visual PNGs as one undoable operation.

        Every catalog target, private source original, supplied PNG, and
        currently staged replacement is checked before this method changes any
        working-session edit. The validated bytes are copied into private
        transaction files first. A commit failure restores every touched file
        and the prior in-memory state, so callers never receive a partially
        imported bundle.

        Source-derived originals may be decoded into the existing private
        source cache during validation. They never enter session replacements,
        undo snapshots, or shareable projects unless the supplied pixels truly
        differ from the source original.
        """

        requested = tuple(replacements)
        if not requested:
            raise ValidationError("Choose at least one visual PNG to import.")
        if not isinstance(label, str) or not label.strip():
            raise ValidationError("The batch edit needs a readable undo label.")

        selected: list[tuple[Any, Path]] = []
        seen: set[str] = set()
        for number, row in enumerate(requested, 1):
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValidationError(
                    f"Visual batch row {number} must contain an asset and PNG path."
                )
            supplied_asset, supplied_path = row
            asset_id = getattr(supplied_asset, "asset_id", None)
            if not isinstance(asset_id, str) or not asset_id:
                raise ValidationError(
                    f"Visual batch row {number} has no valid asset ID."
                )
            if asset_id in seen:
                raise ValidationError(
                    f"The visual batch lists {asset_id} more than once."
                )
            seen.add(asset_id)
            # Resolve through this session's catalog so a caller cannot attach
            # foreign dimensions/provider selectors to a familiar-looking ID.
            asset = self._visual_asset(asset_id)
            if not bool(getattr(asset, "editable", True)):
                raise ValidationError(
                    f"{asset.label} is preview/export-only because its texture "
                    "format has no proved fixed-span importer."
                )
            selected.append((asset, Path(supplied_path)))

        @dataclass(frozen=True)
        class _ValidatedBatchRow:
            asset: Any
            payload: bytes
            rgba: bytes
            original_rgba: bytes
            current_rgba: bytes | None

        validated: list[_ValidatedBatchRow] = []
        # This entire loop is read-only with respect to session edit state.
        # ``ensure_original`` is allowed to populate the separate private
        # source cache, which is not a project mutation or an undoable edit.
        for asset, supplied_path in selected:
            original_path = self.asset_io.ensure_original(asset)
            _original_payload, original_rgba = self.asset_io.validate_replacement(
                asset, original_path
            )
            payload, rgba = self.asset_io.validate_replacement(asset, supplied_path)
            current = self._edits.get(asset.asset_id)
            current_rgba: bytes | None = None
            if current is not None:
                current_payload, current_rgba = self.asset_io.validate_replacement(
                    asset, current.replacement_path
                )
                if (
                    sha256_bytes(current_payload) != current.replacement_sha256
                    or sha256_bytes(current_rgba) != current.rgba_sha256
                ):
                    raise ValidationError(
                        f"The staged PNG for {asset.label} changed outside Mod Studio. "
                        "Replace it again before importing a bundle."
                    )
            validated.append(_ValidatedBatchRow(
                asset, payload, rgba, original_rgba, current_rgba
            ))

        changed = tuple(
            row for row in validated
            if row.rgba != (
                row.current_rgba
                if row.current_rgba is not None else row.original_rgba
            )
        )
        requested_ids = tuple(row.asset.asset_id for row in validated)
        if not changed:
            return BatchReplaceResult(
                requested_ids,
                (),
                tuple(
                    asset_id for asset_id in requested_ids
                    if asset_id in self._edits
                ),
                "Every imported PNG already matches the current working pixels.",
            )

        transaction = uuid4().hex
        staged_paths: dict[str, Path] = {}
        snapshots: dict[str, Path | None] = {}
        old_edits = dict(self._edits)
        old_undo_length = len(self._undo)
        old_order_length = len(self._undo_order)
        old_history_sequence = self._history_sequence
        committed_ids: set[str] = set()
        try:
            # Materialize exact bytes read above before touching live session
            # destinations. Rows restoring source pixels need no staged file.
            for row in changed:
                if row.rgba == row.original_rgba:
                    continue
                staged = self.replacements / (
                    f".team-kit-{transaction}-{_asset_key(row.asset.asset_id)}.png"
                )
                _write_new_atomic(staged, row.payload)
                staged_paths[row.asset.asset_id] = staged

            # Snapshot all previous authored states only after every input and
            # every new transaction payload passed validation.
            undo_items: list[_UndoItem] = []
            for row in changed:
                snapshot = self._snapshot_previous(row.asset.asset_id)
                snapshots[row.asset.asset_id] = snapshot
                undo_items.append(_UndoItem(row.asset.asset_id, snapshot))

            new_edits = dict(old_edits)
            for row in changed:
                asset_id = row.asset.asset_id
                destination = self.replacements / f"{_asset_key(asset_id)}.png"
                if row.rgba == row.original_rgba:
                    committed_ids.add(asset_id)
                    destination.unlink(missing_ok=True)
                    new_edits.pop(asset_id, None)
                    continue
                staged = staged_paths.pop(asset_id)
                committed_ids.add(asset_id)
                with _explain_write_failure(destination):
                    os.replace(platform_compat.long_path(staged), platform_compat.long_path(destination))
                new_edits[asset_id] = SessionEdit(
                    asset_id,
                    destination,
                    sha256_bytes(row.payload),
                    sha256_bytes(row.rgba),
                )

            self._edits = new_edits
            normalized_label = label.strip()
            self._undo.append(_UndoAction(normalized_label, tuple(undo_items)))
            self._undo_order.append(_SessionUndo("visual", normalized_label))
            self._write_manifest()
        except BaseException:
            # Restore touched replacement paths from the pre-commit snapshots.
            # If the manifest write itself failed, best-effort rewriting the old
            # state keeps the on-disk session ledger aligned as well.
            self._edits = old_edits
            del self._undo[old_undo_length:]
            del self._undo_order[old_order_length:]
            self._history_sequence = old_history_sequence
            for row in changed:
                asset_id = row.asset.asset_id
                if asset_id not in committed_ids:
                    continue
                destination = self.replacements / f"{_asset_key(asset_id)}.png"
                destination.unlink(missing_ok=True)
                snapshot = snapshots.get(asset_id)
                if snapshot is not None and snapshot.is_file():
                    copy_user_asset_atomic(snapshot, destination)
            try:
                self._write_manifest()
            except BaseException:
                pass
            for snapshot in snapshots.values():
                if snapshot is not None:
                    snapshot.unlink(missing_ok=True)
            raise
        finally:
            for staged in staged_paths.values():
                staged.unlink(missing_ok=True)

        changed_ids = tuple(row.asset.asset_id for row in changed)
        modified_ids = tuple(
            asset_id for asset_id in requested_ids if asset_id in self._edits
        )
        return BatchReplaceResult(
            requested_ids,
            changed_ids,
            modified_ids,
            f"Imported {len(changed_ids)} changed uniform component"
            f"{'s' if len(changed_ids) != 1 else ''} as one undoable edit.",
        )

    def revert(self, asset: Any) -> bool:
        edit = self._edits.get(asset.asset_id)
        if edit is None:
            return False
        previous = self._snapshot_previous(asset.asset_id)
        edit.replacement_path.unlink(missing_ok=True)
        del self._edits[asset.asset_id]
        self._undo.append(
            _UndoAction(f"Revert {asset.label}", (_UndoItem(asset.asset_id, previous),))
        )
        self._undo_order.append(_SessionUndo("visual", f"Revert {asset.label}"))
        self._write_manifest()
        return True

    def uniform_colors(self, selector: str) -> tuple[str, str, bool]:
        """Current pair for one physical set and whether it is staged."""
        from mod_editor.core import nfl2k5_unif_color_writer as colour

        uniform_set = self.catalog.get_uniform_set(selector)
        staged = self._unif_colors.get(uniform_set.selector)
        if staged is not None:
            return staged[0], staged[1], True
        try:
            retail = colour.resolve_uniform_color_record(
                self.cache.pack0, uniform_set.selector
            )
        except colour.UnifColorWriterError as exc:
            raise ValidationError(str(exc)) from exc
        return retail.facemask_argb, retail.turtleneck_argb, False

    def set_uniform_colors(
        self, selector: str, facemask: str, turtleneck: str
    ) -> tuple[str, str, bool]:
        """Stage one selected set, preserving every neighboring record."""
        from mod_editor.core import nfl2k5_unif_color_writer as colour

        uniform_set = self.catalog.get_uniform_set(selector)
        try:
            pair = (colour.parse_color(facemask), colour.parse_color(turtleneck))
            retail = colour.resolve_uniform_color_record(
                self.cache.pack0, uniform_set.selector, verify_pack_hash=True
            )
        except colour.UnifColorWriterError as exc:
            raise ValidationError(str(exc)) from exc
        canonical = (f"{pair[0]:08X}", f"{pair[1]:08X}")
        previous = self._unif_colors.get(uniform_set.selector)
        if canonical == previous:
            return canonical[0], canonical[1], True
        if previous is None and canonical == retail.pair:
            # Applying the source pair to an unmodified set is a true no-op:
            # do not create phantom Undo history or dirty a project that still
            # contains no build edits.
            return canonical[0], canonical[1], False
        if canonical == retail.pair:
            self._unif_colors.pop(uniform_set.selector, None)
        else:
            self._unif_colors[uniform_set.selector] = canonical
        label = f"Set colours for {uniform_set.label}"
        self._undo_order.append(
            _SessionUndo("uniform_color", label,
                         (uniform_set.selector, previous))
        )
        try:
            self._write_manifest()
        except BaseException:
            if previous is None:
                self._unif_colors.pop(uniform_set.selector, None)
            else:
                self._unif_colors[uniform_set.selector] = previous
            self._undo_order.pop()
            raise
        return canonical[0], canonical[1], canonical != retail.pair

    def clear_uniform_colors(self, selector: str) -> bool:
        """Revert only the selected set to its source colours."""
        uniform_set = self.catalog.get_uniform_set(selector)
        previous = self._unif_colors.pop(uniform_set.selector, None)
        if previous is None:
            return False
        label = f"Revert colours for {uniform_set.label}"
        self._undo_order.append(
            _SessionUndo("uniform_color", label,
                         (uniform_set.selector, previous))
        )
        try:
            self._write_manifest()
        except BaseException:
            self._unif_colors[uniform_set.selector] = previous
            self._undo_order.pop()
            raise
        return True

    def revert_all(self) -> int:
        text_count = self.text_edits.modified_count if self.text_edits else 0
        audio_count = len(self._audio_edits)
        crib_count = len(self._crib_edits)
        crib_geometry_count = len(self._crib_geometry_edits)
        stadium_count = len(self._stadium_edits)
        stadium_geometry_count = int(self._stadium_geometry_edit is not None)
        annotation_count = len(self._audio_annotations)
        colour_count = len(self._unif_colors)
        play_route_count = len(self._play_route_edits)
        if (
            not self._edits and not text_count and not audio_count
            and not crib_count and not stadium_count and not annotation_count
            and not crib_geometry_count
            and not stadium_geometry_count and not colour_count
            and not play_route_count
        ):
            return 0
        previous_unif_colors = dict(self._unif_colors)
        previous_play_routes = dict(self._play_route_edits)
        self._unif_colors = {}
        self._play_route_edits = {}
        # Revert All is one transaction across every editor. Replacement bytes
        # remain in place until the empty manifest commits; on any failure the
        # new history snapshots and ledgers are removed and the live edit maps
        # are restored exactly. This matters for mixed projects: a cue label
        # must never disappear while a PNG/WAV edit remains (or vice versa).
        history_sequence = self._history_sequence
        undo_length = len(self._undo)
        crib_undo_length = len(self._crib_undo)
        stadium_undo_length = len(self._stadium_undo)
        order_length = len(self._undo_order)
        snapshot_paths: list[Path] = []
        items: list[_UndoItem] = []
        audio_snapshots: tuple[tuple[Any, ...], ...] = ()
        crib_items: list[_UndoItem] = []
        stadium_items: list[_UndoItem] = []
        text_snapshot = (
            self.text_edits.replacement_document()
            if self.text_edits is not None and text_count else None
        )
        annotation_snapshot = self.audio_annotations
        try:
            for asset_id in sorted(self._edits):
                snapshot = self._snapshot_previous(asset_id)
                assert snapshot is not None
                snapshot_paths.append(snapshot)
                items.append(_UndoItem(asset_id, snapshot))
            if audio_count:
                staged_audio: list[tuple[Any, ...]] = []
                audio_service = self._require_audio_service()
                for asset_id in sorted(self._audio_edits):
                    edit = self._audio_edits[asset_id]
                    if self._uses_immutable_audio_gate(audio_service):
                        self._authorize_audio_path(
                            edit.asset_id, edit.replacement_path
                        )
                    snapshot = self._snapshot_audio(asset_id)
                    assert snapshot is not None
                    snapshot_paths.append(snapshot)
                    if self._uses_immutable_audio_gate(audio_service):
                        staged_audio.append((
                            asset_id, snapshot, edit.asset_id,
                            edit.affected_asset_ids,
                        ))
                    else:
                        staged_audio.append((asset_id, snapshot))
                audio_snapshots = tuple(staged_audio)
            for asset_id in sorted(self._crib_edits):
                snapshot = self._snapshot_crib(asset_id)
                assert snapshot is not None
                snapshot_paths.append(snapshot)
                crib_items.append(_UndoItem(asset_id, snapshot))
            for asset_id in sorted(self._stadium_edits):
                snapshot = self._snapshot_stadium(asset_id)
                assert snapshot is not None
                snapshot_paths.append(snapshot)
                stadium_items.append(_UndoItem(asset_id, snapshot))
        except BaseException:
            self._unif_colors = previous_unif_colors
            self._play_route_edits = previous_play_routes
            for snapshot in snapshot_paths:
                snapshot.unlink(missing_ok=True)
            self._history_sequence = history_sequence
            raise

        previous_edits = self._edits
        previous_text_edits = self.text_edits
        previous_audio_edits = self._audio_edits
        previous_crib_edits = self._crib_edits
        previous_crib_geometry_edits = self._crib_geometry_edits
        previous_stadium_edits = self._stadium_edits
        previous_stadium_geometry_edit = self._stadium_geometry_edit
        previous_annotations = self._audio_annotations
        self._edits = {}
        if text_snapshot is not None:
            self.text_edits = Nfl2k5TextEdits(self.text_catalog)  # type: ignore[arg-type]
        self._audio_edits = {}
        self._crib_edits = {}
        self._crib_geometry_edits = {}
        self._stadium_edits = {}
        self._stadium_geometry_edit = None
        self._audio_annotations = {}
        if items:
            self._undo.append(_UndoAction("Revert all assets", tuple(items)))
        if crib_items:
            self._crib_undo.append(
                _UndoAction("Revert all assets", tuple(crib_items))
            )
        if stadium_items:
            self._stadium_undo.append(
                _UndoAction("Revert all assets", tuple(stadium_items))
            )
        self._undo_order.append(_SessionUndo(
            "revert_all", "Revert all assets",
            (
                bool(items), text_snapshot, audio_snapshots, bool(crib_items),
                bool(stadium_items), previous_crib_geometry_edits,
                previous_stadium_geometry_edit,
                annotation_snapshot, previous_unif_colors,
                previous_play_routes,
            ),
        ))
        try:
            self._write_manifest()
        except BaseException:
            self._edits = previous_edits
            self.text_edits = previous_text_edits
            self._audio_edits = previous_audio_edits
            self._crib_edits = previous_crib_edits
            self._crib_geometry_edits = previous_crib_geometry_edits
            self._stadium_edits = previous_stadium_edits
            self._stadium_geometry_edit = previous_stadium_geometry_edit
            self._audio_annotations = previous_annotations
            self._unif_colors = previous_unif_colors
            self._play_route_edits = previous_play_routes
            del self._undo[undo_length:]
            del self._crib_undo[crib_undo_length:]
            del self._stadium_undo[stadium_undo_length:]
            del self._undo_order[order_length:]
            for snapshot in snapshot_paths:
                snapshot.unlink(missing_ok=True)
            self._history_sequence = history_sequence
            raise

        # Only a committed empty manifest authorizes removal of the previous
        # working files. Their history copies remain until Undo succeeds.
        for edit in previous_edits.values():
            edit.replacement_path.unlink(missing_ok=True)
        for edit in previous_audio_edits.values():
            edit.replacement_path.unlink(missing_ok=True)
        for edit in previous_crib_edits.values():
            edit.replacement_path.unlink(missing_ok=True)
        for edit in previous_stadium_edits.values():
            self._remove_stadium_edit_files(edit)
        return (
            len(items) + text_count + audio_count + crib_count + stadium_count
            + crib_geometry_count + stadium_geometry_count
            + annotation_count + colour_count
            + play_route_count
        )

    def undo(self) -> str | None:
        if not self._undo_order:
            return None
        record = self._undo_order[-1]
        if record.source == "audio":
            # Audio actions can span many cue files. Keep both Undo ledgers in
            # place until every file and the session manifest commit together.
            self._undo_audio_action(expected_label=record.label)
            self._undo_order.pop()
            return record.label
        if record.source == "audio_annotation":
            cue_id, previous = record.payload  # type: ignore[misc]
            current = self._audio_annotations.get(cue_id)
            if previous is None:
                self._audio_annotations.pop(cue_id, None)
            else:
                self._audio_annotations[cue_id] = previous
            try:
                self._write_manifest()
            except BaseException:
                if current is None:
                    self._audio_annotations.pop(cue_id, None)
                else:
                    self._audio_annotations[cue_id] = current
                raise
            self._undo_order.pop()
            return record.label
        if record.source == "play_route":
            selector, previous = record.payload  # type: ignore[misc]
            current = self._play_route_edits.get(selector)
            if previous is None:
                self._play_route_edits.pop(selector, None)
            else:
                self._play_route_edits[selector] = previous
            try:
                self._write_manifest()
            except BaseException:
                if current is None:
                    self._play_route_edits.pop(selector, None)
                else:
                    self._play_route_edits[selector] = current
                raise
            self._undo_order.pop()
            return record.label
        if record.source == "formation_create":
            selector, previous = record.payload  # type: ignore[misc]
            current = self._formation_creates.get(selector)
            if previous is None:
                self._formation_creates.pop(selector, None)
            else:
                self._formation_creates[selector] = previous
            try:
                self._write_manifest()
            except BaseException:
                if current is None:
                    self._formation_creates.pop(selector, None)
                else:
                    self._formation_creates[selector] = current
                raise
            self._undo_order.pop()
            return record.label
        if record.source == "play_create":
            selector, previous = record.payload  # type: ignore[misc]
            current = self._play_creates.get(selector)
            if previous is None:
                self._play_creates.pop(selector, None)
            else:
                self._play_creates[selector] = previous
            try:
                self._write_manifest()
            except BaseException:
                if current is None:
                    self._play_creates.pop(selector, None)
                else:
                    self._play_creates[selector] = current
                raise
            self._undo_order.pop()
            return record.label
        if record.source == "revert_all":
            self._undo_revert_all_transaction(record)
            self._undo_order.pop()
            return record.label
        if record.source == "uniform_color":
            selector, previous = record.payload  # type: ignore[misc]
            current = self._unif_colors.get(selector)
            if previous is None:
                self._unif_colors.pop(selector, None)
            else:
                self._unif_colors[selector] = previous
            try:
                self._write_manifest()
            except BaseException:
                if current is None:
                    self._unif_colors.pop(selector, None)
                else:
                    self._unif_colors[selector] = current
                raise
            self._undo_order.pop()
            return record.label
        if record.source == "stadium_geometry":
            current = self._stadium_geometry_edit
            previous = record.payload
            if previous is not None and not isinstance(
                previous, StadiumGeometrySessionEdit
            ):
                raise ValidationError(
                    "The Stadium geometry undo history is inconsistent."
                )
            self._stadium_geometry_edit = previous
            try:
                self._write_manifest()
            except BaseException:
                self._stadium_geometry_edit = current
                raise
            self._undo_order.pop()
            if current is not None and (
                previous is None or current.recipe_path != previous.recipe_path
            ):
                current.recipe_path.unlink(missing_ok=True)
            return record.label
        if record.source == "crib_geometry":
            scene_id, previous = record.payload  # type: ignore[misc]
            current = self._crib_geometry_edits.get(scene_id)
            if previous is not None and not isinstance(
                previous, CribGeometrySessionEdit
            ):
                raise ValidationError(
                    "The Crib geometry undo history is inconsistent."
                )
            if previous is None:
                self._crib_geometry_edits.pop(scene_id, None)
            else:
                self._crib_geometry_edits[scene_id] = previous
            try:
                self._write_manifest()
            except BaseException:
                if current is None:
                    self._crib_geometry_edits.pop(scene_id, None)
                else:
                    self._crib_geometry_edits[scene_id] = current
                raise
            self._undo_order.pop()
            if current is not None and (
                previous is None or current.recipe_path != previous.recipe_path
            ):
                current.recipe_path.unlink(missing_ok=True)
            return record.label
        record = self._undo_order.pop()
        if record.source == "text":
            if self.text_edits is None or not self.text_edits.undo():
                raise ValidationError("The text undo history is inconsistent.")
            self._write_manifest()
            return record.label
        if record.source == "crib":
            self._undo_crib_action()
            self._write_manifest()
            return record.label
        if record.source == "stadium":
            self._undo_stadium_action()
            self._write_manifest()
            return record.label
        self._undo_visual_action()
        self._write_manifest()
        return record.label

    def _undo_revert_all_transaction(self, record: _SessionUndo) -> None:
        """Restore one Revert-All snapshot without consuming it before commit."""

        (
            has_visual, text_snapshot, audio_snapshots, has_crib, has_stadium,
            crib_geometry_snapshot, stadium_geometry_snapshot, annotation_snapshot,
            uniform_color_snapshot,
            play_route_snapshot,
        ) = record.payload  # type: ignore[misc]
        if self.modified_count or self._audio_annotations:
            raise ValidationError(
                "Revert-All undo history conflicts with current project changes."
            )
        visual_action = self._undo[-1] if has_visual and self._undo else None
        crib_action = self._crib_undo[-1] if has_crib and self._crib_undo else None
        stadium_action = (
            self._stadium_undo[-1]
            if has_stadium and self._stadium_undo else None
        )
        if has_visual and visual_action is None:
            raise ValidationError("The visual Revert-All history is inconsistent.")
        if has_crib and crib_action is None:
            raise ValidationError("The Crib Revert-All history is inconsistent.")
        if has_stadium and stadium_action is None:
            raise ValidationError("The Stadium Revert-All history is inconsistent.")

        restored_text: Nfl2k5TextEdits | None = self.text_edits
        if text_snapshot is not None:
            if self.text_catalog is None:
                raise ValidationError("The text catalog is unavailable for undo.")
            restored_text = Nfl2k5TextEdits(self.text_catalog)
            restored_text.load_replacement_document(text_snapshot)

        visual_plan: list[tuple[_UndoItem, bytes, bytes, Path]] = []
        for item in visual_action.items if visual_action is not None else ():
            if item.previous_snapshot is None:
                raise ValidationError("The visual Revert-All snapshot is missing.")
            asset = self._visual_asset(item.asset_id)
            payload, rgba = self.asset_io.validate_replacement(
                asset, item.previous_snapshot
            )
            destination = self.replacements / f"{_asset_key(item.asset_id)}.png"
            if destination.exists():
                raise ValidationError(
                    "The visual Revert-All destination is unexpectedly occupied."
                )
            visual_plan.append((item, payload, rgba, destination))

        crib_plan: list[tuple[_UndoItem, bytes, bytes, Path]] = []
        for item in crib_action.items if crib_action is not None else ():
            if item.previous_snapshot is None:
                raise ValidationError("The Crib Revert-All snapshot is missing.")
            asset = self._require_crib_catalog().get(item.asset_id)
            payload, rgba = self._require_crib_io().validate_replacement(
                asset, item.previous_snapshot
            )
            destination = self.replacements / f"{_asset_key(item.asset_id)}.png"
            if destination.exists():
                raise ValidationError(
                    "The Crib Revert-All destination is unexpectedly occupied."
                )
            crib_plan.append((item, payload, rgba, destination))

        stadium_plan: list[tuple[_UndoItem, StadiumTexture, bytes, bytes,
                                  CompiledStadiumTextureEdit]] = []
        writer = self._require_stadium_writer() if stadium_action is not None else None
        for item in stadium_action.items if stadium_action is not None else ():
            if item.previous_snapshot is None or writer is None:
                raise ValidationError("The Stadium Revert-All snapshot is missing.")
            texture = self._stadium_texture_for_id(item.asset_id)
            payload, rgba, compiled = writer.validated_replacement(
                texture, item.previous_snapshot
            )
            stadium_plan.append((item, texture, payload, rgba, compiled))

        service = self._require_audio_service() if audio_snapshots else None
        prepared_audio: list[tuple[str, Path, str, tuple[str, ...], bytes, str]] = []
        if service is not None and self._uses_immutable_audio_gate(service):
            for state_id, snapshot, logical_id, affected in audio_snapshots:
                asset = service.resolve_editable_audio(logical_id)
                if service.audio_physical_id(asset) != state_id:
                    raise ValidationError(
                        "Revert-All audio history no longer resolves to its physical slot."
                    )
                checked = service.read_replacement_snapshot(asset, snapshot)
                issued = service.authorize_replacement_snapshot(asset, checked)
                prepared_audio.append((
                    state_id, snapshot, logical_id, affected,
                    issued.wav_bytes, issued.wav_sha256,
                ))
        elif service is not None:
            for asset_id, snapshot in audio_snapshots:
                asset = service.catalog.get_asset(asset_id)
                service.validate_user_replacement(asset, snapshot)
                payload = snapshot.read_bytes()
                prepared_audio.append((
                    asset_id, snapshot, asset_id, (), payload,
                    sha256_bytes(payload),
                ))

        written_paths: list[Path] = []
        restored_stadium: dict[str, StadiumSessionEdit] = {}
        try:
            restored_visual: dict[str, SessionEdit] = {}
            for item, payload, rgba, destination in visual_plan:
                _replace_atomic(destination, payload)
                written_paths.append(destination)
                restored_visual[item.asset_id] = SessionEdit(
                    item.asset_id, destination,
                    sha256_bytes(payload), sha256_bytes(rgba),
                )
            restored_audio: dict[str, AudioSessionEdit] = {}
            for state_id, _snapshot, logical_id, affected, payload, digest in prepared_audio:
                destination = self.replacements / f"{_asset_key(state_id)}.wav"
                if destination.exists():
                    raise ValidationError(
                        "The audio Revert-All destination is unexpectedly occupied."
                    )
                _replace_atomic(destination, payload)
                written_paths.append(destination)
                restored_audio[state_id] = AudioSessionEdit(
                    logical_id, destination, digest, state_id, affected
                )
            restored_crib: dict[str, SessionEdit] = {}
            for item, payload, rgba, destination in crib_plan:
                _replace_atomic(destination, payload)
                written_paths.append(destination)
                restored_crib[item.asset_id] = SessionEdit(
                    item.asset_id, destination,
                    sha256_bytes(payload), sha256_bytes(rgba),
                )
            for item, texture, payload, rgba, compiled in stadium_plan:
                staged = self._stage_stadium_edit(
                    texture, payload, rgba, compiled
                )
                restored_stadium[item.asset_id] = staged
                written_paths.extend((staged.replacement_path, staged.preview_path))

            previous_text = self.text_edits
            previous_annotations = self._audio_annotations
            previous_unif_colors = self._unif_colors
            previous_crib_geometry = self._crib_geometry_edits
            previous_stadium_geometry = self._stadium_geometry_edit
            previous_play_routes = self._play_route_edits
            self._edits = restored_visual
            self.text_edits = restored_text
            self._audio_edits = restored_audio
            self._crib_edits = restored_crib
            self._crib_geometry_edits = dict(crib_geometry_snapshot)
            self._stadium_edits = restored_stadium
            self._stadium_geometry_edit = stadium_geometry_snapshot
            self._audio_annotations = {
                annotation.cue_id: annotation
                for annotation in annotation_snapshot
            }
            self._unif_colors = dict(uniform_color_snapshot)
            self._play_route_edits = dict(play_route_snapshot)
            try:
                self._write_manifest()
            except BaseException:
                self._edits = {}
                self.text_edits = previous_text
                self._audio_edits = {}
                self._crib_edits = {}
                self._crib_geometry_edits = previous_crib_geometry
                self._stadium_edits = {}
                self._stadium_geometry_edit = previous_stadium_geometry
                self._audio_annotations = previous_annotations
                self._unif_colors = previous_unif_colors
                self._play_route_edits = previous_play_routes
                raise
        except BaseException:
            for path in written_paths:
                path.unlink(missing_ok=True)
            raise

        if has_visual:
            self._undo.pop()
        if has_crib:
            self._crib_undo.pop()
        if has_stadium:
            self._stadium_undo.pop()
        snapshot_paths = [
            item.previous_snapshot
            for action in (visual_action, crib_action, stadium_action)
            if action is not None
            for item in action.items
            if item.previous_snapshot is not None
        ] + [row[1] for row in audio_snapshots]
        for snapshot in snapshot_paths:
            try:
                snapshot.unlink(missing_ok=True)
            except OSError:
                pass

    def _undo_visual_action(self) -> None:
        if not self._undo:
            raise ValidationError("The visual undo history is inconsistent.")
        action = self._undo.pop()
        for item in action.items:
            current = self._edits.pop(item.asset_id, None)
            if current is not None:
                current.replacement_path.unlink(missing_ok=True)
            if item.previous_snapshot is not None:
                asset = self._visual_asset(item.asset_id)
                payload, rgba = self.asset_io.validate_replacement(
                    asset, item.previous_snapshot
                )
                destination = self.replacements / f"{_asset_key(item.asset_id)}.png"
                copy_user_asset_atomic(item.previous_snapshot, destination)
                self._edits[item.asset_id] = SessionEdit(
                    item.asset_id,
                    destination,
                    sha256_bytes(payload),
                    sha256_bytes(rgba),
                )
                item.previous_snapshot.unlink(missing_ok=True)

    def _undo_crib_action(self) -> None:
        if not self._crib_undo:
            raise ValidationError("The Crib undo history is inconsistent.")
        action = self._crib_undo.pop()
        for item in action.items:
            current = self._crib_edits.pop(item.asset_id, None)
            if current is not None:
                current.replacement_path.unlink(missing_ok=True)
            if item.previous_snapshot is not None:
                asset = self._require_crib_catalog().get(item.asset_id)
                payload, rgba = self._require_crib_io().validate_replacement(
                    asset, item.previous_snapshot
                )
                destination = self.replacements / f"{_asset_key(item.asset_id)}.png"
                copy_user_asset_atomic(item.previous_snapshot, destination)
                self._crib_edits[item.asset_id] = SessionEdit(
                    item.asset_id, destination,
                    sha256_bytes(payload), sha256_bytes(rgba),
                )
                item.previous_snapshot.unlink(missing_ok=True)

    def _undo_stadium_action(self) -> None:
        if not self._stadium_undo:
            raise ValidationError("The Stadium undo history is inconsistent.")
        action = self._stadium_undo.pop()
        writer = self._require_stadium_writer()
        for item in action.items:
            texture = self._stadium_texture_for_id(item.asset_id)
            current = self._stadium_edits.pop(item.asset_id, None)
            if current is not None:
                self._remove_stadium_edit_files(current)
            if item.previous_snapshot is not None:
                payload, rgba, compiled = writer.validated_replacement(
                    texture, item.previous_snapshot
                )
                self._stadium_edits[item.asset_id] = self._stage_stadium_edit(
                    texture, payload, rgba, compiled
                )
                item.previous_snapshot.unlink(missing_ok=True)

    def text_value(self, asset_id: str) -> str:
        return self._require_text_edits().value(asset_id)

    def number_value(self, asset_id: str) -> int:
        return self._require_text_edits().number(asset_id)

    def set_text(self, asset: TextAsset | str, value: str) -> ReplaceResult:
        edits = self._require_text_edits()
        asset_id = asset.asset_id if isinstance(asset, TextAsset) else asset
        selected = self._require_text_catalog().get_asset(asset_id)
        before = edits.value(asset_id)
        edits.set_text(asset_id, value)
        after = edits.value(asset_id)
        if before != after:
            self._undo_order.append(_SessionUndo("text", f"Edit {selected.label}"))
        self._write_manifest()
        return ReplaceResult(
            asset_id, asset_id in self.modified_asset_ids,
            f"{selected.label} is ready to build."
            if asset_id in self.modified_asset_ids else
            f"{selected.label} was restored to its original value.",
        )

    def set_number(
        self, asset: RosterNumberAsset | str, value: int
    ) -> ReplaceResult:
        edits = self._require_text_edits()
        asset_id = asset.asset_id if isinstance(asset, RosterNumberAsset) else asset
        selected = self._require_text_catalog().get_number_asset(asset_id)
        before = edits.number(asset_id)
        edits.set_number(asset_id, value)
        after = edits.number(asset_id)
        if before != after:
            self._undo_order.append(_SessionUndo("text", f"Edit {selected.label}"))
        self._write_manifest()
        return ReplaceResult(
            asset_id, asset_id in self.modified_asset_ids,
            f"{selected.label} is ready to build."
            if asset_id in self.modified_asset_ids else
            f"{selected.label} was restored to its original value.",
        )

    def revert_text(self, asset_id: str) -> bool:
        edits = self._require_text_edits()
        if asset_id not in self.modified_asset_ids:
            return False
        edits.revert(asset_id)
        self._undo_order.append(_SessionUndo("text", f"Revert {asset_id}"))
        self._write_manifest()
        return True

    def current_crib_path(self, asset: CribAsset | str) -> Path:
        selected = (
            self._require_crib_catalog().get(asset)
            if isinstance(asset, str) else asset
        )
        edit = self._crib_edits.get(selected.asset_id)
        return edit.replacement_path if edit else self._require_crib_io().ensure_original(
            selected
        )

    def export_crib(self, asset: CribAsset | str, destination: Path) -> Path:
        selected = (
            self._require_crib_catalog().get(asset)
            if isinstance(asset, str) else asset
        )
        edit = self._crib_edits.get(selected.asset_id)
        if edit is None:
            return self._require_crib_io().export_original(selected, destination)
        requested = destination.expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        return _write_new_atomic(
            requested, edit.replacement_path.read_bytes()
        ).resolve(strict=True)

    def replace_crib(
        self, asset: CribAsset | str, supplied_png: Path
    ) -> ReplaceResult:
        selected = (
            self._require_crib_catalog().get(asset)
            if isinstance(asset, str) else asset
        )
        io = self._require_crib_io()
        original_path = io.ensure_original(selected)
        _original_payload, original_rgba = io.validate_replacement(
            selected, original_path
        )
        payload, rgba = io.validate_replacement(selected, supplied_png)
        previous = self._snapshot_crib(selected.asset_id)
        if rgba == original_rgba:
            current = self._crib_edits.pop(selected.asset_id, None)
            if current is not None:
                current.replacement_path.unlink(missing_ok=True)
            self._crib_undo.append(_UndoAction(
                f"Restore {selected.label}",
                (_UndoItem(selected.asset_id, previous),),
            ))
            self._undo_order.append(
                _SessionUndo("crib", f"Restore {selected.label}")
            )
            self._write_manifest()
            return ReplaceResult(
                selected.asset_id, False,
                "That PNG matches the original pixels, so the photo was reverted.",
            )
        destination = self.replacements / f"{_asset_key(selected.asset_id)}.png"
        _replace_atomic(destination, payload)
        self._crib_edits[selected.asset_id] = SessionEdit(
            selected.asset_id, destination,
            sha256_bytes(payload), sha256_bytes(rgba),
        )
        self._crib_undo.append(_UndoAction(
            f"Replace {selected.label}",
            (_UndoItem(selected.asset_id, previous),),
        ))
        self._undo_order.append(
            _SessionUndo("crib", f"Replace {selected.label}")
        )
        self._write_manifest()
        return ReplaceResult(
            selected.asset_id, True, f"{selected.label} is ready to build."
        )

    def revert_crib(self, asset: CribAsset | str) -> bool:
        selected = (
            self._require_crib_catalog().get(asset)
            if isinstance(asset, str) else asset
        )
        current = self._crib_edits.get(selected.asset_id)
        if current is None:
            return False
        previous = self._snapshot_crib(selected.asset_id)
        current.replacement_path.unlink(missing_ok=True)
        del self._crib_edits[selected.asset_id]
        self._crib_undo.append(_UndoAction(
            f"Revert {selected.label}",
            (_UndoItem(selected.asset_id, previous),),
        ))
        self._undo_order.append(_SessionUndo("crib", f"Revert {selected.label}"))
        self._write_manifest()
        return True

    def _crib_geometry_texture_edits(
        self, scene_id: str
    ) -> tuple[tuple[str, Path], ...]:
        """Return staged P8 edits sharing the geometry scene's one SCNE."""

        scene_rows = {
            str(row["scene_id"]): row
            for row in list_editable_crib_geometry_scenes()
        }
        scene = scene_rows.get(scene_id)
        if scene is None:
            raise ValidationError(
                "That Crib scene is export-only because its bounded position "
                "catalog is unavailable."
            )
        chunk_index = int(scene["chunk_index"])
        catalog = self._require_crib_catalog()
        rows: list[tuple[str, Path]] = []
        for asset_id, edit in sorted(self._crib_edits.items()):
            asset = catalog.get(asset_id)
            if asset.storage == "scene_embedded" and asset.chunk_index == chunk_index:
                rows.append((asset.selector, edit.replacement_path))
        return tuple(rows)

    def replace_crib_geometry(
        self, compiled: CompiledCribGeometryRecipe
    ) -> ReplaceResult:
        """Preflight and stage one bounded Crib position-only recipe."""

        editable_scene_ids = {
            str(row["scene_id"])
            for row in list_editable_crib_geometry_scenes()
        }
        if (
            not isinstance(compiled, CompiledCribGeometryRecipe)
            or compiled.scene_id not in editable_scene_ids
            or sha256_bytes(compiled.recipe) != compiled.recipe_sha256
            or compiled.changed_target_count <= 0
            or compiled.changed_vertex_count <= 0
            or compiled.preserved_triangle_count <= 0
        ):
            raise ValidationError(
                "The compiled Crib geometry recipe changed before staging."
            )
        current = self._crib_geometry_edits.get(compiled.scene_id)
        if current is not None and current.recipe_sha256 == compiled.recipe_sha256:
            return ReplaceResult(
                current.asset_id, True, "That edited Crib model is already staged."
            )

        key = _asset_key(f"{compiled.scene_id}.geometry")
        destination = self.replacements / f"{key}-{uuid4().hex}.geometry.json"
        _write_new_atomic(destination, compiled.recipe)
        try:
            # A recipe is accepted only when the exact current source and every
            # staged same-SCNE P8 edit fit one deterministic fixed allocation.
            build_unified_crib_geometry_import(
                self.cache.pack0,
                self.cache.inventory,
                destination,
                self._crib_geometry_texture_edits(compiled.scene_id),
            )
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

        staged = CribGeometrySessionEdit(
            compiled.scene_id,
            destination,
            compiled.recipe_sha256,
            compiled.changed_target_count,
            compiled.changed_vertex_count,
            compiled.preserved_triangle_count,
        )
        self._crib_geometry_edits[compiled.scene_id] = staged
        self._undo_order.append(_SessionUndo(
            "crib_geometry",
            "Import edited Crib model",
            (compiled.scene_id, current),
        ))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            if current is None:
                self._crib_geometry_edits.pop(compiled.scene_id, None)
            else:
                self._crib_geometry_edits[compiled.scene_id] = current
            destination.unlink(missing_ok=True)
            raise
        return ReplaceResult(
            staged.asset_id,
            True,
            f"Crib geometry is ready to build: {staged.changed_vertex_count:,} "
            f"vertices across {staged.changed_target_count} fixed target(s).",
        )

    def revert_crib_geometry(self, scene_id: str) -> bool:
        """Revert one staged Crib model while keeping its Undo recipe private."""

        current = self._crib_geometry_edits.pop(scene_id, None)
        if current is None:
            return False
        self._undo_order.append(_SessionUndo(
            "crib_geometry", "Revert edited Crib model", (scene_id, current)
        ))
        try:
            self._write_manifest()
        except BaseException:
            self._undo_order.pop()
            self._crib_geometry_edits[scene_id] = current
            raise
        return True

    @staticmethod
    def _uses_immutable_audio_gate(service: Any) -> bool:
        return isinstance(service, Nfl2k5AudioService)

    def _select_audio_target(self, asset: Any) -> Any:
        service = self._require_audio_service()
        if self._uses_immutable_audio_gate(service):
            return service.resolve_editable_audio(asset)
        return service.catalog.get_asset(asset)

    def _select_playable_audio_target(self, asset: Any) -> Any:
        """Resolve standalone/range playback without requiring editability."""

        service = self._require_audio_service()
        if not self._uses_immutable_audio_gate(service):
            return service.catalog.get_asset(asset)
        if isinstance(asset, Nfl2k5AudioAsset):
            return service.catalog.get_asset(asset)
        if isinstance(asset, Nfl2k5StreamingAudioRange):
            return service.catalog.get_streaming_range(asset)
        if isinstance(asset, str):
            try:
                return service.catalog.get_asset(asset)
            except ValidationError:
                return service.catalog.get_streaming_range(asset)
        raise ValidationError("Unknown playable audio asset.")

    def _audio_state_id(self, asset: Any) -> str:
        service = self._require_audio_service()
        selected = self._select_playable_audio_target(asset)
        if (
            self._uses_immutable_audio_gate(service)
            and isinstance(selected, Nfl2k5StreamingAudioRange)
        ):
            return service.audio_physical_id(selected)
        return selected.asset_id

    def _audio_affected_ids(self, asset: Any) -> tuple[str, ...]:
        service = self._require_audio_service()
        selected = self._select_audio_target(asset)
        if self._uses_immutable_audio_gate(service):
            return service.audio_affected_asset_ids(selected)
        return (selected.asset_id,)

    def _audio_original_path(self, asset: Any) -> Path:
        service = self._require_audio_service()
        selected = self._select_audio_target(asset)
        if self._uses_immutable_audio_gate(service):
            return service.audio_original_path(selected)
        return service.ensure_original(selected)

    def _authorize_audio_path(self, asset: Any, path: Path) -> tuple[Any, Any]:
        """Read once, authorize that exact snapshot, and return both."""

        service = self._require_audio_service()
        selected = self._select_audio_target(asset)
        if not self._uses_immutable_audio_gate(service):
            metadata = service.validate_user_replacement(selected, path)
            return metadata, None
        snapshot = service.read_replacement_snapshot(selected, path)
        issued = service.authorize_replacement_snapshot(selected, snapshot)
        if issued.wav_sha256 != snapshot.metadata.wav_sha256:
            raise ValidationError(
                f"The staged WAV for {selected.name} changed during authorization."
            )
        return snapshot, issued

    def current_audio_path(
        self,
        asset: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange | str,
    ) -> Path:
        service = self._require_audio_service()
        selected = self._select_playable_audio_target(asset)
        state_id = self._audio_state_id(selected)
        edit = self._audio_edits.get(state_id)
        if edit is None:
            if self._uses_immutable_audio_gate(service):
                return service.audio_playback_path(selected)
            return service.playback_path(selected)
        try:
            checked, issued = self._authorize_audio_path(
                selected, edit.replacement_path
            )
        except ValidationError as exc:
            raise ValidationError(
                f"The staged WAV for {selected.name} changed outside Mod Studio. "
                "Replace it again before playing or exporting it. "
                f"{exc}"
            ) from exc
        checked_sha256 = (
            issued.wav_sha256 if issued is not None else checked.wav_sha256
        )
        if checked_sha256 != edit.replacement_sha256:
            raise ValidationError(
                f"The staged WAV for {selected.name} changed outside Mod Studio. "
                "Replace it again before playing or exporting it."
            )
        return edit.replacement_path

    def audio_content_origin(
        self,
        asset: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange | str,
    ) -> str:
        """Identify whether the current playable WAV is source-derived or staged."""

        service = self._require_audio_service()
        selected = self._select_playable_audio_target(asset)
        if self._audio_state_id(selected) not in self._audio_edits:
            return "retail_derived"
        # Reuse the same checksum/contract check used by Play and Export so the
        # bundle manifest cannot label an externally changed file as the staged
        # project replacement.
        self.current_audio_path(selected)
        return "user_replacement"

    def export_audio(
        self,
        asset: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange | str,
        destination: Path,
    ) -> Path:
        service = self._require_audio_service()
        selected = self._select_playable_audio_target(asset)
        edit = self._audio_edits.get(self._audio_state_id(selected))
        if edit is None:
            if isinstance(selected, Nfl2k5StreamingAudioRange):
                return service.export_streaming_range_wav(selected, destination)
            return service.export_wav(selected, destination)
        current = self.current_audio_path(selected)
        requested = destination.expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        return _write_new_atomic(requested, current.read_bytes()).resolve(
            strict=True
        )

    def replace_audio(
        self,
        asset: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange | str,
        supplied_wav: Path,
    ) -> ReplaceResult:
        service = self._require_audio_service()
        if self._uses_immutable_audio_gate(service):
            return self._replace_authorized_audio(asset, supplied_wav)
        selected = service.catalog.get_asset(asset)
        metadata = service.validate_replacement(selected, supplied_wav)
        payload = metadata.wav_path.read_bytes()
        if sha256_bytes(payload) != metadata.wav_sha256:
            raise ValidationError(
                f"The supplied WAV for {selected.name} changed while it was checked."
            )
        original = service.ensure_original(selected).read_bytes()
        if payload == original:
            previous = self._snapshot_audio(selected.asset_id)
            current = self._audio_edits.pop(selected.asset_id, None)
            if current is not None:
                current.replacement_path.unlink(missing_ok=True)
            if current is not None or previous is not None:
                self._audio_undo.append(_UndoAction(
                    f"Restore {selected.name}",
                    (_UndoItem(selected.asset_id, previous),),
                ))
                self._undo_order.append(
                    _SessionUndo("audio", f"Restore {selected.name}")
                )
            self._write_manifest()
            return ReplaceResult(
                selected.asset_id, False,
                "That WAV matches the original cue, so the audio was reverted.",
            )
        metadata = service.validate_user_replacement(selected, supplied_wav)
        payload = metadata.wav_path.read_bytes()
        if sha256_bytes(payload) != metadata.wav_sha256:
            raise ValidationError(
                f"The supplied WAV for {selected.name} changed while it was checked."
            )
        previous = self._snapshot_audio(selected.asset_id)
        destination = self.replacements / f"{_asset_key(selected.asset_id)}.wav"
        _replace_atomic(destination, payload)
        staged = service.validate_user_replacement(selected, destination)
        self._audio_edits[selected.asset_id] = AudioSessionEdit(
            selected.asset_id, staged.wav_path, staged.wav_sha256
        )
        self._audio_undo.append(_UndoAction(
            f"Replace {selected.name}",
            (_UndoItem(selected.asset_id, previous),),
        ))
        self._undo_order.append(_SessionUndo("audio", f"Replace {selected.name}"))
        self._write_manifest()
        return ReplaceResult(
            selected.asset_id, True, f"{selected.name} is ready to build."
        )

    def _replace_authorized_audio(
        self,
        asset: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange | str,
        supplied_wav: Path,
    ) -> ReplaceResult:
        """Stage one exact authorized snapshot under its physical edit key."""

        service = self._require_audio_service()
        assert isinstance(service, Nfl2k5AudioService)
        selected = service.resolve_editable_audio(asset)
        snapshot = service.read_replacement_snapshot(selected, supplied_wav)
        payload = snapshot.wav_bytes
        state_id = service.audio_physical_id(selected)
        affected_ids = service.audio_affected_asset_ids(selected)
        original = service.audio_original_path(selected).read_bytes()

        current = self._audio_edits.get(state_id)
        if payload == original:
            if current is None:
                return ReplaceResult(
                    selected.asset_id,
                    False,
                    "That WAV matches the original cue; nothing is modified.",
                )
            # Validate the live authored state before snapshotting it for Undo.
            self._authorize_audio_path(selected, current.replacement_path)
            previous = self._snapshot_audio(state_id)
            current.replacement_path.unlink(missing_ok=True)
            del self._audio_edits[state_id]
            label = f"Restore {selected.name}"
            self._audio_undo.append(_UndoAction(
                label,
                (_UndoItem(
                    state_id,
                    previous,
                    current.asset_id,
                    current.affected_asset_ids or affected_ids,
                ),),
            ))
            self._undo_order.append(_SessionUndo("audio", label))
            self._write_manifest()
            return ReplaceResult(
                selected.asset_id,
                False,
                "That WAV matches the original cue, so every linked alias was reverted.",
            )

        issued = service.authorize_replacement_snapshot(selected, snapshot)
        if current is not None:
            _current_snapshot, current_issued = self._authorize_audio_path(
                selected, current.replacement_path
            )
            assert current_issued is not None
            if current_issued.wav_bytes == issued.wav_bytes:
                return ReplaceResult(
                    selected.asset_id,
                    True,
                    "That WAV is already staged for this physical slot and all linked aliases.",
                )
        previous = self._snapshot_audio(state_id)
        prior_logical_id = current.asset_id if current is not None else selected.asset_id
        prior_affected = (
            current.affected_asset_ids if current is not None
            else affected_ids
        )
        destination = self.replacements / f"{_asset_key(state_id)}.wav"
        _replace_atomic(destination, issued.wav_bytes)
        self._audio_edits[state_id] = AudioSessionEdit(
            selected.asset_id,
            destination,
            issued.wav_sha256,
            state_id,
            affected_ids,
        )
        label = f"Replace {selected.name}"
        self._audio_undo.append(_UndoAction(
            label,
            (_UndoItem(
                state_id,
                previous,
                prior_logical_id,
                prior_affected,
            ),),
        ))
        self._undo_order.append(_SessionUndo("audio", label))
        self._write_manifest()
        linked = len(affected_ids)
        message = f"{selected.name} is ready to build."
        if linked > 1:
            message += f" It changes {linked} linked logical ranges together."
        return ReplaceResult(selected.asset_id, True, message)

    def replace_audio_batch(
        self,
        replacements: Iterable[
            tuple[Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange | str, Path]
        ],
        *,
        label: str = "Import audio replacement pack",
    ) -> BatchReplaceResult:
        """Validate and stage several standalone WAVs as one Undo action.

        Every asset ID, exact WAV contract, private original, and currently
        staged WAV is validated before live session state changes. True changes
        are first copied to transaction files. If any commit or manifest write
        fails, all touched destinations and in-memory ledgers are restored.
        """

        service = self._require_audio_service()
        if self._uses_immutable_audio_gate(service):
            return self._replace_authorized_audio_batch(replacements, label=label)
        requested = tuple(replacements)
        if not requested:
            raise ValidationError("Add at least one replacement WAV to the pack.")
        if not isinstance(label, str) or not label.strip():
            raise ValidationError("The audio batch needs a readable Undo label.")

        selected: list[tuple[Nfl2k5AudioAsset, Path]] = []
        seen: set[str] = set()
        for number, row in enumerate(requested, 1):
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValidationError(
                    f"Audio batch row {number} must contain an asset and WAV path."
                )
            supplied_asset, supplied_path = row
            asset = service.catalog.get_asset(supplied_asset)
            if asset.asset_id in seen:
                raise ValidationError(
                    f"The audio batch lists {asset.asset_id} more than once."
                )
            seen.add(asset.asset_id)
            if not asset.editable:
                raise ValidationError(
                    f"{asset.name} is not an Editable standalone cue. "
                    "Complete streaming banks and unknown standalone targets remain locked."
                )
            selected.append((asset, Path(supplied_path)))

        @dataclass(frozen=True)
        class _ValidatedAudioRow:
            asset: Nfl2k5AudioAsset
            payload: bytes
            payload_sha256: str
            original: bytes
            current: bytes
            current_edit: AudioSessionEdit | None

        validated: list[_ValidatedAudioRow] = []
        # Read-only with respect to the working project. Decoding a source WAV
        # may populate the separate private original cache, never replacements.
        for asset, supplied_path in selected:
            metadata = service.validate_replacement(asset, supplied_path)
            _resolved, payload = read_bounded_regular_file(
                metadata.wav_path,
                f"Supplied WAV for {asset.name}",
                maximum=metadata.wav_size,
            )
            if sha256_bytes(payload) != metadata.wav_sha256:
                raise ValidationError(
                    f"The supplied WAV for {asset.name} changed while it was checked."
                )
            original_path = service.ensure_original(asset)
            original_metadata = service.validate_replacement(asset, original_path)
            _resolved, original = read_bounded_regular_file(
                original_metadata.wav_path,
                f"Private original WAV for {asset.name}",
                maximum=original_metadata.wav_size,
            )
            if payload != original:
                metadata = service.validate_user_replacement(asset, supplied_path)
                _resolved, payload = read_bounded_regular_file(
                    metadata.wav_path,
                    f"Authored WAV for {asset.name}",
                    maximum=metadata.wav_size,
                )
                if sha256_bytes(payload) != metadata.wav_sha256:
                    raise ValidationError(
                        f"The supplied WAV for {asset.name} changed while it was checked."
                    )
            current_edit = self._audio_edits.get(asset.asset_id)
            if current_edit is None:
                current = original
            else:
                current_metadata = service.validate_user_replacement(
                    asset, current_edit.replacement_path
                )
                _resolved, current = read_bounded_regular_file(
                    current_metadata.wav_path,
                    f"Staged WAV for {asset.name}",
                    maximum=current_metadata.wav_size,
                )
                if (
                    current_metadata.wav_sha256 != current_edit.replacement_sha256
                    or sha256_bytes(current) != current_metadata.wav_sha256
                ):
                    raise ValidationError(
                        f"The staged WAV for {asset.name} changed outside Mod Studio. "
                        "Replace it again before importing an audio pack."
                    )
            validated.append(_ValidatedAudioRow(
                asset, payload, metadata.wav_sha256, original, current, current_edit
            ))

        changed = tuple(row for row in validated if row.payload != row.current)
        requested_ids = tuple(row.asset.asset_id for row in validated)
        if not changed:
            raise ValidationError(
                "Every supplied WAV already matches the current project. "
                "No audio was staged and no Undo action was added."
            )

        transaction = uuid4().hex
        staged_paths: dict[str, Path] = {}
        snapshots: dict[str, Path | None] = {}
        old_edits = dict(self._audio_edits)
        old_undo_length = len(self._audio_undo)
        old_order_length = len(self._undo_order)
        old_history_sequence = self._history_sequence
        committed_ids: set[str] = set()
        try:
            for row in changed:
                if row.payload == row.original:
                    continue
                staged = self.replacements / (
                    f".audio-pack-{transaction}-{_asset_key(row.asset.asset_id)}.wav"
                )
                _write_new_atomic(staged, row.payload)
                # Register immediately after publication. Any later validator
                # exception must still leave the common ``finally`` able to
                # remove this private transaction file.
                staged_paths[row.asset.asset_id] = staged
                # Revalidate bytes at their transaction location before commit.
                checked = service.validate_user_replacement(row.asset, staged)
                if checked.wav_sha256 != row.payload_sha256:
                    raise ValidationError(
                        f"The transaction WAV for {row.asset.name} changed before staging."
                    )

            # Capture the exact Undo state first. The snapshot itself is the
            # optimistic-concurrency witness: only after its ledger, bytes, and
            # still-live source all match the validated baseline may commit
            # begin. A mutation interposed inside snapshot capture therefore
            # fails before any destination or Undo ledger is changed.
            undo_items: list[_UndoItem] = []
            for row in changed:
                snapshot = self._snapshot_audio(row.asset.asset_id)
                snapshots[row.asset.asset_id] = snapshot
                undo_items.append(_UndoItem(row.asset.asset_id, snapshot))

            for row in changed:
                live_edit = self._audio_edits.get(row.asset.asset_id)
                if live_edit != row.current_edit:
                    raise ValidationError(
                        f"The staged WAV for {row.asset.name} changed after validation. "
                        "Import the audio pack again so the newer edit is preserved."
                    )
                if live_edit is None:
                    if snapshots[row.asset.asset_id] is not None:
                        raise ValidationError(
                            f"The staged WAV for {row.asset.name} changed after validation. "
                            "Import the audio pack again so the newer edit is preserved."
                        )
                    continue
                snapshot = snapshots[row.asset.asset_id]
                if snapshot is None:
                    raise ValidationError(
                        f"The staged WAV for {row.asset.name} changed after validation. "
                        "Import the audio pack again so the newer edit is preserved."
                    )
                try:
                    _resolved, snapshot_payload = read_bounded_regular_file(
                        snapshot,
                        f"Undo snapshot for {row.asset.name}",
                        maximum=len(row.current),
                    )
                    live_path = self.current_audio_path(row.asset)
                    _resolved, live_payload = read_bounded_regular_file(
                        live_path,
                        f"Staged WAV for {row.asset.name}",
                        maximum=len(row.current),
                    )
                except ValidationError as exc:
                    raise ValidationError(
                        f"The staged WAV for {row.asset.name} changed after validation. "
                        "Import the audio pack again so the newer edit is preserved."
                    ) from exc
                if (
                    snapshot_payload != row.current
                    or live_payload != snapshot_payload
                    or sha256_bytes(live_payload) != live_edit.replacement_sha256
                ):
                    raise ValidationError(
                        f"The staged WAV for {row.asset.name} changed after validation. "
                        "Import the audio pack again so the newer edit is preserved."
                    )

            new_edits = dict(old_edits)
            for row in changed:
                asset_id = row.asset.asset_id
                destination = self.replacements / f"{_asset_key(asset_id)}.wav"
                committed_ids.add(asset_id)
                if row.payload == row.original:
                    destination.unlink(missing_ok=True)
                    new_edits.pop(asset_id, None)
                    continue
                # Keep the transaction path in ``staged_paths`` until the
                # outer ``finally`` runs.  If ``os.replace`` fails, the source
                # file still exists and must be removed there; popping first
                # would orphan an undeclared ``.audio-pack-*`` WAV.
                staged = staged_paths[asset_id]
                with _explain_write_failure(destination):
                    os.replace(platform_compat.long_path(staged), platform_compat.long_path(destination))
                checked = service.validate_user_replacement(row.asset, destination)
                if checked.wav_sha256 != row.payload_sha256:
                    raise ValidationError(
                        f"The staged WAV for {row.asset.name} changed during commit."
                    )
                new_edits[asset_id] = AudioSessionEdit(
                    asset_id, destination, checked.wav_sha256
                )

            self._audio_edits = new_edits
            normalized_label = label.strip()
            self._audio_undo.append(
                _UndoAction(normalized_label, tuple(undo_items))
            )
            self._undo_order.append(_SessionUndo("audio", normalized_label))
            self._write_manifest()
        except BaseException:
            self._audio_edits = old_edits
            del self._audio_undo[old_undo_length:]
            del self._undo_order[old_order_length:]
            self._history_sequence = old_history_sequence
            for row in changed:
                asset_id = row.asset.asset_id
                if asset_id not in committed_ids:
                    continue
                destination = self.replacements / f"{_asset_key(asset_id)}.wav"
                destination.unlink(missing_ok=True)
                snapshot = snapshots.get(asset_id)
                if snapshot is not None and snapshot.is_file():
                    copy_user_asset_atomic(snapshot, destination)
            try:
                self._write_manifest()
            except BaseException:
                pass
            for snapshot in snapshots.values():
                if snapshot is not None:
                    snapshot.unlink(missing_ok=True)
            raise
        finally:
            for staged in staged_paths.values():
                staged.unlink(missing_ok=True)

        changed_ids = tuple(row.asset.asset_id for row in changed)
        modified_ids = tuple(
            asset_id for asset_id in requested_ids if asset_id in self._audio_edits
        )
        return BatchReplaceResult(
            requested_ids,
            changed_ids,
            modified_ids,
            f"Imported {len(changed_ids)} changed audio cue"
            f"{'s' if len(changed_ids) != 1 else ''} as one Undo action.",
        )

    def staged_preflight_inputs(self) -> tuple[tuple[Any, ...], ...]:
        """Snapshot every staged PNG edit as a prediction input.

        Deliberately fast and side-effect free, so a caller can take it under a
        lock and then run the slow prediction outside one. Resolving the fixed
        allocation is a cached report lookup, not a build.
        """

        from mod_editor.core import nfl2k5_import_preflight as preflight

        staged: list[tuple[Any, Path]] = []
        for asset_id in sorted(self._edits):
            asset = self._visual_asset(asset_id)
            staged.append((asset, self._edits[asset_id].replacement_path))
        return preflight.edits_for_assets(staged)

    def preflight_visual_edits(
        self,
        progress: Callable[[str, int, int], None] | None = None,
    ) -> tuple[Any, ...]:
        """Say what each staged PNG will become before a build decides it.

        Beta 41/42 replaced a hard build failure with a palette ladder that
        quantizes art down until it fits its fixed VC-LZ span. That is lossy and
        it shipped silent, so a jersey could lose 240 palette entries with
        nothing said. This runs the real quantizer and encoder against the real
        slot contract first, per staged edit.

        It is read-only: no session state changes, and a family with no modelled
        contract -- or one whose compatibility report is unavailable -- is
        reported as unmodelled rather than guessed at.
        """

        from mod_editor.core import nfl2k5_import_preflight as preflight

        rows = self.staged_preflight_inputs()
        if not rows:
            return ()
        return preflight.predict_edits(rows, progress=progress)

    def preflight_audio_batch(
        self,
        replacements: Iterable[
            tuple[Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange | str, Path]
        ],
    ) -> AudioBatchPreflightResult:
        """Fully authorize and simulate a batch without changing project state.

        The production replacement-pack route always uses the immutable NFL 2K5
        audio gate. Keeping preflight limited to that route prevents an older
        validator adapter from being mistaken for the current source-containment
        contract.
        """

        service = self._require_audio_service()
        if not self._uses_immutable_audio_gate(service):
            raise ValidationError(
                "Audio replacement-pack preflight requires the current immutable "
                "NFL 2K5 audio safety gate."
            )
        return self._preflight_authorized_audio_batch(replacements)

    def _preflight_authorized_audio_batch(
        self,
        replacements: Iterable[
            tuple[Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange | str, Path]
        ],
    ) -> AudioBatchPreflightResult:
        """Read, authorize, alias-check, and simulate one modern audio batch."""

        service = self._require_audio_service()
        assert isinstance(service, Nfl2k5AudioService)
        requested = tuple(replacements)
        if not requested:
            raise ValidationError("Add at least one replacement WAV to the pack.")

        @dataclass(frozen=True, slots=True)
        class _Group:
            selected: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange
            state_id: str
            affected_ids: tuple[str, ...]
            payload: bytes
            original: bytes
            current_edit: AudioSessionEdit | None
            current_payload: bytes

        @dataclass(frozen=True, slots=True)
        class _Requested:
            selected: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange
            state_id: str

        grouped: dict[str, _Group] = {}
        logical_seen: set[str] = set()
        requested_rows: list[_Requested] = []
        for number, row in enumerate(requested, 1):
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValidationError(
                    f"Audio batch row {number} must contain an asset and WAV path."
                )
            supplied_asset, supplied_path = row
            selected = service.resolve_editable_audio(supplied_asset)
            if selected.asset_id in logical_seen:
                raise ValidationError(
                    f"The audio batch lists {selected.asset_id} more than once."
                )
            logical_seen.add(selected.asset_id)

            snapshot = service.read_replacement_snapshot(
                selected, Path(supplied_path)
            )
            payload = snapshot.wav_bytes
            original_path = service.audio_original_path(selected)
            original_snapshot = service.read_replacement_snapshot(
                selected, original_path
            )
            original = original_snapshot.wav_bytes
            if payload != original:
                authorized = service.authorize_replacement_snapshot(
                    selected, snapshot
                )
                if (
                    authorized.wav_bytes != payload
                    or authorized.wav_sha256 != snapshot.metadata.wav_sha256
                ):
                    raise ValidationError(
                        f"The authorized WAV for {selected.name} changed during "
                        "replacement-pack preflight."
                    )
                payload = authorized.wav_bytes

            state_id = service.audio_physical_id(selected)
            affected_ids = service.audio_affected_asset_ids(selected)
            requested_rows.append(_Requested(selected, state_id))
            prior = grouped.get(state_id)
            if prior is not None:
                if prior.payload != payload:
                    raise ValidationError(
                        "Two logical streaming aliases in this import own one "
                        "physical slot but supply different WAVs. Nothing was "
                        "changed; keep one WAV or make both alias entries identical."
                    )
                continue

            current_edit = self._audio_edits.get(state_id)
            if current_edit is None:
                current_payload = original
            else:
                _current_snapshot, current_authorized = self._authorize_audio_path(
                    selected, current_edit.replacement_path
                )
                assert current_authorized is not None
                if current_authorized.wav_sha256 != current_edit.replacement_sha256:
                    raise ValidationError(
                        f"The staged WAV for {selected.name} changed outside Mod Studio."
                    )
                current_payload = current_authorized.wav_bytes
            grouped[state_id] = _Group(
                selected,
                state_id,
                affected_ids,
                payload,
                original,
                current_edit,
                current_payload,
            )

        resulting: dict[str, tuple[str, ...]] = {
            state_id: edit.affected_asset_ids or (edit.asset_id,)
            for state_id, edit in self._audio_edits.items()
        }
        for state_id, row in grouped.items():
            if row.payload == row.original:
                resulting.pop(state_id, None)
            else:
                resulting[state_id] = row.affected_ids

        preview_rows = tuple(
            AudioBatchPreflightRow(
                asset_id=row.selected.asset_id,
                label=row.selected.name,
                would_change=(
                    grouped[row.state_id].payload
                    != grouped[row.state_id].current_payload
                ),
                would_restore_original=(
                    grouped[row.state_id].payload
                    != grouped[row.state_id].current_payload
                    and grouped[row.state_id].payload
                    == grouped[row.state_id].original
                ),
                affected_asset_ids=grouped[row.state_id].affected_ids,
            )
            for row in requested_rows
        )
        resulting_ids = tuple(sorted({
            asset_id for affected_ids in resulting.values()
            for asset_id in affected_ids
        }))
        changed_groups = tuple(
            row for row in grouped.values()
            if row.payload != row.current_payload
        )
        restoring_groups = tuple(
            row for row in changed_groups if row.payload == row.original
        )
        affected_ids = tuple(dict.fromkeys(
            asset_id for row in changed_groups for asset_id in row.affected_ids
        ))
        return AudioBatchPreflightResult(
            preview_rows,
            resulting_ids,
            len(changed_groups),
            len(restoring_groups),
            affected_ids,
        )

    def _replace_authorized_audio_batch(
        self,
        replacements: Iterable[
            tuple[Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange | str, Path]
        ],
        *,
        label: str,
    ) -> BatchReplaceResult:
        """Validate all logical requests, deduplicate aliases, then commit once."""

        service = self._require_audio_service()
        assert isinstance(service, Nfl2k5AudioService)
        requested = tuple(replacements)
        if not requested:
            raise ValidationError("Add at least one replacement WAV to the pack.")
        if not isinstance(label, str) or not label.strip():
            raise ValidationError("The audio batch needs a readable Undo label.")

        @dataclass(frozen=True)
        class _Row:
            selected: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange
            state_id: str
            affected_ids: tuple[str, ...]
            payload: bytes
            payload_sha256: str
            authorized: Any | None
            original: bytes
            current_edit: AudioSessionEdit | None
            current_payload: bytes

        grouped: dict[str, _Row] = {}
        logical_seen: set[str] = set()
        requested_ids: list[str] = []
        # This entire pass is read-only with respect to the working session.
        # Every caller path is read once into ``AudioReplacementSnapshot``.
        for number, row in enumerate(requested, 1):
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValidationError(
                    f"Audio batch row {number} must contain an asset and WAV path."
                )
            supplied_asset, supplied_path = row
            selected = service.resolve_editable_audio(supplied_asset)
            if selected.asset_id in logical_seen:
                raise ValidationError(
                    f"The audio batch lists {selected.asset_id} more than once."
                )
            logical_seen.add(selected.asset_id)
            requested_ids.append(selected.asset_id)
            snapshot = service.read_replacement_snapshot(
                selected, Path(supplied_path)
            )
            payload = snapshot.wav_bytes
            original = service.audio_original_path(selected).read_bytes()
            authorized = None
            payload_sha256 = snapshot.metadata.wav_sha256
            if payload != original:
                authorized = service.authorize_replacement_snapshot(
                    selected, snapshot
                )
                payload_sha256 = authorized.wav_sha256
            state_id = service.audio_physical_id(selected)
            affected_ids = service.audio_affected_asset_ids(selected)
            prior = grouped.get(state_id)
            if prior is not None:
                if prior.payload != payload:
                    raise ValidationError(
                        "Two logical streaming aliases in this import own one "
                        "physical slot but supply different WAVs. Nothing was "
                        "changed; keep one WAV or make both alias entries identical."
                    )
                # Identical aliases deliberately collapse to the first public
                # logical ID. One physical edit and one project record result.
                continue

            current_edit = self._audio_edits.get(state_id)
            if current_edit is None:
                current_payload = original
            else:
                _current_snapshot, current_authorized = self._authorize_audio_path(
                    selected, current_edit.replacement_path
                )
                assert current_authorized is not None
                if current_authorized.wav_sha256 != current_edit.replacement_sha256:
                    raise ValidationError(
                        f"The staged WAV for {selected.name} changed outside Mod Studio."
                    )
                current_payload = current_authorized.wav_bytes
            grouped[state_id] = _Row(
                selected,
                state_id,
                affected_ids,
                payload,
                payload_sha256,
                authorized,
                original,
                current_edit,
                current_payload,
            )

        changed = tuple(
            row for row in grouped.values() if row.payload != row.current_payload
        )
        if not changed:
            raise ValidationError(
                "Every supplied WAV already matches the current project and "
                "physical audio state. No audio was staged and no Undo action "
                "was added."
            )

        transaction = uuid4().hex
        stages: dict[str, Path] = {}
        snapshots: dict[str, Path | None] = {}
        old_edits = dict(self._audio_edits)
        old_undo_length = len(self._audio_undo)
        old_order_length = len(self._undo_order)
        old_history_sequence = self._history_sequence
        committed: set[str] = set()
        try:
            for row in changed:
                if row.authorized is None:
                    continue
                stage = self.replacements / (
                    f".audio-pack-{transaction}-{_asset_key(row.state_id)}.wav"
                )
                _write_new_atomic(stage, row.authorized.wav_bytes)
                stages[row.state_id] = stage

            undo_items: list[_UndoItem] = []
            for row in changed:
                snapshot = self._snapshot_audio(row.state_id)
                snapshots[row.state_id] = snapshot
                prior_logical = (
                    row.current_edit.asset_id
                    if row.current_edit is not None else row.selected.asset_id
                )
                prior_affected = (
                    row.current_edit.affected_asset_ids
                    if row.current_edit is not None
                    and row.current_edit.affected_asset_ids
                    else row.affected_ids
                )
                undo_items.append(_UndoItem(
                    row.state_id, snapshot, prior_logical, prior_affected
                ))

            # The snapshot is also the optimistic-concurrency witness. A live
            # mutation after the read-only pass aborts before any destination.
            for row in changed:
                if self._audio_edits.get(row.state_id) != row.current_edit:
                    raise ValidationError(
                        f"The staged WAV for {row.selected.name} changed after "
                        "validation. Import the pack again."
                    )
                snapshot = snapshots[row.state_id]
                if row.current_edit is None:
                    if snapshot is not None:
                        raise ValidationError(
                            f"The staged WAV for {row.selected.name} changed after validation."
                        )
                    continue
                if snapshot is None:
                    raise ValidationError(
                        f"The staged WAV for {row.selected.name} changed after validation."
                    )
                snapshot_check = service.read_replacement_snapshot(
                    row.selected, snapshot
                )
                snapshot_auth = service.authorize_replacement_snapshot(
                    row.selected, snapshot_check
                )
                live_check = service.read_replacement_snapshot(
                    row.selected, row.current_edit.replacement_path
                )
                live_auth = service.authorize_replacement_snapshot(
                    row.selected, live_check
                )
                if not (
                    snapshot_auth.wav_bytes
                    == live_auth.wav_bytes
                    == row.current_payload
                ):
                    raise ValidationError(
                        f"The staged WAV for {row.selected.name} changed after "
                        "validation. Import the pack again."
                    )

            new_edits = dict(old_edits)
            for row in changed:
                destination = self.replacements / f"{_asset_key(row.state_id)}.wav"
                committed.add(row.state_id)
                if row.authorized is None:
                    destination.unlink(missing_ok=True)
                    new_edits.pop(row.state_id, None)
                    continue
                with _explain_write_failure(destination):
                    os.replace(platform_compat.long_path(stages[row.state_id]), platform_compat.long_path(destination))
                new_edits[row.state_id] = AudioSessionEdit(
                    row.selected.asset_id,
                    destination,
                    row.authorized.wav_sha256,
                    row.state_id,
                    row.affected_ids,
                )
            self._audio_edits = new_edits
            normalized_label = label.strip()
            self._audio_undo.append(_UndoAction(
                normalized_label, tuple(undo_items)
            ))
            self._undo_order.append(_SessionUndo("audio", normalized_label))
            self._write_manifest()
        except BaseException:
            self._audio_edits = old_edits
            del self._audio_undo[old_undo_length:]
            del self._undo_order[old_order_length:]
            self._history_sequence = old_history_sequence
            for row in changed:
                if row.state_id not in committed:
                    continue
                destination = self.replacements / f"{_asset_key(row.state_id)}.wav"
                destination.unlink(missing_ok=True)
                if row.current_edit is not None:
                    _replace_atomic(destination, row.current_payload)
            try:
                self._write_manifest()
            except BaseException:
                pass
            for snapshot in snapshots.values():
                if snapshot is not None:
                    snapshot.unlink(missing_ok=True)
            raise
        finally:
            for stage in stages.values():
                stage.unlink(missing_ok=True)

        changed_ids = tuple(dict.fromkeys(
            asset_id for row in changed for asset_id in row.affected_ids
        ))
        modified_ids = tuple(sorted(
            asset_id
            for row in self._audio_edits.values()
            for asset_id in (row.affected_asset_ids or (row.asset_id,))
        ))
        return BatchReplaceResult(
            tuple(requested_ids),
            changed_ids,
            modified_ids,
            f"Imported {len(changed)} physical audio edit"
            f"{'s' if len(changed) != 1 else ''} as one Undo action.",
        )

    def revert_audio(
        self,
        asset: Nfl2k5AudioAsset | Nfl2k5StreamingAudioRange | str,
    ) -> bool:
        service = self._require_audio_service()
        if self._uses_immutable_audio_gate(service):
            selected = service.resolve_editable_audio(asset)
            state_id = service.audio_physical_id(selected)
            edit = self._audio_edits.get(state_id)
            if edit is None:
                return False
            self._authorize_audio_path(selected, edit.replacement_path)
            previous = self._snapshot_audio(state_id)
            edit.replacement_path.unlink(missing_ok=True)
            del self._audio_edits[state_id]
            label = f"Revert {selected.name}"
            self._audio_undo.append(_UndoAction(
                label,
                (_UndoItem(
                    state_id,
                    previous,
                    edit.asset_id,
                    edit.affected_asset_ids
                    or service.audio_affected_asset_ids(selected),
                ),),
            ))
            self._undo_order.append(_SessionUndo("audio", label))
            self._write_manifest()
            return True
        selected = service.catalog.get_asset(asset)
        edit = self._audio_edits.get(selected.asset_id)
        if edit is None:
            return False
        previous = self._snapshot_audio(selected.asset_id)
        edit.replacement_path.unlink(missing_ok=True)
        del self._audio_edits[selected.asset_id]
        self._audio_undo.append(_UndoAction(
            f"Revert {selected.name}",
            (_UndoItem(selected.asset_id, previous),),
        ))
        self._undo_order.append(_SessionUndo("audio", f"Revert {selected.name}"))
        self._write_manifest()
        return True

    def _undo_audio_action(self, *, expected_label: str | None = None) -> None:
        """Undo one audio action as an all-files-plus-manifest transaction."""

        if not self._audio_undo:
            raise ValidationError("The audio undo history is inconsistent.")
        action = self._audio_undo[-1]
        if expected_label is not None and action.label != expected_label:
            raise ValidationError("The audio undo labels are inconsistent.")
        if not action.items or len({item.asset_id for item in action.items}) != len(
            action.items
        ):
            raise ValidationError("The audio undo action has duplicate or empty targets.")

        service = self._require_audio_service()
        if self._uses_immutable_audio_gate(service):
            self._undo_authorized_audio_action(action)
            return
        transaction = uuid4().hex
        old_edits = dict(self._audio_edits)
        manifest_path = self.root / "session.json"
        try:
            manifest_payload = manifest_path.read_bytes()
        except OSError as exc:
            raise ValidationError(
                f"The working-session manifest cannot be protected for Undo: {exc}"
            ) from exc

        restore_stages: dict[str, Path] = {}
        rollback_stages: dict[str, Path] = {}
        expected_previous_hashes: dict[str, str] = {}
        expected_current_hashes: dict[str, str] = {}
        commit_started = False
        try:
            # Validate and copy every before/after state before changing a live
            # destination. A broken second cue therefore cannot partially undo
            # a valid first cue.
            for item in action.items:
                asset = service.catalog.get_asset(item.asset_id)
                destination = self.replacements / f"{_asset_key(item.asset_id)}.wav"
                current = old_edits.get(item.asset_id)
                if current is None:
                    if os.path.lexists(destination):
                        raise ValidationError(
                            f"An undeclared audio file blocks Undo for {asset.name}."
                        )
                else:
                    checked_current = service.validate_user_replacement(
                        asset, current.replacement_path
                    )
                    if checked_current.wav_sha256 != current.replacement_sha256:
                        raise ValidationError(
                            f"The staged WAV for {asset.name} changed outside Mod Studio."
                        )
                    rollback = self.replacements / (
                        f".audio-undo-{transaction}-{_asset_key(item.asset_id)}-rollback.wav"
                    )
                    copy_user_asset_atomic(current.replacement_path, rollback)
                    # Register before validation so a validator failure cannot
                    # orphan the newly copied transaction file.
                    rollback_stages[item.asset_id] = rollback
                    rollback_checked = service.validate_user_replacement(asset, rollback)
                    if rollback_checked.wav_sha256 != current.replacement_sha256:
                        raise ValidationError(
                            f"The protected current WAV for {asset.name} changed during Undo."
                        )
                    expected_current_hashes[item.asset_id] = current.replacement_sha256

                if item.previous_snapshot is not None:
                    checked_previous = service.validate_user_replacement(
                        asset, item.previous_snapshot
                    )
                    restore = self.replacements / (
                        f".audio-undo-{transaction}-{_asset_key(item.asset_id)}-restore.wav"
                    )
                    copy_user_asset_atomic(item.previous_snapshot, restore)
                    # As above, the cleanup ledger must own the temp before a
                    # fallible validation step runs.
                    restore_stages[item.asset_id] = restore
                    restore_checked = service.validate_user_replacement(asset, restore)
                    if restore_checked.wav_sha256 != checked_previous.wav_sha256:
                        raise ValidationError(
                            f"The protected prior WAV for {asset.name} changed during Undo."
                        )
                    expected_previous_hashes[item.asset_id] = (
                        checked_previous.wav_sha256
                    )

            new_edits = dict(old_edits)
            commit_started = True
            for item in action.items:
                asset = service.catalog.get_asset(item.asset_id)
                destination = self.replacements / f"{_asset_key(item.asset_id)}.wav"
                if item.previous_snapshot is None:
                    destination.unlink(missing_ok=True)
                    new_edits.pop(item.asset_id, None)
                    continue
                # Keep the restore path registered through the transaction.
                # A failed ``os.replace`` leaves its source in place, and the
                # common ``finally`` must still know which path to remove.
                restore = restore_stages[item.asset_id]
                with _explain_write_failure(destination):
                    os.replace(platform_compat.long_path(restore), platform_compat.long_path(destination))
                checked = service.validate_user_replacement(asset, destination)
                expected_hash = expected_previous_hashes[item.asset_id]
                if checked.wav_sha256 != expected_hash:
                    raise ValidationError(
                        f"The restored WAV for {asset.name} changed during Undo."
                    )
                new_edits[item.asset_id] = AudioSessionEdit(
                    item.asset_id, destination, checked.wav_sha256
                )

            self._audio_edits = new_edits
            self._write_manifest()
        except BaseException as original_error:
            self._audio_edits = old_edits
            rollback_errors: list[str] = []
            if commit_started:
                for item in action.items:
                    destination = (
                        self.replacements / f"{_asset_key(item.asset_id)}.wav"
                    )
                    try:
                        destination.unlink(missing_ok=True)
                        rollback = rollback_stages.get(item.asset_id)
                        if rollback is not None:
                            copy_user_asset_atomic(rollback, destination)
                            asset = service.catalog.get_asset(item.asset_id)
                            checked = service.validate_user_replacement(
                                asset, destination
                            )
                            if (
                                checked.wav_sha256
                                != expected_current_hashes[item.asset_id]
                            ):
                                raise ValidationError(
                                    "restored current WAV checksum does not match"
                                )
                    except BaseException as rollback_error:
                        rollback_errors.append(
                            f"{item.asset_id}: {rollback_error}"
                        )
                try:
                    _replace_atomic(manifest_path, manifest_payload)
                except BaseException as rollback_error:
                    rollback_errors.append(f"session manifest: {rollback_error}")
            if rollback_errors:
                raise ValidationError(
                    "Audio Undo failed and its rollback was incomplete: "
                    + "; ".join(rollback_errors)
                ) from original_error
            raise
        else:
            self._audio_undo.pop()
            for item in action.items:
                if item.previous_snapshot is not None:
                    try:
                        item.previous_snapshot.unlink(missing_ok=True)
                    except OSError:
                        # A stale private history copy is harmless and can be
                        # cleaned with the session; committed state stays valid.
                        pass
        finally:
            for temporary in (*restore_stages.values(), *rollback_stages.values()):
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def _undo_authorized_audio_action(self, action: _UndoAction) -> None:
        """Undo physical audio edits using only preauthorized immutable bytes."""

        service = self._require_audio_service()
        assert isinstance(service, Nfl2k5AudioService)
        old_edits = dict(self._audio_edits)
        manifest_path = self.root / "session.json"
        try:
            manifest_payload = manifest_path.read_bytes()
        except OSError as exc:
            raise ValidationError(
                f"The working-session manifest cannot be protected for Undo: {exc}"
            ) from exc

        transaction = uuid4().hex
        restore_stages: dict[str, Path] = {}
        rollback_stages: dict[str, Path] = {}
        previous_tokens: dict[str, Any] = {}
        current_tokens: dict[str, Any] = {}
        previous_targets: dict[str, Any] = {}
        commit_started = False
        try:
            for item in action.items:
                logical_id = item.logical_asset_id
                if not isinstance(logical_id, str) or not logical_id:
                    raise ValidationError(
                        "Authorized audio Undo is missing its logical asset ID."
                    )
                selected = service.resolve_editable_audio(logical_id)
                if service.audio_physical_id(selected) != item.asset_id:
                    raise ValidationError(
                        "Authorized audio Undo no longer resolves to its physical slot."
                    )
                previous_targets[item.asset_id] = selected
                destination = self.replacements / f"{_asset_key(item.asset_id)}.wav"
                current = old_edits.get(item.asset_id)
                if current is None:
                    if os.path.lexists(destination):
                        raise ValidationError(
                            f"An undeclared audio file blocks Undo for {selected.name}."
                        )
                else:
                    current_selected = service.resolve_editable_audio(current.asset_id)
                    snapshot = service.read_replacement_snapshot(
                        current_selected, current.replacement_path
                    )
                    issued = service.authorize_replacement_snapshot(
                        current_selected, snapshot
                    )
                    if issued.wav_sha256 != current.replacement_sha256:
                        raise ValidationError(
                            f"The staged WAV for {current_selected.name} changed outside Mod Studio."
                        )
                    current_tokens[item.asset_id] = issued
                    rollback = self.replacements / (
                        f".audio-undo-{transaction}-{_asset_key(item.asset_id)}-rollback.wav"
                    )
                    _write_new_atomic(rollback, issued.wav_bytes)
                    rollback_stages[item.asset_id] = rollback

                if item.previous_snapshot is not None:
                    snapshot = service.read_replacement_snapshot(
                        selected, item.previous_snapshot
                    )
                    issued = service.authorize_replacement_snapshot(
                        selected, snapshot
                    )
                    previous_tokens[item.asset_id] = issued
                    restore = self.replacements / (
                        f".audio-undo-{transaction}-{_asset_key(item.asset_id)}-restore.wav"
                    )
                    _write_new_atomic(restore, issued.wav_bytes)
                    restore_stages[item.asset_id] = restore

            new_edits = dict(old_edits)
            commit_started = True
            for item in action.items:
                destination = self.replacements / f"{_asset_key(item.asset_id)}.wav"
                if item.previous_snapshot is None:
                    destination.unlink(missing_ok=True)
                    new_edits.pop(item.asset_id, None)
                    continue
                with _explain_write_failure(destination):
                    os.replace(platform_compat.long_path(restore_stages[item.asset_id]), platform_compat.long_path(destination))
                issued = previous_tokens[item.asset_id]
                logical_id = item.logical_asset_id
                assert isinstance(logical_id, str)
                affected = item.affected_asset_ids or service.audio_affected_asset_ids(
                    previous_targets[item.asset_id]
                )
                new_edits[item.asset_id] = AudioSessionEdit(
                    logical_id,
                    destination,
                    issued.wav_sha256,
                    item.asset_id,
                    affected,
                )
            self._audio_edits = new_edits
            self._write_manifest()
        except BaseException as original_error:
            self._audio_edits = old_edits
            rollback_errors: list[str] = []
            if commit_started:
                for item in action.items:
                    destination = self.replacements / f"{_asset_key(item.asset_id)}.wav"
                    try:
                        destination.unlink(missing_ok=True)
                        token = current_tokens.get(item.asset_id)
                        if token is not None:
                            _replace_atomic(destination, token.wav_bytes)
                    except BaseException as rollback_error:
                        rollback_errors.append(
                            f"{item.asset_id}: {rollback_error}"
                        )
                try:
                    _replace_atomic(manifest_path, manifest_payload)
                except BaseException as rollback_error:
                    rollback_errors.append(f"session manifest: {rollback_error}")
            if rollback_errors:
                raise ValidationError(
                    "Audio Undo failed and its rollback was incomplete: "
                    + "; ".join(rollback_errors)
                ) from original_error
            raise
        else:
            self._audio_undo.pop()
            for item in action.items:
                if item.previous_snapshot is not None:
                    item.previous_snapshot.unlink(missing_ok=True)
        finally:
            for temporary in (*restore_stages.values(), *rollback_stages.values()):
                temporary.unlink(missing_ok=True)

    def canonical_document(self) -> dict[str, object]:
        text_provider_edits = (
            self.text_edits.provider_edits() if self.text_edits is not None else ()
        )
        if (
            not self._edits
            and not self._crib_edits
            and not self._crib_geometry_edits
            and not self._stadium_edits
            and self._stadium_geometry_edit is None
            and not text_provider_edits
            and not self._audio_edits
            and not self._unif_colors
            and not self._play_route_edits
            and not self._formation_creates
            and not self._play_creates
            and not self._formation_links
        ):
            raise ValidationError("Replace at least one asset before building a modded XISO.")
        edits: list[dict[str, object]] = []
        for asset_id in sorted(self._edits):
            asset = self._visual_asset(asset_id)
            edit = self._edits[asset_id]
            edits.append(asset.provider_edit(edit.replacement_path))
        if self._crib_edits:
            crib_catalog = self._require_crib_catalog()
            for asset_id in sorted(self._crib_edits):
                asset = crib_catalog.get(asset_id)
                edit = self._crib_edits[asset_id]
                edits.append(asset.provider_edit(edit.replacement_path))
        for asset_id in sorted(self._stadium_edits):
            edit = self._stadium_edits[asset_id]
            edits.append({
                "kind": "stadium_texture",
                "target": asset_id,
                "png": str(edit.replacement_path),
            })
        if self._stadium_geometry_edit is not None:
            edits.append({
                "kind": "stadium_geometry",
                "target": self._stadium_geometry_edit.scene_id,
                "recipe": str(self._stadium_geometry_edit.recipe_path),
            })
        for scene_id in sorted(self._crib_geometry_edits):
            edit = self._crib_geometry_edits[scene_id]
            edits.append({
                "kind": "crib_scene_geometry",
                "target": edit.scene_id,
                "recipe": str(edit.recipe_path),
            })
        for selector in sorted(self._unif_colors):
            facemask, turtleneck = self._unif_colors[selector]
            edits.append({
                "kind": "unif_color",
                "selector": selector,
                "facemask": facemask,
                "turtleneck": turtleneck,
            })
        edits.extend(text_provider_edits)
        edits.extend(
            request.provider_edit() for request in self.play_route_edits
        )
        edits.extend(
            request.provider_edit() for request in self.formation_creates
        )
        edits.extend(
            request.provider_edit() for request in self.play_creates
        )
        edits.extend(
            request.provider_edit() for request in self.formation_links
        )
        if self._audio_edits:
            audio_service = self._require_audio_service()
            for edit in sorted(
                self._audio_edits.values(), key=lambda item: item.asset_id
            ):
                asset = self._select_audio_target(edit.asset_id)
                if isinstance(asset, Nfl2k5StreamingAudioRange):
                    edits.append({
                        "asset_id": edit.asset_id,
                        "kind": "ausb_audio",
                        "wav": str(edit.replacement_path),
                    })
                elif asset.selector == MENU_BACK_SELECTOR:
                    edits.append({
                        "kind": "menu_back_audio",
                        "wav": str(edit.replacement_path),
                    })
                else:
                    edits.append({
                        "asset_id": edit.asset_id,
                        "kind": "audo_audio",
                        "wav": str(edit.replacement_path),
                    })
        return {
            "edits": edits,
            "purpose": "Built with 2K5 Mod Studio from user-supplied replacements.",
            "schema": BACKEND_SCHEMA,
        }

    def write_canonical_project(self, destination: Path) -> Path:
        return _write_new_atomic(destination, _canonical_json(self.canonical_document()))

    def save_shareable_project(
        self,
        destination: Path,
        *,
        replace: bool = False,
        expected_target: ProjectTargetIdentity | None = None,
        allow_empty: bool = False,
    ) -> Path:
        """Save only user replacements and metadata to a portable project."""

        if self._stadium_geometry_edit is not None or self._crib_geometry_edits:
            subjects = []
            if self._stadium_geometry_edit is not None:
                subjects.append("Stadium")
            if self._crib_geometry_edits:
                subjects.append("Crib")
            raise ValidationError(
                f"Edited {' and '.join(subjects)} model positions are kept only "
                "in this private "
                "working session because they are derived from your game copy. "
                "Build the XISO locally, or revert the edited model before "
                "saving a shareable project."
            )

        audio_edits = tuple(
            sorted(self._audio_edits.values(), key=lambda item: item.asset_id)
        )
        archive_audio_edits: tuple[Any, ...] = audio_edits
        if audio_edits:
            service = self._require_audio_service()
            if self._uses_immutable_audio_gate(service):
                authorized_edits: list[AuthorizedProjectAudioEdit] = []
                for edit in audio_edits:
                    asset = service.resolve_editable_audio(edit.asset_id)
                    snapshot = service.read_replacement_snapshot(
                        asset, edit.replacement_path
                    )
                    issued = service.authorize_replacement_snapshot(
                        asset, snapshot
                    )
                    if issued.wav_sha256 != edit.replacement_sha256:
                        raise ValidationError(
                            f"The staged WAV for {asset.name} changed outside Mod Studio. "
                            "Replace it again before saving."
                        )
                    authorized_edits.append(AuthorizedProjectAudioEdit(
                        edit.asset_id, issued
                    ))
                archive_audio_edits = tuple(authorized_edits)
            else:
                for edit in audio_edits:
                    asset = service.catalog.get_asset(edit.asset_id)
                    metadata = service.validate_user_replacement(
                        asset, edit.replacement_path
                    )
                    if metadata.wav_sha256 != edit.replacement_sha256:
                        raise ValidationError(
                            f"The staged WAV for {asset.name} changed outside Mod Studio. "
                            "Replace it again before saving."
                        )

        return save_project_archive(
            catalog=self._project_catalog_router,
            asset_io=self._project_io_router,
            edits=self.iter_project_png_edits(),
            destination=destination,
            replace=replace,
            expected_target=expected_target,
            allow_empty=allow_empty,
            text_replacements=(
                self.text_edits.replacement_document()
                if self.text_edits is not None and self.text_edits.modified_count
                else None
            ),
            audio_edits=archive_audio_edits,
            audio_annotations=self.audio_annotations,
            uniform_colors=(
                {
                    "selector": selector,
                    "facemask": self._unif_colors[selector][0],
                    "turtleneck": self._unif_colors[selector][1],
                }
                for selector in sorted(self._unif_colors)
            ),
            play_route_edits=(
                request.provider_edit() for request in self.play_route_edits
            ),
            formation_creates=(
                request.provider_edit() for request in self.formation_creates
            ),
            play_creates=(
                request.provider_edit() for request in self.play_creates
            ),
            formation_links=(
                request.provider_edit() for request in self.formation_links
            ),
        )

    def load_shareable_project(self, source: Path) -> int:
        """Load a completely validated project into a new, empty session."""

        if self.modified_count or self._audio_annotations:
            raise ValidationError(
                "Projects load into a fresh working session; save or revert current edits first."
            )
        loaded = load_project_archive(
            source=source,
            catalog=self._project_catalog_router,
            asset_io=self._project_io_router,
            private_root=self.root,
        )
        try:
            new_play_routes: dict[str, PlayRouteCloneRequest] = {}
            if loaded.play_route_edits:
                inspector = self.playbook_inspector
                if inspector is None:
                    raise ValidationError(
                        "This project includes PLAY routes, but the private "
                        "playbook source is not attached."
                    )
                by_book: dict[str, list[PlayRouteCloneRequest]] = {}
                for raw in loaded.play_route_edits:
                    request = play_route_request_from_mapping({
                        key: value for key, value in raw.items() if key != "kind"
                    })
                    if request.selector in new_play_routes:
                        raise ValidationError(
                            "Project repeats one PLAY assignment-route target."
                        )
                    new_play_routes[request.selector] = request
                    by_book.setdefault(request.asset_id, []).append(request)
                for asset_id, requests in by_book.items():
                    self._validate_play_route_set(inspector.load(asset_id), requests)
            new_formation_creates: dict[str, FormationCreateRequest] = {}
            new_play_creates: dict[str, PlayCreateRequest] = {}
            for raw in loaded.formation_creates:
                request = formation_request_from_mapping({
                    key: value for key, value in raw.items() if key != "kind"
                })
                new_formation_creates[request.selector] = request
            for raw in loaded.play_creates:
                request = formation_play_request_from_mapping({
                    key: value for key, value in raw.items() if key != "kind"
                })
                new_play_creates[request.selector] = request
            new_links: dict[str, FormationLinkRequest] = {}
            for raw in loaded.formation_links:
                request = link_request_from_mapping({
                    key: value for key, value in raw.items() if key != "kind"
                })
                new_links[request.selector] = request
            if new_formation_creates or new_play_creates or new_links:
                inspector = self.playbook_inspector
                if inspector is None:
                    raise ValidationError(
                        "This project includes playbook creates, but the private "
                        "playbook source is not attached."
                    )
                from nfl_outer import read_entry_range
                from mod_editor.core.nfl2k5_formation_play_writer import (
                    compile_formation_play_creations,
                )
                books: set[str] = (
                    {r.asset_id for r in new_formation_creates.values()}
                    | {r.asset_id for r in new_play_creates.values()}
                    | {r.asset_id for r in new_links.values()}
                )
                for asset_id in sorted(books):
                    record = inspector.index.get(asset_id)
                    raw = read_entry_range(
                        inspector.index.archive,
                        inspector.index.archive.entries[record.outer_index],
                        record.chunk_offset,
                        record.raw_size,
                    )
                    compile_formation_play_creations(
                        raw,
                        formation_requests=[
                            r for r in new_formation_creates.values()
                            if r.asset_id == asset_id
                        ],
                        play_requests=[
                            r for r in new_play_creates.values()
                            if r.asset_id == asset_id
                        ],
                        link_requests=[
                            r for r in new_links.values()
                            if r.asset_id == asset_id
                        ],
                    )
                self._formation_creates = new_formation_creates
                self._play_creates = new_play_creates
                self._formation_links = new_links
            if self.audio_service is not None:
                for annotation in loaded.audio_annotations:
                    self.audio_service.resolve_playable_audio(annotation.cue_id)
            service = self._require_audio_service() if loaded.audio_edits else None
            if (
                service is not None
                and self._uses_immutable_audio_gate(service)
                and not service.audio_origin_ready
            ):
                raise AudioProjectPreparationRequired(
                    "This project includes user audio. Prepare the private audio "
                    "safety inventories from your own game copy, then open the "
                    "project again. No project edits were applied."
                )
            validated_audio: list[tuple[Any, Any, Any, str, tuple[str, ...]]] = []
            validated_physical: dict[
                str, tuple[Any, Any, Any, str, tuple[str, ...]]
            ] = {}
            # Source-origin validation is session/service-specific, so the
            # generic ZIP loader cannot perform it. Finish that validation for
            # every audio member before applying even the first project edit.
            for row in loaded.audio_edits:
                service = self._require_audio_service()
                if self._uses_immutable_audio_gate(service):
                    asset = service.resolve_editable_audio(row.asset_id)
                    if (
                        type(row.wav_bytes) is not bytes
                        or sha256_bytes(row.wav_bytes) != row.wav_sha256
                    ):
                        raise ValidationError("Project audio changed during import.")
                    issued = service.authorize_user_replacement_bytes(
                        asset, row.wav_bytes
                    )
                    if issued.wav_sha256 != row.wav_sha256:
                        raise ValidationError("Project audio changed during import.")
                    state_id = service.audio_physical_id(asset)
                    affected = service.audio_affected_asset_ids(asset)
                    prepared = (row, asset, issued, state_id, affected)
                    previous = validated_physical.get(state_id)
                    if previous is not None:
                        if previous[2].wav_bytes != issued.wav_bytes:
                            raise ValidationError(
                                "This project contains two logical streaming aliases "
                                "for one physical slot with different WAVs. Nothing "
                                "was imported."
                            )
                        # Identical duplicate aliases collapse to the first
                        # logical record without creating another physical edit.
                        continue
                    validated_physical[state_id] = prepared
                    validated_audio.append(prepared)
                else:
                    asset = service.catalog.get_asset(row.asset_id)
                    metadata = service.validate_user_replacement(
                        asset, row.staged_path
                    )
                    if metadata.wav_sha256 != row.wav_sha256:
                        raise ValidationError("Project audio changed during import.")
                    validated_audio.append((
                        row, asset, metadata, row.asset_id, (row.asset_id,)
                    ))

            # Build the complete destination state before publishing any file.
            # Staged PNG/WAV members are renamed into place on the same private
            # filesystem, so import does not require a second full payload copy.
            new_visual: dict[str, SessionEdit] = {}
            new_crib: dict[str, SessionEdit] = {}
            new_stadium: dict[str, StadiumSessionEdit] = {}
            png_moves: list[tuple[Path, Path]] = []
            stadium_moves: list[tuple[Path, Path, Path, bytes]] = []
            reserved_paths: set[Path] = set()
            for row in loaded.edits:
                asset = row.asset
                asset_id = asset.asset_id
                if isinstance(asset, _ProjectStadiumAsset):
                    texture = asset.texture
                    writer = self._require_supported_stadium_texture(texture)
                    payload, rgba, compiled = writer.validated_replacement(
                        texture, row.staged_path
                    )
                    if (
                        sha256_bytes(payload) != row.png_sha256
                        or sha256_bytes(rgba) != row.rgba_sha256
                    ):
                        raise ValidationError(
                            "Project Stadium texture changed during import."
                        )
                    token = uuid4().hex
                    key = _asset_key(texture.texture_id)
                    authored = self.replacements / f"{key}-{token}.png"
                    preview = self.replacements / f"{key}-{token}.preview.png"
                    edit = StadiumSessionEdit(
                        texture.texture_id,
                        authored,
                        row.png_sha256,
                        row.rgba_sha256,
                        preview,
                        sha256_bytes(compiled.quantized_preview_png),
                    )
                    new_stadium[asset_id] = edit
                    stadium_moves.append((
                        row.staged_path, authored, preview,
                        compiled.quantized_preview_png,
                    ))
                    destinations = (authored, preview)
                else:
                    destination = (
                        self.replacements / f"{_asset_key(asset_id)}.png"
                    )
                    edit = SessionEdit(
                        asset_id, destination, row.png_sha256, row.rgba_sha256
                    )
                    if isinstance(asset, CribAsset):
                        new_crib[asset_id] = edit
                    else:
                        new_visual[asset_id] = edit
                    png_moves.append((row.staged_path, destination))
                    destinations = (destination,)
                for destination in destinations:
                    if destination in reserved_paths or destination.exists():
                        raise ValidationError(
                            "A private project-import destination is unexpectedly occupied."
                        )
                    reserved_paths.add(destination)

            new_text = self.text_edits
            if loaded.text_replacements is not None:
                if self.text_catalog is None:
                    raise ValidationError(
                        "Load the game's text catalog before opening this project."
                    )
                new_text = Nfl2k5TextEdits(self.text_catalog)
                new_text.load_replacement_document(loaded.text_replacements)

            new_audio: dict[str, AudioSessionEdit] = {}
            audio_moves: list[tuple[Path, Path]] = []
            for row, _asset, _authorized_or_metadata, state_id, affected \
                    in validated_audio:
                if sha256_bytes(row.staged_path.read_bytes()) != row.wav_sha256:
                    raise ValidationError("Project audio changed during import.")
                destination = self.replacements / f"{_asset_key(state_id)}.wav"
                if destination in reserved_paths or destination.exists():
                    raise ValidationError(
                        "A private audio import destination is unexpectedly occupied."
                    )
                reserved_paths.add(destination)
                service = self._require_audio_service()
                new_audio[state_id] = AudioSessionEdit(
                    row.asset_id,
                    destination,
                    row.wav_sha256,
                    state_id if self._uses_immutable_audio_gate(service) else None,
                    affected,
                )
                audio_moves.append((row.staged_path, destination))

            new_annotations = {
                annotation.cue_id: annotation
                for annotation in loaded.audio_annotations
            }
            from mod_editor.core import nfl2k5_unif_color_writer as colour

            new_unif_colors: dict[str, tuple[str, str]] = {}
            for row in loaded.uniform_colors:
                uniform_set = self.catalog.get_uniform_set(row["selector"])
                try:
                    retail = colour.resolve_uniform_color_record(
                        self.cache.pack0, uniform_set.selector
                    )
                    canonical = (
                        f"{colour.parse_color(row['facemask']):08X}",
                        f"{colour.parse_color(row['turtleneck']):08X}",
                    )
                except colour.UnifColorWriterError as exc:
                    raise ValidationError(str(exc)) from exc
                if canonical == retail.pair:
                    raise ValidationError(
                        f"Project colours for {uniform_set.selector} match the "
                        "source record; replacement-only projects may not carry no-op edits."
                    )
                new_unif_colors[uniform_set.selector] = canonical
            previous_state = (
                self._edits, self.text_edits, self._audio_edits,
                self._crib_edits, self._stadium_edits,
                self._audio_annotations, self._unif_colors,
                self._play_route_edits,
                self._undo, self._crib_undo,
                self._stadium_undo, self._audio_undo, self._undo_order,
            )
            # Compute exact atomic-manifest and generated-preview headroom while
            # the imported state is visible only in memory, then restore it.
            self._edits = new_visual
            self.text_edits = new_text
            self._audio_edits = new_audio
            self._crib_edits = new_crib
            self._stadium_edits = new_stadium
            self._audio_annotations = new_annotations
            self._unif_colors = new_unif_colors
            self._play_route_edits = new_play_routes
            try:
                manifest_size = len(_canonical_json(self._manifest_document()))
            finally:
                (
                    self._edits, self.text_edits, self._audio_edits,
                    self._crib_edits, self._stadium_edits,
                    self._audio_annotations, self._unif_colors,
                    self._play_route_edits,
                    _old_undo, _old_crib_undo, _old_stadium_undo,
                    _old_audio_undo, _old_undo_order,
                ) = previous_state
            preview_bytes = sum(len(row[3]) for row in stadium_moves)
            commit_headroom = manifest_size + preview_bytes + (1024 * 1024)
            if shutil.disk_usage(self.root).free < commit_headroom:
                raise ValidationError(
                    "There is not enough free space to finish importing this project. "
                    "Free space on the Mod Studio session drive and try again."
                )

            written: list[Path] = []
            try:
                for staged_path, destination in (*png_moves, *audio_moves):
                    with _explain_write_failure(destination):
                        os.replace(platform_compat.long_path(staged_path), platform_compat.long_path(destination))
                    written.append(destination)
                for staged_path, authored, preview, preview_payload in stadium_moves:
                    _write_new_atomic(preview, preview_payload)
                    written.append(preview)
                    with _explain_write_failure(authored):
                        os.replace(platform_compat.long_path(staged_path), platform_compat.long_path(authored))
                    written.append(authored)
                self._edits = new_visual
                self.text_edits = new_text
                self._audio_edits = new_audio
                self._crib_edits = new_crib
                self._stadium_edits = new_stadium
                self._audio_annotations = new_annotations
                self._unif_colors = new_unif_colors
                self._play_route_edits = new_play_routes
                self._undo = []
                self._crib_undo = []
                self._stadium_undo = []
                self._audio_undo = []
                self._undo_order = []
                self._write_manifest()
            except BaseException as original_error:
                (
                    self._edits, self.text_edits, self._audio_edits,
                    self._crib_edits, self._stadium_edits,
                    self._audio_annotations, self._unif_colors,
                    self._play_route_edits,
                    self._undo, self._crib_undo,
                    self._stadium_undo, self._audio_undo, self._undo_order,
                ) = previous_state
                rollback_errors: list[str] = []
                for destination in reversed(written):
                    try:
                        destination.unlink(missing_ok=True)
                    except OSError as rollback_error:
                        rollback_errors.append(
                            f"{destination.name}: {rollback_error}"
                        )
                if rollback_errors:
                    raise ValidationError(
                        "Project import failed and private-file cleanup was incomplete: "
                        + "; ".join(rollback_errors)
                    ) from original_error
                if isinstance(original_error, OSError):
                    raise ValidationError(
                        "Could not commit the project to the private workspace: "
                        f"{original_error}"
                    ) from original_error
                raise
            return len(loaded.edits) + (
                new_text.modified_count if new_text is not None else 0
            ) + len(new_audio) + len(new_annotations) + len(new_unif_colors) \
                + len(new_play_routes)
        finally:
            loaded.cleanup()

    def iter_edits(self) -> Iterable[SessionEdit]:
        for asset_id in sorted(self._edits):
            yield self._edits[asset_id]

    def attach_visual_catalog(self, catalog: Any) -> None:
        """Give the session the aggregate that resolves every visual browser.

        The facade already builds one; attaching it here just saves the
        session from building its own.
        """

        self.visual_catalog = catalog

    def _visual_asset(self, asset_id: str) -> Any:
        """Resolve one staged PNG edit through the catalog that owns its ID.

        Only the uniform sets live in ``self.catalog``.  Everything else a
        visual browser can stage -- ``tset:`` uniform equipment (socks, elbow
        pads, gloves, long sleeves, shoes, wristbands), ``p8:`` textures,
        portraits, live faces, create-field art, the scorebug -- is minted by
        the extended catalog, and asking the uniform catalog about one of those
        IDs raises "Unknown uniform asset ID".

        That is exactly what happened: ``replace()`` takes an already-resolved
        asset *object* from the panel, so staging a Bengals sock worked, and
        every later step re-resolved the ID *string* through the wrong catalog
        and refused. Build, Save Project, Load Project, batch import, Undo's
        restore and Revert All all funnel through here now, so a browser can
        never again stage something the build cannot name.

        ``Nfl2k5ProductVisualCatalog`` was written for this -- its own
        docstring says a reversible session can use it "for either catalog
        without knowing where the asset originated" -- and it is built from the
        uniform catalog this session already holds, so a uniform edit resolves
        to the identical object it always did.
        """

        catalog = self.visual_catalog
        if catalog is None:
            catalog = self._derive_visual_catalog()
        return catalog.get_asset(asset_id)

    def _derive_visual_catalog(self) -> Any:
        """Build the aggregate from this session's own uniform catalog.

        Deriving it rather than requiring a caller to attach one keeps the
        "nobody wired it up" failure mode from existing at all. A session given
        a stand-in catalog (tests, doubles) keeps using that stand-in.
        """

        if not isinstance(self.catalog, _Nfl2k5UniformCatalog):
            return self.catalog
        try:
            self.visual_catalog = Nfl2k5ProductVisualCatalog(
                self.catalog, load_nfl2k5_extended_visual_catalog()
            )
        except Exception:
            # A missing or unreadable extended report must not take out uniform
            # editing, which never needed it.
            return self.catalog
        return self.visual_catalog

    def iter_project_png_edits(self) -> Iterable[SessionEdit]:
        """Yield all user-authored PNG edits accepted by the project router."""

        yield from self.iter_edits()
        for asset_id in sorted(self._crib_edits):
            yield self._crib_edits[asset_id]
        for asset_id in sorted(self._stadium_edits):
            yield self._stadium_edits[asset_id]

    def _snapshot_previous(self, asset_id: str) -> Path | None:
        previous = self._edits.get(asset_id)
        if previous is None:
            return None
        self._history_sequence += 1
        snapshot = self.history / (
            f"{self._history_sequence:08d}-{_asset_key(asset_id)}.png"
        )
        copy_user_asset_atomic(previous.replacement_path, snapshot)
        return snapshot

    def _snapshot_audio(self, asset_id: str) -> Path | None:
        previous = self._audio_edits.get(asset_id)
        if previous is None:
            return None
        self._history_sequence += 1
        snapshot = self.history / (
            f"{self._history_sequence:08d}-{_asset_key(asset_id)}.wav"
        )
        copy_user_asset_atomic(previous.replacement_path, snapshot)
        return snapshot

    def _snapshot_crib(self, asset_id: str) -> Path | None:
        previous = self._crib_edits.get(asset_id)
        if previous is None:
            return None
        self._history_sequence += 1
        snapshot = self.history / (
            f"{self._history_sequence:08d}-{_asset_key(asset_id)}.png"
        )
        copy_user_asset_atomic(previous.replacement_path, snapshot)
        return snapshot

    def _snapshot_stadium(self, asset_id: str) -> Path | None:
        previous = self._stadium_edits.get(asset_id)
        if previous is None:
            return None
        self._history_sequence += 1
        snapshot = self.history / (
            f"{self._history_sequence:08d}-{_asset_key(asset_id)}.png"
        )
        copy_user_asset_atomic(previous.replacement_path, snapshot)
        return snapshot

    def _stage_stadium_edit(
        self,
        texture: StadiumTexture,
        payload: bytes,
        rgba: bytes,
        compiled: CompiledStadiumTextureEdit,
    ) -> StadiumSessionEdit:
        if (
            compiled.texture_id != texture.texture_id
            or compiled.replacement_png_sha256 != sha256_bytes(payload)
            or compiled.replacement_rgba_sha256 != sha256_bytes(rgba)
            or compiled.quantized_preview_png_sha256
            != sha256_bytes(compiled.quantized_preview_png)
        ):
            raise ValidationError("The compiled Stadium texture changed before staging.")
        token = uuid4().hex
        key = _asset_key(texture.texture_id)
        authored = self.replacements / f"{key}-{token}.png"
        preview = self.replacements / f"{key}-{token}.preview.png"
        _write_new_atomic(authored, payload)
        try:
            _write_new_atomic(preview, compiled.quantized_preview_png)
        except BaseException:
            authored.unlink(missing_ok=True)
            raise
        return StadiumSessionEdit(
            texture.texture_id,
            authored,
            sha256_bytes(payload),
            sha256_bytes(rgba),
            preview,
            sha256_bytes(compiled.quantized_preview_png),
        )

    @staticmethod
    def _remove_stadium_edit_files(edit: StadiumSessionEdit) -> None:
        edit.replacement_path.unlink(missing_ok=True)
        edit.preview_path.unlink(missing_ok=True)

    def _validate_stadium_project_png(
        self, texture: StadiumTexture, path: Path
    ) -> tuple[bytes, bytes]:
        writer = self._require_supported_stadium_texture(texture)
        supplied = path.expanduser().resolve(strict=True)
        stock = texture.png_path.expanduser().resolve(strict=True)
        if supplied == stock:
            payload, rgba = writer.read_validated_png(stock, texture)
            if (
                sha256_bytes(payload) != texture.png_sha256
                or sha256_bytes(rgba) != texture.rgba_sha256
            ):
                raise ValidationError(
                    "The private Stadium preview no longer matches its manifest."
                )
            return payload, rgba
        payload, rgba, _compiled = writer.validated_replacement(texture, supplied)
        return payload, rgba

    def _manifest_document(self) -> dict[str, object]:
        document = {
            "edits": [
                {
                    "asset_id": edit.asset_id,
                    "replacement_sha256": edit.replacement_sha256,
                    "rgba_sha256": edit.rgba_sha256,
                }
                for edit in self.iter_edits()
            ],
            "schema": SESSION_SCHEMA,
            "session_id": self.session_id,
            "source_sha256": self.cache.source.sha256,
        }
        if self.text_edits is not None:
            document["text_replacements"] = self.text_edits.replacement_document()
        if self._audio_edits:
            document["audio_edits"] = [
                {
                    "asset_id": edit.asset_id,
                    "replacement_sha256": edit.replacement_sha256,
                }
                for edit in sorted(
                    self._audio_edits.values(), key=lambda item: item.asset_id
                )
            ]
        if self._audio_annotations:
            document["audio_annotations"] = annotation_document(
                self.audio_annotations
            )
        if self._crib_edits:
            document["crib_edits"] = [
                {
                    "asset_id": edit.asset_id,
                    "selector": self._require_crib_catalog().get(
                        edit.asset_id
                    ).selector,
                    "replacement_sha256": edit.replacement_sha256,
                    "rgba_sha256": edit.rgba_sha256,
                }
                for edit in sorted(
                    self._crib_edits.values(), key=lambda item: item.asset_id
                )
            ]
        if self._stadium_edits:
            document["stadium_edits"] = [
                {
                    "asset_id": edit.asset_id,
                    "replacement_sha256": edit.replacement_sha256,
                    "rgba_sha256": edit.rgba_sha256,
                    "preview_sha256": edit.preview_sha256,
                    "shared_ownership_note": self._stadium_ownership_note(
                        self._stadium_texture_for_id(edit.asset_id)
                    ),
                }
                for edit in sorted(
                    self._stadium_edits.values(), key=lambda item: item.asset_id
                )
            ]
        if self._stadium_geometry_edit is not None:
            edit = self._stadium_geometry_edit
            document["stadium_geometry_edit"] = {
                "asset_id": edit.asset_id,
                "scene_id": edit.scene_id,
                "recipe_sha256": edit.recipe_sha256,
                "changed_target_count": edit.changed_target_count,
                "changed_vertex_count": edit.changed_vertex_count,
                "preserved_triangle_count": edit.preserved_triangle_count,
                "private_source_derived_recipe": True,
            }
        if self._crib_geometry_edits:
            document["crib_geometry_edits"] = [
                {
                    "asset_id": edit.asset_id,
                    "scene_id": edit.scene_id,
                    "recipe_sha256": edit.recipe_sha256,
                    "changed_target_count": edit.changed_target_count,
                    "changed_vertex_count": edit.changed_vertex_count,
                    "preserved_triangle_count": edit.preserved_triangle_count,
                    "private_source_derived_recipe": True,
                }
                for edit in sorted(
                    self._crib_geometry_edits.values(),
                    key=lambda item: item.scene_id,
                )
            ]
        if self._unif_colors:
            document["uniform_colors"] = [
                {
                    "selector": selector,
                    "facemask": self._unif_colors[selector][0],
                    "turtleneck": self._unif_colors[selector][1],
                }
                for selector in sorted(self._unif_colors)
            ]
        if self._play_route_edits:
            document["play_route_edits"] = [
                request.provider_edit() for request in self.play_route_edits
            ]
        return document

    def _write_manifest(self) -> None:
        _replace_atomic(
            self.root / "session.json",
            _canonical_json(self._manifest_document()),
        )
        self._mutation_revision += 1

    def _project_png_asset(self, asset_id: str) -> Any:
        if STADIUM_TEXTURE_SELECTOR_RE.fullmatch(asset_id) is not None:
            if self.stadium_writer is None:
                raise StadiumProjectPreparationRequired(
                    "This project includes an editable Stadium texture. Prepare "
                    "Stadium Studio from your own game copy, then open the project "
                    "again."
                )
            return _ProjectStadiumAsset(self._stadium_texture_for_id(asset_id))
        if asset_id.startswith("nfl2k5.crib."):
            return self._require_crib_catalog().get(asset_id)
        return self._visual_asset(asset_id)

    def _require_text_catalog(self) -> Nfl2k5TextCatalog:
        if self.text_catalog is None:
            raise ValidationError("Load the game's text catalog before editing text.")
        return self.text_catalog

    def _require_text_edits(self) -> Nfl2k5TextEdits:
        if self.text_edits is None:
            raise ValidationError("Load the game's text catalog before editing text.")
        return self.text_edits

    def _require_audio_service(self) -> Nfl2k5AudioService:
        if self.audio_service is None:
            raise ValidationError("Load the game's audio catalog before using audio.")
        return self.audio_service

    def _require_crib_catalog(self) -> Nfl2k5CribCatalog:
        if self.crib_catalog is None:
            raise ValidationError("Load the game's Crib catalog before using The Crib.")
        return self.crib_catalog

    def _require_crib_io(self) -> Nfl2k5CribIO:
        if self.crib_io is None:
            raise ValidationError("Load the game's Crib catalog before using The Crib.")
        return self.crib_io

    def _require_stadium_writer(self) -> Nfl2k5StadiumTextureWriter:
        if self.stadium_writer is None:
            raise ValidationError(
                "Open Stadium Studio before using an editable Stadium texture."
            )
        return self.stadium_writer

    def _stadium_texture_for_id(self, asset_id: str) -> StadiumTexture:
        selected = self._stadium_textures.get(asset_id)
        if selected is not None:
            return selected
        writer = self._require_stadium_writer()
        selected = writer.texture(asset_id)
        self._stadium_textures[asset_id] = selected
        return selected

    @staticmethod
    def _stadium_ownership_note(texture: StadiumTexture) -> str:
        if not texture.mapped_material_names:
            return (
                "No direct decoded material owner; the visible consumer may be "
                "indirect or absent."
            )
        names = ", ".join(texture.mapped_material_names[:8])
        if len(texture.mapped_material_names) > 8:
            names += f", and {len(texture.mapped_material_names) - 8} more"
        return (
            f"Shared by {texture.mapped_material_count} material(s): {names}. "
            "Every linked surface changes together."
        )

    def _require_supported_stadium_texture(
        self, texture: StadiumTexture
    ) -> Nfl2k5StadiumTextureWriter:
        writer = self._require_stadium_writer()
        if not writer.supports(texture):
            raise ValidationError(
                "That Stadium texture is Preview/Export-only because its complete "
                "fixed P8/SCNE ownership could not be proved."
            )
        self._stadium_textures[texture.texture_id] = texture
        return writer
